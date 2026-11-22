# Test slice: Không chồng nhiều slice để tạo một context không rõ phạm vi

## 1. Vấn đề: test cần MVC và JPA thì có nên ghép hai annotation?

Spring Boot hỗ trợ các **test slice** để tải một phần ứng dụng, ví dụ `@WebMvcTest` cho Spring MVC và `@DataJpaTest` cho repository JPA. Mỗi slice có một **ý đồ về ranh giới kiểm thử**: chỉ kích hoạt những bean, cơ chế quét thành phần và auto-configuration đủ cho mục tiêu đó.

Một đoạn code thường xuất hiện khi người học muốn “có cả controller lẫn database”:

```java
// SAI: đây là phản ví dụ, không phải một test hợp lệ.
@WebMvcTest(AccountController.class)
@DataJpaTest
class AccountControllerAndJpaTest {
    // ...
}
```

Trông có vẻ như “cộng MVC slice và JPA slice”, nhưng theo tài liệu **Spring Boot 3.3**, việc đặt **nhiều `@…Test` slice trên cùng một test là không được hỗ trợ**. Các annotation này không phải các công tắc độc lập có thể cộng lại một cách tùy ý. Mỗi annotation định nghĩa một cơ chế bootstrap, bộ filter và nhóm auto-configuration của riêng nó; trộn chúng làm **phạm vi test không rõ** và thường dẫn tới lỗi từ giai đoạn xây dựng Spring test context.

Nguyên tắc thực dụng:

> **Một test class nên có một quyết định rõ ràng về context.** Nếu chỉ cần kiểm tra web, dùng một MVC slice và cung cấp collaborator giả. Nếu chỉ cần persistence, dùng JPA slice. Nếu cần xác nhận nhiều tầng hoạt động cùng nhau, dùng `@SpringBootTest` với các công cụ test phù hợp — không xếp chồng các slice.

Một lựa chọn nâng cao được Spring Boot cho phép là **chọn đúng một slice rồi thêm các `@AutoConfigure…` cần thiết của slice khác** bằng cấu hình tường minh. Tuy nhiên, điều đó không biến việc nạp nhiều slice annotation thành hợp lệ, cũng không mặc nhiên làm các bean thiếu xuất hiện. Cần hiểu bootstrap, loại context và hạ tầng được kích hoạt, và thường **full integration test đơn giản hơn** nếu thật sự muốn test nhiều tầng.

## 2. Mục tiêu bài học

Sau khi học xong, bạn có thể:

1. Diễn giải “slice test” bằng ba yếu tố: **component scan bị giới hạn**, **auto-configuration được chọn** và **test infrastructure được cấu hình**.
2. Giải thích vì sao `@WebMvcTest` + `@DataJpaTest`, `@SpringBootTest` + `@WebMvcTest` không phải phương pháp ghép tùy ý.
3. Nhận diện các tình huống cần MVC slice, JPA slice, JSON test, client test hoặc full Spring Boot context.
4. Dùng `@MockBean` của Spring Boot 3.3 (hoặc `@MockitoBean` ở các dòng Framework mới) cho collaborator ngoài phạm vi slice.
5. Dùng `@Import`/`@TestConfiguration` để thêm **một số bean cụ thể** mà vẫn giữ ranh giới test hiểu được.
6. Dùng `@SpringBootTest` + `@AutoConfigureMockMvc` để kiểm tra controller → service → repository mà không mở HTTP server thật.
7. Viết các test Java 17/JUnit Jupiter với kết quả có thể kiểm chứng, giải thích **test chứng minh điều gì** và **không chứng minh điều gì**.
8. Chẩn đoán lỗi multiple bootstrappers, missing beans, sai auto-configuration, datasource và context cache.
9. Bảo vệ ranh giới kiểm thử khi refactor, nâng Spring Boot hoặc tăng phạm vi tích hợp.

## 3. Test slice là gì?

Spring Boot là một IoC container có nhiều thành phần: controllers, services, repositories, databases, HTTP clients, security filters, schedulers, metrics và các auto-configurations. Để kiểm thử chỉ một phần, Spring Boot có những annotation **`@…Test`** hướng tới từng công nghệ.

```text
Full Spring Boot application
+--------------------------------------------------+
| MVC controllers / filters / JSON                  |
| Services / domain use cases                      |
| JPA repositories / entities / SQL                |
| HTTP clients / event publishers / security       |
| Configurations / infrastructure / startup jobs   |
+--------------------------------------------------+

@WebMvcTest
+-----------------------------+
| MVC controller              |
| MVC infrastructure / JSON   |
| Selected filters/advice     |
| Mock collaborators          |
+-----------------------------+

@DataJpaTest
+-----------------------------+
| JPA entities                |
| Repositories                |
| EntityManager / datasource  |
| Test transactions           |
+-----------------------------+
```

Đây là **sơ đồ khái niệm**, không phải danh sách tuyệt đối mọi bean. Ví dụ `@WebMvcTest` vẫn có thể đưa vào security filter, controller advice hoặc các web component tùy classpath/configuration. `@DataJpaTest` có thể có migration/datasource test setup. Tập auto-configuration chính xác phải tra theo **phiên bản Spring Boot**, không đoán từ tên annotation.

Mỗi slice thường làm ba việc:

1. **Giới hạn component scan:** chỉ các kiểu bean liên quan tới vùng công nghệ đang test được chọn. `@WebMvcTest` không tự quét service thường, còn `@DataJpaTest` không tự nạp mọi controller/service.
2. **Chọn auto-configuration:** chỉ một tập cấu hình framework phù hợp (MVC dispatcher/JSON, hoặc JPA/transaction/datasource...).
3. **Chuẩn bị test infrastructure:** ví dụ `MockMvc` cho web slice, `TestEntityManager` và transaction rollback cho JPA slice.

Lợi ích: boot nhanh hơn, ít dependency ngoài, lỗi dễ khoanh vùng, yêu cầu nghiệp vụ của test rõ hơn.

**Hạn chế có chủ ý:** test slice không phải một mô hình đầy đủ của toàn ứng dụng. Khi MVC test mock service, bạn không thể kết luận SQL/repository hoạt động đúng. Khi JPA test query repository, bạn không thể kết luận HTTP status/JSON contract đúng.

## 4. Những annotation slice thường gặp

