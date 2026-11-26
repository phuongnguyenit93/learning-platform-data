# Kiểm thử hồi quy cùng bộ ca sử dụng trên các phiên bản hoặc store mục tiêu

## 1. Hồi quy cần được đánh giá bằng hợp đồng của ứng dụng

Trong chương **Kiểm thử** của module **SPRING_DATA_COMMONS**, một thay đổi dependency hoặc kho dữ liệu cần được đánh giá qua những hành vi ứng dụng đang sử dụng: CRUD, derived query, phân trang, sắp xếp, projection, auditing hoặc fragment tùy chỉnh.

Việc ứng dụng khởi động thành công chưa chứng minh các hành vi đó vẫn đúng. Một query có thể chạy nhưng thiếu điều kiện tenant, thứ tự phân trang có thể thay đổi, hoặc constructor của projection có thể nhận dữ liệu khác trước.

Ý tưởng của bộ ca hồi quy dùng chung là:

~~~text
Cùng dữ liệu logic + cùng hành động + cùng kỳ vọng
                         |
          +--------------+--------------+
          |                             |
          v                             v
Cấu hình nền đã chốt           Cấu hình ứng viên đã chốt
          |                             |
          v                             v
  Kết quả và bằng chứng          Kết quả và bằng chứng
          +--------------+--------------+
                         |
                         v
         Đối chiếu với hợp đồng ứng dụng
~~~

Cấu hình nền là điểm so sánh, không phải nguồn chân lý duy nhất. Nếu phiên bản cũ đã có lỗi, giữ nguyên kết quả sai không phải mục tiêu hồi quy.

Bài này minh họa một hợp đồng đọc danh mục bằng **Java 17, JUnit Jupiter và Spring Boot 3.5**, với hai adapter sử dụng **Spring Data JPA 3.5** và **Spring Data MongoDB 4.5**. Các con số này xác định phạm vi ví dụ, không phải tuyên bố về phiên bản mới nhất.

## 2. Hai trục kiểm thử cần phân biệt

### 2.1. Cùng store, thay phiên bản

Ví dụ giữ PostgreSQL và dữ liệu test không đổi, thay bộ dependency của ứng dụng. Mục tiêu là phát hiện thay đổi ở mapping, query derivation, driver, provider hoặc cấu hình mặc định.

Một lượt chạy phải ghi nhận phiên bản dependency thực sự được resolve. Nhãn “mới” hoặc “hiện tại” không đủ để tái hiện lỗi.

