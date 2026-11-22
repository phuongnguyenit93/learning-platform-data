# Static column và dữ liệu dùng chung trong một phân vùng

Trong Apache Cassandra, một **phân vùng** (*partition*) có thể chứa nhiều hàng, được phân biệt bởi **clustering columns**. Khi nhiều hàng thuộc cùng phân vùng cần dùng chung một thông tin, Cassandra cho phép khai báo **static column** bằng từ khóa CQL `STATIC`. Giá trị của cột này tồn tại ở **mức phân vùng**, thay vì được lưu riêng cho từng hàng có clustering key khác nhau.

Khái niệm này đặc biệt hữu ích trong mô hình wide-column phân tán: partition key xác định nhóm hàng và tập replica phụ trách; clustering columns phân biệt/sắp xếp hàng trong nhóm; còn static columns mô tả thông tin áp dụng cho **cả nhóm**. Tuy nhiên, “dùng chung” chỉ có ý nghĩa **bên trong một phân vùng logic của một bảng**; nó không biến Cassandra thành hệ quản trị quan hệ với phép JOIN hoặc dữ liệu dùng chung giữa mọi phân vùng.

Sau bài học, bạn có thể:

- Nhận diện cột `STATIC` và phân biệt nó với partition key, clustering column và cột thường.
- Tạo bảng có static columns; ghi metadata phân vùng kể cả khi chưa có hàng sự kiện.
- Đọc, cập nhật và xóa static columns đúng phạm vi bằng CQL.
- Hiểu vì sao static data có thể lặp lại trong kết quả `SELECT` nhưng chỉ thuộc một phân vùng.
- Đánh giá lợi ích, giới hạn, TTL, replication và các lỗi mô hình hóa khi dùng static data.
- Sử dụng Java Driver để đọc/ghi metadata ở mức phân vùng.

## 1. Static column là gì?

Giả sử ứng dụng lưu các sự kiện trong một phiên truy cập. Mỗi phiên có **nhiều sự kiện**, nhưng `user_id`, thời gian mở phiên và nguồn truy cập là **thông tin chung cho toàn phiên**.

Nếu đặt những thuộc tính này thành các cột thường, mỗi hàng sự kiện phải mang một bản giá trị riêng. Với `STATIC`, ta khai báo metadata **một lần theo partition key** và các hàng sự kiện trong phân vùng cùng nhìn thấy giá trị đó.

| Loại cột | Khóa/ví dụ | Tác dụng |
| --- | --- | --- |
| Partition key | `(tenant_id, session_id)` | Chọn phân vùng và xác định vị trí phân phối dữ liệu. |
| Clustering columns | `event_time`, `event_id` | Phân biệt các sự kiện, quyết định thứ tự trong phiên. |
| Static columns | `user_id STATIC`, `started_at STATIC`, `source_app STATIC` | Lưu metadata chung của phân vùng/phiên. |
| Regular columns | `event_type`, `payload` | Lưu giá trị riêng của từng hàng sự kiện. |

Một cách hình dung:

```text
Partition key = ('acme', session-01)
│
├── Static data của phân vùng:
│     user_id    = user-77
│     started_at = 2026-11-21 08:00:00 UTC
│     source_app = web
│
├── Hàng (08:00:05, event-A) -> page_view, /home
├── Hàng (08:00:10, event-B) -> button_click, buy
└── Hàng (08:00:15, event-C) -> page_view, /checkout
```

Các hàng trong cùng phân vùng sử dụng **cùng giá trị static hiện hành**. Thay đổi `source_app` ở mức phân vùng sẽ được phản ánh khi đọc những hàng ấy, theo thời điểm ghi và mức nhất quán đọc/ghi đang dùng.

> **Điểm phân biệt:** static column không phải một phần của primary key. Nó **không** thay đổi token, không định danh hàng và không ảnh hưởng đến thứ tự clustering.

## 2. Khai báo static column trong CQL

Thiết kế bảng phục vụ hai truy vấn chủ lực:

1. Đọc danh sách sự kiện mới nhất của một phiên.
2. Đọc metadata áp dụng cho toàn phiên mà không cần truy cập từng sự kiện.

