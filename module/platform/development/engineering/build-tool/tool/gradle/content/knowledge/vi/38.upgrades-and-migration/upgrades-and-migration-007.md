# Giữ nguyên hành vi dependency, kiểm thử và đóng gói khi di chuyển Gradle

## 1. Mục tiêu: chuyển công cụ hoặc phiên bản nhưng không đổi hợp đồng sản phẩm

Bài thuộc nhóm **Nâng cấp và di chuyển** của chủ đề **Build Tool Gradle**. Một lần migration có thể là:

- Nâng **Gradle Wrapper** từ phiên bản cũ lên một phiên bản mới, đặc biệt từ Gradle 8.x sang 9.x.
- Đổi **Groovy DSL sang Kotlin DSL** trong cùng Gradle build.
- Di chuyển **Maven/Ant sang Gradle**, từ multi-module Maven sang multi-project Gradle.
- Nâng plugins như Java, Kotlin, Spring Boot, Shadow, JaCoCo, publishing hoặc testing integrations.
- Tách monolith thành nhiều subprojects, đổi repository hoặc CI runner/JDK mà vẫn muốn giữ sản phẩm tương đương.

Một migration **thành công** không chỉ có nghĩa lệnh `./gradlew build` trả exit code 0. Nó phải bảo toàn những **hợp đồng quan sát được** mà team đã chấp nhận:

1. **Dependency contract:** đúng các modules/versions/variants, classpath compile/runtime/test, API exposure, exclusions, BOM alignment, repository trust và artifact integrity.
2. **Test contract:** cùng tests hoặc phạm vi tests dự định chạy, cùng engine, assertions, test inputs/JVM flags, kết quả và ngưỡng coverage, không âm thầm bỏ test.
3. **Packaging contract:** đúng artifact coordinates, tên và loại JAR/ZIP/TAR/WAR, classes/resources, manifest, launcher, runtime libraries, metadata, permissions và các đầu ra publish.
4. **Runtime contract:** cùng hành vi ứng dụng, exit code/stdout/stderr hoặc giao thức/API công khai, Java target, startup flags và cách chạy trên môi trường thật.
5. **Reproducibility/security contract:** lockfiles, verification metadata, signatures, secrets và nguồn binary được kiểm soát; khi cần byte-identical phải có quy trình xác minh riêng.

Bài dùng một **Gradle Kotlin DSL + Java 17 multi-project sample** chạy được, với test và kiểm tra archive bằng một chương trình Java 17 thứ hai. Sau đó hướng dẫn thu thập baseline, so sánh hai phiên bản, phát hiện drift và khóa quality gates trong CI.

**Nguyên tắc:** Migration phải tách **thay đổi công cụ** khỏi **thay đổi nghiệp vụ/dependency**. Nếu đồng thời nâng 25 thư viện, đổi Java runtime và đổi định dạng gói, khi kết quả khác sẽ rất khó xác định nguyên nhân.

## 2. Phân biệt “giống hành vi” và “giống byte”

| Mức tương đương | Câu hỏi | Ví dụ kiểm chứng |
| --- | --- | --- |
| Behavioral parity | Người dùng/ứng dụng khác có quan sát cùng kết quả? | Java output, API contract, integration test |
| Dependency parity | Resolved modules/versions/variants có phù hợp baseline? | `dependencies`, `dependencyInsight`, lockfiles |
| Test execution parity | Thực sự chạy đúng tests và engine? | XML reports, test count, failures/skips |
| Packaging semantic parity | Nội dung JAR/ZIP/metadata đúng contract? | `jar tf`, manifest, distribution lib/bin |
| Binary reproducibility | Hai build có cùng bytes/hash? | SHA-256, controlled environment, reproducible archive settings |
| Publication parity | Consumer nhận đúng group/artifact/version/POM/Gradle metadata? | Local publish và consumer smoke test |

Hai JAR có thể có **hash khác** vì timestamp entry, file ordering, manifest metadata, build-info, launcher scripts hoặc Java compiler patch version, mặc dù Java runtime output tương đương. Ngược lại, hai JAR có gần như cùng nội dung nhưng **thiếu một transitive runtime dependency** ở distribution có thể gây `NoClassDefFoundError` khi deploy.

Vì vậy hãy xác định **mức parity bắt buộc theo từng artifact**:

- **Thư viện public:** semantic API + dependencies metadata + binary compatibility/ABI + JAR contents.
- **CLI app:** startup/exit/stdout/stderr + runtime classpath + launcher/distribution layout.
- **Web service:** endpoints/configuration/integration tests + container/package contents.
- **Release artifacts có yêu cầu reproducibility:** thêm SHA-256 byte-for-byte khi input/toolchain đủ được cố định.
- **Internal build task:** input/output/task graph contract và CI automation.

Không coi SHA-256 bằng nhau là tiêu chí duy nhất, cũng không bỏ qua hash differences khi policy yêu cầu reproducible releases.

## 3. Chốt baseline trước khi sửa bất kỳ build script nào

### 3.1. Ghi rõ “before” và “after”

Mỗi migration cần một bảng baseline tối thiểu:

| Thuộc tính | Before | After | Đánh giá |
| --- | --- | --- | --- |
| Gradle/Maven version | Ghi theo CLI | Ghi theo CLI | Có chủ đích |
| JDK running build | Vendor + version | Vendor + version | Compatible |
| Java target/toolchain | Java 17 | Java 17 | Không drift |
| Modules | :api, :app | :api, :app | Đúng graph |
| Runtime dependencies | Coordinates/selected versions | Coordinates/selected versions | Không đổi ngoài approved |
| Test cases | Đếm và tên tests | Đếm và tên tests | Không mất test |
| Test engine/JVM args | JUnit Jupiter + config | Tương đương | Không giảm coverage |
| JAR contents | Inventory + manifest | Inventory + manifest | Đúng contract |
| Distribution | bins/libs/config | bins/libs/config | Chạy được |
| Artifact identity | group/name/version | group/name/version | Consumer không bị gãy |
| Publish metadata | POM/Gradle metadata | POM/Gradle metadata | Scope/variant đúng |

Không đủ khi báo “Before: BUILD SUCCESSFUL, After: BUILD SUCCESSFUL”. Cần lưu bằng chứng về graph, actual executed tests, archive inventory và binary behavior.

### 3.2. Giữ bằng chứng tách khỏi build outputs

Ví dụ dùng thư mục ở **ngoài project** hoặc CI artifacts để tránh `clean` xóa baseline:

~~~text
migration-evidence/
├── before/
│   ├── versions.txt
│   ├── projects.txt
│   ├── compile-classpath.txt
│   ├── runtime-classpath.txt
│   ├── test-runtime-classpath.txt
│   ├── test-results/
│   ├── artifact-inventory.txt
│   ├── manifest.mf
│   ├── sha256.txt
│   └── expected-behavior.txt
└── after/
    └── ...
~~~

Bảng cấu trúc này là **kế hoạch lưu chứng cứ**; các files không tự được tạo chỉ vì Gradle chạy `build`. Trong thực tế hãy lưu ở CI job artifacts có access policy, tránh commit generated outputs/secrets vào repo.

### 3.3. Baseline cần kiểm soát điều kiện chạy

Pin hoặc ghi nhận:

- Gradle Wrapper distribution, plugins và build scripts commit SHA.
- JDK major/vendor/patch version chạy Gradle và JDK toolchains.
- OS/architecture, locale, timezone và file encoding.
- Gradle repositories/mirror URLs, credentials scopes và network policy.
- Test environment variables/system properties, fixtures và external services.
- Build Cache/Configuration Cache/daemon state; nếu đo hiệu năng phải tách warm/cold.
- Dependency lock state, verification metadata và plugin versions.
- Build-time values như commit/version/build timestamp và signing inputs.

Một byte-for-byte comparison từ Windows JDK 17.0.x sang Linux JDK 21, khác plugins và khác timestamps có thể thất bại dù migration về chức năng đúng. Đừng đổi benchmark conditions mà không ghi lý do.

## 4. Quy trình migration có checkpoints và rollback

~~~text
Freeze baseline (old build)
            |
            v
Capture dependencies + tests + archives + runtime
            |
            v
Change one layer:
  Wrapper OR DSL OR plugins OR build system
            |
            v
Resolve model & task graph
            |
            v
Dependency parity gate
            |
            v
Test execution parity gate
            |
            v
Packaging/publishing/runtime gate
            |
            v
Reproducibility/security review
            |
       +----+----+
       |         |
     PASS       FAIL
       |         |
       v         v
  Candidate   Revert/repair one change
       |
       v
CI matrix, staged release, monitor, promote
~~~

**Rollback cần có đường cụ thể:** giữ Wrapper/build files baseline trong Git, lưu artifact baseline đã kiểm tra, không ghi đè release binary trong repository và không xóa lockfiles cũ khi chưa có quyết định. Dùng một branch/PR riêng cho migration; nếu fail, revert commit build config theo quy trình, không dùng `--refresh-dependencies` như “rollback”.

## 5. Dependency parity: phải so cái gì?

Những câu hỏi quan trọng:

1. **Declared dependencies:** các `implementation`/`api`/`runtimeOnly`/`compileOnly`/`testImplementation` có đúng ý đồ?
2. **Resolved dependencies:** cuối cùng Gradle chọn **version nào** sau conflict resolution, BOM, constraints, capabilities, attributes và substitutions?
3. **Variant parity:** consumer lấy API variant hay runtime variant? Library Java có `apiElements` và `runtimeElements` khác nhau.
4. **Transitive scope:** thư viện được xuất ra consumer API hay chỉ dùng nội bộ?
5. **Module identity:** group/name/version, classifier, extension, repository identity.
6. **Artifact bytes:** cùng version tọa độ nhưng private mirror khác có thể là binary khác.
7. **Exclusions:** old build có exclude logging/XML/test engine library không? New build có giữ đúng không?
8. **Plugins/tooling dependencies:** Gradle plugin classpath nằm ngoài app runtime classpath; đừng trộn.
9. **Lock/verification policy:** dependency versions/sha256/signatures có được kiểm soát và review?
10. **Dynamic/changing versions:** nếu baseline dùng `1.+` hoặc SNAPSHOT, resolution có thể đổi không do migration.

### 5.1. Declared khác resolved

Một dòng:

~~~kotlin
implementation("com.example:library:1.0")
~~~

là **mảnh minh họa**, không khẳng định artifact tồn tại. Gradle có thể chọn phiên bản mới hơn vì một transitive dependency, constraint, platform hoặc conflict rule. Vì thế so chuỗi trong `build.gradle.kts` **không đủ**.

Dùng:

~~~bash
./gradlew :app:dependencies --configuration compileClasspath --console=plain
./gradlew :app:dependencies --configuration runtimeClasspath --console=plain
./gradlew :app:dependencies --configuration testRuntimeClasspath --console=plain
~~~

và truy vấn nguyên nhân lựa chọn:

~~~bash
./gradlew :app:dependencyInsight \
  --configuration runtimeClasspath \
  --dependency junit-jupiter \
  --console=plain
~~~

Trong lab, JUnit chỉ nằm trong `test` configurations; muốn xem JUnit phải dùng `testRuntimeClasspath` thay vì `runtimeClasspath`. Một dependency report `runtimeClasspath` thiếu JUnit là hành vi **đúng**, không phải bug.

### 5.2. Đừng so raw dependency report byte-for-byte

Gradle version khác có thể đổi formatting, arrows, task headers, selection reason wording và thứ tự hiển thị. Cần chuẩn hóa thành tập `group:name:resolvedVersion + variant/capability` nếu cần tự động hóa. Có thể lưu raw reports để điều tra, nhưng diff raw logs là **tín hiệu**, không phải kết luận parity cuối cùng.

### 5.3. Direct/transitive và dependency tree

Một dependency có thể không xuất hiện trực tiếp trong build script nhưng vẫn có trong runtimeClasspath vì transitive dependency. Nếu Maven baseline có `dependency:tree` mà Gradle candidate dùng variant-aware resolution, mỗi cạnh và scope có thể cần đối chiếu bằng semantics, không chỉ tên artifact.

## 6. Maven scopes sang Gradle configurations

Khi di chuyển từ Maven:

| Maven | Gradle thường dùng | Lưu ý |
| --- | --- | --- |
| `compile` cho API cần công khai | `api` (Java Library) | Public consumer compileClasspath cần type |
| `compile` cho phụ thuộc nội bộ | `implementation` | Không rò API không cần thiết |
| `provided` | `compileOnly` hoặc plugin-specific provided | Runtime container phải thật sự cung cấp dependency |
| `runtime` | `runtimeOnly` | Chỉ khi chạy |
| `test` | `testImplementation`/`testRuntimeOnly` | Cần JUnit engine/launcher phù hợp |
| `annotationProcessorPaths` | `annotationProcessor` | Không tự đưa processor lên runtime |
| `dependencyManagement` BOM | `platform(...)` hoặc `java-platform` | BOM constraints khác forced versions |
| Maven modules | Gradle `include(":...")` | Đường module, group, artifact names cần đối chiếu |

**Không có mapping 1:1 tuyệt đối** cho mọi Maven plugin scope/optional dependency. Maven `optional`, dependencyManagement, classifier, profiles và shade configurations cần đánh giá theo use case.

### 6.1. Khi nào chọn api?

Nếu public class hoặc method của library dùng type `com.vendor.Type` trong method signature, consumer thường cần phụ thuộc ấy trên compile classpath; khai báo `api` tương ứng trong `java-library`. Nếu type chỉ được dùng bên trong method body, `implementation` thường đúng. Sai ở đây có thể khiến internal module vẫn compile vì classpath rộng nhưng downstream consumer bị lỗi.

### 6.2. Mô hình version constraints và BOM

~~~kotlin
dependencies {
    implementation(platform("org.example:vendor-bom:1.2.3"))
    implementation("org.example:vendor-api")
}
~~~

Đây là **đoạn minh họa với tọa độ giả**, không chạy độc lập. `platform` nhập constraints nhưng **không tự thêm tất cả BOM modules**. `enforcedPlatform` có semantics ép version mạnh hơn, có thể lan tới downstream consumers; không đổi `platform` sang `enforcedPlatform` chỉ để “hết conflict” khi migration.

Nếu đổi Maven BOM sang Gradle catalog, cần nhớ **version catalog chủ yếu khai báo requested versions**, không tự áp constraints cho transitive graph giống một platform. Migration vẫn phải kiểm tra resolved classpaths.

## 7. Dependency locking và verification: giữ resolution ổn định

Gradle dependency locking pin selected versions của direct và transitive dependencies cho những configurations đã bật locking. Nó giúp bảo toàn version graph qua migration và ngăn dynamic versions bất ngờ nâng cấp.

Một **mảnh Gradle Kotlin DSL áp dụng khi dự án cần locking**:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Để tạo/update lock state, chạy những tasks thực sự resolve configurations cần khóa, kèm `--write-locks`:

~~~bash
./gradlew :app:dependencies \
  --configuration runtimeClasspath \
  --write-locks \
  --console=plain
~~~

Nếu muốn khóa test runtime, chạy thêm `testRuntimeClasspath`. **Không** giả định một lệnh chỉ resolve runtimeClasspath sẽ khóa cả test, compile, annotationProcessor hoặc plugin classpaths. Lockfiles được lưu vào source control sau khi kiểm tra diff.

### 7.1. Cẩn thận với changing/SNAPSHOT modules

Lockfile cố định version coordinates nhưng không đóng băng bytes của một SNAPSHOT có thể bị publish lại. Gradle docs không khuyến nghị dùng locking như giải pháp cho changing modules. Với release, cần artifact repository bất biến, checksums/signatures hoặc verification metadata.

### 7.2. Dependency verification

`gradle/verification-metadata.xml` có thể dùng SHA-256/signatures để xác minh downloaded modules/metadata và plugins. Trong migration, khi dependency version hoặc repository origin đổi, verification có thể phát hiện binary khác. Đừng giải quyết bằng việc bật verification mode `off` hoặc copy một checksum chưa kiểm chứng.

Khi chủ động bổ sung artifact, Gradle có lệnh:

~~~bash
./gradlew --write-verification-metadata sha256 help
~~~

**Chỉ dùng như thao tác bootstrap/update có review.** Không tự động commit mọi hash được sinh mà không đối chiếu nguồn tin cậy. Một số dependency chỉ được resolve khi thực thi task đặc biệt có thể chưa xuất hiện trong lần bootstrap.

### 7.3. Version catalogs không phải lockfiles

`libs.versions.toml` gom declared coordinates và version aliases; nó **không** chứng minh resolved transitive versions bất biến. Khi migrate build scripts sang catalog, baseline phải tiếp tục kiểm tra `dependencyInsight` và locking/verification theo policy.

## 8. Test parity: test phải thật sự chạy

Một migration có thể gây hậu quả nguy hiểm: build xanh nhưng **mất một phần test coverage** vì Gradle Test task không chạy bất kỳ test nào.

Kiểm tra:

1. Tên/danh sách test classes và methods được discovery.
2. Test engine: JUnit Platform/JUnit Jupiter, JUnit4/Vintage, TestNG, Spock.
3. Gradle `Test` task classpath/testClassesDirs/source sets.
4. Include/exclude filters, tags, suites, categories và test selection.
5. Số tests passed/failed/skipped, không chỉ `BUILD SUCCESSFUL`.
6. JVM toolchain, `systemProperty`, `jvmArgs`, environment và locale/timezone.
7. Forking, parallel tests, maxParallelForks/forkEvery và ordering dependencies.
8. Test resources/fixtures và working directory.
9. Test task dependencies: unit, integration, contract, smoke.
10. XML/HTML reports, coverage thresholds và CI publication.

### 8.1. JUnit Platform và engine

Với JUnit Jupiter thông thường:

~~~kotlin
dependencies {
    testImplementation(platform("org.junit:junit-bom:5.10.2"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Đây là một fragment Gradle Kotlin DSL có thể đặt trong project có Java plugin + repository, chứ không phải file build đầy đủ. **`useJUnitPlatform()` chọn test runner**, không tự thêm tất cả JUnit libraries. Với JUnit4 legacy tests chạy bằng Jupiter Platform, có thể cần Vintage engine hoặc migration assertions; đừng ngầm bỏ test cũ.

### 8.2. Gradle 9: thay đổi đáng chú ý với Test tasks

Theo guide nâng từ Gradle 8 sang 9:

- Các **custom `Test` tasks** trước đó dựa vào conventions mặc định của `test` source set có thể **không còn tự được gán `testClassesDirs` và `classpath`**; task riêng có thể không chạy test, đôi khi không fail ngay.
- Với task `test` chuẩn và có test sources, Gradle 9 chặt chẽ hơn khi **không tìm thấy test** trong trường hợp không áp filters; điều này giúp phát hiện cấu hình engine sai.
- Default framework versions qua JVM Test Suite plugin cũng có thể đổi khi upgrade; phải pin framework version nếu parity yêu cầu.

Đừng nhìn một Gradle task tên `integrationTest` rồi kết luận nó thật sự discover tests.

### 8.3. Sửa custom Test task không có classes/classpath

**Ví dụ sai/thiếu:**

~~~kotlin
tasks.register<Test>("integrationTest") {
    useJUnitPlatform()
}
~~~

Nó có Test task nhưng **chưa khai báo test classes và runtime classpath**. Một bản build cũ có thể dựa vào conventions mặc định; ở Gradle 9 nên định nghĩa rõ hoặc dùng JVM Test Suite plugin.

**Mảnh sửa minh họa cho task cố ý chạy lại bộ test mặc định:**

~~~kotlin
tasks.register<Test>("verifySameTests") {
    description = "Chạy lại test source set với cấu hình tường minh."
    testClassesDirs = sourceSets.test.get().output.classesDirs
    classpath = sourceSets.test.get().runtimeClasspath
    useJUnitPlatform()
}
~~~

Đoạn trên yêu cầu Java plugin và sourceSets accessors, được đặt ở project script thích hợp. Nếu mục tiêu **integration test riêng**, không sử dụng lại `sourceSets.test` như ví dụ: hãy tạo `integrationTest` source set/JVM test suite riêng và wire dependencies/fixtures/outputs đúng.

Lựa chọn hiện đại cho test suites là JVM Test Suite plugin, với `JvmTestSuite` và một target/task riêng. Không chuyển từ Maven Failsafe sang Gradle `test` duy nhất rồi bỏ mất integration tests.

### 8.4. Đừng tắt no-tests check để làm xanh build

Có thể tìm thấy hướng dẫn đặt `failOnNoDiscoveredTests = false`; việc này có tình huống hợp lý như optional test source, nhưng **không nên dùng làm workaround mặc định** trong migration. Hãy kiểm tra vì sao test không được discover hoặc engine thiếu trước. Tắt check có thể che hồi quy.

## 9. Test parity với Maven Surefire/Failsafe

Khi từ Maven sang Gradle, cần map:

| Maven behavior | Gradle equivalent cần cấu hình |
| --- | --- |
| Surefire unit tests | `test`/`useJUnitPlatform()` |
| Failsafe integration tests | `integrationTest` suite/source set và `check` wiring |
| JUnit includes/excludes | Gradle Test filters/tags |
| Maven `argLine` | Gradle `jvmArgs` và toolchain |
| `systemPropertyVariables` | `systemProperty` |
| Parallel forks/test strategy | `maxParallelForks`/JUnit settings |
| Test reports XML | Gradle Test XML/HTML reports |
| JaCoCo coverage | Gradle JaCoCo plugin/report/verification |
| Test fixtures/resources | Gradle test source sets/fixtures dependencies |

Nếu Maven lifecycle trước kia chạy cả Surefire + Failsafe trên `verify`, Gradle `./gradlew test` có thể chỉ chạy unit tests. Để parity, đặt kiểm thử tích hợp vào `check` hoặc một CI task graph được công nhận, rồi ghi lại số lượng tests chạy.

### 9.1. Test reports cần so theo ngữ nghĩa

JUnit XML thường có timestamp, execution time, hostname và runtime paths. So nguyên file XML byte-for-byte là quá chặt. Parse `tests`, `failures`, `errors`, `skipped`, test case names và CI-tracked coverage. Một số Gradle/test framework versions đổi XML format; normalizing hợp lệ nhưng không được xóa thông tin test missing.

### 9.2. `UP-TO-DATE`/`FROM-CACHE` không chứng minh test đã chạy lại

~~~bash
./gradlew :app:test --rerun-tasks --console=plain
~~~

`--rerun-tasks` buộc task execution thay vì up-to-date/build-cache avoidance cho invocation đó; có thể dùng một lần trong regression testing để bảo đảm tests thực sự được gọi. Nhưng nó không tự tạo tests nếu discovery/classpath sai. `--dry-run` chỉ hiển thị task graph, không thực thi test actions.

## 10. Packaging parity: inventory trước khi hash

Một bản phát hành có thể gồm:

- Java Library JAR: classes + resources + `META-INF/MANIFEST.MF`.
- Application distribution: app JAR + dependency JARs + Unix/Windows launch scripts trong `bin/`.
- Executable/fat JAR (khi có plugin riêng): dependencies được gộp hoặc Spring Boot layout.
- WAR/EAR: web app content, `WEB-INF`, application libraries/metadata.
- ZIP/TAR: config files, docs, executable permissions.
- Published module: POM, Gradle Module Metadata, source/javadoc JARs, signatures/checksums.

**Không giả định `application` plugin tạo ra một fat JAR.** Gradle Application plugin tạo launch scripts/distribution gồm app JAR **và runtime dependencies**. App JAR đơn lẻ không có mọi dependencies trên classpath; gọi `java -jar app.jar` có thể không chạy ngay cả khi `Main-Class` được khai báo.

### 10.1. Những chi tiết cần so

| Chi tiết | Tại sao quan trọng? |
| --- | --- |
| Artifact filename/version/classifier | Scripts và consumer có thể phụ thuộc |
| Manifest: Main-Class/Implementation-Version/etc. | Launch, diagnostics, scanners |
| List classes/resources | Thiếu file gây lỗi runtime |
| Duplicates/exclusions | `META-INF/services`, licensing, loader behavior |
| File order/timestamps/permissions | Reproducibility, executable scripts |
| Dependency JARs trong dist `lib/` | Runtime `ClassNotFoundException` nếu thiếu |
| Start scripts `bin/` | OS compatibility, JAVA_OPTS, main class |
| Resource filtering/env config | Không rò secret, đúng mặc định |
| Compression/ZIP64/TAR handling | Consumer/extractor compatibility |
| Signing/SBOM/provenance | Release trust và reproducibility |
| POM scopes/Gradle metadata | Downstream dependency resolution |

### 10.2. Byte-level drift vs semantic drift

Các Gradle versions khác nhau có thể tạo JAR bytes khác dù entry tree giống nhau, do archive defaults, timestamp rules hoặc manifests. Gradle 9.0+ đặt defaults **reproducible file order = true**, **preserveFileTimestamps = false** cho archives. Nếu chuyển từ Gradle cũ, settings/outputs có thể thay đổi: ghi nhận đây là **thay đổi mặc định đã biết** và quyết định có cần parity byte-for-byte hay chỉ semantic parity.

Để diễn đạt ý đồ rõ ràng qua nhiều Gradle versions, có thể cấu hình:

~~~kotlin
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Đây là fragment yêu cầu import `AbstractArchiveTask` trong Kotlin DSL. **Nó không tự bảo đảm toàn bộ artifacts có SHA giống nhau** nếu compiler/JDK/plugin/script templates/build-info/signing khác. Phải kiểm soát mọi nguồn nondeterminism.

## 11. Lab runnable: dự án Java 17 api + app với test và distribution

Dự án gồm:

~~~text
migration-parity-lab/
├── settings.gradle.kts
├── api/
│   ├── build.gradle.kts
│   └── src/main/java/demo/api/Greeter.java
├── app/
│   ├── build.gradle.kts
│   ├── src/main/java/demo/app/Main.java
│   └── src/test/java/demo/app/GreetingTest.java
├── tools/
│   └── MigrationAudit.java
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

Điều kiện: **JDK 17**, một Gradle Wrapper được tạo từ nguồn đáng tin, Maven Central hoặc mirror được phê duyệt để tải JUnit. Nếu dùng Gradle 9.x, Gradle Daemon cũng phải chạy JVM 17+; nếu dùng Gradle cũ, xem compatibility matrix của version đó.

### 11.1. settings.gradle.kts

~~~kotlin
rootProject.name = "migration-parity-lab"

include(":api", ":app")
~~~

Không cần root `build.gradle.kts` cho lab. Hai subprojects tự khai báo plugins/toolchains/version.

### 11.2. api/build.gradle.kts

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.jvm.toolchain.JavaLanguageVersion

plugins {
    `java-library`
}

group = "demo.migration"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

`java-library` cung cấp `api` và `implementation`, tạo JAR `api-1.0.0.jar` trong `api/build/libs/`.

### 11.3. app/build.gradle.kts

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask
import org.gradle.api.tasks.bundling.Jar
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.jvm.toolchain.JavaLanguageVersion

plugins {
    application
}

group = "demo.migration"
version = "1.0.0"

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

dependencies {
    implementation(project(":api"))

    testImplementation(platform("org.junit:junit-bom:5.10.2"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}

application {
    mainClass.set("demo.app.Main")
}

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}

tasks.named<Jar>("jar") {
    manifest {
        attributes(
            mapOf(
                "Implementation-Title" to "migration-app",
                "Implementation-Version" to project.version.toString()
            )
        )
    }
}
~~~

Đây là build script hoàn chỉnh cho lab. Java plugin được `application` áp tự động. `distZip`/`distTar`/`installDist` được Application/Distribution plugins tạo sẵn. JAR manifest `Implementation-Title` và `Implementation-Version` là một **packaging contract** cụ thể có thể kiểm tra bằng JDK.

**Lưu ý:** Chỉ thiết lập manifest `Implementation-Title/Version`, không khai báo runnable fat JAR hoặc `Main-Class`. Để chạy ứng dụng có dependency `:api`, dùng Gradle `:app:run` hoặc launch scripts trong distribution.

### 11.4. api/src/main/java/demo/api/Greeter.java

~~~java
package demo.api;

public final class Greeter {
    private Greeter() {
    }

    public static String message(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên trống");
        }
        return "Xin chào, " + name.trim() + "!";
    }
}
~~~

Public method `message` là một API contract. Sau migration, output với input `Gradle` và lỗi khi tên trống cần giữ như baseline.

### 11.5. app/src/main/java/demo/app/Main.java

~~~java
package demo.app;

import demo.api.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.message("Gradle"));
    }
}
~~~

