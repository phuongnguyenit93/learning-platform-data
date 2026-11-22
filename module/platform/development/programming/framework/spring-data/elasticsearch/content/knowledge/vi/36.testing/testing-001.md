# Phân biệt kiểm thử dịch vụ và tích hợp Repository

Trong ứng dụng Spring Data Elasticsearch, service và repository đảm nhiệm hai phần việc khác nhau. Service điều phối nghiệp vụ: kiểm tra điều kiện, kết hợp dữ liệu, quyết định thứ tự thao tác và chuyển kết quả thành phản hồi của ứng dụng. Repository chuyển các thao tác lưu/đọc/xóa thành request Elasticsearch thông qua mapping, query derivation và client.

Vì trách nhiệm khác nhau, hai lớp cần được kiểm thử ở những mức khác nhau:

- **Service unit test:** cô lập service bằng cách mock repository hoặc dependency bên ngoài. Mục tiêu là xác minh quy tắc nghiệp vụ và cách service phản ứng với kết quả/lỗi từ dependency.
- **Repository integration test:** chạy với một Elasticsearch thực tế, thường qua Testcontainers, để xác minh mapping, serialization, query, CRUD, refresh và hành vi thực của Elasticsearch.

Một service test có thể pass dù query repository sai vì repository đã được mock. Một repository integration test có thể pass dù service áp dụng sai quy tắc nghiệp vụ vì nó không kiểm tra toàn bộ orchestration của service. Hai loại test bổ sung cho nhau.

## 1. Phân chia trách nhiệm cần kiểm thử

Ví dụ luồng tạo sản phẩm:

```text
HTTP Controller
      |
      v
ProductService
  - kiểm tra SKU đã tồn tại chưa
  - quyết định có cho tạo mới không
  - gọi repository.save(...)
  - chuyển entity thành response
      |
      v
ProductRepository
  - ánh xạ entity thành document
  - tạo request Elasticsearch
  - thực thi Get/Search/Index/Delete
      |
      v
Elasticsearch
  - mapping và analyzer
  - lưu document
  - refresh/search visibility
```

Service unit test nên tập trung vào các quyết định trong `ProductService`. Repository integration test nên tập trung vào việc `ProductRepository` và Elasticsearch phối hợp đúng như thế nào.

| Khía cạnh | Service unit test | Repository integration test |
|---|---|---|
| Dependency repository | Mock hoặc fake. | Repository thật do Spring tạo. |
| Elasticsearch instance | Không cần. | Cần Elasticsearch thật hoặc môi trường tương đương. |
| Mapping `@Field`, `@Id`, `@Document` | Không xác minh. | Có thể xác minh mapping và serialization thực tế. |
| Query method derivation | Không xác minh query thực thi. | Xác minh kết quả query trên index thật. |
| `NativeQuery`, CriteriaQuery | Chỉ có thể kiểm tra cách service gọi API hoặc query builder thuần. | Xác minh query DSL và kết quả thực tế. |
| Quy tắc nghiệp vụ | Trọng tâm. | Chỉ được kiểm tra nếu test đi qua service. |
| Refresh/search visibility | Không xác minh semantics Elasticsearch. | Có thể kiểm thử trực tiếp. |
| Tốc độ | Nhanh, chạy nhiều lần. | Chậm hơn do khởi động container/index. |
| Lỗi được phát hiện | Nhánh nghiệp vụ, mapping response, xử lý empty/error ở service. | Mapping sai, query sai, lỗi client/configuration, semantics Elasticsearch. |

## 2. Ví dụ cấu trúc service và repository

