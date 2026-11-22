# Kiểm thử bằng StepVerifier và dữ liệu Elasticsearch thực

## 1. Mục tiêu của kiểm thử reactive với Elasticsearch

Một ứng dụng Spring Data Elasticsearch reactive thường dùng Mono<T> cho thao tác trả về tối đa một kết quả và Flux<T> cho luồng có thể phát nhiều kết quả. Repository và ReactiveElasticsearchTemplate trả về các publisher này để ứng dụng ghép nối truy vấn, chuyển đổi dữ liệu, xử lý lỗi và điều khiển luồng.

Kiểm thử các publisher đó cần xác nhận hai điều:

1. Chuỗi reactive phát đúng tín hiệu: giá trị, lỗi hoặc hoàn tất.
2. Các thao tác lưu trữ thật sự tạo ra trạng thái đúng trong Elasticsearch.

Project Reactor cung cấp StepVerifier để mô tả kỳ vọng theo thứ tự tín hiệu. Testcontainers cung cấp container Elasticsearch tạm thời để kiểm thử mapping, query, repository và hành vi của server thật.

Hai công cụ này giải quyết hai phần bổ sung cho nhau. StepVerifier kiểm tra hợp đồng reactive; Elasticsearch thật kiểm tra hành vi tích hợp với search engine.

Ví dụ, một test chỉ kiểm tra:

~~~java
StepVerifier.create(Mono.just("saved"))
    .expectNext("saved")
    .verifyComplete();
~~~

sẽ xác nhận một publisher phát đúng chuỗi tín hiệu. Nó không chứng minh repository có ghi document, mapping có đúng, analyzer có hoạt động hay query Elasticsearch trả đúng dữ liệu.

Ngược lại, một test chỉ gọi block rồi so sánh object có thể xác nhận kết quả lưu trữ, nhưng không mô tả rõ thứ tự tín hiệu, lỗi, cancellation hoặc backpressure của publisher.

Bài này kết hợp hai cách kiểm tra để xây dựng integration test cho Spring Data Elasticsearch reactive.

## 2. Các lớp kiểm thử nên có

Không phải mọi test đều cần khởi động Elasticsearch. Hãy chọn loại test theo điều cần xác nhận.

| Loại test | Thành phần | Mục đích |
|---|---|---|
| Unit test reactive | Service và publisher giả lập | Kiểm tra nhánh nghiệp vụ, mapping DTO, xử lý lỗi |
| Test publisher | Mono, Flux, TestPublisher, PublisherProbe | Kiểm tra operator và subscription path |
| Integration test | Reactive repository/template + Elasticsearch thật | Kiểm tra mapping, query, CRUD và refresh |
| End-to-end test | API hoặc ứng dụng + Elasticsearch thật | Kiểm tra cấu hình, serialization và luồng request thực tế |

Unit test vẫn hữu ích khi repository được mock. Tuy nhiên, mock không thể xác nhận Elasticsearch hiểu query DSL, áp dụng analyzer, mapping field, xử lý version conflict hoặc refresh document như thế nào.

Với những hành vi phụ thuộc engine, hãy dùng một Elasticsearch instance thật trong test. Testcontainers giúp tạo instance này theo vòng đời của JUnit test.

Một integration test tốt thường:

- Khởi động Elasticsearch đúng major version mà ứng dụng hỗ trợ.
- Tạo index và mapping cần kiểm tra.
- Ghi dữ liệu qua reactive API.
- Refresh index khi test cần tìm kiếm document vừa ghi.
- Đọc dữ liệu bằng một truy vấn thực.
- Kiểm tra cả giá trị và tín hiệu reactive.
- Xóa dữ liệu hoặc index sau test.

## 3. StepVerifier kiểm tra tín hiệu nào?

StepVerifier thuộc artifact reactor-test. Nó đăng ký một subscriber vào publisher được kiểm thử và so sánh các tín hiệu nhận được với kịch bản đã khai báo.

Một Mono<T> có thể:

- Phát một onNext(T) rồi onComplete().
- Chỉ phát onComplete() mà không có giá trị.
- Phát onError(Throwable).

Một Flux<T> có thể phát nhiều onNext, sau đó hoàn tất hoặc kết thúc bằng lỗi.

Ví dụ kiểm tra một Mono thành công:

~~~java
Mono<String> source = Mono.just("product-1");

StepVerifier.create(source)
    .expectNext("product-1")
    .expectComplete()
    .verify();
~~~

verify() mới thực sự subscribe và chạy publisher. Nếu chỉ tạo Mono hoặc Flux rồi không subscribe, thao tác lưu trữ có thể chưa được thực hiện.

Có thể dùng shortcut:

~~~java
StepVerifier.create(repository.findById("product-1"))
    .expectNextMatches(product ->
        product.getId().equals("product-1")
    )
    .verifyComplete();
~~~

verifyComplete() vừa mong đợi publisher hoàn tất vừa thực thi verification. Khi cần timeout rõ ràng, nên dùng terminal expectation rồi gọi verify(Duration):

~~~java
StepVerifier.create(repository.findById("product-1"))
    .expectNextMatches(product ->
        product.getId().equals("product-1")
    )
    .expectComplete()
    .verify(Duration.ofSeconds(10));
~~~

Theo mặc định, các phương thức verification không có timeout. Nếu publisher không phát tín hiệu kết thúc, test có thể chờ vô hạn. Với integration test có network I/O, đặt timeout phù hợp cho từng test hoặc cấu hình timeout mặc định của StepVerifier.

### Các expectation thường dùng

| Method | Mục đích |
|---|---|
| expectNext(value) | Mong đợi giá trị tiếp theo bằng giá trị chỉ định |
| expectNextMatches(predicate) | Kiểm tra giá trị tiếp theo bằng predicate |
| assertNext(consumer) | Chạy assertion trên giá trị tiếp theo |
| consumeNextWith(consumer) | Tiêu thụ và kiểm tra giá trị tiếp theo |
| expectNextCount(n) | Mong đợi đúng n phần tử tiếp theo |
| expectNextSequence(values) | Mong đợi một chuỗi giá trị theo thứ tự |
| expectComplete() | Mong đợi publisher hoàn tất |
| expectError(type) | Mong đợi lỗi thuộc kiểu chỉ định |
| expectErrorMatches(predicate) | Kiểm tra lỗi bằng predicate |
| expectErrorMessage(message) | Kiểm tra message của lỗi |
| thenAwait(duration) | Chờ một khoảng thời gian trong kịch bản |
| thenRequest(n) | Yêu cầu thêm n phần tử để kiểm tra backpressure |
| thenCancel() | Hủy subscription |
| verify(duration) | Chạy kịch bản với timeout |

Ví dụ kiểm tra nhiều kết quả:

