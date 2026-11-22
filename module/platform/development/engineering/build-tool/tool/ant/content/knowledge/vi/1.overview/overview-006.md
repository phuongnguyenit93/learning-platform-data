# Task có sẵn, task tùy chọn và phần mở rộng bên ngoài

Trong Apache Ant, một **task** là đơn vị thực hiện một hành động trong quá trình build. Task thường xuất hiện bên trong một `target`, còn target gom các bước có liên quan thành một công đoạn như chuẩn bị thư mục, biên dịch, kiểm thử hoặc đóng gói.

```xml
<project name="sample" default="package" basedir=".">
    <target name="prepare">
        <mkdir dir="build"/>
    </target>

    <target name="package" depends="prepare">
        <echo message="Đang chuẩn bị gói ứng dụng"/>
    </target>
</project>
```

Trong ví dụ trên, `mkdir` và `echo` là tên task. Ant tìm cách thực thi tương ứng với từng tên task khi đọc build file. Phần lớn task quen thuộc đã được Ant cung cấp sẵn; một số task cần thư viện bổ sung; và dự án có thể nạp thêm task từ thư viện bên ngoài hoặc tự viết task riêng.

Ba nhóm này có cách phân phối và yêu cầu môi trường khác nhau. Hiểu rõ chúng giúp build file dễ chạy trên máy của lập trình viên, máy CI và các môi trường khác.

## 1. Task có sẵn trong Ant Core

**Core task** là các task thuộc phần lõi của Apache Ant. Chúng được cung cấp cùng Ant và là nền tảng cho các thao tác build thông dụng. Với một bản cài đặt Ant bình thường, bạn có thể dùng chúng trực tiếp mà không cần cài thêm thư viện task riêng.

Một số task thường gặp:

| Nhóm công việc | Task tiêu biểu | Công dụng |
|---|---|---|
| Thông báo và điều khiển | `echo`, `fail`, `condition`, `available` | In thông báo, dừng build khi điều kiện không đạt, kiểm tra điều kiện hoặc sự tồn tại của tài nguyên |
| Thuộc tính và đường dẫn | `property`, `path` | Khai báo giá trị dùng lại và tập hợp đường dẫn classpath |
| Hệ thống tệp | `mkdir`, `delete`, `copy`, `move`, `touch` | Tạo, xóa, sao chép, di chuyển và cập nhật thời gian tệp |
| Biên dịch và chạy Java | `javac`, `java` | Biên dịch mã nguồn Java và chạy lớp Java |
| Đóng gói | `jar`, `zip`, `unzip`, `manifest` | Tạo hoặc giải nén archive và xây dựng manifest |
| Tiến trình bên ngoài | `exec` | Gọi chương trình hoặc lệnh của hệ điều hành |
| Tài liệu và kiểm tra | `javadoc`, `checksum`, `uptodate` | Sinh tài liệu, tính checksum và kiểm tra trạng thái cập nhật |
| Điều phối build | `ant`, `antcall`, `subant` | Gọi build file khác, target khác hoặc build ở các thư mục con |

Đây là các ví dụ tiêu biểu, không phải danh sách đầy đủ. Danh sách và hành vi chi tiết phụ thuộc phiên bản Ant đang dùng; tài liệu task của đúng phiên bản là nguồn tham khảo cuối cùng.

### Ví dụ: dùng các Core task để biên dịch và đóng gói

```xml
<project name="hello-ant" default="package" basedir=".">
    <property name="src.dir" value="src"/>
    <property name="build.dir" value="build"/>
    <property name="classes.dir" value="${build.dir}/classes"/>

    <target name="clean">
        <delete dir="${build.dir}"/>
    </target>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac
            srcdir="${src.dir}"
            destdir="${classes.dir}"
            includeantruntime="false"
            encoding="UTF-8"/>
    </target>

    <target name="package" depends="compile">
        <jar
            destfile="${build.dir}/hello.jar"
            basedir="${classes.dir}"/>
        <echo message="Đã tạo ${build.dir}/hello.jar"/>
    </target>
</project>
```

