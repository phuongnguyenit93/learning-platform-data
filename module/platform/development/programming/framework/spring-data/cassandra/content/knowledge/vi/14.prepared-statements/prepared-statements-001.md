# SimpleStatement, PreparedStatement và BoundStatement

Trong **Apache Cassandra**, mọi truy vấn được thực thi dưới dạng **CQL (Cassandra Query Language)**. Khi ứng dụng dùng **Spring Data Cassandra**, ta có thể làm việc qua entity mapping, repository, `CassandraTemplate`, `CqlTemplate` hoặc trực tiếp với **Java Driver**. Ở tầng Java Driver 4.x, ba khái niệm cốt lõi cần phân biệt là **`SimpleStatement`, `PreparedStatement` và `BoundStatement`**.

Ba khái niệm này không phải ba kiểu bảng hay ba ngôn ngữ truy vấn khác nhau. Chúng thể hiện **cách ứng dụng chuẩn bị, gắn tham số, gửi và tái sử dụng một câu CQL**. Hiểu đúng giúp giảm chi phí chuẩn bị các truy vấn lặp lại, bind đúng kiểu dữ liệu, hạn chế lỗi ghép chuỗi và cấu hình paging, consistency, timeout một cách có chủ đích.

Bài thuộc chương **Prepared statement** của module **SPRING_DATA_CASSANDRA**. Ví dụ dùng API phổ biến của **DataStax/Apache Cassandra Java Driver 4.x**; tên class, overload hoặc cơ chế tự động cấu hình có thể thay đổi giữa các phiên bản Spring Boot, Spring Data và driver. Hãy đối chiếu API của phiên bản đang triển khai.

## 1. Ba đối tượng giải quyết ba vấn đề khác nhau

| Đối tượng | Ý nghĩa | Thường dùng để |
| --- | --- | --- |
| **`SimpleStatement`** | Một câu CQL có thể thực thi trực tiếp, kèm giá trị tham số và các tùy chọn của request | Truy vấn ít lặp lại, thao tác đơn giản hoặc câu CQL chưa cần prepare |
| **`PreparedStatement`** | Mô tả câu CQL đã được **chuẩn bị** với metadata về bind markers/kiểu tham số | Tái sử dụng cùng mẫu CQL qua nhiều lần gọi |
| **`BoundStatement`** | Một lần **gắn giá trị cụ thể** vào một `PreparedStatement`, kèm tùy chọn thực thi | Gửi truy vấn đã chuẩn bị với dữ liệu của từng request |

~~~text
Nhánh 1 — Simple statement
Ứng dụng ── SimpleStatement(CQL + giá trị) ──> session.execute(...)
                              |
                              └── server xử lý câu lệnh tại lần thực thi

Nhánh 2 — Prepared statement
Ứng dụng ── session.prepare(CQL có markers) ──> PreparedStatement
                                                   |
              Request A ── bind(A) ───────────────> BoundStatement A
              Request B ── bind(B) ───────────────> BoundStatement B
                                                   |
                                             session.execute(...)
~~~

**Phân biệt quan trọng:** `PreparedStatement` chưa mang đầy đủ giá trị của từng request. Nó là **mẫu câu lệnh đã được chuẩn bị**; `BoundStatement` mới gắn giá trị để thực thi. `SimpleStatement` cũng có thể bind tham số an toàn mà **không cần** chuẩn bị thành `PreparedStatement`.

## 2. Chuẩn bị một bảng Cassandra cho ví dụ

Giả sử cần lấy các đơn hàng mới nhất của **một khách hàng trong một ngày**. Thiết kế bảng được dẫn dắt bởi truy vấn đó:

~~~sql
CREATE KEYSPACE IF NOT EXISTS commerce_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS commerce_ks.orders_by_customer_day (
    customer_id  uuid,
    order_day    date,
    placed_at    timestamp,
    order_id     uuid,
    status       text,
    total_amount decimal,
    PRIMARY KEY ((customer_id, order_day), placed_at, order_id)
) WITH CLUSTERING ORDER BY (placed_at DESC, order_id DESC);
~~~

Đây là schema minh họa; tên datacenter `dc1` và RF = 3 phải được điều chỉnh theo cluster thực tế và số node/replica khả dụng. Ở production, quản lý schema bằng quy trình triển khai CQL thay vì mặc định tạo bảng mỗi lần ứng dụng khởi động.

