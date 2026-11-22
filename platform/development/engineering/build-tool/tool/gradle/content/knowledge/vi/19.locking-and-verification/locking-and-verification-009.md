# Kiểm tra tính tái lập qua môi trường sạch và build độc lập trong Gradle

## 1. Tại sao một lần build thành công chưa chứng minh tính tái lập?

Một lần chạy `./gradlew build` thành công trên máy developer chưa đủ để kết luận dự án có thể build lại một cách đáng tin cậy. Máy đó có thể chứa dependency đã tải từ lâu, file sinh ra chưa được khai báo, secret trong `~/.gradle/gradle.properties`, toolchain khác CI, task output còn sót, môi trường hệ điều hành đặc biệt, hoặc remote Build Cache đang cung cấp artifact cũ.

**Build tái lập (reproducible build)** có nghĩa là từ **cùng nguồn và cùng bộ đầu vào được xác định**, hai lần build trong những môi trường được kiểm soát có thể tạo ra output **giống hệt ở mức byte**, chẳng hạn file JAR có SHA-256 giống nhau. Khả năng tái lập cần phân biệt với:

- **Build thành công:** kết thúc mà không có lỗi. Hai lần thành công vẫn có thể cho JAR khác bytes.
- **Build có thể lặp lại (repeatable):** chạy lại trong cùng môi trường cho kết quả dự đoán được, nhưng chưa chắc tái lập trên máy khác.
- **Build sạch (clean build):** xoá output build và chạy lại. `clean` không đồng nghĩa môi trường độc lập.
- **Build độc lập (independent build):** lấy cùng revision trong workspace khác, hạn chế dùng state của lần build trước.
- **Hermetic build:** mọi đầu vào cần thiết được khai báo/kiểm soát, hạn chế phụ thuộc trạng thái ngoài sandbox. Gradle không tự làm mọi plugin/task trở nên hermetic.
- **Dependency verification:** xác minh checksum/chữ ký của dependency tải về; khác kiểm tra byte-for-byte output do chính ta build.

Ví dụ những tình huống làm sai kết luận:

1. Hai lần `build` đều báo `UP-TO-DATE` vì không thực thi lại task nào.
2. Lệnh `clean build` tạo JAR giống nhau nhờ một remote cache, dù local compiler thực tế có bug/nondeterminism.
3. Lần đầu có `~/.gradle/caches` với JAR không còn được repository cung cấp, lần thứ hai trên runner mới không tải được.
4. Cùng source, task tự ghi thời gian hiện tại hoặc UUID vào manifest, làm hash mỗi JAR khác nhau.
5. JDK 17 trên máy A và JDK 21 trên máy B biên dịch cùng source nhưng tạo bytecode khác nhau.

Mục tiêu là tạo **bằng chứng có thể kiểm tra**, không chỉ nhìn status BUILD SUCCESSFUL.

## 2. Xác định chính xác điều cần tái lập

Không nên bắt đầu bằng câu “mọi thứ phải giống nhau” nếu chưa xác định sản phẩm và ranh giới so sánh.

| Cấp độ | Câu hỏi kiểm tra | Bằng chứng |
| --- | --- | --- |
| **Dependency graph** | Cùng version modules/variants được chọn? | Lockfile, `dependencies`/`dependencyInsight` |
| **Integrity đầu vào** | JAR/plugin đã tải có đúng bytes được tin cậy? | Dependency Verification, trusted checksums/signatures |
| **Task execution** | Task có thực sự chạy trong lượt kiểm tra? | Gradle task outcome/log; tắt output cache và rerun khi cần |
| **Artifact bytes** | Hai JAR/ZIP/WAR có byte-for-byte giống nhau? | So sánh binary trực tiếp hoặc SHA-256 |
| **Hành vi** | Chương trình/test cho kết quả đúng? | Test, integration test, exact stdout trong demo |
| **Môi trường khác** | Clone độc lập, User Home riêng có build được không? | CI run logs và output hashes của hai phiên |
| **Build phát hành** | Artifact được publish tương ứng đúng source/tag? | So sánh hash với release artifact do pipeline tin cậy lưu |

Trong bài này, phép kiểm tra chính là **hai checkout khác nhau của cùng một commit, dùng hai Gradle User Home khác nhau, không dùng Build Cache, chạy task tạo JAR và so sánh byte-for-byte**.

Nếu cùng SHA-256, đó là bằng chứng mạnh rằng **hai artifact quan sát được có cùng bytes**. Nó không tự chứng minh mọi máy/OS/JDK hoặc mọi thời điểm đều tái lập, và cũng không tự chứng minh source và dependencies không chứa mã độc. Phạm vi kiểm tra phải được ghi cùng báo cáo.

## 3. Môi trường sạch có nhiều tầng

Một lệnh `./gradlew clean` chỉ làm sạch một phần trạng thái. Các tầng khác nhau:

| Tầng | Ví dụ trạng thái | Làm sạch/cô lập bằng cách nào? |
| --- | --- | --- |
| Output của project | `build/`, compiled classes, generated resources | `clean` (khi plugin cung cấp) và checkout mới |
| File sinh ngoài output chuẩn | File plugin ghi vào `src/`, project root, temp tùy ý | Sửa task; dùng workspace mới và kiểm tra diff |
| Gradle User Home | `~/.gradle/caches`, wrapper distributions, daemon metadata, `gradle.properties` | Dùng `GRADLE_USER_HOME` khác nhau |
| Build Cache | Task outputs cached local/remote | `--no-build-cache` trong phép đo |
| Configuration Cache | `.gradle/configuration-cache` và cấu hình được reuse | `--no-configuration-cache`; checkout mới |
| JDK/toolchain | Java compiler, libraries của JDK, JVM | Dùng Java toolchain và kiểm soát vendor/patch khi cần |
| Dependency repositories | Dynamic versions, snapshots, metadata thay đổi | Dependency locking, verification, trusted mirror |
| OS/filesystem | File modes, order, case-sensitivity, locale, timezone | Container/runner image được pin, normalized outputs |
| Git metadata | Commit/tag, dirty tree, submodules, Git LFS | Build từ commit SHA đã xác nhận và fetch đầy đủ |
| Environment/secrets | `HOME`, `TZ`, `LANG`, tokens, proxy/CI variables | Chỉ cấp inputs thực sự cần, tránh ghi chúng vào output |

**`GRADLE_USER_HOME` không phải `project/.gradle`.** User Home mặc định thường là `~/.gradle` hoặc user profile trên Windows. Nó chứa caches, init scripts, Gradle properties, wrapper downloads và có thể cả credentials. Nếu dùng hai checkout nhưng chung User Home, bạn chưa cô lập được mọi trạng thái Gradle.

### 3.1. clean, --rerun-tasks và --no-build-cache khác nhau

