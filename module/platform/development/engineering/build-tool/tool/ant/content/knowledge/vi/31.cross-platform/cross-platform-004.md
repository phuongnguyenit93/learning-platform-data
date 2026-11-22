# Chọn công cụ ngoài theo hệ điều hành và xác minh trước khi chạy trong Apache Ant

Một dự án dùng **Apache Ant** có thể hoạt động trên Windows, Linux và macOS nhưng vẫn phải gọi chương trình ngoài: Git để lấy revision, một trình đóng gói, trình ký số, trình chuyển đổi tài liệu hoặc script do dự án cung cấp. Khó khăn nằm ở chỗ **tên executable, cách truyền lệnh, đường dẫn và công cụ được cài sẵn không giống nhau giữa các hệ điều hành**.

Trong chương **Đa nền tảng** của **Build Tool Ant**, bài học này hướng dẫn cách nhận diện hệ điều hành từ JVM đang chạy Ant, chọn đúng executable, xác minh công cụ sẵn sàng, rồi mới gọi nó bằng `<exec>`. Một luồng build đáng tin cậy cần có thông báo rõ ràng nếu nền tảng không được hỗ trợ, công cụ không tồn tại, không thể khởi chạy, sai phiên bản hoặc trả về mã lỗi.

## 1. Vấn đề: “đã chọn đúng OS” chưa có nghĩa là chạy được

Giả sử build cần chạy Git để xác định commit hiện tại:

```bash
git rev-parse --verify HEAD
```

Cùng ý nghĩa nghiệp vụ nhưng các môi trường có thể khác nhau:

| Môi trường | Cách gọi thường gặp | Điểm phải xác minh |
| --- | --- | --- |
| Windows | `git.exe`, có thể ở `C:\Program Files\Git\cmd\git.exe` | Git có trên PATH hay có đường dẫn cấu hình cụ thể; file `.exe` khởi chạy được |
| Linux | `git`, thường từ một thư mục trên PATH | Git đã được cài, có quyền thực thi, đúng phiên bản |
| macOS | `git` | Git thực sự sẵn sàng; không chỉ có một launcher yêu cầu cài thêm công cụ |
| Container/CI | `git` hoặc path riêng do image cấp | Binary có trong image, cấu hình môi trường và quyền chạy phù hợp |

Một build Ant có thể gặp nhiều trường hợp lỗi khác nhau:

- Script chỉ gọi `git.exe` nên thất bại trên Linux/macOS.
- Script gọi `git` nhưng Git chưa được cài vào CI.
- Trình đóng gói chỉ có dạng `.cmd` trên Windows, trong khi `<exec>` gọi file đó như executable trực tiếp.
- Công cụ tồn tại nhưng không thể chạy, hoặc chạy được nhưng trả mã lỗi khác `0`.
- Task `<exec>` bị bỏ qua bởi điều kiện `osfamily`, trong khi các task phía sau vẫn giả định đầu ra đã được tạo.
- Công cụ trên PATH thuộc phiên bản khác, không hỗ trợ tham số mà build cần.

Vì vậy, quá trình phải đi theo thứ tự **xác định nền tảng → chọn công cụ → kiểm tra khả năng sử dụng → thực thi → xác nhận kết quả**.

## 2. Nhận diện hệ điều hành bằng Ant

Ant cung cấp điều kiện `<os>` trong `<condition>`. Đây là cách khai báo độc lập với cú pháp shell:

```xml
<target name="detect-platform">
    <condition property="platform.windows">
        <os family="windows"/>
    </condition>

    <condition property="platform.unix">
        <os family="unix"/>
    </condition>

    <condition property="platform.macos">
        <os family="mac"/>
    </condition>
</target>
```

Các giá trị được xét theo thông tin hệ điều hành do JVM mà Ant đang chạy cung cấp.

| Điều kiện | Ý nghĩa |
| --- | --- |
| `<os family="windows"/>` | Các phiên bản Windows |
| `<os family="unix"/>` | Nhóm Unix-like, gồm Linux và macOS |
| `<os family="mac"/>` | Họ hệ điều hành Apple Macintosh/macOS |
| `<os name="Linux"/>` | Tên hệ điều hành đúng theo `os.name` của JVM |
| `<os arch="amd64"/>` | Kiểm tra kiến trúc JVM/OS báo cáo |
| `<os family="unix" arch="aarch64"/>` | Chỉ đúng khi đồng thời thỏa cả họ OS và kiến trúc |

**Chú ý:** macOS thường thỏa cả `family="mac"` và `family="unix"`. Đừng viết hai nhánh độc lập rồi giả định chúng không bao giờ cùng chạy. Nếu dùng hai nhóm **Windows và Unix**, nhánh macOS nằm trong Unix và hai nhánh thường tách biệt. Nếu cần khác biệt giữa macOS và Unix khác, hãy dùng điều kiện loại trừ:

```xml
<condition property="platform.unix.nonmac">
    <and>
        <os family="unix"/>
        <not>
            <os family="mac"/>
        </not>
    </and>
</condition>
```

Đây là nhóm “Unix nhưng không phải macOS”, **không đồng nghĩa với Linux**: BSD và các biến thể Unix khác có thể cũng thuộc nhóm này. Khi chỉ hỗ trợ Linux, kiểm tra rõ `<os name="Linux"/>` hoặc điều kiện thích hợp đã kiểm thử.

### Điều kiện `if` của target xét *sự tồn tại* property

Ví dụ sau hoạt động đúng, vì `platform.windows` chỉ được đặt khi điều kiện đúng:

```xml
<condition property="platform.windows">
    <os family="windows"/>
</condition>

<target name="windows-step" if="platform.windows">
    <echo message="Chạy riêng trên Windows"/>
</target>
```

**Bẫy phổ biến:**

```xml
<condition property="platform.windows" value="true" else="false">
    <os family="windows"/>
</condition>

<target name="windows-step" if="platform.windows">
    <!-- Nhánh này vẫn chạy trên Unix vì property tồn tại,
         dù giá trị của nó là chuỗi "false". -->
</target>
```

Trong cơ chế `if="property-name"` truyền thống của target, giá trị chuỗi `false` **không làm property trở thành “chưa tồn tại”**. Nếu cần kiểm tra giá trị boolean, dùng điều kiện phù hợp hoặc cơ chế `if:true` của Ant phiên bản tương ứng; trong ví dụ bài học, chỉ đặt property khi điều kiện đúng là cách dễ hiểu.

### Không được bỏ qua nền tảng không hỗ trợ

Nếu build bắt buộc phải có một nhánh công cụ, thêm điều kiện nền tảng hỗ trợ:

```xml
<condition property="platform.supported">
    <or>
        <os family="windows"/>
        <os family="unix"/>
    </or>
</condition>
<fail unless="platform.supported"
      message="Build này chỉ hỗ trợ Windows hoặc Unix-like."/>
```

Nếu không có `<fail>`, một nhóm `<exec osfamily="...">` có thể bị bỏ qua trên OS không khớp, khiến pipeline báo thành công giả.

## 3. Chọn executable: hai mô hình thường dùng

### 3.1. Cùng chương trình, khác tên/path

Git là ví dụ đơn giản: tên thường là `git.exe` trên Windows và `git` trên Linux/macOS. Ant có thể chọn một trong hai bằng `<condition>`:

```xml
<condition property="git.executable"
           value="git.exe"
           else="git">
    <os family="windows"/>
</condition>
```

Nếu không có cấu hình trước đó, `git.executable` được gán theo OS. Do property Ant thường bất biến sau khi được đặt, môi trường CI có thể chủ động chỉ định đường dẫn riêng:

```bash
ant -Dgit.executable=/opt/tools/git/bin/git show-revision
```

Trên Windows, giá trị có thể chứa dấu cách:

```powershell
ant '-Dgit.executable=C:\Program Files\Git\cmd\git.exe' show-revision
```

Tùy shell, có thể cần điều chỉnh cách quote tham số `-D`, nhưng giá trị truyền cho Ant phải là **đường dẫn executable**, không gộp thêm `--version` hay tham số khác.

Điểm cần nhớ: `executable` xác định một chương trình; mỗi tham số nên được đưa qua một `<arg>` riêng.

### 3.2. Mỗi nền tảng dùng một chương trình hoặc script khác

Chẳng hạn dự án có `scripts/export.cmd` cho Windows và `scripts/export.sh` cho Unix. Thay vì ép cả hai dùng cú pháp shell của một OS, tạo hai target tách biệt và gọi bằng interpreter tương ứng:

```xml
<target name="export-windows"
        depends="detect-platform"
        if="platform.windows">
    <exec executable="cmd.exe"
          osfamily="windows"
          dir="${basedir}"
          failonerror="true">
        <arg value="/d"/>
        <arg value="/c"/>
        <arg file="scripts/export.cmd"/>
    </exec>
</target>

<target name="export-unix"
        depends="detect-platform"
        if="platform.unix">
    <exec executable="sh"
          osfamily="unix"
          dir="${basedir}"
          failonerror="true">
        <arg file="scripts/export.sh"/>
    </exec>
</target>

<target name="export" depends="export-windows,export-unix"/>
```

Đây là **cách chọn nhánh**; bản triển khai hoàn chỉnh cần xác minh script có tồn tại và interpreter có thể chạy trước khi gọi. Phần dưới trình bày riêng việc xác minh đó.

