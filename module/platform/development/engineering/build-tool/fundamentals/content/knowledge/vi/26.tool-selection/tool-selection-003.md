# Gradle: mô hình tác vụ, plugin và DSL cấu hình

Gradle tổ chức quá trình build quanh **task** (tác vụ), **plugin** và **build script**. Task biểu diễn một đơn vị công việc như biên dịch mã nguồn, chạy kiểm thử, đóng gói JAR hoặc tạo tài liệu. Plugin bổ sung các khả năng build có quy ước, chẳng hạn Java Library, Application hoặc Maven Publish. DSL Groovy và Kotlin cho phép khai báo project, dependency, plugin, task và các quy tắc cấu hình bằng mã dễ đọc.

Muốn làm việc hiệu quả với Gradle, cần hiểu ba giai đoạn chính: khởi tạo build, cấu hình project/task và thực thi task graph. Một task có thể được đăng ký, cấu hình và thực thi ở những thời điểm khác nhau. Việc đăng ký task theo cách lazy, khai báo đúng quan hệ phụ thuộc và dùng Provider API giúp build nhanh hơn, dễ bảo trì và tương thích với Configuration Cache.

Bài này giải thích mô hình tác vụ của Gradle, cách plugin mở rộng build, sự khác nhau giữa Groovy DSL và Kotlin DSL, và cách kết hợp chúng để xây dựng cấu hình rõ ràng.

## 1. Gradle build gồm những thành phần nào?

Một dự án Gradle thường có các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| Gradle Wrapper | Cố định phiên bản Gradle mà dự án sử dụng |
| Settings script | Khai báo tên build, project con, plugin repository và một số quy tắc ở cấp build |
| Build script | Cấu hình một project: plugin, dependency, task và các thuộc tính |
| Project | Một đơn vị trong build, có thể là root project hoặc subproject |
| Plugin | Bổ sung task, extension, configuration và quy ước |
| Task | Một đơn vị công việc có thể được đưa vào task graph |
| Dependency configuration | Nhóm dependency theo mục đích như compile, runtime hoặc test |
| Extension | Một đối tượng cấu hình có tên, thường được plugin tạo ra |

Một cấu trúc điển hình:

    sample-app/
      gradlew
      gradlew.bat
      settings.gradle
      build.gradle
      gradle/
        wrapper/
          gradle-wrapper.jar
          gradle-wrapper.properties
      src/
        main/
          java/
        test/
          java/

Với Kotlin DSL, các file script thường có đuôi .gradle.kts:

    settings.gradle.kts
    build.gradle.kts

Gradle Wrapper là cách khuyến nghị để chạy build vì nó giúp mọi thành viên và CI dùng cùng phiên bản Gradle đã khai báo.

## 2. Task là gì?

Task là một đơn vị công việc do Gradle quản lý. Ví dụ:

- compileJava biên dịch mã nguồn Java chính.
- processResources sao chép và xử lý tài nguyên.
- test chạy kiểm thử.
- jar tạo JAR từ output của source set.
- javadoc tạo tài liệu API.
- publish xuất bản artifact lên repository.

Một task thường có:

- **Inputs:** dữ liệu mà task đọc, ví dụ source files, dependency classpath, cấu hình hoặc file dữ liệu.
- **Outputs:** dữ liệu task tạo ra, ví dụ class file, JAR hoặc report.
- **Actions:** các thao tác được thực thi khi task chạy.
- **Dependencies:** các task phải hoàn thành trước task hiện tại.
- **Properties:** giá trị cấu hình task và các input/output được khai báo.

Ví dụ, compileJava đọc mã nguồn và classpath, rồi tạo class file. Task jar cần output từ compileJava và processResources để đóng gói ứng dụng.

Task không nhất thiết tương ứng với một lệnh shell hoặc một process riêng. Một task có thể chạy code trong Gradle daemon, dùng worker process hoặc gọi công cụ ngoài tùy plugin và cách triển khai.

## 3. Ba giai đoạn của Gradle build

Gradle thực hiện build qua ba giai đoạn khái niệm:

    Initialization
         |
         v
    Configuration
         |
         v
    Execution

### Initialization

Gradle đọc settings script để xác định build gồm những project nào, root project là gì và các project con được kết nối ra sao. Trong giai đoạn này, Gradle tạo mô hình build và xác định các project cần tham gia.

Với multi-project build, settings.gradle có thể khai báo:

    rootProject.name = 'shop'
    include 'domain', 'application', 'web'

Khi đó, Gradle biết có root project và ba subproject.

### Configuration

Gradle đánh giá build scripts và cấu hình các project, plugin, extension, dependency configuration và task. Gradle cũng xác định các quan hệ cần thiết để tạo task graph cho yêu cầu build hiện tại.

Ví dụ, khi dùng Java Plugin, plugin đăng ký các task compileJava, processResources, classes, test và jar cùng những quan hệ tương ứng.

### Execution

Gradle thực thi những task nằm trong task graph theo thứ tự phụ thuộc. Những task độc lập có thể chạy song song nếu build và cấu hình cho phép.

Một task không nằm trong task graph của lần chạy hiện tại sẽ không thực thi, dù nó đã được đăng ký trong build script.

## 4. Task graph là gì?

Task graph là đồ thị có hướng mô tả các task cần chạy và quan hệ thứ tự giữa chúng. Nếu task B phụ thuộc task A, A phải hoàn thành trước khi B chạy.

Ví dụ:

    compileJava ------+
                      |
    processResources -+--> classes --> jar

Một lệnh:

    ./gradlew jar

có thể khiến Gradle đưa compileJava, processResources, classes và jar vào task graph theo quan hệ dependency được plugin Java định nghĩa.

Một lệnh:

    ./gradlew test

sẽ chọn task test và các task cần thiết để biên dịch test, biên dịch mã chính và chuẩn bị tài nguyên. Task graph thực tế phụ thuộc plugin, project và cấu hình của build.

