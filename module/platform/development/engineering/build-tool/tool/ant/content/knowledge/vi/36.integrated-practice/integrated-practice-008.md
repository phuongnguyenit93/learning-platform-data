# Viết và kiểm thử một custom task Java có đóng gói antlib

Apache Ant cung cấp nhiều task sẵn có như `<javac>`, `<copy>`, `<jar>`, `<exec>` và `<condition>`. Tuy nhiên, trong dự án thực tế có lúc bạn cần một thao tác riêng: kiểm tra quy ước đặt tên, tạo metadata, chuẩn hóa đầu vào hoặc kết nối với một công cụ nội bộ. Khi logic đủ phức tạp để khó diễn đạt bằng các task có sẵn, bạn có thể viết **custom task bằng Java** và dùng trong `build.xml` như một thẻ XML thông thường.

Bài thực hành này hướng dẫn tạo task `<demo:greet>` nhận tên người dùng, có tùy chọn chuyển tên thành chữ hoa, ghi thông báo vào hệ thống log của Ant và từ chối dữ liệu không hợp lệ. Sau đó, chúng ta **biên dịch, đóng gói task cùng `antlib.xml` trong một JAR, khai báo namespace, sử dụng từ project khác và kiểm thử cả logic Java lẫn việc nạp antlib thực tế**.

Chủ đề chính là *Build Tool Ant → Thực hành*. Mục đích cuối cùng là hiểu một quy trình có thể áp dụng cho các custom task có ích hơn, chẳng hạn task kiểm tra cấu hình hoặc sinh metadata trước khi phát hành.

## 1. Custom task và antlib là gì?

Một **custom task** là lớp Java được Ant biết cách khởi tạo và cấu hình từ thuộc tính XML. Cách phổ biến nhất là kế thừa `org.apache.tools.ant.Task`, cung cấp các setter cho thuộc tính và ghi đè phương thức `execute()`:

~~~java
public class ExampleTask extends Task {
    public void setValue(String value) {
        // Ant goi setter khi gap thuoc tinh value.
    }

    @Override
    public void execute() throws BuildException {
        // Logic cua task.
    }
}
~~~

Một **antlib** (*Ant Library*) là cách đóng gói và đăng ký các custom task/type dưới một namespace. File `antlib.xml` chứa các khai báo như `<taskdef>`, thường được đặt trong JAR tại đường dẫn gắn với package:

~~~text
com/example/ant/antlib.xml
~~~

Khi JAR có resource này trên classpath của khai báo antlib, project dùng task với tiền tố namespace, ví dụ `<demo:greet name="An"/>`.

Phân biệt các thành phần:

| Thành phần | Vai trò |
|---|---|
| Lớp `GreetTask extends Task` | Thực hiện hành vi Java, định nghĩa thuộc tính và kiểm tra đầu vào |
| `setName(String)`, `setUppercase(boolean)` | Chỗ Ant truyền thuộc tính trong XML vào object Java |
| `execute()` | Điểm thực thi chính khi Ant chạy task |
| `BuildException` | Báo lỗi phù hợp với cơ chế fail của Ant |
| `antlib.xml` | Ánh xạ tên tag trong antlib tới lớp Java |
| JAR antlib | Phân phối class và resource XML cho project khác |
| `<taskdef>` | Cho project biết nơi nạp antlib và các task của nó |
| `xmlns:demo="antlib:com.example.ant"` | Định danh namespace để dùng thẻ `<demo:greet>` |

Antlib là **cơ chế đăng ký task/type và namespace**, không phải một ứng dụng Java độc lập có hàm `main`. JAR antlib thường không cần `Main-Class` trong manifest.

### Khi nào nên viết custom task?

Custom task thích hợp khi công việc cần tích hợp chặt với Ant: đọc thuộc tính XML, sử dụng `Project` và `Location`, phát log theo mức của Ant, ném `BuildException`, thao tác file trong `basedir` hoặc cung cấp một API tái sử dụng giữa các build.

Nếu chỉ cần sao chép file hoặc thực thi một chương trình ngoài, ưu tiên các task sẵn có trước. Custom task mang thêm trách nhiệm biên dịch, test, tương thích API Ant, đóng gói và quản lý version.

## 2. Yêu cầu và cấu trúc project

Ví dụ dùng **JDK có hỗ trợ biên dịch với `--release 11`**, **Apache Ant 1.10.x** và các công cụ dòng lệnh `java`, `javac`, `ant`. Mã minh họa chọn Java release 11 để dùng được các API như `String.isBlank()` nếu cần; bản JDK thực tế chạy Ant có thể mới hơn, miễn compiler hỗ trợ release 11.

Ví dụ không phụ thuộc JUnit, Maven hay thư viện ngoài. Bài kiểm tra logic được viết dưới dạng một chương trình Java nhỏ để có thể chạy bằng Ant ngay cả trên môi trường đơn giản. Trong dự án có framework test, bạn có thể chuyển các assertion sang JUnit tương ứng.

Cấu trúc thư mục sẽ tạo:

~~~text
custom-antlib-demo/
├── build.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/ant/GreetTask.java
│   │   └── resources/
│   │       └── com/example/ant/antlib.xml
│   └── test/
│       └── java/
│           └── com/example/ant/GreetTaskSelfTest.java
├── consumer/
│   └── build.xml
└── build/                                # Ant tao, khong commit
    ├── classes/
    │   └── com/example/ant/
    │       ├── GreetTask.class
    │       └── antlib.xml
    ├── test-classes/
    ├── dist/
    │   └── greet-antlib.jar
    └── reports/
        └── integration.log
