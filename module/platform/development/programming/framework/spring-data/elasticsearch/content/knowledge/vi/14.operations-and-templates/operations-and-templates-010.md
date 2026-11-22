# Tiêm Operations trong dịch vụ hoặc Repository fragment

Spring Data Elasticsearch cung cấp ElasticsearchOperations như một abstraction để ứng dụng thực hiện các thao tác tìm kiếm, lưu, lấy và xóa document. Thay vì tự tạo client ở từng service hoặc viết toàn bộ truy vấn trong repository method, ứng dụng có thể inject ElasticsearchOperations vào service hoặc vào một repository fragment chuyên xử lý truy vấn tùy chỉnh.

Hai cách tổ chức này giải quyết những nhu cầu hơi khác nhau:

- **Inject vào service:** phù hợp khi thao tác Elasticsearch là một phần của use case hoặc nghiệp vụ của service. Service trực tiếp xây dựng query, gọi operations và xử lý kết quả.
- **Inject vào repository fragment:** phù hợp khi muốn gom các truy vấn dữ liệu đặc thù thành một API repository có thể tái sử dụng. Service gọi phương thức có ý nghĩa nghiệp vụ trên repository, còn fragment đảm nhiệm chi tiết truy vấn.

Trong cả hai cách, nên dùng constructor injection, phụ thuộc vào interface ElasticsearchOperations và để Spring quản lý bean cùng vòng đời của client. Không nên tự tạo ElasticsearchTemplate hoặc ElasticsearchClient mới bên trong mỗi phương thức.

## 1. ElasticsearchOperations là gì?

ElasticsearchOperations là interface cấp cao của Spring Data Elasticsearch, cung cấp các thao tác làm việc với document và index. ElasticsearchTemplate là implementation phổ biến của interface này trong ứng dụng đồng bộ.

Operations đứng giữa tầng nghiệp vụ và Elasticsearch Java Client:

    Controller
       |
       v
    Service hoặc Repository fragment
       |
       v
    ElasticsearchOperations
       |
       +-- MappingElasticsearchConverter
       |
       v
    Elasticsearch Java Client
       |
       v
    Elasticsearch cluster

Khi gọi operations với một entity class, Spring Data có thể sử dụng mapping metadata và converter để chuyển đổi giữa object Java và document JSON. Vì vậy, ứng dụng vẫn làm việc với entity và kiểu dữ liệu quen thuộc thay vì tự tuần tự hóa toàn bộ document.

Một số trách nhiệm thường dùng của ElasticsearchOperations:

- Lưu hoặc cập nhật entity.
- Lấy document theo id.
- Xóa document.
- Thực hiện truy vấn search.
- Trả về SearchHits để giữ thông tin về score, highlight và metadata của từng hit.
- Thực hiện thao tác thông qua IndexCoordinates khi cần chỉ định index hoặc alias rõ ràng.

ElasticsearchOperations là abstraction cho thao tác dữ liệu. Việc tạo index, mapping và settings thuộc nhóm API quản lý index như IndexOperations, dù operations có thể cung cấp điểm truy cập đến các API này.

## 2. Vì sao inject ElasticsearchOperations?

Nếu chỉ dùng các thao tác CRUD thông thường, repository có thể đã đủ:

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String> {
        List<Product> findByCategory(String category);
    }

Nhưng khi truy vấn có nhiều điều kiện, cần dùng native query, aggregation, highlight hoặc xử lý SearchHits, một repository method được tạo từ tên phương thức có thể không còn dễ diễn đạt.

Inject ElasticsearchOperations giúp service:

- Xây dựng query bằng Query, NativeQuery hoặc CriteriaQuery.
- Kết hợp must, should, filter, range, sort và pagination.
- Lấy SearchHits để đọc score hoặc highlight.
- Chọn entity class để Spring Data ánh xạ kết quả.
- Kiểm soát rõ ràng nơi đặt truy vấn và cách xử lý kết quả.

Ví dụ, màn hình tìm sản phẩm cần tìm theo tên, chỉ lấy sản phẩm đang hoạt động và phân trang. Đây là truy vấn có thể được diễn đạt bằng NativeQuery trong service.

