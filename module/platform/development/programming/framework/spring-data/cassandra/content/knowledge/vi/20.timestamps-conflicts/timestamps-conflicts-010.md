# Khi nào cần LWT hoặc mô hình sự kiện thay vì dựa vào timestamp trong Spring Data Cassandra

## 1. Bài toán: hai thao tác ghi đều thành công, trạng thái cuối vẫn sai

Giả sử ứng dụng Spring Boot dùng **Spring Data Cassandra** lưu đơn hàng. Hai dịch vụ cùng đọc thấy đơn hàng có trạng thái `CREATED`:

- Dịch vụ thanh toán muốn đổi sang `PAID`.
- Dịch vụ hủy đơn muốn đổi sang `CANCELLED`.

Cả hai lần ghi có thể được Cassandra xác nhận thành công. Nhưng ở trạng thái cuối, hệ thống chỉ giữ một giá trị `state` do cơ chế hòa giải xung đột. Nếu chỉ dựa vào timestamp, một thao tác có thể **ghi đè quyết định nghiệp vụ hợp lệ** của thao tác còn lại.

Ba câu hỏi cần được tách biệt:

1. **Khi có nhiều phiên bản của một cột, replica nào thắng?** Cassandra sử dụng timestamp và các quy tắc hòa giải giá trị.
2. **Làm sao từ chối cập nhật khi trạng thái đã thay đổi?** Cần cơ chế kiểm tra điều kiện nguyên tử phù hợp, thường là **lightweight transaction (LWT)** với `IF`.
3. **Làm sao biết mọi sự kiện đã từng xảy ra, kể cả khi trạng thái hiện tại bị thay thế?** Cần **mô hình sự kiện** hoặc nhật ký thay đổi có thiết kế lưu trữ độc lập.

Bài này thuộc chương **Timestamp và xung đột** của module `SPRING_DATA_CASSANDRA`. Nội dung liên kết với entity mapping, repository, `CassandraTemplate`, truy vấn CQL, thiết kế bảng theo truy vấn, partition key, consistency, paging và hiệu năng của một hệ dữ liệu phân tán.

Sau bài học, bạn có thể:

1. Giải thích **last-write-wins (LWW)** của Cassandra là **theo timestamp của mutation/cell**, không đơn giản là request nào đến sau.
2. Nhận ra các tình huống mà **`QUORUM` hoặc `LOCAL_QUORUM` không giải quyết lost update**.
3. Viết và đọc kết quả `INSERT ... IF NOT EXISTS`, `UPDATE ... IF version = ?`, `IF state = ?`.
4. Phân biệt **state hiện tại**, **event log**, **projection**, **idempotency** và **sequence**.
5. Lựa chọn giữa ghi không điều kiện, LWT, event log hoặc kết hợp cả hai theo bất biến nghiệp vụ.
6. Kiểm thử tranh chấp, timeout, retry và lệch đồng hồ mà không đưa ra lời bảo đảm quá mức.

## 2. Timestamp trong Cassandra là gì?

### 2.1. Timestamp của mutation không phải cột timestamp nghiệp vụ

Cassandra quản lý **write timestamp** để hòa giải các phiên bản dữ liệu. Với các cột thông thường, timestamp này gắn với **cell/mutation**, thường tính bằng **microsecond từ Unix epoch**.

Phân biệt ba khái niệm:

| Giá trị | Ví dụ | Mục đích |
| --- | --- | --- |
| **Write timestamp nội bộ** | Một số microsecond dùng để hòa giải mutation | Xác định phiên bản nào thắng khi xung đột |
| **Cột CQL `timestamp`** | `occurred_at timestamp` hoặc `updated_at timestamp` | Lưu thời điểm có ý nghĩa nghiệp vụ, độ chính xác mili giây |
| **Thời điểm client nhận HTTP response** | Thời gian gateway trả 200 | Đo latency và thứ tự quan sát ở application, không tự quyết định LWW |

Ví dụ:

~~~sql
CREATE TABLE app_ks.orders_by_id (
    order_id uuid PRIMARY KEY,
    state text,
    version bigint,
    updated_at timestamp
);
~~~

`updated_at` là **một cột dữ liệu do ứng dụng quản lý**. Nếu ứng dụng ghi `updated_at = '2026-11-25T09:00:00Z'` thì giá trị đó **không tự trở thành write timestamp nội bộ** được dùng để hòa giải `state`. Hai khái niệm chỉ có liên hệ nếu ứng dụng chủ động cấu hình/gắn write timestamp theo chính sách cụ thể.

### 2.2. Cassandra hòa giải theo timestamp, không theo thứ tự arrival

Giả sử cùng một hàng/cột `state` nhận hai mutation:

~~~text
Mutation A: state = PAID,       write timestamp = 1_800_000_000_000_100
Mutation B: state = CANCELLED,  write timestamp = 1_800_000_000_000_050

Request B có thể tới coordinator sau A,
nhưng A vẫn có timestamp lớn hơn và được ưu tiên khi hòa giải.
~~~

Do đó, cụm “last-write-wins” dễ gây hiểu lầm. Trong Cassandra, cách hiểu hữu ích hơn là **“phiên bản có timestamp phù hợp với quy tắc hòa giải thắng”**, không phải **“request Java cuối cùng theo wall clock thắng”**.

Khi timestamp của các phiên bản bằng nhau, Cassandra có **quy tắc phân giải xung đột xác định** cho dữ liệu/tombstone, phụ thuộc loại giá trị và phiên bản. Không nên dựa vào tie-break đó để thực thi ưu tiên nghiệp vụ kiểu “thanh toán quan trọng hơn hủy đơn”.

### 2.3. Timestamp có thể đến từ đâu?

Tùy cấu hình và phiên bản Cassandra/Java driver, write timestamp có thể do **client-side timestamp generator** cung cấp hoặc do Cassandra quyết định khi client không gửi timestamp tường minh. CQL cũng có cú pháp `USING TIMESTAMP` cho một số thao tác ghi thông thường.

~~~sql
-- Minh họa kiểm soát timestamp một mutation thường.
-- Đơn vị của USING TIMESTAMP là microsecond.
UPDATE app_ks.orders_by_id
USING TIMESTAMP 1800000000000100
SET state = 'PAID'
WHERE order_id = 11111111-1111-4111-8111-111111111111;

-- Dù thực thi sau, timestamp thấp hơn có thể không thắng.
UPDATE app_ks.orders_by_id
USING TIMESTAMP 1800000000000050
SET state = 'CANCELLED'
WHERE order_id = 11111111-1111-4111-8111-111111111111;
~~~

Đây là **bài minh họa trong môi trường thử nghiệm**, không phải mẫu nên dùng cho API production. Một write timestamp quá xa trong tương lai có thể làm nhiều lần ghi thông thường về sau **khó thay thế được giá trị cũ** cho đến khi timestamp mới vượt qua nó.

**Không sử dụng `USING TIMESTAMP` làm cách thay thế cho LWT.** Các tổ hợp với câu lệnh có điều kiện còn có giới hạn cú pháp/phiên bản riêng; ngay cả với ghi không điều kiện, tự gắn timestamp vẫn không kiểm tra được bất biến nghiệp vụ.

