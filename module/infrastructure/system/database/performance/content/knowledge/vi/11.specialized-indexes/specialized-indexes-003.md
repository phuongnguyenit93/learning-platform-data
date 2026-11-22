# Chỉ mục băm và giới hạn đối với tìm kiếm phạm vi

Chỉ mục băm (hash index) là cấu trúc truy cập dữ liệu dùng hàm băm để biến khóa tìm kiếm thành một giá trị đại diện, từ đó xác định bucket hoặc vị trí cần tra cứu. Cấu trúc này thường phù hợp với truy vấn so sánh bằng trên toàn bộ khóa được lập chỉ mục. Nó không lưu các khóa theo thứ tự tăng dần như B-tree, vì vậy không hỗ trợ trực tiếp việc tìm một đoạn khóa liên tiếp, sắp xếp kết quả hoặc tìm tiền tố theo cách của B-tree.

Hiểu đúng khả năng và giới hạn của chỉ mục băm giúp chọn cấu trúc phù hợp với workload. Với một truy vấn tra cứu chính xác như tìm tài khoản theo mã định danh, hash index có thể là một lựa chọn đáng thử nếu hệ quản trị và loại bảng hỗ trợ. Với truy vấn lấy dữ liệu trong khoảng thời gian, tìm giá trị nhỏ nhất/lớn nhất, sắp xếp hoặc phân trang, B-tree thường phù hợp hơn. Quyết định cần dựa trên số liệu thực tế, execution plan và chi phí vận hành.

Nội dung thuộc chương **Chỉ mục chuyên biệt** của module DATABASE_PERFORMANCE. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; vì vậy, việc chọn hash index cần gắn với mẫu truy vấn thực tế, tần suất tra cứu, phân bố khóa, mức đồng thời, bộ nhớ và tác động đến thao tác ghi.

## 1. Nguyên lý hoạt động của hash index

Hash index sử dụng một hàm băm để ánh xạ giá trị khóa thành mã băm. Mã này được dùng để tìm bucket (ngăn chứa) tương ứng. Bucket có thể chứa một hoặc nhiều mục chỉ mục, tùy cấu trúc của hệ quản trị. Mỗi mục dẫn đến bản ghi hoặc vị trí lưu trữ cần kiểm tra.

Quy trình tra cứu khái quát:

1. Nhận giá trị khóa từ điều kiện truy vấn.
2. Tính mã băm bằng hàm băm phù hợp với kiểu dữ liệu và quy tắc so sánh.
3. Dùng mã băm để xác định bucket.
4. Kiểm tra các mục trong bucket để tìm ứng viên khớp.
5. Xác nhận khóa thực tế bằng phép so sánh chính xác, nếu cần, rồi truy cập bản ghi.

Ví dụ, ứng dụng thường xuyên tra cứu tài khoản bằng mã khách hàng:

~~~sql
SELECT customer_id, customer_name, account_status
FROM customers
WHERE customer_id = ?;
~~~

Nếu hash index được hỗ trợ cho cột customer_id, hệ quản trị có thể tính hash của giá trị tham số và tìm bucket tương ứng thay vì duyệt lần lượt các khóa theo thứ tự. Hash index thường hướng đến tra cứu bằng chính xác (exact-match lookup), tức tìm một giá trị cụ thể.

### Bucket và va chạm hash

Hàm băm ánh xạ một không gian khóa lớn vào một không gian mã hoặc bucket hữu hạn. Vì vậy, hai khóa khác nhau có thể tạo ra cùng mã băm hoặc cùng bucket. Hiện tượng này gọi là va chạm (collision).

Va chạm không làm sai kết quả nếu hệ quản trị xác minh khóa thực tế trước khi trả bản ghi. Khi nhiều khóa cùng bucket, hệ quản trị phải kiểm tra thêm các mục ứng viên; bucket có nhiều va chạm có thể làm truy vấn chậm hơn dự kiến.

Một hàm băm tốt cần phân phối khóa tương đối đều trên các bucket đối với dữ liệu thực tế. Tuy nhiên, chất lượng phân phối còn phụ thuộc vào kiểu dữ liệu, mẫu giá trị, số bucket và cách triển khai của hệ quản trị. Không thể suy ra hiệu năng chỉ từ việc chỉ mục có sử dụng hash.

