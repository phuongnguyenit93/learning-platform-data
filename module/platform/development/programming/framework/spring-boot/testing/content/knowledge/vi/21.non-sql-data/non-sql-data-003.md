# @DataElasticsearchTest và khác biệt của khả năng hỗ trợ theo phiên bản

## 1. Đặt đúng vấn đề

Trong **Spring Boot - testing**, nhóm **Dữ liệu ngoài SQL**, `@DataElasticsearchTest` là annotation test slice cho **Spring Data Elasticsearch**. Nó giúp khởi tạo những thành phần liên quan Elasticsearch như entity `@Document`, repository, converter và client phù hợp, thay vì nạp toàn bộ ứng dụng.

Tên annotation trông giống nhau qua nhiều đời Spring Boot nhưng **khả năng hỗ trợ phụ thuộc phiên bản** ở ít nhất ba tầng:

1. **Annotation/import và module test:** Spring Boot 2.7/3.x dùng namespace `org.springframework.boot.test.autoconfigure.data.elasticsearch`, còn Spring Boot 4.x chuyển sang `org.springframework.boot.data.elasticsearch.test.autoconfigure`.
2. **Spring Data Elasticsearch/client:** client cũ, Java API client, các template và module auto-configuration thay đổi qua các đời Boot; không thể tùy tiện chép import `ElasticsearchRestTemplate` của tài liệu cũ.
3. **Cluster thật:** `@DataElasticsearchTest` không tạo Elasticsearch embedded kiểu H2. Muốn chứng minh query/index/mapping chạy đúng, phải có Elasticsearch server được cấu hình, thường qua Testcontainers.

Ví dụ chính trong bài chọn **Java 17, Spring Boot 3.5.16, JUnit Jupiter, Elasticsearch 8.17.2 trong Testcontainers**. Đây là một bộ phiên bản minh họa nhất quán. Các phần dành cho **Boot 2.7 và Boot 4.x** được tách riêng, tránh nhập nhằng package/dependency.

Một test tốt không chỉ hỏi repository có được inject không mà còn kiểm tra **save/get by id, derived query, mapping `Keyword`, refresh để tìm kiếm thấy dữ liệu, update và delete**. Trước khi viết, phải xác định test có Docker/cluster hay đang cố kiểm tra logic Java mà không cần Elasticsearch thật.

## 2. Elasticsearch không phải một database JPA có thể thay bằng H2

| Tiêu chí | Spring Data JPA | Spring Data Elasticsearch |
| --- | --- | --- |
| Đơn vị lưu trữ | Table/row | Index/document |
| Entity | `@Entity` | `@Document` |
| Repository | `JpaRepository` | `ElasticsearchRepository` |
| API truy vấn | SQL/JPQL/JPA Criteria | Elasticsearch search/query DSL |
| Mapping | Column/relationship | Field type, analyzer, normalizer |
| Dữ liệu search nhìn thấy ngay? | Theo isolation/transaction | Search near-real-time; có thể cần refresh |
| Hạ tầng test | H2 hoặc RDBMS thật | Elasticsearch cluster thật hoặc test double tùy mục tiêu |
| Rollback test | `@DataJpaTest` thường transactional và rollback | `@DataElasticsearchTest` **không** tự rollback index như JPA |
| Client | JDBC/JPA provider | Elasticsearch REST/Java client phù hợp version |

**Bẫy:** test lưu document qua `repository.save(...)` rồi gọi `repository.findById(...)` có thể PASS nhưng `findByCategory(...)` ngay sau khi ghi chưa thấy vì Elasticsearch search index chưa refresh. Cần phân biệt **GET theo id** với **search query**.

Test nào chỉ mock `ElasticsearchRepository` thì **không chứng minh Elasticsearch query/mapping chạy thật**. Nó có thể hữu ích cho unit test service tiêu thụ repository, nhưng phải đặt tên và báo cáo đúng phạm vi.

## 3. Ma trận import và module theo phiên bản

| Dòng Spring Boot | Import `DataElasticsearchTest` | Phần test liên quan | Khác biệt đáng chú ý |
| --- | --- | --- | --- |
| **2.7.x** | `org.springframework.boot.test.autoconfigure.data.elasticsearch.DataElasticsearchTest` | `spring-boot-test-autoconfigure`, thường qua `spring-boot-starter-test` | Tài liệu cũ nhắc `ElasticsearchRestTemplate` |
| **3.0–3.5.x** | `org.springframework.boot.test.autoconfigure.data.elasticsearch.DataElasticsearchTest` | `spring-boot-test-autoconfigure`/`spring-boot-starter-test` | Java 17+, Spring Data Elasticsearch 5.x và Elasticsearch Java API client |
| **4.0–4.1.x** | `org.springframework.boot.data.elasticsearch.test.autoconfigure.DataElasticsearchTest` | Module `spring-boot-data-elasticsearch-test` và starter `spring-boot-starter-data-elasticsearch-test` | Test module chuyên biệt, namespace mới và client stack thay đổi |

Đây là **ma trận theo các nhánh đã có tài liệu/Javadoc chính thức**. Annotation không bị xóa hoàn toàn ở Boot 4.x; ngược lại, tài liệu **Spring Boot 4.1** vẫn liệt kê `@DataElasticsearchTest`. Thay đổi quan trọng là **package và vị trí dependency**.

