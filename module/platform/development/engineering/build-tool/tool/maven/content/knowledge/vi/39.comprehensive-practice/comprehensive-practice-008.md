# Thiết kế chuỗi CI có cache, báo cáo và artifact truy vết được bằng Maven

## 1. Bài thực hành tổng hợp: mục tiêu và điều kiện đạt

Một lệnh `mvn clean verify` chạy thành công là điều kiện cần, nhưng **chưa đủ** để có quy trình CI đáng tin. Người nhận một file JAR phải xác định được: nó được build từ **commit nào**, bằng **Maven/JDK nào**, tests nào đã chạy, có báo cáo gì nếu tests thất bại, file đã tải về có đúng **bytes được kiểm tra** không, và bản đó còn được lưu ở đâu.

Bài thực hành tổng hợp này sử dụng **Java 17, Maven Wrapper và GitHub Actions** để dựng chuỗi:

**Checkout → JDK/Dependency cache → clean verify → Surefire reports → binary stage + metadata + SHA-256 → upload artifact → download/verify bundle → optional attestation/release.**

Các nguyên tắc tương tự áp dụng cho GitLab CI, Jenkins hoặc Azure Pipelines dù YAML/commands khác.

**Đầu ra cần có:**

- Maven project Java 17 có POM, Wrapper và các JUnit 5 tests **được chạy thật**.
- Cache dependency giúp giảm thời gian tải mà không làm tests bị bỏ qua.
- Báo cáo `target/surefire-reports` còn truy cập được kể cả khi Maven tests FAIL.
- Binary JAR chỉ được upload khi quality gate PASS.
- Gói binary chứa JAR, POM, Wrapper properties, Maven/JDK version, `BUILD-INFO.txt` và `SHA256SUMS`.
- Manifest có GAV, repository, ref, event, trigger/checkout SHA, run ID, **run attempt** và run URL.
- Job độc lập tải đúng gói artifact cùng workflow run rồi chạy `sha256sum --check`.
- Job summary có status, test counts, link/digest của binary artifact nếu có.
- Không cấp publish/secrets/OIDC cho untrusted pull requests.
- Phân biệt **cache**, **artifact**, **checksum**, **provenance attestation** và **reproducible build**.

Bài xây một dự án nhỏ tự đủ để có thể copy nội dung và chạy. Các versions được **ghim cho ví dụ**, không phải khẳng định chúng luôn mới nhất.

## 2. Định nghĩa ba loại dữ liệu dễ nhầm

| Loại | Nằm ở đâu? | Dùng để làm gì? |
| --- | --- | --- |
| Maven dependency cache | Local repository (thường `~/.m2/repository`) | Tái dùng POM/JAR/plugin đã download |
| Test reports | `target/surefire-reports/` | Xem tests run/failure/error/skipped |
| Binary artifact bundle | GitHub Actions artifact hoặc release repository | Phân phối đúng JAR + metadata + hash |

Cache là **input optimization**, không phải chứng cứ source hiện tại đã PASS. Reports là **diagnostic outputs**, cần giữ lúc thất bại. Binary là **build output** phải bị chặn nếu gate FAIL.

Một run có **cache hit nhưng test fail** vẫn phải có CI status FAILED, report artifact (nếu XML đã tạo), **không có verified binary**. Ngược lại, cache trống không làm hỏng tính đúng đắn nếu Maven vẫn tải được mọi dependency từ trusted repositories.

## 3. Định nghĩa truy vết và integrity

Một artifact “truy vết được” có ít nhất:

1. **Source identity**: repository, commit thực đã checkout, event và ref.
2. **Build identity**: Maven/JDK version, workflow name, run ID, run attempt.
3. **Output identity**: Maven GAV, JAR filename, SHA-256, artifact ID/URL.
4. **Quality evidence**: test reports và trạng thái verify/check-bundle.
5. **Access/retention**: repository lưu binary, hạn lưu và người được phép tải.

**SHA-256 chỉ xác minh integrity khi bạn tin nguồn hash.** Nếu attacker thay cả JAR lẫn checksum, một phép `sha256sum -c` có thể PASS. Signed artifact attestation giúp ràng buộc binary digest với builder identity đã xác thực; bản thân attestation không thay code review, security scan, license approval hay quy trình release.

**Reproducibility** lại là khái niệm khác: hai lần build độc lập từ inputs tương đương phải tạo cùng binary digest. Việc có manifest/sha không tự chứng minh điều đó.

## 4. Luồng CI nên nhìn như một state machine

~~~text
Push / Pull Request
        |
        v
Checkout source
        |
        v
Setup Java 17 + Maven caches
        |
        v
./mvnw -B -ntp clean verify
        |
     +--+--+
     |     |
    PASS  FAIL
     |     |
     |     +------> Upload Surefire reports if available
     |                     |
     |                  JOB RED
     v
Summarize tests & upload reports
     |
     v
Stage JAR + POM + toolchain + BUILD-INFO
     |
     v
Compute file SHA256SUMS
     |
     v
Local sha256sum -c PASS?
     |
     v
Upload binary artifact
     |
     v
Job khác: download artifact cùng run
     |
     v
sha256sum -c + GAV check
     |
     v
CI GREEN; binary là release candidate
     |
     v
[Optional trusted attestation / protected publish]
~~~

Nếu Compiler fail trước tests thì Surefire reports có thể chưa tồn tại; upload report phải được phép **warning**, không được tạo thành công giả. Nếu binary staging không có file, upload binary phải **error**.

## 5. Phiên bản công cụ và môi trường

Bài chọn:

| Thành phần | Version dùng trong bài |
| --- | --- |
| JDK | 17+ |
| Apache Maven qua Wrapper | 3.9.9 |
| Maven Wrapper Plugin | 3.3.4 |
| Maven Compiler Plugin | 3.13.0 |
| Maven Surefire Plugin | 3.2.5 |
| JUnit Jupiter | 5.11.4 |
| Maven Clean Plugin | 3.3.2 |
| Maven Resources Plugin | 3.3.1 |
| Maven JAR Plugin | 3.4.2 |
| actions/checkout | `@v7` |
| actions/setup-java | `@v6` |
| actions/upload-artifact | `@v7` |
| actions/download-artifact | `@v8` |
| actions/attest | `@v4`, tùy chọn |

