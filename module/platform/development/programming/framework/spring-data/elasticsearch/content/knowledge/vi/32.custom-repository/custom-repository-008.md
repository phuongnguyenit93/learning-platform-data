# Kiểm thử fragment và cấu hình Repository thực tế

Spring Data Elasticsearch cho phép mở rộng repository bằng các fragment tùy biến. Một repository có thể kết hợp các method do Spring Data sinh tự động với những method do ứng dụng triển khai, chẳng hạn tìm sản phẩm đang hoạt động, áp dụng quy tắc tìm kiếm riêng hoặc phối hợp nhiều thao tác Elasticsearch.

Một fragment chỉ hoạt động đúng khi Spring Data phát hiện được interface, implementation và ghép chúng vào repository. Vì vậy, kiểm thử method tùy biến bằng cách gọi trực tiếp implementation chưa đủ. Ứng dụng còn cần xác nhận repository scanning, tên implementation, package, template được inject, mapping entity và kết nối Elasticsearch thực tế đều được cấu hình đúng.

Bài học này trình bày cách tổ chức fragment, kiểm thử riêng logic fragment, kiểm thử quá trình Spring lắp ghép repository, dựng Elasticsearch thật cho integration test và xử lý các lỗi cấu hình thường gặp.

## 1. Repository fragment là gì?

Spring Data repository có thể bao gồm nhiều phần chức năng. Một phần được cung cấp bởi framework, phần khác được thêm bằng interface fragment và class implementation do ứng dụng viết.

Ví dụ repository sản phẩm cần:

- **findById** và **save** do ElasticsearchRepository cung cấp.
- **findByStatus** do derived query tạo từ tên method.
- **findActiveProducts** do ứng dụng triển khai bằng fragment.
- Một truy vấn tìm kiếm phức tạp dùng ElasticsearchOperations.

Có thể hình dung cấu trúc:

~~~text
ProductRepository
       |
       +---- ElasticsearchRepository<Product, String>
       |          |
       |          +---- CRUD và query methods của Spring Data
       |
       +---- ProductSearchFragment
                  |
                  +---- ProductSearchFragmentImpl
                             |
                             +---- ElasticsearchOperations
~~~

Repository chính chỉ cần kế thừa interface fragment. Spring Data tìm implementation phù hợp và kết hợp nó vào proxy repository được tạo khi khởi động application context.

Fragment giúp tách truy vấn tùy biến khỏi repository interface lớn, đồng thời cho phép tái sử dụng cùng một hành vi ở nhiều repository nếu thiết kế phù hợp.

## 2. Tạo interface cho fragment

Ví dụ fragment cung cấp method tìm sản phẩm đang active:

~~~java
public interface ProductSearchFragment {

    List<Product> findActiveProducts();

    List<Product> searchByNameAndStatus(
        String name,
        String status
    );
}
~~~

Interface mô tả hành vi mà repository sẽ cung cấp. Nó không cần kế thừa Repository hoặc ElasticsearchRepository.

Repository chính kết hợp fragment với repository Spring Data:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchFragment {

    List<Product> findByStatus(String status);
}
~~~

Sau khi Spring Data tạo repository proxy, caller có thể dùng CRUD, derived query và method fragment trên cùng một bean:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public List<Product> getActiveProducts() {
        return repository.findActiveProducts();
    }
}
~~~

Không cần inject riêng ProductSearchFragmentImpl vào service. Ứng dụng nên phụ thuộc vào repository interface được compose.

## 3. Đặt tên và vị trí implementation

Theo cơ chế fragment composition hiện đại, implementation class thường dùng tên interface fragment cộng với repository implementation postfix. Với postfix mặc định Impl:

| Fragment interface | Implementation class |
|---|---|
| ProductSearchFragment | ProductSearchFragmentImpl |
| InventoryRepositoryFragment | InventoryRepositoryFragmentImpl |
| ProductStatistics | ProductStatisticsImpl |

Ví dụ:

~~~java
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    private final ElasticsearchOperations operations;

    public ProductSearchFragmentImpl(
            ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<Product> findActiveProducts() {
        // Query implementation
        return List.of();
    }

    @Override
    public List<Product> searchByNameAndStatus(
            String name,
            String status) {
        // Query implementation
        return List.of();
    }
}
~~~