Các task trong ví dụ đều là task tiêu chuẩn của Ant:

1. `property` khai báo các đường dẫn để có thể thay đổi cấu hình tại một nơi.
2. `delete` xóa thư mục build cũ khi cần làm sạch.
3. `mkdir` tạo thư mục chứa bytecode.
4. `javac` gọi trình biên dịch Java để biên dịch mã nguồn.
5. `jar` đóng gói các lớp đã biên dịch thành tệp JAR.
6. `echo` ghi thông báo vào log.

Chạy target mặc định:

```bash
ant
```

Chạy riêng target làm sạch:

```bash
ant clean
```

Task `javac` là task của Ant, nhưng nó vẫn cần một môi trường Java phù hợp. Vì vậy, “có sẵn trong Ant” không có nghĩa là task không cần công cụ hoặc điều kiện bên ngoài. Ví dụ, muốn biên dịch Java thì máy chạy build phải có JDK tương thích; Ant không tự mang theo một trình biên dịch Java độc lập.

### Task và nested element

Một task có thể nhận thuộc tính XML, nested element hoặc cả hai. Ví dụ:

```xml
<copy todir="build/config">
    <fileset dir="src/config">
        <include name="**/*.yml"/>
        <exclude name="local-*.yml"/>
    </fileset>
</copy>
```

Ở đây:

- `copy` là task thực hiện thao tác sao chép.
- `fileset` mô tả tập tệp nguồn.
- `include` và `exclude` xác định mẫu tên tệp cần lấy hoặc loại bỏ.

`fileset` là một data type của Ant được dùng lồng trong task. Không phải mọi thẻ XML trong build file đều là task độc lập; một số thẻ là cấu hình hoặc kiểu dữ liệu mà task hỗ trợ.

## 2. Task tùy chọn của Apache Ant

**Optional task** là task được Ant cung cấp trong hệ sinh thái phân phối của mình nhưng không thuộc nhóm Core task tối thiểu. Chúng thường được tách sang JAR riêng hoặc cần thêm thư viện của bên thứ ba.

Tên gọi “tùy chọn” nói về việc task không phải thành phần lõi luôn có sẵn trong mọi môi trường Ant. Nó không đồng nghĩa với việc task do cộng đồng bên ngoài viết. Một số optional task được duy trì cùng dự án Apache Ant; điều kiện để dùng chúng được ghi trong tài liệu của từng task.

Ví dụ thường gặp:

| Task | Mục đích | Phụ thuộc thường gặp |
|---|---|---|
| `junit` | Chạy bộ kiểm thử bằng JUnit theo cách tích hợp của Ant | JAR task của Ant và thư viện JUnit tương thích |
| `junitlauncher` | Chạy kiểm thử dựa trên JUnit Platform | JAR task tương ứng và các thư viện JUnit Platform cần thiết |
| `ftp` | Trao đổi tệp qua FTP | JAR task FTP và Apache Commons Net |
| `scp`, `sshexec` | Sao chép tệp hoặc thực thi lệnh qua SSH | JAR task SSH và thư viện SSH tương thích, chẳng hạn JSch |
| `jdepend` | Phân tích một số chỉ số phụ thuộc của mã Java | JAR task JDepend và thư viện JDepend |

Tên JAR và phiên bản thư viện có thể thay đổi theo phiên bản Ant. Trước khi cấu hình, hãy xem mục Dependencies hoặc Installation trong tài liệu của task tương ứng; đừng suy luận rằng chỉ cần thêm một JAR có tên gần giống là đủ.

### Phân biệt thư viện triển khai task và classpath của chương trình

Đây là điểm dễ gây nhầm lẫn khi cài optional task.

