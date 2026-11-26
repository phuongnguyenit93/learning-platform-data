# Phụ thuộc Spring Data khi sử dụng repository

Trong **SPRING_VAULT**, cách truy cập HashiCorp Vault phổ biến nhất là gọi `VaultTemplate` để đọc KV secrets, xác thực theo workload và xử lý token/lease; các nghiệp vụ Transit encryption và PKI cũng có API domain riêng. Khi cần lưu nhiều đối tượng có cấu trúc dưới **KV secrets engine**, Spring Vault còn hỗ trợ mô hình **Spring Data repository**: định nghĩa entity và interface `CrudRepository`, sau đó Spring tạo implementation đọc/ghi Vault.

**Chương:** Phiên bản và phụ thuộc. Bài học trả lời câu hỏi **khi nào cần thêm Spring Data, phải thêm những artifact nào và chúng tác động ra sao tới cách ứng dụng lưu secret**. Phần minh họa dùng KV v2, phiên bản có optimistic locking và phân quyền tối thiểu.

Sau khi hoàn thành, người học có thể:

- Phân biệt `VaultTemplate` thuần với `Vault repository`, Spring Cloud Vault Config Data và các loại repository của Spring Data khác.
- Chọn đúng `spring-data-keyvalue`, `spring-data-commons` cùng Spring Data BOM tương thích với `spring-vault-core`.
- Cấu hình `@EnableVaultRepositories`, `@Secret`, `@Id`, `@Version` và interface repository.
- Hiểu keyspace, JSON mapping, giới hạn truy vấn theo ID, paging/sorting và KV v2 CAS.
- Kiểm tra policy, mount discovery, phụ thuộc runtime, lỗi mapping và kiểm thử thực tế.

> **Mốc tham chiếu: 25/11/2026.** Ví dụ nhắm đến **Spring Vault 4.1.2**, Java 17+ và dòng Spring Framework 7.0 tương thích; trang repository của Spring Vault 4.1 dùng **Spring Data release train 2026.0.0** làm ví dụ BOM. Ở dự án có Spring Boot, ưu tiên BOM Boot để đồng bộ Spring Framework, Spring Data, JSON và HTTP client. Cần đối chiếu phiên bản thực tế bằng dependency tree trước khi phát hành.

## 1. Repository của Vault dùng để làm gì?

Với `VaultTemplate`, code trực tiếp chọn mount và secret path:

```java
VaultResponse response = vaultOperations
    .opsForKeyValue("secret", KeyValueBackend.KV_2)
    .get("orders/config");
```

Với repository, code định nghĩa **một entity được lưu như một secret** và Spring Data cung cấp các thao tác quen thuộc:

```java
OrderConfigSecret settings = repository.findById("orders")
    .orElseThrow();

settings.setRetryLimit(5);
repository.save(settings);
```

Các đoạn minh họa giả định biến `vaultOperations`, `repository` và import đã được tạo ở Spring context. Khác biệt quan trọng là **repository vận hành trên key/value secrets engine**, không biến Vault thành SQL/NoSQL database có chỉ mục và truy vấn tùy ý.

| Vấn đề | `VaultTemplate` / `VaultOperations` | Spring Data Vault repository |
| --- | --- | --- |
| Dependency chính | `spring-vault-core` | `spring-vault-core` **cộng** Spring Data Commons/KeyValue |
| Đường dẫn secret | Code chỉ định mount và path | `@Secret` + `@Id` tạo keyspace/path |
| Mapping | `VaultResponse`, `Map`, DTO | `VaultConverter` và Spring Data mapping metadata |
| CRUD | Gọi `get`/`put`/`delete` rõ ràng | `save`, `findById`, `existsById`, `deleteById` |
| Truy vấn | Tự gọi KV list/read nếu cần | Query derivation **giới hạn theo ID**, sorting/paging có chi phí |
| KV v2 version | `opsForVersionedKeyValue` | `@Version` dùng CAS; `RevisionRepository` đọc revisions |
| Transit, PKI, token, lease | Có API domain tương ứng | **Không phải mục đích** của KV repository |
| Reactive | Có `ReactiveVaultTemplate` | Tài liệu Vault repository tập trung interface **đồng bộ**; không suy rằng `ReactiveCrudRepository` được hỗ trợ |

**Quyết định thực tế:** nếu ứng dụng chỉ cần vài secret cấu hình hoặc gọi Transit/PKI, `VaultTemplate` thường đơn giản hơn. Repository phù hợp khi nhiều đối tượng KV có schema ổn định và đội phát triển muốn dùng chung mô hình aggregate/CRUD với Spring Data.

## 2. Dependency nào là bắt buộc?

Các lớp `@EnableVaultRepositories`, `@Secret` và Vault-specific mapping/adapter **đã nằm trong `spring-vault-core`**. Tuy nhiên phần hợp đồng repository, mapping metadata và hạ tầng KeyValue nằm ở **Spring Data**; tài liệu chính thức yêu cầu cả:

| Artifact | Chứa gì | Cần thiết khi nào? |
| --- | --- | --- |
| `org.springframework.vault:spring-vault-core` | `VaultTemplate`, repository adapter, `@Secret`, `@EnableVaultRepositories`, `VaultConverter` | **Bắt buộc** |
| `org.springframework.data:spring-data-keyvalue` | `KeyValueTemplate`, KeyValue repository factory, query derivation và mapping nền | **Bắt buộc** khi bật Vault repositories |
| `org.springframework.data:spring-data-commons` | `CrudRepository`, `@Id`, `@Version`, `Pageable`, `RevisionRepository` | **Bắt buộc về mặt classpath**, thường do `spring-data-keyvalue` kéo transitively |
| `tools.jackson.core:jackson-databind` trên stack Framework 7 / Vault 4.x | Giải mã/mã hóa JSON từ Vault | Cần có mapper tương thích; có thể đã được starter/BOM ứng dụng cung cấp |
| HTTP client phù hợp, TLS, `SessionManager` | Kết nối Vault và quản lý token | Hạ tầng runtime phải được cấu hình, dù repository không trực tiếp thấy nó |
| `spring-cloud-starter-vault-config` | Tích hợp Vault vào Spring Environment/Config Data | **Tùy chọn**; không phải dependency bắt buộc của Vault repository |
| `spring-data-jpa`, `spring-data-redis`, `spring-data-mongodb` | Repository cho những store khác | **Không cần** chỉ vì bạn dùng Vault repository |

**Không tìm một JAR riêng `spring-vault-repository`:** repository support đã có trong Core nhưng các dependency Spring Data có thể được khai báo là tùy chọn; vì vậy chỉ khai báo Core chưa chắc tạo được bean repository. Nếu muốn thao tác KV với `VaultTemplate` thuần, hoàn toàn **không cần Spring Data**.

### 2.1. Maven với Spring Boot parent/BOM

Ví dụ dự án **đã sử dụng Spring Boot 4.1.3 parent** và Java 17:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
              https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.3</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>orders-vault-repository</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.vault</groupId>
      <artifactId>spring-vault-core</artifactId>
      <version>4.1.2</version>
    </dependency>
    <dependency>
      <groupId>org.springframework.data</groupId>
      <artifactId>spring-data-keyvalue</artifactId>
    </dependency>
    <dependency>
      <groupId>tools.jackson.core</groupId>
      <artifactId>jackson-databind</artifactId>
    </dependency>
  </dependencies>
</project>
```

`spring-data-commons` được `spring-data-keyvalue` kéo theo thông thường; **phải xác minh** sau `exclude` hoặc override. Jackson 3 trong ví dụ được Boot 4 quản lý phiên bản; thiếu Boot parent/BOM, khai báo không có `version` này sẽ không thể resolve. Đoạn POM minh họa dependency, chưa tạo bean `VaultTemplate` và chưa cấu hình Vault auth/TLS.

**Không nên gắn thêm Spring Data BOM tùy tiện** nếu Boot đã quản lý đúng Spring Data train: hai BOM khác thế hệ có thể làm `spring-data-keyvalue` và `spring-data-commons` lệch nhau. Khi cần patch mới vì lý do cụ thể, nâng cả release train rồi kiểm thử.

### 2.2. Maven thuần Spring Framework: import Spring Data BOM

Khi dự án không có Spring Boot BOM, có thể nhập Spring Data BOM như tài liệu Vault repository 4.1 minh họa:

```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.springframework.data</groupId>
      <artifactId>spring-data-bom</artifactId>
      <version>2026.0.0</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>org.springframework.vault</groupId>
    <artifactId>spring-vault-core</artifactId>
    <version>4.1.2</version>
  </dependency>
  <dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-keyvalue</artifactId>
  </dependency>
</dependencies>
```

**Đây chỉ là phần quản lý Spring Data và Core**, không phải POM chạy độc lập: Spring Framework 7, JSON mapper, HTTP transport và các plugin/build settings vẫn cần được quản lý đồng bộ. Kiểm tra release train chính xác khi thay version. Spring Data BOM không tự kéo `spring-data-keyvalue` vào classpath nếu bạn không khai báo dependency.

### 2.3. Gradle Kotlin DSL

Ví dụ dùng Gradle native BOM để tránh tự chọn từng bản Spring Data:

```kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:4.1.3"))
    implementation("org.springframework.vault:spring-vault-core:4.1.2")
    implementation("org.springframework.data:spring-data-keyvalue")
    implementation("tools.jackson.core:jackson-databind")

    testImplementation("org.junit.jupiter:junit-jupiter")
}

