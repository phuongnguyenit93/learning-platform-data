# Kiểu dữ liệu trong khóa và các ràng buộc tương ứng của Apache Cassandra

Trong **Apache Cassandra**, chọn kiểu dữ liệu cho một cột trong `PRIMARY KEY` không chỉ là quyết định biểu diễn giá trị. Kiểu của **partition key** ảnh hưởng cách Cassandra tạo token và phân phối dữ liệu tới replica; kiểu của **clustering column** ảnh hưởng cách các hàng được **so sánh và sắp xếp bên trong một phân vùng**. Một kiểu CQL hoàn toàn hợp lệ cho cột dữ liệu thông thường chưa chắc hợp lệ — hoặc phù hợp — khi đưa vào khóa.

Bài thuộc chương **Kiểu dữ liệu** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Mục tiêu của module là nắm kiến trúc phân tán và mô hình wide-column, thiết kế bảng theo truy vấn, mức nhất quán đọc/ghi, CQL, replication, compaction, repair, xử lý lỗi và kết nối Java. Vì vậy, bài không chỉ liệt kê cú pháp khóa mà còn giải thích **ngữ nghĩa định danh, thứ tự, uniqueness, khả năng truy vấn, kiểm soát retry và vận hành**. Các chi tiết phụ thuộc phiên bản Cassandra hoặc bản phân phối được chỉ rõ để tránh áp dụng máy móc.

## 1. Hiểu đúng PRIMARY KEY trước khi chọn kiểu

Mỗi bảng Cassandra phải có một **`PRIMARY KEY`**. Khóa chính có hai phần:

1. **Partition key** — luôn tồn tại; gồm **một hoặc nhiều cột**; Cassandra mã hóa và băm nó bằng partitioner để xác định token và các replica.
2. **Clustering columns** — có thể không có; các cột nằm **sau** partition key trong khai báo khóa và quyết định thứ tự các hàng **trong cùng partition**.

Ba khai báo sau **không tương đương**:

~~~cql
-- 1. Chỉ có partition key, mỗi partition có tối đa một row.
CREATE TABLE accounts_by_id (
    account_id uuid PRIMARY KEY,
    display_name text
);

-- 2. account_id là partition key;
--    event_id là clustering column.
CREATE TABLE events_by_account (
    account_id uuid,
    event_id timeuuid,
    event_type text,
    PRIMARY KEY (account_id, event_id)
);

-- 3. (account_id, event_day) là partition key tổng hợp;
--    event_id là clustering column.
CREATE TABLE events_by_account_day (
    account_id uuid,
    event_day date,
    event_id timeuuid,
    event_type text,
    PRIMARY KEY ((account_id, event_day), event_id)
);
~~~

| Khai báo | Partition key | Clustering columns | Hệ quả |
|---|---|---|---|
| `PRIMARY KEY (a)` | `a` | Không có | Mỗi giá trị `a` nhận diện một row/partition |
| `PRIMARY KEY (a, b)` | `a` | `b` | Nhiều row có thể cùng `a`, được sắp theo `b` |
| `PRIMARY KEY ((a, b))` | `(a, b)` | Không có | `a` và `b` **cùng tạo token** của partition |
| `PRIMARY KEY ((a, b), c, d)` | `(a, b)` | `c`, `d` | Dữ liệu cùng cặp `a,b` nằm chung partition, sắp theo `c,d` |

**Thứ tự và dấu ngoặc là một phần của schema**, không phải định dạng trang trí. Một lỗi rất thường gặp là viết `PRIMARY KEY (tenant_id, day, event_id)` rồi tưởng `(tenant_id, day)` là partition key. Thực tế, ở cú pháp ấy **chỉ `tenant_id`** là partition key, còn `day` là clustering column. Muốn bucket theo cả tenant và ngày, phải dùng `PRIMARY KEY ((tenant_id, day), event_id)`.

### 1.1. “Có thứ tự” không có nghĩa “dữ liệu toàn cluster được sắp”

Cassandra không bố trí các partition theo giá trị số/hôm trước/hôm sau của khóa như một bảng SQL có index B-tree tuần tự. Partitioner thường băm **toàn bộ partition key** thành token; hai ngày liên tiếp hoặc hai UUID v1 liên tiếp không nhất thiết nằm gần nhau trên vòng token.

Clustering columns mới có thứ tự trong **một partition**. Do đó:

- `timestamp` làm **partition key đơn** không giúp truy vấn “100 sự kiện mới nhất toàn cluster”.
- `timeuuid` làm **clustering key** trong partition đã chọn có thể giúp đọc dòng theo thời gian nhúng trong UUID v1.
- `date` đưa vào **partition key tổng hợp** hữu ích để bucket, nhưng muốn đọc ba ngày vẫn phải xử lý các partition ngày khác nhau hoặc có đường truy cập khác.

## 2. Kiểu CQL nào được phép làm thành phần khóa?

Tài liệu CQL xác nhận hai ràng buộc **tuyệt đối quan trọng**:

- **`counter` không thể là cột thuộc `PRIMARY KEY`**. Nó là kiểu cột bộ đếm với phép tăng/giảm riêng.
- **`duration` không thể là cột thuộc `PRIMARY KEY`** vì không có thứ tự so sánh độc lập với mốc lịch (`1mo` không luôn lớn/nhỏ hơn `30d`).

Với các kiểu khác, tính hợp lệ còn phụ thuộc kiểu phức hợp, việc **frozen**, phiên bản và quy tắc schema.

| Nhóm/kiểu CQL | Trong `PRIMARY KEY` | Đánh giá thiết kế |
|---|---|---|
| `uuid`, `timeuuid` | Thường phù hợp | `uuid` cho ID; `timeuuid` rất hợp clustering của timeline |
| `text`, `varchar`, `ascii` | Có | Cần chuẩn hóa, giới hạn độ dài, tránh key tùy tiện |
| `tinyint`, `smallint`, `int`, `bigint`, `varint` | Có | Dùng ID/sequence/bucket có miền rõ ràng; tránh hotspot |
| `date`, `timestamp`, `time` | Có | Phân biệt ngày bucket, thời điểm tuyệt đối và giờ trong ngày |
| `inet`, `boolean`, `blob` | Có theo quy tắc kiểu | Tính hợp lệ không đảm bảo phân phối tốt; `boolean` đơn lẻ đặc biệt dễ nóng |
| `decimal`, `float`, `double` | Có thể khai báo theo khả năng kiểu CQL | Thường **không nên** làm ID nghiệp vụ vì chuẩn hóa và số học dấu phẩy động |
| `counter` | **Không** | Chỉ là cột counter với quy tắc ghi riêng |
| `duration` | **Không** | Khoảng lịch không có tổng thứ tự ổn định |
| `list<T>`, `set<T>`, `map<K,V>` **không frozen** | **Không** | Dữ liệu đa cell, không phù hợp cột khóa |
| `frozen<list<T>>`, `frozen<set<T>>`, `frozen<map<K,V>>` | **Có thể**, nếu kiểu con cũng hợp lệ | Hợp pháp không đồng nghĩa nên dùng: khóa lớn/khó ổn định |
| `tuple<...>` | Tuple vốn **frozen**, dùng được khi các kiểu thành phần phù hợp | Dễ nhầm vị trí; nên ưu tiên khóa scalar đơn giản |
| `frozen<UDT>` | Có thể theo phiên bản và kiểu các field | Giá trị nguyên khối; đổi field có thể đổi toàn bộ key |
| UDT không frozen | **Không nên/không hợp lệ** ở vị trí khóa | Nếu cần thử khóa UDT, dùng frozen và kiểm tra DDL |
| `vector<T,N>` (Cassandra 5.0+) | **Không nên chọn làm khóa**; phải kiểm tra hạn chế của bản triển khai | Dùng cột dữ liệu/index vector; giữ khóa nhận diện scalar ổn định |
| `STATIC` | **Không** | `STATIC` là đặc tính của cột **không thuộc khóa** |

