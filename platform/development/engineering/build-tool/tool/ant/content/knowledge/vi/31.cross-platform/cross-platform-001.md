# Thiết kế đường dẫn độc lập với Windows, Linux và macOS trong Apache Ant

## 1. Vì sao đường dẫn là một phần của thiết kế build đa nền tảng?

Một dự án Java có thể dùng cùng mã nguồn trên Windows, Linux và macOS, nhưng quá trình build vẫn thất bại nếu file `build.xml` giả định một hệ điều hành cụ thể. Ví dụ, đường dẫn `C:\work\app\src` chỉ có ý nghĩa trên một số máy Windows; `/home/dev/app/src` không phải vị trí mặc định trên Windows; danh sách các JAR ngăn bởi dấu `;` hoạt động theo quy ước Windows nhưng Linux và macOS thường dùng dấu `:`. Tên file `Main.java` và `main.java` cũng có thể được hệ thống file xử lý khác nhau.

Trong Apache Ant, thiết kế đường dẫn đa nền tảng có nghĩa là **mô tả vị trí file theo cấu trúc dự án và để các tác vụ Ant xử lý quy tắc của hệ điều hành hiện tại**. Tính di động không đơn thuần là đổi `\` thành `/`: nó bao gồm cách xác định thư mục gốc, tạo đường dẫn, gom nhiều đường dẫn thành classpath, chọn file, gọi chương trình bên ngoài, xử lý khoảng trắng và các khác biệt của hệ thống file.

Một build có thiết kế tốt cho phép ba người cùng checkout một repository ở ba vị trí bất kỳ rồi dùng cùng lệnh logic:

```text
Windows: C:\Users\Lan\Java Projects\portable-demo
Linux:   /home/lan/work/portable-demo
macOS:   /Users/lan/Projects/portable-demo
```

Họ không cần sửa `build.xml` để khớp với thư mục cá nhân hoặc ký tự phân cách của máy mình. Kết quả build được đặt tương đối theo gốc dự án, hoặc theo một thư mục đầu ra do môi trường build cung cấp có chủ đích.

## 2. Những khác biệt cần phân biệt

| Khía cạnh | Windows | Linux | macOS | Điều cần làm trong Ant |
|---|---|---|---|---|
| Ký tự phân cách thư mục quen thuộc | `\` | `/` | `/` | Dùng đường dẫn tương đối, thuộc tính `location` và các tác vụ file của Ant; trong đường dẫn Ant thường có thể viết `/` trên cả ba hệ điều hành. |
| Đường dẫn tuyệt đối | `C:\work\app`, đường dẫn UNC | `/home/user/app` | `/Users/user/app` | Không cố định đường dẫn máy cá nhân trong `build.xml`. |
| Phân cách *danh sách* đường dẫn | `;` trong classpath | `:` trong classpath | `:` trong classpath | Dùng `<path>`, `<pathelement>`, `<fileset>` thay vì tự nối chuỗi bằng `;` hay `:`. |
| Phân biệt chữ hoa/chữ thường | Thường không phân biệt với cấu hình mặc định | Thường phân biệt | Thường không phân biệt với cấu hình mặc định, nhưng có thể được cấu hình khác | Giữ chính xác tên và chữ hoa/thường trong mã nguồn, tài nguyên, manifest và đường dẫn. |
| Tên và ký tự file hợp lệ | Có nhiều tên dành riêng và hạn chế ký tự | Quy tắc đặt tên khác | Quy tắc đặt tên khác | Chọn tên file có thể dùng chung, tránh tên dành riêng và ký tự đặc biệt không cần thiết. |
| Giới hạn độ dài đường dẫn, liên kết, quyền file | Phụ thuộc cấu hình Windows và filesystem | Phụ thuộc filesystem và quyền Unix | Phụ thuộc filesystem và quyền Unix | Giữ cấu trúc thư mục hợp lý, xử lý lỗi đọc/ghi và không giả định hỗ trợ symlink hoặc quyền thực thi giống nhau. |

Đường dẫn thư mục `src/main/java` và biến môi trường `PATH` là **hai vấn đề khác nhau**. `src/main/java` mô tả cây file; `PATH` là danh sách thư mục mà hệ điều hành dùng khi tìm lệnh. Tương tự, `file.separator` mô tả dấu phân cách thành phần đường dẫn; `path.separator` mô tả dấu phân cách giữa các đường dẫn trong một danh sách. Nhầm lẫn hai loại separator này là nguyên nhân phổ biến khiến classpath chỉ chạy trên một nền tảng.

## 3. Nguyên tắc cốt lõi: một gốc dự án, các đường dẫn dẫn xuất

Ant có khái niệm **base directory** (`basedir`) của project. Nếu `build.xml` nằm ở gốc repository, khai báo:

```xml
<project name="portable-demo" default="dist" basedir=".">
    <!-- Các target đặt ở đây. -->
