# Tối ưu truy vấn tham số hóa và kế hoạch chuẩn bị theo API hỗ trợ

## 1. Cùng một câu SQL++ được gọi hàng nghìn lần: điều gì có thể tối ưu?

Trong hệ thống Spring Data Couchbase, API lịch sử đơn hàng thường nhận một `customerId` và một `status` khác nhau ở mỗi request. Logic truy vấn không đổi:

~~~sql
SELECT META(o).id AS id,
       o.customerId,
       o.status,
       o.createdAtEpochMs,
       o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.docType = "order"
  AND o.customerId = $customerId
  AND o.status = $status
ORDER BY o.createdAtEpochMs DESC
LIMIT 20;
~~~

Nếu ứng dụng xây một chuỗi SQL++ mới bằng cách chèn giá trị `customerId`/`status` vào mỗi request, nó vừa tạo nguy cơ injection, vừa làm các câu lệnh có hình dạng văn bản khác nhau. Điều đó gây khó cho việc đo đạc, bảo trì và có thể giảm cơ hội tái sử dụng kế hoạch truy vấn.

Có hai kỹ thuật thường được nói cùng nhau nhưng **không phải một**:

- **Tham số hóa (parameterization):** giữ câu lệnh SQL++ ổn định, truyền giá trị tách khỏi cú pháp bằng named/positional parameters.
- **Prepared statement/plan reuse:** yêu cầu hệ thống chuẩn bị và có thể tái sử dụng kế hoạch cho dạng câu lệnh phù hợp; trong Couchbase Java SDK 3.x, một API quan trọng là `QueryOptions.adhoc(false)`.

Bài **“Tối ưu truy vấn tham số hóa và kế hoạch chuẩn bị theo API hỗ trợ”** thuộc chương **Hiệu năng** của module **SPRING_DATA_COUCHBASE**. Module xây dựng tầng truy cập Couchbase với document mapping, repository, `CouchbaseTemplate` và SQL++; thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và lựa chọn API reactive nhằm bảo đảm hiệu năng, nhất quán và khả năng vận hành.

Sau bài, bạn có thể:

1. Viết SQL++ có **named** hoặc **positional parameters**, không nối giá trị người dùng vào câu lệnh.
2. Phân biệt bind **value** với việc chọn field, collection, operator hay hướng sort.
3. Dùng Couchbase Java SDK `cluster.query`/`scope.query` cùng `QueryOptions.adhoc(false)` khi phiên bản hỗ trợ.
4. Hiểu sự khác nhau giữa lượt chuẩn bị đầu tiên và các lượt có khả năng dùng lại plan.
5. Biết các giới hạn của prepared plans khi có index/schema changes, parameter skew và dynamic query shapes.
6. Xác minh generated SQL++ của Spring Data derived query, `@Query` và repository projections trước khi tối ưu.
7. Giữ đúng query consistency, index, authorization, pagination và response contract.
8. Đo p50/p95/p99, throughput, query plan/caching behavior, bytes và lỗi trong benchmark công bằng.

Ví dụ hướng tới Java 17, Spring Boot 3.x, Spring Data Couchbase 5.x, Couchbase Java SDK 3.x và Couchbase Server có SQL++ Query service. Tên API cụ thể, cache behavior và các tính năng optimizer tùy phiên bản; không suy từ một ví dụ rằng mọi release hoặc mọi Spring Data abstraction đều expose cùng tùy chọn chuẩn bị.

## 2. Trước khi tối ưu, chọn đúng đường truy cập

Nếu đã có **document ID chính xác** và biết bucket/scope/collection, `CouchbaseRepository.findById` hoặc SDK `Collection.get` thường phù hợp hơn việc viết SQL++ chỉ để đọc một key.

~~~mermaid
flowchart TD
    A["Yêu cầu dữ liệu"] --> B{"Có exact document ID?"}
    B -- "Có" --> C["KV get / findById / lookupIn"]
    B -- "Chưa, có predicate" --> D["SQL++ parameterized"]
    D --> E{"Query shape lặp nhiều lần?"}
    E -- "Có" --> F["Đánh giá prepared plan qua API hỗ trợ"]
    E -- "Không" --> G["Ad hoc query và đo"]
    F --> H["EXPLAIN + benchmark + consistency"]
    G --> H
    C --> I["Không cần Query service/GSI cho KV lookup"]
~~~

Ví dụ:

| Nhu cầu | Lựa chọn khởi đầu |
| --- | --- |
| Lấy một session theo token/key | KV GET, không SQL++ |
| Lấy order theo document ID | Repository `findById` hoặc SDK GET |
| 20 order mới nhất theo customer/status | SQL++ có parameters + index |
| Top 10 order theo total | SQL++ + index/sort |
| Thống kê theo status | SQL++ aggregation |
| Tìm theo full-text | Search service nếu đúng nhu cầu |
| Truy vấn giống nhau hàng nghìn lần với values khác | SQL++ parameters, thử prepared plan |
| Một truy vấn bảo trì chạy một lần | Parameterized query, chưa chắc cần prepare |

**Prepared statement không làm một full scan trở nên chọn lọc** nếu index và predicate kém. Đường truy cập và index đúng luôn là nền tảng.

## 3. Mô hình dữ liệu và truy vấn xuyên suốt

Collection:

~~~text
Bucket: commerce
Scope: sales
Collection: orders
Document key: order::O-2026-001
~~~

Ví dụ JSON:

~~~json
{
  "docType": "order",
  "tenantId": "tenant-a",
  "customerId": "u-42",
  "status": "PAID",
  "createdAtEpochMs": 1795582800000,
  "orderSequence": 10051,
  "total": 150000,
  "currency": "VND"
}
~~~

Endpoint:

~~~text
GET /tenants/tenant-a/customers/u-42/orders?status=PAID
~~~

Một câu query có đầy đủ điều kiện bảo vệ tenant:

~~~sql
SELECT META(o).id AS id,
       o.status,
       o.createdAtEpochMs,
       o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.docType = "order"
  AND o.tenantId = $tenantId
  AND o.customerId = $customerId
  AND o.status = $status
ORDER BY o.createdAtEpochMs DESC, o.orderSequence DESC
LIMIT 20;
~~~

Các tên `tenantId`, `customerId` và `status` trong SQL++ là **tên trường**; dấu `$` đánh dấu **giá trị parameter** được gửi kèm query. Bucket/scope/collection là **identifiers trong cú pháp**, không phải values để bind như customer ID.

### 3.1. Tách schema, query shape và values

~~~text
Schema/keyspace:
  commerce.sales.orders

Query shape:
  WHERE tenantId = $tenantId
    AND customerId = $customerId
    AND status = $status
  ORDER BY createdAtEpochMs DESC
  LIMIT 20

Values request A:
  tenantId = tenant-a; customerId = u-42; status = PAID

Values request B:
  tenantId = tenant-a; customerId = u-99; status = SHIPPED
~~~

Hai request có thể dùng cùng statement text và chỉ đổi parameters. Đây là cơ sở để tránh tạo vô hạn query strings và đánh giá khả năng reuse prepared plan.

## 4. Anti-pattern: nối input vào SQL++ string

~~~java
// Không dùng: input người dùng được chèn vào cú pháp query.
String sql =
        "SELECT META(o).id FROM `commerce`.`sales`.`orders` o " +
        "WHERE o.customerId = '" + customerId + "' " +
        "AND o.status = '" + status + "'";
~~~

Vấn đề:

1. Dữ liệu chứa dấu nháy có thể làm query lỗi.
2. Input có thể biến thành cú pháp SQL++ nếu không được xử lý an toàn.
3. Statement text thay đổi theo từng customer/status.
4. Metrics/log có thể chứa giá trị nhạy cảm.
5. Khó kiểm thử và kiểm soát query shape.
6. Không tận dụng tối đa khả năng prepared plan cho dạng câu lệnh lặp.