## 3. Chẩn đoán timestamp bằng WRITETIME nhưng không nhầm với lịch sử

Trong `cqlsh`, có thể kiểm tra write timestamp của một cột thông thường bằng `WRITETIME`:

~~~sql
SELECT order_id, state, WRITETIME(state), updated_at
FROM app_ks.orders_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
~~~

Lệnh này giúp điều tra giá trị timestamp lưu cùng `state`. Nó **không tạo một lịch sử các phiên bản cũ**; sau khi giá trị bị thay thế, Cassandra không tự cung cấp cho ứng dụng một danh sách “state trước đó” thông qua `WRITETIME`.

Những điều phải nhớ:

- `WRITETIME(state)` áp dụng cho những kiểu cột/điều kiện được Cassandra hỗ trợ; không suy rộng cho mọi cấu trúc và primary key.
- Giá trị thường là timestamp của **cell đang quan sát**, không phải ID request hay version nghiệp vụ.
- Với cột không có giá trị, kết quả có thể null; với TTL/xóa có thể xuất hiện tombstone và hành vi đọc khác.
- Timestamp không cho biết chắc **ai đã ghi**, **vì sao ghi** hoặc **liệu request client đã nhận thành công hay chưa**.

Muốn audit những thay đổi có ý nghĩa, phải **thiết kế audit/event log** riêng, không kỳ vọng metadata timestamp của Cassandra tự làm việc đó.

## 4. Mất cập nhật (lost update) khi hai writer cùng sửa một hàng

Xem hai thao tác đọc–sửa–ghi:

~~~mermaid
sequenceDiagram
    participant A as Thanh toán
    participant DB as Cassandra
    participant B as Hủy đơn
    A->>DB: SELECT state theo order_id
    DB-->>A: CREATED
    B->>DB: SELECT state theo order_id
    DB-->>B: CREATED
    A->>DB: UPDATE state=PAID (không điều kiện)
    DB-->>A: Write success
    B->>DB: UPDATE state=CANCELLED (không điều kiện)
    DB-->>B: Write success
    Note over DB: Giá trị cuối được hòa giải theo write timestamp
~~~

Nếu nghiệp vụ quy định đơn đã thanh toán **không thể bị hủy bằng yêu cầu bình thường**, trạng thái cuối `CANCELLED` là sai dù cả hai request CQL hợp lệ. Một sai lầm thường gặp là sửa bằng cách nâng cả đọc và ghi lên `LOCAL_QUORUM`.

Quorum giúp kiểm soát **bao nhiêu replica xác nhận và phản hồi**, nhưng **không biến hai lượt SELECT + UPDATE không điều kiện thành một compare-and-set**. Hai writer vẫn có thể đọc cùng trạng thái cũ, rồi cả hai ghi thành công.

### 4.1. Vì sao sửa bằng timestamp không đáng tin cậy?

Một người có thể đề nghị: “Ghi có thời điểm sau sẽ thắng; hãy lấy timestamp mới hơn.” Giải pháp này không giải quyết đúng bất biến:

1. Timestamp không chứng minh trạng thái cũ vẫn là `CREATED`.
2. Nhiều client có thể có **clock skew**; timestamp lớn hơn không tương đương quyết định hợp lệ hơn.
3. Retry sau timeout có thể tạo timestamp mới và ghi đè một mutation đã thành công của writer khác.
4. Ở mức cell, các field của cùng hàng có thể được viết bằng **những timestamp khác nhau**, dẫn tới tổ hợp trạng thái không từng tồn tại như một bản cập nhật nghiệp vụ đơn nhất.
5. Một future timestamp hoặc tombstone có thể ảnh hưởng nhiều lần ghi đến sau.

**Lời giải cần một điều kiện có thể kiểm tra tại thời điểm commit**, không chỉ một con số thời gian.

## 5. Phân biệt consistency, LWT và event log

| Cơ chế | Câu hỏi nó trả lời | Nó **không** tự bảo đảm |
| --- | --- | --- |
| **Regular consistency** như `ONE`, `LOCAL_QUORUM` | Bao nhiêu replica phải phản hồi trước khi request hoàn tất? | Không chặn lost update do hai writer cùng đọc–ghi |
| **Timestamp/LWW** | Phiên bản cell nào được ưu tiên khi có mutation xung đột? | Không hiểu quy tắc chuyển trạng thái và không giữ lịch sử |
| **LWT/CAS** qua `IF` | Có áp dụng mutation nếu điều kiện trên dữ liệu vẫn đúng không? | Không tự cung cấp audit trail hay giao dịch ACID tùy ý trên nhiều partition |
| **Event log/event sourcing** | Những sự kiện nghiệp vụ nào đã được ghi nhận? | Không tự đảm bảo thứ tự nhân quả, unique request hoặc không tranh chấp |
| **Projection/read model** | Mô hình đọc nào có thể phục vụ truy vấn hiệu quả? | Không tự đồng bộ nguyên tử với event log |

Một hệ thống có thể cần **nhiều cơ chế đồng thời**. Ví dụ:

- Dùng **LWT** để từ chối việc chuyển `PAID → CANCELLED` không hợp lệ.
- Dùng **event log** để ghi nhận những sự kiện `OrderPaid`, `CancellationRejected` và phục vụ audit.
- Dùng **bảng truy vấn riêng** để hiển thị timeline theo `order_id`.
- Dùng **consistency level** phù hợp khi đọc/ghi từng bảng.

Mấu chốt là xác định **bất biến** và **nguồn sự thật** trước khi chọn công nghệ.

## 6. Khi nào chỉ dùng ghi không điều kiện và timestamp là đủ?

Không phải mọi write đều cần LWT. Ghi thông thường thường hợp lý khi:

- Dữ liệu là **telemetry** hoặc số đo mới nhất, có thể chấp nhận quy tắc thay thế theo timestamp.
- Mỗi khóa được quản lý bởi **một writer logic** và ứng dụng đã kiểm soát việc phát sinh nhiều phiên bản cạnh tranh.
- Việc ghi lại cùng một giá trị là có thể chấp nhận, và không có **state transition** cần xác minh.
- Không cần khôi phục mọi phiên bản cũ để audit.
- Tập dữ liệu đáp ứng yêu cầu stale read, retry/idempotency và consistency đã thiết kế.

Ví dụ bảng trạng thái cảm biến mới nhất:

~~~sql
CREATE TABLE app_ks.sensor_latest_by_id (
    sensor_id uuid PRIMARY KEY,
    measured_at timestamp,
    temperature_c decimal
);
~~~

Lệnh ghi:

~~~sql
UPDATE app_ks.sensor_latest_by_id
SET measured_at = ?, temperature_c = ?
WHERE sensor_id = ?;
~~~

Nếu nhiều thiết bị/worker có thể gửi mẫu đến **không theo thứ tự**, không nên mặc nhiên xem LWW là “mẫu có `measured_at` lớn nhất”. Timestamp của mutation và cột `measured_at` là **hai giá trị khác nhau**. Khi thật sự cần chọn mẫu có thời điểm đo lớn nhất, hãy thiết kế truy vấn theo thời gian, logic so sánh hoặc mô hình sự kiện/mẫu đo phù hợp.

