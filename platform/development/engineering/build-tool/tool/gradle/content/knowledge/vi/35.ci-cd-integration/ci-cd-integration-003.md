# Caching Gradle User Home với khóa, phạm vi và quyền phù hợp trong CI/CD

## 1. Mục tiêu và bối cảnh

Bài thuộc nhóm **Tích hợp CI/CD** của chủ đề **Build Tool Gradle**. Trên CI runner mới cho mỗi job, Gradle có thể phải tải lại Gradle distribution, dependencies từ Maven, plugin JARs, Kotlin DSL scripts và artifact transforms. Tải lại mọi thứ ở từng workflow run làm build chậm, tốn băng thông và gây áp lực lên repository. Vì vậy **Gradle User Home caching** là một biện pháp quan trọng để tăng tốc CI/CD.

Tuy nhiên, `~/.gradle` không chỉ chứa file cache vô hại: nó có thể chứa `gradle.properties` với mật khẩu, `init.d` với scripts được thực thi, downloaded plugin code và nội dung private Maven artifacts. Một cache “hit” nhưng được ghi từ code không tin cậy có thể gây **cache poisoning** hoặc rò rỉ dữ liệu khi privileged release job khôi phục. Do đó, một chiến lược đúng phải đồng thời giải quyết **cache key**, **cache scope**, **quyền đọc/ghi**, **file được cache**, **tính tái hiện** và **bảo mật**.

Kết thúc bài, bạn có thể:

1. Xác định `GRADLE_USER_HOME` và các thư mục đáng cache, phân biệt với `GRADLE_HOME` và project `.gradle`.
2. Thiết kế cache key theo OS, CPU architecture, JDK, Gradle Wrapper, dependency lockfiles và policy schema.
3. Phân biệt key với CI branch/repository scope và read/write authorization.
4. Dùng `gradle/actions/setup-gradle@v6` và `cache-provider: basic` đúng cách trên GitHub Actions.
5. Tách PR từ fork/read-only với trusted default-branch cache writer.
6. So sánh phương án manual `actions/cache/restore@v4` / `save@v4` và tránh double caching.
7. Thiết kế policy cho GitLab CI, Jenkins và containerized runners.
8. Hiểu `GRADLE_RO_DEP_CACHE`, locking và cách chia sẻ cache an toàn giữa containers.
9. Phân biệt dependency cache, local/remote Build Cache, Configuration Cache và task up-to-date checks.
10. Chạy một Java 17/JUnit lab, kiểm tra stdout, cache restore/save logs, network downloads và Gradle task outcomes.
11. Phòng tránh credentials leakage, untrusted cache injection, checksum bypass và shared runner contamination.
12. Chẩn đoán cache miss/hit giả, repository identity, retention, cleanup, quota, key rotation và caching trên CI ephemeral.

**Nguyên tắc:** Cache là **bản sao để tăng tốc**, không phải nguồn chân lý về dependency graph, artifact integrity hoặc quyền truy cập.

## 2. Gradle User Home là gì?

Mặc định:

~~~text
Linux/macOS:  ~/.gradle
Windows:      C:\Users\<user>\.gradle
~~~

Có thể thay đổi bằng biến môi trường:

~~~bash
export GRADLE_USER_HOME="$HOME/.gradle"
~~~

hoặc đặt riêng cho CI:

~~~bash
export GRADLE_USER_HOME="$PWD/.gradle-ci"
./gradlew test --console=plain
~~~

Trên Windows PowerShell:

~~~powershell
$env:GRADLE_USER_HOME = Join-Path (Get-Location) ".gradle-ci"
.\gradlew.bat test --console=plain
~~~

Gradle CLI còn hỗ trợ:

~~~bash
./gradlew --gradle-user-home /path/to/isolated-home test
~~~

Phân biệt rõ:

| Đường dẫn/khái niệm | Chứa gì | Có phải Gradle User Home? |
| --- | --- | --- |
| `GRADLE_USER_HOME` | Global caches, downloaded distributions, có thể có credentials/init scripts | Có |
| `GRADLE_HOME` | Thư mục cài đặt một Gradle distribution | Không |
| `<root>/.gradle` | Project-local history và Configuration Cache | Không |
| `<root>/build` | Compiled classes, test reports, JAR và generated outputs | Không |
| `~/.m2/repository` | Maven local repository | Không |
| `GRADLE_RO_DEP_CACHE` | Shared read-only dependency cache snapshot | Không; là nguồn phụ được cấu hình riêng |

Nếu action cache `$HOME/.gradle` nhưng Gradle process lại sử dụng `GRADLE_USER_HOME=/tmp/work/.gradle`, bạn có thể thấy cache restore thành công trong logs mà Gradle vẫn tải lại dependencies. **Khớp chính xác đường dẫn được restore và đường dẫn Gradle đọc**.

## 3. Những thư mục trong User Home

Cấu trúc tham khảo:

~~~text
GRADLE_USER_HOME/
├── caches/
│   ├── modules-2/          Downloaded modules/JAR/POM và metadata
│   ├── build-cache-1/      Local task-output Build Cache
│   ├── <gradle-version>/   Kotlin DSL/scripts/generated Gradle JARs
│   ├── transforms-N/       Artifact transforms (N là format)
│   └── jars-N/             Instrumented JARs (N là format)
├── wrapper/
│   └── dists/              Gradle Wrapper distributions
├── daemon/                 Daemon logs và runtime state
├── jdks/                   Java toolchains được provision khi có
├── notifications/
├── gradle.properties       Có thể chứa secret values
└── init.d/                 Initialization scripts
~~~

Tên thư mục format caches thay đổi theo Gradle version. Không viết pipeline phụ thuộc tuyệt đối vào một con số của `transforms-N` hoặc `jars-N` nếu không kiểm tra Gradle Wrapper.

### 3.1. Phần nên cache

- `caches/modules-2`: dependency artifact và metadata cache; thường là phần có tác động rõ nhất lên network downloads.
- `wrapper/dists`: tránh tải lại Gradle distribution theo Wrapper.
- Một số version-specific Kotlin DSL/script caches và artifact transforms: có thể lợi khi build nặng, nhưng cần đo dung lượng và tính portable.
- `notifications` và selected Gradle state mà action chuyên dụng biết xử lý, theo version/provider hiện hành.

### 3.2. Phần không nên đưa vào cache chia sẻ

- `gradle.properties` khi có username/password/private repository tokens.
- `init.d` chứa init scripts có thể thực thi code khi Gradle khởi chạy.
- Signing keys, keystores, SSH keys hoặc environment files chứa secrets.
- `daemon` logs, worker state, transient files, Gradle lock files.
- Tất cả project `build/` như một phần không kiểm soát của User Home cache.
- Toàn bộ `.gradle/configuration-cache` của project mà không có encryption/trust policy.
- File tùy tiện dưới home mà plugin tự tạo nhưng không rõ provenance.

**Không dùng “cache cả `~/.gradle`” làm mặc định**. Ưu tiên `gradle/actions/setup-gradle` hoặc selective directories qua action cache phù hợp.

## 4. Các lớp cache trong một Gradle CI job