### 11.6. app/src/test/java/demo/app/GreetingTest.java

~~~java
package demo.app;

import demo.api.Greeter;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingTest {

    @Test
    void validName() {
        assertEquals(
            "Xin chào, Gradle!",
            Greeter.message("Gradle")
        );
    }

    @Test
    void rejectsBlankName() {
        assertThrows(
            IllegalArgumentException.class,
            () -> Greeter.message("   ")
        );
    }
}
~~~

Có **hai JUnit Jupiter tests**. Khi chạy thành công, Gradle XML report của test class thường nằm tại `app/build/test-results/test/TEST-demo.app.GreetingTest.xml`. Những tests này được cấu hình trong `app`, không phải `api`.

### 11.7. Chạy CLI

Linux/macOS:

~~~bash
./gradlew --version
./gradlew projects --console=plain
./gradlew :api:build :app:test :app:jar :app:distZip :app:installDist --console=plain
./gradlew :app:run --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat projects --console=plain
.\gradlew.bat :api:build :app:test :app:jar :app:distZip :app:installDist --console=plain
.\gradlew.bat :app:run --console=plain
~~~

**Stdout chính xác do Java Main in ra:**

~~~text
Xin chào, Gradle!
~~~

Gradle console còn in task headers/build status, không coi dòng trên là toàn bộ transcript.

Kết quả packaging dự kiến của project lab:

~~~text
api/build/libs/api-1.0.0.jar
app/build/libs/app-1.0.0.jar
app/build/distributions/app-1.0.0.zip
app/build/install/app/bin/app
app/build/install/app/bin/app.bat
app/build/install/app/lib/app-1.0.0.jar
app/build/install/app/lib/api-1.0.0.jar
~~~

Trong Windows dùng batch launcher `app.bat`; trong Linux/macOS dùng shell launcher `app`. Distribution path/root archive naming là convention của Application plugin với project `app` version 1.0.0.

### 11.8. Chạy distribution thay vì JAR lẻ

Linux/macOS:

~~~bash
./app/build/install/app/bin/app
~~~

PowerShell:

~~~powershell
.\app\build\install\app\bin\app.bat
~~~

Expected application stdout vẫn là:

~~~text
Xin chào, Gradle!
~~~

**Không dùng** `java -jar app/build/libs/app-1.0.0.jar` cho lab, vì JAR này không được định nghĩa là fat/executable JAR với dependency classpath. Nếu một migration từ Maven Shade hoặc Spring Boot executable JAR yêu cầu `java -jar`, phải áp đúng packaging plugin/strategy, không cho là Application plugin tự thực hiện.

## 12. Tool Java 17: kiểm tra semantic JAR, tests và ZIP

Để biến việc kiểm tra thành một contract có thể chạy độc lập, tạo file `tools/MigrationAudit.java` dưới root project.

~~~java
import java.nio.file.Path;
import java.util.jar.JarFile;
import java.util.zip.ZipFile;
import java.util.jar.Manifest;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.XMLConstants;
import org.w3c.dom.Element;

public final class MigrationAudit {
    private MigrationAudit() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                "Usage: MigrationAudit app.jar TEST-report.xml dist.zip"
            );
        }

        Path jarPath = Path.of(args[0]);
        Path xmlPath = Path.of(args[1]);
        Path zipPath = Path.of(args[2]);

        try (JarFile jar = new JarFile(jarPath.toFile())) {
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                throw new IllegalStateException("Missing manifest");
            }

            String title = manifest.getMainAttributes()
                    .getValue("Implementation-Title");
            String version = manifest.getMainAttributes()
                    .getValue("Implementation-Version");

            require("migration-app".equals(title), "Wrong title");
            require("1.0.0".equals(version), "Wrong version");
            require(jar.getJarEntry("demo/app/Main.class") != null,
                    "Missing Main.class");
        }
        System.out.println("JAR_OK");

        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newInstance();
        factory.setFeature(
                XMLConstants.FEATURE_SECURE_PROCESSING, true
        );
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl",
                true
        );
        factory.setExpandEntityReferences(false);
        factory.setXIncludeAware(false);

        Element suite = factory.newDocumentBuilder()
                .parse(xmlPath.toFile()).getDocumentElement();

        require("testsuite".equals(suite.getTagName()),
                "Wrong report root");
        require("2".equals(suite.getAttribute("tests")),
                "Expected two tests");
        require("0".equals(suite.getAttribute("failures")),
                "Test failures detected");
        require("0".equals(suite.getAttribute("errors")),
                "Test errors detected");
        require("0".equals(suite.getAttribute("skipped")),
                "Skipped tests detected");
        System.out.println("TESTS_OK");

        try (ZipFile zip = new ZipFile(zipPath.toFile())) {
            require(zip.getEntry("app-1.0.0/bin/app") != null,
                    "Missing Unix launcher");
            require(zip.getEntry("app-1.0.0/bin/app.bat") != null,
                    "Missing Windows launcher");
            require(zip.getEntry("app-1.0.0/lib/app-1.0.0.jar") != null,
                    "Missing application JAR");
            require(zip.getEntry("app-1.0.0/lib/api-1.0.0.jar") != null,
                    "Missing API dependency JAR");
        }
        System.out.println("DIST_OK");
    }

    private static void require(boolean ok, String message) {
        if (!ok) {
            throw new IllegalStateException(message);
        }
    }
}
~~~

Mã chỉ sử dụng **JDK 17 standard APIs**: JarFile, ZipFile và XML parser. Cấu hình parser cấm DOCTYPE để tránh external entity loading nếu report bị thay thế bằng dữ liệu không tin cậy. Nếu artifact/report khác contract, chương trình ném exception và process exit nonzero.

### 12.1. Chạy audit tool

Linux/macOS:

~~~bash
mkdir -p audit-out
javac -encoding UTF-8 --release 17 \
  -d audit-out tools/MigrationAudit.java

java -cp audit-out MigrationAudit \
  app/build/libs/app-1.0.0.jar \
  app/build/test-results/test/TEST-demo.app.GreetingTest.xml \
  app/build/distributions/app-1.0.0.zip
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force audit-out | Out-Null
javac -encoding UTF-8 --release 17 -d audit-out tools\MigrationAudit.java

java -cp audit-out MigrationAudit app\build\libs\app-1.0.0.jar app\build\test-results\test\TEST-demo.app.GreetingTest.xml app\build\distributions\app-1.0.0.zip
~~~

**Stdout chính xác khi cả ba contracts đúng:**

~~~text
JAR_OK
TESTS_OK
DIST_OK
~~~

Đây là output của `MigrationAudit`, không phải toàn bộ output Gradle. Điều kiện trước khi chạy: đã thực thi `:app:test`, `:app:jar`, `:app:distZip` thành công; ZIP entry names đúng với Application plugin default và version 1.0.0 trong lab.

### 12.2. Audit có giới hạn gì?

Audit kiểm tra:
- JAR có expected manifest + Main.class.
- XML report có hai test cases và không fail/error/skip.
- ZIP có hai launcher scripts và hai runtime JARs thiết yếu.

Audit **chưa đủ** cho production: nó không kiểm tra tất cả bytecode public APIs, không thực thi launcher, không đối chiếu toàn bộ transitive dependencies, không kiểm tra CVE/signatures/permissions và không bảo đảm reproducibility. Đây là một **contract test mẫu**, không thay CI đầy đủ. Sau migration thật, mở rộng rules thành manifest/inventory/ABI/API tests cho artifact của tổ chức.