Giả sử ứng dụng có entity sản phẩm:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products-it")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String status;

    // constructors, getters, setters
}
```

Repository:

```java
import java.util.Optional;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    Optional<Product> findBySku(String sku);
}
```

Service:

```java
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product register(Product product) {
        if (repository.findBySku(product.getSku()).isPresent()) {
            throw new DuplicateProductSkuException(product.getSku());
        }

        return repository.save(product);
    }

    public Product getRequired(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new ProductNotFoundException(id));
    }
}
```

Trong ví dụ, service quyết định SKU trùng thì từ chối và ID không tồn tại thì báo lỗi. Repository chỉ cung cấp thao tác lưu và đọc. Đây là ranh giới phù hợp để tách test.

## 3. Service unit test: mock repository

Service unit test không cần khởi động Spring context hoặc Elasticsearch. Dùng JUnit và Mockito để tạo dependency giả, sau đó kiểm tra hành vi của service.

Ví dụ với JUnit 5 và Mockito:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.when;

import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class ProductServiceTest {

    @Mock
    private ProductRepository repository;

    @InjectMocks
    private ProductService service;

    @Test
    void registerSavesWhenSkuDoesNotExist() {
        Product input = new Product(null, "SKU-100", "Keyboard", "ACTIVE");
        Product saved = new Product("P-100", "SKU-100", "Keyboard", "ACTIVE");

        when(repository.findBySku("SKU-100")).thenReturn(Optional.empty());
        when(repository.save(input)).thenReturn(saved);

        Product result = service.register(input);

        assertThat(result.getId()).isEqualTo("P-100");
        verify(repository).findBySku("SKU-100");
        verify(repository).save(input);
    }

    @Test
    void registerRejectsDuplicateSku() {
        Product input = new Product(null, "SKU-100", "Keyboard", "ACTIVE");
        Product existing = new Product("P-001", "SKU-100", "Old keyboard", "ACTIVE");

        when(repository.findBySku("SKU-100")).thenReturn(Optional.of(existing));

        assertThatThrownBy(() -> service.register(input))
                .isInstanceOf(DuplicateProductSkuException.class);

        verify(repository, never()).save(input);
    }

    @Test
    void getRequiredThrowsWhenIdDoesNotExist() {
        when(repository.findById("P-404")).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.getRequired("P-404"))
                .isInstanceOf(ProductNotFoundException.class);
    }
}
```

Các test này kiểm tra ba nhánh nghiệp vụ:

- SKU chưa tồn tại: service gọi save và trả entity được lưu.
- SKU đã tồn tại: service ném lỗi nghiệp vụ và không gọi save.
- ID không tồn tại: service chuyển `Optional.empty()` thành `ProductNotFoundException`.

Không cần `@SpringBootTest`, không cần container và không cần kết nối Elasticsearch. Test chạy nhanh vì chỉ kiểm tra logic service.

### 3.1. Mock đúng ranh giới

Mock repository ở service test là hợp lý vì repository là dependency bên ngoài ranh giới service. Không nên mock chính service đang kiểm thử hoặc mock mọi method nội bộ khiến test chỉ xác nhận implementation hiện tại.

Ví dụ, nếu mục tiêu là kiểm tra service từ chối SKU trùng, chỉ cần mock kết quả `findBySku`. Không cần dựng mapping, index hoặc query Elasticsearch trong test này.

### 3.2. Kiểm tra kết quả và side effect

Nên ưu tiên assertion về kết quả nghiệp vụ:

- Response/entity trả về có đúng ID/trạng thái không?
- Có ném đúng domain exception không?
- Khi điều kiện không thỏa, thao tác ghi có bị bỏ qua không?
- Khi dependency trả empty/error, service xử lý ra sao?

`verify(...)` hữu ích khi một side effect là phần quan trọng của hợp đồng, ví dụ không được gọi save khi SKU trùng. Không nên verify mọi lời gọi nội bộ một cách máy móc vì test sẽ dễ hỏng khi refactor mà hành vi bên ngoài không đổi.

### 3.3. Mock exception từ repository

Service cần phản ứng đúng khi Elasticsearch không khả dụng:

```java
@Test
void registerPropagatesPersistenceFailure() {
    Product input = new Product(null, "SKU-100", "Keyboard", "ACTIVE");

    when(repository.findBySku("SKU-100")).thenReturn(Optional.empty());
    when(repository.save(input)).thenThrow(
            new ElasticsearchAccessException("Unavailable", new RuntimeException())
    );

    assertThatThrownBy(() -> service.register(input))
            .isInstanceOf(ElasticsearchAccessException.class);
}
```

Đây là kiểm tra phản ứng của service với lỗi dependency. Nó không xác minh Elasticsearch thật có phát sinh đúng exception type đó hay không; điều này thuộc repository integration test hoặc test adapter.

## 4. Vì sao service test không chứng minh repository hoạt động?

Trong service test, Mockito thay repository thật bằng một object giả. Khi test viết:

```java
when(repository.findBySku("SKU-100"))
        .thenReturn(Optional.of(product));
```

Mockito trả kết quả đã khai báo mà không gửi query đến Elasticsearch. Do đó test không phát hiện được các lỗi như:

- `sku` bị mapping thành `text` thay vì `keyword`.
- Tên field trong query không khớp mapping.
- Derived query `findBySku` không tạo truy vấn như mong muốn.
- `@Id` không ánh xạ đúng `_id`.
- Converter serialize/deserialize sai kiểu dữ liệu.
- Index chưa được tạo hoặc ứng dụng trỏ sai index/alias.
- Custom routing bị thiếu.
- Search chưa refresh nên chưa nhìn thấy document mới.
- Native query DSL không hợp lệ với phiên bản Elasticsearch đang chạy.

Service test vẫn có giá trị, nhưng câu hỏi nó trả lời là “service có điều phối đúng khi repository trả kết quả X không?”, không phải “repository có truy vấn đúng trên Elasticsearch không?”.

