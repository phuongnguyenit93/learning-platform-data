# Kiểm kê phiên bản Gradle, JDK, plugin và API build đang dùng

## 1. Tại sao phải kiểm kê trước khi nâng cấp?

Nâng Gradle không chỉ là đổi số phiên bản trong `gradle-wrapper.properties`. Một build Java có thể đồng thời sử dụng nhiều phiên bản Java, nhiều plugin ở những nguồn khai báo khác nhau, build logic trong `buildSrc`/included builds và các Gradle APIs đã deprecated hoặc bị gỡ bỏ ở phiên bản đích. Nếu không xác định được **đang dùng gì và dùng ở đâu**, việc nâng cấp có thể tạo lỗi khó truy vết: Gradle Daemon không khởi động, plugin không tương thích, task compile chọn sai JDK, tests chạy trên JVM khác hoặc một API cũ chỉ hỏng khi CI chạy task ít dùng.

Bài thuộc **Build Tool Gradle → Nâng cấp và di chuyển**, tập trung vào **kiểm kê trạng thái hiện tại**, chưa vội sửa build. Mục đích tạo baseline có thể lặp lại cho quyết định migration.

Bạn sẽ làm được:

1. Xác định **Gradle distribution thực sự** qua Wrapper, đối chiếu `./gradlew --version` với bản Gradle global.
2. Phân biệt **Gradle Client JVM**, **Gradle Daemon JVM**, **Java toolchain compiler/launcher**, Java bytecode target (`--release`) và JVM IDE/CI.
3. Tìm nguồn khai báo **plugin IDs, requested versions, implementation versions** trong `plugins {}`, `pluginManagement {}`, version catalogs, `buildscript {}`, `buildSrc`, convention plugins và included builds.
4. Phân biệt Gradle **core plugins** với external plugins; phân biệt plugin versions với dependency versions.
5. Kiểm kê **build APIs** trong Groovy/Kotlin DSL, Java/Kotlin binary plugins, task types, properties, dependency configuration, scripts và init scripts.
6. Dùng `--warning-mode=all`, `help`, `tasks`, `projects`, `dependencies`, `dependencyInsight`, `buildEnvironment` và `javaToolchains` đúng phạm vi.
7. Tạo một dự án Java 17+ chạy được, dùng Gradle Groovy DSL và JUnit, rồi lập bảng kiểm kê có **bằng chứng và mức độ tin cậy**.
8. Phân loại blocker/rủi ro, xây dựng compatibility matrix và kế hoạch nâng theo từng lớp mà không thay mọi thứ một lượt.

**Nguyên tắc:** kiểm kê nên bắt đầu từ **các file trong repository**, sau đó xác nhận bằng **Wrapper và runtime thực tế**. Không xem kết quả một lệnh như “toàn bộ sự thật”. Nếu chỉ mới đọc file, gọi là `declared/requested`; nếu đã quan sát runtime/resolution, gọi là `observed/resolved`.

## 2. Một build Gradle có nhiều loại “phiên bản”

| Thành phần | Nghĩa | Nguồn thường gặp | Cách kiểm kê |
| --- | --- | --- | --- |
| **Gradle Wrapper distribution** | Gradle release điều hành build. | `gradle/wrapper/gradle-wrapper.properties`: `distributionUrl`, `distributionSha256Sum`. | Đọc file + `./gradlew --version`. |
| **Wrapper launcher** | Scripts và JAR tải/chạy distribution. | `gradlew`, `gradlew.bat`, `gradle-wrapper.jar`. | Review Git diff; xác thực JAR/checksum chính thức. |
| **Gradle Client JVM** | JVM khởi chạy lệnh/Wrapper và kết nối Daemon. | `JAVA_HOME`, PATH, IDE/Tooling API. | `java -version` trong shell là gợi ý, không đủ với IDE. |
| **Gradle Daemon JVM** | JVM thực thi build logic/Gradle. | Daemon JVM criteria, `org.gradle.java.home`, Tooling API, môi trường. | `./gradlew --version` + config Daemon và logs khi cần. |
| **Java compiler toolchain** | JDK chứa javac cho `compileJava`. | `java.toolchain`, per-task `javaCompiler`. | `javaToolchains`, compiler selection và build scripts. |
| **Test JVM launcher** | JVM chạy unit/integration tests. | Java toolchain, `Test.javaLauncher`, custom test tasks. | Inspect Test task config/CI, không suy từ Gradle JVM. |
| **Target bytecode/API** | Java version được compile target. | `options.release`, `sourceCompatibility`, `targetCompatibility`. | Script + compile metadata/classfile khi cần. |
| **Core plugins** | Plugin đi kèm bản Gradle distribution. | `id 'java'`, `id 'application'`. | Plugin ID + Gradle release; không có external version riêng. |
| **External plugins** | Gradle plugin từ Portal/private repo/included build. | `plugins {}`, aliases, `pluginManagement`, `buildscript`. | Ghi ID, requested version, resolution source và implementation. |
| **Libraries / BOMs** | App/test dependencies; không đồng nghĩa Gradle plugins. | `dependencies {}`, catalogs, constraints. | `dependencies`, `dependencyInsight`. |
| **Build API / DSL** | Gradle APIs được build scripts/plugins gọi. | Script code, plugin source, buildSrc/convention build. | Static search + Gradle deprecations + targeted test. |

**Không có một biến `JAVA_VERSION` hay `gradleVersion` duy nhất mô tả được toàn bộ ma trận này.** Đặc biệt một build có thể chạy Gradle Daemon trên JDK 21, compile Java 17 và test trên JDK 17 hoặc 21 tùy thiết lập.

## 3. Thứ tự kiểm kê trước khi chạy build logic

Một repository chưa được review có thể chứa Wrapper JAR hoặc build script độc hại. **Đừng bắt đầu bằng cách chạy `./gradlew` từ nguồn không tin cậy trên máy có secrets**.

Trình tự:

1. **Kiểm tra Git/source files trước:** `gradlew`, `gradle-wrapper.jar`, `gradle-wrapper.properties`, settings/build scripts, init scripts, included builds và plugins.
2. **Xác thực Wrapper:** xác nhận `distributionUrl` pin đúng Gradle ZIP, `distributionSha256Sum` từ nguồn chính thức, Wrapper JAR checksum/signature nếu repository mới hoặc JAR đổi.
3. **Chỉ khi trust boundary phù hợp**, chạy các lệnh quan sát `--version`, `help`, `javaToolchains` và task reports.
4. **Đọc warnings và actual resolved state**, so với declarations.
5. **Ghi inventory baseline** gắn với Git commit, môi trường, câu lệnh, Gradle/JDK versions và thời gian kiểm kê; không âm thầm update files.
6. **Sau khi baseline đủ**, mới chọn target Gradle/JDK/plugin versions theo compatibility matrix và migration guides.

