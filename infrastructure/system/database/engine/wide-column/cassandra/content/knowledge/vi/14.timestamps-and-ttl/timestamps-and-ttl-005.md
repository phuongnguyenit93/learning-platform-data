# Ghi đồng thời cùng cột và quy tắc phân giải theo timestamp

## 1. Vấn đề: hai ứng dụng cùng cập nhật một cell

Trong **Apache Cassandra**, hệ quản trị cơ sở dữ liệu **wide-column phân tán**, nhiều client có thể đồng thời ghi vào cùng partition ở các coordinator khác nhau. Cassandra không giữ một hàng duy nhất trên một máy: dữ liệu được nhân bản sang nhiều **replica** theo replication factor. Vì độ trễ mạng, retry và thứ tự xử lý khác nhau, các replica có thể tạm thời nắm các phiên bản khác nhau của một cell.

Khi cần chọn một phiên bản để trả về và hội tụ dữ liệu, Cassandra mặc định sử dụng cơ chế **last-write-wins (LWW)** dựa trên **mutation timestamp**. Điều đó có nghĩa:

> Với cùng một cell thông thường, **phiên bản mang mutation timestamp lớn hơn sẽ thắng**, bất kể yêu cầu nào đến coordinator hoặc replica sau theo thời gian thực.

Đây là quy tắc hòa giải dữ liệu, **không phải cơ chế khóa ghi toàn cluster**, cũng không phải bảo đảm “người nhấn nút Lưu cuối cùng thắng”.

Ví dụ một hệ thống đặt hàng có hai dịch vụ:

- Dịch vụ thanh toán ghi `payment_status = 'PAID'`.
- Dịch vụ quản lý đơn ghi `payment_status = 'CANCELLED'` gần như cùng lúc.
- Hai yêu cầu được chấp nhận ở các coordinator/replica khác nhau.

Không thể xác định trạng thái cuối cùng chỉ bằng thứ tự các lời gọi API hay thời điểm nhận phản hồi. Phải xét **đúng cell**, **write timestamp**, loại mutation (giá trị sống hay xóa), và cách Cassandra phân xử trường hợp timestamp bằng nhau.

## 2. Thế nào là “cùng một cột” trong mô hình wide-column?

Một xung đột LWW thông thường xảy ra tại **cùng vị trí dữ liệu**: cùng keyspace, bảng, partition key, clustering key (nếu có) và cùng cell/cột. Trong Cassandra, cột có tên giống nhau nhưng thuộc hai row khác nhau **không phải** cùng cell.

Giả sử bảng:

```sql
CREATE TABLE IF NOT EXISTS order_state_by_id (
    order_id uuid PRIMARY KEY,
    payment_status text,
    delivery_status text,
    updated_by text
);
```

| Mutation | Cùng cell với mutation A không? | Vì sao |
|---|---|---|
| A ghi `payment_status` của đơn X | — | Cell đang xét |
| B ghi `payment_status` của đơn X | **Có** | Cùng primary key và cột |
| C ghi `delivery_status` của đơn X | **Không** | Cùng hàng nhưng khác cột |
| D ghi `payment_status` của đơn Y | **Không** | Khác partition key |

Ngay cả khi một lệnh `UPDATE` cùng lúc đặt `payment_status` và `updated_by`, mỗi cell có thể được hòa giải riêng với các mutation khác. Hệ quả là một row có thể kết hợp giá trị từ **nhiều lần ghi khác nhau**. Không được mặc định các cột được cập nhật cùng câu lệnh luôn là một “phiên bản hàng” bất khả phân.

Với collection không `frozen`, UDT, row marker và các dạng delete theo phạm vi lớn hơn, Cassandra còn có quy tắc xung đột tại những cell/đường dữ liệu cụ thể. Những ví dụ dưới đây tập trung vào **cột scalar thông thường** để thấy rõ nguyên tắc.

## 3. Cassandra quyết định bản ghi thắng như thế nào?

**Mutation timestamp** là một số nguyên 64-bit, tính bằng **micro giây (µs) kể từ Unix epoch**. Đây là metadata của một lần ghi, khác với cột CQL kiểu `timestamp` dùng để lưu thời gian nghiệp vụ ở độ phân giải mili giây.

Với hai phiên bản sống của **cùng một cell**:

