# Kiểm thử hồi quy build bằng clean build, ca lỗi và kiểm tra sản phẩm trong Apache Ant

Trong quá trình **bảo trì** một dự án dùng **Apache Ant**, một thay đổi nhỏ ở `build.xml`, thư viện build, đường dẫn resource hoặc cách đóng gói có thể làm hỏng hành vi đã hoạt động trước đó. Build vẫn có thể in `BUILD SUCCESSFUL` nhưng JAR thiếu class, thiếu cấu hình, mang manifest sai, không chạy được, hoặc chứa file cũ từ lần biên dịch trước.

**Kiểm thử hồi quy build (build regression testing)** là việc chạy lại những tình huống đại diện để xác nhận các **hợp đồng của quá trình build** vẫn được giữ sau khi chỉnh sửa. Bài học này tập trung vào ba nhóm phép thử bổ sung cho nhau:

1. **Clean build:** xây dựng từ trạng thái không có đầu ra cũ, bảo đảm mọi đầu vào cần thiết được khai báo và quy trình tự tạo đủ sản phẩm.
2. **Ca lỗi (negative/failure cases):** cố ý đưa điều kiện không hợp lệ vào một môi trường thử nghiệm, chứng minh build **phải thất bại rõ ràng** và không phát hành kết quả không đạt.
3. **Kiểm tra sản phẩm (artifact verification):** kiểm tra chính JAR/ZIP hoặc gói phân phối được tạo: sự tồn tại, cấu trúc, metadata, khả năng chạy và các điều kiện của bản phát hành.

Ba phép thử giải quyết ba câu hỏi khác nhau: **có xây lại được không, có từ chối điều kiện sai không, và sản phẩm được tạo có đúng hợp đồng không?**

## 1. Vì sao “Ant trả exit code 0” chưa đủ?

Xét một dự án Java trước đây có các file:

```text
src/demo/App.java
src/demo/Unused.java
resources/application.properties
build.xml
```

Nhà phát triển xóa `Unused.java`, sửa `build.xml` và chạy một target đóng JAR trên thư mục `build/classes` đã tồn tại. Nếu classfile `Unused.class` từ lần build cũ vẫn còn trong thư mục đầu ra, artifact mới có thể chứa class không còn thuộc mã nguồn.

Một ví dụ khác: task `<copy>` dùng cấu hình sai nên bỏ qua `resources/application.properties`; task `<jar>` vẫn chạy thành công; khi triển khai, ứng dụng mới phát hiện thiếu cấu hình. Vì vậy, **thành công của lệnh build là một tín hiệu cần nhưng chưa đủ**.

| Tình huống | Có thể vẫn thấy `BUILD SUCCESSFUL`? | Phép thử phát hiện |
| --- | --- | --- |
| Class cũ còn trong thư mục output | Có | Clean build + đối chiếu entry JAR |
| Resource bị quên đóng gói | Có | Kiểm tra entry/resource bắt buộc |
| `Main-Class` trong manifest trỏ đến class sai | Có, nếu chỉ chạy `jar` | Chạy thử JAR đã đóng gói |
| Phiên bản hoặc metadata phát hành sai | Có | Đọc/kiểm tra manifest và metadata |
| Công cụ ngoài trả exit code khác 0 nhưng Ant bỏ qua | Có khi thiếu `failonerror="true"` | Negative test và kiểm tra mã thoát |
| Thiếu file bắt buộc nhưng target bị bỏ qua | Có nếu logic không chặn | Ca thiếu input, kỳ vọng exit khác 0 |
| Bản release chứa file từ lần chạy trước | Có | Clean build trong workspace sạch |
| File JAR có mặt nhưng rỗng/sai định dạng | Có trong pipeline kiểm tra sơ sài | Kiểm tra cấu trúc, kích thước và thực thi |

**Hợp đồng build** cần được viết thành các điều kiện quan sát được: tên sản phẩm, nội dung cần có, đầu vào bắt buộc, mã thoát khi lỗi, cách xử lý output thất bại và kết quả chạy thử.

## 2. Định nghĩa baseline trước khi sửa build

Trước khi bảo trì, nên mô tả hành vi dự kiến của build ở một revision ổn định. Đây là **baseline hành vi**, không nhất thiết chỉ là một file checksum.

Ví dụ hợp đồng cho một dự án Java nhỏ:

| Mã | Đầu vào / thao tác | Kết quả phải có |
| --- | --- | --- |
| B01 | Chạy `ant release` từ checkout sạch | Process exit `0`; tạo `dist/demo.jar` |
| B02 | Đọc JAR vừa tạo | Có `demo/Main.class` và `META-INF/MANIFEST.MF` |
| B03 | Đọc manifest | `Main-Class: demo.Main`, `Implementation-Version: 1.0.0` |
| B04 | Chạy `java -jar dist/demo.jar` | Exit `0`, stdout đúng `ant-regression-ok` |
| B05 | Thiếu source bắt buộc | Process exit khác `0`; không có JAR release |
| B06 | Manifest trỏ đến main class không tồn tại | Build từ chối phát hành JAR, process exit khác `0` |
| B07 | Thay source rồi clean build | Artifact phản ánh source mới; không giữ class cũ |
| B08 | Chạy build trong môi trường CI đã chốt | Kết quả đúng hợp đồng ở nền tảng được hỗ trợ |

Không nên chọn chỉ tiêu một cách tùy tiện. Ví dụ nếu byte JAR được yêu cầu **tái lập**, baseline có thể kèm SHA-256 ổn định; nếu toolchain, timestamp hoặc chữ ký chưa được cố định, hash có thể khác dù nội dung chức năng vẫn đúng. Khi đó phải kiểm tra **các bất biến thực sự cần thiết**, đồng thời xử lý riêng việc chuẩn hóa byte artifact nếu đó là yêu cầu phát hành.