### Import ở Boot 2.7/3.x

~~~java
import org.springframework.boot.test.autoconfigure.data.elasticsearch.DataElasticsearchTest;
~~~

### Import ở Boot 4.x

~~~java
import org.springframework.boot.data.elasticsearch.test.autoconfigure.DataElasticsearchTest;
~~~

**Không** đặt hai import trong một class. Nếu dự án Boot 3 mà IDE báo không tìm thấy package Boot 4, đó có thể là do dùng tài liệu sai phiên bản, không phải do Spring Boot 3 thiếu Elasticsearch testing. Nếu dự án Boot 4 mà dùng package 3.x, cần chuyển sang module/test starter mới thay vì kéo một jar Boot 3 vào Boot 4.

### Đừng trộn Spring Boot major versions

Plugin Gradle, BOM, `spring-boot-starter-data-elasticsearch`, `spring-boot-starter-test` và module test chuyên biệt phải phù hợp cùng một nhánh. Gắn riêng một bản `spring-boot-test-autoconfigure:3.x` vào ứng dụng Boot 4.x để tìm lại annotation có thể gây lỗi runtime Spring/auto-configuration.

## 4. DataElasticsearchTest nạp những gì, không nạp những gì?

Trong Spring Boot 3.5, test slice chỉ bật nhóm auto-configuration liên quan **Elasticsearch data, sync/reactive repositories và clients** khi các dependency/conditions đáp ứng. Nó tập trung những thành phần như:

- Metadata/domain types `@Document`.
- Spring Data Elasticsearch repository interfaces.
- Mapping converter và `ElasticsearchOperations`/template phù hợp.
- Elasticsearch client được cấu hình từ application properties hoặc connection details.
- Spring TestContext, JUnit Jupiter, một số JSON/cache infrastructure.

Nó thường **không tự scan** toàn bộ `@Service`, `@RestController`, `@Component` thông thường hoặc `@ConfigurationProperties`.

~~~text
@DataElasticsearchTest
     |
     +-- Repository bean + @Document metadata
     +-- ElasticsearchOperations / converter / client
     +-- Auto-config liên quan đến data slice
     |
     X-- Không mặc định nạp @RestController
     X-- Không mặc định nạp service nghiệp vụ
     X-- Không mặc định bind mọi @ConfigurationProperties bean
     X-- Không khởi động embedded Elasticsearch server
~~~

Nhờ vậy một test repository có thể nhẹ hơn `@SpringBootTest`. Tuy nhiên, **slice nhỏ không đồng nghĩa tốc độ test nhanh như unit test**: Elasticsearch container vẫn có chi phí tải image/khởi động và index setup.

Nếu mục tiêu là kiểm tra controller HTTP → service → Elasticsearch thật, hãy dùng integration test phạm vi lớn hơn. Nếu mục tiêu là mapper POJO thuần Java, không cần nạp Spring context.

### @Document khác @Entity

`@Document` thuộc `org.springframework.data.elasticsearch.annotations.Document`. `@Id` trong ví dụ Elasticsearch thuộc `org.springframework.data.annotation.Id`. Không dùng `jakarta.persistence.Entity`/`JpaRepository` rồi chờ Elasticsearch auto-config tạo repository tương ứng.

### Có hỗ trợ reactive không?

Danh sách slice auto-config của Spring Boot 3.5 có cả những thành phần **reactive Elasticsearch repositories/client**. Nhưng việc bean reactive được tạo còn phụ thuộc classpath, phiên bản Spring Data và điều kiện cấu hình. **Không kết luận rằng mọi `@DataElasticsearchTest` đều có sẵn `ReactiveElasticsearchOperations`**, cũng không thay method đồng bộ bằng `Flux` chỉ vì dự án có WebFlux.

## 5. Chọn đúng cấp độ kiểm thử

| Mục tiêu | Phạm vi đề nghị | Lý do |
| --- | --- | --- |
| Kiểm tra mapping document → JSON Elasticsearch | `@DataElasticsearchTest` với Elasticsearch thật | Kiểm tra converter và mapping |
| Derived repository query `findByCategory` | Data slice + cluster thật + refresh | Kiểm tra query và search semantics |
| Cấu hình index template/analyzer | Data slice hoặc integration với cluster đúng version | Cần Elasticsearch xử lý thật |
| Logic service chọn từ khóa, phân trang | Unit test service với repository mock | Không phải bài kiểm tra query engine |
| HTTP status/body khi search | `@WebMvcTest`/`@WebFluxTest` | Test web boundary, mock service ngoài slice |
| Luồng HTTP tới Elasticsearch thật | `@SpringBootTest` + Testcontainers | Test nhiều tầng |
| TLS, auth, cluster nhiều node, index lifecycle | Integration trên môi trường phù hợp | Vượt phạm vi repository đơn giản |

Nguyên tắc là **không mock đối tượng cần kiểm tra**. Nếu muốn kiểm tra `CatalogItemRepository` thật, không gắn `@MockitoBean` lên chính repository; làm vậy test sẽ chỉ xác nhận Mockito.

## 6. Cấu hình dự án Java 17 / Spring Boot 3.5

Cấu trúc:

~~~text
build.gradle
src/main/java/com/example/esdemo/
    ElasticsearchDemoApplication.java
    CatalogItem.java
    CatalogItemRepository.java
    CatalogSearchService.java
