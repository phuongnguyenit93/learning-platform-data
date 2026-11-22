# Áp dụng Gradle Build Cache và kiểm soát đầu vào của tác vụ

## 1. Bài toán và mục tiêu

Trong dự án Spring Boot sử dụng Gradle, một bản dựng thường phải biên dịch Java, xử lý resources, chạy kiểm thử, phân tích chất lượng và đóng gói ứng dụng. Một số bước tốn thời gian nhưng **đã từng chạy với cùng dữ liệu đầu vào** trên máy khác hoặc một lượt CI trước đó. **Gradle Build Cache** cho phép tái sử dụng **đầu ra của task có thể cache** thay vì chạy lại thao tác đó khi Gradle xác định kết quả trước đó còn hợp lệ.

Điểm quan trọng không phải đơn thuần bật `--build-cache`: nếu **đầu vào/đầu ra của task khai báo thiếu hoặc sai**, cache có thể trả về kết quả cũ, không tái lập, hoặc gây lỗi khó phát hiện. Vì thế, chủ đề này kết hợp hai việc: **bật build cache** và **mô hình hóa inputs/outputs chính xác**.

Sau bài học, bạn có thể:

1. Phân biệt `UP-TO-DATE`, `FROM-CACHE` và việc task được thực thi bình thường; hiểu build cache khác dependency cache và configuration cache.
2. Bật local build cache bằng `--build-cache` hoặc `org.gradle.caching=true`; biết lúc nào cần remote cache cho CI và nhóm phát triển.
3. Khai báo `@Input`, `@InputFile`, `@InputFiles`, `@OutputFile`, `@OutputDirectory` và đường dẫn được chuẩn hóa cho một custom Gradle task.
4. Dùng `@CacheableTask` một cách an toàn, tạo task sinh file với kết quả deterministic; quan sát cache hit/miss bằng lệnh Gradle Wrapper.
5. Nhận diện đầu vào ẩn như clock, environment, network, thứ tự file, Java toolchain hoặc system property và đưa chúng vào mô hình task hoặc loại task khỏi caching.
6. Chẩn đoán vì sao cache không hit và thiết kế policy local/CI phù hợp bảo mật, chất lượng và khả năng tái lập.

**Giới hạn ví dụ:** Spring Boot 3.3.5, Java 17, Gradle Wrapper tương thích với phiên bản plugin được chọn. Đây là **phiên bản minh họa** chứ không phải khuyến nghị phiên bản hiện tại của mọi project. Dự án thật phải dùng matrix Spring Boot/Gradle/JDK phù hợp và kiểm tra lại API nếu đang dùng một Gradle release rất cũ.

## 2. Bốn cơ chế dễ bị gọi chung là “cache”

| Cơ chế | Lưu hoặc ghi nhớ cái gì? | Câu hỏi nó trả lời | Dấu hiệu thường gặp |
| --- | --- | --- | --- |
| **Up-to-date checks / incremental build** | Fingerprint inputs/outputs của task và trạng thái đầu ra tại workspace | “Task này đã làm xong với đầu vào/đầu ra chưa đổi trong workspace này chưa?” | `UP-TO-DATE` |
| **Gradle Build Cache** | **Task output artifacts** được lập chỉ mục theo cache key của inputs/task implementation | “Có kết quả tương đương từ một lượt build trước để khôi phục không?” | `FROM-CACHE` |
| **Dependency cache** | Module metadata và artifact từ Maven/Gradle repositories | “JAR/POM này đã tải về hay có metadata trong cache chưa?” | Repository resolution có thể không cần tải lại |
| **Configuration Cache** | Kết quả của pha **configuration**: task graph và trạng thái cấu hình liên quan | “Có thể bỏ qua việc cấu hình lại build không?” | Log reuse configuration cache |

Ngoài ra, **Gradle Daemon** giữ JVM đang chạy và một số trạng thái trong bộ nhớ để giảm thời gian startup, nhưng đó không phải task output build cache.

### Ví dụ hai trạng thái khác nhau

~~~text
Lượt 1: :compileJava                  (executed)
Lượt 2: :compileJava UP-TO-DATE       (output còn nguyên ở workspace)
Lượt 3: :compileJava FROM-CACHE       (output đã mất, cache khôi phục lại)
~~~

Đây là **minh họa trạng thái**, không phải output bắt buộc cho mọi dự án. Gradle chỉ báo `FROM-CACHE` nếu task đủ điều kiện, cache được bật và có một entry khớp. Một task có thể không cacheable; cũng có thể dùng cache nhưng vẫn thực thi do chưa từng có key tương ứng.

**Không đánh đồng:** Maven local repository (`~/.m2/repository`), Gradle dependency cache hay “Download dependencies” trong IDE **không thay thế** Gradle Build Cache. Tải được Spring Boot starter từ cache dependency chỉ tiết kiệm download, không tự làm JavaCompile hoặc Test trở thành cache hit.

## 3. Gradle quyết định dùng lại task output như thế nào?

Một task có tập **inputs**, một đoạn **implementation**, các **outputs**, và có thể có điều kiện chỉ cho phép cache khi an toàn. Với những task được bật caching, Gradle tạo **build cache key** từ thông tin cần thiết để xác định tính tương đương của đầu ra.

Sơ đồ logic:

~~~text
Input values + input files + paths được chuẩn hóa
           + classpath/implementation/plugin/toolchain liên quan
           |
           v
     fingerprint + build cache key
           |
           +--> Outputs hiện có và hợp lệ? --> UP-TO-DATE
           |
           +--> Cache có entry khớp? -------> FROM-CACHE
           |
           +--> Không ----------------------> EXECUTE task
                                               |
                                               v
                                       Xác nhận outputs
                                               |
                                               v
                                      Lưu vào cache nếu được phép
