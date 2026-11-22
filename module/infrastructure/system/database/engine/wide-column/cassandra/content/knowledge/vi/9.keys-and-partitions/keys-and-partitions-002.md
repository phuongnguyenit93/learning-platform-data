# Khóa phân vùng đơn và khóa phân vùng ghép

Trong Apache Cassandra, chọn **partition key** là quyết định quan trọng khi thiết kế bảng: khóa này xác định phân vùng logic mà Cassandra đọc, ghi và sao chép trên các node. Partition key có thể gồm **một cột** (*khóa phân vùng đơn*) hoặc **nhiều cột** (*khóa phân vùng ghép*). Cả hai đều có thể đi kèm các *clustering column* để lưu nhiều hàng trong cùng một phân vùng.

Ở mô hình wide-column phân tán, chọn đúng số lượng và thành phần partition key giúp truy vấn CQL đi thẳng đến dữ liệu cần thiết, phân phối tải hợp lý và kiểm soát kích thước phân vùng. Bài này tập trung so sánh hai cách chọn khóa phân vùng; kiến thức về replication, mức nhất quán và kết nối từ Java sẽ dựa trên lựa chọn đó.

Sau khi học, bạn có thể:

- Phân biệt partition key một cột và nhiều cột qua cú pháp `PRIMARY KEY`.
- Dự đoán hai hàng thuộc cùng hay khác phân vùng bằng cách đối chiếu **toàn bộ** giá trị partition key.
- Chọn khóa phù hợp cho truy vấn theo khách hàng, thiết bị, thời gian và tenant.
- Nhận biết nguy cơ *hot partition*, phân vùng tăng vô hạn và truy vấn thiếu thành phần khóa.
- Viết CQL và truy vấn từ ứng dụng Java khớp với khóa đã thiết kế.

## 1. Partition key đơn: một giá trị xác định một phân vùng

**Khóa phân vùng đơn** là partition key chỉ gồm **một cột**. Ví dụ, mỗi khách hàng có một hồ sơ:

```sql
CREATE TABLE customer_profile_by_id (
    customer_id uuid PRIMARY KEY,
    display_name text,
    email text
);

-- Tương đương: PRIMARY KEY (customer_id)
```

Mỗi `customer_id` xác định một phân vùng logic. Vì primary key không chứa clustering column, mỗi giá trị `customer_id` có tối đa một hàng logic trong bảng này.

```sql
SELECT display_name, email
FROM customer_profile_by_id
WHERE customer_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

Cassandra định vị phân vùng từ `customer_id` và đọc hàng trong phân vùng đó. Khóa đơn **không có nghĩa là** mỗi phân vùng chỉ được chứa một hàng. Khi bổ sung clustering column, một partition key đơn có thể chứa nhiều hàng:

```sql
CREATE TABLE readings_by_device (
    device_id uuid,
    recorded_at timeuuid,
    reading double,
    PRIMARY KEY (device_id, recorded_at)
) WITH CLUSTERING ORDER BY (recorded_at DESC);
```

Trong bảng này:

- Partition key: **`device_id`**.
- Clustering column: **`recorded_at`**.
- Primary key đầy đủ: **`(device_id, recorded_at)`**.
- Mọi bản ghi có cùng `device_id` nằm trong **cùng phân vùng**, dù `recorded_at` khác nhau.

Truy vấn lấy 10 giá trị gần nhất của một thiết bị:

```sql
SELECT recorded_at, reading
FROM readings_by_device
WHERE device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
LIMIT 10;
```

Khóa đơn dễ dùng khi một giá trị đủ để xác định tập dữ liệu cần đọc. Tuy nhiên, nếu một thiết bị liên tục ghi dữ liệu trong nhiều năm, phân vùng của thiết bị đó sẽ tăng rất lớn. Cần cân nhắc cách chia theo thời gian hoặc tiêu chí khác.

## 2. Partition key ghép: nhiều giá trị phối hợp tạo một phân vùng

**Khóa phân vùng ghép** (*composite partition key*) gồm từ hai cột trở lên. Cassandra xem **tổ hợp các giá trị** của chúng là một partition key hoàn chỉnh, rồi tính token dựa trên tổ hợp đó.

Ví dụ, mỗi thiết bị thuộc về một tenant. Cặp `(tenant_id, device_id)` xác định hồ sơ thiết bị trong phạm vi tenant:

```sql
CREATE TABLE device_profile_by_tenant_and_id (
    tenant_id text,
    device_id uuid,
    device_name text,
    firmware_version text,
    PRIMARY KEY ((tenant_id, device_id))
);
```

Hai cặp giá trị sau xác định **hai phân vùng logic khác nhau**:

```text
(tenant_id = 'acme', device_id = D1)  -> partition key ('acme', D1)
(tenant_id = 'beta', device_id = D1)  -> partition key ('beta', D1)
```

Chúng có cùng `device_id` nhưng khác `tenant_id`. Tương tự, hai thiết bị khác nhau trong cùng tenant cũng có partition key khác nhau.

Câu truy vấn phải cung cấp đủ các thành phần để xác định phân vùng:

```sql
SELECT device_name, firmware_version
FROM device_profile_by_tenant_and_id
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

