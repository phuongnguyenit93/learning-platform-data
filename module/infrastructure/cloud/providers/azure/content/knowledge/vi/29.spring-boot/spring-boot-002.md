# Quản lý dependency bằng Spring Cloud Azure

Một dịch vụ Spring Boot cần đọc cấu hình từ Azure Key Vault, tải chứng từ lên Azure Blob Storage và gửi sự kiện đơn hàng qua Azure Service Bus. Lập trình viên thêm ba thư viện Azure vào `pom.xml`, nhưng khi deploy ứng dụng gặp lỗi `NoSuchMethodError` liên quan tới Azure Core; trong một môi trường khác, ứng dụng chạy được nhưng không lấy được token từ Microsoft Entra ID. Có người đề xuất “nâng tất cả dependency lên bản mới nhất”, người khác đề xuất “copy connection string vào application.yml cho nhanh”.

Cả hai cách sửa đó đều có rủi ro. **Một dự án Spring Boot trên Azure phải quản lý hai vấn đề độc lập nhưng liên quan:**

1. **Đúng thư viện và đúng tập phiên bản tương thích** để classpath và auto-configuration hoạt động.
2. **Đúng cấu hình vận hành, danh tính và quyền truy cập** để ứng dụng thực sự kết nối được với Azure.

**Spring Cloud Azure** cung cấp các starters, tích hợp Spring Boot và một **Bill of Materials (BOM)** giúp quản lý những phiên bản thư viện trong hệ sinh thái Azure. BOM làm giảm xung đột và số lượng version phải đặt thủ công, nhưng **không bảo đảm mọi tổ hợp Spring Boot, Spring Cloud, Java, Azure SDK và Azure services đều tương thích**. Người phát triển vẫn phải chọn một bộ release đã được kiểm chứng và duy trì chuỗi cung ứng phần mềm.

Bài học thuộc chương **Spring Boot trên Azure** của module `CLOUD_PROVIDERS_AZURE`. Module giới thiệu toàn bộ Azure từ subscription, resource group, Microsoft Entra ID, mạng ảo, compute, storage và dữ liệu tới triển khai, giám sát, bảo vệ và tối ưu chi phí. Vì thế, bài không dừng ở cú pháp Maven/Gradle mà còn hướng dẫn quyết định dependency nào cần đưa vào ứng dụng, cách dùng managed identity, làm chủ transitive dependencies, kiểm thử và triển khai theo môi trường.

> **Chính sách phiên bản:** Không có một phiên bản Spring Cloud Azure cố định phù hợp mọi dự án. Các dòng Spring Boot, Spring Cloud, Java, Spring Cloud Azure và Azure SDK thay đổi theo thời gian. Những chỗ ghi `REPLACE_WITH_APPROVED_*` là **placeholder bắt buộc thay bằng bản tương thích được xác nhận trong chính sách và tài liệu release hiện hành**. Không copy nguyên placeholder vào bản build thật. Các lệnh trong bài là ví dụ để học viên chạy trong project lab của mình; việc biên soạn tài liệu này không tự chạy Maven/Gradle hay chỉnh file build của repository hiện tại.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của **Spring Boot dependency management**, **Spring Cloud BOM** và **Spring Cloud Azure BOM**.
2. Phân biệt **starter**, **auto-configuration**, **Azure SDK trực tiếp**, **BOM** và **runtime configuration**.
3. Thêm `spring-cloud-azure-dependencies` vào Maven/Gradle đúng phạm vi.
4. Chọn các starters phù hợp cho **Key Vault Secrets, Blob Storage, Service Bus và App Configuration**.
5. Tránh tự gắn version cho từng Azure starter khi BOM đã quản lý chúng.
6. Hiểu vì sao không thể mặc định chọn dòng Spring Cloud Azure mới nhất cho Spring Boot hiện tại.
7. Đọc **effective POM**, **dependency tree** và **Gradle dependencyInsight** để tìm xung đột phiên bản.
8. Nhận biết lỗi `NoSuchMethodError`, `ClassNotFoundException`, lỗi auto-configuration và lỗi authentication.
9. Áp dụng **DefaultAzureCredential/managed identity**, service-specific RBAC, Key Vault và cấu hình theo môi trường.
10. Thiết kế test unit, integration, smoke và CI để phát hiện dependency drift trước Production.
11. Phân biệt **Azure Service Bus starter, JMS, Spring Integration và Spring Cloud Stream binder**.
12. Lập kế hoạch **upgrade/migration** an toàn từ phiên bản cũ sang release train mới.
13. Dùng SBOM và dependency/security scanning mà không nâng bừa thư viện.
14. Hoàn thành lab thêm BOM và tối thiểu hai starters rồi giải thích toàn bộ classpath.

## 2. Tình huống điển hình: API xử lý đơn hàng

Giả sử ứng dụng `order-api` có kiến trúc:

```text
Client
  |
  v
Spring Boot order-api (Java)
  |
  +-- Azure Key Vault
  |     +-- lấy secret được phép
  |
  +-- Azure Blob Storage
  |     +-- lưu file hóa đơn
  |
  +-- Azure Service Bus
  |     +-- phát OrderCreated
  |
  +-- Application Insights / Azure Monitor
  |     +-- telemetry ứng dụng
  |
  v
Azure Container Apps hoặc AKS/App Service
      |
      +-- Managed Identity / Workload Identity
      +-- Network + DNS + private access theo thiết kế
```

Đội phát triển muốn:

- Không viết thủ công logic tạo từng HTTP client, token và retry cho mọi dịch vụ.
- Không hard-code access key vào source code.
- Quản lý dependency bằng một điểm thống nhất.
- Dùng Spring Boot configuration binding/auto-configuration khi phù hợp.
- Có thể kiểm tra classpath và nâng phiên bản có kiểm soát.
- Tách lỗi **classpath** khỏi lỗi **RBAC/network** khi điều tra.

Spring Cloud Azure hỗ trợ mục tiêu ấy, **nhưng không triển khai thay Azure resources**, không tự tạo role assignment và không tự xác minh mọi nghiệp vụ.

## 3. Dependency là gì và vì sao version alignment quan trọng?

Một ứng dụng Java không chỉ có những thư viện bạn ghi trực tiếp trong `pom.xml`.

```text
order-api
  |
  +-- spring-boot-starter-web
  |     +-- Spring Web/MVC
  |     +-- Jackson và các thư viện liên quan
  |
  +-- spring-cloud-azure-starter-storage-blob
  |     +-- Spring Cloud Azure auto-configuration
  |     +-- Azure Storage Blob SDK
  |     +-- Azure Core / Identity / HTTP pipeline dependencies
  |
  +-- spring-cloud-azure-starter-servicebus
        +-- Spring Cloud Azure Service Bus integration
        +-- Azure Messaging Service Bus SDK
        +-- Azure Core / AMQP/Reactor dependencies
```

Những thư viện bên dưới gọi là **transitive dependencies**. Nếu hai nhánh cần hai versions khác nhau của cùng `azure-core` hoặc Reactor, Maven/Gradle sẽ **giải quyết ra một version cuối cùng** theo quy tắc của công cụ build. Version đó có thể không phù hợp với code đã biên dịch của một thư viện khác.

Các triệu chứng thường gặp:

- `NoSuchMethodError`: runtime gọi method không còn tồn tại/không có signature kỳ vọng.
- `ClassNotFoundException` hoặc `NoClassDefFoundError`: thiếu class/module tại runtime.
- `IllegalAccessError`, `LinkageError`: classpath/API không tương thích.
- Auto-configuration fail dù code không đổi.
- Netty/Reactor/HTTP client có xung đột.
- Một thư viện đổi contract khi ứng dụng vẫn dùng starter cũ.

**Dependency management có mục tiêu tạo một đồ thị phiên bản nhất quán**. Nó không thể biến hai API versions không tương thích thành tương thích chỉ bằng cách ép cùng một số version.

## 4. Phân biệt năm thành phần dễ bị nhầm

| Thành phần | Nó làm gì? | Ví dụ |
|---|---|---|
| **Spring Boot starter** | Kéo một nhóm dependency/cấu hình nền tảng Spring Boot. | `spring-boot-starter-web`. |
| **Spring Cloud Azure starter** | Thêm tích hợp và auto-configuration Spring/Azure cho dịch vụ tương ứng. | `spring-cloud-azure-starter-storage-blob`. |
| **Azure SDK for Java** | Cung cấp client APIs thao tác trực tiếp với Azure. | `azure-storage-blob`, `azure-messaging-servicebus`. |
| **BOM** | Danh mục version được quản lý đồng bộ cho những artifacts nằm trong phạm vi BOM. | `spring-cloud-azure-dependencies`. |
| **Runtime configuration** | Cho biết endpoint, namespace, credentials, resource name, policy. | `spring.cloud.azure.storage.blob.account-name`. |

**BOM không phải thư viện chạy ở runtime.** Import BOM không tự đưa Blob SDK vào classpath. Bạn vẫn cần starter hoặc SDK dependency thật.

**Starter không phải Azure resource.** Thêm Service Bus starter không tạo namespace/queue cho bạn. Resource, IAM/RBAC, networking, quotas và cost phải được quản lý riêng.

## 5. Ba tầng quản lý phiên bản

Một ứng dụng phổ biến có ít nhất:

```text
Java runtime / toolchain
           |
Spring Boot release + Boot dependency BOM
           |
Spring Cloud release train (nếu dùng các Spring Cloud components)
           |
Spring Cloud Azure release + Azure BOM
           |
Azure SDK libraries + HTTP/identity dependencies
           |
Ứng dụng Java và cấu hình Azure
```

**Spring Boot BOM** quản lý nhiều thư viện Spring, Jakarta, Jackson, testing, logging, Reactor, v.v.

