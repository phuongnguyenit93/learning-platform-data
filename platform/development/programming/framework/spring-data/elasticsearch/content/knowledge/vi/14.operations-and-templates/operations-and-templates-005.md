# Thực hiện search, count và multi-search theo API hỗ trợ

Spring Data Elasticsearch cung cấp API thao tác cấp cao để ứng dụng Java tìm kiếm document, đếm số document phù hợp và gửi nhiều truy vấn trong một lần gọi. Các thao tác này thường được thực hiện qua `ElasticsearchOperations`, một abstraction phù hợp khi truy vấn cần linh hoạt hơn các method CRUD hoặc query derivation của repository.

Ba thao tác có mục đích khác nhau:

- **Search** thực thi một truy vấn và trả về document cùng metadata như tổng số kết quả, score, highlight hoặc sort values.
- **Count** trả về số document thỏa điều kiện truy vấn, không cần tải toàn bộ document về ứng dụng.
- **Multi-search** gửi một nhóm truy vấn độc lập trong một request dạng multi-search, giúp giảm số lần trao đổi mạng khi cần nhiều tập kết quả.

Chọn đúng API giúp ứng dụng chỉ lấy dữ liệu cần thiết, tránh đọc toàn bộ index để đếm và tổ chức nhiều truy vấn có liên quan một cách hiệu quả.

## 1. ElasticsearchOperations và các API tìm kiếm

### 1.1. Vai trò của ElasticsearchOperations

`ElasticsearchOperations` là abstraction cấp cao của Spring Data Elasticsearch. Nó cung cấp các thao tác như:

- Lưu, đọc và xóa document.
- Tạo và thực thi query.
- Tìm kiếm và lấy metadata của kết quả.
- Đếm document theo query.
- Thực hiện multi-search.
- Làm việc với index thông qua IndexOperations.

Ví dụ inject operations vào service:

~~~java
@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }
}
~~~

Spring Boot thường cấu hình implementation của operations dựa trên Elasticsearch client và mapping converter trong application context. Service không cần tự tạo HTTP client cho mỗi lần tìm kiếm.

### 1.2. Khi nào dùng Operations thay vì Repository?

Repository phù hợp với CRUD và các truy vấn đã biết trước, còn Operations hữu ích khi cần xây query động hoặc lấy metadata chi tiết.

| Nhu cầu | API phù hợp |
|---|---|
| Lưu một document theo ID | ElasticsearchRepository hoặc ElasticsearchOperations |
| Tìm theo một method đã khai báo | ElasticsearchRepository |
| Query DSL động theo nhiều điều kiện | ElasticsearchOperations |
| Lấy SearchHit, score, highlight | ElasticsearchOperations |
| Đếm theo điều kiện query | ElasticsearchOperations.count |
| Gửi nhiều truy vấn độc lập | ElasticsearchOperations.multiSearch |
| Chọn index động khi chạy | Operations với IndexCoordinates |
| Quản lý settings/mapping/index | IndexOperations |

Không nhất thiết chọn một API cho toàn ứng dụng. Một service có thể dùng repository cho thao tác đơn giản và Operations cho màn hình tìm kiếm nâng cao.

### 1.3. Luồng thực thi search

~~~mermaid
flowchart TD
    A[Service tạo Query] --> B[ElasticsearchOperations.search]
    B --> C[Mapping converter và query infrastructure]
    C --> D[Elasticsearch Java client]
    D --> E[Elasticsearch cluster]
    E --> D
    D --> F[Search response]
    F --> G[SearchHits và SearchHit]
    G --> H[Service xử lý kết quả]
~~~

`Query` mô tả điều kiện và các tùy chọn tìm kiếm. `ElasticsearchOperations` chuyển query thành request phù hợp, client gửi request đến cluster và response được ánh xạ thành cấu trúc kết quả của Spring Data.

## 2. Tạo Query để tìm kiếm

### 2.1. Query là mô tả yêu cầu tìm kiếm

Spring Data Elasticsearch có abstraction `Query`. Các implementation phổ biến gồm:

- `NativeQuery`: xây dựng query theo Elasticsearch Query DSL bằng Elasticsearch Java API Client.
- `CriteriaQuery`: biểu diễn điều kiện theo dạng criteria, thuận tiện cho các bộ lọc đơn giản.
- `StringQuery`: cung cấp JSON query dưới dạng chuỗi trong các trường hợp phù hợp.