Một baseline hữu ích có đủ bốn thành phần: **đầu vào được kiểm soát, thao tác cần chạy, trạng thái/mã thoát mong đợi và bằng chứng ở sản phẩm cuối**. Lưu lại revision, phiên bản Ant/JDK, lệnh và kỳ vọng để lần bảo trì tiếp theo có thể lặp lại.

## 3. Clean build: xóa đúng đầu ra, xây lại từ nguồn

### 3.1. Phân biệt incremental build và clean build

**Incremental build** cố tận dụng classfile/resource đã tạo; Ant có thể bỏ qua `<javac>` hoặc `<copy>` khi so sánh thời gian sửa file và tình trạng đầu ra. Cách này giúp tăng tốc vòng lặp phát triển nhưng phụ thuộc trạng thái trên đĩa.

**Clean build** xóa sản phẩm trung gian và sản phẩm phát hành do build sở hữu, sau đó thực hiện đầy đủ các bước tạo lại.

Ví dụ:

```xml
<project name="demo" default="release" basedir=".">
    <property name="work.dir" value="build"/>
    <property name="dist.dir" value="dist"/>

    <target name="clean">
        <delete dir="${work.dir}"/>
        <delete dir="${dist.dir}"/>
    </target>

    <target name="compile">
        <!-- compile thực tế -->
    </target>

    <target name="package" depends="compile">
        <!-- tạo artifact thực tế -->
    </target>

    <target name="release" depends="clean,package"/>
</project>
```

Trong ví dụ này, `ant release` buộc chạy target `clean` trước `package`. Ant duyệt dependency của target theo thứ tự được khai báo và không chạy lại một target đã thực hiện trong cùng invocation. Nếu chỉ gọi `ant package`, quy trình không nhất thiết dọn đầu ra trước.

Hai cách thường dùng:

```bash
ant clean package
ant release
```

Hai lệnh trên có thể thực hiện khác nhau nếu `release` còn có bước kiểm tra, ký hoặc sao chép sản phẩm. Khi viết CI, hãy chọn **target đại diện đúng luồng phát hành** và ghi rõ trong hợp đồng.

### 3.2. Clean không được xóa dữ liệu ngoài phạm vi build

Target `clean` cần biết **đầu ra nào do build sở hữu**. Không cho một biến được cấp tùy ý quyết định vị trí xóa thư mục quan trọng.

Ví dụ cấu hình rủi ro:

```xml
<target name="clean">
    <delete dir="${output.dir}"/>
</target>
```

Nếu `output.dir` lấy từ `-Doutput.dir=...` mà chưa kiểm soát, lệnh clean có thể xóa nhầm dữ liệu ngoài dự án. Với pipeline tin cậy, xác định rõ các thư mục dành riêng cho output (chẳng hạn `build/`, `dist/`), giới hạn nguồn cấu hình và chạy trong workspace cô lập. Không dùng glob quá rộng trùm cả source hoặc thư mục người dùng.

**Clean build mạnh hơn “chạy clean một lần”.** Để biết dự án thật sự đủ đầu vào, cần kiểm tra cả checkout sạch, dependencies đã định nghĩa và file cấu hình không bị rò rỉ từ máy phát triển. Một workspace mới tạo trong CI có giá trị kiểm chứng hơn thư mục đã dùng lâu và chỉ xóa một vài output.

### 3.3. Clean build chưa giải quyết mọi trạng thái ẩn

Dù đã xóa `build/` và `dist/`, các nguồn trạng thái khác có thể tồn tại:

- Cache dependency ngoài workspace; artifact được tải không có version cố định.
- File sinh trong `src/` hoặc một thư mục không bị clean xóa.
- Cấu hình cục bộ, biến môi trường, secret hoặc file path tuyệt đối.
- Công cụ đọc thời gian hiện tại, hostname, timezone hoặc locale.
- Một target chỉ chạy khi file tồn tại và lặng lẽ bỏ qua bước bắt buộc.
- Công cụ ngoài sử dụng trạng thái tạm nằm trong thư mục hệ thống.

Vì thế kiểm thử hồi quy có thể cần **hai mức**: clean build thông thường cho mỗi thay đổi và build từ checkout/runner sạch, toolchain chốt cho release.

## 4. Ví dụ hoàn chỉnh: build, kiểm tra JAR, rồi mới công bố

Ví dụ dưới sử dụng **Apache Ant có hỗ trợ thuộc tính `release` của `<javac>`** và **JDK 17+**. Nó mô phỏng một ứng dụng Java nhỏ. Mục tiêu là tạo JAR vào vùng staging, kiểm tra nội dung và chạy thử, sau đó mới sao chép sang `dist/` để đại diện cho sản phẩm phát hành cục bộ.

Cấu trúc:

```text
ant-regression-demo/
├── build.xml
├── src/
│   └── demo/
│       └── Main.java
├── build/                   # Ant tạo, có thể xóa
│   ├── classes/
│   ├── staging/
│   └── inspection/
└── dist/                    # Chỉ có sau bước xác minh thành công
```

**File `src/demo/Main.java`:**

```java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("ant-regression-ok");
    }
}
```

