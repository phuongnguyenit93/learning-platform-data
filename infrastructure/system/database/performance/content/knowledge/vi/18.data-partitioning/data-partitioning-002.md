# Phân vùng theo khoảng, danh sách và băm theo mẫu truy cập

Phân vùng bảng (table partitioning) chia một bảng logic lớn thành nhiều phần dữ liệu nhỏ hơn theo một quy tắc xác định. Ứng dụng vẫn có thể truy vấn bảng cha như một bảng duy nhất, trong khi hệ quản trị lưu và quản lý các partition riêng. Khi điều kiện truy vấn phù hợp với khóa phân vùng, optimizer có thể loại bỏ những partition không liên quan (partition pruning), giảm lượng dữ liệu phải đọc. Phân vùng cũng hỗ trợ quản lý vòng đời dữ liệu, bảo trì chỉ mục và lưu trữ theo từng giai đoạn.

Ba chiến lược phổ biến là **Range**, **List** và **Hash**. Range gom dữ liệu theo khoảng giá trị liên tiếp, thường phù hợp với thời gian hoặc số thứ tự. List gom theo các giá trị rời rạc như khu vực hoặc nhóm nghiệp vụ. Hash phân phối giá trị khóa qua các partition theo hàm băm, thường dùng để chia đều dữ liệu khi truy vấn hay lọc theo khóa đó. Mỗi chiến lược phục vụ một kiểu truy cập khác nhau; chọn sai partition key có thể khiến truy vấn phải quét mọi partition và làm hệ thống phức tạp hơn.

Trong tối ưu hiệu năng cơ sở dữ liệu, cần bắt đầu từ mẫu truy cập và vòng đời dữ liệu thay vì chọn partition chỉ vì bảng đã lớn. Bài học này giải thích cách hoạt động của Range, List và Hash partitioning, cách kết hợp chúng, cách thiết kế chỉ mục và ràng buộc, cùng quy trình đo kiểm partition pruning, phân phối dữ liệu và chi phí vận hành.

## 1. Phân vùng bảng giải quyết vấn đề gì?

Một bảng lớn có thể chứa hàng trăm triệu hoặc hàng tỷ hàng. Khi dữ liệu tăng, một số hoạt động trở nên tốn kém:

- Truy vấn chỉ cần dữ liệu của một khoảng thời gian nhưng phải đọc phạm vi rộng.
- Xóa dữ liệu hết hạn bằng DELETE tạo nhiều log, dead tuple hoặc undo/redo và gây áp lực lên replication.
- Tạo lại chỉ mục hoặc bảo trì toàn bảng mất nhiều thời gian.
- Dữ liệu nóng và dữ liệu lịch sử có yêu cầu lưu trữ, backup hoặc truy cập khác nhau.
- Một số thao tác quản trị cần cô lập theo tenant, khu vực hoặc giai đoạn dữ liệu.

Partitioning chia bảng thành các phần có ranh giới rõ ràng. Nếu truy vấn nêu điều kiện trên partition key, hệ quản trị có thể chỉ truy cập những partition có khả năng chứa kết quả. Ví dụ, truy vấn lấy sự kiện trong tháng 11 có thể bỏ qua partition của các tháng khác.

Partitioning thường mang lại ba nhóm lợi ích:

1. **Giảm phạm vi đọc:** partition pruning loại các phần không liên quan trước hoặc trong quá trình lập kế hoạch/thực thi.
2. **Quản lý vòng đời:** có thể detach, archive, truncate hoặc drop một partition cũ thay vì xóa từng hàng, tùy khả năng DBMS.
3. **Bảo trì theo phạm vi:** tạo hoặc rebuild chỉ mục, nạp dữ liệu và quản lý thống kê theo từng phần.

Partitioning không tự động làm một truy vấn nhanh hơn. Nếu truy vấn không lọc theo partition key, hệ quản trị có thể phải truy cập tất cả partition. Nhiều partition cũng làm tăng metadata, chi phí lập kế hoạch, số đối tượng chỉ mục và công việc vận hành.

## 2. Các khái niệm cơ bản

- **Partitioned table:** bảng logic được chia thành các partition.
- **Partition key:** cột hoặc biểu thức quyết định hàng thuộc partition nào.
- **Partition boundary:** ranh giới xác định giá trị thuộc partition nào.
- **Partition pruning/elimination:** loại bỏ các partition chắc chắn không chứa hàng thỏa điều kiện.
- **Partition-local index:** chỉ mục được xây dựng riêng trên từng partition.
- **Global index:** chỉ mục có phạm vi bao phủ nhiều partition như một cấu trúc chung; khả năng hỗ trợ tùy DBMS.
- **Default partition:** nơi nhận giá trị không khớp các partition được khai báo, nếu hệ quản trị hỗ trợ.
- **Subpartitioning:** chia một partition thành các partition con theo một quy tắc thứ hai.

Ứng dụng thường truy vấn qua tên bảng logic. Hệ quản trị định tuyến thao tác ghi đến partition phù hợp và sử dụng metadata để chọn partition khi đọc. Cách khai báo, lưu trữ, quản lý chỉ mục và mức độ tự động khác nhau giữa PostgreSQL, MySQL, SQL Server, Oracle và các hệ quản trị khác.

## 3. Chọn partition key theo mẫu truy cập

