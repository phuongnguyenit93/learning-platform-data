# IF NOT EXISTS, IF EXISTS và điều kiện trên giá trị hiện tại trong Spring Data Cassandra

## 1. Khi một thao tác ghi cần kiểm tra trạng thái trước đó

Một ứng dụng đặt hàng có nhiều instance Spring Boot. Hai request đồng thời gửi lệnh **tạo cùng một mã đơn hàng**. Cả hai request có thể cùng gọi `existsById(orderId)`, thấy chưa có dữ liệu rồi lần lượt gọi `save(...)`. Kết quả cuối cùng có thể là một lần ghi **ghi đè** lên lần còn lại, bởi vì Cassandra thông thường sử dụng ngữ nghĩa **upsert**.

Một vấn đề khác xuất hiện khi nhân viên thanh toán và nhân viên hủy đơn cùng đọc thấy `state = CREATED`. Nếu cả hai dùng `UPDATE` không điều kiện, Cassandra có thể xác nhận cả hai mutation mà không hề hiểu rằng nghiệp vụ **không cho phép hủy đơn đã thanh toán**.

Để giải quyết những vấn đề đó, Apache Cassandra hỗ trợ **conditional write** qua các mệnh đề CQL:

- `INSERT ... IF NOT EXISTS`: chỉ tạo hàng khi chưa tồn tại tại khóa mục tiêu.
- `UPDATE ... IF EXISTS`: chỉ cập nhật hàng nếu hàng tồn tại.
- `DELETE ... IF EXISTS`: chỉ xóa nếu hàng tồn tại.
- `UPDATE ... IF state = ?` hoặc `IF version = ?`: chỉ áp dụng mutation nếu giá trị hiện tại thỏa điều kiện.

Các conditional write này được thực hiện thông qua cơ chế **lightweight transaction (LWT)**, dựa trên Paxos. Chúng phục vụ các bất biến nghiệp vụ cục bộ mà **timestamp/last-write-wins** và **consistency level đọc–ghi thông thường** không tự bảo vệ.

Bài học thuộc chương **LWT và khóa lạc quan**, trong module **SPRING_DATA_CASSANDRA**. Bạn sẽ sử dụng Spring Data Cassandra repository, `@Query`, `CassandraTemplate` và `CqlSession`, đồng thời liên hệ với thiết kế bảng theo truy vấn, partition key, consistency, paging và kiểm soát hiệu năng cho cơ sở dữ liệu phân tán.

**Mục tiêu học tập:**

1. Viết được ba nhóm câu CQL `IF NOT EXISTS`, `IF EXISTS` và điều kiện trên giá trị hiện tại.
2. Phân biệt **điều kiện được áp dụng**, **điều kiện không thỏa** và **không có kết quả hợp lệ vì lỗi**.
3. Chọn đúng điều kiện để bảo vệ **create-only**, **update-only**, **state transition** hoặc **optimistic locking bằng version**.
4. Đọc cờ `[applied]` qua Java driver 4.x và xử lý ở tầng service/HTTP.
5. Hiểu giới hạn của LWT về topology, chi phí, retry, idempotency và các thao tác trên nhiều bảng/partition.
6. Kiểm thử được tranh chấp hai writer trên Cassandra thật.

## 2. Chuẩn bị một bảng phù hợp cho ví dụ

Ta xây API đơn hàng có truy vấn chính là **tìm theo `order_id`**. Bảng:

~~~sql
-- app_ks là keyspace thử nghiệm đã tồn tại, với replication phù hợp.
CREATE TABLE app_ks.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    state text,
    version bigint,
    total_cents bigint,
    last_command_id uuid,
    updated_at timestamp
);
~~~

| Cột | Vai trò | Ghi chú |
| --- | --- | --- |
| `order_id` | Partition key, cũng là toàn bộ primary key | Mỗi order ID định vị một hàng |
| `customer_id` | Cột thông thường | Khách hàng sở hữu đơn |
| `state` | Cột thông thường | `CREATED`, `PAID`, `CANCELLED` |
| `version` | Cột thông thường | Số phiên bản logic để phát hiện stale update |
| `total_cents` | Cột thông thường | Tiền tính bằng đơn vị nhỏ nhất |
| `last_command_id` | Cột thông thường | Hỗ trợ đối chiếu một command đã áp dụng |
| `updated_at` | Cột thông thường | Thời điểm nghiệp vụ; **không** thay thế version |

**Vì sao chọn khóa đơn giản?** Tất cả những câu điều kiện sau đều tác động đến **một hàng xác định qua `order_id`**. Điều này giúp người học thấy rõ ranh giới kiểm tra CAS, không nhầm với việc tìm theo `state` hoặc `customer_id` trên toàn cluster.

Khi dùng bảng có khóa tổng hợp, cần định vị hàng/partition theo quy tắc CQL tương ứng; không được suy luận `IF EXISTS` có thể tìm bất kỳ hàng nào chỉ dựa vào một cột thường.

## 3. INSERT và UPDATE thông thường không có ràng buộc tồn tại

Cassandra thường hiểu `INSERT` và `UPDATE` theo ngữ nghĩa **upsert**, khác với một số RDBMS:

~~~sql
-- Nếu đã có hàng cùng order_id, giá trị được ghi có thể thay thế cột cũ.
INSERT INTO app_ks.orders_by_id
    (order_id, customer_id, state, version, total_cents)
VALUES (?, ?, 'CREATED', 1, ?);

-- Nếu hàng chưa tồn tại, UPDATE thông thường cũng có thể tạo hàng.
UPDATE app_ks.orders_by_id
SET state = 'PAID'
WHERE order_id = ?;
~~~

Sự thật này quan trọng khi ứng dụng cần **“chỉ tạo mới”** hoặc **“chỉ sửa cái đã có”**. Một `save(...)` trả về entity không có nghĩa Cassandra đã kiểm tra “hàng này chưa tồn tại”.

### 3.1. Vì sao existsById rồi save không an toàn?

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant C as Cassandra
    participant B as Request B
    A->>C: SELECT theo order_id
    C-->>A: Chưa có
    B->>C: SELECT theo order_id
    C-->>B: Chưa có
    A->>C: INSERT không điều kiện
    C-->>A: Success
    B->>C: INSERT không điều kiện
    C-->>B: Success
    Note over C: Hai lượt kiểm tra không ràng buộc nguyên tử lượt ghi
~~~

Cho dù cả hai lượt đọc/ghi dùng `LOCAL_QUORUM` và replication factor phù hợp, chúng vẫn là **những thao tác tách biệt**. Giữa `existsById` và `save`, writer khác có thể ghi. Đây là lỗi **check-then-act**.

**Cách sửa khi cần create-only:** dùng **một conditional insert** `IF NOT EXISTS` để Cassandra quyết định tại thời điểm ghi.

## 4. INSERT ... IF NOT EXISTS: tạo khi chưa có hàng

