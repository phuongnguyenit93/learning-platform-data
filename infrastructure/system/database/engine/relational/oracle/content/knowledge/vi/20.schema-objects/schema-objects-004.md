# Complete refresh, fast refresh và materialized view log trong Oracle

Materialized view (MV) lưu kết quả của một truy vấn dưới dạng dữ liệu vật lý để có thể đọc lại nhanh hơn, giảm chi phí tính toán lặp lại cho báo cáo hoặc truy vấn tổng hợp. Vì dữ liệu nguồn có thể thay đổi sau khi MV được tạo, Oracle cần một cơ chế **refresh** để đồng bộ nội dung materialized view với các bảng gốc.

Oracle có hai chiến lược refresh quan trọng:

- **Complete refresh:** tính lại toàn bộ truy vấn định nghĩa MV và thay thế nội dung đã lưu.
- **Fast refresh:** chỉ áp dụng phần thay đổi kể từ lần refresh trước, dựa trên thông tin thay đổi được ghi trong materialized view log hoặc cơ chế hỗ trợ khác như Partition Change Tracking (PCT).

Để fast refresh hoạt động, truy vấn MV phải thuộc nhóm Oracle hỗ trợ và các bảng master phải có log phù hợp. Một materialized view log ghi lại thông tin cần thiết về các thay đổi INSERT, UPDATE, DELETE trên bảng nguồn. Thiết kế log không đầy đủ có thể khiến FAST refresh thất bại hoặc buộc hệ thống phải dùng complete refresh.

Bài học giải thích cách hai phương thức hoạt động, cấu hình ON DEMAND/ON COMMIT, tạo log, kiểm tra khả năng fast refresh, gọi DBMS_MVIEW.REFRESH, giám sát trạng thái và xử lý các vấn đề thường gặp.

## 1. Materialized view và nhu cầu refresh

View thông thường lưu câu truy vấn, không lưu sẵn tập kết quả. Mỗi lần truy vấn view, Oracle thực thi truy vấn dựa trên dữ liệu hiện tại của các bảng nguồn (subject to optimizer and execution plan).

Materialized view lưu kết quả truy vấn tại thời điểm build/refresh. Ví dụ, báo cáo doanh thu theo sản phẩm có thể cần join nhiều bảng và tính SUM trên hàng triệu giao dịch. Nếu nhiều báo cáo đọc cùng một phép tổng hợp, một MV có thể giúp tránh tính lại toàn bộ kết quả cho từng request.

~~~sql
CREATE MATERIALIZED VIEW sales_by_product_mv
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT product_id,
       SUM(amount) AS total_amount
FROM sales
GROUP BY product_id;
~~~

Sau khi tạo, MV chứa kết quả đã tính. Nếu bảng SALES có giao dịch mới, dữ liệu MV không tự thay đổi khi đang ở chế độ ON DEMAND; cần refresh theo lịch hoặc gọi thủ công.

### 1.1. Các thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa |
|---|---|
| Materialized view | Đối tượng lưu kết quả truy vấn |
| Master table/detail table | Bảng nguồn được truy vấn MV tham chiếu |
| Materialized view log | Đối tượng lưu dấu vết thay đổi trên bảng master để hỗ trợ fast refresh |
| Complete refresh | Tính lại toàn bộ nội dung MV |
| Fast refresh | Áp dụng thay đổi tăng dần từ lần refresh trước |
| Refresh mode | Khi nào refresh: ON DEMAND hoặc ON COMMIT |
| Refresh method | Cách refresh: COMPLETE, FAST, FORCE |
| Staleness | Mức độ mới/cũ của nội dung MV so với master tables |
| PCT | Partition Change Tracking, cơ chế có thể hỗ trợ refresh tăng dần trong một số MV phân vùng |

### 1.2. Refresh là đồng bộ dữ liệu, không phải query rewrite

Refresh cập nhật dữ liệu đã lưu trong MV. Query rewrite là khả năng optimizer thay một truy vấn trên bảng nguồn bằng cách đọc MV tương đương khi điều kiện phù hợp.

Hai chức năng liên quan nhưng khác nhau:

- Một MV có thể refresh thành công nhưng optimizer không dùng nó để rewrite truy vấn.
- Một MV có thể được cấu hình để rewrite nhưng nếu dữ liệu stale, việc sử dụng còn phụ thuộc các thiết lập freshness/consistency và chính sách rewrite.
- DBMS_MVIEW.REFRESH thực hiện refresh; DBMS_MVIEW.EXPLAIN_REWRITE hỗ trợ phân tích khả năng rewrite, không thay thế kiểm tra fast refresh.

## 2. Complete refresh

**Complete refresh** chạy lại truy vấn định nghĩa materialized view để tạo lại toàn bộ kết quả. Nó không cần materialized view log để xác định phần thay đổi tăng dần.

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'SALES_BY_PRODUCT_MV',
        method => 'C'
    );
END;
/
~~~

C là mã phương thức complete refresh.

### 2.1. Quy trình khái quát

~~~text
Bảng master thay đổi
        |
        v
Yêu cầu complete refresh
        |
        v
Oracle thực thi lại query định nghĩa MV
        |
        v
Tạo lại toàn bộ kết quả MV
        |
        v
Nội dung MV phản ánh dữ liệu nguồn tại thời điểm refresh
~~~

Complete refresh phải đọc và xử lý toàn bộ tập dữ liệu mà truy vấn MV cần. Với một MV tổng hợp trên bảng lớn, chi phí có thể gần với việc chạy lại truy vấn báo cáo gốc.

### 2.2. Ưu điểm

- Không phụ thuộc vào việc có log thay đổi đầy đủ hay không.
- Có thể dùng cho nhiều định nghĩa MV không đủ điều kiện fast refresh.
- Phù hợp khi dữ liệu nguồn ít, truy vấn định nghĩa đơn giản hoặc refresh không thường xuyên.
- Có thể dùng để tái tạo nội dung sau khi thay đổi định nghĩa hoặc khi cần đồng bộ toàn bộ.

### 2.3. Nhược điểm

- Có thể phải đọc, join, group và tính toán lại một lượng dữ liệu lớn.
- Thời gian refresh thường tăng theo kích thước dữ liệu nguồn và độ phức tạp truy vấn.
- Có thể sử dụng nhiều CPU, I/O, TEMP, undo/redo tùy phương thức thực thi và tùy chọn atomic.
- Nếu refresh chạy quá thường xuyên, tải tính lại toàn bộ có thể ảnh hưởng workload giao dịch.

### 2.4. Complete refresh không cần MV log

Nếu MV không có MV log hoặc định nghĩa không hỗ trợ fast refresh, complete refresh vẫn có thể chạy nếu truy vấn định nghĩa hợp lệ và các điều kiện khác được đáp ứng.

Điều này khiến complete refresh trở thành phương án đơn giản và có độ bao phủ rộng. Tuy nhiên, không nên chọn complete chỉ vì dễ cấu hình nếu dữ liệu rất lớn và yêu cầu refresh thường xuyên.

## 3. Fast refresh

**Fast refresh** cập nhật MV bằng cách áp dụng phần thay đổi từ các bảng master kể từ lần refresh trước, thay vì chạy lại toàn bộ truy vấn như complete refresh.