~~~

Thư mục `src/main/java` chứa class; `src/main/resources` chứa resource đóng gói vào JAR. Sau khi biên dịch, Ant copy `antlib.xml` vào cùng cây thư mục dưới `build/classes` và tạo JAR từ nội dung `build/classes`.

Nguyên tắc đóng gói quan trọng: **đường dẫn resource được khai báo trong `<taskdef resource="...">` phải khớp chính xác với đường dẫn của `antlib.xml` bên trong JAR**. Đặt file XML cạnh `build.xml` nhưng quên đưa vào JAR là lỗi rất thường gặp.

## 3. Viết lớp custom task Java

Tạo file `src/main/java/com/example/ant/GreetTask.java`:

~~~java
package com.example.ant;

import java.util.Locale;
import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Project;
import org.apache.tools.ant.Task;

/**
 * Ant task:
 *   <demo:greet name="An" uppercase="true"/>
 *
 * Ghi loi chao thong qua logger cua Ant.
 */
public final class GreetTask extends Task {

    private String name;
    private boolean uppercase;

    /**
     * Setter duoc Ant goi khi gap thuoc tinh name="...".
     */
    public void setName(String name) {
        this.name = name;
    }

    /**
     * Setter cho thuoc tinh uppercase="true|false".
     */
    public void setUppercase(boolean uppercase) {
        this.uppercase = uppercase;
    }

    @Override
    public void execute() throws BuildException {
        if (name == null || name.trim().isEmpty()) {
            throw new BuildException(
                    "Attribute 'name' must not be blank",
                    getLocation()
            );
        }

        String normalized = name.trim();
        String displayName = uppercase
                ? normalized.toUpperCase(Locale.ROOT)
                : normalized;

        log("Xin chào, " + displayName + "!", Project.MSG_INFO);
    }
}
~~~

### Ant biến thuộc tính XML thành giá trị Java như thế nào?

Khi Ant gặp:

~~~xml
<demo:greet name="  An  " uppercase="true"/>
~~~

Ant tìm task tương ứng với tag `greet` trong antlib, tạo object `GreetTask` rồi thiết lập thuộc tính:

~~~java
task.setName("  An  ");
task.setUppercase(true);
task.execute();
~~~

Đây là mô tả khái niệm; Ant thực tế dùng cơ chế cấu hình task và kiểm soát vòng đời riêng. Các setter phải có tên phù hợp và kiểu tham số mà Ant biết chuyển đổi. Với boolean, Ant chuyển giá trị thuộc tính XML sang kiểu `boolean` qua cơ chế introspection của Ant.

Trường `uppercase` mặc định là `false` vì kiểu primitive `boolean` có giá trị mặc định đó trong Java. Do vậy có thể viết:

~~~xml
<demo:greet name="Bình"/>
~~~

để giữ nguyên tên.

### Tại sao validate trong `execute()`?

Khi Ant nạp task, không có bảo đảm người dùng truyền đủ tất cả thuộc tính. Setter `setName` có thể không được gọi, để `name == null`. Thuộc tính cũng có thể là chuỗi trắng:

~~~xml
<demo:greet name="   "/>
~~~

Với cả hai trường hợp, task phải báo lỗi rõ ràng trước khi làm việc. Một `BuildException` sẽ làm build thất bại theo cơ chế lỗi của Ant, cho phép CI thấy task đã thất bại. Truyền `getLocation()` giúp Ant báo vị trí khai báo task trong XML khi có thể, thuận tiện để chẩn đoán.

Không nên âm thầm bỏ qua đầu vào sai hoặc chỉ gọi `System.out.println("error")` rồi trở về bình thường: pipeline có thể tiếp tục và báo thành công giả.

### Tại sao dùng `log(...)` thay cho `System.out.println(...)`?

`Task.log(message, Project.MSG_INFO)` đưa thông báo vào logging system của Ant. Nhờ đó:

- Output đi cùng cơ chế phân cấp mức log và định dạng của Ant.
- Build listener, logger hoặc CI có thể thu thập thông điệp.
- Test có thể lắng nghe `BuildEvent` thay vì phải thay thế `System.out`.
- Task có thể dùng mức `MSG_WARN`, `MSG_VERBOSE` hay `MSG_DEBUG` tùy ý nghĩa.

Ví dụ thông báo cần chẩn đoán sâu có thể dùng `log("...", Project.MSG_VERBOSE)` thay vì in quá nhiều ở chế độ mặc định.

### Những nguyên tắc thiết kế nên giữ

Task trong ví dụ cố tình nhỏ, nhưng các custom task thật cũng nên:

- Chỉ nhận những thuộc tính cần thiết, công khai rõ giá trị mặc định.
- Validate giá trị bắt buộc tại thời điểm chạy.
- Giữ trạng thái thuộc về **mỗi instance**, không dùng static mutable fields tùy tiện.
- Không gọi `System.exit(...)` để báo lỗi.
- Ném `BuildException` với thông điệp có hành động khắc phục.
- Đóng resource như stream hoặc file handle bằng `try-with-resources` nếu có.
- Hạn chế phụ thuộc vào `user.dir` của tiến trình; khi xử lý file, dùng `getProject().resolveFile(path)` để hiểu đường dẫn tương đối theo project.
- Tránh in secret, token hoặc dữ liệu nhạy cảm vào log.

## 4. Khai báo antlib.xml

