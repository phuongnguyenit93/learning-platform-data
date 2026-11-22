# Xây dựng truy vấn bằng builder và biểu thức lambda

Trong Spring Data Elasticsearch, NativeQuery cho phép xây dựng truy vấn bằng Elasticsearch Java API Client. Thay vì ghép JSON query bằng chuỗi, ứng dụng dùng các builder có kiểu dữ liệu và biểu thức lambda để mô tả từng thành phần của Query DSL.

Một lời gọi thường có dạng:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .match(m -> m
                .field("name")
                .query("keyboard")
            )
        )
        .build();

Ở đây, NativeQuery.builder() tạo builder của Spring Data. withQuery nhận một lambda để xây dựng đối tượng Query của Elasticsearch Java API Client. Lambda bên trong match cấu hình một MatchQuery, rồi build() hoàn tất đối tượng NativeQuery.

Builder và lambda giúp truy vấn có cấu trúc rõ ràng, hỗ trợ kiểm tra kiểu khi biên dịch và dễ kết hợp các clause như bool, must, filter, range, sort, pagination và aggregation.

## 1. NativeQuery nằm ở đâu trong Spring Data Elasticsearch?

Spring Data Elasticsearch cung cấp nhiều cách mô tả truy vấn. Repository method phù hợp với các thao tác đơn giản và có quy luật rõ ràng. CriteriaQuery cung cấp API dạng tiêu chí cho các điều kiện phổ biến. NativeQuery phù hợp khi cần kiểm soát trực tiếp Elasticsearch Query DSL.

NativeQuery thuộc package:

    import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Đây là implementation của abstraction Query trong Spring Data Elasticsearch, được tích hợp với Elasticsearch Java API Client. Nó cho phép truyền các đối tượng query được xây dựng từ client Java, cùng các tùy chọn như phân trang, sort, aggregation, highlight và các thành phần truy vấn khác được phiên bản Spring Data hỗ trợ.

Có thể phân biệt các cách tiếp cận:

| Cách xây dựng | Mục đích | Khi phù hợp |
|---|---|---|
| Repository derived query | Tạo truy vấn từ tên phương thức | Điều kiện đơn giản, dễ diễn đạt bằng tên |
| CriteriaQuery | Xây dựng truy vấn qua các tiêu chí | Điều kiện phổ biến, cần API Spring Data |
| NativeQuery | Xây dựng Elasticsearch Query DSL bằng Java API Client | Truy vấn phức tạp hoặc cần tính năng DSL cụ thể |
| JSON query thủ công | Truyền nội dung JSON ở các API phù hợp | Tích hợp đặc biệt hoặc cần giữ nguyên query JSON |

Ví dụ dưới đây sử dụng NativeQuery và Elasticsearch Java API Client theo các dòng Spring Data Elasticsearch hiện đại. Các phiên bản cũ có thể dùng NativeSearchQuery, QueryBuilders hoặc High Level REST Client. Không nên trộn ví dụ API của hai thế hệ client trong cùng một dự án.

## 2. Builder và lambda phối hợp như thế nào?

Builder là đối tượng hỗ trợ xây dựng một object theo từng bước. Mỗi phương thức cấu hình một phần của object và thường trả về builder để có thể gọi nối tiếp.

Lambda là một biểu thức truyền vào phương thức. Trong Java API Client, các phương thức builder thường nhận lambda có tham số là builder của kiểu query tương ứng. Lambda cấu hình builder đó và trả lại builder để thư viện hoàn tất đối tượng.

Ví dụ:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .match(m -> m
                .field("name")
                .query("keyboard")
            )
        )
        .build();

Có thể đọc từ ngoài vào trong:

1. NativeQuery.builder() bắt đầu xây dựng một Spring Data NativeQuery.
2. withQuery(...) cấu hình phần query chính.
3. q là builder của Elasticsearch Query.
4. q.match(...) chọn biến thể match query.
5. m là builder của MatchQuery.
6. field("name") chọn field tìm kiếm.
7. query("keyboard") đặt từ khóa.
8. build() tạo NativeQuery hoàn chỉnh.