~~~java
StepVerifier.create(Flux.just("a", "b", "c"))
    .expectNext("a")
    .assertNext(value -> assertThat(value).isEqualTo("b"))
    .expectNext("c")
    .expectComplete()
    .verify(Duration.ofSeconds(2));
~~~

Ví dụ kiểm tra lỗi:

~~~java
StepVerifier.create(Mono.error(
        new IllegalArgumentException("invalid product")
    ))
    .expectErrorMatches(error ->
        error instanceof IllegalArgumentException
            && error.getMessage().equals("invalid product")
    )
    .verify(Duration.ofSeconds(2));
~~~

### Đặt tên scenario để dễ đọc lỗi

Có thể đặt tên cho toàn bộ kịch bản bằng StepVerifierOptions:

~~~java
StepVerifierOptions options = StepVerifierOptions.create()
    .scenarioName("Lưu sản phẩm và đọc lại bằng ID");

StepVerifier.create(repository.save(product), options)
    .assertNext(saved ->
        assertThat(saved.getId()).isEqualTo(product.getId())
    )
    .expectComplete()
    .verify(Duration.ofSeconds(10));
~~~

Cũng có thể dùng as("mô tả expectation") sau nhiều expectation methods. Khi một expectation do StepVerifier tạo ra thất bại, mô tả này giúp xác định bước gặp lỗi.

## 4. Thêm dependency cho test

Nếu ứng dụng đã có Spring Data Elasticsearch reactive và Reactor ở runtime, phần test thường cần thêm reactor-test, Testcontainers Elasticsearch và tích hợp JUnit Jupiter.

Ví dụ Gradle với Testcontainers BOM:

~~~groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")

    testImplementation(platform("org.testcontainers:testcontainers-bom:2.0.5"))
    testImplementation("org.testcontainers:testcontainers-elasticsearch")
    testImplementation("org.testcontainers:testcontainers-junit-jupiter")
}
~~~

Nếu không dùng Spring Boot dependency management, hãy khai báo phiên bản tương thích cho các dependency của Spring Data Elasticsearch, Reactor và Testcontainers. Không nên trộn các phiên bản Testcontainers module khác nhau trong cùng test runtime.

Với Maven, cấu hình tương đương:

~~~xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-elasticsearch</artifactId>
    <version>2.0.5</version>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-junit-jupiter</artifactId>
    <version>2.0.5</version>
    <scope>test</scope>
</dependency>
~~~

Chọn image Elasticsearch tương thích với phiên bản Spring Data Elasticsearch và phiên bản server production. Ví dụ, release train 2026.0 với Spring Data Elasticsearch 6.1.x dùng Elasticsearch 9.4.7 theo bảng tương thích. Không nên chọn image chỉ vì tag mới nhất nếu client và server trong ứng dụng chưa hỗ trợ phiên bản đó.

Với ví dụ Spring Boot 4 dùng test slice và service connection, thêm các module test tương ứng:

~~~groovy
testImplementation("org.springframework.boot:spring-boot-testcontainers")
testImplementation("org.springframework.boot:spring-boot-data-elasticsearch-test")
~~~

## 5. Khởi động Elasticsearch bằng Testcontainers

Testcontainers chạy image Elasticsearch chính thức trong Docker và cấp một port được ánh xạ động tới máy host. Không hard-code port host vì mỗi lần khởi động container, port có thể khác nhau.

Ví dụ dùng JUnit 5:

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.elasticsearch.ElasticsearchContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class ElasticsearchContainerIT {

    @Container
    static final ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer(
            DockerImageName.parse(
                "docker.elastic.co/elasticsearch/elasticsearch:9.4.7"
            )
        );

    @Test
    void containerStarts() {
        assertThat(elasticsearch.isRunning()).isTrue();
    }
}
~~~

Field static làm container được chia sẻ giữa các test method trong class: container khởi động trước test đầu tiên và dừng sau test cuối cùng. Nếu khai báo container ở instance field, Testcontainers sẽ khởi động và dừng container cho từng method, làm suite chậm hơn.

Không chạy nhiều test song song trên cùng một index dùng chung nếu các test có thể xóa hoặc ghi đè dữ liệu của nhau. Có thể dùng index riêng theo test hoặc cấu hình chạy tuần tự cho nhóm integration test.

### Elasticsearch 8 và 9 bật security mặc định

Từ Elasticsearch 8, security và HTTPS được bật mặc định. Khi test dùng image 8.x hoặc 9.x, client phải xử lý đúng TLS và authentication.

Với Spring Boot 4.1, có thể dùng ServiceConnection cùng Ssl để Boot tự nhận diện Elasticsearch container và cấu hình SSL cho client:

~~~java
import org.springframework.boot.data.elasticsearch.test.autoconfigure.DataElasticsearchTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.boot.testcontainers.service.connection.Ssl;
import org.junit.jupiter.api.Test;
import org.testcontainers.elasticsearch.ElasticsearchContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@DataElasticsearchTest
class ReactiveProductRepositoryContainerIT {

    @Container
    @ServiceConnection
    @Ssl
    static final ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer(
            DockerImageName.parse(
                "docker.elastic.co/elasticsearch/elasticsearch:9.4.7"
            )
        );

    // Inject repository và ReactiveElasticsearchOperations tại đây.
}
~~~

ServiceConnection cung cấp connection details cho auto-configuration. Ssl báo cho Spring Boot xử lý chứng chỉ TLS của Elasticsearch container. Đây là cách gọn khi phiên bản Spring Boot và Testcontainers hỗ trợ service connection tương ứng.

Với Spring Boot 3.x, package của DataElasticsearchTest khác và cấu hình service connection/SSL có thể khác theo minor version. Hãy dùng package và cơ chế SSL của đúng Spring Boot line trong dự án. Nếu tự cấu hình bằng DynamicPropertySource, chỉ truyền URI và credentials là chưa đủ khi server dùng TLS; client còn phải tin cậy CA certificate do container cung cấp.

Không tắt security của container chỉ để tránh cấu hình SSL nếu production dùng TLS/authentication. Integration test có giá trị hơn khi kết nối gần với cấu hình thực tế.

## 6. Entity và reactive repository mẫu

