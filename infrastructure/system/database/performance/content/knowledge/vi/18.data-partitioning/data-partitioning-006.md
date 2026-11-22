# Lựa chọn khóa phân vùng và xử lý phân bố dữ liệu lệch

## Vì sao khóa phân vùng quyết định hiệu năng?

Phân vùng dữ liệu (partitioning) chia một bảng hoặc tập dữ liệu lớn thành các phần nhỏ hơn theo một quy tắc. Ứng dụng vẫn có thể truy vấn bảng logic như một đối tượng thống nhất, trong khi hệ quản trị chỉ cần truy cập những phân vùng liên quan nếu điều kiện truy vấn cho phép loại bỏ phần không cần thiết. Phân vùng cũng hỗ trợ quản lý vòng đời dữ liệu, bảo trì và một số chiến lược song song hóa.

Hiệu quả của thiết kế phụ thuộc nhiều vào khóa phân vùng (partition key). Khóa này quyết định hàng được đặt vào phân vùng nào, truy vấn có thể loại bỏ được bao nhiêu phân vùng, dữ liệu và tải ghi có cân bằng hay không, cũng như việc bảo trì hoặc xóa dữ liệu cũ có thuận tiện không.

Một khóa phân vùng tốt cần cân bằng nhiều mục tiêu:

- Truy vấn thường xuyên có thể lọc theo khóa để thực hiện partition pruning.
- Dữ liệu được phân bố đủ đều theo số hàng, dung lượng và tải truy cập.
- Một vài giá trị phổ biến không dồn toàn bộ công việc vào một phân vùng nóng.
- Số lượng phân vùng không quá lớn đến mức gây overhead lập kế hoạch, metadata và vận hành.
- Khóa ổn định, có ý nghĩa trong vòng đời dữ liệu và phù hợp với ràng buộc toàn vẹn.
- Các thao tác ghi, cập nhật, join và bảo trì có thể thực hiện với chi phí chấp nhận được.

Không có một khóa phân vùng tối ưu cho mọi workload. Khóa phù hợp với truy vấn theo thời gian có thể tạo điểm nóng ghi ở phân vùng hiện tại. Khóa hash có thể phân bố đều nhưng không giúp loại bỏ phân vùng theo khoảng thời gian. Khóa tenant có thể hỗ trợ cô lập dữ liệu nhưng một tenant rất lớn có thể tạo lệch tải nghiêm trọng.

Trong phạm vi DATABASE_PERFORMANCE, việc lựa chọn khóa phân vùng phải dựa trên đo đạc tải, thống kê, kế hoạch thực thi và cơ chế truy cập dữ liệu. Bài học này hướng dẫn cách đánh giá khóa ứng viên, đo skew, nhận diện hot partition, chọn range/hash/list hoặc phân vùng nhiều cấp, rồi kiểm chứng hiệu quả và chi phí sau thay đổi.

## Phân biệt phân vùng, phân mảnh và sharding

Các hệ quản trị dùng thuật ngữ và cách triển khai khác nhau, nhưng có thể phân biệt ở mức khái niệm:

- **Partitioning:** chia một bảng hoặc tập dữ liệu thành các phân vùng theo quy tắc, thường được quản lý trong cùng một hệ quản trị hoặc cụm.
- **Sharding:** phân phối dữ liệu qua nhiều node hoặc shard độc lập; ứng dụng hoặc lớp điều phối có thể phải định tuyến truy vấn đến shard.
- **Sharding key:** khóa quyết định dữ liệu thuộc shard nào; các vấn đề phân bố đều, hot key và khả năng định tuyến tương tự nhưng có thêm chi phí mạng và vận hành phân tán.
- **Subpartitioning:** chia tiếp một phân vùng thành các phần nhỏ hơn theo một quy tắc khác nếu hệ quản trị hỗ trợ.

Phân vùng trong một máy chủ không tự động tăng tổng năng lực CPU, RAM hoặc I/O của máy đó. Nó có thể giảm lượng dữ liệu cần quét, giúp quản lý dữ liệu và tăng khả năng xử lý song song, nhưng mọi phân vùng vẫn có thể cạnh tranh cùng tài nguyên vật lý. Nếu nút thắt là giới hạn của một node, cần đánh giá kiến trúc mở rộng phù hợp thay vì kỳ vọng partitioning tự giải quyết.

## Khóa phân vùng và mẫu truy cập

### Bắt đầu từ workload thực tế

Trước khi chọn khóa, hãy thu thập các truy vấn và thao tác chính:

- Các truy vấn lọc theo tenant, khách hàng, vùng, ngày hoặc trạng thái.
- Các truy vấn đọc theo khoảng thời gian và truy vấn lấy dữ liệu mới nhất.
- Các phép join thường xuyên và cột dùng làm khóa liên kết.
- Tần suất INSERT, UPDATE, DELETE và thời điểm dữ liệu được ghi.
- Các tác vụ retention, archive, backup, restore và bảo trì.
- Kích thước dữ liệu, tốc độ tăng trưởng và thời gian lưu giữ.
- Phân bố số hàng và dung lượng theo từng giá trị ứng viên.
- Phân bố QPS/TPS, CPU, I/O và độ trễ theo khóa hoặc phân vùng.

