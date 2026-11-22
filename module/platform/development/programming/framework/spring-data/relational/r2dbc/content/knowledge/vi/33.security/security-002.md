# Kiểm soát tên bảng, tên cột và hướng sắp xếp động

Trong ứng dụng Spring Data Relational R2DBC, câu SQL thường kết hợp hai loại thông tin: cấu trúc câu lệnh và giá trị dữ liệu. Giá trị như email, trạng thái hoặc khoảng ngày có thể được truyền bằng bind parameter. Tên bảng, tên cột, biểu thức ORDER BY và từ khóa ASC/DESC là thành phần cấu trúc SQL; chúng không thể được thay thế an toàn bằng bind parameter thông thường.

Khi API cho phép client chọn trường sắp xếp, bảng, cột lọc hoặc schema, ứng dụng phải chuyển lựa chọn đó qua một danh sách cho phép do server kiểm soát. Chỉ những identifier và SQL fragment đã được định nghĩa trước mới được đưa vào câu lệnh. Các giá trị dữ liệu tiếp tục được bind riêng.

Bài học này giải thích cách kiểm soát identifier động trong R2DBC, cách xây dựng allowlist cho table/column/sort direction, cách dùng Sort và Criteria của Spring Data, cách ghép SQL động với DatabaseClient, cách xử lý multi-sort, filter, pagination, tenant routing và cách kiểm thử chống SQL injection.

## 1. Phân biệt identifier và value trong SQL

SQL có thể chứa nhiều loại thành phần:

| Thành phần | Ví dụ | Cách xử lý an toàn |
| --- | --- | --- |
| Giá trị dữ liệu | email, status, date, amount | Bind parameter. |
| Tên bảng | products, orders | Chọn từ allowlist server-side. |
| Tên schema | app, reporting | Chọn từ allowlist; không nhận raw input. |
| Tên cột | created_at, price | Chuyển key API sang identifier đã định nghĩa. |
| Hướng sắp xếp | ASC, DESC | Chuyển thành enum hoặc lựa chọn cố định. |
| Biểu thức sort | lower(name), created_at | Chọn toàn bộ expression từ allowlist. |
| Toán tử | =, LIKE, IN, >= | Map từ enum sang toán tử cố định. |
| Tên function/collation | lower, unaccent, collation name | Chọn từ danh sách cho phép. |

Ví dụ SQL có bind parameter:

~~~sql
SELECT id, name, price
FROM products
WHERE category_id = :categoryId
  AND status = :status
ORDER BY created_at DESC
LIMIT :limit OFFSET :offset;
~~~

Trong ví dụ này:

- categoryId và status là giá trị dữ liệu nên có thể bind.
- limit và offset là giá trị số nên có thể bind nếu driver/database hỗ trợ vị trí đó.
- products là tên bảng cố định.
- created_at là tên cột cố định.
- DESC là từ khóa SQL cố định.

Bind parameter bảo vệ giá trị dữ liệu khỏi bị diễn giải thành cú pháp SQL. Nó không biến một chuỗi thành tên bảng hoặc tên cột.

## 2. Vì sao không thể bind tên bảng hoặc tên cột?

Prepared statement phân tích cấu trúc SQL trước, sau đó mới nhận giá trị cho các vị trí bind. Bind marker đại diện cho một literal/value trong biểu thức, không đại diện cho một identifier hoặc từ khóa SQL.

Ví dụ không đúng:

~~~java
databaseClient.sql("""
    SELECT id, name
    FROM :tableName
    WHERE status = :status
    ORDER BY :sortColumn :direction
    """)
    .bind("tableName", tableName)
    .bind("status", status)
    .bind("sortColumn", sortColumn)
    .bind("direction", direction);
~~~

Các bind marker ở vị trí table, column và direction không hoạt động như mong muốn. Database có thể báo lỗi cú pháp, hoặc coi một marker trong ORDER BY là một giá trị hằng thay vì tên cột. Nó không tự biến giá trị được bind thành identifier.

Một số hệ quản trị cho phép ORDER BY một literal hoặc parameter expression. Khi đó tất cả hàng có thể được sắp xếp theo cùng một giá trị hằng, không phải theo cột mà client chọn.

### Quy tắc cần nhớ

- Bind dữ liệu.
- Allowlist identifier.
- Allowlist SQL fragment.
- Không nối raw input vào SQL.
- Không dùng escaping thay cho allowlist.