### Task graph không phải dependency graph thư viện

Hai loại graph cần được phân biệt:

- Dependency graph mô tả các thư viện/module mà project cần và version/variant được resolve.
- Task graph mô tả công việc build cần chạy và thứ tự giữa các task.

Dependency graph ảnh hưởng classpath của task compile/test. Task graph quyết định khi nào task đó chạy. Thay đổi một dependency có thể làm task input thay đổi và khiến task phải thực thi lại.

## 5. Task selector và task dependency

Task selector là tên task được người dùng yêu cầu trên command line:

    ./gradlew build

Gradle tìm task build phù hợp trong project được chọn. Nếu task đó phụ thuộc vào task khác, Gradle thêm các task cần thiết vào graph.

Có thể gọi task ở project cụ thể:

    ./gradlew :app:test
    ./gradlew :domain:build

Dấu hai chấm biểu thị đường dẫn task trong build multi-project. Task :app:test là task test của project app.

### dependsOn

Task có thể khai báo task khác là dependency:

    tasks.register('packageApp') {
        dependsOn tasks.named('jar')
    }

Với Kotlin DSL:

    tasks.register("packageApp") {
        dependsOn(tasks.named("jar"))
    }

Khi packageApp được yêu cầu, jar phải hoàn thành trước.

dependsOn thể hiện quan hệ cần thiết để tạo task graph. Không nên dùng nó chỉ để ép hai task chạy theo thứ tự nếu task sau không thực sự cần output của task trước.

## 6. dependsOn, mustRunAfter và shouldRunAfter

Ba cơ chế này có ý nghĩa khác nhau:

| Cơ chế | Có đưa task vào graph? | Ý nghĩa |
| --- | --- | --- |
| dependsOn | Có | Task hiện tại cần task phụ thuộc được thực hiện |
| mustRunAfter | Không | Nếu cả hai task đã có trong graph, task hiện tại phải chạy sau task được chỉ định |
| shouldRunAfter | Không | Gợi ý thứ tự nếu có thể, nhưng có thể bị bỏ qua |

Ví dụ:

    tasks.register('verifyPackage') {
        dependsOn tasks.named('jar')
    }

    tasks.named('integrationTest') {
        mustRunAfter tasks.named('test')
    }

mustRunAfter không tự chạy test. Nếu chỉ gọi integrationTest, task test không tự được thêm vào graph chỉ vì có quy tắc thứ tự.

Nếu yêu cầu thực sự là integrationTest cần test chạy trước, có thể dùng dependsOn hoặc một task lifecycle thích hợp. Chọn quan hệ theo ý nghĩa của công việc, không chỉ theo thứ tự mong muốn.

## 7. finalizedBy và finalizer task

finalizedBy cho phép gắn một task cuối cùng để thực hiện sau task được chỉ định, kể cả khi task chính kết thúc không thành công trong những trường hợp Gradle hỗ trợ finalizer execution.

Ví dụ:

    tasks.register('cleanupTemp') {
        doLast {
            println 'Cleaning temporary data'
        }
    }

    tasks.named('integrationTest') {
        finalizedBy tasks.named('cleanupTemp')
    }

Khi integrationTest được đưa vào graph, cleanupTemp được gắn như finalizer.

Finalizer hữu ích cho dọn dẹp tài nguyên hoặc hoàn tất thao tác liên quan. Tuy nhiên, task finalizer không nên thay thế cơ chế finally/teardown của framework test hoặc xử lý transaction nếu công việc cần bảo đảm mạnh hơn.

## 8. Đăng ký task: eager và lazy

Gradle cung cấp hai cách thường gặp để tạo task:

    tasks.create('hello') {
        doLast {
            println 'Hello Gradle'
        }
    }

và:

    tasks.register('hello') {
        doLast {
            println 'Hello Gradle'
        }
    }

tasks.create tạo và cấu hình task ngay khi đoạn code được đánh giá. tasks.register đăng ký task theo cách lazy; Gradle trì hoãn tạo/cấu hình task đầy đủ cho tới khi task thực sự cần thiết.

Với build lớn, lazy registration giảm công việc cấu hình cho task không được sử dụng và hỗ trợ configuration avoidance.

### TaskProvider

tasks.register trả về TaskProvider. Có thể dùng provider này để cấu hình hoặc liên kết task khác mà không cần lấy Task instance ngay:

    def reportTask = tasks.register('generateReport') {
        group = 'Reporting'
        description = 'Generates a build report.'
    }

    tasks.register('verifyReport') {
        dependsOn reportTask
    }

Với Kotlin DSL:

    val reportTask = tasks.register("generateReport") {
        group = "Reporting"
        description = "Generates a build report."
    }

    tasks.register("verifyReport") {
        dependsOn(reportTask)
    }

### tasks.named

Khi task đã được đăng ký bởi plugin hoặc build script khác, dùng tasks.named để lấy provider và cấu hình:

    tasks.named('test') {
        useJUnitPlatform()
    }

Kotlin DSL:

    tasks.named<Test>("test") {
        useJUnitPlatform()
    }

tasks.named không tạo task mới. Nó tham chiếu task đã được đăng ký với tên đó và có thể cấu hình lazy.

## 9. Configuration avoidance

Configuration avoidance là cách viết build script để không tạo và cấu hình những task không cần thiết.

Nên ưu tiên:

    tasks.register('generateDocs') {
        // Task configuration
    }

    tasks.named('test') {
        // Configure existing task
    }

Hạn chế truy cập eager:

    tasks.getByName('test') {
        // Eager lookup/configuration
    }

và tránh:

    tasks.all {
        // Có thể khiến nhiều task được cấu hình sớm
    }

Các API eager không phải lúc nào cũng sai, nhưng với build lớn nên ưu tiên register, named, configureEach và Provider API.