## 5. Repository integration test: dùng Elasticsearch thật

Repository integration test cần một Elasticsearch instance tương thích với client và Spring Data version của dự án. Testcontainers giúp khởi chạy Elasticsearch trong Docker và tự quản lý vòng đời container.

Dependencies minh họa cho Gradle:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:elasticsearch'
}
```

Version Testcontainers nên được quản lý bằng BOM hoặc dependency management của dự án. Elasticsearch image nên chọn phiên bản tương thích với Spring Data Elasticsearch/Elasticsearch Java Client mà ứng dụng đang sử dụng; không nên tự động dùng `latest` vì có thể tạo ra thay đổi không kiểm soát trong test.

### 5.1. Khởi chạy Elasticsearch bằng Testcontainers

Ví dụ integration test dùng JUnit 5:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.elasticsearch.ElasticsearchContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class ProductRepositoryIT {

    @Container
    static final ElasticsearchContainer elasticsearch =
            new ElasticsearchContainer(
                    DockerImageName.parse(
                            "docker.elastic.co/elasticsearch/elasticsearch:8.15.0"
                    )
            ).withEnv("xpack.security.enabled", "false");

    @DynamicPropertySource
    static void elasticsearchProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.elasticsearch.uris", elasticsearch::getHttpHostAddress);
    }

    @Autowired
    ProductRepository repository;

    @Autowired
    ElasticsearchOperations operations;

    @BeforeEach
    void prepareIndex() {
        IndexOperations index = operations.indexOps(Product.class);
        index.delete();
        index.createWithMapping();
    }
}
```

Đây là cấu hình minh họa. Tên property kết nối, cách bật/tắt security, package container và phiên bản Elasticsearch cần khớp với Spring Boot, Testcontainers và Spring Data đang dùng. Một số phiên bản Elasticsearch yêu cầu cấu hình password/TLS thay vì tắt security; trong môi trường production-like test, nên kiểm thử với cấu hình bảo mật tương ứng.

`@SpringBootTest` khởi tạo application context thật, do đó Spring Data tạo repository proxy và cấu hình client. Test sẽ đi qua repository thật tới Elasticsearch trong container.

### 5.2. Vì sao cần tạo lại index?

Mỗi test nên bắt đầu từ trạng thái dữ liệu đã biết. Ví dụ trên xóa index test rồi tạo lại mapping từ entity để tránh dữ liệu hoặc mapping của test trước ảnh hưởng test sau.

`createWithMapping()` yêu cầu Spring Data tạo index và mapping từ metadata entity. Nếu dự án quản lý mapping bằng JSON template hoặc migration riêng, integration test nên tạo index theo đúng cơ chế production thay vì vô tình kiểm thử một mapping khác.

Nếu test chạy song song, việc xóa/tạo cùng một index có thể gây xung đột. Khi đó cần index riêng cho mỗi test/class hoặc tắt parallel execution cho nhóm test dùng chung index.

## 6. Kiểm thử CRUD qua repository thật

Sau khi index đã được tạo, có thể kiểm tra save, get, search và delete:

```java
import static org.assertj.core.api.Assertions.assertThat;

@Test
void savesAndReadsProductById() {
    Product input = new Product("P-100", "SKU-100", "Keyboard", "ACTIVE");

    Product saved = repository.save(input);

    Product loaded = repository.findById("P-100").orElseThrow();

    assertThat(saved.getId()).isEqualTo("P-100");
    assertThat(loaded.getSku()).isEqualTo("SKU-100");
    assertThat(loaded.getName()).isEqualTo("Keyboard");
}

@Test
void deletesProductById() {
    repository.save(new Product("P-200", "SKU-200", "Mouse", "ACTIVE"));

    repository.deleteById("P-200");

    assertThat(repository.findById("P-200")).isEmpty();
}
```

Các assertion này đi qua repository và Elasticsearch thật. `findById` sử dụng Get API, có real-time semantics theo mặc định.

### 6.1. Kiểm thử derived query

Derived query cần được xác minh bằng search thực:

```java
@Test
void findsProductBySku() {
    repository.save(new Product("P-300", "SKU-300", "Headphones", "ACTIVE"));

    operations.indexOps(Product.class).refresh();

    Optional<Product> found = repository.findBySku("SKU-300");

    assertThat(found).isPresent();
    assertThat(found.orElseThrow().getName()).isEqualTo("Headphones");
}
```

`findBySku` là Search API nên test refresh index trước khi tìm để không phụ thuộc timing refresh nền. Test này xác minh tên property, mapping và query derivation cùng hoạt động trên Elasticsearch.

### 6.2. Kiểm thử search và delete