### Độ phức tạp tra cứu

Trong điều kiện phân phối tốt và tải phù hợp, hash lookup thường có chi phí tra cứu kỳ vọng gần O(1) theo số mục cần tìm. Đây là mô tả trung bình của cấu trúc băm, không phải cam kết thời gian hằng số cho mọi trường hợp. Va chạm nhiều, bucket quá tải, truy cập bộ nhớ không thuận lợi, đồng thời cao hoặc I/O có thể làm chi phí tăng đáng kể.

B-tree thường cần đi qua một số mức nút theo chiều cao cây, với chi phí tìm kiếm gần O(log n), nhưng có ưu điểm duy trì thứ tự khóa và hỗ trợ nhiều loại truy vấn. Trong thực tế, B-tree có thể rất nhanh nhờ cache, fan-out lớn và các trang được tổ chức hiệu quả. Không nên kết luận hash index luôn nhanh hơn B-tree chỉ dựa trên ký hiệu độ phức tạp.

## 2. Hash index phù hợp với loại điều kiện nào?

Hash index chủ yếu phục vụ phép so sánh bằng trên khóa được lập chỉ mục. Cần phân biệt điều kiện equality với điều kiện phạm vi và điều kiện thứ tự.

| Dạng truy vấn | Hash index | B-tree |
| --- | --- | --- |
| Khóa = giá trị cụ thể | Thường phù hợp | Phù hợp |
| Khóa IN (một số giá trị) | Có thể cần nhiều lần tra cứu bằng, tùy hệ quản trị | Phù hợp |
| Khóa >, <, >=, <= | Không hỗ trợ tìm vùng khóa theo thứ tự | Phù hợp |
| BETWEEN hai giá trị | Không phù hợp | Phù hợp |
| ORDER BY khóa | Không cung cấp thứ tự khóa | Có thể cung cấp thứ tự |
| MIN/MAX trên khóa | Không thể khai thác thứ tự hash để tìm trực tiếp đầu/cuối | Có thể phù hợp |
| Tìm tiền tố chuỗi như LIKE 'ABC%' | Không hỗ trợ theo thứ tự tiền tố | Có thể hỗ trợ tùy collation và biểu thức |
| Tìm kiếm toàn văn bản hoặc không gian | Cần loại chỉ mục chuyên biệt tương ứng | B-tree không thay thế chỉ mục chuyên biệt |

Khả năng chính xác còn tùy sản phẩm, phiên bản, loại chỉ mục và toán tử được hỗ trợ. Bảng trên mô tả đặc tính phổ biến của hash index, không phải danh sách cam kết cho mọi hệ quản trị.

### Tra cứu bằng chính xác

Ví dụ:

~~~sql
SELECT session_id, expires_at
FROM sessions
WHERE session_token = ?;
~~~

Nếu session_token là khóa có quy tắc so sánh rõ ràng và workload chủ yếu tra cứu bằng, hash index có thể là ứng viên để thử. Nếu truy vấn cũng cần lấy các phiên hết hạn theo thời gian, cấu trúc băm không đáp ứng trực tiếp phần truy vấn đó.

### Tìm kiếm phạm vi

Ví dụ:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= ?
  AND created_at < ?
ORDER BY created_at;
~~~

Hash index trên created_at không thể xác định một vùng liên tiếp từ giá trị bắt đầu đến giá trị kết thúc, vì các giá trị đã được ánh xạ sang bucket thay vì lưu theo thứ tự. Một B-tree trên created_at thường phù hợp hơn cho truy vấn này.

### Tìm tiền tố và sắp xếp

Truy vấn:

~~~sql
SELECT customer_id, customer_name
FROM customers
WHERE customer_name LIKE 'Nguyen%';
~~~

Hash index không giữ quan hệ thứ tự giữa các chuỗi, nên không thể đi đến vùng chứa mọi giá trị bắt đầu bằng Nguyen theo cách quét một khoảng B-tree. Với tìm kiếm tiền tố, B-tree có thể được dùng trong một số hệ quản trị và collation; cần kiểm tra quy tắc so sánh chuỗi, biểu thức và execution plan. Tìm kiếm chứa chuỗi ở giữa, tìm gần đúng hoặc toàn văn bản có thể cần giải pháp khác.

