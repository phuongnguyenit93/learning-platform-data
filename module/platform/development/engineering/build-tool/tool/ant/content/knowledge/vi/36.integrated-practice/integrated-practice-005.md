# Thực hành: Tạo báo cáo JUnit Platform và đo độ bao phủ bằng công cụ ngoài với Apache Ant

## 1. Mục tiêu

Apache Ant có thể biên dịch source Java, gọi chương trình khác và gom file đầu ra vào các thư mục xác định. Tuy nhiên, **Ant không tự tạo dữ liệu về độ bao phủ mã nguồn**. Muốn vừa biết test nào đạt/thất bại, vừa biết phần mã nào được test thực thi, ta kết hợp:

- **JUnit Platform Console**: tìm và chạy các bài kiểm thử JUnit Jupiter, xuất **JUnit XML** để người dùng và nền tảng CI đọc kết quả.
- **JaCoCo Java agent**: gắn vào JVM chạy test để thu dữ liệu thực thi dạng nhị phân `jacoco.exec`.
- **JaCoCo CLI**: đọc `jacoco.exec` cùng classfiles và sourcefiles, tạo **coverage HTML, XML, CSV**.
- **Apache Ant**: tổ chức target theo thứ tự, quản lý classpath, đường dẫn và chuyển kết quả test thành exit code cho CI.

Khi hoàn thành, một lệnh sẽ tạo cả hai nhóm báo cáo:

```bash
ant -f build.xml clean verify
```

| Nhóm đầu ra | Ví dụ | Nội dung |
|---|---|---|
| **Báo cáo kết quả test** | `artifacts/reports/junit/TEST-*.xml` | Test case nào chạy, đạt, thất bại, thời lượng và lỗi. |
| **Báo cáo coverage** | `artifacts/coverage/html/index.html` | Phần mã đã/ chưa chạy, theo package, class và source line. |
| **Coverage cho máy đọc** | `artifacts/coverage/jacoco.xml` | Các counter JaCoCo để đưa vào dashboard CI/quality tool. |
| **Dữ liệu trung gian** | `artifacts/coverage/jacoco.exec` | Dữ liệu do agent thu, dùng để dựng báo cáo. |

**Test pass không có nghĩa coverage cao; coverage cao không chứng minh assertion đúng.** Hai phép quan sát bổ sung cho nhau. Đây là bài thực hành điều phối công cụ trong Ant, nên các thư viện và phiên bản công cụ cần được cung cấp rõ ràng, không giả định Ant đã cài sẵn JaCoCo.

```text
Source + JUnit test + JAR công cụ cố định phiên bản
                        |
                        v
                Ant compile-main
                        |
                        v
                Ant compile-tests
                        |
                        v
             JVM chạy JUnit Platform
             (có JaCoCo Java agent)
                 /             \
                v               v
         JUnit XML          jacoco.exec
                                |
                                v
                  JaCoCo CLI + .class + .java
                                |
                                v
                     Coverage HTML/XML/CSV
                                |
                                v
                Ant verify kiểm tra exit code
```

## 2. Môi trường và các JAR cần chuẩn bị

Ví dụ dùng **JDK 17**, **Apache Ant 1.10.x** có hỗ trợ `<javac release="17">`, **JUnit Platform Console Standalone 1.10.2** và **JaCoCo 0.8.12**. Đây là các phiên bản minh họa được ghim để tái hiện thực hành; trước khi áp dụng vào dự án mới, hãy kiểm tra phiên bản JDK, Ant, JUnit và JaCoCo đang được tổ chức hỗ trợ, thay vì coi đây là bản mới nhất.

Các tọa độ Maven:

```text
org.junit.platform:junit-platform-console-standalone:1.10.2
org.jacoco:org.jacoco.agent:0.8.12:runtime
org.jacoco:org.jacoco.cli:0.8.12:nodeps
```

Đặt file đã tải ở:

```text
tools/
├── junit/
│   └── junit-platform-console-standalone-1.10.2.jar
└── jacoco/
    ├── org.jacoco.agent-0.8.12-runtime.jar
    └── org.jacoco.cli-0.8.12-nodeps.jar
```

