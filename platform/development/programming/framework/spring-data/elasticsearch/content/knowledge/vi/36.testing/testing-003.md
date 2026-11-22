# Khởi chạy Elasticsearch bằng Testcontainers tương thích phiên bản

Integration test cho Spring Data Elasticsearch cần một Elasticsearch server thật để kiểm tra mapping, query DSL, repository, bulk operation và hành vi của client. Mock repository hoặc mock HTTP response không thể xác nhận rằng ứng dụng thực sự tương thích với server Elasticsearch đang chạy.

Testcontainers giúp khởi chạy Elasticsearch trong Docker ngay trong vòng đời test. Điểm quan trọng là chọn đúng phiên bản image: phiên bản server phải nằm trong phạm vi tương thích của Spring Data Elasticsearch và Elasticsearch Java API Client mà dự án đang dùng. Nếu dùng tag trôi nổi như latest, test có thể hôm nay chạy được nhưng ngày mai tự thay đổi hành vi khi image mới được phát hành.

Bài này hướng dẫn cách kiểm tra compatibility, pin phiên bản image, cấu hình container, kết nối Spring Boot/Spring Data, viết integration test và xử lý các lỗi thường gặp trong CI.

## 1. Vì sao dùng Testcontainers?

### 1.1. Unit test và integration test kiểm tra hai điều khác nhau

Unit test phù hợp để kiểm tra logic ứng dụng độc lập với Elasticsearch:

- Xây dựng query theo input.
- Chuyển đổi DTO và entity.
- Tính toán giá trị nghiệp vụ.
- Xử lý lỗi và retry ở tầng service.
- Kiểm tra mapper hoặc callback bằng mock.

Integration test cần kiểm tra tương tác thực tế giữa Spring Data, client và Elasticsearch server:

- Mapping được tạo đúng.
- Field type, analyzer và nested mapping được server chấp nhận.
- Repository save/find/search hoạt động.
- Query DSL thực sự chạy được.
- Bulk response có đúng semantics.
- Sort, aggregation, pagination và highlight tương thích.
- Version server không gây lỗi với client của ứng dụng.

Mock không thể xác nhận những hành vi phụ thuộc vào parser, mapping engine, query execution hoặc security của Elasticsearch.

### 1.2. Testcontainers cung cấp môi trường gần production

Testcontainers tạo container tạm thời từ Docker image, expose port động cho test và dọn container khi lifecycle kết thúc.

~~~mermaid
flowchart TD
    A[JUnit test starts] --> B[Testcontainers starts Elasticsearch image]
    B --> C[Container waits until ready]
    C --> D[Spring context receives host and mapped port]
    D --> E[Spring Data client connects]
    E --> F[Integration tests run]
    F --> G[Container is stopped and removed]
~~~

Môi trường này giúp test chạy với server Elasticsearch thật nhưng không yêu cầu developer tự cài Elasticsearch trên máy.

### 1.3. Testcontainers không tự đảm bảo version compatibility

Testcontainers chỉ khởi chạy image mà test yêu cầu. Nó không tự chọn server version phù hợp với Spring Data Elasticsearch.

Ứng dụng vẫn có thể khởi chạy container thành công nhưng gặp lỗi ở bước tạo client, mapping, query hoặc response conversion nếu version không tương thích.

Vì vậy, compatibility phải được xác định trước khi viết test.

## 2. Xác định phiên bản Elasticsearch tương thích

### 2.1. Có nhiều phiên bản tham gia vào một integration test

Một test thường có ít nhất ba thành phần version:

1. Spring Boot và Spring Data Elasticsearch.
2. Elasticsearch Java API Client hoặc client transport mà Spring Data sử dụng.
3. Elasticsearch server Docker image.

Ngoài ra còn có Testcontainers library và JUnit integration module. Những thành phần này cũng cần tương thích với JDK, Docker runtime và nhau.

Không chỉ nhìn vào version của Spring Boot để chọn Elasticsearch image. Hãy kiểm tra dependency thực tế mà Maven/Gradle resolve.

### 2.2. Kiểm tra release train của Spring Data Elasticsearch

Spring Data Elasticsearch công bố compatibility information cho từng release train. Hãy xác định:

- Phiên bản Spring Boot đang dùng.
- Phiên bản Spring Data Elasticsearch do dependency management quản lý.
- Phiên bản Elasticsearch server được release train đó hỗ trợ.
- Phiên bản Elasticsearch Java API Client được Spring Data sử dụng.

Nếu dùng Spring Boot dependency management, nên giữ Spring Data và Elasticsearch client theo bộ version mà Boot quản lý, trừ khi dự án có lý do rõ ràng để override.

Không tự nâng riêng client hoặc server lên bản mới nhất rồi giả định tương thích.

### 2.3. Kiểm tra dependency tree

Với Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-elasticsearch,co.elastic.clients:elasticsearch-java,org.elasticsearch.client:*
~~~

Với Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-data-elasticsearch --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency elasticsearch-java --configuration testRuntimeClasspath
~~~

Các lệnh này cho biết version được resolve thực tế, kể cả khi dependency đến gián tiếp từ Spring Boot BOM.

