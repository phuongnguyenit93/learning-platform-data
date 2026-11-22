# Tái sử dụng bộ dựng truy vấn theo điều kiện nghiệp vụ

Trong một ứng dụng Spring Data Elasticsearch, nhiều màn hình hoặc API thường cần cùng một nhóm điều kiện tìm kiếm: chỉ lấy dữ liệu thuộc tenant hiện tại, chỉ lấy sản phẩm đang hoạt động, giới hạn theo danh mục, khoảng giá hoặc khoảng thời gian. Nếu mỗi service tự dựng lại Query DSL, các điều kiện dễ bị lặp, khác nhau giữa các endpoint và khó thay đổi đồng bộ.

`NativeQuery` cho phép xây dựng truy vấn bằng Elasticsearch Java API Client rồi thực thi thông qua Spring Data Elasticsearch. Có thể tách các điều kiện nghiệp vụ thành những phần nhỏ có thể tái sử dụng, kết hợp chúng thành một `bool` query và dùng chung bộ dựng đó ở nhiều use case.

Điểm quan trọng là tái sử dụng **hàm tạo query fragment và quy tắc kết hợp điều kiện**, còn mỗi request vẫn tạo query mới từ các tham số hiện tại. Cách này giúp giữ điều kiện nhất quán mà không chia sẻ trạng thái builder giữa các request.

## 1. Từ điều kiện nghiệp vụ đến Query DSL

Giả sử một hệ thống catalog có các yêu cầu tìm kiếm:

- Tìm sản phẩm theo từ khóa trong tên hoặc mô tả.
- Chỉ lấy sản phẩm thuộc tenant của người đang đăng nhập.
- Có thể giới hạn theo danh mục và trạng thái.
- Có thể giới hạn theo khoảng giá hoặc thời gian tạo.
- Cho phép sắp xếp và phân trang.

Đây là các điều kiện nghiệp vụ. Chúng không nên phụ thuộc trực tiếp vào cách Elasticsearch biểu diễn `term`, `range`, `match` hay `bool` trong mọi service.

Có thể chia trách nhiệm thành ba lớp:

1. **Search criteria**: dữ liệu đầu vào mô tả người dùng muốn tìm gì, chẳng hạn từ khóa, danh mục, trạng thái và khoảng giá.
2. **Query factory / query parts**: chuyển các tiêu chí thành những query fragment có thể tái sử dụng.
3. **Search service hoặc repository fragment**: gọi factory, bổ sung phân trang/sắp xếp và thực thi query qua `ElasticsearchOperations`.

~~~mermaid
flowchart TD
    A["API / use case"] --> B["ProductSearchCriteria"]
    B --> C["ProductQueryFactory"]
    D["Tenant từ security context"] --> C
    E["Query fragments dùng chung"] --> C
    C --> F["NativeQuery / bool query"]
    F --> G["ElasticsearchOperations"]
    G --> H["SearchHits<ProductDocument>"]
~~~

Việc tách lớp giúp service không phải biết chi tiết từng JSON clause và giúp một nhóm điều kiện được sử dụng lại ở nhiều nơi.

## 2. `NativeQuery` và Elasticsearch Java API Client

`NativeQuery` là kiểu query của Spring Data Elasticsearch dùng để mang các query object được xây dựng bằng Elasticsearch Java API Client. Nó phù hợp khi cần kiểm soát rõ cấu trúc Query DSL như `bool`, `must`, `filter`, `should`, nested query, script hoặc các tính năng nâng cao khác.

Ví dụ tạo một query đơn giản:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Query activeFilter = Query.of(q -> q.term(t -> t
        .field("status")
        .value(FieldValue.of("ACTIVE"))));

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b.filter(activeFilter)))
        .build();
~~~

Ở đây có hai kiểu `Query` cần phân biệt:

- `co.elastic.clients.elasticsearch._types.query_dsl.Query` là query object của Elasticsearch Java API Client, đại diện cho một clause trong Query DSL.
- `org.springframework.data.elasticsearch.client.elc.NativeQuery` là query abstraction của Spring Data Elasticsearch, dùng để đóng gói query client cùng các tùy chọn như sort, pageable, aggregation và source filter.

`NativeQuery` không có nghĩa là SQL native query. Nó là cách sử dụng trực tiếp cấu trúc Elasticsearch Query DSL thông qua Java client.