</project>
```

Với `basedir="."`, các đường dẫn tương đối trong project này được hiểu từ thư mục chứa file build, không phải từ một thư mục cá nhân được hardcode. Ant cung cấp property `${basedir}` cho gốc project. Ta có thể dùng đường dẫn tương đối với thuộc tính `location`:

```xml
<property name="src.dir" location="src/main/java"/>
<property name="resources.dir" location="src/main/resources"/>
<property name="build.dir" location="out"/>
<property name="classes.dir" location="${build.dir}/classes"/>
<property name="dist.dir" location="${build.dir}/dist"/>
<property name="jar.file" location="${dist.dir}/portable-demo.jar"/>
```

Khi Ant xử lý `location`, nó phân giải đường dẫn tương đối dựa trên `basedir` và biểu diễn đường dẫn theo hệ thống file hiện tại. Vì vậy cùng cấu hình `location="src/main/java"` có thể tham chiếu đến `C:\Users\Lan\Java Projects\portable-demo\src\main\java` trên Windows hoặc `/home/lan/work/portable-demo/src/main/java` trên Linux.

Một số quy tắc thiết kế hữu ích:

1. **Khai báo gốc và đường dẫn ở một nơi.** Tránh rải nhiều chuỗi `build`, `dist`, `classes` viết độc lập trong các target.
2. **Dẫn xuất đường dẫn con từ thư mục cha.** Khi thay `build.dir`, `classes.dir` và `dist.dir` cùng đổi theo.
3. **Ưu tiên `location` cho property có ý nghĩa file/thư mục.** `value` phù hợp với dữ liệu chuỗi chung; `location` cho Ant cơ hội phân giải path ở thời điểm khai báo.
4. **Dùng đúng thuộc tính của task.** `dir`, `srcdir`, `destdir`, `file`, `todir`, `destfile` và `classpath` thể hiện ý nghĩa rõ ràng hơn chuỗi lệnh shell.
5. **Không dựa vào thư mục hiện hành tình cờ của shell.** Đặc biệt với `<exec>`, đặt `dir` cụ thể nếu chương trình ngoài đọc/ghi file tương đối.

Chú ý: property truyền từ dòng lệnh bằng `-D` có thể ghi giá trị ưu tiên trước khai báo `<property>`. Vì vậy, một property được viết bằng `location` trong `build.xml` **không tự động chuẩn hóa** giá trị đã được người gọi override. Khi cho phép cấu hình vị trí đầu ra từ CI, phải quy định rõ tham số nhận đường dẫn tuyệt đối hay đường dẫn tương đối và kiểm soát các vị trí có thể bị xóa bởi `clean`.

## 4. Ví dụ hoàn chỉnh: một `build.xml` dùng trên ba hệ điều hành

Ta dùng cấu trúc nhỏ, không cần thư viện bên ngoài:

```text
portable-demo/
├── build.xml
├── src/
│   └── main/
│       ├── java/
│       │   └── example/
│       │       └── Main.java
│       └── resources/             # có thể không tồn tại
└── out/                           # được Ant tạo, không commit
    ├── classes/
    └── dist/
        └── portable-demo.jar
