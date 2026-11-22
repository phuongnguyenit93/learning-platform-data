# Biến bind, cursor sharing và tải có phân bố dữ liệu lệch trong Oracle Database

Bind variable là một phần quan trọng của tối ưu SQL trong Oracle. Ứng dụng gửi câu SQL với placeholder và truyền giá trị ở lần thực thi, thay vì ghép giá trị trực tiếp vào chuỗi SQL. Cách này giúp Oracle nhận diện các câu lệnh giống nhau, tái sử dụng cursor trong shared pool và giảm chi phí hard parse. Bind variable cũng giúp tách dữ liệu khỏi cú pháp SQL, giảm nguy cơ SQL injection.

Tuy nhiên, bind variable tạo ra một thách thức về kế hoạch thực thi: cùng một câu SQL có thể nhận nhiều giá trị có độ chọn lọc rất khác nhau. Nếu cột có phân bố lệch (data skew), ví dụ 99% hàng có STATUS = 'COMMON' nhưng chỉ 1% có STATUS = 'RARE', kế hoạch phù hợp cho giá trị phổ biến có thể không phù hợp cho giá trị hiếm.

Oracle xử lý vấn đề này bằng các cơ chế như bind peeking, bind-sensitive cursor, bind-aware cursor và Adaptive Cursor Sharing (ACS). Histograms giúp optimizer hiểu phân bố dữ liệu, còn ACS quan sát selectivity thực tế của các lần chạy để quyết định khi nào cần nhiều child cursor với các kế hoạch khác nhau.

Bài học đi từ cách bind variable và cursor sharing hoạt động, đến bind peeking, histogram, adaptive cursor sharing, child cursor và cách đo runtime. Các ví dụ lấy Oracle Database 19c làm mốc.

## 1. Vì sao cần bind variable?

### 1.1. Ghép literal trực tiếp vào SQL

Một ứng dụng có thể tạo SQL bằng cách nối giá trị:

~~~sql
SELECT order_id, status, total_amount
FROM   orders
WHERE  customer_id = 1001;
~~~

Lần tiếp theo, ứng dụng tạo một chuỗi SQL khác:

~~~sql
SELECT order_id, status, total_amount
FROM   orders
WHERE  customer_id = 1002;
~~~

Về nghiệp vụ, hai câu lệnh có cùng cấu trúc, chỉ khác giá trị customer_id. Nhưng SQL text khác nhau, nên Oracle có thể phải hard parse và lưu các parent cursor riêng nếu không có cơ chế cursor sharing thay thế literal.

Khi ứng dụng có hàng nghìn giá trị khác nhau, shared pool có thể chứa nhiều cursor tương tự. Chi phí parse, CPU và bộ nhớ tăng lên.

### 1.2. Dùng bind variable

Thay giá trị bằng placeholder:

~~~sql
SELECT order_id, status, total_amount
FROM   orders
WHERE  customer_id = :p_customer_id;
~~~

Ứng dụng gửi SQL text này và bind giá trị 1001, 1002 hoặc giá trị khác ở từng lần thực thi.

Nếu SQL text, kiểu bind, schema object, quyền và môi trường optimizer tương thích, Oracle có thể tái sử dụng cursor đã parse. Nhờ đó giảm hard parse và tăng khả năng dùng chung SQL area.

### 1.3. Bind variable có lợi ích gì?

- Giảm số câu SQL khác nhau chỉ vì literal khác nhau.
- Tăng khả năng tái sử dụng parent/child cursor.
- Giảm CPU và latch/mutex contention liên quan parse trong workload có nhiều SQL lặp.
- Giảm lượng cursor tương tự trong shared pool.
- Tách dữ liệu đầu vào khỏi cú pháp SQL, hỗ trợ chống SQL injection.
- Giúp ứng dụng dùng prepared statement và quản lý kiểu dữ liệu đầu vào rõ ràng.

Bind variable không bảo đảm mọi câu lệnh sẽ dùng cùng một child cursor hoặc cùng một execution plan. Cursor sharing còn phụ thuộc kiểu bind, metadata, optimizer environment, statistics và cơ chế adaptive.

### 1.4. Bind variable không thể thay tên bảng hoặc từ khóa

Bind variable đại diện cho giá trị dữ liệu, không thay thế identifier hoặc cú pháp SQL.

Không thể viết:

~~~sql
SELECT *
FROM   :table_name
WHERE  status = :status;
~~~

để bind tên bảng. Oracle parse tên bảng trước khi bind value. Nếu cần dynamic table/column/order direction, hãy xây SQL từ allowlist identifier hợp lệ và bind mọi giá trị dữ liệu.

Ví dụ an toàn về nguyên tắc:

~~~sql
-- Ứng dụng chỉ chọn tableName từ allowlist đã định nghĩa.
-- Giá trị status vẫn được bind.
SELECT order_id, status
FROM   orders
WHERE  status = :p_status;
~~~

Không ghép chuỗi đầu vào tùy ý của người dùng vào SQL text.

## 2. Hard parse, soft parse và cursor sharing

### 2.1. Hard parse

Hard parse xảy ra khi Oracle cần phân tích SQL và xây dựng kế hoạch/cursor mới. Công việc có thể gồm:
- Parse cú pháp và kiểm tra ngữ nghĩa.
- Kiểm tra quyền và resolve object.
- Tối ưu câu SQL và chọn execution plan.
- Tạo hoặc nạp cấu trúc cursor trong shared pool.
- Kiểm tra tương thích với các cursor đã có.

Hard parse tốn CPU và có thể gây tranh chấp tài nguyên trong hệ thống nhiều session.

### 2.2. Soft parse

Soft parse xảy ra khi Oracle tìm được cursor phù hợp có thể tái sử dụng. Oracle vẫn phải xử lý parse call và kiểm tra một số điều kiện, nhưng tránh được phần lớn công việc tối ưu lại từ đầu.

Soft parse không có nghĩa chi phí bằng 0. Một ứng dụng parse statement liên tục rồi close/reopen vẫn có thể tạo nhiều parse call dù SQL được chia sẻ. Prepared statement ở tầng ứng dụng giúp tái sử dụng statement handle và giảm parse overhead hơn nữa.

### 2.3. Parent cursor và child cursor