## 3. Tạo các query fragment có thể tái sử dụng

Một query fragment là một điều kiện nhỏ có thể được tạo độc lập, ví dụ filter theo tenant, category hoặc trạng thái. Nên viết mỗi fragment thành một method có tên thể hiện đúng mục đích nghiệp vụ.

Ví dụ các fragment dùng chung:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

public final class ProductQueryParts {

    private ProductQueryParts() {
    }

    public static Query tenantFilter(String tenantId) {
        return Query.of(q -> q.term(t -> t
                .field("tenantId")
                .value(FieldValue.of(tenantId))));
    }

    public static Query activeFilter() {
        return Query.of(q -> q.term(t -> t
                .field("status")
                .value(FieldValue.of("ACTIVE"))));
    }

    public static Query categoryFilter(String category) {
        return Query.of(q -> q.term(t -> t
                .field("category")
                .value(FieldValue.of(category))));
    }

    public static Query nameMatch(String text) {
        return Query.of(q -> q.match(m -> m
                .field("name")
                .query(text)));
    }
}
~~~

Các method trên tạo query object mới từ tham số đầu vào. Chúng không giữ một builder mutable trong biến static. Nhờ vậy, nhiều request có thể gọi cùng method với tenant, category hoặc từ khóa khác nhau mà không chia sẻ trạng thái.

Có thể đặt những fragment được dùng chung ở module/package query riêng, ví dụ `search.query.ProductQueryParts`. Nếu fragment chỉ phục vụ một aggregate hoặc một use case, đặt gần query factory tương ứng để tránh tạo một thư viện tiện ích quá rộng.

## 4. Biểu diễn tiêu chí tìm kiếm bằng một object nghiệp vụ

Không nên truyền hàng loạt tham số rời rạc qua nhiều tầng service. Tạo một object thể hiện tiêu chí tìm kiếm giúp việc validate, mở rộng và tái sử dụng rõ ràng hơn.

Ví dụ dùng Java record:

~~~java
import java.time.Instant;
import java.util.Set;

public record ProductSearchCriteria(
        String text,
        String category,
        Set<String> statuses,
        Long minPrice,
        Long maxPrice,
        Instant createdFrom,
        Instant createdTo) {
}
~~~

Object này chỉ mô tả tiêu chí sản phẩm. `tenantId` được truyền riêng từ security context hoặc service xác thực, bởi vì phạm vi tenant là điều kiện truy cập bắt buộc chứ không phải bộ lọc tùy chọn mà client được tự chọn.

Nếu dự án chưa dùng Java record, có thể thay bằng class immutable có constructor, getter và validation tương ứng.

## 5. Xây dựng query factory từ các fragment

Query factory nhận tiêu chí nghiệp vụ, tạo danh sách query clause và kết hợp chúng bằng `bool`. Một quy ước thường hữu ích là:

- Điều kiện tìm kiếm nội dung như `match` được đưa vào `must` để tham gia relevance score.
- Điều kiện bắt buộc nhưng không cần tính điểm như tenant, trạng thái, category và range được đưa vào `filter`.
- Điều kiện lựa chọn hoặc mở rộng kết quả có thể được đưa vào `should` với `minimum_should_match` được xác định rõ.

Ví dụ factory:

~~~java
import java.util.ArrayList;
import java.util.List;

import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

public class ProductQueryFactory {

    public Query buildQuery(ProductSearchCriteria criteria, String tenantId) {
        List<Query> must = new ArrayList<>();
        List<Query> filters = new ArrayList<>();

        // Phạm vi tenant luôn được áp dụng.
        filters.add(ProductQueryParts.tenantFilter(tenantId));

        if (criteria.text() != null && !criteria.text().isBlank()) {
            must.add(ProductQueryParts.nameMatch(criteria.text().trim()));
        }

        if (criteria.category() != null && !criteria.category().isBlank()) {
            filters.add(ProductQueryParts.categoryFilter(criteria.category()));
        }

        if (criteria.statuses() != null && !criteria.statuses().isEmpty()) {
            filters.add(statusesFilter(criteria.statuses()));
        }

        if (criteria.minPrice() != null || criteria.maxPrice() != null) {
            filters.add(priceRangeFilter(
                    criteria.minPrice(), criteria.maxPrice()));
        }

        if (criteria.createdFrom() != null || criteria.createdTo() != null) {
            filters.add(createdAtRangeFilter(
                    criteria.createdFrom(), criteria.createdTo()));
        }

        return Query.of(q -> q.bool(b -> {
            if (!must.isEmpty()) {
                b.must(must);
            }
            if (!filters.isEmpty()) {
                b.filter(filters);
            }
            return b;
        }));
    }

