# Chuỗi CI từ checkout đến verify và thu thập kết quả trong Maven

## 1. Từ code commit đến kết luận kiểm chứng được

Một nhóm sử dụng Maven không chỉ cần thông báo "build xanh" mà còn cần trả lời: **chính xác commit nào được kiểm tra, bằng JDK/Maven nào, những test nào đã chạy, cổng chất lượng nào đã áp dụng và các bằng chứng ở đâu khi job thất bại?**

Quy trình tích hợp liên tục (Continuous Integration, CI) có thể biểu diễn:

~~~text
Sự kiện push / pull request
           │
           ▼
Checkout đúng commit/PR merge ref
           │
           ▼
Chuẩn bị runner + JDK + Maven toolchain
           │
           ▼
Restore cache dependency có kiểm soát
           │
           ▼
Maven clean verify
  ├── validate: đọc model + rules được bind
  ├── compile: biên dịch source
  ├── test: chạy unit tests (Surefire)
  ├── package: sinh JAR/WAR
  ├── integration-test: chạy IT (Failsafe nếu cấu hình)
  └── verify: xác nhận IT + kiểm tra/report khác
           │
           ▼
Thu thập report/artifacts, kể cả khi verify FAIL
           │
           ▼
Phân loại kết quả: PASS / FAIL / NOT RUN
           │
           ▼
PR status check + log + retention/audit
~~~

Bài Knowledge thuộc nhóm **IDE và CI**, với đề mục **Chuỗi CI từ checkout đến verify và thu thập kết quả**. Trọng tâm là tạo chuỗi CI **có thể tái hiện, kiểm chứng được và hữu ích khi điều tra lỗi**, không phải đơn giản chèn một lệnh `mvn test` vào pipeline.

Sau bài này bạn có thể:

1. Hiểu checkout event, commit SHA, pull request merge ref và phạm vi mã được kiểm tra.
2. Thiết lập JDK/Maven tương thích và phân biệt `mvn` với Maven Wrapper `./mvnw`.
3. Sử dụng cache `~/.m2/repository` có giới hạn, không nhầm cache với artifact đầu ra.
4. Hiểu Maven default lifecycle và vì sao `clean verify` khác `test`, `package`, `install`, `deploy`.
5. Cấu hình Surefire cho unit tests, Failsafe cho integration tests và JaCoCo cho coverage reports.
6. Tạo một Maven/Java 17 project đầy đủ, có 4 unit tests và 1 integration test.
7. Xây dựng GitHub Actions workflow gồm checkout, setup-java, cache, build và upload reports khi build fail.
8. Đọc các file `TEST-*.xml`, `failsafe-summary.xml`, `jacoco.xml` và HTML report đúng mục đích.
9. Phân biệt việc **thu thập file** với việc **phân tích, hiển thị và đánh giá** report.
10. Biết cách điều tra flaky tests, thiếu report, sai module/profile, cache cũ, secrets, branch protection và CI pipeline chỉ PASS giả.
11. Thiết kế quality gate và bằng chứng kết quả cho multi-module/monorepo, matrix JDK và CI runner có quyền giới hạn.

**Môi trường demo:** Java 17, Maven 3.8+; Maven Compiler Plugin 3.13.0, Surefire/Failsafe 3.5.4, JaCoCo 0.8.13 và JUnit Jupiter 5.11.4. Đây là các phiên bản ghim cho ví dụ, không phải cam kết mọi môi trường năm nay đều sử dụng đúng versions đó.

## 2. Checkout: đúng nguồn là điều kiện đầu tiên

### 2.1. Checkout không chỉ có nghĩa tải code về

Trong CI, bước checkout quyết định **revision** mà Maven sẽ đọc. Với pull request, tùy CI và cấu hình:

- Có thể checkout **head commit** của nhánh PR.
- Có thể checkout một **synthetic merge commit** ghép PR vào nhánh đích, nhằm kiểm tra khả năng tích hợp.
- Có thể checkout commit của nhánh chính ở sự kiện `push`.
- Có thể shallow clone (history rất ngắn) hoặc fetch đủ Git history.

Bốn trường hợp kiểm tra **những source trees có thể khác nhau**. Vì thế khi ghi kết quả, phải biết commit/ref đã được CI checkout; không chỉ ghi "build PR #..." nếu commit thay đổi trong lúc pipeline chạy.

Ví dụ:

~~~bash
git rev-parse HEAD
git status --short
~~~

Trên một CI checkout sạch, `git rev-parse HEAD` trả về SHA của revision đang build; output là SHA phụ thuộc commit thật, **không có giá trị cố định**. `git status --short` có thể rỗng nếu workspace clean, nhưng những files sinh bởi Maven có thể khiến trạng thái thay đổi sau build nếu bị tạo ngoài `target`.

### 2.2. Shallow checkout

Thông thường, một workflow chỉ cần commit hiện tại và có thể dùng `fetch-depth: 1`. Nhưng một build cần `git describe`, version dựa trên tags, changelog hoặc thông tin ancestor có thể yêu cầu:

~~~yaml
with:
  fetch-depth: 0
~~~

Đây là **mảnh tham số checkout**, không phải workflow đầy đủ. Fetch toàn bộ history tốn thời gian/bandwidth hơn; chỉ bật khi mục tiêu cần.

### 2.3. Kiểm tra merge ref hay head ref?

- Test PR head: kiểm tra code của người đóng góp tại SHA xác định.
- Test PR merge ref: kiểm tra code dự kiến sau khi tích hợp vào base branch.
- Với branch protection, chính sách nên yêu cầu status check trên revision phù hợp và tránh merge khi kết quả đã stale.

GitHub Actions `pull_request` mặc định có những semantics cụ thể cho `GITHUB_SHA` và checkout ref. Đừng tùy tiện override `ref` thành PR head rồi vẫn báo rằng đã kiểm tra merge result. Nếu workflow cần cả hai loại, đặt job/matrix có nhãn rõ.

## 3. Runner, JDK, Maven và môi trường có thể tái hiện

Một CI job cần các thành phần:

| Thành phần | Cần biết | Rủi ro nếu không kiểm soát |
| --- | --- | --- |
| Hệ điều hành/runner image | Ubuntu/Windows/macOS và image revision. | Tool paths, shell behavior, native libs khác nhau. |
| Java runtime | Vendor/distribution và JDK version. | Maven hoặc tests chạy bằng JDK sai. |
| Java target | `maven.compiler.release`. | Bytecode/API không phù hợp version mong đợi. |
| Maven executable | Maven 3.x version chính xác, CLI wrapper hay runner-installed. | Lifecycle/plugin defaults có thể khác. |
| POM/plugin versions | Full Maven GAV và plugin executions. | Cùng commit nhưng build behavior thay đổi. |
| Repositories/settings | Source dependencies/plugins và credentials. | Lấy binary khác hoặc không resolve được. |
| Locale/timezone | Environment của test. | Test phụ thuộc giờ/định dạng bị flaky. |
| Network/secrets | Quyền của runner. | PR code chưa tin cậy có thể tiếp xúc bí mật. |

### 3.1. `java -version` và `mvn --version`

Trong job, nên có:

~~~bash
java -version
mvn --version
~~~

`java -version` cho biết Java command trên PATH; `mvn --version` cho biết **Java runtime đang chạy Maven** và Maven version. Hai đầu ra không nhất thiết trùng nếu máy có nhiều JDK.

**Không ghi output mẫu thành một version "chính xác"** nếu chưa chạy. Trong logs thật sẽ có patch version/vendor/build number cụ thể.

### 3.2. `maven.compiler.release=17` không chọn JDK cho Maven

Trong POM:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

thuộc Compiler Plugin configuration, yêu cầu compiler tạo bytecode/API target Java 17. Nó **không tự tải JDK 17** và không tự đổi JVM Maven đang dùng. JDK trên CI vẫn phải được thiết lập qua runner image, `setup-java`, toolchains hoặc cơ chế tương đương.

Nếu chạy Maven bằng JDK 11, compiler không thể dùng `--release 17`. Nếu chạy bằng JDK 21, nhiều trường hợp vẫn có thể compile với `--release 17`, nhưng runtime/test behavior cần kiểm tra theo chính sách.

### 3.3. Maven Wrapper

Một project có thể commit:

~~~text
mvnw
mvnw.cmd
.mvn/wrapper/maven-wrapper.properties
~~~

và dùng:

~~~bash
./mvnw -B -ntp clean verify
~~~

trên Linux/macOS, hoặc:

~~~powershell
.\mvnw.cmd -B -ntp clean verify
~~~

trên Windows.

Maven Wrapper giúp chọn Maven distribution đã khai báo trong repository, thay vì dùng version ngẫu nhiên được cài trong runner. Nhưng **wrapper scripts và distribution URL cũng là mã/nguồn tải cần được tin cậy**. Rà soát `.mvn/wrapper/maven-wrapper.properties`, distribution checksum nếu được hỗ trợ và quyền của workflow. Ví dụ ở mục 10 dùng `mvn` để không đòi thêm wrapper files; trong dự án thực tế có wrapper được review, có thể chuyển sang `./mvnw`.

### 3.4. Tại sao ghi phiên bản trong logs?

Khi CI lỗi chỉ trên máy GitHub-hosted nhưng PASS local, thông tin `java -version`, `mvn --version`, OS, commit SHA và active profiles giúp tái hiện. Không cần log toàn bộ environment (có thể có secrets); chỉ log các thông số không nhạy cảm thực sự cần.

## 4. Maven lifecycle: tại sao `clean verify`?

Maven có nhiều lifecycles. `clean` thuộc clean lifecycle; `verify` thuộc default lifecycle. Khi gọi:

~~~bash
mvn -B -ntp clean verify
~~~

Maven thực hiện goals/phases của `clean` trước, rồi tiến qua các phases của default lifecycle tới `verify`.

**Đây là khác biệt quan trọng: chỉ `mvn verify` không tự bảo đảm đã chạy `clean`.** Output cũ trong `target` có thể còn nếu job reuse workspace và không cleanup.

Những phase cần biết:

| Phase | Vai trò | Plugin thường liên quan |
| --- | --- | --- |
| `validate` | Kiểm tra project model/quality rules được bind. | Maven Enforcer (nếu cấu hình). |
| `compile` | Biên dịch `src/main/java`. | Compiler Plugin. |
| `test` | Chạy unit tests. | Surefire Plugin. |
| `package` | Tạo JAR/WAR/... | JAR/WAR Plugin. |
| `integration-test` | Chạy integration tests nếu goal được bind. | Failsafe `integration-test`. |
| `verify` | Kiểm tra kết quả integration tests và quality gates. | Failsafe `verify`, JaCoCo `report/check`, plugin khác. |
| `install` | Đưa artifacts/POM vào local repository. | Install Plugin. |
| `deploy` | Publish artifacts/POM đến repository chia sẻ. | Deploy Plugin. |

**Lưu ý:** không phải mọi plugin có tên trên tự chạy. Maven default bindings tùy packaging; Failsafe, JaCoCo hoặc Enforcer thường cần khai báo plugin executions. `mvn clean verify` không mặc định quét security, kiểm coverage threshold hoặc chạy IT nếu project chưa cấu hình các goals đó.

### `verify` là điểm tổng hợp kết quả

Khi quality plugins được bind đúng, `verify` là phase thích hợp để phát hiện:

- Unit test failures (từ `test` trước đó).
- Integration test failures (Failsafe kiểm ở `verify`).
- JaCoCo coverage report/check nếu được cấu hình.
- Static analysis, license/enforcer checks nếu execution phase ≤ verify.

Cần hiểu **goal nào đã thực sự chạy**, không coi một `BUILD SUCCESS` là bằng chứng tất cả các loại kiểm tra tồn tại.

### Vì sao không dừng ở `integration-test`?

Failsafe được thiết kế để chạy IT ở `integration-test`, sau đó báo kết quả qua `failsafe:verify` ở phase `verify`. Nếu chỉ chạy:

~~~bash
mvn integration-test
~~~

pipeline có thể không thực hiện đúng teardown (`post-integration-test`) và verification. Nên chạy **`mvn verify`** khi cần Failsafe lifecycle đầy đủ.

## 5. Cấu hình và đọc Surefire unit-test reports

Maven Surefire Plugin chạy unit tests ở phase `test` (trong JAR build mặc định). Nó thường nhận các test class dạng:

~~~text
**/Test*.java
**/*Test.java
**/*Tests.java
**/*TestCase.java
~~~

Với demo, class `GreetingServiceTest` thuộc nhóm `*Test`, nên Surefire nhận nó.

Output thông thường:

~~~text
target/surefire-reports/
    TEST-demo.ci.GreetingServiceTest.xml
    demo.ci.GreetingServiceTest.txt
~~~

Tên có thể thay khi runner/provider/test configuration khác. XML thường chứa `tests`, `failures`, `errors`, `skipped`; .txt là báo cáo dễ đọc. Maven Console cung cấp `Tests run: ...` nhưng UI CI không tự có bảng test chuẩn chỉ nhờ dòng log.

### XML và console khác nhau

Ví dụ **mảnh XML minh họa về thuộc tính report**:

~~~xml
<testsuite
    name="demo.ci.GreetingServiceTest"
    tests="4"
    errors="0"
    failures="0"
    skipped="0">
</testsuite>
~~~

Đây không phải một file Surefire XML hoàn chỉnh để parser; file thật chứa nhiều thuộc tính và `<testcase>` entries. Đừng lấy regex tìm `Tests run` trong log thay cho XML nếu cần tổng hợp số liệu tin cậy.

### `failIfNoTests`

Nếu một Java module **bắt buộc có unit tests**, có thể đặt:

~~~xml
<configuration>
    <failIfNoTests>true</failIfNoTests>
</configuration>
~~~

Mục tiêu là không để một job PASS giả vì test naming sai hoặc không có tests. Nhưng trong multi-module có parent `packaging=pom` hoặc module không yêu cầu Java unit tests, cấu hình này cần áp dụng theo loại module, không buộc đồng loạt.

## 6. Failsafe: integration-test report và fail ở `verify`

Maven Failsafe Plugin thường nhận các lớp:

~~~text
**/IT*.java
**/*IT.java
**/*ITCase.java
~~~

Ví dụ `GreetingServiceIT` (đuôi `IT`) không được Surefire default include, nhưng được Failsafe include. Đây là **hai nhóm tests khác nhau**, tránh chạy một test hai lần bằng cách đặt tên trùng patterns.

Cấu hình thích hợp bind:

- `failsafe:integration-test` tại `integration-test`.
- `failsafe:verify` tại `verify`.

Khi IT thất bại, Failsafe có cơ chế **không fail ngay ở integration-test phase**, để `post-integration-test` có cơ hội teardown môi trường, rồi báo fail khi `failsafe:verify` chạy.

Output:

~~~text
target/failsafe-reports/
    TEST-demo.ci.GreetingServiceIT.xml
    demo.ci.GreetingServiceIT.txt
    failsafe-summary.xml
~~~

Theo tài liệu Maven, `target/failsafe-reports/TEST-*.xml` là default path. `failsafe-summary.xml` chứa status summary cho `failsafe:verify`. Đừng nhầm nó với từng JUnit XML testsuite.

### Khi nào IT thật sự là integration test?

Một IT thường tương tác database/container/network hoặc kết hợp nhiều thành phần. Demo ở mục 10 dùng một **smoke test end-to-end của API nội bộ, không cần external service** để giữ ví dụ chạy độc lập. Test đó minh họa **lifecycle và reporting của Failsafe**, không chứng minh doanh nghiệp đã kiểm thử integration với một DB hay service thật.

Khi dự án cần Docker/Testcontainers, phải thiết kế runner/network và teardown, không âm thầm tuyên bố demo này kiểm thử hạ tầng production.

## 7. JaCoCo: dữ liệu coverage, báo cáo và ngưỡng

JaCoCo Maven Plugin hỗ trợ:

- `jacoco:prepare-agent`: chuẩn bị Java agent và property cho test JVM.
- `jacoco:report`: tạo HTML/XML/CSV reports từ execution data.
- `jacoco:check`: so kết quả với rules/threshold để fail build nếu dưới yêu cầu.
- Các goals khác như `report-integration`/`report-aggregate` cho trường hợp đặc thù.

Trong một Java project thường gặp:

~~~text
target/jacoco.exec                 # dữ liệu coverage dạng binary
target/site/jacoco/index.html      # báo cáo HTML
target/site/jacoco/jacoco.xml      # báo cáo XML cho công cụ tự động
target/site/jacoco/jacoco.csv      # báo cáo CSV (nếu enabled)
~~~

**`jacoco.exec` không phải XML**, và không thể thay thế hoàn toàn `jacoco.xml` khi một hệ thống CI cần đọc coverage theo schema.

### Coverage data không tự xuất hiện

Cần JaCoCo Java agent thật sự được gắn vào JVM chạy tests. Trong demo:

- `prepare-agent` được gọi sớm qua Maven goal default phase.
- Surefire/Failsafe không override `argLine`, để test forked JVM nhận agent settings.
- Tests chạy và ghi execution data.
- `report` được bind ở `verify` để tạo HTML/XML.

Nếu dự án cấu hình `<argLine>` tùy biến, phải bảo toàn JaCoCo agent options theo hướng dẫn JaCoCo (thường dùng late property evaluation `@{argLine}` trong Surefire/Failsafe), không ghi đè mất agent. Nếu `forkCount=0` làm tests không fork, JaCoCo agent setup kiểu `argLine` có thể không chạy như mong đợi.

### `report` và `check` khác nhau

**Có báo cáo coverage 65% không tự làm build FAIL.** Muốn đặt gate tối thiểu, cần execution `jacoco:check` với rule/limit cụ thể:

~~~xml
<rule>
    <element>BUNDLE</element>
    <limits>
        <limit>
            <counter>LINE</counter>
            <value>COVEREDRATIO</value>
            <minimum>0.80</minimum>
        </limit>
    </limits>
</rule>
~~~

Đây là **mảnh cấu hình cho JaCoCo check**, không phải một POM runnable riêng. Trong ví dụ chính, ta tạo report để minh họa thu thập bằng chứng; phần nâng cao sẽ chỉ cách thêm check gate đúng phase.

Không tự nhận “CI bảo đảm coverage ≥80%” khi project mới chỉ chạy `jacoco:report`.

## 8. Cache Maven dependencies: nhanh hơn nhưng có giới hạn

Với GitHub Actions `actions/setup-java`, input:

~~~yaml
with:
  distribution: temurin
  java-version: '17'
  cache: maven
~~~

giúp quản lý cache liên quan Maven. Theo tài liệu setup-java hiện hành, dependency cache thường lưu `~/.m2/repository`; key dựa trên OS/architecture và hash của Maven input files (như `pom.xml`, Maven Wrapper properties và core extensions). Một số phiên bản action còn tách wrapper/JDK caches, nên luôn đọc tài liệu version bạn đã pin.

**Cache là dữ liệu tăng tốc, không phải deliverable/artifact báo cáo.**

### Những điều cache không bảo đảm

- Cache hit không chứng minh dependencies chưa bị compromise.
- Cache không thay Maven dependency/plugin resolution policy.
- Cùng dependency cache không đồng nghĩa output JAR được build từ source hiện tại.
- Repo manager có thể cung cấp SNAPSHOT mới theo update policy.
- Cache có thể chứa artifacts/lỗi metadata từ build trước.
- Cache restore/save policy khác nhau giữa jobs, branches và các action versions.

Đừng upload toàn `~/.m2/settings.xml` vì nó có thể chứa credential. Không dùng một Maven cache được untrusted PR ghi trực tiếp làm nguồn privileged release mà không có cơ chế tin cậy.

### Cache read-only cho PR

Trong `setup-java@v6` có `cache-read-only`. Khi được bật cho pull request, job có thể **đọc cache phù hợp nhưng không lưu lại cache thay đổi** sau build, giảm khả năng untrusted PR làm nhiễm cache cho workflow khác.

Ví dụ:

~~~yaml
cache: maven
cache-read-only: ${{ github.event_name == 'pull_request' }}
~~~

Input trên thuộc setup-java version có hỗ trợ nó. Không dùng option mới này với action version cũ mà chưa kiểm compatibility.

### Cấu trúc multi-module/monorepo

Nếu một repository có nhiều `pom.xml`, cache key phải bao gồm những POMs/extension inputs làm thay dependency resolution. `setup-java` hiện hỗ trợ `cache-dependency-path` nếu muốn giới hạn/glob cụ thể; cấu hình thiếu POM có thể làm cache key không đổi khi dependency đã thay.

### Khi nào tắt cache?

Nếu điều tra artifact nghi vấn hoặc cần kiểm chứng fresh resolution, có thể tạm chạy build với local repository mới. Nhưng cache-free không đồng nghĩa repository đáng tin; cần xác minh nguồn, checksum/signature/provenance theo policy.

## 9. Phân biệt log, report và artifact upload

| Dạng kết quả | Ví dụ | Người dùng/CI làm gì? |
| --- | --- | --- |
| **Console log** | Maven goal output, stack traces. | Xác định phase/plugin thất bại, xem timeline. |
| **Test XML report** | `target/surefire-reports/TEST-*.xml`. | Parser test runner đọc tests/failures/errors/skipped. |
| **IT XML report** | `target/failsafe-reports/TEST-*.xml`. | Parser integration tests đọc kết quả. |
| **Failsafe summary** | `target/failsafe-reports/failsafe-summary.xml`. | Failsafe verify đọc outcome của IT. |
| **Coverage binary** | `target/jacoco.exec`. | JaCoCo dùng để tạo report, không trực tiếp là XML dashboard. |
| **Coverage report** | `target/site/jacoco/jacoco.xml`/`index.html`. | CI parser/dashboard hoặc người mở HTML. |
| **Build output** | `target/*.jar`, `target/*.war`. | Kiểm tra artifact; không phải test report. |
| **Uploaded CI artifact** | Một zip/archive chứa report paths từ job. | Cho phép tải lại bằng chứng sau job, kể cả fail. |

Việc **upload** XML/HTML vào GitHub Actions artifacts không mặc định chuyển chúng thành GitHub Checks dạng "5 tests PASS". Muốn dashboard/PR test annotations, cần một reporter action hoặc tích hợp CI hỗ trợ **parse JUnit XML**; phải cấp permissions phù hợp và đánh giá security của action đó.

### Tại sao vẫn lưu reports khi build FAIL?

Nếu Surefire phát hiện một assertion fail ở phase `test`, Maven có thể dừng trước `package`/`verify`. Tuy vậy `target/surefire-reports` đã được tạo và có thông tin failure rất hữu ích. Nếu upload chỉ chạy khi step Maven thành công, bạn mất bằng chứng của đúng các lần cần debug nhất.

Cơ chế cần là một **post-build step có điều kiện luôn chạy sau failure**. Trong GitHub Actions thường dùng:

~~~yaml
if: ${{ always() }}
~~~

Nhưng điều này chỉ đảm bảo **bước upload được thử chạy**, không bảo đảm paths tồn tại. Khi checkout/setup/build fail rất sớm, chưa có file test nào; upload nên cho phép báo warning minh bạch.

### Cần bảo vệ dữ liệu trong report

JUnit XML và logs đôi khi chứa stdout/stderr của tests, config hoặc exception messages. Nếu tests in token, password, private URLs hay thông tin cá nhân, upload artifact có thể làm lộ chúng cho những người có quyền xem run. Phải tránh log secrets, có access control/retention hợp lý và cấu hình test data an toàn.

## 10. Dự án Java 17 chạy được để thực hành CI

Tạo project Maven:

~~~text
maven-ci-lab/
├── pom.xml
├── src/
│   ├── main/java/demo/ci/GreetingService.java
│   └── test/java/demo/ci/
│       ├── GreetingServiceTest.java
│       └── GreetingServiceIT.java
└── .github/
    └── workflows/
        └── maven-ci.yml
~~~

Các lớp:

- `GreetingService`: Java 17 service có logic nhỏ và `main` cho chạy thử bằng `java -cp`.
- `GreetingServiceTest`: **4** unit tests, Surefire ở `test`.
- `GreetingServiceIT`: **1** smoke integration-style test, Failsafe ở `integration-test`.
- JaCoCo: chuẩn bị agent và sinh HTML/XML tại `verify`.
- GitHub Actions: từ checkout tới upload reports.

Không cần database, Docker hoặc cloud credentials để chạy ví dụ này.