## 3. Vì sao hash index không hỗ trợ tìm kiếm phạm vi?

Hash function được thiết kế để phân tán các giá trị khóa. Hai giá trị gần nhau về mặt logic không nhất thiết có mã băm gần nhau hoặc rơi vào bucket liền kề.

Ví dụ các khóa thời gian:

| Giá trị khóa | Bucket minh họa |
| --- | --- |
| 2026-04-01 | 17 |
| 2026-04-02 | 4 |
| 2026-04-03 | 29 |
| 2026-04-04 | 11 |

Các ngày liên tiếp được phân tán đến những bucket khác nhau. Khi truy vấn yêu cầu ngày từ 01 đến 04 tháng 04, hệ quản trị không thể chỉ quét các bucket từ vị trí bắt đầu đến vị trí kết thúc như với B-tree. Nó có thể phải kiểm tra nhiều hoặc toàn bộ bucket, làm mất lợi ích của tra cứu băm.

Đây là giới hạn cốt lõi của cấu trúc: hash index giữ khả năng xác định bucket từ một giá trị, nhưng không giữ thứ tự so sánh giữa các giá trị.

### Những phép toán không thể tận dụng thứ tự hash

- Tìm tất cả khóa nằm trong một khoảng.
- Tìm khóa lớn hơn hoặc nhỏ hơn một mốc.
- Trả kết quả theo thứ tự tăng hoặc giảm của khóa.
- Tìm khóa nhỏ nhất hoặc lớn nhất bằng cách đi đến đầu/cuối chỉ mục.
- Tìm tiền tố hoặc một đoạn chuỗi theo thứ tự từ điển.
- Tiếp tục phân trang theo thứ tự khóa nếu cần định vị từ khóa trước/sau.

Nếu workload có cả truy vấn equality và range trên cùng một cột, cần cân nhắc B-tree làm chỉ mục chính. B-tree có thể hỗ trợ equality lẫn range, trong khi hash index chỉ phục vụ nhóm điều kiện hẹp hơn. Một hash index bổ sung chỉ hợp lý khi phép đo chứng minh nó mang lại lợi ích đủ lớn và chi phí duy trì được chấp nhận.

## 4. So sánh hash index và B-tree index

| Tiêu chí | Hash index | B-tree index |
| --- | --- | --- |
| Tổ chức khóa | Ánh xạ khóa vào mã băm/bucket | Duy trì khóa theo thứ tự |
| Tra cứu equality | Là trường hợp sử dụng chính | Được hỗ trợ |
| Tra cứu range | Không phải mục tiêu thiết kế | Được hỗ trợ |
| ORDER BY | Không cung cấp thứ tự khóa | Có thể cung cấp thứ tự |
| Prefix search | Không dựa được vào thứ tự chuỗi | Có thể hỗ trợ tùy điều kiện |
| Va chạm | Có thể nhiều khóa cùng bucket, cần xác minh | Không có khái niệm collision theo cách của hash |
| Hiệu năng | Phụ thuộc phân phối hash, bucket, cache và triển khai | Phụ thuộc chiều cao cây, độ rộng trang, cache và phân bố khóa |
| Tính linh hoạt truy vấn | Hẹp hơn, chủ yếu equality | Rộng hơn |
| Tính khả dụng | Phụ thuộc hệ quản trị và engine | Phổ biến ở hệ quản trị quan hệ |

Không có kết luận chung rằng hash index luôn nhanh hơn hoặc luôn tiết kiệm dung lượng hơn. Một B-tree được cache tốt có thể phục vụ equality rất hiệu quả; một hash index có nhiều va chạm hoặc truy cập bộ nhớ kém có thể không đem lại lợi ích. Hãy đo trên phiên bản, engine, dữ liệu và tải thực tế.

## 5. Những khác biệt theo hệ quản trị

Tên gọi hash index không có nghĩa mọi hệ quản trị triển khai cùng một cấu trúc hoặc cung cấp cùng tính năng. Cần xác định rõ loại hash index đang nói đến.

### PostgreSQL