~~~

**Cache key không chỉ dựa vào tên task.** Với custom task, Gradle còn xét các annotated properties, kiểu task, code/implementation classpath và những thành phần build logic có ảnh hưởng tới kết quả. Cùng tên `generateBuildLabel` nhưng input khác thì không được coi tương đương.

Một số quy tắc:

- **Inputs thay đổi**: Gradle phải thực thi hoặc tìm entry cache tương ứng với fingerprint mới.
- **Outputs bị xóa**: Gradle không thể nói `UP-TO-DATE`; nếu cache có entry khớp, nó có thể khôi phục outputs bằng `FROM-CACHE`.
- **Outputs còn nguyên**: Gradle có thể báo `UP-TO-DATE`, không cần đọc cache dù cache được bật.
- **Task chưa opt-in**: custom task type mặc định **không cacheable** chỉ vì có `@OutputFile`; annotation `@CacheableTask` là một cách explicit opt-in.
- **Task không có đầu ra được khai báo**: Gradle thường không thể tối ưu bằng task output cache theo mô hình thông thường.
- **Một số Gradle task built-in đã cacheable** như `JavaCompile`, `Test`, nhưng không được giả định **mọi** task `Jar`, `Copy`, `bootJar` hay task plugin ngoài đều được cache tự động.

**Giá trị của cache phụ thuộc khả năng tái lập:** cùng inputs và task implementation phải tạo cùng kết quả quan sát được. Nếu task đọc một giá trị mà Gradle không biết, cùng key có thể không còn bảo đảm cùng output.

## 4. Bật local Build Cache bằng Wrapper

### 4.1. Bật cho một lần chạy

Tại root của dự án có `gradlew` và `gradlew.bat`.

Linux/macOS:

~~~bash
./gradlew --version
./gradlew --build-cache build
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat --build-cache build
~~~

Option `--build-cache` kích hoạt build cache cho lần gọi này. Local cache mặc định được Gradle quản lý dưới **Gradle User Home**; không cần tự tạo thư mục cache để dùng cơ chế mặc định.

### 4.2. Bật thường xuyên qua gradle.properties

Trong file `gradle.properties` của project, thêm:

~~~properties
org.gradle.caching=true
~~~

Sau đó chạy:

~~~bash
./gradlew build
~~~

Khi muốn tạm tắt build cache cho một lượt điều tra:

~~~bash
./gradlew --no-build-cache build
~~~

`--no-build-cache` không tự xóa cache entries đã lưu. Cũng đừng xóa toàn bộ `~/.gradle` chỉ vì muốn kiểm tra task có cache hit: thư mục này còn chứa dependency caches, Wrapper distributions, Gradle state và nhiều dữ liệu khác.

### 4.3. Cách thử cache hit đúng

Một quy trình quan sát hợp lý:

~~~bash
./gradlew --build-cache build --info
./gradlew --build-cache build --info
./gradlew --build-cache clean build --info
~~~

- Lần đầu: nhiều task sẽ chạy vì chưa có output/cache.
- Lần thứ hai: với inputs/outputs không đổi, nhiều task có thể `UP-TO-DATE`.
- Lần thứ ba: `clean` xóa output trong thư mục build; các task **cacheable** có thể lấy lại kết quả từ local/remote cache và hiển thị `FROM-CACHE`.

**Không đảm bảo mọi task đều `FROM-CACHE`.** Task có thể không cacheable, phụ thuộc thời gian/network hoặc không có entry phù hợp. Đọc output `--info` để biết lý do.

**Không dùng `--rerun-tasks` để “kiểm tra cache hit”**: option này buộc task thực thi lại, bỏ qua cơ chế reuse thông thường. Nó hữu ích khi muốn điều tra output/task behavior, nhưng không phải phương pháp đo phần output được load từ build cache.

## 5. Kiểm soát inputs và outputs: quy tắc nền tảng

Gradle phải biết **mọi giá trị có thể làm thay đổi output** của task. Với custom task type, dùng các property và annotations được Gradle hỗ trợ.

| Annotation | Dữ liệu khai báo | Ý nghĩa |
| --- | --- | --- |
| `@Input` | String, số, boolean, enum hoặc property value tương ứng | Một giá trị điều khiển kết quả |
| `@InputFile` | Một file input | Gradle fingerprint file, biết khi nội dung/đường dẫn liên quan thay đổi |
| `@InputFiles` | Tập input files | Theo dõi nhiều nguồn; cần path sensitivity/normalization phù hợp |
| `@InputDirectory` | Một thư mục input | Theo dõi các file bên trong và đường dẫn tương đối nếu cấu hình |
| `@Classpath` | JVM classpath | Normalization phù hợp với JAR/classpath, có tính thứ tự |
| `@CompileClasspath` | Compile classpath | Normalization theo API compilation khi thích hợp |
| `@OutputFile` | Một file được tạo | Gradle biết artifact task chịu trách nhiệm |
| `@OutputDirectory` | Một thư mục được tạo | Gradle kiểm soát tập output của task |
| `@Nested` | Một cấu trúc object có annotated properties | Kết hợp model có nhiều thuộc tính |
| `@Internal` | Property không phải input/output cần theo dõi | Chỉ dùng nếu thật sự không ảnh hưởng tới kết quả |

**Không đánh dấu `@Internal` để che một input làm thay đổi output.** Gradle có thể coi task vẫn hợp lệ trong khi kết quả thực phải khác. Điều này làm cache thành **cache không chính xác** chứ không chỉ làm cache chậm.

### Path sensitivity và relocatability

