# Kết hợp Wrapper checksum, dependency verification và locking trong Gradle

## 1. Mục tiêu: vừa đúng phiên bản, vừa đúng dữ liệu, vừa đúng công cụ

Một Gradle build Java có thể bị thay đổi từ ba hướng độc lập:

1. **Build tool bị đổi**: Gradle Wrapper tải một distribution ZIP khác với release bạn định sử dụng; hoặc file `gradle-wrapper.jar` bị sửa ngay trong repository.
2. **Artifact bị thay bytes**: Maven repository, proxy hoặc cache trả một JAR/POM khác, nhưng cùng group:name:version.
3. **Version graph thay đổi**: dynamic version, version range, platform/BOM, constraint hoặc transitive dependency khiến cùng source code resolve phiên bản khác ở thời điểm khác.

Ba biện pháp bổ sung nhau:

- **Gradle Wrapper checksum** ghim release Gradle cụ thể, dùng `distributionSha256Sum` để kiểm tra **downloaded Gradle distribution ZIP**. Phải **kiểm tra riêng Wrapper JAR** vì JAR này chạy trước Gradle.
- **Dependency verification** so các checksums SHA-256 hoặc chữ ký PGP của external dependency artifacts/metadata với giá trị được review trong `gradle/verification-metadata.xml`.
- **Dependency locking** ghi versions thực sự resolve vào `gradle.lockfile` và buộc những lần resolution sau tôn trọng lock state tương ứng.

Nếu một JAR giữ nguyên version nhưng bytes bị thay, **locking không phát hiện**. Nếu một dynamic selector chọn version mới với JAR checksum hợp lệ, **verification không thay locking**. Nếu chính `gradle-wrapper.jar` độc hại, các bước trên chạy *sau* nó không đủ bảo vệ.

Bài học thuộc **Build Tool Gradle → An toàn build**. Bạn sẽ học cách triển khai ba lớp từ đầu trên project Java 17+ bằng Gradle Groovy DSL, review trust metadata, commit files, nâng cấp an toàn và chẩn đoán lỗi supply chain.

### 1.1. Bản đồ các lớp bảo vệ

| Biện pháp | File/trạng thái chính | Đối tượng cần kiểm tra | Thời điểm | Giới hạn |
| --- | --- | --- | --- | --- |
| Wrapper ZIP checksum | `gradle/wrapper/gradle-wrapper.properties` | Gradle distribution `gradle-9.9.0-bin.zip` | Khi distribution chưa được download và Wrapper cần tải mới | Không tự rehash cached distribution mỗi lần, không xác minh Wrapper JAR |
| Wrapper JAR validation | Hash/signature từ Gradle release chính thức và CI check | `gradle/wrapper/gradle-wrapper.jar` | **Trước** khi chạy untrusted Wrapper; khi JAR thay đổi | Không đánh giá build scripts/plugins |
| Dependency verification | `gradle/verification-metadata.xml` | JARs, POMs, module metadata, plugin artifacts theo Gradle engine | Khi resolved artifact được dùng/kiểm tra | Không pin version graph, không thay CVE scanning |
| Dependency locking | `gradle.lockfile` theo project | Resolved versions của modules và transitive graph | Khi resolve configurations có locking | Không hash artifact bytes, không tự lock mọi plugin DSL request |

**Quy tắc bảo mật:** một checksum chỉ có giá trị nếu **expected checksum lấy từ nguồn đã xác thực và được review**. Tự lấy hash từ artifact đã bị compromise rồi tự chấp nhận sẽ tạo ra một baseline độc hại “hợp lệ”.

## 2. Threat model: vì sao cần cả ba

### 2.1. Tấn công vào Gradle distribution

Trong `gradle-wrapper.properties`:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
```

URL này pin một release, nhưng nếu traffic hoặc mirror bị can thiệp, ZIP nhận được có thể không đúng bytes. `distributionSha256Sum` giúp Wrapper từ chối downloaded ZIP khác SHA-256 đã pin.

**Lưu ý:** `distributionSha256Sum` chỉ kiểm tra distribution ZIP **khi cần download**. Nếu máy đã có distribution cached được Wrapper đánh dấu hợp lệ, nó không hứa rehash toàn bộ installed files ở mỗi invocation. Bảo vệ Gradle User Home và CI caches vẫn quan trọng.

### 2.2. Tấn công vào Wrapper JAR

`gradle-wrapper.jar` là executable Java code chạy **trước** phiên bản Gradle ZIP. Nếu attacker thay JAR, JAR độc hại có thể tìm credentials, thực thi code ngoài ý muốn, thậm chí bỏ qua kiểm tra ZIP. Vì thế phải validate JAR **độc lập** với distribution checksum.

### 2.3. Artifact bị thay nhưng version giữ nguyên

Giả sử team đã lock `org.apache.commons:commons-lang3:3.17.0`. Nếu repository hoặc cache trả một JAR khác với coordinate y hệt, lockfile vẫn thấy version `3.17.0`, nên **không phát hiện nội dung thay đổi**. Verification metadata lưu approved SHA/PGP giúp so bytes.

### 2.4. Dynamic version đổi dù JAR hợp lệ

Ví dụ (chỉ để giải thích version selector, không phải một module có thật):

```groovy
dependencies {
    implementation 'com.example:sample-api:2.+'
}
```

Hôm nay resolve `2.4`, ngày mai `2.5`. Hai JAR đều có thể được ký/chứa checksum đúng. Lockfile quyết định version nào đã được chấp thuận cho mỗi configuration. Đừng trộn vấn đề **“đúng bytes của version X”** với **“có được nâng X lên Y hay không”**.

### 2.5. Giới hạn bao phủ

Ba cơ chế không tự loại mọi rủi ro:

- Một publisher có thể phát hành JAR chính chủ nhưng vẫn có lỗ hổng CVE.
- Chữ ký PGP đúng về mật mã không bảo đảm signing key không bị lộ.
- Một PR độc hại có thể sửa cả dependency coordinate và expected hash trong XML nếu code review yếu.
- Build scripts, init scripts, `buildSrc`, included builds và plugins được tin tưởng có thể chạy code tùy ý ở configuration time.
- Source code review, CI isolation, dependency vulnerability scanning, repository allowlists, secrets protection và SBOM vẫn cần thiết theo mức độ rủi ro.

## 3. Thứ tự triển khai: bảo vệ trước khi chạy

```text
Checkout / pull request mới
       |
       +-- Review gradlew + gradlew.bat
       +-- Review gradle-wrapper.properties: distributionUrl, pinned SHA
       +-- Verify gradle-wrapper.jar using official independent checksum/signature
       +-- Inspect settings/build scripts, buildSrc/included build logic
       |
       v
