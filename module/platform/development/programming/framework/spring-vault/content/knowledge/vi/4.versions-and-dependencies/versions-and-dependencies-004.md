# Dependency `spring-vault-core` và các thành phần tùy chọn

Trong module **SPRING_VAULT**, ứng dụng Java sử dụng Spring Vault để truy cập HashiCorp Vault qua `VaultTemplate`, xác thực theo workload và Vault policy; các nghiệp vụ thường gặp gồm KV secrets, token/lease, Transit encryption, PKI, xử lý lỗi và kiểm thử tích hợp. **Câu hỏi về dependency** không dừng ở việc tìm một artifact để ứng dụng biên dịch được: cần biết tính năng nào đã nằm trong Core, tính năng nào cần thư viện tùy chọn, BOM nào kiểm soát phiên bản, và classpath runtime cuối cùng có đúng hay không.

**Chương:** Phiên bản và phụ thuộc. Sau bài này, bạn có thể:

1. Khai báo `org.springframework.vault:spring-vault-core` trong Maven hoặc Gradle.
2. Chỉ thêm thư viện cho JSON, reactive, Spring Data repositories, cloud workload authentication, HTTP transport, Spring Cloud Vault, giám sát và kiểm thử khi thực sự sử dụng.
3. Phân biệt **thư viện Java**, **starter/auto-configuration**, **BOM quản lý phiên bản** và **Vault secrets engine ở phía server**.
4. Phát hiện xung đột hoặc thiếu optional dependency bằng dependency tree và kiểm thử tích hợp.

> **Thời điểm đối chiếu: 25/11/2026.** Các ví dụ dùng Spring Vault **4.1.2**, một bản ổn định đã công bố ngày 19/11/2026. Dòng 4.x dựa trên Spring Framework 7 và yêu cầu Java 17 trở lên. Khi dự án đang dùng Spring Framework 6.x/Boot 3.x, phải chọn dòng Spring Vault 3.x phù hợp thay vì sao chép số phiên bản 4.1.2. Kiểm tra lại release notes và BOM trước ngày phát hành sản phẩm.

## 1. Một JAR chính, nhiều lựa chọn tích hợp

Theo hướng dẫn chính thức, artifact cốt lõi là:

```text
org.springframework.vault:spring-vault-core
```

Các API Vault thông dụng được đóng trong thư viện này: `VaultOperations`/`VaultTemplate`, `VaultKeyValueOperations`, `VaultTransitOperations`, `VaultPkiOperations`, `ClientAuthentication`, `SessionManager` và các API quản lý vòng đời token/lease. Bạn **không cần tìm thêm** các artifact như `spring-vault-kv`, `spring-vault-transit` hay `spring-vault-pki` chỉ vì muốn dùng những secrets engine tương ứng.

Một cấu hình ứng dụng có thể nhìn theo các lớp:

```text
Ứng dụng Java
  │
  ├─ spring-vault-core ────────► VaultTemplate, VaultClient, KV, Transit, PKI,
  │                              authentication, token/lease lifecycle
  │      │
  │      ├─ Jackson 3 hoặc Jackson 2   [chọn JSON mapper]
  │      ├─ spring-webflux/Reactor     [khi dùng reactive API]
  │      ├─ spring-data-keyvalue       [khi dùng Vault repositories]
  │      ├─ AWS/GCP SDK                [một số cơ chế auth theo cloud]
  │      └─ HTTP client ngoài JDK     [khi cần transport/TLS đặc biệt]
  │
  ├─ Spring Cloud Vault starter       [khi cần Config Data: vault://]
  ├─ Boot Actuator/Micrometer         [nếu cần quan sát]
  └─ Testcontainers Vault             [phạm vi test]
                 │
                 ▼
          Vault Server (HTTPS)
         KV / Transit / PKI / Auth
          + Vault ACL policies
```

**Phân biệt “optional” theo nghĩa kỹ thuật:** POM của `spring-vault-core` có thể khai báo một số dependency với cờ `optional=true`. Maven thường **không truyền** chúng đến dự án tiêu thụ chỉ vì dự án thêm Core. Vì vậy một kiểu Java thuộc thư viện tùy chọn có thể tồn tại trong API của Core nhưng không có đủ class để chạy nếu thiếu dependency tương ứng. Cũng có thành phần **độc lập** như Spring Cloud Vault starter hoặc Testcontainers Vault, không phải “module con” của artifact Spring Vault Core.