Prepared statement và bind parameter vẫn là lựa chọn đúng cho giá trị; chỉ phần cấu trúc động cần một cơ chế kiểm soát riêng.

## 3. SQL injection qua ORDER BY

Một endpoint có thể cho client gửi:

~~~text
GET /api/products?sort=createdAt&direction=DESC
~~~

Nếu code nối trực tiếp tham số vào SQL:

~~~java
String sql = "SELECT id, name FROM products ORDER BY "
    + request.sort()
    + " "
    + request.direction();
~~~

client có thể gửi chuỗi không phải tên cột hoặc hướng sắp xếp hợp lệ. Tùy cách tạo SQL, input đó có thể làm thay đổi cấu trúc câu lệnh, gây lỗi hoặc tạo lỗ hổng SQL injection.

Không giải quyết vấn đề bằng cách chỉ xóa dấu chấm phẩy, dấu cách hoặc ký tự quote. SQL có nhiều cú pháp và cách biểu diễn identifier; blacklist ký tự thường thiếu sót. Cách an toàn là không cho input trở thành SQL fragment.

## 4. Tạo allowlist cho cột sắp xếp

Giả sử API hỗ trợ sắp xếp sản phẩm theo tên, giá hoặc thời điểm tạo. Dùng enum biểu diễn lựa chọn được phép:

~~~java
public enum ProductSortKey {
    NAME,
    PRICE,
    CREATED_AT
}
~~~

Chuyển enum sang property Java hoặc SQL expression do server kiểm soát:

~~~java
public enum ProductSortKey {
    NAME("name"),
    PRICE("price"),
    CREATED_AT("createdAt");

    private final String property;

    ProductSortKey(String property) {
        this.property = property;
    }

    public String property() {
        return property;
    }
}
~~~

Khi dùng Spring Data Sort với entity ProductEntity, property thường là tên property Java được mapping, ví dụ createdAt, thay vì tên cột vật lý created_at:

~~~java
Sort.Direction direction = Sort.Direction.DESC;

Sort sort = Sort.by(direction, ProductSortKey.CREATED_AT.property());
~~~

Spring Data mapping sẽ chuyển property thành cột tương ứng theo metadata entity. Điều này giúp giữ khác biệt giữa tên property Java và tên cột database.

Không truyền trực tiếp sort key client gửi vào Sort.by nếu request chứa input tùy ý. Thay vào đó, parse lựa chọn từ allowlist và từ chối giá trị không hỗ trợ.

### Parse input thành enum

Nếu request dùng string:

~~~java
public ProductSortKey parseSortKey(String raw) {
    if (raw == null || raw.isBlank()) {
        return ProductSortKey.CREATED_AT;
    }

    try {
        return ProductSortKey.valueOf(
            raw.trim().toUpperCase(Locale.ROOT)
        );
    } catch (IllegalArgumentException exception) {
        throw new InvalidSortFieldException(raw);
    }
}
~~~

Đoạn code chỉ chấp nhận đúng các tên enum. Nếu API muốn dùng tên public như createdAt thay cho CREATED_AT, tạo Map tường minh từ public key sang enum. Không dùng reflection để biến chuỗi tùy ý thành property path.

Nếu dùng enum trực tiếp trong request DTO hoặc @RequestParam, Jackson/Spring conversion có thể từ chối giá trị không hợp lệ trước khi gọi service. Dù chọn cách nào, response lỗi cần nhất quán và không được fallback sang nối raw input.

## 5. Allowlist cho hướng sắp xếp

Hướng sắp xếp thường chỉ có hai giá trị:

~~~java
public enum SortDirection {
    ASC,
    DESC
}
~~~

Chuyển sang Spring Data:

~~~java
Sort.Direction toSpringDirection(SortDirection direction) {
    return direction == SortDirection.ASC
        ? Sort.Direction.ASC
        : Sort.Direction.DESC;
}
~~~

Nếu API nhận string, parse bằng enum hoặc Map cố định. Không nối direction tùy ý vào SQL.

Khi tạo SQL fragment thủ công, dùng switch:

~~~java
String directionSql = switch (direction) {
    case ASC -> "ASC";
    case DESC -> "DESC";
};
~~~

Giá trị directionSql chỉ có thể là một trong hai literal do source code định nghĩa. Không dùng request string trực tiếp dù nó đã được trim hoặc uppercase.

### Null ordering

Một số database hỗ trợ NULLS FIRST hoặc NULLS LAST. Đây cũng là cấu trúc SQL, nên nếu API cho phép chọn, hãy biểu diễn bằng enum:

~~~java
public enum NullPlacement {
    DEFAULT,
    FIRST,
    LAST
}
~~~

Map từng giá trị sang fragment cố định và chỉ bật tính năng khi database dialect hỗ trợ. Không nối raw input sau ORDER BY.

## 6. Dùng Sort với Spring Data R2DBC repository

Nếu repository method hỗ trợ Sort, có thể truyền Sort đã được xây dựng từ allowlist:

~~~java
public interface ProductRepository
        extends ReactiveCrudRepository<ProductEntity, UUID> {

    Flux<ProductEntity> findByStatus(String status, Sort sort);
}
~~~

Service:

~~~java
public Flux<ProductEntity> findProducts(
        String status,
        ProductSortKey sortKey,
        SortDirection direction) {

    Sort.Direction springDirection =
        direction == SortDirection.ASC
            ? Sort.Direction.ASC
            : Sort.Direction.DESC;

    Sort sort = Sort.by(
        springDirection,
        sortKey.property()
    );

    return repository.findByStatus(status, sort);
}
~~~

Property được chọn từ enum; status là giá trị dữ liệu được Spring Data bind. Repository tạo query dựa trên metadata entity.

Nếu entity khai báo:

~~~java
@Table("products")
public record ProductEntity(
    @Id UUID id,
    String name,
    BigDecimal price,
    @Column("created_at") Instant createdAt,
    String status
) {}
~~~

thì Sort property nên là createdAt. Không nhất thiết dùng created_at vì Sort trong API mapping hướng tới property của entity.

Không đưa tên cột vật lý do client gửi vào Sort. Nếu muốn public API dùng created_at, map key created_at sang property createdAt ở server.

## 7. Dùng Criteria và R2dbcEntityTemplate

Với query động gồm nhiều điều kiện, có thể xây dựng Criteria và Query. Các property path đưa vào Criteria cũng cần được chọn từ allowlist nếu chúng đến từ request.

Ví dụ:

~~~java
Criteria criteria = Criteria.where("status").is(status);

Query query = Query.query(criteria)
    .sort(Sort.by(
        Sort.Direction.DESC,
        ProductSortKey.CREATED_AT.property()
    ))
    .limit(50);

return template.select(ProductEntity.class)
    .matching(query)
    .all();
~~~

Criteria giúp biểu diễn điều kiện theo property và cho Spring Data xử lý mapping. Tuy vậy, nếu ứng dụng cho client chọn tên field, vẫn phải map field key sang property được phép trước khi tạo Criteria.

Ví dụ filter key:

~~~java
public enum ProductFilterField {
    STATUS("status"),
    CATEGORY_ID("categoryId"),
    PRICE("price");

    private final String property;

    ProductFilterField(String property) {
        this.property = property;
    }

    public String property() {
        return property;
    }
}
~~~

Service có thể dùng switch hoặc Map để tạo Criteria phù hợp với kiểu dữ liệu từng field. Tránh tạo Criteria từ một chuỗi property bất kỳ trong request.

## 8. Allowlist cho tên bảng động

Trong hầu hết ứng dụng, tên bảng nên được cố định trong entity mapping hoặc trong repository. Dynamic table selection chỉ cần thiết trong các trường hợp đặc biệt như:

- Bảng archive tách riêng.
- Bảng partition được quản lý theo kỳ.
- Sharding theo tenant hoặc vùng.
- Nhiều bảng có cùng cấu trúc và được chọn bởi một routing registry.

Không viết:

~~~java
String sql = "SELECT * FROM " + request.tableName();
~~~

Cách này cho phép input điều khiển cấu trúc SQL.

Thay vào đó, chuyển một key công khai thành một identifier đã được server đăng ký:

~~~java
public enum DataSet {
    CURRENT,
    ARCHIVE
}

private static final Map<DataSet, String> TABLES = Map.of(
    DataSet.CURRENT, "products",
    DataSet.ARCHIVE, "products_archive"
);

String tableName = TABLES.get(dataSet);
~~~

Ở đây dataSet phải được parse thành enum hợp lệ trước. Tên bảng chỉ lấy từ Map cố định.

Sau đó, nếu thật sự cần raw SQL:

~~~java
String sql = "SELECT id, name FROM " + tableName
    + " WHERE status = :status";
~~~

Phần tableName là literal đã được chọn từ allowlist; status tiếp tục bind. Không dùng request.tableName() trực tiếp.

### Hạn chế dynamic table nếu có thể

