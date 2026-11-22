# Chuẩn bị dữ liệu mẫu và tách biệt dữ liệu kiểm thử

Kiểm thử Spring Data Relational R2DBC chỉ đáng tin cậy khi database bắt đầu từ trạng thái đã biết và các test không làm thay đổi dữ liệu mà test khác đang sử dụng. Dữ liệu mẫu (seed data) cung cấp những bản ghi cần thiết để kiểm thử; fixture tạo dữ liệu phù hợp với từng tình huống; còn chiến lược cô lập bảo đảm một test có thể chạy độc lập, lặp lại và chạy song song mà không phụ thuộc thứ tự.

Với R2DBC, dữ liệu kiểm thử còn phải được thiết lập và dọn dẹp theo reactive flow. Một truy vấn trả về `Mono` hoặc `Flux` chỉ chạy khi được subscribe. Nếu seed data bằng một subscription tách rời, test có thể bắt đầu trước khi dữ liệu được ghi xong. Nếu một test giữ transaction hoặc connection quá lâu, test khác có thể chờ pool hoặc nhìn thấy trạng thái không mong muốn.

Bài học này trình bày cách chuẩn bị schema và dữ liệu mẫu, lựa chọn script SQL hay fixture Java, sử dụng database riêng hoặc Testcontainers, cô lập dữ liệu giữa các test, xử lý transaction rollback trong kiểm thử reactive, chạy test song song và bảo vệ dữ liệu production.

## 1. Seed data, fixture và test data có vai trò khác nhau

Các khái niệm thường được dùng gần nhau nhưng có mục đích riêng:

- **Schema:** cấu trúc database gồm bảng, cột, khóa, constraint, index và quan hệ.
- **Seed data:** tập dữ liệu ban đầu được nạp để tạo môi trường có thể sử dụng hoặc kiểm thử.
- **Fixture:** dữ liệu được chuẩn bị có chủ đích cho một test hoặc nhóm test cụ thể.
- **Test database:** database riêng dành cho kiểm thử, có thể tạo mới và xóa bỏ mà không ảnh hưởng dữ liệu khác.
- **Test isolation:** cách ngăn thay đổi từ test này ảnh hưởng kết quả test khác.

Ví dụ một test kiểm tra tìm đơn hàng theo khách hàng có thể cần:

1. Một khách hàng.
2. Hai đơn hàng thuộc khách hàng đó.
3. Một đơn hàng thuộc khách hàng khác để xác nhận điều kiện lọc.
4. Các trạng thái và timestamp có giá trị xác định.

Fixture nên thể hiện rõ dữ liệu nào phục vụ assertion. Không cần nạp hàng nghìn bản ghi cho một test chỉ kiểm tra một truy vấn đơn giản.

Một môi trường test tốt có ba đặc điểm:

- **Deterministic:** cùng fixture và cùng code tạo ra kết quả có thể dự đoán.
- **Repeatable:** chạy test nhiều lần không làm dữ liệu tích lũy hoặc thay đổi kết quả.
- **Isolated:** test không phụ thuộc dữ liệu do test khác tạo hoặc thứ tự test chạy.

## 2. Tách database kiểm thử khỏi development và production

Không dùng chung database production với test. Test có thể insert, update, delete, truncate hoặc chạy migration; một lỗi cấu hình có thể làm mất dữ liệu thật.

Nên có cấu hình riêng cho từng môi trường:

~~~text
src/main/resources/
    application.yml
    application-dev.yml
    application-test.yml

src/test/resources/
    schema.sql
    data.sql
    application-test.yml
~~~

Ví dụ cấu hình test:

~~~yaml
spring:
  config:
    activate:
      on-profile: test

  r2dbc:
    url: r2dbc:postgresql://localhost:55432/orders_test
    username: test_user
    password: test_password

  sql:
    init:
      mode: always
      schema-locations: classpath:schema.sql
      data-locations: classpath:data.sql
      continue-on-error: false
~~~

Đây là ví dụ cho PostgreSQL và phiên bản Spring Boot có hỗ trợ R2DBC script initialization. URL, driver và thuộc tính cần điều chỉnh theo database và phiên bản Boot của dự án.

Không đặt URL test trong cấu hình mặc định nếu ứng dụng có thể khởi chạy bằng profile production. Hãy kiểm tra profile được kích hoạt và nguồn cấu hình cuối cùng trước khi chạy test.

### 2.1. Dùng profile test có kiểm soát

Có thể kích hoạt profile test trong test class:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class CustomerRepositoryIntegrationTest {
}
~~~

Profile chỉ giúp chọn cấu hình. Nó không tự bảo đảm database được cô lập. Nếu `application-test.yml` vô tình trỏ tới database dùng chung hoặc production, các lệnh dọn dữ liệu vẫn có thể tác động dữ liệu thật.

