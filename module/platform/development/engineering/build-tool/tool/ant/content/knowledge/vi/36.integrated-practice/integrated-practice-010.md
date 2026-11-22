# Thiết lập CI với kiểm tra chất lượng, artifact và gói phát hành bằng Apache Ant

Một lệnh `ant jar` chạy thành công trên máy lập trình viên chưa đủ để kết luận phần mềm có thể phát hành. Bản dựng trong hệ thống CI (Continuous Integration) cần bắt đầu từ mã nguồn xác định, sử dụng công cụ có phiên bản rõ ràng, **dừng khi kiểm tra chất lượng thất bại**, lưu kết quả có thể kiểm chứng và chỉ phát hành khi đáp ứng điều kiện của quy trình.

Trong bài thực hành này, Apache Ant chịu trách nhiệm biên dịch Java, chạy kiểm thử, đóng gói JAR, tạo ZIP phát hành và tính SHA-256. GitHub Actions đảm nhiệm việc lấy mã nguồn, chuẩn bị JDK/Ant, thực thi các target, lưu artifact của mỗi lượt CI và tạo GitHub Release khi có tag phiên bản hợp lệ.

Nguyên tắc xuyên suốt: **một thay đổi mã nguồn chỉ được phép đi tới bước phát hành sau khi các quality gate đã đạt**. File JAR là sản phẩm biên dịch; ZIP chứa JAR và tài liệu là gói phân phối; báo cáo kiểm thử là bằng chứng của lượt chạy CI. Ba loại dữ liệu này có mục đích và thời hạn lưu trữ khác nhau.

## 1. Mục tiêu và kết quả của bài thực hành

Sau khi hoàn thành, bạn có thể:

1. Tạo dự án Ant nhỏ có target `compile`, `test`, `package`, `release-bundle` và `ci` với quan hệ phụ thuộc rõ ràng.
2. Buộc CI thất bại khi Java biên dịch lỗi, có cảnh báo compiler được cấu hình thành lỗi hoặc kiểm thử trả về mã thoát khác 0.
3. Tạo JAR chạy được và ZIP phát hành chỉ chứa các tệp đã chọn.
4. Tạo tệp SHA-256 để người nhận kiểm tra tính toàn vẹn của ZIP.
5. Viết GitHub Actions workflow chạy trên pull request và nhánh chính, lưu báo cáo cùng gói ứng viên dưới dạng CI artifacts.
6. Chỉ tạo bản phát hành dài hạn trên GitHub Release cho các tag phiên bản được xác thực.
7. Điều tra lỗi CI, đọc artifact và phân biệt kiểm thử thành công với việc xác minh toàn bộ gói phát hành.

Ví dụ sử dụng **JDK 21 để chạy Ant**, biên dịch mã nguồn tương thích **Java 17** bằng thuộc tính `release="17"` và một phiên bản Ant hỗ trợ tùy chọn này. Kiểm thử sử dụng một lớp Java có phương thức `main` để không phải tải thư viện JUnit trong bài mẫu; mục mở rộng sẽ nói về JUnit và phân tích tĩnh trong dự án thật.

## 2. Thiết kế pipeline trước khi viết lệnh

Pipeline thực hành có thứ tự:

```text
      Push / Pull Request / Tag
                  |
                  v
            Checkout source
                  |
                  v
         Thiết lập JDK + Ant
                  |
                  v
             ant ci
                  |
                  v
          clean -> compile
                  |
            Cảnh báo/lỗi?
            /          \
           Có          Không
           |             |
           v             v
       CI FAILED        test
                       /    \
                    Fail    Pass
                     |        |
                     v        v
                 CI FAILED  package JAR
                              |
                              v
                         ZIP + SHA-256
                              |
                              v
                      Verify artifacts
                              |
                              v
                         CI SUCCESS
                              |
                 +------------+-----------+
                 |                        |
                 v                        v
          Upload CI artifact         Tag vX.Y.Z?
                                          |
                                    +-----+-----+
                                    |           |
                                   Không        Có
                                    |           |
                                    v           v
                                 Kết thúc    Publish Release
```

Cần phân biệt:

| Thành phần | Vị trí hoặc kênh | Mục đích |
|---|---|---|
| **Báo cáo** | `build/reports/` và log CI | Điều tra lỗi compiler/test, làm bằng chứng kiểm tra |
| **Artifact ứng dụng** | `build/artifacts/ant-ci-demo.jar` | Chạy ứng dụng đã biên dịch |
| **Gói phát hành** | `build/release/*.zip` | Phân phối JAR kèm tài liệu |
| **Tệp checksum** | `build/release/*.zip.sha256` | Xác minh bytes ZIP không thay đổi |
| **CI artifact** | Kho artifact theo từng workflow run | Tải về và xem kết quả build tạm thời |
| **GitHub Release** | Trang release gắn Git tag | Phát hành chính thức theo quy trình |

Một ZIP vừa được tạo trong Ant chưa tự động trở thành “release chính thức”. Việc phân quyền phát hành và chọn tag được thực hiện ở tầng CI/CD.

