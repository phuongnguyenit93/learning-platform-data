# Cấu hình tác vụ bằng `tasks.named` và Provider API trong Gradle với Spring Boot

Trong một ứng dụng Spring Boot dùng Gradle, bạn thường muốn đổi tên executable JAR, chỉnh cách chạy `bootRun`, cấu hình test hoặc nối output của một task tự tạo vào input của task khác. Hai API quan trọng giải quyết vấn đề này:

- **`tasks.named(...)`** tìm và cấu hình **task đã được đăng ký** theo cách trì hoãn, trả về `TaskProvider`. Nó không tạo task mới và không chạy task.
- **Provider API** biểu diễn một **giá trị có thể được tính hoặc cung cấp sau**, ví dụ project property, file trong build directory hoặc output của task khác. Các `Provider<T>` và `Property<T>` giúp nối dữ liệu mà chưa cần đọc giá trị ngay.

Kết hợp đúng hai API giúp Gradle tránh tạo/configure task không liên quan, giữ thông tin phụ thuộc giữa các task, theo dõi inputs/outputs và hỗ trợ build có thể tái lập. Đây là cách viết hiện đại để tùy chỉnh các task Spring Boot như `bootJar` và `bootRun`.

## 1. Phân biệt đăng ký, cấu hình và chạy task

Gradle tổ chức build thành initialization, configuration và execution. Trong **configuration phase**, Gradle đọc cấu hình, áp dụng plugins, đăng ký các task và xây task graph. Trong **execution phase**, Gradle chạy các task được chọn cùng dependencies của chúng.

Không phải mọi task đã đăng ký đều cần được tạo ngay. Task Configuration Avoidance API giúp tránh hiện thực hóa (*realize*) các task không phục vụ lệnh build hiện tại.

| Thao tác | Ý nghĩa | Tác dụng ngay |
| --- | --- | --- |
| `tasks.register('report')` | Đăng ký task mới, trả `TaskProvider` | Chưa chạy; không nhất thiết tạo object Task |
| `tasks.named('bootJar')` | Lấy provider của task đã đăng ký | Chưa chạy; không buộc realize |
| `tasks.named('bootJar') { ... }` | Đăng ký logic cấu hình task | Cấu hình có thể được trì hoãn |
| `tasks.getByName('bootJar')` | Lấy đối tượng task trực tiếp | Có thể realize task sớm |
| `taskProvider.get()` | Lấy đối tượng task từ provider | Có thể realize task sớm |
| `./gradlew bootJar` | Yêu cầu thực thi task | Chạy task và những task phụ thuộc, trừ khi bị skip/up-to-date |

Ví dụ:

~~~bash
./gradlew bootJar
~~~

Lệnh này thường làm Gradle chạy biên dịch, xử lý resources và đóng gói executable JAR. Ngược lại, câu lệnh trong build script:

~~~groovy
tasks.named('bootJar') {
    archiveFileName.set('service.jar')
}
~~~

chỉ mô tả **cách cấu hình** task khi cần; nó không tự kích hoạt `bootJar` và không sinh file ngay.

**Điểm dễ nhầm:** cấu hình lazy không có nghĩa mọi property chỉ được đọc lúc execution. Khi task bị realize, configuration action của `named` có thể chạy trong configuration phase; nếu code gọi `get()` ở đó, giá trị provider sẽ được truy vấn sớm.

## 2. Chọn `register`, `named` hay `configureEach`

### Tạo task mới: `tasks.register`

~~~groovy
def reportTask = tasks.register('printBuildStatus') {
    group = 'verification'
    description = 'In trạng thái của bản build.'
    doLast {
        logger.quiet('BUILD_STATUS=READY')
    }
}
~~~

Khi chạy:

~~~bash
./gradlew -q printBuildStatus
~~~

Dòng do task in ra:

~~~text
BUILD_STATUS=READY
~~~

Đây là task do dự án định nghĩa, khác với task `bootJar` do Spring Boot Gradle plugin đăng ký.

### Chỉnh task có sẵn: `tasks.named`

~~~groovy
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named('bootJar', BootJar) {
    archiveFileName.set('service.jar')
}
~~~

Cấu hình trên giả định project đã áp dụng `java` và `org.springframework.boot` plugins tương thích. `named` tìm task trong **project hiện tại**. Nếu `bootJar` chưa được đăng ký, Gradle có thể ném `UnknownTaskException`; `named` không phải lệnh tự tạo task.

