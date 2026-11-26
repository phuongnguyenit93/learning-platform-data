# Chỉ định bảng đích và kiểu kết quả ánh xạ

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **bảng Cassandra thực sự được truy vấn** với **kiểu Java dùng để ánh xạ kết quả**, dù hai thông tin thường được suy ra từ cùng một entity.
- Dùng `@Table`, `@Column`, `@PrimaryKey` và `CassandraTemplate.select(…)` để đọc đúng bảng, đúng kiểu trong trường hợp thông thường.
- Sử dụng fluent API `query(DomainType.class).inTable("...").as(ResultType.class).matching(query).all()` khi cần chỉ định tường minh bảng và kiểu kết quả.
- Lựa chọn kết quả là **entity đầy đủ**, **interface projection**, **DTO** hoặc xử lý trực tiếp row/statement tùy nhu cầu.
- Hiểu khi nào `select(String cql, Class<T>)` đọc một bảng do câu CQL chỉ định, còn `Class<T>` chủ yếu phục vụ ánh xạ kết quả.
- Viết truy vấn CQL đúng partition key/clustering key, giới hạn số cột, kiểm soát paging và nhận diện sai lệch schema, alias và tên cột.
- Tránh nhầm lẫn giữa việc thay đổi bảng đích, kết quả ánh xạ và ranh giới nhất quán của nhiều bảng được nhân bản theo truy vấn.

Bài thuộc chương **CassandraTemplate** của **SPRING_DATA_CASSANDRA**: sử dụng Spring Data Cassandra để thao tác Apache Cassandra qua entity mapping, repository, `CassandraTemplate` và CQL. Trong Cassandra, thiết kế bảng theo **đường truy vấn**, partition key, consistency level, paging và kích thước partition là những yếu tố quyết định. Template hỗ trợ biểu đạt các thao tác đó bằng Java, nhưng không biến một truy vấn trái với cấu trúc khóa thành truy vấn hiệu quả.

## 1. Bảng đích và kiểu kết quả là hai quyết định khác nhau

Hãy tưởng tượng dịch vụ đơn hàng có hai màn hình:

1. Xem chi tiết đơn theo `order_id`.
2. Xem 20 đơn gần nhất của một khách hàng trong một tháng.

Để phục vụ hai đường đọc, ứng dụng có thể có hai bảng vật lý:

~~~sql
CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    created_at timestamp,
    status text,
    total_amount decimal
);

