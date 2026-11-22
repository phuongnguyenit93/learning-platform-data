# Lưu báo cáo kiểm thử, nhật ký và sản phẩm dưới dạng artifact trong CI/CD với Apache Ant

## 1. Artifact trong một quy trình Ant là gì?

Khi chạy Apache Ant trên máy cá nhân, người phát triển có thể đọc log ngay trong terminal hoặc mở thư mục `dist/`. Trong CI/CD, job thường chạy trên máy ảo/container tạm. Khi job kết thúc, workspace có thể bị xóa. Nếu không giữ lại các file cần thiết, rất khó xác định **test nào lỗi, lỗi xảy ra ở bước nào và bản JAR nào đã được tạo từ commit nào**.

**Artifact** là file hoặc nhóm file mà nền tảng CI thu thập từ một lần chạy để cho phép tải xuống, xem lại hoặc chuyển cho job tiếp theo. Bài học này tập trung vào ba nhóm:

| Nhóm | Ví dụ | Vì sao cần giữ? |
|---|---|---|
| **Báo cáo kiểm thử** | `TEST-example.CalculatorTest.xml`, HTML từ JUnit | Xem test pass/fail, stack trace, thời gian; tích hợp vào giao diện CI. |
| **Nhật ký** | `ant-build.log`, log công cụ/test | Biết trình tự chạy, nguyên nhân lỗi compiler hoặc môi trường. |
| **Sản phẩm** | `calculator.jar`, `.war`, ZIP, checksum | Tải về kiểm tra, đối soát hoặc chuyển tới bước phát hành sau khi đạt gate. |

Báo cáo thể hiện **kết quả có cấu trúc**; log cho biết **quá trình**; sản phẩm là **đầu ra có thể sử dụng**. Khi test thất bại, ta vẫn muốn có XML và log. Một JAR đã tạo ra không có nghĩa JAR đó đủ điều kiện đưa lên production.

Trong thiết kế này có hai trách nhiệm riêng:

1. **Ant tạo file** bằng các task như `<javac>`, `<junit>`, `<jar>`, `<checksum>`.
2. **Hệ thống CI lưu file** bằng cơ chế của GitHub Actions, GitLab CI, Jenkins hoặc hệ thống tương tự.

Ant tự tạo thư mục `dist/` không đồng nghĩa file trong đó đã trở thành artifact của CI. Bước upload/publish cần được khai báo cụ thể.

```text
Checkout + thiết lập JDK, Ant, dependency
                   |
                   v
           Ant compile / test / jar
                   |
          +--------+--------+
          |        |        |
          v        v        v
       reports    logs     dist
          |        |        |
          +--------+--------+
                   |
                   v
           CI lưu artifact theo run
                   |
            +------+------+
            |             |
            v             v
        Điều tra lỗi    Job tiếp theo
                       (sau khi gate đạt)
```

**Nguyên tắc:** lưu artifact cả khi build thất bại, nhưng giữ nguyên trạng thái thất bại của job. Không chuyển test fail thành CI xanh chỉ để chạy được bước upload.

## 2. Quy hoạch thư mục đầu ra

Một repository đơn giản có thể dùng:

```text
ant-demo/
├── build.xml
├── src/
│   ├── main/java/example/Calculator.java
│   └── test/java/example/CalculatorTest.java
├── lib/test/
│   ├── junit-4.13.2.jar
│   └── hamcrest-core-1.3.jar
├── build/                              # trung gian
│   ├── classes/
│   └── test-classes/
└── artifacts/                          # dữ liệu cần giữ
    ├── reports/
    │   └── junit/
    │       └── TEST-example.CalculatorTest.xml
    ├── logs/
    │   └── ant-build.log
    └── dist/
        ├── calculator.jar
        └── calculator.jar.sha256
```

`build/` chứa class trung gian có thể tái tạo. `artifacts/reports/`, `artifacts/logs/` và `artifacts/dist/` là ba nhánh mà pipeline sẽ thu thập. Cách này giúp tránh upload toàn bộ workspace, dependency cache, file tạm hoặc thư mục mã nguồn.

Thêm vào `.gitignore`:

```gitignore
build/
artifacts/
```