Lựa chọn loại query dựa trên độ phức tạp và phiên bản thư viện. Với truy vấn full-text, bool, nested, aggregation hoặc scoring, `NativeQuery` thường cung cấp khả năng diễn đạt đầy đủ hơn.

### 2.2. NativeQuery cho full-text search

Ví dụ tìm sản phẩm theo tên:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("wireless keyboard")
    ))
    .build();
~~~

`match` là full-text query. Elasticsearch phân tích chuỗi tìm kiếm theo analyzer phù hợp với field trước khi so khớp các token trong inverted index.

Tên field trong query là tên field Elasticsearch thực tế. Nếu entity có `@Field(name = "product_name")`, query DSL cần tham chiếu `product_name`, trừ khi query được xây theo abstraction/property path có hỗ trợ metadata ở phiên bản đang dùng.

### 2.3. Kết hợp điều kiện bằng bool query

Một tìm kiếm sản phẩm thường vừa tìm nội dung vừa lọc danh mục và trạng thái:

~~~java
Query query = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> b
        .must(m -> m.match(mm -> mm
            .field("name")
            .query("wireless keyboard")
        ))
        .filter(f -> f.term(t -> t
            .field("category")
            .value("ACCESSORY")
        ))
        .filter(f -> f.term(t -> t
            .field("available")
            .value(true)
        ))
    ))
    .build();
~~~

Trong ví dụ:

- `must` chứa điều kiện full-text có thể tham gia tính relevance score.
- `filter` giới hạn kết quả theo điều kiện chính xác và không nhằm cộng điểm relevance.
- Nhiều filter trong bool query được kết hợp theo logic AND.

Với field `category` kiểu keyword, term query phù hợp để lọc chính xác. Với field `name` kiểu text, match query phù hợp để tìm nội dung đã được analyzer xử lý.

### 2.4. CriteriaQuery cho bộ lọc đơn giản

Khi truy vấn chỉ gồm các điều kiện rõ ràng, có thể dùng Criteria API:

~~~java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

Criteria criteria = new Criteria("category").is("ACCESSORY")
    .and(new Criteria("available").is(true));

Query query = new CriteriaQuery(criteria);
~~~

Sau đó thực thi:

~~~java
SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

Criteria API dễ đọc với các điều kiện cơ bản. Với các tính năng Query DSL chuyên sâu, hãy chuyển sang NativeQuery thay vì cố biểu diễn mọi thứ bằng Criteria.

### 2.5. StringQuery khi cần JSON query trực tiếp

Có thể dùng JSON query khi muốn lưu hoặc truyền query DSL dưới dạng chuỗi:

~~~java
Query query = new StringQuery("""
{
  "bool": {
    "must": [
      {
        "match": {
          "name": "wireless keyboard"
        }
      }
    ],
    "filter": [
      {
        "term": {
          "category": "ACCESSORY"
        }
      }
    ]
  }
}
""");
~~~

StringQuery hữu ích với query JSON tĩnh hoặc được tạo từ một nguồn đã kiểm soát. Nếu ghép input người dùng vào chuỗi JSON, phải serialize/escape đúng cách. Không nối chuỗi tùy tiện vì có thể tạo JSON không hợp lệ hoặc thay đổi cấu trúc query ngoài ý muốn.

## 3. Thực hiện search

### 3.1. Gọi operations.search

Sau khi tạo query, gọi API search:

~~~java
SearchHits<ProductDocument> searchHits =
    operations.search(query, ProductDocument.class);
~~~

Overload này sử dụng index được xác định từ metadata của entity, chẳng hạn `@Document(indexName = "products")`.

Nếu cần chỉ định index tại thời điểm chạy, truyền `IndexCoordinates`:

~~~java
SearchHits<ProductDocument> searchHits =
    operations.search(
        query,
        ProductDocument.class,
        IndexCoordinates.of("products-v2")
    );
~~~

Cách này hữu ích khi ứng dụng dùng index versioned, alias hoặc cần chọn index theo cấu hình runtime. Hãy bảo đảm mapping của index được chọn tương thích với entity class.

### 3.2. Lấy nội dung document từ SearchHits

Kết quả search thường có kiểu `SearchHits<T>`, không phải chỉ là một List entity.

~~~java
for (SearchHit<ProductDocument> hit : searchHits) {
    ProductDocument product = hit.getContent();
    System.out.println(product.getName());
}
~~~

`SearchHits` chứa các kết quả `SearchHit` cùng metadata chung. `SearchHit` đại diện cho một hit và có thể cung cấp:

- `getContent()`: entity Java đã được ánh xạ.
- `getId()`: ID của document.
- `getScore()`: relevance score.
- `getSortValues()`: giá trị sort trả về.
- `getHighlightFields()`: nội dung highlight nếu query yêu cầu.
- Metadata khác tùy phiên bản và response.

Ví dụ đọc score:

~~~java
for (SearchHit<ProductDocument> hit : searchHits) {
    System.out.printf(
        "id=%s, score=%s, name=%s%n",
        hit.getId(),
        hit.getScore(),
        hit.getContent().getName()
    );
}
~~~

Score giúp quan sát mức độ liên quan theo thuật toán Elasticsearch đang sử dụng. Không diễn giải score như phần trăm chính xác hoặc xác suất kết quả đúng.

### 3.3. Metadata tổng thể của SearchHits

Một số thông tin thường dùng:

~~~java
long totalHits = searchHits.getTotalHits();
float maxScore = searchHits.getMaxScore();

List<SearchHit<ProductDocument>> hits =
    searchHits.getSearchHits();
~~~

`getTotalHits()` cho biết tổng số hit được báo cáo theo query và total-hit tracking đang cấu hình. `getMaxScore()` trả score cao nhất trong kết quả. `getSearchHits()` trả danh sách các hit của trang hiện tại.

Tổng số hit và số hit hiện có trong danh sách có thể khác nhau vì query đã giới hạn page size. Ví dụ tổng số phù hợp là 125 nhưng trang hiện tại chỉ chứa 20 hit.

### 3.4. Chỉ lấy entity khi không cần metadata

Nếu service chỉ cần nội dung entity, có thể chuyển SearchHits thành danh sách content:

~~~java
List<ProductDocument> products = searchHits.getSearchHits()
    .stream()
    .map(SearchHit::getContent)
    .toList();
~~~

Cách này đơn giản cho API trả dữ liệu. Tuy nhiên, nếu giao diện cần relevance score, highlight hoặc sort values, hãy giữ lại SearchHit để không làm mất metadata.

### 3.5. Highlight kết quả

Với tìm kiếm văn bản, highlight giúp hiển thị đoạn nội dung chứa từ khóa. Có thể cấu hình highlight query trong NativeQuery; builder cụ thể phụ thuộc phiên bản Elasticsearch Java API Client:

~~~java
Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("description")
        .query("wireless keyboard")
    ))
    .withHighlightQuery(h -> h.fields(
        "description",
        f -> f.preTags("<em>").postTags("</em>")
    ))
    .build();
~~~

Hãy đối chiếu overload highlight của phiên bản dự án và kiểm tra field có hỗ trợ highlight.

Đọc dữ liệu highlight từ hit:

~~~java
for (SearchHit<ProductDocument> hit : searchHits) {
    List<String> fragments =
        hit.getHighlightField("description");

    System.out.println(fragments);
}
~~~

Highlight fragment là nội dung Elasticsearch tạo ra từ dữ liệu được index. Khi đưa ra giao diện HTML, cần xử lý an toàn nội dung và markup; không mặc định fragment có thể được render như HTML đáng tin cậy.

## 4. Phân trang và sắp xếp search

### 4.1. Thêm Pageable vào Query

Để giới hạn số hit trả về, thêm pageable vào query:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.DESC, "price")
);

Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("keyboard")
    ))
    .withPageable(pageable)
    .build();

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

Ví dụ lấy trang đầu tiên với tối đa 20 kết quả, sắp xếp giá giảm dần. Field sort phải có mapping hỗ trợ sorting. Với field text, thường dùng subfield keyword hoặc field riêng được thiết kế cho sort.

### 4.2. Tạo Page từ SearchHits

Nếu cần cấu trúc Page của Spring Data, có thể dùng tiện ích chuyển đổi phù hợp với phiên bản, chẳng hạn `SearchHitSupport.searchPageFor`:

~~~java
SearchPage<ProductDocument> searchPage =
    SearchHitSupport.searchPageFor(searchHits, pageable);
~~~

`SearchPage` giữ nội dung SearchHit và thông tin phân trang. Nếu API chỉ cần một trang entity đơn giản, có thể trả content cùng các trường page metadata do service xây dựng.

### 4.3. Phân biệt số kết quả và số phần tử trong trang

Giả sử query phù hợp với 240 document, nhưng pageable yêu cầu 20 phần tử:

- `getTotalHits()` có thể báo tổng 240 theo total-hit tracking.
- `getSearchHits().size()` là số hit thực sự được trả ở trang hiện tại, thường là 20.
- Trang thứ 2 có offset tương ứng với page index 1.

Không dùng kích thước danh sách hiện tại làm tổng số kết quả. Ngược lại, nếu total hits được giới hạn hoặc không được theo dõi đầy đủ theo cấu hình, hãy hiểu semantics của total-hit tracking trước khi hiển thị con số như một tổng tuyệt đối.

### 4.4. Deep pagination

Phân trang offset phù hợp với các trang đầu. Với trang rất sâu, Elasticsearch phải xử lý nhiều kết quả trung gian và có giới hạn result window. Với quá trình duyệt dữ liệu lớn, cân nhắc:

- `search_after` để tiếp tục từ sort values của hit trước.
- Point-in-time (PIT) để giữ một góc nhìn ổn định trong quá trình phân trang khi cần.
- Scroll cho một số tác vụ batch/export theo API và hướng dẫn phiên bản.

Các API này cần query/sort và quản lý cursor phù hợp; không nên tăng page size hoặc result window vô hạn để thay thế.

## 5. Thực hiện count

### 5.1. Count trả số document phù hợp

Khi chỉ cần số lượng document thỏa query, dùng `ElasticsearchOperations.count`:

~~~java
long count = operations.count(
    query,
    ProductDocument.class
);
~~~

Có thể chỉ định index tường minh:

~~~java
long count = operations.count(
    query,
    ProductDocument.class,
    IndexCoordinates.of("products")
);
~~~

Count phù hợp với:

- Hiển thị số lượng kết quả tìm kiếm.
- Kiểm tra có document nào thỏa điều kiện không.
- Thống kê số sản phẩm theo danh mục.
- Ước lượng số bản ghi cần xử lý trong một tác vụ.
- Kiểm tra dữ liệu sau import hoặc migration.

### 5.2. Count không tải toàn bộ document

Count API của Elasticsearch chỉ tính số document thỏa query. Nó không cần trả `_source` của từng document để ứng dụng chuyển thành object Java.

Điều này thường hiệu quả hơn việc gọi search với page size rất lớn rồi đếm danh sách trong ứng dụng. Không nên dùng `findAll()` hoặc search toàn bộ chỉ để tính số lượng.

Ví dụ tạo query match-all để đếm toàn bộ document của entity:

~~~java
Query allQuery = NativeQuery.builder()
    .withQuery(q -> q.matchAll(m -> m))
    .build();

long totalProducts =
    operations.count(allQuery, ProductDocument.class);
~~~

Nếu cần đếm theo điều kiện, dùng cùng query/filter logic mà nghiệp vụ yêu cầu.

### 5.3. Count theo điều kiện

Ví dụ đếm số sản phẩm đang có sẵn trong danh mục ACCESSORY:

~~~java
Query availableAccessories = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> b
        .filter(f -> f.term(t -> t
            .field("category")
            .value("ACCESSORY")
        ))
        .filter(f -> f.term(t -> t
            .field("available")
            .value(true)
        ))
    ))
    .build();

long total = operations.count(
    availableAccessories,
    ProductDocument.class
);
~~~

Các filter được dùng giống với điều kiện tìm kiếm. Nếu search và count phải hiển thị cùng một tập dữ liệu, hãy tái sử dụng logic xây query để tránh hai nơi vô tình có điều kiện khác nhau.

### 5.4. Count và total hits của search khác nhau ở cách dùng

Search trả document và metadata; count chỉ trả số lượng. Nếu màn hình cần cả danh sách và tổng số kết quả, có thể:

- Gọi search và dùng total hits nếu query/search request đang theo dõi tổng hit phù hợp.
- Gọi count riêng khi chỉ cần số lượng hoặc cần tránh tải document.
- Cân nhắc chi phí của hai request nếu gọi cả search lẫn count cho cùng một điều kiện.

Không cần gọi count riêng chỉ để lấy tổng nếu response search đã cung cấp total hits đúng với yêu cầu. Ngược lại, nếu total-hit tracking bị giới hạn hoặc không được yêu cầu trong search, hãy gọi count riêng khi nghiệp vụ cần con số đầy đủ.

### 5.5. Count không phải thống kê mọi loại dữ liệu

Count trả số document phù hợp với query. Nó không cung cấp phân nhóm theo category, tổng giá, trung bình hoặc histogram.