### configureEach

Có thể cấu hình tất cả task thuộc một loại theo cách lazy:

    tasks.withType(Test).configureEach {
        maxHeapSize = '1g'
    }

Kotlin DSL:

    tasks.withType<Test>().configureEach {
        maxHeapSize = "1g"
    }

Gradle chỉ áp dụng cấu hình khi task phù hợp được tạo/cấu hình. Điều này thường hiệu quả hơn việc duyệt và cấu hình ngay toàn bộ task hiện có.

## 10. Task action và doFirst/doLast

Task action là phần công việc được thực thi khi task chạy. Với task khai báo nhanh trong build script, có thể thêm action bằng doFirst và doLast:

    tasks.register('hello') {
        doFirst {
            println 'Starting hello task'
        }
        doLast {
            println 'Hello from Gradle'
        }
    }

doFirst thêm action vào đầu danh sách action; doLast thêm vào cuối. Các action được thực thi theo thứ tự đã đăng ký tương ứng.

Đây là cách thuận tiện cho tác vụ nhỏ hoặc minh họa. Với logic build phức tạp, nên tạo custom task type có input/output rõ ràng thay vì dồn nhiều logic vào closure trong build script.

Không nên thực hiện công việc nặng ngay trong phần cấu hình task. Phần cấu hình được đánh giá khi Gradle tạo build model. Công việc thực thi nên nằm trong task action hoặc công cụ được task gọi.

## 11. Task inputs và outputs

Gradle cần biết task đọc gì và tạo gì để hỗ trợ up-to-date checking và Build Cache.

Ví dụ custom task:

    abstract class GenerateGreeting extends DefaultTask {
        @Input
        abstract Property<String> getName()

        @OutputFile
        abstract RegularFileProperty getOutputFile()

        @TaskAction
        void generate() {
            File output = outputFile.get().asFile
            output.parentFile.mkdirs()
            output.text = "Hello, " + name.get()
        }
    }

    tasks.register('generateGreeting', GenerateGreeting) {
        name.set('Gradle')
        outputFile.set(layout.buildDirectory.file('generated/greeting.txt'))
    }

Input name là dữ liệu ảnh hưởng kết quả. OutputFile là file task tạo. Nếu name thay đổi, Gradle biết task cần chạy lại hoặc tìm cache entry tương ứng.

### Các annotation input/output thường gặp

| Annotation | Ý nghĩa |
| --- | --- |
| @Input | Giá trị input đơn giản |
| @InputFile | Một file input |
| @InputFiles | Tập hợp file input |
| @InputDirectory | Thư mục input |
| @OutputFile | Một file output |
| @OutputFiles | Tập hợp file output |
| @OutputDirectory | Thư mục output |
| @Classpath | Classpath input có quy tắc fingerprint phù hợp |
| @Nested | Nhóm thuộc tính lồng nhau |
| @Internal | Thuộc tính không tham gia fingerprint input/output |

Annotation phải phản ánh đúng công việc của task. Nếu task đọc file nhưng không khai báo input, Gradle có thể đánh giá sai trạng thái up-to-date hoặc cache. Nếu task ghi file nhưng không khai báo output, Gradle không thể quản lý output như mong đợi.

## 12. @CacheableTask và tính xác định

Task custom có thể được đánh dấu @CacheableTask nếu đầu ra là hàm xác định của các input đã khai báo và việc tái sử dụng output là an toàn.

Ví dụ:

    @CacheableTask
    abstract class GenerateGreeting extends DefaultTask {
        @Input
        abstract Property<String> getName()

        @OutputFile
        abstract RegularFileProperty getOutputFile()

        @TaskAction
        void generate() {
            File output = outputFile.get().asFile
            output.parentFile.mkdirs()
            output.text = "Hello, " + name.get()
        }
    }

Task không nên được cache nếu:

- Nó gửi email hoặc gọi API bên ngoài.
- Nó deploy lên server.
- Nó ghi dữ liệu vào database.
- Nó phụ thuộc thời gian hiện tại nhưng không khai báo input.
- Nó đọc dữ liệu mạng thay đổi mà không khai báo.
- Nó có side effect cần thực hiện ở mọi lần build.

Nếu task được cache, Gradle có thể bỏ qua action khi tìm được cache entry. Vì vậy, chỉ những task tạo output có thể tái sử dụng mới nên được cache.

## 13. Plugin là gì?

Plugin là thành phần mở rộng Gradle. Plugin có thể:

- Đăng ký task.
- Tạo extension để cấu hình.
- Tạo dependency configuration.
- Thiết lập source set.
- Cấu hình compiler, test và packaging.
- Áp dụng quy ước cho project.
- Kết nối task với lifecycle.
- Thêm rule hoặc capability cho dependency resolution.

Ví dụ Java Plugin thêm các task compileJava, processResources, classes, jar, test và javadoc. Người dùng không cần tự viết các task này từ đầu.

Plugin đóng gói quy ước để nhiều project có thể dùng chung một cách nhất quán.

## 14. Plugin core, community và plugin tự viết

Có thể chia plugin thành các nhóm:

### Core plugins

Được Gradle cung cấp và có thể áp dụng mà không cần khai báo version từ plugin portal:

    plugins {
        id 'java'
        id 'application'
    }

Ví dụ:

- java: hỗ trợ build Java cơ bản.
- java-library: hỗ trợ tạo thư viện Java và API/implementation separation.
- application: cấu hình ứng dụng có main class và task run.
- base: cung cấp một số task lifecycle cơ bản.
- maven-publish: publish publication lên Maven repository.

### Community plugins

Được phát triển bởi Gradle community hoặc bên thứ ba, thường được phân phối qua Gradle Plugin Portal hoặc repository plugin khác.

Ví dụ cấu hình:

    plugins {
        id 'com.example.quality' version '1.2.0'
    }

