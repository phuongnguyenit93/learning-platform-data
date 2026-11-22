# Materialized view và lựa chọn ON DEMAND hoặc ON COMMIT trong Oracle Database

Trong hệ thống báo cáo, một truy vấn có thể phải tổng hợp hàng triệu dòng giao dịch mỗi lần người dùng mở dashboard. Nếu kết quả tổng hợp không cần được tính lại từ đầu ở mọi request, Oracle Database có thể lưu trước kết quả đó dưới dạng **materialized view (MV)**. Khi dữ liệu nguồn thay đổi, materialized view cần được refresh để đồng bộ với các bảng nền.

Khi tạo materialized view, một quyết định quan trọng là **khi nào refresh**:

- **ON DEMAND:** refresh khi ứng dụng, DBA hoặc scheduler yêu cầu. Dữ liệu trong MV có thể cũ giữa hai lần refresh.
- **ON COMMIT:** refresh tự động khi transaction thay đổi các bảng nền commit. Dữ liệu được cập nhật tại ranh giới commit, nhưng chi phí refresh được đưa vào đường ghi dữ liệu.

Lựa chọn này ảnh hưởng đến độ mới của báo cáo, thời gian COMMIT, tải hệ thống, khả năng chịu lỗi và cách vận hành. Không có lựa chọn tốt nhất cho mọi workload. Cần hiểu materialized view lưu gì, refresh FAST/COMPLETE/FORCE hoạt động ra sao, materialized view log hỗ trợ thế nào và truy vấn báo cáo chấp nhận độ trễ bao nhiêu.

## 1. View và materialized view khác nhau thế nào?

### 1.1 View thông thường

View lưu định nghĩa truy vấn, không lưu kết quả dữ liệu như một bản sao vật lý:

~~~sql
CREATE OR REPLACE VIEW v_sales_by_region AS
SELECT region_id,
       SUM(amount) AS total_amount
FROM sales
GROUP BY region_id;
~~~

Khi truy vấn:

~~~sql
SELECT *
FROM v_sales_by_region;
~~~

Oracle thực thi kế hoạch truy vấn dựa trên các bảng nguồn. View giúp đóng gói logic và tái sử dụng câu SQL; bản thân view không phải snapshot được lưu sẵn của kết quả.

### 1.2 Materialized view

Materialized view lưu kết quả truy vấn dưới dạng dữ liệu vật lý trong database. Ví dụ:

~~~sql
CREATE MATERIALIZED VIEW mv_sales_by_region
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT region_id,
       SUM(amount) AS total_amount
FROM sales
GROUP BY region_id;
~~~

Oracle thực thi defining query để tạo dữ liệu ban đầu trong MV. Khi truy vấn:

~~~sql
SELECT *
FROM mv_sales_by_region;
~~~

ứng dụng đọc dữ liệu đã được materialize. MV có thể giúp giảm chi phí tính toán lặp lại, nhất là khi truy vấn tổng hợp nặng và dữ liệu nguồn thay đổi ít hơn tần suất đọc.

### 1.3 So sánh

| Tiêu chí | View | Materialized view |
|---|---|---|
| Lưu định nghĩa SQL | Có | Có |
| Lưu kết quả dữ liệu vật lý | Không như một bản sao kết quả | Có |
| Khi truy vấn | Tính theo dữ liệu nguồn và execution plan | Đọc kết quả đã materialize; có thể được optimizer dùng qua query rewrite |
| Cập nhật kết quả | Phản ánh dữ liệu nguồn theo truy vấn | Cần refresh theo chính sách |
| Chi phí lưu trữ | Chủ yếu metadata | Cần segment, index và metadata |
| Chi phí ghi dữ liệu nguồn | Không có refresh MV | Có thể phát sinh log/refresh overhead |
| Phù hợp | Đóng gói logic, truy vấn linh hoạt | Báo cáo/tổng hợp cần tái sử dụng kết quả |

Materialized view không tự động nhanh hơn view. Nếu MV thường xuyên phải COMPLETE refresh, quá lớn hoặc truy vấn nguồn đã rất rẻ, tổng chi phí lưu trữ và refresh có thể không đáng.

## 2. Các thành phần của materialized view

Một MV thường có các thành phần:

1. **Defining query:** SELECT xác định dữ liệu được lưu.
2. **Detail/base tables:** các bảng nguồn mà defining query đọc.
3. **Materialized view segment:** nơi Oracle lưu các dòng kết quả.
4. **Refresh method:** cách đồng bộ kết quả, chẳng hạn FAST hoặc COMPLETE.
5. **Refresh mode:** thời điểm refresh, chẳng hạn ON DEMAND hoặc ON COMMIT.
6. **Materialized view log:** metadata/change records trên bảng nền, khi cần cho fast refresh.
7. **Index và statistics:** hỗ trợ truy vấn trực tiếp MV và optimizer.

Ví dụ luồng:

~~~text
SALES (bảng giao dịch)
        |
        v
Defining query: GROUP BY REGION
        |
        v
MV_SALES_BY_REGION (kết quả lưu vật lý)
        |
        +--> Dashboard đọc kết quả
        |
        +--> Optimizer có thể cân nhắc query rewrite
~~~

Materialized view là đối tượng schema có thể được truy vấn như bảng/view. Tuy nhiên, ứng dụng thông thường nên xem nó là dữ liệu dẫn xuất và để Oracle refresh theo chính sách; không tự ý cập nhật trực tiếp các dòng MV như thể đó là bảng nghiệp vụ gốc.

## 3. Tạo materialized view cơ bản

### 3.1 Tạo bảng nguồn minh họa

Trong schema lab riêng:

~~~sql
CREATE TABLE sales (
    sale_id   NUMBER PRIMARY KEY,
    region_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    amount    NUMBER(12,2)
);
~~~

Nạp một vài dòng:

~~~sql
INSERT INTO sales VALUES (1, 10, DATE '2026-01-05', 100);
INSERT INTO sales VALUES (2, 10, DATE '2026-01-06', 150);
INSERT INTO sales VALUES (3, 20, DATE '2026-01-07', 200);
INSERT INTO sales VALUES (4, 20, DATE '2026-01-08', 50);
COMMIT;
~~~

### 3.2 Tạo MV refresh theo yêu cầu

~~~sql
CREATE MATERIALIZED VIEW mv_sales_by_region
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT region_id,
       COUNT(*) AS sale_count,
       COUNT(amount) AS known_amount_count,
       SUM(amount) AS total_amount
FROM sales
GROUP BY region_id;
~~~

Các lựa chọn:

- BUILD IMMEDIATE: chạy defining query ngay khi tạo để nạp dữ liệu ban đầu.
- REFRESH COMPLETE: mỗi lần refresh, tính lại toàn bộ kết quả theo defining query.
- ON DEMAND: không tự refresh theo mỗi commit của bảng nguồn; refresh khi được gọi hoặc theo lịch.

Có thể truy vấn:

~~~sql
SELECT *
FROM mv_sales_by_region
ORDER BY region_id;
~~~

Kết quả ban đầu:

| REGION_ID | SALE_COUNT | KNOWN_AMOUNT_COUNT | TOTAL_AMOUNT |
|---:|---:|---:|---:|
| 10 | 2 | 2 | 250 |
| 20 | 2 | 2 | 250 |

### 3.3 BUILD IMMEDIATE và BUILD DEFERRED

- BUILD IMMEDIATE: tạo MV và nạp dữ liệu ban đầu ngay.
- BUILD DEFERRED: tạo metadata trước, chưa populate dữ liệu cho đến lần refresh đầu tiên.

Nếu dùng BUILD DEFERRED, phải có kế hoạch refresh ban đầu trước khi ứng dụng phụ thuộc vào MV. Không giả định MV vừa tạo đã chứa dữ liệu khi chưa được populate.

### 3.4 Khai báo refresh mode tường minh

Oracle thường mặc định refresh mode là ON DEMAND nếu không chỉ định ON COMMIT. Tuy nhiên, trong DDL production nên ghi rõ mode để người đọc không phải dựa vào default:

~~~sql
REFRESH COMPLETE ON DEMAND
~~~

Cách viết tường minh giúp review và vận hành migration dễ hơn.

## 4. Hai lựa chọn refresh mode: ON DEMAND và ON COMMIT

### 4.1 ON DEMAND

ON DEMAND nghĩa là MV được refresh khi có yêu cầu. Yêu cầu có thể đến từ:

- DBA hoặc người vận hành gọi DBMS_MVIEW.REFRESH.
- Ứng dụng gọi procedure refresh theo lịch nghiệp vụ.
- DBMS_SCHEDULER chạy job định kỳ.
- Một quy trình batch refresh sau khi nạp dữ liệu nguồn.

Giữa hai lần refresh, MV có thể ở trạng thái STALE so với bảng nền. Đây là đặc điểm được chấp nhận nếu báo cáo có thể chịu độ trễ.

### 4.2 ON COMMIT

ON COMMIT nghĩa là Oracle refresh MV khi transaction thay đổi các bảng nền commit. Refresh được gắn với đường commit của transaction đó.

Điều này giảm khoảng thời gian dữ liệu MV bị cũ sau khi transaction nguồn commit, nhưng có thể làm commit của ứng dụng chậm hơn vì database phải thực hiện công việc refresh liên quan.

Với workload ghi nhiều, một transaction có thể cập nhật nhiều dòng/bảng nền và kéo theo refresh MV. Nếu có nhiều MV ON COMMIT phụ thuộc cùng nguồn, chi phí ghi có thể tăng đáng kể.

### 4.3 Bảng so sánh

| Tiêu chí | ON DEMAND | ON COMMIT |
|---|---|---|
| Thời điểm refresh | Khi được gọi hoặc theo lịch | Khi transaction thay đổi bảng nền commit |
| Độ mới dữ liệu | Có độ trễ theo lịch/yêu cầu | Được refresh tại ranh giới commit nếu refresh thành công |
| Ảnh hưởng đến COMMIT của bảng nguồn | Thường tách khỏi commit ghi dữ liệu | Có thể tăng thời gian commit |
| Điều khiển thời điểm | Linh hoạt | Tự động theo commit |
| Khả năng gom nhiều thay đổi | Có thể gom thành một lần refresh | Refresh gắn với từng transaction commit liên quan |
| Phù hợp | Báo cáo định kỳ, batch, dashboard chấp nhận lag | MV nhỏ/đủ điều kiện, cần độ mới cao |
| Vận hành | Cần scheduler/trigger gọi refresh và giám sát lịch | Cần giám sát tác động trực tiếp lên đường ghi |

### 4.4 Không có lựa chọn luôn tốt hơn

Chọn ON COMMIT chỉ vì muốn “dữ liệu luôn mới” có thể làm tăng độ trễ giao dịch của hệ thống OLTP. Chọn ON DEMAND cho báo cáo yêu cầu số liệu mới nhất ngay sau giao dịch có thể khiến người dùng thấy số liệu cũ.

Quyết định nên dựa trên:

- Độ trễ dữ liệu tối đa được chấp nhận.
- Tần suất và khối lượng DML trên bảng nền.
- Số lượng MV phụ thuộc.
- Khả năng fast refresh của defining query.
- SLA của đường đọc và đường ghi.
- Khung thời gian refresh, tài nguyên và cơ chế phục hồi.

## 5. Refresh method: FAST, COMPLETE và FORCE

Refresh mode trả lời **khi nào** refresh; refresh method trả lời **bằng cách nào** refresh.

### 5.1 COMPLETE refresh

COMPLETE refresh thực thi lại defining query để tính toàn bộ dữ liệu MV:

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'MV_SALES_BY_REGION',
        method => 'C'
    );
END;
/
~~~

'C' là mã method cho COMPLETE trong DBMS_MVIEW. Cách refresh này không phụ thuộc vào việc có thể tính delta từ MV log hay không, nhưng có thể tốn tài nguyên nếu truy vấn nguồn lớn.

Phù hợp khi:

- MV nhỏ hoặc defining query không hỗ trợ fast refresh.
- Tần suất refresh thấp.
- Cần tính lại toàn bộ kết quả để đơn giản hóa vận hành.
- Thay đổi nguồn hoặc cấu trúc khiến fast refresh không còn khả thi.

### 5.2 FAST refresh

FAST refresh cập nhật MV dựa trên những thay đổi đã ghi nhận ở bảng nền, thay vì tính lại toàn bộ kết quả. Với nhiều loại MV, Oracle cần materialized view log trên bảng nền và defining query phải thỏa các điều kiện fast refresh.

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'MV_SALES_BY_REGION',
        method => 'F'
    );
END;
/
~~~

FAST refresh thường giảm lượng dữ liệu phải xử lý khi phần thay đổi nhỏ so với toàn bộ bảng. Nhưng nó cần thêm chi phí ghi log, lưu trữ và quản lý khả năng refresh.

Không phải mọi SELECT đều fast refresh được. Các yếu tố như GROUP BY, aggregate, DISTINCT, UNION, join, biểu thức, subquery và thao tác DML trên bảng nguồn ảnh hưởng khả năng này. Hãy dùng công cụ kiểm tra capability thay vì suy đoán chỉ từ cú pháp.

