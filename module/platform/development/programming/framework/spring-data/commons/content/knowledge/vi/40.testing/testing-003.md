# Chọn test slice và Testcontainers phù hợp với store mẫu

## 1. Hai lựa chọn giải quyết hai câu hỏi khác nhau

Trong chương **Kiểm thử** của module **SPRING_DATA_COMMONS**, một bài test repository cần làm rõ hai điều:

1. Spring context phải nạp những thành phần nào để kiểm tra hành vi đang quan tâm?
2. Hành vi đó phải chạy trên loại backend nào để kết quả có giá trị?

**Test slice** giới hạn phần ứng dụng được khởi tạo, chẳng hạn entity, mapping và repository JPA. **Testcontainers** cung cấp backend chạy trong container, chẳng hạn PostgreSQL hoặc MongoDB, với vòng đời phù hợp cho kiểm thử.

Hai lựa chọn này có thể kết hợp:

| Phạm vi Spring | Backend | Ví dụ mục tiêu |
| --- | --- | --- |
| Slice dữ liệu | Database nhúng | Kiểm tra nhanh một phần mapping/query không phụ thuộc dialect đích |
| Slice dữ liệu | Database trong container | Kiểm tra repository với engine và các đặc điểm dữ liệu cần dùng |
| Toàn ứng dụng | Database trong container | Kiểm tra service, transaction manager, converter và wiring tổng thể |
| Không nạp Spring | Không cần backend | Kiểm tra thuật toán thuần hoặc logic quyết định trong service với test double |

Một test dùng Testcontainers vẫn có thể chỉ nạp slice. Một test dùng `@SpringBootTest` vẫn có thể trỏ nhầm backend. Vì vậy, không dùng tên annotation hoặc việc Docker đang chạy làm bằng chứng duy nhất cho phạm vi kiểm thử.

Spring Data Commons cung cấp các abstraction như Repository, Pageable, Sort, projection và Query by Example. Việc thực thi các abstraction đó thuộc từng module store. Không có một test slice chung mang tên `@DataCommonsTest` để bảo đảm mọi loại repository hoạt động như nhau.

## 2. Chọn bằng chứng trước khi chọn annotation

Hãy bắt đầu từ một câu có thể kiểm chứng:

- “Repository khởi tạo được với tên derived query này.”
- “Sau khi ghi và đọc lại, chuỗi tiếng Việt cùng các field bắt buộc được giữ đúng.”
- “Truy vấn active trả đúng hai phần tử ở trang đầu và đúng tổng số bản ghi.”
- “Projection cung cấp đúng SKU và label.”
- “Ràng buộc unique của schema thật từ chối SKU trùng.”
- “Hai thao tác repository cùng rollback khi service thất bại.”
- “Custom converter và auditing configuration thực tế được sử dụng.”

Các câu này cần mức kiểm thử khác nhau.

| Bằng chứng cần có | Lựa chọn xuất phát |
| --- | --- |
| Service chọn đúng nhánh khi repository trả dữ liệu | Unit test với test double phù hợp |
| Mapping, query derivation, sort, page, projection của một store | Slice của module store và backend phù hợp |
| SQL, index, converter hoặc constraint phụ thuộc engine | Slice trên engine tương ứng qua container |
| Nhiều repository, nhiều bean cấu hình và ranh giới service | Test tích hợp nạp đủ cấu hình liên quan |
| Migration nâng cấp schema cũ | Backend tương ứng, migration thật và fixture của phiên bản cũ |

Một mock trả sẵn `PageImpl` không chứng minh store đã sinh count query đúng. Một mock trả projection đã dựng sẵn không chứng minh mapping từ kết quả truy vấn hoạt động. Ngược lại, không cần khởi động database chỉ để kiểm tra phép tính thuần không liên quan persistence.

~~~mermaid
flowchart TD
    A["Muốn kiểm chứng điều gì?"] --> B{"Có cần thực thi repository hoặc mapping thật?"}
    B -- "Không" --> C["Unit test, không cần store"]
    B -- "Có" --> D{"Có cần service hoặc wiring ngoài tầng dữ liệu?"}
    D -- "Không" --> E["Chọn slice đúng module store"]
    D -- "Có" --> F["Nạp cấu hình tích hợp cần thiết"]
    E --> G{"Hành vi phụ thuộc engine hoặc schema đích?"}
    F --> G
    G -- "Có" --> H["Backend tương ứng qua Testcontainers"]
    G -- "Chưa cần" --> I["Có thể dùng backend thay thế với phạm vi kết luận rõ"]
    H --> J["Kiểm tra kết nối, fixture, isolation và assertion"]
    I --> J
~~~

