# Quan hệ giữa Spring Vault, Spring Boot và Spring Cloud release train

Trong ứng dụng Java dùng HashiCorp Vault, có hai cách tích hợp thường gặp: gọi API Vault bằng `VaultTemplate` của **Spring Vault** hoặc để **Spring Cloud Vault** đưa secret từ Vault vào cấu hình Spring Boot khi ứng dụng khởi động. Hai cách này có thể kết hợp, nhưng chúng thuộc các lớp dependency khác nhau. Nếu chọn sai Spring Cloud release train so với Spring Boot, ứng dụng có thể lỗi trước khi kịp xác thực workload hoặc đọc KV secret.

**Chương:** Phiên bản và phụ thuộc. **Mục tiêu bài học:** phân biệt Spring Vault Core, Spring Cloud Vault và Spring Boot; hiểu cách BOM/release train xác định các phiên bản đi cùng nhau; cấu hình dependency cho Maven/Gradle; kiểm tra bản thực sự được nạp; và nâng cấp an toàn khi ứng dụng còn dùng KV secrets, token/lease, Transit encryption hoặc PKI.

> **Thời điểm đối chiếu: 25/11/2026.** Bảng phiên bản sử dụng các release chính thức đã xuất bản đến ngày này. Spring Cloud, Spring Boot và Spring Vault có lịch phát hành riêng; luôn xem release notes, tình trạng hỗ trợ và dependency tree của **bản vá chính xác** trước khi triển khai.

## 1. Ba tên gần nhau nhưng không phải ba phiên bản của cùng một thư viện

| Thành phần | Dependency / BOM tiêu biểu | Trách nhiệm |
| --- | --- | --- |
| **Spring Boot** | `org.springframework.boot:spring-boot-dependencies` hoặc `spring-boot-starter-parent` | Quản lý nền Spring Framework, Jackson, HTTP client, logging, test và quy trình khởi động/auto-configuration |
| **Spring Cloud release train** | `org.springframework.cloud:spring-cloud-dependencies` | Chọn **một bộ phiên bản tương thích** cho Spring Cloud Config, Commons, Vault, Gateway, Kubernetes... theo thế hệ Spring Boot |
| **Spring Cloud Vault** | `org.springframework.cloud:spring-cloud-starter-vault-config` (kèm `spring-cloud-vault-config`) | Tích hợp Vault làm nguồn cấu hình cho `Environment`, Config Data, xác thực, secret backends và một số cơ chế vòng đời |
| **Spring Vault Core** | `org.springframework.vault:spring-vault-core` | Thư viện trực tiếp làm việc với Vault: `VaultTemplate`, KV, authentication, token/lease, Transit, PKI |
| **HashiCorp Vault Server** | Dịch vụ riêng, không phải dependency Maven | Lưu/duy trì secrets và policies, thực thi ACL, Transit/PKI, cấp token/lease |

**Spring Cloud Vault xây dựng trên Spring Vault Core.** Khi thêm starter Cloud Vault, thông thường classpath đã có `spring-vault-core` như dependency bắc cầu. Vì vậy cần phân biệt:

- **Spring Vault 4.1.2**: phiên bản thư viện `spring-vault-core`.
- **Spring Cloud Vault 5.1.0**: phiên bản **một module** trong Spring Cloud.
- **Spring Cloud 2026.0.0**: phiên bản **release train/BOM**, không phải số phiên bản của starter Cloud Vault.
- **Spring Boot 4.2.0**: phiên bản nền ứng dụng; BOM Boot quản lý Spring Framework 7.1.0 cùng nhiều thành phần khác.

Không có quy tắc “Spring Boot 4.x thì Spring Cloud Vault 4.x”. Số major của các thành phần khác nhau được đặt độc lập.

