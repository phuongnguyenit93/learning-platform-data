# Phân biệt query cache, request cache và cache ứng dụng

Elasticsearch và ứng dụng Spring có nhiều lớp cache, nhưng mỗi lớp lưu một loại kết quả khác nhau. **Query cache** lưu kết quả của một phần query có thể tái sử dụng, chủ yếu là các query chạy trong filter context. **Request cache** lưu kết quả tìm kiếm ở cấp shard cho một request đủ điều kiện, đặc biệt hữu ích với aggregation hoặc truy vấn không cần hit (`size: 0`). **Application cache** lưu kết quả nghiệp vụ hoặc response đã xử lý ở phía ứng dụng, thường dùng Caffeine, Redis hoặc một cache provider khác.

Ba lớp cache có thể cùng tồn tại trong một request. Application cache có thể trả kết quả mà không gọi Elasticsearch; nếu cache miss, Elasticsearch có thể tái sử dụng request cache; trong lúc thực thi request, các filter phù hợp có thể được query cache hỗ trợ. Chúng không thay thế nhau vì khác phạm vi, cache key, cách invalidation và chi phí lưu trữ.

Để chọn đúng cache trong Spring Data Elasticsearch, trước hết hãy xác định phần nào lặp lại, dữ liệu thay đổi thường xuyên đến đâu và độ trễ dữ liệu cũ có thể chấp nhận được. Sau đó mới chọn cache, đặt TTL hoặc chính sách invalidation và đo hit ratio. Bật mọi cache cùng lúc mà không hiểu key và refresh behavior có thể làm hệ thống phức tạp hơn nhưng không tăng hiệu năng.

## 1. Ba lớp cache trong một kiến trúc tìm kiếm

```text
Client request
     |
     v
Application cache
     | cache hit
     +------------------------------> Cached response
     |
     | cache miss
     v
Spring Data Elasticsearch
     |
     v
Elasticsearch search request
     |
     +--> Request cache: kết quả request/shard đã được cache?
     |
     +--> Query cache: filter result của segment đã được cache?
     |
     v
Search execution / aggregation
     |
     v
Response -> application mapping -> optional app cache
```

| Lớp | Nơi lưu | Thứ được cache | Phạm vi tái sử dụng |
|---|---|---|---|
| Query cache | Heap của Elasticsearch node | Tập document phù hợp với query trong filter context, theo segment | Một filter có thể được tái sử dụng trong nhiều search request |
| Request cache | Heap của Elasticsearch node, theo shard | Kết quả của search request đủ điều kiện | Các request tương đương trên cùng shard copy |
| Application cache | JVM của ứng dụng hoặc hệ thống cache ngoài như Redis | DTO, trang kết quả, aggregation response hoặc dữ liệu nghiệp vụ | Nhiều request ứng dụng có cùng cache key |

### Ví dụ

Một dashboard luôn hiển thị số sản phẩm active theo category:

- Filter `tenantId = tenant-42` và `status = ACTIVE` có thể được query cache tái sử dụng.
- Search request chỉ trả aggregation và `size: 0` có thể được request cache lưu kết quả shard.
- API có thể cache toàn bộ dashboard DTO trong Redis trong 30 giây để tránh gọi Elasticsearch ở mỗi lần tải trang.

Mỗi cache loại bỏ một phần công việc khác nhau. Nếu dữ liệu được refresh liên tục, request cache có thể bị invalidation thường xuyên; nếu app cache TTL dài, dashboard có thể vẫn trả dữ liệu cũ dù Elasticsearch đã có dữ liệu mới.

## 2. Query cache là gì?

Query cache của Elasticsearch lưu kết quả của những query chạy trong **filter context** dưới dạng tập document phù hợp trên các segment. Khi cùng filter được dùng lại, Elasticsearch có thể sử dụng kết quả đã cache thay vì đánh giá lại filter trên segment đó.

Query cache đặc biệt hữu ích với điều kiện lọc lặp lại, chẳng hạn:

- `tenantId = tenant-42`.
- `status = ACTIVE`.
- `categoryId = c-100`.
- `visibility = PUBLIC`.
- Các range filter ổn định theo một khoảng thời gian cố định.

