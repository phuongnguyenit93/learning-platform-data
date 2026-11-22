# Tách tham số khỏi chuỗi lệnh để giảm phụ thuộc shell trong Apache Ant

Một tác vụ build có thể chạy đúng trên Linux nhưng hỏng trên Windows chỉ vì cách ghép lệnh: đường dẫn chứa khoảng trắng bị tách thành nhiều phần, dấu nháy kép được hiểu khác nhau, hoặc ký tự `|`, `>`, `*` và biến môi trường được xử lý bởi shell thay vì bởi chương trình cần gọi. Với **Apache Ant**, cách giảm đáng kể các vấn đề đó là khai báo **chương trình thực thi** và **từng đối số** riêng biệt.

Thay vì tạo một chuỗi lệnh dài rồi kỳ vọng mọi hệ điều hành diễn giải giống nhau, Ant có thể truyền một danh sách đối số cho tiến trình đích. Kỹ thuật này đặc biệt hữu ích trong chương *Đa nền tảng*: cùng một `build.xml` có thể xử lý đường dẫn có khoảng trắng và dữ liệu động mà ít phụ thuộc hơn vào quy tắc của `cmd.exe`, PowerShell, `sh` hay `bash`.

## 1. Vấn đề nằm ở đâu khi ghép cả lệnh thành một chuỗi?

Giả sử cần lấy trạng thái Git của một tệp trong thư mục dự án có tên `My Project`. Trong terminal, người dùng có thể viết:

```bash
git -C "My Project" status --short -- "docs/ghi chu.txt"
```

Dấu nháy trong ví dụ là **cú pháp của shell** để gom các từ chứa khoảng trắng. Khi đưa nguyên chuỗi đó vào Ant, ta phải xem ai sẽ phân tích cú pháp: Ant, hệ điều hành hay shell được gọi tường minh?

Ví dụ dưới đây có vấn đề:

```xml
<!-- Sai: cả chuỗi bị xem là tên chương trình cần thực thi. -->
<exec executable="git -C My Project status --short"/>
```

`executable` được dùng để chỉ **tệp/chương trình thực thi**, không phải nơi viết toàn bộ dòng lệnh. Ant sẽ không tự hiểu khoảng trắng trong thuộc tính đó là ranh giới giữa tên chương trình và đối số.

Cách viết dưới đây cũng mong manh:

```xml
<!-- Dễ sai khi property chứa khoảng trắng. -->
<exec executable="git">
    <arg line="-C ${repo.dir} status --short -- ${tracked.file}"/>
</exec>
```

`<arg line="...">` yêu cầu Ant **tách một dòng văn bản thành các đối số**. Nếu giá trị property sau khi thay thế chứa khoảng trắng mà không được nhóm đúng cách, số lượng đối số có thể khác dự tính. Đặt thêm dấu nháy bằng phép nối chuỗi sẽ làm logic trở nên khó bảo trì, đặc biệt khi dữ liệu chứa chính dấu nháy.

Giải pháp ưu tiên là khai báo từng đối số rõ ràng:

```xml
<exec executable="git" failonerror="true">
    <arg value="-C"/>
    <arg file="${repo.dir}"/>
    <arg value="status"/>
    <arg value="--short"/>
    <arg value="--"/>
    <arg value="${tracked.file}"/>
</exec>
```

Trong cách viết này, `repo.dir` và `tracked.file` **mỗi giá trị là một đối số**, kể cả khi chứa khoảng trắng. Không cần tự thêm dấu nháy của shell vào nội dung property.

## 2. Ba lớp cần phân biệt: Ant, danh sách đối số và shell

Một lệnh chạy từ terminal thường đi qua nhiều lớp:

```text
Người dùng nhập chuỗi vào terminal
             |
             v
Shell (sh, bash, cmd.exe, PowerShell)
  - phân tích dấu nháy
  - thay biến hoặc ký tự đặc biệt theo cú pháp shell
  - xử lý pipe và chuyển hướng khi có yêu cầu
             |
             v
Chương trình đích + các đối số đã phân tách
```

Với `<exec executable="...">` và các `<arg>` riêng, Ant chủ động tạo danh sách đối số để khởi chạy chương trình:

```text
Ant build.xml
  executable = git
  arg[0]     = -C
  arg[1]     = /path/My Project
  arg[2]     = status
  arg[3]     = --short
  arg[4]     = --
  arg[5]     = docs/ghi chu.txt
             |
             v
Tiến trình Git nhận các đối số
```

Ở đây, Ant **không tự gọi shell chỉ để phân tích các ký tự `|`, `>`, `*` hoặc dấu nháy**. Việc khởi chạy tiến trình vẫn phụ thuộc API của JVM và hệ điều hành; trên Windows, hệ thống và chương trình đích còn có quy tắc chuyển danh sách đối số thành tham số mà ứng dụng nhận. Tuy vậy, không phải tự viết một tầng shell quoting là lợi ích lớn cho khả năng di chuyển giữa hệ điều hành.

Hãy phân biệt hai trường hợp:

- **Không dùng shell:** chương trình thật nhận `argv`/các đối số; ký tự `*` hoặc `|` thường là dữ liệu thông thường, trừ khi chính chương trình quyết định giải thích chúng.
- **Chủ động gọi shell:** ví dụ chạy `sh -c` hoặc `cmd /c`, shell sẽ tiếp tục phân tích chuỗi lệnh được truyền cho nó. Khi đó các vấn đề về quoting và khác biệt nền tảng xuất hiện trở lại.

## 3. Chọn đúng cách viết `<arg>` trong Ant

`<exec>`, `<java>` và một số tác vụ khác của Ant hỗ trợ phần tử `<arg>`. Mỗi kiểu khai báo có mục đích riêng:

| Dạng | Ý nghĩa | Tình huống nên dùng |
| --- | --- | --- |
| `<arg value="..."/>` | Truyền **một đối số nguyên vẹn**; khoảng trắng bên trong vẫn thuộc đối số đó | Tên có khoảng trắng, chuỗi `--option=value`, nội dung do property cung cấp |
| `<arg file="..."/>` | Truyền **một đường dẫn tệp**; Ant giải quyết đường dẫn tương đối theo `basedir` | Đường dẫn tệp/thư mục là một tham số của chương trình |
| `<arg path="..."/>` | Truyền một chuỗi **đường dẫn theo quy ước path của hệ điều hành**, có thể có danh sách các phần tử | Tham số dạng classpath hoặc danh sách đường dẫn |
| `<arg line="..."/>` | Ant phân tích một dòng văn bản thành **nhiều đối số** | Danh sách tùy chọn tĩnh, đơn giản, không chứa dữ liệu đường dẫn tùy ý |

Ví dụ:

```xml
<exec executable="some-tool" failonerror="true">
    <arg value="--title"/>
    <arg value="Báo cáo tháng 11"/>
    <arg value="--output"/>
    <arg file="reports/output file.txt"/>
    <arg value="--mode=release"/>
</exec>
```

Chương trình nhận năm đối số: `--title`, `Báo cáo tháng 11`, `--output`, đường dẫn tệp đã được Ant giải quyết, và `--mode=release`. Đoạn này minh họa cấu trúc đối số; `some-tool` là tên chương trình giả định, phải thay bằng công cụ thực tế khi sử dụng.

**Không tự bọc giá trị bằng dấu nháy kiểu shell**:

```xml
<!-- Không cần: dấu nháy có thể trở thành một phần nội dung đối số. -->
<arg value="&quot;Báo cáo tháng 11&quot;"/>

<!-- Đúng: giá trị có khoảng trắng vẫn là một đối số. -->
<arg value="Báo cáo tháng 11"/>
```

Tương tự, `<arg value="--title Báo cáo tháng 11"/>` tạo **một đối số dài**, không phải `--title` cùng với giá trị của nó. Việc chia đối số phải khớp với giao diện dòng lệnh của chương trình đích.

### Giá trị `path` không tương đương giá trị `file`

Nếu chương trình cần nhận một đường dẫn duy nhất, `file` thường làm rõ chủ đích hơn:

```xml
<arg file="${source.file}"/>
```

Nếu chương trình cần nhận một *danh sách* đường dẫn theo ký tự phân cách đường dẫn của hệ điều hành, `path` có thể phù hợp:

```xml
<arg path="${library.path}"/>
```