| Cơ chế | Chức năng | Dấu hiệu |
| --- | --- | --- |
| Dependency Cache | Downloaded dependencies, metadata, artifact transforms | Ít Maven/JAR downloads hơn |
| Gradle distribution cache | Wrapper distribution đã tải | Không phải download Gradle ZIP mỗi run |
| Up-to-date checks | Local task inputs/outputs hợp lệ | `UP-TO-DATE` |
| Build Cache | Khôi phục task outputs theo fingerprint/cache key | `FROM-CACHE` |
| Configuration Cache | Reuse configured task graph/state | `Configuration cache entry reused` |

Phân biệt:

~~~text
Gradle User Home caching:
  -> giúp không tải lại dependencies/distribution

Build Cache:
  -> giúp không phải biên dịch hoặc tạo lại task outputs

Configuration Cache:
  -> giúp không tính lại configuration task graph

Up-to-date:
  -> giúp không thực thi task action khi outputs hiện có vẫn hợp lệ
~~~

Một CI job mới có cache User Home từ hôm trước nhưng **không** có `build/classes/java/main`, nên `compileJava` vẫn có thể chạy. Ngược lại, Build Cache remote có thể restore class outputs mà một private Maven dependency vẫn cần tải vì dependency cache thiếu. Đừng gộp các con số thành “cache hit” duy nhất.

## 5. Cache key, cache scope và permissions

Ba khái niệm độc lập:

**Cache key**: chuỗi định danh archive/entry, do workflow/action tạo.

~~~text
gradle-v2-linux-x64-jdk17-wrapperhash-lockhash
~~~

**Cache scope**: repository, branch, PR merge ref, namespace, workflow hoặc protected environment do CI platform kiểm soát. Một job có key đúng vẫn có thể bị từ chối restore nếu ở scope không được phép.

**Permissions**: quyền đọc hoặc tạo/ghi/evict cache theo actor, event type và provider rules. Không mặc định `contents: read` của GitHub token là đủ để kiểm soát toàn bộ Cache API, vì cache service có policies và tokens riêng.

~~~text
           Key match?
             |
             v
       Scope allows restore?
             |
             v
         Read allowed?
             |
             v
        Restore archive

          Trusted writer?
             |
             v
        Save allowed?
             |
             v
         Save archive
~~~

Một key prefix `main-` **không phải permission boundary**. Cần ràng buộc writer bằng workflow/event, protected branches, secret access rules và cache provider permissions.

## 6. Thiết kế cache key có chủ đích

Với manual caching, những yếu tố thường quan trọng:

1. **OS**: Linux, Windows, macOS có path/native artifact differences.
2. **Architecture**: x64, arm64 đặc biệt với native dependencies/transform artifacts.
3. **JDK vendor/major**: Temurin 17, Java 21 hoặc toolchain variants.
4. **Gradle Wrapper**: file `gradle/wrapper/gradle-wrapper.properties`.
5. **Dependency locks**: root/subproject `gradle.lockfile` khi có.
6. **Version catalog**: `gradle/libs.versions.toml` nếu dùng.
7. **Dependency verification metadata**: nếu changes ảnh hưởng policy/graph.
8. **Cache schema prefix**: `gradle-v1`, `gradle-v2` để rotate chủ động.
9. **Trust tier**: trusted base build và untrusted feature/PR entries khi cần isolate.

Ví dụ conceptual:

~~~text
gradle-v3-Linux-X64-temurin17-wrapperA-lockB
gradle-v3-Windows-X64-temurin17-wrapperA-lockB
gradle-v3-Linux-ARM64-temurin21-wrapperA-lockB
~~~

**Key quá chặt** có commit SHA mỗi run thường gây miss liên tục. **Key quá rộng** dùng chung OS/JDK/trust tiers có nguy cơ khôi phục cache không tương thích hoặc không an toàn.

### 6.1. Restore-key prefix là chiến lược fallback

Ví dụ:

~~~text
Exact:
  gradle-v3-Linux-X64-temurin17-abc123

Fallback:
  gradle-v3-Linux-X64-temurin17-
~~~

Khi exact key chưa tồn tại, action có thể tìm entry phù hợp prefix trong **scope được CI cho phép**. Gradle vẫn resolve missing dependencies. Không đặt fallback `gradle-` quá rộng nếu nó nối các OS/trust tiers khác nhau.

### 6.2. Có cần hash mọi build.gradle.kts?

Không nhất thiết. Một thay đổi nhỏ ở task description không cần xóa toàn bộ downloaded JAR cache. Cache action chuyên dụng có eviction/Gradle internal metadata logic; manual key thường nên hash những dependency/Wrapper-related files. Khi dependency graph đổi, Gradle có thể tải artifacts thiếu vào home restore từ một fallback.

### 6.3. Kết hợp architecture/version đúng mục đích

`wrapper/dists` có thể giống giữa JDK 17/21, nhưng nếu manual cache key tách JDK thì nhận trade-off giữa kích thước/logic đơn giản và hit rate. Với Gradle-specific action, tốt hơn dùng cơ chế caching nó đã triển khai thay vì tạo một key phức tạp phủ trùm toàn home.

## 7. Trust matrix cho branch và CI event

| Loại job | Cache restore | Cache save | Secrets |
| --- | --- | --- | --- |
| Protected default branch `push` | Có từ trusted namespace | **Được phép** theo policy | Least privilege |
| Trusted release | Chỉ cache đáng tin | Có thể read-only hoặc scope riêng | Release credentials có kiểm soát |
| Feature branch | Đọc default-branch cache nếu scope cho phép | Thường read-only | Không có release secrets |
| Pull request từ fork | Restore chỉ từ các scopes được phép, cân nhắc read-only | **Không được ghi trusted cache** | Không có production secrets |
| `pull_request_target` có untrusted checkout | Nên cách ly/bypass cache | Không cho chạm trusted namespace | Không chạy PR code với privileged secrets |
| Self-hosted multi-tenant runners | Theo từng tenant/job | Chỉ trusted writers | Không dùng chung credentials/home |
| Cache warming job | Đọc/ghi thuộc trusted scope | Có | Quyền tối thiểu cần cho dependency source |

**Đừng chạy Gradle code không tin cậy trong privileged workflow chỉ vì cần cache.** PR có thể sửa build scripts, plugin versions hoặc Wrapper URL: những nội dung này là executable code, không chỉ Java source an toàn.

### 7.1. Vì sao PR từ fork nguy hiểm?

Untrusted PR có thể:

1. Sửa build script để tải một plugin độc hại.
2. Chèn file vào shared Gradle cache nếu writer scope quá rộng.
3. Đợi trusted release job restore archive.
4. Khi Gradle nạp plugin/init scripts, mã độc có cơ hội đọc secrets hoặc thao túng artifacts.

Đây là **cache poisoning**. Hạn chế quyền ghi và không share caches qua trust boundaries là tuyến phòng vệ đầu tiên.

### 7.2. GitHub Actions branch scopes

GitHub Actions Cache còn có cơ chế scope theo branch/default branch/PR merge ref. Caches của `pull_request` có restrictions riêng và không đương nhiên cho phép overwrite default-branch entries. Một số low-trust triggers đến default-branch scope có write restrictions. Tuy nhiên policies có thể thay theo event/organization settings.

