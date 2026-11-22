# Quyền của pipeline pull request so với pipeline xuất bản trong Maven

## 1. Vấn đề: cùng là CI nhưng mức độ tin cậy khác nhau

Một repository chứa dự án Java được xây bằng Maven. Nhóm muốn:
- Mỗi pull request (PR) tự động chạy compile, unit tests, kiểm tra chất lượng.
- Khi maintainer phát hành bản `1.0.0`, CI tạo JAR và upload lên Maven registry.
- Contributor từ một fork bên ngoài vẫn gửi PR được nhưng **không nhận được token xuất bản**.

Nếu dùng cùng một workflow, cùng `settings.xml` chứa credentials và cùng quyền ghi repository cho cả hai trường hợp, một contributor có thể sửa `pom.xml` để thêm Maven plugin execution chạy lệnh bất kỳ ngay tại phase `validate`. Khi pipeline gọi `mvn verify`, đó là mã của contributor đang chạy trong runner — **không phải chỉ dữ liệu cấu hình để đọc**. Nếu runner có quyền `packages: write` hoặc Maven deploy secret, người gửi PR có thể tìm cách đọc và lạm dụng chúng.

Ranh giới quan trọng nhất:

> **PR pipeline kiểm tra mã chưa được chấp nhận, vì vậy phải chạy trong môi trường ít quyền, không có bí mật phát hành. Publish pipeline thực hiện hành động có tác động lâu dài, vì vậy chỉ được chạy từ mã đã được kiểm soát và cấp quyền phát hành có điều kiện.**

Nội dung thuộc mục **IDE và CI — Build Tool Maven**, minh họa bằng **Maven 3.9.x**, **Java 17**, **JUnit 5** và GitHub Actions. Các nguyên tắc tương tự áp dụng cho GitLab CI, Jenkins, Azure Pipelines, nhưng cách đặt tên tokens, fork policy và protected environment khác nhau.

### Mục tiêu sau bài học

Bạn sẽ:
1. Phân biệt trust level của pull request, merge branch, protected tag và deployment.
2. Hiểu vì sao `mvn clean verify` có thể chạy code của người gửi PR.
3. Cấp `GITHUB_TOKEN` theo nguyên tắc least privilege, không mặc định `write-all`.
4. Biết vì sao forked PR không được nhận secrets trong cấu hình GitHub thông thường và các ngoại lệ nguy hiểm.
5. Tránh lạm dụng `pull_request_target` và `workflow_run` để chạy code PR với quyền cao.
6. Viết workflow PR có `contents: read` và không cấp `packages: write`.
7. Viết workflow phát hành chỉ chạy với event `release.published`, tag đúng version, protected environment và token ghi đúng registry.
8. Hiểu Maven `distributionManagement/repository/id` khớp `settings.xml/server/id`.
9. Dùng `actions/setup-java` để cấu hình Maven server credentials từ environment variables, không hard-code token vào POM.
10. Hiểu OIDC có thể thay static cloud credentials khi registry/identity provider hỗ trợ, nhưng không phải registry nào cũng dùng OIDC.
11. Nhận diện rủi ro cache poisoning, artifact poisoning, self-hosted runner và action supply chain.
12. Xây bài lab Java 17/JUnit 5 runnable và một checklist kiểm quyền trước khi publish.

## 2. Tài sản nào cần bảo vệ?

### 2.1. Quyền đọc và quyền ghi không tương đương

Một pipeline chỉ chạy test thường cần:
- đọc source code từ repository;
- tải dependencies từ Maven repository công khai hoặc một mirror **read-only**;
- chạy Maven Compiler, Surefire, static checks;
- công bố kết quả test có giới hạn.

Một pipeline xuất bản có thể cần thêm:
- upload JAR/POM/sources/Javadoc vào Maven registry;
- ký artifact bằng signing key;
- tạo release metadata hoặc provenance;
- cập nhật tag/release nếu đó là trách nhiệm đã được phê duyệt;
- truy cập repository credentials/secrets hay identity federation.

**Quyền upload Maven packages không cần thiết để đọc source và chạy unit tests**. Việc tách quyền giảm tác động nếu source PR hoặc dependency build bị lợi dụng.

### 2.2. Bảng ranh giới tin cậy

| Thuộc tính | PR pipeline | Pipeline xuất bản |
| --- | --- | --- |
| Mục đích | Kiểm compile/test/chất lượng | Build và publish release artifact |
| Source | Commit/merge ref của PR, có thể do contributor ngoài kiểm soát | Commit/tag đã được duyệt |
| Tính tin cậy của code | **Không tin cậy** cho tới khi review và merge | Chỉ tin cậy sau source/release controls |
| Token GitHub tối thiểu | `contents: read` | `contents: read` + `packages: write` nếu publish GitHub Packages |
| Maven repository access | Public hoặc read-only scoped | Write token scoped đúng registry/repository |
| Signing keys | Không cấp | Chỉ cấp trong publish job được bảo vệ |
| Cloud OIDC | Không cần; nên tắt trong PR | Có thể cấp `id-token: write` nếu federation cần |
| Environment | Runner cách ly, không production secrets | Protected release environment |
| Kích hoạt | `pull_request` | `release: published`/protected tag/manual approval |
| Artifact output | Test reports, ephemeral JAR | Release JAR/POM và checksum/signature |
| Side effects | Không publish, không push tag | Có upload; có thể không hoàn tác |
| Khi fail | Báo status fail để chặn merge | Dừng publish, kiểm trạng thái staging/registry |

Đây là **policy khuyến nghị**, không phải tuyên bố mọi provider tự áp dụng đúng bảng. Repo/admin settings vẫn có thể làm yếu các mặc định, đặc biệt với private forks hoặc self-hosted runners.

### 2.3. Vì sao POM của PR được xem là executable?

Maven xử lý `pom.xml` để xác định plugins và goals. Một PR có thể thay đổi:
- `<build><plugins>` và `<executions>` được bind vào `validate`, `test` hoặc `package`;
- Maven profiles và extensions trong `.mvn/extensions.xml`;
- các scripts như `mvnw`, `mvnw.cmd`;
- source Java và unit tests;
- surefire plugin configuration, forked JVM arguments;
- third-party plugins cùng dependencies của chúng;
- cấu hình download repository, annotation processor hoặc generated source.

Khi CI thực thi `mvn clean verify`, Maven có thể nạp plugin code và chạy source/tests từ PR. Vì vậy **review chỉ file workflow YAML chưa đủ** để ngăn code execution. Nếu runner đã có deploy secret, code PR có thể tìm cách đọc secret đó trước khi job đến bước `deploy`.

Nguyên tắc đúng là **không đặt secret/token có giá trị cao vào môi trường đang chạy PR code**.

## 3. GitHub Actions: event và token theo nguồn code

### 3.1. pull_request

Một workflow:

```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened]
```

thường được kích hoạt khi PR mở hoặc cập nhật. Với PR từ fork, GitHub mặc định:
- cấp `GITHUB_TOKEN` **read-only**;
- **không chuyển repository/organization secrets** (trừ `GITHUB_TOKEN`);
- có các chính sách approval cho contributor mới;
- có một số cấu hình admin dành cho forked PR/private repositories có thể thay đổi behavior mặc định.

