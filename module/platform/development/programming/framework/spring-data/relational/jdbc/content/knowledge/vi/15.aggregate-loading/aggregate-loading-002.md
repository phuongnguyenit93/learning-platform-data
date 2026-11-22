# Số lượt truy vấn khi đọc một aggregate hoặc một danh sách

Khi gọi repository trong Spring Data JDBC, ứng dụng thường muốn nhận được **aggregate đầy đủ**: root cùng các entity mà root sở hữu. Vì Spring Data JDBC không dùng lazy proxy như JPA/Hibernate, các phần được ánh xạ của aggregate được tải trong quá trình đọc repository. Cách tải này ảnh hưởng trực tiếp đến số câu SQL được thực thi.

Có hai chiến lược cần phân biệt:

- **Tải truyền thống:** truy vấn root trước, sau đó thực hiện các câu SQL riêng để tải những entity được tham chiếu. Khi đọc danh sách nhiều root có collection, cách này có thể tạo ra mẫu N+1.
- **Single Query Loading:** từ Spring Data JDBC 3.2, có thể tải nhiều aggregate đầy đủ bằng một câu SELECT nếu mô hình và phương thức truy vấn đáp ứng các điều kiện hỗ trợ.

Số câu SQL không chỉ phụ thuộc vào số bản ghi trả về. Nó còn phụ thuộc vào cấu trúc aggregate, số collection, độ sâu lồng nhau, loại repository method, pagination và chiến lược tải đang bật.

Bài học dùng ví dụ đơn hàng có nhiều dòng hàng và ghi chú:

~~~text
PurchaseOrder (aggregate root)
    |
    +-- OrderLine (0..n)
    |
    +-- OrderNote (0..n)
~~~

Mục tiêu là hiểu cách ước lượng số truy vấn, nhận diện N+1, biết khi nào Single Query Loading có thể giảm số lần round-trip và biết cách đo bằng SQL log.

## 1. Một lời gọi repository có thể tạo nhiều câu SQL

Xét aggregate đơn giản:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private String status;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

Mỗi `OrderLine` được lưu ở bảng riêng và có khóa ngoại `order_id` trỏ về `purchase_orders.id`.

Repository:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Khi gọi:

~~~java
PurchaseOrder order = repository.findById(100L).orElseThrow();
~~~

Kết quả mong đợi là một `PurchaseOrder` có cả danh sách `lines`. Ở chiến lược tải truyền thống, Spring Data JDBC thực hiện truy vấn lấy root, rồi truy vấn riêng để lấy collection:

~~~sql
-- Truy vấn 1: aggregate root
SELECT *
FROM purchase_orders
WHERE id = :id;

-- Truy vấn 2: entity con
SELECT *
FROM order_lines
WHERE order_id = :id;
~~~

Với một aggregate có một collection, ví dụ này thường cần **2 câu SELECT**. Nếu root còn có thêm một collection khác, collection đó cũng cần được tải bằng statement riêng trong chiến lược truyền thống.

Điểm quan trọng: cả hai câu SQL xảy ra trong quá trình thực thi `findById(...)`. Gọi getter `order.getLines()` sau đó chỉ đọc collection đã được materialize; getter không phát sinh một truy vấn lazy mới.

## 2. Đếm truy vấn khi đọc một aggregate

Với một root duy nhất, có thể ước lượng theo cấu trúc:

| Cấu trúc aggregate | Tải truyền thống, minh họa |
|---|---:|
| Chỉ có root, không có entity tham chiếu | 1 SELECT |
| Root có một collection | 1 SELECT root + 1 SELECT collection |
| Root có hai collection độc lập | 1 SELECT root + 2 SELECT collection |
| Root có collection lồng trong child | Root + SELECT child + SELECT collection của child |
| Root có nhiều tầng collection | Thêm statement cho các quan hệ collection ở các tầng |

Ví dụ:

~~~text
PurchaseOrder
    |
    +-- List<OrderLine>
    |
    +-- List<OrderNote>
~~~

Trong chế độ truyền thống:

~~~text
1. SELECT purchase_orders
2. SELECT order_lines
3. SELECT order_notes

Tổng minh họa: 3 câu SELECT
~~~

Nếu có quan hệ lồng nhau:

~~~text
PurchaseOrder
    |
    +-- List<Shipment>
             |
             +-- List<Parcel>
~~~

Một aggregate đơn lẻ có thể cần:

~~~text
1. SELECT purchase_orders
2. SELECT shipments
3. SELECT parcels

