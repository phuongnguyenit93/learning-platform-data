# Bảo đảm tính nhất quán giữa trang dữ liệu và tổng đếm

Một API phân trang thường trả về hai loại thông tin: danh sách bản ghi của trang hiện tại và tổng số bản ghi thỏa điều kiện lọc. Ví dụ giao diện hiển thị “21–40 trên 327 sản phẩm”. Trong Spring Data Relational R2DBC, danh sách thường được lấy bằng query có LIMIT/OFFSET hoặc keyset cursor, còn tổng số được lấy bằng query COUNT riêng.

Hai query này có thể nhìn thấy hai trạng thái dữ liệu khác nhau nếu có INSERT, UPDATE hoặc DELETE xảy ra giữa chúng. Khi đó response có thể chứa một trang gồm 20 hàng nhưng total count không khớp với tập dữ liệu mà trang đó đại diện. Vấn đề còn rõ hơn khi người dùng chuyển qua nhiều trang trong lúc dữ liệu thay đổi.

Để bảo đảm tính nhất quán, trước hết cần định nghĩa “nhất quán” có nghĩa gì đối với API: danh sách và tổng đếm phải phản ánh cùng một snapshot trong một response, hay toàn bộ hành trình duyệt nhiều trang phải nhìn thấy cùng một tập dữ liệu? Hai yêu cầu này cần những chiến lược khác nhau. Bài học này trình bày cách đồng bộ filter/order, transaction isolation, single-statement count, offset/keyset pagination và các lựa chọn khi dữ liệu thay đổi liên tục.

## 1. Một response phân trang gồm những gì?

Một response theo page number thường có:

~~~json
{
  "items": [
    { "id": 101, "name": "Keyboard" },
    { "id": 102, "name": "Mouse" }
  ],
  "page": 5,
  "size": 20,
  "totalElements": 327,
  "totalPages": 17,
  "hasNext": true
}
~~~

Các trường có ý nghĩa:

| Trường | Ý nghĩa |
|---|---|
| items | Các hàng thuộc trang hiện tại |
| page | Chỉ số trang, thường bắt đầu từ 0 |
| size | Số hàng tối đa được yêu cầu |
| totalElements | Tổng số hàng thỏa filter |
| totalPages | Số trang theo page size |
| hasNext | Có trang tiếp theo hay không |

Với page number, offset thường được tính:

$$
offset = page \times size
$$

Và tổng số trang:

$$
totalPages = \left\lceil \frac{totalElements}{size} \right\rceil
$$

Khi totalElements bằng 0, totalPages bằng 0. Nếu page size không hợp lệ, API nên từ chối hoặc chuẩn hóa theo hợp đồng đã công bố.

Với keyset pagination, response thường dùng cursor:

~~~json
{
  "items": [
    { "id": 101, "name": "Keyboard" },
    { "id": 102, "name": "Mouse" }
  ],
  "nextCursor": 102,
  "hasNext": true
}
~~~

Keyset pagination không nhất thiết cung cấp totalElements. Cursor và total count là hai khái niệm độc lập; chỉ thêm tổng đếm khi sản phẩm thực sự cần nó.

## 2. Vì sao query lấy trang và query COUNT có thể lệch nhau?

Một cách triển khai phổ biến là chạy hai statement:

~~~sql
SELECT id, name, price
FROM product
WHERE active = TRUE
ORDER BY id
LIMIT 20 OFFSET 100;
~~~

~~~sql
SELECT COUNT(*)
FROM product
WHERE active = TRUE;
~~~

Giả sử bảng có 327 sản phẩm active khi query trang chạy. Ngay sau đó, một request khác thêm 5 sản phẩm active. Query COUNT có thể trả 332. Response lúc này ghép một page được đọc từ trạng thái trước với total count được đọc từ trạng thái sau.

Các tình huống tương tự:

- Một hàng bị xóa sau query trang nhưng trước query COUNT: total có thể thấp hơn tập mà page vừa đọc.
- Một hàng được chuyển từ inactive sang active giữa hai query: page và count nhìn thấy các tập khác nhau.
- Một hàng bị cập nhật cột filter: nó có thể chuyển vào hoặc ra khỏi tập kết quả.
- Một request khác thêm/xóa hàng ở phía trước OFFSET: vị trí hàng trên trang tiếp theo có thể thay đổi.

Sự lệch này không nhất thiết là lỗi database. Nó là hệ quả của việc các statement quan sát dữ liệu ở những thời điểm khác nhau theo transaction isolation đang dùng.

## 3. Điều kiện đầu tiên: COUNT và page phải dùng cùng filter

Trước khi xét transaction, hai query phải định nghĩa cùng một tập dữ liệu.

Ví dụ API lọc theo trạng thái active và tên:

~~~sql
SELECT id, name, price
FROM product
WHERE active = :active
  AND name ILIKE :pattern
ORDER BY id
LIMIT :size OFFSET :offset;
~~~

Query đếm phải áp dụng cùng điều kiện:

~~~sql
SELECT COUNT(*)
FROM product
WHERE active = :active
  AND name ILIKE :pattern;
~~~

Nếu query page lọc theo tenant, quyền truy cập, soft-delete hoặc trạng thái mà query count bỏ sót, totalElements sẽ sai ngay cả khi cả hai statement chạy trên cùng snapshot.

Một nguyên tắc dễ kiểm tra là định nghĩa tập kết quả trước:

~~~text
Tập dữ liệu D =
    các hàng được phép nhìn thấy
    AND chưa bị soft-delete
    AND thỏa filter nghiệp vụ

Page  = lấy một đoạn có thứ tự từ D
Count = đếm số hàng trong D
~~~

COUNT và page cần cùng:

- Tenant/ownership scope.
- Authorization filter.
- Soft-delete condition.
- Search/filter parameters.
- Join condition.
- Quy tắc distinct/grouping.

### 3.1. Chú ý join làm nhân bản hàng

Nếu query page join bảng con, một product có thể xuất hiện nhiều lần:

~~~sql
SELECT p.id, p.name, c.id AS category_id
FROM product p
JOIN product_category c ON c.product_id = p.id
WHERE c.category_id IN (:categoryIds)
ORDER BY p.id;
~~~

Nếu API hiển thị mỗi product một lần, query count cần đếm product duy nhất:

~~~sql
SELECT COUNT(DISTINCT p.id)
FROM product p
JOIN product_category c ON c.product_id = p.id
WHERE c.category_id IN (:categoryIds);
~~~

COUNT(*) đếm số hàng sau join, không nhất thiết là số entity gốc. Với query có GROUP BY, cần xác định total là số nhóm hay số hàng nguồn. Ý nghĩa total phải trùng với đơn vị mà API trả về trong items.