Trong `build.xml`, đường dẫn nên dẫn xuất từ `basedir` của project và từ những property chung; tránh hardcode ổ `C:\`, `/home/ci` hay đường dẫn cá nhân. Nếu nhiều job dùng chung workspace, phải tách vùng đầu ra theo dự án, job hoặc run để không ghi đè hay xóa nhầm file.

## 3. Ví dụ mã nguồn và test

File `src/main/java/example/Calculator.java`:

```java
package example;

public class Calculator {
    public static int add(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) {
        System.out.println(add(2, 3));
    }
}
```

File `src/test/java/example/CalculatorTest.java`:

```java
package example;

import org.junit.Test;
import static org.junit.Assert.assertEquals;

public class CalculatorTest {
    @Test
    public void addTwoNumbers() {
        assertEquals(5, Calculator.add(2, 3));
    }
}
```

Ví dụ giả định có **JDK 17 trở lên, Ant 1.10.x và JUnit 4**. Hai thư viện `junit-4.13.2.jar` và `hamcrest-core-1.3.jar` được chuẩn bị trong `lib/test/` (hoặc một bước quản lý dependency tạo đúng cấu trúc này trước khi gọi Ant). Tùy bản phân phối, task Ant `<junit>` còn cần các JAR hỗ trợ `ant-junit` và `ant-junit4` của Ant. Những JAR thư viện này là **đầu vào**, không phải artifact đầu ra.

Nếu dự án dùng JUnit 5, cần thiết lập task/runner theo JUnit Platform (chẳng hạn `<junitlauncher>` trên Ant thích hợp) và dependency tương ứng; không giả định `<junit>` của ví dụ này tự chạy được mọi framework test.

## 4. Tạo XML, JAR và checksum bằng Ant

File `build.xml` minh họa một pipeline compile, test và package:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-ci-artifacts" default="ci" basedir=".">

    <!-- Đầu vào -->
    <property name="src.main.dir" location="src/main/java"/>
    <property name="src.test.dir" location="src/test/java"/>
    <property name="lib.test.dir" location="lib/test"/>

    <!-- File trung gian -->
    <property name="work.dir" location="build"/>
    <property name="classes.dir" location="${work.dir}/classes"/>
    <property name="test.classes.dir" location="${work.dir}/test-classes"/>

    <!-- Nhóm file để CI thu thập -->
    <property name="artifacts.dir" location="artifacts"/>
    <property name="reports.junit.dir"
              location="${artifacts.dir}/reports/junit"/>
    <property name="logs.dir" location="${artifacts.dir}/logs"/>
    <property name="dist.dir" location="${artifacts.dir}/dist"/>
    <property name="jar.file" location="${dist.dir}/calculator.jar"/>

    <path id="test.classpath">
        <pathelement location="${classes.dir}"/>
        <pathelement location="${test.classes.dir}"/>
        <fileset dir="${lib.test.dir}" includes="*.jar"/>
    </path>

    <target name="prepare">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${test.classes.dir}"/>
        <mkdir dir="${reports.junit.dir}"/>
        <mkdir dir="${logs.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="compile" depends="prepare">
        <javac srcdir="${src.main.dir}"
               destdir="${classes.dir}"
               release="17"
               encoding="UTF-8"
               includeantruntime="false"/>
    </target>

    <target name="compile-tests" depends="compile">
        <javac srcdir="${src.test.dir}"
               destdir="${test.classes.dir}"
               classpathref="test.classpath"
               release="17"
               encoding="UTF-8"
               includeantruntime="false"/>
    </target>

    <target name="test" depends="compile-tests">
        <!-- Không dừng khi một assertion thất bại;
             tạo báo cáo trước rồi mới trả lỗi tại target ci. -->
        <junit fork="true"
               printsummary="true"
               haltonfailure="false"
               haltonerror="false"
               failureproperty="tests.failed"
               errorproperty="tests.errored">
            <classpath refid="test.classpath"/>
            <formatter type="xml"/>
            <batchtest todir="${reports.junit.dir}">
                <fileset dir="${test.classes.dir}"
                         includes="**/*Test.class"/>
            </batchtest>
        </junit>
    </target>

    <target name="package" depends="compile">
        <jar destfile="${jar.file}" basedir="${classes.dir}">
            <manifest>
                <attribute name="Main-Class" value="example.Calculator"/>
            </manifest>
        </jar>
        <checksum file="${jar.file}"
                  algorithm="SHA-256"
                  fileext=".sha256"/>
    </target>

    <!-- Package trước test, sau đó báo trạng thái thật. -->
    <target name="ci" depends="package,test">
        <fail if="tests.failed"
              message="Test thất bại; xem artifacts/reports/junit."/>
        <fail if="tests.errored"
              message="Lỗi khi chạy test; xem artifacts/reports/junit."/>
    </target>

    <target name="clean">
        <delete dir="${work.dir}"/>
        <delete dir="${artifacts.dir}"/>
    </target>
</project>
```