## 3. Chọn slice theo module đang thực thi

Bảng sau dùng tên annotation của **Spring Boot 3.5**:

| Đường truy cập dữ liệu | Slice điển hình | Điểm cần phân biệt |
| --- | --- | --- |
| JPA entity và repository | `@DataJpaTest` | Nạp tầng JPA, có hỗ trợ TestEntityManager |
| Spring Data JDBC aggregate/repository | `@DataJdbcTest` | Kiểm tra repository JDBC và mapping tương ứng |
| SQL trực tiếp bằng Spring JDBC | `@JdbcTest` | Không thay cho slice Spring Data JDBC repository |
| Repository/template R2DBC | `@DataR2dbcTest` | Nạp hạ tầng R2DBC, không phải JDBC |
| Document/repository MongoDB | `@DataMongoTest` | Nạp hạ tầng MongoDB |

Các store khác có slice và auto-configuration tương ứng tùy phiên bản Spring Boot. Đối chiếu danh sách được hỗ trợ thay vì suy từ tên một interface Commons. [Danh sách test slices của Spring Boot 3.5](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html).

`@DataJpaTest` tập trung vào thành phần JPA, có transaction test và rollback mặc định. Nó không nạp toàn bộ service/controller của ứng dụng. [DataJpaTest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html).

`@DataJdbcTest` cũng có transaction test và rollback mặc định cho phạm vi JDBC, nhưng không biến entity JPA thành aggregate JDBC. [DataJdbcTest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/data/jdbc/DataJdbcTest.html).

Không gắn đồng thời `@DataJpaTest` và `@SpringBootTest` lên cùng một class để “có đủ mọi thứ”. Chọn một cơ chế bootstrap chính; nếu slice thiếu một cấu hình cụ thể, cân nhắc import có chủ đích hoặc chuyển sang test tích hợp phù hợp.

## 4. Chọn container theo store và hành vi cần kiểm tra

Tên store chưa mô tả hết môi trường cần có:

| Mẫu ứng dụng | Backend test phù hợp với mục tiêu | Chi tiết cần cố định |
| --- | --- | --- |
| JPA hoặc JDBC dùng PostgreSQL | PostgreSQL container | Version, extension, collation và schema cần dùng |
| JPA hoặc JDBC dùng MySQL | MySQL container | SQL mode, charset và quy tắc so sánh cần dùng |
| MongoDB cần multi-document transaction | MongoDB với topology hỗ trợ transaction | Replica set và transaction configuration |
| R2DBC dùng PostgreSQL | PostgreSQL container cùng driver R2DBC | ConnectionFactory và URL/protocol đúng |
| Repository search dùng index/analyzer riêng | Engine search tương ứng | Mapping, analyzer và thời điểm dữ liệu có thể tìm thấy |

Ví dụ, H2 có thể phục vụ một số kiểm thử nhanh nhưng không chứng minh câu SQL có extension riêng của PostgreSQL chạy được trên PostgreSQL. Chế độ tương thích không thay thế toàn bộ hành vi engine đích.

Ngay cả cùng engine, một container đơn lẻ cũng chưa tái hiện mọi đặc tính production như replication, failover hoặc tải đồng thời. Phạm vi kết luận nên gắn với cấu hình đã kiểm chứng.

Image cần được chọn theo môi trường mục tiêu. Các tag trong bài là minh họa; khi cần tái lập nghiêm ngặt, hãy cố định patch version hoặc digest được dự án chấp nhận. Tránh dùng `latest` rồi mặc định các lần chạy có cùng backend.

## 5. Ví dụ chính: JPA slice trên PostgreSQL

Phần code sau minh họa **Spring Boot 3.5, Java 17+, JUnit Jupiter, Jakarta Persistence và API Testcontainers 1.x** với dependency management tương thích. Đây là phạm vi của ví dụ, không phải khẳng định phiên bản đang dùng trong một repository cụ thể.

Nếu dùng Spring Boot hoặc Testcontainers major khác, cần đối chiếu package, artifact và API của major đó. Không trộn ngẫu nhiên import và dependency từ nhiều major.

Các dependency cần có theo vai trò:

| Dependency | Vai trò |
| --- | --- |
| Spring Boot starter Data JPA | Repository JPA, ORM và integration |
| Spring Boot starter Test | JUnit Jupiter, Spring Test và assertion |
| `spring-boot-testcontainers` | Service connection và tích hợp container với Spring Boot |
| `org.testcontainers:postgresql` của dòng 1.x | PostgreSQLContainer dùng trong ví dụ |
| PostgreSQL JDBC driver | Kết nối JDBC từ ứng dụng test tới PostgreSQL |

