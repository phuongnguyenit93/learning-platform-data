# Chọn cột, sắp xếp, giới hạn và phân trang trong Query

Trong Spring Data JDBC, khi truy vấn cần được xây dựng theo điều kiện thay đổi ở runtime, bạn có thể dùng đối tượng **§org.springframework.data.relational.core.query.Query§** cùng với §Criteria§, §Sort§ và §Pageable§. Đối tượng này mô tả các phần chính của một câu SELECT: điều kiện lọc, danh sách cột cần lấy, thứ tự sắp xếp, số hàng tối đa và số hàng cần bỏ qua.

Đối tượng §Query§ được thực thi thông qua §JdbcAggregateTemplate§ hoặc §JdbcAggregateOperations§. Cách này phù hợp khi service cần tạo truy vấn từ nhiều bộ lọc tùy chọn, chọn tập cột, thay đổi sort và giới hạn kết quả mà không phải ghép chuỗi SQL thủ công.

Bốn khả năng cần nắm:

- **Chọn cột:** dùng §columns(...)§ để giới hạn các cột trong SELECT.
- **Sắp xếp:** dùng §sort(Sort)§ để chỉ định thứ tự kết quả.
- **Giới hạn:** dùng §limit(int)§ để giới hạn số hàng và §offset(long)§ để bỏ qua một số hàng.
- **Phân trang:** dùng §with(Pageable)§ để áp dụng đồng thời offset, limit và sort từ một yêu cầu phân trang.

Bài học tập trung vào API §Query§ của Spring Data JDBC, cách xây dựng truy vấn động, cách trả về kết quả trang và những giới hạn cần hiểu khi chỉ chọn một phần cột của aggregate.

## 1. Query trong Spring Data JDBC là gì?

§Query§ là một value object mô tả truy vấn quan hệ. Nó có thể chứa:

| Thành phần | API | Vai trò |
| --- | --- | --- |
| Điều kiện | §Criteria§ / §CriteriaDefinition§ | Tạo mệnh đề WHERE. |
| Danh sách cột | §columns(...)§ | Chọn các cột cần đọc. |
| Sắp xếp | §sort(Sort)§ | Tạo ORDER BY. |
| Giới hạn | §limit(int)§ | Giới hạn số hàng trả về. |
| Offset | §offset(long)§ | Bỏ qua số hàng đầu theo thứ tự. |
| Phân trang | §with(Pageable)§ | Áp dụng offset, limit và sort cùng lúc. |

Ví dụ truy vấn một người dùng theo tên:

§§§java
Query query = Query.query(
        Criteria.where("name").is("Gandalf")
);

Optional<Person> person =
        jdbcAggregateTemplate.findOne(query, Person.class);
§§§

§Query.query(criteria)§ tạo query có điều kiện. §findOne§ thực thi truy vấn và trả về §Optional§; nếu không có kết quả thì trả §Optional.empty()§, nếu có nhiều hơn một kết quả thì phát sinh lỗi kích thước kết quả không hợp lệ.

Khác với tên method suy diễn như §findByStatusAndCategoryId§, §Query§ cho phép service quyết định ở runtime bộ lọc nào sẽ được thêm vào.

### 1.1. Query API khác với annotation @Query

Có hai API dễ bị nhầm:

| API | Package | Mục đích |
| --- | --- | --- |
| §Query§ class | §org.springframework.data.relational.core.query.Query§ | Xây dựng query bằng Java API. |
| §@Query§ annotation | §org.springframework.data.jdbc.repository.query.Query§ | Khai báo SQL dạng chuỗi trên repository method. |

Ví dụ §Query§ class:

§§§java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
).limit(20);
§§§

Ví dụ annotation §@Query§:

§§§java
@Query("SELECT * FROM products WHERE status = :status")
List<Product> findActiveProducts(String status);
§§§

Bài học này nói về đối tượng §Query§ dùng cùng §JdbcAggregateTemplate§. Với SQL dạng chuỗi trong §@Query§, ứng dụng tự viết câu SQL và phải tự quản lý phần giới hạn/sắp xếp theo các quy tắc hỗ trợ của API đó.

## 2. JdbcAggregateTemplate thực thi Query

§JdbcAggregateTemplate§ là API truy cập trực tiếp hơn để đọc và lưu aggregate. Khi cấu hình Spring Data JDBC, framework cung cấp nó như một Spring bean, vì vậy có thể inject vào service hoặc custom repository fragment.

Ví dụ:

§§§java
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final JdbcAggregateTemplate jdbc;

    public ProductSearchService(JdbcAggregateTemplate jdbc) {
        this.jdbc = jdbc;
    }
}
§§§

Các phương thức đọc thường dùng:

| Phương thức | Kết quả |
| --- | --- |
| §findOne(Query, Class<T>)§ | §Optional<T>§, yêu cầu tối đa một kết quả. |
| §findAll(Query, Class<T>)§ | §List<T>§ các aggregate phù hợp. |
| §streamAll(Query, Class<T>)§ | §Stream<T>§ để đọc tuần tự. |
| §count(Query, Class<T>)§ | Số aggregate thỏa điều kiện. |
| §exists(Query, Class<T>)§ | Kiểm tra có aggregate thỏa điều kiện hay không. |

Ví dụ:

§§§java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
);

List<Product> products =
        jdbcAggregateTemplate.findAll(query, Product.class);
§§§

