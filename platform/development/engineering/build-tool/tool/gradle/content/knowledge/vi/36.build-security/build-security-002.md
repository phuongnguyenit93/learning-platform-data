# Ranh giới tin cậy của pull request, plugin và repository bên ngoài trong Gradle

## 1. Build thành công chưa chứng minh build đáng tin

Trong một dự án Java dùng Gradle, lệnh `./gradlew test`, `./gradlew build` hoặc `./gradlew publish` có thể thực thi mã từ **Gradle Wrapper**, `settings.gradle.kts`, `build.gradle.kts`, plugin implementation, `buildSrc`, included `build-logic`, Java annotation processor, custom code generator, scripts shell, test code và external tools. Một pull request (PR) chưa được review có thể thay đổi nhiều trong số đó.

**Ranh giới tin cậy (trust boundary)** là nơi dữ liệu hoặc mã từ nguồn ít đáng tin đi vào môi trường có nhiều quyền hơn. Ba ranh giới cần thiết kế rõ:

1. **PR → CI runner:** tác giả PR có thể sửa code và build scripts; runner không được cung cấp signing keys, publish token hoặc quyền cloud không cần thiết.
2. **Plugin/Wrapper → Gradle process:** plugin và Wrapper là executable code; version pin, kiểm tra checksum, review nguồn và isolation là các biện pháp bổ sung lẫn nhau.
3. **Repository → dependency graph:** metadata, JAR, transitive dependency hoặc plugin artifact đến từ repository phải được giới hạn nguồn, verify integrity/provenance và đánh giá lỗ hổng.

Mục tiêu của bài: biết **ai có quyền thay đổi một đầu vào**, **mã nào sẽ được thực thi**, **quyền nào mã đó nhận**, cách giữ untrusted PR ở môi trường ít đặc quyền và cách chỉ dùng approved artifacts trong release. Không có một cờ Gradle duy nhất thay thế authorization, code review hoặc runner sandbox.

## 2. Mô hình đe dọa: dữ liệu từ đâu và đi qua đâu?

~~~text
External contributor / unreviewed PR
               |
               v
Java sources + settings/build scripts + Wrapper + workflow + catalog
               |
               v
     Isolated, low-privilege PR CI
               |
               +--> Gradle Wrapper (runs before build logic)
               +--> settings & plugin resolution
               +--> compilation, tests, codegen
               +--> external repositories and cache
               |
               v
      Test reports / generated JARs
             (UNTRUSTED)
               |
               | Must not silently cross trust boundary
               v
Protected branch + reviews + required checks
               |
               v
Trusted release build on protected ref
               |
               v
Sign / publish / deploy with scoped credentials
~~~

| Bề mặt | Người có thể tác động | Điều có thể bị ảnh hưởng | Kiểm soát |
| --- | --- | --- | --- |
| PR sửa Java source/tests | PR author | Test execution, app behavior | Ephemeral CI, không secrets |
| PR sửa `build.gradle.kts` | PR author | Arbitrary build-time execution | Code review, sandbox, token tối thiểu |
| PR sửa `settings.gradle.kts` | PR author | Plugin & repository policy | Trusted CI constraints ngoài PR |
| PR sửa Wrapper JAR/script | PR author | Mã chạy trước Gradle | Official checksum validation |
| PR sửa version catalog/locks | PR author | Dependency versions | Lock/verification diff review |
| PR sửa `verification-metadata.xml` | PR author | Trust anchors/hashes | Independent artifact/hash verification |
| Third-party plugin | Publisher hoặc repo bị compromise | Gradle process, host secrets | Pin, verify, allowlist sources |
| Maven package từ external repo | Publisher/upstream/repo | Compile/runtime code | Content filtering, integrity, scanning |
| Internal group trên public registry | Attacker | Dependency confusion | `exclusiveContent` |
| PR-built artifact | Untrusted build process | Release supply chain | Rebuild protected ref |
| Shared remote build cache | Cache write principal | Trusted task outputs | Cache trust partition, write ACL |
| Persistent runner | PR code | Credentials/files/docker/cloud metadata | Isolated runner, no privileged mounts |
| Privileged workflow trigger | Workflow context | `GITHUB_TOKEN`/OIDC | Permission minimization & ref controls |

Cần phân biệt **integrity** (bytes đúng expected checksum), **provenance** (ai ký/tạo artifact), **vulnerability status** (có CVE đã biết), và **authorization** (mã được phép chạy ở đâu). Không thuật ngữ nào thay thế hoàn toàn thuật ngữ khác.

## 3. Những file PR có thể dùng để thực thi mã build

Không chỉ `src/main/java`:

- `gradlew`/`gradlew.bat`: shell/batch scripts.
- `gradle/wrapper/gradle-wrapper.jar`: Java executable.
- `gradle/wrapper/gradle-wrapper.properties`: distribution URL/version/checksum.
- `settings.gradle(.kts)`: settings plugins, plugin management, repository resolution.
- `build.gradle(.kts)` root/subproject: plugin application, task configuration/actions.
- `buildSrc/**`, `build-logic/**` và composite/included builds.
- `gradle/libs.versions.toml`: plugin/dependency aliases và requested versions.
- `gradle/verification-metadata.xml`: checksum/signature trust metadata.
- `gradle.lockfile` hoặc files dependency constraints.
- `.github/workflows/**`, shell scripts, Dockerfiles, CI action definitions.
- Tests, annotation processors, generated scripts và task inputs đã được execute.

Nếu một PR “chỉ thay dependency version” nhưng nâng plugin có quyền đọc environment, rủi ro xảy ra **ngay trong quá trình build**, không phải chỉ khi chạy production app.

### 3.1. `./gradlew help` không phải chế độ kiểm tra an toàn

Dù task `help` không compile source, Gradle vẫn chạy Wrapper, xử lý initialization/settings, resolve/apply plugins và configure build theo nhu cầu. Một build script độc hại có thể làm việc trong configuration phase. IDE import/Gradle sync cũng có thể kích hoạt build logic. Vì vậy đừng chạy checkout lạ trên laptop có cloud credentials rồi nghĩ `help` chỉ đọc metadata.

### 3.2. PR pass tests không có nghĩa PR không độc hại

Unit tests chỉ kiểm tra assertions đã viết. Chúng không chứng minh plugin không gửi network request, script không đọc secret hoặc generated JAR không bị chèn mã. Functional test và supply-chain review phải là các lớp kiểm tra riêng.

