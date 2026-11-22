# Phân loại thao tác đọc, ghi, tìm kiếm điểm, quét phạm vi và tổng hợp

Hiệu năng cơ sở dữ liệu chịu ảnh hưởng lớn bởi loại công việc mà hệ thống phải xử lý. Hai ứng dụng cùng sử dụng một DBMS, cùng có bảng vài triệu dòng và cùng có số truy vấn mỗi giây như nhau vẫn có thể cần cách thiết kế hoàn toàn khác nhau. Một hệ thống tra cứu trạng thái đơn hàng thường thực hiện nhiều lần đọc một vài dòng; một hệ thống báo cáo lại đọc hàng triệu dòng rồi nhóm và tính tổng. Một hệ thống ghi nhận sự kiện có thể liên tục thêm dữ liệu; một hệ thống quản lý tồn kho phải cập nhật những hàng nóng mà nhiều giao dịch cùng tranh chấp.

Trong module **DATABASE_PERFORMANCE**, mục tiêu là tối ưu hiệu năng dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Vì vậy, trước khi chỉnh SQL hoặc tạo chỉ mục, cần nhận diện chính xác khối lượng công việc (workload): hệ thống đọc và ghi những gì, theo mẫu truy cập nào, với quy mô và tần suất ra sao, trong điều kiện đồng thời nào.

Bài học này phân loại các thao tác đọc, ghi, tìm kiếm điểm, quét phạm vi và tổng hợp. Đây là các mẫu truy cập thường gặp trong cả hệ thống giao dịch lẫn phân tích. Việc phân loại giúp dự đoán tài nguyên bị tiêu tốn, hiểu vì sao một chỉ mục có ích cho truy vấn này nhưng gây hại cho truy vấn khác, và xây dựng phép đo đại diện cho tải thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt thao tác đọc và ghi, đồng thời nhận ra một câu SQL có thể kết hợp nhiều loại công việc.
- Nhận diện point lookup, range scan, full scan và aggregation qua điều kiện truy vấn và execution plan.
- Giải thích ảnh hưởng của selectivity, cardinality, locality, working set, skew và concurrency đến chi phí truy cập.
- So sánh workload thiên về đọc, thiên về ghi và workload hỗn hợp; liên hệ chúng với OLTP và OLAP.
- Đánh giá tác động hai chiều của chỉ mục đối với truy vấn đọc, thao tác ghi, bộ nhớ và lưu trữ.
- Thu thập workload profile và kiểm chứng thay đổi bằng tải thử nghiệm có tính đại diện.

## 1. Workload là gì và vì sao phải phân loại?

Workload là tập hợp các thao tác mà ứng dụng gửi đến DBMS trong một khoảng thời gian, cùng với tần suất, dữ liệu đầu vào, mức đồng thời và yêu cầu thời gian phản hồi của chúng. Một workload không chỉ được mô tả bằng số truy vấn mỗi giây. Cần biết loại truy vấn, số dòng đọc hoặc thay đổi, số byte truyền, số lần truy cập chỉ mục, số transaction, tỷ lệ commit, thời gian chờ và phân bố tham số.

Ví dụ, hai hệ thống đều xử lý 1.000 request mỗi giây:

- Hệ thống A thực hiện 950 lần tra cứu theo khóa chính, mỗi lần trả về một dòng, và 50 lần cập nhật một dòng.
- Hệ thống B thực hiện 20 truy vấn báo cáo, mỗi truy vấn đọc hàng triệu dòng và tính tổng, cùng hàng trăm thao tác ghi theo lô.

Số request mỗi giây không cho biết hệ thống nào tiêu tốn nhiều CPU, I/O hoặc bộ nhớ hơn. Cần phân loại công việc trước khi đưa ra giả thuyết tối ưu.

Một workload profile hữu ích thường trả lời các câu hỏi:

- Tỷ lệ đọc, ghi và thao tác hỗn hợp là bao nhiêu?
- Các thao tác đọc là tra cứu một bản ghi, quét một khoảng, quét phần lớn bảng hay tổng hợp dữ liệu?
- Các thao tác ghi là thêm mới, cập nhật một vài hàng, cập nhật theo phạm vi, xóa hay upsert?
- Mỗi loại chạy bao nhiêu lần, với bao nhiêu dòng và bao nhiêu byte?
- Tham số có phân bố đều hay tập trung vào một số khóa nóng?
- Dữ liệu được truy cập có nằm trong cache không? Working set lớn đến đâu?
- Có bao nhiêu transaction chạy đồng thời? Chúng có tranh chấp cùng hàng, trang, index page hoặc tài nguyên không?
- Độ trễ p50, p95, p99 và thông lượng mong muốn là bao nhiêu?
- Có yêu cầu nhất quán, thứ tự, độ bền và thời gian hoàn tất theo lô nào?

Phân loại workload là bước mô tả thực tế. Nó chưa tự đưa ra giải pháp; nó giúp xác định đúng loại bằng chứng cần thu thập và tiêu chí đánh giá giải pháp.

## 2. Đọc và ghi: hai nhóm công việc cơ bản

### 2.1. Thao tác đọc

Thao tác đọc lấy dữ liệu để ứng dụng hiển thị, kiểm tra điều kiện, tính toán hoặc tạo báo cáo. Trong SQL, SELECT là hình thức phổ biến, nhưng không phải SELECT nào cũng có cùng chi phí. Một truy vấn có thể lấy một dòng theo khóa chính, quét một khoảng thời gian, đọc toàn bảng, nối nhiều bảng hoặc tổng hợp hàng triệu dòng.

Chi phí đọc phụ thuộc vào:

- Số dòng và số trang phải truy cập.
- Số cột cần lấy và độ rộng của mỗi dòng.
- Đường truy cập được chọn: index seek, index scan, table scan, sequential scan hoặc bitmap access.
- Mức độ dữ liệu có sẵn trong buffer cache.
- Chi phí lọc, join, sort và aggregate.
- Số dòng kết quả phải truyền đến client.
- Thời gian chờ khóa, I/O hoặc tài nguyên khác theo cơ chế đồng thời của DBMS.