**File `build.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-regression-demo" default="release" basedir=".">

    <!-- Các -D... có thể ghi đè giá trị mặc định khi thử ca lỗi. -->
    <property name="src.dir" value="src"/>
    <property name="work.dir" value="build"/>
    <property name="classes.dir" value="${work.dir}/classes"/>
    <property name="stage.dir" value="${work.dir}/staging"/>
    <property name="inspection.dir" value="${work.dir}/inspection"/>
    <property name="stage.jar" value="${stage.dir}/demo.jar"/>
    <property name="dist.dir" value="dist"/>
    <property name="release.jar" value="${dist.dir}/demo.jar"/>
    <property name="main.class" value="demo.Main"/>
    <property name="release.version" value="1.0.0"/>

    <target name="clean">
        <!-- Chỉ xóa output thuộc build. -->
        <delete dir="${work.dir}"/>
        <delete dir="${dist.dir}"/>
    </target>

    <target name="check-input">
        <available file="${src.dir}/demo/Main.java"
                   type="file"
                   property="source.exists"/>
        <fail unless="source.exists"
              message="Thiếu source bắt buộc: demo/Main.java"/>
    </target>

    <target name="prepare" depends="check-input">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${stage.dir}"/>
    </target>

    <target name="compile" depends="prepare">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               encoding="UTF-8"
               release="17"
               includeantruntime="false"
               failonerror="true"/>
    </target>

    <target name="package" depends="compile">
        <!-- Chưa công bố vào dist/: đầu ra đang chờ xác minh. -->
        <jar destfile="${stage.jar}"
             basedir="${classes.dir}"
             duplicate="fail"
             update="false"
             whenmanifestonly="fail">
            <manifest>
                <attribute name="Main-Class"
                           value="${main.class}"/>
                <attribute name="Implementation-Version"
                           value="${release.version}"/>
            </manifest>
        </jar>
    </target>

    <target name="verify-artifact" depends="package">
        <available file="${stage.jar}"
                   type="file"
                   property="jar.exists"/>
        <fail unless="jar.exists"
              message="Không tìm thấy JAR ở vùng staging"/>

        <!-- Quan sát entry thật từ JAR, không giả định vì compile
             thành công thì file chắc chắn được đóng gói. -->
        <unzip src="${stage.jar}"
               dest="${inspection.dir}"/>

        <available file="${inspection.dir}/demo/Main.class"
                   type="file"
                   property="main.class.in.jar"/>
        <available file="${inspection.dir}/META-INF/MANIFEST.MF"
                   type="file"
                   property="manifest.in.jar"/>

        <fail unless="main.class.in.jar"
              message="JAR thiếu demo/Main.class"/>
        <fail unless="manifest.in.jar"
              message="JAR thiếu META-INF/MANIFEST.MF"/>

        <!-- Xác nhận phiên bản phát hành trong manifest. -->
        <loadfile property="manifest.text"
                  srcFile="${inspection.dir}/META-INF/MANIFEST.MF"
                  encoding="UTF-8"/>
        <condition property="manifest.version.ok">
            <contains string="${manifest.text}"
                      substring="Implementation-Version: ${release.version}"/>
        </condition>
        <fail unless="manifest.version.ok"
              message="Manifest không chứa version mong đợi"/>

        <!-- Smoke test trên chính JAR, không chạy class rời. -->
        <java jar="${stage.jar}"
              fork="true"
              failonerror="true"
              outputproperty="smoke.stdout"
              errorproperty="smoke.stderr"/>

        <condition property="smoke.ok">
            <equals arg1="${smoke.stdout}"
                    arg2="ant-regression-ok"
                    trim="true"/>
        </condition>
        <fail unless="smoke.ok"
              message="Output smoke test không khớp"/>
    </target>

    <target name="publish-local" depends="verify-artifact">
        <mkdir dir="${dist.dir}"/>
        <copy file="${stage.jar}"
              tofile="${release.jar}"
              overwrite="true"/>

        <available file="${release.jar}"
                   type="file"
                   property="release.jar.exists"/>
        <fail unless="release.jar.exists"
              message="Không tạo được dist/demo.jar"/>

        <!-- Chứng minh bản sao phát hành giống bản đã kiểm tra. -->
        <checksum file="${stage.jar}"
                  algorithm="SHA-256"
                  property="stage.sha256"/>
        <checksum file="${release.jar}"
                  algorithm="SHA-256"
                  property="release.sha256"/>
        <condition property="published.bytes.match">
            <equals arg1="${stage.sha256}"
                    arg2="${release.sha256}"
                    casesensitive="false"/>
        </condition>
        <fail unless="published.bytes.match"
              message="JAR phát hành khác byte JAR đã xác minh"/>
    </target>

    <!-- Luồng phát hành bắt buộc xóa output cũ trước. -->
    <target name="release"
            depends="clean,publish-local"/>
</project>
```

**Chạy clean build:**

```bash
ant -version
java -version
ant release
```

Trong một workspace có hai file đầu vào như trên, quy trình dự kiến:

```text
ant release
   |
   v
clean                  xóa build/, dist/
   |
   v
check-input            đòi src/demo/Main.java tồn tại
   |
   v
prepare -> compile     sinh build/classes/demo/Main.class
   |
   v
package                sinh build/staging/demo.jar
   |
   v
verify-artifact        kiểm tra entry, manifest, java -jar
   |
   v
publish-local          copy -> dist/demo.jar; so SHA-256
   |
   v
BUILD SUCCESSFUL
```

**Vì sao ví dụ tạo JAR ở staging?** Nếu compile hoặc kiểm tra JAR thất bại, bản JAR chưa đạt không được tự động đặt vào vị trí release. Điều này không thay thế cơ chế publish có giao dịch/atomicity ở artifact repository thực tế, nhưng là một cách tổ chức build rõ ràng: **kiểm tra xong rồi mới công bố**.

**Vì sao dùng `java jar="..." fork="true"`?** Smoke test chạy chính archive được đóng gói bằng một JVM con, đọc `Main-Class` trong manifest. Nếu chỉ gọi `<java classname="demo.Main" classpath="build/classes">`, chương trình có thể chạy dù JAR thiếu entry hoặc manifest sai, và phép thử sẽ bỏ sót lỗi đóng gói.

**Vì sao cần `loadfile`/`contains`?** Chạy thử chứng minh JAR khởi động nhưng chưa xác nhận phiên bản được khai báo. Manifest là một phần hợp đồng của artifact, nên được đọc từ file vừa đóng gói và đối chiếu với kỳ vọng.

**Giới hạn của ví dụ:** Chạy được JAR và có hai entry chính chưa chứng minh một hệ thống lớn có đầy đủ resource, dependency, chữ ký hoặc đường dẫn cấu hình cần dùng. Với ứng dụng thực tế, mở rộng các điều kiện kiểm tra tương ứng hợp đồng triển khai.