Có thể hình dung:
- **Parent cursor:** đại diện cho SQL statement trong library cache.
- **Child cursor:** một phiên bản cursor cụ thể, chứa plan và thông tin thực thi phù hợp với một tập điều kiện tương thích.

Một SQL_ID có thể có nhiều child cursor. Nguyên nhân có thể là:
- Bind metadata hoặc kiểu bind khác nhau.
- Optimizer environment khác nhau.
- Object metadata hoặc quyền khác nhau.
- Statistics thay đổi.
- Adaptive Cursor Sharing cần kế hoạch cho các selectivity range khác nhau.
- Các lý do không tương thích khác được Oracle ghi nhận.

Vì vậy, nhiều child cursor không đồng nghĩa chắc chắn có lỗi. Cần xem lý do child cursor không share được.

### 2.4. Cursor sharing và plan sharing là hai khái niệm khác nhau

Cursor sharing cho phép nhiều lần thực thi dùng chung cấu trúc SQL/cursor khi tương thích. Plan sharing là khả năng dùng lại cùng execution plan.

Một parent SQL có thể có nhiều child cursor với nhiều plan hash value. Điều này có thể là hành vi mong muốn khi bind value có selectivity khác nhau.

### 2.5. Ví dụ quan sát cursor

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       parse_calls,
       version_count,
       is_bind_sensitive,
       is_bind_aware,
       is_shareable
FROM   v$sql
WHERE  sql_text LIKE 'SELECT order_id, status, total_amount%'
ORDER  BY sql_id, child_number;
~~~

V$SQL hiển thị các child cursor đang có trong shared SQL area. Truy vấn mẫu có thể khớp nhiều SQL khác nhau; trong hệ thống thật hãy lọc theo SQL_ID chính xác sau khi xác định câu lệnh cần điều tra.

## 3. CURSOR_SHARING

### 3.1. EXACT

CURSOR_SHARING = EXACT là mặc định phổ biến. Oracle yêu cầu SQL text khớp theo quy tắc nhận diện cursor để chia sẻ cursor; các câu lệnh chỉ khác literal thường không được tự động chuẩn hóa thành cùng một SQL.

Ứng dụng nên chủ động dùng bind variables để có SQL text ổn định.

~~~sql
ALTER SESSION SET cursor_sharing = EXACT;
~~~

Đây là thiết lập ở mức session trong ví dụ. Giá trị production thường được quản trị ở mức instance hoặc session theo chính sách.

### 3.2. FORCE

CURSOR_SHARING = FORCE yêu cầu Oracle thay nhiều literal trong SQL bằng system-generated bind variables để tăng khả năng chia sẻ cursor.

~~~sql
ALTER SESSION SET cursor_sharing = FORCE;
~~~

Ví dụ hai câu SQL chỉ khác literal có thể được chuẩn hóa thành dạng có bind nội bộ để tái sử dụng cursor.

FORCE có thể hữu ích như biện pháp chuyển tiếp cho ứng dụng cũ tạo quá nhiều SQL text khác nhau. Tuy nhiên, nó không thay thế việc sửa ứng dụng để dùng bind variable rõ ràng. Các literal khác nhau có thể cần kế hoạch khác nhau; ép chia sẻ có thể làm giảm chất lượng kế hoạch nếu optimizer không xử lý selectivity phù hợp.

### 3.3. SIMILAR

CURSOR_SHARING = SIMILAR là lựa chọn cũ đã bị deprecated. Không nên chọn SIMILAR cho thiết kế mới; dùng EXACT và bind variables ở tầng ứng dụng, hoặc đánh giá FORCE như biện pháp chuyển tiếp khi có lý do cụ thể.

### 3.4. FORCE không phải giải pháp SQL injection

CURSOR_SHARING = FORCE không biến dynamic SQL không an toàn thành an toàn. Nó không thay identifier do người dùng cung cấp bằng allowlist và không thay thế bind variable đúng cách trong code ứng dụng.

Phòng chống SQL injection vẫn cần:
- Bind tất cả giá trị dữ liệu.
- Allowlist identifier nếu dynamic SQL cần tên bảng/cột.
- Không ghép raw input vào SQL.
- Phân quyền tối thiểu cho schema ứng dụng.

### 3.5. Không thay đổi CURSOR_SHARING tùy tiện ở production

Thay đổi CURSOR_SHARING có thể ảnh hưởng toàn bộ workload của session/instance. Trước khi đổi:
1. Đếm SQL có literal variants và parse rate.
2. Xác định ứng dụng nào không dùng bind.
3. Đánh giá các truy vấn phụ thuộc literal-specific optimization.
4. So sánh plan và runtime trước/sau.
5. Thử trên môi trường tương đương production.
6. Chuẩn bị cách rollback tham số.

Sửa ứng dụng để dùng bind đúng kiểu thường là giải pháp bền vững hơn.

## 4. Data skew — dữ liệu có phân bố lệch

### 4.1. Phân bố đồng đều và phân bố lệch

Nếu một cột có 100 giá trị và mỗi giá trị chiếm xấp xỉ 1% hàng, phân bố tương đối đồng đều.

Nếu một cột STATUS có:
- COMMON: 99.000 hàng.
- RARE: 1.000 hàng.

thì phân bố lệch. Giá trị COMMON phổ biến, RARE hiếm.

Selectivity là tỷ lệ hàng thỏa predicate so với tổng số hàng. Với 100.000 hàng:
- STATUS = 'COMMON' có selectivity khoảng 99%.
- STATUS = 'RARE' có selectivity khoảng 1%.

Cùng một câu SQL có thể cần hai access path khác nhau:
- COMMON có thể phù hợp full table scan vì cần phần lớn hàng.
- RARE có thể phù hợp index range scan vì chỉ cần một phần nhỏ hàng.

### 4.2. Vì sao một plan có thể không phù hợp mọi bind value?

Giả sử SQL:

~~~sql
SELECT order_id,
       status,
       payload
FROM   orders_skew
WHERE  status = :p_status;
~~~

Nếu Oracle chọn index range scan dựa trên bind value hiếm, kế hoạch có thể rất tốt cho RARE nhưng tốn nhiều table access cho COMMON.

Nếu Oracle chọn full table scan dựa trên bind value phổ biến, kế hoạch có thể tốt cho COMMON nhưng đọc nhiều block không cần thiết cho RARE.

