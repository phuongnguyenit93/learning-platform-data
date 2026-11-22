# Phân biệt thời gian cấu hình, tải phụ thuộc và thực thi tác vụ

Khi một lệnh build chạy lâu, không nên mặc định compiler hoặc test là nguyên nhân. Gradle và Maven đều thực hiện nhiều công việc: khởi tạo build, đọc cấu hình, tìm plugin, giải quyết dependency, tải artifact, lập kế hoạch công việc rồi thực thi compiler, test và đóng gói. Mỗi phần có nguyên nhân chậm và cách tối ưu khác nhau.

Bài học này phân biệt ba nhóm thời gian: **thời gian cấu hình**, **thời gian giải quyết/tải phụ thuộc**, và **thời gian thực thi tác vụ**. Chúng có liên quan nhưng không phải lúc nào cũng diễn ra tuần tự hoàn toàn. Dependency resolution có thể xảy ra khi Gradle cấu hình project hoặc khi task cần classpath; plugin và build logic cũng cần được resolve trước khi một số project được cấu hình. Muốn tối ưu đúng, cần xác định hoạt động nào đang tiêu tốn thời gian thay vì chỉ nhìn tổng thời gian build.

## 1. Ba loại thời gian trong một lần build

| Phần thời gian | Công việc điển hình | Dấu hiệu thường gặp |
|---|---|---|
| Configuration time | Khởi tạo build model, đọc settings/build script, áp dụng plugin, cấu hình task và tạo task graph | Chậm trước khi task bắt đầu; nhiều project hoặc build logic xử lý nặng |
| Dependency resolution/download time | Đọc metadata, chọn version, tải POM/module metadata/JAR/plugin artifact | Chờ repository hoặc mạng; lần đầu thường chậm hơn; log có hoạt động resolve/download |
| Task execution time | Biên dịch, chạy test, xử lý resource, đóng gói, tạo report | Task có thời gian thực thi lớn; CPU, I/O hoặc test process hoạt động |

Sơ đồ khái quát:

```text
Lệnh build
   |
   v
Khởi tạo và đọc cấu hình
   |
   v
Giải quyết dependency cần thiết
   |
   v
Lập task graph
   |
   v
Thực thi task
   |
   v
Kết quả build
```

Đây là cách phân loại để chẩn đoán, không phải mô tả cứng rằng dependency download luôn nằm giữa configuration và execution. Thời điểm resolve phụ thuộc build tool, plugin và cách build script truy cập dependency.

Ví dụ một lần chạy Gradle có thể mất 2 giây khởi tạo/cấu hình, 8 giây resolve và tải artifact chưa có trong cache, 20 giây compile/test và 3 giây tạo report. Tổng thời gian là 33 giây, nhưng tối ưu cần nhắm đúng phần chiếm thời gian.

Các con số chỉ minh họa. Build thật có thể chồng lấp I/O, daemon startup, worker và task execution nên không phải lúc nào cũng cộng thành ba khoảng độc lập.

## 2. Gradle build lifecycle

Gradle có ba phase lớn: Initialization, Configuration và Execution.

### Initialization

Gradle xác định build nào tham gia, đọc settings và tạo các project tương ứng. Với multi-project build, settings xác định root project, subprojects và included builds.

```groovy
rootProject.name = 'commerce'
include 'app', 'domain', 'infrastructure'
```

Trong initialization, Gradle có thể cần resolve plugin hoặc build logic được khai báo ở settings, plugin management hoặc included build. Vì vậy, build có thể mất thời gian trước khi task ứng dụng đầu tiên bắt đầu.

### Configuration

Gradle đánh giá build script và plugin để tạo mô hình project, cấu hình task, dependency và quan hệ giữa task.

```groovy
plugins {
    id 'java'
}

tasks.register('hello') {
    doLast {
        println 'Hello'
    }
}
```

Task được đăng ký/cấu hình trong configuration phase. Nội dung trong doLast là action của task và chỉ chạy khi task được đưa vào execution graph.

Nếu build script duyệt filesystem lớn, gọi process, truy vấn mạng hoặc resolve configuration eager trong lúc cấu hình, các hoạt động đó có thể kéo dài configuration time.

### Execution

Sau khi xác định task graph, Gradle thực thi những task cần chạy theo quan hệ dependency và ordering.

```bash
./gradlew :app:test
```

Gradle cấu hình build cần thiết, xác định task graph cho :app:test và các prerequisite, sau đó thực thi những task cần thiết. Không phải tất cả task đã đăng ký đều được thực thi.

### Dependency resolution không phải một phase cố định thứ tư

Initialization và configuration có ranh giới lifecycle rõ, nhưng dependency resolution có thể xảy ra ở nhiều thời điểm. Plugin resolution có thể diễn ra khi xử lý settings/build logic; project dependency có thể được resolve khi task cần compile/runtime classpath; build script eager có thể ép resolve sớm trong configuration.

Khi đo hiệu năng, nên ghi nhận hoạt động cụ thể và phase liên quan thay vì gán mọi thời gian tải dependency vào một khối cố định.

## 3. Dependency resolution khác artifact download

**Dependency resolution** là quá trình build tool xác định module và phiên bản nào đáp ứng yêu cầu trong dependency graph. Nó xem xét tọa độ, metadata, version constraints, platform/BOM, exclusions, variants, capabilities và dependency bắc cầu.

**Artifact download** là quá trình lấy file cần thiết từ repository, ví dụ POM, Gradle Module Metadata, JAR, ZIP hoặc plugin artifact.

Ví dụ:

```groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
}
```

Gradle cần xác định metadata của jackson-databind, biết các dependency liên quan, chọn version phù hợp và lấy artifact nếu chúng chưa có trong cache.

Một số trường hợp cần đọc metadata nhưng không cần tải lại JAR vì artifact đã có trong cache. Ngược lại, metadata hết hạn hoặc dynamic version cần kiểm tra lại có thể tạo request đến repository dù JAR cuối cùng không đổi.

| Thành phần | Nội dung thường chứa | Vai trò |
|---|---|---|
| POM | Coordinates, dependencies, scopes, metadata Maven | Mô tả artifact và dependency |
| Gradle Module Metadata | Variants, attributes, capabilities, constraints | Cung cấp thông tin module cho Gradle |
| JAR | Bytecode và resources | Được dùng khi compile hoặc runtime |
| Plugin artifact | Plugin implementation và dependency | Cung cấp logic build |
| Checksum/signature | Dữ liệu xác minh nội dung | Hỗ trợ xác thực artifact |

Lần đầu trên máy mới có thể phải tải wrapper distribution, plugin, build logic dependency, project dependency và metadata, rồi mới compile/test. Lần sau thường nhanh hơn nhờ cache. Nhưng build script, dependency, cache state hoặc task input thay đổi có thể khiến một phần công việc phải thực hiện lại.

## 4. Plugin resolution khác project dependency resolution

Cần phân biệt dependency của build logic với dependency của ứng dụng.

### Plugin resolution

Plugin cung cấp khả năng build:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
}
```

Gradle cần tìm plugin marker, implementation artifact và dependency của plugin. Quá trình này có thể diễn ra trước khi task ứng dụng được thực thi.

Repository plugin có thể được cấu hình trong settings:

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
```

Nếu plugin chưa có trong cache, repository chậm hoặc plugin kéo theo nhiều dependency, build có thể chậm ngay ở phần khởi tạo/cấu hình.

### Buildscript classpath

Build logic cũ hoặc một số plugin script có thể khai báo dependency qua buildscript classpath:

```groovy
buildscript {
    repositories {
        mavenCentral()
    }
    dependencies {
        classpath 'com.example:build-plugin:1.4.0'
    }
}
```

Đây là dependency phục vụ build script, khác với dependency runtime/compile của ứng dụng.

### Project dependencies

```groovy
dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.16'
}
```

Đây là dependency của source code hoặc runtime application. Nó thường được resolve khi một configuration như compileClasspath hoặc runtimeClasspath được sử dụng.

Nếu build mất thời gian trước task đầu tiên, kiểm tra plugin/build logic và configuration code. Nếu task compile bắt đầu rồi mới chờ tải JAR, xem project dependency resolution và repository.

## 5. Khi nào Gradle resolve dependency?

Gradle dùng configuration để mô tả nhóm dependency. Với Java plugin, các configuration thường gặp:

- compileClasspath: dependency cần cho biên dịch source chính.
- runtimeClasspath: dependency cần khi chạy source chính.
- testCompileClasspath: dependency cần khi biên dịch test.
- testRuntimeClasspath: dependency cần khi chạy test.

Dependency được khai báo không nhất thiết lập tức tải mọi artifact. Resolution thường diễn ra khi một configuration được yêu cầu ở trạng thái cần resolve, ví dụ task compiler cần compileClasspath.

Build script có thể ép resolution sớm:

```groovy
configurations.compileClasspath.files.each {
    println it
}
```

Truy cập files có thể làm Gradle resolve configuration ngay khi build script được đánh giá. Nếu thực hiện tương tự trên nhiều configuration hoặc nhiều project, configuration time có thể tăng mạnh.

Nên tránh resolve dependency eager khi không cần. Ưu tiên Provider, Configuration, FileCollection và task input để Gradle trì hoãn công việc đến khi cần.

Ví dụ task sử dụng runtime classpath:

```groovy
tasks.register('inspectLibraries') {
    inputs.files(configurations.runtimeClasspath)

    doLast {
        configurations.runtimeClasspath.files.each { file ->
            println file.name
        }
    }
}
```

Đây là ví dụ minh họa. Với custom task dùng lâu dài, nên khai báo property input có kiểu phù hợp và tránh truy cập project model không được hỗ trợ trong task action nếu cần configuration cache.

## 6. Cấu hình eager làm tăng configuration time

Một build script có thể thực hiện công việc nặng ngay khi Gradle cấu hình project, dù task liên quan không được chạy.

Ví dụ:

```groovy
// Chạy ngay trong configuration phase.
def allFiles = fileTree('src').files
println "Found " + allFiles.size() + " files"

tasks.register('countSources') {
    doLast {
        println allFiles.size()
    }
}
```

Truy cập fileTree.files ngay lúc cấu hình có thể duyệt filesystem lớn. Dù người dùng chỉ chạy một task khác, đoạn code vẫn làm chậm cấu hình.

Nên trì hoãn việc truy cập đến task action:

```groovy
tasks.register('countSources') {
    doLast {
        def allFiles = fileTree('src').files
        println "Found " + allFiles.size() + " files"
    }
}
```

Trong custom task thực tế, nên mô hình hóa source file bằng input property để Gradle biết task phụ thuộc vào dữ liệu nào:

```groovy
abstract class CountSources extends DefaultTask {
    @InputFiles
    abstract ConfigurableFileCollection getSources()

    @TaskAction
    void count() {
        println "Found " + sources.files.size() + " files"
    }
}

tasks.register('countSources', CountSources) {
    sources.from(fileTree('src'))
}
```

