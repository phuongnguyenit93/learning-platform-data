# Build sạch với JDK và dependency đã cố định

Một build sạch phải tạo lại output từ source hiện tại, không phụ thuộc file biên dịch cũ còn sót trong thư mục build. Một build có thể tái lập còn cần cố định JDK, build tool, plugin, dependency bắc cầu và các yếu tố môi trường có ảnh hưởng đến artifact. Chỉ chạy `clean` chưa đủ để bảo đảm hai máy tạo ra cùng kết quả.

Với dự án Java 26, hãy cố định JDK toolchain ở release 26, đặt compiler `--release 26`, dùng Maven Wrapper hoặc Gradle Wrapper, khóa phiên bản dependency và xác minh nội dung artifact tải về. Trên JDK 27, có thể chạy thêm một lượt kiểm thử tương thích trong khi vẫn giữ `--release 26` cho bytecode và API đích. Các ví dụ dưới đây dùng API và cơ chế build ổn định; không bật preview cho build phát hành thông thường.

## 1. Build sạch, build ổn định và reproducible build

Ba khái niệm có liên quan nhưng khác nhau:

| Khái niệm | Ý nghĩa | Cách kiểm soát |
| --- | --- | --- |
| Clean build | Xóa output cũ rồi build lại từ source | `mvnw clean verify`, `gradlew clean build` |
| Stable build inputs | Các lần build dùng cùng JDK, build tool, plugin, dependency và cấu hình | Wrapper, toolchain, version pinning, dependency lock |
| Reproducible build | Cùng source và đầu vào tạo artifact giống hệt từng byte | Kiểm soát thêm timestamp, thứ tự archive, encoding, OS và môi trường |

Ví dụ, `gradlew clean build` xóa thư mục `build/` của project và chạy lại các task cần thiết. Lệnh này không xóa Gradle dependency cache, không tự cố định JDK, không khóa phiên bản thư viện và không bảo đảm archive có timestamp giống lần build trước.

Một quy trình đáng tin cậy phải kiểm soát cả ba lớp. Điều này đặc biệt quan trọng khi CI build artifact để ký, phát hành hoặc triển khai lên nhiều môi trường.

## 2. Phân biệt JDK chạy build với JDK biên dịch

Một quy trình Java có thể dùng nhiều JDK:

- **Build JVM:** JVM chạy Maven hoặc Gradle.
- **Compiler toolchain:** JDK cung cấp `javac` dùng biên dịch source.
- **Test launcher:** JDK chạy unit test và integration test.
- **Runtime đích:** JDK mà ứng dụng sẽ chạy sau khi phát hành.

Trong dự án đơn giản, cả bốn có thể cùng là JDK 26. Nhưng khi kiểm tra tương thích trên JDK 27, bạn có thể chạy build tool trên JDK 27, biên dịch bằng toolchain 26 và chạy thêm một lượt test trên JDK 27.

Kiểm tra môi trường trước khi build:

```bash
java -version
javac -version
```

Với Maven Wrapper:

```bash
./mvnw --version
```

Với Gradle Wrapper:

```bash
./gradlew --version
```

Trên Windows dùng `mvnw.cmd` và `gradlew.bat`. Các lệnh trên giúp thấy JVM đang chạy build tool. Nếu project cấu hình toolchain riêng, hãy kiểm tra log build để xác nhận compiler/test task thực sự chọn đúng JDK.

Để build có thể tái lập ở mức cao, ngoài major version 26 còn cần thống nhất vendor, patch release, OS và kiến trúc CPU. Gradle/Maven toolchain thường chọn theo thuộc tính JDK như major version và vendor; nếu cần cùng patch build, hãy cố định bản JDK cụ thể trong CI image/container hoặc cơ chế provisioning có version chính xác.

## 3. Dùng `--release` để cố định ngôn ngữ, API và bytecode

`javac --release 26` kiểm soát đồng thời:

1. Quy tắc ngôn ngữ Java được chấp nhận.
2. Bộ Java SE/JDK API mà source được phép tham chiếu.
3. Phiên bản class file được tạo để chạy trên Java 26.

Ví dụ biên dịch trực tiếp:

```bash
javac --release 26 -encoding UTF-8 -d out src/com/example/App.java
```

`--release` là lựa chọn phù hợp khi muốn build trên JDK mới hơn nhưng giữ compatibility với release đích. Chỉ đặt `-source 26 -target 26` không giới hạn API theo đúng Java 26; có thể vô tình gọi API chỉ có ở JDK dùng để biên dịch. Trên JDK 9+, ưu tiên `--release` thay cho việc ghép `-source`/`-target` với boot class path thủ công.

Nếu build source Java 26 bằng JDK 27, vẫn đặt `--release 26` để compiler không cho dùng API chỉ xuất hiện ở Java 27. Khi chạy kiểm thử trên JDK 27, đây là một lượt kiểm tra tương thích runtime bổ sung; artifact vẫn có target Java 26.

Preview features là ngoại lệ có chủ đích: phải bật preview ở compile và runtime trên cùng JDK release. Ví dụ code preview được compile bằng JDK 26 cần chạy bằng JDK 26 với `--enable-preview`; không dùng JDK 27 để chạy class file preview của JDK 26. Build phát hành ổn định nên không bật preview trừ khi dự án chấp nhận rõ ràng phụ thuộc đó.

## 4. Gradle: cố định Wrapper và Java toolchain

Gradle Wrapper đảm bảo mọi developer và CI dùng cùng phiên bản Gradle được khai báo trong repository. Thay vì gọi `gradle build` từ bản Gradle cài toàn máy, hãy gọi `./gradlew` hoặc `gradlew.bat`.

Ví dụ `gradle/wrapper/gradle-wrapper.properties`:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.2-bin.zip
distributionSha256Sum=<sha256-lay-tu-trang-checksum-chinh-thuc>
```

Thay giá trị placeholder bằng checksum SHA-256 lấy từ trang checksum chính thức của đúng bản phân phối. Commit cả Wrapper scripts, Wrapper JAR và file properties theo chính sách repository. Không dùng URL `latest` hoặc version động cho Wrapper.

Về khả năng tương thích, Gradle 9.4.0 trở lên hỗ trợ Java 26 cho việc chạy Gradle và toolchains; Gradle 9.8.0 trở lên hỗ trợ Java 27. Ví dụ dùng Gradle 9.9.2 ở trên đáp ứng cả hai mức. Luôn kiểm tra compatibility matrix của đúng phiên bản Gradle trước khi nâng JDK.

### Cấu hình toolchain và release trong build.gradle.kts

```kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test

plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(26)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(26)
    options.encoding = "UTF-8"
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}

dependencyLocking {
    lockAllConfigurations()
}

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

`toolchain` chọn JDK 26 cho các task hỗ trợ toolchain. `options.release` giới hạn API/source/bytecode đích ở Java 26. Hai cấu hình này bổ sung cho nhau: toolchain quyết định JDK compiler, còn `release` quyết định nền tảng đích.

Nếu CI dùng JDK 27 để kiểm tra runtime tương thích, có thể thay toolchain test ở một job riêng sang JDK 27 nhưng giữ `options.release.set(26)` cho compilation. Đừng thay đổi toolchain một cách ngầm định theo `JAVA_HOME` của từng máy.

### Khóa dependency và xác minh nội dung dependency

Gradle có hai cơ chế riêng:

- **Dependency locking:** khóa phiên bản module đã resolve, bao gồm dependency bắc cầu.
- **Dependency verification:** xác minh checksum hoặc chữ ký của artifact được tải về.

Tạo/cập nhật lock state sau khi review dependency:

```bash
./gradlew build --write-locks
```

Tạo verification metadata SHA-256:

```bash
./gradlew --write-verification-metadata sha256 build
```

