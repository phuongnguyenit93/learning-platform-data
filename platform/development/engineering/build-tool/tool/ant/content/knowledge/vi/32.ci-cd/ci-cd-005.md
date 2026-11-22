# Chạy ma trận JDK, hệ điều hành và cấu hình cần hỗ trợ với Apache Ant trong CI/CD

## 1. Mục tiêu của kiểm thử ma trận

Một dự án Java dùng **Apache Ant** có thể chạy `ant verify` thành công trên máy phát triển nhưng vẫn thất bại trên JDK khác, hệ điều hành khác hoặc cấu hình ứng dụng khác. Những ví dụ thường gặp:

- Mã biên dịch trên JDK 21 nhưng gọi API không tồn tại trên JDK 17 mà dự án cam kết hỗ trợ.
- Đường dẫn tệp chạy được trên Windows nhưng lỗi trên Linux do khác biệt chữ hoa/chữ thường.
- Chương trình dùng resource ở cấu hình `dev` nhưng artifact của cấu hình `prod` thiếu file cần thiết.
- Test phụ thuộc múi giờ, locale, encoding, ký tự xuống dòng hoặc quyền thực thi của script.
- Một task Ant gọi công cụ chỉ có trên Linux, khiến quy trình build thất bại trên Windows.

**Ma trận CI/CD (build/test matrix)** là tập hợp những tổ hợp môi trường mà dự án muốn kiểm chứng. Giả sử dự án hỗ trợ:

| Trục | Giá trị |
| --- | --- |
| JDK | 17, 21 |
| Hệ điều hành | Ubuntu, Windows, macOS |
| Cấu hình | `dev`, `prod` |

Chạy đầy đủ cả ba trục tạo ra:

\[
2\text{ JDK}\times3\text{ OS}\times2\text{ profiles}=12\text{ jobs}
\]

Mỗi job phải cung cấp kết quả độc lập: biên dịch được, test đạt, artifact được tạo và chạy đúng. Nếu `Windows / JDK 17 / prod` thất bại, ma trận **chưa đạt**, ngay cả khi 11 job khác thành công, nếu tổ hợp ấy thuộc cam kết hỗ trợ.

Bài học hướng tới bốn kết quả:

1. Xác định phạm vi JDK, hệ điều hành và cấu hình thật sự cần hỗ trợ.
2. Xây `build.xml` dùng chung có thể nhận các tham số cấu hình từ CI.
3. Tạo pipeline chạy Ant trên từng tổ hợp, thu được test và artifact.
4. Tổng hợp kết quả để quyết định chấp nhận thay đổi hoặc phát hành.

## 2. Phân chia trách nhiệm giữa Ant và CI

Ant tập trung vào **target, task và quan hệ phụ thuộc**: biên dịch với `<javac>`, sao chép bằng `<copy>`, kiểm thử với `<java>`/`<junit>`, đóng gói với `<jar>`. Ant không tự thuê runner Windows, cấp phát máy Linux và chọn JDK trên hạ tầng CI.

| Thành phần | Trách nhiệm |
| --- | --- |
| `build.xml` | Định nghĩa logic build, test, package, verify |
| `ant -D...` | Truyền profile và lựa chọn biên dịch cho một lượt build |
| CI matrix | Sinh các job từ tập tổ hợp được hỗ trợ |
| Runner | Cấp môi trường hệ điều hành và kiến trúc |
| Toolchain setup | Cài JDK, Ant, dependency và công cụ đi kèm |
| Artifact/test report | Ghi lại kết quả và sản phẩm của từng job |
| Quality gate | Yêu cầu các tổ hợp bắt buộc thành công |

Luồng tổng quát:

```text
             Commit / Pull request
                      |
                      v
              Sinh tổ hợp CI
                      |
       +--------------+--------------+
       |              |              |
       v              v              v
   Ubuntu/17/dev  Windows/21/prod  macOS/21/dev
       |              |              |
       v              v              v
    Cài JDK + Ant, gọi cùng target verify
       |              |              |
       v              v              v
    Biên dịch, test, đóng gói, smoke test
       |              |              |
       +--------------+--------------+
                      |
                      v
            Tổng hợp trạng thái
```

Sơ đồ chỉ minh họa ba ô; ma trận đầy đủ bên trên gồm 12 ô.

## 3. Chọn các trục theo chính sách hỗ trợ

### 3.1. JDK biên dịch và JDK chạy chương trình

Hai khái niệm này khác nhau:

- **Build JDK**: JVM/compiler đang chạy Ant và biên dịch mã nguồn.
- **Runtime JDK**: JVM mà người dùng thật hoặc hệ thống triển khai dùng để chạy artifact.
- **Target release**: mức API và phiên bản bytecode mà lệnh biên dịch được phép sinh ra.

Ví dụ, trên JDK 21 có thể dùng `<javac release="17">` để nhắm Java 17. Điều đó giúp tránh sử dụng API Java mới hơn mức đích trong mã được biên dịch, nhưng **không thay thế** việc chạy test trên runtime JDK 17 thật. Dependency của dự án cũng cần tương thích mức runtime thấp nhất.

Nếu dự án hỗ trợ JDK 17 và JDK 21, nên có các job kiểm thử trên **cả hai JVM**. Nếu chỉ phát hành một bản JAR nhắm Java 17, có thể dùng chung `release=17` trên các job, miễn điều kiện toolchain và dependency phù hợp.

### 3.2. Hệ điều hành

Ma trận OS phải xuất phát từ mục đích sản phẩm. Một ứng dụng chỉ chạy trên Linux server có thể ưu tiên Linux. Một thư viện Java được công bố là đa nền tảng cần kiểm tra cả Windows và macOS.

Các nhãn runner như `ubuntu-latest`, `windows-latest` và `macos-latest` có thể chuyển sang image mới theo thời gian. Nếu cam kết của sản phẩm phụ thuộc phiên bản OS cụ thể, hãy dùng image được định danh rõ và ghi phiên bản trong log. Runner ảo không tự mô phỏng hết môi trường người dùng: filesystem, kiến trúc CPU, native library và quyền hệ thống có thể khác.

### 3.3. Cấu hình ứng dụng

Cấu hình có thể bao gồm profile `dev`/`prod`, feature flag, loại database, chế độ kiểm thử hoặc tập tài nguyên khác nhau. Các giá trị được đưa vào matrix nên làm thay đổi hành vi thực sự cần kiểm chứng.

Không đưa secret sản xuất vào tên profile, `matrix` hoặc tệp commit công khai. Profile `prod` trong bài thực hành chỉ là **dữ liệu mô phỏng** để kiểm tra đúng việc lựa chọn cấu hình.

### 3.4. Phân loại các tổ hợp

| Nhóm | Cách xử lý |
| --- | --- |
| Bắt buộc theo cam kết hỗ trợ | Tất cả phải đạt trước merge/release theo quy định |
| Mở rộng hoặc kiểm tra trước release | Chạy ở CI định kỳ hoặc trước khi phát hành |
| Thử nghiệm, như JDK early access | Theo dõi riêng; không tự coi là đã hỗ trợ chính thức |

Thêm một trục 3 loại database vào ma trận 12 job sẽ tạo tới **36 job** nếu chạy toàn bộ tích Descartes. Vì vậy cần cân bằng độ bao phủ với chi phí runner, nhưng không được âm thầm loại bỏ môi trường đang được cam kết hỗ trợ.

## 4. Tạo dự án Ant mẫu có hai profile

Để mỗi ô matrix kiểm tra kết quả cụ thể, ta dùng một chương trình Java nhỏ đọc file cấu hình từ classpath. Bài thực hành không cần thư viện test bên ngoài; kiểm thử là chương trình Java ném `AssertionError` khi kết quả sai.

```text
ant-matrix-demo/
├── build.xml
├── config/
│   ├── dev/app.properties
│   └── prod/app.properties
└── src/
    ├── main/java/demo/App.java
    └── test/java/demo/AppTest.java
```

**`config/dev/app.properties`**

```properties
app.profile=dev
```

**`config/prod/app.properties`**

```properties
app.profile=prod
```

**`src/main/java/demo/App.java`**

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class App {
    private App() {}

    public static String configuredProfile() throws IOException {
        Properties props = new Properties();
        try (InputStream in = App.class.getResourceAsStream("/app.properties")) {
            if (in == null) {
                throw new IOException("Missing app.properties");
            }
            props.load(in);
        }
        String value = props.getProperty("app.profile");
        if (value == null || value.isBlank()) {
            throw new IOException("Missing app.profile");
        }
        return value;
    }

    public static void main(String[] args) throws IOException {
        System.out.println("profile=" + configuredProfile());
    }
}
```

**`src/test/java/demo/AppTest.java`**

```java
package demo;

public final class AppTest {
    private AppTest() {}

