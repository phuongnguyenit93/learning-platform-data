# uuid, timeuuid và yêu cầu về định danh hoặc thứ tự trong Apache Cassandra

Trong **Apache Cassandra**, `uuid` và `timeuuid` đều là kiểu định danh 128 bit, nhưng chúng phục vụ hai mục tiêu khác nhau. `uuid` biểu diễn **một định danh UUID**; `timeuuid` biểu diễn **UUID phiên bản 1 (v1)** có thành phần thời gian và được Cassandra so sánh theo thứ tự thời gian khi dùng làm *clustering column*. Chọn kiểu theo câu hỏi nghiệp vụ: cần nhận diện một thực thể ổn định, hay cần vừa phân biệt sự kiện vừa lấy các sự kiện theo thứ tự tạo ID?

Bài này thuộc chương **Kiểu dữ liệu** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Kiến thức được đặt trong mô hình wide-column phân tán: **partition key** quyết định nơi phân phối dòng, **clustering columns** quyết định thứ tự *bên trong phân vùng*. Ví dụ CQL và Java Driver cho thấy lựa chọn UUID liên quan như thế nào đến thiết kế bảng theo truy vấn, retry sau timeout, mức nhất quán đọc/ghi, replication, compaction và repair.

## 1. Phân biệt định danh với thứ tự thời gian

Một bài toán thường đặt ra hai yêu cầu:

1. **Định danh:** mỗi khách hàng hoặc giao dịch có ID ổn định để tra cứu, cập nhật, chống tạo trùng khi retry.
2. **Thứ tự:** trong cùng một khách hàng, lấy 100 sự kiện mới nhất hoặc các sự kiện nằm trong một khoảng thời gian.

Hai yêu cầu không nhất thiết phải dùng cùng một cột. Một ID ngẫu nhiên thích hợp để nhận diện, còn một cột `timestamp` có thể phù hợp hơn để sắp theo **thời điểm thực sự xảy ra sự kiện**. `timeuuid` hữu ích khi ID được sinh vào đúng thời điểm cần sắp thứ tự và việc sử dụng khóa thời gian nằm trong phạm vi chấp nhận được.

| Tiêu chí | `uuid` | `timeuuid` |
|---|---|---|
| Kích thước | 128 bit (16 byte) | 128 bit (16 byte) |
| Ý nghĩa | Định danh UUID nói chung | UUID **v1** dựa trên thời gian |
| CQL tạo giá trị | `uuid()` sinh UUID v4 ngẫu nhiên | `now()` sinh UUID v1 dựa trên thời gian tại coordinator |
| Java tạo phổ biến | `UUID.randomUUID()` (v4) | `Uuids.timeBased()` trong Java Driver 4.x (v1) |
| Java đọc/ghi | `UUID`, `getUuid`/`setUuid` | Cũng là `UUID`, `getUuid`/`setUuid` |
| Vai trò phù hợp | ID tài khoản, đơn hàng, thực thể, khóa tra cứu | Clustering key cho timeline/sự kiện theo thời gian sinh ID |
| Thứ tự theo thời gian | **Không bảo đảm**, nhất là UUID v4 | Cassandra so sánh theo thành phần thời gian của UUID v1 |
| Có thể suy ra thời điểm tạo? | Không phải tính chất chung của mọi UUID | Có thể chuyển thành timestamp với độ phân giải phù hợp |
| Điểm cần tránh | Nghĩ UUID ngẫu nhiên sẽ tự tạo thứ tự thời gian | Coi thời điểm sinh ID bằng thời điểm xảy ra sự kiện ở nguồn |

**Lưu ý:** UUID là *định danh*, không phải “mã tăng dần toàn cluster” hoặc cơ chế phân quyền. Việc một ID khó đoán không thay thế xác thực và kiểm tra quyền truy cập.

## 2. Cấu trúc UUID và các phiên bản quan trọng

### 2.1. Cách đọc một UUID

UUID thường được hiển thị dưới dạng 36 ký tự: 32 chữ số hệ 16 và 4 dấu gạch ngang, theo dạng `8-4-4-4-12`.

Ví dụ:

~~~text
550e8400-e29b-41d4-a716-446655440000
             ^
             4 -> version 4, UUID ngẫu nhiên
~~~

Chuỗi trên chỉ là cách **hiển thị** của một giá trị nhị phân 16 byte. Nếu dùng cột CQL `uuid`/`timeuuid`, Cassandra lưu giá trị theo kiểu UUID, thay vì mặc định coi nó là `text` dài 36 ký tự.

Trong Java:

~~~java
import java.util.UUID;

UUID id = UUID.fromString("550e8400-e29b-41d4-a716-446655440000");

System.out.println(id.version());  // 4
System.out.println(id.toString()); // dạng 8-4-4-4-12

UUID anotherId = UUID.randomUUID();
System.out.println(anotherId.version()); // 4
~~~

`UUID.randomUUID()` của Java tạo **UUID v4**; nó thích hợp cho cột CQL `uuid`. Không dùng nó trực tiếp để ghi vào cột `timeuuid` vì `timeuuid` yêu cầu dạng UUID v1.