## 5. Ca lỗi: buộc build thất bại trong các điều kiện đã biết

Một bộ kiểm thử hồi quy chỉ chạy **happy path** dễ bỏ sót những thay đổi khiến Ant “nuốt lỗi”. **Negative test** phải có đầu vào không hợp lệ, kết quả mong đợi là *thất bại*, và phép xác nhận rằng không có artifact release hợp lệ nào được xuất ra.

### 5.1. Thiếu source bắt buộc

Ví dụ project cho phép `-Dsrc.dir=...` ghi đè vị trí source, nên có thể chạy:

```bash
ant -Dsrc.dir=missing-source release
```

Kỳ vọng:

- `clean` được chạy trước, làm trống `build/` và `dist/` cũ.
- Target `check-input` không tìm thấy `missing-source/demo/Main.java`.
- `<fail>` khiến Ant kết thúc với exit code **khác 0**.
- Không có `dist/demo.jar` được công bố.

Đây là test cho **validation của đầu vào bắt buộc**. Nếu build vẫn thành công do chỉ tạo một JAR rỗng hoặc do `<javac>` không thấy source và lặng lẽ bỏ qua, hợp đồng đã bị vi phạm.

### 5.2. Manifest chỉ đến main class sai

Sử dụng property `main.class` để tạo một lỗi có chủ đích:

```bash
ant -Dmain.class=demo.DoesNotExist release
```

`<javac>` vẫn có thể thành công; `<jar>` vẫn có thể đóng gói một manifest ghi `Main-Class: demo.DoesNotExist`. Nhưng bước `<java jar="..." fork="true" failonerror="true">` phải thất bại khi không tìm được entry point. Vì `publish-local` chỉ chạy sau `verify-artifact`, `dist/demo.jar` sẽ không xuất hiện trong một lần clean release thất bại.

Ca này cho thấy **kiểm tra artifact khác kiểm tra có tạo được file**. Chỉ yêu cầu `dist/demo.jar` tồn tại không đủ bảo đảm JAR thực sự dùng được.

### 5.3. Lỗi biên dịch

Trong một bản sao làm việc phục vụ test, tạo lỗi cú pháp nhỏ ở `Main.java` rồi chạy `ant release`. Kỳ vọng:

- Task `<javac failonerror="true">` trả lỗi và Ant dừng.
- Không chạy task `package` hoặc `publish-local`.
- Log xác định được file/dòng lỗi biên dịch.
- Lệnh build trả exit code khác `0`.

Không nên chủ động thay đổi mã nguồn thật của nhánh phát hành để tạo negative test. Có thể chuẩn bị fixture riêng hoặc một checkout tạm; mọi thao tác phá hoại đầu vào phải được giới hạn trong vùng thử nghiệm.

### 5.4. Công cụ ngoài lỗi

Nếu dự án có `<exec>` để chạy Git, trình nén, trình ký số hoặc tool generator, phải test ít nhất hai lớp lỗi:

1. **Không khởi chạy được** — tên/path executable không tồn tại hoặc không có quyền chạy.
2. **Có chạy nhưng trả exit code khác 0** — chương trình báo thất bại khi xử lý input.

Ví dụ cách gọi trong bước nghiệp vụ:

```xml
<exec executable="${tool.executable}"
      dir="${basedir}"
      failifexecutionfails="true"
      failonerror="true"
      timeout="30000">
    <arg value="--input"/>
    <arg file="${input.file}"/>
</exec>
```

`failifexecutionfails="true"` xử lý tình huống không thể tạo process; `failonerror="true"` xử lý tình huống chương trình chạy xong với exit code khác 0. Nếu công cụ bắt buộc, cả hai tình huống phải dừng build. Cũng cần kiểm tra sản phẩm của công cụ ngoài, vì một chương trình có thể trả `0` nhưng không tạo đúng output do hợp đồng hoặc bug của chính chương trình.

### 5.5. Cách test một lệnh được kỳ vọng phải thất bại

Một negative test được coi là **đạt** khi lệnh được thử **thất bại như mong đợi**. Nếu Ant bất ngờ trả `0`, chính test phải fail.

Ví dụ shell cho Linux/macOS:

```bash
#!/bin/sh
set -eu

if ant -Dsrc.dir=missing-source release; then
    echo "ERROR: build thieu source da thanh cong ngoai mong doi"
    exit 1
fi

if test -e dist/demo.jar; then
    echo "ERROR: artifact release ton tai sau build that bai"
    exit 1
fi

echo "PASS: thieu source duoc tu choi, khong publish artifact"
```

Ví dụ PowerShell:

```powershell
& ant -Dsrc.dir=missing-source release
if ($LASTEXITCODE -eq 0) {
    throw 'ERROR: expected build failure for missing source'
}
if (Test-Path -LiteralPath 'dist/demo.jar') {
    throw 'ERROR: release artifact exists after failed build'
}
Write-Output 'PASS: missing input rejected'
```

Hai ví dụ kiểm tra cả **exit code** lẫn **điều kiện sau thất bại**. Với codebase thực tế, nên chạy các negative cases ở workspace độc lập để không va chạm output của các phép thử khác. Nếu dùng chung workspace, cần bảo đảm từng ca bắt đầu từ trạng thái sạch và kết thúc với dữ liệu được khôi phục.

### 5.6. Phân biệt lỗi mong đợi với lỗi hạ tầng

Một negative test có thể trả exit khác 0 vì nhiều lý do: đúng validation, hết ổ đĩa, thiếu JDK, không tải được dependency, hoặc runner bị hỏng. **Exit code khác 0 là điều kiện cần, chưa đủ để xác nhận đúng nguyên nhân.**