**Chú ý với kiểu phức hợp:** `frozen` có thể giúp một collection/UDT được lưu và so sánh như một giá trị, nhưng **không hợp thức hóa mọi kiểu con**. Ví dụ, việc chứa `duration` hoặc cấu trúc bị hạn chế ở sâu bên trong vẫn có thể khiến schema khóa bị từ chối. **Kiểm tra trực tiếp `CREATE TABLE` trên phiên bản Cassandra thực tế** khi dùng kiểu phức hợp; không suy từ chữ `frozen` rằng “mọi thứ đều dùng làm key được”.

Trong thực tế, hầu hết bảng production sẽ có khóa gồm `uuid`, `timeuuid`, `text`, `int`, `bigint`, `timestamp`, `date` hoặc vài kiểu scalar đơn giản khác. Khóa phức hợp frozen là **khả năng ngôn ngữ**, không phải lời khuyên mặc định.

## 3. Partition key: ba ràng buộc về nhận diện, giá trị và phân phối

### 3.1. Cần giá trị hiện diện và ổn định

Một partition key phải có **giá trị hợp lệ**, không phải `NULL` hay `UNSET`. Trong prepared statement, không được bỏ qua bind marker thuộc partition key rồi mong Cassandra tự chọn row.

~~~cql
-- Sai: NULL không tạo được partition key.
-- INSERT INTO accounts_by_id (account_id, display_name)
-- VALUES (null, 'Khách A');

-- Đúng: cung cấp UUID phù hợp.
INSERT INTO accounts_by_id (account_id, display_name)
VALUES (11111111-1111-4111-8111-111111111111, 'Khách A');
~~~

Trong một câu lệnh `INSERT`, mọi thành phần `PRIMARY KEY` cần được xác định. Với `DELETE`/`SELECT`, một số cú pháp cho phép chọn **phân vùng** hoặc **khoảng clustering** thay vì một row cụ thể, nhưng không nên nhầm **bỏ điều kiện clustering để tác động lên nhiều row** với **bind NULL cho key**.

**`0`, `false` hoặc ngày `1970-01-01` không phải NULL.** Đây là những giá trị CQL hợp lệ khi chúng thuộc miền nghiệp vụ. Tuy nhiên, việc dùng một giá trị đặc biệt như `0` để thay “chưa biết ID” có thể khiến nhiều request vô tình gom vào một partition và ghi đè cùng khóa. Trường thiếu ID nên được xử lý ở tầng ingest hoặc staging bằng một khóa hợp lệ khác.

### 3.2. Không thể UPDATE trực tiếp giá trị primary key

Một lần ghi với **cùng toàn bộ primary key** sẽ được Cassandra xử lý theo cơ chế **upsert** (các cell có thể được ghi/ghi đè), không sinh một row mới do khóa trùng. CQL không cho phép biến `account_id = A` thành `account_id = B` bằng `UPDATE SET account_id = B`.

Muốn thay khóa về mặt nghiệp vụ, cần **tạo row mới với khóa mới** và xử lý row cũ, cùng mọi bảng theo truy vấn có liên quan:

~~~cql
-- Giả sử ID mới là một tài khoản khác.
INSERT INTO accounts_by_id (account_id, display_name)
VALUES (22222222-2222-4222-8222-222222222222, 'Khách A');

-- Chỉ xóa row cũ sau khi việc di chuyển đã được kiểm tra.
DELETE FROM accounts_by_id
WHERE account_id = 11111111-1111-4111-8111-111111111111;
~~~

Hai câu lệnh này **không mặc nhiên là một transaction ACID đa partition**. Ứng dụng cần cơ chế trạng thái, đối soát, rollback/compensation hoặc LWT tùy yêu cầu. Đặc biệt, đổi partition key có thể chuyển dữ liệu tới **token và replica khác**.

### 3.3. Kiểu hợp lệ vẫn có thể gây hotspot

Giả sử một bảng dùng:

~~~cql
-- Sai về phân phối khi bảng dự kiến có hàng triệu sự kiện:
-- CREATE TABLE all_events_by_success (
--     succeeded boolean,
--     occurred_at timestamp,
--     event_id uuid,
--     PRIMARY KEY (succeeded, occurred_at, event_id)
-- );
~~~

`boolean` có thể là một kiểu khóa CQL hợp lệ, nhưng partition key **chỉ có hai giá trị thường gặp**: `true` và `false`. Tất cả sự kiện có thể tập trung vào hai partition cực lớn, tạo hotspot, read amplification và áp lực compaction.

Một `tenant_id` đơn lẻ cũng có thể nóng nếu một tenant phát hàng triệu event mỗi giờ. **Cardinality cao không phải chỉ tiêu duy nhất**; phải xem lưu lượng và **kích thước từng partition**.

Quy tắc: chọn partition key dựa trên **mẫu truy vấn + khả năng chia tải + kích thước dự kiến**, không chọn chỉ vì kiểu được parser chấp nhận.

## 4. Composite partition key: kiểu của từng thành phần là hợp đồng

Một partition key tổng hợp được tạo bằng cách mã hóa **tất cả thành phần khóa**, theo thứ tự khai báo.

~~~cql
CREATE TABLE api_events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    response_code smallint,
    service_name text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

Ý nghĩa:

- `tenant_id uuid` nhận diện tenant ổn định.
- `event_day date` tạo **bucket ngày** để không đặt toàn bộ event của tenant vào một partition vô hạn.
- `occurred_at timestamp` sắp các hàng theo thời điểm (mili giây).
- `event_id uuid` làm **tie-breaker**, giúp phân biệt các sự kiện có cùng `occurred_at`.
- `response_code smallint` và `service_name text` là cột dữ liệu, **không** tham gia nhận diện row hay phân phối token.

Truy vấn đọc 50 event gần nhất của tenant trong ngày:

~~~cql
SELECT occurred_at, event_id, response_code, service_name
FROM api_events_by_tenant_day
WHERE tenant_id = 99999999-9999-4999-8999-999999999999
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

Truy vấn trong khoảng 08:00–09:00 UTC:

~~~cql
SELECT occurred_at, event_id, response_code
FROM api_events_by_tenant_day
WHERE tenant_id = 99999999-9999-4999-8999-999999999999
  AND event_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T08:00:00Z'
  AND occurred_at <  '2026-11-21T09:00:00Z'
LIMIT 100;
~~~