### 10.1. `pom.xml` hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo.ci</groupId>
    <artifactId>maven-ci-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.11.4</junit.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
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
                <version>3.5.4</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.5.4</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
                <executions>
                    <execution>
                        <id>run-integration-tests</id>
                        <phase>integration-test</phase>
                        <goals>
                            <goal>integration-test</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>verify-integration-tests</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.jacoco</groupId>
                <artifactId>jacoco-maven-plugin</artifactId>
                <version>0.8.13</version>
                <executions>
                    <execution>
                        <id>coverage-agent</id>
                        <goals>
                            <goal>prepare-agent</goal>
                        </goals>
                        <configuration>
                            <append>true</append>
                        </configuration>
                    </execution>
                    <execution>
                        <id>coverage-report</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>report</goal>
                        </goals>
                    </execution>
                </executions>
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

**Giải thích quan trọng:**

1. `maven.compiler.release=17` đặt Java API/bytecode target, không tự chọn JDK.
2. Unit tests thuộc `junit-jupiter` `test` scope; JUnit không trở thành runtime dependency của JAR.
3. Surefire ghim version và `failIfNoTests=true` để nhận biết unit test discovery sai.
4. Failsafe có **hai executions rõ phase**, đảm bảo integration tests chạy ở `integration-test` và kết quả được kiểm ở `verify`.
5. `failIfNoTests=true` của Failsafe hợp lý cho **demo luôn có một IT**. Ở các project/module không cần IT phải thiết kế rule khác, không copy vô điều kiện.
6. JaCoCo `prepare-agent` không có `<phase>` trong execution vì goal có default phase `initialize`; đây là cách cấu hình chuẩn. `report` được bind `verify`.
7. `append=true` giúp dữ liệu execution của nhiều test JVMs có thể được nối vào file đích; vẫn cần runner và agent thực sự hoạt động.
8. Không có cấu hình `argLine` của Surefire/Failsafe ghi đè JaCoCo agent property; nếu thêm JVM args riêng, phải merge một cách đúng.
9. Không thêm `jacoco:check` gate trong POM cơ bản; phần 14 giải thích cách thêm ngưỡng sau khi hiểu report thực.
10. Plugin versions được ghim, nhưng các dependencies/plugins vẫn phải resolve từ repositories hợp lệ.

**Đây là một POM đầy đủ cho demo, không phải fragment.** XML namespace/schemaLocation theo Maven POM 4.0.0.

### 10.2. `src/main/java/demo/ci/GreetingService.java`

~~~java
package demo.ci;

public final class GreetingService {
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello " + name + " from CI";
    }

    public String channel(boolean release) {
        return release ? "release" : "development";
    }

    public static void main(String[] args) {
        System.out.println(new GreetingService().greet("Maven"));
    }
}
~~~

Java 17 hỗ trợ `String.isBlank()` và các biểu thức trong mã. Không cần package nội bộ nào khác để chạy.

### 10.3. `src/test/java/demo/ci/GreetingServiceTest.java`

~~~java
package demo.ci;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingServiceTest {
    private final GreetingService service = new GreetingService();

    @Test
    void createsGreeting() {
        assertEquals("Hello Maven from CI", service.greet("Maven"));
    }

    @Test
    void rejectsNull() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.greet(null));
    }

    @Test
    void rejectsBlank() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.greet("  "));
    }

    @Test
    void distinguishesReleaseChannel() {
        assertEquals("release", service.channel(true));
        assertEquals("development", service.channel(false));
    }
}
~~~

Có **4 JUnit Jupiter methods**. Với Surefire naming convention, `GreetingServiceTest` được chạy ở `test`. Việc gọi cả `release=true` và `false` giúp coverage logic của `channel` được kiểm tra đầy đủ.

### 10.4. `src/test/java/demo/ci/GreetingServiceIT.java`

~~~java
package demo.ci;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingServiceIT {
    @Test
    void integrationStyleSmokeJourney() {
        GreetingService service = new GreetingService();
        String result = service.greet("Maven");
        assertEquals("Hello Maven from CI", result);
        assertEquals("release", service.channel(true));
    }
}
~~~

Một test mô phỏng hành trình kết hợp các operations của service. Failsafe nhận lớp `*IT`; Surefire default không nhận pattern này. Test không kết nối external service nên dễ chạy local.

### 10.5. Chạy local như CI

Từ root `maven-ci-lab`:

~~~bash
java -version
mvn --version
mvn -B -ntp clean verify
~~~

Trong môi trường chuẩn, Maven:

1. Xóa `target` cũ ở clean lifecycle.
2. Chạy `jacoco:prepare-agent` sớm.
3. Biên dịch `GreetingService.java`.
4. Surefire chạy **4** unit tests.
5. Package main JAR `target/maven-ci-lab-1.0.0-SNAPSHOT.jar`.
6. Failsafe chạy **1** integration-style test.
7. Failsafe `verify` kiểm kết quả IT.
8. JaCoCo `report` tạo coverage HTML/XML từ execution data.
9. Kết thúc `BUILD SUCCESS` nếu test/toolchain/dependency resolution đúng.

**Trích đoạn log dự kiến (không phải toàn bộ stdout Maven):**

~~~text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Order, log prefix và vị trí thông báo phụ thuộc plugin/runner; không dùng ba dòng này như snapshot test của Maven console.

### 10.6. Chạy Java và xác minh stdout

Sau `mvn clean verify`:

~~~bash
java -cp target/classes demo.ci.GreetingService
~~~

**Stdout chính xác của riêng chương trình Java:**

~~~text
Hello Maven from CI
~~~

Không dùng `java -jar target/maven-ci-lab-1.0.0-SNAPSHOT.jar` trong demo, vì POM không cấu hình manifest `Main-Class`. Cách `java -cp` chạy class trực tiếp từ `target/classes` đủ để kiểm thử output.

### 10.7. Báo cáo được tạo ở đâu?

Sau run thành công:

~~~text
maven-ci-lab/
└── target/
    ├── maven-ci-lab-1.0.0-SNAPSHOT.jar
    ├── surefire-reports/
    │   ├── TEST-demo.ci.GreetingServiceTest.xml
    │   └── demo.ci.GreetingServiceTest.txt
    ├── failsafe-reports/
    │   ├── TEST-demo.ci.GreetingServiceIT.xml
    │   ├── demo.ci.GreetingServiceIT.txt
    │   └── failsafe-summary.xml
    ├── jacoco.exec
    └── site/
        └── jacoco/
            ├── index.html
            ├── jacoco.xml
            └── jacoco.csv
~~~

Đây là **cây minh họa các file quan trọng**, không liệt kê toàn bộ `target`. Một số HTML assets/nested pages có thể nằm dưới `site/jacoco`. Đừng xóa/di chuyển report trước khi upload.

## 11. GitHub Actions: workflow checkout → verify → thu thập results

GitHub Actions dùng YAML ở `.github/workflows/maven-ci.yml`. Ví dụ dưới đây sử dụng các major release đang được tài liệu action repositories hiện hành mô tả: `actions/checkout@v7`, `actions/setup-java@v6`, `actions/upload-artifact@v7`. Các action majors có thể thay đổi theo thời gian, và tự-hosted runner cần thỏa điều kiện runtime của version; kiểm tra release docs khi dùng.

### 11.1. Workflow hoàn chỉnh

Tạo `.github/workflows/maven-ci.yml`:

~~~yaml
name: Maven CI

on:
  push:
    branches:
      - main
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    name: Java 17 - Maven verify
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
      - name: Checkout source
        uses: actions/checkout@v7
        with:
          persist-credentials: false

      - name: Set up Java 17 and Maven cache
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
          cache-read-only: ${{ github.event_name == 'pull_request' }}

      - name: Record tool versions
        run: |
          java -version
          mvn --version
          git rev-parse HEAD

      - name: Maven clean verify
        run: mvn -B -ntp clean verify

      - name: Upload Maven test and coverage reports
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: maven-reports-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            **/target/surefire-reports/**
            **/target/failsafe-reports/**
            **/target/site/jacoco/**
            **/target/jacoco.exec
          if-no-files-found: warn
          retention-days: 7
~~~

**Đây là một workflow thực tế cho cấu trúc demo trên GitHub-hosted Ubuntu**, với điều kiện repository hỗ trợ GitHub Actions, có tên branch `main` phù hợp, runners/actions được cấp quyền và dependencies resolve được.

