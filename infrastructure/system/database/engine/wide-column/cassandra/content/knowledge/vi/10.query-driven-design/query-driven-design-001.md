# Thu thập truy vấn, điều kiện lọc, thứ tự đọc và giới hạn kết quả

## Mục tiêu bài học

Trong Apache Cassandra, **mô hình dữ liệu bắt đầu từ các truy vấn mà ứng dụng cần thực hiện**. Trước khi chọn partition key, clustering column hay viết `CREATE TABLE`, người thiết kế phải làm rõ người dùng muốn đọc dữ liệu nào, theo điều kiện gì, theo thứ tự nào và lấy bao nhiêu bản ghi. Đây là bước đầu của thiết kế theo truy vấn (query-driven design) cho cơ sở dữ liệu phân tán dạng wide-column.

Sau bài này, bạn có thể:

- Chuyển một yêu cầu nghiệp vụ hoặc API thành **hợp đồng truy vấn** (query contract) có thể triển khai và kiểm tra.
- Phân biệt điều kiện nhận diện phân vùng, điều kiện giới hạn các hàng trong phân vùng và điều kiện lọc trên thuộc tính thông thường.
- Ghi nhận chính xác thứ tự sắp xếp, quy tắc xử lý các giá trị bằng nhau, `LIMIT`, phân trang, phạm vi thời gian và chi phí truy vấn nhiều phân vùng.
- Dùng danh mục truy vấn để định hướng **partition key**, **clustering column** và các bảng được nhân bản theo từng cách đọc; nhận diện sớm những yêu cầu không khớp với cách đọc hiệu quả của Cassandra.

## 1. Tại sao phải thu thập truy vấn trước khi tạo bảng?

Với cơ sở dữ liệu quan hệ, nhóm phát triển thường chuẩn hóa các thực thể rồi ghép, lọc và sắp xếp khi cần. Cassandra tối ưu cho việc định tuyến truy vấn tới những phân vùng xác định qua **partition key**, sau đó đọc các hàng đã được tổ chức theo **clustering column** trong từng phân vùng. Nó không cung cấp khả năng `JOIN` tùy ý và sắp xếp toàn bộ các phân vùng như một hệ quản trị quan hệ thông thường.

Vì vậy, câu hỏi “có những trường nào trong đơn hàng?” chưa đủ để thiết kế. Cần hỏi cụ thể:

> “Khách hàng xem 20 đơn gần nhất của mình trong một tháng, mới nhất trước, và có thể tải tiếp trang sau”

Yêu cầu trên đã gợi ý ba chiều thiết kế:

1. **Điểm vào truy vấn:** khách hàng nào, thuộc tenant nào, trong tháng nào → các thành phần có thể tạo thành partition key.
2. **Thứ tự đọc:** thời gian tạo đơn giảm dần → clustering column và hướng sắp xếp.
3. **Biên truy vấn:** tối đa 20 đơn mỗi lần xem → `LIMIT` và chiến lược phân trang; nếu phải xem qua nhiều tháng thì phải quy định cách đọc nhiều phân vùng.

Không có một bảng Cassandra “đa năng” phục vụ tốt mọi bộ lọc tùy ý. Có thể cần nhiều bảng lưu các bản sao có chủ đích của cùng dữ liệu, ví dụ `orders_by_customer_month`, `orders_by_id` và `orders_by_tenant_status_day`. Ứng dụng phải duy trì tính nhất quán của các cách biểu diễn đó khi dữ liệu thay đổi.

## 2. Mẫu thu thập một truy vấn

Với mỗi hành vi đọc, ghi một dòng trong **query inventory** và một hợp đồng chi tiết. Tối thiểu phải có những thông tin sau:

| Thành phần | Câu hỏi cần hỏi | Ví dụ: lịch sử đơn hàng |
| --- | --- | --- |
| Mục đích và người gọi | Ai đọc, đọc trong chức năng nào? | Khách hàng xem lịch sử đơn hàng qua API |
| Dữ liệu trả về | Những cột nào thực sự cần? | `order_id`, `created_at`, `status`, `total_amount` |
| Điều kiện bắt buộc | Giá trị nào luôn có khi gọi? | `tenant_id`, `customer_id`, `month_bucket` |
| Điều kiện tùy chọn | Có bộ lọc nào người dùng bật/tắt được? | Khoảng `created_at`; **không** mặc định có lọc `status` |
| Toán tử | So sánh bằng, khoảng, danh sách hay tiền tố? | Bằng trên khóa phân vùng, khoảng trên `created_at` |
| Thứ tự | Sắp theo cột nào và chiều nào? | `created_at DESC`, nếu trùng thì `order_id DESC` |
| Giới hạn và phân trang | Mỗi lần lấy bao nhiêu, tải tiếp ra sao? | 20 hàng, tối đa 100; driver paging/cursor |
| Phạm vi | Một phân vùng hay nhiều phân vùng? | Một khách hàng, một tháng; qua nhiều tháng thì nhiều lần đọc |
| Tải và độ lệch | QPS trung bình/đỉnh? Tenant nào quá lớn? | Cần đo theo khách hàng và theo tenant |
| Độ mới và nhất quán | Có chấp nhận dữ liệu chậm cập nhật? | Quy định yêu cầu hiển thị trạng thái đơn hàng, mức nhất quán đọc/ghi |
| Vòng đời dữ liệu | Giữ bao lâu, phát sinh sửa/xóa thế nào? | Lưu 24 tháng; trạng thái đơn có thể thay đổi |

Các con số trong ví dụ là **giả định để minh họa**, không phải cấu hình mặc định của Cassandra. Trước khi khóa thiết kế, thay chúng bằng dữ liệu đo thực tế hoặc cam kết sản phẩm.

Một hợp đồng truy vấn nên có định dạng dễ đối chiếu với API và CQL:

```text
ID: Q01
Use case: Khách hàng xem đơn trong một tháng
Input bắt buộc: tenantId, customerId, month (UTC, YYYY-MM)
Input tùy chọn: fromInclusive, toExclusive, pageToken
Filter: tenantId = ?, customerId = ?, monthBucket = ?;
        createdAt >= ? và createdAt < ? nếu có khoảng thời gian
Sort: createdAt DESC, orderId DESC
Output: orderId, createdAt, status, totalAmount
Page: 20 bản ghi; giới hạn nghiệp vụ 100 bản ghi/yêu cầu
Scope: chính xác một phân vùng của customer/tháng
Khác: từ ngày A đến B qua nhiều tháng → quy tắc đọc từng tháng riêng
```

Điểm quan trọng là **tách bộ lọc bắt buộc khỏi bộ lọc tùy chọn**. Một API cho phép `status` hoặc `minAmount` thay đổi tùy ý có thể tạo ra nhiều hình dạng truy vấn (query shape) khác nhau, và mỗi hình dạng cần được đánh giá riêng.

## 3. Phân loại điều kiện lọc trong Cassandra

Một `WHERE` trong CQL không đồng nghĩa với việc Cassandra có thể dùng mọi cột để tìm dữ liệu hiệu quả. Khi ghi nhận điều kiện, hãy chia chúng thành ba nhóm.

### 3.1. Điều kiện xác định phân vùng

**Partition key** quyết định dữ liệu nằm ở đâu trong cụm. Với khóa phân vùng ghép như `(tenant_id, customer_id, month_bucket)`, truy vấn thường cần giá trị cụ thể cho **tất cả** thành phần để nhắm vào một phân vùng:

```sql
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
```

Nếu chỉ biết `tenant_id` mà không có `customer_id` hoặc `month_bucket`, truy vấn trên bảng này không còn là lượt đọc trực tiếp vào một phân vùng. Đừng giả định Cassandra sẽ tìm nhanh mọi đơn của tenant bằng cách quét bảng.

