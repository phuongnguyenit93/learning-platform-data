# Xây dựng workflow Gradle trên GitHub Actions

GitHub Actions là hệ thống tự động hóa được kích hoạt bởi sự kiện trong GitHub. Gradle là công cụ mô hình hóa và thực thi công việc build, test, packaging, publishing của dự án. Kết hợp hai công cụ đúng cách giúp một pull request tự động được biên dịch và kiểm thử bằng môi trường có thể tái tạo, trả status check cho người review, giữ báo cáo test khi lỗi, đóng gói artifact khi thành công và hạn chế nguy cơ truy cập secrets trong các pull request không đáng tin.

Bài Knowledge thuộc phần **Tích hợp CI/CD** của *Build Tool Gradle*, tập trung vào đề bài **“Xây dựng workflow Gradle trên GitHub Actions”**. Nội dung dùng **Java 17, Gradle Kotlin DSL, Gradle Wrapper, JUnit 5 và GitHub-hosted Ubuntu runner**, kèm file YAML đầy đủ, output dự kiến, lệnh chạy local, cache policy, artifact upload, dependency submission, matrix, release security, lỗi phổ biến và bài tập. GitHub Actions versions được đối chiếu theo tài liệu hiện hành tháng 11/2026: `actions/checkout@v7`, `actions/setup-java@v6`, `gradle/actions/setup-gradle@v6`, `actions/upload-artifact@v7`, `gradle/actions/dependency-submission@v6`. Với production, ưu tiên **pin full verified commit SHA** hoặc GitHub Actions dependency lockfile thay vì phụ thuộc vô điều kiện vào major tags.

## 1. Kiến trúc CI: GitHub điều phối, Gradle thực thi task

~~~text
Push to main / Pull request / Manual trigger
                  |
                  v
.github/workflows/gradle-ci.yml
  on, permissions, concurrency, jobs
                  |
                  v
Job "build" on ubuntu-24.04
  actions/checkout  -> tải code
  actions/setup-java -> JDK 17
  gradle/actions/setup-gradle -> Wrapper checks + cache
                  |
                  v
        ./gradlew build distZip
                  |
             Gradle task graph
  compileJava, processResources, compileTestJava,
  test, check, jar, distZip, assemble, build
                  |
                  v
         Exit status + test reports
                  |
                  v
    Upload report and distribution artifacts
                  |
                  v
      PR status check / branch protection
~~~

Một GitHub Actions **workflow** là một YAML file trong `.github/workflows/`. Nó có event triggers, một hoặc nhiều **jobs**, mỗi job chạy trên **runner** với nhiều **steps**. Step có thể dùng một reusable **action** (`uses: ...`) hoặc shell command (`run: ...`).

Một **Gradle task** khác với một GitHub Actions job. `:test` là task trong Gradle build; `build` là job name trong YAML. Job có thể gọi nhiều Gradle tasks, còn Gradle quản lý dependencies/order giữa các tasks.

| Tầng | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| GitHub event | `pull_request` | Khi nào kiểm thử code |
| GitHub job | `jobs.build` | Runner, permissions, steps |
| Action step | `actions/setup-java@v6` | Cài và chọn JDK |
| Shell step | `run: ./gradlew build` | Gọi công cụ build |
| Gradle Wrapper | `./gradlew` | Chọn Gradle distribution của repo |
| Gradle task | `test`, `distZip` | Biên dịch, test, package |
| Workflow artifact | Uploaded ZIP/report | Lưu tệp để download hoặc chuyển giữa jobs |

**Không nên viết lại chuỗi `javac`/`java`/JUnit command dài trong workflow nếu Gradle đã mô tả chúng.** Khi đó local và CI sẽ có hai cấu hình classpath/test khác nhau, khó tái lập lỗi.

## 2. Chuẩn bị dự án Java 17 đủ để kiểm thử pipeline

Trước khi viết CI, cần biết `./gradlew build` đã chạy được ở máy phát triển. Ví dụ sau gồm application và hai unit tests thật, để GitHub Actions có một kết quả có ý nghĩa.

### Cây thư mục

~~~text
hello-actions/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── src/
│   ├── main/java/demo/app/
│   │   ├── Greeting.java
│   │   └── Main.java
│   └── test/java/demo/app/
│       └── GreetingTest.java
└── .github/
    └── workflows/
        └── gradle-ci.yml
~~~

Dự án yêu cầu JDK 17 toolchain và Gradle Wrapper tương thích. Maven Central cần truy cập ở lần resolve JUnit dependencies đầu tiên. Không tạo thủ công `gradle-wrapper.jar`; Wrapper phải được Gradle tạo và kiểm tra nguồn gốc.

### `settings.gradle.kts`

~~~kotlin
rootProject.name = "hello-actions"
~~~

### `build.gradle.kts` — toàn bộ file

~~~kotlin
plugins {
    application
}

group = "dev.learning"
version = "1.0.0"

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.14.3"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}

application {
    mainClass.set("demo.app.Main")
}
~~~

`application` là core Gradle plugin; nó áp dụng Java plugin, tạo các tasks `run`, `distZip`, `distTar` và Java lifecycle. `java.toolchain` yêu cầu JDK 17 cho Java tasks. JUnit BOM `5.14.3` quản lý các phiên bản JUnit Jupiter/Platform nhất quán, `junit-platform-launcher` được dùng khi thực thi tests qua Gradle, còn `useJUnitPlatform()` kích hoạt test engine phù hợp.

`mavenCentral()` là **repository để tải dependencies**, không phải đích upload artifact. Application plugin tạo distribution ZIP, không tự tạo một GitHub Release hay Maven publication.

### `src/main/java/demo/app/Greeting.java`

~~~java
package demo.app;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is blank");
        }
        return "Hello, " + name + "!";
    }
}
~~~

### `src/main/java/demo/app/Main.java`

~~~java
package demo.app;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.message("Actions"));
    }
}
~~~

### `src/test/java/demo/app/GreetingTest.java`

~~~java
package demo.app;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

public final class GreetingTest {

    @Test
    void formatsGreeting() {
        assertEquals(
            "Hello, Actions!",
            Greeting.message("Actions")
        );
    }

    @Test
    void rejectsBlankName() {
        assertThrows(
            IllegalArgumentException.class,
            () -> Greeting.message("   ")
        );
    }
}
~~~