Có thể lấy các JAR này từ kho Maven Central. Với máy có Bash và `curl`, các lệnh sau tạo đúng cấu trúc trên:

```bash
mkdir -p tools/junit tools/jacoco

curl -fL --retry 3 \
  -o tools/junit/junit-platform-console-standalone-1.10.2.jar \
  https://repo.maven.apache.org/maven2/org/junit/platform/junit-platform-console-standalone/1.10.2/junit-platform-console-standalone-1.10.2.jar

curl -fL --retry 3 \
  -o tools/jacoco/org.jacoco.agent-0.8.12-runtime.jar \
  https://repo.maven.apache.org/maven2/org/jacoco/org.jacoco.agent/0.8.12/org.jacoco.agent-0.8.12-runtime.jar

curl -fL --retry 3 \
  -o tools/jacoco/org.jacoco.cli-0.8.12-nodeps.jar \
  https://repo.maven.apache.org/maven2/org/jacoco/org.jacoco.cli/0.8.12/org.jacoco.cli-0.8.12-nodeps.jar
```

Lệnh tải chỉ là cách chuẩn bị thủ công. Trong CI thật, nên dùng kho dependency đáng tin cậy, khóa phiên bản và **xác minh checksum** trước khi chạy; tránh tải artifact theo nhãn `latest`. JaCoCo **agent** có nhiệm vụ đo trong JVM, còn JaCoCo **CLI** dựng báo cáo từ dữ liệu đã đo. Không thể thay một JAR cho JAR kia.

## 3. Cấu trúc dự án và bài kiểm thử JUnit Jupiter

Cây file ban đầu:

```text
ant-junit-coverage/
├── build.xml
├── .gitignore
├── tools/
│   ├── junit/junit-platform-console-standalone-1.10.2.jar
│   └── jacoco/
│       ├── org.jacoco.agent-0.8.12-runtime.jar
│       └── org.jacoco.cli-0.8.12-nodeps.jar
└── src/
    ├── main/java/example/DiscountCalculator.java
    └── test/java/example/DiscountCalculatorTest.java
```

File `src/main/java/example/DiscountCalculator.java`:

```java
package example;

public final class DiscountCalculator {
    private DiscountCalculator() {
    }

    public static int finalPrice(int price, boolean member) {
        if (member) {
            return price * 90 / 100;
        }
        return price;
    }
}
```

Phương thức có hai đường đi: khách hàng thành viên được giảm giá, khách thường giữ giá gốc. Ta có thể đo **branch coverage** bằng cách kiểm tra cả hai trường hợp.

File `src/test/java/example/DiscountCalculatorTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DiscountCalculatorTest {

    @Test
    void appliesDiscountToMember() {
        assertEquals(90, DiscountCalculator.finalPrice(100, true));
    }

    @Test
    void keepsPriceForRegularCustomer() {
        assertEquals(100, DiscountCalculator.finalPrice(100, false));
    }
}
```

Đây là **JUnit Jupiter** (`org.junit.jupiter.api`) chạy trên JUnit Platform. JAR Console Standalone chứa API, engine và launcher cần cho ví dụ. Không dùng task `<junit>` truyền thống của Ant rồi mặc định nó sẽ chạy JUnit 5: task đó chủ yếu dành cho cơ chế JUnit cũ. Ant cũng có task `<junitlauncher>` cho JUnit Platform ở các bản phù hợp, nhưng bài này dùng **ConsoleLauncher như công cụ ngoài** để thấy rõ cách Ant truyền classpath, tham số báo cáo và JaCoCo agent.

Tạo `.gitignore`:

```gitignore
/build/
/artifacts/
```

`build/` chứa class biên dịch; `artifacts/` chứa báo cáo do job tạo. Không commit các đầu ra có thể sinh lại vào repository. Thư mục `tools/` là đầu vào chứa công cụ đã được chuẩn bị; quy định riêng của dự án sẽ quyết định tải trên CI hay lưu vào kho artifact/dependency nội bộ.

## 4. Viết `build.xml` hoàn chỉnh

