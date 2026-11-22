# Chọn unit test, repository test và integration test theo mục tiêu

Kiểm thử ứng dụng **Spring Data MongoDB** không có một lựa chọn đúng cho mọi trường hợp. Một quy tắc chuẩn hóa email có thể kiểm thử bằng Java và Mockito trong vài mili giây, nhưng muốn biết **MongoRepository** có truy vấn đúng theo tên phương thức hay không, hoặc **MongoTemplate** aggregation có chạy trên MongoDB thật hay không, phải sử dụng MongoDB. Khi cần xác minh service, transaction và cấu hình của toàn ứng dụng, cần mở rộng phạm vi thành **integration test**.

Bài học trong chương **Kiểm thử** này hướng dẫn cách chọn **unit test**, **repository test** và **integration test** theo mục tiêu kiểm chứng, thiết kế ví dụ cho **SPRING_DATA_MONGODB**, tổ chức dữ liệu kiểm thử và tránh những bài test xanh nhưng không phát hiện lỗi sản xuất.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân loại rủi ro cần kiểm chứng thành **business rule**, **mapping và query**, hoặc **hành vi phối hợp giữa nhiều thành phần**.
2. Chọn phạm vi test nhỏ nhất nhưng đủ để phát hiện lỗi mục tiêu.
3. Viết **unit test** cho service dùng MongoDB repository bằng JUnit 5 và Mockito, không khởi tạo Spring context.
4. Viết **repository test** bằng **@DataMongoTest** kết hợp MongoDB thật qua Testcontainers.
5. Viết **integration test** bằng **@SpringBootTest** để xác minh service, repository, cấu hình và MongoDB hoạt động cùng nhau.
6. Xác định khi nào phải kiểm thử **index, aggregation, transaction, optimistic locking và reactive streams**.

## 2. Bắt đầu từ câu hỏi: “Muốn chứng minh điều gì?”

| Mục tiêu cần kiểm chứng | Mức kiểm thử ưu tiên | Có cần MongoDB thật? | Vì sao? |
| --- | --- | --- | --- |
| Chuẩn hóa chuỗi, kiểm tra input, tính toán nghiệp vụ | **Unit test** | Không | Hành vi nằm trong Java thuần, có thể cô lập qua mock dependency. |
| Service gọi repository đúng điều kiện, phản ứng khi dependency lỗi | **Unit test** | Không | Kiểm soát đầu vào, kết quả, exception và tương tác bằng mock. |
| **findByEmail**, **Criteria**, **Query**, **Aggregation** tạo truy vấn đúng | **Repository test** | Có | Phải xác minh mapping và cách MongoDB thực thi truy vấn. |
| **@Document**, **@Field**, converter, BSON, cách ánh xạ **_id** | **Repository test** | Có | Mockito không mô phỏng cơ chế chuyển đổi BSON và mapping. |
| Tạo unique index, kiểm tra duplicate key, collation | **Repository test** | Có | Cần engine MongoDB và chỉ mục thực tế. |
| Service gọi nhiều repository, event, converter hoặc transaction manager | **Integration test** | Có, nếu luồng dùng MongoDB | Phải kiểm tra ranh giới thành phần và cấu hình Spring. |
| Endpoint HTTP → service → repository → MongoDB | **Integration test** | Có khi muốn xác minh lưu trữ thật | Test cả wiring, serialization, validation, exception handling. |
| Atomic update, concurrent write, transaction, read concern | **Repository / Integration test** | Có, với topology phù hợp | Đây là hành vi MongoDB, không thể kết luận từ mock. |
| Backpressure, hủy subscription, retry khi dùng ReactiveMongoTemplate | **Unit + Integration test** | Tùy hành vi | Dùng StepVerifier cho operator; DB thật để kiểm tra truy vấn và I/O. |
| Hiệu năng của index và aggregation trên dữ liệu lớn | **Performance / load test** riêng | Có, dữ liệu và môi trường đại diện | Test chức năng không chứng minh hiệu năng sản xuất. |