tasks.test {
    useJUnitPlatform()
}
```

Ở đây Gradle `platform(...)` chỉ nhập dependency constraints của Boot; nó **không tự khởi động ứng dụng Boot**. Nếu dự án đã dùng `org.springframework.boot` plugin hay `io.spring.dependency-management`, áp dụng thống nhất cách quản lý BOM và xem dependency thực sự được resolve.

Nguồn: [Spring Vault – Vault Repositories](https://docs.spring.io/spring-vault/reference/vault/vault-repositories.html), [Spring Data – Dependencies](https://docs.spring.io/spring-data/keyvalue/reference/data-commons/dependencies.html).

## 3. Từ VaultTemplate đến Vault repository: các lớp hoạt động ra sao?

```text
Business service
   │
   └── OrderConfigRepository extends CrudRepository
            │  (Spring Data Commons)
            ▼
      VaultRepositoryFactory
            │  (Spring Data KeyValue)
            ▼
      VaultKeyValueTemplate
            ▼
      VaultKeyValueAdapter + VaultConverter
            │  entity ↔ SecretDocument ↔ JSON/Map
            ▼
      VaultOperations / VaultTemplate
            │  keyspace/id, KV mount/version
            ▼
      HTTPS → Vault Server: KV v1/v2
            ▲
       Vault token + ACL policy
```

| Lớp/annotation | Thuộc tầng | Trách nhiệm |
| --- | --- | --- |
| `CrudRepository`, `RevisionRepository`, `@Id`, `@Version` | Spring Data Commons | Hợp đồng repository, định danh, revision và optimistic locking |
| `KeyValueTemplate`, KeyValue repository support | Spring Data KeyValue | Hạ tầng repository cho key/value store |
| `@Secret`, `VaultRepositoryFactory`, `VaultKeyValueTemplate` | Spring Vault Core | Định nghĩa mount/keyspace và nối Spring Data với Vault |
| `VaultConverter`, `SecretDocument`, `VaultMappingContext` | Spring Vault Core + Spring Data | Mapping dữ liệu Java sang document |
| `VaultTemplate`, `SessionManager` | Spring Vault Core | Giao tiếp Vault HTTP, dùng token theo workload |
| Vault auth mount/policy và KV v1/v2 | Vault Server | Xác thực, cấp quyền, versioning và lưu secret |

`VaultKeyValueTemplate` **khác `VaultTemplate`**: tên trước là adapter Spring Data KeyValue; tên sau là API chung để truy cập Vault. Khi nhìn thấy lỗi thiếu bean `vaultKeyValueTemplate`, phải kiểm tra cấu hình repository và `spring-data-keyvalue`, không chỉ kết luận thiếu HTTP client.

## 4. Entity, keyspace và repository interface

### 4.1. Định nghĩa entity theo một KV mount cụ thể

Ví dụ service `orders-api` cần lưu cấu hình cho từng tenant. Mỗi đối tượng dùng định danh `id` và một document dưới keyspace `order-settings` tại KV mount `secret`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.vault.repository.mapping.Secret;

@Secret(value = "order-settings", backend = "secret")
public class OrderSettings {
    @Id
    private String id;

    @Version
    private Long version;

    private String apiBaseUrl;
    private Integer retryLimit;

    public OrderSettings() {
    }

    public OrderSettings(String id, String apiBaseUrl, Integer retryLimit) {
        this.id = id;
        this.apiBaseUrl = apiBaseUrl;
        this.retryLimit = retryLimit;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public Long getVersion() { return version; }
    public void setVersion(Long version) { this.version = version; }

    public String getApiBaseUrl() { return apiBaseUrl; }
    public void setApiBaseUrl(String apiBaseUrl) { this.apiBaseUrl = apiBaseUrl; }

    public Integer getRetryLimit() { return retryLimit; }
    public void setRetryLimit(Integer retryLimit) { this.retryLimit = retryLimit; }
}
```

**Ý nghĩa metadata:**

- `@Secret(value = "order-settings")` xác định **keyspace**; `backend = "secret"` xác định **KV secrets engine mount**, không phải path đầy đủ.
- `@Id` yêu cầu khóa định danh **`String`**. Với `id = "tenant-a"`, key logic là `order-settings/tenant-a` dưới mount `secret`.
- `@Version Long version` cung cấp cơ chế optimistic locking khi mount là KV v2. Version thuộc metadata KV; không tự chọn một version khi tạo mới.
- `@Secret` có thêm thuộc tính `engine` từ dòng 4.1 làm alias cho `backend`; ở ví dụ dùng `backend` để tương thích với code đã có.

**Không ghép path thủ công thành `secret/data/order-settings/tenant-a` trong trường `id`:** adapter Spring Vault định tuyến theo mount/version. Định danh đến từ input người dùng cần được giới hạn ký tự, độ dài, dấu gạch chéo và các segment đáng ngờ; không biến một ID thành đường dẫn bất kỳ.

### 4.2. Interface repository và cấu hình scanning

