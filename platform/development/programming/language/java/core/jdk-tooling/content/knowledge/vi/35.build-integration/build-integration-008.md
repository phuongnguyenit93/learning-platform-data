# Gradle Jar task: đóng gói ứng dụng Java thành JAR

## 1. Jar task là gì?

`Jar` là task của Gradle dùng để tạo một Java Archive (JAR) từ class đã biên dịch và các resource. JAR là một archive dựa trên ZIP, có cấu trúc thư mục và metadata theo quy ước của nền tảng Java.

Khi áp dụng Java Plugin hoặc Java Library Plugin, Gradle tự tạo task tên `jar`. Task này đóng gói output của source set `main`, thường gồm:

- Các file `.class` đã biên dịch từ `src/main/java`.
- Resource đã xử lý từ `src/main/resources`.
- File manifest `META-INF/MANIFEST.MF`.
- `module-info.class` hoặc metadata khác nếu dự án có cấu hình tương ứng.

`jar` tạo một artifact để chương trình Java khác sử dụng hoặc để phân phối. Task không tự đóng gói mọi thư viện trong `runtimeClasspath` vào archive. Đây là khác biệt quan trọng giữa JAR thông thường và fat/uber JAR.

## 2. Jar task nằm ở đâu trong build lifecycle?

Với Java Plugin, Gradle tạo các task chính sau:

| Task | Công việc |
|---|---|
| `compileJava` | Biên dịch source Java của source set main |
| `processResources` | Sao chép và xử lý resource của main |
| `classes` | Gom output của compile và process resources |
| `jar` | Đóng gói output main thành JAR |
| `assemble` | Tạo các artifact chính của dự án |
| `build` | Chạy các bước kiểm tra và đóng gói, gồm `check` và `assemble` |

`jar` được gắn vào lifecycle `assemble`. Vì vậy, chạy `gradle assemble` sẽ tạo JAR mặc định. Chạy `gradle build` cũng tạo JAR sau khi các bước cần thiết hoàn tất.

`src/test/java` và `src/test/resources` thuộc source set test. Chúng không được đưa vào JAR production mặc định. Test được biên dịch và chạy qua các task riêng như `compileTestJava` và `test`.

Luồng cơ bản:

```text
src/main/java       src/main/resources
       |                     |
  compileJava          processResources
       |                     |
       +--------- classes ---+
                    |
                   jar
                    |
             build/libs/*.jar
                    |
                 assemble
                    |
                  build
```

Task `jar` dùng output của source set nên Gradle biết các dependency task cần chạy. Khi tự tạo Jar task, nên dùng `sourceSets.main.output` thay vì tự ghép đường dẫn tới thư mục class bằng chuỗi; cách này giữ quan hệ task dependency chính xác.

## 3. Cấu trúc của một file JAR

Có thể liệt kê nội dung JAR bằng:

```bash
jar --list --file build/libs/my-app-1.0.jar
```

Ví dụ một JAR đơn giản:

```text
META-INF/
META-INF/MANIFEST.MF
com/
com/example/
com/example/Main.class
com/example/service/OrderService.class
application.properties
```

Các thành phần thường gặp:

- `META-INF/MANIFEST.MF`: metadata của archive, có thể khai báo entry point, phiên bản hoặc thông tin triển khai.
- `.class`: bytecode của Java class.
- Resource: file properties, JSON, XML, template, ảnh hoặc dữ liệu cần đọc lúc chạy.
- `META-INF/services/`: service provider configuration dùng với `ServiceLoader`.
- `module-info.class`: module descriptor khi dự án sử dụng Java Platform Module System.
- Các file chữ ký như `META-INF/*.SF`, `*.RSA` hoặc `*.DSA`: xuất hiện trong JAR đã ký.

Tên package của class được biểu diễn thành đường dẫn thư mục. Ví dụ `com.example.Main` nằm ở `com/example/Main.class`.

Resource trong `src/main/resources` được đưa vào archive theo đường dẫn tương đối của nó. Ví dụ `src/main/resources/config/app.properties` trở thành `config/app.properties`. Có thể đọc resource bằng `Class.getResourceAsStream` hoặc `ClassLoader.getResourceAsStream`.

