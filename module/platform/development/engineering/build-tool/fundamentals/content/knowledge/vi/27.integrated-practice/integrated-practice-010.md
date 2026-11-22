# Tự đánh giá khả năng đọc và giải thích một dự án build chưa quen

Khi nhận một repository Gradle chưa từng làm việc, mục tiêu đầu tiên không phải là nhớ hết mọi file hay chạy ngay mọi task. Mục tiêu là dựng được một mô hình đủ chính xác về cách dự án được cấu hình, dependency đi qua các project như thế nào, task nào tạo ra sản phẩm và lệnh nào được dùng trong CI.

Một người đọc build tốt có thể trả lời những câu hỏi thực tế:

- Đây là một Gradle build đơn hay build nhiều project?
- Phiên bản Gradle và JVM nào đang được yêu cầu?
- Plugin và build logic được lấy từ đâu?
- Source set, dependency và variant nào tạo nên compile/runtime classpath?
- Task graph của lệnh build chính gồm những bước nào?
- Output được tạo ở đâu và task nào sở hữu output đó?
- Test, package, publish và deploy được tổ chức ra sao?
- Những kết luận nào đã được xác nhận bằng file hoặc lệnh, và những điểm nào vẫn chỉ là giả thuyết?

Bài này đưa ra một phương pháp thực hành để đọc một dự án build chưa quen, từ việc định hướng repository đến việc giải thích toàn bộ luồng build bằng bằng chứng. Cuối bài có một bài tập mô phỏng và thang tự đánh giá để xác định phần kỹ năng đã vững và phần cần luyện thêm.

## 1. Đọc build như một hệ thống có nhiều lớp

Một dự án Gradle thường có nhiều lớp cấu hình. Nếu đọc file theo thứ tự ngẫu nhiên, rất dễ bỏ lỡ quan hệ giữa chúng.

Có thể chia việc tìm hiểu thành các lớp:

1. **Entry point:** Wrapper, Gradle version, JVM và lệnh build.
2. **Build structure:** settings, root project, subprojects và included builds.
3. **Build logic:** plugin, convention plugin, version catalog và buildSrc.
4. **Project model:** source set, configurations, dependencies và variants.
5. **Task model:** task registration, task graph, input/output và ordering.
6. **Deliverables:** classes, JAR/WAR, distributions, reports và publication.
7. **Automation:** CI workflow, cache, artifact handoff và release process.

~~~text
Developer / CI command
         |
         v
Gradle Wrapper + JVM
         |
         v
Settings and build structure
         |
         v
Plugins and convention build logic
         |
         v
Projects, source sets, configurations
         |
         v
Dependency and variant resolution
         |
         v
Task graph
         |
         v
Task inputs --> Task actions --> Task outputs
         |
         v
Tests / archives / reports / publications
         |
         v
CI artifacts and release
~~~

Mỗi lớp trả lời một nhóm câu hỏi. Chẳng hạn, settings cho biết project nào thuộc build; build script và plugin cấu hình các project; dependency declarations ảnh hưởng classpath; task graph cho biết các bước được chọn; task outputs và publication xác định sản phẩm cuối.

Không nên suy luận toàn bộ build chỉ từ một file build.gradle. Build logic có thể được đặt trong settings, convention plugin, included build hoặc plugin bên ngoài.

## 2. Bắt đầu từ repository và Wrapper

Trước khi đọc logic chi tiết, hãy xác định root của repository và những file chỉ dẫn cách build.

Các dấu hiệu thường gặp:

~~~text
repository/
  gradlew
  gradlew.bat
  gradle/
    wrapper/
      gradle-wrapper.jar
      gradle-wrapper.properties
  settings.gradle
  build.gradle
  gradle.properties
  gradle/
    libs.versions.toml
~~~

Không phải repository nào cũng có đủ các file trên. Kotlin DSL dùng settings.gradle.kts và build.gradle.kts. Một số project không có version catalog hoặc root build script.

### Wrapper cho biết Gradle distribution được chọn

Mở gradle/wrapper/gradle-wrapper.properties và tìm distributionUrl.

Ví dụ:

~~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
~~~~

Giá trị này cho biết Wrapper sẽ dùng Gradle distribution nào. Nó là bằng chứng quan trọng khi đọc plugin API, syntax và khả năng tương thích.

Ưu tiên Wrapper khi chạy build của repository:

~~~~shell
./gradlew --version
~~~~

Trên Windows:

~~~~powershell
.\gradlew.bat --version
~~~~

Kết quả giúp xác định Gradle version và JVM thực tế được dùng trong lần chạy. Đừng mặc định version Gradle cài toàn hệ thống là version của project.

### Phân biệt Wrapper với JVM

Wrapper chọn Gradle distribution. JVM chạy Gradle cần đáp ứng yêu cầu của Gradle version đó. Java toolchain có thể chọn JDK khác cho compile hoặc test.

Khi đọc project, ghi nhận riêng:

- Gradle Wrapper version.
- JVM chạy Gradle daemon.
- Java toolchain được cấu hình cho compile/test.
- JDK tối thiểu mà project tuyên bố hỗ trợ.
- JVM mà IDE hoặc CI runner sử dụng.

Một dòng java version trong terminal không tự chứng minh Gradle dùng cùng JDK. Hãy kiểm tra output của Wrapper và cấu hình liên quan.

### Đừng chạy build trước khi hiểu môi trường

Nếu project cần credential, service hoặc property nội bộ, một lệnh build toàn diện có thể thất bại vì thiếu điều kiện môi trường. Đầu tiên hãy đọc README hoặc hướng dẫn trong repository, sau đó chọn lệnh kiểm tra phù hợp.

## 3. Xác định root project và cấu trúc build

File settings.gradle hoặc settings.gradle.kts là điểm bắt đầu để hiểu build gồm những project nào.

Ví dụ:

~~~~groovy
rootProject.name = 'commerce-platform'

include 'domain'
include 'service'
include 'application'
include 'integration-tests'
~~~~

Cấu trúc thư mục có thể tương ứng:

~~~~text
commerce-platform/
  settings.gradle
  build.gradle
  domain/
    build.gradle
  service/
    build.gradle
  application/
    build.gradle
  integration-tests/
    build.gradle
~~~~

Từ đây có thể đưa ra giả thuyết ban đầu:

- domain chứa model hoặc API lõi.
- service phụ thuộc domain.
- application kết hợp các thành phần để chạy ứng dụng.
- integration-tests kiểm tra tích hợp.

Nhưng tên project không chứng minh trách nhiệm thực tế. Cần xác nhận qua build script, source tree, dependency declarations và task.

### Dùng lệnh projects

~~~~shell
./gradlew projects
~~~~