Không chọn partition key chỉ vì một cột có nhiều giá trị khác nhau. Cardinality cao không đảm bảo phân bố đều. Một khóa có hàng triệu giá trị nhưng phần lớn hàng tập trung vào một vài giá trị vẫn tạo skew. Ngược lại, khóa có ít giá trị có thể phân bố rất đều nhưng tạo quá ít phân vùng để tận dụng song song hoặc quản lý vòng đời.

### Những tiêu chí đánh giá khóa ứng viên

| Tiêu chí | Câu hỏi cần trả lời | Rủi ro nếu không phù hợp |
|---|---|---|
| Partition pruning | Truy vấn phổ biến có điều kiện trên khóa không? | Phải mở nhiều hoặc toàn bộ phân vùng |
| Phân bố hàng | Số hàng mỗi phân vùng có cân bằng không? | Một số phân vùng quá lớn |
| Phân bố byte | Dung lượng dữ liệu mỗi phân vùng có cân bằng không? | Một phân vùng chứa hàng rộng hoặc dữ liệu lớn |
| Phân bố tải | QPS, ghi, CPU và I/O có tập trung không? | Hot partition hoặc hot key |
| Cardinality | Có đủ giá trị để tạo số phân vùng hợp lý không? | Quá ít hoặc quá nhiều phân vùng |
| Tính ổn định | Khóa có thay đổi trong vòng đời hàng không? | UPDATE có thể phải di chuyển hàng giữa phân vùng |
| Join locality | Các bảng thường join có dùng khóa tương thích không? | Tốn shuffle, network hoặc truy xuất nhiều phân vùng |
| Vòng đời dữ liệu | Có thể archive hoặc xóa theo khóa không? | Retention phức tạp, xóa hàng loạt tốn kém |
| Ràng buộc duy nhất | Primary key/unique constraint có tương thích không? | Khó bảo đảm uniqueness theo cách mong muốn |
| Vận hành | Có thể tạo trước, theo dõi và bảo trì phân vùng không? | Lỗi khi dữ liệu mới vượt phạm vi hoặc metadata quá tải |

Một khóa tốt thường giúp cả đường đọc quan trọng và một số thao tác quản trị. Tuy nhiên, không nhất thiết phải tối ưu tất cả truy vấn bằng cùng một partition key; có thể dùng chỉ mục cục bộ, bảng phụ hoặc kiến trúc lưu trữ khác để phục vụ mẫu truy cập phụ.

### Chọn khóa có ý nghĩa nghiệp vụ và ổn định

Khóa phân vùng thường nên là thuộc tính ổn định trong vòng đời hàng. Nếu một hàng thường xuyên thay đổi khóa phân vùng, hệ quản trị có thể phải chuyển hàng từ phân vùng này sang phân vùng khác. Trong một số hệ quản trị, cập nhật partition key có thể bị hạn chế hoặc được thực hiện như xóa và chèn lại; điều này có thể ảnh hưởng khóa, trigger, replication và transaction.

Ví dụ, created_at thường không thay đổi sau khi tạo sự kiện, phù hợp với phân vùng theo thời gian. status thường xuyên thay đổi từ NEW sang PROCESSING rồi COMPLETED, vì vậy phân vùng theo status có thể khiến hàng di chuyển liên tục. tenant_id thường ổn định, nhưng cần xem có tenant lớn bất thường hay không.

Không dùng một cột có thể NULL hoặc dữ liệu không hợp lệ mà chưa xác định quy tắc cho giá trị NULL, giá trị ngoài miền và phân vùng mặc định. Các giá trị này có thể dồn vào một partition hoặc gây lỗi ghi khi không có partition nhận dữ liệu.

## Các chiến lược phân vùng phổ biến

### Range partitioning

Range partitioning chia dữ liệu theo các khoảng giá trị, thường dùng thời gian hoặc số tăng dần.

Ví dụ, phân vùng bảng sự kiện theo tháng:

~~~sql
-- Cú pháp minh họa theo kiểu PostgreSQL
CREATE TABLE events (
    event_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    event_time TIMESTAMP NOT NULL,
    event_type VARCHAR(40) NOT NULL
) PARTITION BY RANGE (event_time);

CREATE TABLE events_2026_11
PARTITION OF events
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');

CREATE TABLE events_2026_12
PARTITION OF events
FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');
~~~

Ưu điểm:

- Truy vấn theo khoảng thời gian có thể loại bỏ phân vùng ngoài khoảng.
- Dễ quản lý retention bằng detach/drop partition nếu hệ quản trị hỗ trợ.
- Có thể lưu trữ phân vùng cũ trên tầng lưu trữ rẻ hơn.
- Tạo phân vùng mới theo lịch giúp quản lý dữ liệu tăng trưởng.

Rủi ro:

- Dữ liệu mới thường tập trung vào phân vùng hiện tại, tạo hot partition.
- Truy vấn không lọc thời gian có thể phải truy cập nhiều phân vùng.
- Chọn khoảng quá nhỏ tạo nhiều partition; quá lớn làm mỗi partition nặng.
- Dữ liệu đến muộn hoặc có timestamp ngoài dự kiến cần partition phù hợp.
- Tác vụ tạo partition không kịp có thể khiến INSERT thất bại hoặc dồn dữ liệu vào default partition.

Range partitioning phù hợp khi truy vấn và vòng đời dữ liệu có tính thời gian rõ rệt. Nó không tự cân bằng tải ghi nếu mọi dữ liệu mới đều rơi vào cùng khoảng hiện tại.

### Hash partitioning

Hash partitioning áp dụng hàm băm lên khóa để phân phối hàng vào một số phân vùng xác định. Nếu khóa có phân bố đủ đa dạng và hàm hash tốt, số hàng có thể cân bằng hơn so với range hoặc list.

Ví dụ khái niệm:

~~~text
partition_number = HASH(tenant_id) MOD partition_count
~~~

Cú pháp thực tế phụ thuộc hệ quản trị. Một số sản phẩm dùng số lượng bucket hoặc modulus/remainder; một số sản phẩm tự quản lý phân vùng hash.

Ưu điểm:

- Phân bố các khóa đa dạng trên nhiều phân vùng.
- Có thể giảm việc mọi bản ghi mới dồn vào một vùng tuần tự.
- Truy vấn bằng khóa hash có thể định vị một phân vùng hoặc một tập nhỏ phân vùng.
- Hữu ích khi workload chủ yếu tra cứu theo khóa phân phối.

Rủi ro:

- Truy vấn theo khoảng giá trị thường không thể loại bỏ phân vùng hiệu quả.
- Truy vấn không có partition key có thể phải truy cập tất cả phân vùng.
- Nếu một khóa cụ thể chiếm phần lớn tải, hash không chia nhỏ khóa nóng đó.
- Thay đổi số phân vùng có thể làm thay đổi ánh xạ và cần tái phân phối dữ liệu tùy hệ thống.
- Hash partitioning không tự giải quyết join lớn nếu các bảng không được phân phối tương thích.

Hash tenant_id có thể cân bằng nhiều tenant, nhưng nếu một tenant duy nhất tạo phần lớn giao dịch thì toàn bộ tải của tenant đó vẫn vào cùng partition. Đây là skew theo khóa, dù hàm hash phân bố các giá trị khác nhau rất đều.

### List partitioning

List partitioning gán giá trị hoặc nhóm giá trị cụ thể vào từng phân vùng, thường dùng region, loại dữ liệu hoặc nhóm nghiệp vụ.

Ví dụ khái niệm:

~~~sql
-- Cú pháp minh họa; danh sách partition phụ thuộc hệ quản trị
CREATE TABLE sales (
    sale_id BIGINT,
    region_code VARCHAR(10),
    sale_time TIMESTAMP
) PARTITION BY LIST (region_code);
~~~

Ưu điểm:

- Dễ cô lập dữ liệu theo nhóm nghiệp vụ.
- Truy vấn lọc chính xác region có thể pruning tốt.
- Có thể áp dụng chính sách lưu trữ hoặc bảo mật khác nhau theo nhóm.

Rủi ro:

- Số lượng giá trị có thể thay đổi và cần cập nhật cấu hình.
- Một region hoặc loại dữ liệu lớn có thể trở thành hot partition.
- Các truy vấn không lọc region có thể quét nhiều phân vùng.
- Một giá trị mới không có partition có thể bị từ chối hoặc rơi vào default partition.

Không dùng list partitioning theo một thuộc tính có phân bố rất lệch nếu chưa có chiến lược cho nhóm lớn. Một partition cho mỗi khách hàng có thể tạo quá nhiều đối tượng và overhead metadata nếu số khách hàng rất lớn.

### Composite và subpartitioning

Một số hệ quản trị hỗ trợ phân vùng nhiều cấp hoặc khóa ghép. Ví dụ, phân vùng cấp một theo thời gian, sau đó chia mỗi phân vùng theo hash của tenant_id. Ý tưởng:

~~~text
events
  ├── range(event_time): 2026-11
  │      ├── hash(tenant_id): bucket 0
  │      ├── hash(tenant_id): bucket 1
  │      └── ...
  └── range(event_time): 2026-12
         ├── hash(tenant_id): bucket 0
         ├── hash(tenant_id): bucket 1
         └── ...
~~~

Cách này có thể giữ lợi ích pruning theo thời gian đồng thời phân tán dữ liệu của nhiều tenant trong mỗi khoảng. Nhưng nó tăng số lượng phân vùng con, phức tạp hóa quản trị, backup, restore và truy vấn. Hệ quản trị có thể giới hạn loại subpartitioning, số cấp hoặc cách kết hợp range/hash/list.

