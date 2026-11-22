# Cấu hình ReactiveElasticsearchConfiguration và client reactive

Spring Data Elasticsearch cung cấp client reactive để ứng dụng gửi request tới Elasticsearch bằng Project Reactor. Thay vì trả kết quả đồng bộ, các API reactive thường trả về Mono hoặc Flux. Nhờ đó, service có thể ghép nhiều thao tác bất đồng bộ mà không cần chặn thread để chờ từng response.

Trong Spring Data Elasticsearch hiện hành, lớp cấu hình chính là ReactiveElasticsearchConfiguration thuộc package org.springframework.data.elasticsearch.client.elc. Lớp này tạo các bean cần thiết cho kết nối, gồm low-level Rest5Client, ElasticsearchTransport, ReactiveElasticsearchClient và ReactiveElasticsearchOperations. ReactiveElasticsearchTemplate là implementation mặc định của operations.

Bài này tập trung vào cách cấu hình client, chọn các tùy chọn kết nối, sử dụng template và repository reactive, tích hợp với Spring Boot, đồng thời giữ luồng xử lý không blocking từ HTTP endpoint đến Elasticsearch.

## 1. Reactive Elasticsearch là gì?

Reactive Elasticsearch cho phép ứng dụng làm việc với Elasticsearch bằng các publisher của Reactor:

- Mono<T>: phát ra tối đa một giá trị T, hoặc hoàn tất mà không có giá trị.
- Flux<T>: phát ra không hoặc nhiều giá trị T.
- ReactiveElasticsearchClient: client cấp thấp cung cấp các thao tác Elasticsearch theo kiểu reactive.
- ReactiveElasticsearchOperations: abstraction cấp cao để lưu, đọc, tìm kiếm, xóa và quản lý document.
- ReactiveElasticsearchTemplate: implementation mặc định của ReactiveElasticsearchOperations.
- Reactive Elasticsearch Repository: repository trả về Mono và Flux thay cho kiểu kết quả đồng bộ.

Một luồng điển hình:

~~~text
WebFlux Controller
       |
       v
Service trả Mono / Flux
       |
       v
ReactiveElasticsearchOperations
       |
       v
ReactiveElasticsearchTemplate
       |
       v
ReactiveElasticsearchClient
       |
       v
ElasticsearchTransport
       |
       v
Rest5Client
       |
       v
Elasticsearch cluster
~~~

Ứng dụng có thể dùng ReactiveElasticsearchOperations hoặc repository cho hầu hết nghiệp vụ. ReactiveElasticsearchClient cấp thấp hữu ích khi cần truy cập API cụ thể mà abstraction cấp cao chưa bao phủ.

Reactive không có nghĩa mọi đoạn code trong ứng dụng tự động chạy trên một thread riêng. Mục tiêu chính là không giữ thread chờ I/O. Khi dùng đúng cách, thread có thể xử lý công việc khác trong lúc chờ Elasticsearch phản hồi.

## 2. ReactiveElasticsearchConfiguration

Lớp ReactiveElasticsearchConfiguration là base configuration để tạo kết nối Elasticsearch theo reactive stack.

Import chính:

~~~java
import org.springframework.data.elasticsearch.client.elc.ReactiveElasticsearchConfiguration;
~~~

Lớp này yêu cầu ứng dụng cung cấp ClientConfiguration thông qua method clientConfiguration(). Từ cấu hình đó, Spring Data tạo các bean cần thiết:

| Bean | Vai trò |
| --- | --- |
| ClientConfiguration | Địa chỉ cluster, SSL, authentication, timeout, headers và các tùy chọn HTTP. |
| Rest5Client | HTTP client cấp thấp được Elasticsearch Java Client sử dụng trong stack hiện hành. |
| ElasticsearchTransport | Kết nối transport và JSON mapper với low-level client. |
| JsonpMapper | Chuyển đổi JSON cho Elasticsearch Java API Client. |
| ReactiveElasticsearchClient | Client reactive được Spring Data dùng để gửi request. |
| ReactiveElasticsearchOperations | API cấp cao để thao tác với document; implementation mặc định là ReactiveElasticsearchTemplate. |

Bean operations/template được đăng ký với tên reactiveElasticsearchOperations và reactiveElasticsearchTemplate. Repository reactive sử dụng operations này ở bên dưới.

### 2.1. Cấu hình tối thiểu

Ví dụ kết nối tới Elasticsearch chạy local:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ReactiveElasticsearchConfiguration;
import org.springframework.data.elasticsearch.repository.config.EnableReactiveElasticsearchRepositories;

@Configuration
@EnableReactiveElasticsearchRepositories(
        basePackages = "com.example.catalog.repository"
)
public class ElasticsearchReactiveConfiguration
        extends ReactiveElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
                .connectedTo("localhost:9200")
                .build();
    }
}
~~~

Giải thích:

- @Configuration đăng ký class này như một Spring configuration.
- @EnableReactiveElasticsearchRepositories kích hoạt quét repository reactive trong package được chỉ định.
- ReactiveElasticsearchConfiguration cung cấp hạ tầng client và template.
- clientConfiguration() mô tả cách kết nối tới cluster.
- Không cần tự tạo ReactiveElasticsearchClient hoặc ReactiveElasticsearchTemplate nếu dùng cấu hình base class này.

Nếu repository nằm cùng package hoặc package con của configuration class, có thể bỏ basePackages. Trong dự án lớn, khai báo package rõ ràng giúp kiểm soát phạm vi quét.

### 2.2. Không nhầm với AbstractReactiveElasticsearchConfiguration