Implementation phải nằm trong phạm vi package mà cơ chế repository implementation discovery có thể tìm thấy theo cấu hình. Cách tổ chức đơn giản là đặt fragment interface, implementation và repository interface trong cùng package hoặc trong cấu trúc package được quy ước rõ ràng.

Tên class sai postfix, sai package hoặc không khớp fragment interface là những nguyên nhân phổ biến khiến Spring không ghép implementation.

### Fragment implementation khác legacy repository implementation

Các phiên bản Spring Data cũ thường được hướng dẫn tạo class theo tên repository, ví dụ ProductRepositoryImpl. Cơ chế này là kiểu custom repository implementation legacy.

Với fragment composition, nên tạo interface fragment riêng và implementation theo tên fragment. Cách này rõ ràng hơn khi repository có nhiều nhóm method tùy biến và giúp tái sử dụng fragment.

Không trộn hai quy ước đặt tên nếu không có lý do cụ thể. Khi nâng cấp Spring Data, kiểm tra lại quy ước discovery mà phiên bản đang dùng hỗ trợ.

## 4. Cài đặt fragment bằng ElasticsearchOperations

ElasticsearchOperations cung cấp API imperative để tạo query, đọc kết quả, index và cập nhật document. Fragment có thể inject operations qua constructor.

Ví dụ entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Boolean)
    private boolean active;

    // constructors, getters and setters
}
~~~

Implementation:

~~~java
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    private final ElasticsearchOperations operations;

    public ProductSearchFragmentImpl(
            ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<Product> findActiveProducts() {
        Query query = new CriteriaQuery(
            new Criteria("active").is(true)
        );

        SearchHits<Product> hits =
            operations.search(query, Product.class);

        return hits.getSearchHits().stream()
            .map(SearchHit::getContent)
            .toList();
    }

    @Override
    public List<Product> searchByNameAndStatus(
            String name,
            String status) {

        Criteria criteria = new Criteria("name").matches(name)
            .and("status").is(status);

        Query query = new CriteriaQuery(criteria);

        SearchHits<Product> hits =
            operations.search(query, Product.class);

        return hits.getSearchHits().stream()
            .map(SearchHit::getContent)
            .toList();
    }
}
~~~

Ví dụ dùng Criteria để minh họa fragment gọi Operations. Với truy vấn full-text phức tạp, có thể thay bằng NativeQuery và Java API Client builder. API Criteria và NativeQuery cụ thể cần khớp phiên bản Spring Data Elasticsearch của dự án.

### Vì sao implementation không nên tự tạo client?

Nếu ứng dụng đã cấu hình ElasticsearchOperations, hãy inject bean đó thay vì tự khởi tạo một client mới trong fragment. Như vậy fragment dùng cùng:

- Connection và authentication.
- Converter và entity mapping.
- IndexCoordinates.
- Client timeout và cấu hình liên quan.
- Cơ chế quan sát/logging đã được cấu hình cho application.

Tạo client riêng trong fragment có thể khiến production và test dùng cấu hình khác nhau, đồng thời làm vòng đời resource khó quản lý.

## 5. Dùng fragment với nhiều repository

Một fragment có thể được dùng bởi nhiều repository nếu hành vi không phụ thuộc chặt vào một entity hoặc index duy nhất.

Ví dụ fragment tìm kiếm theo trạng thái:

~~~java
public interface StatusSearchFragment<T> {

    List<T> findByStatus(String status);
}
~~~

Tuy nhiên, generic fragment cần implementation và cách xác định entity type rõ ràng. Nếu implementation phải biết Class<T>, index hoặc mapping cụ thể, cần thiết kế constructor/metadata phù hợp với cơ chế fragment composition.

Trong nhiều ứng dụng, fragment chuyên biệt theo aggregate dễ hiểu và ít rủi ro hơn việc xây một generic fragment quá tổng quát.

Không chia sẻ một fragment chỉ vì hai repository có method cùng tên. Chỉ dùng chung khi semantics, mapping và yêu cầu kết quả thực sự giống nhau.

## 6. Repository scanning và cấu hình thực tế

Spring Data cần biết package nào chứa repository interface và template nào sẽ thực thi repository đó.

Trong ứng dụng Spring Boot, auto-configuration thường tạo client, converter và template dựa trên application properties. Nếu dùng cấu hình repository tường minh, có thể khai báo:

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository",
    repositoryImplementationPostfix = "Impl"
)
public class ElasticsearchRepositoryConfiguration {
}
~~~