- **Classpath của Ant** phải chứa lớp triển khai task và các thư viện mà chính task cần để hoạt động. Nếu thiếu, Ant có thể báo không tìm thấy task, không nạp được lớp hoặc gặp `NoClassDefFoundError`.
- **Classpath của chương trình được build hoặc kiểm thử** chứa lớp ứng dụng và các thư viện mà mã ứng dụng cần. Classpath này thường được truyền vào task thông qua nested element như `<classpath>`.

Ví dụ, khi dùng task kiểm thử JUnit, việc đặt JUnit vào classpath của các lớp kiểm thử chưa chắc đã đủ để Ant nạp được chính task `junit`. JAR triển khai task và thư viện mà task cần phải được nhìn thấy bởi classloader của Ant theo hướng dẫn cài đặt của phiên bản đang dùng.

### Cách cung cấp thư viện cho Ant

Có một số cách phổ biến để bổ sung JAR vào classpath của Ant:

**1. Thư mục thư viện của bản cài Ant**

Đặt các JAR cần thiết trong thư mục thư viện của Ant, thường là `ANT_HOME/lib`. Một số bản cài hoặc quy trình quản lý có thể dùng thêm thư mục thư viện riêng của người dùng. Cách này thuận tiện cho máy cá nhân nhưng có thể khiến build phụ thuộc vào cấu hình đã cài trên máy.

**2. Tùy chọn `-lib` khi chạy Ant**

```bash
ant -lib path/to/ant-task-library.jar test
```

Tùy chọn `-lib` bổ sung thư mục hoặc JAR vào classpath của Ant cho lần chạy đó. Có thể dùng nhiều lần nếu task cần nhiều thư viện. Đây là cách rõ ràng khi muốn truyền dependency từ script CI hoặc lệnh chạy.

**3. Khai báo classpath trong `taskdef`**

Với thư viện task cần đăng ký tường minh, có thể khai báo classpath ngay trong build file:

```xml
<taskdef
    name="custom-check"
    classname="com.example.ant.CustomCheckTask">
    <classpath>
        <pathelement location="tools/custom-ant-tasks.jar"/>
        <pathelement location="tools/dependency.jar"/>
    </classpath>
</taskdef>
```

Ví dụ này giả định JAR chứa lớp `CustomCheckTask` và dependency đã được đặt ở các đường dẫn trên. Tên task và class phải đúng với thư viện thực tế. Không phải optional task nào cũng cần tự khai báo `taskdef`: một số task đã có ánh xạ mặc định trong Ant và chỉ cần các JAR cần thiết xuất hiện trên classpath. Hãy theo tài liệu của task.

### Ví dụ cấu hình task JUnit

Ví dụ sau minh họa cách gọi task JUnit cổ điển:

```xml
<target name="test" depends="compile">
    <mkdir dir="build/test-reports"/>

    <junit fork="true" printsummary="yes">
        <classpath>
            <pathelement location="build/classes"/>
            <pathelement location="build/test-classes"/>
        </classpath>

        <formatter type="plain"/>

        <batchtest todir="build/test-reports">
            <fileset dir="build/test-classes">
                <include name="**/*Test.class"/>
            </fileset>
        </batchtest>
    </junit>
</target>
```

Để ví dụ chạy được, môi trường Ant còn phải có task JUnit và các thư viện JUnit phù hợp trên classpath của Ant theo tài liệu phiên bản đang sử dụng. Nested `<classpath>` trong task ở ví dụ trên là classpath dành cho các lớp cần kiểm thử; nó không thay thế việc cài thư viện triển khai optional task.

## 3. Phần mở rộng từ thư viện bên ngoài

Ngoài task do Apache Ant cung cấp, hệ sinh thái Ant cho phép nạp các thư viện mở rộng. Chúng có thể bổ sung task, data type hoặc cơ chế tích hợp với một công cụ khác.

Một số ví dụ:

- **Ant-Contrib** bổ sung các cấu trúc và thao tác như `if`, `for`, `foreach`, `trycatch` và một số tiện ích khác.
- **Apache Ivy** bổ sung các task quản lý dependency như resolve và retrieve.
- Các thư viện do tổ chức hoặc dự án tự phát triển có thể cung cấp task để gọi công cụ nội bộ, kiểm tra quy tắc, triển khai ứng dụng hoặc tích hợp hệ thống.

Các thư viện này không mặc nhiên có trong một bản cài Ant. Dự án phải cung cấp JAR và đăng ký task hoặc antlib theo hướng dẫn của thư viện.

### Ví dụ: đăng ký Ant-Contrib

Một cách đăng ký thường dùng của Ant-Contrib là nạp resource chứa các định nghĩa task:

```xml
<taskdef resource="net/sf/antcontrib/antcontrib.properties">
    <classpath>
        <pathelement location="tools/ant-contrib.jar"/>
    </classpath>
</taskdef>

<target name="conditional-build">
    <if>
        <available file="src/optional"/>
        <then>
            <echo message="Có thư mục nguồn tùy chọn"/>
        </then>
        <else>
            <echo message="Bỏ qua phần nguồn tùy chọn"/>
        </else>
    </if>
</target>
```

Ví dụ minh họa cách đăng ký và sử dụng; hãy dùng đúng JAR, resource và cú pháp tương ứng với phiên bản Ant-Contrib mà dự án chọn. Nếu resource không tồn tại hoặc JAR không nằm trong classpath, Ant không thể đăng ký các task.

### Ví dụ: đăng ký Apache Ivy qua antlib

Antlib là cơ chế đóng gói định nghĩa task và data type theo namespace. Một thư viện có thể cung cấp tệp `antlib.xml` để Ant đọc các định nghĩa của nó.

```xml
<project name="ivy-example"
         default="resolve"
         xmlns:ivy="antlib:org.apache.ivy.ant">

    <taskdef
        resource="org/apache/ivy/ant/antlib.xml"
        uri="antlib:org.apache.ivy.ant">
        <classpath>
            <pathelement location="tools/ivy.jar"/>
        </classpath>
    </taskdef>

    <target name="resolve">
        <ivy:resolve/>
        <ivy:retrieve/>
    </target>
</project>
```

Namespace `ivy` giúp phân biệt task của Ivy với task khác có thể trùng tên. JAR Ivy phải có mặt ở classpath được dùng để nạp antlib; dự án cũng cần cấu hình nguồn dependency phù hợp để Ivy biết nơi lấy artifact. Tên namespace, resource và các bước cấu hình phải khớp với phiên bản Ivy.

## 4. Đăng ký task và data type

Khi dùng một thư viện mở rộng, Ant cần biết tên XML nào tương ứng với lớp Java nào. Hai cơ chế thường gặp là `taskdef` và `typedef`.

| Cơ chế | Dùng để đăng ký | Ví dụ sử dụng |
|---|---|---|
| `taskdef` | Một task hoặc nhóm task | `<custom-check/>` |
| `typedef` | Một data type | `<custom-path/>` hoặc kiểu dữ liệu được lồng trong task |
| antlib | Một nhóm định nghĩa task và data type, thường có namespace | `<ext:custom-check/>` |

### `taskdef`

`taskdef` đăng ký một tên task với lớp triển khai:

```xml
<taskdef
    name="greet"
    classname="com.example.ant.GreetingTask"
    classpath="tools/greeting-ant-task.jar"/>

<target name="hello">
    <greet message="Xin chào từ Ant"/>
</target>
```

Khi Ant gặp thẻ `<greet>`, nó tạo đối tượng từ lớp đã đăng ký, gán các thuộc tính tương ứng và thực thi task. Trong ví dụ này, lớp Java cần có setter tương ứng với thuộc tính `message`, chẳng hạn `setMessage(String value)`.