Nếu dependency tree cho thấy nhiều client hoặc một version bị override ngoài ý muốn, xử lý dependency management trước khi chọn image.

### 2.4. Dùng compatibility matrix của đúng release

Quy trình chọn image:

1. Đọc version Spring Data Elasticsearch trong dependency tree.
2. Mở compatibility matrix hoặc release documentation tương ứng.
3. Xác định dải Elasticsearch server được hỗ trợ.
4. Chọn một patch version cụ thể trong dải đó.
5. Dùng cùng version trong local, CI và các test profile liên quan.
6. Ghi version này thành một property hoặc constant duy nhất.

Không dùng một compatibility matrix của release train khác. Spring Data Elasticsearch có thay đổi theo từng major/minor release, nên version phù hợp với dự án cũ có thể không phù hợp với dự án mới.

### 2.5. Pin image bằng version cụ thể

Ví dụ một image tag cụ thể:

~~~text
docker.elastic.co/elasticsearch/elasticsearch:8.17.0
~~~

Version 8.17.0 chỉ là ví dụ minh họa. Hãy thay bằng version đã xác nhận tương thích với dependency của dự án.

Tránh các tag:

- latest.
- 8.
- 8.x.
- Một tag không chỉ rõ patch version.
- Một biến môi trường không được kiểm soát có thể tự đổi version giữa các lần chạy.

Tag cụ thể giúp kết quả test có thể lặp lại. Với yêu cầu reproducibility cao hơn, có thể pin thêm image digest sau khi xác nhận image chính thức.

### 2.6. Testcontainers version và Elasticsearch image version là hai thứ khác nhau

Version của dependency Testcontainers không phải version Elasticsearch server.

Ví dụ:

- Testcontainers library: version quản lý API Java và Docker integration.
- Elasticsearch image: version server được Docker pull.
- Elasticsearch Java API Client: version client được Spring Data dùng.

Nâng Testcontainers không có nghĩa là phải nâng Elasticsearch server. Ngược lại, nâng image không tự nâng client dependency.

Quản lý ba version này độc lập nhưng có kiểm tra compatibility.

## 3. Khai báo dependency Testcontainers

### 3.1. Maven dependencies

Với Testcontainers Java 1.x, các module thường dùng gồm Elasticsearch module và JUnit Jupiter integration:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>1.20.4</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>elasticsearch</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Version 1.20.4 ở đây chỉ minh họa cách import BOM. Dự án phải chọn một version Testcontainers được hỗ trợ bởi JDK, JUnit và dependency policy của nó.

Testcontainers major release mới có thể thay đổi cách chia module hoặc artifact coordinates. Khi nâng major, kiểm tra hướng dẫn dependency của đúng version thay vì trộn artifact của hai major.

### 3.2. Gradle dependencies

Ví dụ Gradle dùng version catalog hoặc BOM:

~~~kotlin
dependencies {
    testImplementation(platform("org.testcontainers:testcontainers-bom:1.20.4"))
    testImplementation("org.testcontainers:elasticsearch")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Version trong ví dụ cần được thay theo version Testcontainers đã chọn. Nếu dự án dùng Gradle version catalog, khai báo version ở một nơi để tránh module Testcontainers lệch version.

### 3.3. Đặt dependency ở test scope

Testcontainers chỉ phục vụ test. Không đưa Elasticsearch container module vào runtime classpath của ứng dụng production.

Dùng Maven test scope hoặc Gradle testImplementation. Nếu class test được đặt nhầm trong source set production, cần sửa source layout thay vì tăng scope dependency.

### 3.4. Không tự thêm Elasticsearch server dependency vào ứng dụng

Docker image đã cung cấp Elasticsearch server. Ứng dụng test chỉ cần Spring Data/client và Testcontainers module.

Không thêm một dependency Java chỉ để “chạy server Elasticsearch” trong cùng JVM trừ khi dự án có use case riêng. Elasticsearch server là process riêng trong container.

## 4. Tạo ElasticsearchContainer

### 4.1. Khởi tạo container với image đã pin

Ví dụ JUnit 5:

~~~java
import org.testcontainers.elasticsearch.ElasticsearchContainer;
import org.testcontainers.utility.DockerImageName;

ElasticsearchContainer elasticsearch =
    new ElasticsearchContainer(
        DockerImageName.parse(
            "docker.elastic.co/elasticsearch/elasticsearch:8.17.0"
        )
    );
~~~

Class ElasticsearchContainer thuộc module Elasticsearch của Testcontainers. Image name phải là image mà module hỗ trợ.

Một số version của Testcontainers có thể kiểm tra image compatibility qua DockerImageName. Không dùng asCompatibleSubstituteFor để bỏ qua cảnh báo nếu image thực tế không tương thích; chỉ khai báo substitute khi đã xác minh image thay thế có cùng contract.

### 4.2. Cấu hình single-node cho integration test

Một container test thường chạy một node:

~~~java
static final ElasticsearchContainer ELASTICSEARCH =
    new ElasticsearchContainer(
        DockerImageName.parse(
            "docker.elastic.co/elasticsearch/elasticsearch:8.17.0"
        )
    )
    .withEnv("discovery.type", "single-node")
    .withEnv("xpack.security.enabled", "false")
    .withEnv("ES_JAVA_OPTS", "-Xms512m -Xmx512m");
~~~

Cấu hình này phù hợp với test chức năng cơ bản trong môi trường cô lập:

- Single node tránh yêu cầu discovery cluster nhiều node.
- Tắt security giúp ví dụ CRUD đơn giản không phải cấp credential.
- Heap giới hạn để container không chiếm quá nhiều memory trên máy test.

Đây là cấu hình test, không phải cấu hình production. Nếu ứng dụng production yêu cầu TLS, API key hoặc security enabled, cần có integration test riêng kiểm tra chính các cơ chế đó.

### 4.3. Không dùng container test thay cho cluster production

Một node container không kiểm tra được đầy đủ:

- Replica allocation và failover.
- Multi-node discovery.
- Shard relocation.
- Cluster-wide availability.
- Rolling upgrade.
- Network partition giữa node.
- Hiệu năng ở quy mô production.

Testcontainers cung cấp một Elasticsearch thật trong phạm vi test, nhưng topology cần được mở rộng nếu bài test muốn xác minh hành vi cluster nhiều node.

### 4.4. Đặt startup timeout hợp lý

Có thể tăng startup timeout khi image lớn hoặc CI có tốc độ pull chậm:

~~~java
.withStartupTimeout(Duration.ofMinutes(2));
~~~

Không tăng timeout quá lớn để che giấu lỗi image hoặc Docker. Nếu container không sẵn sàng, hãy xem logs, exit code, memory và health check.

### 4.5. Wait strategy và readiness

Elasticsearch cần thời gian khởi động JVM, load plugin, bootstrap và mở HTTP endpoint. Test không nên bắt đầu ngay sau khi Docker tạo container.

Testcontainers module có thể đã cung cấp wait strategy phù hợp. Nếu tự cấu hình, dùng một điều kiện readiness có thể xác minh endpoint Elasticsearch phản hồi, ví dụ HTTP GET / với status mong đợi khi security đang tắt.

Không chỉ kiểm tra container đang chạy. Process có thể còn sống nhưng Elasticsearch chưa sẵn sàng nhận request.

## 5. Quản lý vòng đời container bằng JUnit Jupiter

### 5.1. Container dùng chung trong một test class

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class ProductRepositoryIntegrationTest {

    @Container
    static final ElasticsearchContainer ELASTICSEARCH =
        new ElasticsearchContainer(
            DockerImageName.parse(
                "docker.elastic.co/elasticsearch/elasticsearch:8.17.0"
            )
        )
        .withEnv("discovery.type", "single-node")
        .withEnv("xpack.security.enabled", "false")
        .withEnv("ES_JAVA_OPTS", "-Xms512m -Xmx512m");

}
~~~

Container static được chia sẻ giữa các test method trong cùng class. Container instance không static thường được tạo và dừng theo từng test method, làm test chậm hơn.

### 5.2. Dùng container static để giảm thời gian

Elasticsearch là process tương đối nặng. Khởi động một container cho mỗi method thường không cần thiết nếu các test có thể cô lập dữ liệu bằng index riêng hoặc cleanup.

Có thể dùng một container cho một class hoặc một test suite. Chọn phạm vi theo yêu cầu isolation và cách Spring test context được cache.

### 5.3. Lưu ý Spring TestContext cache

Spring có thể cache ApplicationContext giữa các test class. Nếu container static thuộc một class bị dừng sau class đó nhưng Spring giữ lại context dùng cùng endpoint, class tiếp theo có thể dùng context trỏ tới container đã dừng.

Một số cách xử lý:

- Dùng một singleton container được quản lý xuyên suốt test suite.
- Chia context/test class để không tái sử dụng context sau khi container dừng.
- Dùng @DirtiesContext khi cần buộc Spring loại bỏ context.
- Tổ chức test suite sao cho vòng đời container dài hơn vòng đời context.

Không thêm @DirtiesContext bừa bãi cho mọi test vì có thể làm suite chậm đáng kể.

### 5.4. Singleton container cho nhiều test class

Một pattern là tạo class holder dùng chung:

~~~java
public final class ElasticsearchTestContainer {

    public static final ElasticsearchContainer INSTANCE =
        new ElasticsearchContainer(
            DockerImageName.parse(
                "docker.elastic.co/elasticsearch/elasticsearch:8.17.0"
            )
        )
        .withEnv("discovery.type", "single-node")
        .withEnv("xpack.security.enabled", "false");

    static {
        INSTANCE.start();
    }

    private ElasticsearchTestContainer() {
    }
}
~~~

Các test class tham chiếu cùng INSTANCE. Đây là pattern cần quản lý lifecycle rõ ràng; đừng đồng thời đăng ký cùng container vào nhiều @Container field.

Nếu dùng singleton, bảo đảm container chỉ được start một lần và có quy tắc dọn dẹp khi JVM test kết thúc. Testcontainers/Ryuk thường hỗ trợ cleanup container được tạo trong test session, nhưng CI vẫn cần kết thúc process đúng cách.

### 5.5. Tùy chọn bỏ qua test khi không có Docker

JUnit integration của Testcontainers có tùy chọn bỏ qua test khi Docker không khả dụng ở một số version:

~~~java
@Testcontainers(disabledWithoutDocker = true)
~~~

Tùy chọn này tiện cho môi trường developer không có Docker. Với CI bắt buộc chạy integration test, không nên âm thầm skip khi Docker agent bị cấu hình sai. Hãy để pipeline fail rõ ràng hoặc có một job riêng được đánh dấu optional.

## 6. Kết nối Spring Boot với port động

### 6.1. Không hardcode localhost:9200

Testcontainers thường map port container sang một port ngẫu nhiên trên host để tránh xung đột với Elasticsearch local hoặc test khác.

Không giả định server luôn ở localhost:9200. Lấy host và mapped port từ container:

~~~java
String address = ELASTICSEARCH.getHttpHostAddress();
~~~

Giá trị trả về thường có dạng host:mappedPort. Dùng địa chỉ này để cấu hình Spring.

### 6.2. Dùng DynamicPropertySource

Với Spring Boot version sử dụng property spring.elasticsearch.uris, có thể đăng ký endpoint động:

~~~java
@DynamicPropertySource
static void elasticsearchProperties(DynamicPropertyRegistry registry) {
    registry.add(
        "spring.elasticsearch.uris",
        ELASTICSEARCH::getHttpHostAddress
    );
}
~~~

Tên property khác nhau giữa các thế hệ Spring Boot. Một số version cũ dùng property có prefix spring.elasticsearch.rest. Hãy kiểm tra configuration metadata và property reference của Boot đang dùng.

Nếu dự án tự cấu hình ClientConfiguration hoặc Elasticsearch client bean, hãy truyền host/port từ container vào bean test configuration thay vì giả định auto-configuration sẽ đọc property đó.

### 6.3. Dùng ServiceConnection khi Spring Boot hỗ trợ

Một số phiên bản Spring Boot có @ServiceConnection để tự tạo connection details từ Testcontainers container:

~~~java
@Container
@ServiceConnection
static final ElasticsearchContainer ELASTICSEARCH =
    new ElasticsearchContainer(
        DockerImageName.parse(
            "docker.elastic.co/elasticsearch/elasticsearch:8.17.0"
        )
    );
~~~

Chỉ dùng cách này khi Spring Boot version và loại container có service connection factory tương ứng. Nếu không được hỗ trợ, dùng @DynamicPropertySource hoặc test configuration tùy chỉnh.

Không kết hợp hai cách một cách tùy tiện nếu chúng cùng cung cấp connection details khác nhau. Chọn một nguồn cấu hình rõ ràng.

### 6.4. Tránh tạo client thứ hai trong test

Một lỗi phổ biến là Spring Data repository dùng client được auto-configure, trong khi test tự tạo một Elasticsearch client khác để kiểm tra. Khi đó test có thể ghi vào container này nhưng repository lại kết nối endpoint khác.

Dùng cùng Spring-managed client/template cho các thao tác test cần xác minh. Nếu có custom configuration, xác nhận repository và ElasticsearchOperations được inject đúng bean.

## 7. Ví dụ integration test với Spring Data Elasticsearch

### 7.1. Entity và repository

Ví dụ entity đơn giản:

~~~java
@Document(indexName = "products-it")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    // Constructors, getters and setters.
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
~~~

Index name trong test nên tách biệt với index của developer hoặc môi trường khác. Không trỏ test tới index production.

### 7.2. Cấu hình test class

~~~java
@Testcontainers
@SpringBootTest
class ProductRepositoryIntegrationTest {

    @Container
    static final ElasticsearchContainer ELASTICSEARCH =
        new ElasticsearchContainer(
            DockerImageName.parse(
                "docker.elastic.co/elasticsearch/elasticsearch:8.17.0"
            )
        )
        .withEnv("discovery.type", "single-node")
        .withEnv("xpack.security.enabled", "false")
        .withEnv("ES_JAVA_OPTS", "-Xms512m -Xmx512m");

    @DynamicPropertySource
    static void elasticsearchProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.elasticsearch.uris",
            ELASTICSEARCH::getHttpHostAddress
        );
    }

    @Autowired
    ProductRepository repository;

    @Test
    void savesAndReadsProduct() {
        ProductDocument product = new ProductDocument();
        product.setId("p-100");
        product.setSku("SKU-100");
        product.setName("Wireless Keyboard");

        repository.save(product);

        Optional<ProductDocument> loaded =
            repository.findById("p-100");

        assertThat(loaded).isPresent();
        assertThat(loaded.get().getSku()).isEqualTo("SKU-100");
        assertThat(loaded.get().getName())
            .isEqualTo("Wireless Keyboard");
    }
}
~~~