Run a trusted Wrapper
       |
       +-- Download Gradle distribution ZIP if absent
       +-- Compare ZIP SHA-256 to distributionSha256Sum
       |
       v
Gradle resolves plugin and project dependencies
       |
       +-- Dependency verification compares artifact/metadata hashes or signatures
       +-- Dependency locking enforces resolved versions
       |
       v
Compile, test, package, release according to CI policy
```

**Không chạy `./gradlew` của một untrusted checkout chỉ để “tạo checksum cho nó”.** Đối với repository từ bên ngoài, hãy kiểm tra Wrapper trước khi IDE tự import/sync, vì IDE sync cũng có thể thực thi Gradle build logic.

## 4. Wrapper files và cách pin distribution SHA-256

### 4.1. Những file cần commit

```text
project/
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
```

- `gradlew` và `gradlew.bat` gọi Wrapper JAR.
- `gradle-wrapper.jar` bootstrap distribution.
- `gradle-wrapper.properties` chứa URL, base directories và SHA-256 nếu đã cấu hình.
- Distribution ZIP được cache trong Gradle User Home (`~/.gradle/wrapper/dists` theo cấu hình thông dụng), không phải JAR ứng dụng.
- Người dùng và CI nên dùng **Wrapper đã xác minh** thay vì một Gradle global không rõ version/provenance.

Một file properties sau khi chạy wrapper task sẽ chứa những thuộc tính kiểu:

```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```

Đây **chưa phải cấu hình cuối cùng** vì không có SHA. Phải thêm thuộc tính `distributionSha256Sum` với đúng **64 ký tự hex** được lấy từ publisher trusted. Ví dụ bài dùng Gradle **9.9.0-bin.zip**; bản `all.zip` là file khác với checksum khác.

### 4.2. Nguồn SHA chính thức

Gradle công bố hashes ở:

- https://gradle.org/release-checksums/
- https://services.gradle.org/distributions/gradle-9.9.0-bin.zip.sha256

Checksum trả về thường là một dòng SHA-256. Nếu môi trường có threat model cao, đối chiếu hash với **release checksums được xác thực độc lập**, chữ ký release và trusted source control. Chỉ tải artifact và hash từ cùng nguồn vừa bị compromise không tự tạo niềm tin.

### 4.3. Tạo Wrapper từ trusted Gradle trên Linux/macOS

Dưới đây là command **thật** lấy checksum, kiểm tra định dạng và chuyển vào `gradle wrapper`. Nó cần một installation `gradle` đã được team tin cậy, chứ không dùng JAR của checkout chưa kiểm tra.

```bash
sha=$(curl -fsSL \
  https://services.gradle.org/distributions/gradle-9.9.0-bin.zip.sha256 |
  tr -d '\r\n')
printf '%s\n' "$sha" | grep -Eq '^[0-9a-fA-F]{64}$' || exit 1

# Cross-check checksum với official release checksums trước khi dùng.
gradle wrapper \
  --gradle-version 9.9.0 \
  --distribution-type bin \
  --gradle-distribution-sha256-sum "$sha"
```

Sau lệnh, kiểm tra file thật:

```bash
grep -E '^(distributionUrl|distributionSha256Sum)=' \
  gradle/wrapper/gradle-wrapper.properties
```

**Không có checksum bịa trong bài**: giá trị thật được lấy và ghi bởi command. Đừng tự copy một hash “gần giống” hoặc lấy SHA của ZIP khác.

Nếu Gradle cài sẵn là version cũ, Gradle Wrapper docs giải thích có thể cần chạy wrapper task lần thứ hai để đồng bộ Wrapper JAR/scripts khi nâng cấp. Cách an toàn nhất là dùng một **trusted Gradle 9.9.0 installation** và validate JAR sau khi tạo.

### 4.4. Windows PowerShell

```powershell
$sha = (Invoke-RestMethod -Uri 'https://services.gradle.org/distributions/gradle-9.9.0-bin.zip.sha256').Trim()
if ($sha -notmatch '^[0-9a-fA-F]{64}$') {
    throw 'Checksum response is not a SHA-256 hex value'
}

# Cross-check the SHA-256 with official release checksums.
gradle wrapper --gradle-version 9.9.0 --distribution-type bin --gradle-distribution-sha256-sum $sha
```

`$sha` là PowerShell variable; command khác lệnh Bash `sha=$(...)`. Chạy tại root project đã được review.

### 4.5. Phân biệt download checksum và JAR checksum

`distributionSha256Sum` của ZIP **không phải** hash của `gradle-wrapper.jar`. Hai tệp có định dạng/đường dẫn khác nhau:

| Artifact | Checksum official |
| --- | --- |
| `gradle-9.9.0-bin.zip` | `gradle-9.9.0-bin.zip.sha256` |
| `gradle-9.9.0-wrapper.jar` | `gradle-9.9.0-wrapper.jar.sha256` |

Cần kiểm tra **cả hai**. Wrapper JAR không tự xác minh chính nó trước khi chạy.

## 5. Kiểm tra gradle-wrapper.jar trước khi dùng

### 5.1. Linux/macOS

Ví dụ với Wrapper JAR của Gradle 9.9.0 đúng release:

```bash
expected=$(curl -fsSL \
  https://services.gradle.org/distributions/gradle-9.9.0-wrapper.jar.sha256 |
  tr -d '\r\n')

if command -v sha256sum >/dev/null 2>&1; then
  actual=$(sha256sum gradle/wrapper/gradle-wrapper.jar | cut -d ' ' -f1)
else
  actual=$(shasum -a 256 gradle/wrapper/gradle-wrapper.jar | cut -d ' ' -f1)
fi

if [ "$expected" != "$actual" ]; then
  echo 'Wrapper JAR checksum mismatch' >&2
  exit 1