## 4. Ba mức tin cậy cho CI

| Mức | Nguồn | Quyền phù hợp |
| --- | --- | --- |
| **Untrusted PR** | Fork PR hoặc source/build code chưa review | Read-only repo token, ephemeral sandbox, không signing/publishing/deploy secrets |
| **Reviewed merge** | Commit đã qua code review và protected branch policy | Build, test, scan và chuẩn bị release |
| **Privileged release** | Approved protected ref/tag và deployment environment | Short-lived scoped publish/deploy credentials, signing, provenance |

Không có quy tắc “mọi PR đều như nhau”. Fork PR với trigger `pull_request` thường bị hạn chế secrets, nhưng PR từ branch cùng repository hoặc workflow trigger khác có thể có permission model khác. Hãy xét **trigger, checked-out ref, token scopes và runner environment**, không chỉ nhãn PR.

**Không tự nâng cấp quyền:** PR check xanh hoặc artifact được upload không phải giấy phép chạy nó trong release job có secrets.

## 5. GitHub Actions: pull_request khác pull_request_target

| Event | Context | Security consequence |
| --- | --- | --- |
| `pull_request` | Thường check out PR merge commit theo action mặc định; fork restrictions | Phù hợp chạy tests trên untrusted PR với quyền thấp |
| `pull_request_target` | Workflow thuộc base branch, có thể có quyền cao hơn | Không checkout/execute PR head trong privileged job |
| `workflow_run` | Bước sau một workflow khác | Artifacts từ PR upstream vẫn untrusted |
| `push` protected branch | Code đã merge | Có thể là đầu vào trusted release workflow |
| `workflow_dispatch` | Manual invocation | Phải kiểm người, ref, environment và token quyền gì |

GitHub Docs mô tả fork PR với `pull_request` thường có token read-only và không được đưa repository secrets theo mặc định, phụ thuộc repository/org policies. Nhưng một self-hosted runner có secrets ở file/env vẫn nguy hiểm; GitHub token restrictions không tự xóa secrets trên host.

### 5.1. Mẫu workflow kiểm tra PR có quyền tối thiểu

**File `.github/workflows/pr-check.yml`:**

~~~yaml
name: PR Java Gradle checks

on:
  pull_request:

permissions:
  contents: read

jobs:
  check:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - name: Checkout PR code
        uses: actions/checkout@v4
        with:
          persist-credentials: false

      - name: Use Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"

      - name: Prepare Gradle and validate Wrapper
        uses: gradle/actions/setup-gradle@v4
        with:
          cache-read-only: true

      - name: Run unprivileged tests
        run: ./gradlew --no-daemon test --stacktrace
~~~

**Phạm vi:** mẫu học tập thể hiện quyền thấp, không phải bằng chứng toàn bộ organization đã an toàn. `@v4` là version tag; CI production nên pin actions vào **reviewed immutable commit SHA** và cập nhật có kiểm soát. Không đưa một SHA bịa vào tài liệu.

Giải thích:

- `permissions: contents: read` thu hẹp `GITHUB_TOKEN`, không yêu cầu package write hoặc `id-token: write`.
- `persist-credentials: false` giảm credential persistence trong checkout Git config.
- Không cấp env/secrets để publish/deploy.
- Gradle setup action có hỗ trợ Wrapper validation; xác minh chính phiên bản/action được sử dụng.
- `cache-read-only: true` tránh job PR ghi setup-gradle cache trong mẫu này.
- Hosted ephemeral runner được ưu tiên hơn một long-lived privileged self-hosted runner.
- `timeout-minutes` giảm resource abuse nhưng không thay sandbox/egress policy.

**Vẫn còn rủi ro:** PR có thể sửa Java/build logic mà `./gradlew test` thực thi. Sandbox và least privilege hạn chế hậu quả nếu code đó có hành vi không mong muốn; chúng không biến code PR thành trusted code.

## 6. Vì sao pull_request_target + PR head là anti-pattern

`pull_request_target` chạy từ base context và có thể được trao quyền comment/label/write hoặc secrets. Nếu job này checkout PR head/merge commit rồi chạy `./gradlew build`, `npm install` hoặc shell script từ PR, nó vừa vượt qua trust boundary.

Một sơ đồ nguy hiểm:

~~~text
pull_request_target (base workflow, privileged token)
     |
     +--> checkout PR head (untrusted)
     |
     +--> execute ./gradlew (untrusted build logic)
     |
     +--> secrets/token exposed to code from PR
~~~

Không cần attacker sửa Java production source; chỉ cần thay settings/plugin/build script để tạo rủi ro.

**Khuyến nghị:** dùng `pull_request` cho PR compilation/tests. Chỉ dùng `pull_request_target` khi thật sự cần thao tác metadata của PR trong base context; không download/execute PR code. PR title, branch name, body và labels vẫn là untrusted strings; không đưa chúng vào shell code mà thiếu safe quoting/validation.

### 6.1. Không ngộ nhận workflow file từ base có nghĩa “an toàn”

Workflow có thể vẫn chạy PR-controlled shell scripts, Gradle plugin, jar, test binary hay artifact. Ranh giới nằm ở **thứ thực sự được thực thi và quyền process**, không chỉ ở file YAML được đọc từ branch nào.

## 7. workflow_run và artifacts chưa được tin cậy

Workflow downstream có thể chạy sau khi PR workflow kết thúc. Nếu downstream có privileges cao, nó **không được execute artifact/script** tải từ untrusted PR run.

Ví dụ:

~~~text
Untrusted pull_request job:
    builds report.zip
         |
         v
Privileged workflow_run:
    downloads report.zip
    parses trusted?  <-- SAI nếu coi nội dung tự động trusted
    executes script  <-- RỦI RO
~~~

Nếu cần tạo comment tổng kết PR, có thể lấy **data-only report** rồi parse an toàn, validate schema/run ID/size/content type, chống path traversal khi unzip, không chạy shell từ archive và không nhận filename/metadata PR làm command.

**Release:** checkout protected commit/tag đã review và **rebuild artifact** trong trusted release context thay vì lấy PR JAR rồi ký/phát hành trực tiếp.

## 8. Gradle Wrapper là mã thực thi trước các biện pháp bên trong build

Wrapper gồm:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
~~~

- Scripts `gradlew`/`gradlew.bat` chạy ngay khi gọi.
- JAR Wrapper chạy trước `settings.gradle.kts`.
- `distributionUrl` chỉ định distribution tải nếu cần.
- `distributionSha256Sum` dùng để kiểm đúng bytes distribution ZIP tải về.