### 4.1. Cú pháp và bind parameters

~~~sql
INSERT INTO app_ks.orders_by_id
    (order_id, customer_id, state, version,
     total_cents, last_command_id, updated_at)
VALUES (?, ?, 'CREATED', 1, ?, ?, ?)
IF NOT EXISTS;
~~~

Nếu hàng tại `order_id` chưa tồn tại, Cassandra có thể áp dụng mutation và trả một kết quả điều kiện có cờ:

~~~text
 [applied]
-----------
 True
~~~

Nếu hàng đã tồn tại, thao tác **không thay thế** hàng đó và trả:

~~~text
 [applied] | ... các giá trị hiện có tùy kết quả server ...
-----------+---------------------------------------------
 False     | ...
~~~

**Không được** viết logic phụ thuộc vào việc mọi cột hiện tại chắc chắn có trong result khi `false`. Thông tin cốt lõi, ổn định để quyết định đã tạo hay chưa là **`[applied]`**; các cột bổ trợ phải được kiểm tra theo API/metadata thực tế.

### 4.2. Hai request cùng ID

Giả sử A và B cùng muốn tạo `order_id = X` với `total_cents` khác nhau. Hai lệnh `INSERT ... IF NOT EXISTS` cạnh tranh trên cùng khóa. Trong điều kiện thao tác LWT hoàn tất hợp lệ, **không phải cả hai đều được áp dụng như hai lần tạo độc lập**: một lệnh có thể được áp dụng, lệnh kia nhận `false`.

~~~mermaid
flowchart TD
    A[Request tạo đơn với order_id X] --> B[INSERT IF NOT EXISTS]
    B --> C{Kết quả?}
    C -->|applied = true| D[Đã tạo đơn mới]
    C -->|applied = false| E[Đã có hàng ở khóa X]
    C -->|timeout hoặc lỗi| F[Trạng thái chưa xác định / lỗi]
    E --> G[Đối chiếu command ID nếu cần idempotency]
~~~

Điều kiện `IF NOT EXISTS` bảo vệ **tính duy nhất của hàng theo primary key**. Nó không tự bảo vệ:

- Mỗi khách hàng chỉ có một đơn hàng trên toàn bộ keyspace.
- Một email không bao giờ xuất hiện trong bảng khác.
- Một command trùng ý định nhưng sử dụng **hai order ID khác nhau**.
- Ghi thêm bảng timeline và bảng tìm kiếm cùng một giao dịch ACID toàn cục.

Nếu muốn duy nhất theo **email hoặc username**, phải thiết kế bảng/khóa phục vụ chính bất biến đó, rồi áp dụng CAS tại khóa thích hợp.

### 4.3. Tạo lại sau TTL hoặc DELETE

`IF NOT EXISTS` kiểm tra sự tồn tại **theo trạng thái dữ liệu hiện hành mà Cassandra xác định trong conditional operation**. Nếu hàng đã bị xóa hoặc hết TTL và không còn được xem là tồn tại, một lần tạo mới có thể được chấp nhận.

Vì vậy, **“chưa tồn tại lúc này” khác “chưa từng được cấp phát”**. Nếu order ID hoặc reservation phải duy nhất vĩnh viễn, hãy xây chính sách retention/tombstone và bảng định danh bền vững; không dựa vào một hàng hết TTL để bảo vệ một ID suốt đời.

## 5. UPDATE ... IF EXISTS: chỉ sửa hàng đã tồn tại

Một yêu cầu nghiệp vụ thường gặp:

> “Nếu đơn hàng đã tồn tại thì cập nhật trạng thái; nếu chưa có, không tạo hàng mới.”

Câu CQL:

~~~sql
UPDATE app_ks.orders_by_id
SET state = ?, updated_at = ?
WHERE order_id = ?
IF EXISTS;
~~~

| Tình huống | `[applied]` | Ý nghĩa |
| --- | --- | --- |
| Hàng đang tồn tại và mutation hoàn tất | `true` | Thao tác update-only được áp dụng |
| Không có hàng tại khóa mục tiêu | `false` | Không tạo hàng mới |
| Cassandra timeout hoặc không đủ replica | Không có cờ hợp lệ | Chưa có kết luận chắc chắn về kết quả |

`UPDATE ... IF EXISTS` đặc biệt hữu ích để tránh **accidental upsert**. Nhưng nó **không** nói trạng thái đang là `CREATED` hay `CANCELLED`, và cũng không kiểm tra version.

**Ví dụ nguy hiểm:**

~~~sql
UPDATE app_ks.orders_by_id
SET state = 'PAID'
WHERE order_id = ?
IF EXISTS;
~~~

Nếu đơn hàng **đang là `CANCELLED`** nhưng còn tồn tại, lệnh có thể được áp dụng. Với quy tắc “chỉ thanh toán đơn còn CREATED”, điều kiện **tồn tại** là chưa đủ. Cần `IF state = 'CREATED'` hoặc kiểm tra version/state tương ứng.

## 6. DELETE ... IF EXISTS: xóa có kiểm tra tồn tại

Nếu API cần biết một hàng có tồn tại trước khi xóa, có thể dùng:

~~~sql
DELETE FROM app_ks.orders_by_id
WHERE order_id = ?
IF EXISTS;
~~~

Một lần `[applied] = true` nghĩa là conditional delete đã được áp dụng. `false` nghĩa điều kiện tồn tại không thỏa. Với API xóa **idempotent** mà “xóa hàng không có sẵn” vẫn là thành công, có thể không cần LWT:

~~~sql
-- Xóa không điều kiện: có thể được thiết kế là idempotent ở API.
DELETE FROM app_ks.orders_by_id
WHERE order_id = ?;
~~~

**Đánh đổi:** `DELETE IF EXISTS` tốn chi phí đồng thuận để biết “đã tồn tại hay chưa”. Nếu API chỉ cần đảm bảo sau thao tác hàng không còn hiển thị theo contract, thường không nên trả thêm chi phí LWT chỉ để phân biệt một trường hợp không cần thiết.

Xóa trong Cassandra liên quan đến **tombstone**. `IF EXISTS` không loại bỏ tombstone và không làm compaction hay repair trở nên miễn phí. Nếu dữ liệu phục vụ event log/audit, cần xem kỹ retention trước khi xóa.

## 7. Điều kiện trên giá trị hiện tại: IF state = ?

Thay vì chỉ hỏi hàng tồn tại, ứng dụng có thể hỏi:

> “Đơn hàng **vẫn đang là CREATED** vào lúc Cassandra quyết định mutation chứ?”

~~~sql
UPDATE app_ks.orders_by_id
SET state = 'PAID', updated_at = ?
WHERE order_id = ?
IF state = 'CREATED';
~~~

Nếu một writer khác đã chuyển state thành `CANCELLED` trước khi điều kiện được quyết định, mutation chuyển sang `PAID` không được áp dụng và `[applied] = false`.