Các thành phần khóa:

- `(customer_id, order_day)` là **composite partition key**: Cassandra dùng nó để xác định token và replica chịu trách nhiệm.
- `placed_at` và `order_id` là **clustering columns**, xác định hàng và thứ tự **trong partition**.
- Cùng một khách hàng, ngày khác nhau nằm ở các partition khác nhau.

Truy vấn chúng ta sẽ thực thi lặp đi lặp lại:

~~~sql
SELECT placed_at, order_id, status, total_amount
FROM commerce_ks.orders_by_customer_day
WHERE customer_id = ?
  AND order_day = ?
LIMIT 100;
~~~

Hai dấu `?` là **bind markers** theo vị trí, tương ứng với kiểu CQL `uuid` và `date`. Một truy vấn đúng kiểu và bind an toàn vẫn có thể sai thiết kế nếu không cung cấp đủ partition key; prepared statement không thay thế việc thiết kế bảng theo truy vấn.

## 3. SimpleStatement: gửi CQL trực tiếp

Trong Java Driver 4.x, ví dụ một câu lệnh không có tham số:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement statement = SimpleStatement.newInstance(
    "SELECT data_center FROM system.local"
);

ResultSet resultSet = session.execute(statement);
~~~

`session` là một bean `CqlSession` đã được cấu hình và quản lý vòng đời phù hợp. Câu truy vấn ở ví dụ chỉ đọc thông tin node cục bộ từ bảng hệ thống; nó không đại diện cho truy vấn nghiệp vụ quy mô lớn.

Với tham số nghiệp vụ, **SimpleStatement vẫn có thể gắn giá trị**, không cần nối chuỗi:

~~~java
import java.time.LocalDate;
import java.util.UUID;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

UUID customerId = UUID.fromString(
    "550e8400-e29b-41d4-a716-446655440000"
);
LocalDate orderDay = LocalDate.of(2026, 11, 25);

SimpleStatement simple = SimpleStatement.builder(
    "SELECT placed_at, order_id, status, total_amount " +
    "FROM commerce_ks.orders_by_customer_day " +
    "WHERE customer_id = ? AND order_day = ? LIMIT 100"
).addPositionalValues(customerId, orderDay)
 .setPageSize(25)
 .build();

ResultSet rows = session.execute(simple);
~~~

Thao tác này gửi **CQL cùng các giá trị bound**. Nó tránh việc tự tạo literal `uuid`, `date` hoặc chuỗi CQL từ input, nhưng **không tạo một prepared query phía server để tái sử dụng theo cách của `session.prepare(...)`**.

### SimpleStatement không đồng nghĩa với ghép chuỗi không an toàn

Hai ví dụ sau **khác nhau**:

~~~java
// NÊN: bind giá trị theo kiểu được driver hỗ trợ.
SimpleStatement safe = SimpleStatement.newInstance(
    "SELECT * FROM commerce_ks.orders_by_customer_day " +
    "WHERE customer_id = ? AND order_day = ? LIMIT 20",
    customerId, orderDay
);

// KHÔNG NÊN: ghép trực tiếp input vào cú pháp CQL.
String unsafeCql = "SELECT * FROM commerce_ks.orders_by_customer_day " +
    "WHERE customer_id = " + requestCustomerId +
    " AND order_day = '" + requestDay + "'";
~~~

Nguy cơ của cách ghép chuỗi là injection, lỗi escaping và sai kiểu dữ liệu, không phải bản thân tên class `SimpleStatement`. **Prepared statement thường là lựa chọn tốt cho mẫu truy vấn lặp lại**, còn simple statement có binding vẫn là cách gửi input an toàn khi được sử dụng đúng.

## 4. PreparedStatement: chuẩn bị mẫu truy vấn một lần

Đối với truy vấn được gọi thường xuyên, dùng `CqlSession.prepare(...)`:

~~~java
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

PreparedStatement latestOrders = session.prepare(
    "SELECT placed_at, order_id, status, total_amount " +
    "FROM commerce_ks.orders_by_customer_day " +
    "WHERE customer_id = ? AND order_day = ? LIMIT 100"
);
~~~

