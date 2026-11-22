# Khóa phân cụm và thứ tự lưu các hàng trong phân vùng

Trong Apache Cassandra, **partition key** quyết định dữ liệu nằm ở phân vùng nào, còn **clustering column** (cột khóa phân cụm) quyết định các hàng trong **cùng phân vùng** được phân biệt và sắp theo thứ tự nào. Sự kết hợp này tạo nên khả năng đọc dữ liệu theo thực thể, theo chuỗi thời gian hoặc theo một phạm vi có thứ tự mà không cần sắp xếp toàn bộ bảng như trong nhiều truy vấn SQL quan hệ.

Chủ đề này thuộc phần **Khóa và phân vùng** của mô hình *wide-column* Cassandra. Hiểu clustering key giúp bạn thiết kế bảng theo truy vấn CQL, đồng thời có nền tảng để giải thích hiệu năng đọc, phân phối replica và tác động của quá trình lưu trữ, compaction hoặc repair.

Sau bài học, bạn có thể:

- Xác định đúng clustering columns trong khai báo `PRIMARY KEY`.
- Giải thích thứ tự từ điển (*lexicographic order*) khi có nhiều clustering columns.
- Dùng `CLUSTERING ORDER BY` để chọn thứ tự mặc định của dữ liệu trong mỗi phân vùng.
- Viết truy vấn CQL đọc theo tiền tố clustering key, theo khoảng thời gian và theo thứ tự đảo ngược hợp lệ.
- Thiết kế khóa có cột phân biệt sự kiện trùng thời gian, nhận diện những truy vấn không khớp khóa.

## 1. Clustering column nằm ở đâu trong primary key?

Một hàng logic được định danh bằng **toàn bộ primary key**:

```text
PRIMARY KEY = partition key + clustering columns (có thể không có)

Partition key          -> Chọn phân vùng, tham gia tính token.
Clustering column 1    -> Thứ tự và định danh trong phân vùng.
Clustering column 2    -> Phân biệt/sắp thứ tự khi cột 1 bằng nhau.
...
```

Ví dụ:

```sql
CREATE TABLE orders_by_customer (
    tenant_id text,
    customer_id uuid,
    created_at timestamp,
    order_id uuid,
    amount decimal,
    PRIMARY KEY ((tenant_id, customer_id), created_at, order_id)
);
```

| Loại cột | Cột | Vai trò |
| --- | --- | --- |
| Partition key ghép | `(tenant_id, customer_id)` | Xác định một phân vùng khách hàng trong tenant. |
| Clustering column thứ nhất | `created_at` | Nhóm và sắp các hàng theo thời điểm tạo. |
| Clustering column thứ hai | `order_id` | Phân biệt các đơn có cùng thời điểm và tạo thứ tự phụ. |
| Cột thường | `amount` | Giá trị của hàng, không quyết định token hay thứ tự clustering. |

Với cách khai báo trên, `(tenant_id, customer_id, created_at, order_id)` là **primary key đầy đủ**. Hai hàng có cùng `tenant_id` và `customer_id` nhưng khác `order_id` có thể cùng tồn tại trong phân vùng. Nếu mọi thành phần primary key đều giống nhau, ghi thêm dữ liệu là thao tác lên **cùng hàng logic**, không tạo hàng mới.

Đừng nhầm:

```sql
-- Chỉ tenant_id là partition key; các cột sau là clustering columns:
PRIMARY KEY (tenant_id, customer_id, created_at, order_id)

-- tenant_id và customer_id cùng là partition key; chỉ còn hai clustering columns:
PRIMARY KEY ((tenant_id, customer_id), created_at, order_id)
```

Cặp ngoặc bên trong có ý nghĩa quyết định: lựa chọn sai có thể khiến toàn bộ khách hàng của một tenant nằm trong một phân vùng quá lớn.

## 2. Thứ tự clustering chỉ tồn tại bên trong một phân vùng

Giả sử một bảng đo nhiệt độ có ba thành phần partition key: tenant, thiết bị và ngày. Với từng phân vùng, dữ liệu của các hàng được tổ chức theo clustering columns:

```text
Partition key = ('acme', 'device-01', 2026-11-21)
    |
    +-- clustering (09:20, event-B) -> nhiệt độ 38.2
    +-- clustering (09:20, event-C) -> nhiệt độ 38.3
    +-- clustering (09:10, event-A) -> nhiệt độ 37.9
    +-- clustering (08:55, event-D) -> nhiệt độ 37.7

Partition key = ('acme', 'device-02', 2026-11-21)
    |
    +-- clustering (09:15, event-E) -> nhiệt độ 36.6
    +-- clustering (08:45, event-F) -> nhiệt độ 36.4
```

Ở ví dụ này, thứ tự được minh họa theo thời điểm **giảm dần**. `event-B` và `event-C` có cùng thời điểm nên cột thứ hai sẽ quyết định thứ tự giữa chúng. Hai phân vùng tách biệt không có một thứ tự clustering chung.

Điều này dẫn đến ba kết luận quan trọng:

1. Cassandra đọc hiệu quả một **chuỗi hàng liên tiếp trong một phân vùng** khi truy vấn khớp partition key và clustering key.
2. Clustering columns **không thay đổi token** và không quyết định tập replica lưu phân vùng; đó là chức năng của partition key.
3. Cassandra không tự tạo một danh sách toàn cục đã được sắp theo clustering columns trên mọi phân vùng của cluster.

## 3. Khai báo thứ tự bằng `CLUSTERING ORDER BY`

Nếu không có cấu hình khác, Cassandra sắp các clustering columns theo thứ tự **tăng dần (`ASC`)**. Bạn có thể khai báo thứ tự mặc định khi tạo bảng, đặc biệt hữu ích với sự kiện cần đọc mới nhất trước:

```sql
CREATE TABLE sensor_events_by_device_day (
    tenant_id text,
    device_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    temperature double,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Trong bảng này:

- **Partition key:** `(tenant_id, device_id, event_day)`.
- **Clustering key:** `(occurred_at, event_id)`.
- **Thứ tự mặc định:** `occurred_at DESC`; nếu hai sự kiện cùng `occurred_at`, so sánh `event_id ASC`.
- **Cột thường:** `event_type` và `temperature` không thể được dùng như clustering columns chỉ vì chúng xuất hiện trong `SELECT`.

Điểm khác giữa `PRIMARY KEY` và `CLUSTERING ORDER BY`:

| Cấu hình | Quyết định điều gì? |
| --- | --- |
| `PRIMARY KEY ((tenant_id, device_id, event_day), occurred_at, event_id)` | Thành phần khóa phân vùng, số cột clustering và **thứ tự ưu tiên so sánh** của chúng. |
| `CLUSTERING ORDER BY (occurred_at DESC, event_id ASC)` | **Chiều tăng/giảm** mặc định của từng clustering column trong thứ tự lưu/đọc. |
| `ORDER BY` trong `SELECT` | Yêu cầu đọc theo thứ tự clustering hợp lệ trên truy vấn cụ thể; không định nghĩa lại schema. |

Thông thường nên chọn thứ tự mặc định phù hợp với luồng đọc phổ biến nhất. Ví dụ, dữ liệu theo thời gian thường đặt `occurred_at DESC` để lấy bản ghi mới nhất nhanh bằng `LIMIT`. Nếu nhiều cột cùng xuất hiện, thứ tự so sánh **theo vị trí trong primary key** vẫn giữ nguyên dù khai báo các chiều `ASC`/`DESC` khác nhau.

## 4. Nhiều clustering columns được sắp như thế nào?

Khi clustering key gồm nhiều cột, Cassandra so sánh **từ trái sang phải** theo định nghĩa bảng:

1. So sánh `occurred_at` trước, theo `DESC`.
2. Chỉ khi `occurred_at` bằng nhau mới so sánh `event_id`, theo `ASC`.
3. Hai hàng có cùng cả `occurred_at` lẫn `event_id` trong cùng partition key là **một hàng logic**.

Ví dụ minh họa (rút gọn `event_id` để dễ nhìn):

| `occurred_at` | `event_id` | Vị trí theo `(occurred_at DESC, event_id ASC)` |
| --- | --- | ---: |
| 09:20 | E-002 | 2 |
| 09:10 | E-005 | 3 |
| 09:20 | E-001 | 1 |
| 08:55 | E-004 | 4 |

Kết quả đúng trong cùng phân vùng:

```text
(09:20, E-001)
(09:20, E-002)
(09:10, E-005)
(08:55, E-004)
```

Bảng trên dùng mã `E-001` để minh họa. Trong CQL thật, `event_id` là `uuid` nên thứ tự phụ tuân theo bộ so sánh kiểu `uuid` của Cassandra, không phải so sánh chuỗi hiển thị tùy ý.

Cần tránh hiểu sai rằng Cassandra sẽ “sắp toàn bộ các hàng theo cột thứ hai” sau khi đã sắp cột thứ nhất. Cột thứ hai chỉ phá hòa giữa các hàng có cùng giá trị cột thứ nhất. Vì vậy, **thứ tự clustering columns trong primary key rất quan trọng**.

## 5. Ghi dữ liệu: clustering key cũng giúp định danh hàng

Để minh họa, ghi ba sự kiện của cùng thiết bị, cùng ngày. Hai sự kiện đầu cố ý trùng timestamp, nhưng khác `event_id`:

```sql
INSERT INTO sensor_events_by_device_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_type, temperature
) VALUES (
    'acme', 3f8d8c10-0bfe-4f27-b7f5-975e1db0d181, '2026-11-21',
    '2026-11-21T09:20:00+0700',
    00000000-0000-4000-8000-000000000001,
    'temperature', 38.1
);