```sql
CREATE TABLE session_events_by_id (
    tenant_id  text,
    session_id uuid,
    event_time timestamp,
    event_id   timeuuid,
    user_id    uuid STATIC,
    started_at timestamp STATIC,
    source_app text STATIC,
    event_type text,
    payload    text,
    PRIMARY KEY (
        (tenant_id, session_id),
        event_time,
        event_id
    )
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

Đọc schema này như sau:

- **Partition key ghép:** `(tenant_id, session_id)`. Mỗi cặp tenant–phiên là một phân vùng logic.
- **Clustering columns:** `event_time` và `event_id`. Chúng phân biệt/sắp thứ tự các sự kiện trong phiên.
- **Static columns:** `user_id`, `started_at` và `source_app`. Ba giá trị này được chia sẻ trong cùng phân vùng.
- **Regular columns:** `event_type` và `payload`, thay đổi theo từng sự kiện.

### Quy tắc khai báo

Static columns chỉ được hỗ trợ trong bảng có **ít nhất một clustering column**. Chúng không được là thành phần của primary key.

Ví dụ không hợp lệ:

```sql
-- Không có clustering column: không thể khai báo STATIC.
CREATE TABLE invalid_session_metadata (
    session_id uuid PRIMARY KEY,
    source_app text STATIC
);
```

Với trường hợp chỉ có đúng một hàng cho mỗi partition key và không có clustering columns, hãy dùng **cột thường**, không cần `STATIC`.

Mặt khác, khóa phân vùng **không bắt buộc phải là khóa ghép** để dùng static columns. Bảng có khóa `PRIMARY KEY (session_id, event_time)` vẫn có thể chứa `source_app text STATIC`, vì `event_time` là clustering column.

## 3. Ghi metadata tĩnh và ghi sự kiện

### Ghi metadata khi phiên bắt đầu

Static columns có thể được ghi bằng cách cung cấp **đầy đủ partition key**, ngay cả khi không cung cấp clustering columns:

```sql
INSERT INTO session_events_by_id (
    tenant_id, session_id, user_id, started_at, source_app
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    8817a208-1858-4144-86e9-b24d9083e478,
    '2026-11-21T08:00:00Z',
    'web'
);
```

Lệnh trên tạo/cập nhật **dữ liệu static của phân vùng**. Nó không tạo một hàng sự kiện bình thường có đủ `event_time` và `event_id`. Đây là khác biệt so với thao tác ghi cột thường: cột thường gắn với một hàng cụ thể, nên muốn ghi phải xác định đủ clustering key của hàng.

### Ghi các sự kiện vào cùng phiên

```sql
INSERT INTO session_events_by_id (
    tenant_id, session_id, event_time, event_id, event_type, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21T08:00:05Z',
    now(),
    'page_view',
    '/home'
);

INSERT INTO session_events_by_id (
    tenant_id, session_id, event_time, event_id, event_type, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21T08:00:10Z',
    now(),
    'button_click',
    'buy'
);
```

Cả hai hàng sự kiện có cùng partition key `('acme', 327a71e9-...)`, nên đều nhìn thấy cùng `user_id`, `started_at` và `source_app` trong phân vùng.

**Chú ý về `now()`:** hàm này sinh một `timeuuid` mới mỗi lần gọi. Nếu nghiệp vụ cần thao tác ghi idempotent khi retry, hãy dùng định danh sự kiện ổn định do ứng dụng tạo và tái sử dụng, để tránh tạo nhiều hàng cho cùng một sự kiện.

### Ghi metadata sau khi đã có sự kiện

Không bắt buộc phải ghi static data trước. Nếu các hàng sự kiện đã tồn tại, một lệnh `UPDATE` static column theo partition key vẫn áp dụng giá trị mới cho toàn phân vùng.

```sql
UPDATE session_events_by_id
SET source_app = 'web-v2'
WHERE tenant_id = 'acme'
  AND session_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

Không cần truyền `event_time` hay `event_id`, vì `source_app` thuộc phân vùng, không thuộc từng hàng sự kiện.

## 4. Static data xuất hiện thế nào khi `SELECT`?

### Đọc các hàng sự kiện kèm metadata