Các ví dụ cũ có thể sử dụng AbstractReactiveElasticsearchConfiguration và ReactiveRestClients. Đây là API thuộc thế hệ client reactive legacy.

Trong Spring Data Elasticsearch hiện hành, dùng ReactiveElasticsearchConfiguration trong package client.elc. Với Spring Data 6.x, client RestClient cũ đã bị deprecated; cấu hình hiện hành dùng Rest5Client và Elasticsearch Java Client transport.

| API | Thế hệ | Ghi chú |
| --- | --- | --- |
| ReactiveElasticsearchConfiguration | Client ELC hiện hành | Base class cấu hình reactive client. |
| ReactiveElasticsearchLegacyRestClientConfiguration | Legacy client | Dùng khi cần duy trì low-level RestClient cũ. |
| AbstractReactiveElasticsearchConfiguration | API reactive cũ | Không nên sao chép nguyên ví dụ cũ vào dự án dùng client hiện hành. |
| ReactiveRestClients | API legacy | Không nhầm với ReactiveElasticsearchClient hiện hành. |

Khi nâng cấp Spring Data Elasticsearch, cần kiểm tra package import và loại low-level client đang được cấu hình. Không trộn class của client legacy với Elasticsearch Java API Client.

## 3. ClientConfiguration và các tùy chọn kết nối

ClientConfiguration mô tả các thông số kết nối mà ReactiveElasticsearchConfiguration sử dụng để tạo client.

Các tùy chọn thường dùng:

| Tùy chọn | Mục đích |
| --- | --- |
| connectedTo | Một hoặc nhiều địa chỉ node Elasticsearch. |
| usingSsl | Bật HTTPS/TLS. |
| withBasicAuth | Cấu hình HTTP Basic Authentication. |
| withConnectTimeout | Giới hạn thời gian thiết lập kết nối. |
| withSocketTimeout | Giới hạn thời gian chờ phản hồi trên socket. |
| withProxy | Cấu hình proxy HTTP. |
| withPathPrefix | Thêm path prefix khi cluster nằm sau reverse proxy. |
| withDefaultHeaders | Gửi header mặc định trên mọi request. |
| withHeaders | Cung cấp header động trước mỗi request. |
| withClientConfigurer | Tùy chỉnh low-level client hoặc HTTP client bên dưới. |

### 3.1. Kết nối nhiều node

Có thể khai báo nhiều địa chỉ:

~~~java
@Override
public ClientConfiguration clientConfiguration() {
    return ClientConfiguration.builder()
            .connectedTo(
                    "es-node-1.example.net:9200",
                    "es-node-2.example.net:9200",
                    "es-node-3.example.net:9200"
            )
            .build();
}
~~~

Client sử dụng các địa chỉ đã cấu hình để kết nối tới cluster. Trong môi trường triển khai thực tế, hãy dùng endpoint được cung cấp bởi hạ tầng Elasticsearch hoặc load balancer của hệ thống.

Không khai báo địa chỉ HTTP đầy đủ nếu builder yêu cầu host và port. Khi bật SSL, cấu hình scheme qua usingSsl() hoặc overload SSL tương ứng.

### 3.2. Bật SSL/TLS và Basic Authentication

Ví dụ cấu hình HTTPS:

~~~java
import java.time.Duration;

@Override
public ClientConfiguration clientConfiguration() {
    return ClientConfiguration.builder()
            .connectedTo("search.example.net:9200")
            .usingSsl()
            .withBasicAuth(username, password)
            .withConnectTimeout(Duration.ofSeconds(5))
            .withSocketTimeout(Duration.ofSeconds(10))
            .build();
}
~~~

username và password nên được nạp từ secret store, environment hoặc hệ thống quản lý cấu hình của ứng dụng. Không commit thông tin xác thực vào source code hoặc file cấu hình dùng chung.

usingSsl() bật TLS. Nếu cluster dùng certificate nội bộ hoặc certificate authority riêng, cần cấu hình SSLContext hoặc certificate fingerprint theo overload được hỗ trợ bởi phiên bản client. Không tắt kiểm tra certificate chỉ để xử lý lỗi kết nối.

### 3.3. Timeout

Hai timeout thường cần phân biệt:

- Connect timeout: thời gian tối đa để thiết lập kết nối tới node.
- Socket timeout: thời gian tối đa chờ phản hồi trên kết nối.

Ví dụ:

~~~java
ClientConfiguration configuration = ClientConfiguration.builder()
        .connectedTo("localhost:9200")
        .withConnectTimeout(Duration.ofSeconds(3))
        .withSocketTimeout(Duration.ofSeconds(8))
        .build();
~~~

Giá trị phù hợp phụ thuộc latency, kích thước request, số lượng shard và thời gian xử lý query. Timeout quá ngắn có thể làm request hợp lệ thất bại; timeout quá dài có thể khiến tài nguyên bị giữ lâu khi cluster gặp sự cố.

Timeout ở client cũng cần được phối hợp với timeout của HTTP server, gateway và service gọi tới ứng dụng.

### 3.4. Proxy và path prefix

Khi Elasticsearch nằm sau reverse proxy, có thể cần proxy hoặc path prefix:

~~~java
ClientConfiguration configuration = ClientConfiguration.builder()
        .connectedTo("search-gateway.example.net:443")
        .usingSsl()
        .withProxy("proxy.example.net:8888")
        .withPathPrefix("elasticsearch")
        .build();
~~~

Chỉ dùng withProxy khi mạng triển khai yêu cầu proxy. Chỉ dùng withPathPrefix khi reverse proxy thực sự chuyển tiếp request qua prefix tương ứng. Nếu khai báo sai prefix, client có thể nhận 404 dù host và port đúng.