fi
echo 'Wrapper JAR checksum OK'
```

Khi expected và actual khớp, command in:

```text
Wrapper JAR checksum OK
```

Đây là output **có điều kiện**, không phải bằng chứng bạn đã chạy validation trên repository thật. Nếu JAR khác version, so với official checksum của version tương ứng trước khi thay đổi.

### 5.2. PowerShell

```powershell
$expected = (Invoke-RestMethod -Uri 'https://services.gradle.org/distributions/gradle-9.9.0-wrapper.jar.sha256').Trim().ToLowerInvariant()
$actual = (Get-FileHash .\gradle\wrapper\gradle-wrapper.jar -Algorithm SHA256).Hash.ToLowerInvariant()

if ($expected -ne $actual) {
    throw 'Wrapper JAR checksum mismatch'
}
Write-Output 'Wrapper JAR checksum OK'
```

Nếu JAR hash không khớp, **không tự sửa expected hash sang actual**. Kiểm tra version mismatch, JAR release signatures, binary provenance và trusted source.

### 5.3. CI validation và chữ ký PGP

Gradle công bố Wrapper JAR signatures và SHA checksums. Có thể đối chiếu detached PGP signature với release signing key đã xác minh fingerprint. Không tin một public key chỉ vì tải nó từ key server với một tên giống publisher.

Trong GitHub Actions, **`gradle/actions/setup-gradle` v4+** thực hiện Wrapper JAR validation theo Gradle docs. Dù vậy reviewer vẫn cần xem `gradlew`, `gradlew.bat`, `gradle-wrapper.properties` và các build scripts: CI JAR validation không review mọi đoạn code khác.

### 5.4. Điều kiện first-download

Gradle Wrapper chỉ kiểm tra SHA ZIP khi distribution chưa được download/cached theo cơ chế Wrapper. Nếu distribution đã được xác minh và giải nén trước đó, nó được reuse trong các invocation sau; vì thế:

- Không hiểu `distributionSha256Sum` là “rehash mọi file distribution ở mọi build”.
- Bảo vệ Gradle User Home và remote/shared CI caches.
- Không sửa/xóa toàn bộ machine caches chỉ để chứng minh command đã chạy; khi muốn kiểm tra bootstrap trong CI, dùng fresh/isolated Gradle User Home có policy phù hợp.
- Nếu Wrapper báo distribution checksum mismatch, điều tra mirror/network/URL và expected hash từ trusted channel, không vô hiệu check.

## 6. Dependency verification — bảo vệ artifacts và metadata

### 6.1. Scope

Gradle dependency verification kiểm tra artifacts từ dependency engine, gồm JAR, ZIP, POM, Gradle Module Metadata, Ivy descriptors, plugin artifacts (bao gồm plugins trong plugin DSL, theo scope resolution) và một số advanced resolution APIs.

Một external module có thể có nhiều artifacts/metadata. Một Maven POM bị sửa có thể làm graph chứa transitive dependencies mới dù main JAR không đổi; metadata verification vì thế có giá trị thực.

**Giới hạn theo tài liệu Gradle:** locally generated artifacts và changing dependencies như SNAPSHOT không được bảo vệ theo cách tương tự immutable artifacts. Đừng nói dependency verification kiểm tra mọi file mà Gradle chạm đến.

### 6.2. Đặt verification-metadata.xml ở đâu?

```text
project/
├── settings.gradle
├── build.gradle
└── gradle/
    ├── verification-metadata.xml
    └── wrapper/
        ├── gradle-wrapper.properties
        └── gradle-wrapper.jar
```

Một khi `gradle/verification-metadata.xml` tồn tại, Gradle tự bật verification. Mode mặc định theo docs là **strict**: nếu artifact thiếu expected metadata hoặc checksum/signature sai, build có thể fail.

Trong một multi-project Gradle build, verification metadata ở root áp dụng cho các subprojects và `buildSrc`. Khi main build dùng `includeBuild`, docs nêu current/main build verification metadata chi phối invocation composite; verification metadata riêng của included build có thể bị bỏ qua khi nó là included build, nhưng dùng khi chạy build đó **độc lập**.

### 6.3. SHA-256 và PGP khác nhau

| Phương pháp | Chứng minh | Không chứng minh |
| --- | --- | --- |
| SHA-256 | Bytes artifact khớp một approved digest. | Baseline SHA ban đầu đến từ nguồn tốt hay publisher đáng tin. |
| PGP signature | File có signature tương ứng với một public key được trust. | Key không bị compromise; người ký không thể publish mã có lỗ hổng. |
| Cả hai | Integrity và provenance có thể được kiểm tra bổ sung. | Artifact an toàn tuyệt đối hoặc không có CVE. |

Ưu tiên SHA-256/SHA-512 thay MD5/SHA-1. Với PGP phải review key fingerprint/publisher identity, không auto-trust chỉ vì signature cryptographically valid.

### 6.4. Bootstrap checksum metadata

Sau khi xác minh Wrapper, chạy:

```bash
./gradlew help --write-verification-metadata sha256 \
  --console=plain
```

Windows:

```powershell
.\gradlew.bat help --write-verification-metadata sha256 --console=plain
```

Gradle tạo/cập nhật `gradle/verification-metadata.xml`. Generation có thể resolve artifacts của root/subprojects/plugins/buildSrc/included builds theo cơ chế Gradle; những artifact thực tế có mặt phụ thuộc build/plugins/configuration và invocation. Kiểm tra file kết quả, không suy đoán mọi dependency ở mọi task execution đã được bao phủ nếu cấu hình đặc biệt chưa được resolve.

Khi muốn thêm signature metadata:

```bash
./gradlew help --write-verification-metadata sha256,pgp \
  --console=plain
