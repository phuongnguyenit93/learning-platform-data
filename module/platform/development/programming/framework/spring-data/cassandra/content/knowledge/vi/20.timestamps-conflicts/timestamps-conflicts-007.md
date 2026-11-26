# USING TIMESTAMP và các tùy chọn ghi của Spring Data Cassandra

Apache Cassandra cho phép nhiều client ghi cùng một primary key thông qua những coordinator khác nhau. Khi hai mutation cùng tác động lên một ô dữ liệu (*cell*), hệ thống cần một quy tắc để quyết định giá trị nào sẽ thắng khi các replica hội tụ. Một yếu tố quan trọng của quy tắc này là **write timestamp**: mỗi giá trị được ghi có một timestamp ở độ phân giải **microsecond**, và Cassandra thường áp dụng cơ chế **last-write-wins dựa trên timestamp**, không đơn giản dựa vào thứ tự request đến server.

Trong CQL, mệnh đề `USING TIMESTAMP` cho phép lập trình viên **chỉ định write timestamp tường minh**. Ở tầng ứng dụng, **Spring Data Cassandra** có những tùy chọn ghi (ví dụ `InsertOptions`, `UpdateOptions`, `WriteOptions` tùy API/phiên bản); **Java Driver** còn có tùy chọn timestamp ở mức statement. Cần hiểu chính xác các nguồn timestamp và độ ưu tiên giữa những cơ chế này trước khi áp dụng vào bài toán cập nhật trạng thái, backfill, retry, TTL hoặc dữ liệu được ghi từ nhiều vùng.

Bài học thuộc chương **Timestamp và xung đột** của module `SPRING_DATA_CASSANDRA`. Mục tiêu không chỉ là nhớ cú pháp CQL, mà là xây dựng **quy tắc ghi có thể dự đoán được** khi dùng entity mapping, repository, CassandraTemplate, truy vấn CQL, partition key, consistency level, paging và vận hành cluster phân tán.

> **Nguyên tắc cốt lõi:** timestamp ghi là một phần của **metadata phiên bản của dữ liệu trong Cassandra**. Nó **khác** cột nghiệp vụ `created_at`/`updated_at`, không phải số thứ tự giao dịch, và không tự giải quyết ghi cạnh tranh theo logic nghiệp vụ. Đặt timestamp thủ công sai có thể khiến dữ liệu mới bị một giá trị cũ có timestamp cao hơn che khuất trong thời gian dài.

## 1. Ba khái niệm thời gian rất dễ nhầm

Giả sử một row chứa cột CQL `updated_at timestamp`. Ta có thể gặp ba giá trị thời gian khác nhau:

| Khái niệm | Nơi xuất hiện | Ý nghĩa |
|---|---|---|
| **Write timestamp** | Metadata của cell/mutation trong Cassandra | Thứ tự ưu tiên khi các ghi cạnh tranh vào cùng cell; đơn vị **microsecond** |
| **Cột CQL `timestamp`** | Giá trị của cột như `updated_at`, `created_at` | Một thời điểm nghiệp vụ; driver thường ánh xạ sang Java `Instant`, chính xác đến **millisecond** ở kiểu CQL thông dụng |
| **Thời điểm client gửi/nhận request** | Log, metrics, đồng hồ ứng dụng | Mốc quan sát giao dịch; không nhất thiết trùng write timestamp |

Ví dụ:

```sql
UPDATE orders_by_id
USING TIMESTAMP 1760000000000000
SET state = 'PAID',
    updated_at = '2026-11-25T03:30:00Z'
WHERE order_id = 11111111-1111-1111-1111-111111111111;
```

`1760000000000000` là **write timestamp tính bằng microsecond từ Unix epoch**. Chuỗi `2026-11-25T03:30:00Z` là **giá trị** lưu vào cột `updated_at`; nó không phải timestamp mà Cassandra dùng để quyết định mutation này thắng hay thua. Hai giá trị được chọn khác nhau có chủ đích để nhấn mạnh rằng chúng **không tự đồng bộ**.

Không dùng `Instant.toEpochMilli()` rồi đưa thẳng vào `USING TIMESTAMP`: một giá trị millisecond chỉ khoảng 13 chữ số ở thời đại hiện nay, trong khi microsecond có khoảng 16 chữ số. Nhầm đơn vị khiến dữ liệu bị gán timestamp quá xa trong quá khứ; ngược lại tự nhân sai có thể tạo timestamp quá xa trong tương lai.

## 2. Cấu trúc bảng để học về xung đột ghi

Dùng bảng đọc theo primary key đơn, để việc chọn partition không làm nhiễu bài học:

```sql
CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    state text,
    total_minor bigint,
    updated_at timestamp
);
```

Các thuộc tính:

- `order_id` là partition key; thao tác `WHERE order_id = ?` chạm đến một logical partition.
- `state` là trạng thái nghiệp vụ, ví dụ `NEW`, `PAID` hoặc `CANCELLED`.
- `total_minor` là số tiền ở đơn vị nhỏ nhất; tránh dùng số thực cho phép tính cần chính xác tuyệt đối.
- `updated_at` là cột nghiệp vụ kiểu CQL `timestamp`, **không phải writetime của toàn row**.
- Những cell như `state` và `total_minor` có thể được ghi vào **các thời điểm khác nhau**.

Cassandra phân phối partition đến các replica theo keyspace replication strategy. Một request có `LOCAL_QUORUM` không nhất thiết có write timestamp cao hơn request `LOCAL_ONE`; **consistency level và write timestamp giải quyết hai vấn đề khác nhau**.

Để minh họa ngữ nghĩa, bài dùng một ID test cố định. Trong ứng dụng thật, ID phải được quản lý theo quy tắc idempotency và tránh ghi nhầm dữ liệu production.

## 3. Last-write-wins theo timestamp: không phải “request đến sau thắng”

Khi các mutation tác động lên **cùng cell**, Cassandra so sánh write timestamp để chọn bản ghi cần được giữ khi hòa giải dữ liệu. Ví dụ:

```text
Cell: orders_by_id.state, order_id = O1

Mutation A: state='PAID',      writetime = 1_760_000_000_000_100
Mutation B: state='CANCELLED', writetime = 1_760_000_000_000_090

Kết quả ưu tiên theo timestamp: 'PAID'
Dù B có thể đến coordinator sau A.
```

Cassandra không thực hiện “last-arrival-wins” theo thứ tự xử lý request trên một coordinator. Nó có thể nhận ghi từ các client/coordinator khác nhau, ở các replica khác nhau và vào những thời điểm mạng khác nhau. **Thứ tự được quyết định bởi metadata timestamp của cell** khi có xung đột.

### Xung đột thường được xét ở cấp cell

Một update chỉ thay `state` không buộc `total_minor` có writetime giống `state`:

```sql
UPDATE orders_by_id
USING TIMESTAMP 1760000000000100
SET state = 'PAID'
WHERE order_id = 11111111-1111-1111-1111-111111111111;

UPDATE orders_by_id
USING TIMESTAMP 1760000000000200
SET total_minor = 125000
WHERE order_id = 11111111-1111-1111-1111-111111111111;
```

Sau hai lệnh, `state` có thể mang timestamp `...0100`, còn `total_minor` có timestamp `...0200`. Không nên giả định “row đã được update ở thời điểm X” giống nhau cho mọi cột.

Ngoài ra, việc ghi một entity bằng template/repository có thể tác động **nhiều cột** tùy cách converter tạo statement và chính sách xử lý null. Khi chỉ muốn sửa một cột, cần chọn API update đúng trường thay vì vô tình ghi lại giá trị cũ của các cột khác với timestamp mới.

## 4. Điều gì xảy ra nếu hai ghi có cùng timestamp?

Trong thực tế, hai mutation có thể nhận **cùng write timestamp**, nhất là khi client tự đặt một timestamp cố định cho nhiều lần ghi hoặc nhiều producer có đồng hồ/độ phân giải không được điều phối. Cassandra có quy tắc quyết định để hòa giải dữ liệu cùng timestamp; kết quả **không** được phép dựa vào thứ tự HTTP request đến ứng dụng.

Ở mức khái quát:

- Nếu **live values khác nhau** có cùng timestamp, Cassandra dùng quy tắc tie-break xác định dựa trên biểu diễn nội bộ/giá trị cell.
- **Tombstone (dấu xóa)** có quy tắc ưu tiên đặc biệt khi timestamp bằng nhau, để việc xóa không bị một giá trị sống cùng timestamp ghi đè tùy ý.
- Với collection, TTL hoặc loại mutation khác, chi tiết hòa giải phụ thuộc kiểu dữ liệu và semantics Cassandra; không nên suy luận từ thứ tự chữ cái của hai `String` Java.

**Không thiết kế nghiệp vụ dựa vào tie-break khi timestamp bằng nhau.** Nếu trạng thái `PAID` và `CANCELLED` loại trừ nhau về mặt nghiệp vụ, đừng hy vọng Cassandra chọn “đúng” theo thứ tự tên hằng. Cần cơ chế chuyển trạng thái có điều kiện (LWT) hoặc một quy trình single-writer/serialization phù hợp.

## 5. Cú pháp USING TIMESTAMP của CQL

`USING TIMESTAMP` đưa timestamp của mutation vào lệnh CQL. Giá trị là số nguyên 64-bit biểu diễn **microsecond từ Unix epoch**.

### INSERT

```sql
INSERT INTO orders_by_id (
    order_id, customer_id, state, total_minor, updated_at
) VALUES (
    11111111-1111-1111-1111-111111111111,
    22222222-2222-2222-2222-222222222222,
    'NEW',
    125000,
    '2026-11-25T03:30:00Z'
)
USING TIMESTAMP 1760000000000000;
```

### UPDATE

```sql
UPDATE orders_by_id
USING TIMESTAMP 1760000000000100
SET state = 'PAID'
WHERE order_id = 11111111-1111-1111-1111-111111111111;
```

### DELETE

```sql
DELETE state
FROM orders_by_id
USING TIMESTAMP 1760000000000200
WHERE order_id = 11111111-1111-1111-1111-111111111111;
```

Delete với một cột tạo dấu xóa phù hợp cho `state`; xóa toàn row/partition có phạm vi tombstone khác. Dù statement được coordinator nhận trước hay sau một ghi khác, **timestamp mutation** vẫn đóng vai trò quyết định kết quả khi xung đột.

### TTL cùng write timestamp

Với những loại mutation hỗ trợ TTL:

```sql
INSERT INTO orders_by_id (
    order_id, state, total_minor
) VALUES (
    33333333-3333-3333-3333-333333333333,
    'NEW',
    125000
)
USING TTL 3600 AND TIMESTAMP 1760000000000000;
```

`TTL 3600` nghĩa là dữ liệu được ghi chịu thời hạn sống khoảng **3.600 giây** theo semantics TTL của Cassandra. `TIMESTAMP ...` là metadata dùng giải quyết xung đột. Hai tham số này **không phải cùng một khái niệm thời gian**; TTL liên quan expiration và tombstone, còn timestamp ảnh hưởng hòa giải mutation.

Tùy loại statement, thứ tự `TTL`/`TIMESTAMP` và hỗ trợ của Cassandra version, hãy xác minh bằng CQL parser của môi trường thật. Không phải mọi loại mutation (ví dụ counter updates hoặc một số thao tác conditional) đều cho phép dùng `USING TIMESTAMP` theo cách thông thường.

## 6. Đọc write timestamp bằng hàm WRITETIME

Để xem timestamp của một cell, có thể dùng hàm CQL `WRITETIME(column)` khi kiểu cột được hỗ trợ:

```sql
SELECT state,
       WRITETIME(state) AS state_written_us,
       total_minor,
       WRITETIME(total_minor) AS total_written_us,
       updated_at,
       WRITETIME(updated_at) AS updated_at_written_us
FROM orders_by_id
WHERE order_id = 11111111-1111-1111-1111-111111111111;
```

Kết quả minh họa:

```text
state  | state_written_us  | total_minor | total_written_us
-------+-------------------+-------------+-----------------
PAID   | 1760000000000100  | 125000      | 1760000000000000
```

Không có một `WRITETIME(row)` chung cho mọi cell. Nếu cột chưa có giá trị, hàm có thể trả null; quy tắc cho collection, UDT và những dạng cột đặc biệt cần kiểm tra theo phiên bản Cassandra.

**Không gọi `WRITETIME` trên partition key/clustering key như thể chúng là cell dữ liệu thông thường**, và không áp dụng máy móc lên counter hoặc collection phức tạp. Khi muốn audit toàn bộ lịch sử thay đổi, `WRITETIME` **không đủ**: nó chỉ phản ánh metadata của giá trị còn có thể đọc, không phải nhật ký các mutation đã diễn ra.

### Đối chiếu với cột updated_at

```sql
SELECT updated_at,
       WRITETIME(updated_at) AS updated_at_write_us
FROM orders_by_id
WHERE order_id = ?;
```

`updated_at` trả về giá trị CQL timestamp do ứng dụng ghi, còn `updated_at_write_us` là microsecond write timestamp của **cell updated_at**. Chúng hoàn toàn có thể khác nhau, và điều đó không phải lỗi driver.

## 7. Kiểm chứng độ lớn và đơn vị microsecond trong Java

Java `Instant` có giây và nanosecond. Cassandra write timestamp được biểu diễn bằng microsecond từ epoch, nên cần chuyển đổi **rõ ràng**:

```java
import java.time.Instant;

public final class CassandraTimestampUtil {
    private CassandraTimestampUtil() {}

    public static long toEpochMicros(Instant instant) {
        long secondsMicros = Math.multiplyExact(
            instant.getEpochSecond(), 1_000_000L
        );
        long fractionalMicros = instant.getNano() / 1_000L;
        return Math.addExact(secondsMicros, fractionalMicros);
    }

    public static Instant fromEpochMicros(long micros) {
        long seconds = Math.floorDiv(micros, 1_000_000L);
        long microPart = Math.floorMod(micros, 1_000_000L);
        return Instant.ofEpochSecond(seconds, microPart * 1_000L);
    }
}
```

`Math.floorDiv` và `Math.floorMod` giúp xử lý đúng thời điểm trước epoch, thay vì tự chia số âm bằng phép chia làm tròn về 0. `Math.multiplyExact`/`addExact` làm lỗi overflow lộ rõ thay vì âm thầm tạo timestamp sai.

Ví dụ:

```java
Instant instant = Instant.parse("2026-11-25T03:30:00.123456Z");
long writeTimestampMicros =
    CassandraTimestampUtil.toEpochMicros(instant);

Instant roundTrip =
    CassandraTimestampUtil.fromEpochMicros(writeTimestampMicros);

assert roundTrip.equals(instant);
```

Phần assert ở trên chỉ đúng cho `Instant` có phần lẻ chính xác đến microsecond; nếu instant ban đầu có nanosecond không chia hết cho 1.000, việc chuyển sang microsecond **cắt bỏ phần nhỏ hơn microsecond**. Đây là quy tắc dữ liệu, không phải chi tiết có thể bỏ qua.

Cách lấy microsecond đơn giản từ millisecond:

```java
long micros = Math.multiplyExact(
    instant.toEpochMilli(), 1_000L
);
```

Phép này **mất độ chính xác sub-millisecond**; chỉ dùng nếu hệ thống chủ ý làm việc ở độ phân giải millisecond. Không dùng kết quả `instant.toEpochMilli()` trực tiếp làm timestamp mutation.

## 8. Mặc định lấy write timestamp từ đâu?

Nếu CQL **không có `USING TIMESTAMP`**, Cassandra/driver vẫn cần một write timestamp cho mutation. Trong Java Driver, việc tạo timestamp phía client có thể được thực hiện bằng **timestamp generator** được cấu hình cho session; nếu không gửi explicit query timestamp, server có thể tạo timestamp tùy cấu hình và giao thức.

Vì vậy, thứ tự các khái niệm thường là:

```text
1. CQL có USING TIMESTAMP tường minh?
       → CQL quyết định timestamp của mutation đó.

2. Nếu không có, statement có explicit query timestamp?
       → Driver gửi timestamp theo statement API khi hỗ trợ.

3. Nếu không có explicit override, driver dùng timestamp generator?
       → Giá trị do cơ chế generator được cấu hình tạo ra.

4. Nếu request không mang timestamp từ client:
       → Coordinator/server có thể đặt timestamp.
```

Đây là mô hình lựa chọn theo API; **tránh đồng thời cấu hình nhiều nguồn timestamp cho cùng statement** rồi phụ thuộc vào một thứ tự ưu tiên chưa được kiểm chứng. Hãy chọn một chiến lược nhất quán trong team và test trên version driver thực tế.

### Vì sao clock skew nguy hiểm?

Hai ứng dụng viết vào cùng row có thể chạy ở hai server với đồng hồ khác nhau:

```text
Client A: clock nhanh hơn thực tế 5 phút
Client B: clock gần đúng

A ghi state='PAID'      với timestamp rất cao
B ghi state='REFUNDED'  sau A theo nghiệp vụ, nhưng timestamp thấp hơn

Khi hòa giải theo timestamp:
  'PAID' có thể tiếp tục thắng dù thao tác của B đến sau.
```

Đây là một nguyên nhân của **future timestamp poisoning**: một giá trị được ghi với timestamp vô tình nằm xa trong tương lai có thể che khuất nhiều cập nhật hợp lệ tiếp theo. Giải pháp không chỉ là tăng consistency level; cần kiểm soát đồng hồ/NTP, nguồn timestamp, giới hạn độ lệch và quy tắc update cạnh tranh.

### Timestamp generator không phải global sequencer

Một generator monotonic trong một `CqlSession` có thể hạn chế tạo hai timestamp bằng hoặc lùi nhau **trong phạm vi generator đó**. Nó không đảm bảo thứ tự toàn cục giữa nhiều JVM, nhiều region hoặc nhiều producer. Khi yêu cầu nghiệp vụ là “trạng thái A chỉ được chuyển sang B”, **LWT hoặc mô hình điều phối một writer** phù hợp hơn một tập đồng hồ client.

## 9. Java Driver 4.x: đặt timestamp ở mức statement

Java Driver 4.x cung cấp API để điều chỉnh **query timestamp** của statement. Ví dụ dạng prepared/bound:

```java
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

public final class StateWriter {
    private final CqlSession session;
    private final PreparedStatement update;

    public StateWriter(CqlSession session) {
        this.session = session;
        this.update = session.prepare(
            "UPDATE orders_by_id " +
            "SET state = ? WHERE order_id = ?"
        );
    }

    public void updateState(
            UUID orderId, String state, long timestampMicros) {

        if (orderId == null || state == null) {
            throw new IllegalArgumentException("Missing input");
        }

        BoundStatement statement = update.bind(state, orderId)
            .setQueryTimestamp(timestampMicros);

        session.execute(statement);
    }
}
```

Ở đây CQL **không có `USING TIMESTAMP`**; timestamp được đặt **trên statement Java Driver**. Cách này giúp tập trung chính sách timestamp ở tầng code mà không phải lặp tham số `USING TIMESTAMP ?` trong mọi chuỗi CQL.

**Cần đối chiếu phiên bản:** tên phương thức, kiểu argument và tương tác với timestamp generator phải kiểm tra theo Java Driver đã resolve. Các phiên bản khác nhau có thể dùng cách builder/setter khác; ví dụ này minh họa hướng làm với Java Driver 4.x.

Java Driver statement theo kiểu immutable-style: phương thức `setQueryTimestamp(...)` trả về một statement đã thay đổi; phải giữ giá trị trả về. **Không gọi setter rồi bỏ qua kết quả**.

### Cách khác: bind trực tiếp CQL USING TIMESTAMP

```java
PreparedStatement updateWithTimestamp = session.prepare(
    "UPDATE orders_by_id USING TIMESTAMP ? " +
    "SET state = ? WHERE order_id = ?"
);

BoundStatement bound = updateWithTimestamp.bind(
    timestampMicros, state, orderId
);

session.execute(bound);
```

Hai cách có cùng ý đồ nhưng **không nên dùng đồng thời** trên cùng statement để tránh mơ hồ precedence. Khi một service gọi trực tiếp `CqlSession`, nên thống nhất một đường đặt timestamp và viết test `WRITETIME` xác minh microsecond thực sự được lưu.