## 4. Tạo dự án Java tối thiểu

Cấu trúc dự án tiêu chuẩn:

```text
jar-task-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── Main.java
        └── resources/
            └── app.properties
```

File `settings.gradle`:

```groovy
rootProject.name = 'jar-task-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.2.3'

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

`options.release = 17` yêu cầu compiler tạo bytecode và áp dụng API surface tương ứng Java 17. Trong dự án thật, có thể khai báo Java toolchain để cố định JDK dùng khi build; `options.release` và toolchain giải quyết hai việc liên quan nhưng khác nhau.

## 5. Chạy và tìm JAR mặc định

Các lệnh thường dùng:

```bash
gradle tasks --all
gradle clean
gradle jar
gradle assemble
gradle build
```

Sau khi chạy `gradle jar`, artifact mặc định thường nằm tại:

```text
build/libs/jar-task-demo-1.2.3.jar
```

Tên file mặc định ghép từ project name và project version. Thư mục đích mặc định của JAR là `build/libs`.

Kiểm tra file đã tạo:

```bash
jar --list --file build/libs/jar-task-demo-1.2.3.jar
```

Nếu build script không thay đổi, source và resource không thay đổi, Gradle có thể báo task `jar UP-TO-DATE`. Đây là hành vi incremental build bình thường.

## 6. Cấu hình Jar task

Dùng `tasks.named` để cấu hình task `jar` mà Java Plugin đã tạo:

```groovy
tasks.named('jar', Jar) {
    archiveBaseName = 'sample-app'

    manifest {
        attributes(
            'Main-Class': 'demo.Main',
            'Implementation-Title': 'Sample App',
            'Implementation-Version': project.version
        )
    }
}
```

Trong Kotlin DSL:

```kotlin
tasks.named<Jar>("jar") {
    archiveBaseName = "sample-app"

    manifest {
        attributes(
            mapOf(
                "Main-Class" to "demo.Main",
                "Implementation-Title" to "Sample App",
                "Implementation-Version" to project.version
            )
        )
    }
}
```

`tasks.named` cấu hình task đã tồn tại mà không cần tạo task mới. Khi cần tạo một archive khác, dùng `tasks.register<Jar>` trong Kotlin DSL hoặc `tasks.register('name', Jar)` trong Groovy DSL. Đây là cách cấu hình lazy, phù hợp với Gradle task configuration avoidance.

Không tạo thêm một task tên `jar` vì tên đó đã được Java Plugin sử dụng.

## 7. Các thuộc tính đặt tên và vị trí archive

`Jar` kế thừa các thuộc tính của `AbstractArchiveTask`. Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `archiveBaseName` | Phần tên chính của archive |
| `archiveAppendix` | Phần bổ sung sau base name |
| `archiveVersion` | Phần version |
| `archiveClassifier` | Nhãn phân biệt artifact như `sources`, `javadoc` hoặc `all` |
| `archiveExtension` | Phần mở rộng, mặc định là `jar` |
| `archiveFileName` | Tên file hoàn chỉnh |
| `destinationDirectory` | Thư mục chứa archive |
| `archiveFile` | Provider trỏ tới file kết quả, chỉ đọc |

Tên mặc định có dạng:

```text
[baseName]-[appendix]-[version]-[classifier].[extension]
```

Các phần trống sẽ không tạo dấu gạch nối dư. Với Java Plugin, `archiveBaseName` mặc định là project name, `archiveVersion` lấy từ `project.version` và `archiveClassifier` thường trống.

Ví dụ:

```groovy
tasks.named('jar', Jar) {
    archiveBaseName = 'orders'
    archiveVersion = '2.4.0'
    archiveClassifier = 'linux'
    destinationDirectory = layout.buildDirectory.dir('release')
}
```

Kết quả:

```text
build/release/orders-2.4.0-linux.jar
```

Nếu muốn đặt tên cố định, có thể gán `archiveFileName`:

```groovy
tasks.named('jar', Jar) {
    archiveFileName = 'application.jar'
}
```

Đặt `archiveFileName` sẽ ghi đè cách ghép tên từ base name, appendix, version, classifier và extension. Hãy tránh để nhiều task ghi cùng một đường dẫn output. Khi tạo nhiều biến thể archive, dùng classifier khác nhau.

Có thể đọc đường dẫn output thông qua Provider:

```groovy
def jarFile = tasks.named('jar', Jar).flatMap { it.archiveFile }
```

Không gán trực tiếp vào `archiveFile` vì đây là output provider chỉ đọc; hãy cấu hình các thuộc tính tên và thư mục.

## 8. Thêm Main-Class và các manifest attributes

Manifest nằm trong `META-INF/MANIFEST.MF`. Muốn chạy JAR bằng `java -jar`, cần khai báo entry point:

```groovy
tasks.named('jar', Jar) {
    manifest {
        attributes(
            'Main-Class': 'demo.Main',
            'Implementation-Title': 'Order Service',
            'Implementation-Version': project.version,
            'Automatic-Module-Name': 'com.example.orders'
        )
    }
}
```

`Main-Class` là tên class đầy đủ gồm package, không có đuôi `.class`. Class đó phải có method `public static void main(String[] args)` và phải nằm trong JAR hoặc classpath có thể truy cập.

Một manifest minh họa:

```text
Manifest-Version: 1.0
Main-Class: demo.Main
Implementation-Title: Order Service
Implementation-Version: 2.4.0
```

`Implementation-Title` và `Implementation-Version` là metadata mô tả artifact. `Automatic-Module-Name` cung cấp tên module ổn định cho JAR chưa có module descriptor tường minh; nếu có `module-info.class` thì module descriptor quyết định tên module.

Manifest cũng có thuộc tính `Class-Path`. Giá trị này là danh sách URL tương đối tới các JAR khác theo quy ước manifest. Nó không tự động được tạo từ Gradle `implementation` và cũng không có nghĩa các dependency đã được nhúng vào JAR.

Không ghi password, token, private key hoặc thông tin bí mật vào manifest. Nội dung manifest được phân phối cùng artifact và người nhận có thể đọc được.

## 9. Tùy chỉnh nội dung JAR bằng from, include, exclude và into

`Jar` là archive task dựa trên cơ chế CopySpec. Có thể thêm nhiều nguồn file:

```groovy
tasks.named('jar', Jar) {
    from(sourceSets.main.output)

    from('src/main/extra') {
        into 'extra'
    }
}
```

Một số thao tác thường dùng:

- `from`: thêm file hoặc directory vào archive.
- `into`: thay đổi thư mục đích bên trong archive.
- `include`: chỉ lấy file khớp pattern.
- `exclude`: loại file khớp pattern.
- `rename`: đổi tên file khi copy.
- `filesMatching`: cấu hình riêng các file theo pattern.
- `eachFile`: thay đổi đường dẫn hoặc thuộc tính của từng file.

Ví dụ chỉ đưa một nhóm file vào archive:

```groovy
tasks.named('jar', Jar) {
    from(sourceSets.main.output)

    include 'demo/**'
    exclude 'demo/internal/**'
    exclude '**/*.bak'
}
```

Ví dụ đổi vị trí một resource:

```groovy
tasks.named('jar', Jar) {
    from('src/main/resources') {
        into 'config'
        include '**/*.properties'
    }
}
```

Nếu file ban đầu ở `src/main/resources/app.properties`, ví dụ trên đưa nó vào `config/app.properties`. Cần kiểm tra đường dẫn resource mà code đang sử dụng sau khi thay đổi cấu trúc archive.

`include` và `exclude` dùng pattern theo quy tắc Ant-style. Pattern áp dụng lên đường dẫn tương đối trong CopySpec, vì vậy hãy kiểm tra nội dung archive sau khi cấu hình thay vì chỉ nhìn tên file nguồn.

## 10. Tạo Jar task riêng

Có thể tạo thêm archive cho một phần output:

```groovy
tasks.register('demoJar', Jar) {
    archiveClassifier = 'demo'

    from sourceSets.main.output

    include 'demo/**'
    exclude 'demo/internal/**'
}
```

Task này dùng lại output của source set main, nhưng tạo artifact riêng với classifier `demo`. Vì dùng `sourceSets.main.output`, Gradle biết cần build output tương ứng trước khi đóng gói.

Nếu chỉ muốn đóng gói một thư mục file độc lập:

```groovy
tasks.register('configJar', Jar) {
    archiveClassifier = 'config'
    from('src/main/config')
    include '**/*'
}
```

Nếu một task tự lấy file từ thư mục build bằng đường dẫn chuỗi như `build/classes/java/main`, hãy khai báo dependency phù hợp lên task tạo ra thư mục đó. Ưu tiên dùng output Provider hoặc source set để Gradle quản lý quan hệ này.

## 11. Tạo Sources JAR và Javadoc JAR

Java Plugin hỗ trợ thêm hai artifact thường dùng khi phát hành thư viện:

```groovy
java {
    withSourcesJar()
    withJavadocJar()
}
```

Gradle tạo các task `sourcesJar` và `javadocJar`. Chúng đóng gói source production và Javadoc tương ứng. Ví dụ:

```text
build/libs/library-1.0-sources.jar
build/libs/library-1.0-javadoc.jar
build/libs/library-1.0.jar
```

Sources JAR hữu ích để IDE hiển thị source khi người dùng mở dependency. Javadoc JAR chứa tài liệu API được sinh ra từ source và Javadoc comments.

Không nên tự tạo task thứ hai trùng tên `sourcesJar` hoặc `javadocJar` khi đã bật các tùy chọn trên. Nếu cần archive source tùy chỉnh, đặt tên task và classifier riêng.

## 12. Xử lý duplicate entries

Duplicate entry xảy ra khi nhiều nguồn cùng đưa một đường dẫn vào archive. Ví dụ hai dependency cùng chứa `META-INF/services/com.example.Plugin` hoặc một resource trùng tên.

`duplicatesStrategy` quyết định cách xử lý:

| Strategy | Hành vi |
|---|---|
| `INHERIT` | Kế thừa chiến lược từ CopySpec cha |
| `INCLUDE` | Giữ các bản trùng |
| `EXCLUDE` | Bỏ qua các bản trùng tiếp theo |
| `WARN` | Ghi cảnh báo và tiếp tục |
| `FAIL` | Dừng build khi gặp duplicate |

Với Java Plugin, mặc định của `Jar` là `DuplicatesStrategy.INHERIT`. Khi tạo fat JAR, hãy chọn chiến lược có chủ đích:

```groovy
tasks.named('fatJar', Jar) {
    duplicatesStrategy = DuplicatesStrategy.EXCLUDE
}
```

`EXCLUDE` có thể giúp build tiếp tục, nhưng cũng có thể âm thầm bỏ một service provider hoặc resource cần thiết. Với library hoặc plugin sử dụng `ServiceLoader`, cần hợp nhất nội dung `META-INF/services` theo đúng định dạng thay vì tùy tiện loại bản trùng.

`FAIL` phù hợp khi muốn phát hiện xung đột sớm. Sau đó, xử lý từng resource trùng bằng cách loại đúng file, đổi đường dẫn hoặc hợp nhất nội dung. Không dùng `EXCLUDE` như cách che mọi xung đột.

## 13. JAR thông thường và fat/uber JAR

JAR thông thường của Java Plugin chứa output của dự án: class và resource production. Dependency khai báo bằng `implementation` hoặc `runtimeOnly` không tự động được nhúng vào file đó.

Ví dụ ứng dụng phụ thuộc vào thư viện ngoài:

```groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
```

`build/libs/app.jar` có thể chứa class của dự án, nhưng không tự chứa class của Commons Lang. Khi chạy bằng `java -jar`, cần có dependency trên runtime classpath hoặc dùng cách đóng gói ứng dụng phù hợp.

**Fat JAR** (còn gọi là uber JAR) giải nén nội dung dependency JAR và đưa vào cùng archive. Ví dụ:

```groovy
tasks.register('fatJar', Jar) {
    archiveClassifier = 'all'
    duplicatesStrategy = DuplicatesStrategy.EXCLUDE

    manifest {
        attributes('Main-Class': 'demo.Main')
    }

    from sourceSets.main.output

    dependsOn configurations.runtimeClasspath
    from {
        configurations.runtimeClasspath
            .findAll { it.name.endsWith('.jar') }
            .collect { zipTree(it) }
    }
}
```

Đoạn này lấy output của ứng dụng và nội dung các JAR trong runtime classpath. Nó là mẫu tối giản; dự án thật cần xử lý duplicate resources, service descriptors, module metadata và chữ ký của dependency.

Khi gộp dependency đã ký vào archive mới, các chữ ký cũ không còn hợp lệ cho nội dung mới. Cần loại signature metadata cũ và ký lại artifact cuối nếu quy trình phát hành yêu cầu. Với service loader, dùng plugin đóng gói hỗ trợ merge service files, chẳng hạn Shadow Plugin, hoặc cấu hình hợp nhất tương đương.

Fat JAR cũng có thể gây xung đột class nếu nhiều thư viện chứa cùng package/class. Khi cần relocate package, xử lý service resource và loại dependency không dùng, nên sử dụng công cụ chuyên dụng và kiểm thử artifact đầu ra.

## 14. Khi nào nên dùng Application Plugin thay vì fat JAR?

Nếu mục tiêu là phân phối một ứng dụng Java cùng các thư viện runtime, Gradle Application Plugin thường là lựa chọn rõ ràng hơn.

```groovy
plugins {
    id 'application'
}