```

Gradle có thể ghi trusted/ignored signing keys trong bootstrap. Nếu signature không sẵn, checksum fallback có thể được dùng. **Không tự chấp thuận một signing key chỉ vì Gradle tìm thấy nó trên public key server.**

### 6.5. Trust-on-first-use — sai lầm nguy hiểm nhất

`--write-verification-metadata` ghi lại trạng thái những artifact bytes tại **thời điểm bootstrap**. Nếu repository đã compromised, tool cũng có thể ghi checksum **của artifact bị thay**. Vì vậy generation **không phải chứng nhận an toàn**.

Quy trình review sau generation:

1. Liệt kê direct/transitive artifacts mới, plugin artifacts/metadata.
2. Đối chiếu repositories với allowlist và mirror đã tin.
3. Kiểm tra hashes đối với các release quan trọng qua publisher checksums/signatures được xác minh độc lập.
4. Nếu dùng PGP, xác minh signing key fingerprint; không trust keys chỉ qua email hiển thị.
5. Review `git diff -- gradle/verification-metadata.xml`, gồm cả changes ở trusted keys, ignored keys, trust regex và metadata policy.
6. Không thêm `trusted-artifacts` wildcard rộng để tắt failures hàng loạt.
7. Chỉ commit sau khi reviewer hiểu provenance; CI chỉ **enforce**, không tự approve baseline mới.

### 6.6. Verification modes

| Mode | Behavior | Khuyến nghị |
| --- | --- | --- |
| `strict` (mặc định) | Verification failure dừng build càng sớm càng tốt. | Default cho CI/release. |
| `lenient` | Ghi lỗi nhưng cho phép build tiếp tục. | Chỉ diagnostic ngắn hạn có kiểm soát. |
| `off` | Bỏ qua verification. | Không dùng để sửa supply-chain incident. |

Command check strict:

```bash
./gradlew build --dependency-verification strict \
  --console=plain
```

Fragment khi điều tra tạm (không nên dùng làm release gate):

```bash
./gradlew build --dependency-verification lenient \
  --console=plain
```

Muốn lỗi verification hiển thị chi tiết hơn, có thể thêm vào `gradle.properties`:

```properties
org.gradle.dependency.verification.console=verbose
```

Báo cáo HTML verification có thể xuất hiện khi fail, đường dẫn sẽ được Gradle thông báo. Đừng in secrets hoặc nội dung private artifacts vào public CI logs khi chia sẻ báo cáo.

### 6.7. Các exception/điểm cần tránh

- Tắt metadata verification làm giảm bảo vệ trước POM/module metadata bị thay.
- Mark một group artifact là fully trusted có thể bỏ qua checksum cả nhóm.
- `--dependency-verification off` hoặc ignored keys/wide trusted rules làm an toàn giả.
- Không tự tin `--refresh-dependencies` giải quyết checksum mismatch; flag này recheck remote metadata/artifacts, **không chứng minh remote là trusted**.
- Dependency verification không thay vulnerability/license scanning hoặc source review.
- Một dependency cố định version nhưng artifact corrupt vẫn fail nếu expected hash khác; đó là **tính năng**, không phải “cache hỏng cần tắt verification”.

## 7. Dependency locking — khóa resolved version graph

### 7.1. Vì sao khai báo version chưa đủ?

Gradle resolve một cấu hình từ direct dependencies, BOM/platform constraints, transitive dependencies, dependency substitutions và conflict resolution. Version catalog chỉ tập trung **declared coordinates**, không tự persist phiên bản thực tế của mọi transitive artifact.

Locking ghi **selected versions** theo resolvable configuration để một build khác ở cùng lock state không âm thầm chọn graph mới.

### 7.2. Bật locking bằng Groovy DSL

Trong `build.gradle`:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Điều này áp dụng cho **project đang cấu hình**. Những configuration buckets không thể resolve như `implementation` không có lock state độc lập; `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath` là ví dụ resolvable configurations.

Trong multi-project, phải apply locking cho từng project cần bảo vệ qua convention plugin hoặc cấu hình có chủ đích. Không giả định root `lockAllConfigurations()` tự lan vào mọi included builds.

### 7.3. Tạo gradle.lockfile

```bash
./gradlew dependencies --write-locks --console=plain
```

Command ghi lock state cho các configurations có locking và đã resolve. Trong single-project, file thường là:

```text
project/
└── gradle.lockfile
```

Trong multi-project, mỗi project có lockfile riêng như `app/gradle.lockfile`, `core/gradle.lockfile`. `./gradlew dependencies` ở root **không tự chạy** task `:app:dependencies` và `:core:dependencies`; cần resolve từng project/configuration theo scope.

Một dòng trong generated lockfile có **dạng**:

```text
org.apache.commons:commons-lang3:3.17.0=compileClasspath,runtimeClasspath,testCompileClasspath,testRuntimeClasspath
```

Đây là ví dụ **một dòng cấu trúc**, không phải cam kết toàn bộ file thực có đúng thứ tự/tập configuration như vậy. Gradle ghi transitive/JUnit entries khác theo actual graph. Lockfile **không ghi SHA-256 của JAR**.

### 7.4. STRICT locking sau khi bootstrap

Có thể thay block ở mục 7.2 bằng:

```groovy
dependencyLocking {
    lockAllConfigurations()
    lockMode = LockMode.STRICT
}
```

`STRICT` yêu cầu locked configuration có lock state; nếu chưa khởi tạo state thì failure là hợp lý. Chỉ bật trên CI sau khi relevant lockfiles đã được tạo và reviewed.

- Default lock mode enforce các lockfiles đã có.
- STRICT còn fail khi một marked locked configuration thiếu state.
- LENIENT linh hoạt hơn khi thử versions, không phải release gate phù hợp.

**Đừng dán hai blocks locking với hai chính sách khác nhau**; phần trên là **biến thể thay thế**.

### 7.5. Buildscript/plugin versions không tự được khóa toàn bộ

`lockAllConfigurations()` trong project không tự lock legacy `buildscript classpath`. Khi còn dùng `buildscript { dependencies { classpath ... } }`, có thể thêm:

```groovy
buildscript {
    configurations.classpath {
        resolutionStrategy.activateDependencyLocking()
    }
}
```

Lock state tương ứng có thể nằm ở `buildscript-gradle.lockfile`. Gradle `plugins { id 'plugin.id' version '...' }` có plugin resolution/version policy riêng; project lockfile **không thay** việc pin plugin IDs/versions hoặc kiểm tra plugin artifacts.

### 7.6. Selective vs full lockfile updates

Cập nhật các configurations được resolve:

```bash
./gradlew dependencies --write-locks --console=plain
```

Cập nhật chọn lọc một module:

```bash
./gradlew dependencies \
  --update-locks org.apache.commons:commons-lang3 \
  --console=plain
