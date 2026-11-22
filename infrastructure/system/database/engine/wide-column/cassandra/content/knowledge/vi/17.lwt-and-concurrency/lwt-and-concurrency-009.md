# Khóa lạc quan bằng cột phiên bản hoặc trạng thái

## Mục tiêu bài học

Trong Apache Cassandra, nhiều client có thể đọc rồi ghi vào cùng một hàng gần như đồng thời. Nếu ứng dụng đọc giá trị, tính toán ở phía Java rồi ghi lại bằng `UPDATE` thông thường, một client có thể **ghi đè kết quả của client khác**. **Khóa lạc quan** (*optimistic locking*) giải quyết tình huống này bằng cách chỉ cho phép cập nhật khi dữ liệu vẫn đáp ứng điều kiện mà client đã đọc hoặc mong đợi.

Trong module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, kỹ thuật này gắn với cách Cassandra phân phối dữ liệu theo **partition key**, mô hình **wide-column**, thiết kế bảng theo truy vấn, replication và mức nhất quán đọc/ghi. Cơ chế chính là **Lightweight Transaction (LWT)** qua cú pháp CQL `IF`, sử dụng giao thức đồng thuận để xử lý cập nhật có điều kiện.

Sau bài này, bạn có thể:

- Nhận biết lỗi **lost update** và giải thích vì sao đọc/ghi ở `QUORUM` không tự ngăn lỗi này.
- Chọn khóa lạc quan bằng **cột `version`** hoặc bằng **cột `status`** tùy bất biến nghiệp vụ.
- Viết `INSERT ... IF NOT EXISTS`, `UPDATE ... IF version = ?` và `UPDATE ... IF status = ?`.
- Xử lý đúng `[applied] = false`, tranh chấp, timeout và yêu cầu gửi lại từ Java.
- Hiểu giới hạn của LWT khi dữ liệu trải trên nhiều partition, khi có tải tranh chấp cao và khi cần exactly-once.

## 1. Vì sao cần khóa lạc quan?

Giả sử một đơn hàng đang có `status = 'PENDING'` và `version = 7`. Hai tiến trình cùng đọc hàng này:

1. Tiến trình A muốn xác nhận thanh toán: chuyển sang `PAID`.
2. Tiến trình B muốn hủy đơn: chuyển sang `CANCELLED`.
3. Cả hai gửi `UPDATE` thông thường dựa trên kết quả đọc cũ.

Không có điều kiện bảo vệ, mỗi lệnh ghi có thể được Cassandra chấp nhận, và trạng thái cuối cùng phụ thuộc vào cách các giá trị ghi được hòa giải. Một cập nhật nghiệp vụ có thể bị cập nhật khác ghi đè.

~~~sql
-- KHÔNG AN TOÀN nếu nhiều tiến trình có thể ghi cùng đơn hàng.
UPDATE orders_by_id
SET status = 'PAID'
WHERE order_id = 11111111-1111-4111-8111-111111111111;

UPDATE orders_by_id
SET status = 'CANCELLED'
WHERE order_id = 11111111-1111-4111-8111-111111111111;
~~~

Việc client đọc và ghi ở `LOCAL_QUORUM` hoặc `QUORUM` không biến hai câu lệnh trên thành một phép **đọc–kiểm tra–ghi nguyên tử**. Consistency level quyết định mức xác nhận từ replica; nó không thay thế điều kiện cạnh tranh giữa các client.

Khóa lạc quan hoạt động theo nguyên tắc:

> Đọc bản ghi → chuẩn bị thay đổi → ghi **chỉ khi** phiên bản/trạng thái vẫn đúng như dự kiến → kiểm tra kết quả.

Không cần giữ một khóa ứng dụng trong suốt thời gian xử lý. Nếu một tiến trình khác đã thay đổi giá trị được bảo vệ, thao tác có điều kiện **không được áp dụng** và client phải quyết định cách xử lý xung đột.

## 2. Chuẩn bị bảng theo truy vấn

Ví dụ ứng dụng Java thường lấy một đơn hàng từ `order_id` và chuyển trạng thái của chính đơn đó. Thiết kế bảng theo truy vấn:

~~~sql
CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    status text,
    version int,
    amount_minor bigint,
    updated_at timestamp
);
~~~

Ở đây `order_id` là **partition key**. Tất cả thao tác đọc, kiểm tra và chuyển trạng thái trong ví dụ nhắm vào một partition xác định. `version` là một số nguyên thông thường do ứng dụng quản lý; nó **không phải kiểu `counter`**.

Khởi tạo một đơn hàng bằng LWT:

~~~sql
INSERT INTO orders_by_id (order_id, status, version, amount_minor)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'PENDING',
    0,
    125000
)
IF NOT EXISTS;
~~~

Nếu chưa có hàng tương ứng, Cassandra tạo hàng và trả về `[applied] = true`. Nếu hàng đã tồn tại, câu lệnh không ghi đè giá trị đang có và trả về `[applied] = false`. Đây là cách an toàn để tránh hai tiến trình cùng tự khởi tạo một bản ghi ở cùng khóa chính.

~~~sql
SELECT status, version, amount_minor
FROM orders_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
~~~

Một trạng thái ban đầu được tạo bằng `INSERT` thông thường cũng có thể tồn tại, nhưng `IF NOT EXISTS` đặc biệt hữu ích khi việc tạo mới phải chống cạnh tranh. Đừng giả định `UPDATE ... IF version = 0` sẽ tự khởi tạo hàng chưa có: điều kiện cần được thỏa bởi dữ liệu hiện tại.

## 3. Khóa lạc quan bằng cột version

Giả sử client vừa đọc `version = 0`, `status = 'PENDING'` và muốn chuyển trạng thái sang `PAID`. Client tính `newVersion = oldVersion + 1` rồi gửi:

~~~sql
UPDATE orders_by_id
SET status = 'PAID',
    version = 1,
    updated_at = toTimestamp(now())
WHERE order_id = 11111111-1111-4111-8111-111111111111
IF version = 0;
~~~

LWT kiểm tra điều kiện và thực hiện cập nhật như một thao tác có điều kiện trên partition liên quan:

| Giá trị hiện tại khi kiểm tra | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `version = 0` | `[applied] = true` | Chấp nhận cập nhật; version trở thành 1. |
| `version = 1` | `[applied] = false` | Có cập nhật khác đã tăng version, nên bản ghi client đọc đã cũ. |
| Hàng chưa tồn tại | `[applied] = false` | Không được phép giả định đã có bản ghi version 0. |

**Cassandra không tự tăng `int version` bằng `version = version + 1` như counter.** Ứng dụng phải tính giá trị mới và gửi cả giá trị mới lẫn điều kiện so khớp giá trị cũ. Chính điều kiện `IF version = oldVersion` giữ cho cập nhật không ghi đè bản ghi đã đổi.

Khi mọi thao tác sửa hàng đều tăng `version`, cột này bảo vệ đồng thời nhiều trường: `status`, `amount_minor` và các thuộc tính khác. Chỉ cần bỏ quên một đường ghi thông thường không cập nhật `version` là quy ước khóa lạc quan có thể bị phá vỡ. Vì vậy cần thống nhất quy tắc ở tất cả thành phần cùng ghi bảng.

### Hai client cạnh tranh một version

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant C as Cassandra
    A->>C: SELECT (version = 7, status = PENDING)
    B->>C: SELECT (version = 7, status = PENDING)
    A->>C: UPDATE status = PAID, version = 8 IF version = 7
    C-->>A: [applied] = true
    B->>C: UPDATE status = CANCELLED, version = 8 IF version = 7
    C-->>B: [applied] = false
    B->>C: SELECT trạng thái hiện tại
    C-->>B: version = 8, status = PAID
~~~

Đây là **phát hiện xung đột**, không phải cơ chế xếp hàng tự động thực thi lần lượt hai thay đổi. Client B phải kiểm tra luật nghiệp vụ trước khi quyết định có nên thử lại trên phiên bản mới.

## 4. Khóa lạc quan bằng cột status

Nếu nghiệp vụ chỉ cho phép một chuyển trạng thái cụ thể, dùng `status` làm điều kiện có thể rõ ràng hơn:

~~~sql
UPDATE orders_by_id
SET status = 'CANCELLED',
    version = 1
WHERE order_id = 11111111-1111-4111-8111-111111111111
IF status = 'PENDING';
~~~

Câu lệnh chỉ thành công khi trạng thái hiện tại là `PENDING`. Nếu đã `PAID`, client không thể hủy nhờ điều kiện này. Đây là mô hình **state transition có điều kiện**: chuyển trạng thái phụ thuộc vào trạng thái xuất phát.

Tuy nhiên, **chỉ kiểm tra status** có các giới hạn:

- Hai client có thể cùng sửa các trường khác mà `status` không đổi; điều kiện `IF status = 'PENDING'` của cả hai có thể lần lượt đúng, gây ghi đè thông tin.
- Nếu trạng thái có thể quay lại giá trị cũ, chẳng hạn `PENDING → REVIEW → PENDING`, client giữ kết quả đọc từ trước vòng chuyển trạng thái vẫn thấy `PENDING` và có thể thực hiện thao tác cũ. Đây là vấn đề **ABA**.
- Điều kiện status phù hợp khi chính chuyển trạng thái là bất biến cần bảo vệ, và mọi trạng thái được phép chuyển sang đã được xác định rõ.

Khi cần ngăn cả thay đổi khác xảy ra giữa hai lần đọc/ghi, hãy kiểm tra **cả version và status**:

~~~sql
UPDATE orders_by_id
SET status = 'PAID',
    version = 1,
    updated_at = toTimestamp(now())
WHERE order_id = 11111111-1111-4111-8111-111111111111
IF version = 0 AND status = 'PENDING';
~~~

Điều kiện gồm hai phần: hàng chưa bị sửa kể từ lần đọc (version) **và** vẫn ở trạng thái cho phép thanh toán (status). Nếu ứng dụng có nhiều luồng cập nhật trạng thái, kết hợp cả hai thường giúp diễn đạt bất biến rõ hơn.

### Chọn version hay status?

| Tiêu chí | `IF version = ?` | `IF status = ?` | Kết hợp cả hai |
| --- | --- | --- | --- |
| Mục tiêu chính | Phát hiện mọi thay đổi có tăng version | Bảo vệ một chuyển trạng thái | Vừa chống bản ghi cũ, vừa bảo vệ luật chuyển trạng thái |
| Không đổi status nhưng sửa trường khác | Phát hiện nếu đường ghi đó tăng version | Không tự phát hiện | Phát hiện nếu đường ghi tăng version |
| Chống tình huống trạng thái quay lại (ABA) | Có, khi version tăng liên tục | Không | Có |
| Phụ thuộc quy ước ứng dụng | Mọi đường ghi phải cập nhật version | Mọi chuyển trạng thái phải tuân luật | Cả hai quy ước |

Lưu ý: `IF EXISTS` chỉ kiểm tra hàng có tồn tại hay không. Nó **không** kiểm tra version hoặc trạng thái cũ, nên riêng `IF EXISTS` không đủ để chống lost update.

## 5. LWT làm gì bên trong?

Câu lệnh có `IF` là **Lightweight Transaction**: Cassandra phối hợp một vòng đồng thuận Paxos (và các giai đoạn cần thiết) để quyết định điều kiện và cập nhật. Các thao tác cạnh tranh trên cùng phạm vi được bảo vệ sẽ không cùng thắng nếu chúng cùng đòi một giá trị `version` cũ.

Phải phân biệt hai loại consistency level của một thao tác LWT:

| Loại | Ví dụ | Vai trò |
| --- | --- | --- |
| Consistency cho pha ghi/đọc thông thường | `LOCAL_QUORUM`, `QUORUM` | Quy định mức xác nhận từ replica cho phần thao tác thông thường. |
| **Serial consistency** cho pha điều kiện/đồng thuận | `LOCAL_SERIAL`, `SERIAL` | Quy định phạm vi đồng thuận của LWT. |

