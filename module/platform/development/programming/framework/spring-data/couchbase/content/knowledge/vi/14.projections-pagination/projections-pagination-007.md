# OFFSET và LIMIT khi số lượng dữ liệu tăng

Trong **Spring Data Couchbase**, truy vấn lấy một trang dữ liệu thường có dạng `LIMIT 20 OFFSET 0`. Cách này rõ ràng và thuận tiện cho bảng có nút “Trang trước / Trang sau”. Tuy nhiên, khi tập dữ liệu tăng lên hàng trăm nghìn hoặc hàng triệu document, một trang rất sâu như `LIMIT 20 OFFSET 1000000` có thể đắt hơn nhiều so với trang đầu, mặc dù kết quả chỉ có tối đa 20 hàng.

Bài học thuộc chương **Chiếu và phân trang** của module **SPRING_DATA_COUCHBASE**, trong bối cảnh xây dựng tầng truy cập Couchbase bằng document mapping, repository, `CouchbaseTemplate`, truy vấn SQL++, index và reactive API. Ta sẽ phân biệt **số hàng trả về** với **số hàng mà hệ thống phải xét trước khi trả kết quả**, sau đó chọn kỹ thuật phù hợp cho phân trang sâu.

Các mục tiêu chính:

1. Hiểu chính xác `LIMIT` và `OFFSET` vận hành trong một truy vấn SQL++ có `ORDER BY`.
2. Ước lượng vì sao chi phí tăng theo độ sâu của trang và khi nào index giúp giảm chi phí.
3. Kết hợp `Pageable`/`PageRequest` với repository Spring Data Couchbase mà không tạo câu SQL++ trùng clause.
4. Dùng `EXPLAIN` và query profiling để xem các bước scan, sort, fetch và pagination pushdown.
5. Chuyển từ offset sang keyset/cursor khi sản phẩm chỉ cần đọc tuần tự hoặc “Tải thêm”.
6. Đảm bảo thứ tự có khóa phân xử, xử lý thay đổi đồng thời, `NULL`/`MISSING`, TTL và tính mới của index.
7. Thiết kế giới hạn an toàn cho API, bài kiểm thử và chỉ số vận hành khi dữ liệu tăng.

## 1. Một ví dụ thực tế

Giả sử bucket `shop`, scope `crm`, collection `customers` chứa các document:

~~~json
{
  "fullName": "Trần Minh",
  "email": "minh@example.test",
  "active": true,
  "createdAt": "2026-11-20T08:15:00.000Z",
  "tenantId": "tenant-01"
}
~~~

Document key là `customer::42`, được lưu trong metadata Couchbase. Màn hình quản trị muốn hiển thị tối đa 20 khách hàng đang hoạt động, theo thứ tự mới nhất trước:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email,
       c.createdAt AS createdAt
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
  AND c.tenantId = "tenant-01"
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT 20 OFFSET 0;
~~~

`LIMIT 20` giới hạn số hàng được trả. `OFFSET 0` bỏ qua 0 hàng đứng đầu trong **kết quả đã được xác định thứ tự**. Với trang tiếp theo, ứng dụng tăng `OFFSET`.

Ví dụ kích thước trang là 20:

| Trang giao diện (tính từ 1) | Trang Spring Data (từ 0) | `OFFSET` | `LIMIT` |
| ---: | ---: | ---: | ---: |
| 1 | 0 | 0 | 20 |
| 2 | 1 | 20 | 20 |
| 11 | 10 | 200 | 20 |
| 1.001 | 1.000 | 20.000 | 20 |
| 50.001 | 50.000 | 1.000.000 | 20 |

Công thức:

\[
\text{offset} = \text{pageNumber} \times \text{pageSize}
\]

Với `pageNumber` bằng 50.000 và `pageSize` bằng 20, offset là 1.000.000. API vẫn chỉ nhận 20 hàng, nhưng để chọn được chúng, truy vấn có thể phải đi qua rất nhiều hàng đứng trước.

**Chú ý:** “Có thể phải xử lý `offset + limit` hàng” là cách hình dung chi phí thường gặp, **không phải khẳng định mọi câu SQL++ đều đọc nguyên vẹn từng document ở vùng bị bỏ qua**. Couchbase có thể sử dụng secondary index, đẩy `LIMIT/OFFSET` xuống Index Service hoặc tối ưu khác; số index entries quét, số body fetch và công việc sort phụ thuộc kế hoạch thực thi.

## 2. `LIMIT` và `OFFSET` thực sự làm gì?

Một query đơn giản:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.fullName ASC, META(c).id ASC
LIMIT 3 OFFSET 4;
~~~

Giả sử kết quả của `WHERE` và `ORDER BY` là:

~~~text
Vị trí 0: An    / customer::101
Vị trí 1: An    / customer::102
Vị trí 2: Bình  / customer::103
Vị trí 3: Chi   / customer::104
Vị trí 4: Dũng  / customer::105
Vị trí 5: Hà    / customer::106
Vị trí 6: Minh  / customer::107
Vị trí 7: Nam   / customer::108
~~~

Query bỏ qua bốn vị trí đầu và trả tối đa ba hàng tiếp theo:

~~~text
Dũng / customer::105
Hà   / customer::106
Minh / customer::107
~~~

Ba điều cơ bản:

- `WHERE` chọn hàng đủ điều kiện.
- `ORDER BY` xác lập thứ tự dùng để cắt trang.
- `OFFSET` bỏ qua phần đầu; `LIMIT` giới hạn phần được trả.

Trong kết quả cuối, `LIMIT 3` không có nghĩa mọi toán tử trước đó chỉ làm việc với ba hàng. Nếu query có `JOIN`, `UNNEST`, `GROUP BY`, `DISTINCT` hoặc sort cần tổng hợp, giới hạn kết quả cuối còn có thể xảy ra sau những bước xử lý đắt tiền.

### Không có `ORDER BY` thì sao?

~~~sql
SELECT META(c).id AS id
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
LIMIT 20 OFFSET 20;
~~~

SQL++ **không cam kết thứ tự hàng** khi không có `ORDER BY`. Thứ tự quét index hoặc thực thi song song không phải thứ tự nghiệp vụ. Vì vậy không có cơ sở để nói trang 1 và trang 2 là hai lát cắt tiếp nhau của một dãy ổn định.

