# Tái sử dụng prepared statement theo vòng đời session trong Spring Data Cassandra

## 1. Bài toán: một câu CQL được gọi hàng nghìn lần

Một dịch vụ Spring Boot cần đọc đơn hàng theo `order_id`. Trong một ngày, cùng một câu CQL có thể được thực thi hàng trăm nghìn lần, chỉ khác giá trị UUID:

~~~sql
SELECT order_id, state, total_cents
FROM app_ks.orders_by_id
WHERE order_id = ?;
~~~

Nếu mỗi request lại gọi `session.prepare(...)` rồi mới `execute(...)`, ứng dụng lặp lại công việc chuẩn bị truy vấn không cần thiết, làm tăng chi phí xử lý và có thể tạo áp lực lên cả client lẫn các node Cassandra. Ngược lại, chuẩn bị câu truy vấn **một lần trên `CqlSession` đang sống**, rồi mỗi lần gọi tạo một **`BoundStatement` mới với tham số khác nhau**, giúp tách hai công việc: chuẩn bị cấu trúc câu CQL và thực thi với dữ liệu thực tế.

Đó là nội dung trọng tâm của bài học thuộc chương **Prepared statement** trong module **Spring Data Cassandra**. Ứng dụng có thể truy cập Cassandra qua entity mapping, repository, `CassandraTemplate`, `CqlTemplate` hoặc Java driver; khi cần tự điều khiển prepared statement, phải hiểu **vòng đời `CqlSession`** và trách nhiệm của từng đối tượng.

**Mục tiêu:**

1. Phân biệt `CqlSession`, `PreparedStatement`, `BoundStatement` và các vòng đời tương ứng.
2. Biết vì sao nên tái sử dụng prepared statement theo **session và câu CQL ổn định**, nhưng tạo bound statement **mới cho từng lần thực thi**.
3. Viết ví dụ Java driver 4.x và tích hợp với Spring bean mà không tạo session hay chuẩn bị truy vấn cho mỗi HTTP request.
4. Xử lý nhiều keyspace/session, truy vấn động, schema thay đổi, node khởi động lại và tình huống `UNPREPARED`.
5. Nhận diện ranh giới của prepared statement: nó không thay đổi partition key, consistency, paging, tính nguyên tử hay chất lượng mô hình dữ liệu.

## 2. Hiểu chính xác ba đối tượng

| Đối tượng | Vai trò | Vòng đời đề xuất | Dùng chung giữa các luồng? |
| --- | --- | --- | --- |
| **`CqlSession`** | Quản lý kết nối, metadata, routing, thực thi CQL trong một cluster | Thường một bean dùng lâu dài cho một cấu hình kết nối, do Spring quản lý | **Có**, dùng để phục vụ nhiều request |
| **`PreparedStatement`** | Mẫu CQL đã được chuẩn bị, kèm metadata về bind variables và kết quả | Tái sử dụng trong phạm vi **session đã chuẩn bị nó** và khi schema/query còn hợp lệ | **Có**, có thể chia sẻ tham chiếu |
| **`BoundStatement`** | Mẫu prepared + **giá trị tham số của một lần gọi**, cùng các tùy chọn execution | Thường tạo mới cho mỗi thao tác | Có tính bất biến trong Java driver 4.x, nhưng không nên dùng **cùng bộ giá trị** cho request khác |
| **`ResultSet`/`Row`** | Kết quả và hàng của lần thực thi | Gắn với mỗi thao tác thực thi | Không coi là cache dữ liệu nghiệp vụ lâu dài |

Hình dung:

~~~mermaid
flowchart TD
    A[Spring Boot khởi tạo] --> B[Tạo CqlSession]
    B --> C[prepare câu CQL ổn định]
    C --> D[Giữ PreparedStatement dưới dạng Spring bean/service field]
    D --> E[Request 1: bind UUID A]
    D --> F[Request 2: bind UUID B]
    D --> G[Request 3: bind UUID C]
    E --> H[session.execute]
    F --> H
    G --> H
    H --> I[Coordinator và replica Cassandra]
    J[Spring context đóng] --> K[Đóng CqlSession]
~~~

Một `PreparedStatement` **không phải kết quả truy vấn**. Nó cũng **không phải một kết nối TCP riêng**; Java driver quản lý pool kết nối thông qua session. Việc giữ một prepared statement không khóa một node duy nhất làm coordinator cho mọi lần gọi.

## 3. Prepared statement thực sự được chuẩn bị ở đâu?

Khi dùng Java driver thực thi `session.prepare(cql)`, driver gửi hoặc sử dụng thông tin chuẩn bị câu CQL từ Cassandra theo cơ chế của phiên bản driver và cấu hình:

1. **Client** gửi truy vấn với các dấu đánh dấu tham số (`?` hoặc dạng bind marker được hỗ trợ).
2. **Cassandra** phân tích cú pháp/kiểm tra schema và tạo metadata cùng định danh prepared query trên node xử lý.
3. **Driver** giữ `PreparedStatement` để lần sau có thể bind giá trị mà không cần diễn giải lại nguyên văn query ở tầng ứng dụng.
4. **Khi execute**, driver gửi truy vấn đã bind tới node coordinator được chọn; node cần có trạng thái prepared tương ứng hoặc phải được chuẩn bị lại theo cơ chế driver/server.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant Driver as CqlSession / Driver
    participant N as Node Cassandra
    App->>Driver: prepare(CQL có ?)
    Driver->>N: PREPARE
    N-->>Driver: prepared id + metadata
    Driver-->>App: PreparedStatement
    loop Nhiều request
        App->>Driver: execute(prepared.bind(values))
        Driver->>N: EXECUTE prepared id + values
        N-->>Driver: Rows hoặc trạng thái ghi
        Driver-->>App: ResultSet
    end
~~~

Sơ đồ là mô hình khái niệm: **driver có thể cache kết quả chuẩn bị, chuẩn bị trên các node khác hoặc tự reprepare** theo tính năng/cấu hình cụ thể. Không nên suy luận rằng mọi lần gọi `prepare` đều gửi đúng một packet, hoặc một lần `PREPARE` trên một node đồng nghĩa cả cluster đã có prepared query mãi mãi.