### 3.2. COUNT(*) và COUNT(column)

COUNT(*) đếm mọi hàng. COUNT(column) bỏ qua hàng có giá trị NULL ở cột đó. Nếu cần tổng số bản ghi, COUNT(*) thường là biểu thức rõ ràng hơn.

Với projection có thể tạo duplicate, dùng COUNT(DISTINCT primary_key) khi semantics yêu cầu đếm entity duy nhất. Không chọn COUNT(DISTINCT) theo thói quen nếu query đã bảo đảm một hàng cho mỗi entity; phép distinct có thể làm query tốn tài nguyên hơn.

### 3.3. Không để count tiết lộ dữ liệu bị giới hạn quyền

Nếu danh sách chỉ trả hàng thuộc tenant hiện tại nhưng count đếm toàn bảng, API có thể làm lộ số lượng dữ liệu của tenant khác. Count phải áp cùng authorization scope như query page.

## 4. Thứ tự sắp xếp phải xác định và ổn định

Pagination cần một thứ tự xác định. Nếu sort theo cột không duy nhất, các hàng có cùng giá trị có thể đổi vị trí giữa những lần chạy query.

Không nên chỉ:

~~~sql
SELECT id, name
FROM product
ORDER BY created_at
LIMIT :size OFFSET :offset;
~~~

Nếu nhiều hàng có cùng created_at, database không có nghĩa vụ giữ một thứ tự phụ ổn định giữa chúng. Hãy thêm khóa duy nhất làm tie-breaker:

~~~sql
SELECT id, name, created_at
FROM product
ORDER BY created_at, id
LIMIT :size OFFSET :offset;
~~~

Với keyset pagination, cursor phải chứa đủ giá trị sort để xác định vị trí duy nhất. Nếu sort theo created_at rồi id, điều kiện cursor phải so sánh cả hai trường theo cùng thứ tự.

Thứ tự ổn định giải quyết vấn đề nondeterministic ordering tại một snapshot. Nó không tự ngăn page drift khi dữ liệu bị INSERT/DELETE/UPDATE giữa các request.

## 5. PostgreSQL READ COMMITTED và snapshot của từng statement

PostgreSQL mặc định dùng isolation level READ COMMITTED. Ở mức này, mỗi statement nhìn thấy một snapshot gồm các thay đổi đã commit trước khi statement bắt đầu.

Điều đó có nghĩa hai query liên tiếp trong cùng transaction READ COMMITTED vẫn có thể nhìn thấy hai trạng thái khác nhau:

~~~text
Transaction A                         Transaction B
-------------                         -------------
BEGIN
SELECT page
  -> nhìn thấy 100 hàng
                                      INSERT product
                                      COMMIT
SELECT COUNT(*)
  -> nhìn thấy 101 hàng
COMMIT
~~~

Vì vậy, chỉ bọc query page và query COUNT trong cùng một transaction mặc định chưa đủ để bảo đảm chúng dùng cùng snapshot trên PostgreSQL READ COMMITTED.

### 5.1. READ COMMITTED vẫn phù hợp với nhiều API

Nếu dữ liệu thay đổi thường xuyên và API chấp nhận total là số liệu gần thời điểm đọc, READ COMMITTED có thể là lựa chọn hợp lý. Nó có concurrency tốt và không giữ snapshot dài như REPEATABLE READ.

Điều quan trọng là công bố semantics: total là số đếm tại thời điểm query count, không phải cam kết bất biến trong suốt quá trình người dùng duyệt nhiều trang.

## 6. Dùng REPEATABLE READ cho count và page trong cùng response

Trong PostgreSQL, REPEATABLE READ giữ một transaction snapshot ổn định cho các statement trong cùng transaction. Khi query COUNT và query page chạy tuần tự trong transaction này, cả hai nhìn thấy cùng trạng thái dữ liệu.

Luồng:

~~~text
BEGIN ISOLATION LEVEL REPEATABLE READ
    |
    v
SELECT COUNT(*) ...  ----+
                         |
                         +-- cùng snapshot
                         |
SELECT ... LIMIT/OFFSET -+
    |
    v
COMMIT
~~~

Đây là cách phù hợp khi một response cần total count chính xác theo cùng snapshot với items.

### 6.1. Cấu hình TransactionalOperator với isolation level

Có thể tạo operator riêng cho thao tác đọc cần snapshot:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.reactive.TransactionalOperator;
import org.springframework.transaction.support.DefaultTransactionDefinition;

@Configuration
public class PaginationTransactionConfiguration {

    @Bean
    TransactionalOperator repeatableReadOperator(
            ReactiveTransactionManager transactionManager) {

        DefaultTransactionDefinition definition =
            new DefaultTransactionDefinition();
        definition.setReadOnly(true);
        definition.setIsolationLevel(
            TransactionDefinition.ISOLATION_REPEATABLE_READ
        );
        definition.setName("pagination-count-and-page");

        return TransactionalOperator.create(
            transactionManager,
            definition
        );
    }
}
~~~

Bean này giả định application dùng một reactive transaction manager tương ứng với R2DBC ConnectionFactory. Nếu có nhiều database/transaction manager, cần chỉ định đúng manager cho pool chứa dữ liệu đang phân trang.

### 6.2. Chạy COUNT và page trong cùng transaction

Ví dụ dùng DatabaseClient với filter active:

~~~java
import java.util.List;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public record ProductRow(Long id, String name) {
}

public record ProductPage(
    List<ProductRow> items,
    int page,
    int size,
    long totalElements,
    long totalPages
) {
}

@Repository
public class ProductPaginationRepository {

    private final DatabaseClient databaseClient;
    private final TransactionalOperator repeatableReadOperator;

    public ProductPaginationRepository(
            DatabaseClient databaseClient,
            TransactionalOperator repeatableReadOperator) {
        this.databaseClient = databaseClient;
        this.repeatableReadOperator = repeatableReadOperator;
    }

    public Mono<ProductPage> findActivePage(
            int page,
            int size) {

        long offset = Math.multiplyExact((long) page, size);

        Mono<Long> countQuery = databaseClient.sql("""
                SELECT COUNT(*)
                FROM product
                WHERE active = TRUE
                """)
            .map((row, metadata) -> row.get(0, Long.class))
            .one()
            .defaultIfEmpty(0L);

        Mono<List<ProductRow>> pageQuery = databaseClient.sql("""
                SELECT id, name
                FROM product
                WHERE active = TRUE
                ORDER BY id
                LIMIT :size OFFSET :offset
                """)
            .bind("size", size)
            .bind("offset", offset)
            .map((row, metadata) -> new ProductRow(
                row.get("id", Long.class),
                row.get("name", String.class)
            ))
            .all()
            .collectList();

        Mono<ProductPage> result = countQuery.flatMap(total ->
            pageQuery.map(items -> new ProductPage(
                items,
                page,
                size,
                total,
                total == 0 ? 0 : (total + size - 1) / size
            ))
        );

        return result.as(repeatableReadOperator::transactional);
    }
}
~~~