Khi chuẩn bị, driver và Cassandra làm việc với mẫu CQL có marker; server phân tích/chuẩn bị câu lệnh, và driver nhận metadata cần thiết để bind theo đúng kiểu. Câu lệnh được **định danh** để có thể thực thi nhiều lần với các tham số khác nhau mà không phải gửi lại toàn bộ chuỗi CQL theo kiểu unprepared cho mỗi request.

Ưu điểm có thể có:

1. Tránh lặp lại chi phí parse/prepare ở các lần thực thi cùng mẫu CQL.
2. Metadata của marker giúp driver kiểm tra/encode các giá trị bound theo kiểu CQL.
3. Câu CQL cố định, rõ ràng hơn khi kiểm soát các tham số nghiệp vụ.
4. Dễ tái sử dụng cho nhiều request và áp dụng tùy chọn riêng trên mỗi `BoundStatement`.

**Không nên gọi `session.prepare(...)` trong mỗi lần nhận HTTP request** nếu query không đổi. Việc prepare có chi phí phối hợp với cluster; dù driver có khả năng cache một phần, chiến lược rõ ràng vẫn là chuẩn bị theo vòng đời ứng dụng hoặc cache theo **mẫu CQL ổn định**.

**Lưu ý:** prepared statement không tự đảm bảo truy vấn nhanh. Một prepared query thiếu partition key, quét nhiều partition, đọc tombstone hoặc trả dữ liệu quá lớn vẫn có thể chậm. Việc prepare chỉ tối ưu **cách thực thi mẫu CQL**, không sửa một access pattern sai.

## 5. BoundStatement: gắn tham số cho từng lần chạy

Sau khi có `PreparedStatement`, dùng `bind(...)` để tạo statement cho request cụ thể:

~~~java
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

BoundStatement bound = latestOrders.bind(customerId, orderDay);

ResultSet rows = session.execute(bound);
~~~

Giá trị thứ nhất gắn với marker `customer_id = ?` và phải tương thích CQL `uuid`; giá trị thứ hai gắn với `order_day = ?` và phải tương thích CQL `date`.

Ví dụ hai request:

~~~java
BoundStatement forDay25 = latestOrders.bind(
    customerId, LocalDate.of(2026, 11, 25)
);

BoundStatement forDay26 = latestOrders.bind(
    customerId, LocalDate.of(2026, 11, 26)
);

ResultSet day25 = session.execute(forDay25);
ResultSet day26 = session.execute(forDay26);
~~~

**Cùng một `PreparedStatement` nhưng có hai `BoundStatement` khác nhau.** Do phần CQL/kiểu marker không đổi, ứng dụng không cần prepare một câu mới chỉ vì khách hàng hay ngày thay đổi.

Trong Java Driver 4.x, các statement được thiết kế theo hướng **immutable**; những setter cấu hình/bind trên `BoundStatement` thường **trả về một statement mới**. Hãy giữ giá trị trả về, không viết code theo giả định setter luôn thay đổi tại chỗ như Java bean.

~~~java
// ĐÚNG: giữ object sau khi thêm execution options.
BoundStatement configured =
    latestOrders.bind(customerId, orderDay)
                .setPageSize(25);

// Dễ sai nếu tưởng setter tự đổi bound object trước đó.
BoundStatement original = latestOrders.bind(customerId, orderDay);
original.setPageSize(25);  // Bỏ qua object được trả về.
~~~

Trong ví dụ thứ hai, khi gửi `original`, đừng kỳ vọng page size đã được cập nhật. Hành vi object cụ thể cần đối chiếu API driver hiện dùng; khuyến nghị dùng chain hoặc gán lại giá trị.

## 6. Bind theo vị trí và bind theo tên

### Marker theo vị trí

Với CQL:

~~~sql
WHERE customer_id = ? AND order_day = ?
~~~

gọi:

~~~java
BoundStatement bound = latestOrders.bind(customerId, orderDay);
~~~

**Thứ tự bắt buộc khớp.** Nếu đổi nhầm `LocalDate` và `UUID`, driver có thể báo lỗi codec/binding. Nguy hiểm hơn, với hai marker **cùng kiểu dữ liệu**, tráo thứ tự có thể vẫn thực thi nhưng query trả dữ liệu sai hoặc rỗng.

### Marker có tên

Khi có nhiều tham số, marker đặt tên có thể giúp tránh sai thứ tự:

~~~sql
SELECT placed_at, order_id, status
FROM commerce_ks.orders_by_customer_day
WHERE customer_id = :customer_id
  AND order_day = :order_day