Trên Windows, Ant thường không thể chạy trực tiếp `.bat` hoặc `.cmd` qua cơ chế khởi tạo process của Java, vì vậy dùng `cmd.exe /c`. Trên Unix, dùng `sh script.sh` để không phải phụ thuộc bit thực thi của file script; nếu script dùng cú pháp Bash, phải gọi `bash` và xác minh Bash tồn tại thay vì mặc định rằng `sh` tương đương Bash.

## 4. Ba mức xác minh trước khi chạy

Việc chọn đúng tên file mới chỉ là bước đầu. Tùy công cụ, có thể xác minh theo các lớp sau.

### 4.1. Kiểm tra file cấu hình có tồn tại

Khi được cung cấp **đường dẫn file cụ thể**, `<available>` có thể kiểm tra:

```xml
<property name="tool.executable"
          location="tools/bin/converter"/>

<available file="${tool.executable}"
           type="file"
           property="tool.file.exists"/>

<fail unless="tool.file.exists"
      message="Thiếu công cụ tại ${tool.executable}"/>
```

`location` tạo đường dẫn tuyệt đối để Ant tìm file, nhưng không bắt buộc đường dẫn đó đi vào artifact. `<available type="file">` kiểm tra sự tồn tại và loại đối tượng, **không bảo đảm file có quyền chạy, đúng định dạng hoặc đúng phiên bản**.

Khi chương trình nằm trên PATH, có thể dùng `<available file="..." filepath="...">` để dò tên file trong tập thư mục được chỉ định:

```xml
<property environment="env"/>
<available file="git"
           filepath="${env.PATH}"
           type="file"
           property="git.found.on.path"/>
```

Ví dụ trên phù hợp khi biến môi trường `PATH` có đúng tên như vậy trong môi trường đang chạy, nhưng một số môi trường Windows có cách viết `Path` khác, và file trên Windows thường là `git.exe`. Hơn nữa, PATH chứa file chưa chứng minh chương trình chạy được. Vì vậy với công cụ trên PATH, **thử chạy lệnh kiểm tra nhẹ** là cách xác minh thực dụng và sát yêu cầu hơn.

### 4.2. Kiểm tra có thể khởi chạy và trả kết quả thành công

Một chương trình có thể có sẵn file nhưng hỏng thư viện động, thiếu quyền hoặc không tương thích kiến trúc. Với công cụ hỗ trợ `--version`, có thể probe:

```xml
<exec executable="${git.executable}"
      dir="${basedir}"
      failifexecutionfails="false"
      failonerror="false"
      resultproperty="git.probe.exit"
      outputproperty="git.probe.stdout"
      errorproperty="git.probe.stderr"
      timeout="10000">
    <arg value="--version"/>
</exec>

<fail unless="git.probe.exit"
      message="Không khởi chạy được Git: ${git.executable}"/>

<condition property="git.probe.nonzero">
    <not>
        <equals arg1="${git.probe.exit}" arg2="0"/>
    </not>
</condition>

<fail if="git.probe.nonzero"
      message="Git --version thất bại: exit=${git.probe.exit}"/>
```

Trong pha **probe**, `failifexecutionfails="false"` cho phép Ant tiếp tục đến `<fail>` tùy chỉnh, để đưa ra thông báo rõ ràng khi không khởi tạo được tiến trình. Sau đó kiểm tra property chứa mã thoát có tồn tại và có bằng `0` hay không. Nếu không được thiết lập, báo lỗi thiếu/không chạy được công cụ. Nếu là mã khác `0`, coi bước xác minh thất bại.

Tuy nhiên không phải công cụ nào cũng hỗ trợ `--version`. Có công cụ dùng `-version`, `/?` hoặc yêu cầu tham số probe riêng. Hãy chọn **lệnh nhẹ, không tạo tác dụng phụ**, rồi quy định mã thành công theo công cụ. Không lấy một cú pháp probe bất kỳ áp vào mọi chương trình.

### 4.3. Kiểm tra phiên bản và năng lực đúng yêu cầu

`git --version` thoát `0` chứng minh khả năng chạy cơ bản, nhưng chưa chứng minh nó hỗ trợ tất cả cờ build cần. Nếu dự án yêu cầu **Git tối thiểu 2.40**, hoặc một trình ký số có provider cụ thể, cần áp dụng thêm chính sách:

- Parse và so phiên bản theo **thành phần số**, tránh so sánh chuỗi từ điển như `"2.9" > "2.40"`.
- Thử một tính năng cụ thể không có tác dụng phụ nếu khó xác định năng lực bằng version.
- Kiểm tra module/plugin/license cần thiết trước khi tạo artifact.
- Nếu cần tính tái lập cao, cố định binary bằng toolchain/container được kiểm soát và ghi rõ phiên bản dự kiến trong cấu hình CI.

Một số lệnh `--version` có thể ghi ra stderr mà vẫn thoát `0`; điều kiện thành công phải dựa vào hợp đồng của từng công cụ. Đừng giả định mọi chương trình đều in stdout.