Trường hợp danh sách classpath trong tác vụ Java thường nên dùng chính cơ chế `<classpath>` hoặc `classpathref` của Ant, để Ant xử lý phân cách và thứ tự phần tử. Đừng gộp nhiều đường dẫn thành một chuỗi có dấu `:` cố định rồi giả định Windows cũng hiểu giống Unix; Windows thường dùng `;` cho danh sách path, còn hệ Unix thường dùng `:`.

## 4. Ví dụ hoàn chỉnh: truyền chuỗi và đường dẫn chứa khoảng trắng

Ví dụ dưới đây dùng `<java>` của Ant để chứng minh các đối số được truyền độc lập. Nó chỉ yêu cầu **JDK và Apache Ant**, không cần cài Git hay một CLI bên thứ ba. Cấu trúc dự án:

```text
ant-arguments/
├── build.xml
└── src/
    └── demo/
        └── ShowArguments.java
```

### Mã Java nhận đối số

Tạo `src/demo/ShowArguments.java`:

```java
package demo;

public class ShowArguments {
    public static void main(String[] args) {
        for (int i = 0; i < args.length; i++) {
            System.out.printf("arg[%d] = <%s>%n", i, args[i]);
        }
    }
}
```

Lớp này không thực hiện thao tác trên tệp; nó in từng phần tử của `args` để người học có thể thấy ranh giới đối số chính xác.

### Tệp `build.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-arguments" default="run" basedir=".">
    <property name="src.dir" location="src"/>
    <property name="classes.dir" location="build/classes"/>
    <property name="message.text" value="Xin chào từ Apache Ant"/>
    <property name="input.file" location="data/tập tin mẫu.txt"/>

    <target name="compile" description="Biên dịch chương trình minh họa">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8"/>
    </target>

    <target name="run" depends="compile"
            description="In các đối số nhận được">
        <java classname="demo.ShowArguments"
              classpath="${classes.dir}"
              fork="true"
              failonerror="true">
            <arg value="--message"/>
            <arg value="${message.text}"/>
            <arg value="--input"/>
            <arg file="${input.file}"/>
        </java>
    </target>

    <target name="clean" description="Xóa đầu ra biên dịch">
        <delete dir="build"/>
    </target>
</project>
```

Chạy từ thư mục chứa `build.xml`:

```bash
ant run
```

Phần đầu ra do lớp Java in có dạng:

```text
arg[0] = <--message>
arg[1] = <Xin chào từ Apache Ant>
arg[2] = <--input>
arg[3] = </duong-dan-tuyet-doi/ant-arguments/data/tập tin mẫu.txt>
```

Đường dẫn ở `arg[3]` chỉ là minh họa; trên Windows nó có thể bắt đầu bằng ký tự ổ đĩa và dùng dấu `\`. Tệp đầu vào không cần tồn tại vì lớp Java chỉ in chuỗi đối số.

Điều quan trọng là chương trình nhận **bốn đối số**. Cụm `Xin chào từ Apache Ant` vẫn nằm nguyên ở `arg[1]`, và đường dẫn có khoảng trắng vẫn nằm nguyên ở `arg[3]`. Nếu ghép bằng một chuỗi lệnh rồi tách sai, số lượng và vị trí đối số có thể thay đổi.

Có thể thay chuỗi đầu vào qua CLI:

```bash
ant -Dmessage.text="Bản build kiểm tra" run
```

Dấu nháy trong lệnh trên dành cho **shell nơi người dùng nhập lệnh** để chuyển một giá trị duy nhất cho `-Dmessage.text`. Một khi property đã vào Ant, `<arg value="${message.text}"/>` tự duy trì giá trị như một đối số riêng, không cần một lớp nháy bổ sung.

## 5. Áp dụng với công cụ bên ngoài qua `<exec>`

Trong dự án thực tế, Ant thường cần gọi công cụ không có task chuyên biệt hoặc task sẵn có chưa đáp ứng yêu cầu. Ví dụ dùng Git:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="git-status" default="status" basedir=".">
    <property name="repo.dir" location="../My Project"/>
    <property name="tracked.file" value="docs/ghi chu.txt"/>

    <target name="status" description="Xem trạng thái một file Git">
        <exec executable="git" failonerror="true">
            <arg value="-C"/>
            <arg file="${repo.dir}"/>
            <arg value="status"/>
            <arg value="--short"/>
            <arg value="--"/>
            <arg value="${tracked.file}"/>
        </exec>
    </target>
</project>
```