Version plugin cần được cố định để build có thể tái lập và tránh thay đổi hành vi ngoài ý muốn.

### Custom plugin

Tổ chức có thể viết plugin nội bộ để chuẩn hóa cấu hình Java, test, compiler, quality gate hoặc publication giữa nhiều project.

Custom plugin phù hợp khi logic cấu hình được dùng lặp lại và có quy ước ổn định. Không nên tạo plugin chỉ để bọc một vài dòng cấu hình đơn giản nếu chưa có nhu cầu tái sử dụng.

## 15. Áp dụng plugin bằng plugins DSL

Cách hiện đại thường dùng:

    plugins {
        id 'java'
        id 'application'
    }

Kotlin DSL:

    plugins {
        java
        application
    }

Với plugin ngoài:

    plugins {
        id 'org.springframework.boot' version '3.3.2'
    }

Kotlin DSL:

    plugins {
        id("org.springframework.boot") version "3.3.2"
    }

plugins DSL khai báo plugin ở đầu build script và giúp Gradle xử lý plugin resolution theo một quy tắc rõ ràng.

### apply false

Ở root project, có thể khai báo version plugin nhưng chưa áp dụng:

    plugins {
        id 'org.springframework.boot' version '3.3.2' apply false
    }

Sau đó subproject cần plugin mới áp dụng:

    plugins {
        id 'org.springframework.boot'
    }

Điều này hữu ích trong multi-project build để quản lý version plugin tập trung mà không áp dụng plugin cho mọi project.

## 16. Plugin DSL và legacy apply plugin

Cách cũ:

    apply plugin: 'java'

Cách hiện đại:

    plugins {
        id 'java'
    }

plugins DSL có lợi thế về khai báo plugin rõ ràng, version resolution và hỗ trợ IDE tốt hơn. Một số plugin hoặc trường hợp đặc biệt có thể vẫn cần apply plugin hoặc cơ chế apply từ script plugin, nhưng nên ưu tiên plugins DSL khi có thể.

Không trộn nhiều cách áp dụng cùng một plugin một cách tùy tiện. Áp dụng trùng có thể gây cấu hình khó hiểu hoặc làm build script khó bảo trì.

## 17. Plugin repositories và dependency repositories

Plugin resolution và dependency resolution có thể sử dụng các repository khác nhau.

Plugin repository được cấu hình trong settings.gradle:

    pluginManagement {
        repositories {
            gradlePluginPortal()
            mavenCentral()
        }
    }

Dependency repository thường được cấu hình trong project:

    repositories {
        mavenCentral()
    }

Plugin DSL tìm plugin marker/artifact theo plugin resolution rules. Dependency repositories cung cấp thư viện mà ứng dụng sử dụng. Một repository có thể phục vụ cả hai vai trò nếu được cấu hình phù hợp, nhưng không nên nhầm hai cấu hình.

Với Kotlin DSL:

    pluginManagement {
        repositories {
            gradlePluginPortal()
            mavenCentral()
        }
    }

    dependencyResolutionManagement {
        repositories {
            mavenCentral()
        }
    }

Settings có thể quản lý repository ở cấp build để áp dụng chính sách thống nhất cho nhiều project.

## 18. Plugin tạo extension

Extension là đối tượng cấu hình có tên mà plugin thêm vào project. Người dùng tương tác với extension qua DSL.

Ví dụ Java Plugin tạo extension java:

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(21)
        }
    }

Application Plugin có extension application:

    application {
        mainClass = 'com.example.Main'
    }

Extension thường mô tả cấu hình cấp plugin hoặc một nhóm tính năng. Task thường mô tả công việc cụ thể.

Ví dụ:

- java extension cấu hình toolchain và source compatibility.
- application extension cấu hình main class và application distribution.
- publishing extension cấu hình publications và repositories.
- tasks.register đăng ký một công việc build cụ thể.

Không nên nhầm extension với task. Việc cấu hình extension thường ảnh hưởng đến cách plugin tạo/cấu hình nhiều task.

## 19. Dependency configuration và task configuration

Gradle dùng từ configuration ở hai ngữ cảnh:

1. Giai đoạn configuration của build.
2. Dependency configuration như implementation, runtimeOnly hoặc testImplementation.

Đây là hai khái niệm khác nhau.

Dependency configuration là một tập hợp dependency được resolve cho một mục đích cụ thể:

    dependencies {
        implementation 'org.slf4j:slf4j-api:2.0.16'
        testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    }

Task configuration là các thuộc tính và hành vi của task:

    tasks.named('test') {
        useJUnitPlatform()
        maxHeapSize = '1g'
    }

Build configuration là quá trình Gradle đánh giá các build script và tạo mô hình build.

Phân biệt đúng ba cách dùng giúp đọc build script và log chính xác hơn.

## 20. Java Plugin và các task được tạo

Khi áp dụng:

    plugins {
        id 'java'
    }

Gradle tạo source sets và các task phổ biến.

| Task | Vai trò |
| --- | --- |
| compileJava | Biên dịch source Java chính |
| processResources | Xử lý/copy resource chính |
| classes | Tổng hợp output của mã chính |
| compileTestJava | Biên dịch source test |
| processTestResources | Xử lý resource test |
| testClasses | Chuẩn bị output test |
| test | Chạy test |
| jar | Tạo JAR |
| javadoc | Tạo Javadoc |
| assemble | Tạo artifact |
| check | Chạy các kiểm tra |
| build | Tổng hợp assemble và check |

Tên task và cấu hình có thể được plugin khác mở rộng. Dùng:

    ./gradlew tasks

để xem task có thể gọi trong project.

Với task chi tiết:

    ./gradlew help --task test

Gradle hiển thị thông tin task nếu task tồn tại trong build.

## 21. Application Plugin

Application Plugin phù hợp với project có entry point để chạy ứng dụng Java.