Ngay cả với `ORDER BY c.fullName`, nhiều document trùng tên vẫn có thứ tự không xác định giữa chúng. Nên thêm khóa phân xử duy nhất, chẳng hạn:

~~~sql
ORDER BY c.fullName ASC, META(c).id ASC
~~~

Đây là điều kiện quan trọng để phân trang lặp lại được khi tập dữ liệu không thay đổi. Nó **không ngăn được vị trí bị dịch khi dữ liệu thay đổi giữa hai lần đọc**.

## 3. Vì sao trang sâu thường tốn hơn?

Hình dung một bảng danh sách có 2 triệu khách hàng và thứ tự tìm kiếm cố định:

~~~text
Trang đầu:
  Bỏ qua 0 hàng  → lấy 20 hàng.

Trang thứ 1.001:
  Bỏ qua 20.000 hàng → lấy 20 hàng.

Trang thứ 50.001:
  Bỏ qua 1.000.000 hàng → lấy 20 hàng.
~~~

Ngay cả khi index đã sắp xếp theo trường cần tìm, hệ thống vẫn cần xác định vị trí bắt đầu chính xác trong thứ tự kết quả. Khi không có một cách seek trực tiếp đến khóa của hàng đầu tiên ở trang sâu, phần việc phải đi qua nhiều kết quả trước đó có thể tăng theo offset.

Chi phí cần phân biệt:

| Loại chi phí | Điều gì có thể xảy ra khi offset tăng? |
| --- | --- |
| Index scan | Có thể phải duyệt nhiều index entries để bỏ qua các hàng đầu |
| Sort | Phải xác lập thứ tự; nếu không được index hỗ trợ, có thể phát sinh operator sort đắt |
| Document fetch | Có thể phải đọc body cho các row không được index bao phủ; số fetch tùy kế hoạch |
| Query Service | Có thể phải xử lý nhiều hàng trung gian trước khi cắt kết quả |
| Network | Payload cuối có thể vẫn chỉ 20 row; không phản ánh hết tài nguyên server đã dùng |
| Latency | Có thể tăng với độ sâu trang, độ chọn lọc điều kiện và tải hệ thống |
| COUNT | Nếu trả `Page<T>`, một query đếm tổng có thể phát sinh thêm; độc lập với chi phí OFFSET |

**Không đồng nhất** việc quét nhiều index entries với việc truyền nhiều document body về ứng dụng. Index-only/covering query có thể tránh phần fetch body, nhưng vẫn phải xét thứ tự và vị trí trang.

### Hai ví dụ để tránh kết luận sai

**Trường hợp A:** Có secondary index phù hợp, query được index bao phủ, thứ tự cũng khớp index. Couchbase có thể xử lý phần lớn công việc ở Index Service và trả ít dữ liệu về Query Service. Tuy vậy, offset sâu vẫn có thể cần duyệt một vùng index lớn.

**Trường hợp B:** Query chọn nhiều field không có trong index, sắp xếp bằng biểu thức không phù hợp index và có join. Query Service có thể cần fetch/sort rất nhiều dữ liệu trung gian; offset sâu lúc này càng đắt.

Số liệu thực tế phải lấy từ `EXPLAIN` và query profiling, không suy ra từ `LIMIT 20`.

## 4. Phân trang qua Spring Data `Pageable`

`Pageable` là yêu cầu phân trang của Spring Data; `PageRequest` là một hiện thực phổ biến:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable request = PageRequest.of(
        10,
        20,
        Sort.by(Sort.Order.desc("createdAt"),
                Sort.Order.asc("id"))
);
~~~

`PageRequest.of(10, 20, ...)` yêu cầu trang số 10 nếu đếm từ 0, tức trang thứ 11 trên giao diện, offset 200.

Các API thường dùng:

~~~java
int page = request.getPageNumber();   // 10
int size = request.getPageSize();      // 20
long offset = request.getOffset();     // 200L
Sort sort = request.getSort();         // createdAt DESC, id ASC
~~~

Kiểu `long` của `getOffset()` quan trọng: nếu tính offset bằng phép nhân trên hai số `int` trước, có thể tràn số. Tuy nhiên, ngay cả khi phép tính đúng, ứng dụng vẫn nên có giới hạn trang sâu theo nhu cầu nghiệp vụ.

### Entity và repository minh họa

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document
@Scope("crm")
@Collection("customers")
public class Customer {
    @Id
    private String id;

    private String fullName;
    private String email;
    private boolean active;
    private String createdAt;

    // Constructor và accessor phù hợp với mapping của dự án.
}
~~~

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    Page<Customer> findByActiveTrue(Pageable pageable);

    Slice<Customer> findByActive(boolean active, Pageable pageable);
}
~~~

Spring Data Couchbase có thể chuyển `Pageable` thành phân trang ở SQL++ trên các đường repository được hỗ trợ. Cần phân biệt:

- `Page<Customer>` có metadata tổng như `getTotalElements()`, `getTotalPages()`; framework có thể phải chạy count query.
- `Slice<Customer>` có `hasNext()` mà không cần tổng của cả tập, thường dựa trên việc lấy thêm một hàng.
- **Cả Page và Slice đều không xóa chi phí offset** nếu điều hướng theo số trang sâu.
- `Sort.by("id")` dùng tên property entity; khi `id` ánh xạ từ `@Id` sang document key, phải kiểm tra SQL++ sinh ra có thật sự dùng `META(c).id` hay không. Nếu không chắc, dùng custom SQL++ tường minh.

### `@Query` với `Pageable`: tránh hai nguồn phân trang

Ví dụ query phục vụ entity:

~~~java
import org.springframework.data.couchbase.repository.Query;

@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} AND active = $1")
Page<Customer> findActiveCustomers(boolean active, Pageable pageable);
~~~

Với inline query có tham số `Pageable`/`Sort`, Spring Data Couchbase có thể **tự thêm** `ORDER BY`, `LIMIT` và `OFFSET`. Không viết sẵn các clause đó rồi lại truyền `Pageable`, vì nguy cơ tạo query sai cú pháp do ghép clause hai lần.

Nếu cần kiểm soát chính xác sort theo `META().id`, có thể dùng custom repository/SDK query và **tự quản lý phân trang hoàn toàn ở một nơi**, thay vì kỳ vọng `Sort` property bất kỳ sẽ map sang biểu thức SQL++ tùy ý.

## 5. SQL++ với tham số giới hạn và offset trong Java SDK

