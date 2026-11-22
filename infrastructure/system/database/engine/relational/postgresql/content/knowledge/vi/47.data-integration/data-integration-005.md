# Ước tính chi phí, fetch size và hiệu năng truy vấn liên máy

Khi ứng dụng truy vấn dữ liệu trên một PostgreSQL server khác, thời gian hoàn thành phụ thuộc vào nhiều yếu tố: kế hoạch thực thi ở máy chủ gọi truy vấn, công việc trên máy chủ chứa dữ liệu, lượng dữ liệu truyền qua mạng, số lượt trao đổi và phần xử lý còn lại ở máy chủ gọi. Một câu SQL ngắn vẫn có thể chậm nếu nó chuyển hàng trăm nghìn hàng qua mạng rồi mới lọc hoặc join.

Trong PostgreSQL, một cách tích hợp phổ biến là **postgres_fdw**. Phần mở rộng này tạo các foreign table đại diện cho bảng ở máy chủ khác. Ứng dụng truy vấn foreign table gần giống bảng thông thường; postgres_fdw quyết định phần nào của truy vấn có thể gửi sang máy chủ từ xa. Các khái niệm về ước tính chi phí, thống kê, **fetch_size** và pushdown giúp kiểm soát hiệu năng của mô hình này.

Các tùy chọn **use_remote_estimate**, **fdw_startup_cost**, **fdw_tuple_cost** và **fetch_size** trong bài thuộc postgres_fdw. Một FDW khác có thể có cơ chế và tên tùy chọn khác.

## 1. Đường đi của một truy vấn liên máy

Giả sử ứng dụng kết nối đến PostgreSQL A, còn dữ liệu đơn hàng nằm trên PostgreSQL B. Trên A, quản trị viên cấu hình postgres_fdw, khai báo server B, ánh xạ thông tin đăng nhập và tạo foreign table cho bảng đơn hàng ở B.

Khi ứng dụng chạy truy vấn trên foreign table, luồng xử lý thường gồm các bước:

1. PostgreSQL A phân tích câu SQL và lập kế hoạch thực thi.
2. Bộ lập kế hoạch ước tính số hàng, chi phí và các phương án thực hiện.
3. postgres_fdw chuyển phần truy vấn đủ điều kiện sang PostgreSQL B.
4. PostgreSQL B thực thi SQL nhận được, có thể sử dụng chỉ mục và thống kê của chính B.
5. Kết quả được gửi về A theo từng đợt fetch.
6. PostgreSQL A tiếp tục các phép tính chưa thể đẩy sang B, chẳng hạn join với bảng cục bộ hoặc xử lý biểu thức không được hỗ trợ từ xa.

Vì vậy, SQL viết ở A không có nghĩa toàn bộ truy vấn chạy ở A. Nếu bộ lọc và phép tổng hợp được đẩy sang B, mạng chỉ cần truyền kết quả đã thu gọn. Nếu không, A có thể phải nhận rất nhiều hàng rồi mới lọc hoặc nhóm dữ liệu.

Cần phân biệt ba phần công việc: **lập kế hoạch** dựa trên ước tính; **thực thi từ xa** trên máy chủ chứa dữ liệu; và **truyền cùng xử lý cục bộ** tại máy chủ gọi truy vấn.

## 2. PostgreSQL ước tính chi phí như thế nào?

PostgreSQL dùng cost để so sánh các phương án thực thi. Giá trị cost trong EXPLAIN là **đơn vị chi phí nội bộ**, không phải mili giây. Kế hoạch có cost 500 không có nghĩa truy vấn mất 500 ms. Cost hữu ích nhất khi so sánh các phương án trong cùng môi trường và cấu hình.

Kế hoạch thường thể hiện hai giá trị:

- **startup cost:** chi phí ước tính trước khi có thể trả về hàng đầu tiên.
- **total cost:** chi phí ước tính để hoàn thành toàn bộ nút thực thi.

Với truy vấn liên máy, startup cost có thể phản ánh phần chi phí cố định khi bắt đầu truy cập từ xa. Chi phí theo hàng phản ánh phần việc tăng thêm khi xử lý và truyền dữ liệu. Ước tính ảnh hưởng đến quyết định chọn foreign scan, thứ tự join và nơi thực hiện phép tính.