```java
@Test
void deletesDocumentAndRemovesItFromSearchResultsAfterRefresh() {
    repository.save(new Product("P-400", "SKU-400", "Monitor", "ACTIVE"));
    operations.indexOps(Product.class).refresh();

    assertThat(repository.findBySku("SKU-400")).isPresent();

    repository.deleteById("P-400");
    operations.indexOps(Product.class).refresh();

    assertThat(repository.findBySku("SKU-400")).isEmpty();
}
```

Ở đây refresh sau delete để xác minh trạng thái Search API. Nếu chỉ gọi `findById` sau delete, Get API real-time có thể trả empty mà không cần refresh.

## 7. Kiểm thử mapping và serialization

Repository integration test là nơi phù hợp để phát hiện mapping annotation không đúng.

Ví dụ entity khai báo:

```java
@Field(type = FieldType.Keyword)
private String sku;
```

Test có thể xác minh:

- Index được tạo với field `sku` là `keyword`.
- Document được serialize đúng tên field.
- Giá trị được deserialize về entity đúng kiểu.
- Field `@Id` được lưu thành `_id` và đọc lại đúng.
- Các field date, numeric, geo, nested hoặc join có mapping đúng.

Có thể đọc mapping qua:

```java
Map<String, Object> mapping = operations.indexOps(Product.class).getMapping();
assertThat(mapping).isNotNull();
```

Assertion cụ thể nên dựa trên cấu trúc mapping mà Spring Data/Elasticsearch version trả về, thay vì so sánh toàn bộ JSON dạng chuỗi dễ bị ảnh hưởng bởi thứ tự field hoặc format.

Nếu mapping được quản lý bằng file JSON/template riêng, hãy kiểm tra mapping thực tế trên index sau khi tạo. Việc entity có annotation đúng không bảo đảm index cũ đã được cập nhật nếu index đã tồn tại trước đó.

## 8. Kiểm thử `NativeQuery` và CriteriaQuery

Khi repository có custom fragment dùng `ElasticsearchOperations`, integration test nên xác minh query trên Elasticsearch thật.

Ví dụ fragment:

```java
public interface ProductSearchFragment {
    List<Product> searchActiveByKeyword(String keyword);
}
```

Implementation:

```java
public class ProductSearchFragmentImpl implements ProductSearchFragment {

    private final ElasticsearchOperations operations;

    public ProductSearchFragmentImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<Product> searchActiveByKeyword(String keyword) {
        Query query = new CriteriaQuery(
                new Criteria("name").matches(keyword)
                        .and("status").is("ACTIVE")
        );

        return operations.search(query, Product.class)
                .stream()
                .map(SearchHit::getContent)
                .toList();
    }
}
```

Integration test:

```java
@Test
void customSearchFragmentExecutesAgainstElasticsearch() {
    repository.save(new Product("P-501", "SKU-501", "Mechanical Keyboard", "ACTIVE"));
    repository.save(new Product("P-502", "SKU-502", "Mechanical Keyboard Case", "INACTIVE"));
    operations.indexOps(Product.class).refresh();

    List<Product> results = repository.searchActiveByKeyword("keyboard");

    assertThat(results)
            .extracting(Product::getId)
            .contains("P-501")
            .doesNotContain("P-502");
}
```

Ví dụ này xác minh custom fragment được ghép vào repository proxy, query thực sự chạy và filter status có tác dụng. Nếu chỉ mock `ElasticsearchOperations`, test sẽ không phát hiện lỗi field name hoặc DSL.

### 8.1. Unit test riêng cho query builder

Nếu query phức tạp và được xây dựng trong một class thuần, có thể tách phần tạo query thành function/builder để unit test các nhánh điều kiện.

Ví dụ:

```java
Query buildProductQuery(String keyword, String status) {
    // Return a Query based on the input criteria.
}
```

Unit test có thể kiểm tra builder thêm filter nào trong từng trường hợp. Nhưng việc query builder tạo ra DSL đúng cú pháp và đúng semantics vẫn cần ít nhất một repository integration test với Elasticsearch thật.

## 9. Kiểm thử service và repository cùng nhau

Ngoài service unit test và repository integration test, có thể có một số service integration test chạy toàn bộ service + repository + Elasticsearch.

Ví dụ:

```java
@Test
void registerRejectsExistingSkuUsingRealRepository() {
    repository.save(new Product("P-900", "SKU-900", "Existing", "ACTIVE"));
    operations.indexOps(Product.class).refresh();

    assertThatThrownBy(() -> productService.register(
            new Product(null, "SKU-900", "Duplicate", "ACTIVE")
    )).isInstanceOf(DuplicateProductSkuException.class);
}
```

Test này xác minh quy tắc service kết hợp với query repository thực. Nó có phạm vi lớn hơn unit test và chậm hơn, nhưng hữu ích cho một số luồng quan trọng.