Cách eager cần tránh khi không cần task object ngay:

~~~groovy
// Có thể realize task ngay khi cấu hình:
tasks.getByName('bootJar').archiveFileName.set('service.jar')
~~~

Cách phù hợp với configuration avoidance:

~~~groovy
tasks.named('bootJar') {
    archiveFileName.set('service.jar')
}
~~~

### Cấu hình nhiều task cùng loại: `configureEach`

~~~groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()
    testLogging {
        events 'failed', 'skipped'
    }
}
~~~

Đây là cú pháp Groovy DSL trong project có Java plugin và JUnit Platform khi muốn áp dụng chính sách cho mọi task `Test`. `configureEach` trì hoãn áp dụng logic tới khi từng task cần được configure, kể cả task loại đó được đăng ký sau.

Ngược lại, `tasks.withType(Test) { ... }` là dạng có thể cấu hình eager. Nếu chỉ muốn chỉnh một task biết tên, dùng `tasks.named('test', Test)`. Không cần cấu hình mọi task khi chỉ một task phải đổi.

### Truyền `TaskProvider` trực tiếp vào `dependsOn`

~~~groovy
def reportTask = tasks.register('printBuildStatus') {
    doLast { logger.quiet('BUILD_STATUS=READY') }
}

tasks.named('check') {
    dependsOn(reportTask)
}
~~~

Ví dụ độc lập này giả định Java plugin đã tạo `check`. Khi chạy `check`, task `printBuildStatus` thuộc task graph. Bạn không cần viết `dependsOn(reportTask.get())`. `dependsOn` yêu cầu task phụ thuộc phải chạy, trong khi `mustRunAfter` chỉ quy định thứ tự **nếu cả hai task đều được chọn**.

## 3. Provider API: nối dữ liệu trước khi có giá trị

Gradle phân biệt hai nhóm:

- **`Provider<T>`:** chỉ có thể truy vấn giá trị (chẳng hạn `get()`, `map`, `flatMap`, `orElse`); không tự đặt lại giá trị của nguồn.
- **`Property<T>`:** mở rộng Provider và cho phép cấu hình giá trị bằng `set` hoặc mặc định bằng `convention`.

Các kiểu thường gặp:

| Kiểu | Chứa gì? | Tình huống |
| --- | --- | --- |
| `Provider<String>` | Chuỗi được cung cấp khi cần | Tên artifact từ `-P` |
| `Property<String>` | Chuỗi có thể cấu hình | Input task, tên archive |
| `RegularFileProperty` | Đường dẫn file có thể cấu hình | `@InputFile`, `@OutputFile` |
| `DirectoryProperty` | Đường dẫn thư mục có thể cấu hình | Folder output |
| `ListProperty<T>`, `MapProperty<K,V>` | Collection có thể cấu hình | Danh sách hoặc map tham số |
| `TaskProvider<T>` | Tham chiếu lazy đến task | Giá trị trả về từ `register`/`named` |

### `providers.gradleProperty` thay vì tự resolve ngay

~~~groovy
def nameProvider = providers.gradleProperty('bootJarName')
    .orElse('service.jar')

tasks.named('bootJar') {
    archiveFileName.set(nameProvider)
}
~~~

Khi chạy `./gradlew bootJar`, file mặc định tên `service.jar`; khi chạy `./gradlew bootJar -PbootJarName=release.jar`, file tên `release.jar`. `orElse` cung cấp giá trị fallback nếu property không được đặt. `set(Provider)` nối property đích với provider nguồn, không cần lấy chuỗi ngay.

Tránh resolve quá sớm:

~~~groovy
// Không cần thiết trong trường hợp này:
def fileName = providers.gradleProperty('bootJarName')
    .orElse('service.jar')
    .get()

tasks.named('bootJar') {
    archiveFileName.set(fileName)
}
~~~

Code vẫn có thể chạy, nhưng mất khả năng trì hoãn phép truy vấn. Đặc biệt với provider liên quan đầu ra của một task khác, việc chuyển quá sớm thành `String` hoặc `File` có thể làm mất metadata về task producer.

### `set` và `convention` khác nhau

~~~groovy
tasks.named('bootJar') {
    archiveFileName.convention('fallback.jar')
    archiveFileName.set(
        providers.gradleProperty('bootJarName').orElse('release.jar')
    )
}
~~~