Hai publisher được compose tuần tự: COUNT hoàn tất rồi mới chạy query page. Cả hai nằm trong cùng subscription do TransactionalOperator quản lý. Trên PostgreSQL REPEATABLE READ, chúng dùng cùng transaction snapshot.

Không dùng Mono.zip(countQuery, pageQuery) một cách mặc định khi cả hai query cần chạy trên cùng một connection transaction. Mono.zip subscribe cả hai nhánh cùng lúc; nhiều R2DBC driver/connection không hỗ trợ thực thi hai statement đồng thời trên một connection theo cách mà code có thể giả định. Compose tuần tự bằng flatMap dễ hiểu và tương thích hơn.

### 6.3. Vì sao readOnly không tự bảo đảm snapshot?

readOnly là hint/thuộc tính transaction, không tự động nâng isolation level. Nếu chỉ đặt readOnly=true nhưng database vẫn dùng READ COMMITTED, mỗi statement vẫn có snapshot riêng. Cần chỉ định isolation level phù hợp và xác nhận transaction manager/driver áp dụng nó.

### 6.4. Cẩn thận với transaction kéo dài

REPEATABLE READ giữ snapshot trong suốt transaction. Giữ transaction lâu có thể làm tăng thời gian giữ connection và khiến PostgreSQL phải giữ lại phiên bản row cũ cần thiết cho snapshot. Vì vậy:

- Chỉ bao trùm hai query ngắn cần nhất quán.
- Không stream toàn bộ response qua một transaction dài nếu không cần.
- Không gọi HTTP service hoặc chờ client trong transaction này.
- Không dùng một transaction snapshot cho hành trình người dùng duyệt nhiều trang trong nhiều phút.

## 7. Dùng một SQL statement để lấy page và total cùng snapshot

Một cách khác là tính tổng bằng window function trong cùng statement:

~~~sql
SELECT
    id,
    name,
    price,
    COUNT(*) OVER() AS total_elements
FROM product
WHERE active = TRUE
ORDER BY id
LIMIT :size OFFSET :offset;
~~~

COUNT(*) OVER() tính tổng số hàng trong tập sau WHERE và gắn total_elements vào mỗi hàng được trả. Vì page và count thuộc cùng một statement, chúng nhìn thấy cùng statement snapshot mà không cần transaction bao quanh hai query riêng.

Ưu điểm:

- Không có khoảng thời gian giữa query count và query page.
- Không cần transaction nhiều statement chỉ để đồng bộ hai kết quả.
- Có thể lấy total từ hàng đầu tiên trong page.

Hạn chế:

- Nếu offset vượt quá cuối tập kết quả, query không trả hàng nào; khi đó không có hàng để đọc total_elements.
- Window count thường vẫn phải xét toàn bộ tập hàng thỏa filter, nên LIMIT không làm phép đếm trở thành miễn phí.
- Nếu query join làm nhân bản hàng, window count có thể đếm số hàng sau join; cần thiết kế tập đầu vào đúng đơn vị.
- Mapping phải đọc total_elements từ mỗi row hoặc từ row đầu tiên.

### 7.1. Ví dụ mapping window count

~~~java
public record ProductWithTotal(
    Long id,
    String name,
    Long totalElements
) {
}

public Flux<ProductWithTotal> findActivePage(
        int size,
        long offset) {

    return databaseClient.sql("""
            SELECT id, name, COUNT(*) OVER() AS total_elements
            FROM product
            WHERE active = TRUE
            ORDER BY id
            LIMIT :size OFFSET :offset
            """)
        .bind("size", size)
        .bind("offset", offset)
        .map((row, metadata) -> new ProductWithTotal(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("total_elements", Long.class)
        ))
        .all();
}
~~~

Service có thể lấy totalElements từ phần tử đầu tiên rồi tạo page response. Vì mọi hàng trong cùng result có cùng total, không cần tính lại ở từng phần tử.

Nếu page rỗng, cần chính sách riêng. Có thể trả total bằng 0 nếu API định nghĩa page ngoài phạm vi là empty mà không cần số đếm chính xác; hoặc chạy count riêng trong một REPEATABLE READ transaction; hoặc dùng một query CTE/LEFT JOIN để vẫn trả tổng dù page rỗng.

### 7.2. CTE/LEFT JOIN để có total ngay cả khi page rỗng

PostgreSQL có thể tính total và page trong một statement rồi LEFT JOIN để luôn có một hàng tổng:

~~~sql
WITH totals AS (
    SELECT COUNT(*) AS total_elements
    FROM product
    WHERE active = TRUE
),
page_rows AS (
    SELECT id, name, price
    FROM product
    WHERE active = TRUE
    ORDER BY id
    LIMIT :size OFFSET :offset
)
SELECT
    page_rows.id,
    page_rows.name,
    page_rows.price,
    totals.total_elements
FROM totals
LEFT JOIN page_rows ON TRUE
ORDER BY page_rows.id;
~~~

Statement luôn có một hàng từ totals. Nếu page_rows rỗng, các cột page_rows là NULL nhưng total_elements vẫn có giá trị. Mapper cần phân biệt sentinel row này với product thật, ví dụ kiểm tra id null rồi không thêm item vào list.

Hai CTE cùng thuộc một statement snapshot. PostgreSQL có thể tối ưu/in-line CTE tùy phiên bản và cấu trúc query; không nên mặc định CTE luôn materialize. Hãy kiểm tra EXPLAIN trên dữ liệu thực tế.

## 8. Chọn giữa hai query trong transaction và một query window

| Tiêu chí | COUNT + page trong REPEATABLE READ | COUNT(*) OVER() |
|---|---|---|
| Snapshot | Cùng transaction snapshot | Cùng statement snapshot |
| Số statement | Hai | Một |
| Page rỗng | COUNT vẫn có giá trị | Window không trả hàng chứa total |
| Cấu trúc query | Dễ tách count/page và tái sử dụng | Gọn trong một SQL nhưng cần mapping tổng |
| Transaction | Cần reactive transaction | Không cần transaction chỉ để đồng bộ count/page |
| Chi phí | Hai lần statement, count vẫn phải đếm | Window count vẫn phải xét tập kết quả |
| Phù hợp | Repository/service cần tách query | API page cần total và page trong một statement |

