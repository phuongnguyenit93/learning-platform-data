# Khóa có độ phân biệt thấp và nguy cơ partition nóng

## Mục tiêu học tập

Trong Apache Cassandra, **partition key** quyết định cách dữ liệu của bảng được phân bố và định tuyến trong cụm. Một khóa chỉ có vài giá trị khác nhau, hoặc có một giá trị nhận phần lớn lưu lượng, có thể khiến một số partition trở nên quá lớn hoặc phải phục vụ quá nhiều truy vấn. Đây là vấn đề quan trọng khi thiết kế bảng theo truy vấn với **Spring Data Cassandra**.

Sau bài này, bạn có thể:

- Giải thích **độ phân biệt (cardinality)** của partition key và phân biệt nó với độ phân bố đều của dữ liệu, lưu lượng.
- Nhận diện vì sao dùng các giá trị như `status`, `country` hoặc `is_active` làm partition key đơn lẻ thường nguy hiểm với bảng lớn.
- Mô tả **hot partition**, **large partition** và **hot node**, cùng mối quan hệ nhưng không đồng nhất giữa chúng.
- Thiết kế partition key tổng hợp, time bucket hoặc shard theo cách vẫn phục vụ được truy vấn CQL.
- Đánh giá chi phí của giải pháp: tăng số partition có thể giúp phân tán tải nhưng làm đọc và paging phức tạp hơn.
- Áp dụng các quyết định này vào entity mapping, repository và `CassandraTemplate` trong Spring Data Cassandra.

## 1. Partition key liên quan gì đến độ phân biệt?

Trong Cassandra, một bảng được chia thành các **partition**. Các hàng có cùng **toàn bộ giá trị partition key** thuộc cùng một partition logic. Cassandra dùng partitioner để tính **token** từ partition key; token cùng chiến lược replication quyết định các replica chịu trách nhiệm cho partition đó.

**Độ phân biệt của khóa** là số lượng giá trị partition key **khác nhau** xuất hiện trong tập dữ liệu. Với partition key tổng hợp, phải đếm số lượng **tổ hợp đầy đủ**, không đếm riêng từng cột:

```text
PRIMARY KEY (status, created_at, order_id)
  -> Partition key: status
  -> Ví dụ 4 trạng thái: chỉ khoảng 4 partition cho toàn bảng.

PRIMARY KEY ((tenant_id, status), created_at, order_id)
  -> Partition key: (tenant_id, status)
  -> Mỗi tenant có tối đa một partition cho mỗi trạng thái.

PRIMARY KEY ((tenant_id, status, bucket_day, shard), created_at, order_id)
  -> Partition key: (tenant_id, status, bucket_day, shard)
  -> Một trạng thái của một tenant được chia theo ngày và shard.
```

Các ví dụ trên chỉ minh họa **phần khai báo khóa chính** trong một lệnh `CREATE TABLE`. `created_at` và `order_id` là **clustering columns**: chúng phân biệt và sắp thứ tự hàng **bên trong partition**, nhưng **không tạo thêm partition**.

Điều này dẫn đến một lỗi thiết kế thường gặp: thêm rất nhiều clustering columns rồi nghĩ rằng dữ liệu đã được phân tán sang nhiều node. Nếu partition key không đổi, các hàng mới vẫn đi vào cùng partition logic.

### Độ phân biệt thấp không tự động đồng nghĩa với lỗi

Một bảng vài trăm hàng, đọc thưa thớt, có partition key ít giá trị vẫn có thể đáp ứng yêu cầu. Nguy cơ xuất hiện khi có thêm những yếu tố như:

- **Nhiều hàng trên mỗi khóa:** dữ liệu dồn vào một partition lớn.
- **Nhiều request tập trung vào một khóa:** một partition nhận phần lớn tải đọc/ghi.
- **Phân bố lệch:** một giá trị, chẳng hạn `PENDING`, chiếm phần lớn dữ liệu; các giá trị còn lại ít sử dụng.
- **Tăng trưởng không giới hạn:** partition tiếp tục lớn lên vì dữ liệu không được chia theo thời gian hoặc không có chính sách vòng đời phù hợp.

Vì vậy, cần xem cả **cardinality**, **kích thước partition**, **mức lệch tải** và **mẫu truy vấn**. Số lượng giá trị khóa chỉ là một tín hiệu ban đầu.

## 2. Vì sao một partition có thể thành điểm nóng trong hệ phân tán?

Giả sử cụm Cassandra có nhiều node và keyspace dùng replication factor phù hợp. Một partition key, ví dụ `(tenant=T1, status=PENDING)`, được băm ra một token. Cassandra xác định một **tập replica** chịu trách nhiệm cho token đó.