Vẫn nên thiết kế `cache-read-only` tường minh trong workflow và kiểm tra các event như `workflow_run`, `issue_comment`, `pull_request_target` trước khi cho phép privileged secrets.

## 8. GitHub Actions: dùng setup-gradle làm cache owner

Trên GitHub, hướng triển khai đơn giản thường là:

1. `actions/checkout` lấy source.
2. `actions/setup-java` chọn JDK nhưng không bật Gradle cache riêng.
3. `gradle/actions/setup-gradle` quản lý User Home cache và Gradle diagnostics.
4. Chạy Gradle Wrapper: `./gradlew test`.

Tài liệu hành động `setup-gradle@v6` hiện hành có `cache-provider`:

- `basic`: open-source cache provider dựa trên GitHub Actions Cache.
- `enhanced`: provider tối ưu với availability/cost model riêng.
- `external`: báo action không restore/save User Home vì external cache system đã làm.

Ví dụ dùng `basic` để không phụ thuộc nhà cung cấp caching thương mại.

### 8.1. Workflow đầy đủ: .github/workflows/gradle-ci.yml

~~~yaml
name: Gradle Java CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout sources
        uses: actions/checkout@v6

      - name: Configure JDK 17
        uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: '17'

      - name: Configure Gradle caching
        uses: gradle/actions/setup-gradle@v6
        with:
          cache-provider: basic
          cache-read-only: ${{ github.event_name != 'push' || github.ref != 'refs/heads/main' }}

      - name: Check Wrapper version
        run: ./gradlew --version

      - name: Run tests
        run: ./gradlew test --no-daemon --console=plain
~~~

**Điều kiện:** Repository có Wrapper JAR, Wrapper properties và `gradlew` executable; Gradle version hỗ trợ JDK được chọn. Thay `main` nếu default/protected branch thực tế có tên khác.

Ý nghĩa bảo mật:

- Trusted `push` vào `main` có thể **ghi cache**; PR hoặc feature branch **chỉ đọc** theo access scope.
- `permissions: contents: read` giảm quyền repo token, nhưng **không tự thay** CI cache write restrictions.
- Job không được cấp signing/Maven publish secrets.
- Gradle Wrapper pin Gradle version mà project yêu cầu, thay vì chọn bản Gradle tùy ý trên runner.
- `--no-daemon` có thể thích hợp job ngắn, nhưng **không phải điều kiện của cache hit**.

### 8.2. Không tạo double caching

Không thêm vào cùng job:

~~~yaml
- uses: actions/setup-java@v5
  with:
    distribution: temurin
    java-version: '17'
    cache: gradle
~~~

khi đã dùng `gradle/actions/setup-gradle`. Cũng không dùng một `actions/cache@v4` khác restore/save `$HOME/.gradle` trong cùng workflow job.

Nếu đã có external caching do tổ chức quản lý, dùng `cache-provider: external` (hoặc disable theo docs) để tránh hai cache owners tranh nhau cùng files.

### 8.3. setup-gradle phát hiện pre-existing User Home

Nếu runner đã có `$GRADLE_USER_HOME/caches` trước khi setup-gradle restore, action có thể tránh overwrite và ghi thông báo cache disabled vì home đã có nội dung. Không bật `cache-overwrite-existing: true` một cách máy móc trên self-hosted runner: phải biết ai sở hữu cache và những credentials/init scripts nào đã ở đó.

**Cách tốt hơn:** dùng ephemeral/private Gradle User Home cho job, không thực hiện cache restore chồng và chọn một owner rõ ràng.

### 8.4. Pin action versions

Các major tags `@v6`/`@v5` trong bài cho dễ đọc. Với policy security cao, nên pin full reviewed commit SHA, theo dõi Dependabot updates và kiểm tra supply-chain provenance. Không tự tạo một SHA không được xác minh.

## 9. Configuration Cache trong GitHub Actions và encryption key

Configuration Cache mặc định là **project-local**:

~~~text
<project>/.gradle/configuration-cache/
~~~

Không phải `$GRADLE_USER_HOME/caches/modules-2`. Tài liệu `setup-gradle` nêu việc save/restore Configuration Cache qua action cần cung cấp `cache-encryption-key`.

Trong cùng setup-gradle step, có thể bổ sung:

~~~yaml
- name: Configure Gradle caching
  uses: gradle/actions/setup-gradle@v6
  with:
    cache-provider: basic
    cache-read-only: ${{ github.event_name != 'push' || github.ref != 'refs/heads/main' }}
    cache-encryption-key: ${{ secrets.GRADLE_ENCRYPTION_KEY }}
~~~

**Đây là step thay thế**, không phải step thứ hai thêm vào workflow để tạo double caching.

Để tạo key một lần trên máy quản trị tin cậy:

~~~bash
openssl rand -base64 16
~~~

Lưu output thành GitHub Actions secret `GRADLE_ENCRYPTION_KEY`, **không in key trong CI logs**. Nếu fork PR không được cấp secret, action không thể save/restore encrypted Configuration Cache như trusted main job; điều đó bình thường. **Không cấp privileged secret cho PR chỉ để cải thiện cache hit rate.**

### 9.1. Encryption không thay permissions

Một actor có cả cache bytes và encryption key có thể giải mã. Phải phân quyền cache storage, key và CI environment. Không upload project `.gradle/configuration-cache` vào public artifact store.

### 9.2. Configuration Cache không đồng nghĩa Build Cache

`Configuration cache entry reused` nghĩa Gradle không cấu hình lại task graph tương ứng; `:compileJava FROM-CACHE` nghĩa task output được khôi phục từ Build Cache. Các cơ chế này có thể cùng xuất hiện nhưng không quyết định lẫn nhau.

## 10. Phương án thay thế: manual actions/cache với key tường minh

Khi cần custom keys/prefix/restore policy, có thể dùng `actions/cache/restore@v4` và `actions/cache/save@v4`. **Phương án này thay thế setup-gradle User Home caching, không dùng đồng thời.**

### 10.1. Workflow manual cache hoàn chỉnh

~~~yaml
name: Gradle Manual Cache

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest

    env:
      GRADLE_USER_HOME: ${{ github.workspace }}/.gradle-ci

    steps:
      - uses: actions/checkout@v6

      - uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: '17'

      - name: Restore selected Gradle caches
        uses: actions/cache/restore@v4
        with:
          path: |
            .gradle-ci/caches/modules-2
            .gradle-ci/wrapper/dists
          key: gradle-v2-${{ runner.os }}-${{ runner.arch }}-jdk17-${{ hashFiles('gradle/wrapper/gradle-wrapper.properties', 'gradle/libs.versions.toml', 'gradle.lockfile') }}
          restore-keys: |
            gradle-v2-${{ runner.os }}-${{ runner.arch }}-jdk17-

      - name: Build and test
        run: ./gradlew test --no-daemon --console=plain

      - name: Save only from trusted default branch
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        uses: actions/cache/save@v4
        with:
          path: |
            .gradle-ci/caches/modules-2
            .gradle-ci/wrapper/dists
          key: gradle-v2-${{ runner.os }}-${{ runner.arch }}-jdk17-${{ hashFiles('gradle/wrapper/gradle-wrapper.properties', 'gradle/libs.versions.toml', 'gradle.lockfile') }}