### 4.1. Kết quả của từng target

| Target | Việc làm | File được tạo |
|---|---|---|
| `compile` | `<javac>` biên dịch mã nguồn | `build/classes/` |
| `compile-tests` | Biên dịch JUnit test với test classpath | `build/test-classes/` |
| `test` | `<junit>` cùng `<formatter type="xml"/>` | `artifacts/reports/junit/TEST-*.xml` |
| `package` | `<jar>` và `<checksum>` | `calculator.jar` và `calculator.jar.sha256` |
| `ci` | Dùng `<fail>` để kết thúc lỗi nếu test fail/error | Exit code để CI biết thành/bại |

`haltonfailure="false"` và `haltonerror="false"` cho JUnit cơ hội viết XML dù assertion fail hoặc test gặp lỗi. `failureproperty` và `errorproperty` là các tín hiệu cho target `ci`. **Chỉ đặt `haltonfailure="false"` rồi không kiểm tra kết quả sẽ tạo nguy cơ báo job xanh sai.** Trong ví dụ, `<fail>` được đặt sau các target sản xuất report nên job vẫn trả exit code khác `0` khi test không đạt.

Thứ tự `depends="package,test"` làm JAR được đóng gói trước test. Điều này chủ động giữ lại sản phẩm của một build có assertion fail để điều tra, nhưng JAR đó **không đủ điều kiện triển khai**. Nếu lỗi compiler hoặc lỗi cấu hình khiến test không chạy, XML có thể chưa có; bước upload phải xử lý trường hợp chỉ có log.

`<batchtest>` minh họa quy ước chọn lớp có hậu tố `Test.class`. Nếu không có test nào khớp, đó không phải bằng chứng bộ kiểm thử đã đạt; dự án thực tế cần quy tắc khám phá test và nên báo lỗi nếu thiếu test trái mong đợi.

### 4.2. Log Ant được tạo thế nào?

XML JUnit ghi kết quả test, còn log toàn bộ lệnh Ant gồm warning compiler, target đã chạy và nguyên nhân lỗi sớm. File `build.xml` trên tạo thư mục `artifacts/logs/` nhưng **chưa ghi log**. Bước CI ở phần sau dùng `tee` để chuyển stdout và stderr của Ant vào `artifacts/logs/ant-build.log`, đồng thời hiển thị chúng trong console.

Ant cũng hỗ trợ tùy chọn `-logfile` và task `<record>`. Khi dùng chúng, cần tạo thư mục đích trước khi mở file và nhớ rằng lỗi xảy ra trước lúc logger được bật có thể không được ghi lại. Log runner của nền tảng CI vẫn quan trọng cho lỗi checkout, cài toolchain hoặc chuẩn bị dependency.

## 5. Chạy thủ công trước khi cấu hình CI

Từ gốc repository:

```bash
ant -f build.xml clean
ant -f build.xml ci
```

Khi test đạt, Ant trả exit code `0`, tạo XML, JAR và checksum dưới `artifacts/`. Nếu sửa `assertEquals(5, Calculator.add(2, 3))` thành `assertEquals(99, Calculator.add(2, 3))` rồi chạy lại, JUnit ghi assertion failure vào XML và target `ci` trả exit code khác `0`. Những file đã được tạo trước khi báo fail vẫn còn để xem.