Ví dụ:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless mouse"
          }
        }
      ],
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "status": "ACTIVE" } }
      ]
    }
  }
}
```

Hai điều kiện `term` trong `filter` là những ứng viên phù hợp để được query cache hỗ trợ khi chúng được lặp lại đủ thường xuyên và đáp ứng điều kiện cache của Elasticsearch. Phần `match` trong `must` chạy trong query context để tính relevance score; không nên kỳ vọng query cache lưu kết quả scoring của nó theo cùng cách.

## 3. Filter context và query context

Elasticsearch phân biệt hai ngữ cảnh:

| Context | Câu hỏi | Có tính relevance score? | Mục đích thường gặp |
|---|---|---:|---|
| Query context | Document phù hợp đến mức nào? | Có | Full-text search, relevance ranking |
| Filter context | Document có thỏa điều kiện hay không? | Không | Tenant, status, category, date range, exact filters |

Query cache tập trung vào kết quả filter context. Vì vậy, hãy đặt điều kiện lọc nghiệp vụ vào `bool.filter` thay vì đưa tất cả vào `must` nếu không cần score.

### Ví dụ dùng đúng filter context

```json
{
  "query": {
    "bool": {
      "must": [
        { "multi_match": {
            "query": "wireless mouse",
            "fields": ["name^3", "description"]
        }}
      ],
      "filter": [
        { "term": { "status": "ACTIVE" } },
        { "term": { "categoryId": "c-100" } },
        { "range": { "priceAmount": { "gte": 10, "lte": 100 } } }
      ]
    }
  }
}
```

Full-text condition quyết định relevance; các điều kiện status/category/price chỉ loại document không phù hợp. Cấu trúc này thể hiện đúng semantics và cho phép Elasticsearch cân nhắc cache các filter.

### Không chuyển mọi query sang filter chỉ để cache

Nếu người dùng cần xếp hạng theo relevance, đặt `match` trong `must`/`should` để score vẫn được tính. Đưa full-text query vào filter làm mất score và có thể thay đổi thứ tự kết quả. Tối ưu cache không được làm sai semantics tìm kiếm.

## 4. Query cache hoạt động theo segment

Lucene lưu index thành các segment bất biến. Query cache gắn kết quả filter với segment cụ thể. Một filter có thể được cache trên segment đã tồn tại và tái sử dụng khi segment đó vẫn còn.

Khi có refresh, segment mới được mở cho search. Khi merge, các segment cũ có thể bị thay thế bằng segment mới. Cache entry gắn với segment cũ sẽ không còn dùng được khi segment bị loại bỏ. Vì vậy, query cache có thể mất một phần hiệu quả trong index ghi liên tục.

```text
Segment A -- filter F được cache
Segment B -- filter F được cache

Refresh tạo Segment C
  -> Cần đánh giá/cache F cho Segment C

Merge A + B -> Segment D
  -> Cache entry của A/B không còn dùng cho D
```

Điều này giải thích vì sao query cache thường có lợi hơn với dữ liệu tương đối ổn định và filter lặp lại. Index thay đổi liên tục có thể làm các cache entry bị thay thế trước khi tận dụng được nhiều lần.

## 5. Query cache không cache mọi query

Elasticsearch tự quyết định query nào đủ điều kiện và đáng cache. Không phải mọi filter trong mọi request đều lập tức được lưu. Cơ chế sử dụng heuristic, tần suất lặp, kích thước segment và ngân sách cache; chi tiết có thể thay đổi theo phiên bản.

Một số điểm cần nhớ:

- Query cache tập trung vào filter context.
- Query quá ít lặp lại có thể không đáng cache.
- Segment nhỏ hoặc vừa được tạo có thể chưa đủ điều kiện theo heuristic hiện hành.
- Cache entry bị loại khi segment tương ứng không còn tồn tại.
- Cache có dung lượng hữu hạn và sử dụng cơ chế eviction.
- Query có giá trị thay đổi theo thời gian như range chứa `now` thường khó tái sử dụng như filter cố định.

Không nên viết code phụ thuộc vào việc một filter cụ thể chắc chắn sẽ được cache. Hãy dùng filter context đúng semantics và đo hit/miss trong workload thật.

## 6. Theo dõi query cache

Có thể xem query cache statistics ở cấp node:

```http
GET /_nodes/stats/indices/query_cache
```

Hoặc xem thống kê của một index:

```http
GET /products/_stats/query_cache
```

Các chỉ số quan trọng thường gồm:

| Chỉ số | Ý nghĩa |
|---|---|
| `memory_size_in_bytes` | Bộ nhớ đang dùng cho query cache |
| `total_count` | Tổng số lần query cache được truy cập/kiểm tra theo thống kê |
| `hit_count` | Số lần tìm được cache entry phù hợp |
| `miss_count` | Số lần không tìm được entry phù hợp |
| `cache_size` | Số entry hiện có |
| `evictions` | Số entry bị loại khỏi cache |

Tên và cách nhóm thống kê có thể khác theo API/version. Dùng node stats để hiểu cache theo node và index stats để khoanh vùng workload của index.

### Tính hit ratio

Một cách tính đơn giản:

\[
\text{Hit ratio} = \frac{\text{hit count}}{\text{hit count} + \text{miss count}}
\]

Chỉ số này cần được đọc cùng số lượng query, latency và memory. Hit ratio cao không tự chứng minh hệ thống nhanh hơn; cache có thể hit cho filter rất rẻ trong khi bottleneck thực tế nằm ở scoring, fetch, aggregation hoặc network.

## 7. Request cache là gì?

Request cache của Elasticsearch lưu kết quả tìm kiếm ở cấp shard cho một search request đủ điều kiện. Nó hữu ích khi cùng một request được gửi lặp lại và phần dữ liệu liên quan chưa thay đổi.

Mặc định, Elasticsearch thường cache các search request có `size: 0`. Đây là kiểu request phổ biến cho dashboard và aggregation vì không cần trả về danh sách document hits mà chỉ cần total hits hoặc aggregation result.

Ví dụ:

```http
POST /products/_search
Content-Type: application/json