Mỗi lambda có phạm vi riêng. Tên biến q, m, b chỉ là tên tham số do lập trình viên chọn; chúng không phải từ khóa đặc biệt của Elasticsearch.

### Lambda không phải là truy vấn được thực thi ngay

Các lambda trong builder dùng để cấu hình object query. Khi đoạn code tạo NativeQuery chạy, nó xây dựng cấu trúc truy vấn trong bộ nhớ. Elasticsearch chỉ nhận và thực thi truy vấn khi ứng dụng gọi operations.search(...), elasticsearchClient.search(...) hoặc một API thực thi tương ứng.

Vì vậy, cần phân biệt:

- **Xây dựng query:** tạo cấu trúc Java mô tả điều kiện.
- **Thực thi query:** gửi request đến Elasticsearch.
- **Đọc kết quả:** nhận response và ánh xạ document thành entity hoặc kiểu kết quả.

Việc tách ba bước này giúp có thể tạo query trong một phương thức, truyền nó sang tầng khác, kiểm thử cấu trúc hoặc tái sử dụng query trước khi thực thi.

## 3. Truy vấn match cơ bản

Ví dụ tìm sản phẩm theo tên:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .match(m -> m
                .field("name")
                .query("mechanical keyboard")
            )
        )
        .build();

Query này tương ứng với Elasticsearch DSL:

    {
      "query": {
        "match": {
          "name": "mechanical keyboard"
        }
      }
    }

match phù hợp với field text, vì Elasticsearch phân tích chuỗi tìm kiếm bằng analyzer của field. Từ khóa được phân tích thành token rồi dùng để tìm document phù hợp.

Nếu field là keyword và cần so khớp chính xác, thường dùng term thay vì match. Lựa chọn query cần dựa trên mapping và mục tiêu tìm kiếm.

## 4. Phân biệt NativeQuery và Query của Elasticsearch Java Client

Có hai kiểu Query dễ gây nhầm lẫn:

- org.springframework.data.elasticsearch.core.query.Query: abstraction query của Spring Data.
- co.elastic.clients.elasticsearch._types.query_dsl.Query: kiểu query do Elasticsearch Java API Client cung cấp.

NativeQuery là kiểu query của Spring Data, còn lambda trong withQuery xây dựng kiểu query của Elasticsearch Java API Client.

Các import thường dùng:

    import co.elastic.clients.elasticsearch._types.FieldValue;
    import co.elastic.clients.elasticsearch._types.query_dsl.Query;
    import org.springframework.data.elasticsearch.client.elc.NativeQuery;
    import org.springframework.data.elasticsearch.core.SearchHits;
    import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

Trong code thực tế, không cần khai báo biến Query nếu chỉ dùng lambda trong withQuery. Nhưng khi tách query ra phương thức riêng, có thể khai báo rõ kiểu co.elastic.clients.elasticsearch._types.query_dsl.Query để tránh nhầm với interface query của Spring Data.

Ví dụ tạo một query Java Client trước:

    co.elastic.clients.elasticsearch._types.query_dsl.Query nameQuery =
        co.elastic.clients.elasticsearch._types.query_dsl.Query.of(q -> q
            .match(m -> m
                .field("name")
                .query("keyboard")
            )
        );

    NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(nameQuery)
        .build();

Query.of(...) là factory method của kiểu query Java Client. Nó tạo một query cụ thể từ lambda builder. Sau đó đối tượng này được truyền vào NativeQuery.

## 5. Xây dựng bool query với nhiều lambda lồng nhau

Truy vấn thực tế thường kết hợp nhiều điều kiện. Ví dụ tìm sản phẩm có tên liên quan đến keyboard, chỉ lấy sản phẩm đang hoạt động và thuộc danh mục accessories.

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .bool(b -> b
                .must(m -> m
                    .match(mm -> mm
                        .field("name")
                        .query("keyboard")
                    )
                )
                .filter(f -> f
                    .term(t -> t
                        .field("status")
                        .value(FieldValue.of("ACTIVE"))
                    )
                )
                .filter(f -> f
                    .term(t -> t
                        .field("category")
                        .value(FieldValue.of("accessories"))
                    )
                )
            )
        )
        .build();

