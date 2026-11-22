# Ranh giới tin cậy của build.xml, antlib và công cụ ngoài trong Apache Ant

Apache Ant đọc một file XML để xây dựng phần mềm. Vì có đuôi `.xml`, `build.xml` dễ bị nhầm là dữ liệu khai báo vô hại. Trên thực tế, **build file có thể yêu cầu Ant thực hiện thao tác với file, mạng, tiến trình hệ điều hành và mã Java tùy biến**. Thư viện mở rộng `antlib` có thể nạp class Java vào quá trình Ant; chương trình gọi bằng `<exec>` có thể thực thi dưới quyền của tài khoản đang chạy build.

Trong chương **An toàn build** của **Build Tool Ant**, bài học này xác định ba ranh giới tin cậy quan trọng: **(1) build.xml và các build file liên quan; (2) antlib, task và thư viện mở rộng; (3) công cụ ngoài được gọi khi build**. Nội dung tập trung vào cách nhìn nhận quyền thực thi, cách một đầu vào kém tin cậy đi qua ranh giới, và cách thiết kế CI/build để một thành phần chưa được phê duyệt không mặc nhiên có quyền của máy phát hành.

## 1. Hiểu đúng “ranh giới tin cậy”

Một **ranh giới tin cậy (trust boundary)** là điểm mà dữ liệu hoặc mã từ một nguồn có mức tin cậy thấp hơn bắt đầu được sử dụng trong một ngữ cảnh có quyền cao hơn. Với Ant, các điểm vượt ranh giới thường không xuất hiện dưới tên “security” mà dưới tên task thông thường:

- **`build.xml`:** một file do người dùng, repository, pull request hoặc công cụ sinh ra có thể điều khiển các task của Ant.
- **`<import>`, `<include>` và `<ant>`:** có thể nạp hoặc kích hoạt build file khác. Review file gốc mà bỏ qua build file được nạp là chưa thấy hết mã sẽ chạy.
- **`<taskdef>`, `<typedef>` và antlib:** đăng ký các class, type hoặc task do thư viện Java bên ngoài cung cấp. Khi được nạp/chạy, chúng tham gia cùng quá trình build.
- **`<exec>`, `<apply>` và `<java>`:** có thể chạy executable hoặc chương trình Java; chúng nhận quyền và tài nguyên của môi trường thực thi.
- **Tài nguyên đầu vào:** URL, JAR, file cấu hình, biến môi trường, tham số `-D`, đường dẫn và executable trên `PATH` có thể làm thay đổi chương trình được gọi hoặc dữ liệu đi vào thao tác có quyền.

Sơ đồ luồng tin cậy điển hình:

```text
Nguồn từ bên ngoài
(PR, dependency, URL, PATH, input, cấu hình)
                  |
                  v
        [Ranh giới A: chọn và
        phê duyệt nguồn build]
                  |
                  v
         build.xml + import
                  |
        +---------+-----------+
        |                     |
        v                     v
[Ranh giới B]           [Ranh giới C]
taskdef / typedef      exec / apply / java
antlib JAR              executable / interpreter
        |                     |
        v                     v
Mã Java trong           Tiến trình con
process Ant             của hệ điều hành
        |                     |
        +----------+----------+
                   |
                   v
       Tài khoản chạy build
  (filesystem, network, credentials)
                   |
                   v
         Artifact + log + cache
```

**Tuyên bố nền tảng:** Ant không cung cấp sandbox bảo mật cho một `build.xml` bất kỳ. Nếu build file là không đáng tin, không thể giải quyết bằng cách chỉ “giới hạn vài target” trong chính file đó: người kiểm soát file có thể sửa task, thêm task mới, import build file khác hoặc thay cấu hình kiểm tra.

Ranh giới cần được bảo vệ **ở bên ngoài mã chưa đáng tin**: quyền của runner, loại sự kiện CI, quyền đọc/ghi, phân phối secrets, nguồn toolchain và cơ chế phê duyệt thay đổi.

## 2. Ranh giới thứ nhất: build.xml là mã điều khiển thực thi

### 2.1. Tại sao XML vẫn có quyền tạo tác dụng phụ?

Một build file có thể chứa:

```xml
<project name="demo" default="package" basedir=".">
    <target name="prepare">
        <mkdir dir="build"/>
        <copy file="config/sample.properties"
              tofile="build/sample.properties"/>
    </target>

    <target name="package" depends="prepare">
        <jar destfile="dist/demo.jar"
             basedir="build"/>
    </target>
</project>
```

Đây là một bản build bình thường: tạo thư mục, copy file và đóng JAR. Nhưng cùng cú pháp XML còn có thể yêu cầu:

| Khả năng của Ant | Ví dụ task | Tài nguyên bị tác động |
| --- | --- | --- |
| Đọc/ghi/xóa dữ liệu | `<copy>`, `<move>`, `<delete>` | File trong workspace và những nơi tài khoản có quyền |
| Tạo gói/kết quả mới | `<jar>`, `<zip>`, `<echo file="...">` | Artifact và file xuất bản |
| Gọi tiến trình ngoài | `<exec>`, `<apply>` | Executable, shell, thư viện hệ thống |
| Thực thi chương trình Java | `<java>`, `<taskdef>` | JVM và mã Java được tải |
| Truy cập tài nguyên qua mạng | `<get>` và task bổ sung từ antlib | Nguồn tải, repository, dịch vụ bên ngoài |
| Mở rộng đồ thị thực thi | `<import>`, `<include>`, `<ant>`, `<antcall>` | Build file/target bổ sung |

