# Thêm bộ lọc tùy chọn mà không nối chuỗi giá trị SQL

Trong ứng dụng dùng **Spring Data Relational JDBC**, màn hình tìm kiếm thường có nhiều bộ lọc tùy chọn: trạng thái đơn hàng, khách hàng, khoảng ngày, mã đơn hoặc từ khóa. Người dùng có thể chỉ nhập một vài điều kiện, vì vậy câu truy vấn cần thay đổi theo những bộ lọc thực sự được cung cấp.

Cách làm an toàn là **xây dựng cấu trúc câu SQL từ các mệnh đề cố định trong code và truyền giá trị qua bind parameter**. Với Spring JDBC, **NamedParameterJdbcTemplate** cho phép đặt tên tham số như **:status**, **:fromTime** và gắn giá trị riêng. Có thể ghép thêm hoặc bỏ bớt các mệnh đề WHERE, nhưng không được chèn trực tiếp dữ liệu đầu vào vào chuỗi SQL.

Bài học trình bày cách thiết kế bộ lọc tùy chọn, xây dựng câu truy vấn động an toàn, xử lý danh sách IN, tìm kiếm LIKE, sắp xếp và phân trang, cũng như cách lựa chọn giữa derived query, @Query và NamedParameterJdbcTemplate.

## 1. Vì sao bộ lọc tùy chọn cần truy vấn động?

Giả sử màn hình tìm đơn hàng có các trường:

- Trạng thái đơn hàng.
- Mã khách hàng.
- Thời điểm tạo từ ngày.
- Thời điểm tạo đến ngày.
- Một phần mã đơn hàng.

Người dùng có thể tìm theo trạng thái, theo khách hàng, theo ngày hoặc kết hợp nhiều điều kiện. Ví dụ:

| Yêu cầu tìm kiếm | Điều kiện SQL cần có |
|---|---|
| Không nhập bộ lọc | Không có điều kiện bổ sung |
| Chỉ tìm đơn đã gửi | **o.status = :status** |
| Tìm đơn của một khách | **o.customer_id = :customerId** |
| Tìm đơn trong khoảng ngày | **o.created_at >= :fromTime** và **o.created_at < :toTime** |
| Tìm theo trạng thái và khách hàng | Kết hợp hai điều kiện bằng AND |

Nếu viết một câu SQL riêng cho mọi tổ hợp, số lượng truy vấn tăng nhanh. Với năm bộ lọc độc lập, số tổ hợp có thể lên tới \(2^5 = 32\). Khi số điều kiện tăng, cách tạo một truy vấn từ những mệnh đề cố định thường dễ quản lý hơn.

Ví dụ schema:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);
~~~

Truy vấn danh sách đơn có thể bắt đầu bằng:

~~~sql
SELECT
    o.id,
    o.order_number,
    o.customer_id,
    o.status,
    o.created_at
FROM purchase_orders o
~~~

Sau đó ứng dụng thêm các điều kiện phù hợp với bộ lọc đã nhận.

## 2. Phân biệt nối cấu trúc SQL với nối giá trị đầu vào

Có hai việc khác nhau:

1. **Nối cấu trúc SQL:** thêm một mệnh đề cố định do lập trình viên viết, chẳng hạn **AND o.status = :status**.
2. **Nối giá trị dữ liệu:** chèn nội dung người dùng nhập trực tiếp vào câu SQL.

Việc thứ nhất có thể an toàn khi các mảnh SQL là hằng số do ứng dụng kiểm soát. Việc thứ hai tạo nguy cơ SQL injection và lỗi cú pháp.

### 2.1. Cách không an toàn

~~~java
String sql = "SELECT * FROM purchase_orders WHERE status = '"
    + requestedStatus + "'";

List<Map<String, Object>> rows = jdbcTemplate.queryForList(sql);
~~~

Nếu người dùng nhập:

~~~text
' OR '1'='1
~~~