Không nên inject operations vào mọi service chỉ vì có thể. Nếu repository method đã thể hiện rõ nghiệp vụ và không cần truy vấn tùy chỉnh, dùng repository thường đơn giản hơn. Operations hữu ích khi cần quyền kiểm soát truy vấn ở mức Spring Data.

## 3. Spring Boot cung cấp bean ElasticsearchOperations

Trong ứng dụng Spring Boot sử dụng Spring Data Elasticsearch starter, cấu hình tự động thường tạo các bean cần thiết cho client và operations dựa trên cấu hình kết nối.

Dependency Gradle thường dùng:

    dependencies {
        implementation("org.springframework.boot:spring-boot-starter-data-elasticsearch")
    }

Địa chỉ cluster có thể khai báo:

    spring:
      elasticsearch:
        uris: http://localhost:9200

Khi cấu hình tự động hoạt động, service có thể inject ElasticsearchOperations trực tiếp. Ứng dụng không cần tự khởi tạo ElasticsearchTemplate trong constructor.

Nếu dự án tự cấu hình client, cần bảo đảm bean ElasticsearchOperations được tạo từ client và converter tương ứng. Với các dòng Spring Data hiện đại, cấu hình thường kết nối ElasticsearchClient với ElasticsearchTemplate.

Ví dụ cấu hình bean theo hướng thủ công có thể phụ thuộc vào phiên bản Spring Data và cách ứng dụng tạo client. Chỉ nên cung cấp bean tùy chỉnh khi cần thay đổi cấu hình mặc định, chẳng hạn kết nối nhiều cluster hoặc converter đặc biệt.

## 4. Inject ElasticsearchOperations vào service bằng constructor injection

Ví dụ service trực tiếp thực hiện truy vấn tìm sản phẩm theo tên:

    @Service
    public class ProductSearchService {

        private final ElasticsearchOperations operations;

        public ProductSearchService(
                ElasticsearchOperations operations) {
            this.operations = operations;
        }

        public SearchHits<Product> searchByName(
                String keyword,
                Pageable pageable) {

            Query query = NativeQuery.builder()
                .withQuery(q -> q
                    .match(m -> m
                        .field("name")
                        .query(keyword)
                    )
                )
                .withPageable(pageable)
                .build();

            return operations.search(query, Product.class);
        }
    }

Ở ví dụ này:

1. Spring tạo ProductSearchService và inject bean ElasticsearchOperations.
2. Service xây dựng NativeQuery với match query trên field name.
3. Pageable xác định số trang và kích thước trang.
4. operations.search gửi truy vấn qua tầng tích hợp client.
5. Spring Data ánh xạ các document trả về thành Product và đóng gói thông tin trong SearchHits.

Constructor injection có một số lợi ích:

- Phụ thuộc được thể hiện rõ ngay trong constructor.
- Trường operations có thể khai báo final.
- Service dễ kiểm thử vì có thể truyền mock hoặc implementation thay thế.
- Không cần field injection hoặc gọi ApplicationContext để lấy bean.

Không nên viết:

    public ProductSearchService() {
        this.operations = new ElasticsearchTemplate(...);
    }

Cách tự tạo template trong service làm service phụ thuộc vào chi tiết cấu hình client, có thể tạo nhiều client/connection pool và bỏ qua cấu hình chung của Spring.

## 5. Dùng NativeQuery và đọc SearchHits trong service