```sql
SELECT event_time, event_id, event_type, payload,
       user_id, started_at, source_app
FROM session_events_by_id
WHERE tenant_id = 'acme'
  AND session_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
LIMIT 20;
```

Nếu phân vùng chứa hai hàng sự kiện, **kết quả** có thể trông như sau (rút gọn `event_id` cho dễ đọc):

| `event_time` | `event_id` | `event_type` | `source_app` | `user_id` |
| --- | --- | --- | --- | --- |
| 08:00:10 | B | button_click | web-v2 | user-77 |
| 08:00:05 | A | page_view | web-v2 | user-77 |

`source_app` và `user_id` **được hiển thị lặp lại trên từng hàng kết quả**. Điều đó không có nghĩa Cassandra đã lưu một bản sao riêng của hai cột này cho từng sự kiện. Chúng là các giá trị chung của phân vùng, được ghép vào từng hàng kết quả khi đọc.

### Đọc một lần metadata của phân vùng

Nếu chỉ cần metadata, dùng `SELECT DISTINCT` trên **partition key cùng các static columns**:

```sql
SELECT DISTINCT tenant_id, session_id, user_id, started_at, source_app
FROM session_events_by_id
WHERE tenant_id = 'acme'
  AND session_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

Cách này biểu diễn đúng ý định “một dòng dữ liệu chung cho phân vùng”. Với `SELECT DISTINCT` của Cassandra, không được tự ý thêm clustering columns hoặc regular columns vào danh sách chọn.

Chỉ `SELECT source_app FROM ... WHERE ...` **không phải cam kết luôn trả đúng một hàng**, bởi static data có thể được chiếu ra trên từng hàng clustering. Nếu không dùng `DISTINCT` nhưng chỉ cần một hàng bất kỳ mang metadata, có thể dùng `LIMIT 1` theo truy vấn phù hợp.

### Phân vùng chỉ có static data

Một trường hợp quan trọng: lệnh `INSERT` chỉ ghi static columns đã tạo metadata của phiên, nhưng chưa có sự kiện nào.

Khi chọn dữ liệu ở phân vùng này, Cassandra vẫn có thể trả về **một hàng biểu diễn static data**; các cột clustering và cột thường của hàng đó có giá trị `null`. Khi các hàng sự kiện được ghi, static columns sẽ xuất hiện cùng các hàng ấy trong kết quả đọc.

Ví dụ về kết quả trước sự kiện đầu tiên:

| `tenant_id` | `session_id` | `event_time` | `event_id` | `source_app` |
| --- | --- | --- | --- | --- |
| acme | session-01 | `null` | `null` | web |

Bảng minh họa chỉ biểu diễn ý nghĩa dữ liệu; chuỗi `session-01` là ký hiệu rút gọn, không phải literal kiểu `uuid` trong CQL.

Ngược lại, nếu phân vùng có các hàng sự kiện nhưng static columns chưa được ghi, các giá trị static đọc ra có thể là `null`.

## 5. Cập nhật và xóa: phạm vi partition so với phạm vi hàng

Static và regular columns có phạm vi cập nhật khác nhau:

| Thao tác | Điều kiện khóa bắt buộc trong trường hợp thông thường | Ảnh hưởng |
| --- | --- | --- |
| `UPDATE` static column | Toàn bộ partition key | Giá trị dùng chung của phân vùng. |
| `UPDATE` regular column | Toàn bộ partition key **và** clustering key của hàng | Một hàng xác định. |
| `DELETE static_column` | Toàn bộ partition key | Xóa giá trị static của phân vùng. |
| `DELETE` một hàng clustering | Toàn bộ primary key của hàng | Xóa hàng sự kiện đó; static data vẫn còn. |
| `DELETE` cả phân vùng | Toàn bộ partition key, không chỉ định clustering key | Xóa cả hàng clustering lẫn static data của phân vùng. |

### Cập nhật static column

```sql
UPDATE session_events_by_id
SET source_app = 'android'
WHERE tenant_id = 'acme'
  AND session_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

Lần đọc sau có thể hiển thị `android` ở **mọi hàng** trong phân vùng, tùy thời điểm và consistency level. Cassandra xử lý ghi theo semantics timestamp của các cell; cập nhật đồng thời có thể dẫn đến kết quả theo quy tắc phân giải xung đột, không phải phép gán có khóa độc quyền toàn phân vùng.