Các task chỉ giới hạn bởi quyền thực tế của process Ant, điều kiện của hệ điều hành và chính sách runtime; **không** bị giới hạn chỉ vì dự án gọi chúng là “build task”.

Ví dụ nếu Ant chạy trên một runner có quyền ghi vào nơi phát hành, một build file bị thay đổi có thể cố sử dụng quyền đó. Nếu Ant chạy dưới tài khoản không được cấp quyền phát hành, cùng hành vi sẽ bị giới hạn bởi hệ điều hành hoặc dịch vụ.

### 2.2. Đường dẫn build file cũng là một nguồn mã

Người vận hành thường chạy:

```bash
ant -f build.xml release
```

Tùy hệ thống, build còn có thể dùng `-f` để chọn file khác, hoặc một file được nạp qua `<import>`:

```xml
<project name="demo" default="release">
    <import file="build/common.xml"/>
    <target name="release" depends="shared.prepare"/>
</project>
```

Khi review phải xem **cả nội dung `build/common.xml`**, cũng như các import và taskdef từ file đó. Một thay đổi ở `build/common.xml` có thể làm thay đổi hành vi của `ant release` dù dòng lệnh và `build.xml` ở gốc vẫn giữ nguyên.

Các thành phần khác có thể ảnh hưởng quá trình chạy:

- File bổ sung được gọi qua `<ant antfile="...">` hoặc `<subant>`.
- Task định nghĩa từ `<macrodef>` hoặc `<presetdef>`: là cách tái sử dụng hành vi, không phải vùng an toàn.
- Thư viện được nạp qua `<taskdef>`, `<typedef>`, `-lib` hoặc classpath của Ant.
- Property truyền qua `-Dkey=value` và những file `.properties`/biến môi trường mà build file đọc.
- Tham số, file và đường dẫn do script CI chọn khi gọi Ant.

Ngay cả thao tác chỉ “xem danh sách target” cũng không nên được coi là thực thi build file không tin cậy trong sandbox; Ant có thể phải phân tích project và xử lý cấu hình/định nghĩa ở mức project. Với một repository lạ, hãy xem XML là **mã cần review**, không thực thi chỉ để tìm hiểu.

### 2.3. Quy tắc nguồn đáng tin

Đối với build phát hành, cần xác định:

1. **Revision:** build từ commit hoặc tag đã phê duyệt, không lấy nội dung `build.xml` đang thay đổi trong một PR chưa review.
2. **Chuỗi phụ thuộc file:** mọi `import`, `include`, build file phụ, file cấu hình điều khiển target và script gọi từ Ant đều thuộc phạm vi review.
3. **Quyền chạy:** job xử lý code chưa tin cậy dùng quyền thấp, không được đưa signing key hoặc token ghi phát hành.
4. **Chính sách nằm ngoài build file:** kiểm soát branch protection, runner, quyền token, quy tắc cấp secrets và nguồn artifact phải do CI hoặc hạ tầng đáng tin thực thi.

Không thể đặt một `<target name="security-check">` trong file do người không tin cậy kiểm soát rồi xem đó là bảo vệ đầy đủ: cùng người ấy cũng có thể sửa hoặc bỏ target đó.

## 3. Ranh giới thứ hai: antlib và custom task là mã Java

### 3.1. antlib thực chất là gì?

Trong Ant, **antlib** là tập định nghĩa task/type mở rộng, thường được đóng gói trong một JAR có file `antlib.xml`. Chẳng hạn:

```xml
<!-- File bên trong JAR:
     org/example/build/antlib.xml -->
<antlib>
    <taskdef name="transform"
             classname="org.example.build.TransformTask"/>
</antlib>
```

Build file có thể nạp thư viện:

```xml
<project name="demo"
         xmlns:tools="antlib:org.example.build">
    <taskdef uri="antlib:org.example.build"
             resource="org/example/build/antlib.xml"
             classpath="vendor/example-build-antlib.jar"/>

    <target name="transform">
        <!-- Cú pháp minh họa, thuộc tính cụ thể phụ thuộc API của task. -->
        <tools:transform/>
    </target>
</project>
```

Tên `antlib:org.example.build` là **URI định danh namespace**, giúp Ant định tuyến tên task. Nó **không phải chứng chỉ, chữ ký số, không xác thực publisher và không tạo sandbox**.

Một class được khai báo qua `<taskdef>` có thể được tải vào JVM Ant. Khi thực thi, custom task có thể sử dụng API Java, đọc biến môi trường, mở file hoặc gọi process theo quyền tài khoản chạy Ant. Nó không tự trở nên an toàn vì được viết bằng Java hay có namespace riêng.

### 3.2. Điều gì nằm trong ranh giới antlib?

| Thành phần | Cần xác minh điều gì? |
| --- | --- |
| JAR của antlib | Nguồn phát hành, phiên bản, checksum/chữ ký, việc thay thế file |
| `antlib.xml` | Các task/type/script/macro thực sự được khai báo |
| Class và phụ thuộc đi kèm | Code được thực thi khi nạp hoặc gọi task |
| `classpath` và `-lib` | Những JAR nào có thể được Ant tìm và tải |
| Artifact repository | Địa chỉ tin cậy, phiên bản cố định, quyền ghi, rủi ro thay nội dung |
| Đường dẫn local/cache | Một file có tên hợp lệ nhưng có thể đã bị thay byte |

Các cơ chế `loaderref`, classloader và namespace có thể giúp tổ chức việc nạp class hoặc tránh xung đột, nhưng **không phải ranh giới cô lập an ninh**. Nếu custom task không đáng tin, không nên tải nó trong process có quyền nhạy cảm.

