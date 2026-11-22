# Testcontainers cho phụ thuộc tích hợp có dữ liệu thực

## 1. Vì sao một REST API cần chạy kiểm thử với phụ thuộc thật?

Giả sử **Orders API** được viết bằng Java/Spring Boot, sử dụng PostgreSQL để lưu đơn hàng, Redis để giữ hạn mức gọi API và một message broker để phát sự kiện. Đội phát triển đã có hàng trăm unit test, controller test dùng `MockMvc`, repository test dùng H2. Tuy nhiên, trên môi trường triển khai xảy ra lỗi:

- Hai request `POST /orders` gửi đồng thời với cùng `Idempotency-Key` tạo hai đơn vì unique constraint trong PostgreSQL khác với mô hình H2 giả lập.
- Một câu query dùng `jsonb`, `ON CONFLICT`, `FOR UPDATE SKIP LOCKED`, partial index hoặc row-level security hoạt động sai khi chuyển từ H2 sang PostgreSQL.
- Test “rollback sau mỗi case” đều xanh, nhưng khi chạy HTTP qua server thật, dữ liệu vẫn được commit vì transaction của request chạy trên thread khác.
- Application phát event vào broker, consumer chạy riêng; một test chỉ mock publisher nên không phát hiện event trùng hoặc mất.
- Cache theo tenant hoạt động đúng trong object giả nhưng sử dụng sai key ở Redis khiến người dùng tenant khác nhận dữ liệu cũ.

**Testcontainers** là thư viện giúp bài test khởi chạy container tạm thời chứa **dịch vụ thật**: PostgreSQL, Redis, Kafka và nhiều hệ thống khác. Ứng dụng kết nối tới service được container tạo bằng thông tin host/port động; khi kết thúc kiểm thử, môi trường có thể được dọn dẹp. Ta có thể kiểm tra hành vi của **driver, SQL dialect, schema migration, transaction, cache và protocol** gần với môi trường vận hành hơn so với mock.

“Có dữ liệu thực” ở đây nghĩa là **dữ liệu được ghi, đọc, khóa, ràng buộc và xử lý bởi phần mềm lưu trữ thực**. Không nên sao chép dữ liệu khách hàng thật vào test. Tạo fixture tổng hợp, đã biết kỳ vọng, đủ thể hiện nhiều tenant, nhiều trạng thái và những đường lỗi.

Bài học thuộc chương **Kiểm thử** của module **INTEGRATION_API_REST**, tập trung các bước thiết kế REST API có URI, phương thức, HTTP status, phân trang, cache, idempotency, OpenAPI, xác thực/phân quyền và xử lý lỗi. Testcontainers là một phần của chiến lược kiểm thử những hợp đồng đó với Java/Spring hoặc nền tảng tương đương.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Chọn đúng thành phần cần **mock**, cần Testcontainers và cần môi trường end-to-end.
2. Cấu hình JUnit 5, Spring Boot và Testcontainers với PostgreSQL thật; hiểu `@ServiceConnection` và `@DynamicPropertySource`.
3. Chạy schema migration và fixture trên database tạm, tránh phụ thuộc thứ tự test hoặc rò dữ liệu giữa case.
4. Viết integration test cho HTTP status, quyền truy cập tenant, SQL/transaction, idempotency và tác dụng phụ.
5. Tạo Redis hoặc broker container khi hành vi giao thức là phần cần kiểm tra.
6. Thiết kế CI có khả năng tái lập, timeout hợp lý, log chẩn đoán và ngân sách tài nguyên.

## 2. Đặt Testcontainers đúng vị trí trong chiến lược kiểm thử

| Loại test | Đối tượng chạy thật | Đối tượng có thể thay thế | Phát hiện tốt | Giới hạn |
|---|---|---|---|---|
| **Unit test** | Hàm/class, policy thuần | DB, mạng, đồng hồ, broker | Tính toán, validation, state transition | Không chứng minh database/driver hoạt động thật |
| **Controller/web slice test** | MVC validation/filter/serialization theo slice được cấu hình | Service/repository qua mock | HTTP binding, JSON, 400/401/403, CORS ở tầng app | Không chứng minh constraint SQL, transaction hay container |
| **Repository integration test** | JPA/JDBC, PostgreSQL container, migration/schema | HTTP controller, downstream | Query, unique/FK/index, locking, native SQL | Không phủ hoàn chỉnh đường HTTP và auth |
| **Application integration test** | Spring context, HTTP layer, database container, service | Một số đối tác ngoài qua fake | Hợp đồng REST tới commit DB, security/filter, lỗi và idempotency | Chưa chứng minh CDN, trình duyệt hay provider bên ngoài thật |
| **Component integration test** | API + database + Redis/broker, worker liên quan | Hệ thống thứ ba khó kiểm soát | Cache, message delivery, retry, outbox/inbox | Chi phí chạy cao hơn; cần quản lý đồng thời |
| **End-to-end/sandbox test** | Các hệ thống ghép vào nhau, có thể kèm browser/provider sandbox | Ít thành phần | Hợp đồng phối hợp triển khai, network, cấu hình, UX | Chậm, phụ thuộc bên ngoài, khó cô lập |

Testcontainers **không tự biến test thành E2E**. Một repository test với PostgreSQL container vẫn chỉ kiểm repository. Một `MockMvc` test với database thật kiểm luồng MVC + service + DB, nhưng chưa đi qua socket HTTP ngoài thực tế. Nếu cần xác minh cổng, proxy, TLS, cookie và HTTP client thật, chạy `@SpringBootTest(webEnvironment = RANDOM_PORT)` với `TestRestTemplate` hoặc `WebTestClient` thích hợp; nếu cần kiểm CORS trong browser, thêm browser test riêng.

Ngược lại, không cần container cho mọi unit test. Policy retry/backoff, tính toán quota, parser hoặc state machine nên được kiểm nhanh với dependency giả và đồng hồ điều khiển được. Đưa Testcontainers vào nơi khác biệt của **phụ thuộc thật** quyết định kết quả.

## 3. Kiến trúc ví dụ: Orders API với PostgreSQL

Hợp đồng minh họa:

| HTTP | Resource | Điều cần chứng minh |
|---|---|---|
| `POST /api/tenants/{tenantId}/orders` | Tạo đơn theo `Idempotency-Key` | Unique key có tác dụng; replay cùng key không tạo đơn thứ hai; khác body bị 409 |
| `GET /api/tenants/{tenantId}/orders/{orderId}` | Đọc đơn | Kiểm `orders.read`, membership, owner và tenant; người ngoài nhận 403/404 theo policy |
| `GET /api/tenants/{tenantId}/orders?page=...` | Danh sách | Phân trang/tổng số chỉ tính những dòng caller được xem |
| `PATCH /api/tenants/{tenantId}/orders/{orderId}` | Cập nhật có điều kiện | Trạng thái/version/owner được kiểm ở DB; ngăn lost update |
| `GET /api/orders/{id}/events` | Xem thay đổi nghiệp vụ | Dữ liệu outbox/inbox phù hợp từng operation |