```

File `src/main/java/example/Main.java`:

```java
package example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Portable build with Apache Ant");
    }
}
```

File `build.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="portable-demo" default="dist" basedir=".">

    <!-- 1. Khai báo đường dẫn dựa trên gốc project. -->
    <property name="src.dir" location="src/main/java"/>
    <property name="resources.dir" location="src/main/resources"/>
    <property name="build.dir" location="out"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.dir" location="${build.dir}/dist"/>
    <property name="jar.file" location="${dist.dir}/portable-demo.jar"/>

    <!-- 2. Kiểm tra dữ liệu đầu vào của build. -->
    <target name="validate">
        <available file="${src.dir}"
                   type="dir"
                   property="src.exists"/>
        <fail unless="src.exists"
              message="Thiếu thư mục mã nguồn: ${src.dir}"/>
    </target>

    <!-- 3. Tạo đầu ra; mkdir hoạt động trên cả ba hệ điều hành. -->
    <target name="prepare" depends="validate">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <!-- 4. Gọi compiler qua task javac của Ant. -->
    <target name="compile" depends="prepare">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8"
               release="17"/>
    </target>

    <!-- 5. Copy resource nếu thư mục resource tồn tại. -->
    <target name="copy-resources" depends="prepare">
        <copy todir="${classes.dir}">
            <fileset dir="${resources.dir}"
                     erroronmissingdir="false"/>
        </copy>
    </target>

    <!-- 6. Tạo JAR tại đường dẫn dẫn xuất, không dùng dấu ổ đĩa. -->
    <target name="dist" depends="compile,copy-resources">
        <jar destfile="${jar.file}" basedir="${classes.dir}">
            <manifest>
                <attribute name="Main-Class" value="example.Main"/>
            </manifest>
        </jar>
    </target>

    <!-- 7. Chạy JAR qua task java, không viết lệnh shell. -->
    <target name="run" depends="dist">
        <java jar="${jar.file}"
              fork="true"
              failonerror="true"/>
    </target>

    <!-- 8. Chỉ xóa thư mục đầu ra mà build này sở hữu. -->
    <target name="clean">
        <delete dir="${build.dir}"/>
    </target>
</project>
```

Ví dụ dùng **JDK 17 trở lên** cùng phiên bản Apache Ant hỗ trợ thuộc tính `release` của `<javac>`. Nếu dự án dùng JDK khác, thay giá trị release theo Java mục tiêu và phiên bản Ant phù hợp. Thư mục tài nguyên được xem là tùy chọn nhờ `erroronmissingdir="false"` ở `<fileset>`.

Chạy từ thư mục `portable-demo/`:

```bash
ant -f build.xml clean
ant -f build.xml dist
ant -f build.xml run
```

Các lệnh Ant và tên target giống nhau trong PowerShell, Command Prompt, Bash và Zsh; phần khác biệt chỉ là cách cài JDK/Ant và gọi executable `ant` trong môi trường. Bạn có thể chạy `ant -f <đường-dẫn-đến-build.xml> dist` từ thư mục khác khi đường dẫn tới build file được shell đó hiểu đúng.

`out/` sẽ được tạo dưới gốc của `portable-demo` trên từng máy. Ví dụ này cố ý để `out/` ở mức project vì dễ hiểu; nếu nhiều job cùng build đồng thời trên chung workspace thì nên dẫn xuất thư mục đầu ra theo project/job/run riêng để tránh ghi đè. Không đưa `out/` vào Git.

### 4.1. Vì sao ví dụ không dùng lệnh `mkdir`, `cp`, `del` hay `rm` của shell?

Các lệnh và cú pháp shell khác nhau giữa các hệ điều hành:

```text
Windows cmd.exe:   mkdir out\classes
Linux/macOS shell: mkdir -p out/classes
Windows cmd.exe:   del file.txt
Linux/macOS shell: rm file.txt
```

Trong Ant, `<mkdir>`, `<copy>`, `<move>`, `<delete>`, `<javac>`, `<jar>` và `<java>` cung cấp thao tác trực tiếp mà không buộc build script phải biết shell đang chạy. Vì thế, với thao tác file và Java thông thường, ưu tiên task gốc của Ant trước khi gọi một lệnh nền tảng riêng.

## 5. Phân biệt đường dẫn đơn, tập file và danh sách classpath

Ba khái niệm khác nhau nên dùng ba loại cấu hình phù hợp:

| Cần mô tả | Dùng trong Ant | Ví dụ |
|---|---|---|
| Một file hoặc thư mục cụ thể | `location`, `file`, `dir`, `destdir` | `<property name="src.dir" location="src/main/java"/>` |
| Một nhóm file theo mẫu | `<fileset>`, `<patternset>` | `<fileset dir="${lib.dir}" includes="**/*.jar"/>` |
| Một danh sách thư mục/JAR trên classpath | `<path>`, `<pathelement>`, `<fileset>` | `<path id="compile.classpath">...</path>` |

### 5.1. Không nối classpath bằng dấu cố định

Cách dễ lỗi:

```xml
<!-- Không di động: dấu ; phù hợp Windows, không phù hợp Unix. -->
<property name="compile.classpath"
          value="lib/a.jar;lib/b.jar;${classes.dir}"/>