§findAll(Query, Class)§ trả về danh sách aggregate đã được ánh xạ. Nếu aggregate có các entity được sở hữu, Spring Data JDBC vẫn áp dụng cơ chế tải aggregate tương ứng; Query không biến repository thành một API trả về bảng phẳng tùy ý.

## 3. Tạo Query không có điều kiện hoặc có Criteria

Có hai cách tạo query cơ bản.

### 3.1. Query.empty()

Dùng khi không cần điều kiện WHERE:

§§§java
Query query = Query.empty();
§§§

Có thể nối thêm sort, limit, offset hoặc columns:

§§§java
Query query = Query.empty()
        .sort(Sort.by("name").ascending())
        .limit(20);
§§§

Query này lấy tối đa 20 kết quả và sắp xếp theo tên tăng dần.

### 3.2. Query.query(Criteria)

Dùng khi có điều kiện:

§§§java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
);
§§§

Điều kiện tương đương:

§§§sql
WHERE status = ?
§§§

Giá trị được bind qua cơ chế JDBC; không cần nối chuỗi giá trị đầu vào vào SQL.

### 3.3. Kết hợp nhiều điều kiện

§Criteria§ hỗ trợ các phép so sánh như §is§, §greaterThan§, §lessThan§, §between§, §in§, §like§, §isNull§ và §isNotNull§. Có thể kết hợp điều kiện bằng §and§ và §or§.

Ví dụ:

§§§java
Criteria criteria = Criteria.where("status").is("ACTIVE")
        .and("price").greaterThanOrEquals(new BigDecimal("100"))
        .and("stock_quantity").greaterThan(0);

Query query = Query.query(criteria);
§§§

Ý nghĩa SQL:

§§§sql
WHERE status = 'ACTIVE'
  AND price >= 100
  AND stock_quantity > 0
§§§

Có thể dùng nhóm điều kiện:

§§§java
Criteria criteria = Criteria.from(
        Criteria.where("status").is("ACTIVE"),
        Criteria.where("price").greaterThanOrEquals(
                new BigDecimal("100")
        )
);
§§§

§Criteria§ cũng là immutable API: mỗi lần nối điều kiện trả về một object mới. Khi xây dựng điều kiện động, hãy gán lại biến:

§§§java
Criteria criteria = Criteria.where("status").is("ACTIVE");

if (minimumPrice != null) {
    criteria = criteria.and("price").greaterThanOrEquals(minimumPrice);
}

if (maximumPrice != null) {
    criteria = criteria.and("price").lessThanOrEquals(maximumPrice);
}

Query query = Query.query(criteria);
§§§

Nếu quên gán kết quả của §and§ hoặc §or§, điều kiện mới sẽ không nằm trong biến query ban đầu.

## 4. Chọn cột bằng columns(...)

§Query.columns(...)§ chỉ định các cột cần được chọn trong câu SELECT.

Ví dụ chỉ lấy ID, tên và trạng thái:

§§§java
Query query = Query.empty()
        .columns("id", "name", "status");

List<Product> products =
        jdbcAggregateTemplate.findAll(query, Product.class);
§§§

Ý tưởng SQL:

§§§sql
SELECT id, name, status
FROM products;
§§§

Nếu không gọi §columns(...)§, query sử dụng tập cột mặc định theo mapping của aggregate. Khi gọi §columns(...)§, danh sách cột được chọn được giới hạn theo những tên đã khai báo.

### 4.1. Tên cột phải phù hợp mapping

Spring Data Relational dùng naming strategy để chuyển tên property Java thành tên cột. Theo quy ước mặc định, property §createdAt§ thường ánh xạ thành cột §created_at§. Nếu có §@Column§, tên cột được khai báo tường minh.

Ví dụ:

§§§java
@Table("products")
public class Product {

    @Id
    private Long id;

    private String name;

    @Column("created_at")
    private LocalDateTime createdAt;
}
§§§

Khi chọn cột, dùng tên cột SQL tương ứng với mapping, ví dụ §created_at§. Nếu schema dùng tên tùy chỉnh, cần chọn đúng identifier được khai báo.

Từ Spring Data Relational 4.1, §Query§ còn có API §columnsOf(...)§ nhận các §TypedPropertyPath§ để chọn cột dựa trên property path có kiểu. API này giúp giảm phụ thuộc vào chuỗi tên cột trong các trường hợp phù hợp.

### 4.2. Chọn cột không tự biến kết quả thành DTO

Điểm cần nhớ: §findAll(query, Product.class)§ vẫn yêu cầu ánh xạ kết quả thành kiểu §Product§. §columns(...)§ chỉ thay đổi danh sách cột SELECT; nó không tự tạo một projection interface hoặc DTO mới.

Ví dụ nếu §Product§ có constructor bắt buộc:

§§§java
public record Product(
        Long id,
        String name,
        BigDecimal price,
        String status
) {
}
§§§

nhưng query chỉ chọn §id§ và §name§:

§§§java
Query query = Query.empty().columns("id", "name");
List<Product> products =
        jdbcAggregateTemplate.findAll(query, Product.class);
§§§

thì mapper không có đủ dữ liệu để gọi constructor có các tham số §price§ và §status§. Với kiểu mutable có constructor không tham số, thuộc tính không được chọn có thể không được thiết lập và giữ giá trị mặc định/null.

Vì vậy:

- Chỉ chọn subset cột khi kiểu kết quả có thể được ánh xạ an toàn từ các cột đó.
- Không dùng aggregate đọc thiếu cột như đầu vào §save§.
- Nếu mục tiêu là DTO chỉ đọc, dùng query/custom repository với §RowMapper§ phù hợp hoặc cơ chế projection được hỗ trợ.
- Nếu cần cập nhật aggregate, tải trạng thái đầy đủ trước khi thay đổi và lưu.

Đây là ranh giới quan trọng giữa **tối ưu dữ liệu đọc** và **đối tượng mang trạng thái để ghi**.

### 4.3. Ví dụ read model riêng cho một truy vấn

Nếu chỉ cần danh sách tóm tắt sản phẩm, có thể dùng JDBC mapper cho DTO:

§§§java
public record ProductSummary(
        Long id,
        String name,
        String status
) {
}
§§§

Với §NamedParameterJdbcTemplate§ hoặc §JdbcTemplate§, bạn có thể viết SQL chọn đúng cột và map trực tiếp vào DTO:

§§§java
String sql = """
        SELECT id, name, status
        FROM products
        WHERE status = :status
        ORDER BY name ASC, id ASC
        LIMIT :limit OFFSET :offset
        """;

MapSqlParameterSource parameters = new MapSqlParameterSource()
        .addValue("status", "ACTIVE")
        .addValue("limit", 20)
        .addValue("offset", 0);

List<ProductSummary> summaries =
        namedParameterJdbcTemplate.query(
                sql,
                parameters,
                (rs, rowNum) -> new ProductSummary(
                        rs.getLong("id"),
                        rs.getString("name"),
                        rs.getString("status")
                )
        );
§§§

Đây là JDBC query tùy chỉnh, không phải cách gọi §JdbcAggregateTemplate.findAll(Query, Product.class)§. Dùng nó khi cần read model/DTO hoặc SQL projection rõ ràng.

## 5. Sắp xếp bằng Sort

§Query.sort(Sort)§ thêm thứ tự sắp xếp cho query.

Ví dụ sắp xếp theo tên tăng dần:

§§§java
Query query = Query.empty()
        .sort(Sort.by("name").ascending());
§§§

Tương đương:

§§§sql
ORDER BY name ASC
§§§

Sắp xếp theo giá giảm dần:

§§§java
Sort sort = Sort.by(Sort.Direction.DESC, "price");

Query query = Query.empty().sort(sort);
§§§

### 5.1. Sắp xếp theo nhiều thuộc tính

§Sort§ có thể chứa nhiều thứ tự:

§§§java
Sort sort = Sort.by(
        Sort.Order.asc("status"),
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
);

Query query = Query.empty().sort(sort);
§§§

Database sắp xếp:

1. Status tăng dần.
2. Trong cùng status, ngày tạo giảm dần.
3. Nếu status và ngày tạo bằng nhau, ID tăng dần.

Thêm khóa duy nhất như §id§ ở cuối giúp kết quả có thứ tự ổn định khi các giá trị sort chính trùng nhau.

### 5.2. Vì sao sort ổn định quan trọng?

Nếu phân trang theo §createdAt DESC§ nhưng nhiều hàng có cùng timestamp, database không bảo đảm thứ tự giữa các hàng bằng nhau nếu không có tiêu chí phụ. Khi lấy trang tiếp theo, một hàng có thể xuất hiện lặp hoặc bị bỏ qua do thứ tự không xác định.

Một sort tốt cho phân trang thường gồm:

§§§java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
);
§§§

Thứ tự có ID duy nhất làm tie-breaker. Điều này tạo thứ tự xác định hơn khi dữ liệu không thay đổi trong lúc đọc.

### 5.3. Sort từ request phải có allowlist

Không nên nhận tên cột tùy ý từ client rồi đưa trực tiếp vào §Sort.by(...)§. Hãy giới hạn những property mà API cho phép:

§§§java
private Sort resolveSort(String requestedSort) {
    return switch (requestedSort) {
        case "name" ->
                Sort.by("name").ascending()
                        .and(Sort.by("id").ascending());
        case "price" ->
                Sort.by(Sort.Order.desc("price"))
                        .and(Sort.Order.asc("id"));
        case "created" ->
                Sort.by(Sort.Order.desc("createdAt"))
                        .and(Sort.Order.asc("id"));
        default ->
                Sort.by(Sort.Order.asc("id"));
    };
}
§§§

Sort không phải bind parameter như giá trị WHERE. Tên thuộc tính sắp xếp ảnh hưởng cấu trúc SQL, vì vậy phải được kiểm soát.

### 5.4. Sort.unsorted()

Nếu không cần sắp xếp:

§§§java
Query query = Query.empty().sort(Sort.unsorted());
§§§

Tuy nhiên, nếu đang phân trang, nên chỉ định thứ tự rõ ràng thay vì dựa vào thứ tự mặc định của database.

## 6. Giới hạn số hàng bằng limit(...)

§limit(int)§ giới hạn số hàng tối đa trả về.

Ví dụ lấy 10 sản phẩm:

§§§java
Query query = Query.empty().limit(10);

List<Product> products =
        jdbcAggregateTemplate.findAll(query, Product.class);
§§§

SQL khái niệm:

§§§sql
SELECT ...
FROM products
LIMIT 10;
§§§

Cú pháp SQL thực tế do dialect của database quyết định. Không phải mọi hệ quản trị đều dùng đúng cú pháp §LIMIT§ như PostgreSQL.

### 6.1. Kết hợp điều kiện và limit

§§§java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
).limit(10);