Không có lựa chọn nào luôn nhanh hơn. Hãy benchmark với filter, index và kích thước dữ liệu thật. Nếu total count chính xác không cần thiết, bỏ count thường là tối ưu đơn giản nhất.

## 9. Count và page phải thống nhất filter động

Trong API thật, filter có thể tùy chọn: active, category, từ khóa, giá tối thiểu/tối đa. Cần bảo đảm cả hai query nhận cùng giá trị và semantics.

Ví dụ với active là bắt buộc:

~~~java
Mono<Long> countProducts(boolean active) {
    return databaseClient.sql("""
            SELECT COUNT(*)
            FROM product
            WHERE active = :active
            """)
        .bind("active", active)
        .map((row, metadata) -> row.get(0, Long.class))
        .one()
        .defaultIfEmpty(0L);
}
~~~

Với tham số tùy chọn có thể null, R2DBC DatabaseClient không nên được gọi bằng bind(name, null). Dùng bindNull(name, JavaType.class) hoặc xây dựng query/criteria phù hợp.

Ví dụ ý tưởng:

~~~java
DatabaseClient.GenericExecuteSpec spec = databaseClient.sql(sql);

if (active == null) {
    spec = spec.bindNull("active", Boolean.class);
} else {
    spec = spec.bind("active", active);
}
~~~

Điều kiện SQL kiểu:

~~~sql
WHERE (:active IS NULL OR active = :active)
~~~

có thể thuận tiện nhưng OR với tham số tùy chọn đôi khi làm planner khó chọn index tối ưu. Với workload lớn, cân nhắc tạo các query shape rõ ràng theo filter hiện có hoặc dùng Spring Data Criteria/Query builder để tạo predicate nhất quán.

### 9.1. Tránh copy-paste filter khác nhau giữa count và page

Khi filter thay đổi, rất dễ cập nhật query page nhưng quên query count. Có thể giảm rủi ro bằng:

- Một hàm build criteria dùng chung cho hai query.
- Một repository method nhận một object filter bất biến.
- Một SQL CTE chung khi dùng một statement.
- Integration test so sánh count với số hàng trong fixture đã biết.

Nếu tự nối fragment SQL, chỉ nối các fragment cố định do code tạo; không nối trực tiếp input từ client.

### 9.2. Filter authorization phải giống nhau

Ví dụ multi-tenant:

~~~sql
WHERE tenant_id = :tenantId
  AND deleted_at IS NULL
  AND active = :active
~~~

Cả count và page phải dùng cùng tenantId lấy từ security context đã xác thực, cùng soft-delete condition và cùng filter active. Không nhận tenantId từ query parameter rồi tin cậy trực tiếp nếu authorization yêu cầu tenant lấy từ principal.

## 10. Offset pagination và page drift

Offset pagination dễ triển khai:

~~~sql
SELECT id, name
FROM product
WHERE active = TRUE
ORDER BY id
LIMIT :size OFFSET :offset;
~~~

Nhưng vị trí hàng được xác định theo số lượng hàng đứng trước nó. Nếu có INSERT hoặc DELETE trước offset giữa hai request, page tiếp theo có thể chứa duplicate hoặc bỏ sót hàng so với hành trình ban đầu.

Ví dụ:

~~~text
Trước khi đọc page 1:
IDs: 10, 20, 30, 40, 50, 60
size = 3

Page 1 (offset 0): 10, 20, 30

Một hàng mới ID 15 được INSERT.
Thứ tự mới: 10, 15, 20, 30, 40, 50, 60

Page 2 (offset 3): 30, 40, 50
                         ^^
                    ID 30 bị lặp
~~~

Nếu có DELETE trước offset, page tiếp theo có thể bỏ qua một hàng. Stable ORDER BY giúp thứ tự xác định tại mỗi snapshot, nhưng không ngăn các vị trí thay đổi giữa snapshot.

### 10.1. Total count có thể thay đổi giữa các page

Ngay cả khi count và page của từng response nhất quán, totalElements ở page 1 và page 2 có thể khác nhau nếu dữ liệu thay đổi giữa hai HTTP request. Đây là hành vi bình thường khi mỗi request dùng snapshot mới.

Nếu UI hiển thị tổng số cố định trong suốt hành trình, cần định nghĩa một snapshot/cutoff hoặc chấp nhận total là giá trị tham khảo tại thời điểm bắt đầu.

## 11. Keyset pagination giảm page drift do INSERT ở phía trước

Keyset pagination dùng khóa cuối của page trước:

~~~sql
SELECT id, name
FROM product
WHERE active = TRUE
  AND id > :afterId
ORDER BY id
LIMIT :size;
~~~

Nếu page đầu trả ID 10, 20, 30 thì cursor là 30. Một hàng mới có ID 15 được thêm sau đó sẽ không đẩy các hàng sau cursor sang vị trí offset khác; page kế tiếp vẫn bắt đầu từ id > 30.

Keyset thường phù hợp cho:

- Bảng lớn và duyệt tuần tự.
- Feed hoặc danh sách mới nhất/cũ nhất.
- Export theo batch.
- API không cần nhảy trực tiếp tới page number bất kỳ.

Keyset không tự giữ snapshot của dữ liệu. Hàng sau cursor vẫn có thể bị xóa hoặc đổi filter; hàng đã đọc có thể bị cập nhật; một hàng mới có khóa nhỏ hơn cursor có thể không được nhìn thấy trong lượt duyệt hiện tại.

### 11.1. Cursor nhiều cột

Nếu thứ tự là created_at rồi id:

~~~sql
SELECT id, name, created_at
FROM product
WHERE active = TRUE
  AND (created_at, id) > (:afterCreatedAt, :afterId)
ORDER BY created_at, id
LIMIT :size;
~~~

Row-value comparison như trên phù hợp PostgreSQL với các cột có semantics so sánh tương thích. Khi có sort direction DESC, nullable sort key hoặc nhiều cột phức tạp, phải thiết kế điều kiện cursor tương ứng, bao gồm quy tắc NULLS FIRST/LAST.

### 11.2. Total count với keyset

Keyset page chỉ cần truy vấn hàng tiếp theo và có thể lấy thêm một hàng để biết hasNext:

~~~sql
SELECT id, name
FROM product
WHERE active = TRUE
  AND id > :afterId
ORDER BY id
LIMIT :sizePlusOne;
~~~

Nếu nhận size + 1 hàng, có trang tiếp theo. Bỏ hàng thừa trước khi trả response và dùng ID cuối cùng trong số size hàng thực sự trả về làm cursor.