Không tự sửa bằng cách replace ký tự nháy thủ công: hãy **bind values qua API**.

## 5. Named parameters với Java SDK 3.x

Đây là cách đọc và bảo trì rõ ràng khi query có nhiều input:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryResult;

public final class OrderQueryGateway {

    private final Cluster cluster;

    public OrderQueryGateway(Cluster cluster) {
        this.cluster = cluster;
    }

    public QueryResult findRecent(
            String tenantId, String customerId, String status) {

        String sql = """
                SELECT META(o).id AS id,
                       o.status,
                       o.createdAtEpochMs,
                       o.total
                FROM `commerce`.`sales`.`orders` AS o
                WHERE o.docType = "order"
                  AND o.tenantId = $tenantId
                  AND o.customerId = $customerId
                  AND o.status = $status
                ORDER BY o.createdAtEpochMs DESC,
                         o.orderSequence DESC
                LIMIT 20
                """;

        JsonObject params = JsonObject.create()
                .put("tenantId", tenantId)
                .put("customerId", customerId)
                .put("status", status);

        return cluster.query(
                sql,
                QueryOptions.queryOptions()
                        .parameters(params)
        );
    }
}
~~~

**Chú ý:** tên key trong `JsonObject` là `tenantId`, không kèm `$`; dấu `$tenantId` nằm trong SQL++.

Việc bind ngăn values bị diễn giải như query syntax trong vị trí parameter hợp lệ. Nó không tự xác minh người dùng có quyền với tenant được bind; authorization vẫn là trách nhiệm nghiệp vụ.

### 5.1. Named parameters không phụ thuộc thứ tự

~~~java
JsonObject params = JsonObject.create()
        .put("status", status)
        .put("tenantId", tenantId)
        .put("customerId", customerId);
~~~

Với named parameters, key names xác định cách bind. Thứ tự gọi `put` không làm query đổi thứ tự WHERE hay ORDER BY.

### 5.2. Không thêm dấu nháy quanh parameter

Sai:

~~~sql
WHERE o.customerId = '$customerId'
~~~

Khi ở trong literal string, `$customerId` có thể được hiểu là chữ trong chuỗi, **không phải placeholder**. Đúng:

~~~sql
WHERE o.customerId = $customerId
~~~

Đừng truyền một giá trị chứa dấu nháy và cố “escape” để trở thành SQL string literal; cứ bind string Java bình thường.

## 6. Positional parameters

SQL++ hỗ trợ placeholders vị trí như `$1`, `$2`. Java SDK nhận `JsonArray` khi API hỗ trợ:

~~~java
import com.couchbase.client.java.json.JsonArray;
import com.couchbase.client.java.query.QueryOptions;

String sql = """
        SELECT META(o).id AS id, o.status
        FROM `commerce`.`sales`.`orders` AS o
        WHERE o.customerId = $1
          AND o.status = $2
        LIMIT 20
        """;

var result = cluster.query(
        sql,
        QueryOptions.queryOptions()
                .parameters(JsonArray.from("u-42", "PAID"))
);
~~~

Trong ví dụ, phần tử đầu gắn với `$1`, phần tử thứ hai với `$2`. **Không dùng chỉ số 0 trong SQL++ chỉ vì array Java thường index từ 0.**

### 6.1. Chọn named hay positional?

| Tình huống | Gợi ý |
| --- | --- |
| Query dài, nhiều điều kiện | Named parameters dễ review |
| Query ngắn, ít giá trị | Positional có thể đủ |
| Refactor thêm một predicate | Named giảm rủi ro sai thứ tự |
| Tự động generated query của framework | Dùng binding syntax framework hỗ trợ |
| Debug mismatch parameters | Named rõ ý nghĩa hơn |
| Bảo vệ injection | Cả hai đều an toàn khi bind đúng |

Không trộn cả hai kiểu tùy tiện trong một statement nếu SDK/server release không cho phép hoặc làm contract khó hiểu. Chọn nhất quán theo codebase.

## 7. Bind đúng kiểu dữ liệu, không stringify mọi giá trị

SQL++ phân biệt string, number, boolean, null, object và array. Ví dụ:

~~~java
JsonObject params = JsonObject.create()
        .put("customerId", "u-42")
        .put("minTotal", 100000L)
        .put("active", true);
~~~

Query:

~~~sql
SELECT META(o).id AS id, o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND o.total >= $minTotal
  AND o.active = $active;
~~~

Nếu truyền số tiền thành string `"100000"` thay vì number, phép so sánh có thể khác hoặc không match index/type. Tương tự, thời gian nên có contract rõ: epoch milliseconds dạng số hoặc định dạng timestamp nhất quán với schema, không tùy ý đổi giữa các request.

### 7.1. Định nghĩa typed request trước khi bind

~~~java
public record OrderSearch(
        String tenantId,
        String customerId,
        String status,
        long minTotal) {

    public OrderSearch {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Missing tenant");
        }
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("Missing customer");
        }
        if (minTotal < 0) {
            throw new IllegalArgumentException("Negative total");
        }
    }
}
~~~

Khi type và boundary hợp lệ ở Java, parameter binding phản ánh đúng nghiệp vụ; database parameters không thay validation.

## 8. Bind một danh sách bằng array parameter

Muốn tìm nhiều trạng thái, đừng nối raw input vào `IN (...)`:

~~~sql
SELECT META(o).id AS id, o.status
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND o.status IN $statuses;
~~~

Couchbase SDK:

~~~java
import com.couchbase.client.java.json.JsonArray;
import com.couchbase.client.java.json.JsonObject;

var parameters = JsonObject.create()
        .put("customerId", "u-42")
        .put("statuses",
                JsonArray.from("PAID", "SHIPPED", "PACKED"));
~~~

`IN $statuses` dùng giá trị array được bind, không phải chuỗi chứa dấu ngoặc. Hãy validate danh sách không quá lớn, giá trị status thuộc allowlist và behavior khi array rỗng.

### 8.1. Có phải IN luôn tối ưu?

Không. Với index `(customerId, status, createdAtEpochMs DESC)`, `IN` gồm nhiều status có thể tạo nhiều spans và phải merge/sort. Prepared plan không thay đổi chi phí scan của một predicate kém phù hợp. Cần `EXPLAIN` cho các cardinality array thường gặp.

### 8.2. Đừng đưa danh sách ID hàng triệu phần tử vào một query

Nếu đã biết nhiều document IDs, hãy cân nhắc KV batch/concurrency có giới hạn, hoặc SQL++ `USE KEYS` theo phạm vi phù hợp. Một parameter array cực lớn có network/parse/memory cost và không thay thế thiết kế data access.

## 9. Bind object hoặc nested value khi thật sự cần

Các parameters có thể là JSON object:

~~~java
JsonObject filters = JsonObject.create()
        .put("minTotal", 100000)
        .put("maxTotal", 500000);

JsonObject params = JsonObject.create()
        .put("customerId", "u-42")
        .put("filter", filters);
~~~

Query:

~~~sql
SELECT META(o).id AS id, o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND o.total >= $filter.minTotal
  AND o.total <= $filter.maxTotal;
~~~

Cú pháp truy cập thuộc tính trên bound JSON object phải được kiểm tra với SQL++ server release; khi không cần object phức tạp, **named scalars** thường dễ đọc, dễ gỡ lỗi và phù hợp hơn với query/index analysis.

Tránh cho phép client gửi một object có cấu trúc bất kỳ để quyết định operators/field names. Parameters đại diện **dữ liệu**, không phải toàn bộ AST của query.

## 10. NULL, MISSING và optional filters

SQL++ có ngữ nghĩa phân biệt `NULL`, `MISSING` và trường không tồn tại. Việc bind Java `null` không nhất thiết tương đương việc bỏ hẳn predicate.

Ví dụ:

~~~sql
WHERE o.customerId = $customerId
  AND o.status = $status