Lệnh thứ hai tạo hoặc cập nhật `gradle/verification-metadata.xml` cho các artifact được resolve trong lần chạy đó. Review checksum từ nguồn tin cậy rồi commit metadata. Không xem việc tự sinh checksum từ một dependency chưa được kiểm tra là bằng chứng dependency an toàn; bootstrap cần được thực hiện trong môi trường tin cậy và kiểm tra nguồn phát hành.

Khóa phiên bản không thay thế xác minh artifact: cùng một tọa độ/version vẫn cần được kiểm tra nội dung tải về. Ngược lại, checksum đúng không ngăn một version mới được resolve nếu build khai báo dependency động. Cần cả hai.

## 5. Gradle: chạy clean build và kiểm tra dependency

Build sạch có unit test và các task kiểm tra:

```bash
./gradlew clean build
```

`build` phụ thuộc `check` và `assemble`; `check` chạy các test và verification task được cấu hình trong project. Với project chỉ muốn chạy verification/test:

```bash
./gradlew clean check
```

Xem cây dependency:

```bash
./gradlew dependencies
```

Tìm vì sao một dependency được chọn:

```bash
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

`--offline` buộc Gradle chỉ dùng artifact đã có trong cache; hữu ích cho kiểm tra môi trường không mạng nhưng không thay thế lock/verification. `--refresh-dependencies` yêu cầu Gradle kiểm tra lại trạng thái dependency từ repository; không nên thêm mặc định vào CI vì làm build phụ thuộc trạng thái repository và mạng.

Khi điều tra output cũ hoặc cache gây nhiễu, có thể chạy `./gradlew clean build --no-build-cache`. Đây là bước chẩn đoán; build cache được cấu hình đúng vẫn có thể dùng an toàn để tăng tốc và không thay thế việc cố định đầu vào.

## 6. Maven: cố định Wrapper, compiler và test plugins

Maven Wrapper (`mvnw`, `mvnw.cmd`) tải và sử dụng Maven release được khai báo trong `.mvn/wrapper/maven-wrapper.properties`. Commit Wrapper files để developer và CI không phụ thuộc Maven cài sẵn trên máy. Tại thời điểm cập nhật bài này, Maven 3.10.2 là stable release được Apache khuyến nghị; Maven 4.0.0-rc-7 vẫn là release candidate, chưa phải lựa chọn production mặc định.

Ví dụ cấu hình:

```properties
distributionUrl=https\://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.10.2/apache-maven-3.10.2-bin.zip
distributionSha256Sum=<sha256-cua-maven-distribution>
wrapperSha256Sum=<sha256-cua-maven-wrapper-jar-neu-dung-wrapper-jar>
```

Các checksum phải lấy từ nguồn phát hành chính thức, không tự điền giá trị đoán. `distributionSha256Sum` xác minh Maven distribution; `wrapperSha256Sum` xác minh Wrapper JAR nếu loại Wrapper của project sử dụng file đó. Với loại `only-script`, cấu trúc Wrapper khác và không có Wrapper JAR để kiểm tra.

### Khai báo release và plugin versions trong pom.xml

Ví dụ phần cấu hình liên quan đến compile, test và reproducible archive:

```xml
<properties>
    <maven.compiler.release>26</maven.compiler.release>
    <project.build.outputTimestamp>2026-11-27T00:00:00Z</project.build.outputTimestamp>
</properties>

<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
                <configuration>
                    <release>${maven.compiler.release}</release>
                    <encoding>UTF-8</encoding>
                    <proc>full</proc>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.6.3</version>
            </plugin>
        </plugins>
    </pluginManagement>

    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-failsafe-plugin</artifactId>
            <executions>
                <execution>
                    <goals>
                        <goal>integration-test</goal>
                        <goal>verify</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-enforcer-plugin</artifactId>
            <executions>
                <execution>
                    <id>enforce-dependency-convergence</id>
                    <goals>
                        <goal>enforce</goal>
                    </goals>
                    <configuration>
                        <rules>
                            <dependencyConvergence/>
                        </rules>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Các plugin trong `pluginManagement` có version/configuration được quản lý tập trung. Failsafe được khai báo trong `plugins` để gắn hai goal integration test vào lifecycle; Enforcer được kích hoạt để kiểm tra dependency convergence. Surefire chạy unit test ở phase `test`; Failsafe chạy integration test ở `integration-test` và kiểm tra kết quả ở `verify`.