Bản thân antlib cũng có thể định nghĩa `macrodef`, `presetdef` hoặc `scriptdef`, ngoài `taskdef`/`typedef`. Một task sử dụng script engine (khi runtime có engine phù hợp) hoặc gọi chương trình ngoài vẫn cần được đánh giá như mã thực thi.

### 3.3. Không tải JAR trước khi xác minh

Mẫu thiếu kiểm soát:

```xml
<!-- Không bảo đảm nguồn gốc và tính toàn vẹn. -->
<get src="https://example.invalid/latest/tasks.jar"
     dest="build/tasks.jar"/>
<taskdef resource="org/example/build/antlib.xml"
         classpath="build/tasks.jar"/>
```

Ở đây đường dẫn `latest` có thể đổi theo thời gian; chưa có cơ chế bảo đảm byte JAR là bản đã được phê duyệt. HTTPS giúp bảo vệ kênh tải theo khả năng của TLS, nhưng **không tự chứng minh nội dung JAR được nhà phát triển dự án phê duyệt**.

Thứ tự an toàn hơn:

1. Xác định một **phiên bản bất biến** từ nguồn cung cấp đã được phê duyệt.
2. Lấy artifact qua cơ chế quản lý dependency của tổ chức hoặc kho được kiểm soát.
3. Xác minh digest SHA-256/chữ ký theo **giá trị tin cậy đã chốt độc lập**.
4. Chỉ sau đó mới đăng ký task bằng `<taskdef>` hay `<typedef>`.
5. Giữ file đã xác minh ở nơi không thể bị một bước kém tin cậy thay thế trước lúc nạp.

Ví dụ Ant tính digest và từ chối JAR không khớp:

```xml
<project name="verified-antlib" default="load-extension"
         basedir=".">

    <property name="extension.jar"
              location="vendor/example-build-antlib-1.2.3.jar"/>

    <target name="verify-extension">
        <!-- Giá trị này phải đến từ cấu hình/phát hành tin cậy
             và được CI kiểm soát, không lấy từ chính JAR vừa tải. -->
        <fail unless="approved.extension.sha256"
              message="Chưa cung cấp SHA-256 của antlib được phê duyệt"/>

        <available file="${extension.jar}"
                   type="file"
                   property="extension.exists"/>
        <fail unless="extension.exists"
              message="Thiếu JAR antlib đã chốt"/>

        <checksum file="${extension.jar}"
                  algorithm="SHA-256"
                  property="extension.actual.sha256"/>

        <condition property="extension.hash.matches">
            <equals arg1="${extension.actual.sha256}"
                    arg2="${approved.extension.sha256}"
                    casesensitive="false"/>
        </condition>
        <fail unless="extension.hash.matches"
              message="SHA-256 antlib không khớp bản đã phê duyệt"/>
    </target>

    <target name="load-extension" depends="verify-extension">
        <taskdef uri="antlib:org.example.build"
                 resource="org/example/build/antlib.xml"
                 classpath="${extension.jar}"/>
        <echo message="Đã đăng ký antlib từ JAR được xác minh"/>
    </target>
</project>
```

Để dùng ví dụ, CI phải cung cấp `approved.extension.sha256` từ **nguồn do nhóm sở hữu build kiểm soát**. Trong build thực tế, giá trị này có thể nằm trong lockfile/manifest phát hành đã review cùng repository tin cậy. Đừng tải file `.sha256` từ cùng URL tùy biến rồi mặc nhiên xem là nguồn chuẩn độc lập. Việc so hash giúp kiểm tra **tính toàn vẹn so với digest đã chốt**; nó không tự chứng minh nhà cung cấp thư viện là an toàn.

**Giới hạn quan trọng:** Nếu một người có thể sửa toàn bộ `build.xml` và đồng thời điều khiển job chạy nó, họ có thể loại bỏ đoạn xác minh ở trên. Vì vậy bước kiểm tra nội bộ này chỉ phát huy vai trò khi build script và nguồn digest thuộc phần đã tin cậy; với PR không tin cậy, còn cần cách ly bằng CI.

## 4. Ranh giới thứ ba: `<exec>` và chương trình ngoài

### 4.1. Process con dùng quyền nào?

Task `<exec>` tạo một process hệ điều hành:

```xml
<exec executable="git"
      dir="${basedir}"
      failonerror="true">
    <arg value="--version"/>
</exec>
```

Process con thường chạy dưới **cùng tài khoản hệ điều hành** với process Ant, kế thừa môi trường theo cấu hình `<exec>` và có thể truy cập những tài nguyên mà tài khoản đó được cho phép. `osfamily="unix"`, `timeout` hoặc việc đặt executable trong một biến không phải giới hạn quyền bảo mật.

Trước khi gọi executable trong build có quyền phát hành, cần xác định:

- **Binary nào sẽ chạy?** Có đường dẫn cụ thể hay chỉ tên được tìm trên PATH?
- **Nguồn binary có tin cậy không?** Nó được cài sẵn trong image được quản lý, tải từ kho có digest hay có thể bị một bước build thay thế?
- **Chương trình nhận input nào?** File/argument có đến từ PR, user input hoặc metadata bên ngoài không?
- **Chương trình có quyền nào?** Nó có thể đọc secrets, gọi mạng, thay artifact, ghi ra thư mục phát hành không?
- **Hệ thống xác định thành công ra sao?** Exit code, file kết quả, signature và tiêu chí kiểm tra artifact là gì?