Ví dụ dùng một index sản phẩm có các field đơn giản:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "reactive-products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Boolean)
    private boolean active;

    public Product() {
    }

    public Product(
            String id,
            String name,
            String category,
            boolean active) {
        this.id = id;
        this.name = name;
        this.category = category;
        this.active = active;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public void setCategory(String category) {
        this.category = category;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

Reactive repository có thể khai báo các query method:

~~~java
import org.springframework.data.elasticsearch.repository.ReactiveElasticsearchRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    Flux<Product> findByCategory(String category);

    Flux<Product> findByCategoryOrderByNameAsc(String category);

    Mono<Product> findByName(String name);

    Mono<Long> countByCategory(String category);
}
~~~

Reactive Elasticsearch repository sử dụng Project Reactor. Các phương thức trả Mono hoặc Flux, không cần tự chuyển kết quả đồng bộ thành publisher.

Trong một test slice, repository và entity cần nằm trong package được Spring Boot scan. Nếu dùng EnableReactiveElasticsearchRepositories thủ công, hãy chỉ rõ package chứa repository.

## 7. Tạo và làm sạch index cho mỗi test

Một integration test cần dữ liệu độc lập. Nếu test trước để lại document, test sau có thể nhận thêm kết quả ngoài dự kiến.

ReactiveIndexOperations cung cấp API reactive để quản lý index. Có thể xóa index cũ rồi tạo lại index cùng mapping trước mỗi test.

~~~java
import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import org.springframework.data.elasticsearch.core.ReactiveIndexOperations;
import reactor.test.StepVerifier;

abstract class ReactiveElasticsearchTestSupport {

    @Autowired
    protected ReactiveElasticsearchOperations operations;

    protected ReactiveIndexOperations productIndex() {
        return operations.indexOps(Product.class);
    }

    @BeforeEach
    void recreateIndex() {
        StepVerifier.create(
                productIndex()
                    .delete()
                    .then(productIndex().createWithMapping())
            )
            .expectNext(true)
            .expectComplete()
            .verify(Duration.ofSeconds(30));
    }
}
~~~

delete() trả false nếu index chưa tồn tại. Vì vậy có thể gọi nó trước createWithMapping() mà không cần tự kiểm tra trạng thái bằng một request riêng.

createWithMapping() tạo index cùng settings và mapping lấy từ annotation của entity. Test này kiểm tra luôn mapping metadata mà Spring Data sinh ra.

Nếu index của test cần mapping thủ công, có thể dùng create(settings, mapping) hoặc tạo mapping riêng rồi kiểm tra kết quả bằng Elasticsearch thật.

### Không xóa index bằng lệnh đồng bộ giữa các test

Khi đã dùng reactive API, hãy giữ chuỗi quản lý index dưới dạng Mono:

~~~java
Mono<Boolean> recreate = productIndex()
    .delete()
    .then(productIndex().createWithMapping());
~~~

Không gọi subscribe() trong BeforeEach rồi để test tiếp tục chạy. Khi subscribe() trả về, thao tác bất đồng bộ có thể chưa hoàn tất. Dùng StepVerifier để chờ đến tín hiệu kết thúc trước khi test bắt đầu.

Các method lifecycle của JUnit vốn là synchronous, nên việc verify(Duration) chờ ở ranh giới test là hợp lý. Điều cần tránh là chặn bên trong luồng xử lý production reactive.

## 8. Kiểm thử lưu và đọc lại bằng ID

Test đầu tiên xác nhận save trả về entity có ID và Elasticsearch có thể đọc lại document.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import reactor.test.StepVerifier;

class ReactiveProductRepositoryCRUDIT
        extends ReactiveElasticsearchTestSupport {

    @Autowired
    ProductRepository repository;

    @Test
    void shouldSaveAndFindProductById() {
        Product product = new Product(
            "p-100",
            "Wireless Headphones",
            "audio",
            true
        );

        StepVerifier.create(repository.save(product))
            .assertNext(saved -> {
                assertThat(saved.getId()).isEqualTo("p-100");
                assertThat(saved.getName())
                    .isEqualTo("Wireless Headphones");
            })
            .expectComplete()
            .verify(Duration.ofSeconds(10));

        StepVerifier.create(repository.findById("p-100"))
            .assertNext(found -> {
                assertThat(found.getCategory()).isEqualTo("audio");
                assertThat(found.isActive()).isTrue();
            })
            .expectComplete()
            .verify(Duration.ofSeconds(10));
    }
}
~~~

findById thường dùng thao tác GET theo ID của Elasticsearch. GET là realtime theo cơ chế của Elasticsearch, vì vậy không cần đợi refresh để kiểm tra document vừa index bằng ID.

Điều này khác với search query. Một test tìm theo category hoặc query method có thể cần refresh trước khi đọc.

Nếu test cần xác nhận save() trả về một entity đã được mapping đúng, hãy kiểm tra các field trong assertNext, không chỉ kiểm tra publisher hoàn tất.

## 9. Kiểm thử query method cần refresh index

Elasticsearch là near-real-time search engine. Sau khi index một document, thao tác GET theo ID có thể thấy dữ liệu ngay, nhưng search không nhất thiết thấy document đó cho đến lần refresh tiếp theo.

Đừng dùng Thread.sleep() để chờ refresh. Thời gian refresh có thể thay đổi theo cấu hình và tải của cluster, khiến test vừa chậm vừa không ổn định.

Dùng reactive index operation:

~~~java
@Test
void shouldFindProductsByCategoryAfterRefresh() {
    Product first = new Product(
        "p-101", "Headphones", "audio", true
    );

    Product second = new Product(
        "p-102", "Speaker", "audio", true
    );

    StepVerifier.create(
            repository.saveAll(Flux.just(first, second))
                .then(productIndex().refresh())
                .thenMany(repository.findByCategoryOrderByNameAsc("audio"))
        )
        .assertNext(product ->
            assertThat(product.getName()).isEqualTo("Headphones")
        )
        .assertNext(product ->
            assertThat(product.getName()).isEqualTo("Speaker")
        )
        .expectComplete()
        .verify(Duration.ofSeconds(20));
}
~~~

Trong chuỗi trên:

1. saveAll lưu hai document.
2. then chờ toàn bộ thao tác lưu hoàn tất.
3. refresh yêu cầu Elasticsearch làm cho các thay đổi searchable.
4. thenMany chỉ chạy query sau khi refresh hoàn tất.
5. StepVerifier kiểm tra thứ tự và dữ liệu trả về.

ReactiveIndexOperations.refresh() trả về Mono<Void>, nên nó phát tín hiệu hoàn tất mà không phát giá trị. Dùng thenMany để chuyển sang Flux kết quả tìm kiếm sau refresh.

Cách này tránh race condition giữa ghi và search. Không nên chèn delayElement, Thread.sleep hoặc một khoảng chờ tùy ý để giả lập refresh.

## 10. Kiểm thử bulk save và số lượng document

Có thể dùng saveAll để kiểm tra thao tác lưu nhiều entity. Khi test số lượng, hãy refresh trước khi chạy search hoặc count nếu cần trạng thái searchable.

~~~java
@Test
void shouldSaveAllProductsAndCountByCategory() {
    List<Product> products = List.of(
        new Product("p-201", "Keyboard", "accessories", true),
        new Product("p-202", "Mouse", "accessories", true),
        new Product("p-203", "Monitor", "display", true)
    );

    Mono<Long> count = repository.saveAll(products)
        .then(productIndex().refresh())
        .then(repository.countByCategory("accessories"));

    StepVerifier.create(count)
        .expectNext(2L)
        .expectComplete()
        .verify(Duration.ofSeconds(20));
}
~~~

saveAll trả Flux<S>. Dùng then(...) để đợi Flux hoàn tất rồi mới thực hiện refresh và count.

Nếu test cần xác nhận từng entity được trả từ saveAll, có thể kiểm tra expectNextCount(3) hoặc thu thập list rồi assert. Không nên giả định thứ tự bulk response luôn giống thứ tự input nếu API hoặc implementation không cam kết thứ tự đó.

Ví dụ chỉ xác nhận số phần tử:

~~~java
StepVerifier.create(repository.saveAll(products))
    .expectNextCount(3)
    .expectComplete()
    .verify(Duration.ofSeconds(20));
~~~

Nếu phần tiếp theo của test cần search, hãy nối refresh vào cùng chuỗi thay vì chạy hai subscription độc lập.

## 11. Kiểm thử kết quả rỗng

Reactive repository thường biểu diễn không tìm thấy một entity bằng Mono.empty(). Với query trả nhiều kết quả, không có document phù hợp thì Flux hoàn tất mà không phát onNext.

Ví dụ:

~~~java
@Test
void shouldCompleteEmptyWhenProductDoesNotExist() {
    StepVerifier.create(repository.findById("missing-id"))
        .expectComplete()
        .verify(Duration.ofSeconds(10));
}
~~~

Với query method:

~~~java
@Test
void shouldReturnEmptyFluxWhenCategoryDoesNotExist() {
    StepVerifier.create(repository.findByCategory("unknown"))
        .expectComplete()
        .verify(Duration.ofSeconds(10));
}
~~~

Đừng dùng expectNext(null). Reactor không cho phép phát null như một phần tử của Mono hoặc Flux.

Nếu service biến kết quả rỗng thành lỗi nghiệp vụ bằng switchIfEmpty, hãy kiểm thử cả hai hành vi:

~~~java
Mono<Product> findRequired(String id) {
    return repository.findById(id)
        .switchIfEmpty(Mono.error(
            new ProductNotFoundException(id)
        ));
}
~~~

~~~java
StepVerifier.create(productService.findRequired("missing-id"))
    .expectErrorMatches(error ->
        error instanceof ProductNotFoundException
    )
    .verify(Duration.ofSeconds(10));
~~~

## 12. Kiểm thử delete và xác nhận document đã biến mất

Reactive repository có các phương thức delete trả publisher. Có thể kiểm tra thao tác xóa hoàn tất và sau đó xác nhận document không còn tồn tại.

~~~java
@Test
void shouldDeleteProduct() {
    Product product = new Product(
        "p-301", "Portable Speaker", "audio", true
    );

    Mono<Boolean> existsAfterDelete = repository.save(product)
        .then(repository.deleteById("p-301"))
        .then(productIndex().refresh())
        .then(repository.existsById("p-301"));

    StepVerifier.create(existsAfterDelete)
        .expectNext(false)
        .expectComplete()
        .verify(Duration.ofSeconds(20));
}
~~~

Đây là một chuỗi reactive duy nhất: lưu, xóa, refresh và kiểm tra. Nếu test chỉ gọi repository.deleteById(id) rồi ngay lập tức search, kết quả có thể bị ảnh hưởng bởi refresh timing.

Nếu chỉ cần xác nhận publisher delete hoàn tất, có thể kiểm tra:

~~~java
StepVerifier.create(repository.deleteById("p-301"))
    .expectComplete()
    .verify(Duration.ofSeconds(10));
~~~

Tuy nhiên, test trên chưa xác nhận document thực sự biến mất khỏi index. Với integration test, nên có ít nhất một test kiểm tra trạng thái sau delete.

## 13. Kiểm thử mapping và kiểu dữ liệu

Một trong những lý do quan trọng để dùng Elasticsearch thật là kiểm tra mapping được tạo từ annotation.

Ví dụ field category được khai báo Keyword, nên exact term query phải hoạt động theo giá trị đầy đủ. Nếu vô tình map thành Text, query và aggregation có thể có semantics khác.

Có thể kiểm tra mapping thông qua API index operations:

~~~java
@Test
void shouldCreateIndexWithExpectedMapping() {
    StepVerifier.create(productIndex().getMapping())
        .assertNext(mapping -> {
            assertThat(mapping.toJson())
                .contains("\"category\"");
            assertThat(mapping.toJson())
                .contains("\"keyword\"");
        })
        .expectComplete()
        .verify(Duration.ofSeconds(10));
}
~~~

Kiểu trả về của mapping API và cách serialize Document phụ thuộc Spring Data Elasticsearch version. Khi cần assertion chặt, nên parse mapping thành cấu trúc JSON hoặc dùng client API để kiểm tra property type thay vì chỉ so sánh chuỗi.

Mapping test nên tập trung vào những thuộc tính quan trọng:

- Field type (keyword, text, date, nested, numeric).
- Analyzer và search analyzer.
- Multi-field.
- Normalizer.
- Dynamic mapping.
- Routing và version metadata.
- Settings có ảnh hưởng tới search behavior.

Đừng chỉ kiểm tra entity có annotation. Test cần xác nhận mapping được Elasticsearch chấp nhận và truy vấn thật hoạt động theo ý định.

## 14. Kiểm thử custom query và analyzer bằng dữ liệu thật

Một repository query method đơn giản không đại diện cho tất cả query DSL. Nếu ứng dụng dùng @Query, NativeQuery, Criteria hoặc analyzer tùy chỉnh, hãy ghi một tập dữ liệu có chủ đích rồi kiểm tra kết quả từ Elasticsearch.

Ví dụ service:

~~~java
public Flux<Product> activeProducts(String category) {
    return repository.findByCategory(category)
        .filter(Product::isActive);
}
~~~

Test:

~~~java
@Test
void shouldReturnOnlyActiveProducts() {
    List<Product> products = List.of(
        new Product("p-401", "Headphones", "audio", true),
        new Product("p-402", "Speaker", "audio", false)
    );

    StepVerifier.create(
            repository.saveAll(products)
                .then(productIndex().refresh())
                .thenMany(productService.activeProducts("audio"))
        )
        .assertNext(product ->
            assertThat(product.getId()).isEqualTo("p-401")
        )
        .expectComplete()
        .verify(Duration.ofSeconds(20));
}
~~~

Ví dụ này kiểm tra cả repository query và operator filter ở service. Nếu filter được đẩy xuống Elasticsearch bằng query DSL, test cần gọi đúng phương thức đó để kiểm tra query engine thực thi.

Với full-text search, dữ liệu test nên chứa những trường hợp analyzer có thể xử lý khác nhau:

- Chữ hoa và chữ thường.
- Dấu câu.
- Từ có dấu và không dấu.
- Tokenization.
- Stop words.
- Synonym.
- Prefix hoặc n-gram.
- Ngôn ngữ mà analyzer hỗ trợ.

Đừng dùng một chuỗi quá đơn giản rồi kết luận analyzer production hoạt động đúng.

## 15. Kiểm thử lỗi và exception translation

Reactive client có thể phát lỗi khi:

- Elasticsearch không kết nối được.
- Authentication hoặc TLS thất bại.
- Index không tồn tại.
- Mapping từ chối dữ liệu.
- Query DSL không hợp lệ.
- Version conflict xảy ra.
- Request timeout hoặc server trả lỗi.

StepVerifier có thể kiểm tra lỗi được truyền xuống publisher:

~~~java
StepVerifier.create(
        repository.save(new Product(
            "p-501", null, "audio", true
        ))
    )
    .expectError()
    .verify(Duration.ofSeconds(10));
~~~

Ví dụ trên chỉ phát sinh lỗi nếu ứng dụng hoặc mapping thực sự có ràng buộc từ chối giá trị null. Elasticsearch không tự động coi mọi field thiếu là lỗi. Vì vậy, không nên viết test với giả định rằng field Java bắt buộc sẽ bị Elasticsearch từ chối nếu mapping không quy định điều đó.

Nếu cần kiểm tra lỗi mapping, hãy tạo mapping có ràng buộc kiểu dữ liệu cụ thể rồi gửi dữ liệu sai kiểu qua đường ghi thật. Khi đó kiểm tra exception class hoặc cause theo version của Spring Data và client đang dùng.

Không nên khẳng định exception class chính xác dựa trên một version khác. Spring Data có exception translation, nhưng lớp exception cụ thể phụ thuộc lỗi gốc và phiên bản thư viện.

## 16. Kiểm thử validation trước khi gọi Elasticsearch

Nhiều lỗi nghiệp vụ nên được chặn trước khi gửi request đến Elasticsearch. Có thể kiểm thử phần này bằng unit test, không cần container.

Ví dụ:

~~~java
public Mono<Product> create(Product product) {
    if (product.getName() == null || product.getName().isBlank()) {
        return Mono.error(
            new IllegalArgumentException("Product name is required")
        );
    }

    return repository.save(product);
}
~~~

Test:

~~~java
@Test
void shouldRejectProductWithoutName() {
    Product invalid = new Product(
        "p-601", " ", "audio", true
    );

    StepVerifier.create(productService.create(invalid))
        .expectErrorMatches(error ->
            error instanceof IllegalArgumentException
                && error.getMessage().equals(
                    "Product name is required"
                )
        )
        .verify(Duration.ofSeconds(2));
}
~~~

Đây là unit test cho nhánh validation. Nếu muốn xác nhận repository không bị gọi, dùng mock hoặc PublisherProbe/Mockito verifyNoInteractions theo cấu trúc service. Không cần khởi động Elasticsearch cho một điều kiện kiểm tra chuỗi đơn giản.

Integration test vẫn cần kiểm tra đường ghi hợp lệ để xác nhận service thực sự lưu dữ liệu.

## 17. RefreshPolicy và khả năng nhìn thấy dữ liệu trong test

Spring Data Elasticsearch có RefreshPolicy:

| Policy | Hành vi |
|---|---|
| NONE | Không yêu cầu refresh đặc biệt; dùng hành vi mặc định của cluster |
| IMMEDIATE | Refresh ngay sau thao tác ghi |
| WAIT_UNTIL | Chờ refresh tiếp theo làm thay đổi searchable |

Có thể tạo một instance operations dùng policy riêng:

~~~java
ReactiveElasticsearchOperations testOperations =
    operations.withRefreshPolicy(RefreshPolicy.WAIT_UNTIL);
~~~

Ví dụ:

~~~java
StepVerifier.create(testOperations.save(product, IndexCoordinates.of("reactive-products")))
    .expectNextMatches(saved ->
        saved.getId().equals(product.getId())
    )
    .expectComplete()
    .verify(Duration.ofSeconds(20));
~~~

Chữ ký save cụ thể có overload theo entity và index. Dùng overload phù hợp với Spring Data Elasticsearch version trong dự án.

Trong integration test, hai cách phổ biến để đảm bảo dữ liệu searchable là:

1. Gọi ReactiveIndexOperations.refresh() sau khi seed dữ liệu.
2. Dùng WAIT_UNTIL cho write cần được search ngay.

IMMEDIATE có thể khiến test đơn giản hơn nhưng gây thêm refresh và chi phí segment. Không nên bật refresh ngay cho mọi write trong production chỉ để test dễ viết.

Nếu dùng repository implementation mặc định, hành vi refresh của repository có thể khác template operations theo cấu hình và version. Hãy kiểm tra chính sách thực tế thay vì giả định mọi API save đều có cùng semantics.

## 18. Không dùng Thread.sleep để chờ Elasticsearch

Ví dụ không ổn định:

~~~java
repository.save(product).block();

Thread.sleep(1000);

List<Product> products = repository.findByCategory("audio")
    .collectList()
    .block();
~~~

Đoạn code trên có nhiều vấn đề:

- block làm test không còn mô tả publisher theo StepVerifier.
- Một giây có thể quá ngắn khi cluster bận.
- Một giây có thể dài không cần thiết khi cluster rảnh.
- Test dễ flaky trên CI.
- Hai subscription độc lập làm thứ tự thao tác khó đọc.

Cách rõ ràng hơn:

~~~java
StepVerifier.create(
        repository.save(product)
            .then(productIndex().refresh())
            .thenMany(repository.findByCategory("audio"))
    )
    .expectNextMatches(found ->
        found.getId().equals(product.getId())
    )
    .expectComplete()
    .verify(Duration.ofSeconds(20));
~~~

Ở đây, refresh là một bước trong reactive chain. Query chỉ chạy sau khi refresh hoàn tất.

## 19. Phân biệt realtime GET và near-real-time Search

Elasticsearch có hai hành vi đọc cần nhớ:

- GET document theo ID là realtime.
- Search dựa trên các segment đã refresh, nên near-real-time.

Vì vậy, test save rồi findById có thể thành công ngay, nhưng test save rồi query theo category cần refresh.

| Test case | Cần refresh trước khi đọc? |
|---|---|
| save() rồi findById() | Thường không, vì GET realtime |
| save() rồi existsById() | Thường không, vì kiểm tra theo ID |
| save() rồi query method theo field | Có thể cần |
| saveAll() rồi Search API | Có thể cần |
| save() rồi aggregation | Cần nếu aggregation phải thấy document mới |
| delete() rồi Search API | Cần để kết quả search phản ánh trạng thái mới |

Nếu test đang kiểm tra semantics của refresh, hãy tách riêng test đó. Không nên vô tình phụ thuộc refresh policy mặc định của môi trường.

## 20. Kiểm thử reactive callback và auditing

Spring Data Elasticsearch có reactive entity callback riêng, ví dụ:

- ReactiveBeforeConvertCallback.
- ReactiveAfterSaveCallback.
- ReactiveAfterLoadCallback.
- ReactiveAfterConvertCallback.
- ReactiveAuditingEntityCallback.

Một callback đồng bộ không tự động được dùng trong reactive template. Vì vậy, nếu ứng dụng dùng reactive API, hãy đăng ký callback reactive và kiểm tra chính callback đó.

Ví dụ callback trước khi convert:

~~~java
import org.reactivestreams.Publisher;
import org.springframework.data.elasticsearch.core.event.ReactiveBeforeConvertCallback;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ProductDefaultsCallback
        implements ReactiveBeforeConvertCallback<Product> {

    @Override
    public Publisher<Product> onBeforeConvert(
            Product product,
            IndexCoordinates index) {

        if (product.getCategory() == null) {
            product.setCategory("general");
        }

        return Mono.just(product);
    }
}
~~~

Integration test có thể lưu entity thiếu category qua reactive repository rồi đọc lại bằng ID:

~~~java
@Test
void shouldApplyReactiveBeforeConvertCallback() {
    Product product = new Product(
        "p-701", "Desk Lamp", null, true
    );

    StepVerifier.create(repository.save(product))
        .assertNext(saved ->
            assertThat(saved.getCategory()).isEqualTo("general")
        )
        .expectComplete()
        .verify(Duration.ofSeconds(10));

    StepVerifier.create(repository.findById("p-701"))
        .assertNext(found ->
            assertThat(found.getCategory()).isEqualTo("general")
        )
        .expectComplete()
        .verify(Duration.ofSeconds(10));
}
~~~

Để test callback bean thực sự được đăng ký trong application context, hãy dùng test slice hoặc SpringBootTest có import configuration chứa callback. Nếu callback không được load, test chỉ xác nhận hành vi của repository mà không kiểm tra callback.

Với auditing, cần bật EnableReactiveElasticsearchAuditing và cung cấp ReactiveAuditorAware nếu entity dùng CreatedBy hoặc LastModifiedBy. Có thể dùng một auditor cố định trong test configuration để assertion xác định.

## 21. Kiểm thử Reactor Context

Một số ứng dụng truyền thông tin tenant, security principal hoặc correlation ID qua Reactor Context. StepVerifier hỗ trợ kiểm tra context được truyền vào publisher.

Ví dụ:

~~~java
StepVerifier.create(
        Mono.deferContextual(context ->
            Mono.just(context.get("tenantId"))
        ),
        StepVerifierOptions.create()
            .withInitialContext(Context.of("tenantId", "tenant-7"))
    )
    .expectAccessibleContext()
    .contains("tenantId", "tenant-7")
    .then()
    .expectNext("tenant-7")
    .expectComplete()
    .verify(Duration.ofSeconds(2));
~~~

Đối với Elasticsearch, có thể dùng context để xác định tenant hoặc actor ở service layer, rồi xác nhận query hoặc callback sử dụng đúng giá trị.

Tuy nhiên, không giả định mọi Reactor Context tự động trở thành Elasticsearch routing hoặc security metadata. Ứng dụng phải có logic rõ ràng để chuyển context thành query filter, routing hoặc audit actor.

## 22. Kiểm thử backpressure và cancellation

Flux có thể phát nhiều kết quả. Nếu service cần tuân thủ backpressure, StepVerifier cho phép điều khiển số phần tử được yêu cầu.

Ví dụ:

~~~java
StepVerifier.create(
        repository.findByCategory("audio"),
        0
    )
    .thenRequest(1)
    .expectNextCount(1)
    .thenRequest(1)
    .expectNextCount(1)
    .thenCancel()
    .verify(Duration.ofSeconds(10));
~~~

Kịch bản này kiểm tra consumer chỉ yêu cầu từng phần tử và sau đó hủy subscription.

Với query Elasticsearch thực, cancellation có thể xảy ra sau khi request đã được gửi đến server. Không nên giả định mọi cancellation đều lập tức dừng toàn bộ công việc trên Elasticsearch. Test này xác nhận hành vi publisher ở phía client; để kiểm tra resource usage hoặc cancellation propagation sâu hơn cần instrumentation và test chuyên biệt.

## 23. Virtual time không thay thế Elasticsearch thật

StepVerifier.withVirtualTime hữu ích cho publisher có timer, delay, retry backoff hoặc interval:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofHours(1))
    )
    .expectSubscription()
    .thenAwait(Duration.ofHours(1))
    .expectNext(0L)
    .expectComplete()
    .verify(Duration.ofSeconds(2));