Ví dụ đặt `<proc>full</proc>` khi project có annotation processor được khai báo. Nếu project không dùng annotation processing, chọn `<proc>none</proc>`. Với JDK mới, hãy cấu hình rõ chế độ xử lý annotation và khai báo processor dependency thay vì dựa vào việc tự dò processor trên classpath. Annotation processor là code được thực thi trong build, vì vậy cũng cần pin và xác minh dependency của chúng.

`project.build.outputTimestamp` giúp các plugin hỗ trợ reproducible archive dùng timestamp cố định. Giá trị ví dụ là mốc UTC cố định; release pipeline có thể cập nhật nó theo timestamp của commit hoặc quy tắc release đã thống nhất.

## 7. Maven: chọn JDK toolchain riêng

Maven có thể chạy bằng một JDK nhưng compiler/test plugin sử dụng JDK khác thông qua Maven Toolchains. Đây là cách tách JVM chạy Maven khỏi JDK thực hiện compile/test.

Trong `~/.m2/toolchains.xml` của máy build:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>[26,27)</version>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/jdk-26</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

Đường dẫn `/opt/jdks/jdk-26` là ví dụ; thay bằng thư mục JDK 26 đã được provision trên máy. Range `[26,27)` chọn JDK có major version 26 và cho phép patch update trong cùng major. Nếu cần khóa đúng patch/vendor, hãy dùng tiêu chí tương ứng trong toolchains và cố định distribution trong CI image.

Khai báo Maven Toolchains Plugin trong `pom.xml` để chọn toolchain:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.2.0</version>
    <executions>
        <execution>
            <goals>
                <goal>toolchain</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <toolchains>
            <jdk>
                <version>[26,27)</version>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