`convention(...)` đặt **giá trị mặc định**, chỉ có hiệu lực khi property chưa có giá trị tường minh. `set(...)` chỉ định **giá trị tường minh**, có thể là một Provider. Nếu một plugin đã cung cấp convention hợp lý, thông thường chỉ cần `set` khi muốn thay đổi. Đừng tùy tiện gọi `finalizeValue` hoặc `disallowChanges`, bởi plugin khác có thể còn cần cấu hình property trước khi Gradle khóa giá trị.

`get()` có thể báo lỗi nếu provider không có giá trị. Dùng `orElse` khi thiếu dữ liệu là trường hợp hợp lệ; với đầu vào bắt buộc, để Gradle báo lỗi rõ là hợp lý.

### `map` và `flatMap`

~~~groovy
def channel = providers.gradleProperty('channel').orElse('dev')
def jarName = channel.map { value -> 'service-' + value + '.jar' }

tasks.named('bootJar') {
    archiveFileName.set(jarName)
}
~~~

Với `-Pchannel=prod`, `jarName` đại diện chuỗi `service-prod.jar`. `map { T -> R }` tạo một provider mới từ phép biến đổi giá trị đơn lẻ; `flatMap { T -> Provider<R> }` dùng khi kết quả của phép biến đổi vốn đã là một provider. Dùng `flatMap` đặc biệt hữu ích để lấy **file output property của task** mà vẫn giữ quan hệ nguồn tạo file.

Các phép biến đổi trong provider nên thuần túy: không mở kết nối mạng, chỉnh dữ liệu ngoài hay ghi file bên trong `map`. Gradle có thể truy vấn provider vào những thời điểm khác nhau; tác dụng phụ nên nằm trong task action được mô hình hóa.

### Provider dành cho file và thư mục

~~~groovy
def markerFile = layout.buildDirectory.file(
    'generated/build-marker.txt'
)
~~~

`markerFile` là `Provider<RegularFile>` gắn với build layout, thay cho việc ghép đường dẫn thủ công như `new File(project.buildDir, '...')`. Đối với input/output task, ưu tiên `RegularFileProperty`, `DirectoryProperty` và nối provider tương ứng để Gradle theo dõi dependency/caching.

## 4. Spring Boot: cấu hình `bootJar` và `bootRun`

### `bootJar` — executable archive

~~~groovy
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named('bootJar', BootJar) {
    archiveFileName.set(
        providers.gradleProperty('bootJarName').orElse('service.jar')
    )
}
~~~

`bootJar` được Spring Boot Gradle plugin đăng ký khi Java plugin phù hợp được áp dụng. Task này đóng gói executable Spring Boot JAR, bao gồm class ứng dụng, launcher và dependencies cần chạy. `jar` của Java plugin tạo archive Java thông thường, có thể khác executable Boot JAR. Các task này là các công việc build khác nhau.

Có thể đổi classifier:

~~~groovy
tasks.named('bootJar') {
    archiveClassifier.set('exec')
}
~~~

Đây là **ví dụ riêng** khi cần đổi classifier. Nếu đồng thời đặt `archiveFileName` tường minh, tên file cụ thể đã ghi sẽ chi phối output name; đừng mặc định classifier sẽ tự nối vào tên do bạn đã cố định. Các tùy chọn archive phải được chọn thống nhất.

### `bootRun` — chạy ứng dụng bằng Gradle

~~~groovy
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named('bootRun', BootRun) {
    systemProperty 'demo.mode', 'training'
}
~~~

`BootRun` mở rộng `JavaExec`, nên có thể tùy chỉnh JVM/system properties và các đối số được truyền tới ứng dụng. `bootRun` dùng runtime classpath của project để chạy trong quá trình development. Cấu hình `systemProperty` ở đây chỉ áp dụng cho JVM được `bootRun` khởi động; không đưa giá trị vào artifact JAR.

Khi chạy bằng `java -jar` tại server, JVM/application arguments được cung cấp riêng. Chẳng hạn `java -Ddemo.mode=training -jar app.jar` là cách truyền JVM system property tương ứng. Không kỳ vọng các cấu hình chỉ dành cho `bootRun` tự đi theo JAR khi deploy.

### Các task không phải lúc nào cũng tồn tại

