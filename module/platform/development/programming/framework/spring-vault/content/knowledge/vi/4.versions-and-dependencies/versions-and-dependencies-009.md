# Khóa phiên bản và kiểm tra dependency bắc cầu

Trong một ứng dụng Java sử dụng **Spring Vault** để đọc KV secrets qua `VaultTemplate`, đăng nhập HashiCorp Vault bằng workload identity, quản lý token/lease hoặc gọi Transit encryption và PKI, việc viết `spring-vault-core:4.1.2` trong file build **chưa bảo đảm** runtime có một bộ thư viện đúng và an toàn. `spring-vault-core` còn phụ thuộc Spring Framework, HTTP client, JSON mapper và có thể cùng xuất hiện với Spring Cloud Vault, Reactor, Spring Data hay SDK xác thực cloud. Mỗi thư viện có đồ thị phụ thuộc riêng; một BOM, bản override hoặc rule giải quyết xung đột có thể làm phiên bản cuối cùng khác phiên bản lập trình viên nghĩ mình đã chọn.

**Chương:** Phiên bản và phụ thuộc. Bài này tập trung vào **khóa phiên bản (version pinning/locking) và kiểm tra dependency bắc cầu** khi triển khai SPRING_VAULT. Bạn sẽ học cách phân biệt dependency trực tiếp và bắc cầu, dùng Maven BOM/Enforcer hoặc Gradle platform/lockfile, xem bản đã resolve, kiểm tra patch bảo mật và đưa việc xác minh vào CI.

> **Mốc đối chiếu: 25/11/2026.** Các ví dụ minh họa dùng Spring Boot **4.2.0**, Spring Cloud release train **2026.0.0**, Spring Cloud Vault **5.1.0** và bản vá Spring Vault Core **4.1.2**. Đó là **bốn nhãn phiên bản khác nhau**, không phải phiên bản của cùng một artifact. Spring đã công bố vá CVE-2026-41698 ở Spring Vault **4.0.5 và 4.1.2** ngày 19/11/2026. Luôn xác nhận bản được resolve thực tế, chứ không suy phiên bản Core chỉ từ tên release train.

## 1. Dependency trực tiếp, bắc cầu và BOM không giống nhau

### 1.1. Đường đi từ starter đến Core

Đồ thị dưới đây là **sơ đồ khái niệm**, không phải cây phụ thuộc thực tế của một bản build cụ thể:

```text
Ứng dụng Spring Boot
  │
  ├── Spring Boot parent/BOM
  │      └── quản lý Spring Framework, Jackson, Reactor, HTTP client...
  │
  ├── Spring Cloud BOM (release train)
  │      └── quản lý Spring Cloud Vault, Commons, Config...
  │
  ├── spring-cloud-starter-vault-config           [direct]
  │      └── spring-cloud-vault-config            [transitive]
  │             └── spring-vault-core             [transitive]
  │                    └── spring-web và các thư viện nền
  │
  ├── spring-webflux                              [chỉ khi dùng reactive]
  ├── spring-data-keyvalue                        [chỉ khi dùng repository]
  ├── tools.jackson.core:jackson-databind         [khi cần JSON mapper]
  └── cloud SDK                                   [theo phương thức auth]
```

**Dependency trực tiếp** là artifact khai báo trong `dependencies` của ứng dụng. **Dependency bắc cầu** được kéo vào vì một artifact khác khai báo nó. **BOM** (`Bill of Materials`) chọn/quản lý phiên bản cho một nhóm artifact nhưng **không tự thêm artifact vào classpath** chỉ vì được import.

Ví dụ khi khai báo `spring-cloud-starter-vault-config`, `spring-vault-core` thường đến theo quan hệ bắc cầu. Không cần khai báo thêm một Core với phiên bản ngẫu nhiên chỉ để có `VaultTemplate`. Ngược lại, nếu chỉ dùng `spring-vault-core` thì **không có** cơ chế `spring.config.import: "vault://"` của Spring Cloud Vault chỉ nhờ Core.

### 1.2. Khái niệm nào thực sự “khóa” phiên bản?

| Cơ chế | Tác dụng | Điều **không** bảo đảm |
| --- | --- | --- |
| Phiên bản trực tiếp, ví dụ `spring-vault-core:4.1.2` | Nêu một yêu cầu phiên bản cụ thể | Không tự khóa toàn bộ dependency bắc cầu |
| Maven `dependencyManagement` / BOM | Điều phối phiên bản theo chính sách dự án | Không tạo lockfile đầy đủ và bất biến cho toàn bộ đồ thị |
| Gradle `platform(...)` / dependency constraints | Đưa ràng buộc phiên bản vào thuật toán resolve | Không tự lưu chính xác mọi dependency bắc cầu qua các lần build |
| Gradle `dependencyLocking` | Lưu các phiên bản đã resolve theo configuration vào `gradle.lockfile` | Không xác minh checksum hoặc tính an toàn của JAR |
| Gradle `verification-metadata.xml` | Xác minh checksum/chữ ký artifact | Không quyết định bản vá CVE nào cần áp dụng |
| Maven Enforcer | Có thể chặn các đồ thị phụ thuộc không hội tụ/không đúng upper bound | Không thay thế phân tích CVE, API compatibility hoặc kiểm thử Vault |
| Dependency tree, SBOM, báo cáo scan | Cho biết cái gì thực sự có mặt và rủi ro được nhận diện | Một báo cáo đúng không tự cập nhật dependency |

