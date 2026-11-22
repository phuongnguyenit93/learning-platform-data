# Thiết kế bộ lọc hợp lệ và kiểm soát tên trường do người dùng cung cấp

Trong ứng dụng dùng **Spring Data Relational JDBC (Spring Data JDBC)**, truy vấn động thường bắt đầu từ một màn hình tìm kiếm cho phép người dùng chọn trạng thái, khách hàng, khoảng thời gian, giá trị tối thiểu hoặc cách sắp xếp. Các lựa chọn này được gửi lên server qua query parameters hoặc JSON rồi được chuyển thành điều kiện truy vấn.

Điểm cần kiểm soát là **giá trị lọc** và **tên trường/identifier** có bản chất khác nhau. Giá trị như mã khách hàng hoặc ngày tạo có thể được bind thành tham số SQL. Tên cột, tên property, toán tử và hướng sắp xếp lại quyết định cấu trúc câu truy vấn; chúng phải được chọn từ danh sách mà ứng dụng cho phép. Không đưa trực tiếp tên trường do client gửi vào Criteria, Sort hoặc chuỗi SQL.

Bài này trình bày cách thiết kế filter DTO có kiểu dữ liệu, allowlist trường và toán tử, xây dựng Criteria/Query, tạo SQL động an toàn, xử lý NULL/IN/LIKE, kiểm soát sort và phân trang.

## 1. Tách dữ liệu đầu vào khỏi cấu trúc truy vấn

Giả sử API tìm đơn hàng nhận các lựa chọn:

~~~http
GET /api/orders?status=OPEN&customerId=101&createdFrom=2026-01-01&sortBy=createdAt&direction=DESC&page=0&size=20
~~~

Các giá trị như OPEN, 101 và ngày bắt đầu là **dữ liệu**. Server có thể kiểm tra kiểu, miền giá trị rồi bind chúng vào điều kiện. sortBy=createdAt là một **identifier được yêu cầu**; nó không phải giá trị SQL thông thường. Nếu server nối trực tiếp chuỗi đó vào ORDER BY, client có thể yêu cầu cột hoặc biểu thức ngoài phạm vi ứng dụng cho phép.

Phân biệt ba nhóm:

| Nhóm | Ví dụ client gửi | Cách xử lý |
|---|---|---|
| Giá trị lọc | status=OPEN, customerId=101 | Parse sang kiểu Java, validate rồi bind parameter |
| Tên trường | sortBy=createdAt, field=customerId | Tra cứu allowlist và ánh xạ sang property/cột cố định |
| Toán tử/cách sắp xếp | operator=GTE, direction=DESC | Chuyển thành enum hoặc nhánh code được định nghĩa trước |

~~~mermaid
flowchart TB
    Request["HTTP request<br/>filter, sort, page"]
    Parse["Parse sang DTO có kiểu"]
    Validate["Validate giá trị<br/>field, operator, sort, limits"]
    Allow["Allowlist<br/>field/property/SQL column"]
    Build["Build Criteria hoặc SQL"]
    Bind["Bind các giá trị"]
    DB[("Database")]
    Result["Kết quả truy vấn"]
    Request --> Parse --> Validate --> Allow --> Build --> Bind --> DB --> Result
~~~

Nguyên tắc xuyên suốt: **client được chọn trong những lựa chọn server đã công bố; client không được tự định nghĩa cấu trúc SQL**.

## 2. Vì sao không thể bind tên cột như bind giá trị?

Prepared statement bind giá trị vào vị trí parameter:

~~~sql
SELECT id, status
FROM sales_orders
WHERE status = :status;
~~~

Ở đây :status là chỗ chứa giá trị. JDBC driver gửi giá trị riêng với cấu trúc SQL, vì vậy chuỗi người dùng nhập được xử lý như dữ liệu.

Nhưng parameter không đại diện cho identifier. Ví dụ:

~~~sql
SELECT id, status
FROM sales_orders
ORDER BY :sortColumn;
~~~

Nếu bind sortColumn = 'created_at', database thường hiểu đó là một giá trị hằng được dùng để sắp xếp, không phải tên cột cần sắp xếp. Câu lệnh không thực hiện sort động như mong muốn.

Một cách khác là nối trực tiếp:

~~~java
String sql = "SELECT id, status FROM sales_orders ORDER BY "
    + request.sortBy();
~~~

Cách này nguy hiểm vì client có thể gửi identifier, biểu thức hoặc cú pháp ngoài dự kiến. Bind parameter không thể bảo vệ phần chuỗi đã được nối vào cấu trúc SQL.

Do đó:

- **Giá trị** dùng bind parameter.
- **Identifier** chỉ được chọn từ allowlist phía server.
- **Operator** được chuyển từ enum sang một toán tử cố định.
- **Direction** chỉ nhận ASC hoặc DESC từ enum/nhánh code.

## 3. Thiết kế Filter DTO có kiểu dữ liệu