| Task | Điều kiện cơ bản | Vai trò |
| --- | --- | --- |
| `bootJar` | Spring Boot plugin + Java plugin | Executable Spring Boot JAR |
| `bootRun` | Spring Boot plugin + Java plugin | Chạy ứng dụng từ classpath |
| `jar` | Java plugin | Plain Java JAR |
| `bootWar` | Spring Boot plugin + `war` plugin | Executable WAR |
| `test` | Java plugin | Thực thi kiểm thử |

`tasks.named('bootWar')` sẽ không hoạt động nếu module không có task WAR. Trong multi-project build, cấu hình task phải đặt vào **đúng project** đang có task đó. Root project không tự có `bootJar` chỉ vì một subproject áp dụng Spring Boot plugin.

## 5. Ví dụ đầy đủ: chạy ứng dụng và tạo task custom có wiring

Ví dụ cố định **Spring Boot 3.3.5**, **Gradle 8.7** và **Java 17** cho mục đích thực hành, không khẳng định đây là các phiên bản mới nhất. Khi làm dự án mới, kiểm tra các phiên bản đang được hỗ trợ và tương thích. Dùng Groovy DSL trong `build.gradle`.

Cấu trúc dự án:

~~~text
provider-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/demo/DemoApplication.java
~~~

### File `settings.gradle`

~~~groovy
rootProject.name = 'provider-demo'
~~~

### File `build.gradle` hoàn chỉnh

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.springframework.boot.gradle.tasks.bundling.BootJar
import org.springframework.boot.gradle.tasks.run.BootRun

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}

// Tùy chỉnh task đã được Spring Boot plugin đăng ký.
def chosenJarName = providers.gradleProperty('bootJarName')
    .orElse('provider-demo.jar')

tasks.named('bootJar', BootJar) {
    archiveFileName.set(chosenJarName)
}

tasks.named('bootRun', BootRun) {
    systemProperty 'demo.mode', 'training'
}

// Định nghĩa custom task có input/output đúng kiểu.
abstract class WriteBuildMarker extends DefaultTask {
    @Input
    abstract Property<String> getMessage()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        File target = outputFile.get().asFile
        target.parentFile.mkdirs()
        target.setText(message.get() + '\n', 'UTF-8')
    }
}

abstract class PrintBuildMarker extends DefaultTask {
    @InputFile
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract RegularFileProperty getSourceFile()

    @TaskAction
    void show() {
        String value = sourceFile.get().asFile.getText('UTF-8').trim()
        logger.quiet('MARKER=' + value)
    }
}

// tasks.register trả TaskProvider, không yêu cầu tạo task ngay.
def markerTask = tasks.register('writeBuildMarker', WriteBuildMarker) {
    message.convention(
        providers.gradleProperty('buildMessage').orElse('READY')
    )
    outputFile.convention(
        layout.buildDirectory.file('generated/build-marker.txt')
    )
}

// flatMap nối output của producer với input consumer.
tasks.register('printBuildMarker', PrintBuildMarker) {
    sourceFile.set(markerTask.flatMap { task -> task.outputFile })
}
~~~

**Vai trò từng phần:**

1. Java/Spring Boot plugins cung cấp `compileJava`, `bootJar`, `bootRun`, v.v. `tasks.named` chỉ cấu hình các task sẵn có.
2. `chosenJarName` là `Provider<String>` từ project property, có fallback. `archiveFileName.set(chosenJarName)` giữ kết nối lazy đến nguồn giá trị.
3. `bootRun` gán `demo.mode=training` cho tiến trình development mà Gradle khởi chạy.
4. `WriteBuildMarker` có `@Input Property<String>` và `@OutputFile RegularFileProperty`. Các annotation giúp Gradle nhận diện đầu vào/đầu ra để thực hiện up-to-date checks.
5. `PrintBuildMarker` nhận `@InputFile` với `@PathSensitive(PathSensitivity.RELATIVE)`; nó chỉ có nhiệm vụ đọc file và log thông điệp.
6. `markerTask.flatMap { task -> task.outputFile }` kết nối provider output của task sản xuất với property input của task tiêu thụ. Gradle giữ metadata nguồn tạo file và có thể tự suy ra thứ tự thực thi, không cần `dependsOn` riêng.
7. `get()` trong `@TaskAction` phù hợp vì lúc task thực thi cần sử dụng giá trị/file thực tế. Không truy vấn file output quá sớm ở lúc cấu hình build.

