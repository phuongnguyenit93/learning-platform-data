# Phân biệt cache tải thư viện, cache cấu hình và cache đầu ra tác vụ trong Spring Boot Build Tooling

## 1. Mục tiêu và bức tranh tổng thể

Khi chạy `./gradlew build` nhiều lần, ứng dụng Spring Boot có thể build nhanh hơn dù bạn không sửa mã nguồn. Nhưng “Gradle đã dùng cache” là một câu chưa đủ chính xác. Ít nhất có ba cơ chế khác nhau:

1. **Dependency cache**: tránh tải lại artifact và metadata dependency từ Maven Central, Gradle Plugin Portal hoặc repository nội bộ khi dữ liệu cache vẫn dùng được.
2. **Configuration cache**: giữ kết quả cấu hình build (task graph, configured task state, dependency information cần thiết) để các lần chạy tương thích có thể bỏ qua việc đánh giá lại build scripts và plugins.
3. **Build cache (task output cache)**: tái sử dụng **đầu ra của task cacheable** khi các inputs tương ứng không đổi, thay vì chạy lại công việc như biên dịch Java hoặc xử lý một số loại output.

Ba cache không thay thế nhau, có thể hoạt động cùng lúc và có điều kiện hợp lệ khác nhau. **`UP-TO-DATE` không phải `FROM-CACHE`**, còn “thư viện đã tải sẵn” không chứng minh Gradle đã reuse configuration hoặc task output.

Sau bài học, bạn có thể:

- Vẽ đúng luồng initialization → configuration → execution và đặt từng cache vào bước phù hợp.
- Đọc log để phân biệt download reuse, configuration cache reuse, `UP-TO-DATE` và `FROM-CACHE`.
- Bật/tắt đúng cache bằng CLI hoặc `gradle.properties`, hiểu tác dụng của `clean`, `--offline`, `--refresh-dependencies`, `--rerun-tasks`.
- Thực hành trên một project Java 17 + Spring Boot 3.3.13, dùng Gradle Groovy DSL hoặc Kotlin DSL.
- Biết khi nào task không được cache, vì sao input/output declaration và deterministic builds quan trọng.
- So sánh tương đối với **Maven local repository** và **Maven Build Cache Extension**, không nhầm chúng với cơ chế built-in của Gradle.
- Chẩn đoán cache miss, dependency stale, plugin incompatibility và những rủi ro bảo mật/correctness trên CI.

**Giới hạn phiên bản:** ví dụ chọn Spring Boot 3.3.13 và Java 17 để thống nhất với module. Đây là mốc minh họa, không phải tuyên bố là bản Spring Boot mới nhất. Một số tùy chọn và mức hỗ trợ configuration cache thay đổi theo Gradle/plugin version, nên dùng Gradle wrapper của repository và đối chiếu tài liệu tương ứng.

## 2. Mỗi cache tối ưu phần nào của vòng đời?

Gradle thường có ba giai đoạn chính:

~~~text
Initialization
  └─ Xác định build, settings, root/subprojects

Configuration
  ├─ Đọc settings.gradle(.kts), build.gradle(.kts)
  ├─ Apply plugins, tạo/cấu hình tasks
  ├─ Xác định task graph và dependencies liên quan
  └─ Tạo configured build model

Execution
  ├─ Kiểm tra inputs/outputs của từng task
  ├─ Resolve artifacts khi task/build cần
  ├─ Chạy compiler, tests, packaging nếu cần
  └─ Sinh build/classes, build/resources, build/libs...
~~~

Đây là sơ đồ khái niệm. **Dependency resolution có thể xảy ra khi configuration hoặc execution**, tùy build logic và cách Gradle lưu configuration cache; không nên dạy rằng nó tuyệt đối chỉ thuộc một phase.

Ba cache nằm ở các điểm sau:

~~~text
Remote repositories (Maven Central, mirror, Plugin Portal)
          |
          v
[DEPENDENCY CACHE] ──> Maven/Gradle modules, metadata, JARs
          |
          v
Gradle build model / task classpath
          |
[CONFIGURATION CACHE] ──> configured task graph + task state
          |
          v
Task execution decisions
          |
          +── Inputs/output tại workspace đã đúng ──> UP-TO-DATE
          |
          +── Cacheable task + matching cache key ─> FROM-CACHE
          |
          +── Không thể reuse ──────────────────────> EXECUTED
                                                     |
                                                     v
                                             Output trong build/
~~~

Một project có thể đã cache toàn bộ dependency nhưng vẫn cần compile lại code; đã reuse configuration nhưng vẫn phải chạy tests; hoặc reuse cached task output nhưng vẫn phải đánh giá cấu hình vì configuration cache đang tắt.

## 3. Bảng so sánh ba cơ chế

| Tiêu chí | Dependency cache | Configuration cache | Build cache |
| --- | --- | --- | --- |
| Tối ưu | Download và metadata resolution | Giai đoạn cấu hình Gradle | Tính toán/đầu ra của task |
| Dữ liệu chính | Modules, artifacts, POM/metadata, kết quả resolution | Task graph, configured task state và thông tin cấu hình | Outputs của cacheable tasks / một số transforms |
| Điểm lưu phổ biến | `GRADLE_USER_HOME/caches/modules-2` | `.gradle/configuration-cache` ở root build | Local build cache dưới Gradle User Home; có thể thêm remote |
| Điều kiện dùng lại | Module/repository metadata và TTL/checksum hợp lệ | Cùng kiểu task invocation và configuration inputs còn hợp lệ | Cache key của task khớp declared inputs, implementation và output metadata |
| Kích hoạt | Gradle dùng dependency cache mặc định | `--configuration-cache` hoặc property tương ứng | `--build-cache` hoặc property tương ứng |
| Tắt/vô hiệu hóa tạm | `--refresh-dependencies` yêu cầu xác minh mới; `--offline` chỉ dùng dữ liệu local | `--no-configuration-cache` | `--no-build-cache` |
| Dùng qua nhiều project/máy | Artifact cache local; sharing cần giải pháp cẩn trọng | Không phải cache chia sẻ remote phổ thông | Local hoặc remote shared cache nếu được cấu hình |
| Dấu hiệu kiểm tra | Ít/không download; dependency graph đúng | Log configuration cache stored/reused | `FROM-CACHE` trong task output |
| Tác động của `clean` | Không xóa cache Gradle User Home | Không tự xóa configuration cache | Xóa outputs trong `build` nhưng không xóa build cache entries |
| Có nghĩa tests đã chạy? | Không | Không | Không; cached task result không phải test execution mới |

