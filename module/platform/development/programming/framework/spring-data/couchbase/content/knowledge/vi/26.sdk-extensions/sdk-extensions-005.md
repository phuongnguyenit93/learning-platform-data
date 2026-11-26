# Full-Text Search: chỉ mục tìm kiếm và truy vấn qua SDK

Trong **Spring Data Couchbase**, Repository và `CouchbaseTemplate` thuận tiện cho CRUD document, truy vấn có điều kiện và mapping entity. Tuy nhiên, khi sản phẩm cần **tìm kiếm văn bản tự nhiên**—tìm theo từ/cụm từ, độ liên quan, highlights, facets, autocomplete hoặc tìm đồng thời trên nhiều trường—một câu SQL++ `WHERE field LIKE ...` không nhất thiết là giải pháp phù hợp.

Couchbase cung cấp **Search Service**, thường gọi là **Full-Text Search (FTS)**, với **Search index** và API tìm kiếm riêng. Couchbase Java SDK cho phép gọi `Cluster.searchQuery(...)` / `Scope.searchQuery(...)` hoặc API `search(...)` nhận `SearchRequest`. Các kết quả là **search hits** có ID, score, highlights và metadata, **không mặc nhiên là một entity Spring Data hoàn chỉnh**.

Bài thuộc chương **Mở rộng bằng SDK** của module **SPRING_DATA_COUCHBASE**: xây dựng tầng truy cập Couchbase bằng document mapping, Repository, `CouchbaseTemplate` và SQL++; hiểu thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và reactive API với yêu cầu hiệu năng, tính nhất quán và vận hành.

**Luận điểm quan trọng:** Search Service là một **đường đọc có chỉ mục chuyên dụng**. Kết quả khớp tìm kiếm có thể trễ so với document nguồn; điểm liên quan không phải thứ tự bất biến; nội dung highlight không phải dữ liệu đủ tin cậy để cập nhật hoặc cấp quyền. Hãy thiết kế **search query, mapping, bảo mật, hydration và freshness** như một hợp đồng riêng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `KV get`, SQL++/GSI và Search Service/FTS theo mục đích sử dụng.
2. Thiết kế một Search index có mapping cho scope, collection, trường văn bản, keyword, numeric và datetime.
3. Hiểu analyzer/tokenization, field mapping, stored fields và doc values phục vụ full-text, highlighting, facets và sort.
4. Sử dụng Couchbase Java SDK `SearchQuery.match`, `matchPhrase`, `prefix`, `conjuncts` và `queryString` đúng ngữ nghĩa.
5. Phân biệt **global Search index** với **scoped Search index**, gọi đúng API `Cluster` hoặc `Scope`.
6. Đọc `SearchResult`, `SearchRow`, ID, score, fragments, fields và search metadata, không ép thành entity.
7. Giới hạn kết quả, làm facets, highlights, phân trang có ý thức về độ ổn định thứ tự và thay đổi dữ liệu.
8. Giải thích consistency mặc định của Search index và sử dụng `MutationState`/`consistentWith(...)` cho read-your-own-writes khi áp dụng được.
9. Dùng Search để tìm ID, sau đó KV/Repository hydrate DTO hoặc entity khi cần, có xử lý mismatch và authorization.
10. Tạo SDK adapter đồng bộ/reactive, kiểm thử ranking, Unicode tiếng Việt, tenant isolation, lag và hiệu năng.

## 2. Khi nào dùng FTS thay vì KV hoặc SQL++?

Một hệ thống bán hàng có collection `shop.catalog.products`, mỗi document:

~~~json
{
  "tenantId": "tenant-01",
  "type": "product",
  "name": "Cà phê rang mộc Đà Lạt",
  "description": "Hạt Arabica rang vừa, hương trái cây nhẹ",
  "category": "COFFEE",
  "active": true,
  "priceCents": 145000,
  "createdAt": "2026-11-20T08:15:00.000Z"
}
~~~

Document key có thể là `product::sku-1001`. Sản phẩm yêu cầu:

- Người dùng nhập `"cà phê rang"` và thấy kết quả phù hợp, kể cả khi từ xuất hiện trong `name` hoặc `description`.
- Xếp kết quả theo **relevance score**, có thể ưu tiên tên hơn mô tả.
- Hiển thị đoạn văn bản được match.
- Lọc theo tenant, trạng thái active và category; trả facets theo category.
- Chỉ trả tối đa một số hits, có trang tiếp hoặc load more.

So sánh ba đường truy cập:

| Đường | Truy vấn điển hình | Mạnh ở điểm nào | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| **KV** | `collection.get("product::sku-1001")` | Đọc document khi biết key; CAS/TTL/expiry | Không tìm full-text theo nhiều key bất kỳ |
| **SQL++ với GSI** | `SELECT ... WHERE category = ... ORDER BY price` | Predicate có cấu trúc, join, aggregate, paging | Không mặc định có analyzers, ranking, highlight như Search |
| **Search Service/FTS** | `SearchQuery.match("cà phê").field("name")` | Token matching, scoring, facets, highlighting | Search index là dữ liệu suy diễn, có lag và mapping riêng |

FTS **không thay thế toàn bộ SQL++**. Nếu bài toán là “tìm đúng ID”, KV thường đơn giản hơn. Nếu là “đếm chính xác số đơn PAID” hoặc join nghiệp vụ, SQL++/aggregation thường phù hợp hơn. Nếu là văn bản tự nhiên/ranking, Search là ứng viên cần đánh giá.

## 3. Sơ đồ luồng dữ liệu

~~~text
                           Couchbase Data Service
                             Bucket shop
                             Scope catalog
                             Collection products
                                    |
                          document mutation stream
                                    |
                                    v
                           Couchbase Search Service
                         Search index: products-text
                         token / inverted index / metadata
                                    ^
                                    | search request
Application service ── SDK Search API ───> SearchResult
                                    |
                             hits: ID + score
                                    |
                  optional hydrate via KV / Repository
                                    |
                          ProductSearchResponse
~~~

Các ý quan trọng:

1. Document nguồn vẫn tồn tại trong **collection Couchbase**.
2. Search index phải được **tạo và cấu hình**; SDK query không tự tạo index.
3. Search Service lấy dữ liệu nguồn để xây index theo cấu hình mapping/analyzer.
4. Index có thể **chưa bắt kịp** mutation mới.
5. Search hit thường chứa ID, score, optional stored fields/highlight và metadata; không nhất thiết chứa toàn bộ document body.
6. Nếu cần body cập nhật hơn, có thể đọc KV theo ID sau search, nhưng phải xử lý document đã bị xóa/sửa giữa hai bước.
7. Search Service và GSI Index Service là **hai đường chỉ mục khác nhau**, với khả năng tối ưu và consistency khác nhau.

## 4. Full-Text Search không phải phép `LIKE` có từ khóa

Ví dụ SQL++:

~~~sql
SELECT META(p).id AS id,
       p.name,
       p.description
FROM `shop`.`catalog`.`products` AS p
WHERE p.tenantId = $tenantId
  AND LOWER(p.name) LIKE "%ca phe%"
LIMIT 20;
~~~