**Quy tắc:** phân loại theo **bằng chứng cần có**, không dựa vào tên class được kiểm thử. Một bài test cho service nhưng mock toàn bộ **MongoRepository** vẫn là unit test; nó **không** kiểm chứng truy vấn MongoDB.

~~~mermaid
flowchart TD
    A["Cần chứng minh điều gì?"] --> B{"Quy tắc Java có thể tách khỏi database?"}
    B -- "Có" --> C["Unit test: JUnit + Mockito"]
    B -- "Không" --> D{"Cần chạy gần như toàn bộ ứng dụng?"}
    D -- "Không" --> E["Repository test: @DataMongoTest + MongoDB thật"]
    D -- "Có" --> F["Integration test: @SpringBootTest + MongoDB thật"]
    E --> G["Feature đặc biệt: topology và server version tương thích"]
    F --> G
~~~

## 3. Một ví dụ dùng xuyên suốt

Giả sử ứng dụng quản lý khách hàng cho phép đăng ký email. Nghiệp vụ yêu cầu:

- Email được **trim** và chuyển về chữ thường trước khi ghi.
- Không chấp nhận email trống.
- Một email chỉ được đăng ký một lần; phía MongoDB phải bảo vệ bằng **unique index**.
- Khách hàng được tạo với trạng thái **ACTIVE**.
- Có thể truy vấn danh sách khách hàng theo trạng thái, sắp xếp email tăng dần.

**Entity — Customer.java:**

~~~java
package example.customer;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public class Customer {
    @Id
    private String id;

    @Indexed(unique = true)
    private String email;

    private String status;

    protected Customer() {
        // Dành cho cơ chế mapping.
    }

    public Customer(String email, String status) {
        this.email = email;
        this.status = status;
    }

    public String getId() { return id; }
    public String getEmail() { return email; }
    public String getStatus() { return status; }
}
~~~

**Repository — CustomerRepository.java:**

~~~java
package example.customer;

import java.util.List;
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerRepository
        extends MongoRepository<Customer, String> {

    boolean existsByEmail(String email);

    Optional<Customer> findByEmail(String email);

    List<Customer> findByStatusOrderByEmailAsc(String status);
}
~~~

**Service — CustomerRegistrationService.java:**

~~~java
package example.customer;

import java.util.Locale;
import org.springframework.stereotype.Service;

@Service
public class CustomerRegistrationService {
    private final CustomerRepository repository;

    public CustomerRegistrationService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer register(String rawEmail) {
        if (rawEmail == null || rawEmail.isBlank()) {
            throw new IllegalArgumentException("Email is required");
        }

        String email = rawEmail.trim().toLowerCase(Locale.ROOT);
        if (repository.existsByEmail(email)) {
            throw new IllegalStateException("Email already registered");
        }

        return repository.save(new Customer(email, "ACTIVE"));
    }
}
~~~

Phép **existsByEmail** giúp trả lỗi nghiệp vụ sớm nhưng **không ngăn được race condition** khi hai request cùng kiểm tra một email chưa tồn tại. **Unique index ở MongoDB** mới là hàng rào cuối cùng để ngăn ghi trùng. Ứng dụng thực tế cần ánh xạ **DuplicateKeyException** thành lỗi domain hoặc phản hồi HTTP phù hợp.

Các ví dụ dưới đây dùng **JUnit Jupiter**, **Mockito**, **Spring Boot 3.x / Spring Data MongoDB 4.x** và **Testcontainers 1.x** để minh họa import/class cụ thể. Nếu dự án dùng major version khác, hãy đối chiếu package Testcontainers, thuộc tính kết nối và thư viện tương thích với BOM đang dùng trước khi sao chép.

## 4. Unit test: kiểm tra nghiệp vụ mà không khởi tạo MongoDB

Unit test tập trung vào quyết định của service, chẳng hạn email trống bị từ chối trước khi gọi repository; chuỗi được chuẩn hóa; email đã tồn tại phát sinh exception; khách hàng mới có trạng thái **ACTIVE**.