1. So sánh mutation timestamp.
2. Phiên bản có timestamp **lớn hơn** thắng.
3. Nếu timestamp **bằng nhau**, Cassandra sử dụng quy tắc phân xử xác định ở mức dữ liệu nội bộ. **Không** suy ra bản gửi/nhận sau thắng.
4. Khi một **tombstone** (dấu xóa) và giá trị sống của cùng cell có timestamp bằng nhau, **tombstone được ưu tiên**. Tombstone lớn hơn che các giá trị cũ hơn.

Đối với **hai giá trị sống** có timestamp bằng nhau, Cassandra có các quy tắc so sánh giá trị ở mức biểu diễn dữ liệu (trong trường hợp cell đơn giản, giá trị có thứ tự byte lớn hơn có thể thắng). Đó là hành vi phân xử xung đột, **không phải quy tắc nghiệp vụ nên dựa vào**: thứ tự byte không nói sự kiện nào xảy ra sau; các cấu trúc dữ liệu phức tạp và metadata hết hạn có chi tiết xử lý riêng.

| Cell đã có | Mutation mới | Kết quả cơ bản | Nguyên nhân |
|---|---|---|---|
| `A @ 100` | `B @ 200` | `B` | `200 > 100` |
| `A @ 200` | `B @ 100` | `A` | Mutation mới có timestamp cũ |
| `A @ 200` | `B @ 200` | Theo quy tắc tie-break nội bộ | Không căn cứ thời điểm đến |
| `A @ 200` | Xóa `@ 200` | Cell bị xóa | Tombstone thắng giá trị sống tại timestamp bằng nhau |
| Tombstone `@ 300` | `C @ 250` | Vẫn bị xóa | Tombstone lớn hơn che ghi cũ |
| Tombstone `@ 300` | `C @ 350` | `C` hiển thị | Mutation mới hơn tombstone |

```text
                Hai mutation nhắm cùng cell?
                       |
            +----------+-----------+
            |                      |
          Không                   Có
            |                      |
     Không tranh LWW      So sánh write timestamp
                                   |
                          +--------+--------+
                          |                 |
                       Khác nhau         Bằng nhau
                          |                 |
                 Timestamp lớn thắng   Tie-break:
                                      tombstone ưu tiên
                                      hơn giá trị sống;
                                      giá trị sống dùng
                                      quy tắc nội bộ
```

### “Last” trong LWW không có nghĩa “last” của người dùng

Giả sử client A phát lệnh lúc 10:00:00.000, client B phát lệnh lúc 10:00:00.010, nhưng A có đồng hồ nhanh hơn B hai giây. A có thể gán timestamp lớn hơn, vì vậy **A thắng dù gửi trước**. Nếu nhiều máy tự gán timestamp, cơ chế LWW **không tự cung cấp total order theo thời gian thực** giữa tất cả request.

## 4. Thực hành CQL: ghi cùng cell với timestamp khác nhau

Các ví dụ sử dụng bảng `order_state_by_id` trong **keyspace thử nghiệm** đã chọn. Chọn UUID chưa từng dùng; số timestamp được cố định để dễ kiểm chứng. Không tái sử dụng UUID từ lần chạy khác nếu đã có tombstone hoặc timestamp lớn hơn.

### 4.1. Ghi ban đầu

```sql
INSERT INTO order_state_by_id (
    order_id, payment_status, delivery_status, updated_by
)
VALUES (
    55555555-1111-4111-8111-555555555555,
    'PENDING',
    'CREATED',
    'checkout'
)
USING TIMESTAMP 1800000000000000;

SELECT payment_status, writetime(payment_status),
       delivery_status, writetime(delivery_status),
       updated_by, writetime(updated_by)
FROM order_state_by_id
WHERE order_id = 55555555-1111-4111-8111-555555555555;
```

Ba cell vừa tạo đều có mutation timestamp `1800000000000000`. `writetime()` trả về timestamp của cell tương ứng và **không** dùng cho primary key/counter.

### 4.2. Giả lập hai ghi cạnh tranh, thứ tự đến ngược thứ tự timestamp

Đầu tiên ghi `'PAID'` với timestamp lớn:

```sql
UPDATE order_state_by_id
USING TIMESTAMP 1800000000002000
SET payment_status = 'PAID'
WHERE order_id = 55555555-1111-4111-8111-555555555555;
```