Các GitHub Actions major được đối chiếu với hướng dẫn upstream, nhưng môi trường GitHub Enterprise Server/self-hosted runner có thể yêu cầu version khác. Trong production nên pin actions bằng **approved full commit SHA** theo supply-chain policy thay vì mutable major tags; không tự sáng tác hash để “cho có”.

Workflow baseline chạy trên GitHub.com-hosted `ubuntu-latest`; nó dùng Bash, GNU `sha256sum` và Python3 thông dụng trên runner đó.

## 6. Project source mẫu

Tạo project:

~~~text
traceable-math/
├── pom.xml
├── .gitignore
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/maven-wrapper.properties
├── src/main/java/dev/learning/ci/
│   ├── Numbers.java
│   └── App.java
├── src/test/java/dev/learning/ci/
│   └── NumbersTest.java
├── scripts/test_summary.py
├── .github/workflows/maven-ci.yml
└── target/                    (generated, không commit)
~~~

Các files `mvnw` và `mvnw.cmd` sẽ sinh ở bước Maven Wrapper. `target/` chỉ xuất hiện sau build.

Maven coordinates của project demo:

~~~text
dev.learning.ci:traceable-math:1.0.0
~~~

File binary được JAR Plugin tạo:

~~~text
target/traceable-math-1.0.0.jar
~~~

Nếu đổi `version` hoặc `artifactId`, cần cập nhật tên JAR/GAV được dùng ở staging và kiểm tra.

## 7. POM Maven Java 17 đầy đủ

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning.ci</groupId>
    <artifactId>traceable-math</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### Các quyết định liên quan đến CI

- JDK cần thực sự là 17+; `maven.compiler.release=17` không tự cài JDK.
- JUnit `test` scope giúp consumer runtime không cần JUnit chỉ để chạy class chính.
- `failIfNoTests=true` chặn một dự án có test bắt buộc bị báo xanh dù không discover tests. Với reactor có POM-only modules, áp dụng chính sách riêng theo module.
- `project.build.outputTimestamp` giúp archive timestamps ổn định khi plugin hỗ trợ, **không bảo đảm toàn bộ build đã reproducible**.
- Các Maven lifecycle plugins được ghim version.
- Không bật `testFailureIgnore` hoặc `skipTests` trong QA gate.
- JAR là plain JAR; runtime class chỉ dùng Java standard library.

## 8. Java code: Numbers.java

File `src/main/java/dev/learning/ci/Numbers.java`:

~~~java
package dev.learning.ci;

/** Integer addition that fails on 32-bit overflow. */
public final class Numbers {

    private Numbers() {
        throw new AssertionError("Utility class");
    }

    public static int addExact(int left, int right) {
        return Math.addExact(left, right);
    }
}
~~~

`Math.addExact` trả tổng chính xác khi còn nằm trong miền int và ném `ArithmeticException` nếu tràn. Đây là hành vi xác định để kiểm thử.

## 9. Java main: App.java

File `src/main/java/dev/learning/ci/App.java`:

~~~java
package dev.learning.ci;

public final class App {

    private App() {
        throw new AssertionError("Utility class");
    }