**Cần phân biệt “đã có file” với “cache hit”:** package đã tải sẵn trong Gradle User Home không có nghĩa task biên dịch đã được cache. Cũng như archive `build/libs/app.jar` còn nguyên không chứng minh task đang đọc cache; có thể Gradle chỉ đánh giá task là `UP-TO-DATE` dựa trên local outputs và history.

## 4. Cache tải thư viện (Dependency Cache)

### 4.1. Cache chứa những gì?

Gradle lưu thông tin dependency resolution và artifacts đã tải trong Gradle User Home, theo mặc định thường là:

~~~text
~/.gradle/
└── caches/
    └── modules-2/
        ├── files-2.1/      # các artifact files/checksums
        └── metadata-.../   # kết quả resolution/metadata, tên thay đổi theo Gradle
~~~

Đường dẫn là minh họa convention; trên Windows thường ở thư mục user và có thể đổi bằng `GRADLE_USER_HOME`. **Không viết build logic phụ thuộc cấu trúc file cache nội bộ**: Gradle có thể thay đổi tổ chức directory theo phiên bản.

Ví dụ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Gradle phải resolve dependency graph, BOM/constraints, metadata và tải các JAR cần thiết. Những artifacts có thể dùng lại ở các build sau. Nhưng Java source thay đổi thì `compileJava` có thể cần chạy lại dù download cache hoàn toàn hợp lệ.

Gradle còn cache thông tin resolution của version động, metadata module và cả thông tin không tìm thấy module tại một repository. Cache metadata gắn với nguồn repository; việc đổi URL, layout hoặc cấu hình repository có thể khiến Gradle cần resolve lại. Dependency cache **không phải danh sách JAR bất kỳ bạn tự copy vào một folder rồi mặc nhiên được tin cậy**.

### 4.2. Version cố định, dynamic và changing

Ba trường hợp cần phân biệt:

| Khai báo | Ví dụ | Nguyên tắc |
| --- | --- | --- |
| Version cố định | `spring-core:6.1.20` | Thường được xem là artifact bất biến; Gradle ưu tiên reuse theo metadata/checksums |
| Dynamic version | `1.+` hoặc `latest.release` | Gradle cache kết quả chọn một version cụ thể theo TTL |
| Changing module | SNAPSHOT hoặc dependency được đánh dấu changing | Metadata/artifact có thể đổi mà tọa độ chưa đổi; dùng TTL thích hợp |

Gradle mặc định cache **dynamic versions** và **changing modules** trong khoảng **24 giờ** (theo tài liệu Gradle hiện hành), trừ khi resolution strategy được điều chỉnh. Điều này không có nghĩa mọi version cố định bị “refresh sau 24 giờ”; fixed releases thường được kỳ vọng không thay nội dung.

**Groovy DSL**, fragment điều chỉnh TTL trong một build:

~~~groovy
configurations.configureEach {
    resolutionStrategy.cacheDynamicVersionsFor 10, 'minutes'
    resolutionStrategy.cacheChangingModulesFor 4, 'hours'
}
~~~

**Kotlin DSL** tương đương:

~~~kotlin
configurations.configureEach {
    resolutionStrategy.cacheDynamicVersionsFor(10, "minutes")
    resolutionStrategy.cacheChangingModulesFor(4, "hours")
}
~~~

Đây là **fragment bổ sung**, không cần cho ví dụ mặc định. Giảm TTL sẽ làm nhiều network checks hơn; đặt 0 hoặc refresh liên tục chỉ có lý do khi cần SNAPSHOT thực sự cập nhật nhanh. Ứng dụng production nên ưu tiên pinned versions và cơ chế kiểm soát dependency rõ ràng để tránh build không tái lập.

### 4.3. `--offline` và `--refresh-dependencies` không có nghĩa giống nhau

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration runtimeClasspath --offline
./gradlew dependencies --configuration runtimeClasspath --refresh-dependencies
~~~

- `--offline`: không dùng network để resolve; chỉ sử dụng artifacts/metadata có sẵn. Nếu dependency bắt buộc chưa cache hoặc metadata thiếu, build có thể **FAIL**. Offline không tạo dependency mới và không có nghĩa mọi artifact cache luôn “mới”.
- `--refresh-dependencies`: yêu cầu Gradle kiểm tra lại resolution/metadata và xác minh artifact với repository. Nó **không nhất thiết tải lại toàn bộ file JAR**; nếu checksum/remote metadata cho thấy file cũ vẫn đúng, Gradle có thể dùng lại dữ liệu.
- Lệnh bình thường: dùng cache theo chính sách TTL/resolution và tải khi cần.

**Không nhầm:** `--refresh-dependencies` không “xóa build cache”, còn `--offline` không bật configuration cache hay task output cache. Cũng không nên ghép `--offline` và `--refresh-dependencies` để kỳ vọng Gradle vừa dùng mạng vừa không dùng mạng.

### 4.4. Khi nào kiểm tra dependency cache?

Khi gặp:

- Dependency resolve lúc nhanh lúc chậm hoặc liên tục download.
- Snapshot/dynamic version không phản ánh bản bạn mong đợi.
- Đổi repository/mirror, credentials hoặc mạng và build báo không tìm thấy module.
- CI agent ephemeral phải tải dependencies lại.
- Lỗi classpath dù các file đã có từ lần build trước.

Bắt đầu bằng `--info`/`dependencyInsight` và kiểm tra repository; **không xóa toàn bộ `~/.gradle/caches` ngay lập tức**. Một missing artifact thường là lỗi tọa độ, mirror, policy hoặc network, không phải “cache hỏng”.

## 5. Configuration Cache: tránh cấu hình lại toàn bộ build

### 5.1. Configuration phase làm gì?

Ở configuration, Gradle đọc settings/build scripts, apply plugins (như `java` và `org.springframework.boot`), tạo/cấu hình tasks `compileJava`, `test`, `bootJar` và tính graph cho các task được yêu cầu.

Với repository nhiều module, configuration có thể mất thời gian ngay cả khi task execution sau đó chỉ vài giây. **Configuration cache** lưu trạng thái đã cấu hình để lặp lại cùng kiểu build mà không phải thực hiện đầy đủ configuration phase.

Ví dụ (tùy Gradle version):

~~~bash
./gradlew help --configuration-cache
./gradlew help --configuration-cache
~~~