~~~mermaid
sequenceDiagram
    participant A as Thanh toán
    participant DB as Cassandra LWT
    participant B as Hủy đơn
    A->>DB: IF state=CREATED SET state=PAID
    B->>DB: IF state=CREATED SET state=CANCELLED
    DB-->>A: Một request có thể applied=true
    DB-->>B: Request còn lại có thể applied=false
~~~

Kết quả cụ thể tùy request nào thắng đồng thuận. **Không mặc định A luôn thắng** chỉ vì sơ đồ đặt A bên trái.

### 7.1. Khi IF state không đủ

Một lệnh chỉ kiểm tra `state = CREATED` có thể **không phát hiện** thay đổi ở những cột khác nếu state vẫn giữ nguyên. Ví dụ nhân viên sửa địa chỉ giao hàng, một worker khác đọc bản cũ rồi sửa tổng tiền; cả hai vẫn thấy `state = CREATED`.

Nếu nghiệp vụ cần phát hiện **bất kỳ sửa đổi nào trong một tập field**, hãy dùng số `version` logic hoặc điều kiện trên nhiều giá trị phù hợp CQL. `IF state = ?` phù hợp hơn cho **state transition** đơn giản.

## 8. IF version = ?: optimistic locking rõ ràng

Một cách thường dùng để tránh **lost update** là optimistic concurrency control:

1. Đọc hàng và ghi nhớ `version = N`.
2. Tạo mutation muốn cập nhật, dự kiến `newVersion = N + 1`.
3. Gửi conditional update với `IF version = N`.
4. Nếu `true`: lệnh được áp dụng. Nếu `false`: dữ liệu đã đổi hoặc không còn thỏa điều kiện.

Ví dụ dữ liệu:

~~~text
order_id = ...
state = CREATED
version = 7
total_cents = 125000
~~~

Conditional update:

~~~sql
UPDATE app_ks.orders_by_id
SET state = ?, version = ?, updated_at = ?
WHERE order_id = ?
IF version = ?;
~~~

Giá trị bind minh họa:

~~~text
state           = "PAID"
new_version     = 8
updated_at      = "2026-11-25T09:00:00Z"
order_id        = UUID đơn hàng
expectedVersion = 7
~~~

Hai writer cùng kỳ vọng version 7 **không thể cùng cập nhật thành công như hai CAS độc lập trên cùng trạng thái version 7**, nếu không có ghi ngoài luồng phá quy tắc. Writer thua phải đọc lại và quyết định có thử lại trên dữ liệu mới không, thay vì tự chuyển sang ghi không điều kiện.

### 8.1. Vì sao version khác timestamp?

- `version` là **số thứ tự logic** do ứng dụng/quy trình cập nhật quản lý.
- `updated_at` là **thời điểm nghiệp vụ**, có thể cùng thời điểm hoặc lệch do clock.
- **Write timestamp của Cassandra** quyết định cách hòa giải cell; nó không thay thế kiểm tra `IF version`.

Hai request có thể mang cùng timestamp mili giây hoặc timestamp bị lệch; version guard vẫn mô tả rõ điều kiện “chỉ ghi nếu bản đang lưu còn là bản tôi đã đọc”.

### 8.2. Các quy tắc để version guard có ý nghĩa

1. Khởi tạo `version` ngay khi tạo hàng, ví dụ 1.
2. Mọi code path **sửa các field được bảo vệ** phải kiểm tra và tăng version nhất quán.
3. Không để một `repository.save(...)` không điều kiện vô tình bỏ qua chính sách CAS.
4. Không tự reset/reuse version khi hàng đã tồn tại.
5. Định nghĩa cách migration dữ liệu cũ có `version = null`, không giả định null bằng 0.
6. Nếu có thao tác xóa–tạo lại cùng ID, xem xét **ABA problem**: version và trạng thái có thể trùng lại trong một đời sống khác của aggregate; cần quy tắc vòng đời/epoch hoặc ID bất biến nếu rủi ro đó quan trọng.
7. Bảo vệ chống **integer overflow**, dùng kiểu số và chính sách phù hợp.

### 8.3. Kết hợp state và version

Đối với lệnh thanh toán, có thể kiểm tra **cả hai**:

~~~sql
UPDATE app_ks.orders_by_id
SET state = 'PAID', version = ?, updated_at = ?
WHERE order_id = ?
IF version = ? AND state = 'CREATED';
~~~

Đây là cách diễn đạt rõ: dữ liệu chưa bị thay đổi kể từ lúc đọc **và** state còn cho phép thanh toán. Cần kiểm chứng cú pháp các điều kiện theo phiên bản CQL đang dùng. Khi điều kiện không thỏa, server có thể trả giá trị hiện tại để điều tra, nhưng service vẫn nên dựa trên `[applied]` và đọc lại khi cần lý do chính xác.

## 9. So sánh bốn điều kiện phổ biến

| Điều kiện CQL | Kiểm tra gì? | Trường hợp thích hợp | Không đủ khi nào? |
| --- | --- | --- | --- |
| `INSERT IF NOT EXISTS` | Hàng tại khóa chưa có | Create-only, reservation theo khóa | Cần kiểm tra trạng thái ở một hàng/bảng khác |
| `UPDATE IF EXISTS` | Hàng tại khóa còn tồn tại | Update-only, tránh upsert | State machine/version concurrency |
| `DELETE IF EXISTS` | Hàng tại khóa còn tồn tại | API cần phân biệt xóa có dữ liệu | Xóa idempotent đơn giản không cần biết tồn tại |
| `UPDATE IF state = ?` | Giá trị state hiện tại khớp | Chuyển trạng thái có điều kiện | Các field khác đổi nhưng state giữ nguyên |
| `UPDATE IF version = ?` | Phiên bản logic khớp | Optimistic locking | Có code path khác bỏ qua version |
| `UPDATE IF version = ? AND state = ?` | Version và state cùng khớp | Quy tắc cập nhật quan trọng | Bất biến nằm ở nhiều partition/bảng |

**Lựa chọn đúng không nhất thiết là điều kiện phức tạp nhất.** Mỗi điều kiện bổ sung nên xuất phát từ một bất biến nghiệp vụ đã mô tả được.

## 10. LWT và cờ [applied]: ba kết quả phải tách biệt

Câu conditional write trả một result set đặc biệt có cột `[applied]`. Hãy phân biệt:

~~~mermaid
flowchart TD
    A[Thực thi conditional mutation] --> B{Nhận kết quả hợp lệ?}
    B -->|Có| C{applied?}
    C -->|true| D[APPLIED: điều kiện thỏa]
    C -->|false| E[NOT_APPLIED: điều kiện không thỏa]
    B -->|Không| F[ERROR hoặc trạng thái chưa xác định]
    E --> G[Đối chiếu lý do theo loại lệnh]
    F --> H[Phân loại lỗi; không suy thành false]