Tài liệu GitHub nói rõ `GITHUB_TOKEN` từ forked `pull_request` thường chỉ đọc, nhưng có các settings như **Send write tokens to workflows from pull requests** hoặc **Send secrets to workflows from pull requests** ở những phạm vi được hỗ trợ. **Không dựa riêng vào default**; đặt `permissions` tường minh và khóa policy tại repo/org.

Với PR từ branch **cùng repository**, runner có thể có các quyền/secret khác so với fork, tùy event, configuration và quyền actor. Vì thế workflow PR vẫn phải cấp token ít quyền và không tiêm release secrets, kể cả khi contributors đều là nhân sự nội bộ.

### 3.2. pull_request_target

`pull_request_target` khác `pull_request`. Nó chạy trong ngữ cảnh của **base repository**, thường dùng khi maintainer muốn làm công việc được cấp quyền như thêm label, đóng/mở issue, hoặc đăng một comment xác thực.

Rủi ro nghiêm trọng xuất hiện khi workflow `pull_request_target`:
1. Có quyền ghi hoặc có repository secrets;
2. Checkout **head commit của PR từ fork**;
3. Chạy `mvn test`, shell script hoặc tool có khả năng thực thi mã của PR.

Khi đó untrusted code có thể chạy cùng các bí mật/quyền của base repo — kiểu **pwn request**. GitHub đã bổ sung một số chặn mặc định trong `actions/checkout@v7` đối với fork code ở privileged triggers, nhưng **không được dựa vào chặn riêng của checkout để thay trust boundary**: người viết workflow có thể fetch code bằng lệnh khác, hoặc chạy input chưa được kiểm soát theo nhiều con đường.

**Quy tắc:** Không dùng `pull_request_target` để build/test mã PR cùng secrets. Nếu workflow cần tự động label, nó chỉ nên xử lý metadata ở dạng dữ liệu và không chạy script từ PR head.

### 3.3. workflow_run

`workflow_run` có thể được kích hoạt khi workflow khác kết thúc. Một workflow “PR tests” ít quyền có thể upload artifact, còn workflow “post-process” có quyền cao muốn tải artifact đó để báo cáo.

Đây là **một ranh giới tin cậy mới**: artifact từ PR có thể bị người gửi PR kiểm soát. Không tải artifact PR rồi thực thi binary/script của nó trong workflow có deployment secrets hoặc token ghi. Nếu chỉ cần đọc test results, xử lý như dữ liệu không tin cậy; chống path traversal/zip slip, parse injection, workflow input interpolation và cache poisoning.

Nếu thực sự cần publish sau CI, **đừng xem `workflow_run concluded success` của untrusted source là giấy phép phát hành**. Publish phải kiểm lại source commit/tag, reviewer/protection, registry version và quality gates trên trusted workflow.

### 3.4. release và push tag

Một workflow publish có thể bắt đầu từ:

```yaml
on:
  release:
    types: [published]
```

hoặc `push.tags` nếu chính sách release dựa trên protected tags. Tuy nhiên việc event là `published` **không tự chứng minh tag được tạo từ reviewed main**. Chính sách tạo GitHub release/tag, tag protections/rulesets, branch protection và quyền tạo release phải được cấu hình ngoài YAML.

Ngay cả workflow phát hành cũng không nên trao `contents: write` nếu nó chỉ **đọc tag và upload Maven package**. Mỗi quyền ghi phải gắn với một action được giải thích.

## 4. Cách dùng permissions: tối thiểu và có phạm vi

### 4.1. GITHUB_TOKEN nhận scopes nào?

Ở GitHub Actions, `permissions` có thể đặt ở workflow hoặc từng job. Ví dụ:

```yaml
permissions:
  contents: read
```

Theo GitHub Workflow Syntax, khi bạn khai báo một hoặc vài scope, **các scope khác không được liệt kê sẽ là `none`**. Vì vậy workflow trên không có `packages: write`, `id-token: write`, `issues: write`.

Trong workflow PR, chỉ `contents: read` là đủ cho `actions/checkout` truy cập source; một số workflow cần `checks: write` để tự đăng check run, nhưng **không cấp nếu không cần**. Test reports vẫn có thể được hiển thị qua job status mà không cấp khả năng ghi Packages.

### 4.2. Job-level permissions giới hạn write

Một workflow có thể định nghĩa mặc định:

```yaml
permissions:
  contents: read
```

và chỉ trong publish job:

```yaml
jobs:
  publish:
    permissions:
      contents: read
      packages: write
```

Job này có thêm khả năng ghi GitHub Packages (nếu package/registry policy cho phép). Không cấp `write-all` cho cả workflow. Việc có token scope `packages: write` **không vượt qua mọi package ACL/registry policy** và cũng không tạo được Central Portal publisher token.

### 4.3. persist-credentials: false

`actions/checkout` có tùy chọn:

```yaml
with:
  persist-credentials: false
```

Nó hạn chế việc Git credentials được lưu sẵn để các bước sau dùng lại khi thực thi `git push`. Trong PR job, đây là defense-in-depth. Nhưng:
- Nó không làm PR code “an toàn”.
- Nó không vô hiệu hóa `GITHUB_TOKEN` nếu bạn chủ động đưa token vào environment.
- Nó không xóa các quyền cloud/network của self-hosted runner.
- Publish workflow vẫn có thể dùng `GITHUB_TOKEN` riêng cho registry upload trong đúng bước cần thiết.

### 4.4. Actions version và supply-chain risk

Ví dụ bên dưới dùng `actions/checkout@v7` và `actions/setup-java@v6` theo docs công bố vào năm 2026, phù hợp GitHub-hosted runner hỗ trợ runtime tương ứng. Những major tags là **references có thể thay đổi**. Với production có yêu cầu supply chain nghiêm ngặt, pin third-party và first-party actions theo **full commit SHA được kiểm tra**, dùng Dependabot hoặc policy để nâng có review. Không tự bịa SHA trong tutorial.

Với self-hosted runners, các actions mới có thể yêu cầu runner version tối thiểu. Nếu job báo runtime Node/action compatibility, kiểm docs/runner version thay vì hạ quyền bảo mật.

## 5. Bài lab Java 17: project dùng cả PR verify và publish workflow

Project ví dụ nhỏ, không cần database/HTTP/cloud để chạy unit tests. Mục tiêu là thấy rằng **cùng Maven POM, cách CI cấp quyền quyết định build có khả năng publish hay không**.

### 5.1. Cấu trúc project

```text
pr-publish-boundary-lab/
├── pom.xml
├── src/
│   ├── main/java/dev/example/pipeline/ReportFormatter.java
│   └── test/java/dev/example/pipeline/ReportFormatterTest.java
└── .github/
    └── workflows/
        ├── pr-verify.yml
        └── publish.yml
```

`pom.xml` chứa cấu hình Maven Build và một đích Maven registry **mẫu**. `pr-verify.yml` chạy từ PR không có credentials. `publish.yml` chỉ chạy từ GitHub release được phê duyệt và yêu cầu environment bảo vệ.

