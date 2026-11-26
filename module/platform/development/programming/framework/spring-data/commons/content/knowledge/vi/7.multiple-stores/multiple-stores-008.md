# Kiểm thử cùng một ca sử dụng trên các store được chọn

## Mục tiêu bài học

Hai repository cùng dùng các abstraction của Spring Data Commons chưa chắc có hành vi nghiệp vụ tương đương. Mapping, query, collation, phân trang và cách dữ liệu trở nên nhìn thấy có thể khác giữa các store.

Muốn kiểm tra khả năng thay thế trong một ca sử dụng cụ thể, cần xác định hợp đồng hành vi chung, chạy cùng những kỳ vọng trên từng adapter và giữ phần chuẩn bị hạ tầng riêng cho mỗi store.

Bài học thuộc chương **Nhiều store** của module SPRING_DATA_COMMONS. Ví dụ chọn Spring Data JPA và Spring Data MongoDB để kiểm thử một ca tra cứu danh mục. Sau bài học, bạn có thể:

- Chuyển yêu cầu nghiệp vụ thành một bộ kiểm thử hợp đồng dùng lại được.
- Tách dữ liệu đầu vào và kết quả nghiệp vụ khỏi ID kỹ thuật của từng store.
- Kiểm chứng bộ lọc, thứ tự và metadata phân trang trên nguồn dữ liệu thật.
- Chuẩn bị fixture có phạm vi rõ và nhìn thấy được từ thao tác đọc.
- Phân biệt kiểm thử hợp đồng chung với kiểm thử đặc thù store và kiểm thử phối hợp nhiều store.

Các ví dụ bootstrap sử dụng namespace Spring Boot 3.x, Jakarta Persistence và Java 17. Khi dự án dùng bộ phiên bản khác, phần bootstrap cần phù hợp với bộ đó; các kỳ vọng nghiệp vụ vẫn phải được giữ rõ ràng.

## 1. Chọn một ca sử dụng đủ cụ thể

Ca sử dụng trong bài:

> Tra cứu sản phẩm đang hoạt động, có tên bắt đầu bằng một tiền tố, sắp theo tên rồi SKU tăng dần và trả kết quả phân trang kèm tổng số phần tử phù hợp.

Hợp đồng được chốt như sau:

| Khía cạnh | Quy định |
| --- | --- |
| Điều kiện hoạt động | Chỉ lấy sản phẩm có active bằng true. |
| Điều kiện tên | Tên bắt đầu bằng prefix theo ngữ nghĩa đã chọn. |
| Dữ liệu kiểm thử cơ sở | Chuỗi ASCII có cách viết hoa/thường nhất quán để kiểm chứng luồng cơ bản. |
| Thứ tự | name tăng dần, rồi sku tăng dần. |
| Trang | Chỉ số bắt đầu từ 0, kích thước dương. |
| Nội dung kết quả | SKU và tên, không công khai ID kỹ thuật của store. |
| Tổng số phần tử | Tổng của tập thỏa bộ lọc, không phải tổng mọi sản phẩm. |
| Không có kết quả phù hợp | Trang có content rỗng và tổng bằng 0. |
| Trang ngoài phạm vi | Content rỗng; vẫn phản ánh tổng của tập phù hợp. |

Dữ liệu cơ sở chưa kiểm chứng đầy đủ việc so sánh chữ hoa/thường, dấu tiếng Việt hoặc collation. Những yêu cầu đó phải được định nghĩa và bổ sung riêng nếu ca sử dụng thực tế cần.

Đây là kiểm thử một năng lực đã chọn, không phải tuyên bố rằng toàn bộ API JPA và MongoDB có thể hoán đổi.

## 2. Tách hợp đồng dùng chung khỏi model persistence

Hai store có thể dùng ID khác nhau, chẳng hạn Long của JPA và String của MongoDB. Ca tra cứu danh mục sử dụng SKU làm giá trị nhận diện nghiệp vụ trong kết quả thử.

Hai record sau đặt trong các file cùng tên ở package `com.example.catalog.core`:

~~~java
package com.example.catalog.core;

public record ProductSeed(
    String sku,
    String name,
    boolean active
) {
}
~~~

~~~java
package com.example.catalog.core;

public record ProductView(String sku, String name) {
}
~~~

Port truy vấn:

~~~java
package com.example.catalog.core;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface CatalogSearchPort {

    Page<ProductView> searchActiveByNamePrefix(
        String prefix,
        Pageable pageable
    );
}
~~~

Port chủ động dùng Page và Pageable của Commons. Điều đó giúp dùng lại mô hình phân trang chung, nhưng port vẫn có phụ thuộc framework theo lựa chọn thiết kế này.

Một service dùng chung xây yêu cầu truy vấn:

~~~java
package com.example.catalog.core;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

public class CatalogSearchService {

    private final CatalogSearchPort port;

    public CatalogSearchService(CatalogSearchPort port) {
        this.port = port;
    }

    public Page<ProductView> search(
            String prefix,
            int page,
            int size) {

        if (prefix == null || prefix.isBlank()) {
            throw new IllegalArgumentException(
                "Tiền tố tên không được để trống"
            );
        }

        Sort sort = Sort.by("name").ascending()
            .and(Sort.by("sku").ascending());

        return port.searchActiveByNamePrefix(
            prefix,
            PageRequest.of(page, size, sort)
        );
    }
}
~~~

Service không có nhánh chọn JPA hoặc MongoDB. Khác biệt được đặt trong adapter và cấu hình kiểm thử.

Các thuộc tính name và sku là một phần thỏa thuận giữa service với adapter trong ví dụ. Nếu model persistence đặt tên khác, adapter phải ánh xạ yêu cầu phù hợp thay vì truyền mù quáng đường dẫn thuộc tính không tồn tại.

## 3. Thiết kế fixture phân biệt được lỗi

Dùng một tập dữ liệu nhỏ:

| SKU | name | active |
| --- | --- | --- |
| P01 | Java Basics | true |
| P02 | Java Basics | true |
| P03 | Java Data | true |
| P04 | Java Legacy | false |
| P05 | Kotlin Intro | true |

Tập này có chủ đích:

- P04 giúp phát hiện query quên điều kiện active.
- P05 giúp phát hiện query quên điều kiện tiền tố tên.
- P01 và P02 có cùng tên để kiểm chứng tiêu chí sắp xếp phụ.
- Ba kết quả phù hợp với kích thước trang 2 tạo được một trang đầy và một trang cuối thiếu phần tử.

Với prefix Java, thứ tự kết quả là P01, P02, P03. Tổng phần tử phù hợp là 3 dù fixture có 5 sản phẩm.

Không sắp theo ID kỹ thuật tự sinh để so sánh hai store. Giá trị và chiến lược sinh ID có thể khác mà không làm ca sử dụng sai.

Fixture trong bài có SKU riêng biệt. Nếu ứng dụng yêu cầu tính duy nhất SKU trên toàn hệ thống, cần thiết lập ràng buộc hoặc index phù hợp ở từng store và kiểm thử invariant đó riêng.

## 4. Adapter JPA

Các lớp sau thuộc package `com.example.catalog.jpa`. Mỗi kiểu public nằm trong file cùng tên.

### 4.1. Model persistence

~~~java
package com.example.catalog.jpa;

import com.example.catalog.core.ProductSeed;
import com.example.catalog.core.ProductView;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "catalog_product")
public class JpaProduct {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String sku;

    private String name;

    private boolean active;

    protected JpaProduct() {
    }

    public JpaProduct(ProductSeed seed) {
        this.sku = seed.sku();
        this.name = seed.name();
        this.active = seed.active();
    }

    public ProductView toView() {
        return new ProductView(sku, name);
    }
}
~~~

JPA sử dụng field access vì annotation mapping được đặt trên field. Không cần getter chỉ để query có thể tham chiếu các thuộc tính được mapping.

Chiến lược ID và mapping phải phù hợp với SQL engine được chọn cho kiểm thử.