| Slice | Ranh giới nổi bật | Kết quả nên assert | Thành phần thường không được tự nạp |
| --- | --- | --- | --- |
| `@WebMvcTest` | Spring MVC controllers, mapping, JSON, validation, MVC filters | HTTP status, header, response JSON, exception mapping | Service/repository thông thường |
| `@WebFluxTest` | Reactive web controllers, WebFlux infrastructure | Web response, reactive contract | Repository/service toàn ứng dụng |
| `@DataJpaTest` | Entity mapping, repository, JPA queries, database test | Persist/reload/query, constraints, transaction behavior | MVC controller và service thường |
| `@JdbcTest` | JDBC, DataSource, JdbcTemplate | SQL/JDBC interactions | MVC controller và phần lớn ứng dụng |
| `@DataJdbcTest` | Spring Data JDBC repositories | Mapping/query/data behavior | MVC và service thường |
| `@JsonTest` | JSON mapper, modules, JSON components | Serialize/deserialize, field types | HTTP server/controller, database |
| `@RestClientTest` | REST client dưới kiểm thử và HTTP mock infrastructure | Outbound method/path/headers/body | Full web server, DB |
| `@WebClientTest` | WebClient-related client slice | Reactive client requests/responses | Full application flow |
| `@GraphQlTest` | GraphQL schema/controller related infrastructure | GraphQL query/response | Full DB/service mặc định |

Các annotation theo cơ chế và artifact thực tế có thể khác ở Spring Boot 3.x và 4.x. Trong **Spring Boot 4**, test module/starter theo chức năng được tách nhỏ hơn, ví dụ `spring-boot-starter-webmvc-test` và `spring-boot-starter-data-jpa-test`. Tránh sao chép package/import của 3.3 vào 4.x mà không xem migration guide.

### 4.1. `@SpringBootTest` có phải một slice không?

**Không.** `@SpringBootTest` nạp Spring Boot application context theo cấu hình của ứng dụng, thường có phạm vi rộng hơn slice. Nó cho phép dùng các annotation **`@AutoConfigure…`** như `@AutoConfigureMockMvc`, nhưng không nên được ghép cùng một annotation `@WebMvcTest` hay `@DataJpaTest` như cách cộng hai slice.

So sánh:

```java
// ĐÚNG: chọn một MVC slice để kiểm tra controller.
@WebMvcTest(AccountController.class)
class AccountWebTest { }

// ĐÚNG: chọn một JPA slice để kiểm tra repository.
@DataJpaTest
class AccountJpaTest { }

// ĐÚNG: chọn full Boot context, thêm MockMvc infrastructure.
@SpringBootTest
@AutoConfigureMockMvc
class AccountFlowTest { }

// KHÔNG ĐƯỢC HỖ TRỢ: hai test slices trên cùng class.
@WebMvcTest(AccountController.class)
@DataJpaTest
class WrongMixedSlicesTest { }

// KHÔNG NÊN: ghép full Boot bootstrap với slice bootstrap.
@SpringBootTest
@WebMvcTest(AccountController.class)
class WrongFullPlusSliceTest { }
```

Tất cả các class ở đoạn trên chỉ là **mẫu so sánh annotation**, không đủ imports/bean để chạy độc lập. Hai class cuối là phản ví dụ có chủ đích. Đừng để chúng trong source test của build thật.

## 5. Vì sao không thể “cộng” các slice bằng cách xếp annotation?

### 5.1. Xung đột cơ chế bootstrap

Một annotation slice của Spring Boot có thể được meta-annotate bằng `@BootstrapWith` để chọn một `TestContextBootstrapper` chuyên biệt. Ví dụ ở Boot 3.3, MVC và JPA slices dùng các bootstrapper test đặc thù; mỗi bootstrapper quyết định cách áp dụng context customizers, auto-configuration và exclusions.

Hai annotation slice trên cùng class có thể khiến Spring TestContext nhìn thấy **hơn một khai báo `@BootstrapWith` không tương thích**, dẫn đến lỗi ở giai đoạn bootstrap. Thông báo cụ thể phụ thuộc bản Boot/Framework, nhưng lớp vấn đề giống nhau: framework không được thiết kế để tự suy diễn “bootstrapper hợp nhất” từ hai loại slice độc lập.

Mẫu log thường gặp (minh họa, không cam kết từng ký tự):

```text
IllegalStateException:
Configuration error: found multiple declarations of @BootstrapWith
...
@WebMvcTest ...
@DataJpaTest ...
```

Không phải cứ thấy lỗi này là thiếu dependency Maven/Gradle. Cần đọc **annotations trên test class và meta-annotations** trước khi thử thêm starter.

### 5.2. Quy tắc component scan khác nhau

`@WebMvcTest` ưu tiên controllers và thành phần web; `@DataJpaTest` ưu tiên entities/repositories và persistence. Nếu cố đưa cả hai, không có câu trả lời rõ:

- Service `@Service` có được quét không?
- ControllerAdvice/security có được nạp không?
- Repositories có bị filter ra không?
- EntityManager/DataSource nằm ở phạm vi nào?
- Người đọc có nên coi test là web-only, DB-only hay toàn luồng?

Thứ người viết test muốn thực sự có thể là **integration test**, nhưng test annotation lại tuyên bố hai ranh giới thu hẹp khác nhau.

### 5.3. Auto-configuration không phải phép cộng không điều kiện

Mỗi slice import một danh sách auto-configurations và áp dụng `@OverrideAutoConfiguration`/type exclude filters/test customizers theo cơ chế tương ứng. Việc thêm nhóm cấu hình của tầng khác mà không biết prerequisites có thể khiến một số bean:

- không được tạo do condition không thỏa;
- được tạo trùng với bean đã có;
- yêu cầu datasource/web environment chưa sẵn;
- bị exclude bởi filter của slice gốc;
- gây xung đột bean name hoặc conditional configurations;
- xuất hiện nhưng không có cộng tác viên cần thiết để chạy thật.

**Thêm một `@AutoConfigure…` không tự biến một MVC slice thành full integration context.** Một số nhóm cấu hình có thể nhập được có chủ đích nhưng phải xác minh đầy đủ prerequisites và bằng chứng; đừng hiểu đó là “chồng hai slice thành công”.

## 6. Nguyên tắc thiết kế: chọn một hợp đồng quan sát được

Trước khi chọn annotation, hãy mô tả **hành vi muốn chứng minh**:

| Câu hỏi | Ranh giới nhỏ nhất hợp lý | Thành phần chạy thật |
| --- | --- | --- |
| GET /accounts/41 trả JSON đúng? | `@WebMvcTest(AccountController.class)` | Controller/MVC/JSON |
| JPA lưu account với code unique và query lại đúng? | `@DataJpaTest` | Entity, repository, datasource |
| Service có tính opening balance đúng? | JUnit unit test | Service/domain |
| Service phối hợp repository thật nhưng không cần HTTP? | `@DataJpaTest` + `@Import` một service cụ thể, hoặc integration service test | Service + JPA |
| POST /accounts trả 201 và DB có account? | `@SpringBootTest` + `@AutoConfigureMockMvc` | Controller, service, repository |
| HTTP thật qua socket và DB được ghi? | `@SpringBootTest(webEnvironment=RANDOM_PORT)` | Server thật + app + DB |
| JSON record serialize theo contract? | `@JsonTest` | JSON mapper/modules |
| REST client gọi đúng URL/header/body? | `@RestClientTest` | Client + mock server |