```

`--update-locks` giữ lại lock state khác làm input và cho phép modules được nêu cập nhật. Nhưng transitive graph/constraints có thể khiến nhiều dòng thay đổi; luôn review diff.

**Không chỉnh tay lockfile để che build failure**. Gradle docs khuyên commit lockfiles vào version control và cập nhật qua resolution commands.

### 7.7. SNAPSHOT và changing modules

Lockfile cố định **version coordinates**, không cố định bytes. Module `1.0-SNAPSHOT` có thể bị republish cùng coordinate, làm build nhận binary khác dù file `gradle.lockfile` không đổi. Gradle docs khuyến cáo không dùng dependency locking với changing modules như một cam kết reproducibility. Ưu tiên immutable releases cho builds phát hành.

## 8. Lab Java 17+ có đủ ba lớp bảo vệ

### 8.1. Kết quả mong muốn

Tạo ứng dụng Java sử dụng Apache Commons Lang 3.17.0 và 2 JUnit Jupiter tests. Sau khi khởi tạo, project có:

```text
trusted-build-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle.lockfile
├── gradle/
│   ├── wrapper/
│   │   ├── gradle-wrapper.jar
│   │   └── gradle-wrapper.properties
│   └── verification-metadata.xml
└── src/
    ├── main/java/demo/App.java
    └── test/java/demo/AppTest.java
```

Cần Java 17+ compiler, Gradle 9.9.0 Wrapper được tạo và JAR được validate như mục 4–5, Internet/trusted Maven Central trong bước bootstrap ban đầu. Các bước **không cần tự bịa hoặc điền một SHA-256 bằng tay**.

### 8.2. settings.gradle

```groovy
rootProject.name = 'trusted-build-lab'
```

### 8.3. build.gradle đầy đủ

```groovy
plugins {
    id 'application'
}

group = 'demo'
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
    mainClass = 'demo.App'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

dependencyLocking {
    lockAllConfigurations()
}
```

Giải thích:

- `application` dùng Gradle core plugin, cung cấp `run` và JavaCompile/Test tasks.
- `commons-lang3` là dependency external, giúp minh họa dependency verification trên artifact thật.
- `junit-bom` đồng bộ JUnit versions nhưng không thay lock state của resolved configurations.
- `junit-jupiter` chứa API/engine, `junit-platform-launcher` hỗ trợ Gradle Test task chạy JUnit Platform.
- `options.release=17` target Java 17; không tự cài JDK.
- `lockAllConfigurations()` bật khóa resolvable configurations của **project đơn này**.

### 8.4. src/main/java/demo/App.java

```java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static String message(String name) {
        return StringUtils.capitalize("secure")
                + ", " + name + "!";
    }

    public static void main(String[] args) {
        String recipient =
                args.length == 0 ? "Gradle" : args[0];
        System.out.println(message(recipient));
    }
}
```

`StringUtils.capitalize("secure")` trả `Secure`, nên `App.message("Team")` trả `Secure, Team!`. App source không đọc trực tiếp XML/lockfile: chính Gradle resolver sử dụng chúng trước khi compile/test/run.

### 8.5. src/test/java/demo/AppTest.java

```java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void defaultGreeting() {
        assertEquals("Secure, Gradle!",
                App.message("Gradle"));
    }

    @Test
    void customGreeting() {
        assertEquals("Secure, Team!",
                App.message("Team"));
    }
}
```

**Hai JUnit tests**. Nhánh `test` còn resolve các JUnit artifacts/metadata, giúp verification/lockfiles bao phủ cả test dependency graph.

### 8.6. Quy trình bootstrap từng bước

**Bước 1 — Wrapper trust.** Dùng một trusted Gradle installation để tạo Wrapper 9.9.0 với official checksum bằng command mục 4.3/4.4. Kiểm tra `distributionSha256Sum` đã được ghi và validate `gradle-wrapper.jar` theo mục 5. **Chỉ sau đó** mới dùng Wrapper cho bước tiếp.

**Bước 2 — Tạo lock state.**

Linux/macOS:

```bash
./gradlew dependencies --write-locks --console=plain
```

Windows:

```powershell
.\gradlew.bat dependencies --write-locks --console=plain
```

Sau bước này `gradle.lockfile` được sinh cho configurations đã resolve. Review contents, không giả định mọi task-specific configuration đã covered nếu command chưa resolve chúng.

**Bước 3 — Tạo verification metadata.**

Linux/macOS:

```bash
./gradlew help --write-verification-metadata sha256 \
  --console=plain
```

Windows:

```powershell
.\gradlew.bat help --write-verification-metadata sha256 --console=plain
```

Gradle tạo `gradle/verification-metadata.xml`. **Đây là bootstrap, không phải kết quả một security audit**. Review checksum entries/metadata/repository provenance trước khi commit. Nếu policy yêu cầu signature verification, cân nhắc `sha256,pgp` với PGP key fingerprint review theo mục 6.

**Bước 4 — Review và commit.**

```bash
git status --short
git diff -- gradle.lockfile
git diff -- gradle/verification-metadata.xml
git diff -- gradle/wrapper/gradle-wrapper.properties
```

Các files mới **chưa tracked** không hiển thị đầy đủ trong `git diff` mặc định; dùng `git status` và mở file mới hoặc `git add -N` khi cần so diff. Commit Wrapper scripts/JAR/properties, verification metadata, lockfile và build files sau khi approved.

**Bước 5 — Chạy build/test dưới chế độ bảo vệ.**

```bash
./gradlew clean test run --dependency-verification strict \
  --console=plain
./gradlew -q run --args="Team"
```

Windows:

```powershell
.\gradlew.bat clean test run --dependency-verification strict --console=plain
.\gradlew.bat -q run --args="Team"
```

Stdout riêng của **Java main** trong lần chạy đầu không args:

```text
Secure, Gradle!
```

Stdout Java main ở invocation có `--args="Team"`:

```text
Secure, Team!
```

Đây là hai **invocations riêng**; Gradle còn in task logs/test outcomes. Dựa trên code, hai tests được kỳ vọng PASS nếu dependencies và môi trường hợp lệ; chỉ tuyên bố đã chạy thành công khi có kết quả Gradle thực tế.

### 8.7. Kiểm tra version đã resolve

```bash
./gradlew dependencyInsight \
  --dependency commons-lang3 \
  --configuration runtimeClasspath \
  --console=plain