```java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface OrderSettingsRepository
        extends CrudRepository<OrderSettings, String> {

    List<OrderSettings> findByIdStartsWith(String prefix);
}
```

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.repository.configuration.EnableVaultRepositories;

@Configuration(proxyBeanMethods = false)
@EnableVaultRepositories(basePackageClasses = OrderSettingsRepository.class)
class VaultRepositoryConfig {
    // Phải có bean VaultTemplate tên "vaultTemplate" từ cấu hình hạ tầng
    // và phải có session manager / VaultEndpoint / TLS phù hợp.
}
```

`@EnableVaultRepositories` chọn package chứa repository để Spring tạo proxy. Trong ứng dụng có nhiều repository khác loại, **không quét tràn toàn bộ package** rồi hy vọng Spring phân biệt mọi interface. Sử dụng `basePackageClasses`/`basePackages` rõ ràng; nếu dùng nhiều `VaultTemplate`, xem `vaultTemplateRef`/`keyValueTemplateRef` trong Javadoc.

**Điều kiện ẩn mà ví dụ không được bỏ qua:** ứng dụng phải có bean `VaultTemplate` (mặc định tên `vaultTemplate`). Chỉ thêm dependency và annotation không tự tạo endpoint, TLS, xác thực workload, Vault role hoặc policy. Có thể cấu hình `VaultTemplate` thủ công hay dùng cơ chế hạ tầng phù hợp với Spring Boot/Spring Cloud đang triển khai.

### 4.3. CRUD thực tế

```java
import java.util.Optional;

public final class OrderSettingsService {
    private final OrderSettingsRepository repository;

    public OrderSettingsService(OrderSettingsRepository repository) {
        this.repository = repository;
    }

    public OrderSettings createOrUpdate(String tenantId, String url, int retries) {
        OrderSettings value = repository.findById(tenantId)
            .orElseGet(() -> new OrderSettings(tenantId, url, retries));

        value.setApiBaseUrl(url);
        value.setRetryLimit(retries);
        return repository.save(value);
    }

    public Optional<OrderSettings> find(String tenantId) {
        return repository.findById(tenantId);
    }

    public void delete(String tenantId) {
        repository.deleteById(tenantId);
    }
}
```

Đoạn trên minh họa CRUD nhưng **không phải upsert an toàn nếu nhiều luồng cùng tạo mới**. Với KV v2, `@Version` tạo CAS khi update, nhưng hai request tạo cùng ID có thể đua nhau; cần test xung đột hoặc chủ động thiết kế thao tác tạo. Thêm validation cho `tenantId`, URL và retry limit trước khi gọi repository; không đưa đối tượng chứa plaintext secret vào log.

## 5. Repository không có query engine như database

HashiCorp Vault KV không có SQL index hay công cụ tìm kiếm theo trường. Query derivation của Vault repository chỉ áp dụng predicate trên **ID**. Ví dụ hợp lệ:

```java
List<OrderSettings> findByIdStartsWith(String prefix);
List<OrderSettings> findByIdBetween(String from, String to);
```

Ví dụ **không nên mong đợi Vault thực thi thành truy vấn theo dữ liệu**:

```java
// Không phải truy vấn được Vault tối ưu theo field.
List<OrderSettings> findByRetryLimitGreaterThan(int limit);
```

Các phương thức như `count()`, `findAll()`, query ID, sorting/paging có thể cần **list** key và/hoặc **fetch** nhiều secret; kết quả được lọc, phân trang hoặc sắp xếp ở phía client. Do đó chi phí tăng theo **số secret trong keyspace**, không theo một index server-side.

| Tính năng | Được hỗ trợ theo tài liệu | Giới hạn |
| --- | --- | --- |
| `findById(String)` | Có | Đọc một path cụ thể, phụ thuộc quyền `read` |
| `findByIdStartsWith(...)`, `findByIdRegex(...)` | Có, trên `@Id` | Phải liệt kê ID/path; không phải search index |
| `findByRetryLimitGreaterThan(...)` | **Không** là predicate Vault repository được hỗ trợ | Vault KV không đánh index field này |
| `count()`, `findAll()` | Có | Cần quyền liệt kê và có thể tốn request |
| Sorting / paging | Có ở tầng Spring Data | Sorting/paging được xử lý phía client; không có `ORDER BY` phía Vault |
| `@Version` | Có với KV v2 | Dùng KV CAS, không thay cho transaction nhiều document |

Từ Spring Data 3.x, `PagingAndSortingRepository` **không còn kế thừa `CrudRepository`**. Nếu muốn cả CRUD và paging/sorting, khai báo cả hai:

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.PagingAndSortingRepository;

public interface PageableOrderSettingsRepository
    extends CrudRepository<OrderSettings, String>,
            PagingAndSortingRepository<OrderSettings, String> {
}
```

