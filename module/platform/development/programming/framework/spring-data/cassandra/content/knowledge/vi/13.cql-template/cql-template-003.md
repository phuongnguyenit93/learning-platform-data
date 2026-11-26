# Điều kiện partition key và khoảng clustering hợp lệ trong CQL và CqlTemplate

## 1. Vì sao cần hiểu điều kiện WHERE của Cassandra?

Trong **Apache Cassandra**, truy vấn hiệu quả thường bắt đầu từ **partition key** và tiếp tục bằng các **clustering columns**. Khác với suy nghĩ quen thuộc khi dùng cơ sở dữ liệu quan hệ, không phải cứ có bảng và thêm một biểu thức vào `WHERE` là Cassandra có thể tìm nhanh các hàng phù hợp.

Với **Spring Data Cassandra**, ứng dụng có thể gọi repository, `CassandraTemplate` hoặc `CqlTemplate` để thực thi CQL. Dù dùng API nào, **quy tắc truy vấn của Cassandra không thay đổi**. Nếu điều kiện bỏ thiếu một phần khóa phân vùng, lọc sai thứ tự clustering hoặc yêu cầu sắp xếp ngoài khả năng của schema, kết quả có thể là lỗi CQL hoặc một truy vấn phải lọc rất nhiều dữ liệu.

Bài học thuộc chương **CQL và CqlTemplate**, tập trung vào:

1. Điều kiện **bằng** trên đầy đủ partition key, kể cả khóa phân vùng tổng hợp.
2. Điều kiện **tiền tố clustering**: các cột đầu so sánh bằng, rồi có thể dùng khoảng trên cột tiếp theo.
3. Cách diễn đạt **khoảng thời gian nửa mở**, `LIMIT`, `ORDER BY` và tham số bind.
4. Trường hợp không phù hợp như bỏ thiếu partition key, lọc theo cột thường hoặc dùng `ALLOW FILTERING` để che thiết kế sai.
5. Cách triển khai cùng quy tắc bằng `CqlTemplate`, xử lý kết quả rỗng, paging và các lỗi ứng dụng.

Kết quả mong muốn không chỉ là viết được một câu CQL hợp lệ, mà còn **giải thích vì sao câu truy vấn chỉ phải đọc một tập dữ liệu được định vị trước**, không trở thành quét toàn cluster.

## 2. Bảng minh họa: sự kiện theo tenant và ngày

Giả sử API có hai access pattern:

- Đọc **50 sự kiện mới nhất** của một tenant trong một ngày.
- Đọc sự kiện **trong một khoảng thời gian** của cùng tenant/ngày, có thể phân trang.

Một bảng thiết kế theo truy vấn:

~~~sql
CREATE TABLE events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    category text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

| Cột | Vai trò | Hệ quả đối với truy vấn |
| --- | --- | --- |
| `tenant_id` | Thành phần 1 của partition key | Khi lookup một partition, phải biết tenant |
| `event_day` | Thành phần 2 của partition key | Khi lookup một partition, phải biết ngày chính xác |
| `occurred_at` | Clustering column thứ nhất | Có thể giới hạn theo thời điểm **sau khi đã xác định partition** |
| `event_id` | Clustering column thứ hai | Phân biệt các sự kiện trùng thời điểm; có thể ràng buộc khi cột clustering đứng trước được ràng buộc phù hợp |
| `category`, `payload` | Cột thông thường | Không tự tạo đường truy cập để lọc tùy ý bằng `WHERE` |

Cụm `PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)` có hai cặp ngoặc: cặp bên trong xác định **partition key tổng hợp**. Cassandra tính token từ **toàn bộ cặp `tenant_id + event_day`**, sau đó các hàng của cùng partition được tổ chức theo khóa clustering.

~~~mermaid
flowchart TD
    A[WHERE tenant_id = T AND event_day = D] --> B[Định vị một partition bằng toàn bộ partition key]
    B --> C[Những hàng cùng tenant và ngày]
    C --> D[Clustering: occurred_at DESC]
    D --> E[Tie-break: event_id ASC]
    E --> F[Áp dụng khoảng thời gian và LIMIT]
~~~

Với một tenant rất lớn, chia theo ngày vẫn có thể sinh partition lớn hoặc nóng; ứng dụng cần đo kích thước partition và tải ghi thực tế. Bảng trên là **ví dụ để học quy tắc**, không phải cam kết phù hợp với mọi hệ thống.

## 3. Quy tắc thứ nhất: xác định đầy đủ partition key

### 3.1. Truy vấn đúng một partition

Trong bảng minh họa, điều kiện chuẩn là:

~~~sql
SELECT event_id, occurred_at, category
FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
LIMIT 50;
~~~

Hai dấu `?` là **bind markers**. Khi tham số có giá trị hợp lệ, Cassandra xác định được partition cần đọc, rồi lấy tối đa 50 hàng theo thứ tự clustering mặc định của bảng. Không cần thêm `ALLOW FILTERING`.

Tương đương về ý nghĩa, với giá trị cụ thể của một ngày:

~~~sql
SELECT event_id, occurred_at, category
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-25'
LIMIT 50;
~~~