Hỏi thêm khi thu thập yêu cầu:

- Người gọi **luôn** có đủ thành phần partition key không?
- Có truy vấn “tất cả khách hàng” hoặc “tất cả tháng” không? Nếu có, cần một cách đọc khác hay phân rã thành nhiều truy vấn?
- Phân vùng có nguy cơ rất lớn hoặc trở thành điểm nóng khi một khách hàng/tenant có lưu lượng cao không?

### 3.2. Điều kiện trên clustering column

Trong mỗi phân vùng, **clustering column** xác định thứ tự lưu trữ logic của các hàng. Chẳng hạn khóa `(created_at, order_id)` cho phép đọc theo thời gian và dùng `order_id` để xác định vị trí khi nhiều đơn có cùng thời điểm tạo.

Điều kiện trên clustering column phải phù hợp với **thứ tự các cột trong khóa**: thường dùng điều kiện bằng trên tiền tố, sau đó có thể dùng điều kiện khoảng trên cột phù hợp. Không thể tùy ý bỏ qua một clustering column đứng trước rồi trông đợi truy vấn vẫn được tối ưu. Các quy tắc cụ thể còn tùy loại toán tử CQL và phiên bản Cassandra; cần kiểm tra truy vấn thực tế với schema đã chọn.

Ví dụ phù hợp với bảng được định nghĩa ở phần sau:

```sql
AND created_at >= ?
AND created_at < ?
```

Phạm vi **bao gồm đầu, loại trừ cuối** (`[from, to)`) giúp tránh đếm trùng bản ghi khi chia khoảng thời gian liên tiếp. Cần thống nhất múi giờ, chẳng hạn UTC, để tính `month_bucket` và hai mốc thời gian đồng bộ.

### 3.3. Điều kiện trên cột thông thường

Các cột như `status`, `total_amount` hay `customer_name` có thể chỉ là **regular column** trong một bảng. Cassandra không mặc nhiên có đường truy cập hiệu quả cho các bộ lọc trên chúng.

Ví dụ, câu hỏi “mọi đơn `PAID` trong ngày của một tenant” **khác** với “20 đơn gần nhất của một khách hàng”. Nếu `status` là điều kiện bắt buộc của truy vấn thứ nhất, có thể cần bảng có `status` trong partition key, thay vì thêm `WHERE status = ?` vào bảng lịch sử khách hàng.

`ALLOW FILTERING` có thể cho phép một số câu truy vấn được thực thi, nhưng **không biến bộ lọc sau khi đọc thành đường truy cập có chi phí dự đoán được**. Chỉ dùng sau khi hiểu rõ khối lượng đọc, kích thước phân vùng và giới hạn vận hành; không coi đó là cách sửa mô hình dữ liệu.

Secondary index hoặc Storage-Attached Index (SAI, nếu phiên bản/triển khai hỗ trợ) cũng là những lựa chọn cần đánh giá theo đặc điểm truy vấn và dữ liệu. Chúng không thay thế việc mô tả rõ partition key, tính chọn lọc, thứ tự đọc và yêu cầu độ trễ.

## 4. Thu thập thứ tự đọc chính xác

“Đơn gần nhất” chưa đủ rõ. Cần hỏi:

- “Gần nhất” dựa trên `created_at`, `updated_at` hay thời điểm hoàn tất?
- Tăng dần hay giảm dần? Có cần đảo chiều?
- Khi hai hàng trùng thời gian, cột nào phân định thứ tự? Có cần thứ tự lặp lại ổn định giữa các trang?
- Phải sắp xếp **trong một phân vùng** hay **trên nhiều phân vùng**?

Trong Cassandra, `CLUSTERING ORDER BY` ở định nghĩa bảng thiết lập thứ tự mặc định bên trong phân vùng. Truy vấn `ORDER BY` trong CQL bị ràng buộc bởi khóa phân vùng và clustering column; không thể yêu cầu sắp xếp toàn cục theo một regular column như trong SQL tùy ý.