Truy vấn tương đương:

    {
      "query": {
        "bool": {
          "must": [
            {
              "match": {
                "name": "keyboard"
              }
            }
          ],
          "filter": [
            {
              "term": {
                "status": "ACTIVE"
              }
            },
            {
              "term": {
                "category": "accessories"
              }
            }
          ]
        }
      }
    }

Trong ví dụ:

- bool kết hợp nhiều clause.
- must yêu cầu document khớp nội dung tìm kiếm và đóng góp vào điểm liên quan.
- filter giới hạn trạng thái và danh mục, không tính điểm liên quan.
- FieldValue.of(...) tạo giá trị term theo kiểu dữ liệu mà Java API Client yêu cầu.

Các lambda lồng nhau phản ánh cấu trúc của Query DSL. Mỗi cấp có một builder tương ứng: Query.Builder, BoolQuery.Builder, MatchQuery.Builder hoặc TermQuery.Builder.

### Dùng should để tăng điểm

Nếu muốn ưu tiên sản phẩm có tên phù hợp và tăng điểm thêm khi mô tả cũng phù hợp:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .bool(b -> b
                .must(m -> m
                    .match(mm -> mm
                        .field("name")
                        .query("mechanical keyboard")
                    )
                )
                .should(s -> s
                    .match(m -> m
                        .field("description")
                        .query("mechanical keyboard")
                    )
                )
                .minimumShouldMatch("0")
            )
        )
        .build();

Ở đây must quyết định điều kiện tìm kiếm chính. should có thể đóng góp điểm nếu mô tả khớp. Vì bool đã có must, should mặc định là tùy chọn; khai báo minimumShouldMatch("0") làm ý định này rõ ràng.

Nếu yêu cầu ít nhất một điều kiện trong should phải khớp, đặt minimumShouldMatch("1") và tổ chức các clause phù hợp. Giá trị của minimum_should_match có thể là biểu thức linh hoạt hơn một số nguyên, tùy cú pháp Elasticsearch hỗ trợ.

## 6. Xây dựng term query và giá trị có kiểu

term dùng để so khớp chính xác một giá trị đã được index. Nó thường phù hợp với field keyword, mã định danh, trạng thái hoặc giá trị enum.

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .term(t -> t
                .field("status")
                .value(FieldValue.of("ACTIVE"))
            )
        )
        .build();

Java API Client sử dụng FieldValue để biểu diễn các loại giá trị khác nhau như string, long, double, boolean hoặc null. Ví dụ:

    FieldValue stringValue = FieldValue.of("ACTIVE");
    FieldValue numberValue = FieldValue.of(100L);
    FieldValue decimalValue = FieldValue.of(19.95);
    FieldValue booleanValue = FieldValue.of(true);

Không nên truyền mọi giá trị thành chuỗi. Kiểu dữ liệu của giá trị phải phù hợp với mapping của field. Ví dụ field số nên dùng giá trị số; field keyword nên dùng chuỗi.

## 7. Xây dựng range query

Range query dùng để lọc theo khoảng số, ngày hoặc kiểu dữ liệu có hỗ trợ range. Ví dụ tìm sản phẩm có giá từ 100 đến 500:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .range(r -> r
                .number(n -> n
                    .field("price")
                    .gte(100.0)
                    .lte(500.0)
                )
            )
        )
        .build();

Với Elasticsearch Java API Client hiện đại, range query có các biến thể theo kiểu dữ liệu. Đối với field số, builder number biểu diễn numeric range. Với field ngày, có thể dùng biến thể date range và giá trị ngày ở định dạng mà mapping hỗ trợ.

Ví dụ lọc ngày tạo trong một khoảng:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .range(r -> r
                .date(d -> d
                    .field("createdAt")
                    .gte("2026-01-01T00:00:00Z")
                    .lt("2027-01-01T00:00:00Z")
                )
            )
        )
        .build();

Các biến thể builder của range query có thể thay đổi theo phiên bản Java API Client. Hãy dùng kiểu phù hợp với dependency đang khai báo; không trộn cú pháp range cũ dùng JsonData với API typed range mới trong cùng ví dụ.