Đối với log-based fast refresh, Oracle đọc dữ liệu thay đổi từ materialized view log. Với một số trường hợp, Oracle có thể sử dụng cơ chế khác như Partition Change Tracking nếu MV và thao tác phân vùng thỏa điều kiện.

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'SALES_BY_PRODUCT_MV',
        method => 'F'
    );
END;
/
~~~

F yêu cầu fast refresh. Nếu MV không đủ điều kiện hoặc thiếu thông tin log cần thiết, lệnh có thể thất bại; Oracle không tự chuyển sang complete chỉ vì ta đã chỉ định F.

### 3.1. Fast refresh làm gì?

Giả sử MV đã lưu doanh thu theo sản phẩm:

| Product | Total amount |
|---|---:|
| P01 | 1000 |
| P02 | 700 |

Sau đó bảng nguồn nhận một giao dịch mới cho P01 trị giá 100 và một giao dịch mới cho P03 trị giá 250.

Fast refresh có thể áp dụng phần thay đổi để đưa MV về:

| Product | Total amount |
|---|---:|
| P01 | 1100 |
| P02 | 700 |
| P03 | 250 |

Thay vì quét lại toàn bộ lịch sử giao dịch để tính lại mọi sản phẩm, Oracle dùng thông tin thay đổi và thuật toán phù hợp với định nghĩa MV.

### 3.2. Ưu điểm

- Thường giảm lượng dữ liệu phải xử lý khi tỷ lệ thay đổi nhỏ so với toàn bộ dữ liệu.
- Có thể phù hợp với MV lớn cần refresh thường xuyên.
- Hỗ trợ các báo cáo gần dữ liệu nguồn hơn mà không phải complete refresh mỗi lần.
- Khi thiết kế đúng, chi phí refresh chủ yếu gắn với phần thay đổi và chi phí duy trì log.

### 3.3. Nhược điểm và điều kiện

- Không phải mọi truy vấn đều hỗ trợ fast refresh.
- Cần materialized view log có đúng khóa/cột/thông tin cần thiết, hoặc cơ chế PCT đủ điều kiện.
- MV log làm tăng chi phí DML trên bảng master và sử dụng thêm storage.
- Query có join, aggregate, analytic function, set operator hoặc cấu trúc phức tạp có thể bị hạn chế tùy loại MV và phiên bản.
- Nếu thay đổi định nghĩa MV hoặc bảng nguồn, khả năng fast refresh cần được kiểm tra lại.

### 3.4. Fast refresh không có nghĩa chỉ đọc đúng số dòng vừa thay đổi

Một thay đổi ở bảng master có thể ảnh hưởng nhiều nhóm hoặc nhiều kết quả MV. Ví dụ, cập nhật một sản phẩm từ category A sang B có thể làm thay đổi hai nhóm tổng hợp. Fast refresh phải tính đúng phần bị ảnh hưởng; lượng công việc không nhất thiết bằng số dòng DML ở bảng nguồn.

## 4. FORCE refresh và lựa chọn phương thức

Oracle hỗ trợ các phương thức refresh phổ biến:

| Method | Ý nghĩa |
|---|---|
| COMPLETE (C) | Luôn yêu cầu complete refresh |
| FAST (F) | Yêu cầu fast refresh; không đủ điều kiện thì báo lỗi |
| FORCE (?) | Thử fast refresh nếu có thể; nếu không thì dùng complete refresh |

Ví dụ:

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'SALES_BY_PRODUCT_MV',
        method => '?'
    );
END;
/
~~~

FORCE tiện khi muốn Oracle chọn phương án khả dụng, nhưng cần lưu ý một điểm vận hành: refresh có thể âm thầm chuyển sang complete và tốn thời gian hơn dự kiến. Hãy kiểm tra LAST_REFRESH_TYPE sau khi chạy để biết phương thức thực tế.

Nếu SLA yêu cầu refresh phải hoàn tất trong thời gian ngắn và chỉ chấp nhận fast refresh, hãy yêu cầu FAST rõ ràng và giám sát lỗi. Nếu chấp nhận complete refresh như fallback, hãy dùng FORCE nhưng theo dõi thời gian và loại refresh thực tế.

## 5. So sánh COMPLETE, FAST và FORCE

| Tiêu chí | COMPLETE | FAST | FORCE |
|---|---|---|---|
| Cách làm | Tính lại toàn bộ query | Áp dụng phần thay đổi | Thử FAST, fallback COMPLETE |
| Cần MV log | Không bắt buộc | Thường cần cho log-based fast refresh; có thể dùng PCT trong trường hợp hỗ trợ | Chỉ cần nếu đường FAST được chọn |
| Điều kiện query | Rộng hơn | Phải thỏa fast refresh capability | Chấp nhận cả hai; kết quả phụ thuộc khả năng |
| Chi phí | Có thể cao với dữ liệu lớn | Thường thấp hơn khi thay đổi ít, nhưng phụ thuộc workload | Không cố định |
| Hành vi khi FAST không khả dụng | Không liên quan | Báo lỗi | Chạy COMPLETE |
| Trường hợp phù hợp | MV nhỏ, ít refresh, định nghĩa phức tạp | MV lớn, thay đổi tăng dần, có log/PCT phù hợp | Muốn fallback tự động và chấp nhận biến động thời gian |

Không có một phương thức tốt nhất cho mọi hệ thống. Hãy đo trên dữ liệu thật hoặc dữ liệu mô phỏng đủ đại diện, kiểm tra thời gian refresh, chi phí DML do log và yêu cầu freshness của báo cáo.

## 6. Materialized view log là gì?

**Materialized view log** là đối tượng Oracle tạo trên bảng master để ghi nhận thông tin về các thay đổi cần thiết cho fast refresh của những materialized view phụ thuộc.

Mỗi bảng master có thể có materialized view log dùng chung cho các MV phụ thuộc phù hợp. Log không phải bản sao đầy đủ của bảng; nó lưu các thông tin cần thiết để Oracle xác định và áp dụng thay đổi.

### 6.1. Log ghi nhận thay đổi DML

Các thao tác có thể được ghi nhận bao gồm:

- INSERT: hàng mới được thêm.
- UPDATE: hàng thay đổi; có thể cần giá trị cũ/mới hoặc các cột liên quan.
- DELETE: hàng bị xóa.
- Một số kiểu thao tác nạp dữ liệu hoặc thao tác phân vùng có cơ chế hỗ trợ riêng.

Thông tin cụ thể được lưu phụ thuộc cách tạo log, ví dụ ROWID, PRIMARY KEY, SEQUENCE, danh sách cột và INCLUDING NEW VALUES.

### 6.2. Log không tự refresh materialized view

Tạo MV log không làm MV tự cập nhật ngay sau mỗi DML. Log chỉ ghi nhận thay đổi. MV vẫn cần refresh theo một trong các cơ chế:

- REFRESH ON DEMAND: refresh khi ứng dụng, DBA hoặc scheduler gọi.
- REFRESH ON COMMIT: refresh khi transaction thay đổi bảng master commit, nếu loại MV hỗ trợ.
- Refresh theo lịch bằng job hoặc DBMS_SCHEDULER.

### 6.3. MV log làm tăng chi phí ghi dữ liệu

Mỗi DML trên bảng master có thể phải ghi thêm thông tin vào MV log. Vì vậy, log có thể làm tăng:

- redo/undo và I/O;
- dung lượng lưu trữ;
- thời gian DML/commit;
- công việc purge log sau refresh.