**Spring Cloud BOM** quản lý một hệ sinh thái Spring Cloud như Config/Gateway/Stream và những modules nằm trong release train đó; chỉ thêm khi dự án thật sự dùng và cần alignment theo release tương ứng.

**Spring Cloud Azure BOM** quản lý các artifacts Spring Cloud Azure và một tập dependency Azure có liên quan theo bản phát hành.

Ba BOM **không thể thay cho nhau**. Nếu có nhiều BOM cùng quản lý một artifact, **thứ tự import và dependencyManagement trực tiếp có thể ảnh hưởng version được chọn**; phải xem effective POM/Gradle resolved graph thay vì dựa vào dự đoán.

## 6. Chọn release matrix trước khi viết dependency

Trước khi chọn `spring-cloud-azure.version`, xác nhận:

1. Java runtime/JDK: version và vendor được doanh nghiệp hỗ trợ.
2. Spring Boot major/minor/patch.
3. Spring Framework/Jakarta namespace phù hợp Spring Boot version.
4. Spring Cloud release train nếu dự án dùng.
5. Spring Cloud Azure line chính thức hỗ trợ Boot/Cloud đó.
6. Azure SDK versions được BOM quản lý.
7. Azure services và starters cần dùng.
8. Plugin Maven/Gradle, compiler toolchain và test framework.
9. Security advisories và end-of-support policies.
10. Những giới hạn của production hosting (App Service, Container Apps, AKS, Java native image nếu áp dụng).

### Quy tắc compatibility

**Không tự suy ra:** “Spring Boot 4 chạy được với Spring Cloud Azure 5 vì đều là số mới”. Chuyển đổi major version có thể ảnh hưởng Spring Framework, Jakarta API, auto-configuration metadata, Reactor và dependencies.

**Không tự suy ra:** “Azure SDK mới nhất tương thích với starter cũ”. Starter có thể được biên dịch theo APIs của dòng SDK khác.

Hãy lập **compatibility matrix** từ release notes/support table của chính Spring Cloud Azure và Spring Boot tương ứng; khóa tập phiên bản đó trong project build, có test và định kỳ nâng cấp.

## 7. Quy trình chọn version có thể kiểm chứng

| Bước | Hỏi gì? | Bằng chứng cần ghi |
|---|---|---|
| 1. Cố định Boot | Dự án đang dùng Boot major/minor nào? | Parent/plugin version trong build file. |
| 2. Chọn Spring Cloud | Có Gateway/Config/Stream components không? | Release train compatible với Boot. |
| 3. Chọn Spring Cloud Azure | Dòng nào được hỗ trợ cho cặp Boot/Cloud? | Official compatibility table và release notes. |
| 4. Kiểm tra Java | Release mới cần JDK nào? | Java baseline/toolchain. |
| 5. Kiểm tra starters | Artifact có tồn tại trong dòng đã chọn không? | Artifact coordinates của release thật. |
| 6. Import BOM | BOM điều phối Azure artifacts nào? | Effective POM/resolved dependencies. |
| 7. Thử build/test | Có lỗi compilation/linkage/auto-config không? | CI output và integration tests. |
| 8. Security scan | Có CVE hoặc bản đã hết hỗ trợ không? | SBOM và vulnerability report. |
| 9. Ghi ADR | Vì sao khóa phiên bản ấy? | Architecture decision record. |
| 10. Lập upgrade plan | Khi nào nâng và rollback thế nào? | Cadence, owner, acceptance criteria. |

Các dòng/version cụ thể **không được bịa hoặc cố định tùy tiện** trong tài liệu này. Mã bên dưới dùng placeholder để buộc người học thay bằng **phiên bản có chứng cứ tương thích**.

## 8. Maven: import Spring Cloud Azure BOM