Câu này phụ thuộc so khớp chuỗi, Unicode, chuẩn hóa và kế hoạch/index SQL++. Nó không tự tạo một relevance score như FTS, cũng không tự cung cấp stemming, tokenization, phrase matching hay highlight.

Một Search query có thể được viết:

~~~java
SearchQuery.match("cà phê")
        .field("name");
~~~

Nhưng kết quả thực tế phụ thuộc **analyzer của field `name`**. Nếu analyzer không xử lý tiếng Việt, dấu, dấu cách, chữ hoa/thường như yêu cầu, người dùng nhập `"ca phe"` chưa chắc match `"cà phê"`. Full-text là **mô hình phân tích ngôn ngữ và chỉ mục**, không phải “LIKE nhưng nhanh hơn”.

## 5. Chuẩn bị Search Service và index

Trước khi gọi SDK, môi trường cần:

1. Couchbase deployment có **Search Service** theo topology và quyền truy cập phù hợp.
2. Bucket `shop`, scope `catalog`, collection `products` đã tồn tại.
3. Dữ liệu mẫu và field schema thống nhất.
4. Search index được tạo ở **bucket/cluster level** hoặc **scope level**, tùy phiên bản và yêu cầu.
5. Type mapping/collection mapping có chọn đúng `catalog.products`.
6. Field mapping/analyzer phù hợp các truy vấn.
7. Trạng thái index hoạt động, đã xử lý dữ liệu đủ để test.
8. User/role có quyền thực thi tìm kiếm trên index/keyspace dự kiến.

Trong Couchbase Web Console, có thể vào phần Search, tạo Search index, đặt tên, chọn bucket hoặc scope và cấu hình mapping. Để quản lý production, nên đưa **định nghĩa index vào quy trình triển khai/version control** bằng công cụ vận hành phù hợp thay vì sửa UI ngẫu hứng.

### Vì sao chỉ tạo index có tên là chưa đủ?

Một index đặt tên `products-text` nhưng không chọn đúng collection hoặc field mapping có thể:

- Không chứa document cần tìm.
- Index toàn bộ bucket ngoài dự kiến.
- Chứa cả dữ liệu loại document khác.
- Không lưu field để trả trong `SearchRow.fieldsAs(...)`.
- Không có doc values cần cho facets/sort.
- Dùng analyzer sai khiến query match thất thường.

Một Search query chạy thành công nhưng trả 0 hits không tự chứng minh sản phẩm không tồn tại.

## 6. Global Search index và scoped Search index

Couchbase hỗ trợ **scoped Search index** từ **Server 7.6** bên cạnh global index truyền thống.

| Kiểu index | Phạm vi danh tính | API truy vấn điển hình |
| --- | --- | --- |
| Global Search index | Index ở mức bucket/cluster với tên index toàn cục theo cách quản lý tương ứng | `cluster.searchQuery(indexName, query)` hoặc `cluster.search(indexName, request)` |
| Scoped Search index | Index thuộc một scope | `scope.searchQuery(indexName, query)` hoặc `scope.search(indexName, request)` |

Ví dụ với scoped index trong `shop.catalog`:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Scope;
import com.couchbase.client.java.search.SearchRequest;
import com.couchbase.client.java.search.SearchResult;
import com.couchbase.client.java.search.SearchQuery;

Scope scope = cluster.bucket("shop").scope("catalog");

SearchResult result = scope.search(
        "products-text",
        SearchRequest.create(SearchQuery.match("cà phê")
                .field("name")));
~~~

**Cần đối chiếu phiên bản:** `SearchRequest` và `search(...)` thuộc API Search mới hơn, được thiết kế cả cho truy vấn vector/hybrid; `searchQuery(...)` vẫn là đường truy vấn văn bản truyền thống. Chữ ký và khả năng scoped index phụ thuộc SDK/Server. Không dùng `Cluster.searchQuery(...)` cho một index scoped rồi mặc định nó tự tìm thấy index đó.

### Đừng nhầm scope của index với collection được index

Một scoped index thuộc `shop.catalog` có thể có mapping cho một hoặc nhiều collections trong phạm vi hỗ trợ. Việc index “ở catalog” **không đồng nghĩa** mọi collection đều được index và mọi field đều có thể search.

Địa chỉ của keyspace và phạm vi của Search index là hai thông tin phải được cấu hình và kiểm thử độc lập.

## 7. Mapping nên bắt đầu từ nhu cầu tìm kiếm

Ví dụ đề xuất cho `products`:

| Trường JSON | Kiểu trong Search index | Tác dụng |
| --- | --- | --- |
| `name` | text, analyzer chọn theo dữ liệu | Match/search, score, highlight |
| `description` | text | Full-text bổ sung |
| `category` | keyword/text không phân tách phù hợp | Lọc category và term facet |
| `tenantId` | keyword/exact-match phù hợp | Lọc tenant bắt buộc |
| `active` | boolean | Chỉ hiện sản phẩm active |
| `priceCents` | number | Numeric range, facet/sort khi có doc values |
| `createdAt` | datetime theo format chuẩn | Date range, sort |

Đây là **đặc tả mapping mục tiêu**, không phải payload JSON cấu hình Search index đầy đủ. Trong index thực, việc thiết lập `type`, analyzer, `index`, `store`, `docvalues` và source type mapping cần được tạo theo schema Couchbase của phiên bản Server.

### Static hay dynamic mappings?

**Dynamic mapping** giúp index nhanh nhiều field nhưng dễ phình kích thước và vô tình index thông tin không cần tìm kiếm. **Static mapping** yêu cầu khai báo field, ít bất ngờ hơn và giúp kiểm soát chi phí/bảo mật.

Với sản phẩm có field nhạy cảm như `internalNotes`, `costPrice` hoặc thông tin định danh cá nhân, nên **chỉ index những trường cần tìm** và hạn chế stored fields. Phân quyền ứng dụng vẫn bắt buộc; “không store” không tự biến index thành cơ chế authorization.

## 8. Analyzer và dữ liệu tiếng Việt

Search Service sử dụng analyzer để biến chuỗi thành **tokens**. Một analyzer có thể bao gồm tokenizer, lowercase, char filters và token filters.

Ví dụ text:

~~~text
Cà phê rang mộc Đà Lạt
~~~

Người dùng có thể gõ:

~~~text
cà phê
ca phe
cafe
rang moc
Đà Lạt
da lat
~~~

**Không suy ra** các chuỗi trên tự tương đương. Khi thiết kế phải kiểm tra:

- Unicode normalization và cách lưu UTF-8.
- Chữ hoa/thường.
- Dấu tiếng Việt và yêu cầu tìm có/không dấu.
- Phân tách từ tiếng Việt nhiều âm tiết.
- Tokenization trên ký tự đặc biệt, dấu gạch ngang, SKU.
- Stop words, stemming hoặc custom analyzer khi thật sự phù hợp.
- Query-time analysis có nhất quán với index-time analysis không?
- Có cần một **field chuẩn hóa phục vụ search** riêng, ví dụ `nameSearch`, được tạo bởi pipeline dữ liệu đáng tin cậy không?

