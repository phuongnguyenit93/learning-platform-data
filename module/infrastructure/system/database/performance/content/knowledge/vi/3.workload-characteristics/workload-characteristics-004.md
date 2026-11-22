# Kích thước dữ liệu, tập dữ liệu hoạt động và tốc độ tăng trưởng

## Mục tiêu bài học

Khi đánh giá hiệu năng cơ sở dữ liệu, tổng dung lượng lưu trữ chỉ cho biết một phần của bức tranh. Một bảng có thể chứa hàng terabyte dữ liệu lịch sử nhưng các truy vấn hằng ngày chỉ đọc một phần nhỏ. Ngược lại, một tập dữ liệu hoạt động nhỏ hơn nhiều vẫn có thể gây áp lực lớn nếu nó liên tục được cập nhật, có nhiều chỉ mục hoặc không vừa với bộ nhớ đệm.

Sau bài học, bạn có thể:

- Phân biệt kích thước dữ liệu lưu trữ, số lượng bản ghi, kích thước chỉ mục và tập dữ liệu hoạt động (working set).
- Giải thích cách tính cục bộ truy cập, bộ nhớ đệm và phân bố dữ liệu ảnh hưởng đến hiệu năng.
- Đo mức tăng trưởng theo thời gian và xây dựng dự báo dung lượng có xét đến tải, lưu trữ phụ trợ và chính sách lưu giữ.
- Nhận diện tác động của dữ liệu tăng lên đối với I/O, bộ nhớ, chỉ mục, thống kê, sao lưu và phục hồi.
- Lập kế hoạch đo đạc và kiểm chứng khi dữ liệu thay đổi hoặc khi cần mở rộng hệ thống.

Nội dung thuộc chương **Khối lượng công việc** của module **DATABASE_PERFORMANCE**. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Vì vậy, kích thước và tăng trưởng cần được xem trong mối liên hệ với truy vấn thực tế, mức đồng thời và tài nguyên mà cơ sở dữ liệu sử dụng.

## 1. Ba khái niệm cần tách biệt

### 1.1. Kích thước dữ liệu

Kích thước dữ liệu mô tả lượng dữ liệu mà hệ thống đang quản lý hoặc chiếm dụng. Tùy câu hỏi, số đo có thể là:

- Số bản ghi hoặc số đối tượng.
- Dung lượng logic của dữ liệu nghiệp vụ.
- Dung lượng vật lý của bảng, chỉ mục và các cấu trúc phụ trợ trên đĩa.
- Dung lượng toàn cơ sở dữ liệu, bao gồm nhiều đối tượng và phần chi phí lưu trữ của hệ quản trị.
- Dung lượng log giao dịch, vùng tạm, bản sao, bản sao lưu và các bản xuất dữ liệu.

Các số đo này không đồng nghĩa. Hai bảng có cùng số dòng có thể có kích thước rất khác nhau do độ dài cột, kiểu dữ liệu, giá trị NULL, mức độ nén, định dạng lưu trữ và cấu trúc chỉ mục. Dung lượng tệp trên đĩa cũng có thể lớn hơn phần dữ liệu đang được sử dụng do trang trống, phân mảnh hoặc không gian chưa được thu hồi.

Khi nói một bảng có kích thước 100 GB, cần xác định rõ đó là kích thước phần dữ liệu, dữ liệu cộng với TOAST/LOB, dữ liệu cộng chỉ mục, hay toàn bộ dung lượng vật lý liên quan. Nếu không thống nhất phạm vi, việc so sánh theo ngày hoặc giữa các môi trường có thể dẫn đến kết luận sai.

### 1.2. Tập dữ liệu hoạt động (working set)

Working set là tập các trang dữ liệu và chỉ mục được một nhóm công việc truy cập thường xuyên trong một khoảng thời gian quan sát. Đây là phần dữ liệu có ảnh hưởng trực tiếp đến nhu cầu bộ nhớ đệm và I/O của tải đang chạy.

Ví dụ, một cửa hàng trực tuyến lưu lịch sử 5 năm với dung lượng 2 TB, nhưng trong giờ cao điểm phần lớn yêu cầu chỉ đọc sản phẩm đang bán, tồn kho hiện tại và đơn hàng trong vài tuần gần nhất. Tập dữ liệu hoạt động của luồng giao dịch có thể nhỏ hơn đáng kể tổng dữ liệu. Trong khi đó, truy vấn báo cáo cuối quý có thể truy cập một phạm vi lịch sử rộng hơn và tạo ra working set khác.

Working set không nhất thiết là một tập cố định. Nó thay đổi theo:

- Khung thời gian và chu kỳ nghiệp vụ, chẳng hạn giờ cao điểm, ngày chốt sổ hoặc mùa khuyến mại.
- Loại truy vấn, người dùng, tenant hoặc khu vực dữ liệu.
- Tần suất đọc và ghi, cũng như tính cục bộ theo thời gian và theo khóa.
- Kích thước bảng, chỉ mục, phân vùng và cách truy cập của kế hoạch thực thi.
- Chính sách cache, dung lượng RAM và hoạt động của các tiến trình khác.