INSERT INTO sensor_events_by_device_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_type, temperature
) VALUES (
    'acme', 3f8d8c10-0bfe-4f27-b7f5-975e1db0d181, '2026-11-21',
    '2026-11-21T09:20:00+0700',
    00000000-0000-4000-8000-000000000002,
    'temperature', 38.3
);

INSERT INTO sensor_events_by_device_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_type, temperature
) VALUES (
    'acme', 3f8d8c10-0bfe-4f27-b7f5-975e1db0d181, '2026-11-21',
    '2026-11-21T09:10:00+0700',
    00000000-0000-4000-8000-000000000003,
    'temperature', 37.9
);
```

Khi đọc phân vùng theo thứ tự mặc định, hai sự kiện 09:20 đứng trước 09:10; sự kiện 09:20 có `event_id` nhỏ hơn đứng trước sự kiện còn lại.

Nếu ghi lại với cùng **partition key + occurred_at + event_id**, Cassandra cập nhật giá trị của **chính hàng đó** theo cơ chế ghi và quy tắc xử lý xung đột của Cassandra, không chèn thêm hàng trùng. Vì vậy:

- Nếu cần giữ **nhiều sự kiện có timestamp giống nhau**, hãy có khóa phân biệt ổn định như `event_id`.
- Nếu cần **retry an toàn**, ứng dụng nên dùng lại `event_id` đã cấp cho cùng sự kiện khi gửi lại lệnh ghi.
- Không dùng `temperature` làm clustering column chỉ để sắp xếp kết quả đo: số đo có thể trùng, biến động và không đại diện cho định danh sự kiện.

Mọi thành phần primary key phải có giá trị hợp lệ, không được `null` khi xác định hàng. Đổi `occurred_at` hay `event_id` nghĩa là đổi primary key; thông thường cần ghi hàng theo khóa mới và xử lý hàng cũ một cách có chủ đích.

## 6. Truy vấn theo thứ tự clustering

### 6.1. Lấy 20 sự kiện gần nhất trong ngày

```sql
SELECT occurred_at, event_id, event_type, temperature
FROM sensor_events_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 3f8d8c10-0bfe-4f27-b7f5-975e1db0d181
  AND event_day = '2026-11-21'
LIMIT 20;
```

Mệnh đề `WHERE` xác định **đầy đủ partition key**. Trong phân vùng được chọn, dữ liệu tuân theo thứ tự mặc định `occurred_at DESC, event_id ASC`; do đó `LIMIT 20` lấy 20 hàng đầu tiên của thứ tự này. Không cần `ORDER BY` nếu muốn đúng thứ tự clustering đã khai báo.

### 6.2. Lấy sự kiện trong một khoảng thời gian

```sql
SELECT occurred_at, event_id, temperature
FROM sensor_events_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 3f8d8c10-0bfe-4f27-b7f5-975e1db0d181
  AND event_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T08:00:00+0700'
  AND occurred_at <  '2026-11-21T10:00:00+0700';