### 5.3 FORCE refresh

FORCE yêu cầu Oracle thử FAST refresh nếu có thể; nếu không, Oracle có thể thực hiện COMPLETE refresh:

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'MV_SALES_BY_REGION',
        method => '?'
    );
END;
/
~~~

Dấu hỏi là mã FORCE trong API DBMS_MVIEW. Đây là lựa chọn linh hoạt nhưng kết quả có thể có chi phí khác nhau giữa các lần chạy: một lần FAST, lần khác COMPLETE. Nếu SLA phụ thuộc vào thời gian refresh, cần biết method thực tế được dùng và giám sát nó.

### 5.4 Phân biệt mode và method

| Khái niệm | Ví dụ | Câu hỏi |
|---|---|---|
| Refresh mode | ON DEMAND, ON COMMIT | Khi nào MV được refresh? |
| Refresh method | FAST, COMPLETE, FORCE | Refresh bằng cách nào? |

Ví dụ:

~~~sql
REFRESH FAST ON DEMAND
~~~

nghĩa là refresh theo yêu cầu, dùng phương pháp FAST nếu defining query đáp ứng điều kiện.

~~~sql
REFRESH FAST ON COMMIT
~~~

nghĩa là yêu cầu fast refresh khi transaction thay đổi bảng nền commit. Phải xác nhận MV đủ điều kiện fast refresh và thỏa các giới hạn của phiên bản Oracle đang chạy.

## 6. Materialized view log và FAST refresh

### 6.1 Vì sao cần materialized view log?

Để fast refresh, Oracle cần biết những thay đổi nào đã xảy ra ở bảng nền kể từ lần refresh trước. Materialized view log là đối tượng ghi lại thông tin thay đổi phục vụ quá trình này.

Ví dụ minh họa:

~~~sql
CREATE MATERIALIZED VIEW LOG ON sales
WITH ROWID, SEQUENCE (region_id, sale_date, amount)
INCLUDING NEW VALUES;
~~~

MV log được tạo trên bảng nền SALES. Các lựa chọn log phụ thuộc loại defining query và kiểu fast refresh mong muốn:

- PRIMARY KEY hoặc ROWID xác định cách nhận diện dòng nguồn.
- Các cột được ghi log phải đáp ứng nhu cầu của defining query.
- SEQUENCE có thể cần cho một số trường hợp cần giữ thứ tự thay đổi.
- INCLUDING NEW VALUES lưu thông tin giá trị mới cần thiết cho một số kiểu fast refresh, đặc biệt với aggregate.

Đây là ví dụ minh họa, không phải công thức chung cho mọi MV. Cột và option chính xác cần được xác định từ capability của truy vấn và phiên bản Oracle.

### 6.2 MV log làm tăng chi phí ghi

Khi bảng nền INSERT, UPDATE hoặc DELETE, Oracle có thể phải ghi thêm thông tin vào MV log. Điều này làm tăng:

- Dung lượng lưu trữ.
- Redo/undo và I/O liên quan.
- Công việc DML trên bảng nền.
- Công việc dọn log sau các lần refresh phù hợp.

FAST refresh giảm chi phí tính lại MV trong một số workload nhưng không miễn phí. Phải đo tổng chi phí đọc, ghi, refresh và storage.

### 6.3 Một bảng có thể có log phục vụ nhiều MV

Một materialized view log trên bảng nền có thể hỗ trợ nhiều MV phụ thuộc, nếu cấu hình log đáp ứng tất cả yêu cầu của chúng. Nếu thêm MV mới cần cột log hoặc option chưa có, có thể phải thay đổi log. Không drop log chỉ vì một MV đã bị xóa nếu còn MV khác phụ thuộc.

### 6.4 Kiểm tra khả năng FAST refresh

Oracle cung cấp DBMS_MVIEW.EXPLAIN_MVIEW để phân tích khả năng refresh và query rewrite của một MV hoặc defining query.

Trong schema có quyền, tạo bảng capability bằng script Oracle cung cấp, thường là utlxmv.sql trong thư mục quản trị database:

~~~sql
@?/rdbms/admin/utlxmv.sql
~~~

Sau đó:

~~~sql
BEGIN
    DBMS_MVIEW.EXPLAIN_MVIEW(
        mv           => 'MV_SALES_BY_REGION',
        statement_id => 'CHECK_SALES_MV'
    );
END;
/
~~~

Xem kết quả:

~~~sql
SELECT capability_name,
       possible,
       related_text,
       msgtxt
FROM mv_capabilities_table
WHERE statement_id = 'CHECK_SALES_MV'
ORDER BY seq;
~~~

Các dòng capability giải thích khả năng FAST refresh, PCT refresh, query rewrite và những điều kiện chưa thỏa. Tên/cột output cụ thể cần đối chiếu script utlxmv.sql đi kèm phiên bản database.

### 6.5 EXPLAIN_MVIEW trước khi chọn ON COMMIT

Nếu định dùng ON COMMIT, kiểm tra khả năng fast refresh trước khi triển khai. ON COMMIT gắn refresh vào đường commit, nên một MV không đủ điều kiện hoặc refresh quá nặng có thể làm kế hoạch vận hành không phù hợp.

Ngoài capability, hãy thử DML thực tế trên môi trường test để đo commit latency và kiểm tra trigger, foreign key, concurrency, số lượng MV phụ thuộc.

## 7. Ví dụ FAST refresh cho MV tổng hợp

Ví dụ sau minh họa một MV tổng hợp doanh thu theo khu vực. Khả năng fast refresh thực tế phải được xác nhận bằng EXPLAIN_MVIEW trên đúng phiên bản Oracle và defining query.

### 7.1 Tạo MV log

~~~sql
CREATE MATERIALIZED VIEW LOG ON sales
WITH ROWID, SEQUENCE (region_id, amount)
INCLUDING NEW VALUES;
~~~

### 7.2 Tạo MV có aggregate hỗ trợ refresh

~~~sql
CREATE MATERIALIZED VIEW mv_sales_fast
BUILD IMMEDIATE
REFRESH FAST ON DEMAND
AS
SELECT region_id,
       COUNT(*) AS row_count,
       COUNT(amount) AS amount_count,
       SUM(amount) AS total_amount
FROM sales
GROUP BY region_id;
~~~

Với aggregate MV, các aggregate bổ sung như COUNT(*) và COUNT(measure) có thể cần thiết để Oracle duy trì kết quả sau INSERT/UPDATE/DELETE. Điều kiện chính xác phụ thuộc loại aggregate và defining query.

### 7.3 Thay đổi bảng nguồn

~~~sql
INSERT INTO sales (
    sale_id,
    region_id,
    sale_date,
    amount
)
VALUES (
    5,
    10,
    DATE '2026-01-10',
    75
);