`LOCAL_SERIAL` phù hợp với một số hệ thống triển khai và ghi trong **một datacenter**. Nếu cùng một partition có thể nhận cập nhật điều kiện từ **nhiều datacenter**, phải xem xét phạm vi của `SERIAL` và mô hình replication; không nên mặc định phối hợp cục bộ ở nhiều DC độc lập sẽ bảo vệ toàn cục giống nhau. Kiểm tra topology và chính sách định tuyến client trước khi chọn consistency.

LWT có **chi phí nhiều bước liên lạc**, thường cao hơn `UPDATE` thông thường. Một khóa chính bị nhiều client tranh chấp sẽ gặp nhiều kết quả `[applied] = false`, tăng latency và giảm thông lượng. Chỉ dùng LWT khi thật sự cần điều kiện cạnh tranh; nếu chỉ lưu số liệu gần đúng hoặc đếm lượt xem với tải cao, cách thiết kế thường khác.

LWT bảo vệ thao tác có điều kiện trong phạm vi phân vùng phù hợp, **không phải giao dịch ACID xuyên tùy ý nhiều partition**. Một `SELECT` thông thường trước LWT có thể đọc bản cũ; tính đúng đắn của cập nhật đến từ `IF` lúc Cassandra xử lý, không phải từ việc ứng dụng giả định lần đọc trước đã khóa dữ liệu.

Replication, compaction và repair đều quan trọng đối với vận hành Cassandra, nhưng **không thay thế** câu lệnh `IF` để giải quyết tranh chấp giữa các cập nhật nghiệp vụ. Repair cũng không tự biết client nào đã cố chuyển đơn hàng theo một quyết định lỗi.

## 6. Xử lý kết quả và lỗi đúng cách

Khi gửi `UPDATE ... IF ...`, ứng dụng cần phân biệt ba trường hợp:

1. **`[applied] = true`:** Cassandra xác nhận điều kiện được thỏa và cập nhật đã được áp dụng. Có thể tiếp tục xử lý theo nhánh thành công.
2. **`[applied] = false`:** Cassandra xác nhận điều kiện không còn đúng. Đây là **xung đột nghiệp vụ hợp lệ**; đọc lại trạng thái/version, trả lỗi cạnh tranh hoặc tính lại thao tác theo luật cho phép.
3. **Timeout, mất kết nối, lỗi không rõ kết quả:** Client **chưa thể kết luận** thao tác thành công hay thất bại. Cần đối soát trạng thái hiện tại và định danh yêu cầu nếu nghiệp vụ đòi biết chính xác.

Trong `cqlsh`, cập nhật có điều kiện trả cột `[applied]`:

~~~text
 [applied]
-----------
      True
~~~

Khi điều kiện sai, hệ thống có thể trả thêm các giá trị hiện hành liên quan đến điều kiện. Không dựa vào việc luôn có đầy đủ mọi cột trong kết quả thất bại; dùng `SELECT` theo khóa chính khi cần xem đầy đủ bản ghi mới nhất.

### Retry khi tranh chấp

Một quy trình xử lý điển hình:

~~~text
Đọc (version = 7, status = PENDING)
    |
    v
Kiểm tra có được phép chuyển trạng thái không?
    |
    v
UPDATE ... SET version = 8 ... IF version = 7 AND status = 'PENDING'
    |
    +-- [applied] = true  --> Hoàn tất
    |
    +-- [applied] = false --> Đọc lại, đánh giá quy tắc nghiệp vụ
    |
    +-- timeout ----------> Kết quả chưa rõ, đối soát trước khi thử lại
~~~

Sau `[applied] = false`, **không tự động tăng version rồi gửi lại vô hạn**. Ví dụ, đơn đã thanh toán không thể tự động bị hủy chỉ vì tiến trình hủy đã tìm được version mới. Thử lại chỉ hợp lệ khi trạng thái mới vẫn cho phép hành động; cần giới hạn số lần retry, dùng backoff và ghi nhận contention.