basePackages phải bao gồm package của ProductRepository. Postfix cần khớp tên implementation fragment. Nếu dùng template riêng, annotation có thuộc tính tham chiếu template tương ứng; tên thuộc tính và bean name cần đối chiếu phiên bản Spring Data đang cài.

Không khai báo nhiều cấu hình repository scanning chồng lấn cùng một package nếu không có chủ đích. Việc scan trùng có thể tạo bean definition conflict hoặc khiến repository được gắn với template không mong muốn.

### Khi nào cần @EnableElasticsearchRepositories?

Dùng annotation này khi cần kiểm soát rõ package scanning hoặc cấu hình repository ngoài auto-configuration mặc định. Trong ứng dụng Boot đơn giản, có thể để auto-configuration phát hiện repository từ package gốc của application class.

Nếu repository nằm ngoài package scan mặc định, hãy mở rộng package scan hoặc cấu hình EnableElasticsearchRepositories tường minh.

### Phân biệt template imperative và reactive

Spring Data Elasticsearch có các API imperative và reactive:

- ElasticsearchRepository dùng mô hình imperative.
- ReactiveElasticsearchRepository dùng mô hình reactive.
- ElasticsearchOperations là API imperative.
- ReactiveElasticsearchOperations là API reactive.

Fragment imperative nên inject ElasticsearchOperations. Fragment reactive nên inject ReactiveElasticsearchOperations và trả về Mono/Flux.

Không inject reactive operations vào fragment imperative rồi gọi block() để biến nó thành đồng bộ. Cũng không dùng ElasticsearchOperations blocking trong reactive request path.

## 7. Cấu hình client và template cho ứng dụng

Repository proxy cần một template phù hợp để thực thi query. Trong Spring Boot, các property thường dùng để cấu hình endpoint nằm dưới prefix spring.elasticsearch, ví dụ:

~~~yaml
spring:
  elasticsearch:
    uris: http://localhost:9200
~~~

Tùy phiên bản và môi trường, có thể cần cấu hình username, password, TLS hoặc các tùy chọn client khác. Không đưa secret production vào file cấu hình được commit.

Nếu tự cấu hình thay vì dùng Boot auto-configuration, cần đảm bảo các bean client, converter, template và repository scanning tương thích với cùng một phiên bản Spring Data Elasticsearch/Elasticsearch Java API Client.

Không tạo một template giả hoặc mock trong production configuration chỉ để repository khởi động. Integration test cần kiểm tra cấu hình tương tự application thật.

### Nhiều cluster hoặc nhiều template

Một ứng dụng có thể kết nối nhiều Elasticsearch cluster hoặc dùng nhiều template. Khi đó, mỗi nhóm repository phải gắn đúng template và client tương ứng.

Cần đặt tên bean rõ ràng, ví dụ:

- catalogElasticsearchOperations
- analyticsElasticsearchOperations
- catalogElasticsearchClient
- analyticsElasticsearchClient

Cấu hình repository scanning phải tham chiếu đúng template bean. Tránh dựa vào bean Primary khi repository cần kết nối cluster cụ thể; khai báo rõ ràng sẽ dễ kiểm tra hơn.

## 8. Kiểm thử fragment độc lập bằng unit test

Unit test fragment tập trung vào logic của implementation và cách nó gọi ElasticsearchOperations. Không cần khởi động Spring context hoặc Elasticsearch thật nếu chỉ kiểm tra việc xây query và chuyển kết quả.

Có thể dùng Mockito để mock Operations và SearchHits.

~~~java
@ExtendWith(MockitoExtension.class)
class ProductSearchFragmentImplTest {

    @Mock
    ElasticsearchOperations operations;

    @Mock
    SearchHits<Product> searchHits;

    @Mock
    SearchHit<Product> searchHit;

    @Test
    void returnsActiveProducts() {
        Product product = new Product();
        product.setId("P-100");
        product.setActive(true);

        when(searchHit.getContent()).thenReturn(product);
        when(searchHits.getSearchHits())
            .thenReturn(List.of(searchHit));
        when(operations.search(
            any(Query.class),
            eq(Product.class)
        )).thenReturn(searchHits);

        ProductSearchFragmentImpl fragment =
            new ProductSearchFragmentImpl(operations);

        List<Product> result = fragment.findActiveProducts();

        assertThat(result).containsExactly(product);
        verify(operations).search(
            any(Query.class),
            eq(Product.class)
        );
    }
}
~~~