### 4.2. PATH là một phần của ranh giới

```xml
<exec executable="converter"
      failonerror="true">
    <arg value="--version"/>
</exec>
```

Lệnh này dựa vào cách Java/OS tìm executable. Nếu `PATH` khác giữa máy dev và CI, Ant có thể dùng công cụ khác phiên bản hoặc khác hẳn chương trình dự kiến. Rủi ro tăng nếu thư mục ưu tiên trong PATH có thể được ghi bởi nội dung không tin cậy.

Với bước nhạy cảm, tốt hơn là để **CI đáng tin xác định path của công cụ đã phê duyệt**, giữ nó trong thư mục không thể bị workspace chưa tin cậy sửa, rồi truyền path đó cho Ant. Chỉ chấp nhận cấu hình thay executable từ nguồn quản trị tin cậy; không nên để một input PR tùy ý quyết định file nào sẽ chạy trong job có quyền cao.

Xác minh bằng `<available type="file">` chỉ cho biết file tồn tại; `--version` xác minh khả năng khởi chạy ở mức cơ bản; **digest hoặc chữ ký đáng tin** mới kiểm tra nội dung binary so với bản đã chốt. Các lớp xác minh giải quyết những câu hỏi khác nhau.

### 4.3. Tham số tách biệt với chuỗi shell

Mẫu dễ rủi ro khi tên file đến từ nguồn không tin cậy:

```xml
<!-- Shell sẽ diễn giải một chuỗi có nội suy. -->
<exec executable="sh"
      failonerror="true">
    <arg value="-c"/>
    <arg value="converter --input ${input.from.user}"/>
</exec>
```

Lúc này ký tự đặc biệt do nguồn đầu vào đưa vào có thể được shell diễn giải thành cú pháp điều khiển. Quoting và escaping khác nhau giữa `sh`, `bash`, `cmd.exe` và PowerShell.

Khi công cụ có executable độc lập, truyền danh sách đối số thay vì ghép một chuỗi lệnh:

```xml
<exec executable="${converter.executable}"
      dir="${basedir}"
      failifexecutionfails="true"
      failonerror="true">
    <arg value="--input"/>
    <arg file="${input.file}"/>
    <arg value="--output"/>
    <arg file="${output.file}"/>
</exec>
```

`<arg file>` giúp Ant truyền path một cách nhất quán; `<arg value>` tạo đúng một argument. Không có shell sẽ giảm nguy cơ metacharacter bị thông dịch, nhưng **không có nghĩa đầu vào đã an toàn cho chính chương trình được gọi**. Một công cụ vẫn có thể hiểu giá trị bắt đầu bằng `-` là option, theo symlink ra khỏi workspace hoặc đọc một file nhạy cảm được chỉ định. Vẫn cần kiểm soát loại file, đường dẫn cho phép và quyền của process.

`<arg line="...">` có quy tắc tách chuỗi riêng; tránh đưa một chuỗi động chứa nhiều argument vào đây khi muốn bảo đảm ranh giới mỗi argument rõ ràng. Với `cmd.exe /c` hoặc `sh -c`, hãy coi cả chuỗi sau `-c` như mã shell có khả năng thực thi.

### 4.4. Kế thừa môi trường và secrets

`<exec>` có thể truyền biến môi trường cho process con qua `<env>`; thông thường nó kế thừa môi trường của Ant. Thuộc tính `newenvironment="true"` có thể thay đổi việc kế thừa khi cung cấp biến môi trường mới, nhưng **không phải sandbox an ninh**: process vẫn thuộc tài khoản có quyền truy cập file và tài nguyên tương ứng.

Ví dụ cấu hình biến không nhạy cảm:

```xml
<exec executable="${converter.executable}"
      failonerror="true">
    <env key="LC_ALL" value="C"/>
    <arg value="--version"/>
</exec>
```

Không in token hoặc private key bằng `<echo>` để kiểm tra giá trị; không gắn secret vào tên file, artifact, tham số command hoặc log nếu có phương án truyền an toàn hơn. Trong nhiều hệ thống, đối số dòng lệnh có thể lộ qua process listing/log. Dù CI có cơ chế che chuỗi bí mật khỏi log, điều đó **không ngăn mã đang chạy đọc secret rồi gửi đến nơi khác**. Cơ chế bảo vệ hiệu quả nhất là không cấp secret cho một build chưa đáng tin.

### 4.5. Fail rõ ràng nếu công cụ bắt buộc bị lỗi

Task `<exec>` mặc định **không fail toàn bộ build chỉ vì process trả exit code khác 0**, trừ khi đặt `failonerror="true"`. Phải phân biệt lỗi **không khởi chạy được** với lỗi **đã chạy nhưng exit khác 0**:

```xml
<!-- Trong bước làm việc thật: thiếu process hoặc exit != 0
     đều phải dừng build. -->
<exec executable="${converter.executable}"
      dir="${basedir}"
      failifexecutionfails="true"
      failonerror="true"
      timeout="30000">
    <arg value="--version"/>
</exec>
```

Với bước thăm dò trước khi quyết định có dùng tool không, có thể đặt `failifexecutionfails="false"`, `failonerror="false"` và dùng `resultproperty` để tự xử lý. Nhưng nếu công cụ là điều kiện bắt buộc của bản phát hành, không thể âm thầm bỏ qua khi nó vắng mặt.

## 5. Mô hình thực hành: kiểm tra binary trước khi giao công việc

