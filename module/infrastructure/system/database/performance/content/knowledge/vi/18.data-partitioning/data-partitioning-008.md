# Kiểm chứng lợi ích phân vùng và phân biệt với chia dữ liệu sang nhiều máy

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích phân vùng bảng (partitioning) giải quyết vấn đề gì và những trường hợp phân vùng không cải thiện truy vấn.
- Chọn khóa và chiến lược phân vùng theo phạm vi truy vấn, phân bố dữ liệu, vòng đời lưu trữ và mẫu ghi.
- Kiểm tra partition pruning, số phân vùng được truy cập, chỉ mục, thống kê và chi phí lập kế hoạch qua execution plan.
- Thiết kế phép đo trước/sau để xác nhận tác động đến độ trễ, throughput, I/O, CPU, ghi dữ liệu và bảo trì.
- Phân biệt phân vùng bảng trong một hệ quản trị với sharding dữ liệu qua nhiều máy chủ, kể cả chi phí định tuyến và giao dịch phân tán.

## 1. Phân vùng dữ liệu giải quyết vấn đề gì?

Phân vùng bảng (table partitioning) chia một bảng logic lớn thành nhiều phần vật lý hoặc phần lưu trữ được quản lý riêng theo một quy tắc. Ứng dụng vẫn truy vấn bảng cha như một tập dữ liệu thống nhất; hệ quản trị xác định những phân vùng có thể chứa hàng phù hợp và truy cập các phần cần thiết.

Phân vùng thường được cân nhắc khi bảng lớn, dữ liệu có quy luật phân bố rõ ràng hoặc có vòng đời lưu trữ theo thời gian. Ví dụ, bảng sự kiện có thể chia theo tháng; dữ liệu đơn hàng có thể chia theo năm hoặc theo tenant; bảng giao dịch có thể dùng hash partition để phân bố hàng tương đối đều giữa các phân vùng.

Trong module DATABASE_PERFORMANCE, phân vùng là một kỹ thuật tổ chức dữ liệu để hỗ trợ đường truy cập, quản lý dung lượng và bảo trì. Nó không tự động làm mọi câu SQL nhanh hơn. Lợi ích chỉ xuất hiện khi cách phân vùng phù hợp với workload và hệ quản trị có thể bỏ qua những phân vùng không liên quan, giảm lượng dữ liệu phải đọc hoặc đơn giản hóa thao tác vận hành.

Phân vùng cũng không thay thế chỉ mục. Một truy vấn có thể chỉ truy cập một phân vùng nhưng vẫn phải quét toàn bộ phân vùng đó nếu thiếu chỉ mục phù hợp. Ngược lại, một chỉ mục tốt trên bảng chưa phân vùng có thể đã đủ nhanh cho quy mô và mẫu truy vấn hiện tại.

## 2. Phân biệt partitioning và sharding

Trong nhiều tài liệu, từ partition có thể được dùng cho cả phần dữ liệu logic và phần dữ liệu được phân phối trên các node. Trong bài này, ta dùng hai nghĩa thực hành:

- **Partitioning:** chia bảng hoặc tập dữ liệu thành các phân vùng do cùng một hệ quản trị hoặc cùng một cụm cơ sở dữ liệu quản lý. Các phân vùng thường vẫn nằm trong cùng miền quản trị và được truy vấn qua một bảng logic.
- **Sharding:** chia ngang dữ liệu thành các shard và phân phối chúng trên nhiều máy chủ hoặc node cơ sở dữ liệu độc lập. Ứng dụng, proxy hoặc lớp điều phối phải định tuyến truy vấn đến shard chứa dữ liệu.

Sharding thường cũng là một dạng phân chia dữ liệu theo khóa, nhưng điểm khác biệt vận hành là dữ liệu được đặt trên nhiều node. Một số hệ quản trị phân tán gọi các đơn vị phân phối đó là partition hoặc shard; hãy đọc đúng mô hình của sản phẩm.

| Tiêu chí | Partitioning trong một hệ quản trị | Sharding qua nhiều node |
| --- | --- | --- |
| Mục tiêu chính | Tổ chức bảng lớn, loại bỏ vùng dữ liệu không cần đọc, quản lý vòng đời và bảo trì | Phân phối dung lượng và tải xử lý qua nhiều máy chủ |
| Vị trí dữ liệu | Các phân vùng do cùng hệ quản trị/cụm quản lý | Các shard nằm trên những node khác nhau |
| Định tuyến | Thường do optimizer và partition map của hệ quản trị xử lý | Cần shard key và cơ chế định tuyến ở ứng dụng, proxy hoặc lớp phân tán |
| Truy vấn không có khóa phân vùng | Có thể phải quét nhiều hoặc tất cả phân vùng trong cùng hệ quản trị | Có thể phải fan-out đến nhiều shard và hợp nhất kết quả qua mạng |
| Giao dịch | Thường nằm trong một miền transaction của hệ quản trị | Giao dịch nhiều shard có thể cần coordinator hoặc cơ chế phân tán, với chi phí và giới hạn riêng |
| Mở rộng tài nguyên | Không tự tạo thêm CPU/RAM/IOPS cho máy chủ | Có thể tăng tổng tài nguyên bằng cách thêm node, tùy kiến trúc |
| Vận hành | Quản lý partition, index, statistics, retention và maintenance | Thêm cả việc cân bằng shard, định tuyến, di chuyển dữ liệu, lỗi node và tính nhất quán |