PostgreSQL cung cấp hash access method cho chỉ mục trên một cột, phục vụ phép so sánh bằng được hỗ trợ bởi operator class tương ứng. Ví dụ:

~~~sql
CREATE INDEX idx_customers_customer_id_hash
ON customers USING HASH (customer_id);
~~~

Hash index của PostgreSQL không hỗ trợ unique constraint và không cung cấp thứ tự để xử lý range hoặc ORDER BY. Cấu trúc lưu mã hash và khi tra cứu cần kiểm tra lại giá trị thực tế để xử lý va chạm. Vì thế, kết quả vẫn chính xác; va chạm có thể làm tăng số ứng viên phải kiểm tra.

Không nên giả định có thể tạo hash index nhiều cột trong PostgreSQL theo cú pháp composite B-tree. Hash access method này chỉ hỗ trợ một cột cho mỗi chỉ mục. Nếu cần điều kiện equality trên nhiều cột, hãy xem B-tree composite index hoặc chiến lược khác phù hợp với phiên bản và workload.

### SQL Server memory-optimized tables

SQL Server hỗ trợ hash index cho bảng memory-optimized. Hash index được tổ chức theo bucket và cần cấu hình số bucket (BUCKET_COUNT). Đây là cơ chế gắn với In-Memory OLTP, không phải một lựa chọn thay thế tổng quát cho mọi bảng rowstore thông thường.

Ví dụ minh họa cú pháp:

~~~sql
CREATE TABLE dbo.CustomerSession
(
    SessionId bigint NOT NULL,
    CustomerId bigint NOT NULL,
    ExpiresAt datetime2 NOT NULL,
    INDEX IX_CustomerSession_SessionId
        HASH (SessionId) WITH (BUCKET_COUNT = 100000)
)
WITH (MEMORY_OPTIMIZED = ON, DURABILITY = SCHEMA_AND_DATA);
~~~

Hash index của memory-optimized table phù hợp với equality lookup trên toàn bộ tập cột khóa. Truy vấn chỉ cung cấp một phần khóa của hash index nhiều cột có thể không tận dụng được đường tra cứu hash như mong muốn. Nó không hỗ trợ range scan hoặc thứ tự khóa; SQL Server cũng cung cấp nonclustered index dạng range cho memory-optimized table khi workload cần các thao tác đó.

BUCKET_COUNT cần được chọn dựa trên số lượng khóa duy nhất dự kiến và đặc điểm tăng trưởng. Quá ít bucket làm chuỗi va chạm dài; quá nhiều bucket tiêu tốn bộ nhớ. Hãy xem tài liệu phiên bản SQL Server đang dùng để chọn cấu hình và hiểu giới hạn của engine.

### MySQL và các loại hash index

MySQL có thể cung cấp hash index trong một số engine hoặc cấu trúc nhất định, chẳng hạn chỉ mục HASH của MEMORY engine. Các chỉ mục HASH này phục vụ equality lookup và không hỗ trợ range hoặc thứ tự khóa như BTREE. InnoDB có Adaptive Hash Index là cơ chế nội bộ có thể xây dựng dựa trên các truy cập lặp lại; đây không phải một chỉ mục HASH do người dùng khai báo bằng câu lệnh CREATE INDEX thông thường.

Vì vậy, khi nói đến hash index trong MySQL, cần phân biệt engine lưu trữ và cơ chế cụ thể. Không nên suy luận rằng bảng InnoDB có thể được chuyển sang một hash index do người dùng tự thiết kế giống MEMORY engine.

### Nguyên tắc áp dụng

Trước khi viết DDL, hãy xác nhận:

- Hệ quản trị và phiên bản có hỗ trợ hash index cho loại bảng đang dùng hay không.
- Hash index có giới hạn một cột hay hỗ trợ nhiều cột.
- Toán tử equality, kiểu dữ liệu và quy tắc so sánh nào được hỗ trợ.
- Có hỗ trợ unique, NULL, partitioning hoặc index-only access hay không.
- Hash index nằm trên đĩa hay trong bộ nhớ và cách nó xử lý va chạm.
- Công cụ execution plan hiển thị việc sử dụng chỉ mục như thế nào.