Partition key là quyết định quan trọng nhất. Một khóa tốt cần phục vụ truy vấn thường gặp và phân phối dữ liệu phù hợp với mục tiêu quản lý.

Hãy phân tích:

- Các cột thường xuất hiện trong WHERE.
- Các điều kiện theo khoảng thời gian hoặc khoảng giá trị.
- Các điều kiện bằng theo tenant, khách hàng, khu vực hoặc loại dữ liệu.
- Truy vấn thường đọc một partition hay phải kết hợp nhiều partition.
- Join có thể thực hiện partition-wise hay không.
- Dữ liệu đến muộn hoặc được cập nhật lại có thường xuyên không.
- Dữ liệu có phân bố lệch theo partition key không.
- Chính sách lưu trữ, archive và xóa dữ liệu hết hạn.

Ví dụ, bảng events thường được truy vấn theo thời gian:

~~~sql
SELECT event_id, tenant_id, event_type
FROM events
WHERE occurred_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND occurred_at <  TIMESTAMP '2026-12-01 00:00:00';
~~~

Partition theo occurred_at có thể cho phép bỏ qua các tháng khác. Nếu phần lớn truy vấn lại lọc theo tenant_id mà không có điều kiện thời gian, partition theo tháng có thể không giảm được số partition cần mở. Khi đó có thể cần chỉ mục phù hợp trên từng partition, subpartitioning hoặc một mô hình lưu trữ khác.

### 3.1. Không chọn partition key chỉ vì cột có nhiều giá trị

NDV cao không tự động làm cột trở thành partition key tốt. Ví dụ, partition theo order_id có thể tạo quá nhiều partition hoặc không giúp các truy vấn theo thời gian. Hash partition theo customer_id có thể phân phối nhiều khách hàng qua các partition, nhưng truy vấn theo created_at sẽ không tự động loại bỏ partition.

Hãy chọn key mà các truy vấn quan trọng thường xuyên dùng, đồng thời cân bằng kích thước partition và khả năng bảo trì.

### 3.2. Partition key nên ổn định

Nếu partition key thay đổi, hàng có thể phải chuyển từ partition này sang partition khác. Việc cập nhật có thể tốn kém, cần khóa và có giới hạn riêng theo hệ quản trị. Cột thời gian tạo bản ghi thường ổn định hơn cột trạng thái hoặc khu vực có thể thay đổi.

Nếu dữ liệu có thể đến muộn, cần có quy trình đưa hàng vào partition cũ hoặc xử lý hàng không khớp ranh giới. Không nên mặc định mọi dữ liệu luôn đến đúng thứ tự thời gian.

## 4. Range partitioning — phân vùng theo khoảng

Range partitioning chia miền giá trị thành các khoảng liên tiếp. Mỗi partition nhận một khoảng không chồng lấn, ví dụ một tháng, một quý hoặc một dải số ID.

Đây là chiến lược phù hợp khi truy vấn thường lọc theo khoảng và dữ liệu có vòng đời theo thời gian.

Ví dụ phân vùng sự kiện theo tháng:

~~~sql
CREATE TABLE events (
    event_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB,
    PRIMARY KEY (occurred_at, event_id)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE events_2026_11
PARTITION OF events
FOR VALUES FROM ('2026-11-01 00:00:00+00')
             TO ('2026-12-01 00:00:00+00');

CREATE TABLE events_2026_12
PARTITION OF events
FOR VALUES FROM ('2026-12-01 00:00:00+00')
             TO ('2027-01-01 00:00:00+00');
~~~

Đây là cú pháp PostgreSQL minh họa. Ranh giới FROM là bao gồm (inclusive), TO là không bao gồm (exclusive), vì vậy các khoảng liền nhau không bị trùng tại thời điểm đầu tháng. Kiểu timestamp và múi giờ trong ví dụ được thống nhất theo UTC.

### 4.1. Lợi ích của Range

- Truy vấn theo khoảng ngày/tháng có thể chỉ mở các partition giao với khoảng đó.
- Dữ liệu mới có thể được nạp vào partition hiện tại hoặc tương lai.
- Dữ liệu cũ có thể được detach/archive/drop theo đơn vị thời gian.
- Có thể áp dụng chính sách lưu trữ khác nhau cho dữ liệu nóng và dữ liệu lịch sử.
- Bảo trì chỉ mục theo từng partition thay vì toàn bộ bảng logic.

### 4.2. Chọn kích thước khoảng

Kích thước partition cần phù hợp với tốc độ tăng dữ liệu và cửa sổ truy vấn:

| Kích thước | Ưu điểm | Rủi ro |
|---|---|---|
| Theo ngày | Pruning rất cụ thể cho truy vấn ngày; dễ xóa dữ liệu theo ngày | Số partition tăng nhanh, metadata và quản lý phức tạp |
| Theo tháng | Cân bằng giữa số partition và phạm vi truy vấn phổ biến | Truy vấn chỉ vài giờ vẫn mở partition của cả tháng |
| Theo quý | Ít partition hơn, dễ quản lý | Mỗi partition lớn hơn, bảo trì và pruning kém chi tiết |
| Theo năm | Đơn giản với dữ liệu tăng chậm | Có thể không đủ nhỏ để giảm chi phí truy vấn hoặc bảo trì |

Không có kích thước chuẩn cho mọi bảng. Hãy ước lượng số hàng và dung lượng mỗi kỳ, số kỳ cần giữ, số partition đồng thời và tần suất truy vấn. Partition quá nhỏ làm tăng số đối tượng; partition quá lớn làm giảm lợi ích quản lý và có thể tăng thời gian bảo trì.

### 4.3. Ranh giới nửa mở

Với timestamp, nên dùng khoảng nửa mở [bắt đầu, kết thúc) thay vì kết thúc bằng thời điểm cuối ngày:

~~~sql
WHERE occurred_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND occurred_at <  TIMESTAMP '2026-12-01 00:00:00'
~~~

Cách này tránh phụ thuộc độ chính xác của timestamp và phù hợp với ranh giới partition liền nhau. Với timestamp có múi giờ, hãy tính biên theo múi giờ nghiệp vụ rồi chuyển về kiểu và múi giờ lưu trữ nhất quán.

### 4.4. Dữ liệu đến muộn và khoảng ngoài dự kiến

Một partition theo tháng có thể nhận sự kiện cũ được đồng bộ trễ. Cần tạo trước partition lịch sử hoặc có quy trình đưa dữ liệu vào đúng partition. Nếu không có partition phù hợp, lệnh INSERT có thể thất bại, trừ khi DBMS hỗ trợ partition mặc định.

Partition mặc định giúp tránh lỗi ghi khi gặp giá trị chưa được khai báo, nhưng có thể che giấu việc thiếu partition mới. Cần theo dõi kích thước default partition và chuyển dữ liệu ra đúng partition định kỳ. Một số hệ quản trị không thể tách partition mặc định nếu còn hàng vi phạm ranh giới mới mà không xử lý trước.

## 5. List partitioning — phân vùng theo danh sách giá trị

List partitioning gán các giá trị rời rạc hoặc nhóm giá trị vào từng partition. Nó phù hợp khi dữ liệu có các nhóm ổn định và truy vấn thường lọc theo nhóm đó.

Ví dụ, chia dữ liệu theo vùng:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT NOT NULL,
    region_code VARCHAR(10) NOT NULL,
    email VARCHAR(320) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (region_code, customer_id)
) PARTITION BY LIST (region_code);