~~~java
package example.customer;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CustomerRegistrationServiceTest {

    @Mock
    CustomerRepository repository;

    @InjectMocks
    CustomerRegistrationService service;

    @Test
    void shouldNormalizeEmailAndSaveActiveCustomer() {
        when(repository.existsByEmail("ada@example.com")).thenReturn(false);
        when(repository.save(any(Customer.class)))
            .thenAnswer(invocation -> invocation.getArgument(0));

        Customer result = service.register(" Ada@Example.COM ");

        ArgumentCaptor<Customer> captor =
            ArgumentCaptor.forClass(Customer.class);
        verify(repository).save(captor.capture());

        assertEquals("ada@example.com", captor.getValue().getEmail());
        assertEquals("ACTIVE", captor.getValue().getStatus());
        assertEquals("ada@example.com", result.getEmail());
    }

    @Test
    void shouldRejectBlankEmailWithoutAccessingDatabase() {
        assertThrows(IllegalArgumentException.class,
            () -> service.register("   "));
        verifyNoInteractions(repository);
    }

    @Test
    void shouldRejectAlreadyRegisteredEmail() {
        when(repository.existsByEmail("ada@example.com")).thenReturn(true);

        assertThrows(IllegalStateException.class,
            () -> service.register("Ada@example.com"));

        verify(repository, never()).save(any(Customer.class));
    }
}
~~~

**Unit test này chứng minh được:** logic chuẩn hóa, điều kiện từ chối, thông tin gửi tới dependency và nhánh xử lý từ kết quả mock. **Nó không chứng minh được:** MongoDB có unique index, phương thức **existsByEmail** có truy vấn đúng, document có mapping đúng hay lệnh **save** có thất bại khi ghi trùng hay không.

Không cần **@SpringBootTest**, **@DataMongoTest** hoặc **@MockBean** để kiểm thử class này. Test càng ít khởi tạo hạ tầng thì càng chạy nhanh và dễ chỉ ra lỗi.

## 5. Repository test: chứng minh ánh xạ và truy vấn trên MongoDB thật

**@DataMongoTest** là một test slice của Spring Boot dành cho MongoDB: tạo context tập trung vào thành phần MongoDB như **MongoTemplate**, mapping và repository, đồng thời hạn chế quét bean không thuộc phạm vi này. Nó **không** tự đảm bảo có MongoDB đang chạy. Đối với bài test có giá trị về truy vấn, hãy dùng MongoDB thật thông qua Testcontainers hoặc một MongoDB test instance được quản lý.

Ví dụ dưới đây dùng Testcontainers 1.x, với Docker khả dụng. Dependency tối thiểu trong test scope gồm **spring-boot-starter-test**, **org.testcontainers:junit-jupiter** và **org.testcontainers:mongodb** (version phải thống nhất với dependency management).

~~~java
package example.customer;

import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@DataMongoTest
@Testcontainers
class CustomerRepositoryTest {

    @Container
    static final MongoDBContainer mongo = new MongoDBContainer(
        DockerImageName.parse("mongo:7.0")
    );

    @DynamicPropertySource
    static void mongodbProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", mongo::getReplicaSetUrl);
    }

    @Autowired
    CustomerRepository repository;

    @Autowired
    MongoTemplate template;

    @BeforeEach
    void resetData() {
        repository.deleteAll();
    }

    @Test
    void shouldFindActiveCustomersOrderedByEmail() {
        repository.saveAll(List.of(
            new Customer("zoe@example.com", "ACTIVE"),
            new Customer("ada@example.com", "ACTIVE"),
            new Customer("bob@example.com", "INACTIVE")
        ));

        List<String> emails = repository
            .findByStatusOrderByEmailAsc("ACTIVE")
            .stream().map(Customer::getEmail).toList();

        assertEquals(
            List.of("ada@example.com", "zoe@example.com"),
            emails
        );
    }

    @Test
    void shouldEnforceUniqueEmailInMongoDB() {
        // Tạo index thật: không phụ thuộc vào auto-index-creation.
        template.indexOps(Customer.class).ensureIndex(
            new Index().on("email", Sort.Direction.ASC).unique()
        );

        repository.save(new Customer("ada@example.com", "ACTIVE"));

        assertThrows(DuplicateKeyException.class,
            () -> repository.save(
                new Customer("ada@example.com", "ACTIVE")
            ));
    }
}
~~~