Một truy vấn chỉ trả về một dòng vẫn có thể đắt nếu DBMS phải quét nhiều dữ liệu để tìm dòng đó. Ngược lại, một truy vấn trả về nhiều dòng có thể hiệu quả nếu đọc tuần tự một vùng dữ liệu phù hợp và xử lý theo pipeline.

### 2.2. Thao tác ghi

Thao tác ghi thay đổi trạng thái dữ liệu. Các nhóm phổ biến gồm:

- INSERT: thêm bản ghi mới.
- UPDATE: thay đổi giá trị của bản ghi hiện có.
- DELETE: xóa bản ghi.
- UPSERT hoặc MERGE: thêm mới nếu chưa có, hoặc cập nhật nếu đã tồn tại; cú pháp và ngữ nghĩa cụ thể phụ thuộc DBMS.
- Ghi theo lô (batch write): thực hiện nhiều thay đổi trong một transaction hoặc một nhóm thao tác.

Chi phí ghi không chỉ là ghi dữ liệu vào bảng. DBMS có thể phải cập nhật nhiều chỉ mục, kiểm tra ràng buộc, duy trì khóa ngoại, ghi transaction log hoặc write-ahead log, đồng bộ dữ liệu theo chính sách độ bền và xử lý xung đột với transaction khác.

Một bảng có nhiều chỉ mục có thể giúp đọc nhanh nhưng làm mỗi INSERT hoặc UPDATE tốn thêm công việc. Nếu một cột được cập nhật nằm trong nhiều chỉ mục, DBMS có thể phải thay đổi các entry tương ứng. Với chỉ mục phân cụm hoặc cấu trúc lưu trữ đặc thù, cập nhật khóa có thể còn dẫn đến di chuyển bản ghi hoặc chia trang.

### 2.3. Đọc và ghi không phải hai loại tách biệt tuyệt đối

Một transaction nghiệp vụ thường kết hợp nhiều thao tác. Ví dụ, đặt hàng có thể:

1. Đọc thông tin sản phẩm.
2. Kiểm tra tồn kho.
3. Cập nhật số lượng tồn.
4. Thêm đơn hàng và chi tiết đơn hàng.
5. Ghi lịch sử hoặc sự kiện.
6. Commit toàn bộ thay đổi.

Tổng chi phí và độ trễ của transaction phụ thuộc cả các thao tác đọc lẫn ghi, thời gian giữ khóa, mức đồng thời và cách chia ranh giới transaction. Khi phân tích, hãy xem xét toàn bộ đường đi nghiệp vụ, không chỉ câu SQL có thời gian riêng lẻ cao nhất.

## 3. Tìm kiếm điểm (point lookup)

### 3.1. Khái niệm

Point lookup là thao tác tìm một bản ghi hoặc một số rất ít bản ghi bằng điều kiện xác định một giá trị khóa. Ví dụ, lấy đơn hàng theo order_id hoặc tìm hồ sơ người dùng theo user_id.

~~~sql
SELECT order_id, customer_id, status, total
FROM orders
WHERE order_id = 830154;
~~~

Nếu order_id là khóa chính hoặc có chỉ mục phù hợp, DBMS thường có thể đi trực tiếp đến vị trí chứa bản ghi. Với B-tree index, quá trình tìm kiếm đi qua các trang nhánh đến trang lá, sau đó xác định vị trí dòng hoặc khóa tương ứng. Số bước thường tăng chậm theo số lượng entry của chỉ mục.

Point lookup thường có đặc điểm:

- Điều kiện lọc là phép so sánh bằng trên khóa chính hoặc khóa có tính duy nhất.
- Số dòng kết quả dự kiến rất nhỏ.
- Độ trễ mỗi lần tra cứu quan trọng, nhất là khi endpoint gọi nhiều lần.
- Tần suất có thể rất cao, vì vậy một chi phí nhỏ mỗi lần vẫn tạo ra tải đáng kể.
- Nếu truy cập khóa tập trung, một số trang hoặc hàng có thể trở thành điểm nóng.

### 3.2. Chỉ mục và khả năng bao phủ

Một chỉ mục phù hợp cho point lookup giúp DBMS xác định nhanh vị trí bản ghi. Nếu truy vấn chỉ cần những cột có sẵn trong chỉ mục, DBMS có thể tránh một lần truy cập bổ sung vào bảng trong các điều kiện mà hệ quản trị hỗ trợ. Khả năng này thường được gọi là covering index hoặc index-only access, tùy DBMS.

Ví dụ, nếu ứng dụng thường tìm đơn hàng theo order_id và chỉ lấy status, có thể cân nhắc một chỉ mục bao phủ. Tuy nhiên, nếu order_id đã là khóa chính và bản ghi nhỏ, thêm một chỉ mục riêng chỉ để chứa status có thể lãng phí dung lượng và làm tăng chi phí ghi. Cần kiểm tra kế hoạch thực thi và đo tác động trước khi quyết định.

### 3.3. Point lookup không luôn rẻ

Một phép tra cứu theo khóa vẫn có thể chậm trong các trường hợp:

- Không có chỉ mục phù hợp nên DBMS phải scan nhiều dòng.
- Kiểu dữ liệu hoặc biểu thức khiến điều kiện không khớp với cách tổ chức chỉ mục.
- Truy vấn lấy thêm nhiều cột ngoài chỉ mục, dẫn đến nhiều lần truy cập bảng.
- Các khóa được truy cập phân tán rộng khiến cache miss và I/O tăng.
- Nhiều transaction cập nhật cùng một hàng nóng, tạo lock contention.
- Ứng dụng thực hiện N+1 query: một truy vấn lấy danh sách rồi phát sinh một point lookup cho từng phần tử.
- Connection pool, mạng hoặc xử lý kết quả ở client chiếm phần lớn thời gian.

Một endpoint gọi 500 point lookup tuần tự có thể chậm hơn một truy vấn lấy dữ liệu theo lô, dù mỗi point lookup riêng lẻ rất nhanh. Khi đó cần xem số lần round-trip, batching và cách tổ chức truy vấn.