Với ca quan trọng, ngoài exit code và không có artifact, hãy kiểm tra thêm dấu hiệu lỗi đặc trưng như thông báo `Thiếu source bắt buộc` hoặc mã lỗi do task của dự án quy định. Khi test phụ thuộc chuỗi log, chọn marker ổn định do chính build kiểm soát, tránh đối chiếu cả log của compiler/JDK vốn có thể thay đổi.

Bản build kiểm thử cũng cần cách phân biệt *test không chạy được* với *test chạy và phát hiện lỗi đúng*. Nếu thiếu Ant/JDK, CI phải báo lỗi hạ tầng và không ghi nhận test là pass chỉ vì exit khác 0.

## 6. Kiểm tra sản phẩm: xác minh đúng thứ đem triển khai

### 6.1. Không dừng ở điều kiện “file tồn tại”

Kiểm tra đơn giản:

```xml
<available file="dist/demo.jar"
           type="file"
           property="artifact.exists"/>
<fail unless="artifact.exists"
      message="Khong co artifact"/>
```

Điều này chứng minh có một file tại path, nhưng không trả lời:

- JAR có phải một ZIP hợp lệ không?
- File có thực sự vừa được build hay còn từ lần trước?
- Có đúng class, resource và manifest cần thiết không?
- Manifest có phiên bản và entry point đúng không?
- JAR có chạy được trên môi trường mục tiêu không?
- Có chứa file bị cấm như secret, bản backup, cache, file riêng máy không?
- Có thể đưa JAR này vào repository phát hành một cách an toàn không?

Vì vậy, nên kiểm tra theo **nhiều tầng**, tùy hợp đồng của sản phẩm.

### 6.2. Bốn tầng kiểm tra JAR/ZIP

| Tầng | Điều kiện | Cách kiểm tra |
| --- | --- | --- |
| File vật lý | Đúng tên, đúng vị trí, kích thước hợp lý, được tạo từ run hiện tại | `<available>`; clean/staging; thông tin file |
| Cấu trúc archive | ZIP đọc được, có entry bắt buộc, không có entry cấm | `jar tf`, `<unzip>`, công cụ kiểm tra ZIP |
| Metadata | `Main-Class`, `Implementation-Version`, manifest, cấu hình phát hành đúng | Đọc `META-INF/MANIFEST.MF` và resource |
| Hành vi | JAR chạy/test/smoke thành công; output và exit đúng | `java -jar`, `<java fork="true">`, integration test |

Một hệ thống phức tạp có thể có tầng thứ năm: **kiểm tra nguồn gốc và tính toàn vẹn của artifact phát hành**, chẳng hạn SHA-256, chữ ký hợp lệ, danh sách dependency hoặc provenance. Những kiểm tra đó cần gắn với quy trình release thực tế.

### 6.3. Xem archive bằng công cụ JDK

Sau khi build, có thể xem:

```bash
jar tf dist/demo.jar
jar tvf dist/demo.jar
java -jar dist/demo.jar
```

`jar tf` liệt kê entry; `jar tvf` cho thêm metadata như kích thước/thời gian; `java -jar` chạy thử entry point. Nếu cần đọc manifest mà không dùng `unzip`, có thể giải nén vào thư mục kiểm thử riêng:

```bash
mkdir inspection
cd inspection
jar xf ../dist/demo.jar
```

Các lệnh trên giả sử shell và thư mục hiện tại phù hợp. **Không giải nén một archive chưa đáng tin vào vị trí chứa dữ liệu quan trọng.** Với artifact từ nguồn lạ, sử dụng thư mục cô lập và kiểm tra path entry để phòng nguy cơ ghi đè/traversal.

Trong Ant, ví dụ ở mục 4 dùng `<unzip>` để tạo `build/inspection/`, sau đó kiểm tra class và manifest trực tiếp bằng `<available>`. Cách này tránh phụ thuộc vào `grep` hoặc `unzip` CLI của từng hệ điều hành.

### 6.4. Kiểm tra nội dung bị cấm

Ngoài các entry bắt buộc, danh mục **entry không được xuất hiện** cũng là một phần hợp đồng:

- File `.env` hoặc cấu hình chứa token/password.
- Thư mục `.git/`, `node_modules/`, cache và log cá nhân không thuộc gói phát hành.
- File sao lưu `*.bak`, `*.tmp`, bản build cũ và dữ liệu test.
- Path tuyệt đối/hostname của build agent trong metadata, nếu phạm vi phát hành yêu cầu build tái lập.
- Class hoặc resource đã bị xóa khỏi source nhưng còn trong output cũ.

Có thể đọc danh sách entry rồi so với allowlist hoặc quy tắc đóng gói cụ thể. Với JAR Java thuần, việc tạo `<jar basedir="${classes.dir}">` từ thư mục classes sạch thường dễ kiểm soát hơn gom toàn bộ project với `<fileset dir=".">`.

### 6.5. Kiểm tra phiên bản và thành phần phụ thuộc

Nếu JAR phải khai báo `Implementation-Version: 1.0.0`, kiểm tra manifest là bắt buộc. Nếu một bản phân phối ZIP phải có `bin/start.sh`, `lib/app.jar` và `config/default.yml`, kiểm tra từng entry bắt buộc. Nếu release yêu cầu tất cả dependency đi kèm, một smoke test riêng từ môi trường sạch thường phát hiện thiếu thư viện mà chạy từ IDE chưa chắc thấy.

Khi ứng dụng cần các điều kiện từ dịch vụ ngoài (database, message broker...), tách **smoke test tối thiểu của artifact** khỏi **integration test phụ thuộc hạ tầng**. Không làm cho một yêu cầu dịch vụ ngoài không liên quan khiến mọi clean build cục bộ bất khả thi; nhưng cũng không tuyên bố release đã kiểm thử đầy đủ khi chưa chạy integration test cần thiết.

## 7. Kiểm thử hồi quy riêng cho incremental build