Hai tests có assertions thực. Một test bảo đảm kết quả của public API, một test xác nhận đầu vào sai bị từ chối.

### Kiểm tra trên máy phát triển

Linux/macOS:

~~~bash
./gradlew --version
./gradlew clean test
./gradlew run --quiet
./gradlew build distZip
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test
.\gradlew.bat run --quiet
.\gradlew.bat build distZip
~~~

**Stdout đúng do Java Main in ra:**

~~~text
Hello, Actions!
~~~

Gradle sẽ có task logs riêng; chỉ chuỗi trên là output từ `Main.main()`. Khi build PASS, kiểm tra các output dự kiến:

~~~text
build/libs/hello-actions-1.0.0.jar
build/distributions/hello-actions-1.0.0.zip
build/reports/tests/test/index.html
build/test-results/test/TEST-demo.app.GreetingTest.xml
~~~

Paths trên là **đường dẫn dự kiến** với demo này. `distZip` chứa scripts và libraries cho distribution; main JAR riêng chưa chắc chạy được bằng `java -jar` vì Application plugin không tự bảo đảm runnable fat JAR/manifest cho mọi cấu hình.

## 3. Gradle Wrapper là source of truth của CI

Hai lệnh khác nhau:

~~~bash
gradle build
./gradlew build
~~~

Lệnh đầu sử dụng Gradle installation trên `PATH`. Lệnh sau chạy Wrapper script từ repository và tải/chọn Gradle distribution đã chỉ định trong `gradle/wrapper/gradle-wrapper.properties`.

Với CI, ưu tiên **`./gradlew`**:
- Local và runner dùng cùng Gradle version.
- PR nâng Gradle Wrapper có thể được review rõ.
- Không phụ thuộc phiên bản Gradle mặc định của runner.
- Có thể kiểm chứng Wrapper JAR và distribution checksums.

Bốn Wrapper files quan trọng thường cần commit: `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar` và `gradle/wrapper/gradle-wrapper.properties`.

Nếu chưa có Wrapper, dùng Gradle đã cài phù hợp để bootstrap một lần:

~~~bash
gradle wrapper --gradle-version 9.9.0 --distribution-type bin
~~~

Sau đó chạy `./gradlew --version`, kiểm tra những file do Gradle tạo và commit. Đây là **bước tạo Wrapper tại local**, không phải step CI tự viết wrapper JAR.

### Executable bit trên Linux

Nếu CI báo `./gradlew: Permission denied`, file có thể chưa được lưu executable bit vào Git. Tạm thời, workflow có thể dùng:

~~~bash
chmod +x ./gradlew
~~~

Giải pháp bền vững là sửa permission của `gradlew` trong Git, không dùng `sudo` hoặc cấp root cho build chỉ vì thiếu executable bit.

### Hai lớp xác minh Wrapper

- **Wrapper JAR validation**: kiểm tra `gradle-wrapper.jar` có checksum chính thống. `gradle/actions/setup-gradle@v6` tự làm mặc định.
- **Gradle distribution ZIP validation**: dùng `distributionSha256Sum` trong `gradle-wrapper.properties` nếu được cấu hình, với SHA-256 thực lấy từ nguồn phát hành Gradle đáng tin.

Hai việc khác nhau; không bịa SHA-256 và không giả định chỉ sửa `distributionUrl` là đủ để upgrade Wrapper an toàn.

## 4. Workflow tối thiểu

Tạo `.github/workflows/gradle-ci.yml`:

~~~yaml
name: Gradle CI

on:
  push:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - uses: gradle/actions/setup-gradle@v6

      - run: ./gradlew build
~~~

Đây là workflow YAML tối thiểu, chạy khi có `push` hoặc `pull_request`, cài Temurin 17, thiết lập Gradle và gọi Wrapper.

`setup-gradle` **không tự chạy `build`**: bạn vẫn cần bước `run`. Đồng thời `setup-java` chỉ cấp JDK cho runner; Gradle toolchain và Java build vẫn được kiểm soát trong `build.gradle.kts`.

Bản tối thiểu đủ thử nhưng chưa có least privilege, cache policy, report upload hay hủy các PR runs cũ. Phần kế tiếp là bản phù hợp hơn để bắt đầu CI thật.

## 5. Workflow hoàn chỉnh: build, test, report, distribution

Đây là **nội dung đầy đủ** của `.github/workflows/gradle-ci.yml` cho demo Java ở phần 2:

~~~yaml
name: Java Gradle CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: gradle-ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