Tổng minh họa: 3 câu SELECT
~~~

Đây là cách đếm theo các bước tải quan hệ. Cấu trúc mapping cụ thể, loại quan hệ và phiên bản Spring Data JDBC có thể ảnh hưởng đến SQL thực tế; vì vậy số trong bảng là mô hình để suy luận, không phải cam kết cố định cho mọi mapping.

### 2.1. Không phải số dòng trả về là số truy vấn

Một đơn có 100 dòng hàng vẫn có thể được tải bằng một câu SELECT cho root và một câu SELECT cho collection trong trường hợp chỉ đọc một aggregate theo chiến lược truyền thống.

~~~text
PurchaseOrder #100
    100 OrderLine

SQL:
    1 SELECT purchase_orders
    1 SELECT order_lines WHERE order_id = 100
~~~

Database trả về 100 hàng con trong ResultSet thứ hai. Đó là **100 dòng kết quả**, không phải 100 câu truy vấn.

Phân biệt:

- Query count: số statement SQL được thực thi.
- Result row count: số hàng database trả về.
- Network round-trip: số lần giao tiếp thực tế giữa ứng dụng và database, có thể phụ thuộc driver, batching và cách thực thi.
- Processing time: thời gian database chạy SQL, truyền dữ liệu và Spring dựng object graph.

Giảm query count thường giúp giảm round-trip, nhưng không tự động bảo đảm truy vấn nhanh hơn nếu câu SQL mới trả về quá nhiều dữ liệu hoặc có kế hoạch thực thi kém.

## 3. Đọc danh sách nhiều aggregate và vấn đề N+1

Vấn đề thể hiện rõ khi đọc nhiều root cùng lúc.

Giả sử repository có 100 đơn hàng, mỗi đơn có một collection `lines`. Ở chiến lược tải truyền thống, Spring Data JDBC tải root list trước, rồi tải các entity được tham chiếu cho từng root bằng statement riêng.

~~~text
N = 100 PurchaseOrder

1. SELECT * FROM purchase_orders

2. SELECT * FROM order_lines WHERE order_id = 1
3. SELECT * FROM order_lines WHERE order_id = 2
4. SELECT * FROM order_lines WHERE order_id = 3
...
101. SELECT * FROM order_lines WHERE order_id = 100
~~~

Tổng cộng:

\[
Q = 1 + N
\]

Với 100 đơn hàng và một collection cần tải cho mỗi đơn:

\[
Q = 1 + 100 = 101
\]

Đây là mẫu **N+1 query**:

- 1 query lấy danh sách root.
- N query tiếp theo tải collection cho N root.

Nếu mỗi root có hai collection độc lập, ví dụ `lines` và `notes`, mô hình có thể thành:

\[
Q = 1 + 2N
\]

Với 100 root:

\[
Q = 1 + 2 \times 100 = 201
\]

Nếu có collection lồng nhau, số statement có thể tăng tiếp theo số đối tượng cha ở từng tầng.

### 3.1. Ví dụ có hai tầng collection

~~~text
PurchaseOrder
    |
    +-- Shipment
            |
            +-- Parcel
~~~

Giả sử có 100 đơn hàng, mỗi đơn có 2 shipment và mỗi shipment có collection parcel.

Theo cách tải truyền thống, mô hình truy vấn minh họa:

- 1 SELECT để lấy 100 đơn hàng.
- 100 SELECT để lấy shipment của từng đơn.
- 200 SELECT để lấy parcel của từng shipment.

Tổng:

\[
Q = 1 + 100 + 200 = 301
\]

Con số phụ thuộc số đối tượng cha thực tế ở từng tầng, không chỉ phụ thuộc số root. Nếu một đơn không có shipment thì không có collection parcel nào bên dưới đơn đó cần tải.

### 3.2. Vì sao gọi một lần findAll vẫn có thể tạo N+1?

Tên phương thức `findAll()` chỉ cho biết ứng dụng gọi một thao tác repository. Nó không có nghĩa database chỉ nhận một câu SQL trong mọi chiến lược tải.

Spring Data JDBC cần dựng đầy đủ aggregate. Ở cách tải truyền thống, mỗi root được đọc, sau đó các entity tham chiếu được tải bằng các statement riêng. Khi có N root và collection, các statement tải collection có thể lặp lại theo từng root.

Đây là lý do cần quan sát SQL thực tế thay vì đếm số lần gọi Java method.

## 4. So sánh đọc một root và đọc một danh sách