~~~

Virtual time điều khiển scheduler của Reactor. Nó không làm đồng hồ của Elasticsearch, network hoặc refresh engine chạy nhanh hơn.

Không dùng virtual time để giả lập việc index document rồi chờ Elasticsearch refresh. Hãy gọi refresh API hoặc dùng refresh policy phù hợp.

Nếu service có retry với backoff trước khi gọi Elasticsearch, có thể tách phần retry policy thành unit test dùng virtual time, còn đường gọi repository thật được kiểm tra bằng integration test.

## 24. Dùng TestPublisher và PublisherProbe ở đúng chỗ

reactor-test còn có TestPublisher và PublisherProbe.

TestPublisher giúp phát tín hiệu theo ý muốn để kiểm tra operator hoặc service logic mà không cần Elasticsearch.

~~~java
TestPublisher<String> publisher = TestPublisher.create();

StepVerifier.create(
        publisher.flux().map(String::toUpperCase)
    )
    .then(() -> publisher.emit("audio", "video"))
    .expectNext("AUDIO", "VIDEO")
    .expectComplete()
    .verify(Duration.ofSeconds(2));
~~~

PublisherProbe giúp xác nhận một publisher thay thế có được subscribe hay không, ví dụ nhánh switchIfEmpty.

Những công cụ này rất phù hợp cho unit test reactive. Không dùng chúng thay cho integration test khi cần xác nhận Elasticsearch thực sự lưu và tìm document.