COMMIT;
~~~

MV đang ON DEMAND nên chưa được yêu cầu refresh chỉ vì transaction nguồn commit. Truy vấn MV trước refresh có thể vẫn trả số liệu cũ.

### 7.4 Gọi FAST refresh

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'MV_SALES_FAST',
        method => 'F'
    );
END;
/
~~~

Sau refresh, truy vấn MV sẽ phản ánh thay đổi theo khả năng và semantics refresh. Nếu FAST không khả thi, lệnh yêu cầu FAST có thể thất bại; không tự giả định Oracle sẽ chuyển sang COMPLETE khi method được chỉ định rõ là F.

### 7.5 So sánh với COMPLETE

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'MV_SALES_FAST',
        method => 'C'
    );
END;
/
~~~

COMPLETE tính lại toàn bộ kết quả theo defining query. Đây là phương án dự phòng khi fast refresh không phù hợp, nhưng cần đánh giá thời gian, I/O và ảnh hưởng workload.

## 8. ON DEMAND: refresh thủ công hoặc theo lịch

### 8.1 Refresh thủ công

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'MV_SALES_BY_REGION',
        method => 'C'
    );
END;
/
~~~

Ứng dụng hoặc DBA có thể gọi refresh sau khi một batch nạp dữ liệu hoàn tất. Với MV đủ điều kiện, dùng F để yêu cầu FAST; dùng dấu hỏi để yêu cầu FORCE.

### 8.2 Lên lịch bằng DBMS_SCHEDULER

Ví dụ refresh mỗi giờ:

~~~sql
BEGIN
    DBMS_SCHEDULER.CREATE_JOB(
        job_name        => 'JOB_REFRESH_MV_SALES',
        job_type        => 'PLSQL_BLOCK',
        job_action      =>
            'BEGIN DBMS_MVIEW.REFRESH(''MV_SALES_BY_REGION'', ''F''); END;',
        start_date      => SYSTIMESTAMP,
        repeat_interval => 'FREQ=HOURLY;INTERVAL=1',
        enabled         => TRUE,
        comments        => 'Refresh sales materialized view hourly'
    );
END;
/
~~~

Job chạy theo lịch đã khai báo. Cần bảo đảm owner có quyền phù hợp, defining query và MV log sẵn sàng, lịch refresh không chồng lấn quá mức và thời gian hoàn thành nằm trong cửa sổ vận hành.

### 8.3 Lịch refresh không phải cam kết dữ liệu luôn mới đúng từng giờ

Nếu job bị lỗi, bị disable, không có tài nguyên hoặc refresh mất lâu hơn chu kỳ, MV có thể stale lâu hơn dự kiến. Hệ thống cần giám sát:

- Lần refresh thành công gần nhất.
- Trạng thái stale.
- Thời gian chạy và số lần lỗi.
- Job có đang chạy hoặc bị trễ không.
- Khoảng trễ dữ liệu thực tế so với SLA.

### 8.4 Refresh sau batch load

Nếu ETL nạp dữ liệu một lần mỗi đêm, có thể refresh MV sau khi ETL và validation hoàn tất. Điều này tránh refresh nhiều lần trong lúc dữ liệu nguồn đang được nạp theo từng bước.

Một quy trình:

~~~text
Load dữ liệu nguồn
       |
       v
Validate / reconcile
       |
       v
COMMIT batch nguồn
       |
       v
Refresh MV
       |
       v
Kiểm tra kết quả và đánh dấu batch hoàn tất
~~~

Nếu refresh lỗi, giữ trạng thái batch đã nạp nhưng MV chưa được cập nhật và cho phép retry refresh theo chính sách. Không chạy lại ETL mù nếu batch nguồn đã commit.

## 9. ON COMMIT: refresh trong đường commit

### 9.1 Tạo MV ON COMMIT

Ví dụ minh họa:

~~~sql
CREATE MATERIALIZED VIEW mv_sales_on_commit
BUILD IMMEDIATE
REFRESH FAST ON COMMIT
AS
SELECT region_id,
       COUNT(*) AS row_count,
       COUNT(amount) AS amount_count,
       SUM(amount) AS total_amount
FROM sales
GROUP BY region_id;
~~~

Để mẫu này hoạt động, defining query phải đủ điều kiện FAST refresh và bảng nền cần MV log phù hợp. ON COMMIT có các giới hạn về cấu trúc truy vấn và đối tượng nguồn; phải kiểm tra capability và SQL Language Reference của phiên bản Oracle đang dùng.

### 9.2 Điều gì xảy ra khi transaction nguồn COMMIT?

Ví dụ:

~~~sql
INSERT INTO sales (
    sale_id,
    region_id,
    sale_date,
    amount
)
VALUES (
    6,
    10,
    DATE '2026-01-11',
    25
);

COMMIT;
~~~

Khi transaction thay đổi bảng SALES commit, Oracle thực hiện refresh ON COMMIT cho MV phụ thuộc theo cơ chế được cấu hình. Công việc refresh gắn với commit, vì vậy thời gian COMMIT có thể tăng.

### 9.3 ON COMMIT không refresh sau mỗi câu DML

Nếu transaction thực hiện:

~~~sql
INSERT INTO sales VALUES (7, 10, DATE '2026-01-12', 40);
UPDATE sales SET amount = 45 WHERE sale_id = 7;
DELETE FROM sales WHERE sale_id = 7;

COMMIT;
~~~

ON COMMIT gắn refresh với thời điểm transaction commit, không phải refresh riêng sau từng câu INSERT, UPDATE và DELETE. Điều này cho phép Oracle xử lý thay đổi của transaction như một đơn vị refresh.

### 9.4 Ảnh hưởng đến latency và throughput

ON COMMIT có thể phù hợp khi số thay đổi nhỏ và tần suất commit không quá cao. Với OLTP có nhiều transaction ngắn, mỗi transaction cập nhật bảng nền có thể kéo theo refresh. Kết quả:

- Commit latency tăng.
- CPU và I/O tăng trên đường ghi.
- MV log và refresh cần tài nguyên.
- Nhiều MV phụ thuộc có thể làm chi phí tăng thêm.
- Transaction có thể gặp lỗi nếu quá trình refresh không hoàn tất theo yêu cầu.

Đo cả latency p50/p95/p99 của commit và throughput giao dịch, không chỉ thời gian SELECT trên MV.

### 9.5 ON COMMIT không phải cơ chế đồng bộ giữa nhiều hệ thống