    private Query statusesFilter(java.util.Set<String> statuses) {
        List<FieldValue> values = statuses.stream()
                .map(FieldValue::of)
                .toList();

        return Query.of(q -> q.terms(t -> t
                .field("status")
                .terms(v -> v.value(values))));
    }

    private Query priceRangeFilter(Long min, Long max) {
        return Query.of(q -> q.range(r -> r.number(n -> {
            n.field("priceInCents");
            if (min != null) {
                n.gte(min.doubleValue());
            }
            if (max != null) {
                n.lte(max.doubleValue());
            }
            return n;
        })));
    }

    private Query createdAtRangeFilter(
            java.time.Instant from, java.time.Instant to) {
        return Query.of(q -> q.range(r -> r.date(d -> {
            d.field("createdAt");
            if (from != null) {
                d.gte(from.toString());
            }
            if (to != null) {
                d.lt(to.toString());
            }
            return d;
        })));
    }
}
~~~

Factory trên có thể được dùng bởi nhiều service hoặc repository fragment. Mỗi lần gọi `buildQuery` sẽ tạo danh sách clause riêng, sau đó trả về một query object hoàn chỉnh.

### 5.1. Vì sao tenant filter phải luôn có mặt?

Trong ví dụ, tenant filter được thêm trước các điều kiện tùy chọn. Người gọi không thể bỏ qua filter này bằng cách gửi category rỗng hoặc không truyền status.

`tenantId` phải lấy từ danh tính đã được xác thực ở server, ví dụ từ security principal hoặc một service xác định tenant hiện hành. Không lấy tenant ID trực tiếp từ query parameter rồi tin rằng client chỉ yêu cầu dữ liệu của chính họ.

Đây là một quy tắc bảo vệ dữ liệu. Nếu mỗi endpoint tự thêm tenant filter theo cách khác nhau, một endpoint quên điều kiện có thể trả về document của tenant khác. Đặt quy tắc trong factory dùng chung giúp giảm nguy cơ sai lệch, nhưng service vẫn cần bảo đảm chỉ truyền tenant đã được xác thực.

### 5.2. Xử lý điều kiện trống

Không phải điều kiện nào cũng cần xuất hiện trong query:

- Từ khóa null hoặc blank: bỏ qua `match` clause.
- Category null hoặc blank: không thêm category filter.
- Set trạng thái null hoặc rỗng: không thêm terms filter.
- Chỉ có min hoặc max: tạo range với một biên.
- Không có điều kiện tìm kiếm nào ngoài tenant: vẫn giới hạn theo tenant; có thể dùng `match_all` kết hợp filter hoặc bool chỉ chứa filter.

Không tạo `terms` query với danh sách rỗng. Tùy cách xây dựng và phiên bản client, danh sách rỗng có thể bị từ chối hoặc cho kết quả không như ý. Kiểm tra collection trước khi tạo clause.

## 6. Tạo NativeQuery kèm sort và pageable

Query factory có thể chỉ chịu trách nhiệm tạo phần Query DSL. Một lớp khác đóng gói nó thành `NativeQuery` cùng với phân trang và sort:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

public class ProductNativeQueryFactory {

    private final ProductQueryFactory queryFactory;

    public ProductNativeQueryFactory(ProductQueryFactory queryFactory) {
        this.queryFactory = queryFactory;
    }

    public NativeQuery build(
            ProductSearchCriteria criteria,
            String tenantId,
            Pageable pageable) {

        return NativeQuery.builder()
                .withQuery(queryFactory.buildQuery(criteria, tenantId))
                .withPageable(pageable)
                .build();
    }
}
~~~

`Pageable` có thể mang page number, page size và `Sort`. Nếu muốn sort mặc định, service có thể tạo `PageRequest` trước khi gọi factory:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("sku")));
~~~