Ba việc cần kiểm độc lập:

1. **Wrapper JAR** có SHA-256 thuộc bộ official Gradle releases?
2. **Scripts và distribution URL** có khớp version/mirror HTTPS được duyệt?
3. **Distribution checksum** có từ nguồn official độc lập và khớp ZIP đúng version?

### 8.1. Kiểm tra JAR mà không thực thi nó

Linux:

~~~bash
sha256sum gradle/wrapper/gradle-wrapper.jar
~~~

macOS:

~~~bash
shasum -a 256 gradle/wrapper/gradle-wrapper.jar
~~~

Windows PowerShell:

~~~powershell
(Get-FileHash gradle\wrapper\gradle-wrapper.jar -Algorithm SHA256).Hash.ToLower()
~~~

Đối chiếu hash với <https://gradle.org/release-checksums/> **độc lập với PR**. Không coi “file checksum do chính PR thêm” là trusted source; người sửa JAR có thể thay cả hash trong PR.

### 8.2. distributionSha256Sum phải là SHA thực từ official release

Trong `gradle/wrapper/gradle-wrapper.properties`, cấu hình `distributionSha256Sum` bằng đủ **64 ký tự hex SHA-256** chính thức của đúng distribution ZIP (chú ý khác nhau giữa binary và all ZIP). Không tự đo artifact nghi bị thay rồi dùng hash đo được như nguồn chân lý.

Theo Gradle Wrapper docs, verification được thực hiện khi distribution cần **download**; nếu cached distribution đã tồn tại, không nên suy nó được re-verify mỗi lần. Kiểm soát quyền ghi cache/GRADLE_USER_HOME và dùng runner fresh khi cần.

### 8.3. Đừng dùng Wrapper chưa verify để “tự regenerate”

Lệnh `./gradlew wrapper` đã thực thi script/JAR của checkout. Đừng chạy nó trên checkout nghi bị compromise để sửa Wrapper. Sử dụng trusted CI wrapper-validation action hoặc independent checksum tool trước, rồi mới dùng trusted Gradle để regenerate nếu cần.

## 9. Plugin và build logic: thực thi từ rất nhiều nguồn

| Nguồn | Điểm thực thi |
| --- | --- |
| `settings.gradle.kts`, settings plugins | Initialization/settings evaluation |
| Root/subproject `build.gradle.kts` | Build configuration và task actions |
| External Gradle plugin | Khi được apply, khi task action chạy |
| `buildSrc` | Build logic được compile/load vào build |
| Included `build-logic`, convention plugins | Plugin build và implementation code |
| Init scripts | Global/user/CI initialization hook |
| Annotation processor | Java compilation |
| Test engine/tests | Gradle Test process |
| Custom `JavaExec`/`Exec`/code generator | External JVM/process/tool |
| Gradle Wrapper | Trước project build logic |

Vì vậy một PR sửa plugin version/catalog/buildSrc có thể đưa mã chạy trên CI dù không có một thay đổi nào ở `src/main/java`.

### 9.1. Plugin version pin chỉ là một lớp

Plugin declaration như sau **là ví dụ notation, không phải plugin thật để cài**:

~~~kotlin
plugins {
    id("com.example.audit") version "2.3.0"
}
~~~

Pin `2.3.0` làm resolution ổn định hơn dynamic version, nhưng không chứng minh publisher đáng tin hoặc JAR không bị tráo. Cần trusted plugin repositories, dependency verification và review permission của plugin.

### 9.2. Plugin repository khác dependency repository

`plugins { id(...) version(...) }` thường resolve qua `pluginManagement.repositories` và plugin marker artifacts. Library JARs trong `dependencies { ... }` resolve qua `dependencyResolutionManagement.repositories` hoặc project repositories theo policy. **Harden cả hai.** Không nghĩ có `mavenCentral()` là mọi plugin đều đã được quản lý an toàn.

## 10. Review PR thay đổi plugin, script và workflow

Checklist review tập trung:

1. Xem mọi file khác ở `gradlew`, Wrapper JAR, `settings`, build scripts, `buildSrc`, `build-logic`, version catalogs, verification metadata, lockfiles và workflow YAML.
2. Xác định plugin publisher/group/id/version, repo serving metadata/JAR.
3. Kiểm tra có `Exec`, `ProcessBuilder`, remote scripts, dynamic version hoặc bất ngờ thêm Maven repository không.
4. Kiểm tra internal group không bị hỏi public registry.
5. Kiểm tra thay đổi keys/hashes của dependency verification có evidence độc lập.
6. Xem CI permissions, `pull_request_target`, `workflow_run` và checkout ref.
7. Xem đường PR artifacts đi vào trusted workflows.
8. Kiểm tra remote cache write credentials, secrets trong env/Gradle user home.
9. Chạy build trong unprivileged runner, không tự dùng laptop có production credentials.
10. Với thay đổi security-sensitive, yêu cầu CODEOWNERS hoặc reviewer chuyên trách và cập nhật policy sau merge.

PR “chỉ sửa dependency” có thể được tự động tạo bởi bot, nhưng bot identity không làm plugin hoặc artifact ngoài tự thành trusted.

## 11. External repositories: repository nào được phép phục vụ artifact nào?

Một Maven repository có thể trả về JAR, POM, Gradle Module Metadata hoặc transitive dependencies. Plugin repository có thể trả plugin marker và implementation binary. Mỗi URL là một **quyết định tin cậy**.

Hai rủi ro tiêu biểu:

- **Dependency confusion:** một internal module (group/name) bị attacker publish lên public registry; Gradle resolve từ nguồn không mong đợi.
- **Compromised upstream/mirror:** một artifact ở cùng coordinates bị tráo hoặc publisher bị compromise.

Chỉ xếp internal repo lên đầu danh sách đôi khi không đủ để bảo đảm internal modules **không bao giờ** được hỏi từ public. Dùng repository content filtering hoặc `exclusiveContent` theo group.

### 11.1. HTTPS là điều kiện cần, không phải chứng minh publisher

Từ chối HTTP repositories hoặc `isAllowInsecureProtocol = true` trừ tình huống có security exception được kiểm soát; ưu tiên HTTPS proxy/mirror. TLS giảm nguy cơ can thiệp trên đường truyền nhưng không chứng minh artifact tương ứng thuộc release đã review.

