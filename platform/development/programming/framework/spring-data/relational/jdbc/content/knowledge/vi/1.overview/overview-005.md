# So sánh JDBC thuần, Spring JDBC, Spring Data JDBC, JPA và R2DBC

Khi xây dựng ứng dụng Java sử dụng cơ sở dữ liệu quan hệ, năm cái tên **JDBC thuần**, **Spring JDBC**, **Spring Data JDBC**, **JPA** và **R2DBC** thường xuất hiện trong cùng một cuộc thảo luận. Tuy nhiên, chúng giải quyết các vấn đề ở những tầng khác nhau: có công nghệ cung cấp kết nối đến cơ sở dữ liệu, có công nghệ giảm mã lặp khi truy vấn, có công nghệ quản lý mô hình dữ liệu, và có công nghệ thay đổi cách ứng dụng thực thi I/O.

Trong hệ sinh thái **Spring Data Relational**, việc phân biệt rõ các lựa chọn này đặc biệt quan trọng. **Spring Data JDBC** hướng đến mô hình *aggregate* đơn giản, dễ dự đoán, với SQL và quan hệ dữ liệu tường minh. Nó không phải là phiên bản rút gọn của JPA; cũng không đồng nghĩa với Spring JDBC hoặc Spring Data R2DBC.

## 1. Phân biệt theo tầng công nghệ

**JDBC (Java Database Connectivity)** là API tiêu chuẩn của Java để làm việc với cơ sở dữ liệu quan hệ theo mô hình đồng bộ. Ứng dụng dùng `Connection`, `PreparedStatement`, `ResultSet` và driver JDBC để gửi SQL, nhận dữ liệu.

**Spring JDBC** là lớp tiện ích trên JDBC, nổi bật với `JdbcTemplate`, `NamedParameterJdbcTemplate` và, ở các phiên bản Spring Framework hỗ trợ, `JdbcClient`. Nó quản lý tài nguyên, chuyển đổi lỗi và đơn giản hóa thao tác thực thi SQL. Lập trình viên vẫn chủ động viết truy vấn và ánh xạ phần lớn kết quả.

**Spring Data JDBC** là mô-đun của Spring Data, sử dụng cơ sở hạ tầng JDBC/Spring JDBC để ánh xạ các đối tượng trong một *aggregate* và tự tạo SQL cho những thao tác lưu, đọc, xóa thông dụng. Nó cung cấp repository và mô hình đối tượng, nhưng **không có persistence context, lazy loading hoặc dirty checking kiểu JPA**.

**JPA (Jakarta Persistence)** là đặc tả ORM (Object–Relational Mapping), không phải một driver hoặc thư viện truy vấn cụ thể. Các nhà cung cấp triển khai như **Hibernate** quản lý entity, quan hệ, trạng thái đối tượng và câu SQL tương ứng. Trong ứng dụng Spring, người học thường gặp JPA thông qua **Spring Data JPA** với `JpaRepository`.

**R2DBC (Reactive Relational Database Connectivity)** là đặc tả truy cập cơ sở dữ liệu quan hệ theo cách *reactive*, hỗ trợ I/O không chặn ở tầng ứng dụng khi driver tương ứng triển khai đúng mô hình đó. Có thể sử dụng trực tiếp R2DBC SPI, Spring R2DBC (`DatabaseClient`), hoặc **Spring Data R2DBC** (`ReactiveCrudRepository`). R2DBC là một nhánh kết nối khác với JDBC, không phải cấp độ ORM cao hơn JPA.

~~~mermaid
flowchart TD
    A["Ứng dụng Java / Spring"] --> B["JDBC thuần"]
    A --> C["Spring JDBC"]
    A --> D["Spring Data JDBC"]
    A --> E["Spring Data JPA"]
    A --> F["Spring Data R2DBC"]
    D --> C
    E --> G["JPA provider (ví dụ Hibernate)"]
    B --> H["JDBC driver"]
    C --> H
    G --> H
    F --> I["R2DBC driver"]
    H --> DB[("Cơ sở dữ liệu quan hệ")]
    I --> DB
~~~