```

Đây là truy vấn **range** trên clustering column đầu tiên. Vì các hàng được tổ chức theo khóa này trong từng phân vùng, Cassandra có thể tìm khoảng phù hợp và đọc theo thứ tự clustering.

Lưu ý: `event_day` ở partition key là ngày bucket mà **ứng dụng** chọn. Hãy thống nhất múi giờ và cách tính bucket; dữ liệu được ghi vào ngày UTC nhưng ứng dụng đọc theo ngày Việt Nam sẽ có thể tìm nhầm phân vùng nếu quy tắc không đồng nhất.

### 6.3. Lọc theo tiền tố clustering key

Vì cột `occurred_at` đứng **trước** `event_id`, bạn có thể lọc bằng một giá trị `occurred_at` cụ thể rồi áp dụng điều kiện trên `event_id`:

```sql
SELECT event_id, temperature
FROM sensor_events_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 3f8d8c10-0bfe-4f27-b7f5-975e1db0d181
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T09:20:00+0700'
  AND event_id >= 00000000-0000-4000-8000-000000000001;
```

Ở đây việc lọc `event_id` hiệu quả vì cột đứng trước (`occurred_at`) đã được ràng buộc bằng giá trị bằng. Nếu không biết `occurred_at`, việc lọc riêng `event_id` không thể sử dụng clustering key như một đường truy cập đơn giản theo tiền tố.

### 6.4. Đọc theo chiều đảo ngược

```sql
SELECT occurred_at, event_id, temperature
FROM sensor_events_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 3f8d8c10-0bfe-4f27-b7f5-975e1db0d181
  AND event_day = '2026-11-21'
ORDER BY occurred_at ASC, event_id DESC
LIMIT 20;
```

Thứ tự `ASC, DESC` ở đây là **đảo chiều của toàn bộ** thứ tự mặc định `DESC, ASC`. Cassandra có thể duyệt ngược clustering order khi truy vấn giới hạn đúng một phân vùng. Không nên suy ra rằng CQL cho phép đảo chiều từng cột tùy ý hay sắp theo bất kỳ cột nào như SQL quan hệ.

## 7. Các ràng buộc đáng nhớ của `WHERE` và `ORDER BY`

CQL được tối ưu cho những phép truy cập khớp khóa, vì vậy cần nắm một số nguyên tắc:

| Truy vấn | Phù hợp với bảng ví dụ? | Lý do |
| --- | --- | --- |
| Đầy đủ `tenant_id`, `device_id`, `event_day` | **Có** | Chọn được phân vùng. |
| Đầy đủ partition key + khoảng `occurred_at` | **Có** | Clustering column đầu tiên hỗ trợ điều kiện range. |
| Đầy đủ partition key + `occurred_at = ...` + lọc `event_id` | **Có** | Tuân theo thứ tự tiền tố clustering key. |
| Chỉ `tenant_id = ...` | **Không theo đường khóa thông thường** | Thiếu hai phần partition key ghép. |
| Đầy đủ partition key + chỉ `event_id = ...` | **Không theo đường khóa thông thường** | Bỏ qua clustering column đứng trước. |
| Đầy đủ partition key + `ORDER BY temperature DESC` | **Không** | `temperature` không phải clustering column. |
| `ORDER BY occurred_at DESC` trên toàn cluster, thiếu partition key | **Không** | Không có thứ tự clustering toàn cục. |

Ví dụ sai:

```sql
-- Cột event_id không phải clustering column đầu tiên:
SELECT * FROM sensor_events_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 3f8d8c10-0bfe-4f27-b7f5-975e1db0d181
  AND event_day = '2026-11-21'
  AND event_id = 00000000-0000-4000-8000-000000000001;

-- Không thể sắp theo một cột thường:
SELECT * FROM sensor_events_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 3f8d8c10-0bfe-4f27-b7f5-975e1db0d181
  AND event_day = '2026-11-21'