ON COMMIT cập nhật MV trong cùng Oracle database theo quan hệ bảng nền. Nó không bảo đảm một dịch vụ bên ngoài, cache, search index hoặc hệ thống BI khác đã nhận dữ liệu. Các hệ thống đó cần cơ chế đồng bộ riêng.

## 10. Độ mới dữ liệu và trạng thái STALE

### 10.1 MV có thể stale

Với ON DEMAND, sau khi bảng nền thay đổi nhưng trước lần refresh tiếp theo, MV có thể chứa kết quả cũ. Oracle có metadata để thể hiện trạng thái freshness/staleness.

### 10.2 Xem trạng thái MV

Trong schema sở hữu MV:

~~~sql
SELECT mview_name,
       staleness,
       last_refresh_type,
       last_refresh_date,
       compile_state
FROM user_mviews
ORDER BY mview_name;
~~~

Các cột này giúp vận hành kiểm tra:

- STALENESS: trạng thái mới/cũ theo metadata Oracle.
- LAST_REFRESH_TYPE: kiểu refresh gần nhất.
- LAST_REFRESH_DATE: thời điểm refresh gần nhất.
- COMPILE_STATE: trạng thái compile của MV.

Tên/cột metadata có thể khác theo phiên bản hoặc view dictionary được dùng; kiểm tra USER_MVIEWS/ALL_MVIEWS/DBA_MVIEWS của hệ thống.

### 10.3 STALE không nhất thiết có nghĩa dữ liệu sai theo mọi mục đích

Nếu dashboard chấp nhận dữ liệu trễ 15 phút, MV stale 5 phút có thể vẫn đáp ứng yêu cầu. Ngược lại, một màn hình số dư tài khoản cần cập nhật ngay có thể không chấp nhận stale dù chỉ vài giây.

Định nghĩa freshness bằng yêu cầu nghiệp vụ, ví dụ:

- Dashboard điều hành: tối đa 15 phút.
- Báo cáo cuối ngày: refresh sau khi batch ETL hoàn tất.
- Báo cáo đối soát: chỉ đọc sau khi xác nhận refresh thành công.
- Luồng giao dịch: đọc bảng nguồn hoặc một cơ chế đồng bộ phù hợp nếu không chấp nhận MV stale.

### 10.4 Query rewrite và freshness

Nếu MV được bật query rewrite, Oracle có thể dùng MV thay cho truy vấn trên bảng nguồn khi điều kiện phù hợp. Việc có dùng MV stale hay không còn phụ thuộc QUERY_REWRITE_INTEGRITY và chính sách freshness. Không nên giả định query rewrite luôn dùng dữ liệu mới nhất hoặc luôn dùng MV.

## 11. Query rewrite: optimizer sử dụng materialized view

### 11.1 Mục đích

Query rewrite cho phép optimizer thay một truy vấn trên bảng nguồn bằng truy vấn tương đương trên MV, khi MV chứa đủ thông tin và các điều kiện ngữ nghĩa được thỏa.

Ví dụ MV tổng hợp:

~~~sql
CREATE MATERIALIZED VIEW mv_sales_region_qr
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
ENABLE QUERY REWRITE
AS
SELECT region_id,
       SUM(amount) AS total_amount
FROM sales
GROUP BY region_id;
~~~

Ứng dụng có thể chạy:

~~~sql
SELECT region_id,
       SUM(amount)
FROM sales
GROUP BY region_id;
~~~

Oracle có thể cân nhắc rewrite sang MV nếu query rewrite được bật, quyền và metadata phù hợp, MV đủ điều kiện và optimizer thấy có lợi. Đây không phải cam kết rằng mọi truy vấn tương tự sẽ luôn đọc MV.

### 11.2 Bật query rewrite ở session/database

Tham số hệ thống/session liên quan:

~~~sql
ALTER SESSION SET QUERY_REWRITE_ENABLED = TRUE;
~~~

Quyền thay đổi tham số phụ thuộc môi trường. DBA có thể cấu hình ở mức hệ thống; developer có thể cần quyền phù hợp để thay đổi ở session.

### 11.3 QUERY_REWRITE_INTEGRITY

Các mức thường gặp:

- ENFORCED: yêu cầu các ràng buộc/điều kiện đảm bảo tính đúng đắn được thực thi theo chính sách nghiêm ngặt.
- TRUSTED: cho phép optimizer dựa trên một số constraint/relationship được tin cậy.
- STALE_TOLERATED: cho phép dùng MV stale trong phạm vi chính sách cho phép.

Không chọn STALE_TOLERATED chỉ để tăng tốc nếu báo cáo cần dữ liệu mới nhất. Query rewrite integrity là quyết định về tính đúng của dữ liệu trả về, không chỉ là một nút tối ưu hiệu năng.

### 11.4 Kiểm tra query rewrite

Có thể xem execution plan:

~~~sql
EXPLAIN PLAN FOR
SELECT region_id,
       SUM(amount)
FROM sales
GROUP BY region_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Nếu plan thể hiện truy cập MV, optimizer đã chọn MV cho truy vấn đó. Nếu không, có thể do query rewrite chưa bật, MV không đủ điều kiện, freshness/integrity, thống kê, cost hoặc khác biệt biểu thức.

## 12. Chọn ON DEMAND hay ON COMMIT theo workload

### 12.1 ON DEMAND phù hợp khi

- Báo cáo chấp nhận dữ liệu trễ theo lịch.
- Bảng nguồn ghi liên tục và không muốn thêm refresh vào mỗi commit.
- Có thể gom nhiều thay đổi rồi refresh một lần.
- MV lớn hoặc COMPLETE refresh cần chạy trong cửa sổ batch.
- Hệ thống có pipeline ETL và checkpoint rõ.
- Muốn chủ động kiểm soát thời gian, tải và thời điểm refresh.

Ví dụ: dashboard doanh thu tổng hợp mỗi 15 phút hoặc báo cáo điều hành sau batch cuối ngày.

### 12.2 ON COMMIT phù hợp khi

- Cần MV được cập nhật cùng thời điểm transaction nguồn commit.
- Số thay đổi nhỏ hoặc refresh incremental rất nhẹ.
- Defining query đáp ứng yêu cầu fast refresh và giới hạn ON COMMIT.
- Tải ghi có đủ ngân sách cho chi phí refresh bổ sung.
- Đội vận hành đã đo commit latency và có cảnh báo phù hợp.

Ví dụ: một bảng tổng hợp nhỏ dùng cho màn hình quản trị cần phản ánh giao dịch đã commit gần như ngay lập tức.

### 12.3 Bảng quyết định