{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "status": "ACTIVE" } }
      ]
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "categoryId",
        "size": 20
      }
    }
  }
}
```

Kết quả aggregation của request này có thể được request cache lưu lại để tái sử dụng khi request tương đương chạy lại trên cùng shard copy và shard chưa refresh.

## 8. `size: 0` và cache aggregation

Dashboard thường không cần document hits; nó cần số liệu tổng hợp như:

- Số sản phẩm theo category.
- Tổng đơn hàng theo trạng thái.
- Doanh thu theo ngày.
- Số lượng người dùng theo khu vực.
- Phân phối giá theo range.

Đặt `size: 0` giúp response không chứa hits. Đây cũng là dạng request được request cache hỗ trợ mặc định trong Elasticsearch.

Ví dụ aggregation theo trạng thái:

```json
{
  "size": 0,
  "query": {
    "term": {
      "tenantId": "tenant-42"
    }
  },
  "aggs": {
    "by_status": {
      "terms": {
        "field": "status"
      }
    }
  }
}
```

Nếu dashboard gọi cùng request nhiều lần trong khi index ít thay đổi, request cache có thể giảm đáng kể công việc aggregation. Nếu index refresh liên tục, cache entry bị invalidation thường xuyên và lợi ích giảm.

## 9. Bật hoặc tắt request cache cho một request

Có thể điều khiển bằng URL parameter `request_cache`:

```http
POST /products/_search?request_cache=true
Content-Type: application/json

{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "categoryId"
      }
    }
  }
}
```

`request_cache=true` yêu cầu cache request kể cả trong trường hợp không thuộc mặc định `size: 0`, nếu request và context đáp ứng điều kiện cache. `request_cache=false` tắt request cache cho request đó.

Không nên bật `request_cache=true` cho mọi search request một cách máy móc. Với request có hits thay đổi liên tục, query chứa thời gian hiện tại hoặc key gần như duy nhất, cache có thể ít hit nhưng vẫn tiêu tốn memory và tạo churn.

## 10. Request cache key và tính tương đương của request

Request cache chỉ hữu ích khi request được lặp lại với cùng nội dung có ý nghĩa. Thay đổi query, aggregation, sort, runtime mappings hoặc các tham số ảnh hưởng kết quả có thể tạo cache key khác.

Ví dụ hai request khác nhau:

```json
{ "size": 0, "query": { "term": { "status": "ACTIVE" } } }
```

```json
{ "size": 0, "query": { "term": { "status": "INACTIVE" } } }
```

Chúng không thể dùng chung kết quả vì điều kiện khác nhau.

Một số nguyên tắc giúp request có khả năng tái sử dụng:

- Dùng cấu trúc query ổn định.
- Tránh tạo nhiều biến thể request chỉ vì thứ tự field JSON khác nhau nếu client tự serialize không nhất quán.
- Dùng `size: 0` cho aggregation-only request.
- Tránh tham số biến động không cần thiết.
- Giữ `preference` ổn định nếu muốn request đi tới cùng shard copy.
- Không thêm timestamp ngẫu nhiên hoặc correlation ID vào query body nếu chúng không ảnh hưởng kết quả.

Elasticsearch tạo cache key theo nội dung request và ngữ cảnh shard; không tự xây key ứng dụng dựa trên phỏng đoán. Khi dùng REST/client, hãy giữ request body ổn định và kiểm tra thống kê cache.

## 11. `preference` và cache locality

Một shard có thể có primary và replica. Request cache nằm trên node giữ shard copy cụ thể. Nếu hai request tương đương được gửi tới hai shard copy khác nhau, chúng có thể không dùng cùng cache entry.

Tham số `preference` có thể giúp các request có cùng preference được định tuyến ổn định hơn tới cùng shard copies:

```http
POST /products/_search?preference=dashboard-tenant-42
```

Điều này có thể cải thiện cache locality cho dashboard lặp lại. Tuy nhiên, preference cũng ảnh hưởng phân phối tải và lựa chọn shard copy. Không dùng một giá trị preference duy nhất cho mọi workload nếu nó làm dồn tải lên một node.

Với user-facing search có tải phân tán lớn, cân nhắc giữa cache locality và cân bằng tải. Với dashboard định kỳ, preference ổn định có thể hữu ích nếu đo được lợi ích.

## 12. Request cache bị invalidation khi nào?

Request cache được gắn với trạng thái shard. Khi shard refresh và dữ liệu search-visible thay đổi, kết quả request cache cũ không còn hợp lệ và bị invalidation.

Hệ quả:

- Index ít ghi và refresh thưa thường có cơ hội request cache hit cao hơn.
- Index ghi liên tục có thể invalidation cache thường xuyên.
- Một dashboard chạy mỗi giây trên index refresh mỗi giây có thể không tận dụng request cache tốt.
- Tăng `refresh_interval` có thể tăng khoảng thời gian cache entry tồn tại, nhưng làm search visibility trễ hơn.

Đây là trade-off giữa freshness và cache reuse. Không kéo dài refresh interval chỉ để tăng cache hit nếu nghiệp vụ cần dữ liệu gần realtime.

### Cache không thay đổi consistency model

Request cache không làm Elasticsearch trở thành strongly consistent giữa mọi writer và reader. Nó chỉ tái sử dụng kết quả của một trạng thái shard đã refresh. Sau lần refresh tiếp theo, cache cũ bị vô hiệu hóa và search request mới có thể tính lại trên trạng thái mới.

## 13. Cấu hình request cache ở cấp index

Index có setting `index.requests.cache.enable` để bật hoặc tắt request cache cho index:

```http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "requests": {
      "cache": {
        "enable": true
      }
    }
  }
}
```

Setting này điều khiển khả năng dùng request cache ở cấp index. Có thể kiểm tra setting hiện tại bằng:

```http
GET /products/_settings?include_defaults=true
```

Không nhầm setting này với tham số `request_cache` trên từng search request. Một request có thể yêu cầu cache, nhưng setting index vẫn có thể vô hiệu hóa khả năng cache.

## 14. Theo dõi request cache

Có thể xem thống kê:

```http
GET /_nodes/stats/indices/request_cache
```

Hoặc theo index:

```http
GET /products/_stats/request_cache
```

Các trường thường quan tâm:

| Chỉ số | Ý nghĩa |
|---|---|
| `memory_size_in_bytes` | Bộ nhớ request cache đang dùng |
| `hit_count` | Số lần request cache hit |
| `miss_count` | Số lần request cache miss |
| `evictions` | Số entry bị loại do áp lực cache/dung lượng |

Tính hit ratio tương tự query cache:

\[
\text{Hit ratio} = \frac{\text{hit count}}{\text{hit count} + \text{miss count}}
\]

Đọc số liệu theo node và index, đồng thời quan sát refresh count, search latency, aggregation latency và indexing throughput. Cache hit ratio thấp có thể do request không lặp lại, shard copy phân tán, refresh liên tục hoặc cache bị eviction.

## 15. Application cache là gì?

Application cache nằm ngoài Elasticsearch và lưu kết quả ở tầng ứng dụng. Nó có thể lưu:

- Một DTO sản phẩm đã được làm giàu dữ liệu.
- Trang search result đã map sang response API.
- Dashboard tổng hợp.
- Danh sách category hoặc brand ít thay đổi.
- Cấu hình hoặc dữ liệu tham chiếu.
- Kết quả nghiệp vụ được tính từ nhiều nguồn.

Các lựa chọn phổ biến:

| Công nghệ | Phạm vi | Đặc điểm |
|---|---|---|
| Caffeine | Trong một JVM | Nhanh, độ trễ thấp, mỗi instance có cache riêng |
| Redis | Dùng chung giữa nhiều instance | Phù hợp cache phân tán, TTL và eviction tập trung |
| Hazelcast hoặc cache grid | Nhiều node | Có thể hỗ trợ distributed cache theo kiến trúc |
| Spring Cache abstraction | API thống nhất | Cho phép dùng annotation/CacheManager với provider phù hợp |

Application cache có thể cache kết quả sau khi Spring Data đã chuyển `SearchHits` thành DTO. Nó giúp tránh cả network round trip tới Elasticsearch khi cache hit.

## 16. Cache key của ứng dụng

Cache key phải bao gồm mọi yếu tố có thể làm thay đổi kết quả. Ví dụ với product search:

```text
product-search:
  tenantId:
  normalizedText:
  categoryId:
  status:
  sort:
  page:
  size:
  locale:
  projectionVersion
