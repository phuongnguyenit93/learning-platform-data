# Thiết lập executable, dir, environment và điều kiện hệ điều hành

Apache Ant thường được dùng để biên dịch, kiểm thử và đóng gói Java, nhưng một quy trình build còn có thể cần gọi chương trình bên ngoài: Git, Docker, một script triển khai, công cụ sinh mã hoặc một CLI chuyên dụng. Task `<exec>` cho phép Ant khởi chạy tiến trình ngoài và truyền cho tiến trình đó lệnh, thư mục làm việc, biến môi trường cùng các đối số.

Khi build chạy trên nhiều máy hoặc nhiều hệ điều hành, bốn phần cấu hình cần được hiểu rõ:

- `executable`: chương trình hoặc script cần chạy.
- `dir`: thư mục làm việc hiện tại của tiến trình con.
- `env` và `newenvironment`: các biến môi trường được truyền cho tiến trình.
- `os` hoặc điều kiện `<os>`: giới hạn lệnh theo hệ điều hành hiện tại.

Thiết lập đúng những phần này giúp build không phụ thuộc ngầm vào thư mục terminal, PATH hay cấu hình riêng của một máy phát triển.

## 1. Cấu trúc cơ bản của task exec

Ví dụ gọi Git để lấy phiên bản:

```xml
<target name="show-git-version">
    <exec executable="git" failonerror="true">
        <arg value="--version"/>
    </exec>
</target>
```

Task `<exec>` khởi chạy chương trình `git` với đối số `--version`. `failonerror="true"` yêu cầu Ant làm build thất bại nếu chương trình trả mã thoát khác 0.

Một lệnh gọi đầy đủ có thể có dạng:

```xml
<exec executable="tools/release-checker"
      dir="${basedir}"
      failonerror="true"
      timeout="60000">
    <arg value="--artifact"/>
    <arg file="${basedir}/dist/app.jar"/>
    <arg value="--mode"/>
    <arg value="verify"/>
</exec>
```

Trong ví dụ, Ant chạy executable trong thư mục project, truyền đường dẫn artifact và chế độ kiểm tra, đồng thời đặt timeout 60 giây. Đối số được khai báo thành từng phần tử riêng để giữ đúng ranh giới token, kể cả khi đường dẫn có dấu cách.

## 2. Thiết lập executable

Thuộc tính `executable` chỉ định tên lệnh hoặc đường dẫn đến chương trình cần khởi chạy. Ví dụ:

```xml
<exec executable="java" failonerror="true">
    <arg value="-version"/>
</exec>

<exec executable="git" failonerror="true">
    <arg value="status"/>
    <arg value="--short"/>
</exec>
```

Nếu chương trình đã nằm trong `PATH` của môi trường chạy Ant, có thể dùng tên lệnh như `java`, `git` hoặc `docker`. Nếu chương trình nằm ở vị trí riêng của dự án, có thể chỉ định đường dẫn:

```xml
<property name="tool.dir" location="${basedir}/tools"/>

<exec executable="${tool.dir}/release-checker.exe"
      dir="${basedir}"
      failonerror="true">
    <arg value="--check"/>
</exec>
```

Đường dẫn executable có thể khác nhau giữa Windows, Linux và macOS. Khi dự án cung cấp script theo từng nền tảng, nên đặt đường dẫn trong property riêng và chọn target phù hợp với hệ điều hành.

Không ghép cả câu lệnh và tham số vào `executable`. Chương trình cần chạy thuộc `executable`; các tham số của nó đặt trong `<arg>`. Điều này giúp Ant truyền đối số trực tiếp mà không phải dựa vào cách shell phân tích chuỗi.

## 3. Truyền đối số cho tiến trình con

Mỗi `<arg value="..."/>` biểu diễn một đối số. Ví dụ:

```xml
<exec executable="java" failonerror="true">
    <arg value="-jar"/>
    <arg file="${basedir}/tools/report-generator.jar"/>
    <arg value="--output"/>
    <arg file="${basedir}/build/reports"/>
</exec>
```