Phân vùng một bảng trên một máy chủ không có nghĩa hệ thống đã scale-out. Nếu máy chủ vẫn dùng chung CPU, RAM và thiết bị lưu trữ, tổng tài nguyên vẫn bị giới hạn bởi máy chủ hoặc cụm đó.

## 3. Các chiến lược phân vùng phổ biến

### Range partitioning

Chia dữ liệu theo các khoảng của một khóa, thường là thời gian hoặc số thứ tự. Ví dụ, mỗi tháng có một partition cho `created_at`.

Range partition phù hợp khi truy vấn thường có điều kiện khoảng như từ ngày A đến ngày B, hoặc khi dữ liệu cũ có thể được lưu trữ/xóa theo từng giai đoạn.

Điểm cần chú ý là khoảng phân vùng phải bao phủ dữ liệu đến. Nếu không có partition cho giá trị mới, thao tác ghi có thể thất bại hoặc đi vào default partition nếu hệ quản trị hỗ trợ.

### List partitioning

Chia dữ liệu theo một tập giá trị xác định, chẳng hạn khu vực, loại dữ liệu hoặc nhóm tenant. Cách này phù hợp khi số nhóm hữu hạn và workload thường lọc theo nhóm đó.

Nếu có quá nhiều tenant hoặc một tenant phát triển vượt trội, tạo một partition cho mỗi tenant có thể gây phức tạp và mất cân bằng. Cần xem số lượng phân vùng, kích thước từng nhóm và cách thêm nhóm mới.

### Hash partitioning

Dùng hàm băm trên khóa để phân phối hàng vào một số phân vùng cố định. Hash partition thường giúp phân tán các giá trị khóa tương đối đều khi khóa có phân bố phù hợp.

Hash partition có thể hữu ích cho truy vấn bằng khóa phân vùng và một số workload cần phân tán ghi. Nó thường không hỗ trợ loại bỏ phân vùng hiệu quả cho truy vấn theo khoảng giá trị như range partition.

### Composite hoặc subpartitioning

Một số hệ quản trị cho phép chia theo nhiều tầng, ví dụ range theo tháng rồi hash theo tenant trong mỗi tháng. Cách này có thể kết hợp pruning theo thời gian với phân phối tải trong từng khoảng.

Đổi lại, số lượng phân vùng vật lý tăng theo tích của số nhóm ở mỗi tầng. Chỉ dùng khi workload và vận hành thật sự cần; nhiều tầng không tự động đem lại lợi ích.

## 4. Chọn partition key theo workload

Khóa phân vùng (partition key) quyết định hàng nằm ở đâu và optimizer có thể loại bỏ phân vùng nào. Chọn khóa sai có thể làm hầu hết truy vấn phải chạm mọi partition.

Hãy đánh giá các yếu tố:

- **Predicate phổ biến:** truy vấn có thường lọc theo khóa này bằng điều kiện bằng hoặc khoảng không?
- **Độ chọn lọc:** một điều kiện thường giữ lại bao nhiêu dữ liệu và bao nhiêu partition?
- **Phân bố:** giá trị có đều hay lệch mạnh? Có một tenant, ngày hoặc nhóm tạo phần lớn dữ liệu không?
- **Mẫu ghi:** dữ liệu mới chủ yếu đi vào một partition hay được phân bố trên nhiều partition?
- **Vòng đời:** có thể archive hoặc drop partition theo thời gian/nhóm nghiệp vụ không?
- **Khóa và ràng buộc:** PRIMARY KEY, UNIQUE, FOREIGN KEY và các truy vấn join có phù hợp với khóa phân vùng không?
- **Khả năng tăng trưởng:** số partition sẽ là bao nhiêu sau vài năm và hệ quản trị xử lý số lượng đó ra sao?

Ví dụ, nếu phần lớn truy vấn báo cáo lọc theo `created_at` và dữ liệu được giữ theo tháng, range partition theo thời gian có thể phù hợp. Nếu các request trực tuyến chủ yếu tìm đơn theo `tenant_id` mà không có điều kiện thời gian, partition theo tháng có thể không giúp những truy vấn đó bỏ qua partition.