    public static void main(String[] args) throws Exception {
        String expected = System.getProperty("expected.profile");
        String actual = App.configuredProfile();
        if (expected == null || !expected.equals(actual)) {
            throw new AssertionError(
                "Expected " + expected + ", but got " + actual
            );
        }
        System.out.println("Profile test passed: " + actual);
    }
}
```

Nếu một job chọn `prod` nhưng JAR chứa `app.properties` của `dev`, kiểm thử sẽ thất bại. Đây là một phép kiểm chứng nội dung, thay vì chỉ kiểm tra file artifact có tồn tại hay không.

### 4.1. `build.xml` để CI gọi thống nhất

Ví dụ cần JDK 17 trở lên và bản Ant có hỗ trợ thuộc tính `release` của `<javac>`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-matrix-demo" default="verify" basedir=".">
    <property name="build.profile" value="dev"/>
    <property name="bytecode.release" value="17"/>

    <property name="build.dir" location="build/${build.profile}"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="tests.dir" location="${build.dir}/test-classes"/>
    <property name="dist.dir" location="${build.dir}/dist"/>

    <target name="validate">
        <condition property="supported.profile">
            <or>
                <equals arg1="${build.profile}" arg2="dev"/>
                <equals arg1="${build.profile}" arg2="prod"/>
            </or>
        </condition>
        <fail unless="supported.profile"
              message="Unsupported profile: ${build.profile}"/>
        <available file="config/${build.profile}/app.properties"
                   property="config.exists"/>
        <fail unless="config.exists"
              message="Missing config file for ${build.profile}"/>
    </target>

    <target name="clean">
        <delete dir="${build.dir}" quiet="true"/>
    </target>

    <target name="compile" depends="validate">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="src/main/java"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8"
               debug="true"
               release="${bytecode.release}"/>
    </target>

    <target name="resources" depends="compile">
        <copy file="config/${build.profile}/app.properties"
              tofile="${classes.dir}/app.properties"/>
    </target>

    <target name="compile-tests" depends="resources">
        <mkdir dir="${tests.dir}"/>
        <javac srcdir="src/test/java"
               destdir="${tests.dir}"
               includeantruntime="false"
               encoding="UTF-8"
               debug="true"
               release="${bytecode.release}">
            <classpath>
                <pathelement location="${classes.dir}"/>
            </classpath>
        </javac>
    </target>

    <target name="test" depends="compile-tests">
        <java classname="demo.AppTest"
              fork="true"
              failonerror="true">
            <classpath>
                <pathelement location="${classes.dir}"/>
                <pathelement location="${tests.dir}"/>
            </classpath>
            <sysproperty key="expected.profile"
                         value="${build.profile}"/>
        </java>
    </target>

    <target name="dist" depends="resources">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${dist.dir}/app.jar"
             basedir="${classes.dir}"
             duplicate="fail">
            <manifest>
                <attribute name="Main-Class" value="demo.App"/>
                <attribute name="Implementation-Version" value="1.0.0"/>
            </manifest>
        </jar>
    </target>

    <target name="verify" depends="test,dist">
        <echo message="Verified ${build.profile}: ${dist.dir}/app.jar"/>
    </target>
</project>
```

Ý nghĩa:

- `-Dbuild.profile=prod` ưu tiên giá trị mặc định `dev` trong file Ant. Ant properties không bị ghi đè tùy tiện sau khi được đặt.
- `-Dbytecode.release=17` xác định mức bytecode/API đầu ra; không đổi JDK thực tế đang chạy Ant.
- `validate` từ chối profile lạ hoặc cấu hình thiếu.
- Các thư mục `build/dev` và `build/prod` tách đầu ra, hạn chế lấy nhầm tài nguyên của profile khác.
- `test` chạy JVM con và `failonerror="true"` để lỗi test làm build đỏ.
- `dist` đưa class cùng `app.properties` vào JAR, còn `verify` đòi hỏi cả test và đóng gói.

Chạy thủ công trên máy đã có Ant và JDK:

```bash
ant -version
java -version
ant -noinput -Dbuild.profile=dev clean verify
java -jar build/dev/dist/app.jar
ant -noinput -Dbuild.profile=prod clean verify
java -jar build/prod/dist/app.jar
```

Lệnh chạy JAR phải lần lượt in `profile=dev` và `profile=prod`. Target `clean` chỉ xóa thư mục đầu ra của profile được chọn.

## 5. Khai báo GitHub Actions matrix