Ví dụ:

    plugins {
        id 'application'
    }

    application {
        mainClass = 'com.example.Main'
    }

Task run có thể chạy ứng dụng với runtime classpath được cấu hình bởi plugin:

    ./gradlew run

Application Plugin cũng hỗ trợ tạo distribution chứa ứng dụng và dependency runtime:

    ./gradlew installDist
    ./gradlew distZip

Các task này giúp tạo gói chạy có cấu trúc và script khởi động. Nếu chạy bằng java -jar thủ công, cần hiểu cách artifact được đóng gói và classpath được thiết lập.

## 22. Java Library Plugin và API/implementation

Java Library Plugin:

    plugins {
        id 'java-library'
    }

Plugin này cung cấp cấu hình api và implementation để thể hiện dependency được công khai qua API của thư viện hay chỉ dùng nội bộ.

Ví dụ:

    dependencies {
        api 'com.example:public-contract:1.0.0'
        implementation 'com.example:internal-helper:2.0.0'
    }

api được dùng khi kiểu từ dependency là một phần API công khai mà consumer cần nhìn thấy trên compile classpath. implementation dùng cho dependency nội bộ của library.

Tách đúng API và implementation giúp giảm dependency bị lộ, giảm recompilation ở consumer và làm rõ hợp đồng thư viện.

Nếu dùng Java Plugin đơn giản, implementation vẫn là configuration phổ biến. Cấu hình api có ý nghĩa khi dùng Java Library Plugin.

## 23. Maven Publish Plugin

Plugin maven-publish cung cấp các task publish publication:

    plugins {
        id 'java-library'
        id 'maven-publish'
    }

    group = 'com.example'
    version = '1.0.0'

    publishing {
        publications {
            mavenJava(MavenPublication) {
                from components.java
            }
        }
        repositories {
            maven {
                url = uri(layout.buildDirectory.dir('repo'))
            }
        }
    }

Với cấu hình này, Gradle tạo publication từ Java component và có thể publish vào repository được cấu hình. Thông tin credentials trong môi trường thực tế cần lấy từ secret hoặc property được bảo vệ.

Các task publish được plugin tạo ra thường có tên dựa trên publication và repository. Dùng:

    ./gradlew tasks --all

để xem task publish cụ thể.

## 24. Custom task type

Khi logic build cần tái sử dụng, nên tạo task type thay vì lặp closure trong nhiều build script.

Ví dụ Groovy:

    abstract class GenerateVersionFile extends DefaultTask {
        @Input
        abstract Property<String> getVersionName()

        @OutputFile
        abstract RegularFileProperty getOutputFile()

        @TaskAction
        void generate() {
            File file = outputFile.get().asFile
            file.parentFile.mkdirs()
            file.text = versionName.get()
        }
    }

    tasks.register('generateVersionFile', GenerateVersionFile) {
        versionName.set(project.version.toString())
        outputFile.set(layout.buildDirectory.file('generated/version.txt'))
    }

Custom task type có thể được đặt trong:

- Build script cho logic nhỏ và cục bộ.
- buildSrc cho build logic được chia sẻ trong một build.
- Included build hoặc convention plugin build để tái sử dụng rõ ràng hơn.
- Plugin project riêng để publish hoặc dùng trong nhiều repository.

Với logic phức tạp, nên đặt task type trong source code có thể test, thay vì để build script ngày càng dài.

## 25. Plugin tự viết và Plugin interface

Một plugin Gradle thường triển khai Plugin<Project>:

    class GreetingPlugin implements Plugin<Project> {
        void apply(Project project) {
            project.tasks.register('greet') {
                group = 'Example'
                description = 'Prints a greeting.'
                doLast {
                    println 'Hello from custom plugin'
                }
            }
        }
    }

    apply plugin: GreetingPlugin

Ví dụ này minh họa cách plugin nhận Project và đăng ký task. Với plugin phân phối thực tế, nên dùng plugin ID, plugin marker và cấu trúc project phù hợp để consumer có thể áp dụng qua plugins DSL.

Plugin nên:

- Tạo extension cho cấu hình người dùng.
- Đăng ký task theo cách lazy.
- Dùng Provider API và task properties.
- Tránh đọc môi trường hoặc file ngoài mà không khai báo.
- Tránh truy cập Project từ task action.
- Đặt tên task và extension rõ ràng.
- Không áp đặt cấu hình ngoài phạm vi trách nhiệm của plugin.

## 26. Extension trong custom plugin

Plugin có thể tạo extension để người dùng cấu hình:

    class GreetingExtension {
        final Property<String> message

        GreetingExtension(ObjectFactory objects) {
            message = objects.property(String)
            message.convention('Hello')
        }
    }

    class GreetingPlugin implements Plugin<Project> {
        void apply(Project project) {
            def extension = project.extensions.create(
                'greeting',
                GreetingExtension,
                project.objects
            )

            project.tasks.register('greet') {
                doLast {
                    println extension.message.get()
                }
            }
        }
    }

Người dùng có thể cấu hình:

    greeting {
        message = 'Welcome'
    }

Trong plugin thực tế, task nên nhận giá trị từ extension qua task property được khai báo rõ, thay vì giữ tham chiếu extension/Project tùy ý trong action. Điều đó giúp task dễ cache và tương thích Configuration Cache hơn.

## 27. Groovy DSL và Kotlin DSL

Gradle hỗ trợ hai DSL chính:

- Groovy DSL dùng Groovy và thường có file .gradle.
- Kotlin DSL dùng Kotlin và file .gradle.kts.

Cả hai DSL cấu hình cùng mô hình Gradle. Khác biệt nằm ở cú pháp, kiểu dữ liệu, khả năng hoàn tất mã và cách IDE cung cấp hỗ trợ.