Với query tùy chỉnh, dùng tham số để truyền giá trị:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = $active
  AND c.tenantId = $tenantId
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT $limit OFFSET $offset;
~~~

Ví dụ Java:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryResult;
import java.util.List;

import static com.couchbase.client.java.query.QueryOptions.queryOptions;

public record CustomerCard(String id, String fullName, String email) {}

// Phương thức minh họa nằm trong service/custom repository có Cluster.
public List<CustomerCard> loadPage(
        Cluster cluster,
        String tenantId,
        int page,
        int size) {

    if (page < 0 || size < 1 || size > 100) {
        throw new IllegalArgumentException("Invalid pagination");
    }

    long offset = Math.multiplyExact((long) page, (long) size);

    if (offset > 10_000) {
        throw new IllegalArgumentException(
                "Page too deep; use cursor pagination");
    }

    String statement = """
        SELECT META(c).id AS id,
               c.fullName AS fullName,
               c.email AS email
        FROM `shop`.`crm`.`customers` AS c
        WHERE c.active = TRUE
          AND c.tenantId = $tenantId
        ORDER BY c.createdAt DESC, META(c).id DESC
        LIMIT $limit OFFSET $offset
        """;

    JsonObject params = JsonObject.create()
            .put("tenantId", tenantId)
            .put("limit", size)
            .put("offset", offset);

    QueryResult result = cluster.query(
            statement,
            queryOptions().parameters(params));

    return result.rowsAsObject().stream()
            .map(row -> new CustomerCard(
                    row.getString("id"),
                    row.getString("fullName"),
                    row.getString("email")))
            .toList();
}
~~~

Chú ý các lựa chọn:

1. `size` được giới hạn để tránh một request trả hàng trăm nghìn document.
2. `offset` được tính bằng kiểu `long` và có giới hạn sản phẩm minh họa là `10_000`. Đây là **chính sách ví dụ**, không phải giới hạn SQL++ hoặc Couchbase Server.
3. `tenantId`, `limit`, `offset` được bind làm **giá trị**. Định danh bucket/scope/collection và biểu thức `ORDER BY` phải đến từ cấu hình/allowlist đáng tin cậy, không ghép input tùy ý vào câu SQL++.
4. `SELECT` chỉ chọn ID, tên, email để giảm payload; document key lấy qua `META(c).id`.
5. `createdAt` dùng để sắp xếp dù không nằm trong payload trả; cursor pagination sau này phải lấy được giá trị sort để tạo cursor.
6. `rowsAsObject()` đúng vì result row của `SELECT ... AS ...` là JSON object. Với `SELECT RAW` trả scalar, phải chọn API giải mã khác.

Đoạn ví dụ tập trung vào một trang số. Khi tích hợp thực tế, cần kiểm soát timeout, lỗi server, quyền truy cập, tính nhất quán truy vấn và giám sát query.

## 6. Những điều index có thể tối ưu và không thể tự giải quyết

Secondary index giúp Couchbase tìm document theo predicate và có thể hỗ trợ thứ tự. Ví dụ index ứng viên:

~~~sql
CREATE INDEX ix_customers_active_created
ON `shop`.`crm`.`customers` (active, createdAt DESC);
~~~

Với truy vấn:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT 20 OFFSET 20000;
~~~

Index trên là **ứng viên để đánh giá**, chưa bảo đảm toàn bộ query dùng index order hoặc covering index. Các field `fullName`, `email` không nằm trong danh sách khóa index đã khai báo; optimizer có thể cần `Fetch`. Thành phần thứ tự phụ `META(c).id DESC` và thứ tự trong index cũng ảnh hưởng việc optimizer có push down sort/pagination hay không.

Nếu workload thực sự đòi hỏi tối ưu cùng một query, có thể cân nhắc index bao phủ thêm field trả về, nhưng điều đó tăng dung lượng và chi phí cập nhật index. Hãy dùng kế hoạch và phép đo trước khi quyết định.

### Pagination pushdown

Couchbase có khả năng **đẩy** một số phép toán `LIMIT`, `OFFSET`, lọc hoặc sort vào Index Service khi điều kiện thích hợp. Điều này có thể làm giảm số row chuyển tới Query Service và các bước xử lý trung gian.

Nhưng **không nên suy rằng có index là `OFFSET 1000000` lập tức rẻ**. Indexer vẫn phải xử lý việc định vị vùng sau offset theo cách mà kế hoạch đã chọn. Các điều kiện như `JOIN`, `DISTINCT`, index intersection, sort không theo index hoặc residual predicate có thể cản trở pushdown.

Vì vậy phải kiểm tra **query plan thực tế**, không chỉ xem `CREATE INDEX` hay giá trị `LIMIT`.

## 7. Đọc `EXPLAIN` và query profile

Đo riêng truy vấn trang đầu và trang sâu:

~~~sql
EXPLAIN
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT 20 OFFSET 0;
~~~

~~~sql
EXPLAIN
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT 20 OFFSET 20000;
~~~

Khi xem kế hoạch và profiling, hỏi:

- **Index scan:** index nào được chọn; có quét nhiều entries không?
- **`Fetch`:** Query Engine có cần tải body document để lấy field hoặc xử lý predicate không?
- **`Order`:** có phép sort tại Query Service hay thứ tự được cung cấp bởi index?
- **`Limit`/`Offset`:** được xử lý ở operator nào; có bằng chứng pagination pushdown không?
- **`covers`:** các biểu thức select/filter/order được index bao phủ đến đâu?
- **Số hàng trung gian:** operator nào đọc/trả nhiều hàng, dù kết quả cuối chỉ có 20?
- **Độ trễ:** `elapsedTime`, `executionTime` và thời gian từng operator (nếu profiling bật) tăng thế nào?

Không nên đánh giá hiệu năng từ một lệnh `EXPLAIN` duy nhất. `EXPLAIN` mô tả kế hoạch dự kiến; query profiling và metrics trong workload mới cho biết **thời gian và số hàng thật**. Hãy lấy kết quả ở trang 0, trang 100, trang 1.000 và giới hạn sâu nhất sản phẩm cho phép, trên các bộ lọc có độ chọn lọc khác nhau.

### Bảng đo minh họa cần lập

