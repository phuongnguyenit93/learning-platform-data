# Chỉ cấp thông tin bí mật và quyền phát hành cho nhánh, sự kiện hợp lệ trong Gradle CI/CD

## 1. Tại sao build thành công không có nghĩa được phép phát hành?

Một Java library có thể được biên dịch và kiểm thử từ mọi pull request, kể cả PR đến từ fork. Nhưng credential để ghi Maven repository, private signing key, cloud identity hoặc quyền tạo GitHub Release **không được cấp cho mọi build**. Gradle scripts và Gradle plugins là mã có thể thực thi: khi CI chạy `./gradlew check`, mã trong `settings.gradle.kts`, `build.gradle.kts`, `buildSrc` hoặc external plugins có thể đọc environment, gọi process và truy cập network.

Nếu pipeline đặt `PUBLISH_PASSWORD` trong environment của một job chạy mã PR chưa được review, attacker có thể thêm một đoạn build logic gửi credential ra ngoài. Việc job chỉ gọi `check` chứ không gọi `publish` **không bảo vệ credential** khi secret đã được cấp cho process chạy code không tin cậy.

Nguyên tắc của bài học:

> **Xác minh quyền trước khi cấp secret; tách build/test không cần secrets khỏi release job; bảo vệ nguồn mã, Git ref, CI environment và repository write ACL như những lớp kiểm soát độc lập.**

Đây là bài học trong nhóm **Tích hợp CI/CD với Gradle**. Trọng tâm là kiểm tra **branch, tag, event, source commit, review/approval và identity** trước khi cho phép Maven publishing; không phải hướng dẫn lưu token trong project.

### 1.1. Luồng mong muốn

```text
Untrusted fork PR / branch
  -> verify job: read-only checkout + Gradle check
  -> no release secrets, no signing key, no remote publication

Reviewed PR merged to protected main
  -> required status checks pass
  -> maintainer/release bot creates protected v1.2.3 tag

Release tag push
  -> verify event/ref/repository/source commit
  -> Gradle compile/test/check
  -> protected environment requires approval
  -> issue scoped publisher credentials or OIDC identity
  -> publish exact approved artifact/version
  -> verify Maven GAV, checksum, signature and provenance
```

Nếu một bước không đạt, hệ thống **fail-closed**: không âm thầm chuyển sang token khác, không phát bản stable vào repository thử nghiệm để “chữa cháy”, không cấp credential cho một event không được phép.

## 2. Ma trận độ tin cậy theo sự kiện

| Sự kiện/ngữ cảnh | Có thể chạy Gradle test? | Được phát stable artifact? |
| --- | --- | --- |
| `pull_request` từ fork | Có, nhưng token read-only và không publishing secrets. | **Không**. |
| `pull_request` từ branch nội bộ | Có, code vẫn chưa được review/merge. | **Không**. |
| Push feature branch | Có theo CI filter. | **Không**. |
| Push vào protected `main` | Có, có thể build artifacts kiểm tra. | Không tự phát stable theo policy ví dụ. |
| Tag `v1.2.3` chưa được bảo vệ | Có thể verify. | **Không** chỉ vì tag có tên đẹp. |
| Tag bảo vệ, commit không thuộc reviewed main | Có thể verify và phát hiện lỗi. | **Không**. |
| Tag hợp lệ nhưng checks fail | Verify fail. | **Không**. |
| Tag hợp lệ, đang chờ environment reviewer | Verify xong. | **Chưa**. |
| Tag hợp lệ, đúng source, checks và approval pass | Có. | Có, **nếu** backend cho identity quyền ghi. |
| `workflow_dispatch` manual | Phụ thuộc user/ref, cần validation. | Không mặc nhiên được phép. |
| `pull_request_target` | Rất cẩn trọng với code PR không tin cậy. | Không chạy PR code với secrets. |
| `workflow_run` tiếp nhận artifact từ PR | Có thể dùng sau validate. | Không dùng untrusted artifact làm executable/published bytes thiếu provenance. |

**Không có thuộc tính đơn lẻ nào đủ.** `github.base_ref == 'main'` chỉ nói PR **nhắm tới main**, không có nghĩa PR đã được review. `refs/tags/v1.2.3` là tag name, không chứng minh tag creator được tin cậy. `github.event_name == 'push'` không chứng minh commit đã qua bảo vệ branch.

## 3. Ba lớp enforcement độc lập

### 3.1. Lớp workflow/job filter

CI xác định event, ref, repository identity và release version hợp lệ trước khi tạo publish job. GitHub Actions dùng `on.push.tags`, `jobs.publish.if`; GitLab dùng `rules:if` với `CI_PIPELINE_SOURCE`, `CI_COMMIT_TAG`, `CI_COMMIT_REF_PROTECTED`.

### 3.2. Lớp secrets/environment approval

Environment `maven-release` có protected deployment tag rules và required reviewers. Chỉ publish job tham chiếu environment này và mới được nhận secrets sau khi rules pass. Với GitLab, biến `Protected` và protected environment/runner được cấu hình tương ứng. Không đặt `PUBLISH_PASSWORD` ở workflow-level environment hoặc mọi job.

### 3.3. Lớp quyền ghi tại artifact repository

Server Maven/Nexus/Artifactory/GitHub Packages/IAM cấp quyền:
- Read-only dependency consumer.
- Snapshot writer nếu quy trình cần snapshots.
- Stable release writer chỉ được ghi release namespace.
- Không redeploy/overwrite stable GAV; không quyền admin/delete credentials.

Ngay cả khi YAML có bug, backend phải từ chối PUT của identity không được phép. Đừng coi một shell `if` là biên giới bảo mật cuối cùng.

## 4. Cách nhận diện event và Git ref trong GitHub Actions

| Biến/context | Ví dụ | Dùng làm gì? |
| --- | --- | --- |
| `github.event_name` | `push`, `pull_request`, `workflow_dispatch` | Loại sự kiện thực sự. |
| `github.ref` | `refs/heads/main` | Full branch ref của push event. |
| `github.ref` | `refs/tags/v1.2.3` | Full tag ref của tag push. |
| `github.ref` với PR | `refs/pull/24/merge` | Thường không phải protected release ref. |
| `github.ref_name` | `v1.2.3` | Chỉ tên rút gọn, có thể trùng branch/tag. |
| `github.repository` | `demo-org/release-gates` | Đảm bảo đúng repository cho phép publish. |
| `github.base_ref` | `main` | Đích PR; không chứng minh code nguồn đáng tin. |
| `github.head_ref` | `feature/new-feature` | Source branch do PR author có thể kiểm soát. |
| `github.sha` | Event-associated commit | Với PR có thể là merge commit do platform tạo. |
| `secrets.MAVEN_PASSWORD` | Environment secret | Không đọc trong job không có quyền. |
| `vars.MAVEN_RELEASE_URL` | Environment variable | Cấu hình URL, không phải authorization. |