### 2.1. Thống kê của foreign table

Khi dùng ước tính cục bộ, PostgreSQL cần thống kê để dự đoán số hàng thỏa điều kiện WHERE, số giá trị phân biệt, phân bố dữ liệu và số hàng trung gian khi join hoặc group.

Có thể thu thập thống kê cho foreign table bằng:

~~~sql
ANALYZE remote_orders;
~~~

Với postgres_fdw, ANALYZE lấy mẫu dữ liệu từ máy chủ từ xa để xây dựng thống kê mà bộ lập kế hoạch cục bộ sử dụng. Tiến trình autovacuum không tự động phân tích foreign table như bảng cục bộ thông thường, vì vậy cần chủ động lên lịch ANALYZE khi dữ liệu nguồn thay đổi đáng kể.

Nếu thống kê cũ hoặc thiếu, PostgreSQL có thể dự đoán sai số hàng. Ví dụ, bộ lập kế hoạch ước tính điều kiện ngày tháng chỉ trả về 100 hàng trong khi thực tế trả về 500.000 hàng. Kế hoạch join dựa trên ước tính sai có thể khiến lượng dữ liệu truyền qua mạng tăng mạnh.

### 2.2. Lấy ước tính từ máy chủ từ xa

postgres_fdw có tùy chọn **use_remote_estimate**:

- Mặc định là **false**. PostgreSQL cục bộ ước tính dựa trên thống kê cục bộ của foreign table và các tùy chọn chi phí FDW.
- Khi đặt thành **true**, postgres_fdw gửi lệnh EXPLAIN đến máy chủ từ xa để lấy ước tính từ bộ lập kế hoạch ở đó.

Ước tính từ xa hữu ích khi máy chủ B có thống kê, chỉ mục hoặc phân bố dữ liệu mà thống kê ở A không phản ánh đầy đủ. Máy chủ B có thể đánh giá điều kiện lọc và kế hoạch truy cập dựa trên tình trạng dữ liệu thực tế của nó.

Đổi lại, việc lấy ước tính từ xa phát sinh trao đổi với B trong giai đoạn lập kế hoạch. Điều này có thể làm tăng planning time, nhất là khi ứng dụng tạo nhiều truy vấn ngắn hoặc có nhiều foreign table. Ước tính từ xa cũng không bảo đảm thời gian thực thi thực tế, vì tải máy chủ và tình trạng mạng vẫn thay đổi.

Có thể cấu hình tùy chọn ở cấp server hoặc foreign table. Ví dụ:

~~~sql
CREATE SERVER warehouse_srv
  FOREIGN DATA WRAPPER postgres_fdw
  OPTIONS (
    host 'warehouse-db',
    port '5432',
    dbname 'warehouse',
    use_remote_estimate 'true'
  );
~~~

Nếu truy vấn có thời gian chạy dài và ước tính từ xa giúp chọn kế hoạch tốt hơn, chi phí lập kế hoạch bổ sung có thể chấp nhận được. Với workload gồm nhiều truy vấn rất ngắn, cần đo cả planning time trước khi bật tùy chọn này rộng rãi.

### 2.3. Hai tham số chi phí của postgres_fdw

Khi **use_remote_estimate** tắt, postgres_fdw dùng thêm hai tùy chọn để mô hình hóa chi phí truy cập dữ liệu từ xa:

| Tùy chọn | Giá trị mặc định | Ý nghĩa |
|---|---:|---|
| **fdw_startup_cost** | 100 | Phần chi phí cố định cộng vào startup cost của foreign scan |
| **fdw_tuple_cost** | 0.2 | Phần chi phí bổ sung cho mỗi hàng được truyền từ máy chủ từ xa |

**fdw_startup_cost** đại diện gần đúng cho chi phí cố định khi bắt đầu truy vấn từ xa, chẳng hạn chi phí kết nối và khởi tạo thực thi. Giá trị cao hơn làm cho kế hoạch phải mở foreign scan trở nên đắt hơn trong mắt bộ lập kế hoạch. Tham số này đáng quan tâm nếu kế hoạch có thể tạo nhiều lần truy cập từ xa.