**Không thể hiểu khóa ghép như nhiều khóa độc lập.** Truy vấn chỉ có `tenant_id` không thể suy ra token của một khóa gồm `(tenant_id, device_id)`:

```sql
-- Không xác định được một partition key hoàn chỉnh:
SELECT *
FROM device_profile_by_tenant_and_id
WHERE tenant_id = 'acme';
```

Trong cách truy cập thông thường và khi không có chỉ mục thích hợp, Cassandra không hỗ trợ truy vấn trên mà không phải dùng phương án lọc rộng. Thêm `ALLOW FILTERING` có thể khả thi trong một số trường hợp nhưng thường không phải lựa chọn tốt cho dữ liệu lớn.

### Ghép partition key với clustering column

Một partition key ghép vẫn có thể có nhiều hàng bên trong phân vùng. Ví dụ, lấy lịch sử đo đạc của **một thiết bị, thuộc một tenant, trong một ngày**:

```sql
CREATE TABLE readings_by_tenant_device_day (
    tenant_id text,
    device_id uuid,
    event_day date,
    recorded_at timestamp,
    event_id timeuuid,
    reading double,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        recorded_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (recorded_at DESC, event_id DESC);
```

Ở đây, ba cột **`tenant_id`, `device_id`, `event_day` cùng tạo nên một partition key**. Hai cột `recorded_at` và `event_id` là clustering columns, phân biệt các hàng và quyết định thứ tự trong cùng phân vùng.

```text
Partition A = ('acme', D1, 2026-11-21)
  (08:45, E3) -> reading = 38.1
  (08:30, E2) -> reading = 37.9
  (08:00, E1) -> reading = 37.7

Partition B = ('acme', D1, 2026-11-22)
  (08:10, E4) -> reading = 38.0

Partition C = ('acme', D2, 2026-11-21)
  (09:00, E5) -> reading = 36.5
```

A, B và C là các **phân vùng logic**. Chúng có thể tình cờ nằm trên cùng một node hoặc có tập replica trùng nhau; khác partition key không bảo đảm khác máy chủ.

## 3. Dấu ngoặc trong `PRIMARY KEY` thay đổi ý nghĩa

Đây là lỗi dễ gặp nhất khi chuyển từ SQL quan hệ sang CQL:

| Khai báo | Partition key | Clustering columns |
| --- | --- | --- |
| `PRIMARY KEY (tenant_id)` | `tenant_id` | Không có |
| `PRIMARY KEY (tenant_id, device_id)` | `tenant_id` | `device_id` |
| `PRIMARY KEY ((tenant_id, device_id))` | `(tenant_id, device_id)` | Không có |
| `PRIMARY KEY ((tenant_id, device_id), recorded_at)` | `(tenant_id, device_id)` | `recorded_at` |
| `PRIMARY KEY ((tenant_id, device_id, event_day), recorded_at, event_id)` | `(tenant_id, device_id, event_day)` | `recorded_at`, `event_id` |