Sơ đồ thể hiện những thành phần phổ biến trong một ứng dụng Spring. JPA provider thường thực thi SQL qua JDBC; Spring Data JDBC sử dụng hạ tầng JDBC; Spring Data R2DBC sử dụng driver R2DBC. Một hệ quản trị như PostgreSQL có thể được truy cập qua cả JDBC và R2DBC, nhưng API và cách quản lý giao dịch khác nhau.

## 2. Bảng so sánh nhanh

| Tiêu chí | JDBC thuần | Spring JDBC | Spring Data JDBC | JPA / Spring Data JPA | R2DBC / Spring Data R2DBC |
|---|---|---|---|---|---|
| Cấp độ | API kết nối SQL | Tiện ích trên JDBC | Ánh xạ aggregate và repository | ORM theo đặc tả JPA | API kết nối reactive; có repository khi dùng Spring Data |
| Cách thực thi | Đồng bộ, chặn luồng gọi | Đồng bộ, chặn luồng gọi | Đồng bộ, chặn luồng gọi | Thông thường đồng bộ qua JDBC | Reactive, I/O không chặn khi stack hỗ trợ |
| Ai viết SQL? | Lập trình viên | Chủ yếu lập trình viên | Framework tạo SQL CRUD; SQL tùy chỉnh khi cần | ORM sinh SQL; có JPQL, Criteria, native SQL | Framework tạo CRUD; truy vấn tùy chỉnh qua SQL |
| Ánh xạ dữ liệu | Tự đọc `ResultSet` | `RowMapper`, mapper tiện ích | Ánh xạ entity/aggregate | Entity, association, persistence context | Ánh xạ entity đơn giản; quan hệ thường xử lý tường minh |
| Quản lý quan hệ | SQL JOIN và mã Java | SQL JOIN và mapper | Ranh giới aggregate, entity con, tham chiếu bằng ID | `@OneToMany`, `@ManyToOne`, cascade, fetch | Liên kết nhiều bảng qua truy vấn hoặc pipeline tường minh |
| Theo dõi thay đổi object | Không | Không | Không theo kiểu JPA | Có dirty checking đối với managed entity | Không theo kiểu JPA |
| Lazy loading quan hệ | Tự xây dựng nếu cần | Tự xây dựng nếu cần | Không có lazy loading kiểu JPA | Có, tùy mapping và provider | Không có lazy loading kiểu JPA |
| Transaction điển hình | `commit` / `rollback` thủ công | `@Transactional` với transaction manager JDBC | `@Transactional` với transaction manager JDBC | `@Transactional` với JPA transaction manager | Reactive transaction manager, Reactor context |
| Mức độ kiểm soát SQL | Rất cao | Rất cao | Cao với SQL tùy chỉnh; CRUD tự sinh | Có thể kiểm soát, nhưng cần hiểu SQL do ORM sinh | Cao với SQL tường minh |
| Chi phí học tập | SQL và quản lý tài nguyên | SQL và API Spring | SQL, repository, aggregate | ORM, vòng đời entity, fetch, cascade, session | Reactive Streams, Reactor, driver và transaction reactive |

**Lưu ý về tên gọi:** khi so sánh “JPA” với “Spring Data JDBC”, lựa chọn tương ứng trong dự án Spring thường là **Spring Data JPA + Hibernate**. Tương tự, khi nói “R2DBC” trong ứng dụng Spring, cần tách biệt **R2DBC SPI**, **Spring R2DBC** và **Spring Data R2DBC**.

## 3. Cùng một bài toán: đọc khách hàng theo ID

Giả sử hệ thống quản lý bán hàng có bảng:

~~~sql
CREATE TABLE customers (
    id   BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(150) NOT NULL
);
~~~

Cú pháp tạo ID tự động có thể thay đổi giữa các hệ quản trị cơ sở dữ liệu. Trong ví dụ, nhiệm vụ là tìm khách hàng có `id = 10`. Các đoạn mã chỉ tập trung vào API chính; phần import và cấu hình kết nối được lược bớt để dễ đối chiếu.

### 3.1. JDBC thuần: tự điều khiển vòng đời tài nguyên

~~~java
record CustomerRow(Long id, String name) {}