~~~

Điểm kỹ thuật:

- `GRADLE_USER_HOME` được đặt trong workspace, khớp cache path.
- Chỉ cache dependency `modules-2` và Gradle distributions, không cache secrets, `init.d`, daemon hoặc toàn bộ project outputs.
- Key phân tách OS, architecture và JDK 17, còn hash chứa Gradle Wrapper và relevant dependency configuration files.
- `restore-keys` chỉ fallback trong cùng OS/arch/JDK prefix.
- PR chỉ restore. Save step chỉ được gọi trên trusted `push main`.
- GitHub Cache API vẫn thực thi branch/repository scope rules của nó.
- Không dùng setup-java `cache: gradle`, setup-gradle cache hay một second cache owner trong job.

### 10.2. Khi repo có nhiều lockfiles

Ví dụ trên đọc root `gradle.lockfile` nếu có. Một multi-project build có thể có nhiều lockfiles/independent builds, nên cần mở rộng hash pattern theo file thực tế. Nếu file được nêu không tồn tại, `hashFiles` không băm file đó. Không dùng hash của toàn bộ Java sources như dependency cache key.

### 10.3. Tại sao tách restore và save?

Tách bước cho phép read-only jobs không có bất cứ save action nào. Trong một workflow sử dụng `actions/cache@v4` thống nhất, lưu ý action auto-save có thể không biểu đạt policy rõ bằng restore/save riêng. Khi exact key đã tồn tại, cache có thể immutable và save không tạo entry mới; không coi việc cache key already exists là build failure.

### 10.4. Restore fallback không bảo đảm offline build

Một fallback entry có thể thiếu JUnit plugin, Maven module mới hoặc metadata repository đúng. Gradle vẫn phải resolve dependencies và tải những gì thiếu. Không dùng `--offline` như workaround mặc định khi restore partial cache.

## 11. Gradle dependency cache và repository identity

Dependency Cache không chỉ là JAR files; nó có:

1. Content-addressed downloaded artifact store.
2. Binary metadata store gồm module descriptors, resolved versions và repository origins.

Những điểm cần nhớ:

- Gradle ghi nhận repository identity (URL/type/layout). Cùng tọa độ Maven từ repositories khác nhau không tự được coi là cùng nguồn dữ liệu.
- Artifact có thể được giữ theo checksum, không dựa đơn thuần vào filename.
- Dynamic versions và changing/SNAPSHOT dependencies có metadata TTL.
- `--refresh-dependencies` làm Gradle xem lại metadata, có thể dùng checksums/HEAD để tránh tải lại file giống hệt.
- `--offline` chỉ dùng cache đã có; thiếu module sẽ fail.
- Cache metadata format thay đổi theo Gradle release, cần Wrapper compatibility.
- Nếu tự copy dependency cache, không copy `*.lock` hay `gc.properties`.
- Dependency locks và verification metadata mới là những thành phần quan trọng cho reproducible build, không phải sự tồn tại của cache key.

### 11.1. `--refresh-dependencies` không đồng nghĩa xóa mọi JAR

~~~bash
./gradlew test --refresh-dependencies --console=plain
~~~

Gradle sẽ kiểm tra lại resolution state, nhưng không buộc download lại mọi artifact nếu checksums/metadata cho biết file không đổi. Đừng thêm flag này vào mọi CI build vô điều kiện vì có thể tăng network requests không cần thiết.

### 11.2. `--offline` là một chính sách riêng

~~~bash
./gradlew test --offline --console=plain
~~~

Lệnh phù hợp khi cần air-gapped build hoặc verify prefetch coverage. Cache hit của CI archive **chưa đủ** chứng minh mọi dependency đều có sẵn để chạy offline.

### 11.3. Repositories private

Cache có thể chứa **private library JARs** dù không cache token. Với fork PR hoặc public CI artifact storage, chính nội dung JAR nội bộ cũng có thể là sensitive. Cân nhắc isolation: low-trust jobs không nên có quyền đọc cache chứa proprietary modules nếu không được phê duyệt.

## 12. Chia sẻ cache giữa container builds và file locking

Gradle dependency cache có file-based locking. Việc nhiều Gradle processes cùng truy cập writable metadata cache chỉ được hỗ trợ đúng khi chúng có thể giao tiếp nhau, điều thường không bảo đảm giữa containers độc lập hoặc network filesystem.

**Không mount cùng một writable `~/.gradle/caches/modules-2` vào nhiều concurrent containers rồi trông cậy hoàn toàn vào locks.**

### 12.1. Per-job writable home

~~~text
Container A: GRADLE_USER_HOME=/work/A/gradle-home (writable)
Container B: GRADLE_USER_HOME=/work/B/gradle-home (writable)
Container C: GRADLE_USER_HOME=/work/C/gradle-home (writable)
~~~

Mỗi job có state và permissions riêng.

### 12.2. Trusted read-only dependency cache

Gradle hỗ trợ `GRADLE_RO_DEP_CACHE` trỏ tới một read-only directory có `modules-2`:

~~~text
/opt/trusted-gradle-deps/
  modules-2/
    files-2.1/
    metadata-.../

Container A:
  GRADLE_RO_DEP_CACHE=/opt/trusted-gradle-deps
  GRADLE_USER_HOME=/work/A/gradle-home

Container B:
  GRADLE_RO_DEP_CACHE=/opt/trusted-gradle-deps
  GRADLE_USER_HOME=/work/B/gradle-home
~~~

Các containers có thể đọc shared immutable snapshot; dependencies còn thiếu được tải vào writable per-job home. Đây không phải cách ghi vào một shared writable cache.

**Điều kiện:** seed bằng trusted job, copy `modules-2` thành snapshot không bị writer chỉnh trong lúc readers sử dụng, bỏ `*.lock`/`gc.properties`, xác minh Gradle version compatibility. Feature này được mô tả là incubating trong Gradle docs hiện hành, nên kiểm tra Wrapper version.

## 13. Quyền filesystem của Gradle User Home

Trên POSIX, Gradle Security docs khuyến nghị User Home owner-only và `gradle.properties` private:

~~~bash
chmod 700 "$GRADLE_USER_HOME"
chmod 600 "$GRADLE_USER_HOME/gradle.properties"
~~~

Chạy `chmod 600` chỉ khi file tồn tại. Trên Windows dùng NTFS ACLs thay vì POSIX `chmod`.

Security checklist:

- Không chia sẻ writable User Home giữa hai CI users/tenants khác trust.
- Không cache `gradle.properties`, `init.d` hoặc signing keys.
- Không cho PR code thực thi trong self-hosted runner có tokens của job trước.
- Hạn chế permissions của S3/GCS/blob container dùng lưu cache.
- Không cho low-trust actors xóa/ghi trusted cache entries.
- Bảo vệ environment variables và repository credentials riêng từng job.
- Trên reused runners, kiểm soát cleanup và ephemeral workspaces.
- Đối chiếu cache provenance, who-wrote-it, scope và last update time.

### 13.1. `init.d` đặc biệt nguy hiểm

Gradle initialization scripts có thể được nạp và chạy trước project tasks. Nếu untrusted job ghi một script vào shared home mà release job restore, có nguy cơ thực thi code với privileged credentials. Đây là lý do nguy cơ cache poisoning **không thể giải quyết chỉ bằng cache key**.

