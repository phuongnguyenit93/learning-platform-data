# Kế hoạch rollback và quản lý thay đổi lockfile, verification metadata trong Gradle

## 1. Vì sao nâng cấp Gradle phải có kế hoạch quay lui?

Một pull request (PR) nâng cấp dependency thường thay nhiều thứ cùng lúc: phiên bản khai báo trong `build.gradle` hoặc version catalog, phiên bản thực tế của transitive modules trong `gradle.lockfile`, checksums/chữ ký trong `gradle/verification-metadata.xml`, đôi khi cả Gradle Wrapper, plugin versions và Java toolchains. Nếu chỉ quay lại một file, build có thể vẫn fail hoặc, nguy hiểm hơn, vô tình chấp nhận artifact không đáng tin.

**Rollback** là đưa hệ thống về một **trạng thái đã biết, được xác minh và được phép triển khai**, không phải xóa file gây lỗi rồi bật chế độ lenient/off để Gradle chịu chạy. **Quản lý thay đổi** là giữ cho dependency graph, artifact trust baseline, build logic, CI và deployment đi cùng một quyết định nâng cấp hoặc hạ cấp.

Bài thuộc **Build Tool Gradle → Nâng cấp và di chuyển**. Sau bài này, bạn sẽ:

1. Phân biệt vai trò `gradle.lockfile` và `gradle/verification-metadata.xml` trong reproducibility và integrity.
2. Thiết kế baseline “known-good” gồm source commit, Gradle Wrapper, JDK/plugin matrix, dependencies, lockfiles, verification metadata/keyrings, CI results và artifact release.
3. Biết cập nhật lockfile bằng `--write-locks` hoặc `--update-locks`, không vô tình ghi lại cả graph ngoài ý muốn.
4. Biết thêm/check verification entries qua `--write-verification-metadata sha256`, `sha256,pgp` và preview `--dry-run` với review bắt buộc.
5. Phân biệt failure do **version graph mismatch**, **missing verification entry**, **incorrect SHA/signing key** và **Gradle/plugin/JDK incompatibility**.
6. Lập runbook rollback bằng `git revert` trên branch mới, review toàn bộ file liên quan, kiểm tra `--dependency-verification strict`, test và release.
7. Biết trường hợp **không được quay về bản cũ** (phiên bản đã bị compromise/CVE, security policy đổi) và phải chọn **forward fix** an toàn.
8. Hiểu khác biệt giữa quay lại **source/build definition**, quay lại **CI runtime** và rollback **artifact đã triển khai**.
9. Tự chạy lab Java 17+ với Gradle Groovy DSL, Commons Lang, JUnit Jupiter và một lần nâng từ `3.16.0` lên `3.17.0` rồi mô phỏng rollback.
10. Tạo checklist và bằng chứng để reviewer/CI có thể xác định rollback thật sự khôi phục một state nhất quán.

**Giới hạn bảo mật:** Lockfile cố định **version được resolve**, verification metadata kiểm tra **artifact bytes/metadata/chữ ký** và Wrapper checksum kiểm tra **Gradle distribution**. Không cơ chế nào thay thế code review, dependency vulnerability scanning, policy repository, credential hygiene hoặc quản trị release.

## 2. Hai file trung tâm: khác nhiệm vụ, phải thay đổi đồng bộ

| Thành phần | Lưu gì? | Giúp gì? | Không giúp gì? |
| --- | --- | --- | --- |
| `gradle.lockfile` | Resolved `group:name:version` và các configurations có module đó. | Ngăn resolved version graph trôi ngoài trạng thái đã review. | Không lưu SHA-256, không chứng minh artifact bytes đúng. |
| `gradle/verification-metadata.xml` | Expected checksums, trusted PGP keys, signatures/exceptions và verification policy cho dependencies/artifacts/metadata. | Phát hiện artifact/POM bytes không khớp approved baseline; kiểm chứng signatures theo trust configuration. | Không cố định dynamic version và không chứng minh baseline đã sinh từ nguồn sạch. |
| `build.gradle`/`libs.versions.toml` | Declared dependencies, aliases, constraints, platforms và plugin requests. | Diễn tả **mong muốn** của build. | Không lưu toàn bộ transitive graph, không hash JAR. |
| `gradle-wrapper.properties`/Wrapper JAR | Distribution URL/version, `distributionSha256Sum` và launcher. | Pin và xác minh Gradle tool được dùng. | Không thay dependency verification và không tự kiểm tra Wrapper JAR. |
| Signing keyring (nếu dùng) | Public PGP keys được export, ví dụ `gradle/verification-keyring.gpg`. | Giảm keyserver dependency và hỗ trợ signature verification. | Không tự xác thực fingerprint hoặc trust policy. |

**Ví dụ đổi dependency:** ứng dụng khai báo `commons-lang3:3.16.0`, lockfile chứa đúng 3.16.0 và verification metadata có SHA của JAR/POM 3.16.0. Nếu developer chỉ đổi khai báo thành `3.17.0`:

- Existing lock state có thể vẫn ép version 3.16.0 hoặc làm resolution fail do strict lock constraint.
- Nếu resolver được cho phép chọn 3.17.0 nhưng verification metadata chưa có artifact/metadata tương ứng, **strict verification** có thể fail.
- Nếu tự thay XML checksum dựa vào bytes tải từ nguồn không tin cậy, CI có thể PASS với một artifact độc hại.
- Nếu tắt verification/locking để deploy 3.17.0, bạn đã bỏ security controls đúng lúc cần chúng nhất.

Điều cần review là **một change set nhất quán**, không một file đơn lẻ.

### 2.1. Mô hình “ba loại trạng thái”

```text
SOURCE STATE (Git)
  build.gradle / version catalogs / settings / plugin versions
  gradle.lockfile của các project
  gradle/verification-metadata.xml và public PGP keyring
  Gradle Wrapper files / Gradle properties / CI configuration
                       |
                       v
RESOLUTION + BUILD STATE
  Selected versions per configuration
  External artifact bytes/signatures
  Gradle/JDK/compiler/plugin runtime
  Tests, build reports, published JARs
                       |
                       v
DEPLOYED STATE
  Release artifact identifier/digest
  Environment, config, feature flags, compatible DB schema
  Runtime monitoring, user impact
```

Rollback Git **không tự rollback** artifact đã deploy, một database migration hoặc secret/key đã rotate. Tách ba trạng thái trong runbook để người vận hành không đánh đồng “CI PASS ở commit cũ” với “production đã quay về”.

## 3. Baseline known-good: cần khóa những thông tin nào?

Trước khi sửa dependency/Gradle Wrapper, hãy ghi một **baseline manifest**. Không cần invent version hay checksum: thu thập bằng lệnh sau khi đã xác minh Wrapper/repository đáng tin.

| Nhóm | Phải lưu | Vì sao |
| --- | --- | --- |
| Source control | Git commit SHA, protected branch/tag, PR/release ID. | Quay về **đúng trạng thái** thay vì nhớ mơ hồ “hôm qua còn chạy”. |
| Gradle Wrapper | `gradlew`, `gradlew.bat`, `gradle-wrapper.jar`, properties và pinned ZIP SHA. | Gradle version/scripts khác có thể thay cách resolve/execute. |
| JVM & toolchains | Daemon JVM, Java toolchain target, JDK vendor/version, CI runner. | Rollback build files vẫn có thể fail khi runner/JDK đã đổi. |
| Plugins/build logic | Plugin IDs/versions, `pluginManagement`, included builds, `buildSrc`, init scripts. | Plugin incompatibility có thể không nằm trong dependency lockfile. |
| Declared deps | build scripts, version catalogs, BOMs, constraints và repositories. | Giải thích lý do version selection thay đổi. |
| Resolved graph | `gradle.lockfile` của từng project, buildscript lockfiles nếu có. | Baseline versions, direct và transitive. |
| Artifact trust | `gradle/verification-metadata.xml` và PGP keyrings/policy nếu dùng. | Baseline checksums/trusted keys. |
| CI evidence | `test`, `check`, integration/functional tests, strict verification, target JDK/OS. | Biết baseline thật sự **đã được kiểm thử**. |
| Release artifact | Build artifact digest, registry/tag, publish job, deployment revision. | Rollback deployment không phụ thuộc việc rebuild lại không byte-identical. |
| Security review | Publisher/repo provenance, vulnerability/license decision, change approval. | “Known-good” phải **được phép dùng**, không chỉ compile được. |