Nên dùng các biện pháp bổ sung:

- Dùng database có tên riêng như `orders_test`.
- Dùng user database chỉ có quyền trên database test.
- Dùng container hoặc database ephemeral.
- Không đưa credential production vào test configuration.
- Kiểm tra host, database name và profile trước khi chạy destructive setup.
- Không dùng bản dump chứa dữ liệu cá nhân production làm fixture.

## 3. Chuẩn bị schema bằng SQL script

Spring Boot có thể chạy script khởi tạo schema khi ứng dụng bắt đầu. Với R2DBC, script initialization sử dụng cơ chế tương thích R2DBC do Spring Boot cấu hình.

Ví dụ `schema.sql`:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(200) NOT NULL UNIQUE,
    full_name VARCHAR(150) NOT NULL
);

CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id) REFERENCES customer(id)
);
~~~

Script schema nên tạo đúng các thành phần mà ứng dụng cần:

- Bảng và cột.
- Primary key và foreign key.
- Unique, not-null và check constraint.
- Index cần thiết cho truy vấn.
- Sequence hoặc cấu trúc sinh ID nếu database yêu cầu.
- View hoặc function nếu test cần chúng.

Không chỉ tạo bảng tối giản để test chạy qua nếu ứng dụng production dựa vào constraint hoặc index quan trọng. Test schema nên phản ánh schema được quản lý bằng migration.

### 3.1. Thứ tự tạo và xóa bảng

Khi có foreign key, tạo bảng được tham chiếu trước, sau đó tạo bảng phụ thuộc. Khi dọn dữ liệu, xóa bảng con trước bảng cha nếu không dùng cascade.

Ví dụ:

~~~text
CREATE customer
      |
      v
CREATE purchase_order
      |
      v
INSERT customer
      |
      v
INSERT purchase_order
~~~

Thứ tự cleanup thường đảo lại:

~~~text
DELETE purchase_order
      |
      v
DELETE customer
~~~

Nếu schema có nhiều quan hệ, lập thứ tự theo dependency graph. Không thêm `ON DELETE CASCADE` chỉ để việc dọn test thuận tiện nếu hành vi production không yêu cầu cascade.

### 3.2. Không để script tiếp tục khi lỗi ngoài dự kiến

Cấu hình:

~~~yaml
spring:
  sql:
    init:
      continue-on-error: false
~~~

giúp ứng dụng dừng khi script thất bại. Nếu bỏ qua lỗi, test có thể chạy với schema hoặc seed data chỉ được tạo một phần và tạo ra lỗi khó hiểu ở những bước sau.

## 4. Nạp dữ liệu mẫu bằng data.sql

Ví dụ `data.sql`:

~~~sql
INSERT INTO customer (id, email, full_name)
VALUES
    (1001, 'an@example.test', 'Nguyen An'),
    (1002, 'binh@example.test', 'Tran Binh');

INSERT INTO purchase_order
    (id, customer_id, order_number, status, created_at)
VALUES
    (2001, 1001, 'ORD-TEST-001', 'OPEN', TIMESTAMP '2026-01-10 09:00:00'),
    (2002, 1001, 'ORD-TEST-002', 'CLOSED', TIMESTAMP '2026-01-11 10:00:00'),
    (2003, 1002, 'ORD-TEST-003', 'OPEN', TIMESTAMP '2026-01-12 11:00:00');
~~~

Seed data có ID và giá trị cố định giúp test dễ đọc và dễ kiểm tra. Email dùng miền dành cho test, chẳng hạn `example.test`, để tránh vô tình gửi thông tin tới địa chỉ thật.

Một bộ seed data tốt thường:

- Có số lượng nhỏ và dễ hiểu.
- Bao gồm các trường hợp hợp lệ và các trạng thái cần kiểm tra.
- Tuân thủ foreign key và unique constraint.
- Dùng timestamp cố định, không phụ thuộc giờ hiện tại.
- Không chứa bí mật, token hoặc dữ liệu cá nhân thật.
- Có thể nạp lại sau khi database được reset.

### 4.1. Seed data khác fixture theo từng test

`data.sql` phù hợp với dữ liệu nền dùng chung cho cả test suite, ví dụ một số bảng danh mục hoặc cấu hình tham chiếu. Fixture theo test nên tạo trong test hoặc fixture factory để thể hiện chính xác điều kiện của scenario.

Nếu mọi test cùng dùng một tập dữ liệu lớn trong `data.sql`, chúng dễ phụ thuộc vào trạng thái chung. Một test sửa hoặc xóa bản ghi có thể làm test khác thất bại.

Không dùng seed data toàn cục để thay thế mọi fixture riêng.

## 5. Cấu hình SQL initialization của Spring Boot

Một số thuộc tính thường dùng:

| Thuộc tính | Mục đích |
|---|---|
| `spring.sql.init.mode` | Chọn khi nào chạy script: `embedded`, `always` hoặc `never` |
| `spring.sql.init.schema-locations` | Vị trí script tạo schema |
| `spring.sql.init.data-locations` | Vị trí script nạp dữ liệu |
| `spring.sql.init.platform` | Hậu tố platform cho script theo database |
| `spring.sql.init.continue-on-error` | Có tiếp tục khi script lỗi hay không |
| `spring.sql.init.separator` | Ký tự phân tách statement nếu cần tùy chỉnh |

Ví dụ:

~~~yaml
spring:
  sql:
    init:
      mode: always
      platform: postgresql
      schema-locations: classpath:schema-postgresql.sql
      data-locations: classpath:data-postgresql.sql
      continue-on-error: false
~~~

Tên và khả năng của các thuộc tính cần xác nhận theo phiên bản Spring Boot đang dùng. Đặc biệt, không nhầm script initialization với Flyway hoặc Liquibase migration.

### 5.1. Khi nào dùng mode embedded, always và never?

- `embedded`: chạy script tự động trong môi trường database embedded theo quy tắc Boot.
- `always`: yêu cầu chạy script cả với database không embedded.
- `never`: không chạy script initialization.

Trong test dùng PostgreSQL container, thường cần `always` nếu muốn Spring Boot nạp `schema.sql` và `data.sql`. Trong production dùng migration tool, thường không muốn script khởi tạo đơn giản chạy mỗi lần ứng dụng khởi động.

Đừng đặt `mode: always` trong cấu hình mặc định dùng cho mọi profile nếu script có lệnh `DROP`, `TRUNCATE` hoặc tạo lại bảng. Hãy giới hạn trong profile test và xác nhận cấu hình được chọn.

## 6. Dùng migration thay vì duy trì schema test riêng

Trong dự án thật, schema thường được quản lý bằng Flyway hoặc Liquibase. Test nên xác nhận ứng dụng hoạt động với schema được tạo bởi cùng migration mà production sử dụng.

Ví dụ cấu trúc Flyway:

~~~text
src/main/resources/db/migration/
    V1__create_customer.sql
    V2__create_purchase_order.sql
    V3__add_order_status_index.sql
~~~

Mỗi migration bổ sung hoặc thay đổi schema theo phiên bản. Test database được tạo mới rồi chạy toàn bộ migration để kiểm tra migration có thể áp dụng từ đầu.

Flyway và Liquibase truyền thống thường sử dụng JDBC để quản lý migration. Nếu ứng dụng runtime chỉ dùng R2DBC, có thể cần thêm JDBC driver và datasource dành cho migration. Đây là hai đường kết nối khác nhau:

~~~text
Application queries
      |
      v
R2DBC driver
      |
      v
Database

Schema migrations
      |
      v
JDBC migration connection
      |
      v
Same database
~~~

Không mặc định rằng Flyway sẽ dùng R2DBC chỉ vì ứng dụng khai báo `spring.r2dbc.*`.

### 6.1. Chọn một nguồn quản lý schema chính

Tránh để `schema.sql`, Hibernate DDL auto và Flyway/Liquibase cùng thay đổi schema theo những cách không thống nhất.

Một cách tổ chức phổ biến:

- Migration tool là nguồn sự thật của schema.
- Test chạy migration trên database rỗng.
- Test fixture chỉ nạp dữ liệu, không tự tạo lại cấu trúc bảng.
- Production cũng chạy cùng migration theo quy trình triển khai.

Nếu dùng script initialization cho một bài tập hoặc ứng dụng nhỏ, hãy giữ script đó nhất quán giữa các môi trường và không chạy đồng thời một công cụ khác cũng tạo schema.

## 7. Tạo fixture bằng Java cho từng test

Với test cần dữ liệu khác nhau, Java fixture factory dễ biểu đạt ý định hơn một file SQL lớn.

Ví dụ builder đơn giản:

~~~java
public final class CustomerFixtures {

    private CustomerFixtures() {
    }

    public static Customer customer(String email, String name) {
        Customer customer = new Customer();
        customer.setEmail(email);
        customer.setFullName(name);
        return customer;
    }

    public static Customer defaultCustomer() {
        return customer("fixture@example.test", "Fixture Customer");
    }
}
~~~

Fixture factory nên cung cấp các giá trị mặc định hợp lệ nhưng cho phép test ghi đè trường quan trọng.

Ví dụ:

~~~java
@Test
void findsOrdersForCustomer() {
    Customer customer = CustomerFixtures.customer(
            "orders@example.test",
            "Order Test Customer");

    Mono<List<PurchaseOrder>> scenario =
            customerRepository.save(customer)
                    .flatMap(saved ->
                            orderRepository.saveAll(List.of(
                                    OrderFixtures.openOrder(saved.getId()),
                                    OrderFixtures.closedOrder(saved.getId())))
                                    .collectList());

    StepVerifier.create(scenario)
            .assertNext(orders ->
                    assertThat(orders).hasSize(2))
            .verifyComplete();
}
~~~