Ví dụ này yêu cầu Git có thể được gọi từ môi trường chạy Ant và `../My Project` là một Git repository hợp lệ. Đường dẫn `tracked.file` được Git hiểu tương đối với repository, còn `repo.dir` là một đối số đường dẫn mà Ant giải quyết từ `basedir`.

Từng `<arg>` tương ứng với một thành phần của giao diện dòng lệnh Git. Trong đó:

- `-C` yêu cầu Git chuyển sang thư mục được đưa ở **đối số kế tiếp**.
- `status` là subcommand, `--short` là tùy chọn định dạng.
- `--` kết thúc vùng tùy chọn trước khi truyền tên đường dẫn. Cách này cũng giảm khả năng tên tệp bắt đầu bằng `-` bị chương trình hiểu nhầm thành một tùy chọn.
- `docs/ghi chu.txt` là một đối số nguyên vẹn dù chứa khoảng trắng.

Ant không cần chạy qua `sh -c "git ..."` hay `cmd /c "git ..."` cho tình huống này. Cơ chế khởi chạy vẫn khác nhau giữa hệ điều hành, và Git vẫn phải có mặt trên máy, nhưng cấu trúc `build.xml` tránh được sự phụ thuộc không cần thiết vào cú pháp phân tích lệnh của shell.

### Thu thập trạng thái thoát và thông báo lỗi

Khi cần chẩn đoán công cụ bên ngoài, có thể dùng các thuộc tính của `<exec>`:

```xml
<target name="git-check">
    <exec executable="git"
          failonerror="false"
          failifexecutionfails="true"
          resultproperty="git.exit.code"
          outputproperty="git.stdout"
          errorproperty="git.stderr">
        <arg value="--version"/>
    </exec>

    <echo message="Git exit code: ${git.exit.code}"/>
    <echo message="Git stdout: ${git.stdout}"/>
    <fail message="Git failed (exit code ${git.exit.code})">
        <condition>
            <not>
                <equals arg1="${git.exit.code}" arg2="0"/>
            </not>
        </condition>
    </fail>
</target>
```

`failonerror="false"` cho phép target tiếp tục nếu chương trình thoát với mã lỗi để tự tạo thông báo; `resultproperty` lưu mã trả về, còn `outputproperty`/`errorproperty` lưu đầu ra chuẩn/đầu ra lỗi. `failifexecutionfails="true"` yêu cầu dừng nếu Ant thậm chí không thể khởi chạy chương trình. Khi chỉ cần dừng ngay nếu exit code khác 0, dùng `failonerror="true"` là đơn giản hơn.

Lưu ý property của Ant thường được gán một lần. Đừng giả định có thể chạy cùng một tác vụ lặp lại và ghi đè `git.exit.code` bằng kết quả mới trong cùng project. Ngoài ra, đầu ra của tool có thể chứa bí mật: chỉ in hoặc lưu các giá trị cần thiết cho việc chẩn đoán.

## 6. Thay thao tác shell bằng task gốc của Ant khi có thể

Tách tham số làm lời gọi CLI ổn định hơn, nhưng giải pháp đa nền tảng tốt hơn nữa là **tránh khởi chạy chương trình bên ngoài cho công việc Ant đã hỗ trợ**.

| Công việc mong muốn | Lệnh shell hay gặp | Task Ant nên cân nhắc |
| --- | --- | --- |
| Tạo thư mục | `mkdir -p` hoặc `mkdir` với tùy chọn hệ điều hành | `<mkdir dir="..."/>` |
| Sao chép tập tệp | `cp`, `copy`, `xcopy` | `<copy>` kết hợp `<fileset>` |
| Xóa thư mục build | `rm -rf`, `rmdir /s /q` | `<delete dir="..."/>` |
| Đổi tên, di chuyển | `mv`, `move` | `<move>` |
| Đóng gói, giải nén | `zip`, `unzip` hoặc công cụ riêng | `<zip>`, `<unzip>`, `<jar>` |
| Biên dịch và chạy Java | Ghép lệnh `javac`, `java` trong shell | `<javac>`, `<java>` |
| Ghi nội dung vào file | `echo ... > file.txt` | `<echo file="..."/>` |