Clean build chứng minh quy trình có thể dựng lại từ nguồn; **incremental regression** kiểm tra độ đúng khi build nhiều lần trong cùng workspace. Hai nhóm test không thay thế cho nhau.

Một chuỗi thử nghiệm điển hình:

1. Chạy `ant release` từ trạng thái sạch; ghi nhận entry JAR.
2. Sửa một source hợp lệ và chạy target compile/package tương ứng **không clean**; kiểm tra class và hành vi mới.
3. Xóa một source class không còn dùng; chạy incremental; kiểm tra class cũ có còn trong JAR không.
4. So lại với artifact sau một clean build cùng revision. Nếu hai sản phẩm cần tương đương, khác biệt là dấu hiệu cơ chế dọn stale output hoặc packaging chưa đúng.
5. Chạy lại target không thay đổi input; xác nhận không có sự khác biệt bất ngờ do timestamp, phiên bản sinh tự động hoặc resource cũ.

Ví dụ ngắn: trước đây có `src/demo/Legacy.java`, sau khi xóa file source, `build/classes/demo/Legacy.class` vẫn có thể tồn tại vì `<javac>` không mặc nhiên dọn classfile cho source đã bị xóa. Một `<jar basedir="build/classes">` sẽ có nguy cơ đóng gói class cũ. Do đó:

- **Clean release** cho phép sản phẩm không chứa class cũ.
- **Incremental package** có thể cần cơ chế dọn stale outputs hoặc điều kiện bắt buộc clean tại ranh giới phát hành.
- **Artifact verification** phải kiểm tra các entry cấm để biến vấn đề thành lỗi quan sát được.

Không nhất thiết mọi lệnh phát triển đều phải clean (chi phí cao), nhưng luồng release cần có hợp đồng rõ về việc loại bỏ stale files.

## 8. Cách tổ chức bộ ca hồi quy build trong CI

Một ma trận kiểm thử giúp phân biệt lỗi chức năng build với lỗi do nền tảng, phiên bản công cụ hoặc trạng thái cache:

| Nhóm | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| Clean positive | Workspace sạch, JDK/Ant đúng version, `ant release` | Exit `0` và có artifact đạt kiểm tra |
| Artifact positive | Liệt kê entry, đọc manifest, chạy smoke | Đủ thành phần, đúng metadata, exit/output chuẩn |
| Missing input negative | `src.dir` trỏ đến source không tồn tại | Exit khác `0`, không có bản release |
| Invalid entry point | `main.class` sai | Đóng JAR vào staging có thể thành công, smoke fail, không publish |
| Compile failure | Source thử nghiệm có lỗi cú pháp | Compiler fail, package/publish không chạy |
| Tool failure | Binary thiếu hoặc trả mã lỗi | Build fail, không báo thành công giả |
| Repeat clean | Cùng source/toolchain, chạy clean hai lần | Cùng hợp đồng; nếu yêu cầu byte tái lập thì cùng digest |
| Incremental change | Source/resource đổi hoặc bị xóa | Artifact phản ánh thay đổi, không chứa stale files |
| Cross-platform | Windows/Linux/macOS được hỗ trợ | Hành vi và gói sản phẩm nhất quán theo hợp đồng |

Có thể chia quy trình thành ba lớp chi phí:

**Lớp nhanh (mỗi pull request).** Chạy clean build + verify artifact + vài negative cases chủ chốt trên một nền tảng chuẩn. Mục tiêu phát hiện thay đổi dễ gây regress trong `build.xml` trước khi merge.

**Lớp mở rộng (PR nhạy cảm hoặc theo lịch).** Chạy nhiều OS, Java version được hỗ trợ, input missing, tool missing, incremental file deletion và resource packaging. Mục tiêu phát hiện sai biệt theo môi trường và trường hợp biên.

**Lớp phát hành (tag/revision được duyệt).** Chạy release trên workspace/runner sạch, kiểm tra sản phẩm cuối, metadata, chữ ký, digest, dependency, smoke/integration cần thiết rồi mới cho job publish tiếp tục.

Nếu môi trường CI dùng cache để tăng tốc, vẫn nên có một job **không phụ thuộc cache đầu ra biên dịch**. Nếu không, lỗi thiếu dependency hoặc đầu ra không thể tạo lại có thể bị che lấp.

### 8.1. Cần kiểm tra mã thoát từ process Ant

Khi CI gọi Ant qua script, chính script điều phối test phải dừng khi Ant thất bại ngoài mong đợi.

Shell:

```bash
#!/bin/sh
set -eu
ant release
test -f dist/demo.jar
java -jar dist/demo.jar
```

PowerShell:

```powershell
& ant release
if ($LASTEXITCODE -ne 0) {
    throw 'Ant release failed'
}
if (-not (Test-Path -LiteralPath 'dist/demo.jar')) {
    throw 'Missing release artifact'
}
& java -jar dist/demo.jar
if ($LASTEXITCODE -ne 0) {
    throw 'JAR smoke test failed'
}
```

Một pipeline có thể vô tình báo xanh nếu script bỏ qua `$LASTEXITCODE` hoặc dùng một lệnh sau cùng thành công để che thất bại trước đó. Đây là lỗi của **bộ kiểm thử build**, không chỉ của chính `build.xml`.

### 8.2. Cách theo dõi kết quả có ích khi bảo trì

Với mỗi lần chạy, lưu các bằng chứng sau trong kết quả CI:

- Revision nguồn và phiên bản Ant/JDK, OS/architecture.
- Lệnh/target đã chạy cùng những tham số quan trọng (không chứa secrets).
- Mã thoát của positive/negative cases và tên ca được thực hiện.
- Danh sách entry hoặc metadata đã kiểm tra trong artifact.
- SHA-256 của sản phẩm cuối, khi việc lưu digest có ích để đối chiếu.
- Log thất bại và vị trí artifact đã được xác minh.

Việc lưu **digest kèm revision** cho phép truy vết và so sánh, nhưng không tự bảo đảm tính tái lập hay nguồn gốc tin cậy. Cần dùng thêm các kiểm soát source/toolchain và quy trình publish theo chính sách dự án.