GitHub Actions là ví dụ cụ thể cho cú pháp CI. Dự án dùng Jenkins hoặc GitLab CI vẫn có thể gọi cùng `build.xml`, nhưng cần thay phần khai báo matrix và thiết lập runner.

Tạo **`.github/workflows/ant-matrix.yml`**:

```yaml
name: Ant compatibility matrix

on:
  push:
  pull_request:
  workflow_dispatch:

jobs:
  build-matrix:
    name: ${{ matrix.os }} / JDK ${{ matrix.jdk }} / ${{ matrix.profile }}
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        jdk: ['17', '21']
        profile: [dev, prod]

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Install JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.jdk }}

      - name: Install fixed Ant version
        shell: pwsh
        run: |
          $v = '1.10.15'
          $filename = "apache-ant-$v-bin.zip"
          $url = "https://archive.apache.org/dist/ant/binaries/$filename"
          $archive = Join-Path $env:RUNNER_TEMP $filename
          Invoke-WebRequest -Uri $url -OutFile $archive
          Expand-Archive -LiteralPath $archive -DestinationPath $env:RUNNER_TEMP
          $antHome = Join-Path $env:RUNNER_TEMP "apache-ant-$v"
          "ANT_HOME=$antHome" >> $env:GITHUB_ENV
          (Join-Path $antHome 'bin') >> $env:GITHUB_PATH

      - name: Show toolchain
        shell: pwsh
        run: |
          java -version
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          ant -version
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

      - name: Build and verify
        shell: pwsh
        run: |
          ant -noinput -f build.xml "-Dbuild.profile=${{ matrix.profile }}" "-Dbytecode.release=17" clean verify
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

      - name: Smoke test packaged JAR
        shell: pwsh
        run: |
          java -jar "build/${{ matrix.profile }}/dist/app.jar"
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

      - name: Upload representative artifact
        if: matrix.os == 'ubuntu-latest' && matrix.jdk == '21' && matrix.profile == 'prod'
        uses: actions/upload-artifact@v4
        with:
          name: app-ubuntu-jdk21-prod
          path: build/prod/dist/app.jar
          if-no-files-found: error

  compatibility-gate:
    name: Compatibility gate
    needs: build-matrix
    if: always()
    runs-on: ubuntu-latest
    steps:
      - name: Require all matrix jobs to pass
        shell: bash
        run: |
          test "${{ needs.build-matrix.result }}" = "success"
```

Workflow minh họa giả định runner GitHub-hosted có PowerShell `pwsh` và kết nối được tới kho lưu trữ Ant. Bước tải Ant dùng phiên bản cố định để không phụ thuộc vào bản Ant có sẵn trên runner. Trong hệ thống thật, nên **kiểm tra checksum/chữ ký bản phân phối Ant với giá trị hoặc nguồn tin cậy**, và ghim các action theo commit SHA nếu tổ chức yêu cầu mức bảo vệ chuỗi cung ứng cao hơn. Các nhãn `@v4` cố định major version của action, không cố định một commit bất biến.

### 5.1. Cơ chế hoạt động

**`matrix`** sinh 12 tổ hợp độc lập. `runs-on` chọn hệ điều hành. `setup-java` chuẩn bị JDK theo `matrix.jdk`. Bước cài Ant bảo đảm có Ant trên cả ba OS, vì **`setup-java` không tự cài Ant**.

**`fail-fast: false`** giữ các job còn lại chạy khi một tổ hợp thất bại. Đây là cách thu đủ thông tin tương thích; thiết lập này **không biến lỗi thành thành công**.

**`-Dbytecode.release=17`** cho phép kiểm tra cùng một mức đầu ra Java 17 khi build bằng JDK 17 hoặc JDK 21. Với mã hoặc dependency cần Java 21, phải thiết kế các tổ hợp hợp lệ và target release tương ứng; không thể yêu cầu JDK 17 biên dịch ra release 21.

**`Smoke test packaged JAR`** kiểm tra khả năng chạy artifact, tránh trường hợp unit test qua nhưng JAR thiếu manifest hoặc resource. Trong sản phẩm thực tế, smoke test nên có điều kiện xác nhận kết quả đầu ra; ví dụ này dựa vào JVM exit code, còn `AppTest` đã xác minh profile.

**`Upload representative artifact`** chỉ lưu một artifact phát hành đại diện để giảm chi phí lưu trữ. Nếu cần giữ artifact của từng môi trường, dùng tên khác nhau cho từng tổ hợp, chẳng hạn tên chứa OS/JDK/profile, để không đụng nhau.