### 3.1. File/folder thường liên quan

```text
repo/
├── settings.gradle
├── build.gradle
├── gradle.properties
├── gradle.lockfile
├── gradle/
│   ├── libs.versions.toml
│   ├── verification-metadata.xml
│   ├── verification-keyring.gpg           (nếu dùng)
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── gradlew
├── gradlew.bat
├── app/
│   ├── build.gradle
│   └── gradle.lockfile
├── build-logic/                             (nếu included build)
└── .github/workflows/                       (nếu dùng GitHub Actions)
```

Đây là **cây ví dụ**, không phải mọi Gradle project có tất cả các file này. Không thêm một file keyring giả nếu đang dùng checksum-only. Trong composite/multi-project build, kiểm tra file verification ở **current/main build** và lockfiles theo **project/configuration**; không giả định có một lockfile toàn cục.

### 3.2. Snapshot bằng Git và evidence

Linux/macOS:

```bash
git status --short
git rev-parse HEAD
git log -1 --format='%h %s'
./gradlew --version
./gradlew projects --console=plain
./gradlew help --warning-mode=all --console=plain
```

Windows PowerShell:

```powershell
git status --short
git rev-parse HEAD
git log -1 --format='%h %s'
.\gradlew.bat --version
.\gradlew.bat projects --console=plain
.\gradlew.bat help --warning-mode=all --console=plain
```

**Chỉ chạy Gradle commands khi checkout/Wrapper đã được xác minh**: `help`/`projects` vẫn execute build configuration code. `git status` có thể hiển thị untracked/dirty changes; baseline phải chỉ rõ worktree có sạch không trước khi diễn giải kết quả.

Một “successful build” ở developer laptop **không thay** CI matrix hoặc release acceptance. Lưu command, task request, Gradle/JDK, dependency graph và report kết quả thật. Không gắn nhãn baseline `PASS` nếu chưa thực thi tests tương ứng.

## 4. Dependency locking: cơ chế và phạm vi rollback

### 4.1. Bật locking đúng phạm vi

Trong `build.gradle` của project (Groovy DSL):

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Nó đánh dấu **resolvable configurations** trong project để có lock state. `implementation` là declaration bucket, còn `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath` là các configurations thường resolve của Java plugin.

Trong multi-project:

- `app/gradle.lockfile` và `lib/gradle.lockfile` có thể khác nhau.
- Phải bật locking cho từng subproject liên quan, ví dụ qua convention plugin; root project config **không tự bao phủ tất cả**.
- `./gradlew dependencies --write-locks` trên root giải quyết configurations của **root task/project**, không tự chạy `:app:dependencies` hoặc included build tasks.
- Legacy `buildscript.classpath` có thể cần `resolutionStrategy.activateDependencyLocking()` riêng; lockfile đặc thù `buildscript-gradle.lockfile`.
- `plugins { id '...' version '...' }` có plugin management/version declaration riêng; project lockfile không thay version policy plugin.

### 4.2. --write-locks là thao tác rộng

```bash
./gradlew dependencies --write-locks --console=plain
```

Theo Gradle docs, command **ghi lại lock state cho mỗi configuration được resolve trong invocation**; nếu state đã có, các entries tương ứng **được ghi đè**. Đây là lựa chọn thích hợp cho bootstrap hoặc một upgrade nhiều dependencies đã được chấp thuận, nhưng là lựa chọn **rủi ro** khi PR dự định chỉ thay một module.

Nếu build có 20 modules, một root `dependencies` không tự khóa tất cả. Cũng có configurations được resolve **chỉ trong task execution**, không được kích hoạt bởi lệnh báo cáo thông thường. Cần danh sách project/tasks/configurations để đo đủ phạm vi.

### 4.3. --update-locks là thao tác mục tiêu

```bash
./gradlew dependencies \
  --update-locks org.apache.commons:commons-lang3 \
  --console=plain
```

Gradle giữ lock state hiện có cho phần còn lại khi giải quyết những modules được chỉ định. Nhiều modules có thể phân tách bởi dấu phẩy (theo docs), ví dụ:

```bash
./gradlew dependencies \
  --update-locks org.apache.commons:commons-lang3,org.slf4j:slf4j-api \
  --console=plain
```

**Không hứa diff chỉ đổi một dòng.** Một module nâng phiên bản có thể kéo theo transitive constraints, variants, BOM alignments và dependency conflicts, làm nhiều versions trong graph phải đổi. Hãy đọc cả **dòng mới, dòng biến mất và danh sách configurations bị ảnh hưởng**.

### 4.4. Chế độ STRICT và behavior của lock

Nếu baseline đã được bootstrap đầy đủ, có thể chọn:

```groovy
dependencyLocking {
    lockAllConfigurations()
    lockMode = LockMode.STRICT
}
```

Đây là **biến thể thay thế** block ban đầu, không dán thành hai blocks cạnh nhau. STRICT ngoài việc enforce locked versions còn **fail nếu marked locked configuration thiếu lock state**. Đừng bật STRICT rồi giả định mọi configuration đã được bootstrap.

Theo Gradle docs, locked version là strict constraint; declared version thấp hơn có thể bị **nâng lên locked version**, còn declared version cao hơn locked version có thể **làm resolution fail**. Vì thế “sửa build.gradle trở lại version cũ” nhưng quên lockfile không bảo đảm resolver chọn đúng version cũ.

### 4.5. Version catalog, BOM và SNAPSHOT không thay khóa

- `libs.versions.toml` là nơi tập trung **requested versions/aliases**; lockfile ghi **selected versions** thực tế.
- BOM/platform đặt version constraints, không tự persist mọi resolved version.
- Version `1.+` hoặc range có thể resolve thay đổi theo thời gian; locking giúp cố định phiên bản đã chấp thuận.
- `SNAPSHOT`/changing module có thể republish **cùng coordinate** với bytes mới; lockfile không bảo vệ byte-for-byte. Gradle docs khuyên tránh changing modules trong quy trình reproducibility đòi hỏi tính bất biến.
- Dependency substitution/project dependencies và local generated artifacts nằm ngoài bảo đảm “external immutable module bytes” từ lockfile.

## 5. Dependency verification: quản lý trust metadata khi thay đổi

### 5.1. verification-metadata.xml bảo vệ điều gì?

Khi `gradle/verification-metadata.xml` hiện diện tại root build, Gradle tự bật dependency verification theo cấu hình. Nó có thể kiểm tra:

- JAR/ZIP artifacts từ Gradle dependency management.
- POM/Ivy descriptors/Gradle Module Metadata.
- Settings/project plugin artifacts (plugin marker/implementation metadata khi Gradle resolve).
- Các artifacts resolve từ advanced dependency management APIs.

**Giới hạn:** Gradle không verify changing dependencies kiểu SNAPSHOT hay locally produced artifacts theo cùng cơ chế. Một XML trống khi project có external deps không phải “bảo mật cao hơn”: strict verification sẽ fail vì thiếu expected hashes.

Dependency verification mặc định **strict** khi metadata được bật. Modes `lenient` hoặc `off` có thể hỗ trợ debug nhưng không nên là release policy.

### 5.2. Bootstrapping không phải xác thực publisher

```bash
./gradlew help \
  --write-verification-metadata sha256 \
  --console=plain
```

Gradle resolve artifacts có thể nhận diện rồi sinh/cập nhật `gradle/verification-metadata.xml`. Theo docs, sau generation, checksum entries có thể có:

`origin="Generated by Gradle"`

Điều này báo rằng hash được **sinh từ artifact đã tải**, chưa phải bằng chứng publisher đáng tin. Nếu repository bị compromise lúc bootstrapping, XML có thể ghi hash của file độc hại.

Review đòi hỏi:

1. Xác định group/name/version và artifact file `.jar`/`.pom`/`.module` mới.
2. Kiểm repository provenance/allowlist và expected publisher.
3. Cross-check publisher checksum/signing key qua kênh độc lập khi có.
4. Nếu dùng PGP, verify fingerprint/trust relation, không tin một key chỉ vì tìm thấy trên key server.
5. Review ignored keys/trusted keys/trusted-artifacts exceptions; không nới wildcard để che lỗi.
6. Ghi rationale/approver trong PR hoặc policy file.
7. Chỉ sau review thật sự mới dùng annotation `origin="Verified"` nếu policy yêu cầu. **Đổi origin string chỉ là annotation, không tự thực hiện kiểm tra mật mã**.