Nếu cần thống kê như số sản phẩm trong từng danh mục, tổng giá trị tồn kho, giá trung bình theo thương hiệu hoặc số document theo khoảng ngày, nên dùng aggregation. Không lặp nhiều count request cho từng nhóm nếu một aggregation có thể trả kết quả hiệu quả hơn.

### 5.6. Count và tính nhất quán dữ liệu

Elasticsearch là hệ thống tìm kiếm near-real-time. Một document vừa ghi có thể chưa xuất hiện trong search/count cho đến khi refresh làm dữ liệu trở nên searchable.

Vì vậy, nếu ứng dụng vừa ghi rồi lập tức đếm hoặc tìm kiếm, kết quả quan sát được có thể phụ thuộc refresh behavior và cấu hình. Không nên mặc định mọi write lập tức nhìn thấy qua search. Hãy xác định yêu cầu nhất quán và chỉ dùng refresh policy phù hợp khi thực sự cần.

## 6. Thực hiện multi-search

### 6.1. Multi-search giải quyết nhu cầu nào?

Một trang tìm kiếm có thể cần nhiều truy vấn độc lập:

- Danh sách sản phẩm theo từ khóa.
- Danh sách sản phẩm nổi bật.
- Gợi ý theo danh mục.
- Các kết quả liên quan.
- Nhiều nhóm nội dung trên cùng một màn hình.

Nếu gửi từng query tuần tự, ứng dụng phải tạo nhiều lần round trip đến cluster. Multi-search cho phép gửi nhiều truy vấn trong một request dạng `_msearch`.

Multi-search giảm overhead trao đổi request/response, nhưng các truy vấn con vẫn được Elasticsearch thực thi độc lập. Nó không tạo transaction và không bảo đảm mọi truy vấn nhìn thấy cùng một snapshot dữ liệu.

### 6.2. Gọi multiSearch từ ElasticsearchOperations

Spring Data Elasticsearch cung cấp API multi-search trên Operations trong các phiên bản hỗ trợ. Với nhiều query cùng ánh xạ về một entity class, có thể dùng dạng:

~~~java
List<Query> queries = List.of(
    NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
            .field("name")
            .query("wireless keyboard")
        ))
        .withPageable(PageRequest.of(0, 5))
        .build(),

    NativeQuery.builder()
        .withQuery(q -> q.term(t -> t
            .field("category")
            .value("ACCESSORY")
        ))
        .withPageable(PageRequest.of(0, 5))
        .build()
);

List<SearchHits<ProductDocument>> results =
    operations.multiSearch(queries, ProductDocument.class);
~~~

Chữ ký chính xác của multiSearch và các overload có thể khác theo phiên bản Spring Data Elasticsearch. Hãy kiểm tra API của dependency trong dự án, đặc biệt khi cần chỉ định IndexCoordinates hoặc các kiểu entity khác nhau.

### 6.3. Đọc từng nhóm kết quả

Mỗi phần tử trong danh sách kết quả tương ứng với một query đầu vào theo thứ tự request/response của multi-search:

~~~java
for (int i = 0; i < results.size(); i++) {
    SearchHits<ProductDocument> group = results.get(i);

    System.out.println("Query group " + i);
    System.out.println("Total hits: " + group.getTotalHits());

    for (SearchHit<ProductDocument> hit : group) {
        System.out.println(hit.getContent().getName());
    }
}
~~~

Trong ứng dụng thật, nên đặt tên hoặc mô tả query ở service để biết nhóm kết quả nào dùng cho khu vực nào trên giao diện. Không phụ thuộc vào thứ tự ngầm định nếu service tự sắp xếp hoặc biến đổi danh sách query trước khi gửi.

### 6.4. Chỉ định index cho multi-search

Nếu các truy vấn cùng tìm trên một index hoặc alias, dùng overload hỗ trợ `IndexCoordinates`:

~~~java
List<SearchHits<ProductDocument>> results =
    operations.multiSearch(
        queries,
        ProductDocument.class,
        IndexCoordinates.of("products")
    );
~~~

Nếu các query cần tìm ở nhiều index hoặc dùng nhiều kiểu entity khác nhau, hãy xem overload multi-search được cung cấp trong phiên bản đang dùng. Có thể cần API client cấp thấp hơn để biểu diễn từng request với target index riêng.

### 6.5. Multi-search không phải một query bool

Cần phân biệt:

- **Bool query** kết hợp nhiều điều kiện để tạo một tập kết quả duy nhất.
- **Multi-search** gửi nhiều query độc lập và nhận nhiều tập kết quả riêng.

Ví dụ, muốn tìm sản phẩm vừa thuộc category ACCESSORY vừa có tên chứa keyboard, hãy dùng bool query. Nếu muốn hiển thị hai danh sách riêng: “sản phẩm keyboard” và “sản phẩm mới thuộc ACCESSORY”, hãy dùng multi-search.

Không dùng multi-search chỉ để thay thế một bool query có thể biểu diễn thành một request duy nhất.

### 6.6. Lỗi trong multi-search

Các truy vấn con được xử lý độc lập. Một query có thể thành công trong khi query khác gặp lỗi cú pháp, mapping hoặc quyền truy cập tùy cách Elasticsearch/client báo kết quả.

Hãy xác định cách phiên bản Spring Data đang dùng biểu diễn lỗi multi-search. Một số API có thể ném exception khi response chứa item lỗi; API client cấp thấp có thể cung cấp trạng thái từng item. Không giả định cả danh sách thành công chỉ vì request HTTP ngoài cùng được chấp nhận.

Với các khu vực giao diện độc lập, service có thể xử lý lỗi theo từng nhóm để không làm mất mọi kết quả chỉ vì một query phụ thất bại, nếu API abstraction cho phép nhận diện lỗi riêng. Nếu abstraction ném exception cho toàn bộ thao tác, cân nhắc gọi từng query hoặc dùng client response cấp thấp hơn khi cần xử lý độc lập.

## 7. Tối ưu số request và dữ liệu trả về

### 7.1. Chỉ lấy field cần thiết

Nếu giao diện chỉ hiển thị tên và giá, không nhất thiết tải mọi field lớn trong document. Có thể dùng source filtering hoặc cơ chế projection phù hợp với query API.

Ví dụ cấu hình source includes bằng NativeQuery builder có thể thay đổi theo phiên bản client. Hãy kiểm tra builder hỗ trợ source filtering và xác nhận entity mapping vẫn có thể tạo object hợp lệ từ các field được chọn.

Nếu bỏ field bắt buộc hoặc constructor property, object có thể được tạo với giá trị mặc định/null. Vì vậy, source filtering cần đi cùng thiết kế DTO hoặc entity projection rõ ràng.

### 7.2. Giới hạn page size

Không lấy hàng nghìn document chỉ vì API cho phép. Đặt giới hạn page size ở tầng service và kiểm tra tham số đầu vào.

~~~java
int safePage = Math.max(page, 0);
int safeSize = Math.min(Math.max(size, 1), 100);

Pageable pageable = PageRequest.of(safePage, safeSize);
~~~

Giới hạn trên cần được chọn dựa trên kích thước document, độ trễ và nhu cầu giao diện. Với export hoặc batch processing, dùng cơ chế duyệt dữ liệu phù hợp thay vì mở rộng page size vô hạn.

### 7.3. Tránh gọi count không cần thiết

Một màn hình có thể gọi search rồi gọi count riêng cho cùng một query dù SearchHits đã có total hits. Điều này tạo thêm tải và request.

Hãy xác định giao diện thực sự cần gì:

- Chỉ hiển thị một trang kết quả: search có thể đủ.
- Hiển thị tổng số chính xác theo yêu cầu: dùng total-hit tracking phù hợp hoặc count.
- Chỉ cần biết có kết quả hay không: giới hạn search ở một hit hoặc dùng exists/count phù hợp.
- Thống kê theo nhóm: dùng aggregation.

### 7.4. Multi-search không phải lúc nào cũng nhanh hơn

Multi-search giảm round trip, nhưng số query con, kích thước response và tổng công việc trên shard vẫn tồn tại. Một request multi-search quá lớn có thể tạo burst tải lên cluster.

Hãy giới hạn số truy vấn trong một batch, tránh lặp lại query giống nhau và đo độ trễ đầu-cuối. Nếu các query có mức ưu tiên khác nhau, có thể tách thành nhóm để kiểm soát timeout và lỗi tốt hơn.

## 8. Chọn index và entity type

### 8.1. Dùng index từ @Document

Với entity có:

~~~java
@Document(indexName = "products")
public class ProductDocument {
    // ...
}
~~~

lời gọi:

~~~java
operations.search(query, ProductDocument.class);
~~~

có thể lấy index từ metadata entity.

