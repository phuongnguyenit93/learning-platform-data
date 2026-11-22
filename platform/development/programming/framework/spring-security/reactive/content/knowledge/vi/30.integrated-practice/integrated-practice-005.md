# Bảo vệ tài nguyên theo chủ sở hữu bằng phân quyền reactive ở tầng dịch vụ

## Mục tiêu và tình huống thực hành

Bài thực hành tổng hợp thuộc **Spring Security – reactive**. Giả sử một ứng dụng WebFlux quản lý tài liệu: mỗi tài liệu có `id`, `ownerId` và `text`. Cả Alice và Bob đều đăng nhập thành công với role `USER`. Alice được đọc, liệt kê và sửa tài liệu của Alice, nhưng **không được đọc hoặc sửa** tài liệu của Bob, ngay cả khi Alice biết chính xác ID tài liệu của Bob.

Sau bài này, bạn có thể:

1. Phân biệt **authentication** (ai đang gọi?), **quyền tổng quát theo role/authority** (được sử dụng tính năng nào?) và **phân quyền theo chủ sở hữu** (được thao tác trên *bản ghi cụ thể* nào?).
2. Đọc danh tính đáng tin cậy từ `ReactiveSecurityContextHolder` trong service, truyền qua `Mono`/`Flux` và trả lỗi đúng khi không đủ quyền.
3. Chặn việc rò rỉ dữ liệu trước khi phát `onNext`; không dùng `filter(...)` mà quên xử lý trường hợp thiếu quyền.
4. Bảo vệ cả thao tác **READ**, **LIST** và **UPDATE**; khi UPDATE, giữ việc kiểm chủ sở hữu và ghi dữ liệu trong một thao tác nguyên tử để hạn chế lỗ hổng TOCTOU.
5. Thiết lập WebFlux Security, chạy ví dụ Java 17+ và dùng `StepVerifier`/`WebTestClient` kiểm thử cả nhánh được phép lẫn bị từ chối.
6. Biết khi nào nên chọn HTTP `403` hoặc che giấu sự tồn tại của tài nguyên bằng `404`; tránh IDOR/BOLA (Broken Object Level Authorization).

**Trọng tâm:** phân quyền ở **tầng dịch vụ** vì cùng một dịch vụ có thể được gọi từ HTTP controller, event handler, tác vụ nội bộ hoặc API khác. `SecurityWebFilterChain` giới hạn cửa vào HTTP nhưng không tự kiểm owner của từng tài liệu trong kho dữ liệu.

## 1. Chính sách quyền phải có trước khi viết code

Với người dùng đã xác thực `alice`, giả sử hai bản ghi:

| ID | Chủ sở hữu trong kho dữ liệu | Nội dung ban đầu |
| --- | --- | --- |
| `doc-a` | `alice` | `Nội dung của Alice` |
| `doc-b` | `bob` | `Nội dung của Bob` |

Chính sách ví dụ:

| Actor | Thao tác | Tài nguyên | Kết quả |
| --- | --- | --- | --- |
| Alice (role USER) | GET | `doc-a` | Cho phép, trả dữ liệu |
| Alice (role USER) | GET | `doc-b` | Từ chối, không phát dữ liệu |
| Bob (role USER) | GET | `doc-b` | Cho phép |
| Alice (role USER) | PUT nội dung | `doc-a` | Cho phép, owner không đổi |
| Alice (role USER) | PUT nội dung | `doc-b` | Từ chối, dữ liệu Bob không đổi |
| Alice (role USER) | LIST | tất cả tài liệu | Chỉ được thấy tài liệu của Alice |
| Người chưa đăng nhập | mọi thao tác bảo vệ | bất kỳ | Không có principal đáng tin cậy để cấp quyền |
| Alice | GET | ID không tồn tại | 404, khác lỗi không đủ quyền theo chính sách demo |

**Role USER là điều kiện cần, không đủ.** `hasRole('USER')` ở tầng HTTP chỉ chứng minh actor là thành viên nhóm được sử dụng API. Cả Alice và Bob đều có cùng role, nên kiểm tra role không thể thay thế điều kiện `document.ownerId == authenticatedUserId`.

**Nguồn danh tính:** lấy từ `Authentication` do Spring Security tạo sau khi kiểm credentials/token. Không lấy chủ sở hữu mong muốn từ `?owner=alice`, HTTP header `X-User` hay field `ownerId` do client gửi. ID từ URL chỉ định **đối tượng muốn thao tác**, không chứng minh caller có quyền với đối tượng đó.

**Về `authentication.name`:** trong demo, username chính là ID owner. Ứng dụng thực tế nên dùng **subject/user ID ổn định** từ principal đã xác thực (ví dụ account UUID hoặc `sub` trong JWT) vì username/email có thể đổi, và phải giới hạn theo tenant khi dữ liệu đa tenant. Tất cả so sánh phải dùng cùng một hệ định danh với cột `owner_id` của database.