- `clean` là **task** (thường do base/Java plugin cung cấp), dọn output build mà plugin quản lý. Nó không xóa toàn bộ Gradle User Home hay dependency cache.
- `--rerun-tasks` yêu cầu Gradle chạy lại các task được chọn, bỏ qua kiểm tra up-to-date thông thường; không có nghĩa đã xóa local/remote caches, source không được khai báo hoặc mọi thứ ngoài Gradle.
- `--no-build-cache` không dùng Build Cache để phục hồi task outputs trong lượt chạy. Nó **không tắt dependency artifact cache**.
- `--no-configuration-cache` tránh reuse configuration state trong lượt đo; hữu ích để giảm state ẩn, không phải điều kiện chung cho mọi build production.
- `--offline` cấm Gradle lấy dependency mới qua network và dùng những thứ đã cache; **không phải** phép kiểm tra môi trường trống nếu cache cũng trống.
- `--refresh-dependencies` kiểm tra lại trạng thái dependency cache/metadata theo cơ chế Gradle; **không** tương đương xóa mọi cache và không tự chữa output không deterministic.

Vì thế, một phép thử clean-room phải **kết hợp** checkout độc lập + Gradle User Home riêng + tắt output cache + cùng toolchain + kiểm tra artifact, không trông chờ một cờ đơn lẻ.

## 4. Khóa những yếu tố đầu vào quan trọng

Để so sánh có ý nghĩa, hai lượt build nên cùng revision và cùng những điều kiện có ảnh hưởng thực:

1. **Git commit SHA:** không dùng cùng branch name mà cho phép branch chuyển commit giữa hai lượt. Ghi commit chính xác.
2. **Wrapper version:** commit đủ các file Wrapper cần thiết, có `distributionUrl` và checksum phù hợp.
3. **Plugin versions:** khai báo phiên bản rõ; quản lý plugin repositories có kiểm soát.
4. **Dependency graph:** tránh phiên bản dynamic/changing không kiểm soát; dùng dependency locking cho configurations cần cố định.
5. **Dependency bytes:** dùng Dependency Verification cho artifacts/plugins đáng tin.
6. **JDK/toolchain:** chỉ rõ Java major version; nếu cần byte-for-byte trên nhiều máy, cân nhắc vendor, patch-level hoặc pinned container image.
7. **OS + locale/timezone + line endings:** dùng một baseline trước khi thử cross-platform.
8. **Gradle settings:** cùng những project properties thực sự ảnh hưởng output; không cho User Home ẩn đổi behavior.
9. **Inputs của code generation:** không đọc thời gian hệ thống, random, network hoặc đường dẫn tuyệt đối nếu không được mô hình hóa.
10. **Artifact output path/name:** so sánh đúng JAR được tạo bởi cùng task, không so nhầm bản `sources`/`javadoc`/`plain` hay bản cũ.

**Cảnh báo:** chỉ “pin Java 17” chưa chắc bảo đảm byte-for-byte trên mọi JDK 17: vendor và patch release có thể khác compiler/zip behavior. Với release builds cần chuẩn tái lập chặt, dùng một **container image digest** hoặc toolchain installation được quản lý và ghi lại version/vendor/build cụ thể.

## 5. Gradle Wrapper: bảo đảm cùng công cụ build

Hãy chạy bằng Wrapper của dự án:

~~~bash
./gradlew --version
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat --version
~~~

Các file nên được commit theo chính sách dự án:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
~~~

`gradle-wrapper.properties` chứa `distributionUrl` pin một Gradle distribution nhất định. Thuộc tính `distributionSha256Sum` hỗ trợ xác minh SHA-256 bản phân phối **khi Wrapper tải bản chưa có trong cache**. Không chèn một giá trị hash bịa; lấy checksum chính thức, kiểm tra nguồn tin cậy rồi đưa vào file theo tài liệu Gradle.

**Wrapper checksum khác dependency verification:** Wrapper bảo vệ Gradle distribution download; `gradle/verification-metadata.xml` kiểm tra artifacts/plugins được Gradle dependency resolution tải theo phạm vi hỗ trợ. Một cơ chế không thay thế cơ chế kia.

Nếu hai lần build dùng hai Wrapper versions hoặc một bên gọi Gradle toàn cục `gradle build` khác version, so sánh đó không còn là phép thử cùng công cụ.

## 6. Java Toolchain, encoding, locale và bytecode

Với JVM project, Gradle cho phép chọn toolchain để compile/test mà không phụ thuộc hoàn toàn vào JDK hiện chạy Gradle.

Ví dụ **Kotlin DSL**:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

`languageVersion` yêu cầu một JDK major version. Nếu không có toolchain tương ứng hoặc cơ chế tự cung cấp toolchain chưa cấu hình, Gradle có thể thất bại thay vì tự đoán.

Đối với JavaCompile, có thể chuẩn hóa encoding và target API:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}
~~~

`options.release.set(17)` yêu cầu compiler tuân thủ Java 17 API/bytecode mục tiêu. Nó **không** tự quyết định vendor và patch version của JDK. Hai máy có javac khác vendor/patch vẫn có thể tạo bytes khác nhau trong một số trường hợp.

Một số đầu vào môi trường khác dễ làm lệch:

- `file.encoding` và encoding của source/resource.
- `LANG`, `LC_ALL`, `TZ` và default locale/timezone khi generator format ngày tháng/số.
- Line endings CRLF/LF, permissions và case-sensitivity của filesystem.
- `JAVA_HOME`/Gradle Daemon JVM so với Java toolchain thực sự biên dịch.
- Đường dẫn workspace tuyệt đối xuất hiện trong generated source, debug info, manifest hoặc report.
- Environment variables như build number, commit time, CI job ID.
- Khác biệt giữa plugin/JDK được provision từ mirror hoặc network.

**Thiết kế đúng:** task nào cần locale/timezone hoặc environment input để tạo output thì phải công bố và normalize chúng, hoặc loại hoàn toàn khỏi output nếu mục tiêu là byte-for-byte giống nhau.

## 7. Archive JAR/ZIP có các nguồn nondeterminism riêng

JAR và ZIP chứa không chỉ file content mà cả **metadata**. Hai tập compiled classes giống nhau vẫn có thể tạo hai archives khác nhau nếu:

- Entries được xếp theo thứ tự filesystem không ổn định.
- Mỗi entry giữ timestamp hiện tại.
- File/directory permissions khác nhau giữa Linux/Windows.
- Manifest ghi build time, absolute path, process ID hoặc random number.
- Custom packaging task thêm file theo thứ tự ngẫu nhiên.
- Một plugin ghi marker, generated properties hay signature khác nhau mỗi lượt.

**Thông tin quan trọng theo phiên bản:** từ **Gradle 9.0**, các `AbstractArchiveTask` (ví dụ `Jar`, `Zip`) tạo archives tái lập theo mặc định: thứ tự entries và timestamps deterministic, permissions chuẩn hóa. Với **Gradle trước 9**, nên khai báo tường minh các tùy chọn chính theo tài liệu phiên bản. Có thể đặt tường minh ngay cả trên bản mới để giữ chính sách rõ:

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Đừng vô tình **đảo lại** chính sách bằng:

~~~kotlin
// Chỉ minh họa cấu hình KHÔNG nên dùng để đạt reproducibility.
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = true
    isReproducibleFileOrder = false
}
~~~

`isPreserveFileTimestamps = true` giữ metadata thời gian gốc, có thể làm hash khác khi source copy/checkout lại. `isReproducibleFileOrder = false` có thể đưa thứ tự filesystem vào archive. Riêng Gradle 9+ còn có chính sách file/directory permissions và tùy chọn `useFileSystemPermissions()`; nếu bạn bật preserve permissions, bytes archive lại có thể phụ thuộc OS/filesystem. Khi thật sự cần customize timestamp, Gradle hiện đại còn có `reproducibleFileTimestamp` và có thể liên kết với `SOURCE_DATE_EPOCH` theo hợp đồng phù hợp.

Các cờ trên **không sửa** sự thay đổi của bytes file nguồn, generated code, compiler output hoặc plugin ghi dữ liệu khác nhau vào manifest. Do đó phải kiểm tra **cả nội dung và metadata archive** nếu hash vẫn lệch.

## 8. Demo hoàn chỉnh: JAR Java 17 tái lập được trong hai checkout

Ví dụ này không dùng thư viện ngoài JDK và không tải plugin bên thứ ba. Nó giúp tách vấn đề reproducibility của **bản build** khỏi vấn đề version selection của Maven dependencies.

### 8.1. Cấu trúc dự án

~~~text
repro-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/main/java/demo/Main.java
~~~

Giả sử dự án đã có **Gradle Wrapper hợp lệ**, Git repository và một JDK 17 phù hợp với Gradle version. Không tự tạo một script `gradlew` rỗng; dùng Wrapper được tạo bởi Gradle và commit nó.

**`settings.gradle.kts`:**

~~~kotlin
rootProject.name = "repro-demo"
~~~

**`build.gradle.kts`:**

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    java
}

group = "example"
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

**`src/main/java/demo/Main.java`:**

~~~java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Deterministic build");
    }
}
~~~

Các file này đủ để Java plugin tạo task `jar`; không cần thêm `application` plugin. Vì mã Java dùng toàn bộ API của JDK, bản demo không cần Maven repository cho dependencies của ứng dụng (nhưng **Wrapper distribution** vẫn phải có sẵn hoặc tải được từ nguồn hợp lệ).

### 8.2. Chạy một lượt và xem artifact

Linux/macOS:

~~~bash
./gradlew clean jar --no-build-cache --no-configuration-cache --rerun-tasks
java -cp build/libs/repro-demo-1.0.0.jar demo.Main
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean jar --no-build-cache --no-configuration-cache --rerun-tasks
java -cp build/libs/repro-demo-1.0.0.jar demo.Main
~~~

Dòng **stdout do chương trình Java in**:

~~~text
Deterministic build
~~~

`jar` tạo file thường nằm tại `build/libs/repro-demo-1.0.0.jar` khi giữ build directory/archive naming mặc định. Console Gradle có thể in task names, warning hoặc trạng thái khác nhau; không coi toàn bộ log là output cố định. Lệnh `java -cp ... demo.Main` cho thấy JAR chạy được, nhưng muốn chứng minh tái lập còn phải **so bytes với một bản build độc lập**.

### 8.3. Tại sao mã này có khả năng tái lập?

- Không dùng thời gian hiện tại, UUID hoặc file từ home user.
- Tên project và version ổn định.
- Java toolchain yêu cầu JDK 17.
- Encoding và `--release 17` được cấu hình rõ.
- JAR entries được sắp xếp deterministic và bỏ timestamps nguồn.
- Code và resources không phụ thuộc network hay người dùng.
- Không có dependencies bên ngoài cần chọn dynamic version.

Đây là **bước khởi đầu tốt**, không bảo đảm mọi hệ điều hành/JDK vendor/Gradle plugin đều tạo bytes y hệt. Thực nghiệm hai checkout và kiểm soát toolchain vẫn cần thiết.

## 9. Thử nghiệm độc lập trên Linux/macOS: hai clones và hai Gradle User Homes

Để chạy bài demo, bạn phải **commit các file nguồn/Wrapper trước**. Nếu source còn thay đổi chưa commit, hai clones có thể thiếu các thay đổi đó. Lệnh dưới đây dùng repository hiện tại và commit `HEAD`, tạo hai checkout ở hai directory mới, mỗi checkout dùng **Gradle User Home riêng**.

Chạy từ bên trong repository đã commit:

~~~bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
REVISION="$(git -C "$ROOT" rev-parse HEAD)"
BASE="$(mktemp -d)"

echo "Testing commit: $REVISION"
echo "Independent workspace: $BASE"

git clone --no-local "$ROOT" "$BASE/run-a"
git clone --no-local "$ROOT" "$BASE/run-b"

git -C "$BASE/run-a" checkout --detach "$REVISION"
git -C "$BASE/run-b" checkout --detach "$REVISION"

(
    cd "$BASE/run-a"
    GRADLE_USER_HOME="$BASE/gradle-home-a" \
        ./gradlew clean jar --no-build-cache --no-configuration-cache --rerun-tasks
)

(
    cd "$BASE/run-b"
    GRADLE_USER_HOME="$BASE/gradle-home-b" \
        ./gradlew clean jar --no-build-cache --no-configuration-cache --rerun-tasks
)

ARTIFACT_A="$BASE/run-a/build/libs/repro-demo-1.0.0.jar"
ARTIFACT_B="$BASE/run-b/build/libs/repro-demo-1.0.0.jar"

sha256sum "$ARTIFACT_A" "$ARTIFACT_B"

if cmp -s "$ARTIFACT_A" "$ARTIFACT_B"; then
    echo "MATCH"
else
    echo "MISMATCH"
    exit 1
fi
~~~

**Đây là một bash script runnable** trên hệ thống có `git`, `mktemp`, `sha256sum`, `cmp`, JDK và Wrapper hợp lệ. Trên macOS, `sha256sum` có thể không được cài sẵn; có thể dùng `shasum -a 256` hoặc `openssl dgst -sha256` theo công cụ máy có.

Nếu artifact byte-for-byte giống nhau, dòng **do nhánh kiểm tra cuối in** là:

~~~text
MATCH
~~~

Trước đó sẽ có logs Git/Gradle và hai dòng hash không thể đoán trước, không nên coi toàn bộ stdout có một format cố định. Nếu khác bytes, script in `MISMATCH` và trả exit code 1. **Không bao giờ khẳng định sẽ luôn MATCH trên bất kỳ máy nào**: JDK vendor/patch, file modes, plugins, repo policy hoặc các inputs khác có thể ảnh hưởng.

### 9.1. Vì sao cần hai đường dẫn riêng?

Đường dẫn `run-a` và `run-b` khác nhau. Nếu build nhúng absolute workspace path vào JAR, phép thử này dễ phát hiện sự khác biệt. Dùng cùng một checkout rồi chỉ chạy `clean jar` hai lần **không bắt được mọi vấn đề path-dependent hoặc state ẩn**.

