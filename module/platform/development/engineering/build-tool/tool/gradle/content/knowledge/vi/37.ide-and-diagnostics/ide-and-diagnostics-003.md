# Gradle sync, tải dependency và phân biệt với thực thi task

## 1. Ba hiện tượng trông giống nhau nhưng khác mục đích

Một project Java 17 mở trong IntelliJ IDEA hoặc Android Studio. IDE hiện thông báo **Syncing Gradle project**, tiếp theo là **Downloading dependencies**, rồi báo **Gradle sync finished**. Developer tưởng chương trình đã được build và test xong, nhưng sau đó bấm **Run** lại thấy Gradle chạy `compileJava`, `classes`, `run` hoặc tải thêm JAR.

Điều này hoàn toàn có thể bình thường. Cần phân biệt ba hoạt động:

1. **IDE Gradle sync / reload / import**: IDE yêu cầu Gradle cung cấp mô hình project để hiển thị modules, source roots, classpaths, language levels, tasks, project dependencies và thông tin IDE cần.
2. **Dependency resolution / downloading**: Gradle chọn module/version/variant, đọc metadata và có thể tải POM, Gradle Module Metadata, JAR, sources/Javadoc, toolchains hoặc plugins. Việc này **có thể diễn ra trong sync**, nhưng cũng có thể diễn ra sau đó khi một task được yêu cầu.
3. **Gradle task execution**: Gradle tạo task graph và chạy những tasks được yêu cầu, như `compileJava`, `test`, `jar`, `run` hay một task chuẩn bị đặc thù cho IDE.

Một sync thành công **không chứng minh application đã biên dịch thành công, tests đã pass hoặc JAR đã được tạo**. Ngược lại, một lệnh Gradle CLI có thể resolve dependencies và hoàn tất compilation mà IDE vẫn hiển thị lỗi import vì model settings/IDE Gradle JVM không khớp.

Bài thuộc chủ đề **IDE và chẩn đoán** của module **Build Tool Gradle**, tập trung vào câu hỏi thực tế: **đang sync, đang tải dependency hay đang thực thi task — xác định bằng cách nào và xử lý đúng tầng ra sao?**

### 1.1. Kết quả học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của **Gradle Tooling API** và việc IDE đồng bộ mô hình Gradle project.
- Phân biệt **initialization, configuration và execution** với các pha IDE import và network downloads.
- Hiểu vì sao tải dependencies **không đồng nghĩa** `compileJava`/`test` đã chạy.
- Biết rằng **một số quá trình import có thể yêu cầu tasks**, chẳng hạn code-generation/preparation tasks hoặc tác vụ đặc thù của IDE/plugin.
- Hiểu những repository scopes: `pluginManagement.repositories`, `dependencyResolutionManagement.repositories`, project `repositories` và legacy `buildscript.repositories`.
- Phân biệt tải Gradle Wrapper distribution, plugin, library artifact, dependency metadata, `-sources.jar`, `-javadoc.jar` và Java toolchain.
- Sử dụng `--offline`, `--refresh-dependencies`, `--info`, `dependencies` và `dependencyInsight` đúng ý nghĩa.
- Biết khi nào `--rerun-tasks`, `--no-build-cache`, `--stop` hoặc xóa IDE cache **không giải quyết** lỗi dependency resolution.
- Chẩn đoán plugin not found, could not resolve, missing variant, proxy/TLS/authentication, Gradle JVM/toolchain mismatch và lỗi model import.
- Xây dựng một Gradle Java 17 project runnable có external Maven dependency, kiểm sự khác biệt giữa sync, resolution, task action và main method.
- Phân biệt **IDE Build/Run** được delegate cho Gradle với **IDE native compiler/test runner**.
- Thiết kế checklist giảm rủi ro khi đồng bộ multi-project build và khi chuyển môi trường local/CI.

## 2. Mô hình ba lớp: IDE, Gradle và repository

Một sơ đồ đơn giản:

~~~text
IntelliJ IDEA / Android Studio
  |
  | Sync / Reload project
  v
Gradle Tooling API client
  |
  | hỏi model (projects, source sets, classpath, tasks...)
  v
Gradle build engine / Daemon
  |
  +--> Initialization:
  |      settings.gradle.kts, include projects
  |
  +--> Configuration:
  |      build.gradle.kts, apply plugins, register tasks
  |
  +--> Model query:
  |      resolve những configurations IDE cần
  |      tạo mô hình source roots, modules, dependencies
  |
  +--> Có thể yêu cầu tasks trước/kèm model query
  |      tùy IDE, plugin và import mechanism
  |
  +--> Repository resolution (nếu cần):
         plugin marker / POM / .module / JAR / sources / Javadoc
           |
           v
         Gradle dependency caches
~~~

Khi developer chọn **Run Gradle task** thì IDE cũng có thể dùng Tooling API, nhưng yêu cầu lần này nhắm vào **task execution**. Tooling API có cả API **query models** và **run builds**; vì vậy không thể suy luận “Tooling API = không chạy task”.

### 2.1. IDE sync là gì?

Trong một Gradle-linked project, sync thường nhằm:

1. Đọc danh sách root và subprojects.
2. Nhận biết source sets (ví dụ `src/main/java`, `src/test/java`).
3. Nhận dependencies dùng để xây editor classpath và classpath cho tasks.
4. Nhận Java language level/toolchain metadata.
5. Nhận generated source roots, resources, tasks và project relations.
6. Cập nhật project/module representation trong IDE.
7. Cho phép code completion, import class, navigation và inspections.
8. Hiển thị Gradle tasks trong Gradle tool window.

Tên nút thay theo IDE/version: **Sync Gradle Project**, **Reload All Gradle Projects**, **Load Gradle Changes**, hoặc trong Android Studio thường là **Sync Project with Gradle Files**.

### 2.2. Dependency resolution là gì?

Trong Gradle, `dependencies { implementation("group:module:version") }` **khai báo yêu cầu**, chưa nhất thiết tải JAR tại thời điểm khai báo. Khi một configuration như `compileClasspath` hoặc `runtimeClasspath` được **resolve**, Gradle:

- Chọn repository phù hợp.
- Tìm metadata module (Maven POM hoặc Gradle Module Metadata).
- Giải graph transitives và version/variant constraints.
- Chọn các artifacts cần thiết theo attributes.
- Tải metadata/artifacts còn thiếu trong cache, nếu network được phép.
- Tận dụng Gradle User Home dependency cache cho các lần sau.

IDE có thể yêu cầu resolved compile/test classpaths trong quá trình import. Vì thế **sync có thể tải library JAR mà không chạy `compileJava`**.

### 2.3. Task execution là gì?

Gradle task có actions để thực hiện việc cụ thể, ví dụ:

~~~text
:compileJava  -> gọi Java compiler khi cần
:test         -> thực thi JUnit/TestNG tests
:jar          -> tạo project JAR
:run          -> chạy Java main class
:dependencies -> tạo dependency report
:help         -> hiển thị Gradle help
~~~

Điểm tinh tế: `./gradlew dependencies` **có thực thi một reporting task**, đồng thời có thể resolve dependency graph. Nó **không** biên dịch application. Vì vậy đừng đồng nhất “có task execution” với “đã build code”.

### 2.4. Một tác vụ IDE có thể làm cả ba việc

Tooling API cho phép IDE hỏi model và, khi được yêu cầu, lên lịch preparatory tasks. Ví dụ source generation có thể cần chạy để IDE thấy generated source roots. Một số plugin cố ý resolve dependencies hoặc làm I/O trong **configuration**, làm sync có log giống task execution. Cần xem **task path/outcome và stacktrace**, không chỉ nhìn thanh tiến trình ghi “Sync”.

## 3. Mối quan hệ với ba giai đoạn Gradle

Gradle thường diễn tiến qua:

| Giai đoạn | Gradle làm gì? | Sync có thể gặp? |
| --- | --- | --- |
| **Initialization** | Tìm settings/root project, include projects | Có |
| **Configuration** | Evaluate build scripts, apply plugins, tạo/configure task model | Có |
| **Execution** | Thực thi các task actions đã được scheduled | Có thể có, tùy lời gọi |
| **Model query** | Tooling API đọc/mapping mô hình mà IDE cần | Là trọng tâm sync |
| **Dependency resolution** | Resolve classpaths, plugin dependencies, artifacts khi được yêu cầu | Có thể xuất hiện ở nhiều giai đoạn |

**Model query** và **dependency resolution** không phải “giai đoạn thứ tư, thứ năm” chính thức của Gradle build lifecycle; bảng dùng để chỉ những hoạt động thường thấy **gắn với** ba giai đoạn chuẩn.

### 3.1. Initialization có thể fail trước khi thấy một task

Ví dụ:

~~~kotlin
// settings.gradle.kts
rootProject.name = "sync-demo"
include(":api", ":app")
~~~

Nếu một included project path sai hoặc settings plugin không resolve được, sync có thể fail sớm. Chạy `:app:compileJava` cũng sẽ fail khi Gradle không initialize được build.

### 3.2. Configuration có thể có side effects

Một anti-pattern:

~~~kotlin
// Không nên dùng trong build thật
println("Configuring project: " + project.path)
~~~

Dòng này có thể chạy khi IDE query model **trước khi task actions được thực thi**. Nếu build script viết:

~~~kotlin
val data = java.net.URL("https://example.org/data").readText()
~~~

ngay ở top-level configuration, sync còn có thể tạo network request **không liên quan tới dependency repository**. Đó là lý do cần thiết kế build logic tránh network/disk side effects trong configuration và dùng Provider API/lazy tasks.

Hai snippets trên là **anti-pattern minh họa**, không thuộc project lab runnable ở phần sau.

### 3.3. Task registration khác task execution

~~~kotlin
tasks.register("greet") {
    doLast {
        println("TASK_ACTION_EXECUTED=YES")
    }
}
~~~

Khi Gradle evaluate script, task `greet` được **đăng ký**. `doLast` chỉ chạy nếu task được đưa vào task graph và Gradle thực thi nó. Sync có thể nhìn thấy task `greet` trong IDE mà dòng `TASK_ACTION_EXECUTED=YES` chưa từng xuất hiện.

### 3.4. Cẩn thận với Configuration Cache

Nếu `org.gradle.configuration-cache=true` và cache entry được reuse, Gradle có thể bỏ qua phần configuration ở lần gọi sau. Không thấy một `println` ở configuration **không chứng minh sync chưa chạy**, cũng không chứng minh một task được thực thi. Với thí nghiệm cần quan sát configuration, dùng invocation kiểm soát `--no-configuration-cache`.

## 4. Tại sao sync thường kéo theo download?

### 4.1. IDE cần external libraries để hỗ trợ editor

Để biết `org.apache.commons.lang3.StringUtils` nằm ở đâu, IDE cần compiled library artifacts hoặc mô hình classpath hợp lệ. Khi project khai Maven dependency nhưng cache chưa có, Gradle có thể truy Maven Central trong lúc IDE sync.

Tương tự, nếu Kotlin/Android plugin cung cấp model cần additional components, Gradle có thể resolve chúng ngay khi import.

