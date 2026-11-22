# Kiểm tra hợp đồng Spring Data REST với cơ sở dữ liệu thật qua Testcontainers

## Mục tiêu

Sau bài này, bạn có thể xây dựng integration test cho Spring Data REST chạy với database thật trong Testcontainers; kiểm tra HTTP contract của collection, item, association và query resource; xác minh HAL links, status code, header, validation và persistence; chạy schema migration trên database test; và tổ chức test độc lập, lặp lại được trong CI.

## 1. Vì sao cần kiểm thử với database thật?

Một controller hoặc repository test dùng mock có thể xác nhận code gọi đúng collaborator, nhưng không chứng minh ứng dụng hoạt động đúng với database mà production sử dụng. Một số lỗi chỉ xuất hiện khi chạy qua JDBC driver, ORM provider, SQL dialect và schema thật:

- Kiểu cột, precision, timezone hoặc constraint không tương thích.
- Query method sinh SQL khác nhau giữa H2 và PostgreSQL/MySQL.
- Mapping entity, lazy loading, cascade hoặc orphan removal hoạt động khác kỳ vọng.
- Unique constraint, foreign key và transaction rollback không đúng.
- Migration thiếu index, sai thứ tự hoặc không chạy trên database trống.
- Spring Data REST trả association link hoặc representation khác dự kiến sau khi serialize entity được persistence provider nạp.

Testcontainers cho phép khởi động database thực trong container dùng cho test. Ứng dụng Spring kết nối vào container đó, chạy migration và xử lý HTTP request như một ứng dụng tích hợp thông thường. Test vì thế kiểm tra được hợp đồng từ HTTP đến database.

Mục tiêu không phải thay toàn bộ unit test bằng container test. Unit test vẫn phù hợp để kiểm tra logic thuần và nhanh. Dùng Testcontainers cho các hành vi phụ thuộc database, mapping, transaction, migration và HTTP integration.

## 2. Testcontainers hoạt động như thế nào?

Testcontainers là thư viện Java điều khiển container runtime để tạo dependency tạm thời cho test. Với database, test khai báo image và cấu hình như username, password, database name. Khi test cần container, thư viện khởi động database, chờ readiness, cung cấp host/port được ánh xạ và dọn container theo lifecycle.

Ví dụ PostgreSQL:

```java
PostgreSQLContainer<?> postgres =
    new PostgreSQLContainer<>("postgres:16-alpine")
        .withDatabaseName("spring_data_rest_test")
        .withUsername("test")
        .withPassword("test");
```

Port của container thường được ánh xạ sang một port khả dụng trên host. Không hard-code port PostgreSQL là 5432 trong cấu hình test; lấy JDBC URL, username và password từ container.

Ưu điểm:

- Dùng đúng engine database gần với production.
- Không cần cài database riêng trên máy của từng developer.
- Có thể chạy song song với các build khác nhờ port mapping động.
- Mỗi test suite có thể dùng database sạch.
- Có thể kiểm tra migration và constraint thực tế.

Testcontainers cần Docker-compatible container runtime đang chạy. Trong CI, runner phải cho phép khởi động container hoặc dùng cấu hình Testcontainers Cloud/remote runtime phù hợp.

## 3. Thêm dependency cho Spring Boot và PostgreSQL