application {
    mainClass = 'demo.Main'
}
```

Plugin tạo distribution chứa JAR của ứng dụng, dependency JAR và script khởi chạy cho Unix-like systems và Windows. Task `run` cho phép chạy ứng dụng từ build; `installDist` tạo thư mục cài đặt; `distZip` và `distTar` tạo archive phân phối.

Cách này giữ dependency thành các JAR riêng trong thư mục `lib` và script sẽ cấu hình classpath. Người vận hành có thể thay thế hoặc kiểm tra thư viện riêng lẻ dễ hơn so với một fat JAR lớn.

Chọn cách đóng gói theo nhu cầu:

- Library: JAR thông thường và metadata dependency để project khác sử dụng.
- CLI application: Application Plugin để có script và thư viện runtime.
- Fat JAR: khi môi trường triển khai yêu cầu một archive duy nhất và đã giải quyết duplicate/signature/service metadata.
- Web application dạng Servlet: cân nhắc WAR Plugin; task `war` tạo cấu trúc web archive với `WEB-INF/classes` và `WEB-INF/lib`.

## 15. Tạo archive có thể tái lập

Build reproducible tạo archive byte-for-byte giống nhau khi input và điều kiện build tương ứng giống nhau. Điều này hữu ích cho CI, kiểm toán artifact và kiểm tra nguồn gốc binary.

Từ Gradle 9.0, các archive task mặc định có:

- `preserveFileTimestamps = false`: không giữ timestamp file nguồn trong entry archive.
- `reproducibleFileOrder = true`: sắp xếp file theo thứ tự ổn định khi đóng gói.

Có thể cấu hình rõ ràng nếu build cần hỗ trợ Gradle cũ:

```groovy
tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
```

Đây là điều kiện giúp archive ổn định, nhưng không bảo đảm toàn bộ build luôn giống nhau. Các yếu tố khác vẫn có thể làm output khác:

- JDK/compiler version thay đổi dẫn tới bytecode khác.
- Build script chèn timestamp, hostname hoặc đường dẫn máy local.
- Nội dung generated resource phụ thuộc môi trường.
- Dependency không được khóa phiên bản hoặc repository trả artifact khác.
- Manifest chứa build number hoặc metadata thay đổi theo từng lần build.

Muốn build có thể tái lập, hãy pin toolchain, khóa dependency khi phù hợp, tránh metadata không ổn định và so sánh hash của artifact. Không bật `preserveFileTimestamps = true` chỉ để lưu thời điểm file nguồn; timestamp build nên được ghi vào hệ thống build metadata nếu thật sự cần.

## 16. Incremental build, cache và output Provider

`Jar` là task có input/output được Gradle quản lý. Nếu class, resource và cấu hình task không thay đổi, Gradle có thể bỏ qua task do output vẫn hợp lệ.

- `UP-TO-DATE`: output hiện tại phù hợp với input đã ghi nhận.
- `FROM-CACHE`: output được khôi phục từ build cache.
- `NO-SOURCE`: không có source input phù hợp.
- `EXECUTED`: task thực sự chạy trong build hiện tại.

Khi viết task phụ thuộc vào JAR, dùng Provider thay vì tự ghép chuỗi đường dẫn:

```groovy
tasks.register('copyAppJar', Copy) {
    from(tasks.named('jar', Jar).flatMap { it.archiveFile })
    into(layout.buildDirectory.dir('copied'))
}
```

Cách này cho Gradle biết output file được tạo bởi task nào và duy trì quan hệ dependency. Tránh gọi `jar.archiveFile.get().asFile` quá sớm trong configuration phase hoặc dùng `doLast` để tự tạo JAR bằng lệnh shell; làm vậy có thể khiến Gradle khó theo dõi input/output và giảm hiệu quả incremental build.

## 17. Phát hành JAR qua Maven Publish

Với library, nên publish component Java để Gradle sinh metadata artifact và dependency phù hợp.

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example'
version = '1.0.0'

java {
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
```