Trước khi tạo log cho một bảng giao dịch có throughput cao, cần đánh giá overhead và nhu cầu fast refresh thực tế.

## 7. Tạo materialized view log

Cú pháp khái quát:

~~~sql
CREATE MATERIALIZED VIEW LOG ON master_table
    [WITH [PRIMARY KEY] [ROWID] [SEQUENCE] [(column_list)]]
    [INCLUDING NEW VALUES];
~~~

Các thành phần thường gặp:

- PRIMARY KEY: ghi thông tin khóa chính để định danh hàng thay đổi.
- ROWID: ghi ROWID của hàng master.
- SEQUENCE: ghi sequence information để phân biệt thứ tự các thay đổi trong một số kịch bản fast refresh.
- (column_list): chỉ định các cột bổ sung cần ghi trong log.
- INCLUDING NEW VALUES: yêu cầu lưu giá trị mới trong log, thường cần cho các trường hợp fast refresh của aggregate MV và các định nghĩa cần thông tin new values.

Không có một cấu hình log duy nhất đúng cho mọi MV. Cần dựa vào định nghĩa truy vấn, loại MV, khóa master, aggregate, join và capability mà Oracle báo.

### 7.1. Log theo primary key

~~~sql
CREATE MATERIALIZED VIEW LOG ON products
WITH PRIMARY KEY;
~~~

Log chứa thông tin khóa chính của bảng PRODUCTS. Cách này phù hợp khi MV sử dụng cơ chế định danh theo primary key và định nghĩa hỗ trợ tương ứng.

Bảng master cần có primary key hợp lệ nếu cấu hình yêu cầu primary key. Nếu không có primary key, không thể giả định WITH PRIMARY KEY sẽ hoạt động như mong muốn.

### 7.2. Log theo ROWID

~~~sql
CREATE MATERIALIZED VIEW LOG ON sales
WITH ROWID;
~~~

ROWID giúp nhận diện hàng vật lý trong bảng master. Rowid-based materialized view có thể sử dụng log này trong những trường hợp Oracle hỗ trợ.

ROWID không phải khóa nghiệp vụ ổn định để ứng dụng lưu lâu dài. Nó là định danh hàng do Oracle quản lý và có thể thay đổi trong một số thao tác di chuyển/tổ chức lại dữ liệu. Dùng ROWID theo yêu cầu refresh của Oracle, không dùng như business key.

### 7.3. Log có SEQUENCE

~~~sql
CREATE MATERIALIZED VIEW LOG ON sales
WITH ROWID, SEQUENCE;
~~~

SEQUENCE bổ sung thông tin thứ tự thay đổi. Nó có thể cần khi fast refresh phải phân biệt nhiều thao tác trên cùng một hàng hoặc xử lý các tình huống DML phức tạp theo yêu cầu của thuật toán refresh.

Không phải mọi MV đều bắt buộc có SEQUENCE; hãy xác nhận bằng tài liệu và EXPLAIN_MVIEW cho đúng định nghĩa.

### 7.4. Log ghi các cột được tham chiếu

~~~sql
CREATE MATERIALIZED VIEW LOG ON sales
WITH ROWID, SEQUENCE
    (product_id, sale_date, amount)
INCLUDING NEW VALUES;
~~~

Ví dụ log lưu ROWID, sequence và các cột PRODUCT_ID, SALE_DATE, AMOUNT, đồng thời ghi new values.

Danh sách cột cần dựa trên các cột mà định nghĩa MV sử dụng, bao gồm cột trong select list, filter, join, group by và aggregate. Một log thiếu cột cần thiết có thể làm fast refresh không khả dụng.

### 7.5. Một bảng master có nhiều MV phụ thuộc

Nhiều materialized view có thể phụ thuộc cùng một bảng master và dùng chung MV log. Không tạo một log mới cho mỗi MV. Khi thêm một MV mới, cần kiểm tra log hiện có đã chứa đủ thông tin cho tất cả MV phụ thuộc hay chưa.

Nếu cần bổ sung cột hoặc thuộc tính log, phải dùng cú pháp quản lý MV log được Oracle hỗ trợ và kiểm tra ảnh hưởng tới các MV hiện tại. Thay đổi log có thể ảnh hưởng refresh của các MV phụ thuộc; không sửa tùy tiện trên production.

## 8. INCLUDING NEW VALUES và aggregate materialized view

Aggregate MV thường cần nhiều thông tin hơn MV chỉ chọn hàng. Ví dụ:

~~~sql
SELECT product_id,
       SUM(amount) AS total_amount
FROM sales
GROUP BY product_id;
~~~

Khi một giao dịch thay đổi amount hoặc product, Oracle phải biết ảnh hưởng tới nhóm cũ và nhóm mới. Với update, chỉ lưu thông tin hàng thay đổi mà không có đủ giá trị cần thiết có thể không đủ để cập nhật aggregate chính xác.

INCLUDING NEW VALUES cho phép log ghi nhận giá trị mới trong các trường hợp cần thiết cho fast refresh. Khi thiết kế aggregate MV, cần xem xét:

- Tất cả cột tham gia GROUP BY.
- Cột được dùng trong aggregate expression.
- Cột trong điều kiện lọc.
- Cột join nếu truy vấn có join.
- COUNT(*) và các biểu thức đếm cần thiết để xử lý insert/delete/update.
- SUM và các thành phần cần để duy trì AVG.

Ví dụ aggregate MV có thể khai báo:

~~~sql
CREATE MATERIALIZED VIEW LOG ON sales
WITH ROWID, SEQUENCE
    (product_id, amount)
INCLUDING NEW VALUES;
~~~

Đây là mẫu minh họa; cấu hình log cuối cùng phải được xác minh theo định nghĩa MV và release Oracle đang chạy.

## 9. Fast refresh với aggregate: vì sao cần COUNT và SUM?

Giả sử MV lưu:

~~~sql
SELECT product_id,
       SUM(amount) AS total_amount,
       AVG(amount) AS average_amount
FROM sales
GROUP BY product_id;
~~~

Để duy trì aggregate sau insert, delete hoặc update, Oracle cần đủ thông tin để cập nhật tổng và số lượng.

AVG(amount) có thể được biểu diễn về mặt toán học bằng:

~~~text
AVG(amount) = SUM(amount) / COUNT(amount)
~~~

Do đó, một aggregate MV hỗ trợ fast refresh thường cần lưu các thành phần aggregate phù hợp, ví dụ:

~~~sql
SELECT product_id,
       COUNT(*) AS row_count,
       COUNT(amount) AS amount_count,
       SUM(amount) AS total_amount,
       SUM(amount * amount) AS sum_amount_squared
FROM sales
GROUP BY product_id;
~~~

Danh sách aggregate cần thiết phụ thuộc các hàm được sử dụng và capability. Không nên tự suy ra rằng chỉ thêm SUM là đủ cho mọi AVG, variance hoặc aggregate khác. Dùng DBMS_MVIEW.EXPLAIN_MVIEW để kiểm tra chính xác.

### 9.1. COUNT(*) và COUNT(column)

Hai biểu thức khác nhau:

- COUNT(*): đếm tất cả hàng.
- COUNT(amount): chỉ đếm hàng có AMOUNT không null.

Nếu cột aggregate cho phép null, Oracle cần phân biệt số hàng với số giá trị hợp lệ. Đây là lý do aggregate MV có thể cần cả hai.

### 9.2. AVG cần thành phần duy trì