## 8. Xây dựng multi_match query

multi_match tìm nội dung trên nhiều field. Có thể tăng trọng số field quan trọng bằng cú pháp boost:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .multiMatch(m -> m
                .query("spring data")
                .fields("name^3", "description", "brand")
            )
        )
        .build();

Ở ví dụ này, field name có boost 3, còn description và brand dùng trọng số mặc định. Document khớp ở tên sản phẩm có thể được ưu tiên hơn document chỉ khớp ở mô tả hoặc thương hiệu.

Multi-match có nhiều kiểu hoạt động, chẳng hạn best_fields, most_fields, cross_fields hoặc phrase. Nếu nghiệp vụ cần chọn kiểu cụ thể, cấu hình type(...) theo enum tương ứng của Java API Client.

Không nên thêm nhiều field vào multi-match mà không cân nhắc mapping, analyzer và độ quan trọng của từng field. Số lượng field cùng tham gia có thể ảnh hưởng chi phí query và thứ tự kết quả.

## 9. Tách query thành các phương thức nhỏ

Một truy vấn lớn có thể khó đọc nếu mọi điều kiện được đặt trong một biểu thức lambda lồng sâu. Có thể tách các phần thành những phương thức trả về Query.

    private Query nameMatch(String keyword) {
        return Query.of(q -> q
            .match(m -> m
                .field("name")
                .query(keyword)
            )
        );
    }

    private Query activeFilter() {
        return Query.of(q -> q
            .term(t -> t
                .field("status")
                .value(FieldValue.of("ACTIVE"))
            )
        );
    }

    private Query categoryFilter(String category) {
        return Query.of(q -> q
            .term(t -> t
                .field("category")
                .value(FieldValue.of(category))
            )
        );
    }

Sau đó kết hợp:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .bool(b -> b
                .must(nameMatch(keyword))
                .filter(activeFilter())
                .filter(categoryFilter(category))
            )
        )
        .build();

Lợi ích:

- Mỗi phương thức mô tả một điều kiện có ý nghĩa.
- Có thể tái sử dụng filter hoặc query ở nhiều truy vấn.
- Dễ kiểm thử riêng từng thành phần.
- Giảm độ sâu của lambda trong truy vấn tổng thể.

Không nên tách mọi dòng thành một phương thức nhỏ. Chỉ tách những điều kiện có ý nghĩa nghiệp vụ hoặc có khả năng tái sử dụng để tránh làm code phân mảnh.

## 10. Kết hợp điều kiện tùy chọn

Một màn hình tìm kiếm có thể cho phép người dùng nhập từ khóa, chọn danh mục hoặc giới hạn giá. Một số tham số có thể để trống. Khi đó, chỉ thêm clause tương ứng nếu người dùng đã cung cấp giá trị.

Có thể xây dựng danh sách query trước rồi đưa vào bool query:

    List<Query> filters = new ArrayList<>();

    filters.add(Query.of(q -> q
        .term(t -> t
            .field("status")
            .value(FieldValue.of("ACTIVE"))
        )
    ));

    if (category != null && !category.isBlank()) {
        filters.add(Query.of(q -> q
            .term(t -> t
                .field("category")
                .value(FieldValue.of(category))
            )
        ));
    }

    if (minimumPrice != null || maximumPrice != null) {
        filters.add(Query.of(q -> q
            .range(r -> r
                .number(n -> {
                    n.field("price");
                    if (minimumPrice != null) {
                        n.gte(minimumPrice);
                    }
                    if (maximumPrice != null) {
                        n.lte(maximumPrice);
                    }
                    return n;
                })
            )
        ));
    }

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .bool(b -> b
                .filter(filters)
            )
        )
        .build();

Ở đây, danh sách filters được tạo theo tham số đầu vào. Lambda block cho phép gọi nhiều phương thức trên cùng builder trước khi trả builder ở cuối. Cách này hữu ích khi query có điều kiện tùy chọn.