Các field sort phải có mapping hỗ trợ sort, thường là `keyword`, số, ngày giờ hoặc kiểu scalar có doc values. Không sort trực tiếp trên `text` thông thường; dùng subfield `keyword` nếu cần sắp xếp chuỗi.

## 7. Thực thi query bằng ElasticsearchOperations

Service nhận tiêu chí nghiệp vụ, lấy tenant đã xác thực, tạo NativeQuery và thực thi:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;
    private final ProductNativeQueryFactory queryFactory;
    private final CurrentTenantProvider currentTenantProvider;

    public ProductSearchService(
            ElasticsearchOperations operations,
            ProductNativeQueryFactory queryFactory,
            CurrentTenantProvider currentTenantProvider) {
        this.operations = operations;
        this.queryFactory = queryFactory;
        this.currentTenantProvider = currentTenantProvider;
    }

    public SearchHits<ProductDocument> search(
            ProductSearchCriteria criteria, Pageable pageable) {

        String tenantId = currentTenantProvider.requireTenantId();
        NativeQuery query = queryFactory.build(criteria, tenantId, pageable);

        return operations.search(query, ProductDocument.class);
    }
}
~~~

`CurrentTenantProvider` là abstraction của ứng dụng để lấy tenant từ security context. Tên và cách triển khai phụ thuộc hệ thống xác thực đang dùng.

`SearchHits<T>` chứa các search hit và metadata từ Elasticsearch. Nếu API chỉ cần danh sách document, có thể chuyển `hits` thành content; nếu cần score hoặc total hits, giữ `SearchHits` để xử lý metadata.

## 8. Tái sử dụng query ở nhiều use case

Một bộ fragment có thể được dùng trong nhiều truy vấn nhưng kết hợp theo mục đích khác nhau.

Ví dụ:

| Use case | Query context (`must`) | Filter context (`filter`) |
| --- | --- | --- |
| Tìm kiếm catalog | `match` trên tên hoặc mô tả. | Tenant, trạng thái, category, giá. |
| Danh sách sản phẩm đang hoạt động | Có thể không cần query nội dung. | Tenant và trạng thái `ACTIVE`. |
| Tìm sản phẩm trong khoảng giá | Có thể là `match` từ khóa nếu người dùng nhập. | Tenant, category và price range. |
| Tìm sản phẩm mới tạo | Có thể không cần query nội dung. | Tenant và khoảng `createdAt`. |
| Tìm theo nhiều trạng thái | Có thể có `match` theo từ khóa. | Tenant và terms filter trạng thái. |

Ví dụ một use case chỉ lấy sản phẩm đang hoạt động:

~~~java
Query query = Query.of(q -> q.bool(b -> b
        .filter(ProductQueryParts.tenantFilter(tenantId))
        .filter(ProductQueryParts.activeFilter())));

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(query)
        .build();
~~~

Use case tìm kiếm theo category có thể dùng cùng fragment tenant và category:

~~~java
Query query = Query.of(q -> q.bool(b -> b
        .filter(ProductQueryParts.tenantFilter(tenantId))
        .filter(ProductQueryParts.categoryFilter("ACCESSORIES"))));
~~~

Các fragment là phần nhỏ có thể kết hợp theo ngữ cảnh. Không cần tạo một factory khổng lồ chứa mọi điều kiện của toàn bộ domain nếu chúng thuộc các aggregate hoặc mapping khác nhau.

## 9. Tái sử dụng theo repository fragment

Khi truy vấn nghiệp vụ phức tạp, có thể đặt custom search method vào repository fragment để caller không phải tự biết `NativeQuery` hoặc `ElasticsearchOperations`.

Interface fragment:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.core.SearchHits;

public interface ProductSearchOperations {

    SearchHits<ProductDocument> search(
            ProductSearchCriteria criteria, Pageable pageable);
}
~~~

Repository chính kết hợp CRUD repository và fragment:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String>,
                ProductSearchOperations {
}
~~~

Implementation fragment:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

public class ProductSearchOperationsImpl implements ProductSearchOperations {

    private final ElasticsearchOperations operations;
    private final ProductNativeQueryFactory queryFactory;
    private final CurrentTenantProvider currentTenantProvider;