### 9.2. Vì sao cần hai GRADLE_USER_HOME?

Mỗi lượt dùng directory `gradle-home-a`/`gradle-home-b` trống ban đầu. Điều đó giảm nguy cơ một lượt vô tình được hỗ trợ bởi dependency cache, init scripts, user-level properties hoặc Wrapper distribution state của lượt kia. Nó cũng khiến hai lượt có thể cần **tải Gradle distribution riêng**; bài thử yêu cầu network/mirror hợp lệ.

**Không copy `~/.gradle/gradle.properties` cá nhân hoặc credentials vào các User Homes mới.** Nếu build thật cần private repositories, CI phải cấp secrets đã phê duyệt qua môi trường riêng, không ghi password vào repo hoặc log.

### 9.3. “Clone” chưa chắc có mọi đầu vào

Nếu dự án dùng Git submodules, Git LFS, generated code không commit, container images, local Maven repository hoặc external service, hai clones có thể chưa tương đương. Hãy dùng cơ chế checkout đầy đủ của tổ chức (submodules/LFS) và ghi phiên bản những input ngoài Git. Không tự ý đưa binary/secret vào source chỉ để clone thuận tiện.

### 9.4. Vì sao không thử offline trong lượt đầu?

Mỗi User Home mới có dependency/distribution cache trống. `--offline` có thể thất bại ngay khi Gradle distribution hoặc dependencies chưa có; thất bại đó không nói rằng build không tái lập, mà nói cache chưa đủ. Phép thử nguồn sạch cần mạng từ **trusted mirrors** hoặc các artifacts đã được provision một cách kiểm chứng trước, có kiểm soát đầy đủ.

## 10. Thử nghiệm tương đương trên Windows PowerShell

Với dự án demo được commit, đây là một script PowerShell 5+ để clone hai lần vào temp directory, dùng hai Gradle User Homes và so sánh hash.

~~~powershell
$root = (git rev-parse --show-toplevel).Trim()
$revision = (git -C $root rev-parse HEAD).Trim()
$base = Join-Path $env:TEMP ("gradle-repro-" + [guid]::NewGuid().ToString("N"))

New-Item -ItemType Directory -Path $base -Force | Out-Null

$a = Join-Path $base "run-a"
$b = Join-Path $base "run-b"
$homeA = Join-Path $base "gradle-home-a"
$homeB = Join-Path $base "gradle-home-b"

git clone --no-local $root $a
git clone --no-local $root $b
git -C $a checkout --detach $revision
git -C $b checkout --detach $revision

Push-Location $a
try {
    $env:GRADLE_USER_HOME = $homeA
    & .\gradlew.bat clean jar --no-build-cache --no-configuration-cache --rerun-tasks
    if ($LASTEXITCODE -ne 0) { throw "Build A failed" }
}
finally {
    Pop-Location
}

Push-Location $b
try {
    $env:GRADLE_USER_HOME = $homeB
    & .\gradlew.bat clean jar --no-build-cache --no-configuration-cache --rerun-tasks
    if ($LASTEXITCODE -ne 0) { throw "Build B failed" }
}
finally {
    Pop-Location
}

$jarA = Join-Path $a "build/libs/repro-demo-1.0.0.jar"
$jarB = Join-Path $b "build/libs/repro-demo-1.0.0.jar"

$hashA = (Get-FileHash -Algorithm SHA256 $jarA).Hash
$hashB = (Get-FileHash -Algorithm SHA256 $jarB).Hash

if ($hashA -eq $hashB) {
    Write-Output "MATCH"
}
else {
    Write-Output "MISMATCH"
    throw "JAR SHA-256 differs"
}
~~~

Nếu hai files có hash giống nhau, dòng do kiểm tra cuối in `MATCH`. PowerShell có thể hiển thị thêm logs Git và Gradle. Lệnh `Get-FileHash` là công cụ built-in dùng để so SHA-256 trên Windows; script không giả định giá trị hash cụ thể.

**Giới hạn của script minh họa:** khi chạy shell đang dùng secrets hoặc nhiều công việc khác, biến `$env:GRADLE_USER_HOME` còn giá trị của lượt B sau khi script hoàn tất. Với pipeline thật, chạy các lượt trong hai process/job riêng hoặc khôi phục giá trị biến môi trường ban đầu trong `finally`. Không chạy script build thử trong repository có local secret mà không kiểm soát cách CI/user home được tạo.

## 11. So sánh SHA-256 và kiểm tra byte-by-byte

**Mục tiêu chính:** với cùng input baseline, file JAR của hai lượt build phải có cùng bytes.

### 11.1. SHA-256 dùng để làm gì?

SHA-256 biến bytes đầu vào thành dấu vân tay 256 bit. Nếu hai bản JAR có cùng SHA-256 thì đó là bằng chứng thực tế mạnh rằng bytes giống nhau; khác hash thì chắc chắn bytes khác.

Linux/macOS (khi có tiện ích thích hợp):

~~~bash
sha256sum path/to/run-a.jar path/to/run-b.jar
~~~

macOS có thể dùng:

~~~bash
shasum -a 256 path/to/run-a.jar path/to/run-b.jar
~~~

Windows:

~~~powershell
Get-FileHash -Algorithm SHA256 path\to\run-a.jar
Get-FileHash -Algorithm SHA256 path\to\run-b.jar
~~~

Một phép so **binary trực tiếp** như `cmp -s` trên Unix trả kết quả bằng nhau/khác nhau mà không dựa trên xác suất collision của hash. Với CI, có thể dùng cả hai: hash dễ ghi vào release report, binary comparison có kết quả trực tiếp.

### 11.2. Khi hash khác, xác định khác bên trong hay metadata

Đừng sửa tất cả yếu tố cùng lúc. Hãy điều tra theo thứ tự:

1. Xác nhận hai artifacts được tạo từ cùng commit và cùng version.
2. Ghi SHA-256/size và exact path từng artifact.
3. Liệt kê entries JAR/ZIP; so tên, số lượng, thứ tự và kích thước.
4. So **timestamp/permissions/manifest** của entries.
5. Giải nén an toàn vào hai thư mục **tách biệt**, so file bytes.
6. Nếu `.class` khác, kiểm tra javac vendor/version, compiler flags, generated sources và inputs.
7. Nếu chỉ manifest khác, tìm build time, hostname, Git branch, CI build ID, random UUID.
8. Nếu generated resource khác, tìm locale/timezone, file path, environment, filesystem order.
9. Sửa **nguyên nhân** rồi chạy lại **hai builds sạch**, đừng chỉnh binary sau build để ép hash trùng mà che source nondeterminism.

Có thể dùng công cụ archive của JDK:

~~~bash
jar tf path/to/run-a.jar
jar tf path/to/run-b.jar
~~~

