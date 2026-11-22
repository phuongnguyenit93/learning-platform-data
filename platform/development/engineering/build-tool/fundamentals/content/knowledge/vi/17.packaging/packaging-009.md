# Tệp nguồn, tài liệu API và các artifact bổ trợ

Một thư viện Java thường được phát hành dưới dạng JAR chứa bytecode và resource để ứng dụng khác có thể sử dụng. Tuy nhiên, người dùng thư viện còn cần đọc mã nguồn khi debug, xem tài liệu API khi tích hợp, tải các file kiểm thử dùng chung hoặc xác minh nguồn gốc và tính toàn vẹn của bản phát hành. Vì vậy, một lần release có thể tạo nhiều artifact đi kèm với JAR chính.

Các artifact bổ trợ thường gặp gồm **Sources JAR** chứa mã nguồn, **Javadoc JAR** chứa tài liệu API HTML, test JAR hoặc test fixtures, archive phân phối ZIP/TAR, SBOM, checksum và chữ ký. Chúng thường dùng chung tọa độ Maven cơ bản với artifact chính nhưng được phân biệt bằng classifier hoặc phần mở rộng file. Build tool có trách nhiệm tạo chúng từ đúng đầu vào, gắn chúng vào publication và publish cùng phiên bản.

Bài này giải thích vai trò của từng loại artifact, cách Maven và Gradle tạo cũng như phát hành chúng, cách consumer tải đúng biến thể và những điểm cần lưu ý để bản phát hành có thể sử dụng, debug và xác minh được.

## 1. Artifact chính và artifact bổ trợ

Một project Maven/Gradle có thể tạo nhiều file từ cùng một source tree. Ví dụ một thư viện có thể phát hành:

```text
customer-model-1.4.0.jar
customer-model-1.4.0-sources.jar
customer-model-1.4.0-javadoc.jar
customer-model-1.4.0-tests.jar
customer-model-1.4.0.pom
customer-model-1.4.0.module
customer-model-1.4.0.jar.sha256
customer-model-1.4.0.jar.asc
```

Đây là danh sách minh họa; không phải dự án nào cũng tạo mọi file. Vai trò điển hình:

| Artifact | Nội dung | Người sử dụng chính |
|---|---|---|
| JAR chính | Bytecode và resource của thư viện/ứng dụng | JVM, project phụ thuộc |
| Sources JAR | File `.java` tương ứng với phiên bản đã phát hành | IDE, developer debug và đọc implementation |
| Javadoc JAR | HTML tài liệu API được sinh từ Javadoc comments | IDE, developer tích hợp thư viện |
| Test JAR/test fixtures | Test class hoặc tiện ích kiểm thử được chia sẻ | Project kiểm thử khác |
| Distribution ZIP/TAR | Ứng dụng, thư viện phụ thuộc, script và file hướng dẫn | Người triển khai/vận hành |
| POM/Gradle Module Metadata | Tọa độ, dependency và metadata publication | Maven/Gradle khi resolve |
| SBOM | Danh sách thành phần phần mềm và thông tin liên quan | Security, compliance, vận hành |
| Checksum | Digest để kiểm tra nội dung file | Client hoặc pipeline xác minh tải xuống |
| Chữ ký | Bằng chứng mật mã gắn với artifact | Consumer xác minh publisher và tính toàn vẹn |

Artifact chính và artifact bổ trợ thường được tạo từ cùng một version/release. Việc phát hành chúng đồng bộ giúp người dùng tải được đúng source và tài liệu tương ứng với binary mà họ đang sử dụng.

## 2. Classifier và cách định danh artifact bổ trợ

Trong Maven repository, artifact chính thường được nhận diện bằng tọa độ:

```text
groupId:artifactId:version
```

Một artifact bổ trợ có thể dùng thêm **classifier** để phân biệt biến thể:

```text
groupId:artifactId:version:classifier:extension
```

Ví dụ:

```text
vn.acme:customer-model:1.4.0              -> customer-model-1.4.0.jar
vn.acme:customer-model:1.4.0:sources      -> customer-model-1.4.0-sources.jar
vn.acme:customer-model:1.4.0:javadoc      -> customer-model-1.4.0-javadoc.jar
vn.acme:customer-model:1.4.0:tests        -> customer-model-1.4.0-tests.jar
```

Classifier không thay thế `groupId`, `artifactId` hoặc `version`. Nó xác định một biến thể được phát hành cùng artifact chính. Extension cho biết định dạng file, ví dụ `jar`, `zip` hoặc `tar.gz`.

Một số quy ước phổ biến:

- `sources`: mã nguồn.
- `javadoc`: tài liệu API HTML.
- `tests`: test classes hoặc test utilities.
- `all`: thường được một số plugin dùng cho archive tổng hợp, nhưng không phải classifier chuẩn chung cho mọi dự án.
- `linux-x86_64`, `windows-x86_64`: classifier tùy dự án để phân biệt binary theo nền tảng.