### Xóa duy nhất một static column

```sql
DELETE source_app
FROM session_events_by_id
WHERE tenant_id = 'acme'
  AND session_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

Sau khi xóa thành công và đọc với mức nhất quán phù hợp, `source_app` không còn giá trị hiện hành, nhưng các sự kiện và những static columns khác vẫn có thể tồn tại.

### Xóa một sự kiện vẫn giữ metadata

```sql
-- Giả sử event_id dưới đây là ID thật của sự kiện cần xóa:
DELETE FROM session_events_by_id
WHERE tenant_id = 'acme'
  AND session_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_time = '2026-11-21T08:00:05Z'
  AND event_id = 199dd010-a94c-11e5-bf7f-feff819cdc9f;
```

Lệnh này tác động đến hàng có clustering key đã cho; các static columns vẫn thuộc về phân vùng.

### Xóa toàn phân vùng

```sql
DELETE FROM session_events_by_id
WHERE tenant_id = 'acme'
  AND session_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

Khi xóa **partition** theo cách này, Cassandra xóa cả phần static và các hàng clustering của phân vùng, bằng cơ chế tombstone. Trong Cassandra, xóa không có nghĩa dữ liệu biến mất tức thời khỏi mọi SSTable vật lý; compaction và cơ chế xử lý tombstone liên quan đến vòng đời lưu trữ.

> **Lỗi dễ gặp:** muốn đổi metadata chung, nhưng lại ghi nó như một regular column trên một hàng cụ thể. Đọc các hàng khác sẽ không tự có giá trị ấy. Hãy khai báo `STATIC` đúng lúc thiết kế nếu ngữ nghĩa thực sự thuộc về phân vùng.

## 6. TTL, timestamp ghi và replication của static columns

Static columns là **các cell Cassandra bình thường xét về TTL, write timestamp và replication**, chỉ khác phạm vi gắn với phân vùng.

### TTL có thể áp dụng cho static column

Ví dụ, đặt thời hạn một giờ cho một giá trị static:

```sql
UPDATE session_events_by_id
USING TTL 3600
SET source_app = 'temporary-web'
WHERE tenant_id = 'acme'
  AND session_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

TTL gắn với **giá trị cell được ghi bởi thao tác**, không mặc nhiên đặt hạn sử dụng một giờ cho mọi hàng sự kiện trong phân vùng. Khi giá trị static hết TTL, các sự kiện khác vẫn có thể tiếp tục tồn tại.

Có thể quan sát TTL và write timestamp của một cell trong ngữ cảnh truy vấn thích hợp:

```sql
SELECT DISTINCT tenant_id, session_id, source_app
FROM session_events_by_id
WHERE tenant_id = 'acme'
  AND session_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

Nếu muốn xem `TTL(source_app)` hoặc `WRITETIME(source_app)`, có thể truy vấn các hàm đó trong câu `SELECT` thông thường; giá trị nhận được phản ánh metadata của cell còn tồn tại và phụ thuộc thời điểm đọc.

### Static data vẫn chịu replication và consistency

- Static values thuộc **cùng phân vùng** với hàng sự kiện, được phân phối theo **cùng partition key**, không có token riêng.
- Các replica được quyết định bởi **keyspace replication strategy và replication factor**. Static columns không tạo một “bảng con” có replication khác.
- Đọc/ghi static columns dùng semantics **consistency level** và **last-write-wins theo timestamp** như dữ liệu Cassandra tương ứng. Điều đó không bảo đảm mọi replica nhìn thấy cập nhật ngay tức thời.
- `STATIC` không tự đem lại transaction đa phân vùng, tính duy nhất toàn hệ thống hoặc bảo đảm các trường metadata được cập nhật đồng thời theo mọi yêu cầu nghiệp vụ.

Ví dụ: nếu một ứng dụng ghi metadata ở consistency level `ONE` và ngay sau đó đọc từ replica chưa nhận cập nhật, có thể nhìn thấy giá trị cũ. Việc chọn consistency level theo nhu cầu đọc/ghi là quyết định riêng của hệ thống, không phải tính năng đặc biệt của static column.