## 6. Chỉ mục băm nhiều cột và khóa đầy đủ

Một số hệ quản trị hỗ trợ hash index có nhiều cột khóa, nhưng cách tra cứu thường yêu cầu cung cấp giá trị equality cho toàn bộ khóa. Ví dụ, với khóa băm (tenant_id, external_id), truy vấn phù hợp có thể là:

~~~sql
SELECT record_id, payload
FROM external_records
WHERE tenant_id = ?
  AND external_id = ?;
~~~

Nếu chỉ có điều kiện tenant_id mà thiếu external_id, hệ quản trị có thể không xác định được bucket theo đầy đủ khóa và không sử dụng hash index hiệu quả. Hành vi cụ thể phụ thuộc engine; PostgreSQL hash index không hỗ trợ composite key, trong khi một số triển khai in-memory có thể hỗ trợ khóa nhiều cột.

Với B-tree (tenant_id, external_id), tiền tố trái có thể hỗ trợ truy vấn chỉ lọc tenant_id và truy vấn lọc cả hai cột. Đây là lợi thế quan trọng khi workload cần truy vấn theo nhiều mức khóa.

Không nên nhầm hash index nhiều cột với một hàm ứng dụng tự nối chuỗi hai giá trị rồi băm thành một cột duy nhất. Cách tự tạo khóa tổng hợp cần xử lý ranh giới, mã hóa, NULL, collation, va chạm và thay đổi định dạng; nó còn có thể làm mất khả năng tra cứu từng thành phần. Chỉ sử dụng khóa tổng hợp khi thiết kế dữ liệu và tính duy nhất đã được xác định rõ.

## 7. Phân bố khóa, va chạm và kích thước bucket

Hiệu năng của hash index phụ thuộc đáng kể vào cách các khóa được phân phối. Khi nhiều khóa rơi vào cùng bucket, một lần tra cứu phải kiểm tra nhiều mục hơn. Số bucket và cách xử lý bucket đầy khác nhau theo hệ quản trị.

### Bucket quá ít

Nếu số bucket nhỏ hơn nhiều so với số khóa duy nhất, nhiều khóa sẽ chia sẻ bucket. Chuỗi va chạm dài có thể làm tra cứu chậm và tăng chi phí cập nhật. Với hash index cần cấu hình bucket count, hãy ước lượng số khóa duy nhất trong suốt vòng đời dự kiến, không chỉ số dòng tại ngày triển khai.

### Bucket quá nhiều

Tạo quá nhiều bucket có thể lãng phí bộ nhớ hoặc dung lượng cấu trúc. Với hash index trong bộ nhớ, bucket array lớn chiếm một phần ngân sách RAM mà ứng dụng và dữ liệu cần sử dụng. Khi hệ thống tăng trưởng, cấu hình ban đầu có thể không còn phù hợp.

### Dữ liệu lệch và hash distribution

Một cột có phân bố giá trị lệch không nhất thiết đồng nghĩa hàm băm phân phối bucket kém; hàm băm tốt có thể phân tán các giá trị phổ biến khác nhau. Tuy nhiên, nhiều bản ghi có cùng một khóa logic vẫn phải được xử lý như nhiều mục trùng khóa, và một khóa nóng có thể tạo tải truy cập tập trung. Cần phân biệt va chạm do hash code/bucket với hotspot do cùng một giá trị khóa được truy cập thường xuyên.

### Theo dõi chỉ số phù hợp

Tùy hệ quản trị, có thể theo dõi:

- Số bucket và số khóa duy nhất.
- Số mục trung bình hoặc lớn nhất trong một bucket.
- Tỷ lệ bucket trống và phân bố va chạm.
- Chi phí bộ nhớ của bucket array.
- Số lần tra cứu, thời gian tra cứu và mức độ sử dụng chỉ mục.
- Lock/latch hoặc contention trên các vùng dữ liệu nóng.

Không phải hệ quản trị nào cũng công khai toàn bộ số liệu bucket. Dùng thống kê mà nền tảng cung cấp và kết hợp với đo độ trễ, CPU, memory, I/O để đánh giá.

## 8. Kiểu dữ liệu và quy tắc so sánh