## 12. Tập trung cấu hình repositories trong settings

Một base settings Kotlin DSL dùng được cho dự án demo:

**`settings.gradle.kts`:**

~~~kotlin
import org.gradle.api.initialization.resolve.RepositoriesMode

pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = "secure-gradle-lab"
~~~

- `pluginManagement.repositories` dùng cho plugin resolution.
- `dependencyResolutionManagement.repositories` dùng cho libraries.
- `FAIL_ON_PROJECT_REPOS` ngăn project/plugin tự thêm dependency repository ở project scope trái policy.
- Application/Java plugins thuộc Gradle core, không cần thêm arbitrary plugin repo.

**Giới hạn bảo mật:** Nếu attacker kiểm soát PR chỉnh `settings.gradle.kts`, họ cũng có thể xóa `FAIL_ON_PROJECT_REPOS` hoặc thêm repo. Cấu hình này là hygiene của repo đã review, **không là immutable defense** chống code PR. Các giới hạn CI/egress/runner cần ở hạ tầng ngoài untrusted checkout.

## 13. exclusiveContent cho internal group

Khi tổ chức sở hữu internal group `com.acme.internal`, không để public registry nhận yêu cầu cho group đó.

Một policy settings **minh họa**, chỉ dùng sau khi thay domain bằng repository nội bộ thật đã phê duyệt:

~~~kotlin
import org.gradle.api.credentials.PasswordCredentials
import org.gradle.api.initialization.resolve.RepositoriesMode

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)

    repositories {
        exclusiveContent {
            forRepository {
                maven {
                    name = "internal"
                    url = uri("https://repo.company.example/maven")
                    credentials(PasswordCredentials::class)
                }
            }

            filter {
                includeGroupAndSubgroups("com.acme.internal")
            }
        }

        mavenCentral()
    }
}
~~~

Đoạn này là **phương án thay thế** cho `dependencyResolutionManagement` mục 12, không paste thêm cùng lúc. `repo.company.example` là domain minh họa; không có server/credentials tương ứng sẽ không resolve. Ưu tiên read-only repository credentials được cấp từ environment/secret manager hoặc Gradle credential APIs.

**Khác biệt:**

- `content { includeGroup(...) }` ở riêng một repo hạn chế những gì repo đó được phép phục vụ.
- `exclusiveContent` còn loại các repositories khác khỏi việc serve coordinates khớp filter.
- `includeGroupAndSubgroups` bao gồm group gốc và những subgroups như `com.acme.internal.api`.

Policy này giảm dependency confusion và rò rỉ tên module nội bộ. Với plugin repositories có cơ chế tương tự nhưng ràng buộc riêng; `exclusiveContent` trong `pluginManagement` ảnh hưởng khả năng thêm repositories qua `buildscript`, cần đọc docs trước khi áp.

### 13.1. Mirror nội bộ chưa phải trust anchor

Mirror có thể cache cả artifacts compromised nếu không verify khi ingest. Hạn chế quyền publish, verify checksum/signature từ upstream independent source và audit mirror logs/ACL. Đừng tắt dependency verification chỉ vì URL của mirror là internal.

## 14. Dependency verification: checksum và chữ ký

Gradle hỗ trợ `gradle/verification-metadata.xml` để kiểm artifact từ dependency engine, bao gồm external libraries, metadata và plugins.

| Biện pháp | Trả lời câu hỏi | Chưa giải quyết |
| --- | --- | --- |
| SHA-256/SHA-512 checksum | Bytes có đúng fingerprint expected? | Ai là publisher đáng tin? |
| PGP signature | Artifact có được ký bằng trusted key? | Mã đó có lỗ hổng hay hành vi xấu? |
| Dependency locking | Resolved versions có đúng lock state? | Artifact bytes có bị tráo? |
| Vulnerability scanning | Có CVE đã biết không? | Có mã độc chưa biết? |
| Repository filtering | Module được lấy từ đúng nguồn? | Repo đó có tuyệt đối đáng tin? |
| Artifact provenance/attestation | Ai, workflow, source nào tạo? | Code có được review đủ chưa? |

**Checksum không phải xác thực danh tính.** Nếu chỉ ghi checksum của artifact bị attacker cung cấp, nó vẫn xác minh đúng bytes độc hại. Signature cũng chỉ hữu ích khi trusted key/publisher identity đã được kiểm tra.

### 14.1. Bootstrap verification metadata ở nguồn tin cậy

Sau khi kiểm tra source/repositories/versions, trên **trusted protected branch**:

~~~bash
./gradlew --write-verification-metadata sha256,pgp build
~~~

Gradle có thể sinh `gradle/verification-metadata.xml` gồm artifact fingerprints/keys được suy ra. Review kỹ:

- group:name:version và transitive dependencies;
- plugin JAR/markers;
- SHA-256 source/expected values;
- trusted và ignored PGP keys;
- modules chưa được resolve bởi task `build`;
- khác biệt với file metadata commit trước;
- nguồn repository và lý do cập nhật.

**Không chạy bootstrap rồi auto-accept kết quả PR.** Nếu dependency/repo đã bị compromise, lệnh bootstrap có thể lưu chính checksum của bytes độc hại. Cần kiểm nguồn độc lập cho artifacts quan trọng.

### 14.2. Khi verification fail

- Dừng build.
- Ghi lại artifact coordinates, repo source và expected/actual fingerprint.
- Kiểm tra official release, publisher, key và mirror/cache.
- Không tắt verification hoặc đổi checksum thành giá trị vừa thấy để “green”.
- Sau investigation và review mới cập nhật metadata.
- Nếu nghi runner/token đã bị lộ, chuyển sang incident response và rotate credentials.

### 14.3. Một ngoại lệ quan trọng trong composite build

Theo tài liệu Gradle, dependency verification của **current build invocation** có phạm vi global cho root, subprojects, `buildSrc` và included builds. Khi included build có file verification metadata riêng, file của current build được dùng cho composite invocation, thay vì mỗi included build tự áp một allowlist riêng.

Điều này **khác** với `settings`/catalog/repositories nói chung vốn do từng included build tự định nghĩa. Khi include thêm `build-logic`, phải cập nhật trusted verification metadata của build đang chạy. Đây là ngoại lệ không nên bỏ qua khi review ranh giới tin cậy.

### 14.4. Verification không phát hiện mọi CVE