**Lưu ý:** Gradle `help`, `projects`, `tasks` không phải read-only theo nghĩa security sandbox: chúng vẫn có thể execute settings/build scripts và apply plugins trong configuration phase. Dùng trên source đã tin cậy hoặc isolated runner.

## 4. Kiểm kê Gradle Wrapper chính xác

### 4.1. Các file quan trọng

```text
repo/
├── gradlew
├── gradlew.bat
├── gradle/
│   ├── wrapper/
│   │   ├── gradle-wrapper.jar
│   │   └── gradle-wrapper.properties
│   └── gradle-daemon-jvm.properties   (nếu có)
├── settings.gradle hoặc settings.gradle.kts
├── build.gradle hoặc build.gradle.kts
└── gradle.properties                   (nếu có)
```

File `gradle/wrapper/gradle-wrapper.properties` ví dụ:

```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```

Ở đây **9.9.0** là Gradle **declared distribution version**, không phải Java version. Dạng `-bin.zip` khác `-all.zip`. Với Gradle 9.x, giá trị version trong `distributionUrl` của released distribution có định dạng đầy đủ `X.Y.Z`.

Trên các project đã tăng cường supply-chain controls, cần có `distributionSha256Sum` với SHA-256 chính thức cho **đúng ZIP**. Đừng chép một hash ví dụ tùy tiện. Kiểm tra riêng `gradle-wrapper.jar` vì Wrapper ZIP checksum **không tự kiểm tra JAR launcher**. Xem https://gradle.org/release-checksums/ .

### 4.2. Lệnh xem version thực tế

Linux/macOS:

```bash
./gradlew --version
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
```

Để xem bản Gradle được cài hệ thống (nếu có):

```bash
gradle --version
```

Hai lệnh **có thể khác version**. Trong repository, ưu tiên Wrapper đã được xác minh; không suy ra CI dùng bản global chỉ vì shell của developer có Gradle khác.

Báo cáo cần ghi:

| Field | Ý nghĩa |
| --- | --- |
| `Gradle distribution declared` | Release trong Wrapper properties. |
| `Gradle observed` | Release từ Wrapper `--version`. |
| `Wrapper type` | `bin` hay `all`, host/mirror/HTTPS. |
| `Wrapper checksum status` | Có pinned SHA? JAR được xác minh chưa? |
| `Global Gradle` | Bản global nếu có; chỉ để phân biệt, không phải baseline build. |
| `CI/IDE wrapper usage` | Gradle distribution CI/IDE thật sự dùng là Wrapper hay override. |

### 4.3. Khi declared và observed không khớp

Kiểm tra người chạy có thật sự gọi `./gradlew` từ đúng root, có dùng wrapper ở included build/subproject khác, Gradle distribution URL có bị tùy chỉnh/mirror, IDE có override Gradle distribution, CI action có pin version riêng không. Trong Gradle 9.x, `gradle --version` chỉ là bản **global**, không làm Wrapper thay đổi.

**Không sửa `distributionUrl` khi đang kiểm kê**. Ghi lại hiện trạng và tạo PR nâng riêng sau khi đánh giá compatibility.

## 5. Kiểm kê JDK: đừng gộp Client, Daemon, Compiler, Test

### 5.1. Bốn câu hỏi phải trả lời riêng

1. **JVM shell/client:** `java -version` in Java gì? `JAVA_HOME` trỏ đến đâu?
2. **JVM chạy Gradle Daemon:** phiên bản Java thực thi settings/build scripts/plugins là gì? Nó có bị override bởi `org.gradle.java.home`, IDE/Tooling API hoặc Daemon JVM criteria không?
3. **JDK compiler toolchain:** `compileJava` và `compileTestJava` dùng compiler nào?
4. **JVM chạy tests/app:** `Test.javaLauncher`, `JavaExec.javaLauncher` hoặc application/runtime environment có dùng cùng JDK không?

**Gradle 9.x yêu cầu JVM 17 trở lên để chạy Gradle Daemon**. Client launcher/Wrapper có thể có yêu cầu khác theo version; dùng compatibility matrix chính thức: https://docs.gradle.org/current/userguide/compatibility.html .

Một dự án cố ý compile/test Java 11 vẫn có thể chạy build logic trên Gradle 9.9/JDK 21 nếu toolchain và Gradle/JDK compatibility được hỗ trợ. Java 11 **target** không đồng nghĩa Gradle Daemon có thể chạy trên JDK 11.

### 5.2. Shell và Gradle Daemon

Linux/macOS:

```bash
java -version
javac -version
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
./gradlew --version
```

Windows PowerShell:

```powershell
java -version
javac -version
Write-Output ("JAVA_HOME=" + $env:JAVA_HOME)
.\gradlew.bat --version
```

`java -version`/`javac -version` kiểm tra tools từ **shell PATH/JAVA_HOME**, không bảo đảm compileJava hoặc Gradle Daemon dùng chính binaries đó. `--version` cho biết Gradle release và thông tin JVM theo Gradle version (một số bản tách launcher/daemon JVM).

**Cảnh giác:** `JAVA_HOME` có thể khác compiler toolchain. Một IDE có **Gradle JVM** riêng; CI có `org.gradle.java.home` hoặc wrapper/toolchain config khác, khiến local PASS và CI FAIL dù project source giống nhau.

### 5.3. Daemon JVM criteria được ưu tiên

Kiểm tra file `gradle/gradle-daemon-jvm.properties` nếu tồn tại. Trong Gradle hỗ trợ Daemon JVM criteria, tệp này do task `updateDaemonJvm` sinh và có thể chứa `toolchainVersion`/vendor/download URLs.

**Thứ tự quan trọng:** Daemon JVM criteria (nếu được cấu hình) **ưu tiên hơn `JAVA_HOME` và `org.gradle.java.home`** theo Gradle docs. Nếu không có criteria, Gradle có thể dùng `org.gradle.java.home` hoặc environment/Tooling API. Đừng nhìn JAVA_HOME rồi kết luận Daemon JVM chắc chắn giống shell.

Bản ghi inventory:

```text
Gradle Daemon JVM criteria file: present/absent
Requested Daemon Java version/vendor: <observed declaration>
org.gradle.java.home: configured/not configured (redact personal paths)
IDE Gradle JVM: <observed IDE configuration>
Actual Gradle JVM: <Gradle --version / diagnostics>
```

Dòng có `<...>` là **mẫu cần điền bằng chứng thật**, không phải kết quả công cụ đã chạy.

### 5.4. Toolchain/compiler/bytecode target

Ví dụ trong `build.gradle`:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

- `java.toolchain` yêu cầu **compiler/launcher JDK 17** theo toolchain selection.
- `options.release = 17` yêu cầu compiler phát bytecode/API tương thích Java 17; nó **không tự chọn hoặc tải compiler JDK**.
- `sourceCompatibility`/`targetCompatibility` khác `--release`: chúng không luôn ngăn compile gọi API mới hơn target khi compiler mới.
- Per-task override `javaCompiler` hoặc `javaLauncher` có thể khác project default, vì thế phải kiểm từng important task, không chỉ java extension.