Ví dụ này nối việc tạo customer và order trong cùng reactive chain. Test không bắt đầu assertion trước khi fixture hoàn tất.

Các fixture factory nên tránh che giấu quá nhiều hành vi. Khi test cần kiểm tra một trạng thái đặc biệt, hãy để giá trị đó hiển thị ngay trong test.

### 7.1. Dùng dữ liệu duy nhất giữa các test

Nếu test chạy song song hoặc dùng chung database, fixture cố định như `fixture@example.test` có thể gây duplicate key.

Có thể dùng một ID/namespace riêng cho test:

~~~java
String email = "customer-" + UUID.randomUUID() + "@example.test";
~~~

Giá trị ngẫu nhiên chỉ nên dùng cho trường không nằm trong assertion cố định hoặc được giữ lại để assertion. Không dùng random timestamp hoặc random business state nếu điều đó làm test khó tái hiện.

Một lựa chọn khác là mỗi test có database/schema riêng để có thể dùng dữ liệu cố định mà không xung đột.

## 8. Dọn dữ liệu sau mỗi test

Dữ liệu test cần được xóa hoặc database cần được reset để test tiếp theo bắt đầu từ trạng thái đã biết.

Các chiến lược phổ biến:

| Chiến lược | Khi phù hợp | Hạn chế |
|---|---|---|
| Rollback transaction | Tất cả thao tác test nằm trong cùng transaction | Reactive test transaction cần cấu hình đúng; commit độc lập không bị rollback |
| DELETE theo fixture/test ID | Test chỉ tạo một nhóm bản ghi xác định | Cần xóa đúng thứ tự FK |
| TRUNCATE bảng | Database test riêng và có thể xóa toàn bộ dữ liệu | Có thể ảnh hưởng test song song dùng chung database |
| Tạo database/container mới | Cần cô lập mạnh và schema sạch | Tốn thời gian khởi tạo |
| Tạo schema riêng | Nhiều test suite có thể dùng chung server | Cần quản lý search path, quyền và cleanup |

Ví dụ cleanup bằng SQL:

~~~java
Mono<Void> cleanDatabase() {
    return databaseClient.sql("DELETE FROM purchase_order")
            .then()
            .then(databaseClient.sql("DELETE FROM customer").then());
}
~~~

Đoạn code minh họa thứ tự xóa bảng con trước bảng cha. API cụ thể có thể cần điều chỉnh theo phiên bản `DatabaseClient`; có thể dùng `rowsUpdated()` nếu muốn kiểm tra số hàng bị xóa.

Không xóa dữ liệu theo email chung nếu nhiều test có thể tạo cùng email. Dùng ID hoặc namespace thuộc test đó để cleanup chính xác.

### 8.1. Cleanup phải được await

Không làm như sau:

~~~java
@AfterEach
void cleanup() {
    databaseClient.sql("DELETE FROM customer")
            .fetch()
            .rowsUpdated()
            .subscribe();
}
~~~

`subscribe()` tạo một luồng thực thi tách rời. JUnit có thể bắt đầu test kế tiếp trước khi DELETE hoàn tất.

Thay vào đó, hãy dùng cơ chế test lifecycle có hỗ trợ reactive completion hoặc nối cleanup vào publisher của test. Với JUnit `@AfterEach` đồng bộ, phương thức không tự chờ một `Mono` được trả về; đừng giả định chỉ cần return `Mono<Void>` từ lifecycle method là JUnit sẽ subscribe.

Có thể viết test helper trả về `Mono<Void>` và nối cleanup vào cuối publisher test, hoặc dùng extension phù hợp. Nếu buộc phải chặn trong test infrastructure, chỉ làm ở ranh giới test có chủ đích, không đưa blocking vào code ứng dụng reactive.

## 9. Tách biệt bằng database riêng và Testcontainers

Testcontainers cho phép chạy database thật trong container trong vòng đời test. Điều này giúp test dùng đúng engine và driver thay vì chỉ dựa vào H2 hoặc mock.

Ví dụ PostgreSQL container:

~~~java
@Testcontainers
@DataR2dbcTest
@ActiveProfiles("test")
class CustomerRepositoryTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("orders_test")
                    .withUsername("test")
                    .withPassword("test");

    @DynamicPropertySource
    static void configureR2dbc(DynamicPropertyRegistry registry) {
        registry.add("spring.r2dbc.url", () ->
                "r2dbc:postgresql://"
                        + postgres.getHost()
                        + ":"
                        + postgres.getMappedPort(5432)
                        + "/"
                        + postgres.getDatabaseName());

        registry.add("spring.r2dbc.username", postgres::getUsername);
        registry.add("spring.r2dbc.password", postgres::getPassword);
    }
}
~~~