ORDER BY temperature DESC;
```

Có những trường hợp Cassandra hỗ trợ `IN`, chỉ mục hoặc `ALLOW FILTERING`, nhưng chúng có ràng buộc và chi phí riêng. Nếu truy vấn chủ đạo luôn cần “tìm theo event ID mà không biết thời gian”, hãy thiết kế một bảng tra theo `event_id` hoặc một đường truy cập chuyên biệt, thay vì dựa vào lọc rộng.

## 8. Thứ tự các clustering columns là một quyết định thiết kế

Cùng ba cột `event_type`, `occurred_at` và `event_id` nhưng đổi vị trí clustering sẽ phục vụ những truy vấn khác nhau.

**Phương án A — ưu tiên chuỗi thời gian của mọi loại sự kiện:**

```sql
PRIMARY KEY (
    (tenant_id, device_id, event_day),
    occurred_at,
    event_id
)
```

Phương án này phù hợp để lấy sự kiện theo khoảng thời gian, bất kể `event_type`. Nếu phải truy vấn thường xuyên theo loại sự kiện, `event_type` là cột thường nên không tự hỗ trợ truy cập theo khóa.

**Phương án B — ưu tiên sự kiện theo loại, rồi mới theo thời gian:**

```sql
PRIMARY KEY (
    (tenant_id, device_id, event_day),
    event_type,
    occurred_at,
    event_id
)
```

Cách này phù hợp khi ứng dụng **biết trước loại sự kiện**:

```sql
SELECT occurred_at, event_id
FROM sensor_events_by_type_day
WHERE tenant_id = 'acme'
  AND device_id = 3f8d8c10-0bfe-4f27-b7f5-975e1db0d181
  AND event_day = '2026-11-21'
  AND event_type = 'temperature'
  AND occurred_at >= '2026-11-21T08:00:00+0700';
```

**Chú ý:** `sensor_events_by_type_day` là **bảng minh họa khác**, chưa được tạo bằng các lệnh phía trên. Nếu triển khai phương án B, cần tạo bảng đó với partition key và thứ tự clustering tương ứng trước khi chạy truy vấn.

Nếu chỉ biết khoảng `occurred_at` nhưng không biết `event_type`, phương án B không còn cho phép sử dụng một khoảng thời gian liên tục trên toàn phân vùng theo tiền tố clustering key. Vì vậy, câu hỏi “sắp theo cột nào trước?” chính là câu hỏi “ứng dụng lọc theo điều kiện nào trước?”.

Trong Cassandra, có thể lưu **nhiều bảng cùng biểu diễn một thực thể** nhưng tổ chức theo những câu truy vấn khác nhau. Đây là phương pháp *query-driven table design* thay vì mong một bảng trả lời hiệu quả mọi loại truy vấn.

## 9. “Thứ tự lưu” không có nghĩa là toàn bộ phân vùng nằm một chỗ trên đĩa

Ở mức mô hình dữ liệu, các hàng trong một phân vùng có thứ tự theo clustering key. Ở mức lưu trữ thật, Cassandra dựa trên kiến trúc kiểu **LSM-tree**:

1. Ghi được tiếp nhận qua cơ chế của Cassandra và dữ liệu được tích lũy trong *memtable*.
2. Khi flush, dữ liệu được ghi thành các **SSTable** bất biến, được tổ chức có thứ tự theo khóa.
3. Một phân vùng logic có thể có các phiên bản hoặc phần dữ liệu phân tán trên **nhiều SSTable**; Cassandra kết hợp kết quả khi đọc.
4. **Compaction** hợp nhất/viết lại SSTable theo chính sách thích hợp, giúp quản lý các phiên bản và dữ liệu cũ. **Repair** hỗ trợ đồng bộ dữ liệu giữa các replica; cả hai không đổi định nghĩa partition/clustering key của bảng.

Do đó, phát biểu “clustering key sắp dữ liệu vật lý” cần hiểu là **quy tắc tổ chức thứ tự bên trong phân vùng mà công cụ lưu trữ và truy vấn sử dụng**, không có nghĩa toàn bộ phân vùng vĩnh viễn nằm liên tục trong một tệp.

Clustering key cũng **không giải quyết phân vùng quá lớn**. Nếu partition key chỉ gồm `device_id` và thiết bị ghi không ngừng, phân vùng đó vẫn tăng dần, dù dữ liệu đã được sắp hoàn hảo theo thời gian. Để giới hạn kích thước, cần bucket theo ngày/giờ/tháng trong **partition key**, ví dụ `(tenant_id, device_id, event_day)`.

### Đọc phân trang và thứ tự có ý nghĩa gì?

Với một phân vùng có hàng triệu sự kiện, nên dùng giới hạn hợp lý và tính năng phân trang của driver khi cần đi qua nhiều hàng. Phân trang giúp kiểm soát lượng dữ liệu mỗi lần lấy nhưng không đổi bản chất thứ tự clustering. Với dữ liệu đang ghi liên tục, một chuỗi nhiều truy vấn ở các thời điểm khác nhau không tự trở thành ảnh chụp nhất quán của toàn bộ lịch sử; cần thiết kế logic đọc theo yêu cầu nghiệp vụ.

## 10. Dùng clustering key từ ứng dụng Java

Ví dụ dưới đây sử dụng API Java Driver 4.x, giả định đã có `CqlSession` và bảng `sensor_events_by_device_day`. Prepared statement cung cấp các điều kiện bằng cho partition key, rồi đọc kết quả theo thứ tự clustering:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public final class SensorEventReader {
    private final CqlSession session;
    private final PreparedStatement latestInDay;

    public SensorEventReader(CqlSession session) {
        this.session = session;
        this.latestInDay = session.prepare(
            "SELECT occurred_at, temperature " +
            "FROM sensor_events_by_device_day " +
            "WHERE tenant_id = ? AND device_id = ? AND event_day = ? " +
            "LIMIT 20"
        );
    }

    public List<Instant> recentTimes(
            String tenantId, UUID deviceId, LocalDate day) {

        ResultSet rows = session.execute(
            latestInDay.bind(tenantId, deviceId, day)
        );

        List<Instant> result = new ArrayList<>();
        for (Row row : rows) {
            result.add(row.getInstant("occurred_at"));
        }
        return result;
    }
}
```