Cùng một aggregate có thể có query count khác nhau tùy số root cần tải:

| Thao tác | Root được tải | Một collection ở mỗi root, chiến lược truyền thống |
|---|---:|---:|
| `findById(100L)` | 1 | 2 SELECT |
| `findAllById(ids)` với 10 ID | 10 | 1 + 10 = 11 SELECT |
| `findAll()` trả 100 root | 100 | 1 + 100 = 101 SELECT |
| `findAll()` trả 1.000 root | 1.000 | 1 + 1.000 = 1.001 SELECT |

Đây là mô hình N+1 được mô tả cho aggregate có một collection. Nếu mỗi root có nhiều collection hoặc nhiều tầng, số statement tăng theo các quan hệ cần tải.

Một hệ quả thực tế: truy vấn một aggregate theo ID có thể nhanh, nhưng cùng thiết kế đó khi dùng `findAll()` cho hàng trăm aggregate lại tạo nhiều round-trip.

Không nên chỉ benchmark `findById()` rồi kết luận màn hình danh sách cũng có hiệu năng tương tự.

## 5. Single Query Loading giải quyết vấn đề như thế nào?

Spring Data JDBC 3.2 giới thiệu **Single Query Loading**. Với aggregate và phương thức truy vấn đủ điều kiện, Spring Data JDBC có thể tải nhiều aggregate hoàn chỉnh bằng một câu SELECT.

~~~text
Tải truyền thống:

SELECT roots
    |
    +-- SELECT children cho root 1
    +-- SELECT children cho root 2
    +-- SELECT children cho root 3
    +-- ...
    +-- SELECT children cho root N

Single Query Loading:

SELECT roots + các collection trong cùng một SQL
    |
    v
Dựng nhiều aggregate từ ResultSet
~~~

Với 100 đơn hàng có một collection:

| Chiến lược | Query count minh họa |
|---|---:|
| Tải truyền thống | 101 |
| Single Query Loading đủ điều kiện | 1 |

Single Query Loading dùng các window function như `row_number()` và `count()` để biểu diễn các phần tử collection trong một ResultSet, đồng thời tránh nhân bản toàn bộ dữ liệu root theo tích Descartes của nhiều collection.

Nó không đơn giản là join tất cả các bảng rồi chấp nhận một ResultSet phình to. SQL được tạo có cấu trúc để ghép các phần tử collection theo vị trí của chúng.

### 5.1. Vì sao không join collection một cách ngây thơ?

Giả sử một đơn có:

- 5 dòng hàng.
- 4 ghi chú.
- 3 khoản phí.

Join trực tiếp cả ba collection có thể tạo ra:

\[
5 \times 4 \times 3 = 60
\]

hàng kết quả cho một đơn, dù aggregate thực tế chỉ có 12 phần tử con.

Đó là hiện tượng **Cartesian multiplication**: các collection độc lập nhân số hàng với nhau và lặp dữ liệu root cũng như dữ liệu của collection khác.

Single Query Loading sử dụng window functions và cách ghép theo số thứ tự để tránh cách nhân bản dữ liệu ngây thơ này.

## 6. Điều kiện và giới hạn của Single Query Loading

Single Query Loading không tự động áp dụng cho mọi aggregate và mọi repository method.

Theo tài liệu Spring Data Relational hiện hành, các điều kiện chính gồm:

1. Aggregate không có nested collections, bao gồm cả `Map`.
2. Aggregate không dùng `AggregateReference` hoặc embedded entities.
3. Database dialect phải hỗ trợ. Trong các dialect được Spring Data JDBC cung cấp, H2 và HSQL không được hỗ trợ cho chiến lược này; các dialect còn lại được hỗ trợ.
4. Chiến lược áp dụng cho các phương thức find của `CrudRepository`; derived query và annotated `@Query` không được áp dụng.
5. Phải bật cờ Single Query Loading trên `JdbcMappingContext`.

Nếu một điều kiện không đáp ứng, Spring Data JDBC quay lại chiến lược tải mặc định.

**Lưu ý về phiên bản:** Single Query Loading được giới thiệu từ Spring Data JDBC 3.2 và tài liệu hiện hành vẫn mô tả đây là tính năng experimental. Hãy kiểm tra tài liệu đúng phiên bản Spring Data JDBC mà ứng dụng đang dùng trước khi dựa vào nó trong thiết kế hiệu năng.

### 6.1. Nhiều collection trực tiếp và collection lồng nhau

Ví dụ aggregate có hai collection trực tiếp:

~~~java
class PurchaseOrder {

    @Id
    Long id;

    List<OrderLine> lines;
    List<OrderNote> notes;
}
~~~

Cấu trúc này có thể phù hợp với Single Query Loading nếu đáp ứng các điều kiện còn lại.

Nhưng aggregate có collection lồng nhau:

~~~java
class PurchaseOrder {

    @Id
    Long id;

    List<Shipment> shipments;
}

class Shipment {

    List<Parcel> parcels;
}
~~~

Đây là nested collection, nên Single Query Loading hiện không hỗ trợ trường hợp này theo giới hạn được tài liệu nêu.

### 6.2. Bật Single Query Loading

Có thể cấu hình `JdbcMappingContext` trong cấu hình JDBC:

~~~java
@Configuration
class DataJdbcConfig extends AbstractJdbcConfiguration {

    @Override
    public JdbcMappingContext jdbcMappingContext(
            Optional<NamingStrategy> namingStrategy,
            JdbcCustomConversions customConversions,
            RelationalManagedTypes jdbcManagedTypes
    ) {
        JdbcMappingContext context = super.jdbcMappingContext(
                namingStrategy,
                customConversions,
                jdbcManagedTypes
        );

        context.setSingleQueryLoadingEnabled(true);
        return context;
    }
}
~~~

Các import và chữ ký method cần khớp với phiên bản Spring Data Relational đang dùng. Nếu ứng dụng đã tùy chỉnh `AbstractJdbcConfiguration` hoặc `JdbcMappingContext`, hãy tích hợp cờ vào cấu hình hiện tại để tránh đăng ký hai bean mapping context.

Khi bật cờ, framework **sẽ thử dùng** Single Query Loading khi dialect và aggregate phù hợp. Bật cờ không đồng nghĩa mọi method đều chắc chắn chạy một query.

## 7. Repository method ảnh hưởng đến query count

Không chỉ cấu trúc aggregate, loại method cũng ảnh hưởng đến chiến lược tải.

| Method | Ý nghĩa | Query count cần chú ý |
|---|---|---|
| `findById(id)` | Tải một aggregate theo ID | Root và các phần tham chiếu; có thể Single Query Loading nếu đủ điều kiện |
| `findAll()` | Tải danh sách aggregate | Có thể N+1 ở chiến lược truyền thống |
| `findAllById(ids)` | Tải các aggregate theo tập ID | Cũng cần xét số root và collection |
| Derived query | Tìm aggregate theo thuộc tính root | Tải aggregate theo chiến lược mặc định; không dùng Single Query Loading theo giới hạn hiện hành |
| `@Query` | SQL do lập trình viên khai báo | Query tùy chỉnh không được áp dụng Single Query Loading |
| `findAll(Pageable)` | Tải một trang aggregate | Có truy vấn trang, có thể thêm count query, rồi tải phần tham chiếu |
| `findAll(Sort)` | Tải danh sách có sắp xếp | Tương tự chiến lược tải aggregate của method tương ứng |

### 7.1. Derived query không có nghĩa chỉ đọc một bảng

Ví dụ:

~~~java
List<PurchaseOrder> findByStatus(String status);
~~~

Derived query tạo điều kiện tìm root theo thuộc tính `status`. Nếu method trả về aggregate, các phần tham chiếu vẫn cần được tải theo cơ chế aggregate loading.

Một method có tên ngắn không đồng nghĩa chỉ có một câu SQL.

### 7.2. @Query cũng cần hiểu cách mapping kết quả

Ví dụ:

~~~java
@Query("SELECT * FROM purchase_orders WHERE status = :status")
List<PurchaseOrder> findOpenOrders(String status);
~~~

Câu SQL tùy chỉnh lấy root. Khi kết quả được ánh xạ thành aggregate, Spring Data JDBC vẫn có thể phát sinh các query riêng để tải các collection entity được tham chiếu. `@Query` không tự động join và materialize mọi collection.

Tài liệu Spring Data JDBC cũng nêu rằng mapping từ string-based query dùng RowMapper cho root, embedded entities và one-to-one relationships, trong khi các collection như Map, List, Set và arrays of entities được tải bằng query riêng.

Vì vậy, khi cần một kết quả báo cáo có join, nên cân nhắc DTO/read model thay vì trả về aggregate đầy đủ.

## 8. Pagination: Page và Slice thêm loại truy vấn nào?

Pagination thay đổi query count theo cách riêng.

### 8.1. Page

