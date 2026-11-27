# Quản lý version bằng Spring Modulith BOM

Spring Modulith được chia thành nhiều artifact để ứng dụng chỉ thêm những tính năng cần thiết, chẳng hạn module model, runtime support, integration kiểm thử hoặc event publication registry. Các artifact này được phát hành theo một dòng phiên bản có quan hệ với nhau. Nếu khai báo version riêng cho từng dependency, dự án có thể vô tình kết hợp các module Modulith không cùng phiên bản và gặp lỗi tương thích ở compile time hoặc runtime.

Spring Modulith cung cấp Bill of Materials (BOM) để quản lý version tập trung. Khi import `spring-modulith-bom`, build tool nhận được các version được khuyến nghị cho những artifact thuộc Spring Modulith. Sau đó, khi khai báo dependency, nhóm có thể bỏ version ở từng artifact và để BOM cung cấp.

## 1. BOM giải quyết vấn đề gì?

BOM là một POM chuyên quản lý dependency version thông qua phần `dependencyManagement`. Nó mô tả version nên dùng cho một nhóm artifact có liên quan. BOM không tự thêm các thư viện vào classpath; ứng dụng vẫn phải khai báo những artifact thực sự cần sử dụng.

Ví dụ, một ứng dụng có thể cần các artifact sau:

| Artifact | Mục đích |
|---|---|
| `spring-modulith-starter-core` | Các tính năng cốt lõi và module model |
| `spring-modulith-starter-test` | Hỗ trợ kiểm thử application module |
| `spring-modulith-runtime` | Truy cập module model và hỗ trợ runtime |
| `spring-modulith-starter-jdbc` | Starter cho event publication registry dùng JDBC |

Nếu khai báo từng dependency với version riêng, cấu hình có thể trở nên như sau:

```groovy
dependencies {
    implementation 'org.springframework.modulith:spring-modulith-starter-core:2.2.0'
    testImplementation 'org.springframework.modulith:spring-modulith-starter-test:2.1.3'
    runtimeOnly 'org.springframework.modulith:spring-modulith-runtime:2.2.0'
}
```

Ví dụ này trộn hai version Modulith khác nhau. Dù build có thể giải quyết được một số dependency bắc cầu, nhóm vẫn phải tự xác minh rằng các API và implementation tương thích. Khi sử dụng BOM, version được quản lý tại một điểm duy nhất.

## 2. Chọn version Spring Modulith tương thích với Spring Boot

Trước khi import BOM, hãy chọn dòng Spring Modulith phù hợp với Spring Boot mà dự án đang sử dụng. BOM chỉ quản lý version của các artifact trong hệ sinh thái Spring Modulith; nó không tự quyết định hoặc nâng version Spring Boot.

Tài liệu Spring Modulith công bố các dòng release ổn định và bảng tương thích Spring Boot. Ví dụ cấu hình dưới đây dùng `2.2.0`, là version hiển thị trong reference documentation hiện hành tại thời điểm biên soạn. Khi áp dụng vào dự án khác, hãy thay bằng release phù hợp với Spring Boot và chính sách nâng cấp của dự án.

Không nên chọn version chỉ vì đó là số lớn nhất trên Maven Central. Hãy kiểm tra:

1. Phiên bản Spring Boot hiện tại và dòng Modulith tương thích.
2. Những artifact Modulith mà ứng dụng thực sự cần.
3. Release note nếu nâng qua một minor hoặc major version.
4. Các thay đổi API hoặc cấu hình có ảnh hưởng tới code hiện tại.
5. Quy tắc quản lý dependency của dự án, bao gồm Spring Boot BOM hoặc corporate BOM nếu có.

## 3. Import Spring Modulith BOM trong Maven

Trong Maven, import BOM bên trong `dependencyManagement` của parent POM. Có thể khai báo version BOM thành một property để nâng cấp tại một vị trí:

```xml
<properties>
    <spring-modulith.version>2.2.0</spring-modulith.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-bom</artifactId>
            <version>${spring-modulith.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Hai khai báo `type` và `scope` có ý nghĩa quan trọng:

- `type` là `pom` vì BOM được phát hành dưới dạng Maven POM.
- `scope` là `import` để đưa các dependency management entry của BOM vào `dependencyManagement` hiện tại.

Sau khi import BOM, khai báo các artifact cần dùng mà không phải ghi version:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-core</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

</dependencies>
```

Maven lấy version được quản lý từ BOM. BOM không tự thêm các artifact vào ứng dụng; các dependency trong `<dependencies>` mới quyết định thư viện nào được sử dụng.

Nếu ứng dụng cần JDBC event publication registry, có thể dùng `spring-modulith-starter-jdbc`. Starter này đã bao gồm `spring-modulith-starter-core`, nên khi chọn starter JDBC không cần khai báo thêm starter core lần nữa.