```text
  Java runtime (JDK)
         │
         ▼
  Spring Boot parent / BOM ──► Spring Framework, Jackson, HTTP client...
         │
         │  Chọn Spring Cloud release train tương thích với Boot
         ▼
  Spring Cloud BOM (spring-cloud-dependencies)
         │
         ▼
  Spring Cloud Vault starter / config
         │  dùng
         ▼
  Spring Vault Core (VaultTemplate, auth, token/lease, Transit, PKI)
         │  HTTPS / Vault API + policy của workload
         ▼
  HashiCorp Vault Server
```

**Khi chỉ cần `VaultTemplate`** để đọc/ghi KV hoặc gọi Transit/PKI, một ứng dụng Spring Framework thuần có thể dùng `spring-vault-core` trực tiếp, không bắt buộc có Spring Cloud release train hay Spring Boot. **Khi muốn import secrets thành cấu hình ứng dụng** trong Spring Boot, `spring-cloud-starter-vault-config` và release train tương ứng thường là lựa chọn hợp lý hơn.

## 2. Release train giải quyết vấn đề gì?

Spring Cloud gồm nhiều dự án có tốc độ phát hành khác nhau. Release train (ví dụ **2025.1.x – Oakwood**) là **tập hợp các phiên bản module đã được phối hợp theo một thế hệ Spring Boot**, công bố qua BOM `spring-cloud-dependencies`. Một bản service release của train có thể chứa Spring Cloud Vault 5.0.4, Spring Cloud Config 5.0.7 và Spring Cloud Commons 5.0.5; các module **không nhất thiết có cùng số patch**.

Spring Boot BOM và Spring Cloud BOM có trách nhiệm bổ sung nhau:

1. **Boot parent/BOM** xác định nền tảng Spring Framework, Jackson và phần lớn dependency cho ứng dụng.
2. **Cloud BOM** chọn phiên bản các **module Spring Cloud**, trong đó có Spring Cloud Vault, tương ứng với Boot.
3. **Spring Cloud Vault** phụ thuộc vào Spring Vault Core; phiên bản Core được quản lý qua dependency management của bộ thư viện đang sử dụng.
4. **Trình giải quyết dependency** (Maven/Gradle) quyết định phiên bản cuối cùng; override trực tiếp, BOM import, dependency bắc cầu và quy tắc chọn phiên bản có thể ảnh hưởng kết quả.

Nhập BOM chỉ **quản lý phiên bản**, không tự thêm thư viện vào classpath. Bạn vẫn phải khai báo `spring-cloud-starter-vault-config` trong `dependencies` khi muốn dùng starter.

> **Release train không phải bằng chứng đã vá mọi lỗ hổng mới phát hiện.** Khi có CVE ở Spring Vault Core, phải xác minh phiên bản `spring-vault-core` thực sự được resolve, kể cả đang dùng bản train mới nhất.

## 3. Ma trận Spring Boot ↔ Spring Cloud ↔ Spring Cloud Vault

Các dòng dưới đây dựa trên thông báo phát hành, tài liệu tương thích và danh sách module chính thức đến **25/11/2026**:

| Spring Boot | Nền Spring Framework | Spring Cloud release train | Spring Cloud Vault trong bản train nêu ở đây | Trạng thái và ghi chú |
| --- | --- | --- | --- | --- |
| **4.2.x** | **7.1.x** | **2026.0.x – Paddington**; GA **2026.0.0** | **5.1.0** | Bản train mới công bố 20/11/2026, dựa trên Boot **4.2.0** |
| **4.0.x / 4.1.x** | **7.0.x** | **2025.1.x – Oakwood**; bản **2025.1.5** | **5.0.4** | Từ **2025.1.2** trở đi mới công bố tương thích Boot 4.1.x |
| **3.5.x** | **6.2.x** | **2025.0.x – Northfields**; bản **2025.0.3** | **4.3.3** | Bản 2025.0.3 phát hành 11/06/2026; dòng 2025.0.x **hết hỗ trợ nguồn mở 30/06/2026** |
| **3.4.x** | **6.2.x** | **2024.0.x – Moorgate** | Nhánh **4.2.x** | Dòng đã hết vòng đời hỗ trợ nguồn mở, chỉ dùng khi duy trì hệ thống cũ và có kế hoạch nâng cấp |
| **3.2.x / 3.3.x** | **6.1.x** | **2023.0.x – Leyton** | Nhánh **4.1.x** | Hỗ trợ Boot 3.3 từ bản train 2023.0.2; dòng đã hết vòng đời nguồn mở |