| Tiêu chí | Groovy DSL | Kotlin DSL |
| --- | --- | --- |
| File | build.gradle | build.gradle.kts |
| Cú pháp | Linh hoạt, dựa trên Groovy | Kiểu tĩnh, dựa trên Kotlin |
| IDE completion | Có, tùy mức hỗ trợ | Thường mạnh hơn nhờ kiểu tĩnh |
| Dấu ngoặc | Có thể lược bỏ nhiều trường hợp | Thường dùng ngoặc rõ ràng |
| String | Nháy đơn hoặc kép | Nháy kép phổ biến |
| Lambda | Closure | Lambda Kotlin |
| Dùng API Java | Thường ít cần import rõ | Có thể cần import hoặc type receiver rõ |

Không có DSL nào thay đổi bản chất task graph. Một project có thể dùng một DSL thống nhất; khi migration, nên đổi từng build script có kiểm soát và giữ cấu hình tương đương.

## 28. Ví dụ cấu hình plugin bằng Groovy DSL

build.gradle:

    plugins {
        id 'java'
        id 'application'
    }

    group = 'com.example'
    version = '1.0.0'

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(21)
        }
    }

    application {
        mainClass = 'com.example.Main'
    }

    repositories {
        mavenCentral()
    }

    dependencies {
        implementation 'org.slf4j:slf4j-api:2.0.16'
        testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    }

    tasks.named('test') {
        useJUnitPlatform()
    }

Ví dụ trên:

- Áp dụng Java và Application Plugin.
- Đặt group và version.
- Chọn toolchain JDK 21.
- Cấu hình main class.
- Khai báo repository.
- Khai báo dependency production và test.
- Cấu hình test task dùng JUnit Platform.

## 29. Ví dụ cấu hình plugin bằng Kotlin DSL

build.gradle.kts:

    plugins {
        java
        application
    }

    group = "com.example"
    version = "1.0.0"

    java {
        toolchain {
            languageVersion.set(JavaLanguageVersion.of(21))
        }
    }

    application {
        mainClass.set("com.example.Main")
    }

    repositories {
        mavenCentral()
    }

    dependencies {
        implementation("org.slf4j:slf4j-api:2.0.16")
        testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    }

    tasks.test {
        useJUnitPlatform()
    }

Kotlin DSL dùng accessor được tạo từ plugin và extension đã áp dụng. Nếu accessor chưa khả dụng do thứ tự hoặc plugin không được áp dụng tĩnh, có thể dùng API tasks.named hoặc extensions.configure với kiểu rõ ràng.

## 30. Provider API và Property

Provider API cho phép mô tả giá trị có thể được tính hoặc lấy sau, đồng thời truyền dữ liệu giữa các phần của build mà không cần đọc giá trị quá sớm.

Các kiểu thường gặp:

- Property<T>: một giá trị có thể cấu hình.
- RegularFileProperty: đường dẫn tới một file.
- DirectoryProperty: đường dẫn tới một thư mục.
- Provider<T>: nguồn cung cấp một giá trị.
- ListProperty<T> và SetProperty<T>: tập hợp giá trị.

Ví dụ:

    abstract class GenerateReport extends DefaultTask {
        @Input
        abstract Property<String> getTitle()

        @OutputFile
        abstract RegularFileProperty getReportFile()

        @TaskAction
        void generate() {
            File file = reportFile.get().asFile
            file.parentFile.mkdirs()
            file.text = title.get()
        }
    }

    tasks.register('generateReport', GenerateReport) {
        title.set('Build report')
        reportFile.set(layout.buildDirectory.file('reports/build.txt'))
    }

Provider giúp trì hoãn việc lấy giá trị và giữ quan hệ dữ liệu giữa task. Nó hỗ trợ configuration avoidance và Configuration Cache.

Không nên gọi get() quá sớm trong lúc cấu hình nếu không cần thiết. Truyền provider trực tiếp khi API cho phép để Gradle có thể đánh giá giá trị đúng thời điểm.

## 31. Tránh cấu hình task bằng cách truy cập Project trong action

Task action nên dựa vào các property được khai báo trên task. Ví dụ không tốt:

    tasks.register('printInfo') {
        doLast {
            println project.version
            println project.layout.projectDirectory
        }
    }

Action truy cập Project có thể gây vấn đề với Configuration Cache và làm task phụ thuộc ngầm vào trạng thái project.

Một hướng tốt hơn là truyền giá trị qua task property:

    abstract class PrintInfo extends DefaultTask {
        @Input
        abstract Property<String> getVersionText()

        @TaskAction
        void printInfo() {
            println versionText.get()
        }
    }

    tasks.register('printInfo', PrintInfo) {
        versionText.set(project.version.toString())
    }

Việc chuyển dữ liệu thành property giúp Gradle biết input và task dễ kiểm thử hơn. Với task cần file, dùng RegularFileProperty hoặc DirectoryProperty thay vì tự dựng đường dẫn trong action.

## 32. Plugin và lifecycle task

Plugin thường tạo task lifecycle để nhóm công việc:

- assemble: tạo artifact.
- check: thực hiện kiểm tra.
- build: thường phụ thuộc assemble và check.

Ví dụ Java Plugin:

    ./gradlew assemble
    ./gradlew check
    ./gradlew build

assemble tập trung vào artifact; check tập trung vào kiểm tra; build kết hợp cả hai. Plugin bổ sung có thể gắn task của nó vào check hoặc build.

Ví dụ task kiểm tra chất lượng có thể được nối vào check:

    tasks.named('check') {
        dependsOn tasks.named('verifyFormatting')
    }

Không nên gắn task nặng hoặc tác dụng phụ vào lifecycle chung nếu mọi build không cần nó. Hãy xác định mục tiêu của task và task selector phù hợp.

## 33. Task ordering không thay thế dependency dữ liệu

Nếu task B cần file do task A tạo, nên khai báo quan hệ dependency hoặc nối output provider, không chỉ đặt mustRunAfter.