### Bài test analyzer tối thiểu

| Document name | Query | Kỳ vọng nghiệp vụ cần xác nhận |
| --- | --- | --- |
| Cà phê rang mộc | cà phê | Match |
| Cà phê rang mộc | ca phe | Match nếu hỗ trợ bỏ dấu |
| Điện thoại thông minh | điện thoại | Match |
| Áo sơ mi nam | áo sơ mi | Match theo cụm |
| SKU-AB-123 | AB-123 | Match chính xác SKU nếu thiết kế field tương ứng |

Test phải chạy trên Search index thật, không chỉ unit-test Java query builder. Một analyzer tiếng Anh không phải lựa chọn mặc định đúng cho mọi tiếng Việt.

## 9. `index`, `store` và `docvalues` không đồng nghĩa

Trong field mapping:

- **`index`**: cho phép field tham gia tìm kiếm theo kiểu được cấu hình.
- **`store`**: cho phép Search Service trả giá trị field trực tiếp trong hit khi request.
- **`docvalues`**: cấu trúc hỗ trợ một số thao tác như facets và sorting.
- **`analyzer`**: kiểm soát text được token hóa/chuẩn hóa như thế nào.
- **`type`**: text, number, datetime, boolean, geopoint... tùy khả năng.

Ví dụ `SearchOptions.fields("name")` **không tạo ra giá trị name** nếu field không được store trong Search index. Nếu không muốn lưu nhiều dữ liệu trong index, có thể chỉ lấy ID rồi hydrate bằng KV.

Các lựa chọn index/store/docvalues ảnh hưởng dung lượng, chi phí index, độ trễ và privacy. Không bật mọi option trên mọi field nếu workload không cần.

## 10. Tạo truy vấn text đơn giản với SDK

Ví dụ global index tên `idx-products-text`:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.search.SearchQuery;
import com.couchbase.client.java.search.SearchResult;
import com.couchbase.client.java.search.SearchRow;

SearchResult result = cluster.searchQuery(
        "idx-products-text",
        SearchQuery.match("cà phê")
                .field("name"));

for (SearchRow row : result.rows()) {
    System.out.println("Document ID: " + row.id());
    System.out.println("Score: " + row.score());
}
~~~

API `Cluster.searchQuery` nhận tên **global Search index** và một `SearchQuery`. Nếu index được tạo scoped, chuyển sang `Scope` tương ứng.

Không lẫn với SQL++:

~~~java
// SQL++ chạy Query Service:
cluster.query("SELECT ...");

// Search Service:
cluster.searchQuery("idx-products-text",
        SearchQuery.match("cà phê"));
~~~

Hai đường có ngôn ngữ truy vấn, index, result shape và consistency khác nhau.

## 11. Các loại `SearchQuery` thường gặp

| Query builder | Ý nghĩa | Ví dụ nhu cầu |
| --- | --- | --- |
| `SearchQuery.match(text)` | Phân tích input, tìm token phù hợp | Tên/mô tả |
| `SearchQuery.matchPhrase(text)` | Tìm cụm từ theo kết quả phân tích | Tên sản phẩm theo cụm |
| `SearchQuery.term(term)` | Term-level match theo cách field được index | Mã/nhãn/tenant theo exact policy |
| `SearchQuery.prefix(prefix)` | Tìm term có tiền tố | Gợi ý prefix trên field phù hợp |
| `SearchQuery.wildcard(pattern)` | Pattern trên terms | Tìm theo mẫu có kiểm soát |
| `SearchQuery.regexp(regex)` | Regular expression trên term index | Nhu cầu đặc biệt, giới hạn chi phí |
| `SearchQuery.numericRange()` | Khoảng số | Giá, rating |
| `SearchQuery.dateRange()` | Khoảng ngày | Sản phẩm mới |
| `SearchQuery.conjuncts(...)` | AND nhiều truy vấn con | Text + tenant + active |
| `SearchQuery.disjuncts(...)` | OR nhiều truy vấn con | Match name hoặc description |
| `SearchQuery.queryString(text)` | Cú pháp query-string riêng | Chỉ dùng khi thực sự cần parser này |

Ví dụ tìm phrase:

~~~java
SearchQuery query = SearchQuery
        .matchPhrase("cà phê rang")
        .field("name");
~~~

Ví dụ prefix trên text field:

~~~java
SearchQuery query = SearchQuery
        .prefix("ara")
        .field("name");
~~~

**Cảnh báo:** prefix/wildcard/regexp làm việc trên **terms đã được index**, không mặc nhiên trên toàn chuỗi nguyên bản. Match theo SKU, barcode hoặc mã cố định thường cần mapping kiểu keyword/chính sách exact match riêng.

Không cho client nhập regex hoặc wildcard quá rộng không giới hạn; chúng có thể làm query đắt hoặc tạo mức tải khó kiểm soát.

## 12. Kết hợp text, tenant và trạng thái trong cùng Search query

Ví dụ business rule: chỉ tìm sản phẩm của `tenant-01` đang active, có từ khóa trong tên.

~~~java
SearchQuery query = SearchQuery.conjuncts(
        SearchQuery.match("cà phê").field("name"),
        SearchQuery.term("tenant-01").field("tenantId"),
        SearchQuery.booleanField(true).field("active")
);
~~~

Cấu hình index phải bảo đảm:

- `tenantId` được index theo ngữ nghĩa **exact match**, tránh analyzer làm vỡ tenant token.
- `active` có boolean field mapping phù hợp.
- `name` dùng text analyzer đúng yêu cầu.
- Không vô tình index toàn bộ tenant data với default mapping mà thiếu điều kiện quyền.
- Mọi nhánh `OR` về text vẫn nằm **bên trong** điều kiện `AND tenant/active`.

Có thể diễn giải điều kiện:

~~~text
tenantId = authenticatedTenant
AND active = true
AND (
    name matches text
    OR description matches text
)
~~~

Khi muốn OR hai field, tạo `SearchQuery.disjuncts(...)` ở **bên trong** `SearchQuery.conjuncts(...)`; đừng đặt tenant filter thành một nhánh OR ngoài cùng.

**Quy tắc bảo mật:** tenant lấy từ authentication/authorization context, không tin một parameter tự chọn của client. Nếu index bao gồm nhiều collection hoặc document types, cần filter phạm vi phù hợp và kiểm chứng toàn bộ hit ID trước khi hydrate/trả nội dung.

## 13. `queryString(...)` có cú pháp riêng và rủi ro input

~~~java
SearchQuery query = SearchQuery.queryString(
        "name:cafe AND category:COFFEE");
~~~

`queryString(...)` có thể diễn giải operator, field và các cấu trúc theo parser Search, không phải chỉ một chuỗi literal cần match.

Vì vậy, với ô tìm kiếm tự do của end-user, thường nên ưu tiên:

~~~java
SearchQuery query = SearchQuery
        .match(userText)
        .field("name");
~~~

kết hợp một cây truy vấn có **field allowlist và filter do server đặt**.

Nếu product yêu cầu “advanced search syntax”, hãy giới hạn độ dài, token complexity, những field được phép, escape/validate input và quota query. Không coi `queryString` tương đương một cách bind SQL++ parameter an toàn mặc định.