Đây là vấn đề bind-sensitive plan: cùng SQL text nhưng selectivity khác nhau theo giá trị bind.

### 4.3. Data skew không chỉ có ở cột status

Skew có thể xuất hiện ở:
- Mã tenant: một tenant có phần lớn dữ liệu.
- Trạng thái: một trạng thái chiếm đa số.
- Quốc gia/khu vực: dữ liệu tập trung ở một số giá trị.
- Loại giao dịch hoặc sản phẩm.
- Ngày tháng: dữ liệu mới chiếm tỷ trọng lớn.
- Cột nullable: phần lớn giá trị là NULL hoặc một giá trị cụ thể.

Đặc biệt chú ý predicate có bind trên cột có histogram hoặc có phân bố lệch mạnh.

## 5. Chuẩn bị dữ liệu lệch để thực hành

### 5.1. Tạo bảng

~~~sql
CREATE TABLE orders_skew (
    order_id NUMBER PRIMARY KEY,
    status   VARCHAR2(20) NOT NULL,
    payload  VARCHAR2(200)
);
~~~

### 5.2. Nạp 100.000 hàng với 1% RARE

~~~sql
INSERT INTO orders_skew (order_id, status, payload)
SELECT level,
       CASE
           WHEN MOD(level, 100) = 0 THEN 'RARE'
           ELSE 'COMMON'
       END,
       RPAD('X', 100, 'X')
FROM   dual
CONNECT BY level <= 100000;

COMMIT;
~~~

Mỗi 100 hàng có một hàng RARE, tạo phân bố xấp xỉ 99% COMMON và 1% RARE.

### 5.3. Tạo index

~~~sql
CREATE INDEX ix_orders_skew_status
ON orders_skew(status);
~~~

Index này cho phép optimizer cân nhắc range scan khi giá trị chọn ít hàng. Với COMMON, đọc phần lớn bảng qua index rồi truy cập table row có thể đắt hơn full scan.

### 5.4. Thu thập statistics và histogram

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'ORDERS_SKEW',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR COLUMNS SIZE 254 STATUS',
        cascade          => TRUE
    );
END;
/
~~~

SIZE 254 cho phép optimizer tạo histogram với số bucket tối đa phù hợp. Kết quả cụ thể phụ thuộc phiên bản, NDV, sampling và thuật toán histogram.

Không dùng bảng demo này để kết luận mọi hệ thống phải tạo histogram 254 bucket. Histograms cần được chọn theo phân bố, workload và chính sách thống kê.

### 5.5. Kiểm tra phân bố thực tế

~~~sql
SELECT status,
       COUNT(*) AS row_count,
       ROUND(
           COUNT(*) * 100 /
           (SELECT COUNT(*) FROM orders_skew),
           2
       ) AS pct
FROM   orders_skew
GROUP  BY status
ORDER  BY status;
~~~

Kết quả cho thấy COMMON chiếm khoảng 99%, RARE khoảng 1%. Đây là dữ liệu thực tế của bảng; optimizer dùng statistics để ước lượng thay vì chạy COUNT(*) cho mỗi lần hard parse.

## 6. Histograms và selectivity

### 6.1. Statistics cơ bản

Optimizer dùng table/column statistics như:
- NUM_ROWS.
- NDV (number of distinct values).
- NULL_COUNT.
- DENSITY.
- Histogram.
- Index statistics và clustering factor.

Nếu không có histogram, optimizer thường phải ước lượng selectivity từ thống kê tổng quát. Với cột lệch mạnh, giả định phân bố đồng đều có thể gây sai lệch lớn.

### 6.2. Histogram giúp gì?

Histogram mô tả phân bố giá trị trong cột chi tiết hơn so với NDV/density đơn giản. Nó giúp optimizer nhận ra giá trị phổ biến và hiếm để ước lượng số hàng phù hợp.

Ví dụ với STATUS:
- COMMON là popular value.
- RARE là unpopular value.

Khi optimizer biết điều đó, kế hoạch cho predicate literal hoặc bind được peek có thể phản ánh selectivity tốt hơn.

### 6.3. Các loại histogram

Trong các phiên bản Oracle hiện đại có thể gặp:
- **Frequency histogram:** lưu tần suất các giá trị khi số distinct values phù hợp với số bucket.
- **Top-frequency histogram:** tập trung vào các giá trị phổ biến nhất khi số distinct values vượt số bucket nhưng một nhóm giá trị chiếm phần lớn dữ liệu.
- **Hybrid histogram:** kết hợp thông tin tần suất và endpoint để ước lượng phân bố.
- **Height-balanced histogram:** dạng histogram cũ, chủ yếu gặp trong hệ thống hoặc statistics được tạo ở các phiên bản trước.

Loại histogram được tạo phụ thuộc NDV, số bucket, sampling và phiên bản. Không cần tự chọn loại histogram trong hầu hết trường hợp; hãy dùng DBMS_STATS với METHOD_OPT phù hợp rồi xem metadata.

### 6.4. Kiểm tra histogram

~~~sql
SELECT column_name,
       histogram,
       num_distinct,
       num_buckets,
       density,
       last_analyzed
FROM   user_tab_col_statistics
WHERE  table_name = 'ORDERS_SKEW'
AND    column_name = 'STATUS';
~~~

Xem các endpoint:

~~~sql
SELECT endpoint_number,
       endpoint_value,
       endpoint_actual_value
FROM   user_tab_histograms
WHERE  table_name = 'ORDERS_SKEW'
AND    column_name = 'STATUS'
ORDER  BY endpoint_number;
~~~

Tên cột và khả năng xem endpoint phụ thuộc loại dữ liệu và phiên bản. Với VARCHAR2, có thể cần xem thêm endpoint_actual_value nếu có.

### 6.5. SIZE AUTO và SIZE 254

- SIZE AUTO để DBMS_STATS quyết định histogram dựa trên thông tin workload/column usage và chính sách thống kê.
- SIZE 254 yêu cầu số bucket tối đa theo giới hạn được hỗ trợ.
- SIZE 1 không tạo histogram chi tiết (chỉ statistics cơ bản).
- SIZE REPEAT giữ cách tạo histogram theo thống kê hiện có trong một số quy trình.

Histogram không phải lúc nào cũng nên tạo. Một cột có nhiều giá trị, workload không lọc theo cột đó hoặc bind workload không hưởng lợi có thể không cần histogram.