**fdw_tuple_cost** đại diện cho chi phí tăng thêm khi mỗi hàng được chuyển từ B về A. Mạng chậm, hàng rộng hoặc chi phí chuyển đổi dữ liệu lớn có thể khiến giá trị thực tế cần cao hơn mặc định. Khi giá trị này tăng, bộ lập kế hoạch tính việc kéo nhiều hàng từ xa là đắt hơn.

Hai giá trị này là đơn vị chi phí của planner, không phải số mili giây. Không nên lấy độ trễ mạng 20 ms rồi đặt fdw_tuple_cost thành 20. Hãy thay đổi từng bước, quan sát kế hoạch được chọn và so sánh thời gian thực thi trên workload đại diện.

Có thể khai báo ở cấp server:

~~~sql
CREATE SERVER warehouse_srv
  FOREIGN DATA WRAPPER postgres_fdw
  OPTIONS (
    host 'warehouse-db',
    port '5432',
    dbname 'warehouse',
    use_remote_estimate 'false',
    fdw_startup_cost '100',
    fdw_tuple_cost '0.2',
    fetch_size '500'
  );
~~~

Hoặc đặt riêng cho một foreign table:

~~~sql
ALTER FOREIGN TABLE remote_orders
  OPTIONS (ADD fdw_tuple_cost '0.35');
~~~

Nếu tùy chọn đã tồn tại ở cấp foreign table, dùng **SET** thay cho **ADD**. Cấu hình ở foreign table cho phép tinh chỉnh một bảng mà không làm thay đổi mọi bảng dùng chung server.

## 3. Fetch size và cách dữ liệu được chuyển qua mạng

**fetch_size** quy định số hàng postgres_fdw lấy trong mỗi lần fetch kết quả từ máy chủ từ xa. Giá trị mặc định là **100 hàng**. Tùy chọn này có thể được khai báo ở cấp foreign server hoặc foreign table; thiết lập ở bảng cho phép ghi đè cấu hình chung của server.

Ví dụ, tăng fetch size cho bảng đơn hàng:

~~~sql
ALTER FOREIGN TABLE remote_orders
  OPTIONS (ADD fetch_size '1000');
~~~

Nếu bảng đã có tùy chọn fetch_size, dùng:

~~~sql
ALTER FOREIGN TABLE remote_orders
  OPTIONS (SET fetch_size '1000');
~~~

Fetch size chỉ quyết định kích thước từng đợt lấy kết quả. Nó không giới hạn tổng số hàng truy vấn trả về, không thay thế LIMIT và không thay đổi ý nghĩa của câu SQL.

### 3.1. Vì sao fetch size ảnh hưởng hiệu năng?

Giả sử truy vấn trả về 10.000 hàng:

- Với fetch size 100, cần khoảng 100 lượt fetch có dữ liệu.
- Với fetch size 1.000, cần khoảng 10 lượt fetch có dữ liệu.

Số lượt trao đổi giảm có thể giúp truy vấn nhanh hơn trên mạng có độ trễ cao. Tuy nhiên, tăng fetch size cũng khiến mỗi đợt chứa nhiều hàng hơn, làm tăng bộ nhớ cần dùng để giữ dữ liệu đang nhận và có thể làm tăng độ trễ trước khi xử lý xong một đợt.

Mô hình gần đúng để hình dung thời gian truyền dữ liệu:

~~~text
Số lượt fetch có dữ liệu ≈ ceil(Tổng số hàng / fetch_size)

Thời gian tổng ≈ Thời gian xử lý từ xa
               + Số lượt trao đổi × Độ trễ mạng
               + Dung lượng dữ liệu / Băng thông hữu dụng
               + Thời gian xử lý cục bộ
~~~

Đây là mô hình giải thích, không phải công thức cost mà PostgreSQL dùng. Thực tế còn phụ thuộc cách máy chủ truyền kết quả, kích thước từng hàng, khả năng xử lý đồng thời, bộ đệm và tải của hai máy chủ. Có thể phát sinh thêm một lượt fetch để xác nhận đã hết dữ liệu.