Đối với telemetry, nhiều hệ thống lưu **mẫu đo append-only theo thời gian** và xây một bảng latest riêng. Cách này linh hoạt hơn nếu cần truy vấn lại lịch sử.

## 7. LWT là gì và giải quyết xung đột nào?

**Lightweight transaction (LWT)** trong Cassandra thực thi **ghi có điều kiện** bằng cơ chế đồng thuận Paxos trong phạm vi dữ liệu/partition thích hợp. Điều kiện được kiểm tra ở server khi thực hiện thao tác, thay vì ứng dụng tự thực hiện SELECT rồi UPDATE tách rời.

Các mẫu thường gặp:

~~~sql
-- Tạo hàng chỉ khi khóa chưa tồn tại.
INSERT INTO app_ks.orders_by_id (order_id, state, version)
VALUES (?, 'CREATED', 1)
IF NOT EXISTS;

-- Chỉ cập nhật khi hàng có sẵn.
UPDATE app_ks.orders_by_id
SET state = 'PAID'
WHERE order_id = ?
IF EXISTS;

-- Chỉ chuyển trạng thái khi trạng thái cũ còn phù hợp.
UPDATE app_ks.orders_by_id
SET state = 'PAID'
WHERE order_id = ?
IF state = 'CREATED';

-- Optimistic concurrency: chỉ cập nhật khi version chưa đổi.
UPDATE app_ks.orders_by_id
SET state = ?, version = ?, updated_at = ?
WHERE order_id = ?
IF version = ?;
~~~

**`IF EXISTS` không đủ để bảo vệ state machine:** nó chỉ xác nhận hàng tồn tại, không xác nhận state hiện tại hợp lệ cho thao tác. Khi business cần kiểm tra trước trạng thái, dùng điều kiện `IF state = ?`, `IF version = ?` hoặc kết hợp các điều kiện được phiên bản Cassandra hỗ trợ.

### 7.1. Kết quả [applied] không phải mã lỗi

Một conditional write trả kết quả có cờ `[applied]`:

~~~text
 [applied]
-----------
 True
~~~

Nếu điều kiện không thỏa:

~~~text
 [applied] | ... dữ liệu hiện tại nếu Cassandra trả về ...
-----------+--------------------------------------------
 False     | ...
~~~

**Phân biệt ba trạng thái:**

| Kết quả | Cách hiểu |
| --- | --- |
| `[applied] = true` | Điều kiện được thỏa và mutation có điều kiện được chấp nhận |
| `[applied] = false` | Điều kiện **không thỏa**; mutation không được áp dụng |
| Timeout, unavailable, lỗi driver/schema | Không có kết quả điều kiện hợp lệ; trạng thái request có thể **chưa rõ** |

Đừng bắt exception rồi trả `false`. `false` là **một kết quả nghiệp vụ có ý nghĩa**, khác với lỗi hạ tầng hoặc mất phản hồi sau khi mutation có thể đã diễn ra.

## 8. LWT với version: lựa chọn phù hợp để chặn lost update

Giả sử `orders_by_id` lưu:

~~~text
order_id = ...
state = CREATED
version = 7
~~~

Hai worker cùng đọc `version = 7`:

~~~mermaid
sequenceDiagram
    participant A as Writer A
    participant DB as Cassandra
    participant B as Writer B
    A->>DB: Đọc version=7
    B->>DB: Đọc version=7
    DB-->>A: CREATED, 7
    DB-->>B: CREATED, 7
    A->>DB: SET state=PAID, version=8 IF version=7
    DB-->>A: [applied] = true
    B->>DB: SET state=CANCELLED, version=8 IF version=7
    DB-->>B: [applied] = false
~~~

Đây là kết quả minh họa khi A thắng cuộc đua. Nếu B thắng trước, vai trò hai kết quả có thể đảo ngược. Điều quan trọng là **không phải cả hai đều được áp dụng** với cùng expected version của một trạng thái đã được bảo vệ đúng cách.

### 8.1. Cách dùng version đúng

1. Khi tạo hàng, **khởi tạo `version` một cách tường minh**, ví dụ 1.
2. Khi đọc, lưu lại `expectedVersion` trong request/command.
3. Khi ghi, cập nhật các field liên quan và tăng version trong **cùng conditional mutation**.
4. Nếu `[applied] = false`, không tự động ghi không điều kiện; đọc lại, đánh giá lệnh nghiệp vụ còn hợp lệ hay trả conflict.
5. Bảo đảm **mọi code path sửa các field được bảo vệ** tuân theo version guard. Một repository `save(entity)` không điều kiện có thể phá hợp đồng của LWT.
6. Với dữ liệu cũ thiếu version, cần migration/chiến lược tương thích; không mặc định null là 0 ở mọi phiên bản ứng dụng.

**Version là số thứ tự logic do ứng dụng quản lý**, không phải write timestamp. Lựa chọn version giúp diễn đạt “trạng thái vẫn là bản tôi đã đọc” thay vì “client này có đồng hồ lớn hơn”.

## 9. Java driver 4.x: lấy chính xác kết quả CAS

Khi cần đọc `[applied]` và cấu hình statement, dùng `CqlSession` của Java driver là cách rõ ràng:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.time.Instant;
import java.util.UUID;

public final class OrderTransitionGateway {
    private final CqlSession session;
    private final PreparedStatement changeState;

    public OrderTransitionGateway(CqlSession session) {
        this.session = session;
        this.changeState = session.prepare(
            "UPDATE app_ks.orders_by_id " +
            "SET state = ?, version = ?, updated_at = ? " +
            "WHERE order_id = ? " +
            "IF version = ? AND state = ?"
        );
    }

    public boolean payIfUnchanged(
            UUID orderId, long expectedVersion, Instant updatedAt) {
        BoundStatement statement = changeState.bind(
                "PAID", expectedVersion + 1, updatedAt,
                orderId, expectedVersion, "CREATED")
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

        ResultSet result = session.execute(statement);
        return result.wasApplied();
    }
}
~~~

Với một `CqlSession` đã được Spring cấu hình, class chuẩn bị mẫu CQL **một lần** và tạo `BoundStatement` mới cho mỗi lần ghi. `wasApplied()` trả boolean về điều kiện, **không tự diễn giải lý do thất bại**. Trường hợp false có thể do version khác, state khác hoặc hàng không tồn tại; nếu cần thông báo chính xác, service phải đối chiếu dữ liệu hiện tại theo chính sách nhất quán.

Những điểm cần xác minh trước khi đưa vào production:

- Ví dụ dùng **Java driver 4.x** và câu CQL `IF version = ? AND state = ?`; xác minh với **phiên bản Cassandra đang chạy**.
- `LOCAL_QUORUM` là **regular consistency**, còn `LOCAL_SERIAL` là **serial consistency** dùng cho LWT; lựa chọn thực tế phụ thuộc topology, đặc biệt multi-datacenter.
- `expectedVersion + 1` phải kiểm tra tràn số nếu hệ thống có vòng đời/version đặc biệt dài; số phiên bản không được giảm hoặc tái dùng tùy tiện.
- `Instant` là timestamp nghiệp vụ; không được lấy nó thay `version` để ra quyết định CAS.
- Không đóng `CqlSession` sau mỗi request, không tự tạo session mới cho mỗi lần gọi.
- Nếu `session.execute(...)` ném exception, **không coi kết quả là false**; phải xử lý trạng thái chưa chắc chắn.