**Không chọn annotation vì thấy test cần “nhiều bean”.** Đầu tiên hãy xác định bên ngoài test cần quan sát **HTTP boundary, persistence boundary hay integration flow**. Annotation chỉ là công cụ dựng môi trường đúng với mục tiêu.

## 7. Ví dụ runnable: Java 17, Spring Boot 3.3.0, JUnit Jupiter

Bộ ví dụ sẽ so sánh **bốn test hợp lệ** trên cùng một ứng dụng Account đơn giản:

1. **MVC slice:** Controller thật, service mock, không có database.
2. **JPA slice:** Repository thật và H2 test database, không có controller.
3. **JPA slice có service import:** Service thật + repository thật, không có MVC.
4. **Full integration:** Controller → service → repository thật, MockMvc, H2.

Chọn **Spring Boot 3.3.0** và Java 17 để imports nhất quán. Đây là mốc minh họa cho API 3.x; production nên dùng bản vá được duyệt và kiểm tra security/support. H2 dùng cho mục tiêu test demo, không tự chứng minh mọi semantics của PostgreSQL/MySQL production.

### 7.1. Cấu trúc dự án

```text
slice-boundaries-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/
    │   ├── SliceDemoApplication.java
    │   ├── Account.java
    │   ├── AccountRepository.java
    │   ├── AccountView.java
    │   ├── AccountService.java
    │   └── AccountController.java
    └── test/java/example/
        ├── AccountControllerSliceTest.java
        ├── AccountRepositorySliceTest.java
        ├── AccountServiceJpaSliceTest.java
        └── AccountFlowIntegrationTest.java
```

### 7.2. Gradle

**`settings.gradle`:**

```groovy
rootProject.name = 'slice-boundaries-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Có `spring-boot-starter-web` và `spring-boot-starter-data-jpa` trên main classpath, nhưng **điều đó không làm mọi slice tải toàn bộ bean**. Slice boundary được quyết định bởi test annotations/configuration, không phải chỉ từ dependencies hiện diện.

Ở đây H2 chỉ nằm trên **test runtime classpath**; chạy ứng dụng bằng `bootRun` ngoài môi trường test sẽ cần cấu hình database/driver riêng. Các lệnh kiểm chứng chính của ví dụ là `./gradlew test` và chạy từng test class.

### 7.3. Main application

**`src/main/java/example/SliceDemoApplication.java`:**

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SliceDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SliceDemoApplication.class, args);
    }
}
```

Đặt class tại package `example` giúp các lớp khác trong package này được component scan trong full application context. Slice tests dùng primary configuration để tìm phạm vi ứng dụng, nhưng áp dụng bộ lọc slice riêng.

### 7.4. Entity JPA

**`src/main/java/example/Account.java`:**

```java
package example;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "accounts")
public class Account {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String code;

    @Column(nullable = false)
    private long balance;

    protected Account() {
        // JPA yêu cầu constructor không tham số.
    }

    public Account(String code, long balance) {
        this.code = code;
        this.balance = balance;
    }

    public Long getId() {
        return id;
    }

    public String getCode() {
        return code;
    }

    public long getBalance() {
        return balance;
    }
}
```

Tệp dùng `jakarta.persistence` theo Spring Boot 3.x, không phải `javax.persistence` của những project Spring Boot 2.x cũ. `IDENTITY` hoạt động với H2 trong demo; nếu dùng database production khác, cần xác minh generation strategy và schema thực tế.

### 7.5. Spring Data repository

**`src/main/java/example/AccountRepository.java`:**

```java
package example;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface AccountRepository
        extends JpaRepository<Account, Long> {
    Optional<Account> findByCode(String code);
}
```

Spring Data JPA tạo implementation của interface repository trong JPA context. `findByCode` dựa trên tên thuộc tính `code` của entity. Vì vậy JPA slice có thể kiểm tra query method mà không cần controller.

### 7.6. DTO và service

**`src/main/java/example/AccountView.java`:**

```java
package example;

public record AccountView(
        Long id,
        String code,
        long balance) {}
```

**`src/main/java/example/AccountService.java`:**

```java
package example;

import java.util.NoSuchElementException;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountService {
    private final AccountRepository repository;

    public AccountService(AccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public AccountView create(String code, long openingBalance) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException(
                    "account code is required");
        }
        if (openingBalance < 0L) {
            throw new IllegalArgumentException(
                    "negative opening balance");
        }

        Account saved =
                repository.save(new Account(code, openingBalance));

        return new AccountView(
                saved.getId(), saved.getCode(), saved.getBalance());
    }

    @Transactional(readOnly = true)
    public AccountView get(Long id) {
        Account found = repository.findById(id)
                .orElseThrow(() -> new NoSuchElementException(
                        "account " + id + " not found"));

        return new AccountView(
                found.getId(),
                found.getCode(),
                found.getBalance());
    }
}
```

Service thuộc lớp nghiệp vụ, không phải một phần được `@WebMvcTest` tự động scan. Nó cần repository thật khi kiểm tra persistence, hoặc được thay bằng mock khi chỉ kiểm tra controller mapping. `@Transactional` trên service chỉ hoạt động khi gọi qua Spring proxy phù hợp; unit test bằng `new` không tự kích hoạt transaction advice.

### 7.7. Controller

**`src/main/java/example/AccountController.java`:**

```java
package example;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/accounts")
public class AccountController {
    public record CreateAccountRequest(
            String code,
            long balance) {}

    private final AccountService service;

    public AccountController(AccountService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public AccountView get(@PathVariable Long id) {
        return service.get(id);
    }

    @PostMapping
    public ResponseEntity<AccountView> create(
            @RequestBody CreateAccountRequest request) {
        AccountView created =
                service.create(request.code(), request.balance());

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(created);
    }
}
```

Controller chỉ gọi service và biến dữ liệu thành HTTP response. Bài tập tập trung vào đường thành công; ví dụ chưa có validation annotation, exception handler hoặc security. Do đó **không suy luận** mọi input sai sẽ tự trả 400/404/409 nếu chưa triển khai mapping tương ứng.

## 8. Test 1 — Chỉ chọn `@WebMvcTest` để kiểm tra HTTP

**`src/test/java/example/AccountControllerSliceTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(AccountController.class)
class AccountControllerSliceTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    AccountService service;

    @Test
    void mapsGetAndSerializesAccountJson() throws Exception {
        when(service.get(41L))
                .thenReturn(new AccountView(41L, "AC-41", 5000L));

        mvc.perform(get("/api/accounts/{id}", 41L))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(41))
                .andExpect(jsonPath("$.code").value("AC-41"))
                .andExpect(jsonPath("$.balance").value(5000));

        verify(service).get(41L);
    }
}
```

### Điều được chứng minh

- `AccountController` được Spring MVC phát hiện với route `GET /api/accounts/{id}`.
- Path variable `41` được bind vào kiểu `Long`.
- Controller dùng `AccountService` bean trong MVC test context.
- HTTP status 200 và JSON fields `id`, `code`, `balance` đúng với kết quả service giả lập.
- Không có HTTP server TCP thật: `MockMvc` kiểm tra ở mock servlet environment.