Khi truy vấn cần kết hợp tìm kiếm toàn văn và điều kiện lọc, có thể xây dựng NativeQuery:

    public SearchHits<Product> searchProducts(
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

Trong ví dụ:

- must chứa match query, nên nội dung tên sản phẩm tham gia tính điểm liên quan.
- filter giới hạn category nhưng không đóng góp vào score.
- Pageable giới hạn kết quả theo trang.
- SearchHits giữ cả nội dung entity và metadata của kết quả tìm kiếm.

Có thể đọc kết quả:

    SearchHits<Product> hits =
        searchProducts("mechanical keyboard", "accessories",
                       PageRequest.of(0, 20));

    for (SearchHit<Product> hit : hits) {
        Product product = hit.getContent();
        float score = hit.getScore();
        // Use product and score
    }

Nếu service chỉ cần danh sách entity, có thể chuyển SearchHits thành List<Product>. Nhưng nếu giao diện cần hiển thị score, highlight hoặc thông tin hit, nên giữ SearchHits ở tầng xử lý thích hợp thay vì bỏ metadata quá sớm.

Tên builder và kiểu query cụ thể cần theo phiên bản Spring Data Elasticsearch của dự án. NativeQuery trong các dòng hiện đại được tích hợp với Elasticsearch Java Client.

## 6. Khi nào nên inject Operations vào service?

Inject ElasticsearchOperations trực tiếp vào service phù hợp khi truy vấn là một phần của use case và chỉ được sử dụng ở một vài nơi.

Ví dụ:

- Một màn hình báo cáo cần nhiều aggregation.
- Một use case cần kết hợp search và filter theo quyền truy cập.
- Một quy trình cần search, sau đó xử lý SearchHits hoặc score.
- Một tác vụ quản trị dữ liệu cần thực hiện thao tác có cấu trúc đặc biệt.

Service có thể phối hợp nhiều nguồn dữ liệu:

    @Service
    public class CatalogService {

        private final ProductRepository repository;
        private final ElasticsearchOperations operations;

        public CatalogService(
                ProductRepository repository,
                ElasticsearchOperations operations) {
            this.repository = repository;
            this.operations = operations;
        }

        public Product getProduct(String id) {
            return repository.findById(id).orElseThrow();
        }

        public SearchHits<Product> searchCatalog(
                String keyword,
                Pageable pageable) {
            Query query = NativeQuery.builder()
                .withQuery(q -> q
                    .multiMatch(m -> m
                        .query(keyword)
                        .fields("name", "description")
                    )
                )
                .withPageable(pageable)
                .build();

            return operations.search(query, Product.class);
        }
    }

Repository đảm nhiệm thao tác tìm theo id đơn giản; operations đảm nhiệm truy vấn nhiều trường. Việc sử dụng hai abstraction trong cùng service là hợp lý nếu mỗi abstraction làm rõ một loại thao tác.

Tuy nhiên, nếu nhiều service lặp lại cùng một truy vấn phức tạp, nên đưa phần truy vấn đó vào repository fragment để tránh lặp code và giữ API dữ liệu ở một nơi.

## 7. Repository fragment là gì?

Repository fragment là một phần mở rộng tùy chỉnh được ghép vào repository Spring Data. Fragment cho phép bổ sung phương thức mà repository interface mặc định không cung cấp, trong khi vẫn giữ cách sử dụng repository thông qua dependency injection.

Ví dụ, ProductRepository có thể kế thừa:

- ElasticsearchRepository<Product, String> cho CRUD.
- ProductSearch cho truy vấn tìm kiếm tùy chỉnh.

Sơ đồ:

    ProductService
         |
         v
    ProductRepository
         |
         +-------------------------------+
         |                               |
         v                               v
    ElasticsearchRepository         ProductSearch
    CRUD mặc định                   Fragment interface
                                         |
                                         v
                                  ProductSearchImpl
                                         |
                                         v
                                  ElasticsearchOperations

Spring Data ghép fragment implementation vào repository proxy. Service chỉ cần inject ProductRepository và gọi cả phương thức CRUD lẫn phương thức tùy chỉnh.

## 8. Tạo repository fragment interface

Trước tiên, khai báo interface mô tả khả năng tìm kiếm tùy chỉnh:

    public interface ProductSearch {

        SearchHits<Product> searchByName(
            String keyword,
            Pageable pageable
        );
    }

Interface này mô tả API mà repository muốn bổ sung. Nó không cần kế thừa ElasticsearchRepository và không chứa chi tiết cách tạo query.

Sau đó, repository chính kế thừa fragment:

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String>,
                    ProductSearch {
    }

ProductRepository hiện có:

- Các phương thức CRUD từ ElasticsearchRepository.
- Phương thức searchByName từ ProductSearch.

Service có thể inject ProductRepository và sử dụng cả hai nhóm phương thức mà không cần biết repository được ghép từ những fragment nào.

## 9. Viết fragment implementation và inject Operations

Theo quy ước mặc định, implementation của fragment interface ProductSearch được đặt tên ProductSearchImpl. Spring Data tìm implementation theo quy ước repository fragment và ghép nó vào repository proxy.

Ví dụ:

    public class ProductSearchImpl implements ProductSearch {

        private final ElasticsearchOperations operations;

        public ProductSearchImpl(
                ElasticsearchOperations operations) {
            this.operations = operations;
        }

        @Override
        public SearchHits<Product> searchByName(
                String keyword,
                Pageable pageable) {

            NativeQuery query = NativeQuery.builder()
                .withQuery(q -> q
                    .match(m -> m
                        .field("name")
                        .query(keyword)
                    )
                )
                .withPageable(pageable)
                .build();

            return operations.search(query, Product.class);
        }
    }

Implementation nhận ElasticsearchOperations qua constructor giống một service thông thường. Spring Data quản lý việc tạo fragment implementation và cung cấp bean dependency cho nó.

Theo mặc định, implementation class nên nằm trong package được repository scanning tìm thấy, thường là cùng package hoặc package con của repository interface. Hậu tố implementation mặc định là Impl. Có thể cấu hình repository implementation postfix nếu dự án dùng quy ước tên khác.

Không nên tạo một repository implementation tổng thể theo kiểu cũ nếu chỉ cần bổ sung một nhóm phương thức. Fragment interface và fragment implementation giúp tách từng phần mở rộng theo trách nhiệm, dễ kết hợp và dễ bảo trì hơn.

## 10. Gọi fragment từ service

Khi fragment đã được ghép vào ProductRepository, service chỉ cần inject repository:

    @Service
    public class ProductService {

        private final ProductRepository repository;

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        public SearchHits<Product> search(
                String keyword,
                Pageable pageable) {
            return repository.searchByName(keyword, pageable);
        }
    }

Service không cần biết truy vấn được thực hiện bằng NativeQuery hay CriteriaQuery. Chi tiết đó nằm trong ProductSearchImpl.

Lợi ích của cách tổ chức này:

- API repository phản ánh khả năng truy cập dữ liệu mà ứng dụng cần.
- Service không chứa nhiều chi tiết Elasticsearch Query DSL.
- Truy vấn tùy chỉnh có thể được dùng ở nhiều service thông qua cùng repository.
- Có thể thay đổi implementation mà không đổi cách gọi từ service.
- Có thể viết test riêng cho fragment và test tích hợp repository.

## 11. Fragment có thể dùng nhiều Operations method

Fragment không bị giới hạn ở search. Nó có thể dùng ElasticsearchOperations để xây dựng các truy vấn hoặc thao tác chuyên biệt.

Ví dụ, một fragment có thể cung cấp:

    public interface ProductCatalogOperations {

        SearchHits<Product> searchAvailable(
            String keyword,
            Pageable pageable
        );

        long countAvailable(String category);
    }

Implementation:

    public class ProductCatalogOperationsImpl
            implements ProductCatalogOperations {

        private final ElasticsearchOperations operations;

        public ProductCatalogOperationsImpl(
                ElasticsearchOperations operations) {
            this.operations = operations;
        }

        @Override
        public SearchHits<Product> searchAvailable(
                String keyword,
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
                    )
                )
                .withPageable(pageable)
                .build();

            return operations.search(query, Product.class);
        }

        @Override
        public long countAvailable(String category) {
            NativeQuery query = NativeQuery.builder()
                .withQuery(q -> q
                    .bool(b -> b
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
                .build();

            return operations.count(query, Product.class);
        }
    }

Repository có thể kế thừa fragment:

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String>,
                    ProductCatalogOperations {
    }

Ví dụ cho thấy fragment có thể đóng gói nhiều thao tác có liên quan vào một interface. Nên đặt tên fragment theo khả năng hoặc trách nhiệm, tránh gom mọi truy vấn không liên quan vào một class implementation lớn.

## 12. Nhiều repository fragment trong cùng repository

Một repository có thể ghép nhiều fragment:

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String>,
                    ProductSearch,
                    ProductCatalogOperations,
                    ProductExportOperations {
    }

Mỗi fragment có interface và implementation riêng:

    ProductSearch
        -> ProductSearchImpl

    ProductCatalogOperations
        -> ProductCatalogOperationsImpl

    ProductExportOperations
        -> ProductExportOperationsImpl

Các implementation có thể cùng inject ElasticsearchOperations. Điều này giữ mỗi trách nhiệm nhỏ và giúp service gọi một repository thống nhất.

Nếu hai fragment có phương thức cùng chữ ký hoặc có default method trùng nhau, cần thiết kế lại API hoặc quy định rõ cách composition để tránh xung đột. Không nên tạo các fragment có trách nhiệm chồng lấn chỉ để chia file.

## 13. Dùng CriteriaQuery thay cho NativeQuery

Không phải truy vấn nào cũng cần biểu diễn bằng Elasticsearch Query DSL. Với điều kiện đơn giản, CriteriaQuery có thể dễ đọc hơn.

Ví dụ trong fragment:

    Criteria criteria = new Criteria("status").is("ACTIVE")
        .and("category").is("accessories");

    Query query = new CriteriaQuery(criteria)
        .setPageable(pageable);

    return operations.search(query, Product.class);

CriteriaQuery phù hợp với những điều kiện filter hoặc query cơ bản. NativeQuery hữu ích khi cần các khả năng Elasticsearch chuyên sâu, query DSL cụ thể, nhiều clause lồng nhau hoặc tính năng mà Criteria API không biểu diễn thuận tiện.

Chọn API theo độ phức tạp và yêu cầu truy vấn. Không cần ép mọi truy vấn vào NativeQuery nếu CriteriaQuery đủ rõ; cũng không nên làm phức tạp CriteriaQuery khi query cần chính xác các semantics của Elasticsearch DSL.

## 14. Chọn kiểu kết quả phù hợp

ElasticsearchOperations cung cấp nhiều dạng kết quả. Chọn kiểu trả về theo thông tin mà tầng gọi cần:

| Kiểu kết quả | Khi nào dùng |
|---|---|
| List<T> | Chỉ cần danh sách entity |
| SearchHits<T> | Cần tổng số hit, score, highlight và metadata |
| SearchPage<T> | Cần kết quả search kết hợp thông tin phân trang |
| long từ count | Chỉ cần số document phù hợp |
| Từ get | Cần đọc một document theo id |

Ví dụ, nếu fragment trả SearchHits<Product>, service có thể xử lý:

    SearchHits<Product> hits =
        repository.searchByName(keyword, pageable);

    long total = hits.getTotalHits();

    List<Product> products = hits.getSearchHits()
        .stream()
        .map(SearchHit::getContent)
        .toList();

Nếu service chuyển ngay thành List<Product>, score và highlight sẽ không còn nằm trong kiểu dữ liệu trả về. Hãy giữ SearchHits khi giao diện hoặc logic xếp hạng cần metadata đó.

## 15. Chỉ định index hoặc alias rõ ràng

Thông thường entity có @Document với indexName và Spring Data sử dụng thông tin đó để xác định index. Nếu một truy vấn cần nhắm đến index hoặc alias khác, có thể truyền IndexCoordinates vào overload tương ứng của operations:

    SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
    );