### 4.2. Repository và adapter

~~~java
package com.example.catalog.jpa;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface JpaProductRepository
        extends JpaRepository<JpaProduct, Long> {

    Page<JpaProduct> findByActiveTrueAndNameStartingWith(
        String prefix,
        Pageable pageable
    );
}
~~~

~~~java
package com.example.catalog.jpa;

import com.example.catalog.core.CatalogSearchPort;
import com.example.catalog.core.ProductView;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public class JpaCatalogAdapter implements CatalogSearchPort {

    private final JpaProductRepository repository;

    public JpaCatalogAdapter(JpaProductRepository repository) {
        this.repository = repository;
    }

    @Override
    public Page<ProductView> searchActiveByNamePrefix(
            String prefix,
            Pageable pageable) {

        return repository
            .findByActiveTrueAndNameStartingWith(
                prefix,
                pageable
            )
            .map(JpaProduct::toView);
    }
}
~~~

Điều kiện được đưa vào query trước khi phân trang. Adapter dùng Page.map để chuyển nội dung mà vẫn giữ metadata phân trang.

Không lấy một trang tất cả sản phẩm rồi lọc active trong Java. Cách đó không kiểm chứng đúng hợp đồng về tổng số kết quả phù hợp.

## 5. Adapter MongoDB

Các lớp tương ứng thuộc package `com.example.catalog.mongo`.

### 5.1. Model persistence riêng

~~~java
package com.example.catalog.mongo;

import com.example.catalog.core.ProductSeed;
import com.example.catalog.core.ProductView;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "catalog_products")
public class MongoProduct {

    @Id
    private String id;

    private String sku;

    private String name;

    private boolean active;

    protected MongoProduct() {
    }

    public MongoProduct(ProductSeed seed) {
        this.sku = seed.sku();
        this.name = seed.name();
        this.active = seed.active();
    }

    public ProductView toView() {
        return new ProductView(sku, name);
    }
}
~~~

Không cần gắn đồng thời @Entity và @Document lên cùng một lớp để tái sử dụng kiểm thử. Model riêng giúp giữ mapping và định danh của từng store rõ ràng.

### 5.2. Repository và adapter

~~~java
package com.example.catalog.mongo;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface MongoProductRepository
        extends MongoRepository<MongoProduct, String> {

    Page<MongoProduct> findByActiveTrueAndNameStartingWith(
        String prefix,
        Pageable pageable
    );
}
~~~

~~~java
package com.example.catalog.mongo;

import com.example.catalog.core.CatalogSearchPort;
import com.example.catalog.core.ProductView;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public class MongoCatalogAdapter implements CatalogSearchPort {

    private final MongoProductRepository repository;

    public MongoCatalogAdapter(
            MongoProductRepository repository) {
        this.repository = repository;
    }

    @Override
    public Page<ProductView> searchActiveByNamePrefix(
            String prefix,
            Pageable pageable) {

        return repository
            .findByActiveTrueAndNameStartingWith(
                prefix,
                pageable
            )
            .map(MongoProduct::toView);
    }
}
~~~

Hai repository có tên method tương tự, nhưng query được tạo và thực thi bởi hai module khác nhau. Chính kết quả từ nguồn dữ liệu thật mới cung cấp bằng chứng rằng hai adapter đáp ứng hợp đồng đang kiểm thử.

## 6. Viết bộ kiểm thử hợp đồng dùng chung

Bộ kiểm thử phụ thuộc port và dữ liệu nghiệp vụ. Nó không biết entity JPA, document MongoDB hoặc kiểu ID kỹ thuật.

File `CatalogSearchContract.java` trong package `com.example.catalog.contract`:

~~~java
package com.example.catalog.contract;

import com.example.catalog.core.CatalogSearchPort;
import com.example.catalog.core.CatalogSearchService;
import com.example.catalog.core.ProductSeed;
import com.example.catalog.core.ProductView;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.Page;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

public abstract class CatalogSearchContract {

    private CatalogSearchService service;

    protected abstract CatalogSearchPort searchPort();