src/test/java/com/example/esdemo/
    ElasticsearchContainerTestConfig.java
    CatalogElasticsearchSliceTest.java
~~~

**Tệp `build.gradle` (Gradle Groovy DSL):**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-elasticsearch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:elasticsearch'
    testImplementation 'org.testcontainers:junit-jupiter'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

- `spring-boot-starter-data-elasticsearch`: Spring Data Elasticsearch và client tương thích với Boot 3.5 BOM.
- `spring-boot-starter-test`: JUnit Jupiter, AssertJ, Spring Boot test infrastructure.
- `spring-boot-testcontainers`: annotation `@ServiceConnection` và integration giữa Boot với Testcontainers.
- `org.testcontainers:elasticsearch`: `ElasticsearchContainer`. Module `junit-jupiter` hỗ trợ phương án container field quản lý bằng JUnit, không bắt buộc cho cách container bean ở ví dụ chính.
- Không chỉ định riêng version Spring Data/Elasticsearch Java client/Testcontainers trong dependencies vì **BOM** đang quản lý chúng.

Cần Gradle Wrapper, Docker daemon và quyền tải container image. **Dùng Elasticsearch image 8.17.2 cho demo**, tương ứng ví dụ chính thức trong tài liệu Testcontainers của Spring Boot 3.5. Không thay image thành `latest` mà không chạy lại kiểm thử compatibility.

**`src/main/java/com/example/esdemo/ElasticsearchDemoApplication.java`:**

~~~java
package com.example.esdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ElasticsearchDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ElasticsearchDemoApplication.class, args);
    }
}
~~~

Lớp ứng dụng nằm ở package cha của domain/repository/test. `@DataElasticsearchTest` tìm được cấu hình gốc nhưng vẫn giới hạn bean scan; không gọi `main` khi chạy test.

## 7. Document có mapping rõ ràng

**`src/main/java/com/example/esdemo/CatalogItem.java`:**

~~~java
package com.example.esdemo;

import java.util.Objects;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "catalog_items_test", createIndex = false)
public class CatalogItem {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Text)
    private String title;

    @Field(type = FieldType.Integer)
    private Integer quantity;

    protected CatalogItem() {
    }

    public CatalogItem(
            String id,
            String sku,
            String category,
            String title,
            Integer quantity
    ) {
        this.id = Objects.requireNonNull(id, "id");
        this.sku = Objects.requireNonNull(sku, "sku");
        this.category = Objects.requireNonNull(category, "category");
        this.title = Objects.requireNonNull(title, "title");
        this.quantity = Objects.requireNonNull(quantity, "quantity");
    }

    public String getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getCategory() {
        return category;
    }

    public String getTitle() {
        return title;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = Objects.requireNonNull(quantity, "quantity");
    }
}
~~~

### Vì sao chọn Keyword và Text?

`FieldType.Keyword` lưu giá trị phù hợp cho tìm kiếm chính xác và aggregation như `category="office"` hoặc SKU. `FieldType.Text` dùng cho nội dung như `title`, thường đi qua analyzer; derived query trên `Text` có thể có token matching khác với một keyword exact match.

Vì thế **đừng viết cùng một expected result cho `keyword` và `text`** khi chưa xác định mapping/analyzer.

### Vì sao createIndex = false?

Một số phiên bản Spring Data Elasticsearch có cơ chế **tự tạo index khi khởi tạo repository** nếu `@Document(createIndex=true)` (mặc định). Ví dụ chủ động đặt `createIndex=false` để setup test quyết định thời điểm xóa/tạo index/mapping bằng `IndexOperations`.

Trong production, index settings/mappings/aliases có thể do migration hoặc provisioner riêng đảm nhiệm; không để test xóa index production. `createIndex=false` không làm Spring Data bỏ qua metadata của document.

## 8. Repository thật và một service cố ý nằm ngoài slice

**`src/main/java/com/example/esdemo/CatalogItemRepository.java`:**

~~~java
package com.example.esdemo;

import java.util.List;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface CatalogItemRepository
        extends ElasticsearchRepository<CatalogItem, String> {

    List<CatalogItem> findByCategory(String category);
}
~~~

`ElasticsearchRepository` được Spring Data tạo implementation. Method `findByCategory` là **derived query** trên field có mapping `Keyword`. Bài test sẽ lưu dữ liệu thật vào Elasticsearch và gọi method này, không mock kết quả.

**`src/main/java/com/example/esdemo/CatalogSearchService.java`:**

~~~java
package com.example.esdemo;

import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class CatalogSearchService {
    private final CatalogItemRepository repository;

    public CatalogSearchService(CatalogItemRepository repository) {
        this.repository = repository;
    }

    public List<CatalogItem> inCategory(String category) {
        return repository.findByCategory(category);
    }
}
~~~

Service dùng để chứng minh **ràng buộc của data slice**: repository thật có thể được inject, nhưng service `@Service` thông thường không tự được quét trong `@DataElasticsearchTest`. Nếu muốn test logic của service, dùng unit test hoặc `@Import(CatalogSearchService.class)` có chủ đích.

## 9. Elasticsearch Testcontainers được quản lý theo Spring context

**`src/test/java/com/example/esdemo/ElasticsearchContainerTestConfig.java`:**