Lệnh này liệt kê root project và các subproject Gradle đã nhận diện. Nó hữu ích khi thư mục không phản ánh trực tiếp project path hoặc settings có ánh xạ projectDir tùy chỉnh.

Ví dụ settings có thể ánh xạ:

~~~~groovy
include 'domain'
project(':domain').projectDir = file('modules/core-domain')
~~~~

Project path là :domain, dù thư mục thật là modules/core-domain.

### Included build và composite build

Settings có thể include một build khác:

~~~~groovy
includeBuild('build-logic')
~~~~

Included build có lifecycle và settings riêng. Nó thường được dùng để phát triển convention plugin hoặc build logic dùng chung.

Khi thấy includeBuild, hãy xác định:

- Đường dẫn included build.
- Mục đích của build đó.
- Nó cung cấp plugin, dependency substitution hay component nào.
- Nó có được dùng trong build chính hoặc chỉ trong plugin management không.

Đừng nhầm included build với subproject. Subproject thuộc cùng Gradle build; included build là một build riêng được kết nối với build hiện tại.

### Dựng bản đồ project

Sau khi đọc settings và xem kết quả projects, tạo bảng tạm:

| Project path | Thư mục | Vai trò dự kiến | Bằng chứng cần tìm |
|---|---|---|---|
| :domain | domain/ | API/model lõi | Plugin, source, public types |
| :service | service/ | Logic nghiệp vụ | Dependency tới domain, task |
| :application | application/ | Ứng dụng chạy được | Application plugin, main class |
| :integration-tests | integration-tests/ | Kiểm thử tích hợp | Test source set, runtime dependency |

Đây là bản đồ để định hướng đọc, không phải kết luận cuối cùng.

## 4. Tìm build logic dùng chung

Trong dự án lớn, build.gradle của từng module có thể rất ngắn vì phần lớn logic được đưa vào plugin hoặc convention plugin.

Các vị trí nên tìm:

- buildSrc/
- build-logic/
- gradle/
- settings.gradle(.kts)
- pluginManagement trong settings
- plugins block trong từng project
- Included builds được khai báo trong settings

### BuildSrc

buildSrc là một build đặc biệt mà Gradle tự nhận diện để cung cấp build logic cho build chính. Nó có thể chứa plugin, task type, extension và helper code.

Ví dụ:

~~~~text
buildSrc/
  build.gradle.kts
  src/
    main/
      kotlin/
        JavaLibraryConventionPlugin.kt
~~~~

Nếu một project dùng:

~~~~kotlin
plugins {
    id("acme.java-library")
}
~~~~

nhưng không thấy plugin đó trong plugin portal hoặc plugin repository, hãy tìm trong buildSrc hoặc included build.

### Convention plugin

Convention plugin đóng gói cấu hình dùng chung, chẳng hạn:

- Java toolchain và compiler options.
- Test framework.
- Dependency constraints.
- Checkstyle hoặc static analysis.
- Publication metadata.
- Quy tắc source set.
- Cấu hình cache hoặc reproducibility.

Ví dụ plugin convention:

~~~~kotlin
class AcmeJavaLibraryPlugin : Plugin<Project> {
    override fun apply(project: Project) {
        project.pluginManager.apply("java-library")

        project.extensions.configure<JavaPluginExtension> {
            toolchain.languageVersion.set(
                JavaLanguageVersion.of(21)
            )
        }

        project.tasks.withType<JavaCompile>().configureEach {
            options.encoding = "UTF-8"
        }
    }
}
~~~~

Khi project áp dụng plugin này, một phần cấu hình không nằm trong build.gradle của project. Vì vậy, muốn giải thích compile behavior phải lần theo plugin implementation.

### Version catalog

File gradle/libs.versions.toml có thể tập trung version và alias dependency.

Ví dụ:

~~~~toml
[versions]
junit = "5.11.0"
slf4j = "2.0.16"

[libraries]
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
slf4j-api = { module = "org.slf4j:slf4j-api", version.ref = "slf4j" }

[plugins]
spring-boot = { id = "org.springframework.boot", version = "3.3.5" }
~~~~

Build script có thể dùng alias:

~~~~kotlin
dependencies {
    testImplementation(libs.junit.jupiter)
    implementation(libs.slf4j.api)
}
~~~~

Khi thấy alias, hãy lần về version catalog để xác định tọa độ và version thực tế. Nếu version được quản lý qua platform, constraint hoặc plugin logic, cần tiếp tục lần theo nguồn đó.

### Tìm nơi cấu hình version

Không phải version nào cũng nằm trong libs.versions.toml. Tìm cả:

- Plugin version trong settings hoặc plugins block.
- gradle.properties.
- Build logic convention.
- Platform/BOM.
- Dependency constraints.
- Dependency locking files.
- Version được truyền từ CI qua -P hoặc environment variable.

Mục tiêu là xác định version cuối cùng được resolve, không chỉ tìm chuỗi version đầu tiên xuất hiện.

## 5. Đọc plugin để hiểu khả năng của từng project

Plugin định hình nhiều phần của project model và lifecycle task.

Một số plugin thường gặp:

| Plugin | Điều thường cung cấp |
|---|---|
| java | Java source sets, compile/test/JAR tasks |
| java-library | Java library component và API/implementation configurations |
| application | Cấu hình main class và distribution/application tasks |
| war | WAR packaging |
| maven-publish | Publication và publish tasks |
| java-gradle-plugin | Cấu trúc phát triển Gradle plugin |
| jacoco | Coverage instrumentation/report tasks |
| checkstyle | Static analysis task |
| org.springframework.boot | Spring Boot packaging và boot tasks |
| base | Lifecycle tasks như clean, assemble, check |

Plugin bên thứ ba có thể thêm extension, configuration và task riêng.

### Phân biệt plugin được áp dụng trực tiếp và plugin được áp dụng qua convention

Ví dụ:

~~~~kotlin
plugins {
    id("acme.java-library")
}
~~~~

Project không viết id("java-library"), nhưng convention plugin có thể áp dụng nó. Khi đó các task compileJava, test và jar vẫn xuất hiện.

Để hiểu project, hãy đọc implementation của convention plugin hoặc tài liệu nội bộ tương ứng. Đừng kết luận rằng project không dùng Java plugin chỉ vì build.gradle không khai báo trực tiếp.

### Tìm plugin resolution

Plugin DSL có thể dùng repository được cấu hình trong settings:

~~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
~~~~

Nếu plugin không tìm thấy, kiểm tra pluginManagement và version trước. Dependency repository trong project không tự động thay thế plugin repository.

## 6. Đọc source tree và source sets

Sau khi hiểu project structure và plugin, xác định code được biên dịch từ đâu.

Với Java plugin, cấu trúc mặc định thường là:

~~~~text
src/
  main/
    java/
    resources/
  test/
    java/
    resources/