CREATE TABLE customers_north
PARTITION OF customers
FOR VALUES IN ('NORTH');

CREATE TABLE customers_south
PARTITION OF customers
FOR VALUES IN ('SOUTH');

CREATE TABLE customers_central
PARTITION OF customers
FOR VALUES IN ('CENTRAL');
~~~

Ví dụ dùng cú pháp PostgreSQL. Khi truy vấn lọc region_code = 'NORTH', hệ quản trị có thể chỉ truy cập partition NORTH nếu partition pruning được áp dụng.

### 5.1. Khi nào List phù hợp?

- Khu vực địa lý có số lượng giới hạn và tương đối ổn định.
- Nhóm dữ liệu có chính sách lưu trữ hoặc quyền truy cập khác nhau.
- Truy vấn thường chỉ đọc một hoặc vài nhóm.
- Có nhu cầu detach, archive hoặc chuyển nhóm dữ liệu riêng.

### 5.2. Hạn chế của List

- Danh sách giá trị có thể tăng theo thời gian và cần tạo partition mới.
- Nếu một nhóm chiếm phần lớn dữ liệu, partition đó có thể rất lớn.
- Truy vấn không lọc theo list key có thể phải mở tất cả partition.
- Thay đổi giá trị phân loại có thể làm hàng chuyển partition.
- Nếu nhóm quá nhiều, số partition và thao tác quản trị tăng nhanh.

List theo status thường không phù hợp nếu trạng thái thay đổi liên tục. Một đơn hàng chuyển từ NEW sang PAID có thể phải di chuyển giữa partition. Nếu truy vấn thường xem tất cả trạng thái hoặc lọc theo thời gian, partition theo status có thể không đem lại lợi ích tương xứng.

### 5.3. Giá trị không nằm trong danh sách

Khi một giá trị mới xuất hiện, hệ quản trị có thể từ chối INSERT nếu không có partition phù hợp hoặc partition mặc định. Hãy định nghĩa quy trình thêm nhóm mới trước khi ứng dụng phát sinh dữ liệu.

Nếu dùng default partition, cần theo dõi các giá trị rơi vào đó. Default partition không nên trở thành nơi chứa lâu dài mọi giá trị không được quản lý.

## 6. Hash partitioning — phân vùng theo hàm băm

Hash partitioning áp dụng hàm băm lên partition key và phân phối hàng vào các partition theo phần dư hoặc cơ chế phân vùng nội bộ của DBMS. Mục tiêu thường là phân tán dữ liệu tương đối đều khi giá trị khóa có phân phối phù hợp.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE user_activity (
    activity_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    action_type TEXT NOT NULL,
    PRIMARY KEY (user_id, activity_id)
) PARTITION BY HASH (user_id);

CREATE TABLE user_activity_p0
PARTITION OF user_activity
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE user_activity_p1
PARTITION OF user_activity
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE user_activity_p2
PARTITION OF user_activity
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE user_activity_p3
PARTITION OF user_activity
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
~~~

Với 4 partition, mỗi partition nhận một nhóm giá trị user_id theo quy tắc hash của PostgreSQL. Truy vấn có điều kiện bằng trên user_id có thể cho phép pruning đến partition tương ứng. Cú pháp và cách phân phối cụ thể phụ thuộc DBMS.