```

Thay bằng kiểu dữ liệu `path` của Ant:

```xml
<property name="lib.dir" location="lib"/>

<path id="compile.classpath">
    <pathelement location="${classes.dir}"/>
    <fileset dir="${lib.dir}"
             includes="**/*.jar"
             erroronmissingdir="false"/>
</path>

<target name="compile-with-dependencies" depends="prepare">
    <javac srcdir="${src.dir}"
           destdir="${classes.dir}"
           includeantruntime="false"
           encoding="UTF-8"
           release="17">
        <classpath refid="compile.classpath"/>
    </javac>
</target>
```

Ở đây `<fileset>` chọn các JAR trong `lib/`, còn `<path>` giữ từng thành phần classpath. Ant xây dựng biểu diễn classpath phù hợp với máy đang chạy. Không cần biết phải dùng `;` hay `:`. Nếu ứng dụng thực sự phụ thuộc các JAR trong `lib`, **classpath khi chạy** cũng phải được cấu hình tương ứng; đóng gói riêng class vào một JAR thông thường không tự động đóng gói toàn bộ dependency.

Trong Java, `file.separator` và `path.separator` là hai thuộc tính hệ thống khác nhau. Ant có thể truy cập `${file.separator}` và `${path.separator}` trong nhiều ngữ cảnh, nhưng việc tự ghép chuỗi bằng các property đó thường làm script khó đọc và vẫn dễ bỏ sót trường hợp đặc biệt. `<path>` và các tham số đường dẫn có ý nghĩa của task nên là lựa chọn mặc định.

### 5.2. Không dùng shell glob khi Ant đã có `<fileset>`

Trong Bash, biểu thức `src/**/*.java` có thể được shell mở rộng theo một cấu hình nhất định; trong PowerShell hoặc `cmd.exe`, quy tắc mở rộng khác. Nếu Ant được gọi qua các shell hoặc script khác nhau, không nên dựa vào việc shell tự mở rộng wildcard.

Ant có patternset riêng:

```xml
<copy todir="${build.dir}/config">
    <fileset dir="src/main/resources"
             includes="**/*.properties,**/*.xml"
             excludes="**/*.secret"/>
</copy>
```

Trong pattern Ant, dấu `/` thường dùng để phân cấp thư mục ngay cả khi build chạy trên Windows. `**` đại diện cho nhiều cấp thư mục, còn `*` đại diện cho tên phù hợp trong một cấp. `<fileset>` sẽ duyệt cây thư mục bằng API file của Java/Ant; không phụ thuộc vào việc shell có hiểu `**` hay không. Lưu ý thư mục `src/main/resources` trong ví dụ trên phải tồn tại, trừ khi cấu hình `erroronmissingdir="false"`.

### 5.3. Khi nào cần `<pathconvert>`?

Một vài công cụ ngoài Ant bắt buộc nhận classpath hoặc danh sách file dưới dạng **một chuỗi duy nhất**. Khi đó, có thể chuyển `<path>` thành property để truyền vào công cụ, thay vì tự nối dấu phân cách:

```xml
<pathconvert property="tool.classpath"
             refid="compile.classpath"/>