### 3.5. Header mặc định và header động

Có thể thêm header cho mọi request:

~~~java
import org.springframework.data.elasticsearch.support.HttpHeaders;

HttpHeaders headers = new HttpHeaders();
headers.add("X-Application", "catalog-service");

ClientConfiguration configuration = ClientConfiguration.builder()
        .connectedTo("localhost:9200")
        .withDefaultHeaders(headers)
        .build();
~~~

Nếu cần token thay đổi theo thời gian, có thể dùng supplier:

~~~java
ClientConfiguration configuration = ClientConfiguration.builder()
        .connectedTo("search.example.net:9200")
        .withHeaders(() -> {
            HttpHeaders headers = new HttpHeaders();
            headers.add("Authorization", currentAuthorizationHeader());
            return headers;
        })
        .build();
~~~

Trong reactive setup, supplier tạo header không được thực hiện thao tác blocking. Không gọi dịch vụ cấp token bằng một lời gọi đồng bộ bên trong supplier. Nếu token cần refresh bất đồng bộ, hãy thiết kế cơ chế cung cấp token phù hợp với lifecycle của ứng dụng và API client.

Không ghi token hoặc thông tin xác thực vào log request.

### 3.6. Tùy chỉnh client nâng cao

Khi các tùy chọn chuẩn không đáp ứng yêu cầu, ClientConfiguration hỗ trợ withClientConfigurer để tùy chỉnh các thành phần thấp hơn như Rest5Client hoặc HTTP async client.

Ví dụ dạng cấu hình callback:

~~~java
import static org.springframework.data.elasticsearch.client.elc.ElasticsearchClients.*;

ClientConfiguration configuration = ClientConfiguration.builder()
        .connectedTo("localhost:9200")
        .withClientConfigurer(Rest5Clients.ElasticsearchRest5ClientConfigurationCallback.from(
                restClientBuilder -> {
                    // Tùy chỉnh low-level Rest5Client theo nhu cầu triển khai.
                    return restClientBuilder;
                }))
        .build();
~~~

Kiểu callback cụ thể phụ thuộc loại thành phần cần tùy chỉnh. Rest5Client có callback riêng cho client builder, HTTP async client, connection manager và request configuration.

Chỉ can thiệp low-level client khi thật sự cần. Các tùy chỉnh connection pool, retry hoặc TLS có thể ảnh hưởng tới toàn bộ request và cần được kiểm thử bằng tải đại diện.

## 4. Tùy chỉnh transportOptions và JsonpMapper

ReactiveElasticsearchConfiguration cho phép override các hook để tùy chỉnh transport.

### 4.1. transportOptions()

transportOptions() cung cấp các tùy chọn được thêm vào request gửi qua transport. Đây là điểm mở rộng khi cần cấu hình mặc định ở tầng request.

Ví dụ khung override:

~~~java
import co.elastic.clients.transport.TransportOptions;

@Override
public TransportOptions transportOptions() {
    return super.transportOptions();
}
~~~

Ví dụ trên giữ nguyên mặc định. Khi cần tùy chỉnh header hoặc request option ở transport level, hãy dùng builder và kiểu option phù hợp với phiên bản Elasticsearch Java Client.

Không dùng transportOptions để thay thế security role hoặc quyền index. Các option ở client không cấp thêm quyền cho user trên cluster.

### 4.2. jsonpMapper()

JsonpMapper chịu trách nhiệm chuyển đổi JSON cho Elasticsearch Java API Client. ReactiveElasticsearchConfiguration cung cấp bean mapper mặc định và dùng nó khi tạo ElasticsearchTransport.

Chỉ override jsonpMapper() khi cần quy tắc serialization/deserialization đặc biệt, ví dụ custom JSON handling hoặc cấu hình mapper tích hợp với ứng dụng.

Khi tùy chỉnh mapper, cần kiểm tra:

- Kiểu dữ liệu ngày giờ.
- Enum và custom value object.
- Tên property.
- Null handling.
- Compatibility với response của Elasticsearch.
- Mapping entity của Spring Data có còn hoạt động đúng không.

Không tạo một mapper khác biệt tùy tiện cho từng service nếu toàn ứng dụng cần cùng quy tắc chuyển đổi.

## 5. Các bean được tạo và cách inject

Sau khi cấu hình hoàn tất, Spring có thể inject các bean reactive:

~~~java
import org.springframework.data.elasticsearch.client.elc.ReactiveElasticsearchClient;
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;

@Service
public class ProductSearchService {

    private final ReactiveElasticsearchOperations operations;
    private final ReactiveElasticsearchClient client;

    public ProductSearchService(
            ReactiveElasticsearchOperations operations,
            ReactiveElasticsearchClient client) {
        this.operations = operations;
        this.client = client;
    }
}
~~~

Vai trò của từng bean:

- ReactiveElasticsearchClient: giao tiếp cấp thấp với Elasticsearch.
- ReactiveElasticsearchOperations: abstraction cấp cao, có mapping entity, query API và exception translation.
- ReactiveElasticsearchTemplate: implementation mặc định của operations.
- Rest5Client: low-level HTTP client do Elasticsearch Java Client sử dụng.
- ElasticsearchTransport: kết nối HTTP client với JSON mapper và API client.

Trong phần lớn service nghiệp vụ, nên inject ReactiveElasticsearchOperations. Chỉ inject ReactiveElasticsearchClient khi cần gọi API cấp thấp hoặc tính năng chưa được operations hỗ trợ.