Cách này làm rõ input và giúp Gradle quản lý task tốt hơn.

## 7. Task execution không có nghĩa mọi task đều làm việc thật

Task có thể xuất hiện trong task graph nhưng không nhất thiết thực thi action.

| Trạng thái | Ý nghĩa |
|---|---|
| EXECUTED | Task đã thực thi action |
| UP-TO-DATE | Input/output phù hợp trạng thái đã ghi nhận; task không cần chạy lại |
| FROM-CACHE | Output được khôi phục từ build cache |
| NO-SOURCE | Không có source input phù hợp để xử lý |
| SKIPPED | Task bị bỏ qua do điều kiện hoặc cấu hình |
| FAILED | Task thực thi và thất bại |

Ví dụ:

```text
:compileJava UP-TO-DATE
:test FROM-CACHE
:jar SKIPPED
```

Build có thể nhanh vì compile output đã hợp lệ và test output được lấy từ cache. Nếu tổng thời gian vẫn cao, nút thắt có thể nằm ở configuration, dependency resolution hoặc task khác.

### Ba loại cache khác nhau

| Cache | Tái sử dụng điều gì? | Có thể giảm |
|---|---|---|
| Configuration cache | Kết quả cấu hình và task graph cho invocation phù hợp | Configuration time |
| Build cache | Output của task có thể cache | Task execution time |
| Dependency cache | Metadata và artifact dependency đã tải | Resolve/download time |

Bật build cache không tự làm build script cấu hình nhanh hơn. Bật configuration cache không tự tải sẵn mọi dependency. Dependency cache không thay thế output của compiler/test.

## 8. Configuration cache trong Gradle

Configuration cache lưu trạng thái cấu hình build để lần chạy sau có thể bỏ qua phần lớn việc đánh giá build script nếu điều kiện đầu vào phù hợp.

```bash
./gradlew test --configuration-cache
```

Lần đầu, Gradle cấu hình build và lưu cache entry. Lần sau, nếu build logic tương thích và input cấu hình không thay đổi, Gradle có thể tái sử dụng configuration cache.

Có thể bật qua gradle.properties:

```properties
org.gradle.configuration-cache=true
```

Khi settings, build script, plugin, version catalog hoặc input cấu hình được theo dõi thay đổi, cache có thể bị invalidated và Gradle phải cấu hình lại.

Những việc dễ cản trở configuration cache:

- Truy cập hoặc giữ object Gradle Project ở task action theo cách không được hỗ trợ.
- Dùng biến global mutable chia sẻ trạng thái giữa task.
- Gọi process hoặc đọc environment/configuration ngoài mô hình input được khai báo.
- Tạo side effect trong lúc cấu hình.
- Dùng plugin cũ không hỗ trợ configuration cache.

Hãy đọc thông báo Gradle và xử lý compatibility thay vì tắt cache ngay khi gặp vấn đề.

## 9. Dependency cache trong Gradle

Gradle lưu artifact và metadata trong cache người dùng, thường nằm dưới Gradle user home. Dependency cache có thể gồm:

- Metadata về module và version.
- Kết quả resolve dynamic version.
- Artifact đã tải như JAR, POM và module metadata.
- Thông tin repository và cache state.

Lần build trên máy đã có cache có thể không cần tải lại dependency. Một runner CI mới có thể phải tải nhiều artifact.

### Refresh dependency

```bash
./gradlew build --refresh-dependencies
```

Tùy chọn này yêu cầu Gradle làm mới trạng thái dependency cache và kiểm tra metadata/artifact cần thiết. Nó không đồng nghĩa mọi file JAR chắc chắn được tải lại nếu artifact hiện có vẫn khớp.

Đây là công cụ chẩn đoán hoặc cập nhật có chủ đích, không nên thêm vào mọi lệnh build thông thường vì có thể tăng truy cập mạng và thời gian build.

### Offline mode

```bash
./gradlew build --offline
```

Offline mode yêu cầu Gradle không truy cập mạng để resolve dependency. Build chỉ thành công nếu metadata và artifact cần thiết đã có trong cache. Nó hữu ích để kiểm tra build có phụ thuộc vào repository trong lần chạy đó không; nó không phải cách cập nhật dependency.

### Cache TTL

Gradle cache kết quả dynamic version và changing module theo khoảng thời gian. Với một project development cần nhận snapshot nhanh hơn, có thể cấu hình:

```groovy
configurations.configureEach {
    resolutionStrategy {
        cacheChangingModulesFor 10, 'minutes'
        cacheDynamicVersionsFor 30, 'minutes'
    }
}
```

Ví dụ này rút ngắn thời gian cache tương ứng. TTL quá thấp có thể khiến build liên tục hỏi repository, làm pipeline chậm và phụ thuộc mạng nhiều hơn. Chỉ thay đổi khi có nhu cầu thực tế và phạm vi rõ ràng.

## 10. Tải dependency bị chi phối bởi mạng và repository

Nếu log cho thấy build dừng lâu ở các request HTTP, nguyên nhân có thể là:

- Repository phản hồi chậm.
- DNS, proxy hoặc TLS handshake mất thời gian.
- Repository yêu cầu xác thực.
- Metadata bị kiểm tra lại thường xuyên.
- Có nhiều repository được thử lần lượt.
- Dynamic version hoặc snapshot cần kiểm tra cập nhật.
- Plugin hoặc build logic tải nhiều artifact.

Tăng số worker không giải quyết repository chậm. Tăng heap cũng không làm server Maven phản hồi nhanh hơn.