Ví dụ, một bảng lưu đơn theo khách hàng/tháng với clustering `created_at DESC, order_id DESC` phục vụ tự nhiên yêu cầu “mới nhất trước”. Nhưng nó **không** tự phục vụ yêu cầu “xếp mọi đơn toàn tenant theo `total_amount DESC`”; yêu cầu đó phải được đưa vào query inventory như một truy vấn độc lập.

Nếu màn hình hiển thị kết quả tổng hợp từ nhiều tháng hoặc nhiều phân vùng, ứng dụng cần quyết định **thứ tự hợp nhất các luồng kết quả**, số phân vùng tối đa sẽ đọc và cách tiếp tục ở trang sau. Cassandra không tự đảm bảo một thứ tự toàn cục khi ứng dụng ghép nhiều lượt đọc.

## 5. Phân biệt `LIMIT`, kích thước trang và giới hạn chi phí

Ba khái niệm sau không thể thay thế cho nhau:

| Khái niệm | Tác dụng | Điều **không** đảm bảo |
| --- | --- | --- |
| `LIMIT n` trong CQL | Giới hạn số hàng được trả về bởi câu truy vấn | Không đảm bảo chỉ đọc `n` hàng ở tầng lưu trữ, đặc biệt khi có tombstone/lọc |
| `page size` của driver | Điều khiển số hàng mục tiêu cho một trang kết quả được tải qua mỗi lượt phân trang | Không phải quy tắc nghiệp vụ “chỉ được xem tối đa `n` hàng” |
| Giới hạn ở API | Giới hạn kích thước dữ liệu/độ rộng khoảng thời gian/số phân vùng cho một yêu cầu | Không tự tối ưu CQL nếu khóa phân vùng hoặc bộ lọc không phù hợp |

Ví dụ:

```sql
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
LIMIT 20;
```

Nếu ứng dụng cần phân trang qua nhiều lượt gọi, nên dùng cơ chế paging của Cassandra driver và quản lý **paging state** một cách an toàn. Paging state là dữ liệu opaque gắn với câu truy vấn và tham số liên quan; không tự sửa, không dùng nó cho câu truy vấn khác và không mặc định xem một chuỗi trang là ảnh chụp nhất quán khi dữ liệu có cập nhật đồng thời. Không thiết kế phân trang kiểu `OFFSET` của SQL cho CQL.

Với UI kiểu “xem 20 đơn đầu tiên” hoặc “tải thêm”, phải ghi rõ liệu `LIMIT 20` là **tổng số hàng** tối đa cho câu truy vấn hay sản phẩm muốn **20 hàng mỗi trang qua nhiều trang**. Nếu muốn nhiều trang, triển khai `LIMIT` và cơ chế paging phải được thiết kế cùng nhau; một truy vấn bị `LIMIT 20` sẽ không cung cấp tùy ý trang thứ hai gồm 20 hàng khác của cùng kết quả.

Ngoài số hàng, cần giới hạn **số phân vùng được chạm tới**, **độ rộng thời gian** và **kích thước bản ghi**. Đọc 20 hàng sau một tập lớn tombstone, hoặc hỏi 20 hàng mới nhất qua hàng trăm phân vùng, vẫn có thể tốn tài nguyên và gây chậm.

## 6. Ví dụ xuyên suốt: hệ thống đơn hàng nhiều tenant

Giả sử một dịch vụ Java dùng Cassandra để lưu đơn hàng. Bảng sau là danh mục truy vấn thu thập từ sản phẩm; các tần suất và mục tiêu thời gian phản hồi cần được đo/bổ sung trước khi triển khai thực tế.