Nếu chỉ cần phân biệt dữ liệu hiện tại và lịch sử, có thể dùng hai repository/query cố định. Nếu tenant chỉ là điều kiện phân vùng logic, một bảng chung với tenant_id thường đơn giản hơn việc tạo bảng cho mỗi tenant.

Dynamic table làm phức tạp migration, index, observability, query planning, quyền truy cập và transaction. Chỉ sử dụng khi có lý do kiến trúc rõ ràng.

## 9. Schema-qualified identifier và quoting

Một tên bảng có thể gồm schema và table:

~~~sql
SELECT id FROM reporting.monthly_sales
~~~

Nếu database yêu cầu quote identifier, hãy quote từng thành phần theo quy tắc của dialect:

~~~sql
SELECT id FROM "reporting"."monthly_sales"
~~~

Không quote toàn bộ chuỗi như một identifier duy nhất:

~~~sql
SELECT id FROM "reporting.monthly_sales"
~~~

Câu lệnh sau có thể được hiểu là một tên bảng duy nhất chứa dấu chấm, thay vì schema reporting và table monthly_sales.

### Quoting không thay thế allowlist

Quoting giúp database hiểu đúng identifier, nhất là khi tên có chữ hoa, từ khóa dành riêng hoặc ký tự đặc biệt. Nó không biến raw input thành an toàn. Nếu cho client chọn identifier, vẫn phải chọn từ allowlist trước khi quote.

Khi dùng SQL thủ công, dùng identifier processing/quoting phù hợp với R2DBC dialect của database. Không giả định mọi database dùng dấu nháy kép; một số dialect có quy tắc khác. Nếu tên đã được định nghĩa cố định trong source code, có thể dùng fragment đã quote sẵn theo vendor đang hỗ trợ.

### Không tự quote bằng cách thay ký tự

Không tạo hàm quote bằng cách chỉ nối dấu quote quanh raw input. Mỗi database có quy tắc escape identifier riêng. Cách đúng là lấy identifier từ metadata/allowlist rồi dùng API identifier processing của dialect hoặc một helper đã được kiểm chứng theo vendor.

## 10. SQL động với DatabaseClient

DatabaseClient hữu ích khi query có cấu trúc động mà repository method không diễn đạt được. Quy tắc là chỉ ghép các fragment SQL do server kiểm soát; mọi giá trị dữ liệu vẫn dùng bind parameter.

Ví dụ query theo status và sort key:

~~~java
public Flux<ProductRow> search(
        String status,
        ProductSortKey sortKey,
        SortDirection direction) {

    String column = switch (sortKey) {
        case NAME -> "name";
        case PRICE -> "price";
        case CREATED_AT -> "created_at";
    };

    String order = switch (direction) {
        case ASC -> "ASC";
        case DESC -> "DESC";
    };

    String sql = """
        SELECT id, name, price, created_at
        FROM products
        WHERE status = :status
        ORDER BY %s %s, id ASC
        """.formatted(column, order);

    return databaseClient.sql(sql)
        .bind("status", status)
        .map((row, metadata) -> new ProductRow(
            row.get("id", UUID.class),
            row.get("name", String.class),
            row.get("price", BigDecimal.class),
            row.get("created_at", Instant.class)
        ))
        .all();
}
~~~

Hai fragment column và order đến từ switch cố định. status là dữ liệu nên được bind. id ASC là tie-breaker cố định để kết quả có thứ tự ổn định khi nhiều hàng có cùng giá trị sort.

Ví dụ giả định driver ánh xạ UUID, NUMERIC và timestamp về các kiểu Java đã nêu. Có thể cần điều chỉnh converter theo database.

### Tránh nối fragment không được kiểm soát

Không thay switch bằng cách ghép request.sort() hoặc request.direction() trực tiếp vào SQL. Không dùng regex đơn giản để “làm sạch” chuỗi sort. Hãy từ chối mọi lựa chọn ngoài allowlist.

## 11. Multi-column sort

Một API có thể cho client gửi:

~~~text
GET /api/products?sort=name,ASC&sort=price,DESC
~~~

Đặt giới hạn số tiêu chí, loại bỏ field trùng lặp nếu hợp đồng không cho phép và map từng key sang allowlist.

DTO:

~~~java
public record SortRequest(
    String field,
    String direction
) {}
~~~

Một parser có thể trả về Sort.Order:

~~~java
Sort.Order toOrder(SortRequest request) {
    ProductSortKey key = parseSortKey(request.field());
    SortDirection direction = parseDirection(request.direction());

    Sort.Direction springDirection =
        direction == SortDirection.ASC
            ? Sort.Direction.ASC
            : Sort.Direction.DESC;

    return new Sort.Order(
        springDirection,
        key.property()
    );
}
~~~

Ghép Sort:

~~~java
List<Sort.Order> orders = requests.stream()
    .limit(3)
    .map(this::toOrder)
    .toList();

Sort sort = orders.isEmpty()
    ? Sort.by(Sort.Direction.DESC, "createdAt")
    : Sort.by(orders);
~~~

Trong code thực tế, cần từ chối nếu số sort field vượt giới hạn thay vì chỉ âm thầm cắt bằng limit. Giới hạn 3 ở ví dụ chỉ minh họa policy. Nếu danh sách có field trùng lặp, hãy quy định rõ lấy lần đầu, lần cuối hay trả lỗi.

Với raw SQL, mỗi Order phải được chuyển sang fragment từ allowlist. Không dùng property hoặc direction string chưa xác thực.

## 12. Dynamic filters và toán tử

Filter động cũng có thể tạo injection nếu ứng dụng ghép field hoặc operator từ client.

Một request có thể yêu cầu:

~~~text
filterField=price
operator=gte
value=100
~~~

Chỉ field và operator được hỗ trợ mới được chuyển thành SQL:

~~~java
enum FilterField {
    STATUS,
    PRICE,
    CATEGORY_ID
}

enum FilterOperator {
    EQ,
    GTE,
    LTE,
    IN
}
~~~

Map operator:

~~~java
String operatorSql(FilterOperator operator) {
    return switch (operator) {
        case EQ -> "=";
        case GTE -> ">=";
        case LTE -> "<=";
        case IN -> "IN";
    };
}
~~~

Tên cột cũng cần map độc lập:

~~~java
String columnSql(FilterField field) {
    return switch (field) {
        case STATUS -> "status";
        case PRICE -> "price";
        case CATEGORY_ID -> "category_id";
    };
}
~~~

Sau đó bind value theo kiểu field. Không cho client gửi chuỗi operator tùy ý rồi nối vào SQL.

### Kiểm tra kiểu theo field

Không phải filter nào cũng nhận String. PRICE cần BigDecimal; CATEGORY_ID cần UUID; STATUS có thể là enum hoặc string code. Parse và validate kiểu trước khi bind.

Nên dùng một model nội bộ có kiểu rõ ràng thay vì một Map<String, Object> không kiểm soát:

~~~java
sealed interface ProductFilter
    permits StatusFilter, PriceRangeFilter, CategoryFilter {}

record StatusFilter(String status) implements ProductFilter {}
record PriceRangeFilter(BigDecimal min, BigDecimal max)
    implements ProductFilter {}
record CategoryFilter(UUID categoryId) implements ProductFilter {}
~~~

Mỗi loại filter có builder riêng tạo Criteria hoặc SQL fragment cố định. Điều này giảm lỗi ép kiểu và hạn chế input có thể tác động tới cú pháp.

## 13. IN clause và danh sách giá trị

Danh sách giá trị cần bind từng phần tử. Không nối chuỗi CSV vào SQL:

~~~java
// Không an toàn và cũng dễ sai khi giá trị chứa dấu phẩy/quote.
String sql = "WHERE id IN (" + String.join(",", rawIds) + ")";
~~~

Với DatabaseClient, có thể tạo tên bind marker theo index:

~~~java
String placeholders = IntStream.range(0, ids.size())
    .mapToObj(index -> ":id" + index)
    .collect(Collectors.joining(", "));

String sql = "SELECT id, name FROM products WHERE id IN ("
    + placeholders
    + ")";

DatabaseClient.GenericExecuteSpec spec = databaseClient.sql(sql);

for (int index = 0; index < ids.size(); index++) {
    spec = spec.bind("id" + index, ids.get(index));
}

return spec.map((row, metadata) ->
        new ProductRow(
            row.get("id", UUID.class),
            row.get("name", String.class)
        ))
    .all();
~~~

Tên placeholder chỉ được tạo từ số index do server tạo. Mỗi UUID vẫn được bind như một value.

### Xử lý danh sách rỗng

Không tạo SQL IN () nếu database không hỗ trợ. Quy định semantics rõ:

- Nếu danh sách rỗng nghĩa là không lọc, bỏ điều kiện IN.
- Nếu danh sách rỗng nghĩa là không có kết quả, trả Flux.empty hoặc thêm điều kiện luôn sai.
- Không tự hiểu danh sách rỗng thành “tất cả” nếu điều đó có thể mở rộng quyền truy cập.

### Giới hạn số bind parameter

Danh sách lớn có thể vượt giới hạn bind parameters. Chia danh sách thành chunk, dùng temporary table hoặc cơ chế bulk phù hợp database. Đừng chuyển sang nối raw value vào SQL để tránh giới hạn parameter.

## 14. LIKE, wildcard và tìm kiếm chuỗi

Bind parameter ngăn dữ liệu trở thành SQL syntax, nhưng ký tự % và _ trong LIKE vẫn mang ý nghĩa wildcard. Nếu API yêu cầu tìm chuỗi literal, cần escape wildcard theo quy tắc database.

Ví dụ SQL:

~~~sql
WHERE name LIKE :pattern ESCAPE '\'
~~~

Code tạo pattern cần escape:

~~~java
String escapeLike(String value) {
    return value
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_");
}

String pattern = "%" + escapeLike(searchText) + "%";
~~~

Cú pháp escape và string literal có thể khác theo database; kiểm thử trên dialect production. Bind vẫn cần thiết để tránh SQL injection. Escape wildcard chỉ điều chỉnh semantics tìm kiếm, không thay thế bind parameter.

Không nối searchText trực tiếp vào SQL, kể cả khi đã escape wildcard.

## 15. Pagination và thứ tự ổn định

LIMIT/OFFSET thường là value và có thể bind:

~~~sql
SELECT id, name, created_at
FROM products
ORDER BY created_at DESC, id ASC
LIMIT :limit OFFSET :offset;
~~~

Validate:

- page không âm.
- size lớn hơn 0.
- size không vượt ngưỡng.
- offset không vượt giới hạn số nguyên hoặc chính sách API.
- sort key và direction đến từ allowlist.

Không cho client truyền một chuỗi SQL hoàn chỉnh vào query parameter sort.

### Luôn có tie-breaker

Nếu sort theo created_at, nhiều hàng có thể cùng timestamp. Thêm id làm tie-breaker:

~~~sql
ORDER BY created_at DESC, id ASC
~~~

Thứ tự ổn định giúp pagination ít bị trùng hoặc bỏ sót khi giá trị sort chính bằng nhau. Nếu dữ liệu thay đổi liên tục giữa các trang, OFFSET pagination vẫn có thể dịch chuyển kết quả; cân nhắc keyset pagination.

### Keyset pagination

Với sort created_at DESC, id ASC, cursor có thể chứa createdAt và id của hàng cuối trang. Query trang sau dùng điều kiện so sánh tương ứng. Cấu trúc cột và hướng sort phải được chọn từ allowlist; cursor values phải được bind.

Keyset pagination phù hợp với tập dữ liệu lớn vì không phải bỏ qua offset rất sâu. Tuy nhiên, mỗi tổ hợp sort có thể cần một predicate riêng. Chỉ hỗ trợ các tổ hợp đã định nghĩa và kiểm thử kỹ semantics so sánh/null.

## 16. Dynamic table trong hệ multi-tenant

Một số hệ thống tạo bảng riêng cho từng tenant. Đây là trường hợp đặc biệt cần kiểm soát chặt chẽ.

Không tạo table name trực tiếp từ header hoặc query parameter:

~~~java
String table = "orders_" + request.tenant();
~~~

Ngay cả khi tenant name chỉ gồm chữ và số, việc ghép tên bảng từ input vẫn tạo rủi ro routing sai tenant, truy cập dữ liệu chéo tenant hoặc injection khi quy tắc tên thay đổi.

Ưu tiên:

1. Lấy tenant identity từ security context đã xác thực.
2. Tra cứu tenant trong registry server-side.
3. Registry trả về schema/table identifier đã được provisioning.
4. Kiểm tra tenant có được phép truy cập database/shard đó.
5. Chọn SQL fragment từ metadata đã tin cậy.
6. Bind mọi giá trị filter, kể cả tenant key nếu schema dùng chung.

Nếu mô hình cho phép, một bảng chung có tenant_id và row-level access condition thường dễ quản lý hơn nhiều bảng riêng.

### Table allowlist không thay authorization

Ngay cả khi table name hợp lệ, người dùng vẫn có thể không có quyền truy cập tenant tương ứng. Allowlist bảo vệ cấu trúc SQL; authorization bảo vệ quyền truy cập dữ liệu. Phải thực hiện cả hai.