`Page<T>` cần biết tổng số phần tử để cung cấp tổng trang và tổng bản ghi. Spring Data JDBC có thể thực hiện:

1. Query lấy root trong phạm vi trang.
2. Query count để tính tổng bản ghi, nếu cần.
3. Các query tải entity tham chiếu cho aggregate trong trang theo chiến lược tải đang dùng.

Ví dụ trang 20 đơn hàng, mỗi đơn có một collection, tải truyền thống:

~~~text
SELECT purchase_orders ... LIMIT 20 OFFSET ...
SELECT COUNT(*) FROM purchase_orders ...
SELECT order_lines ... (cho root thứ 1)
SELECT order_lines ... (cho root thứ 2)
...
SELECT order_lines ... (cho root thứ 20)
~~~

Query count minh họa tối đa theo mẫu này:

\[
Q = 1 + 1 + 20 = 22
\]

Trong đó:

- 1 query lấy trang root.
- 1 query đếm tổng.
- 20 query tải collection cho các root trong trang.

Query count có thể thấp hơn nếu Spring Data xác định không cần chạy count query, chẳng hạn có thể suy ra tổng từ nội dung trang.

### 8.2. Slice

`Slice<T>` chỉ cần biết có trang tiếp theo hay không. Spring Data lấy `LIMIT + 1` để xác định còn dữ liệu hay không, không cần query tổng count như `Page`.

Với 20 phần tử trong slice và một collection mỗi root, mô hình tải truyền thống:

~~~text
SELECT purchase_orders ... LIMIT 21
SELECT order_lines ... (cho từng root được giữ trong slice)
~~~

Query count minh họa:

\[
Q \approx 1 + 20
\]

Số root thực tế được materialize có thể là 20; hàng thứ 21 chỉ hỗ trợ xác định `hasNext`.

### 8.3. Pagination không tự giải quyết N+1

Pagination giới hạn số root trong một lần đọc, nhưng nếu mỗi root vẫn cần query collection riêng thì query count vẫn tăng theo kích thước trang.

Ví dụ trang 100 root vẫn có thể tạo khoảng 101 query cho một collection theo chiến lược truyền thống. Chọn page size nhỏ hơn làm giảm query trong một request nhưng tăng số request cần thiết để duyệt toàn bộ dữ liệu.

## 9. Đọc danh sách chỉ để hiển thị: có nhất thiết phải tải aggregate?

Một màn hình danh sách đơn hàng thường chỉ cần:

- ID đơn.
- Mã đơn.
- Trạng thái.
- Tên khách hàng.
- Tổng tiền.
- Ngày tạo.

Nếu gọi:

~~~java
List<PurchaseOrder> orders = repository.findAll();
~~~

ứng dụng có thể tải cả các collection dòng hàng, ghi chú và những thành phần khác của aggregate dù màn hình không sử dụng chúng.

Đó là chi phí đọc không cần thiết.

Trong trường hợp chỉ cần danh sách tóm tắt, hãy dùng **read query hoặc DTO projection** để lấy đúng cột cần thiết.

Ví dụ với `NamedParameterJdbcTemplate`:

~~~java
public record PurchaseOrderSummary(
        Long id,
        String orderCode,
        String status,
        BigDecimal totalAmount
) {
}
~~~

~~~java
@Repository
public class PurchaseOrderSummaryQuery {

    private final NamedParameterJdbcTemplate jdbc;

    public PurchaseOrderSummaryQuery(
            NamedParameterJdbcTemplate jdbc
    ) {
        this.jdbc = jdbc;
    }

    public List<PurchaseOrderSummary> findSummaries(String status) {
        String sql = """
            SELECT
                o.id,
                o.order_code,
                o.status,
                COALESCE(SUM(l.quantity * l.unit_price), 0) AS total_amount
            FROM purchase_orders o
            LEFT JOIN order_lines l ON l.order_id = o.id
            WHERE o.status = :status
            GROUP BY o.id, o.order_code, o.status
            ORDER BY o.id DESC
            """;

        return jdbc.query(
                sql,
                Map.of("status", status),
                (rs, rowNum) -> new PurchaseOrderSummary(
                        rs.getLong("id"),
                        rs.getString("order_code"),
                        rs.getString("status"),
                        rs.getBigDecimal("total_amount")
                )
        );
    }
}
~~~

Truy vấn này trả về DTO cho màn hình. Nó không yêu cầu dựng `PurchaseOrder` cùng toàn bộ collection của từng aggregate.