### Dùng BOM trong Maven multi-module

Nếu dự án có parent POM và nhiều module con, đặt import BOM trong `dependencyManagement` của parent. Các module con kế thừa dependency management từ parent và có thể khai báo artifact Modulith mà không ghi version.

```text
shop-parent
├── pom.xml                 <- import spring-modulith-bom
├── shop-application
│   └── pom.xml             <- khai báo starter-core, runtime...
├── shop-architecture-tests
│   └── pom.xml             <- khai báo starter-test
└── shop-adapters
    └── pom.xml             <- khai báo integration cần thiết
```

Lưu ý rằng dependency management được kế thừa qua quan hệ parent POM. Nếu một POM chỉ được liệt kê trong `<modules>` nhưng không kế thừa parent chứa BOM, module đó không tự động nhận các version được quản lý từ parent.

## 4. Import BOM trong Gradle Kotlin DSL

Gradle hỗ trợ Maven BOM thông qua `platform(…)`. Khai báo platform trong dependency configuration, sau đó thêm các artifact Modulith không có version:

```kotlin
dependencies {
    implementation(platform("org.springframework.modulith:spring-modulith-bom:2.2.0"))

    implementation("org.springframework.modulith:spring-modulith-starter-core")
    testImplementation("org.springframework.modulith:spring-modulith-starter-test")
}
```

`platform(…)` yêu cầu Gradle đọc các dependency constraint trong BOM. Những dependency Modulith được khai báo trong các configuration liên quan sẽ nhận version do platform quản lý.

## 5. Import BOM trong Gradle Groovy DSL

Nếu dự án sử dụng `build.gradle`, cú pháp tương đương là:

```groovy
dependencies {
    implementation platform('org.springframework.modulith:spring-modulith-bom:2.2.0')

    implementation 'org.springframework.modulith:spring-modulith-starter-core'
    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
}
```

Một lựa chọn khác là dùng plugin `io.spring.dependency-management` với khối `dependencyManagement`:

```groovy
dependencyManagement {
    imports {
        mavenBom 'org.springframework.modulith:spring-modulith-bom:2.2.0'
    }
}
```

Cách dùng plugin thường xuất hiện trong các dự án đã áp dụng Spring Boot Gradle plugin hoặc Spring dependency management plugin. Với Gradle hiện đại, `platform(…)` là cách native để import BOM và không yêu cầu thêm plugin quản lý dependency chỉ vì mục đích này.

## 6. BOM không tự thêm starter hoặc tính năng

Một hiểu nhầm phổ biến là chỉ cần import `spring-modulith-bom` thì toàn bộ tính năng Spring Modulith đã có trong ứng dụng. BOM chỉ cung cấp thông tin version. Hãy chọn dependency theo tính năng cần dùng:

| Nhu cầu | Artifact có thể cần | Scope thường dùng |
|---|---|---|
| API và module model cơ bản | `spring-modulith-starter-core` | Compile |
| Kiểm thử application module | `spring-modulith-starter-test` | Test |
| Runtime module model và initializer | `spring-modulith-runtime` | Runtime |
| Event publication registry với JDBC | `spring-modulith-starter-jdbc` hoặc artifact JDBC phù hợp | Tùy starter và cách cấu hình |
| Expose module structure qua Actuator | `spring-modulith-starter-insight` hoặc `spring-modulith-actuator` | Runtime |

Các starter có thể kéo theo một nhóm artifact liên quan. Ví dụ `spring-modulith-starter-jdbc` đã bao gồm `spring-modulith-starter-core` cùng các module event API, core, JDBC và Jackson cần thiết. Trước khi thêm một dependency đơn lẻ, kiểm tra bảng Spring Modulith modules để tránh khai báo trùng các thành phần mà starter đã cung cấp.

## 7. Kết hợp Spring Boot BOM và Spring Modulith BOM

Nhiều ứng dụng Spring Boot đã import `spring-boot-dependencies` thông qua Spring Boot parent hoặc dependency management. Spring Boot BOM quản lý version của hệ sinh thái Spring Boot; Spring Modulith BOM quản lý version các artifact Modulith.