Lệnh `jar tf` thường liệt kê entry names, không tự hiển thị đầy đủ timestamps/permissions. Dùng công cụ ZIP inspection phù hợp khi cần metadata chi tiết. Không giải nén một archive không tin cậy bằng mã tùy tiện có path traversal.

## 12. Dependency locking: cố định phiên bản đã resolve

Một build có dependencies ngoài JDK có thể tạo artifacts khác qua hai lần nếu phiên bản trong graph thay đổi theo repository metadata:

~~~kotlin
dependencies {
    implementation("org.example:library:1.+")
}
~~~

Đoạn này chỉ là **snippet minh họa**, không khẳng định module có thật. Selector `1.+` có thể nhận bản mới được publish sau đó. Tương tự, changing modules/SNAPSHOTs có thể thay đổi bytes dù version string giữ nguyên.

**Dependency locking** ghi **resolved module versions** vào lockfile để những lượt sau chọn cùng versions khi sử dụng cùng lock state.

Ví dụ trong `build.gradle.kts` của một project Java:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau khi cấu hình locking, có thể tạo/update state cho resolvable `runtimeClasspath`:

~~~bash
./gradlew dependencies --configuration runtimeClasspath --write-locks
~~~

Gradle hiện đại thường lưu tại `gradle.lockfile`; commit các lockfiles theo chính sách repository, review diff và dùng workflow cập nhật locks khi cần nâng phiên bản.

**Hai giới hạn rất quan trọng:**

- Locking giúp cố định **version graph**, nhưng chưa chắc bảo đảm **artifact bytes** nếu repository cho phép thay đổi nội dung của cùng version hoặc source metadata không đáng tin.
- `--write-locks` là thao tác **cập nhật** lock state. Không dùng nó trong phép thử reproducibility chỉ để build “xanh” nếu mục đích là chứng minh lockfile đã có được tôn trọng. Trong CI verify, giữ lockfile từ commit và để Gradle phát hiện graph không còn tương thích.

Với multi-project build, `dependencies --configuration runtimeClasspath` chỉ kiểm tra configuration của **project mà lệnh đang chạy**. Muốn lock toàn bộ configurations liên quan, cần workflow có chủ đích cho từng module/source set hoặc task/report tương ứng.

## 13. Dependency Verification: cố định niềm tin vào artifact bytes

Lockfile nói **nên chọn phiên bản nào**; dependency verification nói **bytes/signature tải về có khớp dữ liệu tin cậy không**.

Gradle hỗ trợ `gradle/verification-metadata.xml` với checksums/signatures được quản lý. Khi metadata tin cậy yêu cầu một SHA-256, Gradle có thể từ chối artifact tải về nếu checksum không khớp.

Đây là lớp bảo vệ chống thay đổi artifact/plugin không mong đợi và rủi ro chuỗi cung ứng. Nó **không** thay cho unit tests hoặc việc so byte-by-byte giữa hai sản phẩm JAR do build sinh ra.

Để bootstrap một metadata file, Gradle có command như:

~~~bash
./gradlew --write-verification-metadata sha256 help
~~~

**Không dùng command trên trong lượt kiểm thử read-only tự động.** Nó tạo/cập nhật verification metadata và tin những bytes đang được repository cung cấp ở thời điểm bootstrap. Phải review các hashes, nguồn tải, signatures khi có, và policy của tổ chức **trước khi commit hoặc đưa vào CI**. Đừng tự động chấp nhận mọi dependency mới chỉ để Gradle không còn báo mismatch.

Những gì verification thường bao phủ gồm artifacts/plugins được dependency resolution engine quản lý. Nó không tự kiểm tra code tự download bằng `curl`, file từ secret store, network data đọc trong custom task hoặc artifact do project sinh ra. Những nguồn đó cần ranh giới tin cậy/kiểm tra riêng.

### 13.1. Wrapper checksum, verification metadata và output hash là ba lớp khác nhau

| Lớp | Bảo vệ cái gì? | Artifact liên quan |
| --- | --- | --- |
| Wrapper checksum | Bản Gradle distribution mới tải | `gradle-wrapper.properties` / `distributionSha256Sum` |
| Dependency verification | External dependencies/plugins metadata/artifacts | `gradle/verification-metadata.xml` |
| Build reproducibility comparison | Output mà project sinh ra từ source | SHA-256 hoặc binary compare của `build/libs/*.jar` |

Cả ba nên xuất hiện trong release pipeline nghiêm túc, nhưng không cơ chế nào tự thay thế cơ chế còn lại.

## 14. Build Cache: lợi ích và rủi ro khi đo tính tái lập

Gradle Build Cache giúp tái sử dụng task outputs khi input fingerprints trùng. Đây là công cụ tăng tốc rất hữu ích, nhưng trong phép thử tính tái lập ta cần phân biệt:

- **Cache output reuse:** nhận lại JAR/output đã tồn tại từ máy hay phiên build trước.
- **Fresh execution:** compiler/generator thực sự chạy lại và tạo bytes.

Hai lần nhận cùng output từ cùng một cache chỉ chứng minh cache reuse, chưa chứng minh compiler/generator tạo kết quả giống nhau ở hai môi trường độc lập.

**Phép thử cơ bản nên dùng `--no-build-cache`.** Nếu nghi một task bị skip do incremental/up-to-date, dùng checkout sạch và/hoặc `--rerun-tasks`. Khi đã có baseline thành công, có thể chạy **bài kiểm thử thứ hai với Build Cache bật** để xác minh cache correctness, nhưng không trộn kết quả này với kết luận fresh-build reproducibility.

Một task custom có input/output khai báo thiếu có thể cho ra kết quả sai khi cache hit. Cần sửa task contract: `@Input`, `@InputFiles`, `@OutputFile` và các inputs môi trường thực sự ảnh hưởng. Không đánh dấu property quan trọng là `@Internal` để làm cache hit “đẹp”.

### 14.1. Configuration Cache khác Build Cache

`--no-configuration-cache` tránh reuse trạng thái cấu hình được ghi trước đó. Tuy nhiên, một fresh checkout với project state mới cũng không thay thế việc kiểm soát Gradle User Home. Configuration Cache ảnh hưởng thời gian cấu hình, không phải nơi chuẩn để “pin” dependency versions hoặc đảm bảo artifact bytes.

## 15. Nguồn nondeterminism trong custom tasks và plugins

Thường những lỗi khó nằm trong build logic ngoài code Java:

| Nguồn | Ví dụ làm output khác nhau | Thiết kế phù hợp |
| --- | --- | --- |
| Đồng hồ | `Instant.now()` ghi vào manifest | Bỏ timestamp hoặc dùng input reproducible đã pin |
| Random/UUID | Tạo ID mới mỗi build | Dùng ID từ stable input hoặc seed được kiểm soát |
| Filesystem order | Iterate files theo thứ tự directory | Sort theo key ổn định |
| Absolute path | Ghi `projectDir.absolutePath` vào generated file | Dùng relative path chuẩn hóa |
| Locale | Format tháng/ngày theo default locale | Chọn locale xác định trong generator |
| Timezone | Sử dụng system default zone | Cấu hình zone rõ hoặc loại thời gian |
| JDK | javac vendor/patch khác | Pin toolchain/image khi cần byte-level parity |
| Resource encoding | Đọc file text theo default charset | Chỉ định UTF-8 trong compiler/generator |
| Network | Truy vấn service cập nhật liên tục | Snapshot input đáng tin, checksum/version nó |
| Git | Branch name, dirty status, commit timestamp | Dùng immutable commit metadata có chủ đích |
| Concurrency | Race giữa tasks cùng ghi output | Tách ownership, khai báo dependencies và outputs |
| ZIP/JAR | Timestamps, order, permissions không được normalize | Dùng reproducible archive settings |
| OS filesystem | Path case, symlink/mode khác | Normalize inputs, thử cross-platform riêng |
| Secrets | Đưa username/token vào manifest, report | Không nhúng secret vào public artifacts |
| Generated docs | Tool sinh “Generated at: now” | Bỏ clock hoặc định nghĩa deterministic source date |

Ví dụ **anti-pattern** (không được đưa vào cấu hình cần reproducible output):

~~~kotlin
import java.time.Instant
import org.gradle.api.tasks.bundling.Jar

tasks.named<Jar>("jar") {
    manifest {
        attributes(
            "Build-Time" to Instant.now().toString()
        )
    }
}
~~~

Đoạn này gọi `Instant.now()` khi cấu hình task và đưa giá trị khác nhau vào manifest giữa các lần chạy. Không sửa bằng cách tắt cache hoặc xóa build directory; hãy **loại bỏ metadata thời gian** nếu không cần, hoặc dùng giá trị được xác định bởi nguồn/chuỗi cung ứng có kiểm soát như commit timestamp khi policy yêu cầu.

Kể cả khi hai lần sinh ra cùng file content, **thứ tự entries** hoặc **permission bits** bên trong archive có thể tạo hash khác.

### 15.1. Source date và build metadata

Một số hệ thống sử dụng `SOURCE_DATE_EPOCH` để cung cấp **timestamp nguồn đã xác định** thay vì wall-clock time. Gradle mới hỗ trợ cấu hình `reproducibleFileTimestamp` cho archive tasks khi cần timestamp có ý nghĩa. Tuy nhiên, không phải mọi plugin hay công cụ Java tự đọc biến môi trường này, và format archive có giới hạn độ phân giải/thời gian hỗ trợ. Chỉ dùng khi hiểu đầy đủ hành vi của task/plugin và bảo đảm cùng giá trị trong cả hai lượt.

## 16. CI pipeline nên kiểm tra những gì?

Một pipeline kiểm chứng mạnh có thể tách thành hai loại job:

**Job A — build chất lượng thông thường:** checkout commit, dùng verified Wrapper, toolchain phù hợp, resolve dependencies đã khóa, chạy tests, static checks, rồi tạo artifact. Job này có thể dùng cache tăng tốc theo policy.

**Job B — reproducibility verification:** lấy **cùng commit** vào hai workspaces độc lập, hai Gradle User Homes mới (hoặc runner sạch), tắt Build Cache, build cùng task, so hashes/artifacts, công bố báo cáo không nhạy cảm. Nên chạy theo cùng container image digest hoặc một baseline JDK/OS xác định.

Sơ đồ:

~~~text
Fixed commit SHA
      |
      +---- checkout A ------ fresh Gradle Home A
      |                            |
      |                       clean jar
      |                            |
      |                      artifact A
      |
      +---- checkout B ------ fresh Gradle Home B
                                   |
                               clean jar
                                   |
                             artifact B
                                   |
                        SHA-256 / binary compare
                                   |
                            MATCH or FAIL
~~~

Chỉ khi policy yêu cầu **cross-machine reproducibility** mới mở rộng job B sang runner khác, OS khác hoặc JDK vendor khác. Nếu không giới hạn các yếu tố này, một mismatch không thể phân biệt compiler khác, filesystem khác hay source nondeterminism.

### 16.1. CI không nên vô tình dùng chung state

- Không dùng cùng thư mục build hoặc cache workspace cho hai lượt chạy đang so sánh.
- Không cho hai tasks cùng ghi một output directory.
- Không upload nguyên `GRADLE_USER_HOME` làm artifact: có thể chứa user properties, logs, init scripts và credentials.
- Nếu CI cần private repo, cấp secrets riêng đúng scope; không in password/token, không nhúng vào JAR.
- Không để build A viết file sang workspace B.
- Không dùng `--write-locks` hay bootstrap verification metadata tự động trong pha xác minh, vì chúng **thay đổi inputs** mà ta đang kiểm chứng.
- Ghi lại Gradle version, JDK vendor/version, image digest, commit SHA và artifact hashes trong báo cáo.

### 16.2. Mức đạt/chưa đạt nên tách rõ

| Kết quả | Có thể kết luận | Chưa thể kết luận |
| --- | --- | --- |
| Hai fresh builds thành công | Source đủ đầu vào để build trong hai môi trường đã thử | Bytes output bằng nhau |
| Hai JAR cùng SHA-256 | JAR bytes giống nhau trong hai lượt đó | Artifact không chứa mã độc hoặc tái lập ở mọi OS |
| Build B fail vì thiếu dependency | Môi trường B chưa có đủ artifact/quyền mạng | Build logic chắc chắn nondeterministic |
| Hash khác | Output bytes khác nhau, cần điều tra | Không thể đoán nguyên nhân chỉ từ hash |
| Cache hit cho cùng output | Cache hoạt động theo dữ liệu được ghi nhận | Compiler fresh-run luôn deterministic |
| Tests pass nhưng JAR khác | Hành vi kiểm thử đã qua trong phạm vi tests | Byte-for-byte reproducibility |

## 17. Lộ trình xử lý khi hash không khớp

Một cuộc điều tra nên tái hiện có kiểm soát thay vì đổi ngẫu nhiên các cờ Gradle.

1. **Xác nhận đầu vào Git:** `git rev-parse HEAD` giống nhau? Có file uncommitted/untracked được task đọc không?
2. **Xác nhận tools:** `./gradlew --version` và Java toolchain compiler/launcher thật; có khác vendor/patch không?
3. **Xác nhận dependency graph:** lockfiles của cả hai lượt giống và không bị cập nhật? Build có dùng SNAPSHOT/dynamic version?
4. **Xác nhận artifact:** có thực sự so hai file tương ứng từ cùng task không? Đổi tên archive có dựa vào CI build ID không?
5. **Xác nhận archive metadata:** entry order, timestamps, file permissions, manifest?
6. **Xác nhận bytes bên trong:** generated sources/resources, class files, embedded config?
7. **Xác nhận trạng thái ẩn:** remote cache, directory temp, user home properties, init scripts, local Maven repository, secrets?
8. **Xác nhận môi trường:** locale/timezone/line endings, filesystem case, network route, JDK install?
9. **Sửa một nguyên nhân**, chạy lại hai fresh builds, ghi lại hashes/traces.
10. **Thêm regression test** hoặc CI reproduction step để ngăn tái diễn.