Ví dụ bên dưới giả sử có một công cụ chuyển đổi được phê duyệt tại `tools/converter`, nhận cú pháp `--version` và `--input PATH --output PATH`. Đây là **CLI giả định để minh họa cơ chế Ant**: khi áp dụng, cần thay đúng binary, checksum và giao diện tham số của công cụ thật.

File `build.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="verified-external-tool"
         default="convert"
         basedir=".">

    <!-- Đường dẫn nội bộ do dự án/CI tin cậy kiểm soát. -->
    <property name="tool.file" location="tools/converter"/>
    <property name="input.file" location="input/data.txt"/>
    <property name="output.file" location="build/result.txt"/>

    <target name="verify-tool">
        <!-- Digest kỳ vọng phải do policy CI hoặc config
             đã phê duyệt cung cấp; không lấy từ tool. -->
        <fail unless="approved.tool.sha256"
              message="Thiếu SHA-256 của executable được duyệt"/>

        <available file="${tool.file}"
                   type="file"
                   property="tool.file.exists"/>
        <fail unless="tool.file.exists"
              message="Không tìm thấy executable đã cấu hình"/>

        <!-- So sánh byte với bản đã được phê duyệt. -->
        <checksum file="${tool.file}"
                  algorithm="SHA-256"
                  property="tool.sha256.actual"/>

        <condition property="tool.sha256.matches">
            <equals arg1="${tool.sha256.actual}"
                    arg2="${approved.tool.sha256}"
                    casesensitive="false"/>
        </condition>
        <fail unless="tool.sha256.matches"
              message="Executable không khớp digest tin cậy"/>

        <!-- Khởi chạy thử lệnh không có tác dụng phụ.
             Cho phép lấy kết quả để báo lỗi chính xác. -->
        <exec executable="${tool.file}"
              dir="${basedir}"
              failifexecutionfails="false"
              failonerror="false"
              resultproperty="tool.probe.exit"
              timeout="10000">
            <arg value="--version"/>
        </exec>

        <condition property="tool.probe.ok">
            <equals arg1="${tool.probe.exit}" arg2="0"/>
        </condition>
        <fail unless="tool.probe.ok"
              message="Công cụ không khởi chạy hoặc --version bị lỗi"/>
    </target>

    <target name="convert" depends="verify-tool">
        <available file="${input.file}"
                   type="file"
                   property="input.exists"/>
        <fail unless="input.exists"
              message="Thiếu dữ liệu đầu vào"/>

        <mkdir dir="build"/>

        <exec executable="${tool.file}"
              dir="${basedir}"
              failifexecutionfails="true"
              failonerror="true"
              timeout="30000">
            <arg value="--input"/>
            <arg file="${input.file}"/>
            <arg value="--output"/>
            <arg file="${output.file}"/>
        </exec>

        <available file="${output.file}"
                   type="file"
                   property="result.exists"/>
        <fail unless="result.exists"
              message="Công cụ thoát thành công nhưng không tạo output"/>
    </target>
</project>
```

Ví dụ có ba cổng kiểm soát:

| Cổng | Kiểm tra | Phạm vi bảo đảm |
| --- | --- | --- |
| `available` | Có file executable ở path đã chốt | Chỉ sự tồn tại/loại file |
| `checksum` + digest đáng tin | Byte binary đúng bản đã phê duyệt | Tính toàn vẹn so với digest |
| `exec --version` + exit code | Binary có thể khởi chạy cơ bản | Khả năng thực thi, không bảo đảm mọi chức năng |
| `exec` thực thi chính + output | Công việc kết thúc thành công và có file | Kết quả theo tiêu chí tối thiểu |

Bước `convert` còn cần kiểm tra **định dạng/nội dung của `result.txt`** nếu đó là output bảo mật hoặc artifact phát hành. Một file có tồn tại chưa chứng minh nội dung đúng. Để tránh nhầm output cũ, cần dọn hoặc tạo output mới trong một thư mục sạch/riêng trước khi chạy. Nếu cần bảo đảm tính nguyên tử, có thể sinh output trong vùng tạm rồi chỉ chuyển vào artifact cuối sau khi xác minh.

**Điều kiện quan trọng:** Ngay cả khi ví dụ có hash check, một người kiểm soát `build.xml` vẫn có thể bỏ qua target này. Do đó hash check **không thay thế** việc chạy script đáng tin và hạn chế quyền của runner.

## 6. Đâu là đầu vào không tin cậy khi gọi Ant?

### 6.1. Property và tham số command line

Ant cho phép truyền property bằng `-D`:

```bash
ant -Dinput.file=input/data.txt convert
```

Nếu một job nhận đường dẫn này từ PR hoặc request bên ngoài, cần coi nó là **dữ liệu chưa được xác thực**. Ant property thường bất biến sau lần gán đầu tiên, nên một `-D` có thể tác động mạnh hơn giá trị mặc định trong `build.xml`.

Rủi ro tăng nếu property được dùng cho:

- `<delete dir="${cleanup.dir}"/>`: có thể xóa nhầm ngoài workspace.
- `<exec executable="${tool.executable}">`: có thể chọn binary khác.
- `<import file="${common.file}"/>`: có thể thay mã build được nạp.
- `<copy todir="${publish.dir}">`: có thể ghi vào đích không mong muốn.
- Chuỗi lệnh truyền cho `sh -c` hoặc `cmd /c`: có thể bị thông dịch như cú pháp shell.

Đừng coi `<property location="...">` là kiểm tra “nằm trong workspace”. Nó có thể chuẩn hóa/giải đường dẫn tương đối thành đường dẫn tuyệt đối nhưng **không bảo đảm đường dẫn được cho phép**, đặc biệt khi có `..` hoặc symlink. Nếu cho phép input điều khiển đường dẫn nhạy cảm, cần bước xác thực canonical path, allowlist các thư mục đích và kiểm soát symlink ở lớp đáng tin.