Một lần gửi lại **chính cùng câu lệnh** có `IF version = 7` sau khi lần đầu đã thành công có thể trả `[applied] = false` vì version đã là 8. Khi đó `false` không cho biết chắc lần đầu do chính client này thực hiện hay do client khác. Nếu yêu cầu nghiệp vụ phải xác định *một yêu cầu* đã được xử lý chưa, có thể lưu `operation_id` cùng bản ghi trong LWT và thiết kế quy tắc kiểm tra sau timeout. Một cột `last_operation_id` đơn lẻ chỉ giúp nhận diện thao tác gần nhất còn lưu; nó không thay thế nhật ký idempotency bền vững khi có nhiều thao tác tiếp theo.

**LWT không tự đảm bảo exactly-once cho toàn bộ quy trình ngoài Cassandra**, chẳng hạn gọi cổng thanh toán, gửi email, phát sự kiện hoặc sửa nhiều partition. Đặc biệt tránh gọi hệ thống bên ngoài trước khi chắc chắn đã giành quyền chuyển trạng thái và có phương án phục hồi khi hệ thống ngoài lỗi.

## 7. Ví dụ Java với Cassandra Driver 4.x

Giả sử `CqlSession` đã được cấu hình keyspace và datacenter hợp lệ. Đoạn mã dưới đây đọc version hiện tại, kiểm tra luật nghiệp vụ rồi gửi CAS (`compare-and-set`) có điều kiện:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.util.UUID;

public final class OrderStateService {
    private final CqlSession session;
    private final PreparedStatement loadOrder;
    private final PreparedStatement payIfPending;

    public OrderStateService(CqlSession session) {
        this.session = session;
        this.loadOrder = session.prepare(
            "SELECT status, version FROM orders_by_id WHERE order_id = ?");
        this.payIfPending = session.prepare(
            "UPDATE orders_by_id SET status = ?, version = ? " +
            "WHERE order_id = ? IF status = ? AND version = ?");
    }

    // true: thao tác này thắng CAS; false: hàng vắng mặt hoặc xung đột.
    // Timeout được để cho lớp gọi xử lý như một kết quả chưa xác định.
    public boolean markPaid(UUID orderId) {
        Row current = session.execute(loadOrder.bind(orderId)).one();
        if (current == null || !"PENDING".equals(current.getString("status"))) {
            return false;
        }

        int expectedVersion = current.getInt("version");
        int nextVersion = Math.incrementExact(expectedVersion);

        BoundStatement cas = payIfPending.bind(
                "PAID", nextVersion, orderId, "PENDING", expectedVersion)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
            .setIdempotence(false);

        Row result = session.execute(cas).one();
        if (result == null) {
            throw new IllegalStateException("LWT không trả kết quả");
        }
        return result.getBoolean("[applied]");
    }
}
~~~

Giải thích:

- `loadOrder` lấy ảnh chụp trạng thái để quyết định hành động. Không có khóa được giữ trong khoảng thời gian giữa `SELECT` và `UPDATE`.
- `payIfPending` gửi **cả status cũ lẫn version cũ**. Nếu ai đó sửa hàng trong khoảng giữa, điều kiện bảo vệ phát hiện xung đột.
- `Math.incrementExact` ngăn ứng dụng âm thầm tràn số nguyên 32 bit; hệ thống lớn nên có chính sách vòng đời version hoặc chọn kiểu đủ rộng theo nhu cầu.
- `LOCAL_QUORUM` và `LOCAL_SERIAL` là **cấu hình minh họa**, cần điều chỉnh theo replication/topology thực tế.
- `setIdempotence(false)` làm rõ rằng lớp gọi không nên mặc định phát lại khi kết quả chưa xác định. Ngay cả câu CAS lặp lại có thể tránh ghi đè nhờ điều kiện, kết quả lần thử lại vẫn có thể khác và phải được diễn giải theo nghiệp vụ.
- Với `false`, lớp gọi nên đọc lại và trả lỗi xung đột, hoặc chỉ thử lại sau khi kiểm tra trạng thái mới vẫn hợp lệ.

Thực tế, các `PreparedStatement` nên được chuẩn bị một lần và tái sử dụng; theo dõi timeout, số lần CAS không được áp dụng, độ trễ và tải trên partition. Tránh tạo vòng retry đồng loạt gây thêm tranh chấp.