## 14. Đọc `SearchResult` và `SearchRow`

Ví dụ:

~~~java
SearchResult result = cluster.searchQuery(
        "idx-products-text",
        SearchQuery.match("cà phê"),
        searchOptions().limit(10));

for (SearchRow hit : result.rows()) {
    String id = hit.id();
    double score = hit.score();
    String index = hit.index();

    System.out.printf(
            "id=%s score=%f index=%s%n",
            id, score, index);
}

long reportedTotal = result.metaData()
        .metrics()
        .totalRows();
~~~

Với `SearchRow`, những thông tin đáng biết:

- `id()`: document ID của hit.
- `index()`: Search index gắn với hit.
- `score()`: điểm liên quan do Search Service tính.
- `fieldsAs(...)`: giải mã các stored fields được yêu cầu.
- `fragments()`: đoạn highlight nếu có.
- `locations()`: vị trí các match theo cách Search Service cung cấp.
- `explanation()`: thông tin giải thích score khi bật explain.

`SearchResult.metaData()` có metrics và **có thể chứa errors/partial failures** dù query đã trả một số hits. Nếu API cần kết quả **đầy đủ** thay vì best-effort, phải kiểm tra metadata errors theo SDK contract, không chỉ bắt exception.

**Reported total** là thống kê Search tại thời điểm query/index state, không phải chứng cứ tất cả source documents đã được index hoặc một count bất biến xuyên request.

## 15. Search hit không phải entity Spring Data Couchbase

Một hit minh họa:

~~~json
{
  "id": "product::sku-1001",
  "score": 2.87,
  "fields": {
    "name": "Cà phê rang mộc Đà Lạt"
  }
}
~~~

Đây là mô tả ý tưởng, **không phải JSON response chuẩn đầy đủ** của mọi phiên bản SDK. Những field được trả phụ thuộc `store` và `SearchOptions.fields(...)`.

Một Spring Data entity có thể là:

~~~java
@Document
@Scope("catalog")
@Collection("products")
public class Product {
    @Id
    private String id;

    @Version
    private Long version;

    private String name;
    private String description;
    private String tenantId;
    private boolean active;
    private long priceCents;
}
~~~

Hit `id+score` không có đầy đủ body, metadata `@Version` hoặc CAS của document nguồn. Không tạo một partial `Product` từ Search hit rồi gọi `repository.save(...)`—nó có thể làm mất field hoặc ghi đè phiên bản.

Nên có read model:

~~~java
public record ProductHit(
        String documentId,
        double score,
        String displayName) {}
~~~

Nếu cần entity/current value, **hydrate** bằng KV hoặc Repository theo ID và xử lý sai lệch giữa index và source.

## 16. Ví dụ SDK adapter tìm kiếm theo tên

Dưới đây là custom read adapter cho **global Search index** đã cấu hình field `name` là searchable và stored:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.search.SearchQuery;
import com.couchbase.client.java.search.SearchResult;
import com.couchbase.client.java.search.SearchRow;
import com.couchbase.client.java.search.SearchOptions;
import com.couchbase.client.java.json.JsonObject;

import java.util.List;

import static com.couchbase.client.java.search.SearchOptions.searchOptions;

public record ProductHit(
        String documentId,
        double score,
        String displayName) {}

public List<ProductHit> searchByName(
        Cluster cluster,
        String input,
        int limit) {

    if (input == null || input.isBlank()
            || input.length() > 120) {
        throw new IllegalArgumentException("Invalid search text");
    }
    if (limit < 1 || limit > 50) {
        throw new IllegalArgumentException("Invalid limit");
    }

    SearchQuery query = SearchQuery
            .match(input.trim())
            .field("name");

    SearchResult result = cluster.searchQuery(
            "idx-products-text",
            query,
            searchOptions()
                    .limit(limit)
                    .fields("name"));

    return result.rows().stream()
            .map(hit -> {
                JsonObject fields = hit.fieldsAs(JsonObject.class);
                return new ProductHit(
                        hit.id(),
                        hit.score(),
                        fields.getString("name"));
            })
            .toList();
}
~~~

Trong thực tế, adapter cần thêm tenant/authorization filter, observability, timeout và error mapping. Ví dụ này **cố ý chỉ tập trung shape** và giả định `name` đã được store trong Search index. Nếu không stored, `fieldsAs(...)` có thể thiếu tên, phải có chính sách fallback/hydration thay vì tự tin gán null là tên sản phẩm.

Một adapter an toàn cho multi-tenant **không dùng** ví dụ unfiltered này nguyên trạng; áp dụng predicate tenant/active và kiểm tra quyền trước khi trả nội dung.

### Vì sao giữ adapter thay vì SDK ở controller?

- Controller không cần biết tên Search index hoặc API thấp tầng.
- Có thể đổi index alias/tên index mà không thay domain API.
- Một nơi quản lý normalization, tenant filter và error policy.
- Unit test mock port; integration test kiểm tra Search thực.
- Dễ chuyển một phần sang SQL++ khi điều kiện nghiệp vụ thay đổi.

## 17. Highlights và cách hiển thị an toàn

Search Service có thể trả **highlight fragments** cho field được yêu cầu:

~~~java
import com.couchbase.client.java.search.HighlightStyle;

SearchResult result = cluster.searchQuery(
        "idx-products-text",
        SearchQuery.match("cà phê").field("description"),
        searchOptions()
                .limit(10)
                .highlight(HighlightStyle.HTML, "description"));

for (SearchRow row : result.rows()) {
    System.out.println(row.fragments());
}
~~~

**Cần tách rõ:**

1. Highlight fragments là dữ liệu phục vụ trình bày **match**, không phải body đầy đủ.
2. Không suy ra chúng luôn có nếu field/mapping/query không phù hợp.
3. Nếu trả HTML fragments cho UI, cần kiểm soát encoding/sanitization và cơ chế render an toàn. Nội dung được index có thể chứa chuỗi do người dùng nhập.
4. Không đưa HTML highlight vào `innerHTML` không kiểm soát vì nguy cơ XSS. Có thể dùng style/format phù hợp và escape text.
5. Highlighting không làm dữ liệu mới hơn; fragment vẫn phụ thuộc phiên bản index.
6. Không lưu lại highlight như document nguồn hay dùng làm cơ sở sửa entity.

## 18. Facets: không phải SQL++ `GROUP BY` và không miễn phí

Một cửa hàng có giao diện lọc kết quả theo `category`. Search Service hỗ trợ term facets:

~~~java
import com.couchbase.client.java.search.SearchFacet;
import java.util.Map;

Map<String, SearchFacet> facets = Map.of(
        "categories", SearchFacet.term("category", 10));

SearchResult result = cluster.searchQuery(
        "idx-products-text",
        SearchQuery.match("cà phê"),
        searchOptions()
                .limit(20)
                .facets(facets));
~~~

Facet cho phép UI hiển thị các nhóm/đếm được tính trong **ngữ cảnh Search query**, không phải một SQL++ query đếm toàn bộ collection theo arbitrary predicate.

