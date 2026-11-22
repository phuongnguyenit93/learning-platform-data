# Generic plan, custom plan và câu lệnh được chuẩn bị trong PostgreSQL

Một ứng dụng thường lặp đi lặp lại các câu SQL có **cùng cấu trúc nhưng khác tham số**:

~~~sql
SELECT job_id, state, payload
FROM jobs
WHERE state = 'rare';

SELECT job_id, state, payload
FROM jobs
WHERE state = 'common';
~~~

Nếu dùng tham số, cấu trúc có thể trở thành một câu lệnh được chuẩn bị:

~~~sql
PREPARE lookup_job(text) AS
SELECT job_id, state, payload
FROM jobs
WHERE state = $1;
~~~

Sau đó ứng dụng truyền giá trị khác nhau khi thực thi:

~~~sql
EXECUTE lookup_job('rare');
EXECUTE lookup_job('common');
~~~

Câu hỏi tưởng đơn giản nhưng có tác động lớn đến hiệu năng là: **PostgreSQL có nên lập kế hoạch riêng cho từng giá trị tham số, hay tái sử dụng một kế hoạch chung cho mọi giá trị?**

- **Custom plan** được tối ưu dựa trên **giá trị tham số của lần thực thi cụ thể**. Nó có thể chọn đường truy cập khác nhau cho `'rare'` và `'common'`, nhưng có chi phí lập kế hoạch lặp lại.
- **Generic plan** là một kế hoạch có thể **tái sử dụng cho nhiều bộ tham số**, vì không phụ thuộc vào giá trị cụ thể khi lập kế hoạch. Nó giảm chi phí planning về sau, nhưng có thể không phù hợp với những giá trị tham số đặc biệt.

Đó là nội dung trung tâm của bài **“Generic plan, custom plan và câu lệnh được chuẩn bị”**, thuộc chương **Kế hoạch truy vấn** của module **Database Engine Relational PostgreSQL**.

Bài học sẽ giải thích cơ chế chọn plan, cung cấp ví dụ SQL thực hành, cách đọc `EXPLAIN EXECUTE`, các lỗi khi dữ liệu phân bố lệch, sự khác nhau giữa `PREPARE` phía server và `PreparedStatement` trong Java/JDBC, cùng các biện pháp điều tra an toàn trước khi thay đổi cấu hình production.

## 1. Bốn khái niệm cần tách bạch

| Khái niệm | Câu hỏi nó trả lời |
|---|---|
| **Parameterized SQL** | Thay các giá trị cụ thể bằng tham số như `$1` hoặc `?` như thế nào? |
| **Prepared statement** | Cấu trúc câu lệnh có được server/client giữ lại để thực thi nhiều lần không? |
| **Custom plan** | Có lập kế hoạch dựa trên giá trị tham số **của lần chạy này** không? |
| **Generic plan** | Có thể dùng chung một kế hoạch cho **nhiều lần chạy với các giá trị khác nhau** không? |

Một hiểu nhầm phổ biến là:

> “Đã PREPARE thì chỉ tạo một plan duy nhất một lần, và mọi EXECUTE sau đó bắt buộc dùng lại plan ấy.”

Điều này **không đúng** với PostgreSQL. Một prepared statement có thể được thực thi nhiều lần bằng **các custom plans khác nhau**, hoặc một **generic plan** có thể được tái sử dụng, tùy cấu hình và cơ chế chọn plan.

Một hiểu nhầm khác:

> “Ứng dụng Java dùng PreparedStatement, tức là PostgreSQL chắc chắn đang dùng generic plan.”

Cũng **không đúng**. `PreparedStatement` là một API của JDBC; việc driver sử dụng server-side prepared statement và việc server chọn generic/custom là **hai quyết định khác nhau**.

## 2. Vì sao PostgreSQL cần kế hoạch truy vấn?

SQL diễn đạt **kết quả cần có**, không cố định từng bước đọc dữ liệu.

Ví dụ:

~~~sql
SELECT job_id, payload
FROM jobs
WHERE state = 'rare';
~~~

PostgreSQL phải quyết định có thể:

- Quét toàn bảng (`Seq Scan`).
- Dùng B-tree index (`Index Scan`).
- Dùng `Bitmap Index Scan` + `Bitmap Heap Scan`.
- Sắp xếp ở đâu, nếu có `ORDER BY`.
- Chọn join order, join algorithm và index phù hợp nếu có JOIN.
- Ước lượng số hàng thỏa `WHERE`.
- Xem xét chi phí I/O, CPU, parallelism và các yếu tố kế hoạch khác.

Những quyết định này nằm trong **execution plan**. Người học có thể xem bằng:

~~~sql
EXPLAIN
SELECT job_id, payload
FROM jobs
WHERE state = 'rare';
~~~

Planner không đoán bằng cảm tính; nó dùng metadata, thống kê của bảng, index, các điều kiện truy vấn và mô hình chi phí.

### 2.1. Hai giá trị tham số có thể tạo hai yêu cầu rất khác nhau

Giả sử bảng có 1.000.000 hàng:

~~~text
state = 'common': 999.000 hàng
state = 'rare'  :   1.000 hàng
~~~

Với `state='common'`, một `Seq Scan` có thể rẻ hơn việc đọc phần rất lớn bảng qua index rồi fetch nhiều heap pages.

Với `state='rare'`, `Index Scan` hoặc `Bitmap Heap Scan` có thể hiệu quả hơn vì chỉ cần tìm một phần nhỏ dữ liệu.

Cùng một cấu trúc SQL nhưng **phân bố giá trị tham số** làm kế hoạch tối ưu khác nhau.

Đây là tình huống mà custom plan có thể có lợi.

## 3. Đường đi từ câu SQL đến execution plan

Một mô hình đơn giản:

~~~text
Ứng dụng gửi câu SQL
          |
          v
Phân tích cú pháp (parse)
          |
          v
Phân tích ngữ nghĩa / kiểu / quan hệ (analyze)
          |
          v
Viết lại truy vấn khi cần (rewrite)
          |
          v
Lập kế hoạch (plan)
          |
          v
Thực thi (execute)
          |
          v
Trả kết quả
~~~

Prepared statement cho phép server giữ lại những thông tin cần thiết liên quan cấu trúc câu lệnh và tránh một phần công việc lặp lại. Nhưng ở bước planning vẫn có lựa chọn:

~~~text
Prepared statement đã có
          |
          v
EXECUTE với tham số mới
          |
          +--> Custom plan:
          |      lập plan có xét giá trị tham số lần này
          |
          +--> Generic plan:
                 dùng một plan không phụ thuộc
                 giá trị tham số cụ thể
~~~

**Generic không có nghĩa là không có `WHERE` hoặc index.** Nó chỉ có nghĩa planner không được tối ưu bằng cách giả định một giá trị tham số cụ thể tại thời điểm lập generic plan.

## 4. PREPARE, EXECUTE và DEALLOCATE

PostgreSQL cung cấp cú pháp SQL trực tiếp:

~~~sql
PREPARE statement_name (parameter_type, ...)
AS
sql_statement;
~~~

Ví dụ tự chứa không cần bảng thực:

~~~sql
PREPARE plus_tax(numeric) AS
SELECT $1 + 10::NUMERIC AS total;

EXECUTE plus_tax(100);
EXECUTE plus_tax(250);

DEALLOCATE plus_tax;
~~~

Kết quả:

~~~text
EXECUTE plus_tax(100) -> 110
EXECUTE plus_tax(250) -> 260
~~~

Các thành phần:

- `PREPARE` đặt tên câu lệnh và xác định kiểu của tham số.
- `$1` tham chiếu tham số thứ nhất; `$2` là tham số thứ hai, v.v.
- `EXECUTE` truyền giá trị cụ thể.
- `DEALLOCATE` giải phóng prepared statement đã đặt tên trong session.

### 4.1. PREPARE có phải câu lệnh thực thi query không?

`PREPARE` khai báo câu lệnh cho những lần chạy sau, **không trả tập kết quả của SELECT được chuẩn bị**.

~~~sql
PREPARE find_one(bigint) AS
SELECT $1 AS requested_id;
~~~

Để có kết quả:

~~~sql
EXECUTE find_one(42);
~~~

### 4.2. Không thể chuẩn bị hai statement cùng tên trong một session

Nếu `plus_tax` đã tồn tại, việc dùng lại `PREPARE plus_tax` trong cùng session có thể lỗi. Hãy `DEALLOCATE plus_tax` hoặc dùng tên khác.

Không tự gọi `DEALLOCATE ALL` trong một session ứng dụng đang chạy nhiều chức năng, bởi lệnh này ảnh hưởng **mọi prepared statement của session hiện tại**.

### 4.3. PREPARE tồn tại bao lâu?

Câu lệnh `PREPARE` SQL thông thường có hiệu lực trong **session hiện tại** cho tới khi bị `DEALLOCATE` hoặc session kết thúc.

Nó không tự chia sẻ sang connection khác và không phải một đối tượng schema bền vững như TABLE/VIEW.

## 5. PostgreSQL có những lớp “prepared” khác nhau

Từ “prepared statement” xuất hiện ở nhiều tầng:

| Tầng | Ví dụ | Ý nghĩa |
|---|---|---|
| SQL server-side | `PREPARE name(text) AS ...` | Tạo prepared statement có tên trong session PostgreSQL |
| Wire protocol | PostgreSQL extended query protocol: Parse/Bind/Execute | Driver truyền câu lệnh và giá trị tham số, có thể dùng named/unnamed statement |
| JDBC | `connection.prepareStatement(sql)` | Ứng dụng tạo đối tượng PreparedStatement và bind tham số |
| Driver cache | Cache statement của driver/pool | Tối ưu việc lặp lại cấu trúc và protocol calls |
| Server plan cache | Generic/custom plan decision | PostgreSQL quyết định lập mới theo tham số hay tái sử dụng plan |

Những tầng này **liên quan nhưng không đồng nhất**.

Ví dụ Java gọi:

~~~java
PreparedStatement ps = connection.prepareStatement(
    "SELECT job_id FROM plan_lab.jobs WHERE state = ?"
);
~~~

không tự chứng minh một SQL-level `PREPARE name` đã được tạo theo cú pháp SQL. Driver có thể dùng extended query protocol, statement không tên, named statement hoặc cơ chế chuyển trạng thái sau một số lần chạy.

Để kết luận server chọn generic hay custom cần quan sát ở **server**, không chỉ nhìn tên class JDBC.

## 6. Generic plan là gì?

Một **generic plan** được tối ưu mà **không dựa vào giá trị tham số cụ thể** cho lần chạy.

Ví dụ:

~~~sql
PREPARE find_by_state(text) AS
SELECT job_id, state, payload
FROM plan_lab.jobs
WHERE state = $1;
~~~

Khi server xây generic plan, nó không thể giả định chắc chắn `$1='rare'` hay `$1='common'`. Nó phải chọn một phương án có thể dùng cho các giá trị hợp lệ khác nhau.

Ví dụ kế hoạch minh họa:

~~~text
Seq Scan on jobs
  Filter: (state = $1)
~~~

Một plan dùng `$1` có thể tái sử dụng khi gọi:

~~~sql
EXECUTE find_by_state('rare');
EXECUTE find_by_state('common');
~~~

### 6.1. Ưu điểm của generic plan

- Tránh chi phí optimizer lập plan mới ở những lần chạy sau khi plan có thể tái sử dụng.
- Tốt với statement ngắn, chạy rất nhiều lần, nơi planning time là tỷ lệ đáng kể.
- Có thể ổn định khi số hàng/đường truy cập tương tự cho nhiều giá trị tham số.
- Có ích khi phân bố dữ liệu khá đồng đều và generic plan có chất lượng gần các custom plan.