    public ProductSearchOperationsImpl(
            ElasticsearchOperations operations,
            ProductNativeQueryFactory queryFactory,
            CurrentTenantProvider currentTenantProvider) {
        this.operations = operations;
        this.queryFactory = queryFactory;
        this.currentTenantProvider = currentTenantProvider;
    }

    @Override
    public SearchHits<ProductDocument> search(
            ProductSearchCriteria criteria, Pageable pageable) {

        String tenantId = currentTenantProvider.requireTenantId();
        NativeQuery query = queryFactory.build(criteria, tenantId, pageable);
        return operations.search(query, ProductDocument.class);
    }
}
~~~

Spring Data repository fragment composition cho phép ghép implementation tùy chỉnh vào repository. Tên implementation cần tuân theo quy ước fragment của phiên bản Spring Data đang dùng hoặc được đăng ký rõ trong cấu hình repository.

Với cách này, controller hoặc service gọi `productRepository.search(criteria, pageable)`; phần dựng query được đóng gói ở fragment và query factory.

## 10. Tách query condition khỏi sort, paging và projection

Bộ dựng điều kiện nên tập trung vào điều kiện lọc và tìm kiếm. Sort, paging, source filtering và aggregation là các khía cạnh khác của request.

Có thể tổ chức thành các phần riêng:

- `ProductQueryFactory`: dựng `bool`, `must`, `filter`, `should`.
- `ProductSortPolicy`: ánh xạ lựa chọn sort hợp lệ từ API sang `Sort`.
- `Pageable` từ tầng API/service: xác định cửa sổ kết quả.
- Projection/source filter: xác định field cần trả về.
- Aggregation builder: tạo thống kê khi use case cần facets hoặc dashboard.

Việc tách này giúp cùng một tập điều kiện được dùng cho trang danh sách, export, autocomplete hoặc dashboard mà mỗi use case vẫn có sort, page size và aggregation riêng.

Nếu dùng `Pageable`, hãy giới hạn page size và whitelist field sort. Không nhận trực tiếp field name tùy ý từ client rồi truyền vào `Sort.by`.

## 11. Quy tắc AND, OR và nhóm điều kiện tùy chọn

Query factory cần thể hiện rõ logic nghiệp vụ. Ví dụ, người dùng muốn sản phẩm thuộc một trong hai category nhưng vẫn phải là ACTIVE:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "status": "ACTIVE" } },
        {
          "bool": {
            "should": [
              { "term": { "category": "ACCESSORIES" } },
              { "term": { "category": "OFFICE" } }
            ],
            "minimum_should_match": 1
          }
        }
      ]
    }
  }
}
~~~

Các điều kiện status và nhóm category đều là filter. Trong nhóm category, `should` biểu diễn OR và `minimum_should_match: 1` bảo đảm ít nhất một nhánh phải khớp.

Khi dùng Java API Client, có thể tạo nhóm OR thành một query fragment rồi đưa vào filter:

~~~java
private Query categoryAnyOf(java.util.Set<String> categories) {
    List<Query> choices = categories.stream()
            .map(category -> Query.of(q -> q.term(t -> t
                    .field("category")
                    .value(FieldValue.of(category)))))
            .toList();

    return Query.of(q -> q.bool(b -> b
            .should(choices)
            .minimumShouldMatch("1")));
}
~~~

Khi category set rỗng, caller cần quyết định ý nghĩa nghiệp vụ: bỏ qua điều kiện, không trả kết quả hay từ chối request. Không nên để một nhóm `should` rỗng tự quyết định hành vi thay cho ứng dụng.

## 12. Xác thực và kiểm tra tiêu chí trước khi dựng query

Query factory là nơi chuyển dữ liệu đầu vào thành DSL, nhưng validation nghiệp vụ nên được thực hiện trước hoặc ngay tại constructor của criteria object.

Các kiểm tra thường cần có:

- `minPrice` không lớn hơn `maxPrice`.
- `createdFrom` phải trước `createdTo`.
- Từ khóa có độ dài tối thiểu/tối đa hợp lý.
- Set trạng thái chỉ chứa giá trị nghiệp vụ được phép.
- Category phải thuộc tập category hợp lệ nếu domain có danh mục cố định.
- Tenant ID phải lấy từ server-side identity.
- Page size và sort field phải nằm trong giới hạn API.

Ví dụ validation trong service:

~~~java
private void validate(ProductSearchCriteria criteria) {
    if (criteria.minPrice() != null
            && criteria.maxPrice() != null
            && criteria.minPrice() > criteria.maxPrice()) {
        throw new IllegalArgumentException(
                "minPrice must not exceed maxPrice");
    }

    if (criteria.createdFrom() != null
            && criteria.createdTo() != null
            && !criteria.createdFrom().isBefore(criteria.createdTo())) {
        throw new IllegalArgumentException(
                "createdFrom must be earlier than createdTo");
    }
}
~~~

Đừng để factory âm thầm sửa dữ liệu đầu vào hoặc bỏ qua một điều kiện sai. Trả lỗi validation rõ ràng giúp caller hiểu vì sao request không hợp lệ.

## 13. Tổ chức reusable query parts theo phạm vi

Không phải mọi điều kiện đều nên đặt vào một class chung. Có thể chia theo phạm vi:

| Nhóm fragment | Ví dụ | Phạm vi tái sử dụng |
| --- | --- | --- |
| Điều kiện truy cập dùng chung | Tenant, quyền hiển thị, trạng thái soft-delete. | Nhiều use case trong cùng miền dữ liệu. |
| Điều kiện theo entity | Category, price, SKU, brand. | Các truy vấn Product. |
| Điều kiện tìm kiếm nội dung | Match name, description, synonym-aware query. | Các endpoint search sản phẩm. |
| Điều kiện theo use case | Chỉ lấy hàng sắp hết, hàng nổi bật. | Một vài luồng nghiệp vụ cụ thể. |

Có thể có một lớp `CommonQueryParts` cho điều kiện thực sự dùng chung, nhưng không nên tạo một bộ dựng generic biết tên field của mọi index. Field name, mapping và semantics thuộc domain document cụ thể.

## 14. Những cách làm nên tránh

| Cách làm | Vấn đề | Cách tổ chức tốt hơn |
| --- | --- | --- |
| Giữ một `BoolQuery.Builder` static rồi thêm clause theo từng request. | Builder mutable có thể giữ điều kiện cũ hoặc gây race giữa các request. | Tạo builder mới trong mỗi lần build; tái sử dụng method tạo fragment. |
| Chia sẻ một `NativeQuery` đã chứa criteria động giữa nhiều người dùng. | Query có thể mang tenant/filter/page/sort của request trước. | Tạo NativeQuery mới cho từng request. |
| Đưa tenant ID vào DTO do client tự gửi. | Client có thể thay tenant để truy cập dữ liệu ngoài phạm vi. | Lấy tenant từ security context và thêm filter bắt buộc ở server. |
| Tạo một method với hàng chục boolean flag. | Khó hiểu tổ hợp nào hợp lệ và khó kiểm thử. | Dùng criteria object có ý nghĩa và các fragment nhỏ. |
| Nối chuỗi JSON bằng string concatenation. | Dễ sai escape, kiểu dữ liệu và cấu trúc DSL. | Dùng Java API Client builders hoặc JSON DSL có kiểm soát. |
| Dùng query context cho mọi điều kiện chỉ vì tiện. | Các điều kiện không cần relevance có thể tham gia `_score`. | Dùng `bool.filter` cho điều kiện chỉ cần đúng/sai. |
| Tạo generic query factory cho mọi index. | Field và semantics giữa các domain không giống nhau. | Dùng factory theo document/domain và chia sẻ fragment thật sự chung. |
| Không kiểm tra danh sách rỗng hoặc range ngược. | Có thể tạo query vô nghĩa hoặc lỗi ở runtime. | Validate criteria trước khi build. |

## 15. Kiểm thử bộ dựng truy vấn

Bộ dựng query có thể kiểm tra theo hai cấp:

### 15.1. Unit test cho điều kiện nghiệp vụ

Kiểm tra factory với các trường hợp đầu vào khác nhau:

- Chỉ có tenant: query vẫn phải chứa tenant filter.
- Có text: query phải có match clause.
- Có category/status: các clause tương ứng phải xuất hiện trong filter.
- Có một biên giá: range chỉ có `gte` hoặc `lte` phù hợp.
- Set trạng thái rỗng: không tạo terms query rỗng.
- Khoảng giá hoặc thời gian không hợp lệ: validation từ chối.
- Không có tenant: request không được tạo query có thể truy cập toàn bộ dữ liệu.