### 6.6. Histogram không thay thế index

Histogram giúp optimizer ước lượng selectivity. Index là cấu trúc access path. Histogram không tự làm truy vấn đọc ít block hơn; nó chỉ giúp optimizer chọn kế hoạch dựa trên phân bố tốt hơn.

## 7. Bind peeking — optimizer nhìn giá trị bind lúc parse

### 7.1. Bind peeking là gì?

Khi hard parse một câu SQL có bind variable, Oracle có thể peek (xem) giá trị bind hiện tại để ước lượng selectivity và chọn execution plan.

Ví dụ:

~~~sql
SELECT order_id, payload
FROM   orders_skew
WHERE  status = :p_status;
~~~

Nếu lần hard parse đầu tiên có bind RARE, optimizer có thể ước lượng khoảng 1% hàng và chọn index range scan.

Nếu lần hard parse đầu tiên có bind COMMON, optimizer có thể ước lượng khoảng 99% hàng và chọn full table scan.

### 7.2. Bind peeking không có nghĩa mỗi execution đều hard parse

Bind peeking chủ yếu liên quan lúc optimizer tạo/biên dịch cursor. Khi cursor được tái sử dụng, Oracle không hard parse lại chỉ vì bind value đổi. Do đó kế hoạch ban đầu có thể tiếp tục được dùng cho giá trị khác.

Đây là nguồn gốc vấn đề “một plan cho mọi bind value” trong workload có data skew.

### 7.3. Giá trị bind đầu tiên có thể ảnh hưởng kế hoạch ban đầu

Nếu lần parse đầu tiên nhận giá trị hiếm, plan có thể tối ưu cho hiếm. Nếu giá trị phổ biến đến sau, cùng child cursor có thể không tối ưu cho workload đó.

Điều ngược lại cũng đúng: parse đầu với COMMON có thể chọn full scan rồi dùng lại cho RARE.

Không nên dùng thao tác flush shared pool trong production để “thử bind đầu tiên”. Thử nghiệm nên thực hiện trên schema hoặc database kiểm soát được, với session/cursor riêng và cách thu thập plan rõ ràng.

### 7.4. Peeked bind trong DBMS_XPLAN

Có thể xem bind value mà optimizer peek ở thời điểm hard parse bằng format option phù hợp:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :p_sql_id,
        :p_child_no,
        'ALLSTATS LAST +PEEKED_BINDS +PREDICATE'
    )
);
~~~

PEEKED_BINDS phản ánh giá trị được peek lúc parse, không phải nhật ký đầy đủ của mọi bind value từng được dùng khi execute.

### 7.5. Bind peeking không giải quyết mọi skew

Bind peeking cải thiện ước lượng cho lần parse cụ thể, nhưng một cursor có thể được thực thi với nhiều bind value khác nhau. Nếu selectivity khác biệt lớn, cần cơ chế tạo và quản lý nhiều plan phù hợp hơn.

## 8. Bind-sensitive cursor và Adaptive Cursor Sharing

### 8.1. Bind-sensitive cursor

Một cursor được gọi là bind-sensitive khi optimizer nhận thấy kế hoạch/ước lượng có thể phụ thuộc vào giá trị bind. Oracle có thể đánh dấu cursor này để theo dõi các lần thực thi với bind values khác nhau.

Không phải mọi câu SQL có bind đều trở thành bind-sensitive. Cơ chế phụ thuộc predicate, statistics, histogram, selectivity và điều kiện optimizer.

Trong V$SQL, có thể xem cờ:
- IS_BIND_SENSITIVE.
- IS_BIND_AWARE.

### 8.2. Bind-aware cursor

Khi Oracle có đủ bằng chứng rằng các bind values tạo selectivity khác nhau và cần kế hoạch khác nhau, cursor có thể trở thành bind-aware.

Oracle có thể tạo thêm child cursor để phục vụ các selectivity range khác nhau. Ví dụ:
- Một child cho COMMON với full table scan.
- Một child cho RARE với index range scan.

Các giá trị bind có selectivity gần nhau có thể tiếp tục dùng cùng một child cursor.

### 8.3. Adaptive Cursor Sharing (ACS)

ACS là cơ chế theo dõi hiệu quả thực thi của bind-sensitive cursor và điều chỉnh việc chọn child cursor theo selectivity của bind.

Khái quát quá trình:

~~~text
SQL có bind variable
        |
        v
Hard parse / bind peeking
        |
        v
Tạo child cursor ban đầu
        |
        v
Oracle theo dõi executions và selectivity
        |
        v
Phát hiện các bind values có selectivity khác nhau?
        |
       Có
        |
        v
Cursor trở thành bind-aware
        |
        v
Tạo/chọn child cursor phù hợp
cho các selectivity range
~~~

ACS không nhất thiết tạo child cursor ngay sau lần chạy thứ hai. Oracle cần dữ liệu quan sát và điều kiện phù hợp. Có thể không kích hoạt nếu optimizer không thấy lợi ích hoặc selectivity không đủ khác biệt.

### 8.4. ACS không phải một child cho mỗi giá trị bind

Mục tiêu của ACS là gom các bind values có hành vi selectivity tương tự vào một vùng. Không phải tạo một child cursor cho từng giá trị riêng lẻ.

Ví dụ:
- RARE_A và RARE_B có thể nằm cùng selectivity range.
- COMMON có thể nằm trong range khác.
- Một số giá trị trung gian có thể dùng một child thứ ba nếu optimizer thấy cần.

### 8.5. ACS không bảo đảm mọi workload skew đều được giải quyết

ACS phụ thuộc:
- Statistics và histogram.
- Mức độ chênh selectivity.
- Số lần thực thi và thông tin runtime.
- Kế hoạch thay thế có lợi ích đủ lớn.
- Phiên bản và trạng thái cursor.
- Bind metadata và optimizer environment.

Nếu kế hoạch vẫn kém, hãy điều tra cardinality, histogram, access path, join order và runtime. Đừng giả định chỉ cần bật ACS là mọi vấn đề biến mất.

### 8.6. Xem trạng thái bind-sensitive/bind-aware

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       is_bind_sensitive,
       is_bind_aware,
       is_shareable
FROM   v$sql
WHERE  sql_id = :p_sql_id
ORDER  BY child_number;
~~~