### 2.2. UUID v1 trong timeuuid

UUID **phiên bản 1** chứa thành phần thời gian, **clock sequence** và thành phần nhận diện node. Dấu thời gian được mã hóa theo số đơn vị **100 nano giây tính từ ngày 15/10/1582**, khác với Unix epoch bắt đầu năm 1970. Thành phần node của một UUID v1 có thể được sinh từ thông tin mạng hoặc được thay thế bằng thuật toán riêng của thư viện; **không** dùng nó làm danh tính máy chủ đáng tin cậy.

Ví dụ một UUID v1:

~~~text
f47ac10b-58cc-11cf-a447-001122334455
             ^
             1 -> version 1
~~~

Dấu thời gian nhúng trong UUID v1 cho phép so sánh thứ tự thời gian **theo thời điểm sinh ID**. Tuy nhiên:

- Độ phân giải 100 ns của **trường timestamp** không chứng minh độ chính xác 100 ns của đồng hồ thực hoặc dữ liệu đo.
- Đồng hồ giữa các host có thể lệch nhau; lịch sử sự kiện toàn cluster không tự hình thành một thứ tự tuyệt đối đúng với nghiệp vụ.
- Nếu sự kiện xảy ra lúc 09:00 nhưng đến hệ thống lúc 09:10, ID sinh lúc ingest thường mang thời gian **09:10**, không phải 09:00.
- Một UUID v1 không chứng minh nó được tạo bởi host nào, người dùng nào, hoặc nguồn nào đáng tin.

### 2.3. Các UUID khác

UUID v4 dùng dữ liệu ngẫu nhiên; UUID v3/v5 dựa trên tên và namespace; các phiên bản UUID mới hơn cũng tồn tại trong hệ sinh thái. Nhưng với **Cassandra CQL `timeuuid`**, hãy sử dụng **UUID v1** theo hợp đồng kiểu. Đừng giả định UUID có timestamp theo các chuẩn khác, chẳng hạn UUID v7, có thể đưa thẳng vào `timeuuid` hoặc sẽ được Cassandra sắp xếp giống v1.

Nếu một hệ thống ngoài cấp UUID khác phiên bản, có thể cần lưu ở **`uuid`** và có một cột **`timestamp`** riêng để đáp ứng truy vấn theo thời gian; kiểm tra khả năng tương thích của driver và cluster khi đưa dữ liệu từ bên ngoài vào.

## 3. Hàm CQL để tạo UUID và timeuuid

Cassandra cung cấp các hàm dựng sẵn thường gặp:

| Hàm CQL | Trả về | Mục đích |
|---|---|---|
| `uuid()` | `uuid` v4 ngẫu nhiên | Tạo ID mới cho thực thể |
| `now()` | `timeuuid` v1 | Tạo ID sự kiện tại thời điểm lệnh được thực thi |
| `current_timeuuid()` | `timeuuid` | Tên tương đương với `now()` trong tài liệu CQL hiện hành |
| `min_timeuuid(t)` | timeuuid *sentinel* nhỏ nhất tại `t` | Cận dưới khi lọc theo khoảng thời gian |
| `max_timeuuid(t)` | timeuuid *sentinel* lớn nhất tại `t` | Cận trên khi lọc theo khoảng thời gian |
| `to_timestamp(timeuuid)` | `timestamp` | Trích thời điểm nhúng trong timeuuid, với độ phân giải timestamp |
| `to_unix_timestamp(timeuuid)` | `bigint` | Trích thời điểm dưới dạng mili giây Unix |

Tên hàm có thể được viết theo các dạng tương ứng ở những tài liệu/phiên bản CQL khác nhau, ví dụ **`minTimeuuid`**/`maxTimeuuid` hoặc **`min_timeuuid`**/`max_timeuuid`. Ví dụ trong bài dùng dạng có gạch dưới theo tài liệu CQL hiện hành; hãy kiểm tra cú pháp của phiên bản Cassandra đang triển khai.

Ví dụ tạo một thực thể bằng UUID ngẫu nhiên:

~~~cql
CREATE TABLE accounts_by_id (
    account_id uuid PRIMARY KEY,
    account_name text,
    created_at timestamp
);

INSERT INTO accounts_by_id (account_id, account_name, created_at)
VALUES (uuid(), 'Khách hàng thử nghiệm', '2026-11-21T00:00:00Z');
~~~

Mỗi lần thực hiện `uuid()` sẽ sinh một ID mới. Nếu lệnh này bị timeout rồi ứng dụng chạy lại nguyên văn, **có thể tạo hai hàng** thay vì ghi lại cùng một hàng. Với đường ghi cần idempotency, ứng dụng nên tạo ID **một lần**, ghi nhớ ID đó và truyền cùng ID khi retry.

Hàm `now()` cũng tạo một timeuuid mới trên coordinator khi thực thi. Không viết:

~~~cql
-- Không phải cách tìm bản ghi đã được tạo bằng now():
SELECT * FROM some_events WHERE event_id = now();
~~~