Các target được thiết kế sao cho **ngay cả khi test assertion thất bại, JaCoCo vẫn có cơ hội dựng báo cáo**, sau đó Ant mới trả lỗi cho CI. File minh họa:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-junit-coverage" default="verify" basedir=".">

    <!-- Source và JAR công cụ -->
    <property name="src.main.dir" location="src/main/java"/>
    <property name="src.test.dir" location="src/test/java"/>
    <property name="junit.console.jar"
              location="tools/junit/junit-platform-console-standalone-1.10.2.jar"/>
    <property name="jacoco.agent.jar"
              location="tools/jacoco/org.jacoco.agent-0.8.12-runtime.jar"/>
    <property name="jacoco.cli.jar"
              location="tools/jacoco/org.jacoco.cli-0.8.12-nodeps.jar"/>

    <!-- File class trung gian -->
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="test.classes.dir" location="${build.dir}/test-classes"/>

    <!-- Báo cáo có thể tải/lưu từ CI -->
    <property name="artifacts.dir" location="artifacts"/>
    <property name="junit.reports.dir"
              location="${artifacts.dir}/reports/junit"/>
    <property name="coverage.dir" location="${artifacts.dir}/coverage"/>
    <property name="jacoco.exec.file"
              location="${coverage.dir}/jacoco.exec"/>
    <property name="coverage.html.dir"
              location="${coverage.dir}/html"/>
    <property name="coverage.xml.file"
              location="${coverage.dir}/jacoco.xml"/>
    <property name="coverage.csv.file"
              location="${coverage.dir}/jacoco.csv"/>

    <!-- Kiểm tra dependencies trước khi biên dịch. -->
    <target name="check-tools">
        <available file="${junit.console.jar}" type="file"
                   property="junit.console.exists"/>
        <available file="${jacoco.agent.jar}" type="file"
                   property="jacoco.agent.exists"/>
        <available file="${jacoco.cli.jar}" type="file"
                   property="jacoco.cli.exists"/>
        <fail unless="junit.console.exists"
              message="Thiếu JUnit Platform Console Standalone JAR"/>
        <fail unless="jacoco.agent.exists"
              message="Thiếu JaCoCo runtime agent JAR"/>
        <fail unless="jacoco.cli.exists"
              message="Thiếu JaCoCo CLI nodeps JAR"/>
    </target>

    <target name="prepare" depends="check-tools">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${test.classes.dir}"/>
        <mkdir dir="${junit.reports.dir}"/>
        <mkdir dir="${coverage.html.dir}"/>
    </target>

    <target name="compile-main" depends="prepare">
        <javac srcdir="${src.main.dir}"
               destdir="${classes.dir}"
               release="17"
               encoding="UTF-8"
               debug="true"
               debuglevel="lines,source"
               includeantruntime="false"/>
    </target>

    <target name="compile-tests" depends="compile-main">
        <javac srcdir="${src.test.dir}"
               destdir="${test.classes.dir}"
               release="17"
               encoding="UTF-8"
               includeantruntime="false">
            <classpath>
                <pathelement location="${classes.dir}"/>
                <pathelement location="${junit.console.jar}"/>
            </classpath>
        </javac>
    </target>

    <!-- Chạy JUnit Platform trong JVM riêng có JaCoCo agent. -->
    <target name="run-tests" depends="compile-tests">
        <java classname="org.junit.platform.console.ConsoleLauncher"
              fork="true"
              failonerror="false"
              resultproperty="tests.exit.code">

            <jvmarg
                value="-javaagent:${jacoco.agent.jar}=destfile=${jacoco.exec.file},append=false"/>

            <classpath>
                <pathelement location="${junit.console.jar}"/>
                <pathelement location="${classes.dir}"/>
                <pathelement location="${test.classes.dir}"/>
            </classpath>

            <arg value="execute"/>
            <arg value="--scan-class-path"/>
            <arg value="--fail-if-no-tests"/>
            <arg value="--reports-dir"/>
            <arg file="${junit.reports.dir}"/>
        </java>
    </target>

    <!-- Dùng CLI để đổi jacoco.exec thành báo cáo đọc được. -->
    <target name="coverage-report" depends="run-tests">
        <available file="${jacoco.exec.file}" type="file"
                   property="jacoco.exec.exists"/>
        <fail unless="jacoco.exec.exists"
              message="Thiếu jacoco.exec: xem trạng thái JVM test/agent"/>

        <java jar="${jacoco.cli.jar}"
              fork="true"
              failonerror="true">
            <arg value="report"/>
            <arg file="${jacoco.exec.file}"/>
            <arg value="--classfiles"/>
            <arg file="${classes.dir}"/>
            <arg value="--sourcefiles"/>
            <arg file="${src.main.dir}"/>
            <arg value="--html"/>
            <arg file="${coverage.html.dir}"/>
            <arg value="--xml"/>
            <arg file="${coverage.xml.file}"/>
            <arg value="--csv"/>
            <arg file="${coverage.csv.file}"/>
        </java>
    </target>

    <!-- Test không đạt => báo lỗi cho CI sau khi thử sinh report. -->
    <target name="verify" depends="coverage-report">
        <condition property="tests.passed">
            <equals arg1="${tests.exit.code}" arg2="0"/>
        </condition>
        <fail unless="tests.passed"
              message="JUnit Platform thất bại hoặc không tìm thấy test"/>
        <echo message="JUnit XML: ${junit.reports.dir}"/>
        <echo message="Coverage HTML: ${coverage.html.dir}/index.html"/>
    </target>

    <target name="clean">
        <delete dir="${build.dir}"/>
        <delete dir="${artifacts.dir}"/>
    </target>