Trong Spring Boot, nên inject một `CqlSession` được quản lý vòng đời, không tạo session mới trên mỗi request. Tránh tạo nhiều session có timestamp generator hoặc clock policy khác nhau mà không có lý do.

## 10. Spring Data: repository, CassandraOperations và WriteOptions

Spring Data Cassandra cung cấp nhiều mức API:

| API | Mục đích | Khả năng kiểm soát timestamp |
|---|---|---|
| `CassandraRepository` | CRUD và query methods | Thường dựa trên write options/defaults của infrastructure; cần xem API version cụ thể |
| `CassandraOperations` / `CassandraTemplate` | Mapping entity, insert/update/delete, query | Có các overload nhận write options như `InsertOptions` và `UpdateOptions` ở những dòng hỗ trợ |
| `CqlOperations` / `CqlTemplate` | CQL trực tiếp với bind parameters và row mapping | Có thể dùng `USING TIMESTAMP ?` như CQL thuần |
| `CqlSession` | Driver API, prepared/bound statements | Có thể đặt query timestamp trên statement hoặc CQL trực tiếp |
| Driver execution profile | Chính sách mặc định theo workload | Liên quan timestamp generator/config; không thay logic nghiệp vụ |

**Điểm quan trọng:** không phải vì `CassandraRepository.save(entity)` được gọi sau một request khác mà mutation của nó chắc chắn có write timestamp lớn hơn trên mọi client. Repository giúp xây mutation từ entity, còn quy tắc timestamp vẫn do Spring/driver/Cassandra áp dụng theo cấu hình thực tế.

Các class Spring Data thường gặp:

```java
import org.springframework.data.cassandra.core.CassandraOperations;
import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.data.cassandra.core.InsertOptions;
import org.springframework.data.cassandra.core.UpdateOptions;
```

Ở những bản Spring Data Cassandra hiện đại, `InsertOptions` và `UpdateOptions` dùng builder cho TTL, write timestamp, consistency và các thuộc tính ghi được hỗ trợ. **Cần kiểm tra Javadoc đúng bản đã resolve**: package, overload, tên builder method và các tùy chọn có thể khác giữa release. Không đưa một đoạn code chưa xác minh version vào production chỉ vì kiểu tên trông giống nhau.

### Một thao tác ghi entity thông thường

```java
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.CassandraOperations;

UUID orderId = UUID.randomUUID();

OrderById order = new OrderById(
    orderId,
    UUID.randomUUID(),
    "NEW",
    125000L,
    Instant.now()
);

operations.insert(order);
```

`operations` là bean `CassandraOperations` do Spring cấu hình; `OrderById` là entity mapping đầy đủ ở mục 11. Với lời gọi trên, nếu không đưa custom write options, timestamp được quyết định bởi **mặc định của stack**. `updatedAt = Instant.now()` chỉ là **giá trị cột nghiệp vụ**, không chủ động thiết lập write timestamp cho tất cả cột.

### Ý đồ cấu hình InsertOptions / UpdateOptions

Ở những phiên bản hỗ trợ các builder method tương ứng, cách dùng có dạng:

```java
// Mã minh họa: đối chiếu API InsertOptions/UpdateOptions
// của đúng phiên bản Spring Data Cassandra trước khi biên dịch.

long writeTimestampMicros = 1760000000001000L;

InsertOptions insertOptions = InsertOptions.builder()
    .timestamp(writeTimestampMicros)
    .build();

operations.insert(order, insertOptions);

// Khi muốn cập nhật toàn entity (xem cảnh báo về field null).
UpdateOptions updateOptions = UpdateOptions.builder()
    .timestamp(writeTimestampMicros + 100L)
    .build();

operations.update(order, updateOptions);
```

Đoạn trên minh họa **vị trí đặt write timestamp ở tầng Spring Data**, không phải bằng chứng chắc chắn overload hay builder giống hệt trong mọi phiên bản. Cần đọc Javadoc của dependency project và chạy integration test để xác minh `WRITETIME` sau insert/update.

**Không nên tùy tiện gọi `update(order, options)` để đổi một field duy nhất.** Mapper có thể tạo mutation cho nhiều property của entity; null/unset/TTL có semantics riêng. Khi sửa một trạng thái quan trọng, cập nhật cột cụ thể bằng `CqlSession` hoặc API update có chọn cột và điều kiện rõ ràng thường dễ kiểm soát hơn.

## 11. Entity mapping: updatedAt là field, không phải version của Cassandra

Ví dụ entity:

```java
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_id")
public class OrderById {
    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("customer_id")
    private UUID customerId;

    @Column("state")
    private String state;

    @Column("total_minor")
    private Long totalMinor;

    @Column("updated_at")
    private Instant updatedAt;

    public OrderById() {}

    public OrderById(UUID orderId, UUID customerId, String state,
                     Long totalMinor, Instant updatedAt) {
        this.orderId = orderId;
        this.customerId = customerId;
        this.state = state;
        this.totalMinor = totalMinor;
        this.updatedAt = updatedAt;
    }

    // Bổ sung getters/setters theo JavaBeans/mapping strategy dự án.
}
```

`@Column("updated_at")` chỉ nối Java `updatedAt` với cột CQL `timestamp`. Nó **không tự đổi timestamp metadata** của mutation và cũng không phải một trường versioning có khả năng ngăn lost update.

Nếu application muốn cập nhật cả `state` lẫn `updated_at` cùng một write timestamp:

```sql
UPDATE orders_by_id
USING TIMESTAMP ?
SET state = ?,
    updated_at = ?
WHERE order_id = ?;
```

Trong đó tham số thứ nhất là **microsecond write timestamp**, còn tham số thứ ba là giá trị **CQL timestamp** của `updated_at` (driver map từ `Instant`). Chỉ vì hai giá trị đều liên quan thời gian không có nghĩa phải đưa cùng một kiểu Java/số nguyên vào cả hai vị trí.

### Vì sao không dùng mỗi updatedAt để phân xử ghi?

Giả sử client A và B cùng đọc trạng thái `NEW`. Mỗi client tạo `updatedAt = Instant.now()`, rồi lần lượt gọi `repository.save`. Kết quả còn tùy mutation timestamps, clock skew, số cột được ghi và thời điểm request; **không có so sánh điều kiện bắt buộc rằng row còn ở trạng thái NEW**. `updatedAt` là dữ liệu, không tự bật compare-and-set.

Muốn giữ invariant chuyển trạng thái, hãy dùng một thao tác điều kiện có cơ chế kiểm tra ở Cassandra như `IF state = 'NEW'`, hoặc serialize writers/thiết kế domain phù hợp.

## 12. Khi nào nên chỉ định USING TIMESTAMP thủ công?

Một số tình huống có lý do chính đáng để kiểm soát write timestamp:

### 12.1. Backfill/migration có thứ tự nguồn dữ liệu

Ví dụ di chuyển một dataset lịch sử mà **timestamp nguồn được tin cậy và có thứ tự nhất quán**. Ứng dụng có thể muốn ghi các giá trị cũ với timestamp thấp hơn mutation hiện tại, để tránh dữ liệu lịch sử vô tình ghi đè dữ liệu mới.