Nguồn: [Spring Vault – Dependencies](https://docs.spring.io/spring-vault/reference/introduction/dependencies.html), [Maven Central – spring-vault-core](https://central.sonatype.com/artifact/org.springframework.vault/spring-vault-core).

## 2. Bảng chọn thành phần theo nhu cầu

| Nhu cầu | Dependency nên xem xét | Bắt buộc thêm ngoài Core? | Điều kiện thực tế |
| --- | --- | --- | --- |
| KV v1/v2, `VaultTemplate`, Transit, PKI, token, lease | `spring-vault-core` | **Không** cần JAR theo engine | Vault server phải bật đúng engine, mount và policy |
| Serialize/deserialize JSON với Spring Vault 4.x | `tools.jackson.core:jackson-databind` **hoặc** Jackson 2 `com.fasterxml.jackson.core:jackson-databind` | **Có**, nếu chưa có từ ứng dụng/BOM | Ưu tiên Jackson 3 trên Framework 7 |
| `ReactiveVaultTemplate`, `ReactiveVaultClient` | `org.springframework:spring-webflux` cùng Reactor (được WebFlux kéo theo) | **Có** nếu chưa có WebFlux/Reactor | Dùng reactive HTTP client, không block event loop |
| `@EnableVaultRepositories`, `CrudRepository` cho KV | `org.springframework.data:spring-data-keyvalue` (và Commons) | **Có** | Repository phụ thuộc Spring Data và nhận diện KV mount |
| AWS IAM login vào Vault | `com.amazonaws:aws-java-sdk-core` | **Có** với `AwsIamAuthentication` theo tài liệu API | Credential nguồn AWS và Vault role/policy phải hợp lệ |
| GCP IAM Credentials login | `com.google.cloud:google-cloud-iamcredentials` | **Có** với API IAM Credentials được tài liệu mô tả | Bật IAM Credentials API và quyền ký JWT |
| HTTP transport tuỳ chọn, pooling/TLS | `org.apache.httpcomponents.client5:httpclient5`, `io.projectreactor.netty:reactor-netty` hoặc Jetty tương ứng | **Không** nếu JDK HTTP client đáp ứng | Đảm bảo lựa chọn HTTP thực sự được dùng |
| Nạp secrets thành Spring `Environment`/`vault://` | `org.springframework.cloud:spring-cloud-starter-vault-config` | **Có** nếu cần cơ chế Config Data Spring Cloud | Dùng Spring Cloud BOM tương thích với Boot |
| Quan sát sức khoẻ/metrics cho ứng dụng Boot | `org.springframework.boot:spring-boot-starter-actuator` | **Có** nếu cần Actuator | Chọn metric an toàn, không xuất plaintext secrets |
| Tích hợp test trên Vault thật trong container | `org.testcontainers:testcontainers-vault` | **Có** trong `test` scope khi dùng Testcontainers | Runtime container và policies thử nghiệm |

**Không hiểu sai bảng:** Spring Cloud Vault starter có thể **kéo theo** Spring Vault Core. Không khai báo cả starter và một Core với số phiên bản khác nhau chỉ để có thêm KV/Transit/PKI. Ngược lại, thêm Core đơn thuần **không tự kích hoạt** tính năng `spring.config.import: vault://` của Spring Cloud.

## 3. Maven: cấu hình tối thiểu có quản lý phiên bản

### 3.1. Dùng trực tiếp Spring Vault Core trong ứng dụng Spring Boot

Ví dụ POM cho dự án đã chọn **Spring Boot 4.1.3** (thuộc thế hệ Spring Framework 7), dùng Core **4.1.2** và Jackson 3. Khai báo BOM Boot bằng parent giúp thư viện nền như Jackson có số phiên bản nhất quán.

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
    <artifactId>vault-core-demo</artifactId>
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
            <groupId>tools.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <!-- Phiên bản do Spring Boot BOM quản lý -->
        </dependency>
    </dependencies>
</project>
```

Đây là **POM minh hoạ bộ dependency cho thao tác Vault Core**, chưa phải ứng dụng hoàn chỉnh: cần cấu hình bean `VaultTemplate`/`VaultOperations`, `VaultEndpoint`, TLS và phương thức xác thực workload thích hợp. Nếu bỏ parent/BOM Boot, phải chỉ rõ hoặc import quản lý phiên bản cho Jackson, Spring Framework và các dependency khác. Không sao chép một dependency thiếu `<version>` vào POM Maven không có dependency management.

Ví dụ kiểm tra nghiệp vụ KV sau khi ứng dụng đã có bean `VaultOperations`:

```java
import java.util.Map;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;

public class FeatureFlagReader {
    private final VaultOperations vault;

    public FeatureFlagReader(VaultOperations vault) {
        this.vault = vault;
    }

    public Map<String, Object> readFlags() {
        VaultResponse response = vault
            .opsForKeyValue("secret", KeyValueBackend.KV_2)
            .get("orders/feature-flags");
        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Missing feature-flags secret");
        }
        return response.getData();
    }
}
```

Ở ví dụ, `secret` là **KV mount** và `orders/feature-flags` là path **tương đối** trong mount. `opsForKeyValue(..., KV_2)` thực hiện phần đường dẫn API của KV v2; không tự thêm `secret/data/` vào tham số `get`. Ví dụ không log dữ liệu đọc được và giả định Vault policy đã cho phép đọc đúng path.

### 3.2. Không dùng Spring Boot

Với ứng dụng Spring Framework thuần, ví dụ Maven căn bản có thể khai báo phiên bản trực tiếp:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.vault</groupId>
        <artifactId>spring-vault-core</artifactId>
        <version>4.1.2</version>
    </dependency>
    <dependency>
        <groupId>tools.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <version>3.1.8</version>
    </dependency>
</dependencies>
```