Có thể gọi target riêng:

```bash
# Chỉ tạo JAR, chưa chạy test:
ant -f build.xml package

# Chạy test và các target phụ thuộc:
ant -f build.xml test
```

Trong ví dụ này, gate thất bại nằm ở target `ci`, không nằm ở target `test` khi gọi riêng. Vì vậy pipeline chính thức phải gọi `ci` để trạng thái job phản ánh kết quả kiểm thử.

## 6. GitHub Actions: lưu artifact kể cả khi Ant thất bại

Một workflow `.github/workflows/ant-ci.yml` cho runner Ubuntu:

```yaml
name: Ant CI

on:
  push:
  pull_request:

jobs:
  build-test:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Install Ant
        run: |
          sudo apt-get update
          sudo apt-get install -y ant ant-optional

      # Giả định lib/test đã có JUnit 4 và Hamcrest đầu vào
      # từ repository hoặc bước quản lý dependency trước đó.

      - name: Clean previous output
        run: ant -f build.xml clean

      - name: Build, test and capture log
        shell: bash
        run: |
          mkdir -p artifacts/logs
          set -o pipefail
          ant -f build.xml ci 2>&1 | tee artifacts/logs/ant-build.log

      - name: Upload build evidence and product
        if: ${{ always() }}
        uses: actions/upload-artifact@v4
        with:
          name: ant-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            artifacts/reports/
            artifacts/logs/
            artifacts/dist/
          if-no-files-found: warn
          retention-days: 14
```

Workflow dùng Bash và `apt-get` vì runner là Ubuntu. Nếu dùng Windows/macOS cần đổi bước cài Ant và cú pháp shell, nhưng hợp đồng thư mục artifact mà Ant tạo vẫn vậy. Các JAR JUnit/Hamcrest trong `lib/test/` phải được provision trước bước build; workflow minh họa này không thực hiện tải chúng. Trong dự án thật, quản lý dependency theo phiên bản cố định và nguồn tải được kiểm soát.

### 6.1. Tại sao cần `set -o pipefail`?

```bash
ant -f build.xml ci 2>&1 | tee artifacts/logs/ant-build.log
```

`2>&1` đưa stderr vào stdout; `tee` vừa ghi file vừa hiển thị dòng log trên console. Nhưng nếu shell chỉ lấy exit code của lệnh cuối cùng trong pipeline, `tee` có thể thành công dù Ant thất bại, khiến CI báo xanh sai. `set -o pipefail` giữ tín hiệu lỗi từ Ant.

Chú ý phải chạy `ant clean` **trước** khi mở log bằng `tee`. Cách viết `ant clean ci 2>&1 | tee artifacts/logs/ant-build.log` có thể khiến target `clean` xóa chính file log đang được `tee` ghi; trên một số filesystem log sẽ biến mất khỏi đường dẫn cần upload.

### 6.2. Vì sao upload dùng `always()`?

Nếu step build/test trả exit code khác `0`, các step sau thường bị bỏ qua. `if: ${{ always() }}` yêu cầu GitHub Actions vẫn cố gắng upload file sau failure, giúp lưu log và XML dù test fail. Điều kiện này **không** che lỗi step build trước đó.

`always()` không bảo đảm file xuất hiện khi runner bị hủy cưỡng bức, hết dung lượng hoặc lỗi xảy ra trước khi tạo JAR/XML. `if-no-files-found: warn` cảnh báo khi không có file khớp; các pipeline có yêu cầu bắt buộc về artifact cần thêm quy tắc fail khi thiếu đầu ra.

Tên artifact có `github.run_id` và `github.run_attempt` để phân biệt lần chạy và lần retry. Nếu workflow có matrix nhiều OS/JDK, thêm nhãn `matrix.os`, `matrix.java` vào tên; không để hai job cố tải lên cùng một tên artifact. Với `actions/upload-artifact@v4`, tên artifact được quản lý như một bản upload bất biến, không ghép tùy tiện nhiều lần upload cùng tên như các cơ chế cũ.

### 6.3. Lưu artifact không đồng nghĩa phát hành