Ví dụ `pom.xml` tối thiểu cho Spring Boot app dùng **Key Vault Secrets** và **Blob Storage**. Các placeholder là văn bản cần thay, **không chạy nguyên mẫu**.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>REPLACE_WITH_APPROVED_BOOT_VERSION</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>order-api</artifactId>
    <version>0.1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <spring-cloud-azure.version>REPLACE_WITH_COMPATIBLE_SCA_VERSION</spring-cloud-azure.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.azure.spring</groupId>
                <artifactId>spring-cloud-azure-dependencies</artifactId>
                <version>${spring-cloud-azure.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-starter-keyvault-secrets</artifactId>
        </dependency>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### Vì sao không ghi version cho từng starter?

BOM đang quản lý versions, vì vậy dependencies có thể được khai báo **không có `<version>`**. Thêm phiên bản tùy ý trên mỗi starter sẽ giảm khả năng alignment và có thể tạo classpath không kiểm soát.

### Phân tích từng phần

- `spring-boot-starter-parent` mang dependency/plugin management do Boot cung cấp.
- `dependencyManagement` import Spring Cloud Azure BOM kiểu `pom`/`import`.
- `spring-cloud-azure-starter-keyvault-secrets` tạo tích hợp Key Vault.
- `spring-cloud-azure-starter-storage-blob` cung cấp integration Blob Storage.
- Test starter có `scope=test`, không đưa test framework vào production runtime.
- Azure credentials và endpoint **không viết vào pom.xml**.

**Java 17 trong ví dụ chỉ là giá trị minh họa**, không bảo đảm mọi cặp Boot/Spring Cloud Azure hỗ trợ đúng baseline đó. Chọn JDK theo compatibility matrix thật.

## 9. Maven: BOM không tự kéo vào tất cả dịch vụ

Nếu chỉ khai báo:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>REPLACE_WITH_COMPATIBLE_SCA_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

thì **chưa có Azure Blob SDK/starter trong runtime classpath**. BOM chỉ quản lý phiên bản **nếu dependency liên quan được yêu cầu** qua direct hoặc transitive dependency.

Để dùng Blob, bạn phải thêm:

```xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
</dependency>
```

và sau đó cấu hình tài nguyên/identity đúng. Điều này cũng đúng với Key Vault, Service Bus và các tích hợp khác.

### Dependency management khác dependency declaration

| Khối | Ý nghĩa |
|---|---|
| `<dependencyManagement>` | Quy định version/scope/exclusions mặc định khi artifact được dùng. |
| `<dependencies>` | Thực sự yêu cầu dependency vào project. |
| `<scope>test</scope>` | Dùng tại compile/test theo semantics Maven; không cần trong production runtime. |
| `<scope>provided</scope>` | Do runtime/environment cung cấp theo hợp đồng; phải sử dụng cẩn trọng. |
| `<exclusions>` | Loại bỏ dependency transitive có chủ đích; có thể gây thiếu class. |

**Không dùng exclusions để “chữa” một lỗi linkage mà chưa chứng minh dependency nào sai.**

## 10. Gradle Groovy DSL: import BOM bằng plugin

Một hướng phổ biến với plugin `io.spring.dependency-management`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'REPLACE_WITH_APPROVED_BOOT_VERSION'
    id 'io.spring.dependency-management' version 'REPLACE_WITH_APPROVED_PLUGIN_VERSION'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencyManagement {
    imports {
        mavenBom "com.azure.spring:spring-cloud-azure-dependencies:REPLACE_WITH_COMPATIBLE_SCA_VERSION"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'com.azure.spring:spring-cloud-azure-starter-keyvault-secrets'
    implementation 'com.azure.spring:spring-cloud-azure-starter-storage-blob'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### Chú ý

- Plugin Spring Boot và plugin dependency-management cần version tương thích.
- `dependencyManagement.imports.mavenBom` quản lý versions tương tự Maven theo cơ chế plugin.
- Đừng dùng dòng code copy từ plugin version cũ khi Boot/Gradle major version đã đổi.
- Với Gradle native BOM platform, mô hình import và conflict resolution khác; phải chọn strategy thống nhất.

**Không cho rằng Maven và Gradle luôn chọn cùng version transitive** nếu có nhiều BOM hoặc constraints. Hãy kiểm tra runtime classpath thực.

## 11. Gradle Kotlin DSL: BOM bằng native platform

Một cách khác là dùng Gradle native `platform(...)`, minh họa trong `build.gradle.kts`:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "REPLACE_WITH_APPROVED_BOOT_VERSION"
}

group = "com.example"
version = "0.1.0-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(
        platform(
            "com.azure.spring:spring-cloud-azure-dependencies:REPLACE_WITH_COMPATIBLE_SCA_VERSION"
        )
    )
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("com.azure.spring:spring-cloud-azure-starter-storage-blob")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
```

**Cảnh báo về version resolution:** nếu dự án không dùng Boot dependency-management plugin, Spring Boot Gradle plugin có những cơ chế/BOM expectations riêng; tùy project, có thể cần import Spring Boot BOM như Gradle `platform("org.springframework.boot:spring-boot-dependencies:...")` hoặc dùng BOM management tương ứng. Hãy xem **resolved dependency graph** để xác nhận mọi versions của Spring/Jackson/Reactor đã được quản lý.

### Không trộn chiến lược tùy tiện

Hai cách sau không tự giống nhau:

1. Plugin `io.spring.dependency-management` với `dependencyManagement.imports.mavenBom`.
2. Gradle native `platform(...)` với version constraints và conflict resolution của Gradle.

Chọn một cấu hình rõ ràng, ghi vào convention của repo. Nếu cần cả hai, phải hiểu ưu tiên version resolution và kiểm thử chặt, không đoán.

## 12. Starters nào nên đưa vào ứng dụng?

| Nhu cầu | Artifact Spring Cloud Azure để đánh giá | Ghi chú |
|---|---|---|
| Đọc secrets từ Key Vault như configuration source. | `spring-cloud-azure-starter-keyvault-secrets` | Quyền secrets read, endpoint và property-source config. |
| Dùng Blob Storage với Spring integration. | `spring-cloud-azure-starter-storage-blob` | Storage Blob data-plane RBAC và account config. |
| Tích hợp Azure Service Bus SDK/Spring Boot. | `spring-cloud-azure-starter-servicebus` | Không đồng nhất với JMS/Stream binder. |
| App Configuration với Spring configuration model. | `spring-cloud-azure-starter-appconfiguration-config` | Artifact/config import tùy line; xác minh module trong release. |
| Service Bus qua Spring JMS. | `spring-cloud-azure-starter-servicebus-jms` | Chọn khi code thực dùng JMS contract và feature phù hợp. |
| Service Bus với Spring Integration. | `spring-cloud-azure-starter-integration-servicebus` | Chọn khi ứng dụng dùng Spring Integration channels. |
| Service Bus qua Spring Cloud Stream. | `spring-cloud-azure-starter-stream-servicebus` | Kiểm tra binder compatibility với Spring Cloud release train. |

**Các coordinates trên đại diện cho những dòng Spring Cloud Azure phổ biến.** Từng dòng phát hành có thể đổi/tách/loại artifact hoặc cách cấu hình. Xác minh artifacts được publish trong đúng release line; không ép Maven tải artifact không tồn tại hoặc ghép starter cũ vào BOM mới.

### Không thêm tất cả starters “để sẵn”

Nếu ứng dụng chỉ dùng Key Vault và Blob, không cần thêm JMS, Service Bus, Cosmos DB, Redis, Event Hubs và các integrations khác. Starters dư thừa làm classpath lớn, mở rộng attack surface, tăng khả năng auto-configuration không mong muốn và khó debug.

**Nguyên tắc:** mỗi dependency phải có use case, owner và lý do tồn tại.

## 13. BOM, starter và Azure SDK: ba mô hình sử dụng

Giả sử chỉ cần Azure Blob Storage.

**Cách A — Spring Cloud Azure starter:**

```xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
</dependency>
```

Phù hợp khi muốn Spring Boot property binding, auto-configuration và client bean do starter cung cấp.

**Cách B — Azure SDK trực tiếp:**

```xml
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-storage-blob</artifactId>
    <version>REPLACE_WITH_APPROVED_AZURE_SDK_VERSION</version>
</dependency>
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
    <version>REPLACE_WITH_APPROVED_IDENTITY_VERSION</version>
</dependency>
```

Phù hợp khi muốn tự tạo clients và không cần Spring integration; nếu có Azure SDK BOM đã được phê duyệt, ưu tiên BOM để tránh tự pin từng SDK.

**Cách C — Kết hợp starter và client tùy biến:**

Có thể dùng starter cho phần lớn dịch vụ nhưng tạo một `BlobServiceClient` custom khi cần account/endpoint khác, proxy/HTTP transport đặc biệt hoặc credential policy riêng.

**Điểm cần xác minh:** nhiều client beans cùng type có thể gây lỗi autowiring hoặc inject sai account. Dùng `@Qualifier`, explicit bean names và test.

## 14. Hiểu auto-configuration của Spring Cloud Azure

Starter thường mang các classes auto-configuration và Spring Boot configuration metadata. Khi phù hợp điều kiện, Spring có thể khởi tạo clients/beans dựa trên:

- Classpath có các Azure SDK classes cần thiết.
- Cấu hình service endpoint/account/namespace.
- Credential provider/identity.
- Conditional annotations và properties.
- Sự hiện diện hoặc vắng mặt của một bean do ứng dụng tự tạo.
- Active Spring profiles.
- Các cơ chế import property source khi dùng Key Vault/App Configuration.

```text
pom.xml / Gradle
     |
     +-- Starter available on classpath
     |
     v
Spring Boot starts
     |
     v
Auto-configuration conditions evaluated
     |
     +-- match + config valid -> Azure client bean
     |
     +-- no match -> no bean or startup failure (theo module)
     |
     v
Application services inject clients
```

**Không phải mọi starter tự sinh mọi loại bean**. API beans và auto-configuration đổi theo release; hãy xem actuator conditions report/diagnostics và tài liệu version đã chọn.

### Khi nào tự cấu hình?

- Nhiều storage accounts trong một ứng dụng.
- Custom retry/timeout, HTTP proxy, transport và diagnostics.
- Kết nối qua endpoint đặc biệt hoặc sovereign cloud.
- Muốn tách identity của từng service.
- Starters tạo bean không phù hợp contract cụ thể.

Khi tự tạo client, phải giữ **credential lifecycle, thread safety, close/shutdown, telemetry và testability**.

## 15. Key Vault Secrets starter

Key Vault lưu secrets/keys/certificates; **Secrets starter** chủ yếu hỗ trợ truy xuất secrets/configuration theo các API và property-source integration được cung cấp.

Maven dependency:

```xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-keyvault-secrets</artifactId>
</dependency>
```

Ví dụ `application.yml` với một cấu hình property source thường gặp:

```yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - endpoint: https://REPLACE_WITH_VAULT_NAME.vault.azure.net/

app:
  payment:
    # Không đặt password hoặc token thật vào YAML.
    mode: sandbox
```

**Cú pháp thuộc tính cần kiểm tra theo phiên bản Spring Cloud Azure thực**. Một số dòng hỗ trợ nhiều property sources/ordering; một số thế hệ cũ dùng naming/auto-config conventions khác.

### Khác biệt quan trọng

- Key Vault **management permission** không đồng nghĩa quyền đọc secrets qua data plane.
- Một `@Value("${secret-name}")` chỉ hoạt động nếu tên secret được ánh xạ vào Spring Environment theo cấu hình đang dùng.
- Secret name normalization (dấu gạch nối, dấu chấm) có thể khác convention app property.
- Secret refresh/rotation không nhất thiết tự cập nhật mọi singleton bean đã đọc giá trị khi startup.
- Không mặc định app sẽ “luôn sống” nếu vault/identity/network tạm lỗi lúc khởi động.

### Thiết kế startup an toàn

Với secret **bắt buộc**, cân nhắc fail startup rõ ràng nếu không lấy được secret, nhưng đồng thời đặt timeout/retry hợp lý. Với một secret tùy chọn, nên có fallback được phê duyệt, không tự chuyển sang plaintext credential trong source.

## 16. Blob Storage starter

Dependency:

```xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
</dependency>
```

Cấu hình minh họa:

```yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: REPLACE_WITH_STORAGE_ACCOUNT

app:
  storage:
    container: documents-lab
```

Spring Cloud Azure có thể tạo Blob SDK client(s) từ cấu hình và identity phù hợp theo release.

Ví dụ bean sử dụng client:

```java
package com.example.orders;

import com.azure.storage.blob.BlobServiceClient;
import org.springframework.stereotype.Service;

@Service
public class BlobAccountInfoService {
    private final BlobServiceClient blobServiceClient;

    public BlobAccountInfoService(BlobServiceClient blobServiceClient) {
        this.blobServiceClient = blobServiceClient;
    }

    // Phương thức này chỉ đọc metadata của client object.
    public String configuredAccountName() {
        return blobServiceClient.getAccountName();
    }
}
```

**Code yêu cầu** auto-configuration version được chọn thực sự expose `BlobServiceClient` bean; nếu không, cần cấu hình explicit Bean hoặc dùng SDK theo contract. Chỉ có bean trong Spring context **không chứng minh identity được phép upload blob**. Data-plane role như `Storage Blob Data Contributor` cần gán phù hợp scope khi thao tác ghi.

### Nên tách container name khỏi SDK dependency

Tên container, endpoint và account lấy từ configuration theo môi trường. Không build code thành một JAR khác chỉ vì đổi storage account từ lab sang Production.

## 17. Service Bus starter và các đường tích hợp

Azure Service Bus hỗ trợ queue/topic/subscription, nhưng cách ứng dụng Spring dùng phụ thuộc lập trình model:

| Cách tích hợp | Thói quen lập trình | Dependency liên quan |
|---|---|---|
| **Azure SDK** | `ServiceBusClientBuilder`, `ServiceBusSenderClient`, processor client. | `azure-messaging-servicebus`. |
| **Spring Cloud Azure starter** | Cấu hình và client integration qua Boot. | `spring-cloud-azure-starter-servicebus`. |
| **Spring JMS** | `JmsTemplate`, `@JmsListener` khi được hỗ trợ. | `spring-cloud-azure-starter-servicebus-jms`. |
| **Spring Integration** | Message channels/adapters. | `spring-cloud-azure-starter-integration-servicebus`. |
| **Spring Cloud Stream** | Function/message binder patterns. | `spring-cloud-azure-starter-stream-servicebus` theo compatibility. |

**Không gắn toàn bộ starters** chỉ vì ứng dụng “dùng Service Bus”. Chọn một abstraction đáp ứng processing model, error semantics, transactions và team skills.

Maven:

```xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-servicebus</artifactId>
</dependency>
```

Ví dụ property:

```yaml
spring:
  cloud:
    azure:
      servicebus:
        namespace: REPLACE_WITH_SERVICEBUS_NAMESPACE
```

Cấu hình namespace/transport/entity names khác nhau theo starter và integration, vì thế với JMS/Stream cần đọc đúng mapping property của artifact.

### Những điều dependency không quyết định

- Entity có phải queue/topic thực không.
- Receiver dùng peek-lock hay receive-and-delete.
- Dead-letter, retry, TTL và duplicate handling.
- Service Bus data-plane role có đủ quyền send/receive không.
- Connection đi qua AMQP port nào, có proxy/firewall không.
- Consumer có idempotent business handler không.

## 18. Ví dụ Service Bus SDK trực tiếp để hiểu lớp dependency

Khi không dùng auto-config của starter, Azure SDK có thể tạo sender bằng Microsoft Entra credential.

```java
package com.example.orders;

import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusSenderClient;
import com.azure.messaging.servicebus.ServiceBusMessage;

public final class OrderPublisher {
    private OrderPublisher() {}

    public static void sendLabMessage(
            String fullyQualifiedNamespace,
            String queueName) {

        try (ServiceBusSenderClient sender =
                 new ServiceBusClientBuilder()
                     .credential(
                         fullyQualifiedNamespace,
                         new DefaultAzureCredentialBuilder().build()
                     )
                     .sender()
                     .queueName(queueName)
                     .buildClient()) {

            ServiceBusMessage message =
                new ServiceBusMessage("OrderCreated:ORD-LAB-1042");
            message.setMessageId("evt-lab-1042-created");
            sender.sendMessage(message);
        }
    }
}
```

**Đây là ví dụ SDK Java**, không phải yêu cầu thêm Azure starters chỉ để chạy nó. Nó cần `azure-identity` và `azure-messaging-servicebus` versions tương thích, Azure Service Bus Data Sender permission đúng queue/namespace và đường mạng hoạt động.

- Dùng **stable message ID**/idempotency ở tầng nghiệp vụ.
- Đừng gửi message thật trong constructor hoặc tại startup hook mà thiếu kiểm soát.
- Client có thể được tạo như singleton Bean thay vì mỗi message tạo mới; ví dụ try-with-resources chỉ để minh họa lifecycle.
- Không coi Send success là downstream processing success.

## 19. App Configuration và Key Vault không phải một loại resource

**Azure App Configuration** phù hợp với cấu hình ứng dụng/feature flags có quản trị. **Key Vault** phù hợp quản lý secrets, keys và certificates.

```text
App Configuration
  ├── feature toggle
  ├── pricing-policy-version
  └── endpoint/name/reference to secrets
         |
         v
Key Vault
  ├── external-api-key
  └── service credential khi không thể dùng managed identity
```

Spring Cloud Azure có integration cho App Configuration, ví dụ starter thuộc dòng hỗ trợ `spring-cloud-azure-starter-appconfiguration-config`. Khi chọn phải xác minh:

- Artifact có tồn tại trong version đã khóa không.
- Cơ chế import Spring Config Data có cần `spring.config.import` hoặc cấu hình tương đương không.
- Feature flag refresh/watch semantics của phiên bản.
- Label/filter giữa dev/staging/prod.
- Key Vault references được resolve ở đâu, identity nào cần quyền.
- Có khả năng runtime refresh và cơ chế consistency/rollback không.

**Không dùng App Configuration như nơi mặc định lưu secret raw** nếu đã có Key Vault. **Không dùng Key Vault như kho mọi config không nhạy cảm** chỉ vì nó sẵn.

## 20. Dependency alignment và thông tin xác thực là hai vấn đề khác nhau

Ví dụ:

```text
Classpath OK:
  Spring Cloud Azure starter load successful
  BlobServiceClient created

Azure call FAIL:
  403 AuthorizationPermissionMismatch
```

Đây **không phải bằng chứng BOM sai**. Lỗi có thể do managed identity thiếu Blob data role, endpoint/account sai, firewall hoặc resource không tồn tại.

Ngược lại:

```text
Application fails at startup:
  java.lang.NoSuchMethodError on azure-core/HTTP pipeline
```

Lỗi này **có thể** do version alignment/classpath, không nên sửa bằng cách cấp nhiều Azure RBAC permissions hơn.

### Bản đồ phân loại lỗi

| Nhóm lỗi | Dấu hiệu | Kiểm tra đầu tiên |
|---|---|---|
| Dependency/linkage | `NoSuchMethodError`, missing class. | Dependency tree, BOM/version overrides. |
| Auto-config | No qualifying bean, property bind failure. | Conditions report và starter module. |
| Authentication | 401, credential chain failed. | Principal, token, env/config. |
| Authorization | 403, forbidden. | Data-plane RBAC/scope và propagation. |
| Resource/config | 404, invalid namespace/account. | Endpoint/entity names, environment. |
| Network | Timeout/DNS/TLS/AMQP connection. | Private DNS, outbound rules, TLS. |
| Throttling | 429/quota/exceeded. | Azure service quota/capacity/retry. |
| Business semantics | Duplicate message, stale secret, wrong container. | Idempotency, ownership, validation. |

## 21. Passwordless identity: DefaultAzureCredential

Ưu tiên Microsoft Entra authentication hoặc managed identity khi dịch vụ và Java SDK hỗ trợ.

Một chuỗi phổ biến:

```text
Local developer
  → az login / IDE-supported credential
  → DefaultAzureCredential (theo chain và SDK)
  → Azure service data plane

Cloud runtime
  → Managed identity / Workload Identity
  → Azure service data plane
```

`DefaultAzureCredential` có thể thử nhiều credential sources theo environment và phiên bản SDK. Vì vậy:

- Dev/test có thể dùng Azure CLI/IDE login khi được cấu hình.
- Production nên dựa vào **một identity đã biết** theo nền tảng hosting.
- Đừng vô tình để một production container sử dụng credential của developer.
- Nếu runtime hỗ trợ nhiều user-assigned identities, chọn đúng client ID theo policy.
- Không log access tokens hoặc credential values.
- Cần role assignment cho **từng service** riêng.
- Kiểm tra tenant/subscription của principal hiện tại.
- Nếu chain không chọn được credential, điều tra identity configuration thay vì mở rộng permission vô hạn.

**Spring Cloud Azure starter có thể tự dựng credential/client** theo cấu hình tương ứng; trong custom code có thể dùng Azure SDK `DefaultAzureCredentialBuilder`. Không giả định một bean credential được starter expose trong mọi version.

## 22. Entra RBAC: control plane khác data plane

| Dịch vụ | Ví dụ quyền data plane cần xem xét | Điều kiện |
|---|---|---|
| Key Vault Secrets | Role được phép đọc secrets, ví dụ `Key Vault Secrets User` theo RBAC mode. | Vault dùng RBAC hay access policy model? |
| Blob Storage | `Storage Blob Data Reader/Contributor`. | Đọc hay ghi? Account/container scope? |
| Service Bus | `Azure Service Bus Data Sender/Receiver`. | Send hay consume? Namespace/entity scope? |
| App Configuration | Role Data Reader theo data plane. | Chỉ đọc config/feature flags? |
| Application Insights/Monitor | Permissions để cấu hình hoặc xuất telemetry theo phương thức. | Không đồng nghĩa đọc toàn bộ workspace. |

**Đây là tên role thường gặp, không phải lời khẳng định quyền đã tồn tại trong subscription**. Kiểm tra role, scope, mode và propagation thực tế.

Một service principal có quyền **Contributor trên resource group** không nhất thiết có quyền đọc secrets/Blob data qua SDK. Nếu gặp 403, đừng thêm SDK version khác trước khi xác minh RBAC.

## 23. Tổ chức cấu hình theo môi trường

Một nguyên tắc: **JAR giống nhau, cấu hình và identity thay đổi theo environment**.

```text
order-api.jar
    |
    +-- local  → developer login + lab resources
    |
    +-- staging → managed identity staging + staging resources
    |
    +-- prod → managed identity prod + production resources
```

Một số field có thể đến từ `application.yml`, profiles, environment variables hoặc configuration service.

```yaml
app:
  storage:
    container: ${APP_STORAGE_CONTAINER:documents-lab}

spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}
      servicebus:
        namespace: ${AZURE_SERVICEBUS_NAMESPACE}