~~~

Nếu `$status = NULL`, đừng giả định điều kiện nghĩa là “bất kỳ status”. Phép so sánh với NULL có semantics riêng và có thể không match các row như người viết mong đợi.

Có hai hướng có chủ đích:

1. Dùng **query template riêng** khi filter status không có.
2. Dùng một predicate optional có logic chính xác, rồi **đo query plan**.

Ví dụ hai templates:

~~~sql
-- Có status:
SELECT META(o).id AS id
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND o.status = $status;

-- Không có status:
SELECT META(o).id AS id
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId;
~~~

Hai query shapes có thể cần hai indexes/plan khác nhau; đây không phải vấn đề cần ép về một statement bằng mọi giá.

## 11. Giá trị được bind; identifiers thì không

Một parameter placeholder **không phải** cách thay thế tên bucket, scope, collection, field hay hướng `ASC/DESC`.

Sai về ý tưởng:

~~~sql
SELECT *
FROM $collection
ORDER BY $field $direction;
~~~

`$collection`, `$field` và `$direction` ở đây không phải chỗ thích hợp để bind identifiers/SQL grammar. Không mong SDK tự quote hoặc validate chúng.

Giải pháp an toàn là **allowlist query structure**:

~~~java
public enum OrderSort {
    NEWEST,
    HIGHEST_TOTAL
}
~~~

~~~java
static String orderBy(OrderSort sort) {
    return switch (sort) {
        case NEWEST ->
                "o.createdAtEpochMs DESC, o.orderSequence DESC";
        case HIGHEST_TOTAL ->
                "o.total DESC, o.orderSequence DESC";
    };
}
~~~

Chỉ dùng những fragments được định nghĩa sẵn trong code, không nối trực tiếp chuỗi `sortBy` hay `direction` từ HTTP request.

### 11.1. Keyspace động cần whitelist và identifier quoting

Nếu multi-tenant architecture dùng nhiều collections khác nhau, thay đổi collection là thay đổi **query structure**; hãy xác nhận namespace thuộc danh sách cấu hình được phép và dùng cơ chế quote identifier phù hợp. Khi có thể, prefer một shared collection với `tenantId` được bind và tenant authorization đúng contract.

**Bind value bảo vệ một loại injection**, không miễn trách nhiệm kiểm tra identifiers và quyền truy cập.

## 12. Tham số hóa không thay authorization

Một caller biết `tenantId = tenant-b` vẫn có thể gửi value đó. Vì vậy giá trị tenant dùng trong query phải lấy từ **context đã xác thực/được cho phép**, không tin hoàn toàn vào query string của client.

Ví dụ:

~~~sql
WHERE o.tenantId = $authorizedTenantId
  AND o.customerId = $customerId
~~~

`$authorizedTenantId` cần được xác định bởi service từ identity/authorization context. Parameter binding giúp query an toàn cú pháp, **không tự đảm bảo row-level security**.

Không log raw customer identifiers, session IDs hoặc giá trị nhạy cảm chỉ để debug prepared plan hit.

## 13. Prepared statement là gì ở cấp khái niệm?

Một câu SQL++ thường cần các bước như parse, kiểm tra semantics, chọn access path/index và xây execution plan trước khi thực thi.

~~~mermaid
sequenceDiagram
    participant App as Spring service
    participant SDK as Couchbase SDK
    participant QS as Query service
    participant IS as Index/Data services
    App->>SDK: Statement + named parameters
    SDK->>QS: Query request
    alt Ad hoc / chưa có prepared plan
        QS->>QS: Parse / optimize / plan
    else Prepared plan có thể tái sử dụng
        QS->>QS: Tìm prepared plan phù hợp
    end
    QS->>IS: Scan / fetch / execute
    IS-->>QS: Rows
    QS-->>SDK: Result
    SDK-->>App: Rows/metadata
~~~

Prepared plan có mục tiêu giảm công việc chuẩn bị lặp lại cho cùng dạng statement. Nó **không lưu sẵn kết quả query**. Request A và B dùng cùng plan vẫn đọc dữ liệu theo parameters khác nhau.

### 13.1. Plan reuse khác result caching

| Khái niệm | Có thể được tái sử dụng | Không bảo đảm |
| --- | --- | --- |
| Parameterized statement | Cú pháp/structure ổn định | Query nhanh hơn nếu index kém |
| Prepared plan | Một execution plan đã chuẩn bị | Reuse mãi mãi; có cache miss/invalidation |
| Application data cache | Kết quả/DTO theo cache key | Fresh read hoặc quyền truy cập luôn đúng |
| KV read by key | Đường tìm document trực tiếp | Tự tạo kết quả cho query predicate |

Nếu app dùng cache dữ liệu, latency giảm có thể đến từ cache hit, không phải prepared plan. Phân biệt những nguồn tối ưu này trong benchmark.

## 14. Couchbase Java SDK: `QueryOptions.adhoc(false)`

Trong Couchbase Java SDK 3.x, thiết lập:

~~~java
import com.couchbase.client.java.query.QueryOptions;

var options = QueryOptions.queryOptions()
        .parameters(params)
        .adhoc(false);
~~~

yêu cầu đường truy vấn dùng **prepared statement behavior** theo khả năng SDK/Query service. SDK và server có thể xử lý việc chuẩn bị, ghi nhớ và dùng lại plan phù hợp; cơ chế cache cụ thể phụ thuộc version và topology.

Thực hiện:

~~~java
var result = cluster.query(
        ORDER_LIST_SQL,
        QueryOptions.queryOptions()
                .parameters(params)
                .adhoc(false)
);
~~~

Trong đó `ORDER_LIST_SQL` là câu SQL++ **ổn định**, được khai báo một lần:

~~~java
private static final String ORDER_LIST_SQL = """
        SELECT META(o).id AS id,
               o.status,
               o.createdAtEpochMs,
               o.total
        FROM `commerce`.`sales`.`orders` AS o
        WHERE o.docType = "order"
          AND o.tenantId = $tenantId
          AND o.customerId = $customerId
          AND o.status = $status
        ORDER BY o.createdAtEpochMs DESC,
                 o.orderSequence DESC
        LIMIT 20
        """;
~~~

Không cần nối values vào constant SQL. Mỗi request tạo `JsonObject` parameters mới chứa values hợp lệ.

### 14.1. `adhoc(false)` không có nghĩa “câu query được cache kết quả”

Sau mutation, query vẫn phải đọc dữ liệu/độ mới theo scan consistency. Plan có thể được dùng lại trong khi rows thay đổi; đó là điều bình thường.

### 14.2. `adhoc(true)` không đồng nghĩa “không an toàn”

Ad hoc chỉ nói về lựa chọn prepared statement behavior. Một query ad hoc vẫn có thể được **tham số hóa an toàn** bằng `QueryOptions.parameters`.

**Tham số hóa và prepared plan là hai quyết định độc lập.** Tất cả queries nhận user values nên bind đúng, dù dùng ad hoc hay prepared plan.

## 15. Khi nào chuẩn bị plan đáng cân nhắc?

| Query pattern | Lựa chọn cần benchmark |
| --- | --- |
| SQL++ cùng shape, hàng nghìn calls/phút | `adhoc(false)` có thể có lợi |
| Query quan trọng chạy liên tục với parameters khác | Prepared plan đáng thử |
| Query một lần trong migration | Ad hoc thường đơn giản hơn |
| Mỗi request tạo SQL++ string riêng | Sửa dynamic shape trước khi chuẩn bị |
| Query có rất nhiều plan variants | Tránh làm phình cache; phân nhóm templates |
| Query predicate/index kém | Tối ưu index/predicate trước |
| Query cost rất cao do scan hàng triệu rows | Plan preparation có thể là phần nhỏ |
| Query rất ngắn, kết quả ít và thường xuyên | Plan overhead có thể đáng kể |