</project>
```

Ví dụ cố ý dùng `location` cho đường dẫn và các `<arg>` riêng lẻ. Ant sẽ xử lý path của Java classpath theo hệ điều hành đang chạy, thay vì phải tự ghép dấu `;` trên Windows hoặc `:` trên Linux/macOS. Mọi đầu ra được dẫn xuất từ `basedir`; không hardcode thư mục của một máy phát triển.

### 4.1. Compile main và test cần classpath khác nhau

Mã nguồn chính `DiscountCalculator.java` không phụ thuộc JUnit, nên target `compile-main` chỉ cần JDK. Target `compile-tests` cần cả class ứng dụng và JUnit API để biên dịch các import như `org.junit.jupiter.api.Test`. Vì JAR Console Standalone trong ví dụ có JUnit API, nó được đưa vào classpath test.

`debug="true"` và `debuglevel="lines,source"` giúp compiler lưu thông tin số dòng trong file class. Nhờ đó JaCoCo có thể liên kết bytecode với source để tô màu line coverage trên trang HTML. Nếu class được biên dịch thiếu thông tin dòng, số liệu instruction có thể còn nhưng HTML không thể hiện số dòng như mong muốn.

### 4.2. Vì sao JVM chạy test phải được fork?

JaCoCo thu coverage theo cơ chế **Java instrumentation agent**, được JVM nạp bằng tùy chọn:

```text
-javaagent:<đường-dẫn-agent.jar>=destfile=<đường-dẫn-jacoco.exec>,append=false
```

Target `run-tests` đặt `fork="true"` để JVM test được khởi động với agent riêng. Nếu chỉ gắn agent cho tiến trình Ant mà test chạy trong JVM khác, dữ liệu thu được sẽ không phản ánh chương trình cần kiểm tra.

Tham số `destfile` chỉ nơi ghi `jacoco.exec`. `append=false` giúp tránh trộn số liệu của lượt chạy hiện tại với lượt cũ; lệnh `clean verify` còn xóa toàn bộ báo cáo cũ trước khi tạo lại. `jacoco.exec` là **dữ liệu nhị phân**, không phải XML hoặc HTML. JaCoCo thường ghi file lúc JVM kết thúc bình thường; nếu tiến trình bị kill hoặc crash, báo cáo có thể thiếu.

### 4.3. JUnit Platform tạo test report như thế nào?

Các đối số của ConsoleLauncher là:

```text
execute
--scan-class-path
--fail-if-no-tests
--reports-dir <đường-dẫn>
```

`execute` là lệnh chạy test trong ConsoleLauncher của phiên bản minh họa. `--scan-class-path` tìm các lớp test trên classpath. `--fail-if-no-tests` tránh tình huống pipeline xanh dù không phát hiện một bài kiểm thử nào. `--reports-dir` đặt vị trí ghi test report XML.

File XML thường mang dạng `TEST-*.xml`; tên cụ thể phụ thuộc engine/listener và phiên bản, nên CI nên cấu hình glob thích hợp. Nếu launcher không tìm thấy test do tên package, classpath hoặc test engine sai, cần xử lý nguyên nhân thay vì coi “0 test, 0 failure” là thành công.

Vì task `<java>` sử dụng `resultproperty="tests.exit.code"` và `failonerror="false"`, Ant **ghi lại exit code** nhưng không dừng ngay nếu một assertion thất bại. Các target phụ thuộc tiếp theo vẫn có thể tạo coverage. Target `verify` cuối cùng so sánh mã thoát với `0` và gọi `<fail>` khi test không đạt; vì vậy trạng thái CI không bị che giấu.

### 4.4. JaCoCo CLI cần nhiều hơn `jacoco.exec`

`jacoco.exec` chỉ chứa dữ liệu thực thi; CLI cần đọc file class để xác định class/method/line/branch nào được bao phủ. Lệnh tương đương:

```text
java -jar org.jacoco.cli-0.8.12-nodeps.jar report jacoco.exec
     --classfiles build/classes
     --sourcefiles src/main/java
     --html artifacts/coverage/html
     --xml artifacts/coverage/jacoco.xml
     --csv artifacts/coverage/jacoco.csv