### 17.1. Ví dụ phân loại mismatch

| Quan sát | Giả thuyết đầu tiên | Cách kiểm tra |
| --- | --- | --- |
| Các file classes giống, JAR hash khác | ZIP timestamps/order/permissions/manifest | Liệt kê archive metadata, inspect manifest |
| `.class` hash khác | javac/toolchain/generated source | Xem compiler vendor/version và bytecode diff |
| Chỉ `build-info.properties` khác | Timestamp, hostname, CI ID | Đọc file/producer task |
| Output chứa `/tmp/run-a` và `/tmp/run-b` | Absolute path leak | Tìm generator/plugin ghi đường dẫn |
| Dependency graph khác | Lockfile chưa đủ, dynamic/changing modules | `dependencyInsight`/report và locks |
| Chỉ CI B fail download | Repository auth/network hoặc secret injection khác | Xem lỗi resolution, không đánh đồng với mismatched bytes |
| Chỉ sau khi bật Build Cache mới “match” | Có thể đang reuse cùng output cache | Chạy lại với `--no-build-cache` |
| Bản thứ hai có file thừa trong archive | Task copy/generate chưa dọn output riêng | Dùng output ownership và clean checkout |
| Thay đổi permission giữa Linux/Windows | Archive preserves filesystem permissions | Normalize permissions và thử same-image baseline |
| Thời gian khác làm metadata khác | `Instant.now()` hoặc source timestamps | Bỏ clock/normalize archive entries |

**Đừng sửa bằng cách lấy một JAR của A copy sang B rồi báo MATCH.** Điều đó chỉ kiểm tra copy thành công, không chứng minh build độc lập tạo ra cùng artifact.

## 18. Các giới hạn quan trọng của phép thử

### 18.1. Hai checkout trên cùng máy chưa là hai máy độc lập

Hai clones và Gradle User Homes riêng đủ để bắt nhiều lỗi state/path, nhưng chúng vẫn dùng chung kernel, network path và JDK cài trên máy. Để đánh giá khả năng tái lập trên các môi trường độc lập thật sự, chạy trên hai runner/VM/container được pin với cùng image và toolchain policy rồi so artifacts.

### 18.2. “Không có network” khác “đủ dependency”

Một build hermetic thường muốn chỉ dùng inputs đã được provision và xác minh. Chạy `--offline` với User Home mới trống thường fail; điều đó chỉ cho biết artifacts chưa được cung cấp. Muốn kiểm thử không cần network, phải **provision dependencies đã khóa và verified** bằng cơ chế đáng tin trước khi chạy; không che giấu bằng cách copy nguyên thư mục home cá nhân có credentials.

### 18.3. Different output paths không phải luôn lỗi

Một số output sinh để debug/test có thể chứa đường dẫn, thời gian hoặc môi trường và không phải artifact phát hành. Phải xác định **tập sản phẩm cần byte-identical** và tiêu chuẩn chấp nhận. Không đánh đổi tính chính xác của log/test report chỉ để mọi file trong `build/` có cùng hash; nhưng nếu release JAR chứa path/timestamp không ổn định thì đó là vấn đề reproducibility thực sự.

### 18.4. Kết quả byte-identical không tự xác minh provenance

Hai builds tạo JAR giống nhau nhưng cả hai dùng dependency độc hại vẫn có thể cùng hash. Cần supply-chain controls riêng: trusted source, reviews, wrapper checksum, dependency verification, CI access control, artifact attestations/signing khi policy yêu cầu.

## 19. Groovy DSL tương đương cho cấu hình nền

Nếu dự án dùng `build.gradle` (Groovy DSL), các settings thiết yếu có thể viết:

~~~groovy
plugins {
    id 'java'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Đây là **file build.gradle độc lập** tương đương cấu hình Kotlin DSL của demo khi có Java plugin và các Gradle imports mặc định tương ứng. Một số DSL/API property có thể khác ở Gradle Wrapper cũ; kiểm tra tài liệu của version đang chạy. Không trộn cú pháp Groovy vào `build.gradle.kts`.

## 20. Những hiểu nhầm thường gặp

**Hiểu nhầm A — `clean build` là clean-room.** Sai: nó không tự tạo Gradle User Home rỗng, không vô hiệu hóa caches, không pin JDK, không cô lập process/OS.

**Hiểu nhầm B — BUILD SUCCESSFUL nghĩa là tái lập.** Sai: đó chỉ là thành công của lượt chạy; cần so bytes artifact.

**Hiểu nhầm C — Hai hashes khác nhau nghĩa là source Java khác.** Sai: có thể chỉ timestamps ZIP, manifest, compiler hoặc filesystem metadata.

**Hiểu nhầm D — Hai hashes giống nhau chứng minh artifact an toàn.** Sai: integrity/provenance cần trust và verification riêng.

**Hiểu nhầm E — Dependency locking bảo vệ artifact bytes.** Chưa đủ: locking chốt resolved versions, verification kiểm tra artifact bytes.

**Hiểu nhầm F — Java toolchain 17 pin JDK patch.** Không: chủ yếu chọn major/version và có thể vendor/implementation; patch/vendor cụ thể phải được quản lý thêm nếu thật sự quan trọng.

**Hiểu nhầm G — Gradle 9 đã reproducible archives nên mọi custom task tự deterministic.** Sai: nó chuẩn hóa archive metadata mặc định, không xóa nondeterminism trong generated code/network inputs/custom plugins.

**Hiểu nhầm H — `--offline` kiểm tra network đã sửa.** Sai: nó không dùng network mới, nên không có bằng chứng đó.

**Hiểu nhầm I — `--refresh-dependencies` xóa sạch mọi cache.** Sai: cơ chế refresh metadata/artifacts không phải full clean environment.

**Hiểu nhầm J — Có remote Build Cache nên không cần fresh build.** Sai: cache kiểm tra reuse, không chứng minh compiler chạy độc lập có cùng output.

## 21. Bài tập thực hành có đáp án

**Câu 1.** Hai lần `./gradlew build` đều báo `UP-TO-DATE`. Có bằng chứng byte-for-byte reproducibility không?  
**Đáp án:** chưa. Có thể cả hai không tạo lại output. Cần fresh executions và so artifact bytes.

**Câu 2.** `./gradlew clean` có xóa `~/.gradle/caches` và `gradle.properties` của người dùng không?  
**Đáp án:** không. Dùng Gradle User Home mới/cô lập nếu cần.

**Câu 3.** Vì sao phải ghi commit SHA thay vì chỉ ghi branch `main`?  
**Đáp án:** branch có thể thay commit; cùng revision bất biến mới là đầu vào có thể kiểm chứng.

**Câu 4.** Hai JAR có cùng SHA-256 có thể kết luận gì?  
**Đáp án:** hai files quan sát có bytes trùng nhau với độ tin cậy thực tế rất cao; không tự chứng minh build luôn tái lập hoặc artifact đáng tin.

**Câu 5.** `isPreserveFileTimestamps=true` có thể gây vấn đề gì?  
**Đáp án:** giữ timestamp nguồn trong entries JAR/ZIP, làm hash khác theo máy/lượt checkout.

**Câu 6.** Từ phiên bản Gradle nào archives của `AbstractArchiveTask` tái lập mặc định theo tài liệu mới?  
**Đáp án:** từ Gradle 9.0.0; build cũ cần xem policy và cấu hình tương ứng.

**Câu 7.** Chỉ đặt `java.toolchain.languageVersion=17` đã pin exact compiler chưa?  
**Đáp án:** chưa; vendor/patch và JDK distribution vẫn có thể khác.

**Câu 8.** Lockfile khác Dependency Verification như thế nào?  
**Đáp án:** lockfile quản lý versions đã resolve; verification metadata kiểm tra integrity của bytes/signatures từ nguồn tin cậy.

**Câu 9.** Một project có dependency `1.+` nhưng chưa dùng locks. Có rủi ro gì?  
**Đáp án:** resolved version có thể thay đổi theo repository metadata, khiến hai builds cùng source khác graph/output.

**Câu 10.** Phép thử mới có User Home rỗng chạy `--offline` rồi báo thiếu plugin. Có chứng minh build không reproducible không?  
**Đáp án:** chưa; inputs chưa được provision nên chưa thể làm phép thử output.

**Câu 11.** JAR hash khác nhưng class files giống. Kiểm tra gì trước?  
**Đáp án:** entry order, timestamps, permissions, manifest và các resource files trong archive.

**Câu 12.** Vì sao cần hai workspace khác đường dẫn?  
**Đáp án:** để phát hiện outputs vô tình phụ thuộc absolute paths hoặc local state nằm trong workspace.

**Câu 13.** `--no-build-cache` có xóa dependency artifacts cache không?  
**Đáp án:** không; cần User Home mới nếu muốn cô lập dependency cache.

**Câu 14.** Nên đưa ngày build hiện tại vào JAR manifest nếu muốn bit-identical?  
**Đáp án:** không, trừ khi dùng thời điểm ổn định được pin và chính sách reproducible metadata phù hợp.

**Câu 15.** Build A và B đều thành công nhưng SHA-256 khác nhau. Bước sửa đầu tiên là gì?  
**Đáp án:** điều tra có hệ thống theo commit, Gradle/JDK, dependencies, archive metadata, generated files, môi trường; không copy một artifact thay artifact kia.

**Câu 16.** Tại sao release pipeline vẫn cần tests nếu hai JAR hash giống nhau?  
**Đáp án:** reproducibility nói về tính đồng nhất của output, không bảo đảm logic chương trình đúng.

**Câu 17.** Lệnh nào so byte trực tiếp hai files trên Unix?  
**Đáp án:** `cmp -s fileA fileB`; exit code 0 nghĩa là cùng bytes.

**Câu 18.** Một nhiệm vụ cần private Maven repository; có nên copy file `~/.gradle/gradle.properties` có password vào hai workspaces để tái lập?  
**Đáp án:** không. Dùng CI secret store, quyền tối thiểu và chỉ cấp credentials vào môi trường tin cậy; không đưa chúng vào source, report hoặc artifact.

## 22. Checklist xác nhận trước khi kết luận “reproducible”

- [ ] Đã xác định output cần so sánh (JAR/ZIP/WAR hoặc artifact phát hành cụ thể)?
- [ ] Hai runs dùng **đúng cùng Git commit** và checkout đầy đủ submodules/LFS?
- [ ] Workspace A/B độc lập và không chứa outputs của lượt trước?
- [ ] `GRADLE_USER_HOME` riêng, không có init scripts/properties cá nhân ngoài hợp đồng?
- [ ] Không dùng Build Cache trong lượt kiểm tra fresh execution?
- [ ] Không dựa vào Configuration Cache/UP-TO-DATE để giả vờ build lại?
- [ ] Gradle Wrapper version và distribution checksum được xác nhận?
- [ ] Gradle daemon JDK và compiler/toolchain được xác định rõ?
- [ ] Dependency versions/graph được khóa đúng phạm vi khi có external dependencies?
- [ ] Dependency artifacts/plugins được kiểm tra bằng verification metadata/trusted source?
- [ ] Locale/timezone/encoding/OS/image digest có baseline rõ?
- [ ] Archive metadata như timestamp/order/permissions/manifest đã được chuẩn hóa?
- [ ] Generated code/resources không phụ thuộc clock/random/path/user home ngoài hợp đồng?
- [ ] Task không ghi đè outputs của task khác hoặc lấy file không khai báo?
- [ ] Có ghi SHA-256, size, exact file path và build/toolchain versions?
- [ ] So sánh bytes/outputs chứ không chỉ nhìn BUILD SUCCESSFUL?
- [ ] Khi mismatch, có báo cáo điều kiện khác nhau và nguyên nhân đã xác minh?
- [ ] Không upload credentials, nguyên User Home hoặc logs nhạy cảm làm bằng chứng?
- [ ] Có chạy tests/verification riêng, không đồng nhất reproducibility với security?
- [ ] Nếu kết luận cross-machine, đã thử trên runner/OS/JDK được định nghĩa cụ thể?

## 23. Tài liệu chính thức

- [Gradle — Working with Files: Reproducible archives](https://docs.gradle.org/current/userguide/working_with_files.html): archive order/timestamps/permissions và hành vi Gradle 9+.
- [Gradle — Best Practices for Security](https://docs.gradle.org/current/userguide/best_practices_security.html): nondeterminism, artifact verification và những lựa chọn ảnh hưởng supply-chain security.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): `distributionUrl`, `distributionSha256Sum` và quản lý distribution.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): pin compiler/toolchain, vendor và JVM lựa chọn.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): lưu/respect resolved versions để tăng khả năng tái lập.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): kiểm tra integrity/checksums/signatures của dependency artifacts.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): reuse task outputs và các giới hạn của caching.
- [Gradle — Gradle User Home](https://docs.gradle.org/current/userguide/gradle_directories.html): global configuration/caches/Wrapper distributions và User Home isolation.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): trạng thái configuration được tái sử dụng.
- [Reproducible Builds project](https://reproducible-builds.org/docs/): khái niệm byte-for-byte reproducibility, các nguồn nondeterminism.
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html): khai báo task inputs/outputs và up-to-date checks.

**Kết luận:** kiểm tra tính tái lập không phải chỉ chạy `clean` hay thấy `BUILD SUCCESSFUL`. Hãy cố định commit và công cụ, cô lập **hai checkout + hai Gradle User Homes**, không dùng output cache trong lượt đo, chạy lại đúng task, **so byte/hash của artifact**, rồi điều tra những nguồn khác biệt theo lớp. Dependency locking đảm bảo graph ổn định, verification bảo vệ bytes đầu vào, còn archive normalization và deterministic build logic giúp tạo ra output thật sự tái lập.