LIMIT 100;
~~~

Java Driver 4.x có thể bind bằng metadata tên marker:

~~~java
PreparedStatement named = session.prepare(
    "SELECT placed_at, order_id, status " +
    "FROM commerce_ks.orders_by_customer_day " +
    "WHERE customer_id = :customer_id " +
    "AND order_day = :order_day LIMIT 100"
);

BoundStatement byName = named.bind()
    .setUuid("customer_id", customerId)
    .setLocalDate("order_day", orderDay);
~~~

Nếu tên marker xuất hiện lặp lại, cần chú ý semantics của binding theo tên và metadata của phiên bản driver; tránh thiết kế câu CQL nhập nhằng khi một tên được tái sử dụng cho nhiều ý nghĩa khác nhau.

### Có thể bind tên bảng hoặc tên cột không?

**Không.** Bind markers đại diện **giá trị**, không phải những cấu trúc cú pháp như keyspace, table name, column name hoặc thứ tự `ORDER BY` tùy ý. Ví dụ sau không hợp lệ về ý định:

~~~sql
-- KHÔNG thay tên bảng bằng ? theo cách bind giá trị.
SELECT * FROM ? WHERE customer_id = ?;
~~~

Nếu cần chọn bảng theo một danh sách nghiệp vụ, hãy dùng **whitelist tên bảng được kiểm soát** và tạo những mẫu CQL hợp lệ, thay vì nối chuỗi tên bảng do client cung cấp.

## 7. Bảng so sánh vòng đời và hiệu năng

| Góc nhìn | SimpleStatement | PreparedStatement + BoundStatement |
| --- | --- | --- |
| Mẫu CQL | Gắn với statement được thực thi | Mẫu CQL được chuẩn bị trước, không chứa giá trị request |
| Bind tham số | Có thể, qua API simple statement | Bắt buộc khi câu prepared có markers |
| Chuẩn bị trước ở server | Không theo đường `session.prepare(...)` | Có, qua prepare và metadata |
| Tái sử dụng | Có thể tái tạo statement hoặc dùng cùng query text | Reuse `PreparedStatement`, tạo bound cho từng request |
| Chi phí thiết lập | Thường ít hơn nếu chạy một lần | Có chi phí prepare ban đầu |
| Truy vấn lặp lại nhiều lần | Có thể chạy, nhưng mất lợi ích prepare/cache phía server | Thường là lựa chọn phù hợp |
| Loại bỏ injection | **Có nếu bind đúng giá trị**; không an toàn nếu ghép chuỗi | Có nếu bind đúng giá trị; vẫn phải whitelist identifier |
| Giới hạn CQL/partition key | Không thay đổi | Không thay đổi |
| Timeout/CL/paging | Có thể cấu hình trên statement | Có thể cấu hình trên bound statement |

**Quy tắc thực hành:** dùng prepared statement cho những mẫu SELECT/INSERT/UPDATE thường xuyên, cố định cấu trúc và thay giá trị mỗi lần. Với câu lệnh ít lặp, simple statement có bind values có thể là lựa chọn đủ tốt. Đừng đánh đổi thiết kế khóa và giới hạn kết quả chỉ để tối ưu giai đoạn parse của câu CQL.

## 8. Kết nối PreparedStatement với Spring Boot

Spring Boot với starter đồng bộ có thể cung cấp `CqlSession` dưới dạng bean được quản lý:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra</artifactId>
</dependency>
~~~

Ví dụ cấu hình:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: dc1
    keyspace-name: commerce_ks
    schema-action: none
~~~

§schema-action: none§ nghĩa là keyspace/bảng phải được quản lý trước; việc chuẩn bị statement cũng đòi bảng/cột mà query nhắc tới đã tồn tại. Không nên thiết kế một bean prepare sớm hơn quy trình migration schema mà chính nó phụ thuộc.

Ví dụ service chuẩn bị một lần ở thời điểm khởi tạo:

~~~java
import java.time.LocalDate;
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import org.springframework.stereotype.Service;

@Service
public class OrderHistoryReader {

    private final CqlSession session;
    private final PreparedStatement latestOrders;

    public OrderHistoryReader(CqlSession session) {
        this.session = session;
        this.latestOrders = session.prepare(
            "SELECT placed_at, order_id, status, total_amount " +
            "FROM commerce_ks.orders_by_customer_day " +
            "WHERE customer_id = ? AND order_day = ? LIMIT 100"
        );
    }