Tạo `src/main/resources/com/example/ant/antlib.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<antlib>
    <taskdef name="greet"
             classname="com.example.ant.GreetTask"/>
</antlib>
~~~

Ý nghĩa:

- Thẻ `<antlib>` là gốc resource định nghĩa thư viện.
- `<taskdef name="greet">` công bố tên task sẽ dùng trong XML.
- `classname="com.example.ant.GreetTask"` phải trùng với package và tên class đã biên dịch.
- Nếu thư viện có nhiều task, có thể đăng ký thêm nhiều `<taskdef>` hoặc type bằng `<typedef>` trong cùng antlib.

Một JAR có thể chứa:

~~~text
greet-antlib.jar
└── com/
    └── example/
        └── ant/
            ├── GreetTask.class
            └── antlib.xml
~~~

Trong ví dụ này, tên namespace được chọn là `antlib:com.example.ant`, tương ứng với package chứa resource. Đây là quy ước dễ hiểu: người tiêu dùng nhìn namespace biết nhóm thư viện nào đang được dùng.

**Phân biệt:** tên URI `antlib:com.example.ant` là định danh namespace, không phải đường dẫn file trên đĩa. Resource path `com/example/ant/antlib.xml` mới là đường dẫn cần được classloader tìm thấy bên trong JAR.

## 5. Biên dịch Java và đóng gói antlib bằng Ant

Tạo `build.xml` tại project root với các target công khai để compile, đóng gói, test và dọn dẹp:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="custom-antlib-demo"
         default="verify"
         basedir="."
         xmlns:demo="antlib:com.example.ant">

    <description>
        Bien dich, dong goi va kiem thu custom Ant task GreetTask.
    </description>

    <property name="src.dir" location="src/main/java"/>
    <property name="resources.dir" location="src/main/resources"/>
    <property name="test.src.dir" location="src/test/java"/>

    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="test.classes.dir"
              location="${build.dir}/test-classes"/>
    <property name="dist.dir" location="${build.dir}/dist"/>
    <property name="reports.dir" location="${build.dir}/reports"/>
    <property name="antlib.jar"
              location="${dist.dir}/greet-antlib.jar"/>

    <!-- ant.core.lib la duong dan toi ant.jar cua Ant dang chay. -->
    <path id="ant.api.classpath">
        <pathelement location="${ant.core.lib}"/>
    </path>

    <target name="compile"
            description="Bien dich custom task va copy antlib.xml">
        <mkdir dir="${classes.dir}"/>

        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               release="11"
               encoding="UTF-8"
               includeantruntime="false">
            <classpath refid="ant.api.classpath"/>
        </javac>

        <copy todir="${classes.dir}">
            <fileset dir="${resources.dir}" includes="**/*"/>
        </copy>
    </target>

    <target name="jar"
            depends="compile"
            description="Dong goi greet-antlib.jar">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${antlib.jar}" basedir="${classes.dir}"/>
    </target>

    <!-- Cac target test se duoc bo sung o phan tiep theo. -->

    <target name="clean"
            description="Xoa output sinh ra trong build/">
        <delete dir="${build.dir}" quiet="true"/>
    </target>
</project>
~~~

Ở phần sau, chúng ta sẽ **bổ sung target kiểm thử vào cùng project này**, không tạo một `build.xml` thứ hai trùng target. Lúc này `default="verify"` sẽ hợp lệ khi target `verify` ở phần kiểm thử được thêm vào. Để thử riêng hai bước đầu trước khi viết test, có thể gọi trực tiếp:

~~~bash
ant compile
ant jar
~~~

Nếu đang dùng Ant trên Windows, các lệnh tương tự chạy trong terminal có Ant được cài và JDK đã cấu hình. Trong dự án CI nghiêm ngặt, nên dùng script wrapper chọn đúng phiên bản Ant và JDK.

### Vai trò của `ant.core.lib`

Lớp `Task`, `Project` và `BuildException` nằm trong Ant API. Task của chúng ta cần tham chiếu Ant API **khi biên dịch**, nhưng JAR antlib không nên đóng gói lại toàn bộ `ant.jar` bên trong. Ant đã cung cấp API này khi thực thi.

Thuộc tính được Ant thiết lập `ant.core.lib` trỏ tới JAR cốt lõi Ant của runtime hiện tại. Vì `<javac>` có `includeantruntime="false"`, classpath compile được khai báo tường minh bằng `<pathelement location="${ant.core.lib}"/>`; điều này tránh việc compiler vô tình phụ thuộc vào classpath bổ sung trên máy người viết.

Trong dự án thật, muốn khống chế tính tương thích cần xác định **phiên bản Ant API tối thiểu được hỗ trợ** và kiểm thử với bản đó. Không nên biên dịch dựa vào một Ant rất mới rồi giả định task sẽ chạy trên mọi bản Ant cũ.

### Vì sao phải copy resource trước khi tạo JAR?

Đường dẫn `src/main/resources/com/example/ant/antlib.xml` là input source, còn `<jar basedir="build/classes">` chỉ đóng gói nội dung bên trong `build/classes`. Nếu thiếu bước `<copy>`, JAR có class nhưng **không có antlib.xml**, khiến `<taskdef resource="com/example/ant/antlib.xml">` không tìm được resource.

Sau khi tạo JAR, có thể xem nội dung bằng:

~~~bash
jar tf build/dist/greet-antlib.jar
~~~

Bạn cần thấy ít nhất:

~~~text
com/example/ant/GreetTask.class
com/example/ant/antlib.xml
~~~

Tệp `META-INF/MANIFEST.MF` thường cũng tồn tại trong JAR được tạo bởi Ant. Task trong ví dụ không cần đăng ký class trong manifest vì `antlib.xml` đã thực hiện việc ánh xạ.

## 6. Nạp antlib và sử dụng task từ project khác

Tạo `consumer/build.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="greet-consumer"
         default="demo"
         basedir="."
         xmlns:demo="antlib:com.example.ant">

    <property name="task.jar"
              location="../build/dist/greet-antlib.jar"/>

    <target name="load-antlib">
        <available file="${task.jar}" property="task.jar.exists"/>
        <fail unless="task.jar.exists"
              message="Chua co JAR; chay ant jar tu project root."/>

        <taskdef uri="antlib:com.example.ant"
                 resource="com/example/ant/antlib.xml"
                 classpath="${task.jar}"/>
    </target>

    <target name="demo"
            depends="load-antlib"
            description="Goi GreetTask qua antlib namespace">
        <demo:greet name="An" uppercase="true"/>
        <demo:greet name="Bình"/>
    </target>

    <target name="invalid"
            depends="load-antlib"
            description="Thu dau vao rong de kiem tra BuildException">
        <demo:greet name="   "/>
    </target>