### 9.1. Không hiểu nhầm @Query / @Modifying của repository

Spring Data Cassandra hỗ trợ repository và khai báo CQL bằng `@Query`. Có thể thấy dạng:

~~~java
@Modifying
@Query("UPDATE app_ks.orders_by_id " +
       "SET state = ?0 WHERE order_id = ?1 IF EXISTS")
void updateIfPresent(String state, UUID orderId);
~~~

Đây chỉ là **minh họa declaration**, cần đặt trong repository và import annotations phù hợp phiên bản. `void` **không cho biết `[applied]` là true hay false**. Nếu code cần phát hiện tranh chấp, không được suy từ “method không ném lỗi” rằng điều kiện đã được áp dụng.

Khả năng hỗ trợ `@Modifying`, kiểu return và cách ánh xạ kết quả conditional query có thể khác theo dòng Spring Data Cassandra. Khi cần kiểm soát kết quả CAS tường minh, dùng gateway dựa trên `ResultSet.wasApplied()` và test tích hợp. `CassandraRepository.save(...)` thông thường **không tự sinh CAS chỉ vì entity có field `version`**.

## 10. Khi nào LWT không đủ hoặc không nên dùng?

LWT có thể bảo vệ **bất biến cục bộ trên dữ liệu được điều kiện kiểm tra**, nhưng không tự giải quyết mọi vấn đề:

| Nhu cầu | LWT có đủ không? | Giải thích |
| --- | --- | --- |
| Không cho hai writer tạo cùng `order_id` | **Thường có**, với `INSERT ... IF NOT EXISTS` | Khóa mục tiêu là nơi kiểm tra tính duy nhất |
| Chỉ đổi `CREATED → PAID` khi state còn đúng | **Thường có**, với `IF state = ?` | CAS trên hàng được định vị |
| Không ghi đè snapshot đã có version mới hơn | **Có thể**, với `IF version = ?` | Tất cả writer phải tuân thủ guard |
| Biết mọi lần trạng thái từng thay đổi | **Không** | Snapshot bị thay thế không còn lịch sử |
| Audit lệnh bị từ chối, ai yêu cầu, lý do | **Không tự có** | Cần event/audit riêng |
| Ghi nguyên tử trạng thái và một bảng timeline ở partition khác | **Không tự có** | Phải thiết kế workflow/outbox/đối soát |
| Ghi hàng triệu điểm đo độc lập với throughput tối đa | **Thường không cần** | Paxos tạo chi phí không tương xứng |
| Bảo đảm mọi replica/đọc ở mọi DC lập tức thấy thay đổi | **Không tự có** | Còn phụ thuộc CL, replica, topology và read path |

LWT có **nhiều pha phối hợp giữa replica** hơn write thường, tốn thêm round-trip và có thể chịu contention khi nhiều writer cạnh tranh cùng partition. Nên đo P95/P99 latency, tỷ lệ `[applied] = false`, timeout và sức chịu tải trước khi dùng LWT trên đường ghi có lưu lượng cao.

### 10.1. SERIAL và LOCAL_SERIAL không phải chỉ là lựa chọn tốc độ

LWT dùng **serial consistency** để chỉ định phạm vi đồng thuận theo topology. Với hệ thống multi-DC, `LOCAL_SERIAL` và `SERIAL` có phạm vi khác nhau; không nên tùy tiện dùng một cơ chế đồng thuận local rồi giả định tất cả vùng địa lý đồng thuận tức thì.

Đồng thời **regular consistency** của câu ghi và đọc tiếp theo cũng cần được chọn theo yêu cầu quan sát. Không có một tổ hợp CL nào thay cho việc thiết kế đúng state machine và xử lý concurrent writers.

## 11. Khi nào nên lưu sự kiện thay vì chỉ cập nhật trạng thái?

**Mô hình sự kiện** trở nên quan trọng khi nghiệp vụ không chỉ hỏi:

> “Trạng thái hiện tại là gì?”

mà còn hỏi:

> “Điều gì đã xảy ra, theo thứ tự nào, do ai yêu cầu, và vì sao trạng thái hiện tại như vậy?”

Ví dụ với đơn hàng:

~~~text
OrderCreated       (orderId, customerId, occurredAt)
PaymentAuthorized  (orderId, paymentId, occurredAt)
OrderPaid          (orderId, paymentId, occurredAt)
CancellationRequested (orderId, requestId, occurredAt)
CancellationRejected  (orderId, reason, occurredAt)
~~~

Nếu chỉ giữ cột `state = PAID`, ứng dụng không thể khôi phục những sự kiện trung gian chỉ bằng `WRITETIME(state)`. Một **event log** có chủ đích có thể giúp:

- **Audit** và điều tra nguyên nhân.
- **Replay** để tái tạo projection khi logic đọc đổi.
- **Tích hợp** với hệ thống khác mà không cần poll liên tục một cột snapshot.
- Phân biệt **lệnh được yêu cầu** (`CancellationRequested`) với **kết quả đã được chấp nhận** (`CancellationRejected` hoặc `OrderCancelled`).
- Phục vụ phân tích lịch sử, kiểm toán và phát hiện hành vi bất thường.

**Event sourcing** là một dạng mạnh hơn: **event stream là nguồn sự thật**, còn các bảng trạng thái hiện tại là projection được xây dựng từ stream. Không phải cứ có thêm bảng `audit_log` là hệ thống đã thực hiện event sourcing đúng nghĩa.

## 12. Thiết kế bảng sự kiện theo truy vấn

Một access pattern phổ biến là **đọc lịch sử sự kiện của một đơn hàng theo thứ tự sequence**. Có thể thiết kế:

~~~sql
CREATE TABLE app_ks.order_events_by_order (
    order_id uuid,
    sequence_no bigint,
    event_id uuid,
    event_type text,
    occurred_at timestamp,
    payload text,
    PRIMARY KEY ((order_id), sequence_no)
) WITH CLUSTERING ORDER BY (sequence_no ASC);
~~~

| Cột | Vai trò | Lưu ý |
| --- | --- | --- |
| `order_id` | Partition key | Tất cả event của một đơn hàng nằm cùng partition |
| `sequence_no` | Clustering key | Cho phép đọc theo thứ tự logic do ứng dụng cấp phát |
| `event_id` | Định danh sự kiện | Hỗ trợ correlation/idempotency, **chưa được dùng làm unique key toàn cục trong bảng này** |
| `event_type` | Loại sự kiện | Tên có schema và versioning rõ ràng |
| `occurred_at` | Thời điểm nghiệp vụ | Không tự bảo đảm thứ tự commit |
| `payload` | Nội dung sự kiện | Cân nhắc kích thước, version và dữ liệu nhạy cảm |

CQL đọc timeline:

~~~sql
SELECT sequence_no, event_id, event_type, occurred_at, payload
FROM app_ks.order_events_by_order
WHERE order_id = ?
  AND sequence_no >= ?
LIMIT 100;
~~~

Với full partition key và clustering range hợp lệ, query này phù hợp cách Cassandra tổ chức hàng. Nhưng phải quyết định **sequence_no được cấp phát và bảo vệ thế nào**; chỉ ghi `sequence_no = MAX(sequence_no) + 1` sau một SELECT thông thường **có race condition**.

### 12.1. Không được dùng write timestamp như sequence_no

Write timestamp có thể trùng, lệch do client clock, hoặc phản ánh thời điểm phát lệnh khác với thời điểm nghiệp vụ hoàn tất. Cột `occurred_at` có thể hữu ích để hiển thị, nhưng **không thay thế sequence được quản lý rõ** nếu cần thứ tự quyết định trạng thái.

Nếu dùng `timeuuid` hoặc timestamp làm clustering key để đọc timeline **theo thời gian**, phải hiểu rằng **thứ tự thời gian không đồng nghĩa thứ tự nhân quả/toàn hệ thống**. Nhiều producer có clock skew và retry, nên event có thể xuất hiện “muộn” so với logic đã áp dụng.

### 12.2. Partition có thể phát triển vô hạn

Bảng `order_events_by_order` đặt tất cả event của một đơn hàng trong một partition. Nó hợp lý nếu mỗi đơn có **số lượng sự kiện được giới hạn**. Với aggregate có thể phát sinh hàng triệu event, cần:

- Thiết kế **bucket** hoặc chiến lược lưu trữ/archive theo quy mô.
- Quản lý sequence xuyên bucket một cách rõ ràng.
- Dùng paging state và giới hạn số hàng xử lý mỗi lần.
- Không đọc toàn bộ partition thành `List` trong mỗi request.

Đổi partition key để tối ưu kích thước cần được xem xét cùng **khả năng replay đầy đủ event stream**.

## 13. Append-only cần ID ổn định, không chỉ INSERT thường

CQL `INSERT` của Cassandra có **ngữ nghĩa upsert**. Nếu ghi lại cùng primary key `(order_id, sequence_no)`, giá trị event cũ có thể bị thay bằng mutation mới theo timestamp; bảng có tên “event log” **không tự trở thành append-only bất biến**.

Để bảo vệ vị trí sự kiện:

~~~sql
INSERT INTO app_ks.order_events_by_order
    (order_id, sequence_no, event_id, event_type, occurred_at, payload)
VALUES (?, ?, ?, ?, ?, ?)
IF NOT EXISTS;
~~~

`IF NOT EXISTS` giúp từ chối ghi lại **cùng khóa hàng**. Nhưng cần hiểu:

1. Nó bảo vệ **`(order_id, sequence_no)`**, không tự bảo đảm một `event_id` không xuất hiện dưới **hai sequence_no khác nhau**.
2. Hai writer đều muốn append `sequence_no = 8`: một writer có thể thắng, writer còn lại phải **đọc/đối soát và quyết định** có tạo event với sequence tiếp theo không.
3. Nếu retry bằng **event ID mới** hoặc tự đổi sequence không kiểm tra business command, hệ thống có thể tạo **hai sự kiện nghiệp vụ tương đương**.
4. Một LWT chỉ đảm bảo điều kiện trên vị trí event; nó **không tự biết** sự kiện `OrderPaid` có hợp lệ khi state hiện tại là `CANCELLED` hay không.
5. Nếu có thể tồn tại **khoảng trống sequence**, người đọc phải định nghĩa rõ cách xử lý, không âm thầm giả định mọi giá trị từ 1 đến N đều chắc chắn tồn tại.

Để có append-only đáng tin, cần phối hợp **quy tắc cấp sequence**, **idempotency key** ổn định và **validation trạng thái** trước khi chấp nhận event. Một cách thiết kế là **single writer/command processor cho mỗi aggregate**; một cách khác dùng CAS và checkpoint. Cả hai đều đòi hỏi mô hình triển khai chứ không phải chỉ một annotation Java.

## 14. Event sourcing: nguồn sự thật, projection và eventual consistency

Trong **event sourcing**, event stream là dữ liệu đã cam kết của aggregate. Trạng thái hiện tại được **reduce/replay** từ các event theo thứ tự hợp lệ:

~~~mermaid
flowchart TD
    A[Business command] --> B[Validate dựa trên state + version]
    B --> C{Command hợp lệ?}
    C -->|Không| D[Reject / conflict]
    C -->|Có| E[Append event có ID và sequence ổn định]
    E --> F[Event stream - nguồn sự thật]
    F --> G[Projector cập nhật order snapshot]
    F --> H[Projector cập nhật timeline/search table]
    G --> I[API đọc trạng thái hiện tại]
    H --> J[API đọc lịch sử]
~~~

**Khác biệt cốt lõi với chỉ lưu snapshot:**

- **Snapshot làm nguồn sự thật:** cập nhật hàng hiện tại, cần cơ chế CAS nếu bảo vệ version; event/audit là thành phần bổ sung.
- **Event stream làm nguồn sự thật:** commit event hợp lệ trước, projector đọc event và cập nhật snapshot; snapshot có thể **trễ hơn** event stream.

Không nên đồng thời tuyên bố **cả snapshot và event log đều là nguồn sự thật duy nhất** nếu hai thao tác ghi chúng không được phối hợp bằng một quy trình đảm bảo. Hãy chọn nơi commit nghiệp vụ thực sự xảy ra.

### 14.1. Projection cần idempotent và có checkpoint

Giả sử một projector nhận lại `OrderPaid` hai lần do retry. Nếu nó chỉ dùng `UPDATE state = 'PAID'` với event ID ổn định, việc lặp có thể an toàn với một số field; nhưng nếu nó đồng thời **cộng tổng tiền, gửi email hoặc phát thanh toán**, chạy hai lần có thể tạo hiệu ứng sai.

Projector nên lưu thông tin như `last_applied_sequence` hoặc một **inbox/deduplication record** theo key phù hợp, và bảo vệ thao tác cập nhật theo mô hình nhất quán đã chọn. Việc đặt offset ở một bảng khác mà không có giao thức khôi phục lỗi vẫn có thể gặp **đã apply nhưng chưa đánh dấu** hoặc **đã đánh dấu nhưng chưa apply**.

Cần thiết kế để **at-least-once delivery** có thể được xử lý an toàn, thay vì giả định mạng và consumer chỉ giao một lần.

### 14.2. Read-after-write với projection có thể cần chờ

Khi lệnh đã append event thành công nhưng projector chưa bắt kịp, API đọc bảng snapshot có thể vẫn thấy `state = CREATED`. Đây là một đặc tính **eventual consistency ở tầng ứng dụng**, khác với CL replica Cassandra.

Các lựa chọn:

- Trả trạng thái **accepted/pending** và phiên bản event đã commit.
- Đọc trực tiếp nguồn sự thật event stream khi nghiệp vụ bắt buộc thấy ngay quyết định vừa ghi.
- Chờ projection đạt **sequence đã xác nhận** trong thời hạn rõ ràng, rồi trả kết quả hoặc pending.
- Thiết kế giao diện hiển thị trạng thái đang xử lý thay vì trả thành công giả cho snapshot chưa cập nhật.