Không tạo mới client trong mỗi method hoặc mỗi request. Client nên là bean dùng chung do Spring quản lý để tận dụng connection pool và lifecycle của application context.

## 6. ReactiveElasticsearchOperations và ReactiveElasticsearchTemplate

ReactiveElasticsearchOperations là API cấp cao để thao tác với Elasticsearch trong reactive application. ReactiveElasticsearchTemplate là implementation mặc định.

Các thao tác thường dùng:

| Thao tác | Kiểu trả về thường gặp |
| --- | --- |
| save(entity) | Mono<T> |
| get(id, type) | Mono<T> |
| exists(id, index) | Mono<Boolean> |
| delete(id, index) | Mono<String> |
| search(query, type) | Flux<SearchHit<T>> |
| searchForHits(query, type) | Mono<ReactiveSearchHits<T>> |
| searchForPage(query, type) | Mono<SearchPage<T>> |
| count(query, type) | Mono<Long> |
| aggregate(query, type) | Flux<AggregationContainer<?>> |

Mono được dùng khi thao tác trả về tối đa một kết quả. Flux được dùng khi có thể trả nhiều hit hoặc nhiều phần tử.

### 6.1. Lưu document

Entity ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    // Constructor, getters và setters
}
~~~

Lưu entity bằng operations:

~~~java
Mono<Product> save(Product product) {
    return operations.save(product);
}
~~~

Lời gọi save trả về Mono. Việc lưu được thực hiện khi publisher được subscribe bởi framework hoặc caller. Nếu không có subscriber, pipeline không được thực thi theo cách reactive thông thường.

### 6.2. Lấy document theo ID

~~~java
Mono<Product> findById(String id) {
    return operations.get(id, Product.class);
}
~~~

Nếu không tìm thấy document, Mono hoàn tất mà không phát giá trị. Có thể dùng switchIfEmpty để xử lý trường hợp không tồn tại:

~~~java
Mono<Product> findRequired(String id) {
    return operations.get(id, Product.class)
            .switchIfEmpty(Mono.error(
                    new IllegalArgumentException("Product not found: " + id)
            ));
}
~~~

Trong ứng dụng thực tế, có thể thay IllegalArgumentException bằng exception nghiệp vụ và ánh xạ sang HTTP 404 ở controller advice.

### 6.3. Tìm kiếm bằng Query API

Ví dụ tìm sản phẩm theo tên:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import reactor.core.publisher.Flux;

Flux<Product> searchByName(String text) {
    var query = NativeQuery.builder()
            .withQuery(q -> q.match(m -> m
                    .field("name")
                    .query(text)
            ))
            .build();

    return operations.search(query, Product.class)
            .map(SearchHit::getContent);
}
~~~

operations.search trả Flux<SearchHit<Product>>. Mỗi SearchHit chứa entity cùng metadata như ID, score và thông tin highlight nếu query có cấu hình. map lấy phần entity để trả về Flux<Product>.

Nếu cần score, ID hoặc highlight metadata, giữ SearchHit thay vì chỉ lấy getContent().

### 6.4. Lấy thông tin tổng thể của search

Khi cần total hits hoặc metadata search, dùng searchForHits:

~~~java
Mono<ReactiveSearchHits<Product>> searchWithMetadata(Query query) {
    return operations.searchForHits(query, Product.class);
}
~~~

Khi cần cấu trúc SearchPage, có thể dùng searchForPage:

~~~java
Mono<SearchPage<Product>> searchPage(Query query) {
    return operations.searchForPage(query, Product.class);
}
~~~

Các API này trả metadata ở dạng Mono vì toàn bộ thông tin của một search response được đóng gói trong một kết quả. Chọn API theo việc caller cần stream từng hit hay cần metadata của response.

### 6.5. Tìm kiếm và đếm

~~~java
Mono<Long> countByCategory(String category) {
    Query query = NativeQuery.builder()
            .withQuery(q -> q.term(t -> t
                    .field("category")
                    .value(category)
            ))
            .build();

    return operations.count(query, Product.class);
}
~~~

Count trả Mono<Long>. Không cần lấy toàn bộ document rồi dùng collectList().count() để đếm. Dùng count API giúp Elasticsearch thực hiện phép đếm ở phía server.

### 6.6. Xóa document

~~~java
Mono<String> deleteById(String id) {
    return operations.delete(id, Product.class);
}
~~~

Nếu thao tác cần index cụ thể, có thể dùng overload nhận IndexCoordinates. Khi làm việc với custom routing, hãy bảo đảm routing resolver được cấu hình đúng để thao tác tới đúng shard.

## 7. Reactive Repository

Spring Data Elasticsearch hỗ trợ reactive repository dựa trên Project Reactor. Các interface nền tảng thường dùng là:

- ReactiveRepository.
- ReactiveCrudRepository.
- ReactiveSortingRepository.

Ví dụ repository:

~~~java
import org.springframework.data.repository.reactive.ReactiveSortingRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ProductRepository
        extends ReactiveSortingRepository<Product, String> {

    Flux<Product> findByCategory(String category);

    Mono<Product> findFirstBySku(String sku);

    Flux<Product> findByCategoryOrderByPriceAsc(String category);
}
~~~

Một số kiểu trả về:

- Flux<Product>: nhiều sản phẩm hoặc không có sản phẩm nào.
- Mono<Product>: tối đa một sản phẩm.
- Mono<Long>: số lượng document.
- Mono<Boolean>: kiểm tra có tồn tại hay không.