```text
Current cell:
  state = 'PAID', writetime = 2000

Backfill từ nguồn cũ:
  state = 'NEW',  timestamp = 1000

Kết quả:
  'PAID' tiếp tục thắng theo timestamp.
```

Cách này **chỉ an toàn nếu timestamp hiện tại và timestamp lịch sử cùng một quy ước**, không có dữ liệu cũ mang future timestamp hoặc migration nhiều nguồn có clock skew. Một backfill cần xác minh schema, TTL, deletion và convergence trên môi trường đại diện.

### 12.2. Retry cùng mutation khi kết quả không chắc chắn

Khi một write timeout, không thể kết luận mutation chưa được replica nào nhận. Nếu retry phải **idempotent**, việc giữ nguyên ID và cùng timestamp/giá trị có thể giúp giảm rủi ro thay đổi thứ tự bản ghi giữa các lần retry. Tuy nhiên, đây không phải điều kiện đủ: kết quả của counter, LWT, TTL và side effect nghiệp vụ vẫn cần được xem riêng.

### 12.3. Phối hợp producer có clock/order được điều phối

Một số hệ thống event-driven có thể gắn timestamp theo một nguồn duy nhất hoặc một logical version được chuyển đổi có kiểm soát. Chỉ nên làm vậy nếu đã có định nghĩa rõ về thứ tự, độ phân giải, giới hạn số và cách xử lý sự kiện đến muộn. **Không dùng timestamp vật lý để giả vờ có một thứ tự nghiệp vụ toàn cục giữa nhiều writer độc lập.**

### Khi không nên làm

- Chỉ vì muốn “update mới hơn” mà tự tăng một số ngẫu nhiên.
- Muốn ép một mutation cũ thắng bằng timestamp xa trong tương lai.
- Muốn bỏ qua thiết kế LWT hoặc kiểm soát xung đột nghiệp vụ.
- Muốn thay `updated_at` hoặc TTL bằng write timestamp.
- Muốn sửa truy vấn thiếu partition key hoặc chậm bằng cách đổi timestamp.

## 13. Delete, tombstone và timestamp: rủi ro dữ liệu “sống lại”

Xóa trong Cassandra thường được biểu diễn bằng **tombstone**, không phải lúc nào cũng là loại bỏ vật lý ngay lập tức. Tombstone có metadata timestamp dùng để ngăn những giá trị cũ xuất hiện lại khi replica hội tụ.

Ví dụ:

```sql
-- Ghi dữ liệu.
UPDATE orders_by_id
USING TIMESTAMP 1760000000000100
SET state = 'PAID'
WHERE order_id = 11111111-1111-1111-1111-111111111111;

-- Xóa cell ở timestamp cao hơn.
DELETE state
FROM orders_by_id
USING TIMESTAMP 1760000000000200
WHERE order_id = 11111111-1111-1111-1111-111111111111;
```

Nếu sau đó một backfill ghi `state = 'NEW'` với timestamp `1760000000000150` (nhỏ hơn timestamp của tombstone), giá trị cũ **không nên thắng dấu xóa** khi chúng được hòa giải theo đúng semantics. Một mutation mới muốn tạo lại `state` phải có timestamp phù hợp và cần được cho phép về nghiệp vụ.

**Rủi ro zombie data:** nếu tombstone bị thu hồi trong khi một replica chưa nhận xóa và repair chưa được thực hiện đúng giới hạn thời gian, giá trị cũ ở replica đó có thể tái xuất hiện. Vì thế `gc_grace_seconds`, TTL, repair, backup và thời gian mất kết nối replica phải được thiết kế cùng nhau.

Không đặt timestamp tương lai quá lớn lên DELETE chỉ để “xóa chắc chắn”. Một tombstone với timestamp nằm xa trong tương lai có thể che phủ những lần tạo lại dữ liệu hợp lệ về sau.

## 14. TTL + timestamp: hai đồng hồ và những hiểu nhầm

TTL và write timestamp thường đi cùng mutation nhưng có mục đích khác nhau:

| Thành phần | Đơn vị | Dùng để |
|---|---|---|
| `USING TIMESTAMP` | Microsecond từ epoch | Hòa giải xung đột ghi |
| `USING TTL` | Giây | Xác định thời hạn sống của cell theo semantics Cassandra |
| Cột `expires_at timestamp` | Thời điểm ứng dụng ghi | Hiển thị/ra quyết định nghiệp vụ, không tự xóa cột |
| `WRITETIME(column)` | Microsecond | Quan sát timestamp ghi của cell |
| `TTL(column)` | Giây còn lại | Quan sát TTL còn lại của cell khi áp dụng |

Ví dụ:

```sql
UPDATE orders_by_id
USING TTL 120 AND TIMESTAMP 1760000000000100
SET state = 'PENDING'
WHERE order_id = 33333333-3333-3333-3333-333333333333;

SELECT state,
       WRITETIME(state) AS state_write_us,
       TTL(state) AS state_ttl_seconds
FROM orders_by_id
WHERE order_id = 33333333-3333-3333-3333-333333333333;
```

`TTL(state)` thay đổi theo thời gian, còn `WRITETIME(state)` phản ánh timestamp của mutation tạo ra cell đang được đọc. Khi TTL hết hạn, cell có thể trở thành dữ liệu hết hạn/tombstone theo cơ chế Cassandra; nó không đơn giản “hoàn tác về giá trị trước đó” như stack lịch sử.

**Dùng giá trị timestamp quá cũ khi kết hợp TTL** cần được test kỹ: timestamp được dùng để phân xử khi đụng một phiên bản khác, TTL quyết định hết hạn theo semantics lưu trữ. Không nên suy rằng một timestamp cũ tự kéo thời điểm hết hạn về quá khứ hoặc ngược lại mà không kiểm tra phiên bản Cassandra thực tế.

## 15. CQL counter và một số ngoại lệ

Counters của Cassandra có ngữ nghĩa khác cột thường:

```sql
CREATE TABLE page_view_counters (
    page_id uuid PRIMARY KEY,
    views counter
);
```

Counter được cập nhật bằng phép cộng/trừ thay vì đặt một giá trị đơn giản:

```sql
UPDATE page_view_counters
SET views = views + 1
WHERE page_id = 11111111-1111-1111-1111-111111111111;
```

**Không coi counter update là mutation thường có thể gắn `USING TIMESTAMP` và retry idempotent như ghi `state = 'PAID'`.** Cassandra không cho phép một số tùy chọn timestamp/TTL trên counter và xử lý conflict theo semantics riêng. Retry increment sau timeout có thể tăng đếm **hai lần**; phải thiết kế chính sách at-least-once, deduplication hoặc công cụ đếm thích hợp.