Điều này hữu ích khi:

- Dùng alias ổn định trỏ đến index vật lý theo phiên bản.
- Có nhiều index cùng ánh xạ về một entity.
- Một tác vụ quản trị cần truy vấn index cụ thể.

Không nên hardcode tên index vật lý vào nhiều service. Nếu ứng dụng dùng alias, hãy để cấu hình hoặc metadata phù hợp quyết định tên logic, đồng thời bảo đảm mapping giữa các index phía sau alias tương thích với entity.

## 16. Khi nào không nên đưa truy vấn vào repository fragment?

Fragment phù hợp với logic truy cập dữ liệu có thể tái sử dụng. Tuy nhiên, không phải toàn bộ nghiệp vụ đều nên đặt trong repository.

Nên giữ trong service khi:

- Truy vấn chỉ phục vụ một use case và cần phối hợp nhiều nguồn dữ liệu.
- Kết quả cần áp dụng quy tắc nghiệp vụ hoặc kết hợp nhiều repository.
- Truy vấn là một bước trong quy trình dài hơn, không phải API dữ liệu có thể tái sử dụng.

Nên dùng fragment khi:

- Nhiều service cần cùng một truy vấn phức tạp.
- Muốn repository có API rõ ràng cho tìm kiếm tùy chỉnh.
- Có nhiều thao tác Elasticsearch liên quan cùng một miền dữ liệu.
- Muốn cô lập chi tiết NativeQuery/CriteriaQuery khỏi tầng nghiệp vụ.