Đối với event `push`, GitHub workflow syntax cho phép:

```yaml
on:
  pull_request:
  push:
    branches:
      - main
    tags:
      - 'v*'
```

`v*` là **glob**, không phải SemVer regular expression. Nó có thể match `vtest` hay `vabc`; chỉ dùng làm bộ lọc sơ bộ. Job publisher phải validate version chặt hơn.

## 5. Quyền GITHUB_TOKEN và nguyên tắc least privilege

Đặt mức mặc định hẹp:

```yaml
permissions:
  contents: read
```

Với checkout/build/test thông thường, `contents: read` thường đủ. Không cấp `contents: write`, `packages: write`, `actions: write` hoặc `id-token: write` cho mọi job theo thói quen.

Khi publish **GitHub Packages**, chỉ publish job mới có thể cần `packages: write`. Khi upload tới internal Maven bằng username/password khác, `GITHUB_TOKEN` có thể vẫn chỉ cần `contents: read`. Nếu dùng OIDC, thêm `id-token: write` **chỉ** vào job đổi OIDC token lấy short-lived credentials và bắt buộc cấu hình IAM trust policy ràng buộc repo/ref/environment.

GitHub thường không truyền repository secrets thông thường cho workflow từ fork PR; những ngoại lệ/cấu hình admin về token permissions vẫn tồn tại. **Đừng dựa hoàn toàn vào behavior mặc định của fork**: job publisher cần event/ref/environment/server-side controls riêng.

## 6. Demo Java 17 và Gradle Maven Publish: kiểm thử được mà không có secrets

Ví dụ này cố tình tách một **LocalStaging repository** không cần credentials khỏi **ReleaseRepo** có credentials và chỉ đăng ký khi explicit bật remote publication. Nó minh họa rằng developer/PR có thể compile/test và kiểm tra publication model mà không cần quyền release.

### 6.1. Cây thư mục

```text
release-gates/
├── settings.gradle.kts
├── gradle.properties
├── build.gradle.kts
├── tools/
│   └── ReleaseGateDemo.java
├── src/
│   ├── main/java/demo/Greeting.java
│   └── test/java/demo/GreetingTest.java
└── .github/workflows/release.yml
```

Ngoài các file được liệt kê, cần Gradle Wrapper `gradlew`, `gradlew.bat` và `gradle/wrapper/` đã tạo/commit bằng Gradle version hỗ trợ Java 17. Mẫu dùng JDK 17+, dependency JUnit Jupiter từ Maven Central hoặc cache/mirror có sẵn.

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "release-gates"
```

**`gradle.properties`:**

```properties
org.gradle.warning.mode=all
```

Không lưu password/token/private signing key ở file này trong Git. `releaseVersion` được truyền vào từ tag bởi release CI, còn local build mặc định `0.1.0-SNAPSHOT`.

### 6.2. build.gradle.kts hoàn chỉnh

```kotlin
import org.gradle.api.publish.maven.MavenPublication

plugins {
    `java-library`
    `maven-publish`
}

group = "org.example.training"
version = providers.gradleProperty("releaseVersion")
    .orElse("0.1.0-SNAPSHOT")
    .get()

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
    withSourcesJar()
    withJavadocJar()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.11.4")
}

tasks.test {
    useJUnitPlatform()
}

val enableRemote = providers
    .gradleProperty("enableRemotePublication")
    .map { it == "true" }
    .orElse(false)
    .get()

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
            pom {
                name.set("Release Gates Example")
                description.set("A gated Gradle publication")
                url.set("https://example.org/release-gates")
            }
        }
    }

    repositories {
        maven {
            name = "LocalStaging"
            url = uri(
                layout.buildDirectory.dir("publication-staging")
            )
        }

        if (enableRemote) {
            maven {
                name = "ReleaseRepo"
                url = uri(
                    providers.gradleProperty("releaseRepoUrl").get()
                )

                credentials {
                    username = providers
                        .environmentVariable("PUBLISH_USER").orNull
                    password = providers
                        .environmentVariable("PUBLISH_PASSWORD").orNull
                }
            }
        }
    }
}
```

**Ý nghĩa từng lớp:**

- `repositories { mavenCentral() }` dùng **tải dependencies**; `publishing.repositories` là **đích upload**.
- `LocalStaging` là file-based Maven repo dưới `build/publication-staging`, dùng cho local QA. Nó không cấp quyền remote.
- `enableRemotePublication` mặc định false nên local `check` hoặc `publishMavenJavaPublicationToLocalStagingRepository` **không cần secrets**.
- Khi `enableRemotePublication=true`, Gradle mới đăng ký `ReleaseRepo` và task `publishMavenJavaPublicationToReleaseRepoRepository`.
- `releaseRepoUrl` phải trỏ Maven-compatible releases endpoint đã được cấp phép. `example.org` trong POM chỉ là metadata minh họa, không phải một release service có thật.
- Username/password lấy từ environment variables `PUBLISH_USER`/`PUBLISH_PASSWORD`, không lưu trong Gradle source.
- `maven-publish` không tự chạy `check` trước mọi targeted publish task. CI phải đảm bảo verification pass trước publish.
- Điều kiện enableRemote là defense-in-depth tiện dụng, **không phải** policy độc lập: code Gradle có thể bị thay. Không chạy mã chưa tin cậy trong môi trường chứa secrets.

### 6.3. Source Java 17

**`src/main/java/demo/Greeting.java`:**

```java
package demo;

import java.util.Objects;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String name) {
        return "Hello, " + Objects.requireNonNull(name).strip() + "!";
    }

    public static void main(String[] args) {
        System.out.println(message(" Release "));
    }
}
```

Biên dịch/chạy **độc lập Gradle** với JDK 17:

```bash
mkdir -p manual-out
javac --release 17 -d manual-out src/main/java/demo/Greeting.java
java -cp manual-out demo.Greeting
```

Stdout chính xác:

```text
Hello, Release!
```

Đây là Java 17-compatible source không cần thư viện ngoài. Dùng `java -cp` thay vì `java -jar`: Java Library plugin không tự đưa `Main-Class` manifest vào JAR.

### 6.4. Test thực sự trong check task

**`src/test/java/demo/GreetingTest.java`:**

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

public class GreetingTest {
    @Test
    void removesPadding() {
        assertEquals(
            "Hello, Release!",
            Greeting.message(" Release ")
        );
    }
}
```