**Điểm cần quan sát:**

- Test kiểm tra quá trình serialize thành BSON, mapping ngược thành **Customer**, derived query và kết quả thực sự do MongoDB trả về.
- **findByStatusOrderByEmailAsc** được kiểm chứng thực sự; Mockito không thể phát hiện tên property sai hoặc cách database thực thi query.
- **@Indexed(unique = true)** khai báo ý định; việc tạo index từ annotation phụ thuộc **auto-index-creation**. Bài test chủ động **ensureIndex** để chứng minh engine từ chối dữ liệu trùng.
- **@DataMongoTest** không tự nạp service bất kỳ. Có thể dùng **@Import** nếu mục tiêu test phù hợp, nhưng một luồng nhiều bean thường rõ nghĩa hơn ở integration test.
- **mongo:7.0** chỉ là ví dụ. Dùng server version gần production, nhất là khi kiểm tra operator, aggregation, index hoặc transaction.

**Lưu ý phiên bản:** một số Testcontainers major version mới thay package hoặc API của **MongoDBContainer**. Ví dụ trên dành cho **Testcontainers 1.x**; hãy chọn import và dependency phù hợp với bản thực tế, không trộn nhiều major version.

## 6. Integration test: service, Spring context và MongoDB đi cùng nhau

**@SpringBootTest** tải ApplicationContext của ứng dụng và kiểm thử bean, cấu hình thật, service và repository phối hợp. Nó phù hợp với lỗi do wiring, profile, converter, event listener, transaction manager hoặc các dependency tích hợp. Không cần dùng full context để kiểm tra mọi phương thức của repository.

Ví dụ dưới đây giả định ứng dụng thực tế có class **@SpringBootApplication** và scan được **CustomerRegistrationService**:

~~~java
package example.customer;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Testcontainers
class CustomerRegistrationIntegrationTest {

    @Container
    static final MongoDBContainer mongo = new MongoDBContainer(
        DockerImageName.parse("mongo:7.0")
    );

    @DynamicPropertySource
    static void mongodbProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", mongo::getReplicaSetUrl);
    }

    @Autowired
    CustomerRegistrationService service;

    @Autowired
    CustomerRepository repository;

    @BeforeEach
    void resetData() {
        repository.deleteAll();
    }

    @Test
    void registrationShouldPersistNormalizedEmail() {
        Customer saved = service.register("  Ada@Example.COM ");
        assertNotNull(saved.getId());
        assertEquals("ada@example.com", saved.getEmail());

        Customer stored = repository
            .findByEmail("ada@example.com")
            .orElseThrow();
        assertEquals(saved.getId(), stored.getId());
        assertEquals("ACTIVE", stored.getStatus());
    }
}
~~~

Test này xác minh luồng **CustomerRegistrationService → CustomerRepository → MongoDB**, kết quả ghi và khả năng đọc lại document. Với **@SpringBootTest(webEnvironment = RANDOM_PORT)**, có thể mở rộng để gửi HTTP qua **TestRestTemplate**, **WebTestClient** hoặc client HTTP phù hợp, kiểm tra request validation, JSON, security và exception mapping.

**Cấu hình cho ứng dụng thực tế:** **@SpringBootTest** sẽ kích hoạt những bean mà full application yêu cầu. Nếu dự án còn Kafka, S3, external HTTP hay authentication server, cần cấu hình fake/test double hoặc test instance phù hợp cho dependency đó. Thiếu dịch vụ ngoài không đồng nghĩa MongoDB sai, nhưng bỏ qua dependency quan trọng cũng không chứng minh được toàn bộ luồng.