</project>
~~~

Chạy theo thứ tự:

~~~bash
# Trong thu muc custom-antlib-demo/
ant jar

# Consumer doc JAR da dong goi
ant -f consumer/build.xml demo
~~~

Thông điệp ý nghĩa mong đợi:

~~~text
[greet] Xin chào, AN!
[greet] Xin chào, Bình!
BUILD SUCCESSFUL
~~~

Tiền tố log thực tế tùy phiên bản Ant và cấu hình logger. Phần quan trọng là task có thể được đăng ký bằng resource bên trong **JAR đã build**, sau đó chạy qua namespace `demo`. Project consumer không tham chiếu trực tiếp source Java của task.

### Nạp bằng `taskdef` khác gì với namespace?

Khai báo:

~~~xml
<taskdef uri="antlib:com.example.ant"
         resource="com/example/ant/antlib.xml"
         classpath="${task.jar}"/>
~~~

nói cho Ant resource nào chứa các định nghĩa và classpath nào để tìm lớp. Còn `xmlns:demo="antlib:com.example.ant"` khai báo tiền tố để bạn viết `<demo:greet>` trong XML. **Hai URI phải khớp**.

Có thể dùng tiền tố khác `demo`, ví dụ `xmlns:custom="antlib:com.example.ant"` và `<custom:greet>`; identity nằm ở URI, không nằm ở tên tiền tố.

Khi phát hành JAR vào kho artifact, người sử dụng có thể lấy nó qua pipeline phụ thuộc hoặc lưu trong thư mục `tools/antlib/` và cập nhật đường dẫn `classpath`. Không nên yêu cầu người dùng copy JAR vào `ANT_HOME/lib` toàn hệ thống, vì điều đó làm cấu hình build phụ thuộc vào máy cá nhân.

## 7. Kiểm thử hành vi Java của custom task

Cần test các trường hợp:

| Ca | Input | Kết quả |
|---|---|---|
| Tên hợp lệ | `name="An"` | Ghi `Xin chào, An!` |
| Chuyển chữ hoa | `name="  An  " uppercase="true"` | Ghi `Xin chào, AN!` |
| Không có `name` | Không gọi setter | Ném `BuildException` |
| Tên toàn khoảng trắng | `name="   "` | Ném `BuildException` |
| Tên có Unicode | `name="Bình"` | Hiển thị Unicode, không lỗi encoding |
| Antlib packaging | Nạp bằng resource trong JAR | Tag `<demo:greet>` được nhận diện |

Hai phần kiểm thử phục vụ mục tiêu khác nhau: **unit test Java** tập trung vào logic setter/`execute()`; **integration test Ant** xác minh việc đóng gói, đăng ký task qua antlib, ánh xạ thuộc tính và log thực tế.

Để giữ ví dụ chạy được với JDK + Ant mà không cần tải thêm framework, ta dùng class Java self-test nhỏ có `main` và ném `AssertionError` khi sai. Đây là giải pháp minh họa; dự án có hệ thống test hiện hữu nên dùng JUnit hoặc framework phù hợp.
## 8. Viết self-test Java không cần thư viện test bên ngoài

Tạo `src/test/java/com/example/ant/GreetTaskSelfTest.java`:

~~~java
package com.example.ant;

import org.apache.tools.ant.BuildEvent;
import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.BuildListener;
import org.apache.tools.ant.Project;

/**
 * Self-test nho cho GreetTask.
 * Chay bang Java main; loi assertion tao exit code khac 0.
 */
public final class GreetTaskSelfTest {

    private GreetTaskSelfTest() {
    }

    public static void main(String[] args) {
        Project project = new Project();
        project.init();

        RecordingListener listener = new RecordingListener();
        project.addBuildListener(listener);

        // Case 1: trim ten va chuyen thanh chu hoa.
        GreetTask uppercaseTask = createTask(project, "  An  ", true);
        uppercaseTask.execute();
        assertContains(listener.messages(), "Xin chào, AN!");

        // Case 2: mac dinh khong chuyen thanh chu hoa.
        listener.clear();
        GreetTask normalTask = createTask(project, "Bình", false);
        normalTask.execute();
        assertContains(listener.messages(), "Xin chào, Bình!");

        // Case 3: thieu thuoc tinh bat buoc.
        expectInvalidName(project, null);

        // Case 4: chuoi chi co khoang trang.
        expectInvalidName(project, "   ");

        System.out.println("GreetTaskSelfTest PASSED");
    }

    private static GreetTask createTask(
            Project project, String name, boolean uppercase) {

        GreetTask task = new GreetTask();
        task.setProject(project);
        task.setName(name);
        task.setUppercase(uppercase);
        return task;
    }