Đặc biệt, hai dòng dưới đây **không tương đương**:

```sql
-- Chỉ tenant_id là partition key:
PRIMARY KEY (tenant_id, device_id, recorded_at)

-- tenant_id và device_id tạo partition key ghép:
PRIMARY KEY ((tenant_id, device_id), recorded_at)
```

Ở cách thứ nhất, tất cả thiết bị thuộc cùng tenant chia sẻ **một phân vùng**; `device_id` chỉ giúp sắp xếp và phân biệt hàng trong phân vùng đó. Ở cách thứ hai, mỗi cặp tenant–device có **một phân vùng riêng**, giúp phân tán dữ liệu khi tenant có nhiều thiết bị.

Tên gọi cũng dễ gây nhầm lẫn:

- **Composite partition key**: partition key có nhiều thành phần trong cặp ngoặc trong cùng.
- **Compound primary key**: primary key có partition key và một hoặc nhiều clustering columns.
- Một primary key có thể dùng partition key đơn **hoặc** ghép, có **hoặc không có** clustering columns.

Muốn xác định loại khóa, hãy nhìn **cú pháp dấu ngoặc**, không chỉ đếm số cột xuất hiện sau `PRIMARY KEY`.

## 4. Cassandra phân phối hai loại khóa như thế nào?

Về nguyên tắc, Cassandra mã hóa giá trị partition key rồi dùng *partitioner* (thường là `Murmur3Partitioner`) để tính **token**. Token và chiến lược replication xác định các node chịu trách nhiệm cho phân vùng đó.

```text
Khóa đơn
    device_id = D1
       |
       v
    token(D1) ------------------> Tập replica chịu trách nhiệm

Khóa ghép
    (tenant_id, device_id, event_day)
    ('acme',   D1,        2026-11-21)
       |
       v
    token(tổ hợp cả 3 giá trị) -> Tập replica chịu trách nhiệm
```

Những điểm cần nắm:

1. Cassandra tính token từ **toàn bộ partition key**. Với khóa ghép, không có quy tắc mặc định “lấy token tenant rồi chọn con theo device”.
2. Các hàng có **cùng partition key** thuộc cùng một phân vùng logic. Các hàng ở các phân vùng logic khác nhau có thể có token giống nhau (va chạm) hoặc nằm trên cùng tập replica.
3. Thay đổi một thành phần của partition key tạo **khóa phân vùng mới**, thường có token khác; dữ liệu cũ không tự chuyển sang khóa mới chỉ bằng `UPDATE`.
4. Clustering columns **không tham gia tính token**. Chúng tổ chức dữ liệu bên trong phân vùng.
5. `replication factor` quy định số bản sao theo chiến lược replication; tăng số bản sao không chia nhỏ một phân vùng quá lớn thành nhiều partition key.

Với khóa ghép, **thứ tự cột trong khai báo khóa** là một phần định nghĩa khóa và cần được giữ đúng khi làm việc với schema/token. Ngược lại, thứ tự viết các điều kiện bằng trong mệnh đề `WHERE` không bắt buộc phải trùng thứ tự khai báo, miễn là cung cấp đầy đủ khóa.

## 5. So sánh qua yêu cầu truy vấn thực tế

Việc chọn khóa nên bắt đầu từ **câu hỏi ứng dụng cần trả lời**:

| Yêu cầu | Partition key gợi ý | Clustering columns gợi ý | Điều cần cân nhắc |
| --- | --- | --- | --- |
| Lấy hồ sơ theo `customer_id` | `customer_id` | Không cần | Một hàng cho mỗi khách hàng. |
| Liệt kê thiết bị của một tenant | `tenant_id` | `device_id` | Phân vùng của tenant lớn có thể quá to. |
| Lấy thông tin một thiết bị trong tenant | `(tenant_id, device_id)` | Không cần | Cần biết cả tenant và device. |
| Lấy sự kiện theo thiết bị trong ngày | `(tenant_id, device_id, event_day)` | `recorded_at`, `event_id` | Phải giới hạn bucket ngày và xử lý truy vấn nhiều ngày. |
| Lấy sự kiện mới nhất của mọi thiết bị trong tenant | Cần mô hình truy vấn riêng | Phụ thuộc thứ tự truy cập | Không thể giả định một bảng lịch sử theo thiết bị giải quyết hiệu quả mọi truy vấn tổng hợp. |