CREATE TABLE orders_by_customer_month (
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    PRIMARY KEY ((customer_id, month_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

Cùng một đơn hàng có thể xuất hiện trong hai bảng, vì Cassandra thường **nhân bản dữ liệu theo mô hình đọc**. Nếu chỉ cần giao diện danh sách đơn, ứng dụng không nhất thiết tải đầy đủ object nghiệp vụ từ bảng chi tiết.

Một request có hai câu hỏi độc lập:

| Câu hỏi | Được quyết định bởi | Ví dụ |
| --- | --- | --- |
| **Đọc từ bảng nào?** | `FROM` của CQL, `@Table` của domain class, hoặc fluent `inTable` | `orders_by_customer_month` |
| **Ánh xạ các row trả về thành kiểu Java nào?** | `Class<T>` của phương thức `select` hoặc fluent `as` | `OrderByCustomerMonth`, `OrderListItem` |

Hai câu hỏi có thể trùng đáp án về ý tưởng: ta thường đọc bảng `orders_by_id` và nhận một entity `OrderById`. Nhưng khi viết dashboard, export hay endpoint đọc danh sách, **bảng nguồn vẫn như cũ**, trong khi kiểu kết quả có thể là DTO ít trường hơn.

### 1.1. Luồng xử lý

~~~mermaid
flowchart TD
    A["Service cần danh sách đơn"] --> B["Chọn bảng: orders_by_customer_month"]
    B --> C["Xây điều kiện theo partition key"]
    C --> D["CassandraTemplate / CQL"]
    D --> E["Cassandra Java Driver"]
    E --> F["Rows từ bảng vật lý"]
    F --> G["MappingCassandraConverter"]
    G --> H["OrderByCustomerMonth"]
    G --> I["OrderListItem DTO"]
    G --> J["OrderListProjection interface"]
~~~

- **Bảng nguồn** quyết định CQL được thực thi và những cột thực sự tồn tại.
- **Domain type** giúp Spring Data biết metadata bảng, tên cột, primary key và cách chuyển tên property trong tiêu chí truy vấn.
- **Kiểu kết quả** giúp converter xây dựng entity/DTO hoặc projection từ những cột đã trả về.
- **Cassandra Java Driver** giải mã CQL type và thực thi câu lệnh; nó không tự hiểu nghiệp vụ quan hệ như JPA.

Spring Data Cassandra dùng `MappingCassandraConverter` theo mặc định để đọc row thành object Java. Cấu hình converter/type codec phù hợp vẫn cần thiết nếu kiểu domain đặc biệt không có chuyển đổi mặc định.

## 2. Trường hợp đơn giản: @Table quyết định bảng

Nếu một Java class đại diện trực tiếp cho một bảng:

~~~java
import java.math.BigDecimal;
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

    @Column("created_at")
    private Instant createdAt;

    @Column("status")
    private String status;

    @Column("total_amount")
    private BigDecimal totalAmount;

    public OrderById() {
    }

    // Constructors, getters và setters còn lại...
}
~~~

`@Table("orders_by_id")` là metadata về bảng cho các operation dựa trên `OrderById.class`. Khi ứng dụng đọc theo ID:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.core.CassandraTemplate;

public class OrderReader {

    private final CassandraTemplate template;

    public OrderReader(CassandraTemplate template) {
        this.template = template;
    }

    public OrderById findById(UUID orderId) {
        return template.selectOneById(orderId, OrderById.class);
    }
}
~~~

CassandraTemplate có thể suy bảng `orders_by_id` từ `@Table`; kiểu `OrderById.class` cũng là kiểu nhận kết quả. `selectOneById` trả về object hoặc `null` nếu không có row, theo hợp đồng API/version. Lớp service cần chuyển thành `Optional`, ngoại lệ hoặc HTTP 404 theo nhu cầu.

Nếu cần điều kiện thay vì trực tiếp theo ID:

~~~java
import static org.springframework.data.cassandra.core.query.Criteria.where;
import static org.springframework.data.cassandra.core.query.Query.query;

import org.springframework.data.cassandra.core.query.Query;

Query q = query(where("order_id").is(orderId));

OrderById order = template.selectOne(q, OrderById.class);
~~~

Vẫn có hai quyết định: bảng là `orders_by_id` theo entity, và kiểu trả về là `OrderById`. `@Column("order_id")` hay `@PrimaryKey("order_id")` giúp chuyển giữa tên property `orderId` và tên cột `order_id`.

### 2.1. getTableName để kiểm tra metadata

Khi nghi ngờ bảng được chọn không đúng, bạn có thể kiểm tra metadata:

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;

CqlIdentifier tableName = template.getTableName(OrderById.class);
System.out.println(tableName.asCql(true));
~~~

`getTableName(Class<?>)` trả về một `CqlIdentifier` của driver, có xử lý đúng quy tắc định danh CQL. Kiểm tra này giúp xác minh tên bảng trong mapping; nó **không xác minh bảng đó thực sự tồn tại trên cluster**. Kiểm tra schema riêng trong `cqlsh` hoặc metadata của Cassandra.

### 2.2. @Table không tạo bảng khi ứng dụng đọc

Nếu `@Table("orders_by_id")` tồn tại trong Java nhưng bảng CQL chưa được tạo hoặc tên không khớp, lời gọi select có thể thất bại với lỗi schema. Annotation không tự tạo keyspace/bảng trừ khi ứng dụng đã được cấu hình quản lý schema tương ứng. Với production, thường tạo schema bằng migration được kiểm soát.

Nếu đổi `@Table` trong Java từ `orders_by_id` sang `orders_archive`, dữ liệu cũ **không tự di chuyển** sang bảng mới. Chỉ đường đọc/ghi dựa vào mapping thay đổi; phải có quy trình di chuyển dữ liệu nếu cần.

## 3. Bảng có khóa ghép: domain type mô tả đường truy cập

Bảng `orders_by_customer_month` có partition key ghép `(customer_id, month_bucket)` và clustering columns `created_at, order_id`. Để minh họa việc ánh xạ DTO về sau, ví dụ chọn khai báo các thành phần khóa **trực tiếp trên entity**. Nhờ vậy, `orderId` và `createdAt` là các property cấp cao nhất của domain type.

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_customer_month")
public class OrderByCustomerMonth {

    @PrimaryKeyColumn(
        name = "customer_id",
        ordinal = 0,
        type = PrimaryKeyType.PARTITIONED
    )
    private UUID customerId;

    @PrimaryKeyColumn(
        name = "month_bucket",
        ordinal = 1,
        type = PrimaryKeyType.PARTITIONED
    )
    private String monthBucket;

    @PrimaryKeyColumn(
        name = "created_at",
        ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING
    )
    private Instant createdAt;

    @PrimaryKeyColumn(
        name = "order_id",
        ordinal = 3,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.ASCENDING
    )
    private UUID orderId;

    @Column("status")
    private String status;

    @Column("total_amount")
    private BigDecimal totalAmount;

    public OrderByCustomerMonth() {
    }

    // Constructors, getters và setters còn lại...
}
~~~

**Lưu ý:** Spring Data Cassandra cũng hỗ trợ `@PrimaryKeyClass` và `@PrimaryKey` với khóa nhúng, nhưng khi đó tên property của khóa nằm dưới một object trung gian. Nếu dùng khóa nhúng cùng projection/DTO, phải xác minh cách framework xử lý property path và cột được chọn. Ở đây, entity dùng khóa trực tiếp để phần `as(OrderListItem.class)` ở dưới có các property tương ứng rõ ràng. Đoạn mã Java lược bỏ getters/setters và constructor phục vụ mapping để tập trung vào cấu trúc khóa.

Truy vấn “20 đơn mới nhất của khách trong tháng”:

~~~java
Query q = query(where("customer_id").is(customerId))
    .and(where("month_bucket").is("2026-11"))
    .limit(20);

List<OrderByCustomerMonth> items =
    template.select(q, OrderByCustomerMonth.class);
~~~

Ở đây:

- `OrderByCustomerMonth.class` quy định **bảng theo `@Table`** và **kiểu kết quả**.
- `where("customer_id")` + `where("month_bucket")` xác định đầy đủ partition key.
- `limit(20)` giới hạn số hàng trả về trong CQL; không phải số trang của API.
- `WITH CLUSTERING ORDER BY (created_at DESC, ...)` cho phép lấy đơn mới nhất **trong partition** trước theo thứ tự khai báo.
- Nếu cần danh sách liên tục qua hai tháng, ứng dụng phải biết đọc các bucket tương ứng và ghép kết quả; Cassandra không tự ORDER BY toàn cụm.

## 4. Khi muốn chọn bảng tường minh: fluent inTable(…)

`CassandraTemplate` cũng cung cấp **fluent API** để tách biệt bảng truy vấn khỏi domain type.

Ví dụ:

~~~java
import java.util.List;
import org.springframework.data.cassandra.core.CassandraOperations;
import org.springframework.data.cassandra.core.query.Query;

public class CustomerOrderReader {

    private final CassandraOperations operations;

    public CustomerOrderReader(CassandraOperations operations) {
        this.operations = operations;
    }

    public List<OrderByCustomerMonth> list(
            UUID customerId, String bucket) {

        Query q = query(where("customer_id").is(customerId))
            .and(where("month_bucket").is(bucket))
            .limit(20);

        return operations.query(OrderByCustomerMonth.class)
            .inTable("orders_by_customer_month")
            .matching(q)
            .all();
    }
}
~~~

API `query(DomainType.class)` bắt đầu bằng **kiểu domain**, sau đó:

1. `inTable("orders_by_customer_month")` **ghi đè tên bảng vật lý** mà thao tác sẽ đọc.
2. `matching(q)` đưa điều kiện và tùy chọn truy vấn vào operation.
3. `all()` thực thi, trả một danh sách object theo kiểu hiện hành.

Trong trường hợp ví dụ, `inTable` lặp lại cùng tên bảng trong `@Table` nhằm minh họa cú pháp. Khi class đã có annotation đúng, **không bắt buộc** gọi `inTable`.

### 4.1. Khi nào inTable thực sự hữu ích?

Giả sử cùng một layout dữ liệu tồn tại ở hai bảng có schema tương thích:

~~~sql
CREATE TABLE orders_by_customer_month_archive (
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    PRIMARY KEY ((customer_id, month_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

Chúng có **cùng tên cột, kiểu và khóa**, nhưng đường vận hành/lưu trữ khác nhau. Khi service muốn đọc archive:

~~~java
List<OrderByCustomerMonth> archived =
    operations.query(OrderByCustomerMonth.class)
        .inTable("orders_by_customer_month_archive")
        .matching(q)
        .all();
~~~

Bảng `orders_by_customer_month_archive` là **đích thật của CQL**, còn metadata `OrderByCustomerMonth.class` vẫn được dùng để chuyển tên property và đọc kết quả. Cách dùng này chỉ hợp lý khi hai schema thực sự tương thích. Nếu bảng archive khác loại khóa, tên cột hoặc kiểu CQL, cần tạo domain mapping riêng hoặc điều chỉnh câu lệnh/projection đúng thực tế.

Không nên dùng `inTable` như cách ngẫu nhiên chọn một bảng bất kỳ rồi mong converter tự sửa sai mọi khác biệt schema.

### 4.2. inTable nhận String hoặc CqlIdentifier

Fluent API có overload với chuỗi và với `com.datastax.oss.driver.api.core.CqlIdentifier`:

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;

CqlIdentifier table =
    CqlIdentifier.fromCql("orders_by_customer_month_archive");

List<OrderByCustomerMonth> archived =
    operations.query(OrderByCustomerMonth.class)
        .inTable(table)
        .matching(q)
        .all();
~~~

`CqlIdentifier` giúp xử lý cú pháp định danh CQL, đặc biệt khi schema dùng identifier có chữ hoa hoặc dấu ngoặc kép. Ví dụ tên `"OrderArchive"` **có phân biệt chữ hoa** khác với `orderarchive` do Cassandra chuẩn hóa định danh không quoted.

Tên bảng không phải tham số có thể bind bằng dấu `?` như giá trị `customer_id`. Nếu bảng được chọn theo cấu hình động, hãy dùng **allowlist** các bảng đã được provision và kiểm tra quyền, thay vì nối trực tiếp tên do người dùng gửi vào câu CQL.

### 4.3. Hạn chế của chọn bảng động

Cassandra vốn thiết kế bảng theo access pattern. Tự tạo một bảng mới cho mỗi khách hàng hoặc chọn bảng bằng HTTP parameter thường kéo theo:

- Schema proliferation, tăng chi phí metadata và vận hành.
- Khó áp dụng migration/repair/backup/retention đồng nhất.
- Khó xác minh partition key và paging của mọi bảng.
- Nguy cơ đọc nhầm dữ liệu giữa tenant nếu routing hoặc phân quyền sai.

Nếu nhiều tenant dùng **cùng** access pattern, đa số trường hợp nên cân nhắc `tenant_id` trong partition key hoặc kiến trúc tenant isolation có chủ đích, không mặc định “mỗi tenant một bảng”.

## 5. Kiểu kết quả khác kiểu domain: fluent as(…)

Một màn hình danh sách có thể chỉ cần bốn trường:

- `order_id`
- `created_at`
- `status`
- `total_amount`

Ta không cần trả toàn bộ entity có nhiều trường nội bộ. Fluent template hỗ trợ:

~~~java
List<OrderListItem> items =
    operations.query(OrderByCustomerMonth.class)
        .inTable("orders_by_customer_month")
        .as(OrderListItem.class)
        .matching(q)
        .all();
~~~

**Ý nghĩa rất quan trọng:**

- `query(OrderByCustomerMonth.class)` giữ **domain type**, nơi Spring Data lấy mapping của bảng và property để dựng CQL.
- `inTable(...)` chọn **bảng vật lý**.
- `as(OrderListItem.class)` chọn **kiểu Java của kết quả**.
- `matching(q)` giữ điều kiện query.
- `all()` bắt đầu thực thi và trả `List<OrderListItem>`.

Thứ tự gọi trên là cú pháp hợp lệ của fluent API. Có thể bỏ `inTable` nếu đúng bảng đã được xác định bằng `@Table`.

### 5.1. DTO dạng record

Với Java/Spring Data hỗ trợ record-based projection, một DTO có thể được viết:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderListItem(
    UUID orderId,
    Instant createdAt,
    String status,
    BigDecimal totalAmount
) {
}
~~~

Mục tiêu là một object chỉ có đúng các field màn hình dùng. Tên component và tên property của domain cần khớp theo cơ chế mapping; ví dụ `orderId` của domain được map tới cột `order_id`, `totalAmount` map tới `total_amount`.

Khi dùng DTO có constructor, Spring Data dựa trên metadata/parameter names để biết trường cần đọc. Hãy đảm bảo dự án giữ thông tin tên tham số biên dịch (khi cần) hoặc dùng annotation constructor phù hợp, đồng thời kiểm tra khả năng project sang record trong **phiên bản Spring Data Cassandra** đang chạy.

Với DTO class có nhiều constructor, cần giúp framework chọn constructor bằng `@PersistenceCreator` khi thích hợp. Nếu DTO chứa logic tùy biến phức tạp, nên tách bước mapping trong service để dễ kiểm soát.

### 5.2. Interface projection

Có thể dùng interface đóng (closed projection):

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public interface OrderListView {
    UUID getOrderId();
    Instant getCreatedAt();
    String getStatus();
    BigDecimal getTotalAmount();
}
~~~

Và truy vấn:

~~~java
List<OrderListView> views =
    operations.query(OrderByCustomerMonth.class)
        .as(OrderListView.class)
        .matching(q)
        .all();
~~~

Spring Data có thể tạo projection proxy cho interface, ánh xạ getter tới các thuộc tính được hỗ trợ của domain. Với **closed projection** (getter khớp property), framework có cơ sở để tối ưu các cột cần đọc. Với **open projection** dùng SpEL/`@Value`, framework có thể phải tải nhiều dữ liệu hơn vì biểu thức có thể truy cập thuộc tính ngoài danh sách getter.

Không nên xem projection là tính năng “tự động giảm network payload trong mọi trường hợp”. Cần xác minh CQL được phát sinh và những cột thật sự được chọn. Một số cấu hình `Query`, converter hoặc projection type có thể khiến select lấy đủ tất cả cột.

### 5.3. Bảng nguồn, domain type và result type độc lập ra sao?

| Trường hợp | Cấu hình | Kết quả |
| --- | --- | --- |
| Đọc entity theo annotation | `operations.query(OrderById.class).all()` | Bảng theo `@Table("orders_by_id")`, trả `OrderById` |
| Ghi đè bảng tương thích | `query(OrderByCustomerMonth.class).inTable("..._archive").all()` | Đọc archive, trả `OrderByCustomerMonth` |
| Chỉ đổi kiểu trả về | `query(OrderByCustomerMonth.class).as(OrderListItem.class).all()` | Đọc bảng mặc định, trả DTO |
| Ghi đè cả hai | `query(OrderByCustomerMonth.class).inTable("..._archive").as(OrderListItem.class).all()` | Đọc archive, trả DTO |
| CQL tường minh | `select("SELECT ... FROM ...", OrderListItem.class)` | `FROM` trong CQL quyết định bảng, class quyết định mapping |

Điểm cuối đặc biệt quan trọng: **`select(String cql, Class<T>)` không lấy `@Table` của `T` để thay thế `FROM` đã ghi trong chuỗi CQL.** Nó thực thi query do bạn đưa vào rồi ánh xạ các row sang kiểu `T`.

## 6. select(Query, Class<T>) và select(String CQL, Class<T>) khác gì?

`CassandraTemplate` cung cấp nhiều overload:

~~~java
List<OrderById> a =
    template.select(qById, OrderById.class);

OrderById b =
    template.selectOne(qById, OrderById.class);

List<OrderListItem> c =
    template.select(cqlString, OrderListItem.class);
~~~

**Overload nhận `Query`** dùng metadata của `entityClass` để sinh CQL và suy bảng. Nếu bạn truyền `OrderListItem.class` chỉ để muốn kết quả là DTO nhưng DTO không map bảng đúng, framework có thể suy bảng/column không đúng mục tiêu. Đây là lý do cần fluent API `query(Domain.class).as(Dto.class)` khi muốn tách hai trách nhiệm.

**Overload nhận `String cql`** đã có `SELECT ... FROM ...`. Bảng vật lý lấy từ chuỗi CQL; `entityClass` nói cách chuyển row thành Java type. Không nên viết câu CQL bằng nối chuỗi các giá trị người dùng vì dễ gây lỗi cú pháp/bảo mật và bỏ qua lợi ích prepared statements.

### 6.1. Ví dụ dùng Statement có binding thay cho nối chuỗi

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement stmt = SimpleStatement.builder(
        "SELECT order_id, created_at, status, total_amount "
      + "FROM orders_by_customer_month "
      + "WHERE customer_id = ? AND month_bucket = ? "
      + "LIMIT 20")
    .addPositionalValue(customerId)
    .addPositionalValue("2026-11")
    .build();

List<OrderListItem> items =
    template.select(stmt, OrderListItem.class);
~~~

Ví dụ này dùng driver `SimpleStatement` với bound values; kiểu Java `OrderListItem` nhận dữ liệu từ các cột của CQL. Hãy kiểm tra rằng DTO có cơ chế ánh xạ phù hợp tên cột/constructor theo version Spring Data.

Đối với câu CQL lặp lại liên tục, prepared statement/bound statement là đường dùng phổ biến. `CassandraTemplate` cũng có cơ chế sử dụng prepared statement tùy cách API được cấu hình; khi cần kiểm soát trực tiếp execution profile, consistency và paging state, bạn có thể chọn `CqlSession` với prepared/bound statements phù hợp.

### 6.2. Các lỗi khi dùng CQL tường minh

~~~java
// Không nên: FROM của CQL đã là bảng danh sách,
// nhưng DTO được thiết kế cho các cột không tồn tại trong bảng này.
template.select(
    "SELECT * FROM orders_by_customer_month WHERE ...",
    PaymentDetails.class
);
~~~

Nếu `PaymentDetails` có field bắt buộc `paymentProvider` hoặc constructor yêu cầu cột không có trong bảng nguồn, mapping có thể báo lỗi hoặc tạo object thiếu thông tin tùy cách chuyển đổi. **DTO không tạo ra cột không có trong Cassandra.**

Không đặt `SELECT *` cho một DTO rất nhỏ rồi nghĩ chắc chắn tiết kiệm băng thông. Nếu muốn kiểm soát payload, chọn các cột cần thiết trong CQL hoặc xác minh cơ chế chọn cột khi dùng projection.

## 7. Ánh xạ tên cột: @Column, camelCase và alias

Trong ví dụ, Java dùng:

~~~text
orderId      createdAt      totalAmount
~~~

Trong CQL dùng:

~~~text
order_id     created_at     total_amount
~~~

`@Column("...")` giúp quy định ánh xạ tường minh:

~~~java
@Column("order_id")
private UUID orderId;

@Column("created_at")
private Instant createdAt;

@Column("total_amount")
private BigDecimal totalAmount;
~~~

Khi không có annotation, Spring Data có các quy ước đặt tên tùy naming strategy. Với hệ thống cần tương thích nhiều bản migration/schema, khai báo tường minh giúp giảm sự phụ thuộc vào default naming.

### 7.1. Alias trong CQL phải phù hợp với kiểu kết quả

Giả sử truy vấn trực tiếp:

~~~sql
SELECT
    order_id,
    created_at,
    status,
    total_amount
FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
LIMIT 20;
~~~

Các cột trả về có tên như schema, converter có thể map chúng theo metadata property/column. Nếu query có alias khác thường:

~~~sql
SELECT
    order_id AS id,
    status AS state
FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?;
~~~

thì DTO/projection cần khớp tên `id`, `state` hoặc có mapping tường minh tương ứng. Không giả định `OrderListItem.orderId` sẽ tự đọc alias `id` nếu converter không biết quy tắc đó.

Đặc biệt, kết quả của hàm hoặc phép tính CQL có thể trả tên cột tổng hợp. Khi cần ánh xạ vào DTO, nên **đặt alias rõ ràng** và kiểm tra kiểu CQL của expression. Những query kiểu aggregation, function result hoặc vector similarity càng cần chú ý phần này.

### 7.2. Không tự suy từ case khi dùng quoted identifier

Cassandra chuẩn hóa identifier không quoted về chữ thường. Tên quoted như `"OrderEvents"` hoặc `"orderId"` có phân biệt chữ hoa/chữ thường. Khi bảng được tạo với quoted identifier, `@Table`, `@Column`, `inTable(CqlIdentifier)` và CQL trực tiếp cần cùng quy ước.

Tránh tạo schema có tên khó đoán/khác kiểu chữ nếu không có yêu cầu bắt buộc. Khi cần tương tác với schema sẵn có, dùng `CqlIdentifier` để tránh tự ghép cặp dấu ngoặc kép một cách sai sót.

## 8. Chọn result type nào cho mỗi đường đọc?

### 8.1. Entity đầy đủ

Chọn entity khi logic nghiệp vụ cần toàn bộ fields của row hoặc muốn thao tác mapping thống nhất:

~~~java
OrderById order =
    template.selectOneById(orderId, OrderById.class);
~~~

Ưu điểm: sử dụng toàn bộ metadata entity, thuận tiện cho truy cập theo key. Nhược điểm: nếu endpoint chỉ dùng 2–3 trường thì dễ lấy thừa dữ liệu khi query dùng `SELECT *`.

### 8.2. Closed interface projection

Chọn projection khi chỉ cần vài getter:

~~~java
List<OrderListView> views =
    operations.query(OrderByCustomerMonth.class)
        .as(OrderListView.class)
        .matching(q)
        .all();
~~~

Ưu điểm: API ở tầng read model gọn, có khả năng tối ưu cột. Nhược điểm: proxy và mapping cần được kiểm chứng; nested/open projection có hạn chế khác với DTO thường.

### 8.3. DTO dạng class/record

Chọn DTO khi muốn một cấu trúc trả về rõ ràng, dễ serialize:

~~~java
List<OrderListItem> items =
    operations.query(OrderByCustomerMonth.class)
        .as(OrderListItem.class)
        .matching(q)
        .all();
~~~

Ưu điểm: hợp đồng trả về rõ, không lộ entity nội bộ. Nhược điểm: constructor/property names/field aliases cần map đúng, có thể cần custom conversion với những kiểu phức tạp.

### 8.4. Raw Row hoặc CqlSession

Khi truy vấn trả nhiều expression/aggregate khó map, hoặc cần điều khiển driver chính xác:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement statement = SimpleStatement.builder(
        "SELECT status FROM orders_by_id WHERE order_id = ?")
    .addPositionalValue(orderId)
    .build();

Row row = session.execute(statement).one();

String status = row == null
    ? null
    : row.getString("status");
~~~

Đây là hướng chủ động xử lý kết quả driver, hữu ích khi không cần full entity converter. Tuy nhiên, việc phải tự đọc type, xử lý null, bind, paging và exception có thể làm mã rải rác. Nên giữ các thao tác kiểu này trong một adapter/repository chuyên biệt, đồng thời tái sử dụng `CqlSession` do Spring quản lý.

| Kết quả | Khi nên dùng | Điều cần kiểm tra |
| --- | --- | --- |
| Entity | CRUD/read theo key và domain rõ ràng | `@Table`/`@PrimaryKey`/`@Column` khớp schema |
| Interface projection | View nhỏ, getter theo domain | Getter, column selection, open/closed projection |
| DTO | API/report có contract ổn định | Constructor, alias, converter, phiên bản Spring Data |
| Raw `Row` | Truy vấn đặc thù và kiểm soát driver | Null, CQL type, bind và lỗi |

## 9. selectOne, first, one, all và kết quả rỗng

Các API kết thúc query có khác biệt về mục tiêu:

| API | Kết quả mong đợi | Điều nên nhớ |
| --- | --- | --- |
| `template.select(query, Entity.class)` | `List<Entity>` | Có thể nhiều row; không dùng vô hạn nếu partition lớn |
| `template.selectOne(query, Entity.class)` | Một object hoặc null | Query nên ràng buộc để lấy tối đa một row |
| `operations.query(Type.class).matching(q).all()` | Danh sách | Thực thi khi gọi `all()` |
| `...first()` | Row đầu tiên nếu có | Cần hiểu thứ tự clustering của bảng |
| `...one()` | Một kết quả theo hợp đồng API | Cần bảo đảm query thật sự chỉ trả số row phù hợp |
| `...stream()` | Luồng row được chuyển đổi | Quản lý vòng đời và tải nhiều page hợp lý |

Sự khác nhau giữa `first()` và `one()` có ý nghĩa khi query trả nhiều hàng: nếu cần lấy dòng đầu theo clustering order thì `first()` phù hợp hơn, còn `one()` biểu đạt kỳ vọng một kết quả duy nhất. Tránh xem `one()` như một cách tối ưu hóa truy vấn vốn trả hàng nghìn row.

### 9.1. selectOne không thay thế điều kiện khóa

Ví dụ muốn đọc chi tiết đơn theo `order_id` từ `orders_by_id`:

~~~sql
SELECT * FROM orders_by_id WHERE order_id = ?;
~~~

Câu này hợp partition key, trả tối đa một row về mặt schema. Nhưng câu:

~~~sql
SELECT * FROM orders_by_customer_month
WHERE customer_id = ? AND month_bucket = ?;
~~~

có thể trả nhiều row. Nếu gọi `selectOne` mà không giới hạn hoặc không xác định row cần lấy, đó là lỗi thiết kế truy vấn. Nếu yêu cầu “đơn mới nhất”, hãy dùng clustering order với `LIMIT 1`, rồi lấy dòng đầu một cách tường minh.

## 10. Chọn bảng đúng phải đi đôi với chọn partition key đúng

Hai bảng được xây để phục vụ truy vấn khác nhau:

~~~sql
-- Chi tiết theo ID:
SELECT * FROM orders_by_id
WHERE order_id = ?;

-- Danh sách theo khách/tháng:
SELECT * FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
LIMIT 20;
~~~

Lỗi thường gặp khi dùng template:

~~~java
// Đúng cú pháp Java nhưng CQL sẽ không có partition key đủ:
Query q = query(where("status").is("PAID"));

List<OrderByCustomerMonth> orders =
    template.select(q, OrderByCustomerMonth.class);
~~~

Trường `status` không thuộc partition key/clustering key của bảng `orders_by_customer_month` trong schema ví dụ. Cassandra có thể từ chối query hoặc cần giải pháp index/filtering phù hợp; không nên mặc định dùng `ALLOW FILTERING` để ép toàn bảng. Thay `OrderByCustomerMonth.class` bằng một DTO cũng **không sửa được access pattern**.

Nếu sản phẩm cần “đơn đã PAID trong cửa hàng hôm nay”, nên xem xét bảng theo `(store_id, status, day_bucket)` với clustering theo thời gian, cùng cơ chế đồng bộ những bản sao dữ liệu. Template chỉ chọn và đọc bảng đã có; mô hình khóa vẫn do bạn quyết định.

### 10.1. Bảng khác có thể mang dữ liệu không đồng bộ

Giả sử lệnh ghi trạng thái `PAID` đã thành công trong `orders_by_id`, nhưng projector chưa cập nhật `orders_by_customer_month`. Khi đọc bằng `CassandraTemplate`:

~~~text
select(orders_by_id)              -> status = PAID
select(orders_by_customer_month)  -> status = CREATED
~~~

Đây có thể là **projection lag giữa hai bảng**. Chọn `LOCAL_QUORUM` cho cả hai thao tác không có nghĩa Cassandra tự bảo đảm chúng chứa cùng một snapshot nghiệp vụ. Replication theo node là vấn đề khác với đồng bộ read model cấp ứng dụng.

Hệ thống cần xác định:

- Bảng nào là nguồn sự thật cho từng trường.
- Đường đồng bộ nào cập nhật các bảng phục vụ truy vấn.
- Độ trễ được chấp nhận cho màn hình danh sách.
- Cách chống retry/event sai thứ tự và quy trình đối soát.

`inTable` không tự giải quyết dữ liệu sai lệch nếu hai bảng vật lý khác trạng thái.

## 11. Column projection giúp giảm dữ liệu đọc ra

Giả sử bảng có 25 cột, nhưng endpoint danh sách dùng bốn cột. Việc chỉ đổi kiểu trả về thành DTO **có thể** giúp Spring Data tối ưu column selection tùy projection và cơ chế chuyển đổi; tuy nhiên phải kiểm chứng câu CQL thực tế.

CQL tường minh dễ nhìn nhất:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
LIMIT 20;
~~~

So với `SELECT *`, câu này chỉ trả những cột được liệt kê. Đối với row rộng hoặc cột UDT/collection lớn, giảm dữ liệu trả về có thể tiết kiệm network, bộ nhớ và chi phí giải mã.

Trong Spring Data Cassandra, `Query` hỗ trợ cấu hình cột được chọn; các phiên bản mới còn có cơ chế projection function của `StatementFactory`. Ví dụ một lựa chọn cần kiểm chứng:

~~~java
// Khái niệm: chỉ chọn các cột API cần, và ánh xạ vào DTO.
// Cú pháp Query.select(Columns...) / Query.columns(...)
// phụ thuộc phiên bản Spring Data Cassandra được dùng.
~~~

Nếu cần tránh phụ thuộc version, dùng `SimpleStatement` với `SELECT` tường minh và `template.select(statement, OrderListItem.class)` như phần 6.1.

**Không suy rằng DTO luôn làm Cassandra đọc ít cột**, cũng không suy rằng giảm field trong HTTP response có tác dụng giảm CQL network payload. Mọi tối ưu hóa cần đo từ câu CQL được phát sinh, byte trả về và latency.

## 12. Paging và giới hạn khi ánh xạ kết quả

Cassandra không phù hợp với phân trang offset không giới hạn kiểu `OFFSET 100000 LIMIT 20`. Driver thường sử dụng **paging state** để tiếp tục một query hợp lệ.

Phân biệt:

- `LIMIT 20` trong CQL: giới hạn tổng số row của truy vấn đó.
- **Page size** của driver: số row mục tiêu mỗi lần fetch mạng.
- **Paging state**: token để tiếp tục query theo ngữ cảnh cũ.
- **API cursor**: hợp đồng ứng dụng cung cấp cho client, có thể chứa/đại diện paging state và thông tin bucket.

`CassandraTemplate` hỗ trợ `slice(query, Entity.class)` và `CassandraPageRequest` để làm việc với paging theo phiên bản Spring Data. Ví dụ mang tính định hướng:

~~~java
// Query q đã chứa điều kiện partition key.
// Hãy thiết lập CassandraPageRequest/paging state theo API của
// phiên bản Spring Data Cassandra đang chạy, rồi:
Slice<OrderByCustomerMonth> page =
    template.slice(q, OrderByCustomerMonth.class);
~~~

Mã trên nhấn mạnh điểm kết thúc `slice(Query, Class)`; phần tạo page request phụ thuộc contract của hệ thống và version API nên phải đối chiếu trước khi triển khai. Không dùng PageRequest có offset tùy ý rồi mong Cassandra hỗ trợ truy cập trang 10.000 bằng cách nhảy trực tiếp.

### 12.1. Khi kết quả là DTO hay projection

Với màn hình chỉ cần `OrderListItem`, có thể dùng fluent `as(OrderListItem.class)` cho truy vấn danh sách nhỏ. Với paging/streaming lớn, xem API slice/stream mà version Spring Data hỗ trợ cho loại kết quả đã chọn; cần đo việc row được ánh xạ và bộ nhớ sử dụng.

Đừng lấy toàn bộ dữ liệu thành `List<OrderByCustomerMonth>` rồi chuyển hàng triệu object thành DTO tại controller. Tối ưu cần bắt đầu từ **giới hạn query, partition key và cột dữ liệu**.

### 12.2. Phân trang xuyên bucket

Nếu một khách có dữ liệu của tháng 11, 10 và 09, Cassandra không có một paging state tự sắp xếp ba partition thành một danh sách chung. Ứng dụng phải thiết kế cách đi qua từng bucket theo thứ tự, hoặc merge dữ liệu nhiều partition với giới hạn đồng thời, và tạo cursor chứa ngữ cảnh.

Khi dữ liệu tiếp tục được ghi trong lúc phân trang, có thể xảy ra việc bản ghi mới chen vào đầu danh sách. Nên xác định hợp đồng API về snapshot thời điểm bắt đầu duyệt, độ trễ projection và cách chống hiển thị trùng/thiếu khi client xem nhiều trang.

## 13. Kiểm soát kiểu mapping: UUID, Instant, BigDecimal và UDT

Tên cột khớp chưa đủ; kiểu CQL và Java cũng phải tương thích.

| CQL | Java thường dùng | Lưu ý |
| --- | --- | --- |
| `uuid` | `UUID` | Không nhầm với `timeuuid` khi schema yêu cầu UUID version 1 |
| `timestamp` | `Instant` | Cassandra lưu theo mili giây; mất phần nano nhỏ hơn mili giây |
| `decimal` | `BigDecimal` | Phù hợp số tiền có precision; domain phải quy định scale |
| `text` | `String` | Chuỗi UTF-8 |
| `set<text>` | `Set<String>` | Giới hạn kích thước collection, không dùng như event log vô hạn |
| `frozen<shipping_address>` | Class có `@UserDefinedType` / `UdtValue` | Cần metadata UDT và converter phù hợp |

Nếu DTO có constructor đòi `Instant createdAt` nhưng CQL trả `created_at` dưới một alias khác chưa được mapping, kết quả có thể lỗi hoặc null tùy loại đối tượng. Nếu DTO dùng `Double totalAmount` nhưng CQL là `decimal`, dễ sai precision tiền tệ. Đừng “chữa” bằng cast thiếu kiểm soát; hãy chọn kiểu domain đúng và converter phù hợp.

### 13.1. Custom converter

Nếu ứng dụng có `Money` hoặc `OrderId` là value object, phải định nghĩa cách chuyển đổi với các kiểu Java Driver hỗ trợ. Ví dụ `OrderId` có thể chuyển qua `UUID`, `Money` qua `BigDecimal` theo contract.

`@Table` và `as(...)` không tự tạo codec mới. Converter/codec phải được đăng ký đúng phạm vi, và có test round-trip theo schema thực tế. Khác với JPA, Spring Data Cassandra không tự khởi tạo quan hệ foreign key/cascade giữa nhiều bảng đọc.

## 14. Đường đọc bằng fluent template có thể tái sử dụng

Một thiết kế service gọn cho nhiều endpoint:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.core.CassandraOperations;
import org.springframework.data.cassandra.core.query.Query;

import static org.springframework.data.cassandra.core.query.Criteria.where;
import static org.springframework.data.cassandra.core.query.Query.query;

public class CustomerOrderReadService {

    private final CassandraOperations ops;

    public CustomerOrderReadService(CassandraOperations ops) {
        this.ops = ops;
    }

    public List<OrderListItem> latest(
            UUID customerId,
            String monthBucket) {

        Query q = query(where("customer_id").is(customerId))
            .and(where("month_bucket").is(monthBucket))
            .limit(20);

        return ops.query(OrderByCustomerMonth.class)
            .inTable("orders_by_customer_month")
            .as(OrderListItem.class)
            .matching(q)
            .all();
    }

    public List<OrderListItem> archived(
            UUID customerId,
            String monthBucket) {

        Query q = query(where("customer_id").is(customerId))
            .and(where("month_bucket").is(monthBucket))
            .limit(20);

        return ops.query(OrderByCustomerMonth.class)
            .inTable("orders_by_customer_month_archive")
            .as(OrderListItem.class)
            .matching(q)
            .all();
    }
}
~~~

Điểm khác nhau nằm ở **bảng đích**. Cả hai phương thức vẫn dùng cùng domain metadata `OrderByCustomerMonth.class` và cùng DTO `OrderListItem.class`. Cách này phù hợp nếu schema archive và schema hiện hành tương thích hoàn toàn với các trường query và projection.

Trong production, có thể giảm lặp code bằng một phương thức private nhận enum bảng đã allowlist:

~~~java
enum OrderReadTable {
    CURRENT("orders_by_customer_month"),
    ARCHIVE("orders_by_customer_month_archive");

    final String table;

    OrderReadTable(String table) {
        this.table = table;
    }
}
~~~

Không lấy tên bảng tùy ý từ HTTP header rồi dùng trong `inTable`. Việc routing sang archive cũng cần kiểm tra permission và thời hạn dữ liệu, nhất là nếu bảng chứa thông tin nhiều tenant.

## 15. Những lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Query chạy vào bảng sai | `@Table` không khớp mong muốn hoặc quên `inTable` | Kiểm tra `getTableName(Domain.class)`, CQL thực thi và tên bảng thật |
| Fluent query trả sai kiểu | `as(...)` thiếu hoặc DTO/projection không tương thích | Phân biệt `query(Domain)` và `as(Result)`, kiểm tra fields/constructor |
| Dùng `select(Query, Dto.class)` bị tìm sai bảng | Kiểu DTO bị dùng để suy nguồn CQL | Sử dụng `query(Domain.class).as(Dto.class)` hoặc CQL tường minh |
| DTO có field null bất ngờ | Thiếu cột trong SELECT, alias khác, converter chưa đăng ký | Kiểm tra danh sách cột và mapping |
| Lỗi type conversion | CQL type và Java type không phù hợp | Kiểm tra schema, `@CassandraType` và converters/codecs |
| Bảng archive không đọc được bằng domain cũ | Schema archive khác primary key/cột/kiểu | Tạo domain riêng hoặc sửa truy vấn/migration; không ép mapping |
| Query thiếu partition key | Bảng được thiết kế theo khóa khác | Thiết kế bảng đúng access pattern và truyền đủ khóa |
| `ALLOW FILTERING` làm chậm khi dữ liệu lớn | Quét/lọc nhiều partition | Thiết kế read model mới, tối ưu CQL, đo tải |
| `SELECT *` trả quá nhiều dữ liệu | Bảng có payload rộng và projection không giảm cột | Chỉ rõ cột trong CQL, xác minh projection function |
| `one()` trên query nhiều dòng | Không bảo đảm duy nhất kết quả | Dùng query theo đủ key hoặc `first()`/`LIMIT 1` đúng ngữ nghĩa |
| Paging trang sau thiếu/trùng | Token/bucket bị dùng sai hoặc có ghi đồng thời | Cursor gắn với query, quy tắc snapshot và khóa ổn định |
| Đọc hai bảng khác trạng thái | Projection lag hoặc write path chưa đồng bộ | Kiểm tra nguồn sự thật, revision, retry và đối soát |
| Identifier viết hoa gây lỗi | CQL quoted/unquoted khác nhau | Dùng `CqlIdentifier` và thống nhất quy tắc đặt tên |

### 15.1. Cách kiểm tra nhanh theo lớp

1. **Schema:** `DESCRIBE TABLE` hoặc `system_schema.columns` để xác nhận bảng, primary key, tên/kiểu cột.
2. **Mapping:** `getTableName(Domain.class)`, `@Table`, `@Column` và constructor/getter DTO.
3. **CQL:** Đọc câu lệnh thật của template, điều kiện partition key, `SELECT` columns và `LIMIT`.
4. **Driver:** Kiểm tra consistency, timeout, page size và các lỗi server/driver.
5. **Nghiệp vụ:** Xác minh đúng bảng nguồn sự thật, độ trễ đồng bộ với read model và những người ghi cạnh tranh.
6. **Hiệu năng:** Đo p95/p99, kích thước partition, số rows/page, payload, tombstone và hotspot.

## 16. Thực hành: cùng một bảng, ba kiểu trả về

Bối cảnh: một màn hình của khách hàng cần hiển thị danh sách đơn; cùng dữ liệu có thể được truy vấn từ bảng hiện hành hoặc archive. API cần ba chế độ:

- Chế độ quản trị: xem entity đầy đủ để điều tra.
- Chế độ khách hàng: xem DTO bốn trường.
- Chế độ API nội bộ: xem interface projection.

### 16.1. Chuẩn bị schema

~~~sql
CREATE TABLE orders_by_customer_month (
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    PRIMARY KEY ((customer_id, month_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

Ứng dụng dùng entity `OrderByCustomerMonth` có các trường khóa được khai báo trực tiếp như phần 3.

### 16.2. Ba cách đọc

~~~java
Query q = query(where("customer_id").is(customerId))
    .and(where("month_bucket").is("2026-11"))
    .limit(20);

// 1. Entity đầy đủ:
List<OrderByCustomerMonth> fullRows =
    ops.query(OrderByCustomerMonth.class)
        .matching(q)
        .all();

// 2. DTO:
List<OrderListItem> cards =
    ops.query(OrderByCustomerMonth.class)
        .as(OrderListItem.class)
        .matching(q)
        .all();

// 3. Interface projection:
List<OrderListView> simpleViews =
    ops.query(OrderByCustomerMonth.class)
        .as(OrderListView.class)
        .matching(q)
        .all();
~~~

Cả ba đường đọc đều dùng **một bảng** và cùng partition key. Chúng khác nhau ở kiểu Java nhận kết quả. Nếu kiểm chứng cho thấy DTO chỉ cần vài cột, có thể tối ưu phần select columns theo cơ chế projection/CQL phù hợp với phiên bản Spring Data.

### 16.3. Ghi đè bảng tương thích

Giả sử schema `orders_by_customer_month_archive` đã tồn tại và giống bảng chính:

~~~java
List<OrderListItem> history =
    ops.query(OrderByCustomerMonth.class)
        .inTable("orders_by_customer_month_archive")
        .as(OrderListItem.class)
        .matching(q)
        .all();
~~~

Hãy kiểm chứng CQL thật sự có `FROM orders_by_customer_month_archive`. Nếu bảng archive không chứa tháng đó, kết quả rỗng là bình thường; một projection không tự tạo dữ liệu.

### 16.4. Kiểm thử mapping và truy vấn

| Kịch bản | Kết quả kỳ vọng |
| --- | --- |
| Domain có `@Table("orders_by_customer_month")` | `query(Domain).all()` đọc đúng bảng |
| Thêm `inTable("orders_by_customer_month_archive")` | CQL đọc archive |
| Thêm `as(OrderListItem.class)` | Trả DTO, giữ domain cho query |
| DTO chỉ có vài trường | Chỉ những trường hợp lệ được map; kiểm tra SELECT columns |
| DTO dùng alias sai | Lỗi/thiếu dữ liệu được phát hiện, cần sửa mapping |
| Thiếu `month_bucket` trong điều kiện | Truy vấn không phù hợp partition key ghép |
| Query trả nhiều hàng nhưng gọi `one()` | Phải xử lý theo contract số kết quả |
| Bảng archive thay tên `total_amount` | Mapping cũ không còn phù hợp |
| Dữ liệu giữa bảng chính/archive lệch | Phải xác định quy tắc đồng bộ, không phải lỗi `as` |
| Đọc xuyên nhiều tháng bằng một paging state | Không được giả định sắp xếp/phân trang hợp lệ qua nhiều partition |

### 16.5. Các câu hỏi suy luận

**Câu 1.** `template.select(query, OrderById.class)` lấy tên bảng từ đâu nếu query không chứa `FROM`?

*Gợi ý:* Từ mapping của `OrderById.class`, thường là `@Table("orders_by_id")`.

**Câu 2.** Vì sao `query(OrderByCustomerMonth.class).as(OrderListItem.class)` an toàn hơn `select(query, OrderListItem.class)` khi DTO không có `@Table`?

*Gợi ý:* Fluent API giữ domain type để sinh CQL và dùng result type chỉ để map row.

**Câu 3.** `inTable("orders_archive")` có làm Java entity tự di chuyển dữ liệu từ bảng hiện hành sang archive không?

*Gợi ý:* Không; chỉ thay bảng trong thao tác CQL, không thay dữ liệu/schema.

**Câu 4.** Một DTO chỉ có hai trường nhưng query dùng `SELECT *`. Có chắc payload mạng nhỏ hơn không?

*Gợi ý:* Không; cần kiểm chứng cột thực sự được chọn hoặc dùng select columns tường minh.

**Câu 5.** Tại sao `as(AnotherDto.class)` không thể giúp query `WHERE status = ?` chạy hiệu quả trên bảng partition theo `customer_id, month_bucket`?

*Gợi ý:* Result mapping không thay schema/partition key.

**Câu 6.** `LOCAL_QUORUM` khi đọc hai bảng có bảo đảm hai bảng cùng revision nghiệp vụ không?

*Gợi ý:* Không; replication consistency khác với tiến độ đồng bộ read model.

**Câu 7.** Khi dùng một tên bảng động từ client, rủi ro nào xuất hiện?

*Gợi ý:* Bảng không thuộc allowlist, sai schema, phân quyền tenant, lộ dữ liệu hoặc schema proliferation.

**Câu 8.** Khi dùng `inTable` với `CqlIdentifier` cần chú ý điều gì?

*Gợi ý:* Quy tắc quoted/unquoted và chữ hoa/thường của CQL identifiers.

## 17. Checklist trước khi dùng trong production

- Xác định **bảng nguồn** theo access pattern: tra cứu ID, danh sách theo khách/tháng, theo trạng thái/cửa hàng, hay loại khác.
- Đảm bảo entity `@Table` và các annotation khóa khớp schema CQL thật; không tin rằng annotation tự migration.
- Nếu bảng khác tên: sử dụng fluent `inTable` hoặc CQL `FROM` tường minh, và xác nhận schema tương thích.
- Nếu kiểu kết quả khác entity: sử dụng fluent `as` với domain type đúng; DTO/projection khớp các cột được trả.
- Chọn đúng Java type: UUID/timeuuid, timestamp/Instant, decimal/BigDecimal, UDT/collection/converter.
- Tránh `SELECT *` khi payload quá rộng; xác minh những cột thực sự được truy vấn.
- Ràng buộc partition key đầy đủ; thiết kế clustering order theo trang/list cần đọc.
- Dùng `LIMIT`, page size và paging state đúng ngữ nghĩa; không tự áp offset kiểu RDBMS.
- Tái sử dụng `CassandraTemplate`/`CqlSession` do Spring quản lý; tránh tạo session mới mỗi request.
- Không nhận tên bảng tùy ý từ bên ngoài; quản lý allowlist, quyền truy cập và version schema.
- Đo latency p95/p99, timeout, consistency, partition size, tombstone, số page và kích thước response.
- Phân biệt lỗi mapping với lỗi đồng bộ dữ liệu ở nhiều bảng; có quy trình retry, revision và đối soát read model.

## Tài liệu tham khảo

- [Spring Data Cassandra — Persisting Entities / CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): thao tác `select`, fluent template, `inTable`, `as`, projection và ánh xạ row.
- [Spring Data Cassandra — CassandraOperations API](https://docs.spring.io/spring-data/cassandra/reference/api/java/org/springframework/data/cassandra/core/CassandraOperations.html): chữ ký các overload select/selectOne/slice và `getTableName`.
- [Spring Data Cassandra — ExecutableSelectOperation API](https://docs.spring.io/spring-data/cassandra/reference/api/java/org/springframework/data/cassandra/core/ExecutableSelectOperation.html): contract chọn domain type, table và result type.
- [Spring Data Cassandra — Projections](https://docs.spring.io/spring-data/cassandra/reference/repositories/projections.html): interface projection, DTO, constructors và cơ chế tối ưu cột.
- [Apache Cassandra — CQL Reference](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/index.html): cấu trúc primary key, giới hạn WHERE/ORDER BY và truy vấn theo partition.

## Kết luận

Trong **CassandraTemplate**, **bảng đích** và **kiểu kết quả ánh xạ** là hai quyết định riêng. Đường phổ biến `select(Query, Entity.class)` sử dụng metadata entity để suy bảng và chuyển row; khi yêu cầu phức tạp hơn, fluent API `query(Domain.class).inTable("...").as(Result.class).matching(query).all()` cho phép nói rõ từng phần. CQL trực tiếp với `SELECT ... FROM ...` cũng có thể chỉ định bảng, còn `Class<T>` trong `select(statement, Class<T>)` điều khiển cách ánh xạ kết quả.

Nhưng việc chọn đúng bảng và DTO mới chỉ là điều kiện ban đầu. Cassandra vẫn yêu cầu truy vấn hợp partition key/clustering key, giới hạn page và kích thước partition, kiểm soát consistency và xử lý đồng bộ các bảng denormalized. Khi thiết kế đúng từ access pattern, dùng entity/DTO/projection phù hợp và kiểm tra CQL thực tế, bạn có thể tận dụng `CassandraTemplate` để viết đường đọc rõ ràng, hiệu quả và dễ bảo trì.