### 5.2. pom.xml đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>pr-publish-boundary-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <name>PR and Publish Trust Boundary Lab</name>
    <description>Java 17 project for least-privilege Maven CI training</description>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-deploy-plugin</artifactId>
                <version>3.1.4</version>
            </plugin>
        </plugins>
    </build>

    <!-- Replace OWNER/REPO before using an actual publish workflow. -->
    <distributionManagement>
        <repository>
            <id>github</id>
            <url>https://maven.pkg.github.com/OWNER/REPO</url>
        </repository>
    </distributionManagement>
</project>
```

Đây là POM hoàn chỉnh hợp lệ cho **`mvn clean verify`** mà không cần registry credentials: Maven không upload gì trong phase `verify`. URL `OWNER/REPO` chỉ là placeholder của `distributionManagement`; **không được dùng `mvn deploy` trước khi đổi thành repository GitHub Packages thực tế và cấu hình quyền publish**.

Chi tiết:
- Version khởi đầu là `1.0.0-SNAPSHOT` để phát triển. Muốn publish release `v1.0.0`, POM **ở commit được gắn tag** phải là `1.0.0`, không còn `-SNAPSHOT`.
- `maven.compiler.release=17` yêu cầu JDK phù hợp.
- JUnit Jupiter là `test` dependency.
- Compiler/Surefire/JAR/Deploy Plugin versions được pin để không phụ thuộc plugin resolution ngẫu nhiên.
- `distributionManagement/repository/id=github` phải khớp server ID mà `setup-java` tạo trong Maven `settings.xml`.
- POM **không chứa mật khẩu hoặc token**. Repo đích được mô tả ở POM, authentication của release job được cung cấp riêng.
- GitHub Packages có package/repository access policies riêng; cùng `GITHUB_TOKEN` có thể được phép trong repository này nhưng không được phép viết vào package khác.
- Nếu dùng Maven Central, workflow và publisher credentials/protocol cần khác; không giả định có thể đổi mỗi URL và dùng nguyên `GITHUB_TOKEN`.

### 5.3. src/main/java/dev/example/pipeline/ReportFormatter.java

```java
package dev.example.pipeline;

import java.util.Locale;

public final class ReportFormatter {

    private ReportFormatter() {
    }

    public static String format(String input) {
        if (input == null || input.isBlank()) {
            return "status:unknown";
        }
        return "status:" + input.strip().toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        System.out.println(format(" Ready "));
    }
}
```

Ứng dụng chỉ xử lý chuỗi, không gọi network hay lấy environment secrets. `Locale.ROOT` giúp lowercasing xác định, không phụ thuộc locale hệ điều hành. `String.isBlank` và `strip` được Java 17 hỗ trợ. Test có thể chạy hoàn toàn offline khi Maven/JUnit plugins đã có trong cache.

### 5.4. src/test/java/dev/example/pipeline/ReportFormatterTest.java

```java
package dev.example.pipeline;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

final class ReportFormatterTest {

    @Test
    void normalizesStatus() {
        assertEquals("status:ready",
                ReportFormatter.format(" Ready "));
    }

    @Test
    void handlesBlankStatus() {
        assertEquals("status:unknown",
                ReportFormatter.format("   "));
    }

    @Test
    void handlesNullStatus() {
        assertEquals("status:unknown",
                ReportFormatter.format(null));
    }
}
```

Có **3 unit tests** xác định. Maven Surefire phát hiện class `*Test` theo convention; JUnit Jupiter engine có qua `junit-jupiter`. Nếu tests run=0, không coi là PASS cho PR gate.

### 5.5. Chạy local, hoàn toàn không có quyền publish

```bash
mvn -version
mvn -B -ntp -C clean verify
java -cp target/classes dev.example.pipeline.ReportFormatter
```

Với Maven 3.9.x, JDK 17+ và dependencies resolve được, log test có thể tóm tắt:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là **tóm tắt log Maven kỳ vọng**, không phải bản sao nguyên văn console. **Stdout chính xác** của chương trình Java:

```text
status:ready
```

`mvn verify` không publish artifact ra registry. `java -cp` chạy class main, còn `java -jar target/pr-publish-boundary-lab-1.0.0-SNAPSHOT.jar` không được đảm bảo hoạt động vì POM không đặt `Main-Class` trong manifest.

## 6. Workflow PR: không có release secret và không có write permission

### 6.1. .github/workflows/pr-verify.yml

```yaml
name: Verify pull request

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

permissions:
  contents: read

jobs:
  verify:
    if: github.event.pull_request.draft == false
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
      - name: Check out PR source
        uses: actions/checkout@v7
        with:
          persist-credentials: false

      - name: Set up Java 17
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - name: Verify Maven project
        run: mvn -B -ntp -C clean verify
```

**Các điểm bảo vệ quan trọng:**

1. Event là `pull_request`, không phải `pull_request_target`. Workflow chạy trên PR ref/merge commit theo semantics GitHub.
2. Token chỉ `contents: read`. Các scopes không khai, gồm `packages: write` và `id-token: write`, trở thành `none`.
3. Không có `secrets.MAVEN_DEPLOY_TOKEN`, `secrets.GPG_PRIVATE_KEY` hay credential injection vào steps.
4. `persist-credentials: false` giảm cơ hội code PR sử dụng Git auth đã được lưu sẵn.
5. Runner `ubuntu-latest` là GitHub-hosted ephemeral environment trong cấu hình GitHub tiêu chuẩn; không mount nội bộ production.
6. `mvn clean verify` chạy compile, 3 unit tests, package và verification; không có `deploy`.
7. Cờ `-C` yêu cầu strict checksum checking trên dependency/plugin transfers được Resolver xử lý; nó không xác minh mọi dependency publisher signature.
8. Không dùng `cache: maven` trong ví dụ để tránh yếu tố cache lẫn môi trường. Khi thêm cache, cần xét policy read/write và không truyền artifacts PR vào privileged cache.
9. Step `if` chỉ bỏ qua draft PR; nó không làm PR branch đáng tin hơn, và không phải release approval.
10. Về nguồn, PR có thể sửa cả `pom.xml` nên job vẫn chạy **untrusted code**. Việc an toàn phụ thuộc runner ít quyền, không phải file Java mẫu đang lành tính.

**Cần cấu hình bên ngoài YAML:** Đặt job `verify` làm required status check trong branch protection/ruleset để merge không bỏ qua tests. Việc đó không tự tạo release permission.

### 6.2. PR có cần quyền đăng comment hoặc cập nhật check run không?

Nếu muốn bot comment vào PR, hãy tách bước đó vào một workflow **metadata-only** với quyền `pull-requests: write` đúng mức, không chạy PR source dưới token ghi. Có thể dùng GitHub App token hạn chế, event `pull_request_target` được kiểm soát hoặc API integration riêng, nhưng không được checkout/test fork head trong privileged job.

Không cần cấp `contents: write` hoặc `packages: write` cho toàn bộ test workflow chỉ để post trạng thái PASS/FAIL; GitHub Actions tự cung cấp job status.

### 6.3. Forked PR và repository-owned branch khác nhau

Với forked PR, GitHub thường tước write token và secrets, nhưng GitHub cho admins một số policy flags để thay đổi; private repo settings cần kiểm. Với PR đến từ branch cùng repo, người tạo branch có thể có thêm trust/permissions; nhưng vì branch vẫn là mã **chưa review**, không đặt deploy credentials vào job PR.

**Thực tế an toàn nhất là explicit deny-by-omission:** PR workflow chỉ định `contents: read`, và release secrets chỉ tồn tại trong protected publish environment.

## 7. Workflow xuất bản: chỉ từ release tag, chỉ job publish có quyền ghi

### 7.1. Bước cấu hình bên ngoài workflow

Trước khi bật publish:
1. Tạo repository GitHub Packages đích, kiểm quyền người tạo package.
2. Thay `OWNER/REPO` trong POM bằng org/user + repository thật.
3. Tạo environment có tên `maven-release` trên GitHub.
4. Thiết lập deployment protection rules phù hợp plan/repository: required reviewers, hạn chế branches/tags được phép deploy, không cho self-review nếu policy yêu cầu.
5. Dùng branch/tag rulesets hạn chế ai tạo/push tag `v*`, bắt buộc code review và test gate trước khi release.
6. Thiết lập quyền tạo GitHub release cho đúng maintainer/bot đã được duyệt.
7. Đảm bảo `1.0.0` chưa tồn tại trong registry; release versions nên immutable.
8. Kiểm runner, Maven/JDK versions, build reproducibility và ký artifact nếu registry/policy yêu cầu.

**Lưu ý tính sẵn có:** GitHub Environments và required-reviewer rules có giới hạn phụ thuộc plan, visibility public/private/internal và chính sách tổ chức. Nếu tài khoản không hỗ trợ reviewer protection, không mô tả workflow này là đã có approval: cần một deployment approval gate khác do tổ chức kiểm soát.

### 7.2. .github/workflows/publish.yml

```yaml
name: Publish approved Maven release