Nếu màn hình tìm kiếm có một số trường cố định, DTO có kiểu thường dễ hiểu và an toàn hơn một cấu trúc chung chứa field, operator, Object value.

Ví dụ:

~~~java
package com.example.sales.order;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record OrderSearchRequest(
    String status,
    Long customerId,
    LocalDateTime createdFrom,
    LocalDateTime createdTo,
    BigDecimal minimumAmount,
    OrderSortField sortBy,
    SortDirection direction,
    Integer page,
    Integer size
) {}

public enum OrderSortField {
    CREATED_AT,
    STATUS,
    CUSTOMER_ID,
    TOTAL_AMOUNT
}

public enum SortDirection {
    ASC,
    DESC
}
~~~

DTO không nhận tên cột SQL tùy ý. OrderSortField chỉ cho phép các giá trị enum được công bố. Khi client gửi một giá trị không nằm trong enum, framework có thể từ chối request ngay ở bước binding.

### Validate miền giá trị

Một bộ lọc cần kiểm tra ít nhất:

- status thuộc tập trạng thái nghiệp vụ hợp lệ.
- customerId là số dương.
- createdFrom không sau createdTo.
- minimumAmount không âm và không vượt giới hạn nghiệp vụ.
- page không âm.
- size lớn hơn 0 và không vượt kích thước tối đa.
- sortBy và direction nằm trong tập lựa chọn đã công bố.

Ví dụ validation ở service:

~~~java
private static final int DEFAULT_PAGE_SIZE = 20;
private static final int MAX_PAGE_SIZE = 100;

private static int validatedPage(Integer page) {
    int value = page == null ? 0 : page;
    if (value < 0) {
        throw new IllegalArgumentException("Page must be non-negative");
    }
    return value;
}

private static int validatedSize(Integer size) {
    int value = size == null ? DEFAULT_PAGE_SIZE : size;
    if (value < 1 || value > MAX_PAGE_SIZE) {
        throw new IllegalArgumentException(
            "Page size must be between 1 and " + MAX_PAGE_SIZE
        );
    }
    return value;
}

private static void validateDateRange(
        LocalDateTime from,
        LocalDateTime to) {
    if (from != null && to != null && from.isAfter(to)) {
        throw new IllegalArgumentException(
            "createdFrom must not be after createdTo"
        );
    }
}
~~~

Trong ứng dụng Spring MVC, có thể dùng Bean Validation (@Min, @Max, @Positive, @NotNull, validator tùy chỉnh) để đưa lỗi về HTTP 400. Dù kiểm tra ở controller hay service, hãy giữ quy tắc miền giá trị ở một nơi có thể tái sử dụng và không phụ thuộc việc client có dùng đúng giao diện hay không.

## 4. Allowlist tên trường và ánh xạ sang property/cột

Nếu API cần bộ lọc tổng quát, đừng cho client gửi bất kỳ tên property nào trong entity. Hãy định nghĩa enum hoặc map cố định:

~~~java
public enum OrderFilterField {
    STATUS,
    CUSTOMER_ID,
    CREATED_AT,
    TOTAL_AMOUNT
}
~~~

Server quyết định mỗi trường được phép lọc bằng toán tử nào và kiểu dữ liệu gì:

| Field API | Property Java | Cột SQL | Kiểu giá trị | Operator được phép |
|---|---|---|---|---|
| STATUS | status | status | String/enum | EQ, IN |
| CUSTOMER_ID | customerId | customer_id | Long | EQ, IN |
| CREATED_AT | createdAt | created_at | LocalDateTime | GTE, LTE, BETWEEN |
| TOTAL_AMOUNT | totalAmount | total_amount | BigDecimal | GTE, LTE |

Ba tên ở ba lớp có thể khác nhau:

- Tên API là hợp đồng client.
- Property Java là tên dùng trong Criteria/Sort theo mapping Spring Data.
- Cột SQL là identifier dùng trong SQL tùy chỉnh.

Không mặc định rằng chuỗi client gửi có thể dùng trực tiếp ở cả ba nơi.

### Ánh xạ sort bằng switch

~~~java
private static String toOrderProperty(OrderSortField field) {
    return switch (field) {
        case CREATED_AT -> "createdAt";
        case STATUS -> "status";
        case CUSTOMER_ID -> "customerId";
        case TOTAL_AMOUNT -> "totalAmount";
    };
}
~~~

Tên trả về là các property Java đã biết trong source code. Nếu sort field không được cung cấp, dùng mặc định:

~~~java
OrderSortField sortField = request.sortBy() == null
    ? OrderSortField.CREATED_AT
    : request.sortBy();

Sort.Direction direction =
    request.direction() == SortDirection.ASC
        ? Sort.Direction.ASC
        : Sort.Direction.DESC;

Sort sort = Sort.by(
    new Sort.Order(direction, toOrderProperty(sortField)),
    Sort.Order.desc("id")
);
~~~

