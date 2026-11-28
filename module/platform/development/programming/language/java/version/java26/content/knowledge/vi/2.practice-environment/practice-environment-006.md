# Cố định phiên bản dependency, plugin và annotation processor

Một build Java có thể cho kết quả khác nhau giữa máy lập trình viên và CI dù mã nguồn không đổi. Nguyên nhân thường nằm ở các thành phần bên ngoài mã nguồn: thư viện trực tiếp, dependency bắc cầu, plugin của build tool, annotation processor, phiên bản JDK hoặc chính Gradle/Maven. Nếu build tự chọn phiên bản mới nhất theo thời điểm chạy, một lần build hôm nay có thể dùng tập thành phần khác lần build ngày mai.

Với dự án Java 26, cần kiểm soát rõ các đầu vào này. Mục tiêu là để nhóm biết chính xác build đang dùng thành phần nào, có thể tái tạo kết quả, cập nhật có chủ đích và kiểm tra được nguồn gốc artifact. Bài viết tập trung vào các cách làm hiện hành với Gradle và Maven; các cấu hình dùng JDK 26 phải được đối chiếu với ma trận tương thích của từng build tool và plugin.

## 1. Phân biệt những thứ cần cố định

| Thành phần | Ví dụ | Cách kiểm soát |
|---|---|---|
| JDK dùng để build | JDK 26 của một vendor và bản cập nhật cụ thể | Java toolchain, Maven toolchains hoặc image CI có digest cố định |
| Build tool | Gradle hoặc Maven | Gradle Wrapper hoặc Maven Wrapper, URL và checksum của distribution |
| Dependency ứng dụng | Thư viện HTTP, JSON, logging, test | Version catalog/BOM, dependency constraints và dependency locking hoặc dependency management |
| Dependency bắc cầu | Thư viện mà dependency trực tiếp kéo vào | Lock toàn bộ graph, BOM, kiểm tra xung đột và xem dependency tree |
| Plugin build | Plugin Java, kiểm tra mã, đóng gói, framework | Khai báo ID và phiên bản rõ ràng; kiểm soát repository và artifact |
| Annotation processor | Bộ sinh mã từ annotation | Khai báo riêng trên processor path/configuration, ghim phiên bản và chỉ cho phép processor cần thiết |
| Nội dung artifact | JAR, ZIP, metadata POM hoặc plugin đã tải | Kiểm tra SHA-256 và chữ ký khi có; chỉ tin nguồn phát hành đã xác minh |

Các cơ chế trên bổ sung cho nhau. **Khai báo phiên bản** giúp biết phiên bản mong muốn; **dependency locking** ghi lại phiên bản thực tế được phân giải; **dependency verification** kiểm tra nội dung artifact tải về. Chúng giải quyết ba câu hỏi khác nhau và nên được phối hợp.

## 2. Quy tắc chung khi quản lý phiên bản

### Ghim phiên bản cụ thể

Trong build phát hành, tránh các khai báo có thể tự đổi kết quả theo thời gian:

- Gradle: `1.+`, `latest.release`, version range hoặc dependency được đánh dấu changing.
- Maven: version range, `LATEST`, `RELEASE` và dependency `SNAPSHOT` dùng làm đầu vào phát hành.
- Plugin: không bỏ trống phiên bản của plugin bên thứ ba và không dùng phiên bản động.

Ví dụ, `com.example:client:4.2.1` thể hiện rõ phiên bản cần dùng hơn `com.example:client:4.+`. Một tọa độ `SNAPSHOT` cũng không bảo đảm nội dung bất biến: repository có thể thay JAR tại cùng tọa độ. Với bản build cần tái tạo, hãy dùng bản release đã phát hành và repository có chính sách lưu trữ bất biến.

Không nhất thiết mọi thư viện phải có số phiên bản lặp lại ở từng module. Hãy tập trung phiên bản tại một nơi bằng BOM hoặc version catalog, sau đó dùng lock để cố định kết quả phân giải bao gồm cả dependency bắc cầu.

### Khai báo dependency mà mã nguồn trực tiếp sử dụng

