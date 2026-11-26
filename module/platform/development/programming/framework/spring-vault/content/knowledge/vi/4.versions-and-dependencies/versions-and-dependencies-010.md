# Đọc API, release notes và tài liệu theo đúng dòng đang dùng

**SPRING_VAULT** giúp ứng dụng Java truy cập HashiCorp Vault qua `VaultTemplate`/`VaultOperations`, xác thực theo workload và chính sách phân quyền, xử lý KV secrets, vòng đời token/lease, Transit encryption, PKI, lỗi và kiểm thử tích hợp. Nhưng khi tìm một ví dụ trên mạng, một đoạn Java có vẻ hợp lý **có thể không tồn tại trong phiên bản Spring Vault mà ứng dụng đang chạy**. Ngược lại, một hướng dẫn cũ có thể khuyên dùng một constructor đã `@Deprecated` hoặc một thư viện cloud SDK không đúng thế hệ.

**Chương: Phiên bản và phụ thuộc.** Bài học này trình bày một quy trình có thể kiểm chứng để **đọc API, release notes và tài liệu Spring Vault theo đúng dòng đang dùng**. Không dựa vào phỏng đoán từ số phiên bản của Spring Boot hoặc Spring Cloud; trước hết phải xác định **artifact thực sự được resolve**, sau đó mở đúng Reference, Javadoc, release tag, changelog và advisory.

Sau khi học, bạn có thể:

1. Xác định phiên bản `spring-vault-core` thực tế trong Maven/Gradle, kể cả khi được kéo bởi Spring Cloud Vault starter.
2. Chọn Reference/Javadoc cho dòng 3.x, 4.0 hoặc 4.1 đúng với classpath, nhận diện `Since`, `Deprecated` và chữ ký API.
3. Đọc release notes theo **thứ tự thay đổi**: tính năng, breaking change, deprecated/removal, dependency upgrade, bug fix, bảo mật.
4. Phân biệt tài liệu **Spring Vault Core**, **Spring Cloud Vault Config**, **Spring Boot**, **Spring Cloud release train** và tài liệu **HashiCorp Vault Server**.
5. Đối chiếu một ví dụ KV/Auth/Transit/PKI với Vault role, policy, token/lease và API HTTP server trước khi đưa vào production.

> **Thời điểm đối chiếu: 25/11/2026.** Spring đã công bố **Spring Vault 4.0.5 và 4.1.2** ngày 19/11/2026; hai bản vá này sửa **CVE-2026-41698**. Bài dùng nhánh **4.1.x** làm ví dụ nhưng vẫn trình bày cách tra nhánh **3.2.x** và **4.0.x**. “Mới nhất”, nhãn “current” và nội dung redirect của website **có thể đổi sau ngày này**; không thay thế cho việc xác nhận phiên bản tại thời điểm build và deploy.

## 1. Bốn loại phiên bản thường bị nhầm

Trong một hệ thống Spring Boot + Spring Cloud Vault, có thể gặp đồng thời các con số sau:

| Thành phần | Ví dụ ở mốc bài viết | Nó quyết định điều gì? |
| --- | --- | --- |
| **Spring Boot** | `4.2.0` | Quản lý nền Framework, JSON, HTTP, lifecycle và auto-configuration của Boot |
| **Spring Cloud release train** | `2026.0.0` | BOM phối hợp nhiều dự án Cloud với một dòng Boot tương thích |
| **Spring Cloud Vault Config** | `5.1.0` | Tích hợp Vault với `Environment`/Config Data và cấu hình qua `spring.cloud.vault.*` |
| **Spring Vault Core** | `4.1.2` | Chứa `VaultTemplate`, `VaultClient`, KV/Transit/PKI, authentication và quản lý session/lease |
| **HashiCorp Vault Server** | Version do đội vận hành triển khai | Quyết định API/secret engines, mount, policy, auth role và các khả năng phía server |

**Những con số này không phải một bộ “tăng cùng nhau”.** Thông báo Spring Cloud **2026.0.0** mô tả Spring Cloud Vault **5.1.0**, và ghi dự án Cloud Vault đã nâng lên **Spring Vault 4.1.0**. Vì vậy tên release train `2026.0.0` hoặc starter `5.1.0` **không chứng minh** runtime Core đã được vá lên `4.1.2`. Phải kiểm tra dependency tree/lockfile. Tương tự, tài liệu Vault Server có thể mô tả endpoint mới mà thư viện Core cũ chưa có API Java thuận tiện.

```text
spring-boot-dependencies:4.2.0
                │
spring-cloud-dependencies:2026.0.0
                │
spring-cloud-starter-vault-config
                │
        spring-cloud-vault-config:5.1.x
                │
         spring-vault-core:4.1.x      ◄─ kiểm tra PATCH thực sự
                │
         Vault Server /v1/...        ◄─ kiểm tra engine, mount, role, policy
```

Đồ thị chỉ mô tả **quan hệ khái niệm**, không phải bản trích tree của một project cụ thể. Phiên bản được chọn có thể thay đổi bởi BOM, dependency management, constraint, `exclude` hoặc lockfile.