## 13. Cách thu thập evidence trước và sau migration

Dùng **cùng một bộ lệnh** ở mỗi revision/branch, lưu outputs vào thư mục ngoài project. Ví dụ trên Linux/macOS:

~~~bash
mkdir -p ../migration-evidence/before

./gradlew --version \
  > ../migration-evidence/before/versions.txt

./gradlew projects --console=plain \
  > ../migration-evidence/before/projects.txt

./gradlew :app:dependencies \
  --configuration runtimeClasspath \
  --console=plain \
  > ../migration-evidence/before/runtime-deps.txt

./gradlew :app:dependencies \
  --configuration testRuntimeClasspath \
  --console=plain \
  > ../migration-evidence/before/test-runtime-deps.txt

./gradlew :app:test :app:distZip --rerun-tasks --console=plain

jar tf app/build/libs/app-1.0.0.jar \
  > ../migration-evidence/before/jar-entries.txt

cp app/build/test-results/test/TEST-demo.app.GreetingTest.xml \
  ../migration-evidence/before/

sha256sum app/build/libs/app-1.0.0.jar \
  > ../migration-evidence/before/sha256.txt
~~~

**Đây là workflow ví dụ cho Linux/macOS có `sha256sum` và `cp`**. Trên macOS có thể dùng `shasum -a 256` thay `sha256sum`; trên PowerShell dùng `Get-FileHash -Algorithm SHA256`, `Copy-Item` và redirection tương ứng. `jar tf` là JDK CLI, không cần unzip. Để lưu manifest thực tế, dùng JDK `jar xf` trong một thư mục tạm hoặc Java `JarFile`, tránh giải nén vào project root.

Sau đổi build tool/Wrapper/DSL, chạy lại nhưng ghi vào `../migration-evidence/after`. Đừng để cả trước và sau ở `build/` rồi chạy `clean` làm mất baseline.

### 13.1. So sánh theo thứ tự

1. Gradle compatibility/JDK/toolchains.
2. `projects` module graph (đừng so task status logs).
3. Resolved dependencies cho **compile/runtime/test** và plugin classpaths.
4. JUnit XML `tests/failures/errors/skipped`, test names và coverage.
5. `jar tf` entry inventory, JAR manifest, ZIP distribution entries.
6. Run launcher, stdout/exit code/working directory/environment.
7. ABI/API compatibility hoặc consumer integration test.
8. SHA-256 chỉ khi byte reproducibility nằm trong contract.
9. Publishing metadata, release artifact names và signatures.

### 13.2. Hash khác không có nghĩa “bỏ qua”

Khi hash JAR khác:
- So archive entries/ordering/timestamps/compression.
- So `MANIFEST.MF`.
- So class bytecode/target Java version/API signatures.
- Kiểm tra injected build timestamp/git SHA, annotation processor/codegen.
- So `Implementation-Version`, dependency versions, services/resources.
- Nếu vẫn cần bit-for-bit, điều tra compiler patch, OS và Gradle archive defaults.

Không đổi expected hash “để CI xanh” trước khi giải thích nguyên nhân.

## 14. Giữ source/test resource behavior

Các thư mục mặc định:

~~~text
src/main/java
src/main/resources
src/test/java
src/test/resources
~~~

Nếu Maven baseline có custom test resources, filtering hoặc generated sources không nằm trong mặc định, Gradle migration phải mô hình hóa tương ứng.

Các rủi ro:

- `src/main/resources/config.yml` bị bỏ ra khỏi JAR.
- Resource filtering làm thay token line endings/encoding hoặc rò secrets.
- Generated sources không có producer task dependency, clean build fail.
- JUnit fixture file paths phụ thuộc Maven working directory.
- Unicode filenames/UTF-8 trong archive khác do platform default.
- `META-INF/services` bị mất hoặc trùng khi tạo fat JAR.
- Licenses/NOTICE/third-party attributions bị bỏ trong distribution.
- Classifier/thư mục output/custom source set khác.

Với Gradle Java plugin, source set `main`/`test` mặc định đã được nhận. Khi source layout khác, khai báo `sourceSets` và kiểm chứng JAR contents, đừng tạo một IDE-only source folder rồi trông đợi Gradle CI hiểu.

## 15. Packaging: JAR, application distribution và fat JAR khác nhau

| Nhu cầu | Gradle plugin/task | Kỳ vọng |
| --- | --- | --- |
| Thư viện Java | `java-library`, `jar` | JAR chứa classes/resources, dependencies khai báo ở metadata |
| CLI application | `application`, `run`/`installDist`/`distZip` | JAR + runtime libs + launch scripts |
| Fat/uber JAR | Shadow plugin hoặc framework packaging plugin | Dependencies được gom theo strategy |
| Spring Boot executable JAR | Spring Boot plugin `bootJar` | Spring Boot launcher/layout |
| Web application WAR | `war` | WEB-INF/classes/libs, web resources |
| Maven publication | `maven-publish` | POM + artifacts, Gradle Module Metadata |
| Custom distribution | `distribution`/`distributions` | ZIP/TAR hoặc installed image |

**Không thay các kiểu này cho nhau** chỉ vì tất cả đầu ra đều mang đuôi `.jar`/`.zip`. Maven Shade có resource transformer/relocation/service merge semantics; Gradle `application` chỉ tạo classpath-based distribution. Migration cần contract riêng cho main class, relocation, service files và conflict duplicates.

### 15.1. Manifest contract

Manifest thường có:
- `Main-Class` (nếu JAR được dùng trực tiếp bởi Java launcher).
- `Implementation-Title`/`Implementation-Version`.
- `Class-Path` (nếu JAR launcher dựa vào external libs).
- `Multi-Release` khi có multi-release JAR.
- Custom OSGi/JPMS/framework attributes tùy plugin.

Các attributes cần parity nếu consumers/scripts đọc chúng. Nhưng không thêm `Main-Class` vào sample app JAR rồi tuyên bố `java -jar` sẽ chạy khi runtime dependency `api` vẫn nằm ngoài JAR.

### 15.2. Application plugin distribution contract

Với lab:

~~~text
app-1.0.0/
├── bin/
│   ├── app
│   └── app.bat
└── lib/
    ├── app-1.0.0.jar
    └── api-1.0.0.jar
~~~

Đây là layout dự kiến **tối thiểu**. Nếu application có external runtime libraries, `lib` sẽ có thêm JARs. Nếu CI/CD chỉ upload `app-1.0.0.jar` mà trước đó release là một distribution ZIP, triển khai có thể fail vì thiếu `api`.

### 15.3. File permissions và line endings

Distribution Unix launch script cần executable permission khi cài đặt/extract trên target. Windows script có CRLF/encoding semantics riêng. Khi so ZIP/TAR qua OS và Gradle versions, kiểm tra:
- Script executable bit/permissions.
- Newline/charset, shebang, executable path.
- Runtime libs và relative classpath.
- License files được ship.
- SHA hash nếu bắt buộc, nhưng ưu tiên chạy thử launcher thật trên môi trường mục tiêu.

## 16. Publishing parity và downstream consumers

Nếu build cũ publish Maven artifact, sau migration cần bảo đảm:

- `groupId`, `artifactId`, `version` và classifiers đúng.
- POM dependencies/scopes/optional/exclusions không bị drift.
- Gradle Module Metadata mô tả variants/capabilities phù hợp.
- Sources/Javadoc artifacts được publish nếu consumer kỳ vọng.
- Signing/checksums/metadata có chính sách đáng tin.
- Release repository URL/permissions tương đương.
- Không publish thử lên production repository khi mới so parity.

### 16.1. Ví dụ Java library maven-publish

**Mảnh build.gradle.kts riêng cho thư viện có `java-library` và `maven-publish` plugins:**

~~~kotlin
publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
            groupId = "demo.migration"
            artifactId = "api"
            version = "1.0.0"
        }
    }
}
~~~

Cần plugin `maven-publish`, Kotlin DSL type imports/accessors phù hợp. Đây là fragment để giải thích, **không thuộc hai build scripts lab** ở phần 11 nếu chưa apply plugin. `from(components["java"])` publish Java software component, gồm variant/dependency metadata phù hợp; không chỉ `artifact(tasks.jar)` rồi quên dependency mapping.

### 16.2. Maven POM và Gradle metadata có khác nhau

Gradle Module Metadata biểu diễn richer variants, capabilities và rich constraints; Maven POM chỉ biểu đạt một phần semantics. Khi migrate từ Maven sang Gradle publishing, test consumer bằng **cả Gradle và Maven** nếu tổ chức có cả hai. Một consumer Maven không đọc các Gradle-only constraints/variants như consumer Gradle.

Khi dynamic versions/lockfiles cần publish resolved dependency versions, dùng `versionMapping` đúng theo documentation thay vì giả định POM sẽ tự phản ánh tất cả conflict resolution decisions.

### 16.3. Consumer smoke test

Tạo một project consumer độc lập bằng Maven hoặc Gradle, resolve artifact từ **staging/local test repository** và chạy một Java compile/integration test. Điều này phát hiện một thư viện self-compile nhưng publish thiếu transitive API dependency.