Điều kiện:

- `category` phải được index với mapping phù hợp facet.
- Có thể cần `docvalues` theo cấu hình Search index.
- Số bucket facet, kết quả và độ chính xác chịu chi phối query/index state và tính năng Server.
- Nếu Search có partial errors hoặc index lag, facet count cũng có thể chưa phản ánh mọi document nguồn.
- Không coi facet count là số liệu giao dịch/kế toán cần snapshot.

Nếu UI cần thống kê định kỳ chính xác theo trạng thái nguồn, dùng SQL++ `GROUP BY` hoặc pipeline tổng hợp có consistency riêng.

## 19. Ranking, score và thứ tự

Theo mặc định, Search thường xếp hits theo **điểm liên quan giảm dần**. `row.score()` là score dùng cho ranking, không phải giá, ngày tạo, CAS hoặc một số thứ tự toàn cục.

Có thể tùy chỉnh sort:

~~~java
import com.couchbase.client.java.search.SearchSort;

SearchResult result = cluster.searchQuery(
        "idx-products-text",
        SearchQuery.match("cà phê"),
        searchOptions().sort(
                SearchSort.byScore(),
                SearchSort.byField("name")));
~~~

Ý nghĩa sort phải kiểm tra theo API/mapping: trường dùng sort cần có cấu trúc index/docvalues phù hợp; quy tắc ASC/DESC cần cấu hình đúng. Không suy ra `byField("name")` sẽ hoạt động với mọi analyzed text field mà không cần mapping riêng.

### Score không phải khóa phân trang bất biến

Nếu document mới được index, analyzer/index thay đổi hoặc từ khóa khác, score có thể đổi. Hai hits cùng score có thể đổi vị trí nếu thiếu tie-breaker ổn định.

Do đó:

- Mặc định sort by relevance phù hợp tìm kiếm tương tác, nhưng có thể **lặp/bỏ sót** giữa nhiều trang trên dataset đang biến động.
- Nếu cần sort theo field, cấu hình field có thứ tự rõ và một khóa phân xử duy nhất ở mức hit.
- Không dùng CAS làm khóa phụ thời gian.
- Nếu sản phẩm đòi snapshot export, phải thiết kế snapshot/result materialization riêng.

## 20. Limit, skip và chi phí trang sâu

Trong Java SDK:

~~~java
SearchResult page = cluster.searchQuery(
        "idx-products-text",
        SearchQuery.match("cà phê"),
        searchOptions()
                .skip(20)
                .limit(10));
~~~

- `limit(10)` giới hạn tối đa 10 hits của response.
- `skip(20)` bỏ 20 hits đầu theo thứ tự Search.
- Mặc định Search Service chỉ trả một số hits đầu (theo tài liệu SDK thường là **10**, từ offset 0).
- `skip` sâu có thể làm server phải xử lý nhiều hits trước khi bỏ qua; không mặc định là O(1).
- Search ranking và index có thể đổi giữa hai request, nên chuyển trang không tạo snapshot.

### Có nên hiển thị `totalPages`?

Search metadata có total hits được báo cáo, nhưng:

- Total thuộc trạng thái index/query, không nhất thiết cập nhật tức thời với source.
- Search query có thể có errors/partial results.
- Total/score có thể đổi ngay khi người dùng chuyển trang.
- Không suy ra “trang 4 luôn có đúng 10 kết quả” từ một total cũ.

Với sản phẩm chỉ cần “Xem thêm”, có thể lấy `pageSize+1` hits để xác định `hasNext` theo lần query hiện tại, nhưng vẫn không tạo snapshot hay tự sửa độ không ổn định của relevance order.

### Deep pagination

Khi số hits lớn, nên áp giới hạn skip/page tối đa, khuyến khích người dùng lọc cụ thể hơn và xem khả năng **search-after** hoặc phương án phân trang được Server/SDK phiên bản của dự án hỗ trợ. Không tự xây keyset trên `score` như thể nó bất biến.

## 21. Search consistency: mặc định nhìn trạng thái index

Một document mới có thể được KV `collection.upsert(...)` xác nhận, nhưng Search index chưa kịp nhận mutation.

~~~text
T0   Product chưa tồn tại
T1   KV upsert(Product) thành công
T2   Search query ngay lập tức
T3   Search index chưa bắt kịp -> chưa có hit
T4   Index bắt kịp -> hit xuất hiện
~~~

Đây là **indexing lag** có thể quan sát, không mặc nhiên là lỗi SDK hay Repository.

Theo tài liệu Search Java SDK:

- Mặc định Search có ngữ nghĩa gần `NOT_BOUNDED`, dùng trạng thái index hiện có.
- `SearchScanConsistency.NOT_BOUNDED` không bắt index chờ tất cả mutation.
- Để phục vụ **read-your-own-writes (RYOW)**, có thể cung cấp `MutationState` từ token của các mutation đã biết và gọi `SearchOptions.consistentWith(...)`.
- Chờ consistency có thể tăng latency và timeout under load.
- Không dùng `QueryScanConsistency.REQUEST_PLUS` của **SQL++** rồi cho rằng Search query đã được cấu hình giống vậy.

## 22. Ví dụ `consistentWith(MutationState)`

SDK KV write trả `MutationResult` và có thể có mutation token:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.MutationResult;
import com.couchbase.client.java.kv.MutationState;
import com.couchbase.client.java.search.SearchQuery;
import com.couchbase.client.java.search.SearchResult;

import static com.couchbase.client.java.search.SearchOptions.searchOptions;

MutationResult mutation = products.upsert(
        "product::sku-1001",
        JsonObject.create()
                .put("name", "Cà phê rang mộc Đà Lạt")
                .put("tenantId", "tenant-01")
                .put("active", true));

MutationState state = MutationState.from(
        mutation.mutationToken()
                .orElseThrow(() -> new IllegalStateException(
                        "Mutation token unavailable")));

SearchResult result = cluster.searchQuery(
        "idx-products-text",
        SearchQuery.match("cà phê").field("name"),
        searchOptions().consistentWith(state));
~~~

Điểm phải hiểu:

1. `MutationState` được xây từ token của **mutation thực sự đã thực hiện**.
2. `consistentWith(state)` yêu cầu Search query đáp ứng consistency tương ứng trước khi trả kết quả, trong phạm vi khả năng Server/SDK.
3. Nếu token không có sẵn, **không** tự tạo một token tưởng tượng; chọn chính sách khác.
4. Request có thể chờ lâu hơn hoặc timeout nếu Search Service chậm.
5. Điều này **không** đảm bảo các request sau nhìn cùng một snapshot, cũng không khóa document khỏi bị sửa/xóa sau đó.
6. Với một UI vừa tạo sản phẩm và muốn tìm lại, đây là lựa chọn có cơ sở hơn `Thread.sleep(...)` cố định.

**Không nên áp dụng RYOW một cách không chọn lọc cho mọi Search request**: người dùng tìm kiếm chung thường chấp nhận index lag nhỏ, trong khi màn hình “vừa tạo xong” có thể cần hợp đồng mạnh hơn.

## 23. SQL++ scan consistency khác Search consistency