```

Trong cấu hình Spring, cú pháp `${ENV_NAME:default}` đọc biến môi trường với giá trị mặc định; cú pháp `${ENV_NAME}` yêu cầu có giá trị tương ứng (hoặc cơ chế xử lý thiếu cấu hình được thiết kế rõ).

### Tránh secrets trong Git

- Không lưu connection string thật vào `application-prod.yml`.
- Không ghi trực tiếp `AZURE_CLIENT_SECRET` vào CI logs.
- Không commit `.env` có secrets.
- Dùng Key Vault/secret manager, managed identity và pipeline secret handling.
- Bảo vệ runtime environment, crash dumps và diagnostic reports.
- Không dùng cùng identity/key cho tất cả môi trường chỉ để tiện test.

### Thứ tự ưu tiên property sources

Spring Boot và các integrations có quy tắc thứ tự các property sources. Key Vault/App Configuration có thể tham gia resolution, tùy module/version và chế độ import. Khi hai nguồn khai báo cùng key, phải biết **nguồn nào thắng**. Kiểm tra effective property resolution (chỉ tên/nguồn đã làm sạch, không in secret) và quy định ownership.

## 24. Điều tra Bean không được tạo

Giả sử một controller constructor cần `BlobServiceClient` nhưng startup báo:

```text
Parameter 0 of constructor required a bean of type
'com.azure.storage.blob.BlobServiceClient'
that could not be found.
```

Cách phân tích:

1. Starter Blob có nằm trong resolved runtime classpath không?
2. `spring-cloud-azure.version` có tương thích Spring Boot không?
3. Artifact name có đúng dòng release không?
4. Auto-configuration của starter có bị exclude/disable không?
5. Các properties account/endpoint được binding đúng không?
6. Có custom Bean override/multiple Beans không?
7. Có active profile nào khiến cấu hình không được nạp?
8. Có các condition annotations khác cần thỏa không?
9. `@ComponentScan` có tìm service của bạn không?
10. Sau khi đã có Bean, mới kiểm tra RBAC/network khi gọi SDK.

### Spring Boot conditions report

Ở lab, có thể bật debug startup:

```properties
debug=true
```

Spring Boot có thể in **conditions evaluation report** về auto-config matches/non-matches. Không bật debug logs tràn lan trong Production khi chưa review rủi ro logging. Với Actuator, `/actuator/conditions` có thể hữu ích nhưng cần bảo vệ endpoint/role, không public ra Internet.

## 25. Kiểm tra Maven resolved dependencies

Khi được phép thao tác trên **project lab**, những lệnh dưới đây giúp đọc build metadata:

```bash
mvn help:effective-pom