### 6.2. Hạn chế của generic plan

- Không thể tối ưu toàn bộ query dựa trên một giá trị cụ thể nếu giá trị đó chỉ có lúc execute.
- Có thể đánh giá selectivity theo số liệu tổng quát, không tận dụng sự lệch tần suất của từng giá trị.
- Có thể không chứng minh được điều kiện cần để dùng một số partial indexes.
- Có thể chọn join order, scan type hoặc sort strategy kém với nhóm tham số hiếm.
- Một plan tốt cho giá trị phổ biến chưa chắc tốt cho tenant rất lớn hoặc rất nhỏ.

**Generic plan không mặc định chậm.** Vấn đề xuất hiện khi **một dạng kế hoạch chung** không tương thích với các giá trị tham số khác nhau về chi phí thực tế.

## 7. Custom plan là gì?

Một **custom plan** được lập khi PostgreSQL đã biết **giá trị tham số của lần thực thi đang xét**.

Ví dụ cùng statement:

~~~sql
EXECUTE find_by_state('rare');
EXECUTE find_by_state('common');
~~~

Nếu custom plan được dùng, optimizer có thể xét:

~~~text
Lần 1: state='rare'
  -> ước lượng ít hàng
  -> có thể chọn Index Scan

Lần 2: state='common'
  -> ước lượng rất nhiều hàng
  -> có thể chọn Seq Scan
~~~

Đây là ví dụ lý thuyết; plan thực tế phụ thuộc dữ liệu, index và thống kê.

### 7.1. Ưu điểm của custom plan

- Có thể tận dụng **giá trị tham số thật** để ước lượng selectivity cụ thể.
- Phù hợp dữ liệu lệch phân bố hoặc các filter có tính chọn lọc rất khác nhau.
- Có thể lựa chọn index/partial index và join strategy thích hợp với từng bộ tham số.
- Có thể có lợi với truy vấn tương đối đắt, nơi giảm execution time bù được chi phí planning.

### 7.2. Đánh đổi

- Lập kế hoạch cho nhiều lần thực thi, tốn CPU và latency planning.
- Nếu một statement chạy hàng trăm nghìn lần/giây nhưng query thực thi rất ngắn, planning lặp lại có thể là chi phí đáng kể.
- Không bảo đảm plan luôn tốt: optimizer vẫn dựa trên thống kê/ước lượng và có thể chọn sai dù biết giá trị.

**Custom plan = plan có xét tham số hiện tại, không phải bảo đảm plan tối ưu tuyệt đối.**

## 8. So sánh generic và custom

| Đặc điểm | Generic plan | Custom plan |
|---|---|---|
| Biết giá trị tham số cụ thể khi lập plan | Không | Có |
| Có thể tái sử dụng plan cho giá trị khác | Có | Không theo cùng cơ chế |
| Planning lặp lại mỗi lần | Thường thấp hơn sau khi cache | Thường cao hơn |
| Nhạy với phân bố skew | Dễ không tối ưu cho một số giá trị | Có thể tối ưu theo giá trị |
| Tận dụng partial index phụ thuộc tham số | Bị hạn chế nếu không chứng minh predicate | Có thể, khi giá trị đáp ứng predicate |
| Plan cho tham số phổ biến/hiếm | Cùng cấu trúc chung khi chưa invalidated | Có thể khác |
| Một statement cực ngắn chạy nhiều lần | Có thể có lợi | Planning overhead có thể đáng kể |
| Một query scan/join lớn có tham số nhạy | Có thể kém | Thường đáng thử |
| Công cụ kiểm tra | `EXPLAIN EXECUTE`, `pg_prepared_statements` | Tương tự |
| Điều khiển phục vụ thí nghiệm | `force_generic_plan` | `force_custom_plan` |

Bảng này là so sánh cơ chế, không phải lời khẳng định generic luôn tiết kiệm tổng thời gian hoặc custom luôn đọc ít hàng.

## 9. PostgreSQL tự chọn generic hay custom như thế nào?

Mặc định, PostgreSQL dùng:

~~~sql
SHOW plan_cache_mode;
~~~

Thông thường kết quả là:

~~~text
auto
~~~

Với **prepared statement có tham số** và `plan_cache_mode=auto`, PostgreSQL dùng một heuristic được mô tả trong tài liệu:

1. Ban đầu dùng **custom plans cho năm lần thực thi đầu**.
2. Tính **chi phí ước lượng trung bình** của những custom plans đó.
3. Xem xét chi phí ước lượng của một **generic plan**.
4. Nếu dùng generic được đánh giá không đắt hơn đáng kể so với custom trung bình, xét đến lợi ích tránh planning lặp lại, server có thể chọn generic cho các lần sau.
5. Nếu generic bị đánh giá quá đắt, server có thể **tiếp tục dùng custom plans**.

Các chi tiết chi phí là logic optimizer, không phải lấy đúng năm con số thời gian từ đồng hồ người dùng rồi so với nhau.

### 9.1. “Sau năm lần luôn thành generic” là sai

**Năm lần đầu là giai đoạn để server đánh giá**, không phải lời hứa “lần thứ sáu chắc chắn dùng generic”.

Nếu generic plan dự kiến tệ hơn nhiều so với custom, PostgreSQL có thể tiếp tục custom.

### 9.2. Statement không có tham số

Với statement được chuẩn bị **không có tham số**, custom theo giá trị tham số không có ý nghĩa. PostgreSQL thường dùng kế hoạch generic cho trường hợp đó.

### 9.3. Heuristic là trên từng prepared statement

Một connection có thể có hai prepared statements:

- Statement A: generic phù hợp.
- Statement B: custom hiệu quả hơn.

Không có quy tắc “cả session chọn generic” ở chế độ `auto` cho mọi truy vấn.

## 10. Điều khiển bằng plan_cache_mode

PostgreSQL cung cấp ba giá trị:

| Giá trị | Ý nghĩa |
|---|---|
| `auto` | Để PostgreSQL áp dụng heuristic mặc định |
| `force_custom_plan` | Buộc sử dụng custom plan khi cơ chế prepared plan áp dụng |
| `force_generic_plan` | Buộc sử dụng generic plan khi có thể |
 
Xem giá trị:

~~~sql
SHOW plan_cache_mode;
~~~

Đặt cho session hiện tại:

~~~sql
SET plan_cache_mode = force_custom_plan;

-- Chạy EXPLAIN EXECUTE hoặc EXECUTE của prepared statement.

RESET plan_cache_mode;
~~~

Hoặc:

~~~sql
SET plan_cache_mode = force_generic_plan;

-- So sánh kế hoạch.

RESET plan_cache_mode;
~~~

**Quan trọng:** PostgreSQL xét `plan_cache_mode` khi **thực thi** một cached statement, không bắt buộc khóa lựa chọn này tại thời điểm `PREPARE`. Vì vậy có thể chuẩn bị một statement rồi đổi mode để so sánh cùng SQL.

### 10.1. Thử nghiệm trong phạm vi transaction bằng SET LOCAL

~~~sql
BEGIN;

SET LOCAL plan_cache_mode = force_custom_plan;

-- EXPLAIN EXECUTE prepared_statement(...);

ROLLBACK;
~~~

`SET LOCAL` có hiệu lực trong transaction hiện tại và tự hết khi transaction kết thúc. Đây là cách hữu ích để giảm nguy cơ bỏ quên một cấu hình thử nghiệm trong session lâu dài.

### 10.2. Không ép mode toàn server theo phản xạ

`force_custom_plan` cho mọi query có thể tăng planning CPU trên toàn workload. `force_generic_plan` cho mọi query có thể làm một số query nhạy tham số chậm đi rất nhiều.

Ưu tiên điều tra từng statement và từng đường truy cập trước khi đặt mode global hoặc trong connection pool dùng chung.

## 11. Lab: tạo bảng có phân bố dữ liệu lệch

Chúng ta xây bộ dữ liệu thực hành khiến cùng một query có hai độ chọn lọc rất khác nhau.

**Chỉ chạy trong database lab**, không trên production. Các lệnh tạo mới schema/bảng nên thực hiện khi tên chưa tồn tại.

~~~sql
CREATE SCHEMA plan_lab;

CREATE TABLE plan_lab.jobs (
    job_id BIGINT PRIMARY KEY,
    state TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    payload TEXT NOT NULL
);

INSERT INTO plan_lab.jobs (
    job_id, state, created_at, payload
)
SELECT
    g::BIGINT,
    CASE
        WHEN g % 1000 = 0 THEN 'rare'
        ELSE 'common'
    END,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + g * INTERVAL '1 second',
    repeat('x', 120) || g::TEXT
FROM generate_series(1, 200000) AS g;

CREATE INDEX idx_jobs_state
ON plan_lab.jobs(state);

ANALYZE plan_lab.jobs;
~~~

Bảng có:

- 200.000 hàng.
- Khoảng 199.800 hàng `state='common'`.
- Khoảng 200 hàng `state='rare'`.
- Index B-tree trên `state`.
- Cột `payload` không có trong index, nhằm làm việc đọc nhiều hàng có chi phí heap thực tế.

Kiểm tra:

~~~sql
SELECT
    state,
    COUNT(*) AS row_count
FROM plan_lab.jobs
GROUP BY state
ORDER BY state;
~~~

Kết quả kỳ vọng:

| state | row_count |
|---|---:|
| common | 199800 |
| rare | 200 |

### 11.1. Vì sao payload có độ rộng nhất định?

Nếu query chỉ đọc một cột đã nằm trong index và mọi heap pages all-visible, PostgreSQL có thể dùng index-only scan rất hiệu quả. Ta cố ý thêm cột `payload` mà query phải lấy từ heap để dễ quan sát sự khác nhau giữa đọc hầu hết bảng và tìm một số ít hàng.

Dù vậy kết quả cụ thể còn phụ thuộc máy, cache, planner settings và PostgreSQL version. Không ép người học phải thấy đúng một loại scan trong mọi môi trường.

## 12. Trước hết xem hai query dùng literal

Đo với giá trị hiếm:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT job_id, state, payload
FROM plan_lab.jobs
WHERE state = 'rare';
~~~

Đo với giá trị phổ biến:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT job_id, state, payload
FROM plan_lab.jobs
WHERE state = 'common';
~~~

Các quan sát hợp lý cần tìm:

- `'rare'` có ít hàng → planner **có thể** dùng Index Scan hoặc Bitmap Heap Scan.
- `'common'` có gần toàn bộ bảng → planner **có thể** chọn Seq Scan.
- `actual rows` khác nhau khoảng ba bậc độ lớn.
- Số buffer hit/read và execution time có thể khác.
- Ước lượng `rows` của planner có gần với thực tế không?

**Không đưa ra một execution plan cố định** vì PostgreSQL có thể chọn khác nhau tùy môi trường và thống kê.

### 12.1. EXPLAIN ANALYZE thực thi query

`EXPLAIN (ANALYZE, BUFFERS)` chạy câu SELECT thực sự để đo. Nó có thể sử dụng CPU/I/O đáng kể với bảng lớn, dù không in toàn bộ rows cho client.

Trong lab 200.000 hàng, điều đó thường chấp nhận được. Trên production phải cân nhắc tải và timeout trước khi bật ANALYZE cho câu SQL nặng.

## 13. PREPARE câu lookup để so generic/custom

Chuẩn bị:

~~~sql
PREPARE job_lookup(text) AS
SELECT job_id, state, payload
FROM plan_lab.jobs
WHERE state = $1;
~~~

Lệnh này đặt tên statement `job_lookup` trong session hiện tại.

Thử custom:

~~~sql
SET plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE job_lookup('rare');

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE job_lookup('common');
~~~

