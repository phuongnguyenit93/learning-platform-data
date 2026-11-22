# Checklist review build Gradle: tính đúng, khả năng bảo trì, hiệu năng và an toàn

## Mục tiêu và cách sử dụng bài học

Một pull request sửa `build.gradle`, `settings.gradle`, version catalog, custom task hoặc CI pipeline có thể khiến `BUILD SUCCESSFUL` xuất hiện mà vẫn tạo sai artifact, bỏ sót test, dùng phiên bản dependency không dự kiến, tăng thời gian build đáng kể hoặc mở đường cho mã/credential không đáng tin. Vì vậy **review build** là hoạt động đánh giá **hành vi và khả năng tái tạo của hệ thống build**, không chỉ đọc cú pháp Gradle DSL.

Bài thuộc nhóm **Thực hành tổng hợp**. Sau khi học, bạn có thể thực hiện một review có bằng chứng theo bốn trục:

1. **Tính đúng (Correctness):** Build đúng source, đúng modules, đúng Java toolchain, đúng dependency graph và task dependency, chạy đủ tests, tạo artifact thực sự dùng được, fail khi phải fail.
2. **Khả năng bảo trì (Maintainability):** Build logic dễ hiểu, có một nguồn sự thật, conventions dùng lại được, plugin boundaries rõ, không lạm dụng cấu hình toàn cục, thay đổi có thể review và nâng cấp.
3. **Hiệu năng (Performance):** Có baseline công bằng; phân biệt startup/configuration/execution; cacheable/incremental tasks đúng inputs/outputs; không I/O sớm hoặc resolve dependencies vô cớ; đo tác động trước/sau.
4. **An toàn (Security):** Wrapper/distribution/plugin/dependency được kiểm nguồn; repository/credentials và caches được bảo vệ; không hardcode secret, không phát tán secret qua logs/artifacts; CI tách trusted release khỏi untrusted PR.

Bài gồm **phiếu checklist theo mức độ nghiêm trọng**, các lệnh kiểm chứng, lab Java 17 hai module có JUnit 5, những anti-pattern thường gặp, quy trình review trước–sau, cách thu thập số liệu và bài tập có đáp án. Các snippets không phải lúc nào cũng độc lập; mỗi đoạn sẽ được gắn nhãn **đầy đủ**, **fragment** hoặc **phản ví dụ**.

**Nguyên tắc lớn:** Một ô checklist chỉ được đánh dấu **PASS** khi có bằng chứng phù hợp. “Không thấy lỗi trong diff” không đủ để khẳng định build đúng. Nếu chưa có quyền chạy CI hoặc thiếu môi trường, đánh dấu **UNVERIFIED** với lý do và bước xác minh tiếp theo, không giả định PASS.

---

## 1. Review build khác review Java code ở đâu?

Review Java code tập trung vào thuật toán, API, điều kiện biên, testability, complexity, readability. Review Gradle build đánh giá thêm **cách biến source thành kết quả**, nghĩa là:

- Nguồn sự thật của Gradle Wrapper, plugins, toolchain và dependency repositories.
- Gradle lifecycle: initialization, configuration, task execution.
- Project graph: root, included builds, multi-project modules.
- Task graph và up-to-date/build cache semantics.
- Source sets, classpaths, variants, compile/test/runtime separation.
- Dependencies thực sự được **selected/resolved**, không chỉ versions được viết trong catalog.
- Những output/artifact files được upload hoặc publish.
- Tương tác với CI runners, secrets, caches, registry và release environment.
- Chi phí build với cache cold, cache warm, thay một file, thay build script và đổi branch.
- Các failure modes mà một build log xanh có thể che khuất.

Ví dụ, một đoạn sau có thể chạy được trên máy developer:

~~~groovy
tasks.register('packageManual', Exec) {
    commandLine 'sh', 'scripts/package.sh'
}
~~~

Nhưng reviewer cần hỏi: script dùng input nào, có cross-platform không, CI agent có shell ấy không, output file ở đâu, task được nối vào `assemble`/`check` chưa, exit code có chặn pipeline không, script có truy cập credential không? Nếu không có bằng chứng, `packageManual` chưa đạt yêu cầu review chỉ vì nó “chạy OK một lần”.

### 1.1. Bốn tiêu chí không độc lập tuyệt đối

| Thay đổi | Tính đúng | Bảo trì | Hiệu năng | An toàn |
| --- | --- | --- | --- | --- |
| Thêm `clean` vào mọi job | Có thể che stale output | Cần lý do | Có thể phá incremental work | Không phải cơ chế cô lập |
| Dùng version `1.+` | Resolution có thể đổi theo thời gian | Khó review upgrade | Tăng metadata lookup | Supply-chain drift |
| Hardcode access token | Build có thể publish được | Không thể chia sẻ an toàn | Không liên quan | Blocker nghiêm trọng |
| `tasks.create` 1.000 tasks eager | Có thể vẫn chạy đúng | Logic phức tạp | Configuration chậm | Tăng plugin surface |
| Bỏ JUnit XML trên failed tests | Không có evidence khi fail | Khó điều tra | Ít tác dụng | Che quality failure |
| Cấu hình Java toolchain 17 | Ổn định compiler | Một nguồn sự thật | Giảm drift cache | Kiểm soát môi trường |

Vì vậy reviewer nên ghi phát hiện theo **hành vi + bằng chứng + rủi ro + đề xuất**, không gắn nhãn chung chung “Gradle code xấu”.

---

## 2. Quy trình review năm bước

### Bước 1 — Xác định thay đổi và trust boundary

Đọc diff của:
- `settings.gradle`/`.kts`, `build.gradle`/`.kts` ở root/modules.
- `gradle/wrapper/gradle-wrapper.properties`, Wrapper scripts/JAR nếu thay đổi.
- `gradle/libs.versions.toml`, plugin versions, lockfiles, verification metadata.
- `build-logic` included build, `buildSrc`, `gradle.properties`, init scripts của CI nếu có.
- `.gitlab-ci.yml`, `Jenkinsfile`, GitHub Actions workflows hoặc tương đương.
- Custom task/plugin code, packaging scripts, test-report/artifact upload rules.

Không đọc một lệnh Gradle tách khỏi task graph và môi trường; một thay đổi duy nhất ở plugin version có thể ảnh hưởng nhiều modules.

### Bước 2 — Thu thập baseline

Ghi trước khi thử:
- Commit SHA trước/sau.
- Gradle Wrapper version và distribution URL/checksum.
- `java -version` của Gradle runtime và Java toolchain compile/test.
- OS, CPU, RAM, runner type, cache policy.
- Các Gradle tasks đã chạy, số tests, output filenames/hashes khi cần.
- Thời gian `cold build`, `warm build`, incremental one-source-change.
- Warnings và known limitations.

**Không đánh giá performance bằng một lần chạy trên hai máy khác nhau.** Nếu chỉ có CI logs hiện tại, ghi mức chắc chắn thấp hơn và tạo follow-up đo có kiểm soát.

### Bước 3 — Chạy kiểm chứng chức năng

Trên checkout sạch/agent tin cậy:

~~~bash
./gradlew --version
./gradlew projects
./gradlew :lib:check :app:check :app:distZip
~~~

Các task paths chỉ đúng cho **lab hai module được nêu ở phần thực hành**. Với dự án thật, dùng task paths phù hợp. Kiểm JUnit reports, artifact content và negative test (ví dụ một assertion cố tình fail trên branch test) thay vì chỉ tìm chuỗi `BUILD SUCCESSFUL`.

### Bước 4 — Review cấu trúc, hiệu năng, bảo mật

Dùng checklist ở các mục tiếp theo. Với lỗi, xác định **mức độ nghiêm trọng**, phạm vi ảnh hưởng và bằng chứng; không buộc một rule chung vào mọi plugin/monorepo mà không xét ngữ cảnh.

### Bước 5 — Chốt quyết định

- **APPROVE:** Các checks bắt buộc PASS; N/A có lý do; không có blocker.
- **REQUEST CHANGES:** Có P0/P1 hoặc quality gate quan trọng thiếu; mô tả cách sửa và test lại.
- **COMMENT/UNVERIFIED:** Còn thông tin cần bổ sung; chưa kết luận PASS hoặc FAIL.
- **FOLLOW-UP:** Rủi ro ít nghiêm trọng không chặn merge có issue/owner và thời hạn rõ.