Classifier phải được consumer khai báo đúng khi cần tải artifact phụ. Ví dụ, khai báo dependency JAR chính không có nghĩa Maven tự tải Sources JAR hoặc Javadoc JAR vào compile/runtime classpath. IDE có thể tải source và documentation riêng để hiển thị khi người dùng yêu cầu.

## 3. Sources JAR: mã nguồn đi kèm binary

Sources JAR là archive chứa mã nguồn `.java` tương ứng với một phiên bản artifact đã phát hành. Tên file thường có hậu tố `-sources.jar` và classifier `sources`.

Ví dụ cấu trúc:

```text
customer-model-1.4.0-sources.jar
└── com/
    └── example/
        └── customer/
            ├── Customer.java
            ├── CustomerId.java
            └── CustomerRepository.java
```

Sources JAR giúp IDE hiển thị source khi developer điều hướng vào class của dependency, đặt breakpoint, xem implementation hoặc đọc logic xử lý. Nó cũng giúp người dùng hiểu hành vi của thư viện khi Javadoc chưa giải thích đủ.

### 3.1. Sources JAR khác source repository

Sources JAR chỉ là snapshot các file nguồn được đóng gói cho một version. Nó không thay thế Git repository:

- Không chứa lịch sử commit, branch, tag, issue hoặc pull request.
- Không nhất thiết chứa toàn bộ build script, CI workflow và tài liệu dự án.
- Thường chỉ chứa source tương ứng với artifact/module được phát hành.
- Không cung cấp quy trình đóng góp hoặc review như VCS.

Git tag có thể chỉ ra commit đã tạo ra Sources JAR, nhưng Sources JAR và Git repository có mục đích khác nhau.

### 3.2. Nguồn nào được đưa vào Sources JAR?

Thông thường Sources JAR chứa source của source set chính. Dự án cần xác định có đưa vào các nguồn sau hay không:

- Source Java do developer viết.
- Source được sinh bởi annotation processor.
- Source được sinh bởi task code generator riêng.
- Source của module con trong publication đa module.

Generated source có thể nằm trong thư mục `target/generated-sources/...` hoặc `build/generated/sources/...`. Nếu muốn Sources JAR chứa chúng, phải cấu hình source set/source roots hoặc plugin tương ứng. Không nên giả định mọi generated source đều tự động được đưa vào archive.

Không đưa test source vào Sources JAR production nếu không có chủ đích. Test source thường được phát hành riêng hoặc giữ trong source repository.

### 3.3. Sources JAR phải khớp binary

Sources JAR cần được tạo từ cùng commit, version và cấu hình nguồn với binary JAR. Nếu binary được build từ tag `v1.4.0` nhưng Sources JAR được tạo từ nhánh đang phát triển sau tag, IDE có thể hiển thị code không khớp với bytecode đang debug.

Pipeline release nên tạo binary, source và tài liệu từ cùng một checkout và cùng version. Không nên upload thủ công Sources JAR được build ở một thời điểm khác rồi gắn vào tọa độ release đã có.

## 4. Javadoc JAR: tài liệu API được đóng gói

Javadoc JAR là archive chứa HTML được tạo bởi công cụ Javadoc từ source code và Javadoc comments. Tên file thường có hậu tố `-javadoc.jar` và classifier `javadoc`.

Ví dụ cấu trúc:

```text
customer-model-1.4.0-javadoc.jar
├── index.html
├── overview-tree.html
├── allclasses-index.html
├── com/
│   └── example/
│       └── customer/
│           ├── Customer.html
│           └── CustomerRepository.html
├── element-list
└── resources/
```

Tên file và cấu trúc HTML cụ thể thay đổi theo phiên bản JDK/Javadoc tool. Điều quan trọng là Javadoc JAR chứa tài liệu đã sinh, không phải source code và cũng không phải bytecode chạy ứng dụng.

### 4.1. Javadoc comments

Javadoc lấy thông tin từ comment theo cú pháp `/** ... */` gắn với class, interface, method, constructor, field và package/module.

Ví dụ:

```java
/**
 * Tìm khách hàng theo định danh.
 *
 * @param id định danh khách hàng cần tìm
 * @return khách hàng nếu tồn tại
 * @throws IllegalArgumentException nếu id là null
 */
public Optional<Customer> findById(CustomerId id) {
    // implementation
}
```

Javadoc có thể tạo trang mô tả API, hierarchy, package, method và các liên kết giữa kiểu dữ liệu. Các tag thường dùng:

| Tag | Mục đích |
|---|---|
| `@param` | Mô tả tham số method/constructor hoặc type parameter |
| `@return` | Mô tả giá trị trả về |
| `@throws` / `@exception` | Mô tả exception có thể được ném |
| `@since` | Chỉ phiên bản API được thêm vào |
| `@deprecated` | Đánh dấu API không còn được khuyến nghị và nêu cách thay thế |
| `@see` | Tham chiếu đến API hoặc tài liệu liên quan |
| `{@link ...}` | Liên kết đến kiểu/thành viên API khác |
| `{@code ...}` | Hiển thị đoạn code inline |
| `{@inheritDoc}` | Kế thừa mô tả từ declaration cha khi phù hợp |

Javadoc tốt nên mô tả hợp đồng sử dụng, điều kiện đầu vào, kết quả, side effect, exception và giới hạn của API. Chỉ lặp lại tên method hoặc viết comment chung chung sẽ không giúp người tích hợp hiểu hành vi.

### 4.2. Javadoc cho API công khai và API nội bộ

Thư viện được publish nên ưu tiên tài liệu hóa public/protected API mà consumer có thể sử dụng. Với module system, có thể dùng các tùy chọn Javadoc để kiểm soát package được đưa vào tài liệu. API nội bộ không nên vô tình trở thành hợp đồng được người dùng phụ thuộc.

Tài liệu cần đồng bộ với version binary. Khi API thay đổi, Javadoc JAR phải được tạo lại cùng release; không dùng tài liệu từ một version khác để đính kèm.

### 4.3. Liên kết đến Javadoc của dependency

Javadoc có thể tạo liên kết đến tài liệu API bên ngoài bằng tùy chọn `-link` hoặc cấu hình tương ứng của plugin. Ví dụ tài liệu của thư viện có thể liên kết đến Java SE API hoặc Javadoc của dependency.

Liên kết ngoài giúp người đọc chuyển từ kiểu dependency sang tài liệu chính thức. Tuy nhiên, build có thể phụ thuộc mạng nếu plugin cần tải package list/element list từ URL. Với CI offline hoặc mạng hạn chế, cần xem cách cung cấp tài liệu ngoài và xử lý warning/error.

## 5. Maven: tạo Sources JAR

Maven Source Plugin tạo source archive và có thể attach nó vào project publication. Cấu hình thường đặt trong `build/plugins` của POM:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-source-plugin</artifactId>
            <version>3.3.1</version>
            <executions>
                <execution>
                    <id>attach-sources</id>
                    <goals>
                        <goal>jar-no-fork</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Goal `jar-no-fork` tạo Sources JAR và attach vào project để các phase publish như `install` hoặc `deploy` có thể xử lý cùng artifact chính. Có thể chạy goal trực tiếp hoặc theo lifecycle đã cấu hình:

```bash
./mvnw clean package
```

Sau build, kiểm tra thư mục `target/` để xác nhận có file `*-sources.jar`. Tên và thời điểm tạo phụ thuộc plugin configuration và lifecycle execution.

### 5.1. Đưa generated source vào Sources JAR

Nếu project có source được sinh bởi annotation processor hoặc code generator, hãy xác nhận source root đó đã được đăng ký với Maven project/compiler plugin. Source Plugin có các tùy chọn cấu hình để xử lý source roots được thêm trong build. Cách tích hợp cụ thể phụ thuộc generator và plugin version.

Không nên copy thủ công mọi thư mục `target/generated-sources` vào source archive. Chỉ đưa những source thuộc API/implementation mà dự án có chủ đích phát hành, tránh file trung gian hoặc source được sinh cho mục đích nội bộ.

## 6. Maven: tạo Javadoc JAR

Maven Javadoc Plugin tạo tài liệu HTML và có goal `jar` để đóng gói tài liệu thành Javadoc JAR. Ví dụ:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-javadoc-plugin</artifactId>
            <version>3.11.2</version>
            <executions>
                <execution>
                    <id>attach-javadocs</id>
                    <goals>
                        <goal>jar</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Khi chạy lifecycle package phù hợp, plugin tạo HTML, đóng gói và attach classifier `javadoc`. Có thể chạy:

```bash
./mvnw clean package
```

Hoặc gọi goal Javadoc trực tiếp trong giai đoạn phát triển:

```bash
./mvnw javadoc:javadoc
```

Goal `javadoc:javadoc` tạo tài liệu trong output directory nhưng không nhất thiết attach Javadoc JAR để publish. Muốn phát hành classifier `javadoc`, dùng goal `javadoc:jar` hoặc execution tương ứng.

### 6.1. Cấu hình Javadoc cho API phức tạp

Một số dự án cần cấu hình thêm:

- `source` hoặc `release` phù hợp với phiên bản Java.
- `links` đến Javadoc của Java platform hoặc dependency.
- `doclint` để kiểm tra cú pháp và nội dung documentation.
- `failOnError`/`failOnWarnings` theo chính sách chất lượng của dự án.
- Include/exclude package hoặc source file.
- Encoding của source và tài liệu.