id là tie-breaker cố định giúp thứ tự ổn định khi nhiều đơn có cùng giá trị ở trường sort chính. Nếu API cho phép sort nhiều trường, hãy giới hạn số lượng, validate từng trường và thêm một khóa duy nhất ở cuối nếu cần thứ tự xác định.

## 5. Dùng Criteria và Query với các trường đã cho phép

Spring Data JDBC cung cấp Criteria và Query để xây dựng điều kiện mà không phải tự nối SQL. Property đưa vào Criteria vẫn là identifier; vì vậy chỉ dùng tên property từ code/allowlist.

Ví dụ DTO có các trường cố định:

~~~java
public record OrderFilter(
    String status,
    Long customerId,
    LocalDateTime createdFrom,
    LocalDateTime createdTo
) {}
~~~

Xây dựng Criteria:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;

public List<Order> search(OrderFilter filter, int page, int size) {
    Criteria criteria = null;

    if (filter.status() != null) {
        criteria = append(criteria,
            Criteria.where("status").is(filter.status()));
    }
    if (filter.customerId() != null) {
        criteria = append(criteria,
            Criteria.where("customerId").is(filter.customerId()));
    }
    if (filter.createdFrom() != null) {
        criteria = append(criteria,
            Criteria.where("createdAt").greaterThanOrEquals(
                filter.createdFrom()));
    }
    if (filter.createdTo() != null) {
        criteria = append(criteria,
            Criteria.where("createdAt").lessThanOrEquals(
                filter.createdTo()));
    }

    Query query = criteria == null
        ? Query.empty()
        : Query.query(criteria);

    query = query
        .sort(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        ))
        .limit(size)
        .offset((long) page * size);

    return StreamSupport.stream(
        template.findAll(query, Order.class).spliterator(), false
    ).toList();
}

private static Criteria append(Criteria current, Criteria next) {
    return current == null ? next : current.and(next);
}
~~~

Đoạn code minh họa cách ghép các điều kiện tùy chọn theo AND. Tên property như status, customerId, createdAt được viết cố định trong server. Nếu muốn cho client chọn trường, phải chuyển giá trị API sang một enum rồi ánh xạ sang property được cho phép trước khi tạo Criteria.

Các method greaterThanOrEquals, lessThanOrEquals, Query.empty, cách overload của Criteria.and và các kiểu trả về cần đối chiếu với phiên bản Spring Data Relational của dự án. Nếu phiên bản đang dùng có API khác, giữ nguyên nguyên tắc allowlist và dùng API tương ứng thay vì truyền chuỗi client trực tiếp.

### Đếm cùng điều kiện

Nếu cần số lượng root thỏa cùng bộ lọc:

~~~java
long count = criteria == null
    ? template.count(Order.class)
    : template.count(Query.query(criteria), Order.class);
~~~

Không cần tải toàn bộ aggregate rồi gọi size() chỉ để đếm. Lưu ý count không có giới hạn trang; nó trả tổng số root thỏa điều kiện.

## 6. Bộ lọc tổng quát: allowlist field, operator và kiểu giá trị

Một API tìm kiếm nâng cao có thể nhận danh sách điều kiện:

~~~json
{
  "filters": [
    { "field": "STATUS", "operator": "IN", "values": ["OPEN", "CONFIRMED"] },
    { "field": "CUSTOMER_ID", "operator": "EQ", "value": 101 },
    { "field": "CREATED_AT", "operator": "GTE", "value": "2026-01-01T00:00:00" }
  ],
  "sort": { "field": "CREATED_AT", "direction": "DESC" },
  "page": 0,
  "size": 20
}
~~~

Không nên dùng Object value rồi tin vào dữ liệu client. Trước khi build query, cần xác thực:

1. field tồn tại trong enum/allowlist.
2. operator được phép cho field đó.
3. value có kiểu tương thích field.
4. Với IN, values là danh sách không rỗng và mỗi phần tử đúng kiểu.
5. Với BETWEEN, có đủ hai đầu mút và thứ tự hợp lệ.
6. Số điều kiện, độ dài chuỗi và kích thước danh sách nằm trong giới hạn.

Ví dụ mô hình operator:

~~~java
public enum FilterOperator {
    EQ, IN, GTE, LTE, BETWEEN, CONTAINS, IS_NULL, IS_NOT_NULL
}
~~~

Một cấu hình server có thể định nghĩa:

~~~java
public record FieldRule(
    String sqlColumn,
    Class<?> valueType,
    Set<FilterOperator> allowedOperators
) {}