Review không chỉ “đếm ô xanh”: một phát hiện về production signing key ở Git phải chặn release dù 100 ô còn lại PASS.

---

## 3. Hệ thống mức độ nghiêm trọng và bằng chứng

| Mức | Ý nghĩa | Quyết định gợi ý |
| --- | --- | --- |
| **P0 — Critical** | Credential/private key lộ; build thay artifact không kiểm soát; supply-chain compromise đang có | Dừng publish/merge, phối hợp incident |
| **P1 — High** | Build sai output, bỏ tests bắt buộc, CI báo xanh dù fail, untrusted code có publish rights | Request changes, cần khắc phục trước merge |
| **P2 — Medium** | Thiếu lock/verification ở dự án cần reproducibility, task inputs/outputs chưa khai báo, performance regression đáng kể | Cần kế hoạch sửa/đánh giá mức chặn theo policy |
| **P3 — Low** | Formatting, tên task khó đọc, duplication nhỏ có hướng cải tiến | Comment/follow-up không nhất thiết chặn |

Đây là **rubric ví dụ**, không thay security policy của công ty. Một P2 có thể trở thành P1 khi xuất hiện trong production release pipeline.

### 3.1. Bốn trạng thái checklist

- **PASS:** Đã kiểm, có evidence link/lệnh/output.
- **FAIL:** Có lỗi có thể tái hiện, severity và fix cụ thể.
- **UNVERIFIED:** Chưa đủ evidence, xác định điều kiện còn thiếu.
- **N/A:** Không áp dụng, giải thích rõ lý do; ví dụ Android checks N/A cho Java-only project.

### 3.2. Một finding tốt phải có gì?

Một review comment thực tế có thể theo mẫu:

~~~text
ID: COR-06
Severity: P1
Finding: CI đang gọi :app:assemble nhưng không gọi :app:check.
Evidence: job logs, test report path trống; build.gradle không nối check.
Impact: Thay assertion thành sai nhưng package job vẫn xanh.
Change: Thêm :lib:check :app:check trước distZip; upload JUnit XML khi fail.
Verify: CI fail khi assertion sai; CI xanh khi hoàn nguyên; có test reports.
~~~

Nêu **đường dẫn, task path, tác động và cách tái kiểm** hữu ích hơn nhận xét “cần kiểm tra tests”.

---

## 4. Checklist tính đúng: Gradle Wrapper, môi trường và build graph

| ID | Điều cần xác nhận | Bằng chứng nên thu | Khi FAIL |
| --- | --- | --- | --- |
| COR-01 | Commit đủ Wrapper (`gradlew`, `.bat`, JAR, properties) | `git ls-files` và `./gradlew --version` | Build không nhất quán giữa máy |
| COR-02 | Wrapper URL/version/checksum được phê duyệt | properties và quy trình Wrapper validation | Có thể chạy Gradle distribution sai |
| COR-03 | JDK chạy Gradle tương thích version Wrapper | `java -version`, `./gradlew --version` | CI/local lệch runtime |
| COR-04 | Java compile/test target được khai báo bằng toolchain | `java.toolchain` + `options.release` nếu cần | Bytecode/API khác mong đợi |
| COR-05 | `settings` khai báo đúng modules/included builds | `./gradlew projects` | Bỏ sót module hoặc project path sai |
| COR-06 | CI chạy đúng verification tasks | Logs của `:module:check` | Build xanh thiếu test/quality gate |
| COR-07 | Task dependencies được biểu diễn bằng Gradle graph | `dependsOn`, Project dependency, task reports | Task chạy sai thứ tự hoặc stale file |
| COR-08 | Build artifact gồm đúng files/dependencies | JAR/ZIP inventory, run smoke test | Artifact không chạy hoặc thiếu runtime lib |
| COR-09 | Tasks fail đúng khi compile/test/packaging fail | Negative test trên branch thử | False-green CI |
| COR-10 | Test reports được tạo và lưu khi failure | JUnit XML, CI reporting settings | Không có evidence để debug |
| COR-11 | Test discovery thực sự chạy cases kỳ vọng | Test count/IDs và XML | `test NO-SOURCE` bị nhầm PASS |
| COR-12 | Các source sets/variants đúng | `tasks --all`, source sets/variant docs | Bỏ integration/variant task |
| COR-13 | Dependencies được phân loại đúng `api`/`implementation`/runtime/test | `dependencies`/`dependencyInsight` | Leaked API hoặc runtime lỗi |
| COR-14 | Resolved graph có phiên bản dự kiến | DependencyInsight và lock/constraints | Transitive upgrade ngoài ý muốn |
| COR-15 | Thay đổi build logic có regression tests | Fixture/JUnit/TestKit/CI | Dễ tái lỗi khi nâng plugin |
| COR-16 | Không dùng file paths cục bộ không portable | Scripts/Gradle files review | Build chỉ chạy trên máy tác giả |
| COR-17 | Artifact mang version/commit phù hợp release | Publication metadata, checksum/manifest | Release không rõ provenance |

### 4.1. `BUILD SUCCESSFUL` chưa chứng minh tests chạy

Gradle có thể báo thành công với `test NO-SOURCE` khi project không có test sources. Một `build` thành công cũng có thể thiếu integration tests nếu chúng không được nối vào `check`. Reviewer cần xem:
- `:lib:test` và `:app:test` có trong task graph không?
- JUnit XML ghi **bao nhiêu tests** và kết quả gì?
- Test framework có cấu hình `useJUnitPlatform()` cho JUnit 5?
- `ignoreFailures` có được bật không?
- Có `-x test`, `--exclude-task` hoặc CI `allow_failure` không?
- Có test filter/tag vô tình bỏ phần quan trọng?
- Unit/integration/functional tests cần task nào?

### 4.2. Task dependency khác task ordering

~~~groovy
tasks.named('packageReport') {
    mustRunAfter 'generateReport'
}
~~~

**Phản ví dụ** nếu mục tiêu là bắt buộc sinh report trước package: `mustRunAfter` chỉ áp quy tắc thứ tự **khi cả hai tasks nằm trong graph**, không tự thêm `generateReport` vào graph.

Đúng nếu thật sự cần report:

~~~groovy
tasks.named('packageReport') {
    dependsOn 'generateReport'
}
~~~

Đây là **configuration fragment** chỉ hợp lệ khi cả hai task names đã tồn tại. Khi task tiêu thụ output của task khác, tốt hơn nối qua **Provider output property** để Gradle tự nhận dependency/provenance.

### 4.3. Không coi `--dry-run` là test correctness

`./gradlew :app:build --dry-run` hữu ích để xem task selection và ordering, nhưng **không thực thi compile/test/Zip task actions**, nên không xác nhận artifact chạy được.

### 4.4. `--rerun-tasks` và `--no-build-cache` dùng khi nào?

Khi nghi cache che lỗi:

~~~bash
./gradlew :lib:check :app:check --rerun-tasks --no-build-cache
~~~

Nó buộc thực thi lại selected task actions khi phù hợp và tránh output reuse từ Gradle Build Cache; đây là **diagnostic**, không nên áp mặc định cho mọi developer/CI run vì làm mất lợi ích incremental. `clean` và `--rerun-tasks` không hoàn toàn đồng nghĩa.

### 4.5. Project dependency tốt hơn hardcoded JAR path

Sai về semantics trong multi-project build:

~~~groovy
dependencies {
    implementation files('../lib/build/libs/lib.jar')
}
~~~

Nó dễ tạo phụ thuộc vào JAR cũ/chưa được build. Nên dùng:

~~~groovy
dependencies {
    implementation project(':lib')
}
~~~

Gradle gắn project dependency vào task/variant/artifact metadata; tránh giả định file JAR vật lý đã tồn tại trước khi build.

---

## 5. Checklist tính đúng: dependency resolution và reproducibility

| ID | Tiêu chí | Evidence |
| --- | --- | --- |
| DEP-01 | Repositories được khai báo rõ và ở nơi policy quy định | Settings/project repository blocks |
| DEP-02 | Không dùng dynamic/changing versions vô thức | Version catalog và dependency declarations |
| DEP-03 | Version catalog aliases không bị nhầm với selected versions | `dependencyInsight` |
| DEP-04 | Conflict resolution/platform/constraints được hiểu rõ | Resolved dependency graph |
| DEP-05 | Lockfiles có chính sách khi cần reproducible graph | Lock state và CI verification |
| DEP-06 | Dependency verification checksums/signatures theo policy | `gradle/verification-metadata.xml` |
| DEP-07 | Plugin versions và wrapper tương thích | Compatibility matrix/CI |
| DEP-08 | Maven metadata/POM publication nhất quán | Generated POM và artifact contents |
| DEP-09 | Java toolchain và encoding không phụ thuộc máy | Toolchain/`options.release`/UTF-8 |
| DEP-10 | `SNAPSHOT`/changing modules được dùng có chủ ý | Dependency review + registry policy |