on:
  release:
    types: [published]

permissions:
  contents: read

jobs:
  publish:
    if: github.event.release.prerelease == false
    runs-on: ubuntu-latest
    timeout-minutes: 30
    environment: maven-release

    permissions:
      contents: read
      packages: write

    steps:
      - name: Check out the published release tag
        uses: actions/checkout@v7
        with:
          ref: ${{ github.event.release.tag_name }}
          persist-credentials: false

      - name: Set up Java and Maven registry authentication
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          server-id: github
          server-username-env-var: GITHUB_ACTOR
          server-password-env-var: GITHUB_TOKEN

      - name: Ensure tag matches POM release version
        env:
          RELEASE_TAG: ${{ github.event.release.tag_name }}
        shell: bash
        run: |
          set -euo pipefail
          VERSION="$(mvn -q -DforceStdout org.apache.maven.plugins:maven-help-plugin:3.5.1:evaluate -Dexpression=project.version)"
          if [ "v$VERSION" != "$RELEASE_TAG" ]; then
            echo "Tag and Maven version differ"
            exit 1
          fi
          case "$VERSION" in
            *-SNAPSHOT)
              echo "A SNAPSHOT cannot be published as a release"
              exit 1
              ;;
          esac

      - name: Verify and upload approved artifact
        env:
          GITHUB_ACTOR: ${{ github.actor }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: mvn -B -ntp -C clean deploy
```

**Vì sao workflow này dùng ít quyền hơn nhiều hướng dẫn cũ?**
- `permissions` cấp mặc định `contents: read`; chỉ job publish có `packages: write`. Không có `contents: write` vì workflow không tạo tag/commit.
- `GITHUB_TOKEN` chỉ được đặt trong environment của step `deploy`, không tiêm vào `Verify tag`. Tuy nhiên **job-level permissions vẫn tồn tại suốt job**; mọi action có khả năng lấy token theo platform API nếu có quyền. Không coi việc đặt env chỉ ở một step là security boundary hoàn toàn.
- `environment: maven-release` yêu cầu môi trường đã được cấu hình bảo vệ, ngăn upload trước approval theo policy.
- Trigger `release.published` giúp quy trình phát hành do người có quyền khởi tạo; **không đủ một mình** để chứng minh Git tag nằm trên branch được review.
- `actions/checkout` chỉ checkout `github.event.release.tag_name`, không checkout một PR head bất kỳ.
- Step version guard so `vVERSION` với tag, chặn mismatch và `-SNAPSHOT`. Nó **không chứng minh tag đã được approved/không bị thay đổi**; cần tags protection, provenance và repository policy.
- `setup-java@v6` tạo Maven `settings.xml` server `github` với **tên biến môi trường**, không đưa secret vào `pom.xml`.
- `mvn clean deploy` đi qua test lifecycle trước upload trong Maven default lifecycle. **Một POM đã bị chỉnh bởi người có quyền tạo release vẫn có thể chạy plugin code**; do đó source tag trust là điều kiện thiết yếu.
- Cờ `-C` là checksum policy, không thay chữ ký hoặc SCA.
- Job không xin `id-token: write`, vì GitHub Packages được xác thực bằng `GITHUB_TOKEN`. OIDC chỉ dùng nếu registry/cloud provider có trust federation tương ứng.

**Trước publish thật:** Project POM đang `1.0.0-SNAPSHOT` và URL `OWNER/REPO` là placeholder. Phải đổi đúng version `1.0.0` ở commit release và thay registry URL. Chỉ sau đó workflow publish mới có thể vượt qua version guard và kết nối registry. Điều này là có chủ đích: ví dụ compile/test chạy được ngay, còn upload yêu cầu cấu hình và quyền thật.

### 7.3. Tại sao chọn clean deploy thay vì skipTests?

`mvn deploy` theo default lifecycle sẽ chạy cả compile/test/package trước deploy. Với ví dụ ba tests, nếu test fail, deploy không được thực thi. Đừng thêm `-DskipTests` chỉ để tiết kiệm vài phút trong một quy trình công bố artifact chính thức mà chưa có kiểm chứng tương đương từ **cùng tagged commit**.

Một quy trình production quy mô lớn có thể tách build/verify và publish thành các jobs, nhưng cần chuyển artifacts được ký/provenance đảm bảo đúng commit, không build lại từ dữ liệu PR chưa tin cậy hoặc cùng một mutable cache. Tách jobs không được làm đứt chuỗi xác minh.

### 7.4. GitHub Packages và Maven Central không giống nhau

Ví dụ dùng endpoint `https://maven.pkg.github.com/OWNER/REPO` và `GITHUB_TOKEN`. Với Maven Central, ngày nay bạn cần theo **Central Portal Publishing**/publisher integration phù hợp, tài khoản namespace đã xác minh, token và chữ ký/metadata theo requirements. **Không copy nguyên `packages: write` và GitHub Package endpoint rồi khẳng định đang publish Maven Central.**

## 8. Maven settings.xml và server IDs: bí mật nằm ở đâu?

### 8.1. distributionManagement chỉ chứa đích, không chứa mật khẩu

Trong `pom.xml`:

```xml
<distributionManagement>
    <repository>
        <id>github</id>
        <url>https://maven.pkg.github.com/OWNER/REPO</url>
    </repository>
</distributionManagement>
```

`<id>github</id>` là tên định danh repository. Để Maven Deploy Plugin upload có authentication, nó tìm server entry có cùng `id` trong Maven `settings.xml`.

### 8.2. Maven settings do setup-java tạo

Một cấu trúc tương đương, chỉ để minh họa:

```xml
<settings>
    <servers>
        <server>
            <id>github</id>
            <username>${env.GITHUB_ACTOR}</username>
            <password>${env.GITHUB_TOKEN}</password>
        </server>
    </servers>
</settings>
```

**Đây là fragment mô tả ý tưởng server credentials**, không phải yêu cầu viết nguyên file vào source repository. Với `setup-java@v6`, các inputs `server-username-env-var` và `server-password-env-var` chỉ định **tên** environment variable mà settings tham chiếu; job xuất bản mới cấp chúng. Dấu `${env...}` trong bản mẫu được dùng để biểu diễn Maven environment property, khác GitHub expression `${{ ... }}`.

Quan trọng:
- POM có thể public nhưng token không được public.
- Không gửi secret trong Maven `-Dpassword=...` vì logs/process list có thể lộ.
- Đảm bảo server ID khớp chính xác: `github` khác `releases`.
- GitHub Packages API có ACL riêng; thiếu quyền package gây 403 ngay cả khi token hợp lệ.
- Với secret nhân sự/tổ chức, dùng environment/repository secrets bảo vệ đúng permission.
- Không dùng personal access token quyền rộng cho PR chỉ để Maven resolve một dependency công khai.

### 8.3. OIDC khác static secret như thế nào?

OpenID Connect cho phép workflow có quyền `id-token: write` xin một JWT danh tính ngắn hạn từ GitHub, rồi đổi JWT lấy credentials của cloud provider/registry **nếu provider có cấu hình federation**.

```yaml
permissions:
  contents: read
  id-token: write
```

Đây là **fragment chỉ dành cho job được phép dùng OIDC**, không thuộc PR workflow trong bài. Bản thân `id-token: write` **không cấp quyền sửa cloud resources**; IAM trust policy ở phía cloud phải ràng buộc repository, ref/tag, environment, audience và phạm vi role. Nếu trust policy cho mọi PR/fork hoặc role quá rộng, OIDC cũng có thể bị lạm dụng.

GitHub Packages trong ví dụ dùng `GITHUB_TOKEN packages: write`, không cần OIDC. Khi chuyển sang AWS/Azure/GCP hoặc registry có trusted publishing, hãy theo đúng flow provider và hạn chế token lifetime/scope.

### 8.4. Secrets không được truyền tới forked PR — nhưng có ngoại lệ policy

GitHub mặc định không chuyển repository/organization secrets tới `pull_request` từ forks, nhưng tổ chức có thể có settings cho forked workflows. Một bài kiểm bảo mật không được dừng ở câu “GitHub luôn an toàn”: cần xác nhận:
- repository/org Actions permissions defaults;
- workflow/job `permissions`;
- fork PR settings;
- secret scopes, environment rules;
- self-hosted runner network/IAM privileges;
- workflow triggers và code checkout behavior.

**Cấu hình rõ ràng và policy ngoài YAML là hai lớp bổ sung.**

## 9. Attack scenarios và cách phòng tránh

### 9.1. Một PR thêm plugin Maven chạy ở validate

PR thay `pom.xml` để thêm Maven plugin có goal chạy lệnh ở phase `validate`. Pipeline gọi `mvn verify` nên thực thi goal này **trước cả khi unit tests bắt đầu**.

**Nếu PR runner có Maven publish secret:** attacker có thể tìm cách lấy secret.  
**Nếu PR runner chỉ có read-only token, không có secrets, mạng nội bộ bị hạn chế:** tác động bị giới hạn hơn; PR job vẫn có thể gây compute abuse, sửa workspace của chính job, tác động cache hoặc đọc các tài nguyên runner có quyền.

Phòng ngừa:
- tách PR job khỏi publish credentials;
- runner ephemeral/isolated;
- không dùng privileged self-hosted runner kết nối production cho PR ngoài;
- review plugin executions và `.mvn/extensions.xml`;
- pin actions/toolchains và giới hạn mạng theo policy.

### 9.2. pull_request_target checkout PR head rồi test

Một anti-pattern:

```yaml
on:
  pull_request_target:

permissions:
  contents: write

jobs:
  unsafe:
    runs-on: ubuntu-latest
    steps:
      # Ví dụ cố ý NGUY HIỂM, KHÔNG sao chép vào CI thật:
      - uses: actions/checkout@v7
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          allow-unsafe-pr-checkout: true
      - run: mvn test
```

Đoạn trên **cố ý là ví dụ không an toàn**, không phải workflow khuyến nghị. `pull_request_target` là privileged trigger; bật `allow-unsafe-pr-checkout` rồi chạy Maven code PR trong ngữ cảnh có quyền ghi tạo rủi ro pwn request. Với checkout v7, input override có tên rất rõ để cảnh báo, không phải giải pháp để dùng tùy tiện.

**Cách xử lý:** dùng `pull_request` cho build/test. Nếu phải dùng `pull_request_target` cho label/comment, giữ workflow **metadata-only**, quyền đúng tối thiểu, không chạy bất kỳ code từ head PR.

### 9.3. workflow_run tải artifact do PR gửi

Một PR pipeline upload ZIP chứa kết quả tests hoặc generated scripts. Workflow privileged kích hoạt sau đó tải ZIP và giải nén/execute, tin rằng “CI đã PASS”.

Rủi ro:
- Artifact có thể chứa file/script do PR kiểm soát.
- File paths có thể gây archive traversal nếu extractor không an toàn.
- Kết quả build có thể bị sửa để giả PASS.
- Cache hoặc build output có thể bị poisoned để đưa binary sai vào publish.

Giảm thiểu:
- Chỉ xử lý PR artifacts như **untrusted data**;
- Không thực thi PR-supplied binary/script với secrets;
- Không dùng file PR artifact làm nguồn release khi chưa xác minh commit/provenance và policy;
- Publish từ **trusted tag**, kiểm version/hash và thực thi verification trong privileged release pipeline;
- Giữ PR job và publisher job trên runners/workspaces tách biệt.

### 9.4. Cache poisoning

Maven cache như `~/.m2/repository` có thể chứa JAR và plugins. Nếu untrusted PR job có khả năng ghi cache được shared với release job, attacker có thể tìm cách khiến privileged job dùng cached artifact sai.

GitHub đã bổ sung cache access controls cho low-trust triggers, nhưng vẫn cần:
- không chia sẻ cache write access giữa PR và release ở cùng trust domain;
- không override `cache-mode: write` trên low-trust triggers nếu chưa có đánh giá;
- key/scoping đúng, restore policy riêng;
- ký/verify artifacts và strict checksums;
- release job không tin cache từ PR là artifact được phê duyệt.

Bài mẫu **không bật dependency cache** để giảm biến số; production có thể bật cache sau khi review rủi ro.

### 9.5. Self-hosted runner có quyền cloud nội bộ

Dù GitHub token `contents: read`, một self-hosted runner có thể:
- có IAM instance role hoặc cloud credentials;
- mount Docker socket;
- đọc filesystem có ssh keys;
- truy cập registry/VPC/internal services;
- giữ process/cache từ jobs trước.

Vì vậy `permissions` không phải toàn bộ sandbox. Với PR từ nguồn ít tin cậy, ưu tiên GitHub-hosted runner hoặc self-hosted **ephemeral** bị cô lập mạng và không gắn cloud role có quyền. Không chạy PR công khai trên runner production có tài sản nhạy cảm.

### 9.6. Trusted tag vẫn có thể trỏ tới mã chưa review

Một maintainer tạo tag `v1.0.0` từ một commit chưa được merge/review, rồi publish release. Workflow có `release.published` và `packages: write` có thể chạy, dù source không được duyệt.

Cần:
- branch protection và required checks;
- protected tag rules;
- review quyền tạo tags/releases;
- optional kiểm commit ancestry với protected main;
- environment approval và trusted reviewer;
- immutable package policy/provenance.

**Tag format guard không thay thế source trust.** Nó chỉ ngăn POM version và tag name lệch nhau.

## 10. Kiểm quyền trong YAML và ngoài GitHub UI

### 10.1. Các quyền nên kiểm tường minh

| Mục | PR verify | Publish job |
| --- | --- | --- |
| `contents` | `read` | `read` |
| `packages` | `none` | `write` nếu dùng GitHub Packages |
| `id-token` | `none` | `none` trong ví dụ, `write` chỉ khi cần OIDC |
| `pull-requests` | `none` | `none` |
| `issues` | `none` | `none` |
| `deployments` | `none` | Chỉ xin thêm nếu workflow cần thao tác deployment API |
| Repository secrets | Không tiêm publisher secrets | Chỉ cấp những secrets được duyệt |
| Environment secrets | Không có | Chỉ sau protection rules |
| Self-hosted privileged runner | Không | Chỉ theo policy có audit |
| Maven deploy | Tuyệt đối không | Chỉ từ trusted release source |

Khi `permissions` khai một vài scope, GitHub áp `none` cho scopes còn lại theo Workflow Syntax. Tuy nhiên các quyền của **credentials bên ngoài** (ví dụ AWS instance role, PAT, Maven token trong file settings có sẵn) **không bị thu hẹp tự động** bởi block `permissions` của GitHub.

### 10.2. Branch protection/rulesets

Một repo nên yêu cầu:
- PR review tối thiểu trước merge;
- required CI status check `verify`;
- hạn chế force push và tag deletion;
- bảo vệ release tags;
- CODEOWNERS review cho `pom.xml`, `.mvn/`, `.github/workflows/` và release scripts;
- approver độc lập cho publish environment nếu plan hỗ trợ.

Chỉ một kiểm tra YAML trong PR không chống được maintainer bị compromise, nhưng làm giảm rủi ro cấp quyền vô tình.

### 10.3. Publisher approval và race conditions

Nếu có nhiều jobs/phát hành cùng GAV:
- environment chỉ cho deploy một release hợp lệ tại thời điểm cần thiết;
- dùng concurrency controls theo tag/version;
- kiểm registry version chưa tồn tại, tránh overwrite;
- xác minh tag/commit checksum và deploy state;
- sau timeout/HTTP 409, **không retry cùng version mù quáng**.

Đặc biệt với Maven Central, released artifacts là immutable. Với GitHub Packages và internal registries, policy có thể khác; tổ chức vẫn nên tránh ghi đè cùng GAV để bảo toàn reproducibility.

### 10.4. Không cấp “write-all” chỉ để tránh lỗi 403

Khi `mvn deploy` bị 403, phải phân biệt:
- `packages: write` thiếu;
- package registry không cho repository này ghi;
- `distributionManagement` URL sai;
- `settings.xml/server/id` không khớp;
- token bị hạn chế scope/repo;
- protected environment chưa duyệt;
- registry yêu cầu credentials khác (Maven Central vs GitHub Packages);
- version đã tồn tại hoặc bị policy từ chối.

**Không giải quyết bằng cách tăng mọi quyền PR và publish lên `write-all`.** Tăng quyền nên có lý do và phạm vi rõ.

## 11. GitLab CI/Jenkins: cùng nguyên tắc nhưng tên quyền khác

### 11.1. GitLab CI

GitLab phân biệt merge request pipeline và tag/release jobs. Các yếu tố cần kiểm:
- `CI_JOB_TOKEN` có permissions và allowlist riêng, không đồng nghĩa GitHub `GITHUB_TOKEN`;
- protected branches/tags và protected CI/CD variables;
- protected environments và deployment approvals;
- rules chỉ cho job publish chạy ở tag/ref được phép;
- forked merge requests có chính sách runner/variables khác nhau, nhất là nếu chạy trong parent project.

Ví dụ **fragment minh họa về routing jobs**, không phải file đủ deploy:

```yaml
stages:
  - verify
  - publish

verify-mr:
  stage: verify
  script:
    - mvn -B -ntp -C clean verify
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'

publish-tag:
  stage: publish
  environment:
    name: maven-release
  script:
    - mvn -B -ntp -C clean deploy
  rules:
    - if: '$CI_COMMIT_TAG =~ /^v[0-9]+\.[0-9]+\.[0-9]+$/'
```

**Fragment trên không đủ an toàn nếu tự đưa vào production:** phải dùng runner image/JDK đúng, protected tag, protected variable/registry credentials, approvals và code verification. Một tag matching regex không chứng minh source đã review.

### 11.2. Jenkins

Jenkins Multibranch Pipeline thường chạy PR builds từ fork/branch. Nếu Jenkins agent có toàn quyền vào credential store, Docker socket hoặc internal network, PR build rất nguy hiểm. Nên tách:
- PR verifier agents không có publish credentials;
- trusted release branch/tag pipeline trên agents được quản lý;
- Jenkins Credentials Binding chỉ trong publish stage, không dùng chung workspace với PR;
- lock resource/repository permissions;
- approvals và audit.

Không khai publisher token trong global environment của Jenkinsfile được PR sửa. Đọc POM và Jenkinsfile từ PR như code không tin cậy khi chạy trên agent.

### 11.3. IDE không mang quyền CI production

Developer chạy `mvn verify` từ IDE (IntelliJ IDEA, Eclipse, VS Code) thường dùng local settings/cache/credentials. Đừng lấy cấu hình IDE local làm mẫu để cấp quyền PR runner:
- IDE có thể có `~/.m2/settings.xml` chứa server token riêng;
- IDE đã đăng nhập registry/private Maven mirror;
- local machine có SSH keys;
- CI PR phải có credential policy riêng và ít quyền hơn.

Nếu PR cần đọc private dependency, cân nhắc tạo **read-only scoped token** cho một registry proxy, không dùng publish token. Chỉ cấp nếu policy chấp nhận chạy untrusted code với quyền đọc này; một số private packages vẫn là dữ liệu nhạy cảm.

## 12. Các thí nghiệm để kiểm trust boundary

### 12.1. Kiểm tra bản PR không thể deploy

Tạo PR từ fork sandbox chứa POM/Java files. PR workflow phải:
1. Chạy `mvn -B -ntp -C clean verify`.
2. Có 3 tests PASS.
3. Không có `mvn deploy`.
4. Không có `packages: write` hoặc `id-token: write`.
5. Không có release secrets.
6. Không có quyền Git push/tạo tag.
7. Không có quyền truy cập self-hosted production runner.

**Không cần cố tình exfiltrate token để thử**. Dựa trên job permissions, environment configuration và audit/logs không chứa secret. Có thể dùng workflow linter/policy-as-code để kiểm các trường cấu hình.

### 12.2. Chứng minh Maven verify không cần deploy credential

Trên local máy mới hoặc runner sandbox chỉ có public dependency access, chạy:

```bash
mvn -B -ntp -C clean verify
java -cp target/classes dev.example.pipeline.ReportFormatter
```

Kết quả Maven PASS, Java stdout `status:ready`. Không có `GITHUB_TOKEN`, JAR vẫn build được. Đây là minh họa **test không đòi secret publish**. Một build không có token vẫn có thể tải public dependencies.

### 12.3. Kiểm release tag/POM không khớp

Giả sử tag là `v1.0.0` nhưng POM trong tag vẫn là `1.0.0-SNAPSHOT`. Workflow publish sẽ lấy version bằng Maven Help Plugin rồi so:
- `v1.0.0-SNAPSHOT` khác `v1.0.0`;
- bước version guard FAIL;
- `mvn deploy` không được chạy.

Đây là guard giúp tránh publish SNAPSHOT như release. Nó **không thay thế** review mã, tag protection hoặc check registry version.

### 12.4. Kiểm thiếu quyền packages

Trên sandbox registry, nếu publish job có `contents: read` nhưng không có `packages: write`, `mvn deploy` tới GitHub Packages thường bị từ chối vì thiếu quyền ghi. Đây là failure đúng của least-privilege policy, **không phải lý do để thêm write permission vào PR job**.

Chỉ cần kiểm cấu hình trong một repo sandbox với release được cho phép; không dùng production để tạo lỗi cố ý hay publish một artifact rác.

### 12.5. Kiểm reviewer/environment gate

Nếu GitHub environment có required reviewers và phù hợp plan:
- Tạo release tag được bảo vệ trên sandbox.
- Kích hoạt `release.published`.
- Confirm publish job chờ approval.
- Khi chưa approve, không được upload package.
- Sau approval và verification, upload mới được phép.

Không nhầm việc ghi `environment: maven-release` trong YAML với **đã cấu hình required reviewers**: environment name có thể được tạo tự động mà không có protection rules, tùy platform.

## 13. Troubleshooting theo pipeline

| Triệu chứng | Nguyên nhân thường gặp | Xử lý đúng |
| --- | --- | --- |
| Forked PR không đọc được secret | GitHub cố ý không gửi secrets | Thiết kế PR không cần publisher secret |
| Forked PR không comment được | Token chỉ đọc | Metadata-only job hoặc bot scoped, không cấp write cho test |
| PR cần private dependency | Registry chỉ cho credentialed reads | Read-only proxy/token đã review, không dùng deploy token |
| PR Maven test có hành vi lạ | PR sửa POM/plugins/scripts | Coi code là untrusted, cô lập runner |
| `pull_request_target` chạy PR head | Pwn request risk | Dùng `pull_request`, không checkout PR under secrets |
| `workflow_run` tải artifact PR | Artifact poisoning | Không execute artifact trong privileged job |
| Cache từ PR được publish job restore | Cache poisoning risk | Cache separation, read-only low-trust mode |
| Publish step 403 | `packages: write`/ACL thiếu | Cấp đúng quyền trong publish job, không PR |
| Publish step 401 | Maven settings credentials/server ID sai | So `distributionManagement/id` và settings server |
| Publish 404 | URL repository sai hoặc package scope chưa cho phép | Kiểm OWNER/REPO và ACL |
| GitHub Packages trả conflict | Version tồn tại/redeploy policy | Kiểm artifact state; dùng new version khi cần |
| Maven Central không nhận `GITHUB_TOKEN` | Registry identity khác | Dùng Central publisher flow |
| Publish job có `id-token: write` nhưng cloud fail | OIDC trust/audience/claims sai | Kiểm cloud IAM federation, không tăng quyền PR |
| Release tag không khớp POM | `-SNAPSHOT` hoặc wrong tag | Chặn publish, tạo release đúng |
| Publish từ code chưa review | Tag không bảo vệ | Branch/tag ruleset, approvals, provenance |
| Action checkout/runtime fail | Runner quá cũ | Nâng self-hosted runner, xem action requirements |
| Java test local PASS nhưng CI fail | JDK/Maven/settings khác | So toolchains và dependencies |
| Maven install plugin fail | Repo/mirror/cache sai | Phân biệt dependency vs plugin repositories |
| Upload step test bị skip | Dùng `-DskipTests` hoặc workflow condition | Không publish khi gate chưa đạt |
| Secret xuất hiện trong log | In env/unsafe debug | Thu hồi token, hạn chế logs và masks |
| PR chạy trên self-hosted production runner | Runner network/IAM có quyền cao | Tách runner pools, ephemeral isolation |
| Environment không chờ review | Chưa cấu hình approval/plan không hỗ trợ | Bổ sung protection gate ngoài YAML |
| Hai publish jobs chạy cùng tag | Thiếu concurrency/idempotency | Lock tag/GAV và kiểm registry |
| Build chỉ có `verify` nhưng tưởng đã upload | `verify` không chạy deploy | Publish job cần deploy riêng |
| Token ghi vẫn hoạt động trên PR | Repo/admin settings lỏng hoặc secret injection | Giảm org policy, explicit permissions, audit |
| Generated JAR từ PR được đưa vào release | Trust boundary giữa jobs bị vượt qua | Rebuild từ trusted tag hoặc verify provenance mạnh |

## 14. Checklist thiết kế CI Maven an toàn

### PR verify

- [ ] Trigger dùng `pull_request` cho test code PR.
- [ ] Workflow/job chỉ `contents: read` nếu không cần quyền khác.
- [ ] Không cấp `packages: write`, `id-token: write` hoặc `contents: write`.
- [ ] Không truyền repository/cloud/deploy signing secrets vào PR.
- [ ] Không dùng publisher `settings.xml` trong runner PR.
- [ ] Không sử dụng `pull_request_target` để checkout và thực thi mã PR.
- [ ] Maven plugins/POM/scripts được xem là executable, không chỉ data.
- [ ] Runner ephemeral hoặc cô lập; không có IAM/internal production access.
- [ ] Cache không cho PR ghi dữ liệu trusted publish job sử dụng thiếu kiểm chứng.
- [ ] Tests run > 0 và không bị skip tùy tiện.
- [ ] Required status checks chặn merge khi fail.
- [ ] Forked PR/admin settings được kiểm và phù hợp chính sách least privilege.

### Publish

- [ ] Trigger dùng approved release/required protected tag, không trực tiếp từ PR.
- [ ] Source tag/commit đã được review và có required checks.
- [ ] Environment bảo vệ, required reviewers hoặc gate tương đương đã cấu hình thực sự.
- [ ] Chỉ publish job có `packages: write` nếu dùng GitHub Packages.
- [ ] Không cấp `contents: write` trừ khi job phải tạo Git release/tag.
- [ ] Chỉ cấp `id-token: write` khi có OIDC trust policy đúng.
- [ ] `distributionManagement/repository/id` khớp Maven settings server ID.
- [ ] Token registry/signing key không nằm trong POM, source, logs hoặc PR job.
- [ ] Release tag `vVERSION` khớp POM version không SNAPSHOT.
- [ ] `mvn clean deploy` chạy kiểm thử trước upload (hoặc có equivalent verified artifact).
- [ ] Registry version chưa tồn tại; policy chống overwrite được tuân thủ.
- [ ] Signing, SBOM, SCA, provenance và artifact metadata theo policy.
- [ ] Không import untrusted PR artifacts/cache vào job có secrets.
- [ ] CI logs, approval, tag SHA và artifact checksums được lưu để audit.
- [ ] Có runbook khi timeout hoặc publish partial; không retry mù.
- [ ] Quyền publisher token có phạm vi nhỏ và thời hạn ngắn nhất có thể.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `mvn verify` trên PR nguy hiểm nếu có deploy secret? Vì PR có thể sửa POM/plugins/scripts/test code, khiến Maven thực thi lệnh của người gửi PR trước cả bước deploy.

**Câu 2.** PR từ fork GitHub mặc định có repository secrets không? Không, thường không; `GITHUB_TOKEN` chỉ đọc. Nhưng repo/org policy có ngoại lệ cần kiểm.

**Câu 3.** `permissions: contents: read` có ý nghĩa với packages? Các scopes không liệt kê trở thành `none`; không có `packages: write`.

**Câu 4.** `pull_request_target` có thể an toàn cho việc thêm label không? Có thể, khi xử lý metadata và không chạy PR head code dưới privileged token.

**Câu 5.** `pull_request_target` checkout head PR rồi `mvn test` với secrets có an toàn không? Không; nguy cơ pwn request.

**Câu 6.** Vì sao publish workflow cần `packages: write`? Vì Maven Deploy Plugin upload artifacts vào GitHub Packages; read-only token không đủ.

**Câu 7.** Có cần `contents: write` để publish package từ tag đã có không? Không, nếu job chỉ checkout và upload registry, `contents: read` là đủ.

**Câu 8.** Khi nào dùng `id-token: write`? Chỉ trong job cần xin OIDC JWT để đổi lấy quyền cloud/registry thông qua trust policy phù hợp.

**Câu 9.** `id-token: write` tự cấp quyền AWS Administrator không? Không; IAM/cloud side phải có role/trust policy và scopes riêng.

**Câu 10.** Maven lấy deploy credentials từ POM `distributionManagement` không? Không; POM xác định repository URL/id, credentials thường ở `settings.xml`/CI secrets.

**Câu 11.** Nếu `distributionManagement/id=github` nhưng settings server ID là `central`, chuyện gì? Maven không tìm đúng credentials cho repo, deploy có thể fail 401.

**Câu 12.** Vì sao PR job không cần Maven deploy token để chạy 3 tests? `verify` không upload artifact, chỉ compile/test/package.

**Câu 13.** Mốc nào đủ để nói source publish đáng tin? Reviewed source commit/tag, protected rules, required CI checks và approval; chỉ tên tag matching regex chưa đủ.

**Câu 14.** `workflow_run` sau PR SUCCESS có thể thực thi luôn binary từ PR trong publish job không? Không nên; đó là vượt trust boundary nếu artifact chưa được xác minh.

**Câu 15.** `persist-credentials: false` có chặn mọi cách lấy GITHUB_TOKEN không? Không; nó chỉ giới hạn việc checkout lưu credentials, không thay job token permissions hoặc environment.

**Câu 16.** Production actions có nên pin major mutable tag mãi không? Nên cân nhắc pin full commit SHA được kiểm và cập nhật qua review.

**Câu 17.** Nếu GitHub Environments không hỗ trợ required reviewers trên plan/repo này, viết `environment: release` đã đủ approval chưa? Chưa; cần kiểm UI và dùng gate tương đương được cho phép.

**Câu 18.** Release từ tag `v1.0.0` nhưng POM `1.0.0-SNAPSHOT` có nên deploy? Không; fail version guard và tạo release hợp lệ mới.

**Câu 19.** CI PR có token đọc, nhưng self-hosted runner có IAM quyền production. Đã an toàn chưa? Chưa; runner/network là trust boundary khác.

**Câu 20.** `mvn clean deploy` fail sau khi upload timeout, có tự retry same GAV được không? Cần kiểm registry state, tránh double publish/overwrite.

## 16. Kết luận

Hai pipeline Maven cần hai **trust domains** khác nhau:

```text
Pull request from contributor
         |
         v
Untrusted POM + code + tests
         |
         v
Read-only token, no publish secrets, isolated runner
         |
         v
mvn clean verify -> status check -> review/merge
         
Approved source / protected release tag
         |
         v
Environment and tag policy approval
         |
         v
Scoped registry credentials / packages: write
         |
         v
mvn clean deploy -> release artifact -> audit
```

**Quy tắc dễ nhớ:** Một PR cần được **kiểm chứng**, không cần được **ủy quyền phát hành**. Một release cần được **ủy quyền phát hành**, nhưng chỉ sau khi code/tag đã được kiểm soát và kiểm thử. Với GitHub Actions, dùng `pull_request` + `contents: read` cho PR, tách `release.published` + protected environment + `packages: write` cho Maven registry. Không để thay đổi trong PR kéo theo quyền ghi, ký artifact hay truy cập bí mật production.

### Tài liệu chính thức để đối chiếu

- [GitHub Actions — Events that trigger workflows, PR from forks](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [GitHub Actions — Workflow syntax and GITHUB_TOKEN permissions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [GitHub Actions — Securely using pull_request_target](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)
- [GitHub Actions — Compromised runners](https://docs.github.com/en/actions/concepts/security/compromised-runners)
- [GitHub Actions — Dependency caching security](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
- [GitHub — Managing environments for deployment](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)
- [GitHub — Publishing Java packages with Maven](https://docs.github.com/en/actions/tutorials/publish-packages/publish-java-packages-with-maven)
- [GitHub — Using OIDC in deployments](https://docs.github.com/en/actions/concepts/security/openid-connect)
- [GitHub — actions/checkout (v7)](https://github.com/actions/checkout)
- [GitHub — actions/setup-java (v6)](https://github.com/actions/setup-java)
- [Apache Maven — Deploy Plugin Usage, server ID and settings](https://maven.apache.org/plugins/maven-deploy-plugin/usage.html)
- [Apache Maven — Deployment transport/security settings](https://maven.apache.org/guides/mini/guide-deployment-transports.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Sonatype Central — Immutability of published components](https://central.sonatype.org/publish/requirements/immutability/)
