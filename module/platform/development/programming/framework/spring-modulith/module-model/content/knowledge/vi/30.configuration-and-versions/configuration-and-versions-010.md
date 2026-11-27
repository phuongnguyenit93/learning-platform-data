# Khóa version để model tái lập trong CI

Spring Modulith xây dựng application module model từ package, class và các dependency mà ứng dụng nhìn thấy trên classpath. Cùng một source code nhưng dùng phiên bản Spring Modulith, Spring Boot, thư viện hoặc JDK khác nhau có thể dẫn đến kết quả phân tích và tài liệu kiến trúc khác nhau. Vì vậy, muốn CI tạo ra cùng một model qua các lần chạy, nhóm cần kiểm soát cả phiên bản trực tiếp, phiên bản bắc cầu và môi trường build.

Mục tiêu của bài học là thiết lập một bộ phiên bản có thể tái lập: dùng BOM để đồng bộ các artifact Spring Modulith, khóa dependency đã phân giải, cố định build tool và JDK, rồi chạy kiểm tra kiến trúc trên cùng cấu hình đó. Việc nâng cấp vẫn cần thiết, nhưng phải là một thay đổi có chủ đích và có thể review.

## 1. Vì sao phiên bản ảnh hưởng đến application module model?

`ApplicationModules.of(ShopApplication.class)` phân tích ứng dụng từ các class và dependency mà quá trình build cung cấp. Mô hình được dùng để phát hiện module, package API, named interface, dependency giữa module, event listener và những cấu trúc liên quan.

Kết quả có thể thay đổi khi:

- Phiên bản Spring Modulith thay đổi cách phát hiện module, kiểu dependency hoặc quy tắc kiểm chứng.
- Phiên bản Spring Framework hoặc Spring Boot thay đổi API, annotation hay cách đăng ký bean mà ứng dụng sử dụng.
- Dependency bắc cầu được nâng cấp và đưa thêm kiểu, annotation hoặc listener vào classpath.
- Phiên bản JDK, compiler hoặc build plugin thay đổi cách biên dịch và đóng gói class.
- Cấu hình component scanning, test runtime hoặc dependency của một source set thay đổi.

Do đó, tái lập model cần kiểm soát nhiều lớp:

| Lớp cần khóa | Ví dụ | Tác động nếu thay đổi tự do |
|---|---|---|
| Release train Spring Modulith | `spring-modulith-core`, `spring-modulith-starter-test`, `spring-modulith-docs` | Các API và quy tắc phân tích có thể không đồng nhất. |
| Nền tảng Spring | Spring Boot và Spring Framework | Thay đổi API, metadata và tích hợp. |
| Dependency bắc cầu | ArchUnit, jMolecules và thư viện runtime khác | Classpath và kết quả phát hiện cấu trúc có thể thay đổi. |
| Build tool và plugin | Gradle/Maven, compiler, test plugin | Cách resolve, compile và chạy test có thể khác. |
| JDK | Bản phân phối và phiên bản JDK dùng trong CI | Khác biệt compiler, runtime và toolchain. |

Một biểu đồ hoặc báo cáo được sinh từ model chỉ có thể tái lập khi source code, dependency graph, cấu hình và môi trường build được kiểm soát đủ chặt.

## 2. Dùng BOM để đồng bộ các artifact Spring Modulith

Spring Modulith phát hành nhiều artifact cùng release train. Nếu mỗi artifact tự khai báo một version riêng, dự án có thể vô tình trộn các phiên bản không tương thích. BOM (`Bill of Materials`) cung cấp một bộ version đã được quản lý thống nhất.

Với Maven, import `spring-modulith-bom` trong `dependencyManagement`. Ví dụ sau minh họa cách tổ chức; version `1.4.0` chỉ là một mốc minh họa, cần chọn release tương thích với phiên bản Spring Boot của dự án theo bảng tương thích chính thức:

```xml
<properties>
    <java.version>21</java.version>
    <spring-modulith.version>1.4.0</spring-modulith.version>
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

Khi BOM quản lý version, dependency không cần lặp lại số version. Nếu cần thêm `spring-modulith-docs` hoặc một starter khác, hãy để BOM quản lý version cho artifact đó. Không nên tự đặt các artifact cùng release train ở những version khác nhau nếu không có lý do tương thích đã được xác minh.

Với Gradle, có thể import BOM bằng native platform:

```kotlin
val springModulithVersion = "1.4.0" // Version minh họa; chọn bản tương thích với Spring Boot.

