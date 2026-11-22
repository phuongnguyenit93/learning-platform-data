# Tái hiện lỗi với POM tối thiểu và lưu bằng chứng trước khi sửa trong Maven

## 1. Tại sao phải tái hiện trước khi sửa?

Một dự án Java báo lỗi khi chạy `mvn clean verify` trên CI. Developer lập tức xóa cache `~/.m2/repository`, nâng nhiều plugin và dependency, đổi JDK, rồi chạy lại thấy `BUILD SUCCESS`. Kết quả trông tốt, nhưng vẫn còn ba câu hỏi: **lỗi ban đầu thực sự là gì, thay đổi nào đã sửa nó, và người khác có thể kiểm chứng kết luận đó không?**

Một quy trình chẩn đoán tốt không bắt đầu bằng chỉnh đại trà. Nó bắt đầu bằng bảo toàn trạng thái lỗi, viết ra **failure signature**, sau đó tạo **minimal reproducible example (MRE)**: tập hợp POM, source, test, data và điều kiện môi trường nhỏ nhất mà vẫn tạo **cùng lỗi gốc**. Khi đã có MRE ổn định, sửa một nguyên nhân và chạy đối chứng mới cho phép khẳng định bản sửa có tác dụng.

Bài Knowledge thuộc nhóm **Chẩn đoán lỗi** với đề mục **Tái hiện lỗi với POM tối thiểu và lưu bằng chứng trước khi sửa**. Nội dung bao gồm:

1. Thu thập Maven command, commit SHA, working-tree state, JDK/Maven versions, plugin goal và report trước khi chỉnh sửa.
2. Phân biệt triệu chứng, lỗi gốc, failure signature, giả thuyết và kết luận có bằng chứng.
3. Rút dự án Maven nhiều module/parent/profile về POM tối thiểu **mà vẫn giữ hành vi lỗi**.
4. Bảo vệ `target/surefire-reports`, `target/failsafe-reports` và log trước khi `clean` xóa chúng.
5. Dùng Maven `-e`, `-X`, Help Plugin, Dependency Plugin và local repository riêng khi cần.
6. Thực hành Java 17 + JUnit 5 với lỗi có chủ đích: test mong đợi 4 nhưng code trả 3.
7. Lưu bằng chứng trước/sau, sửa đúng một dòng và chứng minh chuyển `BUILD FAILURE` thành `BUILD SUCCESS`.
8. Hiểu đặc thù của lỗi network, dependency conflict, parent/BOM, Windows/CI, SNAPSHOT, flaky/parallel tests.
9. Thiết kế CI để upload reports khi build fail mà không che Maven exit status.
10. Chia sẻ một bug report tái hiện được, không lộ passwords, tokens hoặc source nội bộ.

**Môi trường ví dụ:** Maven 3.8+, JDK 17+, Maven Compiler Plugin 3.13.0, Surefire Plugin 3.5.4, Maven JAR Plugin 3.4.2, JUnit Jupiter 5.11.4. Những phiên bản này được ghim cho bài tập; không có tuyên bố chúng luôn là bản mới nhất.

## 2. Triệu chứng khác nguyên nhân gốc

### Triệu chứng

Một lần build có thể in:

~~~text
[ERROR] Failed to execute goal ...
[INFO] BUILD FAILURE
~~~

Đó là **kết luận Maven không hoàn tất**. Nó chưa nói nguyên nhân là source code, Maven settings, compiler, tests hay remote repository.

Một trường hợp xác định hơn:

~~~text
Test: demo.repro.AdderTest.addsTwoNumbers
expected: <4> but was: <3>
Tests run: 1, Failures: 1, Errors: 0, Skipped: 0
BUILD FAILURE
~~~

Dòng trên là **trích đoạn kết quả dự kiến** của bài thực hành dưới đây, không phải log lấy từ một máy cụ thể.

### Failure signature

Để xác nhận hai lần build bị **cùng một lỗi**, ghi:

~~~text
Maven phase/goal: test / maven-surefire-plugin:test
Module: demo.repro:adder-repro
Exception type: org.opentest4j.AssertionFailedError
Test: demo.repro.AdderTest.addsTwoNumbers
Expected/actual: 4 / 3
Maven exit status: nonzero
Reports: Surefire XML có 1 failure
~~~

Timestamp, duration, thứ tự stack frames và số phiên bản trong log có thể khác; những điều đó chưa chắc làm thay đổi bản chất lỗi. Nhưng **một lần fail vì không resolve được JUnit** và **một lần fail vì assertion 4/3** không được coi là cùng lỗi chỉ vì cùng in `BUILD FAILURE`.

### Giả thuyết và root cause

Nếu code có:

~~~java
return left + right - 1;
~~~

trong hàm cộng, một giả thuyết hợp lý là `- 1` tạo ra mismatch. Chỉ sau khi đổi thành `left + right`, chạy **cùng test, cùng lệnh, điều kiện tương đương**, kiểm outcome và số test, bạn mới có bằng chứng mạnh rằng đó là nguyên nhân trong demo.

Không kết luận nguyên nhân từ một dòng lỗi đơn lẻ: một `ClassNotFoundException` có thể do dependency thiếu, scope, classloader hoặc test runtime; một 401 có thể do nhiều cấu hình credentials khác nhau.

## 3. Chuỗi công việc đúng thứ tự

~~~text
Xảy ra lỗi
   │
   ▼
Ghi nhận source/commit + môi trường + lệnh + exit
   │
   ▼
Lưu log và reports TRƯỚC khi xóa target hoặc chạy lại
   │
   ▼
Xác định failing module, goal, phase và signature
   │
   ▼
Tạo bản reproduction cách ly, không phá bản gốc
   │
   ▼
Giảm POM/source/test/fixtures từng phần
   │
   ▼
MRE vẫn thất bại với CÙNG signature
   │
   ▼
Sửa một nguyên nhân và chạy lại
   │
   ├── Vẫn fail / lỗi khác → tiếp tục điều tra
   │
   └── PASS cùng test count → kiểm đối chứng
                      │
                      ▼
             Full project/CI regression
                      │
                      ▼
           Báo cáo kèm evidence trước/sau
~~~

**Điều quan trọng:** `mvn clean verify` có thể xóa `target` trước khi chạy các phases mới. Vì vậy các file report cũ đang trong `target` cần được copy ra thư mục độc lập **trước** khi bạn thêm `clean`, sửa code hoặc rerun.

Đừng coi việc có một lần xanh là chứng minh tuyệt đối đối với lỗi flaky; phải ghi số lần thử và tần suất.