Ví dụ chính để Spring Boot quản lý container như bean nên không cần JUnit extension chỉ để điều khiển vòng đời container. Nếu chọn phương án `@Testcontainers` ở phần sau, cần thêm module JUnit Jupiter của Testcontainers tương ứng.

Database server trong container không tự cung cấp JDBC driver cho JVM ứng dụng. [PostgreSQL module của Testcontainers](https://java.testcontainers.org/modules/databases/postgres/).

Các public type minh họa được hiểu là đặt trong các file Java riêng khi áp dụng. Ứng dụng test cần tìm được cấu hình Spring Boot gốc và quét đúng package entity/repository.

## 6. Entity, repository và projection mẫu

### 6.1. Entity CatalogItem

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "catalog_item")
public class CatalogItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 40)
    private String sku;

    @Column(nullable = false, length = 160)
    private String label;

    @Column(nullable = false)
    private boolean active;

    protected CatalogItem() {
    }

    public CatalogItem(String sku, String label, boolean active) {
        this.sku = sku;
        this.label = label;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getLabel() {
        return label;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

### 6.2. Projection và query method

~~~java
public interface CatalogLabel {
    String getSku();
    String getLabel();
}
~~~

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CatalogItemRepository
        extends JpaRepository<CatalogItem, Long> {

    Optional<CatalogItem> findBySku(String sku);

    Page<CatalogItem> findByActiveTrue(Pageable pageable);

    List<CatalogLabel> findByActiveTrueAndLabelStartingWithIgnoreCase(
        String prefix, Sort sort
    );
}
~~~

Các abstraction `Pageable`, `Sort` và projection là phần kiến thức dùng chung, nhưng các method này đang được kiểm tra bằng implementation JPA cụ thể.

Dữ liệu kiểm thử phải làm lộ việc lọc, thứ tự và số trang. Nếu chỉ có một bản ghi, một query sai predicate hoặc một sort không hoạt động vẫn có thể tạo kết quả trông hợp lệ.

## 7. Cấu hình container do Spring Boot quản lý

~~~java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class PostgresSliceConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("catalog_test")
            .withUsername("catalog_test")
            .withPassword("catalog_test");
    }
}
~~~

`@ServiceConnection` cung cấp connection details từ container được hỗ trợ cho auto-configuration phù hợp. Nó không tự viết schema hoặc tự sinh fixture nghiệp vụ. [ServiceConnection API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/testcontainers/service/connection/ServiceConnection.html).

Trong phương án bean, Spring Boot quản lý vòng đời container cùng application context. Không cần thêm `@Container`, tự gọi `start()` hay `stop()` cho cùng bean đó. Khi context được cache, vòng đời backend cần phù hợp thời gian context còn được sử dụng. [Tích hợp Testcontainers của Spring Boot](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html).

Dùng kiểu trả về `PostgreSQLContainer<?>` giúp thể hiện loại backend. Với generic container hoặc image tùy biến, cần kiểm tra cơ chế nhận diện service connection thay vì giả định framework luôn suy ra đúng loại dịch vụ.

## 8. Test slice đầy đủ với assertion có ý nghĩa

Ví dụ dưới đây dùng schema do Hibernate tạo cho **fixture học tập cô lập**:

- `create-drop` để dựng schema từ entity mẫu.
- Tắt cơ chế SQL init và migration auto-configuration để không trộn nhiều nguồn tạo schema trong ví dụ.
- Giữ đúng DataSource container bằng `Replace.NONE`.

Đây là bài test mapping/query trên schema fixture, chưa phải bài test migration production.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.sql.Connection;
import java.util.List;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

@DataJpaTest(properties = {
    "spring.jpa.hibernate.ddl-auto=create-drop",
    "spring.sql.init.mode=never",
    "spring.flyway.enabled=false",
    "spring.liquibase.enabled=false"
})
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
@Import(PostgresSliceConfiguration.class)
class CatalogItemRepositoryTest {

    @Autowired
    CatalogItemRepository repository;

    @Autowired
    TestEntityManager entityManager;

    @Autowired
    DataSource dataSource;

    @Test
    void usesPostgreSqlBackend() throws Exception {
        try (Connection connection = dataSource.getConnection()) {
            assertThat(
                connection.getMetaData().getDatabaseProductName()
            ).isEqualTo("PostgreSQL");
        }
    }

    @Test
    void writesAndReadsMappedValues() {
        CatalogItem saved = repository.saveAndFlush(
            new CatalogItem("MAP-001", "Sổ tay học Java", true)
        );

        Long id = saved.getId();
        assertThat(id).isNotNull();

        entityManager.clear();

        CatalogItem loaded = repository.findBySku("MAP-001")
            .orElseThrow();

        assertThat(loaded.getId()).isEqualTo(id);
        assertThat(loaded.getLabel()).isEqualTo("Sổ tay học Java");
        assertThat(loaded.isActive()).isTrue();
    }