Các module Spring Data có thể có số phiên bản khác nhau nhưng thuộc cùng release train. Nên sử dụng dependency management/BOM tương thích thay vì tự ghép Commons, JPA và MongoDB theo số phiên bản nhìn có vẻ giống nhau. Xem [Dependencies của Spring Data Commons](https://docs.spring.io/spring-data/commons/reference/3.5/dependencies.html).

### 2.2. Cùng ca sử dụng, thay store

Ví dụ cùng yêu cầu “liệt kê sản phẩm active của tenant, có thứ tự và phân trang”, một adapter dùng JPA, adapter khác dùng MongoDB.

Điều cần giống nhau là hành vi đã cam kết cho caller. Không bắt SQL, BSON, tên index, ID vật lý hoặc số lần truy cập nội bộ phải giống nhau nếu chúng không thuộc hợp đồng đó.

Khả năng query và một số toán tử phụ thuộc store. Commons cung cấp abstraction nhưng không bảo đảm mọi backend hỗ trợ cùng tập truy vấn. Xem [Defining Query Methods](https://docs.spring.io/spring-data/commons/reference/3.5/repositories/query-methods-details.html).

Nếu một yêu cầu bắt buộc không thể thực hiện đúng trên store ứng viên, cần báo không đáp ứng mục tiêu. Không loại yêu cầu đó khỏi bộ test để tạo một kết quả xanh.

## 3. Chốt hợp đồng trước khi xây ma trận

Ca sử dụng minh họa có hợp đồng:

- Chỉ trả sản phẩm active của tenant được yêu cầu.
- Sắp xếp tăng dần theo label, sau đó theo key để phân biệt trường hợp label bằng nhau.
- Số trang bắt đầu từ 0.
- Tổng số phần tử chỉ tính các sản phẩm phù hợp điều kiện.
- Tenant không có dữ liệu nhận danh sách rỗng và tổng bằng 0.
- Trang vượt phạm vi nhận danh sách rỗng nhưng vẫn giữ tổng số phù hợp.

Fixture dùng key và chuỗi đơn giản do test kiểm soát. Với yêu cầu liên quan tiếng Việt, dấu, hoa thường hoặc collation, cần thêm dữ liệu cùng kỳ vọng cụ thể; bộ dữ liệu ASCII không chứng minh các trường hợp đó.

| Key | Tenant | Label | Active |
| --- | --- | --- | --- |
| A2 | north | Shared | true |
| A1 | north | Shared | true |
| A3 | north | Zulu | true |
| A4 | north | Hidden | false |
| B1 | south | Shared | true |

Hai bản ghi Shared kiểm tra khóa sort phụ. Bản ghi inactive và tenant khác giúp bắt lỗi thiếu điều kiện lọc.

Không để implementation nền tự sinh expected result. Kỳ vọng phải xuất phát từ yêu cầu và fixture, chẳng hạn A1, A2, A3 theo đúng thứ tự.

## 4. Mô hình kết quả và lớp kết nối cho test

Các public type dưới đây đặt trong các file Java riêng. Package dùng chung là `example.regression.contract`; adapter JPA và MongoDB đặt ở package riêng.

### 4.1. Dữ liệu đầu vào và view

~~~java
package example.regression.contract;

public record ProductSeed(
        String key,
        String tenant,
        String label,
        boolean active) {
}
~~~

~~~java
package example.regression.contract;

public record CatalogCard(String key, String label) {
}
~~~

~~~java
package example.regression.contract;

import java.util.List;
import java.util.function.Function;

import org.springframework.data.domain.Page;

public record SearchPage(
        List<CatalogCard> items,
        long total,
        int number,
        int size) {

    public SearchPage {
        items = List.copyOf(items);
    }

    public static <T> SearchPage from(
            Page<T> source,
            Function<T, CatalogCard> mapper) {

        return new SearchPage(
                source.getContent().stream()
                        .map(mapper)
                        .toList(),
                source.getTotalElements(),
                source.getNumber(),
                source.getSize());
    }
}
~~~

Hàm chuyển đổi chỉ đổi hình dạng kết quả. Nó không lọc lại, sort lại hoặc tự tính tổng để che lỗi query của adapter.

### 4.2. Giao diện fixture

~~~java
package example.regression.contract;

import java.util.List;

public interface CatalogHarness {

    void reset();

    void seed(List<ProductSeed> products);

    SearchPage searchActive(
            String tenant,
            int page,
            int size);
}
~~~

Đây là lớp kết nối dành cho bộ test minh họa. `reset` và `seed` quản lý fixture trên database test riêng; `searchActive` phải đi qua repository thật.

Trong dự án đã có application port phù hợp, có thể chạy ca sử dụng qua port đó. Không cần tạo một abstraction mới chỉ vì dùng contract test.

## 5. Viết bộ ca dùng chung bằng JUnit Jupiter

JUnit Jupiter cho phép test và lifecycle method nằm trong default method của interface. Các lớp test cụ thể triển khai interface để chạy lại cùng các ca. Xem [Test Interfaces and Default Methods](https://docs.junit.org/5.12.2/user-guide/#writing-tests-test-interfaces-and-default-methods).

~~~java
package example.regression.contract;

import java.util.List;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

public interface CatalogRegressionContract {

    CatalogHarness harness();

    @BeforeEach
    default void seedScenario() {
        harness().reset();

        harness().seed(List.of(
                new ProductSeed(
                        "A2", "north", "Shared", true),
                new ProductSeed(
                        "A1", "north", "Shared", true),
                new ProductSeed(
                        "A3", "north", "Zulu", true),
                new ProductSeed(
                        "A4", "north", "Hidden", false),
                new ProductSeed(
                        "B1", "south", "Shared", true)));
    }

    @AfterEach
    default void cleanScenario() {
        harness().reset();
    }

    @Test
    default void filtersTenantAndActiveWithStableOrder() {
        SearchPage result =
                harness().searchActive("north", 0, 10);

        assertThat(result.items()).containsExactly(
                new CatalogCard("A1", "Shared"),
                new CatalogCard("A2", "Shared"),
                new CatalogCard("A3", "Zulu"));

        assertThat(result.total()).isEqualTo(3);
    }

    @Test
    default void returnsSecondPageAndTotal() {
        SearchPage result =
                harness().searchActive("north", 1, 2);

        assertThat(result.items()).containsExactly(
                new CatalogCard("A3", "Zulu"));

        assertThat(result.total()).isEqualTo(3);
        assertThat(result.number()).isEqualTo(1);
        assertThat(result.size()).isEqualTo(2);
    }

    @Test
    default void unknownTenantHasNoMatches() {
        SearchPage result =
                harness().searchActive("missing", 0, 2);

        assertThat(result.items()).isEmpty();
        assertThat(result.total()).isZero();
    }

    @Test
    default void pageBeyondEndKeepsMatchingTotal() {
        SearchPage result =
                harness().searchActive("north", 4, 2);

        assertThat(result.items()).isEmpty();
        assertThat(result.total()).isEqualTo(3);
        assertThat(result.number()).isEqualTo(4);
    }
}
~~~

Bộ ca không có nhánh `if (mongo)` để nới kỳ vọng. Các yêu cầu đọc chung được kiểm tra như nhau.

Các ca này bảo vệ luồng đọc đã mô tả. Chúng chưa kiểm tra hợp đồng cập nhật, auditing, projection tối ưu hay cạnh tranh; những yêu cầu đó cần ca bổ sung.

Nếu chạy cùng interface trên một fake lưu bằng Map, kết quả chỉ cho biết fake phù hợp bộ ca. Để đánh giá hồi quy persistence, mỗi cấu hình mục tiêu phải sử dụng repository, mapping và backend thật.

## 6. Adapter JPA cho cùng bộ ca

Ví dụ dùng một entity riêng cho JPA. Key được fixture cung cấp trực tiếp; không so sánh sequence hoặc ID tự sinh giữa các store.

### 6.1. Entity và repository

~~~java
package example.regression.jpa;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import example.regression.contract.ProductSeed;

@Entity
@Table(name = "catalog_regression_product")
public class JpaProduct {

    @Id
    @Column(name = "product_key")
    private String key;

    @Column(name = "tenant_key", nullable = false)
    private String tenant;

    @Column(name = "product_label", nullable = false)
    private String label;

    private boolean active;

    protected JpaProduct() {
    }

    public JpaProduct(ProductSeed source) {
        this.key = source.key();
        this.tenant = source.tenant();
        this.label = source.label();
        this.active = source.active();
    }

    public String getKey() {
        return key;
    }

    public String getLabel() {
        return label;
    }
}
~~~

~~~java
package example.regression.jpa;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface JpaProductRepository
        extends JpaRepository<JpaProduct, String> {

    Page<JpaProduct> findByTenantAndActiveTrue(
            String tenant,
            Pageable pageable);
}
~~~

JPA dùng field access theo vị trí annotation ID, nên ví dụ không cần getter cho mọi field để query derivation đọc metadata.

### 6.2. Lớp chạy hợp đồng

~~~java
package example.regression.jpa;

import java.util.List;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

import example.regression.contract.CatalogCard;
import example.regression.contract.CatalogHarness;
import example.regression.contract.CatalogRegressionContract;
import example.regression.contract.ProductSeed;
import example.regression.contract.SearchPage;

@DataJpaTest(
        properties = "spring.jpa.hibernate.ddl-auto=create-drop")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class JpaCatalogRegressionTest
        implements CatalogRegressionContract {

    @Autowired
    private JpaProductRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Override
    public CatalogHarness harness() {
        return new CatalogHarness() {

            @Override
            public void reset() {
                repository.deleteAllInBatch();
                entityManager.clear();
            }

            @Override
            public void seed(List<ProductSeed> products) {
                products.forEach(source ->
                        entityManager.persist(
                                new JpaProduct(source)));

                entityManager.flush();
                entityManager.clear();
            }

            @Override
            public SearchPage searchActive(
                    String tenant,
                    int page,
                    int size) {

                Sort sort = Sort.by("label").ascending()
                        .and(Sort.by("key").ascending());

                var result =
                        repository.findByTenantAndActiveTrue(
                                tenant,
                                PageRequest.of(page, size, sort));

                return SearchPage.from(
                        result,
                        row -> new CatalogCard(
                                row.getKey(),
                                row.getLabel()));
            }
        };
    }
}
~~~

Lớp test cần một DataSource test đã được cấu hình. `Replace.NONE` giữ backend đó, giúp job PostgreSQL không vô tình chuyển sang database nhúng.

`@DataJpaTest` có transaction test theo mặc định. Xem [API DataJpaTest](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html). Ví dụ dùng flush/clear để query không chỉ quan sát entity còn trong persistence context.

Schema tự sinh ở đây phục vụ ví dụ đọc tối thiểu. Khi mục tiêu là tương thích schema/migration thật, job phải dùng đúng migration và cấu hình schema tương ứng.

## 7. Chạy lại nguyên hợp đồng trên MongoDB

MongoDB dùng một domain riêng, tránh trộn annotation persistence của hai store vào cùng kiểu.

### 7.1. Document và repository

~~~java
package example.regression.mongo;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

import example.regression.contract.ProductSeed;

@Document("catalog_regression_product")
public record MongoProduct(
        @Id String key,
        String tenant,
        String label,
        boolean active) {

    public static MongoProduct from(ProductSeed source) {
        return new MongoProduct(
                source.key(),
                source.tenant(),
                source.label(),
                source.active());
    }
}
~~~

~~~java
package example.regression.mongo;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface MongoProductRepository
        extends MongoRepository<MongoProduct, String> {

    Page<MongoProduct> findByTenantAndActiveTrue(
            String tenant,
            Pageable pageable);
}
~~~

Các key A1, A2 trong fixture là chuỗi do test kiểm soát. Không cần dựa vào định dạng ObjectId hoặc ID tự sinh để so sánh hành vi danh mục.

### 7.2. Lớp chạy hợp đồng

~~~java
package example.regression.mongo;

import java.util.List;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

import example.regression.contract.CatalogCard;
import example.regression.contract.CatalogHarness;
import example.regression.contract.CatalogRegressionContract;
import example.regression.contract.ProductSeed;
import example.regression.contract.SearchPage;

@DataMongoTest
class MongoCatalogRegressionTest
        implements CatalogRegressionContract {

    @Autowired
    private MongoProductRepository repository;

    @Override
    public CatalogHarness harness() {
        return new CatalogHarness() {

            @Override
            public void reset() {
                repository.deleteAll();
            }

            @Override
            public void seed(List<ProductSeed> products) {
                repository.saveAll(
                        products.stream()
                                .map(MongoProduct::from)
                                .toList());
            }

            @Override
            public SearchPage searchActive(
                    String tenant,
                    int page,
                    int size) {

                Sort sort = Sort.by("label").ascending()
                        .and(Sort.by("key").ascending());

                var result =
                        repository.findByTenantAndActiveTrue(
                                tenant,
                                PageRequest.of(page, size, sort));

                return SearchPage.from(
                        result,
                        row -> new CatalogCard(
                                row.key(),
                                row.label()));
            }
        };
    }
}
~~~

`@DataMongoTest` tập trung vào thành phần MongoDB; xem [API DataMongoTest](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/data/mongo/DataMongoTest.html). Lớp test cần kết nối MongoDB test đã được cấu hình.

Cùng bốn default test method được chạy, với cùng expected result. Phần khác nhau là cách tạo fixture, query thật và chuyển kết quả thành view.

Reset xóa dữ liệu trong collection dành riêng cho kịch bản. Không dựa vào rollback của JPA để suy ra MongoDB cũng được dọn theo cùng cách. Khi dùng chung backend, cần namespace/database riêng hoặc cơ chế cô lập tương đương cho từng job.

### 7.3. Giữ metadata gắn với đúng module

Nếu cả JPA và MongoDB có mặt trong ứng dụng, hãy dùng repository base interface cùng annotation domain phù hợp, đồng thời kiểm soát package scanning.

Không biến một domain thành cả entity JPA lẫn document chỉ để tái sử dụng code test. Quy tắc phân biệt repository khi có nhiều module được mô tả trong [Defining Repository Interfaces](https://docs.spring.io/spring-data/commons/reference/3.5/repositories/definition.html).

Bộ ca dùng chung tái sử dụng hành vi và fixture logic; các mapping vật lý vẫn có thể độc lập.

## 8. Tạo ma trận phiên bản có thể tái hiện

Một ma trận minh họa:

| Target | Bộ dependency | Store | Backend | Mục tiêu thay đổi |
| --- | --- | --- | --- | --- |
| JPA-A | Nền đã chốt | JPA | PostgreSQL P0 | Mốc so sánh |
| JPA-B | Ứng viên đã chốt | JPA | PostgreSQL P0 | Dependency |
| MONGO-A | Nền đã chốt | MongoDB | MongoDB M0 | Mốc so sánh |
| MONGO-B | Ứng viên đã chốt | MongoDB | MongoDB M0 | Dependency |
| JPA-C | Ứng viên đã chốt | JPA | PostgreSQL P1 | Phiên bản backend |
| MONGO-C | Ứng viên đã chốt | MongoDB | MongoDB M1 | Phiên bản backend |

P0/P1 và M0/M1 là ký hiệu kế hoạch. Khi triển khai job, phải thay bằng phiên bản, image tag/digest và cấu hình đã chọn; không để chúng thành giá trị mơ hồ trong báo cáo thực tế.

Bốn target đầu giúp đánh giá dependency trên cùng backend của từng store. Hai target sau đánh giá thay đổi backend khi bộ dependency đã được giữ cố định.

Nếu đổi đồng thời JDK, framework, driver và backend trong một lượt, một lỗi mới khó được quy về nguyên nhân. Khi cần thay cả nhóm để có cấu hình tương thích, ghi rõ nhóm thay đổi và thêm lượt đối chứng hợp lệ khi có thể.

Không tạo mọi tích Descartes giữa các phiên bản. Chỉ đưa vào ma trận những tổ hợp có ý nghĩa và tương thích mà dự án cam kết hỗ trợ.

### 8.1. Mỗi tổ hợp cần môi trường riêng

Mỗi job nên có:

- Bộ dependency, JDK và cấu hình runtime xác định.
- Backend test riêng hoặc vùng dữ liệu được cô lập.
- Cùng revision của hợp đồng và fixture.
- Cùng nhóm ca bắt buộc được lựa chọn.
- Thông tin kết nối trỏ đúng backend mục tiêu.

Không thay dependency đang chạy trong cùng một application context để mô phỏng hai phiên bản. Chạy bằng classpath/process hoặc môi trường build tách biệt cho từng tổ hợp.

Testcontainers có thể cung cấp backend thật và quản lý vòng đời môi trường test; Boot hỗ trợ service connection và container được quản lý như bean. Xem [Testcontainers của Spring Boot](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html).

Chạy cùng container image chưa có nghĩa mọi cấu hình backend giống nhau. Timezone, collation, extension, index và chế độ replica/cluster cũng có thể ảnh hưởng hành vi.

### 8.2. Phân biệt mã hợp đồng và mã tích hợp framework

Bốn ca trong interface là phần hành vi cần giữ ổn định. Các annotation test slice, package import hoặc cấu hình connection có thể cần thay theo phiên bản nền tảng.

Nếu một bản nâng cấp đổi API cấu hình test, có thể điều chỉnh lớp kết nối môi trường để build được trên target mới. Không tiện tay đổi assertion nghiệp vụ trong lúc sửa phần cấu hình đó.

Lỗi biên dịch ở lớp test tích hợp là một kết quả cần xử lý, không phải bằng chứng bốn ca đã chạy và thành công.

## 9. Phân loại khả năng bắt buộc và phần mở rộng

Bộ ca dùng chung không nên được giới hạn đến mức chỉ còn những thao tác không có giá trị. Nó phải bảo vệ những yêu cầu mà ứng dụng thật sự cam kết trên tất cả target được công bố.

| Nhóm | Ví dụ | Cách tổ chức |
| --- | --- | --- |
| Hợp đồng bắt buộc chung | Tenant, active, thứ tự, trang và tổng | Cùng ca, cùng kỳ vọng trên mọi target |
| Hợp đồng bổ sung của ứng dụng | Projection, auditing, cập nhật có version | Thêm ca chung khi mọi target được yêu cầu đáp ứng |
| Khả năng đặc thù module | JPA lock mode hoặc truy vấn đặc thù store | Bộ test riêng cho target có tuyên bố hỗ trợ |
| Mục tiêu chưa đáp ứng | Store ứng viên không thực hiện được yêu cầu bắt buộc | Báo chưa đạt mục tiêu |
| Lỗi môi trường | Backend không khởi động hoặc thiếu kết nối | Báo không có kết quả hành vi |

JPA có metadata lock trên repository method; xem [Locking của Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/3.5/jpa/locking.html). Không chuyển nguyên annotation hoặc kỳ vọng đó sang MongoDB chỉ vì cả hai có repository.

Ngay cả optimistic locking cũng cần đối chiếu thao tác cùng cấu hình thực tế. Tài liệu MongoDB nêu yêu cầu write acknowledgement cho việc phát hiện lỗi version; xem [Optimistic Locking của Spring Data MongoDB](https://docs.spring.io/spring-data/mongodb/reference/4.5/mongodb/template-crud-operations.html#mongo-template.optimistic-locking).

Nếu ứng dụng yêu cầu “cập nhật từ bản cũ phải bị từ chối”, hãy dùng cùng kịch bản nghiệp vụ nhưng thiết lập version và điều kiện thực thi phù hợp cho từng adapter. Không nhất thiết assert tên exception vật lý giống nhau trừ khi đó là hợp đồng công khai.

Không dùng một flag do test tự suy từ kết quả lỗi để quyết định bỏ qua ca bắt buộc. Khả năng được hỗ trợ phải được khai báo và đánh giá trước theo mục tiêu của target.

## 10. Chọn phép so sánh không che mất hồi quy

### 10.1. Chuẩn hóa hình dạng, giữ nguyên ý nghĩa

Chuyển entity/document thành `CatalogCard` là chuẩn hóa hình dạng. Những hành động sau có thể che mất lỗi nếu không thuộc hợp đồng:

- Sort lại kết quả trong Java trước khi assert thứ tự backend.
- Lọc tenant lần nữa sau khi query đã trả dữ liệu.
- Tính lại total từ fixture thay vì quan sát metadata của query.
- Đổi mọi chuỗi về chữ thường để bỏ qua khác biệt collation.
- Bỏ phần thời gian hoặc làm tròn tiền mà yêu cầu chưa cho phép.

Nếu ứng dụng chủ ý chuẩn hóa chuỗi hoặc độ chính xác trước khi lưu, hãy test chính quy tắc đó và kỳ vọng được công bố. Không thêm bước chuẩn hóa chỉ ở comparator của bộ hồi quy.

### 10.2. So với yêu cầu trước, đối chiếu nền sau

Khi JPA-A trả A1, A2, A3 còn JPA-B trả A2, A1, A3, ca sắp xếp phải chỉ ra khác biệt tại khóa phụ.

Khi cả hai cùng trả thêm B1, cả hai đều vi phạm điều kiện tenant. So sánh hai kết quả bằng nhau không phát hiện được lỗi này; assertion về hợp đồng mới phát hiện được.

Một snapshot có thể hỗ trợ xem khác biệt, nhưng cần kiểm soát field không ổn định. Không tự cập nhật snapshot để chấp nhận kết quả mới khi chưa đánh giá ý nghĩa thay đổi.

### 10.3. Không trộn số liệu hiệu năng vào assertion chức năng

Một target có thể tạo nhiều hơn một query cho `Page`; target khác có cơ chế tính total khác. Nếu yêu cầu chỉ nói về nội dung và metadata, không bắt số statement phải bằng nhau.

Nếu có yêu cầu riêng như “không tải body” hoặc “không có truy vấn tăng theo số dòng”, thêm phép đo phù hợp của từng store. Giữ kỳ vọng theo ràng buộc sử dụng dữ liệu, thay vì đòi SQL và command MongoDB giống nhau.

Đánh giá độ trễ cần môi trường, tải và phương pháp riêng. Một timeout khởi động container không tự chứng minh query của phiên bản mới chậm hơn.

## 11. Đọc kết quả mà không nhầm skip với thành công

Mỗi target cần báo cả tình trạng môi trường và số ca thực sự được chạy.

Mẫu nội dung báo cáo cho một job:

~~~text
TARGET=<tên tổ hợp>
SOURCE_REVISION=<revision của ứng dụng>
CONTRACT_REVISION=<revision của bộ ca>
JDK=<phiên bản thực>
DEPENDENCIES=<bộ phiên bản đã resolve>
STORE=<module thực>
BACKEND=<phiên bản và cấu hình nhận diện>
EXPECTED_SHARED_CASES=4
DISCOVERED_SHARED_CASES=<số runner tìm thấy>
PASSED=<số thành công>
FAILED=<số thất bại>
SKIPPED_OR_ABORTED=<số không chạy đến kết luận>
SETUP_STATUS=<trạng thái môi trường>
~~~

Đây là mẫu để thiết kế báo cáo, không phải kết quả đã thực thi của các ví dụ trong bài.

| Trạng thái tổng hợp | Ý nghĩa |
| --- | --- |
| PASS | Môi trường đúng target, đủ ca bắt buộc được tìm thấy và thành công |
| FAIL | Có hành vi vi phạm hợp đồng hoặc bước kiểm tra bắt buộc thất bại |
| BLOCKED | Chưa đánh giá được hành vi vì môi trường không sẵn sàng |
| UNSUPPORTED | Một khả năng nằm ngoài phạm vi hỗ trợ đã được xác định |
| NOT_RUN | Ca hoặc target chưa được thực thi |

`UNSUPPORTED` không được dùng để biến một yêu cầu bắt buộc bị thiếu thành PASS. Target còn thiếu yêu cầu bắt buộc vẫn chưa đáp ứng mục tiêu của ứng dụng.

Với sáu target và bốn ca chung trong ví dụ, kế hoạch có 24 lần thực thi ca chung. Nếu runner chỉ phát hiện một phần, cần điều tra filter, test discovery hoặc cấu hình job dù số ca đã chạy đều xanh.

Cũng cần nhận diện trường hợp dependency thực tế không đổi: hai job mang tên khác nhau nhưng resolve cùng một bộ phiên bản chưa phải phép so sánh mong muốn.

## 12. Xử lý sai khác có hệ thống

Khi một ca thất bại, lưu đủ thông tin để tái hiện đúng tổ hợp, sau đó phân loại:

1. **Môi trường:** sai backend, thiếu schema/index, kết nối hoặc container không sẵn sàng.
2. **Tích hợp framework:** repository gắn nhầm module, package scanning, converter hoặc cấu hình test.
3. **Khác biệt dữ liệu:** null/missing, collation, kiểu số, timezone hoặc độ chính xác.
4. **Hồi quy hành vi:** điều kiện query, thứ tự, metadata trang, mapping hoặc cách ghi đã thay đổi.
5. **Thay đổi hợp đồng có chủ đích:** yêu cầu mới cần được mô tả và cập nhật cùng bộ ca phù hợp.

Giảm fixture để tìm nguyên nhân nhưng giữ bản ca đã phát hiện lỗi trong bộ hồi quy. Khi sửa xong, chạy lại cả cấu hình nền và ứng viên có liên quan để xác nhận không làm mất hành vi đã được yêu cầu.

Không bắt exception rồi trả danh sách rỗng để test tiếp tục xanh. Không đổi `containsExactly` thành kiểm tra không rỗng khi thứ tự và tập kết quả vẫn là yêu cầu.

Với ca giao dịch, cần đặc biệt kiểm tra transaction bao quanh test. Test-managed transaction có thể làm môi trường khác đường gọi thật của ứng dụng; xem [Transaction Management của Spring TestContext](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html).

Bộ ca dùng chung giúp việc nâng phiên bản hoặc thay store có một chuẩn đánh giá nhất quán. Giá trị của nó nằm ở hợp đồng rõ ràng, adapter thực sự chạy backend và bằng chứng đầy đủ cho từng target, thay vì chỉ một nhãn xanh chung cho cả ma trận.