    protected abstract void replaceFixture(
        List<ProductSeed> products
    );

    @BeforeEach
    protected void prepareFixture() {
        replaceFixture(List.of(
            new ProductSeed("P01", "Java Basics", true),
            new ProductSeed("P02", "Java Basics", true),
            new ProductSeed("P03", "Java Data", true),
            new ProductSeed("P04", "Java Legacy", false),
            new ProductSeed("P05", "Kotlin Intro", true)
        ));

        service = new CatalogSearchService(searchPort());
    }

    @Test
    protected void returnsOnlyActiveProductsWithPrefix() {
        Page<ProductView> result =
            service.search("Java", 0, 10);

        assertEquals(
            List.of("P01", "P02", "P03"),
            skus(result)
        );
        assertEquals(
            "Java Basics",
            result.getContent().get(0).name()
        );
        assertEquals(3L, result.getTotalElements());
    }

    @Test
    protected void keepsOrderAndMetadataAcrossPages() {
        Page<ProductView> first =
            service.search("Java", 0, 2);

        Page<ProductView> second =
            service.search("Java", 1, 2);

        assertEquals(List.of("P01", "P02"), skus(first));
        assertEquals(List.of("P03"), skus(second));

        assertEquals(3L, first.getTotalElements());
        assertEquals(3L, second.getTotalElements());
        assertEquals(2, first.getTotalPages());

        assertEquals(1, second.getNumber());
        assertEquals(2, second.getSize());
        assertEquals(1, second.getNumberOfElements());

        assertTrue(first.hasNext());
        assertFalse(second.hasNext());
    }

    @Test
    protected void returnsEmptyResultForMissingPrefix() {
        Page<ProductView> result =
            service.search("Rust", 0, 2);

        assertTrue(result.getContent().isEmpty());
        assertEquals(0L, result.getTotalElements());
    }

    @Test
    protected void keepsFilteredTotalForPageBeyondEnd() {
        Page<ProductView> result =
            service.search("Java", 2, 2);

        assertTrue(result.getContent().isEmpty());
        assertEquals(3L, result.getTotalElements());
    }

    private static List<String> skus(
            Page<ProductView> page) {

        return page.getContent().stream()
            .map(ProductView::sku)
            .toList();
    }
}
~~~

Những method kiểm thử để protected giúp các lớp con ở package khác kế thừa bộ hành vi cần chạy. Hai hook chỉ cung cấp port và cách thay fixture; toàn bộ kỳ vọng được giữ chung.

Các kiểm tra này nhắm vào hành vi có thể quan sát:

- Đúng tập dữ liệu sau lọc.
- Đúng nội dung DTO.
- Đúng thứ tự khi tên bị trùng.
- Đúng ranh giới trang và tổng số phần tử.
- Phân biệt không có kết quả với yêu cầu một trang nằm ngoài phạm vi.

Chúng không so sánh class proxy, số lượng SQL hay hình dạng query MongoDB.

## 7. Chạy cùng hợp đồng trong hai ngữ cảnh kiểm thử riêng

Một bố cục thực hành phù hợp:

~~~text
catalog-core
    Port, service, ProductSeed, ProductView

catalog-contract-testkit
    CatalogSearchContract

catalog-jpa-it
    Model JPA, repository, adapter, bootstrap và test JPA

catalog-mongo-it
    Model MongoDB, repository, adapter, bootstrap và test MongoDB
~~~

Đóng gói testkit dưới dạng thư viện hoặc test fixture mà hai module kiểm thử sử dụng được. Testkit cần Commons và JUnit Jupiter; mỗi module tích hợp cần Spring Boot test cùng dependency của store tương ứng.

Trong bố cục này, module JPA kiểm thử chỉ đưa module repository JPA vào classpath; module MongoDB kiểm thử chỉ đưa module repository MongoDB vào. Điều đó cô lập phép kiểm chứng adapter và tránh vô tình khởi tạo một kết nối không liên quan.