Nâng read CL từ `ONE` lên `QUORUM` **không làm projector chạy nhanh hơn** và không biến dữ liệu chưa được ghi vào snapshot thành dữ liệu sẵn có.

## 15. Khi kết hợp LWT với event log, bài toán hai lần ghi vẫn còn

Một cách triển khai dễ nghĩ tới:

~~~text
1. UPDATE orders_by_id ... IF version = 7        -> [applied] = true
2. INSERT order_events_by_order (...)           -> thất bại/timeout
3. API thông báo trạng thái...
~~~

**LWT của bước 1 không làm bước 2 nguyên tử theo nó.** Sau bước 1, snapshot đã đổi nhưng timeline có thể thiếu event. Đảo thứ tự để ghi event trước cũng có thể tạo event đã lưu nhưng state chuyển đổi thất bại.

~~~mermaid
flowchart LR
    A[CAS state row] --> B{Đã áp dụng?}
    B -->|Có| C[Append event row]
    B -->|Không| D[Conflict]
    C --> E{Append thành công?}
    E -->|Có| F[Hoàn tất workflow]
    E -->|Không rõ / lỗi| G[Cần retry/đối soát bền vững]
~~~

Các phương án phải cân nhắc **rõ ràng**:

1. **Một nguồn sự thật duy nhất:** event stream được chấp nhận bằng một cơ chế append/sequence an toàn, còn bảng state là projection có thể tái tạo. Khi đó cần bảo vệ state transition ngay ở quá trình commit event, không chỉ ở projector.
2. **Snapshot làm nguồn sự thật + outbox/handoff bền vững:** ghi nhận ý định phát event theo một giao thức có thể đối soát/retry. Trong Cassandra, phải kiểm tra thật kỹ có thể đặt những dữ liệu nào trong **cùng partition/mutation** và giới hạn conditional batch của phiên bản.
3. **Workflow/saga có đối soát:** nếu hai bảng khác partition hoặc hai hệ thống độc lập, chấp nhận các bước riêng và xây cơ chế phát hiện/chữa trạng thái giữa chừng.
4. **Đơn giản hóa yêu cầu:** nếu chỉ cần audit kỹ thuật, có thể dùng một luồng audit được thiết kế rõ mức độ tin cậy thay vì gọi nó là event-sourcing source-of-truth.

**Không mặc định dùng CQL `BATCH` là có transaction ACID nhiều bảng/partition.** Batch trong Cassandra có quy tắc atomicity và hiệu năng riêng, nhưng không cho bạn **isolation/serializability đa partition** tương đương RDBMS và không tự giải quyết tranh chấp nghiệp vụ xuyên các bản sao dữ liệu.

## 16. Quyết định theo yêu cầu: timestamp, LWT hay sự kiện?

| Yêu cầu nghiệp vụ | Cơ chế phù hợp để bắt đầu | Điều phải thiết kế thêm |
| --- | --- | --- |
| Chỉ cần giá trị cuối của một cảm biến, chấp nhận write mới thay giá trị cũ | Ghi thường + quy tắc timestamp rõ | Late data, clock skew, idempotent retry |
| Đơn hàng không được ghi đè sau khi writer khác cập nhật | LWT `IF version = ?` | Mọi write path tuân thủ version, xử lý conflict |
| Chỉ cho phép `CREATED → PAID` | LWT `IF state = ?` hoặc guard kết hợp | State machine và test cạnh tranh |
| Username duy nhất theo tenant | Bảng reservation khóa nghiệp vụ + `IF NOT EXISTS` | Chuẩn hóa username, workflow profile |
| Xem toàn bộ quá trình thay đổi đơn hàng | Event log/audit có event ID | Retention, tính toàn vẹn, truy vấn timeline |
| Replay để xây lại bảng đọc | Event sourcing | Sequence, projector, versioned schema, checkpoint |
| Cập nhật state và phát sự kiện cho hệ khác | Event sourcing hoặc outbox/workflow phù hợp | Handoff bền vững, retry, dedup và đối soát |
| Nhiều thay đổi cùng một account cần thứ tự nghiêm ngặt | Single-writer theo aggregate hoặc CAS + sequence | Partition hot, throughput, availability |
| Query “đơn hàng mới nhất theo customer” | Bảng theo truy vấn + clustering key | Đồng bộ denormalization và paging |

**Chọn theo bất biến, không theo sở thích cú pháp:**

- Nếu **không cần ghi đè có điều kiện** và **không cần lịch sử**, timestamp/LWW có thể đủ.
- Nếu cần **từ chối một quyết định dựa trên trạng thái cũ**, dùng LWT hoặc một cơ chế phân xử tương đương.
- Nếu cần **lịch sử/tái tạo**, dùng event log đúng nghĩa.
- Nếu cần **cả hai**, phải thiết kế ranh giới commit và cơ chế đối soát, không chỉ thêm hai câu INSERT vào service.

## 17. Timeout, retry và idempotency ở cả hai mô hình

### 17.1. “Không nhận được success” không đồng nghĩa “chưa ghi gì”

Một `WriteTimeout` có thể xảy ra khi một số replica đã nhận mutation hoặc khi kết quả LWT đã được quyết định nhưng response không đến client kịp. Không được lập trình:

~~~java
try {
    gateway.payIfUnchanged(orderId, version, now);
} catch (Exception ex) {
    // SAI: không thể kết luận CAS chưa xảy ra.
    return "NOT_APPLIED";
}
~~~

Cách tiếp cận tốt hơn là **phân biệt applied, conflict và unknown**:

~~~java
public enum TransitionOutcome {
    APPLIED,
    CONFLICT,
    UNKNOWN
}
~~~

Đây là enum mô tả **hợp đồng ứng dụng**, không phải mapping tự động từ mọi exception của driver. Trong thực tế, cần phân loại lỗi rõ ràng: một lỗi CQL sai schema chắc chắn không được coi là “unknown” kiểu timeout; lỗi auth/validation phải được sửa hoặc trả lỗi tương ứng.

### 17.2. Idempotency cho command

Một request `PayOrder` nên mang **requestId ổn định** qua các lần retry. Nếu lần đầu đã thành công nhưng client mất response, lần thử lại `IF version = 7` có thể nhận false vì version đã thành 8.

Nếu không có request ID hoặc một dấu vết kết quả bền vững, server có thể không biết:

- Chính request này đã được áp dụng trước đó.
- Một request khác đã áp dụng thao tác cạnh tranh.
- Đơn hàng đã chuyển trạng thái hợp lệ do sự kiện khác.

Giải pháp có thể là **idempotency record**, event ID, correlation ID hoặc một trường/record mô tả command đã được xử lý. Phải chọn **khóa duy nhất ổn định**, thời hạn giữ và cơ chế ghi/đọc đối soát phù hợp; một map in-memory trong một instance không đủ cho nhiều instance.

### 17.3. Retry event không được tạo event mới ngẫu nhiên