`upload-artifact` giữ bản chụp để tải về hoặc truyền cho job khác. Nó không tự tạo release có version hay xác nhận JAR đã qua gate. Job deploy chỉ được sử dụng sản phẩm của run đã được kiểm thử và phê duyệt phù hợp:

```text
Build / test
   |
   +-- FAIL --> lưu XML, log và JAR đã tạo để điều tra
   |           không triển khai
   |
   +-- PASS --> lưu XML, log, JAR/checksum
                 |
                 v
            gate / phê duyệt
                 |
                 v
             phát hành
```

## 7. Cách khai báo tương đương trên GitLab CI và Jenkins

Khi chuyển nền tảng CI, không cần đổi tên các target Ant nếu vẫn dùng cùng cấu trúc `artifacts/`. Chỉ có phần khai báo lưu file và publish test report thay đổi.

### 7.1. GitLab CI

Trong `.gitlab-ci.yml`, với runner đã cài sẵn JDK, Ant và dependency:

```yaml
ant-test:
  stage: test
  script:
    - ant -f build.xml clean
    - mkdir -p artifacts/logs
    - ant -f build.xml ci > artifacts/logs/ant-build.log 2>&1
  artifacts:
    when: always
    paths:
      - artifacts/reports/
      - artifacts/logs/
      - artifacts/dist/
    reports:
      junit: artifacts/reports/junit/TEST-*.xml
    expire_in: 14 days
```

`when: always` yêu cầu lưu file sau job dù thất bại. `reports: junit` giúp GitLab đọc XML và hiển thị test result. Chỉ khai báo `paths` thường chỉ lưu file để tải xuống. Script minh họa dùng shell Unix; nếu muốn vừa thấy log trong console vừa giữ file, dùng `tee` và bảo toàn exit code tương tự ví dụ GitHub.

### 7.2. Jenkins Pipeline

Trong `post` của một Jenkins Declarative Pipeline:

```groovy
post {
    always {
        archiveArtifacts artifacts: 'artifacts/**/*',
                         allowEmptyArchive: true
        junit testResults: 'artifacts/reports/junit/TEST-*.xml',
              allowEmptyResults: true
    }
}
```

`archiveArtifacts` lưu file từ workspace để tải ở giao diện Jenkins. Bước `junit` phân tích XML, hiển thị test result và có thể ảnh hưởng trạng thái build theo chính sách Jenkins. `allowEmpty...` cho phép hậu xử lý không che lỗi gốc khi build dừng sớm; quy trình thật vẫn cần phát hiện trường hợp không có test nào được chạy mà lẽ ra phải có.

## 8. Điều gì còn lại khi job lỗi ở từng giai đoạn?

| Giai đoạn lỗi | File có thể còn | Nên kiểm tra |
|---|---|---|
| Checkout/cài JDK/Ant | Chỉ có log của runner | Quyền, mạng, cấu hình toolchain. |
| Biên dịch source | Log Ant, chưa có JAR hay JUnit XML | Thông báo lỗi `javac`. |
| Biên dịch test | Log, có thể có JAR tạo trước đó | JUnit dependency, import, Java release. |
| Assertion thất bại | JAR, checksum, JUnit XML, log | Test case, expected/actual, stack trace. |
| Test treo/JVM bị kill | Log và một phần báo cáo nếu đã được ghi | Timeout, memory, log tiến trình. |
| Package/checksum lỗi | Log; JAR có thể thiếu/chưa hoàn chỉnh | Target package và quyền ghi. |
| Upload artifact lỗi | File có thể chỉ còn trên runner | Quota, kết nối, permission, tên artifact. |

Không phải lỗi nào cũng tạo đủ ba nhóm file. Upload nên cố lưu **những thứ đã có** và giải thích được vì sao XML/JAR vắng mặt. Nếu file thiếu do bước biên dịch dừng sớm, không nên nhầm với lỗi pattern upload.

Một sai sót shell phổ biến:

```bash
# Exit code cuối có thể là của echo thay vì Ant.
ant -f build.xml ci > artifacts/logs/ant-build.log 2>&1
echo "Đã chạy xong"
```