Ứng dụng đầy đủ có cả hai store vẫn cần một kiểm thử cấu hình kết hợp riêng. Hai bộ thử độc lập không thay thế việc kiểm chứng strict repository configuration, scanning và injection trong ứng dụng nhiều store thực tế.

### 7.1. Bootstrap JPA

~~~java
package com.example.catalog.jpa;

import com.example.catalog.core.CatalogSearchPort;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.context.annotation.Bean;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@SpringBootConfiguration
@EnableAutoConfiguration
@EntityScan(basePackageClasses = JpaProduct.class)
@EnableJpaRepositories(
    basePackageClasses = JpaProductRepository.class
)
public class JpaContractConfiguration {

    @Bean
    CatalogSearchPort searchPort(
            JpaProductRepository repository) {
        return new JpaCatalogAdapter(repository);
    }
}
~~~

Lớp thực thi lại bộ kiểm thử:

~~~java
package com.example.catalog.jpa;

import com.example.catalog.contract.CatalogSearchContract;
import com.example.catalog.core.CatalogSearchPort;
import com.example.catalog.core.ProductSeed;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(classes = JpaContractConfiguration.class)
@ActiveProfiles("jpa-contract")
public class JpaCatalogContractTest
        extends CatalogSearchContract {

    @Autowired
    private CatalogSearchPort port;

    @Autowired
    private JpaProductRepository repository;

    @Override
    protected CatalogSearchPort searchPort() {
        return port;
    }

    @Override
    protected void replaceFixture(
            List<ProductSeed> products) {

        repository.deleteAll();
        repository.saveAll(
            products.stream()
                .map(JpaProduct::new)
                .toList()
        );
    }
}
~~~

### 7.2. Bootstrap MongoDB

~~~java
package com.example.catalog.mongo;

import com.example.catalog.core.CatalogSearchPort;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@SpringBootConfiguration
@EnableAutoConfiguration
@EnableMongoRepositories(
    basePackageClasses = MongoProductRepository.class
)
public class MongoContractConfiguration {

    @Bean
    CatalogSearchPort searchPort(
            MongoProductRepository repository) {
        return new MongoCatalogAdapter(repository);
    }
}
~~~

Lớp chạy hợp đồng trên MongoDB:

~~~java
package com.example.catalog.mongo;

import com.example.catalog.contract.CatalogSearchContract;
import com.example.catalog.core.CatalogSearchPort;
import com.example.catalog.core.ProductSeed;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(classes = MongoContractConfiguration.class)
@ActiveProfiles("mongo-contract")
public class MongoCatalogContractTest
        extends CatalogSearchContract {

    @Autowired
    private CatalogSearchPort port;

    @Autowired
    private MongoProductRepository repository;

    @Override
    protected CatalogSearchPort searchPort() {
        return port;
    }

    @Override
    protected void replaceFixture(
            List<ProductSeed> products) {

        repository.deleteAll();
        repository.saveAll(
            products.stream()
                .map(MongoProduct::new)
                .toList()
        );
    }
}
~~~

Các lớp kết thúc bằng Test để phù hợp quy ước phát hiện test phổ biến. Nếu dự án dùng tên IT hoặc cơ chế tích hợp riêng, cấu hình bộ chạy phải thực sự chọn các lớp đó; một bộ test không được phát hiện không phải kết quả PASS.

## 8. Cấp môi trường kiểm thử có thể tái lập

Chọn SQL engine và MongoDB version theo các store mà ứng dụng thực sự dự định hỗ trợ. Có thể cấp dịch vụ qua container hoặc một môi trường kiểm thử riêng.

Với bootstrap Boot 3.x ở trên, cấu hình test JPA có thể đặt trong `application-jpa-contract.yml` của module tương ứng:

~~~yaml
spring:
  datasource:
    url: ${CATALOG_TEST_JDBC_URL}
    username: ${CATALOG_TEST_JDBC_USER}
    password: ${CATALOG_TEST_JDBC_PASSWORD}

  jpa:
    hibernate:
      ddl-auto: create-drop
~~~

