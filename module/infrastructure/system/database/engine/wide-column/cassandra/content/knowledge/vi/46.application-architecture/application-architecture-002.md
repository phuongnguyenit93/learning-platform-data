# Tách đường ghi nghiệp vụ khỏi bảng đọc theo truy vấn

## 1. Vấn đề kiến trúc cần giải quyết

Trong hệ thống xử lý đơn hàng, thao tác **đặt hàng**, **xác nhận thanh toán** hay **hủy đơn** phải tuân thủ quy tắc nghiệp vụ: không thanh toán hai lần, không chuyển từ trạng thái đã hủy sang đã giao, lưu được lịch sử thay đổi. Trong khi đó, màn hình của khách hàng lại cần những truy vấn khác hẳn:

- Lấy chi tiết một đơn hàng theo `order_id`.
- Hiển thị 20 đơn mới nhất của một khách hàng, có phân trang.
- Xem những đơn đang chờ xử lý của một cửa hàng.

Nếu ép tất cả hoạt động vào một mô hình bảng duy nhất, mỗi lần thêm kiểu truy vấn có thể phải đánh đổi giữa tính đúng đắn của nghiệp vụ và hiệu năng đọc. Với **Apache Cassandra**, vấn đề càng rõ: một bảng thường được thiết kế theo **truy vấn sẽ chạy**, dựa trên partition key và clustering columns, thay vì kỳ vọng truy vấn tùy ý bằng join hay lọc toàn cụm.

Giải pháp là tách:

| Phần | Trách nhiệm | Yêu cầu chủ yếu |
| --- | --- | --- |
| **Đường ghi nghiệp vụ (command/write path)** | Kiểm tra lệnh, áp dụng quy tắc, thay đổi trạng thái có thẩm quyền | Đúng đắn, chống ghi trùng, bảo vệ bất biến nghiệp vụ |
| **Nguồn dữ liệu chuẩn (source of truth)** | Lưu trạng thái được hệ thống công nhận | Có thể kiểm chứng, phục hồi và phát lại thay đổi |
| **Đường đồng bộ (event/projection pipeline)** | Biến thay đổi nghiệp vụ thành một hoặc nhiều bản chiếu để đọc | Bền vững, có thể thử lại, quan sát được độ trễ |
| **Bảng đọc Cassandra (read models/projections)** | Phục vụ một nhóm truy vấn đã biết với khóa phân vùng thích hợp | Đọc nhanh, truy vấn trực tiếp theo khóa, mở rộng ngang |

Đây là cách áp dụng tư duy **CQRS (Command Query Responsibility Segregation)** ở mức kiến trúc dữ liệu: phần ghi quyết định *điều gì hợp lệ*; phần đọc tổ chức *dữ liệu cần hiển thị như thế nào*. Không bắt buộc phải dùng event sourcing; cũng không bắt buộc phải tách thành hai microservice. Điều cốt lõi là phân biệt trách nhiệm và hợp đồng nhất quán.

## 2. Luồng kiến trúc tham chiếu

Ví dụ dưới đây dùng cơ sở dữ liệu giao dịch làm nguồn chuẩn và Cassandra làm kho bảng đọc. Đây là một lựa chọn phù hợp khi cần giao dịch nghiệp vụ tại nguồn, đồng thời cần Cassandra phục vụ nhiều kiểu đọc với lưu lượng lớn.

~~~mermaid
flowchart LR
    U["Ứng dụng người dùng"]
    C["Command API"]
    DB[("Nguồn chuẩn: đơn hàng")]
    OB[("Transactional outbox")]
    R["Outbox relay / CDC"]
    Q[("Luồng sự kiện bền vững")]
    P["Projection worker"]
    A[("Cassandra: orders_by_id")]
    B[("Cassandra: orders_by_customer_month")]
    RA["Query API"]

    U -->|"Đặt / trả tiền / hủy đơn"| C
    C -->|"Một giao dịch"| DB
    C -->|"Cùng giao dịch"| OB
    OB --> R --> Q --> P
    P --> A
    P --> B
    U -->|"Xem đơn hàng"| RA
    RA --> A
    RA --> B
~~~