## 25. Dùng DataElasticsearchTest hay SpringBootTest?

Spring Boot cung cấp DataElasticsearchTest để giới hạn context vào thành phần dữ liệu Elasticsearch. Test slice thường phù hợp khi chỉ cần repository, entity mapping và template.

Dùng SpringBootTest khi test cần toàn bộ application context, ví dụ:

- Service có nhiều dependency.
- Reactive security configuration.
- Custom converter hoặc callback được cấu hình ở tầng ứng dụng.
- WebFlux controller và service.
- Bean routing hoặc tenant resolution.

| Annotation | Phạm vi | Khi phù hợp |
|---|---|---|
| DataElasticsearchTest | Các thành phần data Elasticsearch | Repository, mapping, template |
| SpringBootTest | Application context đầy đủ | Luồng tích hợp nhiều bean |
| JUnit test thuần | Không cần Spring context | Publisher utility, validation, mapper |

Trong Spring Boot 4, package DataElasticsearchTest là org.springframework.boot.data.elasticsearch.test.autoconfigure. Trong Spring Boot 3.x, package phổ biến là org.springframework.boot.test.autoconfigure.data.elasticsearch.

Khi test slice không tự load một service hoặc callback bean cần thiết, có thể import configuration cụ thể bằng Import thay vì mở toàn bộ application context.