~~~~

Các source set bổ sung có thể được tạo:

~~~~text
src/
  integrationTest/
    java/
    resources/
  functionalTest/
    java/
    resources/
~~~~

Source set ảnh hưởng task compile, runtime classpath và output directory.

### Source set mặc định

| Source set | Source | Task thường gặp |
|---|---|---|
| main | src/main/java, src/main/resources | compileJava, processResources, classes |
| test | src/test/java, src/test/resources | compileTestJava, processTestResources, testClasses, test |

Tên và task có thể thay đổi theo plugin hoặc custom configuration.

### Source set bổ sung

Một project có thể khai báo integration test:

~~~~groovy
sourceSets {
    integrationTest {
        java.srcDir 'src/integrationTest/java'
        resources.srcDir 'src/integrationTest/resources'

        compileClasspath += sourceSets.main.output
        runtimeClasspath += output + compileClasspath
    }
}
~~~~

Đây mới là một phần cấu hình source set. Để chạy integration test đúng cách, project còn cần configuration dependency, Test task và quan hệ lifecycle tương ứng.

Khi đọc source set bổ sung, tìm:

- Source directories.
- Compile classpath.
- Runtime classpath.
- Dependency configurations.
- Task compile/test được tạo.
- Task nào gắn vào check hoặc build.
- Output directory và report location.

### Generated source

Source code có thể được tạo bởi task generator thay vì nằm trong repository.

Tìm:

- sourceSets hoặc java.srcDir.
- outputDirectory của generator.
- TaskProvider output được nối vào source set.
- Annotation processor.
- Code generation plugin.
- Thư mục build/generated.

Nếu generated source nằm trong build directory, hãy tìm task tạo nó. Không giả định file đã có sẵn trong checkout.

## 7. Hiểu dependency configurations

Khai báo dependency chỉ là điểm bắt đầu. Cần biết dependency phục vụ compile, runtime, test hay một mục đích khác.

Với Java Library plugin, các configuration thường gặp:

| Configuration | Vai trò khái quát |
|---|---|
| api | Dependency thuộc API được công bố cho consumer |
| implementation | Dependency phục vụ implementation |
| compileOnly | Cần khi compile nhưng không được đưa vào runtime classpath theo cách thông thường |
| runtimeOnly | Chỉ cần ở runtime |
| testImplementation | Dependency cho test compile/runtime |
| testRuntimeOnly | Dependency chỉ cần khi chạy test |
| annotationProcessor | Processor chạy trong compile |

Ví dụ:

~~~~kotlin
dependencies {
    api(project(":domain-api"))
    implementation(libs.slf4j.api)
    runtimeOnly(libs.postgresql)
    testImplementation(libs.junit.jupiter)
}
~~~~

Để giải thích classpath, cần biết configuration cụ thể chứ không chỉ đọc tên thư viện.

### api và implementation

Nếu public API của thư viện dùng type từ một dependency khác, dependency đó có thể cần được khai báo bằng api. implementation dành cho dependency nội bộ mà consumer không cần nhìn thấy trên compile API.

Cách chọn configuration ảnh hưởng cả compilation của consumer và metadata publication.

### Dependency graph

Dùng:

~~~~shell
./gradlew :application:dependencies --configuration runtimeClasspath
~~~~

Hoặc:

~~~~shell
./gradlew :application:dependencies --configuration compileClasspath
~~~~

Lệnh dependencies cho biết dependency tree của configuration được chọn.

Khi cần hiểu tại sao một version được chọn:

~~~~shell
./gradlew :application:dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~~

Dependency insight có thể chỉ ra:

- Dependency được yêu cầu từ đâu.
- Version nào được chọn.
- Conflict resolution.
- Constraint hoặc rule ảnh hưởng.
- Vì sao một version bị nâng hoặc hạ.

Không cần dump toàn bộ dependency graph ngay từ đầu. Chọn configuration liên quan đến câu hỏi đang điều tra.

### Project dependency

Trong multi-project build:

~~~~kotlin
dependencies {
    implementation(project(":domain"))
}
~~~~

Điều này tạo quan hệ component giữa project consumer và producer. Gradle chọn variant phù hợp và nối các task cần để tạo output component.

Project dependency khác với việc tự gọi task của project khác hoặc đọc file từ build directory của project khác.

## 8. Hiểu variants và attributes ở mức cần thiết

Gradle component có thể công bố nhiều variants. Mỗi variant mô tả cách component được sử dụng, ví dụ compile hoặc runtime, cùng attributes và artifact.

Một số attribute thường gặp:

- Usage: java-api hoặc java-runtime.
- Category: library, platform, documentation.
- LibraryElements: jar, classes hoặc dạng khác.
- Target JVM version.
- Bundling hoặc custom attributes.

Ví dụ một project Java library có thể cung cấp API variant và runtime variant. Consumer compile chọn API variant; runtime chọn runtime variant.

Nếu thấy lỗi no matching variant, cần đọc cả phía consumer và producer:

1. Consumer configuration yêu cầu attributes nào?
2. Producer có variants nào?
3. Attributes nào không tương thích?
4. Target JVM có phù hợp không?
5. Consumer có đang yêu cầu library, platform hay documentation không?

Đừng giải quyết variant mismatch bằng cách thêm JAR file path ngay lập tức. Làm vậy có thể bỏ qua metadata và dependency semantics của component.

## 9. Đọc task model và task graph

Sau khi hiểu project, plugin, source set và dependency, hãy xác định lệnh build chính tạo graph nào.

Liệt kê task:

~~~~shell
./gradlew :application:tasks --all
~~~~

Xem thông tin task:

~~~~shell
./gradlew help --task test
~~~~

Xem graph dự kiến:

~~~~shell
./gradlew :application:build --dry-run
~~~~

Task graph được tạo từ các task được yêu cầu và dependency của chúng. Task registration không có nghĩa task luôn chạy.

### Các quan hệ task quan trọng

| Cơ chế | Ý nghĩa |
|---|---|
| dependsOn | Thêm task producer/ prerequisite vào graph |
| Output Provider nối vào input | Consumer nhận dữ liệu và có thể suy ra producer |
| mustRunAfter | Chỉ ràng buộc thứ tự khi cả hai task đã được chọn |
| shouldRunAfter | Gợi ý thứ tự, có thể bị bỏ qua |
| finalizedBy | Thêm task kết thúc sau task được finalize |
| builtBy | Gắn producer với file collection |

Một trong những câu hỏi quan trọng khi đọc build là: nếu gọi task cuối trực tiếp, Gradle có tự đưa các bước tạo input vào graph không?

Nếu câu trả lời phụ thuộc vào việc developer chạy trước một lệnh khác trong shell, build model có thể chưa mô tả đủ quan hệ.