Ví dụ cấu hình rút gọn:

```xml
<configuration>
    <source>21</source>
    <encoding>UTF-8</encoding>
    <doclint>all</doclint>
    <links>
        <link>https://docs.oracle.com/en/java/javase/21/docs/api/</link>
    </links>
</configuration>
```

Tên parameter và cách truyền vào Javadoc tool phụ thuộc phiên bản Maven Javadoc Plugin. Khi nâng JDK, cần kiểm tra plugin có hỗ trợ JDK đó và các tùy chọn doclint có còn phù hợp không.

### 6.2. Javadoc lỗi do comment hoặc dependency

Javadoc có thể thất bại dù compile thành công, ví dụ:

- Link đến kiểu không tồn tại hoặc không nằm trong doclet classpath.
- Tag `@param` không khớp tên tham số.
- HTML trong comment không hợp lệ.
- Javadoc tool không truy cập được tài liệu external link.
- Module/package không được chọn đúng khi chạy Javadoc.

Nên xử lý warning/error theo chính sách của dự án. Nếu tạm thời phải bỏ qua một số lỗi do dependency bên ngoài, hãy cấu hình có mục đích và giữ tài liệu API của chính thư viện ở trạng thái rõ ràng.

## 7. Gradle: tạo Sources JAR

Gradle Java plugin có thể tạo Sources JAR bằng `withSourcesJar()`. Khi bật, plugin đăng ký task `sourcesJar` và thêm source artifact vào outgoing variants/publication của Java component.

Ví dụ Kotlin DSL:

```kotlin
plugins {
    `java-library`
    `maven-publish`
}

group = "vn.acme"
version = "1.4.0"

java {
    withSourcesJar()
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }
}
```

Gradle tạo task `sourcesJar`. Chạy:

```bash
./gradlew sourcesJar
```

hoặc:

```bash
./gradlew build
```

File thường xuất hiện trong `build/libs/` với classifier `sources`, ví dụ `project-1.4.0-sources.jar`.

`withSourcesJar()` lấy source từ source set chính theo cấu hình Java plugin. Nếu có generated source hoặc source directory bổ sung, hãy đăng ký chúng vào đúng source set để artifact phản ánh nội dung mong muốn.

## 8. Gradle: tạo Javadoc JAR

Gradle Java plugin có thể tạo Javadoc JAR bằng `withJavadocJar()`. Tùy chọn này đăng ký task `javadocJar` và gắn tài liệu Javadoc vào outgoing Java component.

Ví dụ:

```kotlin
plugins {
    `java-library`
    `maven-publish`
}

java {
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }
}
```

Các task liên quan:

```bash
./gradlew javadoc
./gradlew javadocJar
```

Task `javadoc` tạo HTML trong build output; `javadocJar` đóng gói HTML thành archive có classifier `javadoc`. Nếu chỉ cần publish tài liệu, cần bảo đảm `withJavadocJar()` hoặc cấu hình publication tương đương đã được bật.

### 8.1. Cấu hình Javadoc task

Có thể cấu hình task Javadoc để điều chỉnh encoding, source level, links và doclint:

```kotlin
tasks.withType<Javadoc>().configureEach {
    options.encoding = "UTF-8"
    (options as StandardJavadocDocletOptions).apply {
        links("https://docs.oracle.com/en/java/javase/21/docs/api/")
        addBooleanOption("Xdoclint:all", true)
    }
}
```

Ví dụ minh họa cách cấu hình Javadoc task bằng Kotlin DSL. Cần import các type tương ứng hoặc để build script dùng API được Gradle cung cấp; tùy chọn doclet có thể khác theo JDK. Nên kiểm tra tài liệu Javadoc tool của phiên bản JDK mục tiêu.

## 9. Phát hành Sources/Javadoc cùng publication

Tạo file trong `build/libs/` hoặc `target/` chưa đồng nghĩa artifact đã được publish. Build phải gắn artifact vào publication hoặc cấu hình deploy để repository nhận chúng.

### 9.1. Maven

Khi Source Plugin và Javadoc Plugin attach classifier vào Maven project, các phase `install` và `deploy` có thể cài/publish artifact bổ trợ cùng artifact chính:

```bash
# Cài vào local repository để thử nghiệm
./mvnw clean install

# Publish lên remote repository đã cấu hình
./mvnw clean deploy
```

Thông thường repository sẽ nhận JAR chính, POM, Sources JAR và Javadoc JAR nếu các execution tương ứng chạy thành công. Nếu plugin chỉ tạo file mà không attach artifact, file có thể nằm trong `target/` nhưng không được deploy.

### 9.2. Gradle

Khi dùng `maven-publish` và `from(components["java"])`, Java component có thể mang theo binary, sources và Javadoc variants đã được bật bằng `withSourcesJar()`/`withJavadocJar()`.