Gradle có thể đưa **đường dẫn** vào fingerprint. Nếu máy A checkout ở `/home/dev/project` còn máy B ở `/agent/work/project`, absolute path khác nhau sẽ gây cache miss dù nội dung source giống hệt.

Các tùy chọn cần hiểu:

- `PathSensitivity.ABSOLUTE`: xét đường dẫn tuyệt đối; thường không phù hợp với remote cache chia sẻ nhiều workspace.
- `PathSensitivity.RELATIVE`: xét các đường dẫn tương đối với root input; phù hợp thư mục có cấu trúc file mang ý nghĩa.
- `PathSensitivity.NAME_ONLY`: quan tâm tên file nhưng không đầy đủ vị trí; chỉ dùng khi tên thực sự ảnh hưởng output.
- `PathSensitivity.NONE`: bỏ qua đường dẫn input file; phù hợp **một file** khi task chỉ đọc nội dung, không dùng tên/path.

Theo Gradle task best practices, thường ưu tiên `NONE` cho một file input nếu filename không ảnh hưởng kết quả, và `RELATIVE` cho thư mục/tập file có cấu trúc đường dẫn quan trọng. Với classpath, **`@Classpath` hoặc `@CompileClasspath`** thường phù hợp hơn tự áp dụng path normalization chung.

**Không chọn normalization chỉ để tăng cache hit** nếu đường dẫn thực sự ảnh hưởng output. Ví dụ task tạo một chỉ mục chứa filename thì filename là input có ý nghĩa, không được bỏ qua.

## 6. Ví dụ chạy được: custom task tạo resource từ file đầu vào

Ví dụ này dùng **Gradle Groovy DSL** để khai báo một custom task type `GenerateBuildLabel` có khả năng cache. Task đọc `src/main/build-label.txt`, tạo `build/generated/build-label.properties` và đăng ký file ấy làm resource ứng dụng. Một Spring Boot main class in giá trị từ resource khi chạy executable JAR.

Ưu điểm của tình huống này: bạn có thể **chứng minh đúng output được tái tạo** sau một lượt `clean`, quan sát version mới khi input đổi và kiểm tra cả file trên disk lẫn resource trong Boot JAR.

### 6.1. Cấu trúc project

~~~text
cache-demo/
├── settings.gradle
├── build.gradle
├── gradle.properties
├── gradlew, gradlew.bat, gradle/wrapper/
└── src/
    └── main/
        ├── build-label.txt
        └── java/com/example/cache/CacheDemoApplication.java
~~~

Ví dụ giả định project đã có Gradle Wrapper hợp lệ và Java 17. Gradle phải có thể tải Spring Boot plugin/dependencies từ các repositories được project/organisation cấp phép. Bạn không cần tạo file Maven vì đây là bài về Gradle Build Cache.

### 6.2. File settings.gradle

~~~groovy
rootProject.name = 'cache-demo'
~~~

### 6.3. File gradle.properties

~~~properties
org.gradle.caching=true
~~~

Đây là **project build-cache flag**, không phải Configuration Cache flag. Nếu tổ chức muốn chỉ bật ở CI hoặc qua CLI, có thể bỏ file này và thêm `--build-cache` vào các lệnh chạy.

### 6.4. File src/main/build-label.txt

~~~text
alpha
~~~

Đây là file text UTF-8 do bạn chủ động tạo. Task dưới đây dùng `trim()` nên một newline cuối file không ảnh hưởng giá trị hiển thị. Khi đổi `alpha` thành `beta`, **nội dung file input** đổi và Gradle phải tính fingerprint mới.

### 6.5. File build.gradle — hoàn chỉnh cho ví dụ

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

@CacheableTask
abstract class GenerateBuildLabel extends DefaultTask {

    @InputFile
    @PathSensitive(PathSensitivity.NONE)
    abstract RegularFileProperty getInputFile()

    @Input
    abstract Property<String> getLabelPrefix()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        String name = inputFile.get().asFile.getText('UTF-8').trim()
        File target = outputFile.get().asFile
        target.parentFile.mkdirs()
        target.setText('build.label=' + labelPrefix.get()
                + name + '\n', 'UTF-8')
    }
}

def buildLabelTask = tasks.register('generateBuildLabel', GenerateBuildLabel) {
    inputFile.set(layout.projectDirectory.file('src/main/build-label.txt'))
    labelPrefix.set(providers.gradleProperty('labelPrefix').orElse('demo-'))
    outputFile.set(layout.buildDirectory.file('generated/build-label.properties'))
}

tasks.named('processResources') {
    from(buildLabelTask)
}

springBoot {
    mainClass = 'com.example.cache.CacheDemoApplication'
}
~~~

Đoạn này là **build.gradle hoàn chỉnh** cho project mẫu, không phải đoạn Java. Trong dự án thực tế đang có `build.gradle` khác, **không ghi đè toàn bộ build file**; tích hợp task type và wiring vào build logic hiện có sau khi kiểm tra plugin/version/repository.

### 6.6. Vì sao task này được cache an toàn?