Đây là kiểu truy vấn hiệu quả theo thiết kế vì đã biết **đầy đủ partition key** và điều kiện khoảng trên clustering column đầu tiên. Dùng khoảng nửa mở `[start, end)` giúp tránh đọc trùng sự kiện ở ranh giới giữa hai cửa sổ liền nhau.

### 4.1. Day bucket cần cùng quy tắc timezone

Java có thể tính:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

Instant occurredAt = Instant.parse("2026-11-21T08:30:15.123Z");
LocalDate eventDayUtc =
    occurredAt.atZone(ZoneOffset.UTC).toLocalDate();
~~~

Nếu các client ghi `event_day` theo UTC nhưng lại truy vấn theo ngày địa phương (ví dụ UTC+07), cùng một event có thể được tìm ở partition khác với nơi thực sự đã ghi. **`date` không có múi giờ**; quy tắc bucket phải được tài liệu hóa.

Ngày là một thành phần partition key nên **nó không tự phân vùng mịn hơn** nếu một tenant gửi rất nhiều event trong một ngày. Khi cần, cân nhắc bucket giờ hoặc thêm shard ổn định và điều chỉnh truy vấn để biết shard phải đọc.

### 4.2. Không thêm sharding mù quáng

Một bảng có `PRIMARY KEY ((tenant_id, event_day, shard), occurred_at, event_id)` có thể giúp chia tải write của tenant/ngày thành nhiều partition. Nhưng muốn đọc “toàn bộ event trong ngày theo thứ tự mới nhất”, ứng dụng phải đọc những shard cần thiết rồi **merge kết quả**; Cassandra không tự gom và sắp toàn bộ các partition đó.

Chọn `shard` bằng hàm ổn định dựa trên event ID hoặc chiến lược điều phối đã định nghĩa. Nếu sau retry cùng một event bị đẩy sang shard khác, sẽ sinh duplicate row. Sharding là **đổi chi phí write lấy độ phức tạp read**, không phải tối ưu miễn phí.

## 5. Clustering key: kiểu phải có thứ tự nhất quán

Clustering columns sắp xếp row **theo comparator của từng kiểu CQL**, lần lượt theo thứ tự khai báo. Điều này khác với thứ tự người dùng mong muốn trên UI hoặc thứ tự địa phương của chuỗi.

Ví dụ:

~~~cql
CREATE TABLE messages_by_room_day (
    room_id uuid,
    message_day date,
    sent_at timestamp,
    message_id uuid,
    sender_id uuid,
    body text,
    PRIMARY KEY ((room_id, message_day), sent_at, message_id)
) WITH CLUSTERING ORDER BY (sent_at DESC, message_id ASC);
~~~

Cassandra có thể đọc “mới nhất trước” trong một partition mà không phải sắp hàng nghìn row ở Java:

~~~cql
SELECT sent_at, message_id, sender_id, body
FROM messages_by_room_day
WHERE room_id = 33333333-3333-4333-8333-333333333333
  AND message_day = '2026-11-21'
LIMIT 50;
~~~

### 5.1. Vì sao cần tie-breaker?

Kiểu `timestamp` trong Cassandra lưu thời điểm tới **mili giây**. Hai message có thể được gửi trong cùng mili giây; nếu primary key chỉ có `((room_id, message_day), sent_at)`, hai lần ghi có thể dùng **cùng khóa row**, làm mất một message.

Thêm `message_id uuid` đảm bảo hai message với ID khác nhau có thể tồn tại cạnh nhau. Thứ tự giữa hai message có **cùng sent_at** lúc này phụ thuộc **comparator của UUID**, không chứng minh message nào xảy ra trước trong thực tế.

Nếu nghiệp vụ cần thứ tự tuyệt đối ở độ phân giải cao hơn, một **sequence ổn định từ nguồn**, `event_epoch_ns bigint` hoặc cơ chế thứ tự được thiết kế riêng có thể phù hợp hơn. Nhưng phải xác định ai cấp sequence và làm sao xử lý nhiều writer đồng thời.

### 5.2. timeuuid và UUID v4 khác nhau

- `uuid` thường dùng cho **định danh ổn định**, ví dụ `UUID.randomUUID()` (UUID v4 trong Java). Không được dựa vào một UUID v4 để sắp các sự kiện theo thời gian.
- `timeuuid` biểu diễn UUID **phiên bản 1**, chứa timestamp và được Cassandra so sánh theo thành phần thời gian. Nó phù hợp làm clustering key cho timeline **theo thời điểm sinh ID**.
- `timeuuid` không chứng minh timestamp hệ thống là chính xác, không đảm bảo thứ tự nhân quả giữa mọi host, và không thay thế `occurred_at` khi sự kiện nguồn có thể đến trễ.

Một thiết kế thay thế:

~~~cql
CREATE TABLE events_by_device_day_timeuuid (
    device_id uuid,
    event_day date,
    event_id timeuuid,
    source_time timestamp,
    event_type text,
    PRIMARY KEY ((device_id, event_day), event_id)
) WITH CLUSTERING ORDER BY (event_id DESC);
~~~

Với bảng này, hàng được sắp theo thời gian trong `event_id`, **không phải** theo `source_time` nếu dữ liệu được nhận trễ. Chọn theo câu hỏi nghiệp vụ, không chỉ vì `timeuuid` chứa chữ “time”.

### 5.3. Kiểu text có thứ tự nhưng không phải collation ngôn ngữ

Nếu `city text` là clustering column, thứ tự so sánh dựa trên giá trị chuỗi theo comparator CQL, **không phải** thứ tự từ điển tiếng Việt/tiếng Pháp do locale quyết định. Việc chữ có dấu, chữ hoa/thường, NFC/NFD và case folding có thể làm kết quả khác mong muốn.

Nếu cần tìm người dùng theo `email`, hãy dùng `email_key text` đã được **canonicalize** ở ứng dụng. Nếu cần danh sách sắp theo cách hiển thị địa phương, phải thiết kế sort key có quy tắc rõ, hoặc sort trong một tập kết quả đã giới hạn, không mong Cassandra tự hiểu locale.

### 5.4. CLUSTERING ORDER BY không áp dụng cho partition key

`WITH CLUSTERING ORDER BY (...)` chỉ nêu **clustering columns**, không nêu các cột của partition key. Ví dụ hợp lệ:

~~~cql
WITH CLUSTERING ORDER BY (sent_at DESC, message_id ASC)
~~~

Không được dùng `WITH CLUSTERING ORDER BY (room_id DESC)` để biến việc phân phối token thành thứ tự thời gian của tất cả room. **Thứ tự clustering chỉ bên trong partition**.

## 6. Quy tắc truy vấn liên quan trực tiếp đến thứ tự khóa

Việc chọn kiểu cho một khóa phải đi kèm **mẫu `WHERE`** mà ứng dụng sử dụng.

Bảng ví dụ `messages_by_room_day` có khóa:

~~~text
Partition:  room_id + message_day
Clustering: sent_at DESC, message_id ASC
~~~