```

| Đối số | Tác dụng |
|---|---|
| `report jacoco.exec` | Phân tích dữ liệu từ agent. |
| `--classfiles build/classes` | Cung cấp bytecode của **ứng dụng** tương ứng với lần chạy test. |
| `--sourcefiles src/main/java` | Cung cấp mã nguồn để hiển thị line coverage. |
| `--html ...` | Sinh report web, có trang `index.html`. |
| `--xml ...` | Sinh report máy đọc để tích hợp dashboard/CI. |
| `--csv ...` | Sinh số liệu ở dạng bảng CSV. |

Ta cố ý **không** truyền `build/test-classes` vào `--classfiles`, vì mục tiêu là đo độ bao phủ mã ứng dụng, không tính cả lớp test vào mẫu số. Với một module thực tế có nhiều thư mục class, khai báo đúng các đầu ra ứng dụng tương ứng. Nếu classfiles khác phiên bản class đã chạy, kết quả không đáng tin cậy.

## 5. Chạy thực hành và tìm báo cáo

Từ gốc repository:

```bash
ant -version
java -version
ant -f build.xml clean verify
```

Sau lượt chạy thông thường, có thể thấy:

```text
build/
├── classes/example/DiscountCalculator.class
└── test-classes/example/DiscountCalculatorTest.class

artifacts/
├── reports/junit/
│   └── TEST-*.xml                  # tên thực tế tùy engine/listener
└── coverage/
    ├── jacoco.exec
    ├── jacoco.xml
    ├── jacoco.csv
    └── html/
        ├── index.html
        └── ...