## 4. Quét phạm vi (range scan)

### 4.1. Khái niệm

Range scan lấy tất cả bản ghi có khóa nằm trong một khoảng hoặc thỏa điều kiện thứ tự. Ví dụ, lấy đơn hàng trong một khoảng thời gian hoặc các giao dịch có số tiền từ một ngưỡng đến ngưỡng khác.

~~~sql
SELECT order_id, created_at, total
FROM orders
WHERE created_at >= TIMESTAMP '2026-10-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-01 00:00:00'
ORDER BY created_at;
~~~

Với B-tree index trên created_at, DBMS có thể tìm vị trí bắt đầu của khoảng rồi đọc liên tiếp các entry phù hợp cho đến khi hết phạm vi. Cách này thường hiệu quả khi phạm vi chọn được một phần nhỏ hoặc vừa phải của dữ liệu và thứ tự chỉ mục hỗ trợ truy vấn.

### 4.2. Độ chọn lọc và kích thước phạm vi

Selectivity mô tả tỷ lệ dữ liệu thỏa điều kiện. Một điều kiện chọn 0,1% số dòng có độ chọn lọc cao theo nghĩa lọc được phần lớn dữ liệu; một điều kiện chọn 80% số dòng có độ chọn lọc thấp. Cách dùng thuật ngữ có thể khác giữa tài liệu, vì vậy khi trao đổi nên ghi rõ tỷ lệ dòng được chọn.

Ví dụ, nếu bảng có 10 triệu đơn hàng:

- Truy vấn một order_id có thể trả về một dòng.
- Truy vấn đơn hàng trong một giờ có thể trả về 2.000 dòng.
- Truy vấn đơn hàng trong một năm có thể trả về 9 triệu dòng.

Cùng dùng điều kiện trên created_at, nhưng ba truy vấn có khối lượng dữ liệu rất khác nhau. Khi phạm vi nhỏ, index range scan thường hữu ích. Khi phạm vi bao phủ phần lớn bảng, sequential scan có thể rẻ hơn việc đi qua chỉ mục rồi truy cập bảng cho từng dòng.

Không có một ngưỡng chọn lọc cố định áp dụng cho mọi hệ thống. Điểm chuyển giữa index access và table scan phụ thuộc kích thước dòng, thứ tự vật lý, cache, storage, số cột cần lấy, thống kê và chi phí mà optimizer ước lượng.

### 4.3. Thứ tự cột trong chỉ mục ghép

Với chỉ mục B-tree ghép, thứ tự cột quyết định những điều kiện nào có thể xác định vùng khóa liên tiếp hiệu quả. Chỉ mục trên (customer_id, created_at) thường phù hợp với truy vấn lọc customer_id bằng một giá trị và quét một khoảng created_at của khách hàng đó.

~~~sql
SELECT order_id, created_at, total
FROM orders
WHERE customer_id = 42
  AND created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-08 00:00:00'
ORDER BY created_at;
~~~

Một chỉ mục có customer_id đứng trước created_at có thể hỗ trợ mẫu truy vấn này vì điều kiện bằng xác định một nhóm khách hàng, sau đó điều kiện phạm vi quét các thời điểm trong nhóm đó. Nếu workload chủ yếu lọc theo khoảng thời gian trên mọi khách hàng, thứ tự cột khác có thể phù hợp hơn. Quyết định phải dựa trên tập truy vấn thực tế, không dựa vào một câu SQL đơn lẻ.

### 4.4. Range scan, phân trang và dữ liệu lớn

Đọc một phạm vi lớn có thể tiêu tốn nhiều I/O, bộ nhớ và băng thông. Khi phân trang, OFFSET lớn có thể buộc DBMS đọc và bỏ qua nhiều dòng trước khi trả về trang tiếp theo. Với tập dữ liệu lớn và có thứ tự ổn định, keyset pagination thường phù hợp hơn:

~~~sql
SELECT order_id, created_at, total
FROM orders
WHERE (created_at, order_id) > (TIMESTAMP '2026-11-01 10:00:00', 830154)
ORDER BY created_at, order_id
LIMIT 100;
~~~

Đây là ví dụ cú pháp PostgreSQL dùng so sánh bộ giá trị; DBMS khác có thể cần viết điều kiện tương đương bằng AND/OR. Cặp khóa sắp xếp cần tạo thứ tự xác định, thường gồm một cột thời gian và một khóa duy nhất để xử lý các dòng có cùng thời điểm.

Range scan cũng xuất hiện trong xử lý theo lô, dọn dữ liệu cũ, đọc log và ETL. Nếu một job quét phạm vi lớn, cần đánh giá thời gian hoàn tất, lượng dữ liệu đọc, ảnh hưởng lên cache của workload tương tác và khả năng chia nhỏ công việc theo partition hoặc khoảng khóa.

## 5. Quét toàn bảng và quét phần lớn dữ liệu

Full table scan đọc phần lớn hoặc toàn bộ bảng. Tên toán tử trong execution plan khác nhau theo DBMS, chẳng hạn sequential scan hoặc table scan. Full scan không mặc nhiên là xấu.

Nó có thể là lựa chọn hợp lý khi:

- Bảng nhỏ và nằm trong cache.
- Truy vấn cần phần lớn các dòng.
- Đọc tuần tự hiệu quả hơn nhiều lần truy cập ngẫu nhiên.
- Truy vấn tổng hợp cần xử lý phần lớn dữ liệu.
- Không có chỉ mục nào chọn lọc đủ tốt để giảm lượng đọc.

Full scan có thể là vấn đề khi một truy vấn lẽ ra chỉ cần vài dòng nhưng phải đọc hàng triệu dòng do thiếu chỉ mục hoặc điều kiện không thể sử dụng access path phù hợp. Nó cũng có thể gây áp lực I/O và đẩy các trang hữu ích khác khỏi cache khi chạy thường xuyên.