Nếu dự án dùng phiên bản Java API Client có API range builder khác, điều chỉnh phần numeric range theo đúng kiểu của phiên bản đó. Ý tưởng composition vẫn giữ nguyên: chỉ tạo clause khi tham số có giá trị, sau đó truyền danh sách vào filter.

Khi có nhiều điều kiện tùy chọn, nên kiểm tra trường hợp danh sách rỗng. Một bool query chỉ có filter rỗng có thể mang ý nghĩa match-all theo semantics của Elasticsearch; nếu nghiệp vụ cần bắt buộc có ít nhất một điều kiện, hãy kiểm tra đầu vào ở service trước khi tạo query.

## 11. Thêm phân trang và sắp xếp

NativeQuery có thể kết hợp với Pageable của Spring Data. Ví dụ lấy trang đầu tiên gồm 20 sản phẩm, sắp xếp giá giảm dần:

    Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("price"))
    );

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .match(m -> m
                .field("name")
                .query("keyboard")
            )
        )
        .withPageable(pageable)
        .build();

PageRequest dùng chỉ số trang bắt đầu từ 0. Sort tham chiếu tên field mapping trong Elasticsearch, vì vậy phải dùng đúng tên field được index.

Nếu cần sắp xếp theo nhiều trường:

    Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.asc("name")
        )
    );

Với tập dữ liệu lớn và phân trang sâu, from/size có giới hạn và có thể tốn tài nguyên. Khi cần duyệt sâu qua nhiều kết quả, cân nhắc search_after cùng sort ổn định hoặc cơ chế phù hợp với phiên bản Elasticsearch.

## 12. Thêm aggregation

NativeQuery cũng có thể chứa aggregation. Ví dụ đếm số sản phẩm theo category:

    import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .term(t -> t
                .field("status")
                .value(FieldValue.of("ACTIVE"))
            )
        )
        .withAggregation(
            "products_by_category",
            Aggregation.of(a -> a
                .terms(t -> t
                    .field("category")
                )
            )
        )
        .build();

Query giới hạn tập sản phẩm đang hoạt động, còn aggregation nhóm các document phù hợp theo category. Field dùng cho terms aggregation thường là keyword hoặc một field có doc values phù hợp, không nên mặc định dùng field text đã phân tích.

Khi cần đọc kết quả aggregation, response có thể được lấy từ SearchHits hoặc API response tương ứng của Spring Data, tùy kiểu aggregation và phiên bản. Nên giữ rõ tên aggregation (products_by_category) để đọc đúng bucket trong kết quả.

## 13. Thực thi NativeQuery bằng ElasticsearchOperations

Sau khi xây dựng query, có thể thực thi qua ElasticsearchOperations:

    @Service
    public class ProductSearchService {

        private final ElasticsearchOperations operations;

        public ProductSearchService(
                ElasticsearchOperations operations) {
            this.operations = operations;
        }

        public SearchHits<Product> search(
                String keyword,
                String category,
                Pageable pageable) {

            NativeQuery query = NativeQuery.builder()
                .withQuery(q -> q
                    .bool(b -> b
                        .must(m -> m
                            .match(mm -> mm
                                .field("name")
                                .query(keyword)
                            )
                        )
                        .filter(f -> f
                            .term(t -> t
                                .field("status")
                                .value(FieldValue.of("ACTIVE"))
                            )
                        )
                        .filter(f -> f
                            .term(t -> t
                                .field("category")
                                .value(FieldValue.of(category))
                            )
                        )
                    )
                )
                .withPageable(pageable)
                .build();

            return operations.search(query, Product.class);
        }
    }

operations.search(query, Product.class) thực hiện truy vấn trên index được xác định từ metadata entity, thường là @Document(indexName = "products"). Spring Data dùng converter để ánh xạ document JSON thành Product.

Nếu cần chỉ định index hoặc alias cụ thể, có thể truyền IndexCoordinates vào overload tương ứng:

    SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
    );

Điều này hữu ích khi entity có thể được đọc từ nhiều index hoặc ứng dụng dùng alias ổn định.

## 14. Đọc SearchHits và metadata của kết quả