Khi method có thể trả nhiều document, không khai báo Mono<Product> chỉ vì caller mong đợi một kết quả. Nếu thực tế có nhiều document, framework có thể báo lỗi result size thay vì âm thầm chọn một bản ghi.

### 7.1. Kích hoạt repository reactive

Dùng annotation:

~~~java
@Configuration
@EnableReactiveElasticsearchRepositories(
        basePackages = "com.example.catalog.repository"
)
public class RepositoryConfiguration {
}
~~~

Nếu class cấu hình này nằm cùng với ReactiveElasticsearchConfiguration, có thể đặt annotation trên class kế thừa đó. Chỉ cần bảo đảm repository reactive được quét và có ReactiveElasticsearchOperations phù hợp trong application context.

Không dùng @EnableElasticsearchRepositories cho repository reactive. Annotation đó kích hoạt hạ tầng repository imperative.

### 7.2. Repository method với Publisher đầu vào

Reactive repository có thể nhận Publisher làm tham số:

~~~java
Flux<Product> findByCategory(Publisher<String> category);
~~~

Điều này cho phép ghép dữ liệu đầu vào từ một nguồn reactive khác. Khi dùng publisher đầu vào, cần hiểu rằng query chỉ được thực hiện khi publisher được subscribe và dữ liệu đầu vào được phát.

## 8. Kết hợp với Spring WebFlux

Reactive client phát huy tác dụng khi các tầng của ứng dụng đều giữ publisher thay vì chuyển kết quả thành giá trị đồng bộ.

Ví dụ controller:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductRepository repository;

    public ProductController(ProductRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/category/{category}")
    public Flux<Product> findByCategory(
            @PathVariable String category) {
        return repository.findByCategory(category);
    }

    @GetMapping("/sku/{sku}")
    public Mono<Product> findBySku(@PathVariable String sku) {
        return repository.findFirstBySku(sku);
    }

    @PostMapping
    public Mono<Product> create(@RequestBody Product product) {
        return repository.save(product);
    }
}
~~~

Spring WebFlux subscribe vào publisher để xử lý request và ghi response. Controller không cần tự gọi subscribe() hoặc block().

Luồng request:

~~~text
HTTP request
     |
     v
WebFlux Controller
     |
     v
Mono / Flux từ service hoặc repository
     |
     v
Reactive Elasticsearch Operations
     |
     v
Elasticsearch
     |
     v
Mono / Flux kết quả
     |
     v
HTTP response
~~~

Nếu một controller trả Mono hoặc Flux, framework có thể quản lý subscription, cancellation và ghi response theo reactive contract.

## 9. Spring Boot auto-configuration

Nếu dùng Spring Boot, không phải lúc nào cũng cần tự viết class kế thừa ReactiveElasticsearchConfiguration.

Khi có Spring Data Elasticsearch và Reactor trên classpath, Spring Boot có thể tự cấu hình ReactiveElasticsearchClient và ReactiveElasticsearchTemplate. Starter thường dùng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-elasticsearch</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Spring Boot BOM quản lý version dependency tương thích. Không tự nâng riêng Elasticsearch Java Client hoặc Rest5Client nếu không kiểm tra compatibility matrix.

### 9.1. Cấu hình bằng application.yml

Ví dụ:

~~~yaml
spring:
  elasticsearch:
    uris: https://search.example.net:9200
    username: ${ES_USERNAME_FROM_SECRET_STORE}
    password: ${ES_PASSWORD_FROM_SECRET_STORE}
    socket-timeout: 10s
~~~

Các giá trị username và password minh họa cần được thay bằng secret được cung cấp qua environment hoặc secret manager. Không commit password thật vào repository.

Spring Boot sử dụng các thuộc tính spring.elasticsearch để cấu hình REST client, transport và ReactiveElasticsearchClient. Với stack hiện hành, ReactiveElasticsearchClient sử dụng transport dựa trên Rest5Client.

### 9.2. Khi nào dùng cấu hình thủ công?

Dùng ReactiveElasticsearchConfiguration khi cần:

- Cấu hình nhiều client hoặc cluster riêng.
- Tùy chỉnh ClientConfiguration ngoài các property mặc định.
- Thay đổi JsonpMapper hoặc transportOptions.
- Cấu hình callback ở low-level client.
- Kiểm soát rõ package repository và mapping infrastructure.

Nếu Boot đã tạo đúng ReactiveElasticsearchClient và ReactiveElasticsearchTemplate, hãy inject các bean đó. Tránh tạo thêm client hoặc template trùng chức năng nếu không có nhu cầu rõ ràng.

Nếu tự cung cấp bean operations/template để backing reactive repositories, bean name được Spring Boot/Spring Data dùng phổ biến là reactiveElasticsearchTemplate. Kiểm tra điều kiện auto-configuration của version Boot đang dùng để tránh xung đột bean.

## 10. Vòng đời client và quản lý tài nguyên

Client là thành phần dùng chung của application context. Không tạo client mới trong mỗi service method hoặc request.

Một cấu hình Spring thông thường quản lý lifecycle như sau:

1. Application context khởi động.
2. ReactiveElasticsearchConfiguration tạo ClientConfiguration.
3. Low-level client và transport được tạo.
4. ReactiveElasticsearchClient được tạo từ transport.
5. ReactiveElasticsearchTemplate được tạo từ client và converter.
6. Service/repository được inject các bean.
7. Khi application context đóng, Spring quản lý lifecycle của các bean hạ tầng.

Không tự đóng client sau mỗi request. Nếu tự tạo low-level client bên ngoài cấu hình Spring, cần tự chịu trách nhiệm đóng tài nguyên khi ứng dụng dừng.