List<Product> products =
        jdbcAggregateTemplate.findAll(query, Product.class);
§§§

Truy vấn lấy tối đa 10 sản phẩm ACTIVE.

### 6.2. Giới hạn cần được validate

Khi nhận limit từ API, nên đặt giá trị mặc định và giá trị tối đa:

§§§java
int normalizedLimit = Math.min(
        Math.max(requestedLimit, 1),
        100
);
§§§

Ví dụ trên giới hạn khoảng giá trị từ 1 đến 100. Chính sách thực tế có thể từ chối đầu vào sai thay vì tự sửa; điều quan trọng là không để client yêu cầu một số hàng tùy ý quá lớn.

§Query.limit§ nhận số nguyên. Hãy kiểm tra đầu vào trước khi tạo Query và tránh giá trị âm hoặc không hợp lệ.

## 7. Bỏ qua hàng bằng offset(...)

§offset(long)§ xác định số hàng cần bỏ qua trước khi lấy kết quả.

Ví dụ bỏ qua 40 hàng đầu:

§§§java
Query query = Query.empty()
        .sort(Sort.by("id").ascending())
        .offset(40)
        .limit(20);
§§§

Ý nghĩa:

- Sắp xếp theo ID tăng dần.
- Bỏ qua 40 hàng đầu.
- Lấy tối đa 20 hàng tiếp theo.

SQL khái niệm:

§§§sql
SELECT ...
FROM products
ORDER BY id ASC
LIMIT 20 OFFSET 40;
§§§

Thứ tự logic phải được xác định trước khi dùng offset. Nếu không có ORDER BY, database không bảo đảm thứ tự hàng và kết quả offset không ổn định.

### 7.1. Công thức offset

Nếu trang bắt đầu từ 0:

\[
offset = pageNumber \times pageSize
\]

Ví dụ trang 3, kích thước 25:

\[
offset = 3 \times 25 = 75
\]

Có thể tạo Query thủ công:

§§§java
int pageNumber = 3;
int pageSize = 25;

long offset = (long) pageNumber * pageSize;

Query query = Query.empty()
        .sort(Sort.by("id").ascending())
        .limit(pageSize)
        .offset(offset);
§§§

Dùng phép nhân với kiểu long để tránh tràn số nguyên khi page number và page size lớn.

### 7.2. Offset sâu có thể tốn kém

Khi offset tăng rất lớn, database vẫn phải xử lý thứ tự và bỏ qua nhiều hàng trước khi trả phần dữ liệu cần thiết. Ví dụ offset 500.000 với limit 20 có thể tốn kém dù ứng dụng chỉ nhận 20 hàng.

Với dữ liệu lớn và duyệt liên tục, hãy cân nhắc keyset/cursor pagination dựa trên giá trị sort cuối cùng đã đọc, hoặc một query model phù hợp. Offset pagination thuận tiện cho giao diện số trang, nhưng không phải lựa chọn tốt nhất cho mọi workload.

## 8. Phân trang bằng Query.with(Pageable)

Nếu đã có §Pageable§, không cần tự tính offset và limit. §Query.with(pageable)§ áp dụng:

- Offset từ §pageable.getOffset()§.
- Limit từ §pageable.getPageSize()§.
- Sort từ §pageable.getSort()§.

Ví dụ:

§§§java
Pageable pageable = PageRequest.of(
        2,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")
        )
);

Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
).with(pageable);

List<Product> products =
        jdbcAggregateTemplate.findAll(query, Product.class);
§§§

Đây là trang số 2, mỗi trang tối đa 20 sản phẩm ACTIVE, sắp xếp theo ngày tạo giảm dần rồi ID tăng dần.

### 8.1. Query.with(Pageable) không tự trả về Page

§JdbcAggregateTemplate.findAll(Query, Class)§ trả về §List<T>§. Khi dùng §with(pageable)§, query chỉ giới hạn vùng dữ liệu được đọc; nó không tự tạo metadata tổng số phần tử hay tổng số trang.

Nếu chỉ cần danh sách của trang, §List§ là đủ.

Nếu cần biết tổng số kết quả, hãy gọi §count(Query, Class)§ riêng rồi tạo §Page<T>§.

### 8.2. Tạo Page bằng count và PageImpl

Ví dụ:

§§§java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;

public Page<Product> findActiveProducts(
        int pageNumber,
        int pageSize
) {
    Pageable pageable = PageRequest.of(
            pageNumber,
            pageSize,
            Sort.by(
                    Sort.Order.desc("createdAt"),
                    Sort.Order.asc("id")
            )
    );

    Query filter = Query.query(
            Criteria.where("status").is("ACTIVE")
    );

    long total = jdbcAggregateTemplate.count(
            filter,
            Product.class
    );

    Query pageQuery = filter.with(pageable);

    List<Product> content = jdbcAggregateTemplate.findAll(
            pageQuery,
            Product.class
    );

    return new PageImpl<>(content, pageable, total);
}
§§§

Luồng xử lý:

1. Tạo §Pageable§ chứa trang, kích thước và sort.
2. Tạo Query chỉ chứa điều kiện lọc.
3. Đếm tổng số aggregate phù hợp bằng §count§.
4. Áp dụng §with(pageable)§ cho query lấy dữ liệu trang.
5. Tạo §PageImpl§ từ nội dung, pageable và total.

**Lưu ý:** query dùng để đếm nên giữ điều kiện lọc nhưng không chứa limit/offset. Trong ví dụ, biến §filter§ chỉ chứa Criteria nên count không bị giới hạn theo trang.