### 4.2. Thời điểm download không cố định

Một declared dependency có thể được resolve:

- Khi Gradle apply plugin/script và plugin chủ động resolve configuration.
- Khi Tooling API/IDE yêu cầu model chứa resolved classpaths.
- Khi `:dependencies`/`:dependencyInsight` tạo report.
- Khi `:compileJava` cần các JAR trên compile classpath.
- Khi `:test`/`:run` cần runtime artifacts.
- Khi IDE yêu cầu tải thêm **sources/Javadoc**.
- Khi một artifact transform hoặc source generator yêu cầu artifacts.

Vì vậy “sync lần đầu có download, sync lần hai không” có thể do cache đã ấm, không phải Gradle ngừng quản lý dependencies.

### 4.3. Download **metadata** khác download **JAR**

Một Maven module có thể có:

~~~text
group: org.apache.commons
name: commons-lang3
version: 3.17.0

Metadata:
  commons-lang3-3.17.0.pom
  Gradle Module Metadata nếu repo công bố
Artifact:
  commons-lang3-3.17.0.jar
Optional editor artifacts:
  commons-lang3-3.17.0-sources.jar
  commons-lang3-3.17.0-javadoc.jar
~~~

Gradle có thể đọc metadata để tạo dependency graph mà chưa cần tải JAR payload. Lệnh `dependencies --configuration runtimeClasspath` không bảo đảm mọi JAR của configuration đã được materialize. Task `compileJava` hoặc một model cần file paths có thể yêu cầu tải chúng.

### 4.4. Plugin JAR khác application library JAR

Plugin Gradle như `com.example.tooling` có thể được resolve khi build script apply plugin trong **configuration**, trước `compileJava`. Library `implementation("org.apache.commons:commons-lang3:3.17.0")` thuộc dependency graph của project.

Một plugin có thể chạy code ở configuration phase, tạo tasks/DSL và thêm dependencies. Đừng sửa `repositories { mavenCentral() }` của project khi lỗi thực tế là plugin marker không tìm được trong `pluginManagement.repositories`.

### 4.5. Sources và Javadoc cho IDE

IDE có tùy chọn download source attachments/documentation. Việc có `-sources.jar` hoặc `-javadoc.jar` trong cache giúp IDE điều hướng code/decompiled sources, **không có nghĩa Gradle đã compile application**.

Một số library không publish source/Javadoc artifacts; thiếu sources có thể chỉ ảnh hưởng khả năng đọc source trong IDE, không phải compilation. Phải đọc mức lỗi/warning và task statuses trước khi coi nó là build failure.

## 5. Phân biệt năm nhóm download thường gặp

| Loại | Triggers | Cache/path thường gặp | Khi lỗi nên xem |
| --- | --- | --- | --- |
| **Gradle distribution** | Wrapper cần version chưa cài | `~/.gradle/wrapper/dists/` | `gradle-wrapper.properties`, distribution URL, TLS/proxy |
| **Gradle plugin** | `plugins { id(...) version ... }` | Gradle dependency caches | `pluginManagement.repositories`, plugin marker |
| **Project dependency** | Compile/runtime/test classpath resolution | `~/.gradle/caches/modules-2/` | `dependencyResolutionManagement` hoặc project repositories |
| **IDE sources/Javadoc** | Attach sources/docs request | Gradle/IDE artifact caches | Source artifacts availability, IDE setting |
| **Java toolchain** | JDK17/21 launcher/compiler requested | Toolchain provisioning locations | JDK installation, toolchain resolver, Gradle JVM requirements |

Đường `~/.gradle` là Gradle User Home mặc định trên Unix-like OS; nó thay đổi khi cấu hình `GRADLE_USER_HOME` và trên Windows. Không mặc định mọi download được giữ trong project `build/`.

### 5.1. Wrapper download

Nếu project có:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.0-bin.zip
~~~

trong `gradle/wrapper/gradle-wrapper.properties`, Wrapper có thể tải **Gradle distribution ZIP**. Đó không phải library dependency `group:module:version` và không được chữa bằng `--refresh-dependencies`.

Đường URL/version trên chỉ là **ví dụ của một distribution hợp lệ**; project thực nên pin bản Gradle Wrapper đã qua kiểm thử và bảo vệ checksum khi cần.

### 5.2. Plugin resolution

Nếu build script:

~~~kotlin
plugins {
    id("org.example.some-plugin") version "1.2.3"
}
~~~

mà plugin repository không có ID/version này, bạn có thể gặp "Plugin ... was not found". Đây là snippet **minh họa ID giả**, không phải dependency runnable. Khi đọc lỗi, kiểm plugin ID/marker, repository URL và plugin version — không đổi Java source imports.

### 5.3. Project dependency resolution

Ví dụ thật:

~~~kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
~~~

Gradle lấy external module từ Maven repository được khai. Nếu metadata được tìm thấy nhưng variant không match requested attributes (JVM target, usage, capabilities...), bạn có thể gặp **No matching variant** thay vì lỗi HTTP/download thuần túy.

### 5.4. Java toolchain auto-provisioning

Nếu project yêu cầu Java17 toolchain nhưng máy có chỉ JDK21, Gradle có thể tìm một Java17 installation hoặc provision thông qua configured toolchain resolver. Lỗi `No matching toolchains found` không mặc định là lỗi Maven library.

### 5.5. Maven Central không phải nơi Gradle Wrapper lấy ZIP

Wrapper distribution download dùng URL distribution của Wrapper; Maven Central dùng để resolve libraries. Cấu hình proxy/firewall áp dụng có thể giống nhau ở mạng công ty nhưng **cấu hình repos và cache là các tầng khác**.

## 6. Repositories: đặt đúng chỗ

Gradle có nhiều repository scopes; nhầm chúng là nguyên nhân rất phổ biến khiến sync fail dù đường mạng bình thường.

### 6.1. Repository cho plugins

Trong `settings.gradle.kts`:

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}
~~~

Đây là nơi Gradle tìm plugins khai bởi `plugins { id("...") version "..." }` theo plugin resolution mechanism. Core plugins như `id("java")` hoặc `id("application")` có sẵn trong Gradle distribution, không cần tải plugin marker ngoài mạng.

### 6.2. Repository cho libraries

Cũng trong `settings.gradle.kts`:

~~~kotlin
dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
~~~

Nó khai Maven Central cho **project dependencies**; không tự làm external Gradle plugins resolve được nếu plugin repository chưa được cấu hình phù hợp.

### 6.3. Đặt project repositories trong build script

Nếu không centralize repositories ở settings:

~~~kotlin
repositories {
    mavenCentral()
}
~~~

trong `build.gradle.kts` là một cách chuẩn. Đừng đặt cùng một repo ở nhiều scopes chỉ vì tưởng Gradle sẽ resolve nhanh hơn. Với tổ chức có policy dùng `RepositoriesMode.FAIL_ON_PROJECT_REPOS`, khai thêm project repositories sẽ bị báo lỗi **theo chính sách**.

### 6.4. Centralize với FAIL_ON_PROJECT_REPOS

Một cấu hình settings thường dùng:

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(
        RepositoriesMode.FAIL_ON_PROJECT_REPOS
    )
    repositories {
        mavenCentral()
    }
}
~~~

Nếu một subproject/plugin thêm `repositories { ... }` sau đó, build có thể fail với message về repositories mode. Đây không phải Maven Central down; policy ngăn project-level repository additions. File settings của project lab ở phần 9 dùng cùng nguyên tắc.

### 6.5. buildscript.repositories là cơ chế khác

Legacy plugin/dependency classpath:

~~~kotlin
buildscript {
    repositories {
        mavenCentral()
    }
    dependencies {
        classpath("org.example:legacy-build-plugin:1.0.0")
    }
}
~~~

là snippet **không runnable** vì GAV chỉ để minh họa. Nó cấu hình classpath để chạy build script legacy; không thay `pluginManagement.repositories` hoặc project `implementation` repositories.

### 6.6. Repository order và content filters

Nếu hai repositories chứa cùng module GAV nhưng artifacts khác nhau, thứ tự và repository identity/cache behavior có ý nghĩa. Gradle có repository metadata caching và cơ chế **repository stickiness**: artifact đã được resolve từ repo A không đơn giản được chuyển sang repo B trong mọi tình huống. Với corporate repos, dùng content filtering/exclusive content và policy công bố artifact rõ ràng để tránh dependency confusion.

Đừng thêm `mavenLocal()` lên đầu mọi project chỉ để “sync nhanh”: local Maven có thể chứa snapshot/test artifacts khác production CI và gây lỗi khó tái hiện.

## 7. Dependency cache: tại sao lần sau ít tải hơn?

Gradle cache metadata và artifacts trong Gradle User Home, điển hình:

~~~text
~/.gradle/
├── caches/
│   ├── modules-2/
│   │   ├── files-2.1/
│   │   └── metadata-*/
│   └── (các Gradle caches khác)
├── daemon/
└── wrapper/dists/
~~~

Đây là cây **mô tả cấp cao**, không phải cấu trúc bất biến qua mọi Gradle version. Project `.gradle/`, `build/` và IDE `.idea/` là các nơi khác.

### 7.1. Tại sao cache không đồng nghĩa “không bao giờ mạng”?

Gradle caching có quy tắc cho:

- Fixed versions (ví dụ `3.17.0`).
- Dynamic versions (ví dụ `1.+`).
- Changing versions/artifacts (ví dụ một số Maven `-SNAPSHOT`).
- Metadata của repository.
- Missing-module/negative lookup.
- Checksums/artifact identities.

Gradle có thể revalidate metadata theo TTL hoặc `--refresh-dependencies`. Một sync gần đây đã tải tất cả thì sync thứ hai ít network hơn, nhưng nếu version/repository/configuration đổi thì vẫn có requests.

### 7.2. Default TTL cho dynamic/changing modules

Theo Gradle dependency caching docs, **dynamic versions và changing modules** mặc định được cache khoảng 24 giờ. Việc cần update mới hơn có thể được điều chỉnh bằng resolution strategy.

Ví dụ:

~~~kotlin
configurations.configureEach {
    resolutionStrategy.cacheDynamicVersionsFor(10, "minutes")
    resolutionStrategy.cacheChangingModulesFor(4, "hours")
}
~~~

Đây là **fragment cấu hình tùy chọn**, không thuộc runnable project lab. TTL ngắn làm tăng repository/network requests; với CI/release hãy ưu tiên fixed versions và dependency locks thay vì dùng dynamic versions để mong “luôn mới”.

### 7.3. --offline

Lệnh:

~~~bash
./gradlew compileJava --offline
~~~

yêu cầu Gradle dùng dependencies đã có trong cache và không truy remote repositories để dependency resolution. Nếu một required module/JAR chưa tồn tại trong cache tương ứng, build sẽ fail.

**Quan trọng:** `--offline` không có nghĩa “bỏ qua dependencies” hoặc “tự tạo artifact”; nó cũng không cho phép một project mới chưa từng cache toàn bộ buildscript/plugins/toolchains đột nhiên compile được.

### 7.4. --refresh-dependencies

Lệnh:

~~~bash
./gradlew compileJava --refresh-dependencies
~~~

buộc Gradle re-evaluate/revalidate dependency resolution state theo repository. **Nó không bắt buộc tải lại từng JAR byte-for-byte** nếu server checksums/metadata cho thấy artifacts vẫn giống nhau. Vì vậy không dùng số lượng HTTP downloads để kết luận option “không hoạt động”.

### 7.5. --offline và --refresh-dependencies có nên dùng chung?

Thông thường không nên dùng như một “công thức sửa sync”: `--offline` cấm remote lookups, trong khi `--refresh-dependencies` hướng tới revalidation với repositories. Hãy chọn **một mục tiêu**: offline reproducibility hay online refresh/diagnostics.

### 7.6. Không xóa ~/.gradle để sửa lỗi đầu tiên

Xóa Gradle User Home làm mất dependency cache, Wrapper distributions, daemon state và có thể ảnh hưởng user-local properties. Nó không sửa credentials/repository URL sai, có thể làm sync chậm và xóa bằng chứng.

Tốt hơn: đọc root cause, thử targeted `--refresh-dependencies` khi metadata nghi stale, kiểm Gradle repo URL, proxy/TLS, và đúng requested dependency.

## 8. Sync không bằng build; build không bằng sync

### 8.1. Bảng đối chiếu hành vi

| Hoạt động | Có thể cấu hình project? | Có thể tải dependencies? | Có thực thi task actions? | Có tạo app JAR/test results mặc định? |
| --- | --- | --- | --- | --- |
| IDE **Sync / Reload** | Có | Có | Có thể nếu IDE/plugin yêu cầu | Không mặc định |
| `./gradlew help` | Có | Có thể (plugins/buildscript) | Có, task `help` | Không |
| `./gradlew tasks` | Có | Có thể | Có, reporting task `tasks` | Không |
| `./gradlew dependencies` | Có | Có, graph resolution | Có, reporting task `dependencies` | Không |
| `./gradlew compileJava` | Có | Có, compile classpath | Có, compiler task khi cần | Classes; chưa mặc định tạo JAR/tests |
| `./gradlew test` | Có | Có, test runtime | Có (compile/test graph) | Test results; có thể thêm classes/JAR theo graph |
| `./gradlew jar` | Có | Có, khi cần compile | Có | JAR khi thành công |
| `./gradlew run` | Có | Có, runtime classpath | Có, `JavaExec` | Application chạy, không tự xác nhận tests pass |
| IDE **Build Project** | Tùy delegate settings | Tùy | IDE compiler hoặc Gradle tasks | Phụ thuộc IDE/delegation |

Chữ **“Có thể”** là có chủ đích. Sync theo Tooling API có thể query model mà không lên lịch user tasks, nhưng một IDE/tooling plugin có thể schedule tasks trước/kèm model query. Không đặt quy tắc “sync tuyệt đối không chạy task”.

### 8.2. Gradle help vẫn thực thi một task

Khi bạn chạy:

~~~bash
./gradlew help
~~~

Gradle có task `help`. Nó phù hợp để kiểm Gradle project initialization/configuration **mà không compile application**, nhưng không phải “0 tasks”.

### 8.3. Dry run không có nghĩa không resolve dependency

~~~bash
./gradlew build --dry-run
~~~

Gradle dựng task graph và bỏ task actions của requested tasks. Nó vẫn phải initialize/configure; plugin/build logic có thể resolve dependencies trong configuration. Dry-run giúp xem **tasks sẽ chạy**, không thay thế IDE model import và không chứng minh build/test pass.

### 8.4. UP-TO-DATE/FROM-CACHE vẫn là task graph execution

Nếu `compileJava` hiện:

~~~text
> Task :compileJava UP-TO-DATE
~~~

Gradle đã xét task trong execution graph nhưng không cần chạy compiler action. Nếu hiện:

~~~text
> Task :compileJava FROM-CACHE
~~~

Gradle đã dùng Build Cache output. Hai tình huống này khác với việc IDE sync chỉ import model mà không yêu cầu compile task.

### 8.5. Task execution là gì trong log IDE?

Tìm những dấu hiệu:

~~~text
> Task :compileJava
> Task :test
> Task :generateSources
> Task :run
~~~

Đây là ví dụ task paths. Một IDE action có thể tạo log task tương tự nếu nó dùng Tooling API để run them. Nếu chỉ thấy download metadata hoặc Gradle model setup, không tự kết luận `:test` đã chạy.

## 9. Lab Java 17 runnable: cố ý tạo ba dấu hiệu khác nhau

Project này minh họa:

1. Một **external Maven dependency** có thể được resolve/download khi IDE sync.
2. Một thông điệp **configuration marker** chỉ hiện khi bật property `-PtraceConfiguration=true` (để phân biệt configuration).
3. Một thông điệp **task-action marker** chỉ xuất hiện khi explicit task `probeTaskExecution` chạy.
4. Một dòng **application stdout** chỉ xuất hiện khi `run` chạy Java main method.
5. Một JDK-only probe để thử `javac/java` độc lập.

Project có JUnit Jupiter test để chứng minh sync thành công **không đồng nghĩa tests pass**.

### 9.1. Cấu trúc thư mục

~~~text
sync-or-build-lab/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    ├── main/
    │   └── java/
    │       └── dev/example/sync/
    │           ├── App.java
    │           └── StandaloneProbe.java
    └── test/
        └── java/
            └── dev/example/sync/AppTest.java
~~~

Yêu cầu: JDK17, Gradle version hỗ trợ Java17, Maven Central truy cập được lần đầu hoặc dependencies đã nằm trong cache. Project mới chưa có Wrapper nên các ví dụ dùng `gradle` trong PATH; khi áp dụng cho team/CI, tạo và commit Wrapper ở version được tổ chức kiểm thử.

### 9.2. settings.gradle.kts đầy đủ

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(
        RepositoriesMode.FAIL_ON_PROJECT_REPOS
    )
    repositories {
        mavenCentral()
    }
}

rootProject.name = "sync-or-build-lab"
~~~

- `pluginManagement`: scope cho **non-core plugins** (lab chỉ dùng core Application plugin).
- `dependencyResolutionManagement.repositories`: scope cho Apache Commons Lang và JUnit.
- `FAIL_ON_PROJECT_REPOS`: source of truth repositories nằm tại settings; project không thêm `repositories { }`.
- `rootProject.name`: IDE model name và tên project.
- File không dùng URL JDK hard-coded hoặc credentials.

`RepositoriesMode` là Gradle Kotlin DSL type available trong settings script của các Gradle versions hiện đại hỗ trợ central repositories.

### 9.3. build.gradle.kts đầy đủ

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    id("application")
}

group = "dev.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")

    testImplementation(
        platform("org.junit:junit-bom:5.11.4")
    )
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly(
        "org.junit.platform:junit-platform-launcher"
    )
}

application {
    mainClass.set("dev.example.sync.App")
}

tasks.test {
    useJUnitPlatform()
}

if (
    providers.gradleProperty("traceConfiguration").orNull == "true"
) {
    logger.lifecycle("CONFIGURATION_MARKER=YES")
}

tasks.register("probeTaskExecution") {
    group = "verification"
    description = "Prints a marker when this task action runs"
    doLast {
        println("TASK_ACTION_MARKER=YES")
    }
}
~~~

Giải thích:

- `application` là Gradle **core plugin**, không cần tải plugin marker từ Plugin Portal.
- `java.toolchain=17` chọn compiler/launcher cho project tasks; Gradle daemon JVM có thể là JDK khác nhưng phải được Gradle version hỗ trợ.
- `options.release=17` giới hạn Java language/API target và bytecode.
- `implementation` khai **Commons Lang 3.17.0**, một Maven Central artifact có thật, dùng trong App.java.
- JUnit dependencies phục vụ `test`; không phải tất cả đều được tải ngay khi khai báo.
- `application.mainClass` định nghĩa Java main được `run` gọi.
- `traceConfiguration` là **opt-in marker**. Khi property bật và Gradle thực sự evaluate build script, logger in một dòng. Không coi nó là chuẩn logging dùng cho production, chỉ là dụng cụ học.
- `tasks.register` không chạy task action; `doLast` chỉ in khi `probeTaskExecution` được yêu cầu.
- Không có top-level network I/O hoặc `configurations...resolve()` ép eager resolution.

### 9.4. src/main/java/dev/example/sync/App.java

~~~java
package dev.example.sync;

import java.util.Locale;
import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static String formatted(String text) {
        return "SYNC_DEMO=" +
                StringUtils.upperCase(text, Locale.ROOT);
    }

    public static void main(String[] args) {
        System.out.println(formatted("gradle sync"));
    }
}
~~~

`StringUtils.upperCase(String, Locale)` đến từ Commons Lang. Đây là **điểm chứng minh phải có external dependency artifact** để compile App.java. Java standard library một mình không có `org.apache.commons.lang3.StringUtils`.

### 9.5. src/main/java/dev/example/sync/StandaloneProbe.java

~~~java
package dev.example.sync;

public final class StandaloneProbe {
    private StandaloneProbe() {
    }

    public static void main(String[] args) {
        System.out.println("STANDALONE_JAVA_MAIN=YES");
    }
}
~~~

Đây là Java17-compatible JDK-only program. Nó giúp so sánh **chạy `javac/java` trực tiếp** với Gradle sync mà không cần phải tự tra đường JAR trong Gradle cache.

### 9.6. src/test/java/dev/example/sync/AppTest.java

~~~java
package dev.example.sync;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

final class AppTest {
    @Test
    void formatsLabelUsingExternalLibrary() {
        assertEquals(
                "SYNC_DEMO=GRADLE SYNC",
                App.formatted("gradle sync")
        );
    }
}
~~~

Test này chỉ chạy khi `test` được yêu cầu qua CLI/IDE Gradle delegation hoặc một action thật sự lên lịch nó. Chỉ mở project/sync không tự xác nhận test đã pass.

### 9.7. Lệnh A: chỉ hỏi Gradle model/task list cơ bản

~~~bash
gradle help --console=plain
gradle tasks --all --console=plain
~~~

Lệnh đầu chạy `help` task; lệnh thứ hai chạy `tasks` reporting task. Không yêu cầu `compileJava`/`run`. Gradle vẫn có thể resolve **buildscript/plugin** dependencies cần cho configuration. Vì lab dùng core `application`, không cần tải binary Gradle plugin ngoài mạng.

### 9.8. Lệnh B: quan sát configuration nhưng không chạy App

~~~bash
gradle -PtraceConfiguration=true help \
    --no-configuration-cache --console=plain
~~~

Trên Windows PowerShell, gõ một dòng:

~~~powershell
gradle -PtraceConfiguration=true help --no-configuration-cache --console=plain
~~~

Khi build.gradle.kts được evaluate và property bật, log có dòng:

~~~text
CONFIGURATION_MARKER=YES
~~~

Đây là dấu hiệu configuration code chạy. Nhưng `help` task cũng chạy để hiển thị help. **Không thấy** `TASK_ACTION_MARKER=YES` và `SYNC_DEMO=GRADLE SYNC` vì chưa yêu cầu custom task hoặc application.