**`compatibility-gate`** tổng hợp kết quả của nhóm matrix. Đây có thể là job ổn định được chọn trong bảo vệ nhánh, với điều kiện toàn bộ các job bắt buộc thực sự thuộc nhóm được tổng hợp và quy tắc skip/error không làm sai ý nghĩa trạng thái.

## 6. Chạy ma trận rút gọn: `exclude` và `include`

Toàn bộ 12 tổ hợp thường dễ kiểm soát nhất. Khi một số tổ hợp thật sự không được hỗ trợ, có thể khai báo `exclude`:

```yaml
strategy:
  fail-fast: false
  matrix:
    os: [ubuntu-latest, windows-latest, macos-latest]
    jdk: ['17', '21']
    profile: [dev, prod]
    exclude:
      - os: macos-latest
        jdk: '17'
        profile: dev
```

Ví dụ còn **11 job**. Không nên dùng `exclude` chỉ để che một tổ hợp đang bị lỗi nhưng vẫn nằm trong cam kết hỗ trợ.

Khi chỉ muốn một tập tổ hợp được chỉ định, dùng `include` độc lập:

```yaml
strategy:
  fail-fast: false
  matrix:
    include:
      - os: ubuntu-latest
        jdk: '17'
        profile: dev
      - os: ubuntu-latest
        jdk: '21'
        profile: prod
      - os: windows-latest
        jdk: '17'
        profile: prod
      - os: macos-latest
        jdk: '21'
        profile: prod
```

Danh sách này tạo **bốn job** vì mỗi phần tử của `include` là một tổ hợp được định nghĩa rõ. Đây có thể là ma trận nhanh của pull request, trong khi pipeline trước phát hành vẫn chạy đủ các tổ hợp chính thức.

| Thời điểm | Ví dụ phạm vi |
| --- | --- |
| Pull request | Ma trận bắt buộc hoặc một tập đại diện nếu chính sách cho phép |
| Push nhánh chính | Nhiều tổ hợp hơn để phát hiện lỗi nền tảng |
| Chạy theo lịch | OS/JDK mở rộng, vendor JDK hoặc phiên bản thử nghiệm |
| Trước release | **Toàn bộ** tổ hợp cam kết và kiểm thử artifact phát hành |

Muốn giảm số job đang thực thi đồng thời nhưng vẫn giữ đủ 12 tổ hợp, có thể thêm `max-parallel: 4` vào `strategy`. Việc này điều tiết runner, không giảm số case phải kiểm tra.

## 7. Phân biệt Ant property và Java system property

Lệnh:

```bash
ant -noinput -Dbuild.profile=prod -Dbytecode.release=17 clean verify
```

truyền **Ant properties** đọc được trong XML qua `${build.profile}` và `${bytecode.release}`. Chúng không tự biến thành system properties của JVM chạy chương trình.

| Kiểu tham số | Ví dụ | Nơi nhận |
| --- | --- | --- |
| Ant property | `ant -Dbuild.profile=prod` | `build.xml` |
| JVM option chạy Ant | `ANT_OPTS="-Duser.timezone=UTC"` | JVM của quá trình Ant, tùy launcher |
| System property cho JVM con | `<sysproperty key="expected.profile" value="prod"/>` | Test chạy bằng `<java fork="true">` |

Vì vậy ví dụ dùng:

```xml
<sysproperty key="expected.profile" value="${build.profile}"/>
```

Nếu chương trình phụ thuộc timezone, có thể đặt rõ `<sysproperty key="user.timezone" value="UTC"/>` trên JVM test. Tuy nhiên, nếu sản phẩm phải hỗ trợ nhiều timezone thì cần thêm các test tương ứng thay vì chỉ cố định mọi test về UTC.

Không ghi token, mật khẩu, khóa truy cập production vào `app.properties` hoặc chuỗi `-D...` xuất hiện trong log. Integration test cần secret nên lấy từ cơ chế quản lý bí mật của CI theo quyền hạn tối thiểu; các job kiểm tra cấu hình sản xuất nên dùng giá trị thử nghiệm an toàn.

## 8. Những kiểm tra cần thực hiện ở mỗi ô

### 8.1. Biên dịch và dependency