~~~

| Kết quả | Ý nghĩa ở tầng CQL | Hành động ứng dụng |
| --- | --- | --- |
| `[applied] = true` | Cassandra áp dụng mutation có điều kiện | Trả thành công theo use case |
| `[applied] = false` | Conditional operation hoàn tất nhưng điều kiện không thỏa | Đã tồn tại / không tồn tại / stale version / conflict tùy lệnh |
| `ReadTimeout`, `WriteTimeout`, `Unavailable` hoặc lỗi khác | Không có kết quả điều kiện thành công để giải thích | Phân loại, log và xử lý trạng thái chưa rõ; không báo false giả |

Một ngoại lệ do **schema sai**, **không đủ quyền** hoặc **tham số invalid** phải được nhận diện là lỗi cấu hình/input. Một timeout có thể để lại **outcome chưa chắc chắn**; không xem tất cả exception có cùng nguyên nhân.

### 10.1. False không đồng nghĩa 404

- `INSERT IF NOT EXISTS` trả false → thường là **đã có hàng**, có thể báo 409 hoặc idempotent replay.
- `UPDATE IF EXISTS` trả false → thường là **không có hàng**, có thể báo 404.
- `UPDATE IF version = ?` trả false → **conflict/stale state** hoặc hàng bị xóa; thường 409, đôi khi cần đọc lại.
- `DELETE IF EXISTS` trả false → hàng đã vắng mặt; API xóa idempotent có thể vẫn trả 204.

Không được viết một handler `if (!applied) return 404;` dùng chung cho tất cả loại CAS.

### 10.2. Các cột hiện tại được trả khi false

Một số dạng conditional query trả thêm **các giá trị đang lưu** khi điều kiện không thỏa. Tuy nhiên:

- Tập cột được trả khác nhau theo lệnh và phiên bản Cassandra.
- Có thể không bao gồm mọi cột entity.
- Một giá trị null trong kết quả **không luôn đồng nghĩa toàn bộ hàng không tồn tại**.
- Giá trị quan sát được có thể thay đổi sau khi LWT kết thúc nếu writer khác hoạt động.

Nếu service cần phân biệt chi tiết lý do conflict, hãy thực hiện **lookup có kiểm soát sau kết quả false** và chấp nhận khả năng dữ liệu lại thay đổi; tránh coi result false là một snapshot bất biến vô hạn.

## 11. Java driver 4.x: ResultSet.wasApplied()

Khi nghiệp vụ cần biết chính xác điều kiện được áp dụng hay không, Java driver cung cấp phương thức **`ResultSet.wasApplied()`**.

### 11.1. Gateway chuẩn bị câu lệnh một lần

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public final class OrderCasGateway {
    private final CqlSession session;
    private final PreparedStatement createIfAbsent;
    private final PreparedStatement updateIfVersion;
    private final PreparedStatement updateIfPresent;

    public OrderCasGateway(CqlSession session) {
        this.session = Objects.requireNonNull(session);
        this.createIfAbsent = session.prepare(
            "INSERT INTO app_ks.orders_by_id " +
            "(order_id, customer_id, state, version, " +
            " total_cents, last_command_id, updated_at) " +
            "VALUES (?, ?, 'CREATED', 1, ?, ?, ?) " +
            "IF NOT EXISTS"
        );
        this.updateIfVersion = session.prepare(
            "UPDATE app_ks.orders_by_id " +
            "SET state = ?, version = ?, " +
            "last_command_id = ?, updated_at = ? " +
            "WHERE order_id = ? " +
            "IF version = ? AND state = ?"
        );
        this.updateIfPresent = session.prepare(
            "UPDATE app_ks.orders_by_id " +
            "SET updated_at = ? WHERE order_id = ? IF EXISTS"
        );
    }

    public boolean create(
            UUID orderId, UUID customerId, long cents,
            UUID commandId, Instant now) {
        ResultSet result = session.execute(
            createIfAbsent.bind(orderId, customerId, cents,
                                commandId, now)
        );
        return result.wasApplied();
    }

    public boolean payIfUnchanged(
            UUID orderId, long expectedVersion,
            UUID commandId, Instant now) {
        if (expectedVersion == Long.MAX_VALUE) {
            throw new IllegalArgumentException("Version overflow");
        }
        ResultSet result = session.execute(
            updateIfVersion.bind(
                "PAID", expectedVersion + 1,
                commandId, now, orderId,
                expectedVersion, "CREATED")
        );
        return result.wasApplied();
    }

    public boolean touchIfPresent(UUID orderId, Instant now) {
        ResultSet result = session.execute(
            updateIfPresent.bind(now, orderId)
        );
        return result.wasApplied();
    }
}
~~~

Đoạn code minh họa **Java driver 4.x**, giả định `app_ks` đã có và dùng `CqlSession` được quản lý trong ứng dụng. Các tham số phải được validate ở service hoặc gateway theo hợp đồng; `null`/UNSET cho từng kiểu cần được xử lý có chủ đích, không truyền bừa để Cassandra tự đoán.

**Các điểm quan trọng:**

1. `PreparedStatement` là mẫu cố định, có thể tái sử dụng khi cùng `CqlSession` còn sống.
2. Mỗi request tạo `BoundStatement` mới từ `bind(...)`, tránh lẫn giá trị giữa các thread.
3. Không nối giá trị UUID hoặc state từ HTTP request trực tiếp vào CQL.
4. `wasApplied()` có ý nghĩa đối với **conditional write**; đừng dùng nó để suy ra số hàng thay đổi ở một `UPDATE` thông thường.
5. Nếu `session.execute(...)` ném exception, method **không trả false**; caller nhận lỗi và xử lý theo chính sách.
6. Một lần trả true không đồng nghĩa thao tác ở **bảng denormalized thứ hai** cũng đã thành công.

### 11.2. Cách lấy thêm giá trị hiện tại

Khi một LWT thất bại, có thể cần thông tin bổ trợ về phiên bản đang lưu:

~~~java
ResultSet result = session.execute(boundConditionalUpdate);

if (result.wasApplied()) {
    return TransitionResult.applied();
}

// Nếu cần lý do chính xác, đọc lại bằng SELECT theo primary key.
return TransitionResult.conflict();
~~~

`TransitionResult` là kiểu kết quả do ứng dụng định nghĩa. Ví dụ cố ý không gọi `result.one().getLong("version")` một cách mù quáng, vì những cột trả về khi `false` không phải lúc nào cũng khớp một projection entity hoàn chỉnh.

Nếu đọc lại để giải thích conflict, phải hiểu đó là **một truy vấn mới**, có thể quan sát giá trị khác do write đồng thời. Không nên dùng phần thông báo lỗi như điều kiện CAS thay thế.

## 12. Spring Data Cassandra: @Query, @Modifying và giới hạn kiểu trả về

Repository với entity mapping vẫn rất hữu ích để **đọc hàng theo khóa**:

~~~java
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_id")
public class OrderRow {
    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("state")
    private String state;

    @Column("version")
    private Long version;

    @Column("updated_at")
    private Instant updatedAt;

    protected OrderRow() {}

    public UUID getOrderId() { return orderId; }
    public String getState() { return state; }
    public Long getVersion() { return version; }
    public Instant getUpdatedAt() { return updatedAt; }
}
~~~

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrderRepository
        extends CassandraRepository<OrderRow, UUID> {
    // findById(...) và các thao tác repository được kế thừa.
}
~~~

Với CQL điều kiện, Spring Data Cassandra có thể cho khai báo `@Query` và các cơ chế modifying query tùy dòng thư viện:

~~~java
import org.springframework.data.cassandra.repository.Modifying;
import org.springframework.data.cassandra.repository.Query;

// Khai báo bên trong repository tương thích với phiên bản thư viện.
@Modifying
@Query("UPDATE app_ks.orders_by_id " +
       "SET state = ?0 WHERE order_id = ?1 IF EXISTS")
void updateExistingState(String state, UUID orderId);
~~~

**Đây là ví dụ về cách biểu đạt câu CQL, không phải một API đảm bảo trả cờ CAS.** Khi method trả `void`, caller không nhận được thông tin điều kiện có được áp dụng hay không. Hơn nữa, kiểu trả `boolean` ở một phương thức modifying query **không mặc nhiên đồng nghĩa `[applied]`**; hợp đồng hỗ trợ phụ thuộc phiên bản Spring Data Cassandra.

Hãy kiểm tra cả **khả năng hỗ trợ annotation**, **cú pháp tham số**, **kiểu kết quả** và **hành vi thực thi** trên đúng phiên bản đang chạy. Nếu nghiệp vụ phải biết true/false của LWT, một **custom repository fragment/gateway dùng `CqlSession` và `wasApplied()`** là lựa chọn tường minh, dễ kiểm thử.

### 12.1. Có thể dùng @Version không?

Một số dòng Spring Data Cassandra hỗ trợ cơ chế optimistic locking cho entity được đánh dấu **`@Version`** theo quy tắc riêng của framework. Tuy nhiên:

- Phải đối chiếu **chính xác phiên bản Spring Data Cassandra** của ứng dụng.
- Phân biệt `@Version` được framework hiểu với một field tên `version` thông thường.
- Kiểm tra đường `save(...)`, trạng thái entity mới/cũ, giá trị khởi tạo version và ngoại lệ khi optimistic locking thất bại.
- Không trộn các đường ghi **bỏ qua cơ chế version** với đường ghi CAS và vẫn kỳ vọng version bảo vệ toàn bộ dữ liệu.
- Viết test tích hợp hai writer để chứng minh behavior thực tế; không chỉ dựa vào annotation xuất hiện trong mã.

Ví dụ gateway CQL của bài này **quản lý version thủ công** để người học nhìn rõ điều kiện `IF version = ?`. Trong ứng dụng thật, có thể chọn cơ chế `@Version` đã được framework hỗ trợ **hoặc** gateway riêng, nhưng phải quy định rõ một nguồn quản lý concurrency, tránh hai cơ chế tăng version không đồng bộ.

## 13. Regular consistency và serial consistency của LWT

LWT có chi phí khác write thông thường vì cần **đồng thuận Paxos**. Với Java driver 4.x, hai mức consistency có vai trò riêng:

| Loại | Ví dụ | Mục đích |
| --- | --- | --- |
| **Regular consistency** | `LOCAL_QUORUM`, `QUORUM` | Yêu cầu replica phản hồi ở pha đọc/ghi thông thường của statement |
| **Serial consistency** | `LOCAL_SERIAL`, `SERIAL` | Phạm vi đồng thuận đối với conditional operation |

Ví dụ:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

BoundStatement conditional = updateIfVersion
    .bind("PAID", expectedVersion + 1,
          commandId, now, orderId,
          expectedVersion, "CREATED")
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

ResultSet result = session.execute(conditional);
boolean applied = result.wasApplied();
~~~

Ví dụ này nằm trong ngữ cảnh có sẵn `updateIfVersion`, `session` và các giá trị bind tương ứng. **Không áp đặt `LOCAL_QUORUM + LOCAL_SERIAL` là cấu hình mặc định cho mọi cluster**: trong multi-DC, việc dùng `LOCAL_SERIAL` chỉ chọn phạm vi đồng thuận local theo quy tắc của hệ thống. Nếu nghiệp vụ cần ngữ nghĩa mạnh xuyên DC, phải thiết kế topology, CL, routing và failover cùng nhau.

**Quorum thường không thay thế CAS.** Dù một cặp mức đọc/ghi có quorum overlap, hai writer vẫn có thể cùng đọc state cũ và ghi không điều kiện. Điều kiện `IF` là nơi Cassandra kiểm tra cạnh tranh theo LWT, chứ không phải chỉ tăng số replica xác nhận của câu `UPDATE`.

### 13.1. LWT không phải transaction quan hệ toàn cục

LWT không tự cung cấp một giao dịch ACID đa bảng/đa partition với isolation theo kiểu RDBMS. Một `INSERT IF NOT EXISTS` trên bảng giữ chỗ username không tự làm việc tạo profile ở một partition khác trở thành nguyên tử.

Khi cần nhiều bảng, hãy dùng **workflow có idempotency và đối soát**, hoặc chọn một nguồn sự thật rồi xây projection cho các bảng truy vấn khác.

## 14. Xử lý xung đột: false không có nghĩa tự động retry

Giả sử hai worker cùng đọc `version = 7`:

~~~text
T0: Order có state=CREATED, version=7
T1: A chuẩn bị IF version=7 -> PAID, version=8
T2: B chuẩn bị IF version=7 -> CANCELLED, version=8
T3: A được [applied]=true
T4: B được [applied]=false
~~~

Khi B nhận false, có ít nhất hai chiến lược:

**Chiến lược 1 — Trả conflict:** B trả lỗi nghiệp vụ/HTTP 409 để client tải lại trạng thái mới và quyết định. Phù hợp nếu thao tác đòi xác nhận của người dùng.

**Chiến lược 2 — Đọc lại rồi đánh giá command:** B tải state/version mới, kiểm tra yêu cầu hủy đơn còn hợp lệ không. Nếu đơn đã `PAID` thì có thể phải **từ chối hủy**; nếu thay đổi trước đó không ảnh hưởng yêu cầu, B có thể tạo lệnh mới với expected version mới.

**Sai lầm cần tránh:**

~~~java
while (!gateway.payIfUnchanged(orderId, version, commandId, now)) {
    version++;  // Sai: tăng đoán mà không đọc/kiểm tra trạng thái thật.
}
~~~