1. **`@CacheableTask`** đánh dấu custom task type là có thể lưu/khôi phục output khi Gradle bật build cache. Chỉ khai báo input/output chưa tự bật caching cho custom task.
2. **`@InputFile`** chỉ ra nguồn `build-label.txt`; Gradle theo dõi nội dung file. Vì code không sử dụng tên/đường dẫn input, `@PathSensitive(PathSensitivity.NONE)` là hợp lý cho task này.
3. **`@Input`** cho `labelPrefix`; khi gọi `-PlabelPrefix=release-`, giá trị tham gia fingerprint, bảo đảm output `release-alpha` không dùng nhầm cache entry của `demo-alpha`.
4. **`@OutputFile`** xác định **một file output** thuộc `build/generated`. Gradle biết nơi lưu/khôi phục kết quả; task không ghi đè file source trong repository.
5. **`@TaskAction`** đọc đúng các inputs đã khai báo, tạo một string deterministic và ghi UTF-8. Nó không dùng giờ hệ thống, network, random, hostname hay secret.
6. **`tasks.register`** đăng ký task lazily; `processResources.from(buildLabelTask)` dùng output task làm resource và giúp Gradle xác định quan hệ task producer/consumer. Task sinh metadata chỉ chạy khi cần cho task graph.
7. **Spring Boot `bootJar`** lấy resources từ main source set qua `processResources`, vì vậy `build-label.properties` có thể được đóng gói trong `BOOT-INF/classes` của executable JAR.
8. Phần generated resource được kiểm tra **bằng nội dung và runtime**, không chỉ qua dòng “task UP-TO-DATE” của Gradle.

**Giới hạn:** file input là một file duy nhất, nên `PathSensitivity.NONE` đúng. Nếu đổi task để đọc **cả thư mục** và tạo output theo cấu trúc đường dẫn tương đối, phải chuyển sang `@InputFiles` hoặc `@InputDirectory` với `RELATIVE` và thực thi task theo đúng cấu trúc ấy. Nếu việc chọn output phụ thuộc vào tên file, cần đưa tên file vào input model.

### 6.7. File src/main/java/com/example/cache/CacheDemoApplication.java

~~~java
package com.example.cache;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CacheDemoApplication {

    public static void main(String[] args) throws IOException {
        Properties props = new Properties();

        try (InputStream in = CacheDemoApplication.class.getClassLoader()
                .getResourceAsStream("build-label.properties")) {
            if (in == null) {
                throw new IllegalStateException("Missing build-label.properties");
            }
            props.load(in);
        }

        System.out.println("BUILD_LABEL=" + props.getProperty("build.label"));
        SpringApplication.run(CacheDemoApplication.class, args);
    }
}
~~~

Đây là lớp Java 17+ hoàn chỉnh và có `main` đúng. Vì Spring Boot Starter cơ bản không bao gồm web server, ứng dụng có thể khởi động rồi thoát sau khi in log; **đó là bình thường**. Giá trị in ra đến từ **file resource sinh bởi custom Gradle task**, không phải từ môi trường bên ngoài.

File này có thể biên dịch/chạy khi các Spring Boot dependencies đã được giải quyết qua Gradle. **Không chạy riêng `javac CacheDemoApplication.java`** mà thiếu Spring Boot trên classpath; dùng Wrapper như mục 7 để biên dịch và đóng gói đầy đủ.

## 7. Thử ba trạng thái: EXECUTED, UP-TO-DATE, FROM-CACHE

### 7.1. Lượt đầu — tạo output

Linux/macOS:

~~~bash
./gradlew --version
./gradlew --build-cache generateBuildLabel --info
cat build/generated/build-label.properties
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat --build-cache generateBuildLabel --info
Get-Content .\build\generated\build-label.properties
~~~

Nội dung file output kỳ vọng chính xác:

~~~properties
build.label=demo-alpha
~~~

Task có thể hiển thị log `> Task :generateBuildLabel` mà không có `UP-TO-DATE` hoặc `FROM-CACHE` trong lượt đầu với cache trống. Nếu cache đã chứa entry từ một lượt chạy trước, ngay lần đầu của **bài thực hành** vẫn có thể `FROM-CACHE`. Không suy ra trạng thái chỉ từ số lần mình gõ lệnh.

### 7.2. Lượt hai — workspace chưa đổi

~~~bash
./gradlew --build-cache generateBuildLabel --info
~~~

Khi inputs/outputs và task implementation không đổi, Gradle có thể hiển thị:

~~~text
> Task :generateBuildLabel UP-TO-DATE
~~~

Tức là **không cần chạy action** vì file output có sẵn và fingerprint hợp lệ. Đừng coi đây là bằng chứng task đã load dữ liệu từ build cache; không có bước khôi phục output nào cần thiết.

### 7.3. Lượt ba — xóa output rồi khôi phục bằng cache

~~~bash
./gradlew --build-cache clean generateBuildLabel --info
cat build/generated/build-label.properties
~~~

Trên PowerShell:

~~~powershell
.\gradlew.bat --build-cache clean generateBuildLabel --info
Get-Content .\build\generated\build-label.properties
~~~

`clean` xóa thư mục output `build` nhưng không xóa local build cache do Gradle quản lý. Nếu entry cache tồn tại và task đủ điều kiện, log có thể là:

~~~text
> Task :generateBuildLabel FROM-CACHE
~~~

File được khôi phục vẫn có:

~~~properties
build.label=demo-alpha
~~~

Nếu Gradle thực thi task thay vì `FROM-CACHE`, hãy dùng `--info` để đọc lý do. Khả năng cao là key khác, lần chạy trước chưa cache, caching bị disable hoặc implementation classpath không ổn định. **Không tự ép kết quả mong đợi**: trạng thái thực tế là dữ liệu kiểm chứng.

### 7.4. Thay input và quan sát cache miss

Trên Linux/bash, ghi nội dung mới:

~~~bash
printf 'beta\n' > src/main/build-label.txt
./gradlew --build-cache generateBuildLabel --info
cat build/generated/build-label.properties
~~~

PowerShell:

~~~powershell
Set-Content -Path .\src\main\build-label.txt -Value 'beta'
.\gradlew.bat --build-cache generateBuildLabel --info
Get-Content .\build\generated\build-label.properties
~~~

File output mới:

~~~properties
build.label=demo-beta
~~~