Sau đó ghi `'CANCELLED'` với timestamp **nhỏ hơn**:

```sql
UPDATE order_state_by_id
USING TIMESTAMP 1800000000001000
SET payment_status = 'CANCELLED'
WHERE order_id = 55555555-1111-4111-8111-555555555555;

SELECT payment_status, writetime(payment_status)
FROM order_state_by_id
WHERE order_id = 55555555-1111-4111-8111-555555555555;
```

Kết quả kỳ vọng: `'PAID'` và `1800000000002000`. Lệnh thứ hai được thực thi sau nhưng không thay đổi phiên bản thắng vì `...1000 < ...2000`.

Để minh họa ghi thắng bằng timestamp lớn hơn:

```sql
UPDATE order_state_by_id
USING TIMESTAMP 1800000000003000
SET payment_status = 'CANCELLED'
WHERE order_id = 55555555-1111-4111-8111-555555555555;

SELECT payment_status, writetime(payment_status),
       delivery_status, writetime(delivery_status)
FROM order_state_by_id
WHERE order_id = 55555555-1111-4111-8111-555555555555;
```

Lúc này `payment_status` là `'CANCELLED'` với timestamp `...3000`. `delivery_status` vẫn `'CREATED'` với timestamp `...0000`. LWW không chọn “toàn bộ row thắng” chỉ vì một cột đã đổi.

> **Lưu ý:** Hai câu `UPDATE` thực hiện tuần tự ở đây **giả lập** hai request cạnh tranh; chúng minh họa phép phân xử khi phiên bản đến theo thứ tự nào cũng vậy. Phần Java phía dưới sẽ dùng hai yêu cầu bất đồng bộ để quan sát tính đồng thời thực sự.

## 5. Khi hai mutation có timestamp bằng nhau

Cassandra không sử dụng “yêu cầu đến sau” để phân xử tie. Vì thế, **đừng chủ động cho hai writer tạo các giá trị khác nhau với cùng timestamp** rồi mong Cassandra đoán được thứ tự kinh doanh.

### 5.1. Hai giá trị sống cùng timestamp

Dùng một khóa riêng:

```sql
INSERT INTO order_state_by_id (order_id, payment_status)
VALUES (55555555-2222-4222-8222-555555555555, 'PAID')
USING TIMESTAMP 1800000000004000;

UPDATE order_state_by_id
USING TIMESTAMP 1800000000004000
SET payment_status = 'CANCELLED'
WHERE order_id = 55555555-2222-4222-8222-555555555555;

SELECT payment_status, writetime(payment_status)
FROM order_state_by_id
WHERE order_id = 55555555-2222-4222-8222-555555555555;
```

`writetime(payment_status)` vẫn là `1800000000004000`, nhưng **không được giả định `'CANCELLED'` thắng vì câu UPDATE chạy sau**. Quy tắc phân xử tie nội bộ quyết định kết quả. Đối với ứng dụng, cần tránh tie bằng chính sách timestamp và/hoặc cơ chế kiểm tra điều kiện.

### 5.2. Xóa cùng timestamp với giá trị sống

Dùng khóa riêng để tránh ảnh hưởng bài thử trước:

```sql
INSERT INTO order_state_by_id (order_id, payment_status, updated_by)
VALUES (
    55555555-3333-4333-8333-555555555555,
    'PAID',
    'payment-service'
)
USING TIMESTAMP 1800000000005000;

DELETE payment_status FROM order_state_by_id
USING TIMESTAMP 1800000000005000
WHERE order_id = 55555555-3333-4333-8333-555555555555;

SELECT payment_status, updated_by
FROM order_state_by_id
WHERE order_id = 55555555-3333-4333-8333-555555555555;
```

Kết quả: `payment_status` là `null`, còn `updated_by` vẫn có `'payment-service'`. **Tombstone thắng giá trị sống ở cùng timestamp**. Điều này cũng có nghĩa ghi lại một giá trị ở timestamp `...5000` chưa đủ để khôi phục cell; cần một mutation hợp lệ có timestamp mới hơn tombstone.

