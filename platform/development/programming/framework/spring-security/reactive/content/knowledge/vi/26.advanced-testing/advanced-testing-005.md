# Kiểm thử phân quyền chủ sở hữu và truy cập chéo tenant trong Spring Security WebFlux

> **Chủ đề:** Spring Security - reactive → Kiểm thử chuyên sâu → Kiểm thử phân quyền chủ sở hữu và truy cập chéo tenant. Bài tập trung vào kiểm thử ủy quyền ở cấp đối tượng và ranh giới tenant trong ứng dụng WebFlux dùng Reactor, JWT và dữ liệu bất đồng bộ.

## 1. Mục tiêu và mô hình đe dọa

Sau bài này, người học có thể thiết kế và chạy các phép thử chứng minh rằng một người dùng đã đăng nhập vẫn không thể đọc, sửa, xóa hoặc liệt kê dữ liệu thuộc người khác hoặc thuộc tenant khác. Cần phân biệt rõ:

- **Authentication (xác thực):** token hợp lệ chứng minh danh tính. Thiếu/sai thông tin xác thực thường nhận HTTP 401.
- **Quyền chức năng:** vai trò/scope quyết định được gọi API nào. Thiếu scope thường nhận HTTP 403.
- **Quyền trên đối tượng (object-level authorization):** dù có scope đọc/ghi, người dùng chỉ được thao tác bản ghi mà chính sách cho phép. IDOR/BOLA xảy ra khi đổi ID trong URL là lấy được dữ liệu của người khác.
- **Cách ly tenant:** người dùng thuộc tenant A không được truy cập dữ liệu tenant B, kể cả hai tenant dùng cùng giá trị user ID, tên tài nguyên hoặc số thứ tự.
- **Horizontal escalation:** người dùng A đọc/sửa tài nguyên của người dùng B cùng cấp. **Cross-tenant escalation:** người dùng A vượt ranh giới khách hàng/tổ chức. Đây là hai trục kiểm thử độc lập.

Mỗi request phải có một ngữ cảnh tin cậy: ví dụ **subject** và **tenant_id** từ JWT đã được xác thực; resource ID đến từ path; owner ID và tenant ID thực tế đến từ dữ liệu lưu trữ. Không lấy subject/tenant để quyết định quyền từ header hoặc JSON body do client tự khai.

## 2. Chính sách cần chuyển thành bất biến kiểm thử

Giả sử API quản lý ghi chú riêng tư: **GET /notes/{id}** và **PUT /notes/{id}**. Một ghi chú có **id, tenant_id, owner_id, content**. Chính sách ví dụ của bài: chỉ chủ sở hữu trong đúng tenant mới được đọc và cập nhật; scope **notes.read** và **notes.write** là điều kiện bắt buộc bổ sung. Chính sách khác như quản trị viên được phép đọc thay phải được định nghĩa và kiểm thử riêng; tuyệt đối không tự suy ra quyền quản trị từ việc sở hữu scope chung.

Một request thành công phải đồng thời thỏa:

1. Token được bộ lọc bảo mật xác thực.
2. Có đúng scope theo HTTP method.
3. Claim **sub** và **tenant_id** tồn tại, không rỗng và có nguồn tin cậy.
4. Bản ghi được truy vấn trong **tenant_id** hiện tại.
5. **owner_id** của bản ghi phù hợp **sub** (hoặc thỏa chính sách chia sẻ đã quy định).
6. Mọi mutation kiểm tra điều kiện tenant/owner ngay tại lệnh ghi; kiểm tra trước rồi ghi sau không tự động an toàn trước race condition.

Ví dụ chính sách phản hồi: **401** khi chưa xác thực; **403** khi đã xác thực nhưng thiếu scope/claim bắt buộc; **404** khi ID không tồn tại hoặc không thể nhìn thấy do sai tenant/sai owner. Gộp 404 cho các trường hợp đối tượng giúp hạn chế dò ID; một hệ thống có thể chọn 403 cho đối tượng bị cấm nếu chính sách công bố cho phép, nhưng test phải thống nhất và không rò rỉ sự tồn tại qua body, timing, log hoặc phân trang.

### Ma trận kiểm thử tối thiểu