| Truy vấn | Có khớp đường truy cập chính không? | Lý do |
|---|---|---|
| Room + day, LIMIT 50 | **Có** | Đã biết cả partition key |
| Room + day + sent_at range | **Có** | Range trên clustering column đầu |
| Room + day + sent_at + message_id cụ thể | **Có** | Càng cụ thể theo thứ tự khóa |
| Chỉ room_id | **Không đủ partition key** | Ngày là thành phần của partition key |
| Chỉ day | **Không đủ partition key** | Chưa biết room_id |
| Chỉ message_id | **Không** | message_id là clustering column sau sent_at và không có partition key |
| Tất cả room theo sent_at mới nhất | **Không** qua bảng này | Không có thứ tự toàn cluster |

Với Cassandra, điều kiện trên clustering columns thông thường theo **thứ tự prefix** của khóa; không thể tùy ý bỏ qua `sent_at` rồi mong `WHERE message_id = ...` hoạt động hiệu quả. Một số kiểu `IN`, index hoặc khả năng filter khác phụ thuộc phiên bản, nhưng không nên dùng chúng làm lối tắt thay cho thiết kế bảng theo truy vấn.

Khi cần “tra một message chỉ bằng message_id”, hãy thêm bảng lookup phù hợp:

~~~cql
CREATE TABLE message_locator_by_id (
    message_id uuid PRIMARY KEY,
    room_id uuid,
    message_day date,
    sent_at timestamp
);
~~~

Ứng dụng tra locator rồi dùng `(room_id, message_day, sent_at, message_id)` để lấy nội dung từ bảng timeline. Hoặc lưu thông tin message trong bảng `messages_by_id` theo mẫu đọc nếu cần. **Việc ghi nhiều bảng cần đồng bộ, idempotency và đối soát**, vì Cassandra không tự bảo đảm mọi bản denormalized luôn được cập nhật cùng lúc như một transaction ACID đa partition.

## 7. NULL, UNSET và khóa không được thiếu

Cột thường có thể chưa được ghi, được xóa bằng NULL/DELETE hoặc bị bỏ qua khi bind UNSET. **Khóa thì khác**: Cassandra cần khóa hợp lệ để xác định row/partition.

~~~cql
-- Không chèn row nếu thiếu account_id.
-- INSERT INTO accounts_by_id (display_name) VALUES ('Chưa có ID');

-- Không bind NULL cho account_id.
-- INSERT INTO accounts_by_id (account_id, display_name)
-- VALUES (null, 'Không hợp lệ');
~~~

Quy tắc ở tầng Java:

| Trạng thái request | Cột khóa | Cột dữ liệu thường |
|---|---|---|
| Vắng mặt | **Từ chối hoặc lấy ID từ quy trình hợp lệ** | Có thể **UNSET/không ghi** trong PATCH |
| Explicit NULL | **Không chấp nhận** | Có thể mang nghĩa **xóa** và tạo tombstone |
| Có giá trị hợp lệ | Bind chính xác, ổn định | Bind/update |
| Có giá trị mặc định giả tạo | Chỉ dùng khi là ID nghiệp vụ thật | Có thể dùng default khi hợp đồng cho phép |

Nếu user chưa có `tenant_id`, đừng tự gán một UUID cố định kiểu “unknown tenant” cho mọi request. Điều đó vừa gây sai phân quyền, vừa gom tất cả dữ liệu vào một partition. Hãy xử lý trường hợp thiếu khóa ở **biên API** hoặc staging pipeline với một ID hợp lệ, được kiểm soát.

**Ngoại lệ cần hiểu đúng:** câu `DELETE FROM table WHERE partition_key = ?` có thể xóa cả partition mà không chỉ ra clustering columns. Đó là **phạm vi mutation khác**, không phải cho phép các thành phần khóa trong một `INSERT` được NULL.

## 8. Không dùng counter, duration và collection non-frozen trong PRIMARY KEY

### 8.1. Counter

`counter` dùng để **tăng/giảm** giá trị số nguyên theo cơ chế counter, không dùng làm định danh row.

~~~cql
CREATE TABLE requests_count_by_tenant_day (
    tenant_id uuid,
    request_day date,
    total counter,
    PRIMARY KEY ((tenant_id, request_day))
);
~~~

Cột `total` là counter **không thuộc khóa**. Những bảng chứa counter còn có quy tắc riêng: **các cột không thuộc PRIMARY KEY phải là counter**, không xen cột thông thường như `updated_at timestamp` tùy tiện. Counter không hỗ trợ TTL như cột thường, và retry phép tăng sau timeout có thể làm **đếm dư**.

~~~cql
UPDATE requests_count_by_tenant_day
SET total = total + 1
WHERE tenant_id = 99999999-9999-4999-8999-999999999999
  AND request_day = '2026-11-21';
~~~

Nếu cần truy vấn ngày/tenant, dùng ngày và ID làm khóa; không biến `total` thành một phần partition key chỉ vì cần đọc số đếm.

### 8.2. Duration

`duration` lưu **tháng, ngày, nano giây**; không thể so sánh có thứ tự duy nhất mà không biết mốc lịch. Đây là lý do Cassandra **cấm `duration` trong PRIMARY KEY**.

~~~cql
-- Sai schema:
-- CREATE TABLE billing_tasks_wrong (
--     interval duration PRIMARY KEY,
--     task_name text
-- );
~~~

Thay vì đó, tính **mốc đến hạn**:

~~~cql
CREATE TABLE billing_tasks_by_day (
    due_day date,
    due_at timestamp,
    task_id uuid,
    billing_interval duration,
    plan_code text,
    PRIMARY KEY ((due_day), due_at, task_id)
) WITH CLUSTERING ORDER BY (due_at ASC, task_id ASC);
~~~

`billing_interval duration` là **dữ liệu chính sách**, còn `due_day/date`, `due_at/timestamp` và `task_id/uuid` là **đường truy cập và định danh**. Nếu một ngày có quá nhiều task, cần shard/giờ hoặc chiến lược phân phối phù hợp, không đặt vô hạn task trong một partition.

### 8.3. Collection không frozen và frozen

`list`, `set`, `map` thông thường có thể là **multi-cell collection**, cho phép cập nhật từng phần tử/entry theo một số thao tác CQL. Chúng **không** phù hợp làm thành phần khóa.

Ngược lại, tài liệu `CREATE TABLE` của Cassandra nêu **primary keys có thể bao gồm frozen collections**:

~~~cql
-- Khả năng CQL, không phải khuyến nghị sản xuất:
CREATE TABLE features_by_frozen_tagset (
    tagset frozen<set<text>> PRIMARY KEY,
    description text
);
~~~

Khóa này có nhiều vấn đề:

- Thêm/bớt một tag làm **đổi toàn bộ giá trị khóa**; không thể cập nhật khóa bằng phép UPDATE.
- Tập có thể lớn, khiến khóa nặng, tốn bytes khi truyền và so sánh.
- Nhiều biểu diễn/canonicalization của text có thể tạo nhiều khóa khác nhau cho cùng ý định.
- Truy vấn “tất cả row có chứa tag X” không tự khả dụng chỉ vì tagset là partition key; vẫn cần **giá trị set nguyên vẹn** để tra đúng partition.

Do vậy, thường dùng `feature_set_id uuid` hoặc một khóa được tạo/canonicalize ổn định, còn `tags set<text>` làm cột dữ liệu. Nếu cần tìm theo tag, xây bảng theo tag hoặc đánh giá index phù hợp.