**Tombstone không thể được xem trực tiếp bằng `writetime(payment_status)` sau khi cell bị xóa.** Công cụ chẩn đoán SSTable, lịch sử lệnh xóa và log ghi là các nguồn phù hợp hơn khi cần xác định một tombstone cụ thể.

## 6. Hai request đồng thời qua Java Driver

Trong ứng dụng Java dùng **Apache/DataStax Cassandra Java Driver 4.x**, hai thread, pod hoặc service có thể phát ghi song song tới cùng partition. Ví dụ dưới đây cho phép hai request có timestamp xác định trước, để kết quả LWW **không phụ thuộc thứ tự completion**.

Giả sử bảng đã có và mỗi lần chạy dùng một `orderId` mới:

```java
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class ConcurrentOrderUpdates {
    private final CqlSession session;
    private final PreparedStatement updateStatus;

    public ConcurrentOrderUpdates(CqlSession session) {
        this.session = session;
        this.updateStatus = session.prepare(
            "UPDATE order_state_by_id " +
            "SET payment_status = ? WHERE order_id = ?"
        );
    }

    public void writeTwoVersions(UUID orderId) {
        // Hai request cùng ghi vào đúng một cell.
        // Timestamp tính bằng MICRO giây kể từ Unix epoch.
        BoundStatement paid = updateStatus
            .bind("PAID", orderId)
            .setQueryTimestamp(1800000000008000L);

        BoundStatement cancelled = updateStatus
            .bind("CANCELLED", orderId)
            .setQueryTimestamp(1800000000007000L);

        CompletableFuture<?> first = session.executeAsync(paid)
            .toCompletableFuture();
        CompletableFuture<?> second = session.executeAsync(cancelled)
            .toCompletableFuture();

        // Chờ cả hai request trả kết quả hoặc nhận lỗi.
        CompletableFuture.allOf(first, second).join();
    }
}
```

Khi chạy với khóa chưa tồn tại, dù request `cancelled` kết thúc trước hay sau request `paid`, sau khi dữ liệu được hòa giải thì **`'PAID'` thắng** do timestamp `...8000 > ...7000`. Với các lần đọc sát thời điểm hai request đang chạy, mức nhất quán và độ trễ replica có thể ảnh hưởng phiên bản tạm thời nhìn thấy; nên thực hiện kiểm tra sau khi cả hai request hoàn tất và ở consistency level phù hợp.

**Chú ý Java Driver:** `setQueryTimestamp(long)` trả về statement mới (API statement bất biến của Driver 4.x); phải sử dụng giá trị trả về như trên. Nếu viết câu CQL có `USING TIMESTAMP`, timestamp từ CQL có ưu tiên cao hơn query timestamp truyền ở mức statement. Cũng cần phân biệt epoch microseconds và `System.currentTimeMillis()` là epoch milliseconds.

## 7. Vì sao timestamp giữa các writer dễ đảo thứ tự?

Cassandra có thể nhận mutation timestamp từ:

- **CQL `USING TIMESTAMP`:** ứng dụng chỉ định số micro giây.
- **Statement timestamp ở driver:** ví dụ `setQueryTimestamp(...)`.
- **Timestamp generator:** Java Driver có generator cấp timestamp phía client; một số loại duy trì tính tăng đơn điệu trong phạm vi generator.
- **Coordinator:** server cấp timestamp nếu request không có timestamp do client gửi.

Những nguồn khác nhau có thể quan sát đồng hồ khác nhau. Một generator tăng đơn điệu **trong một JVM** không tạo ra thứ tự thống nhất giữa nhiều service trên những host riêng. Đồng hồ client nhanh vài giây có thể khiến ghi của nó che các mutation từ client khác trong nhiều giây tiếp theo.

```text
  Thời gian thực            10:00:00.000       10:00:00.050
                               |                    |
  Client A (nhanh 2s)       ts 10:00:02.000        |
  Client B (đúng giờ)           |             ts 10:00:00.050
                               |                    |
  Gửi hai UPDATE              A                    B

  So sánh timestamp: A > B → A thắng,
  mặc dù B phát request 50 ms sau A.
```

Cần đồng bộ giờ trên cả node Cassandra **và** host chạy client/driver bằng nguồn thời gian đáng tin cậy (NTP, chrony hoặc tương đương), giám sát clock skew và thống nhất cách tạo timestamp. Một timestamp ở tương lai có thể làm cell trông như “không nhận ghi mới” đến khi các mutation tiếp theo vượt được giá trị đang thắng.