Cùng một prepared statement, hai lần `EXECUTE` có thể cho **hai plan khác nhau** nếu planner thấy điều đó có lợi.

Ví dụ các đoạn node có thể gặp (chỉ minh họa, không phải output bắt buộc):

~~~text
-- Giá trị hiếm:
Index Scan using idx_jobs_state on jobs
  Index Cond: (state = 'rare'::text)
~~~

~~~text
-- Giá trị phổ biến:
Seq Scan on jobs
  Filter: (state = 'common'::text)
~~~

Điểm cần nhớ không phải tên node, mà là custom planner đã biết giá trị tham số của **lần chạy cụ thể**.

## 14. Buộc generic plan và so lại

Không cần tạo lại prepared statement. Chỉ đổi mode:

~~~sql
SET plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE job_lookup('rare');

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE job_lookup('common');
~~~

Ở chế độ generic, plan tree thường là cùng một cấu trúc cho các giá trị khác nhau, ví dụ có:

~~~text
Seq Scan on jobs
  Filter: (state = $1)
~~~

hoặc một loại index access có điều kiện dạng `state = $1`.

Nếu generic chọn Seq Scan, giá trị `'rare'` có thể bị thiệt đáng kể vì phải đi qua cả bảng để lấy 200 hàng.

Nếu generic chọn Index Scan, giá trị `'common'` có thể phải thực hiện nhiều heap accesses và kém hơn một Seq Scan.

Đây là bài toán **parameter-sensitive plan**: một plan dùng chung có thể không phù hợp mọi giá trị.

Cuối thí nghiệm, trả lại mặc định:

~~~sql
RESET plan_cache_mode;
~~~

Không để lại `force_generic_plan` hoặc `force_custom_plan` trong session ứng dụng chỉ vì đã đo xong.

## 15. Đọc EXPLAIN EXECUTE để phân biệt plan

Trong PostgreSQL, khi trình bày plan của `EXPLAIN EXECUTE`:

- Với **custom plan**, điều kiện thường hiển thị **giá trị cụ thể** đã được bind, ví dụ `state = 'rare'::text`.
- Với **generic plan**, điều kiện thường vẫn hiển thị **placeholder** như `state = $1`.

Ví dụ minh họa:

~~~text
Custom:
  Index Cond: (state = 'rare'::text)

Generic:
  Filter: (state = $1)
~~~

Đây là một cách nhận diện hữu ích. Nhưng cần xem **toàn bộ plan**, không suy từ việc có/không thấy một literal trong một node không liên quan.

### 15.1. EXPLAIN EXECUTE không giống EXPLAIN SELECT literal

~~~sql
EXPLAIN SELECT ... WHERE state = 'rare';
~~~

cho planner giá trị literal ngay từ đầu.

~~~sql
EXPLAIN EXECUTE job_lookup('rare');
~~~

yêu cầu xem kế hoạch **thực tế PostgreSQL chọn cho prepared statement**, có thể là generic hoặc custom.

Nếu điều tra một sự cố chỉ xảy ra ở prepared statement nhưng chỉ EXPLAIN query literal, bạn có thể đang đo **một tình huống khác**.

### 15.2. Chỉ nhìn Execution Time là chưa đủ

Khi so sánh:

- `Planning Time`.
- `Execution Time`.
- `actual rows`/`estimated rows`.
- `Buffers: shared hit/read`.
- Loại scan, join, sort/aggregate.
- `Rows Removed by Filter`.
- Số lần thực thi và p95/p99 latency trong ứng dụng.

Generic có thể giảm planning time nhưng làm execution time tăng. Custom có thể tốn planning hơn nhưng rẻ hơn rất nhiều khi chạy query cho tham số hiếm.

**Tối ưu tổng thời gian và tài nguyên**, không tối ưu riêng chỉ số planning.

## 16. Chế độ auto: cách thử heuristic mặc định

Sau khi `RESET plan_cache_mode`, một prepared statement mới có thể cho thấy lựa chọn sau những lần chạy đầu.

Ví dụ một query trả một giá trị tổng hợp để không in hàng trăm nghìn rows:

~~~sql
PREPARE job_payload_size(text) AS
SELECT SUM(length(payload)) AS total_chars
FROM plan_lab.jobs
WHERE state = $1;
~~~

Chạy nhiều lần với cùng tham số phổ biến:

~~~sql
SET plan_cache_mode = auto;

EXECUTE job_payload_size('common');
EXECUTE job_payload_size('common');
EXECUTE job_payload_size('common');
EXECUTE job_payload_size('common');
EXECUTE job_payload_size('common');

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE job_payload_size('rare');
~~~

Khi thử trên bảng lệch phân bố:

- Nếu các lần đầu chủ yếu là `'common'`, custom plans ban đầu có thể có chi phí quét toàn bảng.
- Generic plan dựa trên selectivity trung bình có thể được coi là hợp lý so với những lần custom đó.
- Một lần sau với `'rare'` có thể gặp generic plan chưa phù hợp.

Đây là tình huống minh họa cho **lựa chọn phụ thuộc lịch sử thực thi**. Không bảo đảm PostgreSQL nhất định chuyển sang generic sau năm lần, vì quyết định dựa trên **ước lượng chi phí của từng statement**.

### 16.1. Vì sao thứ tự tham số có thể quan trọng?

Các custom plan đầu tiên đóng góp vào chi phí ước lượng trung bình dùng cho heuristic. Nếu các giá trị đầu tiên khác phân bố tham số sử dụng về sau, generic có thể được đánh giá theo một “mẫu lịch sử” không đại diện.

Trong vận hành:

~~~text
Ứng dụng mới khởi động
  |
  +--> 5 lần đầu với tenant rất lớn
  |
  +--> Server có thể thiên về generic
  |
  +--> Nhiều lần sau với tenant nhỏ
         |
         +--> query có nguy cơ kém hiệu quả
~~~

Tuy nhiên đây là rủi ro cần **đo và xác minh**, không phải mọi prepared statement đều gặp.

## 17. Quan sát prepared statements trong session

PostgreSQL có system view:

~~~sql
SELECT
    name,
    statement,
    parameter_types,
    from_sql,
    generic_plans,
    custom_plans
FROM pg_prepared_statements
ORDER BY name;
~~~

Các trường đáng chú ý:

| Trường | Ý nghĩa |
|---|---|
| `name` | Tên prepared statement |
| `statement` | Nội dung SQL liên quan |
| `parameter_types` | Danh sách kiểu tham số |
| `from_sql` | Có được tạo từ SQL `PREPARE` hay không |
| `generic_plans` | Số lần generic plan được chọn |
| `custom_plans` | Số lần custom plan được chọn |

Ví dụ lọc:

~~~sql
SELECT
    name,
    generic_plans,
    custom_plans
FROM pg_prepared_statements
WHERE name IN ('job_lookup', 'job_payload_size');
~~~

### 17.1. View chỉ cho session hiện tại

`pg_prepared_statements` phản ánh **prepared statements trong session hiện tại**, không phải một danh sách tất cả prepared statements của mọi session ở cả PostgreSQL instance.

Nếu bạn dùng một connection mới trong pgAdmin, view đó không thể tự nhìn thấy những named prepared statements đã được tạo ở connection JDBC khác.

Đây là nguyên nhân rất thường gặp khi DBA chạy query từ một terminal khác và kết luận “ứng dụng không có prepared statements”.

### 17.2. Counter không phải số hàng hay số request HTTP

`generic_plans` và `custom_plans` mô tả số lần loại plan được chọn cho prepared statement trong session. Chúng không phải số hàng trả về, số lần client gọi API hay total execution time.

Với driver/pool có nhiều physical connections, cần quan sát trên kết nối liên quan hoặc dùng telemetry phù hợp, không gộp giá trị view của một session thành số liệu toàn cụm.

## 18. Phân biệt hai con số “5” trong PostgreSQL và JDBC

Có hai cơ chế đôi khi cùng sử dụng giá trị mặc định gần **5**, nhưng **khác tầng**.

### 18.1. PostgreSQL server: giai đoạn 5 custom plans ban đầu

Ở `plan_cache_mode=auto`, với prepared statement có tham số, server dùng custom plans ban đầu để có cơ sở so sánh chi phí với generic plan.

Đây là **heuristic chọn plan** của PostgreSQL server.

### 18.2. PostgreSQL JDBC: prepareThreshold của driver

Với pgJDBC, tùy cấu hình và phiên bản, `prepareThreshold` điều khiển khi driver chuyển một lệnh được thực thi lặp lại sang sử dụng **server-side prepared statement có tên** theo cơ chế của driver. Giá trị mặc định thường là **5**.

Đây là **quyết định của driver về cách sử dụng protocol/server prepare**, không phải quyết định generic/custom của planner.

### 18.3. Hai ngưỡng có thể xảy ra nối tiếp

Sơ đồ khái niệm:

~~~text
Java PreparedStatement được tạo
          |
          v
Driver thực thi lặp lại
          |
          v
Tùy prepareThreshold và cache:
driver có thể dùng named server-side prepared statement
          |
          v
PostgreSQL nhận executions của prepared statement
          |
          v
Ở plan_cache_mode=auto:
server cân nhắc custom và generic theo heuristic
~~~

Không cộng cứng thành “10 request” hay “25 request” để dự báo chính xác lúc generic xuất hiện. Số lần ở hai tầng còn phụ thuộc driver, cache, lifecycle của statement, connection, kiểu thực thi và phiên bản.

**Cách chắc chắn:** xác minh cấu hình driver và quan sát server thực tế, thay vì suy từ con số mặc định.

## 19. PostgreSQL JDBC PreparedStatement có nghĩa gì?

Ví dụ Java:

~~~java
String sql = """
    SELECT job_id, state
    FROM plan_lab.jobs
    WHERE state = ?
    ORDER BY job_id
    LIMIT ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "rare");
    ps.setInt(2, 20);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long jobId = rs.getLong("job_id");
            String state = rs.getString("state");
        }
    }
}
~~~

Đây là mã dùng **JDBC API** với placeholder `?`. Driver chuyển tham số theo cơ chế protocol thích hợp; phía SQL server thường dùng biểu diễn tương đương `$1`, `$2`.

### 19.1. PreparedStatement không cho phép truyền tên cột tùy ý bằng ?

Ví dụ sai ý nghĩa:

~~~java
// Không thay tên cột SQL bằng tham số giá trị:
String sql = "SELECT job_id FROM plan_lab.jobs ORDER BY ?";
~~~

`?` là một **giá trị**, không phải identifier để động thay `job_id` hoặc `created_at`. Muốn hỗ trợ sort khác nhau, ứng dụng nên whitelist các template SQL an toàn.

### 19.2. Bảo vệ injection và cải thiện hiệu năng là hai mục tiêu riêng

Prepared statements với bind parameters thường giúp giảm nguy cơ **SQL injection qua dữ liệu đầu vào**, vì giá trị không bị nối thành cú pháp SQL.

Nhưng:

- Sử dụng bind parameter không bảo đảm server luôn dùng generic.
- Generic không bảo đảm nhanh.
- Dynamic SQL vẫn cần whitelist identifiers/ORDER BY.
- Những câu query có logic sai hoặc thiếu authorization vẫn sai dù dùng PreparedStatement.

Bảo mật và performance cần được đánh giá riêng.

## 20. Lab Java/JDBC: chạy lặp trên cùng connection

Để quan sát ý nghĩa của prepare threshold, ta dùng cùng một `Connection` và cùng một `PreparedStatement` chạy nhiều lần.

Ví dụ Java 17+, giả định đã có `DataSource`:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class JobQueryDemo {
    private final DataSource dataSource;

    public JobQueryDemo(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void run() throws SQLException {
        String sql = """
            SELECT job_id, state
            FROM plan_lab.jobs
            WHERE state = ?
            ORDER BY job_id
            LIMIT 10
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                 connection.prepareStatement(sql)) {

            for (int execution = 1; execution <= 8; execution++) {
                String state =
                    (execution % 2 == 0) ? "rare" : "common";

                statement.setString(1, state);

                try (ResultSet rs = statement.executeQuery()) {
                    while (rs.next()) {
                        long jobId = rs.getLong("job_id");
                        String returnedState = rs.getString("state");

                        // Minh họa đọc kết quả; ghi log nếu cần
                        // nhưng không in mỗi row trong benchmark.
                    }
                }
            }
        }
    }
}
~~~