<echo message="Classpath cho hệ điều hành hiện tại: ${tool.classpath}"/>
```

Nếu đang tạo một file cấu hình cho **hệ điều hành đích khác** với máy build, `<pathconvert>` còn hỗ trợ `targetos="windows"` hoặc `targetos="unix"`. Nhưng cần hiểu ranh giới: chuyển dấu phân cách của một chuỗi **không** tự biến đường dẫn máy Linux thành đường dẫn thực sự tồn tại trên Windows, và không làm executable của hệ điều hành khác chạy được trên máy hiện tại.

## 6. Gọi công cụ bên ngoài mà không làm hỏng đường dẫn có khoảng trắng

`<exec>` cần thiết khi tác vụ Ant chuẩn không hỗ trợ một công cụ cụ thể. Đây cũng là nơi dễ xảy ra lỗi đa nền tảng nếu người viết trộn việc ghép đường dẫn với cú pháp shell.

Ví dụ không nên dùng cho mục tiêu chạy trên cả ba OS:

```xml
<!-- Dễ lỗi: phụ thuộc shell Unix, quote/redirect và executable. -->
<exec executable="sh">
    <arg value="-c"/>
    <arg value="java -jar out/dist/portable-demo.jar > out/run.log"/>
</exec>
```

Lệnh trên yêu cầu có `sh`, có quy tắc redirection của shell và tự xử lý dấu cách trong path. Nếu chỉ cần chạy JAR, `<java jar="..." fork="true"/>` như ví dụ hoàn chỉnh là gọn và di động hơn.

Nếu bắt buộc dùng `<exec>`, truyền mỗi đối số một cách tường minh:

```xml
<target name="inspect-jar" depends="dist">
    <exec executable="jar"
          dir="${basedir}"
          failonerror="true">
        <arg value="tf"/>
        <arg file="${jar.file}"/>
    </exec>
</target>
```

`<arg value="tf"/>` và `<arg file="${jar.file}"/>` tạo **hai tham số**, bất kể `${jar.file}` có khoảng trắng hay không. Đừng viết cả lệnh thành một `<arg line="..."/>` với phần quote tự ghép trừ khi thật sự hiểu cách Ant phân tích command line. `jar` là công cụ đi kèm JDK, nhưng `<exec executable="jar">` chỉ tìm thấy nó nếu executable đó có thể được hệ điều hành tìm thấy qua môi trường thực thi; các máy có thể cấu hình `PATH` khác nhau.

Một chương trình có thể mong nhận đường dẫn theo định dạng riêng, chẳng hạn công cụ không chấp nhận dấu `/` trên Windows, hoặc mong dấu `:` và `;` theo hệ điều hành đích. Khi đó hãy đọc hợp đồng tham số của chính chương trình đó, dùng `file`/`path` của Ant ở nơi phù hợp, và chuyển đổi đúng tại biên gọi công cụ. Không có một phép thay thế toàn cục mọi `\` thành `/` giải quyết được tất cả công cụ ngoài.

Nếu công cụ chỉ có phiên bản Windows hoặc dùng `cmd /c`/`bash -c`, build đó không thể coi là độc lập hệ điều hành. Có thể phân nhánh theo OS bằng `<condition>` và thuộc tính `<os>`, nhưng nên cô lập nhánh đặc thù ở một target/adaptor thay vì để các lệnh OS rải rác khắp build file.

## 7. Đường dẫn khi build nhiều module và khi dùng `<ant>`/`<subant>`

Với repository nhiều module, `build.xml` ở root có thể lấy `project.id` để tính vị trí source. Quy tắc chung vẫn là xác định đường dẫn từ root:

```xml
<property name="modules.root" location="modules"/>
<property name="module.dir" location="${modules.root}/${project.id}"/>
<property name="module.src" location="${module.dir}/src/main/java"/>
<property name="module.out" location="${basedir}/out/${project.id}"/>
```

Người gọi truyền `-Dproject.id=alpha` hoặc `-Dproject.id=beta`. Chỉ nên cho phép `project.id` thuộc một tập ID hợp lệ hoặc kiểm tra rõ ràng trước khi dùng vào đường dẫn. Không nhận tùy ý `../another-folder` từ người dùng hay nguồn không tin cậy rồi ghép trực tiếp vào `${module.dir}`; việc đó phá vỡ giới hạn thư mục dự kiến.

Khi gọi Ant con, phải hiểu `basedir` của project con có thể khác project cha. Ví dụ:

```xml
<target name="build-child">
    <ant antfile="modules/alpha/build.xml"
         target="dist"
         inheritAll="false">
        <property name="output.root" location="${basedir}/out/alpha"/>
    </ant>