Về bản chất:

~~~text
AVG(amount) = SUM(amount) / COUNT(amount)
~~~

Khi xóa một hàng, chỉ biết tổng mới mà không biết số lượng giá trị còn lại thì không thể tính lại average chính xác. Vì thế fast refresh aggregate cần các thành phần hỗ trợ phù hợp.

## 10. Ví dụ hoàn chỉnh: bảng nguồn, log và aggregate MV

Ví dụ sau minh họa một aggregate MV trên một bảng giao dịch. Thực hiện trong schema DEV/TEST, không dùng bảng nghiệp vụ thật.

### 10.1. Tạo bảng nguồn

~~~sql
CREATE TABLE lab_sales (
    sale_id    NUMBER PRIMARY KEY,
    product_id NUMBER NOT NULL,
    sale_date  DATE NOT NULL,
    amount     NUMBER(12, 2)
);

INSERT ALL
    INTO lab_sales VALUES (1, 101, DATE '2026-01-01', 100)
    INTO lab_sales VALUES (2, 101, DATE '2026-01-02', 150)
    INTO lab_sales VALUES (3, 102, DATE '2026-01-01', 200)
    INTO lab_sales VALUES (4, 102, DATE '2026-01-03', 50)
SELECT 1 FROM dual;

COMMIT;
~~~

### 10.2. Tạo materialized view log

~~~sql
CREATE MATERIALIZED VIEW LOG ON lab_sales
WITH ROWID, SEQUENCE
    (product_id, sale_date, amount)
INCLUDING NEW VALUES;
~~~

Log ghi nhận thay đổi trên bảng LAB_SALES. Các cột được nêu để hỗ trợ định nghĩa aggregate MV bên dưới.

### 10.3. Tạo aggregate MV

~~~sql
CREATE MATERIALIZED VIEW lab_sales_by_product_mv
BUILD IMMEDIATE
REFRESH FAST ON DEMAND
AS
SELECT product_id,
       COUNT(*) AS row_count,
       COUNT(amount) AS amount_count,
       SUM(amount) AS total_amount,
       AVG(amount) AS average_amount
FROM lab_sales
GROUP BY product_id;
~~~

Đây là mẫu minh họa fast-refreshable aggregate MV. Khả năng fast refresh thực tế còn phụ thuộc release, cú pháp, log, aggregate và các giới hạn khác; hãy chạy EXPLAIN_MVIEW trước khi đưa vào vận hành.

### 10.4. Xem dữ liệu MV ban đầu

~~~sql
SELECT product_id,
       row_count,
       amount_count,
       total_amount,
       average_amount
FROM lab_sales_by_product_mv
ORDER BY product_id;
~~~

Kết quả ban đầu:

| Product | Row count | Amount count | Total amount | Average amount |
|---:|---:|---:|---:|---:|
| 101 | 2 | 2 | 250 | 125 |
| 102 | 2 | 2 | 250 | 125 |

### 10.5. Thay đổi bảng nguồn

~~~sql
INSERT INTO lab_sales
    (sale_id, product_id, sale_date, amount)
VALUES
    (5, 101, DATE '2026-01-04', 50);

UPDATE lab_sales
SET amount = 100
WHERE sale_id = 3;

COMMIT;
~~~

Sau commit, MV ở chế độ ON DEMAND chưa nhất thiết được cập nhật. Nội dung MV có thể đang stale cho tới khi refresh.

### 10.6. Chạy fast refresh

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'LAB_SALES_BY_PRODUCT_MV',
        method => 'F'
    );
END;
/
~~~

Đọc lại:

~~~sql
SELECT product_id,
       row_count,
       amount_count,
       total_amount,
       average_amount
FROM lab_sales_by_product_mv
ORDER BY product_id;
~~~

Kết quả mong đợi sau refresh:

| Product | Row count | Amount count | Total amount | Average amount |
|---:|---:|---:|---:|---:|
| 101 | 3 | 3 | 300 | 100 |
| 102 | 2 | 2 | 150 | 75 |

### 10.7. Thử complete refresh để đối chiếu

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'LAB_SALES_BY_PRODUCT_MV',
        method => 'C'
    );
END;
/
~~~

Kết quả cuối phải phản ánh dữ liệu nguồn tương tự fast refresh nếu cả hai phương thức chạy thành công và cùng thời điểm dữ liệu. Sự khác nhau nằm ở cách Oracle tính lại nội dung, không phải ý nghĩa kết quả truy vấn.

## 11. ON DEMAND và ON COMMIT

Refresh method (FAST, COMPLETE, FORCE) trả lời câu hỏi **refresh bằng cách nào**. Refresh mode (ON DEMAND, ON COMMIT) trả lời câu hỏi **refresh vào lúc nào**.

### 11.1. ON DEMAND

~~~sql
CREATE MATERIALIZED VIEW sales_by_product_mv
BUILD IMMEDIATE
REFRESH FAST ON DEMAND
AS
SELECT product_id,
       COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM sales
GROUP BY product_id;
~~~

MV được refresh khi được gọi tường minh hoặc theo lịch job. Đây là lựa chọn phổ biến cho báo cáo có thể chấp nhận dữ liệu trễ vài phút hoặc vài giờ.

Có thể lên lịch bằng DBMS_SCHEDULER hoặc cơ chế scheduling phù hợp của hệ thống. Nên dùng một lịch có kiểm soát, giám sát lỗi và tránh refresh chồng lấn.

### 11.2. ON COMMIT

~~~sql
CREATE MATERIALIZED VIEW sales_by_product_mv
BUILD IMMEDIATE
REFRESH FAST ON COMMIT
AS
SELECT product_id,
       COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM sales
GROUP BY product_id;
~~~

Khi transaction thay đổi bảng master commit, Oracle thực hiện refresh MV theo chế độ được khai báo nếu định nghĩa được hỗ trợ.

Ưu điểm:
- MV được đồng bộ ngay theo transaction commit (khi refresh thành công).
- Ứng dụng không cần tự lên lịch refresh sau mỗi batch thay đổi.

Nhược điểm:
- Commit của transaction master có thể tốn thêm thời gian.
- DML throughput có thể bị ảnh hưởng bởi chi phí duy trì MV.
- Không phù hợp với mọi định nghĩa MV hoặc mọi workload.
- Một transaction cập nhật nhiều bảng/nhóm có thể làm refresh tại commit trở nên nặng.

Không chọn ON COMMIT chỉ vì muốn dữ liệu “luôn mới”. Hãy đánh giá latency commit, số DML, độ phức tạp MV và giới hạn fast refresh.

### 11.3. ON DEMAND kết hợp scheduler

Với hệ thống báo cáo, một lựa chọn là refresh định kỳ:

~~~sql
BEGIN
    DBMS_SCHEDULER.CREATE_JOB(
        job_name        => 'REFRESH_SALES_MV_JOB',
        job_type        => 'PLSQL_BLOCK',
        job_action      => q'[
            BEGIN
                DBMS_MVIEW.REFRESH(
                    list   => 'SALES_BY_PRODUCT_MV',
                    method => 'F'
                );
            END;
        ]',
        start_date      => SYSTIMESTAMP,
        repeat_interval => 'FREQ=MINUTELY;INTERVAL=15',
        enabled         => TRUE
    );
END;
/
~~~

