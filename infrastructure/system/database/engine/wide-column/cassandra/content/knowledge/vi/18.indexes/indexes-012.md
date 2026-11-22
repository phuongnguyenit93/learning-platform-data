# So sánh thêm chỉ mục với thiết kế bảng mới theo truy vấn

> **Chương:** Chỉ mục  
> **Chủ đề:** Ra quyết định giữa tạo index và tạo bảng chuyên cho truy vấn trong Apache Cassandra.  
> **Bối cảnh:** Cassandra là cơ sở dữ liệu phân tán theo mô hình *wide-column*; thiết kế phải xét khóa phân vùng, phân phối dữ liệu, độ trễ đọc/ghi, replication, compaction, repair và cách truy vấn từ ứng dụng Java.

## 1. Câu hỏi kiến trúc cần giải quyết

Giả sử ứng dụng quản lý đơn hàng lưu thông tin chính bằng `order_id`. Ban đầu, API chỉ tra cứu một đơn hàng theo ID. Về sau, sản phẩm bổ sung màn hình:

> “Hiển thị **20 đơn đã thanh toán mới nhất của một khách hàng**, từ mới đến cũ.”

Có hai hướng thường được đề xuất:

1. Giữ nguyên bảng gốc và **thêm chỉ mục** trên `customer_id`, `status` (hoặc những cột cần lọc).
2. Tạo **bảng theo mẫu truy vấn** với `customer_id` và `status` trong partition key, `created_at` trong clustering key.

Cả hai đều giúp tiếp cận dữ liệu theo điều kiện khác với khóa chính gốc, nhưng **không có cùng khả năng sắp xếp, chi phí đọc và trách nhiệm đồng bộ dữ liệu**. Quyết định đúng phải bắt đầu từ hợp đồng API: lọc theo trường nào, trả bao nhiêu hàng, sắp xếp ra sao, độ tươi dữ liệu cho phép bao nhiêu và tải dự kiến lớn đến đâu.

Mục tiêu của bài là biết lúc nào index giải quyết bài toán đủ tốt, lúc nào cần một bảng được thiết kế theo truy vấn, và cách chứng minh lựa chọn bằng phép đo thực tế.

## 2. Vì sao partition key là điểm xuất phát?

Trong Cassandra:

- **Partition key** quyết định token và vị trí các replica chứa partition. Khi biết đầy đủ partition key, coordinator có thể hướng truy vấn tới những replica liên quan.
- **Clustering key** sắp xếp các hàng *bên trong cùng partition*. Nó cho phép đọc một khoảng dữ liệu và trả theo thứ tự đã định, nhưng không cung cấp thứ tự tổng thể giữa nhiều partition.
- **Replication factor (RF)** quyết định số bản sao của một partition. Thêm index không làm mất chi phí liên lạc, đồng bộ hay đọc từ hệ thống phân tán.
- **`LIMIT 20`** chỉ giới hạn số dòng trả về. Nó không bảo đảm Cassandra phải tìm hoặc kiểm tra đúng 20 dòng trước khi có kết quả.

Ví dụ bảng gốc:

```cql
CREATE TABLE IF NOT EXISTS orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    status text,
    created_at timestamp,
    total decimal
);
```

Đường đọc tự nhiên là:

```cql
SELECT order_id, customer_id, status, created_at, total
FROM orders_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

Trong bảng này, mỗi `order_id` là partition key. Câu hỏi “các đơn của khách hàng X có trạng thái PAID” **không có partition key phù hợp**. Cassandra không thể tự suy ra một partition liên tiếp chứa các đơn của khách hàng đó.

Câu lệnh cố dùng `ALLOW FILTERING` không giải quyết gốc rễ. Nó có thể cho phép máy chủ đọc nhiều dữ liệu rồi lọc, khó dự báo độ trễ khi bảng lớn. Hãy xem `ALLOW FILTERING` là tín hiệu phải xem lại access pattern, không phải biện pháp mặc định để biến truy vấn thành hiệu quả.

## 3. Phương án A — Thêm chỉ mục vào bảng gốc

### 3.1. Chỉ mục thực sự làm gì?

Cassandra có các cơ chế index khác nhau tùy **phiên bản và bản phân phối**:

| Loại | Khái quát | Lưu ý thiết kế |
| --- | --- | --- |
| Secondary index truyền thống (thường gọi là **2i**) | Duy trì cấu trúc tra cứu theo cột ngoài khóa chính. | Thường kém phù hợp với truy vấn rất rộng, giá trị phổ biến trên nhiều partition hoặc workload phân tán quy mô lớn. |
| **Storage-Attached Index (SAI)** | Index gắn với lưu trữ của replica, hỗ trợ nhiều kiểu lọc hiệu quả hơn và kết hợp điều kiện ở các phiên bản hỗ trợ. | SAI không đổi cách chia partition và không cung cấp sắp xếp toàn cục tùy ý. Cần benchmark theo lượng kết quả và tải thật. |
| Bảng chuyên cho truy vấn | Lưu thêm một biểu diễn dữ liệu có partition/clustering key khớp cách đọc. | Trả giá bằng nhiều bản ghi, nhiều ghi và logic cập nhật/xóa đồng bộ. |

**Về phiên bản:** Apache Cassandra 5.0 hỗ trợ SAI; các phiên bản cũ, hệ quản trị tương thích CQL hoặc dịch vụ managed có thể khác nhau. Xác nhận khả năng của cluster trước khi dùng cú pháp SAI. Bài dùng SAI minh họa phương án index cho cluster hỗ trợ nó.

### 3.2. Ví dụ CQL với SAI

Trên Cassandra hỗ trợ SAI, sau khi tạo `orders_by_id`:

```cql
CREATE CUSTOM INDEX IF NOT EXISTS orders_customer_sai
ON orders_by_id (customer_id)
USING 'StorageAttachedIndex';