| Tiêu chí | **@DataMongoTest** | **@SpringBootTest** |
| --- | --- | --- |
| Spring context | Chỉ các thành phần MongoDB và cấu hình liên quan | Phần lớn/toàn bộ ứng dụng theo cấu hình test |
| Service do ứng dụng định nghĩa | Thường không được nạp nếu không import | Được nạp nếu thuộc phạm vi component scan |
| Phù hợp nhất | Derived queries, mapping, BSON, index, MongoTemplate | Wiring, service + DB, transaction, security/HTTP khi cần |
| Tốc độ và cô lập lỗi | Thường nhanh hơn, ít dependency | Thường chậm hơn, nhiều thành phần có thể gây lỗi |
| Có MongoDB thật? | **Có**, nếu cấu hình Testcontainers/DB thật | **Có**, nếu cấu hình Testcontainers/DB thật |

Lưu ý: **@DataMongoTest** tuy có tên “slice test” nhưng khi dùng MongoDB thật vẫn là **integration test ở ranh giới repository–database**. Ba nhãn trong bài phân biệt **mục tiêu và phạm vi**, không phải ba hệ thống độc lập tuyệt đối.

## 7. MongoTemplate, Criteria và aggregation: chọn test thế nào?

Với **MongoTemplate**, một phương thức có thể vừa tính toán Java vừa xây dựng **Query** phức tạp. Nên phân loại:

- Hàm tạo điều kiện lọc thuần Java, kiểm tra input hoặc phân nhánh nghiệp vụ: unit test khi không phụ thuộc engine.
- **Criteria**, **Update**, **findAndModify**, **bulk operations**, **aggregation**, chuyển đổi BSON, collation và toán tử MongoDB: repository test trên server thật.
- Luồng nhiều thao tác thay đổi document, gọi event hoặc transaction: integration test với hạ tầng phù hợp.

Ví dụ truy vấn có điều kiện:

~~~java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<Customer> findActiveCustomers(MongoTemplate template) {
    Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
    ).with(Sort.by(Sort.Direction.ASC, "email"));
    return template.find(query, Customer.class);
}
~~~

Đoạn trên minh họa phần thân phương thức trong custom repository hoặc DAO, không phải một file Java độc lập. Chỉ bài test trên database mới chứng minh được tên trường được mapping đúng và thứ tự sắp xếp hoạt động như mong đợi. Với aggregation **$match → $group → $sort**, hãy tạo dữ liệu đại diện nhiều nhóm, dữ liệu rỗng và trường null; kiểm tra **kết quả cuối cùng**, không chỉ xác minh lệnh aggregate đã được gọi.

Khi kiểm thử cập nhật hàng loạt, đừng chỉ kiểm tra **matchedCount**: cần hiểu **modifiedCount**, trường nào thay đổi, có ghi đè document ngoài điều kiện không, và chạy lại có idempotent hay không. Với **findAndModify**, kiểm tra phiên bản document trả về (trước hay sau update) theo **FindAndModifyOptions**.

## 8. Index, transaction và optimistic locking cần điều kiện riêng

### 8.1. Kiểm thử index đúng nghĩa

Một index ảnh hưởng đồng thời đến **đúng/sai** (ví dụ unique constraint) và **hiệu năng** (index plan). Hai loại bằng chứng này khác nhau:

- **Tính đúng:** xác nhận index có key, unique/TTL/collation như thiết kế; thử insert trùng và các trạng thái null/missing nếu nghiệp vụ cần.
- **Hiệu năng:** dùng **explain("executionStats")** với dữ liệu đủ đại diện để xem **winningPlan**, **totalDocsExamined**, **totalKeysExamined**, **nReturned**. Test có 5 document không chứng minh query sẽ nhanh trên 10 triệu document.

TTL index có quá trình xóa nền, không chạy chính xác tới mili giây. Đừng viết test giả định document biến mất ngay tại mốc TTL. Kiểm tra cấu hình index trước; nếu thử độ trễ xóa thực tế, dùng test riêng với khoảng chờ phù hợp.

### 8.2. Kiểm thử transaction

