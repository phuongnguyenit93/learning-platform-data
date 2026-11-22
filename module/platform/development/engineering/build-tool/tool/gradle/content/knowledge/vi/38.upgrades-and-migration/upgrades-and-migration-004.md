# Nâng từng bước và kiểm tra Wrapper, plugin, build logic trong Gradle

## 1. Mục tiêu: nâng Gradle có kiểm soát, không chỉ đổi số phiên bản

Một dự án Java có thể build ổn định nhiều năm với một phiên bản Gradle cụ thể, nhưng việc giữ nguyên mãi sẽ bỏ lỡ bản sửa lỗi, cập nhật bảo mật, hỗ trợ Java mới, cải thiện hiệu năng và API build mới. Ngược lại, sửa `gradle-wrapper.properties` từ phiên bản cũ sang bản mới rồi chạy `build` có thể làm thất bại cả chuỗi:

- JVM hiện dùng chạy Gradle không còn đáp ứng yêu cầu của Gradle mới.
- Kotlin/Groovy DSL đang gọi API đã bị deprecate và bị loại bỏ.
- Plugin bên ngoài dùng Gradle internal APIs hoặc đòi Gradle/JDK version khác.
- `buildSrc`, included build `build-logic` hoặc convention plugin tự viết không biên dịch.
- Custom tasks phụ thuộc hành vi configuration/lazy API cũ.
- Test discovery thay đổi, test task `NO-SOURCE` hoặc số tests thực chạy giảm.
- Build Cache/Configuration Cache che lỗi stale inputs hoặc incompatibility.
- IDE dùng Gradle JVM khác CLI/CI.
- CI dùng action/runner image không còn phù hợp.
- Task `jar`/publishing tạo artifact khác hợp đồng ban đầu.

Bài này hướng dẫn **nâng từng bước**: ghi nhận baseline, khảo sát compatibility, sửa deprecations và plugins, nâng Wrapper theo mốc nhỏ, kiểm tra cả build logic lẫn ứng dụng, xác minh artifacts/CI, rồi chốt hoặc rollback. Mỗi bước có **kết quả chấp nhận được** chứ không dựa trên giả định “build xanh là đã migrate xong”.

### 1.1. Phạm vi phải kiểm tra

| Thành phần | Điều cần xác minh | Ví dụ |
| --- | --- | --- |
| **Gradle Wrapper** | Distribution version, scripts, JAR, checksum | `gradle/wrapper/gradle-wrapper.properties` |
| **JVM chạy Gradle** | Java runtime được phiên bản Gradle hỗ trợ | `./gradlew --version` |
| **Java toolchain** | Version compile/test của ứng dụng | `java { toolchain { ... } }` |
| **Core plugins** | Plugin API/behavior mới | `java`, `application`, `maven-publish` |
| **Third-party plugins** | Compatibility/version và transitive classpath | Kotlin, Android, Shadow, analysis plugins |
| **Build scripts** | Kotlin/Groovy DSL, removed APIs, warnings | `build.gradle.kts`/`settings.gradle.kts` |
| **Build logic nội bộ** | `buildSrc`, included builds, convention/binary plugins | `build-logic`, `Plugin<Project>` |
| **Task model** | Lazy registration, Provider inputs, test behavior | `tasks.register`, `@Input`, `@OutputFile` |
| **Dependency resolution** | Repository, locks, metadata, plugin markers | `pluginManagement`, `libs.versions.toml` |
| **CI/IDE** | Thực sự chạy đúng Wrapper/JDK/toolchain | Gradle sync, release workflows |
| **Artifacts** | Nội dung, entrypoint, publication, hash/behavior | JAR, ZIP, container image |

**Không nên** đồng thời nâng Gradle, Java language level, Kotlin Gradle Plugin, Android Gradle Plugin, thay DSL và viết lại build logic trong một commit lớn trừ khi bắt buộc. Các thay đổi này có compatibility dependencies, nhưng nên chia thành những bước/PR có thể kiểm tra và rollback.

## 2. Hiểu các phiên bản khác nhau trong một Gradle build

Một project có thể có nhiều version “Java” và “Gradle” hoạt động cùng lúc.

```text
Developer / CI
    |
    +-- Gradle Wrapper (distribution 8.x hoặc 9.x)
    |       |
    |       +-- Gradle Daemon JVM (ví dụ JDK 17)
    |       |
    |       +-- build.gradle.kts / Kotlin DSL embedded runtime
    |       |
    |       +-- third-party Gradle plugins
    |       |
    |       +-- build-logic / buildSrc code (chạy trên Gradle JVM)
    |
    +-- Java Toolchains
            |
            +-- javac target của ứng dụng
            +-- Test JVM khi plugin hỗ trợ cấu hình
            +-- Javadoc và một số tool tasks
```

### 2.1. Gradle runtime JVM khác toolchain

`./gradlew --version` cho biết Gradle version và runtime JVM liên quan. `java.toolchain.languageVersion.set(JavaLanguageVersion.of(17))` chọn Java compiler/tool cho Java tasks, **không tự thay đổi JVM chạy Gradle Daemon**.

Ví dụ:

- Gradle 9.x cần JVM **17 hoặc mới hơn** để chạy Gradle.
- Một Java application vẫn có thể target Java cũ qua Java Toolchains nếu Gradle và compiler/toolchain hỗ trợ.
- Một binary Gradle plugin được build bằng Java 21 bytecode có thể không load được trên Gradle Daemon Java 17 dù ứng dụng dùng toolchain Java 21.

Phải xác minh **ba thứ riêng**: Gradle runtime, plugin/build-logic bytecode target và application Java toolchain.

### 2.2. Mốc Gradle 8 → 9 cần đặc biệt chú ý

Theo hướng dẫn chính thức của Gradle 9.0:

- Gradle 9.0.0 yêu cầu **JVM 17+** cho Gradle Daemon.
- Kotlin DSL/embedded Kotlin chuyển sang Kotlin 2.2 và ngôn ngữ Kotlin 2.2, có thể ảnh hưởng build logic viết Kotlin.
- Groovy runtime được nâng lên Groovy 4.
- Kotlin Gradle Plugin tối thiểu được Gradle 9.0 hỗ trợ là **2.0.0**.
- Android Gradle Plugin tối thiểu được Gradle 9.0 hỗ trợ là **8.4.0**.
- Một số API cũ như `Project.exec` / `Project.javaexec` không còn trong Gradle 9; phải chuyển sang `ExecOperations` hoặc task types phù hợp.
- Một số hành vi liên quan test tasks, plugin validation và Kotlin DSL đã thay đổi, cần đối chiếu migration guide.
- Plugin Kotlin DSL được build bằng Gradle 9.x có giới hạn compatibility ngược do Kotlin metadata; nếu xuất bản cho người dùng Gradle cũ, phải kiểm tra riêng matrix.

**Đừng suy diễn** rằng một plugin chạy trên Gradle 8.14.6 chắc chắn chạy trên 9.0.0. Các giới hạn trên là mốc của Gradle 9.0; với Gradle 9.x về sau, phải đọc thêm release notes và compatibility matrix của đúng target.

### 2.3. Ví dụ phiên bản có căn cứ

Ở thời điểm biên soạn (09/11/2026), tài liệu Gradle chính thức hiển thị **9.9.0**. Một lộ trình ví dụ cho dự án đang ở nhánh 8.x là:

```text
Baseline: 8.14.6 (mốc 8.x trước Gradle 9)
    |
    v
Sửa warnings/plugins trong nhánh 8.x
    |
    v
Gradle 9.0.0 + JVM >= 17
    |
    v
Sửa migration breakages + kiểm tra full CI
    |
    v
Gradle 9.9.0 (cập nhật theo từng mốc 9.x cần thiết)
    |
    v
Full CI + IDE + artifact/runtime validation
```

Đây là **ví dụ cho một đường nâng 8.x → 9.x**, không phải “mọi repository đều phải đi qua đúng 8.14.6 và 9.0.0”. Nếu xuất phát từ 6.x hoặc 7.x, trước tiên phải đọc các guide 6→7, 7→8 và kiểm tra plugin/toolchain legacy. Các target versions thay đổi theo thời gian; chọn release cụ thể sau khi xem release notes và support policy.

## 3. Chụp baseline trước khi chạm Wrapper

### 3.1. Lưu commit và trạng thái Git

Trên repository thực, bắt đầu một branch migration và giữ điểm rollback rõ ràng.

Linux/macOS:

```bash
git status --short
git rev-parse HEAD
./gradlew --version
java -version
./gradlew javaToolchains --console=plain
```

Windows PowerShell:

```powershell
git status --short
git rev-parse HEAD
.\gradlew.bat --version
java -version
.\gradlew.bat javaToolchains --console=plain
```

`javaToolchains` giúp xem JDK Gradle biết để toolchain resolution sử dụng; output tùy Gradle version và môi trường. `git status` phải được xem trước khi sửa để không lẫn các thay đổi chưa commit của developer vào PR nâng cấp.

### 3.2. Thu warnings từ phiên bản cũ

```bash
./gradlew help --warning-mode all --stacktrace --console=plain
./gradlew tasks --all --warning-mode all --console=plain
./gradlew clean check --warning-mode all --console=plain
```

`help` là phép kiểm tra **configuration phase** có chi phí thấp; `tasks` cho thấy task registration; `clean check` cần bao phủ tests/quality gates phù hợp dự án. Không tự động giả định root `check` đã bao gồm tất cả integration tests hoặc build-logic tests của included builds.

Ghi:

- Warning text, nguồn file/line/plugin.
- Lỗi đã tồn tại trước migration.
- Thời gian/CI run và Gradle/JDK version.
- Tests discovered/passed/failed/skipped.
- Artifact outputs, version, entrypoint và smoke checks.
- Plugin IDs/versions và repositories.
- Build Cache/Configuration Cache trạng thái hiện hành.