Ví dụ:

    def generatedFile = layout.buildDirectory.file('generated/info.txt')

    def generateInfo = tasks.register('generateInfo') {
        outputs.file(generatedFile)
        doLast {
            generatedFile.get().asFile.text = 'ready'
        }
    }

    tasks.register('consumeInfo') {
        dependsOn(generateInfo)
        doLast {
            println generatedFile.get().asFile.text
        }
    }

Đây là ví dụ đơn giản. Trong custom task type, nên khai báo output property của task tạo và input property của task tiêu thụ để Gradle có thể truyền provider và theo dõi input/output chính xác.

mustRunAfter chỉ sắp thứ tự nếu cả hai task đã có trong graph. Nó không bảo đảm file đầu vào tồn tại.

## 34. Task graph và song song

Gradle có thể thực thi các task độc lập song song nếu build được cấu hình:

    ./gradlew build --parallel

hoặc:

    org.gradle.parallel=true

Task graph cần thể hiện chính xác dependency. Nếu một task đọc output của task khác nhưng không khai báo quan hệ, build có thể chạy sai thứ tự hoặc gặp lỗi race khi chạy song song.

Không nên dùng shared mutable file hoặc thư mục output chung cho nhiều task song song nếu không có cơ chế đồng bộ và ownership rõ ràng.

Task nên có output riêng và khai báo input/output đúng. Điều này hỗ trợ parallel execution, incremental build và cache.

## 35. Tổ chức build logic dùng chung

Khi nhiều project có cùng cấu hình, có thể chia sẻ logic bằng:

- Script plugin.
- buildSrc.
- Included build.
- Convention plugin.
- Plugin project riêng.

### Script plugin

Một file script có thể được áp dụng từ build script khác. Cách này phù hợp với logic nhỏ, nhưng khi số lượng script tăng, việc quản lý classpath và API có thể khó khăn.

### buildSrc

Thư mục buildSrc có thể chứa code build logic được biên dịch và đưa vào classpath của build. Nó thuận tiện cho logic dùng chung trong một repository.

### Included build

Included build cho phép tách build logic thành một build riêng và kết nối với build chính. Đây là cách thường dùng để phát triển convention plugin.

### Convention plugin

Convention plugin đóng gói quy ước như Java toolchain, test framework, compiler flags, lint và repository policy. Các project áp dụng plugin thay vì lặp cấu hình.

Ví dụ plugin nội bộ:

    plugins {
        id 'com.example.java-library-conventions'
    }

Một convention plugin nên tập trung vào một loại project hoặc một nhóm quy tắc rõ ràng.

## 36. Quản lý plugin version

Plugin version là một đầu vào quan trọng của build. Nếu không cố định version, build có thể thay đổi hành vi khi plugin được cập nhật.

Ví dụ:

    plugins {
        id 'com.example.quality' version '1.4.0'
    }

Trong multi-project build, có thể quản lý version ở root với apply false:

    plugins {
        id 'com.example.quality' version '1.4.0' apply false
    }

Subproject:

    plugins {
        id 'com.example.quality'
    }

Version catalog cũng có thể quản lý plugin alias:

    [plugins]
    quality = { id = "com.example.quality", version = "1.4.0" }

Trong build script:

    plugins {
        alias(libs.plugins.quality)
    }

Hãy kiểm tra cú pháp version catalog theo định dạng libs.versions.toml của dự án và tránh khai báo cùng plugin version ở nhiều nơi với giá trị khác nhau.

## 37. Plugin resolution và plugin marker

Với plugins DSL, Gradle thường phân giải plugin ID thông qua plugin marker artifact và repository được khai báo trong pluginManagement.

Settings:

    pluginManagement {
        repositories {
            gradlePluginPortal()
            maven {
                url = uri('https://repo.example.com/gradle-plugins/')
            }
        }
    }

Nếu plugin không tìm thấy:

- Kiểm tra plugin ID.
- Kiểm tra version.
- Kiểm tra pluginManagement repositories.
- Kiểm tra network/proxy/credentials.
- Kiểm tra plugin marker đã được publish hay chưa.
- Kiểm tra resolutionStrategy nếu tổ chức ánh xạ plugin ID sang module khác.

Plugin repository không tự động giống repository dependency. Một dependency có thể resolve được từ mavenCentral trong khi plugin ID vẫn không được tìm thấy nếu plugin repository chưa cấu hình đúng.

## 38. Debug task graph và task execution

Một số lệnh hữu ích:

    ./gradlew tasks
    ./gradlew tasks --all
    ./gradlew help --task test
    ./gradlew build --dry-run
    ./gradlew build --info
    ./gradlew build --stacktrace

- tasks liệt kê các task công khai.
- tasks --all bao gồm task phụ/ẩn hơn.
- help --task mô tả một task.
- --dry-run hiển thị task dự kiến mà không thực thi action.
- --info cung cấp thêm log.
- --stacktrace hiển thị stack trace khi có lỗi.

Dry-run không chứng minh task đã chạy hoặc output đã được tạo. Nó chỉ cho biết kế hoạch task ở mức phù hợp với chế độ dry-run.

Với build scan hoặc profile report, có thể phân tích thời gian cấu hình, thời gian task và cache. Hãy dùng công cụ được tổ chức cho phép và chú ý dữ liệu build scan có thể chứa thông tin môi trường.

## 39. Các lỗi thường gặp trong task configuration

### Task không được chạy

Nguyên nhân có thể là task không nằm trong graph, lệnh gọi sai project path hoặc chỉ có quy tắc ordering mà không có dependency.

Kiểm tra task selector, dependsOn và task graph.

### Task chạy trước khi file đầu vào được tạo

Task tiêu thụ file chưa khai báo dependency hoặc input provider. Khai báo output/input và quan hệ giữa task.

### Task luôn chạy lại