### 13.2. Cache đọc cũng cần kiểm tra tin cậy

Một PR chỉ read-only không bảo đảm downloaded executable artifacts an toàn nếu cache nó đọc đã bị poisoned bởi một actor khác. Kết hợp trusted writer, dependency verification và plugin/Wrapper integrity checks.

## 14. Bảo vệ Gradle Wrapper và dependencies

Giữ các file quan trọng trong review:

~~~text
gradle/wrapper/gradle-wrapper.properties
gradle/wrapper/gradle-wrapper.jar
gradle/verification-metadata.xml
gradle.lockfile (hoặc lockfiles ở subprojects)
gradle/libs.versions.toml
~~~

Gradle Wrapper phải tải một distribution đáng tin. Nếu tổ chức kiểm soát hash distribution ZIP, dùng `distributionSha256Sum` với checksum thật, không điền một giá trị giả. Dependency Verification giúp đối chiếu checksums/signatures theo metadata policy; dependency locking giúp cố định dependency versions.

**Lưu ý:** Cache key phân loại entry; **checksum/signature** mới đánh giá binary identity/integrity theo nguồn tin cậy. Một cache hit không thay dependency verification.

## 15. Bài lab Java 17 xác minh tính đúng đắn sau cache restore

Mục đích là chứng minh build tạo kết quả đúng khi User Home mới, User Home đã warm và CI cache được restore.

Cấu trúc:

~~~text
gradle-cache-ci-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── src/main/java/demo/Greeting.java
├── src/test/java/demo/GreetingTest.java
├── gradlew
├── gradlew.bat
└── gradle/wrapper/...
~~~

Yêu cầu: JDK 17, Gradle Wrapper hợp lệ, Maven Central hoặc mirror được phép để tải JUnit trên cold run.

### 15.1. settings.gradle.kts

~~~kotlin
rootProject.name = "gradle-cache-ci-lab"
~~~