~~~java
package com.example.esdemo;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.boot.testcontainers.service.connection.Ssl;
import org.springframework.context.annotation.Bean;

import org.testcontainers.elasticsearch.ElasticsearchContainer;

@TestConfiguration(proxyBeanMethods = false)
public class ElasticsearchContainerTestConfig {

    @Bean
    @ServiceConnection
    @Ssl
    ElasticsearchContainer elasticsearchContainer() {
        return new ElasticsearchContainer(
                "docker.elastic.co/elasticsearch/elasticsearch:8.17.2"
        );
    }
}
~~~

Tại sao lại dùng một container như **Spring bean**?

1. Spring Boot quản lý lifecycle của container bean: khởi động trước các bean client phụ thuộc, dừng khi context đóng.
2. `@ServiceConnection` tạo connection details từ `ElasticsearchContainer`. Boot auto-config sử dụng URL/TLS/credentials phù hợp, không hard-code `http://localhost:9200`.
3. `@Ssl` hỗ trợ cơ chế phát hiện SSL phía container và cấu hình client theo Boot 3.5. Nó không biến một server không dùng TLS thành server HTTPS.
4. Khi Spring TestContext cache context giữa nhiều test class, vòng đời container gắn với context giúp tránh lỗi bean client còn sống nhưng JUnit-managed container đã dừng.
5. `@Import(ElasticsearchContainerTestConfig.class)` trong test giới hạn rõ config chỉ phục vụ bài kiểm thử.

Đây là môi trường **test**; không nhúng credentials production, không chạy truy vấn phá hủy trên cluster của người dùng.

### Phương án khác: static @Container

Trong Boot 3.5 cũng có thể khai báo:

~~~java
@Testcontainers
@DataElasticsearchTest
class AlternativeContainerStyle {

    @Container
    @ServiceConnection
    @Ssl
    static ElasticsearchContainer elasticsearch =
            new ElasticsearchContainer(
                    "docker.elastic.co/elasticsearch/elasticsearch:8.17.2"
            );

    // @Autowired repository, rồi viết @Test phù hợp.
}
~~~

Đây là **skeleton minh họa**, cần imports và test methods. `@Testcontainers`/`@Container` làm JUnit điều khiển lifecycle. Nếu Spring context được cache sau khi container đã dừng, các bean client còn trỏ tới container đó có thể gây lỗi ở class khác; nên ưu tiên container bean khi cần lifecycle gắn với context. Không khai báo cả hai cách đồng thời nếu không cố ý chạy hai server.

## 10. Bộ test @DataElasticsearchTest hoàn chỉnh

**`src/test/java/com/example/esdemo/CatalogElasticsearchSliceTest.java`:**

~~~java
package com.example.esdemo;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.elasticsearch.DataElasticsearchTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;

import static org.assertj.core.api.Assertions.assertThat;

@DataElasticsearchTest
@Import(ElasticsearchContainerTestConfig.class)
class CatalogElasticsearchSliceTest {

    @Autowired
    CatalogItemRepository repository;

    @Autowired
    ElasticsearchOperations operations;

    @Autowired
    ApplicationContext context;

    @BeforeEach
    void resetIndex() {
        IndexOperations index = operations.indexOps(CatalogItem.class);

        if (index.exists()) {
            assertThat(index.delete()).isTrue();
        }

        assertThat(index.createWithMapping()).isTrue();
        assertThat(index.exists()).isTrue();
    }

    @Test
    void onlyElasticsearchSliceBeansAreLoaded() {
        assertThat(repository).isNotNull();
        assertThat(operations).isNotNull();
        assertThat(context.getBeanNamesForType(
                CatalogSearchService.class
        )).isEmpty();
    }

    @Test
    void saveThenFindById_preservesMappedFields() {
        repository.save(new CatalogItem(
                "P-1", "SKU-7", "office", "Notebook", 4
        ));

        CatalogItem stored = repository.findById("P-1")
                .orElseThrow();

        assertThat(stored.getId()).isEqualTo("P-1");
        assertThat(stored.getSku()).isEqualTo("SKU-7");
        assertThat(stored.getCategory()).isEqualTo("office");
        assertThat(stored.getTitle()).isEqualTo("Notebook");
        assertThat(stored.getQuantity()).isEqualTo(4);
    }

    @Test
    void derivedQuery_usesKeywordCategoryAfterRefresh() {
        repository.save(new CatalogItem(
                "P-1", "SKU-7", "office", "Notebook", 4
        ));
        repository.save(new CatalogItem(
                "P-2", "SKU-8", "books", "Novel", 9
        ));

        operations.indexOps(CatalogItem.class).refresh();

        List<CatalogItem> found =
                repository.findByCategory("office");

        assertThat(found)
                .extracting(CatalogItem::getId)
                .containsExactly("P-1");

        assertThat(repository.findByCategory("missing"))
                .isEmpty();
    }

    @Test
    void updateThenGetById_returnsNewQuantity() {
        repository.save(new CatalogItem(
                "P-1", "SKU-7", "office", "Notebook", 4
        ));

        CatalogItem item = repository.findById("P-1")
                .orElseThrow();
        item.setQuantity(8);
        repository.save(item);

        assertThat(repository.findById("P-1").orElseThrow()
                .getQuantity()).isEqualTo(8);
    }