Ví dụ tạo job mỗi 15 phút. Cần điều chỉnh repeat_interval, quyền và lịch theo hệ thống. Trước khi tạo job production, hãy kiểm tra job cùng tên đã tồn tại chưa, chính sách vận hành, thời gian refresh và khả năng job trước chưa hoàn tất khi lần tiếp theo đến.

## 12. BUILD IMMEDIATE và BUILD DEFERRED

Ngoài refresh mode, lúc tạo MV còn có tùy chọn build:

- BUILD IMMEDIATE: thực thi truy vấn ngay để nạp dữ liệu ban đầu.
- BUILD DEFERRED: tạo metadata MV trước; nội dung được nạp ở lần refresh phù hợp sau đó.

Ví dụ:

~~~sql
CREATE MATERIALIZED VIEW sales_by_product_mv
BUILD DEFERRED
REFRESH FAST ON DEMAND
AS
SELECT product_id,
       COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM sales
GROUP BY product_id;
~~~

Sau đó có thể gọi refresh để build dữ liệu nếu định nghĩa hỗ trợ phương thức được chọn:

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'SALES_BY_PRODUCT_MV',
        method => '?'
    );
END;
/
~~~

BUILD DEFERRED không có nghĩa MV đã chứa kết quả dùng được ngay. Trước lần refresh đầu, MV có thể chưa có dữ liệu; ứng dụng cần quản lý trạng thái sẵn sàng.

## 13. Kiểm tra khả năng FAST REFRESH với EXPLAIN_MVIEW

Không nên đoán fast refresh có được hỗ trợ chỉ dựa trên việc MV tạo thành công. Oracle cung cấp package DBMS_MVIEW.EXPLAIN_MVIEW để phân tích khả năng refresh của một materialized view hoặc định nghĩa truy vấn.

### 13.1. Chuẩn bị bảng capability

Trong nhiều môi trường, cần tạo bảng MV_CAPABILITIES_TABLE bằng script Oracle utlxmv.sql từ thư mục admin của Oracle Home. Việc chạy script này cần quyền và quy trình quản trị phù hợp; không chạy script quản trị trên production nếu chưa được DBA phê duyệt.

Sau khi bảng đã có, gọi:

~~~sql
BEGIN
    DBMS_MVIEW.EXPLAIN_MVIEW('LAB_SALES_BY_PRODUCT_MV');
END;
/
~~~

### 13.2. Đọc kết quả

~~~sql
SELECT capability_name,
       possible,
       related_text,
       msgtxt
FROM mv_capabilities_table
ORDER BY seq;
~~~

Các cột quan trọng:

- CAPABILITY_NAME: khả năng Oracle đang phân tích.
- POSSIBLE: Y hoặc N, cho biết khả năng đó có được hỗ trợ trong ngữ cảnh phân tích hay không.
- RELATED_TEXT: thành phần truy vấn liên quan, nếu có.
- MSGTXT: giải thích hoặc lý do capability không khả dụng.

Tập kết quả có thể chứa nhiều dòng cho các capability khác nhau, không chỉ một dòng FAST. Đọc các dòng liên quan tới fast refresh, join, aggregate và PCT.

### 13.3. Phân tích định nghĩa trước khi tạo MV

EXPLAIN_MVIEW cũng có thể nhận câu query/DDL theo overload được tài liệu hóa. Cách này hữu ích khi thiết kế MV trước khi tạo object. Kiểm tra chữ ký package của release đang dùng và quyền thực thi DBMS_MVIEW.

### 13.4. EXPLAIN_MVIEW không thay thế thử nghiệm refresh

Capability analysis cho biết Oracle đánh giá định nghĩa có khả năng hỗ trợ hay không trong điều kiện hiện tại. Sau khi tạo MV/log, vẫn nên thử các loại DML thực tế (INSERT, UPDATE, DELETE, thay đổi khóa join, null, nhiều DML trên một hàng), chạy fast refresh và xác minh kết quả.

## 14. Giám sát trạng thái materialized view

Các data dictionary views hữu ích:

- USER_MVIEWS: materialized views thuộc schema hiện tại.
- ALL_MVIEWS: materialized views mà user có quyền truy cập.
- DBA_MVIEWS: toàn bộ MV trong database, cần quyền DBA.
- USER_MVIEW_LOGS/ALL_MVIEW_LOGS/DBA_MVIEW_LOGS: thông tin materialized view log.
- USER_MVIEW_DETAIL_RELATIONS: thông tin quan hệ detail/master của MV, tùy quyền và phiên bản.

### 14.1. Xem phương thức và lần refresh gần nhất

~~~sql
SELECT mview_name,
       refresh_mode,
       refresh_method,
       last_refresh_type,
       last_refresh_date,
       staleness,
       compile_state
FROM user_mviews
ORDER BY mview_name;
~~~

Các cột giúp xác định:
- MV được cấu hình refresh theo mode nào.
- Phương thức cấu hình.
- Phương thức thực tế của lần refresh gần nhất.
- Thời điểm refresh.
- Trạng thái fresh/stale.
- Trạng thái compile của MV.

Tên/cột hiển thị có thể khác theo release hoặc view tương ứng; kiểm tra dictionary của database đang sử dụng.

### 14.2. Xem materialized view log

~~~sql
SELECT log_table,
       master,
       rowids,
       primary_key,
       sequence,
       include_new_values
FROM user_mview_logs
ORDER BY master;
~~~

View cho biết các thuộc tính log chính, giúp DBA kiểm tra log có được tạo theo đúng dự kiến hay không.

### 14.3. Kiểm tra freshness

Một MV có thể được báo là FRESH, STALE hoặc trạng thái khác tùy metadata và cách Oracle đánh giá. Không nên chỉ dựa vào thời gian refresh để kết luận dữ liệu luôn fresh; master có thể thay đổi sau thời điểm refresh.

Ứng dụng cần xác định freshness requirement:
- Báo cáo tài chính có thể yêu cầu refresh thành công tới một watermark cụ thể.
- Dashboard vận hành có thể chấp nhận dữ liệu trễ 5–15 phút.
- Dữ liệu tra cứu tham khảo có thể chấp nhận trễ lâu hơn.

Freshness là yêu cầu nghiệp vụ, không chỉ là một cột trạng thái.

## 15. ATOMIC_REFRESH và ảnh hưởng tới tính sẵn sàng

DBMS_MVIEW.REFRESH có tham số atomic_refresh. Tham số này điều khiển cách Oracle thực hiện refresh và tính nguyên tử khi refresh một hoặc nhiều MV.

Ví dụ:

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list           => 'LAB_SALES_BY_PRODUCT_MV',
        method         => 'C',
        atomic_refresh => TRUE
    );
END;
/
~~~

### 15.1. Atomic refresh = TRUE

Khi yêu cầu atomic refresh, Oracle duy trì tính nguyên tử theo transaction của thao tác refresh theo phạm vi API. Với complete refresh, cách thực hiện thường phải dùng thao tác DML để thay nội dung thay vì truncate không thể rollback như DML.

Ưu điểm:
- Giảm nguy cơ người đọc nhìn thấy trạng thái MV bị xóa sạch giữa quá trình complete refresh.
- Nếu refresh thất bại, Oracle có thể rollback các thay đổi refresh trong transaction theo cơ chế hỗ trợ.
- Khi refresh nhiều MV trong cùng lần gọi, có thể giữ tính nhất quán atomic theo phạm vi được hỗ trợ.