Cần nhớ: đây là **read model**. Các thao tác nghiệp vụ thay đổi đơn vẫn nên tải aggregate root và gọi hành vi domain theo thiết kế.

### 9.1. Chọn read model không có nghĩa phá vỡ aggregate

Có thể tổ chức hai đường đọc:

~~~text
Command / nghiệp vụ ghi:
    PurchaseOrderRepository
        -> Load aggregate đầy đủ
        -> Kiểm tra invariant
        -> Save aggregate

Query / màn hình:
    PurchaseOrderSummaryQuery
        -> SQL projection / DTO
        -> Chỉ lấy cột cần hiển thị
~~~

Một aggregate có thể được tải đầy đủ khi cần thực hiện nghiệp vụ, trong khi danh sách và báo cáo dùng truy vấn riêng tối ưu cho đọc.

## 10. Streaming danh sách lớn

Nếu cần xử lý nhiều aggregate, trả về `List<T>` có thể khiến toàn bộ kết quả được giữ trong bộ nhớ.

Spring Data JDBC hỗ trợ một số query method trả về `Stream<T>`, giúp phần tử được cung cấp khi dữ liệu sẵn sàng. Tuy nhiên, Stream giữ kết nối database mở và phải được đóng.

Ví dụ:

~~~java
interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    Stream<PurchaseOrder> streamAllByStatus(String status);
}
~~~

Sử dụng:

~~~java
@Transactional(readOnly = true)
public void processOrders(String status) {

    try (Stream<PurchaseOrder> orders =
                 repository.streamAllByStatus(status)) {

        orders.forEach(this::process);
    }
}
~~~

Lưu ý:

- Luôn đóng Stream bằng try-with-resources.
- Kết nối được giữ trong khi Stream được tiêu thụ.
- Cần quản lý transaction và thời gian xử lý để không giữ connection quá lâu.
- Streaming giúp giảm nhu cầu giữ toàn bộ root list trong bộ nhớ, nhưng không tự động biến việc tải collection thành một query.
- Nếu mỗi aggregate vẫn được tải bằng nhiều statement, query count vẫn cần được đo.

Streaming phù hợp cho batch processing, không nhất thiết phù hợp cho request HTTP cần phản hồi nhanh.

## 11. Cách đo query count trong ứng dụng

Không nên suy luận query count chỉ từ số lần gọi repository. Hãy quan sát SQL thực tế.

### 11.1. Bật log JDBC

Có thể bật log trong `application.yml`:

~~~yaml
logging:
  level:
    org.springframework.jdbc: DEBUG
~~~

Hoặc `application.properties`:

~~~properties
logging.level.org.springframework.jdbc=DEBUG
~~~

Log giúp quan sát các câu SQL do Spring JDBC thực thi. Trong môi trường nhiều traffic, chỉ bật log SQL trong thời gian kiểm tra vì log có thể rất lớn và chứa thông tin nhạy cảm trong bind parameters tùy cấu hình.

### 11.2. Đếm đúng loại statement

Khi đo, hãy phân loại:

- Query lấy aggregate root.
- Query tải collection/entity tham chiếu.
- Query count của pagination.
- Query bổ sung do service tự gọi.
- Query kiểm tra tồn tại hoặc truy vấn nghiệp vụ khác.
- Query khởi tạo/metadata không thuộc use case đang benchmark.

Đừng cộng mọi SQL trong log khởi động vào query count của một thao tác repository.

### 11.3. Integration test đo SQL

Có thể dùng datasource proxy hoặc công cụ quan sát JDBC trong integration test để đếm số statement của một thao tác.

Ví dụ quy trình:

1. Chuẩn bị dữ liệu cố định: 10 đơn, mỗi đơn có 3 dòng.
2. Xóa bộ đếm SQL trước khi gọi repository.
3. Gọi `findAll()` hoặc `findAllById(ids)`.
4. Đếm SELECT root và SELECT collection.
5. Lặp lại với Single Query Loading nếu aggregate đủ điều kiện.
6. So sánh cả query count, tổng số hàng và thời gian thực thi.

Không nên chỉ benchmark trên database in-memory rồi kết luận cho PostgreSQL/MySQL. Dialect, driver, index, dữ liệu và kế hoạch thực thi đều ảnh hưởng kết quả.

## 12. Một ví dụ so sánh hoàn chỉnh

Giả sử có 50 đơn hàng. Mỗi đơn có 2 collection trực tiếp: `lines` và `notes`.

### Tải truyền thống

~~~text
1 SELECT purchase_orders