Không cần chạy mọi nhánh service qua Elasticsearch thật. Giữ phần lớn logic nghiệp vụ ở unit test để test nhanh, rồi chọn một số luồng tích hợp quan trọng để xác nhận các tầng phối hợp.

## 10. Phân biệt `@SpringBootTest` và test slice

`@SpringBootTest` tạo application context theo cấu hình ứng dụng. Nó hữu ích khi cần kiểm thử repository cùng các bean/configuration thực tế, nhưng có thể khởi động nhiều thành phần hơn mức cần thiết.

Test slice giới hạn phạm vi context vào một nhóm thành phần. Nếu phiên bản Spring Boot/Spring Data của dự án cung cấp slice phù hợp cho Elasticsearch, có thể dùng để giảm thời gian khởi động. Tên annotation và auto-configuration được hỗ trợ phụ thuộc phiên bản; hãy kiểm tra danh sách test slice của đúng Spring Boot release.

Nếu không có slice phù hợp hoặc cần xác minh cấu hình ứng dụng đầy đủ, `@SpringBootTest` kết hợp Testcontainers là lựa chọn rõ ràng.

Không dùng `@DataJpaTest` để kiểm thử Elasticsearch repository. Đây là slice cho JPA và không cấu hình Elasticsearch infrastructure.

## 11. Testcontainers và cấu hình kết nối

Một cấu hình integration test cần bảo đảm Spring Boot kết nối đến container thay vì một Elasticsearch local hoặc production endpoint.

Ví dụ cấu hình property động:

```java
@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("spring.elasticsearch.uris", elasticsearch::getHttpHostAddress);
}
```

Tên property thường dùng ở Spring Boot hiện đại là `spring.elasticsearch.uris`; các bản cũ có thể dùng prefix khác. Nếu ứng dụng cần username/password/TLS, đăng ký các property tương ứng từ container hoặc test configuration.

Một số lưu ý:

- Pin Elasticsearch image version thay vì dùng `latest`.
- Chọn version tương thích với Spring Data Elasticsearch và Java API Client.
- Không trỏ integration test đến cluster dùng chung có dữ liệu thật.
- Dùng container riêng để test có thể xóa/tạo index mà không ảnh hưởng người khác.
- Nếu container security bật, cấu hình credential và certificate theo đúng version.
- Chờ container healthy trước khi application context tạo client.

## 12. Cô lập dữ liệu giữa các test

Elasticsearch không tự rollback dữ liệu test như một transaction database thông thường. `@Transactional` không mặc nhiên xóa document đã index khi test kết thúc.

Các chiến lược cô lập:

### 12.1. Tạo lại index cho từng test

Xóa index, tạo mapping mới trong `@BeforeEach`. Cách này tạo trạng thái sạch nhưng có thể tốn thời gian và không phù hợp nếu nhiều test chạy song song trên cùng index.

### 12.2. Dùng ID duy nhất cho từng test

Tạo ID có prefix test/run để tránh trùng:

```java
String id = "it-" + UUID.randomUUID();
```

Sau test, xóa document theo ID và refresh nếu cần. Cách này phù hợp khi dùng chung index trong một test class nhưng cần cleanup cẩn thận.

### 12.3. Index riêng cho từng suite

Dùng index tên riêng như `products-repository-it`. Điều này tách dữ liệu test khỏi index dev hoặc local khác. Với parallel test, có thể tạo tên index theo class/test run và truyền `IndexCoordinates` tương ứng nếu repository/operations cho phép cấu hình động.

### 12.4. Không phụ thuộc thứ tự test

Mỗi test phải tự chuẩn bị dữ liệu nó cần. Không viết test B dựa vào document do test A tạo. Nếu test chạy riêng lẻ hoặc thứ tự thay đổi, kết quả vẫn phải giống nhau.

## 13. Refresh và tính nhất quán trong integration test

Get theo ID là real-time theo mặc định; Search API là near-real-time. Đây là nguyên nhân phổ biến khiến repository integration test chập chờn.

Ví dụ không ổn định:

```java
repository.save(product);
assertThat(repository.findBySku(product.getSku())).isPresent();
```

`findBySku` là search query. Nếu chưa refresh, test có thể không thấy document.

Cách rõ ràng:

```java
repository.save(product);
operations.indexOps(Product.class).refresh();

assertThat(repository.findBySku(product.getSku())).isPresent();
```

Không dùng `Thread.sleep(1000)` để đợi refresh. Sleep phụ thuộc timing, tải máy và cấu hình index. Hãy gọi refresh tường minh hoặc dùng refresh policy `WAIT_UNTIL` khi test cần kiểm tra write visibility.

### 13.1. Kiểm thử GET và Search khác nhau