    @Test
    void deleteById_removesStoredDocument() {
        repository.save(new CatalogItem(
                "P-1", "SKU-7", "office", "Notebook", 4
        ));

        repository.deleteById("P-1");

        assertThat(repository.findById("P-1")).isEmpty();
    }
}
~~~

### Những ca này chứng minh gì?

| Ca | Kết quả cần có | Tính năng được test |
| --- | --- | --- |
| Bean scope | Có repository, operations; không có business service | Spring slice filtering |
| Save / findById | Document lưu và đọc đúng field | Mapping, converter, GET by id |
| Derived query | Chỉ document category `office` được trả | Query, Keyword mapping, refresh |
| Update | Quantity mới được ghi và đọc lại | Ghi document thật |
| Delete | Document không còn theo id | Repository delete |

Mỗi test reset index trước khi chạy. Ví dụ **không chạy tests song song** trên cùng index; nếu bật parallel JUnit/CI workers, cần cô lập index name hoặc container. `index.delete()` là thao tác phá hủy dữ liệu thật: chỉ dùng trong **cluster dành riêng cho test**, không dùng với Elasticsearch dùng chung.

### Không lấy contextLoads làm kết luận cuối

Một test chỉ `assertThat(repository).isNotNull()` mới chứng minh wiring tương đối hẹp, **chưa chứng minh query/mapping**. Các test lưu và tìm kiếm mới buộc Elasticsearch thực thi thao tác cần kiểm tra.

### Vì sao không mock repository?

Vì mục tiêu bài là **Spring Data Elasticsearch**, thay repository bằng mock chỉ kiểm tra dữ liệu đã stub. Bạn có thể mock repository khi test `CatalogSearchService` thuần Java, nhưng khi test `findByCategory` phải để implementation Spring Data hoạt động trên server thật.

## 11. Refresh và tính nhất quán tìm kiếm

Elasticsearch có tính chất **near-real-time search**: sau khi ghi một document, truy vấn search ngay có thể tạm chưa nhìn thấy nó, trong khi GET theo id đã đọc được.

Ví dụ chưa đủ ổn định:

~~~java
repository.save(new CatalogItem(
        "P-1", "SKU-7", "office", "Notebook", 4
));

assertThat(repository.findByCategory("office"))
        .hasSize(1);
~~~

Nếu cần bảo đảm search nhìn thấy dữ liệu trong test, dùng:

~~~java
repository.save(new CatalogItem(
        "P-1", "SKU-7", "office", "Notebook", 4
));

operations.indexOps(CatalogItem.class).refresh();

assertThat(repository.findByCategory("office"))
        .extracting(CatalogItem::getId)
        .containsExactly("P-1");
~~~

`IndexOperations.refresh()` của Spring Data Elasticsearch là thao tác index-level. Nó giúp test deterministic; **không phải lời khuyên refresh sau mọi write production**. Refresh quá thường xuyên có thể làm tăng tải index/search.

Một số đường repository và `ElasticsearchOperations` có chính sách refresh khác nhau theo version và cấu hình. Không suy rằng mọi method có cùng behavior; test phải xác định rõ **khi nào dữ liệu được kỳ vọng có thể search**.

Nếu yêu cầu ở production là read-your-write ngay sau cập nhật, cần thiết kế refresh policy (ví dụ chờ refresh phù hợp) và chấp nhận trade-off hiệu năng.

## 12. Version khác nhau còn ở client và template

Một số tài liệu Spring Boot 2.7 sử dụng `ElasticsearchRestTemplate`. Tài liệu Boot 3.5 và Spring Data Elasticsearch 5.x tập trung `ElasticsearchTemplate`/Java API client thế hệ hiện đại. Boot 4.x tiếp tục thay đổi cách tổ chức client và có tài liệu về REST5.

| Thành phần | Boot 2.7 thường gặp | Boot 3.x | Boot 4.x |
| --- | --- | --- | --- |
| Test annotation | Namespace `boot.test.autoconfigure` | Namespace giống Boot 2.7 | Namespace `boot.data.elasticsearch.test.autoconfigure` |
| Spring Data major | Dòng cũ hơn 3.x | Spring Data Elasticsearch 5.x | Spring Data Elasticsearch đời mới theo BOM 4.x |
| Template | `ElasticsearchRestTemplate` trong docs cũ | `ElasticsearchTemplate` hoặc interface `ElasticsearchOperations` | Template/interface tương ứng release mới |
| Client | REST client đời cũ | Elasticsearch Java API client | Có client REST5 và client stack mới |
| Test packaging | `spring-boot-test-autoconfigure` | `spring-boot-test-autoconfigure` | `spring-boot-data-elasticsearch-test` |
| Testcontainers shortcut | Thường `@DynamicPropertySource` hoặc properties | `@ServiceConnection` trong Boot 3.1+ | Theo API/module của Boot 4.x |

**Mẹo an toàn:** inject **`ElasticsearchOperations`** khi test không cần implementation. Nhưng interface cũng thay đổi theo từng phiên bản Spring Data, vì vậy không hứa rằng một source file import ở Boot 2.7 sẽ biên dịch trên Boot 4 mà không sửa.

**Điểm cốt lõi:** chọn đúng Spring Boot BOM rồi để nó chọn Spring Data Elasticsearch/client tương thích. Không pin riêng client Elasticsearch 9.x vào dự án Boot 2.7 chỉ để kết nối một server mới.