Ví dụ literal chỉ để minh họa. Trong ứng dụng hãy **bind tham số**, không nối trực tiếp chuỗi ngày/UUID nhận từ HTTP request vào CQL.

### 3.2. Thiếu một phần partition key là vấn đề gì?

Những ý tưởng sau **không phải truy vấn định vị partition hợp lệ theo đường đọc thông thường của bảng này**:

~~~sql
-- Thiếu event_day: chỉ biết một phần của composite partition key.
SELECT * FROM events_by_tenant_day
WHERE tenant_id = ?;

-- Thiếu tenant_id: không thể định vị partition từ mỗi ngày.
SELECT * FROM events_by_tenant_day
WHERE event_day = ?;

-- Clustering column không giúp thay thế partition key.
SELECT * FROM events_by_tenant_day
WHERE occurred_at >= ?;
~~~

Không có index/đường truy cập đặc biệt, Cassandra thường **từ chối** các truy vấn trên vì không thể xác định partition theo primary key; một số dạng có thể được chấp nhận khi buộc `ALLOW FILTERING` nhưng phải quét và lọc, không có nghĩa truy vấn đã hiệu quả.

**Khóa phân vùng tổng hợp không phải một index ghép có thể dùng tiền tố theo cách tùy ý.** `tenant_id` tự nó không xác định đúng một partition vì cùng tenant có thể có rất nhiều `event_day`.

### 3.3. Có được dùng IN với partition key?

CQL hỗ trợ một số dạng điều kiện `IN` trên thành phần khóa theo quy tắc của phiên bản Cassandra và dạng primary key. Tuy nhiên, dùng `IN` thường tương đương yêu cầu đọc **nhiều partition/giá trị khóa**, có thể sinh nhiều truy cập replica. Không xem `IN` là giải pháp mặc định cho “tìm tất cả sự kiện của tenant trong cả năm”.

Nếu màn hình cần một khoảng **nhiều ngày**, có ba hướng cần đánh giá:

1. Thực hiện một số **truy vấn partition theo từng ngày đã biết** rồi ghép kết quả ở ứng dụng, với giới hạn số ngày và đồng thời.
2. Thiết kế thêm bảng phục vụ đúng truy vấn liên ngày, có partition key/bucket được tính toán cho tần suất và kích thước dữ liệu.
3. Dùng hệ tìm kiếm/phân tích dữ liệu riêng nếu yêu cầu quét linh hoạt trên tập lớn.

Việc một API Java trả `List<Event>` không tạo ra đường truy cập xuyên nhiều partition một cách tự động.

## 4. Quy tắc thứ hai: clustering columns tạo thành tiền tố có thứ tự

Với khóa clustering theo thứ tự:

~~~text
occurred_at  ->  event_id
     C1             C2
~~~

Khi **partition key đã được xác định**, truy vấn có thể sử dụng phần đầu của khóa clustering.

### 4.1. Điều kiện bằng trên cột clustering đầu tiên

~~~sql
SELECT event_id, category
FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
  AND occurred_at = ?;
~~~

Truy vấn có thể trả **nhiều sự kiện tại cùng thời điểm** nếu `event_id` khác nhau. Nếu muốn đúng một hàng, thêm `event_id`:

~~~sql
SELECT category, payload
FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
  AND occurred_at = ? AND event_id = ?;
~~~

Đây là lookup theo **toàn bộ primary key**: tối đa một hàng. Không nên bỏ qua việc dùng `event_id` chỉ vì thời gian thường khác nhau; nhiều sự kiện vẫn có thể cùng timestamp đến mili giây.

### 4.2. Điều kiện khoảng trên cột clustering đầu tiên

Giả sử cần tất cả sự kiện trong khoảng **từ 09:00 đến trước 10:00** UTC:

~~~sql
SELECT event_id, occurred_at, category
FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
  AND occurred_at >= ?
  AND occurred_at < ?
LIMIT 50;
~~~

Điều kiện này chỉ quét **một khoảng trong một partition đã biết**. Hai phép so sánh đều áp dụng trên **cùng cột clustering đầu tiên** `occurred_at`, nên không cần quét các ngày/tenant khác.

Nên ưu tiên **khoảng nửa mở**:

\[
[fromInclusive,\;toExclusive)
\]

Ví dụ: `2026-11-25T09:00:00Z` ≤ `occurred_at` và `occurred_at` < `2026-11-25T10:00:00Z`. Khi tách các cửa sổ liên tiếp, sự kiện ở đúng 10:00 thuộc cửa sổ tiếp theo chứ không bị đếm hai lần.

### 4.3. Điều kiện khoảng trên clustering column thứ hai

Nếu cột clustering đầu tiên được ràng buộc **bằng** một thời điểm:

~~~sql
SELECT event_id, category
FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
  AND occurred_at = ?
  AND event_id > ?;
~~~

Lúc này `occurred_at` xác định nhóm có cùng timestamp, còn khoảng của `event_id` được áp dụng trên clustering column tiếp theo. Đây là một cách minh họa **equality prefix rồi range**.