Hash index chỉ hoạt động đúng khi hàm băm và phép so sánh khóa tương thích. Những giá trị được xem là bằng nhau theo ngữ nghĩa SQL phải được xử lý nhất quán trong cấu trúc chỉ mục.

Các yếu tố cần quan tâm:

- **Kiểu dữ liệu:** chuyển đổi kiểu ngầm định có thể khiến truy vấn không sử dụng được chỉ mục hoặc làm thay đổi cách so sánh.
- **Collation:** chuỗi có thể được so sánh phân biệt hoa thường hoặc theo quy tắc ngôn ngữ; hàm băm phải tương thích với ngữ nghĩa này.
- **Chuẩn hóa dữ liệu:** nếu ứng dụng chuẩn hóa mã trước khi ghi nhưng không chuẩn hóa tham số khi tìm, kết quả có thể không khớp như mong muốn.
- **NULL:** phép so sánh = NULL không trả về true trong SQL; cách hash index xử lý NULL và khả năng dùng với IS NULL phụ thuộc hệ quản trị.
- **Kiểu tùy biến:** operator class hoặc hàm băm cần được hỗ trợ và bảo đảm nhất quán với toán tử equality.

Ví dụ, nếu mã người dùng được xem là không phân biệt hoa thường, cần thống nhất cách chuẩn hóa hoặc collation giữa lúc lưu và lúc tra cứu. Không nên tự băm chuỗi đã chuyển chữ thường trong ứng dụng trong khi hệ quản trị so sánh theo một quy tắc khác, trừ khi khóa chuẩn hóa đó là một phần rõ ràng của mô hình dữ liệu.

## 9. Hash index không đồng nghĩa với hash join hoặc hash partitioning

Các kỹ thuật cùng dùng hàm băm nhưng giải quyết bài toán khác nhau:

| Khái niệm | Mục đích | Thời gian tồn tại |
| --- | --- | --- |
| Hash index | Tạo đường truy cập để tìm bản ghi theo khóa equality | Cấu trúc chỉ mục được duy trì cùng dữ liệu |
| Hash join | Nối hai tập dữ liệu bằng cách xây dựng và dò hash table trong quá trình thực thi truy vấn | Thường tồn tại trong thời gian thực thi toán tử |
| Hash partitioning | Phân phối dòng dữ liệu vào các phân vùng dựa trên hash của khóa | Là cách tổ chức/phân phối dữ liệu lâu dài |
| Hash aggregate | Gom nhóm hoặc tính tổng hợp bằng cấu trúc hash trong lúc thực thi | Thường tồn tại trong thời gian thực thi toán tử |

Một truy vấn có thể dùng hash join dù không có hash index. Ngược lại, một hash index có thể phục vụ equality lookup mà không cần hash join. Hash partitioning cũng không tự động tạo ra một hash index cho các truy vấn trên bảng.

Không nên nhìn thấy từ hash trong execution plan rồi kết luận truy vấn đang dùng hash index. Cần đọc tên toán tử và đường truy cập cụ thể của hệ quản trị.

## 10. Khi nào nên cân nhắc hash index?

Hash index đáng được xem xét khi workload có những đặc điểm sau:

- Phần lớn truy vấn mục tiêu là equality lookup trên toàn bộ khóa.
- Khóa có kiểu dữ liệu và phép so sánh được hỗ trợ tốt.
- Không cần range scan hoặc thứ tự từ chính cột khóa đó.
- Số khóa và mức tăng trưởng có thể ước lượng.
- Hệ quản trị hỗ trợ hash index cho đúng loại bảng và môi trường triển khai.
- Có số liệu chứng minh B-tree hiện tại hoặc đường truy cập khác đang là nút thắt.
- Chi phí bộ nhớ, va chạm, cập nhật và vận hành được chấp nhận.

Ví dụ workload có thể phù hợp là tra cứu session theo token, tra cứu bản ghi theo mã ngoài duy nhất hoặc truy cập bảng memory-optimized bằng toàn bộ khóa equality. Tuy nhiên, B-tree vẫn có thể là lựa chọn tốt hơn nhờ tính linh hoạt, khả năng range và độ trưởng thành của hệ quản trị.

### Khi không nên ưu tiên hash index