Ví dụ schema PostgreSQL dùng migration thực tế của ứng dụng. Trong tài liệu có thể minh họa bằng SQL sau:

~~~sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    owner_subject VARCHAR(160) NOT NULL,
    idempotency_key VARCHAR(160) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    amount_minor BIGINT NOT NULL CHECK (amount_minor >= 0),
    status VARCHAR(32) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uk_orders_tenant_idempotency
        UNIQUE (tenant_id, owner_subject, idempotency_key)
);

CREATE INDEX idx_orders_tenant_owner_created
    ON orders (tenant_id, owner_subject, created_at DESC, id DESC);

CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders(id),
    event_type VARCHAR(80) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);
~~~

Đây là schema **minh họa**, chưa phải toàn bộ ứng dụng. Khi xây hệ thống thật, cần khóa user/tenant theo principal đã xác minh, bảng membership, trường trạng thái phù hợp, và các khóa ngoại chặt hơn cho bảng con. Unique key trong DB là rào chắn chống race giữa nhiều pod; kiểm tra `SELECT ... WHERE key = ?` trước khi `INSERT` **không đủ** nếu hai request đến đồng thời.

**Giá trị của PostgreSQL thật:** Có thể kiểm `JSONB`, constraint, thời gian với timezone, `ON CONFLICT`, khóa dòng, isolation và các extension/feature mà H2 mô phỏng không đầy đủ.

## 4. Chuẩn bị JUnit 5, Spring Boot và Testcontainers

### 4.1. Điều kiện chạy

Máy developer hoặc CI runner cần có môi trường container được Testcontainers hỗ trợ (thường là Docker Engine/daemon hoặc runtime tương thích được cấu hình đúng). Testcontainers sử dụng Docker API để tạo/kiểm soát container. Một số môi trường CI không cấp quyền tạo container; khi đó test sẽ thất bại ở bước môi trường, không nên âm thầm chuyển sang H2 rồi báo xanh.

Nên xác nhận trước:

- Runtime container có thể truy cập được từ tiến trình JVM chạy test.
- Test runner được phép kéo/chạy image; nếu mạng bị giới hạn, dùng registry nội bộ hoặc image mirror được quản lý.
- Có đủ bộ nhớ, CPU, dung lượng đĩa và thời gian khởi động container.
- Cổng kết nối được ánh xạ tự động; tránh giả định PostgreSQL của test luôn ở `localhost:5432`.
- Test không phụ thuộc container cũ đang chạy hoặc dữ liệu từ lần test trước.
- Không dùng credential thật của production trong biến môi trường/fixture.

Đối với module này, ta ưu tiên **PostgreSQL container** vì SQL semantics quan trọng. Nếu chỉ test handler chọn HTTP status cho lỗi validation, không cần PostgreSQL.

### 4.2. Dependency Gradle

Ví dụ `build.gradle` dùng Spring Boot 3.x, Java 17+, JUnit Jupiter. Các version cần chọn theo **Spring Boot BOM / Testcontainers BOM** mà dự án đã quản lý; không ghép tùy tiện nhiều version không tương thích:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Nếu production dùng Flyway hoặc Liquibase, khai báo dependency migration theo dự án để **cùng migration thật** chạy trong test. Với các version Flyway hiện đại, việc hỗ trợ PostgreSQL có thể cần module database tương ứng; kiểm BOM và cấu hình đang dùng. Không tự thay migration thật bằng schema SQL viết lại riêng cho test rồi tuyên bố kiểm được tương thích triển khai.

Dùng Maven thì chọn dependency tương đương với scope `test` và version quản lý thống nhất. Trong monorepo, chú ý module test phải nhìn thấy dependency container; đừng vô tình đưa Testcontainers vào runtime artifact production.

### 4.3. Hai cách đưa JDBC URL vào Spring

**Cách A — Spring Boot 3.1+ `@ServiceConnection`:** thuận tiện khi đã có `spring-boot-testcontainers`. Spring Boot tạo connection details từ loại container phù hợp, giảm cấu hình thủ công. Ví dụ ngay trong một test class:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class ApplicationDatabaseIT {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("orders_test")
            .withUsername("orders_test")
            .withPassword("test-only-password");

    @Test
    void applicationContextStartsWithRealPostgres() {
        // Spring dùng JDBC connection details từ PostgreSQL container.
        // Cần có entity/migration phù hợp trong ứng dụng.
    }
}
~~~

**Cách B — `@DynamicPropertySource`:** linh hoạt khi không dùng `@ServiceConnection` hoặc cần đưa thuộc tính không được Boot tự nhận diện. Dùng **một trong hai cách** cho cùng datasource để dễ hiểu nguồn cấu hình:

~~~java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class PostgresPropertiesExample {
    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

Ví dụ B chỉ minh họa phương pháp khai báo thuộc tính: để chạy test Spring thực tế còn cần `@SpringBootTest` hoặc một Spring test slice phù hợp. `@DynamicPropertySource` cần field container tĩnh đã được khởi động bởi JUnit extension trước khi Spring dùng thuộc tính. `@ServiceConnection` phù hợp cả kết nối JDBC và các kết nối được Boot hỗ trợ khác, nhưng khả năng nhận diện phụ thuộc loại container và phiên bản Spring Boot.

**Không hardcode mapped port**: Testcontainers thường ánh xạ PostgreSQL cổng container `5432` sang cổng ngẫu nhiên trên host. Luôn dùng `getJdbcUrl()` / `getMappedPort(...)` hoặc connection details tương ứng.

## 5. Chạy migration thật và quản lý fixture

### 5.1. Migration phải khớp ứng dụng

Khi Spring Boot khởi tạo DataSource từ container, Flyway/Liquibase (nếu bật) chạy migration trước khi service test truy cập DB. Ví dụ:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  flyway:
    enabled: true
~~~

`ddl-auto: validate` phù hợp nếu schema **do migration quản lý**: Hibernate chỉ kiểm mapping, không tự tạo bảng giúp test vô tình che đi migration thiếu. Nếu dự án dùng Liquibase, thay cấu hình tương ứng. Không bật đồng thời nhiều schema creator cạnh tranh nhau.

Tại sao phải dùng migration thật?

- Kiểm đúng loại cột `UUID`, `JSONB`, `TIMESTAMPTZ`, default và unique constraint.
- Kiểm migration có thể chạy trên database **trắng**, không cần bản ghi hay sửa tay.
- Kiểm JPA entity/repository tương thích schema thực tế.
- Phát hiện syntax PostgreSQL không được H2 hỗ trợ và ngược lại.
- Dễ nâng cấp schema vì test chạy lại quá trình khởi tạo môi trường.

Testcontainers **không tự chạy migration**: đó là trách nhiệm cấu hình Spring/Flyway/Liquibase. Nếu chỉ container started nhưng app không cấu hình database/migration đúng, test không có ý nghĩa về schema.

### 5.2. Fixture nhỏ, rõ ràng, độc lập

Thiết kế fixture theo tình huống cần chứng minh:

| Tenant | Subject | Order | Trạng thái | Ý nghĩa test |
|---|---|---|---|---|
| A | `alice` | A-101 | NEW | Owner hợp lệ |
| A | `bob` | A-102 | PAID | Người khác cùng tenant |
| B | `charlie` | B-201 | NEW | Tenant khác |
| A | `alice` | A-103 | CANCELLED | Trạng thái không được cập nhật tiếp |

Dùng UUID cố định hợp lệ hoặc ID tạo từ fixture builder; tránh dữ liệu phụ thuộc thời gian hiện tại nếu không cần. Dữ liệu test không nên chứa PII production. Cơ sở dữ liệu trắng mỗi test class hoặc schema riêng giúp giảm phụ thuộc chéo giữa case.

Một cách seed fixture bằng `JdbcTemplate` và SQL tham số hóa:

~~~java
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

class OrderDataFixture {
    static final UUID TENANT_A = UUID.fromString(
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
    static final UUID TENANT_B = UUID.fromString(
        "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb");
    static final UUID ORDER_A = UUID.fromString(
        "11111111-1111-4111-8111-111111111111");
    static final UUID ORDER_B = UUID.fromString(
        "22222222-2222-4222-8222-222222222222");

    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void seed() {
        jdbc.update("DELETE FROM outbox_events");
        jdbc.update("DELETE FROM orders");
        jdbc.update("""
            INSERT INTO orders(
                id, tenant_id, owner_subject, idempotency_key,
                request_hash, amount_minor, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ORDER_A, TENANT_A, "alice", "seed-a", "hash-a",
            320_000L, "NEW");

        jdbc.update("""
            INSERT INTO orders(
                id, tenant_id, owner_subject, idempotency_key,
                request_hash, amount_minor, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ORDER_B, TENANT_B, "charlie", "seed-b", "hash-b",
            450_000L, "NEW");
    }
}
~~~

Lớp trên là **fixture minh họa**, không chạy độc lập như một test: trong dự án thật, đưa `@BeforeEach` vào test class đã có Spring extension, hoặc xây một component/helper được gọi từ test setup. Bảng `outbox_events` cần xóa trước `orders` vì foreign key. Với nhiều bảng hơn, dọn theo thứ tự phụ thuộc hoặc dùng transaction/truncate phù hợp. Tránh `TRUNCATE ... CASCADE` bừa bãi nếu nhiều test đang chia chung DB.

### 5.3. Cẩn thận với `@Transactional` trong integration test

Đây là lỗi hiểu sai hay gặp:

- Repository test chạy cùng test thread, `@Transactional` của Spring Test có thể rollback những thay đổi do test tạo, giúp cô lập dữ liệu.
- `MockMvc` thường chạy request trong cùng thread test, nhưng các nhánh `REQUIRES_NEW`, async hoặc worker khác có thể commit độc lập.
- `@SpringBootTest(webEnvironment = RANDOM_PORT)` gửi HTTP qua server thread/transaction **khác**. Transaction rollback của test method **không rollback các commit do request HTTP tạo**.
- Message consumer, scheduler, outbox publisher hoặc callback chạy async thường có transaction riêng, không được gộp bằng annotation trên phương thức test.

Nếu test cần HTTP qua cổng thật, hãy thiết kế cleanup dữ liệu được commit, database/schema riêng, tenant và key riêng, hoặc container mới với lifecycle phù hợp. Không dựa vào rollback của test để khẳng định DB sạch sau mỗi request.

### 5.4. Mức độ cô lập dữ liệu

| Chiến lược | Ưu điểm | Chi phí/rủi ro |
|---|---|---|
| PostgreSQL container mới cho mỗi test class | Dễ kiểm soát, không trộn dữ liệu giữa class | Tốn thời gian khởi động |
| Container chung cho nhiều class, cleanup từng test | Nhanh hơn với suite lớn | Dễ rò dữ liệu nếu cleanup thiếu; parallel tests khó |
| Database/schema riêng cho từng test | Có thể chạy song song an toàn hơn | Quản lý migration/schema/context phức tạp |
| Transaction rollback của repository test | Rất nhanh, dễ dùng | Không bao phủ request trên thread khác/async |
| Fixture unique ID theo từng test | Giảm đụng độ | Cần cleanup hoặc TTL để tránh DB phình ra |

Không bật **reuse container** toàn cục trong CI chỉ để tăng tốc: tính tái lập và vòng đời dữ liệu quan trọng hơn vài giây. Testcontainers hỗ trợ cơ chế reuse ở một số cấu hình nhưng cần hiểu rõ đó là tối ưu riêng, không thay thế cô lập fixture.

## 6. Integration test REST với PostgreSQL container

### 6.1. Spring Boot + MockMvc + DB thật

Giả sử ứng dụng đã có `GET /api/tenants/{tenantId}/orders/{orderId}` yêu cầu `SCOPE_orders.read`, ánh xạ `sub` sang owner và trả 404 khi không được xem. Test dưới đây dùng container PostgreSQL thật cho service/repository và `MockMvc` cho HTTP/filter chain. Các entity/controller/service tương ứng phải có sẵn trong ứng dụng; đây là **khung test tích hợp** có fixture được tạo trực tiếp trong test.

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
@AutoConfigureMockMvc
class OrderIsolationIT {
    private static final UUID TENANT_A = UUID.fromString(
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
    private static final UUID TENANT_B = UUID.fromString(
        "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb");
    private static final UUID ORDER_A = UUID.fromString(
        "11111111-1111-4111-8111-111111111111");
    private static final UUID ORDER_B = UUID.fromString(
        "22222222-2222-4222-8222-222222222222");

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void seedOrders() {
        jdbc.update("DELETE FROM outbox_events");
        jdbc.update("DELETE FROM orders");
        insert(ORDER_A, TENANT_A, "alice", "fixture-a");
        insert(ORDER_B, TENANT_B, "charlie", "fixture-b");
    }

    void insert(UUID id, UUID tenantId, String owner, String key) {
        jdbc.update("""
            INSERT INTO orders(
                id, tenant_id, owner_subject, idempotency_key,
                request_hash, amount_minor, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, id, tenantId, owner, key, "fixture-hash", 320_000L, "NEW");
    }

    @Test
    void ownerCanReadOwnOrder() throws Exception {
        mvc.perform(get("/api/tenants/{t}/orders/{o}",
                TENANT_A, ORDER_A).with(jwt()
                .jwt(j -> j.subject("alice")
                           .issuer("https://login.example.test"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders.read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(ORDER_A.toString()));
    }

    @Test
    void callerCannotReadOtherTenantsOrder() throws Exception {
        mvc.perform(get("/api/tenants/{t}/orders/{o}",
                TENANT_B, ORDER_B).with(jwt()
                .jwt(j -> j.subject("alice")
                           .issuer("https://login.example.test"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders.read"))))
            .andExpect(status().isNotFound());
    }

    @Test
    void missingScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/tenants/{t}/orders/{o}",
                TENANT_A, ORDER_A).with(jwt()
                .jwt(j -> j.subject("alice"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_profile"))))
            .andExpect(status().isForbidden());
    }
}
~~~

Để test thực sự chạy, phải có domain implementation theo contract và nếu API kiểm membership bằng bảng riêng thì fixture phải seed `tenant_memberships` nữa. Mẫu chọn `owner_subject` trực tiếp để tập trung vào cách Testcontainers kết nối dữ liệu thật; không bỏ membership hoặc identity mapping trong hệ thống production.

**Điểm phân biệt quan trọng:** `.with(jwt())` của `spring-security-test` tạo `JwtAuthenticationToken` giả cho request, vì vậy test này **không kiểm chứng** chữ ký, issuer, audience, hết hạn hoặc JWKS bằng decoder thật. Nó kiểm luật scope, controller/service và query với PostgreSQL thật. Để chứng minh resource server từ chối ID token/sai audience hoặc JWT chữ ký giả, cần test riêng với `Authorization: Bearer <token-ký-thật>`, JWKS thử nghiệm và cấu hình `JwtDecoder` thật. Testcontainers cung cấp DB thật, nhưng không tự làm JWT test trở thành “real auth test”.

### 6.2. Test repository slice dùng PostgreSQL thay H2

Nếu chỉ cần xác minh JPA repository, dùng `@DataJpaTest`. Spring Boot có thể tự thay DataSource test bằng embedded database nếu không chỉ rõ. Khi dùng Testcontainers, đặt:

~~~java
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class OrderRepositoryIT {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    // @Autowired OrderRepository repository;
    // @Autowired TestEntityManager entityManager;
    // Test SQL/constraint/locking cụ thể tại đây.
}
~~~

Tùy version Spring Boot và cấu hình test slice, migration/bean cần được import hoặc bật đúng cách. Kiểm log DataSource cho chắc JDBC URL đang trỏ đến container, không phải H2 hay DB local. Nếu schema migration không chạy trong slice, cần cấu hình slice phù hợp thay vì tạo schema khác với production.

### 6.3. Khi nào dùng RANDOM_PORT?

Nếu cần kiểm headers/serialization qua HTTP socket thật:

~~~java
@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
@Testcontainers
class OrdersHttpIT {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired TestRestTemplate http;

    // http.exchange(...) gửi qua server HTTP thực.
    // Nếu API yêu cầu access token, phát token test phù hợp
    // và kiểm SecurityFilterChain/JwtDecoder thật.
}
~~~

`RANDOM_PORT` dành cho cổng **ứng dụng Spring**, còn `getMappedPort(5432)` là cổng **container PostgreSQL**: đây là hai thứ khác nhau. Test qua cổng thật giúp kiểm HTTP stack, nhưng phải dọn dữ liệu đã commit. Không test song song cùng DB mà dùng câu `DELETE FROM orders` trong `@BeforeEach` của những class khác nhau vì có thể xóa dữ liệu của test đang chạy.

## 7. Những trường hợp Testcontainers phát huy giá trị

### 7.1. Constraint và idempotency ở mức database

Khi nhận `POST /orders`, mã ứng dụng kiểm operation đã tồn tại rồi insert. Hai request đến đồng thời đều có thể thấy chưa tồn tại; DB unique constraint là điều kiện cuối cùng chặn duplicate.

Test cần chứng minh:

1. Cùng tenant + caller + key và cùng fingerprint: chỉ một order/effect logic, response replay trỏ cùng resource/operation.
2. Cùng key nhưng khác fingerprint: API trả 409, không thay order ban đầu.
3. Khác tenant hoặc caller: phạm vi key theo hợp đồng, không cho cache kết quả của người khác.
4. Nhiều thread/pod cùng insert: unique violation được xử lý đúng transaction boundary; không truy vấn tiếp trong transaction đã rollback-only.
5. Với outbox, cả order và outbox intent cùng commit hoặc cùng rollback.

SQL có thể giúp kiểm unique một cách trực tiếp:

~~~sql
INSERT INTO orders(
    id, tenant_id, owner_subject, idempotency_key,
    request_hash, amount_minor, status
) VALUES (
    '11111111-1111-4111-8111-111111111111',
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    'alice', 'create-001', 'hash-1', 320000, 'NEW'
);

-- Insert tiếp với tenant, owner, key tương tự
-- nhưng id khác phải vi phạm uk_orders_tenant_idempotency.
~~~

Nếu muốn kiểm race thật, dùng `CountDownLatch`/barrier để các caller cùng bắt đầu rồi gọi service hoặc HTTP endpoint và thu kết quả. Tránh test chỉ gọi tuần tự hai lần rồi kết luận đã chống được race. Sau cùng query DB để kiểm **COUNT(*)=1** và outbox đúng số logical effect; response 2xx thôi chưa đủ.

### 7.2. Transaction và rollback/commit

Đặt một fault point sau khi insert order nhưng trước khi insert outbox để kiểm local transaction rollback cả hai. Đặt fault point sau commit nhưng trước khi publisher gửi event để kiểm outbox còn record có thể phát lại. Đặt fault point sau khi publisher gửi event nhưng trước khi update `published_at` để kiểm consumer có deduplication.

Các test này có ý nghĩa hơn khi dùng PostgreSQL thật vì transaction isolation, khóa và unique constraint đúng như production. Testcontainers **không biến giao dịch qua broker và DB thành một transaction toàn cục**; vẫn cần outbox/inbox/idempotency và kiểm số side effect thật.

### 7.3. Query có cú pháp/semantics riêng PostgreSQL

Các ví dụ nên test bằng DB đúng loại:

~~~sql
-- Đọc outbox theo từng batch worker, tránh tranh cùng một dòng.
SELECT id
FROM outbox_events
WHERE published_at IS NULL
ORDER BY created_at, id
FOR UPDATE SKIP LOCKED
LIMIT 50;
~~~

~~~sql
-- Upsert có điều kiện theo khóa nghiệp vụ.
INSERT INTO orders(
    id, tenant_id, owner_subject, idempotency_key,
    request_hash, amount_minor, status
)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (tenant_id, owner_subject, idempotency_key)
DO NOTHING;
~~~

`SELECT ... FOR UPDATE SKIP LOCKED` cần chạy trong transaction với cơ chế claim/lease phù hợp; chỉ SELECT rồi commit sẽ thả khóa. `ON CONFLICT DO NOTHING` không tự giải quyết trường hợp **cùng key, khác fingerprint**: sau khi insert không thành công phải đọc lại record đã commit và so fingerprint để trả 409 hoặc replay đúng.

### 7.4. Row-Level Security và tenant isolation

Nếu production sử dụng PostgreSQL RLS, phải test bằng PostgreSQL thật:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_policy ON orders
USING (
    tenant_id = NULLIF(
        current_setting('app.tenant_id', true), ''
    )::uuid
)
WITH CHECK (
    tenant_id = NULLIF(
        current_setting('app.tenant_id', true), ''
    )::uuid
);

ALTER TABLE orders FORCE ROW LEVEL SECURITY;
~~~

Trong transaction của test, đặt tenant context đã được server xác minh:

~~~sql
SELECT set_config(
    'app.tenant_id',
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    true
);
~~~

Sau đó `SELECT * FROM orders` (không có WHERE) phải chỉ thấy dòng Tenant A. Kết thúc transaction, dùng lại pooled connection trong transaction mới với Tenant B, phải chỉ thấy B; khi thiếu context phải fail closed. **Role DB có BYPASSRLS hoặc superuser có thể vượt RLS**, nên test bằng role ứng dụng không có bypass. RLS này chỉ lọc tenant; ownership, membership và scope vẫn cần kiểm ở service hoặc policy DB sâu hơn.

### 7.5. Phân trang và thứ tự ổn định

Với nhiều hàng cùng `created_at`, query chỉ `ORDER BY created_at DESC` có thể cho trang kết quả không ổn định. Test DB với hai timestamp trùng nhau để chứng minh cần tiêu chí phụ `id DESC`. Với cursor keyset:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND owner_subject = :subject
  AND (created_at, id) < (:lastCreatedAt, :lastId)
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

SQL tuple comparison, sorting, index và timezone cần được test với chính PostgreSQL. Test cả `COUNT(*)` hoặc metadata tổng số không lộ tenant khác. Client có thể sửa cursor; server phải ràng buộc filter/tenant với cursor hoặc xác minh lại quyền, không tin chỉ vì truy vấn có parameter.

## 8. Redis trong Testcontainers: kiểm cache và rate limiting

Khi ứng dụng dùng Redis để cache đơn hàng, lưu session, cache idempotency hoặc chia sẻ quota giữa nhiều instance, in-memory mock không thể mô phỏng đủ TTL, key collision, atomic script và lỗi kết nối.

Ví dụ khởi chạy Redis bằng `GenericContainer` và `@DynamicPropertySource`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class RedisCacheIT {
    @Container
    static GenericContainer<?> redis = new GenericContainer<>(
        DockerImageName.parse("redis:7.2-alpine"))
        .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add("spring.data.redis.port",
            () -> redis.getMappedPort(6379));
    }

    @Test
    void cacheUsesRedisConnection() {
        // Kiểm through RedisTemplate/CacheManager thật của Spring.
        // Seed key, đọc lại và assert TTL hoặc invalidation.
    }
}
~~~

Nếu production dùng phiên bản Redis khác, chọn image phù hợp và pin version. Phải thêm `spring-boot-starter-data-redis` vào ứng dụng đang cần Redis. `GenericContainer` chỉ cung cấp container/port: app vẫn cần client/serializer và cấu hình Redis thật.

Các ca test quan trọng:

- Hai tenant có cùng order ID hoặc cùng URI tương đối: cache key cần bao gồm tenant và phạm vi quyền để không trả nhầm dữ liệu.
- TTL hết hạn và invalidation sau PATCH/DELETE: không đọc bản cũ.
- Hai client cùng key quota gửi request cạnh tranh: thao tác token bucket/Redis Lua phải atomic; không cho quota “bị cộng đôi”.
- Redis không sẵn sàng: xác nhận fail-open/fail-closed theo chính sách; nếu quota store lỗi thì không tùy tiện quy kết caller đã vượt quota.
- Không tái sử dụng khóa giữa test case; cleanup namespace Redis riêng hoặc database test tương ứng.

**Không chỉ test GET cache hit:** phải kiểm side effect trên database, TTL, quyền khi user đổi role và hành vi sau Redis restart nếu đó là requirement sản phẩm.

## 9. Broker container, outbox và consumer

Nếu hệ thống dùng Kafka/RabbitMQ, chọn **module Testcontainers chuyên dụng** tương ứng và image/version hợp lệ. Module này giúp chạy broker thật để kiểm serializer, key/partition, consumer group và giao thức publish/subscribe. Các class API Kafka của Testcontainers có thay đổi theo version, nên theo documentation/version của dự án thay vì sao chép class đã deprecate.

Luồng test minh họa:

~~~mermaid
sequenceDiagram
    participant T as Integration test
    participant A as Orders API
    participant D as PostgreSQL container
    participant O as Outbox publisher
    participant B as Broker container
    participant C as Consumer
    T->>A: POST /orders + Idempotency-Key K
    A->>D: TX: order + outbox
    D-->>A: COMMIT
    A-->>T: 202 hoặc 201 theo contract
    O->>D: Claim outbox
    O->>B: Publish OrderCreated
    B->>C: Deliver event
    C->>D: Deduplicate và cập nhật projection
    T->>D: Chờ điều kiện trạng thái cuối với deadline
~~~

Với outbox consumer:

1. Seed order/outbox hoặc gọi REST API để tạo thật.
2. Chờ consumer đạt điều kiện cụ thể (event đã xử lý, projection có dòng), không ngủ cố định 5 giây.
3. Phát lại cùng event ID để kiểm inbox/deduplication; số tác dụng phụ logic vẫn là 1.
4. Làm publisher fail **sau khi broker nhận event nhưng trước khi ghi đã phát**; cho phép publish trùng nhưng consumer không xử lý nghiệp vụ hai lần.
5. Kiểm event đúng tenant, correlation ID, schema version và không chứa dữ liệu nhạy cảm.
6. Xử lý cleanup topic/consumer group hoặc namespace riêng; tránh các test chạy song song giẫm lên state.

Dùng timeout và cơ chế chờ có điều kiện (ví dụ Awaitility) thay cho `Thread.sleep` mù. Testcontainers chỉ cho broker thật; không tự xác minh chính sách exactly-once trong external REST API hoặc trạng thái provider bên thứ ba.

### 9.1. Khi nên mock provider ngoài hệ thống

Không nên dùng live payment service hoặc email provider production trong integration test. Với hệ thống ngoài:

- Dùng **fake adapter/WireMock/MockWebServer** để trả response có kiểm soát: thành công, timeout sau khi provider giả đã ghi effect, HTTP 429/503, webhook trùng.
- Dùng sandbox provider cho một nhóm contract test riêng khi cần kiểm semantics thật của bên thứ ba.
- Giữ token/secret sandbox trong CI secret store; không commit vào bài test.
- Kiểm mapping HTTP request/response, idempotency key, retry và timeout ở adapter.

Những dependency mình **kiểm soát dữ liệu và lifecycle** như database, Redis, broker thường là ứng viên tốt cho Testcontainers. Những dependency có tác dụng phụ thật như cổng thanh toán nên dùng sandbox/contract test theo giới hạn rõ ràng.

## 10. Tổ chức suite để vừa nhanh vừa đáng tin

### 10.1. Không khởi động container ở mọi phương thức nếu không cần

`@Container static` cùng `@Testcontainers` thường có lifecycle theo **test class**: extension khởi động trước test trong class và dừng sau class. Field instance `@Container` có vòng đời ngắn hơn theo phương thức. Điều này tác động rất mạnh đến tốc độ suite.

Có thể tổ chức:

- Unit tests: nhiều, chạy thường xuyên, không container.
- Web slice tests: nhanh, tập trung auth/validation/serialization.
- Repository integration tests: một số lớp nhóm theo tính năng với PostgreSQL thật.
- Application integration tests: cover luồng REST → DB → outbox.
- Broker/Redis tests: chỉ nơi thật sự dùng features của chúng.
- End-to-end sandbox: số ít, tách job khi có yêu cầu vận hành.

**Spring ApplicationContext caching và container lifecycle:** Nếu nhiều test class dùng chung cached Spring context nhưng mỗi class khởi một container tĩnh rồi dừng sau class, một context được tái sử dụng có thể giữ JDBC URL/connection details của container **đã dừng**. Cần thiết kế lifecycle container và context tương thích: nhóm test dùng một container cho cùng context/suite, định danh context rõ, hoặc tránh cache context dùng resource đã chết. Đừng xử lý bằng việc “retry test” vô hạn vì lỗi được che giấu.

### 10.2. Image, port và thời gian chờ

Dùng image đã pin tag tương thích production, ví dụ `postgres:16-alpine`. Với môi trường đòi tái lập mạnh, có thể pin digest và quản lý cập nhật image theo lịch. Không dùng `latest` cho CI mà không kiểm soát thay đổi. Các module `PostgreSQLContainer` có wait strategy tích hợp cho DB; với `GenericContainer` cần chọn wait strategy phù hợp cho service thật.

~~~java
import java.time.Duration;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.utility.DockerImageName;

GenericContainer<?> service = new GenericContainer<>(
    DockerImageName.parse("redis:7.2-alpine"))
    .withExposedPorts(6379)
    .waitingFor(Wait.forListeningPort())
    .withStartupTimeout(Duration.ofSeconds(90));
~~~

`container started` không đồng nghĩa mọi nghiệp vụ bên trong đã sẵn sàng. Với broker/DB có migrations, chờ readiness thực tế của ứng dụng hoặc điều kiện dữ liệu. Không dùng timeout cực dài để bỏ qua lỗi thiết kế. Khi CI fail, lưu log container, log ứng dụng, exception cause và connection URL đã **ẩn credential**.

### 10.3. Parallel test và cách cô lập

Chạy parallel test với DB/container dùng chung cần kế hoạch:

- Unique tenant/user/key theo từng test và cleanup đúng namespace.
- Hoặc tạo schema/database riêng cho mỗi test suite.
- Không chạy hai test cùng `TRUNCATE orders` trong lúc test kia đang đọc/ghi.
- Tách topic/consumer group/cache prefix cho Kafka/Redis.
- Giới hạn concurrency test theo CPU/RAM của CI và pool DB; test chậm do thiếu tài nguyên không nhất thiết là lỗi nghiệp vụ.

Nếu test bắt buộc kiểm race, **chủ động tạo race trong một case** với barrier/latch và dữ liệu riêng; không dựa vào test runner chạy song song ngẫu nhiên để hi vọng tái hiện bug.

### 10.4. Dọn dẹp và resource lifecycle

Testcontainers quản lý container lifecycle, nhưng database fixture, message, cache key và các resource ngoài container vẫn có thể cần cleanup theo test. Không sử dụng `withReuse(true)` mặc định trong CI hoặc các test cần trạng thái trắng. Khi một case thất bại, phải bảo đảm container log/stack trace vẫn thu được; đừng xóa bằng tay trước khi hệ thống thu artifact chẩn đoán.

## 11. CI/CD cho test tích hợp có container

Một pipeline CI điển hình:

~~~text
Checkout source
    |
    v
Setup JDK/Gradle + cache dependency (không cache database test)
    |
    v
Xác minh runner truy cập container runtime
    |
    v
Unit test / web slice test
    |
    v
Testcontainers integration tests
    |- PostgreSQL image được kéo và start
    |- Schema migration chạy trên DB trắng
    |- Fixture tạo dữ liệu có kiểm soát
    |- REST/JPA/security tests
    |- Cleanup + thu logs khi fail
    v
Report JUnit XML + coverage + build status
~~~

Nếu dùng runner do tổ chức cung cấp, cần cấu hình Docker socket/daemon đúng chính sách của runner; một số executor container hóa không cấp Docker API mặc định. Tránh “fix” bằng cách mở socket Docker ra internet hoặc cấp quyền tùy tiện. Với CI bị giới hạn network, có thể mirror image vào registry nội bộ để giảm lỗi kéo image. Testcontainers còn có một số thành phần quản lý lifecycle (ví dụ container dọn rác); phải thiết kế môi trường để chúng hoạt động theo yêu cầu bảo mật của runner, không tắt cơ chế bảo vệ một cách mặc định.

### 11.1. Tách lệnh test theo mục đích

Trong Gradle có thể tạo task `integrationTest` riêng với source set/tag của dự án, nhưng cú pháp cụ thể phụ thuộc build setup. Cách đơn giản là dùng tag JUnit:

~~~java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("integration")
class PostgresOrderIT {
    @Test
    void queryUsesRealDatabase() {
        // Testcontainers + application configuration.
    }
}
~~~

Sau đó cấu hình JUnit Platform/Gradle chọn tags phù hợp: unit test chạy nhanh trong mỗi lần sửa, integration test chạy trong PR, và thử nghiệm sandbox/E2E chạy theo cadence phù hợp. Testcontainers test **phải thật sự chạy trong CI** trước khi merge nếu đó là điều kiện bảo vệ migration và dữ liệu.

### 11.2. Phân loại lỗi test đúng nguyên nhân

| Triệu chứng | Khả năng | Hướng kiểm tra |
|---|---|---|
| `Could not find a valid Docker environment` | Runner không truy cập Docker API | Runtime/permissions/socket, không đổ cho repository |
| Không pull được `postgres:...` | Registry/network/auth | Network/registry mirror/image pin |
| `Connection refused` lúc Spring khởi tạo | Container chưa start, sai mapped port hoặc stale cached context | Log startup, connection details, lifecycle |
| `relation orders does not exist` | Migration không chạy, sai schema/search_path | Flyway/Liquibase logs, DB/schema đang kết nối |
| Unique constraint khác kỳ vọng | Schema migration hoặc business key sai | Constraint name, DDL thực, fixture |
| Test xanh khi chạy riêng, đỏ khi chạy suite | Dữ liệu/container/context dùng chung, race, parallel cleanup | Tách fixture, context lifecycle, nguồn thời gian |
| Test async lúc xanh lúc đỏ | Dùng sleep cố định, consumer/worker chưa xong | Chờ điều kiện với deadline và log |
| Local chạy, CI timeout | Tài nguyên runner yếu, image pull chậm, CPU throttle | Log thời gian start, memory/CPU, wait strategy |
| Security test chỉ dùng `jwt()` vẫn xanh khi decoder sai | Authentication bị mock bypass | Thêm test bearer JWT được ký và JWKS thật |

Khi có lỗi test, cần phân biệt **hạ tầng container không sẵn sàng** và **assertion về dữ liệu/HTTP sai**. Tránh tắt test tích hợp chỉ vì CI chậm; cải thiện cách tổ chức suite, caching dependencies và image mirror có kiểm soát.

## 12. Bảo mật và dữ liệu trong môi trường test

Một PostgreSQL container test có thể chứa nhiều thông tin debug. Dù chỉ chạy trên máy cá nhân/CI, phải giữ các quy tắc cơ bản:

- **Không copy data production** vào image/fixture; tạo dữ liệu tổng hợp hoặc đã khử định danh theo chính sách.
- **Không dùng production credential**, JWT secret, client secret hoặc payment token trong file test.
- **Không dùng cổng DB cố định lộ ra mạng ngoài** nếu không cần; Testcontainers tự ánh xạ port và kết nối trong phạm vi test.
- **Không log nguyên access token/cookie/PII**, kể cả output CI được chia sẻ.
- **Kiểm tenant isolation và BOLA** trên dữ liệu A/B; một ID được đoán ra không phải quyền truy cập.
- **Dùng role DB phù hợp production**, đặc biệt với RLS và permission; đừng kiểm RLS bằng superuser rồi kết luận policy hoạt động.
- **CORS chỉ được browser thực thi**; `MockMvc` hoặc `curl` có thể kiểm header nhưng không mô phỏng bảo mật browser hoàn toàn.
- **Test các mã lỗi thật**: 401 sai token, 403 thiếu scope, 404 tài nguyên không thuộc quyền, 409 idempotency conflict, 429 quota, 503 overload; đừng chỉ đo happy path 200.
- **Không phát side effect ra ngoài**: payment/email nên dùng fake adapter hoặc sandbox có quota/secret được bảo vệ.

Testcontainers giúp tạo môi trường đáng tin để kiểm **dữ liệu**, nhưng không tự xác minh toàn bộ mô hình bảo mật. Test chỉ có giá trị khi assertion diễn đạt quyền, dữ liệu và hành vi mà ta muốn bảo vệ.

## 13. Ma trận kiểm thử REST dùng Testcontainers

| Kịch bản | Phụ thuộc thật cần thiết | Assertion quan trọng |
|---|---|---|
| PostgreSQL migration chạy từ DB trắng | PostgreSQL | Schema, index, constraint, mapping JPA |
| `POST /orders` replay cùng key | PostgreSQL | Một order/operation, same resource ID |
| Hai request tạo đơn đồng thời | PostgreSQL | Unique business key, không có duplicate effect |
| Cùng key khác body | PostgreSQL | HTTP 409, DB không đổi |
| GET order khác tenant | PostgreSQL + Spring web/security | 403/404, không trả data B |
| GET list với pagination | PostgreSQL | Thứ tự ổn định, count đúng tenant/owner |
| PATCH với ETag cũ | PostgreSQL | 412 nếu contract dùng `If-Match`, version không bị ghi đè |
| Worker dùng `SKIP LOCKED` | PostgreSQL | Hai worker không claim một dòng cùng lúc trong transaction |
| RLS tái sử dụng pooled connection | PostgreSQL | Tenant context không rò giữa transaction |
| Cache key trùng giữa tenant | Redis + PostgreSQL nếu có DB fallback | A không nhận JSON của B |
| Rate limiter phân tán | Redis, nhiều caller/instance mô phỏng | Atomic quota, 429 đúng consumer |
| Outbox publish và event trùng | PostgreSQL + broker | Không mất intent; consumer không tạo side effect trùng |
| Timeout sau provider đã ghi effect | Fake provider có state/lookup | Reconcile cùng idempotency key |
| Access token sai audience | Spring Resource Server + test JWT/JWKS | 401 từ decoder thật |
| Preflight và ACAO | Spring MVC/Security | Header CORS đúng, không nhầm với browser E2E |
| API gặp database thật không sẵn sàng | PostgreSQL container có fault injection | Lỗi được ánh xạ phù hợp; không retry vô hạn |

Cần tránh quan niệm “có container nên phải kiểm mọi thứ trong một test dài”. Thay vào đó, mỗi test có **một bất biến chính** và fixture riêng; suite tổng hợp nhiều tầng để bảo đảm hợp đồng API.

## 14. Bài tập thực hành

### Bài tập 1 — Đổi repository test từ H2 sang PostgreSQL

Một `@DataJpaTest` hiện dùng H2. Repository có query native `ON CONFLICT`, `JSONB` và index unique theo tenant/idempotency key.

Yêu cầu: khai báo `PostgreSQLContainer`, `@ServiceConnection`, `@AutoConfigureTestDatabase(replace = NONE)` và dependency cần thiết. Bật migration thật, viết test insert hai lần cùng key kiểm unique violation; kiểm SQL `JSONB` đã hoạt động trong PostgreSQL.

**Tiêu chí đạt:** JDBC URL trỏ container, không phải H2; schema từ migration, test fail khi bỏ unique constraint hoặc native SQL sai.

### Bài tập 2 — Kiểm chứng BOLA trên dữ liệu thật

Dựng hai tenant, A có An/Bình, B có Chi. Tạo một order của An và một order của Chi. API yêu cầu `orders.read`.

Yêu cầu: dùng `MockMvc` + PostgreSQL container kiểm An đọc đúng đơn A (200), đọc đơn B (404 theo policy), thiếu scope (403), không token (401). Sau đó giải thích vì sao test `jwt()` không kiểm chữ ký/audience JWT và thiết kế test decoder thật.

**Tiêu chí đạt:** Có dữ liệu đa tenant trong DB thật, test chặn truy cập chéo và có kế hoạch auth integration test riêng.

### Bài tập 3 — Tạo đơn cùng Idempotency-Key từ nhiều thread

Tạo 20 request đồng thời dùng cùng `tenant, subject, key, fingerprint`. Service hiện kiểm `findByKey` rồi `save`; khi chạy nhanh sinh duplicate.

Yêu cầu: thiết kế unique constraint, transaction boundary xử lý conflict, same-key replay và test đa thread có barrier. Kiểm `COUNT(*)=1`, response cùng operation, outbox chỉ có một logical effect. Thử thêm cùng key nhưng fingerprint khác trả 409.

**Tiêu chí đạt:** Test bắt race thật và không trông cậy `synchronized` trong một JVM.

### Bài tập 4 — Redis cache không được rò tenant

App cache `GET /orders?page=1` dưới key `orders:page:1`. Dữ liệu thực nằm ở PostgreSQL, Redis lưu response.

Yêu cầu: chạy hai container PostgreSQL + Redis; seed tenant A/B; gọi API từ A rồi B có cùng path; chứng minh key cũ gây rò, sửa key theo tenant/caller/permission/filter rồi viết test khẳng định B không nhận dữ liệu A. Bổ sung test invalidation sau PATCH.

**Tiêu chí đạt:** Cache hit/miss và dữ liệu DB được kiểm thật, không chỉ assert tên key trong Java code.

### Bài tập 5 — Test outbox và message trùng

Ứng dụng tạo order + outbox trong cùng PostgreSQL transaction, publisher đưa event vào broker, consumer cập nhật projection.

Yêu cầu: khởi PostgreSQL và broker container, giả lập publisher crash sau khi gửi nhưng trước khi đánh dấu `published_at`, phát lại event và kiểm consumer chỉ tạo một side effect. Sử dụng waiting theo điều kiện với timeout rõ thay vì ngủ cố định.

**Tiêu chí đạt:** Có bằng chứng DB/broker thực tế, vẫn chịu được at-least-once delivery.

### Bài tập 6 — Thiết kế CI đáng tin và ngân sách chạy

Một pipeline có 180 integration test. Mỗi test method tạo PostgreSQL mới, image tag `latest`, cleanup bằng `TRUNCATE` khi nhiều test chạy parallel, và thường đỏ vì `Connection refused`.

Yêu cầu: đề xuất lại lifecycle theo class/suite, image pin, fixture isolation, context-cache policy, concurrency, log và báo cáo lỗi CI. Phân biệt lỗi hạ tầng với lỗi assertion. Nêu trường hợp nào **không** nên dùng container mà dùng unit test sẽ tốt hơn.

**Tiêu chí đạt:** Test tái lập trên runner có Docker, không phụ thuộc thứ tự, không xóa dữ liệu test khác, và có log để điều tra lỗi.

### Bài tập 7 — Test transaction rollback không đủ

Một `@SpringBootTest(webEnvironment = RANDOM_PORT)` có `@Transactional` trên test method. Test gửi `POST /orders`, sau test vẫn thấy order trong DB.

Yêu cầu: giải thích transaction ở server thread, so sánh với `MockMvc`, đề xuất cleanup hoặc schema/database riêng, kiểm cả outbox và async worker. Tạo test thứ hai chứng minh dữ liệu case trước không làm thay đổi kết quả.

**Tiêu chí đạt:** Không giả định rollback của test thread bao trùm request HTTP/consumer khác thread.

## 15. Câu hỏi tự kiểm tra

1. **Testcontainers có dùng dữ liệu production không?** Không bắt buộc và không nên; nó chạy service thật với fixture tổng hợp.
2. **Có Testcontainers thì unit test trở thành E2E?** Không; mức test phụ thuộc code/luồng thực sự được chạy.
3. **Vì sao không hardcode `localhost:5432`?** Host/mapped port được phân bổ động; dùng connection details hoặc `getJdbcUrl()`.
4. **Khác nhau giữa `@ServiceConnection` và `@DynamicPropertySource`?** Một cách để Boot tạo connection details, cách kia khai báo thuộc tính động trực tiếp; không cần dùng cả hai cho cùng datasource.
5. **Vì sao `@DataJpaTest` cần chú ý `@AutoConfigureTestDatabase`?** Test slice có thể tự thay DataSource thành embedded DB.
6. **Rollback của test method có rollback một POST gửi qua `RANDOM_PORT` không?** Không bảo đảm; server xử lý trong thread/transaction riêng.
7. **Làm sao xác minh idempotency khi có race?** Chạy đồng thời và kiểm DB unique constraint cùng số tác dụng phụ, không chỉ gọi hai lần tuần tự.
8. **`jwt()` trong MockMvc có kiểm chữ ký JWT thật?** Không; cần test Bearer token qua decoder/JWKS tin cậy.
9. **Khi nào cần Redis thật?** Khi TTL, atomic operation, serialization, key collision hoặc hành vi cache là phần cần chứng minh.
10. **Testcontainers tự chạy migration và bảo vệ RLS không?** Không; migration và quyền DB là trách nhiệm cấu hình của ứng dụng/test.
11. **Tại sao test xanh riêng nhưng đỏ khi chạy cả suite?** Thường do state shared, cleanup, container lifecycle, context caching hoặc concurrency không được kiểm soát.
12. **Có nên dùng fixed sleep chờ consumer xử lý?** Không; chờ điều kiện nghiệp vụ với timeout và chẩn đoán khi quá hạn.

## 16. Tài liệu và checklist triển khai

Nguồn tham khảo để đối chiếu API theo version đang dùng:

- **Testcontainers for Java — Getting Started:** https://java.testcontainers.org/quickstart/junit_5_quickstart/
- **Testcontainers — JUnit 5 Jupiter:** https://java.testcontainers.org/test_framework_integration/junit_5/
- **Testcontainers — PostgreSQL module:** https://java.testcontainers.org/modules/databases/postgres/
- **Testcontainers — Networking and ports:** https://java.testcontainers.org/features/networking/
- **Spring Boot — Testcontainers support, service connections:** https://docs.spring.io/spring-boot/reference/testing/testcontainers.html
- **Spring Boot — Testing slices:** https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- **Spring Framework — Dynamic Property Sources:** https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dynamicpropertysource.html
- **Spring Security — Testing:** https://docs.spring.io/spring-security/reference/servlet/test/index.html
- **PostgreSQL — Transactions, Constraints and Row Security:** https://www.postgresql.org/docs/current/

Trước khi coi một integration test là bằng chứng bảo vệ REST API, hãy xác nhận:

- Test đã chạy **đúng loại/version dependency** cần kiểm (PostgreSQL, Redis, broker), không âm thầm chuyển sang mock/H2?
- Schema được khởi tạo bằng **migration thật**, fixture độc lập và dữ liệu synthetic?
- Kết nối dùng host/port động từ Testcontainers, không dựa trên DB local đã có dữ liệu?
- Assertion kiểm **HTTP response và trạng thái DB/effect** chứ không chỉ status 200?
- Có thử lỗi: unique conflict, wrong tenant, missing scope, timeout, trùng message và transaction rollback?
- Test phân biệt security mock `jwt()` với kiểm JWT decoder thật?
- Lifecycle container tương thích cached Spring context; test parallel không xóa dữ liệu nhau?
- CI runner chạy được container, có log/report/timeout phù hợp và image được pin?
- Các hành vi không liên quan DB/protocol vẫn được kiểm bằng unit test để suite nhanh?
- Testcontainers không được dùng như lý do bỏ contract test và end-to-end test cần thiết?

**Điểm cốt lõi:** Testcontainers đưa **phụ thuộc tích hợp thật** vào vòng kiểm thử Java/Spring để xác minh những bất biến mà mock không chứng minh được: schema, constraint, transaction, query, cache và event. Giá trị cao nhất đến từ việc chọn đúng test boundary, seed dữ liệu có chủ đích, kiểm tác dụng phụ thực tế, và bảo đảm suite chạy lại được trên cả máy developer lẫn CI.