</target>
```

Đoạn này minh họa việc truyền một đường dẫn đầu ra đã xác định từ project cha vào Ant con. Build con phải thực sự đọc `${output.root}` để sử dụng; truyền property không tự tạo ra tác dụng. `inheritAll="false"` giúp tránh kế thừa toàn bộ property của cha một cách vô tình, nhưng các property do Ant quản lý và các property dòng lệnh vẫn có quy tắc kế thừa/ưu tiên riêng. Muốn hệ thống build con hoạt động ổn định, hãy định nghĩa rõ hợp đồng tham số giữa các build file và kiểm soát cả gốc tính đường dẫn.

Lưu ý Ant `<import>` và `<include>` có quy tắc đường dẫn riêng: task trong file được import vẫn chịu ngữ cảnh project mà nó tham gia, nên không được giả định mọi path tương đối sẽ tự tính theo vị trí của file XML dùng chung. Với build logic chia sẻ giữa nhiều module, công khai property chỉ đến root/module của từng lượt gọi và thử thiết kế trong nhiều layout checkout khác nhau.

## 8. Khác biệt hệ thống file không thể bỏ qua

### 8.1. Phân biệt chữ hoa và chữ thường

Giả sử source được đặt tên `src/main/java/example/Service.java` nhưng script lại tham chiếu `src/main/java/example/service.java`. Tùy filesystem, truy cập có thể thành công trên một máy và thất bại trên máy khác. Trường hợp tệ hơn là repository chứa hai file chỉ khác nhau ở chữ hoa/chữ thường (`Config.xml` và `config.xml`), dẫn tới xung đột khi checkout trên filesystem không phân biệt chữ hoa/thường.

Quy ước tên file nhất quán, dùng đúng kiểu chữ trong mọi đường dẫn, tránh cặp tên chỉ khác chữ hoa/thường và không dựa vào việc hệ thống file tự sửa lỗi. Điều này đặc biệt quan trọng với nguồn Java, resource trên classpath và tên trong `MANIFEST.MF`.

### 8.2. Tên dành riêng và ký tự đặc biệt

Một số tên như `CON`, `PRN`, `AUX`, `NUL`, `COM1` hoặc `LPT1` được Windows dành riêng trong nhiều ngữ cảnh; dấu `:` cũng là một phần của cú pháp ổ đĩa trên Windows và thường không phù hợp trong tên file. Tránh dùng ký tự `\ / : * ? " < > |` trong tên artifact hoặc thư mục con cần chạy trên Windows. Trong XML, các ký tự `&`, `<` có quy tắc escape riêng; đây là vấn đề cú pháp XML, độc lập với OS.

Nếu đường dẫn được tạo từ tên branch, user input hay nhãn job CI, đừng ghép nguyên văn. Hãy chuyển thành ID thư mục có tập ký tự được kiểm soát, ví dụ chữ Latin không dấu, số, dấu gạch ngang và gạch dưới; xử lý cả trường hợp tên trùng sau khi chuẩn hóa.

### 8.3. Dấu cách, Unicode và đường dẫn dài

Checkout ở `C:\Users\Lan\Java Projects\portable-demo` có khoảng trắng vẫn là trường hợp hợp lệ. Task Ant nhận path bằng thuộc tính như `file`, `dir`, `destfile`, `location` sẽ tránh phần lớn lỗi quote của shell. Với công cụ ngoài, truyền từng tham số, như `<arg file="..."/>`. Không giả định người dùng phải đặt workspace dưới `C:\code` chỉ để build chạy được.