### Retry cũng có thể đổi thứ tự nghiệp vụ

Giả sử `E1: PENDING` được gửi trước nhưng timeout; `E2: PAID` được gửi sau và hoàn tất. Nếu retry `E1` **được gán timestamp mới** lớn hơn `E2`, trạng thái có thể lùi về `PENDING`. Nếu nghiệp vụ cần replay chính xác, hãy dùng định danh sự kiện và chính sách idempotency, đồng thời cân nhắc **giữ timestamp ổn định cho cùng mutation** khi thích hợp. Việc giữ timestamp không tự giải quyết được hai mutation khác nhau cố ý dùng cùng timestamp; cần quy tắc phân biệt/thứ tự tại nguồn.

## 8. Replication, consistency level và reconciliation

Giả sử keyspace có **RF = 3**. Hai request ghi cùng cell tại hai coordinator:

```text
                        Client A
                    PAID @ ts = 200
                            |
                            v
                      Coordinator X
                       ↙       ↘
                  Replica 1   Replica 2

                        Client B
                 CANCELLED @ ts = 300
                            |
                            v
                      Coordinator Y
                       ↙       ↘
                  Replica 2   Replica 3

    Các replica có thể tạm giữ những phiên bản khác nhau.
    Khi các phiên bản được đối chiếu: ts = 300 thắng.
```

Hình chỉ minh họa quá trình phân phối không đồng thời. Trong triển khai thật, Cassandra xác định replica cho partition theo topology/replication strategy, và coordinator điều phối theo consistency level của request.

| Khái niệm | Vai trò trong tình huống |
|---|---|
| **Replication factor** | Số replica lưu partition |
| **Consistency level khi ghi/đọc** | Điều kiện số replica cần tham gia/xác nhận phù hợp request, ví dụ `ONE`, `QUORUM`, `ALL` |
| **Last-write-wins** | Quy tắc chọn cell thắng khi các replica có phiên bản xung đột |
| **Read reconciliation, repair** | Cơ chế đọc và vận hành giúp các replica trao đổi, phát hiện và sửa khác biệt |

Với RF = 3, `QUORUM` thường yêu cầu phản hồi từ **2 replica**. Khi cấu hình đọc/ghi phù hợp, các quorum có giao nhau, giúp tăng khả năng quan sát phiên bản mới nhất theo **thứ tự timestamp** trong điều kiện hoạt động thích hợp. Tuy nhiên:

- `QUORUM` **không bảo đảm** lệnh có timestamp thấp hơn ghi đè phiên bản có timestamp cao hơn.
- `ALL` không sửa được clock skew hoặc một `USING TIMESTAMP` sai đơn vị.
- Đọc `ONE` trong lúc có ghi đồng thời có thể quan sát trạng thái tạm thời khác nhau, tùy replica được hỏi.
- **Repair** làm replicas hội tụ theo quy tắc dữ liệu Cassandra; nó không biết trạng thái nào đúng theo nghiệp vụ nếu write timestamp đã sai.

Do đó, cần phân biệt hai câu hỏi: **“Request đã đạt consistency level chưa?”** và **“Phiên bản mutation nào thắng trong cell?”**. Hai câu hỏi được giải quyết bằng hai cơ chế khác nhau.

## 9. TTL và tombstone khi ghi đồng thời

TTL và delete khiến việc phân xử phức tạp hơn ghi sống đơn thuần:

- `USING TTL N` gán thời gian sống **N giây** cho các cell được ghi. Khi hết hạn, dữ liệu được xử lý như đã xóa.
- `DELETE` tạo **tombstone** nhằm che những phiên bản cũ trên replica khác.
- Một tombstone với timestamp lớn hơn (hoặc bằng timestamp của giá trị sống cùng cell) được ưu tiên.
- Một mutation có timestamp lớn hơn tombstone có thể tạo giá trị sống nhìn thấy lại, nếu nghiệp vụ cho phép.

Ví dụ hai bản ghi có TTL khác nhau:

```sql
-- UUID mới cho ví dụ TTL.
INSERT INTO order_state_by_id (order_id, payment_status)
VALUES (55555555-4444-4444-8444-555555555555, 'REVIEW')
USING TIMESTAMP 1800000000010000 AND TTL 3600;

UPDATE order_state_by_id
USING TIMESTAMP 1800000000011000 AND TTL 60
SET payment_status = 'TEMPORARY'
WHERE order_id = 55555555-4444-4444-8444-555555555555;

SELECT payment_status, writetime(payment_status), ttl(payment_status)
FROM order_state_by_id
WHERE order_id = 55555555-4444-4444-8444-555555555555;
```

Ngay sau ghi, `'TEMPORARY'` là phiên bản thắng và `ttl(payment_status)` xấp xỉ 60 giây. **Không được giả định Cassandra sẽ tự quay về `'REVIEW'` khi `TEMPORARY` hết TTL**; bản sống cũ hơn có thể đã bị phiên bản mới/tombstone hết hạn che khuất. TTL không phải “ngăn xếp các giá trị” tự phục hồi về phiên bản trước.

Đối với các bảng nhiều delete/TTL, **compaction**, thời gian lưu tombstone và **repair** là mối quan tâm vận hành. Nếu tombstone được dọn không an toàn khi còn replica giữ dữ liệu cũ, có rủi ro **zombie data**. Hãy thiết kế lịch repair và chính sách tombstone phù hợp với môi trường; không giảm `gc_grace_seconds` tùy tiện để né vấn đề xung đột.

## 10. Không phải thao tác nào cũng xử lý như ghi LWW đơn giản

### 10.1. Counter

Cột `counter` có cơ chế cộng/trừ đặc thù và không tuân theo cách ghi đè giá trị scalar bằng `USING TIMESTAMP`. Không dùng ví dụ LWW thông thường để suy luận kết quả concurrent counter updates; đồng thời phải xem xét retry và khả năng cộng trùng.

### 10.2. Collections và mutation phạm vi rộng

Collection không `frozen` có thể chứa nhiều cell/thành phần được cập nhật độc lập; delete toàn collection có tác động khác update phần tử. Xóa toàn hàng/partition tạo tombstone ở phạm vi rộng hơn xóa một cột. Cần kiểm tra phạm vi xung đột thay vì mặc định mọi trường hợp là hai giá trị vô hướng cùng một cell.

### 10.3. Batch

`BEGIN BATCH ... APPLY BATCH` có semantics của batch trong Cassandra, nhưng **không tạo ra thứ tự “tới sau thắng” cho ghi cạnh tranh cùng cell**. Dù hai batch hoàn tất theo thứ tự nào, cơ chế hòa giải phiên bản vẫn chịu ảnh hưởng mutation timestamp. Batch nhiều partition còn có đặc điểm chi phí và atomicity khác transaction quan hệ, không nên dùng như công cụ thay thế khóa/điều phối nghiệp vụ.

### 10.4. Lightweight transaction (LWT)

Khi cần kiểm tra điều kiện trước khi ghi, Cassandra hỗ trợ **LWT** với `IF` thông qua Paxos. Ví dụ:

```sql
-- Đặt trạng thái ban đầu trên khóa riêng cho ví dụ LWT.
INSERT INTO order_state_by_id (order_id, payment_status)
VALUES (55555555-5555-4555-8555-555555555555, 'PENDING')
IF NOT EXISTS;

-- Chỉ áp dụng nếu trạng thái hiện tại là PENDING.
UPDATE order_state_by_id
SET payment_status = 'PAID'
WHERE order_id = 55555555-5555-4555-8555-555555555555
IF payment_status = 'PENDING';
```

CQL trả kết quả điều kiện `[applied]` để client biết lần cập nhật có được áp dụng không. LWT cho khả năng thực hiện **compare-and-set** trên phạm vi được hỗ trợ, đổi lại thêm round trip/chi phí. Không ghép `USING TIMESTAMP` tùy ý vào **conditional update**; Cassandra không cho phép timestamp người dùng chỉ định cho LWT theo cách ghi thường.

LWT giải quyết một yêu cầu khác với LWW: **chỉ thay đổi khi trạng thái hiện tại thỏa điều kiện**. Khi nhiều dịch vụ cùng ghi một trạng thái quan trọng, cần thiết kế quá trình chuyển trạng thái và phản ứng khi `[applied] = false`.