Ở ví dụ này, lệnh thanh toán thành công khi trạng thái nghiệp vụ và bản ghi outbox đã được commit tại **nguồn chuẩn**. Sự kiện được chuyển tới worker, sau đó worker cập nhật từng bảng đọc. Bởi vậy, **API đọc có thể tạm thời thấy phiên bản cũ**, ngay cả khi API ghi đã phản hồi thành công. Độ trễ này phải là một phần của hợp đồng sản phẩm.

### Luồng ghi từng bước

1. Command API nhận `PayOrder(orderId, idempotencyKey)`, xác thực quyền và kiểm tra trạng thái đơn hàng.
2. Trong **một giao dịch của nguồn chuẩn hỗ trợ giao dịch**, service cập nhật đơn và ghi một sự kiện outbox, chẳng hạn `OrderPaid(orderId, version=7, ...)`. Nếu giao dịch thất bại, cả hai thay đổi bị hủy.
3. Relay hoặc cơ chế CDC đọc outbox rồi đưa sự kiện vào luồng bền vững. Sự kiện nên có `event_id`, `order_id`, `version`, `occurred_at`, loại sự kiện và dữ liệu cần thiết để lập bảng đọc.
4. Projection worker nhận sự kiện, cập nhật các bảng Cassandra liên quan và chỉ xác nhận đã xử lý khi những cập nhật bắt buộc hoàn tất.
5. Query API đọc trực tiếp bảng đáp ứng truy vấn, không cần join sang nguồn chuẩn cho mỗi yêu cầu.

Một luồng sự kiện thường có khả năng **giao ít nhất một lần (at-least-once)**: cùng sự kiện có thể đến lại sau lỗi mạng hoặc worker khởi động lại. Cần thiết kế xử lý lặp, phục hồi và kiểm soát thứ tự; không thể mặc định mỗi sự kiện chỉ đến một lần.

### Vì sao không ghi thẳng vào cả hai phía trong command handler?

Giả sử command handler ghi thành công vào nguồn chuẩn rồi ghi Cassandra nhưng gặp timeout. Hệ thống không biết lệnh Cassandra đã được áp dụng hay chưa. Nếu Cassandra thành công trước nhưng giao dịch nguồn chuẩn bị rollback, bảng đọc lại chứa dữ liệu chưa từng được chấp nhận. Hai thao tác trên hai hệ thống **không tạo thành một giao dịch nguyên tử chỉ vì được gọi liên tiếp**.

**Transactional outbox** xử lý khe hở *ghi nguồn chuẩn nhưng mất sự kiện* khi outbox được ghi trong cùng giao dịch với dữ liệu nghiệp vụ. Tuy vậy, outbox không tự làm các bảng Cassandra đồng bộ nguyên tử: worker vẫn phải idempotent, thử lại và đối soát.

Nếu **Cassandra cũng là nguồn chuẩn**, kiến trúc vẫn có thể tách command model khỏi query projections. Nhưng không được suy rằng một ghi Cassandra vào nhiều partition, một logged batch hay một LWT là giao dịch phân tán tương đương giao dịch của hệ quản trị quan hệ. Phải chọn cơ chế phát thay đổi thích hợp (CDC, log sự kiện bền vững hoặc luồng ghi có chiến lược khôi phục), xác định rõ giới hạn atomicity và đối soát khi cập nhật không đầy đủ.

## 3. Thiết kế bảng đọc Cassandra bắt đầu từ câu truy vấn

Giả sử hệ thống có hai yêu cầu đã biết:

1. `GET /orders/{orderId}`: lấy đơn hàng theo mã.
2. `GET /customers/{customerId}/orders?month=2026-11`: lấy danh sách đơn mới nhất của khách hàng trong một tháng.

Thay vì một bảng chuẩn hóa dùng chung, tạo **hai bản chiếu** chứa dữ liệu lặp có chủ đích:

~~~sql
-- Tên datacenter 'dc1' chỉ là ví dụ; dùng đúng tên DC trong cluster thật.
CREATE KEYSPACE shop_read
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

-- Truy vấn trực tiếp bằng mã đơn hàng.
CREATE TABLE shop_read.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    created_at timestamp,
    status text,
    total_cents bigint,
    event_version bigint
);