### Repository order và content filter

Nên khai báo repository cần thiết và giới hạn nội dung nếu phù hợp:

```groovy
repositories {
    mavenCentral()

    maven {
        url = uri('https://repo.example.com/releases')
        content {
            includeGroup 'com.example.internal'
        }
    }
}
```

Content filter giới hạn group nào được tìm trong repository nội bộ. Điều này giúp resolution rõ ràng hơn và giảm truy vấn nhầm nguồn. Cần bảo đảm chính sách không vô tình loại bỏ dependency cần thiết.

Tổ chức có thể dùng repository manager để proxy Maven Central và lưu cache artifact. Cách này giúp giảm latency, tăng độ ổn định khi upstream gián đoạn và kiểm soát nguồn dependency. Repository manager cần có chính sách retention, metadata, quyền truy cập và tính bất biến của release artifact.

## 11. Task execution bị giới hạn bởi CPU, I/O hoặc tiến trình ngoài

Sau khi task bắt đầu, thời gian thực thi có nhiều nguyên nhân:

- CPU-bound: compiler, xử lý bytecode, phân tích tĩnh.
- I/O-bound: đọc nhiều file, giải nén, copy resource.
- Process-bound: test worker, Docker, Node, compiler ngoài.
- Network-bound: integration test gọi dịch vụ từ xa.
- Contention: nhiều task cạnh tranh CPU, RAM, disk hoặc lock.

Test task chạy lâu không nhất thiết do dependency download. Nó có thể do test chờ database, HTTP server hoặc timeout.

Hãy xem task nào có thời gian lớn, process nào hoạt động và tài nguyên nào bị bão hòa trước khi tăng parallelism.

## 12. Parallel execution không sửa được mọi loại chậm

Gradle có thể chạy task độc lập song song khi task graph và cấu hình cho phép. Tuy nhiên, song song có thể làm tăng contention.

- Nếu CPU đang đầy, tăng worker có thể khiến từng task chậm hơn.
- Nếu disk quá tải, nhiều compiler/test cùng đọc ghi có thể làm I/O chậm.
- Nếu repository chậm, nhiều request đồng thời có thể tăng áp lực lên server.
- Nếu task phụ thuộc lẫn nhau, không thể chạy song song tùy ý.

Với multi-project build, có thể bật parallel project execution:

```properties
org.gradle.parallel=true
```

Hoặc:

```bash
./gradlew build --parallel
```

Chỉ nên bật sau khi xác nhận build logic và task an toàn với concurrency. Song song hóa tận dụng tài nguyên khi có công việc độc lập; nó không thay thế việc loại bỏ công việc thừa hoặc xử lý repository chậm.

## 13. Đo thời gian bằng Gradle profile và log

Bắt đầu bằng:

```bash
./gradlew test --profile
```

Gradle có thể tạo profile report trong thư mục reports của build, thường dưới:

```text
build/reports/profile/
```

Profile report cung cấp dữ liệu về thời gian build và các hoạt động như configuration, task execution hoặc dependency resolution tùy phiên bản. Đường dẫn và chi tiết report có thể thay đổi theo phiên bản.

Có thể tăng log:

```bash
./gradlew test --info
```

Hoặc xem stack trace khi thất bại:

```bash
./gradlew test --stacktrace
```

Build Scan có thể cung cấp timeline và thông tin task/dependency. Việc publish scan phụ thuộc plugin, cấu hình và chính sách chia sẻ dữ liệu của tổ chức; cần kiểm tra dữ liệu nhạy cảm trước khi chia sẻ.

Nếu thời gian trước task đầu tiên lớn, kiểm tra initialization/settings, plugin resolution, buildscript classpath, configuration của từng project, configuration cache hit/miss và dependency resolution bị ép eager.

Nếu task đầu tiên xuất hiện nhanh nhưng compile/test task chờ lâu, kiểm tra dependency resolution/download, compile/runtime classpath, CPU/RAM/disk, test process, external service và task input/output.

## 14. Chẩn đoán dependency resolution

Xem dependency graph:

```bash
./gradlew :app:dependencies --configuration compileClasspath
```

Lệnh này có thể kích hoạt resolution của configuration. Không nên coi nó là phép đo hoàn toàn không tác động; hãy ghi nhận rằng lệnh đang yêu cầu resolve dependency.

Tìm lý do version được chọn:

```bash
./gradlew :app:dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

dependencyInsight giúp phân tích version conflict và constraint, không phải profiler mạng. Nếu nghi ngờ tải chậm, xem log --info, Build Scan hoặc log repository manager.

Có thể so sánh hai lần chạy:

```bash
./gradlew test --offline
./gradlew test --refresh-dependencies
```

- --offline kiểm tra build có thể dùng cache mà không truy cập mạng hay không.
- --refresh-dependencies yêu cầu kiểm tra lại trạng thái dependency.

Không nên so sánh một lần chạy đơn lẻ rồi kết luận chắc chắn. Kết quả còn phụ thuộc task outputs, daemon, filesystem cache, network và trạng thái build. Lặp lại trong điều kiện có kiểm soát.

## 15. Maven lifecycle và thời gian thực thi

Maven có mô hình lifecycle gồm các phase. Với packaging JAR, những phase thường gặp:

```text
validate
   |
compile
   |
test
   |
package
   |
verify
   |
install
   |