| ID | Nhu cầu đọc | Điều kiện đầu vào | Thứ tự và giới hạn | Hướng thiết kế |
| --- | --- | --- | --- | --- |
| Q01 | Xem đơn của một khách trong một tháng | `tenant_id =`, `customer_id =`, `month_bucket =`; thời gian tùy chọn | Mới nhất trước, 20 hàng/trang | `orders_by_customer_month` |
| Q02 | Xem chi tiết một đơn | `tenant_id =`, `order_id =` | Tối đa một đơn | `orders_by_id` |
| Q03 | Nhân viên xem đơn theo trạng thái trong một ngày | `tenant_id =`, `status =`, `day_bucket =` | Mới nhất trước, 50 hàng/trang | `orders_by_tenant_status_day` |
| Q04 | Xem 50 đơn mới nhất qua ba tháng | `tenant_id =`, `customer_id =`, ba tháng cần xét | Thứ tự toàn màn hình, tối đa 50 | Đọc các phân vùng tháng, hợp nhất và giới hạn ở ứng dụng |
| Q05 | Tìm đơn theo từ khóa, lọc số tiền tùy ý, sắp theo số tiền toàn tenant | Bộ lọc tùy ý | Sắp toàn cục và phân trang | Yêu cầu phân tích riêng; có thể cần thêm mô hình truy cập hoặc hệ tìm kiếm phù hợp |

Không nên gộp Q01–Q05 vào một `SELECT` duy nhất với nhiều bộ lọc tùy chọn. Điểm chung là dữ liệu “đơn hàng”; **đường đọc** của chúng khác nhau.

### 6.1. Thiết kế bảng cho Q01: lịch sử theo khách hàng/tháng

```sql
CREATE TABLE orders_by_customer_month (
    tenant_id text,
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    PRIMARY KEY ((tenant_id, customer_id, month_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
```

Ở đây:

- `(tenant_id, customer_id, month_bucket)` là **partition key ghép**. Một khách hàng trong một tháng ứng với một phân vùng logic.
- `(created_at, order_id)` là **clustering key**. Các hàng được tổ chức theo thời gian giảm dần, dùng ID để phân biệt khi trùng timestamp.
- `status` và `total_amount` là dữ liệu hiển thị, **không** phải khóa lọc linh hoạt của Q01.

Truy vấn Q01 với khoảng thời gian nằm trong tháng được yêu cầu:

```sql
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
  AND created_at >= ?
  AND created_at < ?
LIMIT 20;
```

Các dấu `?` là bind marker cho **prepared statement** của ứng dụng Java. Khi chạy trực tiếp bằng `cqlsh`, thay chúng bằng giá trị CQL hợp lệ. Nếu không cung cấp lọc theo khoảng thời gian, dùng một câu truy vấn đã chuẩn bị khác không chứa hai điều kiện `created_at`; đừng ghép điều kiện động tùy ý vào một truy vấn không kiểm soát.

Những điều phải chốt với sản phẩm:

- Có được truy vấn tùy ý qua nhiều tháng không? Nếu có, giới hạn tối đa mấy tháng và hợp nhất kết quả thế nào?
- Một khách hàng rất lớn phát sinh bao nhiêu đơn/tháng? Nếu phân vùng quá lớn, cần bucket nhỏ hơn (chẳng hạn ngày) hoặc phương án chia tải đã đo đạc.
- Khi có trạng thái đơn thay đổi, cột `status` được cập nhật ở những bảng biểu diễn nào?

### 6.2. Thiết kế bảng cho Q02: tra cứu đúng một đơn

```sql
CREATE TABLE orders_by_id (
    tenant_id text,
    order_id uuid,
    customer_id uuid,
    created_at timestamp,
    status text,
    total_amount decimal,
    PRIMARY KEY ((tenant_id, order_id))
);

SELECT customer_id, created_at, status, total_amount
FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
```

Truy vấn chi tiết có đầy đủ partition key và không cần sắp xếp. Nó không phải dạng truy vấn nên ép vào bảng lịch sử khách hàng nếu API không luôn có `customer_id` và `month_bucket`.

### 6.3. Thiết kế bảng cho Q03: danh sách theo trạng thái/ngày