Ví dụ, một lệnh Unix như `cp src/*.properties build/config/` vừa phụ thuộc chương trình `cp`, vừa dựa vào cách shell xử lý `*`. Có thể dùng task Ant:

```xml
<target name="copy-config">
    <mkdir dir="build/config"/>
    <copy todir="build/config">
        <fileset dir="src" includes="*.properties"/>
    </copy>
</target>
```

Ant tự xác định tệp phù hợp với mẫu trong `<fileset>` và sao chép chúng. Không cần yêu cầu shell mở rộng wildcard, cũng không cần hai phiên bản lệnh cho Windows và Unix.

Tương tự, thay vì tạo chuỗi `echo Finished > build/result.txt`, viết:

```xml
<target name="write-result">
    <mkdir dir="build"/>
    <echo file="build/result.txt" message="Finished"/>
</target>
```

Vì Ant sở hữu phần tác vụ, việc xử lý đường dẫn, lỗi tệp và tính tương thích được tập trung vào API task thay vì các tiện ích có cú pháp khác nhau.

## 7. Các ký tự shell không tự nhiên có tác dụng trong `<exec>`

Một số lỗi đa nền tảng đến từ việc quên rằng `<exec>` **không phải một shell command runner**:

| Cú pháp quen thuộc | Ý nghĩa trong shell | Khi truyền trực tiếp cho executable qua `<arg>` |
| --- | --- | --- |
| `|` | Pipe đầu ra giữa các lệnh | Thường chỉ là ký tự trong đối số; không tạo pipeline |
| `>` / `2>` | Chuyển hướng stdout/stderr | Không chuyển hướng nếu không chạy qua shell |
| `&&` | Chạy lệnh sau khi lệnh trước thành công | Không tự gọi lệnh thứ hai |
| `*.java` | Có thể được shell mở rộng thành danh sách tệp | Thường được truyền nguyên văn; tùy chương trình đích có hỗ trợ wildcard hay không |
| `$HOME` / `%USERPROFILE%` | Shell diễn giải biến theo nền tảng | Không tự được Ant thay thế như property `${...}` |
| `~` | Shell có thể mở rộng thành home directory | Không nhất thiết được chuyển thành đường dẫn home |

Vì thế, đoạn sau **không có nghĩa** chạy hai chương trình theo thứ tự:

```xml
<exec executable="git">
    <arg value="status"/>
    <arg value="&amp;&amp;"/>
    <arg value="git"/>
    <arg value="log"/>
</exec>
```

Ant chỉ gọi `git` **một lần** và truyền thêm các đối số `&&`, `git`, `log` cho Git. Nếu muốn chạy hai việc có quan hệ phụ thuộc, cách tự nhiên trong Ant là chia thành hai target:

```xml
<target name="check-status">
    <exec executable="git" failonerror="true">
        <arg value="status"/>
        <arg value="--short"/>
    </exec>
</target>

<target name="show-log" depends="check-status">
    <exec executable="git" failonerror="true">
        <arg value="log"/>
        <arg value="-1"/>
        <arg value="--oneline"/>
    </exec>
</target>
```

Chạy `ant show-log` sẽ thực hiện `check-status` trước `show-log`, và Ant chịu trách nhiệm quản lý chuỗi phụ thuộc. Mẫu XML này cần được đặt trong một `<project>` hợp lệ và chạy từ thư mục Git repository hoặc cấu hình `dir` thích hợp.

## 8. Khi nào thực sự cần shell?

Một số thao tác phụ thuộc vào tính năng shell, chẳng hạn pipeline phức tạp hoặc một script `.sh`/`.cmd` đã được tổ chức riêng. Khi đó, gọi shell **có chủ đích** và tách cấu hình theo nền tảng là hợp lý.

Ví dụ minh họa cho hệ Unix:

```xml
<target name="unix-shell-step">
    <exec executable="sh" osfamily="unix" failonerror="true">
        <arg value="-c"/>
        <arg value="printf 'Build step finished\n'"/>
    </exec>
</target>
```