### 8.3. API findAll(Query, Class, Pageable) đã deprecated

Trong Spring Data Relational 4.1.2, overload:

§§§java
findAll(Query query, Class<T> domainType, Pageable pageable)
§§§

được đánh dấu deprecated từ phiên bản 4.0 và dự kiến loại bỏ. API hiện tại hướng đến việc dùng §findAll(Query, Class)§ với §Query.with(pageable)§, kết hợp §count(Query, Class)§ nếu cần tạo kết quả §Page§.

Vì vậy, nên xây dựng phân trang thủ công bằng hai thao tác rõ ràng như ví dụ trên, thay vì phụ thuộc overload đã deprecated.

## 9. Phân biệt List, Page và Slice trong dynamic Query

§Query§ không tự quyết định kiểu metadata trả về; phương thức thực thi và cách service tổng hợp kết quả mới quyết định.

| Kiểu kết quả | Cách lấy | Metadata |
| --- | --- | --- |
| §List<T>§ | §findAll(query, Type.class)§ | Chỉ nội dung. |
| §Page<T>§ | §count(filter, Type.class)§ + §findAll(filter.with(pageable), Type.class)§ + §PageImpl§ | Tổng phần tử, tổng trang, trang hiện tại. |
| §Slice<T>§ | Lấy §pageSize + 1§ với limit, rồi cắt phần tử dư | Có/không có trang tiếp theo. |

Nếu muốn tạo §Slice§ thủ công:

§§§java
int pageSize = 20;

Pageable pageable = PageRequest.of(
        0,
        pageSize,
        Sort.by("id").ascending()
);

Query query = Query.empty()
        .with(PageRequest.of(
                pageable.getPageNumber(),
                pageSize + 1,
                pageable.getSort()
        ));

List<Product> rows =
        jdbcAggregateTemplate.findAll(query, Product.class);

boolean hasNext = rows.size() > pageSize;

List<Product> content = hasNext
        ? rows.subList(0, pageSize)
        : rows;

Slice<Product> slice = new SliceImpl<>(
        content,
        pageable,
        hasNext
);
§§§

Đây là kỹ thuật minh họa. Trong ứng dụng, cần kiểm tra page size, sort và cách xử lý trang tiếp theo. Nếu không cần total count, việc lấy thêm một hàng giúp tránh truy vấn count riêng.

## 10. Xây dựng truy vấn động từ bộ lọc tùy chọn

Lợi thế lớn của §Query§ là service có thể thêm điều kiện dựa trên những tham số người dùng thực sự gửi.

Giả sử màn hình tìm sản phẩm có bộ lọc:

- Status có thể có hoặc không.
- Giá tối thiểu có thể có hoặc không.
- Giá tối đa có thể có hoặc không.
- Từ khóa tên có thể có hoặc không.
- Sort, page và size do request cung cấp.

Ví dụ xây dựng Criteria:

§§§java
private Criteria buildCriteria(
        String status,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        String keyword
) {
    Criteria criteria = Criteria.empty();

    if (status != null && !status.isBlank()) {
        criteria = criteria.and(
                Criteria.where("status").is(status)
        );
    }

    if (minPrice != null) {
        criteria = criteria.and(
                Criteria.where("price").greaterThanOrEquals(minPrice)
        );
    }

    if (maxPrice != null) {
        criteria = criteria.and(
                Criteria.where("price").lessThanOrEquals(maxPrice)
        );
    }

    if (keyword != null && !keyword.isBlank()) {
        criteria = criteria.and(
                Criteria.where("name").like("%" + keyword.trim() + "%")
        );
    }

    return criteria;
}
§§§

Sau đó tạo query:

§§§java
Criteria criteria = buildCriteria(
        request.status(),
        request.minPrice(),
        request.maxPrice(),
        request.keyword()
);

Query query = Query.query(criteria)
        .sort(resolveSort(request.sort()))
        .limit(request.limit())
        .offset(request.offset());

List<Product> products =
        jdbcAggregateTemplate.findAll(query, Product.class);
§§§

Ví dụ này minh họa cách lắp ghép query theo input. Trong code thực tế, cần chuẩn hóa và validate giá trị, giới hạn page size, kiểm soát sort property và xử lý trường hợp không có điều kiện lọc.

### 10.1. Xử lý điều kiện OR

Có thể nhóm điều kiện OR rồi kết hợp với AND:

§§§java
Criteria nameMatches = Criteria.where("name")
        .like("%keyboard%");

Criteria skuMatches = Criteria.where("sku")
        .like("%keyboard%");

Criteria search = nameMatches.or(skuMatches);

Criteria activeProducts = Criteria.where("status").is("ACTIVE")
        .and(search);
§§§

Ý nghĩa:

§§§sql
WHERE status = 'ACTIVE'
  AND (
       name LIKE '%keyboard%'
       OR sku LIKE '%keyboard%'
  )
§§§

Khi điều kiện phức tạp, hãy dùng nhóm §Criteria§ rõ ràng để tránh thay đổi ý nghĩa do thứ tự AND/OR.

## 11. Kết hợp columns, Sort, limit và offset

Các thiết lập có thể nối vào cùng một Query:

§§§java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
)
.columns("id", "name", "price", "created_at")
.sort(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
))
.limit(20)
.offset(40);

List<Product> products =
        jdbcAggregateTemplate.findAll(query, Product.class);