## 5. Ví dụ hoàn chỉnh: chọn Git theo OS, probe trước, dùng sau

Ví dụ sau là một file `build.xml` dùng **Apache Ant 1.7+** với Git. Dự án chứa file này trong **một Git repository có ít nhất một commit**. Mục tiêu là lấy commit hiện tại; nếu không hỗ trợ OS hoặc không có Git dùng được, Ant dừng với thông báo rõ ràng.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="portable-git" default="show-revision" basedir=".">

    <!-- 1. Nhận diện OS và chọn binary mặc định.
         Cho phép -Dgit.executable=... ghi đè từ lúc gọi Ant. -->
    <target name="detect-platform">
        <condition property="platform.windows">
            <os family="windows"/>
        </condition>
        <condition property="platform.unix">
            <os family="unix"/>
        </condition>

        <condition property="platform.supported">
            <or>
                <os family="windows"/>
                <os family="unix"/>
            </or>
        </condition>

        <fail unless="platform.supported"
              message="Chỉ hỗ trợ Windows hoặc Unix-like (Linux/macOS)."/>

        <condition property="git.executable"
                   value="git.exe"
                   else="git">
            <os family="windows"/>
        </condition>
    </target>

    <!-- 2. Chạy một lệnh thăm dò có chi phí thấp. -->
    <target name="verify-git" depends="detect-platform">
        <exec executable="${git.executable}"
              dir="${basedir}"
              failifexecutionfails="false"
              failonerror="false"
              resultproperty="git.check.exit"
              outputproperty="git.check.stdout"
              errorproperty="git.check.stderr"
              timeout="10000">
            <arg value="--version"/>
        </exec>

        <!-- Nếu process không khởi tạo được, resultproperty
             có thể không được thiết lập. -->
        <fail unless="git.check.exit"
              message="Không tìm thấy hoặc không khởi chạy được Git.
                       Hãy cài Git, cập nhật PATH hoặc truyền
                       -Dgit.executable=đường_dẫn_đến_git"/>

        <!-- Không nhầm 'property tồn tại' với 'exit code bằng 0'. -->
        <condition property="git.check.failed">
            <not>
                <equals arg1="${git.check.exit}" arg2="0"/>
            </not>
        </condition>

        <fail if="git.check.failed"
              message="Git không chạy thành công.
                       Exit=${git.check.exit}; stderr=${git.check.stderr}"/>

        <echo message="Git đã sẵn sàng: ${git.check.stdout}"/>
    </target>

    <!-- 3. Sau khi verify mới chạy lệnh công việc thật. -->
    <target name="show-revision" depends="verify-git">
        <exec executable="${git.executable}"
              dir="${basedir}"
              failifexecutionfails="true"
              failonerror="true"
              outputproperty="source.revision"
              timeout="10000">
            <arg value="rev-parse"/>
            <arg value="--verify"/>
            <arg value="HEAD"/>
        </exec>

        <echo message="Source revision: ${source.revision}"/>
    </target>
</project>
```

**Chạy bình thường:**

```bash
ant show-revision
```

**Chạy khi Git ở vị trí riêng (Linux/macOS):**

```bash
ant -Dgit.executable=/opt/git/bin/git show-revision
```

**Chạy khi Git có đường dẫn chứa khoảng trắng (PowerShell):**

```powershell
ant '-Dgit.executable=C:\Program Files\Git\cmd\git.exe' show-revision
```

Luồng thực tế:

```text
ant show-revision
       |
       v
detect-platform
       |-- không phải Windows/Unix -> FAIL
       |-- Windows -> git.exe (nếu chưa cấu hình)
       '-- Unix    -> git     (nếu chưa cấu hình)
       |
       v
verify-git: git --version
       |-- không tạo được process -> FAIL
       |-- exit code != 0         -> FAIL
       '-- exit code == 0         -> tiếp tục
       |
       v
show-revision: git rev-parse --verify HEAD
       |-- trả lỗi                  -> FAIL
       '-- thành công               -> hiển thị commit