Nếu mã nguồn import một thư viện, hãy khai báo thư viện đó trực tiếp. Không dựa vào việc một dependency khác tình cờ kéo nó vào. Khi dependency trung gian đổi hoặc bỏ dependency bắc cầu, build của bạn sẽ không âm thầm mất một thư viện mà mã nguồn đang sử dụng.

### Cố định môi trường JDK và build tool

Gradle Wrapper và Maven Wrapper giúp cả nhóm sử dụng cùng phiên bản build tool. Chúng không tự bảo đảm mọi máy dùng cùng JDK patch, vendor, hệ điều hành hay biến môi trường. Hãy ghim JDK trong CI bằng image có digest hoặc quy trình cấp phát JDK cụ thể; đồng thời cấu hình toolchain và mức phát hành Java trong build.

Với Gradle, ma trận tương thích hiện hành ghi nhận Gradle 9.4.0 là phiên bản tối thiểu có hỗ trợ chạy Gradle trên JDK 26 và dùng JDK 26 làm toolchain. Chọn một bản Gradle ổn định mới hơn nếu phù hợp với plugin đang dùng, rồi ghim đúng bản đó trong Wrapper. Không suy ra rằng mọi phiên bản plugin cũ đều tương thích chỉ vì Gradle đã hỗ trợ JDK 26.

## 3. Thực hành với Gradle

### 3.1. Khai báo dependency và plugin tập trung

Gradle Version Catalog đặt tại `gradle/libs.versions.toml` giúp quản lý phiên bản thư viện và plugin ở một nơi. Ví dụ Kotlin DSL:

```toml
# gradle/libs.versions.toml
[versions]
json = "2.4.0" # Ví dụ: thay bằng bản release đã được dự án duyệt
processor = "1.8.0"
quality-plugin = "2.1.0"

[libraries]
json = { module = "com.example:json-client", version.ref = "json" }
my-annotations = { module = "com.example:my-annotations", version.ref = "processor" }
my-processor = { module = "com.example:my-processor", version.ref = "processor" }

[plugins]
quality = { id = "com.example.quality", version.ref = "quality-plugin" }
```

Các số phiên bản trong ví dụ chỉ minh họa cách tổ chức TOML; hãy thay bằng phiên bản release thực tế đã kiểm tra tương thích và được dự án chấp thuận. Trong `build.gradle.kts`:

```kotlin
plugins {
    java
    alias(libs.plugins.quality)
}

dependencies {
    implementation(libs.json)

    // Processor chỉ nằm trên classpath xử lý annotation.
    annotationProcessor(libs.my.processor)
    testAnnotationProcessor(libs.my.processor)
}
```

Nếu nhiều module dùng chung plugin, có thể khai báo phiên bản plugin một lần trong `pluginManagement { plugins { ... } }` của `settings.gradle.kts`, hoặc khai báo plugin ở build gốc với `apply false` rồi áp dụng theo nhu cầu ở từng module. Dùng `plugins {}` và `pluginManagement {}` để quản lý plugin theo cơ chế hiện hành. `buildscript { dependencies { classpath(...) } }` và `apply(plugin = ...)` là cách áp dụng plugin kiểu cũ; chỉ giữ chúng khi một tích hợp cụ thể thật sự yêu cầu.

Version Catalog giúp tập trung phiên bản được khai báo, nhưng tự nó không ép phiên bản được chọn cuối cùng trong quá trình giải quyết xung đột. Vì vậy, đừng xem `libs.versions.toml` là lockfile. Cần kết hợp với platform/BOM, dependency constraints và dependency locking.

### 3.2. Cố định JDK biên dịch

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(26))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(26)
}
```

Java toolchain chọn JDK dùng cho các tác vụ Java hỗ trợ toolchain. `options.release` giới hạn ngôn ngữ, bytecode và API Java theo release 26. Hai cấu hình này có mục đích khác nhau: toolchain chọn compiler/JDK; `release` xác định nền tảng Java mà mã nguồn được phép sử dụng. Toolchain theo language version không nhất thiết ghim chính xác vendor và số bản vá JDK, vì vậy CI vẫn cần cung cấp một JDK 26 đã được xác định rõ.

### 3.3. Bật dependency locking

Thêm vào `build.gradle.kts` của từng project cần khóa:

```kotlin
dependencyLocking {
    lockAllConfigurations()
}