Nhược điểm:
- Có thể sử dụng thêm undo/redo và tài nguyên.
- Complete refresh có thể chậm hơn so với đường thực thi không atomic.

### 15.2. Atomic refresh = FALSE

Với complete refresh, Oracle có thể sử dụng TRUNCATE rồi nạp lại dữ liệu để tăng tốc. Vì truncate là DDL có implicit commit trong Oracle, không thể rollback như một thao tác DELETE thông thường.

Ưu điểm:
- Có thể giảm chi phí so với xóa từng hàng bằng DML.
- Có thể phù hợp khi MV rất lớn và khoảng thời gian MV không sẵn sàng đã được chấp nhận.

Rủi ro:
- Refresh không còn atomic theo cách của TRUE.
- Nếu quá trình nạp lại thất bại sau khi nội dung cũ bị truncate, MV có thể không có đầy đủ dữ liệu cho tới khi refresh thành công lại.
- Khi refresh nhiều MV, người đọc có thể quan sát trạng thái các MV không đồng thời nhất quán.

Không đặt atomic_refresh => FALSE chỉ để tăng tốc mà không đánh giá ảnh hưởng tới người đọc và kế hoạch phục hồi.

### 15.3. Atomic refresh khác autocommit của JDBC

ATOMIC_REFRESH là tham số của API refresh Oracle; Connection.setAutoCommit là trạng thái transaction của JDBC connection. Chúng liên quan đến transaction boundary nhưng không phải cùng một khái niệm. Khi gọi DBMS_MVIEW.REFRESH từ JDBC, cần hiểu API refresh và transaction behavior của Oracle, không giả định setAutoCommit(false) sẽ biến một thao tác DDL/refresh không atomic thành atomic.

## 16. PCT: Partition Change Tracking

Với bảng master được partition và materialized view đáp ứng các điều kiện phù hợp, Oracle có thể sử dụng **Partition Change Tracking (PCT)** để refresh nhanh dựa trên các partition bị thay đổi.

PCT không đơn giản là một materialized view log khác. Nó dựa vào quan hệ partition giữa bảng detail và MV, cùng các điều kiện về partitioning/định nghĩa truy vấn mà Oracle hỗ trợ.

PCT có thể hữu ích khi:
- Dữ liệu được nạp hoặc thay đổi theo partition.
- Một số partition được thay thế/trao đổi trong khi phần còn lại không đổi.
- MV có cấu trúc cho phép Oracle xác định phần kết quả bị ảnh hưởng bởi partition change.

Các thao tác như TRUNCATE PARTITION, EXCHANGE PARTITION, DROP PARTITION có thể tác động tới khả năng refresh và freshness của MV. Không giả định mọi thao tác partition maintenance đều tự động fast refresh được. Dùng EXPLAIN_MVIEW, kiểm tra tài liệu PCT theo release và thử quy trình partition maintenance trong môi trường tương ứng.

## 17. Materialized view log và vòng đời dữ liệu thay đổi

MV log phải giữ đủ thay đổi để các MV phụ thuộc có thể refresh. Khi một MV refresh thành công, Oracle quản lý việc purge log theo trạng thái của các MV phụ thuộc và cấu hình liên quan.

Không nên tự xóa/truncate bảng log nội bộ của Oracle để “dọn dung lượng”. Hãy quản lý log bằng các câu lệnh materialized view log được hỗ trợ và kiểm tra MV phụ thuộc.

### 17.1. DML liên tục và log tăng dung lượng

Nếu bảng master có nhiều DML nhưng MV không refresh trong thời gian dài, log có thể tích lũy nhiều dòng thay đổi. Hệ quả:
- Tốn dung lượng.
- Fast refresh sau thời gian dài có thể phải xử lý lượng thay đổi lớn.
- Thời gian refresh tăng.
- DML tiếp tục chịu chi phí ghi log.

Giải pháp thường là lịch refresh phù hợp, theo dõi dung lượng và kiểm soát MV phụ thuộc bị bỏ quên.

### 17.2. Nhiều MV dùng chung một log

Nếu một master table có nhiều MV phụ thuộc, log cần giữ thông tin cho các MV đó. Một MV refresh xong không có nghĩa mọi thay đổi có thể được purge nếu còn MV khác chưa refresh. Khi một MV cũ bị bỏ lại, log có thể phải giữ nhiều thay đổi hơn.

### 17.3. Xóa materialized view log

Khi chắc chắn không còn MV nào cần log và đã đánh giá ảnh hưởng, có thể dùng:

~~~sql
DROP MATERIALIZED VIEW LOG ON sales;
~~~

Đây là DDL ảnh hưởng tới khả năng fast refresh của các MV phụ thuộc. Sau khi xóa log, các MV có thể cần complete refresh hoặc tạo lại log phù hợp trước khi fast refresh tiếp tục. Không xóa log để giải phóng dung lượng nếu chưa kiểm tra dependency.

## 18. Thay đổi bảng master và tác động tới fast refresh

Các thay đổi schema hoặc thao tác dữ liệu đặc biệt có thể làm MV mất khả năng fast refresh hoặc cần refresh lại toàn bộ.

Ví dụ:
- Thay đổi cột được dùng trong MV.
- Thay đổi khóa chính/unique key.
- Thay đổi định nghĩa truy vấn.
- Thay đổi partitioning hoặc thực hiện partition maintenance.
- Một số thao tác direct-path load hoặc bulk operation.
- Drop/recreate log hoặc thay đổi thuộc tính log.

Sau thay đổi, cần:
1. Kiểm tra trạng thái MV và log.
2. Chạy EXPLAIN_MVIEW.
3. Thử fast refresh trong DEV/TEST.
4. Nếu fast refresh không khả dụng, đánh giá complete refresh và thời gian cần thiết.
5. Lên kế hoạch refresh/availability trước khi áp dụng production.

## 19. Lựa chọn chiến lược refresh theo workload

| Tình huống | Chiến lược thường cân nhắc |
|---|---|
| MV nhỏ, nguồn thay đổi ít | COMPLETE ON DEMAND |
| MV lớn, thay đổi ít và truy vấn đủ điều kiện | FAST ON DEMAND |
| MV cần cập nhật cùng commit nguồn, DML không quá nặng | FAST ON COMMIT nếu được hỗ trợ và đã đo |
| MV có thể fast refresh nhưng cần fallback | FORCE ON DEMAND và giám sát LAST_REFRESH_TYPE |
| Dữ liệu nạp theo partition, MV hỗ trợ PCT | Đánh giá PCT/fast refresh |
| Import hàng loạt theo lịch | FAST hoặc COMPLETE theo khả năng và tỷ lệ thay đổi; chạy sau batch |
| Báo cáo chấp nhận trễ 15 phút | ON DEMAND theo lịch |
| Hệ thống OLTP có commit latency nghiêm ngặt | Cân nhắc tránh ON COMMIT nếu refresh làm tăng thời gian commit |

Một cách chọn phương thức thực tế:
- Ước lượng số hàng master và tỷ lệ thay đổi giữa các lần refresh.
- Đo thời gian complete refresh.
- Đo thời gian fast refresh sau các kiểu DML đại diện.
- Đo overhead MV log trên workload ghi.
- Xác định freshness SLA và cửa sổ bảo trì.
- Chọn atomic refresh phù hợp với yêu cầu availability.
- Giám sát refresh duration, failure và staleness sau triển khai.