```

`dependencyInsight` giải thích version selection; nó không tự chứng minh JAR bytes đáng tin. Đọc lockfile và verification-metadata.xml để kiểm tra **version** và **expected hash** tương ứng.

### 8.8. Bật STRICT locking khi bootstrap đủ

Thay block `dependencyLocking` bằng:

```groovy
dependencyLocking {
    lockAllConfigurations()
    lockMode = LockMode.STRICT
}
```

Chỉ làm sau khi các configurations cần giải quyết đã có lock state; STRICT sẽ fail nếu marked locked configuration thiếu state. Đừng thêm đoạn này **bên cạnh** block cũ như hai policy khác nhau.

## 9. Cập nhật dependencies mà không tự làm yếu security gate

Giả sử team duyệt nâng Commons Lang lên một release khác thật sự có trên trusted repository.

1. Tạo PR/branch, ghi lý do nâng và version mới.
2. Sửa dependency declaration hoặc version catalog (nếu dự án dùng catalog).
3. Resolve/update lock state qua `--write-locks` hoặc `--update-locks org.apache.commons:commons-lang3`.
4. Generate verification metadata mới qua `--write-verification-metadata sha256`; đối chiếu checksum/PGP/repository publisher.
5. Review **direct và transitive changes**. Một cập nhật direct module có thể đổi nhiều transitive versions.
6. Chạy strict verification/locking và test/build. Kiểm tra CVEs/license theo policy.
7. Commit cả dependency declaration, lockfiles và verification metadata **sau review**, không auto-merge changes do tool sinh.

Nếu lock state cũ từ chối version mới, dùng targeted update có mục đích. Nếu verification cũ từ chối artifact mới, bootstrap thêm hashes rồi **review**. Không sửa bằng cách vĩnh viễn đặt `--dependency-verification off` hoặc xoá `gradle.lockfile`.

### 9.1. --write-locks và --write-verification-metadata không giống nhau

| Command | Thay đổi gì? |
| --- | --- |
| `--write-locks` | Ghi lại resolved module versions cho configurations bật locking. |
| `--update-locks group:module` | Selectively update allowed modules trong lock state. |
| `--write-verification-metadata sha256` | Bổ sung/cập nhật expected artifact/metadata hashes. |
| `--write-verification-metadata sha256,pgp` | Bootstrap hashes/signatures, có thể tạo trusted/ignored key metadata cần review. |
| `--refresh-dependencies` | Recheck remote dependency resolution/metadata, **không tự là trust audit**. |

**Quan trọng:** `--refresh-dependencies` không bắt buộc tải lại mọi JAR bytes nếu remote metadata/checksum cho thấy artifact không đổi. Nếu artifact cùng immutable version có bytes mới bất thường, ưu tiên điều tra repository/supply-chain thay vì chấp nhận một hash mới ngay.

### 9.2. PGP key rotation

Khi publisher đổi signing key, verify fingerprint qua nguồn publisher chính thức, không chỉ dựa vào email/user ID trên key server. Gradle hỗ trợ keyrings/__`--export-keys` để hạn chế key server lookup khi kiểm tra, nhưng public keyring không tự chứng minh key owner trusted. Các trusted/ignored key entries trong XML phải có lý do và review.

## 10. Nâng cấp Gradle Wrapper an toàn

Khi team quyết định nâng từ Gradle 9.9.0 lên một phiên bản khác:

1. Đọc release notes, JDK/Gradle/plugin compatibility và migration guide.
2. Lấy SHA-256 đúng **version + distribution type** từ official Gradle release checksums.
3. Tạo/nâng Wrapper bằng **trusted Gradle**, không dùng JAR chưa verify từ untrusted checkout.
4. Đảm bảo `distributionUrl` pin đúng bản ZIP và `distributionSha256Sum` khớp.
5. Verify `gradle-wrapper.jar` theo checksum/signature cho version tương ứng; review scripts.
6. Kiểm tra `./gradlew --version` chỉ sau bước validate ban đầu.
7. Chạy build/test với strict verification và lock state. Nếu Gradle version đổi resolution behavior, review files cần update.
8. Commit các Wrapper files trong PR có reviewer hiểu security impact.

Nếu `wrapper` task báo checksum mismatch sau khi đổi distribution, kiểm tra xem phiên bản ZIP/JAR có được cập nhật đồng bộ chưa. Đừng lấy một JAR hash không rõ nguồn và thêm vào allowlist cho nhanh.

**Lưu ý:** `distributionSha256Sum` của Wrapper không phải cùng giá trị với SHA của downloaded Maven JAR; không copy giữa hai hệ thống.

## 11. Version catalog, BOM, locking và verification

| Công cụ | Quản lý cái gì? | Đã cố định resolved graph? | Verify artifact bytes? |
| --- | --- | --- | --- |
| `libs.versions.toml` Version Catalog | Aliases và requested versions. | Không. | Không. |
| BOM/platform | Version constraints/alignment. | Không lưu lock graph. | Không. |
| Dependency constraints | Quy tắc lựa chọn version. | Không tự persist resolved versions. | Không. |
| Dependency locking | Resolved versions của configurations đã khóa. | Có, trong phạm vi lock state. | Không. |
| Dependency verification | Approved SHA-256/PGP cho artifacts/metadata. | Không. | Có cho supported artifacts. |
| Wrapper checksum | Expected Gradle distribution ZIP SHA-256. | Không liên quan module versions. | Verify Gradle ZIP khi downloaded. |

Ví dụ một catalog khai báo Commons Lang 3.17.0, nhưng một platform/constraint có thể ảnh hưởng actual resolver choice. Lockfile lưu version **được chọn thật**, còn verification metadata kiểm tra bytes của artifact tương ứng.

### 11.1. Plugin resolution và included builds

Các plugin IDs trong `plugins { id '...' version '...' }` cần version policy riêng; project `lockAllConfigurations()` không thay pinning plugin versions.

Dependency verification có thể kiểm tra plugin artifacts/metadata tải qua Gradle dependency management; nhưng plugin build local, init script hoặc source code đã được review vẫn có thể chạy executable build logic. Nếu dùng included builds trong composite, review verification configuration context (main/current build áp dụng theo Gradle docs), còn **lock state** lưu theo project/configuration, không tự tập trung vào một file toàn cục.

## 12. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Bước xử lý |
| --- | --- | --- |
| Wrapper ZIP SHA mismatch | Chọn sai `bin/all`, wrong version, mirror cung cấp bytes khác hoặc tampering. | Kiểm official checksums/URL; không chấp nhận actual hash chưa xác thực. |
| Wrapper JAR checksum mismatch | JAR còn version cũ, bị sửa hoặc được tạo từ untrusted Gradle. | Xem provenance/version, tạo lại từ trusted Gradle, validate với official JAR checksum. |
| `distributionSha256Sum` tồn tại nhưng cached distribution bị thay | Wrapper không rehash từng invocation. | Harden Gradle User Home/CI caches; isolate/hardened runner. |
| `verification-metadata.xml` không sinh | Chưa dùng write-verification command hoặc build fail trước generation. | Xem logs/Gradle invocation, chạy trên trusted Wrapper. |
| Verification reports missing metadata | Dependency/plugin artifacts mới chưa trong approved XML. | Review coordinate/repository và bootstrap entry mới có kiểm soát. |
| Verification reports incorrect checksum | Bytes đổi hoặc baseline sai. | Dừng, kiểm provenance/mirror/cache/incident; không tắt verification. |
| PGP key untrusted/absent | Signer key chưa trust hoặc signature unavailable. | Verify publisher fingerprint, checksum fallback khi phù hợp. |
| CI strict fail nhưng local lenient PASS | Local đã nới mode. | Đồng bộ strict policy, xử lý root cause thay vì downgrade CI. |
| Lockfile không được tạo | Chưa bật locking hoặc chưa resolve configuration với write-locks. | Bật scope đúng, chạy resolution task phù hợp. |
| STRICT locking báo missing state | Configuration chưa được bootstrap. | Khởi tạo lockfile cho relevant configurations. |
| Version conflict so với lock state | Direct version/BOM/constraint/transitive graph thay đổi. | dependencyInsight + approved update-locks, review diff. |
| Lockfile không bao phủ `:app` | Chỉ root được bật/resolve. | Apply project-level policy, chạy `:app:dependencies` tương ứng. |
| Lockfile không chặn SNAPSHOT republish | Coordinate không đổi nhưng binary có thể đổi. | Immutable releases/verification/trusted repositories. |
| buildscript plugin không locked | Project lockAll không áp legacy buildscript classpath. | Activate classpath locking riêng, review buildscript lockfile. |
| Plugin marker version khác mong muốn | Plugin management/version policy khác project dependencies. | Pin plugin requests và review plugin artifacts. |
| CI `--offline` thiếu dependency | Chưa có artifacts trong cache; offline không tự tải. | Warm trusted cache/artifact repo, không xóa verification. |
| Verification passes nhưng CVE vẫn tồn tại | Integrity khác vulnerability. | Chạy vulnerability scanning và dependency upgrade policy. |
| XML có `trusted-artifacts` wildcard quá rộng | Exception bỏ qua verification trên nhiều artifacts. | Thu hẹp exception và review owner/lý do. |

### 12.1. Chẩn đoán theo lớp

**Wrapper failure:** trước hết xét distribution URL, SHA, trusted JAR và Gradle User Home. **Dependency verification failure:** xem artifact/metadata/version/repository/hash/signature và XML entry. **Locking failure:** xem resolver selected version, constraints và lock state. **Java compiler/test failure:** kiểm JDK/source/dependency graph, đừng sửa checksum một cách vô cớ.

Khi có nhiều lỗi, xử lý **theo thứ tự trust chain**: Wrapper → Gradle/plugin resolution → external dependency verification → version locking → task compilation/tests.

## 13. CI và code review: bảo vệ nguồn dữ liệu tin cậy

### 13.1. Pre-execution gate trên pull request

Trước khi chạy build logic của PR không tin cậy:

1. Checkout repository bằng job có **quyền tối thiểu**, không cấp production signing/deploy credentials.
2. Validate Wrapper JAR từ trusted tooling/action độc lập; kiểm cả `gradlew`/`gradlew.bat` và pinned distribution URL/SHA.
3. Review settings/build scripts, `buildSrc`, included builds, init scripts và plugin repositories.
4. Chỉ sau validation mới chạy `./gradlew`. IDE imports và CI plugins cũng có thể execute Gradle code.

### 13.2. Build execution gate

1. Chạy Wrapper/JVM version đã pin.
2. Enforce dependency verification `strict` với committed XML.
3. Resolve locked configurations; dùng STRICT lock mode khi organization đã bootstrap đủ.
4. Chạy `test`/`build` và các quality tasks thực tế.
5. Chạy vulnerability scanning/secret scanning/SBOM theo policy.
6. Fail release nếu có unexpected lockfile/XML/JAR changes chưa được reviewed.
7. Không cho CI tự generate verification metadata rồi tự merge PR.

### 13.3. Review matrix

| Changed file | Câu hỏi reviewer cần trả lời |
| --- | --- |
| `gradle-wrapper.properties` | URL/pinned ZIP/version/SHA official đúng? |
| `gradle-wrapper.jar` | Binary checksum/signature thuộc release thật? |
| `gradlew`, `gradlew.bat` | Không có executable code lạ? |
| `build.gradle`/version catalog | Dependency/plugin version mới đã approved? |
| `gradle.lockfile` | Direct/transitive resolved versions đổi thế nào? |
| `gradle/verification-metadata.xml` | New hashes/keys có publisher provenance? Exceptions có quá rộng? |
| `settings.gradle`/plugin repos | Repositories, included build code, settings plugins được trust? |

**Không** coi một PR “chỉ đổi checksum/XML” là vô hại. Attacker có thể cập nhật cả artifact coordinate và trust metadata nếu review không kiểm tra.

### 13.4. Cache và credentials không được bảo vệ tự động

Các cơ chế trên không ngăn untrusted Gradle plugin truy cập environment/file permissions được runner cấp. Bảo vệ Gradle User Home, remote build cache, CI toolchains và network egress. Không commit credentials vào `gradle.properties`; sử dụng CI secrets, credential providers và least privilege. Với untrusted PR/forks, dùng isolated runner không có secrets.

## 14. Bài tập thực hành

**Bài 1 — ZIP vs JAR.** `distributionSha256Sum` kiểm tra Gradle ZIP hay Wrapper JAR? **ZIP**. Phải verify JAR riêng trước khi chạy code chưa trust.

**Bài 2 — Checksum nguồn chính thức.** Vì sao không lấy SHA từ ZIP đã bị nghi compromise rồi commit? Vì sẽ hợp thức hóa chính bytes độc hại.

**Bài 3 — Bản bin/all.** Tại sao SHA của `gradle-9.9.0-all.zip` không hợp cho `gradle-9.9.0-bin.zip`? Vì bytes khác nhau.

**Bài 4 — Cached distribution.** Wrapper có rehash toàn bộ installed ZIP mỗi build không? Không theo cơ chế first-download, nên cần bảo vệ Gradle User Home.

**Bài 5 — Bootstrap XML.** Chạy `--write-verification-metadata sha256` có chứng minh publisher trusted chưa? Chưa, cần review nguồn.

**Bài 6 — Same version, different bytes.** Lockfile phát hiện không? Không; dependency verification kiểm hash/signature.

**Bài 7 — New dynamic version.** Nếu selector đổi resolved version, lớp nào giữ graph? Dependency locking.

**Bài 8 — POM metadata.** POM bị thay transitive graph dù JAR chính không đổi. Vì sao metadata verification hữu ích? Vì POM cũng là input resolution có thể bị can thiệp.

**Bài 9 — PGP key.** Signature đúng nhưng key không trusted. Có auto-trust không? Không, xác minh fingerprint publisher.

**Bài 10 — STRICT mode.** Vì sao `LockMode.STRICT` fail khi configuration thiếu lock state? Bởi chính sách yêu cầu lock state trước resolution.

**Bài 11 — Version catalog.** `libs.versions.toml` có thay gradle.lockfile không? Không, aliases/declared versions khác resolved graph.

**Bài 12 — BOM.** JUnit BOM 5.11.4 có pin hết transitive versions ở mọi module không? Không; locking vẫn hữu ích.

**Bài 13 — Update dependency.** Sau khi nâng Commons Lang, review ít nhất ba files nào? `build.gradle`/catalog, `gradle.lockfile`, `gradle/verification-metadata.xml`.

**Bài 14 — Included build.** Vì sao verification metadata của root composite cần review khi include plugin build mới? Vì included build có thể mang dependency/plugin artifacts mới vào invocation.

**Bài 15 — Multi-project.** Chỉ lock root có bảo vệ `:app` không? Không tự động; cần policy/project-level lock state.

**Bài 16 — Buildscript classpath.** Project `lockAllConfigurations()` đã tự khóa legacy buildscript plugin deps chưa? Chưa.

**Bài 17 — SNAPSHOT.** Vì sao lockfile không bảo đảm binary immutable? SNAPSHOT cùng coordinate có thể republish.

**Bài 18 — Version conflict.** Tool nào giúp giải thích selected module version? `dependencyInsight`, sau đó review lock/constraints.

**Bài 19 — CI.** Vì sao không auto-merge generated verification-metadata.xml từ PR? Vì baseline mới có thể là poisoned artifact hash.

**Bài 20 — Security.** Ba layers pass nhưng JAR vẫn có CVE. Điều đó có hợp lý không? Có; integrity/version locking khác vulnerability scanning.

### Tự kiểm tra

1. **Wrapper ZIP checksum property?** `distributionSha256Sum`.
2. **Wrapper JAR auto self-verifies?** Không.
3. **Gradle checksum release page?** `https://gradle.org/release-checksums/`.
4. **Verification metadata file?** `gradle/verification-metadata.xml`.
5. **Bootstrap checksum flag?** `--write-verification-metadata sha256`.
6. **Bootstrap PGP flag?** `--write-verification-metadata sha256,pgp`.
7. **Verification mode mặc định?** Strict.
8. **Lenient là release gate an toàn?** Không.
9. **Locking activation?** `dependencyLocking { lockAllConfigurations() }`.
10. **Write lock state?** `--write-locks`.
11. **Selective update?** `--update-locks group:module`.
12. **Project lockfile?** `gradle.lockfile`.
13. **Buildscript lockfile?** `buildscript-gradle.lockfile` nếu classpath locking được bật.
14. **STRICT tăng gì?** Fail nếu locked configuration chưa có state.
15. **Version catalog có lock transitive graph không?** Không.
16. **SHA-256 có xác nhận artifact không có CVE?** Không.
17. **Version lock có nhận biết JAR bị republish không?** Không.
18. **Cần commit generated files?** Có, sau provenance review.
19. **CI untrusted PR có nên được cấp signing key?** Không.
20. **Ba lớp có thay thế code review không?** Không.