### 6.2. File và URL tải ngoài

Nguồn không tin cậy có thể là:

- File đã tải qua `<get>` từ một URL do input quyết định.
- JAR được resolve từ kho không có chính sách tính toàn vẹn.
- Script hoặc binary được trích xuất từ archive có thể bị thay đổi.
- Tài liệu/XML/config được custom task phân tích với quyền file và mạng của runner.
- Artifact do job CI khác tạo nhưng chưa có thông tin nguồn gốc đáng tin.
- Cache dùng chung giữa công việc đáng tin và không đáng tin.

Có file “đã nằm trong workspace” không có nghĩa file đó đáng tin: workspace có thể chứa code của PR, cache được ghi từ công việc khác, hoặc resource được sinh từ input bên ngoài.

### 6.3. Biến môi trường và tên tool

`<property environment="env"/>` cho phép Ant nạp biến môi trường thành property. Biến này có thể là đường dẫn cấu hình hợp lệ, nhưng cũng có thể chịu tác động của runner, IDE hoặc script gọi Ant.

Nếu người dùng chỉ sửa được một giá trị trên CI, ví dụ `TOOL_HOME`, giá trị đó có thể làm thay đổi executable được tìm thấy. Cần xác định xem đây là **input dữ liệu** hay **quyết định bảo mật**; những quyết định như nguồn binary, nơi xuất bản và quyền sign phải được kiểm soát bởi cấu hình đáng tin.

## 7. Thiết kế phân quyền trong CI theo mức độ tin cậy

Cùng một repository thường có các luồng thực thi khác nhau:

| Luồng | Mức tin cậy của mã chạy | Quyền được cấp phù hợp |
| --- | --- | --- |
| Build từ PR chưa review | Không đáng tin, dù PR ở cùng repository | Runner tách biệt, token tối thiểu, không secrets phát hành |
| Build kiểm thử từ nhánh đã được kiểm soát | Cao hơn sau review | Quyền cần thiết để test, tránh quyền xuất bản nếu chưa cần |
| Build phát hành từ revision/tag đã phê duyệt | Mã và cấu hình đáng tin theo chính sách release | Chỉ secrets, quyền ghi và toolchain thực sự cần |
| Job ký số hoặc publish | Đặc biệt nhạy cảm | Môi trường tách biệt, input artifact được xác minh, quyền ngắn hạn |

Một flow có thể tổ chức như sau:

```text
Pull request từ nguồn chưa phê duyệt
            |
            v
     CI test cô lập
  quyền read-only / không secret
            |
      review + merge
            |
            v
  checkout revision tin cậy
            |
            v
   pin Ant/JDK + dependency
   xác minh antlib và binary
            |
            v
    build + kiểm tra artifact
            |
            v
    release/sign/publish job
  secrets và quyền cấp tối thiểu
```

Các nguyên tắc thực thi:

1. **Không chạy bản build chưa review với credential phát hành.** Nếu job phải chạy code của PR, cô lập runner, không cung cấp khóa ký số/token xuất bản và hạn chế egress khi chính sách cho phép.
2. **Không coi tên sự kiện CI là bằng chứng code đáng tin.** Xác định revision thực tế được checkout và những file từ PR có được thực thi trong job có quyền hay không.
3. **Tách test khỏi publish.** Một job có thể kiểm thử nội dung kém tin cậy mà không cần quyền đẩy artifact. Chỉ cho phép workflow phát hành đã phê duyệt tiếp cận secrets.
4. **Giới hạn token và tài khoản chạy.** Chỉ cấp quyền đọc/ghi cho đúng repository, registry hoặc đích cần dùng; ưu tiên credential ngắn hạn.
5. **Giữ ranh giới cache/artifact rõ ràng.** Không cho dữ liệu từ job không đáng tin ghi đè JAR/tool được job tin cậy sau này nạp.
6. **Đừng giao kiểm soát chính sách cho chính `build.xml` không đáng tin.** Những điều kiện cho phép cấp secrets, runner và nguồn JAR phải nằm trong CI/hạ tầng tin cậy.

Nếu dùng một runner tự quản lý có nhiều repo hoặc nhiều job truy cập, cần xem xét dữ liệu còn lại trên đĩa, process và credential giữa các lần chạy. Runner tạm thời, tách biệt và cấp quyền tối thiểu giúp giảm phạm vi ảnh hưởng khi một build file xấu được thực thi.

## 8. So sánh ba ranh giới: kiểm tra gì trước khi tin?

| Câu hỏi | `build.xml` / imports | `antlib` / JAR | External tool |
| --- | --- | --- | --- |
| Đây là loại gì? | Mã điều khiển build | Mã Java/task mở rộng | Chương trình/tiến trình ngoài |
| Ai có thể sửa? | Người có quyền với commit/PR/build config | Publisher, repo, cache, người sửa JAR | Nhà cung cấp, image, PATH, filesystem |
| Chạy ở đâu? | Trong project Ant và các task gọi | Thường trong JVM Ant khi custom task chạy | Process con theo hệ điều hành |
| Dùng quyền nào? | Quyền của Ant hoặc process/task được gọi | Quyền của JVM Ant | Quyền tài khoản chạy process |
| Phép xác minh chủ yếu | Revision đã duyệt; review import/call graph; CI gate | Version, nguồn, SHA-256/chữ ký, classpath | Path, nguồn, SHA-256, probe/version, exit/output |
| Điều kiện đủ để an toàn? | Không có phép kiểm bên trong XML tự đủ | Hash không chứng minh tác giả đáng tin | `--version`/file exists không chứng minh nội dung tin cậy |
| Kiểm soát quan trọng nhất | Quyền CI bên ngoài build file | Chỉ nạp binary đã chốt trong môi trường tin cậy | Chỉ chạy binary đã chốt với input và quyền phù hợp |