Trong bảng, **5.1.0 / 5.0.4 / 4.3.3 là số phiên bản Spring Cloud Vault**, không phải Spring Vault Core. Chẳng hạn, Spring Cloud **2026.0.0** công bố Spring Cloud Vault **5.1.0**, đồng thời ghi việc nâng thế hệ thư viện nền lên **Spring Vault 4.1**. Không được suy số patch của `spring-vault-core` từ phiên bản train: cần dùng dependency tree để xác nhận.

**Lựa chọn theo tình huống:**

- Dự án mới chọn **Boot 4.2.0**: ghép **Cloud 2026.0.0**, starter Cloud Vault **5.1.0**; kiểm tra thêm patch Spring Vault Core thực tế.
- Dự án đang chạy **Boot 4.1.x**: ghép **Cloud 2025.1.5**, Cloud Vault **5.0.4**; không tự chuyển riêng starter sang nhánh 5.1 khi vẫn giữ Boot 4.1.
- Dự án **Boot 3.5.x**: về mặt tương thích lịch sử dùng Cloud **2025.0.x**, nhưng bản train này đã hết hỗ trợ nguồn mở vào giữa năm 2026; cần kế hoạch nâng cấp hoặc phương án hỗ trợ bảo mật phù hợp.
- Khi bắt gặp `spring-cloud-starter-vault-config:5.1.0` trong một dự án Boot 3.5 hoặc Boot 4.0, hãy kiểm tra lại cả BOM: đây là dấu hiệu trộn các thế hệ Spring Cloud.