deploy
```

Mỗi phase có thể gắn một hoặc nhiều plugin goal. Khi chạy:

```bash
mvn verify
```

Maven thực thi các phase trước verify theo thứ tự lifecycle và các goal được bind vào chúng.

Maven cũng cần đọc POM, kế thừa parent, áp dụng profile, xây effective model, resolve plugin và dependency rồi mới thực hiện goal. Thời gian trước compiler/test có thể do model building, plugin resolution hoặc dependency resolution.

### Maven model building

Trước khi thực thi goal, Maven xây dựng mô hình project từ:

- POM hiện tại.
- Parent POM.
- Properties và interpolation.
- Dependency management.
- Plugin management.
- Profiles được kích hoạt.
- Các module trong reactor.

Parent POM phức tạp hoặc nhiều profile có thể làm tăng thời gian chuẩn bị. Plugin cũng được resolve khi Maven cần thực thi goal.

### Dependency resolution

Maven đọc metadata và tải dependency theo scope. Dependency cần cho compile, test hoặc runtime có thể được resolve ở những thời điểm khác nhau trong lifecycle. Repository chậm có thể khiến Maven mất thời gian trước khi compiler hoặc test bắt đầu.

### Goal execution

Sau khi chuẩn bị xong, plugin goal thực hiện compile, test, package, report hoặc deploy. Đây là phần tương đương gần nhất với task execution trong Gradle, nhưng Maven dùng lifecycle/goal thay vì task graph theo cùng mô hình.

## 16. Đo và chẩn đoán Maven

Chạy:

```bash
mvn -B -ntp test
```

- -B bật batch mode.
- -ntp tắt progress transfer output để log CI dễ đọc hơn.

Khi cần debug:

```bash
mvn -X test
```

-X bật debug output rất chi tiết. Log có thể dài và chứa đường dẫn hoặc thuộc tính nhạy cảm tùy plugin; cần kiểm tra trước khi lưu hoặc chia sẻ.

Xem dependency graph:

```bash
mvn dependency:tree
```

Xem POM hiệu lực:

```bash
mvn help:effective-pom
```

Các lệnh này giúp hiểu cấu hình và graph, nhưng không thay thế việc đo thời gian bằng profiler hoặc CI timeline.

Maven thường lưu artifact tải về trong local repository, mặc định là .m2/repository dưới user home. Khi artifact đã có sẵn và được xem là hợp lệ, Maven có thể tái sử dụng thay vì tải lại.

Offline mode:

```bash
mvn -o test
```

Nếu dependency hoặc plugin cần thiết chưa có trong local repository, build sẽ thất bại thay vì truy cập mạng.

Cập nhật snapshot:

```bash
mvn -U verify
```

-U yêu cầu Maven kiểm tra snapshot đã cập nhật và release bị thiếu. Nó không có nghĩa mọi release dependency luôn được tải lại từ đầu.

## 17. Maven parallel build

Maven có thể chạy một số module trong reactor song song:

```bash
mvn -T 1C verify
```

-T 1C yêu cầu số thread dựa trên số core theo quy tắc Maven. Có thể chỉ định số thread cụ thể, ví dụ -T 4.

Parallel reactor build có thể giảm thời gian khi module độc lập. Nhưng nếu test hoặc plugin cạnh tranh database, port, filesystem hoặc tài nguyên dùng chung, chạy song song có thể gây lỗi hoặc chậm hơn.

Không nên bật parallel chỉ vì build dài. Hãy xác định phần chậm là model/dependency resolution hay goal execution; số thread không giải quyết được mọi nguyên nhân.

## 18. So sánh Gradle và Maven

| Hoạt động | Gradle | Maven |
|---|---|---|
| Đọc cấu trúc build | Initialization và settings evaluation | Đọc POM, xây Maven model/reactor |
| Cấu hình build | Configuration phase | Model building và chuẩn bị plugin/lifecycle |
| Tải plugin | Plugin management/build logic resolution | Plugin resolution |
| Giải quyết dependency ứng dụng | Configuration resolution khi cần | Dependency resolution theo project/goal |
| Tải artifact | Dependency cache và repository | Local repository và remote repository |
| Lập kế hoạch công việc | Task graph | Lifecycle phase và plugin goal trong reactor |
| Thực thi | Task actions | Plugin goal |
| Tái sử dụng output | UP-TO-DATE, build cache | Một số plugin hỗ trợ incremental/cache; mô hình khác Gradle |
| Giảm cấu hình lặp | Configuration cache | Maven model/plugin behavior và tối ưu theo plugin |
| Parallelism | Task/project execution tùy cấu hình | Reactor parallelism với -T |

Không nên cố ánh xạ mọi chi tiết Maven thành Gradle phase hoặc ngược lại. Hai công cụ có mô hình khác nhau. Bảng này chỉ giúp nhận diện hoạt động tương đương ở mức khái niệm.

## 19. Các yếu tố làm configuration time tăng trong Gradle

### Nhiều project hoặc included build

Build nhiều project có thể cần đánh giá nhiều build script và plugin. Included build hoặc build logic riêng cũng có thể làm tăng công việc khởi tạo.

### Build script thực hiện công việc ngoài cấu hình

Ví dụ duyệt hàng chục nghìn file, đọc file lớn, gọi process, truy vấn mạng hoặc resolve dependency eager.

### Plugin cấu hình nặng

Plugin có thể quét source, phân tích project model hoặc đăng ký nhiều task. Plugin cũ có thể không tận dụng tốt lazy configuration.

### Tạo task eager

Sử dụng API eager để tạo/cấu hình tất cả task khi không cần có thể làm configuration phase nặng hơn. Ưu tiên tasks.register và tasks.named khi phù hợp.

### Không tái sử dụng configuration

Nếu build script hoặc plugin không tương thích configuration cache, Gradle có thể phải cấu hình lại ở mỗi invocation.

### Cách chẩn đoán

- Dùng --profile hoặc Build Scan.
- Xem thời gian configuration theo project.
- Kiểm tra plugin và build logic.
- Tìm truy cập file/network/process trong configuration phase.
- Kiểm tra configuration cache hit/miss và lý do miss.

## 20. Các yếu tố làm dependency download chậm

- **Repository phản hồi chậm:** kiểm tra latency, DNS, proxy, TLS và tình trạng repository server.
- **Cache lạnh:** runner mới hoặc user home mới chưa có metadata/artifact.
- **Dynamic version và snapshot:** selector linh hoạt hoặc changing module có thể yêu cầu kiểm tra metadata định kỳ.
- **Quá nhiều repository:** repository không cần thiết hoặc content filter không rõ có thể làm resolution thử nhiều nguồn.
- **Plugin kéo theo nhiều dependency:** plugin có graph riêng và cần tải trước khi project configuration hoàn tất.
- **Cache không được chia sẻ trong CI:** mỗi job dùng Gradle user home hoặc Maven local repository mới thì artifact phải tải lại.

Có thể dùng cache của nền tảng CI hoặc repository proxy, nhưng cần cache key và invalidation hợp lý.

## 21. Các yếu tố làm task execution chậm

- **Compile:** lượng source lớn, annotation processor, compiler options, generated source hoặc toolchain.
- **Test:** test chậm, test chạy tuần tự, khởi tạo application context, database/container, network hoặc timeout.
- **Resource processing:** copy nhiều file, filter template, nén hoặc biến đổi resource.
- **Static analysis:** Checkstyle, PMD, SpotBugs và các công cụ tương tự có thể quét nhiều module.
- **Packaging:** tạo fat JAR, nén asset, ký artifact hoặc tạo image có thể tốn CPU và I/O.
- **External tools:** Docker, Node, npm, native compiler hoặc script ngoài có startup và cache riêng.

Hãy tìm task cụ thể tiêu tốn thời gian và phân tích input/output, CPU, memory, disk, process và network của task đó.

## 22. Một quy trình đo hiệu năng có kiểm soát

Để tránh tối ưu dựa trên cảm giác:

1. Chọn lệnh build đại diện, ví dụ ./gradlew clean test hoặc mvn clean verify.
2. Ghi lại commit, JDK, build tool version, OS, runner và trạng thái cache.
3. Đo cold build trên môi trường cache sạch nếu cần đánh giá tải dependency.
4. Đo warm build khi dependency và output cache đã có.
5. Dùng profile/timeline để xác định thời gian configuration, resolution và task execution.
6. Xác định task hoặc hoạt động chiếm nhiều thời gian nhất.
7. Thay đổi một yếu tố mỗi lần, ví dụ configuration cache, repository proxy hoặc test parallelism.
8. Chạy lại trong điều kiện tương đương và so sánh nhiều lần.
9. Kiểm tra correctness: build/test phải giữ cùng kết quả.
10. Ghi lại thay đổi và bằng chứng để nhóm có thể tái kiểm tra.

| Loại chạy | Trạng thái thường gặp | Điều muốn đo |
|---|---|---|
| Cold dependency cache | Chưa có artifact/metadata cần thiết | Chi phí repository và download ban đầu |
| Warm dependency cache | Dependency đã có trong cache | Chi phí resolution và task còn lại |
| Warm task output | Task input/output không đổi | UP-TO-DATE hoặc build cache reuse |
| Configuration cache hit | Build configuration phù hợp đã được lưu | Chi phí configuration giảm |
| Clean build | Output project bị xóa | Chi phí compile/test/package từ đầu, dependency cache có thể vẫn nóng |

clean thường xóa output project, không đồng nghĩa xóa Gradle dependency cache hoặc Maven local repository. Vì vậy, clean test không tự tạo ra cold dependency cache.

## 23. Không nhầm clean build với cache lạnh

```bash
./gradlew clean test
```

Lệnh này xóa output của project rồi chạy test. Gradle vẫn có thể tái sử dụng dependency đã tải và configuration cache nếu điều kiện phù hợp.

Để kiểm tra dependency offline:

```bash
./gradlew test --offline
```

Để kiểm tra resolution mới:

```bash
./gradlew test --refresh-dependencies
```

Để kiểm tra task output có thể được tái sử dụng, chạy lại cùng task với cùng input và xem trạng thái UP-TO-DATE/FROM-CACHE. Không nên gộp các phép đo khác mục tiêu thành một con số duy nhất.

## 24. CI cache: cần chọn đúng dữ liệu để lưu

Trong CI, có thể cache:

- Gradle user home hoặc các phần cache dependency phù hợp.
- Maven local repository.
- Wrapper distribution.
- Một số output cache nếu build tool và pipeline hỗ trợ.
- Dependency verification/lock metadata trong repository như source input.

Không nên cache toàn bộ workspace một cách mù quáng. Output cũ có thể làm build khó hiểu nếu task không khai báo input/output đúng hoặc cache key không phản ánh đầy đủ môi trường.

### Gradle CI cache

Cache dependency có thể giảm thời gian download trên runner mới. Gradle remote build cache có thể chia sẻ output task giữa các build nếu task cacheable và input được khai báo đúng.

- Dependency cache lưu metadata và artifact thư viện.
- Build cache lưu output của task.

### Maven CI cache

Maven local repository chứa dependency và plugin đã tải. Cache thư mục repository có thể giảm network time, nhưng cần tránh dùng chung cache bị ghi đồng thời không an toàn giữa nhiều job hoặc tiến trình không được quản lý.

Cache key có thể dựa trên OS, JDK, build file hoặc wrapper version tùy hệ thống CI. Key quá rộng có thể làm cache không phù hợp; key quá hẹp có thể khiến cache bị bỏ lỡ thường xuyên.

## 25. Tối ưu configuration time trong Gradle

Các hướng thường hữu ích:

- Ưu tiên lazy task registration bằng tasks.register.
- Cấu hình task hiện có bằng tasks.named.
- Dùng configureEach thay vì cấu hình eager khi phù hợp.
- Tránh resolve dependency trong build script nếu task chưa cần.
- Tránh duyệt filesystem lớn hoặc gọi process/network trong configuration phase.
- Chuyển logic dùng chung vào convention plugin có API rõ ràng.
- Bật configuration cache sau khi xử lý compatibility.
- Giảm số plugin hoặc cấu hình nặng không cần thiết.
- Tránh tạo task và project model không được dùng.

Không nên xóa task hoặc dependency cần thiết chỉ để giảm thời gian. Mục tiêu là tránh công việc không cần thiết và trì hoãn công việc đến lúc cần.

## 26. Tối ưu dependency resolution và download

- Dùng repository đáng tin cậy, ổn định và gần runner.
- Dùng repository proxy/cache trong tổ chức khi phù hợp.
- Pin version và dùng platform/BOM rõ ràng.
- Tránh dynamic version hoặc snapshot trong build phát hành.
- Hạn chế repository trùng lặp và cấu hình content filter.
- Dùng dependency cache CI với key hợp lý.
- Chỉ refresh dependency khi có chủ đích.
- Kiểm tra plugin resolution riêng với application dependency.
- Không tải lại artifact không cần thiết trong mỗi task action.

Nếu build chỉ chậm ở lần đầu, cache có thể là giải pháp chính. Nếu build warm vẫn chậm ở resolution, kiểm tra metadata refresh, repository và dynamic version.

## 27. Tối ưu task execution

- Xác định task chậm nhất qua profile/timeline.
- Bảo đảm input/output task được khai báo đúng.
- Tránh làm task chạy lại vì timestamp hoặc input không ổn định.
- Bật build cache cho task cacheable khi phù hợp.
- Tối ưu test setup và loại bỏ test trùng lặp.
- Dùng parallel execution khi task độc lập và tài nguyên cho phép.
- Giảm file/resource không cần xử lý.
- Tối ưu annotation processor và generated source.
- Tách integration test nặng khỏi feedback loop nhanh khi quy trình cho phép.
- Đo lại sau từng thay đổi.

## 28. Ví dụ chẩn đoán: build chậm trước task đầu tiên

Tình huống: chạy ./gradlew test, terminal im lặng khoảng 25 giây rồi mới hiện :compileJava.

Có thể nguyên nhân nằm ở:

- Gradle daemon startup hoặc JVM startup.
- Initialization/settings evaluation.
- Plugin resolution.
- Configuration của nhiều subproject.
- Dependency resolution bị ép eager.
- Configuration cache miss.

Cách điều tra:

1. Chạy với --info và --profile.
2. Xem configuration time theo project.
3. Kiểm tra plugin management và buildscript classpath.
4. Tìm code truy cập .files, .get() hoặc resolve configuration trong build script.
5. Xem configuration cache có được tái sử dụng không.
6. So sánh lần đầu và lần sau trong cùng điều kiện.

Không nên tăng số worker trước khi biết task execution đã bắt đầu hay chưa.

## 29. Ví dụ chẩn đoán: build chậm ở compileJava

Tình huống: configuration nhanh, nhưng :app:compileJava mất 40 giây và log có nhiều hoạt động tải.

Có thể nguyên nhân là compile classpath chưa được cache hoặc dependency resolution cần metadata/artifact mới.

Cách điều tra:

1. Xem :app:compileJava có thực sự chạy hay không.
2. Xem compileClasspath bằng dependencies.
3. Kiểm tra repository và log --info.
4. Xác định JAR nào được tải và thời gian request.
5. So sánh với lần chạy offline nếu cache đã đủ.
6. Kiểm tra annotation processor và compiler sau khi dependency sẵn sàng.

Nếu compile task chạy lâu dù dependency đã cache, cần xem CPU, source count, annotation processor và compiler behavior thay vì tiếp tục tối ưu repository.

## 30. Ví dụ chẩn đoán: Maven test chậm

Tình huống: mvn test mất nhiều thời gian trước khi Surefire bắt đầu.

Có thể nguyên nhân là:

- Maven đang tải plugin hoặc dependency.
- Parent POM/profile làm model building phức tạp.
- Repository chậm.
- Compiler plugin hoặc annotation processor cần resolve artifact.

Nếu Surefire bắt đầu sớm nhưng test kéo dài, nguyên nhân có thể là test setup, database, external service hoặc test concurrency.

Cách điều tra:

1. Dùng mvn -B -ntp test để log CI dễ đọc.
2. Dùng mvn -X test khi cần debug sâu.
3. Kiểm tra local repository có cache dependency không.
4. Dùng mvn dependency:tree để xem graph.
5. Xem report Surefire để tìm test chậm.
6. Tách thời gian compile và test bằng cách chạy goal phù hợp.
7. Đo lại trong điều kiện warm/cold đã ghi nhận.

## 31. Bảng quyết định nhanh

| Triệu chứng | Phần cần kiểm tra trước | Công cụ gợi ý |
|---|---|---|
| Chậm trước task đầu tiên | Initialization/configuration/plugin resolution | Gradle --profile, Build Scan, --info |
| Chậm khi tìm plugin | Plugin repository và build logic classpath | Plugin management, log resolution |
| Chậm khi compile classpath được tạo | Dependency resolution/download | dependencies, dependencyInsight, repository logs |
| Lần đầu chậm, lần sau nhanh rõ rệt | Cold dependency cache hoặc task output cache | So sánh cold/warm, offline mode |
| Configuration chậm mỗi lần | Build script/plugin, configuration cache | --configuration-cache, profile report |
| Compile task chạy lâu | Compiler, annotation processor, source count | Task timing, compiler log |
| Test task chạy lâu | Test body, test worker, external services | Test report, test logging |
| Package task chạy lâu | Archive, compression, signing, image creation | Task profile, process/I/O |
| Maven chậm trước goal | POM model, plugin/dependency resolution | mvn -X, effective POM |
| Maven chậm trong Surefire | Test execution | Surefire reports và test logs |

## 32. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Dependency download luôn là một phase tách biệt sau configuration | Resolution/download có thể xảy ra khi configuration hoặc task cần dependency. |
| Configuration time chỉ là đọc build file | Nó còn gồm đánh giá script, áp dụng plugin, tạo model và có thể cả công việc eager. |
| Mọi task trong graph đều thực thi action | Task có thể UP-TO-DATE, FROM-CACHE, NO-SOURCE hoặc SKIPPED. |
| clean xóa mọi cache | clean thường xóa output project, không xóa dependency cache của user. |
| Build cache giảm configuration time | Configuration cache tái sử dụng kết quả cấu hình; build cache tái sử dụng task outputs. |
| --refresh-dependencies luôn tải lại mọi JAR | Gradle làm mới trạng thái cache và kiểm tra cần thiết; artifact hợp lệ có thể được tái sử dụng. |
| Tăng worker luôn làm build nhanh | Chỉ hữu ích khi có công việc độc lập và tài nguyên không bị bão hòa. |
| Maven -T giải quyết repository chậm | Nó tăng parallelism cho reactor; không loại bỏ network latency hoặc model building. |
| Chạy offline là cách cập nhật dependency | Offline chỉ dùng cache hiện có và không truy cập repository. |
| Tổng thời gian build đủ để tìm nút thắt | Cần timeline/profile và phân biệt các giai đoạn. |

## 33. Checklist đo và tối ưu một build chậm

Trước khi thay đổi cấu hình, hãy ghi nhận:

- Lệnh build chính xác và mục tiêu cần đo.
- Commit, JDK, Gradle/Maven version và hệ điều hành.
- Build đang dùng cache lạnh hay nóng.
- Thời gian từ lúc gọi lệnh đến task đầu tiên.
- Thời gian configuration theo project nếu có.
- Thời gian resolve/download dependency.
- Task nào chiếm nhiều thời gian nhất.
- Task có thực thi, UP-TO-DATE hay FROM-CACHE.
- CPU, RAM, disk và network có bị bão hòa không.
- Plugin hoặc build logic nào thực hiện công việc eager.
- CI có cache dependency và output phù hợp không.
- Thay đổi tối ưu có giữ nguyên kết quả compile/test/package không.

## 34. Quy trình chọn đúng hướng tối ưu

```text
Build chậm
   |
   v