    public ResultSet findLatest(UUID customerId, LocalDate day) {
        return session.execute(
            latestOrders.bind(customerId, day)
        );
    }
}
~~~

**Lưu ý thiết kế:** trả trực tiếp `ResultSet` từ service chỉ để minh họa vòng đời statement. Trong ứng dụng thật, nên chuyển hàng thành DTO/model và quản lý số hàng, trang kết quả, logging và timeout. Có thể tạo `PreparedStatement` qua một bean `@Bean` hoặc một lớp query chuyên trách, miễn là tránh prepare lặp lại trên mỗi request.

Khi Spring Data Cassandra thực hiện các thao tác qua `CassandraRepository`, `CassandraTemplate` hay `CqlTemplate`, framework có thể quản lý việc sinh/bind/prepare statement theo API và version; **không mặc định** rằng mọi lời gọi đều dùng đúng một prepared statement được cache như ví dụ Java Driver. Nếu cần kiểm soát chi tiết, hãy kiểm tra câu CQL, driver metrics và các API được version dự án hỗ trợ.

## 9. Trả kết quả: kiểu Java và codec phải đúng CQL

Driver sử dụng **codec** để mã hóa giá trị Java sang CQL khi bind, rồi giải mã các cột trong kết quả. Ví dụ:

| Kiểu CQL | Kiểu Java hay dùng trong Driver 4.x |
| --- | --- |
| `uuid` | `UUID` |
| `date` | `LocalDate` |
| `timestamp` | `Instant` |
| `text` | `String` |
| `decimal` | `BigDecimal` |
| `boolean` | `Boolean` / `boolean` |

Đọc một số cột:

~~~java
for (Row row : rows) {
    Instant placedAt = row.getInstant("placed_at");
    UUID orderId = row.getUuid("order_id");
    String status = row.getString("status");
    BigDecimal amount = row.getBigDecimal("total_amount");
    // Chuyển sang DTO nếu cần, không log dữ liệu nhạy cảm.
}
~~~

Để biên dịch cần import `Row`, `Instant`, `BigDecimal` và các lớp tương ứng. Trong Driver 4.x, `Row.getInstant` phù hợp với CQL `timestamp`, còn `Row.getLocalDate` phù hợp với CQL `date`.

### Spring Data converter khác driver codec

Một custom `@WritingConverter` của Spring Data có thể chuyển domain enum `OrderStatus.PAID` thành `"paid"` khi lưu entity. Nhưng nếu bạn dùng `CqlSession` và prepared statement **trực tiếp**, driver không tự tìm converter của Spring Data. Bạn cần bind `String` đã chuẩn hóa, hoặc đăng ký codec cho kiểu Java riêng theo quy tắc driver.

Tương tự, nếu CQL lưu `text` chữ thường mà parameter `WHERE` lại bind `"PAID"`, truy vấn equality có thể không tìm thấy hàng. **Prepared statement kiểm soát kiểu bind, không tự chuẩn hóa ngữ nghĩa giá trị**.

## 10. Tùy chọn thực thi trên BoundStatement

Mỗi request có thể cần page size, consistency và timeout riêng. Ví dụ:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import java.time.Duration;

BoundStatement statement = latestOrders.bind(customerId, orderDay)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(25)
    .setTimeout(Duration.ofSeconds(3))
    .setIdempotent(true);

ResultSet resultSet = session.execute(statement);
~~~

Đoạn này minh họa **tùy chọn cho một câu SELECT**; nó không phải cấu hình bắt buộc cho mọi môi trường.

| Tùy chọn | Vai trò | Điều cần lưu ý |
| --- | --- | --- |
| `setConsistencyLevel(...)` | Số replica cần đáp ứng theo CL | RF, datacenter và yêu cầu ứng dụng quyết định CL phù hợp |
| `setPageSize(...)` | Số hàng mỗi lần fetch trên đường phân trang | Không đồng nghĩa `LIMIT` và không sửa partition quá lớn |
| `setTimeout(...)` | Giới hạn thời gian xử lý request ở phía driver | Timeout không chứng minh write đã thất bại hoàn toàn |
| `setIdempotent(...)` | Khai báo tính idempotent để driver quyết định retry/speculative behavior | Chỉ bật khi thao tác **thực sự an toàn khi lặp lại** |