| Câu hỏi | Nếu câu trả lời là “có” | Hướng cân nhắc |
|---|---|---|
| Báo cáo chấp nhận stale vài phút/giờ? | Có | ON DEMAND |
| Có batch load theo lịch? | Có | ON DEMAND sau batch |
| OLTP commit rất nhiều và cần latency thấp? | Có | Tránh thêm refresh vào mỗi commit; cân nhắc ON DEMAND |
| Cần MV cập nhật ngay tại commit? | Có | Đánh giá ON COMMIT |
| Defining query không fast refresh được? | Có | ON DEMAND với COMPLETE/FORCE hoặc thiết kế lại MV |
| Bảng nền thay đổi ít, MV nhỏ? | Có | ON COMMIT có thể phù hợp nếu đủ điều kiện |
| Có nhiều MV phụ thuộc cùng bảng? | Có | Đo tổng chi phí refresh và cân nhắc gom lịch |
| Cần kiểm soát chính xác thời gian refresh? | Có | ON DEMAND |

## 13. Các kiểu refresh và tùy chọn vận hành

### 13.1 DBMS_MVIEW.REFRESH

Gọi một MV:

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'MV_SALES_BY_REGION',
        method => 'F'
    );
END;
/
~~~

Refresh nhiều MV:

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'MV_SALES_BY_REGION,MV_SALES_BY_PRODUCT',
        method => 'C'
    );
END;
/
~~~

Các MV có dependency hoặc cần refresh theo thứ tự cần được thiết kế đúng. Không chỉ nối tên vào một chuỗi mà bỏ qua quan hệ giữa các MV lồng nhau.

### 13.2 Atomic refresh

DBMS_MVIEW.REFRESH có tham số atomic_refresh. Khi phù hợp, atomic refresh giúp refresh nhóm MV theo cách có tính nguyên tử hơn; nếu refresh thất bại, có thể rollback phần refresh theo semantics của API. Đổi atomic_refresh sang FALSE có thể cho phép chiến lược refresh khác và hiệu năng tốt hơn trong một số trường hợp, nhưng cần hiểu trạng thái trung gian, khả năng phục hồi và giới hạn DDL/refresh của phiên bản.

Không thay đổi atomic_refresh chỉ vì muốn refresh nhanh hơn mà chưa thử trên dữ liệu đại diện. Đây là lựa chọn về vận hành và tính nhất quán.

### 13.3 COMPLETE refresh có thể tốn tài nguyên

Với MV lớn, COMPLETE refresh có thể đọc lại nhiều dữ liệu nguồn, tạo nhiều I/O, CPU, TEMP và redo/undo tùy cách refresh. Cần lên lịch vào cửa sổ tải phù hợp, kiểm tra dung lượng và ảnh hưởng truy vấn đồng thời.

### 13.4 FORCE refresh có thể thay đổi thời gian chạy

FORCE có thể dùng FAST nếu khả thi, nếu không thì COMPLETE. Vì vậy cùng một job có thể có thời gian chạy khác nhau sau thay đổi schema, log hoặc defining query. Giám sát LAST_REFRESH_TYPE và runtime thay vì chỉ nhìn trạng thái job thành công.

## 14. Giới hạn và điều kiện cần kiểm tra

Materialized view và refresh có nhiều quy tắc theo phiên bản Oracle, kiểu defining query và đối tượng nguồn. Trước triển khai, kiểm tra ít nhất:

- Defining query có đủ điều kiện FAST refresh không?
- Các bảng nguồn đã có MV log với cột/option phù hợp chưa?
- Có remote table/database link không? Một số kiểu refresh, đặc biệt ON COMMIT, có giới hạn với remote detail tables.
- MV có join, aggregate, DISTINCT, UNION, analytic function, subquery hoặc biểu thức phức tạp không?
- Có dùng object/view hoặc function ảnh hưởng tính determinism không?
- Có cần primary key/ROWID/sequence/new values trong log không?
- ON COMMIT có được hỗ trợ cho cấu trúc cụ thể không?
- Có MV lồng nhau hoặc nhiều MV cùng phụ thuộc bảng nền không?
- Refresh có xung đột với batch load, partition maintenance hoặc DDL không?
- Dung lượng log và thời gian lưu change records có đủ cho lịch refresh không?

Không suy luận khả năng FAST chỉ vì câu SELECT chạy được. SELECT hợp lệ không đồng nghĩa materialized view có thể fast refresh.

## 15. Theo dõi materialized view và refresh job

### 15.1 Xem danh sách MV trong schema

~~~sql
SELECT mview_name,
       refresh_mode,
       refresh_method,
       staleness,
       last_refresh_type,
       last_refresh_date
FROM user_mviews
ORDER BY mview_name;
~~~

Các cột giúp xem mode, method được cấu hình và trạng thái refresh gần nhất. Tùy phiên bản, metadata có thể bổ sung hoặc khác tên; xem dictionary view của database cụ thể.

### 15.2 Xem materialized view logs

~~~sql
SELECT log_table,
       master,
       rowids,
       primary_key,
       include_new_values
FROM user_mview_logs
ORDER BY master;
~~~

USER_MVIEW_LOGS cho biết log gắn với bảng nền trong schema. Để xem chi tiết hơn có thể dùng các view ALL_/DBA_ tương ứng khi có quyền.

### 15.3 Xem job refresh

~~~sql
SELECT job_name,
       enabled,
       state,
       last_start_date,
       next_run_date,
       run_count,
       failure_count
FROM user_scheduler_jobs
WHERE job_name = 'JOB_REFRESH_MV_SALES';
~~~

Lịch sử job:

~~~sql
SELECT log_date,
       status,
       error#,
       actual_start_date,
       run_duration,
       additional_info
FROM user_scheduler_job_run_details
WHERE job_name = 'JOB_REFRESH_MV_SALES'
ORDER BY log_date DESC;
~~~

Giám sát job và giám sát freshness là hai việc khác nhau. Job có thể SUCCESS nhưng MV vẫn không đáp ứng SLA freshness nếu lịch chạy quá thưa hoặc dữ liệu nguồn tiếp tục thay đổi.

### 15.4 Kiểm tra dữ liệu đối soát

Có thể so sánh tổng hợp MV với truy vấn nguồn trong cửa sổ kiểm tra:

~~~sql
SELECT region_id,
       SUM(amount) AS source_total
FROM sales
GROUP BY region_id;
~~~

và:

~~~sql
SELECT region_id,
       total_amount
FROM mv_sales_by_region;
~~~

Trong production, đối soát có thể cần snapshot nhất quán, cùng cutoff/batch ID hoặc cùng thời điểm dữ liệu. Nếu bảng nguồn tiếp tục thay đổi giữa hai câu SELECT, kết quả khác nhau không nhất thiết chứng minh MV refresh sai.

## 16. Thay đổi defining query và refresh