### 9.9. Lệnh C: chỉ yêu cầu dependency report

~~~bash
gradle dependencies --configuration compileClasspath \
    --console=plain
~~~

Lệnh này chạy `dependencies` **report task**, giải dependency graph của `compileClasspath`. Bạn sẽ thấy module `org.apache.commons:commons-lang3:3.17.0` khi resolution thành công.

**Không suy ra chắc chắn toàn bộ Commons Lang JAR đã download** chỉ từ dependency tree; tùy cách report/model query, việc cần bytes có thể diễn ra sau đó.

### 9.10. Lệnh D: compile Java thực sự

~~~bash
gradle compileJava --console=plain
~~~

Khi compile lần đầu, Gradle cần Commons Lang JAR trên compile classpath để `javac` resolve `StringUtils`. Nếu chưa cache, đây là một điểm rõ ràng phải lấy artifact từ Maven Central. Nếu lần sau không đổi source, `compileJava` có thể `UP-TO-DATE` hoặc `FROM-CACHE` tùy state.

Kiểm output:

~~~text
build/classes/java/main/dev/example/sync/App.class
build/classes/java/main/dev/example/sync/StandaloneProbe.class
~~~

Files .class chỉ xuất hiện sau compile thành công, không phải chứng cứ bắt buộc của một IDE sync thành công.

### 9.11. Lệnh E: chạy explicit task action

~~~bash
gradle probeTaskExecution --quiet
~~~

**Stdout chính xác** của task, với property `traceConfiguration` không bật:

~~~text
TASK_ACTION_MARKER=YES
~~~

Không có yêu cầu chạy App.java hay JUnit tests. Nếu IDE sync không chạy task này, bạn sẽ không thấy marker này; tuy nhiên điều đó **không chứng minh IDE sync không chạy bất kỳ task khác**.

### 9.12. Lệnh F: chạy Java application

~~~bash
gradle run --quiet
~~~

**Stdout chính xác** của Java main trong lab:

~~~text
SYNC_DEMO=GRADLE SYNC
~~~

Lệnh này chạy `run` task và những dependencies cần thiết để application có compiled classes/runtime classpath. Java main **không tự chạy chỉ vì Gradle sync thành công**.

### 9.13. Lệnh G: chạy JUnit

~~~bash
gradle test --console=plain
~~~

Khi JUnit dependencies có sẵn, `test` thực thi test runner và test method, tạo results/report dưới `build/test-results/test` và `build/reports/tests/test` theo conventions. Test không chạy khi chỉ yêu cầu `dependencies --configuration compileClasspath`.

### 9.14. Lệnh H: build JAR

~~~bash
gradle jar --console=plain
~~~

Tạo project JAR, ví dụ:

~~~text
build/libs/sync-or-build-lab-1.0.0.jar
~~~

JAR từ core Java/Application plugins thông thường **không tự nhúng Commons Lang external runtime JAR**. Khi chạy bằng `gradle run`, Gradle đặt dependency lên runtime classpath. Đừng dùng `java -jar build/libs/...jar` rồi kết luận sync sai nếu JAR không có Main-Class/fat dependencies đã được cấu hình.

### 9.15. Lệnh I: không dùng Gradle — javac/java độc lập

Từ `sync-or-build-lab`, Linux/macOS:

~~~bash
mkdir -p manual-out
javac --release 17 -d manual-out \
    src/main/java/dev/example/sync/StandaloneProbe.java
java -cp manual-out dev.example.sync.StandaloneProbe
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force manual-out | Out-Null
javac --release 17 -d manual-out src\main\java\dev\example\sync\StandaloneProbe.java
java -cp manual-out dev.example.sync.StandaloneProbe
~~~

**Stdout chính xác**:

~~~text
STANDALONE_JAVA_MAIN=YES
~~~

Ví dụ này chỉ compile/run JDK-only StandaloneProbe.java; nó **không** validate Gradle sync, dependency resolution hoặc JUnit. Nếu tự `javac App.java` mà không truyền Commons Lang JAR qua `--class-path`, compiler sẽ báo missing package — đây là lỗi thiếu external classpath trong lệnh javac, không phải bằng chứng rằng Gradle đã resolve sai.

## 10. Đưa lab vào IntelliJ IDEA/Android Studio

### 10.1. Import project

1. Mở IDE và chọn mở thư mục `sync-or-build-lab`.
2. IDE nhận diện `settings.gradle.kts` và `build.gradle.kts` là Gradle build.
3. Chọn Gradle distribution phù hợp: ưu tiên **Wrapper** nếu repo đã commit Wrapper, thay vì dùng Gradle version IDE cài sẵn ngẫu nhiên.
4. Chọn **Gradle JVM** (JDK được Gradle Wrapper/version hỗ trợ).
5. Kích hoạt **Sync / Reload Gradle Project**.
6. Mở Gradle/Build tool window, xem danh sách source sets, external libraries và tasks.

Vì lab có Maven Central dependency, lần import đầu có thể tải Commons Lang/JUnit metadata hoặc JARs. Chọn offline mode khi chưa cache sẽ có thể fail.

### 10.2. Sau sync, tìm gì?

IDE thường có:

~~~text
Modules / source roots:
  src/main/java
  src/test/java

External libraries:
  Commons Lang 3.17.0
  JUnit Jupiter/Platform dependencies

Gradle tool window:
  application/run
  build/compileJava
  verification/test
  verification/probeTaskExecution
  help/tasks
  help/dependencies
~~~

Đây là **minh họa nhóm tasks/IDE presentation**, không phải UI tree cố định qua mọi IDE/version. Gradle IDE model có thể hiển thị tasks theo categories khác nhau.

### 10.3. Bấm Sync có làm App.main chạy không?

Trong lab mặc định, mục tiêu sync là import model, **không có lý do phải chạy App.main**. Khi IDE không cấu hình special task hooks, bạn sẽ không thấy `SYNC_DEMO=GRADLE SYNC` trong output sync.

Tuy nhiên IDE/plugin có thể được cấu hình **Tasks Activation / After Sync** hoặc custom model builders để chạy tasks chuẩn bị. Vì thế luôn kiểm **Gradle Build output/task paths** thay vì tuyên bố tất cả sync tuyệt đối không chạy task.

### 10.4. Build/Run được delegate cho Gradle hay IDE?

Trong IntelliJ IDEA, settings thường nằm dưới:

~~~text
Settings / Preferences
  -> Build, Execution, Deployment
  -> Build Tools
  -> Gradle
~~~

Tại đây có lựa chọn như **Build and run using: Gradle / IntelliJ IDEA** và **Run tests using: Gradle / IntelliJ IDEA** (nhãn thay theo IDE release).

- Nếu **Gradle** được chọn, Build/Run/Test có thể gọi Gradle tasks.
- Nếu **IntelliJ IDEA** được chọn, IDE compiler/runner có thể chạy code mà không gọi Gradle tasks tương ứng.
- Nếu bạn dùng **Gradle task run configuration** trong tool window, đó là yêu cầu Gradle task rõ ràng.
- Đừng lấy việc class được IDE compile làm chứng cứ Gradle task `:compileJava` đã chạy.

### 10.5. Sync/Reimport có thể tự chạy khi file thay đổi

IDE có thể tự reload khi build scripts hoặc settings đổi, theo cấu hình **Auto-Reload / Sync after changes**. Không nhầm auto-sync sau chỉnh `build.gradle.kts` với auto-build sau chỉnh `App.java`; chúng đáp ứng loại thay đổi khác nhau.

### 10.6. After Sync task hooks

IntelliJ IDEA có tính năng **Tasks Activation** để chạy Gradle tasks tại các mốc như Before Build hoặc After Sync. Khi bật, một sync có thể đi kèm task execution do developer/team cấu hình. Với Android/Kotlin/Generated-code plugins, các task chuẩn bị còn có thể được yêu cầu bởi model import.

Vì thế chẩn đoán phải kiểm IDE task activation list và logs trước khi hỏi “Tại sao bấm Sync lại thấy `:generate...`?”.

## 11. IntelliJ Gradle JVM khác project Java toolchain

Hai cấu hình liên quan nhưng riêng biệt:

| Thiết lập | Tác dụng |
| --- | --- |
| **Gradle JVM** trong IDE | JVM chạy Gradle build engine/daemon |
| **Gradle Wrapper version** | Gradle distribution được dùng |
| **Java toolchain** trong build.gradle.kts | JDK cho `javac`, tests và tools theo tasks |
| `JavaCompile.options.release` | Java language/API/bytecode target |
| IDE **Project SDK** | JDK cho editor và IDE native build/runner theo settings |
| IDE **language level** | Syntax/inspections trong editor |

Ví dụ hợp lệ:

~~~text
IDE Gradle JVM: JDK 21
Gradle Wrapper: bản hỗ trợ Java 21
Project toolchain: JDK 17
Java bytecode target: 17
IDE Project SDK: JDK 17
~~~

Đổi Gradle JVM có thể khởi động daemon mới và làm IDE sync lại, nhưng không nhất thiết đổi compiled target. Đổi Project SDK không sửa `java.toolchain` của Gradle build; khi project reimport, Gradle model có thể tiếp tục quyết định module SDK/language-level settings.

### 11.1. Lỗi unsupported Gradle JVM