`from components.java` xuất bản component Java cùng artifact và metadata liên quan. Sources JAR và Javadoc JAR được thêm khi đã bật các tùy chọn tương ứng.

Khi tạo thêm classifier tùy chỉnh, khai báo artifact đó trong publication nếu người dùng cần tải qua Maven repository. Chỉ tạo file trong `build/libs` chưa có nghĩa artifact tự động được publish.

Dùng `archiveClassifier` cho biến thể như `sources`, `javadoc` hoặc `all` để tên artifact được phân biệt rõ trong repository. Không đổi classifier của artifact chính một cách tùy tiện vì có thể làm hỏng quy ước dependency của consumer.

## 18. Module JAR, multi-release JAR và chữ ký

### Module JAR

Nếu dự án có `module-info.java` và biên dịch ra `module-info.class` ở root của JAR, archive là explicit modular JAR. Kiểm tra module descriptor:

```bash
jar --describe-module --file build/libs/app.jar
```

Nếu không có module descriptor, JAR trên module path có thể được coi là automatic module theo quy tắc đặt tên. `Automatic-Module-Name` trong manifest có thể cung cấp tên ổn định cho JAR chưa có `module-info.class`.

### Multi-release JAR

Multi-release JAR có thể chứa implementation khác nhau theo phiên bản Java, đặt trong các thư mục như `META-INF/versions/9/`. Manifest phải có thuộc tính:

```text
Multi-Release: true
```

Chỉ thêm file vào `META-INF/versions/` mà không hiểu quy tắc multi-release có thể khiến JVM không chọn class như mong đợi. Dùng tùy chọn `--release` của công cụ `jar` hoặc cấu hình build chuyên biệt và kiểm tra archive bằng `jar --validate`.

### Chữ ký

JAR có thể được ký bằng `jarsigner` hoặc Gradle Signing Plugin. Nếu thay đổi nội dung archive sau khi ký, chữ ký sẽ không còn xác minh được. Hãy hoàn tất đóng gói, kiểm tra và chỉ ký artifact cuối cùng.

Kiểm tra chữ ký:

```bash
jarsigner -verify -verbose -certs build/libs/app.jar
```

## 19. Kiểm tra nội dung và khả năng chạy của JAR

Một quy trình kiểm tra cơ bản:

1. Kiểm tra task thành công và artifact tồn tại.
2. Liệt kê entry bằng `jar --list`.
3. Xem manifest bằng cách extract `META-INF/MANIFEST.MF`.
4. Kiểm tra class chính và resource bắt buộc có trong archive.
5. Chạy `java -jar` nếu JAR có `Main-Class`.
6. Nếu JAR là library, thử dùng nó từ consumer project.
7. Kiểm tra dependency metadata và classifier nếu chuẩn bị publish.
8. Với JAR modular, kiểm tra bằng `jar --describe-module`.
9. Với multi-release JAR, chạy `jar --validate`.
10. Với artifact có chữ ký, chạy `jarsigner -verify`.