### Thay đổi static value có tác động ra sao?

Một giá trị static mới được ghi **một lần theo partition key**. Ứng dụng không cần phát lệnh `UPDATE` cho từng clustering row. Tuy nhiên, nếu bạn **sao chép cùng một thông tin nghiệp vụ qua nhiều phân vùng** (ví dụ cùng `user_id` trên hàng nghìn phân vùng theo ngày), cập nhật static ở một phân vùng **không** tự cập nhật các phân vùng khác.

## 7. Khi nào nên và không nên dùng `STATIC`?

Static columns thích hợp với dữ liệu:

1. **Có ý nghĩa đúng ở mức partition**: toàn bộ phiên dùng chung user đã đăng nhập, thời gian bắt đầu hoặc kênh tạo phiên.
2. **Thường được đọc kèm các hàng clustering**: truy vấn sự kiện muốn hiện thêm thông tin về phiên.
3. **Được quản lý theo partition key**: ứng dụng có thể biết chính xác phiên cần đọc/cập nhật.
4. **Không cần đồng bộ tự động qua nhiều partition**.

Ví dụ phù hợp:

| Partition key | Clustering keys | Static data có ý nghĩa |
| --- | --- | --- |
| `session_id` | `event_time, event_id` | Thời gian bắt đầu phiên, client tạo phiên. |
| `(tenant_id, device_id, event_day)` | `measured_at, measurement_id` | Ghi chú hoặc cấu hình áp dụng **riêng cho bucket ngày đó**. |
| `order_id` | `line_number` | Trạng thái hoặc đơn vị tiền tệ của **đơn hàng**; từng line item mang giá trị riêng. |
| `(account_id, month_bucket)` | `transaction_time, transaction_id` | Metadata được định nghĩa riêng cho tháng giao dịch. |

Những trường hợp **không phù hợp**:

- **Thông tin toàn cục của người dùng:** tên hiển thị hoặc địa chỉ email phải nhất quán ở hàng nghìn phân vùng theo tenant, ngày và phiên. Một static cell ở phiên A không tự cập nhật ở phiên B. Nên cân nhắc bảng hồ sơ theo `user_id` hoặc mô hình đồng bộ nhiều bảng rõ ràng.
- **Dữ liệu thay đổi theo từng hàng:** nhiệt độ từng lần đo, trạng thái từng line item hoặc thời gian sự kiện. Các giá trị này phải là regular columns.
- **Giá trị tổng hợp cần cập nhật chính xác dưới ghi đồng thời:** `total_events STATIC` rồi đọc–cộng–ghi có thể mất cập nhật khi nhiều producer ghi song song. Cần thiết kế tính toán tổng hợp, counter phù hợp hoặc cơ chế phối hợp riêng; `STATIC` không giải quyết tính nguyên tử của phép cộng.
- **Dữ liệu cần truy vấn theo mọi giá trị static:** ví dụ “tìm tất cả phiên có `source_app = 'web'`”. Định nghĩa static column **không tự tạo chỉ mục toàn bảng** cho `source_app`.
- **Phân vùng quá lớn:** `STATIC` chỉ tiết kiệm phần thông tin lặp lại; nó không chia một phân vùng lớn thành các phân vùng nhỏ hơn.

### Static column so với bảng metadata riêng

Hai cách mô hình hóa phổ biến:

| Tiêu chí | Metadata dưới dạng `STATIC` | Metadata ở bảng riêng |
| --- | --- | --- |
| Phạm vi | Một phân vùng của bảng có clustering rows. | Theo partition key của bảng metadata. |
| Đọc cùng sự kiện | Có thể nhận metadata trong cùng truy vấn theo phân vùng. | Ứng dụng thường cần thêm truy vấn metadata. |
| Cập nhật | Một partition key của bảng sự kiện. | Một partition key của bảng metadata. |
| Tái sử dụng từ nhiều bảng/phân vùng | Không tự đồng bộ. | Có thể cùng đọc một bản ghi metadata độc lập. |
| Vòng đời dữ liệu | Dễ gắn với phân vùng sự kiện, nhưng TTL/xóa cần được cân nhắc. | Có thể quản lý vòng đời metadata riêng. |