```

Mở `artifacts/coverage/html/index.html` bằng trình duyệt để đi từ tổng quan xuống package, class và source line. Đọc `artifacts/reports/junit/TEST-*.xml` bằng editor hoặc import vào CI để thấy số test, thời lượng và các failure. Đừng nhầm JUnit XML với `jacoco.xml`: chúng là **hai schema khác nhau** và được các công cụ khác nhau tiêu thụ.

### 5.1. Thử một test thất bại

Đổi tạm assertion:

```java
@Test
void appliesDiscountToMember() {
    assertEquals(95, DiscountCalculator.finalPrice(100, true));
}
```

Sau đó chạy lại `ant -f build.xml clean verify`. Kết quả thực tế là `90` nên test thất bại. Với thiết kế target đã chọn:

1. JUnit Platform báo failure và cố ghi XML.
2. `run-tests` ghi exit code khác `0` vào property thay vì dừng ngay.
3. `coverage-report` cố tạo JaCoCo HTML/XML từ dữ liệu agent.
4. `verify` mới trả lỗi cho Ant/CI, giúp job hiển thị trạng thái thất bại chính xác.

Khôi phục assertion về `90` sau khi quan sát. Nếu lỗi xảy ra từ trước khi test JVM chạy — chẳng hạn thiếu JAR, lỗi compiler, lỗi kích hoạt agent — thì `jacoco.exec` hoặc XML có thể chưa tồn tại. Không nên giả định mọi failure đều tạo đủ hai báo cáo; log của Ant/CI khi đó là nguồn chẩn đoán đầu tiên.

## 6. Đo branch coverage thay vì chỉ nhìn test PASS

Trong `DiscountCalculator.finalPrice` có một nhánh `if (member)` với kết quả đúng và sai. Hai test ban đầu cho phép quan sát cả hai đường đi. Hãy tạm bỏ test `keepsPriceForRegularCustomer`, giữ một test thành viên, rồi chạy:

```bash
ant -f build.xml clean verify
```

JUnit có thể vẫn báo PASS vì test còn lại đúng, nhưng nhánh dành cho khách thường không được thực thi. Trang HTML coverage sẽ cho thấy vùng code còn thiếu. Khôi phục test thứ hai, chạy lại build sạch và so sánh các counter.

Các chỉ số JaCoCo phổ biến:

| Counter | Điều được đo | Ý nghĩa |
|---|---|---|
| **INSTRUCTION** | Instruction bytecode đã/chưa được thực thi | Thể hiện mức độ thực thi theo JVM bytecode. |
| **LINE** | Dòng source được liên kết với instruction đã/chưa chạy | Giúp tìm dòng chưa được test đi qua. |
| **BRANCH** | Nhánh quyết định đã/chưa đi qua | Một `if` có thể được chạy nhưng chỉ theo một hướng. |
| **METHOD** | Method được gọi hoặc không | Dễ tìm những method chưa được kích hoạt. |
| **CLASS** | Class đã/chưa được thực thi | Bao phủ theo phạm vi class. |
| **COMPLEXITY** | Độ phức tạp chu trình và phần được bao phủ theo mô hình JaCoCo | Gợi ý khu vực có nhiều trường hợp logic cần kiểm thử. |

Ví dụ **giả định** một đoạn `jacoco.xml` có counter:

```xml
<counter type="LINE" missed="2" covered="6"/>
```

Tỷ lệ tương ứng là:

```text
covered / (covered + missed) * 100
       = 6 / (6 + 2) * 100
       = 75%
```

Các số này chỉ minh họa công thức, **không phải dự báo chính xác coverage của ví dụ Java**. Compiler, cấu trúc bytecode và cách JaCoCo tính counter quyết định số liệu thực tế. Không tính coverage bằng số dòng văn bản của file Java một cách thủ công.

**100% line coverage không nhất thiết là 100% branch coverage.** Một dòng chứa điều kiện có thể được chạy mà chưa đi qua tất cả kết quả true/false. Ngay cả 100% các counter cũng không tự khẳng định nghiệp vụ đúng: test có thể thiếu assertion về giá trị biên, exception hoặc điều kiện đồng thời.

## 7. Đồng nhất phiên bản class và dữ liệu coverage

JaCoCo agent đo các class thực sự được JVM nạp. Khi sinh báo cáo, CLI đọc classfiles để ánh xạ các probe, dòng và nhánh. Nếu bạn **thay source, biên dịch lại class sau khi test nhưng trước khi sinh report**, `jacoco.exec` có thể không còn khớp với bytecode mới.

Quy trình an toàn cho một lượt build:

```text
clean output cũ
      |
      v
compile source và test
      |
      v
chạy test với JaCoCo agent
      |
      v
đọc chính classfiles vừa được chạy để sinh report
      |
      v