### 5.1. Version catalog không ép resolved version

~~~toml
[versions]
junit = "5.11.4"

[libraries]
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
~~~

Catalog giúp chuẩn hóa **declared dependency versions** nhưng không bắt buộc transitive dependency graph dùng đúng version ở mọi configuration. Gradle chọn phiên bản theo resolution rules, constraints, platforms, rich versions và conflict resolution. Kiểm:

~~~bash
./gradlew :app:dependencies --configuration testRuntimeClasspath

./gradlew :app:dependencyInsight \
    --dependency org.junit.jupiter:junit-jupiter \
    --configuration testRuntimeClasspath
~~~

Tên dependency/configuration phù hợp **lab JUnit** ở phần thực hành; với dự án thật đổi selector.

### 5.2. Dependency locking là một lớp riêng

Dynamic version như `1.+` có thể resolve khác ở tương lai. Gradle dependency locking lưu resolved modules/versions theo configuration khi được cấu hình, giúp phát hiện graph đổi. Không tự cho rằng catalog là lockfile; dependency locking không bảo đảm bytes của changing module có cùng checksum.

Khi review lock state:
- File nào được track và phạm vi configurations nào đang locked?
- Thay đổi lockfile có giải thích upgrade không?
- Không dùng `--write-locks` vô tội vạ trong CI verification job.
- Khi upgrade có kiểm tests và transitive changes?
- Không đặt `lock` chỉ để che xung đột mà chưa hiểu nguyên nhân.

### 5.3. Dependency verification là lớp khác

Gradle dependency verification có thể xác minh checksums/signatures của downloaded artifacts theo metadata. **Nó không tự xác thực generated JAR của chính project**. Khởi tạo verification metadata từ repository hiện tại là **trust on first use**, nên generated metadata phải review, không chấp nhận mọi checksum mới một cách mù quáng.

Trong một repository đã được cấu hình verification metadata, CI có thể chạy ở strict mode theo policy. Không bật cờ strict rồi nghĩ Gradle tự có trusted checksums nếu file metadata chưa được tạo và duyệt.

### 5.4. Reproducibility nhiều mức

Phân biệt:
- **Functional reproducibility:** Cùng source/compiler/deps tạo hành vi đúng.
- **Dependency reproducibility:** Cùng configuration resolve cùng module versions/artifact bytes.
- **Byte-for-byte reproducibility:** Chính JAR/ZIP bytes giống nhau trong điều kiện kiểm soát đủ timestamps, file order, OS/permissions, encoding và toolchain.

Một ZIP hash khác **không đủ** kết luận code sai; cũng không được mặc định “cùng source” là bytes luôn khớp khi dynamic versions/timestamps thay đổi. Nếu release đòi bit-reproducibility, cần policy riêng và kiểm chính hash.

---

## 6. Checklist bảo trì: tổ chức build scripts và plugins

| ID | Tiêu chí | Dấu hiệu tốt |
| --- | --- | --- |
| MNT-01 | Settings chỉ mô tả build layout, plugin/dependency management | Không giấu module trong script khác |
| MNT-02 | Mỗi module áp plugin thực sự cần | `java-library`/`application` đúng module |
| MNT-03 | Không lặp quá nhiều toolchain/test/plugin conventions | Dùng `build-logic` convention plugins khi quy mô phù hợp |
| MNT-04 | Version declarations tập trung và có nghĩa | Version catalog/approved platform |
| MNT-05 | Tên task/config rõ và có group/description | `tasks --all` có thể đọc |
| MNT-06 | Dùng `tasks.register`/`tasks.named`/`configureEach` | Tránh eager creation không cần thiết |
| MNT-07 | Không có `afterEvaluate`/`allprojects` vô lý | Plugin callbacks và per-project configuration |
| MNT-08 | Không hardcode absolute paths/version/OS | Provider + project layout |
| MNT-09 | Custom task inputs/outputs có hợp đồng rõ | Typed task properties |
| MNT-10 | Tách build logic khỏi source application đúng chỗ | Convention plugin/included build |
| MNT-11 | Nâng plugin có compatibility strategy | Wrapper/JDK/plugin matrix |
| MNT-12 | Docs có một entrypoint build/test/release | README và CI gọi cùng Gradle tasks |
| MNT-13 | Không duplicate CI logic ngoài Gradle | CI orchestration thôi |
| MNT-14 | TestKit/functional tests cho reusable plugin | Fixtures có positive/negative cases |

### 6.1. `allprojects`/`subprojects` có thể làm coupling khó bảo trì

~~~groovy
// Phản ví dụ cho monorepo lớn:
allprojects {
    apply plugin: 'java'
}
~~~

Nó ép cả root aggregator và project không phải Java áp Java plugin. Khi có Android/Kotlin platform/Java platform projects, dễ tạo sai model. **Convention plugins áp tại những modules cần chúng** thường rõ hơn. Với project nhỏ, duplication nhỏ có thể chấp nhận nếu chưa đáng tạo plugin.

### 6.2. `build-logic` so với `buildSrc`

Hai cách đều có thể chứa reusable build logic. Included build tên `build-logic` được Gradle docs hiện đại khuyến nghị cho modularized large builds, nhưng không phải quy tắc buộc mọi project. Khi review:
- Convention nào cần reuse?
- Plugin có tạo public type-safe extension không?
- Cần unit/functional TestKit không?
- Có đang tạo cycle và plugin version drift không?
- Build logic change có invalidation đúng những project liên quan không?

### 6.3. Chọn task names có ý nghĩa

Tên như `buildThing` hoặc `doStuff` thiếu intent. Tên như `generateApiMetadata`, `verifyLicenseHeaders`, `assembleDistribution` cùng group/description rõ giúp developer biết task dùng làm gì. Nhưng đừng tự đặt tên giống core plugin task (`test`, `jar`) nếu không hiểu model conflicts.

### 6.4. Giảm script side-effects trong configuration

Phản ví dụ:

~~~groovy
// Phản ví dụ: công việc tốn I/O xảy ra ở configuration.
def response = new URL('https://example.invalid/config').text
tasks.register('showConfig') {
    doLast {
        println response
    }
}
~~~

Mọi lệnh Gradle cần evaluate build script có thể chạm network trước khi user yêu cầu task đó. Điều này gây build chậm, không offline được, lỗi với CI restricted network, và dễ phá Configuration Cache. Dùng Provider API/typed task inputs và thực hiện I/O trong task action khi cần, với validation và security policy.

---

## 7. Checklist hiệu năng: review từ baseline, không từ cảm giác

| ID | Tiêu chí | Cách kiểm |
| --- | --- | --- |
| PERF-01 | Có baseline cùng commit/hardware/JDK/cache state | Ghi môi trường và repetitions |
| PERF-02 | Đã tách job overhead khỏi Gradle execution | CI timeline vs Gradle task/profile |
| PERF-03 | Configuration không resolve dependencies vô cớ | Build Scan/profile |
| PERF-04 | Tasks dùng configuration avoidance | `register`, `named`, `configureEach` |
| PERF-05 | Custom tasks khai inputs/outputs | Task code/validation |
| PERF-06 | Up-to-date và Build Cache thực sự hoạt động | Task outcomes và cache logs |
| PERF-07 | Configuration Cache được thử trên build/plugin tương thích | Hai invocations cùng task graph |
| PERF-08 | Java compilation tránh rebuild không cần | Thay một source rồi xem tasks |
| PERF-09 | Tests không chạy trùng/hết tài nguyên | Test plan và duration |
| PERF-10 | `clean` không được gọi mọi lúc vô lý | CI scripts và cache rationale |
| PERF-11 | Gradle Daemon phù hợp trust/CI lifetime | Daemon strategy + profiler |
| PERF-12 | Remote cache I/O không đắt hơn tiết kiệm | Cache hit/miss và transfer time |
| PERF-13 | CPU/RAM/parallelism được đo | Worker count, memory, runner |
| PERF-14 | Nâng plugin/Wrapper không gây regression lớn | Before/after summary |