### Truy vấn phù hợp với khóa ghép theo ngày

```sql
SELECT recorded_at, event_id, reading
FROM readings_by_tenant_device_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 20;
```

Do partition key đã xác định đầy đủ, Cassandra biết cần đọc phân vùng nào. Vì schema đã khai báo `recorded_at DESC`, các bản ghi mới nhất của ngày xuất hiện trước trong thứ tự clustering.

Truy vấn một khoảng thời gian trong ngày:

```sql
SELECT recorded_at, event_id, reading
FROM readings_by_tenant_device_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND recorded_at >= '2026-11-21T08:00:00+0700'
  AND recorded_at <  '2026-11-21T09:00:00+0700';
```

Điều kiện khoảng này áp dụng lên **clustering column đầu tiên** sau khi đã ràng buộc bằng tất cả thành phần partition key. Với một truy vấn xuyên nhiều ngày, ứng dụng phải xác định các bucket ngày cần đọc rồi tổng hợp kết quả, hoặc sử dụng mô hình dữ liệu riêng cho kiểu truy vấn đó.

### Truy vấn không phù hợp với khóa ghép

```sql
-- Thiếu tenant_id và event_day:
SELECT *
FROM readings_by_tenant_device_day
WHERE device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;

-- Không có bất kỳ thành phần partition key nào:
SELECT *
FROM readings_by_tenant_device_day
WHERE recorded_at >= '2026-11-21T08:00:00+0700';
```

Những truy vấn này không xác định được phân vùng bằng khóa chính. Nếu cần hỗ trợ chúng thường xuyên, nên lập bảng phục vụ truy vấn tương ứng, hoặc cân nhắc công cụ lập chỉ mục phù hợp với phiên bản Cassandra và quy mô dữ liệu. `ALLOW FILTERING` không làm một truy vấn quét rộng tự động trở nên hiệu quả.

## 6. Khi nào khóa đơn trở thành nút thắt?

**Hot partition** xuất hiện khi một partition key nhận quá nhiều tải đọc hoặc ghi; **large partition** xuất hiện khi một partition key chứa quá nhiều dữ liệu. Hai vấn đề có liên quan nhưng không hoàn toàn giống nhau: phân vùng nhỏ vẫn có thể “nóng” vì được truy cập liên tục.

Giả sử một thiết bị sinh **5 sự kiện/phút**, mỗi sự kiện có tải dữ liệu trung bình **1 KiB**, chưa kể metadata, nén hay tombstone. Với tốc độ đều:

| Khoảng thời gian, mỗi thiết bị | Số hàng ước tính | Dung lượng dữ liệu giả định |
| --- | ---: | ---: |
| 1 ngày | 7.200 | Khoảng 7,0 MiB |
| 30 ngày | 216.000 | Khoảng 211 MiB |
| 365 ngày | 2.628.000 | Khoảng 2,51 GiB |

Nếu khóa chỉ là `device_id`, dữ liệu của thiết bị dồn vào một phân vùng và tăng liên tục. Nếu khóa chỉ là `tenant_id`, một tenant với 1.000 thiết bị ở lưu lượng trên có thể dồn khoảng **7,0 GiB/ngày** vào cùng một phân vùng logic.

Thêm bucket `event_day` vào partition key ghép sẽ giới hạn mỗi phân vùng của từng thiết bị vào **một ngày**. Ví dụ:

```sql
-- Dữ liệu của thiết bị tích lũy không giới hạn theo ngày:
PRIMARY KEY (device_id, recorded_at)

-- Mỗi tenant–device–ngày là một phân vùng:
PRIMARY KEY ((tenant_id, device_id, event_day), recorded_at, event_id)
```