## 4. Snapshot bằng chứng ban đầu

Một bộ thông tin tối thiểu:

| Thành phần | Lý do lưu |
| --- | --- |
| Commit SHA và Git status | Chỉ đúng tree đang lỗi, kể cả thay đổi chưa commit. |
| OS/architecture/shell | Phân biệt Windows/Linux, path và native tool. |
| `java -version` | JDK version/vendor đang chạy. |
| `mvn --version` | Maven version và Java runtime Maven thực sự dùng. |
| Maven command nguyên văn | `-P`, `-D`, `-pl`, `-am`, `-T` thay hành vi. |
| Maven log/exit code | Thấy goal fail và xác nhận status. |
| Surefire/Failsafe XML | Số tests/failures/errors/skipped và stack trace. |
| Effective POM/profiles (khi cần) | Hiểu inherited plugin config và profile. |
| Dependency tree (khi cần) | Hiểu resolved version/scopes/exclusions. |
| Cache/repository state (khi liên quan) | Phân biệt SNAPSHOT/stale cache/mirror. |
| Thời điểm và run ID | Lỗi phụ thuộc network/service có thể đổi theo thời gian. |

Các lệnh **chỉ để nhận diện môi trường** khi repository đã được review và cho phép chạy:

~~~bash
git rev-parse HEAD
git status --short
java -version
mvn --version
~~~

`git rev-parse HEAD` chỉ phản ánh commit; source chưa commit cần được ghi riêng. Nếu đang trên CI PR, cũng cần biết checkout là PR head hay merge ref. Không đưa toàn bộ diff chứa source nội bộ lên public issue chỉ để “đủ bằng chứng”.

### Cảnh báo an toàn

Maven plugins, core extensions trong `.mvn/extensions.xml`, Maven Wrapper và tests có thể chạy mã. Với repository lạ hoặc PR chưa tin, **static-review trước khi chạy** rồi dùng runner cô lập, không có publishing/cloud/signing secrets. Kể cả `mvn help:effective-pom` vẫn khởi chạy Maven/Help Plugin và có thể nạp extensions. Chẩn đoán không phải lý do để chạy code chưa tin cậy với quyền cao.

## 5. Phân loại lỗi để chọn đúng cách rút POM

| Nhóm | Dấu hiệu thường gặp | Phần cần giữ trong MRE |
| --- | --- | --- |
| Model/XML | `Non-parseable POM`, malformed plugin. | POM bytes/config liên quan. |
| Parent/BOM | `Non-resolvable parent POM`, imported BOM lỗi. | Parent coordinates, relativePath, repository. |
| Dependency resolution | `Could not resolve dependencies`. | GAV, versions, repo/mirror/settings đã ẩn secrets. |
| Plugin resolution | `No plugin found`, goal prefix không resolve. | Plugin GAV, `pluginRepositories`, metadata. |
| Compiler | `release version not supported`, compilation error. | JDK/compiler plugin/source/target. |
| Annotation processing | Generated symbols missing. | Processor plugin/dependency/version. |
| Unit test | Assertion hoặc test exception. | Test source, fixture, Surefire/JUnit. |
| Integration test | Service timeout/DB error. | Failsafe, service/port/schema/fixture. |
| Packaging | Missing class/resources, wrong manifest. | Packaging plugins và paths. |
| Multi-module | Sử dụng stale module artifact. | Parent/modules và dependency edges. |
| CI-only | Local PASS, CI FAIL. | Runner/JDK/Maven/profiles/cache/OS. |
| Parallel/flaky | Fail phụ thuộc timing. | `-T`, forks, ports, test data/shared state. |
| Network/auth | HTTP 401/403/404/429, timeout. | Endpoint/policy, proxy, auth mapping. |

MRE **không nhất thiết chỉ gồm một `pom.xml`**. Nếu lỗi do parent inheritance, repository token, TLS truststore, database hoặc wrapper, loại bỏ hoàn toàn điều kiện đó sẽ làm mất lỗi cần tái hiện.

### Minimal, complete, reproducible

Một trường hợp tái hiện tốt cần đồng thời:

- **Minimal:** loại bỏ những phần không cần.
- **Complete:** có đủ POM/source/data/instructions để chạy.
- **Reproducible:** người khác thấy cùng failure signature theo điều kiện mô tả.
- **Faithful:** không biến lỗi test thành lỗi thiếu dependency khác.
- **Safe:** không kèm credentials, private keys, PII hoặc dữ liệu nội bộ không được phép công bố.

## 6. Cách giảm dự án lớn thành MRE

### Giữ nguyên trường hợp lỗi đầu tiên

Trong tổ chức, tốt nhất tạo bản sao checkout/branch/worktree được kiểm soát hoặc snapshot ở thư mục riêng. Đừng `git reset --hard`, xóa source hay xóa target evidence trên working tree đang điều tra. Nếu có changes chưa commit, lưu chúng theo quy trình cho phép trước khi thu nhỏ.

### Giảm từng thành phần

1. Chạy lệnh gốc và ghi signature.
2. Loại một dependency **không được sử dụng**; chạy lại.
3. Nếu signature vẫn giống, giữ việc giảm. Nếu lỗi biến mất, hoàn nguyên.
4. Tiếp tục với plugin configuration, profile, source/test fixture không liên quan.
5. Chỉ bỏ parent POM nếu bạn đã tái tạo được effective settings/config liên quan trong bản độc lập.
6. Với multi-module, thử tối thiểu modules + upstream cần thiết.
7. Nếu failure chuyển thành lỗi “cannot resolve parent/dependency”, đừng gọi đó là thành công; khôi phục phần đã loại.
8. Khi không thể giảm thêm mà vẫn thấy cùng lỗi, đóng băng MRE và viết instructions.

Một **bản thu gọn PASS** thường chỉ chứng minh bạn **đã bỏ yếu tố gây lỗi**, chứ chưa phải MRE thành công. MRE của một bug cần **FAIL một cách xác định** trước khi sửa.

### Chỉ giảm một biến mỗi lần

Ví dụ nếu đồng thời thay Compiler Plugin, JDK, Surefire, parent POM và dependency versions rồi build PASS, bạn mất khả năng quy kết. Nên dùng **delta debugging**: mỗi thử nghiệm đổi một biến/nhóm nhỏ, ghi lại sự khác biệt và outcome.

### Khi phải giữ nhiều modules

Giả sử:

~~~text
root/
├── pom.xml                # aggregator, parent
├── api/pom.xml
├── core/pom.xml           # phụ thuộc api
├── service/pom.xml        # phụ thuộc core
└── integration/pom.xml    # test toàn hệ thống
~~~

Với lỗi compile/test trong service, có thể thử:

~~~bash
mvn -B -ntp -pl :service -am clean verify
~~~

`-pl` chọn module; `-am` thêm các upstream dependencies trong Reactor. Nhưng lệnh này **không chứng minh các modules khác đã được verify**, và không tái hiện lỗi thuộc integration module/aggregator nếu chúng chưa được chọn.

## 7. MRE runnable: Java 17, một lỗi JUnit có thể tái hiện ổn định

Ta tạo dự án nhỏ **không phụ thuộc database, network services hoặc Docker**:

~~~text
maven-minimal-repro/
├── pom.xml
├── src/
│   ├── main/java/demo/repro/Adder.java
│   └── test/java/demo/repro/AdderTest.java
└── evidence/                  # Thư mục do bạn tạo sau, ngoài target
~~~

Source có một lỗi có chủ đích: tính `left + right - 1` thay vì `left + right`. Test kỳ vọng 4 cho input 2,2. Điều này cho phép so **failure → fix → pass** mà không cần kỹ thuật phức tạp.

### 7.1. `pom.xml` đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo.repro</groupId>
    <artifactId>adder-repro</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

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
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
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
                    <rerunFailingTestsCount>0</rerunFailingTestsCount>
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

**Giải thích:**

- `groupId/artifactId/version` định danh MRE riêng, không trỏ một thư viện production.
- `packaging=jar` cung cấp default Java lifecycle bindings.
- `maven.compiler.release=17` đặt bytecode/API target; không tự chọn JVM chạy Maven.
- JUnit Jupiter chỉ dùng trong `test` scope.
- Surefire 3.5.4 hỗ trợ JUnit 5 và tạo XML reports.
- `failIfNoTests=true` chống tình huống build “xanh” do không discover tests.
- `rerunFailingTestsCount=0` tránh test FAIL rồi PASS trong một lần rerun gây nhiễu kết luận.
- Các plugin versions ghim làm reproduction đáng tin hơn giữa các máy.

Đây là POM hoàn chỉnh. Với lỗi Maven thật, mục tiêu là giữ **ít plugin nhất mà vẫn tạo ra triệu chứng**, không ép dự án nào cũng phải có y hệt bộ plugin trên.

### 7.2. `src/main/java/demo/repro/Adder.java` — mã có lỗi cố ý

~~~java
package demo.repro;

public final class Adder {
    private Adder() {
    }

    public static int add(int left, int right) {
        return left + right - 1;
    }

    public static void main(String[] args) {
        System.out.println(add(2, 2));
    }
}
~~~

Logic hiện tại trả `3` cho hai số `2`, `2`. Đây là lỗi nghiệp vụ giả lập, không phải lỗi Maven bản thân; Maven/Surefire giúp **tái hiện và ghi bằng chứng**.

### 7.3. `src/test/java/demo/repro/AdderTest.java`

~~~java
package demo.repro;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AdderTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(4, Adder.add(2, 2));
    }
}
~~~

Tên `AdderTest` khớp naming pattern của Surefire. Test kỳ vọng `4`, implementation trả `3` nên phải FAIL ổn định khi Java/Maven/JUnit được cấu hình đúng.

### 7.4. Chạy lần lỗi đầu

Từ thư mục `maven-minimal-repro`:

~~~bash
java -version
mvn --version
mvn -B -ntp clean verify
~~~

Maven đi qua compile/test-compile rồi Surefire chạy `AdderTest.addsTwoNumbers` tại phase `test`. Vì assertion FAIL, `verify` không hoàn thành và Maven không đạt `package` thành công.

**Trích đoạn log dự kiến (không phải nguyên văn toàn bộ terminal):**

~~~text
org.opentest4j.AssertionFailedError:
expected: <4> but was: <3>
Tests run: 1, Failures: 1, Errors: 0, Skipped: 0
BUILD FAILURE
~~~

Kết quả cần kiểm chứng: **1 test thực sự chạy; 1 failure; Maven exit code khác 0**. Nếu build thay vào đó báo không tải được JUnit, đó là **lỗi dependency resolution**, không phải successful reproduction của bài.

### 7.5. Chạy Java trực tiếp để thấy actual value

Nếu compilation đã hoàn tất:

~~~bash
java -cp target/classes demo.repro.Adder
~~~

**Stdout chính xác của bản lỗi:**

~~~text
3
~~~

Lưu ý: `target/classes` chỉ có sau khi compiler chạy thành công. Nếu Maven fail từ bước đọc POM hoặc tải dependency trước compiler, lệnh Java có thể không chạy; đó là một điều kiện thí nghiệm khác.

## 8. Lưu bằng chứng **trước** khi sửa một dòng

Nên đặt `evidence/` ở root project **ngoài `target/`**. Lần chạy `clean` tiếp theo có thể xóa `target/surefire-reports` cũ.

### 8.1. Bash trên Linux/macOS

Trong terminal tương tác tại root MRE:

~~~bash
mkdir -p evidence
java -version > evidence/java-version.before.txt 2>&1
mvn --version > evidence/maven-version.before.txt 2>&1
mvn -B -ntp clean verify > evidence/verify-before.log 2>&1
printf '%s\n' "$?" > evidence/verify-before-exit.txt
~~~

**Quan trọng:** `printf` phải chạy **ngay sau Maven**, vì `$?` luôn chứa exit status của command gần nhất. Trong script đang bật `set -e`, Maven FAIL có thể khiến shell dừng trước khi lưu exit; hãy chủ động dùng `if ...; then ...; else ...; fi` hoặc kiểm soát `errexit` để lưu đủ bằng chứng.

Sau khi Maven đã chạy tới Surefire, copy reports:

~~~bash
cp target/surefire-reports/TEST-demo.repro.AdderTest.xml evidence/TEST-demo.repro.AdderTest.before.xml
cp target/surefire-reports/demo.repro.AdderTest.txt evidence/AdderTest.before.txt
~~~

Chỉ copy nếu files thực sự tồn tại, không tự tạo một XML giả nếu không có report. Plugin config có thể thay `reportsDirectory` hoặc suffix.

### 8.2. Windows PowerShell 5.1/7