### 3.2. Chọn fetch size phù hợp

Fetch size nhỏ:

- Mỗi đợt chiếm ít bộ nhớ hơn.
- Có thể trả dữ liệu theo từng đợt nhỏ.
- Tạo nhiều lượt trao đổi hơn, nên dễ bị ảnh hưởng bởi độ trễ mạng.

Fetch size lớn:

- Giảm số lượt fetch và thường cải thiện thông lượng khi kết quả lớn.
- Có thể tận dụng tốt hơn đường truyền có độ trễ cao.
- Tăng bộ nhớ cần cho mỗi đợt và có thể không có lợi nếu truy vấn chỉ trả về ít hàng.

Không có một con số tối ưu cho mọi hệ thống. Có thể thử các mức như 100, 500, 1.000 hoặc 2.000 trên dữ liệu đại diện, sau đó so sánh thời gian, bộ nhớ và tải mạng. Nên thử cả truy vấn trả về ít hàng lẫn truy vấn trả về nhiều hàng.

Kích thước hàng cũng quan trọng. Một đợt 1.000 hàng chỉ gồm vài cột số nguyên nhẹ hơn nhiều so với 1.000 hàng chứa văn bản dài hoặc dữ liệu nhị phân. Vì vậy, không nên tăng fetch size chỉ dựa trên số hàng mà bỏ qua độ rộng dữ liệu.

### 3.3. Fetch size không thay thế việc giảm dữ liệu

Nếu ứng dụng chỉ cần mã khách hàng và tổng tiền, hãy chọn đúng hai cột thay vì lấy toàn bộ hàng. Nếu chỉ cần dữ liệu trong một khoảng thời gian, hãy lọc ngay trên truy vấn để điều kiện có thể được đẩy sang máy chủ từ xa.

Tăng fetch size có thể giảm số lần trao đổi cho cùng tập kết quả, nhưng không làm giảm tổng số byte cần truyền. Nếu truy vấn đang chuyển 5 GB dữ liệu không cần thiết, cách xử lý hiệu quả hơn là giảm số hàng hoặc số cột trước khi điều chỉnh fetch size.

## 4. Đẩy phép tính sang máy chủ từ xa (pushdown)

**Pushdown** là khả năng postgres_fdw chuyển một phần phép tính sang PostgreSQL chứa dữ liệu gốc. Máy chủ từ xa thực hiện phép tính gần nơi lưu dữ liệu và chỉ gửi kết quả cần thiết về máy chủ gọi truy vấn.

Ví dụ, truy vấn sau tính tổng doanh thu theo khu vực:

~~~sql
SELECT region, sum(amount) AS total_amount
FROM remote_sales
WHERE sale_date >= DATE '2026-01-01'
GROUP BY region;
~~~

Nếu điều kiện và phép tổng hợp đủ điều kiện pushdown, PostgreSQL từ xa có thể thực hiện WHERE và GROUP BY. Thay vì truyền tất cả giao dịch về A, hệ thống chỉ cần truyền kết quả tổng hợp theo khu vực.

Các phần thường có cơ hội được đẩy xuống gồm điều kiện lọc trên cột từ xa, danh sách cột cần đọc, một số biểu thức và phép sắp xếp, join giữa các foreign table trên cùng một foreign server, cùng một số phép tổng hợp khi biểu thức có thể được thực thi an toàn ở phía từ xa.

Không phải mọi biểu thức đều có thể pushdown. Hàm chỉ tồn tại ở máy chủ cục bộ, phép ép kiểu có ngữ nghĩa khác nhau, collation không tương thích hoặc biểu thức không được FDW xem là an toàn có thể khiến một phần truy vấn phải chạy ở A. Khả năng pushdown cũng phụ thuộc phiên bản PostgreSQL và loại FDW.

### 4.1. Join trên cùng máy chủ từ xa

Nếu hai foreign table cùng trỏ đến một PostgreSQL server và dùng cấu hình ánh xạ người dùng tương thích, postgres_fdw có thể đẩy join sang máy chủ đó khi các biểu thức join đủ điều kiện:

~~~sql
SELECT o.order_id, c.customer_name
FROM remote_orders AS o
JOIN remote_customers AS c
  ON c.customer_id = o.customer_id