### Điều **chưa** được chứng minh

- `AccountService.get` tra repository đúng hay không: service là mock.
- JPA mapping/query hoạt động hay không: JPA không thuộc mục tiêu slice.
- Database có account 41 thật hay không: JSON đến từ Mockito stub.
- Kết nối/hành vi mạng HTTP ở một server thật: không có `RANDOM_PORT`.

Trong **Spring Boot 3.3**, dùng `@MockBean` từ `org.springframework.boot.test.mock.mockito`. Với Spring Boot 3.4+/Framework 6.2+ và Boot 4, cần xem `@MockitoBean`/các test starter tương ứng — đừng tự ghép imports khác major.

**Nếu Spring Security có trên classpath:** `@WebMvcTest` có thể kích hoạt security filters. Test này không thêm starter security nên không cần thiết lập principal/CSRF. Trong dự án thật, HTTP 401/403 có thể là đúng security behavior chứ không phải thiếu bean controller; dùng Spring Security Test nếu cần.

## 9. Test 2 — Chỉ chọn `@DataJpaTest` để kiểm tra repository

**`src/test/java/example/AccountRepositorySliceTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

import static org.junit.jupiter.api.Assertions.assertEquals;

@DataJpaTest(properties =
        "spring.jpa.hibernate.ddl-auto=create-drop")
class AccountRepositorySliceTest {
    @Autowired
    TestEntityManager entityManager;

    @Autowired
    AccountRepository repository;

    @Test
    void persistsAndFindsAccountByCode() {
        entityManager.persistAndFlush(
                new Account("AC-77", 7000L));
        entityManager.clear();

        Account found = repository.findByCode("AC-77")
                .orElseThrow();

        assertEquals("AC-77", found.getCode());
        assertEquals(7000L, found.getBalance());
    }
}
```

### Điều được chứng minh

- Entity `Account` được JPA phát hiện.
- Schema trong H2 test database có thể được tạo theo mapping được cấu hình.
- `AccountRepository.findByCode` chạy được với SQL/JPA.
- Trạng thái có thể được lấy lại sau `flush` và `clear` persistence context.
- Test chạy trong transaction mặc định của `@DataJpaTest` và rollback sau test khi được framework quản lý.

### Điều **chưa** được chứng minh

- MVC controller trả HTTP đúng hay không.
- Service khác ngoài scope JPA có được Spring scan hay không.
- Tương thích tuyệt đối với dialect/constraint/locking của PostgreSQL/MySQL production.
- Dữ liệu đã được commit và nhìn thấy từ một transaction khác: test mặc định rollback.

`TestEntityManager` là tiện ích của JPA test trong Boot 3.3, giúp persist/flush/clear khi test entity/repository. Nó **không tự bổ sung Spring MVC beans**.

**Nếu cần database cùng loại production:** có thể dùng Testcontainers hoặc một database test riêng, cấu hình `@AutoConfigureTestDatabase(replace = NONE)` phù hợp và driver/JDBC URL đúng, thay vì trộn thêm `@WebMvcTest`. Cần cân nhắc transaction, cleanup và thời gian container.

## 10. Test 3 — Một JPA slice, thêm đúng service cần thiết bằng `@Import`

Đây là cách giải quyết nhu cầu thường gặp: “Tôi muốn test service với repository thật, nhưng không cần web”. Không chồng `@DataJpaTest` với `@WebMvcTest`, mà giữ JPA slice và **thêm một bean ứng dụng cụ thể**.

**`src/test/java/example/AccountServiceJpaSliceTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;

@DataJpaTest(properties =
        "spring.jpa.hibernate.ddl-auto=create-drop")
@Import(AccountService.class)
class AccountServiceJpaSliceTest {
    @Autowired
    AccountService service;

    @Autowired
    AccountRepository repository;

    @Test
    void usesRealServiceAndRealRepositoryWithoutWeb() {
        AccountView created =
                service.create("AC-88", 8800L);

        assertEquals("AC-88", created.code());
        assertEquals(8800L, created.balance());

        Account fromDatabase = repository.findByCode("AC-88")
                .orElseThrow();

        assertEquals(8800L, fromDatabase.getBalance());
    }
}
```

Ở đây chỉ có **một annotation slice**: `@DataJpaTest`. `@Import(AccountService.class)` đăng ký đúng service cần kiểm tra trong context slice; service có dependency `AccountRepository` mà JPA slice cung cấp. Không cần controller, `MockMvc` hay server.

### Khi nào `@Import` phù hợp?

- Một service chỉ có vài dependency rõ ràng và tất cả đều có trong JPA slice.
- Một converter/configuration nhỏ hỗ trợ serializer/repository.
- Một test bean/fake cần thêm vào context.
- Một policy hoặc validator được kiểm tra cùng adapter, không kéo theo cả ứng dụng.

### Khi nào `@Import` trở nên nguy hiểm?

Nếu `@Import` một `@Configuration` lớn có `@ComponentScan` toàn ứng dụng, `@EnableScheduling`, HTTP clients, security hoặc nhiều `@Bean` phụ thuộc remote services, ranh giới slice có thể bị mở rộng quá mức. Khi đó test không còn “nhẹ” hoặc “rõ phạm vi”, dù trên class vẫn chỉ có `@DataJpaTest`.

**Quy tắc:** import một tập bean nhỏ có thể giải thích, không import toàn bộ application configuration chỉ để tránh viết test tích hợp. Nếu service thực sự phụ thuộc MVC + database + message broker, chọn full integration test phù hợp.

## 11. Test 4 — Cần HTTP và JPA thật: `@SpringBootTest` + `@AutoConfigureMockMvc`

Khi hợp đồng yêu cầu:

> Gửi `POST /api/accounts` phải trả HTTP 201 với account JSON đúng và account đó phải truy vấn được từ database.

Đây là một **luồng nhiều tầng**, không còn một slice đơn lẻ. Cách rõ ràng là dùng **full Boot context** và bổ sung test infrastructure cho MockMvc.

**`src/test/java/example/AccountFlowIntegrationTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        classes = SliceDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop"
)
@AutoConfigureMockMvc
@Transactional
class AccountFlowIntegrationTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    AccountRepository repository;

    @Test
    void postReturns201AndPersistsReadableAccount() throws Exception {
        mvc.perform(post("/api/accounts")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"code":"AC-99","balance":9900}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.code").value("AC-99"))
                .andExpect(jsonPath("$.balance").value(9900));

        Account persisted = repository.findByCode("AC-99")
                .orElseThrow();
        assertEquals(9900L, persisted.getBalance());

        mvc.perform(get("/api/accounts/{id}", persisted.getId()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("AC-99"))
                .andExpect(jsonPath("$.balance").value(9900));
    }
}
```

**Đây là tổ hợp hợp lệ**, bởi:

- `@SpringBootTest` chọn cơ chế bootstrap và **phạm vi full context**.
- `@AutoConfigureMockMvc` thêm/configure `MockMvc` cho context đó. Nó **không phải** một annotation slice `@…Test` thứ hai.
- `@Transactional` đặt test method trong một test-managed transaction khi có transaction manager, với rollback mặc định; `MockMvc` đồng bộ trong mock servlet environment thường thực thi trên thread test.
- H2 được dùng trên test runtime; schema được tạo theo property test.
- Controller, service và repository đều là **bean thật** trong ứng dụng.

### Điều được chứng minh

- `POST` mapping/JSON request, service, JPA save và HTTP 201 body đi qua luồng thật trong Spring context.
- Repository tìm thấy account vừa ghi trong **test transaction**.
- `GET` truy cập account bằng ID đã lưu được và trả JSON đúng.

### Điều chưa được chứng minh

- HTTP socket/server TCP thật: `MockMvc` không mở cổng mạng.
- Commit/visibility từ giao dịch khác: test có `@Transactional` và rollback sau khi hoàn tất.
- SQL dialect hoặc transaction behavior tuyệt đối giống production nếu DB thật dùng PostgreSQL/MySQL.
- Hiệu ứng của remote services khác, vì ví dụ không có.

Nếu yêu cầu thử HTTP thật, có thể dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và `TestRestTemplate`/HTTP client thích hợp; lúc đó server thread và test thread có transaction khác, nên **rollback test không tự rollback dữ liệu server đã commit**. Cần fixture isolation/cleanup thật, không giả định giống `MockMvc`.

## 12. Chạy các test mẫu và diễn giải kết quả

Dự án cần Gradle Wrapper tương thích (ví dụ Gradle 8.5 với Boot 3.3.0), JDK 17+ và truy cập repository:

```bash
./gradlew test
./gradlew test --tests example.AccountControllerSliceTest
./gradlew test --tests example.AccountRepositorySliceTest
./gradlew test --tests example.AccountServiceJpaSliceTest
./gradlew test --tests example.AccountFlowIntegrationTest
```

Trên Windows:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.AccountFlowIntegrationTest
```

Với code như ví dụ, dự kiến **4 test methods pass** (mỗi class một method). Gradle thường kết thúc bằng `BUILD SUCCESSFUL` nếu tasks thành công; số task/thời gian/log startup không cố định và không phải output dùng để assertion.

Không cần tự viết test “chồng hai slice” trong source tree để kiểm chứng: đó là **anti-pattern đã được Spring Boot tài liệu hóa là unsupported**. Nếu muốn học cơ chế lỗi, chỉ thử trên nhánh sandbox và hoàn nguyên, không đưa vào CI của dự án.

**Quan sát khác biệt runtime:** MVC slice thường không phải dựng JPA database; JPA slice không cần MVC dispatcher; integration test full context có thể tạo cả hai. Đó là những ranh giới cần thấy rõ khi đọc log/bean list, thay vì chỉ so tổng thời gian.

## 13. “Một slice + auto-config khác” được hiểu thế nào cho đúng?

Tài liệu Spring Boot 3.3 nêu rằng nếu cần khả năng test bổ sung, **chọn một `@…Test` annotation rồi thêm các `@AutoConfigure…` của vùng khác theo cách tường minh**, hoặc dùng `@AutoConfigure…` cùng `@SpringBootTest` khi không cần slicing.

Điều này **không mâu thuẫn** với quy tắc “không chồng slice”:

- `@WebMvcTest` và `@DataJpaTest` đều là **slice selectors**, có bootstrap/filter/context design riêng.
- `@AutoConfigureMockMvc` là **test auto-configuration hỗ trợ MockMvc**, không phải selector một context slice độc lập.
- `@AutoConfigureTestDatabase` là test database configuration, không phải `@DataJpaTest`.
- `@Import` đăng ký một bean/configuration được chọn.
- `@ImportAutoConfiguration` có thể dùng để nhập một auto-configuration cụ thể theo cơ chế Boot khi cần.

Ví dụ hợp lệ:

```java
// Một Boot context, thêm hạ tầng MockMvc:
@SpringBootTest
@AutoConfigureMockMvc
class HttpAndPersistenceFlowIT {
    // ...
}

// Một JPA slice, thêm một bean nghiệp vụ cụ thể:
@DataJpaTest
@Import(AccountService.class)
class ServiceWithJpaIT {
    // ...
}