Các con số là ví dụ để lập luận, **không phải ngưỡng dung lượng khuyến nghị chung**. Kích thước thực trên SSTable thay đổi theo kiểu cột, số lần ghi/xóa, compression và compaction; mức tải còn phụ thuộc cấu hình node, replica và kiểu truy vấn. Hãy đo cả phân phối kích thước phân vùng lẫn tải thực tế.

## 7. Chọn thành phần của khóa ghép sao cho hợp lý

Một quy trình thiết kế hữu ích:

1. **Liệt kê truy vấn chủ lực.** Ví dụ: “Lấy 20 bản ghi mới nhất của thiết bị D, tenant T, ngày N”.
2. **Xác định các giá trị ứng dụng chắc chắn biết.** Ở ví dụ trên là `tenant_id`, `device_id` và `event_day`.
3. **Đưa các giá trị giúp chọn đúng nhóm dữ liệu vào partition key.** Xem có cần bucket theo ngày hoặc giờ để giới hạn kích thước hay không.
4. **Đưa cột cần sắp xếp/lọc khoảng vào clustering key.** Ví dụ `recorded_at`, sau đó thêm `event_id` ổn định để phân biệt sự kiện trùng thời gian.
5. **Ước lượng số phân vùng, kích thước và lưu lượng từng phân vùng.** Tránh khóa có rất ít giá trị (ví dụ chỉ `region` hoặc chỉ `status`) khi tập dữ liệu lớn.
6. **Kiểm tra các truy vấn khác.** Nếu truy vấn “mọi thiết bị trong tenant” rất thường xuyên, bảng có khóa `(tenant_id, device_id, event_day)` không trực tiếp đáp ứng; cần một đường truy cập khác.

Một số bẫy phổ biến:

| Thiết kế/nhận định | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| `PRIMARY KEY (tenant_id, device_id)` được hiểu là khóa phân vùng ghép | Trên thực tế chỉ `tenant_id` là partition key. | Viết `PRIMARY KEY ((tenant_id, device_id))` nếu muốn khóa ghép và không cần clustering. |
| Khóa ghép `(tenant_id, device_id)` cho phép tìm tất cả device theo `tenant_id` như tìm tiền tố | Hash token dựa trên toàn bộ cặp khóa. | Dùng bảng liệt kê theo tenant hoặc chỉ mục phù hợp. |
| Chỉ dùng `event_day` làm partition key | Toàn bộ thiết bị trong ngày chia sẻ một phân vùng khổng lồ. | Ghép thêm thực thể định danh như tenant và device. |
| Đưa `recorded_at` có độ phân biệt cao vào partition key khi cần đọc cả chuỗi thời gian | Nhiều phân vùng cực nhỏ, khó lấy dải lịch sử. | Đưa timestamp vào clustering key, dùng bucket thời gian ở partition key. |
| Dùng bucket theo ngày nhưng một thiết bị vẫn có lưu lượng rất lớn | Phân vùng một ngày vẫn có thể quá lớn hoặc quá nóng. | Xem xét bucket giờ hoặc shard có kiểm soát, kèm chiến lược truy vấn. |
| `event_day` được tính theo múi giờ khác nhau ở producer và reader | Cùng sự kiện có thể được ghi/tìm ở bucket không nhất quán. | Chuẩn hóa quy tắc tính bucket, ví dụ ngày UTC, và dùng thống nhất ở mọi nơi. |

**Lưu ý về cardinality:** thêm một cột vào khóa ghép không tự động bảo đảm phân bố đều. Nếu cột ấy chỉ có một hoặc vài giá trị đối với phần lớn hàng, hoặc một tổ hợp nhận tải quá cao, hệ thống vẫn có thể gặp hotspot. Khóa phải được chọn theo phân phối dữ liệu và lưu lượng thực tế.

## 8. Dùng partition key ghép từ ứng dụng Java

Ứng dụng Java nên bind **đủ thành phần partition key** trong prepared statement. Ví dụ dưới đây sử dụng API của DataStax/Apache Cassandra Java Driver 4.x; giả định `session` đã kết nối và keyspace đang dùng chứa bảng ví dụ.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.time.LocalDate;
import java.util.UUID;