### `typedef`

`typedef` đăng ký một kiểu dữ liệu do thư viện cung cấp. Data type thường dùng để mô tả cấu hình hoặc dữ liệu có thể tái sử dụng, thay vì trực tiếp thực hiện một hành động như task.

```xml
<typedef
    name="custom-resource"
    classname="com.example.ant.CustomResource"
    classpath="tools/custom-ant-types.jar"/>
```

Sau khi đăng ký, kiểu dữ liệu có thể được dùng ở vị trí mà task hoặc data type cha hỗ trợ kiểu đó. Cách lồng và các thuộc tính hợp lệ do lớp triển khai quy định.

### Namespace và antlib

Khi thư viện cung cấp nhiều task, namespace giúp tránh xung đột tên và làm rõ nguồn gốc của task. Ví dụ, task Ivy được viết dưới dạng `ivy:resolve`, thay vì một tên chung có thể trùng với task của thư viện khác.

Với thư viện tự viết, có thể đóng gói định nghĩa trong một antlib. Khi đó, build file khai báo namespace, nạp resource antlib và dùng tiền tố tương ứng. Hãy giữ tên namespace ổn định để build file dễ đọc và tránh việc hai thư viện vô tình định nghĩa cùng một tên task trong cùng namespace.

## 5. Tự viết task khi cần mở rộng Ant

Nếu các task hiện có không đáp ứng được một thao tác có tính lặp lại hoặc chứa logic riêng của dự án, nhóm phát triển có thể viết task Java.

Task Java thường kế thừa `org.apache.tools.ant.Task`, cung cấp setter cho các thuộc tính cấu hình và ghi đè phương thức `execute()`.

```java
package com.example.ant;

import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Task;

public class GreetingTask extends Task {

    private String message;

    public void setMessage(String message) {
        this.message = message;
    }

    @Override
    public void execute() throws BuildException {
        if (message == null || message.isBlank()) {
            throw new BuildException("Thuộc tính message không được để trống");
        }

        log(message);
    }
}
```

Sau khi biên dịch lớp này thành JAR và bảo đảm JAR cùng thư viện Ant API tương thích được cấu hình đúng, đăng ký và gọi task trong build file:

```xml
<taskdef
    name="greet"
    classname="com.example.ant.GreetingTask"
    classpath="tools/greeting-ant-task.jar"/>

<target name="hello">
    <greet message="Build đã chạy task tự viết"/>
</target>
```

Trong thực tế, JAR task thường được biên dịch với Ant API tương ứng và không nên đóng gói một bản Ant API khác vào trong JAR task. Nếu task cần thư viện phụ, các dependency đó cũng phải được cung cấp cho classloader nạp task.

### Có nhất thiết phải viết Java task không?

Không. Trước khi tạo lớp Java mới, hãy xem các lựa chọn sau:

- Dùng trực tiếp Core task nếu thao tác đã được hỗ trợ.
- Dùng optional task hoặc thư viện mở rộng đã được dự án chấp nhận nếu nó giải quyết đúng nhu cầu.
- Dùng `macrodef` để gom nhiều task có sẵn thành một thao tác có tên và tham số riêng.
- Dùng `presetdef` để định nghĩa cấu hình mặc định cho một task.
- Viết task Java khi cần logic phức tạp, xử lý dữ liệu riêng hoặc tích hợp có thể tái sử dụng mà các cách trên không diễn đạt tốt.

`macrodef` đặc biệt hữu ích khi mục tiêu chỉ là tái sử dụng một chuỗi thao tác XML. Nó giúp tránh phải duy trì mã Java và JAR riêng cho một quy trình vốn có thể ghép từ các task chuẩn.

Ví dụ:

```xml
<macrodef name="prepare-output">
    <attribute name="directory"/>
    <sequential>
        <mkdir dir="@{directory}"/>
        <echo message="Đã chuẩn bị @{directory}"/>
    </sequential>
</macrodef>

<target name="prepare">
    <prepare-output directory="build/generated"/>
</target>
```