| Phép đo | Trang đầu | Trang giữa | Trang rất sâu |
| --- | --- | --- | --- |
| `LIMIT` | 20 | 20 | 20 |
| `OFFSET` | 0 | 2.000 | 200.000 |
| Latency p50 / p95 | Đo thực tế | Đo thực tế | Đo thực tế |
| Index entries quét | Đo thực tế | Đo thực tế | Đo thực tế |
| Số row qua `Fetch`/`Order` | Đo thực tế | Đo thực tế | Đo thực tế |
| Response bytes | Đo thực tế | Đo thực tế | Đo thực tế |

Không điền các số liệu hiệu năng ước đoán vào báo cáo như thể đó là benchmark thật: độ lớn dữ liệu, cấu hình index, hạ tầng và tải thay đổi kết quả đáng kể.

## 8. Một lỗi khác của OFFSET: trang bị trôi khi dữ liệu đổi

Giả sử `ORDER BY c.createdAt DESC, META(c).id DESC` tạo thứ tự rõ ràng, page size là 3:

~~~text
Ban đầu:
A  B  C  D  E  F  G

Client lấy trang 0 (OFFSET 0):
A  B  C
~~~

Giữa hai request, một document mới `X` được chèn vào đầu:

~~~text
Sau khi chèn:
X  A  B  C  D  E  F  G

Client lấy trang 1 (OFFSET 3):
C  D  E
~~~

`C` xuất hiện lần hai. Không có lỗi trong `ORDER BY` hoặc SQL++; vấn đề là vị trí tương đối đã thay đổi.

Ngược lại, nếu một hàng ở trước offset bị xóa:

~~~text
Ban đầu:
A  B  C  D  E  F  G

Trang 0 đã lấy:
A  B  C

B bị xóa:
A  C  D  E  F  G

Trang 1 với OFFSET 3:
E  F  G
~~~

`D` bị bỏ qua mặc dù client chưa nhìn thấy nó.

Thứ tự có khóa phân xử **chỉ ổn định khi so sánh trên cùng một tập kết quả**. Insert, delete, TTL hoặc update field sắp xếp vẫn có thể gây trùng/bỏ sót khi dùng offset giữa nhiều request.

### Thay đổi field sắp xếp còn phức tạp hơn

Nếu sort theo `fullName` hoặc `score`, một document có thể chuyển từ phía sau offset lên phía trước (hoặc ngược lại) khi được cập nhật. Bởi vậy ngay cả keyset pagination cũng không tự bảo đảm mỗi document chỉ xuất hiện đúng một lần trong toàn phiên duyệt khi khóa sort thay đổi.

Trong hệ thống cần xử lý một tập document **bất biến theo snapshot**, phải có thiết kế riêng cho snapshot, lịch sử hoặc lô xử lý; `ORDER BY`/`OFFSET` không tạo bảo đảm đó.

## 9. Keyset pagination: di chuyển theo khóa, không theo số hàng bỏ qua

Với UI “Tải thêm”, feed hoặc export theo lô, một lựa chọn là **keyset pagination** (*seek pagination*). Thay vì truyền `pageNumber` và `OFFSET`, client gửi giá trị của **hàng cuối đã thấy** làm cursor.

Chọn thứ tự dễ dự đoán:

~~~sql
ORDER BY c.createdAt DESC, META(c).id DESC
~~~

Giả sử ứng dụng quy định `createdAt` luôn có mặt, là chuỗi ISO-8601 UTC chuẩn hóa, và không thay đổi sau khi tạo document. Đây là **ràng buộc dữ liệu do ứng dụng áp đặt** để cursor dễ so sánh; nếu document thiếu/null hoặc string không chuẩn, cần quy tắc riêng.

### 9.1. Trang đầu

~~~sql
SELECT META(c).id AS id,
       c.createdAt AS createdAt,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
  AND c.createdAt IS NOT MISSING
  AND c.createdAt IS NOT NULL
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT 21;
~~~

Giả sử page size 20: yêu cầu 21 hàng để có thể biết có hàng kế tiếp. Trả tối đa 20 hàng cho client; nếu có hàng thứ 21 thì `hasNext=true`.

**Cursor phải lấy từ hàng thứ 20 cuối cùng đã hiển thị**, không lấy từ hàng thứ 21 dùng để nhìn trước.

Ví dụ cursor logic:

~~~json
{
  "afterCreatedAt": "2026-11-20T08:15:00.000Z",
  "afterId": "customer::42"
}
~~~

### 9.2. Trang tiếp theo

Vì cả hai khóa sort đều `DESC`, “đứng sau cursor” nghĩa là giá trị nhỏ hơn theo thứ tự so sánh:

~~~sql
SELECT META(c).id AS id,
       c.createdAt AS createdAt,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
  AND c.createdAt IS NOT MISSING
  AND c.createdAt IS NOT NULL
  AND (
      c.createdAt < $afterCreatedAt
      OR (
          c.createdAt = $afterCreatedAt
          AND META(c).id < $afterId
      )
  )
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT 21;
~~~

Điều kiện gồm hai nhánh:

1. Lấy những document có `createdAt` nhỏ hơn `afterCreatedAt`.
2. Với cùng `createdAt`, chỉ lấy document có key nhỏ hơn `afterId`.

Nếu thứ tự `ASC`, so sánh “sau cursor” thường là `>`. Với hỗn hợp `createdAt DESC, id ASC`, dấu cho thời gian là `<` còn dấu cho ID là `>`. **Dấu so sánh phải khớp từng hướng trong `ORDER BY`**.

### 9.3. Vì sao cursor cần khóa phụ?

Nếu cursor chỉ giữ `createdAt`, mọi document có cùng thời điểm tạo nhưng chưa được hiển thị có thể bị bỏ qua khi page break nằm giữa nhóm timestamp trùng nhau. Thêm `META(c).id` làm khóa phân xử duy nhất trong collection, đồng thời giữ đủ cặp khóa trong cursor.

Với query `JOIN`/`UNNEST` sinh nhiều row cho một document, document key có thể trùng giữa các row; lúc đó cần một khóa phân xử duy nhất cho **row kết quả**, không chỉ cho document nguồn.

### 9.4. Keyset không phải lúc nào cũng nhanh

Query chứa `OR` và điều kiện range có thể được optimizer/index xử lý khác nhau. Một index được thiết kế cho `WHERE` và `ORDER BY` có thể giúp seek hiệu quả, nhưng cần `EXPLAIN` trên phiên bản Server đang sử dụng.