Một số lệnh:

```bash
jar --list --file build/libs/app.jar
jar --extract --file build/libs/app.jar META-INF/MANIFEST.MF
java -jar build/libs/app.jar
javap -classpath build/libs/app.jar demo.Main
```

`java -jar` yêu cầu manifest có `Main-Class` và runtime classpath đáp ứng đầy đủ dependency. Một JAR hợp lệ về định dạng ZIP vẫn có thể không chạy được nếu thiếu class, resource hoặc dependency.

## 20. Ví dụ hoàn chỉnh: tạo executable JAR và custom JAR

Ví dụ này sử dụng Java 17 source release và Gradle Groovy DSL.

File `build.gradle`:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.2.3'

java {
    withSourcesJar()
    withJavadocJar()
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

tasks.named('jar', Jar) {
    archiveBaseName = 'sample-app'

    manifest {
        attributes(
            'Main-Class': 'demo.Main',
            'Implementation-Title': 'Sample App',
            'Implementation-Version': project.version
        )
    }
}

tasks.register('demoJar', Jar) {
    archiveClassifier = 'demo'
    from sourceSets.main.output
    include 'demo/**'
    exclude 'demo/internal/**'
}
```

File `src/main/java/demo/Main.java`:

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public class Main {
    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        try (InputStream input =
                Main.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                        "app.properties is missing from the JAR");
            }
            properties.load(input);
        }

        System.out.println(
                "Jar task demo: " + properties.getProperty("message"));
    }
}
```

File `src/main/resources/app.properties`:

```properties
message=hello
```

Có thể thêm một class nội bộ để thấy tác dụng của exclude:

File `src/main/java/demo/internal/Secret.java`:

```java
package demo.internal;

public class Secret {
}
```

Build các archive:

```bash
gradle clean jar demoJar sourcesJar javadocJar
```

Các artifact được tạo:

```text
build/libs/sample-app-1.2.3.jar
build/libs/jar-task-demo-1.2.3-demo.jar
build/libs/jar-task-demo-1.2.3-sources.jar
build/libs/jar-task-demo-1.2.3-javadoc.jar
```

Kiểm tra nội dung và chạy:

```bash
jar --list --file build/libs/sample-app-1.2.3.jar
java -jar build/libs/sample-app-1.2.3.jar
```

Stdout chính xác:

```text
Jar task demo: hello
```

JAR chính có `demo/Main.class`, `demo/internal/Secret.class` và `app.properties`. Custom `demoJar` chỉ chứa đường dẫn khớp `demo/**` sau khi áp dụng exclude; `demo/internal/Secret.class` không xuất hiện trong archive này.

Manifest của JAR chính:

```text
Manifest-Version: 1.0
Main-Class: demo.Main
Implementation-Title: Sample App
Implementation-Version: 1.2.3
```

Ví dụ đã được build bằng Gradle 9.2.1 trên OpenJDK Zulu 24.0.2; Java source được compile với `--release 17`. Các task `jar`, `demoJar`, `sourcesJar` và `javadocJar` đều hoàn tất. `java -jar` in đúng `Jar task demo: hello`.

## 21. Lỗi thường gặp khi làm việc với Jar task

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không thấy task `jar` | Chưa áp dụng Java Plugin hoặc JVM plugin phù hợp | Thêm `plugins { id 'java' }` |
| Không có JAR sau build | Task chưa chạy hoặc source set không có output | Chạy `gradle jar --info` và xem task graph |
| JAR thiếu resource | Resource đặt sai source directory hoặc include/exclude loại mất file | Đặt file trong `src/main/resources` và kiểm tra `jar tf` |
| `no main manifest attribute` | Manifest thiếu `Main-Class` | Thêm `manifest { attributes('Main-Class': '...') }` |
| `Could not find or load main class` | Sai tên package/class hoặc class không nằm trong archive | Kiểm tra manifest và đường dẫn class trong JAR |
| `NoClassDefFoundError` | JAR thường không chứa runtime dependency | Dùng runtime classpath, Application Plugin hoặc fat JAR |
| `File already exists` hoặc duplicate path | Nhiều nguồn đưa cùng entry vào archive | Xác định nguồn trùng và cấu hình duplicates strategy phù hợp |
| Resource không đọc được khi chạy | Code dùng sai đường dẫn hoặc file không được đóng gói | Dùng classpath resource và xác minh entry trong JAR |
| Archive bị trùng tên | Nhiều task dùng chung destination và filename | Gán classifier hoặc archiveFileName riêng |
| JAR khác hash giữa các lần build | Timestamp, thứ tự entry hoặc input build không ổn định | Dùng reproducible defaults, pin toolchain và loại metadata thay đổi |
| Chữ ký không hợp lệ | Nội dung JAR bị thay đổi sau khi ký hoặc fat JAR giữ signature cũ | Đóng gói xong mới ký; loại chữ ký cũ khi merge dependency |
| ServiceLoader không tìm thấy provider | Service descriptor bị loại do duplicate strategy | Hợp nhất `META-INF/services` thay vì bỏ file trùng |
| Task không chạy lại | Gradle đánh giá input/output vẫn up-to-date | Kiểm tra task inputs, outputs và build script thay đổi |
| Module không resolve | Module descriptor hoặc module path không đúng | Kiểm tra `module-info.class` và `jar --describe-module` |

## 22. Quy trình thực hành khi cần thay đổi JAR

Khi một yêu cầu thay đổi packaging xuất hiện, có thể làm theo thứ tự:

1. Xác định artifact cần tạo là library JAR, executable JAR, fat JAR hay distribution.
2. Kiểm tra plugin và task hiện có: `gradle tasks --all`.
3. Xác định source set/output cần đóng gói.
4. Chọn tên file, version, classifier và destination.
5. Cấu hình manifest nếu cần entry point hoặc metadata.
6. Thêm hoặc loại resource bằng CopySpec.
7. Kiểm tra duplicate entries và dependency packaging.
8. Giữ archive reproducible và task inputs/outputs rõ ràng.
9. Build artifact từ task phù hợp.
10. Liệt kê nội dung, kiểm tra manifest và chạy thử trong môi trường gần với môi trường triển khai.
11. Nếu publish, kiểm tra classifier, dependency metadata và chữ ký.

Đừng dùng một JAR duy nhất cho mọi nhu cầu nếu cấu trúc artifact khác nhau. Một library JAR nên giữ dependency metadata để consumer giải quyết dependency; một CLI app có thể cần distribution; một fat JAR cần chính sách rõ cho duplicate, service descriptor và chữ ký.

## 23. Tổng kết

Gradle `Jar` task đóng gói class và resource production thành một Java Archive. Java Plugin tạo sẵn task `jar` và nối nó vào `assemble`. Có thể tùy chỉnh manifest, tên artifact, classifier, destination, include/exclude và tạo thêm các Jar task riêng.

Những điểm cần nhớ:

- `jar` mặc định đóng gói output của source set main; test output không được đưa vào.
- `archiveBaseName`, `archiveVersion`, `archiveClassifier` và `destinationDirectory` quyết định tên/vị trí archive.
- `manifest` khai báo `Main-Class` để chạy bằng `java -jar`.
- JAR thông thường không tự nhúng runtime dependencies.
- `withSourcesJar()` và `withJavadocJar()` tạo artifact bổ sung cho library.
- Dùng `duplicatesStrategy` có chủ đích, đặc biệt khi tạo fat JAR.
- Gradle 9 trở lên mặc định tạo archive có thứ tự entry ổn định và không giữ timestamp file nguồn.
- Dùng Application Plugin nếu cần phân phối app cùng dependency và script khởi chạy.
- Kiểm tra artifact bằng `jar --list`, manifest, `java -jar` và công cụ phù hợp với module/chữ ký.
- Cấu hình task qua Provider API để Gradle quản lý dependency, incremental build và cache.

**Tài liệu tham khảo chính thức:**

- [Gradle User Manual — Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle DSL — Jar](https://docs.gradle.org/current/dsl/org.gradle.jvm.tasks.Jar.html)
- [Gradle DSL — AbstractArchiveTask](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html)
- [Gradle User Manual — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html)
- [Gradle User Manual — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle User Manual — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Gradle User Manual — Reproducible Archives and Security Best Practices](https://docs.gradle.org/current/userguide/best_practices_security.html)
- [Oracle Java SE 24 — The jar Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html)
- [Oracle Java SE 24 — JAR File Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html)