### 5.3. Cập nhật metadata theo hướng incremental

```bash
./gradlew help \
  --write-verification-metadata sha256 \
  --console=plain
```

Theo Gradle docs, bootstrap **incremental**: nó thêm metadata cần thiết và giữ nhiều entries hiện có, **không tự phát hiện để xóa hết artifact versions đã lỗi thời**.

Hệ quả cho management/rollback:

- Sau khi nâng từ `3.16.0` lên `3.17.0`, XML có thể chứa entries cho **cả hai**.
- Giữ entries cũ có thể hỗ trợ rollback ngay, nhưng cũng làm trust surface/size lớn nếu không có retention policy.
- Xóa entries cũ cần review: chúng có thể vẫn dùng bởi configuration/build khác hoặc rollback support window.
- Không tự chạy “auto-regenerate all” rồi xóa mọi thủ công added checksums/PGP policy, vì bạn có thể phá trusted anchors đã được review.
- Khi rollout/rollback đã qua support window, cleanup unused entries trong PR riêng theo dependency graph toàn tổ chức.

### 5.4. SHA-256 và PGP signatures

Nếu team yêu cầu PGP, có thể bootstrap:

```bash
./gradlew help \
  --write-verification-metadata sha256,pgp \
  --console=plain
```

Gradle có thể tự thêm trusted/ignored PGP keys khi bootstrap; **phải review**. PGP signature đúng về thuật toán chưa đủ chứng minh identity: key có thể không do publisher mong muốn sở hữu. Nếu cần integrity cả cho artifacts được ký bằng hash yếu hoặc unsigned, dùng strong SHA-256/SHA-512 và review trust.

Keyring public được export (nếu policy áp dụng) bằng:

```bash
./gradlew --export-keys
```

Đây là công cụ management; public keyring chứa keys, **không tự xác thực key fingerprint**. Nếu commit `.gpg` hoặc `.keys`, chọn format được team chuẩn hóa và review key changes cùng XML.

### 5.5. Preview XML bằng dry-run

Gradle hỗ trợ:

```bash
./gradlew help \
  --write-verification-metadata sha256 \
  --dry-run --console=plain
```

Theo tài liệu, command này có thể tạo `gradle/verification-metadata.dryrun.xml` để **preview** thay vì ghi trực tiếp vào `verification-metadata.xml`. Chữ “dry-run” ở đây không có nghĩa “không chạy initialization/configuration hoặc không chạm filesystem nào”; nó tạo file preview.

Giới hạn: `--dry-run` không thực thi task actions, nên dependency resolution phát sinh **chỉ ở execution time** có thể bị bỏ sót. Sau review và bootstrap thật vẫn phải chạy full tasks, xem verification failures còn phát sinh không.

### 5.6. Những thay đổi XML phải coi là security-sensitive

| XML diff | Cần xem gì? |
| --- | --- |
| Thêm SHA cho artifact version mới | Publisher, artifact coordinates, JAR/POM source và expected digest. |
| Đổi SHA **cùng coordinate/version** | Có republish/corruption/tampering không? Đây thường là **security incident cho immutable release**, không phải update thường. |
| Thêm `trusted-key` hoặc thay fingerprint | Identity, signer/provenance, scope group/module và key rotation evidence. |
| Thêm `ignored-key` | Vì sao không verify signature? Có fallback checksum đủ mạnh không? |
| Thêm `trusted-artifacts` broad rule | Có vô tình bỏ qua verification cả nhóm artifact không? Cần chính sách hạn chế. |
| Đổi `verify-metadata` từ true sang false | Bỏ bảo vệ POM/module metadata, cần security approval cao. |
| Đổi `verify-signatures` từ true sang false | Hạ mức trust policy, không nên đi kèm dependency update thông thường. |
| Xóa old artifact entry | Có config, included build, rollback window hoặc consumer còn cần không? |
| Thêm repository/plugin artifact | Nguồn có được allowlist? Plugin code chạy trong Gradle, tác động lớn hơn app JAR. |

**Không xử lý checksum mismatch bằng cách thay expected SHA bằng actual SHA ngay.** Việc đó có thể hợp thức hóa poisoned artifact và vô hiệu mục đích verification.

## 6. Scope trong multi-project và composite builds

### 6.1. Lockfiles thường theo project

Ví dụ:

```text
workspace/
├── settings.gradle
├── gradle.lockfile
├── app/gradle.lockfile
├── api/gradle.lockfile
└── build-logic/
    ├── settings.gradle
    ├── build.gradle
    └── gradle.lockfile
```

- Root lockfile không đại diện cho `app` hay `api` khi mỗi project có configurations riêng.
- Included build `build-logic` có build boundary và có thể có lockfiles riêng.
- Legacy buildscript classpath locking có thể tạo `buildscript-gradle.lockfile`.
- Một upgrade JUnit, Kotlin/AGP hoặc plugin build có thể thay more than one lockfile; PR phải liệt kê affected scopes.
- Nếu CI release chỉ chạy `:app:build`, cần có thêm verification coverage/test cho other modules nếu rollback dự kiến bao phủ cả monorepo.

### 6.2. Verification metadata của current build

Theo Gradle docs, dependency verification configuration ở root/current build áp cho subprojects và `buildSrc`. Khi sử dụng `includeBuild`, **verification metadata của current/outer build** được dùng trong composite invocation, included build’s own XML bị bỏ qua trong context đó. Nếu chạy included build standalone, build đó có current-root metadata của chính nó.

Vì vậy khi PR thêm một included build:

- Đọc new build scripts/plugin repositories trước khi execute.
- Xem external artifacts mà included build resolve có đủ trusted metadata ở **outer build** chưa.
- Kiểm các lockfiles của build đó theo logic build riêng.
- Đừng chỉ commit `build-logic/gradle/verification-metadata.xml` rồi nghĩ outer build đã được bảo vệ tương ứng.

## 7. Kế hoạch thay đổi chuẩn: baseline → upgrade → review → rollout

### 7.1. Pha 0 — chốt baseline an toàn

- Xác định baseline Git SHA/approved release tag và **actual artifact digest** đang chạy production.
- Xác nhận tests, CI, Gradle Wrapper/JDK/plugin compatibility ở baseline.
- Lưu lockfiles và verification XML đúng commit; kiểm diff đã sạch.
- Kiểm vulnerability status: **known-good không được đồng nghĩa known-vulnerable**.
- Quy định rõ owner quyết định rollback, thời gian hỗ trợ old versions, artifact retention và monitor signals.
- Xác định rollback có cần cập nhật database/event schemas/feature flags/release configuration không.
- Không tạo baseline bằng cách tự tắt verification để đạt green build.

### 7.2. Pha 1 — thay đổi ở branch/PR giới hạn

Thứ tự khuyên dùng:

1. Sửa version declaration / approved catalog / platform constraint.
2. Resolve và **selectively** update affected lock states.
3. Preview và bootstrap checksums/signatures cho artifacts mới.
4. Review diffs, provenance, key fingerprint, exceptions.
5. Chạy relevant tasks để tìm dependency resolution chỉ có tại execution.
6. Chạy strict verification và locking; build/test + targeted CI tasks.
7. Commit đầy đủ change set, không gộp không liên quan.
8. Đưa PR cho reviewers của source/build/security khi scope đụng supply chain.

### 7.3. Pha 2 — rollout có cổng chặn

- Chạy CI trên clean checkout và locked versions, dùng trusted repository/Gradle caches.
- Validate Wrapper ZIP/JAR/signed release nếu Wrapper đổi.
- Enforce dependency verification strict, không bật `off`/`lenient` để pass.
- Kiểm declared version vs resolved version bằng `dependencyInsight` và expected lockfiles.
- Chạy `test`, `check`, integration/functional tests, plugin tests nếu có.
- Kiểm security advisories, license/compliance, provenance và artifact signatures.
- Publish immutable build artifact vào registry với digest/attestation.
- Rollout canary/staging rồi monitor error rate, startup, latency, security flags và deployment health.

### 7.4. Pha 3 — tiêu chí rollback rõ ràng

Phân loại trigger:

| Trigger | Hành động đầu tiên | Có nên rollback ngay? |
| --- | --- | --- |
| Verification checksum mismatch với cùng immutable coordinate | **Dừng** release, cô lập artifact, kiểm nguồn/checksum, báo security. | Chỉ về baseline **đã xác nhận an toàn**; không bypass. |
| New dependency version làm tests/regression fail | Dừng rollout, lấy logs và diff. | Có thể revert toàn change set về tested version cũ. |
| Plugin/Gradle/JDK incompatibility | So Wrapper/toolchain/plugin versions. | Có thể revert Wrapper/plugins/build logic cùng nhóm; vẫn kiểm release compatibility. |
| Lock mismatch vì cập nhật chưa đủ | Kiểm scope/configurations, constraints/BOM. | Có thể sửa PR trước merge; không cần rollback runtime nếu chưa deploy. |
| New release có CVE/compromise | Suspend deploy, security triage. | Không quay về baseline nếu baseline cũng vulnerable/compromised. |
| Production data schema đã thay đổi không backward-compatible | Freeze rollout, đánh giá migration. | **Chưa được** revert binary mù quáng; cần kế hoạch dữ liệu. |
| Gradle verification metadata auto-edited bất thường trong CI | Dừng pipeline và review source/job. | Không coi auto-edited XML là trusted; khôi phục baseline qua review. |
| Remote repository outage | Kiểm offline artifact availability / mirror provenance. | Không xóa verification/locks để vượt outage. |

Một trigger không có nghĩa chạy `git reset --hard` trên shared branch. Cần quyết định impact và trạng thái dữ liệu.

## 8. Lab runnable: Java 17+ với Gradle Groovy DSL

### 8.1. Mục tiêu thực nghiệm

Tạo ứng dụng nhỏ dùng **Commons Lang 3.16.0** làm baseline, JUnit Jupiter BOM **5.11.4** để test. Ta sẽ:

- Tạo `gradle.lockfile` và `verification-metadata.xml` từ trusted repositories.
- Ghi một baseline Git commit.
- Nâng Commons Lang lên **3.17.0**, cập nhật lockfile/verification metadata, kiểm thử, commit.
- Trên **branch mô phỏng mới**, dùng `git revert` để tạo rollback commit của **toàn bộ update**, không xóa history.
- So versions, metadata, JUnit và stdout trước/sau.

Hai bản Commons Lang trên được dùng **chỉ làm thí nghiệm kỹ thuật**, không khẳng định chúng là latest hoặc an toàn cho production vào mọi thời điểm. Với dự án thật, phải chạy security/vulnerability policy trước khi chọn bất kỳ version nào.

### 8.2. Công cụ cần có

- JDK 17+ và Gradle Wrapper tương thích với JDK đã cài; ví dụ Gradle 9.9.0 đã được pin/verified.
- Git (đã cấu hình name/email để commit), Internet/trusted Maven Central lần bootstrap đầu.
- Workspace **demo riêng**, không chạy `git revert` trên nhánh production của dự án thật.
- Reviewer/owner cho checksums hoặc release publisher provenance khi dùng ngoài demo.

Cấu trúc:

```text
gradle-rollback-lab/
├── .gitignore
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   ├── wrapper/
│   │   ├── gradle-wrapper.jar
│   │   └── gradle-wrapper.properties
│   └── verification-metadata.xml         (sinh ở bước bootstrap)
├── gradle.lockfile                         (sinh ở bước bootstrap)
└── src/
    ├── main/java/example/ReleaseApp.java
    └── test/java/example/ReleaseAppTest.java
```

**Wrapper phải được tạo từ trusted Gradle installation** bằng `gradle wrapper`/`gradle init` trước; chỉ tạo `build.gradle` không tự có Wrapper files. Nếu đang kiểm repo lạ, verify `gradle-wrapper.jar`/scripts và distribution SHA trước khi chạy.

### 8.3. .gitignore

```gitignore
.gradle/
build/
**/build/
```

Đừng ignore `gradle.lockfile`, `gradle/verification-metadata.xml` hay Wrapper JAR. Đây chính là những file cần commit/truy vết history.

### 8.4. settings.gradle

```groovy
rootProject.name = 'gradle-rollback-lab'
```

### 8.5. build.gradle baseline hoàn chỉnh

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
    implementation 'org.apache.commons:commons-lang3:3.16.0'

    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'example.ReleaseApp'
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

dependencyLocking {
    lockAllConfigurations()
}
```

Giải thích:

1. `application` là Gradle core plugin: cung cấp `run`, `compileJava`, `test`, `build`.
2. `commons-lang3:3.16.0` là một **external Java library**; version của nó cần lock và verification.
3. JUnit BOM `5.11.4` đặt constraints cho JUnit modules nhưng **không thay lockfile**.
4. `junit-platform-launcher` giúp Gradle chạy tests qua JUnit Platform.
5. `java.toolchain=17` chọn JDK 17 compiler/launcher nếu được tìm thấy hoặc provision hợp lệ.
6. `options.release=17` target Java 17 APIs/bytecode, không tự tải JDK.
7. `lockAllConfigurations()` bật locking cho resolvable configurations của **single project**.
8. Baseline không giả vờ có SHA: Gradle tạo XML từ artifact thực và team review sau đó.

### 8.6. src/main/java/example/ReleaseApp.java

```java
package example;

import org.apache.commons.lang3.StringUtils;

public final class ReleaseApp {
    private ReleaseApp() {
    }

    public static String message(String recipient) {
        String normalized = StringUtils.trimToEmpty(recipient);
        if (normalized.isEmpty()) {
            normalized = "visitor";
        }
        return "Release: " + StringUtils.capitalize(normalized);
    }

    public static void main(String[] args) {
        String recipient = args.length == 0 ? "gradle" : args[0];
        System.out.println(message(recipient));
    }
}
```

`StringUtils.trimToEmpty` chuyển null/whitespace thành empty và `StringUtils.capitalize` viết hoa chữ cái đầu.

### 8.7. src/test/java/example/ReleaseAppTest.java

```java
package example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReleaseAppTest {
    @Test
    void defaultRecipient() {
        assertEquals("Release: Gradle", ReleaseApp.message("gradle"));
    }

    @Test
    void customRecipient() {
        assertEquals("Release: Team", ReleaseApp.message("team"));
    }

    @Test
    void emptyRecipient() {
        assertEquals("Release: Visitor", ReleaseApp.message("  "));
    }
}
```

Đây là **3 JUnit Jupiter tests**. Không có code phụ thuộc clock, random hoặc network. Java app vẫn cần Maven dependency khi Gradle compile; test results không khẳng định artifact publisher đáng tin, đó là nhiệm vụ verification review.

### 8.8. Bootstrap known-good lockfiles

Sau khi đã xác minh Wrapper, chạy Linux/macOS:

```bash
./gradlew dependencies --write-locks --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat dependencies --write-locks --console=plain
```

Gradle tạo `gradle.lockfile` cho những configurations được resolve và có locking. Đọc file thật, đừng copy một bản lockfile ngắn từ tài liệu; JUnit test/runtime có nhiều transitive modules.

**Quan trọng:** nếu build thực có configurations chỉ được resolve trong task execution, `dependencies` không bảo đảm bao phủ tất cả trong mọi project. Lab single-project này tương đối đơn giản; production phải liệt kê thêm tasks/configurations.

### 8.9. Bootstrap verification metadata và review

```bash
./gradlew help --write-verification-metadata sha256 \
  --console=plain
```

Trên Windows:

```powershell
.\gradlew.bat help --write-verification-metadata sha256 --console=plain
```

Sau đó:

```bash
git status --short
git diff -- build.gradle
```

Nếu XML/lockfile **mới và untracked**, `git diff` không hiển thị nội dung của chúng; mở trực tiếp, `git add -N` hoặc staging có chủ đích sau khi review. Cross-check group/name/version, SHA và repository/publisher; Gradle chỉ tạo baseline từ bytes hiện tại, **không tự xác nhận publisher an toàn**.

### 8.10. Chạy baseline build với strict verification

```bash
./gradlew clean check \
  --dependency-verification strict \
  --console=plain
./gradlew -q run --args="team" \
  --dependency-verification strict