## 26. DynamicPropertySource khi không dùng ServiceConnection

Nếu phiên bản Spring Boot hoặc cách cấu hình dự án không dùng được ServiceConnection, DynamicPropertySource cho phép đăng ký property động sau khi Testcontainers khởi động.

Ví dụ về nguyên tắc:

~~~java
@Container
static final ElasticsearchContainer elasticsearch =
    new ElasticsearchContainer(ELASTICSEARCH_IMAGE);

@DynamicPropertySource
static void elasticsearchProperties(
        DynamicPropertyRegistry registry) {

    registry.add(
        "spring.elasticsearch.uris",
        elasticsearch::getHttpHostAddress
    );
}
~~~

Đoạn này chỉ minh họa cách cung cấp URI cho cấu hình client phù hợp. Với Elasticsearch 8/9 mặc định bật HTTPS và authentication, ứng dụng còn cần username, password và SSL trust configuration. getHttpHostAddress() không tự cấu hình chứng chỉ cho client.

Nếu dùng TLS, ưu tiên Ssl/ServiceConnection khi Spring Boot hỗ trợ, hoặc tự tạo client bean với CA certificate từ container. Không tắt xác thực SSL trong test một cách tùy tiện rồi coi đó là cấu hình tương đương production.

Dynamic properties có precedence cao trong Spring TestContext, nên phù hợp để thay địa chỉ service theo từng test run.