Đây là ví dụ cấu trúc. Các import, constructor, getter/setter và property cần khớp với version Spring Boot/Spring Data của dự án.

### 7.3. Chuẩn bị index và mapping

Có thể để Spring Data tự tạo index theo cấu hình entity, hoặc chủ động tạo trong test:

~~~java
@Autowired
ElasticsearchOperations operations;

@BeforeEach
void prepareIndex() {
    IndexOperations indexOperations =
        operations.indexOps(ProductDocument.class);

    if (!indexOperations.exists()) {
        indexOperations.createWithMapping();
    }
}
~~~

Nếu test cần xác minh mapping được tạo tự động, đừng tạo mapping trước bằng cùng API vì như vậy test không còn kiểm tra hành vi auto-create.

Chia test thành hai nhóm rõ ràng:

- Test mapping/provisioning: tạo index bằng cơ chế ứng dụng cần kiểm tra.
- Test repository CRUD: chuẩn bị index trước khi chạy thao tác.

### 7.4. Dọn dữ liệu giữa các test

Dùng index test riêng và xóa dữ liệu sau mỗi test:

~~~java
@AfterEach
void cleanDocuments() {
    repository.deleteAll();
}
~~~

Nếu test thay đổi mapping hoặc index settings, xóa và tạo lại index có thể cần thiết. Không dùng chung index cho test chạy song song nếu dữ liệu có thể ghi đè nhau.