~~~powershell
New-Item -ItemType Directory -Force evidence | Out-Null
java -version *> evidence\java-version.before.txt
mvn --version *> evidence\maven-version.before.txt
mvn -B -ntp clean verify *> evidence\verify-before.log
$verifyExit = $LASTEXITCODE
Set-Content evidence\verify-before-exit.txt $verifyExit
Copy-Item target\surefire-reports\TEST-demo.repro.AdderTest.xml evidence\TEST-demo.repro.AdderTest.before.xml
~~~

PowerShell redirection `*>` ghi nhiều streams vào file, với encoding/format phụ thuộc PowerShell version; kiểm file log khi cần chia sẻ với parser. `$LASTEXITCODE` phải được chụp ngay sau native command `mvn`. Trong CI, job phải trả về trạng thái thực của Maven; không được chỉ lưu log rồi mặc định success.

### 8.3. Dấu vết cần bảo toàn

Một case record nên gồm:

~~~text
case: adder-repro
source: demo project Adder.java before fix
command: mvn -B -ntp clean verify
jdk: see java-version.before.txt
maven: see maven-version.before.txt
test: demo.repro.AdderTest.addsTwoNumbers
failure: expected 4, actual 3
test count: 1
maven exit: nonzero, see verify-before-exit.txt
logs: verify-before.log
reports: TEST-demo.repro.AdderTest.before.xml
status: reproduced before fix, not yet repaired
~~~

Đây là mẫu mô tả kết quả mong đợi, không phải một log đã được chạy trong môi trường người đọc. Nếu dự án bắt nguồn từ Git, thêm SHA của commit và thông tin thay đổi chưa commit — dữ liệu nhạy cảm phải được kiểm trước khi công bố.

### 8.4. Ghi hash evidence khi cần

Trên Linux/macOS:

~~~bash
sha256sum evidence/verify-before.log
sha256sum evidence/TEST-demo.repro.AdderTest.before.xml
~~~

Windows PowerShell dùng `Get-FileHash`. Giá trị digest phụ thuộc bytes thật, không có một hash cố định cho ví dụ. Việc hash giúp phát hiện file evidence bị thay sau khi lưu; nếu nguồn hash và file đều do attacker kiểm soát, checksum **không tự xác thực tác giả**.

## 9. Đọc XML: không chỉ tìm “BUILD FAILURE”

Surefire mặc định lưu test results dưới:

~~~text
target/surefire-reports/
    TEST-demo.repro.AdderTest.xml
    demo.repro.AdderTest.txt
~~~

XML có các thông tin `tests`, `failures`, `errors`, `skipped` và chi tiết `testcase`. Ví dụ **fragment minh họa**:

~~~xml
<testsuite
    name="demo.repro.AdderTest"
    tests="1"
    failures="1"
    errors="0"
    skipped="0">
    <testcase
        classname="demo.repro.AdderTest"
        name="addsTwoNumbers">
        <failure message="expected: &lt;4&gt; but was: &lt;3&gt;"/>
    </testcase>
</testsuite>
~~~

Đây **không phải file XML Surefire hoàn chỉnh**; file thật thường có duration, properties, provider metadata và stack trace khác nhau.

Hãy phân biệt:

- **Failure:** assertion không đạt (ví dụ demo).
- **Error:** exception khác trong test/setup/teardown.
- **Skipped:** test bị bỏ qua, chưa được xem là PASS.
- **No reports:** build có thể fail trước `test`, hoặc report path đã được override.
- **Zero tests:** test chưa được discover; với MRE yêu cầu test thì kết quả này không đạt.
- **One matching failure:** test lỗi đúng ý đồ và có dữ liệu để so đối chứng.

**Cùng số tests và cùng test identifier** rất quan trọng. Một “fix” làm số tests từ 1 về 0 có thể khiến build xanh giả nếu plugin không enforce điều kiện no-tests.

## 10. Sửa đúng một biến và chạy lại

Đã snapshot evidence, giờ mới sửa `src/main/java/demo/repro/Adder.java`.

**Trước:**

~~~java
return left + right - 1;
~~~

**Sau:**

~~~java
return left + right;
~~~

Không thay đổi test assertion, plugin version, POM, JDK hay command cùng lúc. Nếu làm vậy, kết quả trước/sau ít có giá trị quy kết.

Chạy:

~~~bash
mvn -B -ntp clean verify
~~~

**Log summary dự kiến:**

~~~text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Sau khi build PASS, chạy:

~~~bash
java -cp target/classes demo.repro.Adder
~~~

**Stdout chính xác sau sửa:**

~~~text
4
~~~

Hai bằng chứng độc lập: Surefire test PASS cùng assertion, và chương trình in đúng kết quả.

### Lưu báo cáo sau sửa

Linux/macOS:

~~~bash
mvn -B -ntp clean verify > evidence/verify-after.log 2>&1
printf '%s\n' "$?" > evidence/verify-after-exit.txt
cp target/surefire-reports/TEST-demo.repro.AdderTest.xml evidence/TEST-demo.repro.AdderTest.after.xml
~~~

Windows:

~~~powershell
mvn -B -ntp clean verify *> evidence\verify-after.log
$verifyExit = $LASTEXITCODE
Set-Content evidence\verify-after-exit.txt $verifyExit
Copy-Item target\surefire-reports\TEST-demo.repro.AdderTest.xml evidence\TEST-demo.repro.AdderTest.after.xml
~~~

Không xóa `*.before.*` khi chạy lại. Nếu muốn chứng minh nguyên nhân ở mức mạnh hơn, thực hiện phép đối chứng trong **bản sao sạch**: phục hồi duy nhất dòng sai rồi thấy test FAIL trở lại, sau đó áp lại dòng đúng và thấy PASS. Đừng thử đảo code trên nhánh release đang được dùng.

### Bảng đối chứng

| Tiêu chí | Trước sửa | Sau sửa |
| --- | --- | --- |
| JDK/Maven/POM | Giữ nguyên | Giữ nguyên |
| Source expression | `left + right - 1` | `left + right` |
| Command | `mvn -B -ntp clean verify` | Cùng command |
| Unit tests | 1 chạy / 1 fail | 1 chạy / 0 fail |
| Expected/actual | 4 / 3 | 4 / 4 |
| Java stdout | `3` | `4` |
| Maven | `BUILD FAILURE` | `BUILD SUCCESS` |
| Evidence | `verify-before.log`, XML before | `verify-after.log`, XML after |

**MRE PASS chưa chứng minh production codebase PASS.** Sau khi biết nguyên nhân, phải áp fix trong dự án thật, chạy full Maven Reactor, active CI profiles, integration tests và quality gates liên quan.