### 8.2. Dùng IndexCoordinates

Khi index được chọn động:

~~~java
IndexCoordinates coordinates =
    IndexCoordinates.of("products-v2");

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class, coordinates);
~~~

Cách này thường dùng với alias hoặc index theo phiên bản. Đảm bảo target index có mapping tương thích với ProductDocument. Nếu index chứa document có schema khác, converter có thể không ánh xạ đúng dữ liệu.

### 8.3. Một entity, nhiều index

Có thể tìm cùng kiểu document qua nhiều index khi schema tương thích:

~~~java
IndexCoordinates coordinates =
    IndexCoordinates.of("products-v1", "products-v2");

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class, coordinates);
~~~

Đây là ví dụ chọn nhiều index trong các overload hỗ trợ IndexCoordinates. Trước khi dùng, kiểm tra phiên bản API và bảo đảm mapping giữa các index đủ tương thích. Nếu field cùng tên nhưng khác kiểu hoặc cấu trúc, kết quả có thể lỗi hoặc không nhất quán.

## 9. Xử lý SearchHits trong tầng service

### 9.1. Tạo response DTO

Không nhất thiết trả trực tiếp SearchHits hoặc entity Elasticsearch ra controller. Có thể chuyển thành DTO phù hợp với API:

~~~java
public record ProductSearchItem(
    String id,
    String name,
    BigDecimal price,
    float score
) {
}
~~~

Chuyển đổi:

~~~java
List<ProductSearchItem> items = searchHits.getSearchHits()
    .stream()
    .map(hit -> new ProductSearchItem(
        hit.getId(),
        hit.getContent().getName(),
        hit.getContent().getPrice(),
        hit.getScore()
    ))
    .toList();
~~~

Cách này giúp API không phụ thuộc trực tiếp vào metadata nội bộ của Spring Data. Nếu cần highlight, có thể thêm trường fragments vào DTO sau khi làm sạch/escape nội dung theo cách hiển thị.

### 9.2. Phân biệt total hits và returned hits

Ví dụ response DTO cho một trang:

~~~java
public record ProductSearchResponse(
    List<ProductSearchItem> items,
    long totalHits,
    int page,
    int size
) {
}
~~~

Service có thể lấy total từ SearchHits và content từ danh sách hit:

~~~java
ProductSearchResponse response = new ProductSearchResponse(
    items,
    searchHits.getTotalHits(),
    pageable.getPageNumber(),
    pageable.getPageSize()
);
~~~

Nếu total-hit tracking được giới hạn, cần biểu diễn rõ semantics của tổng số kết quả cho client thay vì hiển thị như một con số chính xác tuyệt đối.

## 10. Kiểm thử search, count và multi-search

### 10.1. Unit test cho logic xây query

Có thể kiểm thử riêng phần service tạo query, chuẩn hóa input, giới hạn page size và chuyển kết quả sang DTO. Những test này không thay thế integration test cho Elasticsearch.

### 10.2. Integration test với Elasticsearch

Để xác minh query DSL và mapping, cần chạy với một Elasticsearch instance tương thích, chẳng hạn container test hoặc môi trường kiểm thử riêng.

Một kịch bản cơ bản:

1. Tạo index với mapping và analyzer cần thiết.
2. Index một tập document mẫu.
3. Thực hiện search và xác nhận ID/content trả về.
4. Thực hiện count với cùng điều kiện và so sánh tổng.
5. Gửi multi-search với hai query khác nhau và xác nhận mỗi nhóm kết quả.
6. Kiểm tra phân trang, sort và field thiếu.
7. Kiểm tra query không có kết quả.
8. Kiểm tra một query con lỗi trong multi-search theo cách API phiên bản đang dùng báo lỗi.
9. Dọn index test sau khi hoàn thành.

Không chỉ mock ElasticsearchOperations rồi kết luận query DSL đúng. Mock kiểm tra cách service gọi API; integration test kiểm tra Elasticsearch thực thi query và mapping thực tế.

### 10.3. Bộ dữ liệu cần có trường hợp biên

Nên có document:

- Thiếu field tùy chọn.
- Có field null hoặc collection rỗng.
- Chứa chữ hoa/thường, dấu và ký tự đặc biệt.
- Có giá trị số ở biên lọc.
- Thuộc nhiều danh mục và trạng thái khác nhau.
- Có nội dung dài hoặc nested object nếu query sử dụng.
- Có ID trùng khi ghi lại để kiểm tra semantics update.