Đây chỉ là **đoạn dependency**. Phiên bản Jackson là ví dụ ở mốc bài viết; cần quản lý phiên bản Spring Framework 7, Spring Web, HTTP client và các mô-đun khác bằng BOM hoặc dependency management thích hợp. Spring Vault không tự động tạo ứng dụng Spring Boot; bạn chủ động khai báo Spring context/configuration để xây `VaultTemplate` và lifecycle manager.

## 4. Gradle Kotlin DSL: hai kiểu tích hợp

### 4.1. Core-only với Gradle native BOM

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
    implementation("tools.jackson.core:jackson-databind")
}
```

`platform(...)` là cơ chế native của Gradle dùng BOM để chọn phiên bản cho những artifact do BOM quản lý; việc import BOM **không tự cài** Spring Boot runtime. Nếu dự án đã dùng Boot plugin và `io.spring.dependency-management`, hãy giữ một chính sách quản lý phiên bản nhất quán, tránh ép khác phiên bản thông qua catalog, constraints hoặc `resolutionStrategy` mà không có căn cứ.

### 4.2. Spring Cloud Vault trong ứng dụng Spring Boot

Khi ứng dụng cần nạp secret vào `Environment`/Config Data, dùng **Spring Cloud Vault**. Ví dụ chọn Boot **4.2.0** với Spring Cloud release train **2026.0.0**, tương ứng thế hệ Cloud Vault **5.1.x**:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "4.2.0"
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:4.2.0"))
    implementation(platform("org.springframework.cloud:spring-cloud-dependencies:2026.0.0"))
    implementation("org.springframework.cloud:spring-cloud-starter-vault-config")
}
```

Đây là ví dụ dependency của **ứng dụng có Spring Boot**, không phải cấu hình Vault đầy đủ. Trong `application.yml` còn cần `spring.config.import: "vault://"`, địa chỉ Vault, TLS, workload auth và role phù hợp. Ở đây **không ghi phiên bản starter**: Cloud BOM chịu trách nhiệm chọn; cũng không thêm `spring-vault-core` một lần nữa với phiên bản tuỳ ý.