## 13. Spring Boot 4.x: import và dependencies phải đổi

**Import Boot 4.x:**

~~~java
import org.springframework.boot.data.elasticsearch.test.autoconfigure.DataElasticsearchTest;
~~~

**Phần dependency dành riêng cho Boot 4.x (minh họa, KHÔNG dùng trong `build.gradle` Boot 3.5 ở trên):**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-elasticsearch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-data-elasticsearch-test'
}
~~~

Spring Boot 4 có module `spring-boot-data-elasticsearch-test` và feature test starter `spring-boot-starter-data-elasticsearch-test`. Đừng thêm hai test starters thuộc hai major Boot khác nhau vào cùng project.

Một số package của Elasticsearch auto-configuration cũng đã thay đổi. Nếu test của bạn đang có `@ImportAutoConfiguration(Elasticsearch...AutoConfiguration.class)` hoặc `excludeAutoConfiguration` trỏ tới class Boot 3, migration cần sửa cả **những import đó**.

### Khi dự án Boot 4 báo không tìm thấy annotation

Theo thứ tự:

1. Xem Gradle plugin/BOM/parent thực sự là Boot **4.x** chưa.
2. Kiểm tra test-scope starter chuyên biệt đã được khai báo chưa.
3. Chuyển import sang namespace `org.springframework.boot.data.elasticsearch.test.autoconfigure`.
4. Kiểm tra dependency tree để loại jar Boot 3 bị giữ lại.
5. Biên dịch test code, rồi mới điều tra lỗi kết nối Elasticsearch.

Đừng quy lỗi `cannot find symbol` cho Docker: lỗi compile liên quan package/classpath, còn Docker thường chỉ gây lỗi **runtime** khi container/cluster cần start.

## 14. Boot 2.7/3.0: điều gì không thể copy nguyên?

Trên Boot 2.7, annotation `@DataElasticsearchTest` đã xuất hiện trong tài liệu và cùng namespace được dùng trong Boot 3.x. Nhưng đoạn code sử dụng `@ServiceConnection` của Boot 3.5 **không thể copy nguyên** sang Boot 2.7: service connection integration là chức năng được giới thiệu ở Boot 3.1.

Một cấu hình Testcontainers cũ hơn có thể dùng `@DynamicPropertySource`:

~~~java
@DynamicPropertySource
static void elasticsearchProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.elasticsearch.uris",
            () -> elasticsearch.getHttpHostAddress()
    );
}
~~~

Đây là **skeleton minh họa**, giả định có static Elasticsearch container tên `elasticsearch` đã được khởi động và Boot version hỗ trợ property này. Phải kiểm tra cụ thể URI scheme, TLS, credentials và thuộc tính theo nhánh Boot bạn sử dụng; đừng kết hợp `@ServiceConnection` và property hard-code một cách mâu thuẫn.

Với Boot 3.0 (chưa có Boot 3.1 service connections) cũng nên chọn cách cấu hình connection tương ứng, trong khi **import `@DataElasticsearchTest` vẫn theo namespace Boot 3.x**.

### Vì sao tên template có thể gây lỗi sau migration?

Nếu code cũ inject `ElasticsearchRestTemplate`, bản Spring Data mới có thể không còn đúng class/constructor như trước. Cân nhắc chuyển theo documentation của nhánh hiện tại, ưu tiên `ElasticsearchOperations` khi API sử dụng chung. Không ép thêm một Spring Data Elasticsearch phiên bản 4.x vào Boot 3.5 chỉ để giữ một class cũ.

## 15. Reactive Elasticsearch: cùng slice nhưng contract khác

Một ứng dụng có thể dùng:

~~~java
interface ReactiveCatalogRepository
        extends ReactiveElasticsearchRepository<CatalogItem, String> {
    Flux<CatalogItem> findByCategory(String category);
}
~~~

Đây là **skeleton**, cần imports của Spring Data Reactive Elasticsearch/Reactor và cấu hình thích hợp. Khi đã dùng reactive, test phải **subscribe publisher**:

~~~java
StepVerifier.create(repository.findById("P-1"))
        .assertNext(item ->
                assertThat(item.getSku()).isEqualTo("SKU-7"))
        .verifyComplete();
~~~

Đoạn này là test body minh họa; cần một `ReactiveElasticsearchRepository` bean và document P-1 đã được lưu.

Với reactive index operations:

~~~java
StepVerifier.create(
        reactiveOperations.indexOps(CatalogItem.class).refresh()
).verifyComplete();
~~~

`reactiveOperations` ở đây phải là **`ReactiveElasticsearchOperations`**, vì `ReactiveIndexOperations.refresh()` trả `Mono<Void>`. Trong ví dụ chính, `ElasticsearchOperations.indexOps(...).refresh()` trả `void`; không truyền nó cho `StepVerifier`.

Dù Boot 3.5 liệt kê reactive client/repositories auto-config trong data slice, điều đó không bảo đảm bean reactive được tạo khi thiếu dependency hoặc điều kiện. Khi test production WebFlux controller, dùng `@WebFluxTest`/`@SpringBootTest` phù hợp; test data slice không tự xác minh HTTP reactive routing.

## 16. Khi nào cần @Import hoặc @ConfigurationProperties?