Lần đầu Gradle thường ghi/stored configuration cache; lần hai nếu điều kiện giống nhau có thể in thông tin **reusing configuration cache**. Task `help` được dùng để học cơ chế cấu hình mà không kéo toàn bộ compilation/tests vào phép đo. Hãy đọc log của **phiên bản wrapper thực tế**: cách diễn đạt message có thể khác.

### 5.2. Bật theo từng lần hoặc trong project

Một lần:

~~~bash
./gradlew help --configuration-cache
~~~

Bật bền vững trong `gradle.properties`:

~~~properties
org.gradle.configuration-cache=true
~~~

Tạm tắt cho lệnh đang chạy:

~~~bash
./gradlew help --no-configuration-cache
~~~

Đừng bật trên tất cả modules một cách mù quáng nếu plugin/task/build logic chưa tương thích. Configuration cache có các ràng buộc riêng về **configuration-time dependencies, task state serialization và việc task không sử dụng trực tiếp Project API ở execution time**. Hãy chạy kiểm chứng và xử lý warnings/errors đúng nguyên nhân.

### 5.3. Configuration cache lưu trạng thái nào?

Gradle ghi configured task graph và những trạng thái task cần thiết cho requested tasks. Key/fingerprints có thể xét:

- Task names, các tham số invocation có ảnh hưởng.
- Settings/build scripts, buildSrc/included build logic.
- `gradle.properties`, version catalogs, dependency verification/lock files.
- Gradle/JVM environment có ảnh hưởng.
- Environment variables/system properties/files được đọc khi configuration.
- Trạng thái filesystem hoặc input được build logic kiểm tra ở configuration.

**Source Java thay đổi** không nhất thiết buộc configuration cache miss nếu nó không được đọc trong configuration và task graph/configuration không đổi. Khi đó configuration cache vẫn hit, nhưng `compileJava` phải xử lý source input mới theo execution logic. Ngược lại, chỉ sửa `build.gradle` có thể làm configuration cache miss ngay cả khi Java sources không đổi.

### 5.4. Configuration cache khác remote build cache

Configuration cache thường lưu ở:

~~~text
<root-project>/.gradle/configuration-cache/
~~~

Nó là cache **local theo build/configuration**. Không đồng nhất với remote build cache. Việc zip thư mục này rồi upload lên server để các CI agents khác reuse là **không phải quy trình sharing mặc định** và có rủi ro về môi trường/tính tương thích và dữ liệu nhạy cảm. Các sản phẩm quản trị cache có thể có cơ chế riêng; chỉ dùng theo chính sách đã xác minh.

Một configuration cache hit không bảo đảm task outputs đã tồn tại. Gradle vẫn có thể compile/test/package sau khi dựng lại task graph từ cache.

### 5.5. Cảnh báo bảo mật

Configuration cache có thể lưu configured task state và fingerprint của inputs, trong đó có môi trường/system properties hoặc credentials mà build logic đọc. Gradle hiện đại có cơ chế bảo vệ dữ liệu cache, nhưng **không biến việc ghi secret trực tiếp vào build script/task state thành thực hành an toàn**.

- Không hardcode credentials trong `build.gradle`/`gradle.properties` commit lên Git.
- Dùng Providers API, secret management và lazy wiring phù hợp; tránh resolve secret ở configuration khi không cần.
- Không chia sẻ thư mục configuration cache cùng key/máy theo cách không được kiểm soát.
- Không in token/private repository credentials vào log `--info` hoặc artifact.

Nếu Gradle báo configuration-cache problem, nên sửa task/plugin/build logic hoặc tạm tắt configuration cache cho workflow đó. Không dùng `configuration-cache-problems=warn` như giải pháp mặc định lâu dài vì có thể che lỗi serializing task state.

## 6. Build Cache: tái sử dụng đầu ra của task

### 6.1. Điều kiện để task output được tái sử dụng

Task như `compileJava` tạo file `.class` từ Java sources, compiler options, classpath và công cụ. Nếu task được hỗ trợ output caching, Gradle có thể tính **cache key** từ:

- Implementation và action implementation của task.
- Các task inputs được khai báo: source files, classpath, compiler flags, options, toolchain...
- Output property names và các yếu tố liên quan.

Khi key khớp một entry trong build cache, Gradle **khôi phục output** thay vì chạy lại compiler. Điều này yêu cầu task cacheable và inputs/outputs được mô hình hóa đúng; không phải task tùy chỉnh nào cũng cacheable.

Gradle Build Cache có thể:

- **Local**: reuse giữa nhiều lần build/workspaces trên cùng máy.
- **Remote**: chia sẻ output qua một build cache server đã cấu hình, khi task cache key và môi trường cho phép.

Cần phân biệt **task output caching** với Gradle **incremental compilation**: incremental compile giảm phần source phải biên dịch khi task cần chạy; build cache có thể bỏ toàn bộ task action bằng output đã lưu.

### 6.2. Kích hoạt build cache

Theo CLI:

~~~bash
./gradlew compileJava --build-cache
~~~

Trong `gradle.properties`:

~~~properties
org.gradle.caching=true
~~~

Tạm tắt:

~~~bash
./gradlew compileJava --no-build-cache
~~~

Đây là cờ cho **task output cache**, không phải cờ cho dependency cache hoặc configuration cache. Trong một số bản Gradle, build cache mặc định không bật; cần kiểm tra cấu hình thực tế của wrapper/repository.

### 6.3. `UP-TO-DATE` và `FROM-CACHE`: khác nhau căn bản

Giả sử task `compileJava` đã tạo `build/classes/java/main`. Lần sau không đổi input và output vẫn có, Gradle có thể bỏ chạy task nhờ **up-to-date checks**. Log có thể cho thấy:

~~~text
> Task :compileJava UP-TO-DATE
~~~

Điều này không yêu cầu build cache. Nó chỉ cho biết task inputs/outputs và local execution history cho phép reuse **output vẫn có trong workspace này**.

Nếu bạn xóa `build` bằng `clean` nhưng build cache còn giữ output hợp lệ, Gradle có thể phục hồi output từ cache:

~~~text
> Task :compileJava FROM-CACHE
~~~

`FROM-CACHE` là tín hiệu **task output được lấy từ build cache**. Nếu log ghi `> Task :compileJava` không có trạng thái reuse, task có thể đã thực hiện action bình thường. Tùy task/version, có thể gặp `NO-SOURCE`, `SKIPPED`, `FROM-CACHE` hoặc `UP-TO-DATE`; không nên suy luận chỉ từ tốc độ chạy.

### 6.4. Thí nghiệm minh họa rõ nhất

Trên project có source Java và Gradle wrapper hợp lệ:

~~~bash
./gradlew clean compileJava --build-cache
./gradlew compileJava --build-cache
./gradlew clean compileJava --build-cache
~~~

Mục đích từng bước:

1. **Clean + compile**: task cần tạo outputs; có thể chạy thật hoặc FROM-CACHE nếu cache đã có entry từ trước.
2. **Compile ngay sau đó**: thường `UP-TO-DATE` nếu inputs/outputs không đổi.
3. **Clean + compile lần nữa**: có cơ hội `FROM-CACHE` vì output workspace đã bị xóa nhưng cache entry còn đúng.

Đây là **kịch bản kỳ vọng**, không phải output được bảo đảm trên mọi máy. Nếu task không cacheable, inputs khác, toolchain/Gradle version khác hoặc cache entry bị evict, Gradle sẽ chạy task. Dùng `--info` để xem lý do task có/không cache.

### 6.5. `--rerun-tasks` khác `--no-build-cache`

~~~bash
./gradlew compileJava --rerun-tasks
./gradlew compileJava --no-build-cache
~~~

- `--rerun-tasks`: yêu cầu Gradle chạy lại task actions thay vì bỏ qua theo up-to-date/build cache reuse; có ích khi cần kiểm tra thực thi mới.
- `--no-build-cache`: tắt lookup/store của build cache trong invocation đó, **không tự vô hiệu hóa up-to-date checks**. Vì vậy task vẫn có thể `UP-TO-DATE`.
- `clean`: xóa outputs của build dưới `build`, nhưng không tự xóa Gradle User Home caches.

Không dùng ba cơ chế này như đồng nghĩa. Để ép task chạy và bỏ cache, `--rerun-tasks` là hướng có liên quan trực tiếp, nhưng kiểm tra flags theo Gradle version khi build logic tùy biến.

### 6.6. Không phải mọi task Spring Boot đều chắc chắn cacheable

`compileJava`, một số resource processing/archive tasks và các transforms có quy tắc caching tùy Gradle/plugin. Test hoặc packaging tasks có thể có điều kiện hoặc không cacheable theo implementation, settings và outputs.

**Đặc biệt:** đừng tự khẳng định `bootJar FROM-CACHE` luôn xuất hiện khi bật `--build-cache`. Hãy kiểm tra task implementation/cacheability và log thật. Việc `bootJar` tạo file giống nhau giữa hai lần build chưa đủ chứng minh cached output.

Custom task viết bằng `doLast` nhưng không khai báo input/output đúng có thể:

- Luôn phải chạy vì Gradle không biết outputs hợp lệ.
- Được coi là `UP-TO-DATE` sai nếu input ẩn không được khai báo.
- Trả kết quả không đúng khi reuse remote cache nếu output chứa thời gian/random/absolute path.

**Nguyên tắc build correctness quan trọng hơn tốc độ:** task cacheable phải deterministic với declared inputs; phải khai báo source, classpath, environment/task properties phù hợp. Tránh đưa timestamp hiện tại vào file sinh ra nếu không thực sự cần và không khai báo nó là input.

## 7. Project mẫu Spring Boot Java 17 để thí nghiệm

Ta dùng một ứng dụng console nhỏ, đủ để chứng minh compilation và packaging mà không cần database hay HTTP server.

Cây thư mục:

~~~text
cache-demo/
├── settings.gradle                # dùng với Groovy DSL
├── build.gradle                   # dùng với Groovy DSL
│  hoặc settings.gradle.kts        # dùng với Kotlin DSL
│  hoặc build.gradle.kts           # dùng với Kotlin DSL
├── gradle.properties              # tùy chọn, ban đầu để trống
└── src/
    └── main/
        └── java/
            └── com/example/cache/
                └── CacheDemoApplication.java
~~~

**Chọn một cặp settings/build tương ứng**, không tạo hai build scripts để Gradle “chạy cả Groovy và Kotlin”. Nếu project đã có Gradle wrapper (`gradlew`/`gradlew.bat`/`gradle/wrapper`) thì dùng wrapper; nếu chưa có, phải chuẩn bị wrapper riêng bằng một Gradle version phù hợp.

### 7.1. Groovy DSL — settings.gradle

~~~groovy
rootProject.name = 'cache-demo'
~~~

### 7.2. Groovy DSL — build.gradle đầy đủ

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0'

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
~~~

`java` tạo các task biên dịch Java; Spring Boot plugin tạo `bootJar` với executable format khi có Java plugin. Dependency management plugin cùng Spring Boot plugin cung cấp BOM tương thích để bỏ version trên starter đã được quản lý.

### 7.3. Kotlin DSL — settings.gradle.kts

~~~kotlin
rootProject.name = "cache-demo"
~~~

### 7.4. Kotlin DSL — build.gradle.kts đầy đủ

~~~kotlin
plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
}
~~~

Dùng `build.gradle.kts` không bắt buộc viết ứng dụng bằng Kotlin. Đây vẫn là Java 17 project.

### 7.5. Main class Java chạy được

Tệp `src/main/java/com/example/cache/CacheDemoApplication.java`:

~~~java
package com.example.cache;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CacheDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CacheDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner printDemo() {
        return args -> System.out.println("CACHE_DEMO_OK");
    }
}
~~~

Dòng output do code tự in khi chạy thành công:

~~~text
CACHE_DEMO_OK
~~~

Các log Spring Boot khác có thể xuất hiện. Vì không dùng web starter hay background thread, process có thể tự kết thúc sau startup; đây là hành vi bình thường của demo, không phải cache làm ứng dụng dừng.

Với toolchain Java 17, máy build phải có JDK 17 phù hợp hoặc Gradle đã được cấu hình provision toolchain. Máy chạy JAR cần Java runtime tương thích.

### 7.6. Build và chạy ứng dụng

~~~bash
./gradlew --version
./gradlew clean build
java -jar build/libs/cache-demo-0.1.0.jar
~~~

Nếu `build` hoàn thành và `bootJar` đã tạo file mặc định, ứng dụng in `CACHE_DEMO_OK`. `build` theo Java lifecycle thường kết nối `assemble` và `check`. Với demo không có JUnit test source, task test có thể được skip hoặc `NO-SOURCE`; **không gọi đó là bằng chứng test đã chạy pass khi không có test**.

## 8. Thực hành A — chứng minh dependency cache

Mục tiêu: chỉ tập trung vào dependency resolution, không đo compilation.

Lần đầu online:

~~~bash
./gradlew dependencies --configuration runtimeClasspath --info
~~~