Driver JDBC của engine được chọn phải có trong dependency kiểm thử. Create-drop chỉ phù hợp khi database/schema được cấp riêng cho bộ thử và được phép tạo/dọn schema.

Cấu hình MongoDB trong `application-mongo-contract.yml`:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${CATALOG_TEST_MONGODB_URI}
~~~

URI phải hướng đến database dành riêng cho lần chạy thử. Fixture đang dùng deleteAll nên phạm vi đó phải được kiểm soát rõ, không dùng một database dùng chung với dữ liệu khác.

Các giá trị kết nối cần được cấp rõ ràng. Không thêm fallback âm thầm sang một database cục bộ chỉ để test có thể khởi động.

Thông tin nên ghi nhận cùng kết quả:

| Thông tin | Mục đích |
| --- | --- |
| Module Spring Data và bộ phiên bản | Biết chính xác implementation đã được kiểm chứng. |
| Engine và phiên bản server | Tránh kết luận từ một engine thay thế khác production. |
| Collation, read preference hoặc cấu hình đọc liên quan | Giải thích ngữ nghĩa so sánh và tính nhìn thấy dữ liệu. |
| Profile và cấu hình bootstrap | Xác nhận đúng adapter đang chạy. |
| Số test được phát hiện và kết quả từng store | Tránh thiếu một nhánh mà vẫn coi cả bộ hỗ trợ đã đạt. |

Không ghi credentials vào báo cáo. Khi cần lưu cấu hình để tái lập, chỉ ghi những thuộc tính và tham số phù hợp với mục đích chẩn đoán.

## 9. Fixture, transaction và tính nhìn thấy dữ liệu

### 9.1. Không dựa vào rollback chung cho mọi store

Các lớp trên dùng SpringBootTest và không đặt @Transactional lên lớp kiểm thử. SpringBootTest tự nó không tạo transaction bao quanh mỗi test.

Với cấu hình JPA thông thường, các lời gọi ghi kế thừa trên repository có transaction tương ứng. Khi không có transaction test bao ngoài, fixture có thể hoàn tất các phạm vi ghi trước khi service truy vấn.

MongoDB không tự có cùng cơ chế rollback chỉ vì test JPA thường được viết với transaction. Fixture phải được dọn theo phạm vi dữ liệu của nó.

Ví dụ này kiểm thử truy vấn, không yêu cầu transaction MongoDB nhiều document. Nó giả định các lần ghi được xác nhận và đọc theo primary phù hợp với môi trường đã chọn.

### 9.2. Tránh đọc lại chỉ từ trạng thái đang quản lý

Trong JPA, persistence context có thể giữ entity đã được quản lý. Một test chỉ sửa entity rồi đọc cùng instance có thể không kiểm chứng đường dữ liệu mong muốn.

Với khung trên, fixture không chia sẻ một transaction test bao ngoài với lời gọi service. Query cần thực sự thực hiện qua repository và mapping của adapter.

Nếu thay đổi khung sang một test có transaction bao ngoài, hãy xác định nhu cầu flush, clear hoặc đọc trong một phạm vi khác theo mục tiêu kiểm chứng. Flush không đồng nghĩa commit.

### 9.3. Không chạy song song những test đang xóa cùng tập dữ liệu

Hai test cùng gọi deleteAll trên một database/schema hoặc collection sẽ làm fixture của nhau biến mất.

Chọn một trong các cách tổ chức:

- Mỗi lần chạy hoặc mỗi nhóm test có nguồn dữ liệu riêng.
- Mỗi ca có namespace/dữ liệu riêng cùng cơ chế dọn tương ứng.
- Các ca dùng chung vùng dọn dữ liệu được thực thi tuần tự.

Không chữa tính không ổn định bằng cách nới lỏng assertion hoặc thêm một thời gian ngủ cố định.

Nếu chọn một store có dữ liệu trở nên tìm kiếm được theo cơ chế eventual consistency, fixture adapter cần cơ chế đồng bộ hoặc chờ điều kiện có thời hạn theo đúng store. Đó phải là một phần được mô tả rõ của môi trường thử.