Không lấy tenant id từ request làm bằng chứng quyền truy cập. Dùng principal đã xác thực và thêm điều kiện tenant vào query để tránh truy vấn nhầm dữ liệu.

## 17. Identifier trong R2DBC và Spring Data mapping

Spring Data Relational dùng metadata entity để ánh xạ property Java sang tên cột/table. Các annotation như @Table, @Id và @Column mô tả mapping tĩnh:

~~~java
@Table("products")
public record ProductEntity(
    @Id UUID id,
    String name,
    @Column("created_at") Instant createdAt
) {}
~~~

Khi dùng repository hoặc R2dbcEntityTemplate, Spring Data biết property createdAt ánh xạ tới cột created_at.

SqlIdentifier là abstraction của Spring Data Relational để biểu diễn identifier và metadata quoting. Nó hữu ích trong các API mapping và custom persistence implementation có hỗ trợ identifier. Nó không phải bind parameter của SQL và không tự làm raw request string trở nên an toàn.

Với raw DatabaseClient SQL, ứng dụng chịu trách nhiệm tạo phần SQL text. Hãy map key ngoài vào identifier đã tin cậy trước khi ghép. Nếu cần quote, dùng identifier processing phù hợp dialect.

### Repository và custom SQL có khác biệt

- Repository derived query thường nhận property và value theo metadata Spring Data.
- Sort trong repository dùng property path được mapping.
- Criteria/Query dùng property của entity.
- DatabaseClient nhận SQL text và bind value; identifier động trong SQL text phải được kiểm soát thủ công.
- Custom Statement ở R2DBC SPI chịu trách nhiệm SQL, marker và lifecycle connection.

Chọn API phù hợp để giảm số lượng SQL fragment phải tự quản lý.

## 18. Kiểm thử allowlist và SQL injection

Kiểm thử bảo mật nên chứng minh input ngoài allowlist bị từ chối trước khi query được thực thi.

### Unit test parser

~~~java
@Test
void acceptsOnlySupportedSortKeys() {
    assertEquals(
        ProductSortKey.CREATED_AT,
        parser.parseSortKey("created_at")
    );
}

@Test
void rejectsUnknownSortKey() {
    assertThrows(
        InvalidSortFieldException.class,
        () -> parser.parseSortKey("name; DROP TABLE products")
    );
}
~~~

Ví dụ đầu chỉ đúng nếu parser có mapping public key created_at sang CREATED_AT. Quy tắc parse phải được xác định rõ, không tự động nhận mọi cách viết.

### Test hướng sắp xếp

Kiểm tra ASC và DESC được chuyển đúng enum hoặc fragment cố định. Gửi các giá trị như DESC NULLS FIRST, ASC kèm cú pháp phụ hoặc chuỗi tùy ý phải bị từ chối nếu API chỉ hỗ trợ ASC/DESC.

### Test giá trị SQL-looking vẫn là dữ liệu

Một chuỗi như:

~~~text
x' OR '1'='1
~~~

được gửi vào field name hoặc searchText phải được lưu/tìm như một giá trị literal khi bind. Nó không được thay đổi điều kiện SQL.

Integration test có thể insert chuỗi đó bằng bind parameter, sau đó đọc lại và xác nhận nguyên văn.

### Test table routing

- Key CURRENT chọn đúng bảng products.
- Key ARCHIVE chọn đúng bảng products_archive.
- Key ngoài enum bị từ chối.
- Tenant không được phép không thể chọn bảng tenant khác.
- Input chứa ký tự SQL không thể trở thành identifier.

### Test không thay đổi schema

Với integration test trên database dùng riêng, gửi sort/table injection attempt rồi xác nhận query trả lỗi validation và các bảng vẫn tồn tại. Không chạy test phá hoại trên database dùng chung.

## 19. Chuẩn hóa lỗi khi identifier không hợp lệ

Một sort key hoặc table key không được hỗ trợ là lỗi request. Có thể trả 400 Bad Request với error code ổn định:

~~~java
public record ApiError(
    String code,
    String message
) {}
~~~

Ví dụ:

~~~java
@ExceptionHandler(InvalidSortFieldException.class)
public ResponseEntity<ApiError> handleInvalidSort(
        InvalidSortFieldException exception) {

    return ResponseEntity.badRequest().body(
        new ApiError(
            "INVALID_SORT_FIELD",
            "Requested sort field is not supported"
        )
    );
}
~~~