### File `src/main/java/com/example/demo/DemoApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner showMode() {
        return args -> System.out.println(
                "BOOT_MODE=" + System.getProperty("demo.mode", "none")
        );
    }
}
~~~

Đây là chương trình Java 17+ với package và tên file chính xác. `spring-boot-starter` không khởi động web server; khi ứng dụng khởi động thành công, `CommandLineRunner` in giá trị system property rồi chương trình kết thúc.

### Các lệnh và kết quả có thể kiểm tra

Các lệnh Gradle sau đây giả định project **đã có Gradle Wrapper**. Trên Linux/macOS:

~~~bash
./gradlew -q printBuildMarker
~~~

Dòng do `PrintBuildMarker` in:

~~~text
MARKER=READY
~~~

File `build/generated/build-marker.txt` chứa `READY` và một ký tự xuống dòng. Gradle chạy producer `writeBuildMarker` trước consumer `printBuildMarker` nhờ kết nối input/output provider.

Thay input bằng CLI project property:

~~~bash
./gradlew -q printBuildMarker -PbuildMessage=CI
~~~

Dòng do task in:

~~~text
MARKER=CI
~~~

Bởi `message` là `@Input`, Gradle có thể nhận biết thay đổi từ `READY` sang `CI` để quyết định thực thi lại task tạo file. Nếu đầu vào và output không thay đổi, producer có thể báo `UP-TO-DATE` và không ghi file thêm lần nữa.

Tạo executable Boot JAR:

~~~bash
./gradlew -q bootJar
~~~

Tên file từ `chosenJarName` mặc định là `build/libs/provider-demo.jar`. Đổi tên mà không sửa script:

~~~bash
./gradlew -q bootJar -PbootJarName=release.jar
~~~

Artifact được cấu hình thành `build/libs/release.jar`. File từ lần build cũ có thể vẫn còn trong output directory; khi kiểm tra nên chú ý artifact thuộc lượt build hiện tại.

Chạy ứng dụng bằng Gradle:

~~~bash
./gradlew bootRun --args='--spring.main.banner-mode=off --logging.level.root=OFF'
~~~

Dòng **do ứng dụng** in ra (log Gradle/Boot khác có thể thay đổi):

~~~text
BOOT_MODE=training
~~~

Chạy artifact trực tiếp bằng JVM, sau khi tạo `provider-demo.jar`:

~~~bash
java -jar build/libs/provider-demo.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Dòng ứng dụng in ra:

~~~text
BOOT_MODE=none
~~~

Truyền cùng system property cho runtime trực tiếp:

~~~bash
java -Ddemo.mode=training -jar build/libs/provider-demo.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Dòng ứng dụng in:

~~~text
BOOT_MODE=training
~~~

Lưu ý `-Ddemo.mode=training` phải nằm **trước `-jar`** để JVM hiểu đó là system property; tham số Spring Boot ứng dụng được đặt sau tên file JAR. Thí nghiệm này cho thấy `bootRun` là một **task development**, còn `java -jar` chạy artifact với cấu hình runtime độc lập.

Nếu chưa có wrapper nhưng máy có Gradle tương thích, tại thư mục project có thể tạo wrapper bằng `gradle wrapper --gradle-version 8.7`; sau đó dùng `./gradlew`. Trên Windows PowerShell, dùng `.\gradlew.bat` và điều chỉnh cách quote đối số cho shell tương ứng.

## 6. Wiring output-input bằng `flatMap` thay vì chỉ nối chuỗi đường dẫn

Đây là mối liên hệ chính trong ví dụ:

~~~text
tasks.register('writeBuildMarker')
         |
         v
TaskProvider<WriteBuildMarker>
         |
         | flatMap { it.outputFile }
         v
Provider<RegularFile> (output có metadata producer)
         |
         | sourceFile.set(...)
         v
tasks.register('printBuildMarker') — @InputFile
         |
         v
Gradle suy ra: cần chạy writeBuildMarker trước printBuildMarker
~~~

Cách dễ gây lỗi:

~~~groovy
// Biết đường dẫn file, nhưng không nói ai tạo ra file.
tasks.register('printBuildMarker', PrintBuildMarker) {
    sourceFile.set(
        layout.buildDirectory.file('generated/build-marker.txt')
    )
}
~~~