## 10. Kỳ vọng nào dùng chung, kỳ vọng nào cần tách?

| Nhóm | Ví dụ | Cách tổ chức |
| --- | --- | --- |
| Hợp đồng nghiệp vụ chung | Active, prefix, thứ tự, nội dung DTO, metadata trang. | Cùng một bộ assertion cho mọi adapter đã cam kết hỗ trợ. |
| Kiểm tra service thuần Java | Từ chối prefix null hoặc rỗng trước khi gọi port. | Kiểm thử nhanh một lần cho service. |
| Đặc thù mapping | Chuyển đổi ID, tên cột/trường, null và kiểu dữ liệu. | Kiểm thử theo adapter/store. |
| Ràng buộc và đồng thời | Index duy nhất, optimistic locking, transaction. | Kiểm thử theo khả năng và hợp đồng store. |
| Hiệu năng | Index, count query, trang sâu, lượng dữ liệu. | Kịch bản đo riêng với dữ liệu đại diện. |
| Cấu hình nhiều store | Scan đúng module, template/factory/manager đúng. | Kiểm thử context ứng dụng kết hợp. |
| Nghiệp vụ ghi qua nhiều store | Một phía thất bại, đồng bộ hoặc bù dữ liệu. | Kiểm thử luồng phối hợp riêng. |

Không chạy lại một kiểm tra prefix null trên mọi database rồi coi đó là bằng chứng các store xử lý lỗi đầu vào giống nhau. Nếu service từ chối trước khi gọi port, test đó không đi tới adapter.

Ngược lại, mock một repository trả Page đúng như mong đợi chỉ kiểm chứng cách service sử dụng kết quả giả. Nó không kiểm chứng derived query, mapping, bộ lọc hoặc count của nguồn dữ liệu thật.

## 11. Những khác biệt phải được quyết định trước khi mở rộng hợp đồng

### 11.1. Chữ hoa/thường, dấu và collation

Dữ liệu ASCII trong bộ thử giúp cô lập luồng cơ bản. Nếu nghiệp vụ yêu cầu tìm tên không phân biệt hoa thường hoặc dấu, bổ sung dữ liệu phân biệt được các trường hợp đó.

Không mặc định IgnoreCase hoặc cùng một tên derived query tạo ngữ nghĩa tương đương trong mọi engine và collation.

### 11.2. Giá trị null và chuỗi rỗng

Null, chuỗi rỗng và thiếu một field document không phải lúc nào cũng được lưu và đối chiếu giống nhau.

Nếu tên sản phẩm có thể thiếu, hợp đồng phải nói rõ có loại khỏi kết quả không, sắp ở đâu và DTO biểu diễn thế nào. Sau đó mới chọn dữ liệu thử và cơ chế mapping tương ứng.

### 11.3. Phân trang và thay đổi đồng thời

Bộ thử giữ fixture không đổi để kiểm chứng ranh giới trang. Nó chưa kiểm chứng việc dữ liệu bị chèn hoặc xóa giữa hai lần đọc.

Một thứ tự có tiêu chí phụ làm thứ tự rõ hơn, nhưng không tự tạo snapshot xuyên các lần gọi. Nếu nghiệp vụ cần bảo đảm cao hơn, bổ sung kịch bản và chiến lược duyệt dữ liệu phù hợp.

### 11.4. Tập khả năng được hỗ trợ

JPA và MongoDB trong ví dụ được chọn vì có thể cung cấp hợp đồng Page cho query đó.

Nếu thêm một store không hỗ trợ đúng yêu cầu, cần điều chỉnh thiết kế adapter hoặc hợp đồng được hỗ trợ. Không bỏ qua assertion tổng số phần tử ở store đó rồi vẫn tuyên bố cùng một hợp đồng đã đạt.

Một ma trận tính năng giúp diễn đạt rõ: ca nào là cam kết chung, ca nào chưa được hỗ trợ và ca nào có ngữ nghĩa riêng.