Nguồn: [Spring Cloud – bảng tương thích và EOL](https://spring.io/projects/spring-cloud/), [Spring Cloud 2026.0.0 GA](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/), [Spring Cloud 2025.1.5 GA](https://spring.io/blog/2026/11/20/spring-cloud-2025-1-5-has-been-released/), [Spring Cloud 2025.0.3](https://spring.io/blog/2026/06/11/spring-cloud-2025-0-3-aka-northfields-has-been-released/) và [Spring Boot 4.2 – System Requirements](https://docs.spring.io/spring-boot/system-requirements.html).

### Không nhầm tương thích với còn được hỗ trợ

Một bộ `Boot 3.5 + Cloud 2025.0` vẫn có thể chạy đúng về mặt nhị phân nhưng **không còn nhận bản vá nguồn mở mới** sau khi kết thúc thời hạn hỗ trợ. Hãy xem đồng thời:

1. Tính tương thích API/ABI giữa Boot, Framework, Cloud và Vault.
2. Trạng thái hỗ trợ của từng dòng và bản vá bảo mật có sẵn.
3. Khả năng vận hành với phương thức xác thực, secrets engines và chính sách Vault của hệ thống.

## 4. Ví dụ Maven: Spring Boot 4.2.0 + Spring Cloud 2026.0.0

Ví dụ tối giản này dùng Java 17, Spring Boot parent quản lý dependency nền và Spring Cloud BOM chọn đúng phiên bản Cloud Vault starter:

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
    <artifactId>vault-cloud-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2026.0.0</spring-cloud.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>${spring-cloud.version}</version>
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

**Đọc POM:**

- Parent Boot **4.2.0** quản lý Spring Framework **7.1.0** và phần lớn dependency nền; Java 17 là mức tối thiểu được Boot 4.2 công bố.
- Cloud BOM **2026.0.0** chọn starter Cloud Vault tương ứng; không cần ghi thủ công `<version>5.1.0</version>` cho starter.
- Starter kéo thêm `spring-cloud-vault-config` và Spring Vault Core. Không khai báo `spring-vault-core` lần hai với số phiên bản ngẫu nhiên nếu chưa có nhu cầu và chưa phân tích dependency.
- Đoạn POM chỉ thể hiện **quan hệ dependency**. Ứng dụng cần code khởi động, kết nối Vault, CA/TLS, workload identity, role và policy hợp lệ mới hoạt động thực tế.

## 5. Ví dụ Gradle Kotlin DSL cùng bộ phiên bản

Với `build.gradle.kts` dùng Spring Boot plugin và plugin dependency management:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "4.2.0"
    id("io.spring.dependency-management") version "1.1.7"
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencyManagement {
    imports {
        mavenBom("org.springframework.cloud:spring-cloud-dependencies:2026.0.0")
    }
}

dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-vault-config")
}
```

Ví dụ Gradle này **cố ý không ghi phiên bản trên starter**: nó được quản lý bởi Cloud BOM. Nếu dự án đã dùng version catalog, native Gradle platform hoặc cơ chế dependency management khác, chỉ nên có một chiến lược quản lý phiên bản rõ ràng; kiểm tra phiên bản thực tế bằng `dependencyInsight`.

Đối với **Boot 4.1**, đổi cả plugin Boot và Cloud BOM sang cặp được công bố tương thích (ví dụ Boot **4.1.3** + Cloud **2025.1.5**). Đổi mỗi Cloud BOM sang `2026.0.0` trong khi giữ Boot 4.1 có thể tạo xung đột phiên bản và vượt ngoài bộ tương thích đã công bố.

## 6. Cấu hình Vault khi dùng Spring Cloud Vault starter

Với Spring Boot, Spring Cloud Vault dùng **Config Data API** để nạp secret thành thuộc tính trong `Environment` từ sớm trong chu trình khởi động. Trong `application.yml`, ví dụ workload chạy trên Kubernetes với Vault role `orders-read`:

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
        service-account-token-file: /var/run/secrets/kubernetes.io/serviceaccount/token
      kv:
        enabled: true
        backend: secret
```

Đây là ví dụ **tên host và role minh họa**, cần thay bằng thông tin thực tế. Ứng dụng dùng token của ServiceAccount để đăng nhập Vault; Vault role phải được ánh xạ đúng namespace/ServiceAccount và policy chỉ cho phép những secret cần thiết. Đừng đưa root token, client secret hoặc giá trị KV nhạy cảm vào Git hay log.

Với `spring.config.import: "vault://"`, Cloud Vault đưa các property được phép đọc từ KV vào Spring Environment theo context/profile đã cấu hình. Đọc cấu hình qua `@ConfigurationProperties`/`@Value` khác với chủ động thao tác secret bằng `VaultTemplate`. Chẳng hạn:

- Cấu hình JDBC tĩnh được nạp khi boot: **Cloud Vault Config Data** thường phù hợp.
- Đọc một khóa KV theo yêu cầu hoặc mã hóa dữ liệu bằng Transit: dùng **Spring Vault Core/`VaultTemplate`**.
- Chứng chỉ PKI hoặc thông tin đăng nhập có **lease và vòng đời ngắn**: cần chủ động chọn mô hình gia hạn/rotation, cách ứng dụng cập nhật credential và xử lý lease hết hạn; nạp cấu hình một lần khi khởi động không tự bảo đảm mọi client dùng credential mới.

Lưu ý phân biệt **KV v1 với KV v2**: đường dẫn dữ liệu và metadata khác nhau; sai mount/path hoặc thiếu policy `read` sẽ gây lỗi ngay cả khi bộ phiên bản hoàn toàn phù hợp.