Không chọn partition key chỉ vì cột có nhiều giá trị phân biệt. Khóa cần tương thích với cách truy vấn và cách vận hành dữ liệu. Một cột có cardinality cao nhưng không xuất hiện trong predicate phổ biến có thể không giúp pruning.

## 5. Partition pruning là cơ chế quan trọng nhất cần kiểm chứng

Partition pruning là việc hệ quản trị loại bỏ các partition không thể chứa hàng thỏa điều kiện truy vấn. Khi pruning hoạt động, truy vấn chỉ truy cập một phần dữ liệu thay vì tất cả partition.

Giả sử bảng được range partition theo `created_at`. Truy vấn:

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= TIMESTAMP '2026-03-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-04-01 00:00:00';
```

có thể chỉ cần truy cập partition tháng 3 năm 2026. Điều kiện dùng khoảng nửa mở `[start, end)` giúp tránh nhập nhằng tại ranh giới giữa hai tháng và phù hợp với partition boundary thường dùng.

Ngược lại, truy vấn sau không nêu điều kiện trên khóa phân vùng:

```sql
SELECT order_id, customer_id
FROM orders
WHERE customer_id = 4201;
```

Optimizer có thể phải xét nhiều hoặc toàn bộ partition để tìm đơn của khách hàng, dù mỗi partition có chỉ mục trên `customer_id`. Chỉ mục có thể giảm công việc bên trong mỗi partition, nhưng không loại bỏ được nhu cầu xét từng partition nếu không có thông tin khác giúp pruning.

### Predicate phải tương thích với partition key

Những điều kiện sau có thể làm pruning khó hơn hoặc phụ thuộc khả năng biến đổi của optimizer:

- Bọc partition key trong hàm hoặc phép ép kiểu không tương thích.
- So sánh hai kiểu dữ liệu khác nhau khiến hệ quản trị phải chuyển đổi.
- Dùng biểu thức phức tạp mà optimizer không thể suy ra khoảng giá trị.
- Truy vấn qua view hoặc hàm có thể che khuất điều kiện, tùy cách inline và tối ưu.

Ưu tiên điều kiện trực tiếp trên partition key với kiểu dữ liệu tương thích. Ví dụ, nếu `created_at` là timestamp, truyền tham số timestamp thay vì chuyển đổi cột thành chuỗi trong WHERE.

```sql
-- Điều kiện trực tiếp trên partition key
WHERE created_at >= ?
  AND created_at < ?;

-- Biểu thức trên cột có thể cản trở pruning hoặc index access
WHERE DATE(created_at) = ?;
```

Không phải mọi hàm đều chắc chắn ngăn pruning; một số hệ quản trị có thể suy luận hoặc hỗ trợ biểu thức cụ thể. Cần xác nhận bằng plan trên phiên bản thực tế.

### Static và runtime pruning

Một số hệ quản trị có thể xác định partition cần đọc ngay khi lập kế hoạch (static pruning). Một số trường hợp khác chỉ biết giá trị tham số khi thực thi nên loại partition tại runtime.

Với prepared statement, parameterized query hoặc nested loop, cần kiểm tra pruning có diễn ra tại thời điểm thực thi hay không. Một plan tổng quát có thể hiển thị nhiều partition nhưng chỉ truy cập một số partition khi chạy; hãy xem actual plan và số lần truy cập thực tế.

## 6. Ví dụ range partition theo tháng trong PostgreSQL

Ví dụ sau minh họa bảng đơn hàng chia theo tháng. Để đơn giản, khóa chính gồm cả partition key và ID vì PostgreSQL yêu cầu unique constraint trên bảng partitioned bao gồm tất cả cột partition key.

```sql
CREATE TABLE orders (
    created_at TIMESTAMPTZ NOT NULL,
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(16) NOT NULL,
    total_amount NUMERIC(19, 2) NOT NULL,
    PRIMARY KEY (created_at, order_id)
) PARTITION BY RANGE (created_at);

CREATE TABLE orders_2026_03
    PARTITION OF orders
    FOR VALUES FROM ('2026-03-01 00:00:00+00')
             TO   ('2026-04-01 00:00:00+00');

CREATE TABLE orders_2026_04
    PARTITION OF orders
    FOR VALUES FROM ('2026-04-01 00:00:00+00')
             TO   ('2026-05-01 00:00:00+00');
```

Truy vấn theo tháng:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-04-01 00:00:00+00'
  AND customer_id = 4201;
```

Trong plan, kiểm tra chỉ partition tháng 3 được truy cập hoặc các partition khác bị loại bỏ. Nếu cần, tạo index phù hợp trên bảng cha để có index tương ứng ở các partition:

```sql
CREATE INDEX ix_orders_customer_created
    ON orders (customer_id, created_at DESC);
```

Chỉ mục giúp tìm đơn theo khách hàng trong partition được chọn; partition pruning giúp bỏ các tháng không liên quan. Hai cơ chế bổ trợ nhau.