Nếu ACS hoạt động, có thể thấy nhiều child cursor và cờ bind-aware. Nhưng nhiều child cũng có thể do bind mismatch hoặc optimizer environment mismatch; cần kiểm tra thêm lý do.

## 9. Child cursor và lý do không share được

### 9.1. Nhiều child cursor có thể bình thường

Một SQL_ID có nhiều child cursor không nhất thiết là lỗi. Một số child có thể cần thiết để:
- Dùng plan khác nhau cho selectivity range khác nhau.
- Hỗ trợ bind datatype/length khác nhau khi Oracle không thể share an toàn.
- Phản ánh optimizer environment khác nhau.
- Xử lý metadata hoặc quyền khác nhau.

Vấn đề cần điều tra khi child cursor tăng liên tục, parse CPU cao, version count lớn hoặc cùng workload tạo nhiều child không cần thiết.

### 9.2. Xem VERSION_COUNT

~~~sql
SELECT sql_id,
       version_count,
       executions,
       parse_calls,
       loads,
       invalidations
FROM   v$sqlarea
WHERE  sql_id = :p_sql_id;
~~~

VERSION_COUNT là số child cursor gắn với parent cursor. Giá trị cao cần được giải thích, không tự động là lỗi.

### 9.3. Xem lý do trong V$SQL_SHARED_CURSOR

~~~sql
SELECT child_number,
       bind_mismatch,
       optimizer_mismatch,
       stats_row_mismatch,
       literal_mismatch,
       language_mismatch,
       bind_equiv_failure
FROM   v$sql_shared_cursor
WHERE  sql_id = :p_sql_id
ORDER  BY child_number;
~~~

Các cột này giúp phát hiện một số lý do cursor không share được. Tập cột và ý nghĩa chi tiết có thể mở rộng theo release; hãy tra Data Dictionary Reference đúng phiên bản.

Một số nguyên nhân thường gặp:
- BIND_MISMATCH: bind metadata không tương thích, ví dụ datatype/length khác.
- OPTIMIZER_MISMATCH: môi trường optimizer khác nhau.
- STATS_ROW_MISMATCH: statistics hoặc metadata liên quan làm cursor không tương thích.
- LITERAL_MISMATCH: literal/SQL text khác theo điều kiện share.
- BIND_EQUIV_FAILURE: bind selectivity không tương đương cho child cursor hiện có trong cơ chế adaptive.

Không sửa bằng cách ép mọi session dùng cùng cấu hình nếu sự khác biệt là có chủ ý. Trước hết xác định nguyên nhân và tác động.

### 9.4. Bind datatype mismatch

Ví dụ cột CUSTOMER_ID là NUMBER nhưng ứng dụng lúc bind số, lúc bind chuỗi. Driver có thể gửi metadata khác nhau:
- setLong cho một lần.
- setString cho lần khác.

Điều này có thể dẫn đến implicit conversion, ảnh hưởng index usage, cardinality hoặc cursor sharing.

Hãy dùng datatype nhất quán với cột:
- NUMBER: bind kiểu số.
- DATE/TIMESTAMP: bind kiểu ngày giờ.
- VARCHAR2: bind chuỗi.
- RAW: bind byte array/RAW theo driver.

### 9.5. Kiểm tra bind metadata

Có thể xem thông tin bind được capture:

~~~sql
SELECT sql_id,
       child_number,
       name,
       position,
       datatype_string,
       max_length,
       was_captured,
       last_captured
FROM   v$sql_bind_capture
WHERE  sql_id = :p_sql_id
ORDER  BY child_number, position;
~~~

Bind capture có tính lấy mẫu và không bảo đảm ghi lại mọi lần thực thi hoặc mọi giá trị. Không dùng view này như audit log đầy đủ của bind values.

## 10. Quan sát Adaptive Cursor Sharing

### 10.1. V$SQL_CS_SELECTIVITY

View này cung cấp thông tin selectivity range mà ACS theo dõi cho các predicate:

~~~sql
SELECT *
FROM   v$sql_cs_selectivity
WHERE  sql_id = :p_sql_id
ORDER  BY child_number, range_id;
~~~

Dùng để xem các vùng selectivity gắn với child cursor. Các cột chi tiết có thể thay đổi theo release; xem mô tả view trong Oracle Database Reference.

### 10.2. V$SQL_CS_STATISTICS

~~~sql
SELECT *
FROM   v$sql_cs_statistics
WHERE  sql_id = :p_sql_id
ORDER  BY child_number;
~~~

View này lưu thống kê thực thi theo bind set mà ACS sử dụng để đánh giá selectivity và hiệu quả cursor. Có thể xem executions, rows processed, buffer gets và thông tin liên quan tùy release.

### 10.3. V$SQL_CS_HISTOGRAM

~~~sql
SELECT *
FROM   v$sql_cs_histogram
WHERE  sql_id = :p_sql_id
ORDER  BY child_number, bucket_id;
~~~

View này hỗ trợ quan sát phân bố các lần thực thi theo bucket của cơ chế ACS. Dùng cùng V$SQL và V$SQL_CS_SELECTIVITY để hiểu cursor đã quan sát bind workload ra sao.

### 10.4. Không đọc ACS view một cách độc lập

Các view CS là dữ liệu chẩn đoán, không phải bằng chứng duy nhất rằng kế hoạch tốt. Cần đối chiếu:
- Child cursor và plan hash value.
- Bind-sensitive/bind-aware flags.
- Selectivity range.
- Actual rows, buffers, elapsed time.
- Bind values/metadata khi có.
- Predicate và execution plan thực tế.

## 11. Thực hành bind peeking và ACS trên dữ liệu skew

### 11.1. Chuẩn bị câu SQL cố định

Dùng cùng SQL text và bind variable:

~~~sql
SELECT /* bind_skew_demo */
       order_id,
       status,
       payload
FROM   orders_skew
WHERE  status = :p_status;
~~~

Nếu dùng SQL*Plus hoặc SQLcl, có thể bind cùng một biến ở các lần chạy:

~~~sql
VARIABLE p_status VARCHAR2(20)

EXEC :p_status := 'RARE';

SELECT /* bind_skew_demo */
       order_id, status, payload
FROM   orders_skew
WHERE  status = :p_status;