Tham khảo: [Spring Cloud Vault Quick Start](https://docs.spring.io/spring-cloud-vault/reference/quickstart.html), [Spring Cloud – Release train compatibility](https://spring.io/projects/spring-cloud/).

## 5. Các dependency tùy chọn cần hiểu sâu

### 5.1. Jackson 3 / Jackson 2: hỗ trợ JSON, không phải API Vault riêng

Spring Vault 4.x **không kéo Jackson vào transitively** để ứng dụng tự chọn thế hệ JSON. Cấu hình được khuyến nghị trên Spring Framework 7 là **Jackson 3**:

```xml
<dependency>
    <groupId>tools.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
</dependency>
```

Mẫu này giả định đã có BOM quản lý phiên bản. Nếu hệ thống bắt buộc Jackson 2, cần đánh giá nhóm `com.fasterxml.jackson.core:jackson-databind` cùng các mapper/converter tương ứng; Spring Vault 4.x còn duy trì tương thích với Jackson 2. **Khi Jackson 2 và 3 cùng tồn tại, Spring Vault ưu tiên Jackson 3**, nên các custom serializer, Kotlin module và kiểu domain cần kiểm thử lại.

Lỗi thường gặp: ứng dụng có `spring-vault-core` nhưng thiếu thư viện JSON, dẫn đến lỗi chuyển đổi message khi gửi/nhận Vault response. Cũng có thể phát sinh lỗi do Spring Boot BOM quản lý Jackson 3 nhưng ứng dụng ép `jackson-databind` 2.x hoặc một plugin kéo hai dòng với custom module chưa tương thích. Xem `dependency:tree` hoặc `dependencyInsight` để kết luận.

Nguồn: [Spring Vault – Dependencies](https://docs.spring.io/spring-vault/reference/introduction/dependencies.html).

### 5.2. Reactive: `spring-webflux` và Reactor

`spring-vault-core` chứa `ReactiveVaultTemplate`/`ReactiveVaultOperations`, nhưng thực thi reactive dựa vào **Spring WebFlux/WebClient và Project Reactor**. Nếu ứng dụng đã dùng `spring-boot-starter-webflux` thì thường đã có chúng. Nếu ứng dụng chỉ cần reactive client mà không cần khởi chạy web server, có thể chỉ thêm:

```kotlin
dependencies {
    implementation("org.springframework.vault:spring-vault-core:4.1.2")
    implementation("org.springframework:spring-webflux")
    implementation("tools.jackson.core:jackson-databind")
}
```

Giả định block này nằm trong build đã import BOM Spring tương thích. `spring-webflux` kéo Reactor qua các phụ thuộc của nó; nếu dùng một transport cụ thể như Reactor Netty, bổ sung và cấu hình transport đó. Không bắt buộc chạy Spring WebFlux HTTP server để gọi Vault bằng reactive client.

`ReactiveVaultTemplate` trả về `Mono`/`Flux` và dùng một `ReactiveSessionManager` để tái sử dụng token theo vòng đời; tránh gọi `block()` trong reactive event loop. Kiểm thử cả reauthentication, timeout và cancellation, vì chỉ biên dịch thành công không xác nhận HTTP client và token supplier đã được cấu hình.

Nguồn: [Spring Vault – Reactive Infrastructure](https://docs.spring.io/spring-vault/reference/vault/reactive-template.html).

### 5.3. Spring Data repositories: `spring-data-keyvalue`

Bạn có thể thao tác KV trực tiếp qua `VaultTemplate` mà **không cần Spring Data**. Chỉ khi muốn interface kiểu `CrudRepository`, mapping entity, truy vấn theo định danh, hãy thêm `spring-data-keyvalue` (cùng `spring-data-commons`, thường đến transitively). Các lớp tích hợp Vault repository đã nằm trong Core; **không có yêu cầu cài một JAR `spring-vault-repositories` riêng**.

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.vault</groupId>
        <artifactId>spring-vault-core</artifactId>
        <version>4.1.2</version>
    </dependency>
    <dependency>
        <groupId>org.springframework.data</groupId>
        <artifactId>spring-data-keyvalue</artifactId>
        <!-- Version từ BOM Spring Data/Spring Boot tương thích -->
    </dependency>
</dependencies>
```

Sau đó kích hoạt repository bằng `@EnableVaultRepositories` và cung cấp bean `VaultTemplate`. Cơ chế repository phát hiện mount qua API `sys/internal/ui/mounts/...` nên phải thiết kế policy để nhận diện được mount; không phải cứ có quyền `read` secret là mọi thao tác repository đều hoạt động. Đối với KV v2, `CrudRepository.delete()` thực hiện xoá logic theo semantics của API versioned KV; **không tương đương destroy vĩnh viễn mọi phiên bản**.

Không xem Vault repositories như một cơ sở dữ liệu truy vấn tùy ý: KV có semantics và khả năng query hạn chế, nên khi chỉ cần vài secret hạ tầng, `VaultTemplate` đơn giản và dễ kiểm soát hơn.

Nguồn: [Spring Vault – Vault Repositories](https://docs.spring.io/spring-vault/reference/vault/vault-repositories.html).

### 5.4. Xác thực workload: SDK bổ sung chỉ cho những cơ chế cần SDK

Spring Vault Core hỗ trợ nhiều `ClientAuthentication`: AppRole, Kubernetes, JWT, token, cert, AWS, Azure, GCP... Nhưng **hỗ trợ phương thức xác thực trong Core không đồng nghĩa đã mang tất cả SDK cloud**.

| Workload/auth method | Nguồn định danh cần có | Dependency bổ sung thường cần |
| --- | --- | --- |
| Kubernetes | ServiceAccount JWT được mount vào pod, Vault Kubernetes role | Thường **không** cần Kubernetes Java client |
| JWT | Workload-provided JWT/JWT supplier, Vault JWT role | Thường **không** cần SDK cloud |
| AppRole | Role ID và Secret ID được cấp/unwrap an toàn | Không nhất thiết cần SDK ngoài |
| AWS IAM | IAM credentials từ metadata/credential provider và chữ ký AWS V4 | `com.amazonaws:aws-java-sdk-core` theo tài liệu `AwsIamAuthentication` |
| GCP IAM Credentials | Tài khoản có quyền gọi `signJwt`, role Vault GCP | `com.google.cloud:google-cloud-iamcredentials` theo tài liệu `GcpIamCredentialsAuthentication` |
| TLS certificate | Client cert + private key trong keystore và truststore | Không nhất thiết cần cloud SDK; cần cấu hình SSL |

Ví dụ chỉ khi chọn **AWS IAM authentication**:

```xml
<dependency>
    <groupId>com.amazonaws</groupId>
    <artifactId>aws-java-sdk-core</artifactId>
    <!-- Version chọn theo dependency management được hỗ trợ -->
</dependency>
```

**Không thêm AWS SDK hoặc GCP SDK nếu chỉ dùng Kubernetes/JWT/AppRole**. Với AWS/GCP, cần xác nhận API auth chính xác theo bản Spring Vault đang dùng, credentials provider, quyền IAM và Vault role; SDK có mặt không thể thay thế Vault ACL. Một số cơ chế chỉ có đường đồng bộ hoặc hạn chế reactive, vì vậy không suy rằng mọi auth implementation hoạt động giống nhau với `ReactiveVaultTemplate`.

Nguồn: [Spring Vault – Authentication Methods](https://docs.spring.io/spring-vault/reference/vault/authentication.html).

### 5.5. HTTP client: JDK mặc định, transport ngoài khi có nhu cầu

Spring Vault 4.1 dùng **JDK `HttpClient`** làm lựa chọn mặc định khi không có HTTP client khác phù hợp. Nếu cần tính năng transport riêng, có thể chọn:

```xml
<!-- Tuỳ chọn 1: Apache HttpComponents 5, chẳng hạn khi cần
     SslConfiguration/keystore chuyên biệt -->
<dependency>
    <groupId>org.apache.httpcomponents.client5</groupId>
    <artifactId>httpclient5</artifactId>
</dependency>
```

```kotlin
// Tuỳ chọn 2: Reactor Netty khi đã theo reactive stack
dependencies {
    implementation("io.projectreactor.netty:reactor-netty")
}
```

Các ví dụ này **cần BOM** hoặc phiên bản được quản lý phù hợp. Tài liệu Spring Vault còn mô tả Jetty và Apache reactive transport, nhưng không nên thêm toàn bộ transport vào cùng ứng dụng chỉ vì chúng có sẵn. Đặc biệt, tài liệu Spring Vault lưu ý `SslConfiguration` dành riêng cho Vault client chỉ áp dụng khi **Apache HttpComponents** có mặt trên classpath trong cấu hình được mô tả; xác minh client thực tế khi cần mTLS, custom CA, timeout hoặc proxy.

Không bật **wire logging** cho HTTP client trong môi trường chạy thật nếu không có kiểm soát chặt: header Vault token và body chứa secret có thể bị ghi ra log. Khi nâng từ 3.x, lưu ý Spring Vault 4.0 đã **bỏ hỗ trợ OkHttp**, nên không chỉ thay version mà cần cập nhật request factory nếu đang dùng OkHttp.

Nguồn: [Spring Vault – HTTP Client Support](https://docs.spring.io/spring-vault/reference/vault/client-support.html), [Spring Vault 4.0 GA](https://spring.io/blog/2025/11/18/spring-vault-4-0-goes-ga/).

### 5.6. Spring Cloud Vault starter: dùng khi cần cấu hình ứng dụng

Core giúp code **chủ động gọi** `VaultTemplate`. Spring Cloud Vault starter dùng **Config Data API** để lấy secret từ Vault đưa vào Spring `Environment` theo application/profile. Với ứng dụng Spring Boot:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>2026.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-vault-config</artifactId>
    </dependency>
</dependencies>
```

Ví dụ này giả định dự án đã dùng **Boot 4.2.0** và BOM Boot tương ứng. Nếu đang dùng Boot 4.0/4.1, phải tra release train Cloud phù hợp (ví dụ dòng `2025.1.x`), không tự gắn `2026.0.0` theo số mới nhất. Starter có thể tự kéo Core; cần xem dependency tree trước khi thêm hoặc override Core.

Mẫu `application.yml` minh họa workload Kubernetes:

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

Tên host, role, mount chỉ là ví dụ. Workload cần ServiceAccount JWT, Vault Kubernetes auth role, Vault policy tối thiểu và kết nối TLS tin cậy. Cấu hình này **không tự thay thế** một tiến trình cập nhật credential động cho JDBC hoặc TLS/PKI sau khi ứng dụng đã khởi động.

Nguồn: [Spring Cloud Vault – Quick Start](https://docs.spring.io/spring-cloud-vault/reference/quickstart.html), [Spring Cloud Vault – Authentication](https://docs.spring.io/spring-cloud-vault/reference/authentication.html).

### 5.7. Giám sát và kiểm thử: tách khỏi runtime Core

Với Spring Boot, thêm `spring-boot-starter-actuator` khi cần kiểm tra sức khoẻ ứng dụng và gửi metric qua Micrometer; yêu cầu này thuộc **quan sát ứng dụng**, không phải một thành phần bắt buộc để `VaultTemplate` hoạt động. Chọn metric như lỗi xác thực, timeout, lỗi renew/rotation token và lease, thời gian phản hồi, trạng thái kết nối; **không** đưa token, path chứa thông tin nhạy cảm hay giá trị secret vào label, log hoặc trace.

Nếu muốn integration test với Vault thực thay cho mock, Testcontainers hiện cung cấp module riêng:

```xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-vault</artifactId>
    <version>2.0.5</version>
    <scope>test</scope>
</dependency>
```

```kotlin
dependencies {
    testImplementation("org.testcontainers:testcontainers-vault:2.0.5")
}
```

Phiên bản trên là ví dụ công bố trong tài liệu Testcontainers tại thời điểm tham chiếu; có thể thay bằng BOM/quản lý test dependency tương thích. Testcontainers **chỉ phục vụ test**, không đưa vào `implementation`/runtime production. Test cần khởi tạo container và bật đúng mount KV/Transit/PKI, xác thực workload giả lập phù hợp, cấp policy tối thiểu; từ đó kiểm tra cả đường thành công và lỗi 403, 404, timeout/lease hết hạn.

Chỉ mock `VaultOperations` giúp unit test thuật toán nghiệp vụ, **không** chứng minh Vault role, mount path, TLS, KV v1/v2 hoặc phiên bản HTTP client đã đúng.

Nguồn: [Testcontainers – HashiCorp Vault module](https://java.testcontainers.org/modules/vault/).

## 6. Phân biệt dependency của Java với cấu hình Vault Server

Những capability sau **đã nằm trong Spring Vault Core**, nhưng chỉ hoạt động khi Vault server được cấu hình:

| Capability | API Spring Vault | Cấu hình Vault Server bắt buộc |
| --- | --- | --- |
| KV secret | `opsForKeyValue(mount, KV_1/KV_2)`, `opsForVersionedKeyValue(mount)` | Mount KV v1/v2, policy `read`/`create`/`update` tùy thao tác |
| Transit encrypt/decrypt | `opsForTransit(mount)` | Transit engine, key và policy trên `encrypt/decrypt` |
| PKI issue/revoke | `opsForPki(mount)` | PKI engine, CA/role, giới hạn TTL/CN, policy cấp/revoke |
| Token/session lifecycle | `ClientAuthentication`, `SessionManager` | Auth mount, role/workload binding, token policy và TTL |
| Dynamic secret lease | `SecretLeaseContainer` và các API quản lý | Secret engine cấp lease, policy renew/revoke khi cần |

Ví dụ: thêm `spring-vault-core` **không** tạo Transit key `orders-key` trên Vault server, cũng không cho quyền `update` đối với `transit/encrypt/orders-key`. Tương tự, thêm `spring-cloud-starter-vault-config` không bảo đảm Kubernetes role đã được cấp quyền truy cập KV mount. Chẩn đoán `403 Forbidden` phải bắt đầu từ token/policy/path, không mặc định coi là thiếu JAR.

## 7. Kiểm tra dependency tree và phát hiện lỗi

**Maven:**

```bash
mvn -version
mvn help:effective-pom
mvn dependency:tree
```

**Gradle:**

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-vault-core
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-webflux
./gradlew dependencyInsight --configuration runtimeClasspath --dependency jackson-databind
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-data-keyvalue
```

Trên Windows có thể dùng `gradlew.bat`. Kiểm tra cả `compileClasspath` và `runtimeClasspath` khi kết quả khác nhau. `optional`, `exclude`, BOM và dependency override đều có thể làm thư viện được yêu cầu khác thư viện thực tế được nạp.

| Triệu chứng | Khả năng liên quan tới dependency | Việc cần kiểm tra |
| --- | --- | --- |
| `NoClassDefFoundError` cho Jackson converter/mapper | Thiếu mapper hoặc hai thế hệ Jackson không nhất quán | Cây phụ thuộc JSON, BOM, module custom |
| Lỗi liên quan `WebClient`/`Mono` | Thiếu `spring-webflux`/Reactor hoặc bị exclude | Runtime classpath reactive và HTTP connector |
| Lỗi khi bật `@EnableVaultRepositories` | Thiếu Spring Data KeyValue/Commons hoặc không đúng thế hệ | Spring Data BOM; sau đó policy mount discovery |
| Lỗi loại AWS credentials/GCP IAM | Thiếu SDK/cloud identity hoặc dùng sai API phiên bản | POM optional SDK và cách lấy workload credential |
| `NoSuchMethodError` trong Spring Framework | Spring Vault 4.x đi cùng Spring Framework 6.x hoặc patch bị ép | `spring-core`, `spring-web`, BOM/Cloud train |
| Không có bean `VaultTemplate` | Core không tự tạo mọi bean trong mọi kiểu ứng dụng | `@Configuration` thủ công hoặc starter/autoconfiguration |
| `403` từ Vault khi đọc KV/Transit/PKI | Thường do ACL/auth/namespace, không phải thiếu JAR | Token policies, path, mount và capability |
| KV trả dữ liệu rỗng/`404` | KV v1/v2 và path API bị nhầm | Mount version, `secret/data/...` và API domain |

Trong Spring Vault **4.0.x/4.1.x**, cần chú ý **CVE-2026-41698** liên quan path traversal qua secret path. Spring đã công bố bản sửa trong **4.0.5 và 4.1.2** ngày **19/11/2026**. Release train/BOM quản lý dependency không bảo đảm Core được resolve về patch đã sửa: kiểm tra classpath cuối cùng và đối chiếu [thông báo bản vá](https://spring.io/blog/2026/11/19/spring-vault-4-0-5-4-1-2-available/).

## 8. Bài tập lựa chọn dependency

**Tình huống A — API Java cần đọc KV v2 và gọi Transit:** chọn `spring-vault-core` cùng Jackson phù hợp và HTTP client mặc định. Tạo bean `VaultOperations`, cấu hình workload auth, ACL KV/Transit và test kết nối. **Không** thêm Spring Data repositories, Cloud Vault starter hay SDK AWS nếu không sử dụng.

**Tình huống B — Spring Boot đọc DB credentials từ Vault khi khởi động:** chọn Cloud Vault starter theo BOM Boot + Cloud, bật Config Data và cấu hình secrets backend. Nếu credential có TTL/lease và cần rotation khi đang chạy, phải thiết kế vòng đời/refresh cụ thể; nạp property một lần không làm mọi connection pool tự nhận mật khẩu mới.

**Tình huống C — dịch vụ reactive trên Kubernetes:** chọn Core + WebFlux/Reactor và reactive client, xác thực bằng ServiceAccount JWT. Không cần Kubernetes Java SDK chỉ để gửi token đăng nhập Vault; kiểm tra `ReactiveSessionManager` và thời gian hết hạn token.

**Tình huống D — lưu entity dưới dạng KV repository:** chọn Core + Spring Data KeyValue và bật `@EnableVaultRepositories`. Thiết kế policy cho mount discovery, kiểm tra semantics xóa của KV v2; không dùng Vault repository như cơ sở dữ liệu hỗ trợ mọi kiểu truy vấn.

**Tình huống E — kiểm thử lỗi Transit/PKI và ACL:** thêm Testcontainers Vault ở **test scope**, bật engines và tạo policy trong container. Kiểm tra trường hợp thành công, thiếu quyền, token hết hạn, TLS/timeout và không xuất secret trong test report.

## 9. Checklist trước khi chốt bộ phụ thuộc

- [ ] Java runtime/JDK và Spring Framework tương thích với dòng Spring Vault đã chọn.
- [ ] `spring-vault-core` có đúng một phiên bản thực sự được resolve; các BOM không kéo về thế hệ khác.
- [ ] Có Jackson tương thích; biết rõ Jackson 2 hay Jackson 3 đang được dùng.
- [ ] Chỉ bổ sung WebFlux/Reactor nếu dùng reactive; Spring Data KeyValue nếu dùng repositories; SDK cloud nếu phương thức auth yêu cầu.
- [ ] Đã quyết định dùng Core trực tiếp hay Cloud Vault starter; nếu dùng Cloud Vault đã chọn đúng Spring Cloud release train.
- [ ] Đã xác minh HTTP client/TLS/timeout và loại bỏ logging có thể làm lộ secret/token.
- [ ] Vault mount, role, policy, KV version, Transit key/PKI role và vòng đời token/lease được kiểm thử.
- [ ] Có unit/integration test đúng phạm vi, trong đó dependency Testcontainers chỉ nằm ở test.
- [ ] Đã kiểm tra patch bảo mật và cây phụ thuộc cuối cùng trước khi phát hành.

**Ghi nhớ:** `spring-vault-core` là điểm khởi đầu cho API Vault; **JSON/reactive/repositories/cloud SDK/HTTP client** là các lựa chọn theo tính năng; **Spring Cloud Vault** giải quyết import cấu hình; còn **Vault Server + policy** quyết định quyền và hành vi runtime. Cài đủ JAR là điều kiện kỹ thuật ban đầu, kiểm chứng runtime và quyền workload mới xác nhận tích hợp hoạt động.

### Nguồn tham khảo

1. [Spring Vault – Dependencies](https://docs.spring.io/spring-vault/reference/introduction/dependencies.html)
2. [Spring Vault – Getting Started](https://docs.spring.io/spring-vault/reference/introduction/getting-started.html)
3. [Spring Vault – Vault Template](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
4. [Spring Vault – Reactive Infrastructure](https://docs.spring.io/spring-vault/reference/vault/reactive-template.html)
5. [Spring Vault – Vault Repositories](https://docs.spring.io/spring-vault/reference/vault/vault-repositories.html)
6. [Spring Vault – Authentication Methods](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
7. [Spring Vault – HTTP Client Support](https://docs.spring.io/spring-vault/reference/vault/client-support.html)
8. [Spring Cloud Vault – Quick Start](https://docs.spring.io/spring-cloud-vault/reference/quickstart.html)
9. [Spring Cloud – Release Train Compatibility](https://spring.io/projects/spring-cloud/)
10. [Testcontainers – HashiCorp Vault Module](https://java.testcontainers.org/modules/vault/)
11. [Spring Vault 4.0.5/4.1.2 – Security Fixes, 19/11/2026](https://spring.io/blog/2026/11/19/spring-vault-4-0-5-4-1-2-available/)