## 9. Tuple, UDT và vector: khả năng kiểu không quyết định thiết kế khóa

### 9.1. Tuple luôn frozen

Một `tuple<int, text>` có số vị trí cố định và **luôn frozen**; Cassandra xử lý như một giá trị nguyên khối. Các cấu trúc kiểu tuple có thể đáp ứng điều kiện dùng như giá trị khóa khi thành phần hợp lệ, nhưng dùng **hai cột scalar riêng** thường giúp ứng dụng truy vấn theo một thành phần rõ ràng hơn.

Ví dụ:

~~~cql
-- Tốt hơn tuple khi cần filter cả country và city rõ ràng:
CREATE TABLE offices_by_country_city (
    country_code ascii,
    city_code text,
    office_id uuid,
    office_name text,
    PRIMARY KEY ((country_code, city_code), office_id)
);
~~~

Nếu gộp `country_code, city_code` vào một `tuple<ascii,text>` làm partition key, ứng dụng mất khả năng biểu diễn từng thành phần bằng cột CQL độc lập trong schema, và việc validate/chuyển đổi theo từng field khó hiểu hơn.

### 9.2. Frozen UDT

Một UDT có tên field có thể dùng làm **giá trị frozen**; từ đó kiểu được xem là nguyên khối và có thể xuất hiện trong các vị trí khóa được phiên bản hỗ trợ. Nhưng một trường địa chỉ không phải định danh tốt:

- Đổi mã bưu điện/chuẩn hóa dấu làm đổi khóa.
- Hai khách hàng có thể trùng địa chỉ.
- Chuyển schema UDT cần kiểm soát codec, field order và migration.
- Truy vấn `city = ?` không tự được tối ưu nếu `city` nằm trong frozen UDT key.

Vì vậy, hãy dùng `customer_id uuid` làm khóa, còn `shipping_address frozen<address>` làm **snapshot dữ liệu**. Một **UDT không frozen** có mutation từng field, không phải cấu trúc để dùng như partition/clustering key.

### 9.3. Vector theo phiên bản Cassandra

Kiểu `vector<T, N>` xuất hiện trong Apache Cassandra **5.0**, lưu dãy phần tử có số chiều cố định. Với `vector<float,N>` và SAI, cluster có thể hỗ trợ **ANN similarity search**.

Đường tìm vector gần nhất khác hẳn đường đọc theo partition key:

~~~cql
-- Ví dụ thiết kế đúng vai trò:
CREATE TABLE embeddings_by_chunk_id (
    chunk_id uuid PRIMARY KEY,
    model_version text,
    embedding vector<float, 3>
);
~~~

Cột `chunk_id` giữ định danh ổn định; `embedding` là dữ liệu được index/so khớp. **Không dùng embedding làm định danh nghiệp vụ hoặc clustering theo similarity**; ANN ordering không phải `CLUSTERING ORDER BY`. Giới hạn chính xác của kiểu/vector trong key cần được kiểm tra theo phiên bản/bản phân phối, nhưng mô hình thông dụng và đáng tin cậy là **khóa scalar + cột vector/index**.

Nếu cluster là Cassandra 4.x, schema `vector<float,3>` có thể không được hỗ trợ; đừng copy một schema của Cassandra 5.0 mà không kiểm tra `release_version` và driver.

## 10. Chuẩn hóa dữ liệu khóa: byte giống nhau mới là ý định giống nhau

### 10.1. Chuỗi text/varchar và Unicode

Cassandra lưu `text`/`varchar` như Unicode UTF-8; nó **không tự chuẩn hóa**:

- `"Alice"` và `"alice"` là hai chuỗi khác nhau theo quy tắc so sánh thông thường.
- `"café"` NFC và `"café"` NFD có thể hiển thị giống nhau nhưng có byte khác nhau.
- Email có quy tắc local-part/domain; không được tự áp dụng `toLowerCase()` lên mọi email mà không định nghĩa chính sách nghiệp vụ.
- `ascii` chỉ phù hợp dữ liệu thực sự thuộc miền ASCII (mã quốc gia, protocol code...), không phù hợp họ tên có dấu.

Nếu yêu cầu truy vấn “tìm user theo tên đăng nhập không phân biệt chữ hoa/thường”, hãy lưu **canonical username key** theo quy tắc nhất quán ở mọi service:

~~~cql
CREATE TABLE users_by_username_key (
    username_key text PRIMARY KEY,
    user_id uuid,
    display_username text,
    created_at timestamp
);
~~~

`username_key` là khóa tra cứu, còn `display_username` giữ cách viết gốc để hiển thị. Cần quyết định normalization, case folding, loại ký tự hợp lệ, hạn mức độ dài và các lỗi Unicode khó nhìn thấy. Nếu namespace user yêu cầu **độc nhất**, cần dùng cơ chế ghi điều kiện/điều phối thích hợp, không chỉ dựa vào cách tạo UUID.

### 10.2. Số và thời gian trong khóa

- **Tiền tệ**: nên dùng `bigint` đơn vị nhỏ nhất hoặc `decimal` cho giá trị cần chính xác, nhưng **không lấy giá tiền làm ID giao dịch**; giá có thể đổi và không duy nhất.
- **`float`/`double`**: sai số biểu diễn, `NaN`/infinity, số `-0.0` và quy tắc so sánh khiến khóa khó kiểm soát; tránh làm khóa kinh doanh.
- **`timestamp`**: chỉ giữ **mili giây**, nên cần UUID/sequence phụ nếu dùng clustering cho sự kiện tần suất cao.
- **`date`**: có nghĩa ngày lịch, không chứa timezone; bucket ngày phải được tính theo UTC hoặc business timezone thống nhất.
- **`inet`**: đại diện một IP, không phải hostname, subnet/CIDR hay danh tính client; nhiều người dùng có thể dùng chung IP qua NAT/proxy.

Những kiểu được phép đặt trong khóa vẫn phải trải qua **validation miền dữ liệu** và kiểm thử tính ổn định khi serialize/deserialize qua các client Java khác nhau.

## 11. PRIMARY KEY, uniqueness và thao tác có điều kiện

Cassandra bảo đảm **một bộ giá trị PRIMARY KEY xác định vị trí row duy nhất trong một bảng**. Nhưng CQL `INSERT` bình thường có semantics **upsert**, không tự từ chối khóa đã tồn tại như một `UNIQUE` constraint trong SQL quan hệ.

Ví dụ:

~~~cql
INSERT INTO users_by_username_key (
    username_key, user_id, display_username, created_at
) VALUES (
    'nguyenha',
    44444444-4444-4444-8444-444444444444,
    'NguyenHa',
    '2026-11-21T08:00:00Z'
) IF NOT EXISTS;
~~~

`IF NOT EXISTS` là **lightweight transaction (LWT)** với cơ chế điều kiện ghi được Cassandra hỗ trợ. Nó hữu ích khi cần **chiếm một username key chưa có người sở hữu**. Ứng dụng phải kiểm tra cờ **`[applied]`** trong kết quả và xử lý trường hợp `false`, timeout hoặc ghi cạnh tranh.

