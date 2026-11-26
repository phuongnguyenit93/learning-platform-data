# Giảm số cột đọc, lượng dữ liệu truyền và số partition truy cập trong Spring Data Cassandra

Khi tối ưu một truy vấn Apache Cassandra, thời gian trả kết quả không chỉ phụ thuộc vào số dòng (*rows*) mà còn vào **số partition phải truy cập**, **dữ liệu phải đọc/xử lý** và **số byte truyền giữa Cassandra với ứng dụng**. Trong Spring Data Cassandra, một lệnh ở `CassandraRepository` hoặc `CassandraTemplate` cuối cùng vẫn trở thành truy vấn CQL do Java Driver thực thi. Vì vậy, tối ưu hiệu năng bắt đầu từ mô hình bảng và hình dạng truy vấn, sau đó mới đến mapping và API Java.

Bài thuộc chương **Hiệu năng** của module `SPRING_DATA_CASSANDRA`. Mục tiêu là biết cách trả về đúng dữ liệu màn hình hoặc nghiệp vụ cần, giới hạn kết quả và tổ chức bảng theo partition key, tránh biến một thao tác đọc nhỏ thành truy vấn rải rác trên nhiều node hoặc quét một partition quá lớn. Các nguyên tắc này có liên hệ trực tiếp với entity mapping, repository, `CassandraTemplate`, CQL, paging và đặc tính phân tán của Cassandra.

## 1. Tách ba đòn bẩy tối ưu

| Đòn bẩy | Câu hỏi cần trả lời | Tác động thường thấy |
| --- | --- | --- |
| **Giảm cột đọc** (*projection*) | API thật sự cần những cột nào? | Giảm dữ liệu kết quả, công giải mã/ánh xạ object, chi phí serialization |
| **Giảm lượng dữ liệu truyền** | Mỗi request lấy bao nhiêu dòng và bao nhiêu byte? Có phân trang/giới hạn không? | Giảm băng thông, bộ nhớ, thời gian xử lý phía client và áp lực lên kết nối |
| **Giảm partition truy cập** | CQL có ràng buộc đủ partition key không? Có đang dùng `IN`, index hoặc filtering để mở rộng vùng đọc? | Giảm số vị trí lưu trữ/coordinator phải xử lý, giảm fan-out và biến động độ trễ |

Ba đòn bẩy có liên quan nhưng **không thay thế nhau**:

- Chuyển `SELECT *` thành `SELECT id, title` có thể giảm nhiều byte phản hồi, nhưng **không tự sửa** truy vấn thiếu partition key.
- Dùng `LIMIT 20` giảm số dòng trả về, nhưng không nhất thiết giảm tương ứng số row/tombstone phải kiểm tra hoặc số partition phải truy cập.
- Truy vấn đúng một partition vẫn có thể chậm nếu partition đó khổng lồ, có nhiều tombstone hoặc phải đọc payload lớn.
- Truy vấn 20 partition nhỏ có thể thích hợp với nhu cầu có kiểm soát; không phải mục tiêu tuyệt đối là “luôn chỉ một partition”, mà là **số partition dự đoán và giới hạn được**.

Có thể dùng mô hình tư duy:

`chi phí đọc ≈ chi phí tìm partition + chi phí duyệt dữ liệu trong partition + byte truyền về + chi phí xử lý/mapping phía client`.

Đây là mô hình định tính, không phải công thức latency chính xác. Replication, cache, compaction, consistency level, kích thước partition, tombstone, topology mạng và mức tải đồng thời có thể thay đổi kết quả đáng kể.

## 2. Ví dụ xuyên suốt: đọc lịch sử sự kiện khách hàng

Một hệ thống cần hiển thị **50 sự kiện mới nhất của một khách hàng trong một ngày**, chỉ gồm thời điểm, mã sự kiện và tiêu đề. Nội dung đầy đủ (*details*) cùng payload nhị phân phục vụ màn hình chi tiết, không cần có mặt ở danh sách.

Một schema định hướng truy vấn:

~~~sql
CREATE KEYSPACE IF NOT EXISTS activity
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS activity.events_by_customer_day (
    customer_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    title text,
    details text,
    payload blob,
    PRIMARY KEY ((customer_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Script này minh họa **cấu trúc bảng**. Hãy thay tên datacenter và replication factor theo topology thật; cấu hình replication factor 3 không phù hợp để chạy nguyên trạng trên một Cassandra node duy nhất.

Trong bảng trên:

- Partition key là cặp `(customer_id, event_day)`. Hai giá trị xác định **một partition logic** để đọc sự kiện của một khách hàng trong một ngày.
- `event_time` và `event_id` là clustering columns. Chúng tổ chức dữ liệu trong partition; cấu hình `event_time DESC` hỗ trợ đọc sự kiện mới trước.
- `title`, `details`, `payload` là các cột dữ liệu. Màn hình danh sách chỉ cần `title` cùng hai cột định danh/thời gian.
- `event_day` là **bucket theo ngày**, giúp giới hạn độ lớn partition nếu số sự kiện phân bố hợp lý. Bucket theo ngày chỉ phù hợp nếu lượng sự kiện theo từng khách hàng/ngày không khiến partition quá lớn hoặc tạo quá nhiều partition cực nhỏ.

Sơ đồ phạm vi dữ liệu:

~~~mermaid
flowchart TD
    Q["Trang lịch sử: khách A, ngày 2026-11-25"] --> K["Partition key: (A, 2026-11-25)"]
    K --> R1["Sự kiện mới nhất"]
    K --> R2["Sự kiện kế tiếp"]
    K --> R3["... tối đa 50 dòng"]
    Q2["Truy vấn thiếu customer_id / event_day"] --> M["Nhiều partition hoặc truy vấn không được CQL hỗ trợ"]
~~~

### Câu đọc rộng và câu đọc gọn

**Đọc rộng, chỉ nên dùng nếu nghiệp vụ thật sự cần mọi cột:**

~~~sql
SELECT *
FROM activity.events_by_customer_day
WHERE customer_id = ?
  AND event_day = ?
LIMIT 50;
~~~

**Đọc đúng cột cho màn hình danh sách:**

~~~sql
SELECT event_time, event_id, title
FROM activity.events_by_customer_day
WHERE customer_id = ?
  AND event_day = ?
LIMIT 50;
~~~

Hai truy vấn xác định cùng một partition và có cùng giới hạn dòng. Truy vấn thứ hai không trả về `details` và `payload`, nên tránh gửi các cột có thể rất lớn qua kết nối và không phải ánh xạ chúng vào object.

**Điểm cần hiểu đúng:** Cassandra không phải cơ sở dữ liệu cột theo cách mà chọn ít cột luôn tương đương chỉ đọc đúng lượng byte tương ứng từ đĩa. Chi phí đọc thực tế còn phụ thuộc cách lưu trữ, SSTable, cache, compaction và tombstone. Điều chắc chắn hơn là **ít dữ liệu hơn được trả về và giải mã**, còn tiết kiệm I/O phía server cần đo trên workload thật.

## 3. Projection: dùng SELECT danh sách cột thay vì SELECT *

Câu lệnh `SELECT *` thuận tiện khi phát triển nhưng gây chi phí ẩn nếu entity chứa nội dung lớn. Nếu `payload` là file, JSON dài, ảnh thu nhỏ nhúng hoặc binary vài KiB, chi phí băng thông có thể áp đảo phần metadata.

Một ví dụ tính dung lượng gần đúng:

- Mỗi dòng chứa khoảng 2 KiB `details + payload` mà màn hình danh sách không dùng.
- Một request đọc 200 dòng dư thừa khoảng `200 × 2 KiB = 400 KiB` ở mức dữ liệu thô.
- 1.000 request tương tự tạo khoảng 400 MiB dữ liệu thô dư thừa, chưa kể protocol overhead, object allocation và các khác biệt do nén.

Đây chỉ là ví dụ minh họa về mức độ; byte thực tế phải đo từ payload và driver/transport. Không thể suy ra latency chỉ từ con số byte.

### Cách tổ chức read model

Nên tách:

1. **Đối tượng dữ liệu đầy đủ** dùng để lưu hoặc hiển thị trang chi tiết.
2. **Read model dạng tóm tắt** chỉ có các trường màn hình danh sách cần.
3. **Query chuyên biệt** chỉ lấy đúng các cột cho read model.

Không nên lấy entity đầy đủ rồi tạo DTO bằng Java như sau nếu mục tiêu là giảm băng thông:

~~~java
// Cách này vẫn có thể tải đủ các cột của entity từ Cassandra.
List<EventEntity> entities = repository.findBy...(...);
List<EventPreview> previews = entities.stream()
    .map(e -> new EventPreview(e.getEventId(),
                               e.getEventTime(),
                               e.getTitle()))
    .toList();
~~~

DTO ở bước cuối chỉ giúp giảm dữ liệu của **JSON API trả ra ngoài**; nó không làm câu CQL trước đó tự chọn ít cột hơn. Cần kiểm tra câu CQL do repository/template phát ra.

### Truy vấn projection từ ứng dụng Spring bằng CqlSession

Vì Spring Data Cassandra sử dụng DataStax/Apache Cassandra Java Driver, một service có thể tiêm `CqlSession` do Spring Boot quản lý khi cần kiểm soát CQL và mapping read model ở mức thấp:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;

record EventPreview(UUID eventId, Instant eventTime, String title) {}

@Service
public class EventPreviewReader {
    private final CqlSession session;
    private final PreparedStatement latestInDay;

    public EventPreviewReader(CqlSession session) {
        this.session = session;
        this.latestInDay = session.prepare("""
            SELECT event_time, event_id, title
            FROM activity.events_by_customer_day
            WHERE customer_id = ?
              AND event_day = ?
            LIMIT 50
            """);
    }

    public List<EventPreview> findLatest(UUID customerId,
                                         LocalDate day) {
        ResultSet result = session.execute(
            latestInDay.bind(customerId, day));

        List<EventPreview> previews = new ArrayList<>();
        for (Row row : result) {
            previews.add(new EventPreview(
                row.getUuid("event_id"),
                row.getInstant("event_time"),
                row.getString("title")));
        }
        return previews;
    }
}
~~~

Mã minh họa sử dụng Java 17 và Java Driver 4.x, phù hợp với nhiều dự án Spring Boot 3.x. `CqlSession` được container Spring quản lý; **không tạo session mới cho từng request**. Prepared statement giúp tái sử dụng câu CQL có bind variables, an toàn hơn so với nối chuỗi tham số vào câu query. Giá trị ngày dùng `java.time.LocalDate` tương ứng kiểu `date` trong CQL; thời điểm dùng `Instant` tương ứng `timestamp`.

Trong luồng dùng `CassandraTemplate` hoặc `CassandraRepository`, có thể triển khai mục đích tương tự qua query/projection API được phiên bản Spring Data Cassandra hỗ trợ. Hãy đối chiếu CQL thực tế: chỉ đặt tên method là `findPreview` hoặc đổi kiểu trả về DTO **chưa chứng minh** server đã ngừng trả `details` và `payload`. Với projection dựa trên entity, cần kiểm tra cả cách map cột và yêu cầu primary key của phiên bản đang dùng.

## 4. Giới hạn số dòng và bytes trên mỗi request

Không chỉ cần giảm cột, còn cần giới hạn số record một API được quyền yêu cầu. Truy vấn này có thể hợp lý:

~~~sql
SELECT event_time, event_id, title
FROM activity.events_by_customer_day
WHERE customer_id = ?
  AND event_day = ?
LIMIT 50;
~~~

Nhưng nếu API cho client tự nhập `limit=1000000`, mục tiêu giảm dung lượng không còn được đảm bảo. Nên đặt giới hạn cấp ứng dụng cho page size/limit, ví dụ:

~~~java
int normalizedPageSize = Math.min(Math.max(requestedSize, 1), 100);
~~~

Chọn giá trị 100 là **ví dụ chính sách**, cần điều chỉnh bằng số dòng, kích thước cột và mục tiêu latency thật. Trong một partition có sự kiện lớn, 100 dòng có thể vẫn quá nhiều.

### LIMIT khác fetch size/paging

| Cơ chế | Ý nghĩa | Sai lầm thường gặp |
| --- | --- | --- |
| `LIMIT n` trong CQL | Giới hạn tối đa số dòng trả về cho câu truy vấn | Tưởng `LIMIT` luôn giới hạn số partition hoặc I/O server |
| Driver page size / fetch size | Kiểm soát số dòng được lấy mỗi lần trả kết quả qua các trang của driver | Tưởng page size là tổng số dòng cần đọc |
| Cursor/paging state | Cho phép tiếp tục từ trang kế tiếp theo cơ chế phân trang Cassandra | Cố dùng `OFFSET` như SQL quan hệ |
| Giới hạn response ở API | Bảo vệ payload và bộ nhớ phục vụ mỗi request | Cắt danh sách sau khi đã tải toàn bộ dữ liệu |

CQL `LIMIT` và driver page size có thể được dùng cùng nhau: query giới hạn tối đa 500 dòng, driver tải dần các trang, mỗi trang 100 dòng. **Nếu ứng dụng duyệt toàn bộ ResultSet**, Java Driver đồng bộ có thể tự tải trang tiếp theo; cấu hình page size không tự bảo đảm chỉ truyền một trang cho một HTTP request.

Ví dụ giới hạn fetch size bằng Java Driver 4:

~~~java
var bound = latestInDay.bind(customerId, day)
    .setPageSize(20);

var resultSet = session.execute(bound);
// Duyệt resultSet có thể khiến driver tự tải thêm trang.
~~~

Ví dụ trên vẫn dùng CQL `LIMIT 50` của prepared statement trước đó. Nếu muốn API trả đúng **một trang và cursor cho request tiếp theo**, cần quản lý paging state bằng API phù hợp của Java Driver hoặc Spring Data Cassandra, và chỉ đọc số dòng mong muốn. Không được tiếp tục duyệt vô hạn rồi mới cắt về 20 dòng trong controller.

**Paging state** phải đi kèm truy vấn tương ứng, bind parameters, policy và phiên bản/định dạng phù hợp; không xem nó là giá trị ổn định để chuyển qua mọi thay đổi query hoặc driver. Hãy xem nó như cursor mờ (*opaque*), bảo vệ khỏi chỉnh sửa hoặc lạm dụng khi đưa ra ngoài API.

### Tránh COUNT(*) chỉ để hiển thị tổng trang

Nếu API phân trang cần nút “tiếp”, cách thông thường là dùng `Slice`/paging state hoặc cơ chế cursor dựa trên khóa phù hợp, thay vì thực hiện `SELECT COUNT(*)` trên một vùng dữ liệu lớn để tính tổng số trang như nhiều hệ SQL. Đếm lượng dữ liệu lớn có thể gây công đọc đáng kể; Cassandra không bảo đảm phép đếm khối lượng lớn là thao tác metadata O(1).

## 5. Giảm số partition truy cập bằng partition key

Trong Cassandra, partition key quyết định vị trí lưu trữ dữ liệu. Truy vấn cung cấp **đủ tất cả thành phần partition key** thường cho phép driver/coordinator xác định một partition đích hiệu quả.

Với bảng mẫu:

~~~sql
PRIMARY KEY ((customer_id, event_day), event_time, event_id)
~~~

**Một partition, có giới hạn:**

~~~sql
SELECT event_time, event_id, title
FROM activity.events_by_customer_day
WHERE customer_id = ?
  AND event_day = ?
LIMIT 50;
~~~

**Giới hạn thêm phần clustering key khi cần đọc một khoảng:**

~~~sql
SELECT event_time, event_id, title
FROM activity.events_by_customer_day
WHERE customer_id = ?
  AND event_day = ?
  AND event_time < ?
LIMIT 50;
~~~

Ràng buộc `event_time` giúp lấy phần dữ liệu cần trong một partition. Query range phải tuân theo quy tắc CQL đối với clustering columns; với bảng này, khóa clustering đầu tiên là `event_time`.

**Ví dụ không phù hợp với primary key của bảng:**

~~~sql
-- Không có customer_id và event_day để định vị partition.
SELECT event_time, event_id, title
FROM activity.events_by_customer_day
WHERE event_time >= ?;
~~~

Cassandra thường từ chối truy vấn thiếu khóa phù hợp hoặc buộc dùng cơ chế lọc/index nếu schema hỗ trợ. Thêm `ALLOW FILTERING` để ép query chạy có thể dẫn đến số lượng dữ liệu/partition phải xét lớn và khó dự đoán. Không nên coi `ALLOW FILTERING` là công cụ tối ưu hiệu năng.

### Vì sao LIMIT không cứu được truy vấn rải rác?

Giả sử yêu cầu là “50 sự kiện mới nhất của **tất cả khách hàng**”, trong khi bảng được thiết kế theo `(customer_id, event_day)`. Không thể chỉ thêm `LIMIT 50` vào một truy vấn thiếu partition key và giả định Cassandra sẽ tự tìm 50 dòng mới nhất một cách tối ưu. Dữ liệu đã được tổ chức cho truy vấn **theo khách hàng và ngày**, không phải feed toàn hệ thống.

Giải pháp có thể là một read model/bảng khác, ví dụ `recent_events_by_tenant_day`, được viết đồng thời theo kiến trúc denormalization phù hợp. Bảng mới phải được thiết kế partition/bucket cẩn thận, tránh tạo một global hot partition. Đánh đổi gồm chi phí ghi thêm, đồng bộ dữ liệu, vòng đời TTL và mô hình consistency giữa các bảng.

Không có một primary key đơn lẻ tối ưu cho mọi truy vấn. Spring Data Cassandra không loại bỏ yêu cầu này chỉ bằng một repository method.

## 6. Cẩn trọng với IN, nhiều bucket và fan-out

Một truy vấn có điều kiện `IN` trên partition key có thể chạm **nhiều partition**; tùy phiên bản CQL và hình dạng key, cú pháp/thao tác được phép còn chịu các ràng buộc cụ thể. Ví dụ ứng dụng cần đọc dữ liệu của 7 ngày liên tiếp nên dự tính việc đọc tối đa khoảng 7 bucket ngày cho một khách hàng, thay vì mặc định “một truy vấn = một partition”.

Với bài toán “lấy 50 sự kiện mới nhất trong 7 ngày của khách A”, phương án dễ hiểu và kiểm soát là:

1. Tính danh sách tối đa 7 ngày trong phạm vi người dùng được phép xem.
2. Truy vấn các partition theo ngày, bắt đầu từ ngày mới nhất.
3. Lấy một số bản ghi có giới hạn và gộp kết quả đúng thứ tự thời gian.
4. Dừng khi đủ 50 kết quả; tránh đọc hết tất cả ngày khi đã đủ.
5. Giới hạn concurrency và độ dài lookback để không tạo fan-out vô hạn.

Điều này cần logic cursor cẩn thận: paging state của một partition không tự đại diện cho vị trí đang duyệt qua 7 partition. Cursor của API có thể cần ghi nhận ngày hiện tại, khóa sắp xếp và paging state tương ứng. Khi dữ liệu mới xuất hiện trong quá trình phân trang, cần quy định rõ tính nhất quán của trải nghiệm duyệt trang.

~~~mermaid
flowchart TD
    A["API: 50 sự kiện mới nhất của khách A, 7 ngày"] --> B["Ngày 7: partition (A, D7)"]
    B --> C{"Đủ 50 kết quả?"}
    C -->|Có| E["Trả kết quả gọn + cursor"]
    C -->|Không| D["Ngày 6, rồi ngày 5..."]
    D --> C
    C -->|Hết phạm vi| E
~~~

**Đánh đổi giữa số và kích thước partition:** bucket quá dài có thể tạo *wide partition*, quá ngắn làm tăng số partition và số lần truy vấn. Chọn ngày/giờ/tháng dựa vào histogram số row, byte trên mỗi partition, TTL, mô hình đọc và partition hotness thực tế. Không có kích thước bucket cố định đúng cho mọi hệ thống.

### Giới hạn concurrency

Khi buộc đọc nhiều partition, đừng phát hàng nghìn truy vấn song song chỉ để làm “nhanh hơn”. Tăng concurrency có thể vượt connection pool/in-flight request capacity của driver và làm coordinator quá tải. Tăng dần concurrency có giới hạn và đo p95/p99 latency cùng tỷ lệ timeout trước khi mở rộng.

## 7. Phân biệt row ít với partition tốt

Một partition lớn có nhiều row hoặc tombstone vẫn có thể tốn công đọc dù bạn yêu cầu `LIMIT 10`. Ví dụ:

- Bảng dùng TTL ngắn cho hàng triệu sự kiện và truy vấn phần cũ.
- Dữ liệu đã xóa để lại tombstone trước khi compaction dọn được.
- Một khách hàng tạo lượng sự kiện lớn bất thường trong một bucket.
- Truy vấn lọc theo điều kiện ngoài primary key và phải xem xét nhiều row.

Khi đó có thể phát sinh read amplification và cảnh báo tombstone. Cần đánh giá thêm:

- Kích thước partition và phân phối phần đuôi (*tail distribution*), không chỉ trung bình.
- Số row/tombstone quét so với số row trả về.
- Clustering key có khớp cách giới hạn và sort dữ liệu không.
- TTL, compaction strategy và lịch sử ghi/xóa dữ liệu.
- Bảng có chứa payload lớn đáng lẽ nên tách khỏi read model danh sách hay không.

Tách `payload` thành bảng chi tiết khác theo event ID có thể giảm kích thước hàng của bảng danh sách và tránh cả việc payload đi cùng truy vấn thường xuyên. Tuy nhiên, phải đánh giá số lần đọc thêm khi người dùng mở chi tiết và chi phí đồng bộ dữ liệu. Một bảng chỉ chứa bản tóm tắt và một bảng chi tiết là mẫu denormalization thường gặp trong Cassandra khi hai kiểu truy vấn có nhu cầu khác nhau.

## 8. Spring Data Cassandra: chọn API phù hợp

| Tình huống | Hướng dùng API | Điều cần kiểm tra |
| --- | --- | --- |
| CRUD entity đầy đủ theo khóa | `CassandraRepository`, `CassandraTemplate` | Tên bảng, mapping, primary key, số row |
| Danh sách chỉ cần vài cột | Projection/query CQL rõ các cột; Spring Data projection nếu phiên bản hỗ trợ | CQL phát ra thật sự không phải `SELECT *` |
| Query thay đổi theo nhiều điều kiện hợp lệ | `CassandraTemplate` với query object, tiêu chí trên partition/clustering key | Điều kiện có phù hợp primary key/index hay không |
| Read model đặc thù hoặc mapping tối giản | `CqlSession`/prepared CQL qua session của Spring | Bind variables, cột trả về, paging, quản lý session |
| Duyệt dataset theo trang | API paging của Spring Data/Java Driver phù hợp | Cursor, page size, số byte và không giữ toàn bộ data trong bộ nhớ |

Có thể giữ `CassandraRepository` cho thao tác đọc/ghi nguyên entity, trong khi một component khác phục vụ endpoint danh sách bằng projection. Đừng thêm abstraction chỉ để “tối ưu” mà không thể quan sát CQL phía dưới.

### Lưu ý khi entity bị đọc thiếu cột

Nếu dùng một entity đầy đủ để hứng kết quả của `SELECT` chỉ lấy một phần cột, các trường không có trong result có thể mang `null` hoặc default tùy mapping. **Không đưa object đó trở lại `save()` như entity hoàn chỉnh**, vì có thể làm mất dữ liệu ở những cột không được tải. Nên dùng read DTO/projection riêng cho các query tóm tắt, và giữ entity đầy đủ cho đường ghi dữ liệu.

### Bỏ qua cột trong JSON chưa đủ

Các annotation như `@JsonIgnore` hoặc công đoạn chuyển entity sang DTO trong controller chỉ ảnh hưởng dữ liệu ở **lớp HTTP**, không nhất thiết ảnh hưởng số cột Cassandra đã trả cho driver. Tối ưu đúng tầng đòi hỏi kiểm chứng CQL.

## 9. Đo tác động thay vì đoán

Tối ưu chỉ có ý nghĩa khi có số liệu trước/sau trên cùng workload và dữ liệu đại diện. Nên ghi nhận ít nhất:

| Chỉ số | Tại sao cần |
| --- | --- |
| p50, p95, p99 latency của truy vấn và API | Trung bình có thể che những lần đọc chậm do node/partition |
| Số row và tổng byte kết quả trả về | Kiểm chứng mục tiêu giảm dữ liệu |
| Số partition/bucket mỗi thao tác dự kiến truy cập | Phát hiện fan-out từ thiết kế query |
| Page size, số page thực sự tải | Phát hiện việc code vô tình duyệt toàn bộ kết quả |
| Read timeout, unavailable, retry, lỗi driver | Đánh giá tải bổ sung hoặc query không ổn định |
| Tombstone warnings, partition size, latency coordinator/server | Phát hiện chi phí lưu trữ dù client nhận ít row |
| JVM allocation, GC, memory và CPU tại service | Đo tác động mapping entity và JSON serialization |

**Không phải tất cả chỉ số có sẵn mặc định.** Tùy phiên bản Java Driver, Spring Boot/Micrometer và cấu hình cluster, cần bật metrics hoặc tracing phù hợp. Số partition được chạm trong một thao tác thường phải suy ra từ key và logic fan-out, hoặc lấy qua công cụ tracing/diagnostic được cho phép; không nên tuyên bố driver luôn cung cấp sẵn một metric tổng hợp chính xác.

Ở môi trường kiểm thử, có thể dùng truy vấn CQL có bật tracing mẫu:

~~~sql
TRACING ON;

SELECT event_time, event_id, title
FROM activity.events_by_customer_day
WHERE customer_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-25'
LIMIT 50;

TRACING OFF;
~~~

Phần này dùng trong `cqlsh` khi có bảng và dữ liệu thích hợp. Tracing làm tăng overhead, vì vậy chỉ dùng có chọn lọc để phân tích, không bật tràn lan trên production. Truy vấn `SELECT` không có dữ liệu cũng không đại diện cho workload có dữ liệu.

### Quy trình so sánh công bằng

1. Chọn một request đang có triệu chứng cụ thể: ví dụ màn hình danh sách sự kiện p95 chậm và payload lớn.
2. Thu thập CQL, điều kiện lọc, số row, kích thước response, số partition liên quan và latency ở baseline.
3. Thay **một nhóm yếu tố**: `SELECT *` → danh sách cột; sau đó đo lại trên cùng phân phối dữ liệu.
4. Nếu vẫn chậm, kiểm tra partition key, wide partition, tombstone và fan-out; thiết kế read model phù hợp nếu cần.
5. Tăng mức tải dần; so sánh p95/p99, throughput, CPU, GC và lỗi, không chỉ một lượt test.
6. Kiểm chứng tính đúng đắn: kết quả không bị mất cột cần thiết, trùng/lệch thứ tự, sai cursor hoặc sai phạm vi phân quyền khách hàng.

Testcontainers với một Cassandra node phù hợp để xác nhận **CQL, mapping, paging và số cột trả về**. Nó không đủ để kết luận hiệu năng và fan-out trên cluster production đa node. Benchmark phải dùng topology, replication, consistency level, network và dữ liệu đại diện với môi trường mục tiêu.

## 10. Chống các “tối ưu” sai chỗ

| Cách làm dễ mắc | Vì sao có vấn đề | Giải pháp tốt hơn |
| --- | --- | --- |
| `SELECT *` rồi map entity thành DTO | Vẫn có thể truyền mọi cột từ Cassandra | SELECT/projection chỉ gồm cột cần |
| `LIMIT 20` trên query thiếu partition key | Không bảo đảm chỉ xem một partition; query có thể bị từ chối | Thiết kế bảng đúng truy vấn, ràng buộc partition key |
| Luôn tăng page size để giảm số round-trip | Có thể tăng byte/heap/latency mỗi page | Đo theo kích thước row và yêu cầu API |
| Nối chuỗi `IN` với hàng nghìn khóa | Fan-out lớn, dễ gây tải đột biến | Giới hạn keys, chia batch có kiểm soát hoặc thêm read model |
| Dùng `ALLOW FILTERING` làm cách chung | Có thể quét lượng dữ liệu khó kiểm soát | Sửa schema/query hoặc dùng index phù hợp, đánh giá chi phí |
| Đưa tất cả dữ liệu của khách hàng vào một partition | Partition có thể quá lớn hoặc trở thành điểm nóng | Bucket theo thời gian/ngữ cảnh phù hợp |
| Bucket quá nhỏ cho mọi bảng | Tăng số partition và công hợp nhất kết quả | Chọn kích thước bucket theo phân phối dữ liệu |
| `SELECT COUNT(*)` trên nhiều partition để phân trang | Tốn chi phí đọc lớn và không phù hợp offset pagination | Dùng paging state/cursor, hoặc read model cho thống kê |
| Thấy test một node nhanh rồi kết luận production nhanh | Không phản ánh replica, mạng, concurrency và cache | Đo trên topology và dữ liệu đủ đại diện |
| Cắt kết quả trong Java sau khi tải toàn bộ | Băng thông và memory đã phát sinh | Giới hạn query và duyệt trang có kiểm soát |

### Trường hợp dùng index

Secondary index hoặc Storage-Attached Index (SAI, khi phiên bản Cassandra/triển khai hỗ trợ) có thể hữu ích cho một số truy vấn phụ, nhưng không phải cách mặc định để thay thế thiết kế partition key theo workload. Hiệu năng phụ thuộc loại điều kiện, cardinality, phân phối dữ liệu, độ chọn lọc và topology. Cần đo truy vấn thực tế thay vì suy ra “có index thì không quét nhiều partition”.

## 11. Bài tập thực hành

### Bài tập 1: Chỉ hiển thị tiêu đề sự kiện

Endpoint đang chạy:

~~~sql
SELECT * FROM activity.events_by_customer_day
WHERE customer_id = ? AND event_day = ?
LIMIT 100;
~~~

Màn hình chỉ hiển thị thời điểm, mã và tiêu đề. Có nên thêm `@JsonIgnore` cho `details` và `payload` để tối ưu truy vấn Cassandra?

**Gợi ý đáp án:** `@JsonIgnore` chỉ tác động serialization JSON ở API. Thay câu CQL bằng `SELECT event_time, event_id, title ...` và trả read DTO/projection riêng. Kiểm tra query thực tế do Spring Data phát ra để xác nhận server chỉ gửi các cột cần.

### Bài tập 2: Một API đọc 30 ngày

Trang báo cáo cần 50 sự kiện mới nhất trong 30 ngày nhưng API đang đọc toàn bộ 30 partition ngày, tất cả cột và mọi row, rồi `sort` và `take(50)` trong Java.

**Gợi ý đáp án:** Truy vấn theo thứ tự ngày mới nhất, lấy projection ít cột và dừng khi đủ kết quả. Đặt giới hạn rõ cho lookback, số partition và concurrency. Nếu workload lớn/lặp lại, cân nhắc một bảng/read model riêng cho kiểu truy vấn liên ngày; cursor phải phản ánh được ngày/partition đang đọc.

### Bài tập 3: LIMIT nhỏ nhưng latency vẫn cao

Một query theo đủ partition key với `LIMIT 10` đôi khi chậm, nhất là trên vài khách hàng có hàng triệu sự kiện và TTL/delete nhiều.

**Gợi ý đáp án:** Kiểm tra wide partition, tombstone, clustering range, partition hotspot, compaction và workload thực tế. `LIMIT 10` không cam kết server chỉ phải xem 10 bản ghi ở storage. Cân nhắc điều chỉnh bucket, TTL/mô hình xóa và đường đọc.

### Bài tập 4: Phân trang quá lớn

Một endpoint đặt driver page size bằng 10.000 trên bảng có payload 8 KiB và giới hạn CQL nhiều nghìn row.

**Gợi ý đáp án:** Ước tính khối lượng dữ liệu/page có thể rất lớn; giảm cột hoặc tách payload, giới hạn page size theo byte và dữ liệu thực, đo heap/GC/p95. Driver page size chỉ kiểm soát cách fetch, không tự hạn chế tổng số row nếu vẫn duyệt tất cả.

### Bài tập 5: Đổi schema theo truy vấn mới

Yêu cầu mới: “lấy sự kiện gần nhất theo `event_id` mà không biết khách hàng và ngày”. Có thể tái sử dụng `events_by_customer_day` bằng cách bỏ ràng buộc partition key không?

**Gợi ý đáp án:** Không nên dựa vào một truy vấn thiếu partition key như vậy. Cần đánh giá read model bảng tra cứu theo `event_id` (hoặc giải pháp index hỗ trợ và đã đo đạc), kèm chi phí ghi/đồng bộ phù hợp. Bảng hiện tại tối ưu cho lịch sử theo khách hàng và ngày.

## 12. Checklist đánh giá trước khi đưa vào production

- [ ] Mỗi endpoint có **access pattern** rõ: lọc theo gì, sort theo gì, lấy bao nhiêu dòng, trả cột nào.
- [ ] Câu CQL dùng projection đúng dữ liệu cần; không vô tình trả `payload` lớn cho danh sách.
- [ ] Query có partition key phù hợp hoặc fan-out đã được thiết kế, giới hạn và đo lường.
- [ ] Đã cân nhắc cả kích thước partition, hot partition, tombstone và TTL.
- [ ] `LIMIT`, page size và cursor đều có quy tắc rõ; không fetch hết rồi mới cắt trong Java.
- [ ] Mapping entity/projection không làm ghi đè các cột không được load.
- [ ] Câu CQL dùng prepared statement và bind variables, không nối dữ liệu người dùng vào query.
- [ ] Đã đo byte trả về, row/page, p95/p99 latency, timeout, memory và mức tải.
- [ ] Test chức năng được xác nhận bằng Spring Data Cassandra; test tải được tiến hành trên môi trường đại diện.
- [ ] Khi thêm read model/bảng denormalized, đã tính đến chi phí ghi và yêu cầu nhất quán giữa các bảng.

**Ghi nhớ:** Ba mục tiêu **đọc ít cột, truyền ít byte, truy cập ít partition** phải được thiết kế cùng nhau. Trong Spring Data Cassandra, hãy bắt đầu từ access pattern và partition key; dùng projection CQL cho từng mục đích đọc; giới hạn và phân trang đúng cách; cuối cùng đo trên dữ liệu và topology đại diện trước khi kết luận truy vấn đã nhanh hơn.