| Principal | Tenant trong token | Tài nguyên | Scope | Kỳ vọng |
| --- | --- | --- | --- | --- |
| alice | tenant-a | Ghi chú của alice tại tenant-a | notes.read | GET 200 |
| alice | tenant-a | Ghi chú của bob tại tenant-a | notes.read | GET 404 |
| alice | tenant-a | Ghi chú của alice tại tenant-b | notes.read | GET 404 |
| alice | tenant-b | Ghi chú của alice tại tenant-b | notes.read | GET 200 |
| alice | tenant-a | Ghi chú của tenant-b, tự gửi header X-Tenant-Id=tenant-b | notes.read | GET 404 |
| alice | tenant-a | Ghi chú của alice tại tenant-a | scope khác | GET 403 |
| Không có token | — | Bất kỳ ghi chú | — | GET 401 |
| alice với token thiếu tenant_id | — | Bất kỳ ghi chú | notes.read | GET 403 |
| alice | tenant-a | Ghi chú của alice tại tenant-b | notes.write | PUT 404, dữ liệu không đổi |
| alice | tenant-a | Ghi chú của alice tại tenant-a | notes.write | PUT 200, dữ liệu được cập nhật |

**Điểm mấu chốt:** kiểm tra response bị từ chối và kiểm tra **trạng thái dữ liệu sau request**. Một API có thể trả 403/404 nhưng đã tạo side effect từ trước đó; đó vẫn là lỗi bảo mật.

## 3. Ví dụ chạy kiểm thử HTTP → SecurityWebFilterChain → Service → Repository

Fixture nhỏ dưới đây dùng Spring Boot 3.3.x, Java 17+, JUnit 5, WebFlux và Spring Security. Repository lưu trong bộ nhớ chỉ để bài test chạy độc lập với database; ở môi trường thật phải thay bằng query tenant-scoped (mục 5). Test dùng **mockJwt()** của spring-security-test để dựng Authentication đáng tin cậy bên trong test. Nó **không** kiểm tra chữ ký JWT, issuer, audience hoặc JWK; các thuộc tính đó cần một nhóm kiểm thử decoder/resource server riêng.

Cấu trúc:

~~~text
settings.gradle
build.gradle
src/main/java/example/tenant/TenantNoteApplication.java
src/test/java/example/tenant/TenantNoteSecurityTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'tenant-note-security-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/main/java/example/tenant/TenantNoteApplication.java**

~~~java
package example.tenant;

import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class TenantNoteApplication {
    public static void main(String[] args) {
        SpringApplication.run(TenantNoteApplication.class, args);
    }
}

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
class SecurityConfiguration {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                // Phù hợp với demo API dùng Bearer JWT, không dùng cookie session.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/notes/**")
                        .hasAuthority("SCOPE_notes.read")
                        .pathMatchers(HttpMethod.PUT, "/notes/**")
                        .hasAuthority("SCOPE_notes.write")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}

record Note(UUID id, String tenantId, String ownerId, String content) {}
record NoteView(UUID id, String content) {}
record NoteUpdate(String content) {}

@Repository
class NoteRepository {
    private final ConcurrentMap<UUID, Note> notes = new ConcurrentHashMap<>();

    NoteRepository() {
        reset();
    }

    void reset() {
        notes.clear();
        notes.put(UUID.fromString("00000000-0000-0000-0000-000000000001"),
                new Note(UUID.fromString("00000000-0000-0000-0000-000000000001"),
                        "tenant-a", "alice", "private-a-alice"));
        notes.put(UUID.fromString("00000000-0000-0000-0000-000000000002"),
                new Note(UUID.fromString("00000000-0000-0000-0000-000000000002"),
                        "tenant-a", "bob", "private-a-bob"));
        notes.put(UUID.fromString("00000000-0000-0000-0000-000000000003"),
                new Note(UUID.fromString("00000000-0000-0000-0000-000000000003"),
                        "tenant-b", "alice", "private-b-alice"));
    }

    Mono<Note> findByTenantAndId(String tenantId, UUID id) {
        return Mono.defer(() -> Mono.justOrEmpty(notes.get(id))
                .filter(note -> note.tenantId().equals(tenantId)));
    }

    // Kiểm tra tenant và owner ngay trong thao tác ghi nguyên tử của fixture.
    Mono<Note> updateOwned(String tenantId, String ownerId, UUID id, String content) {
        return Mono.defer(() -> {
            Note result = notes.computeIfPresent(id, (key, existing) ->
                    existing.tenantId().equals(tenantId)
                            && existing.ownerId().equals(ownerId)
                            ? new Note(id, tenantId, ownerId, content)
                            : existing);
            return Mono.justOrEmpty(result)
                    .filter(note -> note.tenantId().equals(tenantId)
                            && note.ownerId().equals(ownerId));
        });
    }
}