Keyset cũng không thuận tiện khi người dùng muốn nhảy trực tiếp đến trang 500 mà không có cursor của trang trước. Chọn kỹ thuật theo UX, index và đo đạc, không áp dụng như một khẩu hiệu “keyset luôn nhanh”.

## 10. Ví dụ custom repository trả trang cursor

Để tránh làm mờ sự khác biệt giữa `Pageable` và cursor, có thể định nghĩa một hợp đồng riêng:

~~~java
import java.util.List;

public record CustomerCard(
        String id, String createdAt, String fullName, String email) {}

public record CustomerCursor(
        String createdAt, String id) {}

public record CursorPage(
        List<CustomerCard> items,
        boolean hasNext,
        CustomerCursor nextCursor) {}
~~~

Đoạn service/custom repository minh họa:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryResult;
import java.util.List;

import static com.couchbase.client.java.query.QueryOptions.queryOptions;

public CursorPage loadCustomerFeed(
        Cluster cluster,
        String tenantId,
        int size,
        CustomerCursor after) {

    if (size < 1 || size > 100) {
        throw new IllegalArgumentException("Invalid size");
    }
    if (after != null &&
        (after.createdAt() == null || after.id() == null)) {
        throw new IllegalArgumentException("Invalid cursor");
    }

    // Hai đoạn SQL++ do ứng dụng sở hữu, không nhận syntax từ client.
    String cursorPredicate = after == null ? "" : """
        AND (
            c.createdAt < $afterCreatedAt
            OR (
                c.createdAt = $afterCreatedAt
                AND META(c).id < $afterId
            )
        )
        """;

    String statement = """
        SELECT META(c).id AS id,
               c.createdAt AS createdAt,
               c.fullName AS fullName,
               c.email AS email
        FROM `shop`.`crm`.`customers` AS c
        WHERE c.active = TRUE
          AND c.tenantId = $tenantId
          AND c.createdAt IS NOT MISSING
          AND c.createdAt IS NOT NULL
        """ + cursorPredicate + """
        ORDER BY c.createdAt DESC, META(c).id DESC
        LIMIT $limit
        """;

    JsonObject params = JsonObject.create()
            .put("tenantId", tenantId)
            .put("limit", size + 1);

    if (after != null) {
        params.put("afterCreatedAt", after.createdAt());
        params.put("afterId", after.id());
    }

    QueryResult result = cluster.query(
            statement,
            queryOptions().parameters(params));

    List<CustomerCard> fetched = result.rowsAsObject()
            .stream()
            .map(row -> new CustomerCard(
                    row.getString("id"),
                    row.getString("createdAt"),
                    row.getString("fullName"),
                    row.getString("email")))
            .toList();

    boolean hasNext = fetched.size() > size;
    List<CustomerCard> visible = hasNext
            ? fetched.subList(0, size)
            : fetched;

    CustomerCursor nextCursor = hasNext
            ? new CustomerCursor(
                    visible.get(visible.size() - 1).createdAt(),
                    visible.get(visible.size() - 1).id())
            : null;

    return new CursorPage(visible, hasNext, nextCursor);
}
~~~

Điểm đáng chú ý:

- Code không dùng `OFFSET`; nó chọn dữ liệu đứng sau cursor.
- `size+1` giúp biết `hasNext` mà không cần `COUNT`.
- Có `tenantId` trong cả trang đầu và trang sau để giữ cùng bộ lọc.
- Các giá trị cursor được bind; không nối dữ liệu người dùng vào cú pháp SQL++.
- `CursorPage` không hứa biết tổng số trang hay cho phép nhảy tới trang bất kỳ.
- Cursor dùng lại với tenant/filter/sort khác là không hợp lệ; ở API thực tế nên đóng gói các thông tin đó vào token được xác thực hoặc kiểm tra khi nhận request.
- Vì `createdAt` là string, ứng dụng phải quy định format UTC đồng nhất. Nếu có định dạng, múi giờ hoặc độ chính xác khác nhau, thứ tự chuỗi có thể không tương ứng thứ tự thời gian.

Ví dụ chỉ thể hiện cơ chế phân trang, chưa có validation nghiệp vụ đầy đủ, xử lý lỗi kết nối, consistency và chính sách retry. Những phần này cần bổ sung trong ứng dụng sản xuất.

## 11. `NULL`, `MISSING` và phép so sánh cursor

Với Couchbase, một field có thể:

- Có giá trị cụ thể: `"2026-11-20T08:15:00.000Z"`.
- Có mặt nhưng là `NULL`.
- Không tồn tại trong body: `MISSING`.

`ORDER BY` có quy tắc xử lý các giá trị này; điều kiện range trong keyset cũng phải tương thích với thứ tự đó. Ví dụ:

~~~sql
WHERE c.createdAt IS NOT MISSING
  AND c.createdAt IS NOT NULL
~~~

Trong ví dụ này, ta cố ý chỉ duyệt document có timestamp hợp lệ. Nếu nghiệp vụ buộc phải hiển thị cả các document thiếu `createdAt`, cần thiết kế khóa sắp xếp chuẩn hóa hoặc nhiều nhánh cursor để không bỏ sót.

Ngoài ra, JSON cho phép các kiểu dữ liệu khác nhau. Nếu có document lưu `createdAt` dạng số, có document lưu chuỗi ISO-8601, thứ tự SQL++ có thể không tương ứng với thứ tự thời gian nghiệp vụ. Hãy thống nhất kiểu lưu trữ và migration dữ liệu trước khi dựa vào keyset.

Cần kiểm thử các giá trị biên:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Hai document cùng `createdAt` | Khóa `META(c).id` phân xử đúng |
| Timestamp thiếu | Document có bị loại theo chính sách không |
| Timestamp `null` | Cursor có xử lý đúng hay bị lọt/mất |
| Timestamp lưu sai kiểu | Query có thứ tự bất ngờ không |
| Timestamp bị sửa sau khi hiển thị | Document có thể chuyển phía cursor và bị lặp/bỏ sót |
| Cursor chứa khóa không còn tồn tại | Điều kiện theo giá trị sort vẫn có thể chạy; cần quy tắc API rõ |

Với tên người dùng/chuỗi có dấu tiếng Việt, thứ tự so sánh SQL++ có thể không giống collation ngôn ngữ mong muốn. Nếu sort theo tên có yêu cầu ngôn ngữ, nên có khóa sort chuẩn hóa và index phù hợp, không dùng tên hiển thị làm cursor khi quy tắc so sánh chưa được thống nhất.