Khi thấy scan trong execution plan, hãy kiểm tra actual rows, số trang đọc, số dòng bị loại sau filter, kích thước bảng và phần trăm dữ liệu cần thiết. Đừng kết luận chỉ dựa trên tên toán tử.

## 6. Thao tác tổng hợp (aggregation)

### 6.1. Khái niệm

Aggregation biến nhiều dòng thành một hoặc nhiều giá trị tổng hợp. Các hàm thường gặp gồm COUNT, SUM, AVG, MIN và MAX. GROUP BY chia dữ liệu thành nhóm rồi tính kết quả cho từng nhóm.

~~~sql
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total) AS revenue
FROM orders
WHERE created_at >= DATE '2026-11-01'
  AND created_at <  DATE '2026-12-01'
GROUP BY customer_id;
~~~

Truy vấn này phải đọc các dòng trong khoảng thời gian, phân nhóm theo customer_id và tính số đơn hàng cùng doanh thu. Dù kết quả chỉ có vài nghìn dòng, đầu vào có thể chứa hàng triệu dòng. Vì vậy, kích thước kết quả nhỏ không có nghĩa chi phí truy vấn nhỏ.

### 6.2. Các cách thực hiện aggregation

Tùy DBMS và execution plan, aggregation có thể được thực hiện theo một số cách:

- **Hash aggregate:** dùng cấu trúc băm để lưu trạng thái tổng hợp cho từng nhóm. Thường hữu ích khi dữ liệu đầu vào không có thứ tự theo khóa nhóm. Nếu số nhóm lớn hoặc bộ nhớ không đủ, có thể phát sinh dữ liệu tạm.
- **Sort aggregate / stream aggregate:** sắp xếp hoặc tận dụng đầu vào đã có thứ tự theo khóa nhóm, sau đó tổng hợp từng nhóm liên tiếp. Có thể tránh hash table lớn nhưng chi phí sort có thể đáng kể nếu đầu vào chưa có thứ tự.
- **Scalar aggregate:** tổng hợp toàn bộ tập đầu vào thành một kết quả duy nhất, chẳng hạn COUNT(*) không có GROUP BY.

Việc optimizer chọn thuật toán nào phụ thuộc số dòng ước lượng, số nhóm, thứ tự dữ liệu, thống kê, bộ nhớ và khả năng song song hóa.

### 6.3. Những yếu tố làm aggregation đắt

- Đầu vào lớn do lọc không đủ sớm.
- Nhiều nhóm khác nhau khiến cấu trúc hash lớn.
- Khóa nhóm có phân bố lệch hoặc thống kê không chính xác.
- Sort phải xử lý tập dữ liệu lớn hoặc spill ra storage.
- Truy vấn đọc các cột rộng không cần thiết.
- GROUP BY hoặc DISTINCT được dùng trên dữ liệu có cardinality cao.
- Nhiều truy vấn báo cáo đồng thời cạnh tranh CPU, bộ nhớ và I/O.

Một cách cải thiện có thể là lọc dữ liệu trước khi tổng hợp, giảm cột cần đọc, dùng chỉ mục hỗ trợ thứ tự hoặc điều kiện lọc, phân vùng dữ liệu, hoặc duy trì summary table/materialized view khi nghiệp vụ chấp nhận dữ liệu tổng hợp được cập nhật theo lịch hay theo cơ chế cụ thể. Mỗi cách đều có chi phí duy trì và yêu cầu nhất quán riêng.

### 6.4. Aggregation và workload phân tích

Các truy vấn tổng hợp lớn thường xuất hiện trong workload OLAP hoặc báo cáo. Chúng có thể chạy lâu, đọc nhiều dữ liệu và tận dụng xử lý song song. Workload OLTP lại thường ưu tiên transaction ngắn, truy cập ít dòng và độ trễ thấp.

Hai loại workload có thể cùng chạy trên một hệ thống. Một truy vấn báo cáo quét toàn bảng có thể cạnh tranh I/O với các point lookup phục vụ API. Cần cân nhắc lịch chạy, replica đọc, phân vùng, tài nguyên riêng hoặc kiến trúc phân tích phù hợp nếu đo đạc cho thấy ảnh hưởng đáng kể.

## 7. Các kiểu ghi thường gặp

### 7.1. Insert và ghi nối tiếp

INSERT thêm dòng mới. Với bảng sự kiện hoặc nhật ký, dữ liệu có thể được ghi chủ yếu theo thời gian và thường tăng theo khóa tuần tự. Mẫu này có thể thuận lợi cho ghi nối tiếp, nhưng vẫn cần xem số lượng chỉ mục, transaction log, phân trang và mức đồng thời.

~~~sql
INSERT INTO events (event_id, occurred_at, event_type, payload)
VALUES (91001, CURRENT_TIMESTAMP, 'ORDER_CREATED', '{"orderId":830154}');
~~~

Nếu event_id tăng tuần tự, nhiều transaction có thể cùng ghi gần cuối B-tree index. Một số DBMS hoặc cấu hình có thể xuất hiện tranh chấp trên trang cuối (last-page contention). Giải pháp phụ thuộc hệ thống lưu trữ và DBMS; có thể cần xem chiến lược khóa, phân vùng, cách tạo khóa và chỉ số wait trước khi thay đổi.

### 7.2. Update và delete theo điểm

Cập nhật hoặc xóa một dòng theo khóa thường có thể dùng chỉ mục để xác định mục tiêu:

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 501;
~~~

Mặc dù chỉ thay đổi một dòng, thao tác này có thể chờ khóa nếu nhiều giao dịch cùng cập nhật sản phẩm 501. Đây là ví dụ về hot row. Tăng số kết nối hoặc tăng số worker không giải quyết được tranh chấp logic trên cùng một hàng.

Nếu update thay đổi cột có mặt trong nhiều chỉ mục, DBMS có thể phải duy trì các chỉ mục đó. Với MVCC, một số DBMS tạo phiên bản dòng mới thay vì ghi đè trực tiếp, sau đó cần cơ chế dọn dẹp phiên bản cũ. Vì vậy, chi phí update phụ thuộc cả cấu trúc bảng, chỉ mục, cơ chế đồng thời và tỷ lệ cập nhật.