§§§

Query trên biểu diễn:

- Lọc sản phẩm ACTIVE.
- Chọn các cột được chỉ định.
- Sắp xếp theo createdAt giảm dần, id tăng dần.
- Bỏ qua 40 hàng đầu.
- Trả tối đa 20 hàng.

Các phương thức của §Query§ là immutable: mỗi lần gọi trả về một object mới. Viết theo chuỗi như trên giữ lại toàn bộ thiết lập. Nếu viết từng bước, phải gán lại:

§§§java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
);

query = query.columns("id", "name", "price");
query = query.sort(Sort.by("name").ascending());
query = query.limit(20);
query = query.offset(40);
§§§

Nếu chỉ gọi §query.limit(20);§ mà không gán kết quả, biến §query§ ban đầu không nhận thiết lập mới.

## 12. Giới hạn của Query và khác biệt với @Query trên repository

Dynamic §Query§ class và string-based §@Query§ có khả năng khác nhau.

| Nhu cầu | Dynamic Query + JdbcAggregateTemplate | String-based @Query |
| --- | --- | --- |
| Xây dựng Criteria bằng Java | Có | Không; viết SQL. |
| Chọn cột | §columns(...)§ | Viết select list trong SQL. |
| Sort động | §sort(Sort)§ | Tự viết ORDER BY trong SQL. |
| Limit/offset | §limit§ / §offset§ / §with(Pageable)§ | Tự viết SQL và bind giá trị phù hợp. |
| Trả về aggregate qua mapping | Có | Có nếu SQL khớp RowMapper mapping. |
| Trả về DTO tùy chỉnh | Không tự động từ columns; cần mapper/read model phù hợp | Có thể dùng projection/RowMapper theo khả năng hỗ trợ. |

Tài liệu Spring Data JDBC lưu ý string-based query không hỗ trợ pagination tự động và không nhận §Sort§, §PageRequest§ hoặc §Limit§ làm tham số để framework viết lại câu query. Nếu dùng §@Query§, hãy thể hiện limit/sort trong SQL và bind tham số theo cách an toàn.

§Query§ class phù hợp khi điều kiện và sort được tạo động ở runtime. §@Query§ phù hợp khi câu SQL có cấu trúc cố định hoặc cần SQL đặc thù.

## 13. Bảo vệ truy vấn khi nhận dữ liệu từ client

Một query động thường nhận filter, sort, limit và page từ API. Cần kiểm soát chúng trước khi tạo Query.

### 13.1. Không ghép giá trị trực tiếp vào SQL

Với Criteria:

§§§java
Criteria.where("status").is(request.status())
§§§

giá trị được bind qua cơ chế JDBC. Không tự ghép chuỗi như:

§§§java
String sql = "SELECT * FROM products WHERE status = '" +
        request.status() + "'";
§§§

Cách nối chuỗi tạo nguy cơ SQL injection và lỗi escaping.

### 13.2. Allowlist cột sort

Sort là cấu trúc query, không phải một giá trị bind. Hãy map lựa chọn của client thành một tập sort đã định nghĩa:

§§§java
Sort sort = switch (request.sortBy()) {
    case "price" -> Sort.by("price").ascending()
            .and(Sort.by("id").ascending());
    case "createdAt" -> Sort.by("createdAt").descending()
            .and(Sort.by("id").ascending());
    default -> Sort.by("id").ascending();
};
§§§

Không đưa trực tiếp chuỗi tùy ý của client vào §Sort.by§.

### 13.3. Validate limit và offset

Ví dụ:

§§§java
if (request.limit() < 1 || request.limit() > 100) {
    throw new IllegalArgumentException("Invalid limit");
}

if (request.offset() < 0) {
    throw new IllegalArgumentException("Offset must not be negative");
}
§§§

Offset lớn có thể làm truy vấn chậm. Nếu API cần duyệt dữ liệu sâu, hãy đánh giá keyset pagination.

### 13.4. Không bỏ qua sort khi phân trang

Nếu query dùng offset mà không có sort ổn định, database có thể trả kết quả theo thứ tự khác nhau giữa các lần chạy. Luôn thêm một tiêu chí duy nhất như ID ở cuối sort khi phù hợp.

## 14. Hiệu năng: chọn cột, index và offset sâu

Chọn ít cột hơn có thể giảm lượng dữ liệu truyền về, nhưng lợi ích phụ thuộc kích thước hàng, kiểu cột và execution plan. Nếu truy vấn cần nhiều thuộc tính để dựng aggregate hoặc các collection liên quan, cắt cột có thể không giúp như mong đợi.

Một số nguyên tắc:

- Chỉ chọn cột cần thiết cho read use case.
- Dùng projection/DTO hoặc JDBC RowMapper cho read model thay vì dựng aggregate thiếu cột.
- Tạo index hỗ trợ các điều kiện lọc và thứ tự sort thường dùng.
- Kiểm tra execution plan trên database thực tế.
- Giới hạn số hàng ở database thay vì lấy tất cả rồi cắt trong Java.
- Thêm sort tie-breaker duy nhất khi phân trang.
- Tránh offset quá sâu nếu dữ liệu rất lớn.

Ví dụ query:

§§§sql
SELECT id, name, price, created_at
FROM products
WHERE status = 'ACTIVE'
ORDER BY created_at DESC, id ASC
LIMIT 20 OFFSET 1000;
§§§

Index có thể cân nhắc trên PostgreSQL:

§§§sql
CREATE INDEX idx_products_status_created_id
ON products (status, created_at DESC, id ASC);
§§§

Index cần được quyết định dựa trên workload và execution plan. Index tăng tốc một số truy vấn đọc nhưng cũng làm tăng chi phí insert/update và dung lượng lưu trữ.

## 15. Ví dụ service hoàn chỉnh

Giả sử aggregate:

§§§java
@Table("products")
public class Product {

    @Id
    private Long id;

    private String name;
    private BigDecimal price;
    private String status;

    @Column("created_at")
    private LocalDateTime createdAt;

    protected Product() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public String getStatus() {
        return status;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }
}
§§§

Service tạo truy vấn động:

§§§java
@Service
public class ProductSearchService {

    private final JdbcAggregateTemplate jdbc;

    public ProductSearchService(JdbcAggregateTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Product> search(
            String status,
            BigDecimal minPrice,
            int page,
            int size
    ) {
        Criteria criteria = Criteria.empty();

        if (status != null && !status.isBlank()) {
            criteria = criteria.and(
                    Criteria.where("status").is(status)
            );
        }

        if (minPrice != null) {
            criteria = criteria.and(
                    Criteria.where("price").greaterThanOrEquals(minPrice)
            );
        }

        int pageSize = Math.min(Math.max(size, 1), 100);
        int pageNumber = Math.max(page, 0);

        Sort sort = Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")
        );

        Pageable pageable = PageRequest.of(
                pageNumber,
                pageSize,
                sort
        );

        Query query = Query.query(criteria).with(pageable);

        return jdbc.findAll(query, Product.class);
    }
}
§§§

Đây là ví dụ trả về §List<Product>§ của trang hiện tại. Nếu giao diện cần tổng số kết quả, hãy thêm §jdbc.count(filter, Product.class)§ và đóng gói thành §PageImpl§ như phần 8.

Trong ứng dụng thực tế, cần xử lý thêm page âm, size không hợp lệ, sort allowlist và quyền truy cập dữ liệu.

## 16. Những lỗi thường gặp

**“Query là annotation @Query.”** Không đúng. §Query§ là class value object dùng để xây dựng truy vấn bằng Java; §@Query§ là annotation khai báo SQL dạng chuỗi.

**“Query.columns(...) tạo DTO.”** Không đúng. Nó giới hạn cột SELECT nhưng kiểu kết quả vẫn được ánh xạ theo class truyền vào §findAll§.

**“Có thể chọn thiếu cột rồi save aggregate.”** Không an toàn. Thuộc tính không được chọn có thể null/default hoặc không được khởi tạo đầy đủ; save không tự biết chúng có nghĩa là “giữ nguyên”.

**“Query là mutable builder.”** Không đúng. Các method trả về Query mới; phải dùng kết quả trả về hoặc nối chuỗi.

**“limit tự sắp xếp dữ liệu.”** Không. Nếu cần kết quả xác định, hãy thêm §Sort§.

**“offset có thể dùng mà không có ORDER BY.”** Có thể chạy nhưng thứ tự không được bảo đảm; phân trang có thể lặp hoặc bỏ sót hàng.

**“with(Pageable) trả về Page.”** Không. Nó đưa offset, limit và sort vào Query; §findAll(Query, Class)§ vẫn trả về List.

**“findAll(Query, Class, Pageable) là API nên dùng cho Page.”** Overload này deprecated từ Spring Data Relational 4.0; dùng Query.with(Pageable), count và PageImpl.

**“count phải dùng cùng limit/offset.”** Không khi muốn tổng số hàng của bộ lọc. Query đếm nên chứa điều kiện lọc nhưng không chứa giới hạn trang.

**“@Query string cũng tự nhận Pageable và Sort.”** Không. Với Spring Data JDBC, string-based query không được framework tự viết lại để áp dụng pagination hoặc sort; hãy viết SQL tương ứng.

**“Offset càng lớn cũng nhanh như trang đầu.”** Không chắc. Database có thể phải xử lý nhiều hàng trước khi trả vùng dữ liệu cần lấy.

**“Tên sort từ client có thể đưa thẳng vào query.”** Không nên. Hãy dùng allowlist các property được phép.

## 17. Quy trình chọn cột, sort, limit và phân trang

Khi tạo truy vấn động, có thể làm theo thứ tự:

1. **Xác định kiểu kết quả:** aggregate đầy đủ hay read model/DTO.
2. **Xây dựng Criteria:** chỉ thêm các điều kiện có giá trị hợp lệ.
3. **Chọn cột:** chỉ dùng subset khi kiểu kết quả có thể được map an toàn và chỉ đọc.
4. **Tạo Sort:** dùng property được allowlist và thêm tie-breaker duy nhất.
5. **Validate limit:** đặt mặc định và giới hạn tối đa.
6. **Chọn offset hoặc Pageable:** dùng limit/offset thủ công cho query đơn giản, dùng Pageable cho trang có page number/size/sort.
7. **Thực thi:** dùng findOne, findAll, streamAll hoặc count trên JdbcAggregateTemplate.
8. **Tạo Page nếu cần:** count query riêng trên filter và PageImpl cho content.
9. **Kiểm tra hiệu năng:** xem index, execution plan, số hàng và offset sâu.
10. **Giữ tách biệt đọc/ghi:** không save object aggregate được dựng từ một phần cột.