## 11. Thiết kế để tránh xung đột ghi cùng cell

Trong module Cassandra, thiết kế bảng **theo truy vấn** gắn trực tiếp với xử lý cạnh tranh ghi. Các lựa chọn:

| Yêu cầu nghiệp vụ | Cách thiết kế thường phù hợp | Điểm đánh đổi |
|---|---|---|
| Chấp nhận “bản có timestamp cao hơn thắng” | Ghi thường với timestamp generator và đồng bộ đồng hồ | Đơn giản, nhưng cần hiểu thứ tự LWW |
| Một đối tượng có **một writer** sở hữu trạng thái | Định tuyến write theo owner/partition hoặc hàng đợi có thứ tự | Cần cơ chế phân công và phục hồi owner |
| Chuyển trạng thái phải tuân điều kiện | LWT `IF ...`, lưu version hợp lệ, phản ứng khi điều kiện sai | Chi phí điều phối tăng |
| Cần lưu mọi sự kiện cạnh tranh | Bảng lịch sử **append-only**, mỗi event là row riêng | Cần truy vấn/tiến trình xây trạng thái hiện tại |
| Cần idempotent khi retry | Dùng event ID, deduplication và timestamp ổn định theo sự kiện khi phù hợp | Phải quản lý danh tính và chính sách thứ tự sự kiện |

Ví dụ lịch sử thay đổi trạng thái theo order và `event_time`:

```sql
CREATE TABLE IF NOT EXISTS payment_events_by_order (
    order_id uuid,
    event_id timeuuid,
    status text,
    source_service text,
    PRIMARY KEY ((order_id), event_id)
) WITH CLUSTERING ORDER BY (event_id DESC);

SELECT event_id, status, source_service
FROM payment_events_by_order
WHERE order_id = 55555555-1111-4111-8111-555555555555
LIMIT 20;
```

Mỗi event có một row riêng, giảm cạnh tranh trực tiếp trên cell `payment_status`. Nhưng **`timeuuid` cũng thường dựa trên đồng hồ**: một khi nghiệp vụ đòi thứ tự tuyệt đối giữa nhiều writer, cần một **sequence/version được cấp từ nguồn điều phối đáng tin cậy** hoặc quy trình xác định thứ tự riêng. Một bảng lịch sử không tự giải quyết mọi vấn đề clock skew hay thứ tự sự kiện.

Để truy vấn các event mới nhất, **clustering key** tạo thứ tự đọc theo khóa. Cassandra không cho phép dùng `ORDER BY writetime(payment_status)` như cách sắp xếp bất kỳ trên metadata cell.

## 12. Chẩn đoán khi hai lời gọi “thành công” nhưng mất một cập nhật

Xác định **cell cụ thể** và thu thập bằng chứng trước khi thay đổi consistency level hay sửa dữ liệu:

| Bước | Cần kiểm tra | Mục đích |
|---|---|---|
| 1 | Keyspace, bảng, partition key, clustering key, cột bị ghi | Hai request có thật sự nhắm cùng cell? |
| 2 | `SELECT value, writetime(value) ...` | Giá trị nào đang thắng và mang timestamp bao nhiêu? |
| 3 | `USING TIMESTAMP`, `setQueryTimestamp()`, timestamp generator | Timestamp được cấp ở đâu và đơn vị có đúng µs? |
| 4 | Clock skew trên JVM, client host, coordinator | Có máy gán timestamp trong tương lai không? |
| 5 | Retry ID, event ID, thứ tự nghiệp vụ | Có retry mang timestamp mới làm sự kiện cũ thắng không? |
| 6 | `DELETE`/TTL/tombstone, compaction | Có bản ghi bị che bởi tombstone lớn hơn không? |
| 7 | RF, CL đọc/ghi, replica health, repair | Có replica tạm không đồng bộ hay xung đột không? |
| 8 | LWT và kết quả `[applied]` (nếu dùng) | Có thao tác bị từ chối do điều kiện không thỏa? |

Ví dụ truy vấn sau giúp quan sát cell còn tồn tại:

```sql
SELECT payment_status, writetime(payment_status),
       delivery_status, writetime(delivery_status)
FROM order_state_by_id
WHERE order_id = 55555555-1111-4111-8111-555555555555;
```