## 3. Chuẩn bị dự án Java tối thiểu

Cấu trúc dự án:

```text
ant-ci-demo/
├── .github/
│   └── workflows/
│       └── ant-ci.yml
├── src/
│   ├── main/java/demo/Calculator.java
│   └── test/java/demo/CalculatorTest.java
├── README.md
├── build.xml
└── build/                      # được Ant tạo, không commit
    ├── classes/main/
    ├── classes/test/
    ├── reports/
    ├── artifacts/
    └── release/
```

Tạo `README.md` với nội dung công khai:

```markdown
# Ant CI Demo

Build: ant -noinput -f build.xml ci
Run: java -jar build/artifacts/ant-ci-demo.jar
Release bundle: build/release/
```

Tạo `src/main/java/demo/Calculator.java`:

```java
package demo;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int left, int right) {
        return left + right;
    }

    public static void main(String[] args) {
        System.out.println("2 + 3 = " + add(2, 3));
    }
}
```

Tạo `src/test/java/demo/CalculatorTest.java`:

```java
package demo;

public final class CalculatorTest {
    private CalculatorTest() {
    }

    public static void main(String[] args) {
        require(Calculator.add(2, 3) == 5, "2 + 3 must be 5");
        require(Calculator.add(-2, 3) == 1, "-2 + 3 must be 1");
        require(Calculator.add(0, 0) == 0, "0 + 0 must be 0");
        System.out.println("PASS: CalculatorTest");
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Khi điều kiện trong `require` sai, `AssertionError` không bị bắt và tiến trình Java kết thúc với mã khác 0. Vì vậy CI có thể phân biệt test pass với test fail. Trong ví dụ không dùng trực tiếp lệnh `assert` của Java: lệnh này có thể bị vô hiệu hóa nếu JVM không bật `-ea`.

## 4. Tạo buildfile cho cả local và CI

Tạo tệp `build.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-ci-demo" default="ci" basedir=".">
    <property name="release.version" value="0.1.0-dev"/>

    <property name="src.main" location="src/main/java"/>
    <property name="src.test" location="src/test/java"/>
    <property name="build.dir" location="build"/>
    <property name="classes.main" location="build/classes/main"/>
    <property name="classes.test" location="build/classes/test"/>
    <property name="reports.dir" location="build/reports"/>
    <property name="artifacts.dir" location="build/artifacts"/>
    <property name="release.dir" location="build/release"/>

    <property name="app.jar"
              location="${artifacts.dir}/ant-ci-demo.jar"/>
    <property name="release.base"
              value="ant-ci-demo-${release.version}"/>
    <property name="release.zip"
              location="${release.dir}/${release.base}.zip"/>

    <target name="clean">
        <delete dir="${build.dir}"/>
    </target>

    <target name="init">
        <mkdir dir="${classes.main}"/>
        <mkdir dir="${classes.test}"/>
        <mkdir dir="${reports.dir}"/>
        <mkdir dir="${artifacts.dir}"/>
        <mkdir dir="${release.dir}"/>
    </target>

    <target name="compile" depends="init">
        <javac srcdir="${src.main}"
               destdir="${classes.main}"
               release="17"
               encoding="UTF-8"
               includeantruntime="false">
            <compilerarg value="-Xlint:all"/>
            <compilerarg value="-Werror"/>
        </javac>
    </target>

    <target name="test" depends="compile">
        <javac srcdir="${src.test}"
               destdir="${classes.test}"
               release="17"
               encoding="UTF-8"
               includeantruntime="false">
            <classpath>
                <pathelement location="${classes.main}"/>
            </classpath>
        </javac>

        <java classname="demo.CalculatorTest"
              fork="true"
              failonerror="true"
              output="${reports.dir}/test-output.txt"
              error="${reports.dir}/test-error.txt">
            <classpath>
                <pathelement location="${classes.main}"/>
                <pathelement location="${classes.test}"/>
            </classpath>
        </java>
    </target>

    <target name="package" depends="test">
        <jar destfile="${app.jar}" basedir="${classes.main}">
            <manifest>
                <attribute name="Main-Class" value="demo.Calculator"/>
            </manifest>
        </jar>
    </target>

    <target name="release-bundle" depends="package">
        <zip destfile="${release.zip}" duplicate="fail">
            <zipfileset file="${app.jar}"
                        fullpath="${release.base}/app.jar"/>
            <zipfileset file="README.md"
                        fullpath="${release.base}/README.md"/>
        </zip>

        <checksum file="${release.zip}"
                  algorithm="SHA-256"
                  property="release.sha256"/>
        <echo file="${release.zip}.sha256"
              encoding="UTF-8"
              message="${release.sha256}  ${release.base}.zip"/>
    </target>

    <target name="verify-artifacts" depends="release-bundle">
        <condition property="release.complete">
            <and>
                <available file="${app.jar}" type="file"/>
                <available file="${release.zip}" type="file"/>
                <available file="${release.zip}.sha256" type="file"/>
            </and>
        </condition>
        <fail unless="release.complete"
              message="Missing JAR, ZIP or SHA-256 checksum"/>
    </target>

    <target name="ci" depends="clean,verify-artifacts">
        <echo message="CI passed; release bundle ready"/>
    </target>