configurations.configureEach {
    resolutionStrategy {
        failOnDynamicVersions()
        failOnChangingVersions()
    }
}
```

`lockAllConfigurations()` bật locking cho các configuration có thể được phân giải, bao gồm những configuration như `runtimeClasspath`, `testRuntimeClasspath` và `annotationProcessor`. Sau khi cấu hình, chạy các task thực sự phân giải những configuration cần khóa, ví dụ:

```bash
./gradlew build --write-locks
```

Gradle ghi trạng thái dependency đã phân giải vào `gradle.lockfile` ở từng project. Đưa lockfile vào source control. Với multi-project build, bảo đảm task đã chạy qua các module và variant cần thiết; một lệnh `dependencies` ở root có thể chỉ phân giải project root, không tự động bao phủ mọi subproject.

Dependency locking ở đây quản lý các configuration dependency của project; không giả định nó tự ghim phiên bản plugin được yêu cầu trong `plugins {}`. Hãy khai báo phiên bản plugin rõ ràng bằng Version Catalog hoặc `pluginManagement`, đồng thời dùng dependency verification để kiểm tra artifact plugin và các artifact liên quan.

Khi nâng phiên bản trực tiếp hoặc cập nhật BOM, cập nhật lock có chủ đích bằng `--write-locks`, xem diff của các lockfile và chạy lại kiểm tra. Không sửa lockfile bằng tay. Nếu build báo phiên bản khai báo không khớp lock state, hãy xác định dependency nào cần nâng rồi tạo lại lock state có kiểm soát.

### 3.4. Xác minh nội dung artifact

Dependency locking xác nhận phiên bản, nhưng cùng một tọa độ có thể được repository phục vụ bằng nội dung khác nhau. Gradle Dependency Verification bổ sung kiểm tra checksum hoặc chữ ký của artifact và metadata. Tạo metadata ban đầu bằng lệnh:

```bash
./gradlew --write-verification-metadata sha256 build
```

Gradle tạo `gradle/verification-metadata.xml`. Trước khi commit file này, kiểm tra từng dependency mới và đối chiếu checksum/chữ ký với nguồn phát hành đáng tin cậy. Nếu nhà phát hành cung cấp chữ ký PGP và quy trình xác minh khóa đáng tin cậy, có thể tạo metadata với `sha256,pgp`. Không tự động tin một checksum chỉ vì nó được tạo từ chính lần tải xuống đang cần xác minh; việc bootstrap metadata cần một nguồn tin cậy độc lập.

Sau khi file metadata được đưa vào repository, Gradle tự xác minh các dependency trong những lần build sau. Cơ chế này áp dụng cả với artifact của plugin. Khi nâng phiên bản, cập nhật metadata cùng thay đổi dependency và review diff như một phần của quy trình cập nhật.

### 3.5. Kiểm tra dependency graph

```bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency json-client --configuration runtimeClasspath
./gradlew build
```

Lệnh `dependencies` hiển thị cây dependency; `dependencyInsight` giải thích vì sao một phiên bản được chọn và thành phần nào đưa nó vào graph. Kiểm tra thêm configuration của annotation processor khi cần. Việc này giúp phát hiện phiên bản bắc cầu bị nâng do conflict resolution, thư viện trùng vai trò hoặc dependency không còn cần thiết.

## 4. Thực hành với Maven

### 4.1. Quản lý dependency bằng dependencyManagement và BOM

Trong Maven, `dependencyManagement` tập trung phiên bản dependency cho các module con và dependency bắc cầu. BOM là POM chuyên mô tả tập phiên bản tương thích; import BOM bằng scope `import` trong `dependencyManagement`:

```xml
<properties>
    <maven.compiler.release>26</maven.compiler.release>
    <maven-compiler-plugin.version>3.16.0</maven-compiler-plugin.version>
    <platform-bom.version>THAY_BANG_BAN_RELEASE_DA_DUYET</platform-bom.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>platform-bom</artifactId>
            <version>${platform-bom.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>json-client</artifactId>
        <!-- Phiên bản lấy từ BOM đã import. -->
    </dependency>
</dependencies>
```

Thay giá trị minh họa bằng tọa độ và phiên bản BOM thật. Nếu không có BOM phù hợp, khai báo từng dependency cần quản lý trong `dependencyManagement`. BOM giúp đồng bộ các thư viện cùng hệ sinh thái; vẫn cần kiểm tra các dependency nằm ngoài BOM.

Maven `dependencyManagement` quản lý dependency của project, không quản lý dependency bắc cầu của plugin Maven. Phiên bản plugin và phiên bản dependency của plugin là một phạm vi riêng.

### 4.2. Ghim phiên bản plugin

Khai báo phiên bản plugin trong `build/pluginManagement` của POM cha hoặc POM gốc. Module nào cần plugin thì khai báo plugin đó trong `build/plugins`; phiên bản đã quản lý sẽ được áp dụng:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>${maven-compiler-plugin.version}</version>
                <configuration>
                    <release>26</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.7.0</version>
            </plugin>
        </plugins>
    </pluginManagement>

    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

`maven-compiler-plugin.version` phải được định nghĩa trong `properties` bằng một phiên bản release cụ thể đã kiểm tra hỗ trợ JDK 26; không để property này rỗng hoặc dùng version range. `pluginManagement` định nghĩa cấu hình mặc định và phiên bản, còn `plugins` kích hoạt plugin trong build. Đừng nhầm `dependencyManagement` với `pluginManagement`.

### 4.3. Khóa JDK và Maven Wrapper

`maven.compiler.release` đặt mức Java mà compiler chấp nhận và tạo bytecode. Nó không tự chọn JDK cài trên máy. Nếu dự án cần bảo đảm compiler đến từ một JDK cụ thể, hãy dùng Maven Toolchains và cấu hình CI cấp đúng JDK 26; kiểm tra `mvnw -v` để biết Maven đang chạy trên JDK nào.

Commit Maven Wrapper (`mvnw`, `mvnw.cmd` và thư mục `.mvn/wrapper`) để mọi người gọi cùng một Maven distribution. Trong `.mvn/wrapper/maven-wrapper.properties`, ghim URL của một distribution cụ thể và checksum SHA-256 đã xác minh:

```properties
distributionUrl=https\://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.10.2/apache-maven-3.10.2-bin.zip
distributionSha256Sum=THAY_BANG_SHA256_DA_XAC_MINH
```

Maven 3.10.2 là bản GA hiện hành tại thời điểm cập nhật nội dung (27-11-2026). Maven 4.0.0-rc-7 vẫn là bản preview và Apache chưa khuyến nghị dùng trong production; vì vậy ví dụ chọn dòng Maven 3 ổn định. Hãy kiểm tra trang tải Maven trước mỗi lần nâng Wrapper để chọn bản GA mới nhất tương thích với dự án. Maven Wrapper hỗ trợ `distributionSha256Sum`; các bản Wrapper phù hợp cũng hỗ trợ `wrapperSha256Sum` để xác minh chính file wrapper JAR. Trang phát hành Apache công bố checksum SHA-512 và chữ ký; hãy xác minh chữ ký/checksum phát hành từ Apache, rồi cung cấp SHA-256 đã xác minh cho thuộc tính Wrapper. Không tự tính checksum từ một file tải xuống chưa xác minh.

### 4.4. Kiểm tra xung đột dependency

Maven có cơ chế mediation để chọn dependency bắc cầu khi nhiều đường dẫn đưa vào các phiên bản khác nhau. Để phát hiện xung đột thay vì âm thầm chấp nhận phiên bản được chọn theo quy tắc mediation, có thể bật Maven Enforcer rule `dependencyConvergence`:

```xml
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
```

Đặt cấu hình này trong `build/plugins` và quản lý phiên bản Enforcer trong `pluginManagement` như ví dụ trước. Khi rule báo xung đột, xem đường dẫn từng dependency, sau đó điều chỉnh BOM hoặc `dependencyManagement`, nâng dependency cha, hoặc loại trừ dependency bắc cầu nếu có lý do tương thích rõ ràng. Không thêm exclusion chỉ để làm build xanh mà chưa kiểm tra chức năng bị ảnh hưởng.

`dependencyConvergence` kiểm tra các đường dẫn có cùng tọa độ dependency đang dùng cùng phiên bản. Nó không phải lockfile, không cố định mọi graph và không kiểm tra checksum của JAR. Vì vậy vẫn cần khai báo phiên bản rõ ràng, BOM, plugin pinning, Wrapper và quy trình kiểm tra nguồn artifact.

Xem graph và POM sau khi Maven hợp nhất parent, profile và plugin management bằng các lệnh:

```bash
./mvnw dependency:tree
./mvnw help:effective-pom
./mvnw verify
```

`dependency:tree` cho biết dependency trực tiếp và bắc cầu; `help:effective-pom` cho biết phiên bản/cấu hình thực sự sau khi áp dụng parent và profile. Chạy trong cùng profile và thuộc tính với CI để kết quả phản ánh đúng build phát hành.

## 5. Khai báo annotation processor một cách tường minh

Annotation processor là chương trình chạy trong quá trình biên dịch để đọc annotation và có thể sinh mã nguồn hoặc tài nguyên. Ví dụ gồm processor sinh metamodel, mapper hoặc mã hỗ trợ boilerplate. Vì processor thực thi mã trong build, nó có cùng mức độ cần tin cậy như plugin build: phải ghim phiên bản, kiểm tra nguồn và giới hạn đúng processor được phép chạy.

Từ JDK 23, `javac` không còn tự động chạy mọi annotation processor tìm thấy trên classpath nếu build không yêu cầu xử lý annotation một cách tường minh. Thay đổi này giúp tránh việc một dependency vô tình mang theo processor không mong muốn rồi được thực thi trong lúc compile. Trên JDK 26, hãy khai báo processor riêng thay vì dựa vào cơ chế tự dò tìm cũ.

### Gradle

Đưa processor vào `annotationProcessor` và `testAnnotationProcessor` khi cần cho source set tương ứng. Nếu mã nguồn cũng cần API annotation ở compile time, khai báo API đó ở `compileOnly` hoặc configuration phù hợp; không đưa cả processor implementation vào runtime của ứng dụng nếu không có lý do.

```kotlin
dependencies {
    compileOnly(libs.my.annotations)
    annotationProcessor(libs.my.processor)

    testCompileOnly(libs.my.annotations)
    testAnnotationProcessor(libs.my.processor)
}
```

Chỉ thêm processor cần thiết vào configuration xử lý annotation. Dependency locking sẽ ghi phiên bản của configuration này khi `lockAllConfigurations()` được bật và configuration đã được phân giải. Không thêm các processor không rõ nguồn gốc vào `implementation` với kỳ vọng compiler sẽ tự tìm thấy.

### Maven 3 với Maven Compiler Plugin 3.x

Với dòng Maven GA hiện hành và Compiler Plugin 3.x, dùng `annotationProcessorPaths` để tách processor khỏi classpath dependency ứng dụng. Có thể liệt kê rõ tên processor được phép chạy:

```xml
<configuration>
    <annotationProcessors>
        <annotationProcessor>com.example.codegen.MyProcessor</annotationProcessor>
    </annotationProcessors>
    <annotationProcessorPaths>
        <path>
            <groupId>com.example</groupId>
            <artifactId>my-processor</artifactId>
            <version>${my-processor.version}</version>
        </path>
    </annotationProcessorPaths>
</configuration>
```

Đặt cấu hình trong plugin `maven-compiler-plugin` đang được ghim phiên bản. Tại thời điểm cập nhật nội dung, Maven Compiler Plugin 3.16.0 là bản phát hành 3.x hiện hành. Maven 4 và Compiler Plugin 4.x vẫn ở giai đoạn preview/beta, nên không dùng kiểu khai báo processor mới của nhánh 4.x làm nền tảng cho build production cần ổn định. Tránh bật `<proc>full</proc>` chỉ để quét toàn bộ classpath: cách đó có thể kích hoạt processor ẩn hoặc không được dự án chủ động cho phép.

## 6. Quy trình nâng phiên bản an toàn

Khi cần nâng một dependency, plugin hoặc processor, thực hiện theo thứ tự:

1. **Xác định lý do nâng.** Ví dụ cần bản vá bảo mật, sửa lỗi, hỗ trợ JDK 26 hoặc tính năng mới. Kiểm tra release note, chính sách hỗ trợ JDK và yêu cầu tối thiểu của dependency cha.
2. **Chọn phiên bản release cụ thể.** Ưu tiên phiên bản ổn định còn được bảo trì. Kiểm tra tương thích giữa thư viện, plugin, annotation processor, build tool và JDK 26.
3. **Cập nhật nguồn quản lý phiên bản.** Sửa version catalog hoặc BOM/dependencyManagement; với plugin, sửa plugin catalog/pluginManagement hoặc pluginManagement của Maven; với processor, sửa đúng configuration hoặc processor dependency.
4. **Phân giải và xem graph.** Dùng `dependencyInsight`/`dependencies` của Gradle hoặc `dependency:tree`/`effective-pom` của Maven để hiểu các thay đổi bắc cầu và xung đột.
5. **Cập nhật lock và verification.** Với Gradle, tạo lại lock state và metadata verification, sau đó review diff. Với Maven, cập nhật BOM và phiên bản được quản lý, kiểm tra convergence và checksum Wrapper/artifact theo quy trình repository của tổ chức.
6. **Chạy kiểm tra trên JDK 26 đã ghim.** Build sạch, test, kiểm tra đóng gói và chạy smoke test. Nếu thay processor, xác nhận mã sinh ra được cập nhật và không còn phụ thuộc vào output cũ trong thư mục build.
7. **Ghi nhận thay đổi.** Commit cùng nhau build script, lockfile, verification metadata, Wrapper và các file cấu hình liên quan. Ghi rõ lý do nâng để lần sau có thể đánh giá lại.

## 7. Checklist cho build Java 26

- [ ] JDK 26 và build tool được chọn rõ; Wrapper đã ghim distribution cụ thể.
- [ ] Build tool/plugin đã được kiểm tra tương thích với JDK 26 theo tài liệu chính thức.
- [ ] Dependency trực tiếp có phiên bản cụ thể hoặc được quản lý bằng BOM/version catalog.
- [ ] Không dùng dynamic version, version range hoặc SNAPSHOT trong build phát hành.
- [ ] Dependency bắc cầu được kiểm tra; Gradle có lock state hoặc Maven có BOM và kiểm tra convergence phù hợp.
- [ ] Plugin build được ghim phiên bản riêng; không nhầm dependency management của ứng dụng với dependency của plugin.
- [ ] Annotation processor được khai báo riêng, ghim phiên bản và chỉ gồm processor đã duyệt.
- [ ] Artifact và distribution được kiểm tra checksum/chữ ký từ nguồn đáng tin cậy.
- [ ] CI build sạch và test trên JDK đã quy định; diff lockfile/verification được review khi nâng phiên bản.

Không có một con số phiên bản duy nhất phù hợp cho mọi dự án. Hãy chọn bản release đang được hỗ trợ, tương thích với JDK 26 và hệ sinh thái dự án tại thời điểm nâng cấp; sau đó ghim chính xác lựa chọn đó trong cấu hình và source control.

## Tài liệu tham khảo

- [Gradle: Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html)
- [Gradle: Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle: Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html)
- [Gradle: Locking Versions](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Gradle: Securing Dependencies](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Gradle: Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html)
- [Maven: Introduction to the Dependency Mechanism and BOMs](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Maven: Annotation Processors](https://maven.apache.org/components/plugins/maven-compiler-plugin-4.x/examples/annotation-processor.html)
- [Maven Enforcer: Dependency Convergence](https://maven.apache.org/components/enforcer/enforcer-rules/dependencyConvergence.html)
- [Apache Maven Wrapper: Checksum Verification](https://maven.apache.org/tools/wrapper/)
- [Apache Maven: Current Downloads and Release Status](https://maven.apache.org/download.cgi)
- [Apache Maven Compiler Plugin: Current Plugin Releases](https://maven.apache.org/plugins/)
- [JDK 26: The javac Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