Artifact đúng fingerprint vẫn có thể chứa lỗ hổng hoặc hành vi không mong muốn. Kết hợp software composition analysis (SCA), SBOM, vulnerability advisory monitoring, code review, license policy và update/release process.

## 15. Dependency locking giữ versions, không khóa bytes

Gradle hỗ trợ lock state cho resolvable configurations. Trong project cần áp dụng:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Trên trusted branch:

~~~bash
./gradlew dependencies --write-locks
~~~

Review files `gradle.lockfile` và commit có chủ đích. Trong multi-project build, lệnh `dependencies` thường chỉ áp trên project được chọn; cần bảo đảm tất cả configurations quan trọng được resolve/locked. Dynamic selectors như `1.+` hoặc `latest.release` làm giảm reproducibility; khuyến nghị exact versions cho release.

### 15.1. Version catalog không phải lockfile

`gradle/libs.versions.toml` khai báo **requested versions**, nhưng dependency conflict resolution/platform constraints có thể chọn bản khác. Lockfiles ghi resolved versions; verification metadata ghi fingerprints/keys. Ba phần phục vụ mục đích khác nhau.

## 16. Ví dụ Java 17 chạy được không cần external build plugin

Demo `secure-gradle-lab` gồm Java CLI và một JUnit test. Chỉ dùng built-in Application plugin, Maven Central cho JUnit, không có secret hay publishing config.

### 16.1. Cấu trúc

~~~text
secure-gradle-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/demo/SafeGreeting.java
    └── test/java/demo/SafeGreetingTest.java
~~~

Dùng `settings.gradle.kts` **ở mục 12**. Wrapper phải là official verified Wrapper phù hợp JDK/Gradle version; không tạo `gradlew` giả.

### 16.2. build.gradle.kts

~~~kotlin
plugins {
    application
}

group = "org.example.training"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.11.4")
}

tasks.test {
    useJUnitPlatform()
}

application {
    mainClass.set("demo.SafeGreeting")
}
~~~

Giải thích: Java toolchain 17, JUnit chỉ ở test classpath, no release tasks, repo policy tại settings. JUnit versions là pinned versions cho **ví dụ**, không khẳng định latest. Nếu đã bật dependency verification nghiêm ngặt, cần metadata hợp lệ cho JUnit và các transitive modules trước khi test.

### 16.3. src/main/java/demo/SafeGreeting.java

~~~java
package demo;

public final class SafeGreeting {
    private SafeGreeting() {
    }

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "Gradle" : args[0];
        System.out.println(greet(name));
    }
}
~~~

### 16.4. src/test/java/demo/SafeGreetingTest.java

~~~java
package demo;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class SafeGreetingTest {
    @Test
    void greetsAda() {
        assertEquals("Hello, Ada!", SafeGreeting.greet("Ada"));
    }

    @Test
    void greetsDefaultName() {
        assertEquals("Hello, Gradle!", SafeGreeting.greet("Gradle"));
    }
}
~~~

### 16.5. Chạy Gradle

Linux/macOS:

~~~bash
./gradlew test
./gradlew run --args="Ada" --quiet
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
.\gradlew.bat run --args="Ada" --quiet
~~~

**Stdout từ Java Main:**

~~~text
Hello, Ada!
~~~

Không truyền args: `./gradlew run --quiet` cho dòng:

~~~text
Hello, Gradle!
~~~

Gradle/JVM có thể có warnings/logs riêng. Hai dòng trên là kết quả của Java Main, không phải full Gradle console transcript.

### 16.6. Chạy trực tiếp Java 17 với javac/java

Linux/macOS:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
    -d out src/main/java/demo/SafeGreeting.java
java -cp out demo.SafeGreeting Ada
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out src\main\java\demo\SafeGreeting.java
java -cp out demo.SafeGreeting Ada
~~~

**Stdout chính xác:**

~~~text
Hello, Ada!
~~~

Lệnh `javac/java` chứng minh Java source hoạt động độc lập. Nó **không** tải JUnit, chạy Gradle plugins, kiểm Wrapper integrity hoặc xác minh CI permissions. Đừng lấy nó làm bằng chứng security controls đã PASS.

## 17. Phân biệt build-time code với runtime library

Một dependency `implementation("group:module:version")` có thể chỉ được load khi chương trình chạy; annotation processor, plugin hoặc test engine có thể **thực thi ngay lúc CI build**.

Ví dụ notation **minh họa, không có module có thật được bảo đảm**:

~~~kotlin
dependencies {
    annotationProcessor("com.example.tools:codegen:1.2.3")
}
~~~

Annotation processor chạy trong compiler context, nên phải review nguồn/publisher/versions/verification như plugin. Một test JAR có thể được load khi Test task chạy; không coi test-only dependencies là mặc định vô hại.

**Không dùng “compile thành công” làm bằng chứng processor/plugin không đọc env**. Process isolation, secrets availability và trusted source review là defense riêng.

## 18. PR artifacts và release artifacts thuộc hai mức tin cậy

Một PR có thể build ra JAR hợp lệ và upload lên CI. Tuy nhiên:

- PR author có thể sửa mã Java mà artifact chứa.
- PR author có thể sửa build logic/packaging.
- PR author có thể sửa CI upload script và metadata.
- Upload action không tự chứng minh source trust.
- Unit tests PASS chỉ kiểm tra logic do tests xác định.

**Thiết kế release hợp lý:**

1. PR CI ít quyền: compile/test/security scan.
2. Required code-owner/security reviews nếu build logic/Wrapper/dependencies thay đổi.
3. Merge vào protected branch.
4. Trusted release workflow checkout verified commit.
5. Build lại, verify dependencies/checksum, kiểm tests và SBOM/provenance.
6. Publish/sign với short-lived scoped credentials và approval policy.

Nếu cần bảo đảm artifact bit-for-bit tái lập, thiết kế reproducible build và compare digests có thể bổ sung, nhưng không thay authorization.

## 19. Remote Build Cache và Gradle User Home

Remote Build Cache có thể phục vụ task outputs cho nhiều builds. Nếu PR runner có write access vào cùng trusted cache mà release job đọc, xuất hiện nguy cơ **cache poisoning** hoặc rò rỉ credentials.

Chính sách nên là:

- PR job chỉ đọc approved cache hoặc dùng cache namespace riêng.
- Trusted cache write chỉ từ protected branch/identity.
- Remote cache write credentials không nằm trong untrusted job.
- Outputs không chứa secrets hoặc hidden runtime state.
- ACL/audit/integrity checks ở cache service.
- Cache keys/input modeling được review; cache hit không tự là security attestation.