**Build/test không có publishing secrets:**

```bash
./gradlew --version
./gradlew clean check
./gradlew -PreleaseVersion=1.2.3 \
  publishMavenJavaPublicationToLocalStagingRepository
```

Khi chạy publication local, artifact path là:

```text
build/publication-staging/
  org/example/training/release-gates/1.2.3/
    release-gates-1.2.3.jar
    release-gates-1.2.3.pom
    release-gates-1.2.3-sources.jar
    release-gates-1.2.3-javadoc.jar
    ...
```

Các file `.module`/checksum có thể xuất hiện theo Gradle version/repository behavior. Không suy ra local `publish` đã upload lên Maven Central. `clean` có thể xóa `build/publication-staging`.

Để kiểm tra Java class từ output jar:

```bash
java -cp build/libs/release-gates-1.2.3.jar demo.Greeting
```

Stdout:

```text
Hello, Release!
```

## 7. GitHub Actions: workflow verify rộng, publisher rất hẹp

Tạo file **`.github/workflows/release.yml`**. Ý tưởng:
1. `verify` chạy trên PR/push main/tag, chỉ read-only.
2. `publish` có `needs: verify` nhưng **không chỉ dựa vào test pass**.
3. Publisher yêu cầu event `push`, full ref `refs/tags/v...` và đúng repository.
4. Publisher chạy trong protected `maven-release` environment có approval.
5. Bước shell kiểm tra tag stable version và commit thuộc `main`.
6. Secrets chỉ xuất hiện ở bước cần chúng sau các gates.
7. Remote Gradle publication bật explicit, không dùng local credentials.

### 7.1. release.yml hoàn chỉnh

```yaml
name: Verify and publish Gradle library

on:
  pull_request:
  push:
    branches: [main]
    tags:
      - 'v*'

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - uses: gradle/actions/setup-gradle@v4

      - name: Compile and test without release secrets
        run: ./gradlew --no-daemon clean check

  publish:
    needs: verify
    if: >-
      github.event_name == 'push' &&
      startsWith(github.ref, 'refs/tags/v') &&
      github.repository == 'demo-org/release-gates'

    runs-on: ubuntu-latest
    environment: maven-release

    permissions:
      contents: read

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - uses: gradle/actions/setup-gradle@v4

      - name: Validate tag and reviewed source
        id: version
        shell: bash
        run: |
          set -euo pipefail
          tag="${GITHUB_REF#refs/tags/}"

          if [[ ! "$tag" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
            echo "Invalid stable release tag" >&2
            exit 1
          fi

          git fetch --no-tags origin main
          git merge-base --is-ancestor HEAD FETCH_HEAD

          echo "version=${tag#v}" >> "$GITHUB_OUTPUT"

      - name: Validate repository configuration
        shell: bash
        env:
          PUBLISH_USER: ${{ secrets.MAVEN_USERNAME }}
          PUBLISH_PASSWORD: ${{ secrets.MAVEN_PASSWORD }}
          MAVEN_RELEASE_URL: ${{ vars.MAVEN_RELEASE_URL }}
        run: |
          set -euo pipefail
          test -n "$PUBLISH_USER"
          test -n "$PUBLISH_PASSWORD"
          test -n "$MAVEN_RELEASE_URL"

      - name: Publish approved Maven GAV
        env:
          PUBLISH_USER: ${{ secrets.MAVEN_USERNAME }}
          PUBLISH_PASSWORD: ${{ secrets.MAVEN_PASSWORD }}
          ORG_GRADLE_PROJECT_releaseVersion: ${{ steps.version.outputs.version }}
          ORG_GRADLE_PROJECT_enableRemotePublication: 'true'
          ORG_GRADLE_PROJECT_releaseRepoUrl: ${{ vars.MAVEN_RELEASE_URL }}
        run: |
          ./gradlew --no-daemon \
            publishMavenJavaPublicationToReleaseRepoRepository
```

**Bắt buộc tùy chỉnh trước khi áp dụng:** `demo-org/release-gates` là repository minh họa. Trong GitHub Settings → Environments tạo `maven-release`, cấu hình **required reviewers**, **selected deployment tags**, tạo environment secrets `MAVEN_USERNAME`, `MAVEN_PASSWORD` và environment variable `MAVEN_RELEASE_URL`. Không dùng ví dụ để publish thật nếu repository/artifact metadata và security policy chưa được phê duyệt.

Các action versions `@v4` là ví dụ có thể dùng với môi trường tương thích, **không cam kết là bản mới nhất**. Supply-chain policy production nên pin actions bằng **full reviewed commit SHA**, verify action provenance và nâng version theo quy trình được duyệt.

### 7.2. Vì sao verify job không nhận secrets?

Job `verify` chỉ có checkout, JDK setup, Gradle setup và `./gradlew check`. Nó **không tham chiếu environment `maven-release`** và không truyền Maven publishing secrets. Mã PR có thể được execute trong job đó nhưng không có token ghi stable artifacts.

Với private dependencies phục vụ tests, nếu thực sự cần, dùng **read-only registry credential khác**, giới hạn namespace và không dùng lại publishing token. Đừng biến verify job thành publisher ngầm.

### 7.3. Vì sao publish.if chưa đủ?

`jobs.publish.if` lọc event/ref/repository **nhưng không phải quyền bất biến**. Người có thể sửa workflow ở trusted source hoặc tạo tag nếu thiếu protection có thể thay condition. Cần GitHub branch protection/rulesets, tag protection, CODEOWNERS/reviews, environment approval và Maven server ACL.

`needs: verify` đảm bảo verification job pass theo GitHub Actions dependency semantics; nhưng một PR cũng có thể pass tests. Vì vậy publish job phải **độc lập** kiểm tra event/ref/source và permission.

### 7.4. Environment phải được cấu hình, không chỉ đặt tên

Job có:

```yaml
environment: maven-release
```

không tự tạo reviewer/branch/tag restrictions. GitHub có thể tạo environment chưa tồn tại khi workflow tham chiếu tên mới, trong một số trường hợp **không có protection rules**. Vì thế:
- Cấu hình **Required reviewers** cho environment.
- Chọn **Selected branches and tags**, thêm rule **Tag** pattern `v*` theo đúng policy.
- Đặt secrets ở environment thay vì global repository nếu muốn chỉ publisher có quyền nhận.
- Bảo vệ workflow edits/branch/tag creation.
- Xác minh thực tế settings trên repository/plan; một số environment features phụ thuộc plan và visibility.