Khi working set của tải quan trọng vượt quá khả năng lưu giữ hiệu quả trong bộ nhớ đệm, hệ thống có thể phải đọc trang từ thiết bị lưu trữ thường xuyên hơn. Tuy nhiên, không thể kết luận chỉ từ phép so sánh tổng kích thước bảng với RAM: cần xét phần dữ liệu thực sự được truy cập, kích thước các trang cần thiết, cache của hệ quản trị và hệ điều hành, mức đồng thời, tốc độ I/O cùng các tải cạnh tranh.

### 1.3. Tốc độ tăng trưởng

Tốc độ tăng trưởng mô tả dung lượng hoặc số bản ghi thay đổi theo thời gian. Có thể đo theo:

- Mức tăng tuyệt đối, ví dụ GB mỗi ngày hoặc số dòng mỗi giờ.
- Tỷ lệ tăng tương đối, ví dụ phần trăm mỗi tháng.
- Mức tăng ròng sau khi tính dữ liệu bị xóa, hết hạn hoặc nén.
- Mức tăng gộp của các thành phần riêng như bảng, chỉ mục, log, bản sao và bản sao lưu.

Tốc độ tăng không phải lúc nào cũng đều. Nạp dữ liệu theo lô, sự kiện kinh doanh, chiến dịch bán hàng hoặc thời gian lưu giữ có thể tạo ra các đợt tăng đột biến. Một dự báo hữu ích phải dựa trên chuỗi đo đủ dài để nhận ra chu kỳ và ngoại lệ.

## 2. Những thành phần tạo nên dung lượng cơ sở dữ liệu

Dung lượng cần được phân tích theo thành phần vì mỗi thành phần có đặc điểm truy cập và chi phí khác nhau.

| Thành phần | Nội dung | Tác động hiệu năng cần quan sát |
|---|---|---|
| Dữ liệu bảng | Các hàng và cột nghiệp vụ | Số trang cần đọc, kích thước quét, chi phí ghi và cập nhật |
| Chỉ mục | Cấu trúc hỗ trợ tìm kiếm, nối và sắp xếp | Tăng tốc một số truy vấn nhưng chiếm dung lượng và tăng chi phí ghi, bảo trì |
| Dữ liệu ngoài hàng | Giá trị lớn như văn bản dài, JSON hoặc đối tượng LOB/TOAST tùy hệ quản trị | Có thể làm tăng I/O khi truy vấn lấy nội dung lớn; cách lưu phụ thuộc hệ quản trị |
| Không gian trống và phân mảnh | Trang chưa dùng hết, phiên bản hàng cũ hoặc vùng chưa được thu hồi | Làm tăng dung lượng vật lý và số trang cần quản lý hoặc quét |
| Log giao dịch | Nhật ký phục vụ phục hồi và sao chép | Tăng I/O ghi, dung lượng đĩa và lưu lượng truyền log |
| Dữ liệu tạm | Kết quả trung gian của sắp xếp, hash, join hoặc truy vấn | Có thể gây I/O lớn khi vượt bộ nhớ cho phép |
| Bản sao và bản sao lưu | Dữ liệu nhân bản để phục hồi, dự phòng hoặc phân tích | Tăng nhu cầu lưu trữ, mạng, thời gian sao lưu và phục hồi |

Không nên cộng các thành phần từ những nguồn đo khác phạm vi. Ví dụ, kích thước một database có thể không bao gồm bản sao lưu ở kho ngoài; kích thước bảng có thể chưa bao gồm chỉ mục; dung lượng volume có thể bao gồm log và tệp tạm của nhiều database.

## 3. Đo kích thước và tốc độ tăng trưởng

### 3.1. Xác định phạm vi và đơn vị đo

Trước khi thu thập số liệu, cần ghi rõ:

1. Đo ở cấp database, schema, bảng, phân vùng, chỉ mục hay toàn bộ máy chủ?
2. Số liệu là dung lượng logic, dung lượng vật lý đã cấp phát hay dung lượng thực tế đang dùng?
3. Có tính dữ liệu ngoài hàng, chỉ mục, log, vùng tạm và bản sao không?
4. Số đo được lấy tại thời điểm nào, theo múi giờ nào và sau sự kiện bảo trì nào?
5. Các số liệu có cùng đơn vị hay không (byte, KiB, MiB, GiB, TiB)?

Giữ nguyên số byte khi lưu số đo gốc sẽ giúp chuyển đổi đơn vị nhất quán và tránh sai số do làm tròn. Khi báo cáo, cần nêu rõ dùng đơn vị thập phân (1 GB = 1.000.000.000 byte) hay nhị phân (1 GiB = 1.073.741.824 byte).