private static final Map<OrderFilterField, FieldRule> RULES = Map.of(
    OrderFilterField.STATUS,
    new FieldRule(
        "o.status",
        String.class,
        Set.of(FilterOperator.EQ, FilterOperator.IN)
    ),
    OrderFilterField.CUSTOMER_ID,
    new FieldRule(
        "o.customer_id",
        Long.class,
        Set.of(FilterOperator.EQ, FilterOperator.IN)
    ),
    OrderFilterField.CREATED_AT,
    new FieldRule(
        "o.created_at",
        LocalDateTime.class,
        Set.of(
            FilterOperator.GTE,
            FilterOperator.LTE,
            FilterOperator.BETWEEN
        )
    )
);
~~~

Các chuỗi sqlColumn là hằng số do server định nghĩa. Không đưa giá trị field của request vào sqlColumn.

## 7. Xây dựng SQL động an toàn với NamedParameterJdbcTemplate

Khi cần toán tử linh hoạt, OR phức tạp hoặc truy vấn trên projection, có thể dùng Spring JDBC. Mấu chốt là chỉ nối các mảnh SQL đã được server kiểm soát; mọi giá trị đều bind qua MapSqlParameterSource.

Ví dụ đơn giản cho một điều kiện lọc:

~~~java
private static String columnFor(OrderFilterField field) {
    return switch (field) {
        case STATUS -> "o.status";
        case CUSTOMER_ID -> "o.customer_id";
        case CREATED_AT -> "o.created_at";
        case TOTAL_AMOUNT -> "o.total_amount";
    };
}

private static String operatorSql(FilterOperator operator) {
    return switch (operator) {
        case EQ -> "=";
        case GTE -> ">=";
        case LTE -> "<=";
        default -> throw new IllegalArgumentException(
            "Operator is not supported for this expression");
    };
}
~~~

Builder:

~~~java
List<String> predicates = new ArrayList<>();
MapSqlParameterSource params = new MapSqlParameterSource();

for (int i = 0; i < request.filters().size(); i++) {
    FilterCondition filter = request.filters().get(i);
    FieldRule rule = RULES.get(filter.field());

    if (rule == null ||
            !rule.allowedOperators().contains(filter.operator())) {
        throw new IllegalArgumentException("Unsupported filter");
    }

    String column = columnFor(filter.field());
    String parameter = "p" + i;
    String operator = operatorSql(filter.operator());

    predicates.add(column + " " + operator + " :" + parameter);
    params.addValue(parameter, convertAndValidate(filter, rule));
}

String where = predicates.isEmpty()
    ? ""
    : " WHERE " + String.join(" AND ", predicates);

String sql = """
    SELECT o.id, o.customer_id, o.status, o.created_at
    FROM sales_orders o
    """ + where + """
    ORDER BY o.created_at DESC, o.id DESC
    """;
~~~

Đây là khung minh họa; FilterCondition, convertAndValidate và kiểm tra request cần được triển khai theo DTO/kiểu dữ liệu thực tế. columnFor và operatorSql chỉ trả các chuỗi server đã định nghĩa. Parameter name được tạo bởi server (p0, p1...), còn giá trị được bind.

Không cho phép operator tùy ý như = 1 OR 1=1 -- đi vào operatorSql. Không cho phép field tùy ý như o.status) OR ... đi vào columnFor. Hai điểm này quan trọng ngang với việc bind giá trị.

### IN cần xử lý danh sách

NamedParameterJdbcTemplate có thể mở rộng collection cho mệnh đề IN:

~~~java
predicates.add(column + " IN (:statuses)");
params.addValue("statuses", List.of("OPEN", "CONFIRMED"));
~~~

Danh sách rỗng cần được xử lý trước khi build SQL. Tùy hợp đồng API, có thể từ chối request bằng lỗi validation hoặc trả kết quả rỗng ngay; đừng để SQL IN () được tạo ra vì cú pháp không được hỗ trợ nhất quán giữa các database.

Giới hạn kích thước danh sách để tránh truy vấn có quá nhiều bind parameters. Với danh sách rất lớn, cân nhắc bảng tạm, table-valued parameter (nếu DB hỗ trợ), batch hoặc chiến lược join phù hợp.

## 8. NULL phải có toán tử riêng

Trong SQL, NULL không được so sánh bằng = NULL hoặc <> NULL. Điều kiện đó cho kết quả UNKNOWN, không phải TRUE/FALSE như so sánh thông thường.

Sai:

~~~sql
WHERE shipped_at = NULL
~~~

Đúng:

~~~sql
WHERE shipped_at IS NULL
~~~

Với bộ lọc tổng quát, nên có operator IS_NULL và IS_NOT_NULL không cần value:

~~~java
String predicate = switch (filter.operator()) {
    case IS_NULL -> column + " IS NULL";
    case IS_NOT_NULL -> column + " IS NOT NULL";
    default -> column + " " + operatorSql(filter.operator())
        + " :" + parameter;
};
~~~

Không tạo bind parameter cho IS NULL. Với các operator còn lại, từ chối giá trị null nếu hợp đồng API không định nghĩa rõ ý nghĩa của nó.

Phân biệt:

| Đầu vào | Ý nghĩa |
|---|---|
| Không gửi filter shippedAt | Không thêm điều kiện về shippedAt |
| IS_NULL | Chỉ lấy hàng có shipped_at IS NULL |
| IS_NOT_NULL | Chỉ lấy hàng có shipped_at IS NOT NULL |
| EQ với giá trị ngày | So sánh bằng một thời điểm cụ thể |

Không gộp “không có filter” với “lọc các hàng NULL”; hai yêu cầu này khác nhau.

## 9. LIKE, CONTAINS và ký tự wildcard

Bind parameter ngăn giá trị trở thành cú pháp SQL, nhưng với LIKE, các ký tự % và _ vẫn có ý nghĩa wildcard. Đây không phải SQL injection, nhưng có thể khiến tìm kiếm rộng hơn ý định của người dùng.

Nếu CONTAINS phải tìm chuỗi literal, escape ký tự wildcard trước khi thêm % ở hai đầu. Chọn ký tự escape rõ ràng, ví dụ !:

~~~java
private static String containsPattern(String input) {
    String escaped = input
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
    return "%" + escaped + "%";
}
~~~

SQL:

~~~sql
WHERE c.display_name LIKE :pattern ESCAPE '!'
~~~

Bind:

~~~java
params.addValue("pattern", containsPattern(userInput));
~~~

Nếu sản phẩm muốn người dùng chủ động nhập wildcard, hãy công bố rõ ngữ nghĩa và giới hạn quyền sử dụng. Không nhầm LIKE với tìm kiếm toàn văn; với dữ liệu lớn, %term% thường khó tận dụng B-tree index và có thể cần full-text index/search engine.

## 10. Kiểm soát tên trường sắp xếp

Sort là một nguồn rủi ro phổ biến vì tên cột và ASC/DESC là một phần cấu trúc SQL. Đừng làm:

~~~java
String sql = "SELECT ... ORDER BY "
    + request.sortBy() + " " + request.direction();
~~~

Hãy chuyển request thành enum rồi ánh xạ:

~~~java
private static String sortColumn(OrderSortField field) {
    return switch (field) {
        case CREATED_AT -> "o.created_at";
        case STATUS -> "o.status";
        case CUSTOMER_ID -> "o.customer_id";
        case TOTAL_AMOUNT -> "o.total_amount";
    };
}

private static String sortDirection(SortDirection direction) {
    return switch (direction) {
        case ASC -> "ASC";
        case DESC -> "DESC";
    };
}
~~~

Sau khi xác thực:

~~~java
String orderBy = " ORDER BY "
    + sortColumn(request.sortBy()) + " "
    + sortDirection(request.direction())
    + ", o.id DESC";
~~~

Ở đây chuỗi được nối là các identifier và keyword **được server chọn từ switch**, không phải chuỗi tự do từ client. Giá trị lọc vẫn bind parameter bình thường.

Với Spring Data Sort, cũng cần allowlist property:

~~~java
Sort sort = Sort.by(
    new Sort.Order(direction, toOrderProperty(sortField)),
    Sort.Order.desc("id")
);
~~~

Không truyền trực tiếp Sort.by(request.sortBy()) nếu sortBy là chuỗi tùy ý. Sort có thể nhận property path; cho phép client yêu cầu path không kiểm soát có thể làm lộ trường nội bộ, gây lỗi mapping hoặc tạo truy vấn ngoài ý muốn.

## 11. Không để client chọn property path tùy ý

Một số API cho phép field như:

~~~text
sortBy=customer.address.city
~~~

Property path lồng nhau có thể mở rộng phạm vi truy vấn và làm lộ dữ liệu không dự định cung cấp. Trong Spring Data JDBC, quan hệ aggregate không hoạt động như lazy ORM path tùy ý; tuy nhiên, việc nhận path không giới hạn vẫn là thiết kế API không an toàn và khó bảo trì.

Chỉ công bố những trường cần cho use case. Ví dụ:

| Client key | Property được phép | Có cho sort? |
|---|---|---|
| createdAt | createdAt | Có |
| status | status | Có |
| customerId | customerId | Có |
| internalNote | Không công bố | Không |
| customer.passwordHash | Không công bố | Không |

Không dùng reflection để lấy bất kỳ field nào client yêu cầu (getDeclaredField, BeanWrapper với tên tùy ý) rồi biến nó thành điều kiện truy vấn. Reflection không thay thế allowlist.

## 12. Kết hợp AND/OR và giới hạn độ phức tạp

Một bộ lọc có thể có nhiều điều kiện. Ví dụ:

~~~sql
WHERE status = :status
  AND customer_id = :customerId
  AND (created_at >= :fromTime OR priority = :priority)
~~~

Khi cho phép nhóm AND/OR:

- Định nghĩa cấu trúc filter có giới hạn, không nhận đoạn SQL hoặc biểu thức tùy ý.
- Chỉ cho phép field và operator đã công bố.
- Dùng dấu ngoặc để giữ đúng ý nghĩa logic.
- Giới hạn số điều kiện, số nhóm lồng nhau và độ sâu biểu thức.
- Validate kiểu dữ liệu cho từng field.