### 6.1. Lợi ích của Hash

- Phân tán nhiều khóa qua một số partition cố định.
- Có thể giảm kích thước mỗi partition so với bảng đơn lớn.
- Phù hợp với truy vấn tra cứu theo khóa bằng hoặc một tập khóa.
- Không cần khai báo trước từng giá trị như List.
- Có thể giúp phân phối tải lưu trữ khi khóa có cardinality và tần suất tương đối cân bằng.

### 6.2. Hạn chế của Hash

- Không giữ thứ tự theo giá trị khóa; truy vấn theo khoảng thường không được lợi như Range.
- Truy vấn không có điều kiện trên partition key có thể phải mở mọi partition.
- Một khóa nóng vẫn luôn ánh xạ vào một partition; hash không chia một giá trị đơn lẻ thành nhiều partition.
- Thay đổi số partition có thể yêu cầu tái phân phối dữ liệu hoặc quy trình migration.
- Phân phối đều theo số hàng chưa chắc đều theo kích thước hàng hoặc chi phí xử lý.

Hash partitioning theo tenant_id có thể phân phối nhiều tenant qua các partition, nhưng một tenant cực lớn vẫn tập trung vào một partition. Nếu một vài tenant tạo phần lớn tải, cần đo skew và cân nhắc chiến lược riêng như subpartitioning theo thời gian, tách tenant lớn hoặc thiết kế shard theo yêu cầu.

### 6.3. Chọn số partition

Số partition cần cân bằng giữa khả năng phân tán và overhead:

- Quá ít partition: mỗi partition vẫn lớn và có thể chưa tận dụng tốt tài nguyên.
- Quá nhiều partition: metadata, lập kế hoạch, mở index và bảo trì tốn thêm chi phí.
- Số partition phải phù hợp với số lượng giá trị, phân bố khóa, số node hoặc mức song song của hệ thống.
- Thay đổi số partition về sau có thể cần di chuyển dữ liệu và cập nhật ứng dụng/metadata.

Không chọn số partition chỉ bằng số core CPU. Partitioning là cách tổ chức dữ liệu; mức song song hóa là quyết định thực thi khác và phụ thuộc DBMS.

## 7. So sánh Range, List và Hash

| Tiêu chí | Range | List | Hash |
|---|---|---|---|
| Cách chia | Khoảng giá trị liên tiếp | Nhóm giá trị liệt kê | Hàm băm của khóa |
| Mẫu truy vấn phù hợp | Khoảng thời gian, khoảng ID, ngày tháng | Lọc theo vùng hoặc nhóm rời rạc | Tra cứu bằng theo khóa, phân phối nhiều khóa |
| Thứ tự dữ liệu | Có locality theo khoảng | Theo nhóm giá trị | Không giữ thứ tự khóa |
| Partition pruning | Tốt với điều kiện khoảng trên partition key | Tốt với giá trị thuộc danh sách | Tốt với điều kiện phù hợp trên hash key |
| Quản lý vòng đời | Thuận tiện khi dữ liệu hết hạn theo khoảng | Thuận tiện khi nhóm có vòng đời riêng | Ít thuận tiện cho archive theo thời gian |
| Rủi ro chính | Partition mới, dữ liệu đến muộn, khoảng không đều | Nhóm mới, nhóm quá lớn, giá trị thay đổi | Hot key, số partition, tái phân phối |
| Ví dụ | Events theo tháng | Customers theo region | Activity theo user_id |

Chọn Range khi truy vấn theo khoảng và chính sách retention là trọng tâm. Chọn List khi nhóm giá trị ổn định và truy vấn thường giới hạn theo nhóm. Chọn Hash khi cần phân phối nhiều khóa và truy vấn thường dùng điều kiện bằng trên khóa đó.

## 8. Subpartitioning và kết hợp nhiều chiến lược

Một số hệ quản trị hỗ trợ chia partition theo nhiều cấp. Ví dụ, chia Range theo tháng rồi Hash theo tenant_id trong mỗi tháng:

- Range theo occurred_at giới hạn khoảng thời gian và hỗ trợ xóa/archive theo tháng.
- Hash theo tenant_id chia dữ liệu trong mỗi tháng thành các nhóm nhỏ hơn.
- Truy vấn theo tháng và tenant có thể pruning cả cấp Range lẫn Hash nếu optimizer hỗ trợ và predicate phù hợp.

Ví dụ khái niệm:

~~~text
events
├── events_2026_11  [Range: tháng 11]
│   ├── hash_0      [Hash: tenant]
│   ├── hash_1
│   ├── hash_2
│   └── hash_3
└── events_2026_12  [Range: tháng 12]
    ├── hash_0      [Hash: tenant]
    ├── hash_1
    ├── hash_2
    └── hash_3
~~~

Subpartitioning có thể cải thiện tổ chức dữ liệu khi có hai mẫu truy cập quan trọng, nhưng số partition vật lý tăng theo tích số partition ở mỗi cấp. Với 36 tháng và 16 hash partition mỗi tháng, có 576 partition con. Số lượng này có thể tạo overhead đáng kể.

Không phải mọi DBMS hỗ trợ cùng kiểu kết hợp hoặc cùng mức pruning. Cần xác minh cú pháp, giới hạn và kế hoạch thực tế. Trước khi dùng subpartitioning, hãy so sánh với một partition key đơn cùng các index phù hợp.