Task truyền bốn đối số riêng cho executable `java`. `file` phù hợp khi đối số là đường dẫn vì Ant xử lý nó như một giá trị đường dẫn, kể cả khi có khoảng trắng.

Một số thuộc tính thường dùng của nested `<arg>`:

| Thuộc tính | Công dụng |
|---|---|
| `value` | Truyền một đối số với giá trị đã chỉ định |
| `file` | Truyền đường dẫn file dưới dạng một đối số |
| `path` | Chuyển một path thành chuỗi theo dấu phân cách của nền tảng |
| `pathref` | Dùng một path đã khai báo bằng `id` |
| `line` | Phân tích một dòng thành nhiều đối số |

Ưu tiên `value` hoặc `file` cho từng token. `line` ngắn hơn nhưng cần chú ý quy tắc quote và tokenization. Không thêm dấu nháy kép chỉ để giữ một chuỗi có dấu cách khi đã dùng `value` hoặc `file`; Ant truyền mỗi phần tử `<arg>` như một đối số độc lập.

## 4. Thiết lập thư mục làm việc bằng dir

Thuộc tính `dir` xác định working directory (thư mục làm việc hiện tại) của tiến trình con. Các đường dẫn tương đối mà chương trình bên ngoài tự mở thường được tính từ thư mục này.

```xml
<exec executable="git"
      dir="${basedir}"
      failonerror="true">
    <arg value="status"/>
</exec>
```

Nếu bỏ `dir`, tiến trình thường kế thừa thư mục làm việc của Ant. Thư mục đó có thể khác nhau tùy cách build được gọi: terminal của IDE, CI runner hoặc một script cha. Để build dễ tái hiện, nên đặt `dir` rõ ràng.

### 4.1. dir không thay đổi basedir của Ant

`dir` chỉ thay đổi working directory của tiến trình được `<exec>` khởi chạy. Nó không thay đổi property `${basedir}` và cũng không thay đổi cách Ant phân giải các đường dẫn trong những task khác.

Ví dụ:

```xml
<property name="project.root" location="${basedir}"/>

<exec executable="git" dir="${basedir}/frontend" failonerror="true">
    <arg value="status"/>
</exec>

<echo message="Ant basedir remains ${project.root}"/>
```

Git chạy trong thư mục `frontend`, còn `project.root` vẫn trỏ đến project root của Ant. Hai khái niệm này độc lập.

### 4.2. Bảo đảm working directory tồn tại

Nếu thư mục làm việc được tạo trong build, hãy tạo nó trước khi gọi tiến trình:

```xml
<target name="prepare-tool-dir">
    <mkdir dir="build/tool-work"/>
</target>

<target name="run-tool" depends="prepare-tool-dir">
    <exec executable="java"
          dir="build/tool-work"
          failonerror="true">
        <arg value="-version"/>
    </exec>
</target>
```

Đường dẫn `dir` phải trỏ đến một thư mục hợp lệ và có thể truy cập. Nếu thư mục không tồn tại hoặc tiến trình không có quyền truy cập, Ant có thể không khởi chạy được command.

## 5. Thiết lập biến môi trường bằng env

Nested element `<env>` truyền biến môi trường cho tiến trình con. Ví dụ:

```xml
<exec executable="java"
      dir="${basedir}"
      failonerror="true">
    <env key="APP_ENV" value="production"/>
    <env key="APP_HOME" value="${basedir}"/>
    <arg value="-jar"/>
    <arg file="dist/app.jar"/>
</exec>
```

Trong tiến trình Java, có thể đọc các biến đó bằng:

```java
String environment = System.getenv("APP_ENV");
String appHome = System.getenv("APP_HOME");
```

Các thuộc tính thường dùng của `<env>`:

| Thuộc tính | Ý nghĩa |
|---|---|
| `key` | Tên biến môi trường |
| `value` | Giá trị dạng chuỗi |
| `path` | Giá trị dạng đường dẫn, được chuyển sang dấu phân cách phù hợp hệ điều hành |
| `file` | Giá trị lấy từ đường dẫn file |