Tên thư mục Unicode có thể hoạt động tốt nhưng phụ thuộc vào encoding, console và công cụ ngoài. Chỉ định encoding khi biên dịch (`encoding="UTF-8"`), dùng file XML UTF-8, và cân nhắc khả năng công cụ ngoài xử lý tên path Unicode. Ngoài ra, cấu trúc thư mục quá sâu có thể va vào giới hạn độ dài đường dẫn trên một số thiết lập Windows; nên giữ tên thư mục artifact có độ dài vừa phải và không coi một cấu hình filesystem cụ thể là đại diện cho mọi máy.

### 8.4. Quyền, symlink và chữ hoa/thường của volume

Script `.sh` có thể cần quyền thực thi trên Linux/macOS; file `.bat` là trường hợp riêng của Windows. Symbolic link, vị trí file tạm và quyền ghi cũng khác nhau theo máy và cấu hình. Ant giúp thao tác trên file nhưng không xóa bỏ khác biệt của filesystem. Nếu build cần symlink hoặc gọi script, mô tả điều kiện môi trường rõ ràng thay vì kỳ vọng mọi máy giống nhau.

## 9. Dọn đầu ra mà không phụ thuộc vị trí checkout

Build tái lập thường cần xóa sản phẩm cũ trước khi build lại. Quy tắc quan trọng là **chỉ xóa thư mục do build sở hữu**, ví dụ:

```xml
<property name="build.dir" location="out"/>

<target name="clean">
    <delete dir="${build.dir}"/>
</target>
```

`out` được tính từ project, nên dọn đúng output của checkout hiện tại. Không viết:

```xml
<!-- Không di động và có nguy cơ xóa nhầm vùng chia sẻ. -->
<delete dir="C:\temp\build"/>
```

Nếu CI cho phép truyền `-Dbuild.dir=...`, phải xác định `build.dir` có nằm trong vùng được phép dọn hay không. Đây là ranh giới giữa tính di động và quyền sở hữu đường dẫn: property `location` hỗ trợ quy tắc path, nhưng **không phải cơ chế bảo vệ** trước người có thể tùy ý override property hoặc sửa `build.xml`. Trong môi trường nhiều job chạy cùng lúc, thiết kế đường dẫn đầu ra theo project và run riêng để một lệnh `clean` không xóa file mà job khác đang dùng.

Tách thư mục build cũng chỉ giải quyết phần trạng thái trên filesystem. Với mục tiêu build byte-for-byte tái lập, cần kiểm soát thêm phiên bản JDK/Ant, dependency, encoding, timestamp và metadata khi đóng gói JAR.

## 10. Chạy và quan sát trên Windows, Linux, macOS

Khi thiết kế pipeline đa nền tảng, có thể tổ chức cùng một trình tự logic cho từng OS:

```text
Checkout mã nguồn
        ↓
Xác nhận JDK và Ant phù hợp
        ↓
ant -f build.xml clean
        ↓
ant -f build.xml dist
        ↓
Kiểm tra artifact trong out/dist/
        ↓
Lưu artifact từ chính workspace của job
```

Cùng lệnh `ant -f build.xml dist` có thể dùng trên ba hệ điều hành khi `ant` được cấu hình trong `PATH` và working directory chứa build file. Để quan sát Ant đang dùng gốc và đường dẫn nào, có thể bổ sung một target chẩn đoán **chỉ đọc**:

```xml
<target name="show-paths">
    <echo message="OS: ${os.name}"/>
    <echo message="basedir: ${basedir}"/>
    <echo message="src.dir: ${src.dir}"/>
    <echo message="classes.dir: ${classes.dir}"/>
    <echo message="jar.file: ${jar.file}"/>
    <echo message="file.separator: ${file.separator}"/>
    <echo message="path.separator: ${path.separator}"/>
</target>
```

Ant tiếp nhận các system property của Java như `os.name`, `file.separator`, `path.separator`; đây là thông tin phục vụ quan sát, không phải yêu cầu phải tự ghép path bằng chuỗi. Khi build thất bại trên một OS, log các đường dẫn đã phân giải sẽ giúp biết build đang đọc/ghi tại đâu.