jobs:
  build:
    name: verify-java17
    runs-on: ubuntu-24.04
    timeout-minutes: 25

    steps:
      - name: Checkout
        uses: actions/checkout@v7
        with:
          persist-credentials: false

      - name: Set up Java
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - name: Setup Gradle
        uses: gradle/actions/setup-gradle@v6
        with:
          cache-provider: basic
          cache-read-only: ${{ github.event_name == 'pull_request' }}

      - name: Make Gradle Wrapper executable
        run: chmod +x ./gradlew

      - name: Display Java and Gradle versions
        run: |
          java -version
          ./gradlew --version

      - name: Build, test, create ZIP
        run: ./gradlew --no-daemon build distZip --stacktrace

      - name: Upload JUnit test reports
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: test-reports-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            build/reports/tests/test/
            build/test-results/test/
          if-no-files-found: ignore
          retention-days: 7

      - name: Upload application distribution
        if: ${{ success() }}
        uses: actions/upload-artifact@v7
        with:
          name: hello-actions-${{ github.run_id }}-${{ github.run_attempt }}
          path: build/distributions/*.zip
          if-no-files-found: error
          retention-days: 14
~~~

Lưu ý: `main` là branch name dùng trong bài; nếu repository dùng branch khác, đổi đúng tên. GitHub Actions interpolation trong YAML có dạng `$` theo sau biểu thức trong hai cặp dấu ngoặc nhọn (ví dụ `if:` và `concurrency.group` ở trên); đây là **GitHub Actions expression**, không phải Kotlin DSL.

### Từng nhóm bước giải quyết vấn đề gì?

**Trigger:** `push` trên main, `pull_request` nhắm main và `workflow_dispatch` cho người có quyền chạy thủ công. `pull_request` thích hợp kiểm thử code chưa merge theo cơ chế hạn chế secrets của GitHub.

**Permissions:** `contents: read` là mức tối thiểu cho checkout/test. Không cấp `packages: write`, `id-token: write` hoặc `contents: write` cho job PR build nếu không có nhu cầu thực.

**Concurrency:** hủy runs cũ trên cùng PR ref để tiết kiệm runner minutes. Với push main, biểu thức trên không tự hủy một build đang chạy; policy có thể điều chỉnh.

**Checkout:** `persist-credentials: false` tránh lưu lại checkout token trong Git configuration sau step, giảm rủi ro một task không mong muốn sử dụng token đó.

**JDK:** setup-java chọn Temurin 17, đặt `JAVA_HOME`/`PATH`. Gradle `java.toolchain=17` vẫn là contract tại build script.

**Gradle action:** `setup-gradle@v6` thiết lập môi trường/cache và mặc định validate Gradle Wrapper JAR.

**Build:** `./gradlew --no-daemon build distZip --stacktrace` chạy Gradle lifecycle. `--no-daemon` hạn chế daemon reuse, nhưng Gradle vẫn có thể dùng single-use daemon nếu JVM args yêu cầu. Nó không tắt Gradle Build Cache.

**JUnit reports:** `if: always()` giúp upload report nếu `test` fail sau khi tạo XML/HTML. `if-no-files-found: ignore` tránh thêm lỗi upload nếu build đã fail trước khi test chạy. Reports có thể chứa stacktraces/đường dẫn nội bộ, nên cân nhắc privacy ở public repository.

**Distribution ZIP:** chỉ upload khi job đến đây trong trạng thái thành công; `if-no-files-found: error` bảo đảm output thiếu không bị bỏ qua. ZIP là **workflow artifact**, không phải Maven publication hay GitHub Release asset.

## 6. Vì sao các actions version trong ví dụ là v7/v6?

Tại thời điểm biên soạn cuối năm 2026, tài liệu chính thức của Gradle sử dụng `gradle/actions/setup-gradle@v6`; tài liệu hiện hành của các GitHub-maintained actions giới thiệu `actions/checkout@v7`, `actions/setup-java@v6`, `actions/upload-artifact@v7`.

Các phiên bản action có thể phụ thuộc **Node runtime trên GitHub Actions runner**. GitHub-hosted runners được cập nhật, nhưng **self-hosted runner** có thể phải upgrade để dùng các action major mới. Đừng thay tag ngẫu nhiên khi một job fail: xem action release notes, runner version và chính sách GHES trước.

**Security:** major tag như `@v7` có thể được cập nhật. GitHub có cơ chế Actions dependency lockfiles và khuyến nghị pin verified full commit SHA nếu chưa dùng lockfile. Với tutorial, major tags giúp đọc ngắn; với production, review/trust action source và pin theo policy.

## 7. Caching trong GitHub Actions khác caching trong Gradle

Đây là điểm dễ gây ngộ nhận nhất.

| Tầng cache | Tác dụng | Ai quản lý? |
| --- | --- | --- |
| GitHub Actions cache | Khôi phục Gradle User Home cache giữa runners/jobs | GitHub cache + `setup-gradle` |
| Gradle dependency cache | Lưu artifact và dependency metadata được resolve | Gradle |
| Gradle Build Cache | Lưu/phục hồi **cacheable task outputs** | Gradle |
| Gradle up-to-date checks | Skip task action khi local inputs/outputs hợp lệ | Gradle |
| Gradle Configuration Cache | Reuse configured task graph/configuration state | Gradle |
| GitHub uploaded artifact | Lưu ZIP/JUnit report để download | GitHub Actions Artifact service |

`gradle/actions/setup-gradle` cache một số nội dung `GRADLE_USER_HOME` như distribution, dependencies và build-cache files theo provider/cache policy. Điều đó **không tự làm `test` hay `compileJava` báo `UP-TO-DATE`** trên một ephemeral runner chưa có `build/` tại workspace.

Để Gradle sử dụng task output caching có chủ đích:

~~~properties
# gradle.properties
org.gradle.caching=true
~~~

hoặc:

~~~bash
./gradlew build --build-cache
~~~

Chỉ tasks có cacheability đúng mới có thể `FROM-CACHE`; task `UP-TO-DATE` nghĩa local output hiện có phù hợp, không cần restore cache. `test` cũng có thể chạy vì inputs khác nhau. Không đưa toàn bộ `build/` vào GitHub cache để ép Gradle “nhận output cũ”; hãy để Gradle quản lý task outputs qua Build Cache.

### Enhanced và Basic cache providers trong setup-gradle@v6

Gradle Actions v6 cung cấp:

- `cache-provider: enhanced`: backend enhanced, mặc định trong các release v6 hiện hành; có licensing/privacy/availability policy tùy loại repository.
- `cache-provider: basic`: đường open-source dựa trên GitHub Actions cache.

Workflow mẫu dùng `basic` để rõ ràng và không phụ thuộc lựa chọn enhanced tier. Team có thể benchmark enhanced sau khi xem chính sách. Không mặc định rằng enhanced tier luôn có cùng điều kiện cho mọi private repo.

### Cache read-only cho PR

~~~yaml
with:
  cache-provider: basic
  cache-read-only: ${{ github.event_name == 'pull_request' }}
~~~

Ý định là PR jobs có thể **đọc** cache mà không cập nhật trusted cache entries. `setup-gradle` cũng có default policy chỉ cho default-branch jobs ghi cache trong trường hợp phổ biến. Matrix jobs có thể chọn một canonical writer, các legs còn lại read-only.

**Cache miss không được làm build sai**. Nếu thiếu cache mà CI fail vì cần một file không được khai báo nguồn, đó là vấn đề correctness của build, không phải lý do vô hiệu hóa kiểm tra.

## 8. Không cache Gradle User Home hai lần

`actions/setup-java@v6` cũng hỗ trợ:

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '17'
    cache: gradle
~~~

Đây là **phương án caching thay thế**, không nên ghép thêm nguyên xi với `setup-gradle` đã bật caching. Gradle Actions docs khuyến nghị tránh hai actions cùng restore/save `~/.gradle`, cũng tránh tự `actions/cache` cùng directories khi chưa hiểu cache ownership.

Nếu muốn setup-java làm cache owner và vẫn dùng setup-gradle để validate Wrapper, có thể đặt trong setup-gradle:

~~~yaml
with:
  cache-provider: external
~~~

Đây là **mảnh cấu hình** cho tình huống cache đã được cơ chế bên ngoài quản lý; phải xem action version và chính sách project. Mặc định đơn giản cho Gradle repository là **setup-java cài JDK, setup-gradle quản lý Gradle cache**.

## 9. Configuration Cache có lưu xuyên GitHub runs không?

Configuration Cache lưu trạng thái **configuration phase**, khác Build Cache lưu task outputs. Thử local:

~~~bash
./gradlew help --configuration-cache
./gradlew help --configuration-cache
~~~

Với plugin/build script tương thích và inputs không đổi, lần sau có thể reuse configuration entry. Nhưng ở CI ephemeral runners, muốn **persist configuration cache** qua action cache cần đọc Gradle Actions docs về `cache-encryption-key` và secret security. Ví dụ **mảnh opt-in**:

~~~yaml
- uses: gradle/actions/setup-gradle@v6
  with:
    cache-provider: basic
    cache-encryption-key: ${{ secrets.GRADLE_ENCRYPTION_KEY }}
~~~

Không paste fragment này vào workflow mẫu nếu chưa có key đúng định dạng/base64 AES và secret management. **Fork PR thường không nhận repository secrets**; đừng nâng quyền PR để cache config entry. Một CI đúng phải vẫn build thành công không có configuration cache.

Không nhầm: `--configuration-cache` không bảo đảm mọi tasks `FROM-CACHE`, và `--build-cache` không bảo đảm Gradle sẽ reuse configuration phase.

## 10. Wrapper validation và supply-chain security

Gradle Wrapper là mã được chạy **trước** build logic. Trong CI, `gradle/actions/setup-gradle@v6` mặc định kiểm tra checksum của `gradle-wrapper.jar`. Nếu một repository không dùng setup-gradle, có thể dùng standalone action:

~~~yaml
name: Gradle Wrapper Integrity

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  validate:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v7
      - uses: gradle/actions/wrapper-validation@v6
~~~

Workflow trên **đầy đủ**, nhưng không nhất thiết cần chạy thêm trong cùng job đã dùng setup-gradle để tránh validation trùng. Với monorepo có nhiều Wrapper JARs, standalone action tìm và kiểm tra chúng theo tài liệu.

**Wrapper JAR checksum** khác với `distributionSha256Sum` của Gradle distribution ZIP. Cả hai không thay thế cho việc review Gradle Wrapper upgrades và third-party plugins/dependencies.

### Actions pinning

Do actions là executable code trên runner, lựa chọn tag/SHA/lockfile là một quyết định supply-chain security. Với production, ưu tiên lockfile hoặc verified full-length commit SHA; major tags dễ đọc trong tutorial nhưng không đảm bảo bất biến.

## 11. Khi test fail, job phải fail

Với Java demo:

~~~bash
./gradlew test
~~~

JUnit `test` task chạy hai tests. Nếu `Greeting.message("Actions")` trả giá trị khác `"Hello, Actions!"`, `assertEquals` fail, Gradle task fail và shell command trả nonzero. GitHub job được báo **FAILED**.

Nếu người viết workflow dùng:

~~~yaml
- run: ./gradlew test
  continue-on-error: true
~~~

trong required CI job, workflow có thể **không phản ánh thất bại** theo cách team mong đợi. Đừng thêm `continue-on-error` chỉ để "làm xanh" một test flaky. Cần sửa test, quarantine có quy trình hoặc tách nonblocking experimental checks.

### Test report ở đâu?

Với Java plugin thường là:

~~~text
build/reports/tests/test/index.html
build/test-results/test/TEST-<test class>.xml
~~~

HTML cho người xem; JUnit XML cho CI tool/report aggregator. Nếu test fail sau khi chạy, `if: always()` vẫn cho upload reports, nhưng upload sẽ không tìm thấy file nếu build đã fail trước khi tới `test`. Vì vậy `if-no-files-found: ignore` hợp lý với **diagnostic report**, còn distribution release artifact nên dùng `error`.

### Required status checks

YAML tạo job name, nhưng **không tự bật branch protection**. Maintainer vào GitHub Settings → Branches/Rulesets đặt job `verify-java17` hoặc check phù hợp thành required check. Nếu required check được cấu hình nhầm hoặc workflow bị path-filter skip, PR có thể bị chặn hoặc không được bảo vệ như mong muốn. Kiểm tra bằng một PR test có failure thật.

## 12. GitHub workflow artifact khác Gradle artifact và Maven publication

Ví dụ:

~~~yaml
- uses: actions/upload-artifact@v7
  with:
    name: application-${{ github.run_id }}
    path: build/distributions/*.zip
    if-no-files-found: error
~~~

`upload-artifact` tạo một file download tại GitHub Actions run. Nó **không upload Maven GAV** tới Maven Central, không tạo GitHub Release và không đồng nghĩa `maven-publish`.

- **Gradle output artifact**: file do Gradle task tạo, ví dụ `hello-actions-1.0.0.zip`.
- **GitHub workflow artifact**: bản sao/lưu file cho run, dùng để download/đưa sang job khác.
- **Maven publication**: một module có GAV/POM/artifacts được đưa vào Maven repository qua `publishing`.
- **Release asset**: file gắn với GitHub Release/tag, có release policy riêng.

GitHub upload-artifact v7 có quy tắc **artifact names phải unique khi nhiều jobs cùng upload**; không cho các jobs độc lập append vào cùng artifact name như workflow cũ. Với matrix, gắn thêm matrix dimension; với re-run, có thể gắn `github.run_attempt`.

### Retention và security

`retention-days: 7` giảm lưu trữ report tạm. Không upload `~/.gradle`, plaintext credentials, signing keys hoặc cả source workspace không cần thiết. Trong public repo, logs/reports có thể phơi bày tên nội bộ, stacktraces và environment details; xem policy trước khi công khai.

## 13. Workflow có nhiều jobs: `needs` không chuyển files

Một workflow có `verify` và `package`:

~~~yaml
jobs:
  verify:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v7
      # Setup Java/Gradle...
      - run: ./gradlew test

  package:
    needs: verify
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v7
      # Setup Java/Gradle...
      - run: ./gradlew distZip
~~~

Đoạn trên là **cấu trúc minh họa**, chưa runnable đầy đủ vì thiếu setup-java/setup-gradle và `on`/workflow name. Nó cho thấy **mỗi job có runner/workspace riêng**. `needs: verify` là dependency về thứ tự/trạng thái, **không chuyển `build/` từ job verify sang package**.

Nếu job package cần dùng binary đã tạo tại verify, upload tại verify, dùng `actions/download-artifact` trong package rồi verify artifact provenance. Hoặc build lại với source commit/Gradle Wrapper giống nhau. Đừng coi upload artifact từ untrusted PR là trusted release input.

## 14. Matrix: thử nhiều JDK runtimes

Một dự án có thể muốn chạy Gradle trên JDK 17 và 21, nhưng vẫn compile Java source bằng **Java17 toolchain**. Mảnh thay thế `jobs.build`:

~~~yaml
jobs:
  build:
    runs-on: ubuntu-24.04
    strategy:
      fail-fast: false
      matrix:
        gradleJvm: ['17', '21']

    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: |
            17
            ${{ matrix.gradleJvm }}

      - uses: gradle/actions/setup-gradle@v6
        with:
          cache-provider: basic
          cache-read-only: ${{ matrix.gradleJvm != '17' || github.event_name == 'pull_request' }}

      - run: chmod +x ./gradlew
      - run: ./gradlew --no-daemon build
~~~

Đây là **mảnh job minh họa**, không thay thế toàn bộ `gradle-ci.yml` mà không bổ sung workflow name/events/permissions.

`setup-java` hỗ trợ nhiều JDK versions; JDK cuối trong danh sách thường là default `JAVA_HOME`/`PATH`. Vì JDK17 được cài cả trong leg21, Gradle Java17 toolchain vẫn có compiler17. Khi matrix là 17, có thể xảy ra việc liệt kê version17 hai lần; chỉ là cấu hình thừa, không phải hai loại JDK khác nhau.

**Chạy Gradle bằng JDK21 không đồng nghĩa compile bytecode Java21** nếu project có toolchain17. Muốn kiểm tra **ứng dụng runtime trên JDK21**, cần một bước chạy/test thực sự dùng JDK21, chứ không chỉ đổi JDK chạy Gradle.

### Artifact name trong matrix

Nếu mỗi leg upload ZIP:

~~~yaml
name: app-jdk${{ matrix.gradleJvm }}-${{ github.run_id }}
~~~

Tên có matrix dimension để tránh collisions.

## 15. Monorepo: working directory và build roots

Một repository có:

~~~text
repo/
├── services/order/settings.gradle.kts
├── services/order/gradlew
├── services/payment/settings.gradle.kts
└── services/payment/gradlew
~~~

Không có root `./gradlew`, nên workflow phải chọn đúng Gradle build:

~~~yaml
defaults:
  run:
    working-directory: services/order

steps:
  - uses: actions/checkout@v7
  - uses: actions/setup-java@v6
    with:
      distribution: temurin
      java-version: '17'
  - uses: gradle/actions/setup-gradle@v6
    with:
      build-root-directory: services/order
  - run: chmod +x ./gradlew
  - run: ./gradlew build
~~~

**Đây là mảnh jobs configuration**, không phải file hoàn chỉnh; nó chỉ minh họa cách chọn path. `defaults.run.working-directory` ảnh hưởng tới **run steps**, không tự đổi working directory của `uses` actions. `build-root-directory` là input riêng của Gradle action.

Với một **multi-project build** có root settings + `include("app", "library")`, có thể chạy `./gradlew build` hoặc task paths như `:app:build`, `:library:test`. Cẩn thận khi dùng GitHub `paths` filter: thay đổi `gradle/libs.versions.toml`, `build-logic`, root Wrapper hoặc shared Gradle scripts có thể ảnh hưởng **nhiều modules** chứ không chỉ folder vừa sửa.

## 16. Dependency graph và Dependabot: tách quyền ghi

Gradle Actions cung cấp `gradle/actions/dependency-submission@v6` để resolve Gradle dependency graph và gửi snapshot vào GitHub Dependency Submission API. Điều đó hỗ trợ Dependency Graph/Dependabot alerts nếu repository settings đã bật phù hợp.

**Không cấp `contents: write` cho mọi PR build chỉ vì muốn submit graph**. Với `setup-gradle@v6`, dependency graph submission **không phải mặc định tự động**; có thể dùng action riêng.

File `.github/workflows/gradle-dependencies.yml`:

~~~yaml
name: Gradle Dependency Submission

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: write

jobs:
  submit:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - uses: gradle/actions/dependency-submission@v6
~~~

Đây là một **workflow đầy đủ**, nhưng cần repository cho phép GitHub Dependency Graph/API và đủ quyền token. `contents: write` gắn với **trusted main push/manual workflow**, không mang sang `pull_request` của fork.

Nếu dự án có private dependency repositories, graph submission action cũng cần resolve dependencies; chỉ cấp credentials vào trusted jobs với secret restrictions phù hợp. Action có filters cho subprojects/configurations khi monorepo quá lớn hoặc có configurations không nên xuất.

## 17. CI và CD không nên chung một quyền

CI build/test dùng `contents: read`. CD publish Maven package/release cần quyền khác:

- `packages: write` khi publish tới GitHub Packages qua `GITHUB_TOKEN`.
- `id-token: write` nếu release job dùng OIDC nhận short-lived credentials từ cloud provider.
- Secrets riêng khi registry chỉ hỗ trợ username/token.
- Protected tags/branches và GitHub Environment approval khi release production.
- Version/tag/repository ownership, signing, immutable release policy.

Một **fragment** cho job publish:

~~~yaml
jobs:
  publish:
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-24.04
    environment: production
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
      - uses: gradle/actions/setup-gradle@v6
        with:
          cache-provider: basic
          cache-read-only: true
      - run: chmod +x ./gradlew
      - run: ./gradlew build
      - name: Publish
        env:
          ORG_GRADLE_PROJECT_registryUser: ${{ github.actor }}
          ORG_GRADLE_PROJECT_registryToken: ${{ secrets.GITHUB_TOKEN }}
        run: ./gradlew publish
~~~

Đây là **mảnh CD job, không chạy được trên demo Java nếu chưa khai báo `maven-publish`/`publishing.repositories` và registry credential mapping**. Workflow chứa job này cần trigger tags/release phù hợp, Gradle MavenPublication, đúng registry URL và GitHub security approvals. Đừng cho rằng dùng `./gradlew publish` là tự lên Maven Central hoặc GitHub Release.

**Không dùng một untrusted PR artifact làm đầu vào thực thi trực tiếp trong job có production secrets**. GitHub docs gọi kiểu nâng quyền chạy code PR không tin cậy này là “pwn request”.

## 18. Pull request security: `pull_request` khác `pull_request_target`

Build scripts trong PR là **mã chạy được**. Một PR độc hại có thể sửa `build.gradle.kts`, tests hoặc plugins để đọc `System.getenv` hoặc gửi token qua network.

`pull_request` thường chạy code PR trong trust model hạn chế: token read-only cho fork PR, secrets không được cấp; GitHub còn có fork approval policies. Nó phù hợp để chạy compile/test không cần secrets.

`pull_request_target` chạy workflow từ base repository với trust cao hơn, có thể nhận base repo token/secrets. **Không được checkout untrusted fork head rồi chạy `./gradlew build` trong privileged job**. Hãy dùng event phù hợp, tách metadata-only tasks (label/comment) khỏi code execution và dùng GitHub security docs để kiểm tra.

Tương tự, `workflow_run` có thể chạy trong privileged context; nếu tải và thực thi artifact từ một untrusted PR run mà không có trust validation, đó là lối vòng nguy hiểm.

Các nguyên tắc:

1. Dùng `permissions: contents: read` ở PR CI.
2. Không cung cấp registry deploy keys/signing keys cho PR workflows.
3. Cấp `packages: write` và `id-token: write` chỉ cho trusted release jobs khi cần.
4. Dùng GitHub Environments với required reviewers cho production.
5. Với third-party actions, review source và pin SHA/lockfile.
6. Không nhúng untrusted PR title/branch name trực tiếp vào shell `run` expression; dùng env/action inputs có kiểm soát.
7. Self-hosted runners cho PR không đáng tin phải cô lập/ephemeral, không mở private network tùy ý.
8. Không upload toàn bộ `~/.gradle` hoặc credential files vào artifacts.

## 19. GitHub Actions caching và Build Scans

`setup-gradle` có thể đưa Gradle invocation summary vào GitHub job summary. Nếu build có publish Build Scan và tổ chức cho phép, summary có thể chứa link để phân tích task performance.

Để bật **Build Scan publish** có chủ đích:

~~~yaml
- uses: gradle/actions/setup-gradle@v6
  with:
    build-scan-publish: true
    build-scan-terms-of-use-url: "https://gradle.com/terms-of-service"
    build-scan-terms-of-use-agree: "yes"
~~~

Đây là **mảnh opt-in**, không nằm trong workflow mẫu; xem điều khoản, privacy và loại dữ liệu trước khi bật. Với private Develocity server, sử dụng access key và policy riêng. Không giả định mọi build có `setup-gradle` đều tự gửi Build Scan lên server công khai.

Nếu PR build chậm, đo:
- Runner startup và Java/Gradle download time.
- Dependency resolution.
- Gradle configuration vs task execution.
- Task `UP-TO-DATE`/`FROM-CACHE`/`EXECUTED`.
- JUnit test duration.
- Artifact compression/upload time.
- Matrix fanout và concurrency cancellation.

Không tắt tests, wrapper validation hay secret protections để tăng tốc.

## 20. Các flags Gradle trong workflow và ý nghĩa thật

| Flag/task | Có ý nghĩa gì | Không có nghĩa |
| --- | --- | --- |
| `--no-daemon` | Hạn chế Gradle daemon reuse | Không tắt Build Cache hoặc single-use daemon mọi trường hợp |
| `--stacktrace` | In stacktrace khi lỗi | Không tự sửa lỗi |
| `--info` | Chi tiết diagnostic về tasks/dependencies | Không nên public log không được lọc |
| `--build-cache` | Bật task output cache | Không khiến mọi task cacheable |
| `--configuration-cache` | Bật/reuse configuration state khi hỗ trợ | Không lưu task outputs thay Build Cache |
| `--rerun-tasks` | Ép rerun tasks, bỏ skip/cache thông thường | Không sửa thiếu input/output declarations |
| `clean` | Xóa build outputs | Không nên dùng trong mọi warm-cache benchmark |
| `test` | Chạy Test task nếu plugin/source set đã đăng ký | Không tự tạo custom integrationTest |
| `build` | Lifecycle của plugin: check + assemble | Không có nghĩa deploy lên môi trường |
| `distZip` | Đóng Application distribution ZIP | Không publish Maven module |
| `publish` | Publishing tasks do plugin/config đã khai báo | Không tự tạo GitHub Release |

**Không viết `./gradlew --scan` trong mọi PR job rồi mặc định cho Build Scan được public** nếu chưa đồng ý policy. Với Gradle v9, xem docs về Develocity/Build Scan configuration và Gradle Actions setup.

## 21. Debug workflow theo từng tầng

| Triệu chứng | Khả năng nguyên nhân | Kiểm tra/sửa |
| --- | --- | --- |
| Không thấy workflow | YAML path/trigger | File ở `.github/workflows`, branch filters, Actions enabled |
| Job đang chờ runner | Runner/quota/policy | `runs-on` label, limits, self-hosted capacity |
| `Action not found` | Action tag/policy | Verified action refs, organization allowed-actions |
| `./gradlew: Permission denied` | Executable bit | `chmod +x`, commit executable file mode |
| `./gradlew: not found` | Sai directory | Checkout, wrapper files, working-directory |
| Wrapper validation fails | JAR checksum không hợp lệ | Tạo lại từ official Wrapper và review |
| Gradle download fails | URL/proxy/TLS | Distribution URL, network, certificates |
| Wrong Java version | `setup-java`/toolchain | `java -version`, `./gradlew --version`, `javaToolchains` |
| `Unsupported class file major version` | Gradle/JDK/plugin incompatibility | Compatibility matrix, update Wrapper/plugin |
| JUnit 0 tests | Launcher/engine/source set | `useJUnitPlatform` và test dependencies |
| Test pass local, fail Ubuntu | OS-specific behavior | Paths/case, timezone, locale, encoding |
| `distZip` not found | Application plugin chưa áp dụng | `tasks --all`, plugin/root project đúng |
| Artifact upload no files | Wrong path, task missing | `build/distributions`, `if-no-files-found` |
| Report upload skipped | Step `if` không đúng | `if: always()` và thứ tự steps |
| Artifact name collision | Matrix/jobs trùng tên | Thêm matrix dim, job/run ID |
| Cache never hits | Scope/keys/branch read-only | setup-gradle cache logs, input changes |
| `FROM-CACHE` không xuất hiện | Task output locally up to date hoặc cache disabled | Gradle `--info`, cacheability, task outputs |
| Dependency resolution 401 | Private repository auth | Only trusted job secrets, Gradle repositories |
| Dependency submission 403 | API permission/settings | `contents: write` trong trusted job, graph enabled |
| Publishing 403 | Registry credentials | `packages: write`/token scopes, registry URL |
| Self-hosted action Node error | Runner cũ | Upgrade runner per action release notes |

Nếu build thất bại, phân loại: **GitHub trigger**, **runner setup**, **Gradle wrapper**, **JDK**, **dependency resolution**, **Gradle task**, **JUnit assertion**, **artifact upload**, hay **permission/security**. Cùng một dòng `exit code 1` không đủ để xác định nguyên nhân.

### Lệnh hữu ích tại CI hoặc local

~~~bash
java -version
./gradlew --version
./gradlew tasks --all
./gradlew test --info
./gradlew build distZip --stacktrace
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Nếu cần tra dependency cụ thể:

~~~bash
./gradlew dependencyInsight \
  --configuration testRuntimeClasspath \
  --dependency junit-jupiter
~~~

Dấu `\` nối dòng là ví dụ cho Bash; PowerShell có syntax khác, tốt nhất chạy trên một dòng. Không paste output chứa credentials hoặc internal repository URLs lên public issue mà chưa lọc.

## 22. Quy trình CI review trước khi merge

1. **Local correctness:** `./gradlew clean build distZip` PASS và Java stdout đúng.
2. **Wrapper integrity:** commit đủ files, đúng Gradle version, validate Wrapper JAR/distribution checksums.
3. **Workflow syntax:** file YAML đặt đúng path, events, indent, steps/permissions hợp lệ.
4. **Trusted actions:** version/SHA/lockfile theo policy; self-hosted runners tương thích action runtime.
5. **JDK compatibility:** JDK17 có mặt cho toolchain; Gradle daemon có thể chạy trên JDK được hỗ trợ.
6. **Test quality:** test thực sự chạy, có failure case, không `continue-on-error`.
7. **Report retention:** test XML/HTML được upload nếu fail; không upload secrets.
8. **Output artifact:** `distZip` tạo ZIP; missing ZIP làm fail.
9. **Cache ownership:** một action quản lý Gradle User Home, PR read-only.
10. **Build Cache:** task outputs portable/correct, không ép cache project `build/`.
11. **Configuration Cache:** chỉ bật sau compatibility tests; secret key không lộ.
12. **Permissions:** CI read-only, dependency submission write trong trusted job riêng, release scopes riêng.
13. **PR security:** không chạy fork PR head trong privileged workflow.
14. **Monorepo:** build roots/paths filters bao gồm shared Gradle configs.
15. **GitHub ruleset:** required checks chỉ đúng tên job và được kích hoạt ở các PR tương ứng.
16. **CI cold-start:** build phải PASS khi cache trống và trên clean runner.
17. **Regression:** cố tình làm một unit test fail trên PR thử để chắc chắn job đỏ và report có thể download.
18. **Release policy:** tag/approval/registry creds/publishing setup đầy đủ trước khi bật deploy.

## 23. Bài tập thực hành

### Bài A — Làm test fail để chứng minh CI không “xanh giả”

Trong `GreetingTest.formatsGreeting`, tạm đổi expected string:

~~~java
assertEquals("Hello, Wrong!", Greeting.message("Actions"));
~~~

Đây là **một sửa đổi cố ý tạo lỗi**, chỉ dùng trên branch thực hành, không merge vào main. Chạy:

~~~bash
./gradlew test
~~~

JUnit phải fail. Đưa branch lên PR: GitHub check `verify-java17` phải fail, test report được upload nhờ `always()`, distribution upload phải không chạy. Khôi phục assertion đúng và push lại để kiểm tra check xanh. Nếu workflow vẫn xanh khi JUnit fail, tìm `continue-on-error`, `-x test` hoặc custom lifecycle chưa nối tasks.

### Bài B — So sánh cache

Chạy hai lần:

~~~bash
./gradlew build --no-build-cache
./gradlew build --no-build-cache
~~~

Quan sát `UP-TO-DATE` khi output còn nguyên. Sau đó bật `--build-cache`, thử clean build và xem tasks có thể `FROM-CACHE` khi có cache entry. **Không giả định tất cả tasks đều FROM-CACHE**.

### Bài C — Matrix Java 17/21

Áp dụng matrix snippet trong phần 14 và giải thích vì sao cài cả JDK17 khi Gradle JVM leg là 21. Quan sát `./gradlew --version` và toolchain compile result, phân biệt runtime JDK với target bytecode version.

### Bài D — Nhận diện permission sai

So sánh `permissions: contents: read` của PR job với `contents: write` của dependency-submission job. Tại sao không cấp token write cho mọi PR build? Trả lời dựa trên khả năng Gradle build script là code thực thi.

### Bài E — Monorepo đúng path

Cho `services/order` có Wrapper riêng. Sửa `defaults.run.working-directory`, `setup-gradle.build-root-directory` và artifact upload paths để workflow chạy đúng. Tránh path filter bỏ qua thay đổi shared `build-logic`.

## 24. Câu hỏi tự kiểm tra

**1. `setup-gradle` có tự thực thi `./gradlew build` không?** Không; phải có `run` step.

**2. Vì sao dùng Wrapper thay vì system Gradle?** Để pin Gradle distribution và tái lập local/CI.

**3. `setup-java` và Gradle Java Toolchain khác nhau thế nào?** Setup-java cài/chọn JDK trên runner; Gradle toolchain chọn JDK cho compiler/tasks theo project contract.

**4. `build` có tự upload ZIP lên GitHub Actions artifacts?** Không; cần `actions/upload-artifact`.

**5. Vì sao test report upload dùng `always()`?** Để giữ diagnostics ngay khi Gradle test task fail.

**6. `if-no-files-found: error` phù hợp khi nào?** Khi artifact bắt buộc phải có, ví dụ distribution ZIP sau `distZip`.

**7. Có nên dùng cả `setup-java cache: gradle` và `setup-gradle` cache?** Không mặc định; tránh hai owners cho cùng Gradle User Home.

**8. GitHub Actions cache hit có nghĩa `test` UP-TO-DATE không?** Không; Gradle tự xét inputs/outputs và cacheability.

**9. `cache-provider: basic` có mục đích gì?** Chọn caching path open-source qua GitHub Actions cache thay enhanced backend.

**10. Vì sao PR job chỉ có `contents: read`?** Nó cần checkout/build/test, không cần ghi packages/repository.

**11. `pull_request_target` chạy code của fork với secrets có an toàn không?** Không; nguy cơ privileged code execution/pwn request.

**12. Tại sao dependency submission có workflow riêng?** Nó cần quyền `contents: write` và trusted context, không nên nâng toàn bộ PR CI.

**13. `needs` có chuyển `build/distributions` từ job A sang job B không?** Không; jobs có workspaces riêng, cần artifact transfer hoặc build lại.

**14. Làm sao xác định CI đã chạy JUnit tests thật?** Xem `test` outcome, test reports và thử một assertion cố tình fail.

**15. Vì sao `distZip` không tương đương Maven publication?** ZIP là Gradle output; Maven publication cần GAV/metadata/repository qua publishing plugin.

**16. Có nên tạo GitHub Release từ mọi PR artifact?** Không; release cần trusted commit/tag/approval, checks, signing/policy.

**17. Khi nào dùng Configuration Cache encryption key?** Khi muốn persist Configuration Cache trong GitHub cache theo Gradle Actions requirements; bảo quản key bằng GitHub secrets.

**18. Vì sao matrix cần artifact names khác nhau?** GitHub Actions artifact names phải unique khi nhiều jobs cùng upload.

## 25. Checklist cuối cùng

- [ ] Workflow ở `.github/workflows/gradle-ci.yml` và trigger đúng branch.
- [ ] Job `build` có `runs-on` runner có thể dùng và timeout hợp lý.
- [ ] `permissions: contents: read` cho PR CI.
- [ ] `actions/checkout` dùng revision phù hợp, không giữ credential nếu không cần.
- [ ] `actions/setup-java` chọn Temurin 17 và toolchain Gradle tương thích.
- [ ] Wrapper JAR/scripts/properties đầy đủ, có executable bit đúng.
- [ ] `gradle/actions/setup-gradle@v6` validate Wrapper và quản lý caching.
- [ ] Không dùng duplicate Gradle User Home cache owners.
- [ ] `cache-read-only` phù hợp với PR/non-primary matrix legs.
- [ ] `./gradlew build distZip` chạy từ đúng working directory.
- [ ] `useJUnitPlatform()`, JUnit runtime launcher và tests được cấu hình đúng.
- [ ] Test failure làm check fail; test report vẫn được upload.
- [ ] Distribution ZIP được upload chỉ khi build pass và path đúng.
- [ ] Artifact names không trùng giữa jobs/matrix/retries.
- [ ] Build Cache/Configuration Cache/Actions cache được phân biệt.
- [ ] Không đưa secrets vào logs, test artifacts hoặc cache.
- [ ] Dependency Submission chạy trong trusted context và chỉ nó có `contents: write`.
- [ ] Release job được tách scope/secrets/approval, không chạy trên untrusted PR.
- [ ] Workflow action dependencies pin SHA/lockfile theo tổ chức.
- [ ] Self-hosted runners đã upgrade tương thích với action Node runtime.
- [ ] Branch protection yêu cầu đúng status check.
- [ ] Cold build trên runner không có cache vẫn thành công.
- [ ] Không upload toàn bộ `~/.gradle` làm downloadable artifact.
- [ ] Build Scan chỉ publish nếu đã duyệt privacy/terms.

## 26. Tài liệu chính thức

- [Gradle — Gradle on GitHub Actions](https://docs.gradle.org/current/userguide/github-actions.html): setup-gradle v6, wrapper validation, dependency graph, caching, matrix và Build Scan.
- [Gradle Actions repository](https://github.com/gradle/actions): action IDs, cache providers, wrapper and dependency-submission actions.
- [Gradle Actions setup-gradle guide](https://github.com/gradle/actions/blob/main/docs/setup-gradle.md): cache-read-only, basic/enhanced/external providers và Configuration Cache key.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): version, executable scripts, distribution checksum và upgrade.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): JDK selection và compiler/runtime compatibility.
- [Gradle — Testing in Java](https://docs.gradle.org/current/userguide/java_testing.html): Test task, reports, JUnit Platform.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): task output cache.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration state reuse và requirements.
- [GitHub — Workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax): events, jobs, permissions, concurrency, expressions, matrix, needs.
- [GitHub — Building and testing Java with Gradle](https://docs.github.com/en/actions/tutorials/build-and-test-code/java-with-gradle): CI pattern.
- [GitHub — actions/checkout](https://github.com/actions/checkout): checkout action và revision policy.
- [GitHub — actions/setup-java](https://github.com/actions/setup-java): JDK and dependency caching options.
- [GitHub — actions/upload-artifact](https://github.com/actions/upload-artifact): immutability, retention và file missing policy.
- [GitHub — Securely using pull_request_target](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target): untrusted PR code và secret handling.
- [GitHub — Security for GitHub Actions](https://docs.github.com/en/actions/how-tos/secure-your-work): action dependencies lockfiles, pinning, OIDC.
- [GitHub — Dependency Submission API](https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/using-the-dependency-submission-api): dependency snapshots.
- [JUnit 5.14.3 User Guide](https://docs.junit.org/5.14.3/user-guide/): Jupiter assertions/test engine/launcher.