Thông thường, dùng `key` cùng một trong các thuộc tính `value`, `path` hoặc `file`. `path` hữu ích cho biến như `PATH`, `CLASSPATH` hoặc biến chứa danh sách thư mục theo quy ước nền tảng.

Ví dụ đặt biến chứa đường dẫn:

```xml
<exec executable="java" dir="${basedir}" failonerror="true">
    <env key="APP_CONFIG_DIR" path="${basedir}/config"/>
    <arg value="-jar"/>
    <arg file="dist/app.jar"/>
</exec>
```

Giá trị `path` được Ant chuyển theo quy tắc phân cách path của hệ điều hành. Nếu chương trình cần một chuỗi đường dẫn thông thường chứ không phải path-list, dùng `value`.

## 6. Kế thừa môi trường và newenvironment

Theo mặc định, tiến trình con nhận môi trường kế thừa từ tiến trình Ant, sau đó các biến được khai báo trong `<env>` được bổ sung hoặc thay thế theo tên tương ứng.

```xml
<exec executable="java" dir="${basedir}" failonerror="true">
    <env key="APP_ENV" value="test"/>
    <arg value="-version"/>
</exec>
```

Nếu cần một môi trường hoàn toàn mới, có thể đặt `newenvironment="true"`:

```xml
<exec executable="java"
      dir="${basedir}"
      newenvironment="true"
      failonerror="true">
    <env key="APP_ENV" value="test"/>
    <env key="APP_HOME" value="${basedir}"/>
    <arg value="-version"/>
</exec>
```

Với `newenvironment="true"`, tiến trình chỉ nhận các biến môi trường được khai báo cho task. Các biến hệ thống có thể cần thiết như `PATH`, `SystemRoot`, `TEMP`, `HOME` hoặc biến định vị runtime có thể không còn sẵn có nếu không khai báo lại.

Vì vậy, chỉ bật `newenvironment="true"` khi thực sự muốn cô lập môi trường và đã xác định đầy đủ biến cần thiết. Với phần lớn build thông thường, giữ mặc định để kế thừa môi trường rồi ghi đè một số biến cần thiết sẽ đơn giản hơn.

## 7. Đọc biến môi trường hiện có vào Ant property

Nếu cần đọc giá trị môi trường hiện tại trong build file, có thể dùng task `<property environment="..."/>`:

```xml
<property environment="env"/>

<target name="show-environment">
    <echo message="PATH = ${env.PATH}"/>
    <echo message="JAVA_HOME = ${env.JAVA_HOME}"/>
</target>
```

Ant đưa các biến môi trường vào property với prefix đã chỉ định. Trong ví dụ, biến `PATH` trở thành `${env.PATH}`, còn `JAVA_HOME` trở thành `${env.JAVA_HOME}`.

Có thể dùng property này để cấu hình executable hoặc truyền lại cho tiến trình con:

```xml
<property environment="env"/>

<target name="show-java-home">
    <echo message="JAVA_HOME=${env.JAVA_HOME}"/>
    <exec executable="java" dir="${basedir}" failonerror="true">
        <arg value="-version"/>
    </exec>
</target>
```

Ví dụ trên gọi `java` qua PATH; nếu muốn gọi executable bên trong `JAVA_HOME`, hãy ghép đúng tên file theo nền tảng, chẳng hạn `bin/java` trên Unix-like hoặc `bin/java.exe` trên Windows.

Lưu ý tên biến môi trường có thể khác cách viết hoa/thường giữa hệ điều hành. Property Ant có phân biệt tên, vì vậy hãy dùng đúng tên đã được môi trường cung cấp. Nếu `JAVA_HOME` không được thiết lập, tham chiếu `${env.JAVA_HOME}` có thể không có giá trị; nên kiểm tra trước khi sử dụng.

## 8. Giới hạn lệnh theo hệ điều hành bằng thuộc tính os

Task `<exec>` có thuộc tính `os` để chỉ định danh sách tên hệ điều hành được phép chạy command. Danh sách được phân tách bằng dấu phẩy.