## 11. Khi nào thêm Maven `-e` và `-X`?

Maven có hai mức chẩn đoán:

~~~bash
mvn -B -ntp -e clean verify
mvn -B -ntp -X clean verify
~~~

- `-e`/`--errors` bổ sung stack traces để thấy exception chains.
- `-X`/`--debug` bật log chi tiết, hữu ích cho plugin resolution, parameters, classpath, repository và Maven internals.

**Trình tự khuyến nghị:**

1. Lệnh gốc và exit code.
2. First failing module/goal và các test XML.
3. Nếu cần stack trace đầy đủ, `-e`.
4. Nếu vẫn không đủ, `-X` trên môi trường cô lập.
5. Rà soát/redact logs trước khi gửi cho người ngoài.

Không tự động upload raw `-X` logs: chúng có thể chứa internal repository URLs, system properties, usernames, paths, các tham số plugin và thậm chí dữ liệu bí mật do scripts/plugins in ra. Maven có thể che một số fields, nhưng không bảo đảm toàn bộ plugin logging đều an toàn.

**Nếu lỗi đã rõ là expected 4 actual 3, chưa cần -X.** Log dài hơn không làm root cause rõ hơn trong demo.

## 12. Maven Help Plugin: xem cấu hình thực được áp dụng

Một project lớn có thể inherit plugin execution/version từ parent hoặc active profiles. Sau khi code/project đủ tin cậy để chạy Maven, dùng Help Plugin ghim version:

~~~bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose -Doutput=evidence/effective-pom.xml
~~~

`-Dverbose` yêu cầu ghi chú nguồn gốc cấu hình, có thể giúp xác định một plugin version đến từ parent/super POM hay cấu hình hiện tại.

Xem active profiles:

~~~bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
~~~

**Giới hạn:**

- Effective POM phản ánh active profiles và properties của invocation hiện tại.
- Nếu lỗi chỉ xuất hiện với `-Pci` hoặc một property, phải giữ chúng khi chạy diagnostics.
- Output có thể chứa private/internal URLs hoặc properties; kiểm trước khi share.
- Help Plugin cũng là một executable Maven goal, không phải static parser hoàn toàn an toàn trên POM chưa review.
- Effective POM không thay thế source POM và không tự cung cấp lịch sử của binary Maven plugin.

### Vì sao snapshot effective POM có ích?

Khi user báo “POM con không hề khai báo plugin X”, thực tế plugin X có thể đến từ parent `build/plugins`. Với MRE, cần chép cấu hình liên quan của plugin đó hoặc giữ parent; bỏ parent khiến lỗi biến mất có thể chỉ là vì plugin không còn chạy.

## 13. Maven Dependency Plugin: khi lỗi liên quan GAV/scopes

Với lỗi `NoSuchMethodError`, `ClassNotFoundException`, wrong SLF4J/Guava/JUnit provider, một resolved dependency tree là bằng chứng hữu ích:

~~~bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -DoutputType=text -DoutputFile=evidence/dependency-tree.txt
~~~

Maven Dependency Plugin goal `tree` mô tả dependency graph có scope/versions. Đây không phải BOM build-plan hoàn chỉnh; nó cũng **không nhất thiết liệt kê plugin runtime dependencies và core extensions**.

Nếu Maven không resolve được parent/dependency ngay từ đầu, `dependency:tree` có thể cũng fail. Khi đó cần giữ resolver log, POM/GAV, repository settings đã sanitized, **không tạo dependency tree tưởng tượng**.

### Snapshot version và dependency mediation

Một library được khai báo cùng tên nhưng ở version khác có thể được Maven dependency mediation chọn dựa trên nearest-definition/management. MRE chỉ giữ direct dependency có thể mất conflict. Hãy giữ **đường dẫn transitive dẫn đến version bị chọn** và kiểm resolved tree.

### Repository/settings

Một dependency nội bộ chỉ resolve qua corporate mirror hoặc private server thì MRE public không thể trỏ URL với token thật. Có thể thiết lập fixture repository thử nghiệm, mô tả sơ bộ repository policy và cung cấp log đã ẩn thông tin. Nếu không thể tái hiện ngoài môi trường riêng, báo giới hạn đó thẳng thắn.

## 14. Cache, offline, update và tác động đến reproduction

### Không xóa local Maven cache một cách mù quáng

`~/.m2/repository` chứa dependencies, plugin artifacts và metadata. Nó có thể liên quan lỗi stale SNAPSHOT/corrupt artifact nhưng cũng là bằng chứng về binary đã dùng.

Thử cache độc lập:

~~~bash
mvn -B -ntp -Dmaven.repo.local=./.repro-m2 clean verify
~~~

Đây là một **thí nghiệm có chủ đích**: Maven có thể tải lại artifacts vào `.repro-m2`, kết quả khác lần đầu vì cache/repository state thay đổi. Ghi rõ điều kiện và không coi nó tương đương exact original run.

### `-o` và `-U`

~~~bash
mvn -o clean verify
mvn -U clean verify
~~~

- `-o` yêu cầu Maven resolver chạy offline; nếu cache thiếu artifact/plugin thì có thể FAIL theo nguyên nhân mới. Không phải sandbox ngăn plugin/script có sẵn chạy.
- `-U` yêu cầu kiểm lại updates theo Maven snapshot/update behavior, không sửa sai GAV/quyền repo.

Nếu một lệnh tạo outcome khác, đó là **một dữ kiện mới để điều tra**. Không âm thầm thêm flags rồi kết luận lỗi gốc đã được tái hiện.

### Maven Wrapper

Dự án dùng Maven Wrapper `./mvnw` có thể chạy phiên bản Maven khác system `mvn`. Nếu lỗi chỉ trên Wrapper, MRE cần giữ scripts/properties/URL/digest phù hợp. Wrapper cũng là executable input; static-review trước khi chạy repo lạ.

## 15. Các nhóm lỗi không thể tái hiện trung thực chỉ bằng POM

### Lỗi JDK/toolchain

Nếu POM yêu cầu Java release 21 nhưng runner đang dùng JDK 17, lỗi compiler có thể là `release version 21 not supported`. Đừng tự đổi `maven.compiler.release` về 17 ngay mà chưa xác định project thật yêu cầu Java mấy và toolchain mục tiêu. MRE cần ghi **JDK runtime của Maven**, compiler plugin và release target.

### Lỗi network/permissions

HTTP 401/403/404/429 hay TLS timeout có thể phụ thuộc remote server, corporate proxy, cert truststore và token scope. Một POM chạy xanh trên network khác chưa chứng minh fix.