## 9. Partition pruning hoạt động như thế nào?

Partition pruning là khả năng loại bỏ các partition không thể chứa hàng thỏa điều kiện. Optimizer dùng partition key và ranh giới để suy luận phạm vi dữ liệu cần truy cập.

Ví dụ với Range theo occurred_at:

~~~sql
SELECT event_id, event_type
FROM events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-10 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-12 00:00:00+00';
~~~

Nếu bảng có partition theo tháng, truy vấn chỉ cần dữ liệu trong tháng 11 và có thể bỏ qua các partition tháng khác. Nếu khoảng truy vấn cắt qua ranh giới tháng, hai hoặc nhiều partition có thể cần được truy cập.

### 9.1. Predicate phải tương thích với partition key

Truy vấn:

~~~sql
WHERE occurred_at >= :from_time
  AND occurred_at < :to_time
~~~

thể hiện trực tiếp phạm vi trên partition key. Đây thường là dạng dễ pruning.

Ngược lại:

~~~sql
WHERE DATE(occurred_at) = DATE '2026-11-19'
~~~

áp dụng hàm lên partition key. Một số optimizer có thể biến đổi biểu thức, nhưng không nên mặc định pruning luôn xảy ra. Viết điều kiện khoảng nửa mở trên cột gốc thường rõ ràng hơn:

~~~sql
WHERE occurred_at >= TIMESTAMP '2026-11-19 00:00:00'
  AND occurred_at <  TIMESTAMP '2026-11-20 00:00:00'
~~~

Hãy bảo đảm hai biên được tính theo đúng múi giờ nghiệp vụ nếu cột là timestamp có múi giờ.

### 9.2. Điều kiện trên cột không phải partition key

Nếu bảng Range partition theo occurred_at nhưng truy vấn chỉ có:

~~~sql
WHERE tenant_id = 77
~~~

optimizer không thể loại partition dựa trên tenant_id nếu không có quan hệ suy luận phù hợp. Nó có thể phải truy cập mọi partition rồi dùng index cục bộ hoặc scan từng partition để tìm tenant.

Điều này không có nghĩa truy vấn chắc chắn chậm: index trên tenant_id ở mỗi partition có thể giúp tìm dữ liệu. Nhưng số partition phải mở và lập kế hoạch vẫn là yếu tố cần đo.

### 9.3. Static và runtime pruning

Một số hệ quản trị có thể xác định partition cần truy cập khi lập kế hoạch (static pruning). Một số trường hợp khác chỉ xác định được giá trị tham số lúc thực thi, vì vậy pruning xảy ra ở runtime hoặc execution time. Khả năng này phụ thuộc DBMS, phiên bản, prepared statement, join và cách tham số được truyền.

Khi dùng prepared statement, hãy kiểm tra kế hoạch thực tế với tham số đại diện. Không giả định mọi kế hoạch generic đều pruning giống một kế hoạch được tối ưu riêng cho từng tham số.

### 9.4. Xác minh pruning

Trong execution plan, tìm:

- Số partition được liệt kê hoặc thực sự được truy cập.
- Partition bị loại (removed/pruned partitions) nếu công cụ hiển thị.
- Scan operator xuất hiện ở những partition nào.
- Số hàng và buffers ở từng partition.
- Thời gian lập kế hoạch khi có rất nhiều partition.

Tên trường khác nhau theo hệ quản trị. Đừng chỉ nhìn tên bảng cha trong SQL; hãy đọc kế hoạch để xác nhận partition pruning thực sự diễn ra.

## 10. Chỉ mục trên bảng phân vùng

Partitioning và indexing giải quyết hai vấn đề khác nhau:

- Partitioning chia phạm vi dữ liệu và có thể loại bỏ các partition không liên quan.
- Index giúp tìm hàng trong phạm vi dữ liệu mà truy vấn cần truy cập.

Một bảng phân vùng thường vẫn cần chỉ mục bên trong từng partition. Ví dụ, bảng events partition theo tháng nhưng truy vấn trong mỗi tháng lọc theo tenant_id và event_type. Chỉ mục (tenant_id, event_type, occurred_at) hoặc thứ tự phù hợp khác có thể giúp tìm hàng trong partition đã được pruning.

### 10.1. Local index

Local index là chỉ mục gắn với một partition. Mỗi partition có cấu trúc index riêng. Ưu điểm:

- Dễ bảo trì hoặc rebuild theo từng partition.
- Khi drop/detach partition, index tương ứng cũng có thể được xử lý cùng partition.
- Kích thước mỗi index nhỏ hơn so với một index toàn bảng trong nhiều trường hợp.

Nhược điểm:

- Truy vấn nhiều partition có thể phải truy cập nhiều index.
- Mỗi partition cần thống kê và cấu trúc index riêng.
- Nếu truy vấn không pruning, chi phí mở và tìm trong nhiều index có thể tăng.

### 10.2. Global index

Một số hệ quản trị hỗ trợ global index bao phủ nhiều partition. Global index có thể hữu ích khi truy vấn tìm theo một khóa không bao gồm partition key. Tuy nhiên, global index có thể làm thao tác drop/truncate/switch partition phức tạp hơn vì cần giữ tính nhất quán giữa index và các partition.