EXEC :p_status := 'COMMON';

SELECT /* bind_skew_demo */
       order_id, status, payload
FROM   orders_skew
WHERE  status = :p_status;
~~~

Cùng SQL text được thực thi với hai giá trị có selectivity rất khác nhau.

### 11.2. Fetch đầy đủ và lặp lại có kiểm soát

Khi đo runtime:
- Fetch toàn bộ kết quả để đo đầy đủ công việc.
- Chạy nhiều lần với COMMON và RARE.
- Giữ cùng session/environment nếu mục tiêu là quan sát cursor sharing trong session đó.
- Ghi nhận thời điểm parse và child cursor.
- Không flush shared pool hoặc buffer cache trong production.

ACS có thể cần nhiều lần thực thi để nhận diện các selectivity range.

### 11.3. Xem cursor

Sau khi chạy, tìm SQL_ID bằng marker:

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       parse_calls,
       is_bind_sensitive,
       is_bind_aware
FROM   v$sql
WHERE  sql_text LIKE '%bind_skew_demo%'
ORDER  BY child_number;
~~~

Nếu đã có SQL_ID, dùng truy vấn cụ thể thay vì LIKE rộng.

### 11.4. Xem plan của từng child

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :p_sql_id,
        :p_child_no,
        'ALLSTATS LAST +PEEKED_BINDS +PREDICATE +NOTE'
    )
);
~~~

So sánh:
- Operation access path.
- Plan hash value.
- E-Rows so với A-Rows.
- Buffers và elapsed time.
- Bind value được peek.
- Predicate được dùng ở đâu.

### 11.5. Diễn giải kết quả

Một kết quả có thể xảy ra:
- Child đầu tiên có index range scan, phù hợp RARE.
- Sau các lần chạy COMMON, Oracle nhận thấy selectivity khác biệt.
- Cursor trở thành bind-aware và có child khác với full table scan.
- Các lần chạy tiếp theo được gán child phù hợp theo selectivity range.

Đây là hành vi có thể thấy, không phải kết quả bắt buộc cho mọi dữ liệu. Optimizer có thể chọn plan khác dựa trên kích thước bảng, clustering factor, hệ thống lưu trữ và statistics.

## 12. Bind variable, datatype và implicit conversion

### 12.1. Bind đúng kiểu cột

Nếu cột là NUMBER:

~~~sql
SELECT *
FROM   orders
WHERE  customer_id = :p_customer_id;
~~~

Ở JDBC, bind bằng setLong/setBigDecimal phù hợp kiểu cột thay vì setString cho số.

Nếu cột là DATE, dùng bind kiểu DATE/TIMESTAMP, không ghép chuỗi ngày phụ thuộc NLS.

### 12.2. Implicit conversion có thể làm hỏng access path

Ví dụ cột NUMBER nhưng bind VARCHAR2 hoặc literal text:

~~~sql
SELECT *
FROM   orders
WHERE  customer_id = :p_customer_id;
~~~

Nếu Oracle phải chuyển đổi kiểu, cần kiểm tra Predicate Information để xem conversion được áp dụng lên bind hay lên cột. Khi function/conversion áp lên cột index, index thông thường có thể không còn được sử dụng như mong muốn.

Đừng dựa vào NLS_DATE_FORMAT hoặc NLS_NUMERIC_CHARACTERS của session để chuyển dữ liệu. Bind kiểu đúng để tránh lỗi và kế hoạch bất ngờ.

### 12.3. Bind length và character set

Với VARCHAR2, metadata về độ dài và character set có thể ảnh hưởng cursor sharing hoặc conversion. Driver nên bind cùng datatype/length policy nhất quán giữa các lần thực thi.

### 12.4. Bind NULL

Bind NULL cần datatype rõ ràng trong nhiều driver/API. Một placeholder NULL không có type metadata đủ rõ có thể gây conversion hoặc lỗi. Khai báo kiểu bind theo cột và API driver, kể cả khi value hiện tại là NULL.

## 13. Khi nào nên dùng literal, khi nào nên dùng bind?

### 13.1. Dùng bind cho giá trị dữ liệu thay đổi

Phần lớn truy vấn OLTP nên dùng bind:
- customer_id.
- order_id.
- status.
- date range.
- amount threshold.
- tenant_id.

Đây là các giá trị thay đổi giữa executions nhưng cấu trúc SQL giữ nguyên.

### 13.2. Literal có thể hữu ích trong một số truy vấn đặc biệt

Một số workload batch/report có các giá trị cố định, cần plan khác biệt rõ hoặc có SQL text sinh tự động. Literal có thể giúp optimizer thấy giá trị cụ thể khi parse. Tuy nhiên, không nên dùng literal hàng loạt chỉ để tránh vấn đề bind peeking.

Nếu cần tách kế hoạch cho hai loại workload có selectivity rất khác nhau, cân nhắc:
- Tách thành hai câu SQL có mục đích rõ ràng.
- Dùng SQL profiles/baselines hoặc cơ chế plan management khi phù hợp.
- Dùng ACS nếu optimizer nhận diện được bind selectivity.
- Thiết kế predicate và index phù hợp.

### 13.3. Không dùng literal để tạo vô số cursor

Nếu mỗi request tạo SQL text mới vì customer ID khác nhau, parse overhead có thể lớn. Hãy ưu tiên bind và quan sát ACS trước khi quyết định ngoại lệ.

### 13.4. Optional predicate

Mẫu thường gặp:

~~~sql
SELECT *
FROM   orders
WHERE  (:p_status IS NULL OR status = :p_status);
~~~

Mẫu này cho phép một SQL xử lý cả trường hợp lọc và không lọc. Tuy nhiên, OR predicate có thể khiến selectivity và access path khó ước lượng, tùy optimizer và bind value.

Nếu hai trường hợp có workload khác nhau đáng kể, hai câu SQL riêng có thể dễ tối ưu hơn:
- Không có status filter: SQL không chứa predicate status.
- Có status filter: SQL có predicate status = :p_status.

Đây là lựa chọn thiết kế cần đo, không phải quy tắc cứng.

### 13.5. IN list và số lượng phần tử

Một câu IN với số placeholder thay đổi theo độ dài danh sách có thể tạo SQL text khác nhau:
- IN (:b1)
- IN (:b1, :b2)
- IN (:b1, :b2, :b3)