Nếu shell không bật chế độ dừng khi gặp lỗi và không lưu lại exit code, lệnh `echo` có thể khiến script kết thúc với `0`. Không dùng `|| true` cho test để né trạng thái đỏ. Hãy giữ exit code gốc của Ant, còn upload đặt ở giai đoạn hậu xử lý độc lập.

## 9. Báo cáo XML, HTML và log có vai trò khác nhau

**JUnit XML** là dữ liệu máy đọc. File thường dạng `TEST-example.CalculatorTest.xml` với thông tin test suite, test case, thời gian, failure/error và stack trace. Nền tảng CI có thể tổng hợp thành giao diện test nếu cấu hình publisher đúng. Upload XML như file thông thường **chưa chắc** tự xuất hiện trong tab kiểm thử.

**HTML** có thể hữu ích cho người đọc khi có nhiều XML. Ant có task `<junitreport>` nhưng tùy môi trường cần thư viện XSLT/Xalan thích hợp. Ví dụ một target mở rộng:

```xml
<target name="report-html" depends="test">
    <mkdir dir="${artifacts.dir}/reports/html"/>
    <junitreport todir="${reports.junit.dir}">
        <fileset dir="${reports.junit.dir}"
                 includes="TEST-*.xml"/>
        <report format="frames"
                todir="${artifacts.dir}/reports/html"/>
    </junitreport>
</target>
```

Target này là **tùy chọn**, chưa được target `ci` gọi trong ví dụ chính. Nếu muốn dùng, chuẩn bị dependency của task và bổ sung thư mục HTML vào pattern upload. Nên giữ XML vì nó phù hợp để CI phân tích tự động.

**Log** lưu ngữ cảnh mà XML không có: JDK version, warning compiler, target Ant, log công cụ khác và lỗi setup. Tuy nhiên log có thể rất dài và chứa dữ liệu nhạy cảm; cần chọn mức log phù hợp, giới hạn dung lượng, xác định thời gian lưu. Không upload vô tội vạ mọi file trong workspace dưới danh nghĩa “để debug”.

## 10. Định danh và khả năng truy vết artifact

Một artifact cần liên kết được với **commit, cấu hình môi trường và lần chạy**. Có thể đặt tên:

```text
<project>-<commit-short>-<run-id>-<attempt>-<os>-<jdk>
```

Ví dụ `calculator-a91f2b3-284-2-linux-jdk17`. Trong CI matrix, tên nên phân biệt tất cả job có thể chạy song song.

| Metadata | Ý nghĩa |
|---|---|
| Commit SHA | Biết chính xác nguồn nào tạo ra sản phẩm, thay vì chỉ dựa vào tên branch di động. |
| Run ID / attempt | Phân biệt lượt chạy, retry và tránh ghi chồng. |
| JDK / Ant / dependency versions | Có cơ sở tái hiện và giải thích sự khác biệt giữa các runner. |
| SHA-256 checksum | So sánh file tải xuống với file tạo bởi job, phát hiện file bị đổi/hỏng. |
| Kết quả gate | Xác định artifact chỉ phục vụ điều tra hay đủ điều kiện phát hành. |

Có thể sinh thêm `build-info.json` hoặc `manifest.properties` lưu metadata của CI; đừng đặt secrets ở đó. Nếu mục tiêu là build byte-for-byte tái lập, không nhúng timestamp/run ID thay đổi vào chính JAR; giữ metadata theo từng run ở file đi kèm. Checksum không tự chứng minh provenance đáng tin cậy: quy trình phát hành còn cần kiểm soát quyền upload, nguồn, pipeline và chính sách xác minh phù hợp.

## 11. Chính sách lưu giữ, quyền truy cập và dung lượng

Artifact tiêu thụ dung lượng và có thể chứa dữ liệu nội bộ. Khi thiết kế pipeline, xác định rõ **ai có thể tải, giữ trong bao lâu, file nào được phép đưa lên và khi nào dọn**.

| Nhóm file | Chính sách gợi ý |
|---|---|
| XML/HTML test | Giữ đủ lâu để điều tra regression, test không ổn định và đối chiếu pull request. |
| Log debug | Giữ ngắn hơn; chỉ ghi nhiều chi tiết khi có nhu cầu xử lý sự cố. |
| JAR của pull request | Gắn run/commit, lưu ngắn hạn để thử nghiệm; không coi là release chính thức. |
| Release đã duyệt | Lưu theo chính sách phát hành hoặc kho artifact chuyên dụng có quản lý quyền. |