    @Test
    void filtersSortsAndPagesActiveItems() {
        seedCatalog();

        Page<CatalogItem> first = repository.findByActiveTrue(
            PageRequest.of(0, 2, Sort.by("sku").ascending())
        );
        Page<CatalogItem> second = repository.findByActiveTrue(
            PageRequest.of(1, 2, Sort.by("sku").ascending())
        );

        assertThat(first.getContent())
            .extracting(CatalogItem::getSku)
            .containsExactly("A100", "B100");
        assertThat(first.getTotalElements()).isEqualTo(3);
        assertThat(first.hasNext()).isTrue();

        assertThat(second.getContent())
            .extracting(CatalogItem::getSku)
            .containsExactly("C100");
        assertThat(second.getTotalElements()).isEqualTo(3);
        assertThat(second.hasNext()).isFalse();
    }

    @Test
    void mapsClosedProjectionWithDerivedPredicate() {
        seedCatalog();

        List<CatalogLabel> labels =
            repository.findByActiveTrueAndLabelStartingWithIgnoreCase(
                "jAvA", Sort.by("sku").ascending()
            );

        assertThat(labels)
            .extracting(CatalogLabel::getSku)
            .containsExactly("A100", "B100");
        assertThat(labels)
            .extracting(CatalogLabel::getLabel)
            .containsExactly("Java nâng cao", "Java cơ bản");
    }

    @Test
    void databaseRejectsDuplicateSku() {
        repository.saveAndFlush(
            new CatalogItem("DUP-001", "Bản đầu", true)
        );

        assertThatThrownBy(() -> repository.saveAndFlush(
            new CatalogItem("DUP-001", "Bản trùng", false)
        )).isInstanceOf(DataIntegrityViolationException.class);
    }

    private void seedCatalog() {
        repository.saveAll(List.of(
            new CatalogItem("B100", "Java cơ bản", true),
            new CatalogItem("D100", "Java lưu trữ", false),
            new CatalogItem("C100", "Kotlin thực hành", true),
            new CatalogItem("A100", "Java nâng cao", true)
        ));
        repository.flush();
        entityManager.clear();
    }
}
~~~

`Replace.NONE` yêu cầu không thay DataSource ứng dụng bằng một database test khác. Các chính sách mặc định nhận diện database test có khác biệt giữa các phiên bản; khai báo tường minh ở đây làm rõ ý định dùng container. [AutoConfigureTestDatabase.Replace API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.Replace.html).

### 8.1. Vì sao các assertion này có giá trị?

- Kiểm tra metadata giúp phát hiện cấu hình đang chạy H2 dù container PostgreSQL đã khởi động.
- `flush` đẩy thay đổi tới database thay vì chỉ để lỗi ghi dữ liệu xuất hiện sau assertion.
- `clear` loại bỏ các entity đang được giữ trong persistence context cấp một trước khi đọc lại.
- Fixture được insert theo thứ tự khác sort để tránh phụ thuộc tình cờ vào thứ tự ghi.
- Có bản ghi inactive nên predicate thiếu `active = true` sẽ làm sai kết quả.
- Có hơn một trang nên nội dung trang và tổng số bản ghi đều được quan sát.
- Projection kiểm tra cả thứ tự SKU lẫn field label.
- Test unique buộc database thực thi thao tác ghi gây xung đột.

Sau exception constraint, test unique không tiếp tục chạy query trong cùng transaction đã lỗi; nó kết thúc để framework rollback. Test slice này cũng chưa chứng minh service có ranh giới transaction đúng hoặc mọi tùy chọn collation Unicode của production đều đã được kiểm tra.

Các đoạn code là tài liệu minh họa cho thiết kế test, không phải báo cáo đã thực thi thành công trong một dự án cụ thể.

## 9. Khi cần DynamicPropertySource thay service connection

Một cách kết nối khác là đăng ký property động từ container. Phương án này hữu ích khi dự án cần tự kiểm soát các property hoặc chưa dùng service connection.

Đoạn sau minh họa **phần khai báo của một test class thay thế**, không ghép thêm vào class dùng `PostgresSliceConfiguration` ở trên:

~~~java
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@DataJpaTest(properties = {
    "spring.jpa.hibernate.ddl-auto=create-drop",
    "spring.sql.init.mode=never",
    "spring.flyway.enabled=false",
    "spring.liquibase.enabled=false"
})
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class CatalogItemDynamicConnectionTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("catalog_test")
            .withUsername("catalog_test")
            .withPassword("catalog_test");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    // Thêm các method kiểm thử repository theo mục tiêu ở phần trước.
}
~~~