Nếu repository test cần custom converter hoặc một cấu hình mapping nhỏ:

~~~java
@DataElasticsearchTest
@Import(CustomElasticsearchConvertersConfig.class)
class CatalogWithConverterTest {
    // Test mapping thật với cấu hình được import.
}
~~~

Đây là skeleton; `CustomElasticsearchConvertersConfig` phải là class thực trong project. Không đưa cả hệ thống `@Service`/`@Configuration` vào data slice chỉ để sửa một dependency.

Nếu test cần một properties bean riêng:

~~~java
@DataElasticsearchTest(
        properties = "app.search.allow-synonyms=true"
)
@EnableConfigurationProperties(SearchFeatureProperties.class)
class CatalogWithPropertiesTest {
    // Test dùng bean SearchFeatureProperties đã đăng ký.
}
~~~

`@DataElasticsearchTest(properties=...)` **cung cấp property value**, nhưng không tự đăng ký mọi class `@ConfigurationProperties`. `@EnableConfigurationProperties` dùng khi cần bind class thực. Hai ví dụ này chỉ minh họa annotation setup, không phải tệp Java độc lập; không áp dụng nếu project không có các class đó.

Nếu cần business service thật, có thể import riêng service và mock các dependency ngoài phạm vi. Tuy vậy, khi số lượng bean cần import ngày càng lớn, cân nhắc `@SpringBootTest` thay vì phá ranh giới slice.

## 17. Nếu CI không có Docker thì sao?

Test slice có client Elasticsearch **không bắt buộc luôn dùng Testcontainers**, nhưng phải có một backend phù hợp để kiểm tra hành vi thật:

- Một Elasticsearch service do CI tạo và cô lập.
- Một cluster test tách production, có index riêng và cleanup rõ ràng.
- Testcontainers với Docker/Colima/Podman được cấu hình tương thích.
- Unit tests dùng mock repository, **không** đưa ra kết luận về query/mapping.

Nếu test chạy trong môi trường không có Docker, đừng viết báo cáo “Elasticsearch mapping PASS” khi chưa có server. Phân loại chính xác là **hạ tầng test chưa khả dụng**. Nếu không cần test mapping, dùng Mockito ở unit test nhưng đổi tên bài test cho đúng phạm vi.

### Không dùng production cluster làm fixture

Các lời gọi như `index.delete()`, `repository.deleteAll()` hoặc xóa index templates đều có thể phá dữ liệu thật. Demo tạo/xóa index **chỉ** trên container tạm. Với shared test cluster, đặt tên index theo build/test namespace và có quyền hạn giới hạn.

### Test data và parallel execution

JUnit chạy song song hoặc nhiều CI worker cùng trỏ một index có thể gây lỗi:

~~~text
Test A: delete index
Test B: save document
Test A: create index
Test B: search -> index missing / unexpected results
~~~

Tách container/index per worker hoặc dùng cơ chế isolation. Không dùng `Thread.sleep` để che race. Spring TestContext cache cũng có thể reuse context; quản lý vòng đời container để nó sống đủ lâu cho client bean.

## 18. Những lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `DataElasticsearchTest` import không tồn tại trên Boot 4 | Dùng namespace Boot 3 | Đổi import Boot 4, thêm test starter feature |
| Import namespace Boot 4 không tồn tại trên Boot 3 | Copy ví dụ Boot 4 vào Boot 3 | Giữ namespace `boot.test.autoconfigure...` |
| Thiếu `ElasticsearchRestTemplate` | Dùng client/template legacy | Chuyển theo Spring Data version, ưu tiên `ElasticsearchOperations` |
| Context không khởi tạo | Thiếu cluster/client/config/credentials | Kiểm tra root cause và kết nối test server |
| Test mặc định gọi localhost:9200 | Không có Testcontainers/properties | Dùng `@ServiceConnection` hoặc connection config đúng |
| Lỗi TLS handshake/auth | TLS/client credentials khác server | Kiểm tra trust/cert/SSL properties |
| `NoSuchBeanDefinitionException` cho `@Service` | Service ngoài slice | Unit test riêng hoặc import cụ thể |
| Không tìm thấy repository | Package scan/dependency sai | Kiểm tra repository interface, starter và package |
| Không có index | `createIndex=false` và chưa create | Tạo index/mapping trong setup |
| `findById` thấy nhưng search rỗng | Chưa refresh index | `IndexOperations.refresh()` |
| Search field trả sai | `Text` vs `Keyword` hoặc analyzer | Xác minh mapping/query trên cluster thật |
| Test pass đơn lẻ, fail cả suite | Index bị xóa song song, container cache lifecycle | Isolation/test managed container |
| Docker không khởi động | Daemon/permissions/memory/image | Kiểm tra CI resource và Docker logs |
| Reactive test báo method `void` | Nhầm sync với reactive index ops | Đúng `ReactiveElasticsearchOperations` |
| Unit mock test được dùng làm kết luận integration | Repository không được gọi thật | Bổ sung real Elasticsearch tests |
| Boot 4 test có classpath mixed-version | Trộn test module 3.x/4.x | Dùng đúng BOM/version và dependency tree |

**Không chèn thêm một jar khác major để chữa lỗi compile.** Kiểm tra trước Spring Boot plugin, BOM, dependency tree và import; sau đó mới điều tra những lỗi runtime của Elasticsearch.