- Truy vấn cần tìm một khoảng giá trị.
- Truy vấn cần ORDER BY, MIN, MAX hoặc phân trang theo khóa.
- Nhiều truy vấn chỉ cung cấp một phần của khóa composite.
- Dữ liệu tăng nhanh nhưng không thể dự đoán hoặc cấp phát bucket/memory hợp lý.
- Workload có tỷ lệ ghi cao và chi phí duy trì hash index vượt lợi ích đọc.
- Hệ quản trị hoặc engine không hỗ trợ loại hash index mong muốn.
- Chưa có bằng chứng cho thấy B-tree hoặc cách truy cập hiện tại là nút thắt.

## 11. Quy trình đánh giá hash index bằng số liệu

Trước khi tạo hash index, hãy xác định mẫu truy vấn và đo baseline:

1. **Thu thập workload:** xác định fingerprint, tần suất, tỷ lệ equality/range, số lần tra cứu, p50/p95/p99 và tổng thời gian.
2. **Xác nhận hệ quản trị:** kiểm tra phiên bản, engine, kiểu dữ liệu, giới hạn khóa và toán tử được hỗ trợ.
3. **Đánh giá khóa:** xem số khóa duy nhất, giá trị trùng, mức tăng trưởng, hotspot và quy tắc so sánh.
4. **Đọc execution plan:** xác định đường truy cập hiện tại, số dòng đọc, lookup, scan và thời gian thực tế.
5. **Thiết kế thử nghiệm:** xác định hash index có thể tạo, bucket count hoặc giới hạn bộ nhớ nếu cần; chuẩn bị workload equality và workload phụ để đo tác động.
6. **Đo trong môi trường đại diện:** giữ dữ liệu, cache, số client và tốc độ yêu cầu tương đương; kiểm tra cả đọc và ghi.
7. **Đánh giá va chạm và tài nguyên:** theo dõi bucket, bộ nhớ, CPU, I/O, contention và dung lượng nếu nền tảng cung cấp.
8. **So sánh với B-tree:** đo cùng truy vấn và điều kiện; không chỉ so sánh cost estimate mà cần xem latency, throughput và tác động toàn workload.
9. **Theo dõi sau triển khai:** quan sát mức tăng trưởng khóa, truy vấn range, lỗi và các chức năng dùng chung.

### Các chỉ số nên so sánh

| Chỉ số | Câu hỏi |
| --- | --- |
| p50/p95/p99 của equality lookup | Tra cứu chính xác có nhanh và ổn định hơn không? |
| QPS/TPS ở cùng mức tải | Hệ thống có xử lý được nhiều yêu cầu hơn không? |
| CPU và memory | Hash lookup có giảm tổng chi phí hay tiêu tốn thêm tài nguyên? |
| Số lần va chạm/độ dài bucket chain | Phân phối khóa có phù hợp không? |
| Lock/latch contention | Có hotspot hoặc tranh chấp mới không? |
| Tốc độ INSERT/UPDATE/DELETE | Chi phí duy trì chỉ mục ảnh hưởng ghi ra sao? |
| Range scan và ORDER BY | Các truy vấn cần thứ tự có bị suy giảm hoặc vẫn phải dùng đường truy cập khác? |
| Dung lượng và bảo trì | Chi phí dài hạn có chấp nhận được không? |

Nếu hệ quản trị không cung cấp số liệu va chạm, có thể đánh giá gián tiếp qua latency, CPU, mức sử dụng memory và thống kê chỉ mục. Ghi rõ giới hạn quan sát trong báo cáo.

## 12. Ví dụ thực hành: tra cứu session và truy vấn hết hạn

Một dịch vụ quản lý phiên đăng nhập có bảng sessions:

~~~sql
CREATE TABLE sessions
(
    session_token varchar(128) NOT NULL,
    customer_id bigint NOT NULL,
    created_at timestamp NOT NULL,
    expires_at timestamp NOT NULL
);
~~~

Ứng dụng thường xuyên kiểm tra token:

~~~sql
SELECT customer_id, expires_at
FROM sessions
WHERE session_token = ?;
~~~