Nếu dữ liệu thực sự là metadata của **phiên**, static columns hợp lý. Nếu nó là thuộc tính **người dùng tồn tại độc lập với phiên**, bảng hồ sơ riêng thường rõ nghĩa hơn.

## 8. Đọc và cập nhật static columns từ Java

Ví dụ Java Driver 4.x dưới đây giả định `CqlSession` đã kết nối và bảng `session_events_by_id` nằm trong keyspace hiện hành. `PreparedStatement` được chuẩn bị một lần rồi tái sử dụng.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.util.UUID;

public final class SessionMetadataRepository {
    private final CqlSession session;
    private final PreparedStatement readMetadata;
    private final PreparedStatement writeSourceApp;

    public SessionMetadataRepository(CqlSession session) {
        this.session = session;
        this.readMetadata = session.prepare(
            "SELECT DISTINCT tenant_id, session_id, user_id, " +
            "started_at, source_app " +
            "FROM session_events_by_id " +
            "WHERE tenant_id = ? AND session_id = ?"
        );
        this.writeSourceApp = session.prepare(
            "UPDATE session_events_by_id SET source_app = ? " +
            "WHERE tenant_id = ? AND session_id = ?"
        );
    }

    public SessionMetadata findMetadata(String tenantId, UUID sessionId) {
        Row row = session.execute(readMetadata.bind(tenantId, sessionId)).one();
        if (row == null) {
            return null; // Không có dữ liệu cho phân vùng được hỏi
        }
        return new SessionMetadata(
            row.getUuid("user_id"),
            row.getInstant("started_at"),
            row.getString("source_app")
        );
    }

    public void updateSourceApp(String tenantId, UUID sessionId, String sourceApp) {
        session.execute(writeSourceApp.bind(sourceApp, tenantId, sessionId));
    }