Macro là định nghĩa build file, không phải thư viện task Java bên ngoài. Khi cần bảo trì một macro, hãy kiểm tra các thuộc tính và nested element mà macro công bố để người dùng không phải biết toàn bộ chi tiết triển khai bên trong.

## 6. Chọn nhóm task phù hợp

Khi cần thêm một khả năng vào build, có thể quyết định theo thứ tự sau:

1. **Tìm Core task trước.** Nếu task chuẩn đã đáp ứng, dùng nó để giảm số dependency và giúp build dễ chuyển môi trường.
2. **Kiểm tra optional task của Ant.** Đọc yêu cầu phiên bản, JAR và thư viện phụ. Dùng nhóm này khi chức năng phù hợp và dependency có thể được quản lý ổn định.
3. **Đánh giá thư viện bên ngoài.** Kiểm tra mức độ duy trì, giấy phép, khả năng tương thích với phiên bản Ant/JDK, cách phát hành và độ tin cậy của nguồn cung cấp.
4. **Tạo macro hoặc preset.** Nếu chỉ cần gom cấu hình hay chuỗi thao tác, định nghĩa ngay trong build file thường đơn giản hơn.
5. **Viết task riêng.** Chỉ nên làm khi logic đặc thù đủ rõ, có nhu cầu tái sử dụng và nhóm có khả năng kiểm thử, phát hành cũng như bảo trì JAR task.

| Tiêu chí | Core task | Optional task | Thư viện ngoài hoặc task tự viết |
|---|---|---|---|
| Nguồn cung cấp | Apache Ant Core | Hệ sinh thái phân phối Ant | Dự án hoặc nhà cung cấp khác |
| Khả năng có sẵn | Thường có trong bản Ant chuẩn | Tùy JAR và dependency được cài | Phải được dự án cung cấp và nạp |
| Chi phí cấu hình | Thấp | Trung bình, phụ thuộc thư viện | Tùy cách đóng gói và đăng ký |
| Rủi ro tương thích | Chủ yếu là phiên bản Ant/JDK | Ant, JDK và thư viện phụ | Ant, JDK, API và vòng đời thư viện |
| Khi nên dùng | Thao tác build phổ biến | Chức năng mở rộng đã được Ant hỗ trợ | Nhu cầu riêng hoặc tích hợp chuyên biệt |

Đừng chọn thư viện chỉ vì nó có một task tiện lợi. Hãy tính cả chi phí nâng cấp, xử lý lỗ hổng, hỗ trợ CI và khả năng một thành viên mới dựng lại môi trường.

## 7. Giữ build có thể tái lập trên các môi trường

Một build file có thể chạy tốt trên máy của tác giả nhưng thất bại trên máy khác nếu task mở rộng chỉ được cài thủ công. Để hạn chế tình trạng đó:

- Ghi rõ phiên bản Ant được dự án hỗ trợ và phiên bản JDK cần thiết.
- Liệt kê các JAR bổ sung cùng phiên bản và nguồn tải đáng tin cậy.
- Quản lý dependency của task theo một cách nhất quán, chẳng hạn thư mục công cụ có kiểm soát hoặc bước chuẩn bị môi trường của CI.
- Không giả định máy chạy build đã có sẵn một JAR trong `ANT_HOME/lib` nếu dự án chưa ghi rõ yêu cầu đó.
- Dùng đường dẫn tương đối từ thư mục dự án khi phù hợp, tránh hard-code đường dẫn cá nhân.
- Chạy cùng lệnh build trong CI để phát hiện dependency bị thiếu hoặc cấu hình chỉ tồn tại trên máy phát triển.
- Khi nâng Ant, JDK hoặc thư viện mở rộng, kiểm tra lại tài liệu tương thích và chạy các target có sử dụng task đó.