**Không biến mọi deprecation thành một commit vô tội vạ.** Phân loại warnings theo “mã mình sửa được”, “third-party plugin phải nâng” và “Gradle behavior thay đổi”.

### 3.3. Build Scan khi được cho phép

```bash
./gradlew help --scan
```

Theo Gradle upgrade guides, Develocity Build Scan deprecations view có thể hiển thị chi tiết hơn console. Nhưng một Build Scan có thể đưa dữ liệu build/environment lên dịch vụ ngoài hoặc máy chủ Develocity của tổ chức: phải tuân thủ chính sách về bảo mật nguồn, logs, metadata và credentials. Nếu không được phép, dùng `--warning-mode all` và lưu log nội bộ.

### 3.4. Bảng inventory trước nâng

| Hạng mục | Giá trị phải ghi từ project thật |
| --- | --- |
| Source commit | Git SHA đã chốt |
| Gradle version/distribution | Từ Wrapper, không đoán |
| Wrapper JAR checksum | Hash và kết quả đối chiếu official |
| Gradle Daemon JVM | Vendor/version/path |
| Java toolchains | Compiler/test targets |
| Kotlin DSL/embedded Kotlin | Theo Gradle version đang chạy |
| Kotlin/Android/third-party plugins | Plugin IDs + versions |
| Build logic | `buildSrc`, `build-logic`, precompiled scripts |
| Key tasks | `clean check`, integration, publish, assemble |
| Java tests | Số lượng, reports, JUnit version |
| Dependency locking/verification | File đã commit, trạng thái strict |
| CI/IDE settings | Runner OS/JDK, Wrapper/Gradle JVM |
| Artifact contract | Files, manifests, runtime behavior |
| Known deprecations | Từng warning và owner |

Đừng chỉ lưu một screenshot báo “BUILD SUCCESSFUL”; nó không đủ để chứng minh migration không thay đổi hành vi.

## 4. Kế hoạch nâng từng bước có thể kiểm soát

### 4.1. Giai đoạn 0 — Đặt quality gates

Trước khi đổi version, cần có **một phép đo baseline đang xanh**. Nếu build hiện đã fail, ghi lại failure và quyết định liệu có phải sửa riêng trước; đừng quy tất cả cho Gradle mới.

Một gate tối thiểu cho Java project:

```text
Gradle help / configuration succeeds
Java main + test compilation succeeds
Required unit tests actually run and pass
Required integration tests run and pass
Build logic plugins compile and validate
Packaged JAR/distribution is usable
Dependency resolution/verification succeeds
CI clean checkout passes
IDE sync still works on supported IDE/JDK
No accidental publishing/deployment side effect
```

### 4.2. Giai đoạn 1 — Sửa deprecations khi còn trên Gradle cũ

Nhiều deprecations hiện cảnh báo trên 8.x nhưng thành **errors** trên 9.x. Sửa khi tool cũ còn chạy sẽ cô lập nguyên nhân và dễ review.

Ví dụ:

- Dùng `tasks.register`/`tasks.named` thay vì tạo tasks quá sớm hoặc cú pháp Kotlin DSL đã loại bỏ.
- Chuyển task actions cần chạy process sang `Exec`, `JavaExec` hoặc injected `ExecOperations`.
- Thay DSL properties đã bị loại bỏ theo migration guide.
- Dùng `Provider`/`Property` đúng thay vì đọc environment hoặc project state tùy tiện trong task actions.
- Nâng các plugins đã thông báo hỗ trợ Gradle mục tiêu.
- Tối thiểu hóa việc truy cập Gradle internal packages.

### 4.3. Giai đoạn 2 — Nâng plugin theo compatibility matrix

Trước khi đổi Gradle major:

1. Xác định third-party plugin IDs và versions.
2. Đọc release notes/changelog của từng plugin.
3. Kiểm tra Gradle/JDK/Kotlin/AGP support range.
4. Đặt plugin version trong settings/version catalog/root plugins theo model dự án.
5. Chạy `help`/`check` trên Gradle cũ để tìm breaking changes do **plugin update**.
6. Ghi lại plugin version đã qua tests.

**Không đoán tương thích** chỉ từ số version của plugin. Plugin Gradle chạy trong build logic classpath và có thể phụ thuộc Gradle APIs, Kotlin/Groovy runtime và binary libraries.

### 4.4. Giai đoạn 3 — Nâng Wrapper một mốc

Nâng từ 8.x sang 9.0.0 rồi kiểm tra. Nếu vấn đề lớn, rollback tại checkpoint. Nếu ổn, tiếp tục 9.1/9.x theo mục tiêu đã chọn; không bắt buộc commit cho **mọi patch release**, nhưng mỗi lần thay đổi phải đọc những breaking changes tương ứng.

### 4.5. Giai đoạn 4 — Kiểm build logic

`buildSrc` và included build `build-logic` là **Gradle builds thực sự** với source/plugins riêng, không phải “mấy file cấu hình” mặc nhiên tương thích. Chạy validation/functional tests và xác minh consumer build từ root.

### 4.6. Giai đoạn 5 — Clean CI và artifact verification

Sau khi tests pass local:

- Checkout từ clean commit.
- Dùng Wrapper mới và JVM được support.
- Chạy required verification tasks.
- Kiểm tra application output, JAR/distribution contents.
- So dependency locks và verification metadata.
- Chạy integration/CI/IDE smoke tests.
- Không publish production artifact trước khi qua release approval.

### 4.7. Giai đoạn 6 — Chốt hoặc rollback

Chỉ merge khi tất cả required gates pass. Nếu một plugin quan trọng chưa hỗ trợ target, có thể giữ branch ở checkpoint thấp hơn trong thời gian nâng plugin hoặc thay plugin bằng phương án được phê duyệt. Không ép `--warning-mode none` và gọi migration thành công.

## 5. Wrapper: thành phần đầu tiên cần xác minh

Gradle Wrapper gồm:

```text
gradlew
gradlew.bat
gradle/
  wrapper/
    gradle-wrapper.jar
    gradle-wrapper.properties
```

- `gradlew` / `gradlew.bat`: launcher scripts.
- `gradle-wrapper.jar`: Java code khởi chạy tải và gọi distribution.
- `gradle-wrapper.properties`: URL, phiên bản distribution, checksum và network options.

Các file này thường được **commit vào Git**, kể cả `gradle-wrapper.jar`. Chúng là một phần của supply chain: Wrapper JAR được chạy **trước khi build script có thể tự kiểm tra điều gì**.

### 5.1. Nên nâng bằng task `:wrapper`

Ví dụ trên Linux/macOS, từ root project đã có Wrapper **được xác minh** và bản Gradle cũ vẫn chạy được:

```bash
./gradlew :wrapper --gradle-version 9.0.0 --distribution-type bin
./gradlew --version
```

PowerShell:

```powershell
.\gradlew.bat :wrapper --gradle-version 9.0.0 --distribution-type bin
.\gradlew.bat --version
```

Lệnh đầu tiên đổi `gradle-wrapper.properties` (distributionUrl) và có thể giữ một số properties hiện có. Lệnh `--version` chạy qua distribution được cấu hình mới để xác minh. Khi nâng 8→9, máy cần JVM 17+ để chạy distribution 9.0.0.

### 5.2. Chạy Wrapper task **hai lần** để đồng bộ scripts và JAR

Tài liệu Gradle giải thích lần chạy `:wrapper` đầu thường chỉ cập nhật **properties**, còn `gradle-wrapper.jar` và launcher scripts có thể chưa được cập nhật hoàn toàn. Sau khi bản mới đã chạy, chạy lần hai:

```bash
./gradlew :wrapper --gradle-version 9.0.0 --distribution-type bin
./gradlew --version
git diff -- gradlew gradlew.bat gradle/wrapper/gradle-wrapper.properties
git status --short
```

Có thể dùng `git diff --stat` để xem JAR đã thay đổi về bytes (Git hiển thị binary diff khác). **Không xóa Wrapper JAR** chỉ vì là binary. Nếu không có thay đổi JAR, hãy kiểm xem lần nâng có thật sự cần wrapper JAR mới và validate hash.

### 5.3. Mốc tiếp theo: 9.9.0 là ví dụ hiện tại

Sau khi migration lên 9.0.0 đã qua gates và tài liệu release cho phép, có thể tiếp tục:

```bash
./gradlew :wrapper --gradle-version 9.9.0 --distribution-type bin
./gradlew --version
./gradlew :wrapper --gradle-version 9.9.0 --distribution-type bin
```

Với **Gradle 9.x**, giá trị `distributionUrl` trong properties cần là **phiên bản đầy đủ dạng X.Y.Z**, không viết 9 hoặc 9.9 làm version trực tiếp trong file. Khi gọi `--gradle-version`, từ Gradle 9 CLI có thể nhận các dạng rút gọn và resolve release, nhưng **pin patch đầy đủ** vẫn là lựa chọn tốt cho reproducibility và review.

**Nếu môi trường còn sử dụng Wrapper distributions qua một mirror nội bộ**, dùng URL/mirror và hash thật theo policy; đừng tự thay URL về public chỉ để vượt network ACL.

### 5.4. Một trường hợp dễ sai: đã có `distributionSha256Sum`

Nếu `gradle-wrapper.properties` cũ đã chứa `distributionSha256Sum` mà bạn đổi sang version khác, Gradle có thể yêu cầu **checksum tương ứng phiên bản mới** khi chạy `wrapper`. Không giữ checksum của ZIP 8.x cho distribution 9.x.

Có thể tải checksum chính thức từ Gradle distributions hoặc trang release-checksums rồi dùng `--gradle-distribution-sha256-sum`. Ví dụ POSIX shell (chạy trong trusted environment, sau khi xác minh nguồn URL và Wrapper hiện có):