Ví dụ SQL++:

~~~java
cluster.query(
        "SELECT ... FROM `shop`.`catalog`.`products`",
        queryOptions().scanConsistency(
                QueryScanConsistency.REQUEST_PLUS));
~~~

Còn Search:

~~~java
cluster.searchQuery(
        "idx-products-text",
        SearchQuery.match("cà phê"),
        searchOptions().consistentWith(mutationState));
~~~

Chúng tương tác với **dịch vụ và index khác nhau**.

| Vấn đề | SQL++ | Search |
| --- | --- | --- |
| Index thường dùng | GSI/Index Service | Search index/Search Service |
| Query builder | SQL++ text + QueryOptions | SearchQuery/SearchRequest + SearchOptions |
| Consistency phổ biến | `NOT_BOUNDED`, `REQUEST_PLUS` và mutation-state option theo SDK | Search `NOT_BOUNDED` và `consistentWith(MutationState)` |
| Sort | `ORDER BY` theo giá trị | Score/relevance hoặc SearchSort |
| Kết quả | SQL++ JSON rows | Search hits + score/metadata |
| Index lag | Có thể xuất hiện | Có thể xuất hiện, cơ chế riêng |
| Snapshot nhiều request | Không tự có | Không tự có |

Một Search hit không phản ánh mutation mới nhất có thể đến từ **Search indexing lag**; tăng SQL++ scan consistency **không sửa** Search index lag.

## 24. Hydration: Search tìm ID, KV đọc body hiện hành

Search hit chủ yếu cung cấp document ID và metadata. Khi endpoint cần `priceCents` mới nhất hoặc field không store trong Search index, có thể:

1. Search để có một danh sách IDs có score.
2. Dùng KV `get(id)` hoặc Repository `findById(...)` theo đúng collection.
3. Ánh xạ entity/read model và bảo toàn thứ tự Search hit nếu UI xếp theo score.
4. Re-check authorization, `active` và các điều kiện không được phép stale.
5. Xử lý document không tồn tại, TTL hết hạn hoặc bị xóa giữa hai bước.

~~~text
Search index:
  [product::1001(score=3.2), product::1010(score=2.8)]
                  |
                  +-- KV get("product::1001") -> body mới
                  +-- KV get("product::1010") -> NotFound
                  |
                  v
API response: một hit hiển thị, không giả vờ có đủ 2
~~~

### Tại sao hydrate xong vẫn cần kiểm tra?

Một kết quả Search khớp `active=true` tại T0, nhưng sản phẩm có thể chuyển `active=false` ở T1 trước khi KV get. Nếu dữ liệu cần được ẩn khỏi UI, bước hydrate nên kiểm tra **trạng thái hiện tại** theo hợp đồng ứng dụng.

Đặc biệt trong multi-tenant:

- Search query phải có tenant filter đúng.
- KV get theo ID cũng phải được **authorize**, không chỉ tin ID do Search index trả về.
- Không dùng raw stored fields của Search như nguồn quyết định quyền.
- Khi Search index bao gồm nhiều collections, cần biết đúng collection của từng hit để hydrate; **document ID một mình không phân biệt keyspace**.
- Nên dùng index chỉ chứa một collection cho ví dụ đơn giản, hoặc thiết kế hit metadata/routing rõ.

### N+1 reads và hiệu năng

Hydrate 20 hits có thể tạo tới 20 KV gets. Có thể dùng SDK async/reactive, giới hạn concurrency và bảo toàn thứ tự hiển thị; tránh gửi hàng nghìn concurrent gets không giới hạn.

Nếu đa số UI chỉ cần tên và preview, cấu hình stored fields nhỏ đúng mục đích có thể giảm số KV reads—nhưng cần cân nhắc privacy, freshness và dung lượng index.

## 25. Reactive Search không đồng nghĩa kết quả ít tốn hơn

Java SDK có reactive Search API:

~~~java
import com.couchbase.client.java.ReactiveCluster;
import com.couchbase.client.java.search.SearchQuery;
import com.couchbase.client.java.search.ReactiveSearchResult;
import com.couchbase.client.java.search.SearchRow;
import reactor.core.publisher.Flux;

public Flux<ProductHit> searchReactive(
        ReactiveCluster cluster,
        String text) {

    return cluster.searchQuery(
            "idx-products-text",
            SearchQuery.match(text).field("name"),
            searchOptions().limit(20))
        .flatMapMany(ReactiveSearchResult::rows)
        .map(row -> new ProductHit(
                row.id(),
                row.score(),
                row.fieldsAs(JsonObject.class).getString("name")));
}
~~~

Ở đây class `ReactiveCluster` được lấy từ `cluster.reactive()` của **Spring-managed Cluster**, không tạo kết nối mới cho từng request.

Reactive cho khả năng kết hợp publisher, hủy subscription và quản lý backpressure. Nhưng:

- Không biến query Search thành KV get.
- Không tự hạn chế server chỉ xử lý 20 hits nếu thiếu `SearchOptions.limit(...)`.
- `Flux.take(20)` ở downstream không tương đương một kế hoạch Search tối ưu.
- Không thêm snapshot hoặc RYOW nếu chưa chọn consistency.
- Không dùng `block()` trên event loop WebFlux.
- Không gọi `subscribe()` trong service rồi trả một publisher khác nếu không chủ đích quản lý lifecycle riêng.

### Có cần `collectList()`?

Nếu API trả một response gồm `items` và `hasNext`, có thể thu tối đa `pageSize+1` hits vào `Mono<SearchWindow>`. Nhưng phải đặt **limit ở Search Service** trước, không collect một luồng không giới hạn rồi cắt ở Java.

## 26. Sự khác nhau giữa score ordering và async hydration

Nếu Search Service trả:

~~~text
1. product::A, score 4.0
2. product::B, score 3.0
3. product::C, score 2.0
~~~

và bạn dùng:

~~~java
hits.flatMap(hit -> loadProductById(hit.id()))
~~~

thì kết quả hydrate có thể hoàn thành theo thứ tự khác:

~~~text
B -> C -> A
~~~

Lúc đó UI vô tình **mất thứ tự relevance**.

Nếu cần giữ order, dùng `concatMap(...)` hoặc `flatMapSequential(...)` với concurrency/buffering có kiểm soát:

~~~java
Flux<ProductCard> cards = hits.concatMap(hit ->
        loadProductCardReactive(hit.id())
                .map(card -> card.withScore(hit.score())));
~~~

`loadProductCardReactive(...)` và `withScore(...)` là **hàm ứng dụng minh họa**, không phải API tự có của Spring Data/Couchbase SDK.

Khi một ID không còn tồn tại, phải quyết định có bỏ qua, ghi nhận warning hay trả lỗi. Đừng biến lỗi quyền thành “skip item” để giấu dữ liệu không được phép nếu hợp đồng bảo mật cần chặn cả request.

## 27. Search index không tự thực thi authorization

Giả sử Search index chứa nhiều tenant. Nếu truy vấn:

~~~java
SearchQuery.match("cà phê").field("name");
~~~

mà không có tenant filter, Search có thể trả IDs thuộc nhiều tenant mà SDK credentials của service được phép đọc.