### 7.3. Update và delete theo phạm vi

Một lệnh UPDATE hoặc DELETE có thể ảnh hưởng hàng nghìn hoặc hàng triệu dòng:

~~~sql
UPDATE orders
SET archive_flag = TRUE
WHERE created_at < DATE '2024-01-01'
  AND status = 'CANCELLED';
~~~

Đây là workload ghi theo phạm vi. DBMS phải xác định tập dòng phù hợp, khóa hoặc quản lý phiên bản của chúng, cập nhật dữ liệu và các chỉ mục liên quan, ghi log và duy trì ràng buộc. Transaction quá lớn có thể giữ khóa lâu, tạo lượng log lớn, tăng replication lag hoặc làm khó quá trình rollback và phục hồi.

Nếu nghiệp vụ cho phép, có thể chia thành các lô nhỏ theo khóa hoặc partition, commit theo từng lô và theo dõi tiến độ. Cần cân nhắc tính nguyên tử: chia lô đồng nghĩa toàn bộ công việc không còn được bảo đảm trong một transaction duy nhất. Cần thiết kế cách tiếp tục, retry và xử lý lỗi để không bỏ sót hoặc xử lý trùng dữ liệu.

### 7.4. Upsert và ghi theo lô

Upsert kết hợp kiểm tra tồn tại với thêm mới hoặc cập nhật. Nó hữu ích khi đồng bộ dữ liệu, ingest sự kiện hoặc xử lý bản ghi có khóa tự nhiên. Tuy nhiên, upsert vẫn phải kiểm tra xung đột duy nhất, duy trì chỉ mục và có thể tạo tranh chấp khi nhiều phiên ghi cùng một khóa.

Ghi theo lô giảm số lần round-trip và có thể tăng throughput, nhưng batch quá lớn làm tăng bộ nhớ, log, thời gian transaction và khả năng rollback. Kích thước lô cần được đo theo độ trễ, thông lượng, kích thước bản ghi, giới hạn giao thức và tải đồng thời.

## 8. So sánh workload thiên về đọc, thiên về ghi và hỗn hợp

| Đặc tính | Thiên về đọc | Thiên về ghi | Hỗn hợp |
|---|---|---|---|
| Công việc thường gặp | Point lookup, range scan, báo cáo | Insert, update, delete, upsert | Đọc kiểm tra rồi ghi, giao dịch nghiệp vụ |
| Tài nguyên thường nhạy cảm | Cache, I/O đọc, CPU, mạng | Log I/O, IOPS ghi, index maintenance, khóa | Cả đọc/ghi, contention và transaction |
| Vai trò của chỉ mục | Giảm lượng dữ liệu đọc, hỗ trợ thứ tự | Tăng chi phí duy trì khi ghi | Cân bằng lợi ích đọc và chi phí ghi |
| Rủi ro nổi bật | Scan lớn, cache miss, trả quá nhiều dữ liệu | Log tăng, hot row, lock wait, index bloat | Đọc và ghi cạnh tranh cùng dữ liệu |
| Cách đo quan trọng | Rows/bytes read, cache hit, latency | Rows written, log bytes, commit latency | Latency theo transaction, wait, throughput |

Không có một cấu hình tối ưu chung cho cả ba nhóm. Hệ thống thiên về đọc có thể chấp nhận thêm chỉ mục để giảm thời gian truy vấn nếu chi phí lưu trữ và ghi thấp. Hệ thống ingest nhiều dữ liệu cần hạn chế chỉ mục dư thừa và tối ưu ghi theo lô. Hệ thống hỗn hợp cần đánh giá tác động của mọi thay đổi trên cả truy vấn đọc lẫn ghi.

## 9. OLTP và OLAP: hai hình thái workload thường gặp

### 9.1. OLTP

Online Transaction Processing (OLTP) xử lý các giao dịch nghiệp vụ ngắn, thường có nhiều người dùng đồng thời. Các thao tác phổ biến gồm point lookup, insert, update hoặc một số range scan nhỏ. Yêu cầu thường nhấn mạnh độ trễ thấp, tính nhất quán, khả năng xử lý nhiều transaction và độ bền.

Ví dụ: đăng nhập, xem thông tin đơn hàng, đặt vé, cập nhật tồn kho và ghi nhận thanh toán.

Một workload OLTP có thể đạt số transaction mỗi giây cao dù mỗi transaction chỉ đọc hoặc thay đổi vài dòng. Chỉ số cần theo dõi gồm p95/p99 latency, transaction throughput, lock wait, deadlock, connection pool, log flush và số dòng đọc/ghi trung bình.

### 9.2. OLAP

Online Analytical Processing (OLAP) tập trung vào truy vấn phân tích, đọc lượng dữ liệu lớn, join nhiều nguồn, sort và aggregation. Một truy vấn có thể chạy lâu hơn nhưng xử lý hàng triệu hoặc hàng tỷ dòng. Mục tiêu thường là thông lượng phân tích và thời gian hoàn tất báo cáo.

Ví dụ: doanh thu theo tháng, phân tích hành vi khách hàng, tỷ lệ chuyển đổi, báo cáo tồn kho và xu hướng sử dụng dịch vụ.

Workload OLAP thường nhạy với scan throughput, CPU, bộ nhớ cho hash/sort, I/O tuần tự và khả năng song song. Nếu chạy chung với OLTP, truy vấn phân tích có thể gây ảnh hưởng đến cache và tài nguyên dùng chung.

### 9.3. Hệ thống thực tế thường pha trộn

Ranh giới OLTP/OLAP không phải lúc nào cũng tuyệt đối. Một hệ thống vận hành có thể chạy dashboard gần thời gian thực trên dữ liệu giao dịch, hoặc có truy vấn báo cáo ngắn xen kẽ nhiều point lookup. Cần phân loại theo hành vi thực tế của từng nhóm truy vấn và đo ảnh hưởng lên các nhóm còn lại.