```bash
SUM="$(curl -fsSL https://services.gradle.org/distributions/gradle-9.0.0-bin.zip.sha256 | tr -d '\r\n')"
./gradlew :wrapper --gradle-version 9.0.0 \
  --distribution-type bin \
  --gradle-distribution-sha256-sum "$SUM"
./gradlew --version
./gradlew :wrapper --gradle-version 9.0.0 \
  --distribution-type bin \
  --gradle-distribution-sha256-sum "$SUM"
```

Script không in hoặc đoán checksum từ tài liệu; nó lấy bytes hash ở endpoint chính thức. Trong môi trường yêu cầu release review, nên **đối chiếu giá trị SUM** qua [Gradle release checksums](https://gradle.org/release-checksums/) hoặc nguồn độc lập được phê duyệt trước khi commit. Không dùng script này với untrusted network/proxy mà không kiểm tra TLS và nguồn phân phối.

### 5.5. Wrapper ZIP checksum khác Wrapper JAR checksum

Hai kiểm tra khác nhau:

| Đối tượng | Cách kiểm | Tác dụng |
| --- | --- | --- |
| **Gradle distribution ZIP** | `distributionSha256Sum` trong `gradle-wrapper.properties` | Kiểm tra bản ZIP tải xuống |
| **`gradle-wrapper.jar`** | So SHA-256 của JAR với danh sách checksum Gradle chính thức | Phát hiện Wrapper JAR bị sửa |
| **Launcher scripts** | Review Git diff/nguồn tin cậy | Không nằm trong checksum ZIP được nêu ở properties |
| **Build logic và plugins** | Code review, dependency verification, tests | Có thể thực thi với quyền của build |

**Chú ý:** checksum ZIP thường được Wrapper kiểm tra khi **tải mới**. Một distribution đã được tải/cached từ trước có thể không được verify lại trên mọi invocation. Khi cần thực hiện clean-room verification, dùng Gradle User Home tách biệt và policy tin cậy.

### 5.6. Kiểm tra Wrapper JAR trước khi chạy mã chưa tin cậy

Linux:

```bash
sha256sum gradle/wrapper/gradle-wrapper.jar
```

macOS:

```bash
shasum -a 256 gradle/wrapper/gradle-wrapper.jar
```

PowerShell:

```powershell
(Get-FileHash gradle\wrapper\gradle-wrapper.jar -Algorithm SHA256).Hash.ToLower()
```

Sau đó **đối chiếu** giá trị thật với [bảng Gradle release-checksums](https://gradle.org/release-checksums/). Không có một hash “mẫu” nào đúng cho mọi phiên bản Wrapper.

Khi CI dùng `gradle/actions/setup-gradle` phiên bản hỗ trợ, action có thể **validate Wrapper JAR** trong bước setup. Với repo untrusted, kiểm soát workflow trước khi thực thi; không tin rằng file tên `gradle-wrapper.jar` mặc nhiên là JAR chính thức.

### 5.7. Không nhầm “Wrapper đã lên version” với “project đã migrate”

`./gradlew --version` thành công chỉ chứng minh Wrapper khởi chạy distribution được chọn. Nó chưa chứng minh:

- `settings.gradle.kts`/`build.gradle.kts` compile.
- Third-party plugins compatible.
- `build-logic` compile.
- Task `test` thực chạy.
- JAR/distribution hợp lệ.
- IDE/CI/production runtime tương thích.

Do đó sau Wrapper, **luôn chạy ít nhất `help`, các build-logic checks và full verification**.

## 6. Phân biệt plugin version với Gradle version

Gradle version ở Wrapper và third-party plugin version là **hai axes độc lập**.

Ví dụ:

```kotlin
plugins {
    id("org.jetbrains.kotlin.jvm") version "2.2.20"
}
```

Đây là **mảnh minh họa về cú pháp**, không phải lời khuyên nâng bất kỳ dự án nào thẳng lên phiên bản trong ví dụ. Phải chọn plugin version dựa trên compatibility matrix của chính plugin, Gradle target, JDK và các thư viện khác.

### 6.1. Nguồn plugin versions có thể ở đâu?

- Root `plugins` block với `apply false`.
- `settings.gradle.kts` trong `pluginManagement.plugins`.
- Version catalog `gradle/libs.versions.toml` và aliases.
- Precompiled script plugin trong `build-logic`.
- `buildSrc`, root `buildscript` dependencies legacy.
- Included plugin builds qua `pluginManagement.includeBuild`.
- `init.gradle`/`init.gradle.kts` của môi trường.
- External convention plugin được publish vào Maven/Plugin Portal.

**Không chỉ tìm root `build.gradle.kts` rồi kết luận plugin đã được nâng đồng bộ.** Một plugin version được pin ở nơi khác có thể vẫn chạy mã cũ.

### 6.2. Repository của plugins khác repository của ứng dụng

Trong `settings.gradle.kts`:

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
```

cấu hình plugin resolution, gồm plugin marker và implementation. Trong project:

```kotlin
repositories {
    mavenCentral()
}
```

cấu hình dependencies của ứng dụng. Hai phần có thể cùng trỏ đến server nhưng có chức năng khác. Nếu plugin upgrade báo `Plugin not found`, kiểm plugin ID, marker/version, `pluginManagement.repositories` và authentication thay vì sửa project `implementation`.

### 6.3. Dấu hiệu plugin version chưa tương thích

| Lỗi | Hướng kiểm |
| --- | --- |
| `Plugin was not found` | Plugin ID/version/repository/marker |
| `NoSuchMethodError` | Plugin dùng API/library version không còn tương thích |
| `NoClassDefFoundError` | Plugin classpath/JDK/Gradle runtime |
| `UnsupportedClassVersionError` | Bytecode plugin mới hơn JVM Gradle |
| `Could not create task ...` | Plugin task API cũ, removed Gradle APIs |
| `A problem occurred configuring project` | Plugin `apply`, settings, extensions |
| `Could not find method ...` | Kotlin/Groovy DSL/API đổi |
| `ClassCastException` | Plugin classpath hoặc Gradle model incompatibility |
| `Unknown Kotlin metadata version` | Kotlin DSL/build logic compiled incompatibly |
| `Failed to apply plugin` | Đọc `Caused by` của plugin, không chỉ wrapper |

Đọc **stacktrace và first useful code frame**, kiểm plugin changelog và target Gradle support. Không xử lý bằng cách tự thêm plugin JAR vào Java app `runtimeClasspath`.

## 7. Build logic cũng cần được migrate như một dự án riêng

Mã Gradle riêng có thể nằm ở:

```text
root/
├── build.gradle.kts
├── settings.gradle.kts
├── buildSrc/
│   └── src/main/kotlin/...
└── build-logic/
    ├── settings.gradle.kts
    ├── build.gradle.kts
    └── src/main/java/...
```

### 7.1. `buildSrc`

`buildSrc` được Gradle nhận diện và build để cung cấp types/functions cho build scripts. Nếu dùng API cũ, Gradle mới có thể fail **trước khi task của ứng dụng bắt đầu**.

Kiểm:

- Plugins/dependencies của `buildSrc`.
- Kotlin/Groovy versions và source JVM target.
- Gradle API dependencies.
- Tests thuộc `buildSrc` nếu có.
- Chỗ dùng `Project.exec`, legacy task APIs, eager configuration.
- Extension APIs đã deprecated/removed.

### 7.2. Included build `build-logic`

Một included build có `settings.gradle.kts` và `build.gradle.kts` riêng. `pluginManagement.includeBuild("build-logic")` cho phép root build resolve plugin IDs do included build cung cấp, nhưng **không làm included build tự dùng mọi repository/dependency setting của root**.

Cần kiểm:

- Included build Gradle plugin development setup.
- Repositories của included build.
- Plugin implementation class và descriptor.
- Toolchain/target của build logic.
- TestKit functional tests ở nhiều Gradle versions nếu plugin được tái sử dụng.
- Plugin version/cross-build compatibility.
- Task registration, configuration cache và declared task inputs/outputs.
- Root consumer có áp dụng được plugin sau nâng Wrapper không.

### 7.3. Precompiled script plugins

Các file như:

```text
build-logic/src/main/kotlin/dev.learning.java-conventions.gradle.kts
```

được biên dịch thành precompiled convention plugin theo plugin build model. Kotlin DSL/embedded Kotlin upgrade có thể ảnh hưởng cách compiler xử lý code, delegated properties, imports, code generation và extension accessors.

Không xem precompiled script plugin như file text thuần không cần test. Chạy plugin build và root consumer; nếu plugin được publish cho dự án khác, kiểm Gradle versions của consumers theo compatibility matrix.

## 8. Lab thực hành hoàn chỉnh: Gradle Kotlin DSL + Java 17 + included binary plugin

Lab cố ý nhỏ nhưng có đủ ba lớp cần kiểm:

1. Gradle Wrapper của root.
2. Java application và JUnit tests.
3. Included build `build-logic` chứa một binary Gradle plugin Java.

Đây là **một project mẫu độc lập**, không dùng source từ repository người học; chỉ sử dụng API chính thức và JDK 17.

### 8.1. Cây thư mục

```text
gradle-upgrade-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── src/
│   ├── main/java/dev/learning/
│   │   ├── Totals.java
│   │   └── Main.java
│   └── test/java/dev/learning/
│       └── TotalsTest.java
└── build-logic/
    ├── settings.gradle.kts
    ├── build.gradle.kts
    ├── src/main/java/dev/learning/
    │   ├── MigrationChecksPlugin.java
    │   └── MigrationCheckTask.java
    └── src/test/java/dev/learning/
        └── MigrationChecksPluginTest.java
```

Các Wrapper files được **tạo bằng Gradle Wrapper task tin cậy**, không phải chép JAR từ tài liệu. `build/`, `.gradle/` và caches sinh ra khi chạy; chúng không cần commit.

### 8.2. Root settings

**File `settings.gradle.kts`:**

```kotlin
pluginManagement {
    includeBuild("build-logic")
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = "gradle-upgrade-lab"
```

`includeBuild("build-logic")` ở `pluginManagement` cho phép root `plugins` DSL áp dụng plugin ID được đăng ký trong included build. Không cần publish plugin lên Plugin Portal để lab chạy; plugin source được build cục bộ.

### 8.3. Root build script

**File `build.gradle.kts`:**

```kotlin
plugins {
    application
    id("dev.learning.migration-checks")
}

group = "dev.learning"
version = "1.0.0"

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.10.2")
}

application {
    mainClass.set("dev.learning.Main")
}

tasks.test {
    useJUnitPlatform()
}

tasks.named("check") {
    dependsOn("migrationCheck")
}
```

**Cơ chế:**

- Core plugin `application` áp dụng Java plugin, tạo `run`, `jar`, `test` và `check`.
- Plugin `dev.learning.migration-checks` được resolve từ included build và đăng ký task `migrationCheck`.
- `check` phụ thuộc `migrationCheck` nên build verification kiểm được plugin implementation bên cạnh tests.
- Java toolchain 17 dùng compile/test tasks, không tự đổi Gradle Daemon JVM.
- JUnit dependencies chỉ nằm trên test classpaths.
- Không dùng Kotlin Gradle Plugin hoặc Android Gradle Plugin trong lab; với dự án thực phải thêm matrix kiểm thử tương ứng.

### 8.4. Application Java source

**File `src/main/java/dev/learning/Totals.java`:**

```java
package dev.learning;

public final class Totals {
    private Totals() {
    }

    public static long sumUpTo(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be non-negative");
        }

        long result = 0;
        for (int i = 1; i <= n; i++) {
            result += i;
        }
        return result;
    }
}
```

**File `src/main/java/dev/learning/Main.java`:**

```java
package dev.learning;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        long result = Totals.sumUpTo(10);
        System.out.println("migration-lab=OK; total=" + result);
    }
}
```

**Stdout chính xác từ chương trình:**

```text
migration-lab=OK; total=55
```

Đây là kết quả deterministic với input 10. Bài không tuyên bố chương trình đã chạy trên máy người học; stdout là **kết quả mong đợi từ mã Java**.

### 8.5. Unit tests JUnit 5

**File `src/test/java/dev/learning/TotalsTest.java`:**

```java
package dev.learning;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