Gradle sẽ resolve Spring Boot starter và các dependency transitive nếu chưa có cache, có thể tải artifacts/metadata từ repository. Trong lần kế tiếp:

~~~bash
./gradlew dependencies --configuration runtimeClasspath --info
~~~

Nếu cache còn hiệu lực, Gradle có thể dùng lại metadata và artifacts, network download ít đi hoặc không có. **Không dựa chỉ vào việc lệnh chạy nhanh**: daemon, filesystem cache hoặc network proxy cũng ảnh hưởng thời gian.

Thử offline sau khi cache được populate:

~~~bash
./gradlew dependencies --configuration runtimeClasspath --offline
~~~

Nếu mọi thứ cần thiết đã có, nó có thể resolve được. Nếu có artifacts/plugin metadata chưa lưu, offline build có thể fail — điều này **không chứng minh dependency cache hỏng**, mà cho biết offline không đủ dữ liệu để giải quyết build.

Khi nghi artifact changing/snapshot đã được cập nhật trên server:

~~~bash
./gradlew dependencies --configuration runtimeClasspath --refresh-dependencies
~~~

Xem log và resolution result. `--refresh-dependencies` yêu cầu kiểm tra mới, nhưng không tải lại file nếu artifact đã cache có checksum vẫn đúng. **Không** ghép thêm `clean` rồi gọi đó là cách xóa dependency cache.

Một lưu ý: `dependencies` task chủ yếu hiển thị graph; để chắc chắn các binary JAR cần thiết đã được download và compiler có đủ classpath, hãy chạy `compileJava`/`bootJar` trong lần online. Gradle có thể resolve metadata mà chưa cần tải mọi file artifact ở lệnh graph.

## 9. Thực hành B — chứng minh configuration cache

Trên project mẫu:

~~~bash
./gradlew help --configuration-cache
./gradlew help --configuration-cache
~~~

Hai lần yêu cầu cùng task `help`. Khi build logic/configuration inputs không đổi và plugin tương thích, lần đầu thường tạo entry, lần hai reuse. Nếu configuration cache báo lỗi với một plugin hoặc build logic, xem report; không cố xóa cache liên tục để che incompatibility.

Để thấy khác biệt giữa **thay đổi configuration** và **thay đổi source**:

1. Chạy hai lần `help --configuration-cache` tới khi thấy reuse.
2. Thay một comment hoặc property trong `build.gradle`/`build.gradle.kts`, chạy lại. Gradle thường invalidates entry vì build script input đã đổi.
3. Chạy lần kế tiếp không sửa gì, có thể lại reuse configuration cache.
4. Thay body của `CacheDemoApplication.java` và chạy `help --configuration-cache`. Nếu build logic không đọc source content trong configuration, thay đổi source **không nhất thiết** làm configuration cache miss.

Đừng chạy một tác vụ khác rồi yêu cầu reuse đúng entry của `help`: requested tasks là một phần của cache key/validation context. `help`, `compileJava`, `bootJar` và `build` có graph khác nhau.

Để tắt tạm:

~~~bash
./gradlew help --no-configuration-cache
~~~

Tắt configuration cache không xóa dependency JARs và không có nghĩa task outputs sẽ bị xóa.

## 10. Thực hành C — phân biệt UP-TO-DATE và FROM-CACHE

Dùng chính source Java ở mục 7.5, không sửa giữa các lệnh.

~~~bash
./gradlew clean compileJava --build-cache
./gradlew compileJava --build-cache
./gradlew clean compileJava --build-cache
~~~

Quan sát và ghi lại task outcomes:

| Lần chạy | Dự kiến với task cacheable và inputs giống nhau | Vì sao |
| --- | --- | --- |
| Lần 1: clean + compile | EXECUTED hoặc FROM-CACHE nếu cache đã có | Không có local outputs sau clean; có thể cache hit từ build cũ |
| Lần 2: compile | Thường `UP-TO-DATE` | Local class files vẫn tồn tại và inputs không đổi |
| Lần 3: clean + compile | Có thể `FROM-CACHE` | Local outputs đã xóa nhưng cache entry hợp lệ có thể khôi phục |

Nếu không thấy `FROM-CACHE`, chạy thêm `--info` để xem lý do task không cacheable, task inputs thay đổi hoặc cache không được bật/được phép đọc.

Một lệnh đối chứng:

~~~bash
./gradlew compileJava --no-build-cache
~~~

Task vẫn **có thể** là `UP-TO-DATE`; vì thế `--no-build-cache` không phải “force recompilation”. Nếu muốn task action chạy lại để điều tra:

~~~bash
./gradlew compileJava --rerun-tasks
~~~

Task compile có thể vẫn báo `NO-SOURCE` nếu project chưa có Java code; đây là lý do ví dụ bắt buộc phải tạo `CacheDemoApplication.java`.

### 10.1. Kịch bản bật đồng thời hai cache

~~~bash
./gradlew build --configuration-cache --build-cache
./gradlew build --configuration-cache --build-cache
~~~

Ở lần hai có thể thấy **reusing configuration cache** và nhiều task `UP-TO-DATE`. Điều này không chứng minh task output build cache vừa được truy xuất; nếu outputs vẫn có, Gradle thường ưu tiên up-to-date. Nếu chạy `clean build --configuration-cache --build-cache`, một số task cacheable có cơ hội `FROM-CACHE`, nhưng `clean build` có requested task graph khác nên configuration cache entry cũng có thể khác với `build`.

**Mỗi cơ chế có tín hiệu kiểm chứng riêng**, không đánh đồng “build nhanh hơn” với hit cả ba cache.

## 11. Ma trận thay đổi: cache nào có khả năng bị ảnh hưởng?