**Lợi ích cốt lõi:** giảm lặp lại công việc chuẩn bị truy vấn và tạo đường thực thi tham số hóa nhất quán. **Không phải** bỏ qua chi phí đọc/ghi dữ liệu, network round-trip thực thi, replica consistency hay Cassandra query planning theo khóa.

## 4. Bảng và hai truy vấn ổn định để học

Ví dụ dưới đây dùng keyspace `app_ks` **đã tồn tại**. Keyspace và replication phải được quản lý phù hợp với cluster thực tế.

~~~sql
CREATE TABLE app_ks.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    state text,
    total_cents bigint,
    updated_at timestamp
);

CREATE TABLE app_ks.orders_by_customer_day (
    customer_id uuid,
    order_day date,
    created_at timestamp,
    order_id uuid,
    state text,
    total_cents bigint,
    PRIMARY KEY ((customer_id, order_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

Hai mẫu truy vấn:

~~~sql
-- Mẫu A: lookup đúng một hàng theo partition key.
SELECT order_id, state, total_cents
FROM app_ks.orders_by_id
WHERE order_id = ?;

-- Mẫu B: đọc trong một partition và một khoảng clustering.
SELECT order_id, created_at, state
FROM app_ks.orders_by_customer_day
WHERE customer_id = ? AND order_day = ?
  AND created_at >= ? AND created_at < ?
LIMIT 50;
~~~

**Lưu ý về data modeling:**

- `order_id` trong bảng đầu là partition key đầy đủ, phù hợp truy vấn một đơn hàng.
- Bảng thứ hai có partition key tổng hợp `(customer_id, order_day)` và clustering `created_at, order_id`, phù hợp truy vấn theo khách hàng/ngày.
- Đọc bằng prepared statement vẫn phải cung cấp đủ các thành phần partition key để có đường truy cập hiệu quả.
- `LIMIT 50` không tự biến query thành hệ thống phân trang; nếu cần trang tiếp theo phải dùng paging state/cursor đúng ngữ nghĩa.
- Hai bảng có thể biểu diễn cùng dữ liệu nghiệp vụ theo các access pattern khác nhau, nên ứng dụng phải thiết kế cập nhật/đối soát phù hợp.

Không nên dùng `prepare` như cách “hợp pháp hóa” `WHERE state = ?` khi `state` không được hỗ trợ bởi khóa/index. Prepared statement **không** tự tạo index, không làm `ALLOW FILTERING` hiệu quả và không thay đổi partition token.

## 5. Java driver 4.x: prepare một lần, bind nhiều lần

Đây là ví dụ driver độc lập để thấy rõ vòng đời. Nó không dùng Spring quản lý session, nên `try-with-resources` chịu trách nhiệm đóng session:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.util.UUID;

public class PreparedLookupExample {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement findOrder = session.prepare(
                "SELECT order_id, state, total_cents " +
                "FROM app_ks.orders_by_id WHERE order_id = ?"
            );

            UUID firstId = UUID.fromString(
                "11111111-1111-4111-8111-111111111111"
            );
            UUID secondId = UUID.fromString(
                "22222222-2222-4222-8222-222222222222"
            );

            BoundStatement first = findOrder.bind(firstId);
            BoundStatement second = findOrder.bind(secondId);

            ResultSet firstResult = session.execute(first);
            ResultSet secondResult = session.execute(second);

            Row a = firstResult.one();
            Row b = secondResult.one();
            System.out.println(a == null ? "Missing first" : a.getString("state"));
            System.out.println(b == null ? "Missing second" : b.getString("state"));
        }
    }
}
~~~

**Điểm then chốt:** `session.prepare(...)` nằm **ngoài đoạn mã xử lý từng ID**. Hai `BoundStatement` có giá trị khác nhau nhưng đều tham chiếu **cùng một mẫu query**. Giá trị tham số không làm phát sinh một prepared statement mới.

Tên DC `dc1` là **giả định**, không phải default cho mọi cluster. Cần xác minh bằng công cụ Cassandra trước khi kết nối. Ở Spring Boot, không nên tạo/đóng session trong mỗi request như ví dụ `main` này.

### 5.1. Các kiểu bind: theo thứ tự hoặc theo tên

Với câu CQL chứa dấu hỏi:

~~~sql
UPDATE app_ks.orders_by_id
SET state = ?, updated_at = ?
WHERE order_id = ?;
~~~

Các vị trí bind là:

| Chỉ số (bắt đầu từ 0) | Giá trị | Kiểu Java |
| ---: | --- | --- |
| 0 | `state` | `String` |
| 1 | `updated_at` | `Instant` |
| 2 | `order_id` | `UUID` |

~~~java
PreparedStatement updateOrder = session.prepare(
    "UPDATE app_ks.orders_by_id " +
    "SET state = ?, updated_at = ? WHERE order_id = ?"
);

BoundStatement mutation = updateOrder.bind(
    "PAID",
    java.time.Instant.parse("2026-11-25T02:00:00Z"),
    orderId
);

session.execute(mutation);
~~~

CQL/driver cũng hỗ trợ những dạng **named bind markers** theo cú pháp và phiên bản, và driver có thể bind theo tên định danh của biến. Với ví dụ đọc/ghi cơ bản, **bind theo vị trí** là cách dễ kiểm tra. Nếu thay đổi thứ tự `?` trong câu CQL, phải sửa tương ứng thứ tự biến Java và test.

Không được nối giá trị trực tiếp vào chuỗi SQL/CQL chỉ để tránh bind, ví dụ tạo các câu `"... order_id = " + userInput`. Điều đó làm mất lợi ích tái sử dụng query shape và tạo thêm rủi ro sai cú pháp, chuyển kiểu, injection.

## 6. BoundStatement trong driver 4.x có tính bất biến

Với Java driver 4.x, những phương thức cấu hình trên `BoundStatement` thường **trả về một bản statement mới**, không sửa biến statement đang có. Vì vậy phải **nhận lại kết quả** của phép `set...`:

~~~java
PreparedStatement prepared = session.prepare(
    "SELECT order_id, state, total_cents " +
    "FROM app_ks.orders_by_id WHERE order_id = ?"
);

BoundStatement base = prepared.bind();

// ĐÚNG: giữ lại đối tượng được trả về sau khi đặt giá trị.
BoundStatement ready = base.setUuid(0, orderId);
Row row = session.execute(ready).one();
~~~

Ngược lại, cách viết dưới đây **không nên dùng**:

~~~java
BoundStatement wrong = prepared.bind();
wrong.setUuid(0, orderId); // Bỏ qua BoundStatement được trả về.
session.execute(wrong);   // Có thể còn giá trị chưa được bind.
~~~

Khi dùng các phương thức `bind(value1, value2, ...)`, giá trị đã được đặt ngay từ đầu nên ít khả năng bỏ sót kết quả trả về hơn. Với các tùy chọn như consistency, page size hoặc timeout, cũng phải kiểm tra quy tắc immutable của API:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;

BoundStatement readStatement = prepared.bind(orderId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(100);
~~~

**Không nên cache một BoundStatement mutable/shared theo ID rồi thay tham số của nó khi có nhiều request.** Hãy cache `PreparedStatement`, tạo một bound statement mới cho mỗi bộ tham số và giữ nó trong phạm vi lần thực thi. Điều đó giúp xử lý concurrent request mà không lẫn dữ liệu người dùng.

## 7. Tích hợp Spring Boot: session và prepared statement theo vòng đời bean

Trong Spring Data Cassandra, `CqlSession` thường được Spring Boot cấu hình từ properties, với thông tin contact points, port, local datacenter, keyspace và TLS/auth tùy môi trường:

~~~yaml
spring:
  cassandra:
    contact-points:
      - cassandra-a.internal
      - cassandra-b.internal
    port: 9042
    local-datacenter: dc1
    keyspace-name: app_ks
~~~

Các giá trị chỉ minh họa. Spring Boot 3.x thường dùng `spring.cassandra.*`; nhiều ứng dụng Spring Boot 2.x dùng `spring.data.cassandra.*`. Hãy áp dụng prefix thực tế theo phiên bản đang chạy.

### 7.1. Khai báo prepared statement là bean

Khi truy vấn quan trọng có hình dạng CQL cố định, một lựa chọn rõ ràng là chuẩn bị nó **lúc Spring context khởi tạo**:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderPreparedStatementsConfig {

    @Bean(name = "findOrderByIdStatement")
    PreparedStatement findOrderByIdStatement(CqlSession session) {
        return session.prepare(
            "SELECT order_id, state, total_cents " +
            "FROM app_ks.orders_by_id WHERE order_id = ?"
        );
    }

    @Bean(name = "updateOrderStateStatement")
    PreparedStatement updateOrderStateStatement(CqlSession session) {
        return session.prepare(
            "UPDATE app_ks.orders_by_id " +
            "SET state = ?, updated_at = ? WHERE order_id = ?"
        );
    }
}
~~~

**Phân biệt vòng đời:**

- `CqlSession` là bean lâu dài, có quản lý kết nối và phải được đóng khi context kết thúc.
- `PreparedStatement` là mẫu câu truy vấn, **không cần tự gọi `close()`**; nó không sở hữu session.
- `@Bean` chuẩn của Spring có phạm vi **singleton** theo mặc định nếu không tùy chỉnh; các request sử dụng cùng reference prepared statement.
- Nếu schema/keyspace chưa sẵn sàng lúc khởi động, bean `PreparedStatement` có thể khởi tạo thất bại, làm context không start. Đây có thể là chiến lược **fail fast** hữu ích, nhưng dịch vụ có nhiều feature tùy chọn có thể cần cơ chế chuẩn bị lười/bất đồng bộ.
- Với nhiều `CqlSession`, không inject theo kiểu đơn thuần khi có nhiều ứng viên; phải chỉ rõ session bằng `@Qualifier`.

### 7.2. Service tái sử dụng bean, không prepare trong method

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.Optional;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class OrderReadService {
    private final CqlSession session;
    private final PreparedStatement findById;

    public OrderReadService(
            CqlSession session,
            @Qualifier("findOrderByIdStatement") PreparedStatement findById) {
        this.session = session;
        this.findById = findById;
    }

    public Optional<OrderView> find(UUID orderId) {
        Row row = session.execute(findById.bind(orderId)).one();
        if (row == null) {
            return Optional.empty();
        }
        return Optional.of(new OrderView(
            row.getUuid("order_id"),
            row.getString("state"),
            row.getLong("total_cents")
        ));
    }
}
~~~

`OrderView` là DTO do ứng dụng định nghĩa, ví dụ một `record OrderView(UUID orderId, String state, long totalCents)` trên Java hỗ trợ record. Đoạn code minh họa API Java driver 4.x và cần keyspace/schema có sẵn. Nếu `total_cents` có thể null, đọc bằng `getLong` sẽ cần xử lý null rõ ràng trước khi dùng primitive; ví dụ giả định cột này luôn có giá trị ở những row hợp lệ.

**Tại sao cần `@Qualifier`?** Cấu hình có cả `findOrderByIdStatement` và `updateOrderStateStatement`, đều là bean kiểu `PreparedStatement`. Inject một `PreparedStatement` không rõ tên có thể gây lỗi chọn bean hoặc dùng nhầm câu CQL. Tên bean làm rõ mối quan hệ từ service tới đúng truy vấn.

### 7.3. CqlTemplate, CassandraTemplate và repository có cần bean trên không?

Không nhất thiết:

- **`CqlTemplate`** cung cấp API thực thi CQL với bind parameter và RowMapper, nhưng cách xử lý prepared statement nội bộ tùy method/phiên bản; không suy diễn rằng nó dùng chính bean `findOrderByIdStatement` của bạn.
- **`CassandraTemplate`** cung cấp các thao tác mapping entity theo schema/driver; không phải mọi thao tác cần tự định nghĩa một bean `PreparedStatement`.
- **`CassandraRepository`** có thể cung cấp CRUD và câu query khai báo theo tên/`@Query`, sử dụng tầng Spring Data tương ứng. Không tự thêm một lớp prepared statement nếu API repository đã đáp ứng yêu cầu và bạn chưa đo được lợi ích.
- **`CqlSession` trực tiếp** là lựa chọn khi cần kiểm soát prepared statement cụ thể, options, metadata hoặc luồng bất đồng bộ rõ ràng.

Hãy chọn mức trừu tượng phù hợp. Dù API khác nhau, giới hạn truy vấn CQL theo partition key và clustering key vẫn giữ nguyên.

## 8. Không chuẩn bị lại trong mỗi request

Một anti-pattern phổ biến:

~~~java
// KHÔNG KHUYẾN NGHỊ: gọi prepare ở mọi HTTP request.
public Optional<OrderView> find(UUID id) {
    PreparedStatement ps = session.prepare(
        "SELECT order_id, state, total_cents " +
        "FROM app_ks.orders_by_id WHERE order_id = ?"
    );
    Row row = session.execute(ps.bind(id)).one();
    // Ánh xạ row ...
}
~~~

**Vì sao cần tránh?**

1. Đọc code không thấy ranh giới rõ giữa khởi tạo mẫu truy vấn và thực thi tham số.
2. Phụ thuộc cache của driver mà không kiểm soát được tính ổn định của câu query hoặc hiệu quả thực tế.
3. Nếu CQL được ghép động và thay đổi liên tục, mỗi biến thể có thể phát sinh một prepared query/cache entry mới.
4. Khi nhiều request đồng thời ở giai đoạn warm-up, có thể phát sinh thêm công việc chuẩn bị và tăng độ trễ khởi động/truy vấn.

**Cần phân biệt cho chính xác:** nhiều phiên bản Java driver có **cache prepared statement theo session**, nên việc gọi `prepare` lặp lại **không nhất thiết** gửi một `PREPARE` qua mạng mỗi lần. Dù vậy, lưu reference `PreparedStatement` dài hạn cho các mẫu query cố định vẫn giúp code minh bạch và tránh gọi logic chuẩn bị vô ích. Khi tối ưu, **đo metrics thực tế**, không khẳng định mọi lần `prepare` chắc chắn thêm một network round-trip.

## 9. Session boundary: prepared statement thuộc về phiên làm việc nào?

Đây là nguyên tắc quan trọng nhất của chủ đề **tái sử dụng theo vòng đời session**.

### 9.1. Đừng chuyển PreparedStatement sang session khác

Giả sử ứng dụng có hai session:

~~~text
catalogSession --> cluster A, keyspace catalog_ks
billingSession --> cluster B, keyspace billing_ks
~~~

Một `PreparedStatement` được tạo từ `catalogSession.prepare(...)` không nên được lấy rồi tùy tiện đưa vào `billingSession.execute(...)`, ngay cả khi hai CQL nhìn có vẻ giống nhau. Prepared metadata, query identity, keyspace, schema và khả năng prepared trên các node được quản lý trong **bối cảnh session/cluster**. Cần **chuẩn bị riêng** trên session thực sự dùng để execute.

Một mẫu wiring rõ ràng:

~~~java
@Bean(name = "catalogFindProduct")
PreparedStatement catalogFindProduct(
        @Qualifier("catalogSession") CqlSession catalogSession) {
    return catalogSession.prepare(
        "SELECT product_id, name FROM catalog_ks.products_by_id " +
        "WHERE product_id = ?"
    );
}

@Bean(name = "billingFindInvoice")
PreparedStatement billingFindInvoice(
        @Qualifier("billingSession") CqlSession billingSession) {
    return billingSession.prepare(
        "SELECT invoice_id, state FROM billing_ks.invoices_by_id " +
        "WHERE invoice_id = ?"
    );
}
~~~

Đây là các bean method minh họa, cần đặt trong lớp `@Configuration` có import tương ứng và hai session đã được định nghĩa. Trong service, cũng inject **đúng session và đúng statement bằng `@Qualifier`**.

### 9.2. Keyspace mặc định và tên bảng đầy đủ

Trong ví dụ chính, dùng `FROM app_ks.orders_by_id` thay vì `FROM orders_by_id`. Cách viết **fully qualified** giúp tránh nhập nhằng khi ứng dụng có nhiều keyspace và giảm nguy cơ prepared statement trỏ nhầm bảng khi thay cấu hình default keyspace.

Nếu dùng query không có tên keyspace, cách giải quyết phụ thuộc default keyspace/statement keyspace và cơ chế prepare trong driver phiên bản đó. Đừng chạy `USE other_keyspace` giữa các request trên một session dùng chung rồi giả định mọi prepared statement tự chuyển theo; phải có chính sách rõ ràng theo keyspace.

### 9.3. Khi Spring context tái khởi động

Khi một Spring context đóng, session được đóng, các bean prepared statement của context đó cũng hết vòng đời sử dụng. Khi context mới tạo session mới, chuẩn bị lại những mẫu câu mà ứng dụng cần. **Không lưu/serialize một `PreparedStatement` ra file hoặc cache phân tán** để tái sử dụng giữa JVM hay phiên khởi động.

Nếu hệ thống thay đổi endpoint/TLS/credential hoặc chuyển từ cluster A sang cluster B, cần thiết lập session mới và tạo prepared statements phù hợp, không chỉ thay một biến cấu hình trong service rồi giữ reference cũ.

## 10. Query cache: nên tái sử dụng cái gì, không tái sử dụng cái gì?

### 10.1. Cache một tập hữu hạn mẫu CQL ổn định

Những mẫu thích hợp:

~~~sql
SELECT order_id, state FROM app_ks.orders_by_id WHERE order_id = ?;

UPDATE app_ks.orders_by_id
SET state = ? WHERE order_id = ?;

SELECT order_id, created_at FROM app_ks.orders_by_customer_day
WHERE customer_id = ? AND order_day = ?
  AND created_at >= ? AND created_at < ?
LIMIT 50;
~~~

Chúng có **cấu trúc câu lệnh cố định**. Bind values có thể thay đổi hàng triệu lần mà mẫu query vẫn giống nhau.

### 10.2. Không biến mọi giá trị input thành một query shape riêng

**Sai:**

~~~java
String cql = "SELECT order_id, state FROM app_ks.orders_by_id " +
    "WHERE order_id = " + orderId;
PreparedStatement ps = session.prepare(cql);
~~~

Điều này tạo câu CQL khác nhau cho mỗi ID, làm mất ý nghĩa của prepared caching, khó kiểm soát và có rủi ro khi nguồn input không được xác thực.

**Đúng:**

~~~java
PreparedStatement ps = session.prepare(
    "SELECT order_id, state FROM app_ks.orders_by_id WHERE order_id = ?"
);
BoundStatement bs = ps.bind(orderId);
~~~

Ở đây đoạn `prepare` được thực hiện **trong giai đoạn khởi tạo/cấu hình**, không phải mỗi lần tìm ID.

### 10.3. Dynamic WHERE và ORDER BY

**Bind markers dành cho giá trị**, không phải để thay thế tên bảng, tên cột, một biểu thức CQL tùy ý hoặc hướng sắp xếp `ASC/DESC`. Không thể viết `FROM ?` rồi bind tên bảng như bind một UUID.

Nếu API có những lựa chọn truy vấn hợp lệ, hãy tạo **một số ít query shape đã whitelist**:

~~~text
findById             -> SELECT ... WHERE order_id = ?
findByCustomerDay    -> SELECT ... WHERE customer_id = ? AND order_day = ?
findByDayRange       -> SELECT ... WHERE ... created_at >= ? AND created_at < ?
~~~

Các lựa chọn schema/cột phải do code kiểm soát, không dùng tên cột lấy từ HTTP request để nối thẳng vào CQL. Mỗi query shape cần được đánh giá **partition key**, clustering restrictions, tính hợp lệ của `ORDER BY` và giới hạn kết quả.

## 11. Prepared cache trên node, UNPREPARED và node restart

Cassandra lưu thông tin prepared query trong phạm vi server/node theo cơ chế và phiên bản của nó. Một prepared query được sử dụng qua session có thể được execute trên **những coordinator khác nhau**. Khi một node mới xuất hiện, node khởi động lại hoặc cache prepared trên node không còn dữ liệu tương ứng, node đó có thể không nhận ra prepared ID.

Tình huống thường được biểu diễn bằng phản hồi **`UNPREPARED`**. Java driver có cơ chế tự chuẩn bị lại khi cần và có các cấu hình liên quan việc chuẩn bị trên nhiều node hoặc sau khi node lên lại; **hành vi chi tiết tùy phiên bản và cấu hình**.

~~~mermaid
flowchart TD
    A[Client có PreparedStatement] --> B[Execute trên coordinator]
    B --> C{Node biết prepared id?}
    C -->|Có| D[Thực thi với bound values]
    C -->|Không| E[UNPREPARED]
    E --> F[Driver có thể reprepare theo cơ chế/cấu hình]
    F --> G[Thử thực thi lại theo chính sách]
    G --> D
~~~

**Không nên tự viết vòng retry vô hạn** chỉ vì thấy lỗi prepared statement. Cần phân biệt:

- Node vừa khởi động lại và cần **reprepare**: thường là sự kiện có thể khôi phục.
- **Schema thay đổi**, prepared metadata cũ không còn đúng: có thể cần cập nhật query/code và tạo prepared statement mới.
- **Timeout/Unavailable** khi cluster có sự cố: không phải lúc nào cũng được xử lý bằng reprepare.
- **Unauthorized** hoặc keyspace/bảng không tồn tại: reprepare mãi không khắc phục được sai quyền hoặc schema.

Với môi trường production, quan sát metrics/log về số lần prepare/reprepare, tần suất `UNPREPARED`, lỗi driver và latency; nếu liên tục reprepare, điều tra node churn, cache pressure hoặc query shape thay đổi bất thường.

## 12. Schema migration có thể làm PreparedStatement lỗi thời

Prepared statement giữ metadata liên quan **bind variables**, cột và kiểu dữ liệu của query ở thời điểm chuẩn bị. Nếu schema thay đổi, ví dụ đổi kiểu cột, xóa/đổi tên cột hoặc triển khai entity mapping mới, prepared statement cũ có thể không còn phù hợp với bảng thực tế.

Ví dụ ứng dụng trước đây đọc:

~~~sql
SELECT order_id, state, total_cents
FROM app_ks.orders_by_id
WHERE order_id = ?;
~~~

Nếu schema được migration để đổi tên `total_cents`, câu CQL cũng phải được cập nhật. **Reprepare không làm một query sai schema trở thành query đúng**.

Thực hành triển khai:

1. Dùng **schema migration có phiên bản**, áp dụng và xác minh trạng thái Cassandra trước khi đưa code phụ thuộc vào schema mới.
2. Ưu tiên **projection rõ cột** thay vì `SELECT *` trong những query cần độ ổn định; nếu thêm cột mới, `SELECT *` có thể làm thay đổi metadata kết quả và cách map.
3. Triển khai thay đổi schema/ứng dụng theo lộ trình tương thích ngược khi nhiều phiên bản cùng hoạt động.
4. Nếu thay đổi query shape, chuẩn bị **prepared statement mới** và loại bỏ tham chiếu mẫu query cũ khi không còn dùng.
5. Trong bài kiểm thử tích hợp, tái khởi tạo session/ứng dụng sau migration nếu muốn kiểm tra đường chuẩn bị mới.

**Không dùng prepared statement như cơ chế quản lý schema.** Việc driver chuẩn bị câu query thành công chỉ nói câu CQL đó phù hợp tại thời điểm chuẩn bị, không đảm bảo mọi migration về sau luôn tương thích.

## 13. Hiệu năng: prepare một lần không có nghĩa execute miễn phí

### 13.1. Chi phí có thể được giảm

- Giảm lặp lại thao tác xử lý/preparation cho **query shape ổn định**.
- Có thể tận dụng cache prepared query của driver và node Cassandra.
- Bind values theo kiểu dữ liệu, giúp code tái sử dụng và giảm rủi ro tạo CQL khác nhau theo input.
- Tách rõ giai đoạn warm-up/khởi tạo và giai đoạn phục vụ request, dễ quan sát độ trễ.

### 13.2. Chi phí không biến mất

| Hoạt động | Prepared statement có làm biến mất? |
| --- | --- |
| Gửi request qua mạng tới coordinator | **Không** |
| Đọc/ghi replica theo consistency level | **Không** |
| Đọc partition lớn/hot partition | **Không** |
| Xử lý nhiều tombstone | **Không** |
| Trả nhiều row và giải mã dữ liệu | **Không** |
| Paging qua nhiều lượt fetch | **Không** |
| Reprepare khi node thay đổi/schema đổi | **Không** |
| Lost update hoặc lỗi ghi trùng giữa các thao tác nghiệp vụ | **Không** |

Nếu truy vấn chậm do chọn partition key không phù hợp, một `PreparedStatement` tái sử dụng hoàn hảo vẫn có thể thực thi **một truy vấn rất đắt**. Ưu tiên kiểm chứng đường truy cập theo khóa và các metrics đọc/ghi trước khi tối ưu phần khởi tạo prepared query.

### 13.3. Không “prepare mọi thứ” một cách vô hạn

Mỗi query shape có metadata/cache và có thể cần tài nguyên phía node. Nếu ứng dụng sinh ra hàng chục nghìn câu CQL gần như giống nhau chỉ vì thêm literal, đổi thứ tự trường không cần thiết hoặc tạo `IN` có số lượng bind marker thay đổi tùy ý, nó có thể làm cache phình và tăng chi phí prepare.

Đối với những API cho phép lọc/sắp xếp nhiều hướng, nên **giới hạn tập truy vấn được hỗ trợ** dựa trên access pattern, sử dụng query shapes định trước và đo tài nguyên. Nếu quy mô động vượt quá khả năng phù hợp với Cassandra, hãy xem lại thiết kế dữ liệu hoặc chuyển nhu cầu tìm kiếm linh hoạt sang hệ thống chuyên dụng.

## 14. Consistency, paging, null và idempotence vẫn phải chọn cho từng lần execute

### 14.1. Consistency level

Một prepared statement có thể được sử dụng với nhiều lần bind và tùy chọn execute. Consistency level thể hiện yêu cầu của một lần đọc/ghi theo replication strategy và topology; không được hiểu là “prepared thì dữ liệu nhất quán mạnh”.

~~~java
BoundStatement statement = findOrder.bind(orderId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
ResultSet rs = session.execute(statement);
~~~

Với keyspace RF = 3 tại một datacenter, `LOCAL_QUORUM` thường cần 2 replica phản hồi cho hoạt động tương ứng. Cấu hình này **không** cho phép query thiếu partition key và không thay thế cơ chế cạnh tranh ở tầng nghiệp vụ.

### 14.2. Paging

Với mẫu query trả nhiều row, có thể đặt page size trên bound statement (tùy API):

~~~java
BoundStatement pageOne = preparedRange.bind(
        customerId, orderDay, fromInclusive, toExclusive)
    .setPageSize(100);
ResultSet result = session.execute(pageOne);
~~~

**Page size** không phải `LIMIT`: page size quy định số row của từng đợt fetch, trong khi `LIMIT` giới hạn tổng số row của câu truy vấn. Truy cập `ResultSet` đồng bộ có thể kích hoạt **fetch trang tiếp theo** khi cần; hãy cân nhắc API bất đồng bộ hoặc giới hạn row nếu không muốn đọc vô hạn.

Paging state chỉ hợp lệ cho **cùng câu truy vấn và cùng tham số** trong ngữ cảnh tương ứng. Không lấy paging token của một đơn/ngày để áp dụng cho truy vấn khác. Nếu API cần cursor lâu dài, phải thiết kế token an toàn với giới hạn của driver/phiên bản và dữ liệu thay đổi đồng thời.

### 14.3. Null và UNSET

Trong Cassandra, **ghi null** và **không truyền/UNSET** không đồng nghĩa. Ghi null có thể biểu diễn xóa giá trị và tạo tombstone; UNSET ở những ngữ cảnh hỗ trợ có thể có nghĩa không thay đổi cột đó.

Với mutation chuẩn bị sẵn:

~~~sql
UPDATE app_ks.orders_by_id
SET state = ? WHERE order_id = ?;
~~~

Khi có yêu cầu “không sửa state”, tốt hơn là **không thực hiện mutation này**; nếu một thao tác có nhiều cột tùy chọn, dùng API bind/null/unset đúng theo phiên bản và kiểm chứng CQL thực tế. Đừng biến mọi tham số thiếu thành `null` hoặc giả định `bind()` không truyền đủ giá trị sẽ tự có ý nghĩa mong muốn.

### 14.4. Idempotence và timeout

Chuẩn bị một câu `UPDATE` nhiều lần không tự quyết định thao tác đó có **idempotent** hay không. Ví dụ:

- Ghi cùng một giá trị vào cùng khóa có thể được thiết kế để retry an toàn hơn, với điều kiện timestamp/TTL/concurrency được xét.
- Các phép tăng/giảm counter hoặc phát sinh sự kiện phụ có thể **không idempotent**.
- `WriteTimeout` không chứng minh lần ghi trước chưa được áp dụng ở bất kỳ replica nào.

Khi cấu hình retry policy hoặc đánh dấu statement idempotent, phải hiểu **ngữ nghĩa nghiệp vụ của câu CQL**, không gắn idempotence theo cảm tính chỉ vì statement đã được prepare.

## 15. Prepare bất đồng bộ và giai đoạn warm-up

Chuẩn bị nhiều câu CQL trong quá trình khởi động có thể tạo độ trễ cho startup. Với những ứng dụng cần khởi động nhanh hoặc chuẩn bị một tập truy vấn độc lập, Java driver 4.x hỗ trợ API `prepareAsync(...)`.

Ví dụ minh họa:

~~~java
import java.util.concurrent.CompletionStage;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

CompletionStage<PreparedStatement> lookupFuture =
    session.prepareAsync(
        "SELECT order_id, state FROM app_ks.orders_by_id WHERE order_id = ?"
    );

CompletionStage<PreparedStatement> updateFuture =
    session.prepareAsync(
        "UPDATE app_ks.orders_by_id SET state = ? WHERE order_id = ?"
    );

// Xử lý hoặc kết hợp các CompletionStage theo chính sách khởi tạo.
~~~

**Cần cân nhắc:**

1. Không bắt đầu phục vụ request cần query khi `PreparedStatement` tương ứng **chưa chuẩn bị xong**, trừ khi code có đường chờ/fallback an toàn.
2. Không gọi `join()`/`get()` bừa bãi trên luồng event-loop của driver; tránh làm nghẽn thread I/O.
3. Nếu hàng trăm mẫu câu được chuẩn bị đồng thời, hãy giới hạn concurrency và quan sát tải cluster.
4. Xác định chính sách **fail fast** hay **lazy prepare** rõ ràng. Đối với truy vấn cốt lõi, lỗi schema ngay khi startup có thể là tín hiệu cần thiết; với tính năng ít dùng, lazy prepare có thể hợp lý.
5. Bất đồng bộ **không đồng nghĩa** một prepared statement được phép sử dụng trước khi nhận metadata chuẩn bị.

Nếu dùng Spring `@Bean PreparedStatement` đồng bộ như phần 7, đó là lựa chọn đơn giản cho một số ít query shape. Không cần chuyển mọi câu lệnh sang async chỉ vì API có sẵn.

## 16. Những lỗi thường gặp

| Hiểu nhầm hoặc cách làm sai | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| “`prepare` trong mỗi request chắc chắn là nhanh vì có cache.” | Phụ thuộc driver cache, khó đo và tổ chức lifecycle | Tái sử dụng reference prepared statement cho query cố định |
| “Một `PreparedStatement` dùng với mọi `CqlSession`.” | Sai bối cảnh session/schema/keyspace | Prepare riêng trên session sẽ execute |
| “Cache `BoundStatement` và sửa tham số giữa các request.” | Có thể lẫn giá trị hoặc làm sai luồng bất biến | Tạo `BoundStatement` mới từ `PreparedStatement` |
| “`bound.setUuid(...)` sửa tại chỗ mà không cần nhận kết quả.” | Có thể execute statement chưa có giá trị | Gán lại kết quả setter hoặc dùng `bind(values...)` |
| “Prepared statement thay `ALLOW FILTERING`.” | Truy vấn vẫn thiếu đường truy cập phù hợp | Thiết kế bảng theo partition key và clustering |
| “`FROM ?` rồi bind tên bảng.” | Bind marker không dành cho identifier CQL | Whitelist cấu trúc query và dùng tên schema tường minh |
| “`UNPREPARED` luôn là lỗi không phục hồi.” | Có thể xảy ra khi node khởi động lại | Hiểu cơ chế reprepare của driver và theo dõi lỗi |
| “`UNPREPARED` luôn tự phục hồi nên không cần log.” | Có thể che schema/cache/node churn kéo dài | Quan sát tần suất reprepare, latency và lỗi |
| “Schema đổi thì query cũ vẫn đúng vì đã prepare.” | Metadata/cột có thể không còn hợp lệ | Migration có phiên bản, cập nhật query và chuẩn bị lại |
| “Prepared làm truy vấn nhanh bất kể partition lớn thế nào.” | Vẫn phải đọc replica và tombstone | Kiểm tra access pattern, LIMIT/paging và tải cluster |
| “Prepared tự đảm bảo tính nguyên tử nhiều bảng.” | Sai giới hạn Cassandra | Thiết kế workflow, retry/idempotency và consistency |
| “Giữ `CqlSession` trong một static global dù Spring context đã đóng.” | Dễ dùng session đã close | Để Spring quản lý vòng đời và scope tài nguyên |

## 17. Kiểm thử để chứng minh tái sử dụng đúng

### 17.1. Unit test mức service

Mock `CqlSession` và `PreparedStatement` có thể xác minh rằng **constructor/bean chuẩn bị query một lần**, còn mỗi lời gọi `find` bind tham số khác nhau. Tuy nhiên khi mock API bất biến của `BoundStatement`, cần mô phỏng đúng phương thức trả về mới; không tự giả định setter thay đổi object.

Ví dụ giả mã test logic:

~~~text
Given:
  session.prepare(QUERY) trả về prepared
  hai lời gọi find(orderA), find(orderB)

Expect:
  prepare(QUERY) được gọi 1 lần trong giai đoạn khởi tạo
  bind(orderA) được gọi với A
  bind(orderB) được gọi với B
  execute(...) được gọi 2 lần với bound statements đúng tham số
  không có prepare(...) trong method find(...)
~~~

Unit test kiểm tra **cách tổ chức code** nhưng không chứng minh Cassandra chấp nhận query hoặc driver cache hoạt động theo kỳ vọng.

### 17.2. Test tích hợp với Cassandra thử nghiệm

Với keyspace `app_ks` và bảng `orders_by_id` đã tạo:

1. Khởi tạo một `CqlSession` và chuẩn bị câu `SELECT ... WHERE order_id = ?` một lần.
2. Ghi hai hàng thử nghiệm bằng CQL hợp lệ; bind hai ID khác nhau từ cùng `PreparedStatement`.
3. Kiểm tra mỗi kết quả đúng row và đúng state; lookup ID thứ ba phải trả 0 hàng.
4. Gọi đồng thời nhiều truy vấn từ một reference `PreparedStatement`, mỗi lời gọi bind ID riêng; xác minh dữ liệu không bị lẫn.
5. Kiểm tra Spring context có một session đúng cấu hình và bean prepared statement được inject bằng đúng `@Qualifier`.
6. Đối chiếu thời gian thực hiện với những query shape tương đương, kiểm soát warm-up và môi trường test; không dùng một lần đo duy nhất để suy ra lợi ích.
7. Trong môi trường cho phép, khởi động lại một node Cassandra hoặc tạo node mới; quan sát khả năng thực thi tiếp/reprepare của driver. **Không thử fault injection trên production.**
8. Thử migration trong keyspace test làm query cũ không còn hợp lệ; ghi nhận lỗi và xác minh quy trình cập nhật prepared statement.
9. Kiểm tra truy vấn range trong `orders_by_customer_day` luôn có đầy đủ partition key, ranh giới thời gian và `LIMIT` đúng.

### 17.3. Bảng kiểm tra vận hành

| Chỉ số/tín hiệu | Câu hỏi cần trả lời |
| --- | --- |
| Số `CqlSession` đang mở | Có vô tình tạo session cho mỗi request hoặc mỗi tenant không? |
| Số mẫu CQL chuẩn bị | Có tăng theo dữ liệu đầu vào thay vì theo query shape không? |
| Tần suất prepare/reprepare | Có node churn, schema changes hay cache pressure không? |
| `UNPREPARED` và lỗi execute | Driver có khôi phục được và nguyên nhân kéo dài là gì? |
| Latency lúc startup và request đầu | Có chi phí warm-up bất thường hoặc prepare lúc đang phục vụ request không? |
| Partition size/tombstone | Query có chậm dù đã reuse prepared không? |
| Timeout/Unavailable | Consistency, network và replica có đáp ứng mục tiêu không? |
| Số row/page fetch | Có đọc nhiều hơn yêu cầu hoặc hiểu nhầm LIMIT với page size không? |

## 18. Bài thực hành tổng hợp

**Tình huống:** một ứng dụng Spring Boot có API `GET /orders/{id}`. Trong ngày, ứng dụng nhận nhiều request cùng cấu trúc, mỗi request có một UUID khác nhau.

**Yêu cầu:**

1. Tạo bảng `app_ks.orders_by_id` với primary key `order_id`.
2. Cấu hình `spring.cassandra.contact-points`, `port`, `local-datacenter` và keyspace phù hợp môi trường lab.
3. Tạo bean `findOrderByIdStatement` bằng `session.prepare(...)` đúng một lần lúc context khởi tạo.
4. Inject bean vào `OrderReadService` bằng `@Qualifier` và bind mỗi UUID thành `BoundStatement` mới.
5. Trả `Optional.empty()` khi CQL trả 0 hàng; để timeout/mapping error đi qua chính sách xử lý lỗi, không biến thành 404 giả.
6. Gửi hai request đồng thời cho hai UUID, xác minh kết quả không bị lẫn.
7. Thử viết phiên bản gọi `prepare` trong mỗi request; mô tả khác biệt về tổ chức lifecycle, khả năng cache và chi phí quan sát được.
8. Tạo phương thức range đọc tối đa 50 đơn hàng theo `customer_id + order_day`, rồi thêm câu prepared statement thứ hai. Không dùng câu CQL thiếu thành phần partition key.
9. Thử thay tên cột trong schema test và giải thích vì sao query shape phải được migration/reprepare, không chỉ retry.
10. Mô tả vòng đời khi Spring context đóng rồi khởi động lại và vì sao không được mang reference `PreparedStatement` cũ sang session mới.

**Tiêu chí đạt:** người học thể hiện đúng luồng **`CqlSession` sống lâu → `PreparedStatement` được tái sử dụng → `BoundStatement` mới cho mỗi request → execute**, giải thích được giới hạn cache/preparation trên node và không đánh đồng prepared statement với transaction, indexing hay consistency.

## 19. Câu hỏi tự kiểm tra

1. Vì sao prepared statement phù hợp với truy vấn có cấu trúc cố định nhưng giá trị tham số thay đổi thường xuyên?
2. `CqlSession`, `PreparedStatement` và `BoundStatement` khác nhau về vai trò và vòng đời ra sao?
3. Một prepared statement nên được tạo ở đâu trong ứng dụng Spring Boot có hàng nghìn HTTP request?
4. Vì sao cùng `PreparedStatement` có thể được nhiều request sử dụng nhưng không nên tái sử dụng cùng bộ bound values?
5. Với Java driver 4.x, điều gì xảy ra nếu bỏ qua kết quả trả về của `bound.setUuid(...)`?
6. Vì sao việc gọi `prepare` lặp lại không nhất thiết đồng nghĩa một network round-trip mới mỗi lần?
7. Một prepared statement được tạo trên `catalogSession` có nên dùng để execute trên `billingSession` không?
8. Lợi ích của việc ghi rõ `app_ks.orders_by_id` trong câu CQL đã prepare là gì?
9. Tại sao `FROM ?` không thể được dùng để bind tên bảng?
10. Khi node khởi động lại và quên trạng thái prepared, driver/server có thể gặp tình huống gì?
11. Khi schema đổi tên hoặc kiểu cột, chỉ reprepare query cũ có đủ không?
12. Prepared statement có giải quyết truy vấn thiếu partition key, hot partition hoặc tombstone không?
13. `LIMIT`, page size và paging state khác nhau như thế nào đối với query đã prepare?
14. Vì sao `WriteTimeout` trên một câu prepared `UPDATE` không được hiểu ngay là “chưa ghi gì”?
15. Nên dùng test và metrics nào để chứng minh việc reuse prepared statement diễn ra theo mong đợi?

**Ghi nhớ:** **chuẩn bị mẫu CQL ổn định một lần trong vòng đời `CqlSession`, giữ `PreparedStatement` để tái sử dụng và tạo `BoundStatement` mới cho mỗi bộ tham số**. Để Spring quản lý vòng đời session, chú ý bối cảnh keyspace/cluster và kiểm soát reprepare khi topology/schema thay đổi. Prepared statement giúp thực thi CQL tham số hóa hiệu quả hơn, nhưng **không thay thế thiết kế bảng theo truy vấn, partition key, consistency, paging và kiểm soát hiệu năng phân tán**.