MongoDB multi-document transaction cần môi trường **replica set** hoặc **sharded cluster** và **MongoTransactionManager** (hoặc **ReactiveMongoTransactionManager** đối với reactive). Dùng MongoDB standalone để thử transaction rồi kết luận ứng dụng sai là không chính xác.

Một test có giá trị cần chứng minh:

1. Trong transaction, hai thao tác ghi thành công sẽ cùng được commit.
2. Khi thao tác thứ hai thất bại, dữ liệu của thao tác đầu **không** được commit.
3. Đọc ngoài transaction sau khi lỗi phải xác nhận không còn dữ liệu ghi dở.
4. Spring thực sự quản lý transaction của luồng đang kiểm thử; chú ý self-invocation của **@Transactional** và reactive pipeline phải được subscribe.

Tránh đặt **@Transactional** lên chính test rồi kiểm tra trạng thái trước khi transaction của test kết thúc, vì có thể che lỗi commit/rollback của service. Thường nên gọi service có transaction, để phương thức trả về hoặc ném exception, rồi truy vấn lại ở phạm vi mới.

### 8.3. Optimistic locking và concurrent update

Với trường **@Version**, giả lập hai bản đọc cùng version, ghi bản thứ nhất rồi ghi bản thứ hai. Kết quả kỳ vọng là thao tác thứ hai gặp **OptimisticLockingFailureException** trong điều kiện phù hợp, thay vì âm thầm ghi đè dữ liệu mới.

Với thao tác đồng thời, mock repository chạy tuần tự **không thể** chứng minh tính nguyên tử, race condition hay phân giải xung đột. Cần test trên MongoDB thật với request được điều phối đồng thời, assert bất biến cuối cùng: **không có hai email trùng**, **không mất update**, **không ghi dở giữa transaction**.

## 9. ReactiveMongoRepository và ReactiveMongoTemplate

Trong reactive stack, phân biệt **xử lý stream** với **I/O MongoDB**.

**Unit test reactive** kiểm tra operator, nhánh lỗi và retry bằng **StepVerifier** khi publisher không phụ thuộc DB:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveRuleTest {
    Mono<String> normalize(String raw) {
        return Mono.justOrEmpty(raw)
            .filter(s -> !s.isBlank())
            .map(s -> s.trim().toLowerCase(java.util.Locale.ROOT))
            .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Email is required")
            ));
    }

    @Test
    void normalizesWithoutMongoDB() {
        StepVerifier.create(normalize(" Ada@Example.COM "))
            .expectNext("ada@example.com")
            .verifyComplete();
    }
}
~~~

**Repository/integration test reactive** phải subscribe publisher để thao tác thực sự chạy:

~~~java
StepVerifier.create(reactiveRepository.findByEmail("ada@example.com"))
    .assertNext(customer ->
        assertEquals("ada@example.com", customer.getEmail()))
    .verifyComplete();
~~~

Trong snippet thứ hai, **reactiveRepository** là **ReactiveMongoRepository** đã cấu hình MongoDB test thật và có dữ liệu phù hợp từ trước. Nếu không có subscription, nhiều phép I/O reactive không thực thi và một test chỉ gọi hàm rồi kết thúc có thể xanh sai lệch.

Với concurrency, kiểm thử hủy subscription, timeout, backpressure và retry tác động lên thao tác ghi. Không dùng **Thread.sleep** để giả lập độ trễ thiếu kiểm soát; ưu tiên virtual time cho operator thuần Reactor và test tích hợp khi liên quan driver/network.

## 10. Dữ liệu, môi trường và tính độc lập của test

Một test tốt phải **lặp lại được** khi chạy đơn lẻ, chạy cả suite hoặc chạy song song trên CI.