| Tác động | Dependency cache | Configuration cache | Task output / UP-TO-DATE |
| --- | --- | --- | --- |
| Sửa nội dung một file Java | Vẫn có thể reuse artifacts | Có thể reuse nếu không đọc source tại config time | `compileJava` input đổi, cần xử lý lại |
| Sửa `build.gradle` | Dependencies có thể vẫn đã cache | Thường invalidated | Có thể invalidated nếu task config/classpath/input thay đổi |
| Đổi version Spring Boot starter/plugin | Cần resolve metadata/artifacts mới | Thường invalidated | Classpath/tooling đổi, cache key có thể đổi |
| Chạy `clean` | Không xóa Gradle User Home module cache | Không nhất thiết xóa config entry | Xóa local outputs, nhưng build cache entries vẫn có thể reuse |
| Chạy `--offline` | Chỉ dùng dữ liệu local đã cache | Không tự bật/tắt | Task behavior vẫn theo inputs/outputs, có thể fail nếu thiếu dependency |
| Chạy `--refresh-dependencies` | Yêu cầu xác minh dependency mới | Có thể ảnh hưởng resolution/config validity tùy Gradle | Nếu resolved artifacts khác, task inputs/cache key có thể đổi |
| Chạy `--no-configuration-cache` | Không trực tiếp | Tắt reuse cấu hình lần đó | Không tự disable task output cache |
| Chạy `--no-build-cache` | Không trực tiếp | Không trực tiếp | Không lookup/store task output cache; local UP-TO-DATE vẫn có thể xảy ra |
| Chạy `--rerun-tasks` | Không bắt buộc tải lại deps | Không phải nút xóa config cache | Ép task actions chạy lại thay vì reuse outcome |
| Chạy trên CI máy mới | Cần populate/restore dependency cache | Không tự có local entry cũ | Có thể reuse remote build cache nếu được cấu hình/cho phép |

Các kết luận là **khả năng** dựa trên inputs và cấu hình chuẩn; khi plugin custom đọc source trong configuration hoặc có task input ẩn, behavior có thể khác. Đo bằng log/thống kê thật, không suy ra chỉ từ tên tham số.

## 12. Tương quan với Maven: repository cache và build cache extension

### 12.1. `~/.m2/repository` gần với cơ chế nào?

Maven có **local repository**, mặc định thường ở:

~~~text
~/.m2/repository/
~~~

Nó lưu downloaded artifacts từ remote repositories **và** artifacts được build/install tại máy. Vì vậy nó có điểm gần với **Gradle dependency cache**, nhưng không hoàn toàn tương đương: local Maven repository cũng là nơi `mvn install` xuất artifact của dự án, còn Gradle dependency cache có cấu trúc/metadata riêng.

Các lệnh Maven liên quan:

~~~bash
mvn dependency:tree
mvn -o package
mvn -U package
~~~

- `mvn -o` dùng offline mode, không tải dependency mới.
- `mvn -U` yêu cầu check updates cho SNAPSHOT/missing releases theo cơ chế Maven, không phải Gradle `--refresh-dependencies`.
- `mvn dependency:tree` cho resolved graph.

Không xóa `~/.m2/repository` toàn bộ chỉ vì dependency lỗi; có thể làm mất artifacts nội bộ đã `install` nhưng chưa publish. Điều tra đúng tọa độ, mirror, `settings.xml`, local repo configuration và POM trước.

### 12.2. Maven có Configuration Cache giống Gradle không?

Không nên nói Maven local repository là configuration cache. Maven `pom.xml`/lifecycle/plugin execution không có một cờ built-in trực tiếp tương đương Gradle `--configuration-cache` trong cách dùng cơ sở của bài học. Maven có nhiều tối ưu khác, nhưng không quy đồng chúng với cache Gradle.

### 12.3. Maven Build Cache Extension là cơ chế riêng

Apache Maven có **Maven Build Cache Extension** (yêu cầu Maven version phù hợp, tài liệu hiện hành nêu Maven 3.9+). Nó có thể fingerprint module inputs và restore outputs từ local/remote cache, hữu ích cho multi-module builds. Đây là **extension cần được bật/cấu hình**, không phải kết quả tự động chỉ vì đã có `~/.m2/repository`.

Ví dụ khai báo extension (chỉ dùng khi nhóm quyết định áp dụng, version phải được xác nhận):

~~~xml
<extensions>
    <extension>
        <groupId>org.apache.maven.extensions</groupId>
        <artifactId>maven-build-cache-extension</artifactId>
        <version>1.3.0</version>
    </extension>
</extensions>
~~~

Vị trí thường là tệp `.mvn/extensions.xml` của Maven project; đây **không phải `pom.xml` đầy đủ** và không cần thêm vào ứng dụng Spring Boot chỉ để học về cache. Trước khi dùng trên CI, kiểm tra compatibility Maven/plugin, config cache keys, reproducibility, test policies và remote cache trust.

### 12.4. So sánh nhanh

| Khái niệm | Gradle | Maven |
| --- | --- | --- |
| Cache artifacts đã tải | Dependency cache dưới Gradle User Home | Local repository `~/.m2/repository` |
| Cache kết quả configuration/ task graph | Gradle Configuration Cache | Không có đối tượng built-in tương ứng trong workflow Maven cơ sở |
| Cache outputs | Gradle Build Cache có local/remote | Maven Build Cache Extension nếu được cài/kiểm chứng |
| Bỏ dùng network | `--offline` | `-o` |
| Yêu cầu refresh dependency | `--refresh-dependencies` | `-U`, semantics khác |
| Làm sạch project output | `clean` task | `mvn clean` |
| Chạy build chuẩn | `./gradlew build` | `mvn package`/`mvn verify` |

Khi module Spring Boot dùng Maven, **đừng copy lệnh Gradle** như `--build-cache` vào `mvn`. Chọn công cụ tương ứng, đặt kỳ vọng đúng và theo dõi log.

## 13. CI/CD: cache nào nên chia sẻ?

### 13.1. Dependency cache trên CI

CI agents mới thường chưa có Gradle dependency cache, nên lần đầu phải tải artifacts. Có thể cache/restore dữ liệu Gradle User Home theo hướng dẫn chính thức của CI provider, với key dựa trên Gradle version, dependency lock/config và policy hệ thống. Cần chú ý:

- Tránh cache untrusted artifacts hoặc credentials/tokens.
- Không copy Gradle cache dưới process đang dùng rồi bỏ qua concurrency/corruption risks.
- Chỉ cache dữ liệu cần và theo cơ chế được hỗ trợ; một số thư mục Gradle User Home là state mang tính máy/process, không nên chia sẻ nguyên vẹn.
- Nếu dùng private Maven mirror/proxy, kiểm tra nguồn và policy của artifacts.

### 13.2. Configuration cache trên CI

Configuration cache là local state của build, không tự trở thành một remote cache chia sẻ qua nhiều agents. Với pipeline chạy hoàn toàn trên máy ephemeral, lần đầu tạo entry có thể không giúp lần tiếp theo trừ khi có cơ chế lưu/restore chính thức phù hợp. Dùng `--configuration-cache` trên CI cần kiểm chứng plugin task compatibility và lợi ích thực tế.

Không upload thô `.gradle/configuration-cache` lên một public artifact store vì có thể chứa cấu hình/secret-derived state.

### 13.3. Remote build cache