Ví dụ minh họa cho Windows:

```xml
<target name="windows-shell-step">
    <exec executable="cmd" osfamily="windows" failonerror="true">
        <arg value="/c"/>
        <arg value="echo Build step finished"/>
    </exec>
</target>
```

`osfamily` giúp Ant giới hạn lời gọi vào họ hệ điều hành thích hợp. Trong hai trường hợp, giá trị cuối cùng **vẫn là một chuỗi lệnh cho shell phân tích**; quy tắc quoting, biến môi trường và ký tự đặc biệt vì vậy tùy thuộc `sh` hoặc `cmd`. Các ví dụ cố ý đơn giản và có chuỗi tĩnh để làm rõ ranh giới này.

Khi lệnh nhận dữ liệu động (tên tệp, thông điệp, tham số người dùng), không nên chỉ nối dữ liệu đó vào chuỗi cho `sh -c` hoặc `cmd /c`: các ký tự đặc biệt có thể bị diễn giải thành cú pháp mới. Nếu không tránh được shell, cần xử lý quoting theo **đúng loại shell**, kiểm soát đầu vào và giảm phần lệnh tự ghép đến mức tối thiểu. Việc tách `<arg>` ở lớp bên ngoài không tự giải quyết vấn đề nếu một `<arg>` cuối vẫn là cả chuỗi `-c` chứa dữ liệu chưa được bảo vệ.

Với batch script Windows, việc gọi qua `cmd /c` cũng có thể cần thiết vì `.bat`/`.cmd` không giống một chương trình thực thi độc lập trên mọi Java/Windows runtime. Với script Unix, cần chú ý quyền thực thi và shebang hoặc gọi `sh script.sh` nếu script phù hợp cú pháp shell đó. Tốt nhất chỉ dùng script riêng khi nó thật sự cần hành vi của shell hoặc môi trường bên ngoài.

## 9. Đường dẫn, biến môi trường và XML: ba nguồn nhầm lẫn khác nhau

### Đường dẫn có dấu cách và dấu phân cách

Khi đường dẫn được truyền dưới dạng đối số riêng, không cần tự đổi dấu cách thành `\ ` hay bọc toàn bộ đường dẫn trong dấu nháy. Dùng `${basedir}`, thuộc tính `file`/`location`, hoặc task `<path>` để Ant xử lý đường dẫn trong bối cảnh hệ điều hành.

Không nên nối một đường dẫn cố định của Unix như `/tmp/output` rồi mặc định đường dẫn đó có nghĩa tương đương trên Windows. Cũng không nên tự chia `C:\My Project\file.txt` theo khoảng trắng. Mục đích của `<arg file="...">` chính là tách việc xử lý đường dẫn khỏi việc phân tách đối số.

### Biến môi trường của tiến trình khác property Ant

Để đọc biến môi trường dưới dạng property của Ant, có thể nạp chúng tường minh:

```xml
<property environment="env"/>
```

Sau đó có thể tham chiếu, chẳng hạn `${env.JAVA_HOME}` nếu biến này thực sự được thiết lập. Cú pháp `${...}` do Ant xử lý, không phải cú pháp thay biến của `cmd.exe` hoặc `sh`. Tên biến và giá trị khả dụng giữa Windows, Linux và macOS có thể khác nhau.

Để đặt biến môi trường cho tiến trình con của `<exec>`, có thể dùng `<env>`:

```xml
<exec executable="some-tool" failonerror="true">
    <env key="APP_MODE" value="test"/>
    <arg value="--check"/>
</exec>
```

Trong ví dụ này, `APP_MODE` là biến môi trường truyền vào chương trình con; `--check` vẫn là đối số riêng. `some-tool` là chương trình giả định. Không cần ghép cú pháp `APP_MODE=test some-tool --check` theo Unix hay `set APP_MODE=test && some-tool --check` theo Windows.

### XML cũng có quy tắc escape riêng

Trong thuộc tính XML, ký tự `&` phải viết `&amp;`, ký tự `<` phải viết `&lt;`, và dấu nháy bên trong thuộc tính được bọc bằng dấu nháy kép có thể dùng `&quot;`. Đó là **escape của XML**, không phải escape của shell:

```xml
<exec executable="some-tool">
    <arg value="Tom &amp; Jerry"/>
</exec>
```

Chương trình đích nhận một đối số có nội dung `Tom & Jerry`. Nếu thêm dấu nháy shell vào chuỗi này, kết quả có thể không còn như mong muốn.

## 10. Những sai sót nên tránh khi chuyển từ lệnh terminal sang Ant

1. **Đặt cả dòng lệnh vào `executable`.** Hãy để `executable` là chương trình và khai báo các tùy chọn bằng `<arg>`.
2. **Dùng `<arg line>` cho dữ liệu động có khoảng trắng hoặc dấu nháy.** Nên tách từng tham số và truyền nội dung động bằng `value` hay đường dẫn bằng `file`.
3. **Tự chèn dấu nháy vào `value`.** Dấu nháy có thể được gửi như một phần dữ liệu, vì ở đây không có shell để loại bỏ nó.
4. **Giả định wildcard, pipe, redirection hay `&&` được thực thi.** Hãy dùng các task Ant, target với `depends`, hoặc gọi shell tường minh chỉ khi cần.
5. **Giả định mọi hệ điều hành đều có cùng một công cụ.** Tách đối số không cài đặt `git`, `bash` hay các tiện ích Linux trên Windows; cần quản lý tiền điều kiện hoặc chọn task Ant gốc.
6. **Không kiểm tra trạng thái thoát của chương trình.** Với công việc bắt buộc, nên dùng `failonerror="true"` hoặc thu `resultproperty` và chủ động đánh giá mã lỗi.
7. **Gộp dữ liệu không tin cậy vào chuỗi `sh -c`/`cmd /c`.** Điều đó đưa lớp phân tích shell trở lại và có thể làm dữ liệu trở thành một phần cú pháp lệnh.

## 11. Quy trình chuyển một lệnh shell sang cấu hình Ant đa nền tảng

Khi nhận một lệnh từ tài liệu hoặc script cũ, có thể xử lý theo trình tự:

1. **Xác định chương trình thật:** `git`, `java`, `python` hay tiện ích hệ điều hành; phân biệt tên chương trình với các tùy chọn.
2. **Tìm task Ant tương đương:** nếu chỉ copy, delete, mkdir, compile hoặc đóng gói, ưu tiên task có sẵn.
3. **Liệt kê từng đối số logic:** tùy chọn nào đứng riêng, tùy chọn nào cần giá trị ở đối số kế tiếp, giá trị nào là đường dẫn, chuỗi nào chứa khoảng trắng.
4. **Viết `<exec>`/`<java>` với các `<arg>` riêng:** dùng `value` cho chuỗi thông thường, `file` cho đường dẫn đơn, `path` khi đúng ngữ nghĩa danh sách đường dẫn.
5. **Chuyển phần phụ thuộc shell sang Ant:** thay `&&` bằng target với `depends`, chuyển hướng bằng thuộc tính output thích hợp hoặc task ghi file, wildcard tệp bằng `<fileset>`.
6. **Chỉ dùng shell cho thao tác thực sự cần nó:** tách nhánh hệ điều hành khi bắt buộc và kiểm soát dữ liệu đưa vào chuỗi shell.
7. **Quan sát kết quả ở từng nền tảng dự kiến:** xem số lượng đối số, đường dẫn thực tế, output và exit code; xác nhận chương trình yêu cầu có mặt ở môi trường build.

Ví dụ một mục tiêu như "sao chép các file `.properties` sang thư mục build rồi chạy chương trình Java với tên dự án chứa khoảng trắng" nên được mô tả thành hai target Ant và các đối số của `<java>`. Khi đó Ant trực tiếp quản lý tác vụ sao chép, đường dẫn và thứ tự thực hiện, còn chương trình Java nhận những giá trị riêng biệt.

**Nguyên tắc cốt lõi:** một tham số logic nên được truyền thành **một đối số có cấu trúc**. Tách `executable` khỏi các `<arg>`, dùng các task Ant khi có sẵn và chỉ gọi shell có chủ đích sẽ giúp build ít nhạy cảm hơn với dấu cách, dấu nháy, quy tắc phân cách đường dẫn và khác biệt giữa các hệ điều hành.