Ví dụ giúp thấy cách một PreparedStatement được thực thi nhiều lần mà không ghép SQL string từ input.

### 20.1. Vì sao phải giữ cùng physical connection?

Server-side prepared statements được giữ theo **session**. Nếu mỗi lượt vòng lặp lại lấy một physical connection khác, bạn có thể không đạt chuỗi thực thi liên tục trên cùng server statement.

Một connection pool có thể giữ connection vật lý, nhưng pool không tự làm tất cả session chia sẻ một plan cache.

### 20.2. Query trong Java không phải benchmark skew tốt nhất

Ví dụ Java có `LIMIT 10` và `ORDER BY job_id` để tránh trả lượng dữ liệu lớn. Vì thế plan của nó có thể khác query `SELECT job_id,state,payload WHERE state=$1` trong lab SQL.

Không lấy kết quả latency của ví dụ Java này để kết luận hiệu quả custom/generic của một query khác. Muốn so sánh cần cùng cấu trúc SQL, dữ liệu và tham số.

## 21. prepareThreshold=0 có nghĩa gì?

Trong pgJDBC, tùy chế độ driver, đặt `prepareThreshold=0` được dùng để **vô hiệu hóa việc chuyển sang named server-side prepared statements** theo cơ chế threshold.

Điều đó **không tự đồng nghĩa**:

- Không còn dùng `PreparedStatement` API.
- Mọi giá trị SQL bị nối thành chuỗi.
- Không còn bind parameters.
- Mọi query trở thành string concatenation.
- PostgreSQL phải dùng một loại plan duy nhất trong mọi tình huống.

Driver vẫn có thể dùng extended protocol/unnamed statements với parameters tùy chế độ.

Chỉ thay threshold sau khi đọc tài liệu pgJDBC đang dùng và đo cả planning, execution, network round trips, CPU và hành vi connection pool.

### 21.1. Tăng threshold cũng không tự làm generic nhanh hơn

Threshold điều khiển **lifecycle của server prepare phía driver**. Nó không thay đổi phân bố dữ liệu hay buộc một plan chung trở nên phù hợp cho mọi parameter value.

Đây là lý do không nên dùng driver setting như công cụ duy nhất để “chữa” mọi query generic plan chậm.

## 22. Prepared statements tồn tại theo connection

SQL-level `PREPARE` và named prepared statements của PostgreSQL gắn với **backend session/connection**.

Ví dụ:

~~~text
Connection A:
  PREPARE job_lookup(text) ...
  EXECUTE job_lookup('rare') -> thành công

Connection B:
  EXECUTE job_lookup('rare')
  -> có thể lỗi vì statement chưa được PREPARE ở session B
~~~

Một connection pool có thể có 20 connection vật lý. Mỗi connection có thể:

- Có tập prepared statements riêng.
- Có counter generic/custom riêng.
- Có lịch sử tham số khác nhau.
- Có plan cache state khác nhau.
- Gặp invalidation vào thời điểm khác nhau theo hoạt động.

### 22.1. Vì sao cùng endpoint có latency không đồng đều?

Một request tới endpoint có thể mượn connection đã chạy statement hàng trăm lần và chọn generic; request khác mượn connection mới với custom plans ở giai đoạn đầu.

Ngoài cache, latency còn phụ thuộc data cache, lock, CPU, network và tải server. Nhưng prepared statement lifecycle theo connection là một yếu tố nên kiểm tra.

### 22.2. Restart ứng dụng không đảm bảo xử lý tận gốc

Restart có thể làm mất session-level prepared statements và reset lịch sử chọn plan. Query tạm thời nhanh hơn khi quay lại custom stage, nhưng nếu generic plan sau đó lại được chọn thì vấn đề có thể tái diễn.

Không dùng restart connection pool như giải pháp chính nếu chưa tìm ra nguyên nhân selectivity/stats/plan cache.

## 23. Transaction pooling và PgBouncer

Ở kiểu **session pooling**, một client session thường gắn với server session trong vòng đời phù hợp, nên những đối tượng session-level có thể dễ quản lý hơn.

Ở kiểu **transaction pooling**, một client có thể được gán server connection khác giữa các transaction. Điều này làm các tính năng phụ thuộc session state cần được xử lý cẩn thận.

Với prepared statements:

- `PREPARE name AS ...` trong SQL tạo state ở **server session**, không tự chuyển sang backend khác.
- Các **protocol-level named prepared statements** có thể được một số phiên bản/configuration của pooler hỗ trợ và quản lý, nhưng cần cấu hình và thử nghiệm.
- Không suy từ việc pooler hỗ trợ protocol-level prepared statements rằng mọi lệnh SQL `PREPARE/EXECUTE/DEALLOCATE` đều có cùng bảo đảm.
- Các thiết lập session-level `SET plan_cache_mode` có thể không tồn tại qua ranh giới transaction khi transaction pooling chuyển backend.
- Một driver có thể cần setting tương thích với pooler và cách pooling thực tế.

### 23.1. Kiểm tra gì khi có pooler?

1. Pooler đang chạy session pooling hay transaction pooling?
2. Phiên bản có hỗ trợ những prepared protocol messages mà driver dùng không?
3. Cấu hình hỗ trợ named prepared statements có được bật không?
4. Driver dùng threshold/cache ra sao?
5. Một câu PREPARE SQL có được kỳ vọng tồn tại giữa các transaction không?
6. Khi backend bị thay đổi, statement có được tạo lại theo protocol hay có lỗi “prepared statement does not exist”?
7. Có dùng `SET LOCAL` trong một transaction thay vì `SET` session-level khi cần test mode không?

Không khuyên tắt prepared statements toàn ứng dụng trước khi xác minh pooler mode và khả năng tương thích.

## 24. Statistics quyết định chất lượng plan

Custom và generic đều dựa trên PostgreSQL statistics. Những thống kê quan trọng gồm:

- `reltuples` và `relpages` ở relation catalog.
- Phân bố giá trị phổ biến (`most_common_vals`).
- Tần suất các giá trị phổ biến (`most_common_freqs`).
- Số lượng giá trị phân biệt (`n_distinct`).
- Histogram bounds cho một số loại dữ liệu.
- `null_frac`.
- Extended statistics khi có tương quan nhiều cột.

Quan sát thống kê cột `state`:

~~~sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'plan_lab'
  AND tablename = 'jobs'
  AND attname = 'state';
~~~

Trong lab, vì `common` xuất hiện rất nhiều, thống kê MCV thường phản ánh độ lệch này.

### 24.1. ANALYZE giúp gì?

~~~sql
ANALYZE plan_lab.jobs;
~~~

`ANALYZE` cập nhật thống kê giúp planner ước lượng phân bố dữ liệu. Nếu thống kê cũ và dữ liệu đã thay đổi đáng kể, cả generic và custom đều có thể chọn sai.

Đừng ép custom plan khi nguyên nhân thật sự là histogram/MCV cũ mà chưa đo lại sau ANALYZE.

### 24.2. Custom vẫn cần thống kê đủ tốt

Dù biết `state='rare'`, nếu stats không nhận biết độ hiếm hoặc phân bố đã thay đổi lớn, planner vẫn có thể đánh giá sai số hàng và chọn kế hoạch kém.

Knowledge of parameter value không tương đương accurate cardinality estimation.

## 25. Generic plan xử lý selectivity của parameter thế nào?

Với literal:

~~~sql
WHERE state = 'rare'
~~~

planner có thể nhìn MCV và biết `rare` xuất hiện khoảng 0,1% trong dữ liệu lab.

Với generic plan của:

~~~sql
WHERE state = $1
~~~

planner không thể chắc `$1` tương ứng giá trị phổ biến hay hiếm. Nó phải áp dụng cách ước lượng tổng quát dựa trên thống kê và quy tắc selectivity.

Khi có một giá trị chiếm phần lớn dữ liệu và các giá trị còn lại rất hiếm, một ước lượng cho **tham số chưa biết** có thể kém đại diện cho hai trường hợp cực đoan.

Điều này có thể dẫn tới:

- Sai ước lượng số hàng.
- Chọn scan loại khác với custom.
- Chọn join algorithm không phù hợp.
- Cấp phát bộ nhớ hoặc sort/hash kém hiệu quả theo kích thước dữ liệu thật.
- Lệch p95/p99 latency khi một số tenant hoặc trạng thái rất khác nhóm còn lại.

Không thể giải quyết bằng cách chỉ thêm một index mà không kiểm tra shape của query, stats và lựa chọn generic/custom.

## 26. Partial index và tham số: bẫy rất thường gặp

Giả sử hệ thống thường truy vấn riêng những job `state='rare'`:

~~~sql
CREATE INDEX idx_jobs_rare
ON plan_lab.jobs(job_id)
WHERE state = 'rare';
~~~

Index này chỉ chứa những hàng thỏa predicate `state='rare'`.

Một query literal:

~~~sql
EXPLAIN
SELECT job_id
FROM plan_lab.jobs
WHERE state = 'rare';
~~~

có thể sử dụng partial index nếu planner đánh giá có lợi.

Nhưng query chuẩn bị:

~~~sql
PREPARE lookup_any_state(text) AS
SELECT job_id
FROM plan_lab.jobs
WHERE state = $1;
~~~

với **generic plan** không thể khẳng định:

~~~text
$1 luôn bằng 'rare'
~~~

Vì vậy generic planner thường **không thể dùng partial index chỉ dành cho `state='rare'`** làm đường truy cập hợp lệ cho mọi giá trị `$1`.

### 26.1. Custom plan có thể khác

Khi `$1='rare'` được biết lúc lập custom plan, optimizer có thể chứng minh predicate của query phù hợp partial index và cân nhắc dùng nó.

Trong lab:

~~~sql
SET plan_cache_mode = force_custom_plan;

EXPLAIN EXECUTE lookup_any_state('rare');

SET plan_cache_mode = force_generic_plan;

EXPLAIN EXECUTE lookup_any_state('rare');

RESET plan_cache_mode;
~~~

So sánh `Index Scan`/`Index Only Scan` và tên index thực tế. Việc custom *được phép* dùng partial index không bảo đảm nó *bắt buộc* chọn index đó; planner vẫn tối ưu theo cost.

### 26.2. Khi nào nên tách câu SQL?

Nếu endpoint **chỉ cần `state='rare'`** và giá trị là điều kiện cố định được server xác định, có thể viết query với literal an toàn:

~~~sql
SELECT job_id
FROM plan_lab.jobs
WHERE state = 'rare';
~~~

Nếu endpoint nhận state tùy ý, phải cân nhắc trade-off của prepared statement và partial index.

Không ghép một giá trị tùy ý từ người dùng vào SQL để “ép dùng partial index”. Dùng parameter binding cho input chưa tin cậy.

## 27. Optional filters: một câu SQL cho tất cả có thể bất lợi

Một mẫu API phổ biến:

~~~sql
WHERE ($1 IS NULL OR state = $1)
~~~

Nó diễn đạt:

- Nếu tham số NULL → không lọc state.
- Nếu tham số có giá trị → lọc state.