SearchHits<T> chứa các search hit cùng metadata như tổng số kết quả, score và thông tin liên quan. Có thể duyệt:

    SearchHits<Product> hits =
        operations.search(query, Product.class);

    for (SearchHit<Product> hit : hits) {
        Product product = hit.getContent();
        float score = hit.getScore();
        String id = hit.getId();
    }

Nếu chỉ cần entity, có thể chuyển nội dung:

    List<Product> products = hits.getSearchHits()
        .stream()
        .map(SearchHit::getContent)
        .toList();

Không nên bỏ metadata nếu giao diện cần hiển thị score, highlight hoặc tổng số hit. Kiểu kết quả nên phản ánh đúng thông tin tầng gọi cần.

## 15. Thêm highlight cho kết quả tìm kiếm

Với tìm kiếm toàn văn, ứng dụng có thể cần đoạn văn bản khớp từ khóa để hiển thị. NativeQuery có thể cấu hình highlight theo API hỗ trợ của Spring Data và Java Client.

Highlight được khai báo trong phần tùy chọn của truy vấn, chỉ định field cần tạo fragment và các giới hạn như số fragment. Cấu trúc builder cụ thể phụ thuộc phiên bản Spring Data Elasticsearch và Java API Client; hãy kiểm tra chữ ký highlight tương ứng trong dependency thực tế trước khi triển khai.

Highlight chỉ hỗ trợ trình bày phần văn bản khớp. Nó không thay thế analyzer hoặc quyết định query có khớp hay không.

## 16. Tách phần xây dựng query khỏi phần thực thi

Với truy vấn lớn, có thể tạo một phương thức riêng trả về NativeQuery:

    private NativeQuery buildProductQuery(
            String keyword,
            String category,
            Pageable pageable) {

        return NativeQuery.builder()
            .withQuery(q -> q
                .bool(b -> b
                    .must(m -> m
                        .match(mm -> mm
                            .field("name")
                            .query(keyword)
                        )
                    )
                    .filter(f -> f
                        .term(t -> t
                            .field("status")
                            .value(FieldValue.of("ACTIVE"))
                        )
                    )
                    .filter(f -> f
                        .term(t -> t
                            .field("category")
                            .value(FieldValue.of(category))
                        )
                    )
                )
            )
            .withPageable(pageable)
            .build();
    }

    public SearchHits<Product> search(
            String keyword,
            String category,
            Pageable pageable) {
        NativeQuery query =
            buildProductQuery(keyword, category, pageable);

        return operations.search(query, Product.class);
    }

Cách tổ chức này tạo ranh giới rõ ràng:

- buildProductQuery chịu trách nhiệm mô tả điều kiện.
- search chịu trách nhiệm gửi truy vấn và trả kết quả.

Nếu có nhiều biến thể query, có thể tách builder theo use case hoặc nhóm điều kiện. Tránh tạo một query builder tổng quát quá lớn với hàng chục tham số boolean khiến khó hiểu điều kiện nào thực sự được thêm vào.

## 17. Khi nào dùng Query.of và khi nào dùng lambda trực tiếp?

Cả hai cách đều hợp lệ.

Lambda trực tiếp trong NativeQuery:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .match(m -> m
                .field("name")
                .query(keyword)
            )
        )
        .build();

Tạo Query trước bằng Query.of:

    Query esQuery = Query.of(q -> q
        .match(m -> m
            .field("name")
            .query(keyword)
        )
    );

    NativeQuery query = NativeQuery.builder()
        .withQuery(esQuery)
        .build();

Dùng lambda trực tiếp khi query ngắn và chỉ được dùng tại một chỗ. Dùng Query.of khi muốn đặt query vào phương thức riêng, tái sử dụng, ghép danh sách clause hoặc kiểm thử cấu trúc query độc lập với NativeQuery.

## 18. Các lưu ý về builder và biểu thức lambda

### Đặt đúng field name

Các builder nhận tên field dưới dạng chuỗi. Java compiler không thể xác minh tên field có tồn tại trong mapping hay không. Sai tên field có thể khiến query không trả kết quả hoặc gây lỗi khi dùng sort/aggregation.

Hãy đối chiếu với mapping thực tế và cân nhắc hằng số cho những field được dùng nhiều:

    private static final String FIELD_NAME = "name";
    private static final String FIELD_CATEGORY = "category";