### Lifecycle task

Với Java plugin, các task như check, assemble và build gom nhiều bước:

- check thường gom các bước verification.
- assemble gom các artifact.
- build kết hợp verification và assemble.
- clean xóa output build của project.

Project có thể gắn task tùy chỉnh vào lifecycle:

~~~~groovy
tasks.named('check') {
    dependsOn tasks.named('verifySchema')
}
~~~~

Khi thấy task custom, hãy xác định nó có được gắn vào lifecycle hay chỉ chạy khi được gọi trực tiếp.

### Đọc output task

Tìm annotation hoặc cấu hình:

- @Input, @InputFile, @InputFiles, @InputDirectory.
- @OutputFile, @OutputDirectory.
- Task output properties.
- Provider wiring.
- builtBy.
- destinationDirectory và archive properties.

Các khai báo này giúp hiểu dữ liệu task tiêu thụ, output nằm ở đâu và producer nào cần chạy.

## 10. Truy vết một lệnh build từ đầu đến cuối

Đừng chỉ nói “build chạy compile rồi test”. Hãy chọn một lệnh thật và truy vết các bước cụ thể.

Ví dụ lệnh:

~~~~shell
./gradlew :application:build
~~~~

Một cách điều tra:

1. Xác nhận Wrapper và JVM.
2. Xác định project path :application.
3. Đọc plugin được áp dụng trực tiếp hoặc qua convention plugin.
4. Xác định source sets và dependency configurations.
5. Dùng --dry-run để xem graph dự kiến.
6. Dùng --info để quan sát task outcome và resolution.
7. Xác định task nào tạo JAR hoặc distribution.
8. Đọc output path và publication configuration nếu có.
9. Xác định CI job nào gọi lệnh và artifact nào được upload.

~~~text
:application:build
        |
        +--> :application:check
        |        |
        |        +--> :application:test
        |        +--> :application:checkstyleMain
        |        +--> :application:verifySchema
        |
        +--> :application:assemble
                 |
                 +--> :application:classes
                 |        |
                 |        +--> :application:compileJava
                 |        +--> :application:processResources
                 |
                 +--> :application:jar
~~~

Sơ đồ là ví dụ minh họa. Graph thật phải được xác nhận bằng task list, --dry-run hoặc build log của repository đang đọc.

### Phân biệt task graph với execution outcome

--dry-run cho biết task graph và thứ tự dự kiến, nhưng không chạy action. Khi build thật, một task có thể:

- SUCCESS: đã thực thi thành công.
- UP-TO-DATE: output hiện có còn hợp lệ.
- FROM-CACHE: output được khôi phục từ build cache.
- NO-SOURCE: không có source phù hợp.
- SKIPPED: bị bỏ qua theo điều kiện.
- FAILED: thực thi thất bại.

Một task xuất hiện trong graph không có nghĩa action của nó luôn chạy.

## 11. Lần theo input và output của một task quan trọng

Chọn một task đại diện, ví dụ compileJava, generateSources, test hoặc jar. Tìm hiểu:

- Nó đọc file nào?
- Nó nhận configuration/classpath nào?
- Nó dùng toolchain nào?
- Nó tạo output ở đâu?
- Task nào tạo các input được sinh tự động?
- Task nào tiêu thụ output của nó?
- Input/output có được khai báo để Gradle theo dõi không?

### Ví dụ compileJava

Với Java plugin, compileJava thường dùng:

- Source file trong main source set.
- Compile classpath.
- Compiler options.
- Java toolchain/compiler.
- Annotation processor path nếu có.

Output thường nằm trong:

~~~~text
build/classes/java/main/
~~~~

Task jar sau đó sử dụng classes và resources để tạo JAR:

~~~~text
build/libs/<archive-name>.jar
~~~~

Đây là output path mặc định thường gặp; project có thể thay đổi destination hoặc archive naming.

### Ví dụ task generator

Nếu compileJava cần generated source, hãy tìm task tạo generated source và cách source set nhận output provider.

Một mô hình đúng thường có dạng:

~~~text
schema files
     |
     v
generateSources
     |
     v
generated source directory
     |
     v
compileJava
     |
     v
class files
~~~

Nếu generator chỉ được chạy trước bằng shell script mà không được nối vào Gradle graph, gọi compileJava trực tiếp có thể thất bại.

## 12. Hiểu test strategy

Một dự án có thể có nhiều loại test:

- Unit test.
- Integration test.
- Functional test.
- Contract test.
- End-to-end test.
- Test chạy trên nhiều JDK hoặc OS.

Tìm source set, Test task, test framework và lifecycle wiring.

### Test task mặc định

Với Java plugin, test thường dùng test source set và chạy trên runtime classpath của test.

Có thể chạy riêng:

~~~~shell
./gradlew :application:test
~~~~

Xem test report thường ở:

~~~~text
build/reports/tests/test/
build/test-results/test/
~~~~

Đường dẫn cụ thể có thể được tùy chỉnh.

### Integration test riêng

Nếu project có integrationTest, hãy tìm:

- Integration test source set.
- Configuration dependency.
- Test task riêng.
- Runtime classpath.
- Test task có gắn vào check không.
- Service hoặc container cần thiết.
- System property và environment variable.

Không giả định một source directory tên integrationTest tự động được chạy. Cần tìm task và quan hệ lifecycle.

### Test có thể phụ thuộc môi trường

Một integration test có thể cần database, message broker hoặc endpoint. Khi build thất bại, phân biệt lỗi assertion/code với lỗi không khởi động được service.

Đọc Test task configuration, test logs và CI service declarations để hiểu điều kiện thực thi.

## 13. Tìm sản phẩm đầu ra và publication

Một project build thành công có thể tạo nhiều loại output:

- JAR/WAR.
- ZIP/TAR distribution.
- Executable.
- Generated source.
- Test report.
- Coverage report.
- POM/Gradle Module Metadata.
- Container image.
- SBOM hoặc checksum.

Tìm plugin và task tạo chúng. Ví dụ:

| Output | Dấu hiệu cần tìm |
|---|---|
| JAR | Java plugin, jar task |
| WAR | War plugin, war task |
| Executable Spring Boot JAR | Spring Boot plugin, bootJar |
| Distribution ZIP/TAR | Application plugin, distZip/distTar |
| Test report | Test task, reports configuration |
| Coverage | JaCoCo plugin, jacocoTestReport |
| Maven publication | maven-publish, publishing block |
| Gradle plugin | java-gradle-plugin, plugin marker publication |

### Publication không đồng nghĩa artifact local

Nếu thấy maven-publish, đọc:

- Publication name.
- Component hoặc artifact được publish.
- Group, artifact, version.
- Repository đích.
- Credential source.
- Publish task.
- Signing hoặc metadata configuration nếu có.