**Điểm then chốt:** “Đã xác minh” có nhiều nghĩa. `<available>` chứng minh có file; SHA-256 so với digest đã chốt chứng minh file không đổi; chữ ký hợp lệ có thể giúp xác minh nguồn ký theo mô hình tin cậy; kiểm tra version/chức năng chứng minh điều kiện kỹ thuật; review nguồn/nhà cung cấp và phân quyền runtime mới góp phần xác định có nên cấp quyền cho code đó.

Không có một phép kiểm nào đơn lẻ thay thế được toàn bộ các phép kiểm còn lại.

## 9. Sai lầm phổ biến

### 9.1. “build.xml là XML, nên có thể chạy để xem nó làm gì”

Sai về ranh giới: XML này là mô tả **hành động thực thi**. Có thể chứa `<exec>`, `<delete>`, `<taskdef>` và nhiều task khác. Xem nội dung bằng công cụ đọc file và review nguồn trước khi thực thi. Đặc biệt không chạy trên máy có khóa cá nhân, token registry hoặc tài nguyên quan trọng chỉ để khảo sát một dự án lạ.

### 9.2. “Đã chia target an toàn và nguy hiểm nên chỉ gọi target an toàn”

Chia target giúp tổ chức công việc, nhưng nếu file build hoặc custom task không đáng tin, người kiểm soát chúng vẫn có thể thay đổi dependency, top-level configuration hoặc logic mà target an toàn sử dụng. Cô lập quyền thực thi quan trọng hơn tên target.

### 9.3. “Antlib có namespace riêng nên được sandbox”

Namespace chỉ giúp phân biệt tên task. Class Java trong JAR không bị giới hạn quyền theo namespace. Dùng classpath tường minh giảm nhầm lẫn thư viện nhưng cũng không phải cơ chế bảo mật độc lập.

### 9.4. “Tải bằng HTTPS là đủ”

TLS bảo vệ kết nối đến máy chủ theo mô hình chứng chỉ, nhưng không tự xác nhận bạn đã tải **đúng phiên bản và đúng nội dung đã phê duyệt**. Cần pin nguồn/version và xác minh digest/chữ ký từ nguồn đáng tin.

### 9.5. “Tìm thấy file bằng available thì executable an toàn”

`<available>` không kiểm tra quyền chạy, phiên bản, chữ ký, hành vi hoặc nguồn gốc. Cần probe phù hợp và đối chiếu nội dung binary với bản phê duyệt khi mức rủi ro yêu cầu.

### 9.6. “Dùng arg value sẽ tự làm mọi input an toàn”

Tách argument giúp tránh một lớp lỗi thông dịch shell nếu gọi executable trực tiếp. Nhưng nếu chương trình nhận path ngoài vùng cho phép, file cấu hình chứa lệnh riêng của nó hoặc option gây thay đổi nguy hiểm, vấn đề vẫn còn. Kiểm soát input theo hợp đồng của công cụ.

### 9.7. “Build có failonerror=true là an toàn”

`failonerror="true"` giúp phát hiện exit code thất bại. Nó không giới hạn các hành động được process thực hiện trước khi thoát, không ngăn đọc secrets và không bảo đảm artifact có đúng nội dung.

### 9.8. “CI che log secrets là đã bảo vệ secrets”

Che log chỉ giúp tránh lộ theo một kênh. Build code vẫn có quyền đọc secret nếu secret đã được cấp vào job; cần ngăn việc cấp secret cho mã chưa tin cậy từ đầu.

## 10. Quy trình review trước khi chạy build Ant mới

Với một repository vừa nhận bàn giao hoặc PR chạm vào build, có thể đi theo quy trình sau:

1. **Xác định revision và người kiểm soát đầu vào.** Code đã review chưa, có nội dung từ fork/PR/cache không, có quyền gì ở runner?
2. **Đọc `build.xml` và chuỗi nạp file.** Xem target mặc định, `depends`, `import`, `include`, `ant`/`subant`, và các task ở cấp project có thể chạy khi cấu hình.
3. **Liệt kê nơi có tác dụng phụ.** Tìm `exec`, `apply`, `java`, `taskdef`, `typedef`, `get`, `delete`, `copy` đến đích nhạy cảm và plugin được nạp.
4. **Ghi nguồn của từng antlib/binary.** Artifact nào, publisher nào, phiên bản nào, checksum/chữ ký nào, có thể bị cache hoặc workspace ghi đè không?
5. **Kiểm soát dữ liệu điều khiển.** Các `-D`, environment variables, URL, tên script, path và input từ user có được phép thay executable hoặc đích ghi không?
6. **Xác định môi trường thực thi.** Process Ant có những quyền file, mạng, registry, secret nào? Có thể giảm quyền hoặc chuyển sang runner cô lập không?
7. **Chọn phép xác minh thích hợp.** File tồn tại, hash, version/probe, exit code, artifact mới và nội dung đầu ra.
8. **Đưa quyền phát hành ra khỏi phạm vi không tin cậy.** Xác nhận chỉ job/revision đã duyệt mới có signing key hoặc credential publish.