Composite partition key cũng có thể là một khóa ghép nhiều cột trong cùng một quy tắc range/list. Không giả định mọi engine hỗ trợ cùng cú pháp hoặc cùng cơ chế pruning. Hãy kiểm tra tài liệu và execution plan của phiên bản đang dùng.

## Đo phân bố dữ liệu lệch

### Phân biệt lệch số hàng và lệch dung lượng

Một phân vùng có số hàng bằng phân vùng khác chưa chắc có dung lượng tương đương. Hàng có thể có kích thước khác nhau do JSON, text, blob hoặc các cột biến độ dài. Vì vậy, cần đo ít nhất:

- Số hàng mỗi phân vùng.
- Số byte hoặc dung lượng lưu trữ mỗi phân vùng.
- Số trang và mức sử dụng index.
- Tốc độ tăng trưởng theo thời gian.
- Số lần đọc/ghi, QPS/TPS và I/O theo phân vùng.
- CPU, latency và hàng đợi theo phân vùng nếu hệ thống cung cấp.

Ví dụ, partition A có 10 triệu hàng nhỏ, partition B có 4 triệu hàng nhưng chứa payload lớn. Nếu chỉ đếm hàng, có thể kết luận sai về cân bằng lưu trữ.

### Các chỉ số định lượng skew

Có thể bắt đầu bằng tỷ lệ giữa phân vùng lớn nhất và trung vị:

~~~text
skew_ratio = max(partition_size) / median(partition_size)
~~~

Nếu skew_ratio gần 1, kích thước các phân vùng khá cân bằng. Nếu giá trị cao, cần tìm nguyên nhân. Trung vị thường hữu ích hơn trung bình khi có một vài partition cực lớn.

Có thể dùng thêm hệ số biến thiên:

~~~text
CV = standard_deviation(partition_sizes) / average(partition_sizes)
~~~

CV thấp biểu thị kích thước tương đối đồng đều; CV cao cho thấy độ phân tán lớn. Không có ngưỡng chung áp dụng cho mọi hệ thống. Hãy so sánh theo thời gian và với mục tiêu vận hành.

Cần đo riêng skew của tải:

~~~text
load_skew_ratio = max(partition_QPS) / median(partition_QPS)
~~~

Một partition có thể lớn nhưng ít được truy cập; partition khác nhỏ nhưng nhận phần lớn ghi và trở thành điểm nóng. Skew dung lượng và skew tải là hai vấn đề khác nhau.

### Truy vấn thống kê theo khóa

Nếu partition key là tenant_id, có thể phân tích số hàng và tỷ lệ theo tenant:

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS row_count
FROM events
GROUP BY tenant_id
ORDER BY row_count DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Đây là phép thống kê dữ liệu theo khóa, không phải lúc nào cũng phản ánh kích thước partition vật lý. Nếu bảng được hash partition theo tenant_id, cần đối chiếu tenant với partition mà engine ánh xạ tới. Nếu partition key là thời gian, hãy đo theo khoảng thời gian và theo các nhóm tenant để phát hiện sự kết hợp tạo tải lệch.

Đo theo thời gian cũng quan trọng. Một tenant có thể nhỏ trong tổng dữ liệu nhưng tạo đột biến ghi trong một giờ. Hãy dùng cửa sổ đo đủ ngắn để phát hiện peak load và đủ dài để tránh kết luận từ nhiễu ngẫu nhiên.

## Nhận diện các dạng skew và hot partition

### Skew theo giá trị khóa

Một số giá trị xuất hiện nhiều hơn hẳn các giá trị khác. Ví dụ tenant lớn nhất chiếm 40% số hàng hoặc một category chứa phần lớn sản phẩm.

Nếu dùng hash partition theo tenant_id, tenant lớn vẫn đi vào một partition. Hash phân phối đều các giá trị khóa, không chia nhỏ một giá trị đơn lẻ. Đây là lý do cần đo histogram và tần suất theo từng khóa, không chỉ số lượng giá trị khác nhau.

Biện pháp có thể cân nhắc:

- Chia riêng tenant lớn thành nhiều bucket phụ.
- Dùng composite key gồm tenant_id và một thành phần phân tán ổn định.
- Tách workload hoặc dữ liệu của tenant lớn sang bảng/partition riêng.
- Dùng subpartitioning nếu hệ quản trị hỗ trợ.
- Định tuyến tenant lớn theo chiến lược riêng khi kiến trúc sharding cho phép.

Mọi biện pháp phải bảo đảm truy vấn theo tenant vẫn định vị được các bucket liên quan. Nếu thêm bucket nhưng mọi truy vấn vẫn phải quét tất cả bucket, có thể giảm skew ghi nhưng tăng chi phí đọc.

### Hot partition do khóa tăng đơn điệu

Range partition theo timestamp thường đưa mọi bản ghi mới vào partition hiện tại. Khi tải ghi cao, partition hiện tại có thể trở thành điểm nóng về page latch, index contention, WAL/logging hoặc I/O. Các partition cũ gần như chỉ đọc.