@Service
class NoteService {
    private final NoteRepository repository;

    NoteService(NoteRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('SCOPE_notes.read')")
    public Mono<NoteView> read(UUID id, String subject, String tenantId) {
        if (missing(subject) || missing(tenantId)) {
            return Mono.error(new ResponseStatusException(HttpStatus.FORBIDDEN));
        }
        return repository.findByTenantAndId(tenantId, id)
                .filter(note -> note.ownerId().equals(subject))
                .map(note -> new NoteView(note.id(), note.content()))
                .switchIfEmpty(Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND)));
    }

    @PreAuthorize("hasAuthority('SCOPE_notes.write')")
    public Mono<NoteView> update(UUID id, String subject, String tenantId,
                                 NoteUpdate request) {
        if (missing(subject) || missing(tenantId)) {
            return Mono.error(new ResponseStatusException(HttpStatus.FORBIDDEN));
        }
        if (request.content() == null || request.content().isBlank()) {
            return Mono.error(new ResponseStatusException(HttpStatus.BAD_REQUEST));
        }
        return repository.updateOwned(tenantId, subject, id, request.content())
                .map(note -> new NoteView(note.id(), note.content()))
                .switchIfEmpty(Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND)));
    }

    private static boolean missing(String value) {
        return value == null || value.isBlank();
    }
}

@RestController
@RequestMapping("/notes")
class NoteController {
    private final NoteService service;

    NoteController(NoteService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    Mono<NoteView> read(@PathVariable UUID id, @AuthenticationPrincipal Jwt jwt) {
        return service.read(id, jwt.getSubject(), jwt.getClaimAsString("tenant_id"));
    }

    @PutMapping("/{id}")
    Mono<NoteView> update(@PathVariable UUID id, @RequestBody Mono<NoteUpdate> body,
                          @AuthenticationPrincipal Jwt jwt) {
        return body.flatMap(request ->
                service.update(id, jwt.getSubject(), jwt.getClaimAsString("tenant_id"), request));
    }
}
~~~

Trong fixture, **findByTenantAndId** lọc tenant trước khi kiểm tra chủ sở hữu; **updateOwned** không làm hai bước đọc-kiểm-tra-ghi riêng lẻ. Phương thức trả về **Mono** và không gọi **block()**. SecurityWebFilterChain xử lý scope ở HTTP layer; @PreAuthorize bảo vệ service nếu có caller khác ngoài controller; điều kiện tenant/owner vẫn được thực hiện trong domain/data layer.

**src/test/java/example/tenant/TenantNoteSecurityTest.java**

~~~java
package example.tenant;

import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class TenantNoteSecurityTest {
    private static final UUID ALICE_A =
            UUID.fromString("00000000-0000-0000-0000-000000000001");
    private static final UUID BOB_A =
            UUID.fromString("00000000-0000-0000-0000-000000000002");
    private static final UUID ALICE_B =
            UUID.fromString("00000000-0000-0000-0000-000000000003");

    @Autowired ApplicationContext context;
    @Autowired NoteRepository repository;

    // Đủ để khởi tạo OAuth2 Resource Server trong fixture HTTP test.
    @MockBean ReactiveJwtDecoder jwtDecoder;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        repository.reset();
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    private WebTestClient actor(String subject, String tenant, String scope) {
        return client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.subject(subject).claim("tenant_id", tenant))
                .authorities(new SimpleGrantedAuthority("SCOPE_" + scope)));
    }

    @Test
    void ownerCanReadWithinOwnTenant() {
        actor("alice", "tenant-a", "notes.read")
                .get().uri("/notes/{id}", ALICE_A)
                .exchange().expectStatus().isOk()
                .expectBody()
                .jsonPath("$.content").isEqualTo("private-a-alice");
    }

    @Test
    void peerInSameTenantCannotRead() {
        actor("alice", "tenant-a", "notes.read")
                .get().uri("/notes/{id}", BOB_A)
                .exchange().expectStatus().isNotFound();
    }

    @Test
    void sameSubjectInDifferentTenantCannotRead() {
        actor("alice", "tenant-a", "notes.read")
                .get().uri("/notes/{id}", ALICE_B)
                .exchange().expectStatus().isNotFound();

        actor("alice", "tenant-b", "notes.read")
                .get().uri("/notes/{id}", ALICE_B)
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.content").isEqualTo("private-b-alice");
    }

    @Test
    void clientSuppliedTenantAndUserHeadersDoNotOverrideJwt() {
        actor("alice", "tenant-a", "notes.read")
                .get().uri("/notes/{id}", ALICE_B)
                .header("X-Tenant-Id", "tenant-b")
                .header("X-User-Id", "bob")
                .exchange().expectStatus().isNotFound();
    }

    @Test
    void noAuthenticationIsUnauthorized() {
        client.get().uri("/notes/{id}", ALICE_A)
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void wrongScopeIsForbidden() {
        actor("alice", "tenant-a", "unrelated")
                .get().uri("/notes/{id}", ALICE_A)
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void missingTenantClaimIsForbidden() {
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt.subject("alice"))
                        .authorities(new SimpleGrantedAuthority("SCOPE_notes.read")))
                .get().uri("/notes/{id}", ALICE_A)
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void deniedWriteMustNotChangeOtherTenantData() {
        actor("alice", "tenant-a", "notes.write")
                .put().uri("/notes/{id}", ALICE_B)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NoteUpdate("intrusion"))
                .exchange().expectStatus().isNotFound();

        actor("alice", "tenant-b", "notes.read")
                .get().uri("/notes/{id}", ALICE_B)
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.content").isEqualTo("private-b-alice");
    }

    @Test
    void deniedWriteMustNotChangeOtherOwnersData() {
        actor("alice", "tenant-a", "notes.write")
                .put().uri("/notes/{id}", BOB_A)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NoteUpdate("intrusion"))
                .exchange().expectStatus().isNotFound();

        actor("bob", "tenant-a", "notes.read")
                .get().uri("/notes/{id}", BOB_A)
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.content").isEqualTo("private-a-bob");
    }

    @Test
    void ownerCanUpdateOwnNote() {
        actor("alice", "tenant-a", "notes.write")
                .put().uri("/notes/{id}", ALICE_A)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NoteUpdate("updated-by-owner"))
                .exchange().expectStatus().isOk();

        actor("alice", "tenant-a", "notes.read")
                .get().uri("/notes/{id}", ALICE_A)
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.content").isEqualTo("updated-by-owner");
    }
}
~~~