`retention-days: 14` và `expire_in: 14 days` trong ví dụ chỉ là giá trị minh họa; thời gian thực tế phụ thuộc yêu cầu dự án và giới hạn nền tảng CI.

**Không upload secrets.** Token, URL có credential, file `.env`, khóa cá nhân, biến môi trường hoặc dữ liệu test thật có thể rơi vào log hay file được copy. Việc CI che secrets khi **hiển thị console** không bảo đảm file log/artifact tải về đã được làm sạch. Cần giới hạn đường dẫn upload, lọc dữ liệu nhạy cảm và kiểm soát quyền download.

**Artifact khác cache.** Cache dependency được phép tái sử dụng để tăng tốc build; artifact là bằng chứng của một lần chạy và phải gắn đúng run. Không dùng cache làm kho lưu báo cáo/JAR cần truy vết. Nếu archive quá lớn, chỉ lưu file cần thiết, nén có kiểm soát và áp dụng retention thay vì upload toàn bộ workspace.

## 12. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| Test fail, không có XML tải về | Upload bỏ qua vì job lỗi hoặc test chưa chạy | Upload trong hậu xử lý `always`; kiểm tra log giai đoạn sớm. |
| CI xanh dù JUnit có failure | Chỉ đặt `haltonfailure="false"` hoặc `tee` che exit code | Dùng property + `<fail>`, bật `pipefail`. |
| Log biến mất | `clean` xóa file `tee` đang mở; chưa tạo thư mục | Chạy `clean` trước, rồi tạo thư mục và mở log. |
| XML tải được nhưng không hiện tab test | Chỉ upload file thô, chưa khai báo JUnit publisher | Bật chức năng publish test report theo nền tảng CI. |
| Artifact có file từ lần chạy cũ | Runner tái sử dụng workspace, chưa dọn output | Clean vùng job sở hữu; tách thư mục theo run nếu song song. |
| `<junit>` không chạy | Thiếu JUnit 4, Hamcrest hoặc Ant optional task | Chuẩn bị dependencies đúng phiên bản và classpath. |
| Artifact quá lớn | Upload cả workspace/cache/log không cần thiết | Chỉ chọn report/log/dist, đặt giới hạn và thời gian lưu. |
| Tên artifact trùng giữa nhiều job | Thiếu run/attempt hoặc chiều matrix | Đặt tên duy nhất theo run và cấu hình. |
| JAR có sẵn nhưng pipeline vẫn đỏ | Test fail sau bước package | Giữ JAR để điều tra; chặn phát hành cho tới khi gate đạt. |

## 13. Thực hành với hai lần chạy

1. Chạy `ant -f build.xml clean` rồi `ant -f build.xml ci`. Quan sát JUnit XML, JAR và checksum trong `artifacts/`.
2. Đổi assertion từ giá trị kỳ vọng `5` sang `99`, clean rồi chạy lại. Mở XML để xem failure và ghi nhận exit code khác `0` của `ci`.
3. Chạy workflow CI có bước `tee` và upload `always()`. Tải artifact của lần test fail, tìm assertion trong XML và đối chiếu log của Ant. JAR có thể tồn tại nhưng không được tự động phát hành.
4. Khôi phục assertion đúng và chạy lại. So sánh tên artifact theo run/attempt; hai lượt không được bị nhầm lẫn.
5. Thử một lỗi compile để quan sát trường hợp chưa sinh XML. Khi đó log runner và log Ant là thông tin quan trọng nhất; pipeline vẫn phải cố lưu những gì đã được tạo.

Với dự án thật, bổ sung tên module trong đường dẫn, quy tắc phát hiện test rỗng, metadata commit và phân quyền tải artifact. Thiết kế tốt duy trì ba điều: **Ant tạo đầu ra rõ vị trí, CI luôn cố lưu bằng chứng khi thất bại, và chỉ kết quả qua đủ gate mới được phát hành**.