### 7.1. Phân biệt startup, configuration và execution

Một CI job có tổng thời gian:
- Image pull, queue time, checkout, cache restore.
- JDK/Wrapper startup.
- Gradle initialization/configuration.
- Task execution.
- Test reports upload, artifact archiving.

Vì vậy wall-clock của CI job khác **Gradle task execution time**. Khi thấy job chậm, chưa chắc Java compilation chậm. Đầu tiên xác định bottleneck.

### 7.2. Gradle `--profile`

~~~bash
./gradlew :lib:check :app:check --profile
~~~

Gradle tạo HTML report theo convention dưới `build/reports/profile/` của build. Nó cho biết phase và task timing; không thay build scan/profiler cho phân tích sâu, và lần đầu có thể chịu JVM/download warm-up.

### 7.3. Build Cache khác Configuration Cache

- **Build Cache:** tái sử dụng task outputs theo inputs/action implementation được fingerprint.
- **Configuration Cache:** tái sử dụng configured task graph, tránh chạy configuration phase khi input configuration không đổi.
- **Dependency Cache:** downloaded modules/metadata; không phải Build Cache.
- **CI cache:** file storage cho runners; có thể giữ wrapper/dependencies/cache tùy chính sách.

Bật thử cho một task graph:

~~~bash
./gradlew :lib:check :app:check --build-cache
./gradlew :lib:check :app:check --configuration-cache
~~~

Chạy lại cùng lệnh để xem cache reuse. **Không được giả định mọi plugin/task đều tương thích Configuration Cache**; xử lý reported problems hoặc chỉ rõ limitations, không che bằng việc tắt diagnostics.

### 7.4. `UP-TO-DATE` khác `FROM-CACHE`

- `UP-TO-DATE`: Task outputs hiện tại còn hợp lệ theo tracked inputs/outputs.
- `FROM-CACHE`: Task outputs được khôi phục từ Gradle Build Cache.
- `NO-SOURCE`: Task không có source/input source để làm việc.
- `SKIPPED`: Task không được chạy theo điều kiện.
- Task executed: action thực sự chạy.

Review phải giải thích từng outcome quan trọng; `NO-SOURCE` cho test không thể thay unit test evidence.

### 7.5. Đo cold/warm/incremental cho công bằng

Một protocol:
1. Cùng runner loại máy/JDK/Wrapper/commit.
2. Bắt đầu từ clean checkout, ghi rõ Gradle User Home/cache state.
3. Chạy ít nhất vài lần đo, bỏ qua warm-up khi policy cho phép.
4. Ghi median và phân bố, không chọn một run nhanh nhất làm kết luận.
5. Chạy warm no-change build, rồi thay một Java source và đo incremental build.
6. Kiểm test counts/artifact correctness sau tối ưu, vì một build “nhanh” có thể đang bỏ tests.
7. Ghi điều kiện cache enabled/disabled; đừng so hai trạng thái cache khác nhau như thể cùng workload.

**Không dùng `clean` cho mọi warm build**; nó chủ động xóa outputs, làm test incremental/up-to-date mất ý nghĩa.

### 7.6. Thường gặp: configuration phase làm I/O/resolve sớm

~~~groovy
// Phản ví dụ:
def allJars = configurations.runtimeClasspath.files
tasks.register('showJars') {
    doLast {
        println allJars.size()
    }
}
~~~

Đây là resolution ở configuration time khi project có runtimeClasspath. Nó có thể khiến `help` cần network và gây lag. Nên chuyển logic sang task action có đúng @InputFiles/Provider và không capture Project/configuration across task execution nếu muốn Configuration Cache.

---

## 8. Checklist an toàn: build logic là executable code

| ID | Tiêu chí | Điều cần xem |
| --- | --- | --- |
| SEC-01 | Wrapper scripts/JAR/distribution đúng nguồn | `gradle-wrapper.properties`, checksum, validation |
| SEC-02 | Plugin repositories được kiểm soát | `pluginManagement.repositories` và plugin versions |
| SEC-03 | Dependency repositories dùng HTTPS và content filtering phù hợp | Settings/dependency resolution policy |
| SEC-04 | Artifact checksums/signatures theo policy | Verification metadata, signed artifacts |
| SEC-05 | Không hardcode token/password/private signing key | Git diff/history, code scanner |
| SEC-06 | CI secrets được cấp theo trust boundary | GitLab protected variables/Jenkins Credentials |
| SEC-07 | PR jobs không có production publish/sign permissions | Runner/job identity audit |
| SEC-08 | Gradle User Home có ACL riêng | `~/.gradle` permissions, init scripts |
| SEC-09 | Không remote `apply from` không tin cậy | Settings/build scripts review |
| SEC-10 | Caches có trusted writers/isolated namespaces | Remote Build Cache config |
| SEC-11 | Logs/reports/artifacts không chứa secrets | Artifact content scanning |
| SEC-12 | Maven publish chỉ chạy trên protected refs | CI rules, approvals, credentials |
| SEC-13 | Signing key không ở Git/build outputs | Secret store/Key management |
| SEC-14 | Dependency changes được review cả transitive graph | `dependencyInsight`, lock/checksums |
| SEC-15 | Task chạy shell/network có quyền và inputs rõ | Exec/JavaExec/custom plugin code |
| SEC-16 | Không dùng repository credentials trong URL | Credential API/secret manager |

### 8.1. Gradle Wrapper là điểm tin cậy đầu tiên

Trước khi build script chạy, Wrapper đã có thể tải/chạy Gradle distribution. Kiểm:
- `gradlew`, `gradlew.bat`, Wrapper JAR được commit từ nguồn tin cậy.
- Distribution URL dùng HTTPS, version phù hợp.
- `distributionSha256Sum` khi policy yêu cầu, JAR validation.
- Không tự sửa Wrapper scripts/JAR bằng binary không rõ nguồn.

Không coi gradle-wrapper.jar là một dependency bình thường sẽ được Gradle verification metadata tự bảo vệ; nó được chạy trước.

### 8.2. Secrets không chỉ rò qua Git

Token có thể nằm trong `src/main/resources`, JUnit XML, logs, Build Scan, ZIP, container layers, custom task output hoặc configuration cache. `.gitignore` không ngăn custom Copy/Zip lấy file untracked. CI masking chủ yếu áp cho console text theo platform, không thay artifact scan.

### 8.3. Gradle User Home và init scripts

`~/.gradle/gradle.properties` có thể chứa plain-text credentials, `~/.gradle/init.d` có executable init scripts. Một agent cho untrusted PR không nên share home/daemon với trusted release. Trên POSIX có thể bảo vệ ownership bằng `chmod 700 ~/.gradle` và `chmod 600 ~/.gradle/gradle.properties` khi file thuộc user hiện tại.

### 8.4. Không hardcode secret vào Gradle DSL

Phản ví dụ:

~~~groovy
publishing {
    repositories {
        maven {
            url = uri('https://repo.example.invalid/releases')
            credentials {
                password = 'DUMMY_NOT_A_REAL_SECRET'
            }
        }
    }
}
~~~

Dùng Gradle typed `PasswordCredentials`/project property names hoặc secret manager. Không đưa production token lên argv qua `-Ppassword=value` vì process listings/history/logs có thể lưu nó. Secret không được cấp cho untrusted jobs.

### 8.5. Signing không thay artifact content scanning

Public signature chứng minh identity/integrity theo trust model, **không mã hóa JAR**. Nếu JAR chứa token thì ký nó vẫn rò. Kiểm actual output trước signing/publishing; signing private key/passphrase chỉ tồn tại trong protected stage và không được archive.

### 8.6. Remote Build Cache và untrusted writers

Nếu untrusted PR job có quyền ghi cache mà release pipeline dùng, có nguy cơ cache poisoning. Dùng ACL/namespace isolation, không share credential files/Gradle User Home giữa runners có trust khác nhau.

---

## 9. Lab Java 17: dự án có thể được review từ đầu đến cuối

Ta dùng một multi-project Gradle build nhỏ, có production code, 4 JUnit tests, Java toolchain 17, dependency rõ, application ZIP và CI-like verification tasks. Mục tiêu là reviewer có thể quan sát **task graph, test reports, artifact, version/config** chứ không chỉ đọc lý thuyết.

### 9.1. Cấu trúc