kiểm tra test gate và lưu artifact của cùng một run
```

Với nhiều module, chọn đúng classfiles của từng module; nếu gộp nhiều `.exec`, phải quản lý phiên bản, tiến trình và cách merge. Trong ví dụ, `append=false` cùng `clean` tránh việc kết quả cũ làm sai lệch số liệu.

JaCoCo chỉ quan sát **JVM được gắn agent**. Nếu test kích hoạt ứng dụng trên một server JVM khác hoặc tạo child process chạy mã cần đo, agent của JVM chạy ConsoleLauncher không tự theo dõi toàn bộ mã ở tiến trình đó. Để đo server, cần instrument đúng tiến trình chạy server và thiết kế thu thập dữ liệu tương ứng.

## 8. Đưa báo cáo lên CI/CD

Khi chạy pipeline, nên lưu XML JUnit và báo cáo JaCoCo dưới dạng artifact ngay cả khi test thất bại. Ví dụ một phần workflow GitHub Actions sau khi repository hoặc bước trước đã chuẩn bị đúng ba JAR trong `tools/`:

```yaml
name: Ant JUnit Platform Coverage

on:
  push:
  pull_request:

jobs:
  coverage:
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
          sudo apt-get install -y ant

      # Bước provision riêng cần đặt 3 JAR đã ghim phiên bản
      # vào tools/ trước bước Ant dưới đây.

      - name: Run JUnit and generate coverage
        run: ant -f build.xml clean verify

      - name: Save JUnit and coverage reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: junit-jacoco-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            artifacts/reports/junit/
            artifacts/coverage/
          if-no-files-found: warn
          retention-days: 14
```

`always()` cho phép **cố upload** artifact dù bước Ant trước đó đã báo lỗi. Điều này không làm job test thành công giả. Tuy nhiên runner bị kill, hết dung lượng hoặc chưa tạo được file thì vẫn có thể không có báo cáo để upload. Tên artifact chứa run ID và attempt để phân biệt các lần chạy; matrix nhiều OS/JDK cần bổ sung tên cấu hình tương ứng.

Đoạn workflow sử dụng Ubuntu và giả định JAR công cụ đã có ở vị trí được yêu cầu; khi áp dụng thực tế, thêm bước tải và xác minh checksum cụ thể của dự án. Không đặt `continue-on-error: true` cho bước test chỉ để CI xanh.

**Upload file không đồng nghĩa hệ thống CI tự đọc số liệu.** CI cần một JUnit XML publisher đọc `artifacts/reports/junit/TEST-*.xml`, và một JaCoCo/XML coverage importer nếu muốn hiện coverage trong dashboard. Chỉ dùng cùng tên “XML” không có nghĩa `jacoco.xml` là JUnit XML.

Ví dụ trong GitLab CI, phần cấu hình artifact của job:

```yaml
artifacts:
  when: always
  paths:
    - artifacts/reports/junit/
    - artifacts/coverage/
  reports:
    junit: artifacts/reports/junit/TEST-*.xml
  expire_in: 14 days