Nếu muốn kiểm tra đúng semantics:

1. Tạo index với refresh interval được kiểm soát, ví dụ tắt auto refresh trong test.
2. Save document.
3. `findById` có thể đọc document ngay.
4. Derived search query có thể chưa thấy document.
5. Refresh index.
6. Search query nhìn thấy document.

Việc tắt refresh interval phải được cấu hình đúng với version/API đang dùng và khôi phục nếu test dùng index lâu dài. Đối với phần lớn repository test, refresh tường minh trước query là đủ; chỉ tạo test riêng khi cần xác minh near-real-time behavior.

## 14. Kiểm thử custom routing

Nếu entity dùng `@Routing` hoặc repository operations có custom routing, integration test cần xác minh cả index và get/search.

Ví dụ:

```java
@Document(indexName = "orders-it")
@Routing("routing")
public class OrderDocument {
    @Id
    private String id;
    private String routing;
    private String customerId;
}
```

Test nên:

1. Index document với routing value cụ thể.
2. Đọc theo ID với cùng routing và xác nhận tìm thấy.
3. Thử đọc không có hoặc routing khác để xác minh hành vi dự kiến.
4. Kiểm tra repository/service giữ routing nhất quán qua save/get/delete.

Mock `ElasticsearchOperations` không xác minh request thực sự có routing parameter. Đây là lý do cần integration test cho custom routing.

## 15. Kiểm thử aggregation, nested và geo query

Các tính năng Elasticsearch phụ thuộc mapping và engine behavior, nên cần test tích hợp:

- Aggregation: bucket count, metric value, pipeline aggregation.
- Nested query: path và mối quan hệ giữa các field trong cùng nested object.
- Geo query: `geo_point`, bán kính và sort distance.
- Join/parent-child: join mapping, routing và `has_child`/`has_parent`.
- Analyzer: tokenization, lowercase, stemming hoặc synonym.
- Highlight/suggest: response metadata và field mapping.

Service test có thể xác minh rằng service gọi custom repository với tham số phù hợp, nhưng chỉ Elasticsearch integration test mới xác minh được query/mapping có semantics đúng.

## 16. Kiểm thử lỗi và timeout ở các tầng

Service unit test:

- Mock repository ném lỗi timeout hoặc unavailable.
- Xác minh service chuyển lỗi thành domain exception hoặc fallback đúng.
- Xác minh không retry lỗi validation hoặc lỗi nghiệp vụ.
- Xác minh retry policy được áp dụng đúng nếu service sở hữu retry.

Repository integration test:

- Kiểm tra mapping rejection với dữ liệu không hợp lệ.
- Kiểm tra query lỗi hoặc index không tồn tại khi đó là kịch bản cần hỗ trợ.
- Kiểm tra timeout/connection behavior nếu có môi trường mô phỏng phù hợp.
- Kiểm tra optimistic concurrency/version conflict nếu repository custom dùng sequence number/version.

Không cố tình làm hỏng cluster dùng chung để kiểm thử lỗi hạ tầng. Dùng container riêng hoặc test double ở ranh giới network/client khi cần mô phỏng outage.

## 17. Reactive service test và repository integration test

Nếu ứng dụng dùng `ReactiveElasticsearchRepository`, nguyên tắc phân tầng vẫn giống nhau:

- Service unit test mock reactive repository trả `Mono`/`Flux`.
- Repository integration test dùng reactive repository thật kết nối Elasticsearch thật.
- Dùng `StepVerifier` để kiểm tra tín hiệu và thứ tự publisher.
- Dùng refresh tường minh khi test search visibility.

Ví dụ service unit test:

```java
when(repository.findBySku("SKU-1")).thenReturn(Mono.just(product));

StepVerifier.create(service.findRequired("SKU-1"))
        .expectNext(product)
        .verifyComplete();
```

Ví dụ repository integration test:

```java
StepVerifier.create(repository.save(product))
        .expectNextMatches(saved -> saved.getId().equals(product.getId()))
        .verifyComplete();

StepVerifier.create(operations.indexOps(Product.class).refresh())
        .verifyComplete();

StepVerifier.create(repository.findBySku(product.getSku()))
        .expectNextMatches(found -> found.getId().equals(product.getId()))
        .verifyComplete();
```

Các ví dụ dùng Reactor Test. Không gọi `.block()` trong service/controller để làm test dễ hơn; test có thể dùng StepVerifier để subscribe và xác minh publisher.

## 18. Phân biệt mock, fake, embedded và Testcontainers