Hệ thống cần:

1. Lấy tenant từ token/principal đã xác thực, không tin query param tự nhận.
2. Đặt **tenant filter** ở Search query và xác nhận mapping exact-match của field tenant.
3. Lọc theo type discriminator/collection/active khi hợp đồng yêu cầu.
4. Kiểm tra lại tenant/quyền khi hydrate bằng KV.
5. Không cho client chọn Search index hoặc `SearchQuery.queryString` tùy ý nếu không có allowlist.
6. Không trả stored fields, highlight, facets hoặc total counts của tenant khác.
7. Hạn chế quyền Search Service và Data Service qua RBAC theo principle of least privilege.
8. Tránh log query thô chứa PII, thông tin nhạy cảm hoặc từ khóa riêng tư.

**Search hit và facet count có thể làm lộ thông tin dù không trả document body.** Vì vậy security phải được áp dụng trước khi đọc metadata, không chỉ trước khi KV get.

## 28. TTL, CAS và transaction trong Search flow

Một document có TTL có thể hết hạn rồi biến mất khỏi Search index. Tùy lag, trong một cửa sổ ngắn query có thể còn thấy hit trong khi KV get không tìm thấy document.

CAS:

- `SearchRow` không phải một entity chứa CAS sẵn cho mutation.
- Khi cần sửa Product, đọc body/current CAS từ KV hoặc Repository `@Version` phù hợp.
- Không lấy `score`, `index` hay Search highlight làm CAS/version.
- Không viết lại toàn document từ stored fields của Search index.

Transaction:

- Một Search query **không biến** các hits và KV gets tiếp theo thành transaction/snapshot nhiều document.
- Dữ liệu có thể đổi giữa Search query và từng lần hydrate.
- Nếu nghiệp vụ cần báo cáo “as of T0”, thiết kế snapshot/versioned export hoặc materialized result riêng.
- Không mở một transaction kéo dài qua nhiều HTTP request phân trang Search.

## 29. Vận hành Search index: dữ liệu, replicas và chi phí

Một Search index có đời sống độc lập với GSI:

- Index mapping/analyzers cần được version hóa.
- Search nodes, partitions và index replicas là tài nguyên có chi phí.
- Stored fields/docvalues tăng kích thước index.
- Dynamic mapping có thể index dữ liệu thừa.
- Indexing lag có thể tăng khi mutation throughput cao.
- Rebalance/failover có thể ảnh hưởng query latency và availability.
- Thay analyzer/mapping có thể yêu cầu rebuild/reindex và thời gian hội tụ.
- Index alias (khi được hỗ trợ) có thể giúp quản lý phiên bản/chuyển index theo kế hoạch triển khai.
- RBAC và network access tới Search Service phải được kiểm chứng.

### Chẩn đoán 0 hits

Đặt câu hỏi theo thứ tự:

1. Index đúng tên và đúng cấp `Cluster`/`Scope` chưa?
2. Index mapping có chứa đúng `catalog.products` không?
3. Document có tồn tại trong collection không?
4. Index đã ingest document chưa?
5. Field `name` có được index đúng kiểu/analyzer không?
6. Query `match` có phân tích text như mong muốn không?
7. Tenant/active filter có loại hết hits không?
8. Có lỗi Search Service hoặc partial results trong metadata không?
9. Quyền SDK có cho phép query index không?
10. Có schema migration làm thay tên field JSON không?

Không sửa bằng cách tắt tenant filter hoặc bật dynamic mapping toàn bucket trên production.

## 30. Monitoring và benchmark

Các chỉ số nên theo dõi:

| Chỉ số | Câu hỏi |
| --- | --- |
| Search p50/p95/p99 latency | Query text, facets, highlight có nhanh không? |
| Search index lag | Sau write bao lâu hit mới được quan sát? |
| Search result total và partial errors | Kết quả có đầy đủ theo yêu cầu không? |
| Zero-hit rate | Query/mapping/analyzer có sai? |
| Search Service CPU/memory/disk | Index có quá lớn hoặc query quá đắt? |
| Indexing throughput/queue | Mutation stream có bị chậm? |
| Facet/highlight overhead | Tính năng trình bày tăng chi phí bao nhiêu? |
| Deep skip latency | Page sâu có vượt budget? |
| Hydration KV get count/latency | N+1 reads có đáng kể? |
| Tenant filter violations | Có hit metadata sai phạm vi không? |
| Unicode accent match rate | Có đạt UX tìm kiếm tiếng Việt? |

Đo trên corpus đại diện: các trường có dấu tiếng Việt, nhiều tên tương tự, tên dài, sản phẩm trùng từ khóa, và document thay đổi liên tục.

**Đừng chỉ benchmark latency**; còn phải xác nhận ranking đúng, bỏ qua field bí mật, tenant isolation và trạng thái dữ liệu sau cập nhật.

## 31. Checklist kiểm thử tích hợp

### A. Index/mapping

- [ ] Có Search Service và index đúng tên/cấp.
- [ ] Index đúng bucket/scope/collection; không vô tình chọn toàn bucket.
- [ ] `name`/`description` là text theo analyzer đã chọn.
- [ ] `tenantId` exact-match, `active` boolean và category facet đúng kiểu.
- [ ] Field yêu cầu trả bằng `fields(...)` đã được store.
- [ ] Field dùng sort/facet có doc values khi cần.
- [ ] Tài liệu index được quản lý theo môi trường và version.
- [ ] Test index sau lần sửa mapping/analyzer và reindex nếu cần.

### B. Search query

- [ ] `match`, `matchPhrase`, `prefix` có kết quả đúng theo analyzer.
- [ ] Query có `AND tenant/active` không bị nhánh `OR` bỏ qua.
- [ ] Query user input có giới hạn và field allowlist.
- [ ] `limit`/`skip` hợp lý; response không chứa quá nhiều hits.
- [ ] Score sort và tie-breaker (nếu có) đúng kỳ vọng.
- [ ] Highlight không tạo XSS khi frontend hiển thị.
- [ ] Facets phản ánh đúng query filter và không lộ tenant khác.
- [ ] Metadata errors được xử lý theo yêu cầu đầy đủ/best-effort.

### C. Độ mới và hydration

- [ ] Khi KV write vừa xong, Search có thể chưa có hit nếu không yêu cầu consistency.
- [ ] `consistentWith(MutationState)` hoạt động khi mutation token có sẵn.
- [ ] TTL/delete giữa Search và KV get được xử lý.
- [ ] Sản phẩm inactive/khác tenant không lọt qua bước hydrate.
- [ ] Partial entity từ Search không được dùng để save.
- [ ] CAS dùng cho edit lấy từ entity/KV hiện tại, không từ score.
- [ ] Async hydration bảo toàn relevance order.
- [ ] Search/SQL++ có consistency tách biệt đúng semantics.

### D. Reactive và vận hành