**LWT không đồng nghĩa uniqueness toàn cluster của một cột thường.** Ví dụ, nếu một bảng `users_by_id` có `email text` là cột thường, `IF NOT EXISTS` trên `user_id` không tự ngăn một user khác dùng cùng email. Cần **đường tra cứu và giữ chỗ theo canonical email**, cộng một quy trình ghi/đối soát giữa các bảng.

Ngoài ra, `PRIMARY KEY` của Cassandra không tự cung cấp:

- `FOREIGN KEY` giữa hai bảng;
- `UNIQUE` trên cột thường bất kỳ;
- join tổng quát theo quan hệ như SQL;
- global sequence cấp số tăng liên tục;
- toàn bộ transaction ACID giữa nhiều partition/bảng.

Các ràng buộc nghiệp vụ khác phải được biểu diễn bằng **thiết kế bảng, validation ở ứng dụng, LWT khi cần và quy trình đồng bộ dữ liệu**.

## 12. Java Driver 4.x: bind đúng kiểu và giữ khóa ổn định khi retry

Với Java Driver 4.x, các kiểu khóa thường gặp được ánh xạ:

| CQL | Java | Setter khi bind | Getter khi đọc |
|---|---|---|---|
| `uuid`, `timeuuid` | `UUID` | `setUuid` | `getUuid` |
| `text`, `varchar`, `ascii` | `String` | `setString` | `getString` |
| `int`, `smallint`, `tinyint` | `int`, `short`, `byte` | `setInt`, `setShort`, `setByte` | `getInt`, `getShort`, `getByte` |
| `bigint` | `long` | `setLong` | `getLong` |
| `date` | `LocalDate` | `setLocalDate` | `getLocalDate` |
| `timestamp` | `Instant` | `setInstant` | `getInstant` |
| `time` | `LocalTime` | `setLocalTime` | `getLocalTime` |
| `inet` | `InetAddress` | `setInetAddress` | `getInetAddress` |
| `blob` | `ByteBuffer` | `setByteBuffer` | `getByteBuffer` |

### 12.1. Ghi vào bảng theo tenant/ngày

Giả sử `session` là một `CqlSession` đã cấu hình cluster và keyspace:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

// CqlSession session = ...; // Khởi tạo và quản lý ở ngoài ví dụ.

UUID tenantId = UUID.fromString("99999999-9999-4999-8999-999999999999");
UUID eventId = UUID.randomUUID(); // Sinh một lần cho một event.
Instant occurredAt = Instant.parse("2026-11-21T08:30:15.123Z");
LocalDate eventDay = occurredAt.atZone(ZoneOffset.UTC).toLocalDate();

PreparedStatement insert = session.prepare(
    "INSERT INTO api_events_by_tenant_day "
  + "(tenant_id, event_day, occurred_at, event_id, "
  + " response_code, service_name) "
  + "VALUES (?, ?, ?, ?, ?, ?)");

BoundStatement bound = insert.boundStatementBuilder()
    .setUuid(0, tenantId)
    .setLocalDate(1, eventDay)
    .setInstant(2, occurredAt)
    .setUuid(3, eventId)
    .setShort(4, (short) 200)
    .setString(5, "checkout")
    .build();

session.execute(bound);

// Nếu retry sau timeout, dùng lại cùng tenantId,
// eventDay, occurredAt và eventId.
~~~

Nếu ứng dụng **tạo UUID mới mỗi lần retry**, một event có thể được ghi thành hai row vì **primary key khác nhau**. Nếu ứng dụng tính lại bucket ngày từ `Instant.now()` tại mỗi lần thử, cùng event có thể rơi vào partition mới sau nửa đêm. Bởi vậy, hãy giữ nguyên **event envelope**, gồm khóa và dữ liệu nguồn, trong suốt vòng đời retry.

### 12.2. Đọc theo đúng khóa

~~~java
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

PreparedStatement find = session.prepare(
    "SELECT occurred_at, event_id, response_code "
  + "FROM api_events_by_tenant_day "
  + "WHERE tenant_id = ? AND event_day = ? "
  + "AND occurred_at = ? AND event_id = ?");

Row row = session.execute(
    find.bind(tenantId, eventDay, occurredAt, eventId)
).one();

if (row != null) {
    UUID storedEventId = row.getUuid("event_id");
    int status = row.getShort("response_code");
}
~~~

Bảng được partition theo cặp `tenant_id + event_day`, clustering theo `occurred_at + event_id`. Câu truy vấn biết tất cả thành phần nên nhắm đúng row. Nếu chỉ biết `eventId`, phải có **locator/bảng khác** được thiết kế cho đường truy cập đó.

### 12.3. Validate khóa trước khi bind

Ví dụ nguyên tắc:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

static void validateEventKey(
    UUID tenantId, LocalDate eventDay,
    Instant occurredAt, UUID eventId
) {
    Objects.requireNonNull(tenantId, "tenantId");
    Objects.requireNonNull(eventDay, "eventDay");
    Objects.requireNonNull(occurredAt, "occurredAt");
    Objects.requireNonNull(eventId, "eventId");
}
~~~

Không dùng `UNSET` để “bỏ qua” `tenant_id` hoặc `event_id` trong mutation. Với các cột thường không tham gia khóa, PATCH có thể dùng UNSET để giữ nguyên hoặc NULL để xóa; **quy tắc khóa không biến mất vì driver có API `unset()`**.

### 12.4. Khóa phải được mã hóa nhất quán ở mọi client

Nếu Java, Go và Python cùng ghi một keyspace:

- Thống nhất kiểu CQL và codec từ schema.
- Thống nhất normalization của `text`/email/username.
- Thống nhất mốc UTC và cách bucket từ `Instant`.
- Giữ số tiền, ID, chuỗi mã theo cùng miền dữ liệu.
- Với `blob` hoặc frozen type, kiểm soát byte/canonicalization.
- Kiểm thử duplicate key và retry trên nhiều phiên bản driver.

Một khóa “trông giống nhau” trong log không đảm bảo giá trị được serialize giống nhau nếu client dùng quy tắc chuẩn hóa khác hoặc có phiên bản dữ liệu khác.

## 13. Replication, consistency, compaction và repair: hệ quả của chọn kiểu khóa

### 13.1. Token và replication

Partition key được **mã hóa và băm** để tạo token; chiến lược replication xác định replica chịu trách nhiệm. Do đó, kiểu khóa và phân phối giá trị ảnh hưởng **số partition** và tải trên các token range.

- **Định danh UUID phân bố tốt** có thể giúp tránh nhiều giá trị va vào một partition, nhưng không bảo đảm mỗi tenant nhận tài nguyên ngang nhau.
- **Khóa boolean đơn** chỉ có vài giá trị, tạo rất ít partition và dễ hotspot.
- **Khóa text khổng lồ** tăng byte trong request, cache và so sánh; thường không cần thiết.
- **Khóa frozen collection** biến cả cấu trúc lớn thành ID, dễ gây kích thước key bất hợp lý.
- **Bucket theo ngày** giới hạn dữ liệu theo thời gian, nhưng một partition rất lớn vẫn có thể cần giờ/shard.

### 13.2. Clustering, tombstone và compaction