## 20. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| FAST refresh thất bại | MV definition không hỗ trợ fast refresh | Chạy EXPLAIN_MVIEW, đọc capability và message |
| FAST refresh báo thiếu log | Master table chưa có MV log hoặc log thiếu thông tin | Tạo/bổ sung log đúng theo định nghĩa MV |
| FORCE refresh chạy lâu bất thường | Oracle fallback sang COMPLETE | Kiểm tra LAST_REFRESH_TYPE, log và fast-refresh capability |
| MV vẫn stale sau DML | Chế độ ON DEMAND chưa được refresh | Gọi refresh hoặc kiểm tra scheduler |
| ON COMMIT làm commit chậm | Chi phí refresh được thực hiện cùng commit master | Đo workload; cân nhắc ON DEMAND |
| MV có kết quả sai sau thay đổi dữ liệu | Định nghĩa/refresh capability hoặc log không đáp ứng | Kiểm tra DML pattern, log, refresh và đối chiếu query gốc |
| MV log tăng lớn | Refresh không thường xuyên hoặc MV phụ thuộc chưa refresh | Kiểm tra dependency và lịch refresh |
| Complete refresh làm MV tạm không sẵn sàng | Atomic refresh false và phương thức truncate/reload | Đánh giá atomic refresh true hoặc out-of-place strategy phù hợp |
| Fast refresh không khả dụng sau DDL | Thay đổi schema/định nghĩa làm thay đổi capability | Chạy EXPLAIN_MVIEW và complete refresh nếu cần |
| Scheduler job không chạy | Job disabled, credential/privilege hoặc lịch sai | Kiểm tra USER_SCHEDULER_JOBS, USER_SCHEDULER_JOB_RUN_DETAILS |
| Một MV refresh xong nhưng MV khác vẫn stale | Các MV có lịch hoặc lần refresh riêng | Theo dõi từng MV và dependency |
| Không biết lần refresh thực tế là FAST hay COMPLETE | Chỉ nhìn REFRESH_METHOD cấu hình | Kiểm tra LAST_REFRESH_TYPE và lịch sử job |

## 21. Truy vấn giám sát Scheduler job

Nếu dùng DBMS_SCHEDULER, có thể xem job và lần chạy gần đây:

~~~sql
SELECT job_name,
       enabled,
       state,
       repeat_interval,
       last_start_date,
       next_run_date
FROM user_scheduler_jobs
WHERE job_name = 'REFRESH_SALES_MV_JOB';
~~~

Xem lịch sử:

~~~sql
SELECT log_date,
       status,
       error#,
       actual_start_date,
       run_duration,
       additional_info
FROM user_scheduler_job_run_details
WHERE job_name = 'REFRESH_SALES_MV_JOB'
ORDER BY log_date DESC;
~~~

Nếu job gọi procedure refresh, hãy ghi nhận lỗi refresh, thời gian thực tế và phương thức refresh. Không chỉ dựa vào trạng thái job SUCCEEDED: procedure có thể hoàn tất nhưng đã chọn FORCE fallback sang complete; cần xem metadata MV.

## 22. Quy trình triển khai materialized view có fast refresh

Một quy trình triển khai nên đi theo các bước:

1. **Xác định truy vấn MV:** liệt kê master tables, joins, filters, group by và aggregates.
2. **Kiểm tra khả năng:** chạy DBMS_MVIEW.EXPLAIN_MVIEW trên định nghĩa dự kiến.
3. **Thiết kế MV log:** chọn primary key/rowid, các cột, sequence và including new values theo capability.
4. **Tạo log:** trên từng master table cần thiết.
5. **Tạo MV:** chọn BUILD IMMEDIATE hoặc BUILD DEFERRED, REFRESH FAST và mode phù hợp.
6. **Kiểm thử DML:** insert/update/delete, thay đổi join key, null, nhiều DML trong một transaction.
7. **Refresh và đối chiếu:** so sánh kết quả MV với truy vấn gốc sau từng loại DML.
8. **Đo chi phí:** thời gian refresh, overhead ghi log, dung lượng log, commit latency.
9. **Thiết lập giám sát:** last refresh type/date, staleness, job history và lỗi.
10. **Chuẩn bị fallback:** complete refresh hoặc quy trình tái tạo nếu fast refresh không còn khả dụng.

## 23. Checklist trước khi chọn FAST REFRESH

- Truy vấn MV có được Oracle hỗ trợ fast refresh trên đúng release không?
- Tất cả master tables cần log đã có log chưa?
- Log có đúng kiểu định danh PRIMARY KEY/ROWID không?
- Các cột cần cho select, filter, join, group by và aggregate đã có trong log chưa?
- Có cần SEQUENCE hoặc INCLUDING NEW VALUES không?
- Aggregate MV đã có các aggregate support như COUNT(*), COUNT(expr) phù hợp chưa?
- Các DML pattern thật có được hỗ trợ không?
- Có thao tác partition maintenance/direct-path load nào ảnh hưởng không?
- Refresh mode là ON DEMAND hay ON COMMIT? Đã đo commit latency chưa?
- ATOMIC_REFRESH có phù hợp yêu cầu availability không?
- Có giám sát LAST_REFRESH_TYPE, STALENESS, duration và job failure không?
- Có kế hoạch complete refresh khi fast refresh không khả dụng không?

## 24. Bài thực hành có kiểm soát

Các bài thực hành dùng LAB_SALES và LAB_SALES_BY_PRODUCT_MV đã tạo ở phần 10. Chỉ chạy trong schema DEV/TEST được cấp quyền và đúng PDB/service. Không tạo log, MV hoặc chạy refresh trên bảng nghiệp vụ production khi chưa có kế hoạch được phê duyệt.

### Bài 1 — Quan sát ON DEMAND

1. Tạo bảng nguồn, log và MV theo phần 10.
2. Chạy truy vấn đọc MV để ghi nhận kết quả ban đầu.
3. Insert một giao dịch mới vào bảng nguồn và commit.
4. Đọc MV trước refresh.
5. Gọi DBMS_MVIEW.REFRESH(..., method => 'F').
6. Đọc MV lại và so sánh.

Giải thích vì sao DML commit không tự cập nhật MV khi dùng ON DEMAND.

### Bài 2 — So sánh FAST và COMPLETE

Sau khi đã có dữ liệu:
1. Insert/update/delete một số dòng nguồn.
2. Chạy FAST refresh.
3. Ghi thời gian và kết quả.
4. Thay đổi nguồn thêm một lần nữa.
5. Chạy COMPLETE refresh.
6. Đối chiếu nội dung MV với truy vấn aggregate trực tiếp trên bảng nguồn.

Không chỉ so sánh thời gian trên vài dòng lab; mục tiêu chính là hiểu khác biệt phương thức.

### Bài 3 — Kiểm tra FORCE

Gọi:

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'LAB_SALES_BY_PRODUCT_MV',
        method => '?'
    );
END;
/
~~~

Sau đó xem:

~~~sql
SELECT mview_name, last_refresh_type, last_refresh_date, staleness
FROM user_mviews
WHERE mview_name = 'LAB_SALES_BY_PRODUCT_MV';
~~~

Xác định lần refresh thực tế dùng FAST hay COMPLETE.

### Bài 4 — EXPLAIN_MVIEW