Code trên trình bày cách gắn đủ partition key và đọc thứ tự sẵn có. Trong hệ thống thực, cần quyết định quy tắc tính `event_day`, độ dài trang, timeout, mức nhất quán và xử lý lỗi khi một replica không phản hồi; các cấu hình ấy không thay đổi cấu trúc clustering key.

## 11. Các lỗi phổ biến và cách sửa

| Dấu hiệu | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Hai sự kiện trùng timestamp bị “mất một hàng” | Primary key chỉ có `occurred_at`, không có định danh phụ. | Thêm `event_id` ổn định vào clustering key. |
| Lấy bản ghi mới nhất nhưng mỗi lần phải xử lý tập rất lớn | Phân vùng quá lớn hoặc truy vấn không giới hạn. | Dùng bucket ở partition key, `LIMIT` và phân trang phù hợp. |
| Muốn `ORDER BY temperature` nhưng Cassandra từ chối | `temperature` là cột thường. | Thiết kế đường truy cập/bảng riêng nếu đây là yêu cầu chính. |
| Cần lọc `event_id` nhưng không có `occurred_at` | Bỏ qua cột đầu của clustering key. | Dùng bảng tra cứu theo event ID hoặc mô hình khóa khác. |
| Mọi bản ghi một ngày nằm chung một phân vùng | Partition key chỉ có `event_day`, độ phân biệt thấp. | Ghép tenant/thiết bị hoặc thực thể có độ phân biệt phù hợp. |
| Lấy chuỗi thời gian theo dải khó dù có cột thời gian | `event_type` đứng trước `occurred_at` mà truy vấn không ràng buộc loại. | Đổi thứ tự clustering trong bảng mới hoặc thêm bảng truy vấn theo thời gian. |
| Dữ liệu “không được sắp trên toàn cluster” | Nhầm thứ tự clustering nội bộ với thứ tự toàn cục. | Đọc từng partition/bucket và hợp nhất thứ tự trong ứng dụng nếu cần. |