public class ReadingQueries {
    public static ResultSet latestForDay(
            CqlSession session, String tenantId, UUID deviceId, LocalDate eventDay) {

        PreparedStatement query = session.prepare(
            "SELECT recorded_at, event_id, reading " +
            "FROM readings_by_tenant_device_day " +
            "WHERE tenant_id = ? AND device_id = ? AND event_day = ? " +
            "LIMIT 20"
        );

        return session.execute(query.bind(tenantId, deviceId, eventDay));
    }
}
```

Điều quan trọng ở đây không phải cú pháp Java mà là sự phù hợp giữa truy vấn và schema: **`tenantId` + `deviceId` + `eventDay`** xác định đúng một partition key. Trong ứng dụng thực, hãy chuẩn bị câu lệnh một lần và tái sử dụng `PreparedStatement` thay vì `prepare` mỗi lần gọi; tránh truy vấn thiếu khóa rồi thêm `ALLOW FILTERING` để chữa cháy.

## 9. Tự kiểm tra

Xét schema:

```sql
CREATE TABLE audit_by_tenant_user_month (
    tenant_id text,
    user_id uuid,
    event_month text,
    happened_at timestamp,
    audit_id uuid,
    action text,
    PRIMARY KEY ((tenant_id, user_id, event_month), happened_at, audit_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, audit_id ASC);
```

Hãy trả lời:

1. Partition key là một cột hay khóa ghép? Gồm những cột nào?
2. Hai hàng có cùng tenant và user nhưng khác tháng nằm cùng hay khác phân vùng logic?
3. Muốn đọc lịch sử một tháng của một user, `WHERE tenant_id = ... AND user_id = ...` đã đủ chưa?
4. Nếu thay khai báo thành `PRIMARY KEY (tenant_id, user_id, event_month, happened_at, audit_id)` thì partition key còn là gì?
5. Nếu yêu cầu mới là “liệt kê tất cả sự kiện của mọi user thuộc tenant T trong tháng M”, có nên dùng nguyên bảng này làm truy vấn chính không?

**Đáp án giải thích:**

1. Là partition key ghép ba cột: `tenant_id`, `user_id`, `event_month`.
2. Khác phân vùng, vì `event_month` là thành phần partition key.
3. Chưa đủ: còn thiếu `event_month`. Cần biết tháng, hoặc đọc các tháng liên quan.
4. Chỉ còn `tenant_id` là partition key; bốn cột còn lại là clustering columns.
5. Không phù hợp để truy vấn trực tiếp theo tenant và tháng vì còn thiếu `user_id` trong partition key. Cần bảng/đường truy cập khác theo truy vấn đó.

## 10. Ghi nhớ

- **Khóa phân vùng đơn** có một thành phần, ví dụ `PRIMARY KEY (device_id, recorded_at)` thì `device_id` là partition key.
- **Khóa phân vùng ghép** có từ hai thành phần, ví dụ `PRIMARY KEY ((tenant_id, device_id), recorded_at)` thì partition key là cặp `(tenant_id, device_id)`.
- Cassandra tính token từ **toàn bộ** partition key; mọi hàng cùng giá trị khóa thuộc cùng phân vùng logic, còn clustering columns tổ chức các hàng trong phân vùng.
- Thiết kế bảng Cassandra đi từ **kiểu truy vấn + quy mô dữ liệu + phân bố tải**, rồi mới quyết định partition key đơn hay ghép.
- Thêm thành phần thời gian/bucket vào khóa ghép có thể giới hạn phân vùng đang lớn dần, nhưng làm ứng dụng phải quản lý việc đọc nhiều bucket khi cần.

Lựa chọn partition key là điểm nối giữa mô hình dữ liệu wide-column, cơ chế phân tán/replication và hiệu năng truy vấn CQL. Hiểu rõ khóa đơn và khóa ghép giúp bạn chủ động thiết kế bảng Cassandra cho hệ thống có nhiều tenant, ghi sự kiện liên tục và ứng dụng Java cần độ trễ ổn định.

