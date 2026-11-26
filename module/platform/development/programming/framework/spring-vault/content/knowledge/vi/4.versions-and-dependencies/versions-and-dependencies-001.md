# Chọn dòng Spring Vault phù hợp với Java và Spring Framework

Khi đưa HashiCorp Vault vào ứng dụng Java, quyết định đầu tiên không phải là gọi `VaultTemplate.read()` như thế nào mà là **chọn bộ phiên bản chạy cùng nhau**. Spring Vault cung cấp API truy cập KV secrets, xác thực theo danh tính workload, quản lý token và lease, Transit encryption, PKI và các thao tác quản trị Vault. Tuy nhiên, một thư viện Spring Vault quá mới so với Spring Framework của ứng dụng có thể gây lỗi ngay khi khởi động; một thư viện quá cũ lại làm khó việc cập nhật bảo mật và tích hợp.

**Mục tiêu sau bài học:** đọc được ràng buộc phiên bản giữa Java, Spring Framework, Spring Boot, Spring Vault và Spring Cloud Vault; chọn dependency đúng cho dự án mới hoặc dự án đang vận hành; biết cách kiểm tra dependency thực sự được nạp và xác minh khả năng tương thích trước khi nâng cấp.

> **Mốc tham chiếu: 25/11/2026.** Số bản vá bên dưới là ảnh chụp tại thời điểm viết, không phải cam kết rằng chúng luôn mới nhất. Khi triển khai, đối chiếu lại [trang dự án Spring Vault](https://spring.io/projects/spring-vault/) và tài liệu của **đúng phiên bản** đang chọn.

## 1. Phân biệt các tầng phiên bản

| Thành phần | Vai trò | Cần kiểm tra |
| --- | --- | --- |
| **JDK** | Biên dịch và chạy ứng dụng Java | Phiên bản JDK trong CI, lúc build, trong Docker image và production |
| **Spring Framework** | Nền tảng DI, HTTP client, conversion, reactive API mà Spring Vault sử dụng | Dòng `6.1.x`, `6.2.x`, `7.0.x` hoặc `7.1.x` thực tế trên classpath |
| **Spring Boot** (nếu có) | Quản lý phiên bản Spring Framework và nhiều thư viện khác bằng BOM | Parent/BOM nào đang được import; framework nào được giải quyết từ BOM |
| **Spring Vault** | Thư viện Java trực tiếp gọi Vault, có `VaultTemplate`, API xác thực, hỗ trợ secrets engines | Phiên bản `org.springframework.vault:spring-vault-core` |
| **Spring Cloud Vault** (tùy nhu cầu) | Tích hợp Vault vào Spring Environment / Config Data và quản lý cấu hình khởi động | Release train Spring Cloud tương ứng với Spring Boot; starter có thể kéo theo Spring Vault |
| **HashiCorp Vault Server** | Máy chủ xử lý xác thực, ACL, KV, Transit, PKI và cấp lease | Phiên bản server, loại/mount của secrets engine và policy; không được suy ra từ số phiên bản Spring Vault |

Các số `4.1.2` của **Spring Vault**, `4.1.x` của **Spring Boot** và `7.0.x` của **Spring Framework** không có cùng ý nghĩa. Không chọn thư viện bằng cách làm cho số major giống nhau; hãy xuất phát từ **dòng Spring Framework thực tế** và yêu cầu của bản Spring Vault.

Một ứng dụng Spring Boot thông thường có quan hệ phụ thuộc như sau:

```text
JDK (build/runtime)
  └── Spring Boot BOM (nếu dùng Boot)
        └── Spring Framework
              └── Spring Vault Core (truy cập VaultTemplate, KV, Transit, PKI...)
                    └── HashiCorp Vault Server

Spring Cloud BOM → Spring Cloud Vault starter → Spring Vault Core
                   (nếu cần nạp secrets vào cấu hình ứng dụng)
```

## 2. Bảng chọn dòng Spring Vault

Bảng dưới dùng các **bản vá được tài liệu chính thức công bố** tại ngày 25/11/2026. Cột Spring Framework cho biết mức tối thiểu ghi trong tài liệu của **bản vá tương ứng**; với các patch khác trong cùng dòng, phải kiểm tra lại tài liệu của patch đó.

| Spring Vault | Spring Framework theo tài liệu phiên bản | Java tối thiểu | Ngữ cảnh lựa chọn |
| --- | --- | --- | --- |
| **3.1.3** (dòng 3.1.x) | **6.1.12+**, nên giữ cùng dòng 6.1.x | **17** | Dự án còn ở Spring Framework 6.1; thường gặp khi duy trì Spring Boot 3.2/3.3 |
| **3.2.1** (dòng 3.2.x) | **6.2.19+**, nên giữ cùng dòng 6.2.x | **17** | Dự án dùng Framework 6.2; thường gặp với Spring Boot 3.4/3.5 |
| **4.0.5** (dòng 4.0.x) | **7.0.11+** | **17** | Dự án đã sang Framework 7, đang theo nhánh 4.0 để nhận bản vá |
| **4.1.2** (dòng 4.1.x) | **7.0.11+** | **17** | Lựa chọn mặc định cho dự án mới dùng Framework 7 khi đã xác nhận các phụ thuộc liên quan |

**Cách đọc bảng:**

- Các cặp Framework 6.1 ↔ Spring Vault 3.1 và Framework 6.2 ↔ Spring Vault 3.2 là điểm khởi đầu cho ứng dụng hiện hữu. Không đặt Spring Vault 4.x vào Framework 6.x rồi trông chờ dependency resolver tự xử lý xung đột.
- Spring Vault 4.x nâng nền lên **Spring Framework 7**, nhưng **không đòi Java 21**: Java 17 vẫn là mức tối thiểu công bố. Có thể dùng JDK mới hơn khi toàn bộ stack và môi trường chạy hỗ trợ.
- Spring Boot 4.0/4.1 dùng nền Framework 7.0; đó là ngữ cảnh tự nhiên để cân nhắc Spring Vault 4.0/4.1. Nếu dùng Spring Boot 4.2 / Framework 7.1, cần đối chiếu BOM và chạy thử tích hợp; riêng bảng minimum Framework 7.0.11 chưa chứng minh mọi tổ hợp Framework 7.1 đều đã được kiểm thử.
- Tài liệu Getting Started của một số nhánh Spring Vault 3.x còn chứa dòng Java SE 6 mang tính lịch sử. **Không dùng dòng đó làm căn cứ triển khai**: Spring Framework 6.x yêu cầu **Java 17 trở lên**.

Nguồn đối chiếu: [Spring Vault 3.1 dependencies](https://docs.spring.io/spring-vault/reference/3.1/introduction/dependencies.html), [3.2 dependencies](https://docs.spring.io/spring-vault/reference/3.2/introduction/dependencies.html), [4.0 dependencies](https://docs.spring.io/spring-vault/reference/4.0/introduction/dependencies.html), [4.1 dependencies](https://docs.spring.io/spring-vault/reference/introduction/dependencies.html) và [Spring Framework overview](https://docs.spring.io/spring-framework/reference/7.0/overview.html).

### Quy trình quyết định

1. **Chốt runtime Java:** kiểm tra `java -version` ở môi trường thật và Java toolchain của build. Nếu vẫn ở Java 8/11, phải có kế hoạch nâng JDK trước khi chọn các dòng trong bảng.
2. **Xác định Spring Framework đang được giải quyết:** dựa vào `spring-core`, `spring-context`, `spring-web` hoặc BOM của Boot, không chỉ đọc phiên bản khai báo trong một dependency trực tiếp.
3. **Chọn cùng thế hệ thư viện:** Framework 6.1 → Spring Vault 3.1; Framework 6.2 → 3.2; Framework 7 → Spring Vault 4.x. Với dự án mới dùng Framework 7, bắt đầu từ bản vá ổn định mới nhất của dòng 4.1.
4. **Chọn cách tích hợp:** chỉ cần API `VaultTemplate`/Transit/PKI thì dùng `spring-vault-core`; cần nạp secrets thành property khi khởi động thì xét `spring-cloud-starter-vault-config` và BOM Spring Cloud.
5. **Đánh giá bản vá bảo mật và môi trường Vault thực tế:** kiểm tra security advisory, ACL, phương thức xác thực workload, mount KV v1/v2, lease, Transit/PKI trên Vault server của hệ thống.
6. **Khóa bộ phiên bản, chạy kiểm tra:** xem dependency tree rồi thực hiện ít nhất một bài kiểm thử tích hợp với Vault và policy tương đương môi trường chạy.

### Ví dụ lựa chọn

| Tình huống | Hướng xử lý |
| --- | --- |
| Java 17 + Spring Boot 3.5 + Spring Framework 6.2 | Bắt đầu kiểm tra Spring Vault **3.2.x** và patch tương thích; không tự nâng Spring Vault lên 4.x khi Framework còn 6.2 |
| Java 21 + Spring Boot 4.1 + Spring Framework 7.0 | Cân nhắc **Spring Vault 4.1.2**, duy trì BOM Boot và kiểm thử Jackson/HTTP client |
| Java 17 + Spring Framework 6.1 trong ứng dụng lâu năm | Duy trì nhánh **3.1.x** khi chưa thể nâng, kiểm tra tình trạng hỗ trợ/bản vá; lập kế hoạch nâng Framework cùng Spring Vault |
| Spring Boot 4.2 + Framework 7.1 | Xác minh release train và tương thích runtime, kiểm thử tích hợp với Spring Vault trước khi chốt phiên bản |

## 3. Khai báo dependency khi dùng trực tiếp Spring Vault Core

Artifact chính là **`org.springframework.vault:spring-vault-core`**. Nó cung cấp `VaultTemplate` để làm việc với KV secrets, xác thực, token, lease, Transit và PKI. Chọn bản vá cụ thể có thể lặp lại trong CI; hạn chế dùng phiên bản động hoặc `-SNAPSHOT` ở production.

### Maven: ứng dụng đã dùng Spring Boot 4.0/4.1 BOM

Trong `pom.xml` đã có Spring Boot parent hoặc dependency management tương ứng, thêm:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.vault</groupId>
        <artifactId>spring-vault-core</artifactId>
        <version>4.1.2</version>
    </dependency>

    <!-- Jackson 3: phiên bản lấy từ BOM Spring Boot 4.x -->
    <dependency>
        <groupId>tools.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
</dependencies>
```

Ví dụ này **giả định BOM Spring Boot đã có sẵn** và quản lý Jackson 3. Nếu viết ứng dụng Spring Framework thuần không dùng Boot, phải tự quản lý các phiên bản Spring Framework, Jackson, HTTP client và thư viện liên quan một cách đồng bộ (có thể import Spring Framework BOM). Không sao chép đoạn phụ thuộc thiếu `version` của Jackson vào POM không có BOM.

### Gradle Kotlin DSL: ứng dụng đã dùng Spring Boot 4.0/4.1 BOM

```kotlin
dependencies {
    implementation("org.springframework.vault:spring-vault-core:4.1.2")
    // Phiên bản Jackson 3 do Spring Boot BOM quản lý
    implementation("tools.jackson.core:jackson-databind")
}
```

Đoạn Gradle cũng giả định dependency management của Spring Boot đã được cấu hình. Với Spring Framework 6.2 / Spring Boot 3.5, thay dependency của Spring Vault bằng dòng tương ứng:

```xml
<dependency>
    <groupId>org.springframework.vault</groupId>
    <artifactId>spring-vault-core</artifactId>
    <version>3.2.1</version>
</dependency>
```

Ở dự án Boot 3.x, giữ bộ Spring Framework và Jackson 2 do BOM Boot 3.x quản lý. Không đưa nhóm artifact Jackson 3 `tools.jackson.core` vào chỉ vì thấy ví dụ dành cho Spring Vault 4.x.

### Chú ý riêng với Jackson trong Spring Vault 4.x

Spring Vault 4.x hỗ trợ Jackson 3 và duy trì tương thích với Jackson 2, nhưng **không tự kéo Jackson vào transitively chỉ để chọn hộ ứng dụng**. Với chương trình mới dùng Framework 7, nên ưu tiên Jackson 3 (`tools.jackson.core:jackson-databind`) và giữ phiên bản theo BOM. Khi cả Jackson 2 và 3 cùng có mặt, Spring Vault ưu tiên Jackson 3. Vì vậy hãy kiểm tra cả **dependency tree** và xử lý JSON/POJO thực tế thay vì chỉ dựa vào việc biên dịch thành công.

Nguồn: [Spring Vault 4.1 dependencies](https://docs.spring.io/spring-vault/reference/introduction/dependencies.html) và [Spring Vault 4.0 GA](https://spring.io/blog/2025/11/18/spring-vault-4-0-goes-ga/).

## 4. Spring Vault Core khác Spring Cloud Vault ở đâu?

**Spring Vault Core** phù hợp khi code chủ động gọi `VaultTemplate`, đọc/ghi KV, tạo ciphertext bằng Transit, ký/cấp chứng chỉ qua PKI, hoặc quản lý token và lease bằng API. Ứng dụng có thể dùng nó mà không cần Spring Boot.

**Spring Cloud Vault** phù hợp khi ứng dụng Spring Boot cần lấy giá trị từ Vault đưa vào hệ thống `Environment` và quá trình nạp cấu hình. Dependency starter thường gặp:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-vault-config</artifactId>
</dependency>
```

Trong trường hợp này, hãy **import Spring Cloud BOM phù hợp với Spring Boot** và để release train quản lý phiên bản starter cùng các thư viện được kéo theo; tránh ép độc lập `spring-vault-core` sang dòng khác. Ví dụ, [Spring Cloud release train compatibility](https://spring.io/projects/spring-cloud/) ghi Spring Cloud 2025.0.x cho Boot 3.5.x và 2025.1.x cho Boot 4.0.x/4.1.x (có điều kiện từ bản vá release train được công bố). Kiểm tra chi tiết từng patch và BOM thực tế.

Từ Spring Boot 2.4 / Spring Cloud Vault 3.0, cách được ưu tiên để nhập cấu hình là **Config Data API**, ví dụ `spring.config.import: vault://`, thay cho giả định mọi dự án đều cần `bootstrap.yml`. Việc nhập cấu hình, phương thức xác thực workload và policy sẽ được cấu hình riêng theo môi trường.

Không thêm cả starter và core với hai số phiên bản khác nhau chỉ vì cần vừa nạp config vừa gọi `VaultTemplate`. Hãy kiểm tra phiên bản `spring-vault-core` mà starter thực sự resolve; chỉ ghi đè khi có căn cứ về tính tương thích và đã kiểm thử.

Nguồn: [Spring Cloud Vault Quick Start](https://docs.spring.io/spring-cloud-vault/reference/quickstart.html), [Spring Cloud compatibility](https://spring.io/projects/spring-cloud/).

## 5. Kiểm tra phiên bản đang chạy, không chỉ phiên bản được khai báo

Một POM có thể khai báo Spring Vault 4.1.2, nhưng bản `spring-core` trên runtime lại bị một BOM hoặc dependency override xuống 6.x. Tình huống này thường gây `NoSuchMethodError`, `NoClassDefFoundError`, `ClassNotFoundException` hoặc lỗi tạo bean khi khởi động.

**Với Maven:**

```bash
java -version
mvn -version
mvn dependency:tree
mvn help:effective-pom
```

Trong kết quả, tìm các artifact `spring-vault-core`, `spring-core`, `spring-context`, `spring-web`, `spring-cloud-vault-config`, `jackson-databind`. Với dependency trùng phiên bản, kiểm tra nhánh nào thắng khi Maven resolve.

**Với Gradle:**

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-vault-core
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-core
./gradlew dependencyInsight --configuration runtimeClasspath --dependency jackson-databind
```

Trên Windows có thể thay `./gradlew` bằng `gradlew.bat`. Kiểm tra **runtimeClasspath**, vì build thành công chưa chắc các phiên bản đóng gói và thực thi đúng. Nếu ứng dụng dùng BOM Spring Boot/Spring Cloud, xem phiên bản đã resolve thay vì đoán từ tên starter.

Đối với dịch vụ đã triển khai, còn phải xác minh JDK bên trong image/container và phiên bản artifact cuối cùng được phát hành. Việc đổi Java trên máy lập trình không tự đổi Java của runtime production.

## 6. Khi nâng từ Spring Vault 3.x lên 4.x

Đây là một đợt **nâng nền tảng**: Spring Vault 4.0 chuyển baseline lên Spring Framework 7, thêm hỗ trợ `RestClient`, thích ứng Jackson 3 (vẫn giữ đường tương thích Jackson 2) và loại bỏ một số API đã deprecated. Spring Vault 4.1 bổ sung các API phục vụ truy cập và quản lý secret/chứng chỉ như `VaultClient` và các abstraction quản lý vòng đời. Vì vậy việc đổi riêng `<version>3.2.1</version>` thành `4.1.2` thường chưa đủ.

Một kế hoạch nâng cấp có thể kiểm chứng:

1. Ghi lại bộ `JDK + Spring Boot/BOM + Spring Framework + Spring Cloud (nếu có) + Spring Vault` đang chạy; xác nhận dự án có thể lên **Framework 7**.
2. Nâng Boot/BOM và các thư viện Spring liên quan cùng một đợt, xử lý các thay đổi biên dịch của API cũ; kiểm tra đặc biệt code tùy biến HTTP client, authentication, session manager và object mapping.
3. Chọn bản vá Spring Vault 4.x được hỗ trợ, chuẩn hóa Jackson 3 hoặc phương án Jackson 2 có chủ đích; loại bỏ override dependency không còn phù hợp.
4. Chạy kiểm thử gọi Vault theo **workload identity** thực tế (ví dụ Kubernetes, JWT hoặc AppRole), với ACL chỉ cho phép đúng đường dẫn; không dùng root token làm bằng chứng tích hợp production.
5. Kiểm thử cả KV v1/v2, làm mới token/lease, Transit encrypt/decrypt, PKI issue/renew và cách ứng dụng phản ứng khi Vault trả `403`, `404` hoặc timeout. Đối chiếu các API và hành vi với tài liệu **đúng phiên bản**.

**Không đánh đồng mức tương thích client với tương thích Vault server.** KV v1 và KV v2 có path/API khác nhau; policy có thể chặn request dù Maven dependency hoàn toàn đúng. Tương tự, token hết hạn hoặc thiếu quyền Transit/PKI là lỗi cấu hình hay quyền truy cập, không tự động là lỗi chọn phiên bản Spring Vault.

## 7. Bảo mật và tiêu chí chấp nhận trước khi chốt version

Ngày **19/11/2026**, Spring công bố **Spring Vault 4.0.5 và 4.1.2** có bản sửa cho **CVE-2026-41698** (path traversal liên quan tham số đường dẫn secret chưa được làm sạch). Đây là lý do không chọn ngẫu nhiên một bản 4.0.0/4.1.0 chỉ vì nó thuộc đúng dòng. Với nhánh 3.x, phải kiểm tra advisory, tình trạng hỗ trợ và kênh cung cấp bản vá tương ứng; không tự kết luận nhánh cũ an toàn chỉ từ bảng tương thích API.

Trước khi chấp nhận một bộ phiên bản, cần xác nhận:

- Build và chạy trên **JDK production**; dependency tree không trộn Framework 6 và 7 hoặc các bản vá mâu thuẫn.
- Các thư viện Spring Vault, Spring Framework và Spring Cloud (nếu dùng) đi với cùng BOM/release train đã kiểm tra.
- Kết nối TLS, phương thức xác thực workload, quyền Vault policy và KV mount đúng trong môi trường test.
- Một luồng đọc secret, một luồng mã hóa Transit hoặc cấp chứng chỉ PKI (theo chức năng dịch vụ), và một kịch bản token/lease hết hạn hoạt động theo mong đợi.
- Lỗi mạng/Vault không sẵn sàng được xử lý có timeout, log/metric có thể quan sát, và **không ghi plaintext secret hoặc token vào log**.
- Bản vá đang chọn đã được kiểm tra lại với trang release và security advisory ở ngày phát hành ứng dụng.

## 8. Ghi nhớ

**Java 17+ → xác định Spring Framework → chọn đúng dòng Spring Vault → để BOM quản lý các thư viện liên quan → xem dependency thực tế → kiểm thử tích hợp với Vault.** Với ứng dụng mới đang dùng Spring Framework 7.0, Spring Vault **4.1.2** là mốc ổn định để bắt đầu tại ngày 25/11/2026. Với ứng dụng còn ở Framework 6.x, ưu tiên đường nâng cấp có kiểm soát và đánh giá khả năng nhận bản vá thay vì chỉ đổi dependency.

### Nguồn chính thức để kiểm tra lại

- [Spring Vault – trang dự án và bản phát hành](https://spring.io/projects/spring-vault/)
- [Spring Vault 3.1 – Dependencies](https://docs.spring.io/spring-vault/reference/3.1/introduction/dependencies.html)
- [Spring Vault 3.2 – Dependencies](https://docs.spring.io/spring-vault/reference/3.2/introduction/dependencies.html)
- [Spring Vault 4.0 – Dependencies](https://docs.spring.io/spring-vault/reference/4.0/introduction/dependencies.html)
- [Spring Vault 4.1 – Dependencies](https://docs.spring.io/spring-vault/reference/introduction/dependencies.html)
- [Spring Vault 4.0.5 và 4.1.2 – thông báo bảo mật, 19/11/2026](https://spring.io/blog/2026/11/19/spring-vault-4-0-5-4-1-2-available/)
- [Spring Framework – Overview](https://docs.spring.io/spring-framework/reference/7.0/overview.html)
- [Spring Cloud – Release train compatibility](https://spring.io/projects/spring-cloud/)