</project>
```

### 4.1. Target phụ thuộc tạo thành quality gate

Ant thực hiện các dependency theo thứ tự cần thiết:

```text
ci
├── clean
└── verify-artifacts
    └── release-bundle
        └── package
            └── test
                └── compile
                    └── init
```

Vì `release-bundle` phụ thuộc vào `package`, `package` phụ thuộc `test` và `test` phụ thuộc `compile`, một lỗi ở bất kỳ gate trước nào sẽ khiến Ant dừng. Trong một lượt `ant ci`, `clean` chạy trước phần tạo artifact để loại bỏ sản phẩm của lần build cũ.

**Không dùng lại mô hình `clean` tự động cho mọi task khi dự án cần incremental build.** Ở ví dụ này, `ci` là lối vào cố ý chạy sạch; target `compile` hoặc `test` vẫn có thể được gọi riêng để làm việc cục bộ.

### 4.2. Giải thích các tùy chọn compiler và kiểm thử

- `includeantruntime="false"` tránh thêm Ant runtime vào classpath biên dịch, giảm phụ thuộc ngầm vào thư viện của Ant.
- `release="17"` yêu cầu compiler dùng API và định dạng class file tương thích Java 17 khi chạy trên JDK có hỗ trợ `--release`.
- `-Xlint:all` bật các cảnh báo compiler thuộc nhóm được hỗ trợ; `-Werror` khiến compiler thất bại nếu có cảnh báo.
- `fork="true"` trong `<java>` chạy test ở JVM riêng; `failonerror="true"` biến mã thoát khác 0 thành lỗi Ant.
- `output` và `error` ghi hai luồng của kiểm thử vào tệp báo cáo, tiện cho CI thu thập ngay cả khi test lỗi.

Việc biên dịch bằng JDK 21 với `release="17"` không thay cho việc **chạy kiểm thử trên JDK 17** nếu sản phẩm thật yêu cầu hỗ trợ runtime đó. Có thể bổ sung matrix JDK sau.

### 4.3. Chạy trên máy cá nhân

Tại thư mục gốc dự án, khi Ant và JDK đã có trong môi trường:

```bash
ant -version
java -version
ant -noinput -f build.xml ci
```

`-noinput` phù hợp cho CI vì một build không nên dừng để chờ người dùng nhập liệu. Sau khi chạy thành công, kỳ vọng:

```text
build/
├── classes/
│   ├── main/demo/Calculator.class
│   └── test/demo/CalculatorTest.class
├── reports/
│   ├── test-output.txt
│   └── test-error.txt
├── artifacts/
│   └── ant-ci-demo.jar
└── release/
    ├── ant-ci-demo-0.1.0-dev.zip
    └── ant-ci-demo-0.1.0-dev.zip.sha256
```

Chạy ứng dụng:

```bash
java -jar build/artifacts/ant-ci-demo.jar
```

Kết quả dự kiến:

```text
2 + 3 = 5
```

## 5. Thử tình huống kiểm tra chất lượng thất bại

Đổi tạm dòng đầu của `CalculatorTest` thành:

```java
require(Calculator.add(2, 3) == 6, "2 + 3 must be 6");
```

Chạy lại `ant -noinput -f build.xml ci`. Kiểm thử ném `AssertionError`; `<java failonerror="true">` làm Ant trả `BUILD FAILED`. Do `clean` đã chạy, không có ZIP mới của lượt build thất bại. Khôi phục điều kiện đúng và chạy lại để xác nhận gate hoạt động.

| Gate | Lỗi bị chặn | Bằng chứng |
|---|---|---|
| Compile + compiler warnings | Java source sai hoặc cảnh báo theo cấu hình `-Werror` | Log `<javac>` |
| Test | Điều kiện kiểm thử sai hoặc tiến trình JVM lỗi | `test-output.txt`, `test-error.txt`, mã thoát |
| Verify artifacts | Thiếu JAR, ZIP hoặc SHA-256 | `<available>` và `<fail>` |

Ví dụ dùng test dạng `main` để dạy nguyên tắc mã thoát; dự án thật nên dùng framework kiểm thử và report định dạng tiêu chuẩn. Việc artifact có tồn tại cũng mới là kiểm tra cơ bản, chưa chứng minh nội dung đã qua quét bảo mật hoặc tất cả test đã có coverage phù hợp.

## 6. Đóng gói JAR, ZIP và SHA-256

Target `package` tạo `build/artifacts/ant-ci-demo.jar` từ các class đã biên dịch và thêm `Main-Class` vào manifest. Target `release-bundle` tạo ZIP chỉ chứa hai mục:

```text
ant-ci-demo-0.1.0-dev/
├── app.jar
└── README.md
```

Task `<zipfileset file="..." fullpath="...">` giúp chọn tường minh các file được phép phát hành, thay vì nén cả repository có thể chứa `.git`, báo cáo, dữ liệu kiểm thử, credential hoặc sản phẩm cũ.

Version nằm trong property `release.version`; mặc định là `0.1.0-dev`. Để tạo gói ứng viên cho phiên bản `1.2.3` ở local:

```bash
ant -noinput -f build.xml -Drelease.version=1.2.3 ci
```

Lệnh chỉ tạo ZIP và checksum trong thư mục build; không tự upload lên dịch vụ phát hành.

### 6.1. Tại sao cần SHA-256?

Hai task:

```xml
<checksum file="${release.zip}"
          algorithm="SHA-256"
          property="release.sha256"/>