## 27. Test dữ liệu bằng ReactiveElasticsearchOperations

Không phải test nào cũng cần repository. Khi cần kiểm tra một query cụ thể, có thể inject ReactiveElasticsearchOperations.

Ví dụ lưu rồi đọc bằng operations:

~~~java
@Test
void shouldUseReactiveOperationsForSaveAndSearch() {
    Product product = new Product(
        "p-801", "Studio Monitor", "audio", true
    );

    Mono<Product> saveAndRefresh = operations.save(product)
        .flatMap(saved ->
            productIndex().refresh().thenReturn(saved)
        );

    StepVerifier.create(
            saveAndRefresh.flatMapMany(saved ->
                operations.search(
                    Query.findAll(),
                    Product.class
                )
            )
        )
        .expectNextMatches(hit ->
            hit.getContent().getId().equals("p-801")
        )
        .expectComplete()
        .verify(Duration.ofSeconds(20));
}
~~~

Chữ ký search và kiểu trả về có thể khác nhau theo overload. Nếu dùng ReactiveElasticsearchOperations.search(Query, Class<T>), publisher phát SearchHit<T>; nếu dùng overload khác, hãy kiểm tra đúng kiểu của API trong version dự án.

Điểm quan trọng là query, refresh và search đều nằm trong một chuỗi reactive, để thứ tự được bảo đảm.

Với query DSL phức tạp, nên giữ query builder trong service và test qua chính service đó. Nếu test tự dựng query khác với production query, test có thể xanh trong khi code thật vẫn sai.

## 28. Kiểm thử dữ liệu có tính xác định

Integration test cần dữ liệu nhỏ nhưng được thiết kế để phân biệt các trường hợp.

Ví dụ dataset cho category:

| ID | Name | Category | Active |
|---|---|---|---|
| p-1 | Headphones | audio | true |
| p-2 | Speaker | audio | false |
| p-3 | Keyboard | accessories | true |

Với dataset này có thể kiểm tra:

- Query category audio trả đúng hai document.
- Filter active chỉ giữ p-1.
- Sort name trả kết quả theo thứ tự xác định.
- Count category audio bằng hai.
- Delete p-2 làm count còn một sau refresh.
- Search category không tồn tại trả Flux rỗng.

Không dùng ID ngẫu nhiên cho mọi assertion nếu test cần kiểm tra thứ tự hoặc so sánh cụ thể. Có thể dùng ID cố định trong index riêng của test.

Nếu dữ liệu được sinh ngẫu nhiên để test tải, hãy cố định seed để có thể tái hiện lỗi.

## 29. Kiểm thử với nhiều test method và dữ liệu song song

Testcontainers JUnit Jupiter hỗ trợ container static dùng chung giữa các method và container instance khởi động riêng từng method.

Với container static, mỗi test method vẫn phải cô lập dữ liệu. Có thể:

- Xóa và tạo lại index trước mỗi test.
- Dùng index name riêng theo test.
- Dùng ID có prefix riêng.
- Xóa dữ liệu sau khi test kết thúc.

Không để hai test cùng xóa một index khi chạy song song.

JUnit Jupiter integration của Testcontainers được kiểm thử với execution tuần tự; chạy song song có thể tạo tương tác không mong muốn nếu container hoặc dữ liệu được chia sẻ. Nếu muốn bật parallel execution, cần thiết kế index isolation và lifecycle riêng, sau đó kiểm tra concurrency thực tế.

## 30. Kiểm thử hiệu năng không đồng nghĩa kiểm thử chức năng

Một integration test với vài document chỉ xác nhận correctness. Nó không chứng minh ứng dụng có thể xử lý hàng triệu document hoặc nhiều request đồng thời.

Không dùng thời gian chạy của một test JUnit nhỏ làm benchmark. Hiệu năng phụ thuộc:

- Kích thước và cấu trúc index.
- Số shard và replica.
- Mapping, analyzer và aggregation.
- Refresh interval.
- Số request đồng thời.
- Network, CPU, heap và disk.
- Cache state.
- Kích thước response và tốc độ consumer.

Nếu cần benchmark, hãy dùng môi trường và workload riêng, có dữ liệu đại diện và đo latency percentile, throughput, heap và tải cluster.