    private static void assertContains(String actual, String expected) {
        if (!actual.contains(expected)) {
            throw new AssertionError(
                    "Expected log '" + expected + "' but got: " + actual
            );
        }
    }

    private static void expectInvalidName(Project project, String name) {
        GreetTask task = createTask(project, name, false);

        try {
            task.execute();
        } catch (BuildException expected) {
            if (!expected.getMessage().contains("Attribute 'name'")) {
                throw new AssertionError(
                        "Wrong error message: " + expected.getMessage()
                );
            }
            return;
        }

        throw new AssertionError(
                "Expected BuildException for invalid name: " + name
        );
    }

    private static final class RecordingListener implements BuildListener {
        private final StringBuilder messages = new StringBuilder();

        String messages() {
            return messages.toString();
        }

        void clear() {
            messages.setLength(0);
        }

        @Override
        public void messageLogged(BuildEvent event) {
            if (event.getPriority() <= Project.MSG_INFO
                    && event.getMessage() != null) {
                messages.append(event.getMessage()).append('\n');
            }
        }

        @Override
        public void buildStarted(BuildEvent event) {
        }

        @Override
        public void buildFinished(BuildEvent event) {
        }

        @Override
        public void targetStarted(BuildEvent event) {
        }

        @Override
        public void targetFinished(BuildEvent event) {
        }

        @Override
        public void taskStarted(BuildEvent event) {
        }

        @Override
        public void taskFinished(BuildEvent event) {
        }
    }
}
~~~

### Self-test kiểm tra điều gì?

- `createTask(...)` gán `Project` để `Task.log(...)` có môi trường phát sinh `BuildEvent`.
- `RecordingListener` ghi lại thông báo của Ant ở mức thông tin để so sánh kết quả mà không phải thay `System.out`.
- Hai ca hợp lệ kiểm tra trimming, chuyển chữ hoa và giữ Unicode.
- Hai ca không hợp lệ xác nhận `BuildException`, bao gồm nội dung thông báo lỗi dự kiến.
- Mọi assertion thất bại sẽ ném `AssertionError`. Khi chạy trong JVM con với `failonerror="true"`, Ant nhận mã lỗi và làm target test thất bại.

Đây là **self-test của logic Java**, vì mã test tạo task bằng `new GreetTask()` chứ không đăng ký qua antlib resource. Do đó nó chưa thể phát hiện trường hợp JAR thiếu `antlib.xml`, tên task khai báo sai hoặc classpath của consumer lỗi. Ta cần thêm kiểm thử tích hợp ở phần sau.

Nếu dùng JUnit thay vì chương trình `main`, có thể tách thành nhiều `@Test`, dùng cơ chế assert/exception của framework và tạo báo cáo XML. Tài liệu này chọn self-test để bài thực hành không cần tải thêm JUnit hoặc AntUnit.

## 9. Bổ sung target compile và chạy self-test vào build.xml

Đặt các target sau **bên trong `<project>` của `build.xml` ở phần 5**, trước thẻ đóng `</project>`. Không viết thêm một khối `<project>` thứ hai:

~~~xml
<target name="compile-tests"
        depends="compile"
        description="Bien dich chuong trinh tu kiem thu GreetTask">
    <mkdir dir="${test.classes.dir}"/>

    <javac srcdir="${test.src.dir}"
           destdir="${test.classes.dir}"
           release="11"
           encoding="UTF-8"
           includeantruntime="false">
        <classpath>
            <pathelement location="${classes.dir}"/>
            <path refid="ant.api.classpath"/>
        </classpath>
    </javac>
</target>

<target name="unit-test"
        depends="compile-tests"
        description="Chay self-test logic GreetTask">
    <java classname="com.example.ant.GreetTaskSelfTest"
          fork="true"
          failonerror="true">
        <classpath>
            <pathelement location="${test.classes.dir}"/>
            <pathelement location="${classes.dir}"/>
            <path refid="ant.api.classpath"/>
        </classpath>
    </java>
</target>
~~~

Ở đây:

- `compile-tests` cần class của task đã biên dịch và Ant API để biên dịch lớp self-test.
- `unit-test` dùng `<java fork="true">` chạy một chương trình `main` trong JVM con.
- `failonerror="true"` làm build dừng khi self-test kết thúc mã lỗi khác 0.
- Classpath runtime gồm test classes, task classes và `ant.jar`. Không phải thêm `greet-antlib.jar` riêng vào classpath của self-test vì nó kiểm thử trực tiếp class dưới `build/classes`.

Có thể gọi:

~~~bash
ant unit-test
~~~

Nếu đúng, thông báo cuối từ chương trình test sẽ có dạng:

~~~text
GreetTaskSelfTest PASSED
BUILD SUCCESSFUL
~~~

Nếu một assertion thất bại, Ant sẽ báo lỗi thay vì đánh dấu test thành công. Không cần xử lý riêng chuỗi stdout để xác định trạng thái: **exit code** của tiến trình Java là tín hiệu chính.

### Vì sao tự kiểm thử trong JVM con?

Bài test tạo một `Project` và đăng ký `BuildListener`; việc chạy trong JVM con giúp tách trạng thái kiểm thử khỏi JVM điều phối Ant. Chi phí khởi động JVM con là hợp lý trong một bộ self-test nhỏ. Với hàng nghìn test, có thể lựa chọn framework và chiến lược fork phù hợp để không tạo một JVM riêng cho mỗi assertion.

## 10. Kiểm thử tích hợp: Ant có nạp và chạy đúng antlib trong JAR không?