### 7.5. Đợi refresh khi test search

Elasticsearch refresh không nhất thiết xảy ra ngay sau mỗi write. Nếu test save rồi search ngay, kết quả có thể chưa nhìn thấy document dù write đã thành công.

Có thể:

- Dùng refresh policy phù hợp cho test.
- Gọi refresh qua IndexOperations sau write.
- Dùng API test có refresh option nếu version hỗ trợ.

Ví dụ:

~~~java
operations.indexOps(ProductDocument.class).refresh();
~~~

Chỉ thêm refresh trong test cần xác nhận search visibility. Không mặc định refresh sau mọi write trong production vì refresh thường xuyên có chi phí.

## 8. Kiểm tra mapping và query thực tế

### 8.1. Test mapping sau khi tạo index

Có thể đọc mapping từ Elasticsearch để xác nhận field type:

~~~java
IndexOperations indexOperations =
    operations.indexOps(ProductDocument.class);

Map<String, Object> mapping =
    indexOperations.getMapping();

assertThat(mapping).isNotEmpty();
~~~

Tùy API version, kiểu dữ liệu mapping hoặc cách truy cập có thể khác. Quan trọng là test đọc mapping từ server thật, không chỉ assert annotation trên entity.

### 8.2. Test field type quan trọng

Với entity có keyword, text, date, nested hoặc dense vector, kiểm tra mapping thực tế. Các lỗi thường chỉ xuất hiện khi query hoặc indexing dữ liệu có kiểu phức tạp.

Ví dụ test nested:

- Xác nhận field array được mapping là nested.
- Index hai object con có giá trị khác nhau.
- Chạy nested query yêu cầu các điều kiện cùng khớp một object.
- Xác nhận không có false positive.

### 8.3. Test query DSL với server thật

Mock query builder chỉ xác nhận ứng dụng tạo object query theo kỳ vọng. Integration test cần gửi query tới Elasticsearch để xác nhận parser và execution.

Nên có test cho các query quan trọng:

- Bool query và filter.
- Nested query.
- Sort và pagination.
- Aggregation.
- Highlight.
- Date range và timezone.
- Runtime fields hoặc script nếu ứng dụng dùng.

### 8.4. Test behavior thay vì phụ thuộc response nội bộ quá nhiều

Assert các kết quả quan trọng như document nào được trả, field nào được mapping và sort order. Tránh khóa test vào những metadata nội bộ có thể thay đổi giữa patch version nếu đó không phải contract của ứng dụng.

## 9. Kiểm thử security khi production dùng xác thực

### 9.1. Container không bật security chỉ kiểm tra chức năng dữ liệu

Cấu hình xpack.security.enabled=false giúp test CRUD dễ thiết lập. Tuy nhiên, nó không kiểm tra:

- API key header.
- Basic authentication.
- TLS certificate validation.
- Role/index privilege.
- 401 và 403.
- Rotation hoặc revoke credential.

Nếu production bật security, nên có test profile riêng bật security để xác minh client configuration.

### 9.2. Không dùng security-disabled test để kết luận API key hoạt động

Một test CRUD thành công trong container không security chỉ chứng minh client kết nối và thao tác dữ liệu. Nó không chứng minh header API key được gửi đúng hoặc role có quyền phù hợp.

Tách các mục tiêu:

| Test profile | Security | Mục đích |
|---|---|---|
| Fast integration | Có thể tắt | Mapping, repository, query và CRUD |
| Security integration | Bật | TLS, credential, API key, role và 401/403 |
| Production smoke test | Theo cấu hình production | Xác minh cấu hình kết nối sau deploy |

### 9.3. Test quyền tối thiểu

Trong security-enabled test:

1. Tạo index và role bằng principal provisioning riêng.
2. Tạo API key chỉ có quyền cần thiết.
3. Khởi tạo client Spring Data bằng key đó.
4. Thử thao tác được phép.
5. Thử thao tác ngoài phạm vi và xác nhận bị từ chối.
6. Revoke key và xác nhận credential không còn dùng được.