<echo file="${release.zip}.sha256"
      encoding="UTF-8"
      message="${release.sha256}  ${release.base}.zip"/>
```

tạo một file `.zip.sha256` chứa chuỗi hash rồi hai dấu cách và tên ZIP, theo định dạng để `sha256sum -c` đọc. Ví dụ minh họa:

```text
<64 chữ số hexadecimal SHA-256>  ant-ci-demo-1.2.3.zip
```

Hash thật được tính từ bytes của ZIP; dòng trên là biểu diễn cấu trúc, không phải hash hợp lệ để đem kiểm tra.

Trên Linux, khi ở thư mục dự án, có thể chạy:

```bash
jar tf build/artifacts/ant-ci-demo.jar
unzip -l build/release/ant-ci-demo-0.1.0-dev.zip

cd build/release
sha256sum -c ant-ci-demo-0.1.0-dev.zip.sha256
```

Trên macOS thường có `shasum -a 256`, trong khi `sha256sum` có thể cần cài thêm. Trên Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "build/release/ant-ci-demo-0.1.0-dev.zip"
Get-Content "build/release/ant-ci-demo-0.1.0-dev.zip.sha256"
```

Đối chiếu hai giá trị hexadecimal, không phân biệt chữ hoa/chữ thường. SHA-256 phát hiện nội dung bị thay đổi so với checksum được công bố, nhưng không tự xác thực danh tính người phát hành. Nếu cả ZIP và file hash đều bị thay, hai file có thể vẫn khớp. Khi cần bảo đảm nguồn gốc, áp dụng thêm chữ ký số, quyền phát hành hoặc thông tin provenance.

JAR/ZIP cũng có thể chứa timestamp và metadata khác nhau giữa những lần build. Muốn **reproducible build** ở mức byte, phải chuẩn hóa metadata và toolchain, không chỉ đặt tên file theo phiên bản.

## 7. Tích hợp CI bằng GitHub Actions

GitHub Actions được dùng để minh họa một nền tảng CI thực tế; các khái niệm cũng áp dụng cho Jenkins hoặc GitLab CI. Tạo `.github/workflows/ant-ci.yml`:

```yaml
name: Ant CI

on:
  push:
    branches: [main]
    tags: ['v*']
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-24.04
    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Install Apache Ant
        run: |
          sudo apt-get update
          sudo apt-get install -y ant

      - name: Record tool versions
        run: |
          ant -version
          java -version

      - name: Compile, test and package
        shell: bash
        run: |
          if [[ "${GITHUB_REF_TYPE}" == "tag" ]]; then
            version="${GITHUB_REF_NAME#v}"
            if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$ ]]; then
              echo "Invalid release tag version" >&2
              exit 1
            fi
            ant -noinput -f build.xml "-Drelease.version=$version" ci
          else
            ant -noinput -f build.xml ci
          fi

      - name: Preserve test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: ant-reports-${{ github.run_id }}
          path: build/reports/
          if-no-files-found: warn
          retention-days: 14

      - name: Upload candidate release bundle
        uses: actions/upload-artifact@v4
        with:
          name: ant-release-${{ github.run_id }}
          path: build/release/
          if-no-files-found: error
          retention-days: 14

  publish:
    needs: verify
    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-24.04
    permissions:
      contents: write
    steps:
      - name: Download verified bundle
        uses: actions/download-artifact@v4
        with:
          name: ant-release-${{ github.run_id }}
          path: release

      - name: Verify checksum before publish
        shell: bash
        working-directory: release
        run: |
          shopt -s nullglob
          sums=( *.zip.sha256 )
          if (( ${#sums[@]} != 1 )); then
            echo "Expected exactly one checksum file" >&2
            exit 1
          fi
          sha256sum -c "${sums[0]}"

      - name: Create GitHub Release
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh release create "$GITHUB_REF_NAME" \
            release/*.zip release/*.sha256 \
            --verify-tag \
            --title "$GITHUB_REF_NAME" \
            --generate-notes
```

Workflow sử dụng Ubuntu runner, cài Ant từ package repository có sẵn. Cách này thuận tiện cho bài tập nhưng phiên bản Ant nhận được có thể thay đổi khi runner image hoặc package repository cập nhật. Khi yêu cầu tái hiện tuyệt đối, cần cố định phiên bản JDK/Ant và xác minh nguồn cài đặt. Tương tự, trong production nên ghim GitHub Actions theo commit SHA đã đánh giá theo chính sách của tổ chức, thay vì chỉ dựa vào tag major như `@v4`.