Nguồn: [Spring Cloud 2026.0.0 GA](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/), [Spring Cloud Vault Reference](https://docs.spring.io/spring-cloud-vault/reference/), [Spring Vault Project](https://spring.io/projects/spring-vault/).

## 2. Bắt đầu từ phiên bản thực tế trong ứng dụng

### 2.1. Maven: xem cái gì được resolve, không chỉ đọc POM

```bash
# Ghi nhận JDK và Maven chạy trong CI/container
mvn -version

# Nhìn parent, các BOM và dependencyManagement sau khi tổng hợp
mvn help:effective-pom

# Xem toàn bộ cây đã chọn, kể cả dependency bắc cầu
mvn dependency:tree

# Tập trung vào Core và Spring Cloud Vault
mvn dependency:tree -Dincludes=org.springframework.vault:spring-vault-core
mvn dependency:tree -Dincludes=org.springframework.cloud:spring-cloud-vault-config

# Khi muốn xem các node đã bị bỏ qua do trùng/xung đột
mvn dependency:tree -Dverbose
```

Ví dụ kết quả **giả lập**:

```text
com.example:orders-api:jar:1.0.0
\- org.springframework.cloud:spring-cloud-starter-vault-config:jar:5.1.0
   \- org.springframework.cloud:spring-cloud-vault-config:jar:5.1.0
      \- org.springframework.vault:spring-vault-core:jar:4.1.0
```

Đây là ví dụ minh họa cách đọc **bản Core được chọn**, **không** phải tuyên bố rằng mọi bản Spring Cloud Vault 5.1.0 luôn có chính xác các nhánh trên. Với ví dụ này, cần xem advisory và cân nhắc nâng Core lên bản vá `4.1.2` **nếu nằm trong phạm vi tương thích đã kiểm thử**.

### 2.2. Gradle: chọn đúng configuration

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-vault-core
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-cloud-vault-config
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-core
```

Trong output Gradle, `requested -> selected` chỉ bản được chọn; `dependencyInsight` giải thích tại sao (BOM, platform, conflict resolution, constraints hoặc lockfile). Với multi-module, chạy lệnh tại **module có runtime cần kiểm tra**, vì root project không nhất thiết có cùng đồ thị. Trên Windows dùng `gradlew.bat`.

**Ba điều cần ghi vào biên bản tra cứu:**

1. `org.springframework.vault:spring-vault-core`: **version cụ thể** như `4.1.2`.
2. `spring-framework`/`spring-web`, Jackson, Reactor/WebFlux, Spring Data và cloud SDK liên quan: **những bản thực sự đang trên runtime classpath**.
3. Đường vào của dependency: **khai báo trực tiếp** hay **kéo transitively** từ Cloud Vault starter/BOM/đơn vị khác.

Với `spring-vault-core`, cần phân biệt **4.1.2** với **4.1.0**, dù cả hai thuộc dòng **4.1.x**. Javadoc ở mức dòng thường đủ để hiểu chữ ký API, nhưng **patch release notes** mới chỉ ra bug fix, dependency upgrade và advisory.

## 3. Thứ tự ưu tiên nguồn khi tìm lời giải

Không có một trang nào trả lời mọi câu hỏi. Chọn nguồn theo mục đích:

| Câu hỏi đang giải quyết | Nguồn nên mở trước | Vì sao |
| --- | --- | --- |
| Cách cấu hình KV, Transit, PKI, auth, lease | **Spring Vault Reference** đúng dòng Core | Giải thích khái niệm, cấu hình, ví dụ và phạm vi API |
| Method/constructor/parameter có tồn tại ở bản đang chạy không? | **Javadoc** cùng dòng/patch hoặc JAR sources của đúng version | Có chữ ký Java, generic, `Since`, `Deprecated`, exception |
| Bản 4.1 thêm gì so với 4.0? | **GitHub release notes/tag**, tài liệu migration, compare giữa tags | Chỉ ra tính năng mới, sửa lỗi, nâng dependency, API bị bỏ |
| Vấn đề xảy ra sau khi cập nhật từ 4.1.1 lên 4.1.2 | **Release tag 4.1.2**, issues/commits gắn với thay đổi | Tách thay đổi patch khỏi thay đổi lớn của cả dòng 4.1 |
| `spring.config.import: "vault://"` có hợp lệ không? | **Spring Cloud Vault Reference** đúng dòng Cloud Vault | Đây là Config Data/auto-configuration, không phải `VaultTemplate` Core-only |
| Boot nào đi với Cloud train nào? | **Spring Cloud project/release train notes** + Boot documentation | Tránh ghép Cloud BOM và Boot không tương thích |
| Endpoint KV v2, Transit, PKI server thực sự nhận gì? | **HashiCorp Vault API/engine docs** + version Vault Server | Spring Java API che một phần đường dẫn và envelope HTTP |
| Có CVE cần sửa ở bản Core không? | **Spring Security Advisories** và thông báo bản vá | Điều kiện ảnh hưởng và nhánh patch khác các ghi chú tính năng |
| Nghi ngờ tài liệu chưa cập nhật/khác code | **Source code tại git tag**, Javadoc đúng artifact, test của dự án | Có thể xác minh implementation thay vì suy từ ví dụ cũ |

**Cảnh báo:** blog, câu trả lời diễn đàn hoặc snippets tìm kiếm hữu ích để định hướng nhưng có thể dùng milestone, RC, SNAPSHOT, tên lớp thuộc dòng cũ hoặc cấu hình chưa còn được hỗ trợ. Chỉ chốt hướng dẫn sau khi kiểm tra tài liệu của **version đã resolve**.

## 4. Chọn Reference và Javadoc theo đúng dòng

### 4.1. Bảng đường dẫn tài liệu đã đối chiếu

| Đang dùng | Reference theo dòng | Javadoc theo dòng | Nguồn patch release notes |
| --- | --- | --- | --- |
| **3.2.x** | [Reference 3.2 – VaultTemplate](https://docs.spring.io/spring-vault/reference/3.2/vault/imperative-template.html) | [Javadoc 3.2 – VaultTemplate](https://docs.spring.io/spring-vault/reference/3.2/api/java/org/springframework/vault/core/VaultTemplate.html) | [Spring Vault GitHub Releases](https://github.com/spring-projects/spring-vault/releases) và tag `3.2.n` đang dùng |
| **4.0.x** | [Reference 4.0 – VaultTemplate](https://docs.spring.io/spring-vault/reference/4.0/vault/imperative-template.html) | [Javadoc 4.0 – VaultTemplate](https://docs.spring.io/spring-vault/reference/4.0/api/java/org/springframework/vault/core/VaultTemplate.html) | [Release 4.0.5](https://github.com/spring-projects/spring-vault/releases/tag/4.0.5) khi xem patch đã vá |
| **4.1.x** | [Reference 4.1 – VaultTemplate](https://docs.spring.io/spring-vault/reference/4.1/vault/imperative-template.html) | [Javadoc 4.1 – VaultTemplate](https://docs.spring.io/spring-vault/reference/4.1/api/java/org/springframework/vault/core/VaultTemplate.html) | [Release 4.1.2](https://github.com/spring-projects/spring-vault/releases/tag/4.1.2) khi xem patch đã vá |

**Bài thực hành 30 giây:** mở đường Javadoc 3.2 rồi 4.0 rồi 4.1 cho cùng lớp `VaultTemplate`; đọc **Constructor Summary** và **Method Summary**. Trên 3.2, tìm `RestTemplateBuilder`; 4.0 có `RestClientBuilder`; 4.1 xuất hiện constructor nhận `VaultClient`. Bạn sẽ thấy ngay vì sao cùng một class name nhưng code mẫu từ các bài khác phiên bản **không thể copy nguyên vẹn**.

**Lưu ý đặc biệt với website:** đường URL theo dòng, ví dụ `/reference/4.1/...`, có thể được website **redirect về URL canonical** `/reference/...`. Bản hiển thị có thể theo nhánh ổn định hiện hành và dữ liệu cache ở một thời điểm khác. **Luôn đọc banner phiên bản thực tế trên trang**, không chỉ nhìn đường dẫn hoặc tiêu đề kết quả tìm kiếm. Để đối chiếu **patch cụ thể**, dùng link Reference/Javadoc trong **GitHub release tag** của patch đó và xem trang được mở có đúng bản không.

Trang `https://docs.spring.io/spring-vault/reference/` thường trỏ đến **bản hiện hành**; một ngày khác trang này có thể chuyển sang 4.2+. Do đó nó **không phải permalink** cho hành vi của mã 4.0 hoặc 3.2. Tương tự, tài liệu dưới `/reference/4.1/` vẫn có thể được cập nhật theo bản vá 4.1.x; nếu cần lý giải một lỗi chỉ có ở 4.1.0 thì phải dùng release tag/sources cho 4.1.0.

Nguồn: [Spring Vault Reference](https://docs.spring.io/spring-vault/reference/), [Spring Vault 4.1.2 release – Links](https://github.com/spring-projects/spring-vault/releases/tag/4.1.2).

### 4.2. Javadoc nên đọc theo trình tự nào?

Với một class/interface, theo thứ tự:

1. **Package + version banner:** ví dụ `org.springframework.vault.core.VaultTemplate`, và Javadoc đang thuộc Spring Vault 4.1 hay 3.2.
2. **Declaration:** class implements interface nào; code nghiệp vụ có thể phụ thuộc `VaultOperations` thay vì kiểu triển khai cụ thể không?
3. **Constructor Summary:** constructor nào tồn tại, có `Deprecated` hoặc `Since` không; tham số cần `SessionManager`, `VaultClient` hay `RestTemplateBuilder`?
4. **Method Summary:** đúng tên, overload, generic return type, nullability; `get` trả `VaultResponse`, `VaultResponseSupport<T>` hay `Mono`?
5. **Method Details:** mô tả tham số/path, exception, thread-safety và điều kiện như KV v1/v2, namespace, lease TTL.
6. **See Also/Related Types:** đi tiếp tới `VaultOperations`, `VaultKeyValueOperations`, `VaultToken`, `SessionManager` hoặc `ReactiveVaultOperations`.
7. **Since/Deprecated for removal:** `Since: 4.1` = không có ở 4.0; `Deprecated since 4.1` = vẫn có thể còn trong 4.1 nhưng khuyến nghị API thay thế; chỉ khi bị loại khỏi artifact mới là **đã xoá**.

**Không coi dấu `@Deprecated` là lỗi runtime.** Nó là tín hiệu cần lên kế hoạch migration, không phải bằng chứng app đã hỏng. **Không coi `Since: 4.1` là hỗ trợ trong 4.0** dù một trang “current” đề cập phương thức ấy.

## 5. Đọc API thực tế: ví dụ từ 3.x → 4.0 → 4.1

Các ví dụ sau thể hiện **thay đổi ở lớp khởi tạo client**, không phải thay đổi toàn bộ business API.

### 5.1. Dòng 3.x: `RestTemplateBuilder`

Javadoc 3.2 định nghĩa các constructor `VaultTemplate(RestTemplateBuilder)` và `VaultTemplate(RestTemplateBuilder, SessionManager)`. Mã ứng dụng có thể dùng:

```java
// Spring Vault 3.2.x: các biến đã được cấu hình ở tầng hạ tầng
VaultOperations vault = new VaultTemplate(restTemplateBuilder, sessionManager);
```

`restTemplateBuilder` ở đây là **`org.springframework.vault.client.RestTemplateBuilder`**, không tự đồng nhất với lớp builder từ Spring Boot. Khi chuyển từ framework cũ, đọc **import statement** cùng chữ ký.

### 5.2. Dòng 4.0: `RestClientBuilder` trên Spring Framework 7

Javadoc 4.0 có constructor `VaultTemplate(RestClientBuilder, SessionManager)`:

```java
// Spring Vault 4.0.x: RestClientBuilder và SessionManager được tạo trước
VaultOperations vault = new VaultTemplate(restClientBuilder, sessionManager);
```

Tên `RestClientBuilder` trong ví dụ thuộc package `org.springframework.vault.client`. 4.0 còn tồn tại một số đường tương thích với `RestTemplate`, nhưng **có hỗ trợ RestClient không đồng nghĩa đã có `VaultClient`**. Cần kiểm tra cả Spring Framework 7, JSON mapper, HTTP transport, các API bị loại từ version cũ.

### 5.3. Dòng 4.1: `VaultClient` và constructor mới

Javadoc 4.1 ghi constructor `VaultTemplate(VaultClient, SessionManager)` **`Since: 4.1`**:

```java
import org.springframework.vault.authentication.SessionManager;
import org.springframework.vault.client.VaultClient;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTemplate;

// Ví dụ đúng từ 4.1 trở lên: được gọi trong configuration
VaultOperations createVaultOperations(VaultClient client,
                                     SessionManager sessionManager) {
    return new VaultTemplate(client, sessionManager);
}
```

Đây là một **đoạn method**, không phải Java file tự chạy; `client` phải được cấu hình HTTPS, timeout, VaultEndpoint và các tùy biến cần thiết, còn `sessionManager` phải biết xác thực bằng workload phù hợp. Từ 4.1, các constructor dùng một số kiểu `RestTemplateBuilder`/`ClientHttpRequestFactory` cũ được đánh dấu **deprecated**, không nhất thiết bị xoá ngay.

### 5.4. Business API có thể không cần sửa

Một ví dụ đọc secret rõ mount/version:

```java
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;

VaultResponse readOrdersConfig(VaultOperations vault) {
    return vault
            .opsForKeyValue("secret", KeyValueBackend.KV_2)
            .get("orders/config");
}
```

Ở đây `secret` là **KV mount**, `orders/config` là path tương đối trong mount. Phương thức domain `opsForKeyValue(mount, KeyValueBackend.KV_2)` có thể dùng xuyên nhiều dòng đã hỗ trợ nó; **không** tự thêm `secret/data/` vào tham số `get`.

Từ 4.1 có thêm overload `opsForKeyValue(String mount)` giúp tự phát hiện KV version; nó cần tương tác với thông tin mount ở Vault server. **Đừng đổi sang overload mới chỉ để code ngắn hơn** nếu policy/mount discovery trong production chưa được kiểm thử. Khi cần phiên bản KV cụ thể, dùng `opsForVersionedKeyValue`.

**Bài học từ Javadoc:** xác minh chữ ký ở đúng version, chọn API domain nếu đáp ứng yêu cầu; chỉ đổi phần khởi tạo HTTP, converter hoặc session khi release notes/Javadoc chỉ ra.

Nguồn: [VaultTemplate Javadoc 3.2](https://docs.spring.io/spring-vault/reference/3.2/api/java/org/springframework/vault/core/VaultTemplate.html), [4.0](https://docs.spring.io/spring-vault/reference/4.0/api/java/org/springframework/vault/core/VaultTemplate.html), [4.1](https://docs.spring.io/spring-vault/reference/4.1/api/java/org/springframework/vault/core/VaultTemplate.html), [4.1.0 release](https://github.com/spring-projects/spring-vault/releases/tag/4.1.0).

## 6. Cách đọc release notes từ feature lớn đến patch nhỏ

Một trang GitHub `/releases/tag/4.1.2` có thể chứa các nhóm:

| Mục release notes | Cần trả lời câu hỏi gì? | Ví dụ ảnh hưởng tới SPRING_VAULT |
| --- | --- | --- |
| **New Features** | API/engine nào mới xuất hiện? Tên method, `Since`, khả năng bật cấu hình | Spring Vault **4.1.0** đưa vào `VaultClient`, `ManagedSecret`, `CertificateContainer` và KV version detection |
| **Breaking Changes / Removals** | Lớp, constructor, option hay dependency nào đã bị xoá/đổi hợp đồng? | **4.0.0** nâng Framework 7 và bỏ một số API đã deprecated trước đó; cần đánh giá code cũ |
| **Deprecations** | API nào còn tồn tại nhưng có hướng thay? Khi nào dự định gỡ? | Các đường custom `RestTemplate` ở 4.1 được khuyến khích chuyển sang `VaultClient` |
| **Bug Fixes** | Có lỗi thực tế nào ảnh hưởng path, auth, JSON hoặc rotation? | **4.1.2** sửa tình huống concurrent failed certificate rotations có thể ghi đè pending retry |
| **Dependency Upgrades** | Spring Framework, Data, Reactor, Jackson, Security được nâng tới bản nào? | **4.1.2** công bố Framework **7.0.11**, Reactor **2025.0.9**, Spring Data **2026.0.3**, Jackson 3 **3.1.8** |
| **Security Advisories** | CVE nào bị ảnh hưởng, fix ở patch nào, điều kiện khai thác là gì? | **CVE-2026-41698** được sửa trong **4.0.5/4.1.2** |
| **Documentation** | Tài liệu hướng dẫn nào bổ sung hoặc chỉnh sửa? | Ví dụ credential rotation hoặc thay đổi client access |

### 6.1. Đọc đúng bản nguồn và so sánh giữa hai tag

Ví dụ nâng từ `4.1.0` lên `4.1.2`:

1. Mở [tag 4.1.0](https://github.com/spring-projects/spring-vault/releases/tag/4.1.0) để hiểu **những tính năng có từ đầu dòng 4.1**.
2. Mở [tag 4.1.2](https://github.com/spring-projects/spring-vault/releases/tag/4.1.2) để xem **bug fix và dependency upgrade của patch**.
3. Khi cần giải thích thay đổi ở mức code, mở [compare 4.1.0...4.1.2](https://github.com/spring-projects/spring-vault/compare/4.1.0...4.1.2) hoặc commit/issue liên quan; phân biệt thay đổi public API với thay đổi implementation.
4. Xác minh **artifact đã resolve** là 4.1.2 và test lại, vì đọc release notes không làm `pom.xml`/lockfile tự đổi version.

**Không nên chỉ đọc mục “Features”.** Một bản patch có thể chỉ sửa lỗi bảo mật, concurrency, phụ thuộc HTTP/JSON hoặc TLS — những thứ quan trọng hơn tính năng mới đối với dịch vụ quản lý secrets.

### 6.2. Mẫu ghi chú đọc release notes cho pull request

```text
Library:     org.springframework.vault:spring-vault-core
From → To:   4.1.0 → 4.1.2
Target:      Spring Boot 4.2.x + Cloud Vault 5.1.x (nếu đang dùng starter)
Why:         Fix CVE-2026-41698 và nhận bug fixes
Public API:  Đối chiếu Javadoc 4.1 và methods đang gọi
Classpath:   Spring Framework, Jackson, Reactor, Spring Data resolved versions
Tests:       Workload auth, KV v1/v2, token/lease, Transit, PKI, TLS, 403
Evidence:    Release tag + advisory + dependency tree + integration test
Rollback:    Revert BOM/override/lockfile và artifact cùng nhau
```

Đây là mẫu minh họa; chỉ ghi “Tests: PASS” sau khi CI/test thực sự hoàn thành. Nếu gặp lỗi sau khi nâng, trước tiên so sánh **version thực tế, API delta và thay đổi cấu hình**, thay vì đổ lỗi ngay cho Vault Server.

Nguồn: [Release 4.1.0](https://github.com/spring-projects/spring-vault/releases/tag/4.1.0), [Release 4.1.2](https://github.com/spring-projects/spring-vault/releases/tag/4.1.2), [Spring Vault 4.0.5/4.1.2 announcement](https://spring.io/blog/2026/11/19/spring-vault-4-0-5-4-1-2-available/).

## 7. Đọc advisory bảo mật tách biệt với bài hướng dẫn thông thường

Một ví dụ gần ngày viết là **CVE-2026-41698: Spring Vault Path Traversal via unsanitized secret path parameter**. Thông báo Spring ngày **19/11/2026** nêu các patch sửa lỗi **Spring Vault 4.0.5** và **4.1.2**. Khi đánh giá, cần:

1. Xác minh version `spring-vault-core` bằng dependency tree **ở runtime**, không dùng version starter Cloud Vault làm đại diện.
2. Đọc [advisory chính thức](https://spring.io/security/cve-2026-41698/) để xác định **affected versions** và phạm vi API/điều kiện sử dụng; không suy mọi chương trình chạy Vault đều bị khai thác giống nhau.
3. Đối chiếu bản vá phù hợp với **nhánh Framework/Boot/Cloud đang dùng**; không ghép Core 4.1 vào Spring Framework 6 chỉ để tăng số patch.
4. Rà soát **secret path từ nguồn không tin cậy**: không ghép tùy ý URL tuyệt đối, `../`, encoded traversal hoặc input dùng để chọn namespace/Vault endpoint.
5. Giữ Vault token theo **least privilege**, chỉ cấp `read`/`write` trên đúng KV/Transit/PKI path cần thiết, theo dõi lỗi 403, và dùng TLS.
6. Tạo integration test để chứng minh path ngoài keyspace bị từ chối; test không được chạy với root token như bằng chứng policy đã đúng.

**Một bản vá không thay thế thiết kế bảo mật.** Tương tự, `@Deprecated` không phải security advisory: nó thể hiện hướng tiến hóa API, còn advisory chỉ rõ lỗ hổng và nhánh fix. Cần đọc **cả hai** khi nâng dependency.

## 8. Đọc Spring Cloud Vault đúng dòng, không áp ví dụ Core một cách máy móc

**Spring Vault Core** cung cấp `VaultTemplate`, `VaultOperations`, `VaultClient` và các API token/lease. **Spring Cloud Vault Config** nạp secrets vào Spring `Environment`, cấu hình `spring.config.import` và các tùy chọn `spring.cloud.vault.*`. Hai bộ tài liệu có thể nhắc cùng một authentication method nhưng **hướng dẫn thiết lập khác nhau**.

Ví dụ **chỉ có ý nghĩa với Spring Cloud Vault starter tương thích**:

```yaml
spring:
  application:
    name: orders-api
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "https://vault.internal.example:8200"
      authentication: KUBERNETES
      kubernetes:
        role: orders-read
      kv:
        enabled: true
        backend: secret
```

Địa chỉ, role và mount chỉ minh họa. Pod cần ServiceAccount JWT, Vault Kubernetes auth mount/role và policy phù hợp. **Nếu ứng dụng chỉ thêm `spring-vault-core`, cấu hình này không tự tạo cơ chế Config Data của Cloud Vault.**

Các trang Cloud Vault theo dòng cần tra:

- [Spring Cloud Vault 5.0 – Quick Start](https://docs.spring.io/spring-cloud-vault/reference/5.0/quickstart.html) khi sử dụng **Cloud Vault 5.0.x**.
- [Spring Cloud Vault 5.1 – Quick Start](https://docs.spring.io/spring-cloud-vault/reference/5.1/quickstart.html) khi sử dụng **Cloud Vault 5.1.x**.
- [Spring Cloud Vault current](https://docs.spring.io/spring-cloud-vault/reference/) chỉ khi chủ động tra bản hiện hành **và đã kiểm tra banner**.
- [Spring Cloud releases](https://spring.io/projects/spring-cloud/) để xác định Cloud train/Boot compatibility.

**Đọc đúng tính năng:** hỏi “tại sao `spring.config.import=vault://` không load property?” thì tìm **Spring Cloud Vault Config Data**. Hỏi “constructor `VaultTemplate(VaultClient, SessionManager)` có từ khi nào?” thì tìm **Spring Vault Core Javadoc**. Hỏi “KV v2 xoá version khác destroy thế nào?” thì đối chiếu **Spring Vault versioned KV API và HashiCorp Vault KV v2 API**. Việc tìm nhầm kho tài liệu dẫn đến sửa nhầm dependency.

## 9. Một ví dụ đầy đủ: tìm đúng tài liệu cho KV, auth, Transit, PKI và lease

Giả sử dịch vụ `orders-api` đang dùng `spring-vault-core:4.0.5`, xác thực Kubernetes và lấy database credentials có lease; nhóm thấy bài viết nói có `ManagedSecret` và `CertificateContainer`.

| Điều cần làm | Nguồn đúng | Quyết định kỹ thuật |
| --- | --- | --- |
| Xác minh có `ManagedSecret` ở 4.0.5 không | Release **4.1.0** + Javadoc **4.0** và **4.1** | Đừng dùng API mới từ 4.1 trong code 4.0 |
| Đọc KV v2 bằng `VaultOperations` | Reference 4.0 về KV + `VaultKeyValueOperations` Javadoc 4.0 | Dùng overload có `KeyValueBackend.KV_2` phù hợp |
| Đăng nhập bằng Kubernetes JWT | Reference 4.0 Authentication + Vault server Kubernetes auth | Xác minh role, bound ServiceAccount, namespace, audience, TTL |
| Gia hạn token và database credential lease | Reference 4.0 Authentication/Lease lifecycle | Phân biệt **token lifecycle** và **secret lease lifecycle** |
| Mã hóa Transit bằng key đã tạo | Reference 4.0 Transit API + Vault Transit server docs | `opsForTransit` yêu cầu Vault policy trên path encrypt/decrypt |
| Phát hành chứng chỉ PKI | Reference 4.0 PKI API + Vault PKI server docs | Cấp đúng role/TTL; rotation tự động cần đánh giá API theo dòng |
| Nâng Core lên 4.1 để có managed rotation | 4.1.0 release notes + 4.1 Javadoc + compatibility | Nâng có kế hoạch, test JSON/HTTP/auth/lease/PKI, không chỉ thay version |
| Chẩn đoán 403 sau đổi phiên bản | Vault policy/auth docs + response HTTP/trace đã che secret | 403 chưa đủ chứng minh lỗi Java API |

**Chú ý với phiên bản Vault Server:** một request thuộc KV v2 đi tới endpoint `secret/data/...`, còn thao tác trong Spring domain `opsForKeyValue("secret", KV_2).get("orders/config")` nhận path tương đối `orders/config`. Đọc tài liệu Vault HTTP API mà bỏ qua tầng Spring domain dễ dẫn đến ghép `data/` hai lần.

**Chú ý với token/lease:** `SessionManager` quản lý Vault token, còn dynamic credentials có `lease_id`/TTL. Khi đọc docs của một API rotation, tìm rõ nó có làm mới **token**, **database credential**, **TLS certificate**, hay chỉ trả response. Một bean load một lần lúc startup không có nghĩa application datasource/SSL tự nhận credential mới.

## 10. Khi tài liệu chính thức mâu thuẫn hoặc ví dụ không biên dịch

Đôi khi **reference prose chưa theo kịp Javadoc** của patch hoặc dòng mới; cũng có thể website redirect sang bản khác. Dùng trình tự xác minh:

1. Đọc lại **version đang build** (ví dụ `4.1.2`) và **version banner Javadoc**.
2. Kiểm tra **import** và kiểu tham số: `RestTemplateBuilder` trong Spring Vault khác các builder cùng tên ở framework khác; AWS SDK v1 có package `com.amazonaws.*`, SDK v2 có `software.amazon.awssdk.*`.
3. So sánh overload/constructor trong Javadoc đúng dòng, nhất là `Since`/`Deprecated`.
4. Nếu Javadoc còn mơ hồ, xem **source tại release tag** cùng version, rồi tìm test hoặc commit liên quan.
5. Chạy compile hoặc integration test **ở project của bạn** để xác minh; không copy thêm SDK “cho đủ” hoặc thêm random `exclude`.
6. Ghi bằng chứng và hạn chế áp dụng: “ví dụ chỉ đúng với 4.1.2”, “yêu cầu Spring Framework 7”, “cần KV v2”, “cần quyền mount discovery”.

**Ví dụ thực tế 4.1:** Javadoc `AwsIamAuthenticationOptions` mô tả kiểu AWS SDK v2 `software.amazon.awssdk.auth.credentials.AwsCredentialsProvider`, trong khi một số đoạn hướng dẫn lâu đời còn mô tả `BasicAWSCredentials` từ AWS SDK v1. Nếu chỉ copy code theo phần văn xuôi mà không kiểm tra Javadoc **đúng artifact**, code có thể không biên dịch. Tương tự, builder GCP IAM 4.1 dùng tên `credentials(...)`; tên phương thức từ snippet cũ có thể khác. Đối với các trường hợp này **ưu tiên chữ ký API thật của version**, sau đó chọn SDK phù hợp.

**Không tự động coi mọi thay đổi source là public API:** những class trong `internal`, implementation detail, package-private hoặc test fixture có thể thay đổi dù không có thông báo breaking change. Ưu tiên interface được tài liệu bảo đảm, ví dụ `VaultOperations`, trừ khi cần extension có chủ đích.

Nguồn: [AWS IAM options Javadoc 4.1](https://docs.spring.io/spring-vault/reference/4.1/api/java/org/springframework/vault/authentication/AwsIamAuthenticationOptions.AwsIamAuthenticationOptionsBuilder.html), [GCP IAM options Javadoc 4.1](https://docs.spring.io/spring-vault/reference/4.1/api/java/org/springframework/vault/authentication/GcpIamCredentialsAuthenticationOptions.GcpIamCredentialsAuthenticationOptionsBuilder.html), [Spring Vault Authentication Methods](https://docs.spring.io/spring-vault/reference/vault/authentication.html).

## 11. Quy trình tra cứu chuẩn cho một ticket hoặc PR nâng cấp

| Bước | Thao tác | Bằng chứng phải lưu |
| --- | --- | --- |
| **1. Ghi runtime version** | Maven `dependency:tree` / Gradle `dependencyInsight`; kiểm tra JDK và Framework | Tọa độ Core, Cloud Vault, Boot, Framework và nguồn chọn version |
| **2. Chọn đúng docs line** | Reference/Javadoc **3.2**, **4.0** hoặc **4.1** | URL + version banner + ngày tra |
| **3. Xác minh API** | Constructor, import, `Since`, `Deprecated`, return type, exception | Link Javadoc class/method và phương án thay thế |
| **4. Đọc delta release** | Tag bản cũ, tag bản mới, compare commits/issues | Feature, bug fix, dependency changes, removal |
| **5. Đọc bảo mật** | Spring Advisory cho những CVE có liên quan | Affected version, fixed version, mitigation cần làm |
| **6. Kiểm tra Cloud/Boot** | Cloud train tương thích Boot; starter khác Core | BOM và runtime classpath không trộn thế hệ |
| **7. Đọc Vault Server docs** | KV version, auth role, Transit/PKI path và ACL | Engine/mount/policy/TTL được yêu cầu |
| **8. Kiểm thử** | Build/compile, test auth/KV/lease/Transit/PKI, lỗi 403/404/TLS | Kết quả CI và test thật, không phải suy đoán |
| **9. Review & ghi chú** | Ghi link nguồn theo version, không link “latest” chung chung | PR mô tả vì sao API đúng cho version đang dùng |

### Bài thực hành tự kiểm tra

Giả sử bạn nhận nhiệm vụ “sử dụng constructor `VaultTemplate(VaultClient, SessionManager)` để thay một `RestTemplateCustomizer` cũ trên dịch vụ đang dùng Spring Vault 4.0.5”:

1. Kiểm tra `spring-vault-core` đang resolve là **4.0.5**.
2. Mở [VaultTemplate Javadoc 4.0](https://docs.spring.io/spring-vault/reference/4.0/api/java/org/springframework/vault/core/VaultTemplate.html) và [Javadoc 4.1](https://docs.spring.io/spring-vault/reference/4.1/api/java/org/springframework/vault/core/VaultTemplate.html).
3. Thấy constructor nhận `VaultClient` có `Since: 4.1`; **không** thể thêm đoạn code đó vào dự án 4.0.5 mà chỉ thay import.
4. Quyết định: tạm dùng đường `RestClientBuilder` được hỗ trợ trên 4.0, hoặc lên kế hoạch nâng cả Core và các dependency cần thiết sang dòng 4.1.
5. Đọc [release notes 4.1.0](https://github.com/spring-projects/spring-vault/releases/tag/4.1.0) và [4.1.2](https://github.com/spring-projects/spring-vault/releases/tag/4.1.2), xem advisory, rồi kiểm thử Vault auth, KV, token/lease và HTTP/TLS.

**Đáp án trọng tâm:** class name giống nhau không đồng nghĩa constructor giống nhau; phải kiểm tra **Since** cùng version thực tế.

## 12. Checklist khi đọc bất kỳ ví dụ Spring Vault nào

- [ ] Tôi biết chính xác `org.springframework.vault:spring-vault-core` đang chạy version nào, từ Maven/Gradle **runtime**.
- [ ] Tôi đang đọc **Spring Vault Core** hay **Spring Cloud Vault**; Boot/Cloud BOM có tương thích không?
- [ ] Trang Reference/Javadoc đang hiển thị **đúng dòng và patch**; redirect hoặc “current” không làm tôi lạc bản?
- [ ] Tôi đã kiểm tra `Since`, `Deprecated`, overload, import và kiểu trả về của API cần dùng.
- [ ] Tôi đã đọc release notes từ bản cũ đến bản mới, bao gồm bug fix, dependency upgrade, removal và migration.
- [ ] Tôi đã đối chiếu advisory có liên quan (đặc biệt CVE-2026-41698 với những nhánh bị ảnh hưởng).
- [ ] JSON mapper, HTTP transport, Reactor/Spring Data/cloud SDK đúng thế hệ và hiện diện trên runtime classpath.
- [ ] Vault Server cung cấp engine/mount/auth role đúng; Vault policy quyền tối thiểu cho KV/Transit/PKI.
- [ ] Token TTL/lease/rotation và lỗi 401/403/404/TLS đã được kiểm thử ở phiên bản thực tế.
- [ ] PR hoặc tài liệu nội bộ ghi **version cụ thể + link nguồn + kết quả xác minh**, không chỉ link trang “latest”.

**Ghi nhớ:** một cách tra cứu đáng tin cậy bắt đầu từ **artifact đã resolve**, đi tới **Javadoc/Reference theo dòng**, đối chiếu **release tag và advisory theo patch**, rồi kết thúc bằng **kiểm thử trên Vault Server với policy thật**. Đó là cách tránh nhầm API khi xây dựng tích hợp secrets có yêu cầu bảo mật cao.

### Tài liệu tham khảo chính thức

1. [Spring Vault – Project và dòng phát hành](https://spring.io/projects/spring-vault/)
2. [Spring Vault – Reference hiện hành (nhớ kiểm tra banner)](https://docs.spring.io/spring-vault/reference/)
3. [Spring Vault 3.2 – VaultTemplate Reference](https://docs.spring.io/spring-vault/reference/3.2/vault/imperative-template.html)
4. [Spring Vault 3.2 – VaultTemplate Javadoc](https://docs.spring.io/spring-vault/reference/3.2/api/java/org/springframework/vault/core/VaultTemplate.html)
5. [Spring Vault 4.0 – VaultTemplate Javadoc](https://docs.spring.io/spring-vault/reference/4.0/api/java/org/springframework/vault/core/VaultTemplate.html)
6. [Spring Vault 4.1 – VaultTemplate Javadoc](https://docs.spring.io/spring-vault/reference/4.1/api/java/org/springframework/vault/core/VaultTemplate.html)
7. [Spring Vault 4.1.0 – Release Notes](https://github.com/spring-projects/spring-vault/releases/tag/4.1.0)
8. [Spring Vault 4.1.2 – Release Notes/Javadoc links](https://github.com/spring-projects/spring-vault/releases/tag/4.1.2)
9. [Spring Vault 4.0.5 – Release Notes](https://github.com/spring-projects/spring-vault/releases/tag/4.0.5)
10. [Spring Vault 4.0.5 và 4.1.2 – thông báo bản vá 19/11/2026](https://spring.io/blog/2026/11/19/spring-vault-4-0-5-4-1-2-available/)
11. [Spring – CVE-2026-41698 Advisory](https://spring.io/security/cve-2026-41698/)
12. [Spring Cloud Vault 5.0 – Quick Start](https://docs.spring.io/spring-cloud-vault/reference/5.0/quickstart.html)
13. [Spring Cloud Vault 5.1 – Quick Start](https://docs.spring.io/spring-cloud-vault/reference/5.1/quickstart.html)
14. [Spring Cloud 2026.0.0 GA và release train](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
15. [Spring Cloud – Release Train Compatibility](https://spring.io/projects/spring-cloud/)
16. [Maven – Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
17. [Gradle – Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
18. [HashiCorp Vault – API Documentation](https://developer.hashicorp.com/vault/api-docs)
