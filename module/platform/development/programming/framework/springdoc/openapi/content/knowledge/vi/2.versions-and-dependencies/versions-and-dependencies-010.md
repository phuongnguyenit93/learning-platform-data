# Khóa phiên bản và kiểm tra cây phụ thuộc

Một ứng dụng Spring Boot có thể chạy tốt trên máy lập trình viên nhưng lỗi sau khi cập nhật thư viện hoặc khi được build ở môi trường khác. Nguyên nhân thường nằm ở việc các phiên bản phụ thuộc được phân giải khác nhau, một thư viện bắc cầu kéo theo phiên bản không tương thích, hoặc nhiều module trong cùng hệ sinh thái bị trộn lẫn.

Với `springdoc-openapi`, quản lý phiên bản cần bắt đầu từ phiên bản Spring Boot và stack web của ứng dụng. Sau đó mới chọn đúng dòng springdoc, khóa phiên bản trực tiếp và kiểm tra các thư viện bắc cầu như Swagger Core, Swagger UI, Spring Framework và Jackson. Cây phụ thuộc cho biết phiên bản nào thực sự được đưa vào classpath; file build chỉ cho biết những gì dự án yêu cầu.

## 1. Vì sao phải khóa phiên bản?

Khi khai báo một dependency, dự án có thể yêu cầu một phiên bản cụ thể hoặc một khoảng phiên bản. Công cụ build tiếp tục phân giải các dependency bắc cầu mà thư viện đó cần. Kết quả cuối cùng là một tập hợp thư viện được đưa vào classpath để biên dịch, kiểm thử và chạy ứng dụng.

Nếu không kiểm soát phiên bản, các lần build có thể nhận kết quả khác nhau do:

- Khai báo phiên bản động như `2.+`, `latest.release` hoặc khoảng phiên bản.
- Dependency bắc cầu được cập nhật trong repository Maven.
- Nhiều thư viện yêu cầu các phiên bản khác nhau của cùng một module.
- BOM hoặc dependency management thay đổi sau khi nâng Spring Boot.
- Plugin build, repository hoặc cấu hình CI sử dụng phiên bản khác với máy phát triển.

Khóa phiên bản giúp một lần build có thể được tái tạo với cùng tập hợp thư viện. Nó cũng làm cho việc review nâng cấp dễ hơn: thay đổi phiên bản xuất hiện rõ trong file cấu hình hoặc lockfile, thay vì âm thầm thay đổi khi build.

Khóa phiên bản không chứng minh rằng hai thư viện tương thích với nhau. Dự án vẫn cần chọn đúng dòng phiên bản, kiểm tra cây phụ thuộc và chạy kiểm thử trên ứng dụng thực tế.

## 2. Chọn dòng springdoc tương thích với Spring Boot

`springdoc-openapi` tích hợp sâu với Spring Boot, Spring Framework, Spring Web MVC/WebFlux và các thư viện tuần tự hóa. Vì vậy, không nên chọn phiên bản springdoc độc lập với phiên bản Spring Boot.

Theo bảng tương thích trong tài liệu springdoc tại thời điểm biên soạn, các dòng chính có quan hệ như sau:

| Spring Boot | Dòng springdoc tương thích được công bố |
|---|---|
| 4.1.x | 3.1.x đến 3.2.x |
| 4.0.x | 3.0.x |
| 3.5.x | 2.8.x đến 2.10.x |
| 3.4.x | 2.7.x đến 2.8.x |
| 3.3.x | 2.6.x |
| 3.2.x | 2.3.x đến 2.5.x |
| 3.1.x | 2.2.x |
| 3.0.x | 2.0.x đến 2.1.x |

Các dòng Spring Boot cũ hơn có thể cần springdoc 1.x và cách khai báo artifact cũ. Dòng 1.8.0 được tài liệu hiện hành ghi nhận là bản kết thúc hỗ trợ mã nguồn mở cho Spring Boot 1.x/2.x. Với dự án đang bảo trì, hãy kiểm tra đúng tài liệu theo nhánh phiên bản thay vì lấy ví dụ từ hướng dẫn của dòng mới.