- [ ] WebFlux không gọi `block()` trên event-loop.
- [ ] Search có server-side `limit` trước `collectList()`.
- [ ] Query timeout/cancel/partial errors có chính sách.
- [ ] Có đo search latency, indexing lag, CPU/disk và hydrate KV overhead.
- [ ] Test multi-tenant và RBAC trên cluster thật.
- [ ] Test unicode/vietnamese accent trên corpus gần production.
- [ ] Test global vs scoped Search index với đúng SDK/Server version.

## 32. Bài tập thực hành

Xây API:

~~~http
GET /products/search?q=ca%20phe&category=COFFEE&page=0&size=20
~~~

**Phần A — Index**

1. Tạo collection `shop.catalog.products` và seed dữ liệu gồm tên sản phẩm tiếng Việt có dấu.
2. Tạo Search index scoped `products-text` trong `shop.catalog` hoặc global index theo phiên bản.
3. Chọn mapping cho `name`, `description`, `tenantId`, `active`, `category` và `priceCents`.
4. Thử analyzer mặc định, đo trường hợp `"ca phe"`/`"cà phê"`; điều chỉnh theo yêu cầu.
5. Quyết định field nào cần stored và docvalues, ghi lại tradeoff.

**Phần B — SDK Query**

1. Dùng `Scope.search(...)`/`Scope.searchQuery(...)` nếu là scoped index, `Cluster.searchQuery(...)` nếu global.
2. Kết hợp text query với tenant và active filters theo exact mapping.
3. Trả `ProductHit(id, score, displayName)`; không map trực tiếp sang entity đầy đủ.
4. Dùng `limit(size)`, `skip(page*size)` với giới hạn tối đa.
5. Thêm highlight trên `description`, render an toàn.
6. Thêm term facet theo category và kiểm tra metadata.
7. Thử keyword/regex quá dài và bảo đảm validation.

**Phần C — Consistency & Hydration**

1. Tạo Product mới bằng KV rồi search ngay; quan sát indexing lag.
2. Lấy `MutationState` từ mutation token và thử `consistentWith(...)`.
3. Đổi `active=false` sau khi hit xuất hiện; hydrate KV và kiểm tra chặn item cũ.
4. Xóa/TTL một product giữa Search và KV get; ứng dụng phải xử lý not-found.
5. Đảm bảo tenant khác không thể nhận hits, facets, highlights hoặc total.
6. Dùng KV get hiện tại để lấy CAS khi bước tiếp theo là chỉnh sửa.

**Phần D — Reactive & Performance**

1. Viết reactive Search dùng `cluster.reactive().searchQuery(...)`.
2. Giới hạn kết quả ở Search Service, không chỉ `Flux.take(20)`.
3. Nếu hydrate async nhiều ID, giữ thứ tự score.
4. Đo p95 latency với/không facets, highlights, hydration.
5. Kiểm tra Search Service resource và partial errors.
6. Viết ADR chọn Search thay vì SQL++ `LIKE` dựa trên yêu cầu ranking/analyzer và kết quả benchmark.

### Câu hỏi tự kiểm tra

1. FTS index khác GSI index của SQL++ ở điểm nào?
2. Vì sao `WHERE name LIKE "%abc%"` không mặc nhiên thay được Search Service?
3. Global Search index và scoped Search index nên gọi SDK ở cấp nào?
4. Analyzer ảnh hưởng gì tới tìm có dấu/không dấu tiếng Việt?
5. `index`, `store` và `docvalues` có giống nhau không?
6. `SearchQuery.match` khác `term` và `queryString` như thế nào?
7. Vì sao tenant filter cần nằm trong mọi truy vấn nhiều nhánh OR?
8. `SearchRow.id()` và `score()` có đủ để tạo một entity `Product` hoàn chỉnh không?
9. Có nên lấy CAS từ Search score để ghi điều kiện không?
10. Vì sao `fields("name")` chưa chắc trả name?
11. `getAllReplicas` có liên hệ trực tiếp với Search Service không?
12. `SearchResult.metaData().metrics().totalRows()` có phải count tuyệt đối bất biến không?
13. Vì sao index vừa ghi có thể chưa tìm thấy ngay?
14. `consistentWith(MutationState)` giải quyết vấn đề gì và chưa tạo bảo đảm gì?
15. `REQUEST_PLUS` của SQL++ có tự áp dụng cho `searchQuery` không?
16. Vì sao hydration có thể trả ít items hơn hits Search ban đầu?
17. Vì sao `flatMap` hydrate có thể phá relevance order?
18. Khi nào cần materialized snapshot thay vì Search pagination?

## 33. Tài liệu chính thức và chú ý theo phiên bản

- [Couchbase Java SDK — Search](https://docs.couchbase.com/java-sdk/current/howtos/full-text-searching-with-sdk.html): `SearchQuery`, `SearchResult`, `SearchRow`, scoped/global index, facets, highlights, consistency và reactive API.
- [Couchbase Server — Search Index JSON Properties](https://docs.couchbase.com/server/current/search/search-index-params.html): index definitions, type mappings, analyzer, stored fields, docvalues và replicas.
- [Couchbase Server — Customize a Search Index](https://docs.couchbase.com/server/current/search/customize-index.html): tạo cấu hình index, type mapping và analyzers.
- [Couchbase Server — Document/Field Mappings](https://docs.couchbase.com/server/current/search/about-mappings.html): scope/collection type mappings và giới hạn schema.
- [Couchbase Server — Search Request JSON Properties](https://docs.couchbase.com/server/current/search/search-request-params.html): cú pháp request, phân trang, sort và Search result.
- [Couchbase Java SDK — KV Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): đọc current document/CAS, mutation token và expiry.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): khác biệt Query Service, scan consistency và SQL++ options.
- [Spring Data Couchbase — Repository](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): entity mapping, Repository query và truy cập domain.
- [Spring Data Couchbase — Template](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): cấp thao tác thấp hơn Repository, mapping và lựa chọn SDK.
- [Couchbase Java SDK — Reactive/Async APIs](https://docs.couchbase.com/java-sdk/current/howtos/concurrent-async-apis.html): reactive API, backpressure và non-blocking.

**Lưu ý theo phiên bản:** Couchbase Server đã bổ sung scoped Search indexes và các khả năng vector/hybrid qua các thế hệ 7.6+. API `SearchRequest`, `Scope.search(...)`, field mapping, Search index options và tối ưu phân trang phụ thuộc **Couchbase Server/Java SDK/Spring Data Couchbase** đang khóa. Các ví dụ minh họa Spring-managed Cluster và Couchbase Java SDK 3.x; khi triển khai phải kiểm tra package/chữ ký API, cấu hình Search index, kết quả indexing và integration test. Bước viết Markdown này không thay thế vòng Content QA chuyên môn.

> **Ghi nhớ:** Full-Text Search là **Search Service + Search index + analyzer + query/hit model**, không phải `LIKE` được tự động tối ưu. Hãy gọi đúng global/scoped index, chọn mapping tối thiểu, lọc tenant/permission an toàn, hiểu Search index lag và dùng `consistentWith` khi cần read-your-own-writes. Search hit chỉ là kết quả tìm kiếm; muốn thao tác trên entity hãy hydrate từ dữ liệu nguồn, kiểm tra trạng thái/CAS hiện hành và xử lý sai lệch giữa index với document.