Không tuyên bố có một ngưỡng cố định “sau 2 lần thì prepared luôn nhanh hơn”. Lợi ích phụ thuộc thời gian lập plan, hit ratio, topology, index changes và tần suất thực.

## 16. First-call overhead và lượt lặp có plan

Một thử nghiệm nên tách:

~~~text
Cold run:
  Statement chưa có prepared plan phù hợp
  Có thể tốn thêm chi phí chuẩn bị

Warm runs:
  Gửi cùng statement text/query context
  Bind values khác
  Có thể dùng lại prepared plan

Invalidation/change:
  Index/schema/topology đổi
  Plan có thể cần refresh/reprepare
~~~

Dữ liệu giả định:

| Giai đoạn | Ad hoc | Prepared |
| --- | --- | --- |
| First call | Lập plan + thực thi | Chuẩn bị + thực thi |
| Subsequent calls | Có thể lập plan lại theo behavior | Có cơ hội reuse |
| After index change | Optimizer dùng metadata mới | Có thể phải reprepare |
| One-off statement | Không cần quan tâm cache | Có thể tốn setup không bù lợi ích |

Đây là mô hình tư duy, không phải mô tả chính xác từng packet của mọi phiên bản SDK. Benchmark phải tính cả cold/warm và các lần reprepare.

## 17. Cache plans nằm ở đâu, khi nào có thể mất?

Tùy Couchbase Server/SDK release, prepared statement và cache liên quan có thể được quản lý ở Query service và/hoặc qua SDK behavior. Khi có nhiều Query nodes, failover, rolling upgrade hoặc mất cache, không thể giả định mọi request luôn trúng cùng một plan đã chuẩn bị.

Các trường hợp cần theo dõi:

- Server/SDK restart hoặc thay đổi Query service node.
- Index được tạo, drop, build lại hoặc đổi trạng thái.
- Schema/keyspace/query context thay đổi.
- Statement text/template thay đổi.
- Lượng query shapes quá đa dạng làm cache thrash.
- Query planner chọn một plan mới theo khả năng version hỗ trợ.

**Không pin kiến trúc ứng dụng vào giả định cache hit 100%.** Cần có test/resilience đối với plan miss, reprepare và lỗi hạ tầng thật.

### 17.1. Prepared plan không bảo vệ trước lỗi index

Nếu index đang được dùng bị drop, hoặc Query service không thể chọn index hợp lệ, một prepared plan cũ không thay thế dữ liệu/index đã mất. Hãy xử lý lỗi, điều phối rollout index trước ứng dụng và benchmark sau khi plan thay đổi.

## 18. Có cần gửi `PREPARE`/`EXECUTE` SQL++ thủ công?

Couchbase SQL++ có khái niệm lệnh chuẩn bị/thực thi trực tiếp theo server version. Tuy nhiên khi ứng dụng dùng Java SDK 3.x, thường nên **bắt đầu với API `adhoc(false)` được hỗ trợ**, thay vì tự xây cơ chế tạo tên, lưu, phân phối và invalidation kế hoạch.

Việc chủ động điều khiển `PREPARE`/`EXECUTE` có thể phù hợp với công cụ SQL++ hay một use case đặc thù, nhưng cú pháp và caching semantics cần kiểm tra **đúng server version**. Không trộn một manual plan name với SDK automatic preparation mà không hiểu ai sở hữu vòng đời.

### 18.1. Đừng tự phát minh plan cache ở Java bằng string map

Một `Map<String, String>` lưu SQL statement text trong Java không đồng nghĩa đã có prepared execution plan ở Query service. Nó chỉ tái sử dụng text. SDK/server phải thực hiện cơ chế prepared statement thật.

## 19. Query shape ổn định giúp reuse dễ hơn

Nên giữ statement constant:

~~~java
private static final String RECENT_PAID_SQL = """
        SELECT META(o).id AS id,
               o.createdAtEpochMs,
               o.total
        FROM `commerce`.`sales`.`orders` AS o
        WHERE o.tenantId = $tenantId
          AND o.customerId = $customerId
          AND o.status = "PAID"
        ORDER BY o.createdAtEpochMs DESC
        LIMIT 20
        """;
~~~

Với query shape cố định, requests chỉ khác parameter values:

~~~java
JsonObject params = JsonObject.create()
        .put("tenantId", "tenant-a")
        .put("customerId", "u-42");
~~~

Tránh tự tạo các biến thể text vì whitespace, alias hoặc fragment động không cần thiết. Việc thay nhỏ statement text có thể tạo nhiều plan entries tùy implementation.

**Không áp “constant text bằng mọi giá” nếu làm sai tối ưu index.** Khi các filter khác nhau đòi plan khác nhau, dùng một tập templates có kiểm soát là hợp lý.

## 20. Optional predicates: đừng ép một plan phục vụ mọi trường hợp

Hai endpoint:

~~~text
/orders?customerId=u-42
/orders?customerId=u-42&status=PAID
~~~

Hai dạng query có thể cần index khác:

~~~sql
-- Template 1: chỉ customer, sort theo thời gian
SELECT META(o).id AS id, o.createdAtEpochMs
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAtEpochMs DESC
LIMIT 20;
~~~

~~~sql
-- Template 2: customer + status, sort theo thời gian
SELECT META(o).id AS id, o.createdAtEpochMs
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND o.status = $status
ORDER BY o.createdAtEpochMs DESC
LIMIT 20;
~~~

Một cách dễ viết nhưng không chắc tối ưu:

~~~sql
WHERE o.customerId = $customerId
  AND ($status IS NULL OR o.status = $status)
~~~

Predicate chứa `OR` và parameter optional có thể khó push down/sargable theo index hoặc cho plan ít chọn lọc. Hãy đo thay vì cố gom về một template duy nhất.

### 20.1. Query builder an toàn với ít templates

~~~java
static String selectSql(boolean hasStatus) {
    return hasStatus
            ? SQL_BY_CUSTOMER_AND_STATUS
            : SQL_BY_CUSTOMER;
}
~~~

Hai hằng SQL++ được audit và có index tương ứng là giải pháp đơn giản, vừa an toàn vừa cho optimizer nhìn thấy predicate rõ.

## 21. Phân bố giá trị lệch có thể làm plan chung kém phù hợp

Giả sử:

~~~text
status = PAID      → 80% documents
status = CANCELLED → 0,5% documents
~~~

Một plan dùng cho mọi `$status` có thể không tối ưu như nhau khi selectivity rất khác. Prepared plan tiết kiệm công việc lập kế hoạch, nhưng khả năng tối ưu theo từng value/cost model phụ thuộc server version và thực thi.

Đừng kết luận “prepared luôn tốt” chỉ nhờ thử một status hiếm. Benchmark với:

- Giá trị cực phổ biến.
- Giá trị rất hiếm.
- Customer có nhiều đơn/hot key.
- Customer có rất ít đơn.
- Mảng `IN` ngắn và dài.
- Các trường hợp không match.

Khi một số groups cần kế hoạch khác, cân nhắc query/index/template riêng thay vì thay giá trị parameter thành SQL literal trực tiếp để ép plan mà không kiểm soát.

## 22. Index vẫn là trung tâm của query performance

Query:

~~~sql
SELECT META(o).id AS id,
       o.status,
       o.createdAtEpochMs
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.customerId = $customerId
  AND o.status = $status
ORDER BY o.createdAtEpochMs DESC
LIMIT 20;
~~~

Index ứng viên:

~~~sql
CREATE INDEX ix_orders_tenant_customer_status_recent
ON `commerce`.`sales`.`orders` (
    tenantId,
    customerId,
    status,
    createdAtEpochMs DESC
);
~~~

Các equality prefix có thể thu hẹp index spans, key thời gian hỗ trợ order nếu plan phù hợp. Nhưng cần kiểm tra:

1. Index name được optimizer chọn.
2. Index spans có chọn lọc không.
3. Có `Fetch` nhiều document hay chỉ index cover.
4. Có `Order` sort riêng không.
5. Có `Limit` sớm không.
6. Query p95/p99 thay đổi ra sao theo parameter values.

Prepared plan reuse không giúp nếu statement thực hiện primary scan lớn; một index đúng thường có tác động lớn hơn tối ưu thời gian parse/plan.

### 22.1. Covering index và projection

Để tránh Fetch, query cần projection/predicate/order fields được index đáp ứng theo khả năng version. Nếu `SELECT o.*`, một index chỉ chứa bốn fields không mặc nhiên cover query. Prepared plan không làm rộng khả năng cover của index.

## 23. `EXPLAIN` với parameterized query

Khi phân tích, dùng một query có shape tương đương, cho các values đại diện và xem plan theo version/Query Workbench API.

~~~sql
EXPLAIN
SELECT META(o).id AS id,
       o.status,
       o.createdAtEpochMs
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "tenant-a"
  AND o.customerId = "u-42"
  AND o.status = "PAID"
ORDER BY o.createdAtEpochMs DESC
LIMIT 20;
~~~

Đoạn dùng literal cố định là **mẫu phân tích plan** trong môi trường tin cậy, không phải gợi ý nối user input vào production query. Để kiểm tra plan prepared với parameters, dùng tooling/API hỗ trợ và xác minh đúng statement shape và binding.

Không suy ra plan prepared chắc chắn trùng hoàn toàn với plan ad hoc có literal nếu optimizer/version áp quy tắc khác. Dùng profile/query metrics trên **đường production thực tế**.

### 23.1. Kiểm tra cost thay vì chỉ có tên index

Một plan dùng đúng index nhưng scan hàng trăm nghìn entries vẫn có thể chậm. Kiểm tra estimated cardinality, runtime scanned entries, fetch/sort work và request latencies theo server version.

## 24. Spring Data Couchbase derived query

Ví dụ entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("sales")
@Collection("orders")
public class OrderDocument {

    @Id
    private String id;
    private String tenantId;
    private String customerId;
    private String status;
    private Long createdAtEpochMs;

    protected OrderDocument() { }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getCustomerId() { return customerId; }
    public String getStatus() { return status; }
    public Long getCreatedAtEpochMs() { return createdAtEpochMs; }
}
~~~

Repository:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByTenantIdAndCustomerIdAndStatus(
            String tenantId, String customerId, String status);
}
~~~

Spring Data có thể dựng và bind SQL++ cho derived method theo framework/version. Việc code Java không tự nối string không có nghĩa Query service sẽ dùng prepared plan theo tùy chọn mong muốn.

**Quan trọng:** phải kiểm tra SQL++ thực sự phát ra, mapping fields, type filter, sort, projection và API nào expose `adhoc(false)` ở version đang dùng. Không khẳng định `CouchbaseRepository` mặc định chuẩn bị mọi query.

## 25. Spring Data `@Query` với binding có kiểm soát

Spring Data Couchbase thường hỗ trợ `@Query` với những SpEL placeholders dành cho entity query ở các release tương thích:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.Query;

public interface OrderSearchRepository
        extends CouchbaseRepository<OrderDocument, String> {

    @Query(
        "#{#n1ql.selectEntity} WHERE #{#n1ql.filter} " +
        "AND tenantId = $1 " +
        "AND customerId = $2 " +
        "AND status = $3"
    )
    List<OrderDocument> search(
            String tenantId, String customerId, String status);
}
~~~

Các placeholders `#{#n1ql.selectEntity}`/`#{#n1ql.filter}` là công cụ Spring Data (khác với `$1`/`$2`/`$3` để bind values trong SQL++). Chúng có thể giúp giữ entity selection và type discriminator theo framework contract.

Cần xác minh query thật trên phiên bản đã resolve. Một derived/annotated query có thể chọn full entity nên không có covering index; projection DTO có shape khác. Không xóa type filter chỉ để benchmark nhanh rồi vô tình trả nhầm entity.

### 25.1. Tránh dùng Java string interpolation cho `@Query`

Không tạo một annotation hoặc dynamic `@Query` bằng cách nối giá trị người dùng thành literal. Dùng parameter binding mà repository/framework hỗ trợ và test các chuỗi có dấu nháy/ký tự đặc biệt.

## 26. `CouchbaseTemplate` và tùy chọn prepared plan

`CouchbaseTemplate` có API đọc theo ID và truy vấn entity trong Spring Data Couchbase. Tuy nhiên **không phải mọi abstraction của template/repository đều expose trực tiếp một đối số `QueryOptions.adhoc(false)` giống SDK**.

Cách tiếp cận thực tế:

1. Nếu biết document key, dùng `findById`/KV phù hợp.
2. Nếu cần repository derived query, giữ framework binding/mapping và **đo query behavior**.
3. Nếu hot query cần điều khiển explicit QueryOptions như `adhoc(false)`, scan consistency hay diagnostics, cân nhắc một **custom gateway** dựa trên SDK `Cluster.query`/`Scope.query`.
4. Tách result mapping/projection sang DTO rõ ràng.
5. Integration test để bảo đảm keyspace, type filter, tenant, JSON fields và consistency như đường cũ.

Không cố “đẩy” một option không có trong public API template bằng giả định hoặc reflection không được hỗ trợ.

## 27. Tích hợp SDK gateway trong ứng dụng Spring Data

Một service chuyên cho hot SQL++ query có thể nhận `Cluster` đã được Spring quản lý hoặc một bean tương đương do configuration tạo:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;

public final class RecentOrdersGateway {

    private static final String SQL = """
            SELECT META(o).id AS id,
                   o.status,
                   o.createdAtEpochMs,
                   o.total
            FROM `commerce`.`sales`.`orders` AS o
            WHERE o.docType = "order"
              AND o.tenantId = $tenantId
              AND o.customerId = $customerId
              AND o.status = $status
            ORDER BY o.createdAtEpochMs DESC,
                     o.orderSequence DESC
            LIMIT 20
            """;

    private final Cluster cluster;

    public RecentOrdersGateway(Cluster cluster) {
        this.cluster = cluster;
    }

    public java.util.List<JsonObject> execute(
            String tenantId, String customerId, String status) {

        JsonObject values = JsonObject.create()
                .put("tenantId", tenantId)
                .put("customerId", customerId)
                .put("status", status);

        return cluster.query(
                SQL,
                QueryOptions.queryOptions()
                        .parameters(values)
                        .adhoc(false)
        ).rowsAsObject();
    }
}
~~~

Đây là một **gateway chuyên trách**, không có nghĩa toàn ứng dụng phải bỏ repository. Code production cần auth validation ở service, timeout/error handling và DTO mapping; list size phải có giới hạn rõ.

### 27.1. Không tạo Cluster mới mỗi request

SDK `Cluster`/connection environment có vòng đời tương đối dài; Spring Boot nên quản lý và dùng chung. Tạo `Cluster.connect`/`disconnect` mỗi query có overhead và làm sai phép đo prepared reuse.

### 27.2. QueryOptions nên gắn với từng request

Để tránh trộn parameters giữa concurrent requests, tạo options/values mới hoặc dùng pattern bất biến được SDK bảo đảm. Không chia sẻ một mutable options builder chứa user values cho nhiều threads.

## 28. `Cluster.query` và `Scope.query`

Java SDK 3.x cung cấp API truy vấn ở nhiều entrypoints, tùy version:

~~~java
var result = cluster.query(
        SQL,
        QueryOptions.queryOptions()
                .parameters(values)
                .adhoc(false)
);
~~~

Khi dùng một `Scope` handle, có thể viết query với keyspace tương đối và Query context phù hợp:

~~~java
var scope = cluster.bucket("commerce").scope("sales");

String relativeSql = """
        SELECT META(o).id AS id, o.status
        FROM `orders` AS o
        WHERE o.customerId = $customerId
        LIMIT 20
        """;