Nếu Gradle Wrapper không hỗ trợ JVM IDE đang chọn, sync có thể fail trước khi resolve application dependencies. Xem Gradle [compatibility matrix](https://docs.gradle.org/current/userguide/compatibility.html) của đúng version. Đừng chữa bằng cách chỉnh `implementation("...")` hoặc xóa Gradle dependency cache.

### 11.2. Toolchain provisioning khác dependency resolution

Nếu Java toolchain 17 không tồn tại, Gradle có thể báo không tìm thấy matching toolchain. Trong môi trường có configured toolchain resolver, Gradle có thể tải JDK. Đây không phải tải Maven Commons Lang; cần kiểm JDK installations, toolchain settings và Gradle JVM criteria.

### 11.3. Terminal vs IDE có thể dùng Gradle User Home khác nhau

Nếu IDE dùng `GRADLE_USER_HOME` hoặc Gradle user home location khác terminal, một bên có Maven cache còn bên kia chưa có. Khi terminal `./gradlew compileJava --offline` pass nhưng IDE Offline Work fail, hãy so Gradle User Home, JDK/Wrapper và repository settings trước khi kết luận IDE lỗi.

## 12. Dependency graphs và configurations

### 12.1. implementation không trực tiếp là classpath resolvable

Với Java plugins:

~~~kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
~~~

`implementation` thường là **declarable dependency bucket**, không phải configuration để bạn tùy tiện resolve trực tiếp. Gradle tạo các resolvable configurations như `compileClasspath` và `runtimeClasspath`.

### 12.2. compileClasspath vs runtimeClasspath

- `compileClasspath`: dependencies cần biên dịch main sources.
- `runtimeClasspath`: dependencies cần chạy application.
- `testCompileClasspath`: dependencies cần compile test sources.
- `testRuntimeClasspath`: dependencies cần chạy tests.

Các configurations có thể có versions/variants/dependencies khác nhau. IDE model muốn cung cấp editor support cho tests có thể resolve nhiều hơn một configuration.

### 12.3. Xem graph một configuration

~~~bash
gradle dependencies --configuration compileClasspath
gradle dependencies --configuration runtimeClasspath
gradle dependencies --configuration testRuntimeClasspath
~~~

Mỗi lệnh thực thi **dependencies reporting task** và tạo tree của configuration tương ứng. Khi một library không xuất hiện trong `compileClasspath` nhưng có ở `runtimeClasspath`, cần hiểu `runtimeOnly` vs `implementation` thay vì thêm JAR bằng tay vào IDE.

### 12.4. Vì sao một version được chọn?

~~~bash
gradle dependencyInsight \
    --dependency commons-lang3 \
    --configuration runtimeClasspath
~~~

`dependencyInsight` cung cấp thông tin dependency selection path và reasons khi Gradle hỗ trợ. Dùng đúng configuration; một artifact conflict ở `testRuntimeClasspath` có thể không xuất hiện nếu bạn chỉ inspect `compileClasspath`.

### 12.5. Dependencies task không giống jar download

`dependencies` thường phân tích module metadata/graph, còn `compileJava` cần actual compiled JAR bytes. Vì vậy:

~~~text
gradle dependencies --configuration compileClasspath
      -> thường đủ để thấy version graph
gradle compileJava
      -> cần Java classes trên compile classpath
~~~

**Chú ý:** tùy plugin/model/attributes, reporting task cũng có thể khiến artifact resolution; không coi “chỉ metadata” là quy tắc tuyệt đối. Ngược lại Gradle có thể dùng JAR cache và không gửi request mạng dù compileJava chạy.

### 12.6. Dependency constraints và locking

Nếu team dùng version catalog, platforms/BOM, dependency constraints hoặc dependency locking, version IDE hiển thị là **resolved version**, không nhất thiết literal version được khai ngay tại dependency statement. Trước khi kết luận IDE dùng “sai version”, chạy `dependencyInsight` và kiểm locks/constraints.

## 13. Offline mode và Refresh Dependencies trong IDE

### 13.1. IDE Offline Work

IntelliJ/Android Studio thường có tùy chọn **Offline Work** trong Gradle settings/tool window (UI thay theo bản). Về ý nghĩa, nó yêu cầu Gradle hoạt động offline cho resolution.

Nếu plugin, BOM, JAR hoặc metadata cần thiết chưa có trong Gradle User Home cache, sync có thể fail. Hãy chuyển online và sync khi được phép, **không** dùng dummy JAR để làm IDE thôi báo lỗi.

### 13.2. CLI --offline

~~~bash
gradle compileJava --offline
~~~

Dùng để kiểm khả năng build từ cache đã có. Nếu pass, điều này cho biết mọi dependencies mà invocation cần đã resolve được offline. Nó **không** chứng minh một build mới với clean Gradle User Home cũng chạy offline.

### 13.3. --refresh-dependencies

~~~bash
gradle compileJava --refresh-dependencies
~~~

Dùng khi nghi dependency metadata/dynamic/changing artifacts stale. Gradle thực hiện revalidation theo repository; **không bắt buộc download lại mọi JAR nếu checksum không đổi**. Nếu môi trường đang Offline Work, có thể cần tắt offline trước khi refresh.

### 13.4. IDE action và CLI flags là hai đường cấu hình

Một số IDE có nút refresh/reload project và tùy chọn refresh dependencies riêng. **Reload project** chủ yếu yêu cầu import model lại; nó không nhất thiết tương đương CLI `--refresh-dependencies`. Nếu cần chắc chắn dependency refresh, chạy command CLI với flag rõ ràng hoặc thiết lập IDE Gradle options mà bạn đã xác minh.

### 13.5. --rerun-tasks không sửa dependency graph

~~~bash
gradle test --rerun-tasks
~~~

buộc task actions chạy lại bất chấp up-to-date state, nhưng không “thay phiên bản dependency đã resolve thành bản mới” theo cách `--refresh-dependencies`. Nếu repository metadata sai hoặc version thiếu, rerun tasks vẫn gặp lỗi.

### 13.6. --no-build-cache không tắt dependency cache

~~~bash
gradle build --no-build-cache
~~~

tắt **task output cache** cho invocation, không tắt Gradle external module dependency cache. Nếu muốn chẩn đoán remote dependency issue, kiểm `--offline`/`--refresh-dependencies` và repositories, không chỉ tắt Build Cache.

### 13.7. --stop cũng không phải Refresh Dependencies

~~~bash
gradle --stop
~~~

dừng Daemon của cùng Gradle version để reset process state; nó **không xóa Maven dependency metadata/JAR cache**. Nếu plugin/dependency resolution vẫn lỗi, phải xử lý ở repo/JDK/network/cache đúng tầng.

## 14. Đọc lỗi Sync đúng theo nơi xảy ra

### 14.1. "Plugin [id: ...] was not found"

Nếu lỗi:

~~~text
Plugin [id: 'com.example.tool', version: '1.0.0'] was not found
~~~

đây là log ví dụ với plugin ID giả. Kiểm:

1. Plugin ID/version có tồn tại?
2. `pluginManagement.repositories` có đúng plugin repository?
3. Plugin marker/POM được publish chưa?
4. IDE/Gradle có offline không?
5. Repository authentication/proxy/TLS đang hoạt động?
6. Wrapper version có hỗ trợ plugin?
7. Plugin namespace có bị repository content filtering chặn?

Đừng chỉnh `dependencyResolutionManagement.repositories` rồi chờ plugin marker tự có nếu scope sai.

### 14.2. "Could not resolve ..."

Ví dụ:

~~~text
Could not resolve org.apache.commons:commons-lang3:3.17.0
~~~

Kiểm Maven Central repo URL, requested GAV/version, Gradle offline state, credentials/proxy/DNS/TLS, repository policies và metadata. Nếu dependency tồn tại trên Maven Central nhưng build dùng exclusive corporate repository, phải kiểm corporate mirror đã sync artifact chưa.

### 14.3. "No matching variant ..."

Đây thường là **attribute/variant compatibility problem**, không phải “JAR tải chưa xong”. Kiểm requested configuration/usage/JVM target/capabilities, Gradle Module Metadata và publisher variants. `--refresh-dependencies` không tự đổi một producer variant không tương thích.

### 14.4. "Unsupported class file major version"

Xem Gradle JVM, plugin bytecode, Kotlin DSL compiler/plugin compatibility, Java toolchain target và Gradle Wrapper. Đừng cho rằng `java { toolchain=17 }` sẽ tự làm Gradle engine chạy JDK17.

### 14.5. "PKIX path building failed" hoặc TLS

Một lỗi:

~~~text
javax.net.ssl.SSLHandshakeException
~~~

có thể do certificate chain, corporate TLS inspection/proxy hoặc JDK truststore. Kiểm URL, SSL interception policies và đúng JVM truststore. **Không** tắt certificate validation hoặc thêm `allowInsecureProtocol` một cách bừa bãi để “chữa sync”.

### 14.6. 401/403

Repository có thể yêu cầu credentials hoặc quyền chưa đủ. Phân biệt:

- **401 Unauthorized**: token/credentials chưa có hoặc không hợp lệ.
- **403 Forbidden**: identity bị từ chối quyền hoặc repository policy.
- **404 Not Found**: module/artifact/path không tồn tại tại endpoint tương ứng; cũng có thể server che permission bằng 404.
- **429 Too Many Requests**: rate limit, cần retry/backoff/mirror policy.
- **Timeout/DNS**: network/proxy/firewall/service health.

Đừng in passwords vào debug logs. Dùng Gradle credentials providers/environment/Gradle User Home theo team policy.

### 14.7. Sync thành công nhưng IDE vẫn đỏ imports

Có thể:

- IDE index chưa cập nhật.
- Module/source root mapping sai.
- Source set test vs main bị nhận nhầm.
- IDE native compiler classpath khác Gradle classpath.
- SDK/language-level mismatch.
- Generated source root chưa được đăng ký/updated.
- IDE đang dùng stale model hoặc unlinked Gradle project.
- Dependency version không chứa class mong đợi.

Dùng `gradle compileJava` để phân biệt Gradle compilation với IDE index/UI. Nếu CLI compile pass mà IDE đỏ, đọc IDE Gradle model/index logs; đừng bắt đầu bằng xóa toàn bộ `~/.gradle`.

### 14.8. Sync fail nhưng CLI build pass

So:

- IDE Gradle JVM vs terminal `JAVA_HOME`.
- Wrapper vs IDE-local Gradle distribution.
- Gradle User Home khác nhau.
- IDE Offline Work.
- IDE-specific model/initialization scripts.
- Plugin compatibility với Tooling API model builders.
- After Sync task hooks.
- Proxy environment variables/credentials.
- IDE version/Gradle integration bug.

Nếu đã đồng bộ chính xác environment mà CLI pass còn sync fail, vấn đề có thể nằm ở IDE Tooling API/model integration, không phải Java source.

### 14.9. "Could not resolve all files for configuration ..."

Đọc **tên configuration** trong error, chẳng hạn `:compileClasspath` hay `:testRuntimeClasspath`. Nếu `testRuntimeClasspath` thiếu JUnit launcher, compilation main sources có thể vẫn pass. Đừng kết luận toàn project không compile được chỉ từ một configuration của tests.

### 14.10. Gradle sync treo rất lâu

Có thể do:

- Repository timeout/slow metadata requests.
- Plugin/buildscript dependency resolution.
- Daemon JVM startup/GC/memory pressure.
- IDE Tooling API model import lớn.
- Build script network I/O/eager dependency resolution.
- Included builds/composite build.
- Artifact transforms or source generation tasks.
- IDE indexing sau khi Gradle model sync xong.

Xem CPU/network process, Build/Sync tool window, daemon logs, Gradle `--info`, và task paths để xác định **đang ở tầng nào**, không tắt daemon ngay từ đầu.

## 15. Quy trình chẩn đoán năm phút

Khi người khác nói “Gradle sync đang tải mãi”:

### Bước 1 — Ghi rõ thao tác

- Đang **Open/Reload Gradle Project**?
- Đang **Build Project**?
- Đang **Run a Gradle task**?
- Hay chỉ IDE đang **Indexing**?

Chụp **error message/task path** và IDE build window, không chỉ chụp progress spinner.

### Bước 2 — Kiểm toolchain và Wrapper

~~~bash
gradle --version
java -version
~~~

Nếu project có Wrapper thì ưu tiên:

~~~bash
./gradlew --version
~~~

So với Gradle JVM/Wrapper settings trong IDE. Nếu phiên bản không khớp, ghi nhận khác biệt trước khi debug dependency.

### Bước 3 — Kiểm Gradle configuration cơ bản

~~~bash
./gradlew help --stacktrace --console=plain
~~~

Đây là test khởi tạo/configuration (qua `help` reporting task), **chưa đảm bảo compile/test**. Nếu fail tại `settings.gradle.kts` hoặc plugin application, giải quyết trước.

### Bước 4 — Xem dependency graph của configuration có vấn đề

~~~bash
./gradlew dependencies \
    --configuration compileClasspath \
    --console=plain
~~~

Nếu lỗi thuộc test runtime, đổi `--configuration testRuntimeClasspath`. Không report mọi configurations một cách không cần thiết.

### Bước 5 — Xác định chọn version

~~~bash
./gradlew dependencyInsight \
    --dependency commons-lang3 \
    --configuration runtimeClasspath \
    --console=plain
~~~

Dùng đúng module và configuration thật; đó là diagnostic cho module dependencies, không phải plugin marker lookup.

### Bước 6 — Thử task tối thiểu

~~~bash
./gradlew compileJava --stacktrace --console=plain
~~~

Nếu compile pass nhưng IDE sync fail, tập trung vào IDE model/SDK/Tooling API thay vì Java source.

### Bước 7 — Tăng verbosity có kiểm soát

~~~bash
./gradlew help --info --stacktrace --console=plain
~~~

`--debug` có thể tiết lộ rất nhiều network/auth details trong logs; chỉ dùng nếu policy cho phép và biết cách scrub.

### Bước 8 — Thử online refresh khi nghi stale

~~~bash
./gradlew compileJava --refresh-dependencies
~~~

Chỉ làm khi nguyên nhân phù hợp (changing/dynamic/stale metadata). Nếu lỗi là 401 hoặc thiếu repository, refresh không tự chữa.

### Bước 9 — So IDE settings với CLI

Kiểm:

- Gradle JVM.
- Distribution/Wrapper.
- Offline Work.
- Gradle User Home.
- Auto Reload/Tasks Activation.
- Proxy/IDE HTTP settings.
- IDE Build/Run delegation.

### Bước 10 — Xem output thực tế

Kiểm `build/classes/java/main`, `build/test-results/test`, `build/libs` và Gradle task logs. Nếu chỉ sync mà không yêu cầu compile/test, những folders này có thể chưa được tạo — **đó không phải lỗi**.

## 16. Multi-project build: sync thường nhập toàn bộ model

Một settings file:

~~~kotlin
rootProject.name = "multi-lab"
include(":api", ":app", ":integration")
~~~

Gradle tool window của IDE thường nhập cả project graph, không phải chỉ module đang mở trong editor. Khi chạy:

~~~bash
./gradlew :app:compileJava
~~~

Gradle thực thi tasks cần thiết cho `:app` và dependencies. Khi chạy:

~~~bash
./gradlew :api:dependencies \
    --configuration runtimeClasspath
~~~

Gradle giải dependency graph riêng cho `:api`.

### 16.1. Sync import cả graph ≠ build tất cả modules

IDE cần biết modules để thiết lập navigation/source roots. Nó có thể resolve models cho nhiều modules, nhưng không mặc định compile và test tất cả projects.

### 16.2. Vì sao sync multi-project có thể chậm?

- Nhiều build scripts/plugins/included builds.
- Eager configuration gây network/I/O.
- IDE cần nhiều source sets/configuration variants.
- Composite build substitution.
- Generated sources và task-based model preparation.
- Download sources/Javadoc cho nhiều dependencies.
- Kotlin DSL script classpath/indexing.

Giải pháp có thể là lazy task configuration, configuration cache khi tương thích, repository caching và giảm model work — không chỉ tăng heap hoặc xóa cache.

### 16.3. Đừng sửa .idea để thay Gradle source of truth

IDE lưu model imported trong local workspace files, nhưng build scripts/settings mới là nguồn chính cho Gradle-linked project. Nếu bạn thêm dependency chỉ qua IDE Project Structure và sync lại, Gradle import có thể ghi đè IDE-only change. Hãy sửa `dependencies`/repositories trong Gradle source.

## 17. Build script plugin, Kotlin DSL và IDE indexing

### 17.1. Vì sao Kotlin DSL sync tải nhiều thứ?

Với `build.gradle.kts`, IDE cần hỗ trợ Kotlin DSL type-safe accessors và script classpath. Sync có thể:

- Resolve plugins/buildscript dependencies.
- Compile/evaluate Kotlin build scripts.
- Xây Gradle model.
- Cập nhật editor resolution/DSL completion.

Đây là **build logic/tooling work**, không nhất thiết compile application `src/main/java`.

### 17.2. IDE indexing là một hoạt động riêng

Sau khi Gradle model import báo thành công, IDE còn có thể index JAR/source files và xây symbol database. IDE progress “Indexing...” không đồng nghĩa Gradle đang chạy `compileJava`. Nếu Gradle Sync log báo done nhưng editor vẫn tải symbols, xem IDE indexing status và library attachments.

### 17.3. Plugin code có thể làm sync chậm

Một custom Gradle plugin có thể:

~~~kotlin
class ExamplePlugin : Plugin<Project> {
    override fun apply(project: Project) {
        // Chạy khi plugin được apply vào project
    }
}
~~~

Đây là **snippet minh họa**, cần imports/build logic thích hợp nếu muốn compile. `apply(project)` xảy ra trong configuration, tức sync có thể chạy code đó. Nếu plugin làm network requests/eager resolution trong `apply`, sync sẽ bị kéo chậm.

Nên giữ plugin configuration lazy, tránh `configuration.resolve()` tùy tiện khi apply plugin và defer expensive work tới task actions có declared inputs/outputs.

### 17.4. KSP/KAPT/Android/Code generation

Một số plugin/IDE integration cần generated sources và có thể yêu cầu tasks đặc biệt khi sync. Trường hợp này hãy đọc task names thật (ví dụ `generate...`, `prepare...`); không coi mọi background Gradle activity là lỗi, nhưng cần kiểm nó có cần thiết, cacheable và không tạo side effects ngoài ý muốn hay không.

## 18. Gradle Daemon, caches và IDE model cache

Các cache thường bị nhầm:

| Cache/process | Mục đích | Ví dụ |
| --- | --- | --- |
| Gradle **Daemon JVM** | Reuse JVM/JIT/loaded classes | `gradle --status` |
| Gradle **dependency cache** | Metadata/JARs của external modules | `~/.gradle/caches/modules-2` |
| Gradle **Build Cache** | Outputs của cacheable tasks | `org.gradle.caching=true` |
| **Configuration Cache** | Reuse configuration/task graph | `--configuration-cache` |
| **IDE indexes/model** | Code insight, navigation, imported project state | IDE-managed files/cache |
| Gradle **Wrapper cache** | Gradle distributions | `~/.gradle/wrapper/dists` |

### 18.1. Vì sao --stop không làm tải dependency lại?

`gradle --stop` chỉ dừng daemon processes của Gradle version tương ứng, không xóa artifact caches. Một sync sau đó có thể mở daemon mới nhưng sử dụng JARs đã cache.

### 18.2. Vì sao --refresh-dependencies không chạy tests?

`--refresh-dependencies` chỉ ảnh hưởng resolution state trong invocation. Nếu lệnh là:

~~~bash
gradle help --refresh-dependencies
~~~

Gradle chạy `help` task (và plugin/model resolution nếu cần), **không tự chạy `test`**.

### 18.3. Vì sao xóa .idea không chữa Gradle repository?

`.idea` là dữ liệu IDE; Gradle dependency repository/caches thuộc cấu hình Gradle. Nếu repository URL sai hoặc JAR không tồn tại, invalidating IDE caches không tự tạo artifact. Chỉ thao tác IDE caches khi đã chứng minh model/index bị stale và hiểu impact.

### 18.4. Vì sao xóa project build/ không download lại tất cả?

`build/` chứa outputs/reports; external dependency JAR cache thường ở Gradle User Home. `gradle clean` xóa build outputs, nhưng Gradle vẫn có thể sử dụng external libraries cached khi build tiếp.

## 19. Tái hiện lỗi Offline Work có kiểm soát

Lab dùng Maven Central. Để học mà không phá local environment:

1. Chạy `gradle compileJava` online để có thể populate cache.
2. Chạy `gradle compileJava --offline`.
3. Nếu pass, cần nhớ: điều đó chỉ chứng minh **required dependencies đã có trong cache mà invocation dùng**.
4. Không xóa `~/.gradle` để tạo lỗi giả: hành động này làm mất nhiều dữ liệu của user.
5. Muốn thử cold cache thật, dùng một **GRADLE_USER_HOME tạm riêng có chủ đích** và workspace test; sau thí nghiệm dọn đúng path tạm nếu được phép.

### 19.1. Một lệnh minh họa với Gradle User Home riêng

Linux/macOS:

~~~bash
GRADLE_USER_HOME="$PWD/.gradle-lab-home" \
    gradle --offline compileJava
~~~

Với một Gradle User Home mới, offline compile có thể fail vì thiếu artifacts/Gradle toolchains/plugins cache. Với Gradle được cài toàn hệ thống, command vẫn chạy được tới bước cần dependency, nếu distribution/JDK đã có. **Không kết luận outcome chắc chắn** nếu môi trường đã có artifacts hoặc home không thật sự trống.

PowerShell:

~~~powershell
$env:GRADLE_USER_HOME = (Join-Path (Get-Location) ".gradle-lab-home")
try {
    gradle --offline compileJava
}
finally {
    Remove-Item Env:GRADLE_USER_HOME -ErrorAction SilentlyContinue
}
~~~

Snippets nhằm giải thích **isolation of cache**, không yêu cầu xóa thư mục cache sau đó. Với Wrapper, một Gradle User Home mới còn cần tải Gradle distribution; `--offline` dành cho dependency resolution, không nên giả định mọi Wrapper distribution đã có ở home mới.

## 20. Khi nào sync thật sự cần tasks?

### 20.1. IDE model builder có thể yêu cầu preparatory tasks

Tooling API hỗ trợ mô hình **build action** và `forTasks(...)` cho những trường hợp IDE muốn chạy tasks trước khi lấy model. Theo tài liệu Gradle Tooling API hiện hành, nếu `forTasks(...)` không được gọi (hoặc truyền null), model action có thể bỏ qua task execution; nếu tasks được schedule thì chúng là một phần của invocation.

Điều này giải thích tại sao nhiều IDE/plugin syncs chỉ import model, nhưng một vài import có tasks như codegen/prepare test fixtures.

### 20.2. Không phải task nào cũng là compile/test

Một import có thể chạy diagnostic/source generation task mà không chạy `:test`, `:jar` hoặc `:run`. Khi điều tra, quan sát **task path và outcome** thay vì chỉ đếm số task.

### 20.3. Configuration side effects khác task action

Một plugin có thể tải tài nguyên ngay trong `apply(Project)` mà không có task entry. Đó là **configuration-time I/O**; dù không thấy dòng `> Task ...`, sync vẫn có thể dùng network và CPU đáng kể. Thiết kế plugin tốt hạn chế side effects và ưu tiên lazy resolution.

### 20.4. Đặt Tasks Activation/After Sync có chủ ý

Nếu team cấu hình IDE tự chạy `generateApi` sau sync, document rõ:

- Task nào chạy.
- Vì sao cần trước khi editor sử dụng generated files.
- Output directories.
- Có thể cache/up-to-date không.
- Có cần network/credentials không.
- Task failure có làm import fail không.
- Có gây side effects hoặc mở server/background process không.

Không để developers tưởng sync là read-only nếu IDE setup cố ý run tasks tác động filesystem.

## 21. Một test matrix để phân biệt nguyên nhân

| Thí nghiệm | Dấu hiệu expected | Điều không được suy ra |
| --- | --- | --- |
| IDE sync lab | Modules/classpaths/tasks xuất hiện | Test đã pass |
| `gradle help` | Help task chạy, config có thể được evaluate | Application compiled |
| `gradle dependencies --configuration compileClasspath` | Commons Lang graph được resolve | JAR bytes nhất định đã tải |
| `gradle compileJava` | App.class được tạo/cập nhật khi cần | Main method đã chạy |
| `gradle probeTaskExecution --quiet` | `TASK_ACTION_MARKER=YES` | App main/test đã chạy |
| `gradle run --quiet` | `SYNC_DEMO=GRADLE SYNC` | Tests đã pass |
| `gradle test` | JUnit report được tạo khi tests executed | IDE model đã refresh |
| `gradle jar` | Project JAR được tạo | External deps đã được đóng vào JAR |
| `gradle --offline compileJava` | Uses cached artifacts or fails | Môi trường mới sẽ offline pass |
| `gradle --refresh-dependencies compileJava` | Revalidation of dependency state | Tải lại mọi JAR bytes |

### 21.1. Negative control: chỉ sync chưa có App.class

Trên một **project vừa tạo chưa từng compile**, sau sync bạn có thể kiểm `build/classes/java/main/dev/example/sync/App.class` chưa tồn tại. Đó là bình thường. Nhưng **nếu file đã tồn tại từ build cũ**, không thể suy ra sync vừa biên dịch. Cần xem timestamp/task logs và chạy một thử nghiệm từ workspace sạch có kiểm soát nếu muốn xác minh.

### 21.2. Positive control: task marker

`TASK_ACTION_MARKER=YES` được in từ `probeTaskExecution.doLast`, nên nó chứng minh **chính task này** đã chạy action. Nó không nói gì về các tasks khác nếu IDE sync in hoặc không in marker.

### 21.3. Positive control: application marker

`SYNC_DEMO=GRADLE SYNC` được in từ `App.main`, nên marker chỉ xuất hiện khi JVM gọi main method theo ví dụ lab, không phải khi chỉ đọc Gradle model.

## 22. CI/CD liên quan thế nào đến IDE sync?

CI thường chạy Gradle tasks trực tiếp:

~~~bash
./gradlew clean test assemble
~~~

Nó không cần IDE import model để biên dịch/test. Vì thế:

- **CI xanh, IDE sync đỏ**: nghi IDE Tooling API/IDE Gradle JVM/model/index differences.
- **IDE sync xanh, CI đỏ**: nghi compilation/test/packaging, CI OS/JDK/credentials hoặc missing configuration in CI.
- **Cả hai đỏ cùng resolution error**: nghi common Gradle settings/dependencies/network.
- **Chỉ compileClasspath pass, testRuntimeClasspath fail**: nghi test dependencies/engine/variant.
- **IDE tự tải sources, CI không**: có thể chỉ là editor source attachment behavior.

### 22.1. Dùng Gradle Wrapper làm nguồn sự thật

Cả IDE và CI nên dùng cùng Wrapper khi có thể. Không thay production dependency cache từ CI bằng cách commit cả `~/.gradle` hoặc hard-code local Maven jars. Pin dependencies và repository policy trong repo.

### 22.2. Dependency locking và verification

Với CI/release reproducibility, cân nhắc Gradle dependency locking, verification metadata/checksums và repositories filtering. Đây là cách đảm bảo resolved versions/artifacts nhất quán, không phải ép mọi developer dùng `--refresh-dependencies` mỗi lần sync.

### 22.3. Đừng lưu secrets trong logs/sync diagnostics

`--info`/`--debug` có thể làm logs chứa repo URLs, environment metadata hoặc sensitive headers trong một số trường hợp. Không gửi full Gradle/IDE logs public khi chưa rà soát. Dùng credential providers/user-home gradle.properties/environment variables theo policy, không hard-code credentials vào `settings.gradle.kts`.

## 23. Groovy DSL tương đương của lab

Nếu project dùng `settings.gradle` và `build.gradle`, dùng **một cấu hình thay thế**, không kết hợp song song với Kotlin DSL trong cùng module.

### 23.1. settings.gradle

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(
        RepositoriesMode.FAIL_ON_PROJECT_REPOS
    )
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'sync-or-build-lab'
~~~

### 23.2. build.gradle

~~~groovy
plugins {
    id 'application'
}

group = 'dev.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'dev.example.sync.App'
}