-- Truy vấn danh sách theo khách hàng và tháng.
CREATE TABLE shop_read.orders_by_customer_month (
    customer_id uuid,
    order_month text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_cents bigint,
    event_version bigint,
    PRIMARY KEY ((customer_id, order_month), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

Trong bảng `orders_by_customer_month`:

- **Partition key** là cặp `(customer_id, order_month)`. Các đơn của một khách hàng trong một tháng được đặt cùng partition logic.
- **Clustering key** là `(created_at, order_id)`. Thời điểm tạo giảm dần giúp lấy đơn mới trước; `order_id` phân biệt các đơn trùng thời điểm.
- `status` và `total_cents` được **nhân bản** để API danh sách không phải truy vấn bổ sung theo từng `order_id`.
- `event_version` hỗ trợ xác định bản chiếu đang ở phiên bản nghiệp vụ nào.

Hai truy vấn tương ứng:

~~~sql
SELECT order_id, customer_id, created_at, status, total_cents
FROM shop_read.orders_by_id
WHERE order_id = 8c614bba-55ab-46bb-86b1-301e34713b9e;

SELECT order_id, created_at, status, total_cents
FROM shop_read.orders_by_customer_month
WHERE customer_id = 6d075fbd-cf57-4f83-a92c-78ab9f61ece3
  AND order_month = '2026-11'
LIMIT 20;
~~~

Đây là các truy vấn sử dụng đầy đủ partition key. Không cần `ALLOW FILTERING`, quét cụm hay join. Nếu cần xem đơn trong nhiều tháng, ứng dụng truy vấn các bucket liên quan rồi ghép kết quả theo thời gian; `LIMIT 20` trong một bucket không tự giải quyết phân trang xuyên nhiều bucket. Trong môi trường thực, dùng paging state, giới hạn số bucket được truy cập và xác định rõ quy tắc ghép trang.

**Lựa chọn bucket theo tháng phải dựa vào kích thước và độ nóng partition.** Khách hàng có số lượng đơn lớn có thể cần bucket theo ngày hoặc thêm shard; đổi lại, truy vấn phải đọc nhiều partition hơn. Không có một công thức bucket đúng cho mọi tải. Nên đo số hàng/partition, dung lượng/partition, tốc độ ghi và độ trễ đọc với dữ liệu gần sản xuất.

Nếu sản phẩm thêm màn hình **đơn chờ xử lý theo cửa hàng**, phải thiết kế một query model và khóa phù hợp với `store_id`/trạng thái/bucket, đồng thời có chiến lược xóa hoặc di chuyển mục khi trạng thái đổi. Không nên chữa cháy bằng cách thêm `WHERE status = 'PENDING'` vào bảng hiện tại khi `status` không thuộc khóa truy vấn.

## 4. Biến sự kiện nghiệp vụ thành bản chiếu

Worker nhận các sự kiện thuộc cùng một đơn:

~~~json
{
  "event_id": "4b598aeb-5c47-41bf-a644-67e2a0cd4f62",
  "type": "OrderPaid",
  "order_id": "8c614bba-55ab-46bb-86b1-301e34713b9e",
  "customer_id": "6d075fbd-cf57-4f83-a92c-78ab9f61ece3",
  "created_at": "2026-11-20T09:15:00Z",
  "order_month": "2026-11",
  "status": "PAID",
  "total_cents": 259900,
  "version": 7
}
~~~

Khi tạo đơn (`OrderPlaced`, phiên bản 1), projection worker tạo hai bản ghi tương ứng. Khi thanh toán (`OrderPaid`, phiên bản 7), worker cập nhật `status` và `event_version` trên **cả hai** bản chiếu. `created_at` và `order_month` nên là thuộc tính ổn định lấy từ đơn gốc, không tái tính từ thời điểm nhận event.

### Xử lý lặp và sai thứ tự

Upsert CQL thông thường áp dụng cơ chế **last-write-wins dựa trên write timestamp**. Nó không tự hiểu rằng sự kiện nghiệp vụ phiên bản 7 mới hơn phiên bản 6. Nếu sự kiện cũ được phát lại sau sự kiện mới, một cập nhật thiếu kiểm soát có thể đưa `status` trở về giá trị cũ.

Có một số phương án, tùy tải và ràng buộc đúng đắn:

| Phương án | Cách áp dụng | Giới hạn |
| --- | --- | --- |
| **Tuần tự theo khóa đơn hàng** | Luồng sự kiện chọn `order_id` làm partition key, xử lý các version theo thứ tự trong từng đơn | Vẫn cần xử lý lặp, lỗi từng projection và quá trình replay |
| **Điều kiện theo version bằng LWT** | Chỉ chuyển từ version `n-1` sang `n` với `IF event_version = ?` | Tốn thêm round trip/đồng thuận; các bảng khác nhau vẫn cập nhật độc lập |
| **Projection có thể xây dựng lại** | Từ snapshot và event log/source of truth tạo lại dữ liệu đọc | Cần thiết kế watermark, lưu trữ sự kiện hoặc nguồn truy xuất đầy đủ |

Ví dụ CQL dùng **lightweight transaction (LWT)** để chặn cập nhật lùi phiên bản cho **một bản ghi** đã tồn tại:

~~~sql
UPDATE shop_read.orders_by_id
SET status = 'PAID',
    event_version = 7
WHERE order_id = 8c614bba-55ab-46bb-86b1-301e34713b9e
IF event_version = 6;
~~~

Nếu điều kiện không thỏa, worker phải đọc phiên bản hiện tại và phân loại: event đến trùng, đã có version mới hơn hay bị thiếu version trung gian. Không được chỉ bỏ qua mọi kết quả `[applied] = false`. Với sự kiện tạo mới, có thể dùng `INSERT ... IF NOT EXISTS` và xác minh bản ghi đã tồn tại khớp sự kiện trước khi coi là xử lý trùng thành công.

LWT bảo vệ điều kiện trong partition liên quan; **không phải** giao dịch nguyên tử trên `orders_by_id` và `orders_by_customer_month`. Nếu bảng đầu cập nhật thành công còn bảng sau lỗi, sự kiện phải được retry hoặc đưa vào cơ chế phục hồi. Tách trạng thái xử lý cho từng projection khi chúng có yêu cầu khả dụng khác nhau.

### Minh họa consumer Java

Đoạn sau minh họa bước cập nhật **một projection** bằng Java Driver 4.x sau khi bản ghi của phiên bản 6 đã tồn tại. Nó cho thấy cách nhận biết kết quả điều kiện, chưa phải consumer hoàn chỉnh gồm retry, DLQ và quản lý offset:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.util.UUID;

// session được tạo và quản lý vòng đời ở tầng hạ tầng của service.
void projectStatusChange(
        CqlSession session, UUID orderId, String newStatus, long version) {
    PreparedStatement statement = session.prepare(
        "UPDATE shop_read.orders_by_id " +
        "SET status = ?, event_version = ? " +
        "WHERE order_id = ? IF event_version = ?");

    BoundStatement bound = statement.bind(
            newStatus, version, orderId, version - 1)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

    Row result = session.execute(bound).one();
    if (result == null || !result.getBoolean("[applied]")) {
        // Đọc version hiện tại để phân biệt trùng, đến sai thứ tự,
        // hoặc mất bản ghi; sau đó retry/reconcile theo chính sách.
        throw new IllegalStateException("Projection version mismatch");
    }
}
~~~

Trong ứng dụng thực, chuẩn bị `PreparedStatement` một lần và tái sử dụng, tránh gọi `prepare` trên từng event. Những sự kiện của cùng đơn nên có một chiến lược đảm bảo thứ tự ở worker. Áp dụng quy tắc tương tự cho projection theo khách hàng nhưng không coi hai cập nhật là một transaction; chỉ xác nhận event theo chính sách hoàn tất đã định.

## 5. Nhất quán: phân biệt giao dịch nghiệp vụ với độ mới của bảng đọc

Giả sử keyspace trong ví dụ có **replication factor = 3** ở một datacenter và client đọc/ghi với **`LOCAL_QUORUM`**. Khi các replica hoạt động bình thường, quorum địa phương cần phản hồi từ ít nhất 2 trong 3 replica, giúp các quorum đọc/ghi giao nhau trong phạm vi bản sao của **cùng dữ liệu**. Đây là lựa chọn cân bằng giữa khả dụng và mức nhất quán của thao tác Cassandra.

Tuy nhiên, ngay cả khi worker ghi thành công với `LOCAL_QUORUM`, việc command API vừa ghi vào nguồn chuẩn **không đồng nghĩa** query API đã nhìn thấy bản chiếu mới. Giữa hai API còn có relay, queue, worker và khả năng cập nhật thiếu một projection. Cần phân biệt:

1. **Tính đúng đắn nghiệp vụ:** trạng thái chính thức, kiểm tra chuyển trạng thái, giữ idempotency key — thuộc command path/source of truth.
2. **Mức nhất quán Cassandra:** ảnh hưởng việc đọc/ghi các replica của từng bảng Cassandra.
3. **Độ trễ đồng bộ projection:** khoảng cách giữa version tại nguồn chuẩn và version cuối cùng mỗi bảng đọc đã áp dụng.

Một yêu cầu cần dữ liệu mới tức thời sau khi thanh toán có thể trả kết quả xác nhận từ command API, tạm đọc nguồn chuẩn cho thao tác đặc biệt, hoặc trả trạng thái “đang cập nhật” kèm version. Không nên dùng bảng đọc có thể trễ để quyết định có được phép hoàn tiền, trừ khi đã thiết kế cơ chế kiểm tra nghiệp vụ độc lập và phù hợp.

Một thiết kế API dễ kiểm chứng có thể trả:

~~~json
{
  "order_id": "8c614bba-55ab-46bb-86b1-301e34713b9e",
  "accepted_version": 7,
  "read_model_status": "UPDATING"
}
~~~

Đây chỉ là **ví dụ hợp đồng API**: hệ thống cần triển khai được cách xác định `read_model_status` (chẳng hạn tra version đã áp dụng), không suy ra trạng thái đó một cách tùy ý.

## 6. Vận hành, kiểm thử và phục hồi

Tách đường ghi/đọc làm tăng số thành phần vận hành. Các thành phần này phải có cơ chế theo dõi rõ ràng:

| Tín hiệu | Ý nghĩa | Phản ứng điển hình |
| --- | --- | --- |
| **Event lag** theo thời gian và offset | Bảng đọc chậm hơn nguồn chuẩn bao lâu | Kiểm tra queue backlog, tốc độ worker, lỗi Cassandra |
| **Version gap** theo `order_id` hoặc mẫu đối soát | Projection thiếu bước chuyển trạng thái | Retry đúng thứ tự; backfill từ nguồn chuẩn |
| **DLQ / số lần retry** | Event không xử lý được sau nhiều lần thử | Điều tra dữ liệu, schema, dependency; đưa sự kiện trở lại đúng thứ tự |
| **Độ trễ và timeout Cassandra** | Partition nóng, quá tải, mạng hoặc cấu hình CL | Xem phân bố partition, replica, truy vấn, capacity |
| **Kích thước partition và tombstone** | Bucket quá rộng hoặc xóa/cập nhật tạo chi phí đọc | Đổi cách bucket, chiến lược TTL/xóa, theo dõi compaction |

Đối với Cassandra, cần lập kế hoạch **repair**, theo dõi compaction và tombstones theo đặc thù vận hành cluster. TTL không phải cách sửa một cơ chế xóa dữ liệu sai thiết kế: dữ liệu hết hạn cũng tạo tombstone trong vòng đời lưu trữ và có thể ảnh hưởng hiệu năng. Đừng tùy tiện đặt TTL cho bảng đơn hàng nếu sản phẩm cần lịch sử lâu dài.

### Khi projection lỗi giữa chừng

Giả sử sự kiện version 7 đã cập nhật `orders_by_id` nhưng `orders_by_customer_month` timeout:

1. Giữ event chưa được xác nhận hoàn tất (hoặc ghi trạng thái còn thiếu của projection).
2. Thử lại có backoff và giới hạn phù hợp; kiểm tra version để tránh ghi lùi khi retry.
3. Nếu quá ngưỡng, chuyển vào DLQ có đủ `event_id`, `order_id`, version, projection thất bại và nguyên nhân.
4. Sau khi xử lý sự cố, phát lại hoặc backfill và đối soát hai bảng với nguồn chuẩn.

Không giả định timeout nghĩa là ghi thất bại: có thể replica đã nhận mutation trong khi client chưa nhận kết quả. Đây là lý do thao tác replay phải an toàn khi chạy lại.

### Dựng lại một bảng đọc

Khi thêm bảng mới hoặc thay khóa phân vùng, quy trình khả thi là:

1. Tạo schema và projection worker mới, xác định thời điểm bắt đầu ghi nhận thay đổi (**watermark/offset**).
2. Backfill dữ liệu hiện có từ nguồn chuẩn bằng snapshot nhất quán theo khả năng của nguồn.
3. Bắt kịp các sự kiện từ watermark, tránh khoảng trống và không cho sự kiện cũ ghi đè trạng thái mới.
4. Đối soát số lượng và dữ liệu theo cửa sổ thời gian, lấy mẫu hoặc kiểm tra version theo khóa.
5. Chuyển Query API sang projection mới khi độ trễ/độ đầy đủ đạt mục tiêu; giữ khả năng quay lại đường đọc cũ trong giai đoạn chuyển đổi.

Chỉ “copy hết bảng rồi mở worker” mà không có watermark và xử lý xung đột có thể mất các cập nhật xảy ra trong khi backfill.

## 7. Những quyết định cần chốt trước khi triển khai

| Câu hỏi | Gợi ý quyết định |
| --- | --- |
| Hệ thống nào quyết định trạng thái đơn hàng hợp lệ? | Chỉ rõ một **nguồn chuẩn** và nơi kiểm tra invariant. |
| Mỗi endpoint đọc sẽ dùng partition key nào? | Ghi ra CQL truy vấn thực tế rồi thiết kế bảng theo truy vấn đó. |
| Độ trễ projection tối đa cho phép là bao nhiêu? | Đặt mục tiêu đo được, ví dụ p95 lag, và hành vi UI khi chưa cập nhật. |
| Event bị lặp, sai thứ tự hoặc thiếu version thì sao? | Định nghĩa idempotency, ordering, retry, DLQ và reconciliation. |
| Ai chịu trách nhiệm khi cập nhật một trong nhiều bảng thất bại? | Quy định chính sách hoàn tất và cơ chế replay cho từng projection. |
| Khóa phân vùng có tạo partition quá lớn hoặc hotspot không? | Chọn bucket từ dữ liệu tải thật, đo kích thước và truy vấn đa bucket. |
| Làm thế nào đổi schema mà không dừng dịch vụ? | Phiên bản projection, backfill, watermark, đối soát và chuyển luồng đọc. |

### Ví dụ phân tích tình huống

**Tình huống:** Khách hàng vừa thanh toán, API ghi trả thành công, nhưng trang “Đơn hàng của tôi” vẫn hiển thị `PENDING` trong vài giây.

**Phân tích đúng:** Trước tiên xác minh trạng thái `PAID` và event outbox tại nguồn chuẩn. Tiếp theo kiểm tra sự kiện đã được relay chưa, consumer đã xử lý đến version nào và bảng `orders_by_customer_month` có đang trễ không. Không thay đổi ngay consistency level của Query API với hy vọng khắc phục độ trễ *trước khi event đến Cassandra*.

**Hành động thiết kế:** Hiển thị trạng thái đã được command API xác nhận trên màn hình vừa thanh toán, theo dõi lag của bản chiếu và cho phép Query API bắt kịp. Nếu nghiệp vụ yêu cầu read-after-write ngay lập tức, cần một hợp đồng nhất quán mạnh hơn cùng chi phí tương ứng, chẳng hạn đọc qua command-side source trong thời gian chuyển tiếp.

## 8. Ghi nhớ

Tách đường ghi nghiệp vụ khỏi bảng đọc theo truy vấn cho phép ứng dụng tập trung **quy tắc và tính đúng đắn ở command path**, còn Cassandra tập trung **phân phối và phục vụ dữ liệu đã được tổ chức theo truy vấn**. Đổi lại, hệ thống chấp nhận dữ liệu nhân bản, đồng bộ bất đồng bộ và trách nhiệm vận hành projection.

Ba nguyên tắc quan trọng nhất:

1. **Thiết kế bảng Cassandra từ câu hỏi cần trả lời và khóa phân vùng**, không từ sơ đồ thực thể chuẩn hóa.
2. **Không sử dụng nhiều lệnh ghi rời rạc như thể chúng là một giao dịch phân tán**; dùng outbox khi nguồn chuẩn có giao dịch phù hợp và bảo đảm replay an toàn.
3. **Đo và xử lý độ trễ, sự kiện lặp, sai thứ tự, lỗi từng projection**; consistency level của Cassandra không thay thế các bảo đảm này.