## 17. Migration từ Groovy DSL sang Kotlin DSL

Đổi `build.gradle` sang `build.gradle.kts` có thể thay:
- Evaluation timing và type-safe accessors.
- Lazy vs eager configuration APIs.
- String interpolation/assignment/provider syntax.
- Plugin application order, extension names.
- Dependency declarations, configurations, task types.
- Custom task closures, inputs/outputs.
- Task realization và implicit dependencies.

Ví dụ:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.example:public-api:1.2'
    implementation 'org.example:internal:3.4'
}
~~~

và Kotlin DSL:

~~~kotlin
plugins {
    `java-library`
}

dependencies {
    api("org.example:public-api:1.2")
    implementation("org.example:internal:3.4")
}
~~~

Đây là **mảnh minh họa với artifact giả**, không phải runnable project; điều quan trọng là **same dependency scope**, không phải cùng chữ ký DSL. Nếu thay `api` thành `implementation` trong migration vì auto-completion, consumer classpath có thể đổi.

### 17.1. Kiểm tra semantics hơn syntax

Đừng chỉ xem Gradle files không báo lỗi. Chạy `dependencies`/`dependencyInsight`, các tests và packaging gates trước/sau. Nếu logic cũ dùng `afterEvaluate`/`allprojects`/`project.afterEvaluate`, refactor sang lazy providers có thể đúng hơn nhưng cần chứng minh task outputs/variants không đổi.

## 18. Migration từ Maven sang Gradle: lifecycle mapping

Một pipeline Maven có thể:

~~~bash
mvn -B clean verify
mvn -B dependency:tree
mvn -B package
~~~

Lệnh tương ứng **mang ý nghĩa gần** trong Gradle:

~~~bash
./gradlew clean check assemble
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:distZip
~~~

**Không phải mapping tuyệt đối**: Maven `verify` có thể chạy Surefire, Failsafe, plugins report, shading và custom executions; Gradle `check assemble` chỉ chạy những tasks thực sự được wiring vào graph. Giữ behavior nghĩa là **liệt kê từng Maven plugin execution** và thay bằng Gradle tasks/plugins tương đương.

### 18.1. Maven BOM, profiles và property filtering

- Maven BOM imports phải mapping sang Gradle `platform`/constraints có kiểm chứng.
- Maven profiles theo JDK/OS/property cần được phân tích; Gradle có property-based configuration nhưng không tự hoạt động giống Maven profile.
- Maven resource filtering có token syntax/encoding khác Gradle `processResources`; test dữ liệu output chứ không chỉ xem file tồn tại.
- Maven `maven-surefire-plugin` includes/excludes/forking khác Gradle `Test` defaults.
- Maven Shade relocation/service transformers khác Gradle Application distribution.

Đừng di chuyển cả `pom.xml` rồi xóa ngay nếu consumers/tools vẫn đọc nó; xác định migration scope và release timeline.

## 19. Nâng Gradle 8.x lên 9.x: ba vùng dễ gây hồi quy

**(A) Runtime/JDK và plugin compatibility.**

Gradle 9 yêu cầu Gradle Daemon JVM 17+, dù Java toolchains vẫn cho phép target Java versions khác. Một plugin dùng Gradle internal APIs hoặc API đã bị loại có thể fail. Đọc upgrade guide, pin plugin versions phù hợp trước khi đổi Wrapper.

**(B) Test discovery/conventions.**

Như đã nêu ở phần 8, custom `Test` task không gán classpath/test classes tường minh có thể âm thầm không chạy. Built-in `test` kiểm tra chặt hơn khi không discover tests. **Đây là lý do phải so test count** chứ không chỉ exit code.

**(C) Archive/publishing defaults.**

Gradle 9 có reproducible archive defaults và thay đổi một số task/artifact wiring. Những `assemble`/`archives` conventions của plugins cũ có thể không giống mới; Jar/War/Ear/signing metadata cũng cần rà soát. Cần so task graph, archive entries, publish artifacts và consumer test.

### 19.1. Bước upgrade Wrapper

Theo docs, nên xem deprecation warnings trước:

~~~bash
./gradlew help --warning-mode=all --console=plain
~~~

Sau đó đọc release/upgrade notes theo từng major. Với một **phiên bản đích đã được đội ngũ phê duyệt**, dùng:

~~~bash
./gradlew wrapper --gradle-version 9.9.0
./gradlew wrapper --gradle-version 9.9.0
./gradlew --version
~~~

`9.9.0` ở đây là một **phiên bản cụ thể được dùng làm ví dụ từ tài liệu hiện hành**, không phải lời khuyên tự động nâng mọi repository lên version đó. Wrapper version phải tương thích plugins/JDK/tools trong dự án. Theo docs, chạy wrapper task **hai lần** có thể cần để cập nhật cả properties lẫn Wrapper JAR/scripts; commit và review changes. Không sửa `distributionUrl` sang server lạ hoặc bỏ kiểm tra `distributionSha256Sum`.

### 19.2. Thay đổi Gradle version không phải cùng lúc đổi Java target

Khi nâng Gradle Daemon từ JDK 11 sang JDK 17 để hỗ trợ Gradle 9, giữ source/test Java toolchain target như contract đã thống nhất. Nếu đang target Java 11, vẫn có thể dùng toolchain Java 11 cho compilation trong một số setup mà Gradle runtime cần 17; không dùng `sourceCompatibility` tình cờ từ JVM mới.

## 20. Test/report contract: lỗi CI mà `BUILD SUCCESSFUL` không bắt được

Một số thay đổi có thể khiến:
- Integration tests không còn được wiring vào `check`.
- JUnit4 tests bị mất khi chuyển sang JUnit Platform mà thiếu Vintage.
- TestNG/JUnit Jupiter versions tự thay khi dùng unpinned JVM Test Suite defaults.
- Gradle custom Test task chạy `NO-SOURCE` hoặc zero tests.
- Skipped tests tăng từ 0 lên 40 mà pipeline vẫn xanh.
- Coverage gate bị vô hiệu, XML reports đổi đường dẫn.
- Test rerun vô tình dùng cache cũ, không thực thi test action trong migration run.
- Tests pass trên một JVM nhưng fail với Java toolchain được CI dùng.

**Gate mẫu:** Không chấp nhận PR migration khi test count thấp hơn baseline mà không có approval chi tiết; cũng không chỉ dựa vào số lượng: so danh sách test case names, skip reasons và coverage metrics.

### 20.1. Gradle XML report

Với Java plugin và task `test`:

~~~text
app/build/test-results/test/TEST-demo.app.GreetingTest.xml
app/build/reports/tests/test/index.html
~~~

được dùng để điều tra. Trong lab, `MigrationAudit` bắt buộc đúng 2 tests, không failures/errors/skips. Với dự án thật, baseline có thể là hàng nghìn cases, cần CI tool normalize XML; đừng hard-code “2” cho mọi project.

### 20.2. `--continue` và aggregate failures

`--continue` cho Gradle cố chạy các tasks không phụ thuộc những task đã fail; nó không tự biến failures thành successes. Trong migration, có thể dùng để thu nhiều failure cases nhưng quality gate cuối vẫn phải yêu cầu tất cả tasks cần thiết PASS.

## 21. ABI/API compatibility của Java library

Nếu `api` module xuất public types/methods, test runtime output không phát hiện hết breaking API. Cần xét:

- Class/package/module names.
- Public/protected methods, parameter/return types, checked exceptions.
- Binary-incompatible signature changes.
- Java bytecode target/release và JPMS module-info.
- Dependencies xuất hiện trong public API.
- Reflection, annotations, service loader providers.
- Serialization format/network contract nếu consumer dựa vào.

Công cụ `javap -public` có thể hỗ trợ quan sát public API:

~~~bash
javap -classpath api/build/libs/api-1.0.0.jar \
  -public demo.api.Greeter
~~~

Output formatting có thể thay theo JDK; phân tích semantics, không so raw bytes. Với hệ sinh thái cần strict binary compatibility, cân nhắc `japicmp`/`Revapi` hoặc API baseline plugin, nhưng kiểm tra plugin/version phù hợp; không khẳng định Gradle tự có ABI gate cho mọi thư viện.

### 21.1. Smoke test consumer

Một consumer Java 17 độc lập compile:

~~~java
import demo.api.Greeter;

public final class Consumer {
    public static void main(String[] args) {
        System.out.println(Greeter.message("Consumer"));
    }
}
~~~

Nếu file `Consumer.java` nằm ở thư mục test riêng, biên dịch:

~~~bash
javac --release 17 -cp api/build/libs/api-1.0.0.jar Consumer.java
java -cp ".:api/build/libs/api-1.0.0.jar" Consumer
~~~

Linux/macOS output:

~~~text
Xin chào, Consumer!
~~~

Trên Windows classpath separator là semicolon `;` thay cho colon `:`:

~~~powershell
javac --release 17 -cp api\build\libs\api-1.0.0.jar Consumer.java
java -cp ".;api\build\libs\api-1.0.0.jar" Consumer
~~~