Repository nên tập trung vào việc truy cập dữ liệu. Không nên đặt gửi email, gọi hệ thống thanh toán hoặc điều phối quy trình nghiệp vụ dài vào fragment chỉ vì các thao tác đó bắt đầu từ một truy vấn.

## 17. Kiểm thử service và fragment

Constructor injection giúp kiểm thử đơn vị dễ hơn.

Với service inject ElasticsearchOperations, có thể mock interface để kiểm tra service tạo query và xử lý kết quả. Tuy nhiên, test mock không xác minh Elasticsearch thực sự hiểu query như mong muốn.

Với repository fragment, có thể:

- Unit test implementation bằng mock ElasticsearchOperations.
- Integration test repository với Elasticsearch phù hợp phiên bản.
- Kiểm tra mapping, analyzer, query DSL và dữ liệu mẫu.
- Kiểm tra phân trang, sort, filter và trường hợp không có kết quả.

Ví dụ test cấu trúc service:

    @ExtendWith(MockitoExtension.class)
    class ProductSearchServiceTest {

        @Mock
        ElasticsearchOperations operations;

        @InjectMocks
        ProductSearchService service;

        // Stub operations.search(...) and verify the service behavior.
    }

Đây chỉ là khung minh họa. Khi mock phương thức nhận Query, có thể dùng ArgumentCaptor để lấy query và xác nhận các điều kiện cần thiết. Integration test vẫn cần thiết khi muốn xác minh analyzer, mapping và semantics của Elasticsearch.