Đoạn này chỉ biết **file ở đâu**, không thể hiện **task nào tạo file**. Nếu gọi consumer khi file chưa có và không có dependency theo cách khác, Gradle có thể báo thiếu input file. Có thể thêm `dependsOn(markerTask)` tường minh, nhưng nếu file output là dữ liệu chính giữa hai task thì nối `TaskProvider.flatMap { it.outputFile }` giúp quan hệ dữ liệu và task graph nhất quán với nhau.

Đừng dùng:

~~~groovy
// Có thể realize producer sớm, đồng thời chỉ lấy File thuần.
def file = markerTask.get().outputFile.get().asFile
~~~

rồi lấy file đó để cấu hình consumer. Cách này có thể làm mất metadata task dependency và buộc đọc output chưa cần thiết. Hãy truyền Provider trực tiếp vào `RegularFileProperty`.

### Khi nào cần `dependsOn`?

- Dùng `dependsOn(otherTaskProvider)` nếu task phải hoàn tất trước một task khác theo **quy trình**, dù không có output/input property để nối.
- Dùng property output của producer gắn vào input của consumer nếu quan hệ là **dòng dữ liệu**.
- Dùng `mustRunAfter` để ràng buộc thứ tự **khi cả hai đã nằm trong graph**; nó không buộc task kia tham gia.
- Dùng `finalizedBy` cho task kết thúc theo ngữ nghĩa Gradle, không thay cho dependency dữ liệu.

Không có nguyên tắc rằng mọi dependency giữa task đều phải viết bằng `flatMap`. Chọn API phản ánh lý do phụ thuộc thực tế.

## 7. Hiểu chính xác khi nào provider được tính

Provider API **trì hoãn phép tính tới lúc giá trị bị truy vấn**, không cam kết mọi provider chỉ được tính ở execution phase. Trong trường hợp:

~~~groovy
def outputName = providers.gradleProperty('bootJarName')
    .orElse('service.jar')

tasks.named('bootJar') {
    archiveFileName.set(outputName)
}
~~~

Gradle có thể giữ provider cho tới khi tên file thực sự cần để thiết lập task output. Nhưng nếu bạn viết `outputName.get()` trong configuration action, giá trị bị truy vấn khi action đó chạy (thường trước execution).

Tương tự, `tasks.named('bootJar')` không làm Gradle tạo task object lúc lookup; nhưng nếu một đoạn code khác gọi `tasks.named('bootJar').get()`, nó vẫn có thể bị realize sớm. Configuration avoidance chỉ hiệu quả khi **toàn chuỗi build logic** tránh API eager không cần thiết.

### Provider từ biến môi trường

~~~groovy
def label = providers.environmentVariable('BUILD_LABEL')
    .orElse('local')
~~~

Đây là nguồn được Gradle mô hình hóa tốt hơn việc gọi `System.getenv('BUILD_LABEL')` tùy tiện trong task configuration. Nhưng không phải mọi API cũ đều nhận trực tiếp `Provider<T>`. Nếu một API buộc phải lấy giá trị ngay, hãy giải quyết có chủ đích và đánh giá ảnh hưởng đến configuration cache. Không ghi secrets vào manifest, archive hoặc build logs chỉ để thử Provider API.

### `convention`, `set` và giá trị được khóa

`Property<T>` có thể được cấu hình từ plugin, convention plugin và build script. `convention` có ý nghĩa default; `set` là lựa chọn giá trị tường minh. Một số API như `finalizeValue()` và `finalizeValueOnRead()` giúp khóa giá trị sau khi cấu hình, nhưng gọi sai thời điểm có thể khiến plugin khác không còn khả năng bổ sung cấu hình. Trong nội dung học cơ bản, chỉ cần hiểu `set`/`convention`/`get`; khi viết plugin nâng cao mới cần bàn sâu về vòng đời của property.

### API eager dễ bỏ sót

| Cách có thể gây eager configuration | Thay bằng |
| --- | --- |
| `tasks.create('x')` | `tasks.register('x')` |
| `tasks.getByName('x') { ... }` | `tasks.named('x') { ... }` |
| `tasks.all { ... }` | `tasks.configureEach { ... }` khi phù hợp |
| `tasks.withType(Test) { ... }` | `tasks.withType(Test).configureEach { ... }` |
| `taskProvider.get()` chỉ để truyền dependency | Truyền nguyên `taskProvider` |
| `taskProvider.get().outputFile.get()` ở configuration time | `taskProvider.flatMap { it.outputFile }` |