Ví dụ trên giả định các partition đã được tạo cho mọi khoảng thời gian có dữ liệu. Cần lập lịch tạo partition tương lai và quyết định cách xử lý hàng đến muộn hoặc ngoài khoảng. Một default partition có thể giữ dữ liệu không khớp partition hiện có trong PostgreSQL, nhưng cần theo dõi và xử lý vì nó có thể tích tụ dữ liệu ngoài dự kiến.

## 7. Phân vùng không thay thế chỉ mục

Partitioning và indexing giải quyết hai câu hỏi khác nhau:

- Partitioning xác định phần dữ liệu nào cần xét.
- Indexing xác định cách tìm hàng bên trong phần dữ liệu đó.

Ví dụ, bảng có 60 partition theo tháng. Truy vấn tìm một đơn trong một tháng có thể pruning còn một partition, nhưng nếu partition đó chứa 50 triệu hàng và không có index phù hợp, hệ quản trị vẫn phải scan phần lớn 50 triệu hàng.

Ngược lại, một index trên mỗi partition có thể tìm khóa nhanh, nhưng truy vấn không có predicate partition key có thể phải dò index trên cả 60 partition. Chi phí mở/điều phối nhiều index scan có thể lớn hơn truy cập một index duy nhất trên bảng chưa phân vùng.

Khi thiết kế, hãy xác định cả:

- Khóa partition và predicate để pruning.
- Index cục bộ trong mỗi partition để tìm hàng.
- Composite index theo WHERE, JOIN và ORDER BY.
- Cột cần bao phủ và chi phí kích thước index.
- Tác động đến INSERT, UPDATE, DELETE và bảo trì.

Khái niệm local/global index khác nhau theo hệ quản trị. Một số sản phẩm tạo index tương ứng trên từng partition; một số hỗ trợ các dạng global index hoặc index không aligned. Hãy kiểm tra khả năng của nền tảng thay vì giả định mọi index đều có cùng phạm vi.

## 8. Lợi ích quản trị vòng đời và bảo trì

Một lợi ích lớn của phân vùng là quản lý dữ liệu theo nhóm có vòng đời rõ ràng.

Ví dụ, hệ thống lưu log trong 24 tháng và mỗi tháng là một partition. Khi dữ liệu tháng cũ hết hạn, có thể detach, archive hoặc drop partition thay vì DELETE từng triệu hàng.

Thao tác bỏ một partition thường tránh được việc tạo lượng lớn row-level delete và log như xóa từng hàng, nhưng vẫn có chi phí metadata, lock, cập nhật catalog, index và replication tùy hệ quản trị. Cần tuân thủ chính sách backup, foreign key, audit và lưu trữ trước khi bỏ dữ liệu.

Phân vùng cũng có thể hỗ trợ:

- Rebuild hoặc bảo trì index theo từng partition.
- Nạp dữ liệu theo lô vào partition riêng rồi attach hoặc chuyển đổi theo cơ chế hệ quản trị.
- Archive partition cũ sang storage chậm hơn.
- Theo dõi tăng trưởng và dung lượng theo thời gian hoặc nhóm nghiệp vụ.
- Chạy tác vụ bảo trì trên một phần dữ liệu thay vì toàn bảng.

Những lợi ích này thuộc về vận hành và vòng đời dữ liệu. Chúng vẫn có giá trị ngay cả khi một truy vấn không nhanh hơn đáng kể.

## 9. Chi phí và giới hạn của partitioning

Phân vùng tạo thêm cấu trúc và công việc quản trị:

- Nhiều partition làm tăng metadata, số object, chi phí planning và độ phức tạp giám sát.
- Mỗi partition có thể cần index, statistics, vacuum/analyze hoặc bảo trì riêng theo hệ quản trị.
- Truy vấn không lọc partition key có thể phải xét nhiều partition.
- Partition quá nhỏ tạo nhiều object; partition quá lớn không đem lại pruning đủ chi tiết.
- Partition key lệch có thể tạo một partition nóng hoặc lớn vượt trội.
- Thay đổi partition key hoặc tái phân vùng có thể cần di chuyển dữ liệu và xây lại index.
- Ràng buộc UNIQUE, FOREIGN KEY và khả năng index toàn cục có giới hạn riêng theo sản phẩm.

Partition pruning giảm số vùng dữ liệu cần truy cập nhưng không làm mất chi phí tổng hợp kết quả từ nhiều partition. Một truy vấn tổng hợp toàn lịch sử có thể vẫn đọc mọi partition và còn thêm overhead điều phối.

Đừng tạo một partition cho mỗi ngày hoặc mỗi khách hàng nếu số lượng sẽ tăng lên hàng chục nghìn hoặc hàng triệu mà chưa kiểm tra giới hạn và chi phí của hệ quản trị. Chọn kích thước partition dựa trên thời gian lưu trữ, tốc độ tăng dữ liệu, kích thước index và cửa sổ truy vấn.