### 11.2. Giải thích từng khối

**`on: push / pull_request`**

- Chạy trên push vào `main` và các sự kiện PR theo mặc định của GitHub.
- Nếu nhánh chính tên khác, sửa branch filter.
- Có thể xuất hiện runs khác nhau cho cùng thay đổi (PR và push tùy event), cần xem event/SHA thay vì đếm tuyệt đối.

**`permissions: contents: read`**

- Giới hạn GitHub token của workflow theo quyền đọc source cho job không cần write.
- Đây là một lớp least privilege, không phải sandbox đảm bảo mọi code trong POM đáng tin.

**`actions/checkout@v7`**

- Checkout repository ref theo event.
- `persist-credentials: false` tránh giữ credential để các Git commands tiếp theo vô tình sử dụng.
- Nếu muốn pin security chặt hơn, dùng **full immutable commit SHA** của action release đã được tổ chức thẩm định thay cho moving major tag; không bịa SHA.

**`actions/setup-java@v6`**

- Cài đặt/chọn Temurin Java 17; Maven được lấy từ runner environment trong ví dụ này.
- `cache: maven` tăng tốc tải Maven dependencies/plugins; không cache build output `target` như một artifact.
- `cache-read-only` khi PR hạn chế việc ghi trở lại cache từ source chưa tin.
- `java-version: '17'` chọn Java major line, **không chốt toàn bộ patch/build number**. Với reproducibility nghiêm ngặt có thể pin JDK patch/container image và Maven Wrapper.

**`Record tool versions`**

- In Java/Maven versions và Git revision đang build.
- Không in toàn bộ `env` hay `settings.xml`, tránh lộ secrets/configs.

**`Maven clean verify`**