```

Trên Jenkins, bước `junit` có thể đọc `artifacts/reports/junit/TEST-*.xml`; `archiveArtifacts` lưu HTML/XML JaCoCo, và plugin coverage phù hợp có thể phân tích `jacoco.xml`. Các cấu hình import coverage cụ thể tùy phiên bản và plugin đang cài.

## 9. Có cần đặt ngưỡng coverage không?

**Đo** coverage và **bắt build thất bại khi coverage dưới ngưỡng** là hai công việc riêng. Ví dụ Ant ở trên tạo số liệu, nhưng chưa đặt ngưỡng như 80% branch coverage. Có thể bổ sung một tool kiểm tra coverage hoặc JaCoCo Ant tasks nếu dự án thực sự cần quality gate; lựa chọn ngưỡng nên có lý do.

Khi đặt quality gate, cần trả lời:

- Đo toàn bộ repository hay chỉ mã mới thay đổi?
- Dùng instruction, line, branch hay nhiều counter?
- Có những file generated/bootstrap cần loại trừ vì không mang logic cần test không?
- Có yêu cầu tối thiểu số test? Có xử lý lỗi thiếu `jacoco.exec` rõ ràng không?
- Chính sách cho test fail và coverage thấp có khác nhau không?

Không lấy một tỷ lệ mặc định làm tiêu chuẩn chung cho mọi sản phẩm. **Chất lượng assertion và các tình huống nghiệp vụ được kiểm tra** mới là mục tiêu, coverage là tín hiệu hỗ trợ phát hiện phần mã chưa được đi qua.

## 10. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `ClassNotFoundException: org.junit.platform.console.ConsoleLauncher` | JAR Console Standalone thiếu hoặc classpath sai | Kiểm tra `junit.console.jar`. |
| Test không được phát hiện | Sai classpath, package, engine hoặc build không có test | Kiểm tra `test-classes`, `--scan-class-path` và `--fail-if-no-tests`. |
| Test không biên dịch được vì `org.junit.jupiter.api` | Chưa đưa JUnit API vào compile-test classpath | Thêm Console Standalone JAR vào `<javac>` của test. |
| JVM báo lỗi `-javaagent` | Dùng nhầm JAR CLI, agent thiếu hoặc không tương thích | Dùng đúng `org.jacoco.agent-...-runtime.jar`. |
| Không có `jacoco.exec` | Agent không gắn vào JVM test, tiến trình bị kill hoặc path sai | Kiểm tra `fork="true"`, `<jvmarg>`, `destfile`. |
| Có XML JUnit nhưng coverage bằng 0 | Agent không quan sát JVM chạy mã ứng dụng, chọn sai classfiles | Gắn agent đúng JVM và so classfiles với bản đã chạy. |
| HTML không tô màu dòng source | Class thiếu debug line info hoặc `--sourcefiles` sai | Biên dịch với debug, chỉ đúng source path. |
| Coverage báo class không khớp | Dùng classfiles khác commit/lần biên dịch | Chạy lại `clean verify`, không thay bytecode giữa test và report. |
| Test fail nhưng không có coverage report | Ant dừng ở bước chạy test | Ghi exit code bằng `resultproperty`, fail sau target report. |
| Build có 0 test nhưng vẫn xanh | Thiếu điều kiện phát hiện 0 test | Sử dụng `--fail-if-no-tests` và kiểm tra discovery. |
| CI lưu file XML nhưng không hiện kết quả | Chỉ upload artifact, chưa cấu hình parser | Thiết lập publisher JUnit và JaCoCo riêng. |
| JaCoCo không đọc được bytecode | JaCoCo quá cũ so với Java bytecode | Chọn phiên bản JaCoCo hỗ trợ toolchain. |

Một sai lầm quan trọng là chạy test xong rồi **tái biên dịch source trước khi tạo coverage**: XML JUnit vẫn có thể đúng nhưng bản đồ JaCoCo không còn khớp class đã được instrument. Một sai lầm khác là đưa cả `build/test-classes` vào `--classfiles`, làm báo cáo đo cả phần mã kiểm thử thay vì chỉ mã ứng dụng.

## 11. Bài thực hành củng cố

1. Tạo hai file Java ở mục 3 và đặt ba JAR công cụ vào đúng thư mục.
2. Chạy `ant -f build.xml clean verify`. Mở báo cáo JUnit XML và JaCoCo HTML để phân biệt trạng thái test với coverage.
3. Xóa tạm test nhánh khách thường, chạy lại build sạch, quan sát branch coverage. Sau đó khôi phục test.
4. Đổi expected của test thành một kết quả sai, chạy lại. Kiểm tra JUnit XML có failure và target `verify` trả lỗi sau khi JaCoCo cố xuất báo cáo.
5. Tạo tình huống launcher không tìm thấy test để quan sát `--fail-if-no-tests`; giải quyết classpath/discovery thay vì chấp nhận một lần chạy 0 test.
6. Đưa hai loại XML và HTML lên CI với bước upload chạy sau test fail; phân biệt việc **lưu báo cáo** với việc **công bố kết quả test và coverage lên giao diện CI**.

Qua bài thực hành, người học nắm được chuỗi trách nhiệm: **JUnit Platform chạy kiểm thử và xuất JUnit XML; JaCoCo agent thu dữ liệu thực thi; JaCoCo CLI tạo báo cáo coverage; Ant điều phối, giữ đúng đường dẫn và trả đúng trạng thái thành/bại cho CI**. Đây là nền tảng để mở rộng sang dự án nhiều module, chạy test trên nhiều JDK và đặt quality gate có căn cứ.