1. Xác nhận MV_CAPABILITIES_TABLE đã được chuẩn bị bởi DBA hoặc script theo Oracle Home.
2. Chạy DBMS_MVIEW.EXPLAIN_MVIEW.
3. Đọc các capability liên quan FAST và aggregate.
4. Tìm dòng POSSIBLE = 'N' và message giải thích.
5. Ghi lại thay đổi cần thiết cho query hoặc log.

### Bài 5 — Kiểm tra log và DML overhead

1. Xem USER_MVIEW_LOGS.
2. Thực hiện nhiều insert/update/delete trên bảng nguồn.
3. Refresh MV.
4. Quan sát thời gian DML và refresh.
5. Thảo luận trade-off giữa overhead ghi log và thời gian complete refresh.

### Bài 6 — So sánh ON COMMIT và ON DEMAND

Trong schema lab riêng, tạo hai MV phù hợp với hai mode hoặc tạo lại MV theo từng cấu hình. Đo thời gian commit khi cập nhật bảng nguồn. Giải thích vì sao ON COMMIT có thể làm tăng thời gian commit và vì sao không phải mọi MV đều hỗ trợ mode này.

### Thu dọn dữ liệu lab

Chỉ khi xác nhận đúng các object do mình tạo trong DEV/TEST và không có người khác sử dụng:

~~~sql
DROP MATERIALIZED VIEW lab_sales_by_product_mv;
DROP MATERIALIZED VIEW LOG ON lab_sales;
DROP TABLE lab_sales PURGE;
~~~

Thứ tự trên xóa MV trước, sau đó xóa log trên master và cuối cùng xóa bảng lab. Các thao tác DDL có implicit commit; không chạy trên production hoặc bất kỳ object nào ngoài phạm vi thực hành.

## 25. Câu hỏi ôn tập

**Câu 1.** Complete refresh khác fast refresh như thế nào?

**Đáp án:** Complete refresh chạy lại toàn bộ query định nghĩa MV; fast refresh áp dụng phần thay đổi tăng dần từ lần refresh trước dựa trên MV log hoặc cơ chế hỗ trợ như PCT.

**Câu 2.** Complete refresh có bắt buộc phải có materialized view log không?

**Đáp án:** Không. MV log chủ yếu hỗ trợ log-based fast refresh.

**Câu 3.** FAST refresh được chỉ định bằng method nào trong DBMS_MVIEW.REFRESH?

**Đáp án:** F.

**Câu 4.** FORCE refresh làm gì khi fast refresh không khả dụng?

**Đáp án:** Oracle có thể fallback sang complete refresh; cần kiểm tra LAST_REFRESH_TYPE để biết phương thức thực tế.

**Câu 5.** Materialized view log lưu gì?

**Đáp án:** Thông tin thay đổi trên bảng master cần thiết cho fast refresh, chẳng hạn primary key/ROWID, các cột liên quan, sequence và new values tùy cấu hình.

**Câu 6.** INCLUDING NEW VALUES có ý nghĩa gì?

**Đáp án:** Yêu cầu log lưu giá trị mới của các cột thay đổi trong những trường hợp cần thiết cho fast refresh, đặc biệt với một số aggregate MV.

**Câu 7.** Vì sao aggregate MV có thể cần COUNT(*) và COUNT(expression)?

**Đáp án:** Để duy trì chính xác số hàng và số giá trị không null khi insert/delete/update; các thành phần này hỗ trợ tính lại aggregate như AVG.

**Câu 8.** ON DEMAND khác ON COMMIT thế nào?

**Đáp án:** ON DEMAND refresh khi được gọi hoặc theo lịch; ON COMMIT refresh cùng transaction commit trên master nếu định nghĩa hỗ trợ.

**Câu 9.** ATOMIC_REFRESH => FALSE có thể ảnh hưởng gì?

**Đáp án:** Oracle có thể dùng truncate/reload cho complete refresh để tăng tốc; refresh không còn atomic theo cách của TRUE và MV có thể không sẵn sàng đầy đủ nếu quá trình nạp lại thất bại.

**Câu 10.** Làm sao kiểm tra MV có hỗ trợ fast refresh?

**Đáp án:** Dùng DBMS_MVIEW.EXPLAIN_MVIEW, đọc MV_CAPABILITIES_TABLE và thử refresh trên môi trường tương ứng.

**Câu 11.** Một master table có nhiều MV phụ thuộc có cần tạo một log riêng cho từng MV không?

**Đáp án:** Không. Các MV phù hợp có thể dùng chung MV log trên master table; log phải chứa đủ thông tin cho các dependent MVs.

**Câu 12.** Refresh thành công có đồng nghĩa optimizer sẽ dùng MV để rewrite mọi truy vấn không?

**Đáp án:** Không. Refresh và query rewrite là hai chức năng khác nhau; rewrite còn phụ thuộc tương đương truy vấn, cấu hình và freshness policy.

## Kết luận

**Complete refresh** tính lại toàn bộ truy vấn định nghĩa MV và không bắt buộc phải có materialized view log. **Fast refresh** áp dụng phần thay đổi tăng dần, thường dựa trên log ở các bảng master hoặc cơ chế PCT; nó chỉ hoạt động khi định nghĩa MV, log và kiểu DML đáp ứng điều kiện Oracle hỗ trợ. FORCE thử fast refresh rồi có thể fallback sang complete, vì vậy cần theo dõi LAST_REFRESH_TYPE để tránh bất ngờ về thời gian chạy.

Materialized view log ghi nhận thông tin thay đổi, chẳng hạn PRIMARY KEY, ROWID, SEQUENCE, danh sách cột và INCLUDING NEW VALUES. Log giúp fast refresh nhưng làm tăng overhead DML và dung lượng lưu trữ. ON DEMAND cho phép refresh theo lịch hoặc gọi tường minh; ON COMMIT có thể giữ MV gần dữ liệu nguồn hơn nhưng làm tăng công việc trên đường commit. ATOMIC_REFRESH là lựa chọn riêng về tính nguyên tử và cách thay nội dung MV, không phải refresh method.

Trước khi triển khai, hãy kiểm tra capability bằng DBMS_MVIEW.EXPLAIN_MVIEW, thử insert/update/delete thực tế, đo thời gian refresh và chi phí log, kiểm tra freshness sau refresh, rồi thiết lập giám sát và phương án complete refresh khi fast refresh không còn khả dụng.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c Data Warehousing Guide — Refreshing Materialized Views](https://docs.oracle.com/en/database/oracle/oracle-database/19/dwhsg/refreshing-materialized-views.html): complete/fast refresh, refresh mode, PCT và các lưu ý vận hành.
- [Oracle Database 19c SQL Reference — CREATE MATERIALIZED VIEW](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-MATERIALIZED-VIEW.html): cú pháp tạo MV, build mode và refresh clause.
- [Oracle Database 19c SQL Reference — CREATE MATERIALIZED VIEW LOG](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-MATERIALIZED-VIEW-LOG.html): cú pháp log, primary key, ROWID, sequence và new values.
- [Oracle Database 19c PL/SQL Packages — DBMS_MVIEW](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_MVIEW.html): REFRESH, EXPLAIN_MVIEW và các thủ tục quản lý MV.
- [Oracle Database 19c Reference — USER_MVIEWS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_MVIEWS.html): metadata refresh và staleness của materialized view.
- [Oracle Database 19c Reference — USER_MVIEW_LOGS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_MVIEW_LOGS.html): metadata materialized view log.