**Nguyên tắc:** `BOM = chính sách phiên bản`, `lockfile = bản chụp phiên bản đã resolve`, `checksum/signature = kiểm tra artifact tải về`, `advisory/SBOM = dữ liệu đánh giá bảo mật`. Không thay một cơ chế bằng cơ chế khác.

Nguồn: [Maven – Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html), [Spring Boot – Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html), [Gradle – Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html).

## 2. Chọn cả “bộ phiên bản”, không chọn Spring Vault độc lập

| Ứng dụng | Bộ Spring nên đối chiếu | Câu hỏi trước khi khóa |
| --- | --- | --- |
| Spring Framework thuần, dùng `VaultTemplate` | Spring Framework **7.x** + Spring Vault **4.1.x** (hoặc thế hệ tương thích khác) | Java, Jackson, HTTP client đã đồng bộ? |
| Spring Boot **4.2.x** + Cloud Vault starter | Spring Cloud **2026.0.x**, Spring Cloud Vault **5.1.x** | Core thực sự là **4.1.2 trở lên trong nhánh đã vá** hay bản cũ hơn? |
| Spring Boot **4.0.x / 4.1.x** + Cloud Vault starter | Spring Cloud **2025.1.x** (ví dụ **2025.1.5**), Cloud Vault **5.0.x** | Core 4.0.x đang resolve patch nào? |
| Spring Boot **3.5.x** / Framework **6.2.x** | Spring Vault **3.2.x** và Cloud release train phù hợp thế hệ Boot 3.5 | Dòng hỗ trợ nguồn mở và bản vá bảo mật còn khả dụng không? |
| Nền Java 17 nhưng chưa nâng Framework 7 | Không chọn Spring Vault 4.x chỉ dựa vào JDK | Phải nâng Framework/Boot hoặc giữ dòng Vault 3.x tương thích |

Ví dụ **Spring Cloud 2026.0.0** công bố Spring Cloud Vault **5.1.0** và thông báo nâng nền lên dòng Spring Vault **4.1**; việc đó **không nói lên Core patch 4.1.2** đang nằm trong từng bản build. Cùng ngày 20/11/2026, release train **2025.1.5** công bố Spring Cloud Vault **5.0.4** và tương thích Boot **4.0.x/4.1.x**. Không ghép Cloud 2026.0.0 với Boot 4.1 chỉ vì đó là train mới hơn.

Trong môi trường production, **cùng tương thích không có nghĩa cùng được hỗ trợ bảo mật**. Với dự án cũ, phải xem chính sách support và advisory của từng thế hệ, kể cả trường hợp bản vá 3.x chỉ có theo kênh thương mại. Không tự ép Core 4.1 vào Boot 3.x/Framework 6.x để sửa CVE.