Biện pháp:

- Chia partition thời gian hiện tại thành các bucket hash theo tenant hoặc một khóa phân tán.
- Phân tán ghi qua nhiều shard hoặc node nếu cần mở rộng năng lực ghi.
- Thiết kế chỉ mục tránh tập trung cập nhật vào cùng một vùng trang nếu engine có hiện tượng contention.
- Dùng batch insert và kiểm soát concurrency theo khả năng hệ thống.
- Đo riêng thời gian khóa, latch, log flush và I/O để xác định đúng nút thắt.

Không chuyển sang hash partition một cách máy móc. Nếu workload đọc chủ yếu theo khoảng thời gian, mất partition pruning có thể làm chi phí đọc tăng mạnh. Subpartitioning theo thời gian rồi hash theo tenant là một lựa chọn, nhưng cần đánh giá overhead và số partition.

### Hot key và hot row

Hot key là một giá trị khóa được truy cập thường xuyên; hot row là một hàng cụ thể bị nhiều giao dịch đọc hoặc cập nhật đồng thời. Hai khái niệm này có thể xảy ra trong cùng partition nhưng không giống nhau.

Ví dụ, nhiều giao dịch cập nhật số dư của một tài khoản duy nhất. Chia partition theo account_id không giải quyết được tranh chấp trên cùng hàng. Có thể cần thiết kế lại luồng cập nhật, dùng hàng đợi, gom giao dịch, phân bổ bộ đếm theo bucket hoặc thay đổi mô hình dữ liệu.

Nếu partitioning chỉ thay đổi vị trí lưu trữ mà mọi giao dịch vẫn cập nhật cùng một hàng, lock contention vẫn còn. Hãy kiểm tra wait event, lock graph, thời gian giữ khóa và số lần cập nhật trên mỗi khóa.

### Skew do NULL hoặc giá trị mặc định

Nếu partition key thường NULL hoặc có giá trị mặc định như UNKNOWN, hàng có thể dồn vào một partition đặc biệt. Cần đo tỷ lệ NULL và giá trị mặc định trước khi triển khai.

Các lựa chọn:

- Bắt buộc partition key có giá trị hợp lệ bằng NOT NULL nếu nghiệp vụ cho phép.
- Định nghĩa partition cho NULL/default và theo dõi dung lượng/tải riêng.
- Gán giá trị phân vùng hợp lệ ở tầng ghi nếu có quy tắc rõ ràng.
- Không thay NULL bằng một giá trị chung nếu điều đó làm nhiều thực thể khác nhau bị gom vào một partition nóng.

### Skew do thời gian đến muộn hoặc dữ liệu hồi tố

Một hệ thống sự kiện có thể nhận dữ liệu muộn, import lịch sử hoặc cập nhật bản ghi của kỳ trước. Nếu partition theo event_time, ghi vào các partition cũ có thể tạo tải phân tán và tăng chi phí index/maintenance. Nếu partition theo ingestion_time, truy vấn nghiệp vụ theo event_time có thể không pruning tốt.

Cần phân biệt event time (thời điểm sự kiện xảy ra) và ingestion time (thời điểm hệ thống nhận dữ liệu). Chọn khóa theo mục tiêu truy vấn và retention. Nếu cả hai quan trọng, có thể lưu cả hai cột, tạo chỉ mục phù hợp hoặc dùng chiến lược partition/subpartition theo một khóa và index theo khóa còn lại.

## Partition pruning và khóa phân vùng

### Partition pruning hoạt động thế nào?

Partition pruning là khả năng hệ quản trị loại bỏ các phân vùng không thể chứa hàng thỏa điều kiện truy vấn. Với range partition theo event_time, truy vấn có điều kiện thời gian cụ thể có thể chỉ mở những partition giao với khoảng đó.

Ví dụ:

~~~sql
SELECT event_id, event_time, tenant_id
FROM events
WHERE event_time >= TIMESTAMP '2026-11-01 00:00:00'
  AND event_time <  TIMESTAMP '2026-12-01 00:00:00';
~~~

Nếu bảng có partition theo tháng, truy vấn có thể chỉ truy cập partition tháng 11. Cần xác nhận execution plan thực tế cho thấy các partition bị loại bỏ.

Nếu truy vấn không có điều kiện trên partition key, hệ quản trị có thể phải mở hoặc quét nhiều partition. Với một số engine, pruning động có thể xảy ra khi giá trị partition key đến từ join hoặc tham số lúc thực thi; mức hỗ trợ phụ thuộc hệ quản trị và phiên bản.

### Điều kiện truy vấn cần tương thích với partition key

Điều kiện lọc nên so sánh trực tiếp partition key với hằng hoặc tham số có kiểu tương thích. Hàm hoặc chuyển đổi trên cột có thể làm pruning khó hơn nếu optimizer không thể biến đổi biểu thức.

Ví dụ, thay vì lọc bằng hàm DATE trên event_time, hãy dùng khoảng thời gian nửa mở với mốc phù hợp. Đồng thời, bind tham số đúng kiểu timestamp và múi giờ nghiệp vụ.