§§§mermaid
flowchart TD
    A["Nhận filter, sort, limit hoặc page"] --> B["Xây Criteria từ filter hợp lệ"]
    B --> C{"Kết quả cần là gì?"}
    C -->|Aggregate đầy đủ| D["Không cắt cột cần cho mapping"]
    C -->|Read model một phần| E["Chọn columns hoặc dùng DTO RowMapper"]
    D --> F["Tạo Sort có allowlist + tie-breaker"]
    E --> F
    F --> G{"Có phân trang?"}
    G -->|Không| H["Query.limit / Query.sort"]
    G -->|Có| I["Query.with(Pageable)"]
    H --> J["JdbcAggregateTemplate.findAll"]
    I --> J
    J --> K{"Cần total count?"}
    K -->|Có| L["count(filter) + PageImpl"]
    K -->|Không| M["Dùng List"]
    L --> N["Kiểm tra SQL, index và offset"]
    M --> N
§§§

## 18. Bài tập thực hành

Tạo bảng §products§ với các cột §id§, §name§, §price§, §status§ và §created_at§. Tạo aggregate §Product§ ánh xạ bảng này.

### Bài 1: Query cơ bản

1. Dùng §Query.empty()§ để lấy danh sách sản phẩm.
2. Dùng §Query.query(Criteria.where("status").is("ACTIVE"))§ để lọc sản phẩm.
3. Thực thi bằng §JdbcAggregateTemplate.findAll§.
4. Quan sát SQL được tạo.

### Bài 2: Chọn cột

1. Tạo query chọn §id§, §name§ và §status§.
2. Thử ánh xạ vào class mutable có constructor không tham số.
3. Quan sát các thuộc tính không được chọn.
4. Thử với record có constructor đầy đủ và giải thích vì sao cần đủ cột constructor.
5. Không dùng object thiếu cột để gọi save.

### Bài 3: Sắp xếp

1. Sắp xếp theo giá tăng dần.
2. Sắp xếp theo ngày tạo giảm dần.
3. Kết hợp ngày tạo giảm dần và ID tăng dần.
4. Tạo nhiều sản phẩm có cùng timestamp để quan sát tie-breaker.

### Bài 4: Giới hạn và offset

1. Dùng limit 10.
2. Dùng offset 20 và limit 10.
3. Thêm sort theo ID.
4. Quan sát số hàng trả về và thứ tự.
5. Thử offset lớn để xem execution plan.

### Bài 5: Pageable

1. Tạo §PageRequest.of(0, 20, sort)§.
2. Áp dụng §Query.with(pageable)§.
3. Lấy danh sách bằng §findAll(Query, Product.class)§.
4. Tạo Page bằng count và PageImpl.
5. So sánh List và Page metadata.

### Bài 6: Filter động

1. Nhận status, minPrice và maxPrice tùy chọn.
2. Xây Criteria bằng các điều kiện if.
3. Validate limit và sort.
4. Tạo Query có Criteria, Sort và Pageable.
5. Kiểm tra kết quả khi một số filter không được cung cấp.

## 19. Ghi nhớ

- §Query§ trong §org.springframework.data.relational.core.query§ là value object để xây dựng truy vấn động, khác với annotation §@Query§.
- §Criteria§ biểu diễn điều kiện WHERE và có thể kết hợp AND/OR.
- §columns(...)§ giới hạn cột SELECT; §columnsOf(...)§ dựa trên typed property path được bổ sung từ Spring Data Relational 4.1.
- Chọn cột không tự tạo DTO. Kiểu truyền vào §findAll(Query, Class)§ vẫn là kiểu được mapper ánh xạ.
- Không save aggregate được tải thiếu cột; thuộc tính thiếu có thể null/default và không có nghĩa là giữ nguyên dữ liệu.
- §sort(Sort)§ tạo thứ tự kết quả; khi phân trang nên thêm khóa duy nhất làm tie-breaker.
- §limit(int)§ giới hạn số hàng; §offset(long)§ bỏ qua số hàng theo thứ tự đã chọn.
- §with(Pageable)§ áp dụng offset, limit và sort vào Query.
- §findAll(Query, Class)§ trả về List; muốn Page cần count riêng và §PageImpl§.
- Overload §findAll(Query, Class, Pageable)§ deprecated từ Spring Data Relational 4.0; ưu tiên §Query.with(Pageable)§.
- String-based §@Query§ không tự hỗ trợ pagination/sort qua tham số Pageable hoặc Sort trong Spring Data JDBC; phải thể hiện phần SQL tương ứng.
- Kiểm soát sort, limit và offset nhận từ client; đo execution plan và tránh offset quá sâu.
- Giữ tách biệt read model một phần và aggregate đầy đủ dùng cho ghi.

Khi nắm được §Query§, bạn có thể xây dựng truy vấn theo bộ lọc runtime, chọn đúng cột, sắp xếp ổn định và giới hạn dữ liệu ngay tại database. **Hãy coi Query là mô tả của một thao tác đọc có chủ đích**: xác định kiểu kết quả trước, rồi mới chọn cột, sort, limit và phân trang phù hợp.

## Tài liệu tham khảo

- [Spring Data Relational 4.1.2 — Persisting Entities and Querying](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html)
- [Spring Data Relational 4.1.2 — Query API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/query/Query.html)
- [Spring Data Relational 4.1.2 — Criteria API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/query/Criteria.html)
- [Spring Data JDBC 4.1.2 — JdbcAggregateOperations API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateOperations.html)
- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)