WHERE o.created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00';
~~~

Khi join được đẩy xuống, máy chủ từ xa có thể dùng chỉ mục và thống kê của cả hai bảng. Kết quả sau join mới được truyền về A, nhờ đó giảm lượng dữ liệu qua mạng.

### 4.2. Join giữa hai máy chủ hoặc với bảng cục bộ

Nếu remote_orders nằm trên B nhưng remote_customers nằm trên C, postgres_fdw không thể gửi một join thông thường đến một máy chủ duy nhất để đọc cả hai bảng. PostgreSQL A thường phải nhận dữ liệu từ các nguồn rồi thực hiện join cục bộ.

Tình huống tương tự xảy ra khi join foreign table với bảng chỉ tồn tại trên A. Khi đó, cần kiểm soát số hàng được lấy từ xa trước khi join. Có thể lọc foreign table bằng điều kiện có thể pushdown, tổng hợp trước ở nguồn hoặc tổ chức một bước nạp dữ liệu phù hợp nếu truy vấn liên máy diễn ra thường xuyên.

Đây là lý do cần xem câu SQL thực tế được gửi đi, thay vì chỉ nhìn câu SQL ứng dụng viết.

## 5. Đo lường bằng EXPLAIN

Bắt đầu bằng EXPLAIN để xem bộ lập kế hoạch dự định thực hiện truy vấn như thế nào:

~~~sql
EXPLAIN (VERBOSE, COSTS)
SELECT customer_id, sum(total) AS total_amount
FROM remote_orders
WHERE created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
GROUP BY customer_id;
~~~

Với **VERBOSE**, kế hoạch foreign scan thường hiển thị phần **Remote SQL**. Đây là câu SQL postgres_fdw dự định gửi sang máy chủ từ xa. Hãy kiểm tra điều kiện WHERE quan trọng có xuất hiện không, chỉ những cột cần thiết có được chọn không, phép tổng hợp hoặc join có được thực hiện từ xa không và số hàng ước tính có hợp lý không.

Sau đó đo thời gian thực thi thực tế:

~~~sql
EXPLAIN (ANALYZE, VERBOSE, BUFFERS)
SELECT customer_id, sum(total) AS total_amount
FROM remote_orders
WHERE created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
GROUP BY customer_id;
~~~

**ANALYZE** thực thi câu SELECT để thu thập số liệu thực tế. So sánh số hàng ước tính với số hàng thực tế ở các nút quan trọng. Nếu chênh lệch lớn, cần kiểm tra thống kê, độ chọn lọc của điều kiện và cách dữ liệu thay đổi.

Một số giới hạn khi đọc kết quả:

- Thời gian ở foreign scan phản ánh thời gian mà tiến trình cục bộ quan sát được khi thực hiện nút đó, bao gồm việc lấy kết quả từ xa. Nó không tự tách riêng thời gian xử lý trên B và thời gian truyền mạng.
- BUFFERS trong kế hoạch tại A mô tả bộ đệm mà tiến trình A theo dõi; không nên hiểu đó là số liệu bộ đệm của PostgreSQL B.
- EXPLAIN ANALYZE tại A không tự cung cấp đầy đủ kế hoạch thực thi thực tế ở B.

Để hiểu phần chạy ở B, lấy câu lệnh trong Remote SQL và chạy EXPLAIN trực tiếp trên B. Nếu cần đo thời gian và bộ đệm ở B, có thể dùng EXPLAIN ANALYZE trên truy vấn tương ứng tại B trong môi trường kiểm thử phù hợp. Kết hợp số liệu ở hai phía giúp phân biệt truy vấn từ xa chậm với đường truyền chậm.

## 6. Quy trình tinh chỉnh hiệu năng

Nên điều chỉnh theo thứ tự từ nguyên nhân tạo ra dữ liệu truyền đến cách truyền dữ liệu. Cách làm này giúp mỗi thay đổi có mục tiêu và dễ đo kết quả.