### 16.1 CREATE OR REPLACE không phải cách thay đổi MV phổ quát

Materialized view có metadata và dữ liệu lưu trữ riêng. Không áp dụng máy móc CREATE OR REPLACE VIEW cho materialized view. Khi cần đổi defining query, phải chọn quy trình phù hợp như DROP/CREATE hoặc các thao tác được Oracle hỗ trợ cho MV, có đánh giá dependency, quyền, index, log và downtime.

### 16.2 Thay đổi bảng nền

ALTER TABLE trên detail table có thể ảnh hưởng defining query, MV log hoặc khả năng refresh. Trước migration:

1. Liệt kê MV phụ thuộc bảng.
2. Kiểm tra log và refresh capability.
3. Xác định DDL có làm invalid MV hoặc thay đổi query semantics không.
4. Lập kế hoạch refresh/recreate và kiểm tra sau triển khai.

DDL trong Oracle có implicit commit, nên không đặt thay đổi schema vào cùng transaction với DML backfill rồi kỳ vọng rollback toàn bộ nếu refresh lỗi.

### 16.3 Drop MV log khi không còn dependency

~~~sql
DROP MATERIALIZED VIEW LOG ON sales;
~~~

Chỉ drop log khi đã xác nhận không còn MV nào cần log đó cho fast refresh. Nếu còn MV phụ thuộc, fast refresh của chúng có thể thất bại hoặc phải chuyển sang phương án khác.

## 17. Materialized view và query rewrite trong kiến trúc báo cáo

### 17.1 MV như reporting layer

Một mô hình:

~~~text
OLTP tables
    |
    v
MV logs / refresh process
    |
    v
Materialized views (summary layer)
    |
    +--> Dashboard
    +--> BI reports
    +--> Query rewrite
~~~

MV giúp tách workload đọc báo cáo khỏi việc tính tổng hợp lặp lại trên bảng giao dịch. Tuy nhiên, nó vẫn dùng tài nguyên database và cần chính sách freshness.

### 17.2 Chọn mode theo SLA đọc và ghi

Nếu SLA ghi ưu tiên commit nhanh, ON DEMAND thường đáng cân nhắc vì refresh có thể chạy sau. Nếu SLA đọc yêu cầu kết quả cập nhật ngay sau commit và refresh nhẹ, ON COMMIT có thể hợp lý.

Không chỉ hỏi “báo cáo cần mới đến mức nào?” mà còn hỏi “giao dịch nguồn có chấp nhận trả thêm chi phí refresh không?”.

### 17.3 Query rewrite không thay thế API contract

Ứng dụng không nên dựa vào việc optimizer chắc chắn rewrite mọi query sang MV. Nếu ứng dụng cần đọc MV cụ thể, có thể truy vấn MV trực tiếp và kiểm soát freshness; nếu muốn optimizer tự chọn, cần chấp nhận đó là quyết định cost-based và kiểm tra plan.

## 18. Bài lab: so sánh ON DEMAND và ON COMMIT

Các lệnh trong phần này dành cho schema thực hành riêng có quyền tạo MV, MV log, job và quota phù hợp. Không chạy DDL/DML thử nghiệm trên schema production. Oracle DDL có implicit commit.

### 18.1 Tạo bảng nguồn và dữ liệu

~~~sql
CREATE TABLE lab_sales (
    sale_id   NUMBER PRIMARY KEY,
    region_id NUMBER NOT NULL,
    amount    NUMBER(12,2)
);

INSERT INTO lab_sales VALUES (1, 10, 100);
INSERT INTO lab_sales VALUES (2, 10, 150);
INSERT INTO lab_sales VALUES (3, 20, 200);
COMMIT;
~~~

### 18.2 Tạo MV ON DEMAND

~~~sql
CREATE MATERIALIZED VIEW lab_mv_sales_demand
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT region_id,
       COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM lab_sales
GROUP BY region_id;
~~~

Kiểm tra:

~~~sql
SELECT *
FROM lab_mv_sales_demand
ORDER BY region_id;
~~~

### 18.3 Thay đổi bảng nguồn

~~~sql
INSERT INTO lab_sales VALUES (4, 10, 50);
COMMIT;
~~~

Truy vấn MV ON DEMAND:

~~~sql
SELECT *
FROM lab_mv_sales_demand
ORDER BY region_id;
~~~

MV có thể chưa phản ánh dòng mới vì chưa gọi refresh.

### 18.4 Refresh theo yêu cầu

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'LAB_MV_SALES_DEMAND',
        method => 'C'
    );
END;
/
~~~

Truy vấn lại và quan sát TOTAL_AMOUNT của REGION_ID=10 đã tăng từ 250 lên 300.

### 18.5 Tạo MV log cho thử nghiệm FAST

~~~sql
CREATE MATERIALIZED VIEW LOG ON lab_sales
WITH ROWID, SEQUENCE (region_id, amount)
INCLUDING NEW VALUES;
~~~

Tạo MV thử nghiệm:

~~~sql
CREATE MATERIALIZED VIEW lab_mv_sales_fast
BUILD IMMEDIATE
REFRESH FAST ON DEMAND
AS
SELECT region_id,
       COUNT(*) AS row_count,
       COUNT(amount) AS amount_count,
       SUM(amount) AS total_amount
FROM lab_sales
GROUP BY region_id;
~~~

Nếu CREATE hoặc FAST refresh không được hỗ trợ theo cấu hình/phiên bản, dùng DBMS_MVIEW.EXPLAIN_MVIEW để xem capability và thông báo. Không bỏ qua lỗi rồi kết luận FAST refresh hoạt động.

### 18.6 Thay đổi nguồn và FAST refresh

~~~sql
INSERT INTO lab_sales VALUES (5, 20, 75);
COMMIT;

BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'LAB_MV_SALES_FAST',
        method => 'F'
    );
END;
/
~~~

So sánh tổng trong MV với bảng nguồn sau refresh.

### 18.7 Thử ON COMMIT trên MV đủ điều kiện

Chỉ thực hiện sau khi đã xác nhận capability và hiểu các giới hạn của phiên bản Oracle:

~~~sql
CREATE MATERIALIZED VIEW lab_mv_sales_commit
BUILD IMMEDIATE
REFRESH FAST ON COMMIT
AS
SELECT region_id,
       COUNT(*) AS row_count,
       COUNT(amount) AS amount_count,
       SUM(amount) AS total_amount
FROM lab_sales
GROUP BY region_id;
~~~

Thử:

~~~sql
INSERT INTO lab_sales VALUES (6, 10, 25);

-- Trước COMMIT, session hiện tại chưa kết thúc transaction nguồn.
SELECT *
FROM lab_mv_sales_commit
WHERE region_id = 10;