Không phải DBMS nào cũng hỗ trợ global index cho mọi kiểu partition. Ví dụ, trong PostgreSQL, unique index trên partitioned table phải bao gồm tất cả partition key columns; không có một global index chung theo cách Oracle hoặc một số hệ khác hỗ trợ. Hãy kiểm tra tài liệu phiên bản cụ thể.

### 10.3. Chỉ mục duy nhất và khóa chính

Partitioning có thể ảnh hưởng đến cách thực thi PRIMARY KEY và UNIQUE:

- Nếu tính duy nhất chỉ được kiểm tra trong từng partition, cùng một giá trị có thể xuất hiện ở nhiều partition.
- Để bảo đảm duy nhất toàn bảng, DBMS có thể yêu cầu unique key bao gồm partition key hoặc cần global index.
- Khóa ngoại tham chiếu partitioned table có thể có giới hạn riêng theo sản phẩm.

Trong PostgreSQL, ràng buộc PRIMARY KEY/UNIQUE trên partitioned table phải bao gồm tất cả cột partition key để hệ thống có thể bảo đảm tính duy nhất qua các partition mà không cần global index. Ví dụ, nếu partition theo occurred_at thì PRIMARY KEY (event_id) không đáp ứng yêu cầu này; PRIMARY KEY (occurred_at, event_id) có thể phù hợp nhưng không bảo đảm event_id duy nhất toàn bảng nếu cùng ID xuất hiện ở thời điểm khác nhau.

Nếu nghiệp vụ cần event_id duy nhất toàn cục, có thể dùng một bảng registry riêng hoặc cơ chế định danh khác, tùy kiến trúc và DBMS. Không được bỏ ràng buộc duy nhất chỉ để vượt qua giới hạn partition.

## 11. Partition-wise join và truy vấn nhiều bảng

Khi hai bảng được phân vùng tương thích trên khóa join, một số hệ quản trị có thể thực hiện partition-wise join: nối từng cặp partition tương ứng thay vì kết hợp toàn bộ dữ liệu qua một tập trung gian lớn.

Điều kiện thường cần:

- Hai bảng có partitioning tương thích về key và ranh giới.
- Điều kiện join thể hiện quan hệ trên partition key.
- Optimizer hỗ trợ partition-wise join và cấu hình cho phép.
- Các điều kiện khác không làm mất khả năng suy luận.

Ví dụ, bảng orders và order_items cùng Range partition theo order_date hoặc một khóa thời gian phù hợp. Truy vấn lọc một tháng và join theo order_id có thể chỉ xử lý partition tương ứng nếu thiết kế và DBMS cho phép.

Nếu hai bảng partition theo hai key khác nhau, join có thể phải mở nhiều partition và trao đổi dữ liệu nhiều hơn. Partitioning không tự động làm join nhanh; hãy xem kế hoạch, số hàng từng partition, hash/sort spill và lượng dữ liệu trung gian.

## 12. Quản lý vòng đời dữ liệu với partition

Một lợi ích quan trọng của Range partition là có thể quản lý dữ liệu theo thời gian. Thay vì xóa từng hàng:

~~~sql
DELETE FROM events
WHERE occurred_at < TIMESTAMPTZ '2025-01-01 00:00:00+00';
~~~

có thể detach hoặc drop các partition trước năm 2025 nếu chính sách retention cho phép. Thao tác partition thường giảm khối lượng xử lý so với DELETE hàng triệu hàng, nhưng cách khóa, log, replication và yêu cầu bảo toàn dữ liệu khác nhau theo DBMS.

Một quy trình retention:

1. Xác định thời gian lưu trữ và partition hết hạn.
2. Kiểm tra partition có chứa dữ liệu cần giữ, dữ liệu đến muộn hoặc dữ liệu pháp lý không.
3. Detach hoặc archive partition theo cơ chế của DBMS.
4. Xác minh bản archive có thể đọc và phục hồi.
5. Drop partition sau khi hoàn tất điều kiện lưu trữ.
6. Theo dõi dung lượng, metadata và replication.

Không drop partition chỉ dựa trên tên hoặc ngày tạo. Hãy kiểm tra ranh giới thật, timezone và chính sách retention.

### 12.1. Tạo partition tương lai

Với dữ liệu theo thời gian, cần tạo partition trước khi đến kỳ mới. Một job vận hành có thể tạo trước một hoặc vài tháng. Cần cảnh báo nếu partition tương lai chưa được tạo, nếu INSERT bắt đầu rơi vào default partition hoặc bị từ chối.

### 12.2. Archive và detach

Detach partition có thể cho phép chuyển dữ liệu thành bảng độc lập, nén, di chuyển sang storage khác hoặc backup riêng. Các thao tác online/concurrent và yêu cầu lock khác nhau theo DBMS. Cần đọc tài liệu phiên bản và đo thời gian khóa trên bảng cha.

## 13. Phân phối dữ liệu và xử lý skew

Partitioning không bảo đảm mọi partition có kích thước hoặc tải bằng nhau.

### Range skew

Nếu dữ liệu mới luôn tập trung vào khoảng hiện tại, partition tháng mới có thể lớn hơn các partition lịch sử. Đây có thể là điều bình thường với time-series. Nhưng nếu một khoảng có volume đột biến, cần theo dõi dung lượng và tải ghi.

### List skew