### 7.1. Phân biệt hành vi trên PR, branch và tag

| Sự kiện | Job `verify` | Job `publish` | Kết quả |
|---|---|---|---|
| Pull request | Chạy | Không chạy | Gate chất lượng và CI artifact |
| Push lên `main` | Chạy | Không chạy | Gate chất lượng và CI artifact |
| Push tag `v1.2.3` | Chạy | Chỉ khi verify thành công | GitHub Release với ZIP + checksum |
| Test hoặc compile lỗi | Thất bại | Không chạy | Báo cáo được lưu nếu đã có |
| Tag không khớp dạng phiên bản | Thất bại ở lệnh kiểm tra | Không chạy | Không phát hành |

Biểu thức kiểm tra tag minh họa dạng `vX.Y.Z` với hậu tố tùy chọn, chưa bao quát mọi nhánh ngữ pháp Semantic Versioning. Cần điều chỉnh khi dự án dùng quy ước đặt tag khác.

### 7.2. Vì sao `publish` phải phụ thuộc `verify`?

`needs: verify` khiến việc công bố bản phát hành phải chờ job kiểm tra đạt. Job `publish` tải artifact được tạo bởi **cùng workflow run** thay vì build lại lần thứ hai, tránh việc test một bản còn phát hành một bản khác khi môi trường hoặc dependency thay đổi.

Quyền `contents: write` được cấp riêng cho `publish`; các job kiểm thử bình thường chỉ cần `contents: read`. Cần kết hợp bảo vệ tag, điều kiện release và quyền phê duyệt của repository. Không nên cấp secret hoặc quyền phát hành cho các bước chạy mã pull request không tin cậy.

### 7.3. Vì sao upload báo cáo khi build lỗi?

`if: always()` yêu cầu job vẫn thử lưu `build/reports` dù build thất bại ở một bước trước. Điều này hữu ích khi `test-error.txt` có stack trace giải thích nguyên nhân. `if-no-files-found: warn` tránh tạo một lỗi phụ nếu Ant dừng trước khi tạo thư mục reports.

Bước upload report thành công **không chuyển trạng thái verify từ thất bại thành thành công**. Upload ZIP ứng viên không có `always()`, vì không được phát hành output từ một build thất bại.

### 7.4. Vì sao kiểm tra hash trong job publish?

Artifact phải di chuyển từ `verify` đến `publish` qua kho CI. Job publish tính lại hash của file ZIP sau khi tải xuống và đối chiếu với `.sha256`. Nếu không khớp, lệnh `gh release create` không được chạy. Đây là một lớp kiểm tra tính toàn vẹn giữa các job.

Nội dung hash đúng không chứng minh source code, dependency hay GitHub Action đã được kiểm chứng. Với chuỗi cung ứng phần mềm quan trọng, cần thêm cơ chế xác minh provenance/chữ ký và quyền upload artifact.

### 7.5. CI artifact khác Release chính thức

`actions/upload-artifact@v4` lưu file theo workflow run, trong ví dụ đề xuất giữ 14 ngày, tùy giới hạn repository/tổ chức. GitHub Release gắn với tag và phục vụ phân phối lâu dài hơn.

Lệnh `gh release create` có thể thất bại nếu release của tag đã tồn tại. Ví dụ cố tình không tự động ghi đè bản đã công bố khi workflow được chạy lại. Với production, quy trình retry hoặc sửa metadata cần được xác định rõ để một version không vô tình trỏ tới nhiều gói khác nhau.

## 8. Thu thập bằng chứng khi CI lỗi

Khi pipeline thất bại, nên đọc theo thứ tự:

1. **Sự kiện:** PR, push nhánh hay push tag?
2. **Toolchain:** `ant -version`, `java -version` và runner image có đúng không?
3. **Ant target đầu tiên lỗi:** `compile`, `test`, `package`, `release-bundle` hay `verify-artifacts`?
4. **Dữ liệu chẩn đoán:** log compiler, `test-error.txt`, stack trace và mã thoát.
5. **Đầu ra:** JAR, ZIP, checksum có được tạo không; kết quả có đúng từ source vừa checkout không?
6. **Quyền:** nếu chỉ lỗi ở release, điều kiện job, quyền token và GitHub CLI có sẵn không?

Lệnh debug khi chạy tại máy cá nhân:

```bash
ant -noinput -verbose -f build.xml ci
ant -noinput -debug -f build.xml ci
```

`-debug` có thể ghi nhiều dữ liệu nhạy cảm do task hoặc môi trường cung cấp. Không đưa token, mật khẩu hay private key vào Ant property `-D...`; rà soát log trước khi chia sẻ. Dòng `BUILD FAILED` cuối log thường chỉ là kết quả; cần tìm lỗi đầu tiên có ý nghĩa ngay trước đó.

## 9. Mở rộng quality gate bằng JUnit và công cụ chuyên dụng

Bài mẫu sử dụng test `main` để làm rõ mã thoát, nhưng dự án thật thường cần các cổng sau:

| Kiểm tra | Ví dụ công cụ | Đầu ra nên lưu |
|---|---|---|
| Unit test | JUnit 4/5 với tích hợp Ant phù hợp | XML test report, số test lỗi |
| Static analysis | Checkstyle, SpotBugs | Vi phạm theo ruleset, trạng thái gate |
| Coverage | JaCoCo | Coverage report và ngưỡng tối thiểu |
| Dependency security | Công cụ quét dependency được phê duyệt | Phiên bản thư viện, vấn đề theo chính sách |
| Artifact scanning | Công cụ quét secret, license và file phân phối | Báo cáo vị trí vi phạm, không in giá trị secret |
| Integration test | JUnit hoặc chương trình kiểm thử kết nối service | Báo cáo, timeout, cleanup |

Khung minh họa cho `<junit>` của Ant khi sử dụng JUnit 4:

```xml
<target name="unit-test-junit" depends="compile">
    <mkdir dir="${reports.dir}"/>
    <junit fork="true"
           haltonfailure="true"
           haltonerror="true"
           printsummary="yes">
        <classpath>
            <pathelement location="${classes.main}"/>
            <pathelement location="${classes.test}"/>
            <fileset dir="lib/test" includes="**/*.jar"/>
        </classpath>
        <formatter type="xml"/>
        <batchtest todir="${reports.dir}">
            <fileset dir="${classes.test}">
                <include name="**/*Test.class"/>
            </fileset>
        </batchtest>
    </junit>
</target>
```

Đoạn trên là **khung tham khảo**, chưa phải giải pháp chạy trực tiếp trong bài mẫu. Ant JUnit là optional task; cần thư viện JUnit, phần tích hợp Ant phù hợp, thư mục dependency và bước biên dịch test trước khi sử dụng. Với JUnit 5, Ant có `junitlauncher` với classpath/phụ thuộc riêng.

Nếu dùng Checkstyle hoặc SpotBugs, hãy xác định rõ ruleset, version, mã thoát và cách báo cáo. Một dòng `<echo message="Quality passed"/>` không phải quality gate nếu công cụ kiểm tra chưa thực sự chạy.

## 10. Kiểm soát secret và quyền phát hành

Quy trình CI đôi khi cần token upload artifact, khóa ký hoặc mật khẩu repository. Không nên đặt các giá trị đó trực tiếp vào `build.xml`, Java source, tệp phát hành, biến `-D...` của Ant hoặc dòng lệnh hiển thị trong log.

Trong mẫu, job `verify` không cần secret phát hành. Job `publish` dùng token tự động của GitHub qua biến môi trường `GH_TOKEN` và chỉ có quyền `contents: write` trong phạm vi job. Không in token trong `<echo>`, `<echoproperties>`, shell tracing hay log của chương trình ngoài.

Nếu publish tới dịch vụ khác, chỉ cấp credential ở bước thực sự cần quyền upload, bằng secret manager của CI. Công cụ upload nên đọc token từ môi trường đã được cấp hoặc credential store, thay vì nhận giá trị qua đối số `--token ...`. Môi trường và file chứa credential cũng cần giới hạn quyền đọc; bản thân chúng không phải nơi lưu trữ an toàn nếu runner bị chiếm quyền.

Những ranh giới cần bảo vệ:

| Ranh giới | Nội dung cần tránh |
|---|---|
| Source/Git | Token trong `build.xml`, script, properties, source code |
| Compile/package | Resource bị nội suy password, private key trong JAR, tệp secret lọt vào ZIP |
| Test report | Exception in URL có thông tin đăng nhập, dump environment, HTTP headers nhạy cảm |
| CI artifact | Log debug, file cấu hình/secret được upload tự động |
| Release | Gói chưa qua gate, file ZIP từ commit khác, hash không khớp hoặc tag chưa được kiểm soát |

Một số nền tảng CI có tính năng che secret, nhưng không bảo đảm chặn được mọi biến thể đã encode, chia nhỏ hoặc ghi vào file. Cách bảo vệ hiệu quả nhất là tránh đưa giá trị mật vào những output này ngay từ đầu.

## 11. Cố định môi trường và quản lý cache

### 11.1. Phiên bản toolchain

Ví dụ workflow ghi phiên bản `ant -version` và `java -version`. Trên runner có thể có sẵn nhiều Java; cần xác nhận JVM Ant sử dụng và compiler phục vụ `<javac>` là bản được mong muốn. `actions/setup-java` được cấu hình JDK 21, còn `release="17"` điều khiển mục tiêu biên dịch Java của ứng dụng.

`apt-get install ant` sử dụng gói có sẵn từ repository của runner tại thời điểm thực thi. Với dự án yêu cầu tái hiện chặt chẽ, nên dùng image hoặc quy trình cài Ant từ phiên bản cố định, kiểm tra checksum/chữ ký của distribution và cập nhật theo quy trình đã xác định.

Ngoài toolchain, còn cần ghi lại các yếu tố ảnh hưởng tới output: hệ điều hành, encoding, dependency, locale/timezone khi có dùng timestamp, và cách Ant sinh file hoặc tạo archive.