`writetime()` không hiển thị toàn bộ lịch sử các mutation thua hoặc tombstone đã xóa. Khi điều tra production, cần kết hợp log ứng dụng, trace/request metadata và công cụ quản trị Cassandra phù hợp. Ghi log theo `eventId`, `partitionKey`, `mutationTimestampMicros`, `timestampSource` và kết quả request, tránh log các giá trị nhạy cảm không cần thiết.

### Các lỗi dễ bỏ qua

- **Nhầm đơn vị:** `System.currentTimeMillis()` là **mili giây**, trong khi `USING TIMESTAMP` và `setQueryTimestamp()` dùng **micro giây**.
- **Timestamp trùng:** hai client lấy cùng mốc thời gian hoặc độ phân giải nguồn thấp hơn một micro giây; tie không theo thứ tự gửi.
- **Future timestamp:** máy sai đồng hồ có thể chặn các ghi hợp lệ trong tương lai gần.
- **Quan sát sai phạm vi:** thấy một cột đã cập nhật không chứng minh các cột khác trong row cùng phiên bản.
- **Lỗi kỳ vọng nhất quán:** tăng `QUORUM`/`ALL` không sửa timestamp sai; read/write CL và reconciliation giải quyết phạm vi replica, không định nghĩa thứ tự kinh doanh.

## 13. Tự kiểm tra bằng kịch bản

**Câu 1.** Hai client cùng ghi `payment_status` trên một order: A ghi `PAID@500`, B ghi `CANCELLED@700`. B đến coordinator trước A. Giá trị nào thắng sau hòa giải?

**Đáp án:** `CANCELLED`, vì `700 > 500`. Thứ tự coordinator nhận không phải tiêu chí.

**Câu 2.** Hai lệnh ghi khác nhau đều có timestamp `900`. Có thể bảo đảm lệnh gửi sau thắng không?

**Đáp án:** Không. Cassandra dùng cơ chế tie-break xác định của dữ liệu, không căn cứ thứ tự gửi; phải tránh xung đột cùng timestamp.

**Câu 3.** Cell đang sống ở timestamp `1000`, client xóa cell với tombstone timestamp `1000`. Sau hòa giải, cell còn hiển thị không?

**Đáp án:** Không. Tombstone cùng timestamp được ưu tiên trước giá trị sống tương ứng.

**Câu 4.** Hai service đồng thời cập nhật `payment_status` và `delivery_status` của cùng order. Có nhất thiết một trong hai bản ghi bị loại?

**Đáp án:** Không. Chúng là hai cell riêng, có thể cùng tồn tại với write timestamp khác nhau.

**Câu 5.** Đọc và ghi đều `QUORUM`, vậy người dùng cuối bấm “Lưu” sau chắc chắn thắng?

**Đáp án:** Không. Quorum điều chỉnh số replica tham gia và tính nhất quán đọc/ghi; LWW vẫn căn cứ mutation timestamp.

**Câu 6.** Retry sự kiện `PENDING` sau khi `PAID` đã ghi có thể làm trạng thái quay lại `PENDING` không?

**Đáp án:** Có, nếu retry `PENDING` nhận timestamp lớn hơn. Cần idempotency và chính sách thứ tự nghiệp vụ.

**Câu 7.** Nên dùng công cụ nào khi bắt buộc chuyển trạng thái `PENDING → PAID` chỉ nếu trạng thái vẫn là `PENDING`?

**Đáp án:** Cân nhắc LWT `UPDATE ... IF payment_status = 'PENDING'`, kiểm tra `[applied]`, và xử lý tình huống bị cạnh tranh; không dùng ghi LWW vô điều kiện để thay thế compare-and-set.

---

**Ghi nhớ:** Với ghi đồng thời vào **cùng một cell**, Cassandra lựa chọn theo **mutation timestamp**: lớn hơn thắng; khi bằng nhau có **quy tắc phân xử nội bộ**, trong đó **tombstone thắng giá trị sống** tương ứng. Quy tắc này độc lập với thứ tự request đến và không tự bảo đảm thứ tự nghiệp vụ. Để tránh mất cập nhật, cần kiểm soát timestamp/clock skew/retry, thiết kế bảng theo truy vấn và dùng cơ chế điều kiện như **LWT** khi bài toán cần compare-and-set.