// Một MVC slice, mock collaborator ngoài scope:
@WebMvcTest(AccountController.class)
class AccountWebTest {
    @MockBean AccountService service;
}
```

Đây là **các kiểu cấu hình**, cần class ứng dụng, import và test logic thực khi sử dụng. Không ngầm bảo đảm rằng bạn có thể đặt `@AutoConfigureMockMvc` trên `@DataJpaTest` rồi có MVC context: JPA slice có thể không có servlet web application context, MVC controller và tất cả prerequisites của MockMvc. Nếu phải thêm nhiều hạ tầng để test chạy, hãy đánh giá lại rằng bạn đang viết **integration test**.

### 13.1. `@Import` và `@ImportAutoConfiguration` khác nhau

- **`@Import`**: nhập một Java configuration/bean class cụ thể, ví dụ `@Import(AccountService.class)`. Phù hợp với bean phụ trợ hoặc component ứng dụng mà bạn chủ động chọn.
- **`@ImportAutoConfiguration`**: nhập các **auto-configuration classes** theo cách Spring Boot hỗ trợ cho test, thay vì dùng `@Import` thường để đưa một auto-configuration vào context không đúng semantics. Boot cho phép `@ImportAutoConfiguration(exclude=...)` và cơ chế nhập có chọn lọc tùy annotation.

Đừng import toàn bộ `@SpringBootApplication` qua một slice chỉ để “khôi phục” mọi bean bị filter. Điều đó dễ biến test thành context hỗn hợp và khó hiểu hơn dùng `@SpringBootTest`.

### 13.2. Thêm test collaborator sao cho có chủ đích

Khi controller cần một service, có ba lựa chọn:

1. **Mock service:** `@WebMvcTest` + `@MockBean`/`@MockitoBean`, test HTTP contract.
2. **Import service thật vào MVC slice:** chỉ khi service thực sự gọn, mọi dependency có thể cung cấp hợp lý và bạn muốn test logic service gần MVC; lưu ý ranh giới đã rộng hơn. Nếu service cần repository, MVC slice chưa tự mang JPA.
3. **Full integration:** `@SpringBootTest` + `@AutoConfigureMockMvc` và repository/database thật, test nhiều tầng.

Chọn theo **rủi ro cần được xác minh**, không chỉ theo cách viết ít annotation.

## 14. Những tổ hợp sai hoặc dễ gây nhầm lẫn

| Tổ hợp | Đánh giá | Vì sao |
| --- | --- | --- |
| `@WebMvcTest` + `@DataJpaTest` | **Không được hỗ trợ** | Hai selectors/bootstrap contexts |
| `@WebMvcTest` + `@JsonTest` | **Không được hỗ trợ** | Hai slice selectors, không phải phép cộng JSON |
| `@DataJpaTest` + `@JdbcTest` | **Không được hỗ trợ** | Hai slice selectors và auto-configuration khác |
| `@SpringBootTest` + `@WebMvcTest` | **Không dùng để ghép context** | Full Boot và slice bootstrap không phải tổ hợp được thiết kế |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | **Phù hợp** | Full context + test tool |
| `@DataJpaTest` + `@Import(AccountService.class)` | **Phù hợp nếu dependency rõ** | Một slice + bean được chỉ định |
| `@WebMvcTest` + `@MockBean Service` | **Phù hợp trong Boot 3.3** | Controller thật + service mock |
| `@DataJpaTest` + `@AutoConfigureTestDatabase` | **Phù hợp khi DB cần cấu hình** | Một slice + test database choice |
| `@RestClientTest` + `@WebMvcTest` | **Không được hỗ trợ** | Client và server slices khác mục tiêu |
| `@SpringBootTest` + `@AutoConfigureWebTestClient` | **Có thể phù hợp với stack/mục tiêu** | Full context + WebTestClient tool đúng version |

Mọi lựa chọn `@AutoConfigure…` vẫn phải kiểm tra prerequisites của công nghệ, classpath và phiên bản. “Phù hợp về cấu trúc annotation” không đảm bảo bean graph sẽ nạp được trong mọi ứng dụng.

## 15. Test slice và Spring Security

Với `spring-boot-starter-security` trên classpath, MVC slice có thể bao gồm security-related infrastructure và filters. Nếu test dự kiến HTTP 200 nhưng nhận 401/403, không phải tự động vì đang “thiếu JPA slice”.

Giải pháp đúng:

- Quyết định controller contract có yêu cầu identity, role, CSRF không.
- Dùng Spring Security Test, ví dụ `@WithMockUser` và request postprocessors cho MockMvc khi thích hợp.
- Nếu muốn kiểm tra security filters thật, giữ chúng trong phạm vi test.
- Chỉ vô hiệu hóa filter bằng `@AutoConfigureMockMvc(addFilters=false)` trong những test mà filter behavior **thực sự ngoài phạm vi**, và ghi rõ test **không còn chứng minh security**.

Thêm `@DataJpaTest` không giúp giải quyết HTTP 401/403. Ngược lại, cần account từ DB cho security policy thì có thể là integration test thực, dùng full context và test DB.

## 16. JPA slice: embedded database, transaction và giới hạn

`@DataJpaTest` thường:

- nạp entities và Spring Data JPA repositories;
- dùng embedded database có sẵn trên classpath khi thích hợp;
- cấu hình `TestEntityManager`;
- chạy mỗi test trong transaction được rollback mặc định;
- loại nhiều application services/controllers khỏi component scan.

Các điểm cần tránh hiểu nhầm:

1. H2 hoạt động không bảo đảm query dialect của PostgreSQL production hoạt động như nhau.
2. `saveAndFlush`/`persistAndFlush` + `clear` giúp kiểm tra query sau flush, nhưng **không chứng minh commit** nếu test transaction rollback.
3. `@Transactional(propagation=NOT_SUPPORTED)` có thể tắt test-managed transaction trong trường hợp cần thiết, nhưng phải quản lý cleanup và fixture cho đúng.
4. `@AutoConfigureTestDatabase(replace=NONE)` có thể dùng khi bạn chủ đích giữ datasource được cung cấp (ví dụ Testcontainers); phải xác nhận kết nối đó **không phải production DB**.
5. `@DataJpaTest` không tự khởi động HTTP server hoặc làm `MockMvc` xuất hiện.

Nếu repository cần kiểm tra unique constraint, locking, transaction isolation hoặc native SQL, chọn database đúng mức thực tế. Nếu chỉ kiểm tra query derived đơn giản, H2 test database giúp phản hồi nhanh và dễ cô lập.

## 17. Spring TestContext cache: phạm vi càng lẫn lộn, chi phí càng khó hiểu

Spring TestContext giữ context cache theo cấu hình kết hợp: các classes/locations, active profiles, test properties, context customizers, bean overrides, initializers và loader.

Khi chia test theo ranh giới rõ:

```text
AccountControllerSliceTest (@WebMvcTest + mock service)
    -> MVC context A

AccountRepositorySliceTest (@DataJpaTest)
    -> JPA context B

AccountServiceJpaSliceTest (@DataJpaTest + @Import service)
    -> JPA context C (cấu hình khác B)

AccountFlowIntegrationTest (@SpringBootTest + MockMvc)
    -> Full Boot context D