### 11.2. Không cache tùy tiện đầu ra build

Cache có thể giúp tăng tốc CI nhưng cũng dễ che lỗi khi đầu vào thay đổi mà task không phát hiện. Dự án mẫu không dùng dependency ngoài và chạy `clean` đầu pipeline, vì vậy không cần cache.

Với Ant + Ivy hoặc custom dependency downloader, có thể cache **thư viện đã tải** dựa trên metadata, checksum hoặc lockfile. Không coi thư mục `build/release`, JAR cũ hoặc tệp generated resource từ lần CI trước là nguồn tin cậy của lần chạy mới nếu chưa có cơ chế xác định input và kiểm tra tính đúng đắn.

### 11.3. Mối quan hệ giữa tính lặp lại và checksum

Một file ZIP có SHA-256 khác không nhất thiết nghĩa mã Java thay đổi. Timestamp, thứ tự entry ZIP, file attributes hoặc phiên bản JDK/Ant có thể làm bytes khác nhau.

Nếu sản phẩm yêu cầu reproducible build, phải chuẩn hóa những yếu tố này và so sánh gói từ hai lượt build độc lập. Bài mẫu chỉ dùng checksum để kiểm tra **tính toàn vẹn của một gói đã tạo**, không khẳng định reproducibility giữa mọi lần chạy.

## 12. Những trường hợp lỗi CI thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| `ant: command not found` | Runner chưa cài Ant hoặc `PATH` chưa đúng | Kiểm tra bước cài đặt và `ant -version` |
| `javac` không có hoặc compiler option sai | JDK thiếu, khác version hoặc Ant dùng compiler khác | Xem `java -version`, JDK của Ant, cấu hình `<javac>` |
| Compiler fail chỉ trên CI | Encoding, filesystem case sensitivity, dependency hoặc JDK khác | Đọc lỗi Java đầu tiên, so sánh môi trường |
| Test thất bại nhưng job vẫn thành công | Không xử lý mã thoát hoặc nuốt exception | Bật `fork` và `failonerror`, kiểm tra test process |
| Report không xuất hiện | Fail trước khi target test tạo report | Xem log compiler/Ant; `if-no-files-found: warn` |
| JAR có nhưng ZIP không có | Task ZIP sai source path hoặc chưa chạy đến target release | Kiểm tra dependency và tệp thực tế |
| ZIP chứa file không được phép | `fileset` quá rộng hoặc resource có secret | Kiểm tra allowlist và nội dung ZIP |
| SHA-256 không khớp | ZIP thay đổi, tệp hash ghi tên file sai | Kiểm tra cả bytes, tên file, vị trí khi chạy hash |
| Upload CI artifact bị bỏ qua | Build fail trước bước upload thông thường | Đọc trạng thái step; chỉ report nên luôn cố lưu |
| Release không được tạo khi push tag | Gate fail hoặc điều kiện `if` không khớp | Kiểm tra Git ref, job `needs` và version tag |
| `gh: command not found` | Runner không có GitHub CLI | Cài `gh` đúng cách hoặc dùng action phát hành đã kiểm chứng |
| GitHub Release trả 403 | Thiếu quyền `contents: write` hoặc policy repo hạn chế | Xem permissions, branch/tag protection, token |
| Release đã tồn tại | Workflow rerun cho cùng tag | Dùng quy trình retry rõ ràng; không tự ghi đè |
| Mỗi runner tạo ZIP khác hash | Metadata, timestamp hoặc toolchain khác nhau | Xây dựng chính sách reproducible build |

Không nên bỏ qua một test fail chỉ để artifact vẫn được upload. Nếu cần lấy bằng chứng của lần chạy lỗi, hãy lưu **log/báo cáo** theo cơ chế chạy khi thất bại; không xuất bản gói chưa qua quality gate.

## 13. Mở rộng CI đa nền tảng hoặc nhiều JDK

Dự án Java có thể cần kiểm tra trên các JVM hoặc hệ điều hành khác nhau. Ví dụ:

```text
                         Source commit
                              |
          +-------------------+------------------+
          |                   |                  |
          v                   v                  v
    Test JDK 17          Test JDK 21       Test Windows
          |                   |                  |
          +-------------------+------------------+
                              |
                     Mọi gate đều đạt?
                              |
                         +----+----+
                         |         |
                        Không      Có
                         |         |
                         v         v
                      Dừng CI   Package candidate
                                      |
                                      v
                                Tag được phép?
                                      |
                                      v
                                  Publish
```

Nếu sử dụng GitHub Actions matrix, mỗi job cần có output và report riêng để tránh trùng tên khi upload. Bước publish phải chờ **tất cả gate bắt buộc** và tải một candidate artifact được chỉ định rõ, không chọn ngẫu nhiên một file ZIP từ các job của matrix.