dependencies {
    implementation(platform(
        "org.springframework.modulith:spring-modulith-bom:$springModulithVersion"
    ))

    implementation("org.springframework.modulith:spring-modulith-starter-core")
    testImplementation("org.springframework.modulith:spring-modulith-starter-test")
}
```

BOM chỉ quản lý những dependency có trong BOM. Các thư viện ngoài release train Spring Modulith và các build plugin vẫn cần được quản lý bằng dependency management, version catalog hoặc khai báo version rõ ràng.

## 3. Chọn phiên bản tương thích trước khi khóa

Không nên chọn version chỉ vì đó là bản mới nhất. Trước khi nâng cấp, hãy xác định:

1. Phiên bản Spring Boot và Spring Framework mà ứng dụng đang sử dụng.
2. Release train Spring Modulith hỗ trợ nền tảng Spring đó.
3. Phiên bản JDK tối thiểu và phiên bản JDK mà CI sẽ chạy.
4. Các starter và module tích hợp mà ứng dụng thực sự cần.
5. Những thay đổi API hoặc quy tắc kiến trúc có thể ảnh hưởng tới kết quả `verify()`.

Khi đã chọn được một release tương thích, ghi version thành một giá trị cụ thể trong property hoặc version catalog. Tránh các khai báo trôi nổi như `1.+`, `latest.release`, version range hoặc `SNAPSHOT` trong pipeline cần kết quả ổn định. Những khai báo này cho phép cùng một commit resolve ra dependency khác nhau ở các thời điểm khác nhau.

## 4. Khóa dependency đã phân giải trong Gradle

BOM đồng bộ các version được quản lý, nhưng một dependency có thể kéo theo nhiều thư viện bắc cầu. Gradle dependency locking ghi lại version thực tế đã được resolve cho từng configuration để những lần build sau sử dụng cùng bộ version.

Trong `build.gradle.kts`, bật locking cho tất cả configuration:

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

Sau khi cấu hình dependency, chạy các task cần thiết với `--write-locks`:

```bash
./gradlew test --write-locks
```

Gradle ghi trạng thái khóa, thường trong file `gradle.lockfile`. Chạy các task tương ứng với những configuration mà dự án cần, ví dụ test, integration test hoặc task tài liệu, để các dependency của những configuration đó được resolve và đưa vào lock state. Commit lockfile cùng thay đổi build script.

Khi CI chạy bình thường, không truyền `--write-locks`. CI dùng lock state đã được review trong repository. Nếu thay đổi dependency có chủ đích, cập nhật lockfile bằng `--write-locks`, kiểm tra diff và commit thay đổi cùng với lý do nâng cấp.

Locking giúp cố định version đã resolve. Nó không tự xác minh nội dung file JAR tải về có đúng với artifact đã được nhóm tin cậy hay không. Với dự án cần kiểm soát cả tính toàn vẹn artifact, hãy dùng thêm Gradle dependency verification.

## 5. Xác minh checksum dependency trong Gradle

Gradle dependency verification lưu checksum hoặc chữ ký được tin cậy trong `gradle/verification-metadata.xml`. Có thể tạo metadata ban đầu bằng:

```bash
./gradlew --write-verification-metadata sha256 build
```

Lệnh này resolve dependency của các task được chạy và ghi checksum SHA-256. Hãy review nguồn artifact và checksum trước khi chấp nhận metadata; không nên tự động tin mọi checksum chỉ vì lệnh đã tạo ra file. Commit `gradle/verification-metadata.xml` để CI xác minh artifact ở các lần build sau.

Hai cơ chế có mục đích khác nhau:

| Cơ chế | Bảo vệ điều gì? |
|---|---|
| Dependency locking (`gradle.lockfile`) | Version được resolve cho từng configuration. |
| Dependency verification (`verification-metadata.xml`) | Nội dung artifact tải về khớp checksum hoặc chữ ký đã được tin cậy. |

Với các dependency plugin, hãy khai báo version plugin rõ ràng trong `plugins {}` hoặc `pluginManagement` ở `settings.gradle(.kts)`. Không giả định dependency locking của ứng dụng tự động thay thế việc pin version của mọi plugin build.

## 6. Quản lý version trong Maven

Maven không có cơ chế dependency lockfile tích hợp tương đương Gradle dependency locking trong core. Cách quản lý phổ biến là import BOM, khai báo version rõ ràng cho plugin và dùng Maven Enforcer để phát hiện xung đột dependency hoặc môi trường không đáp ứng yêu cầu.

Ví dụ cấu hình Enforcer trong `pom.xml`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-enforcer-plugin</artifactId>
            <version>3.5.0</version>
            <executions>
                <execution>
                    <id>enforce-build-environment</id>
                    <goals>
                        <goal>enforce</goal>
                    </goals>
                    <configuration>
                        <rules>
                            <requireJavaVersion>
                                <version>[21,22)</version>
                            </requireJavaVersion>
                            <dependencyConvergence/>
                        </rules>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Version plugin `3.5.0` trong ví dụ cũng cần được quản lý như một version cố định. `dependencyConvergence` giúp phát hiện trường hợp cùng một artifact xuất hiện với nhiều version trong dependency graph. Quy tắc `requireJavaVersion` kiểm tra major version theo khoảng đã khai báo; để có kết quả tái lập chặt hơn, CI vẫn cần dùng cùng bản phân phối và patch JDK.

Với Maven Wrapper, commit các file wrapper và cố định Maven distribution trong `.mvn/wrapper/maven-wrapper.properties`. Có thể khai báo checksum của distribution nếu wrapper version đang dùng hỗ trợ:

```properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
distributionSha256Sum=<sha256-cua-goi-maven-da-xac-minh>
```

Giá trị checksum trong ví dụ là chỗ điền checksum thật lấy từ nguồn phân phối đáng tin cậy. Không sao chép chuỗi giả hoặc bỏ qua kiểm tra checksum trong pipeline cần độ tin cậy cao. Pin version của Maven plugin trong `build/plugins` hoặc `pluginManagement`; không dựa vào version mặc định có thể thay đổi theo môi trường hoặc parent POM.

Để xem dependency graph thực tế mà Maven đã resolve, có thể dùng `mvnw dependency:tree`. Lưu ý lệnh này giúp kiểm tra và review graph; nó không tạo lockfile hay tự khóa toàn bộ dependency bắc cầu.

## 7. Cố định build tool, plugin và JDK

Ngay cả khi dependency ứng dụng đã khóa, build vẫn có thể thay đổi nếu Gradle, Maven, compiler hoặc test plugin thay đổi. Vì vậy, hãy quản lý các phần sau:

**Gradle:** commit Gradle Wrapper và dùng distribution version cụ thể trong `gradle/wrapper/gradle-wrapper.properties`. Khai báo `distributionSha256Sum` để xác minh gói Gradle. Pin version của Spring Boot Gradle plugin, dependency management plugin và các plugin khác trong `plugins {}` hoặc `pluginManagement`.

**Maven:** commit Maven Wrapper, cố định `distributionUrl`, checksum distribution khi được hỗ trợ, và khai báo version cho các plugin build như compiler, surefire, enforcer và Spring Boot Maven plugin.

**JDK:** dùng Java toolchain để khai báo language version. Ví dụ Gradle:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Với Maven, khai báo `maven.compiler.release` để compiler tạo bytecode theo Java release mục tiêu:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Toolchain hoặc `maven.compiler.release` giúp thống nhất target Java, nhưng không tự pin bản phân phối JDK và patch runtime. CI nên chọn cùng image hoặc cùng bản cài JDK đã xác định, thay vì dùng tag môi trường trôi nổi.

## 8. Chạy kiểm tra module trong CI

Sau khi khóa dependency và build tool, chạy kiểm tra kiến trúc trên classpath mà ứng dụng thực sự dùng. Một test đơn giản có thể xác minh module model:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void applicationModuleModelShouldBeValid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Với Gradle, CI có thể chạy:

```bash
./gradlew clean test
```

Với Maven Wrapper:

```bash
./mvnw clean verify
```

Test kiến trúc cần nằm trong source set và task mà CI thực sự chạy. Nếu test chỉ nằm trong một task integration test riêng, pipeline phải gọi task đó; chỉ chạy `test` sẽ không bảo đảm test này đã được thực thi.

Một pipeline có thể áp dụng trình tự sau:

```mermaid
flowchart TD
    A[Checkout source và lockfile] --> B[Chọn JDK và build tool đã pin]
    B --> C[Resolve dependency theo BOM và lock state]
    C --> D[Xác minh checksum artifact]
    D --> E[Compile và chạy test]
    E --> F[ApplicationModules.verify()]
    F --> G[Sinh tài liệu nếu pipeline yêu cầu]
    G --> H[Review kết quả và lưu artifact]