```text
Các yêu cầu đến bảng orders_by_status:

  (T1, PENDING) ─┐
  (T1, PENDING) ─┼──> Cùng một partition key
  (T1, PENDING) ─┘                │
                                 v
                       Token của partition
                                 │
                                 v
                       Tập replica phụ trách
                       (ví dụ N2, N5, N8)

  (T1, SHIPPED) ──────> Token khác, tập replica có thể khác
```

Replication giúp tăng khả dụng và hỗ trợ các lựa chọn consistency level, nhưng **không làm mỗi hàng thuộc một partition được rải độc lập khắp tất cả node**. Một partition nóng vẫn tập trung công việc trên tập replica chịu trách nhiệm; thêm node vào cụm không đảm bảo giảm tải cho partition này.

### Ba khái niệm cần tách biệt

| Khái niệm | Dấu hiệu | Nguyên nhân tiêu biểu |
| --- | --- | --- |
| **Large partition** | Một partition chứa rất nhiều hàng hoặc có kích thước rất lớn. | Khóa có ít giá trị; không chia bucket; dữ liệu tích lũy lâu dài. |
| **Hot partition** | Một partition nhận lượng đọc/ghi quá lớn so với khả năng phục vụ mong muốn. | Nhiều request cùng một khóa; “khóa nổi tiếng”; lưu lượng tập trung trong khoảng thời gian ngắn. |
| **Hot node** | Một node chịu nhiều CPU, I/O, network hoặc request hơn các node khác. | Có thể do một hoặc nhiều hot partition, phân bố dữ liệu/tải lệch hay các nguyên nhân vận hành khác. |

Một partition có thể **nhỏ nhưng nóng** khi liên tục bị đọc/ghi. Một partition cũng có thể **lớn nhưng ít được truy cập**; dù vậy, nó vẫn ảnh hưởng đến các hoạt động đọc, streaming, compaction hoặc sửa chữa dữ liệu khi cần. Hai hiện tượng có liên hệ nhưng không thể dùng một số đo thay thế cho số đo còn lại.

## 3. Ví dụ dễ mắc lỗi: gom mọi đơn hàng theo trạng thái

Giả sử một ứng dụng nhiều tenant có dashboard “Hiển thị 50 đơn hàng `PENDING` mới nhất của tenant hiện tại”. Request luôn có `tenant_id` và `status`.

Một thiết kế ban đầu có thể là:

```sql
CREATE TABLE orders_by_status_bad (
    tenant_id uuid,
    status text,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    total_amount_cents bigint,
    PRIMARY KEY ((tenant_id, status), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

Đọc dữ liệu:

```sql
SELECT created_at, order_id, customer_id, total_amount_cents
FROM orders_by_status_bad
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND status = 'PENDING'
LIMIT 50;
```

Truy vấn **hợp lệ và thuận theo khóa**: biết đủ partition key, kết quả được sắp theo `created_at DESC` trong partition. Vấn đề nằm ở **dòng dữ liệu đổ về partition**.

Với tenant lớn, tất cả đơn đang ở trạng thái `PENDING` cùng chia sẻ partition key `(tenant_id, 'PENDING')`. Không quan trọng `order_id` có hàng triệu giá trị hay `created_at` khác nhau: chúng đều là clustering columns.

Nếu có một triệu hàng đang nằm trong partition này, giả sử mỗi hàng chứa khoảng 500 byte dữ liệu nghiệp vụ, riêng phần dữ liệu minh họa đã khoảng:

```text
1.000.000 hàng × 500 byte/hàng ≈ 500 MB dữ liệu logic
```

Đây **không phải phép đo kích thước SSTable**; giá trị thực còn phụ thuộc định dạng lưu trữ, overhead, compression, tombstone và nhiều yếu tố khác. Con số cho thấy chỉ một partition đã có thể chứa lượng dữ liệu đáng kể.

Hệ quả tiềm ẩn:

1. Các lượt đọc danh sách `PENDING` liên tục chạm cùng partition; nhiều người dùng dashboard có thể tạo **hot read partition**.
2. Nếu có nhiều đơn được tạo hoặc cập nhật cùng trạng thái, các ghi tập trung vào cùng partition; các replica tương ứng nhận phần lớn tải ghi.
3. Việc chuyển đơn từ `PENDING` sang trạng thái khác kéo theo xử lý bản ghi ở partition trạng thái cũ và mới. Xóa các entry cũ có thể tạo **tombstone**.
4. `LIMIT 50` giới hạn số hàng kết quả, **không** giải quyết vấn đề partition quá lớn hoặc tải đồng thời trên cùng khóa.

**Điểm then chốt:** `PRIMARY KEY ((tenant_id, status), created_at, order_id)` có thể rất tốt về mặt cú pháp và đúng một truy vấn cụ thể, nhưng vẫn không đáp ứng yêu cầu mở rộng khi lưu lượng hoặc dữ liệu tập trung vào ít partition.

## 4. Chẩn đoán nguyên nhân trước khi đổi khóa

Trước khi thêm nhiều cột vào partition key, cần xác định **dạng quá tải nào đang xảy ra**.

| Quan sát thực tế | Câu hỏi cần trả lời | Hướng xem xét |
| --- | --- | --- |
| Partition tăng lớn qua nhiều tháng | Có phải dữ liệu đang tích lũy mãi dưới cùng khóa? | Time bucket, TTL/chính sách giữ dữ liệu, bảng theo khoảng thời gian. |
| Nhiều yêu cầu đọc một khóa `PENDING` | Đọc có dồn vào một nhóm nhỏ khóa không? | Phân shard, caching phù hợp, tóm tắt hoặc tiền tính toán kết quả. |
| Dữ liệu không quá lớn nhưng ghi đột biến | Có nhiều sự kiện cùng cập nhật một partition trong thời gian ngắn không? | Phân chia theo khóa ổn định và kiểm soát tốc độ ghi. |
| Một vài tenant áp đảo toàn hệ thống | Tenant đã là một phần của partition key nhưng vẫn nóng? | Xem xét thêm bucket/shard ở tenant đó; đánh giá mức lệch. |
| Truy vấn chậm khi lọc cột không thuộc khóa | Có đang quét/lọc nhiều dữ liệu rồi mới trả vài hàng? | Thiết kế lại bảng theo truy vấn, không mặc định dùng `ALLOW FILTERING`. |

Trong Cassandra, một số lỗi có thể cùng tồn tại. Chẳng hạn, trạng thái `PENDING` là khóa nóng vì dashboard đọc liên tục, đồng thời cũng là partition lớn vì đơn lâu chưa xử lý.

## 5. Kỹ thuật thứ nhất: tăng tính phân biệt bằng dữ liệu đã có trong truy vấn

Cách đơn giản nhất là bổ sung vào partition key một thuộc tính mà **request luôn biết** và có khả năng chia dữ liệu thành những nhóm hợp lý.

Ví dụ:

- Truy vấn dữ liệu **theo người dùng**: cân nhắc `(tenant_id, user_id)` thay vì chỉ `tenant_id`.
- Truy vấn dữ liệu **theo cửa hàng**: cân nhắc `(tenant_id, store_id)` nếu request có `store_id`.
- Truy vấn dữ liệu **theo đơn hàng**: cân nhắc `(tenant_id, order_id)` nếu cần toàn bộ dòng hàng của một đơn.

Tuy nhiên, không nên thêm cột chỉ vì nó nhiều giá trị. Khi partition key là `(tenant_id, status, user_id)`, một API chỉ biết `tenant_id` và `status` sẽ **không** thể đọc một partition duy nhất cho mọi người dùng. API phải biết `user_id` hoặc thay đổi cách lấy dữ liệu.

Nguyên tắc: **cardinality tốt hơn chỉ có giá trị khi vẫn truy vấn được theo khóa và lượng dữ liệu mỗi partition hợp lý**. Mẫu truy cập của ứng dụng quyết định cách kết hợp các cột.

## 6. Kỹ thuật thứ hai: chia partition theo thời gian (time bucket)

Nếu ứng dụng thường đọc đơn theo ngày, có thể thêm `bucket_day` vào partition key:

```sql
CREATE TABLE orders_by_status_day (
    tenant_id uuid,
    status text,
    bucket_day date,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    PRIMARY KEY ((tenant_id, status, bucket_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

Thay vì một partition `(T1, PENDING)` tích lũy vô hạn, giờ có các partition:

```text
(T1, PENDING, 2026-11-23)
(T1, PENDING, 2026-11-24)
(T1, PENDING, 2026-11-25)
...
```

Truy vấn một ngày:

```sql
SELECT created_at, order_id, customer_id
FROM orders_by_status_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND status = 'PENDING'
  AND bucket_day = '2026-11-25'
LIMIT 50;
```

Ưu điểm: giới hạn dữ liệu gom theo một khoảng thời gian. Đánh đổi: một dashboard muốn “50 đơn gần nhất **không giới hạn ngày**” cần lần lượt truy vấn các bucket phù hợp; không thể bỏ `bucket_day` khỏi `WHERE` rồi kỳ vọng Cassandra tự đọc toàn bộ theo thứ tự thời gian.

**Cần phân biệt hai mục tiêu**:

- Với **bảng sự kiện bất biến**, bucket thường tính từ thời điểm sự kiện và không đổi.
- Với **bảng biểu diễn trạng thái hiện tại**, nếu đơn vẫn `PENDING` qua nhiều ngày, bucket theo **ngày tạo đơn** không tự động chuyển nó sang bucket “hôm nay”. Dashboard cần biết phải đọc những ngày nào. Nếu muốn nhóm theo ngày trạng thái thay đổi, việc đổi bucket đồng nghĩa với việc chuyển entry sang partition mới, không đơn giản là sửa một regular column.

Chọn ngày, giờ hay tháng phải dựa trên tần suất, khối lượng và cửa sổ thời gian mà API thực sự đọc.

## 7. Kỹ thuật thứ ba: phân shard cho một nhóm vẫn quá nóng

Time bucket có thể vẫn chưa đủ. Một tenant lớn có thể phát sinh hàng trăm nghìn đơn trong cùng ngày và trạng thái `PENDING`.

Khi đó, dùng thêm **shard** (còn gọi là *salt bucket*) để chia một nhóm logic thành nhiều partition vật lý.

### 7.1. Schema có cả time bucket và shard

```sql
CREATE TABLE orders_by_status_day_shard (
    tenant_id uuid,
    status text,
    bucket_day date,
    shard int,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    total_amount_cents bigint,
    PRIMARY KEY ((tenant_id, status, bucket_day, shard), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

Giả sử ứng dụng định nghĩa `SHARD_COUNT = 16`. Các đơn của cùng tenant, trạng thái và ngày được chia vào shard từ `0` đến `15`:

```text
Tenant T1 / PENDING / 2026-11-25
  shard 0  -> Partition (T1, PENDING, 2026-11-25, 0)
  shard 1  -> Partition (T1, PENDING, 2026-11-25, 1)
  ...
  shard 15 -> Partition (T1, PENDING, 2026-11-25, 15)
```

Các partition giờ có các giá trị partition key khác nhau; partitioner có thể phân bố chúng vào những token và tập replica khác nhau. Sự phân tán tải thực tế còn phụ thuộc phân phối giá trị, topology và lượng truy cập.

### 7.2. Gán shard một cách ổn định

Một cách đơn giản là lấy shard từ hàm băm của `order_id`:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

public final class OrderPartitioning {
    private static final int SHARD_COUNT = 16;

    public static int shardFor(UUID orderId) {
        // Minh họa: UUID.hashCode() ổn định cho cùng giá trị UUID.
        return Math.floorMod(orderId.hashCode(), SHARD_COUNT);
    }

    public static LocalDate dayBucket(Instant createdAt) {
        return createdAt.atZone(ZoneOffset.UTC).toLocalDate();
    }

    private OrderPartitioning() {}
}
```

Lợi ích của shard tính từ mã đơn:

- Cùng `order_id` luôn chọn lại cùng shard khi retry, miễn là **thuật toán và số shard giữ nguyên**.
- Hai đơn khác nhau có xu hướng rơi vào các shard khác nhau khi giá trị định danh được phân bố tốt.
- Ứng dụng có thể tính shard khi cần cập nhật hoặc xóa entry của một đơn, nếu đã biết `order_id` và các thành phần khóa còn lại.

Đây là ví dụ thuật toán, không phải yêu cầu bắt buộc phải dùng `UUID.hashCode()`. Hệ thống thực cần thống nhất hàm băm giữa các service/ngôn ngữ và kiểm tra phân bố tải. Không được tùy tiện đổi `SHARD_COUNT` từ 16 sang 32 đối với dữ liệu cũ: việc đọc, cập nhật hoặc xóa có thể tìm sai shard. Nếu cần thay đổi, hãy có phiên bản chiến lược, kế hoạch di chuyển hoặc metadata xác định shard áp dụng cho từng nhóm dữ liệu.

### 7.3. Ghi và đọc một shard

Với `SHARD_COUNT = 16` và `order_id` bên dưới, phép tính `Math.floorMod(orderId.hashCode(), 16)` cho ra `shard = 0`:

```sql
INSERT INTO orders_by_status_day_shard (
    tenant_id, status, bucket_day, shard,
    created_at, order_id, customer_id, total_amount_cents
) VALUES (
    11111111-1111-4111-8111-111111111111,
    'PENDING', '2026-11-25', 0,
    '2026-11-25T08:15:00Z',
    22222222-2222-4222-8222-222222222222,
    33333333-3333-4333-8333-333333333333,
    250000
);

SELECT created_at, order_id, customer_id, total_amount_cents
FROM orders_by_status_day_shard
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND status = 'PENDING'
  AND bucket_day = '2026-11-25'
  AND shard = 0
LIMIT 50;
```

Truy vấn trên chỉ trả **50 hàng mới nhất của shard 0**, không phải 50 đơn mới nhất của **toàn bộ 16 shard**.

### 7.4. Trả 50 đơn mới nhất khi dữ liệu ở nhiều shard

Nếu dashboard cần 50 đơn mới nhất trong **một ngày và một trạng thái**, ứng dụng có thể:

1. Gửi tối đa 16 truy vấn theo các shard `0..15` với cùng `tenant_id`, `status` và `bucket_day`.
2. Lấy một số hàng đầu từ mỗi shard theo thứ tự `created_at DESC, order_id ASC`; để xác định top 50 của một ngày, 50 hàng đầu mỗi shard là một giới hạn đủ cho phép hợp nhất chính xác về thứ tự trên tập dữ liệu đã đọc.
3. **Hợp nhất có thứ tự** (*k-way merge*) các luồng, so sánh cả `created_at` lẫn `order_id` để xử lý trường hợp trùng timestamp.
4. Trả 50 hàng đầu của kết quả hợp nhất, đồng thời giữ trạng thái phân trang của từng luồng nếu cần đọc tiếp.

```text
Shard 0:  [09:10] [09:01] [08:40] ...
Shard 1:  [09:12] [09:00] [08:55] ...
Shard 2:  [09:08] [09:02] [08:48] ...
...
             \      |      /
              K-way merge
                   |
            50 đơn mới nhất
```

Chi phí phát sinh rất rõ: chia 1 partition thành 16 có thể giảm tải trên mỗi partition, nhưng một trang dashboard có thể phát sinh 16 truy vấn. Độ trễ sẽ phụ thuộc cả shard chậm nhất, mức song song, số hàng lấy dư và chi phí ghép kết quả.

Đối với paging nhiều shard, **một paging state của một truy vấn Cassandra không đại diện cho toàn bộ tập kết quả đã hợp nhất**. Ứng dụng cần quản lý cursor/trạng thái đọc riêng cho từng shard cùng quy tắc merge ổn định; việc thêm hoặc xóa dữ liệu giữa các trang cũng ảnh hưởng thứ tự quan sát được. Khi số shard lớn, hãy cân nhắc hạn chế cửa sổ thời gian, cache hoặc cách nhìn được tiền tính toán nếu phù hợp.

### 7.5. Chọn số shard thế nào?

Không có số shard mặc định đúng cho mọi hệ thống. Có thể bắt đầu từ mục tiêu **giới hạn kích thước partition** và **giới hạn tải mỗi partition**, sau đó đo thực tế.

Ví dụ minh họa: một nhóm tenant/trạng thái/ngày có khoảng **1.000.000 hàng**, dữ liệu nghiệp vụ trung bình **500 byte/hàng**. Nếu phân đều vào 16 shard:

```text
Trước khi chia: 1.000.000 hàng × 500 B ≈ 500 MB logic / partition

Sau khi chia 16 shard (giả sử phân bố đều):
  1.000.000 / 16 = 62.500 hàng / partition
  500 MB / 16 ≈ 31,25 MB dữ liệu logic / partition
```

Đây chỉ là **ước lượng số lượng hàng và payload**, không phải ngưỡng kích thước “an toàn” hay phép đo dung lượng lưu trữ thật. Một partition 31 MB vẫn có thể quá nóng nếu nhận lưu lượng lớn; ngược lại, 16 shard có thể tạo fan-out quá đắt cho API. Hãy kiểm chứng bằng số liệu và thử tải đại diện.

## 8. Các đánh đổi thường bị bỏ sót

### 8.1. Khóa có tính phân biệt cao nhưng vẫn lệch tải

Thêm `tenant_id` có thể tạo rất nhiều partition trên toàn hệ thống, nhưng nếu một tenant chiếm 90% yêu cầu, partition của tenant đó vẫn nóng. **Cardinality cao không bảo đảm phân bố lưu lượng đều**.

Tương tự, khóa theo ngày có thể phân tán dữ liệu lịch sử nhưng gần như mọi request ghi hôm nay đều hướng vào bucket hiện tại. Đó là lý do đôi khi cần thêm shard hoặc phân đoạn theo một thuộc tính nghiệp vụ phù hợp.

### 8.2. Random shard giúp ghi nhưng làm đọc khó

Gán shard ngẫu nhiên khi ghi có thể phân tán các sự kiện, nhưng nếu không lưu hoặc tính lại được shard, một yêu cầu truy cập **một sự kiện cụ thể** sẽ không biết nên đến partition nào. Shard băm ổn định theo định danh thường thuận lợi hơn cho retry và cập nhật.

Tuy nhiên, nếu truy vấn chủ yếu là **top N toàn bộ nhóm**, bất kỳ shard nào cũng có thể chứa phần tử mới nhất: phải fan-out hoặc duy trì cách nhìn khác. Hãy đánh giá cả đường ghi và đường đọc trước khi chọn shard.

### 8.3. Khóa thay đổi đồng nghĩa với chuyển partition

Trong bảng `orders_by_status_day_shard`, `status` thuộc partition key. Cassandra **không cập nhật partition key tại chỗ** bằng `UPDATE ... SET status = ...`. Khi đơn chuyển từ `PENDING` sang `SHIPPED`, phải:

1. Xác định khóa entry cũ, gồm `tenant_id`, trạng thái cũ, bucket, shard, `created_at` và `order_id`.
2. Ghi entry ở partition có trạng thái mới (nếu dashboard trạng thái mới cần hiển thị đơn).
3. Xóa entry ở partition trạng thái cũ và xử lý khả năng thao tác bị lỗi giữa chừng.

Ví dụ minh họa các thao tác CQL:

```sql
INSERT INTO orders_by_status_day_shard (
    tenant_id, status, bucket_day, shard,
    created_at, order_id, customer_id, total_amount_cents
) VALUES (
    11111111-1111-4111-8111-111111111111,
    'SHIPPED', '2026-11-25', 0,
    '2026-11-25T08:15:00Z',
    22222222-2222-4222-8222-222222222222,
    33333333-3333-4333-8333-333333333333,
    250000
);

DELETE FROM orders_by_status_day_shard
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND status = 'PENDING'
  AND bucket_day = '2026-11-25'
  AND shard = 0
  AND created_at = '2026-11-25T08:15:00Z'
  AND order_id = 22222222-2222-4222-8222-222222222222;
```

Hai thao tác này cần cơ chế nghiệp vụ thích hợp để xử lý ghi một phần và retry; không nên xem chúng như một giao dịch quan hệ được cách ly. Xóa trong Cassandra có thể tạo **tombstone**; bảng có nhiều lần chuyển trạng thái cần quan tâm đến lượng tombstone và chính sách vòng đời.

### 8.4. Không phải vấn đề nào cũng giải quyết bằng thêm partition

| Phương án | Khi phù hợp | Chi phí hoặc giới hạn |
| --- | --- | --- |
| **Bổ sung thuộc tính nghiệp vụ vào khóa** | Request đã biết thuộc tính, ví dụ `user_id` hoặc `store_id`. | Truy vấn thiếu thuộc tính đó có thể cần bảng khác. |
| **Time bucket** | Dữ liệu có chiều thời gian; truy vấn thường giới hạn theo thời gian. | Truy vấn xuyên bucket phải tổng hợp nhiều kết quả. |
| **Hash shard** | Một khóa logic còn quá nhiều dữ liệu hoặc tải sau khi chia bucket. | Đọc toàn nhóm cần fan-out; phải ổn định thuật toán shard. |
| **Bảng tóm tắt theo truy vấn** | Dashboard chỉ cần số liệu tổng hợp hoặc vài bản ghi nổi bật. | Phải duy trì dữ liệu dẫn xuất và xử lý chậm đồng bộ. |
| **Cache thích hợp** | Nhiều lượt đọc lặp lại cùng kết quả, chấp nhận độ trễ cập nhật. | Invalidating cache, dữ liệu cũ và tải lúc cache miss. |
| **Giới hạn giữ dữ liệu/TTL** | Dữ liệu lịch sử có thời hạn nghiệp vụ rõ ràng. | TTL tạo tombstone; không giải quyết hoàn toàn hot write. |

Việc tạo chỉ mục hay dùng `ALLOW FILTERING` không tự biến partition nóng thành nhiều partition độc lập. Index có thể hỗ trợ một số truy vấn cụ thể tùy phiên bản và loại chỉ mục, nhưng vẫn cần đánh giá đường đọc, chi phí ghi và phân bố tải.

## 9. Liên hệ với Spring Data Cassandra

Spring Data Cassandra cung cấp **entity mapping**, **repository**, `CassandraTemplate` và hỗ trợ truy vấn CQL. Các API này giúp viết ứng dụng Java gọn hơn, nhưng **không thay đổi quy tắc định tuyến partition** của Cassandra.

### 9.1. Ánh xạ đúng các thành phần của khóa

Với bảng `orders_by_status_day_shard`, lớp khóa tổng hợp nên mô tả chính xác hai nhóm:

- **Partition key columns:** `tenant_id`, `status`, `bucket_day`, `shard`.
- **Clustering columns:** `created_at`, `order_id`.

Trong mapping có thể dùng `@PrimaryKeyClass` và `@PrimaryKeyColumn` với `PrimaryKeyType.PARTITIONED` hoặc `PrimaryKeyType.CLUSTERED`, cùng `ordinal` để xác định thứ tự. Entity chứa một thuộc tính `@PrimaryKey` trỏ tới lớp khóa đó.

Ví dụ cấu trúc mapping rút gọn:

```java
@PrimaryKeyClass
public class OrderStatusKey implements Serializable {

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "status", ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private String status;

    @PrimaryKeyColumn(name = "bucket_day", ordinal = 2,
        type = PrimaryKeyType.PARTITIONED)
    private LocalDate bucketDay;

    @PrimaryKeyColumn(name = "shard", ordinal = 3,
        type = PrimaryKeyType.PARTITIONED)
    private Integer shard;

    @PrimaryKeyColumn(name = "created_at", ordinal = 4,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant createdAt;

    @PrimaryKeyColumn(name = "order_id", ordinal = 5,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.ASCENDING)
    private UUID orderId;

    // Thêm constructor, getters/setters và equals/hashCode theo quy ước dự án.
}
```

Đây là **khung minh họa**, chưa phải một lớp Java hoàn chỉnh để biên dịch độc lập: cần import các annotation, kiểu dữ liệu và phần triển khai đối tượng khóa. Điều quan trọng nhất là phân biệt đúng các thành phần `PARTITIONED` và `CLUSTERED`.

### 9.2. Repository chỉ truy vấn một shard khi có đủ khóa

Ví dụ truy vấn từ một repository đã ánh xạ entity `OrderStatusRow` và khóa `OrderStatusKey`:

```java
public interface OrderStatusRepository
        extends CassandraRepository<OrderStatusRow, OrderStatusKey> {

    @Query("""
        SELECT *
        FROM orders_by_status_day_shard
        WHERE tenant_id = ?0
          AND status = ?1
          AND bucket_day = ?2
          AND shard = ?3
        LIMIT ?4
        """)
    List<OrderStatusRow> findLatestInShard(
        UUID tenantId,
        String status,
        LocalDate bucketDay,
        int shard,
        int limit
    );
}
```

Phương thức này phải có đủ `tenant_id`, `status`, `bucket_day` và `shard`. Spring Data không tự hợp nhất kết quả từ 16 shard; service của ứng dụng phải điều phối truy vấn và merge khi cần danh sách toàn nhóm. Đối với tập kết quả lớn, cần thiết kế paging/cursor phù hợp thay vì tải tất cả vào một `List`.

Với `CassandraTemplate` hoặc prepared CQL cũng vậy: bind tham số giúp xây dựng truy vấn an toàn và rõ ràng, nhưng không loại bỏ chi phí fan-out. Nếu nghiệp vụ thường xuyên truy vấn đơn theo `order_id`, hãy có bảng/đường truy cập theo mã đơn thay vì tìm ngược qua mọi shard của bảng dashboard.

### 9.3. Consistency level không chữa được hot partition

Cassandra cho phép lựa chọn consistency level khi đọc/ghi, ví dụ `LOCAL_QUORUM` khi topology và replication factor phù hợp. Consistency level ảnh hưởng số replica phải phản hồi, độ trễ và khả dụng. **Tăng consistency level không làm một partition được tự động phân nhỏ** hoặc biến truy vấn thiếu partition key thành truy vấn hiệu quả.

Với dữ liệu nhân bản ở nhiều bảng để phục vụ các cách đọc khác nhau, còn phải thiết kế retry, idempotency và đối soát. Việc cập nhật hai bảng không trở thành một giao dịch ACID có cách ly đầy đủ chỉ nhờ dùng cùng repository hoặc `CassandraTemplate`.

## 10. Cách kiểm chứng thiết kế bằng số liệu

Đừng đặt ra một ngưỡng chung như “partition dưới X MB thì luôn an toàn” hoặc “phải có ít nhất Y shard”. Ngưỡng thực tế phụ thuộc phần cứng, workload, kích thước hàng, consistency level, số replica, compaction và tỷ lệ đọc/ghi.

### Checklist trước khi triển khai

1. **Liệt kê mẫu truy vấn:** mỗi API biết những cột nào của partition key? Có cần đọc nhiều bucket/shard không?
2. **Ước lượng cardinality thật:** số tổ hợp partition key đầy đủ, không chỉ số giá trị của từng cột.
3. **Đo mức lệch:** nhóm nào chiếm nhiều dữ liệu, read QPS và write QPS nhất? Xem cả giờ cao điểm.
4. **Ước lượng tăng trưởng:** số hàng và payload theo một partition trong ngày/giờ/tháng; tính tác động TTL và xóa.
5. **Kiểm thử đọc:** độ trễ phân vị như p95/p99, lượng dữ liệu đọc, số truy vấn khi fan-out, paging qua nhiều shard.
6. **Kiểm thử ghi:** thông lượng, độ trễ, timeout, yêu cầu retry, độ lệch dữ liệu nếu trạng thái thay đổi và cần chuyển partition.
7. **Quan sát vận hành:** phân bố tải trên replica/node, histogram kích thước partition, tombstone, compaction và cảnh báo về partition lớn.
8. **Ghi nhận chiến lược shard:** hàm băm, số shard, time bucket, múi giờ, kế hoạch khi thay đổi schema.

Các công cụ/nguồn quan sát thường dùng gồm driver metrics, số liệu giám sát cụm, thống kê bảng và phân bố partition từ công cụ quản trị Cassandra phù hợp với phiên bản. Với truy vấn đáng ngờ, có thể dùng tracing có kiểm soát để hiểu đường thực thi. Cần đánh giá bằng **dữ liệu và lưu lượng đại diện**, vì thử nghiệm trên vài trăm dòng không bộc lộ vấn đề skew ở tenant lớn.

### Dấu hiệu bản thiết kế cần xem lại

- Tăng số node nhưng một nhóm request vẫn chậm do cùng một khóa nóng.
- Một vài partition lớn vượt trội so với phần còn lại.
- Dashboard đọc cùng dữ liệu quá thường xuyên, trong khi chi phí fan-out hoặc tombstone tăng mạnh.
- Thêm shard khiến độ trễ tổng hợp vượt yêu cầu của UI dù write latency giảm.
- Việc chuyển trạng thái để lại dữ liệu cũ tại partition trước do retry/đối soát chưa đầy đủ.

Những tín hiệu này giúp quyết định nên **điều chỉnh bucket/shard, giới hạn cửa sổ đọc, tạo bảng tóm tắt, hay thay đổi luồng ghi**, thay vì mặc định thêm cột vào partition key.

## 11. Bài tập vận dụng

**Tình huống A — Cờ boolean:** Bảng lưu sự kiện theo `PRIMARY KEY (is_processed, created_at, event_id)`, trong đó `is_processed` chỉ có hai giá trị. Mỗi ngày có hàng triệu sự kiện mới và worker thường đọc sự kiện chưa xử lý.

**Câu hỏi:** Có bao nhiêu giá trị partition key tối đa? Vì sao `event_id` không giúp phân bố sự kiện? Nếu chia theo ngày, worker cần thay đổi cách đọc ra sao?

**Gợi ý:** Chỉ có tối đa hai partition vì `is_processed` là partition key đơn; `created_at` và `event_id` chỉ là clustering columns. Chia theo ngày thêm nhiều partition nhưng worker phải biết bucket cần xử lý. Với tốc độ ghi lớn, có thể cần shard trong bucket và cơ chế đọc/điều phối trên nhiều shard, đồng thời quản lý việc chuyển trạng thái và tombstone.

**Tình huống B — Tenant lớn:** Một hệ thống có 10.000 tenant nhưng 95% truy vấn tập trung ở một tenant. Partition key là `(tenant_id, status)`.

**Câu hỏi:** Vì sao số lượng tenant lớn chưa bảo đảm tránh hot partition?

**Gợi ý:** Số partition lý thuyết có thể lớn, nhưng workload thực tế lệch mạnh. Các trạng thái của tenant lớn vẫn nhận phần lớn tải. Cần đo QPS/kích thước theo **từng tổ hợp khóa** và cân nhắc time bucket, shard, cache hoặc bảng tóm tắt theo yêu cầu truy vấn.

**Tình huống C — Đánh đổi đọc/ghi:** API cần 100 bản ghi mới nhất theo `tenant_id + status` trong vòng một ngày. Bạn định dùng 32 shard.

**Câu hỏi:** Lợi ích gì khi ghi? Đọc phải trả thêm chi phí nào? Có nên mặc định tăng lên 256 shard?

**Gợi ý:** Các ghi có thể phân bổ qua nhiều partition, giảm tập trung trên một khóa. Đọc toàn ngày cần truy vấn nhiều shard và merge kết quả, xử lý cursor riêng, độ trễ và giới hạn song song. Tăng lên 256 shard mà chưa đo có thể làm fan-out đắt hơn lợi ích phân tán ghi.

## Tổng kết

Một partition key có **độ phân biệt thấp** khiến dữ liệu và yêu cầu truy cập dễ tập trung vào ít partition; khi một hoặc vài khóa nhận quá nhiều tải, xuất hiện **hot partition**. Cassandra phân bố theo **toàn bộ partition key**, còn clustering columns chỉ tổ chức dữ liệu **bên trong partition**. Replication cải thiện khả dụng và hỗ trợ consistency, nhưng không tự chia tải của một khóa nóng ra toàn cụm.

Giải pháp thường là chọn thêm chiều phân vùng mà request đã biết, chia theo thời gian hoặc shard ổn định, đồng thời cân bằng **khả năng phân tán ghi** với **chi phí đọc và paging qua nhiều partition**. Khi triển khai bằng Spring Data Cassandra, entity mapping, repository và `CassandraTemplate` phải phản ánh đúng khóa CQL; hiệu năng thực tế vẫn phụ thuộc vào mô hình partition và đặc điểm workload.