```

**Vì sao có hai cách đặt `failonerror`?** Lệnh probe dùng `false` để có thể diễn giải exit code bằng thông báo riêng. Khi chạy lệnh chính, dùng `true` để mọi exit code thất bại khiến build dừng. `<exec>` mặc định **không fail build chỉ vì process trả mã khác 0** nếu không đặt `failonerror="true"`, nên phải chỉ định rõ.

**Vì sao cần `dir="${basedir}"`?** Đường dẫn làm việc ảnh hưởng lệnh Git và nhiều công cụ khác. Ghi rõ thư mục chạy giúp tránh dựa vào working directory hiện tại của quá trình Java/Ant.

**Vì sao dùng ba `<arg value="..."/>`?** Mỗi argument đi vào process dưới dạng một phần tử riêng. Tránh viết `<arg line="rev-parse --verify HEAD"/>` khi có đầu vào động chứa khoảng trắng hoặc ký tự đặc biệt. Với file path, ưu tiên `<arg file="..."/>` để Ant giải quyết đường dẫn.

## 6. Ví dụ chọn script khác nhau và kiểm tra file trước khi chạy

Khi mỗi OS có một script riêng, có thể chia thành target có điều kiện. Ví dụ dưới dùng hai file dự kiến ở `scripts/export.cmd` và `scripts/export.sh`.

```xml
<project name="portable-export" default="export" basedir=".">

    <target name="detect-platform">
        <condition property="platform.windows">
            <os family="windows"/>
        </condition>
        <condition property="platform.unix">
            <os family="unix"/>
        </condition>
        <condition property="platform.supported">
            <or>
                <os family="windows"/>
                <os family="unix"/>
            </or>
        </condition>
        <fail unless="platform.supported"
              message="Không có script export cho hệ điều hành này."/>
    </target>

    <target name="export-windows"
            depends="detect-platform"
            if="platform.windows">

        <available file="scripts/export.cmd"
                   type="file"
                   property="export.windows.exists"/>
        <fail unless="export.windows.exists"
              message="Thiếu scripts/export.cmd"/>

        <!-- cmd.exe là interpreter cho .cmd/.bat. -->
        <exec executable="cmd.exe"
              osfamily="windows"
              dir="${basedir}"
              failonerror="true"
              timeout="120000">
            <arg value="/d"/>
            <arg value="/c"/>
            <arg file="scripts/export.cmd"/>
        </exec>
    </target>

    <target name="export-unix"
            depends="detect-platform"
            if="platform.unix">

        <available file="scripts/export.sh"
                   type="file"
                   property="export.unix.exists"/>
        <fail unless="export.unix.exists"
              message="Thiếu scripts/export.sh"/>

        <!-- Nếu script dùng Bash-specific syntax, gọi bash
             và probe bash trước thay vì giả định sh == bash. -->
        <exec executable="sh"
              osfamily="unix"
              dir="${basedir}"
              failonerror="true"
              timeout="120000">
            <arg file="scripts/export.sh"/>
        </exec>
    </target>

    <target name="export"
            depends="export-windows,export-unix"/>
</project>
```

Để thử cách điều phối, hai script tối thiểu có thể chỉ in một dòng:

**`scripts/export.cmd`**

```bat
@echo off
echo Export hook on Windows
exit /b 0
```

**`scripts/export.sh`**

```sh
#!/bin/sh
set -eu
printf '%s\n' 'Export hook on Unix'
```

Khi thay bằng script xuất file thực tế, cần thêm xác nhận output sau khi chạy, ví dụ:

```xml
<available file="dist/export.zip"
           type="file"
           property="export.artifact.exists"/>
<fail unless="export.artifact.exists"
      message="Lệnh export thoát thành công nhưng thiếu dist/export.zip"/>
```

Đoạn kiểm tra output phải được đặt **sau target export** tương ứng và trong target kiểm tra có dependency đúng; không đặt phía trước rồi mong Ant tự chạy lại điều kiện.

Chỉ kiểm tra file có tồn tại có thể vẫn chưa đủ nếu output của lần trước còn nguyên. Với build cần độ tin cậy cao, hãy dọn đầu ra cũ trước khi chạy hoặc kiểm tra thêm kích thước/hash/định dạng đầu ra theo hợp đồng.

**Lưu ý về shell trên Windows:** `cmd.exe /c` phải xử lý đường dẫn chứa khoảng trắng và quy tắc quote riêng của `cmd`. `<arg file="..."/>` giải quyết đường dẫn thành một argument, nhưng khi thêm nội suy dữ liệu tùy ý vào script/shell, vẫn phải kiểm tra các ký tự có ý nghĩa với interpreter. Với công cụ có executable trực tiếp, gọi trực tiếp qua `<exec>` và tách argument thường đơn giản, an toàn hơn.

## 7. Đường dẫn, PATH và môi trường chạy

### 7.1. Không giả định có cùng PATH

Một công cụ chạy được từ terminal của lập trình viên chưa chắc xuất hiện trong PATH của Ant khi được mở từ IDE, dịch vụ Windows, container hay CI. Ant có thể đọc môi trường:

```xml
<property environment="env"/>
<echo message="Java OS: ${os.name}"/>
```

Khi cần chẩn đoán, xem PATH của **process Ant thực sự chạy**; việc mở terminal khác và gọi `git --version` chỉ chứng minh terminal đó tìm được Git. Cũng cần kiểm tra tên `Path` / `PATH` theo môi trường Windows.

Nếu cần thay đổi PATH riêng cho process con, `<exec>` có nested `<env>`:

```xml
<exec executable="git"
      failonerror="true">
    <env key="PATH" path="/opt/tools/bin:/usr/local/bin:/usr/bin"/>
    <arg value="--version"/>