Optional<CustomerRow> findById(DataSource dataSource, long id)
        throws SQLException {
    String sql = "SELECT id, name FROM customers WHERE id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setLong(1, id); // Tham số hóa, không nối ID vào SQL

        try (ResultSet rs = statement.executeQuery()) {
            if (rs.next()) {
                return Optional.of(
                    new CustomerRow(rs.getLong("id"), rs.getString("name"))
                );
            }
            return Optional.empty();
        }
    }
}
~~~

Ở đây, người viết chịu trách nhiệm chuẩn bị SQL, gắn tham số, lấy kết nối, đóng tài nguyên, đọc từng cột và xử lý `SQLException`. `try-with-resources` giúp đóng kết nối, statement và result set ngay cả khi có lỗi. Mức kiểm soát cao, nhưng việc lặp lại mẫu mã này trên hàng chục repository dễ làm ứng dụng cồng kềnh.

### 3.2. Spring JDBC: vẫn viết SQL, ít mã phụ trợ hơn

~~~java
record CustomerRow(Long id, String name) {}

@Repository
class CustomerJdbcDao {
    private final JdbcTemplate jdbcTemplate;

    CustomerJdbcDao(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    Optional<CustomerRow> findById(long id) {
        return jdbcTemplate.query(
            "SELECT id, name FROM customers WHERE id = ?",
            (rs, rowNum) ->
                new CustomerRow(rs.getLong("id"), rs.getString("name")),
            id
        ).stream().findFirst();
    }
}
~~~

`JdbcTemplate` mượn và trả kết nối phù hợp với cơ chế transaction, quản lý statement/result set, thực thi SQL và chuyển nhiều `SQLException` thành hệ ngoại lệ `DataAccessException` của Spring. SQL vẫn rõ ràng và việc ánh xạ vẫn do người viết quy định. Với truy vấn nhiều tham số có tên, `NamedParameterJdbcTemplate` thường dễ đọc hơn dấu `?` theo vị trí.

### 3.3. Spring Data JDBC: repository và aggregate

~~~java
@Table("customers")
record CustomerJdbc(@Id Long id, String name) {}

interface CustomerRepository extends CrudRepository<CustomerJdbc, Long> {
}

// Trong một Spring service:
Optional<CustomerJdbc> result = customerRepository.findById(10L);
CustomerJdbc created =
    customerRepository.save(new CustomerJdbc(null, "Lan"));
~~~

Spring Data JDBC ánh xạ hàng dữ liệu thành `CustomerJdbc` và tạo SQL cần thiết cho những thao tác repository phổ biến. `@Id` đánh dấu khóa chính; `null` ở ví dụ này biểu thị một đối tượng mới dùng ID do cơ sở dữ liệu sinh. Vì record là immutable, cần sử dụng giá trị **trả về từ `save`** để nhận đối tượng chứa ID đã được cập nhật.

Lợi ích nổi bật không phải chỉ là giảm dòng mã: repository thao tác trên một **aggregate root** với quy tắc sở hữu entity con rõ ràng. Khi cần truy vấn đặc thù, vẫn có thể viết `@Query` hoặc sử dụng Spring JDBC bên cạnh repository.

### 3.4. JPA / Spring Data JPA: entity được ORM quản lý

~~~java
@Entity
@Table(name = "customers")
class CustomerJpa {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected CustomerJpa() {} // JPA cần constructor không tham số