final class TotalsTest {
    @Test
    void zeroHasZeroTotal() {
        assertEquals(0L, Totals.sumUpTo(0));
    }

    @Test
    void tenHasFiftyFiveTotal() {
        assertEquals(55L, Totals.sumUpTo(10));
    }

    @Test
    void negativeIsRejected() {
        assertThrows(
                IllegalArgumentException.class,
                () -> Totals.sumUpTo(-1)
        );
    }
}
```

Ba tests có ý nghĩa độc lập: zero, positive và invalid input. Trong migration, nếu tests không được discover, task `test` báo `NO-SOURCE` hoặc XML report chỉ ghi 0 tests, phải điều tra trước khi tuyên bố QA PASS.

### 8.6. Included build settings

**File `build-logic/settings.gradle.kts`:**

```kotlin
rootProject.name = "build-logic"
```

### 8.7. Included build Gradle script

**File `build-logic/build.gradle.kts`:**

```kotlin
plugins {
    `java-gradle-plugin`
}

group = "dev.learning"
version = "1.0.0"

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.10.2")
}

gradlePlugin {
    plugins {
        create("migrationChecks") {
            id = "dev.learning.migration-checks"
            implementationClass = "dev.learning.MigrationChecksPlugin"
        }
    }
}

tasks.test {
    useJUnitPlatform()
}
```

Gradle Plugin Development Plugin `java-gradle-plugin` cung cấp Gradle API dependency/integration cần cho Java binary plugin và TestKit, đồng thời tạo plugin descriptor từ registration. Không thêm `gradleApi()` thủ công nếu chưa có lý do vì plugin đã quản lý phần này.

**Quan trọng khi nâng:** included build là một Gradle build riêng có dependencies và tests riêng. Root `check` chỉ chạy task `migrationCheck` được plugin đăng ký; nó **không tự chạy `build-logic:test`** trừ khi được cấu hình riêng. Vì vậy cần thêm gate kiểm thử included build.

### 8.8. Java Gradle plugin implementation

**File `build-logic/src/main/java/dev/learning/MigrationChecksPlugin.java`:**

```java
package dev.learning;

import org.gradle.api.Plugin;
import org.gradle.api.Project;

public final class MigrationChecksPlugin implements Plugin<Project> {
    @Override
    public void apply(Project project) {
        project.getTasks().register(
                "migrationCheck",
                MigrationCheckTask.class,
                task -> {
                    task.setGroup("verification");
                    task.setDescription(
                            "Prove that included build logic can run"
                    );
                }
        );
    }
}
```

Plugin **lazily register** task qua `TaskContainer.register`, không dùng eager `create`. Nó không gọi deprecated `Project.exec`. Sau khi plugin được áp dụng, consumer thấy `migrationCheck`.

**File `build-logic/src/main/java/dev/learning/MigrationCheckTask.java`:**

```java
package dev.learning;

import org.gradle.api.DefaultTask;
import org.gradle.api.tasks.TaskAction;

public abstract class MigrationCheckTask extends DefaultTask {
    @TaskAction
    public void verifyBuildLogic() {
        getLogger().lifecycle("build-logic-check=PASS");
    }
}
```

Task chỉ log; nó **không có output file và không phải một task cacheable**. Với production task tạo output, phải khai báo `@Input`/`@OutputFile` và test up-to-date/build cache correctness. Ví dụ tập trung compatibility plugin API sau nâng Gradle.

### 8.9. Functional TestKit test cho plugin

**File `build-logic/src/test/java/dev/learning/MigrationChecksPluginTest.java`:**

```java
package dev.learning;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.gradle.testkit.runner.BuildResult;
import org.gradle.testkit.runner.GradleRunner;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertTrue;

final class MigrationChecksPluginTest {
    @TempDir
    Path fixture;

    @Test
    void appliesPluginAndRunsTask() throws IOException {
        Files.writeString(
                fixture.resolve("settings.gradle.kts"),
                "rootProject.name = \"fixture\"\n"
        );

        Files.writeString(
                fixture.resolve("build.gradle.kts"),
                "plugins { id(\"dev.learning.migration-checks\") }\n"
        );

        BuildResult result = GradleRunner.create()
                .withProjectDir(fixture.toFile())
                .withArguments("migrationCheck", "--stacktrace")
                .withPluginClasspath()
                .build();

        assertTrue(
                result.getOutput().contains("build-logic-check=PASS")
        );
    }
}
```

`java-gradle-plugin` tự thêm TestKit dependencies/inject plugin-under-test classpath để `withPluginClasspath()` hoạt động. Test này **không cần publish plugin JAR** vào repository. Nó kiểm plugin ID/descriptor, apply và task execution thật.

### 8.10. Chạy lab từ root

Linux/macOS:

```bash
./gradlew --version
./gradlew help --warning-mode all --console=plain
./gradlew clean check --warning-mode all --console=plain
./gradlew -p build-logic test validatePlugins --console=plain
./gradlew run --quiet
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat help --warning-mode all --console=plain
.\gradlew.bat clean check --warning-mode all --console=plain
.\gradlew.bat -p build-logic test validatePlugins --console=plain
.\gradlew.bat run --quiet
```

**Dòng do included plugin task in khi `check` chạy:**

```text
build-logic-check=PASS
```

**Stdout từ `run --quiet`:**

```text
migration-lab=OK; total=55
```

Đó là hai output **phân biệt**: một của Gradle task action, một của Java application. Gradle có thể in thêm task headings/BUILD SUCCESSFUL nếu không dùng `--quiet`; không coi hai dòng trên là toàn bộ Gradle transcript.

### 8.11. Chạy Java code độc lập bằng Java 17

Từ root:

Linux/macOS:

```bash
mkdir -p build/manual-classes
javac -d build/manual-classes \
  src/main/java/dev/learning/Totals.java \
  src/main/java/dev/learning/Main.java