</exec>
```

Ví dụ trên **chỉ minh họa Unix PATH**. Trên Windows dấu phân tách và tên biến môi trường có thể khác; không copy cấu hình này cho mọi OS. Việc thay PATH cũng thay đổi thứ tự ưu tiên binary, nên cần được quy định rõ trong CI. Khi có path tuyệt đối đến công cụ đã chốt, có thể cấu hình thẳng `executable`.

### 7.2. Path chứa khoảng trắng

**Không gộp executable và arguments:**

```xml
<!-- Sai: đây không phải một executable hợp lệ. -->
<exec executable="C:\Program Files\Git\cmd\git.exe --version"/>
```

**Tách riêng:**

```xml
<exec executable="C:\Program Files\Git\cmd\git.exe"
      failonerror="true">
    <arg value="--version"/>
</exec>
```

Với tên file/path là một argument:

```xml
<exec executable="${converter.executable}"
      failonerror="true">
    <arg value="--input"/>
    <arg file="input/My Document.txt"/>
    <arg value="--output"/>
    <arg file="build/converted.txt"/>
</exec>
```

`<arg file="..."/>` phù hợp khi tham số là đường dẫn file; Ant chuyển nó thành path phù hợp theo hệ điều hành. Phải dùng `<arg value="..."/>` nếu tham số là một chuỗi option hoặc chuỗi logic không phải file.

### 7.3. Không phụ thuộc cú pháp shell khi không cần

`<exec>` bình thường gọi **một chương trình** với một danh sách tham số. Nó không mặc định hiểu toán tử shell như `|`, `>`, `&&` hoặc mở rộng `*.txt` giống một shell tương tác.

```xml
<!-- Sai kỳ vọng: '>' sẽ thành argument, không tự redirect. -->
<exec executable="git">
    <arg value="--version"/>
    <arg value=">"/>
    <arg value="version.txt"/>
</exec>
```

Nếu cần lưu stdout, dùng thuộc tính chuẩn của Ant:

```xml
<exec executable="git"
      output="build/git-version.txt"
      failonerror="true">
    <arg value="--version"/>