    CustomerJpa(String name) {
        this.name = name;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}

interface CustomerJpaRepository extends JpaRepository<CustomerJpa, Long> {
}

// Ví dụ trong một service có transaction:
CustomerJpa customer = customerJpaRepository.findById(10L)
    .orElseThrow();
customer.setName("Lan cập nhật");
// Managed entity có thể được ghi xuống DB qua dirty checking khi flush.
~~~

Với JPA, entity đang được quản lý trong *persistence context* có thể được theo dõi thay đổi. Tại thời điểm `flush`, provider quyết định câu `UPDATE` phù hợp; không nhất thiết phải gọi `save` sau mỗi setter trên một managed entity. Điều này rất thuận tiện cho domain model có quan hệ phong phú, nhưng đòi hỏi hiểu entity ở trạng thái managed hay detached, thời điểm flush và tác dụng của fetch/cascade.

### 3.5. Spring Data R2DBC: repository trả về publisher

~~~java
@Table("customers")
record CustomerReactive(@Id Long id, String name) {}

interface CustomerReactiveRepository
        extends ReactiveCrudRepository<CustomerReactive, Long> {
}

Mono<CustomerReactive> result =
    customerReactiveRepository.findById(10L);

Mono<CustomerReactive> created =
    customerReactiveRepository.save(new CustomerReactive(null, "Lan"));
~~~

`Mono<CustomerReactive>` biểu diễn một kết quả bất đồng bộ có thể có 0 hoặc 1 phần tử; `Flux<CustomerReactive>` biểu diễn nhiều phần tử. Việc xây dựng publisher thường **chưa thực thi truy vấn**; thao tác được kích hoạt khi có subscription. Trong web application dùng Spring WebFlux, framework thường đảm nhiệm subscription và truyền kết quả đến client.

Không nên gọi `block()` để biến mọi `Mono` thành kết quả đồng bộ, đặc biệt trên luồng xử lý sự kiện của WebFlux: cách này làm mất lợi ích bất đồng bộ và có thể làm nghẽn luồng. Khi cần phối hợp nhiều truy vấn, sử dụng các toán tử như `flatMap`, `map` và `zip` phù hợp với phụ thuộc dữ liệu.

## 4. Khác biệt cốt lõi: mô hình dữ liệu và vòng đời đối tượng

### 4.1. JDBC thuần và Spring JDBC: truy vấn là trung tâm

Với hai lựa chọn này, lập trình viên quyết định chính xác dữ liệu được truy xuất và cách biểu diễn kết quả. Một câu SQL có thể kết hợp nhiều bảng, trả về DTO chuyên cho màn hình, báo cáo hoặc API:

~~~sql
SELECT o.id, o.created_at, c.name AS customer_name
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.id = ?;
~~~

Mô hình này đặc biệt phù hợp cho báo cáo, dữ liệu đọc phức tạp hoặc ứng dụng mà SQL là giao diện chính với database. Đổi lại, việc cập nhật toàn bộ một cấu trúc đối tượng như đơn hàng kèm nhiều dòng hàng cần do ứng dụng tổ chức.

### 4.2. Spring Data JDBC: aggregate là ranh giới nhất quán

Giả sử một đơn hàng chứa nhiều dòng hàng và tham chiếu đến khách hàng:

~~~text
Order (aggregate root)
├── id, customerId, status
├── OrderLine #1 (productId, quantity, unitPrice)
└── OrderLine #2 (productId, quantity, unitPrice)

Customer (aggregate root khác)
└── id, name
~~~

Trong Spring Data JDBC:

- `Order` là *aggregate root*, chịu trách nhiệm cho các bất biến nghiệp vụ của các `OrderLine` thuộc nó.
- `OrderLine` là entity con thuộc vòng đời của `Order`; có thể ánh xạ quan hệ sở hữu bằng `@MappedCollection`.
- `Customer` là một aggregate khác. `Order` thường chỉ lưu `customerId` hoặc dùng `AggregateReference<Customer, Long>`, thay vì gắn nguyên entity `Customer` vào đồ thị sở hữu.
- Repository thường được thiết kế quanh **aggregate root**, không quanh mọi entity con. Các thay đổi trong aggregate được lưu trong transaction phù hợp.

Ví dụ mô hình khái niệm:

~~~java
@Table("orders")
class Order {
    @Id Long id;
    Long customerId; // Tham chiếu tới aggregate Customer qua ID