Không biến JSON filter thành SQL bằng cách nối trực tiếp field, operator và value. Parser phải chuyển từng node thành cấu trúc đã kiểm tra rồi mới build Criteria/SQL.

Ví dụ mô hình cây đơn giản:

~~~java
public sealed interface FilterNode
        permits FilterGroup, FilterCondition {}

public record FilterGroup(
    LogicalOperator operator,
    List<FilterNode> children
) implements FilterNode {}

public record FilterCondition(
    OrderFilterField field,
    FilterOperator operator,
    Object value
) implements FilterNode {}

public enum LogicalOperator {
    AND, OR
}
~~~

Object value ở ví dụ chỉ là cấu trúc transport tổng quát. Trước khi build query, parser phải chuyển nó sang kiểu cụ thể theo OrderFilterField và từ chối mọi giá trị sai kiểu. Không truyền nguyên object này thẳng vào persistence layer.

## 13. Bộ lọc phải tôn trọng quyền truy cập

Allowlist trường và toán tử bảo vệ cấu trúc truy vấn, nhưng chưa đủ để đảm bảo người dùng chỉ nhìn thấy dữ liệu họ được phép xem.

Ví dụ user chỉ được xem Order thuộc Customer của mình. Server phải bổ sung điều kiện phạm vi truy cập từ danh tính đã xác thực:

~~~java
Criteria criteria = Criteria.where("customerId")
    .is(currentUserCustomerId);

if (filter.status() != null) {
    criteria = criteria.and("status").is(filter.status());
}
~~~

currentUserCustomerId phải được lấy từ security context/session đã xác thực, không tin một giá trị client gửi như customerId để quyết định quyền. Nếu người dùng có quyền xem nhiều Customer, server tải danh sách ID được phép hoặc dùng điều kiện quyền tương ứng.

Quy tắc:

- Bộ lọc do client yêu cầu chỉ thu hẹp tập dữ liệu trong phạm vi được phép.
- Điều kiện tenant/owner phải do server thêm vào.
- Không cho client bỏ qua hoặc ghi đè điều kiện phân quyền.
- Không trả về field nhạy cảm chỉ vì client đưa tên field đó vào danh sách filter/sort.

## 14. Phân trang và kiểm soát tài nguyên

Truy vấn động cần giới hạn số kết quả và bảo đảm sort ổn định:

~~~java
int page = validatedPage(request.page());
int size = validatedSize(request.size());
long offset = (long) page * size;

Query query = Query.query(criteria)
    .sort(sort)
    .limit(size)
    .offset(offset);
~~~

Khi dùng SQL tùy chỉnh, LIMIT/OFFSET hoặc cú pháp phân trang tương ứng phải được xây dựng từ số nguyên đã validate. Dùng long khi tính offset để tránh tràn số nguyên 32 bit.

Các biện pháp kiểm soát khác:

- Giới hạn page size tối đa.
- Giới hạn khoảng ngày tìm kiếm tối đa nếu báo cáo có thể quét lượng dữ liệu lớn.
- Giới hạn số lượng filter và kích thước danh sách IN.
- Đặt timeout truy vấn phù hợp.
- Thêm index dựa trên các điều kiện lọc/sort phổ biến.
- Cân nhắc keyset pagination nếu offset sâu hoặc dữ liệu thay đổi liên tục.

Không cho client yêu cầu một truy vấn không giới hạn chỉ bằng cách bỏ page/size. Hãy xác định default và maximum ở server.

## 15. Một service hoàn chỉnh với bộ lọc cố định

Ví dụ sau dùng JdbcAggregateTemplate và các property cố định. Mục tiêu là minh họa cách kết hợp validation, Criteria và sort allowlist trong một use case:

~~~java
package com.example.sales.order;

import java.util.ArrayList;
import java.util.List;