`GRADLE_USER_HOME`/`~/.gradle` có cached JARs, init scripts, repository metadata, global properties và đôi khi credentials. Không cho untrusted PR dùng chung persistent Gradle User Home của privileged job trên self-hosted runner.

**`--offline` không phải chế độ an toàn:** Gradle vẫn có thể execute malicious plugins đã nằm trong local cache. Nó chỉ hạn chế dependency resolution network.

## 20. Secrets: đặt quyền ở đúng chỗ

Các nguồn secrets thường bị lộ:

- CI `env` và secret variables.
- Gradle User Home `gradle.properties`.
- Registry publishing credentials.
- Signing keys hoặc cloud auth files.
- SSH agent, Git credentials.
- Docker socket/instance metadata.
- Tokens trong CLI arguments/logs.
- Build scans hoặc generated artifacts.

Khuyến nghị:

1. PR job không có secrets publish/deploy/signing.
2. Dependency resolution chỉ dùng read-only credentials nếu cần.
3. Release credentials chỉ cấp ở privileged release workflow.
4. Dùng short-lived OIDC với cloud trust policy giới hạn ref/environment khi phù hợp.
5. Không commit password/API key vào build scripts, TOML hoặc source-controlled properties.
6. Không in secrets qua logger/println/`--debug` hoặc artifact report.
7. Không ghi secrets vào cacheable task outputs.
8. Giữ runner ephemeral hoặc sandbox/VM với minimal filesystem/network access.

### 20.1. Provider APIs không thay quyền truy cập

Trong Gradle Kotlin DSL, có thể dùng providers:

~~~kotlin
val repositoryUser =
    providers.environmentVariable("REPO_READ_USERNAME")
val repositoryPassword =
    providers.environmentVariable("REPO_READ_PASSWORD")
~~~

Đây là **đoạn minh họa tạo Providers**; cần nối vào credential configuration hợp lệ khi dùng thực tế. Không in `repositoryPassword.get()`. Provider giúp lookup/configuration rõ hơn, nhưng nếu PR code thực thi trong process có env secret, nó **vẫn có thể đọc được secret**. Quyền thấp ở CI là lớp bảo vệ thực sự.

### 20.2. OIDC không an toàn nếu cấp cho untrusted code

Nếu PR job có `id-token: write` và cloud trust policy quá rộng, mã PR có thể yêu cầu token ngắn hạn rồi dùng quyền cloud. OIDC giảm nguy cơ static credentials khi cấu hình đúng, nhưng không làm mã PR đáng tin. Giới hạn OIDC claim theo protected branch/environment và chỉ cấp token trong trusted release context.

## 21. BuildService và locks: quản lý contention, không tự tạo security boundary

Gradle `BuildService` với `maxParallelUsages` có thể giới hạn số tasks **trong cùng invocation** sử dụng một resource, ví dụ license server hoặc một integration test database. Cơ chế ấy giúp tránh race/concurrency quá mức nhưng **không chặn PR code độc hại truy cập network hoặc secrets**.

Một shared service ở Gradle được các tasks đăng ký `usesService`; nếu `maxParallelUsages=1`, Gradle điều phối các tasks dùng service theo hạn mức. Tuy nhiên, mã chưa tin cậy có thể không sử dụng service, và CI jobs khác không nằm trong invocation. Vì vậy resource scheduling **khác** authorization/security sandbox.

Tương tự, `maxParallelForks=1` có thể tránh flaky tests dùng DB chung, nhưng không bảo đảm test code không gửi request độc hại. Đừng coi task ordering hoặc worker caps là biện pháp chống supply-chain execution.

## 22. Quan sát dependency graph sau khi đã cô lập checkout

Các lệnh giúp tìm resolved artifacts:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight \
    --configuration testRuntimeClasspath \
    --dependency junit-jupiter
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat dependencyInsight --configuration testRuntimeClasspath --dependency junit-jupiter
~~~

Báo cáo giúp hiểu resolved version/conflicts, nhưng **chính các lệnh này vẫn execute Wrapper/settings/plugin code**. Chỉ chạy trong môi trường tin cậy hoặc unprivileged sandbox, sau khi Wrapper được validate. `dependencyInsight` không kiểm malware/provenance; cần verification metadata/registry policy.

### 22.1. Review Git diff build files

Trong Git repo, so PR commit với trusted base để xem thay đổi script/workflow:

~~~bash
git diff --name-status main...HEAD
~~~

Lệnh là ví dụ khi `main` là base branch phù hợp và local refs đã cập nhật; không dùng mù quáng trên mọi repository. Đừng chỉ đọc tên file: xem content diff và checksum của binary Wrapper JAR. Nếu PR đổi branch protection/workflow permissions, cần reviewer có quyền đánh giá policy.

## 23. Những tình huống phải dừng và điều tra

| Tín hiệu | Hành động an toàn |
| --- | --- |
| Wrapper JAR không khớp checksum official | Không chạy Wrapper, xác minh source |
| Distribution SHA mismatch | Dừng, kiểm upstream official checksum/mirror |
| Repository HTTP hoặc URL lạ xuất hiện | Yêu cầu security review |
| Internal package resolve từ public registry | Sửa `exclusiveContent`, đánh giá compromise |
| Dependency verification fail | Điều tra artifact/key; không tắt verification |
| PR tự thêm trusted PGP key/checksum không giải thích | Không auto-approve |
| PR thêm plugin mới từ publisher chưa review | Pin source/version, kiểm plugin code và trust |
| `pull_request_target` checkout PR head và chạy Gradle | Chặn privileged execution |
| `workflow_run` chạy file từ artifact PR | Chặn hoặc chỉ parse data an toàn |
| PR job dùng privileged self-hosted runner | Dời sang isolated runner |
| PR có `packages: write`, `id-token: write` không cần | Thu hẹp permissions |
| PR có remote cache release write credential | Tách cache/credential scopes |
| Build logic đọc secret rồi gửi request | Điều tra incident và rotate tokens |
| Build Scan/log chứa token | Revoke/rotate secret và chỉnh logging policy |
| Artifact được release từ unreviewed PR output | Dừng release, rebuild protected ref |

Không mặc định tác giả có ý xấu; nhiều lỗi đến từ cấu hình thiếu hiểu biết. Tuy nhiên, cần chặn vượt trust boundary **trước** khi xác minh.