Tương tự, một số thao tác conditional (`IF`) có hạn chế về timestamp do pha đồng thuận được quản lý theo cơ chế khác. Hãy kiểm tra CQL statement type và API trước khi áp dụng write options chung lên mọi bảng.

## 16. Consistency level không quyết định mutation nào thắng

Giả sử RF=3 trong một datacenter:

| CL | Ngưỡng replica đáp ứng (RF=3) | Nó quyết định xung đột timestamp không? |
|---|---:|---|
| `ONE` / `LOCAL_ONE` | 1 | **Không** |
| `QUORUM` / `LOCAL_QUORUM` | 2 | **Không** |
| `ALL` | 3 | **Không** |

Ví dụ:

```text
Write A: state='PAID', writetime=2000, CL=ONE
Write B: state='CANCELLED', writetime=1900, CL=ALL

Khi các giá trị được hòa giải theo cùng cell:
  A có timestamp lớn hơn B, nên A có thể thắng.
```

CL cao hơn không tự tạo write timestamp cao hơn; nó yêu cầu nhiều ACK hơn. Ngược lại, ghi có timestamp cao hơn nhưng dùng CL thấp có thể chưa được mọi replica biết ngay lập tức.

**Read QUORUM + Write QUORUM** ở cùng tập RF là cơ sở cho quorum intersection, nhưng không xóa rủi ro timestamp clock skew, concurrent updates hoặc logic nghiệp vụ. Một client có thể quan sát trạng thái ngoài ý muốn dù cả hai mutation dùng `LOCAL_QUORUM` nếu timestamp cao hơn thuộc về thao tác cũ nhưng từ một đồng hồ nhanh.

Với hai datacenter, `LOCAL_QUORUM` ở `dc1` không tự cam kết dữ liệu đã hội tụ ở `dc2`. Việc điều phối qua nhiều DC và source timestamp phải được thiết kế riêng.

## 17. LWT: khi cần chuyển trạng thái có điều kiện

Một đơn hàng thường có invariant: chỉ chuyển `NEW` sang `PAID` nếu trạng thái vẫn là `NEW`. Chỉ dùng timestamp cao hơn không đủ, vì hai client vẫn có thể đưa ra quyết định từ cùng một bản đọc cũ.

CQL hỗ trợ **lightweight transaction (LWT)**:

```sql
UPDATE orders_by_id
SET state = 'PAID'
WHERE order_id = 11111111-1111-1111-1111-111111111111
IF state = 'NEW';
```

Nếu điều kiện không đúng, mutation không được áp dụng theo cơ chế conditional update; client cần đọc và xử lý kết quả `[applied]` hoặc API tương đương. LWT có chi phí đồng thuận và latency cao hơn ghi thông thường.

**Lưu ý đặc biệt:** không trộn `USING TIMESTAMP` tùy ý với LWT/conditional mutation; những statement này có ràng buộc CQL riêng và timestamp được quản lý theo cơ chế đồng thuận. Nếu cần audit sự kiện nghiệp vụ, lưu version/event riêng thay vì ép một timestamp vật lý vào một phép điều kiện rồi suy rằng nó vẫn tuyến tính hóa đúng.

Trong Java Driver, khi dùng LWT còn có **serial consistency** `SERIAL` hoặc `LOCAL_SERIAL` phù hợp topology, bên cạnh regular consistency của request. Serial CL không phải là một cách đặt write timestamp.

### Kết quả condition là một phần của API nghiệp vụ

Một method repository chỉ gọi `save(order)` hoặc `update(order)` **không tự tạo điều kiện `IF state='NEW'`**. Nếu nghiệp vụ yêu cầu không ghi đè khi trạng thái đã chuyển, hãy dùng một lệnh điều kiện và kiểm tra kết quả, hoặc một mô hình persistence phù hợp đã kiểm chứng.

## 18. Ghi có timestamp tường minh qua CqlOperations/CqlTemplate

Nếu Spring Data entity-level API không cung cấp overload bạn cần, có thể dùng **CQL tường minh** qua `CqlOperations`/`CqlTemplate` hoặc `CqlSession`. Ý đồ query:

```sql
UPDATE orders_by_id
USING TIMESTAMP ?
SET state = ?,
    updated_at = ?
WHERE order_id = ?;
```

Một đoạn DAO kiểu Spring Data CQL với bind params:

```java
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.cassandra.core.cql.CqlOperations;

public final class OrderCqlWriter {
    private final CqlOperations cql;

    public OrderCqlWriter(CqlOperations cql) {
        this.cql = cql;
    }

    public void updateState(
            UUID orderId, String state,
            Instant updatedAt, long timestampMicros) {

        if (orderId == null || state == null || updatedAt == null) {
            throw new IllegalArgumentException("Missing write value");
        }

        cql.execute(
            "UPDATE orders_by_id USING TIMESTAMP ? " +
            "SET state = ?, updated_at = ? WHERE order_id = ?",
            timestampMicros, state, updatedAt, orderId
        );
    }
}
```

Ở các dòng Spring Data Cassandra hỗ trợ overload `execute(String, Object... args)`, CqlTemplate có thể prepare/bind các giá trị. **Cần đối chiếu chữ ký API thực tế** và cấu hình keyspace/session khi triển khai.

Ưu điểm của CQL tường minh là **giới hạn những cột bị tác động**, dễ kiểm tra `USING TIMESTAMP`, TTL và điều kiện trong CQL. Nhược điểm: cần tự quản lý DTO/schema, codec, lỗi query và dữ liệu null so với API mapped entity.

**Không ghép trực tiếp giá trị timestamp, UUID hay string từ request vào câu CQL** khi đã có bind marker hỗ trợ. Nếu cho phép lựa chọn bảng/cột, dùng allowlist query constants; bind marker chỉ dành cho **giá trị**, không thay identifier.

## 19. Idempotency, timeout và ghi đồng thời

Trong Cassandra, timeout có thể xảy ra **sau khi một số replica đã nhận mutation**. Điều này tạo bài toán “không biết request đã thành công hay chưa”:

```text
Client gửi UPDATE state='PAID' tại timestamp=2000
  → Replica R1 nhận
  → Replica R2 đang chậm
  → Client timeout

Client retry:
  A. Cùng ID, cùng giá trị, cùng timestamp
  B. Cùng ID, giá trị khác hoặc timestamp khác
  C. Tạo ID mới
```

- **A** thường dễ lập luận idempotent hơn với mutation gán giá trị đơn giản, dù còn phải kiểm tra TTL, LWT, side effects và multi-table projection.
- **B** có thể làm thay đổi thứ tự cạnh tranh hoặc xóa/ghi đè logic của mutation khác.
- **C** có nguy cơ tạo bản ghi nghiệp vụ trùng nếu request đầu đã được áp dụng.

**Không suy ra “cứ cùng timestamp là retry luôn an toàn”.** Với một row chứa nhiều cell, khác biệt null/unset hoặc TTL vẫn có thể tạo side effect. Với counters, retry increment không idempotent như set một giá trị. Với LWT, phải xem kết quả áp dụng và bảo đảm điều kiện nghiệp vụ.