Gradle không được dùng entry `demo-alpha` cho inputs mới. Nó có thể **thực thi task** hoặc lấy từ **một entry đã cache riêng** với nội dung `beta` nếu trước đây bạn từng tạo entry đó.

Nếu muốn kiểm tra input `@Input` không phải file:

~~~bash
./gradlew --build-cache generateBuildLabel -PlabelPrefix=release- --info
cat build/generated/build-label.properties
~~~

Output kỳ vọng:

~~~properties
build.label=release-beta
~~~

Khi quay về `labelPrefix=demo-` và input vẫn là `beta`, Gradle có thể khôi phục cache entry cũ tương ứng. **Không cho rằng Gradle chỉ theo dõi file:** giá trị `@Input` cũng là một phần quan trọng của cache key.

## 8. Kiểm tra file sinh ra đã đi vào Spring Boot executable JAR

Sau khi trả file input về `alpha` (nếu muốn so sánh lại baseline), build ứng dụng:

~~~bash
./gradlew --build-cache clean bootJar
jar tf build/libs/cache-demo-0.0.1-SNAPSHOT.jar |
  grep 'BOOT-INF/classes/build-label.properties'
java -jar build/libs/cache-demo-0.0.1-SNAPSHOT.jar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --build-cache clean bootJar
jar tf .\build\libs\cache-demo-0.0.1-SNAPSHOT.jar |
    Select-String 'BOOT-INF/classes/build-label.properties'
java -jar .\build\libs\cache-demo-0.0.1-SNAPSHOT.jar
~~~

Nếu đầu vào là `alpha` với prefix mặc định `demo-`, dòng do application code in ra là:

~~~text
BUILD_LABEL=demo-alpha
~~~

Nếu đầu vào đang là `beta` hoặc prefix khác, giá trị phản ánh **inputs hiện tại của lượt build**. Ngoài dòng này còn có Spring Boot banner/log không ổn định theo thời gian/môi trường.

**Điểm mấu chốt:** không chỉ kiểm tra `generateBuildLabel` báo `FROM-CACHE`; cần bảo đảm consumer `processResources` sử dụng **đúng output** của producer và `bootJar` đóng gói file đã được tạo/khôi phục. Một build-cache hit có ích phải cho ra artifact **đúng**, không chỉ kết thúc nhanh.

Nếu Gradle báo resource trùng tên hoặc có nhiều task cùng viết `build-label.properties`, hãy tìm nơi khai báo outputs khác và tách đường dẫn. Hai task **không nên ghi đè cùng một output file/directory** mà không có mô hình ownership rõ ràng.

## 9. Các input ẩn khiến cache trả kết quả không an toàn

**Cache correctness** quan trọng hơn tỷ lệ cache hit. Hãy đối chiếu mọi nguồn dữ liệu task dùng với các thuộc tính mà Gradle biết.

| Task đọc hoặc sử dụng | Rủi ro nếu không khai báo | Cách kiểm soát |
| --- | --- | --- |
| Source file hoặc template | Thay nội dung nhưng Gradle vẫn coi cache key cũ | `@InputFile`/`@InputFiles` với normalization phù hợp |
| Các tham số CLI/build property | Đổi flag nhưng output vẫn lấy từ key cũ | `@Input` hoặc Provider được nối vào annotated property |
| Classpath dependency/tool | Đổi library/compiler mà output khác | `@Classpath`/`@CompileClasspath` hoặc sử dụng task chuẩn của plugin |
| JDK/toolchain ảnh hưởng bytecode | Biên dịch khác Java version mà fingerprint thiếu | Khai báo toolchain và để plugin chuẩn theo dõi compiler config |
| Environment variable | CI và local dùng biến khác nhưng Gradle không biết | Model hóa biến ảnh hưởng output là input; không cache task dùng secret không an toàn |
| Current time/clock | Mỗi lượt sinh timestamp khác dù inputs như cũ | Loại timestamp khỏi output hoặc truyền thời điểm cố định như explicit input |
| Random/UUID | Output thay đổi nhưng key không thay đổi | Dùng seed đã khai báo nếu thật sự cần; không cache nondeterministic output |
| Hostname/IP/user home | Cache không relocatable giữa developer/CI | Tránh nhúng path/hostname vào output; nếu thật sự cần, khai báo input hoặc tắt cache |
| Network request/remote API | Response thay đổi ngoài kiểm soát của Gradle | Snapshot dữ liệu thành input được quản lý hoặc không cache task |
| System property/locale/timezone | Biến đổi kết quả format/test | Khai báo các thuộc tính có ảnh hưởng, cố định locale/timezone |
| Thứ tự danh sách input files | Kết quả khác khi thứ tự khác | Dùng dạng input có tính order phù hợp và iterate theo thứ tự deterministic |
| File outside declared inputs | Task đọc một file “bí mật” Gradle không theo dõi | Khai báo file hoặc thiết kế lại task để không phụ thuộc trạng thái ẩn |

Ví dụ sai:

~~~groovy
tasks.register('generateBadVersion') {
    outputs.file(layout.buildDirectory.file('generated/version.txt'))
    doLast {
        def f = layout.buildDirectory.file('generated/version.txt').get().asFile
        f.parentFile.mkdirs()
        f.text = 'built-at=' + new Date().toString()
    }
}
~~~

Task này cho ra nội dung khác nhau theo clock nhưng **clock không được model hóa là input**. Chỉ khai báo output có thể khiến task được coi `UP-TO-DATE` khi kết quả lẽ ra phải thay đổi; nếu tùy tiện thêm caching, lỗi còn nghiêm trọng hơn. Đoạn này **cố tình là phản ví dụ**, không dùng cho pipeline production.