`@DynamicPropertySource` dùng method static nhận `DynamicPropertyRegistry`; giá trị được cung cấp qua supplier khi property được giải quyết. [Dynamic property sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html).

Trong phương án JUnit extension, static `@Container` được dùng chung giữa các method của class; instance field có vòng đời khác. Module extension không mặc định bảo đảm chạy song song an toàn. [JUnit Jupiter integration của Testcontainers](https://java.testcontainers.org/test_framework_integration/junit_5/).

Không điều khiển cùng một container bằng cả Spring bean lifecycle và JUnit extension. Hãy chọn rõ bên sở hữu start/stop.

Nếu nhiều class dùng lại Spring context, context có thể được cache theo cấu hình test. Một container đã dừng trong khi context vẫn giữ DataSource cũ sẽ gây lỗi kết nối ở class tiếp theo. Cần phối hợp vòng đời backend và context; không thêm `@DirtiesContext` vào mọi test theo thói quen. [Context caching của Spring TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html).

## 10. Chọn cách tạo schema theo điều cần chứng minh

Một container database mới chỉ là nơi chạy engine. Nó không tự biết ứng dụng cần những bảng, index, extension hoặc dữ liệu nền nào.

| Mục tiêu | Cách tạo cấu trúc phù hợp | Phạm vi kết luận |
| --- | --- | --- |
| Học mapping JPA đơn giản | Hibernate tạo schema fixture | Mapping/query chạy với schema sinh từ entity |
| Kiểm tra repository trên schema ứng dụng | Chạy migration của ứng dụng | Query và mapping phù hợp schema được quản lý |
| Kiểm tra nâng cấp schema | Bắt đầu từ schema/data cũ rồi chạy migration mới | Đường chuyển đổi đã chọn bảo toàn hợp đồng dữ liệu |
| JDBC/R2DBC không dùng ORM schema generation | Migration hoặc SQL init có kiểm soát | Cấu trúc được khởi tạo đúng trước khi repository chạy |

Với một bài test migration thật, có thể chọn Flyway là cơ chế chính và để Hibernate validate:

~~~text
spring.jpa.hibernate.ddl-auto=validate
spring.flyway.enabled=true
spring.liquibase.enabled=false
spring.sql.init.mode=never
~~~

Đây là một lựa chọn minh họa. Nếu ứng dụng dùng Liquibase, hãy dùng cơ chế tương ứng; không bật cả hai chỉ để tăng số lượng thành phần test.

Spring Boot hỗ trợ nhiều cơ chế khởi tạo database và khuyến nghị chọn một cơ chế tạo schema chính. Khi chuyển từ database nhúng sang database khác, cần khai báo rõ cách schema được dựng thay vì dựa vào mặc định cũ. [Database initialization của Spring Boot 3.5](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html).

Đối với ví dụ unique SKU, schema fixture được sinh từ annotation. Nếu production chỉ quản lý constraint bằng migration, hãy thêm bài test trên migration thật; annotation đúng không chứng minh migration đã tạo constraint đúng.

Dữ liệu seed cũng cần có chủ đích. Không đưa hàng trăm bản ghi mẫu vào mọi test khi chỉ vài bản ghi có thể thể hiện rõ predicate, thứ tự và ranh giới trang.

## 11. Điều chỉnh khi store mẫu là JDBC

Với Spring Data JDBC, giữ container PostgreSQL nếu đó là engine cần kiểm chứng, nhưng chọn `@DataJdbcTest` và model relational phù hợp.

Cần thay đổi:

- Annotation mapping sang loại được Spring Data JDBC hỗ trợ.
- Hạ tầng repository sang Spring Data JDBC.
- Cơ chế tạo schema sang migration hoặc SQL init phù hợp.
- Assertion theo semantics aggregate và thao tác ghi thực tế.

Không giữ `@Entity`, `TestEntityManager` hoặc giả định dirty checking JPA trong bài test JDBC.

Ví dụ model có thể là:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("catalog_item")
public record CatalogRow(
    @Id Long id,
    String sku,
    String label,
    boolean active
) {
}
~~~

Class này chỉ minh họa mapping JDBC; để dùng cần schema, repository và cấu hình khởi tạo tương ứng. Khả năng query và projection phải được đánh giá theo module JDBC, không chép mọi method JPA rồi mặc định cùng cách thực thi.

Nếu mục tiêu chỉ là kiểm thử một DAO dùng `JdbcTemplate`, `@JdbcTest` có thể đúng phạm vi hơn. Nó tập trung vào thành phần JDBC và bỏ qua regular component scanning theo cấu hình slice; DAO tùy biến có thể cần được import tường minh. [JdbcTest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/jdbc/JdbcTest.html).

Sự phân biệt này giúp giải thích lỗi “không tìm thấy repository bean”: có thể annotation slice đang nạp sai tầng, không nhất thiết database hoặc container bị hỏng.

## 12. Điều chỉnh khi store mẫu là R2DBC

`@DataR2dbcTest` tập trung vào repository, model và hạ tầng R2DBC. Không áp dụng cơ chế transaction test JDBC cho nó chỉ vì backend vẫn là PostgreSQL. [DataR2dbcTest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/data/r2dbc/DataR2dbcTest.html).

Cần kiểm tra riêng:

1. JVM có driver R2DBC tương ứng.
2. Cấu hình tạo đúng ConnectionFactory tới container.
3. URL và connection details thuộc giao thức R2DBC khi sử dụng API reactive.
4. Schema đã được khởi tạo bằng cơ chế phù hợp.
5. Test thực sự chờ completion/error của thao tác.

Luồng assertion nên biểu diễn công việc được thực thi:

~~~text
Tạo fixture
    -> chờ thao tác ghi hoàn tất
    -> thực thi query
    -> thu thập kết quả
    -> kiểm tra dữ liệu và completion/error
    -> dọn fixture theo chiến lược đã chọn
~~~

Chỉ gọi `repository.save(...)` rồi bỏ publisher không chứng minh dữ liệu đã được ghi. Tránh `subscribe()` rời rạc khiến method test kết thúc trước assertion.

Có thể dùng công cụ như Reactor StepVerifier hoặc adapter coroutine đúng stack để quan sát kết quả. Lựa chọn đó cần giữ lỗi của pipeline thay vì chuyển mọi lỗi thành danh sách rỗng.

Nếu bài test cần transaction reactive, hãy thiết kế ranh giới transaction reactive tương ứng. Nếu không có, dùng cơ chế cleanup và database/schema test cô lập; đừng mặc định annotation slice sẽ tự rollback mọi thao tác.

Cũng cần phân biệt PostgreSQL server container với JDBC client và R2DBC client. Cùng server không có nghĩa hai client tự chia sẻ cùng transaction.

## 13. Điều chỉnh khi store mẫu là MongoDB

`@DataMongoTest` là slice cho MongoDB mapping/repository; không mang giả định transaction test mặc định của `@DataJpaTest`. [DataMongoTest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/data/mongo/DataMongoTest.html).

Bài test cần xác định:

- Database và collection thuộc phạm vi test nào.
- Các index hoặc validator bắt buộc được tạo ở đâu.
- ID, field nullable và field thiếu được biểu diễn thế nào.
- Custom converter và auditing configuration nào cần được import.
- Fixture được dọn bằng cách nào nếu không có rollback phù hợp.

Nếu mục tiêu có multi-document transaction, một mongod chạy độc lập không đại diện đủ topology cần thiết. MongoDBContainer cung cấp hỗ trợ thiết lập replica set tùy API/version; cần dùng đúng cấu hình và đợi replica set sẵn sàng. Một replica set một node cũng không chứng minh hành vi failover nhiều node. [MongoDB module của Testcontainers](https://java.testcontainers.org/modules/databases/mongodb/).

Không suy rằng field đánh dấu unique trên model đã trở thành index trong backend. Nếu hợp đồng cần từ chối dữ liệu trùng, hãy bảo đảm index được tạo bằng cơ chế thực tế rồi kiểm tra hành vi từ chối đó.

Với store có khả năng tìm kiếm hoặc index cập nhật bất đồng bộ, assertion sau ghi còn phải tuân theo quy tắc visibility của engine. Đặt một khoảng ngủ cố định không thay thế việc chờ điều kiện mà test thực sự cần.

## 14. Cô lập dữ liệu và transaction của test

Cần phân biệt bốn cấp vòng đời:

| Cấp | Câu hỏi cần trả lời |
| --- | --- |
| Container | Backend được tạo/dừng theo method, class hay context? |
| Database/schema | Các test có dùng chung cấu trúc và namespace dữ liệu không? |
| Transaction | Thao tác nào thực sự được rollback sau mỗi test? |
| Fixture | Những bản ghi, index hoặc dữ liệu seed nào còn lại? |

Dùng chung một container không nhất thiết là lỗi nếu dữ liệu được cô lập đúng. Tạo container mới cũng chưa đủ nếu ứng dụng vẫn trỏ tới database bên ngoài qua một cấu hình ghi đè.

Với JPA/JDBC slice có transaction test, rollback hỗ trợ cô lập các thay đổi nằm trong phạm vi được quản lý. Nó không tự hủy một giao dịch đã commit riêng bằng `REQUIRES_NEW`, tác vụ ở luồng khác hoặc tác dụng phụ ngoài database.

Transaction của Spring TestContext và transaction ứng dụng là hai phạm vi cần phân biệt. Khi muốn kiểm chứng ranh giới service hoặc lỗi tại commit, thiết kế test tránh để transaction test bao ngoài làm thay đổi hành vi cần quan sát. [Transaction management trong Spring TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html).

Ví dụ, test repository sau `flush` giúp phát hiện lỗi statement. Một constraint được kiểm tra muộn ở commit hoặc một callback chỉ chạy sau commit có thể cần bài test khác với transaction kết thúc thật.

Nếu dọn dữ liệu bằng lệnh xóa, hãy xét thứ tự khóa ngoại và việc test chạy song song. Không để một method xóa cả bảng đang được method khác sử dụng. Có thể chọn schema/database riêng cho nhóm test hoặc namespace dữ liệu rõ ràng.

Đừng dùng chính một query đang được kiểm thử để dọn fixture một cách mù quáng. Nếu query đó sai predicate, dữ liệu thừa có thể làm các test sau thất bại khó giải thích.

## 15. Bổ sung cấu hình có chủ đích khi slice chưa đủ

Slice chỉ có giá trị khi nó chứa đúng dependency của hành vi đang kiểm tra.

| Thành phần thiếu | Hướng xử lý |
| --- | --- |
| Converter riêng của ứng dụng | Import cấu hình hoặc bean converter cần thiết |
| Auditor/time provider | Import cấu hình auditing và dùng nguồn actor/time xác định |
| Repository fragment phụ thuộc bean khác | Nạp fragment và collaborator tối thiểu cần thiết |
| Service điều phối nhiều repository | Chọn test tích hợp hoặc import phạm vi service có chủ đích |
| Client bên ngoài không thuộc mục tiêu test | Dùng test double theo hợp đồng thay vì mở thêm hệ thống không cần thiết |
| Nhiều store được phối hợp | Nạp và xác định rõ từng backend, manager và giới hạn phối hợp |

Không đổi sang `@SpringBootTest` cho mọi lỗi thiếu bean trước khi hiểu bean đó có thuộc mục tiêu test hay không. Ngược lại, nếu mục tiêu là wiring toàn ứng dụng, một slice đã được sửa tới mức nạp gần như mọi bean có thể không còn là lựa chọn dễ hiểu.

Với auditing, hãy kiểm tra metadata được ghi/đọc theo hợp đồng, không chỉ kiểm tra bean auditor tồn tại. Với fragment, hãy quan sát dữ liệu được thay đổi bằng backend thật nếu mục tiêu là SQL/mapping của fragment.

Khi test Query by Example, fixture và probe cũng cần thể hiện rõ property nào tham gia predicate; giá trị mặc định của một field primitive có thể vô tình tạo điều kiện lọc ngoài ý muốn. Chỉ kiểm thử các khả năng module store đã hỗ trợ và ứng dụng thực sự dùng.

## 16. Vận hành test ổn định ở máy phát triển và CI

### 16.1. Địa chỉ và port phải lấy từ container

Không hard-code `localhost:5432` cho PostgreSQL Testcontainers. Port được publish ra host có thể được cấp động; host cũng có thể khác localhost trong một số runtime. Dùng JDBC URL được container cung cấp hoặc connection details phù hợp. [Networking của Testcontainers](https://java.testcontainers.org/features/networking/).

Đối với generic container, phân biệt port bên trong container với mapped port phía host. Một URL đúng protocol nhưng dùng sai phía port vẫn tạo lỗi kết nối.

### 16.2. Chờ readiness theo tín hiệu phù hợp

Một process đã chạy chưa chắc dịch vụ đã sẵn sàng nhận request hoặc hoàn tất khởi tạo. Dùng wait strategy của module/container và cơ chế sẵn sàng phù hợp; tránh thêm `Thread.sleep` để che lỗi khởi động. [Startup và wait strategies](https://java.testcontainers.org/features/startup_and_waits/).

Ngay cả khi database đã sẵn sàng, migration/schema init vẫn cần hoàn tất trước khi query sử dụng các bảng đó.

### 16.3. Phân biệt lỗi hạ tầng và lỗi hợp đồng dữ liệu

| Lỗi quan sát được | Điều cần kiểm tra trước |
| --- | --- |
| Không tìm thấy Docker/runtime tương thích | Khả năng truy cập runtime của tiến trình test |
| Không kéo được image | Kết nối registry, quyền truy cập hoặc image/tag |
| Connection refused | Vòng đời container, host, mapped port và readiness |
| Authentication failed | Connection details thực sự được ứng dụng dùng |
| Table/collection chưa tồn tại như kỳ vọng | Migration, schema init, namespace và thứ tự khởi tạo |
| Repository bean không có | Slice, package scan và cấu hình module |
| Query sai dữ liệu | Fixture, mapping, predicate, sort và engine semantics |
| Chạy riêng qua nhưng chạy cả suite lỗi | Dữ liệu dùng chung, context cache và vòng đời backend |

Không biến việc backend không khởi động thành một bài test “đã qua”. Nếu một nhóm test được bỏ qua theo điều kiện môi trường, báo cáo CI phải phân biệt rõ passed, failed và skipped.

### 16.4. Tối ưu sau khi biết chi phí nằm ở đâu

Có thể chia nhóm test theo store và cấu hình để tận dụng context/container đúng vòng đời. Trước khi thay đổi, hãy đo thời gian tải image, khởi động database, nạp context, chạy migration và thực thi query.

Một container mới cho từng test thường tăng chi phí khởi động; một container chia sẻ quá rộng lại làm khó cô lập dữ liệu. Quyết định cần dựa vào phạm vi lỗi và mức độ song song mong muốn.

Tăng parallelism không tự giảm thời gian nếu database bị tranh chấp tài nguyên hoặc các test xóa fixture của nhau. Ưu tiên mô hình cô lập dễ hiểu rồi mới điều chỉnh mức chạy đồng thời.

## 17. Ma trận lựa chọn cho một module mẫu

Giả sử module minh họa có bốn nhóm kiểm chứng:

| Nhóm | Phạm vi test | Backend | Bằng chứng chính |
| --- | --- | --- | --- |
| Quy tắc tính toán trong service | Unit | Không có | Kết quả và nhánh xử lý nghiệp vụ |
| Mapping, derived query, page và projection JPA | Data JPA slice | PostgreSQL container | Dữ liệu thực tế và query đúng hợp đồng |
| Repository JDBC riêng của mẫu JDBC | Data JDBC slice | Engine mẫu tương ứng | Aggregate mapping và SQL đúng |
| Nghiệp vụ phối hợp service/repository/fragment | Tích hợp ứng dụng | Backend cần dùng | Wiring và kết quả commit/rollback |

Nếu module có thêm MongoDB hoặc R2DBC, tạo nhóm theo store đó với driver, fixture và cleanup phù hợp. Không lấy một bộ test JPA đã qua làm bằng chứng cho toàn bộ abstraction Commons trên mọi module.

Phạm vi tối thiểu hữu ích nên trả lời được:

1. Đang nạp đúng tầng Spring nào?
2. Đang kết nối backend nào, bằng client/driver nào?
3. Schema, index hoặc mapping được tạo từ nguồn nào?
4. Fixture có thể làm lộ predicate/sort/count sai không?
5. Assertion có quan sát dữ liệu và completion/error thật không?
6. State có được cô lập khi chạy nhiều test không?
7. Những khả năng nào của production chưa được môi trường này tái hiện?

## 18. Tự kiểm tra kiến thức

1. Vì sao test slice và Testcontainers không phải hai lựa chọn loại trừ nhau?
2. Khi nào DataJdbcTest phù hợp hơn JdbcTest, và ngược lại?
3. Việc PostgreSQLContainer đang chạy chưa chứng minh điều gì về DataSource của test?
4. Vì sao cần nhiều bản ghi hơn kích thước một trang khi kiểm thử phân trang và count?
5. Flush và clear trong ví dụ JPA loại bỏ những điểm mù nào?
6. Một schema được Hibernate tạo từ entity bỏ sót bằng chứng nào về migration ứng dụng?
7. Vì sao không được mặc định MongoDB hoặc R2DBC slice có rollback giống JPA slice?
8. Cần phối hợp context cache với container lifecycle như thế nào?
9. Khi nào cần rời khỏi slice để kiểm chứng service và transaction thực tế?
10. Một container cùng engine nhưng khác topology, extension hoặc collation giới hạn kết luận ra sao?

Chọn slice giúp tập trung đúng thành phần Spring; chọn backend giúp kiểm chứng đúng hành vi của store. Một bộ fixture có chủ đích, kết nối đã được xác nhận và assertion quan sát dữ liệu thật sẽ làm rõ khả năng của từng implementation Spring Data thay vì chỉ xác nhận application context khởi động được.