Không đưa secret vào source hoặc log. Dùng secret sinh ra trong test và hủy khi test kết thúc.

### 9.4. TLS và certificate

Nếu production dùng HTTPS, cần một test xác minh trust chain và hostname validation. Cấu hình trust-all chỉ để test chạy sẽ che lỗi certificate configuration.

Có thể dùng test certificate riêng hoặc fixture TLS được kiểm soát. Không dùng private key production trong repository test.

## 10. Reactive integration test

### 10.1. Dùng reactive template/repository

Với reactive application, kết nối cùng Testcontainers endpoint vào ReactiveElasticsearchOperations hoặc reactive repository.

Ví dụ test dùng StepVerifier:

~~~java
@Test
void savesProductReactively() {
    ProductDocument product = new ProductDocument();
    product.setId("p-reactive-1");
    product.setSku("SKU-R1");
    product.setName("USB Hub");

    StepVerifier.create(repository.save(product))
        .assertNext(saved ->
            assertThat(saved.getId()).isEqualTo("p-reactive-1")
        )
        .verifyComplete();

    StepVerifier.create(repository.findById("p-reactive-1"))
        .assertNext(found ->
            assertThat(found.getName()).isEqualTo("USB Hub")
        )
        .verifyComplete();
}
~~~

Test cần dùng đúng reactive repository type và dependency reactive của dự án. Không gọi block() trong production reactive code chỉ để làm test dễ viết; StepVerifier giúp kiểm soát subscription và signal.

### 10.2. Cleanup reactive data

Cleanup có thể compose trong lifecycle test hoặc dùng test fixture:

~~~java
@AfterEach
void cleanDocuments() {
    repository.deleteAll().block();
}
~~~

block() trong test thread có thể chấp nhận được để chờ cleanup hoàn tất trước test tiếp theo, nhưng không copy cách này vào event-loop của ứng dụng production.

Nếu test framework hỗ trợ asynchronous lifecycle, có thể trả Publisher từ setup/cleanup theo extension phù hợp.

### 10.3. Kiểm tra cancellation và timeout với server thật

Mock Publisher hữu ích để kiểm tra operator. Nhưng nếu cần xác minh cancellation ở transport, hãy chạy request thực tới container và quan sát behavior.

Không giả định subscriber cancel có thể rollback write đã được Elasticsearch nhận. Với write test, xác minh trạng thái document sau cancellation hoặc timeout nếu semantics quan trọng.

## 11. Tổ chức test suite và hiệu năng

### 11.1. Chia test theo chi phí

Có thể tổ chức:

- Unit tests: chạy thường xuyên, không Docker.
- Fast integration tests: một Elasticsearch container dùng chung cho nhóm test.
- Security integration tests: container có security/TLS.
- Compatibility tests: chạy theo các server version được hỗ trợ.
- End-to-end tests: chạy trong môi trường tích hợp lớn hơn.

Không cần chạy matrix nhiều version cho mọi commit nếu chi phí cao. Có thể chạy một version chính ở mỗi pull request và chạy compatibility matrix trong scheduled pipeline hoặc release pipeline.

### 11.2. Dùng một container cho nhiều test khi có thể

Elasticsearch khởi động tốn thời gian và memory. Dùng một container cho test class/suite giúp giảm thời gian.

Để giữ isolation:

- Dùng index name riêng cho từng test group.
- Xóa dữ liệu giữa test.
- Không chia sẻ document ID.
- Kiểm soát test parallelism.
- Không thay đổi cluster settings toàn cục trong test chạy song song.

### 11.3. Chạy test song song cẩn thận

Nếu nhiều test class cùng dùng một cluster:

- Không để hai test cùng xóa index.
- Tránh index name cố định trùng nhau.
- Dùng prefix hoặc suffix duy nhất theo test class/run.
- Cẩn thận với alias và template toàn cluster.
- Đặt giới hạn số test đồng thời theo memory và CPU.

Một test chạy độc lập có thể thành công nhưng suite song song lại thất bại do race condition trên index.

### 11.4. Container reuse

Testcontainers có chế độ reuse container cho môi trường local trong một số version. Đây là tối ưu tùy chọn, không nên là điều kiện để CI chạy đúng.

Reusable container có thể giữ lại dữ liệu và settings giữa các lần chạy. Test phải tự đảm bảo cleanup và không phụ thuộc state cũ.

Không bật reuse chỉ để che một test suite khởi tạo quá nhiều container. Trước tiên hãy sửa lifecycle và chia sẻ container hợp lý.

## 12. Chạy Testcontainers trong CI

### 12.1. CI runner cần Docker runtime

Testcontainers cần truy cập Docker daemon hoặc môi trường container runtime được hỗ trợ. CI runner phải có quyền tạo container, network, volume và pull image.

Nếu test chạy trong container lồng nhau, cần cấu hình Docker socket hoặc DinD theo nền tảng CI. Không giả định mọi hosted runner đều có Docker access mặc định.