Đây là skeleton kiểm thử. Constructor entity, kiểu Query và overload search cần khớp phiên bản đang dùng.

Unit test này chứng minh implementation chuyển SearchHits thành entity list và gọi Operations. Nó không chứng minh Spring Data phát hiện fragment hoặc repository proxy được compose đúng.

### Kiểm tra nội dung query

Nếu điều kiện query là phần quan trọng của logic, đừng chỉ verify any(Query.class). Có thể dùng ArgumentCaptor<Query> để bắt query được gửi:

~~~java
ArgumentCaptor<Query> queryCaptor =
    ArgumentCaptor.forClass(Query.class);

verify(operations).search(
    queryCaptor.capture(),
    eq(Product.class)
);

Query actualQuery = queryCaptor.getValue();
~~~

Sau đó kiểm tra loại query, Criteria hoặc cấu trúc query được tạo theo API phù hợp. Nếu query object khó kiểm tra trực tiếp, có thể kiểm tra hành vi bằng integration test với Elasticsearch.

## 9. Kiểm thử Spring repository composition

Một integration test quan trọng là khởi động Spring context, inject repository interface và gọi method fragment thông qua repository proxy.

Điều này xác nhận đồng thời:

- Repository package được scan.
- Interface fragment được nhận diện.
- Implementation class được tìm thấy.
- Constructor dependency được inject.
- Repository proxy kết hợp CRUD, derived query và fragment.
- Template đúng được dùng.

Ví dụ cấu trúc test:

~~~java
@SpringBootTest
class ProductRepositoryCompositionTest {

    @Autowired
    ProductRepository repository;

    @Test
    void repositoryContainsCustomFragment() {
        List<Product> products =
            repository.findActiveProducts();

        assertThat(products).isNotNull();
    }
}
~~~

Nếu fragment không được phát hiện, context có thể thất bại khi khởi động hoặc method fragment không có implementation. Test này phát hiện lỗi wiring mà unit test implementation không thể thấy.

Để xác nhận kết quả nghiệp vụ, test cần index dữ liệu có kiểm soát trước khi gọi method, thay vì chỉ kiểm tra danh sách khác null.

## 10. Dùng Testcontainers để kiểm thử Elasticsearch thật

Elasticsearch có semantics riêng về mapping, analyzer, Query DSL, refresh và version compatibility. Mock ElasticsearchOperations không thể xác nhận các hành vi đó.

Testcontainers có thể khởi động Elasticsearch trong Docker cho integration test. Chọn image version tương thích với Spring Data Elasticsearch và Java API Client mà dự án đang dùng. Không dùng tag latest, vì version mới có thể thay đổi behavior hoặc không tương thích dependency.

Ví dụ cấu trúc với JUnit 5 và Testcontainers:

~~~java
@Testcontainers
@SpringBootTest
class ProductRepositoryIntegrationTest {

    @Container
    static final ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer(
            DockerImageName.parse(
                "docker.elastic.co/elasticsearch/elasticsearch:8.17.0"
            )
        ).withEnv("xpack.security.enabled", "false");

    @DynamicPropertySource
    static void elasticsearchProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.elasticsearch.uris",
            elasticsearch::getHttpHostAddress
        );
    }

    @Autowired
    ProductRepository repository;

    @Autowired
    ElasticsearchOperations operations;
}
~~~

Đây là cấu trúc minh họa. Chọn image tag theo ma trận tương thích của dự án; nếu image hoặc Testcontainers version bật security mặc định, cấu hình username/password và TLS theo container thay vì tắt security. Một số bản Testcontainers Elasticsearch có cách cấu hình container khác nhau.

DynamicPropertySource cung cấp địa chỉ container trước khi Spring tạo client và template. Không khởi tạo repository trước khi endpoint đã được đăng ký.

### Không dùng Docker image tùy tiện

Image test nên gần với version Elasticsearch mà môi trường ứng dụng thực tế sử dụng. Nếu production chạy một phiên bản cụ thể, integration test nên chạy cùng major và tốt nhất cùng minor tương thích.