| Vấn đề | Cách làm phù hợp |
| --- | --- |
| Dữ liệu từ test trước làm sai test sau | Dùng database/collection riêng hoặc xóa dữ liệu xác định trong **@BeforeEach**; tránh xóa toàn DB dùng chung. |
| Nhiều test ghi cùng collection | Dùng namespace riêng cho mỗi test hoặc không chạy song song những test chia sẻ state. |
| Khác server version và tính năng | Chạy container/cluster tương thích production và ghi rõ version; thêm môi trường riêng cho feature đặc biệt. |
| Unique index/TTL chưa tồn tại | Tạo index có kiểm soát trong fixture hoặc migration setup; đừng mặc định annotation tự tạo. |
| Thời gian/ID sinh động làm test không ổn định | Cố định **Clock** cho unit test, kiểm tra ID theo tính chất thay vì hardcode giá trị ngẫu nhiên. |
| External services gây lỗi không liên quan | Dùng service fake/test double hoặc container riêng theo mục tiêu integration test. |
| Docker không khả dụng trong CI | Cấu hình Docker runner tương thích Testcontainers; nêu rõ test bị skip, không coi là đã kiểm chứng. |
| Chạy nhiều test context tốn bộ nhớ | Tái sử dụng cấu hình context hợp lý, giới hạn fixture và số container đồng thời. |

**Không cần rollback tự động trong mọi test MongoDB.** Với test thông thường, dọn dữ liệu giữa các test hoặc dùng database riêng có thể đơn giản hơn. Nếu test yêu cầu transaction, phải kiểm chứng commit/rollback của chính feature đó; gắn annotation transaction lên mọi test có thể khiến assertion lệch hành vi sản xuất.

Với **@DataMongoTest**, xem package của entity/repository: nếu class test nằm ngoài cây package mà Spring tìm bean, hãy cấu hình scan hoặc import rõ ràng. Không tìm thấy repository bean thường do test slice và cấu trúc package, không nhất thiết do MongoDB.

## 11. Thiết kế bộ test theo rủi ro

Đừng viết hàng trăm integration test lặp cùng điều kiện nghiệp vụ. Hãy phân tầng theo rủi ro và khả năng chẩn đoán:

| Nhóm test | Mục tiêu chính | Ví dụ | Nên chạy |
| --- | --- | --- | --- |
| **Unit** | Quy tắc và nhánh xử lý Java | Email trống; chuẩn hóa; lỗi dependency | Mỗi commit / local |
| **Repository slice** | BSON mapping, query, index | Derived query, Criteria, duplicate key | Mỗi PR / CI |
| **Full integration** | Wiring, service–repository, transaction | Đăng ký khách hàng lưu thật; rollback | Mỗi PR hoặc suite tích hợp |
| **Contract / API** | Giao tiếp và định dạng | JSON schema, HTTP status, lỗi trùng | Theo thay đổi API |
| **Performance** | Query plan, thông lượng, latency | Aggregation trên dữ liệu đại diện | Theo thay đổi index/query hoặc định kỳ |

**Ví dụ tối giản nhưng đủ ý nghĩa** cho tính năng đăng ký:

- Unit: 3–5 bài kiểm tra dữ liệu hợp lệ, null/trống, trùng đã biết, chuẩn hóa.
- Repository: 2–4 bài kiểm tra mapping, truy vấn email, danh sách theo trạng thái và unique index.
- Integration: 1–2 bài kiểm tra service thực sự lưu thành công và xử lý lỗi trùng từ DB.
- Khi bổ sung transaction, aggregation, concurrency hoặc reactive, tăng test đúng ở **điểm rủi ro mới phát sinh**, không sao chép toàn bộ kịch bản sang mọi tầng.

Test verify tên phương thức được gọi quá chi tiết dễ trở thành **implementation test**: đổi cách triển khai mà hành vi vẫn đúng cũng làm test hỏng. Với unit test, verify lời gọi có ý nghĩa nghiệp vụ; với repository và integration, ưu tiên assert **trạng thái dữ liệu và kết quả cuối**.

## 12. Một số mẫu test dễ gây hiểu nhầm

### “Mockito chứng minh repository query chạy đúng”

~~~java
when(repository.findByEmail("ada@example.com"))
    .thenReturn(java.util.Optional.of(
        new Customer("ada@example.com", "ACTIVE")
    ));
~~~

Đây là **cài đặt hành vi mock**, không phải kiểm chứng **findByEmail**. Để kiểm tra derived query, cần gửi dữ liệu qua MongoDB thật và gọi repository thật.