```

Nếu bỏ `tenantId`, kết quả của tenant A có thể bị trả cho tenant B. Nếu bỏ sort hoặc page, người dùng có thể nhận sai thứ tự hoặc sai trang. Nếu response phụ thuộc quyền truy cập hoặc role, cache key phải phản ánh authorization scope phù hợp.

### Những thành phần thường cần trong key

- Tenant hoặc organization ID.
- Search text đã normalize.
- Filter values.
- Sort order.
- Page/cursor và page size.
- Locale hoặc timezone nếu response đã định dạng theo vùng.
- User/role scope nếu dữ liệu hiển thị phụ thuộc quyền.
- Projection/index version khi schema response thay đổi.
- Các tham số ảnh hưởng kết quả aggregation.

Không đưa access token hoặc secret thô vào cache key. Dùng định danh ổn định, hash hoặc scope ID theo chính sách bảo mật.

## 17. Ví dụ Spring Cache với kết quả search page

Spring Cache abstraction cho phép đánh dấu method cần cache. Ví dụ cache một response DTO có page size giới hạn:

```java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    @Cacheable(
        cacheNames = "product-search",
        key = "#tenantId + ':' + #text + ':' + #categoryId + ':' + #page + ':' + #size"
    )
    public ProductSearchPage search(
            String tenantId,
            String text,
            String categoryId,
            int page,
            int size) {

        // Build a validated NativeQuery and execute Elasticsearch search.
        // Map hits to an immutable ProductSearchPage DTO.
        return executeSearch(tenantId, text, categoryId, page, size);
    }
}
```

Đây là ví dụ minh họa Spring Cache; ứng dụng cần bật caching bằng `@EnableCaching` và cấu hình `CacheManager` tương ứng. Method phải trả một kiểu kết quả có thể serialize/cache phù hợp với provider. Không cache một page không giới hạn hoặc một object chứa resource mở.

### Cẩn thận với proxy của Spring Cache

Trong chế độ proxy mặc định, lời gọi nội bộ từ một method sang method `@Cacheable` khác trong cùng bean có thể không đi qua proxy và không kích hoạt cache. Đặt method cache ở bean riêng hoặc gọi qua proxy được quản lý thay vì tự gọi `this.search(...)` rồi kỳ vọng cache luôn hoạt động.

### Reactive return types

Với `Mono`/`Flux`, hành vi cache phụ thuộc phiên bản Spring Framework, Spring Cache abstraction và provider. Không giả định annotation `@Cacheable` trên `Flux` sẽ cache một stream vô hạn theo cách mong muốn. Với kết quả reactive, có thể cache một DTO bounded sau khi hoàn tất hoặc dùng cache abstraction hỗ trợ reactive một cách tường minh; tránh `collectList()` trên nguồn không giới hạn chỉ để cache.

## 18. Cache-aside, write-through và write-behind

Application cache thường dùng một trong các chiến lược:

### Cache-aside

1. Ứng dụng kiểm tra cache.
2. Nếu hit, trả kết quả.
3. Nếu miss, đọc Elasticsearch/nguồn dữ liệu.
4. Ghi kết quả vào cache với TTL.

Đây là cách đơn giản và phổ biến. Ứng dụng chịu trách nhiệm invalidation hoặc chấp nhận TTL.

### Write-through

Khi dữ liệu được cập nhật, ứng dụng cập nhật nguồn và cache theo một luồng được quản lý. Cache luôn được làm mới cùng đường ghi nếu thao tác thành công.

### Write-behind

Ứng dụng ghi vào cache trước rồi cập nhật nguồn sau. Cách này có thể giảm latency nhưng phức tạp hơn nhiều về durability, retry và mất dữ liệu. Không dùng write-behind để biến Elasticsearch thành nguồn chuẩn nếu nghiệp vụ yêu cầu database là nguồn có thẩm quyền.

Với search projection, cache-aside kèm TTL hoặc event-based eviction thường dễ triển khai hơn. Nếu có event thay đổi nguồn chuẩn, có thể evict cache liên quan sau khi projection được cập nhật.

## 19. TTL và invalidation của application cache

TTL (time to live) quy định một entry tồn tại tối đa bao lâu. TTL ngắn giảm thời gian dữ liệu cũ nhưng tăng cache miss và tải Elasticsearch. TTL dài tăng hit ratio nhưng có thể trả dữ liệu stale lâu hơn.

Ví dụ chính sách ban đầu:

| Dữ liệu | TTL tham khảo | Lý do |
|---|---:|---|
| Danh sách category/brand ít đổi | Vài phút đến hàng giờ | Thay đổi ít, có thể evict theo event |
| Trang tìm kiếm sản phẩm | Vài giây đến vài chục giây | Giá/trạng thái có thể thay đổi |
| Dashboard tổng hợp | Vài chục giây đến vài phút | Thường chấp nhận độ trễ nhỏ |
| Kết quả phụ thuộc quyền truy cập | TTL ngắn hoặc không cache | Cần kiểm soát thay đổi quyền và scope |
| Dữ liệu giao dịch cần mới nhất | Không cache hoặc xác thực lại nguồn chuẩn | Không chấp nhận kết quả stale |

Các khoảng thời gian chỉ là điểm khởi đầu. TTL thực tế phải dựa trên freshness SLA, tần suất cập nhật và chi phí cache miss.

### Explicit eviction

Sau khi cập nhật sản phẩm, ứng dụng có thể evict cache chi tiết sản phẩm và các trang search bị ảnh hưởng:

```java
@CacheEvict(cacheNames = "product-by-id", key = "#productId")
public void updateProduct(String productId, UpdateProductRequest request) {
    // Update the source of truth and trigger projection update.
}
```

Evict một product-by-id key đơn giản hơn evict mọi tổ hợp search query có thể chứa product đó. Với search cache, thường kết hợp TTL ngắn, versioned keys hoặc namespace invalidation thay vì cố liệt kê mọi query bị ảnh hưởng.

### Evict sau khi cập nhật thành công

Không evict hoặc cache dữ liệu mới trước khi transaction nguồn chuẩn commit thành công. Với projection bất đồng bộ, cần quyết định evict tại thời điểm nguồn commit hay sau khi projection được cập nhật. Nếu evict quá sớm, cache miss có thể đọc projection cũ rồi cache lại; nếu evict quá muộn, cache có thể giữ kết quả cũ trong khoảng chờ.

## 20. Invalidation qua event và versioned key

Với hệ thống event-driven, có thể phát event `ProductUpdated` và evict cache liên quan. Nếu cache key có namespace/version, có thể tăng version để các key cũ tự hết hiệu lực:

```text
product-search:v7:tenant-42:wireless:page-0
product-search:v8:tenant-42:wireless:page-0
```

Sau khi projection version thay đổi, ứng dụng chuyển sang namespace `v8`. Key `v7` có thể được dọn theo TTL thay vì phải xóa từng entry.

Versioned key hữu ích khi có nhiều tổ hợp query. Tuy nhiên, cần có nguồn version nhất quán và tránh để mỗi instance dùng version khác nhau ngoài ý muốn.

## 21. Cache stampede và đồng bộ cache miss

Cache stampede xảy ra khi một key phổ biến hết TTL hoặc bị evict, nhiều request đồng thời cùng miss và cùng gọi Elasticsearch/nguồn dữ liệu. Điều này có thể tạo tải đột biến đúng lúc cache đang thiếu entry.

Các biện pháp:

- Single-flight/request coalescing: chỉ một request tải dữ liệu cho một key, request khác chờ kết quả.
- TTL jitter: thêm biến thiên nhỏ vào TTL để nhiều key không hết hạn cùng lúc.
- Stale-while-revalidate: trả giá trị cũ trong giới hạn cho phép trong khi làm mới nền.
- Pre-warm các dashboard/key nóng theo lịch nếu có căn cứ.
- Giới hạn concurrency cache miss tới Elasticsearch.
- Dùng negative caching có TTL ngắn cho kết quả không tồn tại nếu semantics cho phép.

Không áp dụng stale-while-revalidate cho dữ liệu mà người dùng phải thấy trạng thái giao dịch mới nhất. Negative cache cũng cần phân biệt “không tồn tại” với “không có quyền truy cập”.

## 22. So sánh invalidation giữa ba cache

| Cache | Sự kiện làm kết quả cũ | Cách invalidation/chuyển mới |
|---|---|---|
| Query cache | Segment thay đổi hoặc bị merge/loại bỏ | Entry theo segment không còn dùng; Elasticsearch quản lý eviction |
| Request cache | Shard refresh làm search-visible state thay đổi | Elasticsearch invalidates kết quả request liên quan |
| Application cache | Nguồn/projection thay đổi, quyền thay đổi hoặc TTL hết | TTL, explicit eviction, event invalidation, versioned key |

Query cache và request cache được Elasticsearch quản lý theo trạng thái index/shard. Application cache nằm ngoài vòng đời shard; ứng dụng phải định nghĩa freshness và invalidation.

## 23. Cache và refresh policy liên quan thế nào?

Refresh làm dữ liệu mới trở nên nhìn thấy qua search. Nó cũng ảnh hưởng request cache vì refresh invalidates cache entry của shard. Query cache lại gắn với segment nên segment mới/merge có thể làm thay đổi tập entry có thể tái sử dụng.

Ví dụ index có `refresh_interval = 1s` và dashboard chạy mỗi 5 giây:

```text
T0: Dashboard request -> request cache miss
T1: Index refresh -> request cache cũ invalidated
T5: Dashboard request -> có thể lại miss
T6: Index refresh -> invalidation tiếp
```

Nếu index gần như không có ghi và refresh interval dài hơn, request cache có thể được tái sử dụng qua nhiều lần gọi dashboard.

Không nên kéo dài refresh interval chỉ để giữ request cache nếu search freshness cần thấp. Hãy xem xét cache ở tầng ứng dụng với TTL phù hợp, hoặc tách dashboard aggregation sang index/read model có lịch cập nhật riêng.

## 24. Cache và dữ liệu thời gian động

Query dùng giá trị `now` có kết quả thay đổi theo thời gian ngay cả khi index không refresh:

```json
{
  "range": {
    "expiresAt": {
      "gte": "now-24h"
    }
  }
}
```

Hai request ở hai thời điểm có thể có tập document khác nhau. Request có thời gian động thường không phù hợp để tái sử dụng request cache như một query cố định. Application cache cũng có thể trả kết quả cũ quá TTL nếu key không phản ánh thời điểm hoặc bucket thời gian.

Nếu nghiệp vụ chấp nhận gom thời gian theo phút hoặc giờ, ứng dụng có thể tính một mốc cố định cho bucket và đưa mốc đó vào query/key. Ví dụ dashboard theo ngày có thể dùng `startOfDay` cố định theo timezone nghiệp vụ thay vì `now` ở từng request.

## 25. Cache và personalization

Search result có thể phụ thuộc vào người dùng:

- Quyền truy cập tài liệu.
- Giá hoặc catalog theo nhóm khách hàng.
- Locale/ngôn ngữ.
- Lịch sử hoặc sở thích cá nhân.
- Tenant hoặc organization.

Nếu application cache key không bao gồm scope liên quan, có thể trả kết quả của người dùng này cho người dùng khác. Đây vừa là lỗi correctness vừa có thể là rò rỉ dữ liệu.

Nguyên tắc:

- Authenticate/authorize trước khi dùng cache có dữ liệu nhạy cảm.
- Key phải chứa tenant và authorization scope phù hợp.
- Không cache response đã lọc quyền nếu không thể xác định scope ổn định.
- Evict khi role/permission thay đổi hoặc dùng version trong key.
- Không dựa vào việc client gửi `tenantId` để phân vùng cache.

Elasticsearch request/query cache không thay thế authorization. Ứng dụng vẫn phải áp dụng filter và quyền ở mọi request; credential của Elasticsearch nên có quyền tối thiểu cần thiết.

## 26. Cache nhiều tầng có thể làm dữ liệu stale kéo dài

Nếu cả request cache và application cache đều có TTL/invalidation riêng, thời gian dữ liệu cũ có thể cộng dồn theo cách khó dự đoán.

Ví dụ:

1. Elasticsearch refresh làm request cache invalidated.
2. Application cache vẫn còn entry cũ thêm 60 giây.
3. Client tiếp tục nhận kết quả cũ dù Elasticsearch đã có dữ liệu mới.

Vì vậy, freshness SLA phải được thiết kế đầu-cuối. Không thể chỉ xem TTL của từng cache riêng lẻ.

Một chính sách có thể là:

- Query/request cache do Elasticsearch tự quản lý.
- Application cache TTL 10 giây cho search page.
- Event invalidation cho product detail và category metadata.
- Không cache các endpoint quyết định giao dịch.

Giá trị cụ thể cần dựa trên tốc độ cập nhật và yêu cầu sản phẩm.

## 27. Spring Data Elasticsearch: cấu trúc query để tận dụng query cache

Spring Data Elasticsearch không cần một annotation riêng để bật query cache cho từng filter. Điều quan trọng là query được tạo với đúng semantics filter context.

Ví dụ `NativeQuery`:

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> b
        .must(m -> m.multiMatch(mm -> mm
            .query("wireless mouse")
            .fields("name^3", "description")
        ))
        .filter(f -> f.term(t -> t
            .field("tenantId")
            .value("tenant-42")
        ))
        .filter(f -> f.term(t -> t
            .field("status")
            .value("ACTIVE")
        ))
    ))
    .build();
```