thì câu SQL có thể bị biến đổi thành một điều kiện luôn đúng. Người dùng đã tác động vào **cấu trúc câu lệnh**, thay vì chỉ cung cấp một giá trị tìm kiếm.

Không sửa lỗi bằng cách tự thay dấu nháy đơn, xóa dấu chấm phẩy hoặc lọc một vài ký tự nguy hiểm. Danh sách ký tự có thể khai thác phụ thuộc database và ngữ cảnh SQL; tự escape thủ công rất dễ bỏ sót.

### 2.2. Cách an toàn với bind parameter

~~~java
String sql = """
    SELECT id, order_number, status
    FROM purchase_orders
    WHERE status = :status
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("status", requestedStatus);

List<Map<String, Object>> rows =
    namedParameterJdbcTemplate.queryForList(sql, params);
~~~

Ở đây SQL giữ nguyên cấu trúc. Giá trị requestedStatus được gửi riêng qua cơ chế bind parameter của JDBC driver. Nếu người dùng nhập chuỗi có dấu nháy hoặc ký tự SQL, nó vẫn được xem là dữ liệu của tham số status.

**Quy tắc:** mọi giá trị dữ liệu phải được bind qua ? hoặc named parameter; không nối trực tiếp giá trị đó vào SQL.

## 3. Dùng NamedParameterJdbcTemplate cho các bộ lọc tùy chọn

NamedParameterJdbcTemplate thuộc Spring JDBC. Nó hỗ trợ tham số có tên thay cho placeholder ? theo vị trí, giúp câu SQL và phần gắn dữ liệu dễ đọc hơn.

### 3.1. Khai báo đối tượng bộ lọc

Có thể gom các điều kiện tìm kiếm vào một record:

~~~java
import java.time.LocalDateTime;

public record OrderSearchFilter(
        String status,
        Long customerId,
        LocalDateTime createdFrom,
        LocalDateTime createdTo,
        String orderNumberKeyword
) {
}
~~~

Các trường có thể null nếu người dùng không cung cấp điều kiện. Ở tầng API, có thể chuyển request thành record này sau khi kiểm tra định dạng và quyền truy cập.

Kiểu kết quả cho ví dụ tìm kiếm:

~~~java
import java.time.LocalDateTime;

public record OrderSearchResult(
        Long id,
        String orderNumber,
        Long customerId,
        String status,
        LocalDateTime createdAt
) {
}
~~~

### 3.2. Tạo danh sách mệnh đề và tham số

Ý tưởng:

~~~text
SQL nền
  |
  +-- status có giá trị?       -> thêm "o.status = :status"
  |
  +-- customerId có giá trị?   -> thêm "o.customer_id = :customerId"
  |
  +-- createdFrom có giá trị?  -> thêm "o.created_at >= :createdFrom"
  |
  +-- createdTo có giá trị?    -> thêm "o.created_at < :createdTo"
  |
  +-- keyword có giá trị?      -> thêm "o.order_number LIKE :keyword"
  |
  v
SQL cuối + bộ tham số đã bind
~~~

Các đoạn được thêm vào danh sách là chuỗi SQL cố định do code định nghĩa. Giá trị thật được đặt trong MapSqlParameterSource.

### 3.3. Ví dụ hoàn chỉnh

~~~java
package com.example.orders.read;

import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.List;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderSearchDao {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderSearchDao(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderSearchResult> search(OrderSearchFilter filter) {
        List<String> predicates = new ArrayList<>();
        MapSqlParameterSource params = new MapSqlParameterSource();

        if (filter.status() != null && !filter.status().isBlank()) {
            predicates.add("o.status = :status");
            params.addValue("status", filter.status().trim());
        }

        if (filter.customerId() != null) {
            predicates.add("o.customer_id = :customerId");
            params.addValue("customerId", filter.customerId());
        }

        if (filter.createdFrom() != null) {
            predicates.add("o.created_at >= :createdFrom");
            params.addValue(
                "createdFrom",
                Timestamp.valueOf(filter.createdFrom())
            );
        }

        if (filter.createdTo() != null) {
            predicates.add("o.created_at < :createdTo");
            params.addValue(
                "createdTo",
                Timestamp.valueOf(filter.createdTo())
            );
        }

        if (filter.orderNumberKeyword() != null
                && !filter.orderNumberKeyword().isBlank()) {
            predicates.add("o.order_number LIKE :keyword ESCAPE '!'");
            params.addValue(
                "keyword",
                "%" + escapeLike(filter.orderNumberKeyword().trim()) + "%"
            );
        }

        StringBuilder sql = new StringBuilder("""
            SELECT
                o.id,
                o.order_number,
                o.customer_id,
                o.status,
                o.created_at
            FROM purchase_orders o
            """);

        if (!predicates.isEmpty()) {
            sql.append(" WHERE ")
               .append(String.join(" AND ", predicates));
        }

        sql.append(" ORDER BY o.created_at DESC, o.id DESC");

        return jdbc.query(sql.toString(), params, (rs, rowNum) ->
            new OrderSearchResult(
                rs.getLong("id"),
                rs.getString("order_number"),
                rs.getLong("customer_id"),
                rs.getString("status"),
                rs.getTimestamp("created_at").toLocalDateTime()
            )
        );
    }

    private static String escapeLike(String value) {
        return value
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
    }
}
~~~

Với SQL trong ví dụ, mệnh đề **ESCAPE '!'** dùng ký tự ! làm ký tự escape cho LIKE. Hàm escapeLike xử lý ký tự escape trước, sau đó mới escape % và _. Nếu sản phẩm muốn cho phép wildcard do người dùng nhập, không escape hai ký tự đó; hãy định nghĩa rõ semantics tìm kiếm.

Các class OrderSearchResult và OrderSearchFilter là DTO của ví dụ. Câu SQL có thể được điều chỉnh theo schema, kiểu timestamp và database cụ thể. Trong code thực tế, có thể bind LocalDateTime trực tiếp nếu driver và cấu hình mapping hỗ trợ; ví dụ dùng Timestamp.valueOf để thể hiện kiểu JDBC cho cột TIMESTAMP.

### 3.4. Vì sao cách này an toàn?

- Tên cột và toán tử trong predicate là chuỗi cố định do code định nghĩa.
- status, customerId, thời gian và keyword được truyền qua named parameter.
- Giá trị người dùng không thể biến thành một phần cú pháp SQL.
- Mỗi điều kiện chỉ xuất hiện khi bộ lọc tương ứng được cung cấp.
- Nếu không có bộ lọc nào, query vẫn hợp lệ vì phần WHERE được bỏ qua.

Được phép ghép các **mệnh đề SQL tin cậy** để tạo cấu trúc động. Điều cần tránh là ghép dữ liệu đầu vào vào các mệnh đề đó.

## 4. Một cách khác: câu SQL cố định với điều kiện tham số NULL

Với số lượng bộ lọc ít và cố định, có thể giữ nguyên một câu SQL:

~~~sql
SELECT id, order_number, customer_id, status, created_at
FROM purchase_orders
WHERE (:status IS NULL OR status = :status)
  AND (:customerId IS NULL OR customer_id = :customerId)
  AND (:createdFrom IS NULL OR created_at >= :createdFrom)
  AND (:createdTo IS NULL OR created_at < :createdTo)
ORDER BY created_at DESC, id DESC;
~~~

Khi tham số là NULL, vế đầu của mỗi điều kiện đúng và bộ lọc đó được bỏ qua. Khi tham số có giá trị, vế so sánh áp dụng.

Ví dụ bind bằng MapSqlParameterSource:

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("status", status, java.sql.Types.VARCHAR)
    .addValue("customerId", customerId, java.sql.Types.BIGINT)
    .addValue("createdFrom", createdFrom, java.sql.Types.TIMESTAMP)
    .addValue("createdTo", createdTo, java.sql.Types.TIMESTAMP);
~~~

Khai báo SQL type rõ ràng có thể giúp driver/database xử lý tham số NULL có kiểu. Nếu dùng Map.of, không thể đưa giá trị null vào map; dùng MapSqlParameterSource hoặc một map có hỗ trợ null.

### 4.1. Ưu điểm và giới hạn

| Ưu điểm | Giới hạn |
|---|---|
| Chỉ có một câu SQL cố định | Mỗi điều kiện có biểu thức OR dù bộ lọc không dùng |
| Không cần ghép danh sách predicate | Optimizer có thể khó tận dụng index với một số dạng OR |
| Dễ hiểu với vài bộ lọc đơn giản | Bind NULL cần type phù hợp với driver |
| Dễ giữ query ở annotation @Query | Không phù hợp khi có nhiều điều kiện tùy chọn hoặc nhiều kiểu lọc |

Đây là lựa chọn hợp lý cho một truy vấn nhỏ, ít bộ lọc. Với màn hình tìm kiếm có nhiều điều kiện và cần kiểm soát hiệu năng, cách ghép các predicate cố định thường linh hoạt hơn.

## 5. Dùng @Query trong repository khi tập bộ lọc đơn giản

Nếu truy vấn gắn với aggregate root và số điều kiện tùy chọn ít, có thể khai báo SQL bằng @Query:

~~~java
public interface OrderHeaderProjection {
    Long getId();
    String getOrderNumber();
    Long getCustomerId();
    String getStatus();
    LocalDateTime getCreatedAt();
}

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT id, customer_id, order_number, status, created_at
        FROM purchase_orders
        WHERE (:status IS NULL OR status = :status)
          AND (:customerId IS NULL OR customer_id = :customerId)
        ORDER BY created_at DESC, id DESC
        """)
    List<OrderHeaderProjection> searchHeaders(
        @Param("status") String status,
        @Param("customerId") Long customerId
    );
}
~~~