- Xác nhận `java -version` và `ant -version` trong log, không chỉ tin vào tên job.
- Bảo đảm class và resource được tạo từ source hiện tại; tránh khôi phục output cũ không phù hợp từ cache.
- Nếu nhắm Java 17, kiểm tra dependency không yêu cầu runtime Java mới hơn.
- Nếu dùng annotation processor, plugin compiler hoặc thư viện native, kiểm tra tương thích với từng JDK/OS cần hỗ trợ.

### 8.2. Kiểm thử

- Test phải chạy đủ phạm vi bắt buộc, và lỗi phải làm Ant trả exit code khác 0.
- Nếu dùng JUnit, tạo XML report và giữ kết quả theo từng tổ hợp.
- Không cấu hình bỏ qua lỗi chỉ vì một job chậm hoặc khó tái hiện.
- Các test riêng cho OS được phép có điều kiện chạy nhưng phải phản ánh đặc điểm tính năng thật, không che đi môi trường có hỗ trợ.

### 8.3. Artifact

- Kiểm tra JAR/WAR/ZIP chứa đủ class, resource, manifest và cấu trúc yêu cầu.
- Chạy smoke test từ artifact đã đóng gói, không chỉ từ thư mục class.
- Nếu cần quyền thực thi script trên Linux/macOS, kiểm tra bit executable sau đóng gói/giải nén.
- Nếu có bản phát hành duy nhất, kiểm tra **chính bản artifact sẽ được phát hành** trên các runtime mục tiêu.

### 8.4. Khác biệt hệ điều hành

| Chủ đề | Điều cần lưu ý |
| --- | --- |
| Tên tệp | Linux thường phân biệt hoa/thường; Windows thường không phân biệt theo mặc định |
| Đường dẫn | Dùng `location`, `<path>` và task Ant đa nền tảng thay vì nối chuỗi đường dẫn thủ công |
| Shell | Lệnh `rm -rf` của Unix không phải PowerShell; ưu tiên `<delete>` trong Ant |
| Encoding | Đặt UTF-8 cho nguồn/tài nguyên khi hợp đồng yêu cầu; thử Unicode trong tên file |
| Newline | Script/text có thể dùng LF hoặc CRLF; không giả định hai loại giống byte |
| Symlink/quyền | Hành vi khác theo OS, filesystem và tài khoản runner |
| Native dependency | File `.dll`, `.so`, `.dylib` và kiến trúc CPU không thể dùng thay thế tùy tiện |

## 9. Hai mô hình ma trận cần phân biệt

**Build-many:** mỗi ô JDK/OS tự biên dịch và đóng gói. Kiểm chứng xem quy trình build hoạt động trên từng môi trường, nhưng có thể tạo ra các JAR khác nhau.

**Build-once-test-many:** một job tạo artifact chuẩn, những job khác tải **cùng artifact** xuống để kiểm thử runtime và smoke test. Kiểm chứng một file phát hành thực sự chạy được trên các môi trường đã công bố.

| Câu hỏi | Build-many | Build-once-test-many |
| --- | --- | --- |
| Mã có biên dịch trên Windows/JDK 17 không? | Có thể chứng minh | Không trực tiếp |
| Một JAR duy nhất chạy trên nhiều OS/JDK không? | Chưa chắc, vì mỗi job tự build | Kiểm tra trực tiếp |
| Có so sánh byte giữa các toolchain được không? | Có thể nếu lưu các artifact | Không phải mục tiêu |
| Có giảm thời gian biên dịch lặp lại không? | Thường ít hơn | Thường có |

Hai mô hình có thể kết hợp: kiểm tra build trên các môi trường có cam kết build, đồng thời chạy **artifact được chọn để phát hành** trên các runtime đích.

Một checksum khác nhau giữa các ô không tự động là lỗi: khác JDK, manifest, timestamp hoặc cách nén có thể làm byte khác. Nếu dự án yêu cầu build tái lập, phải kiểm soát đồng thời timestamp trong ZIP/JAR, thứ tự entry, metadata, dependency, phiên bản tool và đầu vào. Nếu yêu cầu chỉ là tương thích chức năng, test và artifact validation là bằng chứng chính.

## 10. Kết quả ma trận và cách tìm nguyên nhân lỗi

Giả sử quan sát:

| Hiện tượng | Khả năng cần kiểm tra |
| --- | --- |
| Chỉ các ô Windows lỗi, mọi JDK/profile | Đường dẫn, lệnh shell, quyền, filesystem |
| Chỉ các ô JDK 21 lỗi trên nhiều OS | Compiler/JVM, dependency hoặc plugin không tương thích |
| Tất cả các ô `prod` lỗi | Resource/config prod, điều kiện target hoặc test profile |
| Chỉ một ô lỗi | Giao điểm cụ thể OS + JDK + profile |
| Nhiều ô lỗi ở bước tải dependency | Repository/network/runner, chưa chắc là lỗi ứng dụng |

Khi điều tra, hãy xem lỗi đầu tiên trong log, xác định target Ant đang chạy, ghi thông tin OS/JDK/Ant/profile và so sánh với job chỉ khác **một trục**. Lỗi hạ tầng khiến job bị hủy hoặc không chạy xong không nên được tính là bằng chứng tương thích.

Một bảng kết quả đạt yêu cầu có thể:

| JDK | Ubuntu dev/prod | Windows dev/prod | macOS dev/prod |
| --- | --- | --- | --- |
| 17 | Đạt / Đạt | Đạt / Đạt | Đạt / Đạt |
| 21 | Đạt / Đạt | Đạt / Đạt | Đạt / Đạt |

Đây là **mẫu báo cáo mong muốn**, không phải kết quả đo từ dự án thật. Với một ô chưa kiểm tra, ghi `Chưa chạy` thay vì suy ra thành công từ ô khác.

## 11. Kỹ thuật giảm chi phí mà không làm sai kết quả

1. **Cache dependency theo khóa đúng:** có thể cache thư viện tải về, nhưng cần phân biệt dependency có bản native/khác JDK/OS. Không tái sử dụng bừa bãi thư mục `build/` vì timestamp có thể làm Ant tưởng output cũ vẫn hợp lệ.
2. **Giới hạn số job đồng thời:** `max-parallel` giúp tránh làm quá tải dịch vụ integration test chung; số tổ hợp không giảm.
3. **Tách các lớp kiểm thử:** unit test có thể chạy trên mọi tổ hợp, integration test mở rộng theo lịch hoặc trước release nếu quy định chất lượng cho phép.
4. **Giữ logic trong Ant:** dùng cùng target `verify` cho mọi runner và chọn profile bằng tham số; giảm nhánh script riêng theo OS.
5. **Lưu report đúng mức:** thay vì upload tất cả artifact lớn, chỉ lưu artifact phát hành đại diện và report/log của các tổ hợp quan trọng hoặc bị lỗi.

Một ma trận chạy nhanh nhưng bỏ qua kiểm thử cần thiết hoặc sử dụng cache output cũ **không chứng minh sản phẩm tương thích**.

## 12. Report JUnit trong dự án thực tế

Ví dụ bài học dùng `AppTest` Java thuần để chạy ngay với Ant và JDK. Dự án thật thường dùng framework kiểm thử. Với task JUnit truyền thống, đoạn sau minh họa cách tạo XML report và dừng khi test lỗi:

```xml
<junit printsummary="yes"
       haltonerror="true"
       haltonfailure="true"
       fork="true">
    <classpath refid="test.classpath"/>
    <formatter type="xml"/>
    <batchtest todir="${build.dir}/test-reports">
        <fileset dir="${tests.dir}">
            <include name="**/*Test.class"/>
        </fileset>
    </batchtest>
</junit>
```

Đoạn cấu hình này **cần tích hợp thêm** classpath, thư mục report, thư viện và task JUnit tương thích. Không dán nguyên vào dự án chưa cấu hình JUnit rồi kỳ vọng chạy được. Với JUnit 5, cần bộ launcher/task tương thích.

Upload report từ từng job GitHub Actions:

```yaml
- name: Upload test reports
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: tests-${{ matrix.os }}-jdk${{ matrix.jdk }}-${{ matrix.profile }}
    path: build/${{ matrix.profile }}/test-reports/
    if-no-files-found: warn
```

Tên artifact chứa đầy đủ trục để không đụng giữa các job. `if: always()` giúp lấy report ngay cả khi bước kiểm thử thất bại, miễn runner vẫn hoạt động và report đã được tạo.

## 13. Những sai lầm hay gặp

**Chỉ đổi JAVA_HOME theo nhãn job.** Đường dẫn thực tế đến `java`/`javac` có thể khác kỳ vọng. Cần kiểm tra version trong từng job.

**Cho rằng `release=17` đồng nghĩa đã test runtime Java 17.** Phải chạy chương trình/test trên JDK 17 thật, không chỉ biên dịch nhắm Java 17 bằng JDK 21.