Build task jar tạo file trong workspace. Publish task chuyển publication đến repository. Hai bước khác nhau.

### Tìm output path thực tế

Không nên chỉ dựa vào quy ước mặc định. Tìm:

- destinationDirectory.
- archiveFileName.
- archiveBaseName.
- archiveVersion.
- archiveClassifier.
- outputFile/outputDirectory của custom task.
- buildDir hoặc layout.buildDirectory override.

Một project có thể thay output path để phù hợp với packaging hoặc CI.

## 14. Đọc CI để biết build được dùng như thế nào

CI workflow cho biết lệnh nào thực sự được chạy trong môi trường tự động.

Tìm file trong các vị trí thường gặp:

~~~text
.github/workflows/
.gitlab-ci.yml
Jenkinsfile
azure-pipelines.yml
.circleci/
buildkite/
~~~

Không phải dự án nào cũng dùng cùng nền tảng.

### Các câu hỏi cần trả lời

- CI chạy trên OS/image nào?
- JDK nào được cài và chọn?
- Dùng Wrapper hay Gradle cài sẵn?
- Lệnh build chính là gì?
- Có truyền project property hoặc environment variable không?
- Cache nào được restore/save?
- Test nào chạy?
- Artifact nào được upload?
- Có publish/deploy không?
- Release có approval hoặc branch/tag condition không?

### Phân biệt cache với artifact

CI cache thường dùng để tăng tốc, ví dụ giữ Gradle dependency cache. CI artifact dùng để bàn giao file cụ thể giữa jobs hoặc giữ kết quả của pipeline run.

Nếu deploy job cần JAR, hãy tìm upload/download artifact hoặc package repository. Không giả định deploy job sẽ tìm được JAR trong Gradle cache.

### Lần theo job dependency

Ví dụ workflow:

~~~text
build
  |
  v
upload application.jar
  |
  +----------+
  |          |
  v          v
integration  package-scan
test         |
  |          |
  +----+-----+
       |
       v
   release gate
       |
       v
     deploy
~~~

Đây là mô hình minh họa. Job graph thật phải được đọc từ workflow configuration.

## 15. Đọc properties và environment mà build yêu cầu

Build script có thể đọc property:

~~~~groovy
def target = providers.gradleProperty('targetEnvironment')
    .orElse('local')
~~~~

CI có thể truyền:

~~~~shell
./gradlew build -PtargetEnvironment=staging
~~~~

Tìm các property trong:

- gradle.properties của repository.
- Gradle User Home properties.
- CI workflow variables.
- Environment variable.
- Command line -P.
- Convention plugin.
- Settings script.

Không đọc hoặc in secret ra log. Khi cần hiểu credential, chỉ xác định tên biến và nơi được cấp, không tiết lộ giá trị.

### Phân biệt project property và environment variable

Project property thường được đọc qua providers.gradleProperty hoặc project.findProperty. Environment variable được đọc qua providers.environmentVariable hoặc System.getenv.

Hai loại có scope và nguồn cấp khác nhau. Nếu build chỉ chạy trong CI, hãy tìm workflow variable tương ứng trước khi kết luận giá trị mặc định.

## 16. Kiểm tra cấu hình repository và dependency resolution

Một dự án có thể dùng nhiều repository cho nhiều mục đích:

- Plugin repository trong pluginManagement.
- Dependency repository trong dependencyResolutionManagement hoặc repositories.
- Legacy buildscript repository.
- Publishing repository.
- Repository nội bộ.

Khi dependency resolve thất bại, xác định đúng configuration và đúng loại repository.

### Đọc repository declarations

Ví dụ:

~~~~kotlin
dependencyResolutionManagement {
    repositories {
        mavenCentral()
        maven {
            url = uri("https://repo.example.internal/releases")
        }
    }
}
~~~~

Settings có thể kiểm soát repository cho các project. Nếu repositoriesMode được cấu hình, repository khai báo trong project có thể bị hạn chế hoặc từ chối.

### Không nhầm repository resolve với repository publish

~~~~groovy
repositories {
    mavenCentral()
}
~~~~

dùng để resolve dependency trong project.

~~~~groovy
publishing {
    repositories {
        maven {
            url = uri("https://repo.example.internal/releases")
        }
    }
}
~~~~

dùng để publish artifact.

Một repository xuất hiện trong publishing không tự động trở thành dependency repository và ngược lại.

## 17. Kiểm tra cache và tính tái lập

Khi đọc build chưa quen, cần hiểu cache được dùng ở lớp nào:

- Dependency cache: metadata và artifact dependency.
- Up-to-date checking: output hiện có của task khi input không đổi.
- Build cache: output task được lưu theo cache key.
- Configuration cache: kết quả cấu hình build.

Tìm:

- org.gradle.caching.
- org.gradle.configuration-cache.
- buildCache trong settings.
- CI cache key và paths.
- Task cacheability annotation.
- Input/output declaration.

Không kết luận build reproducible chỉ vì có build cache. Tính tái lập phụ thuộc input đầy đủ, toolchain, dependency version, môi trường và hành vi task.

### Các lệnh hữu ích

~~~~shell
./gradlew build --info
./gradlew build --build-cache --info
./gradlew build --no-build-cache
./gradlew build --offline
~~~~

Chọn lệnh theo câu hỏi. Không chạy tùy chọn thay đổi hành vi nếu chưa hiểu tác động của nó đến môi trường hoặc output.

## 18. Đọc lỗi theo giai đoạn

Khi thử một lệnh và build thất bại, xác định giai đoạn trước khi sửa.

| Dấu hiệu | Nơi bắt đầu điều tra |
|---|---|
| Wrapper không tải distribution | URL, proxy, TLS, Gradle User Home |
| JVM không khởi động | JAVA_HOME, Gradle JVM, Gradle version |
| Settings/project path lỗi | settings.gradle(.kts), included build |
| Plugin không tìm thấy | pluginManagement, plugin ID/version |
| Build script lỗi | DSL, plugin implementation, property |
| Dependency không resolve | Coordinates, repository, credentials |
| No matching variant | Consumer/producer attributes |
| Compile error | Source, classpath, toolchain, generated source |
| Test failure | Test report, test runtime, service dependency |
| Task không ghi được file | Output path, permission, file lock |
| Publish thất bại | Publication, repository, credential, signing |

Dùng stacktrace và info log:

~~~~shell
./gradlew :application:build --stacktrace
./gradlew :application:build --info --stacktrace
~~~~

Đọc phần What went wrong và các dòng Caused by. Task path trong log là nơi lỗi được báo; exception mới giúp xác định nguyên nhân.

## 19. Một quy trình đọc repository có giới hạn và có bằng chứng

Khi nhận repository mới, không cần đọc tất cả file ngay lập tức. Hãy đi theo câu hỏi đang cần trả lời.