Không chọn “Protected branches only” rồi giả định điều đó cũng cho phép mọi tag; branch và tag có deployment policy semantics riêng.

### 7.5. Tag filter là glob; bước shell kiểm tra strict version

`tags: ['v*']` có thể kích hoạt workflow với `vtest`. Publisher chạy kiểm tra Bash regex **stable `vMAJOR.MINOR.PATCH`**, ví dụ `v1.2.3`; từ chối `v1.2`, `vabc`, `v01.2.3` hoặc `v1.2.3-rc.1`.

`git merge-base --is-ancestor HEAD FETCH_HEAD` kiểm tra source commit đã checkout là ancestor của current fetched `main`. Đây là **defense-in-depth**, không xác minh signed tag, không tự kiểm tra người đã tạo tag. Nếu policy chỉ cho release từ **tip của main** thì phải yêu cầu equality `HEAD == origin/main` thay vì ancestry.

### 7.6. Ghi version từ tag mà không đánh mất nguồn gốc

Bash:
```bash
tag="${GITHUB_REF#refs/tags/}"
version="${tag#v}"
echo "version=$version" >> "$GITHUB_OUTPUT"
```

Producer `build.gradle.kts` lấy `releaseVersion` qua `providers.gradleProperty`. GitHub job truyền bằng `ORG_GRADLE_PROJECT_releaseVersion`, Gradle mapping environment-to-project-property. Generated POM/GAV phải khớp tag. Không hard-code phiên bản stable ở nhiều nơi rồi bỏ qua consistency test.

## 8. Vì sao không dùng pull_request_target để chạy Gradle với secrets?

GitHub `pull_request_target` chạy workflow trong **base repository context**. Nếu job có quyền cao rồi checkout PR head và chạy build scripts, PR author có thể thực thi mã với token/credential.

**Anti-pattern cần tránh:**

```yaml
on:
  pull_request_target:

jobs:
  unsafe:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      - run: ./gradlew check
        env:
          PUBLISH_PASSWORD: ${{ secrets.MAVEN_PASSWORD }}
```

Đây là **ví dụ không an toàn, không được dùng**. Chỉ cần attacker sửa `build.gradle.kts` hoặc `settings.gradle.kts` là có thể đọc environment. Thay bằng `pull_request` với `contents: read` và không publishing secrets. Nếu thực sự cần một privileged step như comment/label, tách nó sang workflow **không execute untrusted PR code**.

### 8.1. workflow_run có rủi ro trust bridge

Workflow PR có thể upload một artifact chứa nội dung attacker chọn. Workflow `workflow_run` chạy sau nó với token quyền cao hơn mà tải và **chạy/extract như trusted executable** có thể trở thành cầu nối nguy hiểm. Cần xác minh source repo/ref/SHA, artifact integrity/format, workflow identity và không execute nội dung chưa được tin cậy trong publisher.

### 8.2. workflow_dispatch không mặc nhiên được phép publish

Manual run có thể chọn ref hoặc inputs chưa được validate. Nếu bật `workflow_dispatch` trong release workflow, phải thêm allowlist ref, repository, actor/role, environment approval, tag/commit validation và backend ACL. Bài lab cố tình **không bật manual release** để không mở thêm đường publish cần guard.

### 8.3. Không dùng github.base_ref để cấp release token

`github.base_ref == 'main'` cũng đúng khi một fork PR hướng vào main. Nó kiểm tra **đích PR**, không kiểm tra source đã merge. Tương tự `github.ref_name == 'main'` không phân biệt branch/tag context. Cần kết hợp event type và full ref với policy nguồn code đã review.

## 9. Java 17 standalone policy simulator: kiểm thử deny-by-default

Một mô hình nhỏ giúp test **logic của một release gate** mà không dùng secrets thật. Nó không thay thế GitHub/GitLab permissions hay server ACL.

**`tools/ReleaseGateDemo.java`:**

```java
import java.util.regex.Pattern;

public final class ReleaseGateDemo {
    private static final Pattern STABLE_TAG = Pattern.compile(
        "refs/tags/v(0|[1-9][0-9]*)\\."
            + "(0|[1-9][0-9]*)\\."
            + "(0|[1-9][0-9]*)"
    );

    private ReleaseGateDemo() {
    }

    static boolean mayPublish(
        String event,
        String repository,
        String ref,
        boolean protectedRef,
        boolean approved
    ) {
        return "push".equals(event)
            && "demo-org/release-gates".equals(repository)
            && STABLE_TAG.matcher(ref).matches()
            && protectedRef
            && approved;
    }

    public static void main(String[] args) {
        String repo = "demo-org/release-gates";

        System.out.println("FORK_PR=" + mayPublish(
            "pull_request", repo,
            "refs/pull/12/merge", false, false
        ));
        System.out.println("MAIN_PUSH=" + mayPublish(
            "push", repo, "refs/heads/main", true, true
        ));
        System.out.println("UNPROTECTED_TAG=" + mayPublish(
            "push", repo, "refs/tags/v1.2.3", false, true
        ));
        System.out.println("PENDING_APPROVAL=" + mayPublish(
            "push", repo, "refs/tags/v1.2.3", true, false
        ));
        System.out.println("TRUSTED_RELEASE=" + mayPublish(
            "push", repo, "refs/tags/v1.2.3", true, true
        ));
        System.out.println("BAD_TAG=" + mayPublish(
            "push", repo, "refs/tags/vtest", true, true
        ));
    }
}
```

Biên dịch/chạy bằng JDK 17:

```bash
mkdir -p policy-out
javac --release 17 -d policy-out tools/ReleaseGateDemo.java
java -cp policy-out ReleaseGateDemo
```

Stdout **chính xác**:

```text
FORK_PR=false
MAIN_PUSH=false
UNPROTECTED_TAG=false
PENDING_APPROVAL=false
TRUSTED_RELEASE=true
BAD_TAG=false
```

Đây là **mô phỏng quyết định**, không xác thực thực tế liệu tag có protected hay environment có được reviewer approve. Những booleans là đầu vào tùy ý; attacker có thể gọi function với `true`. Chỉ GitHub/GitLab rules và server-side IAM/ACL mới thực thi quyền.

## 10. GitLab CI: protected variables, protected tags và rules

GitLab có các biến hữu ích:
- `CI_PIPELINE_SOURCE`: loại pipeline, ví dụ `push` hoặc `merge_request_event`.
- `CI_COMMIT_TAG`: tag name trong tag pipeline.
- `CI_COMMIT_REF_PROTECTED`: chuỗi `"true"` khi ref được xem là protected.
- **Protected CI/CD variables**: mặc định chỉ phát cho protected branch/tag pipelines, với những quy định cụ thể cho một số merge request/merged-results cases.
- **Protected environments**: điều khiển ai có quyền thực hiện deployment.