## 15. Tài liệu tham khảo chính thức

- **Gradle Wrapper:** distribution SHA-256, wrapper tasks, JAR validation và first-download behavior: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- **Securing the Build Tool:** trust boundaries của Wrapper, init scripts, untrusted checkouts và Gradle User Home: https://docs.gradle.org/current/userguide/securing_build_tool.html
- **Official Gradle Release Checksums:** SHA của distribution ZIP và Wrapper JAR: https://gradle.org/release-checksums/
- **Gradle Dependency Verification:** checksum/PGP, XML, bootstrap, modes, scope và failure handling: https://docs.gradle.org/current/userguide/dependency_verification.html
- **Gradle Dependency Locking:** --write-locks, --update-locks, lockAllConfigurations, lock modes, per-project files: https://docs.gradle.org/current/userguide/dependency_locking.html
- **Gradle Dependency Caching:** cached metadata/artifacts, dynamic/changing module TTL: https://docs.gradle.org/current/userguide/dependency_caching.html
- **Gradle Version Catalogs:** aliases khác selected graph: https://docs.gradle.org/current/userguide/version_catalogs.html
- **Gradle Dependency Constraints:** version conflict/resolution: https://docs.gradle.org/current/userguide/dependency_constraints.html
- **Gradle Security Best Practices:** Wrapper checksums, validation, trust/repository hygiene: https://docs.gradle.org/current/userguide/best_practices_security.html
- **Gradle Command-Line Interface:** dependency/locking/diagnostic CLI flags: https://docs.gradle.org/current/userguide/command_line_interface.html
- **Gradle Java Testing:** Java/JUnit Platform Test task: https://docs.gradle.org/current/userguide/java_testing.html

**Kết luận:** Hãy **xác minh Gradle Wrapper scripts/JAR và pin distribution SHA-256 trước khi chạy**, **xác minh bytes/metadata của external dependencies bằng verification-metadata.xml** rồi **khóa resolved module versions bằng gradle.lockfile**. Một lớp bảo vệ công cụ, một lớp bảo vệ nội dung artifact, một lớp bảo vệ version graph. Security phụ thuộc cả trust source, code review, immutable versions, strict CI enforcement và việc không tự chấp nhận generated hashes chưa được review.