### Vòng 1 — Định hướng

1. Xác định repository root.
2. Đọc Wrapper properties.
3. Đọc settings.
4. Liệt kê project bằng lệnh projects.
5. Tìm buildSrc và included build.
6. Xác định build script của root và các project chính.

Kết quả mong muốn: biết build gồm những phần nào và build logic được đặt ở đâu.

### Vòng 2 — Hiểu cấu hình

1. Đọc plugin của project quan trọng.
2. Lần convention plugin nếu có.
3. Đọc version catalog và properties.
4. Xác định source sets.
5. Đọc dependency configurations.
6. Kiểm tra repository và variant nếu cần.

Kết quả mong muốn: biết code nào được build, dependency nào được dùng và cấu hình đến từ đâu.

### Vòng 3 — Hiểu execution

1. Xác định lệnh build chính từ README/CI.
2. Liệt kê task liên quan.
3. Xem task graph bằng dry-run.
4. Chọn task quan trọng và lần input/output.
5. Xác định test, package và report.
6. Kiểm tra cache/outcome nếu cần.

Kết quả mong muốn: có thể mô tả thứ tự thực thi và output của build.

### Vòng 4 — Hiểu delivery

1. Xác định artifact được tạo.
2. Tìm upload/download giữa CI jobs.
3. Tìm publication/deploy tasks.
4. Xác định version và commit identity.
5. Tìm release condition và approval.

Kết quả mong muốn: biết binary đi từ source đến người nhận như thế nào.

### Ghi lại bằng chứng

Với mỗi kết luận, ghi file hoặc lệnh đã chứng minh nó.

| Kết luận | Bằng chứng |
|---|---|
| Build có 4 subprojects | settings.gradle và output projects |
| Dùng Gradle 8.x | gradle-wrapper.properties và --version |
| Java toolchain 21 | Convention plugin hoặc Java extension |
| :app phụ thuộc :domain | build.gradle của :app và dependency report |
| check chạy integration test | Task wiring và dry-run graph |
| JAR được upload trong CI | Workflow upload-artifact step |
| Release publish lên Maven repository | publishing block và CI publish command |

Phân biệt rõ ba trạng thái:

- **Đã xác nhận:** có bằng chứng trực tiếp.
- **Suy luận hợp lý:** có một số dấu hiệu nhưng chưa kiểm chứng đầy đủ.
- **Chưa biết:** chưa tìm thấy bằng chứng.

Điều này giúp giải thích trung thực và tránh biến tên thư mục hoặc tên task thành sự thật chưa được xác nhận.

## 20. Viết bản giải thích dự án cho người khác

Sau khi đọc, thử giải thích dự án bằng cấu trúc ngắn gọn nhưng đủ thông tin.

### A. Tổng quan

- Dự án giải quyết vấn đề gì?
- Root project và các module chính là gì?
- Build được gọi bằng lệnh nào?
- Gradle/JDK version nào được yêu cầu?

### B. Build logic

- Plugin nào được áp dụng?
- Convention plugin nằm ở đâu?
- Version catalog và properties quản lý gì?
- Repository nào được dùng để resolve plugin/dependency?

### C. Dependency và source

- Source set chính là gì?
- Module phụ thuộc nhau ra sao?
- Dependency compile/runtime/test được khai báo thế nào?
- Có generated source hoặc annotation processor không?

### D. Task flow

- Lệnh build chính chọn task nào?
- Task graph có những nhánh nào?
- Verification được gắn vào đâu?
- Output được tạo bởi task nào?

### E. Delivery

- Artifact nào được tạo?
- File nằm ở đâu?
- CI upload artifact nào?
- Publish/deploy được kích hoạt trong điều kiện nào?

### F. Rủi ro hoặc điểm chưa rõ

- Có dependency version động không?
- Có property/secret cần môi trường nội bộ không?
- Có task phụ thuộc trạng thái bên ngoài không?
- Có module hoặc plugin chưa hiểu rõ không?

Một lời giải thích tốt cho biết cả điều đã xác nhận và giới hạn của việc tìm hiểu. Không cần mô tả từng task không liên quan đến luồng build chính.

## 21. Bài tập thực hành: nhận một repository Gradle chưa quen

Giả sử bạn được giao một repository có cấu trúc:

~~~~text
store-platform/
  gradlew
  gradlew.bat
  gradle/
    wrapper/
      gradle-wrapper.properties
    libs.versions.toml
  settings.gradle.kts
  build.gradle.kts
  build-logic/
  domain/
    build.gradle.kts
    src/main/java/
  persistence/
    build.gradle.kts
    src/main/java/
  application/
    build.gradle.kts
    src/main/java/
    src/test/java/
  acceptance-tests/
    build.gradle.kts
    src/acceptanceTest/java/
  .github/workflows/
    build.yml
    release.yml
~~~~

Bạn chưa biết dự án. Không giả định vai trò module chỉ từ tên. Thực hiện các phần sau.

### Nhiệm vụ 1 — Xác định build structure

Trả lời:

1. Root project tên gì?
2. Có bao nhiêu subproject?
3. Có included build không?
4. Project path nào ánh xạ tới thư mục nào?
5. Build logic dùng chung nằm ở đâu?

Bằng chứng cần có: settings file, cấu trúc thư mục và output projects.

### Nhiệm vụ 2 — Xác định môi trường

Trả lời:

1. Gradle Wrapper dùng version nào?
2. JVM chạy Gradle là gì?
3. Java toolchain có được cấu hình không?
4. Có property bắt buộc nào không?
5. CI dùng OS/image và JDK nào?

Bằng chứng cần có: Wrapper properties, --version, properties/convention plugin và workflow.

### Nhiệm vụ 3 — Dựng dependency map

Trả lời:

1. application phụ thuộc module nào?
2. persistence có phụ thuộc domain không?
3. Dependency nào là api, implementation, runtimeOnly?
4. Test framework được khai báo ở đâu?
5. Có dependency nào được quản lý qua platform hoặc version catalog?

Bằng chứng cần có: project build scripts, version catalog và dependency report.

### Nhiệm vụ 4 — Giải thích task graph

Chọn lệnh:

~~~~shell
./gradlew :application:build
~~~~

Trả lời:

1. Task graph có những task compile/test/package nào?
2. acceptance-tests có chạy trong lệnh này không?
3. Custom verification task được gắn vào lifecycle nào?
4. Nếu gọi :application:jar trực tiếp, producer cần thiết có được đưa vào graph không?
5. Task nào có thể up-to-date hoặc from-cache?

Bằng chứng cần có: task list, task wiring, dry-run và log khi build.

### Nhiệm vụ 5 — Truy vết deliverable

Trả lời:

1. Artifact cuối là JAR, WAR hay distribution?
2. Task nào tạo nó?
3. Output path và tên file thực tế là gì?
4. CI upload file nào?
5. Release workflow lấy đúng file nào để publish/deploy?

Bằng chứng cần có: archive task configuration, output file, workflow và publication block.

### Nhiệm vụ 6 — Viết bản giải thích

Viết một bản giải thích khoảng một đến hai trang, đủ để một developer mới biết:

- Cách khởi động build.
- Cấu trúc module.
- Dependency chính.
- Luồng task của lệnh build.
- Test và package.
- Artifact được bàn giao thế nào.
- Các yêu cầu môi trường và điểm còn chưa rõ.

Không cần đoán những điều không có bằng chứng. Ghi rõ câu hỏi còn mở.

## 22. Các câu hỏi tự kiểm tra sau khi đọc

Hãy tự trả lời mà không nhìn lại build script trước. Sau đó mở file/lệnh để kiểm tra bằng chứng.

1. Wrapper lấy Gradle distribution từ đâu?
2. Root build gồm những project path nào?
3. Included build khác subproject ở điểm nào?
4. Convention plugin nào cấu hình Java toolchain?
5. Dependency version được quản lý ở đâu?
6. Project nào cung cấp API mà application tiêu thụ?
7. Compile classpath khác runtime classpath như thế nào?
8. Generated source được tạo bởi task nào?
9. Task cuối có tự kéo producer vào graph không?
10. mustRunAfter khác dependsOn ra sao?
11. Input và output của task quan trọng là gì?
12. Test nào được chạy bởi check?
13. Artifact nào được tạo và ở đâu?
14. CI có upload artifact đó không?
15. Cache đang lưu dữ liệu gì?
16. Publish task đẩy artifact đến repository nào?
17. Lệnh nào giúp xem dependency insight?
18. Lệnh nào giúp xem task graph?
19. Nếu build chỉ lỗi trên CI, những khác biệt môi trường nào cần so sánh?
20. Có kết luận nào bạn đang suy đoán thay vì có bằng chứng?

Một câu trả lời chỉ được tính là vững khi bạn có thể giải thích vì sao và chỉ ra nơi xác nhận.

## 23. Thang tự đánh giá khả năng đọc build

Dùng thang điểm 0–3 cho từng năng lực:

- **0 — Chưa làm được:** không biết bắt đầu ở đâu hoặc chưa thể giải thích.
- **1 — Làm được khi có hướng dẫn:** tìm được file/lệnh sau khi được gợi ý.
- **2 — Tự làm được:** tự tìm ra và giải thích bằng bằng chứng.
- **3 — Giải thích và chẩn đoán được:** có thể hướng dẫn người khác, nhận ra giả định sai và truy vết lỗi.

| Năng lực | Điểm 0–3 | Bằng chứng nên có |
|---|---:|---|
| Đọc Wrapper và xác định Gradle/JVM |  | Wrapper properties, --version |
| Hiểu settings và project structure |  | settings, projects |
| Tìm convention plugin/build logic |  | buildSrc, included build, plugin source |
| Hiểu version catalog và properties |  | TOML, gradle.properties, CI variables |
| Đọc source sets |  | source directories, generated source |
| Hiểu dependency configurations |  | build scripts, dependency report |
| Hiểu variants/attributes cơ bản |  | module metadata hoặc variant error |
| Giải thích task graph |  | task list, dry-run |
| Truy vết input/output |  | Task properties, provider wiring |
| Hiểu test strategy |  | Test tasks, source sets, reports |
| Xác định deliverables |  | archive configuration và output |
| Đọc CI cache/artifact handoff |  | workflow configuration |
| Hiểu publication/release |  | publishing block và release job |
| Chẩn đoán lỗi theo giai đoạn |  | stacktrace, info log, dependency insight |
| Trình bày bằng chứng và điểm chưa rõ |  | bản giải thích có nguồn xác nhận |

Tổng điểm tối đa là 45.

### Diễn giải kết quả

| Tổng điểm | Mức tự chủ | Ý nghĩa |
|---:|---|---|
| 0–14 | Mới bắt đầu | Cần luyện định hướng repository và nhận diện các file cốt lõi |
| 15–25 | Đang hình thành | Có thể đọc từng lớp nhưng chưa nối được toàn bộ luồng |
| 26–35 | Tự chủ thực hành | Có thể giải thích build chính và điều tra nhiều vấn đề phổ biến |
| 36–41 | Vững | Có thể truy vết build logic phức tạp và trình bày bằng chứng rõ |
| 42–45 | Thành thạo | Có thể dẫn dắt người khác đọc build, chẩn đoán và đề xuất thay đổi có cơ sở |

Điểm số chỉ là công cụ định hướng học tập. Một điểm tổng cao không bù được một lỗ hổng nghiêm trọng ở năng lực quan trọng. Ví dụ, nếu chưa thể xác định đúng artifact được deploy, cần luyện phần delivery dù tổng điểm tốt.

## 24. Tự đánh giá bằng một lần giải thích không có ghi chú

Một bài kiểm tra hữu ích là giải thích build trong khoảng mười phút mà không mở file trong lúc trình bày. Sau đó mở repository để xác minh những điểm chưa chắc chắn.

Có thể dùng trình tự:

1. Mô tả root build và các module.
2. Nêu Gradle/JDK version.
3. Giải thích plugin và build logic dùng chung.
4. Mô tả dependency giữa các module.
5. Vẽ task graph cho lệnh build chính.
6. Chỉ ra input/output của một task tiêu biểu.
7. Giải thích test và package.
8. Nêu artifact được upload/publish/deploy.
9. Trình bày một rủi ro hoặc lỗi có thể xảy ra.
10. Chỉ ra bằng chứng và điểm chưa biết.

Nếu chỉ nhớ tên task nhưng không giải thích được task nhận input gì, tạo output nào và ai dùng output đó, bạn mới nhớ cấu trúc bề mặt. Nếu có thể truy vết được dữ liệu qua task graph và CI, bạn đã hiểu build như một hệ thống.

## 25. Dấu hiệu cho thấy bạn đang đọc build quá nông

Một số biểu hiện thường gặp:

- Chỉ đọc root build.gradle rồi kết luận cách mọi module hoạt động.
- Dựa vào tên thư mục để gán trách nhiệm mà không xem source/dependency.
- Không kiểm tra Wrapper version và JVM.
- Thấy alias dependency nhưng không lần về version catalog.
- Thấy task được đăng ký và cho rằng nó luôn chạy.
- Thấy mustRunAfter và cho rằng producer chắc chắn được chạy.
- Không tìm convention plugin nên bỏ lỡ phần cấu hình chính.
- Không kiểm tra source set bổ sung.
- Chỉ chạy build mà không đọc task graph.
- Thấy JAR trong build/libs và cho rằng nó đã được publish.
- Thấy CI cache và cho rằng deploy job dùng cache làm artifact.
- Đọc dòng lỗi cuối cùng mà bỏ qua Caused by.
- Trình bày giả thuyết như sự thật đã xác nhận.