Ví dụ Maven có thể dùng cả hai BOM:

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

        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-bom</artifactId>
            <version>${spring-modulith.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Nếu dùng `spring-boot-starter-parent`, nhiều version Spring Boot đã được quản lý sẵn; không cần import lại Spring Boot BOM một cách dư thừa. Chỉ bổ sung Spring Modulith BOM nếu nó chưa được quản lý bởi parent hoặc corporate BOM.

Khi hai BOM quản lý cùng một dependency, cần xem xét quy tắc precedence của Maven và effective POM để biết version nào đang được áp dụng. Tránh giải quyết xung đột bằng cách thêm version tùy tiện ở nhiều module con.

Trong Gradle, có thể import nhiều platform:

```kotlin
dependencies {
    implementation(platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES))
    implementation(platform("org.springframework.modulith:spring-modulith-bom:2.2.0"))

    implementation("org.springframework.modulith:spring-modulith-starter-core")
}
```

Ví dụ này minh họa việc áp dụng hai platform. Nếu dự án đã dùng Spring Boot plugin và cơ chế quản lý dependency tương ứng, hãy tuân theo cấu hình hiện tại thay vì thêm platform trùng lặp.

## 8. Quản lý version BOM tại một vị trí

Để nâng cấp dễ kiểm soát, lưu version BOM trong property hoặc version catalog thay vì lặp lại literal version ở nhiều build file.

Trong Maven:

```xml
<properties>
    <spring-modulith.version>2.2.0</spring-modulith.version>
</properties>
```

Trong Gradle Kotlin DSL, có thể dùng version catalog:

```toml
[versions]
spring-modulith = "2.2.0"

[libraries]
spring-modulith-bom = { module = "org.springframework.modulith:spring-modulith-bom", version.ref = "spring-modulith" }
spring-modulith-core-starter = { module = "org.springframework.modulith:spring-modulith-starter-core" }
spring-modulith-test-starter = { module = "org.springframework.modulith:spring-modulith-starter-test" }
```

Sau đó import BOM alias như một platform:

```kotlin
dependencies {
    implementation(platform(libs.spring.modulith.bom))
    implementation(libs.spring.modulith.core.starter)
    testImplementation(libs.spring.modulith.test.starter)
}
```

Version catalog cung cấp alias và tập trung khai báo tọa độ/version. Platform BOM mới là thành phần đưa các dependency constraint vào quá trình phân giải version. Không nhầm lẫn vai trò của version catalog với BOM.

## 9. Hiểu platform và enforcedPlatform trong Gradle

Gradle có hai cách import BOM thường gặp:

| Cách import | Hành vi | Khi cân nhắc |
|---|---|---|
| `platform(…)` | Dùng version constraint của BOM như version khuyến nghị; các dependency khác trong graph vẫn có thể ảnh hưởng kết quả | Lựa chọn thông thường để phối hợp với các platform khác |
| `enforcedPlatform(…)` | Chuyển các version constraint thành ràng buộc nghiêm ngặt và ép các dependency trong graph theo BOM | Khi dự án chủ động muốn khóa toàn bộ nhóm version và hiểu rõ ảnh hưởng tới consumer |

Ví dụ:

```kotlin
dependencies {
    implementation(enforcedPlatform("org.springframework.modulith:spring-modulith-bom:2.2.0"))
    implementation("org.springframework.modulith:spring-modulith-starter-core")
}
```

Không mặc định dùng `enforcedPlatform` cho mọi dự án. Nó có thể ép version transitive của dependency consumer, đặc biệt khi một thư viện được publish và platform bị truyền sang các project khác. Hãy bắt đầu với `platform(…)`; chỉ dùng `enforcedPlatform(…)` khi chính sách dependency cần tính nghiêm ngặt đó.

## 10. Kiểm tra version đã được resolve

Sau khi import BOM, hãy kiểm tra version mà build tool thực sự chọn. Việc khai báo không có version không có nghĩa chắc chắn dependency graph đã dùng đúng version mong muốn; một dependency khác hoặc rule quản lý khác có thể ảnh hưởng kết quả.

Với Maven, xem POM sau khi đã áp dụng dependency management:

```bash
mvn help:effective-pom
```

Kiểm tra dependency Modulith trong cây dependency:

```bash
mvn dependency:tree -Dincludes=org.springframework.modulith
```

Với Gradle, xem runtime classpath:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Để biết lý do một artifact nhận version cụ thể, dùng `dependencyInsight`:

```bash
./gradlew dependencyInsight \
  --dependency spring-modulith-core \
  --configuration runtimeClasspath
```

Trong output, kiểm tra các artifact `org.springframework.modulith` có version đồng bộ theo BOM đã chọn hay không. Nếu thấy version được nâng hoặc hạ bởi một constraint khác, đọc phần giải thích của dependency resolution trước khi thay đổi cấu hình.

## 11. Những lỗi thường gặp khi quản lý BOM

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Dependency vẫn báo thiếu version | BOM chưa được import hoặc module con không kế thừa dependency management | Kiểm tra parent POM, `dependencyManagement` hoặc Gradle platform configuration |
| Chỉ một số artifact Modulith được quản lý | Artifact không thuộc BOM hoặc tọa độ bị viết sai | Kiểm tra artifact trong bảng modules và dependency coordinates |
| Nhiều version Modulith xuất hiện trong cây dependency | Có version tường minh hoặc platform khác ảnh hưởng resolution | Dùng effective POM/dependencyInsight để tìm nguồn version |
| Nâng BOM làm build hoặc runtime lỗi | Release mới có thay đổi tương thích hoặc Spring Boot không phù hợp | Kiểm tra compatibility matrix, release notes và nâng cấp theo từng bước |
| Import BOM nhưng tính năng không xuất hiện | BOM không tự thêm artifact vào classpath | Khai báo starter hoặc artifact cần thiết trong dependencies |
| Gradle chọn version cao hơn BOM | `platform(…)` là constraint có thể được điều chỉnh bởi graph | Xem dependencyInsight; cân nhắc nâng BOM hoặc chính sách constraint có chủ đích |
| Version khác nhau giữa các subproject | BOM chỉ được import ở một project, không được chia sẻ sang subproject | Áp dụng platform trong từng subproject hoặc convention plugin dùng chung |

## 12. Quy trình nâng cấp Spring Modulith bằng BOM

Khi cần nâng version, hãy thực hiện theo một quy trình có thể review:

1. Kiểm tra version Spring Boot và compatibility matrix của Spring Modulith.
2. Đọc release notes của version đích, đặc biệt khi nâng major hoặc minor.
3. Thay version BOM tại một vị trí duy nhất trong parent POM, Gradle platform hoặc version catalog.
4. Kiểm tra các artifact Modulith đã được resolve theo version mới.
5. Rà soát các dependency được khai báo tường minh hoặc platform khác có thể ghi đè constraint.
6. Chạy build và các test kiến trúc, module test, integration test của dự án trong pipeline tương ứng.
7. Ghi nhận version BOM đã chọn để các module con và môi trường CI dùng cùng cấu hình.

Không nâng riêng `spring-modulith-core` hoặc một integration lên version khác chỉ để xử lý một lỗi cục bộ mà chưa đánh giá toàn bộ nhóm artifact. Nếu cần ngoại lệ, hãy ghi rõ lý do, kiểm tra dependency graph và có kế hoạch đưa cấu hình trở lại trạng thái được BOM quản lý.

## 13. Bài tập tự kiểm tra

Một ứng dụng Spring Boot sử dụng module model, module test và JDBC event publication registry. Hãy hoàn thành các yêu cầu:

1. Import `spring-modulith-bom` trong Maven parent POM hoặc Gradle platform.
2. Khai báo `spring-modulith-starter-test` cùng `spring-modulith-starter-core` nếu chỉ cần tính năng cốt lõi; nếu cần JDBC event registry, dùng `spring-modulith-starter-jdbc` (đã bao gồm starter core) mà không ghi version từng dependency.
3. Kiểm tra BOM không tự thêm các artifact vào classpath nếu dependency chưa được khai báo.
4. Dùng `effective-pom` hoặc `dependencyInsight` để xác nhận version được resolve.
5. Tạo một cấu hình thử nghiệm có version tường minh khác BOM và quan sát cách build tool giải quyết xung đột.
6. Khôi phục cấu hình dùng BOM, sau đó nâng version tại một vị trí và kiểm tra lại toàn bộ dependency Modulith.

| Câu hỏi | Điều cần trả lời |
|---|---|
| BOM có tự thêm `spring-modulith-starter-core` vào classpath không? | Không. BOM chỉ quản lý version; dependency phải được khai báo riêng. |
| Vì sao nên dùng cùng một BOM cho các artifact Modulith? | Để version các thành phần liên quan được phối hợp theo một release. |
| Spring Modulith BOM có thay thế Spring Boot BOM không? | Không. Hai BOM quản lý các nhóm dependency khác nhau và có thể cùng được sử dụng. |
| Gradle `platform` và `enforcedPlatform` khác nhau thế nào? | Một bên cung cấp constraint theo cơ chế resolution thông thường; bên còn lại áp đặt version nghiêm ngặt. |
| Khi một module con không nhận version từ BOM parent Maven, cần kiểm tra gì? | Quan hệ kế thừa parent và vị trí import trong `dependencyManagement`. |

Khi hoàn thành, bạn cần có khả năng đọc một build file và xác định version Spring Modulith đến từ đâu, artifact nào thực sự được đưa vào classpath, cũng như cách kiểm tra version đã resolve trước khi nâng cấp.

## Tài liệu tham khảo

- [Spring Modulith — Reference Documentation: Using Spring Modulith](https://docs.spring.io/spring-modulith/reference/)
- [Spring Modulith — Appendix: Modules and Compatibility](https://docs.spring.io/spring-modulith/reference/appendix.html)
- [Gradle — Platforms and Importing a BOM](https://docs.gradle.org/current/userguide/platforms.html)
- [Gradle — Centralizing Dependencies](https://docs.gradle.org/current/userguide/centralizing_dependencies.html)