</exec>
```

Đối với lệnh phức tạp buộc dùng shell, thực thi interpreter thích hợp qua `cmd.exe /c` hoặc `sh -c` và kiểm soát quoting. Không ghép trực tiếp chuỗi do người dùng cung cấp vào lệnh shell; ký tự `&`, `|`, `>`, dấu quote và ký tự thay thế biến có thể đổi ý nghĩa lệnh.

### 7.4. Cách tìm executable của Ant

`<exec>` có các tùy chọn:

- `resolveexecutable="true"`: thử phân giải đường dẫn chương trình theo thư mục dự án và thư mục thực thi.
- `searchpath="true"`: cho phép tra cứu trong đường dẫn tìm kiếm của hệ thống khi phân giải executable.
- `vmlauncher="false"`: có thể khiến Ant dùng cơ chế shell trung gian ở một số OS; không nên coi đây là cách chung để “sửa mọi lỗi PATH”.
- `osfamily="windows"` hoặc `osfamily="unix"`: hạn chế nơi task chạy, nhưng **không tự báo lỗi** nếu task bị bỏ qua vì không khớp OS.

Đừng mặc định `resolveexecutable="true"` sẽ luôn ưu tiên binary trong PATH: hành vi này có thể thay đổi nơi tìm công cụ theo project directory. Nếu mục tiêu là chọn đúng toolchain được quản lý, truyền **path tuyệt đối đến binary đã phê duyệt** sẽ rõ ràng hơn.

Trên Windows, Java process launcher không áp dụng đầy đủ quy tắc `PATHEXT` của shell để tìm `.cmd`/`.bat` từ tên không có extension. Vì thế dùng `git.exe` cho binary và `cmd.exe /c` cho batch script là lựa chọn rõ ràng.

## 8. Điều khiển lỗi: bắt buộc khác với tùy chọn

Không phải công cụ nào cũng bắt buộc. Ví dụ Git có thể cần cho bản phát hành, còn công cụ tạo ảnh preview có thể chỉ là bước phụ.

| Loại công cụ | Nếu thiếu | Cách triển khai |
| --- | --- | --- |
| Bắt buộc để tạo artifact đúng | **Dừng build** | Probe, `<fail>` có thông báo, rồi `<exec failonerror="true">` |
| Tùy chọn, không ảnh hưởng artifact chính | Có thể bỏ qua có chủ đích | Đánh dấu rõ capability; log thông điệp; không báo đầu ra giả |
| Chỉ hỗ trợ trên một vài OS | Chặn hoặc disable chức năng có thông báo | Kiểm tra OS trước; nhánh target có điều kiện |
| Có phiên bản được chốt | Sai version là lỗi | Kiểm tra capability/version theo yêu cầu |
| Phải xuất file | Exit code chưa đủ | Kiểm tra artifact được sinh, loại bỏ output cũ |

Khi dùng target `if`/`unless`, phân biệt một property **chưa được đặt** với property mang chuỗi `false`. Khi dùng `resultproperty` của `<exec>`, phân biệt process **không thể khởi chạy** (có thể chưa có property kết quả) với process đã chạy và trả **exit code khác 0**.

Đối với task quan trọng, đừng dùng `spawn="true"`, vì Ant không chờ và không thể dựa vào các property kết quả như khi gọi đồng bộ. Nếu chương trình có khả năng treo, cấu hình `timeout` hợp lý; kết quả bị timeout phải được coi là thất bại khi nghiệp vụ yêu cầu thành công.

Ngoài ra, Ant property thường chỉ gán một lần. Nếu nhiều `<exec>` dùng chung một tên `resultproperty` hoặc `outputproperty`, lần sau có thể không ghi đè giá trị lần đầu. Đặt tên property **riêng cho từng bước** như `git.check.exit` và `converter.check.exit`.

## 9. Giữ tính tái lập và an toàn khi chạy tool ngoài

Việc chọn nhánh đúng giúp build **chạy được** trên nhiều OS; chưa đủ để bảo đảm bản build **tái lập** trên nhiều OS. Hai hệ điều hành có thể tạo ra artifact khác byte do line ending, locale, timezone, quyền file, đường dẫn tuyệt đối, timestamps, phiên bản compiler và thứ tự đóng gói.

Một hợp đồng toolchain có thể chỉ rõ:

| Thành phần | Ví dụ quy định |
| --- | --- |
| Supported OS | Windows 11 x64, Ubuntu x64, macOS ARM64 (theo dự án) |
| Executable | `git.exe` hoặc `git`; cho phép path cấu hình |
| Phiên bản | Git tối thiểu/đúng phiên bản đã kiểm thử |
| Tham số probe | `--version`, tối đa 10 giây |
| Thư mục thực thi | `basedir` của dự án |
| Môi trường | PATH, locale, timezone/encoding, biến cấu hình cần thiết |
| Thành công | Exit code `0` và đầu ra theo hợp đồng |
| Thất bại | Fail build với tên công cụ và gợi ý cấu hình |
| Artifact | Tên file, vị trí và phép kiểm tra sau thực thi |

Các biện pháp bảo vệ thực tế:

- **Ưu tiên task thuần Ant** khi tính năng đã có: `<copy>`, `<zip>`, `<checksum>`... thường tránh được phụ thuộc vào một executable hệ điều hành cụ thể.
- **Pin toolchain trong CI**: version cụ thể, container image hoặc đường dẫn binary do pipeline quản lý. Kiểm tra `--version` là phép phát hiện ban đầu, không chứng minh nguồn gốc đáng tin của binary trên PATH.
- **Tránh shell injection**: gọi executable trực tiếp và dùng `<arg value>`/`<arg file>`. Chỉ dùng shell khi cần và không chèn input không tin cậy vào chuỗi command.
- **Không ghi bí mật ra log**: đừng in token/password trong `<echo>`, dòng lệnh hay stdout được lưu làm artifact.
- **Đảm bảo output sạch**: dọn/kiểm tra output cũ trước khi xác thực rằng lệnh vừa tạo ra file mới.
- **Không nuốt lỗi**: nếu external tool là điều kiện để thành công, không cho phép Ant kết thúc `BUILD SUCCESSFUL` khi tool thực sự thất bại.

## 10. Tình huống lỗi và cách đọc thông điệp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Cannot run program "git": CreateProcess error=2` | Windows không tìm thấy binary tương ứng | Dùng `git.exe`; kiểm tra PATH của Ant; truyền path tuyệt đối |
| `No such file or directory` | Executable/path sai hoặc không có trong container/CI | Xác nhận phiên bản image, PATH và file thực tế |
| `Permission denied` | File không có quyền thực thi hoặc hệ thống không cho phép | Kiểm tra permission/interpreter/volume mount; không chỉ kiểm tra `available` |
| `error=193` trên Windows | Có thể cố thực thi script/file không phải executable Win32 | Dùng đúng interpreter, chẳng hạn `cmd.exe /c` cho `.cmd` |
| `git --version` trả mã khác 0 | Công cụ lỗi khi khởi chạy, thiếu phụ thuộc, policy | Xem stderr, chạy probe trong cùng môi trường của Ant |
| Build báo thành công dù script lỗi | `failonerror` mặc định false, hoặc target bị skip | Đặt `failonerror="true"` và kiểm tra nhánh bắt buộc |
| Có đầu ra từ lần build trước | Không dọn output hoặc không xác nhận file mới | Clean output, sau đó kiểm tra artifact |
| macOS chạy nhầm hai target | Cả `family="mac"` lẫn `family="unix"` đều đúng | Dùng nhánh loại trừ hoặc thiết kế target phụ thuộc rõ ràng |
| Chạy từ IDE lỗi nhưng terminal được | PATH, working directory, JDK hoặc env của IDE khác | In thông tin môi trường an toàn và quy định `dir` |
| Path có khoảng trắng làm mất argument | Gộp executable với option, quote sai trong shell | Tách executable, dùng từng `<arg>` độc lập |