**Không đặt `setIdempotent(true)` tùy tiện cho mọi ghi.** Một thao tác tạo ID mới, thay đổi list, counter hoặc có tác dụng phụ ngoài Cassandra có thể không an toàn khi retry. `SELECT` thuần đọc thường có tính idempotent phù hợp, nhưng vẫn cần hiểu semantics truy vấn và phiên bản driver.

## 11. LIMIT, page size và paging state là ba khái niệm khác nhau

Trong ví dụ:

~~~sql
SELECT placed_at, order_id, status
FROM commerce_ks.orders_by_customer_day
WHERE customer_id = ? AND order_day = ?
LIMIT 100;
~~~

Nếu `BoundStatement` có `setPageSize(25)`:

- `LIMIT 100` giới hạn **tối đa 100 hàng** cho query, không nói rằng cả 100 hàng sẽ xuất hiện trong một network response.
- Page size 25 cho phép driver nhận dữ liệu theo những đợt có kích thước mục tiêu khoảng 25 hàng, tùy cơ chế driver/server.
- Với API `ResultSet` đồng bộ, khi code duyệt qua kết quả, driver có thể **fetch thêm page**; không nên nhầm “đã lấy 25 hàng đầu” với “query chỉ có 25 hàng”.
- Trong async/reactive, việc lấy trang tiếp theo sử dụng API thích hợp của driver/framework và trạng thái continuation.

**Paging state** thuộc về câu truy vấn và các tham số/điều kiện cụ thể. Không lấy paging state của `customer_id=A, order_day=25` rồi dùng cho `customer_id=B, order_day=26`. Nếu đưa continuation token cho client, cân nhắc ký/mã hóa, giới hạn thời gian sống và ràng buộc nó với bộ lọc ban đầu.

Paging không tương đương `OFFSET 1000` của SQL và không biến một partition cực lớn thành nhỏ. Với nhiều bucket ngày hoặc nhiều shard, ứng dụng còn phải ghép kết quả và quản lý continuation **của từng partition/luồng**.

## 12. Tái sử dụng PreparedStatement trong hệ phân tán

Chuẩn bị query ở một coordinator không có nghĩa rằng mọi node mãi mãi giữ đủ metadata prepared trong bộ nhớ. Trong quá trình vận hành có thể xảy ra:

- Một node restart hoặc mất trạng thái prepared.
- Yêu cầu được route tới node chưa có statement tương ứng.
- Thay đổi schema làm metadata của statement không còn phù hợp.
- Client reconnect hoặc triển khai lại ứng dụng.

Java Driver có cơ chế quản lý cache/prepare trên các node và có thể **re-prepare** khi nhận tín hiệu statement chưa được chuẩn bị (chẳng hạn `UNPREPARED`), tùy phiên bản/cấu hình. Ứng dụng vẫn cần xử lý lỗi, timeout và những thay đổi schema không tương thích; không giả định re-prepare sẽ sửa được câu query tham chiếu cột đã xóa hoặc khóa đã thay đổi.

### Prepare khi nào?

**Phù hợp:** lúc khởi tạo service (sau khi schema sẵn sàng), hoặc thông qua cache nội bộ keyed theo **CQL text và các yếu tố cấu hình có liên quan**.

**Không phù hợp:** tạo một prepared statement mới với literal chứa `customer_id` hoặc timestamp khác nhau cho mỗi request. Cách đó làm mất mục tiêu tái sử dụng:

~~~java
// KHÔNG NÊN: mỗi lần lại tạo mẫu CQL khác vì nối giá trị.
String query = "SELECT ... WHERE customer_id = " + customerId;
PreparedStatement p = session.prepare(query);
~~~

Thay bằng **một mẫu CQL có bind markers** và các `BoundStatement` khác nhau theo request.

### Prepare có thay thế schema migration?

**Không.** Nếu bảng hoặc cột chưa tồn tại, `prepare` có thể báo lỗi. Nếu schema đổi (đặc biệt primary key hoặc kiểu cột), phải điều chỉnh query/mapping, áp dụng migration và bảo đảm schema agreement. Nhiều instance ứng dụng chạy code V1/V2 cùng lúc càng cần cơ chế rollout tương thích, không chỉ chờ driver tự re-prepare.

## 13. Prepared statement không sửa được partition key sai