Bảng tương thích có thể thay đổi khi Spring Boot hoặc springdoc phát hành phiên bản mới. Trước khi nâng cấp, kiểm tra bảng chính thức tại [springdoc-openapi compatibility](https://springdoc.org/#what-is-the-compatibility-matrix-of-springdoc-openapi-with-spring-boot-) hoặc tài liệu tương ứng của nhánh 2.x tại [springdoc.org/v2](https://springdoc.org/v2/).

### 2.1. Chọn đúng starter

Với các dòng springdoc hiện đại, artifact starter thể hiện stack web và nhu cầu giao diện:

| Ứng dụng | Artifact thường dùng |
|---|---|
| Spring MVC, có Swagger UI | `springdoc-openapi-starter-webmvc-ui` |
| Spring MVC, chỉ cần OpenAPI endpoint | `springdoc-openapi-starter-webmvc-api` |
| Spring WebFlux, có Swagger UI | `springdoc-openapi-starter-webflux-ui` |
| Spring WebFlux, chỉ cần OpenAPI endpoint | `springdoc-openapi-starter-webflux-api` |

Chọn MVC hoặc WebFlux theo stack mà ứng dụng đang chạy. Không thêm cả hai starter chỉ để thử; điều đó có thể đưa nhiều cấu hình hoặc thư viện không cần thiết vào classpath. Nếu cần Swagger UI, chọn starter `*-ui`; nếu chỉ phân phối JSON/YAML cho công cụ khác, starter `*-api` có thể phù hợp hơn.

Với springdoc 2.x/3.x, các starter dùng chung một phiên bản springdoc. Tránh trộn starter của nhiều dòng major hoặc khai báo đồng thời artifact legacy 1.x với starter mới. Tên artifact, cấu trúc module và cách cấu hình có thể khác giữa các major.

## 3. Khóa phiên bản trong Maven

### 3.1. Dùng Spring Boot BOM và property cho springdoc

Nếu dự án kế thừa `spring-boot-starter-parent`, Spring Boot đã cung cấp dependency management cho nhiều thư viện trong hệ sinh thái Spring. Nếu không dùng parent, có thể import `spring-boot-dependencies` BOM trong `dependencyManagement`.

Spring Boot BOM quản lý các dependency thuộc hệ sinh thái mà nó hỗ trợ. Hãy khai báo phiên bản springdoc tường minh bằng một property riêng, trừ khi tài liệu của phiên bản đang dùng quy định một cơ chế quản lý khác.

Ví dụ dưới đây dành cho dự án Spring Boot 3.5.x và springdoc 2.10.0:

```xml
<properties>
    <springdoc.version>2.10.0</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
```

Ví dụ này giả định ứng dụng dùng Spring MVC. Nếu ứng dụng dùng WebFlux, thay artifact bằng starter WebFlux tương ứng. Với Spring Boot 4.1.x, chọn một phiên bản springdoc 3.1.x hoặc 3.2.x theo bảng tương thích; ví dụ tài liệu hiện hành sử dụng 3.2.0 cho Boot 4.1.x.

Khi dự án không dùng Spring Boot parent, BOM có thể được import như sau:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Không tự đặt phiên bản riêng cho từng module `spring-core`, `spring-web`, `spring-context` hoặc Jackson nếu chưa có lý do tương thích cụ thể. Việc ghi đè các phiên bản do Spring Boot BOM quản lý có thể tạo ra một tổ hợp mà Spring Boot chưa kiểm thử.

### 3.2. Quản lý dependency bắc cầu

Maven chọn phiên bản dependency theo quy tắc phân giải của nó, trong đó khoảng cách từ dependency gốc và `dependencyManagement` có ảnh hưởng đến kết quả. Khi nhiều nhánh yêu cầu cùng một artifact ở các phiên bản khác nhau, cây phụ thuộc có thể hiển thị một phiên bản được chọn và những phiên bản bị bỏ qua.

Nếu có lý do chính đáng để điều chỉnh một dependency bắc cầu, hãy quản lý phiên bản ở `dependencyManagement` tại cấp phù hợp và ghi rõ lý do. Không thêm dependency trực tiếp chỉ để ép một phiên bản mà chưa xác minh tương thích với springdoc và Spring Boot.

Maven không cung cấp lockfile dependency tích hợp theo cách Gradle làm. Để build có thể tái tạo, hãy:

- Khai báo phiên bản trực tiếp và phiên bản plugin build một cách tường minh.
- Dùng BOM đã chọn và giữ phiên bản BOM ổn định.
- Tránh phiên bản động và dependency `SNAPSHOT` trong bản build phát hành.
- Dùng Maven Enforcer để phát hiện xung đột hoặc phiên bản bắc cầu thấp hơn yêu cầu.
- Dùng Maven Wrapper để cố định phiên bản Maven mà dự án sử dụng.
- Giữ cấu hình repository ổn định giữa máy phát triển và CI.

Có thể thêm các rule `dependencyConvergence` và `requireUpperBoundDeps` của Maven Enforcer để phát hiện một số trường hợp lệch phiên bản:

```xml
<rules>
    <dependencyConvergence/>
    <requireUpperBoundDeps/>
</rules>
```

Đoạn trên là phần `rules` trong cấu hình goal `maven-enforcer-plugin`. Cần khai báo plugin và phiên bản plugin trong `build/plugins` hoặc `pluginManagement` của dự án. Hai rule này có thể phát hiện xung đột cần xử lý; nếu một khác biệt phiên bản là chủ ý, hãy giải thích và quản lý ngoại lệ rõ ràng.

## 4. Khóa phiên bản trong Gradle

### 4.1. Khai báo phiên bản và BOM

Gradle có thể dùng Spring Boot BOM thông qua dependency platform. Ví dụ dưới đây minh họa Spring Boot 4.1.2 cùng springdoc 3.2.0:

```kotlin
val springBootVersion = "4.1.2"
val springdocVersion = "3.2.0"

dependencies {
    implementation(platform(
        "org.springframework.boot:spring-boot-dependencies:$springBootVersion"
    ))

    implementation(
        "org.springdoc:springdoc-openapi-starter-webmvc-ui:$springdocVersion"
    )
}
```

Nếu dự án đã dùng Spring Boot Gradle plugin cùng plugin quản lý dependency, hãy làm theo cách import BOM mà dự án đang áp dụng để tránh khai báo hai cơ chế quản lý phiên bản chồng chéo. Spring Boot BOM quản lý các dependency được BOM bao phủ; phiên bản springdoc vẫn cần được chọn theo bảng tương thích.

Có thể tập trung phiên bản trong `gradle/libs.versions.toml` để các module dùng cùng một giá trị:

```toml
[versions]
spring-boot = "4.1.2"
springdoc = "3.2.0"

[libraries]
spring-boot-bom = { module = "org.springframework.boot:spring-boot-dependencies", version.ref = "spring-boot" }
springdoc-webmvc-ui = { module = "org.springdoc:springdoc-openapi-starter-webmvc-ui", version.ref = "springdoc" }
```

Sau đó tham chiếu alias trong `build.gradle.kts`:

```kotlin
dependencies {
    implementation(platform(libs.spring.boot.bom))
    implementation(libs.springdoc.webmvc.ui)
}
```

Version catalog giúp thống nhất phiên bản được khai báo. Nó chưa khóa toàn bộ phiên bản bắc cầu được Gradle phân giải; dependency locking giải quyết phần đó.

### 4.2. Bật dependency locking

Trong `build.gradle.kts`, bật khóa cho các configuration cần dùng:

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

Trong `build.gradle` dùng Groovy DSL:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Sau khi bật locking, chạy một tác vụ phân giải các dependency cần khóa, ví dụ:

```bash
./gradlew build --write-locks
```

Gradle ghi các phiên bản đã phân giải vào lockfile, thường là `gradle.lockfile` ở cấp project. Với multi-project build, lock state có thể được tạo cho từng project. Commit lockfile cùng mã nguồn để các lần build tiếp theo dùng cùng phiên bản đã khóa.

Khi chủ động nâng cấp dependency, thay đổi version catalog hoặc constraint trước, sau đó chạy lại tác vụ phù hợp với `--write-locks`, review thay đổi lockfile và chạy kiểm thử. Không cập nhật lockfile một cách máy móc mà không xem module nào đã đổi phiên bản.

Dependency locking không thay thế quản lý phiên bản plugin Gradle. Các plugin trong `plugins {}` hoặc `pluginManagement` cần được khai báo phiên bản ổn định riêng.

### 4.3. Xác minh tính toàn vẹn của artifact

Lockfile ghi lại phiên bản đã phân giải. Gradle dependency verification bổ sung kiểm tra checksum hoặc chữ ký của artifact đã tải về. Có thể tạo metadata checksum SHA-256 bằng lệnh:

```bash
./gradlew --write-verification-metadata sha256 build
```

Lệnh tạo hoặc cập nhật `gradle/verification-metadata.xml`. Hãy review và commit file này sau khi xác minh artifact đến từ repository tin cậy. Khi build sau đó tải artifact có checksum không khớp, Gradle sẽ báo lỗi thay vì âm thầm chấp nhận nội dung khác.

Không nên dùng dependency thay đổi nội dung như `SNAPSHOT` để mong đợi một lockfile bảo đảm build tái lập tuyệt đối. Khóa phiên bản không thể bảo đảm nội dung artifact bất biến nếu repository cho phép ghi đè artifact cùng tọa độ.

## 5. Đọc và phân tích cây phụ thuộc

Cây phụ thuộc thể hiện mối quan hệ giữa dependency trực tiếp và các dependency bắc cầu. Khi điều tra vấn đề springdoc, cần tập trung vào cả compile classpath và runtime classpath, vì ứng dụng có thể biên dịch thành công nhưng lỗi khi khởi động.

### 5.1. Maven: `dependency:tree`

Xem toàn bộ cây dependency:

```bash
./mvnw dependency:tree
```

Lọc các nhóm liên quan đến springdoc, Swagger và Spring:

```bash
./mvnw dependency:tree -Dverbose \
  -Dincludes=org.springdoc:*,io.swagger.core.v3:*,org.springframework.boot:*,org.springframework:*
```

Trên Windows PowerShell, dùng `mvnw.cmd` thay cho `./mvnw`:

```powershell
.\mvnw.cmd dependency:tree -Dverbose -Dincludes=org.springdoc:*,io.swagger.core.v3:*,org.springframework.boot:*,org.springframework:*
```

`-Dverbose` giúp quan sát thêm các node bị loại trong quá trình giải quyết xung đột. Khi cần biết phiên bản cuối cùng được Maven quản lý từ đâu, xuất effective POM:

```bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
```

Effective POM thể hiện cấu hình sau khi kế thừa parent và áp dụng profile, property cùng dependency management. Đối chiếu effective POM với `dependency:tree` để hiểu phiên bản được khai báo và phiên bản thực sự được chọn.

### 5.2. Gradle: `dependencies` và `dependencyInsight`

Xem runtime dependency tree:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Tìm lý do một phiên bản springdoc được chọn:

```bash
./gradlew dependencyInsight --dependency springdoc-openapi-starter-webmvc-ui --configuration runtimeClasspath
```

`dependencyInsight` cho biết dependency nào yêu cầu module, phiên bản nào được chọn và lý do chọn phiên bản đó, chẳng hạn do conflict resolution, constraint hoặc dependency locking. Nếu ứng dụng dùng WebFlux, thay tên module trong câu lệnh bằng starter WebFlux.

Có thể kiểm tra thêm compile classpath:

```bash
./gradlew dependencies --configuration compileClasspath
```

Nếu module xuất hiện ở compile classpath nhưng không có ở runtime classpath, hãy kiểm tra scope/configuration đã khai báo. Nếu nhiều phiên bản xuất hiện trong báo cáo, đọc phần selection reason để biết Gradle đã giải quyết xung đột như thế nào.

## 6. Đọc cây phụ thuộc trong một tình huống thực tế

Giả sử ứng dụng khai báo:

```text
org.springdoc:springdoc-openapi-starter-webmvc-ui:3.2.0
```

Starter này kéo theo những module cần thiết cho OpenAPI và Swagger UI. Một số dependency bắc cầu có thể bao gồm các module `org.springdoc`, `io.swagger.core.v3`, thư viện Spring và thư viện JSON. Phiên bản cuối cùng của từng module phụ thuộc vào metadata của starter, BOM, constraint và các dependency khác trong ứng dụng.

Khi đọc kết quả, hãy trả lời lần lượt:

1. Có đúng một starter springdoc phù hợp với stack MVC hoặc WebFlux không?
2. Các module `org.springdoc` có cùng dòng phiên bản không?
3. Swagger Core và các module liên quan có bị kéo về phiên bản khác do dependency trực tiếp khác không?
4. Các thư viện Spring Framework, Spring Boot và Jackson có nằm trong dải mà Spring Boot BOM quản lý không?
5. Có node nào bị loại do xung đột phiên bản không? Phiên bản được chọn có phải là phiên bản mà dự án dự định sử dụng không?
6. Runtime classpath có chứa các module cần thiết để tạo `/v3/api-docs` và hiển thị Swagger UI không?

Không phải mọi dependency có nhiều phiên bản được yêu cầu đều là lỗi. Maven và Gradle có quy tắc chọn phiên bản; điều cần xác minh là phiên bản cuối cùng có tương thích với toàn bộ stack hay không. Nếu phải thêm `exclusion`, hãy xác định dependency nào đưa module vào cây và kiểm tra module thay thế có cung cấp đúng API mà thư viện cần hay không.

## 7. Dấu hiệu cây phụ thuộc có vấn đề

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `NoSuchMethodError` hoặc `NoClassDefFoundError` khi khởi động | Thư viện biên dịch và thư viện runtime không cùng API/phiên bản | Xem runtime tree, tìm module Spring hoặc Swagger bị ghi đè. |
| Lỗi tạo bean hoặc auto-configuration | Springdoc không tương thích với dòng Spring Boot/Spring Framework | Đối chiếu compatibility matrix và effective dependency tree. |
| `/v3/api-docs` trả lỗi hoặc không tồn tại | Starter sai stack, thiếu module API hoặc auto-configuration không được nạp | Kiểm tra artifact trực tiếp và log lúc khởi động. |
| Swagger UI không tải được tài liệu | Thiếu starter UI, đường dẫn cấu hình sai hoặc tài nguyên UI không có trong runtime classpath | Kiểm tra artifact `*-ui`, cấu hình path và request mạng của trình duyệt. |
| Cùng một thư viện bị yêu cầu ở nhiều phiên bản | Nhiều dependency trực tiếp/bắc cầu hoặc BOM không thống nhất | Dùng `dependency:tree -Dverbose` hoặc `dependencyInsight`. |
| Máy cá nhân chạy nhưng CI lỗi | JDK, Maven/Gradle, repository, profile hoặc lock state khác nhau | So sánh wrapper, toolchain, effective POM và dependency lockfile. |

Không nên chữa mọi lỗi bằng cách nâng tất cả dependency lên phiên bản mới nhất. Hãy tìm module gây xung đột, xác định bên quản lý phiên bản của module đó, rồi thay đổi BOM, constraint hoặc dependency trực tiếp ở đúng vị trí.

## 8. Quy trình nâng cấp springdoc an toàn

Khi nâng Spring Boot hoặc springdoc, thực hiện theo trình tự sau:

1. **Ghi nhận baseline**: lưu phiên bản Java, Spring Boot, springdoc, Maven/Gradle và lockfile hiện tại.
2. **Xác nhận compatibility**: tra bảng tương thích chính thức theo đúng minor Spring Boot; xác định artifact MVC/WebFlux và API/UI.
3. **Thay đổi có kiểm soát**: cập nhật phiên bản springdoc hoặc Spring Boot theo từng bước; để BOM quản lý Spring Framework và thư viện thuộc hệ sinh thái.
4. **Phân giải lại dependency**: chạy `dependency:tree` hoặc `dependencies`/`dependencyInsight`; kiểm tra các phiên bản được chọn và các node bị loại.
5. **Cập nhật khóa**: với Gradle, tạo lại lock state có chủ đích; với Maven, cập nhật BOM/property và các rule Enforcer khi cần.
6. **Kiểm tra ứng dụng**: chạy unit test, integration test, khởi động ứng dụng và truy cập `/v3/api-docs`, `/v3/api-docs.yaml` nếu bật YAML, cùng trang Swagger UI.
7. **So sánh hợp đồng**: kiểm tra thay đổi OpenAPI có làm đổi schema, operation, security hoặc response mà client hiện tại phụ thuộc không.
8. **Review thay đổi build**: commit file cấu hình, lockfile và verification metadata liên quan; ghi lý do nâng cấp và các thay đổi đáng chú ý.

Nếu nâng Spring Boot và springdoc cùng lúc, khi có lỗi sẽ khó xác định nguyên nhân hơn. Trong dự án lớn, hãy chia thay đổi thành các bước nhỏ có thể kiểm tra riêng, đặc biệt khi thay đổi major version.

## 9. Checklist trước khi merge

- [ ] Phiên bản springdoc thuộc dòng tương thích với phiên bản Spring Boot đang dùng.
- [ ] Starter khớp với Spring MVC hoặc WebFlux và nhu cầu UI/API.
- [ ] Các module springdoc được khai báo cùng một phiên bản.
- [ ] Spring Framework, Spring Boot và Jackson được quản lý nhất quán qua BOM hoặc dependency management.
- [ ] Không có phiên bản động hoặc `SNAPSHOT` trong dependency phát hành.
- [ ] Cây runtime đã được kiểm tra; các xung đột và dependency bị loại đã được giải thích.
- [ ] Maven Enforcer hoặc Gradle dependency locking được cấu hình phù hợp với hệ thống build.
- [ ] Lockfile và verification metadata của Gradle đã được cập nhật, review và commit nếu dự án sử dụng chúng.
- [ ] Ứng dụng khởi động được; OpenAPI JSON/YAML và Swagger UI hoạt động.
- [ ] Thay đổi hợp đồng API đã được đánh giá và kiểm thử.

## 10. Tài liệu tham khảo

- [springdoc-openapi: hướng dẫn và bảng tương thích](https://springdoc.org/)
- [springdoc-openapi v2: tài liệu dành cho Spring Boot 3](https://springdoc.org/v2/)
- [Gradle User Manual: Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Gradle User Manual: Viewing and debugging dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Maven Dependency Plugin: dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Maven Enforcer Plugin](https://maven.apache.org/enforcer/maven-enforcer-plugin/)

Khóa phiên bản giúp build có thể tái tạo; cây phụ thuộc giúp giải thích chính xác những gì được đưa vào ứng dụng. Kết hợp hai việc này với bảng tương thích springdoc và kiểm tra endpoint thực tế sẽ giảm đáng kể lỗi do lệch phiên bản khi phát triển, tích hợp và phát hành API.