## 18. Các lưu ý về package scanning và implementation naming

Spring Data cần tìm thấy fragment implementation để ghép vào repository proxy.

Với cấu hình mặc định:

- Repository interface nằm trong package được Spring Data Elasticsearch scan.
- Fragment interface được repository kế thừa.
- Implementation class theo tên fragment interface cộng hậu tố Impl.
- Implementation nằm trong package được repository infrastructure tìm kiếm.

Ví dụ:

    com.example.catalog.repository
        ProductRepository.java
        ProductSearch.java
        ProductSearchImpl.java

Nếu implementation không được tìm thấy, ứng dụng có thể báo lỗi khi tạo repository bean hoặc không ghép được fragment như mong đợi. Hãy kiểm tra base package của @EnableElasticsearchRepositories, tên implementation và hậu tố được cấu hình.

Nếu dùng nhiều repository package, có thể cấu hình:

    @EnableElasticsearchRepositories(
        basePackages = "com.example.catalog.repository"
    )

Trong ứng dụng Spring Boot, repository scanning có thể đã được cấu hình tự động theo package của application class. Chỉ thêm @EnableElasticsearchRepositories khi cần kiểm soát phạm vi scanning hoặc dùng cấu hình repository riêng.

Không nên đăng ký implementation fragment thành một bean độc lập bằng nhiều cơ chế trùng lặp nếu Spring Data đã tự phát hiện implementation theo quy ước. Tránh tạo hai bean có cùng vai trò dẫn đến ambiguity.

## 19. Nhiều ElasticsearchOperations hoặc nhiều cluster

Một ứng dụng có thể kết nối nhiều Elasticsearch cluster. Khi đó có thể có nhiều bean ElasticsearchOperations. Nếu chỉ inject theo type, Spring có thể không xác định được bean phù hợp.

Có thể dùng qualifier:

    @Service
    public class ProductSearchService {

        private final ElasticsearchOperations catalogOperations;

        public ProductSearchService(
                @Qualifier("catalogOperations")
                ElasticsearchOperations catalogOperations) {
            this.catalogOperations = catalogOperations;
        }
    }

Tên bean và cấu hình cụ thể phụ thuộc vào cách ứng dụng khai báo từng client/template. Nên đặt tên bean theo mục đích hoặc cluster, tránh các tên chung chung khó phân biệt.

Repository fragment cũng có thể cần qualifier khi inject nhiều operations:

    public class ProductSearchImpl implements ProductSearch {

        private final ElasticsearchOperations operations;

        public ProductSearchImpl(
                @Qualifier("catalogOperations")
                ElasticsearchOperations operations) {
            this.operations = operations;
        }
    }