Phần `must` phục vụ full-text scoring; các điều kiện tenant/status nằm trong filter context. Elasticsearch tự quyết định có cache filter hay không dựa trên workload và heuristic. Không nên tạo một query cache riêng trong Java cho từng term filter.

### Query cache không phải API `@Cacheable`

`@Cacheable` của Spring lưu kết quả method ở application layer. Nó không bật query cache Elasticsearch. Tương tự, đặt `request_cache=true` không điều khiển query cache.

## 28. Spring Data Elasticsearch: request cache cho search

Khi cần cache aggregation/search request ở Elasticsearch, có thể truyền request cache option qua Search API. Ví dụ REST:

```http
POST /products/_search?request_cache=true
Content-Type: application/json

{
  "size": 0,
  "query": {
    "term": {
      "tenantId": "tenant-42"
    }
  },
  "aggs": {
    "by_status": {
      "terms": {
        "field": "status"
      }
    }
  }
}
```

Với Elasticsearch Java API Client, Search Request có tùy chọn `requestCache` ở những phiên bản client tương ứng. Spring Data Elasticsearch có thể cung cấp cách cấu hình qua Query/operation hoặc cho phép dùng client trực tiếp; tên API và overload thay đổi theo version. Hãy kiểm tra Javadoc dependency đang dùng thay vì giả định một builder method có mặt ở mọi phiên bản.