### 12.2. Cache image để giảm thời gian

Elasticsearch image có kích thước lớn. CI có thể cache Docker layers hoặc dùng runner image đã pull sẵn đúng version.

Cache phải dựa trên image tag/digest đã pin. Không cache một tag trôi nổi rồi cho rằng image vẫn giống nhau.

### 12.3. Giới hạn memory

Elasticsearch cần memory cho JVM và native process. Container test nên có heap phù hợp với runner:

~~~java
.withEnv("ES_JAVA_OPTS", "-Xms512m -Xmx512m")
~~~

Giá trị này là ví dụ cho test nhỏ. Nếu suite dùng analyzer/plugin hoặc dữ liệu lớn, có thể cần heap cao hơn. Cũng cần tính memory cho Docker daemon, JVM test process và các container khác.

### 12.4. Xử lý architecture

Nếu developer chạy ARM64 nhưng CI chạy AMD64, kiểm tra image có manifest phù hợp với cả hai kiến trúc.

Không ép platform khác một cách tùy tiện vì có thể chạy qua emulation và làm test chậm hoặc gây lỗi native library. Ghi rõ architecture nếu dự án cần test trên một nền tảng cố định.

### 12.5. Khi Docker không khả dụng

Nếu test bắt buộc, CI cần fail với thông báo Docker daemon không truy cập được. Nếu test optional ở môi trường developer, có thể skip có chủ đích.

Không biến mọi lỗi container startup thành assumption rằng Docker không có. Phân biệt Docker unavailable, image pull failure, container exit và Elasticsearch readiness timeout.

## 13. Ma trận kiểm tra tương thích

### 13.1. Một version server cố định cho mỗi build chính

Trong pull request, thường chọn một version server đã được xác nhận tương thích để test nhanh và ổn định.

Ghi version này ở một property dùng chung, ví dụ trong test configuration hoặc build property. Không lặp chuỗi version ở nhiều class vì rất dễ lệch.

### 13.2. Ma trận nhiều version

Nếu ứng dụng hỗ trợ nhiều server version, có thể chạy matrix:

| Job | Spring Data/client | Elasticsearch image | Mục tiêu |
|---|---|---|---|
| Main integration | Version theo BOM | Version server chính | Gate cho mỗi pull request |
| Minimum supported | Cùng dependency ứng dụng | Server thấp nhất còn hỗ trợ | Xác nhận compatibility tối thiểu |
| Latest supported | Cùng dependency ứng dụng | Server mới nhất được release train hỗ trợ | Phát hiện vấn đề trước khi nâng server |
| Upgrade rehearsal | Dependency candidate | Server target upgrade | Kiểm tra nâng cấp có chủ đích |

Không thử mọi version patch nếu không có nhu cầu. Chọn các mốc có ý nghĩa theo compatibility policy của dự án.

### 13.3. Nâng client và server có kiểm soát

Khi nâng Spring Boot/Spring Data:

1. Kiểm tra release notes và compatibility matrix.
2. Cập nhật dependency management.
3. Xem dependency tree để biết client version mới.
4. Chọn Elasticsearch image được hỗ trợ.
5. Chạy integration tests.
6. Kiểm tra deprecation và API behavior.
7. Chỉ sau đó mới thay version trong CI/release.

Không nâng server image độc lập rồi dùng test failure làm cách duy nhất để tìm compatibility.

### 13.4. Không để test version khác production mà không có lý do

Nếu production chạy Elasticsearch 8.x nhưng integration test chạy một major khác, test có thể bỏ sót khác biệt mapping, security và API behavior.

Test version nên phản ánh server production mục tiêu hoặc một version trong compatibility range đã được xác định.

## 14. Thu thập log và chẩn đoán startup failure

### 14.1. Xem container logs

Khi container không sẵn sàng, xem logs để tìm:

- JVM bootstrap failure.
- Memory lock hoặc heap issue.
- Bootstrap checks.
- Permission hoặc file-system issue.
- Plugin load failure.
- Security auto-configuration.
- Cluster formation failure.

Không chỉ tăng startup timeout nếu Elasticsearch đã exit vì cấu hình sai.

### 14.2. Kiểm tra container exit code

Nếu container dừng ngay sau khi start, kiểm tra exit code và logs. Một số nguyên nhân phổ biến là Docker memory quá thấp, bootstrap check thất bại hoặc env setting sai.

### 14.3. Xác minh endpoint và port

In ra host/mapped port trong test log nếu cần, nhưng không log credential. Kiểm tra:

- Host trả về từ Testcontainers.
- Port mapping của HTTP endpoint.
- HTTP scheme đúng với security/TLS mode.
- Client dùng đúng endpoint.
- Không có config khác override DynamicPropertySource.

### 14.4. Kiểm tra server version thực tế

Có thể gọi root endpoint và đọc version:

~~~http
GET /
~~~

Response Elasticsearch có thông tin version. Test có thể assert server version phù hợp với version pin trong build.

Điều này hữu ích khi image tag hoặc biến cấu hình có thể bị override trong CI.