Nguồn: [Spring Cloud Vault – Quick Start](https://docs.spring.io/spring-cloud-vault/reference/quickstart.html), [Config Data API](https://docs.spring.io/spring-cloud-vault/reference/config-data.html), [Authentication](https://docs.spring.io/spring-cloud-vault/reference/authentication.html).

## 7. Nếu chỉ cần Spring Vault Core thì có cần Spring Cloud BOM?

**Không bắt buộc.** Ví dụ ứng dụng dùng Spring Framework 7 và code trực tiếp thao tác `VaultTemplate` để gọi Transit, PKI hoặc KV:

```xml
<dependency>
    <groupId>org.springframework.vault</groupId>
    <artifactId>spring-vault-core</artifactId>
    <version>4.1.2</version>
</dependency>
```

Ví dụ này là **một dependency**, chưa phải POM hoàn chỉnh. Spring Vault 4.x dùng Spring Framework 7 và hỗ trợ Jackson 3 (đồng thời có đường tương thích với Jackson 2); ứng dụng cần có JSON mapper và HTTP client phù hợp. Với Boot, ưu tiên phiên bản do BOM quản lý; nếu dùng Spring Framework thuần, cần quản lý đồng bộ Framework, Jackson và HTTP client.

Thêm `spring-vault-core` không tự mang lại tính năng nạp `vault://` vào Spring Environment của Spring Cloud Vault. Ngược lại, khi đã dùng Cloud Vault starter, thường không cần thêm khai báo Core riêng để gọi `VaultTemplate`.

| Nhu cầu | Chọn dependency chính | Quản lý phiên bản |
| --- | --- | --- |
| Java/Spring Framework gọi API Vault trực tiếp | `spring-vault-core` | Chọn bản Vault Core theo Framework và JDK; kiểm tra phụ thuộc đi kèm |
| Spring Boot nạp secrets vào `application.yml`/`Environment` | `spring-cloud-starter-vault-config` | Boot BOM + **Cloud BOM tương thích** |
| Vừa nạp config, vừa chủ động gọi KV/Transit/PKI | Cloud Vault starter + sử dụng Core trên classpath | Dùng một bộ BOM đồng nhất; chỉ override Core khi có căn cứ |

## 8. Cẩn thận với bản vá bảo mật của Spring Vault Core

Ngày **19/11/2026**, Spring công bố **Spring Vault Core 4.0.5 và 4.1.2** để sửa **CVE-2026-41698** (path traversal do tham số đường dẫn secret không được làm sạch). Chỉ một ngày sau, Spring Cloud phát hành **2025.1.5** và **2026.0.0**. Vì các dự án phát hành độc lập, **không thể suy từ số release train rằng dependency Core đã là 4.0.5 hoặc 4.1.2**.

Quy trình xử lý phù hợp:

1. Chạy `dependency:tree` hoặc `dependencyInsight` và ghi lại **phiên bản `spring-vault-core` thực tế**.
2. Đối chiếu với [thông báo sửa CVE](https://spring.io/blog/2026/11/19/spring-vault-4-0-5-4-1-2-available/) và release notes tương ứng; xác định có cần bản vá trên nhánh 4.0 hoặc 4.1 không.
3. Ưu tiên một bản release train/BOM mới đã quản lý bản vá. Nếu chưa có và buộc phải vá gấp, có thể thử **override đúng artifact Core lên patch đã sửa** trong cùng thế hệ, sau đó chạy integration test đầy đủ trước khi phát hành.
4. Gỡ override tạm khi BOM được cập nhật và xác nhận lại dependency tree.

Ví dụ một **override có chủ đích** trong Maven, chỉ áp dụng sau khi thấy BOM hiện tại còn resolve Spring Vault Core dưới **4.1.2**:

```xml
<dependencyManagement>
    <dependencies>
        <!-- Bản vá Core được ưu tiên trong POM ứng dụng -->
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
```

**Đây là phương án vá có điều kiện**, không phải mẫu cần sao chép vào mọi ứng dụng. Không ép Spring Vault Core 4.1.x vào bộ Spring Boot 3.5/Framework 6.2 hoặc Cloud Vault thế hệ cũ. Bản vá Spring Vault Core cũng không thay thế việc xác định chính xác policy Vault, không ghi secret vào log và kiểm soát truy cập theo workload.

## 9. Kiểm chứng phiên bản mà ứng dụng thực sự sử dụng

### Maven

```bash
mvn -version
mvn help:effective-pom
mvn dependency:tree
```

Trong cây phụ thuộc, tìm tối thiểu: `spring-boot`, `spring-core`, `spring-cloud-vault-config`, `spring-cloud-starter-vault-config`, `spring-vault-core` và Jackson. `help:effective-pom` hữu ích để xem dependency management đã được kế thừa/import.

### Gradle

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-vault-core
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-cloud-vault-config
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-core
```

Trên Windows dùng `gradlew.bat` khi cần. Hãy xác nhận cả **compileClasspath** và **runtimeClasspath** nếu ứng dụng chạy khác khi đóng gói. Phiên bản được yêu cầu trong file build có thể khác phiên bản được resolve do BOM, conflict resolution hoặc override.

### Các lỗi thường gặp và nguyên nhân cần kiểm tra trước

| Dấu hiệu | Hướng kiểm tra |
| --- | --- |
| `CompatibilityNotMetException` khi khởi động | Kiểm tra Boot và Cloud BOM có thuộc cặp tương thích chính thức; sửa cặp phiên bản trước khi xét vô hiệu hóa compatibility verifier |
| `NoSuchMethodError` / `NoClassDefFoundError` trong lớp Spring | Tìm Spring Framework 6.x bị trộn với 7.x hoặc Spring Cloud Vault/Core từ thế hệ khác; xem runtime dependency tree |
| Không nạp giá trị KV vào property | Có starter Cloud Vault? Có `spring.config.import: vault://`? App name/profile, mount và quyền đọc có đúng? |
| `VaultTemplate`/bean Vault không có | Kiểm tra starter/auto-configuration, loại ứng dụng và cấu hình tạo bean; Core khai báo đơn lẻ không bảo đảm auto-config |
| Vault trả `403 Forbidden` | Kiểm tra workload authentication, policy path/capability, namespace, token đã hết hạn; lỗi ACL không tự động do BOM |
| `404`, secret trống hoặc sai cấu trúc | Kiểm tra KV v1/v2, mount/path, context/profile và dữ liệu thực tế |
| Kết nối lỗi/timeout, PKI/Transit lỗi | Kiểm tra TLS/CA, DNS, timeout, quyền engine, lease/renewal; phân biệt lỗi tích hợp với lỗi phụ thuộc |

**Smoke test nên có:** khởi động với xác thực workload thực; đọc một KV secret được cấp phép; thử một path bị từ chối; kiểm tra thời điểm token hết hạn/gia hạn; và nếu ứng dụng dùng Transit/PKI, thử mã hóa/giải mã hoặc cấp/gia hạn chứng chỉ. Các test này cần chạy trên Vault thử nghiệm với cấu hình policy gần production và không lưu secret trong log/test report.

## 10. Quy trình nâng cấp một hệ thống đang vận hành

Giả sử hệ thống đang chạy **Boot 3.5 + Cloud 2025.0 + Cloud Vault 4.3**, đồng thời có code gọi `VaultTemplate`:

1. **Chụp trạng thái hiện tại:** JDK, phiên bản Boot, Spring Framework, Cloud train, Cloud Vault, Spring Vault Core, Jackson và các override. Lưu lại kết quả dependency tree trong hồ sơ nâng cấp.
2. **Chọn đích đã được công bố:** ví dụ Boot **4.2.0 + Cloud 2026.0.0**; kiểm tra yêu cầu JDK, các breaking changes của Boot 4/Framework 7 và Spring Cloud Vault 5.x.
3. **Nâng nền Boot và BOM Cloud cùng nhau**. Không đơn lẻ thay starter Cloud Vault 4.3 thành 5.1 trong khi để nguyên Boot 3.5.
4. **Kiểm tra cấu hình và code:** Config Data `vault://`, các property Spring Cloud Vault, bean `VaultTemplate`, HTTP client/Jackson, mã hóa Transit, PKI, session/token/lease và các API deprecated.
5. **Đánh giá security patch Core:** đối chiếu advisory mới nhất với phiên bản `spring-vault-core` sau khi resolve; chỉ ghi đè khi có lý do và có test.
6. **Triển khai có quan sát:** đo lỗi auth/ACL, lỗi đọc secret và gia hạn lease, timeout, restart/rollout; có kế hoạch rollback cặp BOM/Boot và cấu hình đồng bộ.

Nếu chưa thể nâng Boot vì phụ thuộc hệ thống, hãy kiểm tra chính sách hỗ trợ của release train hiện tại và nhận bản vá theo kênh phù hợp. **Khả năng khởi động thành công không đồng nghĩa với việc bộ phiên bản còn được hỗ trợ bảo mật.**

## 11. Checklist trước khi chốt bộ phiên bản

- [ ] JDK trong CI và production đáp ứng yêu cầu của Boot/Framework.
- [ ] Spring Cloud release train tương thích **đúng Boot minor/patch** theo tài liệu Spring.
- [ ] Starter Cloud Vault và `spring-vault-core` resolve theo bộ đã kiểm tra; không có override ngoài ý muốn.
- [ ] Phiên bản Core đã được so với **security advisory**; không bỏ qua bản vá chỉ vì BOM/train đang là bản mới.
- [ ] `spring.config.import`, auth workload, Vault namespace, ACL và mount KV hoạt động trong môi trường test.
- [ ] Luồng token/lease, Transit/PKI và lỗi Vault được kiểm thử theo chức năng ứng dụng.
- [ ] Không commit token, mật khẩu, khóa riêng hoặc secret plaintext vào source code và log.

**Quy tắc ghi nhớ:** chọn **Spring Boot** trước → tra **Spring Cloud release train** tương thích → để BOM chọn **Spring Cloud Vault starter** → xác minh **Spring Vault Core** đã resolve và mức vá bảo mật → kiểm thử với **Vault Server, workload identity và policy** thật của hệ thống.

### Tài liệu chính thức để đối chiếu

1. [Spring Cloud – release train compatibility và tình trạng hỗ trợ](https://spring.io/projects/spring-cloud/)
2. [Spring Cloud 2026.0.0 – Paddington, 20/11/2026](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
3. [Spring Cloud 2025.1.5 – Oakwood, 20/11/2026](https://spring.io/blog/2026/11/20/spring-cloud-2025-1-5-has-been-released/)
4. [Spring Cloud 2025.0.3 – Northfields, kết thúc hỗ trợ nguồn mở](https://spring.io/blog/2026/06/11/spring-cloud-2025-0-3-aka-northfields-has-been-released/)
5. [Spring Cloud Release – tài liệu và phiên bản module](https://docs.spring.io/spring-cloud-release/reference/index.html)
6. [Spring Cloud Vault – Quick Start](https://docs.spring.io/spring-cloud-vault/reference/quickstart.html)
7. [Spring Cloud Vault – Config Data API](https://docs.spring.io/spring-cloud-vault/reference/config-data.html)
8. [Spring Boot 4.2 – System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
9. [Spring Vault – Dependencies](https://docs.spring.io/spring-vault/reference/introduction/dependencies.html)
10. [Spring Vault 4.0.5 và 4.1.2 – bản vá CVE-2026-41698, 19/11/2026](https://spring.io/blog/2026/11/19/spring-vault-4-0-5-4-1-2-available/)