Thời gian chủ yếu trước task đầu tiên?
   |
   +-- Có --> Kiểm tra initialization/configuration/plugin
   |             |
   |             +--> Build script eager?
   |             +--> Plugin resolution chậm?
   |             +--> Configuration cache miss?
   |
   +-- Không
          |
          v
Thời gian chủ yếu ở dependency resolution/download?
          |
          +-- Có --> Kiểm tra repository, cache, metadata, version selector
          |
          +-- Không
                 |
                 v
           Task execution chậm?
                 |
                 +--> Compile / annotation processor
                 +--> Test / external service
                 +--> Static analysis
                 +--> Packaging / I/O
```

Sau khi xác định đúng phần chậm, chọn giải pháp tương ứng:

- Configuration chậm: giảm công việc eager, tối ưu plugin/build logic, dùng configuration cache khi tương thích.
- Download chậm: dùng cache, repository proxy, pin version và kiểm soát refresh.
- Task chậm: tối ưu input/output, build cache, test, compiler, I/O hoặc parallelism theo bằng chứng.

## 35. Nguyên tắc áp dụng trong thực tế

Thời gian cấu hình, tải phụ thuộc và thực thi tác vụ là ba góc nhìn cần tách ra khi phân tích hiệu năng build. Gradle có initialization/configuration/execution phase, nhưng dependency resolution có thể diễn ra ở nhiều thời điểm tùy cách build được viết. Maven xây model, resolve plugin/dependency rồi thực thi lifecycle goal. Cả hai đều có cache và cơ chế parallelism, nhưng chúng phục vụ các loại công việc khác nhau.

Khi build chậm, hãy đo trước khi tối ưu. Xác định thời gian bị tiêu tốn trước task đầu tiên, trong lúc resolve/download hay bên trong task cụ thể. Sau đó dùng công cụ tương ứng: Gradle profile/configuration cache/dependency insight, Maven debug/effective POM/dependency tree, log repository và báo cáo task. Một thay đổi tối ưu chỉ có giá trị khi nó giảm đúng phần thời gian mục tiêu mà vẫn giữ nguyên tính đúng đắn và khả năng tái lập của build.