Với Maven, ví dụ các dependency test:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
```

Nếu dùng Spring Boot dependency management, ưu tiên để BOM quản lý phiên bản tương thích của Testcontainers thay vì tự chọn các version không đồng bộ. Với Spring Boot phiên bản mới, có thể dùng module Testcontainers tương ứng và annotation `@ServiceConnection` nếu dependency hỗ trợ.

Nếu dự án dùng MySQL, MariaDB, SQL Server hoặc database khác, chọn module và container class đúng engine. Không dùng PostgreSQL container để kết luận query hoặc migration tương thích với production MySQL.

## 4. Khởi động PostgreSQL bằng JUnit 5

Một cách trực tiếp là khai báo container bằng JUnit 5:

```java
@Testcontainers
@SpringBootTest
@AutoConfigureMockMvc
class PersonApiIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("spring_data_rest_test")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
```

Các thành phần:

- `@Testcontainers` bật tích hợp JUnit Jupiter.
- `@Container` đánh dấu container được quản lý theo lifecycle của test class.
- Container static thường được khởi động một lần cho class và dừng sau class.
- `@DynamicPropertySource` đăng ký JDBC URL và credentials động trước khi Spring tạo application context.
- `@SpringBootTest` khởi động Spring context đầy đủ.
- `@AutoConfigureMockMvc` cung cấp MockMvc để gửi request qua Spring MVC/Security stack mà không cần mở cổng HTTP thật.

Nếu muốn kiểm tra toàn bộ network stack qua cổng server thật, có thể dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và `TestRestTemplate` hoặc `WebTestClient`. MockMvc vẫn chạy được với database container thật; nó chỉ mô phỏng lớp HTTP client và servlet container ở mức test.

### Dùng @ServiceConnection

Với Spring Boot hỗ trợ service connections và phiên bản Testcontainers tương thích, cấu hình có thể ngắn hơn:

```java
@Testcontainers
@SpringBootTest
@AutoConfigureMockMvc
class PersonApiIntegrationTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
}
```

Spring Boot tự tạo connection details cho database container. Chọn một cách cấu hình rõ ràng theo phiên bản dự án; không cần đồng thời khai báo dynamic properties trùng lặp nếu service connection đã cung cấp đủ cấu hình.

## 5. Chạy migration trên database test

Test hợp đồng phải kiểm tra schema mà ứng dụng thực sự sử dụng. Nếu production dùng Flyway hoặc Liquibase, để migration chạy trên container test thay vì tự tạo schema bằng Hibernate.

Ví dụ cấu hình:

```properties
spring.jpa.hibernate.ddl-auto=validate
spring.flyway.enabled=true
spring.jpa.open-in-view=false
```

Với cấu hình này:

- Flyway áp dụng migration lên database trống của container.
- Hibernate kiểm tra mapping khớp schema.
- Test sẽ phát hiện migration thiếu cột, sai kiểu hoặc constraint.
- `open-in-view=false` giúp test phát hiện serialization vô tình truy cập lazy association ngoài transaction.

Nếu dự án dùng Liquibase, cấu hình Liquibase thay cho Flyway và bảo đảm changelog chạy trước test. Tránh để `ddl-auto=create-drop` âm thầm tạo schema khác với production; cách đó có thể khiến test pass trong khi migration thật bị lỗi.

Có thể kiểm tra migration trực tiếp qua Flyway/Liquibase metadata hoặc xác nhận các hành vi cần thiết như unique constraint và foreign key bằng API test.

## 6. Chuẩn bị repository và entity mẫu

Ví dụ Person có Address:

```java
@Entity
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String firstName;

    @Column(nullable = false, length = 120)
    private String lastName;

    @ManyToOne(fetch = FetchType.LAZY)
    private Address address;

    protected Person() {
    }

    public Person(String firstName, String lastName) {
        this.firstName = firstName;
        this.lastName = lastName;
    }

    // Getters và setters
}
```

Repository:

```java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    List<Person> findByLastName(@Param("name") String lastName);
}
```

Ví dụ đã lược bỏ Address và migration để tập trung vào test. Trong dự án thật, khai báo constraint, ID generation và association theo schema production. Đặt repository path và relation rõ ràng để HTTP contract có thể được kiểm tra.

## 7. Kiểm tra API root và collection contract

Một contract test nên bắt đầu từ API root và kiểm tra media type cùng các link mà client cần khám phá.

```java
@Autowired
MockMvc mvc;