Hàm này sinh một UUID mới tại lúc truy vấn, nên gần như chắc chắn không trùng với ID của bản ghi cũ. Để tìm một bản ghi đã biết, truyền **ID đã được lưu**; để truy vấn theo thời gian, dùng **các mốc thời gian** hoặc **các khóa timeuuid giới hạn**.

## 4. uuid là khóa định danh tốt, nhưng không phải khóa sắp xếp thời gian

Giả sử ứng dụng cần “lấy thông tin khách hàng bằng ID”. Bảng đơn giản:

~~~cql
CREATE TABLE customers_by_id (
    customer_id uuid PRIMARY KEY,
    full_name text,
    registered_at timestamp,
    status text
);
~~~

`customer_id` là **partition key**. Cassandra băm giá trị khóa qua partitioner để phân phối dữ liệu và replica; vì vậy những UUID có ký tự đầu gần nhau hoặc được tạo gần nhau **không nhất thiết nằm cạnh nhau trên cluster**.

Một bảng `customers_by_id` với UUID làm khóa rất phù hợp cho truy vấn chính xác:

~~~cql
SELECT full_name, registered_at, status
FROM customers_by_id
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
~~~

Nhưng nếu cần “50 khách hàng mới đăng ký” hoặc “khách hàng đăng ký trong tuần”, chỉ chọn `uuid` làm partition key không phục vụ trực tiếp truy vấn này. Cần thêm **một đường truy cập theo thời gian**, ví dụ bảng phân vùng theo một bucket thời gian và có clustering columns.

**Không có AUTO_INCREMENT toàn cluster** cho khóa UUID. Cassandra là hệ phân tán; việc cấp ID tăng tuần tự chung có thể tạo điểm điều phối/điểm nghẽn nếu thiết kế không cẩn thận. UUID thường thuận tiện vì các tiến trình có thể sinh ID mà không cần xin số thứ tự từ một bộ cấp phát trung tâm.

Với mã nghiệp vụ như `"000041"`, mã tài khoản từ hệ ngoài hoặc số điện thoại, kiểu **`text`** có thể phù hợp hơn UUID. Không đổi chuỗi bất kỳ thành UUID nếu hợp đồng dữ liệu không xác định đó là UUID hợp lệ.

## 5. timeuuid làm clustering key cho timeline

Xét yêu cầu: **“Lấy 100 sự kiện ghi nhận gần nhất của một tài khoản trong một ngày, và có thể đọc sự kiện trong một khoảng thời gian sinh ID.”**

Một bảng thiết kế theo truy vấn:

~~~cql
CREATE TABLE events_by_account_day (
    account_id uuid,
    event_day date,
    event_id timeuuid,
    occurred_at timestamp,
    event_type text,
    payload text,
    PRIMARY KEY ((account_id, event_day), event_id)
) WITH CLUSTERING ORDER BY (event_id DESC);
~~~

Ý nghĩa:

- **`(account_id, event_day)`** là partition key tổng hợp. Nó xác định một phân vùng sự kiện của tài khoản trong ngày; nếu quá nhiều sự kiện/ngày cần xem xét bucket nhỏ hơn.
- **`event_id timeuuid`** là clustering key. Cassandra sắp xếp các hàng **trong cùng phân vùng** theo thời gian nhúng trong UUID v1, ở đây theo hướng giảm dần.
- **`occurred_at timestamp`** là thời điểm sự kiện xảy ra **theo nguồn nghiệp vụ**. Nó có thể khác thời điểm tạo timeuuid.
- **`event_type`, `payload`** là cột nội dung; không giúp tự động truy vấn mọi sự kiện có cùng `event_type` trên toàn cluster.

Câu truy vấn đúng mẫu:

~~~cql
SELECT event_id, occurred_at, event_type, payload
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 100;
~~~

Do `CLUSTERING ORDER BY (event_id DESC)`, truy vấn trả về các sự kiện gần nhất **theo thời gian nhúng trong timeuuid**, không phải theo `occurred_at` nếu hai thời gian khác nhau.

Để minh họa sinh sự kiện ngay trong CQL, có thể dùng:

~~~cql
-- Ví dụ khi chạy trong đúng ngày 2026-11-21 (UTC).
INSERT INTO events_by_account_day (
    account_id, event_day, event_id, occurred_at, event_type, payload
) VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21',
    now(),
    '2026-11-21T02:15:00Z',
    'LOGIN',
    'Truy cập thành công'
);
~~~

Dòng này chỉ minh họa cú pháp. Trong vận hành, **không nên sử dụng trực tiếp `now()` trong mỗi lần retry cùng một sự kiện**, vì ID sẽ khác. Cũng cần tạo `event_day` theo cùng quy ước timezone và thời điểm đã chọn để phân bucket; ngày cố định trong ví dụ không phù hợp để chạy lại vào các ngày khác.

### 5.1. Tác động của phân vùng và thứ tự

Cassandra không sắp xếp **toàn cluster** theo `event_id`. Nó chỉ sắp các clustering values trong **từng partition**. Truy vấn “100 sự kiện mới nhất của tất cả tài khoản” không thể được thực hiện hiệu quả chỉ bằng bảng `events_by_account_day`.