### 10.1. .gitlab-ci.yml minh họa

```yaml
stages:
  - verify
  - publish

verify:
  stage: verify
  image: eclipse-temurin:17-jdk
  script:
    - ./gradlew --no-daemon clean check

publish_release:
  stage: publish
  image: eclipse-temurin:17-jdk
  needs:
    - verify
  environment:
    name: maven-release
  rules:
    - if: '$CI_PIPELINE_SOURCE == "push" && $CI_COMMIT_TAG =~ /^v[0-9]+\.[0-9]+\.[0-9]+$/ && $CI_COMMIT_REF_PROTECTED == "true"'
      when: on_success
    - when: never
  script:
    - 'test -n "$PUBLISH_USER" && test -n "$PUBLISH_PASSWORD"'
    - 'test -n "$MAVEN_RELEASE_URL"'
    - 'export ORG_GRADLE_PROJECT_releaseVersion="${CI_COMMIT_TAG#v}"'
    - 'export ORG_GRADLE_PROJECT_enableRemotePublication=true'
    - 'export ORG_GRADLE_PROJECT_releaseRepoUrl="$MAVEN_RELEASE_URL"'
    - './gradlew --no-daemon publishMavenJavaPublicationToReleaseRepoRepository'
```

Đặt `PUBLISH_USER`, `PUBLISH_PASSWORD` là **Protected, Masked/Hidden** (theo tính năng và policy), `MAVEN_RELEASE_URL` là variable được quản lý. Bảo vệ tag `v*`, protected environment `maven-release` và runner identity; publisher không được phép chạy ở một untrusted feature branch.

GitLab rules regex ở trên cho phép một số version với leading zero (ví dụ `v01.2.3`). Nếu yêu cầu strict SemVer, bổ sung validation script giống GitHub demo, không coi regex cơ bản là policy đầy đủ. Đồng thời nên kiểm tra tag commit thuộc reviewed main theo governance.

### 10.2. Protected khác Masked

- **Protected** giới hạn ref/pipeline context nhận biến.
- **Masked** che một số lần xuất hiện của secret trong logs; không bảo đảm chống mọi exfiltration.
- **Hidden** hạn chế hiển thị secret value trong UI.
- **Protected environment** kiểm soát deployment/approvers.
- **Runner isolation** giảm nguy cơ process/workspace/cache từ job khác nhìn thấy secret.

GitLab docs mô tả trường hợp merge request pipelines **có thể** nhận protected variables khi cả source/target refs protected và thỏa quyền. Do đó, đừng tuyên bố rằng “mọi MR chắc chắn không có protected variables”; chính publisher `rules` vẫn phải loại `merge_request_event` và tất cả event không phải protected tag push.

## 11. Gradle Groovy DSL tương đương với build.gradle.kts

Nếu project dùng Groovy DSL, giữ `Greeting.java` và `GreetingTest.java`. Thay `settings.gradle.kts` bằng:

```groovy
rootProject.name = 'release-gates'
```

Thay **`build.gradle.kts`** bằng:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'org.example.training'
version = providers.gradleProperty('releaseVersion')
    .orElse('0.1.0-SNAPSHOT')
    .get()

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    withSourcesJar()
    withJavadocJar()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

def enableRemote = providers
    .gradleProperty('enableRemotePublication')
    .map { it == 'true' }
    .orElse(false)
    .get()

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            pom {
                name = 'Release Gates Example'
                description = 'A gated Gradle publication'
                url = 'https://example.org/release-gates'
            }
        }
    }

    repositories {
        maven {
            name = 'LocalStaging'
            url = layout.buildDirectory.dir('publication-staging')
        }
        if (enableRemote) {
            maven {
                name = 'ReleaseRepo'
                url = uri(providers.gradleProperty('releaseRepoUrl').get())
                credentials {
                    username = providers
                        .environmentVariable('PUBLISH_USER').orNull
                    password = providers
                        .environmentVariable('PUBLISH_PASSWORD').orNull
                }
            }
        }
    }
}
```

Hai bản Kotlin/Groovy có cùng policy: remote repository chỉ được đăng ký với `enableRemotePublication=true`, credential được đọc từ environment, còn local staging có sẵn không cần token. **Không trộn syntax Kotlin/Groovy trong cùng một script.**

## 12. Version từ tag, commit và Maven GAV phải thống nhất

Một release được kiểm soát cần liên kết:

```text
Protected Git tag:       v1.2.3
Reviewed source commit:  full Git SHA
Gradle version:          1.2.3
Maven GAV:
  org.example.training:release-gates:1.2.3