### 15.2. build.gradle.kts hoàn chỉnh

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    application
}

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
    testImplementation(platform("org.junit:junit-bom:5.10.2"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}

application {
    mainClass.set("demo.Greeting")
}
~~~

`application` tạo Java/Application conventions và Gradle `run` task. JUnit BOM version được pin cho reproducible example; nó không được tuyên bố là release mới nhất.

### 15.3. src/main/java/demo/Greeting.java

~~~java
package demo;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Xin chào từ Gradle CI!";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

### 15.4. src/test/java/demo/GreetingTest.java

~~~java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingTest {
    @Test
    void hasExpectedMessage() {
        assertEquals(
            "Xin chào từ Gradle CI!",
            Greeting.message()
        );
    }
}
~~~

### 15.5. Chạy bằng Gradle Wrapper

Linux/macOS:

~~~bash
./gradlew test run --console=plain
./gradlew test run --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat test run --console=plain
.\gradlew.bat test run --console=plain
~~~

**Dòng chính xác do Java main in ra:**

~~~text
Xin chào từ Gradle CI!
~~~

JUnit có một test method, expected pass. Những dòng `> Task ...`/`BUILD SUCCESSFUL` khác nhau theo Gradle version, caches và console settings. Task `run` có thể thực thi mỗi invocation do in console, trong khi compile/test tasks có thể `UP-TO-DATE`; không coi đó là User Home cache miss.

### 15.6. Biên dịch/chạy Java 17 thuần

~~~bash
mkdir -p out
javac -encoding UTF-8 --release 17 \
  -d out src/main/java/demo/Greeting.java
java -cp out demo.Greeting
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -encoding UTF-8 --release 17 -d out src\main\java\demo\Greeting.java
java -cp out demo.Greeting
~~~

**Stdout** vẫn là `Xin chào từ Gradle CI!`. Lệnh `javac/java` nằm ngoài Gradle chỉ xác minh source/Java output, **không chứng minh cache User Home đã restore đúng**.

## 16. Lab cold vs warm dependency cache

### 16.1. Dùng home test riêng để không đụng dữ liệu cá nhân

Linux/macOS:

~~~bash
export GRADLE_USER_HOME="$PWD/.gradle-ci-lab"
./gradlew test --console=plain
~~~

PowerShell:

~~~powershell
$env:GRADLE_USER_HOME = Join-Path (Get-Location) ".gradle-ci-lab"
.\gradlew.bat test --console=plain
~~~

Thêm `.gradle-ci-lab/` vào `.gitignore` nếu dùng dài hạn. Không commit cache hoặc secret files.

### 16.2. Quan sát cache directory

~~~bash
du -sh "$GRADLE_USER_HOME/caches/modules-2"
du -sh "$GRADLE_USER_HOME/wrapper/dists"
~~~

Nếu directory chưa tồn tại, `du` có thể lỗi—đó là điều bình thường với cold home.

### 16.3. Thực nghiệm

1. Chạy build với cold User Home: Gradle có thể download distribution/JUnit/plugin artifacts.
2. Cache `modules-2`/`wrapper/dists` theo workflow policy.
3. Trong fresh runner/job cùng trust tier/OS/JDK, restore đúng key.
4. Chạy cùng Wrapper và `./gradlew test run`.
5. Quan sát action logs: cache hit/exact key/fallback/restored size.
6. Quan sát Gradle downloads và build duration.
7. Kiểm tra JUnit pass và Java stdout đúng.
8. So với một cold runner tương tự để lượng hóa lợi ích.

**Cẩn trọng khi benchmark:** Daemon/JIT warmup, Maven Central response time và Build Cache khác nhau cũng ảnh hưởng duration. Một cache archive 3 GB mất nhiều thời gian tải/giải nén có thể không hiệu quả hơn việc chỉ cache modules.

### 16.4. Khi cache hit mà Gradle vẫn tải dependencies

- Archive chỉ chứa một phần artifacts.
- Project thêm library/plugin version mới.
- Metadata TTL của dynamic/changing dependency hết.
- Repository URL/type/layout thay đổi.
- CI Gradle User Home path khác path đã restore.
- JDK/Gradle Wrapper không tương thích một phần cache format.
- Restore theo fallback key, không có exact dependency set.
- Gradle plugin portal cache khác Maven Central state.

Restore archive thành công **không** có nghĩa Gradle không cần network. Dùng `--info` khi cần, nhưng tránh log secrets.

## 17. GitLab CI: phân quyền bằng cache policy

GitLab CI có `cache:key`, `cache:paths`, `cache:policy` cùng cache backend/runner permissions. Một ví dụ read-only cho untrusted branches:

~~~yaml
image: eclipse-temurin:17-jdk

variables:
  GRADLE_USER_HOME: "$CI_PROJECT_DIR/.gradle-ci"

stages:
  - test

gradle-test:
  stage: test
  cache:
    key:
      files:
        - gradle/wrapper/gradle-wrapper.properties
      prefix: "gradle-$CI_COMMIT_REF_SLUG"
    paths:
      - .gradle-ci/caches/modules-2/
      - .gradle-ci/wrapper/dists/
    policy: pull
  script:
    - ./gradlew test --no-daemon --console=plain
~~~

**Ý nghĩa:** `policy: pull` chỉ restore, không upload. `prefix` dựa branch slug giúp tách caches nhưng cũng làm feature branch có thể không nhận common default-branch cache.

Một **trusted seed job** trên protected default branch có thể dùng cache block với:

~~~yaml
cache:
  key:
    files:
      - gradle/wrapper/gradle-wrapper.properties
    prefix: gradle-trusted-main
  paths:
    - .gradle-ci/caches/modules-2/
    - .gradle-ci/wrapper/dists/
  policy: pull-push
~~~

Đây là fragment thay thế cho một **job được rules bảo đảm chỉ chạy trên trusted protected branch**. Không ghép hai cache blocks vào cùng job. Khi muốn PRs đọc seed cache, thiết kế GitLab `fallback_keys` và protected/non-protected cache separation có chủ đích; không giả định mọi MR có quyền đọc private/protected caches.

### 17.1. GitLab runner backend cũng là security boundary

Dù YAML `policy: pull`, một runner dùng object storage bucket với credentials quá rộng có thể vẫn là rủi ro. Kiểm tra CI runner, object storage, protected branch rules và cache key collision. Không đưa release secrets vào job chạy mã fork.

## 18. Jenkins và self-hosted runners

Jenkins caching phụ thuộc runner lifecycle, persistent volumes hoặc artifact-cache plugin; không có một `setup-gradle` action tiêu chuẩn giống GitHub.

Một shell step trên Linux agent có thể dùng:

~~~bash
export GRADLE_USER_HOME="$WORKSPACE/.gradle-ci"
./gradlew --version
./gradlew test --no-daemon --console=plain
~~~

**Đoạn này chỉ cô lập User Home**, chưa tự làm cross-build caching. Một backend/volume riêng phải lưu selected dirs từ trusted jobs và restore đúng key/scope.

Yêu cầu cho Jenkins/self-hosted:

- Một writable Gradle User Home riêng theo job/tenant.
- File permission owner-only, không giữ credentials từ job khác.
- Không để PR chạy trên release runner có signing keys.
- Không mount một shared writable cache vào concurrent containers.
- Chọn trusted writer/readonly readers.
- Có lifecycle cleanup và cache retention.
- Secret injection qua credentials store; không save secrets vào archive.

### 18.1. `stash/unstash` không tự tạo global cache

Jenkins stash thường phục vụ truyền files giữa stages/nodes trong một pipeline, không phải cơ chế persist dependency cache qua mọi build/repo. Đừng giả định “đã stash” nghĩa cold runner tuần sau không tải lại Maven dependencies.

## 19. Remote Build Cache là cấu hình riêng

Nếu muốn tránh biên dịch lại Java trên fresh workers, dùng Gradle **Build Cache** cho task outputs. Một trusted remote Build Cache thường có policy:

~~~text
Trusted main:
  read + push validated task outputs

Feature branch / PR:
  read only, không push vào privileged namespace

Release:
  read trusted cache, hoặc bypass khi security policy yêu cầu
~~~

Đây là **quyền riêng** so với Gradle User Home dependency cache. User Home cache giảm dependency downloads; Build Cache giảm task work. Không cho untrusted jobs có remote Build Cache push credentials, không cache task outputs chứa secrets.

Mảnh `settings.gradle.kts` chỉ minh họa local Build Cache:

~~~kotlin
buildCache {
    local {
        isEnabled = true
    }
}
~~~

Nó **không** khai báo remote cache. Muốn remote cần `HttpBuildCache` backend, HTTPS URL, credentials và writer policy thật, không được giả mạo endpoint rồi tuyên bố runnable.

### 19.1. Tại sao cacheable task chưa chắc luôn an toàn?

Một custom task có thể đọc environment/untracked file, tạo output phụ thuộc timestamp hoặc gọi remote mutating API. Nếu cache output không phản ánh semantic inputs, Build Cache hit có thể làm output sai. Task cacheability phải được đánh giá riêng, không suy ra từ việc dependency cache hit.

## 20. Configuration Cache trên CI là một lớp riêng

`<root>/.gradle/configuration-cache` lưu configured task graph/state, có thể có secret-bearing fields và phải đáp ứng requirements về serialization. User Home action caching không phải mặc nhiên tương đương Configuration Cache restore.

Khi `gradle/actions/setup-gradle` có `cache-encryption-key`, action có thể save/restore Configuration Cache theo mechanisms được hỗ trợ. Không tự archive project-local state vào public cache chỉ để tăng tốc.

Nếu CI ephemeral không restore Configuration Cache, mỗi run có thể ghi `Configuration cache entry stored` nhưng **không có cross-job reuse**. Điều đó không có nghĩa dependency/User Home caching thất bại.

## 21. Security: chống cache poisoning và rò rỉ credentials

Threat model:

~~~text
Untrusted PR changes build.gradle.kts
       |
       v
Loads malicious Gradle plugin / writes cache data
       |
       v
Wrongly shared cache receives untrusted bytes
       |
       v
Privileged release job restores poisoned cache
       |
       v
Plugin/init logic executes with secrets
       |
       v
Credential leak, artifact tampering, compromised release
~~~

Defense-in-depth:

1. PRs không được write trusted caches.
2. Release workflows không restore caches thiếu provenance.
3. Tránh `pull_request_target` checkout PR code rồi chạy Gradle với secrets.
4. Không chia sẻ `gradle.properties`, `init.d`, signing keys, daemon logs.
5. Pin/validate Gradle Wrapper, dependency verification và locks.
6. HTTPS Maven/plugin repositories, giảm repository substitution/dependency confusion.
7. Cache writer identities và branch scopes được audit.
8. CI tokens least privilege, secrets chỉ cấp vào trusted jobs.
9. Self-hosted runners tách tenant/home/container isolation.
10. Không coi cached binary là được xác thực chỉ vì key trùng.
11. Đánh giá private artifacts trong cache có được phép lộ cho fork PR không.
12. Khi có incident, rotate cache namespace/key và revoke/rotate secrets liên quan.

**Read-only là điều kiện cần, không phải điều kiện đủ**: nếu cache nguồn đã bị poisoned, quyền đọc có thể vẫn mang mã độc vào build.

## 22. Cache retention, cleanup và quota

Gradle định kỳ cleanup những artifacts/version-specific caches không được dùng; CI cache action cũng có cleanup. Trong `setup-gradle@v6`, các modes chính gồm:

~~~yaml
with:
  cache-provider: basic
  cache-cleanup: on-success
~~~

Đây là **fragment cấu hình của setup-gradle step**, không phải workflow tự chạy. Các giá trị:

- `on-success`: cố dọn stale entries trước save nếu Gradle builds trong job thành công.
- `always`: thử cleanup ngay cả khi build fail.
- `never`: không thực hiện cleanup do action.

Khi action caching disabled/read-only, cleanup behavior khác với writable cache mode. Kiểm tra docs version-specific trước khi điều chỉnh.

Đo:

- Cache restore/download duration.
- Cache upload duration.
- Archive size (modules vs transforms).
- Gradle distribution/JUnit download count.
- CI storage quota và eviction frequency.
- Build duration và task outcomes tách riêng.
- Hit exact key, fallback key hay miss.
- Cache-writing job/actor/trust tier.

Một archive lớn không luôn nhanh hơn việc tải vài JAR qua Maven mirror nhanh. Giữ một cache owner và chỉ những dirs có ROI rõ.

### 22.1. Key rotation

Tăng prefix `gradle-v2` lên `gradle-v3` khi:

- Thay cache schema/contents.
- Nâng Gradle/JDK lớn làm cache cũ kém tương thích.
- Có corruption/security incident.
- Cần tách trust tier hoặc backend.
- Muốn loại bỏ cache cũ khỏi restore fallback.

Không tăng version prefix ở mọi commit nếu mục tiêu là tái sử dụng.

## 23. CI troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Restore cache hit nhưng Gradle download JAR | Entry partial, repo identity/TTL, dependency mới | Action logs + Gradle `--info` |
| Cache luôn miss | Key đổi, branch scope, path mismatch | Key/restore logs, GRADLE_USER_HOME |
| PR không thấy cache main | GitHub scopes hoặc event access restrictions | Đọc CI cache access docs |
| PR có quyền ghi trusted cache | Policy lỗi | Bật read-only, protected writer jobs |
| Fork PR không reuse Configuration Cache | Không có encryption secret | Expected; không leak key |
| Self-hosted setup-gradle disabled cache | Pre-existing User Home | Chỉ một owner, isolate runner |
| Cache action reports key already exists | Immutable entry | Không cần overwrite; rotate có chủ đích |
| `--offline` fail sau restore | Thiếu dependencies | Prefetch đúng module hoặc resolve online |
| `--refresh-dependencies` vẫn dùng JAR cũ | Hash/metadata giống | Expected; không đồng nghĩa redownload |
| Build vẫn chậm khi cache hit | Compile/test tasks chạy trong fresh workspace | Tách Build Cache và Dependency Cache |
| Cache archive quá lớn | Transforms/outputs không phù hợp | Selective caching, cleanup/metrics |
| Gradle file locks lỗi ở Docker | Shared writable dependency cache | Writable per-job home, RO snapshot |
| Different Java/Gradle cache incompatibility | Key không tách platform/version | OS/arch/JDK/Wrapper partition |
| Private artifacts lộ qua cache | Scope overly permissive | Tenant/trust isolation, cache content review |
| Secrets trong cache files | Cache toàn User Home | Không cache gradle.properties/init.d/keys |
| Build Cache remote bị poisoned | Untrusted push quyền | Read-only PR, trusted writer identities |
| JUnit test fail dù cache restore hit | Build correctness issue riêng | Xem test reports, dependency graph |
| `UP-TO-DATE` nhưng cache action miss | Project outputs đã có từ workspace | Task snapshot không phải User Home cache |
| Action provider defaults bất ngờ | setup-gradle v6 uses different provider | Chọn `cache-provider` tường minh |
| CI logs thiếu cache diagnostics | Cache action disabled/scope issue | Inspect action summary/permissions |

### 23.1. Quy trình xử lý một cache miss

1. Action đã restore cache hay chưa? Exact/fallback/miss?
2. Job có quyền đọc scope ấy không?
3. `GRADLE_USER_HOME` của Gradle đúng path restored không?
4. Archive có `modules-2` và Wrapper artifacts cần thiết không?
5. Maven/plugin repository identity có thay đổi không?
6. Có JDK/Gradle Wrapper upgrade/metadata TTL/lock update không?
7. Network downloads là artifacts mới hay cùng artifacts cũ?
8. Java/JUnit tests và outputs có đúng không?
9. Restore/upload thời gian có thật sự cải thiện build không?
10. Có security evidence để trust cache writer không?

**Không xóa bừa `~/.gradle`** của shared runner khi chỉ có cache miss; việc đó có thể xóa credentials và gây hậu quả cho jobs khác. Trước khi can thiệp, phải xác định home owner và phạm vi.

## 24. Quy trình kiểm tra trên CI theo trust boundary

~~~text
Trusted default branch push
         |
         v
Checkout + JDK/Wrapper validation
         |
         v
Restore trusted User Home cache
         |
         v
Gradle verify/dependency resolve/test
         |
         v
JUnit PASS + output integrity?
       /              \
     No               Yes
     |                 |
     v                 v
No cache seeding     Cleanup selected dirs
                       |
                       v
               Save trusted new entry

Untrusted PR/fork
         |
         v
No privileged secrets
         |
         v
Read-only restore where allowed
         |
         v
Run Gradle tests in isolated runner
         |
         v
Never write trusted cache
~~~

Một cache service outage **không nên** thay đổi build output nếu artifact repositories đáng tin còn sẵn. Cache miss trước hết là performance issue; luôn kiểm tra cả timing và correctness.

### 24.1. Release job có thể cần bypass cache

Nếu provenance của cached bytes không thể xác nhận, release/signer job nên dùng trusted verified dependency sources và không restore untrusted caches. Hiệu năng không ưu tiên hơn software supply-chain integrity.

## 25. Bài tập tự kiểm tra và đáp án

**Câu 1.** `GRADLE_USER_HOME` và project `.gradle` có giống nhau không?

**Đáp án:** Không. User Home giữ caches/global state, còn project `.gradle` giữ local task history và Configuration Cache của build.

**Câu 2.** Vì sao không cache nguyên `~/.gradle`?

**Đáp án:** Có thể bao gồm credentials, init scripts, logs, locks và dữ liệu không portable.

**Câu 3.** Cache key có thay CI access scope không?

**Đáp án:** Không. Key và branch/repository scope là hai cơ chế khác; quyền restore/save do CI platform kiểm soát.

**Câu 4.** PR từ fork có nên save cache mà release job sẽ restore?

**Đáp án:** Không. Tách trust tiers, cho read-only nếu phù hợp và không cấp secrets.

**Câu 5.** Trong GitHub Actions setup-gradle@v6, `cache-provider: basic` khác `enhanced` thế nào?

**Đáp án:** Basic là cache provider open-source dựa trên GitHub Actions Cache; enhanced là provider khác với khả năng/availability/cost riêng.

**Câu 6.** Khi dùng setup-gradle, có bật `actions/setup-java cache: gradle` cùng lúc không?

**Đáp án:** Không, tránh hai cache owners cho cùng User Home.

**Câu 7.** `cache-read-only: true` có cấm restore không?

**Đáp án:** Không; nó cấm save qua action đó, còn restore vẫn tùy scope.

**Câu 8.** Vì sao fork PR có thể không cache Configuration Cache?

**Đáp án:** Không được cung cấp `GRADLE_ENCRYPTION_KEY`, nên action không save/restore encrypted entry như trusted workflow.

**Câu 9.** Có nên mount cùng writable modules-2 cache vào nhiều Docker containers không?

**Đáp án:** Không nên. Dùng per-job writable home và trusted read-only dependency snapshot nếu cần.

**Câu 10.** `GRADLE_RO_DEP_CACHE` có thay `GRADLE_USER_HOME` không?

**Đáp án:** Không; nó là read-only dependency source phụ.

**Câu 11.** `--refresh-dependencies` có chắc tải lại mọi JAR không?

**Đáp án:** Không; Gradle có thể tái dùng file nếu checksums/metadata chứng minh không đổi.

**Câu 12.** Cache restore hit có chứng minh CI sẽ chạy offline không?

**Đáp án:** Không; cache có thể thiếu một dependency hoặc plugin artifact.

**Câu 13.** `compileJava` chạy lại dù User Home cache hit là lỗi?

**Đáp án:** Không. Fresh workspace có thể thiếu outputs, cần compile.

**Câu 14.** Read-only cache có bảo vệ tuyệt đối khỏi cache poisoning không?

**Đáp án:** Không. Nó ngăn job ghi; nếu cache nguồn đã chứa malicious bytes, job vẫn có thể đọc phải.

**Câu 15.** File permission nào phù hợp trên POSIX?

**Đáp án:** `chmod 700` cho User Home và `chmod 600` cho `gradle.properties` nếu chứa secrets.

**Câu 16.** Java 17 lab in gì?

**Đáp án:** Chính xác `Xin chào từ Gradle CI!`.

**Câu 17.** `actions/cache/save@v4` được chạy khi nào trong workflow mẫu?

**Đáp án:** Chỉ khi event là trusted `push` vào `refs/heads/main`, theo điều kiện của step.

**Câu 18.** Vì sao GitLab `cache:policy: pull` phù hợp PR?

**Đáp án:** Nó chỉ restore cache, không upload vào cache store.

**Câu 19.** Một archive có chứa private artifacts nhưng không có token thì đã an toàn để share public chưa?

**Đáp án:** Chưa. Nội dung artifact có thể là tài sản nhạy cảm.

**Câu 20.** Vì sao CI nên đo cache archive download time?

**Đáp án:** Archive quá lớn có thể mất thời gian hơn những dependencies cần tải.

**Câu 21.** Một cache key có full commit SHA làm gì với hit rate?

**Đáp án:** Dễ miss mỗi commit nếu không có restore prefix fallback.

**Câu 22.** Khi nào nên rotate cache schema prefix?

**Đáp án:** Khi đổi Gradle/JDK, cache contents, trust policy hoặc xử lý corruption/security incident.

## 26. Checklist triển khai thực tế

1. Pin Gradle Wrapper/JDK và xác minh nguồn JAR/ZIP.
2. Xác định `GRADLE_USER_HOME` thực tế của CI process.
3. Chỉ cache directories cần thiết, bắt đầu với `modules-2` và Wrapper distributions.
4. Không cache User Home `gradle.properties`, `init.d`, signing keys hoặc daemon logs.
5. Chọn đúng một cache owner cho mỗi job.
6. Với GitHub, ưu tiên setup-gradle, chọn provider có chủ đích.
7. Tách OS/arch/JDK/Wrapper/dependency lock state trong manual cache key.
8. Không dùng restore fallback xuyên platform/trust tiers.
9. Có một hoặc ít trusted writers; PRs là read-only.
10. Không cấp production secrets cho untrusted Gradle build.
11. Không chạy untrusted checkout bằng privileged `pull_request_target`.
12. Tách private artifacts/secret scopes khỏi public/fork access.
13. Có independent writable home theo container/tenant.
14. Nếu cần shared dependencies, seed trusted read-only snapshot.
15. Không copy `*.lock` hoặc `gc.properties` khi tự phát tán dependency cache.
16. Dùng dependency locking/verification/HTTPS repositories theo policy.
17. Không mặc định cache project Configuration Cache như User Home.
18. Cung cấp encryption key qua secret store khi cache Configuration Cache trên CI.
19. Quản lý remote Build Cache read/write riêng nếu sử dụng.
20. Kiểm tra action logs và Gradle `--info` khi cần.
21. Chạy Java/JUnit tests để xác minh correctness độc lập cache hit.
22. Benchmark cold/warm cùng JDK/Wrapper/network conditions.
23. Dọn cache/đo quota và rotate prefix có kiểm soát.
24. Xem cache là supply-chain input cần trust provenance.
25. Giữ một uncached/verified build path để phục vụ điều tra và release audit.

## 27. Sơ đồ tổng kết

~~~text
                  CI workflow
                      |
             Branch / event / actor
                      |
                Trust policy
                      |
                      v
             Cache key + scope
                      |
                 Read allowed?
                      |
                      v
             Restore trusted cache
                 modules-2
                 wrapper/dists
                      |
                      v
              Per-job writable
              GRADLE_USER_HOME
                      |
                      v
             Gradle Wrapper + JDK
                      |
                 Dependency cache
                      |
                      +----> Build Cache (task outputs, riêng)
                      +----> Configuration Cache (task graph, riêng)
                      +----> Up-to-date checks (project outputs)
                      |
                      v
             Java17/JUnit build tests
                      |
                      v
                Correct output?
                      |
                  Trusted main?
                   /          \
                 Yes           No
                  |             |
                  v             v
             Save selected     No trusted cache write
             cache safely

Key không phải permission.
Read-only không thay checksum verification.
Cache hit không thay test correctness.
~~~

## 28. Tài liệu chính thức

1. Gradle — Gradle-managed Directories and Caches: https://docs.gradle.org/current/userguide/directory_layout.html
2. Gradle — Dependency Caching: https://docs.gradle.org/current/userguide/dependency_caching.html
3. Gradle — Securing the Build Tool: https://docs.gradle.org/current/userguide/securing_build_tool.html
4. Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
5. Gradle — Build Cache Concepts: https://docs.gradle.org/current/userguide/build_cache_concepts.html
6. Gradle — Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache.html
7. Gradle — Configuration Cache Adoption and CI: https://docs.gradle.org/current/userguide/configuration_cache_adoption.html
8. Gradle — Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
9. Gradle — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
10. Gradle — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
11. Gradle — Build Environment: https://docs.gradle.org/current/userguide/build_environment.html
12. Gradle GitHub Actions — README: https://github.com/actions/gradle-build-tools-actions
13. Gradle GitHub Actions — setup-gradle reference: https://github.com/actions/gradle-build-tools-actions/blob/main/docs/setup-gradle.md
14. Gradle setup-gradle action definition: https://github.com/gradle/actions/blob/main/setup-gradle/action.yml
15. GitHub Actions — Cache access and scope: https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching
16. GitHub Actions — Security hardening: https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions
17. GitHub Actions — Workflow syntax and permissions: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
18. GitLab CI — Caching: https://docs.gitlab.com/ci/caching/

**Phiên bản và phạm vi:** Các nguồn `/current/` phản ánh Gradle hiện hành, không phải mọi Gradle Wrapper cũ. Ví dụ GitHub dùng `gradle/actions/setup-gradle@v6` với `cache-provider: basic` theo tài liệu gần đây; CI action versions và GitLab runner permissions có thể thay đổi. Khi triển khai thật, phải kiểm tra Gradle Wrapper/JDK và action/provider versions đang dùng, không sao chép cache policy mà chưa xác minh branch protection và quyền truy cập.

**Kết luận:** Một Gradle CI cache đúng không chỉ giúp tải ít hơn. Nó có **key vừa đủ ổn định, phạm vi trùng trust boundary, quyền ghi dành cho trusted jobs, private User Home cho từng worker, artifact verification, selective files, cleanup và kết quả test đúng**. Tốc độ chỉ có ý nghĩa khi không đánh đổi khả năng tái hiện hoặc an toàn chuỗi cung ứng.