## 24. Incident response khi nghi supply-chain compromise

Khi đã chạy một Wrapper/plugin/dependency đáng ngờ:

1. Dừng release/deploy và các pipelines sử dụng artifacts liên quan.
2. Cô lập runner/CI host, giữ logs và evidence theo policy, tránh tiếp tục chạy mã nghi ngờ.
3. Thu hồi hoặc rotate secrets, registry/cloud tokens có thể bị truy cập.
4. Xác định commit/PR, plugin coordinates, Wrapper version, repository URLs và artifact hashes.
5. Kiểm tra Gradle User Home, remote cache write, published artifacts và downstream consumers.
6. Phân biệt artifact changed, trusted key issue, compromised publisher và security misconfiguration.
7. Rebuild trên trusted fresh runner với verified source/dependencies.
8. So digests/SBOM/provenance và quyết định thu hồi/phát hành lại nếu cần.
9. Thông báo security owners/affected users theo incident policy.
10. Bổ sung regression controls ở CI/runner/repository scope sau xử lý.

Không xóa hết cache/host logs trước khi lưu evidence cần thiết cho investigation.

## 25. Anti-patterns cần tránh

**A — “PR chạy test thôi nên an toàn.”** Test/build scripts vẫn là mã executable.

**B — “Plugin chỉ là dòng cấu hình.”** Plugin chạy trong Gradle process.

**C — “Checksum do PR ghi là trusted.”** Attacker có thể thay artifact và checksum cùng lúc.

**D — “HTTPS đủ để chứng minh artifact.”** Nó chỉ bảo vệ transport, không tự xác minh publisher/release identity.

**E — “Pin version là khóa bytes.”** Version và artifact content là hai lớp khác nhau.

**F — “Lockfile thay dependency verification.”** Lock ghi resolved versions, không SHA/signature.

**G — “Checksum đúng nên không cần CVE scan.”** Artifact hợp lệ vẫn có thể có lỗ hổng.

**H — “Đặt internal repo trước public là đủ.”** Dùng `exclusiveContent` cho internal group.

**I — “FAIL_ON_PROJECT_REPOS bảo vệ cả khi PR sửa settings.”** PR có thể sửa chính policy file.

**J — “pull_request_target chạy base workflow nên execute PR head an toàn.”** Đây là privilege-boundary violation.

**K — “workflow_run artifact đã PASS nên được sign/publish.”** Artifact vẫn là untrusted input.

**L — “Runner self-hosted không có GitHub secrets nên không có secrets nào.”** Files/env/cloud metadata có thể chứa quyền riêng.

**M — “Build cache key chứng minh artifact trusted.”** Cần cache ACL, integrity và trust partition.

**N — “--offline chặn code độc.”** Cached binary vẫn có thể chạy.

**O — “Lệnh gradle help là read-only forensic.”** Wrapper/settings/plugins vẫn có thể thực thi.

**P — “Có OIDC thì PR mã gì cũng chạy được.”** OIDC token vẫn có privileges khi cloud trust policy sai.

**Q — “Tắt verification cho CI xanh nhanh hơn.”** Bỏ integrity control thay vì điều tra.

**R — “Một commit đã merge thì mọi dependency mới chắc an toàn.”** Merge/review là authority boundary cần kết hợp repository controls/scanning.

## 26. Bài tập có đáp án

**Câu 1.** Vì sao `./gradlew help` không an toàn trên checkout chưa tin cậy có secrets?  
**Đáp án:** Wrapper/settings/plugin có thể execute trước task action.

**Câu 2.** Wrapper JAR checksum nên so với nguồn nào?  
**Đáp án:** official Gradle release checksums độc lập với PR.

**Câu 3.** `distributionSha256Sum` kiểm Wrapper JAR không?  
**Đáp án:** không, kiểm distribution ZIP được download.

**Câu 4.** Nếu distribution đã cached, có thể mặc định nó được re-verified mọi invocation không?  
**Đáp án:** không; phải quản lý cache/runner integrity.

**Câu 5.** PR từ fork với `pull_request` thường có secrets không?  
**Đáp án:** repository secrets thường bị withheld theo GitHub policy; vẫn phải kiểm permissions/runner environment.

**Câu 6.** `pull_request_target` có thể build PR head trong privileged job không?  
**Đáp án:** không nên; đó là rủi ro vượt trust boundary.

**Câu 7.** Artifact PR từ `workflow_run` có tự trusted không?  
**Đáp án:** không; xử lý như dữ liệu chưa tin cậy.

**Câu 8.** `permissions: contents: read` có xóa cloud credentials khỏi self-hosted runner không?  
**Đáp án:** không; phải cô lập runner.

**Câu 9.** Java demo `SafeGreeting` in gì với Ada?  
**Đáp án:** `Hello, Ada!`.

**Câu 10.** Chạy `javac/java` thuần có verify Gradle plugin không?  
**Đáp án:** không; chỉ thử Java source.

**Câu 11.** Internal group bị attacker xuất bản trên public repo: control nào?  
**Đáp án:** `exclusiveContent` giới hạn nguồn internal coordinates.

**Câu 12.** `includeGroupAndSubgroups` khác `includeGroup` thế nào?  
**Đáp án:** còn bao gồm các subgroup hierarchy.

**Câu 13.** `FAIL_ON_PROJECT_REPOS` có đủ khi PR sửa chính settings không?  
**Đáp án:** không; cần trusted infra policies ngoài checkout.

**Câu 14.** Một plugin version cố định có thể là malware không?  
**Đáp án:** có; cần publisher review và artifact verification.

**Câu 15.** Artifact đúng SHA-256 có thể vẫn có CVE không?  
**Đáp án:** có; cần scanning.

**Câu 16.** Lockfile xác minh SHA của JAR không?  
**Đáp án:** không; lock giữ versions.

**Câu 17.** Vì sao không auto-accept verification metadata vừa bootstrap từ PR?  
**Đáp án:** có thể ghi checksum của artifact đã compromise.

**Câu 18.** `buildSrc` có được thực thi trong build không?  
**Đáp án:** có, Gradle compile/load build logic trước tests.

**Câu 19.** Annotation processor có nguy cơ chạy mã trong CI không?  
**Đáp án:** có, trong compiler context.

**Câu 20.** Root current build verification metadata có áp vào included builds không?  
**Đáp án:** có theo Gradle composite verification rules.