50 SELECT order_lines
50 SELECT order_notes

Tổng: 101 câu SELECT
~~~

Công thức:

\[
Q = 1 + N \times C
\]

Trong đó:

- `N`: số aggregate root được tải.
- `C`: số collection trực tiếp được tải trên mỗi root.

Với `N = 50`, `C = 2`:

\[
Q = 1 + 50 \times 2 = 101
\]

### Single Query Loading

Nếu aggregate đáp ứng đầy đủ điều kiện và method nằm trong phạm vi hỗ trợ:

~~~text
1 SELECT được tạo để tải:
    purchase_orders
    order_lines
    order_notes

Tổng: 1 câu SELECT
~~~

Query này có thể trả về nhiều hàng hơn một query root đơn giản, nhưng được thiết kế để biểu diễn collection mà không tạo tích Descartes không cần thiết.

### Danh sách tóm tắt bằng DTO

Nếu màn hình chỉ cần ID, status và tổng tiền, một SQL projection có thể đủ:

~~~text
1 SELECT purchase_orders
    JOIN order_lines
    GROUP BY purchase_orders
    -> List<PurchaseOrderSummary>

Tổng: 1 câu SELECT
~~~

Đường đọc này không dựng đầy đủ aggregate. Hãy chọn theo mục đích: nghiệp vụ cần aggregate, màn hình danh sách cần projection.

## 13. Những điều không nên nhầm lẫn

| Nhận định | Cách hiểu chính xác |
|---|---|
| `findAll()` luôn chỉ chạy một SELECT | Tải truyền thống có thể tạo N+1 khi aggregate có collection |
| Một aggregate có 100 child luôn cần 101 query | Một root đơn có một collection thường cần root query và child query; 100 là số dòng kết quả, không phải số query |
| N+1 chỉ xuất hiện trong JPA/Hibernate | Spring Data JDBC cũng có thể gặp N+1 khi tải danh sách aggregate có collection |
| Getter collection mới chạy SQL | Spring Data JDBC tải aggregate trong quá trình repository đọc; getter không phải lazy proxy |
| Bật Single Query Loading là mọi query đều thành một câu | Chỉ áp dụng khi aggregate, dialect và repository method đủ điều kiện |
| `@Query` tự động join mọi collection | Collection entity vẫn có thể được tải bằng statement riêng |
| `Page<T>` và `Slice<T>` có cùng query count | Page có thể thêm count query; Slice dùng LIMIT+1 |
| `Stream<T>` loại bỏ N+1 | Streaming chủ yếu hỗ trợ tiêu thụ kết quả; không tự đổi chiến lược aggregate loading |
| Một query luôn nhanh hơn nhiều query | Cần xét dữ liệu trả về, execution plan, index, network và chi phí dựng object |
| DTO query thay thế repository cho mọi nghiệp vụ | DTO/read query dành cho đọc; thao tác domain vẫn cần aggregate và invariant |

## 14. Quy trình phân tích query count cho một màn hình

Khi một endpoint hoặc màn hình chậm, hãy thực hiện theo thứ tự:

**Bước 1 — Xác định dữ liệu cần dùng.** Màn hình cần aggregate đầy đủ hay chỉ một số cột?

**Bước 2 — Xác định số root.** Một root theo ID, danh sách 20 phần tử, hay hàng nghìn phần tử?

**Bước 3 — Vẽ cấu trúc được tải.** Root có bao nhiêu collection? Có nested collection không? Có tham chiếu một-một hoặc `AggregateReference` không?

**Bước 4 — Xác định method.** `findById`, `findAll`, `findAllById`, derived query, `@Query`, `Page` hay `Stream`?

**Bước 5 — Xác định chiến lược.** Tải truyền thống hay Single Query Loading đã bật và đủ điều kiện?

**Bước 6 — Ước lượng query count.** Tính root query, collection queries, count query và các truy vấn do service gọi thêm.

**Bước 7 — Bật SQL log.** Đối chiếu số dự đoán với số statement thực tế.

**Bước 8 — Chọn cách tối ưu.** Single Query Loading, giảm số root mỗi trang, read DTO, SQL projection, thiết kế lại aggregate hoặc custom query có chủ đích.

**Bước 9 — Đo lại.** So sánh query count, tổng row, dữ liệu truyền, thời gian database và thời gian endpoint.

~~~text
Use case / màn hình
       |
       v
Cần aggregate đầy đủ?
       |
       +---- Có ------------------------------+
       |                                      |
       v                                      v