Nếu muốn thay **cấu trúc primary key** hoặc thứ tự clustering đã định nghĩa cho bảng triển khai, thông thường cần tạo bảng mới, di chuyển/ghi lại dữ liệu và đổi luồng truy cập; không nên coi đây là thao tác `ALTER TABLE` đơn giản. Nên thử schema bằng một bộ truy vấn thực trước khi đưa vào vận hành.

## 12. Bài tập tự kiểm tra

Cho bảng:

```sql
CREATE TABLE activities_by_user_week (
    tenant_id text,
    user_id uuid,
    week_start date,
    activity_type text,
    occurred_at timestamp,
    activity_id uuid,
    payload text,
    PRIMARY KEY (
        (tenant_id, user_id, week_start),
        activity_type,
        occurred_at,
        activity_id
    )
) WITH CLUSTERING ORDER BY (
    activity_type ASC,
    occurred_at DESC,
    activity_id ASC
);
```

Hãy tự trả lời:

1. Partition key gồm những cột nào? Có bao nhiêu clustering columns?
2. Trong cùng tuần và cùng người dùng, hoạt động khác `activity_type` được nhóm/sắp theo tiêu chí nào trước?
3. Hai hoạt động cùng `activity_type` và cùng `occurred_at`, nhưng khác `activity_id`, có tạo hai hàng không?
4. Để lấy 10 hoạt động mới nhất của loại `login`, cần đưa điều kiện nào vào `WHERE`?
5. Để lấy 10 hoạt động mới nhất **bất kể loại nào**, bảng này có trả kết quả theo thời gian toàn cục của phân vùng hay không?
6. Đổi `activity_type` từ vị trí clustering đầu tiên sang vị trí sau `occurred_at` sẽ ưu tiên kiểu truy vấn nào?

**Đáp án giải thích:**

1. Partition key ghép `(tenant_id, user_id, week_start)`; ba clustering columns theo thứ tự `activity_type`, `occurred_at`, `activity_id`.
2. Trước tiên theo `activity_type ASC`. Chỉ trong mỗi giá trị `activity_type` mới sắp `occurred_at DESC`; sau đó `activity_id ASC`.
3. Có, vì `activity_id` tham gia primary key; toàn bộ khóa hai hàng khác nhau.
4. Cần cung cấp đủ `tenant_id`, `user_id`, `week_start` và `activity_type = 'login'`, rồi `LIMIT 10`. Nếu muốn đúng 10 theo thời gian mới nhất trong loại login, thứ tự clustering mặc định đáp ứng.
5. Không. Các hàng được nhóm theo `activity_type` trước, nên 10 hàng đầu có thể chỉ thuộc những loại đứng đầu theo chữ cái, không phải 10 sự kiện mới nhất của mọi loại.
6. Ưu tiên truy vấn theo **thời gian xuyên các loại hoạt động**; nếu cần lọc theo loại, nên cân nhắc tạo thêm bảng chuyên biệt.

## 13. Ghi nhớ khi thiết kế bảng Cassandra

- **Partition key chọn phân vùng; clustering key định danh và sắp các hàng bên trong phân vùng.**
- **Thứ tự các clustering columns trong `PRIMARY KEY`** quyết định thứ tự ưu tiên so sánh. `CLUSTERING ORDER BY` quyết định chiều `ASC`/`DESC`.
- Muốn đọc theo một clustering column phía sau, thông thường cần ràng buộc bằng các clustering columns đứng trước; **range** thường đặt ở cột clustering đầu tiên chưa được cố định.
- `LIMIT`, `ORDER BY` và lọc khoảng phát huy tác dụng khi truy vấn khớp partition key và clustering key; chúng không biến thứ tự nội bộ thành thứ tự toàn cục.
- Chọn cột clustering theo truy vấn chính và có cột phân biệt hàng khi giá trị sắp thứ tự có thể trùng. Muốn giới hạn kích thước phân vùng, phải thiết kế **partition key/bucket** thích hợp.

Nắm chắc clustering key giúp bạn đọc đúng thứ tự dữ liệu, viết CQL có chi phí dự đoán được và chọn cấu trúc bảng wide-column phù hợp với các dịch vụ Java kết nối tới Apache Cassandra.