## 2. Đặt kiểm tra đúng vị trí trong reactive pipeline

Luồng đọc tài liệu theo chính sách demo:

~~~text
HTTP GET /documents/doc-b
    |
    v
SecurityWebFilterChain
    |  kiểm authenticated + ROLE_USER
    v
DocumentController
    |
    v
DocumentService.readById("doc-b")
    |  lấy principal từ ReactiveSecurityContextHolder
    |  repository.findById("doc-b") -> Mono<Document>
    |  so ownerId với trusted principal
    +-- bằng nhau --> Mono.just(document) --> onNext + onComplete
    |
    +-- khác nhau -> Mono.error(AccessDeniedException)
                        --> không phát onNext(document)
~~~

Tại service, viết `flatMap` để so sánh **sau khi repository phát đối tượng**, trước khi đưa đối tượng đến caller. Nếu không đủ quyền, tạo `Mono.error(new AccessDeniedException(...))`; đừng `doOnNext(logicCheck)` mà vẫn để dữ liệu chảy xuống. Có thể chủ động truy vấn `WHERE id=? AND owner_id=?` để không tải bản ghi người khác từ database, nhất là với dữ liệu nhạy cảm.

**Vì sao kiểm owner ở service, không chỉ controller?** Controller có thể bị tái sử dụng hoặc có thêm endpoint mới. Một service công khai `repository.findById(id)` mà không kiểm owner dễ gây IDOR khi controller khác vô tình gọi thẳng. Kiểm chính sách tại ranh giới service bảo đảm mọi caller sử dụng cùng quy tắc.

**Vì sao `@PostAuthorize` một mình không phù hợp cho UPDATE?** Kiểm kết quả sau khi phương thức chạy có thể ngăn trả dữ liệu nhưng **tác dụng phụ ghi/xóa đã diễn ra**. Với thao tác cập nhật, quyền phải được thực thi **trước hoặc đồng thời với thao tác ghi**; ưu tiên truy vấn điều kiện nguyên tử trong database.

## 3. Cấu hình dependencies và WebFlux Security