## 10. Những thuộc tính workload làm thay đổi chi phí

### 10.1. Tần suất và thông lượng

Một truy vấn mất 20 ms nhưng chạy 10 lần mỗi phút có thể ít quan trọng hơn truy vấn mất 2 ms nhưng chạy 20.000 lần mỗi giây. Khi ưu tiên tối ưu, cần xem tổng thời gian tiêu thụ tài nguyên, tần suất, thông lượng và ảnh hưởng lên p95/p99.

Có thể ước lượng tổng thời gian DBMS dành cho một nhóm truy vấn bằng số lần chạy nhân với thời gian trung bình, nhưng phép tính này chỉ là chỉ báo ban đầu. Thời gian truy vấn có thể chồng lấp khi chạy đồng thời; cần xem CPU time, I/O và số liệu hệ thống để đánh giá tải thực.

### 10.2. Cardinality và selectivity

Cardinality là số lượng phần tử hoặc dòng trong một tập dữ liệu hay kết quả trung gian. Selectivity thể hiện mức độ điều kiện lọc thu hẹp dữ liệu. Hai thuộc tính này ảnh hưởng đến lựa chọn scan, index access, join và aggregation.

Thống kê không chính xác có thể khiến optimizer ước lượng sai cardinality. Khi actual rows khác xa estimated rows, hãy kiểm tra thống kê, phân bố dữ liệu, tương quan giữa các cột và giá trị tham số.

### 10.3. Data skew và hot key

Dữ liệu có thể phân bố lệch. Ví dụ, một khách hàng lớn chiếm 40% số đơn hàng, trong khi phần lớn khách hàng chỉ có vài đơn. Một giá trị trạng thái như ACTIVE có thể xuất hiện ở 95% dòng, còn trạng thái hiếm chỉ chiếm 0,01%.

Skew khiến cùng một mẫu truy vấn có chi phí khác nhau theo tham số. Nó cũng có thể tạo hot key: nhiều phiên đồng thời truy cập hoặc cập nhật cùng một khóa. Hãy đo phân bố tham số và nhóm truy vấn theo giá trị đại diện, thay vì chỉ benchmark một giá trị trung bình.

### 10.4. Locality và working set

Locality mô tả mức độ truy cập lặp lại vào cùng vùng dữ liệu hoặc vùng dữ liệu gần nhau. Working set là tập dữ liệu mà workload thường xuyên cần dùng trong một khoảng thời gian.

Nếu working set nằm vừa trong buffer cache, nhiều lần đọc có thể được phục vụ từ RAM. Nếu working set lớn hơn cache hoặc truy cập phân tán, cache miss và I/O có thể tăng. Một bài benchmark lặp lại cùng vài khóa có thể cho kết quả quá lạc quan vì dữ liệu luôn nóng trong cache, trong khi production truy cập nhiều khóa khác nhau.

### 10.5. Concurrency và burstiness

Concurrency là số thao tác hoặc transaction đang chạy đồng thời. Burstiness mô tả tải đến theo từng đợt thay vì đều đặn. Một hệ thống có throughput trung bình thấp vẫn có thể quá tải trong những đợt cao điểm.

Khi concurrency tăng, CPU, I/O, bộ nhớ, kết nối và khóa trở thành tài nguyên chia sẻ. Thời gian chờ có thể tăng nhanh gần điểm bão hòa. Vì vậy, cần benchmark ở nhiều mức đồng thời và theo dõi cả throughput lẫn latency. Tăng concurrency mà throughput không tăng trong khi p95/p99 xấu đi là dấu hiệu cần điều tra điểm bão hòa.

### 10.6. Working set thay đổi theo thời gian

Dữ liệu mới có thể được truy cập nhiều hơn dữ liệu cũ; mẫu truy cập cũng có thể thay đổi theo giờ, ngày hoặc mùa vụ. Ví dụ, hệ thống bán vé tập trung vào sự kiện sắp mở bán, còn hệ thống kế toán tăng tải vào cuối tháng. Benchmark cần phản ánh chu kỳ và phân bố dữ liệu có ý nghĩa với môi trường triển khai.

## 11. Tác động của chỉ mục lên từng loại workload

Chỉ mục là cấu trúc phụ trợ giúp DBMS tìm dữ liệu, nhưng mỗi chỉ mục đều có chi phí tạo, lưu trữ và bảo trì.

| Mẫu truy cập | Lợi ích chỉ mục có thể mang lại | Chi phí hoặc giới hạn |
|---|---|---|
| Point lookup | Tìm nhanh theo khóa | Duy trì entry khi dữ liệu thay đổi; truy cập bảng bổ sung nếu index không bao phủ |
| Range scan | Tìm điểm bắt đầu và đọc các khóa liên tiếp | Phạm vi quá rộng có thể khiến scan bảng rẻ hơn |
| Sort theo khóa | Có thể cung cấp dữ liệu đúng thứ tự | Thứ tự cột và chiều sắp xếp phải phù hợp |
| Aggregation | Có thể giảm dữ liệu đọc hoặc hỗ trợ thứ tự nhóm | Không loại bỏ chi phí xử lý nếu phải tổng hợp nhiều dòng |
| Insert | Chỉ mục hỗ trợ truy vấn sau khi ghi | Mỗi chỉ mục cần được cập nhật; có thể phát sinh page split hoặc contention |
| Update | Có thể tăng tốc tìm dòng cần sửa | Thay đổi cột khóa/chỉ mục làm phát sinh công việc duy trì |
| Delete | Có thể tìm nhanh dòng cần xóa | Phải xóa hoặc đánh dấu entry ở các chỉ mục liên quan |

Một workload đọc nhiều và ít thay đổi dữ liệu có thể chấp nhận nhiều chỉ mục hơn. Workload ghi nặng cần đánh giá nghiêm túc số lượng và độ rộng chỉ mục. Một chỉ mục ghép được thiết kế cho nhiều truy vấn có thể hiệu quả hơn nhiều chỉ mục đơn lẻ, nhưng chỉ khi các mẫu lọc và sắp xếp thực tế phù hợp.