    public static String message() {
        return "3 + 4 = " + Numbers.addExact(3, 4);
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

**Stdout chính xác:**

~~~text
3 + 4 = 7
~~~

Để chạy sau compile:

~~~bash
java -cp target/classes dev.learning.ci.App
~~~

Để chạy từ JAR đã package:

~~~bash
java -cp target/traceable-math-1.0.0.jar dev.learning.ci.App
~~~

Không dùng `java -jar` vì POM baseline chưa đặt `Main-Class` vào manifest; lỗi thiếu main manifest attribute không phải build lỗi ở đây.

## 10. JUnit 5 test class

File `src/test/java/dev/learning/ci/NumbersTest.java`:

~~~java
package dev.learning.ci;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class NumbersTest {

    @ParameterizedTest
    @CsvSource({
        "3, 4, 7",
        "-3, 4, 1",
        "0, 0, 0"
    })
    void addsWithoutOverflow(int left, int right, int expected) {
        assertEquals(expected, Numbers.addExact(left, right));
    }

    @Test
    void rejectsOverflow() {
        assertThrows(ArithmeticException.class,
                () -> Numbers.addExact(Integer.MAX_VALUE, 1));
    }

    @Test
    void printsMessage() {
        assertEquals("3 + 4 = 7", App.message());
    }
}
~~~

Có **5 lượt test invocations**: 3 từ CsvSource, một overflow test và một message test. Theo baseline: `Tests run: 5, Failures: 0, Errors: 0, Skipped: 0`. Test class được Surefire discover theo `*Test.java` convention.

Nếu bỏ tên Test hoặc tests không được discover, `failIfNoTests=true` giúp gate fail thay vì thành công giả. Không lấy số method để thay số invocations của parameterized tests.

## 11. Tạo Maven Wrapper pin Maven version

Lần đầu cần Maven cài sẵn để sinh Wrapper:

~~~bash
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.9 -Dtype=only-script
~~~

Maven Wrapper Plugin tạo những files thông dụng:

~~~text
mvnw
mvnw.cmd
.mvn/wrapper/maven-wrapper.properties
~~~

Với `only-script`, không cần commit một `maven-wrapper.jar`. Review `distributionUrl` trong properties để thấy Maven 3.9.9 và HTTPS endpoint trusted. Có thể pin expected Maven distribution SHA-256 khi upstream cung cấp digest; **không điền hash bịa đặt**.

Linux/macOS:

~~~bash
chmod +x ./mvnw
./mvnw -version
./mvnw -B -ntp clean verify
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd -version
.\mvnw.cmd -B -ntp clean verify
~~~

Wrapper pin **Maven distribution**, không pin JDK; CI sẽ dùng `setup-java`. Commit Wrapper scripts/properties cùng source, không commit `target/` hay cache.

## 12. Kiểm tra local trước khi bật CI

Sau `clean verify`:

~~~bash
jar tf target/traceable-math-1.0.0.jar
java -cp target/traceable-math-1.0.0.jar dev.learning.ci.App
~~~

Tìm các entries:

~~~text
dev/learning/ci/Numbers.class
dev/learning/ci/App.class
~~~

JUnit test reports thường nằm ở:

~~~text
target/surefire-reports/TEST-dev.learning.ci.NumbersTest.xml
target/surefire-reports/dev.learning.ci.NumbersTest.txt
~~~

Không mong thấy `NumbersTest.class` trong main JAR, vì test compile output ở `target/test-classes`.

**Không bịa SHA-256 cụ thể**. Khi chạy thật bạn có thể tạo:

~~~bash
sha256sum target/traceable-math-1.0.0.jar
~~~

Kết quả phụ thuộc exact binary bytes của build đó.

## 13. GITHUB_STEP_SUMMARY và XML test reports

GitHub Actions có environment file `GITHUB_STEP_SUMMARY`. Markdown append vào đó hiển thị trên run summary.

Maven Surefire tạo XML/TXT reports trong `target/surefire-reports`. Thay vì chỉ hiển thị một câu `BUILD SUCCESS`, pipeline nên tóm tắt:

- Số XML test suites.
- Tổng lượt tests đã báo.
- Failures, errors, skipped.
- Không có reports khi build chưa tới test phase.
- Đường dẫn report artifact để đọc chi tiết.

**Không biến summary thành gate thứ hai tự suy ra PASS**. Maven exit code và các required checks mới quyết định build có đủ chất lượng. Script summary phải xử lý cả trường hợp XML chưa tồn tại.

## 14. Python script đọc Surefire XML

Tạo file `scripts/test_summary.py`:

~~~python
from pathlib import Path
import os
import xml.etree.ElementTree as ET


files = sorted(Path("target/surefire-reports").glob("TEST-*.xml"))
stats = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
bad = []

for path in files:
    try:
        root = ET.parse(path).getroot()
        for key in stats:
            stats[key] += int(root.attrib.get(key, "0"))
    except (ET.ParseError, ValueError, OSError) as error:
        bad.append(f"{path.name}: {type(error).__name__}")

lines = [
    "### Maven Surefire tests",
    "",
    f"- XML files: {len(files)}",
    f"- Tests: {stats['tests']}",
    f"- Failures: {stats['failures']}",
    f"- Errors: {stats['errors']}",
    f"- Skipped: {stats['skipped']}",
]

if not files:
    lines.append("- No test XML: build may have failed before Surefire.")
if bad:
    lines.append(f"- Malformed/unreadable XML: {len(bad)}")
    lines.extend(f"  - {name}" for name in bad)

summary = "\n".join(lines) + "\n"
print(summary, end="")

path = os.environ.get("GITHUB_STEP_SUMMARY")
if path:
    with open(path, "a", encoding="utf-8") as output:
        output.write(summary)
~~~

Script dùng Python standard library, không cần pip install. Nó **không thay đổi Maven status** khi tests fail. Khi Maven bị lỗi compile trước khi Surefire chạy, `XML files: 0` không đồng nghĩa `tests PASS`.

Đây là script cho single-module demo. Khi chuyển multi-module, dùng traversal `**/target/surefire-reports/TEST-*.xml` có kiểm soát và tránh đếm trùng.

## 15. Cache Maven với setup-java v6

Dùng input:

~~~yaml
- name: Set up Java and Maven cache
  uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '17'
    cache: maven
    cache-dependency-path: |
      pom.xml
      .mvn/wrapper/maven-wrapper.properties
    cache-read-only: ${{ github.event_name == 'pull_request' }}
~~~

- `cache: maven` quản lý downloaded Maven dependencies (và những cache phụ trợ như Wrapper/JDK theo action version behavior).
- `cache-dependency-path` đưa POM + Wrapper properties vào cache key inputs.
- `cache-read-only` khiến PR chỉ sử dụng cache, không ghi cache mới khi action hỗ trợ.
- Cache bị thiếu/invalidated không được làm thay đổi tính đúng đắn của build.
- Cache local repository chứa executable plugin code; cần policies ngăn cache poisoning và dependency substitution.

Đừng cache nguyên thư mục `target/` như một binary đã qua QA ở commit khác. `clean verify` vẫn phải chạy trên source của run hiện tại, kể cả cache hit.

## 16. GitHub Actions workflow hoàn chỉnh

Tạo file `.github/workflows/maven-ci.yml`. Baseline gồm hai jobs, một job build/test/upload và job kia download + kiểm tra lại bytes:

~~~yaml
name: Traceable Maven CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

concurrency:
  group: maven-ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - name: Checkout
        uses: actions/checkout@v7
        with:
          persist-credentials: false

      - name: Setup Java and Maven cache
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
          cache-dependency-path: |
            pom.xml
            .mvn/wrapper/maven-wrapper.properties
          cache-read-only: ${{ github.event_name == 'pull_request' }}

      - name: Build and run all tests
        shell: bash
        run: |
          set -euo pipefail
          chmod +x ./mvnw
          ./mvnw -version > toolchain.txt
          ./mvnw -B -ntp clean verify

      - name: Summarize tests
        if: always()
        shell: bash
        run: |
          if [[ -f scripts/test_summary.py ]]; then
            python3 scripts/test_summary.py
          else
            echo "Summary unavailable: checkout/setup failed." \
              >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload test reports even after failure
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: surefire-${{ github.run_id }}-${{ github.run_attempt }}
          path: target/surefire-reports/
          if-no-files-found: warn
          retention-days: 14

      - name: Stage binary and build identity
        if: success()
        shell: bash
        run: |
          set -euo pipefail
          jar="target/traceable-math-1.0.0.jar"
          test -s "$jar"
          mkdir -p target/ci-bundle
          cp "$jar" target/ci-bundle/
          cp pom.xml target/ci-bundle/pom.xml
          cp .mvn/wrapper/maven-wrapper.properties \
            target/ci-bundle/maven-wrapper.properties
          cp toolchain.txt target/ci-bundle/toolchain.txt
          {
            printf 'gav=dev.learning.ci:traceable-math:1.0.0\n'
            printf 'repository=%s\n' "$GITHUB_REPOSITORY"
            printf 'ref=%s\n' "$GITHUB_REF"
            printf 'event=%s\n' "$GITHUB_EVENT_NAME"
            printf 'trigger_sha=%s\n' "$GITHUB_SHA"
            printf 'checkout_sha=%s\n' "$(git rev-parse HEAD)"
            printf 'run_id=%s\n' "$GITHUB_RUN_ID"
            printf 'run_attempt=%s\n' "$GITHUB_RUN_ATTEMPT"
            printf 'workflow=%s\n' "$GITHUB_WORKFLOW"
            printf 'run_url=%s/%s/actions/runs/%s\n' \
              "$GITHUB_SERVER_URL" "$GITHUB_REPOSITORY" \
              "$GITHUB_RUN_ID"
          } > target/ci-bundle/BUILD-INFO.txt
          (
            cd target/ci-bundle
            sha256sum \
              traceable-math-1.0.0.jar \
              pom.xml \
              maven-wrapper.properties \
              toolchain.txt \
              BUILD-INFO.txt > SHA256SUMS
            sha256sum --check SHA256SUMS
          )

      - name: Upload verified binary
        if: success()
        id: binary
        uses: actions/upload-artifact@v7
        with:
          name: traceable-math-${{ github.run_id }}-${{ github.run_attempt }}
          path: target/ci-bundle/
          if-no-files-found: error
          retention-days: 30

      - name: Job summary
        if: always()
        shell: bash
        env:
          JOB_STATUS: ${{ job.status }}
          ARTIFACT_URL: ${{ steps.binary.outputs['artifact-url'] }}
          ARCHIVE_DIGEST: ${{ steps.binary.outputs['artifact-digest'] }}
        run: |
          {
            printf '### Maven CI result\n\n'
            printf -- '- Status: %s\n' "$JOB_STATUS"
            printf -- '- Trigger SHA: %s\n' "$GITHUB_SHA"
            printf -- '- Run ID/attempt: %s/%s\n' \
              "$GITHUB_RUN_ID" "$GITHUB_RUN_ATTEMPT"
            if [[ -n "$ARTIFACT_URL" ]]; then
              printf -- '- Artifact URL: %s\n' "$ARTIFACT_URL"
              printf -- '- Archive digest: %s\n' "$ARCHIVE_DIGEST"
            else
              printf '%s\n' '- No verified binary artifact uploaded.'
            fi
          } >> "$GITHUB_STEP_SUMMARY"

  check-bundle:
    name: Download and verify saved artifact
    needs: verify
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Download successful build bundle
        uses: actions/download-artifact@v8
        with:
          name: traceable-math-${{ github.run_id }}-${{ github.run_attempt }}
          path: downloaded

      - name: Check exact bytes and GAV
        shell: bash
        run: |
          set -euo pipefail
          cd downloaded
          sha256sum --check SHA256SUMS
          test -s traceable-math-1.0.0.jar
          grep -Fx 'gav=dev.learning.ci:traceable-math:1.0.0' \
            BUILD-INFO.txt
          echo "Downloaded artifact integrity: PASS"
~~~

**Điều kiện để chạy đúng:** phải commit Wrapper scripts/properties, POM, Java sources, test, Python script và workflow. Workflow dùng GitHub-hosted Ubuntu runner có Python3, Bash và `sha256sum`. Nếu organization dùng GHES hoặc self-hosted runner, kiểm tra compatibility action major/Node runtime theo tài liệu trước khi áp dụng.

## 17. Tại sao reports dùng always(), binary dùng success()?

Surefire unit test fail làm Maven trả non-zero exit code. Các steps bình thường sau đó bị skip. Vì vậy:

~~~yaml
- if: always()
  uses: actions/upload-artifact@v7
  with:
    path: target/surefire-reports/
    if-no-files-found: warn
~~~

là cách tiếp tục lưu báo cáo khi đã sinh XML/TXT. Nếu build fail ở checkout/compiler trước Surefire, report chưa có, sử dụng `warn` thay vì cố tạo report giả. `always()` có thể chạy cả khi cancellation; với workflows cần tránh network work sau khi cancel, có thể xem xét điều kiện `!cancelled()` thay thế theo policy.

Với binary:

~~~yaml
- if: success()
  uses: actions/upload-artifact@v7
  with:
    path: target/ci-bundle/
    if-no-files-found: error
~~~

vì chỉ artifacts đạt gate mới được promotion. Không đổi sang `continue-on-error: true` trên test step để lệnh báo xanh giả.

## 18. Giải thích một bản BUILD-INFO.txt

Phần staging thực sự tạo file metadata:

~~~text
gav=dev.learning.ci:traceable-math:1.0.0
repository=<owner>/<repository>
ref=<event-ref>
event=<event-name>
trigger_sha=<trigger-commit>
checkout_sha=<checked-out-commit>
run_id=<workflow-run-id>
run_attempt=<run-attempt>
workflow=<workflow-name>
run_url=<github-run-link>
~~~

Đây là **schema minh họa, không phải record từ một CI đã chạy**. Trong workflow thật, mỗi giá trị được lấy từ GitHub environment hoặc `git rev-parse HEAD` của checkout.

**Phân biệt hai SHA:**

- `GITHUB_SHA` gắn với event; trên `pull_request` có thể là merge commit dùng cho test.
- `git rev-parse HEAD` là commit thực được checkout trong working tree.
- Nếu muốn ghi PR source head SHA, cần một trường riêng với đúng nguồn thông tin; không đánh tráo với checked-out SHA.

Không dựa chỉ vào tên branch `main` hoặc `feature/foo` để nhận dạng binary: ref có thể di chuyển, còn commit SHA được xác định cụ thể.

## 19. Tại sao cần cả run_id và run_attempt?

GitHub `run_id` định danh workflow run, nhưng khi re-run cùng workflow, `run_attempt` tăng. Cùng commit có thể được build lại trong môi trường khác và tạo artifact digest khác.

Tên artifact của bài:

~~~text
traceable-math-<run_id>-<run_attempt>
~~~

tránh collision giữa các attempts và giúp truy lại đúng run đã tạo binary. Khi mở rộng matrix, thêm OS/JDK/module label để tên unique cho từng job.

Một URL có thể hết hạn nếu artifact bị xóa/expire; long-term release cần kho artifact riêng có retention/immutability theo chính sách.

## 20. SHA256SUMS với relative paths

Phần staging:

~~~bash
(
  cd target/ci-bundle
  sha256sum \
    traceable-math-1.0.0.jar \
    pom.xml \
    maven-wrapper.properties \
    toolchain.txt \
    BUILD-INFO.txt > SHA256SUMS
  sha256sum --check SHA256SUMS
)
~~~

Tạo checksums sau khi tất cả files đã ở đúng bundle. Vì file list có **relative filenames**, sau khi download vào thư mục mới có thể chạy:

~~~bash
cd downloaded
sha256sum --check SHA256SUMS
~~~

Nếu viết checksums với path `target/ci-bundle/...`, verification sau download thường tìm sai đường dẫn. **Không tự hash SHA256SUMS bằng chính nó** trong danh sách vì tạo vòng phụ thuộc.

Hash của JAR không trùng hash của GitHub uploaded archive: một cái là binary bytes, một cái là archive representation của artifact upload.

## 21. Job check-bundle khác rebuild

Job `check-bundle` có:

~~~yaml
needs: verify
~~~

và chỉ dùng `download-artifact` + `sha256sum -c`, không chạy `mvn package` lại.

**Nguyên tắc:** build once, verify, save, promote the **same bytes**. Nếu job B rebuild từ source, nó có thể dùng JDK/plugins/cache khác và tạo JAR có digest khác; bản đó không đương nhiên là binary đã QA ở job A.

Nếu `check-bundle` thất bại vì hash/missing file, toàn workflow phải bị coi là FAIL dù verify job trước đó xanh.

## 22. GitHub artifact ID, URL và digest

Các versions mới của `upload-artifact` cung cấp outputs cho artifact ID/URL/archive digest. Bài đặt `id: binary`, rồi đọc:

~~~yaml
ARTIFACT_URL: ${{ steps.binary.outputs['artifact-url'] }}
ARCHIVE_DIGEST: ${{ steps.binary.outputs['artifact-digest'] }}
~~~

- URL giúp người review tải artifact cùng run/attempt.
- Artifact ID định danh record trên GitHub.
- Archive digest xác minh uploaded artifact representation, **không phải** digest file JAR nằm trong nó.
- `SHA256SUMS` giữ digest của từng file bên trong.
- Nếu dùng attestation, subject digest nên là **JAR exact bytes**.

GitHub artifact v4+ không nên được dùng theo mô hình “nhiều jobs append vào cùng artifact name”. Stage đầy đủ trước rồi upload một lần; matrix jobs phải có tên riêng.

## 23. File retention và long-term tracing

Workflow đặt:

- Test reports: `retention-days: 14`.
- Verified binary bundle: `retention-days: 30`.

Đây là các giá trị **minh họa**, còn bị giới hạn bởi repository/organization/enterprise policy. Một artifact có checksum vẫn có thể bị xóa khi hết hạn và không còn tải được.

Với release cần audit nhiều tháng/năm:

1. Sau QA, chuyển **exact verified bytes** sang Maven repository/registry được quản trị.
2. Lưu POM, digest, commit, run/attempt, build tool info.
3. Giữ test evidence theo thời hạn và quyền đọc phù hợp.
4. Lưu SBOM/attestation nếu policy yêu cầu.
5. Không overwrite một release version immutable bằng binary khác.
6. Quản lý rollback theo version/digest.

GitHub workflow artifact hữu ích cho CI debugging và release candidates; **không tự thay thế permanent release repository**.

## 24. Cache key và Maven model

Trong project đơn, key inputs:

~~~yaml
cache-dependency-path: |
  pom.xml
  .mvn/wrapper/maven-wrapper.properties
~~~

vì POM thay đổi làm dependency/plugins có thể thay; Wrapper properties đổi Maven distribution version. Với multi-module:

- Include toàn bộ `**/pom.xml`.
- Include `.mvn/extensions.xml` nếu dùng extensions.
- Lưu ý active profiles và settings có thể ảnh hưởng resolution ngoài các file đã hash.
- Cache hit không bảo đảm mọi plugin/dependency đã tồn tại.
- Không tự chia sẻ cache path từ OS/JDK architecture khác không tương thích.

Maven Plugin có thể tải artifact lúc goal thực thi. Goal `dependency:go-offline` giúp prefetch declared dependencies/plugins nhưng không đảm bảo mọi runtime custom download. **CI vẫn phải chạy thật `clean verify`**.

## 25. Cache poisoning và pull request security

Pull requests có thể sửa POM, Maven Wrapper script, tests và workflow files, tức là CI đang thực thi code chưa tin cậy.

Các nguyên tắc:

- Dùng `pull_request` chứ không tùy tiện `pull_request_target` + checkout untrusted code với privileged token.
- Chỉ cấp `permissions: contents: read` cho build/test baseline.
- `persist-credentials: false` khi không cần authenticated Git operations.
- Bật `cache-read-only` ở PR với action version hỗ trợ.
- Không truyền deploy keys/token/signing credentials vào PR job.
- Không chạy untrusted PR trên self-hosted runner có quyền nội bộ nhạy cảm.
- Không lưu `settings.xml` có secrets trong shared cache.
- Dùng HTTPS/trusted Maven mirror và repository policies.
- Review third-party actions và pin approved full SHAs cho production.
- Hạn chế dữ liệu nhạy cảm trong logs/test XML và GitHub summaries.

Cache là nơi chứa plugin code có thể được Maven execute; đừng coi Maven dependency cache là “chỉ dữ liệu vô hại”.

## 26. Test failure phải đỏ, không dùng continue-on-error

Một cấu hình không phù hợp:

~~~yaml
- run: ./mvnw -B -ntp clean verify
  continue-on-error: true
~~~

Đoạn này là **anti-pattern**, không nằm trong workflow hoàn chỉnh. Nó có thể biến test failure thành step được chấp nhận, khiến binary stage chạy nếu không có gate khác.

**Đúng:** giữ Maven step thất bại thật, dùng `if: always()` riêng cho test reports, còn binary dùng `if: success()`. Không đặt `-DskipTests`, `-Dmaven.test.skip=true`, `-Dmaven.test.failure.ignore=true` hoặc plugin `testFailureIgnore=true` trong baseline gate.

## 27. Ba tình huống báo cáo lỗi

| Tình huống | Surefire XML | CI verify | Verified binary |
| --- | --- | --- | --- |
| 5 tests PASS | Có | PASS | Được upload nếu staging/upload PASS |
| Assertion fail | Thường có | FAIL | Không upload |
| Compiler/Wrapper fail trước tests | Có thể không có | FAIL | Không upload |

Nếu test summary cho `XML files: 0`, **không** kết luận “0 failures, PASS”. Cần đọc error đầu tiên: checkout, Maven distribution, dependency resolution, compiler hay test discovery.

## 28. Thử kiểm chứng test gate có hoạt động

Trên nhánh thử nghiệm, có thể thêm tạm một assertion sai:

~~~java
@Test
void intentionallyFails() {
    assertEquals(999, Numbers.addExact(3, 4));
}
~~~

Đây là **fragment cố ý sai**, không thuộc `NumbersTest.java` baseline. Khi chạy `clean verify`:

1. Surefire cần phát hiện assertion failure.
2. Build step trả exit code khác 0.
3. Report XML/TXT vẫn được upload nếu sinh ra.
4. Binary stage/upload không chạy.
5. Job check-bundle do `needs: verify` sẽ không chạy.

Khôi phục test trước khi merge. Nếu binary vẫn upload thì CI gate sai; đừng coi trạng thái xanh từ một step khác là đã kiểm thử.

## 29. Kiểm tra download và SHA trên máy khác

Sau khi tải artifact và giải nén vào `downloaded/`:

~~~bash
cd downloaded
sha256sum --check SHA256SUMS
cat BUILD-INFO.txt
jar tf traceable-math-1.0.0.jar
java -cp traceable-math-1.0.0.jar dev.learning.ci.App
~~~

**Stdout:**

~~~text
3 + 4 = 7
~~~

Trên Windows PowerShell nếu không có GNU `sha256sum`, có thể dùng:

~~~powershell
Get-FileHash -Algorithm SHA256 ".\traceable-math-1.0.0.jar"
~~~

rồi so hex digest với dòng tương ứng trong `SHA256SUMS`. Không giả định Windows mặc định có lệnh GNU coreutils.

Một `sha256sum -c` PASS chỉ khẳng định bytes khớp checksums **đang sử dụng**; không chứng minh checksums đến từ một trusted builder.

## 30. Optional: signed artifact attestation

Để tăng provenance, sau khi job `check-bundle` PASS, bổ sung một job **trên trusted main push** với GitHub Actions artifact attestation (nếu repository/plan/policy hỗ trợ). Chèn fragment sau ở **cùng cấp jobs verify/check-bundle**:

~~~yaml
  attest:
    name: Attest verified JAR on trusted main
    needs: check-bundle
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
      attestations: write
      artifact-metadata: write
    steps:
      - name: Download verified bundle
        uses: actions/download-artifact@v8
        with:
          name: traceable-math-${{ github.run_id }}-${{ github.run_attempt }}
          path: attested

      - name: Create build provenance attestation
        uses: actions/attest@v4
        with:
          subject-path: attested/traceable-math-1.0.0.jar
~~~

**Đây là phần mở rộng tùy chọn**, không nằm trong workflow baseline. GitHub hiện hỗ trợ ký provenance bằng OIDC/Sigstore theo documentation, nhưng availability ở private/internal repos phụ thuộc plan/organization.

- Chỉ job `attest` có `id-token: write`; không cấp toàn workflow hoặc cho PR jobs.
- `attest` gắn subject digest với build/workflow identity; consumer phải **verify attestation**, không chỉ đọc một success message.
- Không auto-deploy khi chưa có protected branch/environment, approval, release repo và credentials đã được phép.
- Không thay checksums/reports bằng attestation; các bằng chứng giải quyết các câu hỏi khác nhau.

## 31. Verify signed attestation phía người nhận

Với GitHub CLI/permissions phù hợp, một lệnh minh họa là:

~~~bash
gh attestation verify traceable-math-1.0.0.jar --repo OWNER/REPO
~~~

Thay `OWNER/REPO` bằng repository thật. Lệnh chỉ hữu ích khi artifact đã có attestation và repository cho phép truy cập; ở baseline **chưa có attestation** nên không mong lệnh PASS.

Kiểm tra provenance policy cần xét: subject SHA-256 của JAR, repo identity, workflow, branch/ref, builder và accepted commit. Không xem chứng chỉ ký là thay thế license/security review của dependencies.

## 32. SBOM và reproducibility là mở rộng khác nhau

SBOM (CycloneDX/SPDX) liệt kê components và versions. Với Maven có thể dùng:

~~~bash
./mvnw -B -ntp org.cyclonedx:cyclonedx-maven-plugin:2.9.3:makeBom
~~~

Đây là goal **tùy chọn**; nếu thêm vào pipeline chính, phải quyết định phase/step, pin version, đưa SBOM vào bundle và SHA256SUMS rồi verify cùng binary. Maven SBOM không tự liệt kê mọi OS/JRE/native component.

**Reproducible build** phải được xác minh bằng independent build tạo cùng digest với inputs đã kiểm soát. POM `outputTimestamp` hỗ trợ archive timestamp nhưng không triệt tiêu plugin environment differences, SNAPSHOT drift hoặc generated content chứa thời gian/host.

## 33. Bài toán multi-module

Khi root có:

~~~text
root/
├── pom.xml
├── core/pom.xml
└── app/pom.xml
~~~

reports có thể nằm ở `core/target/surefire-reports` và `app/target/surefire-reports`. Script Python baseline chỉ đọc root `target/`, nên phải sửa:

- Duyệt `**/target/surefire-reports/TEST-*.xml` một cách kiểm soát.
- Tránh đếm trùng reports hoặc build outputs từ previous jobs.
- Chỉ stage JAR từ **modules dự định phát hành**.
- Ghi từng module GAV/version/digest.
- Cache key bao gồm child POMs và extensions.
- Với `-pl/-am`, manifest ghi selected reactor, không tự nói đã build mọi module.
- Nếu module packaging=pom không có tests, điều chỉnh `failIfNoTests` theo module policy.
- Dùng checksum/release metadata của từng JAR thay vì một filename chung.

Không copy mọi `target/*.jar` của reactor vào archive rồi coi tất cả là production binaries; có thể lẫn test fixtures/source JAR.

## 34. Matrix JDK/OS và artifact collision

Nếu thêm:

~~~yaml
strategy:
  matrix:
    java: ['17', '21']
    os: [ubuntu-latest, windows-latest]
~~~

đây mới là **fragment**, không ghép trực tiếp vào workflow Ubuntu/Bash khi chưa chuyển scripts/commands sang Windows-compatible.

Trong matrix, tên artifact cần thêm OS/JDK/module bên cạnh run ID và attempt. Cần quyết định **canonical release binary** xuất từ job nào; các jobs khác là validation.

Không upload từ nhiều jobs vào cùng một artifact name rồi mong upload-artifact tự append. Artifact v4+ không vận hành theo mô hình đó.

## 35. Artifact retention và lâu dài

Workflow chọn reports 14 ngày, binary 30 ngày làm **ví dụ**. GitHub repository/organization có giới hạn retention riêng; artifact có thể mất sau expiry/delete.

Khi phát hành thật:

- Dùng immutable Maven repository/registry với GAV/version.
- Giữ POM, checksum, test evidence, run/commit mapping và attestation/SBOM theo retention yêu cầu.
- Bảo vệ quyền overwrite/delete.
- Không rebuild rồi publish một binary chưa được QA; dùng **build once, promote same bytes**.
- Rollback theo exact version/digest thay vì “JAR mới nhất”.

GitHub Actions artifacts trong bài là release candidates, không tự là kho phát hành dài hạn.

## 36. Các lỗi CI phổ biến

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Wrapper thiếu hoặc permission denied | Chưa commit/gán execute bit | Tạo Wrapper và chmod +x |
| JDK sai | setup-java/JAVA_HOME | Kiểm tra `./mvnw -version` |
| Maven dependency resolution fail | Mirror/proxy/TLS/GAV | Đọc nguyên nhân, không xóa toàn ~/.m2 |
| Cache miss liên tục | Cache key/permissions/branch | Xem setup-java logs |
| Cache hit nhưng build vẫn lâu | Compile/tests chạy thật | Profile Maven goal/test |
| Tests không discover | Tên test, JUnit/Surefire config | `NumbersTest` và failIfNoTests |
| Assertion fail, binary vẫn có | continue-on-error/if gate sai | Chặn binary bằng success() |
| Không có test XML | Fail trước test hoặc wrong path | Debug Maven root cause |
| Report upload fail | Permissions/action/network/storage | Xem upload action status |
| Binary missing | Staging filename cũ sau version bump | Cập nhật GAV/JAR path |
| SHA256SUMS không check | Paths tuyệt đối/copy sai | Dùng relative names |
| Download-artifact not found | Run/attempt/name sai hoặc expired | Tra đúng run identity |
| Archive digest khác JAR digest | Hai đối tượng bytes khác | So đúng digest |
| Optional attest fail | Plan/permissions/OIDC không hỗ trợ | Chỉ bật ở trusted supported repo |
| GHES action incompatibility | Node/runtime/action versions | Chọn supported major |
| PR có secrets | Workflow permissions quá rộng | pull_request + least privileges |

## 37. Phân biệt ba trường hợp FAIL

**Trường hợp A — tests FAIL:** Maven trả non-zero, có thể có Surefire reports, binary không upload. Sửa source/test; đừng xóa cache theo phản xạ.

**Trường hợp B — compile/Wrapper FAIL:** Maven không tới Surefire, report có thể vắng. `if-no-files-found: warn` giữ log lỗi chính dễ đọc. Binary không upload.

**Trường hợp C — check-bundle FAIL:** Build/test PASS trước đó nhưng downloaded artifact/checksum hoặc metadata không hợp lệ; workflow FAIL và release candidate không được promotion. Không được tự rebuild JAR rồi nói đó là cùng artifact.

Ba trường hợp đều cần đọc job/step đầu tiên gây lỗi và đúng run ID/attempt.

## 38. Truy vết một run từ báo cáo đến binary

Khi nhận một JAR từ CI:

1. Lấy artifact URL, ID và run ID/attempt.
2. Đọc `BUILD-INFO.txt`; xác minh repository/ref/event.
3. So `checkout_sha` với commit được CI checkout.
4. Kiểm tra Maven version trong `toolchain.txt` và Wrapper properties.
5. Kiểm tra Surefire reports đã tồn tại, test counts/status và build gate.
6. Chạy `sha256sum -c SHA256SUMS` trong directory chứa downloaded files.
7. Nếu policy đòi signed provenance, verify `gh attestation verify` và subject digest.
8. Nếu phát hành, so published registry JAR digest với verified bundle JAR digest.
9. Kiểm tra artifact vẫn còn trong retention/immutable release repo.
10. Không cấp duyệt chỉ vì file tên `traceable-math-1.0.0.jar`; tên không bảo đảm nội dung.

## 39. Checklist triển khai CI

- [ ] POM đầy đủ, Java 17 compiler target.
- [ ] Maven Wrapper 3.9.9 scripts/properties đã commit.
- [ ] JUnit Jupiter test scope và Surefire failIfNoTests true.
- [ ] `clean verify` chạy không skipTests/testFailureIgnore.
- [ ] Cache Maven chỉ tối ưu downloaded artifacts, không thay build.
- [ ] Cache keys theo POM/Wrapper và profiles cần thiết.
- [ ] PR cache read-only khi được hỗ trợ.
- [ ] Checkout có persist-credentials false nếu không dùng Git push.
- [ ] Workflow permission là contents read ở baseline.
- [ ] Không dùng pull_request_target để thực thi untrusted PR với secrets.
- [ ] Test reports upload dù tests FAIL, not-found=warn.
- [ ] Script summary không diễn giải missing XML là PASS.
- [ ] Binary upload chỉ sau verify và local checksum PASS.
- [ ] Binary upload missing-files=error.
- [ ] Bundle có JAR, POM, Wrapper config, toolchain, BUILD-INFO, SHA256SUMS.
- [ ] Manifest có GAV, ref, event, trigger SHA, checkout SHA.
- [ ] Manifest có run ID, attempt và run URL.
- [ ] SHA256SUMS dùng relative file paths, không checksum bản thân nó.
- [ ] Artifact name unique theo run/attempt/matrix label.
- [ ] Check-bundle job download artifact, không rebuild.
- [ ] Job summary ghi status và artifact URL/digest nếu có.
- [ ] Phân biệt archive digest, JAR digest, attestation subject digest.
- [ ] Retention phù hợp tổ chức; release lưu vào kho bất biến.
- [ ] Không log secrets/private data trong test reports/summary.
- [ ] Signed attestation tùy chọn chỉ bật trusted supported environment.
- [ ] Attestation được consumer verify khi policy yêu cầu.
- [ ] Không gọi SHA256SUMS là bằng chứng reproducible build.
- [ ] Multi-module/matrix policies được xác định trước khi mở rộng.
- [ ] Action majors/runner compatibility được review định kỳ.
- [ ] Run failure không bị biến thành xanh bằng continue-on-error.

## 40. Bài tập nghiệm thu có đáp án

1. **Cache hit đồng nghĩa tests PASS?** Không.
2. **Maven command QA của bài?** `./mvnw -B -ntp clean verify`.
3. **JDK baseline?** Java 17.
4. **GAV của JAR?** `dev.learning.ci:traceable-math:1.0.0`.
5. **Test framework?** JUnit Jupiter 5.11.4.
6. **Test plugin?** Maven Surefire Plugin 3.2.5.
7. **Số test invocations?** 5.
8. **Overflow test kỳ vọng gì?** `ArithmeticException`.
9. **Stdout của App?** `3 + 4 = 7`.
10. **Test reports nằm ở đâu?** `target/surefire-reports`.
11. **Vì sao upload reports dùng always()?** Giữ evidence khi test/build FAIL.
12. **Vì sao reports missing=warn?** Compiler/Wrapper có thể fail trước tests.
13. **Vì sao binary upload dùng success()?** Chặn binary nếu QA gate FAIL.
14. **Nếu binary path sai?** `test -s` và upload missing-files=error khiến job fail.
15. **Vì sao không cache target/ làm verified binary?** Có thể dùng stale output của commit khác.
16. **setup-java cache maven lưu gì?** Downloaded project/plugin artifacts và caches liên quan theo major version.
17. **Run ID có đổi khi rerun cùng run?** Không, run attempt tăng.
18. **GITHUB_SHA luôn PR head SHA?** Không; event-dependent.
19. **Vì sao ghi checkout_sha?** Xác định commit thực build trên runner.
20. **SHA256SUMS tính trên gì?** Các files riêng trong binary bundle.
21. **Có checksum SHA256SUMS bằng chính nó không?** Không.
22. **Tại sao relative paths?** Download sang directory mới vẫn check được.
23. **JAR SHA và GitHub archive digest có giống nhau?** Không.
24. **Check-bundle có chạy Maven build lại không?** Không.
25. **Vì sao build once promote same bytes?** Không xuất bản binary khác bản đã được kiểm tra.
26. **Signed attestation bổ sung gì?** Provenance claims liên kết trusted builder/workflow và binary digest.
27. **Attestation thay security scan không?** Không.
28. **Có nên cấp OIDC quyền cho untrusted PR?** Không khi không cần; bài chỉ ở trusted attest job.
29. **Cache poisoning là gì?** Cache không tin cậy làm trusted workflow dùng artifact độc hại.
30. **Khi test fail, binary vẫn upload có đúng không?** Không.
31. **Khi compile fail, XML có chắc tồn tại?** Không.
32. **Test summary 0 reports có chứng minh PASS?** Không.
33. **Artifact hết retention sẽ ra sao?** Có thể không tải được; cần release repository riêng.
34. **Reproducibility có tự được chứng minh bằng hash?** Không.
35. **Cần thay đổi gì khi chuyển multi-module?** Reports traversal, artifact selection, GAV/digests, cache paths và policy.
36. **Matrix jobs nên có artifact names thế nào?** Unique với OS/JDK/module/run/attempt.
37. **Cache miss có được phép build FAIL?** Chỉ khi dependencies không resolve được; cache miss tự nó không là correctness failure.
38. **Nếu check-bundle FAIL nhưng verify PASS?** Workflow vẫn FAIL, không promote.
39. **Có nên publish JAR từ PR tự động?** Không trong baseline.
40. **Điều kiện xuất bản tin cậy nhất?** QA PASS, exact binary digest + source/run identity, provenance/review theo policy.

## 41. Tài liệu chính thức

- [Maven Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phases test, package, verify, install/deploy.
- [Maven POM Reference](https://maven.apache.org/pom.html): GAV, dependencies, build plugins.
- [Maven Wrapper](https://maven.apache.org/tools/wrapper/): Maven version pinning.
- [Maven Wrapper Plugin — wrapper goal](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/wrapper-mojo.html): generate wrapper scripts.
- [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/): Java release.
- [Maven Surefire Plugin 3.2.5](https://maven.apache.org/surefire-archives/surefire-3.2.5/maven-surefire-plugin/): XML/TXT reports.
- [JUnit 5 User Guide](https://docs.junit.org/5.11.4/user-guide/): Jupiter tests.
- [actions/checkout](https://github.com/actions/checkout): checkout/permissions/ref behavior.
- [actions/setup-java](https://github.com/actions/setup-java): Java and Maven cache behavior.
- [setup-java Advanced Usage](https://github.com/actions/setup-java/blob/main/docs/advanced-usage.md): cache-key and cache-read-only.
- [actions/upload-artifact](https://github.com/actions/upload-artifact): artifacts, archive digest, retention.
- [actions/download-artifact](https://github.com/actions/download-artifact): artifact retrieval/checking.
- [GitHub Actions Contexts](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts): run_id, run_attempt, sha.
- [GitHub Workflow Commands](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands): GITHUB_STEP_SUMMARY.
- [Artifact attestations with GitHub Actions](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations): signed provenance, OIDC.
- [actions/attest](https://github.com/actions/attest): attestation workflow.
- [GitHub CLI attestation verify](https://cli.github.com/manual/gh_attestation_verify): verify provenance.
- [CycloneDX Maven Plugin](https://cyclonedx.github.io/cyclonedx-maven-plugin/): SBOM.
- [Java 17 Math.addExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#addExact(int,int)): overflow check.

**Kết luận:** CI có cache chỉ **nhanh hơn**, không tự đáng tin hơn. CI thực sự truy vết được phải dùng source identity rõ ràng, chạy tests trên code checkout của run hiện tại, giữ Surefire reports khi lỗi, upload binary **chỉ sau gate PASS**, tạo checksums và manifest, rồi xác minh **cùng artifact bytes** sau download. Những tầng signed provenance/SBOM/reproducibility bổ sung được áp dụng theo chính sách release, không thay thế kiểm thử và code review.