mvn dependency:tree

mvn dependency:tree -Dincludes=com.azure.spring,com.azure

mvn dependency:analyze
```

### Giải thích

- **effective-pom:** cấu hình Maven sau parent/profile/dependencyManagement inheritance.
- **dependency:tree:** dependency graph thực tế và các phiên bản resolution.
- **includes:** thu hẹp phạm vi hiển thị để tìm Azure/Spring packages.
- **dependency:analyze:** hỗ trợ phát hiện declared-but-unused hoặc used-but-undeclared dependency, có giới hạn khi dùng reflection/auto-config.

Nếu dự án dùng multi-module, kiểm tra **module đúng đang deploy**. Một dependency thấy ở parent BOM không có nghĩa mọi module đều có nó ở runtime.

### Điều cần tìm trong tree

```text
com.azure.spring:spring-cloud-azure-starter-storage-blob:jar:<resolved>
  +- com.azure:azure-storage-blob:jar:<resolved>
  +- com.azure:azure-core:jar:<resolved>
  ...
```

Đối chiếu versions với BOM đã chọn. Nếu một artifact Azure bị override bởi version trực tiếp hoặc BOM khác, xác định **vì sao** trước khi sửa.

## 26. Kiểm tra Gradle runtimeClasspath

Trong project Gradle lab:

```bash
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency azure-core \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-cloud-azure \
  --configuration runtimeClasspath
```

Trên Windows có thể dùng `gradlew.bat` theo shell thật.

`dependencyInsight` cho biết vì sao Gradle chọn version cụ thể và những constraints/requests liên quan.

### Lưu ý quan trọng

- `compileClasspath` và `runtimeClasspath` có thể khác nhau.
- Dependency constraints, platform và `enforcedPlatform` có semantics khác.
- `resolutionStrategy.force` có thể che xung đột thay vì giải quyết đúng.
- Test classpath không chứng minh production runtime sạch.
- Gradle dependency locking (khi được cấu hình) giúp ghi lại resolved versions, nhưng vẫn phải nâng khóa có chủ đích.
- Sau thay BOM, đọc lại graph thay vì chỉ nhìn build file.

**Không nên force một version Azure Core “cho hết warning”** nếu chưa kiểm tra compatibility với mọi Azure SDK trên classpath.

## 27. BOM import order và quản lý overrides

Trong Maven, parent/inherited dependencyManagement, direct entries và imported BOMs có các quy tắc precedence cụ thể; **nhiều imported BOMs có thể quản lý cùng artifact**.

Ví dụ dự án dùng:

```xml
<dependencyManagement>
    <dependencies>
        <!-- Spring Cloud BOM, nếu dùng components cần thiết -->
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>REPLACE_WITH_COMPATIBLE_CLOUD_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <!-- Spring Cloud Azure BOM -->
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>REPLACE_WITH_COMPATIBLE_SCA_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

**Không có một thứ tự đúng cho mọi tổ hợp release train**. Hãy bám theo hướng dẫn tương thích của bản Spring Cloud Azure/Spring Cloud đã chọn, rồi kiểm tra effective POM. Trong Maven, thứ tự của imported BOMs có thể quyết định version ở trường hợp trùng khai báo; các direct dependencyManagement entries cũng có ưu tiên tương ứng.

### Override có chủ đích

Đôi khi phải override một thư viện vì CVE hoặc yêu cầu SDK. Quy trình:

1. Xác nhận version mới thực sự sửa được vấn đề.
2. Xác định artifacts phụ thuộc API của nó.
3. Lập thử nghiệm tương thích (unit/integration/contract).
4. Viết ADR nêu lý do, owner, ngày hết hạn override.
5. Chỉ override phạm vi tối thiểu; không ép toàn bộ ecosystem.
6. Sau khi BOM được nâng, xóa override nếu không cần.
7. Tạo SBOM và security scan lại.

## 28. Multi-module Maven và tổ chức dependency management

Một repo có nhiều modules:

```text
company-parent
  |
  +-- api-gateway
  +-- order-api
  +-- billing-worker
  +-- notification-worker
```

Có thể đặt **dependencyManagement chung tại parent**:

```xml
<properties>
    <spring-cloud-azure.version>REPLACE_WITH_COMPATIBLE_SCA_VERSION</spring-cloud-azure.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Những modules chỉ thêm dependency cần thiết:

```xml
<!-- order-api: Blob Storage -->
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
</dependency>
```

Ưu điểm:

- Một điểm quản lý Spring Cloud Azure version.
- Không tạo 4 phiên bản Azure SDK khác nhau trong một repo.
- Dễ đánh giá upgrade toàn bộ platform.

Nhưng tránh **thêm starter vào dependencies của parent** khiến mọi child module vô tình kéo Azure clients dù không dùng. Đưa version vào parent dependencyManagement, còn dependency declaration theo **nhu cầu từng module**.

## 29. Gradle version catalog và convention plugins

Với Gradle multi-module, có thể dùng version catalog (ví dụ `gradle/libs.versions.toml` trong project học tập) và convention plugin để quản lý versions, plugins và dependency policies.

Ví dụ minh họa:

```toml
[versions]
spring-boot = "REPLACE_WITH_APPROVED_BOOT_VERSION"
spring-cloud-azure = "REPLACE_WITH_COMPATIBLE_SCA_VERSION"

[libraries]
spring-cloud-azure-bom = {
  module = "com.azure.spring:spring-cloud-azure-dependencies",
  version.ref = "spring-cloud-azure"
}
azure-blob-starter = {
  module = "com.azure.spring:spring-cloud-azure-starter-storage-blob"
}
```

Kết hợp trong Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation(platform(libs.spring.cloud.azure.bom))
    implementation(libs.azure.blob.starter)
}
```

**Đây là pattern cấu hình**, cần đồng bộ aliases với tên mà Gradle tạo accessor và convention plugins thật. Không phải mọi project có sẵn catalog; không thêm công cụ chỉ để tăng số tầng config cho ứng dụng nhỏ.

### Chính sách hữu ích

- Bản phát hành dependency được đề xuất qua PR và CI.
- Không dùng dynamic version `+` hoặc `latest.release` cho Production.
- Không thay BOM trên main branch không có validation.
- Nhận biết dependency được dùng qua transitive/auto-configuration.
- Có SBOM và repository access controls.

## 30. Ưu tiên security và supply-chain

Một bộ dependency tương thích vẫn có thể chứa vulnerabilities. Thiết kế vòng đời:

```text
Developer updates BOM / starter
            |
            v
Resolve effective classpath
            |
            v
SBOM + vulnerability/license scan
            |
            v
Unit + integration + authentication tests
            |
            v
Canary deployment
            |
            v
Monitor, approve or rollback
```

### Những điều cần kiểm tra

- Vulnerabilities trong Azure SDK/Spring Framework/Jackson/Reactor/Netty.
- Severity, **exploitation conditions** và mức ảnh hưởng thực của ứng dụng.
- Package provenance, artifact repositories và checksum/signature policies.
- Licenses và obligations.
- Version end-of-support.
- Thư viện transitive không còn được cập nhật.
- Dependency confusion và repository trust.
- Secrets vô tình được build vào artifact/image.

### Công cụ

Có thể dùng OWASP Dependency-Check, SCA platform của tổ chức, CycloneDX SBOM generation, Dependabot/Renovate hoặc giải pháp tương đương được phê duyệt. Công cụ có thể báo false positives; **không tự force version mới chỉ vì một CVE scanner gắn nhãn**. Hãy đánh giá fix, compatibility và regression.

## 31. Dependency lock và reproducible builds

Một build muốn tái lập cần kiểm soát:

1. Version Spring Boot và Spring Cloud Azure BOM.
2. Version plugins Maven/Gradle.
3. JDK/toolchain.
4. Dependency repositories và cache policy.
5. Không dùng dynamic/range versions ở Production.
6. Test dependencies và optional classifiers.
7. Generated code/annotation processors.
8. Gradle lockfiles hoặc cơ chế tương đương nếu có.
9. Container base image và runtime JDK version.
10. SBOM và build provenance.

**BOM không phải lockfile**. Một BOM quản lý rất nhiều versions, nhưng nếu dự án khai báo dependencies không nằm trong BOM, có dynamic versions hoặc resolution constraints, classpath vẫn có thể khác dự kiến.

### Maven và Gradle khác nhau

Maven thường dùng phiên bản được khai báo và resolution rules cụ thể, không có lockfile mặc định tương đương Gradle dependency locking. Không nên tuyên bố “import BOM nghĩa là build từ hôm nay đến năm sau chắc chắn giống nhau” khi repositories, plugins, metadata hay phạm vi dependencies còn thay đổi.

## 32. Unit test, integration test và cloud smoke test

Ba lớp kiểm thử:

| Lớp | Mục tiêu | Azure resource cần? |
|---|---|---|
| **Unit tests** | Kiểm tra logic nghiệp vụ và config binding/beans bằng mocks. | Thường không. |
| **Integration tests** | Kiểm tra SDK/client/serialization/auto-config với môi trường lab hoặc emulator phù hợp. | Tùy dịch vụ. |
| **Cloud smoke tests** | Kiểm tra identity, data-plane RBAC, DNS và tài nguyên thật sau deploy. | Có, môi trường đã phê duyệt. |

### Ví dụ unit test không gọi Azure

```java
package com.example.orders;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class OrderKeyTest {

    @Test
    void stableMessageIdIsDerivedFromBusinessOperation() {
        String orderId = "ORD-LAB-1042";
        String eventType = "OrderCreated";

        String messageId = eventType + ":" + orderId;

        assertEquals("OrderCreated:ORD-LAB-1042", messageId);
    }
}
```