    @MappedCollection(idColumn = "order_id")
    Set<OrderLine> lines;
}

@Table("order_lines")
class OrderLine {
    Long productId;
    int quantity;
}
~~~

Ví dụ này minh họa **quan hệ sở hữu**; schema thực tế còn phải phù hợp với cột khóa ngoại, khóa chính và cách sinh ID của từng bảng. Với entity con có ID riêng, có thể cần khai báo thêm `@Id` và chiến lược lưu phù hợp.

Spring Data JDBC không có persistence context theo dõi từng object thay đổi. Khi gọi `save(order)`, framework thực hiện các thao tác SQL để lưu trạng thái aggregate. **Tùy cách ánh xạ và thao tác, quá trình cập nhật các collection con có thể bao gồm xóa rồi chèn lại các hàng con**, thay vì cập nhật đúng từng thuộc tính đã thay đổi như dirty checking của JPA. Điều này khiến việc xác định ranh giới aggregate, kích thước collection và chi phí ghi rất quan trọng.

Một hệ quả tích cực: truy xuất aggregate không âm thầm kích hoạt lazy loading JPA khi đọc thuộc tính sau này. Những truy vấn ngoài ranh giới aggregate nên được thực hiện rõ ràng, chẳng hạn bằng repository/query chuyên cho màn hình.

### 4.3. JPA: object graph, association và persistence context

JPA cho phép biểu diễn các quan hệ như `@OneToMany`, `@ManyToOne`, `@OneToOne` và `@ManyToMany` với lựa chọn fetch, cascade và cách quản lý entity. Điều này thuận tiện khi nhiều thao tác nghiệp vụ đi qua quan hệ đối tượng.

Đổi lại, cần hiểu một số cơ chế:

**Persistence context:** lưu và quản lý các entity đã tải trong phạm vi làm việc; với cùng một khóa định danh, thường duy trì một managed instance trong context.

**Dirty checking:** khi flush, provider kiểm tra thay đổi của managed entity để quyết định lệnh ghi.

**Lazy loading:** có thể trì hoãn truy vấn quan hệ đến lúc truy cập. Nếu truy cập ngoài context còn hoạt động, có thể gặp lỗi hoặc không tải được dữ liệu.

**N+1 query:** khi lấy N entity rồi truy cập quan hệ của từng entity, ứng dụng có thể tạo ra nhiều truy vấn hơn dự kiến. Cần chọn fetch join, entity graph, projection hoặc batch fetch theo tình huống.

Vì vậy, năng lực ORM mạnh hơn không mặc nhiên dẫn đến mã đơn giản hơn về vận hành. Phải quan sát SQL thực tế và hiểu thời điểm đọc/ghi.

### 4.4. Spring Data R2DBC: ánh xạ nhẹ, luồng xử lý reactive

Spring Data R2DBC ánh xạ các hàng SQL sang object và cung cấp repository, nhưng không cung cấp cơ chế ORM đầy đủ của JPA. Các quan hệ giữa nhiều bảng thường được xử lý qua truy vấn riêng, JOIN có mapper phù hợp hoặc kết hợp các publisher. Không nên giả định mọi annotation quản lý aggregate/collection của Spring Data JDBC sẽ có cùng hành vi trong R2DBC.

Khi thiết kế reactive, câu hỏi quan trọng không chỉ là “lấy hàng nào?” mà còn là “các phép đọc/ghi phụ thuộc nhau được nối thành một pipeline ra sao?”. Ví dụ, cần dùng `flatMap` để thực thi một truy vấn sau khi truy vấn trước trả kết quả; chỉ tạo hai `Mono` riêng rồi bỏ qua publisher thứ hai sẽ không thực hiện bước đó.

## 5. Giao dịch (transaction) khác nhau thế nào?

Tất cả các công nghệ trên đều có thể tham gia giao dịch database, nhưng cách quản lý context và connection khác nhau.

| Lựa chọn | Quản lý giao dịch thường gặp | Điểm cần ghi nhớ |
|---|---|---|
| JDBC thuần | `Connection#setAutoCommit(false)`, `commit()`, `rollback()` | Tất cả câu lệnh cần cùng connection; phải xử lý lỗi/đóng connection |
| Spring JDBC | `@Transactional` + `JdbcTransactionManager` hoặc `DataSourceTransactionManager` | Các thao tác JDBC tham gia transaction gắn với luồng theo cơ chế Spring |
| Spring Data JDBC | Như Spring JDBC | `save`/`delete` của aggregate cần ranh giới transaction đúng theo nghiệp vụ |
| JPA | `@Transactional` + `JpaTransactionManager` | Persistence context, flush và transaction liên quan chặt chẽ nhưng không đồng nhất |
| Spring Data R2DBC | `R2dbcTransactionManager`, `@Transactional` với publisher reactive hoặc `TransactionalOperator` | Transaction được truyền qua reactive context, không dựa vào ThreadLocal theo cách JDBC truyền thống |

Ví dụ một thao tác cần ghi đơn hàng rồi trừ tồn kho bằng Spring JDBC:

~~~java
@Service
class CheckoutService {
    private final JdbcTemplate jdbc;