Một JAR chỉ chứa bytecode Java có thể dùng được nhiều nền tảng, nhưng điều này còn phụ thuộc thư viện native, resource, encoding và API hệ điều hành mà chương trình thực sự dùng. Bản dựng thành công trên Linux không thay thế kiểm thử trên Windows nếu sản phẩm cam kết hỗ trợ Windows.

## 14. Bài thực hành kiểm chứng từng bước

Thực hiện lần lượt theo cùng cấu trúc dự án:

**Bài A — Bản dựng thành công.** Tạo các tệp ở mục 3 và 4, chạy `ant -noinput -f build.xml ci`. Xem `test-output.txt`, chạy JAR và liệt kê nội dung ZIP. Kiểm tra hash theo hướng dẫn ở mục 6.

**Bài B — Kiểm thử lỗi.** Đổi kỳ vọng của phép cộng `2 + 3` thành `6`. Chạy lại CI và quan sát Ant dừng ở `test`. Vì target `ci` chạy `clean`, file ZIP của lần trước không còn trong build directory. Sửa test rồi xác nhận pipeline thành công.

**Bài C — Lỗi biên dịch.** Thêm lỗi cú pháp vào `Calculator.java`. Kiểm tra `<javac>` trả lỗi và không chạy target `package` hay `release-bundle`.

**Bài D — Phiên bản phát hành.** Chạy:

```bash
ant -noinput -f build.xml -Drelease.version=1.2.3 ci
```

Kiểm tra ZIP mang tên `ant-ci-demo-1.2.3.zip`, có `app.jar` và `README.md`, đồng thời file `.zip.sha256` tham chiếu đúng tên ZIP.

**Bài E — Workflow PR và branch.** Đưa source lên repository thử nghiệm và mở pull request. Theo dõi job verify, tải CI artifact và xem log. Khi push thay đổi lên `main`, job verify tiếp tục chạy nhưng job publish không thực hiện.

**Bài F — Phát hành theo tag.** Chỉ sau khi đã có quyền với repository thử nghiệm và quy tắc tag được xác nhận, tạo tag phù hợp như `v1.2.3`. Xác nhận verify thành công, publish tải đúng bundle từ job verify, kiểm tra SHA-256 và tạo GitHub Release. Kiểm tra danh sách file trên trang release.

**Bài G — Chứng minh không publish khi test fail.** Trên repository thử nghiệm, đưa vào một thay đổi khiến test fail rồi quan sát trạng thái workflow. Dù nhận tag hợp lệ, `needs: verify` phải ngăn job publish chạy. Không cần dùng token thật hoặc repository sản xuất để thực hiện bài học.

### Tiêu chí hoàn thành bài

| Câu hỏi kiểm chứng | Kết quả mong đợi |
|---|---|
| CI có chạy từ nguồn sạch? | Có target `clean` trước phần build |
| Compile/test lỗi có làm CI fail? | Có, Ant trả trạng thái lỗi |
| Artifact có tạo đúng vị trí? | JAR, ZIP, checksum theo đường dẫn đã định |
| ZIP chỉ chứa mục được phép? | Có, dựa trên `zipfileset` được khai báo |
| SHA-256 có kiểm tra được ở phía nhận? | Có, hash khớp bytes ZIP |
| PR có thể phát hành? | Không, workflow chỉ cho publish khi push tag phù hợp |
| Job publish có dùng bản đã test? | Có, tải artifact từ cùng workflow run |
| Lỗi test có bằng chứng? | Log CI và report được lưu khi đã tạo |

## 15. Tài liệu tham khảo

- [Apache Ant Manual — Running Ant](https://ant.apache.org/manual/running.html): các tùy chọn dòng lệnh và `-noinput`.
- [Apache Ant Manual — Targets](https://ant.apache.org/manual/targets.html): dependency và cách thực thi target.
- [Apache Ant Manual — Javac](https://ant.apache.org/manual/Tasks/javac.html): cấu hình compiler và `release`.
- [Apache Ant Manual — Java](https://ant.apache.org/manual/Tasks/java.html): `fork`, `failonerror` và ghi output.
- [Apache Ant Manual — Jar](https://ant.apache.org/manual/Tasks/jar.html): tạo JAR và manifest.
- [Apache Ant Manual — Zip](https://ant.apache.org/manual/Tasks/zip.html): đóng ZIP theo tập file.
- [Apache Ant Manual — Checksum](https://ant.apache.org/manual/Tasks/checksum.html): tính và đối chiếu checksum.
- [GitHub Actions documentation](https://docs.github.com/en/actions): workflow, job dependencies, artifact và permission.
- [GitHub CLI — gh release create](https://cli.github.com/manual/gh_release_create): tạo release từ tag.

Một pipeline Ant đáng tin cậy phải liên kết rõ ba điều kiện: **quality gate phải dừng bản dựng khi có lỗi; CI phải giữ đủ dữ liệu để truy vết; gói phát hành phải chính là output đã được kiểm tra**. Từ nền tảng đó, dự án có thể thêm JUnit, phân tích tĩnh, matrix đa nền tảng và bước phê duyệt mà vẫn duy trì quan hệ trách nhiệm rõ ràng giữa build, artifact và release.