Remote Gradle Build Cache có thể mang lợi ích lớn nếu nhiều developers/CI build cùng code và tasks được thiết kế cacheable/relocatable. Tuy nhiên:

- Chỉ kết nối đến endpoint có quyền truy cập, TLS và cơ chế xác thực phù hợp.
- Quy định ai **được push** và ai chỉ **được pull**; một số nhóm chỉ cho CI trusted branch ghi vào remote cache.
- Không nhận outputs từ cache không tin cậy, vì outputs có thể là binaries/scripts được thực thi/đóng gói.
- Cache keys phải phản ánh thực sự compiler options, runtime/toolchains, generated source config, annotation processors, environment.
- Chạy cold-build validation và so sánh artifact khi triển khai lần đầu; không ưu tiên tốc độ trước correctness.

Build cache làm giảm lặp công việc, **không thay thế kiểm thử, supply-chain security, artifact signing và provenance**.

## 14. Vì sao cache không được sử dụng dù đã bật?

### 14.1. Configuration cache miss

Những lý do thường gặp:

- Build script/settings/version catalog hoặc buildSrc thay đổi.
- Requested tasks khác giữa hai lệnh.
- Environment/Gradle/JVM inputs ảnh hưởng configuration thay đổi.
- Một plugin/task vi phạm configuration-cache requirements.
- Logic đọc filesystem/environment tại configuration time khiến fingerprints thay đổi.

Cách điều tra:

~~~bash
./gradlew help --configuration-cache --info
~~~

Đọc report về configuration cache và nguyên nhân invalidation. Nếu plugin không tương thích, cập nhật plugin hoặc sửa custom build logic; tạm tắt configuration cache cho task không phù hợp thay vì xóa cache rồi làm lại vô hạn.

### 14.2. Build cache miss

Nguyên nhân thường gặp:

- Task không được khai báo cacheable hoặc caching bị disable.
- Inputs đổi: Java source, classpath, compiler options, toolchain, resource, task implementation.
- Output không deterministic hoặc chứa dữ liệu phụ thuộc thời gian/máy.
- Task không khai báo đầy đủ inputs/outputs hoặc outputs không thể cache.
- Remote cache không reachable hoặc entry chưa từng được store.

Kiểm tra:

~~~bash
./gradlew compileJava --build-cache --info
~~~

Có thể Gradle cho biết vì sao caching bị disabled hoặc key thay đổi. `FROM-CACHE` không nhất thiết xuất hiện nếu task đang `UP-TO-DATE`; đó không phải lỗi.

### 14.3. Dependency cache không hit

Các khả năng:

- Dynamic/changing dependency tới hạn TTL.
- Repository URL/layout/mirror đổi.
- Artifact mới, chưa có cache.
- Gradle wrapper/version khác và metadata format/cache context thay đổi.
- Cache eviction hoặc CI agent mới.
- Proxy/credentials/repository bị chặn hoặc checksum mismatch.

Hãy xem log resolution, `dependencyInsight`, settings và mạng trước khi đụng đến cache directory.

## 15. Bảng chẩn đoán lỗi phổ biến

| Hiện tượng | Cơ chế nên kiểm tra | Hành động có giá trị |
| --- | --- | --- |
| Gradle tải lại JAR ở mỗi lần chạy | Dependency cache/repository | Xem TTL, changing modules, mirror và Gradle User Home |
| Chạy offline báo thiếu module | Dependency cache | Chạy online đầy đủ một lần; kiểm tra JAR/metadata đã cache |
| Bật `--refresh-dependencies` nhưng không download lại mọi file | Hành vi đúng của dependency cache | Gradle có thể xác minh checksum và reuse artifact không đổi |
| Build script được đánh giá lại mỗi lần | Configuration cache tắt/miss | Dùng `--configuration-cache`, xem invalidation/compatibility |
| `--configuration-cache` báo plugin task không hợp lệ | Configuration-cache requirements | Sửa plugin/build logic hoặc tắt tạm workflow |
| Task `compileJava UP-TO-DATE` dù build cache đã tắt | Local up-to-date checks | Đây là bình thường; `--no-build-cache` không ép chạy |
| Sau `clean` task `FROM-CACHE` | Task output cache | Output được restore từ cache bên ngoài workspace |
| Sau `clean` vẫn download dependency? | Không nhất thiết do clean | Kiểm tra cache còn/đã expire và repo resolution |
| Bật `--build-cache` nhưng task chạy thật | Cache miss hoặc task không cacheable | `--info` và kiểm tra inputs/cache policy |
| `bootJar` nhanh nhưng test chưa chạy | Task graph, không phải cache | Chạy `build`/`test` phù hợp; packaging không phải JUnit test |
| Hai máy build ra bytes khác dù source giống | Determinism, environment, toolchain | Kiểm tra task inputs/reproducible archives và plugin versions |
| CI nhận artifact không đúng phiên bản | Cache correctness/trust | Kiểm tra remote cache provenance, key và publish workflow |
| Maven local repo có JAR nhưng `mvn package` vẫn compile | Hai cache khác nhau | Repo giải quyết dependency, không tự cache outputs của module |
| Xóa `build` nhưng dependency vẫn dùng được offline | Dependency cache còn trong user home | Đây là kỳ vọng; `clean` chỉ dọn outputs project |
| Task `FROM-CACHE` nhưng sau đó test fail | Cache output không thay cho test hoặc môi trường đổi | Điều tra test runner, test inputs, integration environment |

**Không dùng thao tác “xóa sạch cache” làm giải pháp đầu tiên.** Nó làm mất dữ liệu điều tra, tốn network/CPU và thường không sửa nguyên nhân gốc như version conflict, plugin incompatibility hay undeclared inputs.

## 16. Bài tập có đáp án

### Bài 1. Tốc độ download khác tốc độ compile

**Tình huống:** sau lần đầu, Gradle không còn tải Spring Boot starter nhưng sửa một file Java khiến `compileJava` chạy lại. Cache nào đang hoạt động?

**Đáp án:** dependency cache có thể đang reuse artifacts; thay đổi source làm input của task compile thay đổi. Không có mâu thuẫn.

### Bài 2. Task UP-TO-DATE

**Tình huống:** chạy `./gradlew compileJava --no-build-cache` vẫn thấy `UP-TO-DATE`. Có phải Gradle bỏ qua cờ tắt cache?

**Đáp án:** không. `--no-build-cache` tắt task output cache, nhưng local up-to-date checks vẫn có thể bỏ thực thi task khi outputs và inputs chưa đổi.

### Bài 3. Sau clean lại FROM-CACHE