tasks.named('test') {
    useJUnitPlatform()
}

if (providers.gradleProperty('traceConfiguration').orNull == 'true') {
    logger.lifecycle('CONFIGURATION_MARKER=YES')
}

tasks.register('probeTaskExecution') {
    group = 'verification'
    doLast {
        println 'TASK_ACTION_MARKER=YES'
    }
}
~~~

Giữ nguyên ba Java source files và Gradle commands. Groovy DSL khác cú pháp khai báo, nhưng sync, dependency resolution và task execution **cùng semantics**. Nếu Gradle project được mở bằng IDE, IDE chọn DSL từ filenames.

## 24. Các lỗi phổ biến và cách sửa

### Lỗi 1 — “Sync done nghĩa là JAR đã build”

Sai. Sync chủ yếu import model.

**Sửa:** chạy `jar`/`assemble` rõ ràng và kiểm `build/libs`.

### Lỗi 2 — “Sync có download nghĩa là compile đang chạy”

Sai. IDE có thể resolve classpaths mà không execute compiler task.

**Sửa:** tìm `:compileJava` task path và compiled output/classfile.

### Lỗi 3 — “Sync không bao giờ chạy task”

Quá tuyệt đối. IDE/Tooling API/plugin có thể schedule preparatory tasks.

**Sửa:** kiểm Build/Sync logs và Tasks Activation.