Quy trình này là tư duy review tổng thể, không phải “bật một flag bảo mật cho Ant”. Khi phát hiện một rủi ro, sửa ở **đúng ranh giới**: input thuộc bên ngoài thì policy CI kiểm soát; antlib thuộc dependency thì xác thực/pin artifact; executable thuộc toolchain thì xác minh binary và giới hạn process; việc ghi file thuộc build script thì giới hạn đích và quyền.

## 11. Bài thực hành

### Bài 1 — Vẽ ranh giới cho một build

Cho luồng sau: CI checkout một PR, chạy `ant package`; `build.xml` import `build/common.xml`; `common.xml` nạp `vendor/tasks.jar`; custom task gọi một script ngoài để tạo artifact.

Hãy trả lời:

1. Những file nào được xem là mã điều khiển build?
2. Có bao nhiêu điểm tải/chạy mã ngoài Ant core?
3. Ai có thể chỉnh sửa JAR, script và cấu hình `-D`?
4. Nếu runner có token ghi registry, rủi ro lớn nhất thuộc lớp nào?
5. Cần đặt kiểm soát nào **ngoài `build.xml`** để mã PR không nhận quyền phát hành?

### Bài 2 — Phân biệt kiểm tra tồn tại và kiểm tra tin cậy

Trong môi trường thực hành không có secret, tạo một file giả `vendor/demo-antlib.jar` và dùng `<available>` để xác nhận tồn tại. Tiếp theo, dùng `<checksum algorithm="SHA-256">` lấy digest. Thay đổi một byte của file rồi chạy lại kiểm tra để quan sát hash khác. Giải thích vì sao hash khớp với digest **do chính file đó cung cấp** không phải bằng chứng nguồn đáng tin.

Không nạp file giả làm antlib: bài này chỉ thực hành kiểm tra file và digest.

### Bài 3 — Nhận diện đầu vào nguy hiểm

Xem cấu hình:

```xml
<target name="clean-selected">
    <delete dir="${target.dir}"/>
</target>

<target name="run-helper">
    <exec executable="${helper.path}">
        <arg line="${helper.args}"/>
    </exec>
</target>
```

Giả sử cả ba property đều đến từ một request bên ngoài. Hãy chỉ ra đầu vào nào có thể đổi đích xóa, đổi executable, làm biến đổi argument; đề xuất cách giới hạn path/allowlist và tách argument. Thảo luận vì sao không nên chạy một target như vậy trong job có quyền rộng.

### Bài 4 — Thiết kế pipeline ba cấp quyền

Với một dự án cần chạy unit test, đóng JAR rồi ký số, thiết kế ba job: **PR test**, **trusted build**, **sign/publish**. Xác định code được phép chạy, toolchain cần pin, artifact đầu vào/đầu ra, quyền token và nơi cấp signing key. Giải thích một job PR thất bại hoặc bị sửa ác ý sẽ bị chặn ở ranh giới nào.

### Bài 5 — Thử lỗi công cụ ngoài an toàn

Trong một thư mục luyện tập không có secrets, dùng lệnh probe `--version` của một công cụ được cài sẵn. Thử một tên executable không tồn tại để quan sát lỗi khởi chạy; sau đó tạo một script thử nghiệm chỉ trả exit code khác 0, gọi bằng `<exec resultproperty="..." failonerror="false">` để đọc mã. Cuối cùng bật `failonerror="true"` cho bước bắt buộc và giải thích kết quả.

## Tài liệu tham khảo

- Apache Ant — [Manual: Concepts and Tasks](https://ant.apache.org/manual/index.html): mô hình project, target, task, property.
- Apache Ant — [Antlib](https://ant.apache.org/manual/Types/antlib.html): antlib file, các kiểu định nghĩa, namespace, cách nạp từ JAR.
- Apache Ant — [Taskdef](https://ant.apache.org/manual/Tasks/taskdef.html) và [Typedef](https://ant.apache.org/manual/Tasks/typedef.html): đăng ký custom Java task/type.
- Apache Ant — [Exec](https://ant.apache.org/manual/Tasks/exec.html): executable, arguments, environment, lỗi khởi chạy, mã thoát.
- Apache Ant — [Java](https://ant.apache.org/manual/Tasks/java.html): chạy Java trong hoặc ngoài JVM Ant.
- Apache Ant — [Checksum](https://ant.apache.org/manual/Tasks/checksum.html) và [Available](https://ant.apache.org/manual/Tasks/available.html): kiểm tra hash và tồn tại file.
- Apache Ant — [Import](https://ant.apache.org/manual/Tasks/import.html), [Include](https://ant.apache.org/manual/Tasks/include.html) và [Subant](https://ant.apache.org/manual/Tasks/subant.html): nạp build file/target phụ.
- Reproducible Builds — [Build dependencies](https://reproducible-builds.org/docs/recording/): ghi nhận nguồn đầu vào, toolchain và khả năng tái lập.

**Nguyên tắc cần nhớ:** Một `build.xml` chưa phê duyệt phải được đối xử như **mã có thể thực thi**; một `antlib` phải được đối xử như **thư viện Java có thể thực thi trong build**; một executable ngoài phải được đối xử như **chương trình có quyền của môi trường chạy nó**. Chỉ nạp và chạy các thành phần đã xác định nguồn, giới hạn quyền của CI trước khi chạy và kiểm tra kết quả tại từng ranh giới. Các biện pháp kiểm tra đặt *bên trong* một build file không đáng tin không thể thay thế sự cô lập và phê duyệt từ hạ tầng bên ngoài.