| Cách kiểm thử | Có Elasticsearch thật? | Phù hợp với |
|---|---|---|
| Mock repository | Không. | Service unit test. |
| Fake repository in-memory | Không. | Logic service cần một implementation giả đơn giản. |
| Mock `ElasticsearchOperations` | Không. | Service/custom adapter unit test; xác minh interaction ở mức API. |
| Embedded Elasticsearch cũ | Tùy giải pháp, thường không phản ánh production version. | Không nên chọn làm mặc định nếu không tương thích version. |
| Testcontainers Elasticsearch | Có, chạy trong container. | Repository integration test và service integration test. |
| Elasticsearch test cluster dùng chung | Có. | Chỉ khi có quản lý dữ liệu/namespace chặt chẽ; dễ gây ảnh hưởng lẫn nhau. |

Testcontainers thường là lựa chọn thực tế vì version có thể pin, môi trường được cô lập và test có thể chạy trong CI có Docker/container runtime.

## 19. Chọn mức test theo loại câu hỏi

| Câu hỏi cần trả lời | Test phù hợp |
|---|---|
| SKU trùng thì service có từ chối không? | Service unit test. |
| Repository trả empty thì service có ném NotFound không? | Service unit test. |
| Elasticsearch unavailable thì API/service phản ứng thế nào? | Service unit test với lỗi giả; thêm integration/contract test nếu cần xác minh exception thực. |
| `findBySku` có tạo query đúng không? | Repository integration test. |
| `@Field(Keyword)` có tạo mapping đúng không? | Repository integration test. |
| Entity có serialize/deserialize đúng không? | Repository integration test. |
| Search sau save có thấy document sau refresh không? | Repository integration test. |
| `NativeQuery` aggregation trả đúng bucket không? | Repository integration test. |
| Custom routing có được gửi đúng không? | Repository integration test. |
| Service + repository phối hợp đúng trên một luồng quan trọng không? | Chọn lọc service integration test. |

Không cần kiểm tra tất cả mọi thứ ở mọi tầng. Đặt assertion tại tầng sở hữu hành vi để test rõ nguyên nhân khi thất bại.

## 20. Tổ chức source test

Một cấu trúc đơn giản:

```text
src
├── main
│   └── java/com/example/catalog
│       ├── product
│       │   ├── Product.java
│       │   ├── ProductRepository.java
│       │   └── ProductService.java
│       └── ...
└── test
    └── java/com/example/catalog
        ├── product
        │   ├── ProductServiceTest.java
        │   ├── ProductRepositoryIT.java
        │   └── ProductServiceIT.java
        └── support
            └── ElasticsearchTestContainerConfiguration.java
```

Tên `IT` thường được dùng cho integration test, nhưng Gradle/Maven không nhất thiết tự chạy mọi class có hậu tố đó theo cấu hình mặc định. Hãy cấu hình test task/source set hoặc plugin phù hợp để integration test thực sự được chạy trong CI.

Có thể tách task:

```groovy
tasks.named('test') {
    useJUnitPlatform()
    exclude '**/*IT.class'
}

tasks.register('integrationTest', Test) {
    useJUnitPlatform()
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    include '**/*IT.class'
    shouldRunAfter tasks.test
}
```

Đây là cấu hình Gradle minh họa; dự án có thể dùng source set riêng, plugin convention hoặc task khác. Điều quan trọng là pipeline CI phân biệt test nhanh và test cần container, đồng thời vẫn chạy integration test ở giai đoạn thích hợp.

## 21. Tránh các anti-pattern trong kiểm thử

### 21.1. Mock repository trong test được gọi là repository integration test

Nếu repository bị mock thì test không kiểm tra Elasticsearch. Hãy đặt tên test theo đúng phạm vi: service unit test hoặc service orchestration test.

### 21.2. Dùng Elasticsearch thật cho mọi nhánh service

Việc này làm test chậm, khó setup và khó xác định lỗi nghiệp vụ. Dùng mock cho phần lớn nhánh service; chỉ chọn các luồng tích hợp cần thiết.

### 21.3. Chỉ kiểm tra HTTP status

Repository integration test cần kiểm tra document/query thực tế, không chỉ xác nhận request không ném exception. Ví dụ, query trả 0 kết quả vẫn có thể là request hợp lệ nhưng sai field name.

### 21.4. Dựa vào dữ liệu còn lại từ test trước

Test phụ thuộc thứ tự sẽ chập chờn khi chạy riêng, chạy song song hoặc trên CI. Chuẩn bị và dọn dữ liệu rõ ràng.

### 21.5. Dùng sleep để chờ refresh

Sleep không đồng bộ với Elasticsearch. Dùng refresh API hoặc refresh policy `WAIT_UNTIL`.

### 21.6. Coi `@Transactional` sẽ rollback Elasticsearch

Không mặc định Elasticsearch repository tham gia transaction rollback như JPA. Test cần xóa index/document hoặc dùng namespace riêng.

### 21.7. Dùng version `latest` cho container