Đây là mẫu minh họa cho query có điều kiện tùy chọn và bind parameter. Kiểu projection chỉ khai báo các cột header mà câu SELECT trả về. Một câu SELECT chỉ lấy header không nên được coi là cách tải đầy đủ aggregate có collection con. Với kết quả tìm kiếm màn hình, projection hoặc DTO thường thể hiện đúng mục đích hơn.

Nếu truy vấn cần nhiều bộ lọc, danh sách động, sort tùy chọn hoặc phép tính báo cáo, NamedParameterJdbcTemplate thường cho phép tổ chức SQL và mapping kết quả rõ ràng hơn.

## 6. Bộ lọc danh sách bằng IN

Một bộ lọc thường gặp là trạng thái có thể nhận nhiều giá trị:

~~~sql
WHERE o.status IN (:statuses)
~~~

NamedParameterJdbcTemplate hỗ trợ mở rộng named parameter khi giá trị là collection:

~~~java
Set<String> statuses = Set.of("DRAFT", "SUBMITTED");

String sql = """
    SELECT id, order_number, status
    FROM purchase_orders
    WHERE status IN (:statuses)
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("statuses", statuses);

List<OrderHeader> rows = jdbc.query(sql, params, orderHeaderMapper);
~~~

Template sẽ tạo số placeholder tương ứng với số phần tử. Các giá trị vẫn được bind riêng; không cần tự tạo chuỗi 'DRAFT','SUBMITTED'.

### 6.1. Phải quyết định ý nghĩa của collection rỗng

Có ba trường hợp cần phân biệt:

| Đầu vào | Ý nghĩa nên định nghĩa |
|---|---|
| statuses == null | Người dùng không dùng bộ lọc trạng thái |
| statuses có phần tử | Chỉ lấy các trạng thái được chọn |
| statuses.isEmpty() | Có thể hiểu là không chọn trạng thái nào, hoặc không áp dụng bộ lọc; phải quyết định rõ |

Không truyền collection rỗng vào IN (:statuses) rồi kỳ vọng mọi database xử lý giống nhau. Một số dialect không chấp nhận IN (); hành vi mở rộng collection rỗng còn phụ thuộc phiên bản/framework.

Nếu quy ước collection rỗng nghĩa là không có kết quả, trả List.of() ngay trước khi chạy SQL. Nếu quy ước rỗng nghĩa là bỏ qua bộ lọc, không thêm predicate. Hai lựa chọn có ý nghĩa khác nhau và cần nhất quán với giao diện.

## 7. Tìm kiếm LIKE và wildcard

Bind parameter ngăn SQL injection, nhưng không thay đổi ý nghĩa của wildcard trong LIKE.

~~~sql
WHERE order_number LIKE :keyword
~~~

Nếu bind giá trị %2026%, database hiểu % là “không hoặc nhiều ký tự”. Nếu người dùng muốn tìm đúng dấu % hoặc _ trong dữ liệu, cần escape wildcard theo cú pháp của database:

~~~sql
WHERE order_number LIKE :keyword ESCAPE '!'
~~~

Trong Java:

~~~java
private static String toContainsPattern(String input) {
    String escaped = input
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
    return "%" + escaped + "%";
}
~~~

Đây là escape **ngữ nghĩa tìm kiếm LIKE**, không phải biện pháp thay thế bind parameter. Vẫn phải bind chuỗi kết quả qua :keyword.

Một số điểm cần thống nhất:

- Tìm chính xác: order_number = :orderNumber.
- Tìm tiền tố: order_number LIKE :pattern với pattern kết thúc bằng %.
- Tìm chuỗi con: pattern có % ở cả hai đầu.
- Không phân biệt hoa thường: phụ thuộc collation hoặc có thể dùng LOWER(column) = LOWER(:value); cần cân nhắc index.

LIKE với wildcard ở đầu chuỗi như %abc% thường khó tận dụng B-tree index thông thường. Với dữ liệu lớn, cân nhắc full-text search hoặc loại index phù hợp với database.

## 8. Sắp xếp động mà không nối input vào SQL

Bind parameter chỉ dùng cho **giá trị**, không thể thay thế tên cột hoặc từ khóa SQL:

~~~sql
ORDER BY :sortColumn
~~~

không có nghĩa là database sẽ lấy tên cột từ giá trị tham số. Nó thường được hiểu như sắp xếp theo một giá trị hằng hoặc không có semantics mong muốn.

Không làm như sau:

~~~java
String sql = "SELECT id, order_number FROM purchase_orders ORDER BY "
    + request.sortBy();
~~~

Người dùng có thể gửi một biểu thức SQL tùy ý vào sortBy.

### 8.1. Dùng whitelist cho identifier và direction

Ánh xạ tên sort công khai sang các identifier do code kiểm soát:

~~~java
private static final Map<String, String> SORT_COLUMNS = Map.of(
    "createdAt", "o.created_at",
    "orderNumber", "o.order_number",
    "status", "o.status"
);

private static String resolveSortColumn(String requestedSort) {
    return SORT_COLUMNS.getOrDefault(requestedSort, "o.created_at");
}

private static String resolveDirection(String requestedDirection) {
    if (requestedDirection == null) {
        return "DESC";
    }

    return switch (requestedDirection.toUpperCase(Locale.ROOT)) {
        case "ASC" -> "ASC";
        case "DESC" -> "DESC";
        default -> throw new IllegalArgumentException(
            "Sort direction phải là ASC hoặc DESC");
    };
}
~~~

Sau khi xác thực:

~~~java
String sql = """
    SELECT o.id, o.order_number, o.status, o.created_at
    FROM purchase_orders o
    ORDER BY
    """ + resolveSortColumn(requestedSort)
        + " " + resolveDirection(requestedDirection)
        + ", o.id DESC";
~~~

Đoạn ghép chuỗi này an toàn vì identifier và direction chỉ có thể đến từ whitelist cố định. Không đưa nguyên giá trị request vào SQL.

Luôn thêm một khóa phụ duy nhất như id để thứ tự phân trang ổn định khi nhiều hàng có cùng giá trị sort.

## 9. Phân trang với tham số đã bind

Với database hỗ trợ cú pháp LIMIT và OFFSET:

~~~sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :pageSize OFFSET :offset;
~~~

pageSize và offset là giá trị số nên có thể bind như các tham số khác. Nhưng phải kiểm tra giới hạn ở application layer:

~~~java
if (page < 0) {
    throw new IllegalArgumentException("page không được âm");
}
if (pageSize < 1 || pageSize > 100) {
    throw new IllegalArgumentException("pageSize phải từ 1 đến 100");
}

long offset = Math.multiplyExact((long) page, pageSize);
params.addValue("pageSize", pageSize);
params.addValue("offset", offset);
~~~

Không cho client yêu cầu page size không giới hạn, vì có thể gây truy vấn tốn tài nguyên. Cú pháp phân trang thay đổi giữa database; ví dụ trên dùng dialect có LIMIT/OFFSET.

Với trang rất sâu, OFFSET lớn có thể tốn chi phí. Có thể dùng keyset pagination:

~~~sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = :status
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

Cursor gồm thời gian và ID cuối trang trước. Các giá trị cursor vẫn được bind; thứ tự cột trong ORDER BY là hằng số do ứng dụng định nghĩa.

## 10. Kết hợp điều kiện AND và OR có chủ đích

Khi có nhiều lựa chọn, cần dùng dấu ngoặc để giữ đúng logic. Ví dụ tìm đơn có trạng thái DRAFT hoặc SUBMITTED, đồng thời thuộc một khách hàng:

~~~sql
WHERE o.customer_id = :customerId
  AND (o.status = :statusA OR o.status = :statusB)
~~~

Hoặc dùng IN:

~~~sql
WHERE o.customer_id = :customerId
  AND o.status IN (:statuses)
~~~

Đừng nối điều kiện theo thứ tự tùy tiện rồi bỏ ngoặc. Trong SQL, AND có độ ưu tiên cao hơn OR; thiếu ngoặc có thể khiến một điều kiện lọc bị áp dụng sai.

Ví dụ sai ý định:

~~~sql
WHERE customer_id = :customerId
  AND status = 'DRAFT'
   OR status = 'SUBMITTED'
~~~

SQL trên có thể trả mọi đơn SUBMITTED của khách hàng khác. Dùng ngoặc hoặc IN để diễn đạt chính xác.

## 11. Phân biệt null, chuỗi rỗng và không gửi bộ lọc

API tìm kiếm thường cần một quy ước rõ cho đầu vào:

| Đầu vào | Cách xử lý thường gặp |
|---|---|
| Không gửi field | Bỏ qua bộ lọc |
| Field có giá trị | Áp dụng điều kiện |
| Chuỗi chỉ có khoảng trắng | Chuẩn hóa thành không có bộ lọc hoặc từ chối |
| Giá trị null tường minh | Xác định có nghĩa là bỏ lọc hay tìm cột NULL |
| Muốn tìm hàng có cột NULL | Dùng điều kiện column IS NULL riêng |

Không thể dùng một tham số null để đồng thời biểu đạt hai ý nghĩa: “không áp dụng filter” và “chỉ lấy hàng có giá trị cột là NULL”. Nếu cần tìm giá trị NULL, hãy thêm một lựa chọn riêng trong filter hoặc một predicate rõ ràng:

~~~sql
o.optional_note IS NULL
~~~

Đối với trường hợp bộ lọc có thể yêu cầu tìm NULL, có thể dùng enum/boolean như NoteFilter.ANY, NULL_ONLY, VALUE_ONLY để phân biệt các trạng thái thay vì dựa vào một giá trị String null.

## 12. Khi nào dùng derived query, @Query hay NamedParameterJdbcTemplate?

| Cách | Phù hợp khi | Giới hạn |
|---|---|---|
| Derived query | Một vài tổ hợp điều kiện phổ biến, dễ diễn đạt bằng tên method | Nhiều tổ hợp tùy chọn có thể làm số method tăng nhanh |
| @Query | Câu SQL cố định, ít bộ lọc, gắn với repository | Không thuận tiện khi cần ghép số lượng predicate tùy biến lớn |
| NamedParameterJdbcTemplate | Nhiều bộ lọc tùy chọn, danh sách IN, sort và pagination động | Cần tự quản lý cấu trúc SQL và ánh xạ DTO |
| SQL chuyên biệt hoặc query builder | Truy vấn phức tạp, có nhiều loại điều kiện | Cần thêm abstraction và kiểm soát chặt nguồn SQL |

Spring Data JDBC không cung cấp cùng bộ Criteria API/Specification của Spring Data JPA. Nếu cần truy vấn động phức tạp, không nên giả định có thể lấy nguyên JpaSpecificationExecutor hoặc JPA Criteria rồi dùng trực tiếp với Spring Data JDBC.

Một số method derived query có thể đủ:

~~~java
List<PurchaseOrder> findByStatus(String status);

List<PurchaseOrder> findByCustomerIdAndStatus(
    Long customerId,
    String status
);
~~~

Nhưng nếu có hàng loạt filter độc lập, NamedParameterJdbcTemplate thường giúp biểu diễn rõ hơn mà không phải khai báo mọi tổ hợp method.

## 13. Tối ưu hiệu năng của truy vấn động

Truy vấn động an toàn vẫn cần được tối ưu theo workload. Một số lưu ý:

- Thêm predicate chỉ khi filter có giá trị hợp lệ.
- Dùng điều kiện so sánh trực tiếp trên cột khi có thể, ví dụ created_at >= :fromTime.
- Tránh bọc cột trong hàm như DATE(created_at) nếu muốn tận dụng index thông thường; thay bằng khoảng thời gian phù hợp.
- Dùng index dựa trên điều kiện WHERE và ORDER BY thực tế.
- Giới hạn page size.
- Tránh SELECT * nếu chỉ cần một số cột.
- Xem execution plan với những tổ hợp filter thường gặp.

Ví dụ tìm theo trạng thái và thời gian có thể được hỗ trợ bởi index:

~~~sql
CREATE INDEX idx_orders_status_created
    ON purchase_orders(status, created_at, id);
~~~

Đây chỉ là một phương án minh họa. Thứ tự cột trong composite index cần dựa trên tính chọn lọc của điều kiện, thứ tự sort và database cụ thể. Mỗi index cũng làm tăng chi phí ghi và dung lượng lưu trữ.

### 13.1. OR với tham số NULL có thể ảnh hưởng execution plan

Truy vấn cố định:

~~~sql
WHERE (:status IS NULL OR status = :status)
~~~

đơn giản về code, nhưng biểu thức OR có thể khiến optimizer khó dùng index hiệu quả trong một số database hoặc với một số phân bố dữ liệu. Query động chỉ thêm:

~~~sql
WHERE status = :status
~~~

khi filter được cung cấp có thể giúp optimizer có điều kiện rõ hơn. Hãy đo cả hai cách bằng execution plan và dữ liệu đại diện; không có quy tắc hiệu năng tuyệt đối cho mọi database.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| SQL injection qua status hoặc keyword | Nối giá trị người dùng vào SQL | Dùng named parameter |
| Không lọc khi chuỗi rỗng | Chỉ kiểm tra null | Chuẩn hóa chuỗi rỗng/blank theo quy ước |
| Query lỗi với IN () | Truyền collection rỗng | Quy định semantics và xử lý trước khi chạy SQL |
| Sort có thể chèn SQL | Nối trực tiếp tên cột từ request | Dùng whitelist identifier và direction |
| LIKE tìm wildcard ngoài ý muốn | % và _ có ý nghĩa đặc biệt | Escape wildcard nếu cần tìm literal |
| Không dùng được bind parameter cho tên cột | Parameter chỉ đại diện giá trị | Whitelist tên cột trong code |
| Kết quả phân trang không ổn định | ORDER BY không có khóa phụ duy nhất | Thêm ID vào thứ tự |
| Truy vấn chậm khi filter bị bỏ qua | Dùng OR với tham số null hoặc thiếu index | So sánh query động và query cố định bằng execution plan |
| Lỗi kiểu khi bind null | Driver cần biết SQL type | Dùng MapSqlParameterSource.addValue kèm Types phù hợp |
| Bộ lọc ngày bỏ sót dữ liệu cuối ngày | Dùng hai đầu mút inclusive với độ chính xác không rõ | Dùng khoảng nửa mở >= from và < to |
| Điều kiện OR làm lọt hàng ngoài phạm vi | Thiếu ngoặc | Nhóm biểu thức bằng ngoặc hoặc dùng IN |

## 15. Bài tập thực hành

### Bài 1 — Bộ lọc cơ bản

1. Tạo OrderSearchFilter gồm status, customerId, createdFrom và createdTo.
2. Dùng NamedParameterJdbcTemplate.
3. Chỉ thêm predicate khi field tương ứng có giá trị.
4. Bind mọi giá trị qua MapSqlParameterSource.
5. Thử tìm chỉ theo status, chỉ theo customer và kết hợp cả hai.

### Bài 2 — Bộ lọc danh sách

1. Thêm filter nhiều trạng thái bằng IN (:statuses).
2. Thử đầu vào null, collection rỗng và collection có phần tử.
3. Quy định rõ semantics cho từng trường hợp.
4. Xác nhận không phát sinh IN ().

### Bài 3 — Tìm kiếm LIKE

1. Thêm tìm mã đơn theo chuỗi con.
2. Bind giá trị có %, _ và ký tự escape.
3. Thêm ESCAPE và hàm escape literal.
4. Phân biệt tìm literal với tìm kiếm wildcard.

### Bài 4 — Sắp xếp và phân trang

1. Cho phép sort theo ngày, mã đơn hoặc trạng thái.
2. Ánh xạ lựa chọn sort qua whitelist.
3. Chỉ chấp nhận ASC hoặc DESC.
4. Bind page size và offset.
5. Thêm ID làm khóa phụ để giữ thứ tự ổn định.

### Bài 5 — So sánh hai cách triển khai

1. Viết truy vấn cố định với (:status IS NULL OR status = :status).
2. Viết truy vấn động chỉ thêm status = :status khi có filter.
3. Chạy cả hai với cùng dữ liệu và điều kiện.
4. Xem execution plan và so sánh thời gian.
5. Ghi lại trade-off về độ đơn giản và khả năng tận dụng index.

## 16. Kết luận

Để thêm bộ lọc tùy chọn an toàn, hãy **ghép các mệnh đề SQL cố định trong code và bind toàn bộ giá trị bằng parameter**. NamedParameterJdbcTemplate là lựa chọn linh hoạt khi có nhiều filter, danh sách IN, khoảng thời gian, sort và phân trang. Với vài điều kiện đơn giản, một câu SQL cố định dùng (:parameter IS NULL OR column = :parameter) hoặc repository @Query cũng có thể phù hợp.

Chỉ tên cột, hướng sort hoặc cấu trúc SQL mới cần được chọn từ whitelist; chúng không thể bind như giá trị thông thường. Xử lý rõ null, chuỗi rỗng, collection rỗng và wildcard của LIKE. Cuối cùng, kiểm tra execution plan để chọn giữa query cố định và query được ghép predicate.

Điều cốt lõi là giá trị tìm kiếm luôn được gửi riêng với câu SQL. Cấu trúc truy vấn do ứng dụng kiểm soát, còn dữ liệu đầu vào chỉ quyết định giá trị của các tham số đã khai báo.