## 8. Lỗi thiết kế phổ biến

| Lỗi | Tác hại | Cách sửa |
| --- | --- | --- |
| `SELECT` rồi `UPDATE` không `IF` | Có thể lost update giữa hai client | Dùng `IF version = ?` hoặc điều kiện trạng thái phù hợp |
| Chỉ dùng `IF EXISTS` | Không phát hiện bản ghi đã bị sửa | So sánh giá trị cũ qua `IF` |
| Có `version` nhưng vài đường ghi không tăng nó | CAS có thể bỏ sót thay đổi | Thống nhất mọi cập nhật đều dùng quy ước version |
| Dùng `counter` làm version | Counter không phù hợp với LWT có điều kiện | Dùng `int` hoặc `bigint` thường, gửi giá trị mới từ ứng dụng |
| Retry vô hạn sau `[applied] = false` | Đánh sai luật nghiệp vụ, tạo tải cao | Đọc lại, xác minh chuyển trạng thái, giới hạn retry |
| Xem timeout là thất bại chắc chắn | Có thể xử lý một yêu cầu lần nữa | Đối soát bằng trạng thái và định danh nghiệp vụ |
| Dùng LWT cho mọi phép ghi | Tăng round trip và giảm throughput | Chỉ bảo vệ những bất biến cần CAS |
| Tin rằng LWT bảo vệ nhiều partition bất kỳ | Sai về phạm vi nguyên tử | Thiết kế partition quanh bất biến hoặc dùng quy trình điều phối khác |

## 9. Bài thực hành

**Bài 1 — Chuyển trạng thái thành công.** Tạo bảng `orders_by_id`, chạy `INSERT ... IF NOT EXISTS` ở mục 2 rồi chạy `UPDATE ... IF version = 0 AND status = 'PENDING'` ở mục 4. Kiểm tra `[applied] = true` và `SELECT` cho thấy `status = 'PAID'`, `version = 1`.

**Bài 2 — Phát hiện stale version.** Gửi lại chính câu `UPDATE` dựa trên `version = 0`. Quan sát `[applied] = false`; hàng không trở lại phiên bản cũ. Giải thích vì sao giá trị `false` là thông tin về **điều kiện tại thời điểm xử lý**, không phải chứng cứ duy nhất để biết lịch sử mọi lần gửi.

**Bài 3 — So sánh version và status.** Tạo đơn mới. Cho một client thay đổi một trường nghiệp vụ nhưng giữ `status = 'PENDING'`; cho client khác thực hiện `UPDATE ... IF status = 'PENDING'`. Giải thích vì sao thao tác thứ hai vẫn có thể được chấp nhận. Thiết kế lại bằng cách tăng và kiểm tra `version` ở cả hai luồng ghi.

**Bài 4 — Hai Java client chạy đồng thời.** Cả hai đọc cùng một version, một client đánh dấu `PAID` và client kia muốn `CANCELLED`. Dùng điều kiện kết hợp để chỉ một chuyển trạng thái hợp lệ được chấp nhận. Đếm kết quả `[applied]`, đọc trạng thái cuối và ghi lại cách ứng dụng xử lý xung đột.

**Bài 5 — Sự cố và replication.** Giả lập tình huống client timeout sau khi đã gửi LWT. Viết quy trình đối soát trước khi thử lại, giải thích khi nào cần `SERIAL` thay vì `LOCAL_SERIAL` nếu hệ thống cho phép cập nhật từ nhiều datacenter. Nêu rõ việc chạy repair không thể giải quyết quyết định nghiệp vụ phải retry hay không.

## Ghi nhớ

**Khóa lạc quan trong Cassandra dùng LWT và điều kiện CQL `IF` để kiểm tra dữ liệu ngay khi cập nhật.** `version` phát hiện bản ghi đã thay đổi; `status` bảo vệ chuyển trạng thái; kết hợp cả hai giúp diễn đạt chính xác hơn luật nghiệp vụ. Luôn xử lý tách biệt `[applied] = true`, `[applied] = false` và timeout, đồng thời thiết kế partition và serial consistency phù hợp với phạm vi tranh chấp thực tế.