Đây là truy vấn equality trên một khóa có thể được thiết kế để duy nhất. Hash index có thể là ứng viên nếu engine hỗ trợ và phép đo cho thấy lợi ích. Tuy nhiên, dịch vụ cũng có tác vụ xóa phiên hết hạn:

~~~sql
DELETE FROM sessions
WHERE expires_at < CURRENT_TIMESTAMP;
~~~

Truy vấn xóa cần tìm một phạm vi thời gian. Hash index trên expires_at không hỗ trợ trực tiếp range scan. B-tree trên expires_at phù hợp hơn cho tác vụ này.

Một thiết kế có thể cần hai đường truy cập:

- Chỉ mục phù hợp với equality lookup theo session_token.
- B-tree theo expires_at để tìm các phiên hết hạn.

Nếu hệ quản trị không hỗ trợ hash index phù hợp, một B-tree trên session_token vẫn có thể phục vụ truy vấn equality rất tốt. Không nên thêm hash index chỉ vì tên gọi phù hợp với truy vấn. Hãy đo mức cải thiện so với B-tree và tính cả chi phí cập nhật hai chỉ mục trên mỗi thao tác tạo hoặc gia hạn session.

## 13. Các sai lầm thường gặp

- **Dùng hash index cho range:** hash không giữ thứ tự khóa nên không thể tìm vùng liên tiếp hiệu quả.
- **Cho rằng hash index luôn nhanh hơn B-tree:** hiệu năng thực tế phụ thuộc triển khai, cache, phân bố, va chạm và workload.
- **Nhầm hash index với hash join:** hai cơ chế có mục đích và vòng đời khác nhau.
- **Bỏ qua va chạm:** nhiều khóa cùng bucket có thể làm tăng số ứng viên phải kiểm tra.
- **Chọn bucket count theo số dòng hiện tại:** không tính đến số khóa duy nhất và tăng trưởng tương lai.
- **Dùng khóa composite nhưng chỉ lọc một phần:** một số engine yêu cầu equality trên toàn bộ khóa để khai thác hash index.
- **Không kiểm tra kiểu dữ liệu và collation:** phép băm và phép so sánh không tương thích có thể làm chỉ mục không được dùng đúng.
- **Cho rằng hash index hỗ trợ unique:** khả năng unique phụ thuộc hệ quản trị; PostgreSQL hash index không cung cấp unique constraint.
- **Nhầm Adaptive Hash Index của InnoDB với chỉ mục do người dùng tạo:** đây là cơ chế nội bộ của engine.
- **Chỉ đo truy vấn đọc:** bỏ qua chi phí ghi, bộ nhớ, contention và các truy vấn range liên quan.

## 14. Nguyên tắc cần ghi nhớ

- Hash index ánh xạ khóa sang bucket bằng hàm băm và chủ yếu phục vụ equality lookup.
- Va chạm hash là hiện tượng bình thường; hệ quản trị cần xác minh khóa thực tế để bảo đảm kết quả đúng.
- Hash index không duy trì thứ tự khóa, vì vậy không phù hợp trực tiếp với range scan, ORDER BY, MIN/MAX hoặc tìm tiền tố.
- B-tree hỗ trợ cả equality và range, đồng thời có thể cung cấp thứ tự; nó thường linh hoạt hơn cho workload hỗn hợp.
- Hash index nhiều cột, bucket count, unique và cách xử lý NULL phụ thuộc hệ quản trị và engine.
- Phải phân biệt hash index với hash join, hash aggregate và hash partitioning.
- Đánh giá phân bố khóa, số bucket, bộ nhớ, va chạm, hotspot và mức đồng thời.
- Luôn kiểm tra execution plan và đo latency, throughput, tài nguyên cùng chi phí ghi trước khi quyết định.

Hash index là công cụ chuyên biệt cho tra cứu bằng chính xác. Khi workload thực sự tập trung vào equality lookup và hệ quản trị hỗ trợ cấu trúc này phù hợp, nó có thể là một phương án đáng thử. Khi truy vấn cần tìm khoảng, sắp xếp hoặc phân trang theo khóa, cần chọn cấu trúc duy trì thứ tự như B-tree. Quyết định cuối cùng phải được chứng minh bằng execution plan và phép đo trên dữ liệu, tải và engine thực tế.