Với partition key ghép, truy vấn cần cung cấp đủ điều kiện để pruning hiệu quả theo khả năng engine. Nếu phân vùng theo tenant_id và thời gian, chỉ có tenant_id có thể loại được một số nhánh nhưng vẫn phải đọc nhiều partition thời gian; chỉ có thời gian có thể đọc mọi tenant bucket trong khoảng đó.

### Kiểm tra pruning trong kế hoạch

Trong execution plan hoặc thống kê thực thi, tìm:

- Số partition được lập kế hoạch truy cập.
- Số partition thực tế được mở hoặc quét.
- Partition bị loại bỏ (pruned partitions).
- Số hàng đọc và số hàng trả về trên từng partition.
- Có scan toàn bộ partition do thiếu điều kiện hay không.
- Điều kiện partition key có bị chuyển đổi hoặc bọc hàm không.
- Join có làm phát sinh pruning động hay không.

Tên trường và cách hiển thị khác nhau theo sản phẩm. Hãy dùng EXPLAIN/actual plan hoặc công cụ giám sát đúng hệ quản trị.

## Partitioning và chỉ mục

### Local index và global index

Một số hệ quản trị cung cấp local index, mỗi partition có phần chỉ mục riêng; một số hỗ trợ global index bao phủ nhiều partition. Cách tổ chức ảnh hưởng đến truy vấn, tính duy nhất, rebuild, detach/drop partition và tính sẵn sàng.

Local index thường thuận tiện khi bảo trì hoặc xóa một partition, vì chỉ mục gắn với partition đó. Nhưng truy vấn không lọc partition key có thể phải truy cập nhiều index cục bộ. Global index có thể giúp tra cứu xuyên partition nhưng có thể làm thao tác bảo trì partition phức tạp hơn; một số engine cần cập nhật hoặc rebuild index khi detach/drop partition.

Không giả định local/global index có cùng tên hoặc hành vi giữa PostgreSQL, Oracle, SQL Server, MySQL và các hệ quản trị phân tán. Hãy xác định đúng khả năng của sản phẩm và phiên bản.

### Unique constraint và partition key

Một số hệ quản trị yêu cầu unique constraint hoặc primary key trên bảng partitioned phải bao gồm partition key để có thể bảo đảm tính duy nhất bằng các index cục bộ. Sản phẩm khác có thể hỗ trợ global unique index hoặc cơ chế riêng.

Ví dụ, nếu bảng partition theo event_time nhưng event_id chỉ duy nhất toàn bảng, việc tạo UNIQUE(event_id) có thể bị giới hạn ở một số engine nếu không có global index. Có thể cần dùng khóa ghép (event_time, event_id), một bảng registry riêng hoặc cơ chế định danh toàn cục khác tùy yêu cầu.

Không thay đổi khóa chính chỉ để thỏa điều kiện partitioning mà chưa xem xét các tham chiếu và hợp đồng ứng dụng. Hãy kiểm tra toàn vẹn dữ liệu và cách đảm bảo uniqueness xuyên partition.

### Partition key trong index

Chỉ mục trên các cột thường truy vấn vẫn có thể cần partition key để hỗ trợ pruning hoặc định vị dữ liệu hiệu quả. Ví dụ, index cục bộ trên customer_id trong từng partition thời gian có thể phục vụ truy vấn theo customer_id sau khi partition pruning giới hạn khoảng thời gian. Nếu truy vấn không lọc thời gian, hệ quản trị có thể phải tìm customer_id trong nhiều partition.

Cân nhắc index gồm partition key và cột truy vấn, nhưng không thêm mọi cột vào mọi chỉ mục. Đo số lần truy cập partition, số trang đọc, lookup và chi phí ghi.

## Xử lý skew: các chiến lược thực tế

### Hash subpartitioning hoặc bucket hóa

Khi một tenant lớn tạo tải quá cao trong partition, có thể chia dữ liệu của tenant thành các bucket phụ bằng một khóa phân tán ổn định, chẳng hạn hash của entity_id:

~~~text
bucket = HASH(entity_id) MOD bucket_count
partition = (tenant_id, bucket)
~~~

Khi đó dữ liệu của một tenant được phân tán qua nhiều bucket. Truy vấn theo tenant có thể phải truy cập tất cả bucket của tenant, nhưng mỗi bucket nhỏ hơn và tải ghi có thể được phân tán.

Đánh đổi:

- Truy vấn theo tenant cần fan-out qua nhiều bucket.
- Truy vấn theo entity_id có thể định vị bucket nếu biết khóa.
- Thay đổi bucket_count có thể cần tái phân phối dữ liệu.
- Hash function và cách mã hóa khóa phải ổn định giữa các dịch vụ.
- Một entity_id nóng vẫn có thể dồn vào một bucket và gây hot key.

Bucket hóa không phải phép chia tải miễn phí; nó đổi chi phí ghi tập trung lấy thêm công việc định tuyến và đọc nhiều bucket.