Một test pass với mock không bảo đảm query chạy trên Elasticsearch production. Ngược lại, một test với version khác xa có thể cho kết quả không đại diện.

## 11. Chuẩn bị index và dữ liệu cho integration test

Test cần tạo index có mapping đúng trước khi lưu document. Có thể dùng IndexOperations:

~~~java
@BeforeEach
void prepareIndex() {
    IndexOperations indexOperations =
        operations.indexOps(Product.class);

    if (indexOperations.exists()) {
        indexOperations.delete();
    }

    indexOperations.create();
    indexOperations.putMapping(
        indexOperations.createMapping(Product.class)
    );
}
~~~

Tên method và cách tạo mapping phụ thuộc phiên bản Spring Data Elasticsearch. Với dự án dùng alias hoặc index name động, test cần tạo đúng target mà repository thực sự sử dụng.

Sau đó lưu dữ liệu:

~~~java
Product first = new Product();
first.setId("P-100");
first.setName("Wireless Keyboard");
first.setStatus("ACTIVE");
first.setActive(true);

Product second = new Product();
second.setId("P-101");
second.setName("Office Mouse");
second.setStatus("ACTIVE");
second.setActive(false);

repository.saveAll(List.of(first, second));
~~~

Elasticsearch có refresh interval, vì vậy dữ liệu vừa index có thể chưa xuất hiện ngay trong search. Trong test, có thể refresh index trước khi truy vấn:

~~~java
operations.indexOps(Product.class).refresh();
~~~

Không dùng Thread.sleep tùy tiện để chờ dữ liệu. Hãy dùng refresh hoặc cơ chế đồng bộ rõ ràng của test.

### Xác nhận method fragment qua repository thật

~~~java
@Test
void customFragmentFindsOnlyActiveProducts() {
    List<Product> result =
        repository.findActiveProducts();

    assertThat(result)
        .extracting(Product::getId)
        .containsExactly("P-100");
}
~~~

Kết quả phụ thuộc dữ liệu seed và thứ tự trả về. Nếu query không có sort, đừng khẳng định thứ tự kết quả; dùng containsExactlyInAnyOrder khi thứ tự không thuộc contract.

## 12. Kiểm thử repository scanning và package boundaries

Một lỗi phổ biến là test class nằm trong package có thể scan repository, nhưng application thật lại khởi động từ package root khác. Vì vậy, test chỉ chạy qua configuration test không đảm bảo production scan giống nhau.

Kiểm tra:

- Application main class nằm ở package root phù hợp.
- Repository interface nằm trong package được scan.
- Fragment implementation nằm trong phạm vi discovery.
- EnableElasticsearchRepositories không chỉ vào nhầm package.
- Không có hai configuration scan cùng repository.
- Test không khai báo một Import làm che lỗi component scanning của production.
- Repository dùng đúng template bean.

Có thể viết một context test chỉ kiểm tra repository bean được tạo:

~~~java
@SpringBootTest
class RepositoryConfigurationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void productRepositoryBeanExists() {
        assertThat(context.getBean(ProductRepository.class))
            .isNotNull();
    }
}
~~~

Đây là kiểm tra wiring cơ bản. Integration test gọi một method fragment thực tế còn xác nhận implementation đã được gắn vào repository proxy.

## 13. Kiểm thử nhiều repository và nhiều template

Khi ứng dụng có nhiều nhóm repository, hãy kiểm tra từng nhóm được gắn đúng template.

Ví dụ:

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository",
    elasticsearchTemplateRef = "catalogElasticsearchTemplate"
)
class CatalogRepositoryConfiguration {
}
~~~

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.analytics.repository",
    elasticsearchTemplateRef = "analyticsElasticsearchTemplate"
)
class AnalyticsRepositoryConfiguration {
}
~~~

Tên thuộc tính template reference và kiểu template phải phù hợp với phiên bản Spring Data Elasticsearch đang dùng.

Trong integration test, tạo dữ liệu phân biệt ở mỗi cluster hoặc index. Gọi repository tương ứng và xác nhận dữ liệu không bị đọc nhầm từ template khác. Chỉ kiểm tra hai bean tồn tại là chưa đủ để xác nhận wiring đúng.