**Phân tích lỗi theo từng tầng:** Nếu không thấy cả output của bước probe, xem OS và điều kiện target. Nếu probe có chạy nhưng không có `resultproperty`, xem lỗi khởi tạo process. Nếu exit code khác 0, đọc stderr và cách sử dụng tham số. Nếu exit code 0 mà artifact thiếu, kiểm tra logic của chương trình và bước kiểm tra đầu ra.

## 11. Bài thực hành

**Bài 1 — Chọn Git và xử lý lỗi thiếu executable.** Tạo repository tối thiểu, dùng `build.xml` ở mục 5 và chạy `ant show-revision`. Sau đó truyền `-Dgit.executable=not-a-real-program`, quan sát Ant dừng ở bước probe với thông báo yêu cầu cấu hình công cụ. Khôi phục executable hợp lệ và chạy lại.

**Bài 2 — Chọn script theo OS.** Tạo `scripts/export.cmd` và `scripts/export.sh` như mục 6. Trên Windows, kiểm tra nhánh `cmd.exe` được chọn; trên Linux/macOS, kiểm tra nhánh `sh` được chọn. Xóa tạm **một script của đúng nền tảng đang kiểm thử** rồi quan sát `<available>` và `<fail>` đưa ra thông báo lỗi cụ thể. Khôi phục script để kết thúc thử nghiệm.

**Bài 3 — Phân biệt có file và có thể chạy.** Cấu hình một executable bằng path có tồn tại nhưng không có quyền chạy (trong môi trường thử nghiệm phù hợp). So sánh kết quả `<available type="file">` với bước probe `<exec>`. Giải thích vì sao bước đầu không đủ để xác thực tool.

**Bài 4 — Lỗi exit code.** Tạo một script luôn trả mã `7`, gọi bằng `<exec failonerror="false" resultproperty="demo.exit">` để đọc mã thoát. Sau đó chuyển sang `failonerror="true"` trong bước nghiệp vụ và quan sát build dừng. Giải thích vai trò của `failifexecutionfails` khi process thậm chí không thể bắt đầu.

**Bài 5 — Chuẩn bị CI đa nền tảng.** Viết bảng công cụ bắt buộc, phiên bản, lệnh probe, PATH dự kiến và đầu ra phải có cho Windows/Linux/macOS. Từ đó quyết định công cụ nào có thể thay bằng task Ant và công cụ nào cần cài/pin riêng.

## Tài liệu tham khảo

- Apache Ant — [Exec Task](https://ant.apache.org/manual/Tasks/exec.html): `executable`, `osfamily`, `arg`, `dir`, `resultproperty`, `failonerror`, `failifexecutionfails`, `timeout`, lưu ý Windows.
- Apache Ant — [Conditions](https://ant.apache.org/manual/Tasks/conditions.html): điều kiện `<os>`, các OS family và điều kiện logic.
- Apache Ant — [Condition Task](https://ant.apache.org/manual/Tasks/condition.html): thiết lập property dựa trên điều kiện.
- Apache Ant — [Available Task](https://ant.apache.org/manual/Tasks/available.html): kiểm tra file, resource và `filepath`.
- Apache Ant — [Arg/Command-line Types](https://ant.apache.org/manual/using.html#arg): phân biệt `value`, `file` và các tham số dòng lệnh.
- Apache Ant — [Target](https://ant.apache.org/manual/targets.html): dependency và điều kiện `if`/`unless`.
- Apache Ant — [Property](https://ant.apache.org/manual/Tasks/property.html): nạp property từ môi trường và cơ chế giá trị bất biến.

**Kết luận thực hành:** Hãy để Ant nhận biết OS bằng `<os>`, chọn executable qua property cấu hình, rồi kiểm tra sự tồn tại hoặc chạy một probe không gây tác dụng phụ trước khi chạy tác vụ thật. Với công cụ bắt buộc, dùng mã thoát và kiểm tra artifact để dừng build khi công việc thực tế thất bại. Cách này giúp một build Ant chạy có chủ đích trên từng nền tảng và báo lỗi đủ rõ để khắc phục.