var result = scope.query(
        relativeSql,
        QueryOptions.queryOptions()
                .parameters(
                        JsonObject.create()
                                .put("customerId", "u-42"))
                .adhoc(false)
);
~~~

Query context là một phần quan trọng của statement resolution/caching. Không dùng cùng SQL text tương đối ở nhiều scope rồi giả định kết quả hoặc prepared plan là một. Kiểm tra khả năng `Scope.query` và query context theo SDK/server version thực tế.

## 29. Async SDK cũng phải giữ query options

Ứng dụng có thể dùng `cluster.async().query(...)` để lấy `CompletableFuture` ở SDK phiên bản hỗ trợ:

~~~java
import java.util.concurrent.CompletableFuture;
import com.couchbase.client.java.query.QueryResult;

CompletableFuture<QueryResult> future =
        cluster.async().query(
                SQL,
                QueryOptions.queryOptions()
                        .parameters(values)
                        .adhoc(false)
        );
~~~

Chọn async vì kiến trúc concurrency/I-O, **không vì prepared statement chỉ hoạt động với async**. Bản blocking và async cần cùng query semantics nếu benchmark.

Đừng tạo một lượng futures không giới hạn; tổng in-flight và Query service queue có thể gây p99/timeout cao.

## 30. Reactive SDK với tham số và prepared option

Trong WebFlux/Reactor, có thể compose reactive SQL++ query:

~~~java
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import reactor.core.publisher.Flux;

Flux<JsonObject> ordersFlux =
        cluster.reactive()
                .query(
                        SQL,
                        QueryOptions.queryOptions()
                                .parameters(values)
                                .adhoc(false)
                )
                .flatMapMany(result -> result.rowsAsObject());
~~~

Cần chú ý:

- Publisher được thực thi theo subscription, không phải lúc biến được tạo.
- Mỗi request cần `values`/`QueryOptions` riêng; dùng `Mono.defer` nếu phải tạo params tại subscription.
- Reactive backpressure giúp quản lý luồng Java, không tự cắt Query service index scan khi SQL++ không có LIMIT/predicate.
- `collectList()` sẽ materialize toàn bộ rows; chỉ dùng khi result count đã bị giới hạn hợp lý.
- Không `block()` trên WebFlux event loop.
- Bật `adhoc(false)` không tự làm một query chậm vì scan hàng triệu rows trở nên nhanh.

### 30.1. Kiểm soát số query đồng thời

Nếu pipeline `Flux.fromIterable(customers).flatMap(id -> query(...), 64)`, số 64 là giới hạn một pipeline, không phải giới hạn toàn hệ thống. Đo tổng Query requests, queueing, retries và server CPU khi chọn concurrency.

## 31. Prepared plan, timeout và retries

Đặt một query timeout hay client-side timeout không thay đổi TTL của document hoặc tạo khả năng retry an toàn cho mọi query.

Với `SELECT` read-only, một retry sau transient error có thể hợp lệ theo contract, nhưng cần:

- Timeout budget tổng hợp.
- Bounded retries/backoff/jitter theo design.
- Cancellation và in-flight control.
- Tránh retry storm làm Query service quá tải.
- Đối chiếu consistency để tránh trả dữ liệu quá cũ ngoài yêu cầu.

Với SQL++ `UPDATE`/`DELETE`/`INSERT` có side effects, **không blind retry sau ambiguous timeout** chỉ vì query được parameterized/prepared. Phải xét idempotency, transaction và trạng thái server có thể đã thay đổi.

## 32. Scan consistency không được thay để tăng cache hit

Query `NOT_BOUNDED`, `REQUEST_PLUS` hoặc các cơ chế consistency khác có thể có chi phí và độ mới khác nhau:

~~~java
import com.couchbase.client.java.query.QueryScanConsistency;

var options = QueryOptions.queryOptions()
        .parameters(values)
        .adhoc(false)
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS);
~~~

`REQUEST_PLUS` có thể cần đợi Index service phản ánh mutation theo contract. Nó **không phải chức năng buộc plan cache hit** và không nhất thiết giảm latency.

Để benchmark prepared versus ad hoc, giữ **cùng scan consistency**. Không dùng `NOT_BOUNDED` cho candidate khi baseline yêu cầu `REQUEST_PLUS` rồi gọi đó là cải thiện hiệu năng thuần.

### 32.1. KV read-after-write khác SQL++ index visibility

Với exact document ID sau khi upsert, KV GET thường tránh phụ thuộc secondary index. Nếu một service vừa ghi order rồi truy vấn theo customer/status, Index service và scan consistency trở thành yếu tố cần đo. Prepared plan chỉ giải quyết kế hoạch query, không thay quy tắc mới/cũ của index.

## 33. Prepared plan không làm giảm bytes response mặc nhiên

Hai query giống logic, một có `adhoc(false)`, một ad hoc, vẫn trả cùng field/result count. Kích thước result bytes phụ thuộc `SELECT` projection, pagination, dữ liệu và compression; không vì plan được chuẩn bị mà payload tự nhỏ lại.

Nếu muốn giảm bytes, xem:

- `SELECT` vài field thay vì `SELECT o.*`.
- Covering index khi có thể để giảm Fetch.
- `LIMIT` và keyset pagination.
- KV `lookupIn` nếu biết exact document key và chỉ cần ít path.
- Tránh JOIN/UNNEST tạo quá nhiều rows.

Không đổi đồng thời projection và `adhoc(false)` khi mục tiêu benchmark là đo riêng prepared-plan overhead, trừ khi có ma trận thí nghiệm tách được hiệu ứng.

## 34. Metrics cần thu để đánh giá prepared plan

| Tầng | Metric | Vì sao cần |
| --- | --- | --- |
| HTTP | p50/p95/p99 | Tác động tới người dùng |
| SDK query | p50/p95/p99 | Chi phí data access |
| Query service | Request latency, service/queue time | Phân rã bottleneck |
| Query prepare | Số lần chuẩn bị/cache hit nếu telemetry cung cấp | Có reuse thật không |
| Index | Entries scanned, fetch count | Có query cost lớn hơn plan cost không |
| Application | CPU/GC/allocations | Mapping/serialization |
| Network | Request/result bytes | Parameter payload khác nhau? |
| Throughput | Completed goodput/s | Có tăng business capacity không |
| Error | Timeout, retry, stale-plan errors | Có regression vận hành không |

**Metric name và khả năng nhìn thấy plan-cache hit phụ thuộc server/SDK**. Nếu không có counter đáng tin, ghi rõ rằng bạn chỉ quan sát latency/plan behavior, không tự tuyên bố “cache hit 99%”.

### 34.1. Tách warm và cold measurements

Nếu benchmark A chạy trước tạo cache nóng, B chạy sau được hưởng lợi, so sánh thiếu công bằng. Tái lập vòng đời cache theo cùng quy tắc, đo cold separately và warm steady-state separately, chạy nhiều lượt đảo thứ tự A/B khi phù hợp.

## 35. Thiết kế benchmark `adhoc(true)` so với `adhoc(false)`

Một thí nghiệm hợp lý:

~~~text
Use case: recent order summaries
Statement shape: giống nhau
Parameters: thay customerId/status/tenantId theo phân bố thật
Dataset: đủ lớn, index đã online
Query consistency: giống nhau
Result projection: giống nhau
Load: 100 / 300 / 600 req/s
Phases:
  A: parameterized, ad hoc execution
  B: parameterized, prepared via adhoc(false)
Kiểm soát:
  warm-up, connection reuse, JVM, cluster, network, GC
Đo:
  query p50/p95/p99, goodput, retry/error rate,
  Query CPU/queue, prepare behavior, scan/fetch, bytes
~~~

Cần phân biệt:

1. **Cold preparation cost:** lần đầu chưa có plan.
2. **Warm repeated cost:** nhiều lần gọi cùng shape.
3. **Plan invalidation behavior:** sau index/schema thay đổi trong môi trường test.
4. **Parameter skew:** status/customer phân bố không đều.
5. **Concurrent load:** query throughput và queueing ở nhiều users.

Không đo một query ba lần ở local rồi kết luận prepared plan “tiết kiệm X%” toàn production.

### 35.1. Giá trị minh họa, không phải benchmark thực tế

| Metric | Parameterized ad hoc | Parameterized prepared |
| --- | ---: | ---: |
| p50 query | 17 ms | 15 ms |
| p95 query | 48 ms | 43 ms |
| p99 query | 115 ms | 109 ms |
| Goodput | 295 req/s | 298 req/s |
| Unexpected errors | 0,3% | 0,3% |
| Scan entries/query | 60 | 60 |
| Logical response bytes | 6 KiB | 6 KiB |

Các con số **giả định để học cách đọc kết quả**. Chúng cho thấy prepared có thể cải thiện latency một phần trong khi scan/bytes không đổi. Nếu query scan tốn hàng trăm mili giây, tiết kiệm plan compilation vài ms có thể không đáng kể.

## 36. Tình huống nâng index làm prepared plan cần refresh

Một release thêm index mới:

~~~sql
CREATE INDEX ix_orders_customer_recent
ON `commerce`.`sales`.`orders` (
    customerId,
    createdAtEpochMs DESC
);
~~~

Ứng dụng tiếp tục gọi prepared query cũ. Tùy version, cache/plan có thể cần invalidation hoặc query preparation lại để dùng index mới. Đừng mặc định một process Java chạy lâu tự động chuyển ngay sang index mới đúng thời điểm bạn mong muốn.

Quy trình an toàn:

1. Provision index ở staging và bảo đảm online.
2. Chạy `EXPLAIN`/profile trên query thực tế.
3. Kiểm thử output/consistency.
4. Load test trước và sau.
5. Triển khai thay đổi có monitoring.
6. Kiểm tra lỗi plan/not-found/index và latency sau rollout.
7. Cập nhật kế hoạch rollback theo môi trường/version.

**Không drop index cũ trước khi xác nhận query không còn phụ thuộc.**

## 37. Khi `adhoc(false)` không nên là ưu tiên đầu tiên

Các dấu hiệu:

- Query mới chạy một lần trong tool quản trị.
- Statement shape mỗi request khác nhau do nhiều dynamic fragments.
- Query đang full scan hàng triệu entries vì thiếu index.
- Query fetch full JSON lớn vì `SELECT *`.
- Query trả hàng trăm nghìn rows không có LIMIT.
- App tạo `Cluster.connect()` mới cho mỗi request.
- Số query variants lớn làm plan cache không ổn định.
- Workload bị nghẽn do HTTP serialization, downstream khác hoặc hot key.

Trong các trường hợp đó, phải sửa query shape, index, projection, pagination, connection reuse hoặc data modeling trước. Prepared plan là **một đòn bẩy nhỏ nhưng đúng chỗ**, không phải thay thế tối ưu cơ bản.

## 38. Troubleshooting

| Triệu chứng | Khả năng | Cách chẩn đoán |
| --- | --- | --- |
| Query lỗi syntax khi ID có dấu nháy | Chèn literal string | Dùng named/positional binding |
| Query không lọc theo giá trị truyền | Viết `'$id'` thay vì `$id` | Bỏ quotes quanh parameter |
| Query filter sai khi null | NULL khác bỏ predicate | Hai templates hoặc logic rõ |
| Parameter bind không nhận | Key JsonObject có `$` hoặc thiếu key | Dùng tên không có `$` |
| `$1`/`$2` bị đảo giá trị | Positional order sai | Test array order |
| Query không chọn collection | Cố bind identifier | Allowlist và quote keyspace |
| Prepared không nhanh hơn | Scan/fetch/index bottleneck | EXPLAIN và Query metrics |
| Cold query chậm hơn | Chuẩn bị plan lần đầu | Tách cold/warm benchmark |
| Sau index rollout query lỗi | Cached plan/index invalidation | Kiểm tra reprepare/version |
| Nhiều query shapes | Dynamic SQL string | Chốt số templates |
| Plan tệ với status phổ biến | Skew/selectivity | Benchmark values khác nhau |
| DTO projection vẫn fetch full entity | Mapping/SELECT thực tế rộng | Ghi statement, EXPLAIN |
| Repo không có `adhoc` option | Abstraction không expose như SDK | Custom SDK gateway khi cần |
| Query `REQUEST_PLUS` chậm | Đợi index visibility | Giữ consistency, xem index lag |
| p99 tăng khi concurrency cao | Query queue/client overload | Giới hạn in-flight |
| Timeout bị coi là empty list | Catch-all lỗi | Tách error và no-results |
| Cache result sai tenant | Authorization/cache key sai | Lấy tenant từ auth context |
| Query trả quá nhiều rows | Không LIMIT/pagination | Bounded query/paging |

## 39. Kiểm thử an toàn của parameter binding

Tạo integration test với các inputs:

- Customer ID bình thường.
- Chuỗi có dấu nháy đơn và dấu nháy kép.
- Chuỗi chứa ký tự đặc biệt, Unicode.
- Giá trị status không hợp lệ.
- `null`/empty/blank theo validation contract.
- Number đúng kiểu, giới hạn lớn/nhỏ.
- Array statuses rỗng, 1, 3, nhiều giá trị.
- Tenant ID không được phép.
- Trường hợp không có row.
- Trường hợp rất nhiều row cần LIMIT.

Đầu ra phải được xác minh theo **kết quả business**, không chỉ “query không throw exception”. Việc bind an toàn không tự giới hạn result size hoặc quyền truy cập.

### 39.1. Test injection mà không chèn raw SQL vào production path

Có thể đưa giá trị chuỗi bất thường vào **parameter** và assert nó được đối xử như dữ liệu, không như operator. Không xây query độc hại để thử trên production; kiểm thử trong collection và quyền test riêng.

## 40. Kiểm thử prepared behavior và correctness

Một test integration hữu ích:

~~~text
Arrange
  - Tạo đúng bucket/scope/collection test.
  - Provision index cần thiết, chờ online.
  - Ghi orders cho customer A, B và hai tenants.

Act
  - Gọi cùng statement với adhoc(false).
  - Thay named params theo từng request.
  - Gọi nhiều lần và dưới concurrency có giới hạn.

Assert
  - Không rò row giữa tenants/customers.
  - Status filter và ORDER BY đúng.
  - Response fields/limit đúng.
  - Query exceptions được phân loại.
  - Không có dữ liệu request A bị dùng nhầm cho request B.

Observe
  - Query latency/throughput, prepare behavior nếu có metrics.
  - EXPLAIN/profile khi cần và index plan phù hợp.
~~~

Test còn cần chú ý JSON projection/DTO mapping: SDK query trả rows không có `@Id`/type metadata của Spring Data entity theo cách repository cần. Đừng dùng raw rows như entity hoàn chỉnh khi converter/`@Version` phụ thuộc metadata.

### 40.1. Không dùng test elapsed time cố định làm assertion duy nhất

~~~java
// Anti-pattern: dễ flaky theo tốc độ CI và cache state.
assertThat(elapsedMillis).isLessThan(10);
~~~

Performance regression test nên dựa trên benchmark harness/threshold có bối cảnh và nhiều mẫu, không biến một lần query CI thành cam kết latency cứng.

## 41. Test prepared plan sau đổi index phải có scope

Nếu muốn kiểm tra reprepare:

1. Dùng môi trường test riêng, không production.
2. Tạo index ban đầu và chạy query.
3. Thực hiện thay đổi index có kiểm soát.
4. Chờ index state phù hợp.
5. Gọi query tiếp và xác minh results/correctness.
6. Quan sát lỗi/latency/plan behavior theo server version.
7. Dọn test resource đúng phạm vi.