Không thay mọi API một cách máy móc: có lúc bạn thực sự cần một object task hoặc một giá trị ngay, nhưng đó nên là lựa chọn có chủ ý, sau khi hiểu hệ quả cấu hình.

## 8. Kotlin DSL và Groovy DSL: cùng mô hình, cú pháp khác

Bài thực hành chính viết theo **Groovy DSL `build.gradle`**. Với `build.gradle.kts`, các ý tưởng vẫn như nhau, nhưng cách gọi API theo kiểu generic:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar
import org.springframework.boot.gradle.tasks.run.BootRun

val archiveName = providers.gradleProperty("bootJarName")
    .orElse("service.jar")

tasks.named<BootJar>("bootJar") {
    archiveFileName.set(archiveName)
}

tasks.named<BootRun>("bootRun") {
    systemProperty("demo.mode", "training")
}
~~~

Đây là **đoạn cấu hình trong project Kotlin DSL đã áp dụng các plugin cần thiết**, không phải cả file `build.gradle.kts` độc lập. Không chép cú pháp generic `named<BootJar>` vào `build.gradle` Groovy. Trong Kotlin DSL, một custom task có thể dùng `abstract val message: Property<String>` với `@get:Input`; trong Groovy DSL ví dụ dùng abstract getter `getMessage()`.

## 9. Gỡ lỗi đúng lớp

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `Task with name 'bootJar' not found` | Boot plugin/Java plugin chưa tạo task, hoặc đang cấu hình sai subproject | Kiểm tra plugins, task list, đúng project |
| `Task with name 'bootWar' not found` | Không có WAR plugin/task trong module | Chỉ cấu hình khi project có `bootWar` |
| Provider `get()` báo chưa có value | Chưa `set`/`convention` hoặc chưa có project property | Dùng `orElse` cho tùy chọn hoặc khai báo input bắt buộc |
| Task consumer báo `@InputFile` không tồn tại | Chưa có producer dependency hoặc đường dẫn sai | Nối `TaskProvider.flatMap` đến output property hoặc thêm dependency cần thiết |
| Task custom luôn chạy lại | Thiếu metadata inputs/outputs hoặc output thay đổi | Khai báo đúng `@Input`/`@OutputFile`/`@InputFile`; tránh input ẩn |
| Task bị `UP-TO-DATE` dù bạn tưởng phải chạy | Inputs/outputs không đổi | Xem log `--info`; thử `--rerun-tasks` khi cần chẩn đoán |
| `bootRun` được cấu hình nhưng `java -jar` khác | Runtime độc lập với task Gradle | Truyền JVM args/application args khi deploy |
| Output JAR có tên khác | `archiveFileName`, classifier, destination hoặc script khác ghi đè | Kiểm tra task effective properties và file trong `build/libs` |
| Configuration time quá dài | Có nhiều `getByName`, `create`, `tasks.all` hoặc code eager | Sử dụng `register`/`named`/`configureEach` đúng nơi |
| Configuration cache báo lỗi | Action/closure giữ `Project` hoặc truy cập tài nguyên tùy tiện | Xem nguyên nhân cụ thể, dùng Provider/Property và task types phù hợp |

Một số lệnh chẩn đoán:

~~~bash
./gradlew tasks --all
./gradlew help --task bootJar
./gradlew bootJar --dry-run
./gradlew bootJar --info
./gradlew printBuildMarker --rerun-tasks
./gradlew help --configuration-cache
~~~

`tasks --all` giúp thấy task được đăng ký nhưng có thể làm một số task bị realize để liệt kê; đừng dùng số task lúc liệt kê để đo configuration avoidance của build bình thường. `--dry-run` chỉ xem task graph, **không tạo artifact**. `--info` cho log chi tiết hơn về up-to-date checks; `--rerun-tasks` yêu cầu chạy lại để chẩn đoán. `--configuration-cache` kiểm tra khả năng lưu và tái dùng cấu hình; cần đọc cảnh báo chính xác nếu cache không dùng được.

## 10. Quy trình áp dụng vào dự án Spring Boot thật