```sql
CREATE TABLE orders_by_tenant_status_day (
    tenant_id text,
    status text,
    day_bucket date,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    total_amount decimal,
    PRIMARY KEY ((tenant_id, status, day_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

SELECT order_id, customer_id, created_at, total_amount
FROM orders_by_tenant_status_day
WHERE tenant_id = ?
  AND status = ?
  AND day_bucket = ?
LIMIT 50;
```

`status` là thành phần partition key **trong bảng Q03** vì nó là điều kiện lọc bắt buộc của màn hình này. Ngược lại, trong Q01, `status` chỉ là thuộc tính hiển thị. Đó là lý do cùng một thuộc tính có thể đóng vai trò khác nhau trong các bảng theo truy vấn.

Cần lưu ý hai tình huống vận hành:

1. Một tenant có quá nhiều đơn trong cùng trạng thái/ngày có thể tạo phân vùng lớn hoặc nóng. Trước khi triển khai, ước lượng số hàng và byte trên từng phân vùng ở giờ cao điểm; cân nhắc bucket nhỏ hơn hoặc shard có kiểm soát nếu số liệu yêu cầu.
2. Khi đơn đổi từ `PENDING` sang `PAID`, hệ thống cần cập nhật bảng tra theo ID, bảng lịch sử và **xóa bản ghi khỏi phân vùng trạng thái cũ, ghi bản ghi vào phân vùng mới**. Thiết kế đọc dễ dàng thường đổi lấy trách nhiệm đồng bộ nhiều bảng ở đường ghi; quy định rõ cơ chế xử lý lỗi, retry và đối soát.

### 6.4. Q04: đọc qua nhiều phân vùng không phải một lượt đọc có thứ tự toàn cục

Ví dụ người dùng muốn “50 đơn gần nhất trong ba tháng”. Với bảng Q01, có thể đọc ba phân vùng `month_bucket` tương ứng, lấy dữ liệu đã sắp xếp trong mỗi phân vùng rồi hợp nhất theo `(created_at DESC, order_id DESC)` ở dịch vụ. Thiết kế phải xác định số tháng tối đa, chiến lược lấy thêm khi một tháng hết dữ liệu, giới hạn tổng số hàng và cách lưu trạng thái phân trang cho từng phân vùng.

Không nên giả định thêm `IN` cho nhiều giá trị partition key và một `ORDER BY` sẽ tự tạo ra danh sách toàn cục đúng thứ tự với chi phí thấp. Khi fan-out tăng, tải và độ trễ của API cũng tăng. Nếu kiểu đọc liên tháng là truy vấn chủ đạo, cần đánh giá lại bucket hoặc một bảng phục vụ riêng.

## 7. Những câu hỏi phải giải quyết trước khi chốt khóa

### 7.1. Kích thước và độ nóng của phân vùng

Giả sử một khách có 2.000 đơn/ngày và mỗi hàng lưu trung bình khoảng 1 KiB dữ liệu nghiệp vụ. Một bucket 30 ngày tương ứng **xấp xỉ 60.000 hàng và 59 MiB dữ liệu thô** (chưa tính overhead, index, tombstone và cách lưu trữ thực tế). Đây là phép ước lượng ban đầu, **không** phải ngưỡng an toàn chung cho Cassandra.

Hỏi tiếp: khách hàng lớn nhất có bao nhiêu đơn? Có đột biến theo chiến dịch? Phân vùng lớn nhất, lớn nhất ở từng node và tỷ lệ tombstone là bao nhiêu? Bucket ngày làm phân vùng nhỏ hơn nhưng tăng số phân vùng cần đọc khi truy vấn cả tháng. Phải cân bằng theo tải thực tế và đo trên hệ thống mục tiêu.

### 7.2. Tần suất, SLA và tính nhất quán

Không phải mọi truy vấn đều có mức độ ưu tiên như nhau. Cần ghi nhận:

- Lượt gọi trung bình và đỉnh; số caller đồng thời; tenant hoặc khách hàng tạo nhiều tải nhất.
- Mục tiêu độ trễ (ví dụ p95/p99), tỷ lệ lỗi chấp nhận và dung lượng kết quả tối đa.
- Mức nhất quán đọc/ghi phù hợp (ví dụ `LOCAL_QUORUM` khi triển khai trong datacenter phù hợp), yêu cầu đọc thấy dữ liệu ngay sau khi ghi và cách chịu lỗi.
- Quy luật cập nhật, xóa hoặc TTL: tombstone có thể làm một truy vấn trả ít hàng vẫn tốn nhiều công đọc.

Việc đặt consistency level cao hơn không sửa được một truy vấn đọc quá nhiều phân vùng hoặc lọc dữ liệu kém hiệu quả; đó là hai quyết định thiết kế khác nhau.

### 7.3. Ranh giới của bộ lọc tùy chọn

Mỗi lựa chọn trên màn hình có thể tạo thêm một query shape. Ví dụ:

```text
GET /orders?customerId=...&month=...             -> Q01
GET /orders?customerId=...&month=...&status=PAID -> cần đánh giá riêng
GET /orders?status=PAID&day=...                  -> Q03
GET /orders?minAmount=...&sort=amount_desc      -> Q05, chưa có đường đọc phù hợp
```

Nếu sản phẩm muốn các bộ lọc kết hợp tùy ý, hãy ưu tiên xác định tập truy vấn thật sự được sử dụng, mức tải và trải nghiệm cần hỗ trợ. Không tự hứa hẹn hiệu năng cho tất cả tổ hợp bộ lọc chỉ vì API có thể biểu diễn chúng.

## 8. Mẫu bàn giao query inventory cho bước thiết kế bảng

Một bảng hoàn chỉnh giúp nhóm backend, sản phẩm và vận hành cùng kiểm tra giả định:

| Trường bàn giao | Ví dụ Q01 | Cách kiểm tra |
| --- | --- | --- |
| Query ID / owner | `Q01` / Customer API | Đối chiếu với endpoint và người phụ trách |
| Input luôn có | tenant, customer, month | Kiểm tra contract API và dữ liệu gọi thực tế |
| Khoảng đọc | tối đa một tháng/lượt | Test các trường hợp đổi tháng, UTC và dữ liệu rỗng |
| Bộ lọc | khóa phân vùng bằng; thời gian theo khoảng | Viết CQL thực tế, tránh yêu cầu `ALLOW FILTERING` |
| Sort | thời gian DESC, ID DESC | Test bản ghi trùng `created_at` |
| Limit/page | 20 mặc định; 100 tối đa | Test trang cuối, token không hợp lệ và ghi đồng thời |
| Kích thước phân vùng | dự báo hàng/tháng/customer | Đo theo nhóm lớn nhất, không chỉ giá trị trung bình |
| SLA/tải | số liệu cần điền từ thực tế | Load test, đo p95/p99 và số phân vùng được đọc |
| Nhất quán | chốt sau khi thống nhất nghiệp vụ | Kiểm tra read-after-write và lỗi replica |
| Trạng thái thiết kế | `SUPPORTED` / `NEEDS_DESIGN` | Không đánh dấu hỗ trợ nếu chưa có đường đọc rõ ràng |

Ở bước xác minh, hãy dùng `cqlsh` hoặc prepared statement với **schema và dữ liệu đại diện**, thử đầy đủ trường hợp đầu/cuối khoảng thời gian, phân vùng trống, phân vùng lớn và thay đổi trạng thái. Dùng tracing/metrics khi cần tìm số lượt đọc, độ trễ và vấn đề tombstone; đừng đánh giá chỉ bằng việc một câu CQL chạy thành công trên vài hàng mẫu.

## 9. Các sai lầm phổ biến