```

Compiler, Surefire và Failsafe là các plugin hỗ trợ toolchains. Kiểm tra log Maven để xác nhận toolchain được chọn. `mvnw --version` chỉ cho biết JVM chạy Maven; nó không chứng minh compiler plugin đã dùng cùng JDK.

Nếu không cấu hình toolchain, compiler mặc định dùng `javac` của JDK chạy Maven. Trong trường hợp đó, hãy cố định `JAVA_HOME`/JDK của build agent và kiểm tra `mvnw --version`.

## 8. Maven: chạy clean verify và kiểm tra dependency

Build sạch gồm compile, unit test, đóng gói và các verification goal đã cấu hình:

```bash
./mvnw --batch-mode --no-transfer-progress clean verify
```

Trên Windows:

```powershell
./mvnw.cmd --batch-mode --no-transfer-progress clean verify
```

`verify` đi qua các phase trước đó của Maven lifecycle và chạy Failsafe `verify` nếu plugin đã được cấu hình. Dùng `install` khi cần cài artifact vào local repository cho project khác; dùng `deploy` khi chủ động phát hành lên remote repository. CI kiểm tra thông thường nên dừng ở `verify`.

Kiểm tra cây dependency:

```bash
./mvnw dependency:tree
```

Kiểm tra POM sau khi áp dụng parent, profile và plugin management:

```bash
./mvnw help:effective-pom
```

Chạy offline khi repository cache đã có đủ artifact:

```bash
./mvnw --offline --batch-mode clean verify
```

Offline mode giúp phát hiện build còn phụ thuộc tải dependency mới; nó không chứng minh artifact đã được xác minh hoặc dependency đã được pin. Không dùng `-U` trong clean build thông thường vì tùy chọn này buộc Maven kiểm tra lại snapshot/release metadata từ repository.

## 9. Khóa dependency và plugin versions

Dependency là một phần của build input. Chỉ pin dependency trực tiếp nhưng để dependency bắc cầu thay đổi vẫn có thể tạo ra kết quả khác nhau.

| Build tool | Cách kiểm soát |
| --- | --- |
| Gradle | Version catalog hoặc version khai báo tường minh, dependency locking, dependency verification |
| Maven | Version tường minh, `dependencyManagement`/BOM đã pin, Enforcer rules và repository policy |
| Cả hai | Pin plugin/build extension, tránh version range, `latest.release`, `1.+` và `SNAPSHOT` cho release build |

Với Maven, dùng BOM có version cố định để quản lý một nhóm dependency liên quan. Kiểm tra `dependency:tree` để tìm dependency bắc cầu bị override hoặc nhiều version cùng tồn tại. Enforcer `dependencyConvergence` có thể làm build fail khi phát hiện dependency graph không hội tụ theo rule của dự án.

Với Gradle, dependency locking giữ version đã resolve; dependency verification giữ checksum/signature đã chấp nhận. Khi nâng dependency, cập nhật lock và verification metadata trong một thay đổi được review, rồi chạy đầy đủ test.

Không dùng một version range hoặc `SNAPSHOT` trong artifact phát hành nếu mục tiêu là tái lập. Với dependency nội bộ, repository cần chính sách immutable version: không ghi đè artifact đã phát hành dưới cùng tọa độ/version.

## 10. Reproducible archive và môi trường build

Ngay cả khi source và dependency giống nhau, archive có thể khác byte do timestamp, thứ tự entry, encoding hoặc môi trường build.

Với Gradle, ví dụ cấu hình `AbstractArchiveTask` trong phần trên đặt:

- `isPreserveFileTimestamps = false`: không giữ timestamp file nguồn trong archive.
- `isReproducibleFileOrder = true`: ghi entry theo thứ tự ổn định.

Với Maven, `project.build.outputTimestamp` cung cấp timestamp cố định cho plugin hỗ trợ reproducible output. Cần dùng phiên bản plugin có hỗ trợ tính năng này; Maven reproducibility là tính năng ở cấp plugin, không phải mọi plugin đều tự động tạo output giống nhau.

Các yếu tố môi trường nên được cố định hoặc ghi nhận:

- JDK vendor, version/patch, OS và CPU architecture.
- Maven/Gradle Wrapper version và checksum distribution.
- Plugin, build extension, annotation processor và dependency bắc cầu.
- Locale, timezone, encoding, line ending và biến môi trường có ảnh hưởng output.
- Timestamp release, source commit và trạng thái working tree.
- Repository/mirror được dùng để resolve artifact.

Maven có thể kiểm tra tính tái lập cơ bản bằng cách build/install rồi build lại và so sánh artifact:

```bash
./mvnw clean install
./mvnw clean verify artifact:compare
```

So sánh trên cùng máy chỉ phát hiện một số nguyên nhân không tái lập. Để kiểm chứng mạnh hơn, rebuild cùng commit trong một môi trường độc lập và so sánh artifact bằng checksum hoặc công cụ như `diffoscope`.

## 11. Kiểm tra tương thích Java 26 và Java 27

Nếu artifact phát hành cho Java 26, compile với `--release 26` trên JDK 26. Có thể thêm CI matrix chạy test trên JDK 26 và JDK 27:

| Job | Build JDK/toolchain | Compiler release | Runtime test | Mục tiêu |
| --- | --- | --- | --- | --- |
| Release baseline | JDK 26 | 26 | JDK 26 | Xác nhận target runtime chính |
| Forward compatibility | JDK 27 | 26 | JDK 27 | Phát hiện thay đổi runtime hoặc warning mới |

Nếu test trên JDK 27, không nâng `--release` lên 27 trừ khi sản phẩm chủ đích đổi baseline. Giữ release target ở 26 giúp phát hiện việc vô tình sử dụng API chỉ có trên JDK 27.

Với Gradle, có thể dùng hai CI job và đổi toolchain/test launcher theo từng job, trong khi giữ `options.release.set(26)`. Với Maven, cấu hình Maven Toolchains cho từng agent hoặc cung cấp hai toolchain rồi chọn qua profile/CI property. Đừng để toolchain được chọn tùy ý từ JDK cài sẵn trên developer machine.

Nếu project dùng preview feature của Java 26, hãy tạo job riêng có `--enable-preview` cho compiler và test JVM, và chạy bằng JDK 26. Không trộn class file preview vào artifact stable hoặc chạy nó trên JDK 27.

## 12. Quy trình CI đề xuất

Một pipeline build Java 26 có thể gồm:

```text
Checkout source commit
        |
        v