Để xem toolchains được Gradle phát hiện:

```bash
./gradlew -q javaToolchains
```

`javaToolchains` liệt kê **các JDK/JRE được phát hiện** và metadata, không tự chứng minh `compileJava` thực tế đã chọn JDK nào. Trên build Java plugin mặc định, task có sẵn. Kiểm tiếp `JavaCompile.javaCompiler`, `Test.javaLauncher`, `JavaExec.javaLauncher` tại DSL hoặc diagnostics phù hợp.

Toolchain auto-provisioning (nếu được cấu hình với resolver) có thể tải JDK. Ghi **requested version/vendor** và **selected installation** riêng; không nhầm một JDK được liệt kê là JDK chắc chắn được dùng.

### 5.5. Từ class file biết được gì?

`javap -verbose` có thể hiển thị class file **major version**; Java 17 dùng major **61**. Điều đó cho biết target bytecode, **không chỉ đích danh javac/JDK vendor đã compile**. Với project multi-release hoặc tasks khác nhau, cần kiểm tra đúng artifact/task.

Không đưa một major version quan sát ở module A để kết luận module B hay test JVM cũng giống nhau.

## 6. Kiểm kê plugin IDs/versions từ mọi nguồn khai báo

### 6.1. Phân biệt hai loại plugin

**Core Gradle plugin:**

```groovy
plugins {
    id 'java'
    id 'application'
}
```

`java` và `application` là Gradle core plugins, không khai báo external plugin version riêng như plugin Portal. Plugin behavior đến từ Gradle release. Một core plugin có thể được áp gián tiếp: `application` cũng áp Java plugin.

**External plugin:**

```groovy
plugins {
    id 'org.example.code-quality' version '1.2.3'
}
```

Block này **minh họa cú pháp**, dùng plugin ID và version giả; **không phải một build script runnable khi plugin không tồn tại**. Phải ghi rõ **plugin ID**, **requested version**, nơi resolve (Plugin Portal/private repo/included build), Gradle compatibility và actual implementation artifact/version.

### 6.2. Nguồn 1: plugins block ở từng project/settings

Đọc `settings.gradle(.kts)`, `build.gradle(.kts)` của root và **mọi subproject**. Một plugin có thể chỉ áp ở `:android`, `:api` hoặc `:build-logic`. Tìm:

- `plugins { id '...' version '...' }`.
- `plugins { alias(libs.plugins.someAlias) }`.
- `apply false` trên root: plugin version được khai báo/resolve policy nhưng **không có nghĩa plugin đã apply vào root**.
- `apply plugin: '...'`: plugin legacy application, có thể lấy implementation từ một buildscript classpath/configuration khác.
- Script plugins `apply from: '...'`: có thể chứa thêm `apply plugin`, task APIs hoặc plugin-dependent logic.
- Settings plugins và init scripts áp dụng trước project configuration.

**Không có một lệnh Gradle core duy nhất có thể in chính xác mọi requested/selected ID+version của mọi plugin từ mọi nguồn.** Cần kiểm static declarations, resolution policies và runtime evidence.

### 6.3. Nguồn 2: settings.pluginManagement

Trong `settings.gradle`, block `pluginManagement` có thể đặt:

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
    plugins {
        id 'org.example.code-quality' version '1.2.3'
    }
}

rootProject.name = 'sample'
```

Đây là **ví dụ minh họa** plugin external giả. Khi project áp plugin ID tương ứng mà không chỉ định version, `pluginManagement.plugins` cung cấp version default.

Ngoài ra kiểm:

- `pluginManagement.resolutionStrategy.eachPlugin`: có thể thay plugin request, map ID → module coordinates hoặc version.
- `pluginManagement.includeBuild('build-logic')`: plugin có thể do included plugin build cung cấp, không tải từ Portal.
- `pluginManagement.repositories`: private plugin repository có thể thay nơi cung cấp artifact.
- Settings `plugins {}` có thể áp Settings plugin, khác Project plugin.

Kết quả inventory nên lưu **declared request** và **effective resolution policy**, không chỉ một dòng `id '...'`.

### 6.4. Nguồn 3: version catalog

Ví dụ `gradle/libs.versions.toml`:

```toml
[versions]
quality = "1.2.3"

[plugins]
quality = { id = "org.example.code-quality", version.ref = "quality" }