Input/output chưa khai báo đúng, output bị xóa, input thay đổi hoặc task có hành vi không xác định. Kiểm tra up-to-date log và task properties.

### Configuration Cache không tái sử dụng

Build script hoặc plugin truy cập API không tương thích, đọc dữ liệu cấu hình không được theo dõi hoặc có input configuration thay đổi. Đọc báo cáo Configuration Cache và dùng Provider API.

### Plugin không tìm thấy

Plugin repository, plugin ID hoặc version sai. Kiểm tra pluginManagement và plugin marker.

### Dependency có nhưng task không nhìn thấy

Dependency được khai báo trong configuration sai hoặc task không dùng classpath tương ứng. Kiểm tra compileClasspath/runtimeClasspath và task property.

### Build script quá dài và khó bảo trì

Logic dùng chung bị lặp hoặc task phức tạp được viết bằng nhiều closure. Tách thành convention plugin hoặc custom task type có API rõ.

## 40. Quy tắc chọn Groovy DSL hay Kotlin DSL

Có thể chọn DSL theo các tiêu chí:

### Groovy DSL phù hợp khi

- Repository hiện tại đã dùng Groovy DSL.
- Nhóm quen với Groovy và cần thay đổi nhỏ.
- Có nhiều build script hoặc plugin nội bộ dựa trên closure Groovy.
- Muốn tiếp tục theo cấu trúc hiện hữu mà không migration.

### Kotlin DSL phù hợp khi

- Nhóm sử dụng Kotlin thường xuyên.
- Muốn type-safe accessor và IDE completion tốt.
- Dự án mới muốn dùng DSL có kiểu tĩnh.
- Build logic cần refactor với sự hỗ trợ của compiler/IDE.

Kotlin DSL có thể cần thời gian biên dịch script và hỗ trợ IDE ban đầu; Groovy DSL linh hoạt hơn nhưng một số lỗi chỉ xuất hiện khi build chạy. Cả hai đều có thể tạo build nhanh và rõ nếu dùng API Gradle đúng cách.

Không nên chuyển DSL chỉ vì xu hướng. Nếu migration, hãy giữ hành vi build tương đương và thực hiện theo từng file/project.

## 41. Ví dụ multi-project với plugin và task

settings.gradle:

    rootProject.name = 'shop'
    include 'domain', 'application'

Root build.gradle:

    plugins {
        id 'base'
    }

    subprojects {
        repositories {
            mavenCentral()
        }
    }

domain/build.gradle:

    plugins {
        id 'java-library'
    }

    group = 'com.example.shop'
    version = '1.0.0'

application/build.gradle:

    plugins {
        id 'application'
    }

    dependencies {
        implementation project(':domain')
    }

    application {
        mainClass = 'com.example.shop.Main'
    }

Chạy:

    ./gradlew projects
    ./gradlew :domain:build
    ./gradlew :application:run
    ./gradlew build

Plugin của từng project tạo task và extension tương ứng. Dependency project(':domain') giúp Gradle thiết lập thứ tự build để application sử dụng output của domain.

## 42. Nguyên tắc thiết kế task tốt

- Một task nên có trách nhiệm rõ và tên mô tả hành động.
- Dùng task type khi logic cần tái sử dụng.
- Đăng ký task bằng tasks.register.
- Cấu hình task có sẵn bằng tasks.named hoặc configureEach.
- Khai báo đầy đủ input và output.
- Dùng Property, Provider, RegularFileProperty và DirectoryProperty.
- Không thực hiện công việc nặng trong giai đoạn configuration.
- Tránh truy cập Project từ task action.
- Không cache task có side effect hoặc input không xác định.
- Khai báo dependsOn khi task thực sự cần output của task khác.
- Không dùng mustRunAfter để thay thế dependency dữ liệu.
- Dùng output riêng để hỗ trợ parallel execution.
- Giữ task lifecycle gọn và dễ dự đoán.

## 43. Nguyên tắc thiết kế plugin tốt

- Plugin nên có một mục tiêu hoặc nhóm quy ước rõ ràng.
- Dùng extension để người dùng cấu hình thay vì hard-code.
- Đăng ký task lazy và không tạo task không cần thiết.
- Không tự ý ghi đè cấu hình consumer nếu không có lý do.
- Tách cấu hình plugin resolution và dependency resolution.
- Cố định version plugin.
- Dùng Provider API để nối dữ liệu.
- Viết task type có input/output rõ.
- Tương thích Configuration Cache nếu có thể.
- Tài liệu hóa task, extension và default values.
- Kiểm thử plugin trong project mẫu hoặc TestKit.

## 44. Tổng kết

Gradle xây dựng quá trình build từ task graph. Task mô tả công việc, input/output và quan hệ phụ thuộc; plugin bổ sung task, extension, dependency configuration và quy ước; Groovy DSL hoặc Kotlin DSL là cách khai báo mô hình đó trong build script.

Hiểu ba giai đoạn initialization, configuration và execution giúp xác định code nào chạy khi build được khởi tạo, task được cấu hình và task action được thực thi. Dùng tasks.register, tasks.named, configureEach và Provider API giúp trì hoãn công việc không cần thiết và hỗ trợ Configuration Cache. Khai báo input/output chính xác giúp up-to-date checking và Build Cache hoạt động an toàn.

Plugin nên đóng gói quy ước và tính năng có thể tái sử dụng. Extension cung cấp bề mặt cấu hình; task type chứa logic thực thi; plugin repositories phân giải plugin, còn dependency repositories phân giải thư viện ứng dụng. Groovy DSL và Kotlin DSL cùng cấu hình một mô hình Gradle, vì vậy lựa chọn dựa trên khả năng bảo trì và kỹ năng của nhóm. Khi task, plugin và DSL được thiết kế rõ ràng, build trở nên dễ đọc, dễ mở rộng, có thể tăng tốc và đáng tin cậy hơn.