Ví dụ giả định dự án Spring Boot 3.x/Java 17+ đã cấu hình Boot plugin/BOM và Gradle wrapper. Các dependencies cần có trong `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tạo package `demo.ownership` và các file được ghi rõ bên dưới. Đây là **demo có thể chạy** với kho dữ liệu in-memory `ConcurrentHashMap` để tập trung vào logic security. Ứng dụng thực tế nên thay repository bằng R2DBC/reactive driver và áp dụng truy vấn có điều kiện tại database.

### File 1 — `src/main/java/demo/ownership/OwnershipApplication.java`

~~~java
package demo.ownership;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
public class OwnershipApplication {

    public static void main(String[] args) {
        SpringApplication.run(OwnershipApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        // Tài khoản demo, KHÔNG dùng password hard-code trong production.
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER")
            .build();
        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob-pass"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(alice, bob);
    }

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/documents", "/documents/**")
                    .hasRole("USER")
                .anyExchange().denyAll())
            .httpBasic(withDefaults())
            .build();
    }
}
~~~

`@EnableWebFluxSecurity` và `ServerHttpSecurity` cấu hình **reactive HTTP filter chain**; chúng khác `@EnableWebSecurity` và `HttpSecurity` của Servlet. `hasRole("USER")` mặc định đòi authority `ROLE_USER`. Password được hash bằng `PasswordEncoder`; tên và mật khẩu cố định chỉ dùng cho môi trường demo. `anyExchange().denyAll()` tránh vô tình mở thêm route ngoài phạm vi.

Ở đây **giữ bảo vệ CSRF mặc định**. Với test HTTP `PUT`, phải cung cấp CSRF token hợp lệ (test `WebTestClient` bên dưới dùng `csrf()`). Một lệnh curl PUT có Basic credentials nhưng thiếu CSRF token có thể bị 403 **trước cả khi vào service**; điều đó không chứng minh kiểm chủ sở hữu hoạt động. Không vô hiệu hóa CSRF cho ứng dụng dùng credential tự động gửi từ trình duyệt nếu chưa đánh giá mô hình xác thực và nguy cơ CSRF.

### File 2 — `src/main/java/demo/ownership/Document.java`

~~~java
package demo.ownership;

public record Document(
    String id,
    String ownerId,
    String text
) {}
~~~

`Document` là Java record bất biến. Trong demo, `ownerId` được lưu trong kho và **không thể thay từ request chỉnh text**. Điều này tránh kiểu mass assignment: client gửi JSON với field `ownerId` rồi làm chủ tài liệu của người khác. Trong hệ thống thật, nên có entity persistence và DTO riêng cho read/write, không ánh xạ trực tiếp mọi field client gửi vào entity.

### File 3 — `src/main/java/demo/ownership/InMemoryDocuments.java`

~~~java
package demo.ownership;

import java.util.concurrent.ConcurrentHashMap;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Repository;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Repository
public final class InMemoryDocuments {

    private final ConcurrentHashMap<String, Document> data =
        new ConcurrentHashMap<>();

    public InMemoryDocuments() {
        data.put("doc-a", new Document(
            "doc-a", "alice", "Nội dung của Alice"));
        data.put("doc-b", new Document(
            "doc-b", "bob", "Nội dung của Bob"));
    }

    public Mono<Document> findById(String id) {
        return Mono.defer(() -> Mono.justOrEmpty(data.get(id)));
    }

    public Flux<Document> findByOwner(String ownerId) {
        return Flux.defer(() -> Flux.fromIterable(data.values())
            .filter(doc -> doc.ownerId().equals(ownerId)));
    }

    // Kiểm chủ sở hữu và ghi tại cùng một thao tác nguyên tử.
    public Mono<Document> replaceTextIfOwned(
            String id, String trustedOwner, String newText) {

        return Mono.fromSupplier(() -> {
            Document result = data.computeIfPresent(id, (key, old) -> {
                if (!old.ownerId().equals(trustedOwner)) {
                    throw new AccessDeniedException("Not the owner");
                }
                if (newText == null || newText.isBlank()) {
                    throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "Text must not be blank");
                }
                return new Document(old.id(), old.ownerId(), newText);
            });

            if (result == null) {
                throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Document not found");
            }
            return result;
        });
    }
}
~~~

`ConcurrentHashMap.computeIfPresent` khóa logic sửa theo khóa cho demo; nó chỉ thay `text` nếu chủ sở hữu của **giá trị hiện tại** trùng `trustedOwner`, nên không có khoảng trống giữa “kiểm owner” và “ghi”. Trong database, cần một truy vấn có predicate owner tương đương, không dùng `ConcurrentHashMap` hoặc khóa JVM để thay thế transaction giữa nhiều instance.

`Mono.defer` và `Mono.fromSupplier` tạo nguồn **lazy**: đọc hoặc ghi chỉ xảy ra khi subscribe. Repo in-memory không làm blocking I/O; nếu thay bằng JDBC/JPA đồng bộ, không được tự gọi chúng trên event-loop. Dùng R2DBC/reactive driver hoặc cô lập legacy blocking call phù hợp; đừng chỉ bọc vào `Mono.just(...)`.

**Giới hạn demo:** `findByOwner` duyệt toàn bộ map, hợp lý khi có vài fixture; production phải filter theo owner ở database và phân trang, không tải toàn bộ bản ghi của mọi người rồi `Flux.filter` trên app.

### File 4 — `src/main/java/demo/ownership/DocumentService.java`

~~~java
package demo.ownership;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public final class DocumentService {

    private final InMemoryDocuments documents;

    public DocumentService(InMemoryDocuments documents) {
        this.documents = documents;
    }

    private Mono<String> trustedUsername() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx ->
                Mono.justOrEmpty(ctx.getAuthentication()))
            .filter(Authentication::isAuthenticated)
            .filter(auth ->
                !(auth instanceof AnonymousAuthenticationToken))
            .map(Authentication::getName)
            .switchIfEmpty(Mono.error(
                new AccessDeniedException("Authentication required")));
    }

    public Mono<Document> readById(String id) {
        return trustedUsername().flatMap(username ->
            documents.findById(id)
                .switchIfEmpty(Mono.error(
                    new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Document not found")))
                .flatMap(doc -> doc.ownerId().equals(username)
                    ? Mono.just(doc)
                    : Mono.error(new AccessDeniedException(
                        "Not the owner"))));
    }

    public Flux<Document> listMine() {
        return trustedUsername()
            .flatMapMany(documents::findByOwner);
    }

    public Mono<Document> replaceText(String id, String newText) {
        return trustedUsername().flatMap(username ->
            documents.replaceTextIfOwned(id, username, newText));
    }
}
~~~

**Đọc kỹ `trustedUsername()`:** authentication đi từ Reactor Context, được lọc để bỏ null, trạng thái unauthenticated và anonymous; chỉ sau đó mới lấy username. `Authentication.isAuthenticated()` không nhất thiết loại mọi `AnonymousAuthenticationToken`, nên cần kiểm riêng. Trong ứng dụng có OAuth2/JWT, hãy lấy user ID ổn định từ principal đã xác thực thay vì mặc định dùng username.

Tại `readById`, bản ghi chỉ đi vào `Mono.just(doc)` nếu đúng chủ sở hữu. Khi sai, downstream nhận `AccessDeniedException` dưới dạng `onError`, **không nhận `onNext(doc)`**. Nếu tài liệu không tồn tại, service trả `ResponseStatusException(HttpStatus.NOT_FOUND)`. Đây là **chính sách demo**: authenticated caller có thể phân biệt `403` (ID tồn tại nhưng không sở hữu) và `404` (không tồn tại). Nếu cần chống dò ID, chọn chính sách gộp hai trường hợp thành 404 và ghi log nội bộ; áp dụng nhất quán tại read/list/update.

`listMine` lấy chủ sở hữu đáng tin rồi gọi repository filter theo chủ sở hữu. Nếu có nhiều trang kết quả, cần bảo đảm **mọi trang** đều có owner predicate, không chỉ lọc trên một page đã lấy từ dữ liệu chung. Cách “query toàn bộ + lọc sau” còn có nguy cơ phân trang rỗng, đếm tổng bản ghi sai và kéo tải dữ liệu không cần thiết.

`replaceText` cũng lấy principal trong **service**; client không thể truyền username để tự nhận quyền. Phép kiểm owner tại repository nằm trong cùng thao tác cập nhật, giữ được khi có hai request đồng thời tranh sửa cùng một ID.

### File 5 — `src/main/java/demo/ownership/DocumentController.java`

~~~java
package demo.ownership;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/documents")
public final class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<Document> get(@PathVariable String id) {
        return service.readById(id);
    }

    @GetMapping
    public Flux<Document> mine() {
        return service.listMine();
    }

    @PutMapping("/{id}")
    public Mono<Document> update(
            @PathVariable String id,
            @RequestBody Mono<ReplaceText> body) {
        return body.flatMap(request ->
            service.replaceText(id, request.text()));
    }

    public record ReplaceText(String text) {}
}
~~~

Controller **không nhận ownerId từ request** và không tự sao chép logic so sánh quyền. Dữ liệu nhận từ `PUT` chỉ có `text`; service xác định caller bằng context và repository bảo vệ quyền thay đổi bản ghi. Mỗi method trả một publisher; không gọi `subscribe()` hoặc `block()` trong controller. WebFlux tự subscribe vào publisher trong vòng đời request.

## 4. Kiểm tra HTTP thủ công

Chạy ứng dụng từ project đã cấu hình và có các file trên:

~~~bash
./gradlew bootRun
~~~

Trên Windows có thể dùng `gradlew.bat bootRun`. Với cổng mặc định 8080:

~~~bash
# Alice xem tài liệu của mình: 200.
curl -i -u alice:alice-pass http://localhost:8080/documents/doc-a

# Alice thử xem tài liệu của Bob: 403.
curl -i -u alice:alice-pass http://localhost:8080/documents/doc-b

# Bob xem tài liệu của Bob: 200.
curl -i -u bob:bob-pass http://localhost:8080/documents/doc-b

# Thiếu credentials trên endpoint bảo vệ: 401.
curl -i http://localhost:8080/documents/doc-a

# ID không tồn tại: 404 đối với người đã đăng nhập.
curl -i -u alice:alice-pass http://localhost:8080/documents/no-such-id

# Alice chỉ được liệt kê tài liệu của Alice: 200, một phần tử.
curl -i -u alice:alice-pass http://localhost:8080/documents
~~~

Mã HTTP kỳ vọng tương ứng với **cấu hình demo**. Response JSON cho lời gọi hợp lệ đầu tiên có hình thức:

~~~json
{"id":"doc-a","ownerId":"alice","text":"Nội dung của Alice"}
~~~

Khi bị từ chối, body lỗi thực tế có thể khác tùy Spring Boot/error handlers; không nên dựa vào một chuỗi stack trace hoặc thông điệp English cụ thể. Kỳ vọng quan trọng là trạng thái và việc **không rò rỉ body tài liệu của Bob**.

Với `PUT`, Basic authentication **không thay cho CSRF token**. Các lệnh curl không có CSRF token có thể trả `403` từ lớp CSRF, dù request chưa đến service. Để chứng minh việc cập nhật của đúng/sai chủ sở hữu, dùng test `WebTestClient` với `csrf()` bên dưới hoặc xây dựng flow lấy/gửi token phù hợp ứng dụng. Không kết luận “ownership guard chạy đúng” chỉ vì một `PUT` thiếu CSRF bị từ chối.

## 5. Kiểm thử service bằng StepVerifier

File **`src/test/java/demo/ownership/DocumentServiceTest.java`** là một test class độc lập, chạy không cần HTTP server và không cần Spring context vì logic bảo vệ owner được viết **tường minh trong service**, không dựa vào Spring proxy. Test tự cấp authentication vào Reactor Context bằng `ReactiveSecurityContextHolder.withAuthentication(...)`.

~~~java
package demo.ownership;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DocumentServiceTest {

    private final InMemoryDocuments repository =
        new InMemoryDocuments();
    private final DocumentService service =
        new DocumentService(repository);

    private Authentication user(String username) {
        return UsernamePasswordAuthenticationToken.authenticated(
            username,
            "ignored-test-credential",
            List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    @Test
    void aliceCanReadHerOwnDocument() {
        StepVerifier.create(
            service.readById("doc-a")
                .contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(user("alice"))))
            .assertNext(doc -> {
                assertEquals("doc-a", doc.id());
                assertEquals("alice", doc.ownerId());
                assertEquals("Nội dung của Alice", doc.text());
            })
            .verifyComplete();
    }

    @Test
    void aliceCannotReadBobsDocumentEvenWithSameRole() {
        StepVerifier.create(
            service.readById("doc-b")
                .contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(user("alice"))))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void missingAuthenticationIsDenied() {
        StepVerifier.create(service.readById("doc-a"))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void aliceCanEditOnlyHerText() {
        StepVerifier.create(
            service.replaceText("doc-a", "Alice updated")
                .contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(user("alice"))))
            .assertNext(doc -> {
                assertEquals("Alice updated", doc.text());
                assertEquals("alice", doc.ownerId());
            })
            .verifyComplete();

        StepVerifier.create(repository.findById("doc-a"))
            .assertNext(doc -> {
                assertEquals("Alice updated", doc.text());
                assertEquals("alice", doc.ownerId());
            })
            .verifyComplete();
    }

    @Test
    void aliceCannotEditBobsDocumentAndNothingChanges() {
        StepVerifier.create(
            service.replaceText("doc-b", "stolen")
                .contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(user("alice"))))
            .expectError(AccessDeniedException.class)
            .verify();

        // Kiểm hậu điều kiện: từ chối thật, không ghi dữ liệu.
        StepVerifier.create(repository.findById("doc-b"))
            .assertNext(doc -> {
                assertEquals("bob", doc.ownerId());
                assertEquals("Nội dung của Bob", doc.text());
            })
            .verifyComplete();
    }

    @Test
    void listReturnsOnlyAlicesDocuments() {
        StepVerifier.create(
            service.listMine()
                .contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(user("alice"))))
            .assertNext(doc -> {
                assertEquals("alice", doc.ownerId());
                assertEquals("doc-a", doc.id());
            })
            .verifyComplete();
    }

    @Test
    void missingDocumentReturnsNotFound() {
        StepVerifier.create(
            service.readById("not-present")
                .contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(user("alice"))))
            .expectErrorSatisfies(error -> {
                ResponseStatusException exception =
                    (ResponseStatusException) error;
                assertEquals(HttpStatus.NOT_FOUND,
                    exception.getStatusCode());
            })
            .verify();
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests demo.ownership.DocumentServiceTest
~~~

Test có bảy trường hợp. Với dependencies tương thích và source như phần 3, kỳ vọng **bảy test PASS**; stdout cụ thể của Gradle phụ thuộc phiên bản/build. Các điểm đáng chú ý:

- `StepVerifier` mới thực sự subscribe vào `Mono`/`Flux`; chỉ khẳng định publisher khác null sẽ không chạy phân quyền.
- `contextWrite(withAuthentication(...))` đặt authentication vào **Reactor Context**, nơi `ReactiveSecurityContextHolder` đọc được. Test không dựa vào `SecurityContextHolder` ThreadLocal.
- Vì Alice và Bob cùng `ROLE_USER`, test `aliceCannotReadBobsDocumentEvenWithSameRole` phát hiện bug **role-only authorization**.
- Test UPDATE không dừng ở `expectError`; nó đọc lại kho dữ liệu và xác minh **text của Bob không thay đổi**.
- Test LIST xác nhận dữ liệu người khác không có trong publisher trả về. Nếu tăng fixture, dùng `recordWith`/`collectList` hoặc assertion trên từng phần tử và đếm số lượng.
- Test not-found minh họa chính sách 404; nếu chọn “che ID” bằng 404 cho cả non-owner thì phải chỉnh cả test/HTTP expectations đồng bộ.

`@PreAuthorize`/`@PostAuthorize` (nếu được thêm sau) yêu cầu method được gọi qua **Spring-managed proxy** để interceptor hoạt động. Test `new DocumentService(...)` ở trên chỉ chứng minh **logic phân quyền tường minh**, không chứng minh annotation method security được kích hoạt. Muốn test annotation, phải bật `@EnableReactiveMethodSecurity` và lấy service bean từ Spring context.

## 6. Kiểm thử WebFlux security chain với WebTestClient

Để bảo đảm HTTP controller, filter chain, CSRF và service thực sự nối đúng, thêm test tích hợp **`src/test/java/demo/ownership/DocumentHttpTest.java`**:

~~~java
package demo.ownership;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;

@SpringBootTest
class DocumentHttpTest {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(
                applicationContext)
            .apply(SecurityMockServerConfigurers.springSecurity())
            .build();
    }

    @Test
    void httpReadDeniesNonOwner() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .get().uri("/documents/doc-b")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void httpReadAllowsOwner() {
        client.mutateWith(mockUser("bob").roles("USER"))
            .get().uri("/documents/doc-b")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.ownerId").isEqualTo("bob");
    }

    @Test
    void httpPutWithValidCsrfStillDeniesNonOwner() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .mutateWith(csrf())
            .put().uri("/documents/doc-b")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"text\":\"stolen\"}")
            .exchange()
            .expectStatus().isForbidden();

        client.mutateWith(mockUser("bob").roles("USER"))
            .get().uri("/documents/doc-b")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.text").isEqualTo("Nội dung của Bob");
    }
}
~~~

**Lưu ý cú pháp import:** Java không cho phép xuống dòng giữa `import static` và tên package. Khi chép test, hai dòng import static hiển thị xuống dòng bên trên phải được viết **trên một dòng mỗi import**, như sau:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
~~~

Test `@SpringBootTest` mặc định ở mock-web environment với `WebTestClient.bindToApplicationContext(...).apply(springSecurity())`; nó không cần mở cổng Netty. `mockUser` gắn principal thử nghiệm vào request; `csrf()` vượt qua rào CSRF một cách hợp lệ **cho mục đích kiểm riêng ownership**. Vì không có CSRF token giả lập, một test PUT thất bại `403` có thể là lỗi CSRF và che giấu bug phân quyền owner.

Điểm cần kiểm tra thêm trong dự án thực tế: controller ngoài HTTP (scheduler/message handler) có thể gọi service; WebTestClient không thay thế StepVerifier kiểm logic service. Các test mutable in-memory nên cô lập fixture/tạo context riêng khi test có cập nhật thành công để tránh phụ thuộc thứ tự chạy. Trong file trên, test PUT chỉ thực hiện cập nhật bị từ chối và assert dữ liệu giữ nguyên.

## 7. Nâng cấp sang R2DBC: đưa owner vào câu truy vấn

Repository in-memory ở phần 3 minh họa quy tắc nguyên tử bằng `computeIfPresent`. Khi dùng database, tốt hơn là **lọc theo authenticated user ngay trong truy vấn**.

Đọc một tài liệu:

~~~sql
SELECT id, owner_id, text
FROM documents
WHERE id = :document_id
  AND owner_id = :trusted_user_id;
~~~

Liệt kê tài liệu kèm phân trang:

~~~sql
SELECT id, owner_id, text
FROM documents
WHERE owner_id = :trusted_user_id
ORDER BY id
LIMIT :limit OFFSET :offset;
~~~

Cập nhật nguyên tử:

~~~sql
UPDATE documents
SET text = :new_text,
    version = version + 1
WHERE id = :document_id
  AND owner_id = :trusted_user_id;
~~~

Giá trị `trusted_user_id` phải lấy từ `Authentication` ở service rồi truyền vào repository như tham số server-side. Không truyền giá trị owner do client tự khai báo. Nếu UPDATE ảnh hưởng **0 rows**, đó có thể là không tồn tại **hoặc** caller không có quyền. Chọn chính sách hiển thị 404 chung để tránh lộ sự tồn tại, hoặc dùng truy vấn bổ sung có kiểm soát khi thật sự cần phân biệt 403/404; không vô tình trả 200 khi không hàng nào được sửa.

**Vì sao cần WHERE owner ngay tại UPDATE?** Đoạn sau có cửa sổ rủi ro:

~~~java
// Mẫu dễ tạo TOCTOU: không dùng như kiểm quyền cuối cùng.
return repository.findById(id)
    .flatMap(doc -> {
        if (!doc.ownerId().equals(trustedUser)) {
            return Mono.error(new AccessDeniedException("Not owner"));
        }
        return repository.save(doc.withText(newText));
    });
~~~

Giữa bước đọc/kiểm và bước ghi, bản ghi có thể đã đổi owner, đổi version hoặc bị sửa bởi request khác. Thêm transaction có thể giúp quản lý nhất quán, nhưng **không tự động đảm bảo** quyền sở hữu vẫn đúng với kiểu isolation mặc định. Truy vấn UPDATE có `WHERE owner_id = ...` và kiểm rows affected là rào cuối cùng; thêm `AND version = :expected_version` khi cần optimistic locking.

Nếu ứng dụng đa tenant, predicate cần thêm `AND tenant_id = :trusted_tenant_id`. Bảo vệ quan hệ con (attachment/comment) cũng phải kiểm nó thuộc document và document thuộc user/tenant, không dựa duy nhất vào ID attachment. Mọi API copy/export/delete/archive đều phải thực thi chính sách tương ứng; bảo vệ GET mà bỏ qua download/export vẫn là lỗ hổng.

## 8. Phân biệt ba cách cấp quyền và rủi ro của mỗi cách

| Vị trí kiểm quyền | Phù hợp cho | Giới hạn cần xử lý |
| --- | --- | --- |
| `SecurityWebFilterChain` / `authorizeExchange` | Login, role/scope chung, nhóm URL | Không biết owner của từng hàng dữ liệu trừ khi custom rule truy vấn backend |
| `@PreAuthorize` trên service | Role/authority, một số biểu thức đơn giản trước khi gọi target | Proxy phải hoạt động; nếu owner nằm trong DB, cần kiểm với dữ liệu thật và chú ý async/reactive semantics |
| `@PostAuthorize` trên kết quả | Một số chính sách đọc theo object trả về | Kiểm sau khi business logic tạo kết quả; không bảo đảm ngăn tác dụng phụ ghi/xóa |
| Authorization tường minh trong service + repository predicate | Quyền phụ thuộc owner/tenant và điều kiện dữ liệu sống | Phải kiểm nhất quán ở mọi entrypoint, không gọi repository không bảo vệ từ đường khác |

Có thể kết hợp bảo vệ theo nhiều lớp. Ví dụ service có `@PreAuthorize("hasAuthority('document:write')")` để kiểm quyền chức năng, **vẫn phải** thực thi điều kiện owner trước/đồng thời với UPDATE. Nếu bật annotation cần cấu hình `@EnableReactiveMethodSecurity`, method trả `Mono`/`Flux` và được gọi qua Spring bean proxy; gọi `this.securedMethod()` trong cùng instance có thể bỏ qua AOP advice.

**Cẩn trọng với `@PostAuthorize("returnObject.ownerId == authentication.name")`:** sau khi một method đọc object, rule có thể chặn dữ liệu gửi tới subscriber, nhưng không thay thế điều kiện query để giảm tải dữ liệu nhạy cảm, càng không thay thế permission check trước UPDATE. Trong bài thực hành này, kiểm owner tường minh trong service giúp dễ đọc, dễ test bằng `StepVerifier` và kết hợp được truy vấn UPDATE nguyên tử.

Một lựa chọn khác là tạo bean policy chuyên biệt:

~~~java
public boolean isOwner(String trustedUserId, Document doc) {
    return doc != null && trustedUserId.equals(doc.ownerId());
}
~~~

Đây là method minh họa (không phải file đầy đủ). Với kiểm quyền cần I/O, tránh gọi repository blocking trong phương thức boolean; policy nên compose publisher ở service hoặc dùng authorization API reactive được Spring Security hỗ trợ. Policy bean cho phép tái sử dụng cùng quy tắc ở nhiều dịch vụ, nhưng phải nhất quán với predicate ở kho dữ liệu.

## 9. 403 hay 404? Không có một câu trả lời cho mọi sản phẩm

Với người dùng đã xác thực cố truy cập tài liệu của người khác:

- **403 Forbidden:** rõ nghĩa “đã xác thực nhưng không được phép”; thuận tiện kiểm thử và vận hành. Nhưng caller biết ID đó có thể tồn tại.
- **404 Not Found:** có thể giảm tín hiệu giúp dò ID nếu dùng cùng một response cho “không tồn tại” và “không có quyền”. Khi chọn chính sách này, cần thống nhất GET/PUT/DELETE/LIST và tránh leak qua timing, error body, size hay count.
- **401 Unauthorized:** theo HTTP authentication semantics, thường dùng khi request **chưa được xác thực** hoặc credentials không hợp lệ; không dùng 401 tùy tiện cho mọi lỗi owner khi caller đã đăng nhập.

Trong demo, service dùng 403 cho owner mismatch và 404 cho ID thiếu. Đây là quyết định **minh họa**, không phải chuẩn bắt buộc của Spring Security. Ở tầng test trực tiếp service, 403/404 chưa phải là status HTTP: `AccessDeniedException` hoặc `ResponseStatusException` được phát qua Reactor; WebFlux filters/exception handlers mới dịch sang response cụ thể. Kiểm HTTP bằng WebTestClient hoặc request tích hợp để xác nhận.

## 10. Lỗi phổ biến và cách sửa

1. **Chỉ kiểm role USER.** Hai người có cùng role sẽ đọc chéo dữ liệu. Thêm kiểm đối tượng cụ thể: owner ID hoặc policy theo tenant/quan hệ.
2. **Lấy owner từ body/query.** Client có thể gửi `ownerId=bob` để giả mạo. Lấy principal đã xác thực từ Reactor Context, chỉ dùng owner trong database để so sánh.
3. **Quên subscribe vào Mono.** Gọi `service.readById(id)` rồi so `assertNotNull` không chạy logic. Dùng StepVerifier hoặc WebTestClient để kích hoạt pipeline.
4. **Dùng `filter(doc -> isOwner(doc))` mà không xử lý empty.** Có thể vô tình đổi 403 thành 404/200 empty tùy controller. Chọn rõ `switchIfEmpty`/`Mono.error` theo chính sách.
5. **Dựa vào `ThreadLocal SecurityContextHolder` trong WebFlux.** Reactor chuyển luồng; user có thể biến mất hoặc bị đọc sai. Dùng `ReactiveSecurityContextHolder`, không tự tách chuỗi bằng `subscribe()`.
6. **Kiểm owner sau khi save/delete.** Dù response bị chặn, dữ liệu đã thay đổi. Thực thi owner predicate trong UPDATE/DELETE atomically.
7. **Đọc rồi kiểm rồi save bằng thao tác rời.** Nếu quyền/chủ sở hữu thay đổi đồng thời, gặp TOCTOU. Dùng điều kiện WHERE owner_id và kiểm số hàng bị ảnh hưởng.
8. **List lọc sau phân trang.** Lấy 100 bản ghi toàn hệ thống rồi lọc ra tài liệu của user tạo trang rỗng/số lượng sai và tải dữ liệu ngoài phạm vi. Filter tại query trước LIMIT/OFFSET.
9. **Nhầm CSRF 403 với ownership 403.** Test PUT thiếu CSRF sẽ fail sớm. Dùng `csrf()` trong WebTestClient và xác minh dữ liệu sau nhánh denied.
10. **Chỉ kiểm 403 mà không kiểm side effect.** Một endpoint có thể lỡ sửa dữ liệu rồi ném exception. Assert lại trạng thái repository/database sau request.
11. **Chỉ dùng `@PostAuthorize` cho thao tác ghi.** Rule chạy muộn đối với side effect. Chuyển quyền ghi sang precondition/predicate trong persistence.
12. **Test qua `new Service()` nhưng mong annotation AOP chạy.** Logic tường minh thì test được; nhưng @PreAuthorize yêu cầu Spring proxy. Dùng context-managed bean khi test method security.
13. **Tenant mismatch.** Owner ID trùng giữa hai tenant có thể gây truy cập chéo nếu query thiếu tenant. So sánh cả tenant + subject ổn định theo mô hình dữ liệu.
14. **Cache hoặc search index bỏ quên owner.** Redis/search/cache key chỉ có `documentId` và tái sử dụng response đã cấp cho Bob có thể lộ sang Alice. Cache key và query phải chứa scope quyền hoặc áp lại policy trước khi trả dữ liệu.
15. **WebSocket/event/message handler gọi repository trực tiếp.** HTTP filter không bảo vệ đường không-HTTP. Đặt chính sách trong service hoặc use-case boundary mà mọi caller phải đi qua.
16. **Phân quyền chỉ theo quyền đọc.** Endpoint update/delete/upload/export hoặc thay owner phải có chính sách phù hợp riêng; không suy ra từ GET đã được bảo vệ.

Khi có lỗi “user đăng nhập đúng nhưng bị từ chối”, lần lượt kiểm: (a) authentication và authorities từ context, (b) mapping ID subject/username/tenant, (c) owner trong nguồn dữ liệu thật, (d) branch `switchIfEmpty`/`onError`, (e) proxy nếu có method security, (f) web filter/CSRF nếu lỗi chỉ xuất hiện khi gọi HTTP. Không in toàn bộ JWT, password hoặc nội dung tài liệu nhạy cảm vào log để gỡ lỗi.

## 11. Tiêu chí hoàn thành bài thực hành

Hệ thống chỉ đạt yêu cầu khi có bằng chứng cho tất cả các điều sau:

- Alice/Bob có cùng role USER nhưng **không thể** truy cập chéo tài liệu; người đúng owner vẫn thao tác được.
- Thiếu principal/reactive security context không làm service tự cấp quyền.
- READ bị từ chối không phát `onNext(Document)`; LIST chỉ phát tài liệu thuộc owner đã xác thực.
- UPDATE trái phép không làm thay đổi text, owner hay version; có assertion đọc lại dữ liệu sau khi denied.
- Client không kiểm soát `trustedUserId`; service lấy từ authentication và repository kiểm owner trên dữ liệu hiện tại.
- Khi dùng database, UPDATE/DELETE có `WHERE owner_id = :trustedUserId` và xử lý `rowsUpdated=0` theo policy; khi đa tenant có thêm tenant condition.
- WebFlux HTTP test đi qua security filter thực, phân biệt 401 authentication, 403 ownership, 404 missing và 403 CSRF.
- Các permission checks không gọi API blocking trên event loop; dùng reactive repository hoặc adapter có scheduler phù hợp khi cần.
- Có test cho các đường gọi service ngoài controller, các thao tác theo object con và policy cache/search nếu tính năng thực tế sử dụng chúng.

## Tài liệu tham khảo

- Spring Security – WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security – Authorize ServerHttpRequest: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security – Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security – Testing WebFlux: https://docs.spring.io/spring-security/reference/reactive/test/index.html
- Spring Security – Reactive SecurityContextHolder API: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- OWASP – Broken Object Level Authorization (BOLA) in API Security: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- Project Reactor – Reactor Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