| Dấu hiệu | Vì sao nguy hiểm | Cách sửa ngay từ bước thu thập |
| --- | --- | --- |
| “Cứ lưu đơn rồi sẽ `WHERE` theo trường nào cũng được” | Bỏ qua tính định tuyến phân vùng và thứ tự clustering | Liệt kê riêng từng mẫu truy vấn, input bắt buộc và khối lượng |
| Chỉ ghi “đơn mới nhất” | Không rõ cột thời gian, cách xử lý trùng và phạm vi sắp xếp | Ghi `created_at DESC, order_id DESC`, phạm vi một hay nhiều phân vùng |
| Thêm `ALLOW FILTERING` để qua lỗi CQL | Có thể đọc nhiều dữ liệu rồi mới loại bỏ | Xác định bộ lọc nào cần thành khóa hoặc thành bảng phục vụ riêng |
| Tin rằng `LIMIT 20` bảo đảm truy vấn nhẹ | `LIMIT` không giới hạn tombstone hoặc số phân vùng cần đọc | Ghi giới hạn bucket, số phân vùng và chiến lược phân trang |
| Một partition key chỉ có `tenant_id` cho dữ liệu tăng vô hạn | Tenant lớn tạo phân vùng nóng/rất lớn | Phân tích phân bố dữ liệu, bucket và lưu lượng cao điểm |
| Thêm mọi bộ lọc vào một endpoint mà không phân tích | Mỗi tổ hợp có thể cần đường truy cập khác nhau | Đánh dấu query shape được hỗ trợ và chưa hỗ trợ |
| Nhân bản dữ liệu nhưng bỏ quên cập nhật/xóa | Các bảng có thể trả trạng thái khác nhau | Định nghĩa trách nhiệm cập nhật và quy trình đối soát |

## 10. Thực hành tự kiểm tra

Một sản phẩm yêu cầu màn hình **“20 giao dịch gần nhất của thiết bị trong ngày”**, có lọc bắt buộc theo `tenantId`, `deviceId`, ngày UTC; mặc định mới nhất trước. Người dùng đôi khi muốn xem cả tuần và lọc thêm `severity = HIGH`.

Hãy trả lời trước khi viết CQL:

1. Những trường nào phải có trong hợp đồng Q01? Trường nào là điều kiện lọc tùy chọn?
2. Với truy vấn một ngày, partition key và clustering column hợp lý là gì? Cần dùng cột nào để phân định khi timestamp trùng?
3. Yêu cầu “cả tuần” ảnh hưởng thế nào đến số phân vùng, thứ tự tổng và phân trang?
4. Bộ lọc `severity = HIGH` có thể áp dụng hiệu quả với bảng lịch sử ban đầu hay cần một thiết kế đọc khác?

**Gợi ý đối chiếu:** Một ứng viên là partition key `(tenant_id, device_id, day_bucket)` và clustering `(event_time DESC, event_id DESC)`, với `LIMIT 20` cho một lượt đọc trong ngày. Truy vấn tuần cần giới hạn fan-out và hợp nhất theo thứ tự tại ứng dụng hoặc cân nhắc bảng phù hợp hơn nếu quá phổ biến. `severity` chỉ nên trở thành đường lọc chính sau khi xác nhận mức độ sử dụng; việc chỉ thêm `WHERE severity = 'HIGH'` vào bảng lịch sử chưa đủ chứng minh hiệu quả.

## Kết luận

Trong Cassandra, mỗi truy vấn cần được xem như một **hợp đồng đọc cụ thể**: xác định phân vùng nào, thu hẹp hàng nào, đọc theo thứ tự nào, giới hạn bao nhiêu, phân trang thế nào và dưới tải thực tế ra sao. Danh mục truy vấn càng chính xác thì việc chọn partition key, clustering column, bucket và bảng nhân bản càng ít phải đoán. Ngược lại, các yêu cầu lọc tùy ý, sắp xếp toàn cục hoặc đọc hàng loạt phân vùng phải được nhận diện sớm và thiết kế như những đường đọc riêng có chi phí được kiểm soát.