Một hệ thống có nhiều writer nên có:

1. ID ổn định cho một yêu cầu nghiệp vụ.
2. Quy tắc nguồn timestamp được document và kiểm tra clock skew.
3. Khả năng idempotency/deduplication khi retry.
4. State machine hoặc LWT nếu trạng thái loại trừ nhau.
5. Audit log/event log cho lịch sử thay đổi nếu cần chứng minh thứ tự nghiệp vụ.
6. Giám sát timeout/retry và metric sai lệch đồng hồ/ghi dữ liệu.

## 20. Cách điều tra lỗi “ghi mới nhưng đọc thấy dữ liệu cũ”

Một quy trình điều tra theo tầng:

| Dấu hiệu | Điều cần xác minh | Tầng vấn đề |
|---|---|---|
| `updated_at` lớn nhưng `state` cũ | `WRITETIME(state)` và `WRITETIME(updated_at)` có khác nhau không? | Cell-level timestamps |
| Một client ghi nhưng client khác đọc chưa thấy | RF/CL, replica lag, DC locality | Consistency/replication |
| Retry vẫn không đổi state | Mutation mới có timestamp **thấp hơn** cell cũ/tombstone? | Last-write-wins |
| State bị đảo ngược sau backfill | Backfill có timestamp quá cao/không cùng quy ước? | Migration |
| Cột tự biến mất sau vài phút | TTL của cell có hết hạn? | TTL/tombstone |
| Cột biến mất rồi xuất hiện lại | Repair, tombstone/grace, replica cũ | Distributed deletion |
| Counter tăng hơn số request thành công | Retry increment sau timeout | Non-idempotent operation |
| Đọc chậm dù LIMIT nhỏ | Tombstone, wide partition, compaction | Query/data model |
| Dữ liệu sai tenant/table | CQL/partition key/keyspace sai | Access pattern / authorization |
| Dùng QUORUM vẫn thấy cập nhật không đúng thứ tự | Clock skew, concurrent writes, manual timestamps | Conflict policy |

Các bước thực hiện trong **môi trường an toàn**:

```sql
SELECT state,
       WRITETIME(state) AS state_written_us,
       updated_at,
       WRITETIME(updated_at) AS updated_written_us
FROM orders_by_id
WHERE order_id = ?;
```

Sau đó đối chiếu với application logs (ID request, timestamp nguồn), driver statement options, schema/keyspace, trạng thái node, CL và thông tin replica. Nếu CQL trả đúng writetime nhưng Java entity sai, mới tập trung vào `@Column`, converter, null handling và row mapping.

Đừng bật tracing hoặc log toàn bộ dữ liệu khách hàng trên mọi request production chỉ để điều tra. Ghi nhận context tối thiểu, ẩn dữ liệu nhạy cảm và dùng tracing có chọn lọc.

## 21. Lab: kiểm chứng write timestamp thắng bất kể thứ tự request

Lab này chỉ thực hiện trên **keyspace test riêng**, tuyệt đối không chạy các lệnh DELETE, backfill hoặc timestamp cao trên bảng production.

### 21.1. Tạo keyspace và bảng

```sql
CREATE KEYSPACE IF NOT EXISTS timestamp_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 1
};

CREATE TABLE IF NOT EXISTS timestamp_lab.orders_by_id (
    order_id uuid PRIMARY KEY,
    state text,
    total_minor bigint,
    updated_at timestamp
);
```

RF=1 đủ để minh họa **thứ tự timestamp trên một cell**, nhưng **không** chứng minh tính nhất quán đa replica hoặc failover. Với thử nghiệm nhất quán phân tán, cần lab có nhiều node và RF phù hợp.

### 21.2. Thực hiện hai ghi ngược thứ tự timestamp

```sql
-- Ghi A: timestamp lớn hơn.
UPDATE timestamp_lab.orders_by_id
USING TIMESTAMP 1760000000000200
SET state = 'PAID'
WHERE order_id = 11111111-1111-1111-1111-111111111111;

-- Ghi B: chạy SAU A nhưng timestamp THẤP hơn.
UPDATE timestamp_lab.orders_by_id
USING TIMESTAMP 1760000000000100
SET state = 'CANCELLED'
WHERE order_id = 11111111-1111-1111-1111-111111111111;

SELECT state, WRITETIME(state)
FROM timestamp_lab.orders_by_id
WHERE order_id = 11111111-1111-1111-1111-111111111111;
```

**Kỳ vọng:** `state` vẫn là `PAID`; `WRITETIME(state)` phản ánh timestamp cao hơn `1760000000000200`. Đây là điểm quan trọng: **thứ tự thực thi B sau A không quyết định giá trị thắng**.

### 21.3. Ghi một cột khác và kiểm tra hai writetime

```sql
UPDATE timestamp_lab.orders_by_id
USING TIMESTAMP 1760000000000300
SET total_minor = 125000
WHERE order_id = 11111111-1111-1111-1111-111111111111;

SELECT state, WRITETIME(state),
       total_minor, WRITETIME(total_minor)
FROM timestamp_lab.orders_by_id
WHERE order_id = 11111111-1111-1111-1111-111111111111;
```

Kỳ vọng `state` và `total_minor` có **hai write timestamps khác nhau**, vì chúng được ghi bởi các mutation khác nhau.

### 21.4. Thử tombstone thắng mutation cũ

```sql
DELETE state
FROM timestamp_lab.orders_by_id
USING TIMESTAMP 1760000000000400
WHERE order_id = 11111111-1111-1111-1111-111111111111;

UPDATE timestamp_lab.orders_by_id
USING TIMESTAMP 1760000000000350
SET state = 'NEW'
WHERE order_id = 11111111-1111-1111-1111-111111111111;

SELECT state, WRITETIME(state)
FROM timestamp_lab.orders_by_id
WHERE order_id = 11111111-1111-1111-1111-111111111111;
```

**Kỳ vọng:** `state` không trở lại `NEW`, vì mutation cũ hơn tombstone không thắng xóa. Thử nghiệm này không thay thế việc test repair và `gc_grace_seconds` trên cluster dài hạn.

### 21.5. Thử qua Java Driver / Spring Data

1. Tạo một `PreparedStatement` với `USING TIMESTAMP ?` và bind microsecond đúng kiểu.
2. Gọi mutation cho cùng ID với hai timestamp tăng/giảm có chủ đích.
3. Dùng `WRITETIME(state)` đọc raw metadata.
4. Tạo entity Spring Data có `updated_at` và chứng minh giá trị `Instant` của cột không tự quyết định writetime.
5. Nếu Spring Data version hỗ trợ `InsertOptions`/`UpdateOptions` timestamp, thực hiện thử nghiệm riêng rồi đối chiếu microsecond lưu thực.
6. Xác minh không vô tình có cả `USING TIMESTAMP` trong CQL và `setQueryTimestamp` ở statement cùng lúc.
7. Với RF=3, thử đọc/ghi ở `ONE` và `QUORUM` để phân biệt độ mới giữa replica với thứ tự timestamp.