Không tự drop index đang dùng bởi test khác. Nếu server tự reprepare, test không nên giả định số lần chuẩn bị cụ thể trừ khi có API contract/telemetry chính xác.

## 42. Ma trận quyết định API

| Nhu cầu | Công cụ |
| --- | --- |
| Một document theo key | `repository.findById` hoặc SDK KV GET |
| Query predicate, ít calls | SDK SQL++ with parameters |
| Query predicate, nhiều calls cùng shape | SDK parameters + thử `adhoc(false)` |
| Repository derived search | Spring Data binding/mapping, đo SQL++ thực |
| Tùy biến `adhoc`/consistency chính xác | Custom SDK gateway nếu API Spring Data không expose |
| Async query pipeline | `cluster.async().query` với QueryOptions |
| WebFlux non-blocking | `cluster.reactive().query` với QueryOptions |
| Dynamic WHERE theo vài cases | Một số templates cho phép, values được bind |
| Dynamic sort fields/direction | Enum/allowlisted SQL fragments |
| Query returning 1M rows | Filter/INDEX/LIMIT/pagination/streaming trước prepare |
| Query chi phí nặng do index kém | Sửa index và EXPLAIN trước |

**“Theo API hỗ trợ”** nghĩa là không cố gọi một method không có trên public abstraction. Chọn API có chức năng thật, giữ mapping và kiểm tra version trước khi dùng.

## 43. Tình huống thực hành: lịch sử đơn hàng multi-tenant

Ứng dụng có:

~~~text
commerce.sales.orders
commerce.sales.invoices
commerce.checkout.carts
~~~

API:

~~~text
GET /tenants/{tenantId}/customers/{customerId}/orders?status=PAID
GET /tenants/{tenantId}/customers/{customerId}/orders
GET /tenants/{tenantId}/orders?sort=total
GET /orders/{documentId}
~~~

**Yêu cầu:**

1. Viết SQL++ named parameters cho customerId/status/tenantId.
2. Chuyển sang positional parameters và chỉ ra vai trò `$1`, `$2`.
3. Thêm status list với `IN $statuses`; làm rõ behavior array rỗng.
4. Vì sao `FROM $collection` không phải cách bind tên collection?
5. Thiết kế enum `sort` và allowlist fragments để ngăn injection.
6. Khi status không có, nên dùng hai templates hay một OR predicate? Cần đo gì?
7. Vì sao query theo document ID nên dùng KV thay vì chuẩn bị SQL++?
8. Tạo index phục vụ tenant/customer/status/recent sort.
9. Bật `QueryOptions.adhoc(false)` trong gateway SDK và giữ options theo request.
10. Cho biết đâu là khác biệt giữa parameterization và plan reuse.
11. Vì sao `adhoc(false)` không cache kết quả của request A cho request B?
12. Nếu status `PAID` rất phổ biến và `FAILED` rất hiếm, benchmark plan như thế nào?
13. Nếu Spring Data repository không expose `adhoc`, nên làm gì?
14. Khi đổi index, prepared plan có thể gặp vấn đề nào?
15. Đo p50/p95/p99, goodput, prepare behavior, scan count và error rate ra sao?
16. Vì sao không hạ `REQUEST_PLUS` để khoe prepared query nhanh hơn?
17. Nếu muốn đổi filter tenant theo URL input, cần kiểm tra quyền ở đâu?
18. Query non-idempotent UPDATE timeout có nên blind retry vì prepared không?
19. Prepared plan cache hit ước lượng bằng gì khi server không expose metric?
20. Phác thảo rollout query/index change không làm gián đoạn production.

**Định hướng:** dùng bound values, controlled query structures, index theo predicate, prepared plan trên hot stable query và benchmark cùng consistency/error contract. Không coi prepared statement là cache kết quả hay bảo đảm an toàn truy cập dữ liệu.

## 44. Checklist trước production

- [ ] Đã xác định query có thực sự cần SQL++ hay có thể KV theo key.
- [ ] User-supplied values được bind bằng named/positional parameters.
- [ ] Không nối string values trực tiếp thành SQL++ literals.
- [ ] Placeholder không nằm trong dấu nháy đơn ngoài ý muốn.
- [ ] Key của named parameters không bao gồm dấu `$`.
- [ ] Positional parameters có thứ tự đã test.
- [ ] Số, boolean, array, null được bind đúng JSON type.
- [ ] Optional filters có semantics rõ; không xem null là bỏ predicate.
- [ ] Bucket/scope/collection, field names và ORDER BY direction được allowlist.
- [ ] Tenant ID dùng từ authorized context, không chỉ từ client input.
- [ ] Query shape được giữ ổn định với constants/templates.
- [ ] Không ép mọi query vào một OR template nếu index plan kém.
- [ ] Có benchmark cho parameter skew và query array sizes.
- [ ] `adhoc(false)` được dùng đúng SDK/API version khi có lợi.
- [ ] Không mặc định Spring Data repository/template expose adhoc setting.
- [ ] Không nhầm prepared plan reuse với caching result.
- [ ] Cold/warm plan scenarios được đo riêng.
- [ ] Prepared plan invalidation/reprepare được theo dõi trong rollout.
- [ ] Có `EXPLAIN` và query metrics về scan/fetch/order.
- [ ] Composite index phù hợp với WHERE/ORDER BY thực tế.
- [ ] Projection và LIMIT được thiết kế theo API contract.
- [ ] Scan consistency giữ nguyên trước/sau tối ưu.
- [ ] Async/reactive query kiểm soát concurrency và không block event loop.
- [ ] Mỗi request không chia sẻ mutable parameter object có user values.
- [ ] Retry/timeout phân biệt read-only và mutation side effects.
- [ ] Không tạo/đóng Cluster mỗi request.
- [ ] Latency p50/p95/p99, throughput/goodput và errors có baseline.
- [ ] Byte transfer, Query/Index CPU và plan-cache metrics được ghi theo khả năng.
- [ ] Không log raw PII/secret hoặc bind values nhạy cảm.
- [ ] Test SQL++ injection, null, Unicode, arrays, tenant isolation.
- [ ] Test query after index/schema change trên môi trường riêng.
- [ ] Có release/rollback cho index và query-template changes.
- [ ] Báo cáo kết luận dựa trên dữ liệu thật, không hứa tỷ lệ tăng tốc phổ quát.

## 45. Tổng kết

Trong **Spring Data Couchbase**, **tham số hóa SQL++** là kỹ thuật tách **values** khỏi query syntax để tránh injection, giữ query shape rõ ràng và dễ kiểm thử. Couchbase Java SDK 3.x cung cấp named/positional parameter binding qua `QueryOptions.parameters`. Nếu cùng statement được gọi lặp lại, `QueryOptions.adhoc(false)` là API quan trọng để cân nhắc **prepared plan reuse** theo hành vi SDK/Query service của phiên bản hiện tại.

Prepared plan có thể tiết kiệm công việc lập kế hoạch, **nhưng không cache rows**, không tự tạo index tốt, không thay tenant authorization hoặc consistency, và không đảm bảo kế hoạch luôn phù hợp với mọi parameter distribution. Với Spring Data repository, `@Query` và `CouchbaseTemplate`, cần kiểm tra generated SQL++ và public APIs thật trước khi giả định có cùng cờ điều khiển.

Tối ưu bền vững kết hợp **đúng đường KV/SQL++**, **parameter binding an toàn**, **query templates có kiểm soát**, **index theo predicate/sort**, **prepared plan cho hot repeated shapes**, và **benchmark cold/warm với p95/p99, throughput, errors, scan/fetch/bytes**. Chỉ khi giữ nguyên correctness, CAS/TTL, quyền truy cập và yêu cầu độ mới dữ liệu thì sự giảm độ trễ mới là cải thiện thực sự.