## 10. Dữ liệu lệch và partition nóng

Phân vùng theo hash thường phân phối tương đối đều nếu hàm băm và khóa phù hợp, nhưng không bảo đảm workload đồng đều. Một số tenant hoặc tài khoản có thể tạo nhiều truy vấn hơn hẳn những tenant khác.

Range partition theo thời gian cũng có thể tạo điểm nóng ghi: mọi dữ liệu mới đều đi vào partition hiện tại. Nếu hệ thống ghi đồng thời rất cao, partition mới nhất có thể chịu nhiều áp lực hơn các partition cũ.

Cần đo:

- Số hàng và dung lượng từng partition.
- Tốc độ INSERT/UPDATE theo partition.
- Số request, CPU, I/O và lock wait theo partition hoặc khóa.
- Tỷ lệ truy vấn truy cập một partition so với truy cập nhiều partition.
- Sự chênh lệch giữa tenant lớn nhất và tenant trung bình.

Nếu partition lệch, cần xem lại partition key, số bucket, subpartitioning hoặc cách phân phối. Đừng thêm partition mới chỉ vì một partition lớn nếu truy vấn và tài nguyên không bị ảnh hưởng.

## 11. Partition-wise join và aggregation

Một số hệ quản trị có thể xử lý JOIN hoặc GROUP BY theo từng cặp partition tương ứng thay vì gom toàn bộ dữ liệu từ hai bảng. Đây thường được gọi là partition-wise join hoặc partition-wise aggregation.

Ví dụ, bảng `orders` và `order_items` cùng được phân vùng theo `created_at` với ranh giới tương thích. Khi truy vấn nối theo khoảng thời gian, hệ quản trị có thể xử lý partition tháng 3 của orders với partition tháng 3 của order_items, rồi hợp nhất kết quả.

Lợi ích có thể gồm:

- Giảm kích thước dữ liệu trung gian tại mỗi bước.
- Tăng khả năng xử lý song song theo partition.
- Giảm trao đổi dữ liệu giữa các phần trong một số kiến trúc.
- Tận dụng pruning trên cả hai bảng.

Điều kiện để có lợi phụ thuộc hệ quản trị: partition key, kiểu phân vùng, ranh giới, điều kiện JOIN và cấu hình optimizer có thể phải tương thích. Nếu hai bảng phân vùng khác cách hoặc truy vấn không có điều kiện phù hợp, hệ thống vẫn có thể cần redistribute, repartition, sort hoặc hash dữ liệu.

Không nên phân vùng hai bảng giống nhau chỉ để hy vọng optimizer tự chọn partition-wise join. Hãy xem execution plan và đo lượng dữ liệu trung gian, số worker, CPU, memory và I/O.

## 12. Phân biệt partition pruning với sharding routing

Partition pruning và shard routing đều loại bỏ nơi không cần truy cập, nhưng chúng diễn ra ở các lớp khác nhau.

- Với partitioning, optimizer hoặc partition manager của hệ quản trị dùng điều kiện trên partition key để xác định các partition cần đọc.
- Với sharding, lớp định tuyến dùng shard key để gửi truy vấn đến một hoặc nhiều node. Nếu truy vấn không có shard key, hệ thống có thể phải broadcast/fan-out đến nhiều shard.

Ví dụ, một hệ thống sharding đơn hàng theo `tenant_id` có thể định tuyến truy vấn `WHERE tenant_id = 42` đến một shard. Truy vấn báo cáo theo ngày nhưng không có tenant có thể phải gửi đến mọi shard, đọc dữ liệu trên từng node rồi hợp nhất kết quả.

Trong một shard, bảng orders vẫn có thể được partition theo `created_at`. Khi đó có hai tầng lựa chọn:

1. Shard routing chọn node dựa trên tenant.
2. Partition pruning trong node chọn khoảng thời gian cần đọc.

Thiết kế hai tầng có thể hiệu quả nhưng tăng độ phức tạp: cần quản lý shard key, partition key, phân bố tenant, cân bằng dữ liệu và tính tương thích giữa các node.

## 13. Khi nào cần sharding thay vì chỉ partitioning?

Partitioning có thể giúp quản lý bảng lớn và giảm dữ liệu đọc, nhưng nếu CPU, RAM, IOPS hoặc dung lượng của một máy chủ đã gần giới hạn, chia bảng thành partition trên cùng máy chủ không tự tạo thêm tài nguyên.

Sharding đáng xem xét khi:

- Dung lượng dữ liệu vượt khả năng lưu trữ hoặc backup/restore hợp lý của một node.
- Throughput ghi hoặc đọc vượt năng lực CPU, RAM, I/O của một máy chủ sau khi đã tối ưu truy vấn và schema.
- Cần phân phối tenant hoặc miền dữ liệu sang các cụm độc lập.
- Cần cô lập tải hoặc lỗi giữa các nhóm khách hàng.
- Có khả năng xác định shard key ổn định và định tuyến phần lớn truy vấn theo khóa đó.