1. **Xác định dữ liệu cần dùng.** Bỏ SELECT * nếu chỉ dùng một phần cột. Đưa điều kiện lọc vào SQL và kiểm tra xem điều kiện đó có được pushdown hay không.
2. **Kiểm tra kế hoạch và Remote SQL.** Chạy EXPLAIN VERBOSE để xác định phần nào được gửi sang máy chủ từ xa. Nếu WHERE hoặc phép tổng hợp đáng lẽ thực hiện tại nguồn nhưng lại xuất hiện ở cục bộ, hãy tìm biểu thức cản trở pushdown.
3. **Cập nhật thống kê.** Nếu dùng ước tính cục bộ, chạy ANALYZE trên foreign table sau khi dữ liệu nguồn thay đổi đáng kể. So sánh số hàng ước tính và thực tế. Với truy vấn quan trọng, thử use_remote_estimate và đo cả planning time lẫn execution time.
4. **Điều chỉnh fetch_size.** Khi truy vấn đã trả về đúng lượng dữ liệu cần thiết nhưng vẫn mất nhiều thời gian trao đổi, thử tăng fetch_size. Ghi lại thời gian, số hàng, độ rộng hàng và mức sử dụng bộ nhớ.
5. **Điều chỉnh mô hình chi phí.** Nếu planner thường chọn phương án kéo quá nhiều hàng từ xa, kiểm tra fdw_tuple_cost. Nếu kế hoạch tạo nhiều lần truy cập từ xa nhỏ, kiểm tra fdw_startup_cost. Điều chỉnh từng tham số một.
6. **Kiểm tra cả hai máy chủ và mạng.** Đo CPU, bộ nhớ, I/O, số kết nối và độ trễ mạng ở A lẫn B. Nếu truy vấn tự nó đã chậm khi chạy trực tiếp tại B, tăng fetch_size ở A không giải quyết được nguyên nhân.

## 7. Ví dụ cấu hình và truy vấn hoàn chỉnh

Ví dụ sau minh họa cấu hình server, user mapping và foreign table. Tên máy chủ, tài khoản và mật khẩu chỉ là giá trị mẫu; hãy thay bằng thông tin của môi trường triển khai.

~~~sql
CREATE EXTENSION IF NOT EXISTS postgres_fdw;

CREATE SERVER warehouse_srv
  FOREIGN DATA WRAPPER postgres_fdw
  OPTIONS (
    host 'warehouse-db',
    port '5432',
    dbname 'warehouse',
    use_remote_estimate 'false',
    fdw_startup_cost '100',
    fdw_tuple_cost '0.2',
    fetch_size '500'
  );

CREATE USER MAPPING FOR app_user
  SERVER warehouse_srv
  OPTIONS (
    user 'readonly_user',
    password 'replace-with-managed-secret'
  );

CREATE FOREIGN TABLE remote_orders (
  order_id bigint,
  customer_id bigint,
  created_at timestamptz,
  total numeric
)
SERVER warehouse_srv
OPTIONS (
  schema_name 'sales',
  table_name 'orders'
);

ANALYZE remote_orders;
~~~

Truy vấn lấy dữ liệu trong một khoảng thời gian và tổng hợp theo khách hàng:

~~~sql
EXPLAIN (ANALYZE, VERBOSE, BUFFERS)
SELECT customer_id, sum(total) AS total_amount
FROM remote_orders
WHERE created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
GROUP BY customer_id;
~~~

Nếu Remote SQL chứa điều kiện ngày tháng và GROUP BY, phần lọc và tổng hợp đã được đẩy xuống nguồn. Nếu Remote SQL chỉ đọc nhiều hàng rồi kế hoạch cục bộ mới nhóm dữ liệu, cần kiểm tra lý do aggregate không được pushdown.

Sau khi có số liệu ban đầu, thử fetch size lớn hơn cho riêng bảng:

~~~sql
ALTER FOREIGN TABLE remote_orders
  OPTIONS (ADD fetch_size '1000');
~~~

Chạy lại cùng truy vấn trên cùng dữ liệu và điều kiện tải. Ghi lại thời gian thực thi, số hàng nhận về và mức sử dụng tài nguyên. Nếu thời gian không cải thiện hoặc bộ nhớ tăng đáng kể, quay lại mức phù hợp hơn.