**Không nên so benchmark latency từ một lab RF=1 với production multi-DC**, vì network, replica, compaction và consistency làm thay đổi đáng kể chi phí.

## 22. Các lỗi phổ biến khi áp dụng timestamp và write options

| Hiểu nhầm/lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Đưa `toEpochMilli()` vào `USING TIMESTAMP` | Timestamp bị lùi khoảng 1.000 lần về quá khứ | Chuyển thành microsecond |
| Dùng timestamp tương lai cực lớn | Che khuất các mutation hợp lệ sau đó | Kiểm soát clock, giới hạn/validate nguồn timestamp |
| Coi `updated_at` là writetime | Kết luận sai mutation nào thắng | Dùng `WRITETIME(column)` |
| Giả định request đến sau phải thắng | Sai last-write-wins metadata | Kiểm tra timestamp, concurrency và LWT |
| Hai producer dùng clock khác nhau | Ghi cũ có thể thắng ghi mới | Đồng bộ clock hoặc single-writer/conditional update |
| Cố dùng timestamp để tạo uniqueness | Không ngăn race trên primary key | Thiết kế primary key/LWT khi cần |
| Retry `counter + 1` sau timeout | Có thể tăng hai lần | Không coi counter idempotent |
| LWT và `USING TIMESTAMP` tùy ý | Có thể bị CQL từ chối hoặc sai semantics | Theo đúng LWT API và serial CL |
| Ghi toàn entity để sửa một cell | Có thể overwrite fields khác và timestamp | Update có chọn cột |
| `NULL` vs `UNSET` không được phân biệt | Tombstone hoặc bỏ qua cột ngoài dự kiến | Kiểm tra mapper/driver write semantics |
| TTL được hiểu là write timestamp | Dữ liệu hết hạn ngoài ý muốn | Tách expiration với conflict resolution |
| Xóa dữ liệu với timestamp tương lai | Sau đó khó tạo lại cell | Tránh timestamp tùy ý, kiểm soát tombstone |
| Chỉ nâng CL để sửa conflict | Không sửa clock skew, LWW, concurrent writers | Thiết kế quy tắc nghiệp vụ |
| Mặc định Spring giống nhau ở mọi version | API/behavior khác khi upgrade | Khóa dependency và test writetime |
| Không kiểm tra keyspace/partition key | Đọc dữ liệu sai, đánh giá lỗi nhầm | Xác minh CQL và bảng theo truy vấn |

## 23. Checklist đưa write timestamp vào production

1. **Đã có lý do nghiệp vụ?** Nếu không, ưu tiên default timestamp được driver/cluster cấu hình nhất quán.
2. **Phân biệt đơn vị?** Write timestamp là microsecond; cột CQL `timestamp` lưu giá trị thời gian nghiệp vụ.
3. **Có một nguồn timestamp chuẩn?** Không dùng nhiều generator không điều phối trên cùng key mà không hiểu thứ tự.
4. **Đã kiểm tra clock skew?** Có NTP/monitoring và giới hạn chấp nhận timestamp tương lai bất thường?
5. **Update tác động cột nào?** Tránh vô tình ghi toàn entity và thay writetime những field không mong muốn.
6. **Null/unset semantics rõ?** Kiểm thử tombstone và hành vi converter trên các phiên bản.
7. **TTL có dùng không?** Test tương tác với timestamp, expiration, repair và dữ liệu cũ.
8. **Delete có thể thắng backfill?** Kiểm tra tombstone và chính sách làm sạch/repair.
9. **Retry có idempotent?** Giữ primary key/giá trị/timestamp khi thích hợp; không retry counter/LWT tùy tiện.
10. **Có race nghiệp vụ?** Dùng LWT/conditional update hoặc một cơ chế quản lý trạng thái riêng khi cần.
11. **CQL và Java Driver nhất quán?** Tránh đồng thời `USING TIMESTAMP` với query timestamp option.
12. **Spring Data version chính xác?** Kiểm tra `InsertOptions`, `UpdateOptions` và overload thực tế.
13. **Consistency/RF phù hợp?** CL chọn ngưỡng replica, không chọn winner của timestamp conflict.
14. **Partition key đúng access pattern?** Không dùng timestamp để sửa một truy vấn thiếu khóa phân vùng.
15. **Có đo đạc?** Theo dõi latency, tombstones, retries, clock skew và write conflicts.
16. **Có integration test?** Kiểm tra `WRITETIME` sau mutation, không chỉ so Java entity.
17. **Dữ liệu nhạy cảm được bảo vệ?** Debug/tracing không log đầy đủ payload hoặc secrets.
18. **Rollback/migration có kế hoạch?** Không đưa timestamp tương lai lên dữ liệu production chỉ để ép ghi đè.

**Kết luận:** `USING TIMESTAMP` là công cụ CQL mạnh để chỉ định **write timestamp của mutation**, giúp kiểm soát thứ tự hòa giải cell khi có xung đột, đặc biệt trong backfill và một số quy trình idempotency. Spring Data Cassandra cung cấp các API ghi qua **repository, CassandraTemplate/CassandraOperations** và tùy chọn write phù hợp phiên bản; Java Driver còn cho phép đặt timestamp ở cấp statement. Tuy nhiên, **write timestamp không phải cột `updated_at`, không thay đổi partition key, không nâng consistency level và không bảo đảm đúng thứ tự nghiệp vụ của concurrent writers**. Hãy ưu tiên quy tắc ghi rõ ràng, kiểm chứng bằng `WRITETIME`, và sử dụng LWT/điều phối domain khi tính đúng đắn đòi hỏi điều kiện chuyển trạng thái.

## Tài liệu tham khảo

- [Apache Cassandra — CQL DML](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `INSERT`, `UPDATE`, `DELETE`, `USING TIMESTAMP`, TTL và conditional statements.
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/): partition key, clustering columns, denormalization và đường truy vấn.
- [Apache Cassandra Java Driver — Request Options](https://apache.github.io/cassandra-java-driver/4.18.1/core/statements/): statement-level options, timestamp, consistency và paging.
- [Apache Cassandra Java Driver — Timestamp Generator](https://apache.github.io/cassandra-java-driver/4.18.1/core/query_timestamps/): client-side timestamps, generator và hạn chế đồng hồ.
- [Spring Data Cassandra — Template API](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): `CassandraTemplate`, insert/update và options.
- [Spring Data Cassandra — WriteOptions API](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/WriteOptions.html): các tùy chọn ghi được hỗ trợ trong phiên bản hiện hành.
- [Spring Data Cassandra — CQL Template](https://docs.spring.io/spring-data/cassandra/reference/cassandra/cql-template.html): `CqlTemplate`/`CqlOperations` và bind CQL.