Publish vào Maven Local:

```bash
./gradlew publishToMavenLocal
```

Publish lên repository được cấu hình:

```bash
./gradlew publish
```

Các task cụ thể có thể có tên theo publication và repository, ví dụ `publishMavenJavaPublicationToCompanyRepository`. Dùng `./gradlew tasks --all` để xem task thực tế.

Khi publication được tạo thủ công thay vì `from(components["java"])`, cần khai báo các artifact bổ trợ rõ ràng. Nếu không, `sourcesJar` hoặc `javadocJar` có thể được tạo nhưng không xuất hiện trong repository.

## 10. Test JAR và test fixtures

Một số thư viện muốn chia sẻ test utilities giữa nhiều module, chẳng hạn fixture tạo dữ liệu, mock server hoặc helper kiểm thử. Có thể phát hành test JAR riêng, nhưng cần tránh đưa test-only class vào artifact production.

### 10.1. Maven test JAR

Maven JAR Plugin cung cấp goal `test-jar` để đóng gói test classes thành artifact classifier `tests`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.4.2</version>
    <executions>
        <execution>
            <goals>
                <goal>test-jar</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Consumer có thể khai báo artifact test với type/classifier tương ứng:

```xml
<dependency>
    <groupId>vn.acme</groupId>
    <artifactId>customer-model</artifactId>
    <version>1.4.0</version>
    <type>test-jar</type>
    <classifier>tests</classifier>
    <scope>test</scope>
</dependency>
```

Test JAR thường chỉ được dùng trong test scope. Consumer vẫn cần khai báo dependency production cần thiết; không nên giả định test JAR tự mang theo đầy đủ dependency runtime của thư viện.

### 10.2. Gradle test fixtures

Gradle có Java Test Fixtures plugin để tổ chức test utility như một source set riêng:

```kotlin
plugins {
    `java-library`
    `java-test-fixtures`
}
```

Test fixtures thường được đặt trong:

```text
src/testFixtures/java/
src/testFixtures/resources/
```

Module khác có thể dùng fixture qua cấu hình dependency phù hợp, ví dụ:

```kotlin
dependencies {
    testImplementation(testFixtures(project(":customer-model")))
}
```

Test Fixtures plugin tạo variant riêng cho fixture và hỗ trợ publish/consume theo metadata Gradle. Nếu publish ra Maven repository cho consumer Maven, cần hiểu cách variant được biểu diễn bằng classifier/metadata và xác nhận tương thích với consumer. Test fixtures là API hỗ trợ test, không phải API production mặc định.

## 11. Distribution archive: ZIP và TAR

Ngoài JAR, ứng dụng có thể cần một gói phân phối gồm:

- JAR ứng dụng.
- Các dependency runtime trong thư mục `lib/`.
- Script khởi chạy.
- File cấu hình mẫu.
- README, license và notice.
- File hỗ trợ vận hành hoặc migration.

Một distribution có thể có cấu trúc:

```text
order-service-1.4.0/
├── bin/
│   ├── order-service
│   └── order-service.bat
├── lib/
│   ├── order-service-1.4.0.jar
│   ├── jackson-databind.jar
│   └── logging.jar
├── conf/
│   └── application.properties.example
├── README.md
├── LICENSE
└── NOTICE
```

Archive phân phối thường được phát hành dưới dạng `.zip` hoặc `.tar.gz`. Nó khác JAR: archive có thể chứa nhiều file và script, trong khi JAR là package Java có cấu trúc/metadata riêng.

### 11.1. Gradle Application plugin và Distribution plugin

Gradle Application plugin có thể tạo distribution gồm application JAR, runtime dependencies và script launcher:

```kotlin
plugins {
    application
}

application {
    mainClass = "com.example.order.Main"
}
```

Các task thường gặp:

```bash
./gradlew installDist
./gradlew distZip
./gradlew distTar
```

`installDist` tạo cấu trúc distribution trong build directory; `distZip` và `distTar` tạo archive tương ứng. Nội dung được lấy từ application distribution conventions và có thể tùy chỉnh qua `distributions`.

Ví dụ thêm file tài liệu:

```kotlin
distributions {
    main {
        contents {
            from("README.md")
            from("LICENSE")
            into("conf") {
                from("src/dist/conf")
            }
        }
    }
}
```

Không nên đưa cấu hình chứa secret hoặc file chỉ dành cho máy developer vào distribution. Hãy đóng gói file mẫu và để môi trường triển khai cung cấp giá trị thực.

### 11.2. Maven Assembly Plugin

Maven Assembly Plugin có thể tạo archive ZIP/TAR theo descriptor. Ví dụ một assembly descriptor có thể quy định:

```xml
<assembly xmlns="http://maven.apache.org/ASSEMBLY/2.2.0">
    <id>distribution</id>
    <formats>
        <format>zip</format>
        <format>tar.gz</format>
    </formats>
    <includeBaseDirectory>true</includeBaseDirectory>
    <dependencySets>
        <dependencySet>
            <outputDirectory>lib</outputDirectory>
            <scope>runtime</scope>
        </dependencySet>
    </dependencySets>
    <fileSets>
        <fileSet>
            <directory>src/dist</directory>
            <outputDirectory>/</outputDirectory>
        </fileSet>
    </fileSets>
</assembly>
```

Descriptor đầy đủ còn có thể cấu hình file mode, include/exclude, output name và dependency filtering. Chỉ đưa dependency runtime cần thiết vào archive; không copy test dependency hoặc build-time processor nếu ứng dụng không dùng chúng lúc chạy.

## 12. SBOM: danh sách thành phần phần mềm

SBOM (Software Bill of Materials) là tài liệu có cấu trúc liệt kê các thành phần phần mềm trong một sản phẩm. SBOM có thể ghi nhận:

- Tên và version của dependency.
- Package URL (purl) hoặc định danh package.
- Nhà cung cấp và thông tin nguồn nếu có.
- Quan hệ dependency giữa các thành phần.
- License và thông tin bản quyền khi được xác định.
- Hash hoặc thông tin xác minh artifact nếu công cụ hỗ trợ.

Các định dạng thường gặp gồm CycloneDX và SPDX. SBOM có thể được phát hành như một file JSON/XML riêng, đính kèm vào release hoặc lưu trong hệ thống quản lý artifact/security.

SBOM không phải Javadoc và cũng không phải dependency tree đơn thuần. Nó phục vụ khả năng kiểm kê thành phần, đánh giá lỗ hổng, license và truy xuất nguồn gốc. SBOM cần được tạo từ dependency graph và artifact thực tế của đúng release; nếu chỉ lấy khai báo dependency trực tiếp, nó có thể thiếu dependency bắc cầu.

Trong Maven/Gradle, có thể dùng plugin hoặc công cụ chuyên dụng để tạo SBOM trong CI. Nên lưu SBOM cùng version với artifact chính và xác định rõ nó mô tả build variant, profile hoặc platform nào.

## 13. Checksum và chữ ký artifact

Checksum và chữ ký đều có thể được phát hành kèm artifact, nhưng phục vụ các mục tiêu khác nhau.

### 13.1. Checksum

Checksum là digest tính từ nội dung file, thường dùng SHA-256 hoặc SHA-512. Consumer tải artifact và tính lại digest để kiểm tra file có bị thay đổi hoặc hỏng trong quá trình truyền hay không.

Ví dụ tạo SHA-256:

```bash
# Linux
sha256sum customer-model-1.4.0.jar

# macOS
shasum -a 256 customer-model-1.4.0.jar

# Windows PowerShell
Get-FileHash customer-model-1.4.0.jar -Algorithm SHA256
```

Checksum chỉ xác nhận nội dung khớp với digest được đối chiếu. Nếu attacker có thể thay cả artifact và file checksum ở cùng nơi mà không có cơ chế xác thực, checksum đơn thuần không chứng minh publisher đáng tin cậy.

### 13.2. Chữ ký số

Chữ ký số gắn nội dung artifact với khóa ký của publisher. Với JAR, JDK cung cấp công cụ `jarsigner` để ký và xác minh archive. Một số repository/pipeline còn dùng detached signature, chẳng hạn file `.asc` được tạo bằng hệ thống ký phù hợp.

Consumer cần xác minh chữ ký và tin cậy public key/certificate theo chính sách. Chỉ thấy file chữ ký bên cạnh JAR không có nghĩa artifact đã được xác minh.

Không commit private key hoặc password keystore vào source repository. CI release nên lấy khóa từ secret manager/HSM hoặc cơ chế bảo vệ khóa của tổ chức, giới hạn quyền ký và ghi nhận audit.

## 14. Metadata publication: POM và Gradle Module Metadata

Artifact repository thường lưu metadata đi kèm binary để build tool biết cách sử dụng artifact.

**Maven POM** mô tả tọa độ, dependency, scope, packaging và một số metadata khác. Khi publish Sources/Javadoc JAR bằng classifier, Maven consumer có thể tải các file đó theo tọa độ/variant tương ứng.

**Gradle Module Metadata** thường có phần mở rộng `.module`, mô tả variants, capabilities, attributes và dependency theo mô hình Gradle. Nó có thể biểu diễn nhiều variant chính xác hơn POM Maven truyền thống.

Một publication Gradle có thể tạo cả POM và Gradle Module Metadata tùy cấu hình/repository. Consumer Gradle có thể sử dụng metadata phù hợp; Maven consumer chủ yếu dựa trên POM và artifact/classifier.