Clustering key tổ chức các row trong partition, giúp Cassandra đọc một lát cắt theo `WHERE` và `LIMIT`. Tuy nhiên, cùng một partition có thể chứa rất nhiều hàng, và TTL/xóa trên hàng/cột tạo tombstone cần được xử lý khi đọc.

**Compaction** gộp SSTable và dọn tombstone khi đủ điều kiện; nó **không sửa thiết kế khóa sai**. Nếu `partition_key = succeeded boolean` tạo hai partition khổng lồ, compaction không tự chia partition thành hàng nghìn nhóm nhỏ.

Đổi primary key thường là **migration sang bảng mới** với đường ghi/đọc và backfill rõ ràng, không phải một `ALTER TABLE` tùy tiện.

### 13.3. Repair và sai khác dữ liệu nghiệp vụ

**Repair** giúp replica hội tụ trạng thái các cell/mutation đã ghi. Nó không:

- Hợp nhất hai row có **event_id khác nhau** nhưng thực ra cùng một event do retry.
- Chuyển event bị bucket nhầm ngày từ partition này sang partition khác.
- Chuẩn hóa email Unicode đã được ghi thành hai giá trị key khác nhau.
- Đảm bảo một key định danh duy nhất giữa **hai bảng** tự đồng bộ.

Consistency level như `LOCAL_QUORUM` có thể cải thiện sự hiện diện của ghi/đọc dưới những giả định cụ thể về replication và lỗi, nhưng nó **không thay thế idempotency và ràng buộc khóa nghiệp vụ**.

### 13.4. Bảo mật và quyền truy cập

Một partition key như `tenant_id uuid` là **khóa truy vấn**, không phải hàng rào bảo mật tự động. Service phải xác minh người gọi có quyền truy cập tenant, không chỉ cho phép truyền UUID bất kỳ vào `WHERE`.

Nếu dùng email, số điện thoại hay địa chỉ IP làm khóa, cân nhắc rủi ro lộ **dữ liệu cá nhân** trong log, metrics, URL và trace. Có thể dùng ID surrogate và bảng lookup đã kiểm soát quyền; việc mã hóa/hashing cần thiết kế riêng để vẫn đáp ứng tra cứu và xóa dữ liệu đúng cách.

## 14. Migration khi phải thay kiểu hoặc thành phần khóa

Một bảng đã tồn tại và có dữ liệu thường **không thể được sửa đơn giản** từ `PRIMARY KEY (tenant_id, event_id)` sang `PRIMARY KEY ((tenant_id, event_day), event_id)`. Vị trí phân phối và tổ chức row đã thay đổi. Cũng vậy, việc đổi `event_id text` thành `uuid` trong primary key có thể thay toàn bộ biểu diễn byte và semantics.

Một quy trình migration an toàn:

1. **Khảo sát truy vấn thực tế**: query nào cần được phục vụ, cột nào đang dùng trong WHERE/ORDER BY?
2. **Thiết kế khóa mới**: chọn kiểu, canonicalization, partition bucket và clustering order.
3. **Tạo bảng mới** với schema rõ ràng; không sửa trực tiếp khóa của bảng cũ.
4. **Thêm luồng ghi tương thích**, ví dụ dual-write có ID ổn định và cơ chế đối soát.
5. **Backfill theo khóa đã biết** bằng công cụ có rate limit, checkpoint, retry, tránh quét/ghi bừa bãi trên cluster production.
6. **Kiểm tra số hàng, đối chiếu hash/nội dung và mẫu truy vấn**, gồm các trường hợp Unicode, timezone, trùng timestamp, vắng/null và late arrival.
7. **Chuyển đọc từng bước**, theo dõi latency, lỗi, độ đầy partition và số lượng dữ liệu thiếu.
8. **Dừng ghi bảng cũ và dọn dữ liệu** theo retention/backup/rollback plan sau khi xác minh.

**Không đổi kiểu khóa như một thao tác format**. Đổi `text` sang `uuid` hoặc một khóa số thực sang `bigint` có thể cần sửa ID của mọi row và tất cả bảng tham chiếu. Khi nguồn dữ liệu có nhiều writer, cần kiểm soát cửa sổ backfill và ghi song song.

## 15. Bảng lỗi thiết kế điển hình

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Nhầm `PRIMARY KEY (a,b)` với `PRIMARY KEY ((a,b))` | Phân bố token/đường truy vấn khác hoàn toàn | Xác định rõ partition và clustering trong DDL |
| Dùng `boolean` duy nhất làm partition key cho log lớn | Chỉ vài partition khổng lồ | Bucket theo tenant/thời gian/shard |
| Dùng timestamp đơn lẻ làm clustering key của event tần suất cao | Nhiều event cùng mili giây bị upsert lên một row | Thêm ID ổn định làm tie-breaker |
| Dùng UUID v4 làm clustering và mong thứ tự thời gian | Thứ tự không theo thời gian | `timeuuid` v1 hoặc `timestamp + uuid` |
| Dùng `counter` trong PRIMARY KEY | DDL bị từ chối | Counter là cột thường, khóa dùng scalar khác |
| Dùng `duration` trong PRIMARY KEY | Không có thứ tự tổng quát; DDL bị từ chối | Lưu duration là chính sách, due_at timestamp là key |
| Dùng non-frozen `map/list/set` làm key | Không phù hợp cấu trúc khóa | Frozen khi thực sự cần, thường chọn ID scalar |
| Dùng frozen UDT/collection lớn làm key | Key dễ đổi và có chi phí lớn | ID surrogate, UDT/collection làm value |
| Đưa `STATIC` vào primary key | DDL không hợp lệ | STATIC chỉ dành cho non-key column |
| Bind `NULL`/`UNSET` cho partition key | Không có khóa để định vị row | Validate khóa trước khi execute |
| Gọi `uuid()` hoặc `now()` lại ở mỗi retry INSERT | Có thể tạo row trùng nghiệp vụ | Tạo ID một lần và tái sử dụng |
| Dùng text key không canonicalize Unicode | Hai biểu diễn giống nhau thành hai khóa | NFC/case policy nhất quán |
| Dùng `float` làm định danh tiền/ID | Sai số/khó so sánh và normalize | Bigint/UUID/decimal với hợp đồng rõ |
| Truy vấn chỉ có `event_id` trên bảng partition theo tenant/day | Không định vị được partition | Tạo bảng/locator theo ID |
| Tin CL `LOCAL_QUORUM` đảm bảo duy nhất nhiều bảng | Dữ liệu denormalized vẫn có thể lệch | LWT đúng chỗ, idempotency, đối soát |
| Đổi kiểu khóa bằng `ALTER TABLE` trực tiếp | Không phù hợp storage/token layout | Bảng mới + backfill + cutover |

## 16. Bài tập thực hành

### Bài 1 — Đọc đúng PRIMARY KEY

Cho schema:

~~~cql
CREATE TABLE clicks (
    tenant_id uuid,
    click_day date,
    clicked_at timestamp,
    click_id uuid,
    PRIMARY KEY (tenant_id, click_day, clicked_at, click_id)
);
~~~

**Câu hỏi:** partition key là gì? Có phải tenant/ngày được bucket trong partition key không?