Sharding mang theo chi phí mới:

- Truy vấn không có shard key phải fan-out và hợp nhất kết quả.
- JOIN giữa các shard có thể cần truyền dữ liệu qua mạng hoặc xử lý ở ứng dụng.
- Giao dịch nhiều shard cần coordinator, saga hoặc cơ chế nhất quán phù hợp.
- Unique constraint toàn cục và foreign key xuyên shard có thể không được hỗ trợ trực tiếp.
- Thêm shard hoặc thay đổi shard key có thể cần di chuyển và cân bằng dữ liệu.
- Vận hành backup, restore, failover, schema migration và quan sát phải làm trên nhiều node.

Do đó, sharding không phải bước tiếp theo tự động sau khi bật partitioning. Trước hết cần xác định giới hạn tài nguyên nào đang chạm ngưỡng và liệu tối ưu access path, query, index, retention hoặc vertical scaling có giải quyết được hay không.

## 14. Thiết kế benchmark để kiểm chứng partitioning

Để chứng minh phân vùng có lợi, cần so sánh với đường cơ sở không phân vùng hoặc cấu trúc hiện tại trên cùng dữ liệu và workload.

### Chuẩn bị hai phương án

- **Baseline:** bảng hoặc schema hiện tại, cùng số hàng và cùng phân bố dữ liệu.
- **Partitioned:** cấu trúc phân vùng, index và thống kê được thiết kế cho workload mục tiêu.

Giữ nhất quán các yếu tố:

- Phiên bản hệ quản trị và cấu hình máy chủ.
- Tổng số hàng, kích thước dữ liệu và phân bố giá trị.
- Chỉ mục tương đương về mặt chức năng.
- Query parameters và tỷ lệ từng loại truy vấn.
- Tốc độ đến, mức đồng thời và thời lượng đo.
- Trạng thái cache, warm-up và tác vụ nền.

Nếu so sánh hai cấu trúc có index khác nhau, hãy ghi rõ khác biệt. Nếu mục tiêu là đo riêng lợi ích partition pruning, giữ index tương đương khi có thể.

### Workload cần bao phủ

Không chỉ thử một truy vấn có điều kiện partition key. Hãy bao gồm:

1. Truy vấn lọc đúng một partition.
2. Truy vấn khoảng thời gian đi qua hai hoặc nhiều partition.
3. Truy vấn không có partition key.
4. Truy vấn tổng hợp toàn bộ lịch sử.
5. Truy vấn JOIN với bảng khác.
6. INSERT vào partition hiện tại và dữ liệu đến muộn.
7. UPDATE/DELETE trên hàng thuộc partition cũ và partition hiện tại.
8. Tác vụ bảo trì như analyze, vacuum, archive hoặc drop partition nếu thuộc vận hành thực tế.

Những truy vấn không có điều kiện partition key đặc biệt quan trọng: chúng cho thấy overhead của nhiều partition và giới hạn pruning.

## 15. Chỉ số cần thu thập trước và sau

| Nhóm | Chỉ số | Câu hỏi cần trả lời |
| --- | --- | --- |
| Độ trễ | p50, p95, p99, planning time, execution time | Truy vấn thực sự nhanh hơn hay chỉ một phân vị được cải thiện? |
| Throughput | Request/s, transaction/s, rows/s | Hệ thống xử lý được nhiều công việc hơn không? |
| Pruning | Số partition được xét, loại bỏ và thực sự truy cập | Điều kiện truy vấn có loại bỏ được vùng không liên quan không? |
| I/O | Logical reads, physical reads, bytes, read/write latency | Có giảm lượng trang và byte đọc không? |
| CPU và bộ nhớ | CPU time, memory, sort/hash spill, cache hit | Chi phí xử lý và dữ liệu trung gian thay đổi thế nào? |
| Index | Kích thước, số lần scan/seek, cache footprint | Index trên mỗi partition có quá lớn hoặc bị lặp không? |
| Ghi | Insert/update throughput, WAL/log bytes, lock wait | Phân vùng có làm đường ghi chậm hoặc nóng hơn không? |
| Vận hành | Thời gian tạo, attach/detach, archive, drop, analyze | Quản lý vòng đời có đơn giản và dự đoán được không? |
| Cân bằng | Kích thước và tải từng partition | Có partition nóng hoặc lệch dữ liệu không? |

Không dùng riêng cache hit ratio để kết luận. Một tỷ lệ hit cao có thể đi kèm logical reads rất lớn; hãy xem số trang và byte thực tế.

## 16. Đọc execution plan để xác nhận pruning

Execution plan cần trả lời ba câu hỏi:

1. Hệ quản trị có nhận diện partition key trong predicate không?
2. Bao nhiêu partition bị loại bỏ và bao nhiêu partition thực sự được truy cập?
3. Bên trong các partition được chọn, access path có hiệu quả không?

### PostgreSQL

Dùng `EXPLAIN (ANALYZE, BUFFERS)` để xem kế hoạch và số liệu thực tế:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, total_amount
FROM orders
WHERE created_at >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-04-01 00:00:00+00'
  AND customer_id = 4201;
```

Kiểm tra tên partition xuất hiện trong plan, các dòng `Subplans Removed` nếu có, `loops`, actual rows và buffer hit/read. Với runtime pruning, số partition bị loại có thể được thể hiện khác nhau tùy plan và phiên bản.

### SQL Server

Trong actual execution plan, kiểm tra operator scan/seek trên partitioned table, thuộc tính partition ID hoặc partition range được truy cập, cùng actual rows và logical reads. Có thể dùng `SET STATISTICS IO, TIME ON` để bổ sung số liệu I/O và thời gian.

### MySQL

Với partitioned table, `EXPLAIN` có thể hiển thị danh sách partition được chọn trong cột `partitions`. So sánh danh sách này với partition thực sự cần cho predicate. Dùng `EXPLAIN ANALYZE` khi phiên bản hỗ trợ để quan sát số hàng và thời gian thực tế.

Cú pháp và mức chi tiết của plan khác nhau giữa các hệ quản trị. Không so sánh trực tiếp tên operator giữa các sản phẩm; hãy đối chiếu số partition, số hàng, số trang và thời gian.

## 17. Diễn giải kết quả benchmark

Ví dụ minh họa cho một truy vấn lấy đơn hàng trong một tháng:

| Chỉ số | Bảng chưa phân vùng | Bảng phân vùng theo tháng |
| --- | ---: | ---: |
| Tổng số hàng | 120 triệu | 120 triệu |
| Số vùng dữ liệu cần xét | Toàn bảng | 1 partition tháng |
| Logical reads | 180.000 | 14.000 |
| p95 latency | 1.250 ms | 210 ms |
| Planning time | 4 ms | 7 ms |

Các con số chỉ minh họa. Phân vùng có thể giảm mạnh số trang đọc nhưng planning time tăng do hệ quản trị phải quản lý nhiều partition. Nếu workload chủ yếu truy vấn một tháng, lợi ích tổng thể có thể rõ; nếu phần lớn truy vấn quét toàn bộ lịch sử, kết quả có thể khác.

Đừng chỉ nhìn phần trăm cải thiện của một query. Tính tác động theo tỷ trọng workload: một truy vấn giảm từ 1 giây xuống 200 ms nhưng chỉ chiếm 0,1% request có thể ít ảnh hưởng đến trải nghiệm tổng thể hơn một truy vấn phổ biến giảm từ 30 ms xuống 20 ms.

Đồng thời đánh giá throughput khi nhiều truy vấn chạy cùng lúc. Một phương án có latency tốt khi chạy đơn lẻ nhưng làm tăng CPU planning, lock hoặc I/O khi concurrency cao có thể không phải lựa chọn tốt.

## 18. Các trường hợp partitioning không mang lại lợi ích

- Bảng còn nhỏ và truy vấn đã đọc rất ít trang.
- Truy vấn thường không có điều kiện trên partition key nên phải xét hầu hết partition.
- Partition key không tương ứng với cách lọc dữ liệu phổ biến.
- Mỗi partition quá nhỏ, số lượng partition quá lớn và overhead quản lý vượt lợi ích.
- Một partition nóng chứa phần lớn dữ liệu hoặc nhận hầu hết thao tác ghi.
- Index trong từng partition bị lặp nhiều, làm tăng dung lượng và chi phí ghi.
- Truy vấn tổng hợp cần đọc toàn bộ lịch sử nên không thể pruning.
- Optimizer ước lượng sai do thống kê thiếu hoặc phân bố dữ liệu lệch.
- Predicate bọc partition key trong biểu thức khiến pruning không hoạt động như mong đợi.

Trong những trường hợp này, cải thiện chỉ mục, viết lại SQL, cập nhật thống kê, giảm projection hoặc điều chỉnh retention có thể hiệu quả hơn.

## 19. Quy trình quyết định partitioning hay sharding

1. **Đo giới hạn hiện tại.** Xác định nút thắt là số trang đọc, CPU, RAM, IOPS, dung lượng, lock hay throughput ghi.
2. **Phân tích workload.** Xác định các predicate phổ biến, tỷ lệ truy vấn có partition key, phạm vi truy vấn và vòng đời dữ liệu.
3. **Thử partitioning trên dữ liệu đại diện.** Chọn key, số partition và index; kiểm tra pruning cùng chi phí planning.
4. **Đánh giá lợi ích vận hành.** Đo archive, retention, bảo trì index và thao tác partition lifecycle.
5. **Kiểm tra tài nguyên máy chủ.** Nếu pruning giảm I/O nhưng CPU/RAM vẫn chạm giới hạn, partitioning không tự mở rộng năng lực máy.
6. **Đánh giá khả năng sharding.** Xác định shard key có thể định tuyến phần lớn request và có tránh fan-out không.
7. **Mô hình hóa chi phí phân tán.** Đánh giá cross-shard JOIN, giao dịch nhiều shard, uniqueness, rebalancing, replication và lỗi node.
8. **So sánh tổng chi phí vận hành.** Bao gồm độ trễ, throughput, hạ tầng, phát triển ứng dụng, backup/restore và khả năng xử lý sự cố.
9. **Triển khai theo giai đoạn.** Thử với một nhóm dữ liệu hoặc tenant, xác nhận định tuyến và khả năng rollback trước khi mở rộng.
10. **Theo dõi liên tục.** Đo skew, partition growth, shard balance, query fan-out và plan regression.

## 20. Những sai lầm thường gặp

- **Cho rằng partitioning tự động làm truy vấn nhanh hơn.** Không có pruning hoặc không giảm dữ liệu đọc thì lợi ích có thể rất nhỏ.
- **Nhầm partitioning với sharding.** Nhiều partition trên cùng máy chủ không tạo thêm CPU, RAM hoặc IOPS.
- **Chọn partition key theo cardinality mà bỏ qua predicate.** Khóa có nhiều giá trị nhưng ít xuất hiện trong WHERE không giúp pruning.
- **Không kiểm tra query thiếu partition key.** Truy vấn có thể phải xét toàn bộ partition.
- **Tạo quá nhiều partition.** Planning, metadata, index và bảo trì có thể trở nên đắt đỏ.
- **Quên tạo partition tương lai.** Dữ liệu mới có thể bị lỗi ghi hoặc dồn vào default partition.
- **Chỉ mục hóa từng partition mà không kiểm tra tổng dung lượng.** Nhiều index cục bộ có thể chiếm cache và tăng write amplification.
- **Bỏ qua dữ liệu lệch.** Một tenant hoặc khoảng thời gian nóng có thể tạo bottleneck cục bộ.
- **Chỉ benchmark truy vấn đọc.** INSERT, UPDATE, DELETE, maintenance và retention cũng chịu tác động.
- **Chọn sharding quá sớm.** Chi phí cross-shard query, transaction và rebalancing có thể lớn hơn lợi ích mở rộng.

## 21. Danh sách kiểm tra trước khi triển khai

- [ ] Đã xác định vấn đề cần giải quyết: access path, dung lượng, retention hay giới hạn tài nguyên.
- [ ] Partition key xuất hiện trong predicate của phần lớn truy vấn mục tiêu.
- [ ] Chiến lược range/list/hash phù hợp với phân bố và vòng đời dữ liệu.
- [ ] Kích thước và số lượng partition dự kiến đã được tính cho nhiều năm.
- [ ] Có kế hoạch tạo partition mới và xử lý dữ liệu ngoài khoảng.
- [ ] Execution plan xác nhận partition pruning hoạt động.
- [ ] Index trong partition hỗ trợ WHERE, JOIN và ORDER BY.
- [ ] Đã kiểm tra truy vấn không có partition key và truy vấn quét toàn lịch sử.
- [ ] Đã đo planning time, p95/p99, throughput, logical/physical reads và CPU.
- [ ] Đã kiểm tra partition skew, hot partition và write throughput.
- [ ] Đã đánh giá retention, archive, detach/drop và backup/restore.
- [ ] Nếu sharding, đã xác định shard key, routing, fan-out và chi phí giao dịch phân tán.
- [ ] Có benchmark trước/sau trên cùng dữ liệu và workload đại diện.
- [ ] Có kế hoạch theo dõi và rollback sau triển khai.

## Kết luận

Phân vùng giúp tổ chức bảng lớn thành các phần có thể được truy cập và quản lý riêng. Lợi ích truy vấn chủ yếu đến từ partition pruning, khi điều kiện lọc cho phép hệ quản trị bỏ qua các vùng không liên quan; bên trong partition vẫn cần chỉ mục và thống kê phù hợp. Hãy kiểm chứng bằng execution plan, số partition thực sự được truy cập, logical/physical reads, planning time, độ trễ và throughput trên workload đại diện. Partitioning trên cùng một hệ quản trị không đồng nghĩa với sharding: sharding phân phối dữ liệu qua nhiều node và mở rộng tài nguyên nhưng tạo thêm chi phí định tuyến, fan-out, giao dịch phân tán và cân bằng dữ liệu. Chọn giải pháp theo nút thắt đã đo, không chỉ theo kích thước bảng.