Ngược lại, khi `occurred_at` đã có **khoảng nhiều giá trị**, không nên ràng buộc thêm `event_id = ?` như thể Cassandra có thể dùng mọi cột clustering độc lập:

~~~sql
-- Không phải dạng truy vấn tuần tự theo clustering key thông thường:
SELECT * FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
  AND occurred_at >= ?
  AND event_id = ?;
~~~

Trong thiết kế query-first, trường hợp này thường đòi hỏi lọc bổ sung hoặc một access pattern khác. Đừng dùng `ALLOW FILTERING` chỉ để làm truy vấn được chấp nhận: việc ràng buộc một cột clustering phía sau **mà cột phía trước đang là khoảng** không còn định vị một dải liên tục đơn giản theo thứ tự khóa.

### 4.4. Bảng các dạng điều kiện thường gặp

| Điều kiện sau khi đã đủ partition key | Đánh giá | Lý do |
| --- | --- | --- |
| Không ràng buộc clustering | **Phù hợp** | Duyệt từ đầu partition theo thứ tự clustering |
| `occurred_at = ?` | **Phù hợp** | Equality trên cột clustering đầu |
| `occurred_at >= ? AND occurred_at < ?` | **Phù hợp** | Một khoảng trên cột clustering đầu |
| `occurred_at = ? AND event_id = ?` | **Phù hợp** | Lookup đủ primary key |
| `occurred_at = ? AND event_id > ?` | **Phù hợp** | Equality prefix trước range ở cột sau |
| Chỉ `event_id = ?` | **Không phù hợp với đường truy cập khóa này** | Bỏ qua cột clustering đứng trước |
| `occurred_at > ? AND event_id = ?` | **Không phải mẫu truy vấn khóa chuẩn** | Đòi ràng buộc cột sau khi cột trước đã dùng range |
| `category = ?` | **Không thể định vị qua primary key** | `category` là cột thường |

Một số phiên bản Cassandra/cơ chế index hỗ trợ các dạng truy vấn khác; bảng trên nói về **truy vấn trực tiếp theo primary key, không cần filtering/index bổ sung**. Khi triển khai, cần xác minh trên đúng phiên bản CQL server và schema đã chọn.

## 5. Ba nguyên tắc thực hành với khoảng clustering

### 5.1. Dùng đủ partition key trước khi thêm range

Nếu `event_day` không xuất hiện trong điều kiện, thêm `occurred_at >= ?` không bù được việc thiếu thành phần partition key. Câu query:

~~~sql
-- Thiếu event_day; thêm range không giải quyết đường truy cập.
SELECT * FROM events_by_tenant_day
WHERE tenant_id = ? AND occurred_at >= ?;
~~~

Không tương đương truy vấn một partition có khoảng. Cách sửa là biết thêm `event_day` hoặc thay đổi mô hình bảng theo access pattern.

### 5.2. Giới hạn khoảng và giới hạn số hàng là hai việc riêng

Khoảng thời gian ngắn có thể chứa **rất nhiều sự kiện** khi tải cao. Ngược lại, khoảng dài nhưng chỉ có vài sự kiện có thể ít dữ liệu. Vì vậy nên đồng thời:

- Giới hạn thời gian yêu cầu, chẳng hạn một ngày hoặc vài giờ tùy lưu lượng.
- Dùng `LIMIT` hoặc paging để kiểm soát lượng hàng xử lý trong một request.
- Chọn projection chỉ gồm những cột cần thiết, thay vì `SELECT *` theo thói quen.
- Đo kích thước partition, độ trễ truy vấn, khối lượng row và tombstone thực tế.

`LIMIT 50` chỉ hạn chế số hàng trả về của **truy vấn đó**; không có nghĩa partition sẽ nhỏ hoặc truy vấn lúc nào cũng nhanh, đặc biệt khi nhiều tombstone hoặc partition bị nóng.

### 5.3. Thời gian và độ chính xác

Kiểu CQL `timestamp` biểu diễn một thời điểm với độ chính xác **mili giây**. Phía Java nên dùng `Instant` cho mốc thời gian tuyệt đối và chuẩn hóa đơn vị khi cần:

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

Instant fromInclusive = requestFrom.truncatedTo(ChronoUnit.MILLIS);
Instant toExclusive = requestTo.truncatedTo(ChronoUnit.MILLIS);

if (!fromInclusive.isBefore(toExclusive)) {
    throw new IllegalArgumentException("Invalid time range");
}
~~~

Đoạn code giả định `requestFrom` và `requestTo` là `Instant` đã được validate không null. Nếu giá trị có nano giây, **việc truncate có thể làm thay đổi ranh giới dự kiến**; một API yêu cầu chính xác cao cần quy tắc làm tròn xuống/lên nhất quán, đặc biệt ở ngưỡng `toExclusive`.

**`event_day` phải tương ứng với quy ước xác định ngày**. Ví dụ một ngày UTC từ 00:00 đến trước 00:00 ngày tiếp theo; nếu phân vùng theo ngày địa phương, ứng dụng phải dùng **cùng timezone nghiệp vụ** khi tạo partition key và tính các khoảng truy vấn. Không tự lấy ngày theo timezone máy chủ nếu thời điểm ghi được chuẩn hóa theo quy tắc khác.

