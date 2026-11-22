# Xây dựng luồng tìm kiếm reactive và kiểm thử giới hạn tải

Một luồng tìm kiếm reactive với Spring Data Elasticsearch cần xử lý đồng thời ba việc: xây dựng query đúng semantics, giữ toàn bộ đường đi non-blocking và giới hạn lượng công việc mà ứng dụng gửi xuống Elasticsearch. Nếu chỉ đổi kiểu trả về từ List sang Flux nhưng vẫn dùng blocking client, gọi block() hoặc cho phép số request không giới hạn, ứng dụng vẫn có thể nghẽn khi tải tăng.

Một bài thực hành hoàn chỉnh nên đi từ API nhận tiêu chí tìm kiếm, validate input, tạo query, gọi ReactiveElasticsearchOperations, chuyển SearchHit thành DTO, stream kết quả về client, rồi đo hành vi dưới tải bằng dữ liệu và workload đại diện.

Luồng mục tiêu:

~~~text
HTTP request
    |
    v
WebFlux controller
    |
    v
Validate search criteria
    |
    v
Reactive search service
    |
    +-- build bounded query
    |
    +-- apply timeout / concurrency policy
    |
    v
ReactiveElasticsearchOperations
    |
    v
Reactive Elasticsearch client
    |
    v
Elasticsearch cluster
    |
    v
Flux<SearchHit<Product>>
    |
    v
DTO mapping and streaming response
~~~

## 1. Mục tiêu và phạm vi bài thực hành

Ta xây endpoint tìm kiếm sản phẩm theo từ khóa, chỉ lấy sản phẩm đang hoạt động, có thể giới hạn theo brand, sắp xếp ổn định và trả kết quả theo reactive stream.

Sau đó kiểm thử:

- Độ trễ ở tải thấp, tải bình thường và tải cao.
- Throughput thực tế so với tốc độ request được tạo.
- Tỷ lệ lỗi, timeout và request bị rơi do không đủ virtual users.
- Hành vi khi nhiều request đồng thời.
- Backpressure và giới hạn concurrency.
- Tài nguyên ở application và Elasticsearch.
- Khả năng duy trì latency trong một khoảng thời gian dài.

Ví dụ dùng Spring Boot WebFlux, Spring Data Elasticsearch reactive API, Reactor và k6. Tên method/builder có thể thay đổi theo release train; hãy dùng dependency versions tương thích do Spring Boot/Spring Data quản lý.

## 2. Reactive search khác blocking search ở đâu?

Trong mô hình blocking:

~~~java
List<Product> products = productRepository.findByNameContaining(keyword);
~~~

Thread gọi method phải chờ I/O hoàn tất. Nếu có nhiều request đồng thời, nhiều thread có thể bị giữ trong thời gian chờ Elasticsearch.

Trong mô hình reactive:

~~~java
Flux<Product> products = reactiveProductRepository.findByNameContaining(keyword);
~~~

Method trả về Publisher mô tả công việc. I/O được thực hiện bất đồng bộ khi pipeline được subscribe. Thread không cần bị giữ chỉ để chờ network response.

Điều đó giúp sử dụng thread hiệu quả hơn trong workload I/O-bound, nhưng không làm Elasticsearch có năng lực xử lý vô hạn. Cluster vẫn có số CPU, shard, search thread, memory, file descriptor và network hữu hạn.

### 2.1. Reactive không đồng nghĩa nhanh hơn trong mọi trường hợp

Reactive có thể giảm chi phí thread-per-request và giúp quản lý luồng dữ liệu. Nó không tự làm query DSL rẻ hơn, số shard ít đi, Elasticsearch xử lý nhiều query hơn, mapping/analyzer hiệu quả hơn hoặc một request nặng trở thành request nhẹ.

Nếu query tốn 2 giây ở Elasticsearch, reactive pipeline vẫn phải chờ kết quả đó. Lợi ích là thread ứng dụng có thể phục vụ công việc khác trong lúc chờ.

### 2.2. Không trộn blocking và reactive tùy tiện

Các thao tác sau làm mất lợi ích reactive nếu thực hiện trên event-loop:

- Gọi RestHighLevelClient đồng bộ.
- Dùng RestTemplate hoặc JDBC blocking trực tiếp.
- Gọi Mono.block() hoặc Flux.blockFirst().
- Đọc file/network bằng API blocking.
- Chờ Future.get() không giới hạn.

Nếu buộc phải gọi API blocking, cô lập nó trên boundedElastic hoặc một executor có giới hạn, đồng thời đo và giới hạn concurrency. Tốt hơn là dùng API reactive/non-blocking tương ứng.

## 3. Cấu hình reactive Elasticsearch

Spring Data Elasticsearch cung cấp ReactiveElasticsearchConfiguration để tạo client và operations cho reactive stack.

Ví dụ cấu hình cơ bản:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ReactiveElasticsearchConfiguration;

@Configuration
class ReactiveSearchConfiguration
        extends ReactiveElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo("localhost:9200")
            .withConnectTimeout(Duration.ofSeconds(3))
            .withSocketTimeout(Duration.ofSeconds(5))
            .build();
    }
}
~~~

Đây là cấu hình minh họa. Cấu hình TLS, authentication, path prefix và transport cần khớp môi trường. Spring Data Elasticsearch 6.x dùng Elasticsearch 9 client generation và Rest5Client mặc định; các version trước có client stack khác. Không copy cấu hình client giữa các major version mà không kiểm tra migration guide.

### 3.1. Phân biệt imperative và reactive beans

| Thành phần | Reactive type |
| --- | --- |
| Client | ReactiveElasticsearchClient |
| Operations | ReactiveElasticsearchOperations |
| Repository | ReactiveElasticsearchRepository |
| Auditing provider | ReactiveAuditorAware |
| Callback | ReactiveBeforeConvertCallback và các reactive callback tương ứng |

Không inject ElasticsearchOperations imperative vào service reactive rồi gọi nó trên event-loop. Nếu ứng dụng cần cả hai stack, đặt bean name/qualifier rõ ràng.

### 3.2. Timeout ở các lớp khác nhau

Phân biệt:

- Connect timeout: thời gian thiết lập kết nối.
- Socket/response timeout: thời gian chờ phản hồi ở transport.
- Elasticsearch search timeout: giới hạn thực thi search phía server trong phạm vi API.
- Application deadline: thời gian tối đa mà API nghiệp vụ cho phép.
- Client timeout: thời gian caller chờ response.

Các timeout phải phối hợp với nhau. Nếu client timeout sau 2 giây nhưng server vẫn tiếp tục xử lý query 10 giây, tài nguyên Elasticsearch vẫn có thể bị tiêu thụ sau khi caller đã bỏ cuộc.

## 4. Mapping và document cho tìm kiếm

Ví dụ entity:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products-read")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Keyword)
    private String brandId;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Date)
    private Instant updatedAt;

    // Constructors, getters and setters
}
~~~

Alias products-read có thể trỏ tới một index vật lý hoặc nhiều index có mapping tương thích. Khi chạy load test, dùng index test riêng hoặc alias trỏ đến dataset đã chuẩn bị trong cluster kiểm thử.

### 4.1. Mapping phải phù hợp query

- name và description là text để full-text search.
- brandId và status là keyword để exact match/filter.
- price là numeric để range và sort.
- updatedAt là date để sort theo thời gian.
- id cần có semantics ổn định để làm tie-breaker nếu được dùng trong sort.

Không dùng term query để tìm từ trong text field đã được analyzer xử lý. Dùng match/multi_match cho full-text; dùng keyword field cho exact match.

### 4.2. Analyzer và dữ liệu kiểm thử

Load test cần dữ liệu gần với production: phân bố độ dài name/description, số lượng brand/category, tỷ lệ document ACTIVE/INACTIVE, số lượng shard và replica, mức độ phân bố term, tỷ lệ query có kết quả và không có kết quả.

Dataset quá nhỏ có thể nằm trọn trong cache và không phản ánh chi phí của hệ thống thật. Dataset quá lớn nhưng thiếu phân bố thực tế cũng có thể tạo workload sai.

## 5. Thiết kế API tìm kiếm có giới hạn

API không nên cho client yêu cầu page size tùy ý hoặc truy vấn wildcard/index pattern tự do.

Ví dụ request:

~~~http
GET /api/products/search?q=wireless%20keyboard&brandId=BRAND-10&page=0&size=20
~~~

Quy ước:

- q bắt buộc, độ dài có giới hạn.
- page bắt đầu từ 0 và không âm.
- size mặc định 20, tối đa 50.
- Sort được server kiểm soát hoặc whitelist.
- Tenant/security filters được lấy từ context đã xác thực.
- Không nhận raw Elasticsearch Query DSL từ public API.

### 5.1. Validate trước khi gọi Elasticsearch

~~~java
private static final int MAX_SIZE = 50;
private static final int MAX_OFFSET = 10_000;

private void validate(String keyword, int page, int size) {
    if (keyword == null || keyword.isBlank()) {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST,
            "Search keyword is required"
        );
    }

    if (keyword.length() > 120) {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST,
            "Search keyword is too long"
        );
    }

    if (page < 0 || size < 1 || size > MAX_SIZE) {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST,
            "Invalid page or size"
        );
    }

    long offset = (long) page * size;
    if (offset + size > MAX_OFFSET) {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST,
            "Deep pagination is not supported by this endpoint"
        );
    }
}
~~~

Giới hạn offset ở đây phù hợp với ví dụ phân trang nông. Với kết quả sâu, thiết kế endpoint cursor-based dùng search_after và PIT thay vì tăng max_result_window.

### 5.2. Không tin sort field từ client

~~~java
Sort resolveSort(String requestedSort) {
    return switch (requestedSort) {
        case "price-asc" ->
            Sort.by(Sort.Direction.ASC, "price");
        case "price-desc" ->
            Sort.by(Sort.Direction.DESC, "price");
        case "newest" ->
            Sort.by(Sort.Direction.DESC, "updatedAt");
        default ->
            Sort.by(Sort.Direction.DESC, "updatedAt");
    };
}
~~~

Không nối trực tiếp chuỗi client gửi vào tên field trong query. Chỉ cho phép các field đã được mapping và được nghiệp vụ phê duyệt.

## 6. Xây query reactive bằng NativeQuery

NativeQuery cho phép xây Elasticsearch Query DSL bằng Elasticsearch Java API Client model.

Ví dụ tìm theo tên/mô tả, lọc trạng thái và brand, sắp xếp theo thời gian cập nhật:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

private Query buildQuery(
        String keyword,
        String brandId,
        int page,
        int size) {

    return NativeQuery.builder()
        .withQuery(q -> q.bool(b -> {
            b.must(m -> m.multiMatch(mm -> mm
                .query(keyword)
                .fields("name^3", "description")
            ));

            b.filter(f -> f.term(t -> t
                .field("status")
                .value("ACTIVE")
            ));

            if (brandId != null && !brandId.isBlank()) {
                b.filter(f -> f.term(t -> t
                    .field("brandId")
                    .value(brandId)
                ));
            }

            return b;
        }))
        .withPageable(PageRequest.of(
            page,
            size,
            Sort.by(
                Sort.Order.desc("updatedAt"),
                Sort.Order.asc("id")
            )
        ))
        .build();
}
~~~

Đây là ví dụ theo builder style của Elasticsearch Java API Client; signature của bool builder và query overload có thể khác theo version. Kiểm tra compile với dependency thực tế. Ý nghĩa query cần giữ:

- multi_match ở query context để tính relevance.
- status và brand ở filter context vì chỉ là điều kiện giữ/loại.
- sort có tie-breaker để thứ tự ổn định.
- page size bị giới hạn trước khi build query.

### 6.1. Vì sao filter nên tách khỏi must?

status=ACTIVE và brandId là điều kiện chính xác, không cần làm thay đổi relevance score. Đưa chúng vào bool.filter giúp query diễn đạt đúng semantics và tránh tính điểm không cần thiết cho các điều kiện đó.

### 6.2. Trường hợp không có keyword