Đây là mẫu minh họa; annotation test slice, dependency Testcontainers và driver phải khớp phiên bản Spring Boot/Spring Data của dự án. Nếu test cần toàn bộ application context, có thể dùng `@SpringBootTest` thay cho `@DataR2dbcTest`.

Container cung cấp database thật nhưng không tự làm sạch dữ liệu giữa các test nếu container được chia sẻ. Vẫn cần reset dữ liệu hoặc cấp database/schema riêng cho mỗi test.

### 9.1. Dùng container theo class hay theo test?

- **Một container cho cả test suite:** khởi động nhanh hơn, nhưng các test dùng chung database và cần cleanup nghiêm ngặt.
- **Một container cho mỗi class:** cô lập giữa các class, thời gian khởi động cao hơn.
- **Một container cho mỗi test:** cô lập mạnh, nhưng có thể rất chậm với suite lớn.
- **Một database/schema riêng trong container dùng chung:** cân bằng tốc độ và isolation nếu việc tạo/xóa schema được quản lý cẩn thận.

Nếu dùng container static được chia sẻ, không để các test sửa cùng một hàng hoặc truncate cùng bảng đồng thời. Test parallel phải có namespace/database/schema riêng hoặc phải tắt parallel execution cho nhóm test dùng chung dữ liệu.

### 9.2. Kết nối R2DBC không phải JDBC URL

`PostgreSQLContainer.getJdbcUrl()` trả URL JDBC như `jdbc:postgresql://...`. R2DBC cần URL theo scheme driver, ví dụ `r2dbc:postgresql://...`.

Không gán JDBC URL vào `spring.r2dbc.url`. Tương tự, Testcontainers JDBC URL dành cho migration không tự thay thế R2DBC URL runtime.

## 10. Dùng @DataR2dbcTest và @SpringBootTest

`@DataR2dbcTest` phù hợp khi chỉ muốn kiểm thử repository, mapping và cấu hình R2DBC cần thiết. Nó thường giới hạn application context vào các thành phần persistence và có thể cấu hình transaction/database test theo phiên bản Boot.

`@SpringBootTest` phù hợp khi test cần service, security, transaction configuration, converter hoặc nhiều bean trong application context.

| Annotation | Phạm vi |
|---|---|
| `@DataR2dbcTest` | Tập trung vào repository và persistence |
| `@SpringBootTest` | Khởi tạo application context đầy đủ |
| `@Testcontainers` | Quản lý container trong test |
| `@ActiveProfiles("test")` | Kích hoạt cấu hình test |
| `@DynamicPropertySource` | Đăng ký thuộc tính động từ container |

Không dùng `@SpringBootTest` cho mọi repository test nếu slice test đã đủ. Context đầy đủ khởi động chậm hơn và có thể kéo theo các dịch vụ không liên quan.

Cũng không giả định `@DataR2dbcTest` tự nạp đúng script hoặc tự reset dữ liệu. Hãy kiểm tra cấu hình initializer và chiến lược cleanup rõ ràng.

## 11. Transaction rollback trong reactive test

Trong test JDBC/imperative, `@Transactional` trên test thường được dùng để rollback dữ liệu sau mỗi test. Với R2DBC, transaction là reactive và được truyền qua Reactor Context. Không nên áp dụng máy móc giả định từ JDBC.

Cần xác nhận phiên bản Spring Test và cách test method được thực thi có hỗ trợ reactive transaction hay không. Một method test trả `Mono` không đồng nghĩa JUnit tự subscribe và chờ publisher đó; nhiều test cần dùng `StepVerifier` để kích hoạt và kiểm tra publisher.

### 11.1. Gắn transaction vào publisher

Có thể dùng `TransactionalOperator` trong test để kiểm soát transaction boundary:

~~~java
Mono<Void> scenario =
        transactionalOperator.transactional(
                customerRepository.save(customer)
                        .flatMap(saved ->
                                orderRepository.save(
                                        OrderFixtures.openOrder(saved.getId())))
                        .then());
~~~

Publisher được subscribe qua `StepVerifier` sẽ chạy trong transaction context mà operator tạo.

Nếu test cần xác nhận dữ liệu được commit và nhìn thấy từ connection khác, đừng đánh dấu rollback-only. Hãy để transaction hoàn tất bình thường rồi đọc lại bằng một thao tác độc lập.

### 11.2. Chủ động rollback bằng rollback-only

Nếu muốn test dữ liệu tạm thời và rollback khi hoàn tất, có thể dùng `execute`:

~~~java
Flux<Long> temporaryInsert =
        transactionalOperator.execute(status ->
                customerRepository.save(customer)
                        .map(Customer::getId)
                        .doOnNext(id -> status.setRollbackOnly()));
~~~

Sau khi publisher hoàn tất, transaction được rollback. Ví dụ này chỉ minh họa cách đánh dấu rollback-only; trong test thực tế cần chờ `StepVerifier` hoàn tất rồi kiểm tra từ một transaction khác rằng bản ghi không còn tồn tại.

Cách này chỉ có ý nghĩa khi repository tham gia cùng reactive transaction context. Một publisher được `subscribe()` tách riêng hoặc một thao tác dùng connection factory khác có thể không thuộc transaction đó.

### 11.3. Không phải mọi thay đổi đều được rollback

Các thao tác sau có thể không được hoàn tác cùng transaction đang test:

- Publisher đã subscribe tách rời.
- Thao tác dùng `ConnectionFactory` hoặc transaction manager khác.
- Lệnh commit độc lập qua `REQUIRES_NEW`.
- Gọi HTTP, gửi email, publish message hoặc ghi file.
- Database/driver có semantics DDL hoặc sequence riêng.

Sequence/identity có thể tiếp tục tăng sau rollback. Không viết test giả định ID tiếp theo luôn bằng một số cố định sau khi rollback.

## 12. Kiểm tra tính nhất quán của seed data và thứ tự fixture

Fixture có foreign key phải được tạo theo dependency order:

~~~java
Mono<Customer> customerMono =
        customerRepository.save(CustomerFixtures.defaultCustomer());

Mono<PurchaseOrder> orderMono =
        customerMono.flatMap(customer ->
                orderRepository.save(
                        OrderFixtures.openOrder(customer.getId())));
~~~

Nếu test cần nhiều hàng liên quan, dùng `flatMap` hoặc `then` để nối các bước. Không gọi `subscribe()` cho từng repository operation rồi giả định thứ tự insert.

Khi tạo nhiều hàng độc lập, có thể dùng `saveAll` hoặc `Flux.concat` nếu cần thứ tự. Dùng `flatMap` cho các insert đồng thời chỉ khi chúng không phụ thuộc nhau và driver/database có thể xử lý workload đó.

Nếu test cần xác nhận thứ tự hiển thị, đặt timestamp và sort key tường minh. Không dựa vào thứ tự database tự trả về khi query không có `ORDER BY`.

## 13. Tránh phụ thuộc vào ID tự sinh

Một lỗi phổ biến là fixture insert bản ghi rồi giả định ID sẽ luôn là 1, 2, 3. Sequence có thể tiếp tục tăng qua lần test, rollback hoặc container lifecycle khác nhau.

Thay vào đó:

- Lấy entity đã lưu và dùng ID do database trả về.
- Dùng natural key duy nhất nếu test cần truy vấn lại.
- Không phụ thuộc sequence reset trừ khi test đang kiểm tra chính sequence.
- Nếu cần ID cố định, khai báo ID rõ ràng trong fixture và bảo đảm schema cho phép.

Ví dụ:

~~~java
customerRepository.save(customer)
        .flatMap(saved ->
                orderRepository.findByCustomerId(saved.getId())
                        .collectList());
~~~

Không dùng `SELECT MAX(id)` để suy ra ID vừa insert. Với request đồng thời, một transaction khác có thể tạo ID lớn hơn.

## 14. Tách dữ liệu khi chạy test song song

Test song song có thể làm lộ các phụ thuộc mà test tuần tự chưa phát hiện:

- Hai test cùng insert email cố định.
- Một test truncate bảng trong khi test khác đang đọc.
- Một test cập nhật trạng thái hàng mà test khác đang assert.
- Test cleanup xóa fixture của test khác.
- Connection pool quá nhỏ khiến các test chờ nhau.
- Shared container chạy migration đồng thời.

Các giải pháp:

1. Mỗi test dùng unique namespace cho natural key và cleanup theo namespace đó.
2. Chia database hoặc schema theo test class/suite.
3. Dùng database/container riêng nếu cần isolation mạnh.
4. Tắt parallel execution cho nhóm test bắt buộc dùng chung trạng thái.
5. Không dùng truncate toàn database trong `@AfterEach` nếu test khác có thể đang chạy.
6. Đặt pool size và timeout phù hợp với concurrency của test suite.

Tên test hoặc ID ngẫu nhiên có thể được dùng làm namespace. Hãy giữ namespace trong biến test để cleanup chính xác.

## 15. Dùng H2 hoặc database embedded có đủ không?

Database embedded có thể giúp test chạy nhanh, nhưng không thay thế được integration test với database production nếu ứng dụng phụ thuộc vào dialect hoặc hành vi riêng.

Khác biệt có thể xuất hiện ở:

- Cú pháp SQL.
- Kiểu dữ liệu và precision.
- Identity/sequence.
- Constraint và tên constraint.
- Transaction isolation.
- Locking và `SELECT FOR UPDATE`.
- JSON, array, enum hoặc kiểu dữ liệu đặc thù.
- Alias, quoting và chữ hoa/chữ thường.
- DDL transaction semantics.
- R2DBC driver và mapping converter.

Có thể dùng H2 cho một số test logic đơn giản nếu SQL và schema tương thích. Nhưng nên có integration test với đúng database/driver mà production sử dụng để xác nhận hành vi thực tế.

Testcontainers giúp chạy engine thật trong môi trường tự động hóa. Chi phí khởi động cao hơn nhưng giảm sai lệch giữa test và production.

## 16. Dữ liệu mẫu cho từng loại test

Không phải mọi test cần cùng một kiểu dữ liệu.

| Loại test | Dữ liệu nên chuẩn bị |
|---|---|
| Derived query | Vài hàng có giá trị filter khớp và không khớp |
| Unique constraint | Một hàng đã tồn tại và một hàng có key trùng |
| Foreign key | Hàng cha hợp lệ và ID cha không tồn tại |
| Pagination | Nhiều hàng có sort key khác nhau và có trường hợp bằng nhau |
| Null mapping | Một hàng có cột nullable là SQL NULL |
| Optimistic locking | Hai bản đọc cùng version rồi cập nhật cạnh tranh |
| Transaction rollback | Dữ liệu trước transaction và thao tác cố ý thất bại |
| Auditing | Security context với auditor khác nhau khi insert/update |
| Join/projection | Dữ liệu có quan hệ và trường hợp thiếu hàng phụ nếu join tùy chọn |
| Aggregate query | Dữ liệu có số lượng/tổng đã biết để assert |

Fixture cần làm rõ điều kiện biên. Ví dụ test pagination nên có hai hàng cùng `created_at` để xác nhận `id` là tie-breaker. Test foreign key nên có cả trường hợp cha tồn tại và không tồn tại.

## 17. Reset schema hay chỉ reset dữ liệu?

Hai việc này khác nhau:

- **Reset data:** xóa hoặc nạp lại các hàng, giữ nguyên schema.
- **Reset schema:** xóa cấu trúc database rồi tạo lại bảng, constraint, index và dữ liệu.

Reset data thường đủ cho mỗi test. Reset schema phù hợp khi cần kiểm thử migration từ trạng thái rỗng hoặc khi mỗi test suite có database riêng.

Không reset schema sau từng test nếu không cần thiết. DDL có thể chậm, có thể gây lock và semantics transaction khác nhau giữa database.

Nếu kiểm thử migration, nên tạo database mới, chạy migration từ đầu rồi xác nhận schema và dữ liệu. Không chỉ chạy `schema.sql` thay thế migration nếu mục tiêu là kiểm tra migration.

## 18. Bảo vệ dữ liệu thật và thông tin nhạy cảm

Không sao chép trực tiếp production database vào test environment nếu chưa có quy trình ẩn danh và phê duyệt phù hợp.

Dữ liệu test nên dùng:

- Tên và email giả.
- Số điện thoại dành riêng cho test.
- Địa chỉ giả.
- Token/secret không có giá trị truy cập thật.
- Giá trị thanh toán giả lập.
- ID và mã đơn hàng không trùng môi trường thật.

Không commit password production, connection string có credential hoặc file dump chứa PII vào repository.

Nếu cần dữ liệu gần với phân bố production để benchmark, dùng dữ liệu tổng hợp hoặc quy trình anonymization được kiểm soát. Không dùng bản dump chưa xử lý trong CI.