Nếu gọi qua `ElasticsearchOperations.search(...)`, hãy xác nhận query/transport thực tế có gửi request cache option trước khi dựa vào cache trong production. Với aggregation-only query, `size: 0` thường là bước đầu tiên quan trọng.

## 29. Spring Cache với Caffeine hoặc Redis

Ứng dụng có thể bật Spring Cache:

```java
@Configuration
@EnableCaching
public class CacheConfiguration {
}
```

Sau đó cấu hình `CacheManager` với provider. Ví dụ khái niệm Caffeine:

```java
@Bean
CacheManager cacheManager() {
    CaffeineCacheManager manager = new CaffeineCacheManager("product-search");
    manager.setCaffeine(Caffeine.newBuilder()
        .maximumSize(10_000)
        .expireAfterWrite(Duration.ofSeconds(20))
        .recordStats());
    return manager;
}
```

Đây là ví dụ cho cache cục bộ trong một JVM. Mỗi application instance có cache riêng; sau khi một instance cập nhật dữ liệu, instance khác có thể giữ entry cũ đến khi TTL hết hoặc nhận invalidation riêng.

Redis phù hợp khi nhiều instance cần chia sẻ cache. Tuy nhiên, Redis yêu cầu thiết kế key namespace, TTL, serialization, eviction và bảo vệ network/credentials. Shared cache không tự giải quyết consistency; vẫn cần invalidation.