## 15. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Container chạy nhưng client không kết nối | Dùng port 9200 cố định thay vì mapped port | Lấy endpoint từ container |
| Test chạy lúc được lúc không | Bắt đầu test trước khi Elasticsearch ready | Dùng wait strategy và startup timeout hợp lý |
| Lỗi method/API không tương thích | Spring Data, Java client và server lệch version | Kiểm tra compatibility matrix và dependency tree |
| Mapping bị từ chối | Server version hoặc mapping type không hỗ trợ | Kiểm tra mapping DSL và server version |
| Test local pass, CI fail | Docker daemon, memory, architecture hoặc image pull | Kiểm tra CI runtime, logs và resource limit |
| Test class sau không kết nối được | Container đã dừng nhưng Spring context cache vẫn giữ endpoint | Dùng singleton container hoặc quản lý context lifecycle |
| Test chạy song song thất bại | Nhiều test dùng chung index hoặc xóa dữ liệu lẫn nhau | Tách index và kiểm soát parallelism |
| Search ngay sau save không thấy document | Chưa refresh | Refresh trong test hoặc dùng refresh policy phù hợp |
| 401 khi production dùng API key | Test container tắt security hoặc header sai | Có security integration test riêng |
| 403 dù authentication thành công | Role thiếu index privilege | Kiểm tra role và thao tác API thực tế |
| Image tag thay đổi ngoài ý muốn | Dùng latest hoặc tag không pin patch | Pin exact version hoặc digest |
| Container exit ngay | Heap thấp, bootstrap check hoặc env sai | Đọc logs và chỉnh resource/config |
| Test suite quá chậm | Mỗi method tạo một container | Chia sẻ container theo class/suite |
| Dữ liệu test còn sót | Không cleanup hoặc reuse container | Xóa index/document và cô lập test state |
| Test bỏ qua trên CI | Dùng disabledWithoutDocker trong job bắt buộc | Cấu hình Docker runner và để job fail rõ ràng |

## 16. Quy trình thiết lập từ đầu

Khi thêm Testcontainers vào dự án Spring Data Elasticsearch:

1. Đọc Spring Boot và Spring Data Elasticsearch version trong build.
2. Kiểm tra Elasticsearch Java API Client version thực tế.
3. Tra compatibility matrix của đúng release train.
4. Chọn Elasticsearch image có tag patch cụ thể.
5. Thêm Elasticsearch và JUnit Testcontainers modules ở test scope.
6. Tạo ElasticsearchContainer với single-node settings cho test cơ bản.
7. Đặt readiness wait và startup timeout phù hợp.
8. Đưa host/mapped port vào Spring bằng DynamicPropertySource hoặc ServiceConnection được hỗ trợ.
9. Dùng cùng Spring-managed client/template/repository trong test.
10. Tạo test index và mapping theo mục tiêu cần xác minh.
11. Viết test CRUD, mapping và query với server thật.
12. Cô lập index và cleanup giữa các test.
13. Thêm security-enabled test nếu production dùng authentication/TLS.
14. Chạy test trong CI với Docker access và memory phù hợp.
15. Dùng matrix test cho các server version nằm trong compatibility range.
16. Khi nâng dependency hoặc server, cập nhật version pin và chạy lại integration suite.

## 17. Những điểm cần ghi nhớ

- Testcontainers chạy Elasticsearch server thật trong Docker để kiểm tra tích hợp Spring Data.
- Testcontainers version, Elasticsearch Java API Client version và Elasticsearch server image version là các version khác nhau.
- Chọn server image theo compatibility matrix của đúng Spring Data Elasticsearch release train.
- Pin tag patch cụ thể hoặc digest; tránh latest và tag trôi nổi.
- Dùng image Elasticsearch chính thức và kiểm tra DockerImageName compatibility.
- Cấu hình single-node, heap và security theo mục tiêu test.
- Chờ Elasticsearch readiness; container running chưa chắc HTTP endpoint đã sẵn sàng.
- Lấy host và mapped port từ container, không hardcode localhost:9200.
- Dùng DynamicPropertySource hoặc ServiceConnection nếu Spring Boot version hỗ trợ.
- Chú ý Spring TestContext cache khi container bị dừng trước khi context được tái sử dụng.
- Kiểm tra mapping và query bằng server thật, không chỉ assert entity annotation.
- Search sau write có thể cần refresh trong test.
- Security-disabled container không kiểm tra API key, TLS hoặc role privilege.
- Dùng container chia sẻ hợp lý, index riêng và cleanup để suite nhanh mà vẫn cô lập.
- CI phải có Docker runtime, memory và image architecture phù hợp.
- Khi nâng version, kiểm tra dependency tree, compatibility matrix và chạy integration tests trước khi đổi production target.

Testcontainers làm cho integration test của Spring Data Elasticsearch gần với môi trường thực hơn và có thể chạy lặp lại trên developer machine lẫn CI. Khi pin đúng server image theo dependency của dự án, cấu hình endpoint động và quản lý vòng đời container rõ ràng, test sẽ phát hiện sớm lỗi mapping, query, client compatibility và security trước khi ứng dụng được triển khai.