**Đáp án:** chỉ **`tenant_id`** là partition key; `click_day`, `clicked_at`, `click_id` là clustering columns. Nếu mục tiêu là bucket theo tenant/ngày, sửa thành `PRIMARY KEY ((tenant_id, click_day), clicked_at, click_id)`.

### Bài 2 — Kiểu nào không hợp lệ trong khóa?

Xem các khai báo rút gọn:

~~~cql
-- A: Không hợp lệ
-- CREATE TABLE a (k duration PRIMARY KEY, value text);

-- B: Không hợp lệ
-- CREATE TABLE b (k counter PRIMARY KEY);

-- C: Khả năng CQL, cần cân nhắc thiết kế
-- CREATE TABLE c (k frozen<set<text>> PRIMARY KEY, value text);

-- D: Thông dụng và phù hợp cho tra ID
CREATE TABLE d (
    k uuid PRIMARY KEY,
    value text
);
~~~

**Đáp án:** A và B bị cấm theo quy tắc kiểu; C có thể được chấp nhận vì frozen collection, nhưng thường không nên dùng làm định danh nghiệp vụ; D là một lựa chọn phổ biến.

### Bài 3 — Trùng timestamp

Một bảng có `PRIMARY KEY ((device_id, day), occurred_at)` và hai sự kiện cùng một thiết bị/ngày có `occurred_at` bằng nhau đến mili giây.

**Hỏi:** Cassandra có lưu hai row riêng không?

**Đáp án:** không, vì chúng có cùng toàn bộ primary key; các mutation có thể upsert/cập nhật lên một row. Thêm `event_id uuid` làm clustering key phụ, hoặc dùng thiết kế thứ tự nguồn phù hợp.

### Bài 4 — Truy vấn sai đường truy cập

Bảng `api_events_by_tenant_day` có `PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)`.

**Hỏi:** câu `SELECT * FROM ... WHERE event_id = ?` có tối ưu không?

**Đáp án:** không. Thiếu **toàn bộ partition key**, và `event_id` là clustering column sau `occurred_at`. Cần lookup/bảng theo `event_id`, hoặc biết đủ khóa để truy vấn row.

### Bài 5 — Cardinality và hotspot

Một ứng dụng dùng `client_ip inet` làm partition key đơn trong bảng lưu tất cả request. Hầu hết người dùng đi qua một reverse proxy chung.

**Hỏi:** vì sao kiểu `inet` vẫn không làm mô hình phân phối tốt?

**Đáp án:** kiểu hợp lệ không tạo nhiều giá trị partition key mới; cùng IP proxy/NAT có thể gom lượng request rất lớn vào một partition. Cần khóa theo tenant/service/bucket và/hoặc shard phù hợp với truy vấn. IP nguồn còn phải được lấy từ chuỗi proxy đáng tin.

### Bài 6 — Đổi ngày bucket và retry

Worker ghi event lúc `2026-11-20T18:30:00Z` với `event_day` theo UTC, nhưng retry sau nửa đêm giờ Việt Nam lại dùng `LocalDate.now()`.

**Hỏi:** có thể xảy ra gì?

**Đáp án:** cùng event có thể được ghi vào partition ngày khác nhau, tạo duplicate hoặc không tìm được khi truy vấn. Bucket phải được tính một lần từ **thời điểm nguồn đã chọn** và timezone quy ước; giữ nguyên ID và khóa qua retry.

### Bài 7 — Thiết kế username duy nhất

Một bảng `users_by_id(user_id uuid PRIMARY KEY, username text)` có đảm bảo không hai user trùng `username` không?

**Đáp án:** không. Khóa unique là `user_id`. Muốn chiếm tên duy nhất, dùng canonical `username_key` trong bảng tra theo tên và cơ chế ghi điều kiện/điều phối để giữ chỗ, rồi đồng bộ với bảng theo ID.

## 17. Checklist review kiểu dữ liệu trong khóa

- [ ] Đã phân biệt **partition key** và **clustering columns**, đặc biệt dấu ngoặc của composite partition key?
- [ ] Kiểu của mỗi thành phần khóa được **phiên bản Cassandra thực tế** hỗ trợ?
- [ ] Không đưa **counter**, **duration**, non-frozen collection hoặc `STATIC` vào PRIMARY KEY?
- [ ] Nếu dùng frozen collection/UDT/tuple, đã kiểm tra toàn bộ kiểu con, kích thước và lý do cần khóa phức hợp?
- [ ] Có bảo đảm mọi thành phần khóa không NULL/UNSET khi ghi, không dùng giá trị “unknown” tùy tiện?
- [ ] Giá trị khóa được sinh/chuẩn hóa **một lần và ổn định** qua retry?
- [ ] Partition key có **cardinality và phân phối tải** phù hợp; không có boolean/status/IP proxy gây hotspot?
- [ ] Đã đo số row/bytes trên mỗi partition, throughput và retention để chọn bucket/shard?
- [ ] Các truy vấn quan trọng biết đủ partition key và dùng clustering prefix/range hợp lệ?
- [ ] Clustering columns sắp theo đúng ngữ nghĩa: thời điểm nguồn, timeuuid hay sequence?
- [ ] Có tie-breaker khi timestamp không đủ phân biệt nhiều sự kiện cùng mili giây?
- [ ] Chuỗi text, email, username, Unicode và địa chỉ IP có **canonicalization** nhất quán?
- [ ] Tránh float/double làm định danh hoặc tiền; có hợp đồng đơn vị rõ ràng?
- [ ] Với yêu cầu uniqueness trên cột thường, đã thiết kế bảng/LWT/đối soát thay vì tin PRIMARY KEY khác?
- [ ] Java Driver bind đúng kiểu và có validation khóa trước khi execute?
- [ ] Có kế hoạch migration nếu đổi primary key/type: bảng mới, backfill, dual-write, cutover?
- [ ] Đã xem xét replication, consistency, tombstone, compaction, repair và quản lý dữ liệu cá nhân?

## Tài liệu tham khảo

- [Apache Cassandra — Data Definition: Primary key, partition và clustering columns](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/ddl.html).
- [Apache Cassandra — CREATE TABLE: ràng buộc PRIMARY KEY và frozen collections](https://cassandra.apache.org/doc/latest/cassandra/reference/cql-commands/create-table.html).
- [Apache Cassandra — CQL Data Types: counter, duration, collections, UDT, tuple](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/types.html).
- [Apache Cassandra — Vector data type (Cassandra 5.0)](https://cassandra.apache.org/doc/latest/cassandra/reference/vector-data-type.html).
- [Apache Cassandra Java Driver 4.x — Prepared Statements](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/).

**Ghi nhớ:** một kiểu CQL “hợp lệ” **chưa chắc là một kiểu khóa tốt**. `PRIMARY KEY` quyết định **định danh row**, **partition key** quyết định **phân phối token/replica**, còn **clustering columns** quyết định **thứ tự trong partition**. `counter` và `duration` không được làm khóa; non-frozen collection không thích hợp làm khóa, còn frozen collection/UDT có những khả năng nhưng phải được cân nhắc kỹ. Thiết kế bền vững là chọn **khóa nhỏ, ổn định, chuẩn hóa được, đúng đường truy vấn**, kiểm soát retry và đo tải thật trên hệ Cassandra phân tán.