### “@DataMongoTest mặc định có server”

Annotation này quản lý **test slice** và cấu hình MongoDB của Spring; test vẫn cần MongoDB khả dụng. Không giả định embedded MongoDB tự khởi động trong mọi phiên bản Spring Boot. Nếu dùng fake hoặc embedded engine, cần hiểu sự khác biệt với MongoDB thật, đặc biệt ở transaction/index/aggregation.

### “Một test insert thành công chứng minh unique index”

Insert một document có thể thành công dù unique index chưa tồn tại. Muốn chứng minh tính unique, hãy đảm bảo index tồn tại và thử insert trùng.

### “Dữ liệu ít là đủ chứng minh query nhanh”

Kết quả đúng và query plan tốt là hai mục tiêu khác nhau. Muốn kiểm tra hiệu năng, đo với kích thước dữ liệu, cardinality và phân phối gần production.

### “Reactive method được gọi là đã lưu dữ liệu”

Một **Mono** hoặc **Flux** thường chưa chạy thao tác ghi trước khi được subscribe. Hãy dùng **StepVerifier** hoặc subscriber rõ ràng và kiểm tra trạng thái MongoDB sau khi publisher hoàn tất.

## 13. Checklist trước khi chọn và viết test

1. **Viết một câu về điều cần chứng minh:** “Email được chuẩn hóa” hay “Unique index từ chối hai document trùng”?
2. **Chọn phạm vi nhỏ nhất chứa hành vi:** Java thuần → unit; query/mapping → repository; phối hợp bean và hạ tầng → integration.
3. **Chọn phụ thuộc thật hay giả theo rủi ro:** mock service boundary khi phù hợp, dùng MongoDB thật khi kiểm tra hành vi MongoDB.
4. **Khớp version/topology:** replica set nếu thử transaction, server version phù hợp nếu dùng operator/index mới.
5. **Chuẩn bị fixture cả trường hợp biên:** null, missing, empty, duplicate, Unicode, dữ liệu cũ và nhiều loại BSON khi liên quan.
6. **Kiểm tra kết quả quan sát được:** giá trị trả về, exception, document đã lưu, index và dữ liệu sau rollback.
7. **Giữ test độc lập:** chạy lặp, chạy riêng và trên CI cho kết quả nhất quán.
8. **Giải thích giới hạn của bộ test:** unit không xác nhận query; repository slice không xác nhận toàn bộ wiring; integration nhỏ không khẳng định hiệu năng production.

## 14. Bài thực hành

**Bài toán:** mở rộng **CustomerRegistrationService** để từ chối domain email không được phép và viết chức năng tìm khách hàng theo status từ một **MongoRepository**.

**Yêu cầu:**

1. Tạo unit test cho domain cho phép và từ chối; dùng Mockito để khẳng định repository không được gọi khi email không hợp lệ.
2. Thêm repository query tìm danh sách khách hàng **ACTIVE** theo email tăng dần. Viết **@DataMongoTest** với ít nhất ba document và khẳng định thứ tự kết quả.
3. Tạo unique index thực sự và thử insert trùng cùng email; giải thích tại sao chỉ dùng **existsByEmail** chưa đủ.
4. Dùng **@SpringBootTest** đăng ký một khách hàng qua service, đọc lại bằng repository và xác minh dữ liệu đã chuẩn hóa.
5. Nêu tình huống mà bộ test trên **chưa đủ**, ví dụ đăng ký đồng thời, transaction nhiều document hoặc aggregation phức tạp; đề xuất test bổ sung phù hợp.

**Tiêu chí hoàn thành:** không chỉ có test xanh, mà mỗi nhóm test phải nêu rõ mục tiêu, phần hệ thống đang được thực thi thật và giới hạn bằng chứng. Với Spring Data MongoDB, **unit test bảo vệ logic**, **repository test bảo vệ truy vấn và mapping**, còn **integration test bảo vệ hành vi phối hợp của ứng dụng với MongoDB**.