```

Cache dependency trong CI có thể giảm thời gian tải và resolve, nhưng cache không thay thế lockfile, checksum hoặc wrapper. Build vẫn cần xác minh rằng dependency graph và artifact đáp ứng cấu hình đã commit.

## 9. Quy trình nâng cấp có kiểm soát

Khi cần nâng Spring Modulith hoặc Spring Boot, hãy xem đây là thay đổi có tác động tới model:

1. Chọn cặp version tương thích theo tài liệu release và compatibility matrix.
2. Cập nhật version BOM hoặc property trung tâm; không nâng từng artifact Modulith một cách rời rạc.
3. Cập nhật lockfile nếu dùng Gradle và review toàn bộ diff dependency bắc cầu.
4. Cập nhật checksum verification metadata khi artifact mới đã được xác minh.
5. Chạy test và `ApplicationModules.verify()` trên JDK, wrapper và CI image đã pin.
6. Sinh lại biểu đồ hoặc Module Canvas nếu dự án quản lý các tài liệu đó trong repository.
7. Review những thay đổi trong dependency graph, vi phạm kiến trúc và tài liệu được sinh trước khi hợp nhất.

Nếu model thay đổi sau khi nâng version, hãy xác định thay đổi đến từ source code, dependency graph, quy tắc phân tích mới hay cấu hình build. Không nên chấp nhận một kết quả khác chỉ vì pipeline vẫn chạy thành công; thay đổi kiến trúc cần được hiểu và review.

## 10. Những lỗi thường gặp khi khóa version

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Khai báo version riêng cho từng artifact Spring Modulith | Có thể trộn các artifact khác release train | Dùng `spring-modulith-bom`. |
| Dùng `1.+`, `LATEST`, version range hoặc `SNAPSHOT` | Cùng commit có thể resolve ra version khác | Pin một release cụ thể. |
| Chỉ khóa dependency trực tiếp | Dependency bắc cầu vẫn có thể thay đổi | Dùng Gradle dependency locking hoặc kiểm tra graph Maven bằng Enforcer và quy trình quản lý version. |
| Có lockfile nhưng không cập nhật khi thay dependency | CI thiếu hoặc dùng trạng thái khóa cũ | Cập nhật lock state có chủ đích và review diff. |
| Có lockfile nhưng không xác minh checksum | Artifact có thể khác nội dung đã được tin cậy | Dùng Gradle dependency verification hoặc cơ chế xác minh artifact tương đương. |
| Pin thư viện nhưng để build plugin trôi nổi | Build có thể khác dù dependency ứng dụng giống nhau | Pin plugin và build tool bằng wrapper. |
| Chỉ pin Java release | Máy local và CI có thể dùng patch JDK khác nhau | Cố định JDK distribution và patch trong CI. |
| Nâng Spring Modulith mà không review model | Quy tắc phát hiện module hoặc dependency có thể đổi mà không được nhận biết | Chạy test kiến trúc và review tài liệu được sinh. |

## 11. Tự đánh giá cấu hình CI

Một dự án dùng Gradle đã import Spring Modulith BOM, bật `lockAllConfigurations()` và commit `gradle.lockfile`. Tuy nhiên, CI vẫn dùng `gradle:latest`, JDK image tag `21` không cố định patch, và không có dependency verification metadata. Cấu hình này chưa đủ tái lập: version dependency đã được khóa nhưng build tool và môi trường JDK còn trôi nổi, checksum artifact chưa được xác minh.

Để hoàn thiện, nhóm cần dùng Gradle Wrapper với distribution version và checksum cụ thể, pin plugin, chọn JDK image cố định, tạo và review `gradle/verification-metadata.xml`, rồi chạy đầy đủ test kiến trúc. Khi nâng cấp, cập nhật BOM, lockfile và checksum cùng một thay đổi có thể review.

## Tài liệu tham khảo

- [Spring Modulith – Reference Documentation](https://docs.spring.io/spring-modulith/reference/)
- [Spring Modulith – Getting Started](https://docs.spring.io/spring-modulith/reference/getting-started.html)
- [Spring Boot – Dependency Versions](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Gradle – Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Gradle – Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Maven – Dependency Management](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Maven Enforcer Plugin](https://maven.apache.org/enforcer/maven-enforcer-plugin/)