import org.springframework.data.domain.Sort;
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderSearchService {

    private static final int DEFAULT_SIZE = 20;
    private static final int MAX_SIZE = 100;

    private final JdbcAggregateTemplate template;

    public OrderSearchService(JdbcAggregateTemplate template) {
        this.template = template;
    }

    @Transactional(readOnly = true)
    public List<Order> search(
            String status,
            Long customerId,
            Integer requestedPage,
            Integer requestedSize,
            OrderSortField requestedSort,
            SortDirection requestedDirection) {

        int page = requestedPage == null ? 0 : requestedPage;
        int size = requestedSize == null ? DEFAULT_SIZE : requestedSize;

        if (page < 0) {
            throw new IllegalArgumentException("Invalid page");
        }
        if (size < 1 || size > MAX_SIZE) {
            throw new IllegalArgumentException("Invalid page size");
        }
        if (customerId != null && customerId <= 0) {
            throw new IllegalArgumentException("Invalid customer ID");
        }

        Criteria criteria = null;
        if (status != null) {
            if (!List.of("DRAFT", "OPEN", "CONFIRMED", "CANCELLED")
                    .contains(status)) {
                throw new IllegalArgumentException("Invalid status");
            }
            criteria = append(criteria,
                Criteria.where("status").is(status));
        }
        if (customerId != null) {
            criteria = append(criteria,
                Criteria.where("customerId").is(customerId));
        }

        Sort.Direction direction =
            requestedDirection == SortDirection.ASC
                ? Sort.Direction.ASC
                : Sort.Direction.DESC;

        OrderSortField sortField = requestedSort == null
            ? OrderSortField.CREATED_AT
            : requestedSort;

        String property = switch (sortField) {
            case CREATED_AT -> "createdAt";
            case STATUS -> "status";
            case CUSTOMER_ID -> "customerId";
        };

        Sort sort = Sort.by(
            new Sort.Order(direction, property),
            Sort.Order.desc("id")
        );

        Query query = criteria == null
            ? Query.empty()
            : Query.query(criteria);

        query = query.sort(sort)
            .limit(size)
            .offset((long) page * size);

        Iterable<Order> result = template.findAll(query, Order.class);
        List<Order> orders = new ArrayList<>();
        result.forEach(orders::add);
        return orders;
    }

    private static Criteria append(Criteria current, Criteria next) {
        return current == null ? next : current.and(next);
    }
}
~~~

OrderSortField trong ví dụ chỉ gồm các trường thực sự được cho phép. Nếu entity không có property createdAt, status hoặc customerId tương ứng, phải điều chỉnh enum và mapping theo model thực tế. Ví dụ không nhận tên property tự do từ request.

Nếu ứng dụng cần trả hasNext, tổng số hoặc DTO thay vì List<Order>, hãy xây dựng response phù hợp. Query.limit/offset tự nó không tạo metadata phân trang như Slice/Page.

## 16. Ví dụ SQL động an toàn cho filter và sort

Với báo cáo cần filter field/operator linh hoạt, server có thể tạo mệnh đề SQL từ allowlist:

~~~java
String column = switch (filter.field()) {
    case STATUS -> "o.status";
    case CUSTOMER_ID -> "o.customer_id";
    case CREATED_AT -> "o.created_at";
};

String operator = switch (filter.operator()) {
    case EQ -> "=";
    case GTE -> ">=";
    case LTE -> "<=";
    default -> throw new IllegalArgumentException("Unsupported operator");
};

String parameterName = "filterValue";
String predicate = column + " " + operator + " :" + parameterName;

MapSqlParameterSource parameters = new MapSqlParameterSource()
    .addValue(parameterName, typedValue);

String sortColumn = switch (sortField) {
    case CREATED_AT -> "o.created_at";
    case STATUS -> "o.status";
    case CUSTOMER_ID -> "o.customer_id";
};

String sortDirection = direction == SortDirection.ASC ? "ASC" : "DESC";

String sql = """
    SELECT o.id, o.customer_id, o.status, o.created_at
    FROM sales_orders o
    WHERE %s
    ORDER BY %s %s, o.id DESC
    """.formatted(predicate, sortColumn, sortDirection);
~~~

Trong ví dụ, column, operator, sortColumn và sortDirection đều đến từ switch server-side. typedValue được validate theo field rồi bind vào parameters. Không thay switch bằng filter.field().toString() hoặc request.sortBy().

Nếu dùng nhiều filter, tạo tên parameter do server sinh (p0, p1...) và thêm từng value vào MapSqlParameterSource. Tránh tái sử dụng cùng một tên parameter cho các điều kiện có giá trị khác nhau.

## 17. Kiểm thử bộ lọc và allowlist

Nên kiểm tra cả trường hợp hợp lệ và đầu vào bị từ chối:

| Đầu vào | Kết quả mong đợi |
|---|---|
| status=OPEN | Parse và lọc theo trạng thái OPEN |
| customerId=101 | Parse thành Long và bind |
| sortBy=CREATED_AT | Ánh xạ sang property/cột được cho phép |
| direction=DESC | Chuyển thành hướng sort DESC |
| sortBy=passwordHash | Từ chối do không thuộc allowlist |
| field=customer.passwordHash | Từ chối property path không công bố |
| operator=DROP_TABLE | Từ chối operator không hỗ trợ |
| customerId=abc | Từ chối lỗi parse kiểu |
| page=-1 | Từ chối page âm |
| size=100000 | Từ chối hoặc áp dụng giới hạn theo hợp đồng API |
| IN với danh sách rỗng | Từ chối hoặc trả kết quả rỗng theo quy tắc đã định nghĩa |
| IS_NULL | Sinh điều kiện IS NULL, không bind = NULL |
| Chuỗi LIKE chứa %/_ | Escape nếu hợp đồng là tìm literal |