**Tình huống:** sau khi chạy `./gradlew clean compileJava --build-cache`, log ghi `compileJava FROM-CACHE`. Gradle có chạy lại compiler không?

**Đáp án:** không trong trường hợp task được restore từ build cache; output phù hợp key đã có sẵn và được khôi phục. Việc một output file có timestamp mới không tự chứng minh compiler vừa chạy.

### Bài 4. Configuration cache vẫn hit khi đổi Java source

**Tình huống:** thay code trong `src/main/java` nhưng lần chạy `build --configuration-cache` vẫn reuse configuration cache, sau đó compileJava chạy lại.

**Đáp án:** hợp lý nếu build logic không đọc source content ở configuration. Cached task graph/configuration vẫn dùng được; compilation inputs đã đổi nên execution cần xử lý lại.

### Bài 5. Offline không tìm thấy plugin

**Tình huống:** `./gradlew build --offline` thất bại vì plugin/version chưa được resolve tại máy, dù vài starter JAR đã có.

**Đáp án:** offline yêu cầu mọi metadata/artifacts liên quan đều có sẵn (cả build plugins). Chạy online ở môi trường đã cấu hình repository đúng trước; không coi vài file JAR trong cache là đầy đủ.

### Bài 6. Remote cache trên máy CI

**Tình huống:** build của nhánh không tin cậy có thể push binary outputs vào remote cache mà nhánh release sẽ đọc.

**Đáp án:** cấu hình này có rủi ro supply chain/correctness. Phân quyền push/pull, chỉ cho trusted CI jobs ghi và bảo đảm endpoint/keys/output validation.

### Bài 7. Maven local repo

**Tình huống:** `~/.m2/repository` có Spring Boot dependencies nhưng Maven vẫn thực hiện biên dịch lại module.

**Đáp án:** local repository hỗ trợ dependency download/resolution và installed artifacts, **không tự là task output cache**. Muốn build output caching cho Maven cần công cụ/extension có cấu hình phù hợp, ví dụ Maven Build Cache Extension.

### Bài 8. Sửa dependency stale

**Tình huống:** đội dùng SNAPSHOT, Gradle chưa thấy bản vừa publish.

**Đáp án:** kiểm tra TTL cho changing dependencies, dependency graph và repository; có thể dùng `--refresh-dependencies` để Gradle xác minh lại. Không xóa `build` rồi kỳ vọng download cache bị reset.

### Bài 9. Hai cờ cùng bật

**Tình huống:** team bật `org.gradle.caching=true` và `org.gradle.configuration-cache=true`. Có nghĩa mỗi lần gọi `build` đều không chạy task nào không?

**Đáp án:** không. Configuration cache chỉ tiết kiệm cấu hình khi hit; build cache chỉ áp dụng cho cacheable task output khi key khớp. Tasks vẫn có thể EXECUTED, NO-SOURCE, SKIPPED hoặc UP-TO-DATE.

### Bài 10. Kiểm tra kết quả build thực tế

**Tình huống:** lần build thứ hai nhanh hơn 50%, nhưng người đo không ghi logs hay breakdown. Có thể kết luận “remote build cache tiết kiệm 50%” không?

**Đáp án:** không. Daemon, filesystem page cache, dependency downloads, configuration cache, incremental compilation, up-to-date checks và task output cache đều tác động thời gian. Cần đo có đối chứng và quan sát outcomes trước khi gán nguyên nhân.

## 17. Checklist áp dụng tối ưu cache

- [ ] Có Gradle wrapper/JDK nhất quán, build thành công khi **không dựa vào cache**.
- [ ] Dependency versions/repositories/BOM ổn định; hạn chế dynamic versions trong release.
- [ ] Dependency cache được kiểm tra bằng resolution logs và offline test có điều kiện.
- [ ] Configuration cache được bật thử với workflow rõ ràng, đã xử lý các compatibility problems.
- [ ] Build cache được bật khi tasks cacheable, inputs/outputs đầy đủ và reproducibility phù hợp.
- [ ] Phân biệt rõ log `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE` và actual task execution.
- [ ] Đã thử lệnh `clean compileJava --build-cache` để thấy sự khác biệt với local outputs.
- [ ] Không dùng `--refresh-dependencies` thay thế việc invalidate configuration/task outputs.
- [ ] Không dùng `--no-build-cache` khi mục tiêu là tắt configuration cache, và ngược lại.
- [ ] Custom tasks không đọc thời gian/secret/environment tùy tiện mà thiếu input declarations.
- [ ] CI remote cache được giới hạn quyền và kiểm soát tính tin cậy, không share raw configuration cache.
- [ ] Tests, packaging và security checks vẫn được chạy theo chính sách dù cache hits có thể tiết kiệm work.
- [ ] Cache invalidation và nguồn cache miss được theo dõi qua logs/diagnostics, không “xóa sạch” vô điều kiện.

**Tổng kết:** **Dependency cache** tiết kiệm tải và resolve thư viện; **Configuration cache** tiết kiệm dựng lại cấu hình/task graph; **Build cache** tiết kiệm thực thi các task cacheable bằng cách restore outputs. Cả ba kết hợp được, nhưng **chúng cache ba loại dữ liệu khác nhau và không tự chứng minh build đúng**. Chỉ tối ưu sau khi đã bảo đảm dependency resolution, inputs/outputs và kiểm thử đáng tin cậy.

## 18. Tài liệu chính thức

- Gradle — Dependency Caching: https://docs.gradle.org/current/userguide/dependency_caching.html
- Gradle — Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache.html
- Gradle — Enabling and Configuring Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache_enabling.html
- Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
- Gradle — Build Cache Concepts / Cache Keys: https://docs.gradle.org/current/userguide/build_cache_concepts.html
- Gradle — Command-Line Interface, performance flags: https://docs.gradle.org/current/userguide/command_line_interface.html
- Maven — Local Repositories: https://maven.apache.org/repositories/local.html
- Maven — Maven Build Cache Extension, Overview: https://maven.apache.org/extensions/maven-build-cache-extension/concepts.html
- Maven — Maven Build Cache Extension, Getting Started: https://maven.apache.org/extensions/maven-build-cache-extension/
- Spring Boot — Gradle Plugin 3.3, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html

Với môi trường production, đối chiếu tài liệu theo **Gradle wrapper, Spring Boot Plugin và Maven version đang chạy**. Các ví dụ CLI trên mô tả cách học và kiểm chứng cơ chế cache, không phải mệnh lệnh bật tất cả cache trong một CI pipeline chưa được kiểm thử.