## 12. OFFSET, Slice, Page và chi phí COUNT là những việc riêng

Giả sử API có giao diện chuyển trang bằng số:

~~~java
Page<Customer> page =
        repository.findByActiveTrue(
            PageRequest.of(250, 20, Sort.by("createdAt").descending()));
~~~

`Page<T>` cung cấp `getTotalElements()` và `getTotalPages()`. Để có tổng số, Spring Data thường cần query `COUNT` hoặc có thể suy ra tổng trong một số tình huống. Truy vấn đếm theo bộ lọc có thể là phần đáng kể của độ trễ.

Trong khi đó:

~~~java
Slice<Customer> slice =
        repository.findByActive(
            true,
            PageRequest.of(250, 20, Sort.by("createdAt").descending()));
~~~

`Slice<T>` chỉ cần nội dung và `hasNext()`, thường dùng look-ahead `pageSize + 1`. **Nhưng** vì vẫn có `PageRequest.of(250, 20, ...)`, query vẫn có thể dùng offset 5.000.

Chuyển `Page` sang `Slice` có thể giảm chi phí `COUNT`, **không tự chữa chi phí offset sâu**.

| Thiết kế | Query dữ liệu | Query đếm | Phù hợp |
| --- | --- | --- | --- |
| `Page<T>` + offset | `LIMIT/OFFSET` | Có thể cần | Bảng có tổng và điều hướng trang số |
| `Slice<T>` + offset | Giới hạn kèm look-ahead | Thường không | Danh sách theo trang số không cần total |
| Custom cursor + look-ahead | Range predicate theo khóa sort | Không cần cho `hasNext` | Feed, “Tải thêm”, duyệt tiếp |
| Export theo lô với checkpoint | Range/cursor theo thứ tự cố định | Tùy nghiệp vụ | Job lớn, cần resume và kiểm soát tài nguyên |

Nếu UI chỉ có nút “Tải thêm”, hãy hỏi lại vì sao API phải tính tổng trên mọi request. Nếu UI cần nhảy đến trang 50 bất kỳ, offset có thể vẫn là lựa chọn hợp lý, kèm giới hạn và đo hiệu năng.

## 13. Query đếm tổng khi dữ liệu lớn

Một count query có thể là:

~~~sql
SELECT COUNT(1) AS total
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
  AND c.tenantId = $tenantId;
~~~

`COUNT(1)` tính số hàng khớp bộ lọc, không phụ thuộc `LIMIT/OFFSET` của trang hiện tại. Nó có thể được index hỗ trợ, nhưng vẫn có chi phí quét hoặc aggregation tùy kế hoạch.

Những vấn đề cần tránh:

1. **Count bỏ bộ lọc:** query dữ liệu có `tenantId`, `active`, type discriminator mà count không có → tổng sai và có nguy cơ lộ thông tin.
2. **Đếm sau join khác số entity:** nếu query dùng `JOIN`/`UNNEST`/`DISTINCT`, phải xác định total mong muốn là số row kết quả hay số document duy nhất.
3. **Count và data query khác thời điểm:** hai query độc lập không mặc nhiên cùng một snapshot.
4. **Count trên mỗi lần scroll:** tạo thêm tải vô ích khi UI không hiển thị tổng.
5. **Cache count không có chính sách:** số tổng có thể cũ; cần xác định TTL, key cache theo tenant/filter và độ chính xác chấp nhận được.

Một số tối ưu có thể cân nhắc:

- Dùng `Slice` hoặc cursor khi chỉ cần `hasNext`.
- Tính tổng khi người dùng thật sự yêu cầu.
- Cache tổng theo bộ lọc ổn định và thông báo độ cũ nếu cần.
- Dùng giá trị ước lượng trong dashboard nếu nghiệp vụ chấp nhận, ghi rõ là **ước lượng**.
- Thiết kế index cho count theo workload thật sau khi xem `EXPLAIN`.

## 14. Scan consistency và dữ liệu vừa ghi

Couchbase Query Service có các mức scan consistency. Truy vấn dùng secondary index có thể chưa phản ánh ngay mutation vừa xảy ra nếu chính sách consistency cho phép dữ liệu index chưa bắt kịp.

Ví dụ luồng:

1. Service thêm khách hàng mới.
2. Service ngay lập tức query trang đầu với `ORDER BY createdAt DESC`.
3. Tùy consistency, query có thể chưa thấy khách hàng vừa ghi.

Khi nghiệp vụ cần nhìn thấy thay đổi gần đây, cần chọn cơ chế scan consistency phù hợp (chẳng hạn `REQUEST_PLUS` trong những trường hợp yêu cầu), chấp nhận rằng độ trễ có thể tăng do chờ index cập nhật.

Điều này **không tạo một snapshot chung cho nhiều trang**. Một query ở 10:00 và query tiếp theo ở 10:02 vẫn có thể thấy các trạng thái dữ liệu khác nhau, dù mỗi query riêng lẻ tuân theo mức nhất quán yêu cầu.

### TTL và xóa document

Nếu document có TTL và hết hạn giữa hai lần lấy trang, thứ tự tập kết quả sẽ thay đổi. Với offset, những hàng phía sau có thể bị nhảy qua; với cursor, hàng hết hạn đơn giản không còn được trả, nhưng toàn bộ lịch sử duyệt vẫn không được bảo đảm như snapshot.

### CAS và keyset là hai cơ chế khác nhau

CAS dùng optimistic concurrency cho **một document**, không phải token định vị trang hay timestamp toàn cục. Cursor keyset nên dựa trên **khóa sắp xếp và khóa phân xử**; không sắp xếp bằng CAS để mô phỏng “mới nhất” hoặc để kỳ vọng snapshot nhất quán.

Nếu trang có thao tác cập nhật từng hàng, có thể giữ version token riêng cho mutation, tách với cursor dùng cho phân trang.

## 15. Index pushdown không thay thế việc giới hạn API

Ngay cả khi query hiện tại đã nhanh trên 100.000 document, lượng dữ liệu có thể tăng gấp 10 hoặc 100 lần. Chính sách giới hạn trang nên được thiết kế từ đầu:

| Điều kiện | Chính sách API minh họa | Mục đích |
| --- | --- | --- |
| `page < 0` | Trả lỗi validation | Tránh chỉ số vô nghĩa |
| `size <= 0` | Trả lỗi validation | Tránh query không hữu ích |
| `size > 100` | Từ chối hoặc giới hạn theo hợp đồng | Bảo vệ payload và tài nguyên |
| `offset > 10000` | Yêu cầu dùng cursor hoặc tính năng export | Tránh offset quá sâu |
| Sort field ngoài allowlist | Trả lỗi validation | Tránh SQL++ tùy ý và index scan ngoài dự kiến |
| Cursor không hợp lệ | Trả lỗi, yêu cầu tải trang đầu | Tránh trộn thứ tự/filter |
| Tenant không được phép | Không thực hiện query ngoài phạm vi | Bảo đảm phân quyền |

Các con số `100` và `10000` chỉ là ví dụ chính sách. Tổ chức cần quyết định theo nhu cầu UX, số liệu p95, tài nguyên Index/Query Service và lưu lượng request thực tế.

### Phân loại endpoint

- **Danh sách tương tác:** thường có page size nhỏ và số trang giới hạn.
- **Feed/infinite scroll:** cursor/keyset, không tính tổng nếu không cần.
- **Export hàng triệu hàng:** job riêng, duyệt theo batch, checkpoint/resume, timeout và chính sách snapshot.
- **Báo cáo tổng hợp:** aggregation riêng; không phân trang một danh sách chỉ để lấy tổng.

Đừng dùng endpoint danh sách tương tác làm job export vô hạn với `page++`; điều đó dễ tạo offset rất sâu, timeout và dữ liệu trùng/bỏ sót.

## 16. Reactive API có giúp OFFSET nhanh hơn không?

Không tự động. Spring Data Couchbase và Couchbase Java SDK có reactive API, nhưng `LIMIT/OFFSET` vẫn được thực thi theo kế hoạch của Couchbase Server.

Reactive có thể giúp ứng dụng tránh giữ thread trong lúc chờ IO và xử lý các kết quả theo luồng, nhưng không làm `OFFSET 1000000` thành thao tác hằng số, cũng không miễn chi phí sort, index scan hoặc count.

Với WebFlux:

- Ưu tiên API query/reactive repository tương ứng phiên bản đang dùng.
- Giới hạn số hàng mỗi query, không dựa vào backpressure để giải quyết một query không giới hạn kết quả.
- Không gọi `block()` trên event-loop xử lý request.
- Nếu dùng cursor, giữ cursor và sort nhất quán giữa các request reactive.
- Ghi nhận timeout, cancellation và thời gian query thực tế ở phía Couchbase.

Nếu cần tổng và danh sách, chạy hai query reactive song song có thể giảm thời gian chờ tổng đối với một số workload, nhưng làm tăng truy vấn đồng thời và **không tạo snapshot nhất quán**. Đánh giá tải hệ thống trước khi chọn.

## 17. Những lỗi thường gặp khi dữ liệu tăng

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Trang đầu nhanh, trang 5000 chậm | OFFSET sâu làm phát sinh nhiều scan/skip | Đo plan, giới hạn trang sâu, cân nhắc keyset |
| Trang lúc nhanh lúc chậm | Tải hệ thống, index/sort, độ chọn lọc khác nhau | So sánh cùng workload và query profile |
| Dữ liệu lặp giữa các trang | Insert trước offset hoặc sort chưa toàn phần | Thêm khóa phụ duy nhất; cân nhắc cursor |
| Bỏ sót hàng sau xóa | OFFSET bị dịch vị trí | Dùng cursor hoặc thiết kế snapshot theo yêu cầu |
| Trang không có `ORDER BY` | Thứ tự không được bảo đảm | Đặt thứ tự rõ ràng |
| Cùng `createdAt` xuất hiện nhiều hàng | Timestamp không duy nhất | Phân xử bằng `META(c).id` |
| Keyset bị mất hàng khi cùng timestamp | Cursor chỉ chứa timestamp | Giữ cả timestamp và document key |
| Keyset sai với DESC | Điều kiện cursor dùng sai dấu | Khớp `<`/`>` với từng khóa sort |
| Query trả 20 hàng nhưng server tốn nhiều IO | Không có covering index, sort/fetch đắt | `EXPLAIN`, profile và xem index |
| Đổi từ Page sang Slice nhưng vẫn chậm | Slice vẫn dùng OFFSET | Xem cursor/keyset và index |
| Count sai tổng | Predicate data/count khác nhau | Đồng bộ tenant, discriminator và filter |
| Count rất chậm | Aggregation/index scan lớn | Trì hoãn/cache count khi UX cho phép |
| SQL++ lỗi khi có `@Query` + `Pageable` | ORDER BY/LIMIT/OFFSET bị ghép trùng | Chỉ một nơi kiểm soát phân trang |
| Trang vừa ghi không hiện record mới | Index scan consistency | Chọn consistency theo nghiệp vụ |
| Dùng projection nhỏ rồi `save` | DTO không phải entity đầy đủ, có thể ghi thiếu | Tách read model và mutation theo CAS |

### Tránh ba kết luận vội

**“Có LIMIT nên query rẻ.”** Sai vì LIMIT giới hạn output, không mặc nhiên giới hạn mọi công việc trước đó.

**“Có index nên OFFSET sâu không thành vấn đề.”** Chưa đủ: cần kế hoạch cho đúng filter/order/projection và đo độ sâu thật.

**“Dùng cursor nên dữ liệu không bao giờ lặp.”** Chưa đủ: cursor giảm rủi ro offset drift nhưng update trường sort, thay đổi filter và index consistency vẫn có thể làm tập kết quả biến động.

## 18. Cách benchmark hữu ích

Thử nghiệm phải gắn với workload thực tế, không chỉ một lần chạy query ở trang đầu.

### Chuẩn bị

- Tập dữ liệu tăng theo các cỡ, ví dụ 10.000, 100.000 và 1.000.000 document.
- Có trường hợp filter trả nhiều và ít kết quả.
- Có dữ liệu trùng `createdAt` để kiểm tra khóa phân xử.
- Có tenant khác nhau và field thiếu/null để đánh giá lọc, index và sort.
- Duy trì cùng loại index và cấu hình consistency trong mỗi phép so sánh.

### Các phép thử