**Câu 21.** Version catalog alias bảo đảm resolved version đúng giá trị alias không?  
**Đáp án:** không; resolution có thể chọn bản khác.

**Câu 22.** Có nên đặt publish token vào PR workflow chỉ để test task `publish` dry-run?  
**Đáp án:** không; tách release authorization.

**Câu 23.** Remote Build Cache PR job nên có quyền ghi cache release không?  
**Đáp án:** không; cần phân tách trust scopes/ACL.

**Câu 24.** `--offline` có làm cached plugin không chạy không?  
**Đáp án:** không.

**Câu 25.** `BuildService.maxParallelUsages` có sandbox PR khỏi cloud credentials không?  
**Đáp án:** không; nó giới hạn concurrency, không cấp quyền.

**Câu 26.** OIDC `id-token: write` có thể là rủi ro với PR code không?  
**Đáp án:** có nếu trust policy cấp cloud privileges.

**Câu 27.** PR title/body có trusted trong privileged metadata workflow không?  
**Đáp án:** không; phải escape/parse data đúng.

**Câu 28.** Workflow release nên dùng artifact nào?  
**Đáp án:** rebuild từ protected reviewed commit/tag bằng trusted runner.

**Câu 29.** Một plugin repository khác Maven Central; nơi cấu hình?  
**Đáp án:** `pluginManagement.repositories` tại settings.

**Câu 30.** Build PASS với JUnit có chứng minh không lộ secrets?  
**Đáp án:** không; tests không thay security controls.

**Câu 31.** Runner chứa shared Docker socket có tự isolated chỉ vì chạy trong container không?  
**Đáp án:** không; Docker socket có thể cấp quyền lên host.

**Câu 32.** Khi verification mismatch, có nên đổi checksum sang actual hash cho build xanh?  
**Đáp án:** không; cần verify independent source và review.

## 27. Checklist bảo vệ build và release

- [ ] PR code và build logic được coi untrusted trước review?
- [ ] PR workflow dùng event/permissions phù hợp, read-only token?
- [ ] Không truyền cloud/publish/sign secrets vào PR job?
- [ ] Runner ephemeral hoặc sandbox không có persistent credentials?
- [ ] Wrapper scripts/JAR được kiểm official checksum trước khi chạy?
- [ ] Distribution URL HTTPS, version pin, `distributionSha256Sum` chính thức?
- [ ] Plugin/version/catalog/buildSrc/build-logic diffs được review?
- [ ] Plugin source/publisher/repository và transitive graph được xác minh?
- [ ] Plugin management và dependency repository policy đều được quản lý?
- [ ] Internal groups có `exclusiveContent`/equivalent?
- [ ] `FAIL_ON_PROJECT_REPOS` ở trusted settings, không bị xem là immutable với PR?
- [ ] Không dùng HTTP insecure repo để chữa resolution lỗi?
- [ ] Dependency verification metadata được commit và reviewed?
- [ ] Verification mismatch dẫn đến investigation, không tắt control?
- [ ] Lockfiles đúng resolved graph, không nhầm với hash verification?
- [ ] Có SCA/vulnerability scan, SBOM khi phù hợp?
- [ ] `pull_request_target` không checkout/execute PR head?
- [ ] `workflow_run` không execute PR artifacts?
- [ ] PR artifacts không được ký/phát hành trực tiếp?
- [ ] Actions trong production workflows pin reviewed immutable SHA?
- [ ] Release rebuild từ protected branch/tag và có approval?
- [ ] OIDC/environment secrets chỉ ở trusted release context?
- [ ] PR jobs không được ghi privileged remote Build Cache?
- [ ] Gradle User Home và runner filesystem không chia sẻ secrets?
- [ ] External artifact outputs và downloaded archives được xử lý như untrusted data?
- [ ] PR metadata/shell interpolation được parse/quote/validate đúng?
- [ ] Security-sensitive changes có CODEOWNERS/reviewer chuyên trách?
- [ ] Incident response, token rotation và cache invalidation policy sẵn sàng?
- [ ] Functional tests và supply-chain controls được xác nhận độc lập?

## 28. Tài liệu chính thức

- [Gradle — Best Practices for Security](https://docs.gradle.org/current/userguide/best_practices_security.html): Wrapper JAR/distribution verification và security practices.
- [Gradle — Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html): untrusted checkout, Wrapper risk, IDE sync và build logic.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): checksum, official JAR checks, distribution downloads.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksum/PGP, metadata bootstrapping, included builds và errors.
- [Gradle — Securing Dependencies](https://docs.gradle.org/current/userguide/securing_dependencies.html): integrity/provenance vs vulnerability.
- [Gradle — Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html): HTTPS, content filtering, `exclusiveContent` và dependency confusion.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): resolved version lockfiles và cập nhật.
- [Gradle — Centralizing Repositories](https://docs.gradle.org/current/userguide/centralizing_repositories.html): `dependencyResolutionManagement` và repository mode.
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html): requested dependency/plugin aliases.
- [Gradle — Plugin Management](https://docs.gradle.org/current/userguide/plugins_intermediate.html): plugin DSL và plugin resolution.
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html): included builds và build boundaries.
- [GitHub — Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use): untrusted workflows, permissions và supply-chain risks.
- [GitHub — Securely using pull_request_target](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target): privileged PR event và untrusted checkout.
- [GitHub — Compromised runners](https://docs.github.com/en/actions/concepts/security/compromised-runners): fork restrictions, runner secrets và compromise.
- [GitHub — Workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax): permissions, events, environment.
- [Gradle — Official Release Checksums](https://gradle.org/release-checksums/): independent trusted SHA values cho Wrapper và Gradle distributions.

**Kết luận:** Gradle Wrapper, build scripts và plugins **có thể thực thi mã** trước khi Java tests bắt đầu. Vì vậy mã của PR chưa review phải chạy ở **runner ít quyền**, không được mang release credentials vào context ấy, và PR artifacts không tự trở thành trusted release. Với external repositories, dùng HTTPS/trusted source, `exclusiveContent` cho internal groups, pinned/locked versions, dependency verification và vulnerability scanning để kiểm soát cả nguồn lẫn nội dung artifact. Với GitHub Actions, tách `pull_request` read-only khỏi release workflow và không execute PR head trong `pull_request_target` hoặc artifact PR trong `workflow_run` có đặc quyền. **Trust boundary phải được thực thi bằng CI permissions, runner isolation, repository policy và independent review; một dòng BUILD SUCCESSFUL không đủ.**