CREATE CUSTOM INDEX IF NOT EXISTS orders_status_sai
ON orders_by_id (status)
USING 'StorageAttachedIndex';
```

Truy vấn lọc theo hai cột đã được index:

```cql
SELECT order_id, created_at, total
FROM orders_by_id
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND status = 'PAID';
```

Đối với các kiểu điều kiện được SAI hỗ trợ, Cassandra có thể dùng index để tìm các hàng ứng viên, thay vì quét toàn bộ bảng bằng `ALLOW FILTERING`. Tuy nhiên, cần phân biệt ba việc:

1. **Tìm các hàng thỏa điều kiện:** SAI hỗ trợ mục tiêu này.
2. **Đọc dữ liệu và trả về qua cluster:** vẫn có chi phí tìm partition, đọc row, kiểm tra điều kiện và trao đổi với các replica.
3. **Lấy 20 đơn mới nhất theo `created_at` trên nhiều partition:** hai index trên `customer_id` và `status` **không bảo đảm được thứ tự đó**.

Không thể dựa vào thứ tự trả về tự nhiên của truy vấn SAI để suy ra “mới nhất”. Với mô hình bảng gốc trên, `ORDER BY created_at DESC` không phải cách sắp xếp hợp lệ cho tập kết quả trải trên nhiều partition. Nếu API bắt buộc *top 20 theo thời gian*, việc lấy kết quả từ index rồi sắp xếp trên Java có thể phải thu thập một tập kết quả lớn, phát sinh phân trang và dễ bỏ sót đơn mới nếu chỉ lấy một trang.

### 3.3. Khi nào index đáng cân nhắc?

Index phù hợp hơn khi các điều kiện sau cùng đúng:

- Query phát sinh **ít kết quả**, lọc đủ chọn lọc và không đòi thứ tự clustering cụ thể trên nhiều partition.
- Khối lượng truy vấn, độ trễ chấp nhận được và mức truy cập replica đã được thử ở dữ liệu gần sản xuất.
- Nhu cầu tìm kiếm linh hoạt hay thay đổi; tạo nhiều bảng phục vụ mọi tổ hợp bộ lọc sẽ phức tạp hơn giá trị nhận được.
- Có ngân sách cho dung lượng index, chi phí cập nhật index khi ghi, compaction và vận hành.

**Không dùng số lượng giá trị phân biệt (*cardinality*) làm tiêu chí duy nhất.** Ví dụ `status='PAID'` có ít giá trị phân biệt nhưng có thể khớp hàng triệu đơn; lọc thêm `customer_id` có thể giảm tập kết quả rất mạnh. Điều quyết định là **số hàng/partition ứng viên và độ trễ đo được**, không chỉ tên cột “cardinality cao hay thấp”.

## 4. Phương án B — Tạo bảng riêng theo truy vấn

Thay vì lấy đơn bằng cách tìm qua các partition theo `order_id`, ta lưu thêm một **read model** có partition key là tổ hợp cần lọc và clustering key là thứ tự hiển thị:

```cql
CREATE TABLE IF NOT EXISTS orders_by_customer_status (
    customer_id uuid,
    status text,
    created_at timestamp,
    order_id uuid,
    total decimal,
    PRIMARY KEY ((customer_id, status), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

Một dòng ví dụ:

```cql
INSERT INTO orders_by_customer_status
    (customer_id, status, created_at, order_id, total)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    'PAID',
    '2026-11-20 09:30:00+0000',
    11111111-1111-4111-8111-111111111111,
    249.00
);
```

Truy vấn mới khớp chính xác partition key và sử dụng thứ tự clustering:

```cql
SELECT order_id, created_at, total
FROM orders_by_customer_status
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
```

Ở đây Cassandra biết partition cần đọc từ `(customer_id, status)`; trong partition đó, các hàng đã được lưu theo `created_at DESC`. `order_id` đóng vai trò *tie-breaker* để hai đơn tạo cùng thời điểm vẫn có khóa hàng riêng. API có thể dùng cơ chế paging của driver để đọc trang kế tiếp; không nên giả lập `OFFSET` cho phân trang sâu.

**Bảng mới là một bản sao có chủ đích của dữ liệu phục vụ truy vấn.** Nó không thay thế `orders_by_id` nếu API vẫn cần tra cứu trực tiếp theo ID. Với Cassandra, việc lặp dữ liệu theo access pattern là bình thường, miễn là có quy trình nhất quán và kiểm soát chi phí cập nhật.

### Bảng mới phải trả lời đúng *toàn bộ* truy vấn

Thiết kế trên đáp ứng “20 đơn **PAID của khách hàng X**, mới nhất”. Nó **không** tự giải quyết “20 đơn thuộc **mọi trạng thái** của khách hàng X, mới nhất”, vì mỗi trạng thái là một partition khác nhau.

Nếu cả hai query đều là luồng chính, có thể cần thêm `orders_by_customer` với partition key chỉ gồm `customer_id` và clustering theo thời gian, hoặc thay đổi hợp đồng truy vấn. Việc tạo thêm bảng phải dựa vào mẫu truy vấn được sử dụng thật; không nhất thiết một table cho mỗi biến thể API.

### Tránh partition quá lớn

Một khách hàng có hàng triệu đơn trong cùng trạng thái có thể tạo partition quá lớn. Khi dữ liệu tích lũy không giới hạn, cân nhắc **bucketing theo tháng/ngày** hoặc theo mục tiêu kích thước partition, ví dụ đưa `bucket_yyyymm` vào partition key. Điều này làm query phải xác định bucket cần đọc hoặc đọc một số bucket gần nhất rồi hợp nhất kết quả. Việc bucketing cần dựa trên phân phối đơn hàng và mục tiêu độ trễ thực tế.

## 5. So sánh trực tiếp

| Tiêu chí | Thêm index (ví dụ SAI) | Bảng mới theo truy vấn |
| --- | --- | --- |
| **Thay đổi schema** | Thêm cấu trúc tra cứu vào bảng hiện tại. | Tạo bảng mới có partition/clustering key khác. |
| **Lọc linh hoạt** | Dễ thêm một số điều kiện được index hỗ trợ. | Tốt cho những access pattern đã dự đoán; mẫu truy vấn mới có thể cần bảng khác. |
| **Đọc ít hàng ở tập kết quả nhỏ** | Có thể rất tốt nếu index chọn lọc và cluster hỗ trợ tốt. | Rất tốt khi biết đúng partition và giới hạn dải clustering. |
| **Top N theo thời gian** | Không tự bảo đảm thứ tự toàn cục khi kết quả ở nhiều partition. | Được hỗ trợ tự nhiên nếu thời gian là clustering key trong một partition. |
| **Đọc kết quả rất rộng** | Có thể tốn nhiều công đọc/tra cứu phân tán. | Có thể hiệu quả khi access pattern bó vào partition; vẫn phải quản lý partition lớn. |
| **Chi phí ghi** | Cập nhật base row và cấu trúc index. | Ghi nhiều bảng; update có thể phải xóa/chèn projection. |
| **Dung lượng** | Cần không gian index. | Cần không gian bản sao các cột của read model. |
| **Nhất quán ứng dụng** | Index được Cassandra duy trì theo ghi vào bảng nguồn. | Ứng dụng/pipeline phải bảo đảm đồng bộ các bản sao dữ liệu. |
| **Vận hành** | Theo dõi index, compaction, tài nguyên đọc/ghi và quy trình build index. | Theo dõi từng bảng, tombstone, repair, tăng trưởng và đồng bộ dữ liệu. |
| **Điểm rủi ro chính** | Query rộng hoặc sai giả định về order/limit. | Dữ liệu ở các read model có thể lệch và số lượng bảng tăng quá mức. |

Không có quy tắc “luôn dùng bảng mới” hay “SAI luôn nhanh hơn”. Chúng tối ưu những thành phần chi phí khác nhau: **index tối ưu tìm ứng viên theo thuộc tính**, còn **bảng theo query tối ưu vị trí và thứ tự lưu dữ liệu** cho một tập truy cập xác định.

## 6. Giá phải trả cho một bảng đọc mới

Với `orders_by_customer_status`, khi đơn chuyển `PENDING -> PAID`, ứng dụng không thể chỉ thay đổi `status` trong một hàng của bảng mới. Vì `status` nằm trong **partition key** và là thành phần khóa chính, vị trí logic của đơn đã đổi. Quy trình cần xét:

1. Cập nhật trạng thái nguồn trong `orders_by_id`, có thể dùng LWT/`IF` nếu nghiệp vụ cần tránh tranh chấp trạng thái.
2. Xóa hàng cũ thuộc partition `(customer_id, 'PENDING')` của projection.
3. Thêm hàng mới thuộc partition `(customer_id, 'PAID')`, giữ nguyên `created_at` và `order_id`.
4. Khi lỗi mạng hoặc tiến trình dừng giữa chừng, có cơ chế retry idempotent và **đối soát** để các projection trở về trạng thái đúng.

Một `BATCH` CQL có thể hữu ích cho nhóm ghi liên quan, nhưng **không biến thao tác trên các partition thành giao dịch RDBMS có cô lập đa dòng**. Logged batch nhằm hỗ trợ tính nguyên tử của việc áp dụng các mutation trong batch; không bảo đảm người đọc đồng thời không nhìn thấy trạng thái trung gian ở nhiều partition. Nếu yêu cầu bất biến nghiệp vụ nghiêm ngặt xuyên nhiều partition, phải thiết kế quy trình xử lý, phiên bản hóa và khả năng phục hồi tương ứng.

Cũng phải giữ chính sách `TTL`, xóa dữ liệu, hạn lưu trữ và repair phù hợp giữa các bảng. Xóa một hàng tạo **tombstone**; các trạng thái thay đổi thường xuyên có thể khiến chi phí compaction/đọc tăng. Cần đánh giá vòng đời dữ liệu trước khi nhân bản bảng.

## 7. Bộ tình huống chọn giải pháp

| Access pattern | Hướng ưu tiên để thử | Lý do |
| --- | --- | --- |
| Tra cứu đơn theo `order_id`. | Bảng `orders_by_id`, không thêm index. | Đã có partition key chính xác. |
| Tìm vài đơn theo mã tham chiếu hiếm gặp, không cần sắp xếp. | SAI trên cột mã tham chiếu, nếu cluster hỗ trợ. | Tập kết quả dự kiến nhỏ; tránh duy trì cả bảng chỉ cho truy vấn ít dùng. |
| Lọc các đơn theo `customer_id` và `status` trong công cụ hỗ trợ, trả ít bản ghi, không đòi top N. | Thử SAI, benchmark trước khi chọn. | Hai điều kiện có thể giảm tập ứng viên đáng kể. |
| 20 đơn PAID mới nhất của khách hàng X, API gọi rất thường xuyên. | Bảng `orders_by_customer_status`. | Khóa phân vùng và thứ tự clustering khớp hợp đồng API. |
| Tìm *mọi* đơn PAID trên toàn hệ thống, có hàng triệu kết quả. | Xem lại yêu cầu; dùng bảng phân bucket/shard hoặc hệ tìm kiếm/phân tích phù hợp. | Một index trên giá trị phổ biến không làm truy vấn rộng trở thành nhỏ; một partition theo `status` cũng dễ nóng. |
| Báo cáo tổng hợp theo nhiều chiều, quét phần lớn dữ liệu mỗi ngày. | Hệ thống phân tích/ETL hoặc pre-aggregation. | Cassandra phục vụ truy vấn điều hướng theo khóa tốt hơn quét linh hoạt kiểu kho phân tích. |

**Quy tắc thực hành:** Nếu API cần “trả về **những hàng đầu tiên trong một thứ tự cố định**”, hãy thử mô hình partition/clustering trước. Nếu API cần “**tìm một số ít hàng** theo thuộc tính bổ sung” và không đòi thứ tự đặc biệt, index có thể là lựa chọn gọn hơn.

## 8. Quy trình ra quyết định có thể kiểm chứng

### Bước 1 — Ghi rõ hợp đồng query

Không dừng ở câu “lọc theo customer”. Ghi đủ:

- `WHERE` nào luôn có, điều kiện nào tùy chọn?
- Có yêu cầu `ORDER BY`, `LIMIT`, cursor hay trang tiếp theo không?
- Mỗi giá trị bộ lọc thường trúng **bao nhiêu hàng và bao nhiêu partition**?
- API được gọi bao nhiêu lần/giây ở mức trung bình và giờ cao điểm?
- Độ trễ p95/p99, tính nhất quán, mức chấp nhận trễ projection và số lượng ghi/giây là bao nhiêu?

Nếu chưa có số liệu, ghi đó là giả định cần đo, không tự xem là sự thật.

### Bước 2 — Phân tích khả năng định vị

Vẽ đường đi:

```text
Phương án index
Client -> Coordinator -> SAI/secondary index trên replica
       -> tìm candidate partition/row -> đọc dữ liệu -> trả kết quả

Phương án bảng theo truy vấn
Client -> Coordinator -> partition (customer_id, status)
       -> đọc range theo created_at DESC -> trả LIMIT N
```

Hai đường đi đều sử dụng replica và mức nhất quán Cassandra; khác biệt là Cassandra cần tìm ứng viên qua cấu trúc index hay có thể điều hướng tới ngay partition và dải clustering cần đọc.

### Bước 3 — Ước lượng chi phí ghi và tăng trưởng

Với bảng mới, liệt kê số projection chịu tác động bởi một đơn được tạo hoặc đổi trạng thái. Với index, liệt kê các cột được index, số lần cập nhật và dung lượng index theo thời gian. Đo compaction, tombstone và disk headroom thay vì chỉ quan sát thời gian của một câu `SELECT`.

Một bảng phục vụ query có thể làm đọc nhanh hơn nhưng làm đường ghi phức tạp; một index có thể giúp triển khai nhanh nhưng làm query rộng tạo tải khó dự báo. Đặt chi phí này vào cùng SLO của hệ thống.

### Bước 4 — Thử với dữ liệu và tải đại diện

Tạo môi trường có số partition, kích thước partition, phân phối `status`, số khách hàng lớn/nhỏ và RF gần sản xuất. Chạy **cùng access pattern** với cả hai phương án rồi ghi nhận:

| Chỉ số nên đo | Mục đích |
| --- | --- |
| p50/p95/p99 latency dưới concurrency thực tế | Nhận ra tail latency khi nhiều replica hoặc đĩa bận. |
| Số hàng trả về và tỷ lệ khớp điều kiện | Hiểu độ chọn lọc thực tế của index. |
| Read/write throughput, CPU, network, disk I/O | Tìm chi phí bị chuyển từ đọc sang ghi hoặc ngược lại. |
| Tốc độ tăng dung lượng bảng/index, compaction backlog | Kiểm tra khả năng vận hành dài hạn. |
| Partition size, hot partition, tombstone và timeout | Bắt các vấn đề sẽ nặng hơn khi dữ liệu lớn. |
| Độ lệch và thời gian sửa projection (nếu tạo bảng mới) | Xác nhận yêu cầu nhất quán của ứng dụng. |

Có thể dùng tracing CQL ở môi trường kiểm thử để tìm đường đi đọc, nhưng tránh bật tracing dày đặc trên workload sản xuất vì chính tracing cũng có chi phí. `LIMIT` và một lần benchmark nhanh không thay cho tải kéo dài với dữ liệu lệch (*skew*).

### Bước 5 — Chọn phương án và định nghĩa điều kiện đổi hướng

Ví dụ: chọn index cho tính năng quản trị ít dùng khi kết quả nhỏ, không cần sort và p95 đạt mục tiêu. Nếu sau này số kết quả tăng, API chuyển thành top N hoặc p99 vượt SLO, xem lại thiết kế bảng theo truy vấn.

Ngược lại, chọn bảng riêng cho màn hình lịch sử đơn hàng nóng; chỉ giữ những projection được API dùng và có quy trình backfill, đồng bộ, kiểm thử, giám sát rõ ràng.

## 9. Triển khai thay đổi mà không làm mất dữ liệu

### Nếu chọn thêm index

1. Kiểm tra phiên bản Cassandra, hỗ trợ SAI, kiểu dữ liệu và các loại predicate định dùng.
2. Tạo index trên dữ liệu hiện hữu theo quy trình hỗ trợ của phiên bản; theo dõi việc xây dựng index và tài nguyên cluster.
3. Chạy truy vấn ở tải nhỏ trước, so sánh số hàng và thời gian với đường đọc hiện tại.
4. Đặt quan sát cho truy vấn index có độ chọn lọc thấp, thời gian đọc bất thường và pressure từ compaction.

### Nếu chọn bảng mới

1. Tạo bảng projection với partition/clustering key phục vụ access pattern; ước lượng kích thước partition theo thời gian.
2. Cài đặt ghi kép hoặc pipeline cập nhật có thể retry, xử lý việc đổi khóa chính và xóa.
3. **Backfill** dữ liệu cũ từ nguồn đáng tin cậy với tốc độ kiểm soát; song song nhận các cập nhật mới và có chiến lược xử lý thứ tự sự kiện để tránh dữ liệu cũ ghi đè dữ liệu mới.
4. Đối soát kết quả bằng khóa/phiên bản/timestamp phù hợp; đo độ trễ dữ liệu projection.
5. Đổi luồng đọc bằng feature flag hoặc rollout dần, theo dõi độ trễ cùng sai lệch; giữ khả năng quay lại đường đọc an toàn trong thời gian chuyển đổi.

Đặc biệt, không chỉ tạo bảng rỗng rồi chuyển API sang đọc ngay: các đơn được tạo trước đó sẽ không tự xuất hiện trong projection. Cassandra **không tự đồng bộ hai bảng độc lập** vì chúng lưu cùng thông tin nghiệp vụ.

## 10. Ứng dụng Java nên triển khai hai đường đọc thế nào?

Dù dùng index hay bảng theo truy vấn, nên dùng **prepared statement**, chỉ truyền giá trị tham số, tận dụng paging của driver và theo dõi độ trễ theo loại query. Đừng ép một endpoint top N theo thời gian sử dụng SAI nếu câu truy vấn index không thể thỏa thứ tự.

Ví dụ Java Driver 4.x dùng bảng projection:

```java
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public final class OrderQueries {
    private final CqlSession session;
    private final PreparedStatement recentPaid;

    public OrderQueries(CqlSession session) {
        this.session = session;
        this.recentPaid = session.prepare(
            "SELECT order_id, created_at, total " +
            "FROM orders_by_customer_status " +
            "WHERE customer_id = ? AND status = ? " +
            "ORDER BY created_at DESC LIMIT ?"
        );
    }

    public ResultSet findRecentPaid(UUID customerId, int limit) {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit phải từ 1 đến 100");
        }

        BoundStatement statement = recentPaid.bind(
                customerId, "PAID", limit)
            .setPageSize(limit)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        return session.execute(statement);
    }

    public void printRecentPaid(UUID customerId) {
        ResultSet result = findRecentPaid(customerId, 20);
        for (Row row : result) {
            System.out.println(
                row.getUuid("order_id") + " " +
                row.getInstant("created_at") + " " +
                row.getBigDecimal("total")
            );
        }
    }
}
```

Ví dụ giả định `CqlSession` đã chọn đúng keyspace và có cấu hình topology/replication phù hợp. `LOCAL_QUORUM` là một lựa chọn mức nhất quán đọc, không phải giá trị bắt buộc cho mọi hệ thống. Driver có cơ chế phân trang; khi thiết kế API phân trang nhiều lần, cần quản lý **paging state** đúng với truy vấn và ràng buộc bảo mật của ứng dụng.

Nếu chỉ cần truy vấn hỗ trợ linh hoạt bằng SAI, Java có thể chuẩn bị lệnh `WHERE customer_id = ? AND status = ?` tương tự. Nhưng thứ tự kết quả của truy vấn đó **không được dùng như thứ tự thời gian**.

## 11. Sai lầm thường gặp

**“Cần cột nào trong `WHERE` thì tạo index cột đó.”** Một API có yêu cầu sắp xếp, giới hạn kết quả, điều kiện tổ hợp và phân trang. Index riêng lẻ không bảo đảm đáp ứng toàn bộ.

**“SAI thay thế thiết kế bảng theo truy vấn.”** SAI mở rộng lựa chọn tìm kiếm; không thay thế lợi thế của partition/clustering key khi đọc một dải theo thứ tự biết trước.

**“Có `LIMIT` nghĩa là truy vấn rẻ.”** `LIMIT` giới hạn kết quả trả về; thời gian tìm đủ N kết quả vẫn phụ thuộc độ chọn lọc, phân phối dữ liệu và kế hoạch đọc.

**“Cứ nhân bản bảng là nhanh.”** Một partition nóng hoặc quá lớn vẫn khiến truy vấn chậm. Bảng mới cũng tạo gánh nặng ghi và đối soát.

**“Logged `BATCH` bảo đảm các bảng cập nhật đồng thời và người đọc không thấy trạng thái trung gian.”** Không đúng. BATCH không cung cấp cô lập giao dịch đa partition như RDBMS.

**“Bảng mới có dữ liệu lịch sử ngay khi `CREATE TABLE`.”** Không. Phải backfill và đồng bộ cập nhật phát sinh trong lúc chuyển đổi.

## 12. Tự kiểm tra

1. Vì sao thêm index trên `status` vào `orders_by_id` không tự giải quyết “20 đơn PAID mới nhất của khách hàng X”?
2. Khi nào bạn chọn SAI dù một bảng riêng có thể trả lời truy vấn nhanh hơn? Bạn sẽ chứng minh điều đó bằng những chỉ số nào?
3. Vì sao chuyển `status` từ `PENDING` sang `PAID` trong `orders_by_customer_status` phải tính đến xóa và chèn hàng?
4. Nếu partition `(customer_id, status)` có nguy cơ tăng quá lớn, bạn sẽ thêm bucket vào khóa như thế nào? Điều đó ảnh hưởng paging ra sao?
5. Một `SELECT` chạy nhanh với 1.000 dòng dữ liệu thử nghiệm có đủ để triển khai toàn cluster không? Hãy giải thích cần đo thêm những gì.

**Kết luận thực hành:** Hãy bắt đầu bằng **truy vấn phải phục vụ và cách Cassandra tìm partition**. Dùng index khi cần tra cứu chọn lọc trên thuộc tính bổ sung và kết quả không đòi thứ tự toàn cục; dùng bảng theo truy vấn khi đường đọc chính cần khóa và thứ tự rõ ràng, đủ giá trị để chấp nhận đồng bộ dữ liệu nhân bản. Quyết định cuối cùng dựa vào số liệu về tải, phân phối dữ liệu và SLO, không chỉ vào số dòng CQL cần sửa.