Trước khi thêm chỉ mục, cần kiểm tra:

1. Truy vấn nào sẽ được cải thiện và tần suất chạy của chúng.
2. Execution plan hiện tại và lượng dữ liệu thực tế phải đọc.
3. Độ chọn lọc và thứ tự cột phù hợp với điều kiện.
4. Chỉ mục hiện có có thể phục vụ truy vấn hay không.
5. Dung lượng lưu trữ và chi phí INSERT, UPDATE, DELETE tăng thêm.
6. Tác động đến cache, thời gian tạo chỉ mục và hoạt động đồng thời.
7. Kết quả đo trước/sau trên workload có đại diện hay không.

## 12. Xây dựng workload profile từ dữ liệu đo

Một workload profile tốt giúp đội kỹ thuật ưu tiên đúng nhóm công việc. Có thể tổ chức dữ liệu theo nhóm truy vấn chuẩn hóa (query fingerprint), endpoint hoặc transaction nghiệp vụ.

### 12.1. Nhóm truy vấn

Gom các câu SQL có cùng cấu trúc nhưng khác giá trị tham số thành một nhóm. Với mỗi nhóm, ghi:

- Số lần chạy trong khoảng đo.
- Thời gian trung bình và p50/p95/p99.
- Tổng CPU time hoặc chỉ số tài nguyên tương đương nếu DBMS cung cấp.
- Số dòng và số trang đọc, số dòng trả về.
- Số dòng thêm, sửa hoặc xóa.
- Số byte log và thời gian commit nếu liên quan.
- Các wait event, lock wait hoặc deadlock.
- Execution plan và các giá trị tham số đại diện.

Không ghi giá trị nhạy cảm của người dùng vào log phân tích nếu không cần thiết; có thể dùng fingerprint, phân loại hoặc dữ liệu đã ẩn danh.

### 12.2. Phân loại theo hành vi

Ví dụ bảng workload profile:

| Nhóm | Mẫu thao tác | Tần suất | Dữ liệu mỗi lần | Độ trễ cần quan tâm |
|---|---|---:|---:|---|
| Tra cứu đơn hàng | Point lookup theo order_id | Rất cao | 1-2 dòng | p95/p99 |
| Lịch sử khách hàng | Range scan theo customer_id và thời gian | Cao | Vài trăm dòng | p95 và bytes trả về |
| Dashboard doanh thu | Filter + group + aggregate | Thấp đến vừa | Hàng triệu dòng đầu vào | Thời gian hoàn tất, CPU, I/O |
| Cập nhật tồn kho | Point update trên product_id | Cao | 1 dòng | Lock wait, commit latency |
| Lưu sự kiện | Batch insert | Cao theo đợt | Hàng trăm đến hàng nghìn dòng | Throughput, log I/O |

Các mức tần suất trong bảng chỉ minh họa cách phân loại. Khi lập profile thực tế, hãy thay bằng số đo từ production hoặc tải thử nghiệm đáng tin cậy.

### 12.3. Xác định truy vấn quan trọng

Không chỉ chọn truy vấn có thời gian chạy đơn lẻ cao nhất. Hãy xem tổng tác động:

- Truy vấn rất chậm nhưng hiếm khi chạy có thể ảnh hưởng đến một số tác vụ nền.
- Truy vấn nhanh nhưng chạy liên tục có thể chiếm phần lớn CPU hoặc I/O.
- Truy vấn có p99 rất cao có thể làm trải nghiệm một nhóm người dùng xấu dù trung bình tốt.
- Truy vấn ghi có thể có thời gian SQL ngắn nhưng giữ khóa lâu do transaction rộng.
- Truy vấn báo cáo có thể làm chậm nhóm OLTP khác vì tranh chấp tài nguyên.

Ưu tiên dựa trên tác động nghiệp vụ, tài nguyên tiêu thụ, độ trễ phân vị và mức độ rủi ro của thay đổi.

## 13. Thiết kế benchmark đại diện

Benchmark chỉ có ý nghĩa khi mô phỏng đúng loại công việc và phân bố dữ liệu cần đánh giá.

### Bước 1: Chọn nhóm truy vấn

Chọn các nhóm chiếm tỷ trọng đáng kể về số lần chạy, CPU, I/O, độ trễ hoặc tác động nghiệp vụ. Đưa cả thao tác đọc và ghi vào bộ benchmark nếu production có cả hai.

### Bước 2: Chuẩn bị dữ liệu và phân bố

Dữ liệu thử nghiệm cần có quy mô, phân bố khóa, tỷ lệ NULL, độ lệch và quan hệ giữa các bảng gần với môi trường cần đánh giá. Dùng vài nghìn dòng đồng đều để mô phỏng một bảng hàng chục triệu dòng có skew thường không đủ.

### Bước 3: Mô phỏng tham số

Chọn tham số theo phân bố thực tế: khóa phổ biến, khóa hiếm, khoảng thời gian nhỏ/lớn và các nhóm giá trị có độ chọn lọc khác nhau. Không chỉ chạy một tham số dễ dàng.

### Bước 4: Mô phỏng concurrency và burst

Tăng dần số client hoặc transaction đồng thời. Bao gồm các đợt tải cao nếu production có traffic burst. Đo cả thời gian phản hồi và thông lượng ở từng mức.

### Bước 5: Kiểm soát cache và trạng thái hệ thống

Phân biệt cache nóng và cache lạnh; giữ điều kiện so sánh tương đương. Ghi lại phiên bản DBMS, cấu hình, số liệu thống kê, trạng thái chỉ mục, kích thước dữ liệu và tài nguyên máy.

### Bước 6: Đo cả đọc, ghi và transaction

Với đọc, đo rows/bytes read, logical/physical reads, CPU và latency. Với ghi, đo rows written, log bytes, commit latency, lock wait và ảnh hưởng của chỉ mục. Với transaction hỗn hợp, đo thời gian hoàn tất toàn transaction và tỷ lệ lỗi/retry.

### Bước 7: So sánh trước và sau