Chạy từ thư mục chứa **build.gradle** bằng **gradle test** (hoặc **./gradlew test** khi đã có Gradle Wrapper tương thích). Test không cần server HTTP ngoài hoặc IdP thật vì WebTestClient được gắn vào Spring ApplicationContext và **mockJwt()** cấp Authentication trong test. Kết quả mong đợi: mười trường hợp trên đều pass, với HTTP 200/401/403/404 như ma trận. Không suy ra từ test này rằng chữ ký JWT production đã được xác thực đúng.

**Lưu ý triển khai:** fixture chủ ý dùng **@MockBean** tương thích Boot 3.3.x; trong phiên bản Boot mới hơn có thể chuyển sang API mock bean tương ứng. Với ứng dụng phục vụ trình duyệt bằng cookie/session, không sao chép việc tắt CSRF của API Bearer-only.

## 4. Vì sao phải kiểm thử ở nhiều tầng

- **HTTP integration / WebTestClient:** chứng minh SecurityWebFilterChain, authentication principal, mapping route, status và service hoạt động xuyên suốt.
- **Service/method security:** dùng **StepVerifier** hoặc WebTestClient để chứng minh reactive authorization trên chuỗi publisher; với @PreAuthorize, caller phải mang security context trong **Reactor Context**. Không dùng **SecurityContextHolder.getContext()** kiểu ThreadLocal truyền thống để kết luận ngữ cảnh WebFlux.
- **Persistence integration:** tạo dữ liệu thực của hai tenant và hai owner, chạy query R2DBC với database thử nghiệm, kiểm tra truy vấn không trả dữ liệu ngoài scope và mutation không chạm hàng ngoài scope. Unit test mock repository quá rộng có thể che lỗi SQL thiếu điều kiện tenant.
- **JWT decoder/resource server:** kiểm riêng chữ ký, issuer, audience, hết hạn, key rotation, mapping scope/role và claim tenant; **mockJwt()** chỉ kiểm logic sau khi principal đã được tạo.
- **End-to-end:** với API gateway, forwarded headers, tenant resolution, cache và messaging thực, thử request qua đường vào production-like; không để gateway header trở thành nguồn quyền vô điều kiện.