### 3.2. Ví dụ đo dung lượng trong PostgreSQL

Các truy vấn sau minh họa cách quan sát trong PostgreSQL. Quyền xem số liệu và mức chi tiết có thể phụ thuộc phiên bản, quyền truy cập và cấu hình hệ thống.

Dung lượng toàn database hiện tại:

```sql
SELECT
    current_database() AS database_name,
    pg_database_size(current_database()) AS size_bytes,
    pg_size_pretty(pg_database_size(current_database())) AS size_pretty;
```

Xếp hạng các bảng theo tổng dung lượng liên quan:

```sql
SELECT
    schemaname,
    relname,
    pg_table_size(relid) AS table_bytes,
    pg_indexes_size(relid) AS index_bytes,
    pg_total_relation_size(relid) AS total_bytes,
    pg_size_pretty(pg_table_size(relid)) AS table_size,
    pg_size_pretty(pg_indexes_size(relid)) AS index_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
    n_live_tup,
    n_dead_tup
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 20;
```

`pg_table_size` phản ánh dung lượng của bảng và các thành phần liên quan như TOAST, nhưng không gồm chỉ mục. `pg_indexes_size` đo phần chỉ mục. `pg_total_relation_size` cộng hai phần này. Các cột `n_live_tup` và `n_dead_tup` trong view thống kê là ước lượng, không phải phép đếm chính xác tại thời điểm truy vấn. Số liệu thống kê có thể thay đổi sau `ANALYZE`, `VACUUM` hoặc theo hoạt động của hệ thống.

Để xem dung lượng từng chỉ mục của một bảng cụ thể, có thể dùng:

```sql
SELECT
    indexrelid::regclass AS index_name,
    pg_relation_size(indexrelid) AS size_bytes,
    pg_size_pretty(pg_relation_size(indexrelid)) AS size_pretty
FROM pg_index
WHERE indrelid = 'public.orders'::regclass
ORDER BY pg_relation_size(indexrelid) DESC;
```

Những truy vấn này là ví dụ dành riêng cho PostgreSQL, không thể dùng nguyên trạng trên MySQL, SQL Server, Oracle hay các hệ quản trị khác. Trong môi trường thực tế, nên lưu snapshot định kỳ vào hệ thống giám sát để quan sát xu hướng; một lần truy vấn chỉ cho biết trạng thái tại thời điểm đó.

### 3.3. Tính mức tăng tuyệt đối và tỷ lệ tăng

Giả sử dung lượng một nhóm bảng là \(S_1\) tại thời điểm \(t_1\) và \(S_2\) tại thời điểm \(t_2\). Nếu khoảng cách thời gian là \(d\) ngày, mức tăng ròng trung bình mỗi ngày là:

\[
g_{day} = \frac{S_2 - S_1}{d}
\]

Nếu \(S_1 > 0\), tỷ lệ tăng kép bình quân mỗi ngày có thể ước tính bằng:

\[
r_{day} = \left(\frac{S_2}{S_1}\right)^{1/d} - 1
\]

Ví dụ, một database tăng từ 400 GiB lên 460 GiB trong 30 ngày:

- Mức tăng ròng trung bình: \(60 / 30 = 2\) GiB/ngày.
- Tỷ lệ tăng kép bình quân: \((460/400)^{1/30}-1\), xấp xỉ 0,47% mỗi ngày.

Hai con số trả lời hai câu hỏi khác nhau. Mức tăng tuyệt đối hữu ích khi lập kế hoạch dung lượng trong ngắn hạn. Tỷ lệ tăng tương đối hữu ích khi quy mô có xu hướng tăng theo phần trăm. Nếu dữ liệu có tính mùa vụ, nạp theo lô hoặc có chính sách xóa dữ liệu, không nên ngoại suy một mức trung bình ngắn hạn cho cả năm mà không kiểm tra chuỗi lịch sử.

### 3.4. Phân biệt tăng trưởng gộp và tăng trưởng ròng

Tăng trưởng ròng là chênh lệch dung lượng giữa hai lần đo. Tăng trưởng gộp là tổng lượng dữ liệu mới được thêm vào trước khi trừ phần bị xóa, hết hạn hoặc thu hồi. Ví dụ, mỗi ngày hệ thống ghi thêm 20 GiB và xóa 15 GiB dữ liệu hết hạn thì tăng trưởng ròng có thể chỉ khoảng 5 GiB/ngày, nhưng hệ thống vẫn phải xử lý lượng ghi, log, chỉ mục và công việc dọn dẹp tương ứng với hoạt động lớn hơn.

Điều này quan trọng khi đánh giá hiệu năng. Hai hệ thống có cùng mức tăng ròng có thể có tải ghi, sinh log, vacuum/cleanup và chi phí bảo trì rất khác nhau.

## 4. Hiểu và ước lượng working set