Cách sửa phải theo mục tiêu nghiệp vụ. Nếu metadata `built-at` không cần thiết, bỏ timestamp. Nếu cần timestamp từ release pipeline, truyền một timestamp ổn định và explicit như `-PreleaseTimestamp=...`, khai báo qua `@Input` rồi kiểm soát version/CI. Nếu output bắt buộc phụ thuộc giờ hiện tại thật, **không opt-in vào Build Cache** cho task ấy.

## 10. Chọn normalization đúng cho input files

### 10.1. Một file đầu vào không phụ thuộc tên

Trong task `GenerateBuildLabel`:

~~~groovy
@InputFile
@PathSensitive(PathSensitivity.NONE)
abstract RegularFileProperty getInputFile()
~~~

Task chỉ đọc **nội dung UTF-8**. Nếu đổi thư mục checkout từ `/home/dev/cache-demo` sang `/agent/cache-demo` nhưng file vẫn cùng nội dung, task có thể dùng cùng cache key cho phần input file đó.

### 10.2. Thư mục gồm nhiều file, giữ đường dẫn tương đối

Với task đọc một cây file như `src/main/templates` và output phụ thuộc vào vị trí từng template, pattern:

~~~groovy
@InputDirectory
@PathSensitive(PathSensitivity.RELATIVE)
abstract DirectoryProperty getTemplateDirectory()
~~~

Đây là **trích đoạn thuộc một custom task class khác**, không phải code độc lập. Cần thêm import `org.gradle.api.file.DirectoryProperty`, property output, task action và đăng ký task trước khi dùng. Tham số `RELATIVE` giúp khác checkout root path không gây miss vô ích, nhưng thay `a/index.html` thành `b/index.html` vẫn là thay đổi có ý nghĩa.

### 10.3. Java classpath

Task compiler hoặc analyzer chạy trên dependencies có thể cần:

~~~groovy
@Classpath
abstract ConfigurableFileCollection getAnalysisClasspath()
~~~

Đây là **trích đoạn declaration**; cần import `org.gradle.api.file.ConfigurableFileCollection` và `org.gradle.api.tasks.Classpath`. Gradle dùng normalization đặc thù classpath/JAR, thay vì chỉ so absolute path. Với Java compile classpath, có tình huống `@CompileClasspath` phù hợp vì bỏ qua thay đổi không ảnh hưởng API compilation. Hãy dùng task chuẩn của Java plugin khi có thể thay vì tự viết compiler task với inputs không đủ.

**Không đánh dấu input file cùng lúc bằng các path annotations mâu thuẫn.** Lựa chọn annotation dựa trên **ý nghĩa thực sự** của dữ liệu đối với output.

## 11. Remote Build Cache: dùng khi nhóm hoặc CI cần chia sẻ kết quả

**Local cache** giúp một developer đổi branch, chạy lại task sau `clean` hoặc xây dựng nhiều lần. **Remote cache** cho phép nhiều máy dùng chung kết quả cacheable tasks, thường đặc biệt hữu ích khi CI đã chạy trên clean worker và developer cần cùng output.

Cấu hình của Gradle có thể đặt ở `settings.gradle[.kts]` trong block `buildCache`. Ví dụ ý tưởng bằng Groovy DSL:

~~~groovy
// settings.gradle: chỉ phần cấu hình cache, ghép cùng rootProject.name
import org.gradle.caching.http.HttpBuildCache

buildCache {
    local {
        enabled = true
    }
    remote(HttpBuildCache) {
        url = uri('https://build-cache.example.org/cache/')
        push = System.getenv('CI') == 'true'
        credentials {
            username = providers.gradleProperty('cacheUser').orNull
            password = providers.gradleProperty('cachePassword').orNull
        }
    }
}
~~~

**Đây là ví dụ cấu hình dành cho một server giả định, không chạy được nếu không có cache service thực.** URL minh họa phải được thay bằng địa chỉ remote build cache được tổ chức cấp phép; credentials cần được cung cấp qua CI secret store hoặc môi trường an toàn, **không commit mật khẩu vào repository**. Server phải hỗ trợ Gradle HTTP Build Cache protocol.

Mô hình chia sẻ thường khuyến nghị:

- Developer **đọc** remote cache (pull) nhưng **không push** lên cache chung.
- CI job tin cậy, kiểm thử và làm sạch môi trường có thể **push** khi chính sách tổ chức cho phép.
- CI và developers dùng Gradle Wrapper/JDK/plugin versions có quy tắc tương thích; khác implementation/input sẽ dẫn tới key khác.
- Bảo vệ remote cache bằng TLS, authentication và quyền hạn thích hợp; phân vùng namespace hoặc service nếu tổ chức có nhiều trust levels.
- Theo dõi cache hit rate, chi phí network/storage và an toàn dữ liệu. Một remote cache chậm có thể làm build lâu hơn nếu outputs quá nhỏ hoặc cache misses quá nhiều.

**Cảnh báo bảo mật:** build cache có thể chứa compiled outputs, generated resources hoặc test reports. Không cache các task đưa **secrets** vào output; không cho untrusted branch/job push kết quả vào cache mà nhiều project quan trọng sẽ tin dùng. Remote cache không chỉ là công cụ tăng tốc, nó còn là **nguồn artifact** cần được quản trị.

Trong môi trường chỉ muốn sử dụng local cache, **không cần** remote block. Dùng `--build-cache` hoặc `org.gradle.caching=true` đã đủ để học toàn bộ cơ chế task inputs/outputs.

## 12. Build Cache trong Spring Boot Gradle: nên kỳ vọng điều gì?

Một dự án Spring Boot thông thường có các task như:

| Task | Vai trò | Khả năng cache cần hiểu |
| --- | --- | --- |
| `compileJava` | Biên dịch source Java | Gradle JavaCompile có hỗ trợ caching khi cấu hình phù hợp; compiler args, source/classpath/toolchain là inputs quan trọng |
| `compileTestJava` | Biên dịch test Java | Có thể cacheable; thay đổi test source/classpath gây key mới |
| `test` | Chạy unit/integration tests đã khai báo | Gradle Test có thể cacheable khi inputs, test runtime, JVM args và môi trường có ảnh hưởng được model hóa đúng |
| `processResources` | Xử lý resource copy/filter | Task copy thường không phải trường hợp cần task output caching; up-to-date checks có thể đã đủ |
| `bootJar` | Đóng gói Spring Boot executable JAR | Không mặc định khẳng định task `bootJar` là cacheable với mọi version plugin; kiểm tra bằng log và metadata của version đang dùng |
| `bootRun` | Chạy ứng dụng | Task chạy tiến trình có side effects, thường không nên lấy trạng thái chạy app làm output cache |
| `generateBuildLabel` | Custom task ví dụ | Chỉ cacheable khi khai báo inputs/outputs và `@CacheableTask` như mục 6 |

**Cache không thay thế kiểm thử.** Nếu Gradle `test FROM-CACHE`, Gradle tin rằng task có outputs hợp lệ từ cùng inputs; nhưng nếu test đọc network, secret hoặc external database mà không khai báo phù hợp, việc reuse có thể không an toàn. Với các integration tests phụ thuộc môi trường sống, cần cân nhắc cách cô lập, snapshot trạng thái, hoặc tắt caching của task để luôn chạy.

Tương tự, `bootRun` chạy Spring Boot application là một hoạt động runtime có thể có tác động ngoài build (kết nối database, mở port, gửi message). Không tìm cách cache “kết quả chạy ứng dụng” như task tạo file deterministic.

### Bản dựng có thể tái lập

Để cache hit giữa local và CI mà vẫn đúng:

1. Dùng **Gradle Wrapper** được version-control, không dùng Gradle global phiên bản tùy ý.
2. Dùng **Java Toolchains** cho compiler/test tasks khi project cần một JDK cụ thể.
3. Để dependency versions được quản lý có chủ đích, cân nhắc locking/verification khi chính sách yêu cầu; tránh dynamic/changing versions làm build khó tái lập.
4. Không nhúng absolute checkout paths và timestamps tùy ý vào file generated.
5. Tách inputs hiện trạng build (source, version, config, flag) khỏi runtime secrets và dữ liệu production.
6. Kiểm thử cả **cache cold build** và **cache hit build** để phát hiện đầu vào chưa khai báo.

## 13. Chẩn đoán cache miss: các lệnh hữu ích

### 13.1. Bật log nguyên nhân

Linux/bash:

~~~bash
./gradlew --build-cache generateBuildLabel --info
./gradlew --build-cache clean generateBuildLabel --info
./gradlew --build-cache build --info
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --build-cache generateBuildLabel --info
.\gradlew.bat --build-cache clean generateBuildLabel --info
.\gradlew.bat --build-cache build --info
~~~

Gradle thường giải thích task không cacheable, input/implementation change, cache key hoặc caching bị disabled khi bật `--info` hoặc `--debug`. `--debug` rất nhiều output và có thể chứa thông tin nhạy cảm; chỉ dùng khi cần và làm sạch log trước khi chia sẻ.

### 13.2. Bảng điều tra

| Hiện tượng | Giải thích/nguồn gốc thường gặp | Cách xử lý |
| --- | --- | --- |
| Task luôn `UP-TO-DATE`, không thấy `FROM-CACHE` | Output còn ở workspace, không cần load từ cache | Thử `clean` trước task và đọc `--info` |
| Task luôn thực thi sau `clean` | Chưa có cache entry, cache disabled, task không cacheable hoặc key khác | Xác nhận `--build-cache`, `@CacheableTask`, inputs/outputs và log |
| Gradle báo caching disabled vì thiếu outputs | Task không khai báo outputs thực hoặc không có kết quả dạng file | Khai báo `@OutputFile`/`@OutputDirectory` khi phù hợp |
| Cache miss khi đổi checkout directory | Absolute input paths hoặc output chứa path cứng | Chọn `PathSensitivity.NONE/RELATIVE` theo ý nghĩa, tránh nhúng absolute path |
| Cache miss dù source không đổi | JDK/plugin/Gradle version, build script, compiler args hoặc classpath khác | So sánh Wrapper, toolchain, dependency graph, cache key và Gradle logs |
| Task báo `UP-TO-DATE` nhưng output sai | Một input ảnh hưởng kết quả chưa khai báo | Bổ sung `@Input`/`@InputFile`, xóa giả định sai, kiểm thử |
| Task `FROM-CACHE` nhưng resource trong JAR cũ | Consumer task wiring thiếu output producer hoặc packaging dùng resource khác | Dùng `from(taskProvider)` và kiểm tra `BOOT-INF/classes` |
| Cache hit nhưng integration test không phản ánh DB hiện tại | Test phụ thuộc external mutable state chưa khai báo | Dùng test fixture/container version cố định hoặc tắt caching cho task đó |
| Remote cache trả 401/403 | Thiếu credentials, user không có quyền push/pull | Kiểm tra CI secrets, read/write policy, TLS và endpoint |
| Remote cache chậm hơn chạy task | Network latency/serialization quá lớn, output quá nhỏ | Dùng local cache, tắt remote cho task không hiệu quả hoặc cấu hình cache service hợp lý |
| Có cache entry nhưng không load được | Cache entry hỏng, key không khớp hoặc metadata/implementation khác | Đọc log lỗi, làm sạch entry có vấn đề theo hướng dẫn; không xóa toàn bộ Gradle home |
| Task trùng output directory | Hai producers cùng ghi vào một đường dẫn | Phân quyền ownership output, tách path hoặc cấu hình dependency đúng |
| Chạy với `--offline` thì build được | Artifacts/cache local đã đủ | Không kết luận remote cache/repository đang truy cập tốt |
| Task chạy lại do `--rerun-tasks` | User đã yêu cầu buộc thực thi thay vì reuse | Bỏ flag khi muốn đánh giá cache hits |