Self-test Java không chứng minh antlib đã được đóng gói. Ta bổ sung target `integration-test` thực thi **chính task được đăng ký qua JAR**, sau đó đối chiếu log đã ghi.

Thêm vào `build.xml`:

~~~xml
<target name="integration-test"
        depends="jar"
        description="Nap antlib JAR, chay greet va kiem tra log">
    <mkdir dir="${reports.dir}"/>

    <taskdef uri="antlib:com.example.ant"
             resource="com/example/ant/antlib.xml"
             classpath="${antlib.jar}"/>

    <record name="${reports.dir}/integration.log"
            action="start"
            append="false"
            loglevel="info"/>

    <demo:greet name="  An  " uppercase="true"/>

    <record name="${reports.dir}/integration.log"
            action="stop"/>

    <loadfile property="integration.log.text"
              srcFile="${reports.dir}/integration.log"/>

    <condition property="integration.log.ok">
        <contains string="${integration.log.text}"
                  substring="Xin chào, AN!"/>
    </condition>

    <fail unless="integration.log.ok"
          message="GreetTask khong ghi thong diep du kien."/>
</target>

<target name="verify"
        depends="unit-test,integration-test"
        description="Chay self-test va integration-test antlib"/>
~~~

**Lưu ý:** Target này dùng tiền tố `demo:`, nên thẻ gốc `<project>` đã khai báo `xmlns:demo="antlib:com.example.ant"` như ở phần 5. Với `<taskdef>`, phải dùng đúng resource path và URI trong project.

Ý nghĩa thứ tự:

1. Dependency `jar` bảo đảm class và `antlib.xml` được copy vào JAR.
2. `<taskdef>` nạp resource `com/example/ant/antlib.xml` từ classpath JAR.
3. `<record>` bắt thông báo được gửi tới logging system của Ant vào file.
4. `<demo:greet>` chạy task như người dùng thật sẽ gọi.
5. Sau khi dừng ghi log, `<loadfile>` đọc file và `<contains>` kiểm tra thông điệp.
6. `<fail>` làm target lỗi nếu nội dung đầu ra không đúng.

Cách này kiểm chứng cả **resource packaging, registration, class loading, XML attribute mapping và hành vi task**. Chạy:

~~~bash
ant clean verify
~~~

Cấu trúc phụ thuộc sau khi bổ sung:

~~~mermaid
flowchart TD
    V["verify"] --> U["unit-test"]
    V --> I["integration-test"]
    U --> TC["compile-tests"]
    TC --> C["compile"]
    I --> J["jar"]
    J --> C
    C --> SRC["GreetTask.class + antlib.xml"]
    U --> UT["Self-test: log và BuildException"]
    I --> SM["Smoke test: nạp JAR, gọi demo:greet"]
~~~

Trong cùng invocation `ant clean verify`, Ant giải quyết các dependency và không cần thực thi `compile` lại mỗi lần một nhánh nhắc đến target đó. Nếu chỉ muốn thử antlib, chạy `ant integration-test`; nếu chỉ muốn thử logic Java, chạy `ant unit-test`.

### Kiểm tra đầu ra của JAR riêng

Có thể mở JAR bằng lệnh của JDK:

~~~bash
jar tf build/dist/greet-antlib.jar
~~~

Nếu thấy `GreetTask.class` nhưng không thấy `antlib.xml`, kiểm tra đường dẫn `src/main/resources`, thao tác `<copy>` và `<jar basedir>`. Nếu resource có nhưng tag không được nhận diện, kiểm tra `uri`, `xmlns:demo`, `resource`, `classname` và classpath.

## 11. Kiểm thử trường hợp sai bằng một tiến trình Ant thực

Một custom task dùng trong CI không chỉ cần chạy đúng khi input hợp lệ. Nó còn phải **làm Ant thất bại** khi người dùng quên hoặc nhập sai thuộc tính bắt buộc.

Project consumer ở phần 6 có target:

~~~xml
<target name="invalid" depends="load-antlib">
    <demo:greet name="   "/>
</target>
~~~

Chạy:

~~~bash
ant jar
ant -f consumer/build.xml invalid
~~~

Kỳ vọng: lệnh thứ hai **không** trả về exit code 0. Trong log phải có thông báo tương tự:

~~~text
Attribute 'name' must not be blank
BUILD FAILED
~~~

Thông báo vị trí XML có thể khác theo Ant/terminal. Điều quan trọng là build đã fail vì `BuildException`, chứ không phải do task bị thiếu hoặc file JAR không nạp được.

### Tự động hóa ca âm tính trên Linux/macOS

Có thể tạo script `ci/test-invalid-name.sh` nếu dự án cần tích hợp thêm ca này vào CI:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

# Chay script tu project root, sau khi ant jar da thanh cong.
mkdir -p build/reports

set +e
ant -f consumer/build.xml invalid \
    >build/reports/invalid-name.log 2>&1
actual_exit=$?
set -e

if [ "$actual_exit" -eq 0 ]; then
    echo "FAILED: invalid input unexpectedly succeeded" >&2
    exit 1
fi

if ! grep -Fq "Attribute 'name' must not be blank" \
      build/reports/invalid-name.log; then
    echo "FAILED: wrong error reason" >&2
    exit 1
fi

echo "Negative integration test PASSED"
~~~

Script sử dụng `set +e` tạm thời vì **thất bại của Ant là kết quả được mong đợi ở ca âm tính**, sau đó kiểm tra cả exit code và thông báo. Nếu chỉ chấp nhận mã lỗi khác 0, bài test có thể báo pass vì lỗi “file JAR không tồn tại” hoặc “task không được định nghĩa”. Việc kiểm tra thông báo giúp tránh thành công giả.