Điểm cần kiểm thử thêm:

- Spring context tạo được Bean khi có cấu hình lab.
- Key Vault property source hoạt động dưới role đã cấp.
- Blob SDK đọc/ghi vào container lab theo permission.
- Service Bus sender/receiver với queue/test entity lab.
- Không leak credentials trong logs.
- Retry/idempotency và backoff.
- Cấu hình khác nhau giữa dev/staging/prod không nhầm endpoint.

### Emulator và test doubles

Azurite có thể giúp thử một số APIs Blob Storage, nhưng **không phải Azure Storage đầy đủ về auth, RBAC, networking và mọi tính năng**. Với Key Vault và các tích hợp khác, không giả định luôn có emulator tương đương Production. Dùng mock/stub cho unit tests, và **integration smoke tests trên resources thật được cấp phép** cho đường đi identity/network.

## 33. Spring Cloud Azure configuration và Spring profiles

Một cấu hình dùng profiles:

```yaml
# application.yml
spring:
  application:
    name: order-api

app:
  storage:
    container: ${APP_STORAGE_CONTAINER:documents-lab}
```

Trong `application-local.yml` có thể chỉ tới Azure lab resource, dùng developer identity **không chứa secrets**.

Trong `application-prod.yml` chỉ cấu hình tên tài nguyên/non-secret settings, còn identity lấy từ managed runtime. Tránh đặt access key trực tiếp trong profile vì file này dễ đi vào JAR hoặc repository.

**Không dùng Spring profile như security boundary.** Nếu người dùng vô tình chạy profile `prod` trên máy cá nhân nhưng có credential production, dữ liệu vẫn có thể bị truy cập. IAM/network controls phải độc lập với profile.

### Configuration validation

Có thể tạo `@ConfigurationProperties` với validation để phát hiện thiếu `container` hoặc namespace ngay khi startup. Tuy nhiên, property có string non-empty vẫn chưa chứng minh Azure resource tồn tại hay permission hợp lệ.

## 34. Kết nối mạng, private endpoints và DNS

Dependency đúng không giải quyết được lỗi mạng. Một ứng dụng Spring Boot trên Azure có thể sử dụng:

```text
Spring Boot runtime (VNet-integrated)
    |
    +-- DNS resolves Key Vault private endpoint
    |
    +-- DNS resolves Blob Storage private endpoint
    |
    +-- Azure Service Bus namespace/AMQP connectivity
    |
    +-- Entra identity token endpoint as supported
```

Kiểm tra:

- Service có Private Endpoint/private access theo tier/region không?
- VNet/subnet/NSG/UDR/Azure Firewall có cho phép đúng traffic?
- Private DNS zones liên kết đúng VNet và endpoint?
- Hostname/FQDN và certificate/TLS validation đúng?
- Service Bus transport dùng AMQP/TLS hoặc WebSockets theo cấu hình và mạng?
- Proxy/environment có chặn outbound identity/token calls?
- Staging và Production có khác DNS không?
- Service endpoint/firewall policy có cho identity/resource network thực sự truy cập?
- Timeout do network hay do quota/busy server?
- Logs có vô tình chứa SAS token/connection string không?

**Đừng thay Azure SDK version để sửa một DNS không phân giải được**; và đừng mở firewall toàn Internet để che lỗi cấu hình.

## 35. Startup và secret refresh: thiết kế đúng vòng đời

Một số Azure dependencies/configuration sources được khởi tạo **ngay khi Spring ApplicationContext start**.

```text
Spring Boot startup
     |
     v
Resolve property sources (local/env/Key Vault/App Config)
     |
     v
Bind properties and create beans
     |
     v
Start service
```

Rủi ro:

- Key Vault tạm lỗi khiến ứng dụng không khởi động.
- Role assignment chưa kịp propagate, gặp 403.
- Property source priority không như mong muốn.
- Secret mới rotate nhưng Bean cũ vẫn giữ giá trị trước đó.
- Một client tạo lúc startup đọc namespace sai.
- Dùng refresh không đồng bộ cho config đang cần atomic transition.

### Cách xử lý

1. Phân loại config **bắt buộc** và **tùy chọn**.
2. Giới hạn timeout và retry tại startup.
3. Chọn failure policy rõ ràng.
4. Thiết kế secret rotation/restart hoặc refresh được hỗ trợ.
5. Không để cached credentials vô hạn sau khi quyền đã bị thu hồi.
6. Test cold start khi Key Vault/App Configuration không khả dụng.
7. Theo dõi startup latency và config retrieval failures.
8. Có rollback khi một config update phá schema.

**Không mặc định starter tự refresh mọi `@Value`/singleton bean** sau rotation. Xác minh semantics chính thức của phiên bản sử dụng.

## 36. Observability, health và telemetry dependencies

Spring Boot Actuator có thể cung cấp health/metrics, nhưng cần cẩn trọng khi công bố endpoints và tạo probes.

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Phần tích hợp Azure Monitor/Application Insights/OTel có libraries, instrumentation và cách cấu hình khác theo version/runtime. Chọn một pipeline observability nhất quán thay vì cài cùng lúc nhiều agents tạo duplicate spans.

Các tín hiệu cần đo:

| Tín hiệu | Vì sao cần |
|---|---|
| Boot startup success/failure | Dependency/Bean/config errors. |
| Azure credential failure count | Identity hoặc token chain vấn đề. |
| Key Vault lookup latency/failures | Có ảnh hưởng startup/runtime không? |
| Blob operations p95/403/404/429 | Storage performance và RBAC. |
| Service Bus send/receive errors | Delivery và namespace/network. |
| JVM heap/threads/GC | Azure client và backend performance. |
| Retry counts/throttling | Quota/capacity và cost. |
| Deployment/build metadata | Truy vết BOM/SDK/version. |
| Security alerts | Credentials/log leaks/vulnerability status. |
| Cost per request/outcome | Quản trị ngân sách. |

**Không mở public `/actuator/env`, `/actuator/beans` hoặc các endpoints nhạy cảm**; chỉ expose những endpoints cần và có authentication/authorization. Metrics labels cũng không nên chứa PII hoặc raw connection strings.

## 37. Tối ưu dependency footprint và chi phí runtime

Thêm nhiều starters không chỉ tăng JAR size; có thể ảnh hưởng:

- Thời gian startup/cold start.
- Số classes và memory footprint.
- Auto-configuration evaluation.
- Số Bean/threads/HTTP clients.
- Container image build và vulnerability surface.
- CI dependency download/cache.
- AOT/native-image compatibility nếu sản phẩm sử dụng.
- Khả năng debug và số lượng library versions phải duy trì.

Nhưng **loại bỏ dependency theo cảm tính** có thể làm mất runtime class được load bằng reflection hoặc Spring autoconfig metadata. Dùng dependency analysis **kết hợp tests** trước khi xóa.

### Tránh tối ưu sai

Một ứng dụng đọc Blob 100 lần/ngày không cần tự viết lại SDK HTTP pipeline để cắt vài MB JAR nếu starter làm rõ credential/config và đã được support tốt. Ngược lại, một Lambda-like short-lived function với cold-start SLO nghiêm ngặt có thể hưởng lợi từ việc chỉ kéo SDK tối thiểu.

Chọn theo **đo lường**, không theo số lượng dependencies.

## 38. Lỗi thường gặp: xung đột Azure Core/Reactor

**Triệu chứng:** sau khi thêm Service Bus và Blob, ứng dụng báo `NoSuchMethodError` trong `com.azure.core.*` hoặc `reactor.*`.

### Điều tra

1. Ghi stacktrace và phiên bản Spring Boot/Spring Cloud Azure.
2. Kiểm tra effective POM/dependency tree hoặc Gradle runtimeClasspath.
3. Xác định Azure Core, Identity, Netty/Reactor versions đã resolve.
4. Tìm direct SDK versions hoặc `resolutionStrategy.force`.
5. Kiểm tra có thêm Spring Cloud Azure starter **khác major** không.
6. Kiểm tra một BOM khác có override Azure artifacts không.
7. Xác minh official compatibility matrix.
8. Nếu issue bắt đầu từ PR nâng dependency, so graph trước/sau.
9. Kiểm tra packaged JAR/image đã đúng build mới không.
10. Chạy regression integration tests trên đúng JDK/runtime.

### Khắc phục

- Đưa starters về cùng release/BOM được hỗ trợ.
- Loại bỏ overrides không cần thiết.
- Nếu bắt buộc override vì CVE, chọn version có bằng chứng tương thích.
- Đổi release train theo hướng dẫn migration, không chỉ nâng một JAR lẻ.
- Có canary và rollback.

**Không giải bằng `mvn clean` một cách máy móc rồi tuyên bố hết lỗi**. Clean chỉ loại bỏ build artifacts, không sửa dependency graph sai.

## 39. Lỗi thường gặp: Key Vault startup 403

**Triệu chứng:**

```text
Failed to resolve Key Vault property source
403 Forbidden
```

### Trình tự

1. Xác minh Spring Cloud Azure Key Vault Secrets starter đúng version.
2. Kiểm tra Vault endpoint/URI và active profile.
3. Xác định principal thực tế của ứng dụng (managed identity hay developer).
4. Vault dùng Azure RBAC hay access policies theo cấu hình?
5. Principal có quyền **read secret** đúng scope?
6. Có policy/firewall/Private Endpoint ngăn data plane?
7. Secret có tồn tại/được bật/đúng tên và version?
8. Role mới gán đã propagate chưa?
9. Property-source naming/ordering có đúng với starter version?
10. Logs có vô tình in giá trị secret không?

### Khắc phục

- Cấp đúng quyền tối thiểu sau phê duyệt.
- Sửa endpoint/DNS/network nếu lỗi kết nối.
- Đồng bộ naming và configuration property.
- Kiểm tra lại startup trong lab/staging.
- Không fallback sang hard-coded secret trong source.