Nếu hai cấu hình scan cùng package, repository có thể bị đăng ký nhiều lần hoặc dùng template sai. Hãy chia package repository theo bounded context khi có nhiều cluster.

## 14. Kiểm thử reactive repository fragment

Nếu ứng dụng dùng reactive repository, fragment cũng phải giữ reactive contract.

Interface:

~~~java
public interface ReactiveProductSearchFragment {

    Flux<Product> findActiveProducts();
}
~~~

Implementation:

~~~java
public class ReactiveProductSearchFragmentImpl
        implements ReactiveProductSearchFragment {

    private final ReactiveElasticsearchOperations operations;

    public ReactiveProductSearchFragmentImpl(
            ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public Flux<Product> findActiveProducts() {
        Query query = new CriteriaQuery(
            new Criteria("active").is(true)
        );

        return operations.search(query, Product.class)
            .map(SearchHit::getContent);
    }
}
~~~

Repository:

~~~java
public interface ProductReactiveRepository
        extends ReactiveElasticsearchRepository<Product, String>,
                ReactiveProductSearchFragment {
}
~~~

Không gọi block() trong implementation reactive để lấy kết quả đồng bộ. Unit test có thể dùng StepVerifier, còn integration test nên khởi động reactive repository thực sự và gọi fragment method qua proxy.

Ví dụ:

~~~java
StepVerifier.create(repository.findActiveProducts())
    .expectNextMatches(Product::isActive)
    .thenCancel()
    .verify();
~~~

Nếu test cần xác nhận toàn bộ kết quả và Publisher hoàn tất, dùng expectNextCount, expectNextMatches và verifyComplete theo dữ liệu seed.

## 15. Phân biệt unit, slice và integration test

Ba cấp kiểm thử trả lời những câu hỏi khác nhau:

| Cấp kiểm thử | Thành phần chạy | Điều xác nhận |
|---|---|---|
| Unit test fragment | Implementation và mock Operations | Logic chuyển đổi, tham số và cách gọi dependency |
| Repository/context test | Spring application context và repository proxy | Fragment discovery, package scan, bean wiring |
| Integration test | Spring Data cùng Elasticsearch thật | Mapping, Query DSL, analyzer, refresh và kết quả thực tế |

Một bài test tốt không nhất thiết phải khởi động Elasticsearch cho mọi trường hợp. Dùng unit test cho logic nhỏ để chạy nhanh, rồi dùng một số integration test tập trung để xác nhận behavior của framework và cluster.

### @DataElasticsearchTest

Spring Boot cung cấp test slice DataElasticsearchTest trong các phiên bản hỗ trợ. Slice này tập trung vào thành phần Elasticsearch và có thể phù hợp khi muốn kiểm thử repository/template mà không khởi động toàn bộ ứng dụng.

Tuy nhiên, slice test có thể không nạp mọi service, configuration hoặc bean của application. Nếu custom fragment implementation phụ thuộc bean ngoài slice, cần import cấu hình cần thiết hoặc dùng SpringBootTest cho test wiring toàn ứng dụng.

Không giả định DataElasticsearchTest tự cung cấp một Elasticsearch server. Test vẫn cần endpoint Elasticsearch thật, chẳng hạn Testcontainers hoặc một môi trường test được quản lý riêng.

## 16. Kiểm thử mapping và Query DSL, không chỉ kiểm tra bean

Một repository bean khởi động thành công không chứng minh mapping đúng. Integration test nên xác nhận các field quan trọng có đúng type và query trả kết quả đúng.

Ví dụ:

- Field tên dùng text và analyzer mong muốn.
- Field trạng thái dùng keyword.
- Field boolean có mapping boolean.
- Nested collection được mapping nested khi cần giữ ranh giới object.
- Multi-field có subfield keyword nếu query exact hoặc sort dùng nó.
- Alias trỏ đến index có mapping tương thích.

Có thể kiểm tra mapping được tạo từ entity bằng IndexOperations hoặc gọi API mapping của Elasticsearch. Cách lấy mapping cụ thể phụ thuộc phiên bản.

Đối với analyzer, test dữ liệu với nhiều token, chữ hoa/thường, dấu tiếng Việt hoặc ký tự đặc biệt theo analyzer mà ứng dụng dùng. Không chỉ kiểm tra query trả về một document đơn giản.

## 17. Test data, isolation và chạy song song

Integration test cần dữ liệu độc lập để kết quả không phụ thuộc test chạy trước.

Các chiến lược:

- Xóa và tạo lại index trước mỗi test khi số test ít.
- Dùng index riêng theo test class hoặc test run.
- Dùng ID có prefix test để tránh va chạm.
- Dọn dữ liệu sau test khi index được chia sẻ.
- Tắt hoặc kiểm soát chạy song song nếu nhiều test cùng xóa một index.
- Với alias, tạo index đích riêng rồi gắn alias trong setup.

Không để test dùng chung index development hoặc production. Dữ liệu test phải được cô lập và có thể xóa an toàn.

Nếu nhiều test class dùng chung Testcontainers container, có thể giảm thời gian khởi động, nhưng vẫn cần isolation ở index và document ID. Nếu mỗi test class tạo container mới, thời gian chạy có thể tăng đáng kể.

## 18. Kiểm thử lỗi cấu hình repository

Nên có test hoặc ít nhất một lần khởi động application context trong CI để phát hiện:

- Fragment implementation thiếu constructor dependency.
- Sai tên implementation postfix.
- Repository package không được scan.
- Hai repository cùng tên bean.
- Template bean không tồn tại hoặc sai kiểu.
- Converter không có mapping metadata cần thiết.
- Client không kết nối được endpoint.
- Authentication hoặc TLS không đúng.
- Version Elasticsearch không tương thích.

Một số lỗi chỉ xuất hiện lúc khởi động; lỗi khác chỉ xuất hiện khi method repository được gọi. Vì vậy, test context và test thực thi method fragment đều cần thiết.

### Phân biệt lỗi wiring và lỗi kết nối

Nếu context báo không tìm thấy bean ElasticsearchOperations, đó là lỗi wiring/configuration. Nếu repository proxy được tạo nhưng request thất bại do connection refused, đó là lỗi kết nối endpoint.

Không xử lý cả hai bằng cách thêm mock bean vào integration test. Mock có thể che mất cấu hình production bị thiếu.

## 19. CI và môi trường chạy test

Để integration test ổn định trong CI:

- Pin phiên bản Elasticsearch container.
- Đảm bảo runner có Docker hoặc môi trường container tương thích.
- Chờ health check của container trước khi khởi động Spring context.
- Cấp đủ memory cho Elasticsearch test node.
- Dùng endpoint động từ Testcontainers, không hardcode localhost:9200.
- Không commit password hoặc certificate thật.
- Giới hạn test song song nếu chúng chia sẻ index.
- Lưu log container khi test thất bại.
- Tách unit test nhanh và integration test cần container thành task/nhóm phù hợp.

Nếu CI không hỗ trợ Docker, có thể dùng Elasticsearch test service được quản lý riêng. Khi đó, cần tạo index/namespace cô lập và đảm bảo pipeline cleanup dữ liệu sau khi chạy.

## 20. Những lỗi thường gặp khi kiểm thử fragment và repository config

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không tìm thấy fragment implementation | Sai tên class hoặc postfix | Kiểm tra tên interface + Impl và cấu hình postfix |
| Repository method fragment không có implementation | Fragment interface chưa được kế thừa | Thêm fragment interface vào repository |
| Constructor implementation không được inject | Dependency chưa là bean hoặc template không tồn tại | Kiểm tra Spring context và Operations bean |
| Unit test pass nhưng repository thật lỗi | Unit test gọi implementation trực tiếp | Thêm test qua repository proxy |
| Repository không được tạo | Sai basePackages hoặc application package scan | Kiểm tra repository scanning |
| Hai cấu hình tạo bean trùng | Package bị scan nhiều lần | Tách package và cấu hình một nơi |
| Repository dùng nhầm cluster | Template reference sai hoặc dựa vào Primary | Gắn rõ template theo repository group |
| Test không tìm thấy dữ liệu vừa lưu | Index chưa refresh | Refresh index trước search |
| Query chạy nhưng không có kết quả | Mapping hoặc analyzer không đúng | Kiểm tra mapping và Query DSL thực tế |
| Testcontainers không khởi động | Docker/port/memory hoặc image không phù hợp | Kiểm tra môi trường CI và pin image tương thích |
| Test flaky khi chạy song song | Nhiều test xóa/chia sẻ index | Tạo index riêng hoặc tuần tự hóa test |
| Slice test thiếu fragment bean | Slice không import cấu hình cần thiết | Import fragment config hoặc dùng SpringBootTest |
| Reactive test treo | Dùng block hoặc Publisher không được verify đúng | Dùng StepVerifier và giữ pipeline reactive |
| Test pass với mock nhưng production lỗi TLS | Mock bỏ qua client config | Integration test với cấu hình endpoint/auth tương ứng |

## 21. Ví dụ kịch bản kiểm thử hoàn chỉnh

Một bộ test cho ProductRepository nên xác nhận cả composition và behavior.

**Bước 1: Khởi động Elasticsearch test node**

Dùng Testcontainers với phiên bản phù hợp dependency. Đưa URI container vào Spring Environment trước khi client được tạo.

**Bước 2: Khởi động Spring context**

Dùng SpringBootTest hoặc DataElasticsearchTest phù hợp. Inject ProductRepository và ElasticsearchOperations.

**Bước 3: Tạo index và mapping**

Tạo index theo entity metadata hoặc dùng index template đã được ứng dụng quản lý. Xác nhận index được tạo đúng target.

**Bước 4: Seed dữ liệu**

Lưu ít nhất một sản phẩm active và một sản phẩm inactive với ID ổn định.

**Bước 5: Refresh index**

Refresh trước khi chạy search để test không phụ thuộc refresh interval.

**Bước 6: Gọi repository proxy**

Gọi repository.findActiveProducts() thay vì khởi tạo implementation trực tiếp. Xác nhận chỉ sản phẩm active được trả về.

**Bước 7: Kiểm tra CRUD và derived query**

Gọi findById, save và findByStatus để xác nhận phần Spring Data repository cơ bản hoạt động.

**Bước 8: Dọn dữ liệu**

Xóa index riêng của test hoặc xóa document theo ID. Không tác động index dùng chung ngoài test environment.

Ví dụ assertion:

~~~java
@Test
void repositoryCombinesCrudDerivedQueryAndFragment() {
    List<Product> active =
        repository.findActiveProducts();

    assertThat(active)
        .extracting(Product::getId)
        .containsExactly("P-100");

    assertThat(repository.findByStatus("ACTIVE"))
        .extracting(Product::getId)
        .contains("P-100");
}
~~~

Kết quả chính xác phụ thuộc seed data và sort. Nếu method không khai báo sort, không phụ thuộc thứ tự trả về.

## 22. Checklist kiểm thử repository tùy biến

- [ ] Mỗi nhóm hành vi tùy biến có fragment interface rõ ràng.
- [ ] Repository chính kế thừa đúng fragment interface.
- [ ] Implementation class tuân thủ naming postfix.
- [ ] Implementation nằm trong phạm vi discovery.
- [ ] Constructor inject đúng Operations hoặc ReactiveOperations.
- [ ] Repository scanning bao phủ package interface.
- [ ] Repository dùng đúng template bean.
- [ ] Không scan trùng package ngoài chủ đích.
- [ ] Unit test kiểm tra logic fragment và dependency interaction.
- [ ] Integration test gọi method qua repository proxy.
- [ ] Elasticsearch container được pin version tương thích.
- [ ] Test tạo mapping và index phù hợp entity.
- [ ] Test seed dữ liệu, refresh và xác nhận kết quả.
- [ ] Test phân biệt text, keyword, nested và mapping behavior cần thiết.
- [ ] Test isolation an toàn khi chạy song song.
- [ ] Test cấu hình nhiều repository/template nếu ứng dụng có nhiều cluster.
- [ ] Reactive fragment được kiểm tra bằng StepVerifier.
- [ ] CI có Docker/test service và cleanup phù hợp.
- [ ] Không dùng mock để che lỗi wiring hoặc lỗi kết nối trong integration test.

Kiểm thử fragment cần xác nhận hai điều: implementation thực hiện đúng hành vi và Spring Data thực sự ghép implementation đó vào repository proxy trong cấu hình ứng dụng. Unit test với mock giúp kiểm tra logic nhanh; context test xác nhận discovery và dependency injection; integration test với Elasticsearch thật xác nhận mapping, query và kết quả. Kết hợp ba cấp kiểm thử giúp phát hiện lỗi package scanning, postfix, template wiring và khác biệt giữa cấu hình test với ứng dụng thực tế.