Nếu test thuần service:
 
~~~java
// Pseudocode có chủ đích: tạo Authentication đúng ứng dụng rồi đưa
// vào Reactor Context; không sử dụng ThreadLocal cho WebFlux.
// StepVerifier.create(service.read(id, subject, tenant)
//         .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth)))
//     .expectErrorMatches(error -> /* chính sách mong đợi */)
//     .verify();
~~~

Đoạn trên là minh họa ngữ cảnh Reactor, **không phải** một test độc lập: phải định nghĩa **service**, **id**, **subject**, **tenant** và **auth** tương ứng. Các test WebTestClient phía trên là ví dụ đầy đủ có thể đưa vào project demo.

## 5. Đưa điều kiện vào SQL/R2DBC để tránh lộ dữ liệu

Trong hệ thống dùng database, đặt tenant vào **WHERE** của cả read và write. Dùng repository method name hoặc query rõ ràng; ví dụ cho PostgreSQL/Spring Data R2DBC:

~~~sql
-- Đọc một bản ghi sở hữu trong đúng tenant.
SELECT id, tenant_id, owner_id, content, version
FROM notes
WHERE id = :id
  AND tenant_id = :tenantId
  AND owner_id = :subject;

-- Ghi có kiểm soát quyền và chống lost update.
UPDATE notes
SET content = :content, version = version + 1
WHERE id = :id
  AND tenant_id = :tenantId
  AND owner_id = :subject
  AND version = :expectedVersion;
~~~

Đây là SQL minh họa với named binding parameters của lớp truy cập dữ liệu; khi chạy trực tiếp trong psql cần cú pháp bind tương ứng. Trong Spring Data R2DBC, lệnh UPDATE có thể dùng **@Modifying @Query** và kiểu trả về **Mono<Integer>** là số hàng bị tác động. **0 hàng** có thể do không thấy ID, sai tenant, sai owner hoặc xung đột version; phân loại phản hồi theo chính sách đã quyết định, tránh vô tình cho kẻ tấn công biết bản ghi có tồn tại.

Test persistence phải tạo ít nhất ba bản ghi: alice/tenant-a, bob/tenant-a và alice/tenant-b. Sau lệnh UPDATE trái phép, đối chiếu bản ghi gốc từ phiên kiểm thử có quyền đọc dữ liệu toàn cục (test fixture) để chắc chắn **row count = 0 và content/version không đổi**. Đối với danh sách, phân trang và tìm kiếm, tenant phải nằm trong **query trước** khi áp dụng limit/offset/count; lọc kết quả sau phân trang có thể làm lộ số lượng hoặc thứ tự dữ liệu tenant khác. Xem xét unique index theo tenant cho các natural key, khóa ngoại và joins có cả tenant, cũng như PostgreSQL Row-Level Security nếu được dùng như một lớp bảo vệ bổ sung; policy RLS và session/connection pool phải được test riêng.

## 6. Mở rộng test cho các đường tấn công thực tế

1. **GET một đối tượng:** ID không tồn tại, ID của đồng nghiệp cùng tenant, ID tenant khác, trùng subject giữa tenant; thử ID ngẫu nhiên và ID đoán được.
2. **List/search/export:** response body, totalElements, aggregation, cursor, sorting và file export chỉ chứa tenant hợp lệ; không trả kết quả ngoài scope rồi lọc bằng Java sau khi đã phân trang.
3. **POST/create:** client gửi **tenantId** hoặc **ownerId** giả trong body; server phải bỏ qua hoặc từ chối theo hợp đồng và gán danh tính từ nguồn tin cậy. Kiểm tra dữ liệu thực vừa tạo.
4. **PUT/PATCH/DELETE:** thay ID trong path, thay tenant/owner trong body, batch nhiều ID trộn hai tenant; reject toàn bộ hoặc xử lý từng phần theo hợp đồng rõ ràng, không phát sinh side effect ngoài scope.
5. **Quan hệ đối tượng:** tạo note của tenant A nhưng tham chiếu parent/project/attachment thuộc tenant B; mọi khóa ngoại có khả năng vượt tenant phải được kiểm tra, không chỉ kiểm tra bản ghi gốc.
6. **Cache và async:** cache key phải bao gồm tenant (và principal nếu kết quả cá nhân hóa); khi Reactor chuyển scheduler hoặc tạo publisher khác, truyền security context đúng cách. Message consumer, scheduled job, WebSocket, SSE và background process cần cơ chế tenant context tin cậy riêng.
7. **Scope/role:** thử đủ tổ hợp thiếu scope, thừa scope, role admin của tenant A truy cập tenant B, principal bị disable, tenant bị khóa. Quyền admin nội bộ và quyền admin của tenant là hai chính sách khác nhau.
8. **Request giả mạo:** thử header **X-Tenant-Id**, **X-User-Id**, query string, body JSON, forwarded headers; các giá trị này không được tự nâng quyền. Nếu gateway xác nhận tenant bằng header đã ký, chỉ tin header sau xác minh và có bảo vệ chống request trực tiếp.
9. **Race / TOCTOU:** gửi đồng thời update, transfer ownership, revoke membership và delete; dùng constraint/transaction/optimistic locking để bảo đảm mutation thực hiện theo điều kiện quyền tại thời điểm ghi.
10. **Không rò rỉ:** response lỗi không chứa title/content/owner/tenant bí mật, logs và tracing không phát tán token hoặc dữ liệu của tenant khác; status/timing khác nhau không làm lộ ID theo yêu cầu bảo mật.