Một region hoặc tenant có thể chiếm phần lớn dữ liệu. List partition theo region khi đó tạo một partition rất lớn và các partition khác nhỏ. Hãy kiểm tra số hàng, dung lượng và throughput theo nhóm.

### Hash skew

Hash giúp phân phối nhiều giá trị khóa, nhưng không chia một khóa nóng thành nhiều partition. Nếu một tenant có 40% dữ liệu, toàn bộ tenant đó vẫn ánh xạ đến một hash partition. Cần xem top key, MCV, NDV và số hàng theo partition.

### Không chỉ đo số hàng

Hai partition có cùng số hàng nhưng kích thước khác nhau nếu payload có độ rộng khác. Chi phí xử lý cũng có thể khác nếu một nhóm có nhiều index lookup, JSON lớn hoặc truy vấn cập nhật thường xuyên. Theo dõi:

- Số hàng và dung lượng mỗi partition.
- Số trang và kích thước index.
- Tỷ lệ đọc/ghi và throughput.
- CPU, I/O, cache hit và wait events.
- Số partition được truy cập cho từng truy vấn.
- Độ trễ p95/p99 theo tenant, vùng hoặc khoảng thời gian.

## 14. Ví dụ chọn chiến lược theo workload

Giả sử hệ thống lưu giao dịch thanh toán:

- Báo cáo thường lấy giao dịch theo khoảng ngày.
- Dịch vụ hỗ trợ tra cứu theo transaction_id.
- Một số báo cáo lọc theo merchant_id và khoảng ngày.
- Dữ liệu cũ hơn 7 năm được archive.
- Một vài merchant có volume cao hơn nhiều merchant khác.

### Phương án Range theo thời gian

Partition theo created_at theo tháng hoặc quý:

- Báo cáo theo ngày/tháng có thể pruning.
- Retention 7 năm có thể drop/archive partition cũ.
- Tra cứu transaction_id đơn lẻ có thể phải mở nhiều partition nếu không có điều kiện thời gian và không có global index.

### Phương án Hash theo transaction_id

Hash theo transaction_id có thể phân phối hàng qua nhiều partition:

- Tra cứu bằng transaction_id có thể pruning nếu DBMS hỗ trợ hash pruning.
- Báo cáo theo thời gian có thể phải truy cập nhiều partition.
- Archive theo thời gian khó hơn vì dữ liệu của nhiều năm nằm rải rác ở các hash partition.

### Phương án Range theo thời gian, index theo merchant

Partition theo created_at, tạo local index phù hợp với merchant_id và created_at:

~~~sql
CREATE INDEX payments_merchant_created_idx
ON payments (merchant_id, created_at);
~~~

Truy vấn theo merchant và thời gian có thể pruning partition theo thời gian rồi tìm theo merchant trong từng partition. Tra cứu transaction_id không có created_at vẫn có thể phải tìm trên nhiều partition; cần đánh giá tần suất và độ trễ của use case này.

### Phương án subpartition

Range theo tháng rồi Hash theo merchant_id có thể chia mỗi tháng thành các phần nhỏ hơn. Nhưng merchant lớn vẫn nằm trong một hash remainder ở từng tháng và số partition vật lý tăng. Nếu hot merchant là nút thắt, có thể cần chiến lược riêng cho merchant đó hoặc một khóa phân phối bổ sung; không nên thêm tầng partition chỉ vì muốn có nhiều partition hơn.

Lựa chọn cuối cùng phụ thuộc tỷ trọng truy vấn, retention, phân phối merchant và khả năng của DBMS. Hãy benchmark từng phương án với workload đại diện, không chỉ so sánh thời gian một truy vấn báo cáo.

## 15. Những lỗi thiết kế thường gặp

- **Partition theo cột không xuất hiện trong truy vấn.** Hầu hết truy vấn phải mở tất cả partition và không nhận được pruning.
- **Tạo quá nhiều partition nhỏ.** Metadata, planning và bảo trì tăng, trong khi mỗi partition không đủ dữ liệu để đem lại lợi ích.
- **Tạo quá ít partition lớn.** Bảo trì và retention vẫn tốn kém, truy vấn theo khoảng có thể đọc quá nhiều dữ liệu.
- **Hash theo khóa có hot key.** Một giá trị nóng vẫn tập trung vào một partition.
- **List theo trạng thái thay đổi thường xuyên.** Hàng phải di chuyển partition khi trạng thái thay đổi.
- **Không tạo partition tương lai.** INSERT thất bại hoặc dồn vào default partition.
- **Dùng default partition như vùng lưu trữ lâu dài.** Dữ liệu ngoài dự kiến bị che giấu và partition mặc định phình lớn.
- **Không xem giới hạn unique key.** Có thể vô tình mất bảo đảm duy nhất toàn bảng.
- **Cho rằng mọi index là global.** Nhiều DBMS chỉ có local index hoặc yêu cầu partition key trong unique index.
- **Không theo dõi skew.** Một partition quá lớn hoặc quá nóng trở thành nút thắt.
- **Giả định partitioning luôn tăng tốc.** Chi phí planning và truy cập nhiều partition có thể làm truy vấn chậm hơn.
- **Xóa partition mà không kiểm tra retention.** Có thể mất dữ liệu đến muộn hoặc dữ liệu cần giữ theo nghiệp vụ.

## 16. Quy trình thiết kế và kiểm chứng partitioning