Vòng lặp này vừa có thể chạy vô hạn, vừa phá ý nghĩa kiểm tra trạng thái. Retry không phải là “cố thắng cuộc đua bằng mọi giá”; nó phải tôn trọng bất biến nghiệp vụ và giới hạn tải.

## 15. Retry sau timeout cần idempotency, không chỉ CAS

Một timeout tạo tình huống khó:

~~~text
Client -> Cassandra: INSERT IF NOT EXISTS, order_id = X, command_id = C
Cassandra: có thể đã quyết định/applied mutation
Client: mất response hoặc hết thời gian chờ
Client retry cùng command C
Cassandra: trả [applied] = false vì hàng X đã có
~~~

`false` ở lần retry **không chứng minh request đầu thất bại**. Có thể chính command C đã tạo hàng, hoặc một writer khác đã tạo trước. Đó là lý do bảng minh họa có `last_command_id`.

### 15.1. Đối chiếu bằng command ID

Khi `INSERT IF NOT EXISTS` trả false:

1. Đọc lại hàng theo `order_id` bằng CL phù hợp.
2. So sánh `last_command_id` với `commandId` của request hiện tại.
3. Nếu trùng và payload không mâu thuẫn, có thể coi là **idempotent replay** theo contract.
4. Nếu khác, có thể trả **conflict**.
5. Nếu việc đọc lại thất bại hoặc vẫn không chắc chắn, không tuyên bố tạo thành công/ thất bại một cách tùy tiện.

**Đây là mô hình đơn giản hóa:** một cột `last_command_id` chỉ lưu **command cuối cùng**, nên nếu nhiều thao tác nối tiếp, nó không thay thế một **idempotency ledger** lưu kết quả của nhiều request. Với nghiệp vụ quan trọng, cần thiết kế bảng command/outcome theo ID ổn định và chính sách retention.

### 15.2. Khi timeout xảy ra ở UPDATE IF version

Giả sử lần đầu `IF version=7` đã thành công nhưng response mất. Retry nguyên lệnh với expected version 7 có thể trả false vì version đang là 8.

Không xem false là “command chưa thành công”; cần đối chiếu command ID hoặc nguồn dữ liệu bền vững khác. Một giải pháp dùng **version và command ID** để biết ai đã thay đổi state; với nhiều command liên tiếp, phải giữ lịch sử/cơ chế dedup tương ứng.

## 16. Sử dụng kết quả ở tầng service và HTTP API

Đừng trả thẳng boolean không rõ nghĩa từ mọi endpoint. Một service có thể định nghĩa:

~~~java
public enum CreateOrderOutcome {
    CREATED,
    ALREADY_EXISTS,
    REPLAYED
}

public enum TransitionOutcome {
    APPLIED,
    CONFLICT
}
~~~

Các enum chỉ biểu thị **kết quả nghiệp vụ đã có phản hồi hợp lệ**. Lỗi timeout/Unavailable phải đi qua cơ chế exception/trạng thái bất định riêng, không trả `CONFLICT` giả.

Một quy ước HTTP có thể là:

| Use case | CAS result | HTTP response gợi ý |
| --- | --- | --- |
| Tạo đơn bằng `IF NOT EXISTS` | true | `201 Created` |
| Tạo đơn cùng ID bởi request khác | false | `409 Conflict` |
| Retry tạo đơn, đối chiếu thấy cùng command | false nhưng đã xử lý trước | Trả kết quả idempotent theo contract |
| Update-only bằng `IF EXISTS` | true | `200 OK` hoặc `204 No Content` |
| Update-only khi hàng vắng mặt | false | `404 Not Found` |
| Chuyển trạng thái theo `IF state/version` | true | `200 OK` hoặc `204 No Content` |
| Chuyển trạng thái trên bản đã đổi | false | `409 Conflict` hoặc phản hồi yêu cầu tải lại |
| Xóa idempotent bằng `DELETE IF EXISTS` | false do vắng mặt | Có thể `204 No Content` theo thiết kế API |
| LWT timeout hoặc cluster không sẵn sàng | Không có cờ `[applied]` hợp lệ | Phản hồi lỗi kỹ thuật/trạng thái chưa rõ, không tạo 404/409 giả |

Đây là **quy ước ứng dụng**, không phải HTTP status do Cassandra tự sinh. Đừng lạm dụng HTTP 409 cho mọi lỗi database: lỗi topology, mapping, authentication và invalid query cần được chẩn đoán riêng.

## 17. LWT không tự xử lý denormalization và nhiều partition

Ứng dụng Cassandra thường ghi cùng một thực thể vào nhiều bảng theo truy vấn:

~~~text
orders_by_id
orders_by_customer_day
orders_by_state_day
~~~

Một `INSERT IF NOT EXISTS` trong `orders_by_id` chỉ bảo vệ điều kiện của **hàng/bảng mục tiêu**. Nó không làm cho ghi vào hai bảng khác nguyên tử với thao tác đầu.

~~~mermaid
flowchart TD
    A[CAS tạo orders_by_id] --> B{applied?}
    B -->|true| C[Ghi orders_by_customer_day]
    B -->|false| D[Conflict hoặc replay]
    C --> E{Ghi bảng phụ thành công?}
    E -->|Có| F[Hoàn thành quy trình]
    E -->|Không hoặc timeout| G[Retry/đối soát bảng phụ]
~~~

Nếu bước tạo hàng chính thành công nhưng bước cập nhật bảng phụ thất bại, cần một **handoff bền vững** hoặc workflow có thể tái chạy mà không phá dữ liệu.

Đừng hiểu **CQL BATCH** là cách biến mọi nhóm mutation khác partition thành transaction có isolation/serializability tùy ý như SQL quan hệ. Batch có các quy tắc atomicity và giới hạn riêng; conditional batch/LWT có thêm ràng buộc theo partition và phiên bản. Trước khi dùng, phải xác minh DDL, CQL được Cassandra chấp nhận và đặc tính hiệu năng.

Nếu nghiệp vụ cần kiểm soát phức tạp nhiều đối tượng, xem xét mô hình **event log + projection**, single-writer theo aggregate hoặc workflow/saga phù hợp, thay vì mở rộng một `IF EXISTS` thành lời hứa “toàn hệ thống đã đồng bộ”.

## 18. Hiệu năng: chi phí Paxos và cạnh tranh trên partition

LWT có lợi ích bảo vệ điều kiện nhưng cần nhiều pha giao tiếp replica hơn write thông thường. Vì vậy:

- Độ trễ tail latency của LWT có thể cao hơn ghi không điều kiện.
- Hot partition với nhiều writer CAS cùng lúc có thể tạo contention.
- Retry liên tục sau false/timeout có thể tăng tải, khiến cuộc tranh chấp khó giảm.
- LWT không thay thế **partition key hợp lý, hạn chế scan, projection hay paging**.
- Prepared statement có thể giảm chi phí chuẩn bị CQL, nhưng **không loại bỏ chi phí đồng thuận Paxos**.