Xét hai câu CQL:

~~~sql
-- Query có đủ partition key.
SELECT placed_at, order_id
FROM commerce_ks.orders_by_customer_day
WHERE customer_id = ? AND order_day = ?
LIMIT 100;

-- Query không xác định partition, không phù hợp bảng ví dụ.
SELECT placed_at, order_id
FROM commerce_ks.orders_by_customer_day
WHERE status = ?;
~~~

Câu thứ hai không trở nên hợp lệ hoặc nhanh hơn chỉ vì được `session.prepare(...)`. Cassandra vẫn dùng partition key, clustering key và index để quyết định cách truy cập. Nếu ứng dụng cần liệt kê đơn theo status trên toàn hệ thống, hãy thiết kế **bảng đọc theo status/ngày**, index phù hợp phiên bản/workload, hoặc hệ phân tích riêng.

Tương tự:

- `ORDER BY total_amount` không được thêm tự do chỉ vì câu query được prepare.
- Không có `JOIN` tổng quát như hệ cơ sở dữ liệu quan hệ.
- `ALLOW FILTERING` có thể gây quét dữ liệu đắt đỏ; không là giải pháp mặc định.
- Partition có nhiều triệu hàng vẫn lớn dù SELECT dùng bind và paging.
- Tăng replication factor không chia một partition key thành nhiều partition độc lập.

**Ưu tiên thiết kế bảng theo truy vấn**, tính số hàng/byte và lưu lượng đỉnh của từng partition trước khi tối ưu cách gửi prepared statement.

## 14. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Lỗi bind value | Java type không khớp CQL type hoặc thiếu codec | Đối chiếu schema, metadata marker và codec |
| Query không tìm thấy hàng | Bind nhầm thứ tự, sai ngày/tenant, sai format giá trị | Log an toàn loại/giá trị chuẩn hóa, kiểm tra khóa đã ghi |
| `UNPREPARED` hoặc prepared query thất bại sau node restart | Node chưa có prepared metadata | Kiểm tra driver re-prepare, topology, log và phiên bản |
| Prepare báo unknown column/table | Schema chưa sẵn sàng hoặc khác version | Kiểm tra migration, keyspace, schema agreement |
| Memory/cache nhiều prepared entries | Chuỗi CQL thay đổi với từng input/literal | Dùng một mẫu CQL và bind giá trị |
| `SimpleStatement` bị xem là “nguy hiểm” | Nhầm việc simple với việc nối chuỗi | Dùng SimpleStatement **có bind values** |
| Bỏ qua kết quả setter trên BoundStatement | Driver 4 dùng object immutable | Gán lại hoặc chain setter |
| Trang kết quả trống/bị lặp | Dùng paging state sai query hoặc input thay đổi | Gắn token với statement, parameter, filter |
| Driver retry ghi không an toàn | Đánh dấu idempotent sai | Đánh giá semantics và tạo ID ổn định |
| Câu query vẫn chậm dù prepared | Partition lớn, tombstone, CL cao, nhiều dữ liệu | Đo p95/p99, phân phối tải và access pattern |

### Phương pháp chẩn đoán theo thứ tự

1. **Kiểm tra schema CQL**: keyspace, bảng, partition/clustering key và kiểu column.
2. **Kiểm tra text của mẫu CQL**: không có tên cột sai, không thiếu partition key.
3. **Kiểm tra bind metadata**: đúng số lượng, thứ tự, tên và kiểu marker.
4. **Kiểm tra dữ liệu sau conversion**: ngày UTC/bucket, UUID, enum text, decimal.
5. **Kiểm tra driver/session**: local datacenter, TLS/auth, timeout, re-prepare.
6. **Kiểm tra hiệu năng query**: số partition, số hàng, tombstone, paging và consistency.

Để quan sát truy vấn, dùng logging/metrics/tracing có giới hạn trong môi trường phù hợp, tránh ghi token, thông tin cá nhân hoặc toàn bộ giá trị CQL nhạy cảm vào log production.

## 15. Bài tập thực hành

### Bài tập A — Từ simple sang prepared

Ban đầu code tạo một `SimpleStatement` cho mỗi lần người dùng mở lịch sử đơn trong một ngày. Hãy chuyển sang prepare một lần:

~~~java
// Mẫu query, đặt tại vị trí dùng chung trong service.
PreparedStatement prepared = session.prepare(
    "SELECT placed_at, order_id, status " +
    "FROM commerce_ks.orders_by_customer_day " +
    "WHERE customer_id = ? AND order_day = ? LIMIT 50"
);

// Với mỗi request, chỉ bind giá trị khác nhau.
BoundStatement requestStatement = prepared.bind(customerId, orderDay)
    .setPageSize(20);

ResultSet result = session.execute(requestStatement);
~~~

**Kiểm tra:** thay `customerId`/`orderDay` trong 10 lần gọi nhưng câu CQL vẫn là một mẫu. Đảm bảo query trả dữ liệu đúng partition và không tạo 10 prepared statement text khác nhau.

### Bài tập B — Phát hiện bind sai kiểu

Giả sử:

~~~sql
WHERE customer_id = ? AND order_day = ?
~~~

Một người viết:

~~~java
// Sai thứ tự và sai kiểu:
BoundStatement wrong = prepared.bind(orderDay, customerId);
~~~

**Phân tích:** marker thứ nhất cần `uuid`, marker thứ hai cần `date`, nên driver có thể từ chối bind do không tìm thấy codec tương thích. Sửa bằng `prepared.bind(customerId, orderDay)` hoặc marker có tên rõ ràng.

### Bài tập C — Phân trang và consistency

Truy vấn có `LIMIT 100`, statement có `setPageSize(25)` và `LOCAL_QUORUM`:

**Câu hỏi:** Có phải Cassandra chỉ trả 25 hàng cho toàn bộ query không? Và `LOCAL_QUORUM` có thay đổi thứ tự clustering không?

**Trả lời:** Không. Page size là kích thước fetch mục tiêu, còn `LIMIT 100` là giới hạn tổng hàng. `LOCAL_QUORUM` quy định mức phản hồi từ replica, **không thay đổi** partition key hay thứ tự clustering.

## 16. Tự kiểm tra

**Câu 1.** `PreparedStatement` có chứa riêng giá trị `customerId` của từng HTTP request không?

**Đáp án:** Không. Nó là mẫu query được chuẩn bị; mỗi request tạo `BoundStatement` với giá trị cụ thể.

**Câu 2.** Có thể bind tham số an toàn với `SimpleStatement` mà không dùng `PreparedStatement` không?

**Đáp án:** Có. Java Driver hỗ trợ simple statement kèm positional/named values; tránh tự nối dữ liệu input vào chuỗi CQL.

**Câu 3.** Vì sao không nên `prepare(...)` lại ở mỗi request với cùng mẫu CQL?

**Đáp án:** Prepare có chi phí và prepared statement có mục đích tái sử dụng. Nên cache hoặc giữ mẫu query ổn định trong vòng đời service.

**Câu 4.** Thao tác `original.setPageSize(25);` mà không lưu kết quả có an toàn trong Java Driver 4.x không?

**Đáp án:** Không nên. Statement API mang semantics immutable; hãy dùng `original = original.setPageSize(25)` hoặc chain setter.

**Câu 5.** Tại sao một prepared query `WHERE status = ?` có thể không phù hợp bảng `orders_by_customer_day`?

**Đáp án:** Vì bảng được phân vùng theo `(customer_id, order_day)`; prepared statement không tạo ra index hay thay đổi khả năng định tuyến dữ liệu của Cassandra.

**Câu 6.** Java Driver trực tiếp có tự sử dụng mọi custom converter của Spring Data Cassandra khi bind enum không?

**Đáp án:** Không. Driver dùng codec/kiểu Java được hỗ trợ; nếu domain cần chuyển đổi đặc biệt, ứng dụng phải chuẩn hóa giá trị trước hoặc cấu hình driver codec thích hợp.

---

**Ghi nhớ:** `SimpleStatement` biểu diễn một câu CQL có thể thực thi trực tiếp (vẫn có thể bind tham số); `PreparedStatement` là mẫu CQL được chuẩn bị để tái sử dụng; và `BoundStatement` là một lần bind giá trị cụ thể cho mẫu đó. Trong Spring Data Cassandra, chuẩn bị/bind đúng cách giúp giảm lỗi và chi phí lập lại, nhưng **không thay đổi** các nguyên tắc nền: thiết kế bảng theo truy vấn, cung cấp đủ partition key, chọn consistency phù hợp và phân trang có giới hạn.