### Lỗi 4 — “Đã declare dependency nên JAR phải tồn tại”

Declaration có thể lazy; artifact chỉ tải khi resolution yêu cầu bytes.

**Sửa:** dùng `compileJava`/appropriate resolvable config và kiểm results.

### Lỗi 5 — Sửa project repositories cho plugin not found

Plugin DSL cần đúng plugin resolution scope.

**Sửa:** kiểm `pluginManagement.repositories` và plugin marker/ID/version.

### Lỗi 6 — Sửa pluginManagement cho library missing

Project `implementation` dùng project dependency repositories.

**Sửa:** `dependencyResolutionManagement.repositories` hoặc project `repositories`.

### Lỗi 7 — IDE Offline Work bật mà cache thiếu

Gradle không truy remote repository để lấy missing artifacts.

**Sửa:** chuyển online, sync lại khi được phép, rồi thử offline sau cache warm.

### Lỗi 8 — Nghĩ --refresh-dependencies luôn tải lại mọi JAR

Gradle có revalidation/checksum để tránh download unchanged artifacts.

**Sửa:** đọc logs và metadata state, không đo bằng số JAR download.

### Lỗi 9 — Xóa ~/.gradle để sửa mọi lỗi

Mất caches/distributions và không chữa repo/JDK config.

**Sửa:** thu root-cause và targeted remediation.

### Lỗi 10 — Chỉ dùng --rerun-tasks cho stale dependency

Rerun task actions không đồng nghĩa refresh module metadata.

**Sửa:** xác định cần dependency refresh hay rebuild outputs.

### Lỗi 11 — Dùng --no-build-cache để thử offline

Build Cache khác dependency cache.

**Sửa:** dùng `--offline` cho dependency resolution test.

### Lỗi 12 — Chỉ nhìn IDE Project SDK

Gradle JVM/toolchain có thể khác.

**Sửa:** so Gradle JVM, Wrapper và `java.toolchain` riêng.

### Lỗi 13 — IDE build pass, Gradle build fail

IDE native compiler có thể khác Gradle tasks.

**Sửa:** delegate Build/Run/Test cho Gradle hoặc gọi CLI tasks rõ ràng để so sánh.

### Lỗi 14 — Gradle CLI pass, IDE đỏ imports

Có thể IDE model/index stale.

**Sửa:** reload linked project, xem index/source sets, IDE logs trước khi xóa Gradle caches.

### Lỗi 15 — Không có TEST-*.xml sau sync

Sync không mặc định chạy tests.

**Sửa:** chạy `test` và kiểm Gradle test report.

### Lỗi 16 — No matching variant được coi là timeout

Variant attributes incompatible, không nhất thiết network issue.

**Sửa:** đọc requested usage/JVM attributes/publisher metadata.

### Lỗi 17 — sources.jar thiếu làm tưởng compile fail

Sources attachments phục vụ IDE navigation.

**Sửa:** phân biệt warnings/source-download với `compileJava` result.

### Lỗi 18 — 401/403 bị xử lý bằng Maven version upgrade

Thường là auth/permission issue.

**Sửa:** credentials/CI scope/Repo URL; không in secret.

### Lỗi 19 — Tắt TLS validation để sync qua proxy

Tạo rủi ro supply-chain.

**Sửa:** cấu hình proxy/truststore/certificates đúng chính sách.

### Lỗi 20 — Tăng Gradle Daemon Xmx để giải quyết slow repository

Bottleneck có thể network.

**Sửa:** đo timing/HTTP metadata requests và memory/GC riêng.

### Lỗi 21 — Repo chậm vì dynamic versions

Short TTL/dynamic `1.+` có thể gây nhiều remote checks.

**Sửa:** pin fixed versions/locks và TTL có lý do.

### Lỗi 22 — mavenLocal() che dependency từ CI

Local artifact có thể khác central registry.

**Sửa:** bỏ mavenLocal mặc định hoặc giới hạn theo workflow.

### Lỗi 23 — FAIL_ON_PROJECT_REPOS bị hiểu là network failure

Settings policy cấm project repositories.

**Sửa:** centralize đúng và kiểm dòng `repositoriesMode`.

### Lỗi 24 — Chạy dependencies report cho sai config

`testRuntimeClasspath` khác `compileClasspath`.

**Sửa:** đọc error configuration và chọn đúng report target.

### Lỗi 25 — Dùng --dry-run để chứng minh test pass

Dry-run không execute test task action.

**Sửa:** chạy `test` thật và xem report.

### Lỗi 26 — Không so Gradle User Home của IDE và terminal

Hai môi trường có caches/JDK/config khác.

**Sửa:** xem Gradle settings, IDE gradle user home, môi trường shell.

### Lỗi 27 — Gradle Wrapper download fail bị quy cho Maven Central

Hai loại download khác nhau.

**Sửa:** kiểm `gradle-wrapper.properties` distribution URL và proxy/TLS.

### Lỗi 28 — Sync chậm vì build script tự gọi HTTP trong configuration

Không phải repository dependency resolution.

**Sửa:** loại eager network I/O; defer work vào task được khai inputs/outputs.