**Đây là một consumer smoke test bổ sung có thể chạy** nếu file `Consumer.java` được tạo như snippet và api JAR đã build; nó không thay binary ABI analysis trên toàn public API.

## 22. Classpath ordering, resources và duplicate classes

Maven, Gradle và IDE classpaths có thể khác thứ tự module/JAR. Phần lớn app không nên dựa vào thứ tự, nhưng thực tế có thể có:
- Duplicate `META-INF/services` files.
- Hai JARs cùng class name.
- Logging implementations cạnh tranh.
- XML parsers/service providers.
- Config resource cùng tên nhiều JAR.
- Signed JARs không được phép unpack/re-sign tùy tiện.

Khi đổi từ Maven Shade sang Gradle Shadow hoặc Application distribution, kiểm tra ServiceLoader plugins, thư viện logging và resource transformers cụ thể. Không chỉ nhìn JAR inventory và bỏ qua nội dung `META-INF/services`.

### 22.1. Dependency exclusion

Ví dụ fragment:

~~~kotlin
implementation("org.example:lib:1.0") {
    exclude(group = "org.example", module = "legacy-logger")
}
~~~

Đây là artifact tọa độ giả để minh họa exclusion. Loại một module có thể cần áp ở đúng dependency edge; một exclude rule không nhất thiết ngăn module được kéo vào qua cạnh khác. Kiểm tra runtimeClasspath thực tế sau migration.

## 23. Kích hoạt parallelism/cache sau khi parity đã ổn

`--parallel`, Build Cache và Configuration Cache rất hữu ích, nhưng migration cần tránh nhầm lỗi do biến động build engine/outputs với lỗi do dependencies hoặc packaging.

Lộ trình:

1. So parity ở một baseline invocation đáng tin.
2. Bật Gradle Build Cache/Configuration Cache khi build logic tương thích.
3. Chạy regression tests trong môi trường tương tự CI.
4. Quan sát `UP-TO-DATE`, `FROM-CACHE` và Configuration Cache reuse **riêng biệt**.
5. Với nghi ngờ stale artifact, chạy `--rerun-tasks` cho một lần QA có kiểm soát.
6. Tránh xóa cache hoặc thêm `clean` vô điều kiện làm mất khả năng so performance.

Một task được đánh dấu `UP-TO-DATE` **không chứng minh** thay đổi JVM/plugin đã được kiểm tra qua task action ở invocation đó; cần một regression run thực sự execute tests/packaging khi thích hợp.

## 24. CI matrix cho migration

Một CI gate nên chạy matrix theo phạm vi dự án:

| Nhóm kiểm tra | Environment | Gate |
| --- | --- | --- |
| Dependency graph | Linux JDK17, pinned Wrapper | Lockfile/selected variants đúng |
| Unit tests | Linux JDK17 | Test cases/count/results/coverage đúng |
| Integration tests | Service deps/staging fixtures | External contract vẫn đạt |
| Package JAR/ZIP | Linux JDK17 | Audit Jar/manifest/distribution |
| Windows launcher | Windows JDK17 | Batch script chạy đúng |
| Other supported JDK | Java 21 Daemon + Java17 toolchain nếu supported | Không đổi bytecode target |
| Consumer Maven/Gradle | Clean resolver/staging publication | API/artifact metadata đúng |
| Reproducibility | Hai clean controlled builds | SHA match nếu policy yêu cầu |
| Supply chain | Verified dependencies/Wrapper | Không tắt verification |
| Release smoke | Non-production environment | Package khởi động, health checks |

**Không cần chạy mọi matrix cell cho một lab nhỏ**, nhưng production migration phải chọn đại diện theo supported platforms và deployment contract.

### 24.1. Bảo vệ metadata và secrets

- Không cache nguyên `~/.gradle` chứa credentials như public artifact.
- Không cho PR từ fork có privileged publishing tokens.
- Không publish candidate artifact đè release version bất biến.
- Không tự chấp nhận verification SHA changes.
- Ký artifact đúng policy và đối chiếu key/algorithm trong release output.
- Giữ nguồn provenance của baseline và candidate artifacts.
- Chỉ lưu logs có thông tin cần thiết, redact private tokens.

## 25. Rollback và phased adoption

Quy trình an toàn khi migrate một monorepo:

1. **Đóng băng baseline**: giữ dependency lock/verification, report tests và package.
2. **Lên migration branch**: sửa build files, không đổi source nghiệp vụ nếu không cần.
3. **Chọn một nhóm module**: Java library trước, application/distribution sau.
4. **Bật parity gates**: dependency, test, packaging.
5. **Giải thích mọi diff**: approved drift vs regression.
6. **Đồng bộ CI/IDE**: update Wrapper/plugin/JDK cho dev runners.
7. **Staging publish**: thử consumer smoke tests.
8. **Canary release**: chạy artifact candidate trong nonprod.
9. **Promote hoặc rollback**: giữ release coordinates/versions bất biến, rollback theo artifact/commit đã duyệt.
10. **Sau migration**: ghi deprecation remediation và performance optimizations vào việc riêng.

Nếu dependency graph drift, **dừng ở dependency gate** trước khi chữa bằng exclusions cưỡng bức; nếu tests thiếu, khôi phục test discovery/suite wiring trước khi chỉnh packaging.

## 26. Bảng troubleshooting

| Dấu hiệu | Nguyên nhân có thể | Điều tra/sửa |
| --- | --- | --- |
| Build success nhưng ít tests hơn | Custom Test task không có classpath, excludes, engine | Đếm XML testcases, gán classpath/testClassesDirs |
| `test NO-SOURCE` ngoài ý muốn | Sai source sets/path hoặc chưa tạo tests | Kiểm tra test sources, sourceSets, `useJUnitPlatform` |
| JUnit4 tests mất sau upgrade | Thiếu Vintage engine hoặc test mapping | Chọn engine/runner tương thích hoặc migrate tests |
| Maven verify chạy integration tests, Gradle check không | Chưa wire integrationTest suite vào check | Tạo suite/task và task dependencies |
| Same declared deps nhưng khác runtime JARs | BOM/constraint/conflict/variant | `dependencies`, `dependencyInsight`, locks |
| Runtime `NoClassDefFoundError` | Dist thiếu runtime library | Kiểm tra `runtimeClasspath` và `distZip lib/` |
| Consumer compile fail | `api` bị chuyển sang `implementation` | Java Library API variant/POM |
| JAR tên khác baseline | Project name/version/archiveBaseName | So artifact filename contract |
| `java -jar` fail | App JAR không phải fat/executable | Dùng Distribution launcher hoặc đúng plugin |
| Manifest thiếu Main-Class/Implementation-Version | Packaging config thay | Kiểm tra `MANIFEST.MF` |
| Hash JAR khác, runtime đúng | Timestamps/order/toolchain/compiler/manifest | Archive metadata + content diff |
| ZIP thiếu Unix executable flag | Packaging permissions/tool/version | Kiểm tra extraction trên Linux |
| Maven consumer nhận sai scope | POM mapping khác Gradle variants | `maven-publish` components/`versionMapping` |
| Gradle 9 daemon fail | JDK dưới 17 | Chọn compatible Gradle JVM |
| Plugin apply fail | Plugin version dùng removed API | Upgrade plugin/release notes |
| Locked version conflict | Declared requirement đổi, lock cũ | Review lock update, không tắt locking |
| Verification mismatch | Binary/hash khác | Đối chiếu provenance, không auto-approve |
| Build Cache hit nhưng migration tests chưa chạy | `UP-TO-DATE`/`FROM-CACHE` | `--rerun-tasks` và reports |
| Staging package đúng, production fail | Env/config/permissions/launcher khác | Deployment smoke test đúng platform |
| DSL conversion pass nhưng missing task | Task registration/wiring changed | `tasks --all`, `--dry-run` + actual execution |
| Distribution mới chứa thêm license/config | Intentional artifact change | Approval & consumer impact assessment |

## 27. Bài tập tự thực hành

**Bài 1 — Snapshot dependency graph:** Chạy `:app:dependencies` cho compile/runtime/testRuntime. Xác nhận `:api` có mặt ở runtime, JUnit chỉ thuộc test. Giải thích vì sao chỉ nhìn `implementation(...)` text không đủ.

**Bài 2 — Kiểm tra tests không bị mất:** Chạy `:app:test --rerun-tasks`, kiểm tra hai JUnit test cases/0 failures. Sử dụng `MigrationAudit` để xác minh XML và phát hiện nếu có người disable một test.

**Bài 3 — Kiểm tra manifest:** Thay `Implementation-Version` trong app build script thành `2.0.0` nhưng giữ audit kỳ vọng `1.0.0`. Build package và chạy audit, quan sát lỗi `Wrong version`. Đây là một **thử nghiệm lỗi trong sandbox**, không áp vào release thật.

**Bài 4 — Kiểm tra missing runtime lib:** Tạo bản sao dist ZIP đã bỏ `lib/api-1.0.0.jar` bằng công cụ phù hợp, chạy audit trên ZIP đó. Kỳ vọng fail với `Missing API dependency JAR`.