Đảm bảo fragment dùng đúng operations tương ứng với cluster chứa index products. Việc query nhầm cluster có thể tạo ra lỗi index không tồn tại hoặc trả kết quả khác với mong đợi.

## 20. Không dùng ElasticsearchOperations đồng bộ trong luồng reactive

ElasticsearchOperations là API đồng bộ. Nếu ứng dụng dùng Spring WebFlux và cần xử lý non-blocking, không nên gọi operations đồng bộ trực tiếp trên event-loop thread.

Trong ứng dụng reactive, hãy cân nhắc ReactiveElasticsearchOperations và các API trả về Mono/Flux:

    public class ProductReactiveService {

        private final ReactiveElasticsearchOperations operations;

        public ProductReactiveService(
                ReactiveElasticsearchOperations operations) {
            this.operations = operations;
        }
    }

ReactiveElasticsearchOperations là abstraction khác với ElasticsearchOperations. Không thể chỉ đổi kiểu trả về thành Mono để biến một lời gọi blocking thành non-blocking.

Nếu buộc phải gọi thư viện blocking trong pipeline reactive, cần cô lập phần blocking trên scheduler phù hợp, nhưng đó chỉ là giải pháp tích hợp. Với hệ thống WebFlux, nên giữ reactive API xuyên suốt tầng truy cập dữ liệu.

## 21. Những lỗi thường gặp

### Tự tạo ElasticsearchTemplate trong service

Việc tự khởi tạo template làm service phụ thuộc cấu hình client, có thể tạo connection pool dư thừa và bỏ qua bean mà Spring đã quản lý. Hãy inject ElasticsearchOperations.

### Dùng field injection

Field injection làm phụ thuộc khó nhìn thấy và khó kiểm thử hơn. Dùng constructor injection để khai báo rõ bean cần thiết.

### Đưa mọi truy vấn vào service

Nếu nhiều service lặp lại cùng một query phức tạp, code dễ phân tán và không nhất quán. Hãy cân nhắc repository fragment cho truy vấn dữ liệu có thể tái sử dụng.

### Đưa toàn bộ nghiệp vụ vào repository fragment

Fragment nên đóng gói thao tác truy cập dữ liệu. Quy tắc nghiệp vụ, điều phối nhiều nguồn và xử lý use case vẫn thuộc service.

### Quên kế thừa fragment trong repository chính

Có interface ProductSearch và implementation ProductSearchImpl chưa đủ. ProductRepository phải extends ProductSearch để Spring Data ghép fragment vào repository.

### Đặt sai tên hoặc package implementation

Nếu tên implementation không khớp hậu tố hoặc nằm ngoài phạm vi repository scanning, fragment có thể không được phát hiện. Kiểm tra tên class, package và cấu hình basePackages.

### Inject nhầm operations khi có nhiều cluster

Khi có nhiều bean cùng kiểu, dùng @Qualifier để xác định rõ cluster/operations cần dùng.

### Dùng SearchHits nhưng bỏ qua metadata

Nếu ứng dụng cần score, highlight hoặc total hits, đừng chuyển ngay thành List entity rồi bỏ thông tin tìm kiếm.

### Gọi operations đồng bộ trên event loop

Trong WebFlux, lời gọi blocking có thể làm nghẽn event loop. Dùng ReactiveElasticsearchOperations cho luồng reactive.

## Kết luận

ElasticsearchOperations là abstraction phù hợp khi cần xây dựng truy vấn và thao tác Elasticsearch linh hoạt hơn các repository method thông thường. Inject operations vào service giúp use case kiểm soát truy vấn tại nơi điều phối nghiệp vụ. Inject operations vào repository fragment giúp đóng gói truy vấn tùy chỉnh thành API repository có thể tái sử dụng.

Với fragment, hãy khai báo interface, cho repository chính kế thừa interface đó và cung cấp implementation theo quy ước tên để Spring Data ghép vào repository proxy. Cả service và fragment nên dùng constructor injection, phụ thuộc vào ElasticsearchOperations và để Spring quản lý client/template. Chọn service hay fragment dựa trên phạm vi tái sử dụng của truy vấn, giữ nghiệp vụ ở service, kiểm soát package scanning và dùng ReactiveElasticsearchOperations nếu ứng dụng cần I/O reactive.