Các nguyên tắc:

- Dùng singleton bean cho client và template.
- Không tạo Rest5Client mới cho từng lần search.
- Không gọi close() sau mỗi thao tác.
- Không giữ một connection hoặc response body mở ngoài lifecycle của request.
- Dùng timeout và connection pool phù hợp với tải.
- Theo dõi connection failure, timeout và request latency.

## 11. Reactor: subscription, laziness và backpressure

### 11.1. Publisher chỉ chạy khi được subscribe

Ví dụ:

~~~java
Mono<Product> result = repository.findById("P-100");
~~~

Dòng code này tạo publisher. Nó chưa có nghĩa request Elasticsearch đã hoàn tất hoặc giá trị Product đã có ngay lập tức.

Khi framework hoặc caller subscribe, pipeline mới được thực thi:

~~~java
return repository.findById("P-100")
        .map(Product::getName);
~~~

Trong controller, chỉ cần trả publisher cho WebFlux. Không cần tự subscribe.

### 11.2. Không gọi block() trong reactive request path

Không nên viết:

~~~java
Product product = repository.findById("P-100").block();
~~~

block() chờ kết quả đồng bộ và giữ thread cho tới khi publisher hoàn tất. Nếu gọi trên event-loop thread của WebFlux, nó có thể làm giảm throughput hoặc gây lỗi do blocking call.

Thay vào đó, nối các publisher:

~~~java
Mono<Product> findAndUpdate(String id) {
    return repository.findById(id)
            .flatMap(product -> {
                product.setCategory("FEATURED");
                return repository.save(product);
            });
}
~~~

flatMap nối thao tác save sau khi findById phát ra entity.

### 11.3. Không gọi subscribe() bên trong service

Không nên:

~~~java
public void save(Product product) {
    repository.save(product).subscribe();
}
~~~

Cách này tạo một luồng thực thi tách khỏi caller. Caller không nhận được kết quả hoặc lỗi của thao tác, khó phối hợp với transaction, retry, tracing và cancellation.

Nên trả publisher:

~~~java
public Mono<Product> save(Product product) {
    return repository.save(product);
}
~~~

Caller quyết định cách ghép, xử lý lỗi và hoàn tất request.

### 11.4. Backpressure không đồng nghĩa truy vấn vô hạn

Flux cho phép downstream yêu cầu dữ liệu theo nhu cầu. Tuy nhiên, một search request Elasticsearch vẫn có giới hạn kết quả theo size/from hoặc cơ chế pagination tương ứng.

Không giả định Flux<SearchHit<T>> tự động quét toàn bộ index vô hạn hoặc tự tạo nhiều trang. Nếu cần phân trang, hãy cấu hình Query/Pageable, dùng search_after/PIT khi phù hợp hoặc triển khai cơ chế duyệt kết quả rõ ràng.

Thu thập toàn bộ kết quả bằng collectList() có thể làm tăng bộ nhớ theo số hit. Chỉ dùng khi tập kết quả đã được giới hạn ở mức hợp lý.

## 12. Ghép nhiều thao tác reactive

Reactor cung cấp các operator để ghép thao tác:

| Operator | Mục đích |
| --- | --- |
| map | Chuyển đổi giá trị đồng bộ. |
| flatMap | Ghép một thao tác trả Publisher. |
| concatMap | Thực hiện từng phần tử theo thứ tự tuần tự. |
| flatMapSequential | Thực hiện bất đồng bộ nhưng giữ thứ tự phát kết quả. |
| filter | Lọc giá trị. |
| switchIfEmpty | Xử lý khi publisher không phát giá trị. |
| onErrorResume | Chuyển sang publisher khác khi có lỗi. |
| retryWhen | Retry theo chính sách được cấu hình. |
| timeout | Giới hạn thời gian chờ publisher. |
| zip | Kết hợp kết quả từ nhiều publisher. |

Ví dụ tìm sản phẩm, rồi lưu lịch sử truy cập:

~~~java
Mono<Product> findAndRecord(String id) {
    return repository.findById(id)
            .flatMap(product ->
                    accessLogRepository.save(
                            new ProductAccessLog(product.getId())
                    ).thenReturn(product)
            );
}
~~~

thenReturn giữ kết quả Product sau khi thao tác ghi log hoàn tất.

### 12.1. Chạy nhiều thao tác độc lập

~~~java
Mono<Tuple2<Long, Long>> loadStatistics() {
    Mono<Long> active = repository.countByCategory("ACTIVE");
    Mono<Long> archived = repository.countByCategory("ARCHIVED");

    return Mono.zip(active, archived);
}
~~~

Mono.zip chạy các publisher độc lập và phát một tuple khi tất cả hoàn tất. Nếu một thao tác lỗi, lỗi được chuyển tiếp theo quy tắc của Reactor.

Chỉ chạy song song khi các thao tác thực sự độc lập và cluster có đủ tài nguyên. Tạo quá nhiều request song song có thể làm tăng áp lực lên Elasticsearch.

## 13. Xử lý lỗi và retry

Lỗi từ Elasticsearch được chuyển thành error signal trong Mono/Flux. Có thể xử lý bằng onErrorResume, onErrorMap hoặc retryWhen.

Ví dụ ánh xạ lỗi ở service:

~~~java
Mono<Product> findProduct(String id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)
            ))
            .onErrorMap(
                    ElasticsearchException.class,
                    ProductSearchException::new
            );
}
~~~

Tên exception thực tế phụ thuộc tầng client và Spring Data. Hãy xử lý theo exception type hoặc status code có ý nghĩa thay vì parse message cố định.