Kết quả test có thể thay đổi khi image được cập nhật. Pin phiên bản và nâng version có chủ đích.

## 22. Ví dụ ma trận test cho ProductService/ProductRepository

| Test case | Service unit | Repository integration | Service integration |
|---|:---:|:---:|:---:|
| SKU đã tồn tại thì từ chối tạo | Có | Không bắt buộc | Có thể chọn lọc |
| SKU chưa tồn tại thì gọi save | Có | CRUD save riêng | Có thể chọn lọc |
| `findById` ánh xạ `_id` đúng | Không | Có | Không bắt buộc |
| `findBySku` query đúng field | Không | Có | Không bắt buộc |
| Field `sku` mapping là keyword | Không | Có | Không bắt buộc |
| Elasticsearch timeout được map thành domain error | Có, với exception mock | Có thể kiểm tra adapter/client | Có thể chọn lọc |
| Save rồi search sau refresh | Không | Có | Có thể chọn lọc |
| Custom routing được truyền đúng | Không | Có | Có thể chọn lọc |
| Query aggregation trả metric đúng | Không | Có | Không bắt buộc |
| API trả status/error body đúng | Controller/web test | Không bắt buộc | Có thể dùng WebTestClient/MockMvc với context phù hợp |

Ma trận giúp tránh việc một test bị giao nhiệm vụ xác minh nhiều tầng cùng lúc. Khi lỗi xảy ra, nhóm phát triển dễ xác định cần xem service, mapping, query hay cấu hình client.

## 23. Quy trình xây dựng bộ test

1. **Xác định trách nhiệm service:** liệt kê rule, nhánh điều kiện, lỗi và side effect.
2. **Viết service unit test:** mock repository và kiểm tra kết quả nghiệp vụ.
3. **Xác định hợp đồng repository:** mapping, query method, custom fragment, routing và semantics cần xác minh.
4. **Chuẩn bị Elasticsearch test environment:** dùng Testcontainers với version pin phù hợp.
5. **Tạo index/mapping:** dùng cùng mapping strategy với production.
6. **Viết repository integration test:** kiểm tra CRUD, query, serialization, refresh và các tính năng Elasticsearch được sử dụng.
7. **Cô lập dữ liệu:** tạo lại index hoặc dùng ID/index riêng; không dựa vào thứ tự test.
8. **Thêm service integration test có chọn lọc:** xác minh các luồng quan trọng từ service đến repository thật.
9. **Tách task CI:** chạy unit test nhanh thường xuyên và integration test trong pipeline có container.
10. **Giữ test xác định:** pin version, refresh tường minh, tránh sleep và cleanup rõ ràng.

## 24. Những điểm cần nhớ

- Service unit test kiểm tra nghiệp vụ và orchestration; repository integration test kiểm tra tương tác thực với Elasticsearch.
- Mock repository trong service test giúp test nhanh và cô lập, nhưng không xác minh mapping/query/serialization.
- Repository integration test cần repository proxy thật và Elasticsearch thật hoặc môi trường tương thích.
- Testcontainers giúp khởi chạy Elasticsearch có version pin và cô lập dữ liệu cho CI.
- Kiểm tra `@Document`, `@Id`, `@Field`, mapping, query derivation, `NativeQuery`, custom routing và converter ở tầng integration.
- Get theo ID có real-time semantics; search query near-real-time nên refresh rõ ràng trong test.
- Không dùng `Thread.sleep` để chờ refresh và không giả định `@Transactional` rollback dữ liệu Elasticsearch.
- Dùng unique ID, index riêng hoặc tạo lại index để test không phụ thuộc nhau.
- Test service + repository cùng nhau chỉ cần cho một số luồng quan trọng; không thay thế unit test nhanh.
- Pin Elasticsearch image version tương thích với Spring Data/Java API Client.
- Đặt test ở đúng tầng để lỗi thất bại cho biết chính xác trách nhiệm nào đang có vấn đề.

Service unit test và repository integration test trả lời hai câu hỏi khác nhau. Mock repository giúp xác minh service ra quyết định đúng khi dependency trả về kết quả hoặc lỗi cụ thể; Elasticsearch integration test xác minh repository thực sự ánh xạ và truy vấn dữ liệu đúng trên engine. Kết hợp hai tầng một cách có chủ đích tạo bộ test nhanh, đáng tin cậy và đủ khả năng phát hiện lỗi cả ở nghiệp vụ lẫn tích hợp.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Testing](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/testing.html)
- [Spring Data Elasticsearch — Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/repositories.html)
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Testcontainers — Elasticsearch Module](https://java.testcontainers.org/modules/elasticsearch/)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Mockito Documentation](https://javadoc.io/doc/org.mockito/mockito-core/latest/org/mockito/Mockito.html)