Một số kiểm thử bảo mật hữu ích:

- Gửi chuỗi giống SQL vào giá trị filter và xác minh nó được bind như dữ liệu.
- Gửi tên cột lạ vào field/sort và xác minh request bị từ chối trước khi tạo SQL.
- Gửi operator không hợp lệ và xác minh không có chuỗi đó trong câu SQL.
- Gửi sort direction khác ASC/DESC và xác minh bị từ chối.
- Gửi filter hợp lệ nhưng thuộc Customer khác quyền truy cập và xác minh điều kiện owner/tenant vẫn được áp dụng.

Không chỉ kiểm thử rằng truy vấn không lỗi; cần xác minh nó không trả về dữ liệu ngoài phạm vi được phép.

## 18. Những lỗi thiết kế thường gặp

| Lỗi | Rủi ro/hệ quả | Cách xử lý |
|---|---|---|
| Nối tên trường client gửi vào SQL | SQL injection qua identifier hoặc truy vấn ngoài dự kiến | Allowlist và ánh xạ bằng enum/switch |
| Bind tên cột bằng :column | Database coi đó là giá trị, không phải identifier | Dùng identifier cố định phía server |
| Dùng Sort.by(request.sortBy()) không kiểm tra | Client có thể yêu cầu property không được công bố | Ánh xạ sort field từ enum |
| Cho operator là chuỗi tự do | Có thể chèn cú pháp SQL | Enum và switch sang toán tử cố định |
| Dùng Object value mà không parse | Sai kiểu, lỗi mapping hoặc logic so sánh sai | Parse theo kiểu field và validate |
| Dùng = NULL | Điều kiện không trả về hàng NULL như mong muốn | Dùng IS NULL/IS NOT NULL |
| IN với danh sách rỗng | SQL không hợp lệ hoặc ngữ nghĩa không rõ | Từ chối hoặc trả rỗng theo hợp đồng |
| Không escape wildcard của LIKE | Kết quả rộng hơn ý định người dùng | Escape %, _ nếu tìm literal |
| Cho phép property path tùy ý | Lộ field nội bộ, truy vấn phức tạp và khó kiểm soát | Công bố field cụ thể trong allowlist |
| Không giới hạn page size/filter count | Tốn tài nguyên hoặc tạo truy vấn quá phức tạp | Đặt giới hạn ở server |
| Tin customerId từ client để phân quyền | Có thể truy cập dữ liệu của người khác | Lấy owner/tenant từ security context |
| Dùng cùng tên API, property và cột mà không mapping | Nhầm lẫn khi đổi schema hoặc domain | Tách key API, property Java và SQL identifier |

## 19. Bài thực hành

1. Tạo OrderSearchRequest gồm status, customerId, khoảng ngày, sort field, direction, page và size.
2. Tạo enum OrderSortField; chỉ cho phép CREATED_AT, STATUS và CUSTOMER_ID.
3. Viết hàm ánh xạ enum sang property Java và dùng Sort với ID làm tie-breaker.
4. Dùng Criteria để thêm điều kiện chỉ khi filter tương ứng có giá trị.
5. Thêm kiểm tra createdFrom <= createdTo, customerId dương và page size tối đa 100.
6. Thiết kế FilterField, FilterOperator và bảng quy tắc cho field/operator/type.
7. Dùng NamedParameterJdbcTemplate để tạo SQL động, chỉ nối identifier/operator từ allowlist và bind toàn bộ value.
8. Bổ sung IN, IS_NULL, IS_NOT_NULL và CONTAINS; định nghĩa rõ hành vi với danh sách rỗng và wildcard.
9. Thử gửi sortBy=customer.passwordHash và xác minh server từ chối.
10. Thử chuỗi SQL trong giá trị filter và xác minh nó chỉ được coi là dữ liệu.
11. Thêm điều kiện tenant/owner lấy từ security context và xác minh client không thể ghi đè.
12. Viết kiểm thử cho filter sai kiểu, operator không hợp lệ, ngày không hợp lệ và page size quá lớn.

## 20. Ghi nhớ

Thiết kế truy vấn động an toàn bắt đầu từ việc phân biệt **giá trị dữ liệu** với **cấu trúc truy vấn**. Giá trị lọc được parse, validate và bind parameter. Tên field, property, cột SQL, operator và sort direction phải được chọn từ allowlist do server định nghĩa.

Với Spring Data JDBC, dùng Criteria/Query khi bộ lọc phù hợp với property mapping của aggregate; dùng NamedParameterJdbcTemplate khi cần SQL động phức tạp hoặc projection riêng. Trong cả hai trường hợp, không truyền trực tiếp tên trường do client gửi vào persistence API. Kết hợp allowlist với kiểm tra kiểu, giới hạn tài nguyên, điều kiện quyền truy cập và xử lý rõ NULL/IN/LIKE để bộ lọc vừa linh hoạt vừa kiểm soát được.