Nếu sản phẩm cần hỗ trợ lọc mà không có từ khóa, hãy tạo một query branch riêng chỉ có bool.filter hoặc match_all kết hợp filter. Không gửi chuỗi rỗng vào match/multi_match.

### 6.3. Query phải có giới hạn

Một endpoint tìm kiếm nên giới hạn page size, offset hoặc cursor lifetime, số filter được phép, kích thước terms list, độ dài keyword, wildcard/regex usage, query timeout và kích thước response.

Một query hợp lệ về cú pháp vẫn có thể quá tốn tài nguyên.

## 7. Reactive search service

Service trả Flux<SearchHit<ProductDocument>> hoặc Flux<DTO> để caller compose tiếp.

~~~java
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
class ProductSearchService {

    private final ReactiveElasticsearchOperations operations;

    ProductSearchService(ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    Flux<ProductSearchItem> search(
            String keyword,
            String brandId,
            int page,
            int size) {

        validate(keyword, page, size);
        Query query = buildQuery(keyword, brandId, page, size);

        return operations.search(query, ProductDocument.class)
            .map(this::toSearchItem);
    }

    private ProductSearchItem toSearchItem(
            SearchHit<ProductDocument> hit) {
        ProductDocument product = hit.getContent();
        return new ProductSearchItem(
            product.getId(),
            product.getName(),
            product.getBrandId(),
            product.getPrice(),
            hit.getScore()
        );
    }
}
~~~

SearchHit giữ metadata như score và sort values bên cạnh content. Nếu chỉ cần entity, có thể dùng overload trả Flux<T>, nhưng khi cần score/sort metadata thì giữ SearchHit.

### 7.1. DTO response

~~~java
public record ProductSearchItem(
    String id,
    String name,
    String brandId,
    Double price,
    Float score
) {}
~~~

Không trả trực tiếp toàn bộ entity nếu nó chứa field nội bộ, dữ liệu không cần thiết hoặc thông tin nhạy cảm. DTO giúp giới hạn payload và giảm serialization cost.

### 7.2. Không collect toàn bộ kết quả không giới hạn

Tránh collectList cho một query có thể trả hàng trăm nghìn document. collectList giữ toàn bộ phần tử trong memory cho đến khi stream hoàn tất.

Nếu endpoint chỉ trả một page có size tối đa 50, collectList có thể chấp nhận được. Với export lớn, xử lý theo batch/stream, có checkpoint và giới hạn concurrency.

## 8. WebFlux controller và response streaming

Ví dụ endpoint trả NDJSON để mỗi item có thể được gửi khi có:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
class ProductSearchController {

    private final ProductSearchService searchService;

    ProductSearchController(ProductSearchService searchService) {
        this.searchService = searchService;
    }