Metadata không thay thế JAR. Nó mô tả cách phân giải và lựa chọn artifact. Nếu metadata khai báo variant hoặc classifier nhưng file tương ứng không được publish, consumer có thể gặp lỗi khi resolve hoặc tải artifact.

## 15. Maven: kiểm tra và phát hành toàn bộ artifact

Sau khi cấu hình Source Plugin, Javadoc Plugin và các plugin bổ trợ, có thể chạy:

```bash
./mvnw clean package
```

Liệt kê thư mục output:

```text
target/
├── customer-model-1.4.0.jar
├── customer-model-1.4.0-sources.jar
├── customer-model-1.4.0-javadoc.jar
└── ...
```

Kiểm tra file cụ thể:

```bash
jar --list --file target/customer-model-1.4.0-sources.jar
jar --list --file target/customer-model-1.4.0-javadoc.jar
```

Sau đó publish:

```bash
./mvnw deploy
```

Để release hoàn chỉnh, cần bảo đảm mọi execution attach artifact đã chạy thành công trước phase deploy. Nếu chỉ chạy một goal tạo file thủ công nhưng không attach vào MavenProject, deploy có thể chỉ upload artifact chính và bỏ qua file phụ.

Với multi-module Maven, mỗi module có thể có artifact chính và artifact phụ riêng. Cần đặt plugin execution ở parent phù hợp hoặc khai báo tại module cần publish, tránh vô tình tạo Javadoc/test artifact cho module không phát hành.

## 16. Gradle: kiểm tra và phát hành toàn bộ artifact

Với Java plugin, có thể chạy:

```bash
./gradlew clean jar sourcesJar javadocJar
```

Kiểm tra output trong `build/libs/`. Khi publication dùng `from(components["java"])`, sources/Javadoc variants đã bật có thể được đưa vào Maven publication.

Publish thử vào local Maven repository:

```bash
./gradlew publishToMavenLocal
```

Sau đó kiểm tra tọa độ trong:

```text
~/.m2/repository/<group path>/<artifact>/<version>/
```

Khi publish remote, kiểm tra task publication cụ thể, credential và repository endpoint. Không nên suy luận rằng mọi task `jar`, `sourcesJar`, `javadocJar` được chạy thì tất cả file đều tự động xuất hiện trên remote; phải xem publication đã gắn các artifact tương ứng chưa.

## 17. Đồng bộ version và provenance

Binary, source, Javadoc, SBOM và distribution archive nên cùng phản ánh một release. Ví dụ:

```text
Git tag:             customer-model-v1.4.0
Source commit:       <commit hash>
Maven coordinate:    vn.acme:customer-model:1.4.0
Binary:              customer-model-1.4.0.jar
Sources:             customer-model-1.4.0-sources.jar
Javadoc:             customer-model-1.4.0-javadoc.jar
SBOM:                customer-model-1.4.0.cyclonedx.json
Checksum:            customer-model-1.4.0.jar.sha256
Signature:           customer-model-1.4.0.jar.asc
```

Pipeline nên tạo các artifact từ cùng commit và ghi lại thông tin build như JDK, build tool version, dependency graph, build number và repository destination nếu cần. Điều này giúp consumer xác định binary đang dùng, developer mở đúng source và security team đối chiếu SBOM.

Release version đã publish nên bất biến. Nếu source hoặc Javadoc thay đổi sau khi phát hành, hãy tạo version mới hoặc thực hiện quy trình sửa release được tổ chức cho phép; không âm thầm thay file dưới cùng tọa độ release.

## 18. Reproducible artifacts và thời điểm tạo file

Để hai lần build cùng source/configuration tạo artifact có nội dung ổn định, cần kiểm soát các yếu tố ảnh hưởng đến archive:

- Thứ tự entry trong ZIP/JAR.
- Timestamp của file entry.
- Version JDK và build plugin.
- Encoding và locale.
- Generated documentation có chứa ngày/giờ hoặc đường dẫn máy hay không.
- Dependency và plugin được resolve.
- Thông tin build được ghi vào manifest hoặc metadata.

Reproducible build không có nghĩa mọi file đều giống byte-for-byte nếu pipeline chủ động thêm timestamp hoặc build ID. Nếu cần tính tái lập, hãy dùng tính năng reproducible archive của build tool/plugin, pin version công cụ và dependency, đồng thời tránh đưa đường dẫn tuyệt đối hoặc dữ liệu môi trường không ổn định vào artifact.

Sources JAR và Javadoc JAR cũng cần được tạo theo cùng nguyên tắc. Nếu binary reproducible nhưng Javadoc chứa timestamp hiện tại hoặc nguồn link thay đổi theo môi trường, artifact bổ trợ vẫn có thể khác giữa các lần build.