Nếu ứng dụng thường có danh sách lớn hoặc số lượng thay đổi, cân nhắc collection binding, temporary table hoặc giải pháp staging phù hợp thay vì ghép literal list.

## 14. Histograms, bind peeking và ACS phối hợp ra sao?

### 14.1. Histograms cung cấp thông tin phân bố

Histogram giúp optimizer ước lượng selectivity khác nhau giữa popular và unpopular values. Nếu không có histogram, optimizer có thể ước lượng trung bình và đánh giá sai với giá trị hiếm/phổ biến.

### 14.2. Bind peeking chọn plan ban đầu

Khi hard parse, bind peeking cho optimizer biết giá trị hiện tại để chọn kế hoạch. Histogram có thể hỗ trợ ước lượng giá trị đó.

### 14.3. ACS học từ executions

Nếu cursor bind-sensitive được thực thi với các bind values có selectivity khác nhau, ACS có thể tạo các selectivity range và child cursor tương ứng.

### 14.4. Không phải lúc nào histogram cũng giúp bind

Hiệu quả phụ thuộc cách optimizer xử lý bind, histogram, predicate và phiên bản. Có thể có cursor không trở thành bind-sensitive, hoặc ACS không tạo child mới dù dữ liệu lệch.

Nếu plan vẫn không phù hợp:
- Xác minh histogram có tồn tại và còn mới.
- Xác minh predicate thực sự dùng đúng cột.
- Xem bind datatype và implicit conversion.
- Kiểm tra E-Rows/A-Rows.
- Kiểm tra child cursor và ACS views.
- Đánh giá SQL tách theo workload hoặc thiết kế index.

## 15. Kiểm tra và cập nhật statistics đúng cách

### 15.1. Xem statistics

~~~sql
SELECT table_name,
       num_rows,
       last_analyzed,
       stale_stats
FROM   user_tab_statistics
WHERE  table_name = 'ORDERS_SKEW';
~~~

Xem column statistics:

~~~sql
SELECT column_name,
       num_distinct,
       density,
       histogram,
       num_buckets,
       last_analyzed
FROM   user_tab_col_statistics
WHERE  table_name = 'ORDERS_SKEW';
~~~

### 15.2. Thu thập lại histogram

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'ORDERS_SKEW',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR COLUMNS SIZE 254 STATUS',
        cascade          => TRUE
    );
END;
/
~~~

Statistics mới có thể làm invalidation/reoptimization một số cursor tùy cơ chế và trạng thái. Sau khi gather, quan sát cursor mới và plan thực tế.

### 15.3. Không gather statistics liên tục

Thu thập statistics quá thường xuyên có thể tạo overhead và khiến plan thay đổi không cần thiết. Dùng auto stats task hoặc quy trình quản trị đã thiết kế, theo dõi stale statistics và thay đổi dữ liệu.

### 15.4. Histograms và column usage

SIZE AUTO có thể dùng thông tin column usage do workload tạo ra để quyết định cột nào cần histogram. Điều này giúp tránh histogram không cần thiết, nhưng cần kiểm tra kết quả và chính sách thống kê của môi trường.

## 16. Bind capture và bảo mật dữ liệu

### 16.1. V$SQL_BIND_CAPTURE không phải audit đầy đủ

Oracle có thể capture một số bind values theo chu kỳ và điều kiện. Không phải mọi execution đều được ghi lại. Dữ liệu có thể không có, cũ hoặc bị giới hạn theo datatype.

Không dùng V$SQL_BIND_CAPTURE để chứng minh mọi người dùng đã gửi giá trị gì trong từng request.

### 16.2. Bind values có thể nhạy cảm

Bind có thể chứa customer identifier, email, token hoặc dữ liệu cá nhân. Khi chia sẻ plan output:
- Ẩn giá trị nhạy cảm.
- Không gửi bind dump ra ticket/log công khai.
- Giới hạn quyền xem V$ views.
- Tuân thủ chính sách lưu giữ và audit dữ liệu.

### 16.3. Bind variables giảm injection nhưng không giải quyết mọi dynamic SQL

Bind cho giá trị là lớp bảo vệ quan trọng. Dynamic identifier vẫn cần allowlist/DBMS_ASSERT phù hợp. Không dùng cursor_sharing FORCE để thay thế bảo vệ đầu vào.

## 17. Quy trình chẩn đoán một SQL có bind và data skew

1. Lấy SQL_ID và child_number của câu lệnh thực tế.
2. Kiểm tra số child cursor, executions, parse_calls và plan_hash_value.
3. Kiểm tra IS_BIND_SENSITIVE và IS_BIND_AWARE.
4. Dùng DBMS_XPLAN.DISPLAY_CURSOR để xem operation, predicate, E-Rows/A-Rows, buffers và peeked binds.
5. Kiểm tra histogram, NDV, density, last_analyzed của cột predicate.
6. Kiểm tra bind datatype, length và implicit conversion.
7. Kiểm tra V$SQL_SHARED_CURSOR để biết child cursor không share vì lý do gì.
8. Kiểm tra V$SQL_CS_SELECTIVITY/STATISTICS/HISTOGRAM khi điều tra ACS.
9. Chạy thử các bind values đại diện cho phổ biến, hiếm và trung gian trong môi trường kiểm soát.
10. Đánh giá index, clustering factor, query shape và số hàng thực tế.
11. Chọn giải pháp: statistics, bind metadata, query split, index hoặc plan management.
12. Đo lại trên workload có concurrency và bind distribution tương đương thực tế.

## 18. Các lỗi và hiểu nhầm thường gặp

**“Dùng bind nghĩa là mọi execution dùng một plan duy nhất.”** Không. Một SQL_ID có thể có nhiều child cursor và nhiều plan.

**“Bind variable luôn làm query nhanh hơn.”** Không. Nó giảm parse overhead và hỗ trợ sharing, nhưng một plan dùng chung có thể không tối ưu cho mọi selectivity.

**“Giá trị bind đầu tiên chỉ ảnh hưởng execution đầu.”** Không. Giá trị peek lúc hard parse có thể ảnh hưởng kế hoạch được tái sử dụng sau đó.

**“Oracle peek bind ở mọi execution.”** Không. Bind peeking gắn với quá trình parse/optimization; cursor reuse không đồng nghĩa hard parse mỗi lần.