```xml
<exec executable="tools/windows-tool.exe"
      os="Windows 10,Windows 11"
      dir="${basedir}"
      failonerror="true">
    <arg value="--check"/>
</exec>
```

Nếu hệ điều hành hiện tại không khớp danh sách `os`, task bỏ qua việc chạy command. `os` phù hợp khi chỉ một lệnh duy nhất cần giới hạn theo tên OS.

Tuy nhiên, tên OS cụ thể có thể khác giữa phiên bản Windows hoặc JDK. Ví dụ, `os.name` trên máy Windows có thể được JVM báo là `Windows 10` kể cả trên một số phiên bản Windows mới hơn. Vì vậy, nếu mục tiêu là phân biệt nhóm hệ điều hành, kiểm tra theo `family` thường bền vững hơn.

## 9. Dùng điều kiện os để tạo target riêng cho từng nền tảng

Ant có điều kiện `<os>` để kiểm tra hệ điều hành theo family, name hoặc architecture. Có thể dùng `<condition>` để đặt property rồi điều khiển target bằng `if`/`unless`.

```xml
<condition property="os.windows">
    <os family="windows"/>
</condition>

<condition property="os.unix">
    <os family="unix"/>
</condition>

```

Sau đó định nghĩa target tương ứng:

```xml
<target name="run-windows-tool" if="os.windows">
    <exec executable="cmd.exe" dir="${basedir}" failonerror="true">
        <arg value="/c"/>
        <arg file="tools/run-windows.cmd"/>
        <arg value="--mode"/>
        <arg value="build"/>
    </exec>
</target>

<target name="run-unix-tool" if="os.unix">
    <exec executable="/bin/sh" dir="${basedir}" failonerror="true">
        <arg file="tools/run-unix.sh"/>
        <arg value="--mode"/>
        <arg value="build"/>
    </exec>
</target>

<target name="run-platform-tool"
        depends="run-windows,run-unix"/>
```

Mỗi target có điều kiện riêng. Target không phù hợp với hệ điều hành hiện tại sẽ bị bỏ qua; target phù hợp sẽ thực thi command tương ứng.

Điều kiện `if` của target kiểm tra property có tồn tại hay không. Trong ví dụ, `<condition>` chỉ đặt `os.windows` hoặc `os.unix` khi family phù hợp, nên target tương ứng được bật theo hệ điều hành.

## 10. Kiểm tra hệ điều hành và báo lỗi nếu không hỗ trợ

Nếu build chỉ hỗ trợ một số nền tảng nhất định, không nên để tất cả target bị bỏ qua rồi kết thúc như thành công. Có thể tạo property tổng hợp và dừng bằng `<fail>` khi hệ điều hành không nằm trong danh sách hỗ trợ.

```xml
<condition property="os.windows">
    <os family="windows"/>
</condition>

<condition property="os.unix">
    <os family="unix"/>
</condition>

<condition property="os.supported">
    <or>
        <isset property="os.windows"/>
        <isset property="os.unix"/>
    </or>
</condition>

<target name="validate-platform">
    <fail unless="os.supported"
          message="This build supports Windows and Unix-like operating systems only."/>
</target>
```

Đặt target nền tảng phụ thuộc vào `validate-platform` nếu các bước sau chỉ hợp lệ trên hệ điều hành được hỗ trợ.

Nếu cần kiểm tra cả kiến trúc CPU, điều kiện `<os>` có thể dùng `arch`, ví dụ `arch="amd64"` hoặc `arch="aarch64"`. Giá trị architecture là chuỗi do JVM báo về và có thể khác giữa nhà cung cấp JDK; hãy kiểm tra trên môi trường CI thực tế.

## 11. Kết hợp executable, dir, env và điều kiện OS

Ví dụ sau chọn script theo nền tảng, đặt thư mục làm việc và cung cấp cấu hình runtime:

```xml
<project name="external-tool-demo" default="run-tool" basedir=".">
    <property name="work.dir" location="${basedir}/build/tool-work"/>
    <property name="tool.mode" value="verify"/>

    <condition property="os.windows">
        <os family="windows"/>
    </condition>
    <condition property="os.unix">
        <os family="unix"/>
    </condition>

    <target name="prepare">
        <mkdir dir="${work.dir}"/>
    </target>

    <target name="validate-platform" depends="prepare">
        <condition property="os.supported">
            <or>
                <isset property="os.windows"/>
                <isset property="os.unix"/>
            </or>
        </condition>
        <fail unless="os.supported"
              message="No external-tool script is configured for this operating system."/>
    </target>

    <target name="run-windows" depends="validate-platform" if="os.windows">
        <exec executable="cmd.exe"
              dir="${work.dir}"
              failonerror="true"
              timeout="120000">
            <env key="APP_ENV" value="ci"/>
            <env key="APP_MODE" value="${tool.mode}"/>
            <arg value="/c"/>
            <arg file="${basedir}/tools/run-windows.cmd"/>
            <arg value="--input"/>
            <arg file="${basedir}/dist/app.jar"/>
        </exec>
    </target>

    <target name="run-unix" depends="validate-platform" if="os.unix">
        <exec executable="/bin/sh"
              dir="${work.dir}"
              failonerror="true"
              timeout="120000">
            <env key="APP_ENV" value="ci"/>
            <env key="APP_MODE" value="${tool.mode}"/>
            <arg file="${basedir}/tools/run-unix.sh"/>
            <arg value="--input"/>
            <arg file="${basedir}/dist/app.jar"/>
        </exec>
    </target>

    <target name="run-tool" depends="run-windows,run-unix">
        <echo message="External tool completed for ${tool.mode}."/>
    </target>
</project>
```

Trong ví dụ:

1. `prepare` tạo thư mục làm việc.
2. `validate-platform` xác nhận OS được hỗ trợ.
3. `run-windows` chỉ chạy trên Windows và dùng `cmd.exe /c` để gọi file `.cmd`.
4. `run-unix` chỉ chạy trên Unix-like OS và gọi script qua `/bin/sh`.
5. Cả hai nhánh đều chạy trong `${work.dir}` và nhận `APP_ENV`, `APP_MODE`.
6. `failonerror` và `timeout` bảo vệ build khi command lỗi hoặc chạy quá lâu.

Đường dẫn script và artifact cần tồn tại trước khi target chạy. Nếu script yêu cầu quyền thực thi trên Unix, có thể gọi qua `/bin/sh` như ví dụ hoặc cấp executable permission cho file trong repository.

## 12. Thu thập stdout, stderr và exit code

Tiến trình ngoài thường ghi kết quả ra stdout và diagnostics ra stderr. Ant có thể hiển thị hai luồng trong log hoặc ghi chúng vào file/property.

Ví dụ lưu output vào file:

```xml
<target name="capture-git-status">
    <mkdir dir="build"/>
    <exec executable="git"
      dir="${basedir}"
      output="build/git-status.txt"
      error="build/git-error.txt"
      failonerror="false"
      resultproperty="git.exit.code">
    <arg value="status"/>
    <arg value="--short"/>
</exec>

<echo message="Git exit code: ${git.exit.code}"/>
</target>
```

Các thuộc tính liên quan:

- `output`: file nhận stdout.
- `error`: file nhận stderr.
- `outputproperty`: property nhận stdout.
- `errorproperty`: property nhận stderr.
- `resultproperty`: property nhận mã thoát của tiến trình.
- `failonerror`: làm build thất bại nếu command trả mã khác 0.
- `timeout`: giới hạn thời gian chạy.

Nếu dùng `failonerror="false"`, cần kiểm tra `resultproperty` nếu mã thoát khác 0 vẫn phải được xem là lỗi. Ant property có tính bất biến, vì vậy nên dùng tên property riêng cho mỗi command cần kiểm tra trong cùng invocation.

Ví dụ dừng sau khi kiểm tra mã thoát:

```xml
<exec executable="tools/validator"
      dir="${basedir}"
      failonerror="false"
      resultproperty="validator.exit.code">
    <arg value="dist/app.jar"/>
</exec>

<condition property="validator.succeeded">
    <equals arg1="${validator.exit.code}" arg2="0"/>
</condition>

<fail unless="validator.succeeded"
      message="External validation failed with exit code ${validator.exit.code}."/>
```

Không dựa vào nội dung stdout để quyết định thành công nếu command đã cung cấp exit code rõ ràng. Quy ước phổ biến của tiến trình là `0` biểu thị thành công và giá trị khác `0` biểu thị lỗi.

## 13. Shell, script và sự khác biệt giữa các hệ điều hành

Task `<exec>` khởi chạy executable trực tiếp; nó không tự xử lý các toán tử shell như `>`, `|`, `&&`, wildcard hoặc biến `$NAME` như một shell tương tác.

Ví dụ sau không phải cách chuyển hướng output đáng tin cậy:

```xml
<exec executable="java">
    <arg value="-version"/>
    <arg value="&gt;"/>
    <arg value="version.txt"/>
</exec>
```

Ở đây `>` được truyền như một đối số cho chương trình Java, không phải lệnh chuyển hướng của shell.

Nếu cần shell syntax, hãy gọi shell tường minh. Trên Windows:

```xml
<exec executable="cmd.exe" dir="${basedir}" failonerror="true">
    <arg value="/c"/>
    <arg value="echo build started &gt; build-status.txt"/>
</exec>
```

Trên Unix-like:

```xml
<exec executable="/bin/sh" dir="${basedir}" failonerror="true">
    <arg value="-c"/>
    <arg value="echo build started &gt; build-status.txt"/>
</exec>
```

Chỉ dùng shell khi thực sự cần cú pháp shell. Khi có thể, hãy dùng `output`, `error` và các `<arg>` trực tiếp của Ant; cách đó ít phụ thuộc môi trường hơn và tránh phải xử lý quote phức tạp.

### 13.1. Gọi file batch trên Windows

File `.bat` hoặc `.cmd` cần được chạy qua command interpreter. Ví dụ:

```xml
<exec executable="cmd.exe" dir="${basedir}" failonerror="true">
    <arg value="/c"/>
    <arg file="tools/build-native.cmd"/>
    <arg value="Release"/>
</exec>
```

`/c` yêu cầu `cmd.exe` chạy lệnh được truyền rồi thoát. Dùng `<arg>` riêng để giữ đúng đối số của script.

### 13.2. Gọi shell script trên Unix-like

```xml
<exec executable="/bin/sh" dir="${basedir}" failonerror="true">
    <arg file="tools/build-native.sh"/>
    <arg value="Release"/>
</exec>
```

Gọi qua `/bin/sh` không yêu cầu script có executable bit, nhưng script phải tương thích với shell đó. Nếu script yêu cầu Bash, hãy gọi `/bin/bash` thay vì giả định `/bin/sh` hỗ trợ mọi cú pháp Bash.

## 14. PATH và cách tìm executable

Khi `executable` chỉ là tên lệnh như `git`, Ant và hệ điều hành cần tìm được chương trình trong môi trường thực thi. Nếu CI không có PATH như máy cá nhân, command có thể không được tìm thấy.

Có thể kiểm tra môi trường:

```xml
<property environment="env"/>

<target name="show-path">
    <echo message="PATH=${env.PATH}"/>
    <echo message="JAVA_HOME=${env.JAVA_HOME}"/>
</target>
```

Một số phiên bản/cấu hình Ant cung cấp các thuộc tính `resolveexecutable` và `searchpath` để kiểm soát việc phân giải executable tương đối hoặc tìm executable trên PATH. Khi dùng chúng, hãy đọc đúng tài liệu phiên bản Ant của dự án và kiểm tra hành vi trên CI.

Đối với công cụ quan trọng của release, cách dễ dự đoán nhất thường là cung cấp đường dẫn đã được cấu hình rõ ràng hoặc kiểm tra trước rằng executable tồn tại. Không hard-code đường dẫn cá nhân như `C:/Users/...` vào build file dùng chung.