- 401: có vấn đề authentication/credentials hoặc server policy.
- 403: access bị từ chối theo quyền/policy.
- 404: artifact/endpoint không thấy, đôi lúc do policy ẩn.
- 429: rate limit.
- Timeout/5xx: network/server hoặc infrastructure issues.

Không chia sẻ credentials hay truy vấn endpoint production chỉ để làm MRE public. Nếu service chỉ có trong intranet, mô tả điều kiện hoặc tạo stub hợp pháp.

### Lỗi Failsafe/database/containers

Integration tests có thể dùng DB schema, port cố định, Docker/Testcontainers, files, service lifecycle. Một MRE đúng có thể cần một test container hoặc fixture nhỏ **có nguồn gốc/giấy phép và dữ liệu giả**. Không copy production DB snapshot chứa dữ liệu nhạy cảm.

### Lỗi Windows/Linux

File paths, case sensitivity, separators, locale/line endings và native executables có thể đổi behavior. Khi lỗi chỉ trên Windows, MRE phải được chạy đúng Windows shell/toolchain; không tuyên bố “không tái hiện” vì Linux chạy xanh.

## 16. Lỗi flaky: bảo lưu tần suất chứ không chỉ ảnh chụp

Một lỗi đôi khi fail có thể phụ thuộc timing, `-T`, Surefire forks, test order, port, DB schema hoặc network load.

Với **project đã review, test không có side effects ngoài dự kiến**, loop trên Bash:

~~~bash
for i in 1 2 3 4 5; do
  echo "Trial $i"
  mvn -B -ntp clean verify || {
    echo "Failure in trial $i"
    break
  }
done
~~~

PowerShell:

~~~powershell
1..5 | ForEach-Object {
    Write-Host "Trial $_"
    mvn -B -ntp clean verify
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failure in trial $_"
        break
    }
}
~~~

Nếu 5/5 PASS, vẫn không có bằng chứng tuyệt đối là race đã biến mất; thống kê failure frequency và đối chứng với serial/parallel trong điều kiện tương đương. Khi cần, tăng số lần thử theo chi phí và mức nghiêm trọng, tránh dùng loop cho `deploy` hoặc hoạt động ghi production.

Đặc biệt:

- `-T 1` so với `-T 2`/`-T 4` kiểm reactor concurrency.
- `forkCount` kiểm JVM forks.
- JUnit parallel execution kiểm concurrency của test methods/classes.
- `rerunFailingTestsCount` có thể giúp nhận diện flaky tests nhưng **có thể che outcome cuối** nếu chỉ nhìn build status.
- Một test PASS khi rerun chưa chứng minh nguyên nhân đã được sửa.

Ghi tần suất ví dụ “3/20 lần báo BindException ở -T 2; 0/20 khi -T 1” thay vì “đôi lúc fail”. Đồng thời kiểm hidden shared resources và bằng chứng XML/log mỗi lần fail.

## 17. CI lưu kết quả khi `verify` FAIL

Trong GitHub Actions, nếu test assertion fail ở phase `test`, Surefire có thể đã tạo XML, dù Maven không đến `verify`. Step upload có điều kiện `always()` giúp lưu bằng chứng trong run để developer tải về.

Ví dụ workflow cho demo:

~~~yaml
name: Maven Minimal Repro

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  reproduce:
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - name: Checkout source
        uses: actions/checkout@v7
        with:
          persist-credentials: false

      - name: Set up Java 17
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
          cache-read-only: ${{ github.event_name == 'pull_request' }}

      - name: Record environment
        run: |
          java -version
          mvn --version
          git rev-parse HEAD

      - name: Reproduce Maven failure
        run: mvn -B -ntp clean verify

      - name: Upload available reports
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: maven-repro-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            **/target/surefire-reports/**
            **/target/failsafe-reports/**
            evidence/**
          if-no-files-found: warn
          retention-days: 7
~~~

Giải thích:

- Checkout ref/SHA của event; muốn test PR head hay merge ref phải hiểu GitHub Actions event semantics.
- `permissions: contents: read` giảm quyền token ở verify job; không cấp release secrets cho PR.
- `setup-java` đặt Temurin Java 17; exact patch/runtime nên được ghi trong logs.
- Cache tăng tốc dependency resolution, **không bảo đảm artifact trust**.
- Step Maven giữ exit status thật, không dùng `continue-on-error: true` hay `|| true`.
- `always()` thử upload ngay cả khi build fail; nếu fail trước khi tạo report, `if-no-files-found: warn` thông báo thiếu files.
- Action majors được ghi ở thời điểm soạn; self-hosted/GitHub Enterprise cũ phải kiểm supported runner/runtime, và tổ chức cần pin immutable action SHA nếu security policy yêu cầu.
- Upload artifact chỉ lưu files; không tự parse Surefire XML thành GitHub test annotations.

### Nếu muốn lưu chính Maven exit code thành evidence file

Thay step build bằng shell block (Bash trên GitHub-hosted Ubuntu):

~~~bash
mkdir -p evidence
set +e
mvn -B -ntp clean verify > evidence/verify-before.log 2>&1
build_exit=$?
printf '%s\n' "$build_exit" > evidence/verify-before-exit.txt
exit "$build_exit"
~~~

Điều quan trọng là dòng `exit "$build_exit"`, vì chỉ ghi exit code ra file mà không trả fail status có thể khiến job “xanh giả”. Khối này **là lệnh thay thế cho một step**, không phải nên đặt sau một step Maven đã tự fail.

## 18. Evidence package và mẫu bug report

Một bộ hồ sơ hợp lý:

~~~text
case/
├── reproducer/
│   ├── pom.xml
│   ├── src/main/java/demo/repro/Adder.java
│   └── src/test/java/demo/repro/AdderTest.java
├── evidence/
│   ├── java-version.before.txt
│   ├── maven-version.before.txt
│   ├── verify-before.log
│   ├── verify-before-exit.txt
│   ├── TEST-demo.repro.AdderTest.before.xml
│   ├── verify-after.log
│   ├── verify-after-exit.txt
│   └── TEST-demo.repro.AdderTest.after.xml
└── README.md
~~~

Phần README của case nên có:

- **Title:** lỗi cụ thể, không chỉ “Maven broken”.
- **Environment:** OS/JDK/Maven/plugin versions.
- **Revision:** commit SHA và working-tree differences nếu có.
- **Reproduction command:** đúng working directory, flags, profiles.
- **Expected/observed:** giá trị và failure signature.
- **Minimality:** thành phần đã bỏ và lý do vẫn giữ lỗi.
- **Artifacts:** đường dẫn reports/logs/exit status.
- **Hypothesis/root cause:** cơ chế có thể kiểm chứng.
- **Fix:** diff nhỏ; hiệu quả trước/sau.
- **Security:** evidence đã được rà soát trước khi chia sẻ.
- **Limitations:** những điều kiện CI/service không thể dựng lại độc lập.

Ví dụ case summary:

~~~text
Title: Adder.add(2,2) yields 3; expected 4
Maven project: demo.repro:adder-repro:1.0.0-SNAPSHOT
Java: 17
Maven command: mvn -B -ntp clean verify
Failing goal: maven-surefire-plugin:3.5.4:test
Test: demo.repro.AdderTest.addsTwoNumbers
Observed: expected <4> but was <3>
Before: 1 test; 1 failure; nonzero Maven exit
Fix: remove "- 1" from Adder.add
After: same test PASS; Maven exit 0; Java stdout 4
Evidence: verify-before/after.log, Surefire XML, versions
Scope: minimal Maven/Java exercise, no external services
~~~

Đây là **mẫu dữ liệu sau khi demo được chạy đúng**, không được dùng thay log và kết quả thực tế.

### Hash chứng cứ

Nếu cần chứng minh evidence files không đổi trong quá trình chia sẻ nội bộ, có thể ghi SHA-256. Nhưng khi public source hoặc log chứa thông tin nhạy cảm, không được chỉ “hash rồi upload raw file” mà bỏ qua redaction.

## 19. Bảo mật: không để debug logs trở thành sự cố mới

Các nguồn có thể chứa dữ liệu nhạy cảm:

- `settings.xml`, effective settings, server tokens.
- Maven `-X` logs và plugin parameter logs.
- Private repository/proxy URLs.
- Environment variables và CI secret injection.
- Test stdout/stderr và exception messages.
- Credentials trong URL hoặc command line.
- Source paths có usernames/project/customer IDs.
- Database fixtures có dữ liệu thực.

Quy trình chia sẻ:

1. Giữ **bản gốc** ở nơi có kiểm soát/retention phù hợp.
2. Tạo **bản đã redacted** để gửi người khác.
3. Bỏ/tokenize passwords, URLs riêng tư và PII, không bịa stack trace.
4. Dùng test fixture tổng hợp khi có thể.
5. Nếu redaction làm mất nguyên nhân, chuyển kênh bảo mật được cho phép thay vì public issue.
6. Nếu nghi lộ token, xử lý theo incident/rotation policy.

Không tự gửi toàn `~/.m2/repository` hoặc `~/.m2/settings.xml` cho maintainer. Chúng chứa các thông tin không liên quan, có thể có artifacts/cache/metadata nội bộ.

## 20. Các lỗi thường gặp trong quá trình tái hiện

| Hiện tượng | Vì sao | Cách xử lý |
| --- | --- | --- |
| MRE không còn fail. | Bỏ mất parent/profile/fixture gây lỗi. | Phục hồi phần vừa bỏ. |
| Fail vì không tìm JUnit thay vì assertion. | MRE không resolve test dependency. | Sửa repo/dependency trước rồi tái hiện 4/3. |
| Report cũ bị mất. | `clean` xóa `target`. | Copy ra `evidence/` trước khi chạy lại. |
| Không có Surefire XML. | Fail trước test hoặc reportsDirectory khác. | Đọc phase/goal và cấu hình report. |
| Build PASS nhưng 0 tests. | Tests bị skip/naming sai. | `failIfNoTests`, so XML counts. |
| Bản sau “sửa” có ít tests hơn. | Xóa/disable test. | Khôi phục và test lại. |
| Cả hai runs đều BUILD FAILURE. | Hai nguyên nhân khác nhau. | So failure signature. |
| `-X` log phơi bày token. | Không review/redact. | Bảo quản bản gốc nội bộ, chỉ gửi bản sanitized. |
| Local PASS CI FAIL. | JVM/Maven/profiles/OS/caches khác. | So exact toolchain và CI SHA. |
| Sai plugin version. | Không pin hoặc parent khác. | Xem effective POM/actual log. |
| `dependency:tree` không chạy. | Resolution fail sớm. | Giữ resolution logs. |
| Cache mới làm lỗi biến mất. | Stale/corrupt artifact trong cache cũ. | Ghi nhận như biến môi trường, không xóa mù. |
| `mvn -o` tạo lỗi mới. | Cache thiếu artifact/plugin. | Không nhầm offline failure với lỗi gốc. |
| `-U` làm SNAPSHOT đổi. | Update policy/repository state. | Ghi resolved build timestamp/version. |
| MRE chạy khác trên Windows. | Path/case/encoding/native tool. | Ghi và thử đúng OS. |
| Only parallel build fails. | Race ở test/plugin/port/schema. | Test serial/parallel có đối chứng. |
| Rerun PASS nhưng lỗi trở lại. | Flaky chưa xử lý. | Ghi fail rate, dùng nhiều trials. |
| Thay nhiều phụ thuộc cùng lúc. | Không xác định nguyên nhân. | Sửa một biến, quay lại baseline. |
| Fail ở wrapper nhưng system Maven PASS. | Distribution/launcher khác. | Giữ wrapper config trong MRE. |
| Public bug report thiếu inputs. | Chỉ có ảnh screenshot. | Gửi POM/source/test/log đã sanitized. |
| MRE PASS sau fix nhưng full project FAIL. | Bug thứ hai hoặc interaction bị giản lược. | Chạy full Reactor/CI regression. |

## 21. Bài tập áp dụng

### Bài A — Đó có phải cùng một lỗi?

Run 1:

~~~text
AdderTest.addsTwoNumbers
expected: <4> but was: <3>
BUILD FAILURE
~~~

Run 2:

~~~text
Could not resolve org.junit.jupiter:junit-jupiter
BUILD FAILURE
~~~

**Đáp án:** Không. Run 2 chưa chạy tới assertion, đó là lỗi resolution. Cần restore dependency/build environment và kiểm lại đúng failure signature.

### Bài B — Làm trọn bài thực hành

1. Tạo `pom.xml`, `Adder.java` và `AdderTest.java` ở mục 7.
2. Chạy `mvn --version`/`java -version`.
3. Chạy `mvn -B -ntp clean verify` và xác nhận 1 test FAIL.
4. Chụp exit code, Maven log, Surefire XML sang `evidence/`.
5. Chạy `java -cp target/classes demo.repro.Adder` và kiểm stdout 3.
6. Thay chỉ một dòng `return left + right - 1;` thành `return left + right;`.
7. Chạy lại cùng Maven command.
8. Kiểm 1 test PASS, Maven success, Java stdout 4.
9. Lưu before/after evidence, so tests counts.
10. Viết bug report tóm tắt root cause và diff.

### Bài C — Parent POM và profiles

Một service chỉ fail khi bật `-Pci` từ parent POM. Sau khi copy module sang POM rỗng thì build PASS.

**Đáp án định hướng:** đó chưa phải MRE của lỗi; phải giữ phần parent/profile làm phát sinh lỗi, hoặc chép đúng effective configuration vào POM độc lập rồi xác minh same failure. Dùng `help:effective-pom` chỉ sau static review/trong môi trường được phép.

### Bài D — Tránh “sửa xanh giả”

Một người đề xuất:

- Xóa `AdderTest`.
- Thêm `-DskipTests`.
- Đổi assertion từ expected 4 thành 3.
- Chạy `mvn -fn verify`.
- Sửa implementation bằng `return left + right;`.

**Đáp án:** chỉ đề xuất cuối sửa đúng requirement của demo mà vẫn giữ test. Các cách trước che/mất bằng chứng hoặc thay kỳ vọng sai.

### Bài E — Lỗi CI chập chờn

CI Maven `-T 2` fail 3/20 lần; `-T 1` fail 0/20.

Hãy xác định test/goal/module, Surefire forks, database/port/shared filesystem, ghi log từng lần fail và báo failure rate. Không khẳng định Maven scheduler bug nếu chưa cô lập nguồn race. Sau fix, chạy trials cùng conditions và so tần suất.

### Bài F — Báo lỗi upstream

Chuẩn bị một case an toàn: Maven/JDK/OS, plugin GAV, failure signature, POM/test nhỏ, reproduction command, report XML, sanitized logs và những bước đã thử. Nếu không thể công khai private repository, mô tả limitation và kênh trao đổi phù hợp, **không đính kèm token**.

## 22. Checklist trước khi kết thúc điều tra

**Trước sửa:**

- [ ] Đã ghi source SHA/working tree và toolchain.
- [ ] Đã giữ command nguyên văn cùng profiles/properties.
- [ ] Đã snapshot original logs, exit code, test reports **trước clean**.
- [ ] Đã xác định failing phase/goal/module/test.
- [ ] Đã review dữ liệu nhạy cảm trước khi chia sẻ.

**MRE:**

- [ ] POM hợp lệ, đủ plugin/dependency versions.
- [ ] Giữ đúng parent/BOM/profile/fixture nếu chúng gây lỗi.
- [ ] Source/test names và packages khớp paths.
- [ ] Người khác có thể chạy steps rõ ràng.
- [ ] MRE fail với **cùng signature**.
- [ ] Không phụ thuộc secrets/production service nếu không bắt buộc.
- [ ] Không coi “lỗi khác” là một reproduction.

**Fix:**

- [ ] Có một giả thuyết root cause kiểm chứng được.
- [ ] Diff tối thiểu, không thay nhiều biến cùng lúc.
- [ ] Chạy lại cùng Maven command/toolchain.
- [ ] Số tests không giảm/không bị skip.
- [ ] Có log/XML/exit code sau sửa.
- [ ] Có regression test để ngăn tái phát.
- [ ] Full project/CI kiểm chứng ngoài MRE cũng đạt, hoặc có ghi rõ phần chưa kiểm.

**Handover:**

- [ ] README ghi expected/actual, môi trường và bước reproduce.
- [ ] Evidence paths tồn tại và có retention phù hợp.
- [ ] Không public raw settings/debug logs có secrets.
- [ ] Kết luận tách biệt reproduction, fix, regression.
- [ ] Những bất định/flaky conditions vẫn được nêu rõ.

## 23. Kết luận

**POM tối thiểu là công cụ giảm số biến gây nhiễu để chứng minh vì sao một build bị lỗi, không phải cách làm build xanh bằng mọi giá.** Một MRE tốt đủ nhỏ để người khác hiểu, đủ đầy để chạy và đủ trung thực để tái hiện **cùng failure signature**.

~~~text
Bản lỗi gốc
     │
     ▼
Lưu bằng chứng trước khi sửa
     │
     ▼
Giảm POM/code/fixtures từng phần
     │
     ▼
Tái hiện cùng lỗi trên MRE
     │
     ▼
Sửa đúng một nguyên nhân
     │
     ▼
So XML + exit + stdout trước/sau
     │
     ▼
Chạy lại full project và CI
     │
     ▼
Báo cáo nguyên nhân, fix và giới hạn
~~~

Ghi nhớ: `BUILD FAILURE` **không phải** failure signature; `BUILD SUCCESS` **không phải** bằng chứng đã chạy đủ tests. Hãy lưu nguồn, lệnh, toolchain, exit status và reports trước khi chạy lại `clean`. Chỉ sửa khi lỗi đã tái hiện được và có cách đối chứng. Với lỗi môi trường/CI/flaky, nêu rõ các điều kiện chưa kiểm soát thay vì tuyên bố đã chữa hẳn.

## Tài liệu chính thức

- Apache Maven — Frequently Asked Technical Questions (`-e`/`-X`): https://maven.apache.org/general
- Apache Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven — POM Reference: https://maven.apache.org/pom.html
- Apache Maven — Build Profiles: https://maven.apache.org/guides/introduction/introduction-to-profiles.html
- Maven Help Plugin — `effective-pom`, `-Dverbose`: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- Maven Help Plugin — active profiles: https://maven.apache.org/plugins/maven-help-plugin/plugin-info.html
- Maven Dependency Plugin — `dependency:tree`: https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html
- Maven Surefire Plugin 3.5.4 — `surefire:test` and reportsDirectory: https://maven.apache.org/surefire-archives/surefire-3.5.4/maven-surefire-plugin/test-mojo.html
- Maven Surefire Plugin — overview and reports: https://maven.apache.org/surefire/maven-surefire-plugin/
- Maven — Multiple Modules: https://maven.apache.org/guides/mini/guide-multiple-modules.html
- Maven — Repositories and Offline Mode: https://maven.apache.org/guides/introduction/introduction-to-repositories.html
- Apache Maven Wrapper: https://maven.apache.org/tools/wrapper/
- JUnit — User Guide: https://docs.junit.org/current/user-guide/