Thực hiện nhiều lần chạy, dùng phân vị và thông lượng, đồng thời kiểm tra tính đúng đắn của kết quả. Một thay đổi có thể cải thiện point lookup nhưng làm range scan hoặc insert chậm hơn; cần xem toàn bộ workload.

## 14. Ví dụ thực tế: hệ thống bán hàng

Giả sử hệ thống bán hàng có các nghiệp vụ sau:

- Khách hàng mở trang chi tiết đơn hàng.
- Khách hàng xem lịch sử đơn hàng trong 90 ngày.
- Nhân viên xem doanh thu theo ngày và theo cửa hàng.
- Khách hàng đặt hàng và hệ thống trừ tồn kho.
- Dịch vụ nền ghi nhận sự kiện vận chuyển.

Có thể phân loại:

| Nghiệp vụ | Loại đọc/ghi | Mẫu truy cập | Chỉ số nên xem |
|---|---|---|---|
| Mở chi tiết đơn hàng | Đọc | Point lookup | Latency, index access, cache hit |
| Xem lịch sử 90 ngày | Đọc | Range scan | Rows read, range selectivity, bytes |
| Báo cáo doanh thu | Đọc | Aggregation | CPU, memory, sort/hash spill, scan volume |
| Đặt hàng | Đọc + ghi | Point lookup và point update/insert | Transaction latency, lock wait, commit |
| Ghi sự kiện vận chuyển | Ghi | Batch insert | Throughput, log I/O, index maintenance |

Một thay đổi chỉ mục có thể cải thiện lịch sử đơn hàng nhưng làm tăng chi phí lưu sự kiện nếu bảng có thêm chỉ mục tương ứng. Một báo cáo tổng hợp lớn có thể làm chậm API tra cứu nếu dùng chung cache, CPU và I/O. Một sản phẩm bán chạy có thể trở thành hot row khi nhiều đơn hàng cùng trừ tồn kho.

Cách điều tra phù hợp là đo từng nhóm nghiệp vụ và cả ảnh hưởng liên nhóm. Ví dụ, khi dashboard chạy, hãy so sánh p95/p99 của API tra cứu với thời điểm không chạy dashboard; quan sát I/O, CPU, cache và wait events. Nếu chỉ nhìn thời gian chạy riêng của dashboard, ta có thể bỏ qua ảnh hưởng lên người dùng tương tác.

## 15. Những sai lầm thường gặp khi phân loại workload

**Chỉ nhìn tỷ lệ SELECT/INSERT/UPDATE/DELETE.** Tỷ lệ câu lệnh không cho biết khối lượng dữ liệu. Một SELECT có thể đọc một dòng hoặc toàn bộ bảng; một UPDATE có thể sửa một dòng hoặc hàng triệu dòng.

**Coi mọi SELECT là đọc nhẹ.** Range scan rộng, join lớn và aggregation có thể tiêu tốn nhiều CPU, bộ nhớ và I/O.

**Coi mọi thao tác ghi là giống nhau.** Append insert, update một hàng nóng và delete theo phạm vi có cơ chế chi phí và tranh chấp rất khác nhau.

**Benchmark chỉ với một giá trị tham số.** Dữ liệu lệch và hot key khiến chi phí thay đổi lớn giữa các tham số.

**Dùng dữ liệu nhỏ và đồng đều.** Mô hình này thường làm cache và chỉ mục có vẻ hiệu quả hơn thực tế, đồng thời che giấu sai lệch cardinality.

**Chỉ đo throughput trung bình.** p95/p99 có thể xấu đi khi concurrency tăng dù thông lượng trung bình vẫn tăng nhẹ.

**Tối ưu một truy vấn và bỏ qua workload còn lại.** Chỉ mục, cấu hình bộ nhớ và thay đổi transaction đều có tác động lan sang các nhóm truy vấn khác.

**Cho rằng full scan luôn cần loại bỏ.** Scan tuần tự có thể là cách hiệu quả nhất khi truy vấn cần phần lớn dữ liệu.

## 16. Checklist phân loại và đánh giá workload

- [ ] Đã nhóm câu SQL theo fingerprint hoặc nghiệp vụ chưa?
- [ ] Đã phân loại từng nhóm thành đọc, ghi hay hỗn hợp chưa?
- [ ] Đã xác định point lookup, range scan, full scan và aggregation chưa?
- [ ] Đã ghi số lần chạy, rows/bytes read, rows written và kết quả trả về chưa?
- [ ] Đã xem selectivity, cardinality, skew và các tham số đại diện chưa?
- [ ] Đã xác định working set, locality và trạng thái cache chưa?
- [ ] Đã đo concurrency, burstiness, lock wait và transaction duration chưa?
- [ ] Đã đánh giá chi phí duy trì chỉ mục đối với INSERT/UPDATE/DELETE chưa?
- [ ] Đã benchmark với dữ liệu và tải gần production chưa?
- [ ] Đã so sánh latency phân vị, throughput, tài nguyên và tính đúng đắn trước/sau chưa?

## Kết luận

Phân loại workload là nền tảng để hiểu DBMS đang làm công việc gì và vì sao một thay đổi có thể cải thiện nhóm truy vấn này nhưng làm nhóm khác chậm đi. Point lookup thường tập trung vào việc tìm một số ít dòng; range scan đọc một khoảng khóa; full scan đọc phần lớn dữ liệu; aggregation xử lý nhiều dòng để tạo kết quả tổng hợp. Các thao tác ghi có thể là insert, update, delete hoặc upsert, với chi phí duy trì chỉ mục, ghi log, khóa và commit.

Hiệu năng còn phụ thuộc tần suất, cardinality, selectivity, skew, locality, working set, concurrency và burstiness. Vì vậy, hãy xây dựng workload profile từ số liệu thực tế, thiết kế benchmark với dữ liệu và tham số đại diện, rồi đo cả tác động đọc lẫn ghi. Khi đã hiểu rõ hình thái công việc, việc chọn chỉ mục, cải thiện SQL và điều chỉnh tài nguyên mới có cơ sở và có thể kiểm chứng.