```

Windows:

```powershell
.\gradlew.bat clean check --dependency-verification strict --console=plain
.\gradlew.bat -q run --args="team" --dependency-verification strict
```

**Stdout riêng của Java main**:

```text
Release: Team
```

Chạy không argument:

```bash
./gradlew -q run --dependency-verification strict
```

**Stdout riêng của Java main**:

```text
Release: Gradle
```

Gradle có thể còn hiển thị diagnostics/task messages. 3 tests dự kiến pass nếu dependencies/environment hợp lệ; chỉ ghi trạng thái CI PASS khi **đã chạy thực tế**.

### 8.11. Tạo Git baseline commit

Khi các files đã review, trong **repo demo chuyên dụng**:

```bash
git add .gitignore settings.gradle build.gradle \
  src/main/java/example/ReleaseApp.java \
  src/test/java/example/ReleaseAppTest.java \
  gradlew gradlew.bat \
  gradle/wrapper/gradle-wrapper.jar \
  gradle/wrapper/gradle-wrapper.properties \
  gradle.lockfile gradle/verification-metadata.xml

git diff --cached --stat
git diff --cached -- build.gradle gradle.lockfile \
  gradle/verification-metadata.xml
git commit -m "baseline: trusted Java build with dependency locks"
git rev-parse HEAD
```

Nếu dùng PowerShell 5.1, chạy `git add` trong **một dòng** hoặc dùng backtick continuation chuẩn PowerShell thay vì Bash backslash. Dòng trên là **Bash**.

Nếu commit bị từ chối vì Git identity chưa cấu hình hoặc do hook, phải xử lý đúng lỗi; không bỏ qua security review. **Không dùng `git add -A` bừa bãi ở repo có thay đổi không liên quan.**

### 8.12. Nâng Commons Lang có kiểm soát

Trên **branch upgrade mới**, đổi một dòng trong `build.gradle`:

- Baseline: `implementation 'org.apache.commons:commons-lang3:3.16.0'`.
- Upgrade: `implementation 'org.apache.commons:commons-lang3:3.17.0'`.

Sau khi sửa:

```bash
./gradlew dependencies \
  --update-locks org.apache.commons:commons-lang3 \
  --console=plain

./gradlew help \
  --write-verification-metadata sha256 \
  --console=plain
```

Kiểm tra khác biệt:

```bash
git diff -- build.gradle gradle.lockfile \
  gradle/verification-metadata.xml
./gradlew dependencyInsight \
  --dependency commons-lang3 \
  --configuration runtimeClasspath \
  --console=plain
./gradlew clean check \
  --dependency-verification strict --console=plain
```

**Điểm học tập:** lockfile version nên phản ánh approved graph mới, XML nên có verification entries tương ứng. XML **có thể vẫn giữ 3.16.0** vì bootstrap incremental. Đừng xóa entry cũ nếu rollback window yêu cầu nó hoặc một other configuration vẫn dùng, nhưng cũng đừng để file tăng mãi không review.

Nếu upgrade thêm JUnit/platform plugin khác, cần kiểm tra toàn bộ affected configurations và files. Sau khi review, commit upgrade thành **một change set** trong demo; không commit checksum/generated metadata trước khi được duyệt.

### 8.13. Mô phỏng rollback bằng git revert

Giả sử bạn đã commit upgrade **thành một commit mới** và đang ở chính commit upgrade cuối cùng. Tạo một branch **dành riêng demo**, không sửa main:

Linux/macOS:

```bash
# Run only inside the isolated lab repository,
# when HEAD is exactly the upgrade commit and worktree is clean.
baseline_commit=$(git rev-parse HEAD~1)
git switch -c demo-rollback
git revert --no-edit HEAD

# A simple one-commit upgrade should now restore baseline file content.
git diff --exit-code "$baseline_commit" HEAD -- \
  build.gradle gradle.lockfile gradle/verification-metadata.xml
```

Windows PowerShell:

```powershell
# Run only inside the isolated lab repository,
# when HEAD is the upgrade commit and worktree is clean.
$baselineCommit = (git rev-parse HEAD~1).Trim()
git switch -c demo-rollback
git revert --no-edit HEAD
git diff --exit-code $baselineCommit HEAD -- build.gradle gradle.lockfile gradle/verification-metadata.xml
```

Giải thích:

- `git revert` **tạo commit ngược** thay vì sửa lịch sử/force push trên shared branch.
- `git diff --exit-code` không in diff và exit code **0** khi những files được chỉ định khớp baseline; nonzero khi còn khác.
- Đây là trường hợp **một commit upgrade**. Nếu upgrade gồm nhiều commits hoặc changes xen kẽ, phải xác định đúng commit set/dependencies, revert theo thứ tự phù hợp, giải quyết conflicts và review.
- Nếu Wrapper/plugins/catalog/CI scripts cũng đổi trong upgrade, **phải đối chiếu/revert chúng** chứ không giới hạn vào ba file của lab.
- Nếu PR có source changes không liên quan, không tự revert toàn bộ khi những changes khác cần giữ.
- Git revert không rollback published artifact, production DB hoặc external releases.

Sau revert chạy lại:

```bash
./gradlew dependencyInsight \
  --dependency commons-lang3 \
  --configuration runtimeClasspath \
  --console=plain
./gradlew clean check --dependency-verification strict --console=plain
./gradlew -q run --args="team" --dependency-verification strict
```

Stdout riêng Java main vẫn là:

```text
Release: Team
```

**Chú ý:** stdout giống nhau không chứng minh dependency version đã rollback. Phải kiểm `dependencyInsight`, lockfile, verification XML, Git diff/commit và CI. Đó chính là lý do quản lý thay đổi không chỉ dựa vào ứng dụng có chạy hay không.

## 9. Runbook rollback dành cho production

### 9.1. Decision tree

```text
Observed failure / release incident
           |
           v
Security integrity incident? (checksum mismatch / suspicious publisher)
        /          \
       Yes          No
       |             |
Stop release,        Is issue caused by the new dependency/plugin/runtime?
preserve evidence     /                  \
quarantine input    Yes                  No
review provenance    |                    |
and safe versions   Check rollback       Investigate unrelated
       |            compatibility       root cause, do not revert blindly
       |               |
       +-------+-------+
               |
               v
Is old baseline actually safe and deploy-compatible?
           /                  \
         Yes                   No
          |                     |
Revert coherent Git          Select a forward fix:
change set and/or            patched artifact/version,
redeploy trusted prior       isolated hotfix, feature flag,
artifact with approvals      migration/recovery plan
          |                     |
          +-----------+---------+
                      |
                      v
Strict verification + locking + tests + deployment checks
                      |
                      v