Verify Wrapper + JDK/toolchain version
        |
        v
Resolve locked dependencies
        |
        v
Clean compile with --release 26
        |
        v
Unit tests
        |
        v
Integration tests
        |
        v
Package + reproducibility checks
        |
        v
Archive artifact + checksums + build metadata
```

Lệnh build tương ứng:

```bash
# Gradle
./gradlew clean build

# Maven
./mvnw --batch-mode --no-transfer-progress clean verify
```

Sau khi build, lưu lại source commit, JDK vendor/version, build tool version, dependency lock/verification state, test reports và checksum artifact. Nếu release pipeline có bước ký JAR, hãy ký đúng artifact đã build và xác minh; không build lại hoặc chỉnh sửa archive sau khi ký.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Build thành công trên máy A nhưng fail trên máy B | JDK/build tool khác nhau hoặc dependency chưa khóa | Dùng Wrapper, toolchain, lock state và kiểm tra version đầu vào |
| `invalid source release: 26` | JDK compiler được chọn quá cũ | Kiểm tra toolchain/compiler JDK và nâng lên JDK 26 |
| Compile trên JDK 27 nhưng chạy Java 26 bị `NoSuchMethodError` | Code tham chiếu API chỉ có trên JDK 27 | Dùng `--release 26` khi compile target Java 26 |
| Gradle báo không hỗ trợ JVM 26/27 | Wrapper Gradle quá cũ | Dùng Gradle 9.4.0+ cho JDK 26 hoặc 9.8.0+ cho JDK 27 |
| Maven chạy JDK 27 dù toolchain là JDK 26 | Nhầm JVM chạy Maven với compiler toolchain | Xem `mvnw --version`, cấu hình Toolchains và đọc log compiler |
| Build tải version khác ở lần sau | Dynamic version, range, SNAPSHOT hoặc dependency bắc cầu chưa khóa | Pin version, cập nhật lock state và BOM/dependencyManagement |
| Gradle dependency verification fail | Checksum/signature không khớp hoặc metadata cũ | Xác minh artifact từ nguồn tin cậy trước khi cập nhật verification metadata |
| Build sạch vẫn tạo JAR khác checksum | Timestamp, entry order, JDK patch hoặc môi trường khác | Bật reproducible archive, cố định môi trường và so sánh bằng diffoscope |
| Unit test chạy nhưng integration test không chạy | Failsafe chưa được khai báo execution hoặc gọi sai phase | Bind `integration-test` và `verify`; chạy `mvn verify` |
| Annotation processor không chạy hoặc tự chạy ngoài ý muốn | Chế độ `proc`/processor path không rõ ràng | Chọn `full` hoặc `none`, khai báo processor dependency tường minh |
| Offline build thất bại | Cache chưa có đủ plugin/dependency | Chạy build online trong môi trường tin cậy, sau đó kiểm tra offline |

## 14. Checklist trước khi chấp nhận một clean build

- [ ] Dùng Maven Wrapper hoặc Gradle Wrapper với version cố định.
- [ ] Xác minh checksum của Wrapper distribution và Wrapper JAR nếu có.
- [ ] Cố định JDK toolchain; ghi nhận vendor, patch, OS và architecture.
- [ ] Đặt `--release 26` cho artifact target Java 26.
- [ ] Pin plugin, build extension, annotation processor và dependency trực tiếp/bắc cầu.
- [ ] Bật Gradle dependency locking/verification hoặc Maven dependency management/Enforcer phù hợp.
- [ ] Dùng repository bất biến; không phát hành dependency dưới version đã tồn tại.
- [ ] Chạy `clean build` hoặc `clean verify` để xóa output cũ và chạy toàn bộ verification.
- [ ] Unit test và integration test đều được cấu hình vào lifecycle.
- [ ] Dùng timestamp và archive ordering ổn định nếu cần artifact bit-for-bit reproducible.
- [ ] Lưu source commit, build metadata, test report và checksum artifact.
- [ ] Kiểm thử thêm trên JDK 27 nếu cần forward compatibility nhưng giữ `--release 26`.

## Ghi nhớ

- `clean` xóa output cũ; nó không tự cố định JDK, plugin, dependency hay môi trường.
- `--release 26` khóa ngôn ngữ, API và bytecode đích Java 26; chỉ dùng `-source`/`-target` là chưa đủ để khóa API.
- Toolchain chọn JDK compile/test; JVM chạy Maven/Gradle là một cấu hình riêng.
- Gradle 9.4.0+ hỗ trợ chạy/toolchain JDK 26; 9.8.0+ hỗ trợ JDK 27.
- Dùng Wrapper và xác minh checksum distribution; không dùng build tool cài toàn máy làm nguồn version duy nhất.
- Dependency lock khóa version; dependency verification kiểm tra nội dung artifact. Hai cơ chế bổ sung cho nhau.
- Maven dùng `maven.compiler.release`, toolchains, plugin versions tường minh và `clean verify`.
- Unit test chạy ở Surefire; integration test chạy ở Failsafe và được xác nhận trong phase `verify`.
- Reproducible build cần kiểm soát timestamp, archive order, JDK patch, OS, encoding và các plugin tạo artifact.
- Nếu test trên JDK 27 nhưng phát hành Java 26, giữ `--release 26`.
- Preview feature cần cặp compile/runtime cùng JDK release và nên tách khỏi build phát hành ổn định.

## Tài liệu tham khảo

- [The `javac` Command, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html) — `--release`, classpath/module path, annotation processing và compile target.
- [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html) — JDK hỗ trợ chạy Gradle và toolchains theo từng release.
- [Gradle Toolchains](https://docs.gradle.org/current/userguide/toolchains.html) — chọn JDK compile/test độc lập với JVM chạy Gradle.
- [Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html) — pin Gradle distribution và xác minh SHA-256.
- [Gradle Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html) — khóa version dependency bắc cầu.
- [Gradle Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html) — xác minh checksum/signature của dependency.
- [Maven Compiler Plugin — compile](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html) — cấu hình `release`, encoding, annotation processing và output timestamp.
- [Maven Toolchains Guide](https://maven.apache.org/guides/mini/guide-using-toolchains.html) — tách JDK chạy Maven và JDK dùng bởi compiler/test plugins.
- [Maven Wrapper](https://maven.apache.org/tools/wrapper/) — pin Maven distribution và xác minh checksum Wrapper/distribution.
- [Maven Wrapper Plugin](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/wrapper-mojo.html) — `distributionSha256Sum` và `wrapperSha256Sum`.
- [Apache Maven Downloads and Release History](https://maven.apache.org/download.cgi) — phân biệt stable Maven 3.10.2 với Maven 4 release candidate tại thời điểm cập nhật.
- [Maven Surefire/Failsafe](https://maven.apache.org/surefire/) — unit test, integration test và lifecycle phase.
- [Configuring for Reproducible Builds — Maven](https://maven.apache.org/guides/mini/guide-reproducible-builds.html) — `project.build.outputTimestamp`, compare và chẩn đoán artifact khác nhau.