Với case âm tính quan trọng, xây fixture chứa *dấu hiệu phân biệt* (canary) như nội dung **private-b-alice** rồi assert nó không xuất hiện trong response; đồng thời query lại database để kiểm tra bất biến. Nếu dùng test parameterized, mỗi trường hợp phải định danh rõ subject, tenant, scope, resource và hành động; tránh một mock trả 404 cho tất cả khiến test luôn xanh dù route/service không chạy.

## 7. Sai lầm thường gặp và cách bắt bằng test

| Sai lầm | Hậu quả | Test phát hiện |
| --- | --- | --- |
| Chỉ kiểm tra role hoặc @PreAuthorize mà không kiểm tra bản ghi | Có scope là đọc được mọi ID | Alice đọc ID của bob cùng tenant → phải bị từ chối |
| Chỉ kiểm tra owner_id, bỏ tenant_id | Subject trùng nhau giữa tenant gây truy cập chéo | Alice tenant-a đọc note Alice tenant-b → từ chối |
| Lấy tenant từ header/body do client tự gửi | Người dùng tự chọn tenant của nạn nhân | Header spoofing không đổi kết quả |
| Repository findById(id) rồi mới lọc dữ liệu | Có nguy cơ lộ dữ liệu qua log/joins/cache; mutation không atomic | DB integration và concurrent update |
| Chỉ assert HTTP status | Thao tác có thể đã ghi một phần trước khi trả lỗi | Assert giá trị/version không đổi sau request cấm |
| Dùng mock service trả 404 cho mọi yêu cầu | Test xanh giả, không kiểm tra thật domain authorization | Cần trường hợp 200 và kiểm tra side effect hợp lệ |
| Block(), subscribe() thủ công hoặc ThreadLocal tùy tiện | Mất/đảo reactive security context; side effect ngoài pipeline | Kiểm thử luồng bất đồng bộ và ngữ cảnh auth |
| Cache key theo ID nhưng thiếu tenant | Dữ liệu tenant trước rò sang tenant sau | Hai tenant cùng resource key, gọi xen kẽ |
| Chỉ test GET đơn lẻ | List, export, batch, liên kết vẫn bị BOLA | Bảng kiểm từng endpoint và từng đường truy vấn |

## 8. Checklist chấp nhận và giới hạn

Một triển khai có thể được coi là đạt bài thực hành khi: (1) có trường hợp tích cực GET/PUT 200 và kiểm tra dữ liệu đúng; (2) mọi trường hợp thiếu auth, scope, owner, tenant đều trả đúng chính sách; (3) đổi header/body/ID không vượt quyền; (4) read/list/write ở database có ràng buộc tenant và owner; (5) mutation bị cấm không tạo side effect; (6) JWT/resource server thực được kiểm bằng nhóm test riêng; (7) có kiểm tra race, pagination/cache và quan hệ object ở những endpoint triển khai thực tế.

**Giới hạn ví dụ:** repository trong bộ nhớ mô phỏng một cách cố ý, không tự chứng minh các tính chất transaction, foreign key, RLS, isolation level hoặc correctness của SQL production. Hãy chạy thêm integration test với database thực hoặc Testcontainers tương ứng trước khi kết luận khả năng cách ly tenant.