Monitor, document, close incident only after validation
```

**Không có branch “tắt verification cho nhanh”.** Trong sự cố nghi compromise, xác định trusted root of trust và dùng artifacts đã được xác nhận; không chỉ chọn phiên bản số nhỏ hơn.

### 9.2. Thủ tục trước rollback

1. **Freeze change**: dừng merge/deploy jobs liên quan nếu có rủi ro lan lỗi.
2. Xác định **current deployed release digest**, Git commit, Gradle Wrapper/JDK, plugin versions, lockfiles/XML được dùng khi build artifact đó.
3. Liệt kê **upgrade changeset**, gồm direct/transitive versions, hash/key changes, new repositories, scripts, toolchains, CI configuration.
4. Đánh giá **security**: bản cũ có CVE? Có bị thu hồi/yanked, compromised hoặc thiếu signature không?
5. Đánh giá **runtime/deployment compatibility**: DB schema, API contracts, messages, feature flags, external configuration.
6. Xác định **rollback owner**, approvals, canary/monitoring threshold, artifact location và contingency.
7. Giữ log, CI evidence và artifact hashes trong kho có quyền; không paste secrets vào public ticket.

### 9.3. Chọn loại rollback

| Loại | Dùng khi | Cần làm |
| --- | --- | --- |
| **Pre-merge PR correction** | Upgrade chưa merge/deploy. | Revert/sửa changes trong branch PR; review dependency graph và trust XML. |
| **Git revert of upgrade commit** | Upgrade đã merge, có known-good safe baseline. | Tạo revert PR/commit trên branch mới; revert đồng bộ declarations, locks, XML, Wrapper/plugins/CI nếu cùng change set. |
| **Deploy previous artifact** | Production regression, có artifact đã build và được tin cậy. | Redeploy **đúng digest** từ registry/release storage, không mặc định rebuild mới từ commit cũ. |
| **Forward fix** | Version cũ có CVE/compromise hoặc data schema không rollback được. | Chọn patched version/hotfix/feature flag, update locks/verification metadata qua review. |
| **Environment/JDK rollback** | Runner/daemon/toolchain mới gây incompatibility. | Khôi phục runner image/JDK/toolchain cùng source; vẫn validate Gradle/plugin compatibility. |
| **Repository/mirror restore** | Maven proxy phục vụ artifact bytes/metadata bất thường. | Quarantine compromised source; switch approved mirror hoặc wait remediation, không cập nhật expected hash mù quáng. |

### 9.4. Khi revert một nhóm file

**Nếu đổi dependency declaration**, revert cả:

- `build.gradle(.kts)` và/hoặc `gradle/libs.versions.toml` và dependency constraints/BOM.
- `gradle.lockfile` trong các affected projects.
- `gradle/verification-metadata.xml` và PGP keyrings/policy đã thay vì upgrade.
- Plugin versions/resolution settings nếu plugin cũng nâng.
- Gradle Wrapper files và `distributionSha256Sum` nếu Gradle upgrade nằm trong rollback scope.
- Build logic, CI toolchain settings và test configuration bị thay cùng change set.

Nếu reversion của **một file riêng** là có lý do, PR phải giải thích bằng chứng rằng các files còn lại vẫn tạo resolved graph/trust policy nhất quán. **Không bắt buộc xóa mọi old/new verification entry khi rollback** nếu chúng còn dùng hợp lệ bởi scopes khác; tuy nhiên việc “giữ lại trust rộng” cần security review và cleanup policy.

### 9.5. Không dùng reset --hard/force push trên protected branch

**Tránh** `git reset --hard` và `git push --force` để “khôi phục main”: thao tác đó có thể xóa công việc chưa commit, viết lại lịch sử đã chia sẻ và làm audit khó khăn.

Ưu tiên một **revert commit** với review, CI và phê duyệt như mọi PR khác. Nếu repo có merge commit, `git revert -m` có semantics đặc biệt (chọn mainline parent); không áp template một cách mù quáng khi chưa hiểu history và commit graph.

## 10. Cổng kiểm tra tự động trong CI

### 10.1. Tách generator job và verifier job

Một release pipeline nên phân biệt:

- **Update/generator job** (chỉ branch có chủ đích và reviewer): có thể dùng `--write-locks`, `--update-locks`, `--write-verification-metadata`, tạo diff để được xem xét.
- **Enforcer/verification CI job** (chạy PR/release): dùng checked-in lockfiles và XML **chỉ để kiểm tra**, không auto-update checksums/versions rồi tự coi thành công.

Tại sao? Nếu CI được phép ghi SHA mới từ artifact tải về, một poisoned artifact có thể được biến thành approved hash trong cùng job. Đây là **trust-on-first-use problem**, không phải tiện ích automation vô hại.

### 10.2. Các lệnh CI mẫu (sau Wrapper validation)

Linux/macOS:

```bash
./gradlew --version
./gradlew help --warning-mode=all --console=plain
./gradlew clean check \
  --dependency-verification strict --console=plain

# Detect unintended modifications to previously committed control files.
git diff --exit-code -- \
  gradle.lockfile gradle/verification-metadata.xml \
  gradle/wrapper/gradle-wrapper.properties
```

Phần `git diff --exit-code` phù hợp cho **clean checkout đã chứa commit được test**; nó chỉ bắt **tracked working-tree modifications sau task**, không phải so PR diff với base branch. Với multi-project phải bổ sung relevant lockfiles; với untracked generated files cần `git status`/policy riêng.

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat help --warning-mode=all --console=plain
.\gradlew.bat clean check --dependency-verification strict --console=plain
git diff --exit-code -- gradle.lockfile gradle/verification-metadata.xml gradle/wrapper/gradle-wrapper.properties
```

**Các lệnh này không tự kiểm thử integration/publishing/Android release tasks**; thêm tasks cần thiết theo project. Với dependency resolution chỉ phát sinh khi chạy task execution, chỉ `help` hoặc `dependencies` có thể bỏ sót artifacts cần verify.

### 10.3. Quy tắc policy cho PR

| Rule | Ý nghĩa |
| --- | --- |
| Bắt buộc diff review lockfiles/XML | Mọi transitive change và trusted hash/key đều có reviewer. |
| Chỉ allow approved repositories | Không silently chuyển sang domain/mirror chưa được duyệt. |
| Không nới strict verification | Không chấp nhận `off`, lenient hoặc trust-all wildcard trong upgrade PR thông thường. |
| Bảo vệ PGP keys/public keyrings | Key rotation cần owner/fingerprint/provenance. |
| Commit Wrapper files đồng bộ | Upgrade Gradle cần review scripts, JAR, distribution URL/SHA. |
| Các version có evidence | Lock graph phải khớp declared catalog/BOM và release notes. |
| CI sạch và test coverage | Không skip `check` hoặc target release tests để merge. |
| Retain rollback artifact | Giữ known-good digest trong khoảng support window. |
| Release approval | Người quyết định rollback khác người chỉ tạo generated XML khi policy yêu cầu. |
| Sau rollback có postmortem | Document root cause, timeline, new preventative checks và cleanup. |

### 10.4. Lock mode STRICT và release baseline

Trong production builds đã khởi tạo đầy đủ lock state, `LockMode.STRICT` giúp phát hiện **configuration mới thiếu lockfile**. Nhưng khi bạn thêm một task/configuration mới, STRICT có thể fail dù dependency graph cũ không đổi: đó là lý do cần bootstrap bổ sung với approval, **không phải lý do tắt locking trên CI**.

## 11. Diagnostics: lỗi đến từ lớp nào?

### 11.1. Lock mismatch

**Triệu chứng:** Gradle resolution fail do locked version khác declared version; missing locked module hoặc new module chưa được locked.

**Điều tra:**

```bash
./gradlew dependencyInsight \
  --dependency commons-lang3 \
  --configuration runtimeClasspath \
  --console=plain
```

Kiểm declared version, version catalog, BOM/platform, transitive constraints, dependency substitutions, lockfile scope và expected selected version. Nếu nâng có chủ đích, update **đúng modules** rồi review; nếu phát hiện phiên bản lạ, không tự ghi đè lockfiles.

### 11.2. Missing verification entry

**Triệu chứng:** XML chưa chứa hash/chữ ký cho dependency/plugin mới.

**Điều tra:** xác định group:name:version, artifact file `.jar`/`.pom`/`.module`, repository origin, version/lock graph. Bootstrap trong nhánh change có kiểm soát, compare hashes/signatures từ publisher, review diff rồi commit.

**Không** tự đổi mode sang `off` trong release job. Nếu artifact chỉ được resolve khi chạy test task, `help` một mình không đủ để xác nhận verification coverage.

### 11.3. Incorrect checksum dù version không đổi

**Triệu chứng:** expected digest khác actual bytes của cùng coordinate.

Xét:

1. Artifact immutable bị republish? Repository đã bị compromise?
2. Proxy mirror trả bytes khác release origin?
3. Có cached artifact hỏng hoặc metadata POM variant khác?
4. Expected hash trong XML có bị thay gần đây không?
5. Keyring/signature verification có disagreement?
6. Có security advisory/incident liên quan publisher/repo?

**Ưu tiên dừng và điều tra.** Nếu nghi compromise, coi là supply-chain incident, không copy actual hash vào XML. **Rollback** chỉ đến baseline có artifact bytes đã được xác nhận an toàn, không dựa trên version number.

### 11.4. Signature/key rotation

Publisher đổi signing key có thể khiến XML trusted key fingerprint mismatch. Kiểm fingerprint qua publisher trusted channel, scope key theo group/module nếu phù hợp, review imported public keys/keyring files và fallback SHA-256. Không thêm `ignored-key` vô hạn định hoặc `trusted-artifacts` wildcard rộng.

### 11.5. Gradle Wrapper/plugin/JDK change

Một PR cùng nâng Gradle Wrapper và dependencies có thể fail vì:

- Gradle/JDK compatibility matrix không khớp.
- Plugin dùng removed Gradle APIs, internal APIs hoặc embedded Kotlin/Groovy versions khác.
- Wrapper scripts/JAR chưa được cập nhật đồng bộ hoặc ZIP checksum mismatch.
- Buildscript classpath/includeBuild dependency graphs thay đổi.
- CI gradle.properties/Daemon JVM criteria/JDK toolchain khác baseline.

Đừng sửa verification XML để “chữa” một lỗi `NoSuchMethodError` từ plugin. Cần phân lớp root cause trước khi rollback.

## 12. Các tình huống rollback điển hình

### 12.1. Tình huống A: nâng library làm test regression

**Hiện trạng:** PR đổi `3.16.0 → 3.17.0`, lockfile và XML đúng nhưng một integration test fail.