~~~text
gradle-review-lab/
├── settings.gradle
├── build.gradle
├── gradle.properties
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── lib/
│   ├── build.gradle
│   ├── src/main/java/lab/lib/Numbers.java
│   └── src/test/java/lab/lib/NumbersTest.java
└── app/
    ├── build.gradle
    ├── src/main/java/lab/app/ReviewApp.java
    └── src/test/java/lab/app/ReviewAppTest.java
~~~

**Prerequisites:** JDK 17, Gradle Wrapper tương thích JDK 17, network hoặc internal Maven mirror để tải JUnit Jupiter 5.11.4 lần đầu. Wrapper files cần được tạo bởi Gradle hợp lệ/đã xác minh và commit đầy đủ. Không có bí mật nào trong lab.

### 9.2. settings.gradle

~~~groovy
rootProject.name = 'gradle-review-lab'
include 'lib', 'app'
~~~

### 9.3. gradle.properties

~~~properties
org.gradle.caching=true
org.gradle.warning.mode=summary
~~~

Build Cache được bật để quan sát hành vi, nhưng không bảo đảm mọi task cacheable. Chưa bật Configuration Cache mặc định để reviewer chủ động thử và xem compatibility.

### 9.4. Root build.gradle

~~~groovy
plugins {
    id 'base'
}

tasks.register('reviewAll') {
    group = 'verification'
    description = 'Run checks and create the application distribution'

    dependsOn(
        ':lib:check',
        ':app:check',
        ':app:distZip'
    )
}
~~~

Task `reviewAll` là aggregator, không có side effects. Nó yêu cầu Gradle chạy verification ở hai modules và tạo distribution. **Giới hạn:** Không nên diễn giải `dependsOn` theo thứ tự viết arguments; Gradle có thể chạy các tasks độc lập với thứ tự khác. Nếu muốn buộc **package chỉ sau tests pass** thì stage gating trong CI hoặc task dependency rõ thêm cần được thiết kế; ở đây `reviewAll` sẽ **fail** nếu bất kỳ dependency task nào fail, nhưng các tasks độc lập có thể đã chạy trước failure.

### 9.5. lib/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

repositories {
    mavenCentral()
}

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
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    reports {
        junitXml.required = true
        html.required = true
    }
}
~~~

Ở project thật, repositories nên được thống nhất trong settings theo policy khi phù hợp. Lab để `mavenCentral()` ở mỗi module cho dễ đọc; **không có internal/secret registry**.

### 9.6. lib/src/main/java/lab/lib/Numbers.java

~~~java
package lab.lib;

public final class Numbers {
    private Numbers() {
    }

    public static int sum(int... values) {
        int result = 0;
        for (int value : values) {
            result = Math.addExact(result, value);
        }
        return result;
    }
}
~~~

Java17 code không cần external libraries; `Math.addExact` cố ý fail bằng ArithmeticException khi overflow để test một boundary.

### 9.7. lib/src/test/java/lab/lib/NumbersTest.java

~~~java
package lab.lib;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

public class NumbersTest {
    @Test
    void sumsValues() {
        assertEquals(12, Numbers.sum(3, 4, 5));
    }

    @Test
    void zeroForEmptyInput() {
        assertEquals(0, Numbers.sum());
    }

    @Test
    void throwsOnOverflow() {
        assertThrows(
            ArithmeticException.class,
            () -> Numbers.sum(Integer.MAX_VALUE, 1)
        );
    }
}
~~~

Ba tests chứng minh happy path, empty input và overflow behavior. Đây là unit tests thực tế, không phải `test` task rỗng.

### 9.8. app/build.gradle

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

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
    implementation project(':lib')
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'lab.app.ReviewApp'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    reports {
        junitXml.required = true
        html.required = true
    }
}
~~~

`application` tạo `run`, `distZip` và Java model; `implementation project(':lib')` cho Gradle biết producer/consumer dependency graph. Nó tránh hardcoded `lib/build/libs/lib.jar`.

### 9.9. app/src/main/java/lab/app/ReviewApp.java

~~~java
package lab.app;

import lab.lib.Numbers;

public final class ReviewApp {
    private ReviewApp() {
    }

    public static String message() {
        return "REVIEW_OK: " + Numbers.sum(3, 4, 5);
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

### 9.10. app/src/test/java/lab/app/ReviewAppTest.java

~~~java
package lab.app;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

public class ReviewAppTest {
    @Test
    void messageIsExpected() {
        assertEquals("REVIEW_OK: 12", ReviewApp.message());
    }
}
~~~

Tổng cộng **4 test methods**: 3 ở lib, 1 ở app. Nếu Gradle compile và resolve JUnit bình thường, chạy các Test tasks cho ra 4 passed tests.

### 9.11. Chạy đầy đủ trên Linux/macOS

~~~bash
chmod +x ./gradlew
java -version
./gradlew --version
./gradlew projects
./gradlew --no-daemon --console=plain :lib:check :app:check
./gradlew --no-daemon --console=plain :app:distZip
./gradlew --no-daemon --console=plain :app:run
~~~

Dòng stdout **của Java main** (không phải toàn bộ Gradle log):

~~~text
REVIEW_OK: 12
~~~

### 9.12. Chạy trên Windows PowerShell

~~~powershell
java -version
.\gradlew.bat --version
.\gradlew.bat projects
.\gradlew.bat --no-daemon --console=plain :lib:check :app:check
.\gradlew.bat --no-daemon --console=plain :app:distZip
.\gradlew.bat --no-daemon --console=plain :app:run
~~~

Java stdout vẫn là `REVIEW_OK: 12`. Shell scripting và path syntax khác nhưng Gradle tasks tương đương. Không dùng `chmod` trên Windows.

### 9.13. Chạy `reviewAll`

~~~bash
./gradlew --no-daemon reviewAll
~~~

Lệnh này gọi aggregator được root đăng ký. **Không tự coi đây là release gate theo stage thứ tự**; với CI cần tách test/verify stage và package/release stage để không phát hành khi test chưa pass.

### 9.14. Test results và artifacts

Mặc định thường có:
- `lib/build/test-results/test/TEST-lab.lib.NumbersTest.xml`
- `app/build/test-results/test/TEST-lab.app.ReviewAppTest.xml`
- `lib/build/reports/tests/test/index.html`
- `app/build/reports/tests/test/index.html`
- `app/build/distributions/app.zip` hoặc file ZIP tương ứng project name/version.

JUnit XML có test count/durations/failures; thời gian là đo thực, không hardcode. Tên distribution file phụ thuộc project/version/plugin conventions; dùng glob cụ thể phù hợp thay vì giả định tên duy nhất.

### 9.15. Negative test: bắt buộc pipeline fail

Trên branch thử nghiệm, đổi trong **NumbersTest.java**:

~~~java
assertEquals(12, Numbers.sum(3, 4, 5));
~~~

thành:

~~~java
assertEquals(13, Numbers.sum(3, 4, 5));
~~~

Rồi chạy:

~~~bash
./gradlew :lib:test :app:test
~~~

Kỳ vọng `:lib:test` fail, exit code nonzero; tùy task ordering, `:app:test` có thể chưa chạy. JUnit XML lib ghi failed case. **Hoàn nguyên thay đổi** trước khi merge. Nếu CI vẫn xanh, review phải phát hiện bypass như `ignoreFailures`, `allow_failure`, shell `|| true` hoặc `returnStatus` bị bỏ qua.

### 9.16. Compile Java độc lập bằng javac để cross-check

Linux/macOS:

~~~bash
mkdir -p out/lib out/app

javac --release 17 -encoding UTF-8 \
    -d out/lib \
    lib/src/main/java/lab/lib/Numbers.java

javac --release 17 -encoding UTF-8 \
    -cp out/lib \
    -d out/app \
    app/src/main/java/lab/app/ReviewApp.java

java -cp out/app:out/lib lab.app.ReviewApp
~~~

Stdout chính xác:

~~~text
REVIEW_OK: 12
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out\lib,out\app | Out-Null

javac --release 17 -encoding UTF-8 -d out\lib lib\src\main\java\lab\lib\Numbers.java
javac --release 17 -encoding UTF-8 -cp out\lib -d out\app app\src\main\java\lab\app\ReviewApp.java
java -cp "out\app;out\lib" lab.app.ReviewApp
~~~

`javac` kiểm source Java production, **không chạy JUnit** và không chứng minh toàn bộ Gradle task/CI setup đúng. Đây là kiểm tra bổ sung.

---

## 10. Thực hành review một diff có anti-pattern

Giả sử PR đề xuất trong một Java project:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.example:client:1.+'
}

tasks.register('createArchive', Exec) {
    commandLine 'sh', './pack.sh'
}
~~~

Đây là **phản ví dụ**, không phải lab runnable: dependency `org.example:client:1.+` là minh họa, `pack.sh` chưa được cung cấp.

Reviewer nên nhận ra:
- **Correctness:** Archive không rõ inputs/outputs, task không được nối với verification/package lifecycle, script path/shell không portable.
- **Maintainability:** Logic đóng gói nằm trong script ngoài Gradle model, thiếu docs, thiếu task group/description.
- **Performance:** Exec task không khai inputs/outputs, có thể luôn chạy; khó cache/incremental.
- **Security:** Dynamic dependency cho phép graph drift, script executable là trust boundary; cần kiểm secret/artifact behavior.

### 10.1. Cách cải thiện theo đúng nhiệm vụ

Nếu mục tiêu chỉ là tạo distribution cho Java CLI app, **Application plugin** đã có distZip:

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'org.example.Main'
}
~~~