Ví dụ, nếu build dùng một task SSH, tài liệu dự án nên chỉ rõ JAR task SSH và thư viện SSH tương thích cần được cung cấp như thế nào. Chỉ ghi “cài Ant” là chưa đủ để một máy CI mới có thể tái tạo môi trường.

Các task như `exec`, task SSH hoặc task triển khai có thể chạy chương trình, truy cập mạng và sử dụng thông tin xác thực. Vì vậy, hãy xem JAR task bên ngoài như một dependency có khả năng thực thi mã: lấy từ nguồn đáng tin cậy, cố định phiên bản và chỉ cấp quyền cần thiết cho tiến trình build.

## 8. Chẩn đoán khi Ant không nhận ra task

Khi một task không chạy, hãy phân loại lỗi trước khi thay đổi build file.

| Biểu hiện | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `taskdef class ... cannot be found` | Thiếu JAR chứa lớp task hoặc khai báo sai tên lớp | Kiểm tra đường dẫn JAR, tên lớp và classpath của `taskdef` |
| `task ... not found` hoặc không nhận diện tên thẻ | Task chưa được đăng ký hoặc thư viện chưa được nạp | Kiểm tra `taskdef`, antlib, namespace và classpath của Ant |
| `NoClassDefFoundError` | Có lớp task nhưng thiếu một dependency lúc chạy | Đọc tên lớp bị thiếu và bổ sung đúng thư viện phụ |
| `NoSuchMethodError` hoặc lỗi liên kết tương tự | Các JAR không tương thích hoặc bị trùng phiên bản | Kiểm tra phiên bản Ant, task library và dependency |
| `doesn't support the nested ... element` | Task hoặc phiên bản đang dùng không hỗ trợ nested element đó | Đối chiếu cú pháp với tài liệu đúng phiên bản |
| Task chạy trên máy cá nhân nhưng lỗi trên CI | Máy cá nhân có JAR hoặc cấu hình toàn cục mà CI không có | So sánh phiên bản Ant/JDK và classpath ở hai môi trường |

Một số lệnh hữu ích:

```bash
ant -version
ant -diagnostics
ant -verbose target-name
```

- `ant -version` cho biết phiên bản Ant đang được gọi.
- `ant -diagnostics` in thông tin chẩn đoán về môi trường và các thành phần Ant nhận diện được.
- `ant -verbose target-name` cung cấp log chi tiết hơn khi chạy target, giúp xác định task hoặc bước nào gây lỗi.

Khi báo lỗi, hãy giữ lại tên lớp bị thiếu, phiên bản Ant, phiên bản JDK và lệnh chạy thực tế. Những dữ liệu này thường giúp phân biệt lỗi đăng ký task với lỗi thiếu dependency hoặc không tương thích phiên bản.

## 9. Ghi nhớ

- **Core task** là nền tảng của Ant, phục vụ các thao tác build phổ biến và thường dùng được ngay trong bản cài chuẩn.
- **Optional task** do hệ sinh thái Ant cung cấp nhưng có thể cần JAR riêng và thư viện bổ sung.
- **Task bên ngoài** đến từ thư viện của dự án hoặc nhà cung cấp khác; build phải nạp và đăng ký chúng.
- `taskdef` đăng ký task, `typedef` đăng ký data type và antlib đóng gói các định nghĩa theo namespace.
- `macrodef` và `presetdef` có thể giải quyết nhu cầu tái sử dụng cấu hình mà không cần viết task Java.
- Muốn build chạy ổn định trên máy khác, phải quản lý rõ phiên bản Ant, JDK và dependency của task mở rộng.

Khi đọc một build file, hãy xác định task đang dùng thuộc nhóm nào và thư viện triển khai nó đến từ đâu. Khi thêm task mới, hãy ghi nhận đầy đủ điều kiện chạy để người khác và CI có thể tái tạo cùng một môi trường build.