### 15.2. Integration test với Elasticsearch

Unit test xác nhận factory tạo cấu trúc dự kiến; integration test xác nhận Elasticsearch hiểu mapping và query như mong muốn. Nên có dữ liệu thuộc ít nhất hai tenant để xác nhận tenant filter không trả dữ liệu chéo.

Kiểm tra thêm:

- Mapping `keyword` cho status/category và mapping số/ngày cho range.
- Kết quả match theo analyzer trên field `text`.
- Kết hợp AND/OR và `minimum_should_match`.
- Sort và phân trang theo field hỗ trợ sort.
- Kết quả khi criteria không có text.
- Aggregation nếu query factory được dùng trong dashboard/faceted search.

Có thể quan sát Query DSL được gửi bằng logging client ở môi trường phát triển hoặc dùng Profile API khi cần phân tích hiệu năng. Không bật log chứa request body hoặc dữ liệu nhạy cảm trên production nếu chưa có cơ chế lọc/redaction.

## 16. Ví dụ sử dụng hoàn chỉnh

Luồng thực hiện trong một endpoint có thể được mô tả như sau:

~~~java
public SearchHits<ProductDocument> searchProducts(
        ProductSearchCriteria criteria,
        Pageable pageable) {

    validate(criteria);

    String tenantId = currentTenantProvider.requireTenantId();
    NativeQuery query = nativeQueryFactory.build(
            criteria, tenantId, pageable);

    return elasticsearchOperations.search(query, ProductDocument.class);
}
~~~

Luồng dữ liệu:

~~~mermaid
sequenceDiagram
    participant API
    participant Service
    participant Tenant as TenantProvider
    participant Factory as QueryFactory
    participant ES as Elasticsearch
    API->>Service: criteria + pageable
    Service->>Service: validate(criteria)
    Service->>Tenant: requireTenantId()
    Tenant-->>Service: authenticated tenant
    Service->>Factory: build(criteria, tenant, pageable)
    Factory->>Factory: create reusable fragments
    Factory->>Factory: combine bool must/filter
    Factory-->>Service: NativeQuery
    Service->>ES: operations.search(query)
    ES-->>Service: SearchHits
    Service-->>API: search result
~~~

Với cách tổ chức này, điều kiện tenant và các filter sản phẩm được áp dụng nhất quán ở mọi nơi dùng factory. Mỗi use case vẫn có thể thêm query text, sort, pageable hoặc aggregation riêng mà không phải sao chép toàn bộ cấu trúc Query DSL.

## 17. Quy trình thiết kế bộ dựng truy vấn tái sử dụng

Khi bắt đầu xây dựng query factory cho một domain, hãy thực hiện theo trình tự:

1. Liệt kê các điều kiện nghiệp vụ và phân biệt điều kiện bắt buộc với điều kiện tùy chọn.
2. Xác định field mapping tương ứng: `text`, `keyword`, số, ngày giờ, geo hoặc nested.
3. Xác định điều kiện nào cần relevance score và điều kiện nào chỉ cần filter.
4. Tạo criteria object độc lập với Elasticsearch DSL.
5. Viết các method tạo query fragment nhỏ, có tham số và tên thể hiện nghiệp vụ.
6. Tạo factory mới cho mỗi request, kết hợp fragment bằng `bool.must`, `filter` hoặc `should`.
7. Thêm tenant/authorization filters từ server-side identity, không lấy quyền truy cập từ client input.
8. Đóng gói query bằng `NativeQuery` cùng pageable/sort phù hợp.
9. Thực thi qua `ElasticsearchOperations` hoặc repository fragment.
10. Kiểm thử các tổ hợp criteria, mapping, kết quả thực tế và ranh giới tenant.

`NativeQuery` giúp Spring Data Elasticsearch sử dụng trực tiếp các query object của Elasticsearch Java API Client. Tách query fragment và factory theo domain cho phép tái sử dụng điều kiện nghiệp vụ, giảm lặp Query DSL và giữ quy tắc truy cập nhất quán. Mỗi request vẫn cần tạo query mới từ criteria đã validate, áp dụng các filter bắt buộc từ server và kết hợp query context, filter context theo đúng ý nghĩa tìm kiếm.