[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3", version = "3.17.0" }
```

Đây là **mẫu minh họa**, không phải dependency/plugin benchmark runnable vì plugin external giả. Trong Gradle Groovy DSL, code sử dụng:

```groovy
plugins {
    alias(libs.plugins.quality)
}
```

Version nằm tại `[versions].quality` chứ không hiện ở `build.gradle`. Nhiều version catalogs có thể được import trong `dependencyResolutionManagement { versionCatalogs { ... } }`; không mặc định chỉ có file `libs.versions.toml`.

**Phân biệt:** alias plugin `libs.plugins.quality` và alias library `libs.commons.lang3` đại diện những loại tọa độ khác nhau. Catalog **tập trung requested versions**, không tự cho biết actual plugin implementation module/compatibility hoặc resolved library versions khi có constraints.

### 6.5. Nguồn 4: legacy buildscript classpath và apply plugin

Một số build cũ:

```groovy
buildscript {
    repositories {
        gradlePluginPortal()
    }
    dependencies {
        classpath 'org.example:quality-gradle-plugin:1.2.3'
    }
}

apply plugin: 'org.example.code-quality'
```

Đây là **mã minh họa** với tọa độ giả, không phải code có thể build nếu repository thiếu plugin. Version được xác định qua `classpath` dependency, không nhất thiết xuất hiện ở `apply plugin`.

Dùng:

```bash
./gradlew buildEnvironment
```

`buildEnvironment` hiển thị **buildscript dependencies/classpath** của project theo command target, không bảo đảm liệt kê tất cả plugins từ `plugins {}`, included builds hay Settings plugins.

Ví dụ cho subproject:

```bash
./gradlew :app:buildEnvironment
```

Nếu root `buildEnvironment` báo “No dependencies” vẫn có thể có core plugins hoặc plugins DSL; đó **không phải bằng chứng build không có plugins**.

### 6.6. Nguồn 5: convention plugins, buildSrc, included builds

Kiểm:

```text
repo/
├── buildSrc/
│   ├── build.gradle(.kts)
│   └── src/main/...
├── build-logic/
│   ├── settings.gradle(.kts)
│   ├── build.gradle(.kts)
│   └── src/main/...
├── settings.gradle(.kts)
└── subprojects/...
```

- `buildSrc` là build logic project đặc biệt có dependencies/plugins/Gradle APIs của riêng nó.
- `includeBuild('build-logic')` cho composite builds; `pluginManagement.includeBuild` giúp resolve convention/binary plugins từ một build độc lập.
- **Precompiled script plugins** (`*.gradle` hoặc `*.gradle.kts` trong source folders của build logic) có thể apply plugins bên trong.
- **Binary plugins** `Plugin<Project>`/`Plugin<Settings>` dùng Gradle API, Kotlin/Groovy/Java/JVM target và external dependencies riêng; cần inventory như một software component.
- Project version của plugin build (`version='...'`) không tự là Gradle release; cần ghi độc lập.

Nếu consumer dùng `includeBuild`, chạy một lần `./gradlew projects` ở root không đủ để kết luận bạn đã audit hết các included builds. Đọc files trong mỗi build boundary và đánh dấu ownership.

### 6.7. Nguồn 6: CI, init scripts và IDE

Plugin/version có thể được thêm bằng:

- CI jobs gọi `--init-script` hoặc môi trường `GRADLE_USER_HOME/init.d`.
- Gradle Enterprise/Develocity integration, build scans hoặc security plugins injected từ runner.
- Android Gradle Plugin qua root convention/version catalog, pluginManagement.
- IDE Gradle sync với init scripts/Tooling API configuration.
- Project `gradle.properties` hoặc environment variables quyết định plugin versions/dynamic settings.

**Không in nguyên credentials trong gradle.properties/CI variables vào inventory.** Chỉ ghi tên config key hoặc trạng thái tồn tại, redact user home/repository tokens/private URLs theo policy.

## 7. Phân biệt plugin ID, requested version, applied plugin và implementation

Một inventory chuẩn nên ghi ít nhất:

| Thuộc tính | Ví dụ ý nghĩa |
| --- | --- |
| Plugin ID | `application` hoặc `org.example.code-quality`. |
| Loại | Core, external Portal, private repo, buildSrc/precompiled convention, included build. |
| Scope | Settings/Project hoặc plugin được load từ init script. |
| Declared/requested version | `1.2.3`, alias/catalog ref, default pluginManagement, hoặc core/no version. |
| Applied where? | Root, `:app`, `:lib`, included build; `apply false` ≠ applied. |
| Resolved implementation | JAR/module/version or included plugin source; có bằng chứng gì? |
| Compatibility | Vendor docs/matrix với target Gradle/JDK/Kotlin/Groovy/AGP nếu relevant. |
| Evidence | File:line, command/log/repository metadata, commit. |
| Confidence | Declared only, resolved, runtime-confirmed, chưa xác minh. |

**Không đồng nhất `Plugin ID` với Maven group:name hoặc Gradle plugin implementation class.** Plugin Portal có thể dùng **plugin marker artifact** để dẫn từ ID/version sang implementation module có coordinates khác. Vì thế ngoài plugin request cần xem resolution policy/implementation artifact khi migration nhạy cảm.

**Core plugins:** thường ghi “Gradle core; version follows Gradle distribution”, không bịa một plugin artifact version riêng.

## 8. Kiểm kê Build API được dùng, không chỉ thư viện

### 8.1. API có thể nằm ở đâu?

- Project DSL: `build.gradle`, `build.gradle.kts`.
- Settings DSL: `settings.gradle`, `settings.gradle.kts`.
- Script plugins được `apply from`.
- `buildSrc`, `build-logic`, precompiled script plugins.
- Binary plugin code: `org.gradle.api.Plugin`, `Project`, `Task`, `DefaultTask`, `Provider`, `Property`, `TaskProvider`.
- Code tạo/consume configurations, artifact transforms, custom repository rules.
- Init scripts do CI/IDE áp dụng.
- Plugin source của vendor nằm **ngoài repository**: chỉ biết bằng release notes, dependency graph, diagnostics khi plugin chạy.

Một API có thể **biên dịch được ở bản Gradle hiện tại nhưng đã deprecated**, và có thể bị xóa ở major release tương lai. Một API khác tuy không deprecated nhưng vẫn khiến build chậm hoặc không compatible Configuration Cache.

### 8.2. Nhóm kiểm kê ưu tiên

| Nhóm | Dấu hiệu trong code | Vì sao cần xem |
| --- | --- | --- |
| Task configuration | `tasks.create`, `tasks.all`, `tasks.register`, `tasks.named`. | Eager realization ảnh hưởng performance; chuyển sang lazy APIs khi đúng ngữ cảnh. |
| Lifecycle | `afterEvaluate`, taskGraph listeners, `gradle.projectsEvaluated`. | Compatibility, ordering và Configuration Cache risks; không tự coi mọi call là deprecated. |
| Dependency configurations | Legacy `compile`, `testCompile`, `runtime`; modern `implementation`, `testImplementation`. | Các configurations cũ có thể bị removed; cần theo migration guide/version. |
| Deprecated Gradle APIs | `org.gradle.util`, `org.gradle.internal`, removed properties/methods. | Internal APIs không ổn định; vendor plugin cũng có thể dùng. |
| Task inputs/outputs | `@Input`, `@OutputFile`, `@TaskAction`, `@Internal`. | Validation, build cache correctness, Configuration Cache. |
| Lazy properties | `Property<T>`, `Provider<T>`, `RegularFileProperty`, `DirectoryProperty`. | Avoid eager evaluation và hidden state. |
| Java compiler/tests | `options.release`, `javaCompiler`, `javaLauncher`, `useJUnitPlatform()`. | JDK/bytecode compatibility, test runtime. |
| Plugin development | `java-gradle-plugin`, `gradleApi()`, `gradlePlugin { }`, `validatePlugins`. | Plugin compiled against Gradle API and public task contract. |
| Repository/resolution | `pluginManagement`, `dependencyResolutionManagement`, `resolutionStrategy`, constraints. | Build/plugin graph and security/reproducibility. |
| DSL languages | Groovy DSL, Kotlin DSL, Gradle-embedded Groovy/Kotlin, custom plugin Java/Kotlin. | Embedded-language upgrade can break build scripts/plugins. |

Một tìm kiếm chữ `org.gradle.internal` chỉ là **red flag**, không tự chứng minh lỗi. Một plugin bên thứ ba có thể dùng internal APIs mà source không nằm trong repo, nên cần plugin compatibility reports và build tests.

### 8.3. Tìm trong files đã được Git theo dõi

Nếu team đồng ý đọc repository và có Git, chạy command **chỉ tìm/đọc**, không thay đổi source:

```bash
git ls-files -- '*.gradle' '*.gradle.kts' '*.toml' 'gradle.properties'
git grep -n -E 'pluginManagement|includeBuild|buildscript|apply plugin:|afterEvaluate|tasks.create|org.gradle.internal|org.gradle.util' -- '*.gradle' '*.gradle.kts' '*.toml'
```

`git ls-files` chỉ liệt kê **tracked** files. Một file chưa tracked/được CI generate hoặc init script nằm ngoài repo sẽ không xuất hiện. Git grep pattern là **triage**, không phải static analyzer/parser hiểu được Gradle DSL hoặc multiline rules. Không đọc/upload secret values chỉ để “scan triệt để”.

Nếu không có Git hoặc Windows shell có quoting khác, dùng editor “Find in Files” với cùng từ khóa và scope được phép. Đối với Kotlin DSL, còn cần tìm `tasks.register<...>`, `id("...")`, `alias(libs.plugins...)`, source imports.

### 8.4. --warning-mode=all để biết deprecations thực tế

Sau khi Wrapper được tin cậy:

```bash
./gradlew help --warning-mode=all --console=plain
./gradlew build --warning-mode=all --console=plain
```

- `help` cho warnings ở settings/project configuration hoặc plugin apply path.
- `build` kích hoạt compile/test/package; có thể phát hiện API deprecated chỉ được gọi trong task actions.
- Nhiều CI-specific tasks như publish/codegen/integrationTest **không nằm trong `build`**; cần chạy targeted tasks phù hợp trên môi trường được kiểm soát.
- `--warning-mode=all` hiện full deprecation messages, giúp tìm origin và migration link.
- `--warning-mode=fail` còn **fail build khi có warnings**, phù hợp làm quality gate **sau** khi baseline đã sạch, không nên bật ban đầu rồi coi mọi lỗi là Gradle migration blocker giống nhau.

Không nhầm compiler warnings của Java, Kotlin, plugin logs với **Gradle deprecation warnings**; phân loại theo nguồn. Một số plugin APIs chỉ break ở major version mới mà không có deprecation trước trong release đang chạy, nên vẫn cần đọc plugin compatibility matrix.

### 8.5. Task discovery và dry run

```bash
./gradlew projects
./gradlew tasks --all
./gradlew help --task test
./gradlew build --dry-run
```

Giới hạn:

- `projects` cho project hierarchy của main build; không chứng minh đã inventory đầy đủ included builds.
- `tasks --all` cho tên/tasks được Gradle nhìn thấy, không phải list của plugin versions.
- `help --task test` mô tả task, useful để hiểu task type/commands.
- `--dry-run` mô phỏng execution của task graph **không chạy task actions**, nhưng vẫn có initialization/configuration. Không thể dùng để chứng minh tests, compilation hoặc published artifacts tương thích.

## 9. Inventory dependencies có khác inventory plugins không?

Gradle `dependencies` và `dependencyInsight` chủ yếu mô tả **project configurations và module selections**:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight \
  --dependency commons-lang3 \
  --configuration runtimeClasspath
```

Các configuration names trên áp cho **Java plugin/project** trong lab. Dự án Android/Kotlin/custom plugin có configurations khác; dùng `./gradlew dependencies` để nhận diện tên hợp lệ trước.

**Lưu ý:**

- `dependencies` hiển thị graph và có thể resolve metadata; không nhất thiết tải mọi binary JAR nếu không cần.
- `dependencyInsight` giải thích selected version và lý do (constraints/BOM/conflicts), không tìm plugin IDs một cách tự động.
- `buildEnvironment` hiển thị buildscript classpath, nhưng **không phải toàn bộ plugin ID/version inventory**.
- Một library `org.junit.jupiter:junit-jupiter` **không phải Gradle plugin**.
- **Version catalog** xác định declarations, còn `dependencyInsight` cho actual selected version của một module trong configuration.

Nếu inventory cần **cả buildscript/plugin classpath và app dependencies**, nên có các cột/sections riêng. Không đặt tất cả dưới một nhãn “Gradle dependencies” rồi đánh mất khác biệt.

## 10. Lab thực hành Java 17+ — một baseline có thể kiểm kê

Lab này là **một single-project Gradle Groovy DSL**. Nó cố tình chỉ dùng core `application` plugin để không phụ thuộc vào một third-party Gradle plugin cụ thể; dùng một external **Java library** Commons Lang và JUnit để minh họa sự khác biệt plugin vs dependency.

Mục tiêu: chạy ứng dụng, hai JUnit tests, ghi các phiên bản `declared`, `observed`, JDK toolchain và build APIs.

### 10.1. Chuẩn bị

Cần JDK **17+** cho Gradle 9.x/JDK 17 toolchain, một Gradle Wrapper 9.9.0 **đã được tạo và xác minh** (hoặc pinned Gradle version tương thích của team), network/trusted Maven Central nếu dependencies chưa cache.

Cấu trúc:

```text
gradle-inventory-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/example/InventoryApp.java
    └── test/java/example/InventoryAppTest.java
```

Wrapper files phải được tạo từ `gradle wrapper` hoặc `gradle init` bằng installation trusted. Chỉ viết `build.gradle` không tự sinh `gradlew` hay JAR.

### 10.2. settings.gradle

```groovy
rootProject.name = 'gradle-inventory-lab'
```

### 10.3. build.gradle đầy đủ

```groovy
plugins {
    id 'application'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'

    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'example.InventoryApp'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Kiểm kê ngay từ code:**

- Plugin ID `application` là **core plugin**. Nó cũng áp `java` gián tiếp, không có `version '...'` external.
- `version='1.0.0'` là **project version**, không phải Gradle version hay plugin version.
- External Java library `commons-lang3:3.17.0` là **application dependency**, không phải Gradle plugin.
- JUnit BOM `5.11.4` alignment cho JUnit modules, khác Gradle release và target Java 17.
- `java.toolchain=17` yêu cầu Java compiler/test tools theo toolchain; `options.release=17` thiết lập target Java 17 API/bytecode.
- `tasks.withType(...).configureEach` và `tasks.named` là **lazy/task configuration APIs** đáng ghi vào build API inventory.
- `useJUnitPlatform()` kích hoạt JUnit Jupiter support cho test task.
- Không áp plugin external chỉ để làm inventory, tránh tạo dependency/plugin resolution không cần thiết trong baseline.

### 10.4. src/main/java/example/InventoryApp.java

```java
package example;

import org.apache.commons.lang3.StringUtils;

public final class InventoryApp {
    private InventoryApp() {
    }

    public static String message(String recipient) {
        return "Inventory: "
                + StringUtils.capitalize("hello")
                + ", " + recipient + "!";
    }

    public static void main(String[] args) {
        String recipient =
                args.length == 0 ? "Gradle" : args[0];
        System.out.println(message(recipient));
    }
}
```

`StringUtils.capitalize("hello")` trả `Hello`. Dự án Java yêu cầu external Commons Lang artifact khi compile; Gradle plugin `application` cung cấp task `run`.

### 10.5. src/test/java/example/InventoryAppTest.java

```java
package example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class InventoryAppTest {
    @Test
    void defaultRecipient() {
        assertEquals(
                "Inventory: Hello, Gradle!",
                InventoryApp.message("Gradle"));
    }

    @Test
    void customRecipient() {
        assertEquals(
                "Inventory: Hello, Team!",
                InventoryApp.message("Team"));
    }
}
```

Có **2 JUnit Jupiter test methods**. Test source không sử dụng trực tiếp Gradle API; Gradle Test task chịu trách nhiệm compile/run tests bằng toolchain/launcher tương ứng.

### 10.6. Lệnh thực hành

Linux/macOS:

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew build --warning-mode=all --console=plain
./gradlew -q run
./gradlew -q run --args="Team"
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains
.\gradlew.bat build --warning-mode=all --console=plain
.\gradlew.bat -q run
.\gradlew.bat -q run --args="Team"
```

**Stdout riêng của Java main khi không truyền args:**

```text
Inventory: Hello, Gradle!
```

**Stdout riêng khi truyền Team:**

```text
Inventory: Hello, Team!
```

Đây là stdout **của Java application**, không phải toàn bộ Gradle console transcript. Build logs, deprecation warnings, JDK vendor/toolchain paths có thể khác giữa các máy; **không bịa chính xác các dòng `./gradlew --version`**. Nếu môi trường tương thích và dependencies resolve thành công, hai JUnit tests **dự kiến PASS**; chỉ nói đã chạy thành công khi có báo cáo thực tế từ máy người học.

### 10.7. Inspect dependency graph trong lab

```bash
./gradlew dependencies \
  --configuration runtimeClasspath \
  --console=plain
./gradlew dependencies \
  --configuration testRuntimeClasspath \
  --console=plain
./gradlew dependencyInsight \
  --dependency commons-lang3 \
  --configuration runtimeClasspath \
  --console=plain
./gradlew buildEnvironment --console=plain
```

`buildEnvironment` có thể rất ít/nil dependencies vì lab dùng **core application plugin** và không khai báo legacy `buildscript.classpath`. Điều đó **không** có nghĩa `commons-lang3` hay JUnit không tồn tại: chúng thuộc project runtime/test configurations, không thuộc buildscript classpath.

### 10.8. Tạo một inventory record từ lab

| Mục | Requested/declared | Observed/evidence cần điền | Rủi ro |
| --- | --- | --- | --- |
| Gradle | Wrapper `9.9.0` nếu đã tạo đúng. | `./gradlew --version`, properties path/commit. | Wrapper không đúng version trên IDE/CI. |
| Gradle JVM | Java >= 17 theo Gradle 9.9 requirements. | Output version, Daemon criteria/JAVA_HOME/IDE. | Daemon JDK quá cũ/khác CI. |
| Java toolchain | `17`. | `javaToolchains` + selected compiler evidence. | JDK 17 không cài/không provision được. |
| Bytecode target | `--release 17`. | JavaCompile options/class major=61 khi kiểm. | Chạy app trên JVM <17. |
| Plugin | `application`, core. | build.gradle + Gradle core behavior. | Gradle major API changes. |
| App library | `commons-lang3:3.17.0`. | `runtimeClasspath` / dependencyInsight. | Dependency conflicts/CVE. |
| Tests | JUnit BOM `5.11.4`, Jupiter, launcher. | `testRuntimeClasspath`, test reports. | Test engine/version mismatch. |
| Build API | `tasks.named`, `configureEach`, `java.toolchain`. | build.gradle path/line + warning-mode output. | Incompatibilities khi nâng Gradle. |

**Đây là mẫu requested inventory**, không phải runtime results đã quan sát trên máy của người học. Điền `Observed` từ commands thật khi thực hành.

## 11. Mẫu kiểm kê cho dự án thật

### 11.1. Bảng thành phần

| ID | Layer | Scope | Declared | Observed/Resolved | Evidence | Owner | Compatibility | Action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| G-01 | Gradle Wrapper | root | `9.9.0-bin` | từ Wrapper `--version` | `gradle-wrapper.properties`, checksum | Build team | Gradle/JDK matrix | Keep/upgrade. |
| J-01 | Gradle Daemon JDK | CI/local | criteria/Java home | JVM thực tế | `--version`, CI config | Platform | Gradle Daemon >=17 | Align if needed. |
| J-02 | JavaCompile toolchain | `:app` | 17 | selected JDK | toolchain DSL+metadata | App team | Target 17 | Validate. |
| P-01 | Plugin | `:app` | ID + requested version | artifact/implementation | script/catalog/plugin portal | Build team | plugin release notes | Check. |
| P-02 | Internal convention | `build-logic` | source/project version | applied where | settings includeBuild + plugin sources | Platform | Gradle API compatibility | Test. |
| A-01 | Gradle API | `buildSrc` | task creation, Provider APIs | warnings + source | file:line / --warning-mode=all | Build team | deprecation/removal | Refactor. |

Đây là **schema**, các IDs/versions minh họa không phải discovered facts. Trong công ty nên lưu inventory trong tài liệu version-controlled và link đến exact source/PR, hạn chế hostnames/usernames/credentials.

### 11.2. Các trường bằng chứng quan trọng

- **Repository + commit SHA**: bảo đảm sau này biết đang kiểm kê phiên bản source nào.
- **Build boundary**: root build, từng included build, buildSrc, settings plugin và init/CI injected.
- **Scope**: project nào áp plugin; `apply false` hay applied thực.
- **Declared vs effective**: version từ script/catalog vs artifact/daemon/compiler thực tế.
- **Source line/command**: file:line, `--version`, `dependencyInsight`, deprecation warning.
- **Target version/risks**: plugin supports target Gradle/JDK? SDK/AGP/Kotlin compiler phù hợp?
- **Confidence**: observed, inferred from declaration, unknown.
- **Owner and next action**: chịu trách nhiệm cập nhật plugin/build logic/test.
- **Privacy**: không đưa raw repository tokens/CI secrets/private file contents vào báo cáo chung.

Nếu không biết requested plugin version đến từ đâu, **đừng điền 1.2.3 theo phỏng đoán**. Đánh dấu unknown, truy vết `pluginManagement`, catalog và dependency resolution rules.

## 12. Tạo compatibility matrix trước khi chọn phiên bản đích

Một migration plan hiệu quả nên đánh giá các quan hệ:

| Quan hệ | Vì sao phải kiểm |
| --- | --- |
| Gradle target ↔ Gradle Daemon JVM | Gradle 9.x cần Daemon JVM 17+, một số Java releases mới chỉ được support từ Gradle minor cụ thể. |
| Gradle target ↔ Java toolchain | Compiler/launcher support khác với daemon support; Java version rất mới có thể chưa support đầy đủ. |
| Gradle target ↔ Gradle core APIs | Deprecated/removed DSL/configuration/task APIs, embedded Groovy/Kotlin changes. |
| Gradle target ↔ external plugin version | Plugin có thể gọi Gradle internal APIs hoặc dùng plugin markers/transform APIs không còn phù hợp. |
| Plugin version ↔ Kotlin/AGP/Android SDK | Vendor compatibility matrix riêng; Gradle compatibility chưa đủ. |
| Gradle/Java toolchain ↔ test frameworks | JUnit engine, TestKit, Test task launcher, bytecode target. |
| Compiler target ↔ production runtime | `--release 17` không chạy được trên JVM 11; CI deployment target cần khớp. |
| IDE/CI/Wrapper ↔ developers | IDE Gradle sync JDK và CI runtime có thể khác local shell. |

Ví dụ **không suy diễn**: biết Gradle 9.9 hỗ trợ Daemon JVM 17+ **không đủ** để khẳng định plugin external version 1.2.3 hỗ trợ Gradle 9.9. Cần nhà phát hành plugin release notes/compatibility table và build tests.

### 12.1. Source of truth

Ưu tiên:

1. Gradle official **Compatibility Matrix** cho Gradle/JDK/embedded languages.
2. Gradle official **Upgrade Guide** cho breaking changes và deprecations.
3. Plugin vendor release notes/Gradle Plugin Portal metadata + actual tested compatibility.
4. CI/IDE configuration thực tế và TestKit/regression tests.
5. Source declarations + resolution logs.

Không dùng một bảng “Java 17 tương thích mọi Gradle 9.x” để bỏ qua từng Gradle release/JDK minor specifics. Cũng không nâng Java language target chỉ vì Gradle Daemon phải lên 17.

## 13. Từ inventory thành upgrade plan có kiểm soát

**Pha 1 — Baseline:** giữ nguyên Wrapper/plugins/JDK, chạy `help`, `build`, `test`, `--warning-mode=all`, key CI tasks và lưu logs.

**Pha 2 — Plugin compatibility:** với plugins bị deprecations/internal API, xác định target plugin release và các dependent plugins; không cố nâng Gradle rồi mới cập nhật plugin đã biết không tương thích.

**Pha 3 — Gradle Wrapper:** nâng Gradle theo một PR riêng, kèm Wrapper scripts/JAR/properties + official ZIP SHA; review migration guide và `./gradlew --version`.

**Pha 4 — JVM/toolchains:** giữ app target tương thích deployment, đổi Daemon JVM nếu Gradle yêu cầu, điều chỉnh project toolchains có chủ đích, test CI/IDE.

**Pha 5 — Build APIs:** chuyển APIs deprecated/removed sang alternatives theo Gradle docs; tránh vừa đổi plugin conventions vừa chuyển DSL Java sang Kotlin trong cùng PR nếu không cần.

**Pha 6 — Validation:** compile, test, packaging, codegen, integrationTest/publishing, configuration cache, build cache, TestKit và matrix theo nhiệm vụ.

**Pha 7 — Lock baseline:** commit documented inventory matrix, Wrapper/checksum, plugin version catalogs và dependency/verification lockfiles theo policy; cập nhật runbooks.

Chỉ tuyên bố migration hoàn tất khi **runtime versions, plugin declarations/resolution, build APIs và CI jobs** đều đã được kiểm lại.

## 14. Những lỗi thường gặp khi kiểm kê

| Triệu chứng | Nguyên nhân phổ biến | Cách xử lý |
| --- | --- | --- |
| `gradle --version` khác `./gradlew --version` | Global installation và project Wrapper khác. | Ghi cả hai, dùng Wrapper làm baseline. |
| `java -version` là 21 nhưng Gradle dùng 17 | Daemon criteria hoặc `org.gradle.java.home`, IDE setting. | Kiểm Daemon JVM config/output. |
| `javaToolchains` thấy 3 JDK | Lệnh liệt kê available installations. | Xác định selected compiler/launcher của task. |
| Gradle 9.x fail trước configuration trên JDK 11 | Gradle Daemon cần JVM 17+. | Chạy trên supported JDK, giữ toolchain target riêng. |
| Đọc `options.release=11` và kết luận Daemon là 11 | Target bytecode khác runtime Gradle. | Kiểm --version/Daemon separately. |
| Plugin không có version trong build.gradle | Version đến từ pluginManagement/catalog, core plugin hoặc included build. | Truy vết all sources. |
| Root `apply false` bị tính là root applied plugin | Declaration không đồng nghĩa apply. | Phân biệt requested/available và applied. |
| `buildEnvironment` báo không có dependencies | Chỉ phản ánh buildscript classpath. | Kiểm plugins DSL riêng và project configurations. |
| `dependencies` bị dùng để tìm plugin IDs | Đây chủ yếu là dependency graph report. | Truy vết plugin declarations/markers/build logic. |
| Core `application` bị ghi version 1.0.0 | 1.0.0 là project version. | Core plugin follows Gradle release. |
| Test chỉ chạy `help` nên không thấy warning ở custom task | Task action chưa chạy. | Chạy targeted workflow/CI tasks. |
| `--dry-run` PASS nhưng compile/test thật fail | Dry-run không execute actions. | Chạy thực trên môi trường an toàn. |
| grep không thấy plugin version | Multiline/alias/dynamic resolution/init script/untracked files. | Tìm scoped files và resolve policy; không suy đoán. |
| Source tìm thấy `org.gradle.internal` | API nội bộ, có thể không ổn định. | Xem source/release notes và migrate public API khi có thể. |
| Plugin bên thứ ba dùng internal API mà repo không thấy | Plugin source nằm trong artifact. | Kiểm vendor release notes/build tests/deprecation logs. |
| CI khác local | Wrapper override, Daemon JVM/IDE JDK, toolchain/mirror/CI flags. | So inventory theo environment. |
| Không có thông tin compiler JDK chính xác | Chỉ nhìn JAVA_HOME/javaToolchains. | Kiểm JavaCompile.javaCompiler và toolchain selection. |
| Inventory chụp cả passwords từ gradle.properties | Đọc/ghi raw secrets vào báo cáo. | Redact paths/tokens/credentials, chỉ ghi key/status. |
| Một “plugin version” khác Maven artifact version | Plugin marker mapping dẫn tới implementation artifact. | Ghi cả ID/requested version và implementation/resolution. |

## 15. Bài tập thực hành

**Bài 1 — Gradle version:** một terminal báo global Gradle 8.x nhưng Wrapper properties pin 9.9.0. Khi CI gọi `./gradlew`, version nào là baseline? **Wrapper 9.9.0**, cần xác nhận qua `./gradlew --version`.

**Bài 2 — JVM:** `java -version` báo 21, `gradle-daemon-jvm.properties` yêu cầu 17. Có được ghi “Gradle Daemon=21” chỉ từ shell không? **Không**, phải xem Daemon criteria và actual JVM.

**Bài 3 — Compiler:** `java.toolchain.languageVersion=17` nhưng `options.release=11`. Sự khác nhau? **JDK 17 compiler, Java 11 bytecode/API target** (nếu Gradle/JDK supports).

**Bài 4 — JVM vs classfile:** một class có major version 61. Nó chứng minh Java target 17, nhưng có chứng minh đã dùng Java 17 compiler vendor cụ thể không? **Không**.

**Bài 5 — Core plugin:** `plugins { id 'application' }`. Cần ghi external version của application plugin không? **Không**, core plugin bundled with Gradle.

**Bài 6 — Plugin alias:** `plugins { alias(libs.plugins.quality) }`. Version ở đâu? **Version catalog hoặc imported catalog definition**.

**Bài 7 — apply false:** Root có `id 'org.example.code-quality' version '1.2.3' apply false`. Có chứng minh plugin applied vào root không? **Không**.

**Bài 8 — buildEnvironment:** Report trống nhưng repo dùng `plugins { id 'application' }`. Có mâu thuẫn không? **Không**; buildscript classpath khác plugins DSL/core plugins.

**Bài 9 — Legacy plugin:** `apply plugin: 'org.example.code-quality'` không có version. Tìm tiếp ở đâu? **buildscript classpath/pluginManagement/init/convention context**.

**Bài 10 — Included build:** Settings có `pluginManagement { includeBuild('build-logic') }`. Điều gì cần kiểm kê thêm? **Gradle/plugin version, compiler target và build APIs của build-logic**.

**Bài 11 — Deprecated API:** `--warning-mode=all help` không có warnings. Có đủ kết luận không deprecated APIs nào trong custom task actions không? **Không**; chạy relevant tasks.

**Bài 12 — Eager API:** `tasks.create` có thể gây eager configuration. Có luôn là lỗi compile/deprecated không? **Không mặc định**; đánh giá task avoidance và version cụ thể.

**Bài 13 — Internal API:** code import `org.gradle.internal.X`. Điều gì cần làm? **Xác định public alternative, plugin origin và target Gradle compatibility**.

**Bài 14 — Dependency graph:** muốn biết vì sao `commons-lang3` resolved version 3.17.0, dùng gì? **dependencyInsight** trên đúng configuration.

**Bài 15 — Test engine:** JUnit API có version từ BOM nhưng `test` không chạy. Có thể do đâu? **Junit Platform/engine/runtime classpath/test task config**, không nhất thiết Gradle Wrapper version.

**Bài 16 — CI:** local uses Wrapper/JDK 21, CI overrides Gradle JVM to 17. Trong inventory ghi gì? **Hai environments có bằng chứng khác nhau**.

**Bài 17 — Plugin marker:** plugin ID khác implementation module name. Có bug không? **Không nhất thiết**, marker artifact có thể map ID/version tới implementation coordinates khác.

**Bài 18 — --dry-run:** `./gradlew build --dry-run` PASS có chứng minh tests PASS không? **Không**, task actions không chạy.

**Bài 19 — Security:** Có nên chạy `./gradlew help` trên repo chưa kiểm Wrapper với CI secrets để chỉ kiểm kê không? **Không**, build logic có thể execute code.

**Bài 20 — Migration:** trước khi đổi Wrapper, cần tối thiểu những bằng chứng gì? **Current Gradle/JDK/IDE/CI versions, plugin IDs/versions/origins, build APIs/deprecations, baseline test/CI outputs và target compatibility matrix**.

### Tự kiểm tra nhanh

1. **Gradle release nằm ở đâu?** Wrapper `distributionUrl`.
2. **Lệnh version chuẩn?** `./gradlew --version`.
3. **Global Gradle luôn bằng Wrapper?** Không.
4. **Gradle 9.x Daemon cần Java tối thiểu?** 17.
5. **JAVA_HOME chứng minh compiler JDK?** Không.
6. **Gradle Daemon criteria ưu tiên JAVA_HOME?** Có khi được cấu hình.
7. **Liệt kê detected JDKs?** `javaToolchains`.
8. **Detected toolchains đồng nghĩa selected compiler?** Không.
9. **`options.release` chọn JDK binary?** Không.
10. **Core application plugin có external version?** Không.
11. **Version catalog lưu aliases gì?** Libraries/plugins/versions/bundles.
12. **apply false nghĩa applied?** Không.
13. **buildEnvironment liệt kê mọi plugins DSL?** Không.
14. **dependencies là plugin inventory tool hoàn chỉnh?** Không.
15. **plugin marker có thể khác implementation module?** Có.
16. **help chạy task actions?** Không phải mọi task action.
17. **--dry-run xác minh test results?** Không.
18. **--warning-mode=all dùng làm gì?** Show deprecation warnings.
19. **org.gradle.internal ổn định public API?** Không.
20. **Migration phải validate CI/IDE?** Có.

## 16. Tài liệu chính thức để đối chiếu

- **Gradle Wrapper:** nguồn distribution version, scripts/JAR, checksum, cách upgrade: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- **Gradle Compatibility Matrix:** Gradle JVM, Java toolchains và hỗ trợ Gradle releases: https://docs.gradle.org/current/userguide/compatibility.html
- **Gradle Daemon:** client vs daemon, criteria, `org.gradle.java.home`, `updateDaemonJvm`: https://docs.gradle.org/current/userguide/gradle_daemon.html
- **Gradle Toolchains:** toolchain compiler/launcher, `javaToolchains`, `--release`: https://docs.gradle.org/current/userguide/toolchains.html
- **Gradle Build Environment:** gradle.properties, JAVA_HOME, configuration precedence: https://docs.gradle.org/current/userguide/build_environment.html
- **Gradle Plugin Management:** core/external IDs, plugin marker artifacts, repositories: https://docs.gradle.org/current/userguide/plugins_intermediate.html
- **Gradle Version Catalogs:** aliases, declared versions và imported catalogs: https://docs.gradle.org/current/userguide/version_catalogs.html
- **Gradle Multi-Project:** project hierarchy/boundary: https://docs.gradle.org/current/userguide/multi_project_builds.html
- **Gradle Composite Builds:** included builds và plugin development builds: https://docs.gradle.org/current/userguide/composite_builds.html
- **Gradle Viewing Dependencies:** `dependencies`, `dependencyInsight`: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- **Gradle Command-Line Interface:** `--warning-mode=all`, `--dry-run`, task reports: https://docs.gradle.org/current/userguide/command_line_interface.html
- **Gradle 9 Upgrade Guide:** Gradle API removals/deprecations, migration steps: https://docs.gradle.org/current/userguide/upgrading_major_version_9.html
- **Gradle 9.x Upgrade Notes:** latest 9.x deprecations/plugin compatibility considerations: https://docs.gradle.org/current/userguide/upgrading_version_9.html
- **Gradle Plugin Development:** task API/validation and Java plugin development: https://docs.gradle.org/current/userguide/javaGradle_plugin.html
- **Java 17 class-file major versions:** Java Virtual Machine Specification: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html

**Kết luận:** Để nâng cấp Gradle an toàn, hãy **kiểm kê bản Wrapper thật**, **tách Gradle Daemon JVM khỏi Java compiler/test toolchains và bytecode target**, **truy vết plugin ID/version qua settings, catalogs, legacy classpaths và included builds**, rồi **kiểm kê Gradle build APIs và deprecation warnings theo các tasks được chạy thật**. Ghi requested/declared và observed/resolved riêng, gắn bằng chứng vào một compatibility matrix, giữ nguyên baseline và chỉ chọn target upgrade sau khi hiểu mọi dependency/build-logic boundary.