Trong WebFlux, exception handler có thể trả về reactive type nếu cần; các ví dụ dùng ResponseEntity trực tiếp cho response đồng bộ sau khi exception đã phát sinh.

Không trả raw SQL fragment hoặc chi tiết nội bộ của allowlist nếu không cần thiết. Có thể log key đã mask hoặc giá trị đã giới hạn độ dài để hỗ trợ điều tra.

Phân biệt lỗi validation với lỗi database:

- Sort key không hợp lệ: 400.
- Table key không được phép: 400 hoặc 403 tùy semantics API.
- Tenant không có quyền: 403 hoặc 404 theo chính sách chống dò tài nguyên.
- SQL grammar do bug trong fragment cố định: 500 và cảnh báo vận hành.
- Database tạm thời không khả dụng: xử lý theo lỗi hạ tầng.

## 20. Các lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Bind table name bằng :table | Bind marker là value, không phải identifier. | Chọn table từ allowlist. |
| Bind column trong ORDER BY | Có thể sắp xếp theo literal, không phải cột. | Map key sang property/fragment tin cậy. |
| Bind ASC/DESC | Direction là cú pháp SQL. | Dùng enum và switch cố định. |
| Nối sort request vào SQL | Input điều khiển cấu trúc query. | Parse allowlist trước khi tạo SQL. |
| Dùng regex blacklist để làm sạch identifier | Có nhiều cách biểu diễn SQL và identifier. | Dùng allowlist. |
| Chỉ quote raw identifier | Quoting không thay thế authorization/allowlist. | Allowlist rồi quote theo dialect. |
| Dùng tên cột vật lý trong Sort không đúng mapping | Spring Data thường nhận property Java. | Map public key sang entity property. |
| Dùng raw tenant để tạo tên bảng | Có thể route sai tenant hoặc injection. | Tenant registry server-side và authorization. |
| Cho phép mọi filter operator | Operator là cấu trúc SQL. | Enum/map operator cố định. |
| Nối danh sách IN thành CSV | Quote/comma có thể phá cú pháp và injection. | Bind từng phần tử hoặc dùng collection API phù hợp. |
| Sort không có tie-breaker | Pagination có thể không ổn định. | Thêm cột duy nhất như id. |
| Cho client truyền ORDER BY expression | Function/identifier tùy ý làm tăng bề mặt injection. | Allowlist toàn bộ expression. |
| Dùng tên alias do client gửi | Alias cũng là identifier. | Dùng alias cố định từ source code. |

## 21. Quy trình xây dựng query động an toàn

Khi endpoint cần filter, sort hoặc chọn bảng động, hãy theo thứ tự:

1. **Xác định phần nào là value:** dữ liệu người dùng, ngày, số, ID phải được bind.
2. **Liệt kê cấu trúc được phép:** bảng, schema, cột, alias, expression, operator và direction.
3. **Tạo enum/registry:** ánh xạ public key sang property hoặc SQL fragment cố định.
4. **Parse và validate request:** từ chối lựa chọn không hỗ trợ trước khi gọi database.
5. **Dùng API mapping khi phù hợp:** repository Sort, Criteria và Query giúp Spring Data ánh xạ property.
6. **Ghép SQL tối thiểu:** chỉ nối fragment đã được allowlist.
7. **Bind tất cả giá trị:** không nối value vào SQL text.
8. **Kiểm soát collection:** xử lý IN rỗng và giới hạn số bind parameter.
9. **Giới hạn pagination:** page size, offset, số sort field và độ phức tạp filter.
10. **Kiểm tra authorization:** đặc biệt với schema/table theo tenant.
11. **Test input độc hại:** sort key, direction, table key, filter operator và value SQL-looking.
12. **Quan sát query:** log query name/fingerprint và thời gian; không log dữ liệu nhạy cảm.

Kiểm soát identifier động là trách nhiệm của tầng tạo query. Bind parameter bảo vệ giá trị dữ liệu nhưng không thay thế được allowlist cho tên bảng, tên cột, biểu thức sort hoặc hướng sắp xếp. Trong Spring Data R2DBC, ưu tiên Sort/Criteria dựa trên property đã xác thực; khi phải dùng DatabaseClient hoặc SQL tùy chỉnh, chỉ ghép fragment do server định nghĩa và bind toàn bộ value. Kết hợp allowlist với authorization, quoting theo dialect và integration test giúp query động linh hoạt mà vẫn giữ cấu trúc SQL trong tầm kiểm soát.