### Tách riêng nhóm dữ liệu ngoại lệ

Nếu một tenant hoặc khách hàng lớn chiếm tỷ trọng áp đảo, có thể tách riêng thành partition, bảng hoặc shard chuyên biệt. Các tenant thông thường dùng chiến lược chung; nhóm lớn có chính sách riêng.

Cách này giúp điều chỉnh tài nguyên và bảo trì độc lập, nhưng tăng độ phức tạp truy vấn, routing, backup và triển khai. Cần có quy tắc rõ ràng để ứng dụng biết dữ liệu nằm ở đâu và bảo đảm truy vấn toàn cục hợp nhất kết quả đúng thứ tự.

### Chọn lại khoảng range

Với range partition theo thời gian, kích thước partition quá lớn có thể làm bảo trì chậm; quá nhỏ tạo nhiều partition. Hãy chọn khoảng theo tốc độ tăng dữ liệu và cửa sổ truy vấn thường gặp, ví dụ ngày, tuần hoặc tháng.

Nếu một ngày có lượng dữ liệu rất lớn, partition theo ngày vẫn có thể quá nóng. Có thể subpartition theo hash hoặc giảm khoảng thời gian. Nếu lượng dữ liệu thấp, partition theo ngày có thể tạo hàng nghìn partition mà không mang lại lợi ích tương xứng.

### Tách đọc và ghi theo nhu cầu

Một số workload cần ghi liên tục vào partition hiện tại nhưng đọc nhiều dữ liệu lịch sử. Có thể dùng tầng lưu trữ hoặc replica khác cho truy vấn lịch sử, archive partition cũ, hoặc tạo bảng tổng hợp phục vụ báo cáo.

Đây là thay đổi kiến trúc lớn hơn partition key. Cần xem freshness, replication lag, consistency và chi phí vận hành. Không sao chép dữ liệu sang hệ khác nếu chưa xác định ai chịu trách nhiệm về tính nhất quán.

## Ví dụ lựa chọn khóa cho bảng sự kiện đa tenant

Giả sử hệ thống ghi sự kiện với các đặc điểm:

- Hàng mới được ghi liên tục.
- Truy vấn vận hành thường lọc theo tenant_id và khoảng event_time.
- Báo cáo lịch sử chủ yếu quét theo thời gian.
- Dữ liệu được giữ 13 tháng rồi archive hoặc xóa.
- Một số tenant lớn hơn hàng trăm lần tenant trung bình.

Ba lựa chọn được cân nhắc:

| Phương án | Ưu điểm | Rủi ro |
|---|---|---|
| Range(event_time) | Pruning theo thời gian và retention thuận tiện | Partition hiện tại nhận phần lớn ghi; tenant lớn có thể chi phối |
| Hash(tenant_id) | Phân tán các tenant khác nhau; truy vấn tenant có thể định vị | Tenant lớn vẫn nóng; truy vấn lịch sử theo thời gian phải đi qua nhiều partition |
| Range(event_time) + hash(tenant_id) | Pruning theo thời gian và phân tán tenant trong từng khoảng | Nhiều partition con; truy vấn cần nhiều bucket và quản trị phức tạp hơn |

Nếu truy vấn lịch sử theo thời gian chiếm phần lớn tải và retention là yêu cầu quan trọng, range theo event_time là điểm khởi đầu hợp lý. Nếu một số tenant gây skew tải ghi, subpartition hash theo tenant hoặc bucket của entity có thể giảm tập trung. Nhưng cần thử trên dữ liệu đại diện để xác định số bucket và chi phí truy vấn tenant.

Một phương án thử nghiệm có thể so sánh:

- Số hàng và dung lượng partition lớn nhất/trung vị.
- QPS/TPS và p95/p99 theo partition.
- Số partition được pruning trong truy vấn theo tenant và thời gian.
- I/O, CPU, lock/latch wait và tốc độ ghi.
- Thời gian archive/drop partition.
- Số partition và chi phí lập kế hoạch.
- Fan-out khi truy vấn tenant lớn hoặc báo cáo toàn hệ thống.

Không chọn phương án chỉ dựa trên cân bằng số hàng. Mục tiêu là cân bằng tải quan trọng và giảm chi phí truy vấn thực tế.

## Quy trình đánh giá và kiểm chứng partition key