**Xử lý:** nếu 3.16.0 vẫn được security approval, revert coherent change set gồm version declaration, lockfile, XML changes liên quan. Re-run strict verification + tests trên clean runner. Nếu production đã deploy, redeploy known-good release artifact theo digest và monitor. Không nhất thiết xóa metadata 3.17.0 khỏi mọi build nếu other modules vẫn dùng nó, nhưng mọi retained trust entry phải được kiểm soát.

### 12.2. Tình huống B: checksum của immutable artifact đột ngột đổi

**Hiện trạng:** `commons-lang3:3.16.0` vẫn locked, nhưng actual SHA mismatch.

**Xử lý:** freeze releases, cô lập artifact, check publisher/checksum/PGP independent source, repository logs/proxy, cache provenance. **Không** đổi XML hash hay tắt verification. Nếu local cached artifact verified đã được lưu, nó có thể là evidence/temporary trusted input tùy policy, nhưng không coi mọi cache là nguồn trust tự động. Chỉ rollback/forward-fix khi có verified safe artifact/version.

### 12.3. Tình huống C: JUnit BOM đổi gây transitive churn

**Hiện trạng:** chỉ sửa BOM requested version nhưng `gradle.lockfile` đổi nhiều JUnit modules/platform artifacts.

**Xử lý:** diff đúng là có thể xảy ra; cần review versions theo resolved configurations và vendor release notes. Nếu chưa approved, revert BOM declaration **cùng** locks/verification metadata liên quan, không chỉ xóa 1 dòng trong lockfile.

### 12.4. Tình huống D: plugin/Wrapper major upgrade không tương thích

**Hiện trạng:** bump Gradle Wrapper và plugin version, build fail trong project configuration.

**Xử lý:** kiểm logs với `--warning-mode=all` trên baseline/upgrade, plugin compatibility matrix và Daemon JVM. Nếu rollback hợp lệ, revert Wrapper JAR/scripts/properties/distribution SHA, plugin requests/settings/catalog, build logic, lock/verification metadata nếu các artifact versions thay đổi; rồi validate Wrapper trước khi chạy. Không pin 1 Gradle ZIP SHA cho một release URL khác.

### 12.5. Tình huống E: private repository outage

**Hiện trạng:** builds fail vì không truy cập Maven mirror, nhưng locks/XML không đổi.

**Xử lý:** đây không nhất thiết là regression của dependency upgrade. Có thể dùng `--offline` khi tất cả artifacts/metadata đã cache và policy cho phép, hoặc approved mirror có provenance tương đương. **Không thay expected checksums thành bytes của một mirror bất kỳ** và không tắt strict verification.

### 12.6. Tình huống F: bản cũ có CVE nghiêm trọng

**Hiện trạng:** new version gây functional regression nhưng baseline cũ đã bị advisory nghiêm trọng.

**Xử lý:** rollback về vulnerable release **không phải đáp án mặc định**. Đánh giá exploitability/mitigations, phát hành patched version mới, temporary feature flag/rollback of feature (không dependency), hoặc approved hotfix. Quyết định phải do security + release owner với risk assessment và audit trail.

### 12.7. Tình huống G: XML bị chỉnh manual quá rộng

**Hiện trạng:** PR thêm `trusted-artifacts` regex bao phủ cả organization hoặc tắt `verify-metadata`.

**Xử lý:** fail review/security gate, giới hạn lại scope exception hoặc loại bỏ; nếu đã merge, tạo security fix/revert commit cho trust policy nhưng **không xóa các valid approved hashes/keys** cần cho production. Chạy strict verification và scan diff.

### 12.8. Tình huống H: release artifact deploy đã khác source rollback

**Hiện trạng:** Git đã revert upgrade, CI build cũ PASS, nhưng production container vẫn là image mới.

**Xử lý:** release/deploy pipeline phải chọn đúng previous artifact digest hoặc build/release đã approved, xác nhận runtime config/DB/schema; quan sát health. Git revert và `gradle.lockfile` khớp không tự thay Docker image/JAR đang chạy.

## 13. Quản lý vòng đời verification metadata lâu dài

### 13.1. Khi nào giữ old entries?

Có lý do giữ hash/signature của versions cũ nếu:

- Một subproject/test/configuration còn dùng version đó.
- Có rollback support window và artifact cũ vẫn được phép dùng.
- Một included build được chạy độc lập/bên trong composite với graph khác.
- Một historical release pipeline cần reproducibility/audit có policy giữ riêng.

Nhưng không nên biến XML thành “allowlist mọi artifact từng thấy” vô thời hạn. Nếu một version bị compromise, việc giữ approved hash cũ có thể vẫn đáng xem xét vì hash định danh bytes cụ thể, nhưng security policy có thể yêu cầu **không được tiếp tục dùng artifact đó** dù checksum khớp.

### 13.2. Cleanup sau rollback window

1. Inventory actual resolved graphs của **các supported builds/variants**, không chỉ task help.
2. Xác định entries stale đã hết rollback/maintenance support.
3. Xác định signing key vẫn dùng cho versions hiện tại; tránh xóa key phục vụ artifacts còn trusted.
4. Review removals trong PR riêng, không giấu trong feature PR.
5. Chạy strict verification trên CI matrix; phát hiện missing artifact metadata/keys.
6. Lưu tag/commit của historical release và artifact digests theo retention policy.
7. Không cố “clean XML” bằng xóa file rồi bootstrap mù quáng từ repository hiện tại.

### 13.3. Verification file dry-run có giới hạn

`verification-metadata.dryrun.xml` giúp so metadata dự kiến nhưng không bao phủ mọi execution-time resolution. Đừng dùng nó làm **source duy nhất** để xóa toàn bộ old entries: một plugin/codegen task chạy theo CI branch khác có thể còn cần artifact không có trong preview.

### 13.4. Ghi chép nguyên nhân thay đổi

Mỗi PR ảnh hưởng trust policy nên có:

- Change reason (security patch, bug fix, plugin migration).
- Allowed repositories/publisher provenance.
- Direct/transitive module diff.
- New SHA/PGP entries, changed signing keys và giải thích.
- Affected configurations/projects/included builds.
- Rollback deadline/previous artifact digest.
- CI tests, reviewer/security approval.
- Cleanup plan cho old entries và temporary mitigations.

**Annotation `origin="Verified"` không phải chữ ký của người review.** Bằng chứng review cần nằm trong protected Git history, PR notes/sign-off hoặc provenance system.

## 14. Checklist trước khi merge, triển khai và rollback

### 14.1. Trước khi merge PR nâng cấp

- [ ] Source commit và baseline artifact digest đã ghi nhận.
- [ ] Gradle Wrapper/JDK/plugins tương thích; Wrapper JAR + ZIP checksum đã verify nếu có đổi.
- [ ] Direct dependency declaration/catalog/BOM đúng phiên bản approved.
- [ ] Lockfiles của **mọi affected projects/configurations** được cập nhật và review; không có transitive surprise.
- [ ] `verification-metadata.xml` có hashes/signatures cho required artifacts/metadata.
- [ ] Tất cả `origin="Generated by Gradle"` mới được review publisher/repository trước khi đánh dấu verified.
- [ ] Signing key additions/ignored keys/trusted-artifacts exceptions có rationale và approval.
- [ ] Không vô tình tắt `verify-metadata`, verification strict hoặc locking.
- [ ] Build/test/integration/functional checks đã chạy trên clean checkout và target JDK/CI.
- [ ] Rollback path và deployment compatibility đã được xác nhận.
- [ ] Security advisories/license/SSBOM checks theo policy đã hoàn tất.
- [ ] Release artifact và previous approved artifact được giữ theo retention window.

### 14.2. Trước khi thực hiện rollback

- [ ] Trigger, severity, owner, approver đã được xác nhận.
- [ ] Baseline cũ **thật sự an toàn**, không mang vulnerability/compromise bị biết.
- [ ] Biết upgrade là one commit hay multiple commits/merge commit.
- [ ] Revert coherent file set, không dùng force push/reset shared history.
- [ ] No unrelated worktree changes bị xóa.
- [ ] XML/lockfile diff về đúng expected state hoặc retention differences đã được review.
- [ ] CI strict verification và locks vẫn giữ nguyên/được áp dụng.
- [ ] Unit/integration/smoke tests chạy lại.
- [ ] Previous release artifact digest/DB compatibility/feature flags đã được kiểm tra.
- [ ] Có monitoring, rollout control và incident communication.
- [ ] Có postmortem và kế hoạch fix nguyên nhân gốc.