1. **Xác định task do ai sở hữu.** `bootJar` và `bootRun` do Spring Boot plugin cung cấp; nếu cần task riêng, dùng `tasks.register`.
2. **Kiểm tra task đã hiện diện trong đúng project.** Đừng dùng `tasks.named` để tạo task và đừng cấu hình `bootWar` ở project chỉ tạo JAR.
3. **Cấu hình task lazy.** Dùng `tasks.named('bootJar', BootJar) { ... }` và `withType(...).configureEach` khi cần chính sách trên nhiều task.
4. **Dùng typed Property và Provider.** Project properties từ `providers.gradleProperty`, file outputs từ `layout.buildDirectory.file`; nối `set(Provider)` thay vì `get()` sớm.
5. **Mô hình hóa input/output của task tự tạo.** Dùng `@Input`, `@OutputFile`, `@InputFile` và path sensitivity phù hợp để Gradle biết khi nào phải thực thi lại.
6. **Nối producer và consumer theo dữ liệu.** Nếu task consumer cần file từ producer, lấy output qua `taskProvider.flatMap` để giữ metadata và dependency.
7. **Phân biệt build và runtime.** `bootRun` chỉ dành cho môi trường chạy qua Gradle; xác nhận executable JAR bằng `java -jar` khi đóng gói.
8. **Xác minh bằng task graph, artifact và đầu ra thực tế.** Đừng kết luận “lazy” chỉ từ cú pháp; xem có đoạn code khác đang realize task hoặc resolve Provider sớm không.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `tasks.named('bootJar')` có tạo hoặc thực thi task `bootJar` không?

**Trả lời:** Không. Nó truy xuất `TaskProvider` của task đã đăng ký và có thể gắn logic cấu hình lazy.

**Câu 2.** Vì sao `tasks.register` thường được khuyến nghị thay `tasks.create`?

**Trả lời:** `register` có thể giữ task chưa được tạo/configure cho đến khi cần. `create` tạo task eager, tăng chi phí configuration cho những task không cần chạy.

**Câu 3.** `Property<String>.set(provider)` khác `provider.get()` rồi `set(value)` ở đâu?

**Trả lời:** Cách thứ nhất giữ kết nối lazy tới provider; cách thứ hai truy vấn giá trị ngay thời điểm `get()` được gọi.

**Câu 4.** Khi nào dùng `map` và khi nào dùng `flatMap`?

**Trả lời:** `map` khi ánh xạ giá trị thường sang giá trị thường; `flatMap` khi ánh xạ trả về một Provider khác, đặc biệt khi lấy một property output từ `TaskProvider`.

**Câu 5.** Vì sao `PrintBuildMarker` có thể tự chạy sau `WriteBuildMarker` mà không cần `dependsOn` trong bài thực hành?

**Trả lời:** File input được nối với provider output của producer, nên Gradle mang theo thông tin task nào tạo file và thiết lập dependency cần thiết.

**Câu 6.** Cấu hình JVM system property trong `bootRun` có lưu vào executable Boot JAR không?

**Trả lời:** Không. Task `bootRun` chỉ cấu hình JVM do Gradle khởi động; `java -jar` trên môi trường triển khai nhận cấu hình runtime riêng.

**Câu 7.** Tại sao `tasks.named('bootJar').get()` không được khuyến nghị nếu chỉ muốn chỉnh `archiveFileName`?

**Trả lời:** `get()` có thể realize task sớm mà không cần thiết; `tasks.named('bootJar') { archiveFileName.set(...) }` giữ cấu hình lazy.

## Tài liệu chính thức

- Gradle — [Avoiding Unnecessary Task Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `register`, `named`, `configureEach` và eager API.
- Gradle — [Configuring Tasks Lazily](https://docs.gradle.org/current/userguide/lazy_configuration.html): `Provider`, `Property`, `map`/`flatMap` và nối task inputs/outputs.
- Gradle — [Properties and Providers](https://docs.gradle.org/current/userguide/properties_providers.html): chuỗi provider và fallback.
- Spring Boot — [Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html): `bootJar`, `bootWar` và archive options.
- Spring Boot — [Running Your Application with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/running.html): `bootRun` và `JavaExec`.

**Ghi nhớ:** `tasks.named` giúp **cấu hình task khi cần**; Provider API giúp **cung cấp giá trị khi cần**; typed input/output properties giúp Gradle **nắm được dữ liệu và dependency giữa các task**. Cả ba cùng tạo nên build logic rõ ràng, dễ kiểm tra và có khả năng tối ưu cấu hình.