## 30. Cache result DTO, không cache object tùy tiện

Nên cache DTO bất biến đã được thiết kế cho API:

```java
public record ProductSearchItem(
    String id,
    String name,
    double price,
    String categoryName) {
}

public record ProductSearchPage(
    List<ProductSearchItem> items,
    long total,
    int page,
    int size) {
}
```

DTO giúp cache serialization ổn định và tránh lưu các object có resource, lazy state hoặc internal metadata không cần thiết.

Không cache toàn bộ `SearchHits`, client response object hoặc entity mutable nếu không hiểu lifecycle và serialization. Khi schema API thay đổi, version key hoặc cache name để tránh đọc entry cũ có cấu trúc không tương thích.

## 31. Đo hiệu năng từng lớp cache

Để biết cache nào đang giúp ích, đo riêng từng lớp:

| Lớp | Metrics cần theo dõi |
|---|---|
| Query cache | hit/miss, memory size, cache size, evictions theo node/index |
| Request cache | hit/miss, memory size, evictions, refresh frequency |
| Application cache | hit/miss, eviction, load latency, TTL expiry, entry count, memory |
| Search service | p50/p95/p99 latency, Elasticsearch calls, result size, timeout |
| Cluster | CPU, heap, GC, search thread pool, indexing pressure, disk I/O |

### Benchmark có kiểm soát

Một quy trình đo đơn giản:

1. Chạy query khi cache lạnh và ghi latency.
2. Lặp lại cùng query nhiều lần để quan sát cache warm-up.
3. Thay một filter để kiểm tra cache reuse.
4. Ghi một document và quan sát tác động refresh/invalidation.
5. Chạy cùng request với `request_cache=true` và `false`.
6. Đo app cache hit và miss riêng.
7. So sánh p95/p99, CPU, heap và throughput ghi.

Chạy benchmark trên dữ liệu, shard count, replica và workload gần production. Tránh kết luận từ một lần chạy hoặc một cache hit đơn lẻ.

## 32. Khi nào không nên cache?

Không phải dữ liệu nào cũng phù hợp để cache:

- Kết quả có tính cá nhân hóa mạnh và key khó mô hình hóa an toàn.
- Dữ liệu cần trạng thái mới nhất cho quyết định giao dịch.
- Query có biến động cao và hầu như không lặp lại.
- Request chứa dữ liệu nhạy cảm nhưng không thể phân vùng cache đúng.
- Kết quả lớn hơn chi phí tính lại hoặc gây áp lực memory đáng kể.
- Endpoint chỉ được gọi rất ít và Elasticsearch đã xử lý đủ nhanh.

Cache thêm một tầng state cần vận hành. Nếu không có hit ratio đủ tốt hoặc latency improvement đáng kể, không cần thêm cache chỉ vì có thể.

## 33. Các lỗi thường gặp

### Nghĩ query cache lưu toàn bộ response

Query cache lưu kết quả filter theo segment; request cache mới lưu kết quả search request ở cấp shard. Application cache lưu DTO/response ở tầng ứng dụng.

### Đưa full-text query vào filter để cố cache

Làm thay đổi scoring và relevance. Chỉ đưa điều kiện không cần score vào filter context.

### Nghĩ mọi filter chắc chắn được cache

Elasticsearch dùng heuristic và ngân sách cache. Filter không lặp lại hoặc segment không phù hợp có thể không được cache.

### Nghĩ request cache luôn cache mọi hits

Mặc định request cache tập trung vào search có `size: 0`. Request có hits cần tùy chọn rõ ràng và vẫn phải đáp ứng điều kiện cache.

### Quên request cache invalidation khi refresh

Index ghi liên tục có thể làm request cache mất hiệu quả. Đọc refresh stats cùng cache hit ratio.

### Bật `request_cache=true` cho mọi query

Request gần như duy nhất có thể chỉ tạo cache churn. Chỉ bật cho workload lặp lại có lợi ích đo được.

### Application cache key thiếu tenant hoặc role

Có thể trả dữ liệu của tenant/user khác. Xây key theo toàn bộ scope ảnh hưởng kết quả và luôn authorize trước khi dùng cache.

### TTL dài nhưng không có invalidation

Dữ liệu stale có thể tồn tại lâu hơn SLA. Đặt TTL theo freshness và evict theo event khi phù hợp.

### Chỉ đo hit ratio

Hit ratio cao không đảm bảo latency tốt hoặc memory hiệu quả. Đo p95/p99, CPU, heap, refresh và eviction.

### Cache nhiều tầng nhưng không xác định freshness đầu-cuối

Application cache có thể giữ kết quả cũ sau khi Elasticsearch request cache đã invalidated. Xác định SLA tổng thể và invalidation chain.

## 34. Quy trình chọn cache cho một use case

Khi tối ưu một endpoint Spring Data Elasticsearch, hãy đi theo trình tự:

1. Đo latency hiện tại và xác định phần tốn thời gian: query, aggregation, fetch, network hay mapping DTO.
2. Kiểm tra query có filter context phù hợp để tận dụng query cache không.
3. Nếu là aggregation-only, đặt `size: 0` và đánh giá request cache.
4. Kiểm tra tần suất refresh; request cache có bị invalidation trước lần dùng tiếp theo không?
5. Nếu nhiều request ứng dụng lặp lại cùng response, cân nhắc application cache.
6. Thiết kế key có tenant, authorization scope, filter, sort, page, locale và projection version.
7. Đặt TTL theo freshness SLA và cơ chế event/explicit invalidation.
8. Xử lý cache stampede và giới hạn concurrency khi cache miss.
9. Đo hit/miss, evictions, memory và latency riêng từng lớp.
10. Loại bỏ cache không đem lại lợi ích đo được hoặc tạo độ phức tạp không cần thiết.

## 35. Kết luận

Query cache, request cache và application cache giải quyết ba bài toán khác nhau. Query cache tái sử dụng kết quả filter trong filter context theo segment; request cache tái sử dụng kết quả search ở cấp shard, mặc định hữu ích nhất cho request `size: 0` như aggregation; application cache lưu DTO hoặc kết quả nghiệp vụ ở phía ứng dụng để tránh gọi Elasticsearch.

Query cache và request cache được Elasticsearch quản lý, trong đó refresh và segment lifecycle ảnh hưởng trực tiếp tới khả năng tái sử dụng. Application cache cần cache key, TTL và invalidation do ứng dụng thiết kế; key phải phản ánh tenant, quyền, filter và mọi yếu tố ảnh hưởng response. Trong Spring Data Elasticsearch, dùng `bool.filter` cho điều kiện không cần score, `size: 0` cho aggregation-only request, cấu hình request cache có chọn lọc và cache DTO bounded ở tầng service khi workload lặp lại. Luôn đo hit ratio cùng latency, memory, eviction và freshness; không bật cache chỉ dựa trên giả định rằng cache nhiều hơn sẽ nhanh hơn.

## Tài liệu tham khảo

- [Elasticsearch – Node query cache](https://www.elastic.co/docs/reference/elasticsearch/configuration-reference/node-query-cache-settings)
- [Elasticsearch – Shard request cache](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/shard-request-cache)
- [Elasticsearch – Query and filter context](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-filter-context)
- [Elasticsearch – Search API (`request_cache`)](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-search)
- [Elasticsearch – Index settings](https://www.elastic.co/docs/reference/elasticsearch/index-settings/index-modules)
- [Spring Framework – Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Data Elasticsearch – NativeQuery and operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Caffeine – User guide](https://github.com/ben-manes/caffeine/wiki)