## 31. Những lỗi thường gặp

**Tạo publisher nhưng không gọi verify.** Publisher chưa được subscribe nên thao tác lưu có thể chưa chạy.

**Gọi subscribe trong test rồi không chờ.** Test có thể kết thúc trước khi thao tác Elasticsearch hoàn tất.

**Dùng block ở mọi nơi.** Điều đó làm test khó mô tả tín hiệu reactive và dễ tạo thứ tự không rõ ràng. Dùng StepVerifier cho publisher đang kiểm tra.

**Dùng Thread.sleep để đợi refresh.** Thời gian cố định gây flaky. Dùng ReactiveIndexOperations.refresh() hoặc refresh policy.

**Nhầm GET theo ID với Search.** GET realtime có thể thấy document mới trước khi search thấy nó.

**Mock repository rồi kết luận mapping đúng.** Mock không chạy query engine và không kiểm tra mapping thực.

**Dùng embedded fake thay cho Elasticsearch khi test query DSL.** Các hành vi analyzer, mapping, aggregation và refresh cần engine thật.

**Không reset index.** Dữ liệu từ test trước có thể làm sai số lượng hoặc thứ tự kết quả.

**Chạy test song song trên cùng index.** Một test xóa index trong khi test khác đang search sẽ gây lỗi khó tái hiện.

**Không đặt timeout cho StepVerifier.** Network hoặc publisher bị treo có thể làm test chờ vô hạn.

**Dùng virtual time để chờ Elasticsearch refresh.** Virtual scheduler không điều khiển server thật.

**Kỳ vọng null được phát từ Mono.** Reactor không phát null; kết quả không có dữ liệu được biểu diễn bằng empty completion.

**Kiểm tra chỉ một phần tử rồi bỏ qua phần còn lại.** Với Flux, cần kiểm tra số lượng hoặc terminal signal để chắc chắn publisher không phát thêm giá trị ngoài dự kiến.

**Giả định thứ tự bulk save luôn giống input.** Chỉ assert thứ tự khi API query có sort rõ ràng hoặc contract bảo đảm điều đó.

**Dùng image Elasticsearch không tương thích với client.** Test phải chạy trên phiên bản server được Spring Data line hỗ trợ.

**Tắt security/TLS trong test nhưng không test cấu hình production.** Điều đó có thể bỏ sót lỗi certificate, authentication hoặc connection details.

**Dùng test slice nhưng quên callback/service bean.** DataElasticsearchTest giới hạn component scan; import bean cần thiết hoặc dùng SpringBootTest.

**Kiểm tra service reactive nhưng không kiểm tra dữ liệu thật.** Một publisher có thể phát đúng object giả mà không lưu document vào Elasticsearch.

## 32. Quy trình viết một integration test hoàn chỉnh

Một test có thể đi theo trình tự:

1. Khởi động Elasticsearch bằng Testcontainers.
2. Cấu hình Spring Data reactive client trỏ đến container.
3. Tạo index và mapping bằng reactive index operations.
4. Chuẩn bị document qua repository hoặc template.
5. Dùng StepVerifier để xác nhận publisher lưu hoàn tất.
6. Refresh index nếu bước tiếp theo dùng Search API.
7. Chạy query thực qua repository/template.
8. Dùng assertNext, expectNextCount hoặc collectList để kiểm tra kết quả.
9. Kiểm tra terminal signal bằng expectComplete hoặc expectError.
10. Dùng timeout để tránh test treo.
11. Xóa index hoặc dữ liệu để test sau độc lập.

Một test tổng hợp:

~~~java
@Test
void shouldIndexSearchAndDeleteProduct() {
    Product product = new Product(
        "p-901", "Noise Cancelling Headphones", "audio", true
    );

    Mono<Boolean> existsAfterDelete = repository.save(product)
        .then(productIndex().refresh())
        .then(repository.findByCategory("audio").collectList())
        .flatMap(found -> {
            assertThat(found)
                .extracting(Product::getId)
                .contains("p-901");

            return repository.deleteById("p-901")
                .then(productIndex().refresh())
                .then(repository.existsById("p-901"));
        });

    StepVerifier.create(existsAfterDelete)
        .expectNext(false)
        .expectComplete()
        .verify(Duration.ofSeconds(30));
}
~~~

Test này kiểm tra cả chuỗi thao tác và trạng thái trong Elasticsearch. Nếu một bước lỗi, publisher kết thúc bằng error và StepVerifier báo lỗi tại test.

Với suite lớn, nên tách các hành vi thành test nhỏ: save/read, query/search, delete, callback, error và refresh. Test tổng hợp chỉ nên giữ cho một luồng nghiệp vụ quan trọng.

## Kết luận

StepVerifier giúp kiểm thử Mono và Flux bằng cách mô tả các tín hiệu cần nhận, thứ tự giá trị, lỗi, hoàn tất, cancellation và backpressure. Lệnh verify() là bước kích hoạt subscription; nên đặt timeout cho test có network I/O.

Để xác nhận Spring Data Elasticsearch reactive hoạt động đúng với search engine, hãy chạy integration test trên Elasticsearch thật bằng Testcontainers. Tạo index và mapping cho từng test, ghi dữ liệu qua reactive repository hoặc template, refresh trước khi search, rồi kiểm tra kết quả bằng StepVerifier. Dùng GET theo ID khi cần kiểm tra realtime read và Search API khi cần xác nhận dữ liệu đã searchable.

Không dùng mock để thay thế test mapping hoặc query DSL, không dùng Thread.sleep() để đợi refresh và không chặn publisher tùy tiện bằng block() trong chuỗi reactive. Kết hợp unit test cho logic nghiệp vụ với integration test cho hành vi engine sẽ tạo một bộ kiểm thử nhanh, ổn định và có khả năng phát hiện lỗi thực tế.

## Tài liệu tham khảo

- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Project Reactor — StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
- [Spring Data Elasticsearch — Reactive Elasticsearch Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/6.1/elasticsearch/repositories/reactive-elasticsearch-repositories.html)
- [Spring Data Elasticsearch — Version compatibility](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/versions.html)
- [Spring Data Elasticsearch — ReactiveElasticsearchTemplate API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ReactiveElasticsearchTemplate.html)
- [Spring Data Elasticsearch — ReactiveElasticsearchOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ReactiveElasticsearchOperations.html)
- [Spring Data Elasticsearch — ReactiveIndexOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ReactiveIndexOperations.html)
- [Spring Boot — Working with Elasticsearch](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Spring Boot — Testcontainers and Service Connections](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Testcontainers — Elasticsearch module](https://java.testcontainers.org/modules/elasticsearch/)
- [Testcontainers — JUnit Jupiter integration](https://java.testcontainers.org/test_framework_integration/junit_5/)