**403 không mặc nhiên là lỗi dependency**. Version alignment vẫn nên được xác minh, nhưng ưu tiên evidence từ identity/RBAC.

## 40. Lỗi thường gặp: Service Bus client kết nối nhưng không gửi được

**Triệu chứng:** Spring context start thành công nhưng request publish `OrderCreated` bị từ chối hoặc timeout.

### Điều tra

1. Namespace và queue/topic name có đúng không?
2. Sử dụng base starter, JMS, Integration hay Stream binder?
3. Principal có role **Azure Service Bus Data Sender**?
4. Service Bus namespace có policy/firewall phù hợp?
5. AMQP/TLS/network egress hoặc WebSocket transport có được cấu hình đúng?
6. Entity có bị disable, quota/capacity vượt ngưỡng?
7. SDK retry policy có backoff hợp lý?
8. Exception/status là authentication, authorization, network hay busy?
9. MessageId và business idempotency đã ổn định chưa?
10. Có thể test với một queue/entity lab không?

### Khắc phục

- Phân biệt lỗi Transport và permission.
- Điều chỉnh namespace/entity, role, networking theo bằng chứng.
- Retry có giới hạn, tránh nhân bản business event.
- Không phát message thật trong unit test.
- Theo dõi Send success và downstream processing riêng.

## 41. Nâng cấp Spring Boot / Spring Cloud Azure an toàn

Một major/minor upgrade có thể tác động:

- Java baseline, Spring Framework/Jakarta APIs.
- Spring Boot auto-configuration metadata.
- Spring Cloud release train compatibility.
- Azure SDK HTTP/Identity dependencies.
- Property names, default values và client beans.
- Key Vault configuration loading/refresh.
- Service Bus integration APIs.
- Test annotations/lifecycle.
- Observability và Spring Actuator.
- Security permissions không đổi nhưng authentication behavior đổi.
- Container base image/runtime.

### Runbook nâng cấp

1. Chụp lại versions hiện tại và dependency tree.
2. Tìm compatibility matrix/release notes của target line.
3. Chọn Boot/Spring Cloud/Spring Cloud Azure versions đồng bộ.
4. Cập nhật BOM/plugin versions trong một PR có scope rõ.
5. Di chuyển properties đã deprecated/renamed.
6. Dọn direct SDK overrides chỉ khi có bằng chứng.
7. Chạy compile/unit/integration tests trên JDK target.
8. Kiểm thử managed identity, Key Vault, Blob, Service Bus trong staging.
9. So startup latency, 429, 403, memory và throughput.
10. Tạo SBOM, security/license scan.
11. Triển khai canary, quan sát và rollback nếu regression.
12. Ghi ADR/version inventory để team sau biết lý do.

**Không nâng đồng thời Spring Boot major + tất cả Azure starters + cấu hình network mà không có kế hoạch phân biệt nguyên nhân lỗi.**

## 42. Chuyển từ starters cũ hoặc Azure SDK tự quản sang Spring Cloud Azure

Trong các dự án lâu năm có thể gặp:

- Artifact coordinates/namespace của thế hệ Spring Cloud Azure cũ.
- Azure Spring Boot starter packages đời trước.
- Direct SDK dependencies đã pin từng version.
- Spring Boot 2.x/Java 8/11 và Spring Boot 3.x/Jakarta migration.
- Code tạo clients bằng connection strings.
- Service Bus JMS/binder code từ một integration khác.

### Phương pháp migration

1. Liệt kê **thư viện và purpose hiện tại**, không chỉ tên artifact.
2. Chọn target Spring Boot/Cloud/Azure line được hỗ trợ.
3. Đọc official migration notes của đúng cặp versions.
4. Đổi coordinates khi release thực sự yêu cầu.
5. Import BOM và bỏ versions lẻ đã được BOM quản lý.
6. Thay connection strings bằng identity/passwordless ở nơi hỗ trợ.
7. Chỉnh property keys và Spring bean injection theo API mới.
8. Test message semantics, concurrency, retry và secret refresh.
9. Kiểm tra runtime classpath không còn cả starter cũ và mới chồng lấn.
10. Đẩy lên staging và quan sát trước Production.

Không thực hiện “find-replace artifact name” rồi mặc định toàn bộ logic JMS/Stream/Storage đã tương thích.

## 43. Bài thực hành: thêm BOM và hai starters đúng cách

**Bối cảnh:** đội phát triển có project Spring Boot `order-api-lab` chưa tích hợp Azure. Cần đọc một Key Vault secret của lab và tạo Blob Storage client; bài tập kiểm tra cả classpath và quyền truy cập.

### Môi trường giả lập

| Thành phần | Giá trị |
|---|---|
| Java | JDK được hỗ trợ bởi cặp release đã chọn. |
| Spring Boot | Version được xác nhận trong compatibility matrix. |
| Spring Cloud Azure | Version tương thích với Boot/Cloud. |
| Build | Maven hoặc Gradle, chọn một. |
| Key Vault | `kv-orders-lab`, dữ liệu không nhạy cảm thật. |
| Storage account | `storderslabexample` (phải thay tên thực nếu dùng Azure). |
| Blob container | `documents-lab`. |
| Identity local | Developer principal được cấp quyền lab. |
| Identity cloud | Managed identity/user-assigned identity được cấp quyền. |
| Không làm | Không ghi connection strings/keys vào source, không sửa Production. |

### Các nhiệm vụ

1. Ghi ra version của Java, Spring Boot, Spring Cloud (nếu dùng) và Spring Cloud Azure sẽ chọn.
2. Tra compatibility matrix và ghi **bằng chứng** vì sao chúng đi với nhau.
3. Import `spring-cloud-azure-dependencies` trong dependencyManagement hoặc Gradle platform/plugin.
4. Thêm `spring-cloud-azure-starter-keyvault-secrets` không gắn version lẻ.
5. Thêm `spring-cloud-azure-starter-storage-blob` không gắn version lẻ.
6. Chỉ thêm `spring-cloud-azure-starter-servicebus` nếu bài lab mở rộng cần message queue.
7. Xem effective POM hoặc Gradle runtimeClasspath, ghi resolved Azure SDK versions.
8. Kiểm tra có artifact nào bị override không mong muốn.
9. Đặt vault endpoint/account name bằng config/env theo starter version.
10. Xác thực developer bằng identity được phép; không tạo secret trong code.
11. Cấp đúng Key Vault Secrets Reader/User theo yêu cầu data plane của lab.
12. Cấp Storage Blob Data Reader/Contributor tùy thao tác.
13. Chạy Spring context smoke test trong project lab.
14. Kiểm tra Blob SDK Bean/Client có được tạo đúng không.
15. Thử đọc Key Vault secret lab không chứa dữ liệu nhạy cảm.
16. Thử một Blob operation an toàn theo role đã cấp.
17. Bỏ quyền data plane có chủ đích trên môi trường lab, kiểm tra lỗi 403 và phân biệt với dependency errors.
18. Thử đặt account/endpoint sai, nhận diện lỗi resource/network.
19. Thêm direct Azure SDK version không tương thích vào branch thử nghiệm có kiểm soát, quan sát dependency graph; **không cố ý phát tán CVE/vuln artifact**.
20. Khôi phục alignment qua BOM và chạy lại tests.
21. Tạo SBOM/report library versions.
22. Viết runbook startup 403 và NoSuchMethodError.
23. Tính chi phí môi trường lab gồm Key Vault, Storage, compute, logging nếu có.
24. Dọn lab resources theo quyền; không xóa tài nguyên dùng chung.

### Kết quả cần bàn giao

- Một `pom.xml` hoặc `build.gradle(.kts)` có BOM và starters tối thiểu.
- Version matrix có nguồn và người duyệt.
- Dependency tree/effective POM hoặc Gradle dependencyInsight.
- Cấu hình không chứa keys/secrets.
- Unit/context smoke tests và integration test evidence.
- Kết quả thử 403 chứng minh phân biệt RBAC vs dependency.
- SBOM và danh sách overrides có lý do.
- Checklist security, logging và budget.

## 44. Bài tập phân tích lỗi thực tế

**Tình huống A:** `mvn dependency:tree` cho thấy `spring-cloud-azure-starter-storage-blob` từ một BOM, nhưng một module con khai báo `azure-core` version khác.

Hỏi: sửa thế nào?

**Định hướng:** xác định direct override và version đã resolve, so với BOM được hỗ trợ. Không ép `azure-core` lên bản “mới nhất”; cập nhật đồng bộ, kiểm thử và ghi lý do.

**Tình huống B:** ứng dụng có đủ dependency nhưng báo `No qualifying bean of type BlobServiceClient`.

**Định hướng:** kiểm tra starter thực trên runtime classpath, conditions report, config binding, custom Bean, version alignment, profile. Chỉ sau khi Bean xuất hiện mới kiểm tra storage data plane.

**Tình huống C:** Bean tồn tại, Blob read trả 403.

**Định hướng:** đây có thể là quyền data plane hoặc auth, không chỉ dependency. Kiểm tra principal, role, scope, account và network.

**Tình huống D:** Key Vault secret rotate nhưng `@Value` trong singleton Bean vẫn giữ giá trị cũ.

**Định hướng:** kiểm tra refresh contract, lifecycle, caching và ứng dụng có cần restart/rebind/refresh event theo phiên bản hay không.

**Tình huống E:** dùng Spring Cloud Stream binder nhưng thêm base Service Bus starter rồi tìm không thấy binder.

**Định hướng:** chọn đúng integration artifact/binder, Spring Cloud release train, bindings config và compatibility. Không coi tất cả Service Bus starters là hoán đổi.