Hằng số giảm lỗi gõ sai trong mã Java nhưng không thay thế việc kiểm tra mapping.

### Dùng đúng kiểu giá trị

Java API Client thường yêu cầu FieldValue cho term value. Range query dùng kiểu giá trị phù hợp với biến thể numeric/date. Không chuyển mọi thứ thành String nếu field được mapping là số hoặc ngày.

### Phân biệt must và filter

Builder cho phép gọi cả must(...) và filter(...), nhưng ý nghĩa truy vấn khác nhau:

- must dùng query context và có thể đóng góp score.
- filter chỉ xác định điều kiện đúng/sai và không đóng góp score.

Dùng filter cho trạng thái, danh mục, khoảng giá hoặc điều kiện bắt buộc không cần xếp hạng; dùng must/should cho điều kiện nội dung cần ảnh hưởng điểm liên quan.

### Không tái sử dụng builder đã build

Builder là đối tượng mutable trong quá trình cấu hình. Sau khi gọi build(), hãy sử dụng object query đã tạo. Nếu cần biến thể truy vấn khác, tạo builder mới hoặc tạo object query mới thay vì chia sẻ builder mutable giữa nhiều thread.

### Tránh lambda quá sâu

Lambda lồng nhau phản ánh cấu trúc Query DSL, nhưng quá nhiều tầng có thể làm code khó đọc. Tách các clause thành phương thức trả về Query khi chúng có ý nghĩa riêng hoặc được tái sử dụng.

### Kiểm tra API theo phiên bản

Các kiểu builder do Elasticsearch Java API Client sinh ra phụ thuộc phiên bản client. Một số kiểu range, highlight, aggregation hoặc enum có thể thay đổi giữa các dòng phiên bản. Dùng dependency management của Spring Boot/Spring Data để giữ các thư viện tương thích và kiểm tra Javadoc tương ứng.

## 19. Những lỗi thường gặp

### Nhầm NativeQuery với Query builder

NativeQuery là kiểu query của Spring Data; lambda withQuery xây dựng kiểu Query của Elasticsearch Java API Client. Phân biệt hai abstraction giúp tránh import nhầm class Query.

### Truyền String trực tiếp vào term value

Java API Client thường yêu cầu FieldValue cho term value. Dùng FieldValue.of(...) để biểu diễn giá trị đúng kiểu.

### Dùng term trên field text

Field text được analyzer tách token. Nếu cần tìm toàn văn, dùng match hoặc query phù hợp. term thường dành cho giá trị chính xác trên field keyword hoặc kiểu dữ liệu phù hợp.

### Dùng match trên field keyword mà không hiểu mapping

Match query phân tích chuỗi đầu vào theo search analyzer. Với field keyword, nếu cần so khớp chính xác, term query thường rõ nghĩa hơn.

### Đặt mọi điều kiện vào must

Điều kiện filter như status, category hoặc price range không nhất thiết cần tham gia tính điểm. Đưa chúng vào filter giúp thể hiện đúng ý nghĩa và tránh tính score không cần thiết.

### Không xử lý tham số tùy chọn

Nếu tham số rỗng vẫn được thêm vào query, kết quả có thể sai hoặc query không hợp lệ. Chỉ thêm clause khi đầu vào có giá trị và xác định rõ hành vi khi không có điều kiện.

### Quên phân trang hoặc giới hạn kết quả

Search query có thể trả về số lượng kết quả mặc định giới hạn. Hãy cấu hình Pageable hoặc kích thước kết quả phù hợp với API.

### Nghĩ build() đã gửi request

build() chỉ tạo object query. Request chỉ được gửi khi gọi operations hoặc client thực thi.

### Dùng ví dụ builder không khớp phiên bản

Các builder Java Client có thể khác nhau giữa phiên bản. Nếu IDE báo không có phương thức như number(...), date(...) hoặc một overload cụ thể, kiểm tra phiên bản dependency và dùng chữ ký đúng với API đang có.

## 20. Quy trình xây dựng một NativeQuery dễ bảo trì