**Bài 5 — So CLI vs distribution:** Chạy `:app:run` và `installDist/bin/app`, cùng in `Xin chào, Gradle!`. Nếu khác, so JVM args/classpath/working directory.

**Bài 6 — Thử Gradle upgrade:** Trên branch test, upgrade Wrapper khi plugin/JDK compatibility cho phép, chạy cùng baseline suite và audit tool. So resolved dependencies, tests, JAR inventory, distribution entries. Ghi approved differences.

**Bài 7 — Maven migration mapping:** Với một Maven `pom.xml` giả định gồm compile/provided/runtime/test scopes và Failsafe integration tests, lập bảng Gradle configurations/Test suites tương ứng. Tránh map Maven `verify` thành `gradle test` duy nhất nếu Failsafe từng chạy.

**Bài 8 — Byte reproducibility:** Build cùng commit trong hai clean environments kiểm soát JDK/locale/Gradle/inputs, so SHA. Nếu khác, phân tích archive metadata và embedded build-info; không chỉ tăng cache key.

## 28. Câu hỏi ôn tập và đáp án

**1.** Migration `BUILD SUCCESSFUL` đã chứng minh giữ nguyên behavior? — **Chưa.** Phải kiểm tra dependencies, actual tests, packaging và runtime.

**2.** Declared dependency text có bằng resolved dependency graph? — Không, còn conflict/BOM/constraints/variants.

**3.** `api` và `implementation` có thể thay thế tùy ý? — Không, ảnh hưởng consumer compile classpath.

**4.** Version catalog có khóa transitive dependency graph? — Không, nó chủ yếu lưu requested versions/aliases; dùng locking/verification khi cần.

**5.** `platform` có tự kéo mọi BOM dependency vào runtime? — Không, nó đưa constraints để align dependencies được yêu cầu.

**6.** Vì sao custom Test task ở Gradle 9 đáng kiểm tra? — Nếu từng dựa vào default test classes/classpath conventions, nó có thể ngừng chạy tests.

**7.** `useJUnitPlatform()` có tự thêm engine/library? — Không, cần test dependencies phù hợp.

**8.** `--dry-run` có chạy JUnit tests? — Không, chỉ mô phỏng graph.

**9.** Maven Failsafe tự tương đương Gradle test? — Không, cần integration suite/task wiring.

**10.** JUnit XML nên so raw bytes? — Không, normalize semantic test names/counts/failures/skips/time fields.

**11.** Application plugin có tạo fat JAR mặc định? — Không, tạo application distribution + launch scripts và runtime libs.

**12.** `java -jar app.jar` thất bại có nghĩa `installDist` sai? — Không nhất thiết; app JAR đơn lẻ không chứa external dependencies.

**13.** Vì sao distribution lib phải có api JAR? — Main phụ thuộc `demo.api.Greeter` ở runtime.

**14.** `MigrationAudit` trong lab kiểm tra gì? — Manifest/JAR entry, 2 JUnit tests/0 errors, ZIP launcher và JARs.

**15.** Gradle 9 default archive timestamps/order ra sao? — Preserve timestamps false, reproducible order true cho archive tasks mặc định được mô tả trong docs.

**16.** Hash JAR khác có luôn là functional regression? — Không, nhưng cần điều tra nguồn khác biệt; byte parity có thể là contract bắt buộc.

**17.** Gradle 9 Daemon JVM yêu cầu gì? — JVM 17+.

**18.** Dependency locking có đóng băng SNAPSHOT bytes? — Không, locking chủ yếu chốt resolved versions; changing modules vẫn nguy hiểm.

**19.** POM có biểu diễn đầy đủ Gradle Module Metadata capabilities/variants? — Không, metadata semantics phong phú hơn.

**20.** Nên publish thử trực tiếp lên production coordinates? — Không, dùng staging/local repository và consumer smoke test.

**21.** Khi binary compare fail nhưng semantic compare pass thì làm gì? — Phân loại accepted vs required differences, kiểm tra compiler/archives/toolchain trước khi approve.

**22.** Muốn giữ module graph từ Maven multi-module, phải làm gì? — Định nghĩa Gradle Settings includes/included builds đúng và kiểm tra projects task.

**23.** Thay Groovy sang Kotlin DSL có bảo đảm semantics giữ nguyên? — Không, cần kiểm tra providers/task wiring/dependencies/tests/artifacts.

**24.** Test tasks có `UP-TO-DATE` là test đã chạy trong migration job? — Không, task có thể được bỏ qua. Dùng QA invocation/`--rerun-tasks` khi muốn thực thi thật.

**25.** Khi library self-build pass có đủ chứng minh consumer tương thích? — Không, cần ABI/API và downstream consumer tests.

## 29. Checklist chất lượng trước khi merge migration

- [ ] Baseline commit/Wrapper/JDK/plugin versions được ghi lại.
- [ ] Scope migration tách khỏi những thay đổi nghiệp vụ không cần thiết.
- [ ] Cùng modules, source sets và task graph dự kiến.
- [ ] Compile/runtime/test resolved dependency sets/versions được đối chiếu.
- [ ] BOM/platform/constraints/exclusions/variant behavior được xác minh.
- [ ] Dependency locking và verification metadata giữ nguyên hoặc có approval diff.
- [ ] JUnit/TestNG/Spock engines và suite selection đúng.
- [ ] Test case names/counts và failures/skips so với baseline.
- [ ] Integration/performance/contract tests được wiring vào CI.
- [ ] Custom Test tasks có testClassesDirs/classpath tường minh nếu cần.
- [ ] Toolchain, JVM args, system properties, resources và working directory đúng.
- [ ] JAR classes/resources/manifest và bytecode target đúng.
- [ ] Application distribution chứa runtime libs và launcher scripts.
- [ ] Fat JAR/WAR/EAR/shading contracts được kiểm tra riêng nếu có.
- [ ] Artifact coordinates/version/POM/Gradle metadata và classifiers đúng.
- [ ] Consumer smoke test từ staging publication pass.
- [ ] Archive reproducibility settings/permission/timestamps được hiểu.
- [ ] Hash differences được giải thích và phê duyệt theo policy.
- [ ] Dependency/Wrapper/signing integrity không bị hạ chuẩn.
- [ ] CI chạy được trong clean environment không dựa vào developer local cache.
- [ ] Có rollback commit/artifact và owner của approved differences.
- [ ] Release deploy smoke tests/monitoring có kế hoạch cụ thể.

## 30. Tài liệu chính thức

1. Gradle — Upgrading within Gradle 9.x.y: https://docs.gradle.org/current/userguide/upgrading_version_9.html
2. Gradle — Upgrading to Gradle 9.0.0: https://docs.gradle.org/current/userguide/upgrading_major_version_9.html
3. Gradle — Compatibility Matrix: https://docs.gradle.org/current/userguide/compatibility.html
4. Gradle — Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
5. Gradle — Dependency Management: https://docs.gradle.org/current/userguide/dependency_management.html
6. Gradle — Declaring Dependencies: https://docs.gradle.org/current/userguide/declaring_dependencies.html
7. Gradle — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
8. Gradle — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
9. Gradle — Dependency Constraints: https://docs.gradle.org/current/userguide/dependency_constraints.html
10. Gradle — Platform/BOMs: https://docs.gradle.org/current/userguide/platforms.html
11. Gradle — JVM Test Suite Plugin: https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html
12. Gradle — Java Testing: https://docs.gradle.org/current/userguide/java_testing.html
13. Gradle — Java Library Plugin: https://docs.gradle.org/current/userguide/java_library_plugin.html
14. Gradle — Application Plugin: https://docs.gradle.org/current/userguide/application_plugin.html
15. Gradle — Distribution Plugin: https://docs.gradle.org/current/userguide/distribution_plugin.html
16. Gradle — AbstractArchiveTask API: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html
17. Gradle — Best Security Practices/Reproducible Builds: https://docs.gradle.org/current/userguide/best_practices_security.html
18. Gradle — Maven Publish Plugin: https://docs.gradle.org/current/userguide/maven_plugin.html
19. Gradle — Gradle Module Metadata: https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html
20. Gradle — Publishing Setup: https://docs.gradle.org/current/userguide/publishing_setup.html
21. Gradle — Multi-Project Builds: https://docs.gradle.org/current/userguide/multi_project_builds.html
22. Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
23. Gradle — Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache.html

**Lưu ý phiên bản:** URLs `/current/` mô tả Gradle hiện hành và có thể khác project Wrapper. Ví dụ `9.9.0` là version cụ thể trong tài liệu hiện tại, không phải yêu cầu nâng tất cả dự án lên bản đó. Trước migration cần đọc release notes/compatibility matrix của **đúng source và target versions**, plugin ecosystem và JDK policy.

**Kết luận:** Giữ nguyên hành vi dependency, kiểm thử và đóng gói khi migration là một công việc **kiểm chứng hợp đồng**, không chỉ dịch DSL hay chạy build thành công. Hãy giữ baseline, đối chiếu resolved classpaths, bảo đảm tests thật sự được discover/chạy, kiểm tra JAR/ZIP/POM/runtime bằng contract tests, kiểm soát mọi drift, sau đó mới chuyển CI/release.