Đây là fragment, `org.example.Main` phải tồn tại. Thay custom `Exec` khi Application plugin cung cấp domain model phù hợp, tránh script copy files tùy ý.

### 10.2. Khi bắt buộc có custom task

Nếu output là một file text dựa trên input version, dùng typed task có inputs/outputs rõ. Cần phân biệt **task implementation** với **build file configuration**. Ví dụ Java17 Gradle task type trong file plugin/build logic:

~~~java
package lab.build;

import org.gradle.api.DefaultTask;
import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.OutputFile;
import org.gradle.api.tasks.TaskAction;

public abstract class GenerateVersionFile extends DefaultTask {

    @Input
    public abstract Property<String> getReleaseVersion();

    @OutputFile
    public abstract RegularFileProperty getDestination();

    @TaskAction
    public void generate() throws Exception {
        var path = getDestination().get().getAsFile().toPath();
        var parent = path.getParent();
        if (parent != null) {
            java.nio.file.Files.createDirectories(parent);
        }
        var contents = "release=" + getReleaseVersion().get() + "\n";
        java.nio.file.Files.writeString(
            path,
            contents,
            java.nio.charset.StandardCharsets.UTF_8
        );
    }
}
~~~

Đây là **fragment thuộc custom Gradle plugin source**, không phải Java app source `src/main/java` của lab. Cần Gradle API classpath (ví dụ qua `java-gradle-plugin` trong `build-logic`/`buildSrc`) và đăng ký task. Task khai rõ `@Input` và `@OutputFile`, phù hợp incremental/up-to-date behavior. Nếu muốn `@CacheableTask`, còn cần bảo đảm output deterministic, path sensitivity và Gradle cache rules; không thêm annotation chỉ để có `FROM-CACHE`.

Trong plugin apply method, ví dụ registration fragment:

~~~java
project.getTasks().register(
    "generateVersionFile",
    GenerateVersionFile.class,
    task -> {
        task.getReleaseVersion().set(
            project.provider(() -> project.getVersion().toString())
        );
        task.getDestination().set(
            project.getLayout().getBuildDirectory()
                .file("generated/release.txt")
        );
    }
);
~~~

Fragment này **chỉ minh họa API wiring**; với Configuration Cache cần tránh provider closure capture Project ở execution time và chọn Property/Provider configuration-phase safe. Ví dụ có thể thay `project.provider` bằng `task.getReleaseVersion().set(project.getVersion().toString())` trong plugin configuration nếu version là public stable config.

### 10.3. Nên review generated artifacts thế nào?

- File có nằm ở `build/` thay vì sửa source tree không?
- Output path là `RegularFileProperty` hay hardcoded absolute path?
- Input version có được theo dõi và invalidate khi đổi không?
- Task có gây network I/O ngoài khai báo không?
- Output text dùng encoding/line endings dự kiến không?
- Task có thật sự là producer của task tiêu thụ output không?
- Có smoke test kiểm nội dung file và failure cases không?
- Output có thể chứa secret không?

---

## 11. Kotlin DSL đối chiếu cho lab

Với dự án thích Kotlin DSL, tương đương ngữ nghĩa của Java17 lab:

### 11.1. settings.gradle.kts

~~~kotlin
rootProject.name = "gradle-review-lab"
include("lib", "app")
~~~

### 11.2. build.gradle.kts root

~~~kotlin
plugins {
    base
}

tasks.register("reviewAll") {
    group = "verification"
    description = "Run checks and create the application distribution"

    dependsOn(
        ":lib:check",
        ":app:check",
        ":app:distZip"
    )
}
~~~

### 11.3. lib/build.gradle.kts

~~~kotlin
plugins {
    `java-library`
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
    options.encoding = "UTF-8"
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
    reports {
        junitXml.required.set(true)
        html.required.set(true)
    }
}
~~~

### 11.4. app/build.gradle.kts

~~~kotlin
plugins {
    application
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
    options.encoding = "UTF-8"
}