## 19. Quy trình migration theo từng bước

### Boot 2.7 lên Boot 3.x

1. Nâng JDK theo yêu cầu Boot 3 (Java 17+).
2. Đồng bộ Boot plugin, BOM, Spring Data Elasticsearch và Elasticsearch Java client.
3. Giữ namespace `@DataElasticsearchTest` thuộc `org.springframework.boot.test.autoconfigure.data.elasticsearch` ở 3.x.
4. Rà soát `ElasticsearchRestTemplate`, legacy REST client, repository query syntax và mapping.
5. Đối chiếu Elasticsearch server image tương thích; không dùng bừa 7.x/8.x/9.x.
6. Nếu dùng Boot 3.1+, cân nhắc `@ServiceConnection`; nếu dùng 3.0 vẫn cấu hình động theo công cụ hỗ trợ.
7. Chạy lại test save/find, search với refresh, update/delete và môi trường có TLS như dự kiến.

### Boot 3.x lên Boot 4.x

1. Đổi import sang `org.springframework.boot.data.elasticsearch.test.autoconfigure.DataElasticsearchTest`.
2. Thêm `spring-boot-starter-data-elasticsearch-test` vào test-scope theo dependency model Boot 4.
3. Rà soát package của các auto-configuration class và client REST5/Java API client.
4. Tránh giữ `spring-boot-test-autoconfigure:3.x` trong classpath Boot 4.
5. Kiểm tra Testcontainers/module version, service connection/SSL và server image.
6. Recompile rồi chạy lại **mapping/query**; chỉ `contextLoads` PASS là chưa đủ.
7. Phân biệt thay đổi index schema/migration ở production với thay đổi Java import.

Không coi một bài học dành cho Boot 3.5 là “universally runnable” cho Boot 2.7 hoặc Boot 4.x. Những dòng import và dependency theo phiên bản là một phần của hợp đồng bài học.

## 20. Chạy bộ test, QA và kết luận

Từ thư mục có Gradle Wrapper, Java 17+ và Docker hoạt động:

~~~bash
./gradlew test --tests "com.example.esdemo.CatalogElasticsearchSliceTest"
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.esdemo.CatalogElasticsearchSliceTest"
~~~

Bộ ví dụ có **5 `@Test`**: giới hạn slice, save/find by id, search theo `Keyword`, update và delete. Dựa trên API và thiết kế ví dụ, kết quả kỳ vọng là các assertions PASS **khi dependencies, image Docker và Elasticsearch server phù hợp**. Đây là nhận định sau khi kiểm tra logic mã, **không phải JUnit/Docker log đã chạy thực tế**. Code không in `System.out.println` nên không có stdout ứng dụng cố định; log Gradle/cluster phụ thuộc môi trường.

Checklist:

- [ ] Đã xác định đúng Spring Boot major/minor và import `@DataElasticsearchTest`?
- [ ] Boot 3.x dùng namespace cũ; Boot 4.x dùng namespace/module test mới?
- [ ] Plugin/BOM/test starters không trộn các major?
- [ ] Document dùng đúng `@Document`/`@Id` của Spring Data, repository không bị mock?
- [ ] Có Elasticsearch server thật hoặc đã ghi rõ đây chỉ là unit test mock?
- [ ] Docker image version được pin và có môi trường chạy?
- [ ] `@ServiceConnection`/properties khớp Boot version và TLS?
- [ ] Index test được tạo riêng và không phá shared/production data?
- [ ] Query search có bước refresh cần thiết?
- [ ] Mapping `Keyword`/`Text` được kiểm tra đúng semantic?
- [ ] Test có assert behavior query, không chỉ context startup?
- [ ] Không gắn `@SpringBootTest` khi chỉ cần repository slice?
- [ ] Nếu dùng reactive, method thực sự trả `Mono`/`Flux` và test subscribe?
- [ ] Container lifecycle tương thích Spring TestContext cache?
- [ ] Có quy trình migration test theo từng Boot major?

**Kết luận:** `@DataElasticsearchTest` là lựa chọn chính thống cho Spring Data Elasticsearch slice test, nhưng **khả năng hỗ trợ theo phiên bản** nằm ở namespace/module test, client/template và connection với Elasticsearch server. **Boot 2.7/3.x** và **Boot 4.x** không dùng cùng import. Khi cần kiểm tra query thật, cung cấp cluster test, quản lý index/mapping và refresh; khi cần HTTP full flow, nâng phạm vi sang integration test riêng.

### Tài liệu tham khảo chính thức

- [Spring Boot 2.7 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/docs/2.7.15/reference/htmlsingle/)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — Test Slices](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html)
- [Spring Boot 3.5 — Testcontainers và service connections](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)
- [Spring Boot 4.1 — Test Modules](https://docs.spring.io/spring-boot/reference/testing/test-modules.html)
- [Spring Boot 4.1 — DataElasticsearchTest Javadoc](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/data/elasticsearch/test/autoconfigure/DataElasticsearchTest.html)
- [Spring Data Elasticsearch — Object Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch — Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch 5.5 — IndicesTemplate API](https://docs.spring.io/spring-data/elasticsearch/docs/5.5.x/api/org/springframework/data/elasticsearch/client/elc/IndicesTemplate.html)