    @GetMapping(
        value = "/api/products/search",
        produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    Flux<ProductSearchItem> search(
            @RequestParam String q,
            @RequestParam(required = false) String brandId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {

        return searchService.search(q, brandId, page, size);
    }
}
~~~

NDJSON phù hợp khi client cần nhận từng record. Nếu API cần một JSON object có total count, page metadata và danh sách item, có thể collect một page đã được giới hạn chặt rồi trả Mono<Response>. Đừng dùng streaming response như lý do bỏ giới hạn page size.

### 8.1. Client ngắt kết nối

Khi client hủy subscription, reactive pipeline có thể nhận cancellation. Transport và Elasticsearch request cancellation phụ thuộc client implementation/version; không giả định mọi request server-side dừng ngay lập tức.

Theo dõi request bị cancel và thời gian query còn chạy sau khi client rời đi. Đặt timeout và giới hạn concurrency để tránh query mồ côi tiêu thụ tài nguyên quá lâu.

## 9. Giới hạn concurrency ở tầng ứng dụng

Một lỗi phổ biến là nhận mọi request và gửi ngay xuống Elasticsearch. Khi traffic tăng nhanh, pending requests và connection acquisition có thể tăng, làm latency và memory phình ra.

Các cơ chế kiểm soát:

- Rate limit theo client/tenant/API.
- Bulkhead giới hạn số request search đang hoạt động.
- Timeout cho mỗi request.
- Giới hạn page size và query complexity.
- Giới hạn concurrency của batch job.
- Queue có capacity hữu hạn nếu cần buffering.
- Load shedding khi hệ thống quá tải.

### 9.1. Giới hạn concurrency trong Reactor

~~~java
Flux<SearchRequest> requests = loadRequests();

return requests.flatMap(
    request -> searchService.search(request),
    16
);
~~~

Tham số concurrency giới hạn số inner Publisher được subscribe đồng thời bởi flatMap. Giá trị 16 chỉ là ví dụ; phải đo trên workload thực tế.

Nếu cần giữ thứ tự đầu vào:

~~~java
return requests.concatMap(
    request -> searchService.search(request)
);
~~~

concatMap xử lý tuần tự, giảm concurrency và giữ thứ tự, nhưng throughput có thể thấp hơn. Chọn operator theo semantics nghiệp vụ.

### 9.2. limitRate không phải rate limiter toàn hệ thống

limitRate điều chỉnh cách upstream được request theo batch/backpressure. Nó không thay thế rate limit ở API gateway hoặc bulkhead toàn ứng dụng.

### 9.3. Cẩn thận với onBackpressureBuffer

Buffer không giới hạn có thể biến quá tải tạm thời thành OutOfMemoryError. Nếu cần buffer, đặt capacity hữu hạn, định nghĩa hành vi khi đầy (reject, drop hoặc persist), theo dõi số phần tử bị drop/reject và chọn policy phù hợp semantics dữ liệu.

Không drop request tìm kiếm của người dùng một cách âm thầm. Với load shedding, trả lỗi có thể retry như 429 hoặc 503 cùng Retry-After phù hợp.

## 10. Timeout, retry và error mapping

Không retry mọi lỗi Elasticsearch. Retry chỉ phù hợp với lỗi tạm thời và thao tác có semantics an toàn.

| Lỗi | Hành vi thường phù hợp |
| --- | --- |
| Timeout/network reset | Retry có giới hạn nếu deadline còn đủ |
| HTTP 429/rejected execution | Backoff có jitter, giảm concurrency |
| HTTP 502/503/504 | Retry có giới hạn |
| Mapping/parsing error | Không retry nguyên trạng |
| Authentication/authorization | Không retry; sửa cấu hình/quyền |
| Query syntax error | Không retry |
| Circuit breaker open | Reject nhanh hoặc fallback theo policy |

### 10.1. Retry có backoff

~~~java
return operations.search(query, ProductDocument.class)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .maxBackoff(Duration.ofSeconds(1))
            .jitter(0.5)
            .filter(this::isTransientSearchFailure)
    );
~~~

Đây là ví dụ minh họa. Phải kiểm tra exception type của client version đang dùng. Số lần retry nhỏ giúp tránh khuếch đại tải khi Elasticsearch đang quá tải.

### 10.2. Retry có thể làm tải nặng hơn

Khi cluster trả 429, nếu mọi consumer retry ngay, tải sẽ tăng thêm. Dùng exponential backoff, jitter, giới hạn retry và giảm tốc độ gửi request.

Tổng thời gian retry phải nằm trong deadline request. Nếu deadline đã hết, trả lỗi thay vì tiếp tục query trong nền.

### 10.3. Timeout pipeline

~~~java
return operations.search(query, ProductDocument.class)
    .timeout(Duration.ofSeconds(3));
~~~

Timeout ở Reactor dừng việc chờ của subscriber; khả năng hủy HTTP request và search task phía Elasticsearch phụ thuộc transport/server. Cần kết hợp timeout ở client/server và quan sát request còn chạy sau cancellation.

### 10.4. Ánh xạ lỗi thành HTTP status

Một error handler có thể phân loại:

- Input không hợp lệ: 400.
- Rate limit: 429.
- Search service quá tải/tạm thời unavailable: 503.
- Deadline hết: 504.
- Lỗi nội bộ không dự kiến: 500.

Không trả nguyên stack trace hoặc Elasticsearch error body có thể chứa tên index, query nội bộ hay thông tin hạ tầng cho public caller.

## 11. Phân trang và truy vấn sâu

Với endpoint tương tác thông thường, page size nhỏ và offset nông là lựa chọn đơn giản.

~~~java
PageRequest.of(
    page,
    size,
    Sort.by(
        Sort.Order.desc("updatedAt"),
        Sort.Order.asc("id")
    )
)
~~~

Tie-breaker id giúp thứ tự ổn định khi nhiều document có cùng updatedAt.

### 11.1. Giới hạn from/size

Elasticsearch mặc định giới hạn result window để tránh truy vấn sâu tốn memory. Tăng index.max_result_window không phải giải pháp mặc định cho pagination sâu.

### 11.2. search_after

Với luồng cuộn qua nhiều trang:

1. Mở Point in Time nếu cần view ổn định.
2. Search với sort có tie-breaker duy nhất.
3. Lấy sort values từ hit cuối.
4. Gửi search_after cho trang tiếp theo.
5. Đóng PIT khi hoàn tất.

Cursor nên được server quản lý hoặc ký để client không thể sửa index, query hoặc sort values tùy ý.

### 11.3. Load test pagination

Không chỉ benchmark trang đầu. Hãy kiểm tra trang đầu, trang sâu nhất được API cho phép, cursor/search_after, PIT lifecycle, sort field có doc values và hành vi khi dữ liệu thay đổi trong lúc paging.

Deep pagination thường có cost profile khác trang đầu.

## 12. Tổng số hits và response size

Tính chính xác tổng hits có thể tốn chi phí hơn việc chỉ lấy một page. Nếu giao diện không cần exact total, tránh yêu cầu đếm chính xác trên tập dữ liệu rất lớn.

Khi cần total, xác định có cần exact hay approximate total, giới hạn phạm vi query, dùng API/setting track total hits phù hợp version và không trả hàng nghìn aggregation buckets không cần thiết.

Response size ảnh hưởng network, serialization và memory. Chỉ trả field cần thiết, dùng DTO và giới hạn page size.

## 13. Chuẩn bị môi trường load test

Không chạy load test trên production cluster trừ khi có một kế hoạch kiểm thử được phê duyệt riêng. Dùng môi trường có cấu hình gần production và dữ liệu đại diện.

Chuẩn bị:

- Spring Boot app được build ở profile gần production.
- Elasticsearch cluster test với số node/shard/replica phù hợp.
- Mapping và analyzer tương đương.
- Dataset đại diện.
- Index/alias riêng cho load test.
- k6 hoặc công cụ load test khác.
- Dashboard/metrics cho app và Elasticsearch.
- Giới hạn tài nguyên và kế hoạch dừng test.

### 13.1. Không dùng dataset quá nhỏ

Dataset quá nhỏ có thể luôn nằm trong page cache hoặc query cache. Nó không đại diện cho workload production.

Chuẩn bị dữ liệu với số lượng document đủ lớn, phân bố field và term thực tế, tỷ lệ document phù hợp query gần production, một số query phổ biến và một số query ít phổ biến, document có kích thước khác nhau.

### 13.2. Warm-up

Trước khi đo:

1. Khởi động application và Elasticsearch.
2. Chờ health check ổn định.
3. Gửi một lượng request warm-up.
4. Chờ JIT, connection pool và cache ổn định.
5. Bắt đầu measurement window.

Không gộp warm-up vào số liệu chính nếu mục tiêu là đo steady-state. Nếu startup latency quan trọng, đo riêng cold-start scenario.

## 14. Chọn workload và mô hình tải

| Loại test | Mục đích |
| --- | --- |
| Smoke | Xác nhận kịch bản và endpoint hoạt động |
| Baseline | Đo hiệu năng ở tải thấp/đại diện |
| Load | Đo tại mức tải dự kiến |
| Stress | Tăng tải đến khi xuất hiện giới hạn |
| Spike | Tăng tải đột ngột |
| Soak | Duy trì tải lâu để phát hiện rò rỉ/tích tụ |
| Capacity | Tìm mức throughput đáp ứng SLO |

### 14.1. Virtual users và arrival rate

Virtual users mô phỏng số luồng người dùng đồng thời. Arrival-rate executor tạo request theo tốc độ mục tiêu.

Hai đại lượng không giống nhau:

- VUs: số người dùng ảo đang thực hiện iteration.
- RPS: số request được khởi tạo mỗi giây.

Nếu response time tăng, một VU có thể tạo ít request hơn trong cùng thời gian. Vì vậy, fixed VUs không bảo đảm RPS cố định.

### 14.2. Dùng arrival rate khi cần kiểm tra throughput

Khi mục tiêu là 100 request/second, dùng constant-arrival-rate hoặc ramping-arrival-rate executor. Theo dõi dropped_iterations để biết k6 không đủ VU tạo request theo tốc độ đặt ra.

Không kết luận server chỉ từ RPS thực đạt nếu load generator đã thiếu tài nguyên.

## 15. Script k6 cho endpoint reactive search

Ví dụ script:

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const searchErrors = new Rate('search_errors');
const searchLatency = new Trend('search_latency', true);

export const options = {
  scenarios: {
    product_search: {
      executor: 'ramping-arrival-rate',
      startRate: 5,
      timeUnit: '1s',
      preAllocatedVUs: 20,
      maxVUs: 100,
      stages: [
        { target: 10, duration: '1m' },
        { target: 30, duration: '2m' },
        { target: 60, duration: '2m' },
        { target: 60, duration: '3m' },
        { target: 0, duration: '1m' }
      ]
    }
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<300', 'p(99)<700'],
    search_errors: ['rate<0.01'],
    dropped_iterations: ['count==0']
  }
};

const baseUrl = __ENV.BASE_URL || 'http://localhost:8080';

export default function () {
  const keywords = [
    'wireless keyboard',
    'mechanical keyboard',
    'gaming mouse',
    'usb hub'
  ];

  const keyword = keywords[Math.floor(Math.random() * keywords.length)];
  const url = baseUrl + '/api/products/search?q='
    + encodeURIComponent(keyword) + '&page=0&size=20';

  const response = http.get(url, {
    headers: {
      Accept: 'application/x-ndjson'
    },
    tags: {
      endpoint: 'product-search'
    }
  });

  const ok = check(response, {
    'status is 200': (r) => r.status === 200,
    'response is not empty': (r) => r.body !== null
  });

  searchErrors.add(!ok);
  searchLatency.add(response.timings.duration);

  sleep(0.1);
}
~~~

Các threshold trong ví dụ là mục tiêu minh họa, không phải cam kết hiệu năng. Hãy thay bằng SLO thực tế của hệ thống. Nếu endpoint trả JSON array thay vì NDJSON, đổi Accept header cho phù hợp.

### 15.1. Chạy smoke test

~~~bash
k6 run --vus 1 --iterations 5 search.js
~~~

### 15.2. Chạy load test

~~~bash
k6 run search.js
~~~

Trên Windows PowerShell:

~~~powershell
$env:BASE_URL = "http://localhost:8080"
k6 run .\search.js
~~~

### 15.3. Đọc kết quả

Các metric cần quan tâm:

- http_req_duration: thời gian request tổng thể.
- p(50), p(95), p(99): phân vị latency.
- http_req_failed: tỷ lệ HTTP request lỗi.
- iterations: số iteration hoàn tất.
- dropped_iterations: iteration không thể khởi tạo theo arrival rate.
- search_errors: tỷ lệ check thất bại do script ghi nhận.
- search_latency: trend latency riêng của endpoint.

Không chỉ nhìn average. p95/p99 cho thấy trải nghiệm của nhóm request chậm.

## 16. Thiết kế workload gần thực tế

Một workload tìm kiếm thường có nhiều loại query:

| Loại query | Tỷ trọng minh họa |
| --- | ---: |
| Từ khóa phổ biến, trang đầu | 45% |
| Từ khóa ít phổ biến | 15% |
| Có brand/category filter | 20% |
| Không có kết quả | 5% |
| Sort theo giá/ngày | 10% |
| Trang sâu/cursor | 5% |

Tỷ trọng phải dựa trên traffic thực tế hoặc giả định được ghi rõ. Không dùng một keyword cố định cho mọi VU vì query cache có thể làm kết quả quá lạc quan.

### 16.1. Query mix

Tạo nhiều nhóm: keyword phổ biến, keyword dài, keyword ít match, filter có cardinality thấp, filter có cardinality cao, range rộng và range hẹp, query trả ít và nhiều hits.

Không đưa wildcard/regex nặng vào workload nếu API production không cho phép chúng.

### 16.2. Page size mix

Kiểm tra các page size được API hỗ trợ, ví dụ 10, 20 và 50. Không benchmark size 10 rồi suy ra size 50 có cùng latency.

### 16.3. Cold và warm cache

Đo riêng cold-start/cache lạnh, warm steady-state, sau refresh/indexing và khi dữ liệu cập nhật liên tục. Ghi lại cách tạo cache state để kết quả có thể lặp lại.

## 17. Đo giới hạn tải ở application

Theo dõi:

- HTTP request rate và active requests.
- p50/p95/p99 latency.
- Error rate theo status/exception.
- Reactor event-loop utilization.
- Thread count và blocked threads.
- CPU và heap.
- GC pause và allocation rate.
- Connection pool active/idle/pending acquire.
- Pending requests và timeout.
- Số request bị rate limit/reject.
- Cancellation và client disconnect.

### 17.1. Event-loop bị block

Nếu một callback hoặc service gọi block(), một event-loop thread có thể bị giữ lại. Khi nhiều request đồng thời gặp đoạn blocking, throughput giảm và latency tăng đột biến.

Dấu hiệu:

- CPU không nhất thiết ở mức 100% nhưng latency tăng.
- Event-loop thread bị block.
- Có cảnh báo BlockHound nếu được bật trong test.
- Thread dump cho thấy event-loop đang chờ I/O blocking.

### 17.2. Connection pool

Reactive client vẫn có giới hạn kết nối và pending acquire. Nếu application gửi quá nhiều request đồng thời, request phải chờ lấy connection, pending queue tăng, timeout xảy ra trước khi query đến Elasticsearch và retry làm queue tăng thêm.

Không tăng connection pool vô hạn. Phải điều chỉnh theo năng lực Elasticsearch và giới hạn file descriptor/network.

## 18. Đo giới hạn tải ở Elasticsearch

Theo dõi search thread pool active/queue/rejected, CPU, JVM heap và GC, old-generation pressure, circuit breaker trips, search latency theo shard, query cache hit/miss và memory, segment count/merge activity, disk I/O, network throughput, shard count/size và search task đang chạy.

### 18.1. Search thread pool queue

Nếu queue tăng liên tục và rejected tăng, cluster không xử lý kịp tốc độ request vào. Tăng queue size có thể chỉ kéo dài thời gian chờ và tiêu thụ memory, không tăng năng lực xử lý thực.

Hãy kiểm tra query cost, shard fan-out, concurrency và tốc độ request trước khi thay đổi thread pool settings.

### 18.2. Shard fan-out

Một query chạy trên nhiều shard cần fan-out và reduce. Quá nhiều shard nhỏ có thể tăng overhead coordination. Thiết kế shard count dựa trên kích thước dữ liệu và workload.

### 18.3. Query cache

Theo dõi cache nhưng không giả định mọi filter đều được cache. Cache hit ratio phải được đọc cùng latency, segment churn và query mix.

### 18.4. Circuit breaker

Elasticsearch có circuit breakers để bảo vệ memory. Khi request tạo aggregation hoặc fetch quá lớn, breaker có thể từ chối request. Đây là tín hiệu cần giới hạn query/response và điều chỉnh workload, không phải lý do mặc định để tắt breaker.

## 19. Tìm điểm nghẽn bằng cách thay đổi từng biến

Khi latency tăng, không thay đồng thời page size, shard count, pool size và query DSL. Thay một biến mỗi lần:

1. Giữ dataset và query mix cố định.
2. Tăng arrival rate theo từng bậc.
3. Ghi lại latency và error rate.
4. Quan sát app và Elasticsearch metrics.
5. Xác định thời điểm queue, rejection hoặc p99 tăng mạnh.
6. Thay một yếu tố.
7. Chạy lại cùng workload.

| Thử nghiệm | Thay đổi | Mục đích |
| --- | --- | --- |
| A | Baseline | Đo cấu hình hiện tại |
| B | Giảm page size 50 xuống 20 | Xem chi phí fetch/serialization |
| C | Bỏ aggregation không cần thiết | Xem chi phí aggregation |
| D | Thêm filter/selective query | Xem tác động giảm candidate documents |
| E | Giới hạn concurrency | Xem queue/rejection và p99 |
| F | Thay sort field | Xem doc values và sort cost |

Không coi một lần chạy là kết luận. Chạy lặp lại và giữ cùng môi trường.

## 20. Little's Law và giới hạn concurrency

\[
L = \lambda W
\]

Trong đó L là số request trung bình đang ở trong hệ thống, lambda là throughput trung bình (request/giây), W là thời gian response trung bình (giây).

Ví dụ nếu hệ thống nhận 100 request/giây và thời gian xử lý trung bình là 0,2 giây:

\[
L = 100 \times 0.2 = 20
\]

Trung bình có khoảng 20 request đang được xử lý hoặc chờ trong hệ thống.

Nếu latency tăng lên 1 giây trong khi arrival rate giữ nguyên:

\[
L = 100 \times 1 = 100
\]

Số request đồng thời tăng lên, gây thêm áp lực lên connection pool, memory và queue.

Little's Law giúp hiểu quan hệ giữa throughput, latency và concurrency; nó không tự cho biết concurrency tối đa an toàn. Giới hạn thực tế phải được đo theo tài nguyên và SLO.

### 20.1. Đặt bulkhead

~~~text
Incoming requests
       |
       v
Rate limiter
       |
       v
Search bulkhead (max N active)
       |
       +-- capacity available -> Elasticsearch
       |
       +-- full -> 429/503
~~~

N phải được xác định bằng load test. Đặt N quá cao có thể làm Elasticsearch quá tải; quá thấp có thể không tận dụng hết năng lực cluster.

## 21. Kiểm thử backpressure và cancellation

Reactive Streams định nghĩa cơ chế subscriber request số phần tử từ publisher. Tuy nhiên, Elasticsearch search request không nhất thiết được thực thi theo kiểu một document mỗi lần downstream request.

Cần phân biệt backpressure trong Reactor pipeline, buffering/decoding ở HTTP client, fetch phase của Elasticsearch, số hits được server trả về và response serialization ở WebFlux.

### 21.1. Không giả định downstream demand điều khiển Elasticsearch shard

Backpressure giúp kiểm soát việc phát dữ liệu qua pipeline, nhưng query đã gửi đến Elasticsearch có thể đã tiêu thụ tài nguyên server. Vì vậy vẫn cần page size, query timeout và cancellation policy.

### 21.2. Test client disconnect

Tạo một client bắt đầu nhận stream rồi đóng connection sớm. Quan sát WebFlux có cancel Publisher không, reactive Elasticsearch client có hủy request transport không, search task phía Elasticsearch còn chạy bao lâu, application có giải phóng connection/permit không và có log cancellation/error bất thường không.

### 21.3. Không buffer response lớn trong memory

Nếu client cần export hàng triệu document, thiết kế export job có checkpoint và lưu kết quả vào object storage thay vì giữ toàn bộ Flux trong một HTTP response không giới hạn.

## 22. Soak test và memory leak

Soak test giữ một mức tải ổn định trong thời gian dài để phát hiện heap tăng dần, buffer không được giải phóng, connection leak, pending queue tăng, Reactor subscription không kết thúc, PIT/context không được đóng, Elasticsearch segment/merge pressure và GC pause tăng theo thời gian.

### 22.1. Dấu hiệu memory leak

- Heap sau GC tăng dần qua từng chu kỳ.
- Số object sống lâu tăng.
- Direct memory tăng.
- Pending request hoặc buffered item không giảm về baseline.
- Connection pool không trở về mức bình thường.

### 22.2. Kết thúc tài nguyên

Đảm bảo PIT được đóng, subscription kết thúc/cancel, test container và client được shutdown đúng lifecycle, scheduled task và retry publisher không tiếp tục sau test, kết nối không bị tạo mới cho mỗi request.

## 23. Integration test với Testcontainers

Unit test có thể mock ReactiveElasticsearchOperations để kiểm tra mapping/query branching. Integration test cần Elasticsearch thật để xác nhận query DSL, mapping, analyzer, sorting và reactive client.

Ví dụ test:

~~~java
@Test
void shouldReturnOnlyActiveProducts() {
    ProductDocument active = product("P-1", "Wireless Keyboard", "ACTIVE");
    ProductDocument inactive = product("P-2", "Wireless Keyboard", "INACTIVE");

    StepVerifier.create(
        operations.save(active)
            .then(operations.save(inactive))
            .then(indexOperations.refresh())
            .thenMany(searchService.search("wireless keyboard", null, 0, 20))
    )
    .assertNext(result ->
        assertThat(result.id()).isEqualTo("P-1")
    )
    .verifyComplete();
}
~~~

Đoạn code minh họa cần điều chỉnh theo kiểu trả về của refresh() và cách tạo index/alias trong phiên bản Spring Data đang dùng. Test cần dùng index riêng để tránh dữ liệu từ test khác ảnh hưởng kết quả.

### 23.1. Test reactive pipeline bằng StepVerifier

StepVerifier giúp kiểm tra số phần tử, thứ tự phần tử, completion, error và cancellation trong các test phù hợp.

Không gọi subscribe thủ công trong test rồi assert ngay; test có thể kết thúc trước khi pipeline hoàn tất.

### 23.2. Test mapping và query

Integration test nên xác nhận keyword query tìm được document mong đợi, filter status loại document inactive, brand filter hoạt động, sort có tie-breaker, page size không vượt giới hạn, empty result trả stream rỗng và invalid input bị reject trước khi gọi Elasticsearch.

## 24. Test giới hạn tải theo từng giai đoạn

| Giai đoạn | Tải | Thời lượng | Mục tiêu |
| --- | --- | --- | --- |
| Smoke | 1 VU hoặc vài request | Ngắn | Xác nhận script/endpoint |
| Warm-up | Tải thấp | 1–3 phút | Ổn định JIT và connection pool |
| Baseline | 5–10 RPS | 3–5 phút | Đo latency nền |
| Load | Tăng theo bậc đến target | 5–10 phút | Xác nhận SLO |
| Stress | Tăng vượt target | Theo dõi | Tìm điểm bão hòa |
| Soak | Tải ổn định | 30–120 phút | Tìm leak/tích tụ |
| Recovery | Giảm tải về thấp | 2–5 phút | Xác nhận hệ thống hồi phục |

Các mức tải và thời lượng chỉ là ví dụ lập kế hoạch. Dùng target của sản phẩm, môi trường và ngân sách tài nguyên thực tế.

### 24.1. Điều kiện dừng test

Định nghĩa trước khi chạy: error rate vượt ngưỡng, p99 vượt giới hạn kéo dài, Elasticsearch heap/CPU đạt vùng nguy hiểm, search thread pool rejection tăng liên tục, circuit breaker trips, cluster health chuyển trạng thái không mong muốn hoặc load generator không còn tạo được arrival rate.

Dừng test khi vượt ngưỡng bảo vệ. Không cố đẩy tải vô hạn chỉ để tìm điểm crash.

## 25. Báo cáo kết quả load test

| Chỉ số | Kết quả |
| --- | --- |
| Dataset size | Số document và kích thước index |
| Cluster topology | Node, shard, replica |
| Application replicas | Số instance và CPU/memory limit |
| Target arrival rate | RPS yêu cầu |
| Achieved throughput | RPS thực tế |
| p50 | Latency median |
| p95 | Latency phân vị 95 |
| p99 | Latency phân vị 99 |
| Error rate | Tỷ lệ request lỗi |
| Dropped iterations | Iteration bị rơi từ load generator |
| App CPU/heap | Mức sử dụng application |
| ES CPU/heap | Mức sử dụng Elasticsearch |
| Search rejections | Số request bị từ chối |
| Bottleneck | Nút thắt được quan sát |

Ghi rõ phiên bản app, Spring Data, Elasticsearch, JVM, k6, cấu hình shard, query mix, warm-up và thời gian chạy. Nếu không ghi môi trường, số liệu khó so sánh giữa các lần test.

## 26. Ví dụ cấu hình rate limit và bulkhead

Ở tầng API gateway hoặc service, có thể giới hạn số request mỗi client trong một khoảng thời gian, số search request đồng thời toàn instance, số search request theo tenant và tổng thời gian chờ.

~~~text
Request
  |
  v
Authenticate and resolve tenant
  |
  v
Validate query and page size
  |
  v
Rate limit by tenant/API key
  |
  v
Acquire search permit
  |
  +-- no permit --> return 429/503
  |
  v
Execute bounded reactive query
  |
  v
Release permit on complete/error/cancel
~~~

Permit phải được giải phóng trong mọi terminal signal, kể cả error và cancellation. Nếu dùng semaphore thủ công, tránh release hai lần hoặc quên release khi client disconnect.

Resilience4j có các module RateLimiter, Bulkhead, TimeLimiter và CircuitBreaker. Chọn module tương thích với Reactor integration của version dự án; không bọc reactive Publisher bằng decorator dành riêng cho synchronous call nếu semantics không phù hợp.

## 27. Các lỗi thường gặp

**Chỉ đổi List thành Flux.** Nếu vẫn dùng blocking client hoặc block(), event-loop vẫn có thể bị nghẽn. Dùng reactive client/operations xuyên suốt.

**Subscribe thủ công trong service.** Caller mất khả năng điều phối completion và error. Trả Mono/Flux cho tầng gọi.

**Collect toàn bộ kết quả.** collectList trên tập dữ liệu lớn gây tăng memory. Giới hạn page hoặc stream theo cursor/batch.

**Cho client yêu cầu page size tùy ý.** Một request có thể tạo fetch lớn và làm cluster quá tải. Giới hạn size ở API.

**Cho phép deep pagination bằng from/size.** Chi phí tăng theo offset. Dùng search_after/PIT cho paging sâu.

**Dùng wildcard hoặc regex không giới hạn.** Query có thể mở rộng quá nhiều document/shard. Validate query capability và giới hạn pattern.

**Dùng flatMap không giới hạn.** Nhiều inner Publisher có thể tạo quá nhiều request đồng thời. Đặt concurrency và bulkhead.

**Dùng onBackpressureBuffer không giới hạn.** Queue tăng đến hết memory. Dùng buffer hữu hạn và policy khi đầy.

**Retry mọi exception.** Mapping error và authorization không thể tự hết. Retry chỉ transient error và giới hạn số lần.

**Retry ngay khi nhận 429.** Retry storm làm tải tăng thêm. Dùng backoff, jitter và giảm concurrency.

**Chỉ đo average latency.** Tail latency bị che khuất. Theo dõi p95/p99 và error rate.

**Chỉ dùng fixed VUs để tuyên bố đạt RPS.** Khi response chậm, RPS có thể giảm. Dùng arrival-rate executor nếu cần target throughput.

**Bỏ qua dropped_iterations.** Load generator có thể không tạo đủ tải. Kiểm tra tài nguyên máy chạy k6 và maxVUs.

**Dataset quá nhỏ.** Cache làm số liệu lạc quan. Dùng dữ liệu và phân bố gần production.

**Không warm-up hoặc trộn warm-up với measurement.** Kết quả khó so sánh. Tách giai đoạn.

**Chỉ theo dõi application.** Bottleneck có thể nằm ở search thread pool, shard hoặc disk. Quan sát cả Elasticsearch.

**Chỉ tăng connection pool khi thấy pending acquire.** Elasticsearch có thể đã quá tải. Đo cluster capacity trước khi tăng.

**Không kiểm tra cancellation.** Client rời đi nhưng query có thể tiếp tục tiêu thụ tài nguyên. Theo dõi cancel và server-side task.

**Không kiểm tra recovery sau stress.** Hệ thống có thể tiếp tục có queue/backlog sau khi tải giảm. Thêm recovery phase.

## 28. Quy trình thực hành từ đầu đến cuối

1. Tạo mapping và alias đọc cho dataset test.
2. Cấu hình ReactiveElasticsearchClient và ReactiveElasticsearchOperations tương thích.
3. Tạo ProductDocument với field mapping rõ ràng.
4. Xây query dùng multi_match và bool.filter.
5. Giới hạn keyword, page, size, sort và offset.
6. Viết service trả Flux<SearchHit> hoặc Flux/DTO.
7. Viết WebFlux endpoint trả NDJSON hoặc response page bounded.
8. Thêm timeout, error mapping và concurrency policy.
9. Viết StepVerifier/unit/integration tests.
10. Chuẩn bị dataset và dashboard application/Elasticsearch.
11. Chạy k6 smoke, baseline, load, stress và soak.
12. Theo dõi p95/p99, error rate, achieved RPS và dropped iterations.
13. Xác định bottleneck bằng metrics, thay một biến mỗi lần và chạy lại.
14. Ghi báo cáo cùng version/configuration để so sánh.

## 29. Checklist vận hành

- [ ] Client và Spring Data version tương thích.
- [ ] Service dùng ReactiveElasticsearchOperations hoặc reactive repository.
- [ ] Không có block() hoặc blocking I/O trên event-loop.
- [ ] Query có mapping và analyzer phù hợp.
- [ ] Keyword và filter được validate.
- [ ] Page size và offset có giới hạn.
- [ ] Sort có tie-breaker ổn định.
- [ ] Response chỉ chứa field cần thiết.
- [ ] Không collect tập dữ liệu không giới hạn.
- [ ] Concurrency và rate limit được cấu hình.
- [ ] Timeout và retry policy có giới hạn.
- [ ] Retry có backoff/jitter và chỉ áp dụng transient errors.
- [ ] Cancellation được quan sát.
- [ ] Test dùng index/dataset riêng.
- [ ] Load generator đủ tài nguyên.
- [ ] Theo dõi p95/p99, error rate và dropped iterations.
- [ ] Theo dõi app metrics và Elasticsearch metrics.
- [ ] Có điều kiện dừng stress test.
- [ ] Có recovery phase và soak test.
- [ ] Báo cáo ghi rõ dataset, topology, versions và workload.

## 30. Tài liệu tham khảo

- [Spring Data Elasticsearch - Reactive Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): reactive operations và query execution.
- [Spring Data Elasticsearch - Reactive Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/reactive-repositories.html): reactive repository abstraction.
- [Spring Data Elasticsearch - Client Configuration](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html): client configuration và version-specific client stack.
- [Spring Data Elasticsearch - NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQuery.html): xây dựng query bằng Elasticsearch Java API Client.
- [Project Reactor - Reference Guide](https://projectreactor.io/docs/core/release/reference/): Publisher, backpressure, concurrency, retry và testing.
- [Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive HTTP request handling và streaming.
- [Elasticsearch - Search API](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html): query, sort, timeout và search request options.
- [Elasticsearch - Pagination](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html): from/size, search_after và Point in Time.
- [Elasticsearch - Search thread pool](https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-threadpool.html): thread pool, queue và rejected requests.
- [k6 - Scenarios](https://grafana.com/docs/k6/latest/using-k6/scenarios/): VU-based và arrival-rate executors.
- [k6 - Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/): SLO thresholds cho latency và errors.
- [k6 - Built-in metrics](https://grafana.com/docs/k6/latest/using-k6/metrics/reference/): request duration, failed requests và dropped iterations.

Các method overload của Spring Data Elasticsearch và Java API Client thay đổi theo version. Hãy compile ví dụ với dependency thực tế và đối chiếu Javadoc tương ứng. Mục tiêu của bài thực hành là giữ reactive pipeline non-blocking, giới hạn query/concurrency và dùng load test có kiểm soát để tìm mức tải đáp ứng SLO; reactive API không thay thế việc thiết kế query và quản lý năng lực Elasticsearch.