### Lỗi 29 — Generated source chỉ có sau task nhưng IDE không nhận

Project model không biết output/generated source roots.

**Sửa:** dùng Gradle Provider/task output wiring và IDE plugin integration đúng, không copy generated files thủ công.

### Lỗi 30 — Tự thêm classpath JAR vào IDE Project Structure

Gradle reload có thể ghi đè IDE-only dependency.

**Sửa:** khai trong Gradle source of truth.

### Lỗi 31 — Sync toàn multi-project bị hiểu là build tất cả modules

Import toàn model không đồng nghĩa compile/test tất cả.

**Sửa:** quan sát task execution paths và output artifacts.

### Lỗi 32 — Thay đổi library version mà IDE vẫn hiển thị code cũ

Có thể Gradle cache, IDE index/model stale hoặc version selection via constraints.

**Sửa:** `dependencyInsight`, reload project, refresh dependency khi có cơ sở, kiểm actual resolved artifact.

## 25. Bài tập tự kiểm tra có đáp án

### Bài 1 — Sync thành công, chưa có App.class

**Hỏi:** Đó là lỗi?

**Đáp:** Không. Sync không mặc định compile source; chạy `compileJava` để tạo classfile.

### Bài 2 — Tải Commons Lang trong sync

**Hỏi:** Có nghĩa main đã chạy?

**Đáp:** Không. IDE có thể resolve compile/runtime classpath mà chưa chạy `run`.

### Bài 3 — Tooling API chỉ query model?

**Hỏi:** Có thể schedule tasks không?

**Đáp:** Có. Tooling API hỗ trợ cả model query và task execution, và build action có thể yêu cầu preparatory tasks.

### Bài 4 — Plugin not found

**Hỏi:** Kiểm repositories nào?

**Đáp:** `pluginManagement.repositories`.

### Bài 5 — implementation dependency missing

**Hỏi:** Kiểm repositories nào?

**Đáp:** Project dependency repositories từ `dependencyResolutionManagement` hoặc project `repositories` tùy policy.

### Bài 6 — Offline compile lần đầu

**Hỏi:** Nếu Maven artifacts chưa cache?

**Đáp:** Có thể fail vì Gradle không truy mạng để tải missing dependency.

### Bài 7 — Refresh Dependencies

**Hỏi:** Luôn download lại JAR bytes?

**Đáp:** Không. Gradle revalidates và có thể dùng checksums/HTTP cache semantics để tránh tải bytes không đổi.

### Bài 8 — Run tasks không cùng nghĩa sync

**Hỏi:** Lệnh nào chạy app main trong lab?

**Đáp:**

~~~bash
gradle run --quiet
~~~

Stdout:

~~~text
SYNC_DEMO=GRADLE SYNC
~~~

### Bài 9 — Task action marker

**Hỏi:** Cần lệnh nào để thấy marker?

**Đáp:**

~~~bash
gradle probeTaskExecution --quiet
~~~

Stdout:

~~~text
TASK_ACTION_MARKER=YES
~~~

### Bài 10 — Configuration marker

**Hỏi:** Dùng property nào?

**Đáp:** `-PtraceConfiguration=true`, ví dụ `gradle -PtraceConfiguration=true help --no-configuration-cache`.

### Bài 11 — Không dùng Gradle

**Hỏi:** StandaloneProbe in gì?

**Đáp:**

~~~text
STANDALONE_JAVA_MAIN=YES
~~~

khi chạy bằng `javac --release 17` và `java -cp manual-out dev.example.sync.StandaloneProbe`.

### Bài 12 — dependencies report

**Hỏi:** Có phải một Gradle task thực thi?

**Đáp:** Có, `dependencies` là reporting task. Nó không compile application theo mặc định.

### Bài 13 — IDE Build Project

**Hỏi:** Luôn gọi `:build` của Gradle?

**Đáp:** Không. Phụ thuộc IDE build delegation settings; IDE native compiler có thể được dùng.

### Bài 14 — Lỗi No matching variant

**Hỏi:** Có tự hết bằng --refresh-dependencies?

**Đáp:** Không nếu producer/consumer variants thật sự không tương thích; phải sửa attributes/versions/variants.

### Bài 15 — Dynamic version

**Hỏi:** `1.+` có dễ tạo metadata refresh hơn fixed version?

**Đáp:** Có, theo TTL và repository state; nên pin/lock versions cho reproducibility.

### Bài 16 — Configuration Cache

**Hỏi:** Không thấy configuration marker có chứng minh không sync?

**Đáp:** Không. Configuration Cache có thể reuse model, hoặc marker bị disable/filtered; cần quan sát đúng logs.

### Bài 17 — Sync riêng module

**Hỏi:** IDE thường nhập một module hay toàn linked Gradle project?

**Đáp:** IntelliJ IDEA thường reload toàn linked project graph, gồm modules/dependencies, không mặc định compile mọi module.

### Bài 18 — Java toolchain

**Hỏi:** `java.toolchain=17` có ép IDE Gradle Daemon dùng JDK17?

**Đáp:** Không. Gradle JVM và project toolchain là settings khác nhau.

### Bài 19 — testRuntimeClasspath

**Hỏi:** Vì sao compile main pass nhưng test resolve fail?

**Đáp:** Test runtime có dependencies/variants khác, ví dụ JUnit engine/launcher còn thiếu.

### Bài 20 — --stop

**Hỏi:** Dừng Daemon có xóa Maven dependency cache?

**Đáp:** Không.

### Bài 21 — --no-build-cache

**Hỏi:** Có vô hiệu Gradle external module cache?

**Đáp:** Không; nó tắt task output Build Cache.

### Bài 22 — sources.jar

**Hỏi:** Không tải được source attachment có nhất thiết làm Java compile fail?

**Đáp:** Không nếu binary artifact đã có và IDE chỉ thiếu sources để navigation.

### Bài 23 — HTTP 401

**Hỏi:** Nên thử sửa Java source trước?

**Đáp:** Không. Xác minh repository credentials/authorization và Gradle proxy settings.

### Bài 24 — Jar từ lab

**Hỏi:** Có thể chạy project JAR với `java -jar` mặc định không?

**Đáp:** Không được giả định; thường thiếu Main-Class/embedded external dependencies. `gradle run` cấu hình runtime classpath phù hợp.

### Bài 25 — IDE index còn chạy sau sync

**Hỏi:** Có nghĩa Gradle task tiếp tục?

**Đáp:** Không nhất thiết. IDE index là bước riêng và có thể tiếp tục sau khi Tooling API model import kết thúc.

## 26. Checklist dành cho người review và người trực support

| Câu hỏi | Điều kiện đạt |
| --- | --- |
| Loại thao tác | Phân biệt Sync/Reload, Build, Run, Test, Indexing |
| Gradle distribution | IDE/CLI/CI dùng Wrapper version nhất quán khi phù hợp |
| Gradle JVM | IDE JVM chạy Gradle được hỗ trợ, không nhầm Java toolchain |
| Repositories | Plugin và project dependency scopes khai đúng |
| Dependency coordinates | GAV/version có thật, không dynamic tùy tiện |
| Resolution | Xem đúng compile/runtime/test configuration |
| Plugin downloads | Đúng plugin marker/repository/version |
| Library downloads | Metadata/JAR và Maven Central/corporate repo hoạt động |
| Offline | Offline Work/`--offline` chỉ khi cache đã đủ |
| Refresh | `--refresh-dependencies` dùng đúng lý do; không giả định re-download all |
| Task execution | Dựa trên task paths/outcomes, không dựa progress spinner |
| IDE delegation | Biết Build/Run/Test do Gradle hay IDE compiler |
| Model import | Tooling API có thể query models/chạy preparatory tasks |
| Test correctness | Có `test` execution/report; sync pass không thay test pass |
| IDE indexes | Source roots/libraries/index nhận đúng Gradle model |
| Multi-project | Project graph, included builds và configurations được phân biệt |
| Performance | Tránh eager plugin resolution/network I/O trong configuration |
| Cache | Phân biệt dependency/Build/Configuration/IDE/Wrapper caches |
| Security | Không log/upload secrets; kiểm repository TLS và trust |
| Troubleshooting | Có error message, config name, Gradle/JDK versions, minimal repro |
| CI parity | CLI tasks có thể build độc lập với IDE model import |

**Kết luận:** **Gradle sync** chủ yếu là thao tác **IDE nhập/đồng bộ mô hình dự án qua Tooling API**; **dependency resolution** là việc Gradle chọn phiên bản/variant và lấy metadata/artifacts khi cần; còn **task execution** là việc Gradle chạy actions của tasks được yêu cầu. Ba hoạt động có thể xảy ra trong cùng invocation, nhưng không đồng nghĩa nhau. Sync có thể tải libraries mà không compile; một số IDE/plugin import còn có preparatory tasks. Để chẩn đoán chính xác, hãy xác định **thao tác nào được yêu cầu, configuration nào được resolve, task path nào thực thi, Gradle JVM/repository nào được dùng và output artifact nào thật sự được tạo**, rồi mới chỉnh đúng tầng.

## 27. Tài liệu tham khảo chính thức

- [Gradle — Tooling API](https://docs.gradle.org/current/userguide/tooling_api.html) — model query, task execution, build actions/forTasks và IDE integration.
- [Gradle — Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html) — initialization, configuration và task execution.
- [Gradle — Dependency Management Basics](https://docs.gradle.org/current/userguide/dependency_management_basics.html) — declarations/configurations/resolution.
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html) — Gradle User Home cache, offline mode, refresh-dependencies, changing/dynamic TTL và repository stickiness.
- [Gradle — Declaring Repositories](https://docs.gradle.org/current/userguide/declaring_repositories_adv.html) — plugin vs project repositories.
- [Gradle — Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html) — dependencyResolutionManagement/repositoriesMode/credential safety.
- [Gradle — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html) — dependencies và dependencyInsight.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html) — --offline, --refresh-dependencies, --dry-run, --rerun-tasks và --info.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html) — project compilation toolchain vs Gradle runtime JVM.
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html) — JDK/Gradle releases compatibility.
- [Gradle — Best Practices for Performance](https://docs.gradle.org/current/userguide/performance.html) — configuration/cache/task graph performance.
- [IntelliJ IDEA — Gradle projects](https://www.jetbrains.com/help/idea/work-with-gradle-projects.html) — link/reload Gradle project, synchronize modules/dependencies.
- [IntelliJ IDEA — Build tool window](https://www.jetbrains.com/help/idea/build-sync-tool-window.html) — Sync tab vs Build Output.
- [IntelliJ IDEA — Gradle tasks](https://www.jetbrains.com/help/idea/work-with-gradle-tasks.html) — Gradle tool window, Tasks Activation và Before Build/After Sync hooks.
- [IntelliJ IDEA — Gradle build and run](https://www.jetbrains.com/help/idea/gradle.html) — Gradle JVM, build/run delegation, IDE Gradle settings.
- [Maven Central — Apache Commons Lang 3.17.0](https://central.sonatype.com/artifact/org.apache.commons/commons-lang3/3.17.0) — library dependency used in Java17 lab.