Nếu cần totalElements, query COUNT phải đếm toàn bộ tập filter, không chỉ phần hàng sau cursor. Không thêm điều kiện id > afterId vào count trừ khi API định nghĩa total là “số hàng còn lại sau cursor”.

Đây là điểm cần ghi rõ trong API:

- totalElements: tổng số hàng trong toàn bộ tập filter.
- remainingElements: số hàng còn lại sau cursor.

Hai giá trị không giống nhau.

## 12. Bảo đảm snapshot xuyên nhiều HTTP request

REPEATABLE READ chỉ giữ snapshot trong vòng đời transaction. Nếu client gọi page 1, chờ 10 giây rồi gọi page 2 bằng request khác, transaction của request đầu thường đã kết thúc. Request thứ hai sẽ có snapshot mới.

Không nên giữ một transaction và connection database mở xuyên nhiều HTTP request hoặc trong suốt thời gian người dùng duyệt UI. Cách này:

- Giữ connection lâu và làm giảm pool capacity.
- Giữ MVCC snapshot lâu, có thể cản trở cleanup row version cũ ở PostgreSQL.
- Khó xử lý client bỏ trang, mất mạng hoặc mở nhiều tab.
- Tạo state phía server cần quản lý và hết hạn.

Nếu toàn bộ quá trình cần thấy cùng một tập dữ liệu, hãy chọn một mô hình snapshot phù hợp thay vì giữ transaction mở qua nhiều request.

### 12.1. Snapshot bằng cutoff cho dữ liệu append-only

Nếu bảng chủ yếu append-only và ID tăng đơn điệu, có thể lấy max ID tại lúc bắt đầu:

~~~sql
SELECT COALESCE(MAX(id), 0)
FROM product
WHERE active = TRUE;
~~~

Gọi giá trị đó là snapshotMaxId. Mọi page sau dùng:

~~~sql
SELECT id, name
FROM product
WHERE active = TRUE
  AND id <= :snapshotMaxId
  AND id > :afterId
ORDER BY id
LIMIT :size;
~~~

Điều kiện snapshotMaxId ngăn các hàng mới có ID lớn hơn mốc ban đầu xuất hiện ở những page sau. Đây là kỹ thuật hữu ích cho dữ liệu append-only hoặc khi yêu cầu chỉ cần loại trừ INSERT mới.

Nó không phải snapshot database đầy đủ:

- Hàng cũ vẫn có thể bị DELETE.
- Hàng cũ có thể được UPDATE để vào/ra filter.
- ID được cấp trước nhưng transaction commit muộn có thể xuất hiện sau khi max ID đã được lấy, tùy cách cấp ID và thứ tự commit.
- Các thay đổi ở bảng liên quan có thể làm kết quả join đổi.

Vì vậy, mô tả rõ cutoff chỉ cố định phạm vi khóa, không bảo đảm toàn bộ nội dung row bất biến.

### 12.2. Snapshot theo thời gian hoặc version nghiệp vụ

Nếu dữ liệu có created_at bất biến, có thể lưu asOf timestamp ở request đầu và áp dụng:

~~~sql
WHERE created_at <= :asOf
  AND id > :afterId
~~~

Điều kiện này loại bỏ phần lớn hàng được tạo sau mốc thời gian. Nhưng nó không giữ lại giá trị cũ khi hàng hiện có bị update hoặc delete. Muốn tái dựng trạng thái tại một thời điểm, schema cần lưu lịch sử/version hoặc dùng cơ chế temporal/audit phù hợp.

### 12.3. Materialized snapshot/export job

Với báo cáo hoặc export cần một tập dữ liệu cố định:

1. Tạo export job.
2. Chốt tập ID hoặc ghi snapshot vào bảng staging/materialized result.
3. Worker xử lý snapshot theo batch.
4. Lưu cursor/checkpoint để tiếp tục.
5. Trả file hoặc kết quả khi hoàn tất.
6. Xóa snapshot theo TTL/retention policy.

Cách này tăng chi phí lưu trữ và công việc chuẩn bị nhưng tách vòng đời snapshot khỏi HTTP connection. Nó phù hợp hơn với báo cáo lớn so với giữ một transaction dài.

## 13. Chọn semantics total count

Không phải API nào cũng cần total chính xác. Có thể chọn một trong các semantics:

| Semantics | Mô tả | Phù hợp |
|---|---|---|
| Exact per response | Items và total cùng snapshot trong một response | Trang quản trị cần tổng chính xác |
| Current count | Count phản ánh thời điểm query count | Danh sách thay đổi thường xuyên, UI chấp nhận cập nhật |
| As-of count | Total theo cutoff/version được xác định | Duyệt dữ liệu có mốc thời gian |
| Approximate count | Số ước lượng, không bảo đảm chính xác | Dataset rất lớn, dashboard/analytics |
| No total | Chỉ trả items, cursor và hasNext | Feed, infinite scroll, export |

Hợp đồng API nên ghi rõ semantics. Nếu field tên totalElements nhưng thực chất là approximate, cần đặt tên/metadata rõ hơn để client không hiển thị như số đếm chính xác.

### 13.1. Exact count có chi phí

Trên PostgreSQL, COUNT(*) chính xác cần xác định số hàng thỏa predicate theo visibility rules của MVCC. Với bảng lớn, phép đếm có thể cần đọc nhiều page/index entry hoặc dữ liệu bảng; không nên giả định nó là O(1).

Index phù hợp có thể giúp query filter/count, nhưng không phải lúc nào cũng loại bỏ toàn bộ công việc. Kiểm tra:

- Execution plan.
- Số hàng ước lượng và số hàng thực tế.
- Buffer hit/read.
- Thời gian query.
- Tần suất gọi count.

Nếu total count trở thành bottleneck, cân nhắc bỏ total, dùng hasNext, cache count có TTL, approximate count hoặc bảng counter được duy trì theo nghiệp vụ.

### 13.2. Approximate count trong PostgreSQL

PostgreSQL lưu thống kê ước lượng số hàng trong catalog như reltuples, được cập nhật bởi ANALYZE/VACUUM và có thể cũ. Có thể dùng thống kê này cho dashboard hoặc ước lượng, nhưng không dùng như total chính xác cho hợp đồng API cần số đếm tuyệt đối.

Ước lượng theo điều kiện filter phức tạp còn khó hơn tổng số hàng của bảng. Nếu dùng approximate count, hãy trả metadata cho biết đây là ước lượng và thời điểm cập nhật.

## 14. Đếm trước hay lấy page trước?

Thứ tự thực thi không tự giải quyết consistency nếu isolation vẫn READ COMMITTED. Tuy nhiên, nó ảnh hưởng latency và cách xử lý page ngoài phạm vi.

### 14.1. Count trước rồi page

Ưu điểm:

- Có total ngay cả khi page vượt quá cuối tập.
- Có thể từ chối page number quá lớn nếu API muốn.

Nhược điểm:

- Người dùng phải chờ count trước khi nhận page.
- Nếu count chậm, toàn bộ response chậm.
- Ở READ COMMITTED, page chạy sau vẫn có snapshot khác.

### 14.2. Page trước rồi count

Ưu điểm:

- Có thể phát hiện page rỗng sớm.
- Một số API có thể trả items trước nếu dùng streaming response, dù total lúc đó chưa có.

Nhược điểm:

- Count vẫn cần chạy nếu response yêu cầu total.
- Cùng vấn đề snapshot nếu hai statement không cùng snapshot.

### 14.3. Chọn dựa trên contract và query plan

Nếu response cần items và total cùng lúc, dùng một statement window count hoặc transaction REPEATABLE READ. Nếu không cần total, chỉ lấy page và hasNext. Nếu count là phần đắt nhất, cân nhắc cache/approximate count hoặc bỏ total.

## 15. Tạo response Page an toàn

Một DTO có thể là:

~~~java
import java.util.List;

public record PageResponse<T>(
    List<T> items,
    int page,
    int size,
    long totalElements,
    long totalPages,
    boolean hasNext
) {
    public static <T> PageResponse<T> of(
            List<T> items,
            int page,
            int size,
            long totalElements) {

        long totalPages = totalElements == 0
            ? 0
            : (totalElements + size - 1) / size;

        return new PageResponse<>(
            List.copyOf(items),
            page,
            size,
            totalElements,
            totalPages,
            (long) page + 1 < totalPages
        );
    }
}
~~~

Tính totalPages bằng long để tránh overflow khi tổng dữ liệu lớn. Trước khi tính offset, dùng long và kiểm tra overflow:

~~~java
long offset = Math.multiplyExact((long) page, size);
~~~

Không tính page * size bằng int nếu page có thể lớn. Hãy validate page >= 0 và size trong khoảng cho phép trước khi tạo query.

### 15.1. Page number ngoài phạm vi

Nếu totalElements là 327 và size là 20, totalPages là 17, page index hợp lệ từ 0 tới 16. Khi client yêu cầu page 20, API có thể:

- Trả items rỗng nhưng vẫn có totalElements/totalPages.
- Trả 404/400 theo hợp đồng API.

Thông thường trả 200 với items rỗng giúp client xử lý danh sách dễ hơn, nhưng lựa chọn phải nhất quán và được tài liệu hóa.

## 16. Không dùng total count để suy ra hasNext nếu không cần

Nếu API chỉ cần biết còn trang tiếp theo, có thể query size + 1 hàng:

~~~sql
SELECT id, name
FROM product
WHERE active = TRUE
  AND id > :afterId
ORDER BY id
LIMIT :sizePlusOne;
~~~

Nếu có hơn size hàng:

1. Đặt hasNext = true.
2. Bỏ hàng thừa ở cuối.
3. Tạo cursor từ hàng cuối cùng được trả về.

Ví dụ code:

~~~java
import java.util.List;

public record ProductRow(Long id, String name) {
}

public record CursorPage<T>(
    List<T> items,
    Long nextAfterId,
    boolean hasNext
) {
}

public Mono<CursorPage<ProductRow>> findNext(
        long afterId,
        int size) {

    return databaseClient.sql("""
            SELECT id, name
            FROM product
            WHERE active = TRUE
              AND id > :afterId
            ORDER BY id
            LIMIT :limit
            """)
        .bind("afterId", afterId)
        .bind("limit", size + 1)
        .map((row, metadata) -> new ProductRow(
            row.get("id", Long.class),
            row.get("name", String.class)
        ))
        .all()
        .collectList()
        .map(rows -> {
            boolean hasNext = rows.size() > size;
            List<ProductRow> items = hasNext
                ? List.copyOf(rows.subList(0, size))
                : List.copyOf(rows);

            Long next = items.isEmpty()
                ? null
                : items.get(items.size() - 1).id();

            return new CursorPage<>(items, next, hasNext);
        });
}
~~~

Ở đây collectList chỉ giữ tối đa size + 1 phần tử vì SQL có LIMIT và size đã được validate. Nếu size có thể rất lớn, giới hạn đầu vào trước khi cộng 1.

Đây là cách tránh COUNT chính xác trên mỗi request khi giao diện chỉ cần nút “Load more” hoặc “Next”.

## 17. Count query với Spring Data R2DBC

ReactiveCrudRepository không tự động cung cấp một Page<T> với total count theo cách giống repository đồng bộ truyền thống. Một Flux chỉ đại diện cho luồng kết quả; để tạo PageResponse, ứng dụng cần định nghĩa cách lấy total và items.

Có thể dùng DatabaseClient:

~~~java
Mono<Long> countActiveProducts() {
    return databaseClient.sql("""
            SELECT COUNT(*)
            FROM product
            WHERE active = TRUE
            """)
        .map((row, metadata) -> row.get(0, Long.class))
        .one()
        .defaultIfEmpty(0L);
}
~~~

one() phát một giá trị hoặc empty nếu không có row. COUNT aggregate thông thường luôn trả một row, kể cả khi count bằng 0; defaultIfEmpty vẫn có thể được dùng như bảo vệ cho mapper/implementation.

### 17.1. Không dùng count của toàn bảng cho page đã lọc

Nếu page lọc active = true, count phải lọc active = true. Nếu page áp tenant scope, count cũng áp tenant scope. Không gọi repository.count() không điều kiện rồi gắn vào một page đã lọc.

### 17.2. Filter object bất biến

Với nhiều điều kiện, gom input thành một object:

~~~java
import java.math.BigDecimal;

public record ProductFilter(
    Boolean active,
    String nameContains,
    BigDecimal minPrice,
    BigDecimal maxPrice,
    Long tenantId
) {
}
~~~

Service chuẩn hóa filter một lần, sau đó truyền cùng object cho count và page query. Không tự tạo hai object filter riêng có thể lệch giá trị.

## 18. Kiểm thử tính nhất quán giữa count và page

Unit test với mock có thể xác nhận service ghép đúng total và items, nhưng không kiểm tra MVCC snapshot hoặc isolation của PostgreSQL. Những đặc tính này cần integration test với database thật.

### 18.1. Test cùng filter

Seed một tập sản phẩm có active/inactive và category khác nhau. Gọi API với filter, sau đó xác nhận:

- Items chỉ chứa hàng thỏa filter.
- totalElements bằng số entity duy nhất thỏa cùng filter.
- Page tiếp theo dùng cùng filter.
- Tenant/soft-delete scope được áp dụng ở cả count và page.