## 19. Những lỗi thường gặp khi phát hành artifact bổ trợ

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| IDE không tải được source | Sources JAR chưa được publish hoặc classifier sai | Kiểm tra `*-sources.jar` và publication |
| IDE không hiển thị API docs | Javadoc JAR thiếu hoặc Javadoc goal chỉ tạo HTML local | Dùng goal/variant attach Javadoc JAR và publish |
| Source không khớp bytecode | Sources JAR tạo từ commit/version khác | Tạo mọi artifact từ cùng checkout/release |
| Javadoc build thất bại | Comment/tag/HTML/link/module configuration không hợp lệ | Xem log Javadoc, doclint và external links |
| File có trong `target/` nhưng không có remote repository | Artifact chưa được attach hoặc publication không include | Kiểm tra Maven execution/Gradle publication components |
| Test JAR không được consumer resolve | Sai classifier/type hoặc chưa publish artifact | Kiểm tra tọa độ dependency và repository content |
| Distribution thiếu dependency | Archive descriptor chỉ lấy JAR chính hoặc sai scope | Kiểm tra runtime dependency set và nội dung ZIP/TAR |
| SBOM không khớp artifact | Tạo từ graph khác profile/variant hoặc thời điểm khác | Tạo SBOM từ đúng release build và ghi metadata version |
| Checksum không khớp | File bị thay đổi sau khi tính digest hoặc tải sai | Tính lại từ artifact cuối cùng sau mọi bước đóng gói/ký |
| Chữ ký không hợp lệ | Archive bị sửa sau khi ký hoặc key/certificate không đúng | Ký sau cùng và xác minh trên file phát hành cuối |

## 20. Quy trình release gợi ý

Một pipeline phát hành thư viện Java có thể thực hiện theo thứ tự:

```text
Checkout release tag / commit
          |
          v
Thiết lập JDK và build tool đã pin
          |
          v
Resolve dependency và build sạch
          |
          v
Compile + test + kiểm tra chất lượng
          |
          v
Tạo JAR/WAR chính
          |
          +--> Tạo Sources JAR
          |
          +--> Tạo Javadoc JAR
          |
          +--> Tạo test artifact nếu cần
          |
          +--> Tạo distribution archive nếu cần
          |
          +--> Tạo SBOM/provenance nếu quy trình yêu cầu
          |
          v
Kiểm tra nội dung và metadata artifact
          |
          v
Tính checksum / ký artifact
          |
          v
Publish cùng version lên artifact repository
          |
          v
Ghi release metadata và lưu liên kết tới source commit
```

Thứ tự ký và tạo checksum cần tuân theo quy trình của repository/publisher. Nếu một bước làm thay đổi file sau khi checksum hoặc signature đã được tạo, phải tạo lại dữ liệu xác minh cho đúng nội dung cuối cùng.

Không phải project nào cũng cần mọi artifact. Thư viện public thường có lợi khi phát hành Sources JAR và Javadoc JAR; ứng dụng nội bộ có thể cần distribution ZIP/TAR; pipeline bảo mật có thể yêu cầu SBOM và chữ ký. Chọn artifact dựa trên cách consumer sử dụng sản phẩm.

## 21. Những điều cần ghi nhớ

- Artifact chính thường là JAR/WAR; artifact bổ trợ cung cấp source, API docs, test utilities, distribution hoặc thông tin xác minh.
- Classifier như `sources`, `javadoc`, `tests` phân biệt biến thể cùng GAV; nó không thay thế tọa độ chính.
- Sources JAR chứa mã nguồn của version đã phát hành, không chứa lịch sử Git và không thay thế source repository.
- Javadoc JAR chứa HTML được tạo từ Javadoc comments; nó giúp consumer hiểu API mà không cần đọc implementation.
- Maven Source Plugin và Maven Javadoc Plugin có thể attach artifact phụ để `install`/`deploy` phát hành cùng binary.
- Gradle Java plugin hỗ trợ `withSourcesJar()` và `withJavadocJar()`; publication cần lấy các variants từ Java component hoặc khai báo artifact rõ ràng.
- Test JAR/test fixtures phục vụ chia sẻ test code và không nên bị nhầm với API production.
- Distribution ZIP/TAR có thể chứa application, runtime libraries, launcher, cấu hình mẫu và tài liệu.
- SBOM, checksum và chữ ký phục vụ kiểm kê, xác minh và truy xuất nguồn gốc; chúng có vai trò khác nhau.
- Tạo tất cả artifact từ cùng commit/version, kiểm tra publication và giữ release artifact bất biến.

Khi chuẩn bị phát hành một thư viện Java, hãy xác định consumer cần binary, source, tài liệu API hay cả gói phân phối. Cấu hình build để tạo đúng artifact, gắn chúng vào cùng publication và publish từ một checkout/version duy nhất. Nhờ vậy, developer có thể debug bằng source tương ứng, tích hợp bằng Javadoc chính xác và hệ thống vận hành có đủ metadata để xác minh cũng như truy xuất nguồn gốc bản phát hành.