Ví dụ:

~~~sql
PREPARE list_jobs(text) AS
SELECT job_id, state, payload
FROM plan_lab.jobs
WHERE ($1 IS NULL OR state = $1);
~~~

Ở custom plan:

- Nếu `$1=NULL`, optimizer có thể đơn giản hóa một số biểu thức.
- Nếu `$1='rare'`, optimizer có thể cân nhắc index theo state.

Ở generic plan, optimizer phải giữ khả năng xử lý **cả hai trạng thái**, nên nhiều lúc chọn một plan chung không tốt cho request hiếm.

### 27.1. Hai query template thường rõ hơn

Thay vì một câu SQL xử lý hai workload rất khác nhau:

~~~sql
-- Không có filter:
SELECT job_id, state, payload
FROM plan_lab.jobs;
~~~

~~~sql
-- Có filter:
SELECT job_id, state, payload
FROM plan_lab.jobs
WHERE state = $1;
~~~

Ứng dụng chọn một trong **hai template cố định** theo việc filter có hay không. Giá trị state vẫn được bind an toàn.

Điều này giúp planner có cấu trúc truy vấn rõ hơn và có thể cải thiện khả năng dùng index. Không phải mọi optional filter đều cần tách thành hai query; quyết định dựa trên tần suất, số tổ hợp filters và kế hoạch thực tế.

## 28. Tenant skew: cùng SQL nhưng tenant rất khác nhau

Một ví dụ thực tế:

~~~text
tenant_id = 1       -> 30 triệu hàng
tenant_id = 2       -> 100 hàng
tenant_id = 3       -> 5.000 hàng
tenant_id = 4       -> 200.000 hàng
~~~

Ứng dụng dùng:

~~~sql
SELECT ...
FROM events
WHERE tenant_id = $1
ORDER BY created_at DESC
LIMIT 100;
~~~

Có thể có index:

~~~sql
CREATE INDEX idx_events_tenant_created
ON events(tenant_id, created_at DESC);
~~~

Index này thường hữu ích, nhưng query có thể có JOIN, filter thêm hoặc lấy nhiều dữ liệu. Với tenant cực lớn và tenant cực nhỏ, số rows, join strategy và thứ tự truy cập có thể khác nhau nhiều.

Generic plan dùng chung có thể phù hợp tenant lớn nhưng lãng phí với tenant nhỏ, hoặc ngược lại.

### 28.1. Đừng lấy một tenant làm đại diện cho tất cả

Khi benchmark, chuẩn bị ít nhất:

- Một tenant nhỏ.
- Một tenant trung bình.
- Một tenant lớn.
- Một tenant có phân bố dữ liệu đặc biệt nếu có.

Đo cùng cấu trúc prepared SQL ở cả `force_custom_plan` và `force_generic_plan`. Một benchmark chỉ với tenant lớn chưa đủ để biết p99 của tenant nhỏ.

## 29. Query có nhiều JOIN: khác biệt có thể lớn hơn một Index Scan

Giả sử:

~~~sql
PREPARE tenant_report(bigint) AS
SELECT
    o.order_id,
    c.customer_name,
    o.total_amount
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
WHERE o.tenant_id = $1;
~~~

Nếu tenant 1 có hàng triệu orders và tenant 2 chỉ có 100 orders, phương án tối ưu có thể khác:

- Tenant nhỏ: nested loop + index lookups có thể hợp lý.
- Tenant lớn: hash join hoặc chiến lược scan/join khác có thể tốt hơn.
- Sort, aggregation và parallelism cũng có thể bị ảnh hưởng.

Một generic plan không biết tenant nào sẽ chạy khi planning, nên khó đạt tối ưu tốt cho mọi quy mô.

**Ví dụ chỉ là schema giả định**, không chạy trực tiếp trên `plan_lab.jobs`. Hãy áp dụng quy trình đo trên bảng thật của ứng dụng khi điều tra.

## 30. Prepared parameter và partition pruning

Trên bảng partitioned theo thời gian hoặc tenant, một tham số có thể quyết định partition nào cần đọc.

Ví dụ khái niệm:

~~~sql
PREPARE find_events(timestamptz, timestamptz) AS
SELECT event_id, created_at
FROM partitioned_events
WHERE created_at >= $1
  AND created_at < $2;
~~~

Có hai giai đoạn pruning quan trọng:

- **Plan-time pruning:** planner biết đủ giá trị để loại bỏ partitions ngay lúc lập kế hoạch.
- **Execution-time pruning:** một số partitions có thể được loại khi tham số đã biết lúc thực thi, ngay cả khi plan ban đầu là generic.

### 30.1. Generic plan không đồng nghĩa quét mọi partition

PostgreSQL có hỗ trợ **runtime partition pruning** trong những tình huống phù hợp. Vì vậy generic plan với `$1`, `$2` không tự chứng minh rằng mọi partition đều được scan.

Trong `EXPLAIN (ANALYZE)` của các truy vấn partitioned, có thể thấy một số subplans bị loại hoặc không thực thi theo ngữ cảnh.

Cần xem plan thực tế, version, kiểu partitioning và biểu thức WHERE; không kết luận chỉ từ việc thấy placeholder.

### 30.2. Custom plan vẫn có thể lợi hơn

Nếu custom biết khoảng thời gian và số partitions từ planning, nó có thể loại nhiều phần sớm hơn và chọn những phương án cụ thể. Nhưng execution-time pruning có thể giảm khoảng cách hiệu năng cho generic trong nhiều workload.

Không coi câu “generic không dùng được partition pruning” là chân lý.

## 31. Parameter type cũng ảnh hưởng plan

Kiểu tham số ảnh hưởng đến operator và index compatibility.

Ví dụ:

~~~sql
PREPARE find_job_id(bigint) AS
SELECT job_id, state
FROM plan_lab.jobs
WHERE job_id = $1;
~~~

Đây là so sánh `BIGINT = BIGINT`, phù hợp kiểu primary key.

Nếu ứng dụng truyền text rồi phải cast dữ liệu cột:

~~~sql
-- Mẫu cần đánh giá cẩn thận:
WHERE job_id::TEXT = $1
~~~

việc ép kiểu **trên cột** có thể làm index B-tree trên `job_id` không hỗ trợ trực tiếp điều kiện equality như trước.

Thường tốt hơn là bind/cast tham số về đúng kiểu cột:

~~~sql
WHERE job_id = $1::BIGINT
~~~

### 31.1. Hãy khai báo kiểu tham số khi cần

~~~sql
PREPARE find_job_id(bigint) AS
SELECT job_id
FROM plan_lab.jobs
WHERE job_id = $1;
~~~

PostgreSQL có thể suy luận kiểu tham số từ ngữ cảnh khi không khai báo, nhưng trong các biểu thức mơ hồ như chỉ xét `$1 IS NULL`, việc thiếu kiểu có thể gây lỗi không xác định được datatype.

Trong JDBC, nên dùng setter phù hợp như `setLong`, `setBigDecimal`, `setObject` với kiểu tương thích.

### 31.2. Một statement text khác có thể tạo prepared statement khác

Với driver/cache, hai câu SQL dù logic tương tự nhưng khác cast, whitespace, selected columns hoặc cấu trúc filter có thể được quản lý như những statement khác nhau.

Không mặc định tất cả câu SELECT gần giống nhau chia sẻ cùng plan cache.

## 32. Generic plan có thể được lập lại khi nào?

Một generic plan không phải kế hoạch “đóng băng mãi mãi”.

PostgreSQL có cơ chế **invalidation/replanning** trong những trường hợp phù hợp, ví dụ:

- DDL thay đổi cấu trúc quan hệ được tham chiếu.
- Index/constraint liên quan thay đổi.
- Planner statistics của đối tượng liên quan được cập nhật.
- Một số thay đổi `search_path` có thể khiến statement được phân tích/lập kế hoạch lại.
- Session tạo lại prepared statement hoặc cache entries hết hiệu lực.

Câu `PREPARE` có thể tồn tại lâu nhưng plan cache bên trong nó được cập nhật khi cần.

### 32.1. DDL và prepared statement

Nếu một statement có:

~~~sql
SELECT * FROM some_table WHERE id = $1;
~~~

và ứng dụng thay schema của bảng, kiểu dữ liệu hoặc số cột, statement đã chuẩn bị có thể cần reparse/replan; trong một số trường hợp có thể báo lỗi nếu **kiểu kết quả trả về** thay đổi ngoài khả năng tái sử dụng prepared statement.

Do đó, trong hệ thống có migration thường xuyên, cần kiểm tra tương thích giữa prepared statements, thay đổi SELECT list và schema rollout.

### 32.2. Cập nhật statistics có thể đổi plan

Sau:

~~~sql
ANALYZE plan_lab.jobs;
~~~

một cached plan phụ thuộc thống kê có thể được lập lại và kết quả EXPLAIN thay đổi.

Điều này không có nghĩa mọi lần `ANALYZE` lập tức khiến tất cả session chạy cùng một plan giống nhau. Prepared statements nằm ở các session khác nhau, và quá trình chọn generic/custom vẫn có state tương ứng.

## 33. search_path và schema resolution

Prepared statement có thể tham chiếu tên bảng **không kèm schema**:

~~~sql
PREPARE find_jobs(text) AS
SELECT job_id
FROM jobs
WHERE state = $1;
~~~

Nếu `search_path` thay đổi, PostgreSQL có thể cần phân tích lại statement với ngữ cảnh tên bảng mới.

Đối với ứng dụng nhiều schema/tenant, việc dựa vào `search_path` động cần được thiết kế cẩn thận:

- Tránh tên bảng trùng không rõ nguồn.
- Không để role không tin cậy tự tạo object trong schema được tìm trước.
- Dùng tên đầy đủ như `plan_lab.jobs` khi thích hợp.
- Thử những thay đổi `search_path` dưới connection pooling.
- Không ghép schema name từ request chưa xác thực vào SQL.

### 33.1. Một thay đổi search_path không đơn giản là đổi dữ liệu tham số

`search_path` ảnh hưởng **cách resolve object names**. Đây là ngữ cảnh phân tích tên, khác với `$1` là giá trị dùng trong `WHERE`.

Vì vậy không được coi multi-schema routing qua `search_path` như một tham số hóa dữ liệu thông thường.

## 34. DEALLOCATE, DISCARD PLANS và lifecycle

Dọn một SQL-level prepared statement:

~~~sql
DEALLOCATE job_lookup;
~~~

Dọn mọi SQL-level prepared statements của session:

~~~sql
DEALLOCATE ALL;
~~~

PostgreSQL cũng có lệnh quản trị session cache:

~~~sql
DISCARD PLANS;
~~~

`DISCARD PLANS` giải phóng những cached query plans trong session, để có thể lập lại khi cần. Nó không phải lệnh “tối ưu planner”, và không nên được lạm dụng như công cụ thường xuyên cho mỗi request.

### 34.1. Vì sao không xóa cache liên tục để tránh generic?

Nếu xóa cache khiến statement luôn quay về custom/giai đoạn đầu, bạn đang đánh đổi bằng:

- Nhiều parse/plan work lặp lại.
- Cache misses.
- Phức tạp session lifecycle.
- Có thể làm mất những lợi ích prepared statements mang lại.

Nếu root cause là generic plan kém với skew, nên điều chỉnh đúng statement hoặc cấu trúc truy vấn dựa trên bằng chứng, không dựa vào một cơ chế reset toàn session.

### 34.2. DISCARD ALL khác DISCARD PLANS

`DISCARD ALL` reset nhiều loại session state khác, không chỉ plans. Không dùng trong ứng dụng hay pooler khi chưa hiểu tác động tới prepared statements, temporary objects, settings và session context.