## 15. Kiểm tra executable trước khi gọi

Có thể dùng `<available>` để kiểm tra một file executable tại đường dẫn đã biết:

```xml
<property name="tool.path" location="${basedir}/tools/release-checker.exe"/>

<target name="validate-tool">
    <available file="${tool.path}"
               type="file"
               property="tool.exists"/>
    <fail unless="tool.exists"
          message="Required tool was not found at ${tool.path}."/>
</target>

<target name="run-checker" depends="validate-tool">
    <exec executable="${tool.path}" dir="${basedir}" failonerror="true">
        <arg value="--check"/>
    </exec>
</target>
```

Kiểm tra file chỉ phù hợp khi vị trí executable đã biết. Nếu executable được tìm từ PATH, cần một cách kiểm tra khác phù hợp với OS hoặc chạy lệnh version/health-check rồi kiểm tra exit code.

## 16. Một số thuộc tính exec cần biết khi vận hành

| Thuộc tính | Mục đích | Khi nên dùng |
|---|---|---|
| `executable` | Chương trình cần chạy | Luôn cần chỉ định |
| `dir` | Working directory của tiến trình con | Khi command dùng đường dẫn tương đối hoặc cần chạy trong module cụ thể |
| `os` | Danh sách OS name được phép chạy | Khi một command chỉ hợp lệ trên một số OS name cụ thể |
| `failonerror` | Build fail khi exit code khác 0 | Khi command là bước bắt buộc |
| `resultproperty` | Lưu exit code | Khi cần phân loại hoặc xử lý kết quả sau lệnh |
| `output` / `error` | Lưu stdout/stderr vào file | Khi cần giữ log để chẩn đoán hoặc làm artifact |
| `outputproperty` / `errorproperty` | Lưu output vào property | Khi output nhỏ và cần dùng trong build logic |
| `timeout` | Giới hạn thời gian chạy | Khi command có thể treo hoặc chờ tài nguyên ngoài |
| `newenvironment` | Không kế thừa môi trường cha | Khi cần môi trường cô lập và đã khai báo đầy đủ biến |
| `spawn` | Khởi chạy không chờ tiến trình kết thúc | Chỉ cho tiến trình nền không cần kết quả trong build |

Với `spawn="true"`, Ant không đợi tiến trình hoàn tất theo cách thông thường; vì vậy không phù hợp với bước build cần exit code, output hoặc xác nhận hoàn thành trước khi target tiếp tục. Không dùng spawn cho compiler, test runner, validator hoặc bước publish cần kiểm soát kết quả.

## 17. Bảo mật khi truyền environment và tham số

Biến môi trường thường được dùng để truyền endpoint, profile, thư mục làm việc hoặc secret cho tiến trình con. Cần tránh ghi giá trị nhạy cảm vào log:

- Không in toàn bộ environment ra terminal hoặc report.
- Không hard-code mật khẩu, token hay private key trong `build.xml`.
- Dùng secret store hoặc cơ chế bảo mật của CI để cung cấp giá trị.
- Chỉ truyền biến mà command thực sự cần.
- Hạn chế dùng `newenvironment="true"` nếu chưa biết hết các biến hệ thống cần thiết.
- Tránh đưa secret vào `<arg>` nếu công cụ có thể ghi lại command line hoặc process list.

Một số hệ điều hành cho phép người dùng khác cùng máy quan sát command line của tiến trình. Nếu CLI hỗ trợ đọc secret từ environment, file tạm có quyền truy cập hạn chế hoặc secret manager, hãy ưu tiên cách phù hợp với chính sách bảo mật của dự án.