1. `LIMIT 20 OFFSET 0`, `OFFSET 2000`, `OFFSET 20000`, `OFFSET 200000`.
2. Cùng query với sort được index hỗ trợ và sort buộc Query Service xử lý thêm.
3. Truy vấn có projection ba field và truy vấn trả body nhiều field.
4. `Page` có count so với `Slice` không cần count.
5. Offset so với cursor/keyset theo timestamp và ID.
6. Query sau mutation với consistency phù hợp.
7. 10, 50, 100 request đồng thời nếu sát lưu lượng dự kiến.
8. Trường hợp insert/xóa/update/TTL giữa các lần lấy trang.

### Kết quả nên ghi

| Chỉ số | Ý nghĩa |
| --- | --- |
| p50, p95, p99 latency | Trải nghiệm thông thường và trường hợp chậm |
| Rows returned | Số hàng trả về client |
| Index entries scanned | Công việc phía index |
| Documents fetched | Số body phải lấy từ Data Service nếu có |
| Sort/Fetch operator time | Điểm nghẽn trong Query Service |
| Query/count request count | Có chạy thêm COUNT không |
| Response size | Payload thực sự |
| Timeout/error rate | Rủi ro vận hành |
| Correctness (duplicate/missing) | Độ đúng qua các trang có thay đổi đồng thời |

Đo trên cùng predicate, thứ tự, dữ liệu và điều kiện tải. Không so offset query có `COUNT` với keyset query không count rồi kết luận mọi khác biệt đến từ `OFFSET`: cần tách từng yếu tố.

## 19. Bài tập thực hành

Thiết kế API danh sách khách hàng lớn với hai kiểu điều hướng.

**Nhánh A — Trang số**

- `GET /customers?page=0&size=20&sort=createdAt,desc`.
- Query SQL++ dùng `ORDER BY createdAt DESC, META(c).id DESC`.
- Dùng `LIMIT/OFFSET`, giới hạn `size` và độ sâu.
- Khi giao diện thực sự cần tổng, trả `Page` với logic count đúng bộ lọc.
- Đo latency theo `OFFSET` tăng.

**Nhánh B — “Tải thêm”**

- `GET /customers/feed?limit=20&cursor=...`.
- Query đầu lấy tối đa 21 hàng; hiển thị 20 hàng.
- Tạo cursor từ `createdAt` và document key của hàng cuối hiển thị.
- Query sau dùng bộ so sánh `<` cho cả hai khóa `DESC`.
- Trả `hasNext` mà không tính COUNT chỉ để phục vụ nút tải thêm.
- Test cursor khi nhiều document có cùng `createdAt`.

Thêm các tình huống:

1. Một document mới được chèn đầu danh sách giữa hai request; quan sát offset drift và kết quả cursor.
2. Một document phía trước offset bị xóa; quan sát việc bỏ sót hàng.
3. Một document đổi `createdAt`; giải thích vì sao keyset cũng không phải snapshot.
4. Một document hết hạn TTL; phân tích thay đổi tập kết quả.
5. Một client tăng `size` lên 100.000; xác minh API chặn request.
6. Một sort field không có trong allowlist; xác minh không bị biến thành SQL++ tùy ý.
7. Một truy vấn chỉ chọn ba field nhưng index không cover; dùng `EXPLAIN` xác định có `Fetch` không.
8. Thử trang rất sâu với index ứng viên, đọc lại query profile để kết luận bằng số liệu.

### Câu hỏi tự kiểm tra

1. `LIMIT 20 OFFSET 200000` có nhất thiết chỉ đọc 20 document không? Vì sao?
2. `PageRequest.of(100, 50)` tạo offset bằng bao nhiêu?
3. Tại sao `ORDER BY fullName` vẫn thiếu ổn định khi nhiều khách hàng cùng tên?
4. Khác biệt giữa index scan, document fetch và payload trả về là gì?
5. Khi nào Couchbase có thể đẩy `LIMIT/OFFSET` xuống Index Service?
6. Vì sao index pushdown không đồng nghĩa mọi trang sâu đều nhanh?
7. Khi có insert trước offset giữa hai request, bản ghi nào dễ bị lặp?
8. Cursor theo `createdAt DESC, id DESC` cần so sánh dấu nào?
9. Vì sao cursor phải giữ cả ID nếu `createdAt` không duy nhất?
10. Vì sao `Slice` vẫn có thể chậm ở trang sâu?
11. Vì sao query `COUNT` cần cùng predicate với query dữ liệu?
12. Khi nào nên chuyển một yêu cầu export lớn sang batch job thay vì lặp `page++`?

## 20. Tài liệu chính thức để đối chiếu

- [Couchbase SQL++ — LIMIT Clause](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/limit.html): ý nghĩa giới hạn kết quả.
- [Couchbase SQL++ — OFFSET Clause](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/offset.html): ý nghĩa bỏ qua hàng.
- [Couchbase SQL++ — ORDER BY Clause](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/orderby.html): thứ tự, ASC/DESC và xử lý NULL/MISSING.
- [Couchbase Server — Index Pushdowns](https://docs.couchbase.com/server/current/indexes/index_pushdowns.html): điều kiện Query Service có thể đẩy order, offset và limit tới Index Service.
- [Couchbase Server — EXPLAIN](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/explain.html): phân tích kế hoạch và operator của SQL++.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): tham số truy vấn, result rows và consistency.
- [Spring Data Couchbase — Couchbase Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): repository query, `Pageable` và inline `@Query`.
- [Spring Data — Query Methods](https://docs.spring.io/spring-data/couchbase/reference/repositories/query-methods-details.html): `Page`, `Slice` và ý nghĩa metadata phân trang.

Tài liệu và khả năng optimizer thay đổi theo phiên bản **Spring Data Couchbase, Couchbase Java SDK và Couchbase Server**. Hãy kiểm chứng hành vi `@Query`, index pushdown, cấu hình query và số liệu thực tế trên các phiên bản đang dùng trước khi quyết định chiến lược cho hệ thống sản xuất.

> **Ghi nhớ:** `OFFSET` mô tả “bỏ qua bao nhiêu hàng”; khi dữ liệu tăng, phần **phải xét trước khi bỏ qua** có thể trở thành chi phí chính. `LIMIT` giữ output nhỏ nhưng không mặc nhiên khiến query nhẹ. Nếu sản phẩm chỉ cần đọc tiếp tuần tự, keyset/cursor theo bộ khóa sort ổn định thường đáng thử; nếu phải nhảy trang số, dùng offset với giới hạn độ sâu, index thích hợp và đo bằng `EXPLAIN`/profiling. Cả hai đều cần xử lý thay đổi đồng thời và consistency rõ ràng.