**Nguyên tắc:** cache miss có thể là **hành vi đúng** khi input đổi. Đừng coi mọi cache miss là bug cần ép thành cache hit.

## 14. Quy trình kiểm chứng cache correctness cho CI

Trước khi chia sẻ remote cache với nhiều developer:

1. **Chụp baseline:** Gradle Wrapper/JDK/Boot plugin versions, câu lệnh build, cache flag và những task dự kiến được cache.
2. **Cold build:** chạy trên workspace sạch với cache trống nếu có thể; ghi test results và checksum của generated artifacts.
3. **Local reuse:** chạy lại không đổi; xác minh `UP-TO-DATE`, sau `clean` xác minh task có thể `FROM-CACHE` khi cacheable.
4. **Input mutation:** đổi **một** input được khai báo như `build-label.txt` hoặc `-PlabelPrefix`; xác nhận output mới và cache key mới.
5. **Change back:** đưa input về baseline, xóa output; xác nhận kết quả cache khôi phục đúng nếu có entry.
6. **Cross-workspace:** dùng đường dẫn checkout khác và cùng source/config; kiểm tra path normalization có hợp lý để tăng khả năng cache hit.
7. **Compare outputs:** so sánh file/generated resource thực, không chỉ log. Với artifact có metadata biến động, hiểu và chuẩn hóa nguyên nhân thay đổi.
8. **Run tests:** unit tests và integration tests quan trọng phải pass với cả lượt thực thi mới và lượt load cache.
9. **Security review:** rà các outputs có secret, token, key, endpoint cá nhân; không push lên cache chung nếu chứa thông tin nhạy cảm.
10. **Remote rollout:** ban đầu cho developers đọc, CI trusted push, quan sát cache hit/miss và lỗi truyền tải trước khi mở rộng.
11. **Document:** trong PR ghi rõ inputs/outputs, normalization, cache opt-in và cách vô hiệu cache khi có sự cố.

**Một lần build xanh chưa đủ để kết luận caching an toàn.** Chỉ khi bạn chứng minh input thay đổi dẫn tới output đúng và cùng input khôi phục được output đúng mới có cơ sở tin vào custom cacheable task.

## 15. Bài thực hành và kết quả mong đợi

Thực hiện trong một branch thử nghiệm của Spring Boot Gradle project có Java 17+:

1. Tạo các file ở mục 6 gồm `settings.gradle`, `gradle.properties`, `build.gradle`, `src/main/build-label.txt` và `CacheDemoApplication.java`.
2. Chạy `./gradlew --build-cache generateBuildLabel --info`; mở file `build/generated/build-label.properties`, xác nhận `build.label=demo-alpha`.
3. Chạy lại cùng lệnh để quan sát `UP-TO-DATE` khi outputs vẫn còn.
4. Chạy `./gradlew --build-cache clean generateBuildLabel --info`; kiểm tra khả năng `FROM-CACHE` và file output vẫn chính xác.
5. Đổi đầu vào `alpha` thành `beta`, chạy lại task; xác nhận `build.label=demo-beta`.
6. Chạy với `-PlabelPrefix=release-`; xác nhận `build.label=release-beta` và giải thích vì sao Gradle phải chọn key khác.
7. Chạy `./gradlew --build-cache clean bootJar`, mở `BOOT-INF/classes/build-label.properties` trong JAR và chạy `java -jar`; kiểm tra `BUILD_LABEL` khớp giá trị nguồn.
8. Thử làm task sai ở branch thử nghiệm (ví dụ bỏ annotation `@Input` của prefix), quan sát nguy cơ dùng kết quả cũ, rồi **khôi phục annotation đúng**.
9. Giải thích vì sao `UP-TO-DATE` không đồng nghĩa `FROM-CACHE`, và vì sao `--rerun-tasks` không phải cách chứng minh cache restore.
10. Ghi báo cáo ngắn gồm lệnh, đầu vào, key/miss/hit từ log nếu có, file output, JDK/Gradle version và kết quả run ứng dụng.

**Tiêu chí hoàn thành:** bạn có thể bật cache bằng Wrapper, viết một custom task deterministic và cacheable, khai báo đủ file/value inputs cùng outputs, kiểm tra chính xác resource được đóng gói, và chỉ ra được lý do khi Gradle **không reuse** task output.

## Tài liệu chính thức

- [Gradle – Build Cache](https://docs.gradle.org/current/userguide/build_cache.html)
- [Gradle – Build Cache Use Cases](https://docs.gradle.org/current/userguide/build_cache_use_cases.html)
- [Gradle – Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html)
- [Gradle – Declaring Task Inputs and Outputs](https://docs.gradle.org/current/userguide/incremental_builds.html)
- [Gradle – Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html)
- [Gradle – More About Tasks](https://docs.gradle.org/current/userguide/more_about_tasks.html)
- [Gradle – Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Gradle – Performance](https://docs.gradle.org/current/userguide/performance.html)
- [Gradle – Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Spring Boot – Gradle Plugin: Getting Started](https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html)