Nếu muốn lấy nhiều ngày liên tiếp, cần truy vấn các partition theo ngày rồi kết hợp kết quả ở ứng dụng, hoặc thiết kế bảng/bucket khác phù hợp. Truy vấn theo ngày hoặc từng tài khoản có thể rất hiệu quả, nhưng partition tăng vô hạn vẫn gây áp lực SSTable, tombstone, compaction và repair.

**Đừng chọn `event_day` bằng một timezone ở lúc ghi và timezone khác khi đọc.** Ví dụ, một sự kiện 00:30 sáng giờ Việt Nam vẫn là ngày hôm trước theo UTC. Cần ghi rõ partition bucket là ngày UTC hay ngày địa phương của khách hàng, và dùng đúng quy tắc trong mọi dịch vụ Java.

## 6. Truy vấn timeuuid theo khoảng thời gian

Các hàm **`min_timeuuid`** và **`max_timeuuid`** tạo giá trị ranh giới cho so sánh với cột `timeuuid`; chúng **không phải ID sự kiện thật**. Chỉ dùng các giá trị đó làm **sentinel để truy vấn**, không dùng để INSERT làm khóa.

Ví dụ lấy các sự kiện có thời điểm sinh ID trong khoảng **[01:00, 02:00) UTC** ngày 21/11/2026:

~~~cql
SELECT event_id, event_type, occurred_at
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
  AND event_id >= min_timeuuid('2026-11-21T01:00:00Z')
  AND event_id <  min_timeuuid('2026-11-21T02:00:00Z')
LIMIT 100;
~~~

Ở đây khoảng **nửa mở** `[start, end)` có ý nghĩa:

- Bao gồm mọi timeuuid có thời gian từ `01:00:00Z` trở đi.
- Loại trừ mọi timeuuid có thời gian từ `02:00:00Z` trở đi.
- Không bị nhập nhằng giữa các khoảng sát nhau khi phân tích theo giờ.

Khi muốn lấy sự kiện **sau** một thời điểm (loại trừ toàn bộ những UUID được tạo đúng tại thời điểm đó), có thể dùng cận `> max_timeuuid(start)`. Khi muốn lấy **đến hết** một thời điểm theo độ phân giải của mốc nhập, cần cân nhắc cận trên tương ứng. Tránh ghép dấu so sánh và hàm ranh giới theo trực giác mà không kiểm tra ý nghĩa inclusive/exclusive ở timestamp biên.

Không nên dùng:

~~~cql
-- KHÔNG dùng sentinel làm ID bản ghi thật:
-- INSERT INTO events_by_account_day (..., event_id, ...) VALUES (..., min_timeuuid(...), ...);
~~~

Vì các sentinel không tuân theo cách sinh ID v1 thông thường và **không bảo đảm duy nhất**. Đây là điểm rất quan trọng khi retry: sentinel có thể tạo trùng khóa hoặc ghi đè dữ liệu.

Ngoài ra, hàm chuyển đổi thời gian có ích khi trình bày kết quả:

~~~cql
SELECT event_id, to_timestamp(event_id) AS id_generated_at,
       occurred_at, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

`to_timestamp(event_id)` trả về thời điểm dựa trên ID với độ phân giải **mili giây** của kiểu CQL `timestamp`. Dấu thời gian trong UUID v1 có đơn vị 100 ns, nhưng **không nên suy ra độ chính xác đồng hồ hoặc thời gian sự kiện đến 100 ns** từ phép chuyển đổi này.

### 6.1. Có cần lưu thêm occurred_at?

Có, nếu nghiệp vụ phân biệt:

- **Occurred at:** thời điểm máy nguồn ghi nhận sự kiện.
- **Recorded at:** thời điểm hệ thống lưu nhận/ghi log.
- **Generated at:** thời điểm tạo timeuuid.
- **Cassandra write timestamp:** metadata để giải quyết xung đột last-write-wins (theo micro giây), **khác với CQL `timestamp`** và thành phần thời gian của UUID.

Một timeuuid tạo tại lúc ingest không thay thế được `occurred_at` khi sự kiện có thể đến trễ, được backfill hoặc có clock skew. Nếu muốn sắp xếp theo thời điểm xảy ra sự kiện, xem thiết kế với `timestamp + uuid` ở phần tiếp theo.

## 7. Phương án thay thế: timestamp + uuid cho thứ tự sự kiện nghiệp vụ

Khi hệ thống cần hiển thị **theo thời điểm xảy ra ở nguồn**, không nên mặc định dùng timeuuid tạo tại lúc nhận sự kiện. Có thể dùng một clustering key kép:

~~~cql
CREATE TABLE source_events_by_account_day (
    account_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY ((account_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

Vì sao có **hai clustering columns**?

1. `occurred_at timestamp` tạo thứ tự chính theo thời điểm xảy ra theo dữ liệu nguồn.
2. `event_id uuid` làm khóa phụ để hai sự kiện cùng thời điểm mili giây vẫn được lưu thành **hai hàng khác nhau**, miễn ID khác nhau.

Nếu chỉ chọn `occurred_at` làm khóa clustering, hai sự kiện của cùng partition cùng timestamp có thể có **cùng primary key** và ghi đè một hàng. Cột `event_id` ngăn tình huống này.

~~~cql
SELECT occurred_at, event_id, event_type
FROM source_events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T01:00:00Z'
  AND occurred_at <  '2026-11-21T02:00:00Z'
LIMIT 100;
~~~

Cách này biểu đạt rõ **thứ tự nghiệp vụ**, nhưng vẫn cần kiểm tra chất lượng `occurred_at` từ nguồn: đồng hồ thiết bị sai hoặc nhận dữ liệu quá muộn vẫn có thể gây lệch thứ tự mong muốn.

| Yêu cầu | Thiết kế khởi đầu |
|---|---|
| Tìm đúng khách hàng/giao dịch theo ID | `uuid` làm partition key |
| Timeline theo thời điểm **sinh ID** | `timeuuid` làm clustering key |
| Timeline theo thời điểm **xảy ra ở nguồn** | `timestamp` + `uuid` làm clustering columns |
| Định danh từ hệ ngoài không theo định dạng UUID | `text` hoặc kiểu phù hợp với hợp đồng ngoài |
| Cần thứ tự tuyệt đối/sequence đúng trên mọi writer | Cơ chế cấp thứ tự riêng hoặc mô hình điều phối; UUID/timeuuid **không tự bảo đảm** |
| Cần tìm toàn hệ thống theo ID ở một bảng timeline được bucket theo tài khoản | Thêm đường tra cứu theo ID/bảng theo truy vấn nếu cần |

## 8. Java Driver 4.x: tạo và ghi UUID đúng kiểu

Trong Java Driver 4.x, `uuid` và `timeuuid` cùng ánh xạ sang Java **`java.util.UUID`**. Các phương thức thường dùng là:

- `BoundStatementBuilder.setUuid(index, value)` để bind.
- `Row.getUuid("column_name")` để đọc.
- `Uuids.timeBased()` từ `com.datastax.oss.driver.api.core.uuid.Uuids` để tạo **UUID v1** phù hợp `timeuuid`.
- `Uuids.unixTimestamp(id)` để chuyển thành **mili giây Unix**, nếu ID là UUID v1.

### 8.1. Sinh một lần và giữ nguyên khi retry

Đây là ví dụ ghi vào bảng `events_by_account_day`. Giả sử `session` là một `CqlSession` đã cấu hình keyspace và kết nối tới Cassandra:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.uuid.Uuids;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

// CqlSession session = ...; // Khởi tạo bên ngoài ví dụ.

UUID accountId = UUID.fromString("11111111-1111-4111-8111-111111111111");
UUID eventId = Uuids.timeBased(); // Sinh một lần cho một sự kiện.
if (eventId.version() != 1) {
    throw new IllegalStateException("eventId phải là UUID version 1");
}

// Bucket theo thời gian sinh eventId, thống nhất timezone UTC.
Instant generatedAt = Instant.ofEpochMilli(Uuids.unixTimestamp(eventId));
LocalDate eventDay = generatedAt.atZone(ZoneOffset.UTC).toLocalDate();

// Thời gian nguồn nếu có thể khác generatedAt:
Instant occurredAt = generatedAt;

PreparedStatement insert = session.prepare(
    "INSERT INTO events_by_account_day "
  + "(account_id, event_day, event_id, occurred_at, event_type, payload) "
  + "VALUES (?, ?, ?, ?, ?, ?)");

BoundStatement statement = insert.boundStatementBuilder()
    .setUuid(0, accountId)
    .setLocalDate(1, eventDay)
    .setUuid(2, eventId)
    .setInstant(3, occurredAt)
    .setString(4, "LOGIN")
    .setString(5, "Truy cập thành công")
    .build();

session.execute(statement);

// Nếu retry sau timeout, dùng lại CHÍNH statement hoặc ID/bucket ở trên.
~~~

**Quy tắc quan trọng:** ID và bucket phải có mặt trong envelope/đơn vị công việc ổn định khi retry. Nếu sau timeout tiến trình sinh lại timeuuid rồi ghi, Cassandra sẽ coi đây là **hàng khác** vì clustering key đã thay đổi. Nếu sự kiện phải tồn tại qua việc restart, ID cần được lưu cùng dữ liệu sự kiện hoặc có cách khôi phục từ nguồn đáng tin.

`Uuids.timeBased()` tạo ID theo thời điểm **ứng dụng Java** gọi hàm. Nếu dùng `now()` bên CQL, thời điểm sinh thuộc về **coordinator** xử lý lệnh. Chênh lệch đồng hồ giữa client và node ảnh hưởng mốc thời gian được nhúng; hãy chọn một nơi sinh ID có chủ đích và theo dõi đồng bộ thời gian.

### 8.2. Tra cứu chính xác bằng ID

~~~java
import com.datastax.oss.driver.api.core.cql.Row;

PreparedStatement find = session.prepare(
    "SELECT event_id, occurred_at, event_type "
  + "FROM events_by_account_day "
  + "WHERE account_id = ? AND event_day = ? AND event_id = ?");

Row row = session.execute(
    find.bind(accountId, eventDay, eventId)
).one();

if (row != null) {
    UUID storedId = row.getUuid("event_id");
    Instant sourceTime = row.getInstant("occurred_at");
}
~~~

Truy vấn có đủ **partition key** và clustering key, nên Cassandra có thể đọc đúng hàng. Truy vấn chỉ biết `event_id` nhưng **không biết accountId/eventDay** sẽ không được phục vụ tốt bởi chính bảng này. Nếu ID phải tra cứu toàn hệ thống, cân nhắc thêm bảng `events_by_id` hoặc mapping `event_id -> partition key` theo nhu cầu, kèm cơ chế giữ đồng nhất giữa các bảng.

### 8.3. Truy vấn theo khoảng thời gian từ Java

Java Driver có các hàm **`Uuids.startOf(epochMillis)`** và **`Uuids.endOf(epochMillis)`** trả về UUID **giả dùng làm ranh giới truy vấn**, không phải event ID thật.

~~~java
import com.datastax.oss.driver.api.core.uuid.Uuids;
import java.time.Instant;
import java.util.UUID;

Instant from = Instant.parse("2026-11-21T01:00:00Z");
Instant until = Instant.parse("2026-11-21T02:00:00Z");

// Chỉ để bind vào điều kiện so sánh trong SELECT:
UUID lowerBound = Uuids.startOf(from.toEpochMilli());
UUID exclusiveUpperBound = Uuids.startOf(until.toEpochMilli());

PreparedStatement range = session.prepare(
    "SELECT event_id, occurred_at, event_type "
  + "FROM events_by_account_day "
  + "WHERE account_id = ? AND event_day = ? "
  + "AND event_id >= ? AND event_id < ? LIMIT 100");

for (Row event : session.execute(
    range.bind(accountId, LocalDate.parse("2026-11-21"),
               lowerBound, exclusiveUpperBound)
)) {
    UUID id = event.getUuid("event_id");
    // Xử lý kết quả theo thứ tự timeuuid của Cassandra.
}
~~~

Các sentinel được tạo từ **Unix milliseconds**; không truyền `UUID.timestamp()` trực tiếp vì giá trị đó là số đơn vị 100 ns tính từ mốc 1582. Nếu cần lấy Unix milliseconds từ một UUID v1, dùng `Uuids.unixTimestamp(id)`.

Cũng không dùng `UUID.compareTo()` trên client để giả định nó cho đúng **thứ tự timeuuid của Cassandra**; cách so sánh của `java.util.UUID` không tương đương với comparator `timeuuid` của Cassandra trong mọi trường hợp. Khi cần thứ tự đọc theo Cassandra, tận dụng clustering order trong truy vấn.

## 9. Vận hành phân tán: clock skew, tính nhất quán và idempotency

### 9.1. Timeuuid không phải đồng hồ toàn cluster

Hai node độc lập có thể sinh các UUID v1 có timestamp dựa trên đồng hồ không hoàn toàn đồng bộ. Kết quả sắp theo timeuuid phản ánh **thời gian nhúng trong ID**, không nhất thiết là thứ tự xảy ra hoặc thứ tự hoàn tất ghi của sự kiện trong đời thực.

Cần xem xét:

- **Clock skew:** đồng bộ thời gian của host bằng cơ chế chuẩn, theo dõi lệch đồng hồ.
- **Nguồn thời gian:** timeuuid do Java client sinh có thể lệch thời gian của coordinator; timeuuid do `now()` sinh có thể lệch nguồn sự kiện.
- **Late arrival/backfill:** dữ liệu cũ nhưng nhận muộn có thể nằm ở vị trí không mong muốn nếu ID tạo lúc ingest.
- **Tie-breaker:** nhiều UUID v1 cùng thời gian vẫn có thành phần khác để phân biệt, nhưng không tạo “thứ tự nhân quả” trong hệ phân tán.

Nếu nghiệp vụ yêu cầu **thứ tự tuyệt đối** (ví dụ sequence của sổ cái) hoặc muốn tính “sự kiện A chắc chắn xảy ra trước B” trên mọi dịch vụ, cần một cơ chế thứ tự/phiên bản riêng; timeuuid không cung cấp bảo đảm đó.

### 9.2. Retry sau timeout

Trong hệ Cassandra phân tán, ghi có thể thành công ở một số replica nhưng client vẫn nhận timeout hoặc lỗi kết nối. Khi retry:

- **Giữ cùng primary key** (`account_id`, `event_day`, `event_id`) cho cùng sự kiện.
- Giữ các giá trị cột và quy tắc timestamp ghi nhất quán với yêu cầu nghiệp vụ; tránh một lần retry biến trạng thái từ A sang B ngoài ý muốn.
- Với cập nhật nhiều partition/bảng, cần cơ chế khôi phục/đối soát; retry một câu lệnh không biến toàn bộ quy trình thành một giao dịch ACID đa bảng.
- Nếu dùng LWT (`IF NOT EXISTS`) để giữ điều kiện độc nhất, kiểm tra kết quả và tình huống không biết lệnh có được áp dụng khi timeout.

Một `INSERT` với cùng primary key trong Cassandra có thể ghi đè các cell trùng khóa theo metadata timestamp; **cùng ID** thường cần thiết cho idempotency nhưng **không tự động đủ** nếu nội dung giữa các lần thử khác nhau.

### 9.3. Replication, consistency, compaction và repair

- **Replication** tạo các replica của dữ liệu theo token partition; UUID tham gia partition key được băm để xác định token, không phải xếp các partition theo thời gian sinh ID.
- **Consistency level** (ví dụ `LOCAL_QUORUM`) xác định yêu cầu xác nhận đọc/ghi, không đảm bảo thời điểm trong timeuuid là đúng với thời gian nguồn.
- **Compaction** gộp SSTable, xử lý dữ liệu cũ/tombstone theo quy tắc lưu trữ; nó không tự phát hiện ID bị nhân đôi vì retry.
- **Repair** đồng bộ replica; nó không tự hợp nhất hai bản ghi cùng sự kiện được tạo với hai `timeuuid` khác nhau.

Phân vùng timeline theo ngày/giờ cần đo lưu lượng, số hàng, kích thước partition và retention. Bucket ngày không đủ với nguồn phát hàng triệu sự kiện mỗi ngày; có thể cần bucket giờ hoặc shard, đi kèm thiết kế truy vấn được đo kiểm.

## 10. Tính riêng tư và bảo mật của UUID

UUID dùng để **nhận diện**, không phải để **cấp quyền**. Một URL chứa ID ngẫu nhiên vẫn cần kiểm tra người dùng có quyền đọc dữ liệu ở ID đó hay không.

Với UUID v1, thành phần timestamp có thể tiết lộ khoảng thời gian ID được tạo; một số thuật toán sinh v1 còn có thành phần node hoặc dấu vết môi trường sinh. Vì vậy, không nên coi timeuuid là một chuỗi hoàn toàn bí mật hoặc không tiết lộ metadata.

Với UUID v4, việc đoán đúng một UUID ngẫu nhiên chất lượng cao là cực khó trong điều kiện bình thường, nhưng vẫn **không thể thay thế** authentication, authorization, rate limiting hay audit.

Nếu một ID nghiệp vụ thực sự nhạy cảm, hãy áp dụng kiểm soát truy cập và phân tách dữ liệu thích hợp. Không dựa trên phiên bản UUID để quyết định người gọi được quyền xem bản ghi.

## 11. Các lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Ghi `UUID.randomUUID()` vào cột `timeuuid` | UUID v4 không phù hợp kiểu timeuuid | Dùng UUID v1, ví dụ `Uuids.timeBased()` |
| Gọi `now()` mỗi lần retry cùng sự kiện | Sinh khóa mới, tạo bản ghi trùng | Sinh một lần, giữ ID qua toàn bộ vòng đời retry |
| Gọi `uuid()` trong CQL để chèn account trong một luồng có retry | Account có thể được tạo nhiều ID | Sinh UUID ở ứng dụng và tái sử dụng |
| Giả định `uuid` tăng theo thời gian | Không có thứ tự thời gian đảm bảo | Clustering theo `timestamp` hoặc `timeuuid` đúng mục đích |
| Sử dụng `timeuuid` để suy ra thời gian xảy ra sự kiện từ nguồn | Sai khi ingest trễ/đồng hồ lệch | Lưu `occurred_at timestamp` độc lập |
| Dùng `min_timeuuid` làm ID INSERT | Sentinel không duy nhất | Chỉ dùng sentinel trong WHERE cho range |
| Query chỉ bằng event_id trên bảng partition theo account/day | Không có đầy đủ partition key | Truy vấn kèm khóa, hoặc bảng lookup riêng |
| Đặt timeuuid làm partition key rồi mong các sự kiện cùng tài khoản nằm cạnh nhau | Phân phối token phá thứ tự toàn cluster | Partition theo account/bucket, timeuuid làm clustering |
| So sánh `UUID.compareTo()` và mong trùng order của Cassandra | Có thể sai thứ tự timeuuid | Để Cassandra sắp theo clustering, hoặc comparator phù hợp |
| Dùng `event_day` theo timezone không nhất quán | Cùng sự kiện ở partition ngày khác nhau | Quy định UTC hoặc timezone nghiệp vụ thống nhất |
| Coi UUID là token phân quyền | Lộ ID có thể dẫn đến lộ dữ liệu | Kiểm tra quyền cho mọi thao tác |
| Không dự báo kích thước partition timeline | Partition quá lớn, latency/compaction xấu | Chọn bucket/shard theo throughput và retention |

## 12. Bài tập thực hành

### Bài 1 — Chọn kiểu

Một ứng dụng có ba loại cột: `customer_id` để tra khách hàng; `login_id` dùng sắp các lượt đăng nhập theo **thời điểm server nhận**; `occurred_at` là thời điểm máy khách ghi nhận thao tác.

**Đề xuất:** `customer_id uuid`; `login_id timeuuid` nếu server sinh ID khi nhận; `occurred_at timestamp`. Nếu yêu cầu sắp đúng thời gian nguồn, cần xem xét `occurred_at` làm clustering key và thêm UUID làm tie-breaker.

### Bài 2 — Tại sao trùng sự kiện khi retry?

Lệnh CQL dùng `now()` để insert sự kiện. Lần đầu client timeout nhưng coordinator đã ghi; lần hai lệnh chạy lại.

**Đáp án:** `now()` tạo timeuuid mới ở mỗi lần chạy, nên lần retry có thể chèn hàng thứ hai. Cách sửa là sinh timeuuid ở ứng dụng một lần, lưu trong event envelope và bind lại cùng ID khi retry.

### Bài 3 — Khoảng thời gian [08:00, 09:00)

Một bảng có partition key `(device_id, day)`, clustering key `event_id timeuuid`. Hãy viết CQL truy vấn theo khoảng 08:00–09:00 UTC của một ngày.

~~~cql
SELECT event_id
FROM events_by_device_day
WHERE device_id = 22222222-2222-4222-8222-222222222222
  AND day = '2026-11-21'
  AND event_id >= min_timeuuid('2026-11-21T08:00:00Z')
  AND event_id <  min_timeuuid('2026-11-21T09:00:00Z');
~~~

Đoạn này giả định bảng `events_by_device_day` đã được tạo đúng khóa trong đề bài; quan trọng là **đầy đủ partition key** và **giới hạn theo clustering key**. Không đặt `now()` vào vế giá trị khi cần truy vấn lại một thời điểm đã biết.

### Bài 4 — Cùng timestamp, hai sự kiện

Một bảng có khóa chính `((account_id, day), occurred_at)`. Hai sự kiện khác nhau cùng `occurred_at` đến mili giây. Điều gì xảy ra?

**Đáp án:** chúng có cùng primary key, nên các lần ghi có thể cập nhật lên cùng một hàng. Thêm `event_id uuid` làm clustering column cuối, hoặc dùng một `timeuuid` phù hợp với yêu cầu thứ tự để giữ hai hàng khác nhau.

### Bài 5 — UUID v1 có phải thời gian tuyệt đối đúng?

Hai máy A và B có đồng hồ lệch nhau 3 phút, cùng sinh UUID v1 cho hai sự kiện thực tế cách nhau 1 giây. Có thể lấy thứ tự CQL làm bằng chứng chính xác về trình tự thực tế không?

**Đáp án:** không. Cassandra sắp theo thành phần timestamp nhúng trong timeuuid, còn đồng hồ của các nguồn có thể lệch. Cần dữ liệu thời gian nguồn đã được hiệu chỉnh hoặc cơ chế ghi nhận thứ tự đáng tin theo nghiệp vụ.

## 13. Checklist khi review uuid và timeuuid

- [ ] Giá trị cần **định danh ổn định**, **sắp theo thời điểm sinh ID**, hay **sắp theo thời điểm sự kiện xảy ra**?
- [ ] Cột `timeuuid` chỉ nhận UUID v1; CQL `now()` và Java `Uuids.timeBased()` đã được dùng đúng?
- [ ] Mọi thao tác có thể retry đều tái sử dụng **cùng ID và cùng primary key**, không sinh lại UUID trong câu lệnh?
- [ ] Đã định nghĩa `occurred_at`, `generated_at`, `recorded_at` và **Cassandra write timestamp** theo đúng vai trò?
- [ ] Mọi dịch vụ dùng cùng chính sách timezone và bucket ngày/giờ?
- [ ] Truy vấn xác định đủ **partition key** và dùng điều kiện clustering hợp lệ?
- [ ] Các sentinel `min_timeuuid`/`max_timeuuid` (hoặc `Uuids.startOf/endOf`) chỉ dùng làm giới hạn truy vấn, không chèn vào bảng?
- [ ] Cần thứ tự toàn hệ thống hay chỉ thứ tự bên trong một phân vùng? Có xem xét clock skew/late arrival?
- [ ] Nếu nhiều sự kiện cùng timestamp, khóa đã có **tie-breaker** để không ghi đè?
- [ ] Java Driver đã ánh xạ đúng `UUID` với `getUuid`/`setUuid` và không nhầm phiên bản?
- [ ] Đã giới hạn kích thước partition và có retention, compaction, repair phù hợp?
- [ ] Dữ liệu được bảo vệ bởi quyền truy cập; không sử dụng UUID như một quyền truy cập bí mật?

## Tài liệu tham khảo

- [Apache Cassandra — CQL native functions, UUID và timeuuid](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/functions.html).
- [DataStax Java Driver 4.x — lớp Uuids](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/uuid/Uuids.html).

**Ghi nhớ:** `uuid` là lựa chọn tự nhiên cho **định danh UUID ổn định**; `timeuuid` là UUID **v1** thích hợp khi cần **clustering theo thời điểm tạo ID**. Nếu thứ tự phải theo **thời gian thực xảy ra ở nguồn**, hãy lưu `timestamp` nghiệp vụ và thiết kế clustering key tương ứng. Trong Cassandra, **loại ID, khóa phân vùng, thứ tự clustering và tính idempotent khi retry** quyết định hiệu quả và độ đúng của hệ thống.