## 12. Đọc lỗi theo tầng, không sửa kỳ vọng để hợp thức hóa khác biệt

| Quan sát | Câu hỏi điều tra |
| --- | --- |
| Test không khởi động được. | Bootstrap, dependency, kết nối hoặc mapping có đúng không? |
| Một store không có lớp test được chạy. | Bộ chạy có phát hiện lớp cụ thể và các test kế thừa không? |
| P04 xuất hiện trong kết quả. | Điều kiện active đã được đưa vào query chưa? |
| P05 xuất hiện với prefix Java. | Query có lọc tiền tố tên đúng không? |
| P01/P02 đổi vị trí không ổn định. | Tiêu chí phụ sku có được truyền và áp dụng không? |
| Content đúng nhưng total bằng 5. | Count có phản ánh bộ lọc hay đang đếm toàn bộ fixture? |
| Chạy riêng đạt, chạy cả bộ thất bại. | Fixture dùng chung, chạy song song, profile hoặc context có ảnh hưởng nhau không? |
| JPA đạt trên H2 nhưng thất bại trên engine đích. | Ngữ nghĩa SQL, collation, mapping hoặc cấu hình nào khác nhau? |
| MongoDB chỉ thỉnh thoảng thấy thiếu dữ liệu vừa seed. | Read preference, xác nhận ghi và môi trường có đúng giả định không? |

Nếu một assertion phản ánh yêu cầu nghiệp vụ đã chốt, việc nó thất bại là thông tin cần điều tra. Không tự đổi danh sách kết quả mong đợi theo từng store chỉ để hai màu báo cáo đều xanh.

Nếu yêu cầu ban đầu chưa đúng hoặc chưa đủ rõ, hãy sửa hợp đồng một cách có chủ đích rồi cập nhật tất cả adapter và kỳ vọng liên quan.

## 13. Bài tập vận dụng

### Bài tập 1: Bổ sung một ca phân biệt toán tử

Thêm sản phẩm có tên “Advanced Java” và active bằng true. Xác định vì sao sản phẩm đó không được trả về khi prefix là Java.

Ca này giúp phân biệt tìm theo tiền tố với tìm chứa một chuỗi ở bất kỳ vị trí nào.

### Bài tập 2: Bổ sung yêu cầu hoa/thường

Nghiệp vụ muốn “java” và “Java” có cùng kết quả. Hãy viết bảng dữ liệu và kỳ vọng trước, rồi đánh giá cách mỗi adapter hiện thực yêu cầu.

Giải thích vì sao chỉ đổi dữ liệu thử mà không xác định collation hoặc toán tử có thể tạo một bộ test thiếu căn cứ.

### Bài tập 3: Thêm store thứ ba

Liệt kê những phần cần giữ nguyên và những phần cần bổ sung:

- Hợp đồng và assertion chung.
- Model mapping, repository hoặc API truy vấn.
- Fixture và hạ tầng kết nối.
- Cơ chế nhìn thấy dữ liệu.
- Các giới hạn hoặc năng lực chưa đáp ứng.

Không thêm một nhánh kiểm tra tên store vào assertion chung nếu mục tiêu vẫn là cam kết cùng hành vi.

### Bài tập 4: Kiểm chứng ứng dụng kết hợp

Sau khi hai adapter đạt hợp đồng độc lập, thiết kế một kiểm thử context cho ứng dụng có cả JPA và MongoDB.

Xác định riêng cách kiểm chứng repository thuộc đúng module và cách kiểm chứng ca ghi cần phối hợp hai store. Giải thích vì sao bộ tra cứu chung không tự chứng minh giao dịch xuyên store là nguyên tử.

Một bộ kiểm thử dùng lại có giá trị khi nó giữ nguyên yêu cầu nghiệp vụ nhưng cho phép từng store có cách mapping, cấp dữ liệu và thực thi riêng. Kết quả đạt chỉ xác nhận ca sử dụng, dữ liệu và cấu hình đã được kiểm chứng; phạm vi tương đương cần được mở rộng bằng những hợp đồng cụ thể tiếp theo.