- Chạy đầy đủ lifecycle tới `verify` với ``-B` (batch) và `-ntp` (no transfer progress).
- Exit code khác 0 làm step FAIL; không dùng `continue-on-error: true` để che kết quả.
- Không tự thêm `-DskipTests`/`-Dmaven.test.skip=true`.

**`Upload ... if: always()`**

- Thử upload reports ngay cả khi step build trước đó fail.
- Các glob `**/target/...` bao gồm root và nested modules khi có.
- `if-no-files-found: warn` thông báo thiếu file; không biến trường hợp lỗi trước compile thành lỗi upload thứ hai.
- `retention-days: 7` yêu cầu retention ngắn, chịu giới hạn/chính sách repository hoặc tổ chức.
- Tên artifact chứa run ID và attempt để truy vết/rerun; các jobs/matrix khác phải dùng tên riêng để tránh collision.

### 11.3. Bước upload không phải test parser

`actions/upload-artifact` **đóng gói và lưu file** theo paths. Nó không tự phân tích JUnit XML và tạo GitHub Checks hiển thị từng test, không tự gán JaCoCo percentage vào PR.

Để hiển thị test annotations hoặc coverage badge, cần thêm bước parser/report publisher được phê duyệt (hoặc xử lý XML riêng). Khi thêm third-party action, rà soát source/version/permissions và không cấp `checks: write` cho PR không tin cậy nếu chính sách không cho phép.

## 12. Khi Maven verify thất bại, report nào còn lại?

Không phải mọi lỗi đều tạo cùng artifacts. Một bảng phân tích:

| Điểm thất bại | Surefire XML | Failsafe XML | JaCoCo XML | Bước upload |
| --- | --- | --- | --- | --- |
| Checkout thất bại | Chưa có | Chưa có | Chưa có | Có thể được gọi, báo không tìm thấy file. |
| Setup JDK hoặc dependency resolution fail sớm | Thường chưa có | Chưa có | Chưa có | Được thử nếu runner/action sẵn sàng. |
| Compile error | Thường chưa có | Chưa có | Chưa có | Báo thiếu file theo cấu hình. |
| Unit test assertion fail ở `test` | **Có thể có** XML với failure | Chưa chạy | Thường chưa có `report` ở verify | Upload Surefire XML. |
| Packaging/plugin error | Surefire XML có thể có | Chưa chạy | Chưa tạo report verify | Upload những file đã sinh. |
| Integration test fail | Surefire XML có | Failsafe XML có | Tùy verify goal order/report đã chạy | Upload unit/IT data hiện có. |
| JaCoCo report/check fail tại `verify` | XML unit test có | XML IT có | Có thể thiếu hoặc chưa hoàn chỉnh | Upload reports thực tế còn lại. |
| Toàn bộ `verify` PASS | Có | Có | Có nếu JaCoCo agent/report hoạt động | Upload cả ba nhóm. |

Cột "có thể" là quan trọng: một process bị kill trước khi test runner flush file có thể để report không hoàn chỉnh. `always()` là **điều kiện chạy step**, không tạo file hay chữa lỗi test runner.

### Đừng che build failure

Một anti-pattern:

~~~yaml
- name: Build
  run: mvn clean verify || true
~~~

Đây là **mảnh YAML để phân tích, không dùng trong workflow chính**. Nó biến Maven exit code fail thành success cho shell step, khiến branch protection có thể tin sai rằng build đạt.

Tương tự:

~~~yaml
continue-on-error: true
~~~

nếu đặt ở bước verify mà không có check riêng để giữ job status fail, có thể tạo báo cáo "success" dù tests đỏ.

Giải pháp là **giữ build step thất bại thực sự**, chỉ cho bước upload có `always()` để thu bằng chứng.

## 13. Cách đọc và triage kết quả CI

### 13.1. Maven console

Đọc **điểm thất bại đầu tiên có ý nghĩa**:

- `Failed to execute goal ...` nêu plugin/goal và module lỗi.
- `Compilation failure` cho biết lỗi Java source.
- `There are test failures` cùng link Surefire/Failsafe reports.
- `Coverage checks have not been met` nếu có JaCoCo check.
- `Non-resolvable parent POM` hoặc `Could not resolve dependencies` khi Maven không tạo được model/dependency graph.
- `BUILD FAILURE` ở cuối là kết luận; chi tiết nằm ở những dòng phía trên.

Không dựa vào câu cuối `BUILD FAILURE` để tự suy ra “lỗi Maven” khi lỗi thực nằm ở assertions/test infrastructure.

### 13.2. Test outcome

Từ `TEST-*.xml`, phân biệt:

- **Failure:** assertion kỳ vọng không đạt, framework đánh dấu failure.
- **Error:** exception không được test xử lý hoặc lỗi thiết lập/teardown.
- **Skipped:** test được skip/disabled hoặc điều kiện bỏ qua; chưa phải PASS.
- **Tests count = 0:** có thể không discover tests hoặc module không có tests.
- **Pass:** test chạy và không được report failure/error, nhưng chỉ nói về phạm vi suite đã chạy.

Nếu muốn dashboard chính xác, dùng JUnit XML parser phù hợp với format Surefire/Failsafe, không cộng các dòng console tùy tiện.

### 13.3. Coverage outcome

JaCoCo report có counters như LINE, BRANCH, INSTRUCTION, METHOD, CLASS, COMPLEXITY với semantics khác nhau. Ví dụ **line covered ratio** không giống branch covered ratio. Không coi 80% line coverage là bảo đảm không có bug hoặc đủ security tests.

Khi đưa coverage vào PR, ghi:

- Metric (LINE/BRANCH) và phạm vi (module/BUNDLE/aggregate).
- Tỷ lệ từ JaCoCo XML hoặc tool đã parse.
- Threshold policy nếu có.
- Modules không chạy tests hoặc không sinh report.
- Commit/run ID để so đúng baseline.

### 13.4. Báo cáo coverage nhiều modules

`target/site/jacoco/jacoco.xml` là report cho từng module khi goal `report` chạy ở đó. Muốn coverage tổng hợp toàn reactor, dùng `jacoco:report-aggregate` theo topology/module dependency và cấu hình phù hợp, **không đơn giản nối XML files rồi lấy trung bình số phần trăm**.

Nếu một module Java không có unit tests, Jacoco report có thể trống hoặc skip do không có execution data. Đừng gán 100% cho module "không có dữ liệu".

## 14. Thêm JaCoCo quality gate mà không hiểu sai report

Sau khi chạy POM cơ bản thành công và xác định coverage metrics, có thể thêm execution `check` dưới `jacoco-maven-plugin`:

~~~xml
<execution>
    <id>coverage-check</id>
    <phase>verify</phase>
    <goals>
        <goal>check</goal>
    </goals>
    <configuration>
        <rules>
            <rule>
                <element>BUNDLE</element>
                <limits>
                    <limit>
                        <counter>LINE</counter>
                        <value>COVEREDRATIO</value>
                        <minimum>0.80</minimum>
                    </limit>
                </limits>
            </rule>
        </rules>
    </configuration>
</execution>
~~~

Đây là **mảnh POM thêm vào plugin JaCoCo đã có**, không phải POM độc lập.

**Nếu thêm đoạn này, test `mvn clean verify` phải chứng minh JaCoCo `check` thực sự chạy và fail nếu dưới 0.80.** Khi sắp thứ tự executions ở `verify`, giữ `report` và `check` phù hợp; nếu lỗi sớm ngăn report, upload step vẫn chỉ có những files đã sinh.

### Negative test cho gate

Trên branch/checkout thử nghiệm:

1. Xóa tạm một vài assertions/tests làm tỷ lệ coverage giảm dưới ngưỡng (nếu chắc sẽ ảnh hưởng metric).
2. Chạy `mvn clean verify`.
3. Xác nhận `jacoco:check` FAIL với violated rule.
4. Khôi phục tests/configuration.
5. Kiểm tra workflow chính báo fail và upload artifacts còn lại.

Đừng dùng `-Djacoco.skip=true` hay `-DskipTests` để "chữa" một tỷ lệ coverage thấp khi policy yêu cầu gate.

## 15. Multi-module Maven: Reactor và report per module

Với một aggregator:

~~~text
root/
├── pom.xml           # packaging=pom
├── api/pom.xml        # packaging=jar, unit tests
├── core/pom.xml       # packaging=jar, unit tests
└── service/pom.xml    # packaging=jar, phụ thuộc core/api, IT
~~~

Câu lệnh:

~~~bash
mvn -B -ntp clean verify
~~~

từ root để Reactor build đủ modules. Với dependencies nội bộ, Maven sắp thứ tự phù hợp. Mỗi module tạo report trong chính `target` của mình:

~~~text
api/target/surefire-reports/TEST-*.xml
core/target/surefire-reports/TEST-*.xml
service/target/surefire-reports/TEST-*.xml
service/target/failsafe-reports/TEST-*.xml
service/target/site/jacoco/jacoco.xml
~~~

Vì vậy upload glob `**/target/surefire-reports/**` phù hợp hơn đường dẫn cố định `target/surefire-reports/**` khi dùng multi-module.

### `-pl` và `-am`

Nếu chỉ muốn test service cùng các prerequisites:

~~~bash
mvn -B -ntp -pl :service -am clean verify
~~~

- `-pl` chọn module service.
- `-am` đưa các upstream reactor modules cần thiết vào build.
- Không giả định tất cả các modules chưa chọn cũng đã được verify.
- Nếu service phụ thuộc binary đã install trong local repo, chạy thiếu `-am` có thể dùng code cũ.
- Cần hiểu parent POM và dependency graph trước khi dùng selective build.

Đặc biệt, CI full-merge gate nên có ít nhất một job kiểm tra phạm vi mà team yêu cầu, không chỉ một module nhẹ "xanh".

### `-fae` và `-fn`

- `-fae` (fail at end) giúp Maven cố tiếp tục các modules không bị ảnh hưởng khi một module lỗi, rồi báo build failure ở cuối. Hữu ích để thu nhiều kết quả hơn trong reactor, nhưng không bảo đảm mọi module được chạy.
- `-fn` (fail never) có thể khiến CI không nhận exit code fail theo kỳ vọng; **không dùng nó trong required verify gate** chỉ để thu thêm log.
- `-rf` resume from module thích hợp cho debug có kiểm soát, nhưng nếu dùng để chứng minh toàn reactor đã verify sau clean thì phải hiểu modules nào bị bỏ.

Để thu thập đầy đủ lỗi trong multi-module, `-fae` có thể hữu ích nhưng cần xác định điều kiện dependency modules bị skip; không dùng log ít hơn/nhanh hơn làm bằng chứng mọi test đã chạy.

## 16. Ma trận JDK và khả năng tương thích

Một dự án muốn hỗ trợ cả Java 17 và Java 21 có thể chạy matrix:

~~~yaml
strategy:
  fail-fast: false
  matrix:
    java: ['17', '21']
~~~

và dùng:

~~~yaml
with:
  distribution: temurin
  java-version: ${{ matrix.java }}
  cache: maven
~~~

Đây là **hai mảnh thuộc job matrix và setup-java step**, không phải workflow hoàn chỉnh thay cho mục 11. Mỗi matrix job phải đặt tên artifact **khác nhau**, ví dụ:

~~~yaml
name: maven-reports-java-${{ matrix.java }}-${{ github.run_id }}-${{ github.run_attempt }}
~~~

vì `upload-artifact@v4+` không cho nhiều jobs đồng thời ghi nội dung khác nhau vào **cùng một tên artifact**. Matrix jobs có thể chạy trên OS/JDK khác nhau nên cũng cần cache separation.

### Maven compiler release cố định trên matrix

Nếu POM đặt `maven.compiler.release=17`, JDK 21 có thể compile bytecode target 17; tuy nhiên chạy tests trên JDK 21 là kiểm tra runtime khác. Đừng coi matrix JDK 17/21 là kiểm chứng cả Windows/Linux nếu `runs-on` vẫn một OS.

### `fail-fast: false` và báo cáo

`fail-fast: false` cho phép các matrix jobs tiếp tục sau khi một job fail, hữu ích để xem mức độ tương thích của từng JDK. Nhưng kết quả merge vẫn cần chính sách **tất cả required matrix jobs phải đạt**, không chấp nhận Java 21 fail nếu team cam kết hỗ trợ nó.

## 17. Phân tách CI verify và publish

Một CI job kiểm tra pull request không nên tự động `deploy` artifact vào Maven repository production. Phân biệt:

**Verify job:**

~~~bash
mvn -B -ntp clean verify
~~~

**Publish job** (chỉ chạy từ protected commit/tag sau approval):

~~~bash
mvn -B -ntp clean deploy
~~~

`deploy` thường chạy lại lifecycle tới deploy và có side effects upload vào remote repository, cần credentials. Không dùng private publish token hoặc GPG signing key trong PR job không tin cậy.

### Artifacts tải xuống từ CI có phải release?

Không. File được `actions/upload-artifact` lưu để download trong run có thể là JAR/test report, nhưng không tự trở thành Maven artifact có repository GAV/POM/signatures và release immutability. Người dùng không nên tự coi zip báo cáo CI là một bản thư viện được phát hành chính thức.

### Đảm bảo đúng commit

Nếu verify và publish chạy ở jobs khác nhau, phải tránh thay nguồn giữa các bước. Sử dụng commit SHA/tag rõ và quy trình promotion/rebuild được tổ chức phê duyệt. Nếu publish dùng cache hoặc artifact từ untrusted PR, cần kiểm tra provenance và trust boundary.

## 18. CI security: chạy mã từ PR có quyền gì?

Maven plugins, extensions, test code và wrapper scripts đều có thể thực thi trong CI. Một pull request chưa được review có thể thay đổi `pom.xml`, `.mvn/extensions.xml`, `mvnw` hoặc test sources.

Vì vậy:

- Dùng `permissions: contents: read` cho verify job nếu chỉ cần checkout.
- Không truyền publish token, cloud credentials hoặc signing keys cho PR job.
- Dùng GitHub-hosted ephemeral runner hoặc self-hosted runner đã cô lập.
- Giới hạn Docker socket, filesystem mount, network egress theo chính sách.
- Review actions versions và pin immutable SHA khi cần.
- Cache từ untrusted jobs không được ghi vào trusted release cache tùy tiện.
- Không chạy untrusted PR checkout trong privileged `pull_request_target` hoặc workflow có secrets.
- Không dùng `continue-on-error` để giấu vi phạm.
- Giới hạn artifact retention, loại dữ liệu nhạy cảm khỏi reports.

**Một container build không tự là sandbox bảo mật** nếu mount host secrets, Docker socket hoặc cấp privileged mode.

### Cấu hình action versions

`actions/checkout@v7`, `setup-java@v6`, `upload-artifact@v7` ở workflow mẫu là **major tags** được upstream công bố tại thời điểm soạn. Major tag có thể di chuyển khi upstream cập nhật patches. Để security hardening, tổ chức nên pin full commit SHAs sau khi xác minh nguồn và xây cơ chế cập nhật định kỳ.

Nếu dùng GitHub Enterprise Server hoặc self-hosted runner cũ, khả năng hỗ trợ artifact action/runtime có thể khác GitHub.com-hosted. Hãy kiểm tra action release notes và runner versions, không copy một workflow mới vào môi trường cũ rồi giả định tương thích.

## 19. Local IDE và CI: tránh "works on my machine"

IDE như IntelliJ IDEA, Eclipse/m2e hoặc VS Code Java có thể dùng **JDK, Maven distribution, profiles và test runner riêng**. Một test chạy bằng IDE không tự chứng minh lệnh CI `mvn clean verify` thành công.

Checklist đối chiếu:

| Khía cạnh | IDE local | CI |
| --- | --- | --- |
| JDK | Project SDK / language level / importer JDK. | `setup-java` và `mvn --version`. |
| Maven | Bundled Maven / Maven Wrapper / system Maven. | Runner-installed Maven hoặc Wrapper. |
| Profiles | IDE Maven profiles. | Flags `-P`, settings, environment. |
| Dependencies | Local cache đã có. | Cache riêng hoặc fresh resolution. |
| Tests | IDE JUnit runner có thể chỉ chạy một class. | Surefire/Failsafe theo naming/config. |
| Integration environment | Local Docker/DB/service. | CI services/container networking. |
| Code generation | IDE annotation processing tùy config. | Maven generator/compiler executions. |
| Reports | IDE green bar. | Surefire/Failsafe XML + JaCoCo. |

Khi local PASS CI FAIL, **tái hiện bằng đúng Maven command và JDK** của CI trước khi sửa test:

~~~bash
mvn -B -ntp clean verify
~~~

Nếu build cần profile, flags hoặc toolchains từ CI, chạy chúng một cách tường minh. Không sửa production POM dựa trên một lỗi chỉ do IDE đang dùng JDK khác.

## 20. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Checkout không tìm thấy commit/ref. | Branch/PR ref đổi hoặc thiếu permissions. | Kiểm tra event, SHA, checkout action và token read permission. |
| Maven chạy JDK sai. | PATH/JAVA_HOME hoặc setup-java không thực thi. | Xem `java -version`, `mvn --version`, setup logs. |
| Compiler báo release version not supported. | Maven runtime JDK cũ hơn target. | Chọn JDK đủ mới, không tự đổi API target để né. |
| `mvn verify` PASS nhưng code cũ vẫn có ở `target`. | Chưa clean hoặc reuse workspace. | Dùng `clean verify`, xem output timestamps/provenance. |
| `mvn test` PASS nhưng IT chưa chạy. | Failsafe không bind hoặc chưa tới integration-test/verify. | Ghim Failsafe executions và chạy `verify`. |
| Failsafe test failure nhưng CI vẫn xanh. | Chỉ chạy `integration-test` hoặc thiếu `failsafe:verify`. | Gắn verify goal và gọi `mvn verify`. |
| Report Surefire không có. | Test chưa chạy, compiler fail, naming mismatch. | Kiểm tra phase và `failIfNoTests` policy. |
| Report Failsafe không có. | Không có IT, plugin/execution không chạy. | Xem POM, test naming, lifecycle logs. |
| Test framework không nhận JUnit 5. | Surefire provider/JUnit deps không tương thích. | Kiểm plugin versions và JUnit Platform dependencies. |
| JaCoCo `jacoco.exec` trống. | Agent không gắn vào test JVM. | Kiểm prepare-agent, `argLine`, forkCount. |
| JaCoCo XML không có dù test chạy. | Goal report chưa bind/verify không tới. | Xem `jacoco:report` execution và phase. |
| Coverage report 70% nhưng build xanh. | Chỉ có report, không có `check` gate. | Cấu hình rule `jacoco:check` nếu policy yêu cầu. |
| Workflow upload báo "No files were found". | Build fail quá sớm, paths sai hoặc test không sinh file. | Kiểm checkout/build logs và report paths. |
| Upload artifact PASS nhưng PR không hiển thị test annotations. | Upload chỉ lưu files, không parse JUnit XML. | Thêm test reporter đã review và permissions phù hợp. |
| GitHub action cache miss liên tục. | Key thay do POM/extensions/wrapper, branch scope hoặc OS khác. | Xem cache input paths/hash/scope. |
| Snapshot cũ trong cache. | Metadata/update policy hoặc wrong GAV. | Kiểm Maven resolver, -U khi phù hợp, xác minh repo. |
| Build chọn lọc dùng module binary cũ. | `-pl` không có `-am`. | Chạy reactor prerequisites cùng source hiện tại. |
| Multi-module reports bị thiếu. | Upload chỉ `target/surefire-reports` ở root. | Dùng `**/target/surefire-reports/**` và tương tự Failsafe. |
| CI trả status xanh dù tests đỏ. | `|| true`, `-fn` hoặc `continue-on-error`. | Bỏ bypass, giữ exit code Maven. |
| IT fail nhưng cleanup không chạy. | Chỉ chạy integration-test hoặc thiếu post-integration-test. | Gọi verify lifecycle, dùng Failsafe đúng. |
| Matrix jobs giẫm artifact tên giống nhau. | Upload artifact names không unique. | Thêm JDK/OS/run ID vào name. |
| Codecov/coverage dashboard trống. | Không upload JaCoCo XML hoặc parser sai path. | Xem `target/site/jacoco/jacoco.xml`. |
| PR job có quyền write secrets. | Workflow permissions quá rộng. | Giảm token, tách publish job/protected branch. |
| Flaky tests chỉ trên CI. | Timing, timezone, network, shared fixtures. | Thu XML/log, cô lập state và sửa test nondeterminism. |
| `BUILD SUCCESS` nhưng số tests bằng 0. | Discovery pattern sai hoặc tests bị skip. | Kiểm `failIfNoTests`/counts và CI policy. |
| Self-hosted runner không chạy action major mới. | Runner runtime/Node requirements không đáp ứng. | Nâng runner hoặc dùng version được hỗ trợ theo docs. |

### Trình tự triage gọn và chính xác

1. Xác định event, checkout SHA, runner OS/JDK/Maven versions.
2. Tìm **goal/module đầu tiên FAIL** trong log.
3. Kiểm tra test report XML được tạo chưa và số test thực chạy.
4. Nếu báo lỗi IT, đọc Failsafe XML/summary.
5. Nếu báo coverage, đọc JaCoCo XML/HTML và threshold config.
6. Xem cache/repository/profiles/flags có làm lệch local và CI không.
7. Giữ nguyên build failure status, không dùng skip flags để làm CI xanh giả.
8. Sau khi sửa, chạy lại đúng commit và workflow; không tuyên bố fix khi artifact upload PASS nhưng Maven verify vẫn fail.

## 21. Bài tập thực hành có đáp án

### Bài A — lifecycle

Hãy trả lời:

1. `mvn verify` có tự gọi clean không?
2. `mvn test` có bảo đảm Failsafe IT hoàn tất không?
3. Nếu Surefire FAIL ở test, JaCoCo XML tại verify đã được tạo chưa?
4. Vì sao `mvn integration-test` không phải mục tiêu CI thích hợp nếu dùng Failsafe?
5. `mvn install` và `mvn deploy` có cần trong CI kiểm PR không?

**Đáp án:** (1) Không. (2) Không. (3) Thường chưa, vì build dừng trước verify; phụ thuộc executions khác. (4) Chưa hoàn tất teardown/verify lifecycle. (5) Không bắt buộc; verify đủ cho kiểm chứng, publish là quy trình khác.

### Bài B — chạy Java 17 và xem reports

1. Tạo project theo mục 10 với `pom.xml`, `GreetingService.java`, `GreetingServiceTest.java` và `GreetingServiceIT.java`.
2. Kiểm tra `java -version` và `mvn --version`.
3. Chạy `mvn -B -ntp clean verify`.
4. Xác nhận Surefire chạy 4 tests; Failsafe chạy 1 test.
5. Mở `target/surefire-reports/TEST-demo.ci.GreetingServiceTest.xml`.
6. Mở `target/failsafe-reports/TEST-demo.ci.GreetingServiceIT.xml`.
7. Xem `target/site/jacoco/index.html` và `target/site/jacoco/jacoco.xml`.
8. Chạy `java -cp target/classes demo.ci.GreetingService`; xác nhận stdout `Hello Maven from CI`.
9. Giải thích vì sao Java main không tự được test chỉ do `mvn verify` đã chạy.
10. Nếu HTML coverage có đoạn chưa cover, quyết định có cần thêm unit test hay không theo policy.

### Bài C — build fail nhưng vẫn lưu reports

Trên branch lab tạm, đổi assertion của `createsGreeting` thành chuỗi kỳ vọng sai:

~~~java
assertEquals("Wrong greeting", service.greet("Maven"));
~~~

Commit/PR thay đổi thử nghiệm nếu thuộc repository đào tạo, quan sát:

- Maven fail ở unit-test phase.
- Surefire có report failure.
- Failsafe IT có thể chưa chạy và JaCoCo HTML report chưa được tạo.
- GitHub Actions step upload có `always()`, vẫn cố lưu Surefire XML.
- Job status cuối phải **FAIL**, không bị biến thành PASS.

Khôi phục assertion đúng rồi chạy lại. **Không đưa một lỗi giả vào nhánh release thật**.

### Bài D — thêm coverage gate

1. Bắt đầu từ POM có JaCoCo `prepare-agent` và `report`.
2. Thêm `jacoco:check` tại `verify` với `LINE/COVEREDRATIO >= 0.80` theo mục 14.
3. Chạy build và đối chiếu log check goal.
4. Trong bản sao, giảm coverage có chủ đích và xác nhận gate fail.
5. Khôi phục tests; không sửa threshold tùy tiện cho xanh.
6. Giải thích vì sao `jacoco.exec` không phải XML mà PR dashboard có thể parse trực tiếp.

### Bài E — thiết kế multi-module/matrix

Một repository có `api`, `core`, `service`, Java 17/21 matrix và integration tests chỉ ở service.

Hãy đề xuất:

- Full Reactor verify job chạy ở đâu?
- Khi chỉ test service, dùng `-pl :service -am` ra sao?
- Có nên bật `failIfNoTests=true` cho mọi `packaging=pom` parent không?
- Glob upload Surefire/Failsafe reports cần kiểu gì?
- Artifact name chứa những dimensions nào để tránh collision?
- Coverage aggregate phải làm thế nào để không lấy trung bình phần trăm sai?
- Khi một matrix job fail, merge policy xử lý ra sao?
- PR job có quyền publish/signing không?

**Định hướng:** một gate full Reactor ở commit phù hợp; chọn lọc phải bao gồm upstream; test-required policy theo module type; dùng `**/target/...` globs; unique per matrix; dùng JaCoCo aggregate đúng model; mọi required checks phải PASS; PR no release secrets.

## 22. Checklist đưa một Maven CI pipeline vào vận hành

**Checkout / toolchain:**

- [ ] Trigger push/PR và branch filters đúng.
- [ ] Checkout đúng commit/ref; SHA được ghi vào job logs.
- [ ] JDK vendor/version và Maven runtime được kiểm chứng.
- [ ] Compiler target phù hợp JDK.
- [ ] Wrapper scripts/distribution được review nếu dùng.
- [ ] Secrets/permissions không được cấp vượt nhu cầu.

**Build:**

- [ ] `mvn -B -ntp clean verify` thực sự được gọi.
- [ ] Không dùng `-DskipTests`, `-fn`, `|| true` trong required gate.
- [ ] Parent/plugins/executions được bind vào lifecycle dự định.
- [ ] Surefire và Failsafe thực sự discover số tests mong đợi.
- [ ] JaCoCo agent/report/check chạy đúng nếu policy yêu cầu.
- [ ] CI không dùng binary module cũ thay source hiện tại ngoài ý định.

**Kết quả:**

- [ ] Surefire/Failsafe XML được tạo ở đúng paths.
- [ ] JaCoCo XML/HTML được tạo khi verify đạt tới report phase.
- [ ] Upload step chạy dù build FAIL; không che Maven exit code.
- [ ] Không gán PASS nếu report không tồn tại hoặc test count = 0 ngoài policy.
- [ ] Report parser/PR annotations được cấu hình riêng nếu cần.
- [ ] Artifact names unique, retention và quyền tải phù hợp.
- [ ] Reports/logs không vô tình chứa secrets.
- [ ] Required status checks được branch protection sử dụng.

**Mở rộng:**

- [ ] Multi-module glob/report-aggregate đúng.
- [ ] Matrix JDK/OS jobs có nhãn và artifact names riêng.
- [ ] Flaky tests có nguyên nhân và evidence, không rerun để che failure.
- [ ] Caches không làm nhiễm privileged publish job.
- [ ] Publish/release tách khỏi PR verify và dùng approved commit/tag.
- [ ] Build pipeline được review khi thay POM, plugins, wrapper hoặc CI workflow.

## 23. Kết luận

Một Maven CI đáng tin cậy không kết thúc ở "Maven chạy xong". Nó tạo **chuỗi bằng chứng** từ commit đã checkout đến kết quả thực thi của các quality gates và reports có thể đọc lại.

~~~text
Checkout đúng source
     │
     ▼
JDK/Maven rõ phiên bản + cache có kiểm soát
     │
     ▼
clean verify
  ├── Surefire unit tests → TEST-*.xml
  ├── Failsafe IT tests → TEST-*.xml + summary
  └── JaCoCo → jacoco.exec + jacoco.xml + HTML
     │
     ├──────── Build PASS ────────┐
     │                            │
     └──────── Build FAIL ────────┤
                                  ▼
                      Upload reports always()
                                  │
                                  ▼
                   Status check + triage + audit
~~~

Ghi nhớ bảy điểm:

1. **Checkout SHA và JDK/Maven** là một phần kết quả kiểm chứng, không phải thông tin phụ.
2. **`clean verify`** chạy cleanup và lifecycle đến verify, không tự publish artifact.
3. **Surefire ở test, Failsafe ở integration-test/verify**; đặt tên test class và bind goals đúng.
4. **JaCoCo report khác JaCoCo check**: có HTML/XML chưa đồng nghĩa đã enforcement threshold.
5. **Upload reports sau failure** giúp debug, nhưng `always()` không tạo file chưa tồn tại và không được che failure status.
6. **Cache, multi-module và matrix** cần phạm vi rõ để không xác nhận nhầm các modules/versions chưa được kiểm tra.
7. **An toàn CI quan trọng như quality CI**: untrusted pull request không được nhận quyền release, token ký hoặc cache privileged.

Khi làm tốt, CI trả lời không chỉ "xanh/đỏ", mà còn "xanh/đỏ **vì đâu, bằng chứng gì, trong môi trường nào, trên commit nào**".

## Tài liệu chính thức và tham khảo kỹ thuật

- Apache Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven — Guide to Working with Multiple Modules: https://maven.apache.org/guides/mini/guide-multiple-modules.html
- Apache Maven — POM Reference: https://maven.apache.org/pom.html
- Apache Maven Surefire Plugin — reports and goals: https://maven.apache.org/surefire/maven-surefire-plugin/
- Apache Maven Failsafe Plugin — lifecycle, reports, summary: https://maven.apache.org/surefire/maven-failsafe-plugin/
- JaCoCo Maven Plugin — goals: https://www.jacoco.org/jacoco/trunk/doc/maven.html
- JaCoCo — prepare-agent goal: https://www.jacoco.org/jacoco/trunk/doc/prepare-agent-mojo.html
- JaCoCo — report goal: https://www.jacoco.org/jacoco/trunk/doc/report-mojo.html
- JaCoCo — check goal: https://www.jacoco.org/jacoco/trunk/doc/check-mojo.html
- GitHub Actions — Checkout action: https://github.com/actions/checkout
- GitHub Actions — Set up Java action and Maven caching: https://github.com/actions/setup-java
- GitHub Actions — Upload artifact action: https://github.com/actions/upload-artifact
- GitHub Docs — Workflow syntax and job status checks: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- GitHub Docs — Secure use of GitHub Actions: https://docs.github.com/en/actions/reference/security/secure-use
- Apache Maven Wrapper: https://maven.apache.org/tools/wrapper/