@Test
void apiRootPublishesPeopleAndProfileLinks() throws Exception {
    mvc.perform(get("/")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.people.href").exists())
        .andExpect(jsonPath("$._links.profile.href").exists());
}
```

Sau đó kiểm tra collection:

```java
@Test
void peopleCollectionUsesHalAndExposesSearch() throws Exception {
    mvc.perform(get("/people")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._links.profile.href").exists())
        .andExpect(jsonPath("$._links.search.href").exists())
        .andExpect(jsonPath("$.page.size").exists());
}
```

Các assertion nên phản ánh contract ứng dụng cam kết. Nếu repository không export query methods thì không bắt buộc có search link. Nếu API root hoặc base path được tùy chỉnh, dùng path thực tế của ứng dụng.

## 8. Kiểm tra POST, Location và dữ liệu đã persist

Một test tạo resource cần xác minh cả response HTTP lẫn dữ liệu database. Ví dụ:

```java
@Test
void postCreatesPersonAndReturnsLocation() throws Exception {
    String body = """
        {
          "firstName": "An",
          "lastName": "Nguyen"
        }
        """;

    MvcResult result = mvc.perform(post("/people")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaTypes.HAL_JSON)
            .content(body))
        .andExpect(status().isCreated())
        .andExpect(header().exists(HttpHeaders.LOCATION))
        .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.self.href").exists())
        .andReturn();

    String location = result.getResponse()
        .getHeader(HttpHeaders.LOCATION);

    assertThat(location).isNotBlank();

    URI itemUri = URI.create(location);
    String path = itemUri.getPath();

    mvc.perform(get(path).accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.firstName").value("An"))
        .andExpect(jsonPath("$.lastName").value("Nguyen"));
}
```

Test này kiểm tra:

- POST collection trả `201 Created`.
- Response có `Location` trỏ tới resource mới.
- Representation trả HAL và có self link.
- GET theo resource URI vừa nhận trả dữ liệu đã lưu.

Để xác minh trực tiếp persistence, có thể inject `PersonRepository` và query theo dữ liệu sau khi flush/clear persistence context. Tuy nhiên, kiểm tra lại qua GET hữu ích vì nó xác minh đường serialize và resource lookup mà client thực sự sử dụng.

Không hard-code ID tăng dần hoặc Location cụ thể như `/people/1`; ID có thể thay đổi theo database sequence và test order.

## 9. Kiểm tra GET item, PUT/PATCH và DELETE

Một HTTP contract test nên xác minh semantics của từng operation được export.

Ví dụ GET item sau khi tạo:

```java
@Test
void itemResourceContainsSelfLink() throws Exception {
    Person person = personRepository.saveAndFlush(
        new Person("Mai", "Tran"));

    mvc.perform(get("/people/" + person.getId())
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.firstName").value("Mai"))
        .andExpect(jsonPath("$._links.self.href").exists());
}
```

Ví dụ PATCH:

```java
@Test
void patchUpdatesOnlyRequestedProperty() throws Exception {
    Person person = personRepository.saveAndFlush(
        new Person("Mai", "Tran"));

    mvc.perform(patch("/people/" + person.getId())
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaTypes.HAL_JSON)
            .content("""
                {"firstName":"Linh"}
                """))
        .andExpect(status().isNoContent());

    Person updated = personRepository.findById(person.getId())
        .orElseThrow();

    assertThat(updated.getFirstName()).isEqualTo("Linh");
    assertThat(updated.getLastName()).isEqualTo("Tran");
}
```

Status code cụ thể phụ thuộc Spring Data REST version, configuration và representation. Dựa trên contract ứng dụng đang sử dụng; nếu framework trả `200` với body thay vì `204`, assertion phải phản ánh hành vi được công bố và kiểm thử thực tế.

Ví dụ DELETE:

```java
@Test
void deleteRemovesResource() throws Exception {
    Person person = personRepository.saveAndFlush(
        new Person("An", "Nguyen"));

    mvc.perform(delete("/people/" + person.getId()))
        .andExpect(status().isNoContent());

    assertThat(personRepository.existsById(person.getId())).isFalse();
}
```

Không kiểm tra một status code theo suy đoán. Đối chiếu Spring Data REST version, cấu hình và response contract thực tế của endpoint.

## 10. Kiểm tra query resource và tham số

Query methods được export tạo search resource. Test nên kiểm tra cả link khám phá và kết quả query:

```java
@Test
void searchByLastNameReturnsMatchingPeople() throws Exception {
    personRepository.saveAndFlush(new Person("An", "Nguyen"));
    personRepository.saveAndFlush(new Person("Mai", "Tran"));

    mvc.perform(get("/people/search/findByLastName")
            .param("name", "Nguyen")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$._embedded.people[0].lastName").value("Nguyen"));
}
```

Nếu kết quả collection có thể rỗng hoặc nhiều phần tử, đừng dựa vào index cố định. Dùng JSONPath phù hợp để kiểm tra tập kết quả hoặc kiểm tra count và nội dung từng item. Test nên tạo dữ liệu fixture riêng để kết quả không phụ thuộc thứ tự thực thi test khác.

## 11. Kiểm tra association link và persistence

Với association, test cần xác minh link relation xuất hiện và thao tác liên kết thực sự cập nhật database.

Ví dụ tạo Address và Person, rồi kiểm tra association link:

```java
@Test
void personPublishesAddressAssociationLink() throws Exception {
    Address address = addressRepository.saveAndFlush(
        new Address("District 1"));

    Person person = personRepository.saveAndFlush(
        new Person("An", "Nguyen"));
    person.setAddress(address);
    personRepository.saveAndFlush(person);

    mvc.perform(get("/people/" + person.getId())
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.address.href").exists());
}
```

Nếu contract cho phép cập nhật association qua URI, gửi request đúng media type và payload mà endpoint association yêu cầu. Sau request, đọc lại entity qua repository hoặc GET association để xác nhận foreign key đã thay đổi.

Không chỉ kiểm tra link có tồn tại; link phải trỏ tới endpoint hoạt động, association phải được lưu đúng và authorization phải được áp dụng. Với lazy association, kiểm tra serialization trong cấu hình production tương tự, đặc biệt khi `open-in-view=false`.

## 12. Kiểm tra validation và database constraints

Bean Validation và database constraint bảo vệ các lớp khác nhau. Có thể kiểm tra một request thiếu field bắt buộc:

```java
@Test
void invalidPersonIsRejected() throws Exception {
    mvc.perform(post("/people")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaTypes.HAL_JSON)
            .content("""
                {"lastName":"Nguyen"}
                """))
        .andExpect(status().isBadRequest());
}
```

Nếu unique constraint là một phần contract, tạo hai resource có cùng giá trị unique và xác minh request thứ hai bị từ chối theo exception mapping của ứng dụng. Không phụ thuộc message SQL hoặc tên constraint nội bộ trong response công khai.

Để chứng minh database constraint thật sự tồn tại, có thể kiểm tra trực tiếp bằng repository/JDBC hoặc thử thao tác ghi ở transaction riêng. Khi kiểm tra lỗi persistence, cần xử lý transaction đã đánh dấu rollback-only và tránh để lỗi của test làm hỏng context dùng chung.

Validation test chỉ qua HTTP có thể bị chặn ở Bean Validation trước khi chạm database. Vì vậy, nếu mục tiêu là kiểm tra unique index/foreign key, hãy có test persistence riêng chứng minh database constraint được áp dụng.

## 13. Transaction và dữ liệu test độc lập

Test có thể làm bẩn database nếu dữ liệu được tạo mà không được dọn. Một số lựa chọn:

- Dùng `@Transactional` trên test để rollback các thay đổi trong cùng transaction.
- Xóa fixture bằng repository trước/sau test.
- Dùng database hoặc schema riêng cho mỗi test class/suite.
- Dùng container riêng theo class hoặc suite.
- Dùng unique test data để tránh xung đột khi chạy song song.

Cẩn thận với `@Transactional` trên MockMvc integration test: request HTTP có thể được xử lý trong thread và transaction riêng tùy test setup. Transaction của test không nhất thiết bao quanh request server theo cách bạn mong đợi, đặc biệt khi dùng RANDOM_PORT. Hãy xác minh dữ liệu được commit/rollback theo lifecycle thực tế và chủ động cleanup nếu cần.

Với static container, database thường được chia sẻ giữa các test trong class. Dữ liệu fixture phải được làm sạch hoặc định danh duy nhất. Tránh phụ thuộc thứ tự test và không dùng sequence ID cố định.

## 14. Kiểm tra contract với server chạy trên cổng thật

MockMvc chạy qua Spring MVC stack trong process test, nhưng không kiểm tra network socket hoặc toàn bộ HTTP server runtime. Với endpoint cần xác minh HTTP thực tế, dùng RANDOM_PORT:

```java
@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PersonHttpContractTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @LocalServerPort
    int port;

    @Test
    void rootRespondsWithHal() {
        given()
            .baseUri("http://localhost")
            .port(port)
            .accept("application/hal+json")
        .when()
            .get("/")
        .then()
            .statusCode(200)
            .contentType(containsString("application/hal+json"));
    }
}
```

Ví dụ dùng RestAssured; cần dependency tương ứng và cấu hình static import. Có thể dùng `TestRestTemplate` hoặc `WebTestClient` thay thế. Cổng được Spring chọn ngẫu nhiên, lấy từ `@LocalServerPort`.

Dùng test cổng thật cho một số contract quan trọng, chẳng hạn CORS, filter chain, cookie, redirect, header và network integration. MockMvc thường nhanh hơn và phù hợp với phần lớn endpoint tests.

## 15. Kiểm tra migration và schema drift

Một database container mới là cơ hội kiểm tra toàn bộ migration từ đầu:

1. Khởi động database rỗng.
2. Cho Flyway/Liquibase chạy tất cả migration.
3. Khởi động JPA với `ddl-auto=validate`.
4. Thực hiện một số thao tác API tạo, đọc, cập nhật và xóa.
5. Kiểm tra index, foreign key, unique constraint và default cần thiết qua hành vi hoặc metadata database.

Có thể thêm test xác nhận phiên bản migration cuối đã được áp dụng hoặc schema có bảng/constraint quan trọng. Tránh kiểm tra quá nhiều chi tiết implementation không thuộc contract; ưu tiên các constraint bảo vệ tính toàn vẹn nghiệp vụ.

Nếu production migration có extension, collation, enum hoặc timezone behavior riêng, cấu hình container tương ứng. Database image tag nên được pin rõ ràng để build hôm nay và ngày mai dùng cùng engine version.

## 16. Testcontainers với CI

Để test chạy ổn định trong CI:

- Dùng runner có Docker socket/runtime hoạt động.
- Pin image tag cụ thể; không dùng tag trôi nổi như `latest`.
- Đặt timeout readiness hợp lý và dùng wait strategy nếu database cần thời gian khởi động.
- Tránh hard-code port host.
- Không chia sẻ database container giữa pipeline không liên quan.
- Giới hạn parallelism nếu tài nguyên CI nhỏ.
- Dùng credentials giả dành riêng cho test; không đưa secret production vào container.
- Thu thập log container khi startup hoặc migration thất bại.
- Tách unit test nhanh và integration test cần Docker để developer có thể chạy phù hợp.

Ví dụ lệnh Maven:

```bash
mvn test
```

Nếu integration test được đặt ở Maven Failsafe, dùng lifecycle:

```bash
mvn verify
```

Đặt naming convention như `*IT` và cấu hình Failsafe nếu muốn chạy integration suite riêng. Không để test cần Docker bị chạy ngầm trong mọi unit-test profile nếu dự án có môi trường không hỗ trợ container.

## 17. Những lỗi thường gặp

**Container không khởi động**

Kiểm tra Docker runtime, quyền truy cập socket, image pull, resource limit và log container. Không sửa bằng cách chuyển sang H2 nếu mục tiêu test là database production thật.

**Spring kết nối database trước khi container sẵn sàng**

Dùng `@Testcontainers`/container lifecycle hoặc service connection đúng cách; bảo đảm dynamic properties được đăng ký trước khi application context khởi tạo.

**Test pass với H2 nhưng fail trên PostgreSQL**

Đây là lý do dùng engine thật. Kiểm tra SQL dialect, reserved word, case sensitivity, type mapping, sequence, JSON column và migration.

**Test phụ thuộc thứ tự**

Làm sạch fixture, dùng ID/data duy nhất và không giả định sequence bắt đầu từ 1.

**MockMvc test rollback nhưng dữ liệu vẫn tồn tại**

Xem xét transaction boundary giữa test thread và request processing. Dùng cleanup tường minh hoặc transaction test strategy đã xác minh.

**Migration không chạy trong test**

Kiểm tra Flyway/Liquibase có bị disable bởi test profile, datasource có trỏ vào container, và schema location/changelog path đúng không.

**Response HAL thay đổi theo phiên bản**

Pin phiên bản Spring Boot/Spring Data REST và viết assertion vào contract mà client cần, tránh phụ thuộc thứ tự JSON property hoặc nội dung implementation không ổn định.

**Container test quá chậm**

Dùng static container cho test class/suite khi an toàn, tái sử dụng application context, giảm số lượng test end-to-end và giữ phần logic thuần ở unit test. Chỉ bật reusable containers khi môi trường developer/CI có quy tắc cleanup phù hợp.

## 18. Bộ kiểm tra contract tối thiểu nên có

Với một repository Spring Data REST, integration suite nên bao phủ các hành vi quan trọng:

1. API root trả HAL và công bố collection/profile links.
2. Collection trả đúng media type, self/search/profile links và page metadata.
3. POST trả status và Location phù hợp; resource mới đọc lại được.
4. GET item trả property và self link.
5. PATCH/PUT thay đổi dữ liệu theo semantics đã công bố.
6. DELETE xóa resource và xử lý item không tồn tại đúng contract.
7. Search resource và query parameter trả đúng tập kết quả.
8. Association link có thể điều hướng và thay đổi association được persist.
9. Validation từ chối payload không hợp lệ.
10. Database constraint bảo vệ unique/foreign key và migration tạo schema đúng.
11. Authorization/CSRF được kiểm tra theo security mode của ứng dụng.
12. Conditional headers hoặc pagination được kiểm tra nếu là một phần contract client sử dụng.

Không cần kiểm tra mọi endpoint qua cổng thật. Chọn một số luồng đại diện để xác minh server runtime; dùng MockMvc + Testcontainers cho phần lớn integration tests.

## Tóm tắt

- Testcontainers cung cấp database thật tạm thời để kiểm tra Spring Data REST từ HTTP đến persistence.
- Dùng image/version gần production và lấy JDBC URL/credentials động từ container.
- Kết hợp `@SpringBootTest`, `@Testcontainers`, `@Container`, `@DynamicPropertySource` hoặc `@ServiceConnection`.
- Chạy Flyway/Liquibase trên database trống và dùng `ddl-auto=validate` để phát hiện schema drift.
- Kiểm tra HAL links, media type, status code, Location, query, association và dữ liệu đã persist.
- MockMvc vẫn có thể dùng database container thật; RANDOM_PORT dùng để kiểm tra thêm HTTP server/network behavior.
- Quản lý transaction và fixture độc lập; không phụ thuộc thứ tự test hoặc ID cố định.
- Dùng database thật cho SQL dialect, migration, mapping, transaction và constraints; giữ unit test cho logic thuần.
- CI cần Docker-compatible runtime, image tag pin, readiness strategy và log container khi lỗi.

## Tài liệu tham khảo

- [Testcontainers for Java — JUnit 5 Quickstart](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [Testcontainers — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/)
- [Spring Boot — Testcontainers Support](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Spring Boot — Testing Spring Applications](https://docs.spring.io/spring-boot/reference/testing/)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Flyway — Migrations](https://documentation.red-gate.com/flyway)