**Tình huống F:** chuyển từ Spring Boot cũ sang mới bằng cách chỉ thay Boot parent.

**Định hướng:** lập kế hoạch nâng Spring Cloud/Spring Cloud Azure cùng JDK/framework, migration properties, compile/integration/security tests và rollback.

## 45. Checklist trước Production

**Dependency và versioning**

- [ ] Spring Boot/Cloud/Azure/JDK versions đã được xác nhận tương thích.
- [ ] Có một nguồn quản lý Azure artifact versions bằng BOM phù hợp.
- [ ] Không pin version riêng cho starter nếu không có lý do.
- [ ] Không dùng dynamic versions hoặc `latest.release` trên Production.
- [ ] Dependency tree/effective POM đã được review.
- [ ] Không có starter cũ và mới chồng lấn.
- [ ] Không có unused starters tạo auto-config ngoài ý muốn.
- [ ] Mọi exclusions/overrides có ADR và tests.
- [ ] Có SBOM, vulnerability/license scan và upgrade cadence.
- [ ] JDK, build plugins, container image được version hóa.

**Identity và configuration**

- [ ] Không có connection strings/keys trong source, Git hoặc logs.
- [ ] Managed identity/workload identity và data-plane roles đúng scope.
- [ ] Key Vault/property source được cấu hình theo version thật.
- [ ] Config precedence/secret refresh được kiểm thử.
- [ ] Không nhầm dev/staging/prod resources.
- [ ] Storage/Service Bus/App Config endpoints được xác minh.
- [ ] Private DNS/TLS/networking đã kiểm tra từ runtime thật.
- [ ] Client Beans rõ ràng khi có nhiều accounts/namespaces.
- [ ] Spring Actuator/diagnostics nhạy cảm không mở public.

**Chất lượng và vận hành**

- [ ] Build/unit/context smoke/integration tests PASS trên JDK target.
- [ ] Cloud smoke tests xác thực identity/data plane thực.
- [ ] Retry/backoff/idempotency có chủ đích.
- [ ] Observability theo dõi 403, 429, latency, startup và build versions.
- [ ] Canary/rollback đã thử khi nâng BOM major/minor.
- [ ] Có runbook cho linkage, config, identity và network errors.
- [ ] Có budget/quota alerts và ownership rõ cho Azure resources.
- [ ] Không tuyên bố BOM tự giải quyết vấn đề bảo mật và nghiệp vụ.

## 46. Câu hỏi tự kiểm tra

**Câu 1.** Spring Cloud Azure BOM có phải một client thư viện dùng ở runtime không?

**Đáp án:** Không. BOM quản lý versions, không tự thêm Azure service dependency nếu không có declaration thực.

**Câu 2.** Vì sao nên dùng `spring-cloud-azure-dependencies`?

**Đáp án:** Để align versions giữa Spring Cloud Azure artifacts và những Azure SDK dependencies được BOM quản lý theo release.

**Câu 3.** Có thể import BOM rồi bỏ qua việc thêm starter Blob không?

**Đáp án:** Không. BOM chỉ quản lý version; phải thêm starter hoặc SDK trực tiếp nếu cần Blob.

**Câu 4.** Spring Boot BOM và Spring Cloud Azure BOM có giống nhau không?

**Đáp án:** Không. Chúng quản lý những tập artifacts khác nhau; cần tương thích.

**Câu 5.** Vì sao không chọn mọi dependency ở version mới nhất riêng lẻ?

**Đáp án:** Các thư viện có API/ABI và transitive dependencies cần tương thích, nên trộn tùy ý có thể gây linkage errors.

**Câu 6.** Khi nào cần thêm Spring Cloud BOM?

**Đáp án:** Khi dùng các Spring Cloud components và release train tương ứng, theo compatibility matrix với Boot/Spring Cloud Azure.

**Câu 7.** Maven `dependencyManagement` có tự tải tất cả dependencies không?

**Đáp án:** Không. Nó chỉ quản lý cách resolve khi dependency được khai báo hoặc kéo transitive.

**Câu 8.** Artifact groupId của Spring Cloud Azure BOM là gì?

**Đáp án:** `com.azure.spring`, artifactId `spring-cloud-azure-dependencies`.

**Câu 9.** Vì sao không đặt version vào mỗi Azure starter nếu BOM quản lý?

**Đáp án:** Tránh override không chủ đích và giữ một tập version nhất quán.

**Câu 10.** Lệnh Maven nào giúp xem version graph?

**Đáp án:** `mvn dependency:tree`; dùng `mvn help:effective-pom` để xem dependency management sau inheritance.

**Câu 11.** Với Gradle, lệnh nào tìm lý do chọn version `azure-core`?

**Đáp án:** `dependencyInsight --dependency azure-core --configuration runtimeClasspath`.

**Câu 12.** Gradle `platform(...)` và plugin `io.spring.dependency-management` có hoàn toàn đồng nhất không?

**Đáp án:** Không. Cơ chế constraints/precedence khác nhau; cần kiểm tra resolved graph.

**Câu 13.** Thêm Key Vault starter có tự cho ứng dụng đọc mọi secret không?

**Đáp án:** Không. Cần endpoint, identity, data-plane permissions và networking phù hợp.

**Câu 14.** Vì sao lỗi 403 không tự động được sửa bằng nâng BOM?

**Đáp án:** 403 thường liên quan authentication/authorization/permission hoặc policy của dịch vụ, không nhất thiết là Java linkage.

**Câu 15.** Có thể dùng Developer Azure CLI identity trong local lab không?

**Đáp án:** Có khi được phép và credential chain hỗ trợ; Production nên sử dụng managed/workload identity được cấu hình rõ.

**Câu 16.** `NoSuchMethodError` thường gợi ý điều gì?

**Đáp án:** API/ABI mismatch giữa phiên bản đã compile và runtime, thường do classpath/transitive conflict.

**Câu 17.** Thêm Base Service Bus starter đã tương đương JMS starter chưa?

**Đáp án:** Chưa. JMS, Integration và Spring Cloud Stream có contracts/artifacts riêng.

**Câu 18.** Một Bean `BlobServiceClient` tồn tại có chứng minh upload Blob được phép không?

**Đáp án:** Không. Cần data-plane role, account/container đúng và kết nối mạng.

**Câu 19.** Vì sao dùng managed identity không đồng nghĩa có mọi quyền Azure?

**Đáp án:** Identity phải được gán RBAC/data-plane roles đúng resource/scope.

**Câu 20.** App Configuration và Key Vault nên dùng giống nhau cho mọi loại config không?

**Đáp án:** Không. App Configuration phù hợp non-secret settings/feature flags; Key Vault tập trung secrets/keys/certificates.

**Câu 21.** Key Vault secret rotate có tự cập nhật mọi singleton Bean không?

**Đáp án:** Không nên giả định. Phải kiểm tra refresh semantics và Bean lifecycle theo starter version.

**Câu 22.** Có nên đưa connection string vào `application-prod.yml` để tránh lỗi identity?

**Đáp án:** Không. Ưu tiên managed identity/Key Vault và giải quyết nguyên nhân RBAC/network.

**Câu 23.** Vì sao cần kiểm tra `runtimeClasspath` chứ không chỉ `compileClasspath`?

**Đáp án:** Versions/classes ở runtime có thể khác compile classpath; linkage errors xuất hiện khi chạy.

**Câu 24.** BOM có phải lockfile đảm bảo build luôn tái lập tuyệt đối không?

**Đáp án:** Không. Build còn phụ thuộc plugins, repositories, constraints và dependency declarations khác.

**Câu 25.** Khi một CVE xuất hiện ở Azure SDK transitive, có nên `force` phiên bản bất kỳ để qua scan không?

**Đáp án:** Không. Cần đánh giá remediation, compatibility và kiểm thử.

**Câu 26.** Vì sao không thêm mọi Azure starter trong parent dependencies của multi-module repo?

**Đáp án:** Làm mọi module kéo libraries/auto-config không cần thiết; nên quản lý versions ở parent, khai báo starter tại module dùng thật.

**Câu 27.** Unit test có đủ chứng minh managed identity hoạt động trong Azure runtime không?

**Đáp án:** Không. Cần cloud smoke/integration test dưới identity và network môi trường thật.

**Câu 28.** Thêm Blob starter có tạo Azure Storage account không?

**Đáp án:** Không. Resource provisioning, RBAC, networking và chi phí phải quản lý riêng.

**Câu 29.** Vì sao cần canary khi nâng Spring Cloud Azure release train?

**Đáp án:** Auto-configuration, property names, SDK behavior và latency có thể thay đổi dù compile/tests ở lab PASS.

**Câu 30.** Nguyên tắc cốt lõi để quản lý dependency bằng Spring Cloud Azure là gì?

**Đáp án:** **Chọn tổ hợp Java/Spring Boot/Spring Cloud/Spring Cloud Azure được hỗ trợ, import BOM, thêm đúng starters/SDK tối thiểu, đọc resolved dependency graph, kiểm thử identity/RBAC/network và nâng cấp có kiểm soát.**

**Tóm lại:** **Spring Cloud Azure** giúp Spring Boot tích hợp với Azure qua starters và BOM `spring-cloud-azure-dependencies`. BOM giúp quản lý versions, nhưng **không thay thế compatibility matrix, kiểm tra classpath, cấu hình Azure resources hay data-plane authorization**. Một triển khai đáng tin phải quản lý đầy đủ **Java/Spring Boot/Cloud/Azure SDK alignment, Maven/Gradle resolution, managed identity/Key Vault, test/CI, SBOM/security scan, observability và runbook migration**. Khi phân biệt được **lỗi dependency với lỗi cấu hình, quyền và mạng**, đội phát triển có thể triển khai ứng dụng Spring Boot lên Azure an toàn, dễ nâng cấp và kiểm soát được chi phí.