**Dùng lệnh shell không đa nền tảng.** Script Bash nguyên trạng có thể không chạy trên Windows. Chọn task Ant hoặc shell hỗ trợ nhiều OS.

**Gọi `fail-fast: false` là “cho phép lỗi”.** Tùy chọn này chỉ tránh hủy sớm những job khác; ô lỗi vẫn đỏ.

**Dùng `continue-on-error` cho tổ hợp bắt buộc.** Điều này có thể làm gate thể hiện sai trạng thái cam kết hỗ trợ.

**Bỏ qua artifact.** Test chạy từ thư mục class có thể xanh trong khi JAR thiếu resource/manifest. Cần thêm smoke test từ gói thực tế.

**Gộp cache không phân biệt OS/JDK/profile.** Có thể lấy nhầm class hoặc tài nguyên của tổ hợp khác, sinh kết quả xanh giả.

**Loại tổ hợp lỗi bằng `exclude`.** Chỉ loại khi chính sách hỗ trợ thay đổi có chủ đích; giữ danh sách hỗ trợ và tiêu chí release đồng bộ.

**Coi mọi lỗi runner là lỗi chương trình.** Cần phân biệt test failure, lỗi công cụ, lỗi mạng/dependency và job bị hủy; tất cả đều cần xử lý trước khi tuyên bố tổ hợp đã được xác minh.

## 14. Bài thực hành

1. Tạo các tệp ở mục 4. Chạy `ant -noinput -Dbuild.profile=dev clean verify` và `ant -noinput -Dbuild.profile=prod clean verify`; kiểm tra JAR của mỗi profile.
2. Tạo workflow ở mục 5 trong một repository được phép chạy GitHub Actions; quan sát tên và số lượng job từ ba trục.
3. Tạm sửa `config/prod/app.properties` thành `app.profile=dev` và xác nhận các ô `prod` lỗi ở test. Khôi phục file.
4. Thử `-Dbuild.profile=staging` và quan sát target `validate` từ chối profile chưa hỗ trợ.
5. Thử thay `bytecode.release=17` thành `21` trong một job JDK 17; giải thích lý do mức release không hợp lệ với compiler JDK 17.
6. Tạo ma trận rút gọn bằng `include` và giải thích những tổ hợp còn thiếu trước release. Khôi phục quy trình đầy đủ ở bước kiểm chứng phát hành.
7. Nếu sản phẩm phát hành một JAR duy nhất, bổ sung luồng upload/download artifact để kiểm thử cùng JAR trên JDK 17/21 và các OS đích.

## 15. Ghi nhớ

Với Apache Ant, **ma trận CI/CD là kiểm chứng cam kết tương thích**. Hệ thống CI chọn runner, JDK và cấu hình; `build.xml` cung cấp logic build/test/đóng gói nhất quán. Mỗi tổ hợp cần kiểm tra đúng JDK thực tế, chạy test với mã thoát phản ánh lỗi và xác minh artifact trong môi trường đó.

Một pipeline đạt yêu cầu khi **mọi tổ hợp bắt buộc** được chạy và thành công; test/report/artifact được lưu đủ để truy vết. Nếu bản phát hành là một artifact duy nhất, kiểm tra chính artifact đó trên các runtime cần hỗ trợ thay vì chỉ tin vào các artifact được build riêng ở từng job.

## Tài liệu tham khảo

- [Apache Ant — Running Ant](https://ant.apache.org/manual/running.html): tham số CLI và property.
- [Apache Ant — Buildfile](https://ant.apache.org/manual/using.html): target, dependency, project.
- [Apache Ant — Javac](https://ant.apache.org/manual/Tasks/javac.html): `release`, classpath và compiler.
- [Apache Ant — Java](https://ant.apache.org/manual/Tasks/java.html): `fork`, `failonerror`, `sysproperty`.
- [Apache Ant — Jar](https://ant.apache.org/manual/Tasks/jar.html): đóng gói và manifest.
- [Apache Ant — JUnit](https://ant.apache.org/manual/Tasks/junit.html): kiểm thử và report XML.
- [GitHub Actions — Matrix strategy](https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs): `matrix`, `include`, `exclude` và `fail-fast`.
- [GitHub Actions — Workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax): job, runner, trigger, `needs`, điều kiện.
- [GitHub Actions — Building Java with Ant](https://docs.github.com/en/actions/tutorials/build-and-test-code/java-with-ant): cấu hình CI cho dự án Apache Ant.