| Nhu cầu | Lựa chọn ban đầu |
| --- | --- |
| Ghi mỗi sensor reading theo khóa duy nhất, chấp nhận overwrite theo chính sách | Ghi thông thường, không nhất thiết cần LWT |
| Chỉ tạo một reservation cho mỗi mã hàng | `IF NOT EXISTS` |
| Cập nhật entity chỉ khi đã có | `IF EXISTS` nếu thật sự cần biết tình trạng tồn tại |
| Chỉ cho phép state transition hợp lệ | `IF state = ?` hoặc `IF version = ?` |
| Cập nhật hai bảng khác partition như một workflow | CAS ở nguồn sự thật + retry/đối soát |
| Lưu mọi sự kiện lịch sử và replay | Event log/event sourcing được thiết kế riêng |

### 18.1. Các chỉ số nên đo

1. P50/P95/P99 latency của conditional write so với write thường.
2. Tỷ lệ `[applied] = false` theo từng loại lệnh, không trộn conflict nghiệp vụ với timeout.
3. LWT timeouts, unavailable và tần suất retry.
4. Số concurrent writers trên cùng partition, mức độ hot partition.
5. Số replica/cluster health, DC routing và lựa chọn serial/regular consistency.
6. Số bước workflow ghi bảng phụ còn chờ đối soát.
7. Kích thước partition, tombstone, TTL, compaction và read amplification.

Không khẳng định một cặp CL hoặc một câu conditional query “nhanh nhất” khi chưa đo trên workload và topology thật.

## 19. Những lỗi phổ biến khi dùng IF

| Cách làm sai | Hậu quả | Cách sửa |
| --- | --- | --- |
| `existsById` rồi `save` để tạo duy nhất | Race condition | `INSERT IF NOT EXISTS` trên khóa đúng |
| `UPDATE IF EXISTS` để chuyển state có điều kiện | Chỉ kiểm tra tồn tại, không bảo vệ transition | `IF state = ?` hoặc `IF version = ?` |
| Coi `[applied] = false` là lỗi Cassandra | Báo lỗi hạ tầng sai | Diễn giải theo loại điều kiện |
| Coi timeout là `false` | Có thể báo thất bại giả khi CAS đã áp dụng | Phân biệt unknown và điều kiện false |
| Coi method `void` từ `@Modifying` là applied=true | Bỏ sót conflict | Xác minh kết quả CAS tường minh |
| Coi field thường tên `version` tự bật optimistic locking | Lệnh ghi không điều kiện phá version guard | Dùng API `@Version` được hỗ trợ/kiểm thử hoặc CAS thủ công |
| Writer A dùng CAS, writer B vẫn `save` | Writer B ghi đè được dữ liệu được bảo vệ | Thống nhất mọi write path |
| Retry infinite loop khi version mismatch | Tải cao, có thể ghi sai business state | Đọc lại, kiểm tra lệnh, giới hạn retry |
| Dùng `USING TIMESTAMP` để thực thi check-then-act | Timestamp không kiểm tra trạng thái hiện tại | Dùng conditional write |
| `INSERT IF NOT EXISTS` được xem là unique toàn doanh nghiệp | Nó chỉ bảo vệ khóa mục tiêu | Thiết kế bảng reservation theo business key |
| LWT một bảng rồi tưởng bảng khác đã commit | Dữ liệu denormalized có thể lệch | Workflow/outbox/đối soát |
| Coi `LOCAL_SERIAL` là đồng thuận toàn bộ DC | Sai phạm vi điều kiện ở multi-DC | Thiết kế CL/topology phù hợp |

## 20. Kiểm thử tích hợp trên Cassandra thật

Một unit test với mock gateway có thể xác minh service phân biệt `true` và `false`. Nhưng **không thể chứng minh** điều kiện Paxos có ngăn được hai writer hoặc CQL của Cassandra có hợp lệ hay không. Cần test tích hợp.

### 20.1. Test IF NOT EXISTS hai lần

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

@Test
void insertIfNotExistsAppliesOnlyOnce() {
    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();
    UUID commandId = UUID.randomUUID();

    PreparedStatement insert = session.prepare(
        "INSERT INTO app_ks.orders_by_id " +
        "(order_id, customer_id, state, version, total_cents, " +
        " last_command_id) " +
        "VALUES (?, ?, 'CREATED', 1, ?, ?) IF NOT EXISTS"
    );

    boolean first = session.execute(
        insert.bind(orderId, customerId, 1000L, commandId)
    ).wasApplied();

    boolean second = session.execute(
        insert.bind(orderId, customerId, 9000L, UUID.randomUUID())
    ).wasApplied();

    assertTrue(first);
    assertFalse(second);

    PreparedStatement select = session.prepare(
        "SELECT total_cents FROM app_ks.orders_by_id " +
        "WHERE order_id = ?"
    );
    long stored = session.execute(select.bind(orderId))
        .one().getLong("total_cents");
    assertEquals(1000L, stored);
}
~~~

Ví dụ dùng JUnit 5, `CqlSession session` đã tạo trong test fixture và schema có sẵn. Không khởi tạo/đóng session mỗi lần gọi; sử dụng môi trường lab, tránh ghi fixture vào production. Định danh UUID ngẫu nhiên giảm va chạm giữa các test, nhưng test vẫn cần chính sách dọn dữ liệu.

### 20.2. Test optimistic locking với hai writer

Chuẩn bị một hàng `state=CREATED`, `version=7`. Hai task cùng gọi conditional update:

~~~text
Worker A: UPDATE ... SET state=PAID, version=8
          WHERE order_id=X IF version=7 AND state=CREATED
Worker B: UPDATE ... SET state=CANCELLED, version=8
          WHERE order_id=X IF version=7 AND state=CREATED

Kỳ vọng (không có writer khác phá guard):
  exactly one applied=true;
  exactly one applied=false;
  final version=8;
  final state khớp mutation được áp dụng.
~~~

Nên dùng barrier để hai task cùng bắt đầu sau khi đã chuẩn bị dữ liệu. Không assert **A luôn thắng**, vì lịch thực thi và coordinator không được quyết định bởi thứ tự đặt task trong test.

### 20.3. Ma trận tình huống bắt buộc