### 13.1. Retry có giới hạn

Retry chỉ phù hợp với lỗi tạm thời có thể phục hồi, ví dụ một số lỗi kết nối hoặc throttling. Không retry vô hạn và không retry mọi exception.

Ví dụ:

~~~java
Mono<Product> findWithRetry(String id) {
    return repository.findById(id)
            .retryWhen(
                    Retry.backoff(2, Duration.ofMillis(200))
                            .filter(this::isTransientFailure)
            );
}
~~~

Hàm isTransientFailure cần phân loại lỗi theo chính sách ứng dụng. Lỗi mapping, authentication, validation hoặc query sai thường không tự hết khi retry.

Với thao tác ghi, phải xem xét idempotency. Nếu client không biết request trước đã được server xử lý hay chưa, retry một thao tác ghi không idempotent có thể tạo hiệu ứng lặp.

### 13.2. Timeout và cancellation

Có thể đặt timeout cho một pipeline:

~~~java
Mono<Product> findProduct(String id) {
    return repository.findById(id)
            .timeout(Duration.ofSeconds(3));
}
~~~

Timeout làm publisher phát lỗi nếu không hoàn tất trong thời gian cho phép. Khi downstream hủy subscription, cancellation được truyền qua reactive pipeline ở mức các thành phần hỗ trợ.

Timeout của Reactor không thay thế socket timeout của client. Hai tầng này có mục đích khác nhau và nên được cấu hình tương thích.

## 14. Phân trang và kết quả lớn

Reactive API không tự loại bỏ giới hạn phân trang của Elasticsearch.

Với repository, có thể nhận Pageable:

~~~java
Flux<Product> findByCategory(String category, Pageable pageable);
~~~

Với operations, cấu hình pageable trên Query hoặc NativeQuery theo API phiên bản đang dùng. Khi trả một page cùng metadata, dùng searchForPage để nhận Mono<SearchPage<T>>.

Với dữ liệu rất lớn:

- Không gọi collectList() trên tập kết quả không giới hạn.
- Chọn page size phù hợp.
- Duyệt theo cursor/search_after nếu cần.
- Cân nhắc Point in Time để giữ snapshot khi duyệt nhiều trang.
- Đóng PIT sau khi hoàn tất.
- Hạn chế số request song song.
- Xử lý cancellation khi client ngắt kết nối.

Flux chỉ là cách biểu diễn dữ liệu trong ứng dụng. Nó không tự làm thay đổi semantics của Search API.

## 15. Reactive client và imperative client trong cùng ứng dụng

Một ứng dụng có thể cần cả reactive và imperative client, nhưng phải phân biệt bean và luồng gọi.

| Reactive | Imperative |
| --- | --- |
| ReactiveElasticsearchClient | ElasticsearchClient |
| ReactiveElasticsearchOperations | ElasticsearchOperations |
| ReactiveElasticsearchTemplate | ElasticsearchTemplate |
| Mono / Flux | Giá trị trực tiếp hoặc Collection |
| Reactive repository | Repository imperative |

Không inject ElasticsearchOperations rồi gọi nó trong service reactive và nghĩ rằng bọc kết quả bằng Mono.fromCallable() sẽ biến I/O blocking thành non-blocking.

Nếu bắt buộc tích hợp thư viện blocking, có thể cô lập lời gọi đó trên boundedElastic scheduler:

~~~java
Mono<Result> callBlockingLibrary() {
    return Mono.fromCallable(() -> blockingLibrary.call())
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Đây chỉ là giải pháp cô lập blocking work. Với Elasticsearch, nên dùng ReactiveElasticsearchClient/Operations để giữ I/O theo reactive stack.

Nếu có hai cluster hoặc hai loại client, dùng qualifier rõ ràng và đặt tên bean/service có ý nghĩa để tránh inject nhầm.

## 16. Quản lý index và mapping theo reactive API

ReactiveElasticsearchOperations cung cấp indexOps() để thao tác với index theo kiểu reactive.

Ví dụ lấy ReactiveIndexOperations:

~~~java
ReactiveIndexOperations indexOperations =
        operations.indexOps(Product.class);
~~~

Các thao tác index như kiểm tra tồn tại, tạo index, tạo mapping hoặc xóa index trả publisher theo API tương ứng. Khi gọi các thao tác này, phải subscribe hoặc ghép publisher vào pipeline để request được thực thi.

Ví dụ luồng khởi tạo index nên được quản lý ở bước bootstrap hoặc migration, không chạy create index lặp lại trong mỗi request nghiệp vụ.

Trong production, thường nên quản lý index template, mapping và alias bằng migration/deployment riêng. Tự động tạo index từ entity metadata tiện lợi trong môi trường phát triển, nhưng cần kiểm soát thay đổi mapping ở môi trường thật.

## 17. Kiểm thử reactive client

Có thể dùng Reactor Test với StepVerifier để kiểm thử publisher:

~~~java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

@Test
void returnsProductById() {
    Mono<Product> result = repository.findById("P-100");

    StepVerifier.create(result)
            .expectNextMatches(product ->
                    product.getId().equals("P-100"))
            .verifyComplete();
}
~~~

StepVerifier subscribe vào publisher và xác minh các signal được phát ra. Đây là cách phù hợp để kiểm thử Mono/Flux mà không cần block trong test.

Với integration test:

- Chạy Elasticsearch đúng phiên bản tương thích.
- Xác nhận TLS/authentication nếu môi trường dùng chúng.
- Kiểm tra mapping và index được tạo.
- Kiểm tra save/get/search/delete.
- Kiểm tra empty result và error mapping.
- Kiểm tra timeout, cancellation và retry.
- Kiểm tra repository reactive được scan đúng package.
- Kiểm tra không có imperative client bị inject nhầm.

Testcontainers có thể giúp khởi tạo Elasticsearch cho integration test. Chọn image version theo compatibility matrix của Spring Data Elasticsearch và Elasticsearch Java Client đang dùng.

## 18. Quan sát và vận hành

Trong production, cần theo dõi:

- Request latency và throughput.
- Connection timeout và socket timeout.
- HTTP status/error type.
- Số request đang chạy đồng thời.
- Retry count.
- Connection pool saturation.
- Elasticsearch cluster health và search/write latency.
- Heap, CPU, thread pool và rejected requests ở cluster.
- Cancellation hoặc timeout từ phía ứng dụng.

Spring Data Elasticsearch tích hợp các abstraction về observation/micrometer tùy phiên bản. Có thể dùng observation registry và tracing của Spring Boot để nối request HTTP với các thao tác Elasticsearch.

Transport logging ở mức TRACE có thể hữu ích khi debug request/response nhưng không nên bật rộng trong production. Log có thể chứa query, dữ liệu document hoặc thông tin nhạy cảm.

## 19. Lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy ReactiveElasticsearchClient bean | Thiếu Spring Data Elasticsearch hoặc Reactor, hoặc auto-configuration bị tắt. | Kiểm tra dependency và cấu hình Spring Boot. |
| Không tìm thấy ReactiveElasticsearchOperations | Chưa cấu hình client hoặc chưa tạo template. | Dùng ReactiveElasticsearchConfiguration hoặc Boot auto-configuration. |
| Repository reactive không được tạo | Chưa bật EnableReactiveElasticsearchRepositories hoặc package scan sai. | Kiểm tra annotation và basePackages. |
| Repository trả publisher nhưng không có request | Publisher chưa được subscribe. | Trả publisher cho framework hoặc compose với publisher khác. |
| Request bị treo hoặc thread starvation | Gọi block hoặc dùng imperative client trong WebFlux event loop. | Dùng reactive client xuyên suốt, loại bỏ blocking call. |
| TLS handshake thất bại | Certificate, CA hoặc SSL context không đúng. | Kiểm tra certificate chain và trust configuration. |
| 401/403 | Username/password sai hoặc role thiếu quyền. | Kiểm tra credential và cluster/index privileges. |
| 404 qua reverse proxy | Path prefix hoặc endpoint sai. | Kiểm tra withPathPrefix và cấu hình proxy. |
| Connection timeout | Node không reachable, pool quá tải hoặc timeout quá ngắn. | Kiểm tra mạng, cluster, connection pool và timeout. |
| Search trả thiếu document | Query size/page size hoặc filter giới hạn kết quả. | Kiểm tra Query, Pageable và Search API. |
| Dùng class config cũ không biên dịch | Ví dụ thuộc AbstractReactiveElasticsearchConfiguration hoặc legacy client. | Dùng ReactiveElasticsearchConfiguration đúng package và version. |
| Có nhiều bean operations/client | Boot auto-config và manual config tạo cấu hình trùng nhau. | Chọn một hướng cấu hình hoặc dùng qualifier rõ ràng. |

## 20. Quy trình cấu hình từ đầu đến cuối

Khi đưa reactive Elasticsearch vào ứng dụng, có thể thực hiện theo thứ tự:

1. Chọn version Spring Boot, Spring Data Elasticsearch và Elasticsearch tương thích.
2. Thêm Spring Data Elasticsearch và Reactor dependencies.
3. Nếu HTTP server cũng reactive, dùng Spring WebFlux.
4. Chọn Boot auto-configuration hay ReactiveElasticsearchConfiguration thủ công.
5. Cấu hình host, TLS, authentication, timeout và header.
6. Xác nhận Spring tạo ReactiveElasticsearchClient và ReactiveElasticsearchOperations.
7. Khai báo entity bằng @Document và mapping phù hợp.
8. Bật @EnableReactiveElasticsearchRepositories nếu dùng manual repository configuration.
9. Inject ReactiveElasticsearchOperations hoặc reactive repository vào service.
10. Trả Mono/Flux xuyên suốt service và WebFlux controller.
11. Tránh block(), subscribe() và imperative client trong reactive request path.
12. Kiểm tra pagination, cancellation, retry và error mapping.
13. Kiểm thử integration bằng Elasticsearch tương thích.
14. Theo dõi latency, connection pool và cluster resource trong production.

## 21. Tài liệu tham khảo

- [Spring Data Elasticsearch — Elasticsearch Clients](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html)
- [Spring Data Elasticsearch — ReactiveElasticsearchConfiguration API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ReactiveElasticsearchConfiguration.html)
- [Spring Data Elasticsearch — ReactiveElasticsearchOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ReactiveElasticsearchOperations.html)
- [Spring Data Elasticsearch — Reactive Elasticsearch Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/reactive-elasticsearch-repositories.html)
- [Spring Data Elasticsearch — ReactiveElasticsearchTemplate API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ReactiveElasticsearchTemplate.html)
- [Spring Boot — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)

ReactiveElasticsearchConfiguration tạo client reactive và các abstraction cần thiết từ ClientConfiguration. Trong service, ReactiveElasticsearchOperations hoặc reactive repository cung cấp API Mono/Flux để kết hợp với Spring WebFlux. Giữ luồng xử lý không blocking, quản lý client như singleton bean, cấu hình đúng TLS/auth/timeout và phân biệt client hiện hành với API legacy để kết nối ổn định.