Đếm root N                           Vẽ cấu trúc aggregate
       |                                      |
       +----------------+---------------------+
                        |
                        v
              Xác định repository method
                        |
                        v
              Single Query Loading đủ điều kiện?
                    /             \
                  Có               Không
                  |                  |
                  v                  v
             Một SQL           Root + statements
                               cho references
                                    |
                                    v
                              Kiểm tra N+1
                                    |
                                    v
                              Đo SQL thực tế
                                    |
                                    v
                           Tối ưu theo mục đích
~~~

## 15. Bài tập tự suy luận

**Tình huống A — Một aggregate có 20 dòng hàng**

Gọi `findById(10L)` trong chiến lược truyền thống. Có thể kết luận 21 query không?

**Gợi ý:** Không. Với một root và một collection, mô hình thường là một query root và một query collection. 20 là số dòng kết quả của collection.

**Tình huống B — Danh sách 100 aggregate, mỗi root có một collection**

Tải truyền thống có thể tạo bao nhiêu query?

**Gợi ý:** Theo mẫu N+1, 1 query root cộng 100 query collection, tổng 101.

**Tình huống C — Danh sách 100 aggregate, mỗi root có hai collection**

Nếu cả hai collection đều được tải theo chiến lược truyền thống, query count minh họa là bao nhiêu?

**Gợi ý:** `1 + 2 × 100 = 201`.

**Tình huống D — Page 20 đơn hàng**

`Page<PurchaseOrder>` có thể thêm loại query nào ngoài query root và collection?

**Gợi ý:** Query `COUNT(*)` để xác định tổng số bản ghi, nếu Spring Data cần chạy count query.

**Tình huống E — Aggregate có nested collection**

Có thể bật Single Query Loading rồi mặc định mọi tầng được tải bằng một SQL không?

**Gợi ý:** Không. Nested collections, bao gồm Map, nằm trong các giới hạn hiện hành; framework có thể quay về tải truyền thống.

**Tình huống F — Màn hình chỉ hiển thị mã đơn và trạng thái**

Có cần tải toàn bộ aggregate cùng collection không?

**Gợi ý:** Không nhất thiết. Một read query trả DTO với các cột cần thiết có thể tiết kiệm nhiều truy vấn và bộ nhớ.

## 16. Ghi nhớ

| Khái niệm | Ý nghĩa |
|---|---|
| Aggregate loading | Tải root và các entity được tham chiếu |
| Traditional loading | Root và references được tải bằng nhiều statement |
| N+1 | Một query lấy N root, sau đó N query tải collection |
| Single Query Loading | Có thể tải nhiều aggregate bằng một SQL nếu đủ điều kiện |
| Nested collection | Một trong các giới hạn hiện hành của Single Query Loading |
| `Page<T>` | Có thể thêm count query |
| `Slice<T>` | Dùng `LIMIT + 1` để kiểm tra trang tiếp theo |
| `Stream<T>` | Tiêu thụ kết quả dần; cần đóng stream và quản lý connection |
| DTO/read model | Chỉ lấy dữ liệu màn hình cần, không dựng aggregate đầy đủ |
| SQL logging | Cách xác nhận số statement thực tế |

**Query count cần được suy luận từ cả số root, cấu trúc aggregate và chiến lược tải.** Một lần `findById()` có thể chỉ cần vài câu SQL, nhưng `findAll()` trên hàng trăm aggregate có collection có thể tạo N+1. Single Query Loading giúp giảm vấn đề này khi đáp ứng các giới hạn; với màn hình chỉ đọc một phần dữ liệu, projection/DTO thường là lựa chọn phù hợp hơn. Hãy đo SQL thực tế trên database mục tiêu trước khi kết luận hiệu năng.

## Tài liệu tham khảo

- [Spring Data Relational — Persisting Entities / Loading Aggregates](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): tải truyền thống và Single Query Loading, điều kiện hỗ trợ và giới hạn.
- [Spring Blog — This is the Beginning of the End of the N+1 Problem: Introducing Single Query Loading](https://spring.io/blog/2023/08/31/this-is-the-beginning-of-the-end-of-the-n-1-problem-introducing-single-query/): mô tả mẫu N+1 và cách Single Query Loading dùng window functions.
- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): Page, Slice, Stream và custom `@Query`.
- [Spring Data Relational — Getting Started](https://docs.spring.io/spring-data/relational/reference/jdbc/getting-started.html): bật log `org.springframework.jdbc` để quan sát SQL.