### 4.1. Working set không chỉ là các bảng lớn nhất

Một bảng lớn chưa chắc là phần dữ liệu được truy cập thường xuyên nhất. Bảng nhật ký hàng tỷ dòng có thể chỉ được truy vấn theo một khoảng ngày nhỏ. Một bảng trạng thái vài GB có thể được đọc và cập nhật liên tục trong mọi yêu cầu nghiệp vụ.

Để ước lượng working set, cần quan sát cả đối tượng và kiểu truy cập:

- Bảng, phân vùng và chỉ mục nào xuất hiện trong các truy vấn quan trọng?
- Truy vấn truy cập theo khóa, theo dải thời gian, quét tuần tự hay nối nhiều bảng?
- Bao nhiêu trang được đọc từ cache và bao nhiêu trang phải đọc từ lưu trữ?
- Dữ liệu nóng có tập trung ở một số khóa, tenant hoặc phân vùng không?
- Working set thay đổi thế nào giữa giờ cao điểm, cuối ngày và kỳ báo cáo?

Một truy vấn có thể chỉ trả về 20 dòng nhưng vẫn đọc nhiều trang nếu điều kiện lọc thiếu chọn lọc hoặc kế hoạch thực thi không phù hợp. Ngược lại, truy vấn trả về hàng nghìn dòng có thể hiệu quả nếu dữ liệu liên quan được lưu liên tục và đọc theo phạm vi hợp lý.

### 4.2. Đo theo truy vấn và theo đối tượng

Nên kết hợp nhiều nguồn quan sát:

1. **Thống kê truy vấn:** xác định truy vấn thường chạy, tổng thời gian, thời gian trung bình, số lần gọi và lượng block đọc/được phục vụ từ cache nếu hệ quản trị cung cấp.
2. **Kế hoạch thực thi:** dùng `EXPLAIN` hoặc công cụ tương đương để xem loại scan, chỉ mục được dùng, số dòng ước lượng/thực tế và lượng buffer truy cập.
3. **Thống kê đối tượng:** xem số lần truy cập, số dòng đọc/thay đổi, mức tăng dung lượng và tình trạng phân vùng hoặc chỉ mục.
4. **Quan sát tài nguyên:** đối chiếu cache hit, IOPS, độ trễ đọc, thông lượng, bộ nhớ và tải đồng thời.
5. **Đo theo thời gian:** lặp lại ở nhiều khung giờ và nhiều chu kỳ nghiệp vụ để không nhầm một snapshot với hành vi dài hạn.