Nguồn: [Spring Cloud – Compatibility](https://spring.io/projects/spring-cloud/), [Cloud 2026.0.0 GA](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/), [Cloud 2025.1.5 GA](https://spring.io/blog/2026/11/20/spring-cloud-2025-1-5-has-been-released/).

## 3. Maven: quản lý phiên bản bằng Boot parent, Cloud BOM và dependencyManagement

### 3.1. Ví dụ ứng dụng dùng Spring Cloud Vault

Trong ví dụ sau, **Spring Boot parent 4.2.0** quản lý nền thư viện; **Spring Cloud BOM 2026.0.0** quản lý các module Cloud; một mục `dependencyManagement` của **ứng dụng** chọn Spring Vault Core **4.1.2** do yêu cầu bản vá đã công bố.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.2.0</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>orders-vault-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencyManagement>
    <dependencies>
      <!-- Chỉ giữ override khi BOM chưa chọn bản Core đã vá;
           xác minh bằng dependency:tree và integration test. -->
      <dependency>
        <groupId>org.springframework.vault</groupId>
        <artifactId>spring-vault-core</artifactId>
        <version>4.1.2</version>
      </dependency>

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
</project>
```

**Phân biệt ba vị trí:**

- `<parent>` kế thừa cả plugin/build configuration và dependency management của Spring Boot.
- `<dependencyManagement>` quản lý phiên bản (và có thể một số thuộc tính khác) cho dependency được dùng trực tiếp hoặc bắc cầu. Đặt Core ở đây **không tự thêm Core** nếu chưa có đường phụ thuộc đến nó; trong ví dụ starter Cloud Vault thường kéo Core.
- `<dependencies>` thực sự thêm starter. Phiên bản starter được Spring Cloud BOM chọn nên không cần ghi một số thủ công cho `spring-cloud-starter-vault-config`.

**Override 4.1.2 là ví dụ có điều kiện, không phải mặc định bất biến.** Nếu một bản BOM mới đã quản lý Core với bản vá phù hợp, nên bỏ override, xây dựng lại và kiểm tra cây phụ thuộc. Khi override Core, vẫn phải test với Cloud Vault 5.1, Spring Framework 7, Jackson 3, KV v1/v2, token/lease, Transit và PKI.

### 3.2. Nếu chỉ dùng Spring Vault Core

Ứng dụng Spring Framework thuần hoặc không dùng Config Data chỉ cần khai báo Core và những dependency theo chức năng:

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
    <!-- Version từ Spring Boot BOM hoặc BOM tương thích đã import -->
  </dependency>
</dependencies>
```

Spring Vault 4.x **không tự kéo Jackson vào transitively** để người dùng tự chọn Jackson 3 hay Jackson 2. Nếu không có BOM, phải khai báo version cho Jackson và quản lý Spring Framework/HTTP client phù hợp. Chỉ khi dùng `ReactiveVaultTemplate` mới cần thêm WebFlux/Reactor; chỉ khi dùng `@EnableVaultRepositories` mới cần thêm Spring Data KeyValue; SDK AWS/GCP chỉ thêm theo phương thức xác thực.

## 4. Vì sao Maven có thể chọn bản khác bạn trông đợi?

Maven áp dụng **dependency mediation**: khi nhiều nhánh yêu cầu cùng một `groupId:artifactId` với version khác nhau, quy tắc mặc định ưu tiên dependency “gần” dự án hơn; nếu bằng độ sâu thì khai báo trước thắng. `dependencyManagement` trong dự án có thể điều phối phiên bản được chọn.

Đồ thị **giả lập** để hiểu thuật toán:

```text
orders-api
  ├── lib-a
  │    └── example:http-util:1.4
  └── lib-b
       └── lib-c
            └── example:http-util:1.8

Nếu không có dependencyManagement:
example:http-util:1.4 có đường đi ngắn hơn → có thể được chọn.
```

**Kết luận không phải “Maven luôn chọn bản mới nhất”.** Tương tự, ghi `spring-vault-core:4.1.2` ở nhánh A không cho phép suy rằng mọi Spring component, Jackson hoặc Apache HttpComponents đều được nâng phù hợp.

Một số cơ chế khác thay đổi classpath:

| Cơ chế Maven | Ý nghĩa đối với Spring Vault |
| --- | --- |
| `optional=true` | Dependency tùy chọn của thư viện **không tự truyền** vào dự án tiêu thụ; ví dụ Jackson/WebFlux/Spring Data/SDK cloud phải được thêm theo tính năng |
| `scope=runtime` | Có trên runtime nhưng không nhất thiết có ở compile path |
| `scope=test` | Không phải dependency runtime production; thích hợp cho JUnit/Testcontainers |
| `provided` | Thông thường do môi trường cung cấp; không được giả định luôn có trong executable JAR |
| `exclusions` | Bỏ một dependency từ nhánh transitive cụ thể; có thể vô tình làm thiếu JSON mapper hoặc HTTP transport |
| `dependencyManagement` | Ghi đè phiên bản được chọn theo chính sách quản lý; không tự thêm JAR |
| BOM import thứ tự và inheritance | Nhiều BOM cùng quản lý một artifact có thể gây khác biệt về phiên bản; cần xem effective POM và đồ thị cuối |

**Đặc biệt với Jackson:** `com.fasterxml.jackson.core:jackson-databind` (Jackson 2) và `tools.jackson.core:jackson-databind` (Jackson 3) **khác groupId**, có thể cùng nằm trên classpath. Maven mediation không xem chúng là cùng một artifact để chỉ giữ một bản. Spring Vault 4.x ưu tiên Jackson 3 nếu cả hai hiện diện; custom converter/serializer và DTO phải được test riêng.

Nguồn: [Maven – Introduction to Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html), [Spring Vault – Dependencies](https://docs.spring.io/spring-vault/reference/introduction/dependencies.html).

## 5. Maven: xem cây phụ thuộc và chặn xung đột

### 5.1. Bộ lệnh chẩn đoán

```bash
# Phiên bản Java/Maven mà CI thực sự dùng
mvn -version

# Các BOM, parent và dependency management sau kế thừa/import
mvn help:effective-pom

# Toàn đồ thị phụ thuộc; plugin có thể có nhiều định dạng output
mvn dependency:tree

# Chỉ tập trung dependency dùng ở runtime
mvn dependency:tree -Dscope=runtime

# Chỉ các Spring Vault artifact đã được resolve
mvn dependency:tree -Dincludes=org.springframework.vault:*

# Kiểm tra JSON converter, nơi thường có hai thế hệ Jackson
mvn dependency:tree -Dincludes=tools.jackson.core:*,com.fasterxml.jackson.core:*

# Khi cần cả các nút bị bỏ qua vì conflict/duplicate
mvn dependency:tree -Dverbose
```

`-Dincludes` là bộ lọc **hiển thị cây**, không phải chức năng đổi dependency. `-Dverbose` cho phép thấy các node bị bỏ qua do xung đột, tùy phiên bản Maven Dependency Plugin. Khi cần ghi lại đồ thị cho review, plugin còn hỗ trợ `-DoutputType=json` ở các phiên bản mới; xác minh phiên bản plugin thực tế trong build.

**Hãy kiểm tra cả chiều có và chiều không:** `spring-vault-core` bản nào? Có `spring-cloud-vault-config` thuộc train đúng không? Jackson 3 có thực sự tồn tại? Có `spring-webflux` khi dùng reactive, `spring-data-keyvalue` khi dùng repository hoặc cloud SDK phù hợp phương thức auth không? Việc không thấy một optional dependency trong cây là bình thường nếu tính năng đó không sử dụng.

### 5.2. Maven Enforcer: ngăn một số xung đột ngay tại CI

Maven Enforcer có hai rule đáng biết:

- `requireUpperBoundDeps`: báo lỗi khi **version được chọn thấp hơn** mức phiên bản cao nhất được yêu cầu từ các nhánh được xét. Hữu ích khi một thư viện nền bị mediation về bản cũ.
- `dependencyConvergence`: chặt hơn, yêu cầu **các nhánh yêu cầu cùng một version** cho artifact đó; có thể phát hiện đồ thị không hội tụ nhưng cũng tạo cảnh báo trong những hệ sinh thái đa BOM vì các version được *yêu cầu* khác nhau dù resolver vẫn chọn một bản.

Ví dụ bật `requireUpperBoundDeps` trong vòng `validate` (phiên bản plugin minh họa từ tài liệu Maven):

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-enforcer-plugin</artifactId>
      <version>3.6.3</version>
      <executions>
        <execution>
          <id>check-dependency-bounds</id>
          <goals><goal>enforce</goal></goals>
          <configuration>
            <rules>
              <requireUpperBoundDeps/>
            </rules>
          </configuration>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
```

**Không vội thêm `dependencyConvergence` và tắt mọi cảnh báo bằng exclusions.** Hãy điều tra vì sao hai nhánh đòi version khác nhau, xác nhận BOM được hỗ trợ và sửa ở nguồn quản lý trước. Nếu có exception cần thiết, giới hạn theo artifact, ghi lý do và theo dõi lúc nâng cấp.

Nguồn: [Maven Enforcer – requireUpperBoundDeps](https://maven.apache.org/enforcer/enforcer-rules/requireUpperBoundDeps.html), [dependencyConvergence](https://maven.apache.org/enforcer/enforcer-rules/dependencyConvergence.html), [Maven Dependency Plugin – tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html).

## 6. Gradle: platform, constraints và khóa cả dependency bắc cầu

### 6.1. Cấu hình theo bộ phiên bản và một patch cụ thể

Gradle Kotlin DSL sau minh họa ứng dụng sử dụng starter Cloud Vault, hai BOM và một **constraint có chủ đích** cho Core. Cấu hình `dependencyLocking` lưu chính xác đồ thị được resolve ở các configuration được khóa.

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
    implementation(platform("org.springframework.boot:spring-boot-dependencies:4.2.0"))
    implementation(platform("org.springframework.cloud:spring-cloud-dependencies:2026.0.0"))

    implementation("org.springframework.cloud:spring-cloud-starter-vault-config")

    constraints {
        implementation("org.springframework.vault:spring-vault-core") {
            version {
                strictly("4.1.2")
            }
            because("Bản vá Core đã công bố cho CVE-2026-41698")
        }
    }
}

dependencyLocking {
    lockAllConfigurations()
    lockMode = LockMode.STRICT
}
```

Đây là **ví dụ version pinning**, không tạo kết nối Vault. `LockMode.STRICT` yêu cầu có trạng thái lock cho configuration được đánh dấu khóa khi được resolve; sau khi cấu hình, cần tạo các lockfile ban đầu. `strictly("4.1.2")` ép **chính xác** Core 4.1.2; nếu một module tương lai yêu cầu phiên bản không tương thích, Gradle có thể fail resolution. Điều đó tốt cho khả năng phát hiện lệch version, nhưng phải chủ động **gỡ/nâng constraint khi BOM đã hỗ trợ patch mới**.

**Một sự khác nhau với Maven:** Gradle `platform(...)` đưa *constraints* vào thuật toán chọn version, không mặc nhiên ép cứng mọi version của BOM. `enforcedPlatform(...)` ép version cả nền BOM và có thể tạo hiệu ứng cho consumer khác khi xuất bản thư viện; dùng có chủ đích thay vì mặc định. Đối với một patch cụ thể của Core, `strictly` theo artifact thường dễ xem xét hơn là ép cả hai BOM.

### 6.2. Tạo lockfile và commit vào Git

```bash
# Xem bản đã resolve trước khi khóa
./gradlew dependencies --configuration runtimeClasspath

# Tạo lock state cho các configuration được resolve
./gradlew dependencies --write-locks

# Có thể chạy build/test để resolve thêm configuration liên quan
./gradlew test --write-locks

# Sau khi commit gradle.lockfile: CI chạy bình thường, KHÔNG ghi lại lock
./gradlew clean test
```

Gradle ghi `gradle.lockfile` ở **gốc từng project/subproject** cần khóa, chứa từng tọa độ `group:name:version` và configuration liên quan. **Commit lockfile cùng thay đổi build script**. Không sửa tay các dòng của lockfile vì có thể làm sai trạng thái resolution.

Với project đa module, `./gradlew dependencies --write-locks` ở root **không nhất thiết resolve hết configuration ở mọi subproject**; cần chạy task phù hợp tại từng module hoặc một task chuyên dụng để resolve mọi configuration cần khóa. Không kết luận đã khóa toàn repo chỉ vì thấy một `gradle.lockfile` ở root.

**Lockfile không khóa nội dung của dependency kiểu `-SNAPSHOT` hoặc `changing`** khi tọa độ không đổi nhưng bytes có thể đổi; ưu tiên stable releases. Lockfile cũng không bao phủ mọi classpath plugin/buildscript nếu chưa bật locking tương ứng.

### 6.3. Cập nhật chọn lọc khi có bản vá

Ví dụ một PR bảo mật cần nâng Core lên 4.1.2 mà chưa thay toàn bộ BOM:

1. Xác nhận CVE, phiên bản Core đang resolve và bộ Framework/Cloud Vault tương thích.
2. Thay constraint/BOM thích hợp trước, tránh lockfile mâu thuẫn với yêu cầu mới.
3. Dùng `dependencyInsight` để xem bản Core được chọn và nguyên nhân; sau đó cập nhật lock state có giới hạn:

```bash
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-vault-core

# Chỉ mở khóa và cập nhật artifact được nêu, các nhánh liên quan
# có thể vẫn thay đổi nếu thuật toán resolve yêu cầu.
./gradlew dependencies --update-locks org.springframework.vault:spring-vault-core
```

`dependencies --configuration runtimeClasspath` hiển thị **cả cây**, trong khi `dependencyInsight --dependency spring-vault-core` tập trung vào **một artifact**; không dùng `--dependency` với task `dependencies`.

4. Review `gradle.lockfile`, sau đó chạy `./gradlew clean test`, integration test Vault và CI security checks.
5. Cập nhật thêm lock state của test/runtime configuration hoặc module khác nếu sử dụng.

`--update-locks` chỉ điều khiển **danh sách module được phép cập nhật trong lock state**, không tự nâng version nếu BOM/constraint vẫn giữ bản cũ. Một artifact phụ thuộc liên quan vẫn có thể đổi vì lý do mediation/constraints; **xem diff và dependencyInsight**.

Nguồn: [Gradle – Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html), [Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html), [Platforms](https://docs.gradle.org/current/userguide/platforms.html).

## 7. Kiểm tra đúng dependency đã resolve bằng Gradle

```bash
# Danh sách runtime dependency
./gradlew dependencies --configuration runtimeClasspath

# Vì sao Core có phiên bản này? Bị BOM, lockfile hay constraint chọn?
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-vault-core

# Cùng kiểm tra Cloud Vault starter và Spring Framework
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-cloud-vault-config
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-core

# Tìm mapper JSON mà Vault đang dùng
./gradlew dependencyInsight --configuration runtimeClasspath --dependency jackson-databind

# Nếu dùng WebFlux/ReactiveVaultTemplate
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-webflux
./gradlew dependencyInsight --configuration runtimeClasspath --dependency reactor-core

# Nếu dùng Vault repositories
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-data-keyvalue
```

Ở Windows dùng `gradlew.bat`. Trong kết quả `dependencies`, ký hiệu `(c)` biểu thị *constraint*, không phải chắc chắn JAR đã hiện diện; mũi tên `requested -> selected` cho thấy bản đã chọn. `dependencyInsight` chỉ ra đường nhánh kéo một module và lý do chọn version, hữu ích khi lockfile hoặc BOM làm bản cuối khác với bản bạn ghi.

Ví dụ **minh họa**, không phải output thực tế của repo:

```text
org.springframework.vault:spring-vault-core:4.1.0 -> 4.1.2
  Selection reasons:
    - By constraint (strict 4.1.2)

spring-cloud-vault-config:5.1.0
  \--- spring-vault-core:4.1.0 -> 4.1.2
```

Không lấy ví dụ làm bằng chứng rằng Spring Cloud Vault 5.1.0 **thực tế** yêu cầu đúng 4.1.0: điều đó phải được xác minh trên đồ thị của bản build. Khi nhiều module dùng Core/Framework khác nhau, kiểm tra thêm `compileClasspath`, `testRuntimeClasspath` và `bootJar`/artifact cuối, không chỉ một configuration.

## 8. Optional dependency, scope và artifact “trông như đã có”

Đối với Spring Vault, một số phụ thuộc chỉ xuất hiện khi dùng chức năng:

| Chức năng Spring Vault | Artifact nên tìm trên runtime classpath | Bẫy thường gặp |
| --- | --- | --- |
| KV/Transit/PKI qua `VaultTemplate` | `spring-vault-core` và Spring Web/JSON mapper cần thiết | Thiếu Jackson dù Core biên dịch thành công |
| Jackson 3 trong Framework 7 | `tools.jackson.core:jackson-databind` | Cùng có Jackson 2; custom mapper chọn sai thế hệ |
| Reactive `ReactiveVaultTemplate` | `spring-webflux`, `reactor-core` và HTTP connector | Chỉ có Reactor Core mà thiếu WebClient |
| Vault repositories | `spring-data-keyvalue`, `spring-data-commons` | Nhầm repository với Core-only; quên policy `list` |
| AWS IAM auth qua API dùng SDK v2 | `software.amazon.awssdk:auth` và module liên quan | Dùng snippet SDK v1 cho chữ ký v2 |
| GCP IAM Credentials auth | `com.google.cloud:google-cloud-iamcredentials` | Thiếu transitive GAX/gRPC/Google Auth hoặc quyền `signJwt` |
| Spring Cloud Vault Config Data | `spring-cloud-starter-vault-config` | Có Core nhưng tưởng `vault://` tự hoạt động |
| Integration test | `testcontainers-vault` trong `test` | Đưa container tool vào runtime production |

**Các artifact optional không nên được thêm “cho đủ”.** Để giảm diện tích tấn công và kích thước image, chỉ khai báo JSON/repositories/reactive/cloud SDK đúng nhu cầu. Với Maven, dependency đánh dấu `optional` trong POM của thư viện không tự truyền sang consumer. Với Gradle, cách đọc metadata/variant có thể khác Maven; luôn kiểm tra classpath được resolve thực tế.

**Kiểm tra cả application packaging:** dependency xuất hiện trong `testRuntimeClasspath` nhưng thiếu trong `runtimeClasspath` có thể làm integration test chạy được nhưng production gặp `ClassNotFoundException`. Ngược lại, dependency `test` không nên lọt vào executable archive.

## 9. Khóa phiên bản chưa đủ: kiểm tra integrity, CVE và provenance

### 9.1. Ví dụ bảo mật Spring Vault ngày 19/11/2026

Theo advisory **CVE-2026-41698**, các phiên bản bị ảnh hưởng có thể xử lý secret path chứa traversal chưa được làm sạch trong một số KV/repository API. Spring công bố bản OSS sửa lỗi trong **4.0.5** và **4.1.2**; với các dòng cũ hơn, cần đối chiếu bản fix và kênh hỗ trợ trong advisory.

Điều cần kiểm tra cho ứng dụng dùng Spring Cloud Vault:

1. **Phiên bản `spring-vault-core` được resolve**, không chỉ Cloud Vault starter hoặc release train.
2. **Cấu hình Vault Server và quyền token**: nếu token có quyền rộng, lỗ hổng path traversal có tác động nghiêm trọng hơn. Áp dụng least privilege và validate ID/path đến từ input ngoài.
3. **Version của framework và các dependencies liên quan**, vì một override riêng Core có thể phá vỡ API binary nếu vượt thế hệ.
4. **Integration test** với KV v1/v2, policy chặn đọc path khác keyspace, Transit/PKI, token/lease và xử lý lỗi.

Ví dụ một dòng trong tree mang `spring-cloud-starter-vault-config` phiên bản mới **không chứng minh** Core đã vá. CI nên kiểm tra artifact cụ thể và advisory, rồi review PR nâng BOM/override/lockfile.

Nguồn: [Spring Vault 4.0.5 & 4.1.2 release announcement](https://spring.io/blog/2026/11/19/spring-vault-4-0-5-4-1-2-available/), [Spring Vault CVE-2026-41698 advisory](https://spring.io/security/cve-2026-41698/).

### 9.2. Gradle dependency verification kiểm tra bytes được tải

Gradle có cơ chế **dependency verification** riêng với lockfile. Có thể tạo metadata checksum:

```bash
# Thực hiện trên bộ dependency đã chọn và nguồn repository tin cậy
./gradlew --write-verification-metadata sha256 help
```

Lệnh tạo hoặc cập nhật `gradle/verification-metadata.xml`. Artifact tải về sau đó được đối chiếu checksum; có thể bổ sung chữ ký `pgp` khi upstream hỗ trợ. **Không tin mù quáng file metadata vừa sinh**: nếu nguồn ban đầu đã bị xâm nhập thì checksum sẽ khóa đúng những bytes xấu đó. Review metadata và key trust, chỉ commit sau khi xác minh nguồn và artifact quan trọng.

**Phân biệt:** `gradle.lockfile` ghi **artifact version**, còn `verification-metadata.xml` kiểm tra **artifact bytes/chữ ký**. Một artifact có checksum hợp lệ vẫn có thể tồn tại lỗ hổng CVE; ngược lại một bản mới an toàn nhưng chưa có checksum được duyệt sẽ khiến CI verification fail.

Nguồn: [Gradle – Verifying Dependencies](https://docs.gradle.org/current/userguide/dependency_verification.html), [Gradle – Securing Dependencies](https://docs.gradle.org/current/userguide/securing_dependencies.html).

### 9.3. SBOM và vulnerability scanning

Với hệ thống quản lý secrets, quy trình phát hành có thể tạo **SBOM** cho artifact runtime cuối cùng, đưa qua công cụ kiểm tra lỗ hổng và đối chiếu Spring Security Advisories/NVD theo chính sách tổ chức. SBOM hữu ích để xác định một CVE nằm trong **dependency bắc cầu** không hề được ghi trực tiếp trong POM.

Tuy nhiên:

- Một scanner có thể báo sai hoặc chưa có advisory mới; xác minh version range và điều kiện khai thác trước khi quyết định.
- Một bản Java JAR được build với BOM cũ nhưng deploy cùng thư viện từ classpath khác cần đối chiếu **runtime image thực tế**.
- Không suy chỉ vì không có CVE công bố là an toàn tuyệt đối. Kiểm soát token, Vault ACL, TLS và đường dẫn secret vẫn bắt buộc.

## 10. Quy trình nâng cấp dependency an toàn trong CI

Một quy trình có thể áp dụng cho `orders-api` khi cần cập nhật Spring Vault:

1. **Chụp trạng thái:** JDK, Boot version, Spring Cloud train, Spring Vault Core, Framework, Jackson, WebFlux, Spring Data, cloud SDK và dependency tree hiện tại. Lưu kết quả trong báo cáo build; không ghi secret vào artifact hay log.
2. **Chọn BOM tương thích:** không nâng riêng Cloud Vault starter qua thế hệ Boot khác. Khi đổi Boot/Cloud train, so sánh release notes và các API bị deprecated/breaking.
3. **Đánh giá advisory:** xác định phiên bản Core và patch nhỏ nhất trong **cùng thế hệ tương thích**. Với CVE-2026-41698, kiểm tra 4.0.5 hoặc 4.1.2 và điều kiện ảnh hưởng.
4. **Cập nhật source of truth:** Maven `dependencyManagement` hoặc Gradle platform/constraint trước; không chỉnh lockfile thủ công. Giữ override chỉ khi cần vá và có lý do.
5. **Resolve + review:** Maven `dependency:tree`/effective POM/Enforcer; Gradle `dependencyInsight`, `--update-locks` và review `gradle.lockfile`. Kiểm tra dependency bắc cầu của JSON, HTTP, Reactor, SDK.
6. **Kiểm tra supply chain:** checksum/signature verification khi dùng Gradle, SBOM/vulnerability scan và tính tin cậy của artifact repository.
7. **Chạy test:** unit tests cho code dùng `VaultOperations`; integration tests với Vault test server cho login theo workload, KV v1/v2, token/lease, Transit, PKI, TLS và ACL.
8. **Canary/rollout:** theo dõi lỗi login 401/403, TLS handshake, timeout, lease renewal/rotation, HTTP 429/5xx và mức request Vault. Có kế hoạch rollback **cả BOM/lockfile/artifact** cùng nhau.
9. **Dọn override:** khi BOM mới quản lý patch cần thiết, bỏ constraint hoặc dependencyManagement tạm và tạo lại lockfile; chạy test trước khi merge.

### Quy tắc kiểm thử đừng bỏ qua

| Test | Lý do |
| --- | --- |
| Khởi động với bộ dependency mới | Phát hiện `NoSuchMethodError` / `NoClassDefFoundError` |
| Đọc KV v1/v2, bao gồm path không tồn tại | Kiểm tra HTTP/JSON converter và đường dẫn `data/` |
| Workload auth và token hết hạn | SDK/cloud identity và session manager có thể thay đổi hành vi |
| Token có policy chỉ đọc một keyspace | Không phụ thuộc vào root token test để che thiếu ACL |
| Transit encrypt/decrypt hoặc PKI issue | Xác nhận API domain vẫn hoạt động sau nâng Framework/HTTP |
| Lease gia hạn, rotate hoặc revoke | Build thành công không chứng minh client đang dùng credential mới |
| Lỗi TLS/timeout/HTTP 403 | Xác định fail-fast, retry có giới hạn và log không chứa secret |

## 11. Bảng xử lý sự cố version resolution

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Bản trong `pom.xml` khác `dependency:tree` | BOM, `dependencyManagement`, mediation | Xem `effective-pom`, tree có `-Dverbose` và rule version |
| Gradle chọn bản khác khai báo | Platform/constraint, conflict resolution hoặc lockfile | `dependencyInsight` để xem “selection reasons” |
| Gradle build fail vì lock state | Build script/BOM thay đổi nhưng lock chưa cập nhật | Review thay đổi, chạy `--update-locks` hoặc `--write-locks` đúng configuration |
| CI và local dùng Core khác nhau | Lockfile chưa commit, khác Gradle/Maven settings, repository hoặc JDK | So sánh wrapper, BOM, lockfile, metadata, runtime classpath |
| `NoSuchMethodError` Spring Framework | Trộn Spring Framework 6.x với Vault 4.x/Framework 7 | Chọn lại cả Boot/Framework/Vault cùng thế hệ |
| Jackson class/mapping lỗi | Thiếu Jackson 3, cả Jackson 2/3, module mismatch | Kiểm tra hai groupId và converter thực |
| `ClassNotFoundException` WebClient | WebFlux optional không có trên runtime | Thêm `spring-webflux` khi dùng `ReactiveVaultTemplate` |
| Repository không khởi tạo | Thiếu Spring Data KeyValue/Commons hoặc scan sai | Xem tree và `@EnableVaultRepositories` |
| SDK AWS/GCP auth lỗi | Thiếu SDK tùy chọn hoặc khác API thế hệ | So chữ ký Javadoc và cây dependency của SDK |
| CVE vẫn bị scanner báo sau khi “nâng Cloud” | Core vẫn resolve bản cũ hoặc BOM override | Kiểm tra artifact `org.springframework.vault:spring-vault-core` thực tế |
| Maven Enforcer fail nhiều artifact | Nhánh phụ thuộc không hội tụ; BOM/override xung đột | Điều tra từng artifact, không exclude hàng loạt |
| Build thành công nhưng Vault trả 403 | Workload identity/policy/namespace sai | Kiểm tra Vault role và ACL, không mặc định sửa dependency |

## 12. Checklist chốt phiên bản trước khi phát hành

- [ ] Đã chọn **một bộ** Boot/Framework/Cloud Vault/Spring Vault có hỗ trợ tương thích và được vá.
- [ ] Tồn tại một nguồn quản lý phiên bản rõ ràng: Maven parent/BOM/`dependencyManagement` hoặc Gradle platforms/constraints.
- [ ] Dependency bắc cầu đã được xem tại **runtimeClasspath** thực tế, không chỉ đọc direct dependencies.
- [ ] `spring-vault-core`, Jackson, HTTP client, Reactor/WebFlux, Spring Data và cloud SDK đúng theo tính năng ứng dụng.
- [ ] Gradle lockfile được tạo, review và commit cho từng module cần khóa; Maven dùng Enforcer/report hoặc quy trình kiểm soát tương đương.
- [ ] Không dùng wildcard/range/`-SNAPSHOT` tùy tiện cho release production; phiên bản cuối có thể tái lập được.
- [ ] Có quy trình kiểm tra checksum/signature và vulnerability/SBOM, hiểu rằng lockfile **không** kiểm tra artifact bytes/CVE.
- [ ] Bản vá Spring Vault đã đối chiếu advisory (gồm CVE-2026-41698 khi thuộc nhánh ảnh hưởng).
- [ ] Test xác thực theo workload, KV secrets, token/lease, Transit encryption, PKI, xử lý lỗi và TLS đã chạy.
- [ ] Override bản vá có lý do, chủ sở hữu và kế hoạch gỡ khi BOM cập nhật.

**Ghi nhớ:** **đọc BOM để biết bản được đề xuất, đọc dependency tree để biết bản được chọn, dùng lockfile để giữ ổn định đồ thị, dùng verification để xác minh bytes và đọc advisory để biết bản nào phải vá**. Với Spring Vault, kiểm chứng cuối cùng vẫn là ứng dụng chạy với **Vault token giới hạn quyền**, secret engines cấu hình đúng và vòng đời token/lease được kiểm thử.

### Tài liệu tham khảo

1. [Spring Vault – Dependencies](https://docs.spring.io/spring-vault/reference/introduction/dependencies.html)
2. [Spring Boot – Build Systems and Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
3. [Spring Cloud – Boot Compatibility](https://spring.io/projects/spring-cloud/)
4. [Spring Cloud 2026.0.0 GA (20/11/2026)](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
5. [Spring Cloud 2025.1.5 GA (20/11/2026)](https://spring.io/blog/2026/11/20/spring-cloud-2025-1-5-has-been-released/)
6. [Maven – Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
7. [Maven Dependency Plugin – dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
8. [Maven Enforcer – requireUpperBoundDeps](https://maven.apache.org/enforcer/enforcer-rules/requireUpperBoundDeps.html)
9. [Maven Enforcer – dependencyConvergence](https://maven.apache.org/enforcer/enforcer-rules/dependencyConvergence.html)
10. [Gradle – Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
11. [Gradle – Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
12. [Gradle – Platforms](https://docs.gradle.org/current/userguide/platforms.html)
13. [Gradle – Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
14. [Spring Vault 4.0.5/4.1.2 released (19/11/2026)](https://spring.io/blog/2026/11/19/spring-vault-4-0-5-4-1-2-available/)
15. [CVE-2026-41698 – Spring Security Advisory](https://spring.io/security/cve-2026-41698/)