## 6. ORDER BY: sắp xếp theo khóa clustering, không theo mọi cột

Bảng mẫu có:

~~~sql
WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC)
~~~

Điều đó định nghĩa thứ tự lưu/duyệt logic **bên trong cùng một partition**: thời điểm mới nhất trước; nếu trùng thời điểm thì `event_id` tăng dần.

Truy vấn danh sách phù hợp:

~~~sql
SELECT event_id, occurred_at, category
FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
ORDER BY occurred_at DESC, event_id ASC
LIMIT 50;
~~~

Trong trường hợp này, `ORDER BY` làm rõ thứ tự phù hợp với clustering order đã định nghĩa. Không cần nó nếu chỉ muốn thứ tự mặc định. Những lưu ý quan trọng:

1. Cassandra chỉ cho phép `ORDER BY` trong những điều kiện khóa phù hợp, theo **clustering columns**; không thể tùy ý dùng `ORDER BY category` trên cột thường của bảng.
2. `ORDER BY` phục vụ thứ tự **bên trong partition**. Nhiều partition được truy vấn/gộp lại không mặc nhiên có **thứ tự toàn cục**.
3. Có thể có dạng đọc đảo chiều clustering order theo quy tắc CQL của phiên bản, nhưng không được đảo một cột bất kỳ rồi giả định mọi tổ hợp `ASC/DESC` đều hợp lệ.
4. Trả các hàng mới nhất dựa trên `occurred_at` không đảm bảo “mới ghi vào Cassandra nhất”. Timestamp nghiệp vụ và thời điểm ghi vật lý là hai khái niệm khác nhau.
5. Dữ liệu đang được cập nhật đồng thời có thể làm kết quả trang kế tiếp thay đổi. Sắp xếp hợp lệ không phải snapshot toàn hệ thống.

## 7. ALLOW FILTERING không sửa được khóa được thiết kế sai

Một yêu cầu thường gặp: “Lấy tất cả sự kiện có `category = 'PAYMENT'`” mà **không biết tenant hoặc ngày**. Truy vấn đơn giản:

~~~sql
-- Không có đường truy cập theo primary key.
SELECT * FROM events_by_tenant_day
WHERE category = 'PAYMENT';
~~~

Có thể bị Cassandra từ chối. Một người học có thể thử thêm:

~~~sql
-- Cú pháp có thể cho phép quét/lọc trong một số trường hợp,
-- KHÔNG biến nó thành truy vấn partition-key hiệu quả.
SELECT * FROM events_by_tenant_day
WHERE category = 'PAYMENT'
ALLOW FILTERING;
~~~

**Rủi ro:** server phải đọc tập dữ liệu rộng rồi lọc hàng, lượng dữ liệu/quét và độ trễ có thể tăng rất mạnh theo quy mô; kết quả có thể không ổn định dưới tải. `ALLOW FILTERING` là cảnh báo để **đánh giá lại mô hình dữ liệu**, không phải mẹo tối ưu.

Nếu tìm theo category là access pattern quan trọng, xem xét:

- Bảng riêng, ví dụ `events_by_tenant_day_category` với partition key phù hợp `(tenant_id, event_day, category)` và clustering `(occurred_at, event_id)`.
- Tính toán fan-out/gộp dữ liệu khi một sự kiện được lưu theo nhiều đường đọc.
- Index/search capability được Cassandra phiên bản đang chạy hỗ trợ (nếu chọn), dựa trên đo đạc và giới hạn vận hành cụ thể.

Ví dụ bảng thứ hai:

~~~sql
CREATE TABLE events_by_tenant_day_category (
    tenant_id uuid,
    event_day date,
    category text,
    occurred_at timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((tenant_id, event_day, category), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

Bây giờ khi biết **tenant, ngày, category**, truy vấn đọc một partition có thể áp dụng range trên `occurred_at`. Nhưng nếu yêu cầu “mọi category trên toàn tenant”, vấn đề access pattern vẫn phải được thiết kế; không có một primary key tối ưu cho tất cả kiểu lọc.

## 8. Truy vấn giới hạn và khoảng bằng CqlTemplate

`CqlTemplate` là API Spring Data Cassandra ở mức **CQL**, thường dùng qua `CqlOperations` khi cần trực tiếp kiểm soát câu CQL nhưng vẫn muốn dùng hạ tầng Spring. Nó khác với `CassandraTemplate`, vốn cung cấp các thao tác mapping/entity ở mức cao hơn.

| Thành phần | Khi nên dùng | Điều vẫn phải tự đảm bảo |
| --- | --- | --- |
| `CassandraRepository` | CRUD theo khóa, repository query rõ ràng | Truy vấn phù hợp primary key và số hàng dự kiến |
| `CassandraTemplate` | Thao tác entity/criteria, ánh xạ Java object | Điều kiện CQL hợp lệ, giới hạn/paging và cấu hình mapping |
| `CqlTemplate` / `CqlOperations` | CQL tường minh, ánh xạ `Row` sang DTO | Câu CQL, bind parameter, null/empty, lỗi và giới hạn kết quả |
| `CqlSession` (driver) | Phải kiểm soát prepared statement, paging state, execution options chi tiết | Vòng đời session, bind/codec, consistency và mọi lỗi tầng thấp |

### 8.1. Ví dụ CqlTemplate với bind markers

Giả sử `CqlTemplate` đã được Spring cấu hình và inject vào service. Ta đọc tối đa 50 sự kiện trong một ngày và khoảng thời gian cho trước:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import org.springframework.data.cassandra.core.cql.CqlTemplate;

public class EventReadService {
    private final CqlTemplate cqlTemplate;

    public EventReadService(CqlTemplate cqlTemplate) {
        this.cqlTemplate = cqlTemplate;
    }

    public List<EventView> findEvents(
            UUID tenantId,
            LocalDate eventDay,
            Instant fromInclusive,
            Instant toExclusive) {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(eventDay, "eventDay");
        Objects.requireNonNull(fromInclusive, "fromInclusive");
        Objects.requireNonNull(toExclusive, "toExclusive");
        if (!fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException("Invalid time range");
        }

        String cql =
            "SELECT event_id, occurred_at, category " +
            "FROM events_by_tenant_day " +
            "WHERE tenant_id = ? AND event_day = ? " +
            "AND occurred_at >= ? AND occurred_at < ? " +
            "LIMIT 50";

        return cqlTemplate.query(
            cql,
            (row, rowNum) -> new EventView(
                row.getUuid("event_id"),
                row.getInstant("occurred_at"),
                row.getString("category")),
            tenantId, eventDay, fromInclusive, toExclusive
        );
    }
}
~~~

`EventView` là DTO tự định nghĩa trong ứng dụng, chẳng hạn chứa `UUID eventId`, `Instant occurredAt`, `String category`. Ví dụ minh họa một overload dạng `query(cql, RowMapper, args...)` thường có ở những dòng Spring Data Cassandra tương ứng; **cần xác minh chữ ký API chính xác với phiên bản thư viện đang sử dụng** trước khi đưa nguyên mẫu vào code production.

**Ưu điểm của ví dụ:**

- Toàn bộ partition key có ràng buộc `=`.
- Khoảng `>=` và `<` chỉ áp dụng cho clustering column đầu tiên.
- `LIMIT 50` giới hạn số hàng được yêu cầu trả về.
- Giá trị từ client đi qua **bind markers**, không nội suy vào câu CQL.
- RowMapper chỉ đọc những cột đã select, giảm chuyển đổi không cần thiết.

Giả sử kết quả không có hàng, `query(...)` cho danh sách thường trả một collection **rỗng**, không nên tạo một event giả. Lỗi timeout/kết nối/CQL sai là **ngoại lệ**, không được nuốt thành danh sách rỗng.

### 8.2. Chuẩn bị CqlTemplate trong Spring Boot

Trong các cấu hình Spring Boot/Spring Data Cassandra có hỗ trợ bean phù hợp, hạ tầng kết nối thường bắt đầu từ một `CqlSession`:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.cql.CqlTemplate;

@Configuration(proxyBeanMethods = false)
public class EventCqlConfig {

    @Bean
    CqlTemplate eventCqlTemplate(CqlSession session) {
        return new CqlTemplate(session);
    }
}
~~~

**Không khai báo trùng bean** nếu auto-configuration của phiên bản ứng dụng đã tạo `CqlTemplate`/`CqlOperations` tương ứng. Nếu có nhiều session, phải dùng `@Qualifier` để chọn đúng session/keyspace. Bảng ví dụ `events_by_tenant_day` phải tồn tại trong **keyspace mặc định của session** hoặc phải dùng tên đầy đủ `keyspace.table` trong CQL.

### 8.3. Nếu dùng Java driver trực tiếp

Khi cần điều khiển paging/timeout/consistency ở mức statement cụ thể, có thể làm việc với `CqlSession`:

~~~java
PreparedStatement ps = session.prepare(
    "SELECT event_id, occurred_at, category " +
    "FROM events_by_tenant_day " +
    "WHERE tenant_id = ? AND event_day = ? " +
    "AND occurred_at >= ? AND occurred_at < ? LIMIT 50"
);

BoundStatement statement = ps.bind(
    tenantId, eventDay, fromInclusive, toExclusive
);

ResultSet result = session.execute(statement);
for (Row row : result) {
    // Chuyển mỗi Row thành DTO theo nhu cầu nghiệp vụ.
}
~~~

Ví dụ dùng các kiểu `PreparedStatement`, `BoundStatement`, `ResultSet`, `Row` của **Java driver 4.x**; cần import tương ứng và dùng một session được tái sử dụng. Câu CQL vẫn chịu chính các quy tắc partition/clustering đã giải thích.

## 9. Những ngoại lệ và lỗi CQL thường gặp

| Yêu cầu | Vấn đề thực tế | Hướng sửa |
| --- | --- | --- |
| Chỉ truyền `tenant_id` | Thiếu `event_day` của composite partition key | Xác định ngày hoặc tạo access pattern khác |
| Chỉ lọc `event_id` | Thiếu partition và clustering prefix | Truy vấn bằng khóa đủ, hoặc lập bảng tra cứu theo ID nếu cần |
| Có partition nhưng lọc `category` | Cột thường không thuộc primary key/index hiện có | Tạo bảng theo category hoặc cơ chế index phù hợp |
| Điều kiện `event_id` khi bỏ `occurred_at` | Bỏ cột clustering trước | Thêm tiền tố bằng hoặc thiết kế lại bảng |
| Range trên `occurred_at` rồi lọc thêm `event_id` | Không phải một dải clustering tuần tự đơn giản | Đổi cách truy vấn/paging, cân nhắc cấu trúc khóa |
| `ORDER BY category` | Không phải clustering order | Thêm đường đọc/sắp xếp phù hợp trong schema hoặc giới hạn dữ liệu trước khi xử lý ứng dụng |
| Dùng `LIMIT 50` và nghĩ có đủ mọi sự kiện | Cố ý chỉ lấy một phần | Cần hợp đồng rõ “top 50” hoặc paging thực sự |
| Dùng `ALLOW FILTERING` vì thiếu partition | Có thể quét rộng và tốn tài nguyên | Thiết kế bảng theo truy vấn, không dùng làm mặc định |
| Range thời gian bị đảo, hoặc khác ngày partition | Không đúng hợp đồng truy vấn | Validate đầu vào và quy ước timezone/ngày |
| `CqlTemplate` query không có hàng | Kết quả thành công nhưng rỗng | Trả danh sách rỗng, không ném lỗi 404 vô điều kiện |
| `ReadTimeout` / `Unavailable` | Không đủ phản hồi hoặc truy vấn thất bại | Xử lý ngoại lệ theo chính sách, không báo “không có dữ liệu” |

Thông điệp lỗi cụ thể của Cassandra có thể thay đổi theo phiên bản và có thể nhắc đến `ALLOW FILTERING` hoặc không. Không viết logic ứng dụng dựa trên **chuỗi lỗi** để quyết định tự thêm `ALLOW FILTERING`; thay vào đó kiểm soát câu CQL theo loại truy vấn được hỗ trợ.

## 10. Paging, LIMIT và keyset: ba khái niệm khác nhau

Cassandra hỗ trợ đọc kết quả theo **page** thông qua driver/paging state. Khi truy vấn có thể trả nhiều hàng, cần phân biệt:

- **`LIMIT n`:** giới hạn **tổng số hàng của truy vấn**.
- **Page size:** điều khiển số hàng driver yêu cầu xử lý/chuyển trong từng lượt fetch của một truy vấn.
- **Paging state:** trạng thái tiếp tục từ trang trước; phải gắn với **cùng CQL và tham số**, và được quản lý an toàn khi đưa ra API.

Ví dụ `LIMIT 50` không có nghĩa “mỗi trang 50 và còn trang 2 của mọi dữ liệu”; nếu muốn đọc nhiều hơn 50, cần tổ chức lại **hợp đồng truy vấn** và cách paging.

### 10.1. Khoảng theo thời gian có thay cho paging state không?

Không hoàn toàn. Một API có thể tiếp tục bằng **khóa cuối của trang trước** (keyset pagination) trong một số bảng, nhưng cần xử lý cặp clustering `(occurred_at, event_id)` một cách đúng đắn:

1. Hai sự kiện có thể cùng `occurred_at`.
2. Bảng có mixed clustering order `DESC` cho thời gian và `ASC` cho event ID.
3. Một điều kiện đơn `occurred_at < lastTimestamp` **bỏ sót** các sự kiện trùng timestamp chưa trả.
4. Điều kiện tuple hoặc kết hợp range cần tuân theo khả năng CQL và thứ tự clustering thực tế; không tự suy diễn từ toán học rằng mọi tổ hợp đều được server hỗ trợ.

Vì vậy, khi chỉ cần tiếp tục kết quả của cùng một truy vấn, thường **ưu tiên paging state của driver**. Nếu sản phẩm cần token bền vững, điều hướng ngẫu nhiên hoặc chống trùng giữa các phiên khi dữ liệu thay đổi, phải thiết kế cursor/API riêng với ràng buộc phù hợp, không chỉ truyền timestamp.

### 10.2. Khi nào danh sách rỗng là kết quả bình thường?

Với partition xác định, nếu không có sự kiện trong khoảng thời gian, CqlTemplate có thể trả `List<EventView>` rỗng. Đây không phải dấu hiệu Cassandra bị lỗi. Ngược lại, nếu query bị từ chối, timeout hoặc mapping `Row` thất bại, ứng dụng phải phân loại ngoại lệ đúng, không trả `[]` như thể truy vấn đã thành công.

## 11. Consistency và tác động của cluster tới kết quả khoảng

Một truy vấn CQL hợp lệ không bảo đảm mọi request luôn thành công hoặc mọi node luôn có dữ liệu giống hệt:

- **Replication factor** xác định các replica của partition theo keyspace/topology.
- **Consistency level** xác định yêu cầu phản hồi của các replica cho từng thao tác đọc/ghi.
- Node lỗi, mạng chậm, tombstone và compaction có thể tác động độ trễ ngay cả khi `WHERE` hợp lệ.
- Một lần đọc không thấy row chỉ là kết quả theo trạng thái và consistency của thời điểm đọc, không chứng minh row chưa từng tồn tại.
- `WriteTimeout` của lần ghi trước có thể khiến kết quả thực tế chưa rõ; retry nghiệp vụ cần idempotency và cơ chế đối soát.

Ví dụ với replication factor 3 tại một datacenter, `LOCAL_QUORUM` thường yêu cầu 2 replica đáp ứng theo quy tắc local quorum. Đây là lựa chọn consistency, **không sửa được** truy vấn thiếu partition key hoặc điều kiện clustering sai.

Khi đo hiệu năng, hãy xem độ trễ phân vị, số hàng/tombstone được đọc, kích thước partition, tải từng node và cách chọn coordinator, không chỉ nhìn vào việc CQL có trả về đủ 50 hàng hay không.

## 12. Bài thực hành: phân loại truy vấn hợp lệ và không phù hợp

Chuẩn bị trên cluster thử nghiệm:

1. Tạo keyspace với replication phù hợp số node và định nghĩa `events_by_tenant_day` như phần 2.
2. Sinh dữ liệu cho hai tenant trong hai ngày; trong một partition đặt nhiều sự kiện cùng `occurred_at` nhưng khác `event_id`.
3. Ghi lại **partition key**, hai **clustering columns** và thứ tự sắp xếp đã định nghĩa.
4. Dự đoán hiệu lực của từng truy vấn dưới đây trước khi chạy thử.

### Truy vấn A — Một partition, giới hạn

~~~sql
SELECT event_id, occurred_at
FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
LIMIT 10;
~~~

**Kỳ vọng:** hợp lệ theo đường đọc khóa; tối đa 10 hàng từ một partition.

### Truy vấn B — Khoảng trong một partition

~~~sql
SELECT event_id, occurred_at
FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
  AND occurred_at >= ?
  AND occurred_at < ?
LIMIT 50;
~~~

**Kỳ vọng:** hợp lệ theo đường đọc khóa; chỉ xét một khoảng trên cột clustering đầu.

### Truy vấn C — Bỏ thiếu event_day

~~~sql
SELECT event_id
FROM events_by_tenant_day
WHERE tenant_id = ? AND occurred_at >= ?;
~~~

**Kỳ vọng:** không định vị partition theo composite key, không phải truy vấn phù hợp với bảng này. Giải thích vì sao không nên chỉ thêm `ALLOW FILTERING`.

### Truy vấn D — Chỉ lọc cột thường

~~~sql
SELECT event_id
FROM events_by_tenant_day
WHERE category = ?;
~~~

**Kỳ vọng:** không có đường đọc từ primary key; cần schema/index khác nếu đây là yêu cầu quan trọng.

### Truy vấn E — Lọc clustering không theo tiền tố

~~~sql
SELECT event_id
FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
  AND event_id = ?;
~~~

**Kỳ vọng:** không phải dạng truy vấn hiệu quả dựa trên clustering key của bảng, vì thiếu `occurred_at` đứng trước.

### Truy vấn F — Equality prefix rồi range

~~~sql
SELECT event_id
FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
  AND occurred_at = ?
  AND event_id > ?;
~~~

**Kỳ vọng:** hợp lệ theo khóa; cố định cột clustering thứ nhất rồi dùng range ở cột thứ hai.

### Truy vấn G — ORDER BY không theo clustering

~~~sql
SELECT event_id, category
FROM events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
ORDER BY category ASC;
~~~

**Kỳ vọng:** không được phép sắp xếp tùy ý theo cột thường. Cần thiết kế lại bảng/đường đọc.

**Sau khi thử**, ghi lại với mỗi câu: có định vị partition không; clustering prefix có đúng không; dữ liệu tối đa có thể trả là bao nhiêu; server trả kết quả hay lỗi; có cách thiết kế bảng khác tốt hơn không.

## 13. Bài thực hành CqlTemplate và kiểm thử tích hợp

**Yêu cầu:** viết một service trả tối đa 50 sự kiện trong khoảng thời gian được chọn của một tenant/ngày, sử dụng `CqlTemplate`.

Các bước:

1. Định nghĩa DTO `EventView` và lớp `EventReadService` như ở phần 8.
2. Cấu hình `CqlSession` đến Cassandra thử nghiệm và chọn đúng keyspace/local datacenter.
3. Truyền tham số `UUID`, `LocalDate`, `Instant` qua bind markers. Không tự nối giá trị vào chuỗi CQL.
4. Ghi 3 sự kiện nằm trong khoảng, 2 sự kiện ngoài khoảng nhưng cùng partition, 1 sự kiện ở ngày khác.
5. Kiểm tra service trả đúng 3 sự kiện trong khoảng; thử khoảng không có dữ liệu và xác nhận danh sách rỗng.
6. Thử các giá trị ở đúng ranh giới: sự kiện ở `fromInclusive` được lấy, sự kiện ở `toExclusive` bị loại.
7. Tạo hai sự kiện trùng thời điểm, quan sát tie-break bằng `event_id` theo thứ tự bảng.
8. Gửi khoảng đảo đầu/cuối, xác nhận validation từ chối trước khi phát truy vấn.
9. Thử CQL thiếu `event_day`; ghi lại lỗi server và giải thích tại sao lỗi không nằm ở RowMapper.
10. Quan sát độ trễ với partition lớn hơn; kiểm tra khả năng giới hạn số hàng, data size và paging thay vì thêm `ALLOW FILTERING`.

**Khi dùng test tích hợp**, cần xác minh trên đúng phiên bản Cassandra/Spring Data: API `CqlTemplate`, kiểu codec cho `LocalDate`/`Instant`, cách ánh xạ `Row`, và việc schema đã được chuẩn bị. Không chạy bài thử gây tải lớn trên cluster đang phục vụ người dùng.

## 14. Các hiểu nhầm cần tránh

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Chỉ cần tenant_id là đã đủ partition key tổng hợp.” | Phải biết cả `tenant_id` và `event_day` để định vị một partition của bảng mẫu |
| “Clustering columns có thể lọc độc lập như mọi cột SQL.” | Truy vấn khóa chuẩn sử dụng tiền tố theo thứ tự clustering đã khai báo |
| “Khoảng thời gian không cần partition key.” | Range trên clustering chỉ hữu ích sau khi đã định vị partition |
| “Thêm ALLOW FILTERING là đã tối ưu.” | Có thể phải quét/lọc diện rộng và chi phí tăng theo dữ liệu |
| “LIMIT 50 đồng nghĩa phân trang 50 hàng cho đến hết.” | LIMIT giới hạn tổng kết quả; paging state và page size là khái niệm khác |
| “Có ORDER BY thì sắp xếp toàn cluster.” | ORDER BY dựa trên clustering, không tạo global sort tùy ý trên mọi partition |
| “CqlTemplate tự sửa CQL không hợp lệ.” | Template truyền câu CQL tới Cassandra và ánh xạ kết quả; quy tắc khóa vẫn giữ nguyên |
| “RowMapper rỗng nghĩa là timeout.” | Không có hàng là kết quả hợp lệ; timeout là lỗi |
| “Khóa timestamp đủ cho cursor trong mọi bảng.” | Nhiều hàng có thể trùng timestamp, cần xét toàn bộ clustering key |
| “Consistency level mạnh biến truy vấn scan thành lookup nhanh.” | Consistency và cấu trúc truy vấn là hai vấn đề khác nhau |

## 15. Câu hỏi tự kiểm tra

1. Vì sao `WHERE tenant_id = ?` không đủ để định vị partition của `events_by_tenant_day`?
2. Khác biệt giữa partition key và clustering key trong việc định vị/ràng buộc dữ liệu là gì?
3. Với `PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)`, cách dùng hợp lệ của `occurred_at` và `event_id` trong `WHERE` là gì?
4. Vì sao `occurred_at >= ? AND occurred_at < ?` thường dễ chia cửa sổ hơn dùng hai đầu mút đóng?
5. Tại sao điều kiện `event_id = ?` một mình không phải access pattern phù hợp với bảng sự kiện?
6. Điều kiện nào phải có trước khi dùng range trên clustering column thứ hai?
7. Tại sao `ORDER BY category` không tương đương sắp xếp theo clustering?
8. Khi nào truy vấn nhiều ngày đòi hỏi một bảng/đường đọc khác thay vì chỉ bổ sung `IN`?
9. `ALLOW FILTERING` giải quyết cú pháp hay đảm bảo hiệu năng? Vì sao?
10. Vai trò của `CqlTemplate` khác `CassandraTemplate` và `CqlSession` như thế nào?
11. Vì sao phải dùng bind parameters với UUID, ngày và timestamp?
12. `LIMIT`, page size và paging state khác nhau ở đâu?
13. Vì sao dùng `occurred_at < lastTimestamp` để lấy trang tiếp có thể bỏ sót sự kiện?
14. Một truy vấn hợp lệ trả 0 hàng có ý nghĩa gì, và khác lỗi `ReadTimeout` thế nào?
15. Khi kiểm thử truy vấn, vì sao cần đối chiếu đúng partition key, DDL, clustering order, consistency level và kích thước dữ liệu?

**Ghi nhớ:** khi truy vấn trực tiếp theo primary key của Cassandra, hãy **xác định đủ các thành phần partition key bằng điều kiện phù hợp**, sau đó áp dụng **tiền tố clustering theo thứ tự**, dùng equality trước range và giới hạn kết quả. `CqlTemplate` giúp viết CQL rõ ràng và bind tham số, nhưng không thay đổi cách Cassandra phân bố dữ liệu. Thiết kế truy vấn đúng khóa, kiểm chứng trên schema thật và lựa chọn paging/consistency phù hợp là nền tảng cho ứng dụng Spring Data Cassandra có thể mở rộng.