Trong PostgreSQL, `EXPLAIN (ANALYZE, BUFFERS)` có thể giúp kiểm tra một truy vấn đại diện:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 50;
```

`ANALYZE` thực thi câu truy vấn, vì vậy chỉ dùng với truy vấn và môi trường phù hợp; cần cân nhắc tác động nếu truy vấn có ghi dữ liệu hoặc tải lớn. Phần `BUFFERS` cung cấp thông tin về block được truy cập theo các nhóm buffer mà PostgreSQL báo cáo. Nó giúp hiểu đường truy cập của một lần chạy, nhưng không tự mô tả toàn bộ working set của ứng dụng.

Nếu có công cụ thống kê truy vấn như `pg_stat_statements`, có thể dùng nó để tìm nhóm truy vấn tiêu thụ nhiều thời gian hoặc block. Số liệu thường được tích lũy từ lần reset gần nhất, có thể tổng hợp nhiều lần chạy và nhiều đối tượng. Vì vậy, cần kết hợp kế hoạch truy vấn, thống kê đối tượng và dữ liệu giám sát để xác định working set; không suy ra chính xác working set chỉ từ một bộ đếm tổng hợp.

### 4.3. Cache hit không phải mục tiêu duy nhất

Tỷ lệ cache hit cao thường là tín hiệu tích cực, nhưng không đủ để khẳng định hiệu năng tốt. Một hệ thống có thể có tỷ lệ hit cao vì đọc lặp lại một tập trang nhỏ, trong khi một truy vấn báo cáo hiếm gặp vẫn phải quét lượng dữ liệu lớn từ đĩa. Một tỷ lệ hit thấp cũng có thể chấp nhận được với workload quét tuần tự lớn nếu thiết bị lưu trữ đáp ứng đủ thông lượng và độ trễ.

Khi đánh giá cache, hãy xem đồng thời:

- Độ trễ thực tế của truy vấn và phân vị p95/p99.
- Số block đọc từ lưu trữ, số block cache hit và kích thước dữ liệu được quét.
- Mức độ đồng thời và sự cạnh tranh với các tiến trình khác.
- Loại truy vấn và kỳ vọng của SLA.

Không nên tăng RAM, thay đổi cache hay tạo chỉ mục chỉ dựa trên một tỷ lệ hit đơn lẻ. Trước tiên hãy xác định truy vấn nào bị chậm, truy cập những trang nào và nguyên nhân chính là thiếu cache, đọc dữ liệu không chọn lọc hay một nút thắt khác.

## 5. Tốc độ tăng trưởng ảnh hưởng đến hiệu năng như thế nào?

### 5.1. Tăng kích thước có thể làm thay đổi đường truy cập

Khi bảng và chỉ mục lớn dần:

- Số trang cần quét tăng nếu truy vấn vẫn đọc cùng một tỷ lệ dữ liệu.
- Chỉ mục có thể chiếm nhiều cache hơn; các trang nóng có thể bị đẩy ra khỏi bộ nhớ.
- Một truy vấn trước đây phù hợp với index scan có thể có chi phí khác khi độ chọn lọc hoặc phân bố dữ liệu thay đổi.
- Thống kê cũ có thể khiến bộ tối ưu ước lượng sai số dòng và chọn kế hoạch kém.
- Phép nối, sắp xếp và tổng hợp có thể tiêu thụ thêm CPU, bộ nhớ hoặc vùng lưu trữ tạm.
- Công việc bảo trì như vacuum, analyze, rebuild index, backup và restore có thể kéo dài.

Không phải mọi bảng lớn đều chậm. Nếu truy vấn giới hạn đúng phạm vi, chỉ mục hoặc phân vùng phù hợp và thiết bị lưu trữ đáp ứng tải, hệ thống vẫn có thể phục vụ dữ liệu lớn hiệu quả. Vấn đề nằm ở quan hệ giữa kích thước, cách truy cập và tài nguyên.

### 5.2. Tăng dữ liệu ghi và tranh chấp

Tăng trưởng cũng có thể phản ánh lượng ghi lớn hơn. Khi nhiều phiên cùng ghi vào một số khóa hoặc vùng dữ liệu, hệ thống có thể gặp tranh chấp khóa, latch, trang hoặc log. Các chỉ mục bổ sung làm tăng công việc cập nhật trên mỗi lần ghi. Nếu có phân vùng, cách chọn khóa phân vùng có thể phân tán tải tốt hoặc tạo ra một điểm nóng tùy thiết kế.

Vì vậy, cần phân biệt hai tình huống:

- **Dữ liệu tăng nhưng tải truy cập không đổi:** cần kiểm tra kích thước working set, hiệu quả chỉ mục, phạm vi quét và tác động tới bảo trì.
- **Dữ liệu và tốc độ ghi cùng tăng:** cần kiểm tra throughput ghi, log, checkpoint hoặc cơ chế tương ứng, chờ khóa, phân bố ghi và thời gian xử lý nền.

### 5.3. Tăng dung lượng kéo theo yêu cầu vận hành

Database lớn hơn thường cần nhiều thời gian và tài nguyên hơn cho sao lưu, truyền bản sao, kiểm tra tính toàn vẹn và phục hồi. Nếu mục tiêu RTO/RPO không đổi, thời gian backup/restore và khả năng truyền dữ liệu có thể trở thành giới hạn kiến trúc. Cần đo thời gian thực tế và thử phục hồi định kỳ, thay vì chỉ dựa trên dung lượng tệp sao lưu.

Ngoài ra, cần dự trù dung lượng cho log, dữ liệu tạm, bản sao, bản sao lưu, thao tác bảo trì và các đợt nạp dữ liệu lớn. Một volume vừa đủ cho dữ liệu hiện tại có thể hết chỗ khi hệ thống cần tạo tệp tạm hoặc giữ log trong thời gian dài.

## 6. Dự báo tăng trưởng và lập kế hoạch dung lượng

### 6.1. Thu thập chuỗi số liệu có thể so sánh

Đặt lịch ghi nhận dung lượng theo cùng phạm vi và cùng phương pháp. Tần suất phụ thuộc tốc độ tăng và yêu cầu vận hành: hệ thống tăng nhanh có thể cần đo hằng ngày hoặc thường xuyên hơn; hệ thống ổn định có thể đo theo tuần. Ngoài snapshot định kỳ, hãy ghi nhận các sự kiện như nạp dữ liệu lớn, thay đổi retention, tạo chỉ mục, tái cấu trúc bảng và nâng cấp hệ quản trị.

Mỗi mẫu nên có thời điểm, đối tượng, kích thước byte, số dòng ước lượng hoặc thực tế nếu có, dung lượng bảng, chỉ mục, log và ghi chú về thay đổi vận hành. Không trộn số liệu trước và sau một lần thay đổi phương pháp đo nếu chưa điều chỉnh phạm vi.

### 6.2. Dự báo tuyến tính

Nếu mức tăng tuyệt đối tương đối ổn định, có thể ước lượng dung lượng sau \(T\) ngày:

\[
S_{future} = S_{current} + g_{day} \times T
\]

Ví dụ, hiện có 600 GiB dữ liệu và mức tăng ròng quan sát được là 8 GiB/ngày. Dự báo tuyến tính sau 90 ngày:

\[
600 + 8 \times 90 = 1320\;GiB
\]

Đây là ước lượng cho thành phần đã đo, theo giả định tốc độ tăng giữ nguyên. Nó chưa tự động bao gồm log, bản sao lưu, vùng tạm, dung lượng trống cần cho bảo trì hoặc phần tăng do tạo thêm chỉ mục.

### 6.3. Dự báo theo tỷ lệ tăng

Nếu dữ liệu tăng gần theo tỷ lệ phần trăm, có thể dùng mô hình kép:

\[
S_{future} = S_{current} \times (1+r)^T
\]

Trong đó \(r\) là tỷ lệ tăng mỗi đơn vị thời gian và \(T\) là số đơn vị thời gian tương ứng. Mô hình này nhạy với sai số của tỷ lệ tăng khi kéo dài thời gian dự báo. Chỉ sử dụng khi dữ liệu lịch sử cho thấy xu hướng phù hợp; cần so sánh dự báo với số đo mới và cập nhật giả định.

### 6.4. Lập kịch bản thay vì chỉ dùng một con số

Một kế hoạch dung lượng nên có ít nhất các kịch bản:

| Kịch bản | Giả định | Cách sử dụng |
|---|---|---|
| Cơ sở | Tốc độ tăng gần với mức lịch sử đại diện | Kế hoạch vận hành thông thường |
| Cao | Có thêm người dùng, giao dịch, dữ liệu hoặc đợt nạp lớn | Kiểm tra headroom và thời điểm mở rộng |
| Thấp | Tăng trưởng giảm hoặc retention loại bỏ dữ liệu nhanh hơn | Đánh giá khả năng trì hoãn mở rộng |

Headroom là phần dung lượng dự phòng cần thiết cho biến động, tăng trưởng và hoạt động vận hành. Không có một tỷ lệ dự phòng phù hợp cho mọi hệ thống. Mức cần thiết phụ thuộc tốc độ tăng, thời gian mua/cấp phát tài nguyên, giới hạn volume, thời gian bảo trì, quy trình phục hồi và mức rủi ro có thể chấp nhận.

Khi tính nhu cầu lưu trữ, cần tách các khoản:

- Dữ liệu bảng và dữ liệu ngoài hàng.
- Chỉ mục hiện có và chỉ mục dự kiến bổ sung.
- Log giao dịch và vùng tạm ở mức tải cao điểm.
- Bản sao đọc, bản sao dự phòng và bản sao lưu theo chính sách lưu giữ.
- Dung lượng trống cho bảo trì, tái cấu trúc và thao tác phục hồi.

Không nên lấy tổng dung lượng hiện tại nhân một hệ số duy nhất nếu các thành phần tăng theo quy luật khác nhau. Ví dụ, retention có thể làm dữ liệu bảng ổn định sau một thời gian, trong khi log hoặc bản sao lưu vẫn phụ thuộc vào lưu lượng ghi hằng ngày.

## 7. Biện pháp quản lý dữ liệu tăng trưởng

### 7.1. Chính sách lưu giữ và lưu trữ dữ liệu cũ

Xác định thời gian dữ liệu cần có trong hệ thống giao dịch để phục vụ nghiệp vụ và truy vấn thường xuyên. Dữ liệu quá hạn có thể được xóa, lưu trữ ở tầng rẻ hơn hoặc chuyển sang kho phân tích nếu yêu cầu pháp lý và nghiệp vụ cho phép.

Trước khi xóa hoặc lưu trữ, cần xác nhận:

- Dữ liệu có còn được tham chiếu bởi khóa ngoại, báo cáo, đối soát hoặc quy trình nghiệp vụ không?
- Thời hạn lưu giữ và yêu cầu kiểm toán là bao lâu?
- Có cần giữ khả năng truy vấn lịch sử với độ trễ khác không?
- Việc xóa theo lô có gây khóa kéo dài, tăng log hoặc ảnh hưởng bản sao không?
- Có thể xử lý theo lô nhỏ, theo thời gian hoặc theo phân vùng để giảm tác động không?

Chính sách retention phải được thống nhất với chủ sở hữu dữ liệu và yêu cầu nghiệp vụ. Không tự xóa dữ liệu chỉ vì muốn giảm dung lượng.

### 7.2. Phân vùng dữ liệu

Partitioning chia một bảng logic thành các phần vật lý theo một khóa hoặc quy tắc. Với dữ liệu lịch sử tăng theo thời gian, phân vùng theo ngày, tháng hoặc quý có thể giúp truy vấn loại bỏ các phân vùng không liên quan (partition pruning), quản lý retention và bảo trì từng phần.

Phân vùng chỉ có lợi khi điều kiện truy vấn phù hợp với khóa phân vùng và hệ quản trị có thể loại bỏ phần không cần đọc. Quá nhiều phân vùng, kích thước phân vùng không hợp lý hoặc truy vấn không lọc theo khóa phân vùng có thể làm tăng chi phí lập kế hoạch và vận hành. Cần kiểm tra kế hoạch thực thi để xác nhận partition pruning thực sự xảy ra.

### 7.3. Chỉ mục và thống kê

Khi dữ liệu lớn lên, chỉ mục có thể giúp tránh quét nhiều trang nhưng bản thân chỉ mục cũng tăng kích thước và chi phí cập nhật. Chỉ tạo hoặc thay đổi chỉ mục sau khi xác định truy vấn quan trọng, xem kế hoạch, đánh giá độ chọn lọc và đo cả tác động đọc lẫn ghi.

Thống kê cần phản ánh phân bố dữ liệu hiện tại. Sau khi nạp lượng dữ liệu lớn hoặc thay đổi mạnh phân bố giá trị, cần xem xét cập nhật thống kê theo cơ chế của hệ quản trị. Nếu bộ tối ưu ước lượng sai số dòng, kế hoạch nối hoặc đường truy cập có thể kém hiệu quả dù chỉ mục đã tồn tại.

### 7.4. Nén và tầng lưu trữ

Nén có thể giảm dung lượng và lượng dữ liệu phải đọc từ lưu trữ, nhưng thường tiêu thụ CPU để nén/giải nén và có thể ảnh hưởng khả năng cập nhật. Tầng lưu trữ lạnh hoặc kho dữ liệu phù hợp với dữ liệu ít truy cập, nhưng cần cân nhắc độ trễ truy xuất, chi phí chuyển dữ liệu và yêu cầu phục hồi.

Đánh giá nén hoặc chuyển tầng bằng workload đại diện. So sánh dung lượng tiết kiệm, CPU, I/O, độ trễ truy vấn, tốc độ nạp và chi phí vận hành trước khi áp dụng rộng rãi.

## 8. Quy trình đánh giá khi dữ liệu tăng

Khi hệ thống bắt đầu chậm hơn trong khi dung lượng tăng, có thể thực hiện theo trình tự sau:

**Bước 1 — Xác nhận xu hướng.** So sánh snapshot theo cùng phạm vi, xác định bảng, chỉ mục hoặc thành phần nào tăng nhanh. Kiểm tra sự kiện nạp dữ liệu, thay đổi retention và bảo trì gần thời điểm đó.

**Bước 2 — Xác định luồng tải bị ảnh hưởng.** Thu thập truy vấn chậm, p50/p95/p99, thông lượng, timeout, mức đồng thời và thời điểm phát sinh. Xác định sự cố xảy ra với OLTP, OLAP hay cả hai.

**Bước 3 — Ước lượng working set.** Xem truy vấn thường chạy, phạm vi dữ liệu được truy cập, chỉ mục và phân vùng liên quan, lượng buffer đọc từ cache và lượng I/O thực tế.

**Bước 4 — Kiểm tra kế hoạch và thống kê.** So sánh số dòng ước lượng với thực tế, loại scan, phép nối, sắp xếp và dữ liệu tạm. Kiểm tra thống kê có phù hợp với phân bố dữ liệu hiện tại không.

**Bước 5 — Xác định nút thắt.** Đối chiếu CPU, RAM, cache, IOPS, thông lượng và độ trễ I/O, chờ khóa, log, vùng tạm và hoạt động bảo trì. Không mặc định dung lượng tăng là nguyên nhân trực tiếp của độ trễ.

**Bước 6 — Chọn thay đổi có giả thuyết rõ.** Ví dụ giới hạn phạm vi truy vấn, thêm hoặc điều chỉnh chỉ mục, cập nhật thống kê, phân vùng, thay đổi retention, chuyển báo cáo sang hệ thống phân tích hoặc mở rộng tài nguyên.

**Bước 7 — Đo lại.** Dùng cùng dữ liệu đại diện, cùng truy vấn và mức đồng thời tương đương. So sánh p95/p99, thông lượng, I/O, CPU, bộ nhớ, dung lượng, chi phí ghi và ảnh hưởng lên các workload khác.

## 9. Ví dụ thực tế: đơn hàng tăng theo thời gian

Một ứng dụng thương mại điện tử lưu bảng `orders` và `order_items`. Dung lượng `orders` tăng đều do mỗi giao dịch tạo đơn mới. Ban đầu, trang quản trị lấy 50 đơn gần nhất phản hồi nhanh. Sau một năm, truy vấn bắt đầu chậm hơn.

Không nên kết luận ngay rằng cần tăng RAM hoặc xóa dữ liệu cũ. Hãy kiểm tra:

1. Truy vấn có lọc theo `customer_id` hoặc `created_at` không?
2. Chỉ mục hiện tại có phù hợp với điều kiện lọc và thứ tự sắp xếp không?
3. Số dòng thực tế được đọc có tăng lên đáng kể không?
4. Working set của bảng và chỉ mục có thay đổi so với bộ nhớ đệm không?
5. Có báo cáo lịch sử quét cùng bảng trong giờ cao điểm không?
6. Thống kê có phản ánh phân bố giá trị hiện tại không?

Nếu truy vấn thường lấy các đơn mới nhất của một khách hàng, có thể thử nghiệm chỉ mục ghép phù hợp với đường truy cập, chẳng hạn `(customer_id, created_at DESC)` trên PostgreSQL. Đây chỉ là giả thuyết cần kiểm chứng: cần xem `EXPLAIN (ANALYZE, BUFFERS)`, kiểm tra thứ tự sắp xếp và đo chi phí ghi tăng thêm khi tạo chỉ mục.

Nếu báo cáo lịch sử là nguyên nhân gây quét lớn, có thể xem xét phân vùng theo thời gian hoặc chuyển báo cáo sang bản sao/kho phân tích. Quyết định phụ thuộc khả năng lọc theo khóa phân vùng, độ mới dữ liệu và mức độ tách biệt tài nguyên. Sau thay đổi, cần kiểm tra cả thời gian trang quản trị lẫn p95/p99 của giao dịch tạo đơn.

## 10. Những sai lầm thường gặp

- **Dùng số dòng làm đại diện duy nhất cho dung lượng.** Độ dài hàng, kiểu dữ liệu, chỉ mục và dữ liệu ngoài hàng có thể làm dung lượng khác nhau đáng kể.
- **Đồng nhất tổng kích thước với working set.** Một phần dữ liệu nhỏ có thể được truy cập liên tục, trong khi phần lớn dữ liệu lịch sử gần như không được đọc.
- **Cho rằng cache hit cao luôn có nghĩa là tốt.** Cần đánh giá độ trễ truy vấn, I/O thực tế, loại workload và phân vị phản hồi.
- **Dự báo bằng một snapshot.** Tăng trưởng có thể theo mùa, theo lô hoặc thay đổi khi chính sách retention được áp dụng.
- **Chỉ nhìn tăng trưởng ròng.** Dữ liệu ghi mới và xóa cũ có thể tạo tải ghi, log và dọn dẹp lớn dù dung lượng gần như không đổi.
- **Chờ volume gần đầy mới lập kế hoạch.** Cần tính thời gian cấp phát, headroom, log, vùng tạm, backup và yêu cầu phục hồi.
- **Thêm chỉ mục để xử lý mọi vấn đề do dữ liệu lớn.** Chỉ mục có chi phí lưu trữ và ghi; cần xác định đúng truy vấn và đo trước/sau.
- **Phân vùng nhưng không kiểm tra pruning.** Có phân vùng không đồng nghĩa truy vấn sẽ tự động đọc ít dữ liệu hơn.

## 11. Checklist khảo sát kích thước và tăng trưởng

- [ ] Đã xác định rõ phạm vi và đơn vị của từng số đo dung lượng.
- [ ] Đã tách dung lượng bảng, chỉ mục, log, dữ liệu tạm, bản sao và bản sao lưu.
- [ ] Đã thu thập snapshot định kỳ theo cùng một phương pháp.
- [ ] Đã tính cả tăng trưởng tuyệt đối, tỷ lệ tăng và các đợt tăng đột biến.
- [ ] Đã phân biệt tăng trưởng gộp với tăng trưởng ròng.
- [ ] Đã xác định truy vấn và đối tượng tạo nên working set của workload quan trọng.
- [ ] Đã đối chiếu cache, I/O, kế hoạch thực thi và mức đồng thời.
- [ ] Đã lập kịch bản dung lượng và xác định headroom phù hợp với thời gian mở rộng.
- [ ] Đã đánh giá retention, phân vùng, chỉ mục và tầng lưu trữ bằng workload đại diện.
- [ ] Đã kiểm tra ảnh hưởng của thay đổi tới hiệu năng, backup, restore và các workload khác.

## Kết luận

Kích thước dữ liệu cho biết quy mô lưu trữ, working set cho biết phần dữ liệu và chỉ mục được workload truy cập thường xuyên, còn tốc độ tăng trưởng cho biết nhu cầu tài nguyên sẽ thay đổi ra sao theo thời gian. Ba khái niệm có liên quan nhưng không thể thay thế cho nhau.

Trong tối ưu hiệu năng cơ sở dữ liệu, cần đo từng thành phần, quan sát truy vấn và kế hoạch thực thi, đối chiếu cache với I/O, rồi dự báo dung lượng theo xu hướng có thể kiểm chứng. Khi dữ liệu tăng, lựa chọn như chỉ mục, phân vùng, retention, nén hoặc mở rộng tài nguyên phải dựa trên nút thắt đã đo và được xác nhận bằng cùng workload trước và sau điều chỉnh.