Khi triển khai một truy vấn mới, có thể làm theo trình tự:

1. Xác định mapping của các field sẽ dùng trong query.
2. Xác định điều kiện nào cần tính điểm và điều kiện nào chỉ lọc.
3. Bắt đầu với một query nhỏ, thường là match, term hoặc range.
4. Kết hợp các điều kiện bằng bool và các lambda tương ứng.
5. Tách clause thành phương thức trả về Query nếu truy vấn quá sâu hoặc cần tái sử dụng.
6. Thêm Pageable, sort, aggregation hoặc highlight khi nghiệp vụ cần.
7. Tạo NativeQuery bằng build().
8. Thực thi qua ElasticsearchOperations.search(...).
9. Đọc SearchHits và xử lý score/metadata nếu cần.
10. Kiểm tra truy vấn với dữ liệu và mapping thực tế trên Elasticsearch.

Ví dụ đầy đủ:

    @Service
    public class ProductSearchService {

        private final ElasticsearchOperations operations;

        public ProductSearchService(
                ElasticsearchOperations operations) {
            this.operations = operations;
        }

        public SearchHits<Product> search(
                String keyword,
                String category,
                Double minPrice,
                Double maxPrice,
                int page,
                int size) {

            NativeQuery query = NativeQuery.builder()
                .withQuery(q -> q
                    .bool(b -> {
                        b.must(m -> m
                            .match(mm -> mm
                                .field("name")
                                .query(keyword)
                            )
                        );

                        b.filter(f -> f
                            .term(t -> t
                                .field("status")
                                .value(FieldValue.of("ACTIVE"))
                            )
                        );

                        if (category != null && !category.isBlank()) {
                            b.filter(f -> f
                                .term(t -> t
                                    .field("category")
                                    .value(FieldValue.of(category))
                                )
                            );
                        }

                        if (minPrice != null || maxPrice != null) {
                            b.filter(f -> f
                                .range(r -> r
                                    .number(n -> {
                                        n.field("price");
                                        if (minPrice != null) {
                                            n.gte(minPrice);
                                        }
                                        if (maxPrice != null) {
                                            n.lte(maxPrice);
                                        }
                                        return n;
                                    })
                                )
                            );
                        }

                        return b;
                    })
                )
                .withPageable(PageRequest.of(
                    page,
                    size,
                    Sort.by(Sort.Order.desc("createdAt"))
                ))
                .build();

            return operations.search(query, Product.class);
        }
    }

Trong truy vấn này:

- Tên sản phẩm được tìm bằng match trong must.
- Trạng thái ACTIVE luôn là filter bắt buộc.
- Category chỉ được thêm khi người dùng chọn danh mục.
- Range price chỉ được thêm khi có ít nhất một giới hạn giá.
- Pageable giới hạn số kết quả và sắp xếp theo ngày tạo.
- operations.search thực thi query và ánh xạ kết quả thành Product.

Lambda block cho bool builder cho phép cấu hình các clause theo điều kiện Java rồi trả builder ở cuối. Với phiên bản Java API Client dùng trong dự án, kiểm tra kiểu range builder và chữ ký các overload để bảo đảm code tương thích.

## Kết luận

NativeQuery là cách xây dựng truy vấn linh hoạt trong Spring Data Elasticsearch khi cần sử dụng trực tiếp Elasticsearch Query DSL. NativeQuery.builder() cấu hình query của Spring Data; withQuery nhận một lambda để tạo Query từ Elasticsearch Java API Client. Các lambda lồng nhau lần lượt cấu hình builder của bool, match, term, range và những query khác.

Để truy vấn dễ đọc và đúng semantics, hãy dùng must/should cho điều kiện tìm kiếm có ảnh hưởng đến điểm liên quan, dùng filter cho điều kiện giới hạn, chọn đúng kiểu giá trị như FieldValue, thêm phân trang và sort khi cần, rồi thực thi bằng ElasticsearchOperations. Khi query lớn, tách các clause thành phương thức nhỏ trả về Query. Luôn đối chiếu mapping và phiên bản Java API Client của dự án vì builder được sinh theo phiên bản thư viện.