Artifact SHA-256:        hash of published bytes
CI run ID:               exact verified workflow run
Environment approval:    reviewer + time + policy
```

**Git tag name không thay thế source commit SHA**. Tag có thể bị chuyển nếu không protected; cùng source SHA cũng chưa chắc tạo JAR byte-identical nếu toolchain/dependency/plugin versions khác. Vì vậy cần ghi **artifact hashes, Gradle Wrapper/JDK, CI provenance và repository audit**.

Nếu tag `v1.2.3` nhưng generated POM ghi `0.1.0-SNAPSHOT`, release phải **fail**. Nếu một stable GAV đã tồn tại, repository không nên cho redeploy; nếu cần sửa lỗi, phát hành `v1.2.4`.

### 12.1. Source ancestry khác source equality

`git merge-base --is-ancestor HEAD FETCH_HEAD` chỉ yêu cầu tagged commit là ancestor của tip `main`. Nó cho phép tag một commit cũ đã merge. Nếu governance yêu cầu release tại chính tip, kiểm tra **full SHA equality** với current reviewed main. Dù dùng cách nào, tag creation policy và required checks vẫn cần được enforce.

### 12.2. Stable tag và prerelease tag

Release sample chỉ chấp nhận `vMAJOR.MINOR.PATCH`. Nếu team muốn `v2.0.0-rc.1`, cần policy riêng:
- Cho phép prerelease đúng SemVer.
- Tách staging/prerelease repository nếu phù hợp.
- Không gắn nhãn stable hay nâng latest tag sai.
- Dùng protected tag rules và source verification tương đương stable.
- Không tái sử dụng cùng GAV sau khi công bố.

Snapshot `-SNAPSHOT` là một quy ước Maven khác stable releases; không để snapshot branch job dùng stable release credentials.

## 13. Chỉ đưa secrets vào đúng process

Trong ví dụ, Gradle có thể đọc:
- `providers.gradleProperty("releaseVersion")` từ `ORG_GRADLE_PROJECT_releaseVersion`.
- `providers.gradleProperty("releaseRepoUrl")` từ `ORG_GRADLE_PROJECT_releaseRepoUrl`.
- `providers.environmentVariable("PUBLISH_USER")` và `...("PUBLISH_PASSWORD")` từ publisher step.

**Không đưa password lên command line:**

```bash
# ANTI-PATTERN: có nguy cơ lọt vào process listing/CI logs.
./gradlew publish -PpublishPassword=real-secret-value
```

**Không commit secret vào source:**

```properties
# ANTI-PATTERN:
publishPassword=real-secret-value
```

**Không print secret trong Gradle configuration:**

```kotlin
// ANTI-PATTERN:
println(providers.environmentVariable("PUBLISH_PASSWORD").get())
```

Đây là những **ví dụ không được sử dụng**. Environment variables vẫn có thể bị đọc bởi code đang chạy trong process đó; bảo mật phải bắt đầu **trước khi job nhận secrets**. CI log masking là lớp hỗ trợ, không bảo vệ khỏi malicious network request hoặc cached artifact chứa secret.

### 13.1. Khi thiếu secret, phải fail

GitHub sample dùng `test -n` để xác minh secrets/config tồn tại mà **không in giá trị**. Nếu secret rỗng, upload không được phép chạy. Gradle có thể fail khi task cần credentials; tuy nhiên check trước giúp thông báo rõ hơn.

Không fallback sang `mavenLocal()`, anonymous upload hay một shared admin token khi secret không hợp lệ. Đó là thay đổi security policy, không phải error recovery.

## 14. OIDC: giảm static secrets, không thay điều kiện trust

Khi cloud/artifact provider hỗ trợ OIDC identity federation, release job có thể nhận **short-lived identity token**, đổi lấy temporary credentials. Ưu điểm: không phải cất static password có tuổi thọ dài.

Nhưng IAM trust policy phải ràng buộc:
- Repository/organization identity.
- Workflow/job identity.
- Protected ref/tag hoặc environment.
- Token audience, issuer và thời hạn.
- Scoped role chỉ upload đúng repository/path.

GitHub job dùng OIDC cần `permissions: id-token: write` **chỉ ở job đó**. Không cấp quyền này cho mọi PR job theo mặc định. Nếu backend Maven chỉ hỗ trợ Basic/token auth, không tự invent OIDC exchange endpoint; có thể dùng static scoped credential trong protected environment với rotation.

### 14.1. So sánh static token và OIDC

| Thuộc tính | Static Maven token | OIDC short-lived |
| --- | --- | --- |
| Secrets trong CI | Cần lưu token/password. | Có thể không lưu long-lived cloud credential. |
| Thời hạn | Có thể dài; cần rotation. | Ngắn, thường theo job/session. |
| Quyền | Backend user/ACL. | IAM role/claims/ACL. |
| Rủi ro | Bị lộ có thể dùng tới khi revoke. | Untrusted job nhận role mạnh vẫn nguy hiểm. |
| Phù hợp | Nexus/Artifactory chỉ hỗ trợ user/token. | Provider hỗ trợ OIDC federation. |

## 15. Gradle signing và Maven Central cần gate riêng

Nếu release policy yêu cầu OpenPGP signature, private key/passphrase phải chỉ tồn tại ở trusted publisher job sau approval. Gradle `signing` plugin có thể dùng in-memory keys qua `useInMemoryPgpKeys`.

**Kotlin DSL snippet bổ sung** (chỉ merge vào project đã có `publishing.publications["mavenJava"]`):

```kotlin
plugins {
    `signing`
}