Trong code trên `$actual_exit` là biến shell bình thường (sau khi thay ký hiệu hiển thị), và file log được đặt trong `build/reports` để kiểm tra sau khi chạy. Với CI thực tế, nên gọi đúng wrapper Ant của dự án để cố định toolchain thay vì phụ thuộc vào `ant` trên `PATH`.

Một đường kiểm thử đầy đủ có thể là:

~~~bash
ant clean verify
bash ci/test-invalid-name.sh
~~~

Vì target `verify` đã phụ thuộc `jar` qua `integration-test`, script âm tính có thể chạy sau `verify` mà không phải build JAR thêm lần nữa.

### Tại sao vẫn giữ cả unit và integration test?

Nếu sửa logic `setUppercase` làm tên không được chuyển sang chữ hoa, self-test và integration test đều có thể phát hiện. Nếu xóa `antlib.xml` khỏi JAR, self-test vẫn có thể pass vì class Java vẫn tồn tại, nhưng integration test sẽ fail khi `taskdef` cố nạp resource. Nếu đổi namespace sai, integration test sẽ fail dù logic Java đúng.

Hai tầng test này kiểm tra những rủi ro khác nhau và giúp xác định lỗi nằm ở **hành vi của class** hay **cơ chế phân phối/đăng ký antlib**.

## 12. Quy trình chạy từ đầu đến cuối

Sau khi tạo đầy đủ các file và bổ sung hai nhóm target test vào `build.xml`, thứ tự thao tác thông thường:

~~~bash
# 1. Kiem tra Ant va JDK dang su dung.
ant -version
java -version
javac -version

# 2. Xoa output cu, bien dich, dong goi va chay cac test.
ant clean verify

# 3. Kiem tra JAR.
jar tf build/dist/greet-antlib.jar

# 4. Dung antlib tu project consumer.
ant -f consumer/build.xml demo

# 5. Thu loi dau vao khong hop le (phai BUILD FAILED).
ant -f consumer/build.xml invalid
~~~

Các lệnh trên có thể dùng từ thư mục gốc `custom-antlib-demo/`. Lệnh cuối được thiết kế để fail; khi viết pipeline kiểm thử, phải bắt và kiểm tra expected failure như phần trước, tránh để một ca âm tính dự kiến làm đỏ toàn bộ CI một cách khó hiểu.

Kết quả mong đợi:

| Bước | Bằng chứng quan sát |
|---|---|
| `ant clean verify` | Biên dịch, self-test và integration-test thành công |
| `jar tf ...` | Có `GreetTask.class` và `antlib.xml` trong đúng path |
| `ant -f consumer/build.xml demo` | In lời chào từ JAR antlib |
| `ant -f consumer/build.xml invalid` | Trả exit code lỗi với thông báo thuộc tính `name` không hợp lệ |

## 13. Tích hợp vào CI/CD với version và classpath xác định

Ở môi trường CI, một antlib dùng lại giữa các project cũng cần hợp đồng phiên bản. Không nên chỉ lưu JAR trong thư mục tạm của máy lập trình viên hoặc dựa vào thư viện ngầm trong `ANT_HOME/lib`.

Một trình tự CI đơn giản:

~~~text
Checkout commit
     |
     v
Bootstrap Ant + JDK đúng version
     |
     v
ant clean verify
     |
     v
Đối chiếu file trong JAR / kiểm tra checksum
     |
     v
Lưu greet-antlib.jar + báo cáo test
     |
     v
Phát hành vào artifact repository (nếu được phép)
~~~

Với dự án dùng antlib ở nhiều nơi, nên:

- Chọn version rõ ràng cho JAR, ví dụ `greet-antlib-1.0.0.jar` khi phát hành.
- Lưu SHA-256 của artifact đã kiểm thử; consumer phải lấy đúng binary đã được duyệt.
- Ghi phiên bản Ant và JDK tương thích, Java bytecode target (ở ví dụ là release 11).
- Cung cấp hướng dẫn tải JAR và cách cấu hình `taskdef`/namespace.
- Không đóng gói `ant.jar` của Ant vào bên trong JAR antlib thông thường; đây là API do môi trường Ant cung cấp.
- Khóa version và checksum của mọi thư viện ngoài mà custom task cần, kể cả dependency không có trong Ant core.
- Xác nhận target unit và integration test chạy trên runner sạch, không phụ thuộc JAR từ thư mục người dùng.

Trong pipeline phát hành, bước **publish** phải dùng chính JAR vừa được build và kiểm thử. Nếu CI rebuild JAR trên một runner khác mà không kiểm soát toolchain, artifact đăng lên kho có thể khác binary đã kiểm chứng.