1. **Thu thập workload:** query fingerprint, điều kiện filter, join, sort, tỷ lệ đọc/ghi, concurrency và yêu cầu retention.
2. **Lập hồ sơ dữ liệu:** cardinality, histogram, số hàng, byte, NULL, giá trị mặc định và top key theo tần suất.
3. **Đề xuất khóa ứng viên:** đánh giá pruning, cân bằng dữ liệu, tải, độ ổn định, uniqueness và join locality.
4. **Mô phỏng phân bố:** tính số hàng/byte theo partition và ước lượng skew ratio, CV, phân bố tải.
5. **Kiểm tra hot key:** xác định tenant, account hoặc giá trị nào tạo tải vượt trội; phân biệt hot partition với hot row.
6. **Tạo thử nghiệm:** dùng bản sao dữ liệu và workload đại diện; không thay đổi partitioning production chỉ dựa trên ước lượng.
7. **Đo kế hoạch:** xác nhận partition pruning, số partition truy cập, số hàng đọc và chi phí index.
8. **Đo tài nguyên:** CPU, I/O, latency, queue, lock/latch wait, throughput và replication nếu có.
9. **Kiểm tra vận hành:** tạo partition mới, dữ liệu đến muộn, default partition, retention, backup, restore và thay đổi schema.
10. **So sánh toàn workload:** đọc, ghi, báo cáo, join, archive và các trường hợp tenant lớn.
11. **Triển khai có kiểm soát:** chuẩn bị kế hoạch di chuyển, kiểm tra tính toàn vẹn, theo dõi skew và có phương án quay lui.
12. **Đánh giá định kỳ:** dữ liệu và phân bố tải thay đổi theo thời gian; khóa phù hợp hôm nay có thể trở thành điểm nóng khi quy mô tăng.

## Những sai lầm thường gặp

- **Chọn khóa chỉ vì cardinality cao:** nhiều giá trị không bảo đảm phân bố đều.
- **Chọn tenant_id mà không đo tenant lớn:** một tenant có thể chiếm phần lớn hàng hoặc tải.
- **Dùng range theo thời gian và bỏ qua hot partition hiện tại:** mọi ghi mới có thể tập trung vào cùng vùng.
- **Dùng hash và kỳ vọng truy vấn range được pruning:** hash không giữ thứ tự giá trị thời gian.
- **Tạo một partition cho mỗi khách hàng:** số lượng partition và metadata có thể tăng quá lớn.
- **Chỉ đo số hàng:** bỏ qua byte, IOPS, QPS, CPU và p95/p99.
- **Nhầm hot partition với hot row:** phân tán partition không giải quyết tranh chấp trên cùng hàng.
- **Thêm bucket mà không sửa truy vấn:** truy vấn có thể phải fan-out qua tất cả bucket.
- **Bỏ qua khóa ghép hoặc tenant scope:** dữ liệu có thể được nối hoặc truy vấn sai phạm vi.
- **Không chuẩn bị partition tương lai:** INSERT có thể thất bại hoặc dồn vào default partition.
- **Quên dữ liệu đến muộn:** ghi vào partition lịch sử có thể tạo tải bất ngờ.
- **Giả định partitioning làm tăng năng lực phần cứng:** các partition trên cùng node vẫn cạnh tranh tài nguyên.
- **Không kiểm tra uniqueness và index:** ràng buộc toàn cục có thể bị giới hạn theo engine.
- **Không đo số partition được pruning:** bảng đã phân vùng nhưng truy vấn vẫn quét gần như toàn bộ.

## Checklist lựa chọn khóa phân vùng

- [ ] Xác định truy vấn phổ biến có lọc theo khóa ứng viên hay không.
- [ ] Đo cardinality và phân bố giá trị, không chỉ số lượng giá trị khác nhau.
- [ ] So sánh số hàng và dung lượng giữa các partition.
- [ ] Đo QPS/TPS, CPU, I/O và độ trễ theo partition hoặc key.
- [ ] Tìm tenant/key nóng và phân biệt hot partition với hot row.
- [ ] Đánh giá range, hash, list và subpartitioning theo workload.
- [ ] Kiểm tra khả năng pruning cho truy vấn theo khóa và truy vấn không có khóa.
- [ ] Xem xét tính ổn định của khóa và chi phí di chuyển hàng.
- [ ] Kiểm tra join locality, primary key, unique constraint và foreign key.
- [ ] Đánh giá số lượng partition, metadata và chi phí lập kế hoạch.
- [ ] Chuẩn bị partition tương lai, default partition và xử lý dữ liệu đến muộn.
- [ ] Thử nghiệm với dữ liệu và tải đại diện trước khi triển khai.
- [ ] Đo lại đọc, ghi, retention, backup/restore và các truy vấn quan trọng.

## Kết luận

Khóa phân vùng quyết định dữ liệu được đặt ở đâu, truy vấn có thể loại bỏ những phần nào và tải có tập trung vào một vùng hay không. Chọn khóa chỉ dựa trên cardinality hoặc một truy vấn riêng lẻ dễ tạo ra phân vùng mất cân bằng, hot partition hoặc chi phí fan-out cao.

Hãy bắt đầu từ workload và vòng đời dữ liệu, đo phân bố theo số hàng, byte và tải, rồi so sánh các chiến lược range, hash, list hoặc phân vùng nhiều cấp. Khi phát hiện skew, cần xác định đó là lệch dung lượng, lệch tải, hot key hay hot row trước khi chọn biện pháp. Cuối cùng, dùng execution plan, số liệu tài nguyên và thử nghiệm trên dữ liệu đại diện để xác nhận partition pruning, độ cân bằng và hiệu năng toàn workload sau điều chỉnh.