Khi gặp những dấu hiệu này, quay lại câu hỏi: kết luận đó dựa trên file, task graph, output hay log nào?

## 26. Cách ghi chú để người khác có thể tiếp tục

Ghi chú đọc build nên đủ ngắn để tra cứu nhưng có đường dẫn đến bằng chứng.

Ví dụ:

~~~~markdown
# Build orientation

## Entry point
- Wrapper: Gradle 8.10.2
- Main command: ./gradlew build
- Gradle JVM: Java 21 (confirmed by --version)

## Structure
- Root: commerce-platform
- Projects: :domain, :service, :application
- Shared build logic: build-logic/

## Dependencies
- :service -> :domain
- :application -> :service
- Version aliases: gradle/libs.versions.toml

## Main flow
- :application:compileJava
- :application:test
- :application:jar
- Additional checks: verifySchema

## Deliverables
- JAR: application/build/libs/...
- CI upload: app-package
- Release publication: internal Maven repository

## Open questions
- Does the release job verify the checksum after download?
- Is integrationTest included in the default check lifecycle?
~~~~

Ví dụ này là định dạng ghi chú, không phải thông tin của một repository cụ thể. Thay từng mục bằng dữ liệu đã xác nhận.

### Ghi nguồn cho kết luận

Một ghi chú tốt nên kèm đường dẫn file hoặc lệnh xác nhận:

- settings.gradle.kts: project inclusion.
- build-logic/src/main/kotlin/...: convention plugin.
- application/build.gradle.kts: project dependency.
- --dry-run: task graph.
- CI workflow: artifact upload.
- dependencyInsight: selected version.

Khi build thay đổi, người đọc sau có thể kiểm tra lại nguồn thay vì tin một mô tả cũ.

## 27. Khi nào cần đào sâu và khi nào nên dừng?

Không phải task nào cũng cần đọc source code implementation. Chọn độ sâu theo câu hỏi.

**Chỉ cần định hướng** khi bạn cần biết project nào chịu trách nhiệm và lệnh build cơ bản.

**Cần đọc sâu build logic** khi plugin hoặc convention quyết định toolchain, dependency, source set hay task behavior.

**Cần xem task implementation** khi output, cacheability, input hoặc side effect chưa rõ.

**Cần xem dependency metadata** khi version conflict, variant mismatch hoặc publication behavior là trọng tâm.

**Cần xem CI** khi build local khác CI, artifact không được bàn giao hoặc release gate chưa rõ.

Dừng khi bạn có đủ bằng chứng để trả lời câu hỏi đang cần, biết những điểm còn mở và có thể chỉ ra bước tiếp theo để xác minh. Đọc mọi file trong repository không phải mục tiêu; hiểu đúng luồng liên quan mới là mục tiêu.

## 28. Lộ trình luyện tập để tăng mức tự chủ

Có thể luyện kỹ năng theo các repository tăng dần độ phức tạp:

### Mức 1 — Một project Java đơn giản

Tập trung:

- Wrapper.
- Một build script.
- Source sets main/test.
- compileJava, test, jar.
- Dependency configurations.
- Output directory.

Mục tiêu: giải thích được lệnh build và JAR được tạo như thế nào.

### Mức 2 — Multi-project build

Tập trung:

- settings và project paths.
- Project dependencies.
- API/implementation.
- Task graph liên project.
- Outgoing variants cơ bản.

Mục tiêu: giải thích được module nào cung cấp component cho module nào.

### Mức 3 — Build logic dùng chung

Tập trung:

- buildSrc hoặc included build.
- Convention plugins.
- Version catalog.
- Custom task types.
- Provider wiring.

Mục tiêu: truy được cấu hình thực tế dù nó không nằm trong build script của project.

### Mức 4 — CI và release

Tập trung:

- CI job graph.
- Cache và artifact.
- Test reports.
- Publication.
- Signing/provenance.
- Artifact promotion.

Mục tiêu: giải thích được đường đi từ source commit đến binary được phát hành.

### Mức 5 — Chẩn đoán và tối ưu

Tập trung:

- Stacktrace và --info.
- Dependency insight.
- Variant mismatch.
- Up-to-date checking và build cache.
- Configuration cache.
- Parallel execution và task isolation.

Mục tiêu: đưa ra giả thuyết có bằng chứng, cô lập nguyên nhân và giải thích tác động của thay đổi.

## 29. Bảng tra cứu nhanh

| Câu hỏi | File hoặc lệnh bắt đầu |
|---|---|
| Dùng Gradle version nào? | gradle-wrapper.properties, --version |
| Root build có project nào? | settings.gradle(.kts), projects |
| Build logic dùng chung ở đâu? | buildSrc, build-logic, includeBuild |
| Plugin được resolve từ đâu? | pluginManagement.repositories |
| Dependency version ở đâu? | libs.versions.toml, constraints, locking |
| Project dùng source nào? | sourceSets, src/, generated source |
| Dependency graph ra sao? | dependencies, dependencyInsight |
| Task nào được chọn? | tasks --all, --dry-run |
| Task nhận và tạo dữ liệu gì? | Task annotations, Provider, outputs |
| Test nào được chạy? | Test tasks, check wiring |
| JAR/ZIP nằm ở đâu? | jar/Zip task configuration, output files |
| Artifact được bàn giao ra sao? | CI upload/download steps |
| Package publish ở đâu? | publishing.repositories |
| Lỗi xảy ra ở giai đoạn nào? | --stacktrace, --info, Caused by |
| Build có dùng cache không? | gradle.properties, settings, task outcome |

## 30. Nguyên tắc tự đánh giá

Khả năng đọc một dự án build chưa quen không được đo bằng số file đã mở hoặc số task đã chạy. Nó được đo bằng khả năng dựng một mô hình đúng và giải thích mô hình đó bằng bằng chứng.

Bạn cần biết build bắt đầu từ đâu, project được cấu thành như thế nào, build logic đến từ đâu, dependency và source được đưa vào classpath ra sao, task graph được tạo thế nào và artifact đi đến người dùng bằng đường nào.

Khi có thể trả lời những câu hỏi đó, chỉ ra file/lệnh xác nhận và phân biệt rõ điều đã biết với điều chưa biết, bạn đã có thể tiếp nhận một repository Gradle mới một cách chủ động. Hãy dùng bài tập và thang tự đánh giá để xác định phần cần luyện tiếp, rồi lặp lại quy trình trên một dự án có cấu trúc khác.