## 14. Những lỗi thường gặp khi viết antlib

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `taskdef class ... cannot be found` | Sai `classname`, thiếu class trong JAR hoặc thiếu dependency | Kiểm tra `jar tf`, package/classname và classpath |
| `Resource ... antlib.xml could not be found` | File XML chưa được copy vào JAR hoặc sai `resource` | Đối chiếu đường dẫn resource trong archive |
| `Problem: failed to create task or type demo:greet` | Antlib chưa được đăng ký, sai namespace hoặc URI | Kiểm tra `xmlns:demo`, `taskdef uri` và target load |
| `doesn't support the "name" attribute` | Setter thiếu, không public, tên setter sai hoặc task class không đúng | Kiểm tra `public void setName(String)` và class được nạp |
| `Attribute 'name' must not be blank` | Không truyền `name` hoặc toàn khoảng trắng | Sửa input tại lời gọi task |
| `NoClassDefFoundError` khi task chạy | Có class phụ thuộc lúc runtime nhưng JAR/classpath không có | Khóa và khai báo đầy đủ dependency runtime của task |
| `UnsupportedClassVersionError` | Class được biên dịch cho Java mới hơn JVM chạy Ant | Dùng `release` phù hợp và kiểm tra JDK thực tế |
| Unit test pass, consumer fail | Logic đúng nhưng antlib packaging, resource hoặc namespace sai | Chạy integration-test qua JAR và consumer smoke test |
| Log không xuất hiện | Dùng sai mức log hoặc task không chạy | Kiểm tra `log(..., Project.MSG_INFO)`, target dependency và logger |
| Hành vi khác trên máy khác | Khác phiên bản Ant/JDK, charset, locale, dependency | Pin toolchain và cấu hình encoding nhất quán |

### Một vài lỗi thiết kế cần tránh

**Sai 1 — Dùng console output làm giao diện lỗi.**

~~~java
System.out.println("error: missing name");
return;
~~~

Cách này có thể khiến Ant báo thành công. Thay bằng `throw new BuildException(...)` và dùng `log(...)` cho thông tin bình thường.

**Sai 2 — Nhúng lớp Ant cốt lõi vào JAR của thư viện custom task.** Điều đó dễ tạo classloading conflict hoặc phụ thuộc vào API khác với runtime. Ant API nên là compile dependency phù hợp; runtime do Ant host cung cấp.

**Sai 3 — Giữ trạng thái toàn cục trong static field.** Ant có thể tạo nhiều instance task trong cùng JVM. Static mutable state khiến một lần gọi ảnh hưởng lần khác và làm test khó cô lập.

**Sai 4 — Bỏ qua lỗi kiểm tra đầu vào.** Nếu một task sinh file quan trọng mà âm thầm bỏ qua property thiếu, target sau có thể sử dụng dữ liệu cũ và cho kết quả sai.

**Sai 5 — Chỉ kiểm tra class Java, không test JAR.** Một antlib hoạt động với source trực tiếp vẫn có thể bị đóng gói thiếu `antlib.xml`; cần một bước test nạp **artifact đã đóng gói**.

## 15. Mở rộng custom task sau bài thực hành

Khi đã hiểu mô hình setter + `execute()` + `antlib.xml`, bạn có thể triển khai task thực tế hơn, ví dụ:

- **Validate manifest:** nhận đường dẫn file và quy tắc, xác minh dữ liệu trước khi build.
- **Generate build metadata:** lấy version/commit đã được cung cấp, sinh một file metadata trong thư mục output.
- **Check artifact:** nhận file JAR, kiểm tra tên/size/checksum trước khi publish.
- **Verify structure:** kiểm tra những thư mục hoặc resource bắt buộc có tồn tại.

Với task có đường dẫn input/output, nên sử dụng `getProject().resolveFile(...)` để xử lý path tương đối theo `basedir` của project Ant, validate xem input có tồn tại và output được phép ghi hay không. Có thể thêm property hoặc setter kiểu `File` thay cho `String` khi API Ant hỗ trợ kiểu đó, nhưng phải cập nhật contract và test.

Nếu task cần nhận danh sách hoặc cấu trúc lồng nhau, Ant cũng hỗ trợ cơ chế nested elements thông qua phương thức `create...`, `add...` hoặc `addConfigured...`. Đây là bước mở rộng phù hợp khi cấu hình đã vượt khả năng của vài thuộc tính phẳng. Không nên thêm nested API chỉ để làm ví dụ đơn giản trở nên phức tạp.

Khi antlib được nhiều project sử dụng, xem các setter công khai, tên task và namespace là **API cần tương thích**. Thay đổi tên attribute, kiểu dữ liệu hoặc ngữ nghĩa lỗi có thể làm những build consumer đang chạy thành công bắt đầu thất bại; nên có versioning và test tương thích theo nhu cầu của nhóm.

## 16. Những gì bài thực hành đã xây dựng

Qua ví dụ `GreetTask`, quy trình hoàn chỉnh gồm:

1. **Viết custom task Java:** kế thừa `Task`, expose setter, implement `execute()`, log và ném `BuildException` khi dữ liệu không hợp lệ.
2. **Khai báo antlib:** ánh xạ tag `greet` với `com.example.ant.GreetTask` trong `antlib.xml`.
3. **Đóng gói:** compile class với Ant API, copy resource và tạo JAR chứa cả class lẫn `antlib.xml`.
4. **Tiêu thụ từ project khác:** dùng `<taskdef resource="..." uri="..." classpath="..."/>` và namespace `demo`.
5. **Kiểm thử hai tầng:** self-test Java cho hành vi/ngoại lệ và integration test cho resource, JAR, classloader, XML mapping, log.
6. **Kiểm thử lỗi:** xác nhận input sai khiến Ant trả exit code thất bại với thông báo phù hợp.
7. **Chuẩn bị phân phối:** lưu artifact đã kiểm thử cùng version, checksum, hướng dẫn classpath và phạm vi tương thích.

**Điều cần ghi nhớ:** một custom task chỉ thật sự sẵn sàng dùng lại khi **hành vi Java đúng, Ant đăng ký được task từ antlib resource trong JAR và consumer có thể chạy nó bằng classpath/namespace được tài liệu hóa**. Kiểm thử cả code lẫn artifact đóng gói giúp các dự án Ant có thể tái sử dụng công cụ build Java mà vẫn dễ bảo trì và phát hiện lỗi sớm.