java -cp build/manual-classes dev.learning.Main
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force build\manual-classes | Out-Null
javac -d build\manual-classes src\main\java\dev\learning\Totals.java src\main\java\dev\learning\Main.java
java -cp build\manual-classes dev.learning.Main
```

Stdout chính xác:

```text
migration-lab=OK; total=55
```

Điều này xác minh Java source cơ bản nhưng **không thay thế** JUnit tests và build logic TestKit checks. Một Java program chạy được chưa chứng minh Gradle plugin resolution trên Wrapper mới hoạt động.

## 9. Chạy cùng lab qua hai phiên bản Gradle

Cách kiểm tương thích là **giữ source và gates không đổi** khi đổi một version.

Ví dụ một branch dùng Wrapper 8.14.6 (trước nâng):

```bash
./gradlew --version
./gradlew help --warning-mode all --console=plain
./gradlew clean check --console=plain
./gradlew -p build-logic test validatePlugins --console=plain
./gradlew run --quiet
```

Ghi kết quả vào baseline. Khi nâng sang 9.0.0, chạy lại **đúng bộ lệnh** trên cùng source revision hoặc một candidate thay đổi có ghi rõ. Tất cả tests/behavior phải pass.

### 9.1. Không nhầm baseline tests với mới phát sinh

Các tình huống cần phân biệt:

- Baseline 8.14.6 fail: không quy lỗi đó cho 9.0.0.
- Baseline pass, 9.0.0 fail ở plugin: khả năng Gradle API/classpath compatibility.
- 9.0.0 pass nhưng 9.9.0 fail: xem migration notes của những 9.x versions nằm giữa.
- Root `check` pass nhưng `build-logic:test` fail: migration chưa hoàn thành.
- Gradle build pass nhưng app runtime output đổi: cũng là regression.

### 9.2. Một sample acceptance record

| Gate | 8.14.6 baseline | 9.0.0 candidate | 9.9.0 candidate |
| --- | --- | --- | --- |
| Wrapper verified | Cần đo | Cần đo | Cần đo |
| `help --warning-mode all` | Cần đo | Cần đo | Cần đo |
| Root `clean check` | Cần đo | Cần đo | Cần đo |
| `build-logic:test` | Cần đo | Cần đo | Cần đo |
| `build-logic:validatePlugins` | Cần đo | Cần đo | Cần đo |
| `migrationCheck` | Cần đo | Cần đo | Cần đo |
| Java stdout | Cần so với contract | Cần so | Cần so |
| IDE sync | Cần đo | Cần đo | Cần đo |
| Clean CI | Cần đo | Cần đo | Cần đo |
| Artifact contract | Cần kiểm | Cần kiểm | Cần kiểm |

Các ô “Cần đo” ở đây là **tên trạng thái quy trình** trong bảng phương pháp, không phải một kết quả đã chạy hay metadata của project thật. Đừng ghi PASS nếu chưa thực thi gate.

## 10. Groovy DSL tương đương cho lab

Nếu dự án dùng Groovy DSL, vẫn có thể áp dụng binary plugin Java trên; chỉ thay các Gradle DSL files.

**File `settings.gradle` của root:**

```groovy
pluginManagement {
    includeBuild('build-logic')
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = 'gradle-upgrade-lab'
```

**File `build.gradle` của root:**

```groovy
plugins {
    id 'application'
    id 'dev.learning.migration-checks'
}

group = 'dev.learning'
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
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

application {
    mainClass = 'dev.learning.Main'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

tasks.named('check') {
    dependsOn 'migrationCheck'
}
```

**File `build-logic/settings.gradle`:**

```groovy
rootProject.name = 'build-logic'
```

**File `build-logic/build.gradle`:**

```groovy
plugins {
    id 'java-gradle-plugin'
}

group = 'dev.learning'
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
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

gradlePlugin {
    plugins {
        migrationChecks {
            id = 'dev.learning.migration-checks'
            implementationClass = 'dev.learning.MigrationChecksPlugin'
        }
    }
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Java sources và TestKit test vẫn giữ nguyên. Đây là **phương án thay thế Kotlin DSL**, không chạy đồng thời cả `build.gradle` và `build.gradle.kts` trong cùng project.

### 10.1. Khi đổi Groovy DSL sang Kotlin DSL có nên kết hợp nâng Gradle?

Không nên trộn nếu không bắt buộc. Chuyển DSL là một migration riêng có thể đổi syntax, type-safe accessors, extension names và API resolution; nếu vừa đổi DSL vừa nâng Gradle major, lỗi rất khó khoanh vùng.

Thứ tự khuyến nghị:

1. Giữ DSL cũ, xử lý deprecations và plugin versions.
2. Nâng Gradle/Wrapper và verify.
3. Nếu vẫn muốn Kotlin DSL, làm trong PR riêng với cùng correctness gates.

## 11. Lỗi Gradle 9: ví dụ API bị loại bỏ

### 11.1. `Project.exec` đã không còn trong Gradle 9

Một số build scripts/plugins cũ dùng:

```groovy
// Ví dụ legacy API: không dùng cho Gradle 9.
project.exec {
    commandLine 'git', 'rev-parse', '--short', 'HEAD'
}
```

`Project.exec` và script-level `exec/javaexec` đã bị loại bỏ trong Gradle 9.0. Nếu muốn chạy external process trong một task, ưu tiên task types `Exec` hoặc `JavaExec`:

**Gradle Kotlin DSL:**

```kotlin
tasks.register<Exec>("printCommit") {
    commandLine("git", "rev-parse", "--short", "HEAD")
}
```

**Gradle Groovy DSL:**

```groovy
tasks.register('printCommit', Exec) {
    commandLine 'git', 'rev-parse', '--short', 'HEAD'
}
```

Đây là **hai đoạn thay thế theo DSL**, không phải task trong lab chính. Chúng yêu cầu `git` có trong PATH và repository chứa commit; output **không cố định** vì phụ thuộc SHA thực tế.

Với plugin Java hoặc Kotlin code cần chạy process từ task, cân nhắc injected `ExecOperations`; phải tuân thủ Gradle service injection/lifecycle API đúng version. Không chuyển bừa external command vào configuration phase chỉ để tránh lỗi removal.

### 11.2. Eager task API và loại bỏ Kotlin DSL shorthand

Gradle hướng tới lazy configuration:

```kotlin
tasks.register("verifyThings") {
    group = "verification"
    doLast {
        logger.lifecycle("verified")
    }
}

tasks.named("verifyThings") {
    description = "Small verification task"
}
```

Đoạn trên không cần `tasks.getByName(...)` hoặc eager creation. Nếu build script cũ dùng cú pháp Kotlin DSL kiểu `"taskName"()`, Gradle 9 đã loại bỏ dạng này; dùng `tasks.named("taskName")` và API thích hợp.

### 11.3. `WriteProperties.outputFile` đã bị loại bỏ

Migration guide nêu thuộc tính `WriteProperties.outputFile` bị loại bỏ; thay bằng `destinationFile`. Ví dụ Kotlin DSL:

```kotlin
import org.gradle.api.tasks.WriteProperties

tasks.register<WriteProperties>("writeBuildInfo") {
    destinationFile.set(layout.buildDirectory.file("generated/build-info.properties"))
    property("application", "gradle-upgrade-lab")
}
```

Mảnh này cần đặt trong build script có import hợp lệ, không phải Java main source. Task sẽ tạo file properties khi được chạy. Kiểm lại exact API qua migration guide phiên bản đích; không dùng `outputFile` cũ.

### 11.4. Kotlin DSL delegated properties thay đổi tiếp trong 9.x

Tài liệu upgrading 9.x đã deprecate nhiều Kotlin DSL delegates như:

```kotlin
// Legacy style cần xem xét khi hướng tới Gradle 10:
val demoTask by tasks.registering
```

Thay bằng explicit APIs:

```kotlin
val demoTask = tasks.register("demoTask") {
    doLast {
        logger.lifecycle("demo")
    }
}
```

**Phân biệt:** deprecation trong 9.x là tín hiệu cho migration tiếp theo (một số thứ dự kiến removed ở Gradle 10), không có nghĩa mọi syntax đã fail ngay trên Gradle 9.0. Xem đúng release guide trước khi sửa.

### 11.5. Không gọi Gradle internal API như public contract

Plugin code import `org.gradle.internal.*` có thể compile ở một version rồi fail khi runtime thay đổi. Ưu tiên `org.gradle.api.*` public APIs, `Provider`, `Property` và Gradle task types; nếu plugin cần internal behavior, phải đánh giá rủi ro và matrix test chặt hơn.

Một `NoSuchMethodError` không nhất thiết là bug app; nó có thể do plugin đang gọi API Gradle cũ trên runtime mới.

## 12. Kotlin, Android và convention plugins: nâng theo hệ sinh thái

### 12.1. Kotlin Gradle Plugin (KGP)

Đừng nhầm:

- **Embedded Kotlin của Gradle** dành cho Kotlin DSL/build logic.
- **Kotlin Gradle Plugin** áp dụng để compile source Kotlin của application/library.
- **Kotlin compiler version** được KGP chọn hoặc điều khiển.

Gradle 9.0 có mức tối thiểu KGP theo migration guide; nhưng plugin Kotlin còn có bảng hỗ trợ Gradle/AGP/JDK riêng. Khi nâng KGP, phải kiểm target, compiler flags, source API, Kapt/KSP và test behavior.

### 12.2. Android Gradle Plugin (AGP)

Android projects chịu constraint giữa Gradle, AGP, JDK, Kotlin và Android SDK. Trước nâng Wrapper, kiểm AGP release notes và minimum versions, tránh đổi Gradle 9 trong khi AGP hiện tại chỉ hỗ trợ Gradle cũ.

Gradle 9.0 bắt đầu với minimum supported AGP 8.4.0 theo official Gradle migration guide; **khả năng phù hợp thực tế** vẫn cần test đúng AGP version và release notes. Không lấy con số tối thiểu làm lời khuyên dùng một bản AGP đã hết support.

### 12.3. Precompiled Kotlin script plugin compatibility

Nếu một plugin viết bằng Kotlin DSL và **được build bằng Gradle 9.x**, metadata Kotlin của nó có thể không dùng được trên các bản Gradle rất cũ. Gradle docs nêu plugin Kotlin DSL được build bằng 9.x yêu cầu consumer Gradle **8.11+**; với consumer thấp hơn, cần build/publish từ Gradle version phù hợp hoặc thay đổi support policy.

Vì vậy “nâng producer để phát hành plugin” và “nâng consumer đang dùng plugin” có thể phải phối hợp. Không giả định chỉ đổi Wrapper root là xong nếu plugin được nhiều repositories dùng.

### 12.4. Groovy 4 compatibility

Gradle 9 chuyển Groovy runtime lên 4. Nếu custom plugin/build logic dùng Groovy AST transforms, MetaClass hoặc third-party Groovy libraries, cần chạy tests trên cả target Gradle/Groovy environments. Không fix `MissingMethodException` bằng cách thêm nhiều version Groovy khác nhau vào cùng build classpath nếu chưa hiểu xung đột.

## 13. Migrate `buildSrc` và convention plugins theo trình tự

### 13.1. Inventory build logic

Tìm những nguồn code/build logic thực sự được dùng:

```text
buildSrc/src/main/java/
buildSrc/src/main/kotlin/
buildSrc/src/main/groovy/
build-logic/src/main/java/
build-logic/src/main/kotlin/
build-logic/src/main/groovy/
gradle/libs.versions.toml
settings.gradle.kts
build.gradle.kts
*.gradle / *.gradle.kts
```

Nếu repository có nhiều included builds, kiểm từng build độc lập. Một project có thể có cả `buildSrc` và `build-logic`; đừng kết luận chúng tự dùng chung settings/version catalog.

### 13.2. Build-logic smoke test là gate bắt buộc

Chạy:

```bash
./gradlew help --warning-mode all --console=plain
./gradlew -p build-logic test validatePlugins --console=plain
./gradlew check --console=plain
```

Các lệnh là ví dụ cho lab có `build-logic`. Với project thực, thay đúng path và Gradle tasks; nếu included build không áp dụng `java-gradle-plugin`, nó có thể không có `validatePlugins`.

### 13.3. Chạy plugin TestKit trên nhiều Gradle versions

Khi plugin được nhiều builds dùng, có thể viết TestKit functional tests và chọn Gradle version:

```java
GradleRunner.create()
        .withGradleVersion("9.0.0")
        .withProjectDir(fixture.toFile())
        .withArguments("migrationCheck", "--stacktrace")
        .withPluginClasspath()
        .build();
```

Đây là **mảnh code đặt trong TestKit test đã có imports/fixture** chứ không phải một `main` độc lập. Thêm một test với `8.14.6` hoặc `9.9.0` nếu chúng nằm trong support matrix. TestKit có thể tải distribution lần đầu; Gradle/JDK của test runner phải hỗ trợ version đang chạy.

Quan trọng: `withGradleVersion` kiểm runtime dùng cho **fixture build** trong test, còn plugin-under-test được compile bởi **producer build**. Nếu producer compile bytecode/API không tương thích với version test, test có thể fail — đó là thông tin cần dùng để quyết định support policy.

### 13.4. Đừng tuyên bố compatibility nếu chỉ test Wrapper mới

Nếu một plugin xuất bản công khai dùng ở Gradle 8.x và 9.x, cần chạy trên **mỗi family được hỗ trợ** và đánh giá changes của Kotlin metadata/Gradle APIs. Một test duy nhất trên 9.9.0 không chứng minh consumer 8.4.0 vẫn dùng được.

## 14. Configuration Cache, Build Cache và upgrade regressions

Khi nâng Gradle, thay đổi task implementation/plugins có thể dẫn tới cache misses hoặc incompatibility.

### 14.1. Build Cache

```bash
./gradlew clean check --no-build-cache --console=plain
./gradlew clean check --build-cache --console=plain
```

Hai lệnh minh họa hai modes; **không dùng ngay chúng làm phép benchmark A/B công bằng** nếu cache population/state khác nhau. Về correctness, lần chạy `--no-build-cache` hữu ích để kiểm task actions tạo outputs từ source mới, tránh chỉ khôi phục stale task outputs.

Nếu migration làm cache hit rate giảm, xem task implementation/classpath changes và inputs; không vội bỏ một input quan trọng để ép `FROM-CACHE`.

### 14.2. Configuration Cache

```bash
./gradlew check --configuration-cache --console=plain
./gradlew check --configuration-cache --console=plain
```

Invocation đầu có thể store entry; lần hai có thể reuse nếu phù hợp. Nếu Gradle báo configuration-cache problems, đọc report và sửa custom plugin/task code giữ `Project` state hoặc truy cập APIs không được phép trong execution phase.

Không dùng `--configuration-cache-problems=warn` lâu dài để che incompatibilities. Và nếu build chưa hề dùng Configuration Cache ở baseline, không nhất thiết phải bật đồng thời với nâng Gradle major; có thể triển khai nó ở bước tối ưu riêng.

### 14.3. Đừng xóa toàn bộ caches như bước đầu tiên

`--refresh-dependencies` chỉ kiểm tra lại metadata/artifacts theo cơ chế Gradle, **không sửa API Gradle đã removed**. Xóa `~/.gradle` có thể khiến CI/dev tốn nhiều download, xóa clues và tạo nhiễu mới.

Ưu tiên đọc error stacktrace, dependency reports, plugin compatibility notes và migration guide trước khi reset caches. Khi nghi stale cache, dùng isolated Gradle User Home hoặc cache-disabled invocation có chủ đích.

## 15. Gradle dependency, plugin repositories và locks

### 15.1. Version catalogs không tự bảo đảm compatibility

Một version catalog giúp quản lý versions tập trung:

**File `gradle/libs.versions.toml` — ví dụ cấu trúc:**

```toml
[versions]
junit = "5.10.2"

[libraries]
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }

[plugins]
# Plugin aliases ở project thật cần chọn version sau compatibility review.
```

Đây là **ví dụ cú pháp version catalog**; không cần thêm file này vào lab vì lab đã khai báo JUnit trực tiếp. Catalog giúp tránh version mismatch nhưng không tự chứng minh plugin hỗ trợ Gradle 9.

### 15.2. Dependency locking

Nếu dự án dùng locking, nâng Gradle hoặc plugin có thể thay đổi dependency graph. Kiểm lockfiles đã commit, xác định reason của các version changes và không tự chạy `--write-locks` trong release CI để làm lỗi biến mất.

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency junit-jupiter --configuration testRuntimeClasspath
```

Lệnh cần chạy trong project/configuration đúng. Trong multi-project root không có `runtimeClasspath` thì phải dùng `:app:dependencies` hoặc subproject phù hợp.

### 15.3. Dependency verification

`gradle/verification-metadata.xml` có thể ghi checksums/signatures của artifacts tải từ repositories. Khi nâng plugin/dependencies, metadata mới phải được review; không sinh lại toàn bộ hashes rồi tự tin chúng đều an toàn.

Một release gate có thể kiểm strict:

```bash
./gradlew --dependency-verification strict check
```

Không xóa verification metadata hoặc chuyển `--dependency-verification off` chỉ để Gradle upgrade pass. Nếu có artifact mới, review publisher, checksum/signature, license và source repository theo policy.

### 15.4. Plugin markers và included builds

Với external plugins qua `plugins { id(...) version ... }`, Gradle thường resolve plugin marker theo ID/version qua `pluginManagement.repositories`. Với included build plugin ở lab, `pluginManagement.includeBuild("build-logic")` dùng source local.

Khi migration, kiểm cả hai đường:

- Local included plugin còn apply được không?
- External/plugin portal plugin còn resolve đúng version/marker không?
- Trong CI với proxy, plugin artifact dependencies tải được không?
- Các mirror/repository credentials có đang đúng roles không?

## 16. CI/CD migration: dùng Wrapper mới trong clean runner

Một pipeline kiểm tra nâng Gradle nên có:

```text
PR for Gradle upgrade
       |
       v
Review Wrapper URL/JAR/SHA + plugin diff
       |
       v
Clean checkout at exact commit
       |
       v
JDK supported for target Gradle
       |
       v
./gradlew help --warning-mode all
       |
       v
./gradlew -p build-logic test validatePlugins
       |
       v
./gradlew clean check --no-build-cache
       |
       v
Application runtime smoke + artifact check
       |
       v
IDE smoke (when applicable)
       |
       v
Required checks + reviewer approval
       |
       v
Merge; release pipeline deploys verified artifacts
```

### 16.1. Script tối thiểu cho Linux CI

Với lab ở mục 8:

```bash
set -e

./gradlew --version
./gradlew help --warning-mode all --console=plain
./gradlew -p build-logic test validatePlugins --console=plain
./gradlew clean check --no-build-cache --no-configuration-cache --console=plain
./gradlew run --quiet
```

Dòng app phải là `migration-lab=OK; total=55`. CI không nên chỉ grep stdout rồi bỏ qua `test` exit status; script dùng `set -e` để command nonzero dừng job trên POSIX shell.

### 16.2. PowerShell trên Windows

```powershell
.\gradlew.bat --version
if ($LASTEXITCODE -ne 0) { throw "Gradle version check failed" }

.\gradlew.bat help --warning-mode all --console=plain
if ($LASTEXITCODE -ne 0) { throw "Gradle configuration failed" }

.\gradlew.bat -p build-logic test validatePlugins --console=plain
if ($LASTEXITCODE -ne 0) { throw "Build logic checks failed" }

.\gradlew.bat clean check --no-build-cache --no-configuration-cache --console=plain
if ($LASTEXITCODE -ne 0) { throw "Project verification failed" }

.\gradlew.bat run --quiet
if ($LASTEXITCODE -ne 0) { throw "Application smoke check failed" }
```

PowerShell không luôn coi native process exit nonzero là terminating exception, nên snippet kiểm `$LASTEXITCODE` tường minh.

### 16.3. CI security

- Không cấp release/deploy credentials cho untrusted pull requests.
- Xác minh Wrapper JAR, URL và distribution checksum trước khi chạy.
- Bảo vệ plugin repository credentials và secrets.
- Dùng Gradle User Home/mirror được kiểm soát.
- Không để shared remote cache nhận `PUT` từ untrusted PR.
- Chỉ publish sau required approvals.
- Review GitHub Actions/CI images/version upgrades riêng nếu cần.

### 16.4. IDE sync

Sau CI pass, kiểm:

- IntelliJ/Android Studio đang dùng **Gradle Wrapper** của project.
- Gradle JVM trong IDE đáp ứng Gradle runtime requirement.
- Toolchain JDK được IDE/Gradle detect.
- Kotlin/Android plugin versions tương thích với IDE tooling.
- Imported modules, generated sources và test configurations còn đúng.
- Không có stale IDE caches khiến task/model hiển thị sai.

Nếu CLI pass nhưng IDE sync fail, so Gradle JVM/Tooling API/plugin versions trước khi xóa caches hoặc hạ Gradle.

## 17. Artifact correctness: không đánh đổi tính đúng để nâng nhanh

Một migration có thể “xanh” giả nếu:

- `test` bị disable/`ignoreFailures=true`.
- Build script bỏ modules hoặc source sets.
- Plugin mới không đăng ký static analysis task.
- Custom task trở thành `NO-SOURCE` dù source có.
- CI chỉ chạy `assemble` thay vì `check`.
- JAR thiếu class/resource hoặc runtime dependency.
- Deployment job build lại artifact ở JDK/Gradle khác.
- Plugin publication thiếu marker/POM.
- Configuration/Build Cache trả stale outputs.

Để tránh:

### 17.1. So JAR content

Với lab:

```bash
./gradlew clean jar --no-build-cache --console=plain
jar tf build/libs/gradle-upgrade-lab-1.0.0.jar
```

Tìm:

```text
dev/learning/Totals.class
dev/learning/Main.class
```

Không giả định plain JAR có tất cả external dependencies; lab không có external main runtime dependency. Với app thật, kiểm đúng `distZip`, Shadow JAR, Boot JAR hoặc container image sẽ phát hành.

### 17.2. So runtime behavior

```bash
./gradlew run --quiet
```

Stdout:

```text
migration-lab=OK; total=55
```

Khi chuyển Gradle 8→9, Java source/logic không nên tự biến đổi, nên output này phải nhất quán. Với production, thêm API/integration tests/ABI compatibility checks, không chỉ một dòng stdout.

### 17.3. Test reports

Kiểm `build/test-results/test/` và `build/reports/tests/test/`. Nếu Gradle 9 migration làm các tests không chạy do discovery/source set, phải xem test XML số lượng. Đừng đánh đồng `BUILD SUCCESSFUL` với **đủ số tests đã chạy**.

### 17.4. Plugin output

`migrationCheck` phải tồn tại và khi chạy task phải in:

```text
build-logic-check=PASS
```

Nếu root project build xanh nhưng không còn task này, plugin có thể không được apply hoặc task graph đã thay đổi; cần sửa dù main Java code vẫn compile.

## 18. Điều tra lỗi theo lớp sau mỗi mốc upgrade

| Triệu chứng | Khả năng cao | Hướng xử lý |
| --- | --- | --- |
| Wrapper không chạy | Wrapper scripts/JAR/distribution URL | Review Wrapper diff, JAR SHA, download/checksum |
| JVM không đáp ứng Gradle 9 | Gradle daemon chạy JDK quá cũ | Dùng JDK 17+ được matrix hỗ trợ |
| `UnsupportedClassVersionError` | Build plugin/Gradle code bytecode cao hơn daemon JVM | Kiểm `./gradlew --version` và plugin target |
| `Could not compile build file` | Kotlin/Groovy DSL API bị đổi | `Where`, source line, migration guide |
| `Unknown property/method` | Removed/renamed extension/task API | Cập nhật DSL theo release notes |
| `Project.exec` không tồn tại | API bị loại ở Gradle 9 | Chuyển sang `Exec`/`JavaExec`/`ExecOperations` |
| `NoSuchMethodError` trong plugin | Binary plugin Gradle API incompatible | Nâng plugin hoặc sửa implementation |
| `Plugin not found` | Marker/ID/version/repo sai | `pluginManagement.repositories`, credentials |
| `buildSrc` compile fail | Kotlin/Groovy/Gradle API change | Kiểm plugin dependencies/buildSrc code |
| Included `build-logic` fail | Plugin source hoặc toolchain không tương thích | Chạy riêng `-p build-logic test validatePlugins` |
| `validatePlugins` fail | Task/plugin validation behavior thay đổi | Fix property annotations/toolchains |
| Test task `NO-SOURCE` bất ngờ | Test discovery/source sets thay đổi | Kiểm JUnit engine, test dirs/reports |
| Configuration Cache problem | Plugin giữ state không hỗ trợ | Đọc problems report; sửa API usage |
| Cache-hit nhưng output sai | Task input tracking/caching problem | Rebuild `--no-build-cache`, sửa inputs |
| Gradle Daemon biến mất | JVM/OOM/crash/CI resource limits | Daemon logs, JDK, heap/worker settings |
| IDE sync fail, CLI pass | IDE Gradle JVM/Tooling API khác | Cập nhật IDE settings và compatibility |
| Dependencies đổi bất ngờ | Plugin/transitive graph/version policy | Lockfiles, `dependencyInsight` |
| Gradle 9 chạy nhưng Android build fail | AGP/KGP support mismatch | Xem official compatibility matrix |
| Kotlin DSL plugin build được nhưng consumer cũ fail | Kotlin metadata minimum Gradle version | TestKit matrix/compatibility policy |
| Build nhanh hơn nhưng lint biến mất | Task graph/quality gate đổi | So `tasks --all` và CI required checks |
| JAR content thay đổi | Packaging/reproducibility/compile API | So entries/runtime tests |
| Upgrade QA pass nhưng publish fail | Maven marker/publication changed | Test staging publication/consumer resolution |

### 18.1. Chẩn đoán trong thứ tự hợp lý

1. Xem full `What went wrong` và `--stacktrace`.
2. Đọc Gradle/JDK/Wrapper version thực sự.
3. Xác định lỗi ở Wrapper, settings, plugin resolution, build logic, task hay app runtime.
4. Đối chiếu deprecations/removed APIs tại đúng migration hop.
5. Kiểm plugin changelog và support matrix.
6. Thử task nhỏ trước: `help`, `build-logic:compileJava`, `test`.
7. Chạy full gate ở clean checkout.
8. Ghi lại thay đổi đã sửa, không đổi năm thứ cùng lúc.
9. Nếu test/artifact correctness regress, rollback checkpoint.
10. Chỉ tiếp tục mốc Gradle kế tiếp khi cả gate đang xét đã pass.

## 19. Checklist nâng từ 8.x sang 9.x

### 19.1. Trước nâng

- [ ] Có Git branch/tag rollback và baseline commit.
- [ ] Xác nhận Wrapper version/JAR checksum.
- [ ] Xác nhận Gradle Daemon JVM sẽ đạt yêu cầu 17+.
- [ ] Inventory Java toolchain/test runtime riêng.
- [ ] Run `help --warning-mode all` trên version cũ.
- [ ] Ghi mọi deprecation kèm file/line/plugin.
- [ ] Inventory KGP/AGP/third-party Gradle plugins và support ranges.
- [ ] Inventory `buildSrc`, included builds, precompiled script plugins.
- [ ] Required unit/integration/quality gates hiện đang pass.
- [ ] Ghi artifact/runtime/public API contract.
- [ ] Kiểm dependencies locks/verification metadata.
- [ ] Xem migration guide của từng version liên quan.

### 19.2. Khi nâng Wrapper và plugins

- [ ] Nâng plugins cần hỗ trợ Gradle target.
- [ ] Sửa deprecated/removed APIs ở root build scripts.
- [ ] Sửa `buildSrc`/`build-logic` theo compiler/Gradle API mới.
- [ ] Chạy `:wrapper` với target version và checksum đúng.
- [ ] Chạy `:wrapper` lần hai nếu cần update scripts/JAR đồng bộ.
- [ ] Validate `gradle-wrapper.jar` với official hashes.
- [ ] Check `distributionUrl` và `distributionSha256Sum` phù hợp.
- [ ] Review Git diff; không xóa Wrapper JAR.
- [ ] Chạy `--version` bằng Wrapper vừa nâng.
- [ ] Không bật mặc định experimental features chưa kiểm.

### 19.3. Sau mỗi bước

- [ ] `help --warning-mode all` thành công.
- [ ] Build-logic compile/TestKit tests pass.
- [ ] `validatePlugins` pass nếu plugin project có task.
- [ ] Root `clean check` pass.
- [ ] JUnit tests thực sự được discover và chạy.
- [ ] App runtime smoke output đúng.
- [ ] JAR/distribution vẫn chứa files/entrypoints cần.
- [ ] Dependency graph/locks đã review.
- [ ] Không có deprecation nghiêm trọng bị ignore.
- [ ] Configuration/Build Cache correctness không regress.
- [ ] CI clean runner và IDE sync pass.
- [ ] Release job không sử dụng unreviewed credentials/plugins.
- [ ] Nếu còn failure, chưa nâng tiếp hoặc merge.

## 20. Những ngộ nhận phổ biến

**Ngộ nhận 1: “Đổi `distributionUrl` là xong Gradle migration.”** Không; cần đồng bộ Wrapper files, kiểm runtime, plugins, build logic, tests và artifacts.

**Ngộ nhận 2: “Nâng Java toolchain lên 17 đồng nghĩa Gradle Daemon đã chạy Java 17.”** Không; phải xem Gradle runtime JVM thực tế.

**Ngộ nhận 3: “`help` pass nghĩa là `check` pass.”** Không; `help` chủ yếu thử configuration, không chạy compile/test/package.

**Ngộ nhận 4: “Plugin compile được là mọi consumer Gradle version dùng được.”** Không; API, Kotlin metadata và Gradle runtime matrix khác nhau.

**Ngộ nhận 5: “`buildSrc`/`build-logic` không thuộc phạm vi nâng Gradle.”** Sai; chúng được Gradle build và plugin code chạy trong Gradle.

**Ngộ nhận 6: “Có version catalog thì plugin tương thích với Wrapper.”** Không; catalog chỉ quản lý version references.

**Ngộ nhận 7: “`--refresh-dependencies` sửa được removed Gradle APIs.”** Không; phải sửa build logic hoặc nâng plugin.

**Ngộ nhận 8: “Tắt test/analysis task là tối ưu hợp lệ khi migration gấp.”** Không; làm mất verification scope.

**Ngộ nhận 9: “Wrapper JAR chỉ là binary phụ, có thể không commit.”** Sai trong workflow Wrapper chuẩn; nó cần được commit và verify.

**Ngộ nhận 10: “`distributionSha256Sum` tự kiểm Wrapper JAR.”** Không; đó là checksum cho Gradle distribution ZIP, phải kiểm JAR riêng.

**Ngộ nhận 11: “Hai lần chạy Wrapper task luôn có cùng thay đổi.”** Lần đầu thường cập nhật properties, lần sau có thể cập nhật scripts/JAR.

**Ngộ nhận 12: “Gradle 9 tự đổi JDK bytecode target của app về Java 17.”** Không; Java toolchain/target của app được cấu hình riêng.

**Ngộ nhận 13: “Mọi deprecation trong 9.x đã bị removed ngay.”** Không; phải xem đúng migration/version notes.

**Ngộ nhận 14: “IDE Run hoạt động chứng minh CI Wrapper check pass.”** Không; IDE có thể dùng Gradle JVM/model khác hoặc compiled outputs cũ.

**Ngộ nhận 15: “Một clean build xanh chứng minh plugin public hỗ trợ mọi Gradle 8/9.”** Không; cần TestKit/consumer version matrix.

**Ngộ nhận 16: “Nếu code compile mà test task không chạy thì đã pass.”** Không; `NO-SOURCE` hoặc 0 tests phải được điều tra khi expected tests tồn tại.

## 21. Bài tập thực hành

**Bài tập A — inventory.** Trên một Gradle project của bạn, ghi chính xác Wrapper version, Gradle Daemon JVM, application toolchain và plugin versions. Vì sao phải tách ba trục này?

**Bài tập B — deprecations.** Chạy `./gradlew help --warning-mode all` và phân loại các warnings theo root script, third-party plugin, buildSrc/build-logic.

**Bài tập C — Wrapper files.** Liệt kê bốn Wrapper files và giải thích file nào chịu trách nhiệm phân phối Gradle, file nào là Java bootstrap code.

**Bài tập D — checksum.** So hash thật của `gradle-wrapper.jar` với official release checksums; phân biệt kiểm JAR với `distributionSha256Sum` cho ZIP.

**Bài tập E — chạy Wrapper hai lần.** Trong lab disposable branch, nâng một phiên bản có hỗ trợ, quan sát Git diff sau lần một và lần hai. Vì sao cần kiểm toàn bộ Wrapper files?

**Bài tập F — Java 17 lab.** Tạo đầy đủ root và `build-logic` theo mục 8; chạy `clean check`, `build-logic:test validatePlugins`, `run --quiet`; xác nhận hai dòng output đặc trưng.

**Bài tập G — migration matrix.** Lần lượt kiểm trên 8.14.6 và 9.0.0 với cùng lab/source. Ghi tests thực chạy, runtime output, deprecations và plugin validation.

**Bài tập H — plugin incompatibility.** Trên bản sao build logic, thử dùng một API Gradle đã bị removed. Đọc lỗi compile/runtime ở target Gradle và thay bằng public API mới.

**Bài tập I — `Project.exec`.** Tìm legacy usage và chuyển task sang `Exec`/`JavaExec` hoặc injected `ExecOperations`; kiểm chức năng và không gọi process trong configuration phase.

**Bài tập J — Kotlin DSL delegates.** Chuyển một dạng `by tasks.registering` sang `tasks.register` explicit API. Nêu lý do Gradle 9.x phát cảnh báo hướng tới 10.

**Bài tập K — KGP/AGP.** Lập bảng Gradle/JDK/Kotlin/AGP support cho một project Android hoặc Kotlin thực, dựa vào release notes chính thức trước khi đổi Wrapper.

**Bài tập L — precompiled convention.** Tạo một precompiled script plugin hoặc binary plugin thử nghiệm; kiểm compile/apply trong root và một included build khác.

**Bài tập M — TestKit versions.** Dùng `withGradleVersion(...)` trong functional tests để thử plugin trên nhiều versions được hỗ trợ. Vì sao producer Gradle version và consumer version không đồng nhất?

**Bài tập N — duplicate plugin versions.** Giả sử root `plugins` ghi một version nhưng included `buildSrc`/`build-logic` dùng version khác. Kiểm nơi version được khai báo, classpath conflict và migration plan.

**Bài tập O — test discovery.** Cố ý làm test source path sai trong bản sao. Vì sao `BUILD SUCCESSFUL` mà `test NO-SOURCE` không đáp ứng QA?

**Bài tập P — CI.** Viết job có clean checkout, JDK được pin, Wrapper validation, `help --warning-mode all`, build-logic tests, root `check` và app smoke test.

**Bài tập Q — Configuration Cache.** Bật cache sau khi Gradle upgrade đã pass; xử lý problems report và so kết quả lần reuse.

**Bài tập R — rollback.** Nếu Gradle 9.x lỗi với plugin chưa hỗ trợ, mô tả cách quay lại checkpoint version và giữ artifact production được test trước đó.

**Bài tập S — dependency security.** Khi plugin update làm verification metadata đổi, nêu quy trình review artifacts/hashes thay vì tắt strict verification.

**Bài tập T — artifact consistency.** So JAR entries, test XML, runtime output và dependency graph trước/sau nâng Gradle; khi nào nên reject migration dù build báo success?

### Câu hỏi tự kiểm tra

1. Gradle Wrapper khác Gradle đã cài trên hệ thống như thế nào?
2. Vì sao Gradle 9 cần JVM 17+ trong khi Java application có thể target version khác?
3. `./gradlew --version` cho biết điều gì mà `java.toolchain` không cho biết?
4. `javaToolchains` giúp kiểm tra gì?
5. Vì sao chạy `help --warning-mode all` trước nâng là hữu ích?
6. Build Scan có thể hiển thị deprecation info chi tiết hơn console không?
7. Tại sao phải sửa deprecations trong Gradle version cũ khi có thể?
8. Vì sao nên update third-party plugins trước khi đổi Wrapper major?
9. Tại sao `buildSrc`/`build-logic` cũng cần tests?
10. Precompiled script plugin khác binary plugin ở đâu?
11. `pluginManagement.includeBuild` có vai trò gì?
12. Plugin Java Gradle development plugin hỗ trợ tạo những metadata nào?
13. Vì sao `tasks.register` được ưa hơn eager creation?
14. `Project.exec` bị loại ở Gradle 9 thì thay bằng API nào?
15. `WriteProperties.outputFile` được thay bởi gì?
16. Kotlin DSL delegates trong 9.x có nguy cơ gì khi lên Gradle 10?
17. Gradle 9.0 dùng Kotlin DSL language version nào?
18. Plugin Kotlin DSL build bằng Gradle 9 cần consumer Gradle tối thiểu nào?
19. Kotlin Gradle Plugin và embedded Kotlin khác nhau ra sao?
20. Vì sao phải xem riêng AGP compatibility matrix khi nâng Android build?
21. Tại sao version catalog không tự bảo đảm plugin compatibility?
22. Distribution checksum khác Wrapper JAR checksum thế nào?
23. Vì sao không chạy unverified Wrapper từ untrusted checkout?
24. Vì sao chạy `:wrapper` hai lần khi muốn đồng bộ đầy đủ?
25. `distributionUrl` Gradle 9.x có nên pin X.Y.Z không?
26. `--refresh-dependencies` có khắc phục classloader binary incompatibility không?
27. `test NO-SOURCE` trong project có tests báo hiệu điều gì?
28. Vì sao root `check` không tự chạy test ở mọi included build?
29. `--no-build-cache` và `--no-configuration-cache` giúp cô lập điều gì?
30. Một lỗi chỉ xuất hiện trên IDE nhưng CLI pass cần kiểm trục version nào?
31. Vì sao phải giữ artifact/runtime contract khi đổi Gradle?
32. Trạng thái nào cho phép tiếp tục nâng sang mốc Gradle kế tiếp?

## 22. Tài liệu tham khảo chính thức

- [Gradle — Upgrading within Gradle 9.x.y](https://docs.gradle.org/current/userguide/upgrading_version_9.html)
- [Gradle — Upgrading to Gradle 9.0.0](https://docs.gradle.org/current/userguide/upgrading_major_version_9.html)
- [Gradle — Gradle Wrapper and Upgrading](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html)
- [Gradle — Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html)
- [Gradle — Gradle Plugin Development Plugin](https://docs.gradle.org/current/userguide/java_gradle_plugin.html)
- [Gradle — Testing Plugins with TestKit](https://docs.gradle.org/current/userguide/test_kit.html)
- [Gradle — Logging](https://docs.gradle.org/current/userguide/logging.html)
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Gradle — Securing Dependencies](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Gradle — Troubleshooting](https://docs.gradle.org/current/userguide/troubleshooting.html)

**Ghi nhớ:** Nâng Gradle nên được tiến hành theo **các mốc có thể rollback**: chụp baseline, sửa deprecations, kiểm compatibility của plugins, cập nhật và xác minh Wrapper (JAR/ZIP/scripts), kiểm Gradle JVM khác Java toolchain, chạy tests của cả application lẫn `buildSrc`/`build-logic`, kiểm artifacts và clean CI, rồi mới chốt. `./gradlew --version` thành công chỉ là điểm khởi đầu; một migration thành công phải chứng minh **build logic và sản phẩm vẫn đúng** sau từng lần nâng.