## 35. Khi nào nên cố dùng custom plan?

Những dấu hiệu đáng điều tra:

- Cùng prepared statement có các giá trị tham số với số rows chênh nhau cực lớn.
- `EXPLAIN EXECUTE` generic chọn scan/join rất kém cho một giá trị hiếm.
- Custom plan cho giá trị đó nhanh hơn đáng kể.
- Partial index chỉ dùng được khi planner biết tham số cụ thể.
- p99 latency tăng sau khi statement đã được execute nhiều lần.
- Một endpoint chậm ở một nhóm tenant nhưng nhanh ở nhóm khác.
- Planning time nhỏ so với execution time được tiết kiệm.

Cách thử an toàn trong lab:

~~~sql
SET plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE job_lookup('rare');

RESET plan_cache_mode;
~~~

Nếu Custom hiệu quả hơn, các lựa chọn triển khai có thể gồm:

- Dùng `SET LOCAL plan_cache_mode = force_custom_plan` quanh query trong transaction phù hợp.
- Tách query templates cho những trường hợp rất khác nhau.
- Điều chỉnh index/thống kê để generic vẫn đủ tốt.
- Xem khả năng cấu hình ở tầng driver khi thật sự cần, sau khi đo.

Không tự động đổi `plan_cache_mode` cho toàn cluster chỉ vì một query chậm.

## 36. Khi nào generic plan là lựa chọn tốt?

Những dấu hiệu:

- Câu SQL chạy cực nhiều lần với một cấu trúc ổn định.
- Chi phí planning là phần đáng kể của tổng latency.
- Phân bố tham số tương đối đồng đều.
- Có index/đường truy cập hữu ích cho gần như mọi tham số.
- Generic và custom có execution time gần nhau trên các nhóm giá trị.
- Không có partial-index predicate phụ thuộc vào tham số cụ thể.
- Ít biến thiên join cardinality theo tenant/status.

Ví dụ một lookup bằng primary key:

~~~sql
PREPARE by_primary_key(bigint) AS
SELECT job_id, state
FROM plan_lab.jobs
WHERE job_id = $1;
~~~

Nếu PK luôn unique và cấu trúc lookup gần giống nhau cho mọi ID, generic plan thường có thể đạt hiệu quả rất gần custom. Khi ấy tránh planning lặp lại có thể là lợi ích đáng kể.

**Nhưng vẫn phải đo**: kiểu truy vấn, row visibility, index và cache có thể khác nhau trong hệ thống thực.

## 37. Query hint có giải quyết vấn đề này không?

PostgreSQL không có cú pháp hint mặc định phổ biến kiểu:

~~~text
USE INDEX(index_name)
FORCE PLAN(...)
~~~

trong SQL chuẩn của server để chỉ định mọi node execution plan.

Một số extension bên ngoài có thể cung cấp cơ chế hint, nhưng việc đó nằm ngoài khả năng PostgreSQL core mặc định.

Các công cụ chuẩn nên dùng trước:

1. Viết WHERE/JOIN đúng semantics.
2. Cập nhật thống kê với ANALYZE.
3. Tạo index thích hợp.
4. So sánh `plan_cache_mode` custom/generic.
5. Tách template khi optional filters tạo workload quá khác.
6. Đo bằng `EXPLAIN (ANALYZE, BUFFERS)`.

Không nên giải quyết bằng cách ép tắt `enable_seqscan` hoặc `enable_nestloop` trên production một cách toàn cục. Những GUC này hữu ích cho phân tích nhưng có thể làm hại các query khác và không phải hint hoàn hảo.

## 38. Quan sát planning trong pg_stat_statements

Với extension `pg_stat_statements` được cài đặt và cấu hình, có thể xem thống kê tập trung các câu SQL chuẩn hóa:

~~~sql
SELECT
    queryid,
    calls,
    plans,
    ROUND(total_plan_time::NUMERIC, 2) AS total_plan_ms,
    ROUND(mean_plan_time::NUMERIC, 4) AS mean_plan_ms,
    ROUND(mean_exec_time::NUMERIC, 4) AS mean_exec_ms
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Đây là mẫu truy vấn chỉ hoạt động khi extension đã được bật và server cung cấp những trường tương ứng.

### 38.1. track_planning có thể đang tắt

Việc thu thập planning stats của `pg_stat_statements` phụ thuộc cấu hình như:

~~~sql
SHOW pg_stat_statements.track_planning;
~~~

Nếu extension chưa được nạp/cấu hình, lệnh trên có thể lỗi hoặc không có thông tin mong muốn. Không tự kết luận “planning time bằng 0” nghĩa PostgreSQL không lập kế hoạch.

### 38.2. pg_stat_statements có cho biết generic hay custom không?

`pg_stat_statements` giúp xem số calls và planning/execution time tổng hợp, nhưng không cung cấp trực tiếp một cột “generic_plan=true/false cho request X”.

Cần kết hợp:

- `EXPLAIN EXECUTE` trong context chuẩn bị tương đương.
- `pg_prepared_statements` ở session liên quan.
- Telemetry ứng dụng theo parameter groups.
- Nhật ký/tracing được kiểm soát.
- `pg_stat_statements` để nhận biết statement có chi phí planning/execution bất thường.

### 38.3. Hạn chế về quyền và dữ liệu nhạy cảm

View/extension và log có thể chứa query text hoặc thông tin liên quan cấu trúc dữ liệu. Cấp quyền đọc phù hợp và tránh log tham số nhạy cảm.

Không bật logging mọi statement cùng bind values trên production chỉ để điều tra một query nếu điều đó tạo rủi ro dữ liệu hoặc chi phí lớn.

## 39. Cách benchmark đúng một prepared statement

Để so sánh có ý nghĩa, giữ cố định:

1. Cùng cấu trúc SQL.
2. Cùng database và phiên bản.
3. Cùng data snapshot (hoặc biến động được ghi nhận).
4. Cùng index và statistics.
5. Cùng cấu hình có liên quan ngoài `plan_cache_mode`.
6. Cùng connection/session hoặc setup tương đương.
7. Một tập giá trị tham số đại diện.
8. Nhiều lần đo, không kết luận từ một lần.
9. Đo cả planning và execution.
10. Theo dõi buffers/I/O, không chỉ elapsed time.

Ví dụ một protocol kiểm thử:

~~~sql
-- 1. Tạo dữ liệu và chuẩn bị statement một lần.
ANALYZE plan_lab.jobs;

PREPARE benchmark_job(text) AS
SELECT job_id, state, payload
FROM plan_lab.jobs
WHERE state = $1;

-- 2. So custom cho rare/common.
SET plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE benchmark_job('rare');

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE benchmark_job('common');

-- 3. So generic cho cùng bộ tham số.
SET plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE benchmark_job('rare');

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE benchmark_job('common');

-- 4. Hoàn nguyên.
RESET plan_cache_mode;

DEALLOCATE benchmark_job;
~~~

### 39.1. Đọc số liệu như thế nào?

Đặt cạnh nhau:

| Tham số | Mode | Scan/join | Est rows | Actual rows | Planning ms | Execution ms | Buffers |
|---|---|---|---:|---:|---:|---:|---|
| rare | custom | Ghi theo EXPLAIN | ... | ... | ... | ... | ... |
| rare | generic | Ghi theo EXPLAIN | ... | ... | ... | ... | ... |
| common | custom | Ghi theo EXPLAIN | ... | ... | ... | ... | ... |
| common | generic | Ghi theo EXPLAIN | ... | ... | ... | ... | ... |

Không điền trước số liệu tưởng tượng; người học phải ghi kết quả thật.

### 39.2. Thứ tự chạy có thể làm sai lệch benchmark

Nếu lần đầu phải đọc pages từ đĩa còn lần sau được cache, mode chạy sau có vẻ nhanh hơn dù plan không tối ưu hơn.

Hãy chạy nhiều vòng, đảo thứ tự, đối chiếu buffers và tách warm/cold cache khi cần. Trên production, ảnh hưởng concurrency và background I/O còn lớn hơn.

## 40. Tổng độ trễ: planning và execution

Có thể hình dung:

\[
T_{\mathrm{total}}
\approx T_{\mathrm{planning}} + T_{\mathrm{execution}} + T_{\mathrm{other}}
\]

Trong đó `T_other` có thể gồm network, chờ lock, client processing và các overhead khác.

Ví dụ **giả định**, không phải số đo PostgreSQL:

| Chiến lược | Planning | Execution | Tổng gần đúng |
|---|---:|---:|---:|
| Custom cho rare | 0,7 ms | 1,3 ms | 2,0 ms |
| Generic cho rare | 0,05 ms | 80 ms | 80,05 ms |
| Custom cho common | 0,7 ms | 40 ms | 40,7 ms |
| Generic cho common | 0,05 ms | 40 ms | 40,05 ms |

Nếu workload gồm nhiều `rare`, generic gây thiệt hại lớn dù tiết kiệm planning.

Nếu mọi giá trị có execution time gần như nhau và planning đáng kể, generic có thể tốt hơn.

Cần xem **tần suất thực tế của từng nhóm tham số**, không chỉ trung bình một lượt. Một endpoint có tổng throughput tốt nhưng p99 latency rất tệ cho nhóm tenant nhỏ vẫn có thể là vấn đề nghiêm trọng.

## 41. Generic plan và parameter sniffing

Một số cộng đồng cơ sở dữ liệu gọi hiện tượng plan phụ thuộc tham số là **parameter sniffing**. Khi thảo luận PostgreSQL, nên dùng thuật ngữ chính xác:

- **Custom plan:** optimizer sử dụng giá trị tham số ở lần chạy cụ thể.
- **Generic plan:** optimizer không dựa trên giá trị tham số cụ thể.
- **Auto heuristic:** PostgreSQL lựa chọn giữa hai cách dựa trên ước lượng chi phí và lịch sử lập plan.

Không áp dụng máy móc hướng dẫn về plan cache của SQL Server, Oracle hoặc một hệ quản trị khác cho PostgreSQL. Cú pháp, heuristic và khả năng invalidation khác nhau.

## 42. Prepared statements với PL/pgSQL

Ngoài SQL `PREPARE` và JDBC, PostgreSQL còn có các statement được cache nội bộ trong những cơ chế như PL/pgSQL.

Ví dụ một function:

~~~sql
CREATE OR REPLACE FUNCTION plan_lab.count_jobs(
    requested_state TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $function$
DECLARE
    total_jobs BIGINT;
BEGIN
    SELECT COUNT(*)
    INTO total_jobs
    FROM plan_lab.jobs
    WHERE state = requested_state;

    RETURN total_jobs;
END;
$function$;
~~~

Khi function chạy lặp lại, PL/pgSQL có thể sử dụng cơ chế caching/planning của SQL statements bên trong, với trade-off generic/custom tương tự trong những ngữ cảnh phù hợp.

### 42.1. Không kết luận function luôn replan hoặc luôn generic

Một câu static SQL trong PL/pgSQL có thể được cache và dùng cơ chế chuẩn bị tham số nội bộ, chứ không phải mọi function call đều parse/plan mọi statement từ đầu.

Nếu function chậm với một số tham số, `plan_cache_mode` và `EXPLAIN` trên query tương đương có thể hỗ trợ điều tra. Nhưng việc đo trực tiếp function, SQL trong function và phần thời gian PL/pgSQL cần được phân biệt.

### 42.2. Dynamic EXECUTE trong PL/pgSQL

PL/pgSQL có lệnh `EXECUTE dynamic_sql USING ...` riêng, khác SQL-level `EXECUTE prepared_name(...)`.

Ví dụ:

~~~sql
EXECUTE
    'SELECT COUNT(*) FROM plan_lab.jobs WHERE state = $1'
INTO total_jobs
USING requested_state;
~~~

Đây là fragment trong thân function PL/pgSQL, không chạy độc lập ở SQL prompt.

Dynamic `EXECUTE` trong PL/pgSQL thường lập kế hoạch cho câu SQL được xây dựng khi chạy, thay vì sử dụng plan cache static SQL theo cùng cách. Có thể hữu ích trong những tình huống cần parameter-specific planning, nhưng làm tăng planning overhead và cần dùng `USING`/`format`/whitelisting cẩn thận để tránh SQL injection.

Không chuyển mọi function sang dynamic SQL chỉ vì nghe nói “custom tốt hơn”.

## 43. DML cũng có thể là prepared statement

Một prepared statement không nhất thiết là SELECT.

Ví dụ:

~~~sql
PREPARE set_job_state(bigint, text) AS
UPDATE plan_lab.jobs
SET state = $2
WHERE job_id = $1;
~~~

Khi chạy:

~~~sql
BEGIN;

EXECUTE set_job_state(1000, 'common');

ROLLBACK;
~~~

Đây là thao tác UPDATE thật bên trong transaction lab, được rollback sau khi minh họa.

### 43.1. Generic/custom ảnh hưởng cả DML

Đối với UPDATE/DELETE/MERGE được hỗ trợ và có tham số, lựa chọn access plan vẫn có thể ảnh hưởng:

- Tìm hàng cần sửa.
- Scan/join source/target.
- Số rows bị đọc trước khi thay đổi.
- Lock và thời gian giữ transaction.
- Tài nguyên tiêu thụ.

Nhưng việc lập plan không thay thế CHECK/UNIQUE/FK, row locking và transaction semantics.

### 43.2. EXPLAIN ANALYZE DML là nguy hiểm

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE set_job_state(1000, 'rare');
~~~

nếu chạy ngoài transaction bảo vệ, sẽ **thực thi UPDATE** và có thể thay đổi dữ liệu. Trong môi trường học tập dùng transaction/ROLLBACK khi thích hợp; trên production không dùng tùy tiện.

## 44. Cách điều tra một sự cố “lần đầu nhanh, sau đó chậm”

Triệu chứng:

~~~text
Sau khởi động ứng dụng:
  một endpoint trả nhanh

Sau nhiều request:
  endpoint bắt đầu chậm ở một số tham số

Khởi động lại connection:
  nhanh một lúc rồi chậm trở lại
~~~

Điều này **có thể** gợi ý thay đổi generic/custom plan theo lifecycle prepared statement, nhưng không phải bằng chứng tự thân. Cache, thống kê, lock hoặc thay đổi dữ liệu cũng có thể tạo hiện tượng tương tự.

### 44.1. Quy trình kiểm tra

1. Xác định SQL thật của endpoint, gồm filter, JOIN, ORDER BY và LIMIT.
2. Xác định các nhóm tham số nhanh/chậm.
3. Kiểm tra pgJDBC prepareThreshold/driver mode nếu dùng Java.
4. Kiểm tra connection pooler và session lifecycle.
5. Xác minh server có sử dụng prepared statement tương ứng không.
6. So `EXPLAIN EXECUTE` dưới `force_custom_plan` và `force_generic_plan`.
7. Xem `pg_prepared_statements` trên session liên quan nếu có thể.
8. Đo selectivity, actual/estimated rows, index access, buffers.
9. Kiểm tra thống kê và thời điểm ANALYZE.
10. Chọn biện pháp phù hợp: stats, index, tách template, mode cục bộ, driver configuration.
11. Benchmark nhiều giá trị và môi trường staging.
12. Theo dõi p95/p99 và planning CPU sau thay đổi.

Không skip thẳng đến “force_custom_plan global” chỉ vì nghe mô tả hiện tượng phù hợp.

## 45. Một số câu hỏi chẩn đoán nhanh

| Triệu chứng | Câu hỏi cần kiểm tra |
|---|---|
| Literal query nhanh, prepared query chậm | Prepared query đang generic hay custom? |
| Chỉ một tenant chậm | Tenant có cardinality rất khác? |
| Partial index không được dùng | Generic planner có chứng minh được predicate không? |
| Sau chạy lâu mới chậm | Có sự chuyển chọn generic, cache/counter theo session? |
| Sau ANALYZE plan thay đổi | Thống kê/ước lượng mới có làm đổi cost? |
| Query không dùng index | Kiểu dữ liệu/cast có làm index condition không phù hợp? |
| Driver dùng PreparedStatement nhưng view rỗng | Đang xem khác session, hoặc driver chưa tạo named server prepare? |
| Pooler báo prepared statement không tồn tại | Có transaction pooling/session state không tương thích? |
| Generic trên partitioned table | Có runtime pruning không, các subplans có thật sự chạy không? |
| Force custom làm query nhanh nhưng CPU tăng | Planning overhead trên tổng workload là bao nhiêu? |
| Một EXPLAIN nhanh, API vẫn chậm | Có network, locks, result materialization, N+1 queries hoặc khác tham số không? |
| Đổi ngưỡng driver không giải quyết | Server có đang chọn plan kém vì skew/SQL shape không? |

## 46. Những lỗi và hiểu lầm phổ biến

### Lỗi 1 — Nghĩ PREPARE luôn cố định một plan

Sai. PostgreSQL có thể chọn custom hoặc generic theo từng statement.

### Lỗi 2 — Nghĩ EXECUTE thứ sáu chắc chắn generic

Sai. Năm custom plans đầu phục vụ heuristic; server có thể tiếp tục custom nếu generic quá đắt.

### Lỗi 3 — Coi PreparedStatement của Java đồng nghĩa generic plan

Sai. JDBC API, protocol server prepare và planner mode là các tầng khác nhau.

### Lỗi 4 — Trộn prepareThreshold với năm custom executions của PostgreSQL

Sai. Hai ngưỡng có nguồn gốc và lifecycle khác nhau.

### Lỗi 5 — Chỉ EXPLAIN câu SELECT với literal

Nó không nhất thiết phản ánh plan của prepared statement đang dùng. Hãy xem `EXPLAIN EXECUTE` tương đương.

### Lỗi 6 — Đánh giá bằng một giá trị tham số duy nhất

Có thể bỏ sót sự lệch phân bố tenant/status. Test representative parameter groups.

### Lỗi 7 — Generic chắc chắn không dùng index

Sai. Generic plan vẫn có thể chọn index khi hợp lý cho các giá trị nói chung.

### Lỗi 8 — Custom luôn nhanh hơn

Sai. Planning overhead có thể lớn, và custom cũng có thể bị sai ước lượng.

### Lỗi 9 — Generic chắc chắn quét toàn bộ partitions

Sai. Runtime partition pruning có thể loại partitions khi tham số được biết lúc execute.

### Lỗi 10 — Partial index luôn được dùng nếu query có tham số phù hợp

Generic planner có thể không chứng minh được predicate index từ `column = $1`. Custom có thể khác.

### Lỗi 11 — pg_prepared_statements là toàn cluster

Sai. View này là của session hiện tại.

### Lỗi 12 — Đặt plan_cache_mode global để chữa một query

Có thể làm hại nhiều query khác. Ưu tiên thử và scope thay đổi cục bộ.

### Lỗi 13 — Quên RESET sau khi force mode

Những statement sau trong session có thể bị ảnh hưởng ngoài mục đích benchmark.

### Lỗi 14 — Để cast lên cột làm mất khả năng dùng index

Ví dụ `job_id::text = $1` có thể khác `job_id = $1::bigint` về index compatibility.

### Lỗi 15 — Dùng WHERE ($1 IS NULL OR column = $1) cho mọi endpoint

Một generic plan khó tối ưu hai workload có/không filter khác nhau. Cân nhắc tách templates.

### Lỗi 16 — Không ANALYZE dữ liệu thay đổi mạnh

Custom plan vẫn có thể kém khi thống kê cũ.

### Lỗi 17 — Restart connection coi là fix

Restart chỉ reset session prepared state; nếu root cause còn, vấn đề có thể quay lại.

### Lỗi 18 — Dùng transaction pooling nhưng kỳ vọng SQL PREPARE sống mãi giữa transaction

Session-level state không tự chuyển giữa backends. Kiểm tra pooler và driver protocol support.

### Lỗi 19 — Tắt server preparation đồng nghĩa hết SQL injection

Ngược lại: bảo mật phụ thuộc bind parameters/SQL construction, không phải chỉ threshold. Không ghép input vào SQL.

### Lỗi 20 — So planning time nhưng bỏ execution time

Generic tiết kiệm planning có thể làm execution tệ hơn nhiều. Đo tổng chi phí.

### Lỗi 21 — EXPLAIN ANALYZE DML trên production không kiểm soát

ANALYZE thực thi thay đổi; có thể sửa/xóa dữ liệu thật.

### Lỗi 22 — Tin rằng cached generic plan không bao giờ được invalidated

DDL và statistics updates có thể dẫn tới reparse/replan theo quy tắc PostgreSQL.

### Lỗi 23 — Query có schema động nhưng không kiểm tra search_path

Prepared statements có liên quan object resolution; cần quản lý search_path an toàn.

### Lỗi 24 — Chỉ đo khi cache nóng

Có thể ưu ái mode chạy sau trong benchmark. Đảo thứ tự và quan sát buffers.

### Lỗi 25 — Dùng EXPLAIN để suy ra authorization

Execution plan không thay thế kiểm tra quyền/RLS/tenant filtering của API.

## 47. Checklist thiết kế prepared query có hiệu năng tốt

**Bước 1 — Bắt đầu từ SQL đúng.** Xác định WHERE, JOIN, ORDER BY, loại dữ liệu trả về và điều kiện phân quyền.

**Bước 2 — Dùng bind parameters.** Tránh nối dữ liệu chưa tin cậy vào SQL string.

**Bước 3 — Chọn kiểu tham số phù hợp.** Không cast cột index bừa bãi.

**Bước 4 — Định nghĩa query templates.** Tách những chế độ filter rất khác nhau nếu cần thay vì một OR tham số khổng lồ.

**Bước 5 — Giữ thống kê mới.** Chạy/điều chỉnh ANALYZE theo workload, quan sát skew.

**Bước 6 — Tạo index có chủ đích.** B-tree, partial index, composite index theo truy vấn thật; không tạo chỉ mục chỉ vì thấy WHERE.

**Bước 7 — Tìm nhóm tham số đại diện.** Hiếm, phổ biến, tenant nhỏ/lớn và các giá trị NULL nếu hợp lệ.

**Bước 8 — So mode ở session thử nghiệm.** `force_custom_plan` vs `force_generic_plan`.

**Bước 9 — Đọc `EXPLAIN EXECUTE`.** Ước lượng/actual rows, scan/join, buffers, Planning Time và Execution Time.

**Bước 10 — Kiểm tra server prepared lifecycle.** SQL PREPARE, pgJDBC threshold, pooler mode và per-session counters.

**Bước 11 — Thử trong staging với traffic gần thật.** Đo p50/p95/p99, CPU planning và throughput.

**Bước 12 — Thay đổi phạm vi hẹp.** Ưu tiên giải pháp từng statement/endpoint; có rollback về `auto`.

**Bước 13 — Theo dõi sau triển khai.** Không dừng ở một kết quả EXPLAIN thuận lợi.

## 48. Bài tập thực hành

### Bài 1 — PREPARE đơn giản

Viết prepared statement `add_two(bigint, bigint)` tính tổng hai tham số.

**Gợi ý:** `PREPARE add_two(bigint,bigint) AS SELECT $1 + $2;`.

### Bài 2 — EXECUTE và DEALLOCATE

Thực thi add_two với 10, 20; sau đó giải phóng statement.

**Gợi ý:** `EXECUTE add_two(10,20); DEALLOCATE add_two;`.

### Bài 3 — Khác biệt custom/generic

Vì sao custom plan có thể chọn Index Scan cho rare và Seq Scan cho common?

**Gợi ý:** giá trị tham số được biết lúc lập custom plan, selectivity khác nhau.

### Bài 4 — Generic không luôn chậm

Nêu một truy vấn mà các giá trị tham số có độ chọn lọc gần như giống nhau và generic có thể phù hợp.

**Gợi ý:** lookup bằng primary key.

### Bài 5 — Heuristic năm lần

PostgreSQL auto có luôn chọn generic từ lần thứ sáu không?

**Gợi ý:** không; so sánh estimated cost.

### Bài 6 — plan_cache_mode

Viết SQL kiểm tra và buộc custom trong session rồi hoàn nguyên.

**Gợi ý:** `SHOW`, `SET` và `RESET plan_cache_mode`.

### Bài 7 — SET LOCAL

Trong một transaction, buộc generic rồi rollback để phục hồi setting.

**Gợi ý:** `BEGIN; SET LOCAL plan_cache_mode=force_generic_plan; ... ROLLBACK;`.

### Bài 8 — EXPLAIN EXECUTE

Viết SQL xem plan của `job_lookup('rare')` trong force_custom_plan.

**Gợi ý:** `EXPLAIN (ANALYZE,BUFFERS) EXECUTE job_lookup('rare')`.

### Bài 9 — Placeholder trong plan

Khi EXPLAIN EXECUTE hiện `state = $1`, đó thường là dấu hiệu của loại plan nào?

**Gợi ý:** generic.

### Bài 10 — Source data skew

Trong lab 200.000 hàng, có bao nhiêu hàng rare và common?

**Gợi ý:** 200 và 199.800.

### Bài 11 — Đọc pg_prepared_statements

Viết query xem `name`, `generic_plans`, `custom_plans` của session.

**Gợi ý:** `SELECT ... FROM pg_prepared_statements`.

### Bài 12 — Session visibility

Vì sao một terminal mới không thấy statement đã PREPARE từ ứng dụng Java ở connection khác?

**Gợi ý:** prepared statements gắn với session.

### Bài 13 — Hai ngưỡng số 5

Phân biệt default JDBC prepareThreshold với heuristic PostgreSQL auto.

**Gợi ý:** driver server-prepare lifecycle vs server plan selection.

### Bài 14 — Partial index

Index chỉ dành cho `state='rare'`. Vì sao generic `WHERE state=$1` khó dùng nó?

**Gợi ý:** không thể chứng minh $1 luôn là rare.

### Bài 15 — Custom partial index

Khi $1='rare' và custom plan, partial index có thể được cân nhắc không?

**Gợi ý:** có, nếu planner chứng minh predicate và cost phù hợp.

### Bài 16 — Optional filter

Tại sao `WHERE ($1 IS NULL OR state=$1)` có thể khó tối ưu ở generic plan?

**Gợi ý:** phải xử lý cả trường hợp có và không filter.

### Bài 17 — Tham số và kiểu

So sánh `job_id::text = $1` với `job_id = $1::bigint`.

**Gợi ý:** cast trên cột có thể thay đổi khả năng dùng index.

### Bài 18 — ANALYZE

Nếu phân bố common/rare thay đổi lớn, nên làm gì trước khi kết luận cần force custom?

**Gợi ý:** ANALYZE và EXPLAIN lại.

### Bài 19 — Partition pruning

Generic plan có chắc quét mọi partition vì tham số còn là $1 không?

**Gợi ý:** không; có execution-time pruning.

### Bài 20 — JDBC connection

Lặp cùng PreparedStatement trên những physical connections khác nhau có đảm bảo cùng server prepared statement không?

**Gợi ý:** không; session-bound state.

### Bài 21 — PgBouncer transaction pooling

Vì sao SQL PREPARE/EXECUTE giữa các transaction có thể không an toàn khi backend đổi?

**Gợi ý:** prepared statement thuộc server session.

### Bài 22 — Plan invalidation

Một generic plan có bất biến vĩnh viễn sau PREPARE không?

**Gợi ý:** không; DDL/stats/search_path có thể dẫn tới replan.

### Bài 23 — EXPLAIN ANALYZE UPDATE

Tại sao không chạy trong production mà không kiểm soát?

**Gợi ý:** ANALYZE thực thi UPDATE thật.

### Bài 24 — Tổng thời gian

Custom planning 1 ms và execution 2 ms; generic planning 0,05 ms và execution 40 ms. Chọn hướng nào cho tham số đó, nếu các điều kiện đo tương đương?

**Gợi ý:** custom có tổng thời gian thấp hơn rất nhiều.

### Bài 25 — p99

Vì sao chỉ xem mean latency chưa đủ trong bài toán tenant skew?

**Gợi ý:** nhóm tenant nhỏ/hiếm có thể chậm bất thường.

### Bài 26 — Query templates

Thiết kế hai SQL templates cho trường hợp có và không lọc theo state, vẫn dùng bind khi có filter.

**Gợi ý:** một query không WHERE state, một query WHERE state=$1.

### Bài 27 — PER-QUERY tuning

Vì sao force_custom_plan toàn hệ thống thường không phải phương án đầu tiên?

**Gợi ý:** planning CPU có thể tăng với rất nhiều câu SQL khác.

### Bài 28 — Cấu trúc benchmark

Hãy liệt kê ít nhất năm yếu tố cần giữ cố định khi so generic và custom.

**Gợi ý:** SQL, dataset, stats, index, mode, tham số, cache, nhiều lượt đo.

### Bài 29 — pg_stat_statements

`plans` và `total_plan_time` có luôn được ghi khi extension tồn tại không?

**Gợi ý:** phụ thuộc tracking/config; xem `pg_stat_statements.track_planning`.

### Bài 30 — Chẩn đoán

Một endpoint nhanh sau khi reconnect nhưng chậm sau nhiều lần thực thi với tenant nhỏ. Đề xuất ba bước kiểm tra trước khi sửa code.

**Gợi ý:** xác minh prepared statement lifecycle, so EXPLAIN EXECUTE custom/generic, xem selectivity/stats và index.

## 49. Câu hỏi thường gặp

### Dùng bind parameter có chắc nhanh hơn literal SQL không?

Không. Bind parameters tăng tính an toàn và giúp tái sử dụng cấu trúc, nhưng hiệu năng phụ thuộc việc driver/server chuẩn bị ra sao, custom/generic selection và dữ liệu.

### Một câu PREPARE chỉ được lập plan đúng một lần?

Không. Server có thể dùng custom plans cho nhiều lần execute hoặc tái sử dụng generic, và có thể replan khi invalidation phù hợp.

### Generic plan có biết tham số khi chạy không?

**Có tại thời điểm thực thi** để đánh giá predicate và tính toán kết quả. Nhưng **không biết giá trị cụ thể tại thời điểm tạo generic plan** theo cách cho phép tối ưu selectivity riêng cho từng giá trị.

Đây là khác biệt then chốt: generic không “bỏ qua tham số”, mà chỉ **không lập kế hoạch đặc thù theo giá trị**.

### Có nên đặt force_custom_plan cho toàn bộ connection pool?

Không nên mặc định. Cần đo planning overhead cho toàn workload và xem có thể giải quyết tại statement hoặc query template hay không.

### Có thể xem generic/custom của session Java từ pgAdmin connection khác không?

`pg_prepared_statements` không cho quan sát trực tiếp prepared statements của session khác. Cần công cụ/log/đo tại session phù hợp.

### Có nên ép generic để giữ plan ổn định?

Plan ổn định không đồng nghĩa execution time ổn định giữa các tham số. Một generic plan có thể làm tail latency tệ hơn khi workload có skew.

### Tại sao force custom vẫn chọn Seq Scan cho rare?

Có thể thống kê cũ, index không phù hợp, query yêu cầu đọc nhiều hàng, cost model cho rằng seq rẻ hơn, hoặc dữ liệu thực tế không đủ hiếm. Xem `EXPLAIN (ANALYZE, BUFFERS)` thay vì mặc định custom luôn dùng index.

### Dùng partial index với trạng thái cố định và query prepared thế nào?

Nếu ứng dụng có một query riêng mà điều kiện `state='rare'` thực sự cố định, một template literal an toàn có thể giúp planner chứng minh predicate. Nếu giá trị thay đổi theo request, hãy đo generic/custom và không ghép untrusted input thành literal SQL.

### Khi ANALYZE xong, có phải reconnect mọi ứng dụng không?

Không mặc định. PostgreSQL có cơ chế invalidation/replanning khi statistics liên quan thay đổi. Chỉ điều tra reset connection khi có bằng chứng về lifecycle hoặc state không phù hợp, và hiểu tác động tới pool.

## 50. Tổng kết

- **Parameterized SQL** tách dữ liệu đầu vào khỏi cấu trúc query; **prepared statement** giúp tái sử dụng những phần của việc chuẩn bị câu lệnh.
- PostgreSQL có hai chiến lược chính: **custom plan** lập theo giá trị tham số hiện tại và **generic plan** có thể tái sử dụng cho nhiều giá trị.
- **Custom** có thể chọn index/join/scan phù hợp dữ liệu lệch phân bố, đổi lại tốn planning lặp lại.
- **Generic** giảm chi phí lập kế hoạch sau khi plan được cache, nhưng một plan chung có thể không hợp với cả giá trị hiếm và phổ biến.
- Ở `plan_cache_mode=auto`, PostgreSQL sử dụng **custom plans trong những lần đầu** và cân nhắc generic sau khi so chi phí; **không có quy tắc chắc chắn lần thứ sáu luôn generic**.
- `plan_cache_mode` có các chế độ `auto`, `force_custom_plan` và `force_generic_plan`; nên dùng forced modes để **thử nghiệm có phạm vi**, rồi hoàn nguyên.
- `EXPLAIN EXECUTE` là công cụ quan trọng để xem kế hoạch của prepared statement thật. Generic thường hiển thị `$1`; custom thường hiển thị giá trị tham số đã bind.
- `pg_prepared_statements` cho biết số lần chọn generic/custom trong **session hiện tại**; không phải view toàn instance.
- **JDBC `prepareThreshold` và heuristic năm lần đầu của PostgreSQL là hai cơ chế khác nhau**. JDBC PreparedStatement không tự đồng nghĩa server generic plan.
- **Dữ liệu phân bố lệch**, partial indexes, optional filters, tenant skew và nhiều JOIN có thể làm generic kém với một số bộ tham số.
- Generic có thể hưởng **execution-time partition pruning**; không suy rằng query generic phải scan mọi partition.
- Planner statistics, kiểu tham số, index và cấu trúc SQL ảnh hưởng chất lượng **cả generic lẫn custom**.
- Prepared statements gắn với **server session**; connection pooling và transaction pooling cần cấu hình phù hợp với protocol-level/server-side preparation.
- Cached generic plans có thể được lập lại khi cần do DDL, statistics hoặc ngữ cảnh object resolution thay đổi.
- Với ứng dụng production, cần đo **planning time + execution time + tail latency**, cùng buffers, cardinality và nhóm tham số đại diện trước khi áp dụng tuning.

Điều quan trọng nhất không phải hỏi **“generic hay custom luôn tốt hơn?”**, mà là **“chi phí lập kế hoạch và chi phí thực thi biến đổi ra sao theo các tham số thật của workload?”**. Khi phân biệt được prepared statement ở tầng ứng dụng với plan caching ở server, và đo đúng trên các nhóm dữ liệu khác nhau, chúng ta có thể chọn chiến lược truy vấn PostgreSQL **có thể đo, giải thích và kiểm soát.**