Để thử ước tính từ xa, thay đổi tùy chọn ở cấp server:

~~~sql
ALTER SERVER warehouse_srv
  OPTIONS (SET use_remote_estimate 'true');
~~~

Sau đó chạy lại EXPLAIN và so sánh planning time, kế hoạch được chọn, số hàng ước tính và thời gian thực thi. Quyết định cấu hình dựa trên nhiều truy vấn đại diện thay vì một truy vấn đơn lẻ.

## 8. Các lỗi thường gặp khi tối ưu

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Foreign scan trả về rất nhiều hàng | Bộ lọc không được pushdown hoặc điều kiện quá rộng | Xem Remote SQL, giảm số hàng ở nguồn |
| Kế hoạch join có cost thấp nhưng chạy lâu | Thống kê cũ hoặc số hàng ước tính sai | ANALYZE foreign table, so sánh estimated rows với actual rows |
| Truy vấn chậm dù máy chủ từ xa xử lý nhanh | Nhiều lượt fetch hoặc kết quả quá lớn | Thử fetch_size, giảm số cột và số hàng truyền |
| Tăng fetch_size nhưng không cải thiện | Thời gian chủ yếu nằm ở remote execution hoặc xử lý cục bộ | Đo trực tiếp truy vấn tại máy chủ từ xa |
| Join giữa các nguồn tạo lượng dữ liệu trung gian lớn | Các bảng ở nhiều foreign server nên join phải chạy cục bộ | Lọc hoặc tổng hợp tại từng nguồn trước khi join |
| Planning time tăng sau khi bật remote estimate | Mỗi lần lập kế hoạch cần hỏi máy chủ từ xa | Đo planning time, chỉ bật ở phạm vi cần thiết |

Các lỗi thiết kế thường gặp cần tránh:

- **Chỉ tăng fetch_size:** nếu truy vấn truyền dữ liệu thừa, số byte vẫn không giảm.
- **Chỉ nhìn total cost:** cost là ước tính của planner, cần đối chiếu với thời gian và số hàng thực tế.
- **Bật use_remote_estimate cho mọi truy vấn mà không đo:** ước tính tốt hơn có thể đi kèm planning time cao hơn.
- **Bỏ qua Remote SQL:** câu SQL ứng dụng không cho biết phần nào thật sự chạy trên máy chủ từ xa.
- **Giả định join luôn chạy ở nguồn:** join qua nhiều foreign server hoặc với bảng cục bộ thường cần xử lý tại máy chủ gọi truy vấn.
- **Tăng fetch_size quá cao:** hàng rộng và nhiều truy vấn đồng thời có thể làm tăng áp lực bộ nhớ.

## 9. Nguyên tắc vận hành

Để duy trì hiệu năng ổn định, nên theo dõi các truy vấn liên máy quan trọng sau mỗi thay đổi lớn về dữ liệu hoặc cấu hình. Lưu lại kế hoạch EXPLAIN, planning time, execution time, số hàng ước tính và thực tế, fetch_size cùng cấu hình cost đang dùng. Những số liệu này tạo thành mốc so sánh khi workload thay đổi.

Cũng cần phân biệt cấu hình dùng chung và cấu hình riêng. Tùy chọn ở cấp server ảnh hưởng đến nhiều foreign table, trong khi tùy chọn ở cấp bảng phù hợp với trường hợp một bảng có hàng rộng, lượng dữ liệu lớn hoặc kiểu truy cập khác biệt. Hãy chọn phạm vi nhỏ nhất đáp ứng mục tiêu để việc điều chỉnh có thể dự đoán được.

Với postgres_fdw, hiệu năng tốt thường đến từ sự kết hợp của bốn yếu tố: ước tính đủ sát để chọn kế hoạch phù hợp, pushdown để giảm công việc và dữ liệu truyền, fetch_size cân bằng giữa số lượt trao đổi và bộ nhớ, cùng phép đo ở cả máy chủ cục bộ lẫn máy chủ từ xa. Khi tối ưu theo các yếu tố này, truy vấn liên máy có thể tận dụng dữ liệu ở nhiều PostgreSQL server mà vẫn kiểm soát được độ trễ và tài nguyên.