## 9. Hồi quy khi thay đổi build.xml: chọn ca phù hợp với thay đổi

Không phải mọi thay đổi cần chạy mọi hệ thống phụ trợ, nhưng nên xem tác động của thay đổi lên các **hợp đồng build**.

| Thay đổi | Rủi ro chính | Ca nên ưu tiên |
| --- | --- | --- |
| Sửa đường dẫn `srcdir`, `destdir` | Không compile đúng source, class cũ còn | Clean, missing input, class JAR |
| Sửa `<copy>` và `fileset` | Thiếu/thừa resource | Kiểm tra entry bắt buộc/cấm |
| Đổi `Main-Class` hoặc manifest | JAR không chạy, version sai | Đọc manifest, `java -jar` |
| Thêm `<exec>` | Lỗi bị bỏ qua, thiếu binary trên CI | Exit code, missing tool, probe, cross-platform |
| Thêm `<taskdef>`/antlib | Classpath sai, task không có, dependency drift | Clean từ runner mới, pin dependency |
| Đổi target `depends` | Thứ tự thao tác sai, bỏ bước kiểm tra | Clean/release, negative test, xác minh gating |
| Đổi cấu hình timestamp/version | Artifact thay đổi không chủ đích | So metadata và digest khi cần |
| Đổi cách nén/ký | JAR/ZIP không hợp lệ hoặc mất chữ ký | Kiểm tra archive và verify chữ ký |
| Thêm cache/incremental optimization | Dùng stale output | Clean vs incremental comparison |
| Đổi output path | Publish sai file hoặc file cũ | Kiểm tra đúng file sản phẩm cuối |

Ví dụ sau là một **regression rất dễ bị bỏ sót**:

```xml
<target name="release" depends="package,verify-artifact"/>
```

Nếu `package` tạo thẳng `dist/demo.jar` rồi `verify-artifact` thất bại, file chưa đạt đã nằm trong vị trí release. Tốt hơn là dùng **staging + verify + publish-local** như ví dụ hoàn chỉnh, đồng thời coi job xuất bản ra ngoài là một bước riêng chỉ chạy sau khi tất cả kiểm tra đạt.

Một hồi quy khác là xóa `failonerror="true"` khỏi `<exec>`: trình ký số hoặc generator thất bại, nhưng lệnh `ant release` vẫn có thể báo thành công. Ca lỗi cố ý cho công cụ trả exit khác 0 sẽ phát hiện hành vi sai này.

## 10. Tránh phép thử không ổn định và kết luận sai

### 10.1. Test phụ thuộc thời gian hoặc mạng

Nếu test phụ thuộc API internet, mốc thời gian hệ thống hoặc server bên ngoài, một kết quả fail có thể không liên quan thay đổi trong build. Chọn fixture cục bộ và input được chốt cho hồi quy build cốt lõi; đặt integration test phụ thuộc mạng ở lớp riêng với điều kiện chạy rõ ràng.

### 10.2. Hash khác chưa chắc là hồi quy chức năng

Khi hash artifact khác giữa hai môi trường, xác minh đầu tiên là: source có giống, JDK/Ant có giống, timestamp archive và manifest có được chuẩn hóa, thứ tự đóng gói có ổn định không? Nếu yêu cầu release là **byte-for-byte reproducibility**, mọi khác biệt đều phải được điều tra. Nếu yêu cầu chỉ là chức năng, hash khác là tín hiệu phân tích thêm, không thay cho kiểm tra cấu trúc và hành vi.

### 10.3. Negative test fail vì sai lý do

Ví dụ test thiếu source trả exit khác 0 vì JDK chưa được cài. Nếu bộ điều phối chỉ xem mã thoát, nó có thể thông báo **PASS** sai. Thêm kiểm tra điều kiện tiên quyết và marker lỗi ổn định từ chính Ant, đồng thời phân loại failure hạ tầng.

### 10.4. Artifact cũ khiến phép thử cho kết quả giả

Nếu `dist/demo.jar` đã có từ lần build thành công trước, một lần build thất bại vẫn có thể để lại file đó. Test “thất bại rồi không có JAR” phải bắt đầu bằng clean hoặc workspace mới; còn pipeline phát hành thật nên tách staging khỏi đích cuối và không dùng output cũ làm kết quả mới.

### 10.5. Kiểm tra class rời nhưng không kiểm tra archive

Chạy `java -cp build/classes demo.Main` chỉ chứng minh class ở thư mục build có thể chạy; không chứng minh JAR có manifest và entry cần thiết. **Luôn smoke test sản phẩm thực tế** khi hợp đồng phát hành là một JAR có thể chạy.

### 10.6. Overwrite đầu vào hoặc fixture trong lúc kiểm thử

Ca lỗi nên thực hiện trên bản sao riêng, thư mục test hoặc file fixture. Không dùng target `clean` xóa thư mục nguồn hoặc thay data thật để tiện tạo negative case. Một bộ kiểm thử gây phá hoại dữ liệu làm giảm độ tin cậy của quy trình bảo trì.

### 10.7. Đặt kỳ vọng quá yếu

Những khẳng định như “log có chữ BUILD SUCCESSFUL”, “file JAR tồn tại” hay “jar có kích thước lớn hơn 0” có giá trị nhưng quá yếu nếu đứng một mình. Dự án cần chọn ít nhất những điều kiện thể hiện **mục đích sử dụng của artifact**: class/resource đúng, metadata đúng, chạy/khởi tạo được, và không được publish khi thất bại.

## 11. Bộ tiêu chí bàn giao sau khi bảo trì build

Khi một thay đổi ở Ant đã hoàn tất, người bảo trì nên có khả năng đưa ra câu trả lời có bằng chứng cho các câu hỏi sau:

| Câu hỏi | Bằng chứng mong đợi |
| --- | --- |
| Có build lại từ trạng thái sạch không? | Log clean release ở workspace mới, exit 0 |
| Có phụ thuộc output cũ không? | Thử xóa build/dist và so với lần chạy incremental |
| Khi thiếu input, Ant có dừng không? | Negative test thiếu source, exit khác 0 |
| Khi biên dịch sai, Ant có dừng trước đóng gói không? | Compiler failure, không có release artifact |
| Khi tool ngoài lỗi, Ant có trả thất bại không? | Case exit nonzero và missing executable |
| Artifact có chứa đúng thành phần không? | Danh sách entry JAR và kiểm tra resource |
| Metadata có đúng không? | Manifest/phiên bản/entry point được kiểm tra |
| Artifact có dùng được không? | Smoke test trên chính file JAR/ZIP |
| Có thể phát hành nhầm file chưa đạt không? | Chỉ chuyển từ staging sang dist sau khi verify |
| CI có báo đúng trạng thái không? | Mã thoát Ant được kiểm tra; negative test không pass giả |
| Cần hỗ trợ OS/JDK nào? | Ma trận chạy trên môi trường đã xác định |
| Có thể truy vết lần build không? | Revision, toolchain, log, digest phù hợp |

Đây là **tiêu chí cho quy trình bảo trì**, không phải yêu cầu chèn tất cả kiểm tra vào một target. Một số kiểm tra nằm trong `build.xml`, một số trong script CI, một số ở job release. Điều quan trọng là mọi điều kiện bắt buộc đều được thực thi trước khi artifact được coi là hợp lệ.

## 12. Bài thực hành

### Bài 1 — Clean build và sản phẩm đúng

Tạo hai file `build.xml` và `src/demo/Main.java` ở mục 4, chạy `ant release`. Quan sát `build/staging/demo.jar` và `dist/demo.jar`. Dùng `jar tf` và `java -jar` để xem archive thực sự chứa gì và chạy ra output nào. Ghi nhận các điều kiện mà target `verify-artifact` đã kiểm tra.

### Bài 2 — Negative case thiếu source

Chạy `ant -Dsrc.dir=missing-source release` trong một workspace thử nghiệm. Kiểm tra **cả** exit code lẫn sự không tồn tại của `dist/demo.jar`. Giải thích vai trò của `check-input` và vì sao không nên chỉ dựa vào hành vi mặc định của `javac` khi không thấy source.

### Bài 3 — Negative case manifest sai

Chạy `ant -Dmain.class=demo.DoesNotExist release`. Tìm hiểu vì sao `package` có thể tạo JAR ở `build/staging` nhưng `verify-artifact` thất bại. Trả lời: vì sao `dist/demo.jar` phải vắng mặt, và nếu package được ghi thẳng vào dist thì sẽ có rủi ro gì?

### Bài 4 — Hồi quy stale class

Trong bản sao dự án, thêm `src/demo/Legacy.java` và biên dịch. Xóa file Java này, rồi chạy `ant package` **không clean** để quan sát khả năng `Legacy.class` còn nằm trong JAR. Sau đó chạy `ant release` và đối chiếu danh sách entry. Thảo luận khi nào pipeline cần clean bắt buộc, khi nào có thể dựa vào cơ chế dọn output cũ.

### Bài 5 — Tự thiết kế bảng regression cho dự án thật

Chọn một dự án Ant có JAR/ZIP hoặc generated resources. Xác định ít nhất một ca của mỗi nhóm: **clean positive**, **negative input/tool failure** và **artifact verification**. Với mỗi ca, mô tả input, target, exit code mong đợi, file đầu ra và phép kiểm xác nhận. Nếu dự án chạy trên nhiều OS, nêu rõ môi trường nào phải thực thi từng ca.

## Tài liệu tham khảo

- Apache Ant — [Targets](https://ant.apache.org/manual/targets.html): target, `depends`, `if`/`unless` và thứ tự thực thi.
- Apache Ant — [Delete task](https://ant.apache.org/manual/Tasks/delete.html): xóa thư mục/file đầu ra trong `clean`.
- Apache Ant — [Javac task](https://ant.apache.org/manual/Tasks/javac.html): biên dịch và các thuộc tính ảnh hưởng incremental compilation.
- Apache Ant — [Jar task](https://ant.apache.org/manual/Tasks/jar.html): manifest, đóng gói, kiểm soát archive.
- Apache Ant — [Unzip task](https://ant.apache.org/manual/Tasks/unzip.html), [Available task](https://ant.apache.org/manual/Tasks/available.html) và [Checksum task](https://ant.apache.org/manual/Tasks/checksum.html): kiểm tra file và thành phần sản phẩm.
- Apache Ant — [Java task](https://ant.apache.org/manual/Tasks/java.html): smoke test ứng dụng Java/JAR bằng JVM con, xử lý exit và output.
- Apache Ant — [Exec task](https://ant.apache.org/manual/Tasks/exec.html): công cụ ngoài, `failonerror`, `failifexecutionfails`, `resultproperty`.
- Apache Ant — [Fail task](https://ant.apache.org/manual/Tasks/fail.html), [Condition task](https://ant.apache.org/manual/Tasks/condition.html), [LoadFile task](https://ant.apache.org/manual/Tasks/loadfile.html): biểu diễn điều kiện bắt buộc và báo lỗi có chủ đích.

**Kết luận cần nhớ:** Một thay đổi ở `build.xml` chỉ đáng tin sau khi đã chứng minh quy trình **build sạch được từ nguồn**, **từ chối các điều kiện lỗi đại diện** và **tạo đúng artifact thực tế được sử dụng hoặc triển khai**. Chạy clean, chạy ca lỗi và kiểm tra sản phẩm là ba lớp bằng chứng khác nhau; kết hợp chúng thành một hợp đồng hồi quy có thể lặp lại giúp bảo trì Ant mà không vô tình phá hỏng đường phát hành.