Những dữ liệu này giúp phát hiện sai khác giữa query mong đợi, analyzer, mapping và dữ liệu thực tế.

## 11. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Search trả về danh sách rỗng | Query không khớp, sai field name hoặc analyzer không tương thích | Kiểm tra mapping, _analyze và query DSL |
| Search có hit nhưng content thiếu field | Source filtering hoặc document không có field | Kiểm tra _source, mapping và projection |
| Total hits khác số phần tử trong danh sách | Query có phân trang | Dùng getTotalHits cho tổng và getSearchHits().size() cho trang hiện tại |
| Count thấp hơn kỳ vọng ngay sau khi ghi | Document chưa searchable do refresh timing | Kiểm tra refresh behavior và yêu cầu nhất quán |
| Count và search dùng điều kiện khác nhau | Logic query được xây riêng ở hai nơi | Tái sử dụng query/filter builder |
| Sort không hoạt động | Field text không hỗ trợ sort hoặc field không tồn tại | Dùng keyword field và kiểm tra mapping |
| Search score bằng 0 hoặc không như mong đợi | Query/filter context hoặc scoring strategy | Kiểm tra bool clauses và query type |
| Multi-search thiếu một nhóm kết quả | Query con lỗi hoặc response item bị xử lý khác nhau | Kiểm tra lỗi từng item theo API/client version |
| Multi-search quá chậm | Quá nhiều query con hoặc mỗi query đều nặng | Giảm số query, tối ưu từng query và đo tải |
| Lỗi khi chỉ định index động | Mapping target index không tương thích entity | Kiểm tra IndexCoordinates và mapping thực tế |
| Search bị timeout | Query rộng, wildcard/aggregation nặng hoặc cluster quá tải | Kiểm tra profile/query, shard load và timeout |

Khi điều tra, hãy kiểm tra request DSL thực tế và response từ Elasticsearch. Đừng chỉ nhìn tên method hoặc object Query được tạo trong Java.

## 12. Quy trình chọn API

Khi xây một chức năng tìm kiếm, hãy xác định theo thứ tự:

1. **Cần document hay chỉ số lượng?** Nếu chỉ cần số lượng, dùng count. Nếu cần nội dung và metadata, dùng search.
2. **Một query hay nhiều query độc lập?** Một tập điều kiện dùng search với bool query; nhiều tập kết quả riêng có thể dùng multi-search.
3. **Cần metadata nào?** Nếu cần score, highlight hoặc sort values, giữ SearchHits/SearchHit.
4. **Index nào là target?** Dùng metadata @Document khi cố định; dùng IndexCoordinates khi cần chọn động.
5. **Cần phân trang thế nào?** Pageable cho trang đầu/thông thường; search_after hoặc scroll cho duyệt dữ liệu lớn.
6. **Có cần tổng hit không?** Dùng total hits nếu search đã theo dõi đủ; gọi count khi cần số lượng độc lập.
7. **Query có động và phức tạp không?** Chọn NativeQuery, CriteriaQuery hoặc StringQuery theo yêu cầu.

## 13. Những điểm cần ghi nhớ

- ElasticsearchOperations cung cấp API cấp cao để thực hiện search, count và multi-search.
- Query mô tả điều kiện; NativeQuery phù hợp khi cần Query DSL đầy đủ.
- Search trả SearchHits, trong đó mỗi SearchHit có entity content và metadata như ID, score, highlight hoặc sort values.
- Phân biệt tổng hit với số hit thực sự trả về trong trang.
- Count chỉ đếm document phù hợp, không tải toàn bộ document.
- Multi-search gom nhiều query độc lập vào một request; nó không phải bool query và không phải transaction.
- IndexCoordinates cho phép chọn index hoặc alias tường minh.
- Giới hạn page size, tránh count/search dư thừa và đo hiệu năng multi-search theo workload.
- Integration test với Elasticsearch cần thiết để xác minh mapping và query DSL thực tế.
- Chữ ký API và builder có thể thay đổi theo phiên bản Spring Data Elasticsearch/Elasticsearch Java Client; kiểm tra dependency dự án trước khi áp dụng ví dụ.

Khi hiểu rõ sự khác nhau giữa search, count và multi-search, bạn có thể chọn đúng thao tác cho từng màn hình hoặc tác vụ, chỉ tải dữ liệu cần thiết và kiểm soát tốt hơn số request gửi đến Elasticsearch cluster.