    CheckoutService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void checkout(long orderId, long productId, int quantity) {
        int updated = jdbc.update(
            """
            UPDATE inventory
            SET stock = stock - ?
            WHERE product_id = ? AND stock >= ?
            """,
            quantity, productId, quantity
        );
        if (updated != 1) {
            throw new IllegalStateException("Không đủ hàng");
        }
        jdbc.update(
            "UPDATE orders SET status = ? WHERE id = ?",
            "CONFIRMED", orderId
        );
    }
}
~~~

Nếu hai câu lệnh dùng cùng transaction do Spring quản lý, exception kiểu runtime ném ra sẽ mặc định khiến transaction rollback. Ví dụ giả định bảng và ràng buộc dữ liệu đã được chuẩn bị; trong hệ thống thật phải kiểm tra cả số hàng bị cập nhật, tính idempotent và các quy tắc đồng thời.

Với R2DBC, cùng một ý tưởng có thể biểu diễn bằng `TransactionalOperator`:

~~~java
Mono<Void> checkout =
    updateInventory(productId, quantity)
        .then(confirmOrder(orderId))
        .as(transactionalOperator::transactional);
~~~

Trong đó `updateInventory` và `confirmOrder` được giả định trả về publisher reactive và báo lỗi khi không thể thực hiện nghiệp vụ. Ranh giới transaction bao quanh **chuỗi reactive được subscribe**. Hai API JDBC và R2DBC không tự động chia sẻ cùng một transaction local chỉ vì cùng được đánh dấu `@Transactional`; việc phối hợp chúng đòi hỏi thiết kế riêng.

## 6. SQL, hiệu năng và khả năng dự đoán

Không có công nghệ nào luôn nhanh nhất. Hiệu năng phụ thuộc vào số round-trip tới database, index, truy vấn, transaction, connection pool, độ lớn aggregate/object graph và mức độ đồng thời.

### Kiểm soát câu SQL

- **JDBC thuần / Spring JDBC:** SQL do lập trình viên viết là nguồn hành vi chính. Rất thích hợp khi cần JOIN, CTE, window function, truy vấn báo cáo hoặc câu lệnh tối ưu riêng cho hệ quản trị.
- **Spring Data JDBC:** CRUD thông thường được sinh theo mapping; có thể bổ sung SQL tùy chỉnh. Thường dễ dự đoán hơn một object graph ORM có lazy association, nhưng vẫn cần xem số lệnh SQL khi nạp và lưu aggregate lớn.
- **JPA:** ORM có thể tiết kiệm nhiều công sức cho domain model giàu quan hệ; đồng thời phát sinh câu SQL không hiển nhiên do flush, cascade, fetch và N+1. Có thể dùng projection, JPQL, native SQL và xem SQL log để kiểm soát.
- **R2DBC:** cho phép truy vấn SQL và pipeline reactive, nhưng không tự làm truy vấn kém hiệu quả trở nên nhanh. Driver, database và thiết kế pipeline quyết định hiệu quả thực tế.

### Blocking và non-blocking

JDBC, Spring JDBC, Spring Data JDBC và hầu hết triển khai JPA phổ biến là **blocking tại điểm gọi database**. Khi chờ database phản hồi, luồng đang thực thi thao tác thường bị giữ lại. Connection pool như HikariCP hỗ trợ tái sử dụng connection, nhưng không biến lệnh JDBC thành I/O không chặn.

R2DBC cho phép ứng dụng biểu diễn việc chờ I/O bằng publisher và tiếp tục xử lý các công việc khác trên số lượng luồng hạn chế. Điều này có thể hữu ích ở tải có nhiều yêu cầu đồng thời hoặc ứng dụng đã dùng Spring WebFlux end-to-end. Dù vậy:

1. Database vẫn có giới hạn về CPU, khóa, số kết nối và thông lượng.
2. Driver và những tác vụ trong pipeline cần thực sự phù hợp với non-blocking; nhét JDBC hay xử lý chặn lâu vào event-loop sẽ phá vỡ giả định đó.
3. Reactive bổ sung độ phức tạp về luồng dữ liệu, context, lỗi, backpressure và debug.

Với một ứng dụng MVC truyền thống có số lượng request vừa phải, Spring JDBC hoặc Spring Data JDBC thường là lựa chọn hoàn toàn hợp lý. Việc chuyển toàn bộ hệ thống sang reactive chỉ để tăng tốc một truy vấn đơn giản hiếm khi giải quyết nguyên nhân gốc như thiếu index hoặc N+1.

## 7. Khi nào nên chọn công nghệ nào?

| Bối cảnh | Lựa chọn thường phù hợp | Vì sao |
|---|---|---|
| Công cụ nhỏ, cần hiểu trực tiếp JDBC hoặc kiểm soát driver | JDBC thuần | Thấy đầy đủ connection, statement, result set và transaction |
| API truy vấn SQL tùy chỉnh, báo cáo, JOIN phức tạp | Spring JDBC | SQL làm trung tâm, bớt mã quản lý tài nguyên |
| Dịch vụ nghiệp vụ theo aggregate, mô hình vừa phải, muốn tránh ORM phức tạp | Spring Data JDBC | Repository gọn, quy tắc ownership rõ, không có lazy loading JPA |
| Domain có nhiều quan hệ đối tượng, cần cascade/fetch, thay đổi entity được theo dõi | JPA / Spring Data JPA | Nhiều công cụ ORM, persistence context và mapping quan hệ |
| Ứng dụng reactive end-to-end, driver có R2DBC phù hợp, nhiều I/O đồng thời | Spring Data R2DBC / Spring R2DBC | Kết nối và xử lý truy vấn theo mô hình reactive |
| Cùng hệ thống có các query báo cáo và thao tác ghi aggregate | Kết hợp Spring Data JDBC với Spring JDBC | Repository quản lý aggregate, SQL riêng phục vụ các màn hình đọc |

Đây là điểm khởi đầu để ra quyết định, không phải quy tắc bất biến. Một ứng dụng JPA vẫn có thể dùng native SQL cho báo cáo. Một dịch vụ Spring Data JDBC có thể dùng `JdbcTemplate` cho câu truy vấn không phù hợp với repository. Cũng có thể dùng JPA trong ứng dụng có domain đơn giản, miễn là đội ngũ hiểu và kiểm soát được cơ chế ORM.

### Ba tình huống minh họa

**Tình huống A – Quản lý đơn hàng:** `Order` kiểm soát trạng thái và danh sách `OrderLine`, còn `Customer` và `Product` có vòng đời riêng. Spring Data JDBC là ứng viên tốt nếu aggregate đủ gọn và cập nhật con không quá tốn kém. Các trang thống kê doanh thu có thể dùng Spring JDBC với SQL chuyên biệt.

**Tình huống B – Hệ thống hồ sơ học viên:** nhiều entity liên kết và nghiệp vụ thao tác qua object graph, cần cascade hay truy cập association theo use case. JPA có thể tiện hơn, miễn là thiết kế fetch và transaction cẩn thận để tránh N+1.

**Tình huống C – Gateway/API reactive:** hệ thống đã dùng WebFlux, gọi nhiều nguồn I/O không chặn và database có driver R2DBC đáng tin cậy. Spring Data R2DBC có thể giữ luồng reactive xuyên suốt. Nếu nghiệp vụ cần ORM JPA phong phú, phải cân nhắc đánh đổi thay vì mặc định chuyển JPA sang R2DBC.

## 8. Những nhầm lẫn phổ biến

**“Spring Data JDBC = Spring JDBC cộng vài repository?”** Không đầy đủ. Spring Data JDBC đưa vào khái niệm aggregate root, mapping và cơ chế lưu toàn bộ aggregate. Spring JDBC tập trung vào thực thi SQL; hai công nghệ bổ sung cho nhau nhưng khác mức trừu tượng.

**“Spring Data JDBC giống Spring Data JPA nhưng nhẹ hơn?”** Không. JPA dùng persistence context, managed entity, dirty checking và association mapping; Spring Data JDBC coi aggregate là đơn vị lưu, không vận hành object graph như ORM. Chuyển giữa chúng có thể đòi hỏi thiết kế lại model.

**“Spring Data JDBC không hỗ trợ JOIN?”** Có thể dùng SQL JOIN cho truy vấn tùy chỉnh, đặc biệt với kết quả DTO/read model. Điều không nên mặc định là repository sẽ biến mọi quan hệ JOIN thành đồ thị entity với lazy loading và cascade như JPA.

**“Dùng repository thì không cần biết SQL?”** Sai với cả Spring Data JDBC, JPA lẫn R2DBC. Index, transaction, khóa, isolation và SQL thực tế vẫn quyết định tính đúng đắn, hiệu năng.

**“JPA luôn dùng Hibernate?”** Hibernate là provider rất phổ biến trong Spring Boot, nhưng JPA là đặc tả và còn có provider khác. `JpaRepository` là API của Spring Data JPA, không thuộc bản thân đặc tả Jakarta Persistence.

**“R2DBC luôn nhanh hơn JDBC?”** Không. R2DBC giải quyết mô hình lập trình I/O và quản lý tài nguyên khi tải đồng thời, không bảo đảm latency của từng SQL thấp hơn. Nếu database là nút thắt, đổi API kết nối có thể không tăng thông lượng.

**“Dùng WebFlux bắt buộc dùng R2DBC?”** Không tuyệt đối, nhưng gọi JDBC chặn trực tiếp trên event-loop là vấn đề. Có thể cô lập tác vụ blocking lên scheduler thích hợp trong một số hệ thống, song điều đó không biến JDBC thành reactive và có giới hạn riêng. Khi cần stack database non-blocking xuyên suốt, R2DBC phù hợp hơn.

## 9. Gợi ý lộ trình học trong Spring Data Relational

Để hiểu Spring Data JDBC một cách bền vững, nên học theo thứ tự khái niệm:

1. **SQL và JDBC cơ bản:** hiểu connection, parameter binding, transaction, index, JOIN, khóa chính/ngoại.
2. **Spring JDBC:** thực hiện query/update bằng `JdbcTemplate`; phân biệt SQL, mapper và ranh giới transaction.
3. **Spring Data JDBC:** thiết kế aggregate root, entity con, `@Table`, `@Id`, `@MappedCollection`, `@Version`, repository và query tùy chỉnh; quan sát SQL khi `save`.
4. **So sánh với JPA:** thử cùng một quan hệ `Order–OrderLine` để nhận ra điểm khác giữa lưu aggregate và persistence context; phân tích fetch, dirty checking, cascade.
5. **Tiếp cận R2DBC khi có nhu cầu reactive:** hiểu `Mono`, `Flux`, subscription, transaction context và tác dụng của blocking code trong pipeline.

Đặc biệt với **Spring Data Relational JDBC**, câu hỏi thiết kế quan trọng thường là: *“Dữ liệu nào phải được thay đổi nhất quán cùng nhau trong một aggregate, và dữ liệu nào nên được tham chiếu bằng ID hoặc đọc qua truy vấn riêng?”* Trả lời được câu hỏi đó giúp chọn ranh giới repository và tránh đưa một mạng lưới entity quá lớn vào một thao tác `save`.

## 10. Kết luận

JDBC thuần cho quyền điều khiển trực tiếp với SQL và tài nguyên; Spring JDBC giữ cách tiếp cận SQL nhưng giảm mã lặp; Spring Data JDBC thêm repository và mô hình aggregate rõ ràng; JPA bổ sung sức mạnh ORM cùng các cơ chế vòng đời entity phức tạp; còn R2DBC thay đổi mô hình kết nối và thực thi sang reactive. Chọn công nghệ dựa vào **mô hình nghiệp vụ, nhu cầu SQL, transaction, phong cách ứng dụng và tải thực tế** sẽ có giá trị hơn việc chọn theo số lượng annotation hoặc giả định công nghệ mới hơn luôn tốt hơn.