## 15. Bài tập thực hành và câu hỏi đánh giá

**Bài 1 — Khác biệt bản chất.** `gradle.lockfile` có phát hiện artifact bị republish cùng group:name:version không? **Không**; nó khóa version, còn XML verification kiểm bytes/signatures của artifact hỗ trợ.

**Bài 2 — Upgrade chưa cập nhật locks.** build.gradle đổi `3.16.0 → 3.17.0` nhưng lockfile vẫn cũ. Chuyện gì có thể xảy ra? Resolver vẫn bị strict constraint phiên bản locked hoặc resolution fail; cần update lock state có chủ đích.

**Bài 3 — Missing checksum.** Version mới có lock nhưng strict verification không có JAR/POM hash. Có nên chọn `--dependency-verification off`? **Không**; cần bootstrap/review publisher provenance và commit metadata.

**Bài 4 — Hash đổi dưới cùng coordinate.** Có nên copy actual SHA vào XML? **Không**; điều tra artifact integrity và repository trước.

**Bài 5 — Full vs selective update.** Khi chỉ nâng Commons Lang, cờ nào thường hợp lý hơn? **`--update-locks org.apache.commons:commons-lang3`**, nhưng vẫn review transitive graph.

**Bài 6 — Scope.** Root monorepo có `:app`, `:lib`. Chạy root `dependencies --write-locks` có tự khóa cả hai subprojects không? **Không**.

**Bài 7 — Strict lock mode.** Vì sao `LockMode.STRICT` có thể fail dù declarations đúng? Configuration marked locked thiếu persisted lock state.

**Bài 8 — Old XML entries.** Sau nâng 3.16.0 → 3.17.0, XML vẫn có hash 3.16.0. Có chứng minh update hỏng không? **Không**; Gradle incremental metadata generation giữ existing entries.

**Bài 9 — Cleanup.** Có nên xóa toàn bộ old version hashes ngay khi version mới deploy? **Không mặc định**; xem supported configurations, rollback window và retention policy.

**Bài 10 — PGP.** Signing key mới xuất hiện trong generated XML. Có thể tin ngay vì Gradle nhận signature không? **Không**; xác minh fingerprint và publisher identity.

**Bài 11 — origin.** Đổi annotation `origin="Generated by Gradle"` thành `origin="Verified"` có thực hiện cryptographic validation không? **Không**.

**Bài 12 — XML dry-run.** `--write-verification-metadata sha256 help --dry-run` có thể bỏ qua loại dependency nào? Dependency chỉ resolve trong **task execution**.

**Bài 13 — Rollback scope.** Nếu upgrade đổi Wrapper, plugin versions, build scripts, locks và XML, chỉ `git restore gradle.lockfile` có đủ không? **Không**, phải revert coherent changeset.

**Bài 14 — Git history.** Vì sao nên `git revert` trên branch thay vì `git reset --hard`/force push main? Revert ghi audit commit, không viết lại shared history.

**Bài 15 — Released artifact.** Git đã revert; production app có tự rollback không? **Không**, cần deployment rollback/forward fix theo actual artifact digest.

**Bài 16 — Baseline có CVE.** New release gây regression, old release có CVE nghiêm trọng. Rollback tự động có đúng không? **Không**, security/release owner phải đánh giá forward fix/mitigations.

**Bài 17 — Private mirror.** Maven proxy outage thì sửa XML checksum ngay? **Không**; kiểm mirror/network/provenance, dùng cache/offline có kiểm soát nếu đủ artifacts.

**Bài 18 — CI tự ghi generated hashes.** Vì sao nguy hiểm? CI có thể tự trust bytes độc hại vừa download và tạo green build.

**Bài 19 — Report after revert.** `./gradlew -q run` in cùng stdout trước/sau. Có chứng minh version graph giống baseline không? **Không**; phải kiểm `dependencyInsight`, lockfiles/XML/commit và CI.

**Bài 20 — Incident response.** Checksum mismatch nhưng plugin/JAR vẫn chạy nếu tắt strict. Có nên tắt? **Không**; freeze, triage, khôi phục trust chain và chỉ build/release từ verified artifacts.

### Tự kiểm tra nhanh

1. `--write-locks` cập nhật gì? **Resolved versions của configurations đã resolve**.
2. `--update-locks` làm gì? **Selective allowed module lock updates**.
3. `--write-verification-metadata sha256` viết gì? **Expected SHA metadata từ artifacts hiện được resolve**.
4. Generated SHA chứng minh publisher trustworthy? **Không**.
5. XML incremental có auto-remove old entries không? **Không**.
6. `--dry-run` tạo gì ở verification bootstrap? **verification-metadata.dryrun.xml**.
7. Mode verification phù hợp release? **strict**.
8. Lockfile có SHA-256? **Không**.
9. XML verification pin version range? **Không**.
10. Core Wrapper checksum kiểm downloaded Gradle ZIP? **Có**.
11. Wrapper ZIP checksum tự kiểm Wrapper JAR? **Không**.
12. Plugin requests được project lockAll tự khóa? **Không tự động**.
13. Multi-project thường có lockfiles theo project? **Có**.
14. Included builds có verification context riêng khi chạy standalone? **Có**.
15. Chữ ký PGP hợp lệ có đảm bảo artifact không CVE? **Không**.
16. `git revert` có viết lại shared history? **Không**, tạo commit ngược.
17. Git revert có tự rollback published container? **Không**.
18. Old version đã compromised có nên rollback? **Không mặc định**.
19. CI nên auto-trust mới khi checksum mismatch? **Không**.
20. Điều quan trọng nhất? **Quản lý declared versions, locked graph, trust metadata và release state thành một change set có review**.

## 16. Các tài liệu chính thức

- **Gradle — Dependency Locking:** `lockAllConfigurations`, `LockMode.STRICT`, `--write-locks`, `--update-locks`, per-project lockfiles và changing module limits: https://docs.gradle.org/current/userguide/dependency_locking.html
- **Gradle — Dependency Verification:** verification metadata, SHA-256/PGP, strict mode, incremental generation, dry-run, `origin="Generated by Gradle"`, scope và keyrings: https://docs.gradle.org/current/userguide/dependency_verification.html
- **Gradle — Wrapper:** distribution SHA-256, Wrapper JAR validation, upgrade/downgrade và checked-in scripts: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- **Gradle — Best Practices for Security:** wrapper integrity, approved repositories, dependency verification/locking và CI policy: https://docs.gradle.org/current/userguide/best_practices_security.html
- **Gradle — Securing the Build Tool:** source/CI/build logic trust boundaries và included builds: https://docs.gradle.org/current/userguide/securing_build_tool.html
- **Gradle — Dependency Caching:** stale/changing modules, offline/refresh và repository provenance: https://docs.gradle.org/current/userguide/dependency_caching.html
- **Gradle — Version Catalogs:** requested aliases vs resolved graph: https://docs.gradle.org/current/userguide/version_catalogs.html
- **Gradle — Viewing Dependencies:** `dependencies` và `dependencyInsight` phục vụ review versions: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- **Gradle — Command Line Interface:** flags về locking, verification, log/stacktrace/dry-run: https://docs.gradle.org/current/userguide/command_line_interface.html
- **Gradle — Java Testing:** Java toolchains, JUnit Platform và Test task: https://docs.gradle.org/current/userguide/java_testing.html
- **Git — Reverting Commits:** `git revert` và audit history: https://git-scm.com/docs/git-revert
- **Git — Restoring Working Tree Files:** `git restore`, cảnh báo mất uncommitted changes: https://git-scm.com/docs/git-restore

**Kết luận:** Một rollback an toàn trong Gradle không chỉ hạ `implementation '...:version'`. Phải xác định **known-good commit và artifact**, khôi phục nhất quán **declarations/catalog, resolved lockfiles, verification metadata/PGP keys, Wrapper/plugins/build logic và CI JDK** trong phạm vi change set, kiểm thử lại dưới **strict verification + locking**, rồi mới kiểm soát deployment. Không tự chấp nhận checksum mới từ repository vừa báo mismatch, không dùng lenient/off làm đường tắt và không quay về phiên bản cũ đã bị compromise. Mỗi lần nâng cấp và rollback đều cần review, evidence, approval, release-monitoring và kế hoạch cleanup sau support window.