Để đánh giá tính đa nền tảng của thiết kế, các tình huống có giá trị quan sát gồm:

1. **Checkout ở thư mục có khoảng trắng** và chạy `dist`, `run`.
2. **Chạy bằng cùng file `build.xml` trên ba OS** mà không sửa hardcoded path.
3. **Xóa `out/` rồi build từ đầu** để phát hiện input vô tình đến từ file cũ.
4. **Sử dụng tên file có chữ hoa/thường đúng với repository** để phát hiện sai khác case-sensitive.
5. **Kiểm tra classpath khi có thư viện** để bảo đảm Ant tạo danh sách đường dẫn theo hệ điều hành hiện tại.
6. **Gọi công cụ ngoài với đường dẫn chứa khoảng trắng** để phát hiện việc tự ghép command string gây lỗi.

Các tình huống trên nhằm quan sát hành vi thực tế của build; cùng một hệ điều hành vẫn có thể khác nhau do filesystem, quyền và môi trường cài công cụ.

## 11. Những lỗi thiết kế thường gặp

**Hardcode vị trí workspace.** `C:\dev\my-app` hoặc `/Users/alice/Projects/my-app` khiến người khác phải sửa file build. Hãy dùng `basedir`, đường dẫn tương đối và property `location`.

**Tự viết classpath bằng dấu `;` hoặc `:`.** Một chuỗi có thể chạy trên Windows nhưng không chạy trên Linux/macOS. Hãy dùng `<path>`, `<pathelement>` và `<fileset>`.

**Dùng `\` tùy tiện cho đường dẫn và pattern Ant.** Trong Ant XML và file pattern, dùng `/` theo cấu trúc thư mục, để Ant chuẩn hóa khi cần. Với chương trình ngoài, tuân theo cú pháp đường dẫn mà chương trình ấy thật sự chấp nhận.

**Gọi shell để thực hiện việc Ant đã hỗ trợ.** `rm -rf`, `cp -r`, `mkdir -p` và `del` làm build phụ thuộc vào môi trường. Dùng `<delete>`, `<copy>`, `<mkdir>` khi phù hợp.

**Ghép đường dẫn có khoảng trắng vào một command string.** Shell có thể tách sai thành nhiều tham số. Trong `<exec>`, tách thành từng `<arg>` và dùng `file` cho tham số là đường dẫn.

**Dựa vào tên file không đúng kiểu chữ.** Một filesystem bỏ qua khác biệt hoa/thường có thể che giấu lỗi mà Linux phát hiện ngay. Giữ tên file và tham chiếu trùng khớp tuyệt đối.

**Tưởng rằng đổi dấu phân cách sẽ làm công cụ ngoài di động.** Một script `.bat` vẫn là script Windows dù path được viết bằng `/`. Hãy thay bằng tác vụ Ant, công cụ Java đa nền tảng hoặc nhánh OS có phạm vi rõ ràng.

**Cho phép `clean` xóa vùng ngoài project.** Đường dẫn có thể được override từ dòng lệnh; chỉ chạy thao tác xóa với cấu hình đã kiểm soát, tránh dùng thư mục chung khi nhiều job chạy song song.

## 12. Nguyên tắc áp dụng vào dự án thật

Khi thiết kế một build Ant đa nền tảng, hãy xem **đường dẫn là dữ liệu có cấu trúc**: một gốc repository rõ ràng, các đường dẫn đơn biểu diễn qua thuộc tính file/location, các nhóm file qua resource collection và các danh sách classpath qua `<path>`. Cú pháp hệ điều hành chỉ nên xuất hiện ở biên gọi chương trình thực sự yêu cầu nó.

Nếu có thể checkout cùng nguồn tại `C:\Users\...`, `/home/...` và `/Users/...`, chạy cùng target Ant và nhận JAR từ thư mục đầu ra tương ứng mà không chỉnh file build, thiết kế đã đạt một nền tảng quan trọng của tính di động. Các khác biệt còn lại — toolchain, case-sensitive, quyền, encoding, symlink và metadata — phải được kiểm soát theo yêu cầu của dự án để build hoạt động nhất quán trên Windows, Linux và macOS.