Khi client gửi lại một command, nếu mỗi lần server tạo `UUID.randomUUID()` mới cho event mà không kiểm tra request ID, event log có thể chứa **hai `OrderPaid` cho cùng ý định**. Việc event sử dụng primary key riêng không tự giải quyết idempotency.

**Phải quyết định lúc nào event ID được cấp và giữ cố định giữa các lần thử**. Với log theo `sequence_no`, còn cần cơ chế bảo vệ việc cấp sequence. Retry sau timeout phải ưu tiên **đối soát event/command cũ**, không phải luôn append thêm một hàng mới.

## 18. Spring Data Cassandra và ranh giới sử dụng công cụ

### 18.1. Repository, CassandraTemplate cho đường CRUD

Entity snapshot:

~~~java
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_id")
public class OrderSnapshot {
    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("state")
    private String state;

    @Column("version")
    private Long version;

    @Column("updated_at")
    private Instant updatedAt;

    protected OrderSnapshot() {}

    public OrderSnapshot(UUID orderId, String state,
                         Long version, Instant updatedAt) {
        this.orderId = orderId;
        this.state = state;
        this.version = version;
        this.updatedAt = updatedAt;
    }

    public UUID getOrderId() { return orderId; }
    public String getState() { return state; }
    public Long getVersion() { return version; }
    public Instant getUpdatedAt() { return updatedAt; }
}
~~~

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrderSnapshotRepository
        extends CassandraRepository<OrderSnapshot, UUID> {
}
~~~

`repository.findById(orderId)` thuận tiện để đọc snapshot, và `CassandraTemplate` có thể thực hiện thao tác entity. Nhưng **`repository.save(snapshot)` không tự kiểm tra version** theo ý nghĩa CAS chỉ vì entity có field `version`. Khi nghiệp vụ đòi bảo vệ version, cần dùng một đường conditional write được xác minh.

### 18.2. CqlSession cho thao tác cần kết quả CAS

Trong cùng service, có thể:

~~~text
OrderSnapshotRepository.findById(...) -> đọc trạng thái hiện tại
OrderTransitionGateway.payIfUnchanged(...) -> LWT và wasApplied()
EventRepository / CassandraTemplate -> truy cập event/projection theo schema
~~~

Các thành phần cần dùng **đúng keyspace và session**. Với ứng dụng nhiều session, dùng `@Qualifier`; không chuẩn bị statement ở session A rồi execute tùy tiện trên session B. Spring context quản lý vòng đời `CqlSession`, không tạo/đóng connection theo từng request.

### 18.3. Event log cần mapping bất biến và schema có version

Khi ánh xạ event thành entity:

- Khóa event/sequence **không được thay đổi** sau khi ghi.
- `event_type` và `payload` phải có schema version hoặc cách parse tương thích.
- Nếu payload thay đổi định dạng, consumer cũ cần có đường xử lý hoặc migration.
- Không dùng `repository.save(existingEvent)` để “sửa lịch sử” trừ khi nghiệp vụ thực sự chấp nhận thay đổi event log; nếu cần correction, thường append một **event hiệu chỉnh**.
- Không để việc xóa TTL tự động phá khả năng replay của một nguồn sự thật nếu retention chưa được thiết kế.

**Event log là một hợp đồng dữ liệu lâu dài**, không chỉ là một entity Java có nhiều field.

## 19. Kiểm thử: chứng minh timestamp không thay thế CAS

### 19.1. Chuẩn bị môi trường

Dùng Cassandra **thử nghiệm**, có keyspace `app_ks` với replication factor và datacenter phù hợp. Tạo hai bảng `orders_by_id` và `order_events_by_order` như trên. Không chạy thử node failure hoặc inject clock skew trên production.

### 19.2. Test xung đột write timestamp

1. Ghi `state = PAID` ở một write timestamp đã chọn.
2. Ghi `state = CANCELLED` với **timestamp nhỏ hơn** vào cùng cột.
3. Đọc lại `state` và `WRITETIME(state)`.
4. Quan sát rằng **thứ tự request không đủ để quyết định giá trị cuối**.
5. Thực hiện test trên bản ghi mới, không tái sử dụng dữ liệu có future timestamp từ lần thử khác.

### 19.3. Test hai writer cùng expected version

Giả sử một hàng `state = CREATED`, `version = 7`. Đồng bộ hai worker để cả hai đều dùng `expectedVersion = 7`:

~~~text
Writer A: IF version = 7 AND state = CREATED -> PAID, version = 8
Writer B: IF version = 7 AND state = CREATED -> CANCELLED, version = 8

Expected:
  Một winner nhận [applied] = true;
  writer còn lại nhận [applied] = false;
  state/version cuối phản ánh kết quả được áp dụng.
~~~

Đây là test phải chạy với Cassandra thật để kiểm tra CAS/Paxos. Một mock repository trả boolean không chứng minh được **tính loại trừ của conditional write**.

### 19.4. Test kết quả ứng dụng

| Trường hợp | Hành động | Kỳ vọng |
| --- | --- | --- |
| Conditional insert khi khóa chưa tồn tại | `INSERT IF NOT EXISTS` | `[applied] = true` |
| Conditional insert khi khóa đã tồn tại | Gửi lại với cùng khóa | `false`; không upsert nội dung mới |
| LWT chuyển trạng thái hợp lệ | `IF state = 'CREATED'` | `true` |
| LWT chuyển trạng thái đã lỗi thời | `IF version = 7` sau khi version đã thành 8 | `false`; không ghi đè |
| Write thông thường cùng cột | Gửi mutation với timestamp cao/thấp | Giá trị quan sát tuân theo hòa giải timestamp |
| LWT gặp timeout | Gián đoạn response trong lab | **Không** ánh xạ thành conflict chắc chắn |
| Event ID/sequence trùng | `INSERT ... IF NOT EXISTS` | Chỉ một hàng cùng primary key được chấp nhận |
| Retry command với request ID ổn định | Gửi hai lần cùng ý định | Không tạo hai hiệu ứng nghiệp vụ |
| Projection xử lý lại event | Replay cùng event | Không cộng/gửi hiệu ứng hai lần |
| Event append xong, projection chưa chạy | Đọc snapshot | Có thể trễ; API xử lý theo hợp đồng |

### 19.5. Test timeout và phục hồi

Một tình huống khó nhưng quan trọng: gateway ghi `OrderPaid` và client mất kết nối trước khi nhận response. Sau reconnect:

1. **Không tự gán** lệnh ban đầu là thất bại.
2. Đọc trạng thái/event theo ID ổn định với CL phù hợp.
3. Đối chiếu `requestId`/`eventId` và version.
4. Nếu đã xử lý, trả **idempotent replay**; nếu chưa, thực hiện lại theo chính sách guarded write.
5. Nếu vẫn không xác định được, trả một trạng thái **pending/unknown** phù hợp, có cơ chế kiểm tra lại.

Điều này cần kiểm thử ở mức integration/fault injection có kiểm soát; không thể chứng minh đầy đủ chỉ bằng unit test của method Java.

## 20. Hiệu năng và vận hành: đừng biến mọi write thành LWT

Các chỉ số nên quan sát:

| Metric/tín hiệu | Vì sao quan trọng |
| --- | --- |
| P50/P95/P99 latency của write thường và LWT | Đo chi phí Paxos và contention thực tế |
| Tỷ lệ CAS `[applied] = false` | Phản ánh tranh chấp hoặc expected version cũ |
| `WriteTimeout`, `Unavailable`, retry rate | Đánh giá xác nhận/khôi phục và trạng thái chưa rõ |
| Hot partition, số concurrent writers trên một key | Nhiều LWT cùng khóa có thể tạo bottleneck |
| Đồng bộ đồng hồ / timestamp anomalies | Phát hiện future timestamps và xung đột bất thường |
| Số event theo aggregate/partition | Kiểm soát kích thước partition và chi phí replay |
| Lag của projector (sequence/age) | Đánh giá độ trễ read model so với nguồn sự thật |
| Số event bị xử lý lặp hoặc bỏ sót | Kiểm chứng idempotency/checkpoint |
| Tombstone/TTL/compaction | Tránh read amplification và mất dữ liệu cần replay |
| Độ trễ đa datacenter và failover | Không suy diễn bảo đảm xuyên vùng từ local CL |

**Bốn nguyên tắc vận hành:**

1. Chỉ dùng LWT khi **một bất biến nghiệp vụ cần CAS**; telemetry không có cạnh tranh quan trọng thường không cần.
2. Nếu audit/replay là yêu cầu, thiết kế **event retention và sequence** ngay từ đầu; Cassandra TTL không phải cơ chế archive.
3. Nếu đọc timeline, chọn partition key và clustering key theo access pattern, dùng `LIMIT`/paging; không làm `SELECT *` trên tập event không giới hạn.
4. Đo **tải hệ thống thật**. Prepared statement tối ưu overhead chuẩn bị truy vấn, nhưng không làm các pha Paxos hay reconciliation event miễn phí.

## 21. Bài thực hành tổng hợp: chọn cơ chế theo đúng yêu cầu

**Bối cảnh:** ứng dụng có API tạo đơn hàng, thanh toán, hủy đơn và xem timeline. Có nhiều instance Spring Boot cùng truy cập Cassandra.

**Yêu cầu:**

1. Tạo schema `orders_by_id` với `state`, `version` và `updated_at`.
2. Viết một lệnh `UPDATE` không điều kiện và quan sát lost update trong tình huống hai writer.
3. Thử hai mutation có `USING TIMESTAMP` khác nhau, so sánh `WRITETIME(state)` với `updated_at`.
4. Viết `INSERT IF NOT EXISTS` cho việc tạo hàng; kiểm tra hai writer cùng tạo một `order_id`.
5. Viết `UPDATE ... IF version = ? AND state = ?` để chỉ thanh toán đơn ở trạng thái `CREATED`.
6. Sử dụng Java driver và `ResultSet.wasApplied()`; phân biệt `APPLIED`, `CONFLICT` và lỗi/`UNKNOWN`.
7. Kiểm tra đường `repository.save(...)` có thể phá version guard nếu được gọi không điều kiện; đưa ra quy tắc code review.
8. Tạo `order_events_by_order` và định nghĩa event type, event ID, `sequence_no`, serialization version.
9. Thử hai writer append cùng sequence. Giải thích vì sao `IF NOT EXISTS` chỉ bảo vệ khóa event, không tự bảo vệ state machine.
10. Xây một projector đơn giản tạo `OrderSnapshot` từ event sequence; cho chạy lại một event và xác minh không tạo hiệu ứng hai lần.
11. Mô phỏng bước CAS thành công nhưng append event lỗi. Đề xuất nguồn sự thật và quy trình đối soát, không tuyên bố hai bảng đã nguyên tử.
12. Thêm retry sau timeout với `requestId` ổn định; đảm bảo không tạo hai kết quả nghiệp vụ.
13. Đo latency, tỷ lệ CAS conflict, số event, số trang CQL và độ trễ projection.

**Tiêu chí đạt:** người học giải thích và chứng minh được **timestamp giải quyết hòa giải phiên bản**, **LWT giải quyết kiểm tra điều kiện**, còn **event log giải quyết lưu lịch sử/replay**. Khi kết hợp chúng, thiết kế phải chỉ rõ **ranh giới commit, idempotency, sequence, nguồn sự thật và phục hồi lỗi**.

## 22. Câu hỏi tự kiểm tra

1. Write timestamp nội bộ của Cassandra khác gì cột `updated_at timestamp`?
2. Vì sao một request được gửi **sau** vẫn có thể không thắng mutation trước?
3. `WRITETIME(state)` có cho biết lịch sử các trạng thái cũ không? Vì sao?
4. Nếu cả hai writer dùng `LOCAL_QUORUM`, tại sao lost update vẫn có thể xảy ra?
5. Khi nào ghi không điều kiện theo LWW là chấp nhận được?
6. `IF EXISTS` có đủ để bảo vệ chuyển trạng thái `CREATED → PAID` không?
7. `IF version = ?` giải quyết vấn đề gì mà write timestamp không giải quyết?
8. `[applied] = false` khác với exception `WriteTimeout` thế nào?
9. Serial consistency của LWT khác regular consistency ở đâu?
10. Vì sao LWT thường đắt hơn một write không điều kiện?
11. Event sourcing khác gì một bảng audit ghi thêm?
12. Vì sao `occurred_at` hoặc timeuuid không tự bảo đảm thứ tự nhân quả của event?
13. `INSERT IF NOT EXISTS` vào bảng event bảo vệ khóa nào, và **không** bảo vệ điều gì về `event_id`?
14. Tại sao cách cấp `sequence_no = MAX + 1` bằng đọc rồi ghi không điều kiện có race condition?
15. Vì sao projector phải hỗ trợ idempotency khi đọc event lặp lại?
16. Khi event đã commit nhưng snapshot chưa cập nhật, nâng read CL của snapshot có làm dữ liệu xuất hiện ngay không?
17. Nếu ghi snapshot bằng CAS rồi append event ở bảng khác thất bại, có thể khẳng định cả hai ghi nguyên tử không?
18. Vì sao retry sau timeout cần request ID/event ID ổn định?
19. Khi một aggregate có hàng triệu event, partition key và paging cần thay đổi thế nào?
20. Với ba yêu cầu: đo nhiệt độ mới nhất, chống hủy đơn đã trả tiền, và tái tạo lịch sử thanh toán — bạn chọn cơ chế gì cho từng yêu cầu và vì sao?

**Ghi nhớ:** **timestamp/LWW giúp Cassandra hòa giải phiên bản cell, nhưng không hiểu điều kiện nghiệp vụ và không lưu lịch sử**. Khi cần bảo vệ state transition hoặc tránh mất cập nhật, dùng **LWT với `IF version`/`IF state`** hay một cơ chế phân xử tương đương. Khi cần audit, replay và dựng nhiều read model, thiết kế **event log/event sourcing** với ID ổn định, sequence, projector và idempotency. Trong Spring Data Cassandra, các cơ chế đó vẫn phải đi cùng **partition key đúng, consistency rõ ràng, paging có giới hạn, xử lý timeout và quy trình phục hồi dữ liệu phân tán**.