signing {
    val signingKey = providers.gradleProperty("signingKey").orNull
    val signingPassword = providers
        .gradleProperty("signingPassword").orNull

    useInMemoryPgpKeys(signingKey, signingPassword)
    sign(publishing.publications["mavenJava"])
}
```

Truyền `ORG_GRADLE_PROJECT_signingKey` và `ORG_GRADLE_PROJECT_signingPassword` từ protected secrets khi release job được duyệt. **Không dùng key thật trong PR verification**. Nếu signing là bắt buộc, thiếu key phải fail, không tự xuất unsigned artifact.

**Maven Central lưu ý:** Từ 30/06/2025, legacy OSSRH Maven deployment protocol không còn được Central hỗ trợ; cần Central Publisher Portal-compatible publishing flow/plugin và đáp ứng POM metadata, namespace, license, SCM, signatures. Demo `ReleaseRepo` là Maven-compatible endpoint **khác Central**, không khẳng định task Maven Publish đơn giản có thể upload trực tiếp lên Central Portal.

## 16. Rủi ro cache và artifacts đi qua biên giới trust

Một PR chưa trusted có thể tạo:
- Gradle Build Cache outputs.
- CI uploaded artifacts/test reports.
- JAR trong workspace.
- File thay đổi build metadata.

Nếu trusted release job tải **untrusted JAR** hoặc dùng remote Build Cache entry mà PR có quyền ghi, attacker có thể đưa bytes không phản ánh nguồn đã review vào publication. Nguyên tắc:
1. Trusted CI mới được push vào cache namespace dùng cho release; PR pull-only hoặc isolated namespace.
2. Downloaded artifacts từ workflow khác phải có verified source/run/digest.
3. Producer verify job lưu source SHA và SHA-256 của artifacts.
4. Publisher sau approval **promote exact verified bytes**, không rebuild tùy tiện trong môi trường có secrets nếu platform cho phép.
5. Backend Maven chống overwrite stable GAV.
6. Không bao giờ cache private keys/tokens trong task outputs.

**Gradle Build Cache credential không phải Maven publication credential**. Tránh dùng cùng token hoặc namespace cho hai chức năng.

## 17. Jenkins và các CI khác: cùng nguyên tắc

Một Jenkins declarative pipeline có thể dùng `when { buildingTag() }` và `withCredentials` để giới hạn phạm vi secret. Nhưng `buildingTag()` chỉ nói đó là tag build, không kiểm tra protected/ref/source/approval.

**Ví dụ stage minh họa, không phải Jenkinsfile hoàn chỉnh:**

```groovy
stage('Publish approved release') {
    when {
        buildingTag()
    }
    steps {
        withCredentials([
            usernamePassword(
                credentialsId: 'release-maven',
                usernameVariable: 'PUBLISH_USER',
                passwordVariable: 'PUBLISH_PASSWORD'
            )
        ]) {
            sh './gradlew publishMavenJavaPublicationToReleaseRepoRepository'
        }
    }
}
```

Pipeline thực cần thêm branch/tag protection, strict version validation, commit identity, approval, permission-scoped Jenkins agents, CI tests và Maven ACL. Không đưa `withCredentials` ra global block và không chạy untrusted PR Jenkinsfile/Gradle code trên cùng agent với production credentials.

## 18. Vì sao review cả workflow lẫn Gradle source?

Các file thực thi trong CI thường nằm ngoài `src/main/java`:
- `.github/workflows/*.yml`, `.gitlab-ci.yml`, `Jenkinsfile`.
- `settings.gradle(.kts)` và `build.gradle(.kts)`.
- `buildSrc`, `build-logic`, precompiled script plugins, custom tasks.
- Gradle init scripts, Wrapper distribution, external plugin coordinates.
- Shell scripts được gọi bởi CI, code generation và tests.

Một PR chỉ thay `buildSrc/src/main/java/...` có thể chứa đoạn đọc `System.getenv("PUBLISH_PASSWORD")`. Vì vậy **CODEOWNERS/review rules phải bao quát build logic**, không chỉ workflow YAML. Với third-party plugins/actions, pin version/commit, kiểm tra nguồn và cập nhật có quy trình.

## 19. Kiểm chứng quyền: test negative paths không có secret thật

Một chiến lược kiểm tra gồm:
- Java `ReleaseGateDemo` kiểm thử các event/ref inputs giả lập.
- YAML linter/policy scanner phát hiện thiếu `environment` hoặc token permissions quá rộng.
- PR CI chạy `./gradlew check` với không có publisher secrets.
- Dry-run `LocalStaging` Maven publication để kiểm tra JAR/POM/GAV không upload remote.
- Unprotected branch/tag phải không có publish job hoặc bị gate từ chối.
- Tag không đúng version bị validation từ chối.
- Protected tag nhưng chưa approval phải chưa giải phóng secret.
- Missing secret phải fail trước network upload.
- Remote repo read-only identity phải nhận `403` khi thử PUT trên **test endpoint được kiểm soát**.
- Stable GAV đã tồn tại phải được server từ chối overwrite.
- Sau release, tải JAR từ remote và so SHA-256 với manifest.

Không chạy bài test “liệu PR có exfiltrate được production secret không” bằng secret thật. Dùng fake credentials/test repository/isolated environment cho penetration tests được phê duyệt.

### 19.1. Kiểm tra local trước

```bash
./gradlew clean check
./gradlew -PreleaseVersion=1.2.3 \
  publishMavenJavaPublicationToLocalStagingRepository

java -cp build/libs/release-gates-1.2.3.jar demo.Greeting
```

Output Java:
```text
Hello, Release!
```

Việc này kiểm chứng Java/test/publication trong project, **không** xác nhận permission thật của GitHub/GitLab environment. Muốn xác nhận platform guard, cần xem repository configuration/audit và kiểm thử event thực tế với không có production credential.

## 20. Bảng troubleshooting và xử lý sự cố

| Triệu chứng | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| PR được chạy publish job | Job `if` thiếu event/ref hoặc workflow bị thay đổi. | Disable publisher, kiểm tra rules, revoke tokens nếu có phơi bày. |
| Secret có trong verify job | Đặt workflow-level/global env hoặc inherited secrets. | Scope lại vào protected publisher environment. |
| `pull_request_target` chạy Gradle code từ fork | Privileged execution of untrusted source. | Tách workflow, không checkout/execute PR head với credentials. |
| Push `main` phát stable nhầm | Chỉ kiểm tra branch mà thiếu tag/version policy. | Publisher phải yêu cầu explicit protected release tag. |
| Tag `vtest` được publish | Lấy `v*` glob làm SemVer. | Strict version validation trong job/script. |
| Protected tag nhưng source chưa review | Tag creator/ref protection/ancestry chưa được kiểm tra. | Kiểm tra source SHA thuộc main, siết quyền tag. |
| Environment job không đợi approval | Environment không có required reviewer rules. | Cấu hình environment thực, không chỉ tên. |
| GitHub environment không cấp secrets | Rules chưa pass, secrets chưa set, plan/visibility restrictions. | Kiểm tra job/environment settings, không bypass. |
| GitLab masked variable bị lộ | Masking không chặn malicious code/network. | Revoke secret, giới hạn protected refs, review pipeline. |
| GitLab `CI_COMMIT_REF_PROTECTED` false | Tag/branch chưa protected. | Thiết lập protected tag/ruleset, không bypass. |
| Gradle không có ReleaseRepo task | `enableRemotePublication` false hoặc remote repo chưa đăng ký. | Kiểm tra authorized publisher job env. |
| `releaseRepoUrl` thiếu | Publish property không được cấp. | Fail-closed, cấp biến đúng environment/role. |
| Maven `401 Unauthorized` | Token/secret sai/hết hạn. | Rotate/reissue scoped credential. |
| Maven `403 Forbidden` | Backend ACL từ chối. | Xác minh quyền repo/path, không nâng admin tuỳ tiện. |
| Maven conflict/artifact exists | Stable GAV đã tồn tại. | So hashes; không redeploy/overwrite. |
| Signing không có private key | Signing secrets không được cấp ở release environment. | Chỉ cấp sau approval, giữ gate fail nếu thiếu. |
| Java `java -jar` không chạy | Library JAR thiếu Main-Class manifest. | Dùng `java -cp <jar> demo.Greeting`. |
| Release code không trùng verified SHA | Publisher checkout/rebuild từ source khác. | Ngừng promote, so full commit SHA/artifact hashes. |
| Gradle test cần publisher token | Tách dependency read credential và publish write credential. | Refactor verify/build setup. |
| workflow_run publish untrusted artifact | Trust bridge thiếu provenance/checksum validation. | Reject artifacts chưa validate, dùng exact source/run. |
| OIDC token được grant cho PR | IAM trust policy quá rộng. | Khóa repo/ref/environment/audience/TTL và revoke role. |
| Runner bị dùng lại với residual secrets | Isolation/workspace cleanup yếu. | Dùng isolated trusted runners, revoke secrets, audit. |

### 20.1. Incident procedure khi nghi credential đã lộ

1. Dừng release pipeline có nguy cơ, chặn credential và tag manipulation.
2. Revoke/rotate token/private signing key theo ảnh hưởng; invalidate sessions nếu backend hỗ trợ.
3. Kiểm tra CI job logs, runner/workspace, repo/proxy audit logs và artifact upload history.
4. Xác minh Maven GAV/SHA-256 đã publish; đánh dấu/revoke artifact bị ảnh hưởng theo incident policy.
5. Kiểm tra workflow/Gradle source changes và ai có quyền bypass protections.
6. Chia secrets theo read/write/namespace và thêm negative regression tests.
7. Khôi phục release qua protected source/tag mới sau khi security checks pass.

Không log plaintext secrets trong incident report. Nếu release đã công khai dưới stable GAV, không force-overwrite bằng bytes khác; dùng phiên bản mới và quy trình thông báo phù hợp.

## 21. Checklist release-gating hoàn chỉnh

### Source và Git references

- [ ] `main` có required reviews/status checks/branch protection?
- [ ] CODEOWNERS hoặc policy review bao phủ CI YAML, Gradle scripts, buildSrc và plugin code?
- [ ] Release tags `v*` được bảo vệ khỏi tạo/sửa/xóa trái phép?
- [ ] Source commit của tag thuộc reviewed branch theo release policy?
- [ ] Strict stable version validation không chỉ dùng `v*` glob?
- [ ] Không bật đường manual/fork/workflow_run phát hành thiếu authorization?

### CI event và permissions

- [ ] Verify job chạy PR mà **không có** publisher secrets?
- [ ] Job publish yêu cầu event `push` + full tag ref + repository identity?
- [ ] `needs: verify` và required status checks pass?
- [ ] `GITHUB_TOKEN` ở quyền tối thiểu, job nào không publish không có `packages: write`?
- [ ] OIDC `id-token: write` chỉ ở job thực sự cần?
- [ ] Protected environment `maven-release` có rules và required reviewers thật?
- [ ] GitLab variables protected + publisher `rules` chặn MR/non-tag contexts?
- [ ] Trusted runner khác untrusted PR runner khi cần?

### Secrets và Gradle

- [ ] Credentials không nằm trong source, workflow/global env hay CLI args?
- [ ] Chỉ publisher job đọc `PUBLISH_USER`/`PUBLISH_PASSWORD`?
- [ ] `enableRemotePublication` false mặc định và remote task chỉ đăng ký ở authorized job?
- [ ] Missing credentials/release URL gây fail trước upload?
- [ ] Gradle Wrapper/JDK/plugins/dependencies được pin/verify?
- [ ] Java/test/quality gates pass trước publishing?
- [ ] Source SHA, tag, GAV, POM version và artifact checksum khớp?
- [ ] Signing keys chỉ cấp ở protected release context nếu yêu cầu?
- [ ] Maven backend ngăn nonpublisher và stable GAV overwrite?

### Sau phát hành

- [ ] CI lưu approval, run ID, source SHA, release tag, task results?
- [ ] Kiểm tra remote GAV và SHA-256/signature/provenance?
- [ ] Không đưa secrets vào Build Cache/artifacts/logs?
- [ ] Có quy trình rotate/revoke credential và publish hotfix version mới?
- [ ] Test các deny cases bằng dummy secrets, không bằng production credentials?

## 22. Tự kiểm tra kiến thức

1. **PR từ fork có được chạy Gradle `check` không?** — Có, với read-only permissions và không publishing secrets.
2. **PR nhắm `main` có phải trusted source?** — Không; `github.base_ref` là đích PR.
3. **`tags: ['v*']` có đảm bảo strict SemVer không?** — Không, GitHub dùng glob.
4. **Chỉ có `if: startsWith(github.ref,'refs/tags/v')` đã đủ?** — Không; cần event, repo, source, protected tag, environment approval và backend ACL.
5. **Environment name đã tự bật required reviewers chưa?** — Chưa; admin phải cấu hình rules.
6. **Secret masked có an toàn khi untrusted Gradle code chạy không?** — Không; code có thể đọc/exfiltrate secret.
7. **`maven-publish` tự chạy tests trước upload không?** — Không được mặc định suy luận như vậy; CI cần explicit check gate.
8. **Vì sao tách LocalStaging/ReleaseRepo?** — Local tests không cần credential; remote chỉ có trong release context.
9. **OIDC có nghĩa job PR tự an toàn không?** — Không; IAM trust policy phải ràng buộc source/ref/environment.
10. **Giữ nguyên GAV nhưng thay JAR sau bug có được không?** — Không, phát hành version/tag mới.
11. **`pull_request_target` chạy source PR có publisher secret an toàn không?** — Không.
12. **Khi token upload bị lộ phải làm gì đầu tiên?** — Revoke/rotate và dừng đường phát hành nguy hiểm.

**Kết luận:** Trong Gradle CI/CD, kiểm tra branch hoặc tag là điều kiện cần nhưng **không đủ** để cấp secrets hay quyền publish. Mọi code build/test chưa tin cậy phải chạy trong môi trường không có publishing credentials; release job chỉ được phép từ event/ref/source hợp lệ, sau verification và approval, với quyền ghi do backend kiểm soát. Kết hợp protected branches/tags, workflow job conditions, environment secrets, least-privilege tokens/OIDC, Maven immutable GAV và artifact provenance để bảo vệ chuỗi phát hành từ Git commit đến file JAR cuối cùng.

### Tài liệu tham khảo chính thức

- [GitHub Actions — Workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax): push branch/tag glob, job if, permissions.
- [GitHub Actions — Using secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets): fork PR, environment secrets, handling.
- [GitHub — Deployments and environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments): environment gates and deployment branch/tag rules.
- [GitHub — Managing environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments): required reviewers and selected tags.
- [GitHub — Securely using pull_request_target](https://docs.github.com/en/actions/reference/security/securely-using_pull_request_target): elevated context and untrusted code risk.
- [GitHub — OpenID Connect](https://docs.github.com/en/actions/concepts/security/openid-connect): federation and short-lived identity.
- [GitLab — CI/CD variables](https://docs.gitlab.com/ci/variables/): protected, masked, hidden, MR caveats.
- [GitLab — CI/CD pipelines](https://docs.gitlab.com/ci/pipelines/): protected branches and runner security.
- [Gradle — Maven Publish](https://docs.gradle.org/current/userguide/publishing_maven.html): publication tasks, repositories and Maven Central.
- [Gradle — Supported repository protocols](https://docs.gradle.org/current/userguide/supported_repository_protocols.html): credentials and conditional requirements.
- [Gradle — Build environment](https://docs.gradle.org/current/userguide/build_environment.html): Gradle properties/environment variable mapping.
- [Gradle — Signing Plugin](https://docs.gradle.org/current/userguide/signing_plugin.html): OpenPGP signing and in-memory keys.
- [Gradle — Dependency verification](https://docs.gradle.org/current/userguide/dependency_verification.html): downloaded artifact integrity.