COMMIT;

-- Sau COMMIT thành công, kiểm tra MV.
SELECT *
FROM lab_mv_sales_commit
WHERE region_id = 10;
~~~

Quan sát thời gian COMMIT và kết quả sau commit. Không so sánh latency chỉ bằng một lần chạy; cần nhiều lần với số dòng và mức cạnh tranh đại diện.

### 18.8 Kiểm tra metadata

~~~sql
SELECT mview_name,
       refresh_mode,
       refresh_method,
       staleness,
       last_refresh_type,
       last_refresh_date
FROM user_mviews
WHERE mview_name LIKE 'LAB_MV_%'
ORDER BY mview_name;
~~~

### 18.9 Dọn bảng lab

Chỉ xóa các MV, log và bảng do bạn tạo trong schema thực hành sau khi đã xác nhận không còn cần dữ liệu. DDL có implicit commit:

~~~sql
DROP MATERIALIZED VIEW lab_mv_sales_commit;
DROP MATERIALIZED VIEW lab_mv_sales_fast;
DROP MATERIALIZED VIEW lab_mv_sales_demand;
DROP MATERIALIZED VIEW LOG ON lab_sales;
DROP TABLE lab_sales;
~~~

Không chạy lệnh DROP trên đối tượng không thuộc lab của bạn. Nếu một MV chưa được tạo thành công, bỏ qua đúng lệnh DROP tương ứng thay vì nuốt mọi lỗi.

## 19. Lỗi và ngộ nhận thường gặp

| Lỗi/ngộ nhận | Thực tế | Cách xử lý |
|---|---|---|
| MV giống view thông thường | MV lưu kết quả vật lý | Quản lý storage và refresh |
| ON DEMAND luôn mới | MV có thể stale giữa hai lần refresh | Theo dõi freshness và SLA |
| ON COMMIT miễn phí | Refresh được đưa vào đường commit | Đo commit latency và throughput |
| FAST refresh luôn được hỗ trợ | Defining query và log phải đáp ứng điều kiện | Dùng EXPLAIN_MVIEW |
| FORCE luôn nhanh như FAST | FORCE có thể chuyển sang COMPLETE | Theo dõi LAST_REFRESH_TYPE |
| MV log không có chi phí | Log tăng storage, redo/undo và chi phí DML | Đo tổng workload |
| ON COMMIT refresh sau từng câu DML | Refresh gắn với transaction commit | Hiểu transaction boundary |
| CREATE MV xong luôn có dữ liệu | BUILD DEFERRED chưa populate | Refresh ban đầu |
| Query rewrite luôn dùng MV | Optimizer quyết định theo cost và điều kiện | Xem execution plan |
| STALE luôn là lỗi | Có thể chấp nhận theo SLA | Định nghĩa freshness rõ |
| ON COMMIT phù hợp mọi dashboard | Có thể làm chậm OLTP commit | Cân nhắc ON DEMAND |
| Drop MV log không ảnh hưởng MV khác | Nhiều MV có thể phụ thuộc cùng log | Kiểm tra dependency trước |
| ROLLBACK hoàn tác CREATE/ALTER MV | DDL có implicit commit | Dùng DDL bù hoặc kế hoạch phục hồi |
| Job SUCCESS nghĩa MV mới đúng SLA | Job có thể chạy đúng nhưng lịch quá thưa | Giám sát cả freshness |

## 20. Checklist lựa chọn và triển khai

Trước khi tạo materialized view:

1. Truy vấn nguồn có đủ nặng hoặc được dùng đủ thường xuyên để đáng materialize không?
2. Định nghĩa grouping và measure đã đúng cấp dữ liệu chưa?
3. Báo cáo chấp nhận dữ liệu stale tối đa bao lâu?
4. ON DEMAND có thể đáp ứng SLA bằng lịch hoặc refresh sau batch không?
5. Nếu cần ON COMMIT, defining query có đủ điều kiện và refresh đủ nhẹ không?
6. Có cần FAST refresh hay COMPLETE là đủ?
7. MV log cần PRIMARY KEY, ROWID, SEQUENCE, cột nào và INCLUDING NEW VALUES không?
8. Đã chạy EXPLAIN_MVIEW và thử DML thực tế chưa?
9. Chi phí log và refresh có làm giảm throughput ghi không?
10. Có nhiều MV phụ thuộc cùng bảng nguồn không?
11. Có cần query rewrite? Đã xác định QUERY_REWRITE_INTEGRITY phù hợp chưa?
12. Có lịch refresh, owner, quyền và giám sát job chưa?
13. Có đối soát MV với nguồn theo snapshot/batch nhất quán không?
14. Có kế hoạch khi refresh lỗi hoặc job trễ không?
15. Migration schema có xử lý DDL implicit commit và dependency MV không?
16. Có theo dõi STALENESS, LAST_REFRESH_DATE, runtime và lỗi không?

## 21. Tổng kết

Materialized view lưu kết quả của một truy vấn dưới dạng dữ liệu vật lý để tái sử dụng cho báo cáo hoặc workload đọc. MV cần refresh khi dữ liệu bảng nền thay đổi.

- **ON DEMAND** refresh khi được gọi hoặc theo lịch. Nó tách công việc refresh khỏi commit của giao dịch nguồn, cho phép gom thay đổi và phù hợp với báo cáo chấp nhận độ trễ.
- **ON COMMIT** refresh khi transaction thay đổi bảng nền commit. Nó giúp dữ liệu MV được cập nhật tại ranh giới commit nhưng có thể làm tăng commit latency và chi phí của workload ghi.
- **FAST** áp dụng thay đổi tăng dần khi defining query và MV log đáp ứng điều kiện.
- **COMPLETE** tính lại toàn bộ defining query.
- **FORCE** thử FAST, nếu không khả thi có thể dùng COMPLETE.
- Materialized view log hỗ trợ fast refresh nhưng làm tăng chi phí ghi và storage.
- EXPLAIN_MVIEW, USER_MVIEWS, scheduler history và execution plan giúp kiểm tra khả năng, trạng thái và vận hành.
- Query rewrite cho phép optimizer cân nhắc dùng MV thay truy vấn nguồn; nó phụ thuộc cấu hình, tính đúng đắn, freshness và cost.

Hãy chọn ON DEMAND hay ON COMMIT theo độ trễ dữ liệu mà nghiệp vụ chấp nhận và chi phí mà đường ghi có thể chịu. Một MV chỉ hữu ích khi dữ liệu đủ mới cho mục đích sử dụng, refresh có thể vận hành ổn định và tổng chi phí đọc/ghi/lưu trữ thực sự tốt hơn truy vấn trực tiếp.