## 18. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Execute failed: ... Cannot run program` | Executable không tồn tại hoặc không tìm thấy trong PATH | Kiểm tra `executable`, PATH và quyền chạy |
| Command chạy sai file cấu hình | Working directory không đúng | Đặt `dir` tường minh và kiểm tra đường dẫn tương đối |
| Script không tìm thấy input | Script giả định cwd là thư mục khác | Truyền đường dẫn tuyệt đối hoặc cấu hình `dir` |
| Biến môi trường không có trong process | Chưa khai báo `<env>` hoặc tên biến sai | Kiểm tra `key`, `value`, tên biến và `newenvironment` |
| Command mất PATH/JAVA_HOME | Dùng `newenvironment="true"` nhưng không khai báo lại | Kế thừa môi trường hoặc thêm đầy đủ biến cần thiết |
| Command chạy trên OS không phù hợp | Thiếu `os` hoặc điều kiện target | Dùng `os` hay `<condition><os .../></condition>` |
| Target kết thúc thành công dù command trả lỗi | `failonerror="false"` và không kiểm tra resultproperty | Bật failonerror hoặc kiểm tra exit code rồi `<fail>` |
| Build treo khi chạy công cụ ngoài | Tiến trình chờ vô hạn hoặc đợi input | Đặt `timeout`, cung cấp input hoặc sửa command ở chế độ non-interactive |
| Dấu `>` không tạo file | Ant truyền nó như đối số bình thường | Dùng `output` hoặc gọi shell tường minh |
| Đối số có dấu cách bị tách | Ghép lệnh bằng chuỗi `line` không đúng | Dùng một `<arg value>` hoặc `<arg file>` cho từng đối số |

## 19. Bài tập thực hành

1. Viết target gọi `java -version` bằng `<exec>`.
2. Thêm `dir` để command chạy trong một thư mục con và cho chương trình in working directory hiện tại.
3. Truyền `APP_ENV=development` bằng `<env>` rồi đọc bằng `System.getenv()` trong chương trình Java.
4. Đặt `newenvironment="true"`, chạy lại và quan sát biến môi trường nào không còn được kế thừa; sau đó khai báo lại các biến cần thiết.
5. Dùng `<property environment="env"/>` để in `JAVA_HOME` và `PATH`.
6. Tạo hai script: `run-windows.cmd` và `run-unix.sh`; dùng `<os family="windows"/>` và `<os family="unix"/>` để chọn target.
7. Thử thuộc tính `os` trực tiếp trên `<exec>` và quan sát command bị bỏ qua trên OS không khớp.
8. Gọi một chương trình trả mã thoát khác 0; so sánh `failonerror="true"` với `failonerror="false" resultproperty="..."`.
9. Cấu hình `output` và `error` để lưu stdout/stderr riêng.
10. Đặt timeout ngắn cho một command chạy lâu và quan sát cách Ant xử lý khi hết thời gian.

Sau bài tập, người học cần giải thích được `executable` khác `dir` như thế nào, vì sao environment của Ant không tự động trở thành property nếu chưa khai báo, cách `newenvironment` ảnh hưởng đến tiến trình con và cách giới hạn command theo hệ điều hành.

## 20. Nguyên tắc sử dụng exec trong build thực tế

Hãy chỉ định executable rõ ràng, đặt working directory có chủ đích, truyền đối số theo từng `<arg>` và khai báo đúng biến môi trường mà chương trình cần. Dùng `os` cho command đơn giản chỉ chạy trên một số OS name; dùng điều kiện `<os>` và target riêng khi mỗi nền tảng cần executable hoặc script khác nhau.

Với command bắt buộc, đặt `failonerror="true"` hoặc kiểm tra exit code rồi dừng bằng `<fail>`. Thu thập stdout/stderr khi cần chẩn đoán, đặt timeout cho lệnh có nguy cơ treo và tránh ghi secret vào log. Những quy tắc này giúp tiến trình ngoài trở thành một bước build có thể tái hiện, kiểm soát và vận hành ổn định trên máy phát triển lẫn CI.

## 21. Tài liệu tham khảo

- [Apache Ant Manual: Exec Task](https://ant.apache.org/manual/Tasks/exec.html)
- [Apache Ant Manual: Conditions – OS Condition](https://ant.apache.org/manual/Conditions.html)
- [Apache Ant Manual: Property Task](https://ant.apache.org/manual/Tasks/property.html)