Hãy đánh giá khối lượng dữ liệu. Repository phù hợp khi keyspace nhỏ hoặc truy cập theo ID; nếu cần tìm kiếm theo field, join, filter liên tục, phân trang dữ liệu rất lớn, nên chọn datastore chuyên biệt và dùng Vault để giữ credentials/secrets của datastore đó.

Nguồn: [Spring Vault – Queries and Query Methods](https://docs.spring.io/spring-vault/reference/vault/vault-repositories.html), [Spring Data – Repository Interfaces](https://docs.spring.io/spring-data/keyvalue/reference/repositories/definition.html).

## 6. KV v2, `@Version` và xử lý cạnh tranh bằng CAS

KV v2 lưu phiên bản của một secret. Khi entity có `@Version`, Spring Vault truyền phiên bản mong đợi vào thuộc tính **`cas` (check-and-set)** khi ghi. Nếu bản đang lưu đã thay đổi, Spring Data có thể phát `OptimisticLockingFailureException` và không ghi đè thay đổi của request đến trước.

Giả sử cả A và B cùng đọc `order-settings/tenant-a` ở version 8:

```text
Reader A ─ read v8 ─ modify retryLimit=4 ─ save(CAS v8) ─ OK, sinh v9
Reader B ─ read v8 ─ modify retryLimit=9 ─ save(CAS v8) ─ FAIL
                                            ↑
                          OptimisticLockingFailureException
```

**Ví dụ mã nghiệp vụ:**

```java
import org.springframework.dao.OptimisticLockingFailureException;

void updateRetryLimit(OrderSettingsRepository repository,
                      String id, int retryLimit) {

    OrderSettings original = repository.findById(id).orElseThrow();
    original.setRetryLimit(retryLimit);

    try {
        repository.save(original);
    } catch (OptimisticLockingFailureException conflict) {
        // Caller quyết định đọc lại và merge / báo xung đột.
        // Không ghi log toàn bộ entity nếu chứa dữ liệu nhạy cảm.
        throw conflict;
    }
}
```

**Lưu ý:** CAS chỉ cho một secret KV v2, không tạo transaction đa secret. Không xử lý conflict bằng cách đọc lại rồi **ghi đè mù** trong vòng lặp vô hạn; áp dụng giới hạn số lần, kiểm tra thay đổi của dữ liệu và quyết định merge có chủ đích.

### Xóa trên KV v2 không đồng nghĩa destroy

Theo tài liệu, `CrudRepository.delete(...)` gọi thao tác **DELETE** của versioned KV; giá trị bị xóa logic (soft delete), **không bị destroy vĩnh viễn**. Có thể khôi phục nếu phiên bản chưa bị destroy và policy cho phép. Xóa theo ID và xóa theo entity có phiên bản có phạm vi khác nhau, cần đọc đúng semantics của API.

Khi thực sự cần thao tác metadata, xóa version cụ thể, undelete hoặc **destroy** dữ liệu không thể khôi phục, dùng API versioned KV thích hợp (ví dụ `VaultVersionedKeyValueOperations`), kiểm soát role và policy riêng. Đừng dùng repository `deleteById` như một cơ chế “xóa dữ liệu vĩnh viễn” theo yêu cầu lưu trữ hay tuân thủ.

### RevisionRepository

Vault repository có thể đọc lại các revision của KV v2 bằng Spring Data `RevisionRepository`; ID bắt buộc là `String`, kiểu revision là `Integer`:

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.history.RevisionRepository;

public interface VersionedOrderSettingsRepository
    extends CrudRepository<OrderSettings, String>,
            RevisionRepository<OrderSettings, String, Integer> {
}
```

```java
var history = repository.findRevisions("tenant-a");
// Mỗi revision chứa metadata phiên bản và nội dung được phép đọc.
// Chỉ gọi khi policy cho phép đọc version/metadata tương ứng.
```

Revision không thay thế audit log hoặc event stream: secret version có thể bị xóa/destroy, và Vault policy quyết định được xem bản nào. Không phơi bày lịch sử plaintext secret cho người dùng cuối.

## 7. Mapping JSON và `VaultCustomConversions`

Tầng repository có thêm phép chuyển đổi:

```text
Java entity + @Secret/@Id/@Version
                 │
                 ▼
      VaultMappingContext / VaultConverter
                 │
       SecretDocument (Map / nested types)
                 │
                 ▼
       VaultResponse / Jackson JSON
                 │
                 ▼
         Vault KV v1/v2 HTTP
```

Mặc định, `VaultConverter` chuyển simple types, nested object, list và map. Document có thể mang trường **`_class`** để nhận diện kiểu domain, nhất là với kiểu trừu tượng/polymorphic. `@Id` dùng làm path key và phải là `String`; các field khác được ánh xạ vào dữ liệu lưu trong Vault.

Ví dụ document rút gọn:

```json
{
  "_class": "com.example.orders.OrderSettings",
  "apiBaseUrl": "https://orders.internal.example",
  "retryLimit": 5
}
```

Đoạn JSON minh họa **phần data** lưu bên trong KV, không phải toàn bộ HTTP envelope của KV v2 (có thêm metadata/version). Field `_class` có thể làm lộ tên package/kiểu của ứng dụng; đừng giả định dữ liệu Vault không chứa metadata ứng dụng. Hãy kiểm thử mapping trước khi đổi tên package/class hoặc chia sẻ secret giữa nhiều service.

**Một rủi ro quan trọng:** theo tài liệu Spring Vault, ghi entity qua repository có thể **thay thế toàn bộ document**. Các trường được ghi thủ công bởi ứng dụng khác nhưng không thuộc entity hiện tại có thể mất khi `save`. Vì thế:

1. Mỗi keyspace/secret nên có một chủ sở hữu schema rõ ràng.
2. Cần hợp đồng migration khi thêm/bỏ/đổi tên field.
3. Không dùng entity “chỉ chứa một trường muốn sửa” để save đè lên secret có nhiều trường không quản lý.
4. Với kiểu đặc biệt như `LocalDate`/value object, có thể đăng ký converter riêng qua `VaultCustomConversions`; kiểm tra cả chiều đọc và ghi.
5. Đặt validation trước khi save; tránh ghi các field chứa token tạm, private key hoặc object runtime không dự định persist.

**Spring Vault 4.x và Jackson:** JSON transport của Framework 7 ưu tiên Jackson 3 nếu có; Spring Data mapping sử dụng `VaultConverter` trên tài liệu trung gian. Không nhầm custom Jackson serializer với `VaultCustomConversions`: chúng tùy biến ở hai tầng khác nhau. Khi nâng từ Vault 3.x, kiểm tra dependency Jackson 2/3, converter và POJO thực tế.

Nguồn: [Spring Vault – Object to Vault JSON Mapping](https://docs.spring.io/spring-vault/reference/vault/vault-repositories.html), [VaultCustomConversions Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/repository/convert/VaultCustomConversions.html).

## 8. Chính sách Vault, mount discovery và quyền truy cập

Spring Vault repositories xác định mount bằng endpoint `sys/internal/ui/mounts/...`, sau đó thao tác KV theo version được phát hiện. Vì vậy lỗi repository có thể xảy ra **dù một lời gọi `vault.read(...)` thủ công đến path có quyền thành công**.

Giả sử `@Secret(value = "order-settings", backend = "secret")` và KV v2. Policy minh họa cho service có quyền CRUD trên các document của keyspace:

```hcl
# KV v2 secret payload: read/create/update/delete theo nhiệm vụ
path "secret/data/order-settings/*" {
  capabilities = ["create", "read", "update", "delete"]
}

# Liệt kê ID của keyspace, cần cho findAll/count/query theo prefix.
path "secret/metadata/order-settings" {
  capabilities = ["list"]
}

# Có thể cần list/read metadata dưới prefix, tùy thao tác.
path "secret/metadata/order-settings/*" {
  capabilities = ["read", "list"]
}
```

Đây là **policy minh họa**, phải thu hẹp tiếp theo thực tế; không dùng nếu service chỉ cần đọc. Vault ACL cần phù hợp endpoint mount discovery do Spring Vault gọi; hãy thử với **token workload thực tế**, không giải quyết bằng quyền `sudo` hoặc wildcard `sys/*` một cách tùy tiện.

| Thao tác | Quyền cần đối chiếu |
| --- | --- |
| `findById` | `read` trên path `secret/data/order-settings/{id}` |
| `save` | `create` hoặc `update` tùy tình huống; KV v2 có CAS |
| `deleteById` | Quyền xóa phiên bản hiện hành trên endpoint phù hợp |
| `count` / `findAll` / query theo ID | `list` trên `secret/metadata/order-settings` và `read` khi cần load entity |
| `findRevisions` | Quyền đọc metadata và versioned data tương ứng |
| Detect KV mount | Khả năng sử dụng `sys/internal/ui/mounts/...` cho mount đó; kiểm tra response thực |

Trên KV v1, các API path/policy khác KV v2: không tự ghép `data/` và `metadata/` cho mount v1. Spring Vault repository phát hiện version của mount ở runtime, nhưng điều đó yêu cầu Vault trả đủ thông tin và token có quyền phù hợp.

**Về bảo mật:** repository không thay `SessionManager` và cloud/workload authentication. Kubernetes JWT, AWS IAM, GCP IAM hoặc AppRole chỉ là cách xin Vault token; **Vault policy** mới quyết định keyspace được đọc, ghi hoặc liệt kê. Token TTL/lease expiry và rotation của credential động vẫn phải được quản lý độc lập.

## 9. Những giới hạn cần cân nhắc trước khi chọn repository

- **Hiệu năng:** `findAll`, query prefix, paging/sorting có thể cần nhiều request hoặc liệt kê nhiều ID. Đừng dùng KV repository làm kho tìm kiếm theo trường hoặc danh sách hàng triệu entity.
- **Consistency:** KV v2 CAS bảo vệ **một secret** khi ghi, không bảo vệ một transaction trên nhiều entity.
- **Xóa:** KV v2 `delete` là soft delete; chính sách lifecycle/delete/destroy phải được thiết kế rõ.
- **Mapping:** một lần `save` có thể thay toàn bộ document; schema sharing cần phối hợp.
- **Reactive:** Vault repository truyền thống dựa trên Spring Data KeyValue đồng bộ. Với ứng dụng WebFlux non-blocking, nên cân nhắc `ReactiveVaultOperations` cho tác vụ trực tiếp; không gọi CRUD repository blocking trên event loop.
- **Phạm vi:** repository chỉ làm việc với **KV secrets**. Transit, PKI, token/lease sử dụng API domain của Spring Vault Core.
- **Phân quyền:** list toàn keyspace là quyền khác với chỉ read đúng một ID; cấp quyền riêng theo nhu cầu, không cấp rộng để “repository chạy được”.

Khi ứng dụng chỉ đọc vài key đã biết ở startup và có thể dùng Spring Boot Config Data, Spring Cloud Vault có thể phù hợp hơn. Khi ứng dụng cần chủ động đọc một secret KV hoặc gọi Transit/PKI, `VaultOperations` cho phép kiểm soát path và lỗi rõ hơn mà không phải mang theo Spring Data.

## 10. Kiểm tra dependency tree và xử lý lỗi khởi tạo

### Maven

```bash
mvn -version
mvn help:effective-pom
mvn dependency:tree
```

Trong kết quả, xác nhận các artifact `spring-vault-core`, `spring-data-keyvalue`, `spring-data-commons`, `spring-core`, `spring-context`, `spring-web` và mapper JSON. `mvn help:effective-pom` giúp thấy dependency management sau import BOM; phải xem **runtime** dependency để phát hiện version bị override.

### Gradle

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-vault-core
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-data-keyvalue
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-data-commons
./gradlew dependencyInsight --configuration runtimeClasspath --dependency jackson-databind
```

Trên Windows dùng `gradlew.bat`. Nếu app đang ở Spring Boot 3.x/Spring Framework 6.x, không nâng riêng `spring-vault-core` lên 4.1 chỉ vì cần repository; giữ đúng thế hệ tương thích rồi lập kế hoạch nâng BOM đồng bộ.

| Triệu chứng | Tầng cần kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| `NoClassDefFoundError` cho Spring Data KeyValue/Commons | Dependency | Thêm `spring-data-keyvalue` và kiểm tra Commons transitively |
| `NoSuchMethodError` trong Spring Data / Spring Core | Lệch BOM hoặc override | Đồng bộ Spring Data train với Framework/Boot/Vault |
| Không tạo bean repository | Config scanning / annotation | `@EnableVaultRepositories`, package scan, interface, bean `vaultTemplate` |
| Không có bean `vaultKeyValueTemplate` | Spring Data Vault repository infrastructure | Kiểm tra dependency KeyValue và bean template/adapter |
| `403` ở `sys/internal/ui/mounts/...` | Mount discovery / policy | Kiểm tra token được quyền thao tác trên mount; không cấp `sys/*` rộng |
| `403` khi `findAll` nhưng `findById` thành công | Quyền `list` metadata | Bổ sung quyền **hẹp** cho keyspace cần list |
| `404` hoặc không đọc ra entity | KV v1/v2, keyspace/id, mount | Kiểm tra `@Secret`, ID và path được ghi thực tế |
| `OptimisticLockingFailureException` | CAS KV v2 | Đọc lại, merge có chủ đích hoặc trả conflict |
| `save` làm mất field lạ | Whole-document mapping | Quản lý schema; tránh ghi partial entity |
| `deleteById` vẫn thấy version trong lịch sử | KV v2 soft delete | Phân biệt delete, undelete và destroy theo policy |
| Query `findBySomeField` không hoạt động | Giới hạn query derivation | Chỉ query trên `@Id` hoặc dùng datastore có index |

## 11. Kiểm thử tích hợp: xác minh dependency và semantics

Một bài test repository hiệu quả cần chạy trên **Vault test instance** có mount KV v2 và token/policy gần giống production. Testcontainers Vault có thể hỗ trợ khởi tạo môi trường khi dự án đã có hạ tầng chạy container; `testcontainers-vault` chỉ nên nằm trong **test scope**. Unit test mock repository hữu ích để kiểm tra business logic, nhưng không xác minh KV mount discovery, ACL, versioning hoặc JSON mapping thật.

**Kịch bản nên chạy:**

1. Khởi động Spring context và xác nhận bean `OrderSettingsRepository` được tạo từ `@EnableVaultRepositories` với đúng `VaultTemplate`.
2. `save` một entity, đọc lại `findById` và xác minh path/keyspace cùng giá trị field được map.
3. Tạo hai bản đọc cùng version rồi update lần lượt; lần ghi sau phải nhận `OptimisticLockingFailureException` nếu sử dụng `@Version` trên KV v2.
4. Chạy `findByIdStartsWith`, `count` và `findAll` khi token có quyền `list`; kiểm tra trường hợp token thiếu quyền list.
5. Thử `deleteById`, kiểm tra soft delete và khả năng đọc revision theo policy; không khẳng định dữ liệu bị destroy.
6. Thử mapping nested value và một field không được model hóa, xác định hành vi khi repository save lại document.
7. Kiểm tra login theo workload, token hết hạn/được làm mới và xử lý `403` trên path ngoài phạm vi.
8. Xác nhận log/trace/exception không chứa plaintext secret, password hoặc Vault token.

Ví dụ JUnit 5 chỉ minh họa **assertion sau khi test fixture đã dựng context/Vault**:

```java
@Test
void storesAndReadsEntity() {
    OrderSettings original =
        new OrderSettings("test-tenant", "https://api.test.example", 2);

    repository.save(original);

    OrderSettings loaded =
        repository.findById("test-tenant").orElseThrow();

    assertEquals("https://api.test.example", loaded.getApiBaseUrl());
    assertEquals(2, loaded.getRetryLimit());
}
```

Ở đây `repository` là bean đã inject, `@Test` và `assertEquals` đến từ JUnit 5. Cần test setup riêng tạo Vault container, mount KV v2, role/policy, `VaultTemplate` và dọn dữ liệu sau test. Đừng hard-code root token vào fixture được commit; các thông tin test nhạy cảm phải có vòng đời riêng.

## 12. Checklist khi đưa Spring Data Vault repository vào dự án

- [ ] Đã xác định nghiệp vụ thật sự cần abstraction repository thay vì `VaultTemplate` hoặc Spring Cloud Vault Config Data.
- [ ] Có `spring-vault-core` cùng `spring-data-keyvalue`; `spring-data-commons` và JSON mapper hiện diện trên runtime classpath.
- [ ] Spring Framework, Spring Data BOM và Spring Vault cùng **thế hệ tương thích**; không có override tùy tiện.
- [ ] Entity có `@Secret` đúng mount/keyspace, `@Id String` hợp lệ, và `@Version` khi cần CAS trên KV v2.
- [ ] `@EnableVaultRepositories` quét đúng package, dùng đúng `VaultTemplate` và không cạnh tranh với repository loại khác.
- [ ] Vault policy cho **read/write/list** theo tính năng, có khả năng mount discovery, không cấp quyền rộng vô cớ.
- [ ] Query chỉ theo ID; paging/sorting được kiểm tra chi phí khi keyspace tăng.
- [ ] Hiểu `save` có thể thay toàn document; KV v2 `delete` là soft delete; destroy dùng API và policy khác.
- [ ] Tồn tại integration test cho mapping, CAS, quyền ACL và lỗi khi token hết hạn.
- [ ] Không log entity chứa secret, token, JSON body hoặc dữ liệu nhạy cảm.

**Ghi nhớ:** `spring-vault-core` cung cấp adapter Vault; **Spring Data KeyValue + Commons** cung cấp nền repository; **Jackson** chuyển JSON; **VaultTemplate/SessionManager** thực hiện kết nối và dùng token; **Vault server/policy** quyết định quyền và tính đúng đắn của KV. Repository giúp giảm mã CRUD nhưng vẫn giữ toàn bộ giới hạn thực tế của Vault KV.

### Tài liệu chính thức

1. [Spring Vault 4.1 – Vault Repositories](https://docs.spring.io/spring-vault/reference/vault/vault-repositories.html)
2. [Spring Vault 4.1 – Dependencies](https://docs.spring.io/spring-vault/reference/introduction/dependencies.html)
3. [Spring Vault – EnableVaultRepositories Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/repository/configuration/EnableVaultRepositories.html)
4. [Spring Vault – Secret annotation Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/repository/mapping/Secret.html)
5. [Spring Vault – VaultKeyValueTemplate Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/repository/core/VaultKeyValueTemplate.html)
6. [Spring Vault – VaultCustomConversions Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/repository/convert/VaultCustomConversions.html)
7. [Spring Data KeyValue – Dependencies](https://docs.spring.io/spring-data/keyvalue/reference/data-commons/dependencies.html)
8. [Spring Data KeyValue – Repository Interfaces](https://docs.spring.io/spring-data/keyvalue/reference/repositories/definition.html)
9. [Spring Data – Working with Repositories](https://docs.spring.io/spring-data/keyvalue/reference/data-commons/repositories.html)
10. [HashiCorp Vault – KV secrets engine v2](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2)