    public record SessionMetadata(
        UUID userId, Instant startedAt, String sourceApp
    ) {}
}
```

Điểm cần chú ý:

- Java bind **đủ thành phần partition key**: `tenantId` và `sessionId`.
- `SELECT DISTINCT` chỉ lấy partition key và static columns, phù hợp mục tiêu đọc metadata của một phiên.
- `UPDATE` một static column **không cần event_time/event_id**.
- Giá trị static có thể là `null` nếu chưa ghi hoặc đã hết TTL; ứng dụng cần xử lý trường hợp đó.
- Nếu yêu cầu nghiệp vụ đòi hỏi đọc sau ghi với mức nhất quán cụ thể, hãy cấu hình consistency level trong driver/statement theo chính sách của hệ thống.

`STATIC` giúp giảm thao tác cập nhật nhiều hàng, nhưng vẫn cần quản lý phiên bản metadata, cơ chế retry và đồng thời ghi trong ứng dụng Java như đối với các dữ liệu Cassandra khác.

## 9. Lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `CREATE TABLE` báo lỗi khi khai báo `STATIC` | Bảng không có clustering column, hoặc cố dùng `STATIC` cho khóa. | Kiểm tra cấu trúc primary key, chỉ đánh dấu cột không thuộc khóa. |
| `SELECT *` cho thấy static data “bị lặp” | Static values xuất hiện trên **mỗi hàng kết quả** trong phân vùng. | Hiểu đây là phép chiếu dữ liệu; dùng `SELECT DISTINCT` nếu chỉ cần metadata. |
| Ghi static metadata nhưng chưa thấy sự kiện nào | Ghi chỉ partition key và static columns không tạo hàng clustering. | Đây là trạng thái hợp lệ; ghi event với đầy đủ clustering key khi cần. |
| Cập nhật `source_app` của một phiên nhưng phiên khác vẫn giữ giá trị cũ | Static data chỉ có phạm vi một partition key. | Phân biệt metadata phiên với metadata toàn cục; dùng bảng riêng hoặc cập nhật có chủ đích. |
| Cột static đột nhiên là `null` | Chưa ghi, đã xóa, đã hết TTL hoặc có khác biệt quan sát do consistency. | Kiểm tra luồng cập nhật, TTL, consistency và dấu vết ghi. |
| Xóa hết event nhưng metadata vẫn còn | Xóa từng hàng clustering không xóa static values. | Xác định yêu cầu vòng đời; khi cần xóa cả phiên, xóa nguyên phân vùng. |
| Cập nhật bộ đếm sự kiện bằng `total + 1` rồi `UPDATE` static | Ghi đồng thời gây mất cập nhật. | Dùng mô hình tổng hợp/đồng bộ phù hợp; không coi static cell là counter nguyên tử. |
| Truy vấn `WHERE source_app = 'web'` không được phục vụ hiệu quả | Static column không phải partition key hay clustering key. | Thiết kế bảng phục vụ kiểu truy vấn hoặc đánh giá chỉ mục tương thích phiên bản. |

## 10. Tự kiểm tra kiến thức

Xét bảng lưu danh sách mặt hàng theo đơn hàng:

```sql
CREATE TABLE order_items_by_order (
    order_id      uuid,
    line_number   int,
    product_id    uuid,
    quantity      int,
    unit_price    decimal,
    currency      text STATIC,
    customer_note text STATIC,
    PRIMARY KEY (order_id, line_number)
);
```

Hãy trả lời trước khi xem phần giải thích:

1. Partition key, clustering key và static columns của bảng là gì?
2. Hai line item cùng `order_id` có thể có hai giá trị `currency` riêng không?
3. Có thể ghi `customer_note` trước khi có `line_number` đầu tiên không?
4. Xóa một hàng có `line_number = 3` có làm mất `currency` của đơn không?
5. Nếu muốn đổi `currency` của **một đơn**, phải chỉ định những cột nào trong `WHERE`?
6. `SELECT currency, customer_note FROM order_items_by_order WHERE order_id = ...` có luôn trả một hàng duy nhất không?
7. `currency STATIC` có tự tạo khả năng tìm mọi đơn dùng tiền tệ `'VND'` không?

**Đáp án:**

1. Partition key: `order_id`; clustering key: `line_number`; static columns: `currency` và `customer_note`.
2. **Không theo cùng partition**: mọi line item của cùng đơn nhìn thấy cùng một giá trị static `currency` hiện hành.
3. **Có**: ghi các static columns cùng `order_id`, không cần `line_number`.
4. **Không**: xóa một hàng clustering không xóa static metadata của phân vùng.
5. `WHERE order_id = ...` là đủ để cập nhật `currency`.
6. **Không được giả định**: khi có nhiều hàng clustering, dữ liệu static có thể xuất hiện lặp trong kết quả; nên dùng `SELECT DISTINCT order_id, currency, customer_note ...` nếu chỉ cần metadata.
7. **Không**: `STATIC` không tự cung cấp chỉ mục hay phép tìm kiếm theo giá trị cột trên toàn bảng.

## 11. Tóm tắt và nguyên tắc thiết kế

- `STATIC` khai báo **một giá trị dùng chung cho mỗi partition key**; bảng phải có ít nhất một clustering column.
- Static column không nằm trong primary key, không tham gia hashing token hoặc thứ tự clustering.
- Đọc dữ liệu cùng nhiều clustering rows có thể **hiển thị static data lặp lại**; đó là cách biểu diễn kết quả, không phải nhiều giá trị riêng biệt.
- Có thể **ghi hoặc cập nhật static columns chỉ bằng partition key**; xóa từng clustering row không tự xóa static data.
- Static cells vẫn chịu **TTL, write timestamp, replication, consistency** như dữ liệu Cassandra; tính nhất quán không được tăng cường chỉ vì cột là static.
- Chỉ dùng `STATIC` khi dữ liệu **thật sự có cùng ý nghĩa trong một phân vùng**. Metadata độc lập hoặc phải đồng bộ qua nhiều phân vùng thường cần bảng/chiến lược khác.

Hiểu chính xác static columns giúp bạn kết hợp dữ liệu chung và dữ liệu theo hàng trong mô hình wide-column Cassandra, kiểm soát vòng đời bản ghi và viết truy vấn CQL/Java phù hợp. Đây là nền tảng để tiếp tục tìm hiểu replication, consistency level, compaction, repair và các trường hợp vận hành khi dữ liệu bị cập nhật hoặc xóa.