dependencies {
    implementation(project(":lib"))
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

application {
    mainClass = "lab.app.ReviewApp"
}

tasks.named<Test>("test") {
    useJUnitPlatform()
    reports {
        junitXml.required.set(true)
        html.required.set(true)
    }
}
~~~

Java source/test classes **không đổi**. Groovy và Kotlin DSL là hai cách diễn tả một Gradle model; không đặt cả hai script cùng tên base trong một project với nội dung mâu thuẫn. Kotlin DSL không có nghĩa dự án phải viết Java code thành Kotlin.

### 11.5. Review Kotlin DSL cần chú ý

- Plugins phải được apply đúng project trước khi gọi type-safe accessors.
- Kotlin DSL `Property<T>` assignment/set khác Groovy syntax.
- Không gọi `.get()` quá sớm trên Provider trong configuration phase.
- Không dùng `afterEvaluate` chỉ để bắt lỗi plugin apply order.
- Kiểm plugin/version compatibility và IDE sync.

---

## 12. CI quality gate: test trước package, release có bảo vệ

Một pipeline đơn giản có các giai đoạn:

~~~text
Checkout exact commit + Wrapper/JDK
               |
               v
          Compile/Test/Check
               |
          +----+----+
          |         |
         FAIL      PASS
          |         |
      Stop + XML    v
                  Package
                    |
                    v
              Artifact audit
                    |
                    v
          Protected release (optional)
~~~

### 12.1. GitLab fragment cho lab

~~~yaml
image: eclipse-temurin:17-jdk

stages:
  - verify
  - package

unit_verify:
  stage: verify
  script:
    - chmod +x ./gradlew
    - ./gradlew --no-daemon --console=plain :lib:check :app:check
  artifacts:
    when: always
    reports:
      junit:
        - lib/build/test-results/test/TEST-*.xml
        - app/build/test-results/test/TEST-*.xml

package_zip:
  stage: package
  script:
    - chmod +x ./gradlew
    - ./gradlew --no-daemon --console=plain :app:distZip
  artifacts:
    paths:
      - app/build/distributions/*.zip
~~~

Với GitLab Docker runner có container image hỗ trợ, đây là **pipeline ví dụ cho lab**. Wrapper phải có trong repo, CI có network đến Maven Central/mirror, JDK/toolchain tương thích. Package stage chỉ chạy sau verify pass theo semantics mặc định, không dùng `allow_failure: true` cho verify job. GitLab jobs thường có workspace riêng; package tự build outputs từ đúng source commit thay vì đọc `.jar` local từ verify job.

### 12.2. Jenkins Declarative fragment

~~~groovy
pipeline {
    agent { label 'jdk17-linux' }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Verify') {
            steps {
                sh 'chmod +x ./gradlew'
                sh './gradlew --no-daemon :lib:check :app:check'
            }
        }

        stage('Package') {
            steps {
                sh './gradlew --no-daemon :app:distZip'
            }
        }
    }

    post {
        always {
            junit(
                testResults: 'lib/build/test-results/test/TEST-*.xml,app/build/test-results/test/TEST-*.xml',
                allowEmptyResults: true
            )
        }

        success {
            archiveArtifacts(
                artifacts: 'app/build/distributions/*.zip',
                allowEmptyArchive: false
            )
        }
    }
}
~~~

Agent phải có JDK17, git, shell, Jenkins Pipeline/JUnit plugins và SCM context. `allowEmptyResults: true` chỉ giúp không đè lỗi compile sớm bằng report lỗi, **không chứng minh có tests**; khi require report bắt buộc, thêm guard/adjust policy. Không đưa publishing credentials vào PR verification job.

### 12.3. Negative CI gate

Thực hiện thay assertion thành sai ở branch thử nghiệm. CI phải:
1. Mark verify job/stage FAILED.
2. Lưu JUnit XML nếu Test task đã sinh.
3. Không chạy release.
4. Không công bố ZIP như successful release artifact.
5. Khi hoàn nguyên test, CI phải PASS trở lại.

Nếu package job vẫn chạy khi verify fail, kiểm `allow_failure`, `catchError`, `returnStatus`, `|| true`, `when: always`, stage graph và `needs` semantics. Đừng chỉ sửa màu CI thành xanh bằng cách bỏ tests.

---

## 13. Cách lập phiếu review có thể tái sử dụng

Một phiếu review hiệu quả cần đủ **bằng chứng**, nhưng không biến mọi PR nhỏ thành audit nhiều ngày.

### 13.1. Mẫu điền tay

~~~markdown
# Gradle Build Review — <change/PR>

## Scope
- Commit SHA:
- Modules / build scripts changed:
- Reviewer / date:
- Gradle Wrapper version:
- JDK / OS / CI agent:
- Relevant CI pipeline link:

## Evidence
- Clean verification command and result:
- Number of expected/observed tests:
- Artifact path/hash and smoke test:
- Dependency graph/lockfile impact:
- Build baseline before/after:
- Security scan and secrets/artifact checks:

## Findings
| ID | Status | Severity | Evidence | Recommended fix | Owner |
| --- | --- | --- | --- | --- | --- |
| COR-xx | PASS/FAIL/UNVERIFIED/N/A | P0/P1/P2/P3 | ... | ... | ... |
| MNT-xx | ... | ... | ... | ... | ... |
| PERF-xx | ... | ... | ... | ... | ... |
| SEC-xx | ... | ... | ... | ... | ... |

## Decision
- APPROVE / REQUEST CHANGES / UNVERIFIED
- Blocking issues:
- Accepted N/A reasons:
- Follow-up issue links:
- Retest evidence:
~~~

`<change/PR>` và `...` là **fields trong biểu mẫu minh họa cho reviewer điền**, không phải placeholder trong nội dung dự án. Khi dùng thật hãy thay bằng thông tin có thật và tránh ghi raw credentials vào phiếu.

### 13.2. Mẫu kết luận tốt

~~~text
Decision: REQUEST CHANGES
COR-11 (P1): :lib:test chạy NO-SOURCE dù PR thay đổi build/test setup.
Evidence: CI log tại job verify, chưa có JUnit XML.
Fix: Khôi phục test source set/JUnit Platform, yêu cầu test count tối thiểu.
Retest: JUnit report có các test cases mong đợi và negative test làm job fail.
Follow-up PERF-06 (P3): Đo hiệu quả Build Cache trong một issue riêng.
~~~

Điểm quan trọng là một finding có **actionable fix**, không chỉ nhận xét cảm tính.

### 13.3. Khi nào phải yêu cầu chuyên gia?

Escalate sang người chịu trách nhiệm Gradle build/security khi:
- Wrapper JAR/distribution source bị thay bất thường.
- Credentials hoặc signing keys có khả năng lộ.
- Dependency verification fail không rõ lý do.
- Gradle plugin từ source không tin cậy được thêm vào build.
- Release artifact có binary hash bất thường.
- Configuration Cache báo vi phạm liên quan captured credential.
- Một build tối ưu thời gian bằng cách bỏ validations/tests.
- CI trusted/untrusted jobs dùng chung writable remote build cache.

Không tự sửa một security finding bằng cách tắt scanner hoặc verification.

---

## 14. Bài tập thực hành và đáp án

### Bài 1 — Build báo xanh nhưng Test task `NO-SOURCE`. Đánh giá?

**Đáp án:** Chưa đủ evidence về tests. Xác định test source sets, JUnit setup, test filters và CI tests count; không đánh PASS.

### Bài 2 — Chỉ thay Gradle Wrapper distribution URL mà không sửa source?

**Đáp án:** Vẫn là review quan trọng về correctness và security; xác minh nguồn, version, checksum và compatibility.

### Bài 3 — `implementation files('../lib/build/libs/lib.jar')` có ổn?

**Đáp án:** Có nguy cơ stale/missing jar và thiếu project dependency metadata; dùng `implementation project(':lib')` cho multi-project.

### Bài 4 — `mustRunAfter` có bảo đảm producer chạy?

**Đáp án:** Không. Nó chỉ ràng thứ tự khi tasks đã được chọn; dùng `dependsOn`/Provider wiring khi consumer cần output.

### Bài 5 — `--dry-run` đã PASS thì có cần test thật?

**Đáp án:** Có. Dry-run không chạy task actions, không kiểm bytecode/tests/artifacts.

### Bài 6 — Cùng catalog version có nghĩa cùng resolved version?

**Đáp án:** Không. Xem `dependencyInsight`, constraints/platforms và locking.

### Bài 7 — `1.+` phù hợp release reproducibility không?

**Đáp án:** Không nếu không có lock/governance phù hợp; dynamic version có thể đổi theo thời gian.

### Bài 8 — Dependency locking có bảo vệ changing artifact cùng coordinate?

**Đáp án:** Không hoàn toàn; cần checksum/verification/repository controls và hạn chế changing versions.

### Bài 9 — Quét source Git đủ để bảo đảm JAR sạch secret?

**Đáp án:** Không. Generated resources/class constants/test reports/ZIP outputs có thể rò.

### Bài 10 — Signature `.asc` là private signing key?

**Đáp án:** Signature không phải private key, nhưng extension giống nhau có thể chứa armored key; kiểm nội dung.

### Bài 11 — GitLab package job có tự thấy JAR từ verify job?

**Đáp án:** Không được giả định. Jobs có thể chạy ở runners riêng; dùng artifacts/needs khi bắt buộc truyền chính bytes.

### Bài 12 — `allow_failure: true` cho unit tests ở CI?

**Đáp án:** Không cho required quality gate; nó có thể tạo false-green pipeline.

### Bài 13 — “Build nhanh hơn” vì bỏ `test` khỏi task graph?

**Đáp án:** Đây là correctness regression chứ không phải performance improvement.

### Bài 14 — Build Cache và Configuration Cache khác?

**Đáp án:** Build Cache lưu task outputs; Configuration Cache lưu configured task graph để bỏ configuration khi hit.

### Bài 15 — `UP-TO-DATE` và `FROM-CACHE` giống nhau?

**Đáp án:** Không; một cái dùng outputs hiện có, một cái restore cached outputs.

### Bài 16 — Cold build và warm build so được trực tiếp như hai phiên bản?

**Đáp án:** Không nếu điều kiện không được kiểm soát. Cần cùng cache state/hardware/JDK/commit/task graph và repetitions.

### Bài 17 — Vì sao tránh network I/O ở configuration phase?

**Đáp án:** Nó làm ngay cả lệnh help cần network, tăng config time và có thể phá Configuration Cache.

### Bài 18 — Task `@CacheableTask` không khai input đúng thì sao?

**Đáp án:** Có nguy cơ cache invalidation sai, trả output stale. Annotation không cứu được task model sai.

### Bài 19 — Root `allprojects { apply plugin: 'java' }` tốt với Android + Java platform?

**Đáp án:** Thường không; ép plugin không phù hợp, tăng coupling. Dùng per-module conventions.

### Bài 20 — Kotlin DSL có nghĩa phải apply Kotlin JVM plugin?

**Đáp án:** Không. Kotlin DSL là cách viết build scripts, Kotlin plugin là build integration cho source Kotlin.

### Bài 21 — Test JUnit 5 của lab dùng setting nào?

**Đáp án:** `useJUnitPlatform()`, thêm Jupiter dependency và platform launcher.

### Bài 22 — Lab có bao nhiêu tests?

**Đáp án:** 4 methods: 3 lib, 1 app, khi test sources và JUnit dependencies được resolve đúng.

### Bài 23 — Lab `:app:run` in stdout gì?

**Đáp án:** `REVIEW_OK: 12`.

### Bài 24 — `:app:distZip` tạo loại artifact nào?

**Đáp án:** Application distribution ZIP có scripts và các runtime libs cần thiết theo plugin conventions.

### Bài 25 — `:app:check` có luôn tạo distZip không?

**Đáp án:** Không. Check là verification lifecycle, distZip thuộc distribution packaging; CI nên gọi rõ khi cần ZIP.

### Bài 26 — `reviewAll.dependsOn(check, distZip)` có buộc package sau test?

**Đáp án:** Không bảo đảm ordering giữa các dependency tasks độc lập. CI stage gate hoặc task graph dependency rõ cần được định nghĩa.

### Bài 27 — Khi nào đánh `UNVERIFIED`?

**Đáp án:** Khi thiếu evidence (runner, JDK, logs, tests, artifact). Ghi điều còn thiếu và bước tiếp theo.

### Bài 28 — Một finding P0 nhưng mọi mục khác PASS có approve được?

**Đáp án:** Không. P0 security/correctness cần xử lý trước.

### Bài 29 — Credential trong `gradle.properties` ở Git có chấp nhận?

**Đáp án:** Không. Chuyển secret ra secret manager/user home có ACL phù hợp, rotate nếu đã lộ.

### Bài 30 — CI remote cache writable cho fork PR?

**Đáp án:** Không nên. Có nguy cơ cache poisoning/contamination; hạn chế trusted writers.

### Bài 31 — `--offline` nên dùng mặc định mọi CI?

**Đáp án:** Không. Fresh runner không có dependencies sẽ fail; dùng khi repository cache được chuẩn bị theo policy.

### Bài 32 — Build artifact hash khác giữa Windows và Linux chứng minh lỗi?

**Đáp án:** Chưa chắc; cần kiểm archive normalization, encoding, timestamps, permissions, JDK/toolchain và dependency resolution.

### Bài 33 — Task không có inputs/outputs nhưng chạy được có pass performance review?

**Đáp án:** Tùy workload; với task build output quan trọng, nên khai inputs/outputs để incremental/cache đúng; kiểm side effects.

### Bài 34 — `--profile` cho biết chính xác mọi CI wall time?

**Đáp án:** Không; nó tập trung vào Gradle phases/tasks, CI job còn queue/image/checkout/upload overhead.

### Bài 35 — `tasks.named('compileJava')` ở root chưa apply Java plugin?

**Đáp án:** Có thể fail vì task chưa được đăng ký trong Project đó; xác định plugin scope và dùng callbacks khi cần.

### Bài 36 — Khi custom plugin dùng network/secret phải review gì?

**Đáp án:** Trust source, plugin version, inputs/outputs, credentials scoping, logging, Configuration Cache, CI access.

### Bài 37 — JUnit XML tồn tại nhưng bằng không testcase?

**Đáp án:** Chưa chứng minh tests mong đợi chạy; cần expected test count/IDs, framework discovery và CI guard.

### Bài 38 — Vì sao tách CI verify và release?

**Đáp án:** Verify chạy untrusted code không nên có release credentials; release chỉ chạy trên protected refs/approved artifacts.

### Bài 39 — Review comment nào tốt hơn?

**Đáp án:** Finding có task path, evidence, severity, impact, fix và retest; không chỉ “code chưa đẹp”.

### Bài 40 — Tối ưu thời gian nhiều nhưng sửa output không kiểm chứng?

**Đáp án:** Không approve; correctness/security phải được xác minh trước performance.

---

## 15. Checklist cuối cùng cho buổi review

### Tính đúng

- [ ] Gradle Wrapper được commit, trusted, pin version/checksum theo policy?
- [ ] JDK runtime/toolchain tương thích và Java target được khai báo?
- [ ] Settings/includes và project paths đúng?
- [ ] `check` chạy đủ tests và test counts/IDs đã được xem?
- [ ] CI không bỏ qua test failure hoặc phát hành khi fail?
- [ ] Dependency graph thực tế đúng, không chỉ declared versions?
- [ ] Project dependencies thay vì JAR paths thủ công?
- [ ] Task dependencies, inputs/outputs và lifecycle wiring rõ?
- [ ] Binary artifact/JAR/ZIP hoạt động sau clean checkout?
- [ ] Positive/negative regression tests có kết quả thực?

### Khả năng bảo trì

- [ ] Core/external plugins phù hợp từng Project?
- [ ] Build logic dùng conventions khi thực sự giúp giảm duplication?
- [ ] Không ép mọi project dùng cùng plugin qua allprojects vô cớ?
- [ ] Version catalog/lock/verification files được quản lý tập trung?
- [ ] Custom task APIs, names, group/description rõ?
- [ ] Không hardcode absolute paths hoặc OS-specific shell khi không cần?
- [ ] Dùng TaskProvider/Providers và configuration avoidance?
- [ ] Có test cho reusable plugin/build logic?
- [ ] Docs/CI dùng một Gradle task contract nhất quán?

### Hiệu năng

- [ ] Có before/after baseline và cache state rõ?
- [ ] Đã tách startup/configuration/execution/job overhead?
- [ ] Không làm network/filesystem I/O nặng ở configuration?
- [ ] Incremental task inputs/outputs có đúng?
- [ ] Build Cache/Configuration Cache được thử đúng phạm vi?
- [ ] Không áp `clean`/`--rerun-tasks` mọi job vô căn cứ?
- [ ] CPU/RAM, daemon, parallelism có đo trước khi chỉnh?
- [ ] Tối ưu không giảm test coverage hoặc artifact correctness?

### An toàn

- [ ] Wrapper JAR/distribution và plugins từ nguồn tin cậy?
- [ ] Repositories, versions, lock/checksums theo governance?
- [ ] Không có production secrets trong Git/resources/artifacts/logs?
- [ ] Build scripts/third-party plugins được coi là executable code?
- [ ] Gradle User Home/init scripts/daemon không share qua trust domains?
- [ ] Remote Build Cache writers có quyền phù hợp?
- [ ] Untrusted PR không có publishing/signing credentials?
- [ ] Maven publishing và signing được bảo vệ bằng approvals?
- [ ] Actual JAR/ZIP/POM/reports được scan trước upload?
- [ ] Có cơ chế revoke/rotate và incident response?

### Chốt kết quả

- [ ] Mỗi PASS đều có bằng chứng kiểm?
- [ ] Mỗi FAIL có severity, impact, owner và fix?
- [ ] Mỗi UNVERIFIED nêu lý do và bước kiểm tiếp?
- [ ] N/A có lý do, không dùng để giấu blocker?
- [ ] Không còn P0/P1 trước quyết định merge/release?
- [ ] Follow-ups P2/P3 có tracker và deadline theo policy?
- [ ] Reviewer có thể tái hiện bằng commands/commit/runner đã ghi?

---

## Tài liệu chính thức

- [Gradle — Best Practices for Authoring Builds](https://docs.gradle.org/current/userguide/best_practices.html): index và nguyên tắc review có thể áp dụng.
- [Gradle — Best Practices for Performance](https://docs.gradle.org/current/userguide/best_practices_performance.html): configuration avoidance, UTF-8, caches.
- [Gradle — Improve Performance](https://docs.gradle.org/current/userguide/performance.html): baseline, cache, compile, task execution.
- [Gradle — Best Practices for Dependencies](https://docs.gradle.org/current/userguide/best_practices_dependencies.html): catalogs, repos, conflicts.
- [Gradle — Best Practices for Structuring Builds](https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html): convention plugins và build-logic.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): khi nào reuse task graph, compatibility requirements.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): task output caching.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): lock resolved versions.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksums/signatures.
- [Gradle — Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html): Wrapper, Gradle User Home, plugin trust/caches.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): register/named/configureEach.
- [Gradle — Task Inputs and Outputs](https://docs.gradle.org/current/userguide/incremental_build.html): up-to-date/build cache correctness.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): api/implementation.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): application distributions.
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): Test task và reports.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): pin/verify distribution.

**Kết luận:** Một Gradle build đáng tin cậy phải **đúng**, **dễ bảo trì**, **có hiệu năng được đo**, và **an toàn ở mọi trust boundary**. Review không dừng ở build script nhìn gọn hoặc CI xanh; phải thu chứng cứ về task graph, resolved dependencies, tests, artifacts, cache behavior và credentials. Hãy dùng severity và bằng chứng để quyết định merge/release: **correctness và security là điều kiện trước, performance chỉ có ý nghĩa khi kết quả build vẫn đúng**.