## 19. Các lỗi thường gặp khi chuẩn bị test data

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng chung database production | Có thể sửa hoặc xóa dữ liệu thật | Dùng database riêng, user quyền hạn giới hạn và container |
| Chỉ dùng profile test mà không kiểm tra URL | Profile có thể trỏ nhầm database | Xác nhận host/database trước khi chạy setup |
| Seed data toàn cục quá nhiều | Test phụ thuộc trạng thái chung | Chỉ giữ dữ liệu nền; tạo fixture riêng cho scenario |
| Insert fixture bằng subscription tách rời | Test chạy trước khi seed hoàn tất | Nối publisher và chờ bằng StepVerifier |
| Cleanup gọi subscribe() trong @AfterEach | Test sau có thể chạy trước khi cleanup xong | Compose cleanup hoặc dùng test lifecycle reactive phù hợp |
| Xóa bảng cha trước bảng con | Vi phạm foreign key | Cleanup theo dependency order |
| Dùng ID sequence cố định trong assertion | Test thất bại khi sequence tăng | Dùng ID do save trả về hoặc natural key |
| Giả định rollback reset sequence | ID vẫn có thể tăng sau rollback | Không phụ thuộc giá trị sequence |
| Chạy test song song trên cùng dữ liệu | Duplicate, cleanup chéo hoặc kết quả không ổn định | Namespace/database/schema riêng |
| Dùng H2 làm bằng chứng tương thích production | Khác biệt dialect và driver bị bỏ sót | Integration test với database thật |
| Dùng schema.sql đồng thời với Flyway | Hai nguồn schema có thể lệch nhau | Chọn một nguồn quản lý schema chính |
| Bỏ qua lỗi script initialization | Test chạy trên schema thiếu hoặc sai | Dùng continue-on-error=false |
| Dùng dữ liệu production chưa ẩn danh | Lộ thông tin cá nhân và bí mật | Dùng synthetic/anonymized data |
| Nghĩ @DirtiesContext sẽ xóa database | Context bị tạo lại nhưng dữ liệu có thể còn nguyên | Có cleanup/reset database riêng |
| Nghĩ @Transactional test tự rollback mọi R2DBC operation | Subscription khác hoặc connection khác có thể commit độc lập | Kiểm soát reactive transaction context và kiểm tra dữ liệu sau test |

## 20. Quy trình xây dựng test database đáng tin cậy

Một quy trình có thể áp dụng:

1. Chọn database test riêng, tốt nhất là container hoặc instance ephemeral.
2. Kích hoạt cấu hình test tường minh và kiểm tra URL, database name, user.
3. Chọn một nguồn schema chính: migration tool hoặc SQL initialization.
4. Tạo schema và constraint giống môi trường mục tiêu.
5. Nạp seed data nhỏ chỉ cho dữ liệu nền.
6. Tạo fixture riêng trong từng test theo reactive chain.
7. Dùng ID do database trả về hoặc natural key xác định.
8. Chọn chiến lược cleanup: rollback có kiểm soát, DELETE theo fixture hoặc reset database.
9. Nếu test chạy song song, dùng namespace, schema hoặc database riêng hoặc giới hạn parallelism.
10. Kiểm tra các thao tác cleanup đã hoàn tất trước khi test tiếp theo bắt đầu.
11. Chạy integration test trên đúng database/driver, không chỉ embedded database.
12. Bảo đảm test không thể kết nối hoặc ghi vào production.

Một test repository có thể có cấu trúc:

~~~java
@Test
void findsOnlyOpenOrdersForCustomer() {
    Mono<List<PurchaseOrder>> scenario =
            customerRepository.save(
                            CustomerFixtures.defaultCustomer())
                    .flatMap(customer ->
                            orderRepository.saveAll(List.of(
                                            OrderFixtures.openOrder(customer.getId()),
                                            OrderFixtures.closedOrder(customer.getId())))
                                    .thenMany(orderRepository
                                            .findByCustomerIdAndStatus(
                                                    customer.getId(),
                                                    OrderStatus.OPEN))
                                    .collectList());

    StepVerifier.create(scenario)
            .assertNext(orders -> {
                assertThat(orders).hasSize(1);
                assertThat(orders.get(0).getStatus())
                        .isEqualTo(OrderStatus.OPEN);
            })
            .verifyComplete();
}
~~~

Ví dụ này tạo dữ liệu, truy vấn và assert trong một publisher chain. Trong test suite dùng chung database, vẫn cần cleanup hoặc namespace riêng sau khi test hoàn tất.

## 21. Ghi nhớ

- Schema, seed data và fixture là ba thành phần khác nhau của môi trường test.
- Dữ liệu test cần deterministic, repeatable và isolated.
- Luôn dùng database riêng; không trỏ script hoặc cleanup tới production.
- Spring Boot có thể nạp schema/data script cho R2DBC qua cấu hình SQL initialization phù hợp phiên bản.
- Dùng migration làm nguồn schema chính nếu dự án quản lý schema bằng Flyway hoặc Liquibase.
- Seed data dùng chung nên nhỏ; fixture theo test nên thể hiện rõ scenario.
- Trong reactive test, nối các publisher để chờ seed hoàn tất; không subscribe tách rời.
- Cleanup phải được await; `@AfterEach` đồng bộ không tự chờ một Mono được tạo ra.
- Transaction rollback chỉ cô lập được thao tác thực sự tham gia cùng reactive transaction.
- Không giả định sequence/identity được reset sau rollback.
- Test song song cần namespace, schema hoặc database riêng để tránh xung đột.
- H2 không thay thế integration test với đúng database và R2DBC driver production.
- `@DirtiesContext` không tự xóa dữ liệu database.
- Dùng dữ liệu synthetic hoặc anonymized; không commit dump production, credential hay PII.
- Kiểm thử cả schema, constraint, cleanup, transaction và hành vi concurrency trong môi trường gần production.