```

Các context ở ví dụ thường khác vì cấu hình khác. Việc **nạp context khác nhau có lý do** không phải điều xấu: mỗi test chứng minh một lớp hành vi cụ thể.

Ngược lại, nếu mỗi test class tùy tiện import một tập `@Configuration` và mocks khác nhau, số cache keys có thể bùng lên. Suite chậm hơn và lỗi injection khó hiểu hơn. Không dùng `@DirtiesContext` để “dọn” context vì nhiều annotation không rõ; nó có thể làm reload liên tục.

**Quan trọng:** context cache không reset state của bean singleton. Với JPA slice, rollback chỉ xử lý dữ liệu trong transaction của test theo cấu hình; một runner hoặc service khác đã commit ở startup không tự được rollback. Giữ fixture/DB state độc lập, không phụ thuộc thứ tự test.

## 18. Mã phản ví dụ và cách sửa tối thiểu

### Tình huống A: Web slice thiếu `AccountService`

Sai hướng:

```java
@WebMvcTest(AccountController.class)
@DataJpaTest // Cố lấy thêm repository để service xuất hiện.
class IncorrectTest { }
```

Cách sửa nếu cần chỉ HTTP:

```java
@WebMvcTest(AccountController.class)
class ControllerOnlyTest {
    @MockBean
    AccountService service;
}
```

Nếu thực sự muốn service thật + database: không dùng cả hai slice; chọn `@SpringBootTest` + `@AutoConfigureMockMvc`.

### Tình huống B: JPA slice thiếu service

Sai hướng:

```java
@DataJpaTest
@WebMvcTest(AccountController.class)
class IncorrectServiceTest { }
```

Nếu service chỉ cần repository và bạn muốn test use case ở database boundary:

```java
@DataJpaTest
@Import(AccountService.class)
class ServiceRepositoryTest {
    @Autowired AccountService service;
}
```

Khi service có nhiều collaborators ngoài JPA, test JPA slice có thể không còn thích hợp; dùng full context hoặc unit test với fake/Mockito.

### Tình huống C: Full integration cần MockMvc

Sai hướng:

```java
@SpringBootTest
@WebMvcTest(AccountController.class)
class WrongFullTest { }
```

Sửa:

```java
@SpringBootTest
@AutoConfigureMockMvc
class FullHttpFlowTest {
    @Autowired MockMvc mvc;
}
```

**Điểm phân biệt:** `@AutoConfigureMockMvc` chỉ cấu hình test infrastructure, còn `@WebMvcTest` định nghĩa một slice riêng. Nếu muốn socket HTTP thật, dùng `RANDOM_PORT` thay vì giả định `MockMvc` gửi request qua mạng.

### Tình huống D: Dùng `@Import` để né ranh giới

Rủi ro:

```java
@WebMvcTest(AccountController.class)
@Import(BigProductionConfiguration.class)
class ExpandingSliceTest { }
```

Mã này có thể compile, nhưng `BigProductionConfiguration` (giả định) nếu quét mọi bean và kích hoạt DB/events sẽ làm context khó dự đoán. Cần review xem bean nào bị thêm, filter nào còn áp dụng, external effects nào chạy. Nếu cần cả ứng dụng, nói rõ mục tiêu integration và dùng `@SpringBootTest` thay vì “nới” slice đến không còn ý nghĩa.

Các đoạn ở mục này là **ví dụ cấu hình rút gọn**, không phải class test chạy độc lập; những type chưa khai báo là minh họa. Code hoàn chỉnh có ở mục 7–11.

## 19. Debug theo lỗi thực sự, không thêm annotation theo phản xạ

| Triệu chứng | Nguyên nhân có khả năng | Hướng kiểm tra |
| --- | --- | --- |
| `found multiple declarations of @BootstrapWith` | Nhiều slice/full bootstrap annotations trên class | Bỏ annotation xung đột, chọn một context strategy |
| `No qualifying bean of type AccountService` trong MVC test | `@WebMvcTest` không scan service thường | Mock collaborator hoặc full context |
| `NoSuchBeanDefinitionException` khi `@DataJpaTest` inject controller | JPA slice không nạp MVC | Bỏ controller khỏi JPA test hoặc dùng full context |
| `NoSuchBeanDefinitionException: MockMvc` trong JPA test | Không có MVC auto-config/context | Đừng trộn MVC; chọn full+`@AutoConfigureMockMvc` |
| `Failed to configure DataSource` | Thiếu DB driver, URL, credentials hoặc test db | Kiểm tra H2/Testcontainers/profile |
| HTTP 401/403 trong web test | Spring Security filter/CSRF | Kiểm tra authentication/security test |
| `@SpringBootConfiguration` không tìm thấy | Test package hoặc primary config không tìm được | Đặt test đúng package hoặc `classes=...` |
| Bean trùng/ambiguous | `@Import` quá rộng hoặc nhiều impl cùng type | Thu hẹp cấu hình, `@Qualifier`/`@Primary` có căn cứ |
| Test startup rất chậm | Full context quá lớn hoặc nhiều context keys | Trả test đúng slice; giảm import/mock tùy tiện |
| JPA test pass nhưng production SQL fail | H2 khác dialect/schema/locking | Test với DB tương thích production |
| HTTP test pass nhưng DB không có record | Service bị mock hoặc persistence ngoài scope | Thêm một integration test đúng ranh giới |
| Build xanh nhưng không chạy test | Sai JUnit Platform/engine/filter | Kiểm tra số test thật được discovery |
| `Failed to load ApplicationContext` lặp nhiều lần | Spring context failure threshold sau lỗi đầu | Tìm root cause lần load context đầu tiên |

### 19.1. Quy trình tìm lỗi gốc

1. Xem **đúng class test** và danh sách annotations/meta-annotations.
2. Xác định ranh giới muốn test: HTTP, JPA, client, JSON hay full integration.
3. Xem dependency/bean bị thiếu có thuộc phạm vi dự kiến không.
4. Đọc stack trace đầu tiên của `Failed to load ApplicationContext`; phân biệt bootstrap error với lỗi bean/runtime.
5. Kiểm tra active profiles, bean overrides, datasource properties và classpath.
6. Thay đổi **ít nhất có căn cứ**: mock collaborator, import service nhỏ, hoặc chuyển sang full context.
7. Chạy lại đúng class và cả suite để phát hiện state/context-cache issues.
8. Xem số test thực thi và assertion, không coi chỉ có `contextLoads` pass là đủ.

**Không sửa triệu chứng bằng cách cứ thêm `@SpringBootTest` hoặc thêm mọi starter**. Nó có thể che nguyên nhân bằng cách nạp thêm bean, khiến test chậm và phạm vi khó kiểm soát.

## 20. Kiến thức phiên bản: Spring Boot 3.x và 4.x

Bài mẫu cố định **Spring Boot 3.3.0** để chạy với imports:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.mock.mockito.MockBean;
```

Ở Spring Boot **3.4+**, Spring Framework 6.2 đưa vào `@MockitoBean` thay `@MockBean` (annotation Boot cũ deprecated). Sang **Spring Boot 4**, phần test được chia thành module/starter theo chức năng và package imports có thể khác, ví dụ:

```java
// Spring Boot 4.x: kiểm tra module/starter phù hợp trước khi import.
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

Hai nhóm imports là **phương án theo dòng phiên bản**, không ghép vào một class Java. Với Boot 4, các starter như `spring-boot-starter-webmvc-test` và `spring-boot-starter-data-jpa-test` giúp tải test modules tương ứng, nhưng **việc có cả hai starter trong build không có nghĩa được dùng cả hai slice trên cùng test class**.

Quy tắc “không chồng nhiều `@…Test`” không phụ thuộc vào tên import cũ/mới: nó phản ánh cách Spring Boot thiết kế context slicing.

Khi nâng cấp:

- Nâng Spring Boot BOM đồng bộ với Framework, JUnit, Mockito và test starters.
- Chuyển `@MockBean` sang `@MockitoBean` ở dòng phù hợp, kiểm tra bean override semantics.
- Đổi imports của slice/test auto-configuration đúng phiên bản.
- Giữ bốn test kiểu mục 7–11 để kiểm tra từng ranh giới vẫn bảo vệ hành vi.
- Nếu một slice mới thiếu bean, tìm module/configuration đúng, không khôi phục mọi bean vô điều kiện.
- Không ép artifact Boot 3.x vào BOM Boot 4 chỉ để một annotation cũ tồn tại.

## 21. Thực hành: chọn ranh giới thay vì thêm annotation

### Bài 1 — Sửa test chồng slice

Đưa code sau vào nhánh học tập, **không giữ trong CI**:

```java
@WebMvcTest(AccountController.class)
@DataJpaTest
class CombinedTest { }
```

Giải thích vì sao Spring Boot không hỗ trợ hai slice selectors trên cùng class. Chọn một trong hai hướng:

- Mục tiêu HTTP JSON → giữ `@WebMvcTest`, mock service.
- Mục tiêu POST trả 201 và ghi DB → `@SpringBootTest` + `@AutoConfigureMockMvc`.

**Tiêu chí:** học viên phát biểu được hợp đồng nào mỗi hướng chứng minh.

### Bài 2 — Nâng phạm vi khi yêu cầu thay đổi

Ban đầu test chỉ yêu cầu controller trả `{"code":"AC-41"}` khi service cung cấp account. Sau đó product owner yêu cầu: “POST thành công phải tạo record thật trong DB.” Tại sao chỉ thêm `@DataJpaTest` vào MVC test là sai? Hãy chuyển test sang full context, để service/repository chạy thật, query DB sau request.

### Bài 3 — Giữ JPA slice gọn bằng `@Import`

Dùng `AccountServiceJpaSliceTest` trong ví dụ. Bỏ `@Import(AccountService.class)`: service không còn được scan trong JPA slice; test injection có thể fail. Thêm lại. Giải thích tại sao không cần controller/MVC để test service với repository.

### Bài 4 — Bắt lỗi mock làm mất phạm vi

Trong `AccountControllerSliceTest`, sửa tạm `AccountService.get` của production để trả sai code. MVC slice vẫn có thể pass vì service bị mock. Trong `AccountFlowIntegrationTest`, thay logic service trong nhánh thí nghiệm để trả sai dữ liệu; assertion GET/DB cần bắt được khi mutation ảnh hưởng contract. Khôi phục code.

**Bài học:** không có test đơn lẻ nào mặc định chứng minh mọi tầng. Phải biết vùng mù của test và bổ sung đúng lớp bằng chứng.

### Bài 5 — Không lạm dụng full context

Đo thời gian `AccountControllerSliceTest` và `AccountFlowIntegrationTest` trên cùng máy sau warm-up. Giải thích vì sao full context thường nặng hơn, nhưng không lấy một phép đo lẻ làm định luật. Cache, classpath, JVM và database ảnh hưởng kết quả.

### Bài 6 — Transaction và database thực

Đổi H2 sang Testcontainers PostgreSQL trong nhánh học tập. Cấu hình datasource và `@AutoConfigureTestDatabase(replace=NONE)` nếu phù hợp. So sánh behavior của constraint/schema/query giữa hai DB. Không sử dụng database production, không dựa vào rollback test để dọn transaction đã commit ở request khác.

### Bài 7 — Phân loại annotation

Với mỗi annotation dưới đây, xác định nó là **slice selector**, **full context selector** hay **test infrastructure customizer**:

| Annotation | Phân loại |
| --- | --- |
| `@WebMvcTest` | Slice |
| `@DataJpaTest` | Slice |
| `@JsonTest` | Slice |
| `@RestClientTest` | Slice |
| `@SpringBootTest` | Full context |
| `@AutoConfigureMockMvc` | Test auto-configuration |
| `@AutoConfigureTestDatabase` | Test database configuration |
| `@Import(AccountService.class)` | Explicit bean import |
| `@MockitoBean` / `@MockBean` | Bean override/test double |

Hãy giải thích vì sao **hai selectors** khác với **một selector cộng một customizer**.

## 22. Checklist review test boundary

- [ ] Tôi có thể mô tả một câu nghiệp vụ về kết quả test cần xác minh.
- [ ] Test class có **đúng một context strategy**: một slice hoặc full Spring Boot context.
- [ ] Không chồng `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, `@RestClientTest`... trên cùng class.
- [ ] Không đặt `@WebMvcTest` lên `@SpringBootTest` để “vừa full vừa slice”.
- [ ] Tôi phân biệt `@AutoConfigure…` với `@…Test` slice selector.
- [ ] Service/repository bị mock có thật sự nằm **ngoài mục tiêu test** không?
- [ ] Nếu một bean ngoài slice cần thiết, tôi chọn mock, `@Import` nhỏ hoặc full integration có căn cứ.
- [ ] Tôi không import một production configuration lớn để vô tình phá ranh giới slice.
- [ ] Với MVC test, tôi assert status/JSON/header/security contract.
- [ ] Với JPA test, tôi assert persist/query/constraint/transaction phù hợp.
- [ ] Với multi-layer test, tôi dùng full context và quan sát HTTP + persisted state khi cần.
- [ ] Test DB là môi trường an toàn, không trỏ production; rollback/commit được hiểu đúng.
- [ ] Tôi biết H2 không bảo đảm mọi behavior DB production.
- [ ] Tôi hiểu test context cache có thể tái sử dụng context và chia sẻ singleton state.
- [ ] Tôi kiểm tra Spring Boot version, test starters và imports phù hợp.
- [ ] Khi test fail, tôi tìm root cause thay vì thêm slice annotation theo phản xạ.
- [ ] Tôi chạy đúng JUnit Platform và kiểm tra số test thực chạy.

## 23. Sơ đồ quyết định cuối bài

```text
Cần xác minh kết quả gì?
    |
    +--> Tính toán/service logic thuần?
    |       -> JUnit + Mockito/fake, không cần Spring.
    |
    +--> HTTP mapping/JSON?
    |       -> @WebMvcTest + mock service ngoài slice.
    |
    +--> Repository/JPA?
    |       -> @DataJpaTest + database test.
    |
    +--> Service + JPA, không cần web?
    |       -> @DataJpaTest + @Import(service nhỏ)
    |          hoặc integration service test.
    |
    +--> Controller + service + DB thật?
            -> @SpringBootTest + @AutoConfigureMockMvc
               (hoặc RANDOM_PORT nếu cần socket thật).

Không làm:
    @WebMvcTest + @DataJpaTest
    @WebMvcTest + @JsonTest
    @SpringBootTest + @WebMvcTest

Chỉ bổ sung @AutoConfigure... / @Import khi biết chính xác
prerequisites và ranh giới cần giữ.
```

**Thông điệp cốt lõi:** test slice là một **quyết định loại trừ có chủ ý**, không phải các mảnh Spring context có thể ghép chồng tùy tiện. Càng muốn xác minh nhiều tầng thật, càng nên chuyển sang một integration test được khai báo rõ bằng `@SpringBootTest`, thay vì khiến một slice thành context nửa web nửa JPA không thể giải thích.

## 24. Tài liệu chính thức

- Spring Boot 3.3 — Testing Spring Boot Applications, “Auto-configured Tests”: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Test slices và danh sách auto-configuration: https://docs.spring.io/spring-boot/3.3/appendix/test-auto-configuration/slices.html
- Spring Boot — Testing Spring Boot Applications (dòng mới): https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Spring Boot — Test Modules (dòng 4.x): https://docs.spring.io/spring-boot/reference/testing/test-modules.html
- Spring Boot — Test Slices appendix (dòng mới): https://docs.spring.io/spring-boot/appendix/test-auto-configuration/slices.html
- Spring Framework — TestContext Framework: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html
- Spring Framework — Context Caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework — Testing Transactions: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- JUnit Jupiter User Guide: https://docs.junit.org/current/user-guide/