### 18.2. Test count/page dưới READ COMMITTED

Có thể tạo hai connection/transaction:

~~~text
Transaction A (READ COMMITTED)       Transaction B
--------------------------------     ----------------------------
BEGIN
SELECT COUNT(*) -> 10
                                     INSERT product
                                     COMMIT
SELECT page -> có thể thấy 11 hàng
COMMIT
~~~

Test cần điều phối bằng latch/barrier để INSERT commit đúng giữa hai statement. Xác nhận có thể quan sát hai snapshot khác nhau. Không nên dựa vào sleep cố định vì test sẽ không ổn định.

### 18.3. Test REPEATABLE READ

Lặp lại scenario với Transaction A ở REPEATABLE READ:

~~~text
Transaction A (REPEATABLE READ)     Transaction B
--------------------------------   ----------------------------
BEGIN
SELECT COUNT(*) -> snapshot S
                                   INSERT product
                                   COMMIT
SELECT page -> vẫn dùng snapshot S
COMMIT
~~~

COUNT và page của transaction A cần phản ánh cùng snapshot. Sau khi transaction A commit, query mới có thể nhìn thấy hàng vừa insert.

### 18.4. Test single-statement window count

Với COUNT(*) OVER(), kiểm tra totalElements lặp lại trên mọi row của page và đúng với fixture. Thêm test offset ngoài phạm vi để xác nhận cách API xử lý khi query không trả row nào.

### 18.5. Test page drift giữa hai HTTP request

Đọc page đầu, thực hiện INSERT/DELETE trong transaction khác, rồi đọc page tiếp theo:

- Offset pagination có thể lặp/bỏ sót do vị trí dịch chuyển.
- Keyset pagination theo ID tăng thường tránh việc INSERT mới trước cursor làm dịch chuyển page.
- Cả hai có thể phản ánh dữ liệu thay đổi ở page sau.

Test phải kiểm tra đúng semantics đã công bố, không khẳng định keyset là snapshot đầy đủ.

## 19. Kiểm thử bằng StepVerifier và WebTestClient

StepVerifier hữu ích để kiểm tra publisher trả PageResponse:

~~~java
StepVerifier.create(repository.findActivePage(0, 20))
    .assertNext(page -> {
        assertEquals(20, page.size());
        assertEquals(327L, page.totalElements());
        assertEquals(17L, page.totalPages());
        assertTrue(page.hasNext());
    })
    .verifyComplete();
~~~

Đây là ví dụ test với dữ liệu fixture đã được chuẩn bị; không phải một con số mặc định của repository.

Với WebTestClient, kiểm tra contract HTTP:

~~~java
webTestClient.get()
    .uri("/api/products?active=true&page=0&size=20")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.items.length()").isEqualTo(20)
    .jsonPath("$.totalElements").isEqualTo(327)
    .jsonPath("$.totalPages").isEqualTo(17)
    .jsonPath("$.hasNext").isEqualTo(true);
~~~

Nếu dữ liệu test có thể thay đổi bởi test khác, dùng database/schema riêng hoặc cleanup fixture để tránh phụ thuộc thứ tự chạy.

## 20. Hiệu năng của count và page

Một query page có LIMIT không có nghĩa toàn bộ thao tác rẻ. Count chính xác có thể là phần tốn thời gian nhất.

Các yếu tố ảnh hưởng:

- Số hàng thỏa filter.
- Selectivity của điều kiện.
- Index có phù hợp predicate/order không.
- Join và DISTINCT.
- MVCC visibility và dead tuples.
- Statistics có cập nhật không.
- Cache/buffer state.
- Offset lớn.

### 20.1. Index cho filter và order

Nếu query phổ biến:

~~~sql
WHERE active = TRUE
ORDER BY id
LIMIT :size OFFSET :offset
~~~

Index phù hợp có thể là (active, id) tùy phân bố dữ liệu và workload. Nếu active có độ chọn lọc thấp, planner có thể chọn plan khác. Kiểm tra EXPLAIN (ANALYZE, BUFFERS) trên dữ liệu đại diện.

### 20.2. OFFSET sâu

Với OFFSET lớn, database có thể phải đi qua nhiều hàng trước khi trả page. Keyset pagination thường phù hợp hơn cho duyệt tuần tự trên tập lớn.

### 20.3. Cache count

Nếu total count không cần chính xác tại từng request, có thể cache theo filter key với TTL. Cần xác định:

- Cache key chứa đủ filter/tenant/version.
- TTL và invalidation.
- Chấp nhận độ trễ cập nhật bao lâu.
- Không dùng cache count giữa các tenant hoặc authorization scope.

Cache count là approximate/current-as-of-cache-time, không còn là exact per-response snapshot trừ khi có cơ chế đồng bộ dữ liệu và version rõ ràng.

## 21. Các trường hợp đặc biệt

### 21.1. Trang cuối thay đổi khi có DELETE

Nếu count là 41 và size là 20, totalPages là 3. Trong lúc người dùng đang ở page 2 (index 1), nhiều hàng bị xóa làm total còn 18. Page 2 có thể trả rỗng dù trước đó UI hiển thị có trang này.

API có thể trả empty page kèm total mới; client có thể quay về page cuối hợp lệ. Nếu dùng exact snapshot cho response, page và total trong response đó nhất quán, nhưng request sau vẫn có thể thay đổi.

### 21.2. UPDATE làm hàng đi vào hoặc ra khỏi filter

Nếu filter là active=true và một sản phẩm đổi active từ true sang false, hàng đó biến khỏi tập kết quả. Count và page phải áp filter trên cùng snapshot nếu cần exact per response.

### 21.3. GROUP BY và tổng số nhóm

Nếu API trả mỗi category một hàng tổng hợp, totalElements nên là số category/group được trả về, không phải số product nguồn. Count query cần đếm kết quả group:

~~~sql
SELECT COUNT(*)
FROM (
    SELECT category_id
    FROM product
    WHERE active = TRUE
    GROUP BY category_id
) grouped_categories;
~~~

Hoặc dùng count window trên query đã group. Xác định rõ đơn vị phân trang trước khi viết count.

### 21.4. COUNT DISTINCT trên join

Nếu page trả mỗi product một lần sau khi lọc category, count cần đếm DISTINCT product ID hoặc dùng EXISTS để tránh nhân bản hàng:

~~~sql
SELECT p.id, p.name
FROM product p
WHERE EXISTS (
    SELECT 1
    FROM product_category pc
    WHERE pc.product_id = p.id
      AND pc.category_id = :categoryId
)
ORDER BY p.id
LIMIT :size OFFSET :offset;
~~~

Query count tương ứng:

~~~sql
SELECT COUNT(*)
FROM product p
WHERE EXISTS (
    SELECT 1
    FROM product_category pc
    WHERE pc.product_id = p.id
      AND pc.category_id = :categoryId
);
~~~

EXISTS tránh nhân bản product do join nhiều category rows. Query plan vẫn cần được kiểm tra trên dữ liệu thực tế.

## 22. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| COUNT và page dùng filter khác nhau | Total không mô tả items | Dùng chung filter/criteria và test |
| Page có tenant scope nhưng count không có | Lộ số lượng dữ liệu ngoài quyền | Áp cùng authorization predicate |
| COUNT(*) trên join nhân bản entity | Total lớn hơn số item duy nhất | COUNT(DISTINCT id) hoặc EXISTS |
| ORDER BY không có tie-breaker duy nhất | Thứ tự có thể thay đổi | Thêm primary key vào ORDER BY |
| Nghĩ cùng transaction READ COMMITTED là cùng snapshot | Count và page vẫn có thể lệch | Dùng REPEATABLE READ hoặc một statement |
| Chỉ đặt readOnly=true | Không tự nâng isolation | Cấu hình isolation level rõ ràng |
| Dùng COUNT(*) OVER() nhưng page rỗng | Không có row để đọc total | Xử lý empty page, CTE/LEFT JOIN hoặc transaction count riêng |
| Tính count trên mọi request dù UI không cần | Tốn query và tăng latency | Dùng hasNext hoặc bỏ total |
| Dùng total từ page trước cho page sau mà không định nghĩa snapshot | UI hiển thị số liệu cũ | Định nghĩa current/as-of semantics |
| OFFSET trên dữ liệu thay đổi | Lặp hoặc bỏ sót hàng giữa trang | Keyset hoặc snapshot/cutoff phù hợp |
| Nghĩ keyset tự bảo đảm snapshot | UPDATE/DELETE vẫn làm tập kết quả đổi | Dùng versioned/materialized snapshot nếu cần |
| Giữ REPEATABLE READ qua nhiều HTTP request | Giữ connection/snapshot lâu | Dùng cutoff hoặc export snapshot job |
| Dùng count toàn bảng cho filter | Total sai | Count cùng predicate |
| Không kiểm tra overflow khi tính offset | Offset âm hoặc sai khi page lớn | Dùng long và Math.multiplyExact |
| Cache count nhưng không ghi rõ độ trễ | Client tưởng total là exact | Công bố approximate/as-of semantics |
| Dùng COUNT(DISTINCT) không cần thiết | Query có thể tốn hơn | Xác định grain và kiểm tra execution plan |

## 23. Quy trình thiết kế API page và total

Khi xây một API phân trang có total, thực hiện theo thứ tự:

1. **Xác định đơn vị dữ liệu:** mỗi item là một row, entity duy nhất hay một group.
2. **Xác định filter:** search, tenant, authorization, soft-delete và mọi điều kiện nghiệp vụ.
3. **Xác định order:** có thứ tự ổn định và tie-breaker duy nhất.
4. **Chọn pagination:** offset nếu cần nhảy page; keyset nếu duyệt tuần tự tập lớn.
5. **Xác định total semantics:** exact per response, current, as-of, approximate hay không có total.
6. **Nếu exact per response:** dùng một statement hoặc count/page trong REPEATABLE READ.
7. **Giữ count/page cùng predicate:** tránh duplicate filter logic.
8. **Giới hạn page size:** validate ở API và dùng LIMIT trong SQL.
9. **Xử lý empty/out-of-range page:** công bố rõ response contract.
10. **Kiểm thử concurrent writes:** xác nhận hành vi dưới INSERT/UPDATE/DELETE.
11. **Đo hiệu năng:** kiểm tra count, offset sâu, index và query plan.
12. **Theo dõi production:** count latency, page latency, rows returned và pool usage.

## 24. Nguyên tắc cần nhớ

- COUNT và page phải dùng cùng filter, tenant scope, authorization và đơn vị dữ liệu.
- Join có thể nhân bản hàng; đếm entity duy nhất bằng COUNT(DISTINCT id) hoặc EXISTS khi phù hợp.
- Pagination cần ORDER BY ổn định với tie-breaker duy nhất.
- PostgreSQL READ COMMITTED tạo snapshot mới cho mỗi statement, kể cả trong cùng transaction.
- readOnly=true không tự bảo đảm count và page dùng cùng snapshot.
- Dùng REPEATABLE READ cho hai query trong cùng response khi cần snapshot nhất quán.
- Hoặc dùng COUNT(*) OVER() để page và total thuộc cùng một statement snapshot.
- Window count không trả total nếu page rỗng; xử lý bằng contract, query phụ trong snapshot hoặc CTE/LEFT JOIN.
- COUNT chính xác có chi phí; LIMIT không làm phép đếm toàn bộ trở nên miễn phí.
- Exact per response không đồng nghĩa toàn bộ hành trình nhiều HTTP request dùng cùng snapshot.
- Offset có thể bị page drift khi INSERT/DELETE; keyset giảm dịch chuyển vị trí do hàng mới trước cursor.
- Keyset không tự bảo vệ khỏi UPDATE/DELETE hoặc thay đổi filter.
- SnapshotMaxId/asOf cutoff chỉ bảo đảm phần semantics mà điều kiện cutoff thực sự cố định.
- Không giữ transaction và connection qua nhiều request UI; dùng versioned/materialized snapshot cho export cần tính nhất quán dài hạn.
- Nếu chỉ cần biết còn dữ liệu, lấy size + 1 và trả hasNext thay vì COUNT.
- Dùng totalElements, remainingElements và approximateCount đúng ý nghĩa; không đánh tráo semantics.
- Dùng long cho offset/count và kiểm tra overflow.
- Test isolation/concurrent writes với PostgreSQL thật, không chỉ mock repository.

Tính nhất quán giữa trang dữ liệu và tổng đếm bắt đầu từ việc định nghĩa chính xác tập dữ liệu và thời điểm mà API muốn phản ánh. Khi cần một response có items và total cùng snapshot, hãy dùng một SQL statement có window count hoặc chạy count/page tuần tự trong transaction REPEATABLE READ trên PostgreSQL. Khi người dùng duyệt nhiều trang qua nhiều request, một transaction ngắn không thể giữ snapshot xuyên suốt; cần chọn semantics current/as-of, cursor/cutoff hoặc snapshot job. Nếu giao diện chỉ cần biết còn dữ liệu, keyset pagination cùng LIMIT size + 1 thường đơn giản và tiết kiệm hơn việc đếm chính xác toàn bộ bảng ở mỗi request.