1. **Thu thập workload.** Xác định truy vấn thường gặp, filter, join, sort, tần suất, p95/p99 và tỷ lệ đọc/ghi.
2. **Xác định mục tiêu.** Partitioning nhằm pruning truy vấn, retention, bảo trì, phân phối tải hay cô lập dữ liệu?
3. **Chọn partition key.** Ưu tiên cột xuất hiện trong predicate quan trọng, ổn định và có phân phối phù hợp.
4. **Chọn chiến lược.** Range cho khoảng, List cho nhóm rời rạc, Hash cho phân phối khóa; cân nhắc subpartition chỉ khi có hai nhu cầu rõ ràng.
5. **Ước lượng kích thước.** Tính số hàng/dung lượng mỗi partition, số partition hiện tại và số partition trong toàn bộ retention window.
6. **Thiết kế index và constraint.** Xác định local/global index, unique key, primary key, foreign key và giới hạn DBMS.
7. **Thiết kế vận hành.** Lập lịch tạo partition mới, xử lý late-arriving data, default partition, archive, detach và drop.
8. **Kiểm tra pruning.** Chạy EXPLAIN với các dạng predicate và tham số đại diện; xác nhận số partition thực sự được truy cập.
9. **Đo phân phối và skew.** So sánh row count, size, index size, CPU, I/O và throughput theo partition.
10. **Benchmark toàn workload.** Đo p50/p95/p99, planning time, execution time, I/O, cache và tác động lên ghi.
11. **Kiểm tra correctness.** Xác minh ranh giới, giá trị NULL, dữ liệu ngoài khoảng, unique/FK và truy vấn xuyên partition.
12. **Triển khai có giám sát.** Theo dõi pruning, default partition, partition quá lớn, job tạo partition và lỗi insert.

## 17. Khác biệt giữa các hệ quản trị

Khái niệm Range, List và Hash phổ biến, nhưng khả năng triển khai không giống nhau:

| Hệ quản trị | Hỗ trợ và điểm cần kiểm tra |
|---|---|
| PostgreSQL | Declarative partitioning hỗ trợ RANGE, LIST, HASH; partitioned index và constraint có quy tắc riêng; unique constraint trên partitioned table cần bao gồm partition key; có thể dùng partition pruning và partition-wise join khi điều kiện phù hợp |
| MySQL | Partitioning có các phương thức RANGE, LIST, HASH và KEY; có giới hạn về foreign key, unique key và engine; cần kiểm tra quy tắc mọi unique key liên quan partition expression và khả năng pruning theo phiên bản |
| SQL Server | Partition function/scheme chia dữ liệu theo RANGE và boundary; partition switching và aligned index hữu ích cho quản lý vòng đời; không nên giả định có List/Hash partitioning tương đương cú pháp PostgreSQL |
| Oracle | Hỗ trợ nhiều dạng partitioning như range, list, hash và composite; có local/global index cùng các tùy chọn bảo trì; cần xem quyền sử dụng tính năng và phiên bản |

Không sao chép DDL giữa các hệ quản trị mà không kiểm tra. Đặc biệt, cách bảo đảm uniqueness, foreign key, global index, partition switching và runtime pruning có thể khác đáng kể.

## 18. Checklist trước khi đưa partitioning vào production

- [ ] Partition key xuất hiện trong các truy vấn quan trọng và ổn định theo thời gian.
- [ ] Chiến lược Range/List/Hash phù hợp với mẫu truy cập và retention.
- [ ] Kích thước và số lượng partition nằm trong giới hạn vận hành đã kiểm chứng.
- [ ] Đã xác định cách xử lý dữ liệu đến muộn và giá trị ngoài ranh giới.
- [ ] Có lịch tạo partition mới và cảnh báo khi thiếu partition.
- [ ] Default partition được theo dõi và có quy trình làm sạch.
- [ ] Index được thiết kế cho truy vấn trong từng partition.
- [ ] PRIMARY KEY, UNIQUE và FOREIGN KEY vẫn bảo đảm đúng yêu cầu toàn cục.
- [ ] Đã kiểm tra partition pruning bằng execution plan.
- [ ] Đã đo số partition được truy cập khi truy vấn theo và không theo partition key.
- [ ] Đã kiểm tra skew về số hàng, dung lượng, CPU và I/O.
- [ ] Đã đánh giá partition-wise join nếu có nhiều bảng liên quan.
- [ ] Có quy trình archive, detach, drop và phục hồi dữ liệu.
- [ ] Đã benchmark workload đọc/ghi trước và sau partitioning.
- [ ] Đã kiểm tra ứng dụng, ORM, migration và công cụ vận hành hiểu cấu trúc bảng phân vùng.

Range, List và Hash partitioning là ba cách tổ chức dữ liệu phục vụ các mẫu truy cập khác nhau. Range phù hợp với truy vấn theo khoảng và vòng đời thời gian; List phù hợp với nhóm giá trị rời rạc, ổn định; Hash phù hợp với việc phân phối nhiều khóa và truy vấn bằng trên partition key. Hiệu quả phụ thuộc vào khả năng pruning, chỉ mục bên trong partition, phân phối dữ liệu và cách hệ quản trị triển khai. Hãy bắt đầu từ workload, thiết kế ranh giới và ràng buộc rõ ràng, sau đó xác minh bằng execution plan, số partition được truy cập, độ trễ và chi phí vận hành trước khi mở rộng sang production.