| Tình huống | Query | Kỳ vọng |
| --- | --- | --- |
| Tạo hàng chưa có | `INSERT IF NOT EXISTS` | `true` |
| Tạo lại cùng ID | `INSERT IF NOT EXISTS` | `false`, hàng cũ không bị ghi đè |
| Update-only khi hàng có sẵn | `UPDATE IF EXISTS` | `true` |
| Update-only khi chưa có hàng | `UPDATE IF EXISTS` | `false`, không upsert |
| Xóa hàng hiện hữu | `DELETE IF EXISTS` | `true` |
| Xóa lại | `DELETE IF EXISTS` | `false` |
| State vẫn `CREATED` | `IF state = 'CREATED'` | `true` |
| State đã `CANCELLED` | `IF state = 'CREATED'` | `false` |
| Version trùng | `IF version = 7` | `true`, version tăng |
| Version đã khác | `IF version = 7` | `false` |
| Hai writer cùng version | Hai conditional updates | Chỉ một áp dụng ở trạng thái được bảo vệ |
| Retry sau mất response | Gửi lại cùng command ID | Đối soát, không báo false thành thất bại chắc chắn |
| Driver timeout | Bất kỳ LWT nào | Ngoại lệ; không biến thành điều kiện false |
| Ghi không điều kiện ngoài luồng | `save(...)` hoặc CQL update thường | Test phát hiện đường ghi phá version guard |
| Row TTL đã hết | `INSERT IF NOT EXISTS` | Quan sát điều kiện theo trạng thái dữ liệu hiện thời |

### 20.4. Kiểm chứng schema, consistency và lỗi

Với một cluster lab, kiểm tra thêm:

- Query có ràng buộc **đúng primary key** và keyspace không.
- Đường `@Modifying` có thật sự cho phép lấy thông tin LWT không; không giả định từ method return type.
- `LOCAL_SERIAL` hay `SERIAL` có phạm vi phù hợp topology không.
- Đọc lại sau CAS có dùng CL phù hợp để diễn giải dữ liệu không.
- Timeout/Unavailable có được API phân loại đúng thay vì lẫn với conflict không.
- Không chạy fault injection trên cluster production.

## 21. Bài tập tổng hợp: API tạo, cập nhật và hủy đơn

**Bối cảnh:** xây API cho phép tạo đơn, cập nhật trạng thái và hủy đơn với nhiều instance Spring Boot cùng sử dụng Cassandra.

**Yêu cầu thực hiện:**

1. Tạo bảng `orders_by_id` theo phần 2, khởi tạo version và command ID.
2. Viết `createOrder(...)` dùng `INSERT IF NOT EXISTS`; phân biệt `CREATED` và `ALREADY_EXISTS`.
3. Thêm idempotency bằng `commandId`; gửi lại cùng request sau timeout giả lập và giải thích cách đối chiếu.
4. Viết `touchExistingOrder(...)` dùng `UPDATE IF EXISTS`; xác minh không tạo hàng mới.
5. Viết `payOrder(...)` dùng `IF version = ? AND state = 'CREATED'`; trả `APPLIED` hoặc `CONFLICT`.
6. Viết `cancelOrder(...)` với rule trạng thái tương ứng; không dùng write thường để né conflict.
7. Tạo hai writer cạnh tranh cùng expected version; xác minh chỉ một mutation có điều kiện thắng.
8. Dùng `ResultSet.wasApplied()`; không coi `void` repository method là bằng chứng applied=true.
9. Tạo endpoint HTTP cho từng hành động và quy định status 201, 204, 404, 409 cùng nhóm lỗi hạ tầng.
10. Thêm một bảng `orders_by_customer_day` để hiển thị danh sách; xác định workflow khi CAS hàng chính thành công nhưng ghi bảng phụ thất bại.
11. Đo latency và tỷ lệ conflict khi tăng số concurrent writers; thiết kế giới hạn retry/backoff.
12. Viết giải thích ngắn: **khi nào chỉ dùng IF EXISTS, khi nào phải dùng IF state/version, và vì sao timeout khác false**.

**Tiêu chí đạt:** mọi đường tạo/cập nhật quan trọng thể hiện **điều kiện tại Cassandra**, service đọc đúng cờ `[applied]`, conflict không bị biến thành lỗi kết nối, timeout không bị biến thành `false`, và workflow đa bảng có chiến lược phục hồi rõ ràng.

## 22. Câu hỏi tự kiểm tra

1. Vì sao `existsById(id)` rồi `save(entity)` không an toàn khi hai request cùng tạo một ID?
2. `INSERT` Cassandra thông thường khác `INSERT IF NOT EXISTS` như thế nào?
3. `IF NOT EXISTS` bảo vệ duy nhất theo **khóa nào**? Nó có bảo vệ email ở một bảng khác không?
4. `UPDATE IF EXISTS` giải quyết điều gì mà `UPDATE` không điều kiện không giải quyết?
5. Vì sao `UPDATE IF EXISTS` vẫn có thể làm sai state machine?
6. Khi nào `DELETE IF EXISTS` đáng dùng, và khi nào xóa idempotent bình thường đã đủ?
7. `IF state = 'CREATED'` khác `IF version = 7` ở phạm vi xung đột phát hiện được thế nào?
8. Vì sao cần tăng version trong cùng mutation đã được bảo vệ bởi `IF version`?
9. Nếu hàng chưa có version hoặc vừa được xóa rồi tạo lại, cần xem xét những tình huống nào?
10. Khi cờ `[applied]` là false, tại sao không nên mặc định trả HTTP 404?
11. Một `WriteTimeout` ở LWT có thể chứng minh mutation chưa diễn ra không?
12. `ResultSet.wasApplied()` khác việc đọc một entity từ `SELECT` ra sao?
13. Tại sao method `@Modifying void` không đủ cho API cần biết optimistic conflict?
14. Field Java tên `version` có tự đảm bảo mọi repository save đều dùng CAS không?
15. Regular consistency khác serial consistency của LWT ở đâu?
16. Vì sao `LOCAL_SERIAL` cần đánh giá kỹ trong hệ multi-datacenter?
17. Nếu client retry cùng command sau timeout nhưng CAS trả false, làm sao phân biệt replay với command khác?
18. Vì sao một cột `last_command_id` có thể không đủ để deduplicate mọi request trong lịch sử?
19. LWT một bảng có đảm bảo cập nhật nguyên tử bảng khác partition không?
20. Những test nào cần chạy với Cassandra thật thay vì chỉ dùng mock repository?
21. Khi nào chi phí Paxos lớn hơn giá trị mà điều kiện mang lại?
22. Vì sao prepared statement và `QUORUM` không tự sửa được race condition check-then-act?

**Ghi nhớ:** `IF NOT EXISTS` kiểm tra **hàng chưa tồn tại**, `IF EXISTS` kiểm tra **hàng đang tồn tại**, còn `IF state/version = ?` kiểm tra **giá trị hiện tại** để bảo vệ chuyển trạng thái và khóa lạc quan. **`[applied] = true` là mutation được áp dụng; `false` là điều kiện không thỏa; timeout/exception không đồng nghĩa `false`**. Trong Spring Data Cassandra, phải kiểm chứng kiểu kết quả của `@Query`/`@Modifying` hoặc dùng `CqlSession` và `ResultSet.wasApplied()` để lấy cờ rõ ràng. LWT giải quyết các bất biến cần đồng thuận trên khóa phù hợp, nhưng không thay thế thiết kế partition, consistency, paging, idempotency, phục hồi đa bảng và kiểm soát hiệu năng của hệ phân tán.