**“Histogram tự tạo index.”** Không. Histogram là statistics mô tả phân bố; index là access structure.

**“Có histogram thì ACS chắc chắn tạo nhiều child.”** Không. ACS cần điều kiện phù hợp và bằng chứng runtime.

**“Nhiều child cursor luôn là lỗi.”** Không. Một số child cần thiết cho bind-aware plans hoặc môi trường không tương thích.

**“CURSOR_SHARING FORCE tương đương ứng dụng bind đúng.”** Không. FORCE là biện pháp hệ thống thay literal trong nhiều câu SQL; ứng dụng vẫn nên bind giá trị rõ ràng.

**“FORCE giải quyết SQL injection.”** Không. Nó không bảo vệ dynamic identifier hoặc raw SQL construction.

**“V$SQL_BIND_CAPTURE ghi lại tất cả bind values.”** Không. Đây là cơ chế capture có lấy mẫu và giới hạn.

**“E-Rows là số hàng thật.”** Không. So sánh E-Rows với A-Rows để đánh giá sai lệch cardinality.

**“Tăng PGA hoặc flush shared pool là cách sửa bind peeking.”** Không. Cần xác định nguyên nhân selectivity, histogram, child cursor và workarea trước khi thay đổi cấu hình.

## 19. Bài thực hành

Dùng bảng ORDERS_SKEW ở mục 5 trong schema test.

### Bài 1 — So sánh literal SQL

Chạy hai câu SELECT khác nhau chỉ vì literal COMMON và RARE. Quan sát SQL_ID và số cursor trong V$SQL.

### Bài 2 — Dùng một bind variable

Chạy cùng SQL text với COMMON và RARE. So sánh parse_calls, executions và child_number.

### Bài 3 — Tạo histogram

Thu thập statistics với SIZE 254 cho STATUS. Xem USER_TAB_COL_STATISTICS và USER_TAB_HISTOGRAMS.

### Bài 4 — Quan sát bind peeking

Chạy truy vấn bind trong session test, xem DBMS_XPLAN.DISPLAY_CURSOR với PEEKED_BINDS. Thử các giá trị đầu tiên khác nhau trong môi trường độc lập.

### Bài 5 — Quan sát bind-sensitive

Chạy cùng SQL nhiều lần với các giá trị có selectivity khác nhau. Kiểm tra IS_BIND_SENSITIVE.

### Bài 6 — Quan sát bind-aware

Tiếp tục workload có phân bố bind khác nhau. Kiểm tra IS_BIND_AWARE, số child và plan hash value. Ghi nhận nếu ACS không kích hoạt.

### Bài 7 — Xem selectivity range

Truy vấn V$SQL_CS_SELECTIVITY cho SQL_ID. Liên hệ range với child cursor và bind values đã chạy.

### Bài 8 — Xem thống kê ACS

Truy vấn V$SQL_CS_STATISTICS và V$SQL_CS_HISTOGRAM. Ghi lại executions, rows processed và bucket nếu view có dữ liệu.

### Bài 9 — Kiểm tra child cursor mismatch

Truy vấn V$SQL_SHARED_CURSOR. So sánh BIND_MISMATCH, OPTIMIZER_MISMATCH và BIND_EQUIV_FAILURE.

### Bài 10 — Bind datatype

Từ JDBC, chạy một câu với setLong và một lần với setString cho khóa NUMBER trong schema test. Quan sát datatype, plan và child cursor. Sau đó sửa để dùng datatype nhất quán.

### Bài 11 — Optional predicate

So sánh một SQL dùng OR với hai SQL riêng cho trường hợp có/không có status filter. Đo plan và buffers.

### Bài 12 — Cursor sharing FORCE

Trong session test, so sánh EXACT và FORCE với nhiều literal variants. Ghi nhận số cursor và plan; khôi phục session setting sau thử nghiệm.

### Bài 13 — Thay đổi phân bố dữ liệu

Tăng tỷ lệ RARE hoặc đổi giá trị phổ biến. Thu thập statistics lại và quan sát histogram, cardinality estimate, child cursor.

### Bài 14 — Báo cáo tuning

Chọn một bind query có skew. Viết báo cáo gồm SQL_ID, bind distribution, histogram, child plans, actual rows, buffers, elapsed time và giải pháp được chọn. Không kết luận chỉ từ cost.

## 20. Tài liệu Oracle tham khảo

- [Oracle Database 19c SQL Tuning Guide — Adaptive Cursor Sharing](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/improving-rwp-cursor-sharing.html): bind peeking, bind-sensitive/bind-aware cursor và adaptive cursor sharing.
- [Oracle Database 19c SQL Tuning Guide — Managing SQL Plan Directives and Statistics](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): optimizer statistics, histograms và cardinality.
- [Oracle Database 19c SQL Language Reference — CURSOR_SHARING](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/CURSOR_SHARING.html): EXACT, FORCE và SIMILAR.
- [Oracle Database Reference — V$SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL.html): cursor, child cursor, execution và bind sensitivity flags.
- [Oracle Database Reference — V$SQL_SHARED_CURSOR](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_SHARED_CURSOR.html): lý do child cursor không share được.
- [Oracle Database Reference — V$SQL_CS_SELECTIVITY](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_CS_SELECTIVITY.html): selectivity ranges cho Adaptive Cursor Sharing.
- [Oracle Database Reference — V$SQL_CS_STATISTICS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_CS_STATISTICS.html): thống kê executions theo bind set.
- [Oracle Database Reference — V$SQL_BIND_CAPTURE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_BIND_CAPTURE.html): thông tin bind được capture.

Bind variables giúp Oracle tái sử dụng cursor và giảm hard parse, nhưng data skew khiến selectivity của cùng predicate thay đổi mạnh theo bind value. Bind peeking giúp optimizer chọn plan ban đầu từ giá trị được peek; histograms mô tả phân bố; Adaptive Cursor Sharing có thể tạo và chọn nhiều child cursor cho các selectivity range khác nhau. Khi điều tra, hãy xem SQL_ID, child cursor, bind metadata, histogram, E-Rows/A-Rows và runtime statistics. **Mục tiêu là giữ SQL text ổn định, bind đúng datatype và để optimizer có đủ thông tin chọn kế hoạch phù hợp với từng nhóm giá trị.**
