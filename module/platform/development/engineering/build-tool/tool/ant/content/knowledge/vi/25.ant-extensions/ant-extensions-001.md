# Đăng ký task và kiểu dữ liệu bằng taskdef và typedef

## 1. Mở rộng Ant bằng task và kiểu dữ liệu tùy chỉnh

Apache Ant cung cấp nhiều task và kiểu dữ liệu có sẵn, nhưng một dự án đôi khi cần thao tác build riêng: tạo metadata, kiểm tra một cấu trúc đặc thù, gọi công cụ nội bộ hoặc biểu diễn một nhóm cấu hình có thể tái sử dụng.

Ant cho phép đăng ký lớp Java thành tên XML trong build file:

- **taskdef** đăng ký một lớp Java như một task. Sau khi đăng ký, có thể gọi nó bằng một phần tử XML bên trong target, tương tự copy, javac hoặc jar.
- **typedef** đăng ký một lớp Java như một kiểu dữ liệu của Ant. Kiểu này có thể được dùng làm phần tử lồng nhau, cấu hình có cấu trúc hoặc đối tượng được tham chiếu.

Cả hai task đều ánh xạ một tên XML tới một lớp Java. Khác biệt chính nằm ở vai trò của lớp đó: task thực hiện hành động khi build chạy; kiểu dữ liệu biểu diễn và cung cấp dữ liệu cho task khác.

Ví dụ, một dự án có thể tạo task greet để in thông báo theo cấu hình, và kiểu dữ liệu greeting để đóng gói nội dung lời chào. Sau khi đăng ký, build file có thể dùng cú pháp XML dễ đọc thay vì gọi trực tiếp một chương trình Java bên ngoài.

## 2. Phân biệt taskdef và typedef

| Tiêu chí | taskdef | typedef |
|---|---|---|
| Mục đích | Đăng ký task có thể thực thi | Đăng ký kiểu dữ liệu của Ant |
| Lớp Java thường dùng | Kế thừa org.apache.tools.ant.Task | Kế thừa org.apache.tools.ant.types.DataType hoặc triển khai abstraction phù hợp |
| Vai trò | Thực hiện hành động trong build | Cung cấp cấu hình hoặc dữ liệu cho task |
| Vị trí sử dụng | Phần tử task trong một target | Phần tử lồng nhau, cấu hình hoặc tham chiếu |
| Ví dụ | greet với thuộc tính message | greeting với thuộc tính text |

Không nên đăng ký một lớp thực hiện hành động như một data type chỉ vì cả hai đều được biểu diễn bằng XML. Hãy chọn abstraction phù hợp với contract của lớp Java.

## 3. Viết một custom task đơn giản

Một custom task thường kế thừa org.apache.tools.ant.Task, khai báo thuộc tính qua setter và đặt logic thực thi trong execute().

Ví dụ lớp GreetingTask.java:

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
        if (message == null || message.trim().isEmpty()) {
            throw new BuildException(
                "The message attribute is required.",
                getLocation()
            );
        }

        log(message);
    }
}
```

Ant ánh xạ thuộc tính XML message tới phương thức setMessage(String). Khi task chạy, Ant gọi execute().

Một số quy tắc quan trọng:

- Lớp task cần có constructor công khai không tham số để Ant có thể tạo instance.
- Setter phải có tên theo quy tắc JavaBean, ví dụ setMessage tương ứng với thuộc tính message.
- Kiểu tham số setter phải là kiểu mà Ant có thể chuyển đổi từ giá trị XML, chẳng hạn String, File, boolean, int hoặc các kiểu được Ant hỗ trợ.
- Ném BuildException khi đầu vào không hợp lệ hoặc thao tác task thất bại.
- Dùng log() của Task để ghi thông tin theo hệ thống logging của Ant thay vì tự in mọi thứ bằng System.out.
- Không thực hiện công việc nặng trong constructor; constructor chỉ nên khởi tạo trạng thái mặc định.

getLocation() giúp lỗi có thể gắn với vị trí task trong build file, làm thông báo dễ truy tìm hơn.

## 4. Biên dịch và đăng ký task bằng taskdef

Lớp custom task phải được biên dịch thành .class và đặt trong JAR hoặc thư mục nằm trên classpath của Ant. Khi biên dịch lớp kế thừa Task, compiler cũng cần thấy ant.jar.

Giả sử mã nguồn nằm trong src/ant, có thể tạo JAR custom task bằng Ant:

```xml
<project name="custom-ant-task" default="run-custom-task" basedir=".">
    <property name="ant.task.src" value="src/ant"/>
    <property name="ant.task.classes" value="build/ant-task-classes"/>
    <property name="ant.task.jar" value="build/ant-tasks.jar"/>

    <path id="ant.api.classpath">
        <pathelement location="${ant.home}/lib/ant.jar"/>
    </path>

    <target name="compile-ant-task">
        <mkdir dir="${ant.task.classes}"/>

        <javac srcdir="${ant.task.src}"
               destdir="${ant.task.classes}"
               includeantruntime="false">
            <classpath refid="ant.api.classpath"/>
        </javac>

        <jar destfile="${ant.task.jar}"
             basedir="${ant.task.classes}"/>
    </target>

    <target name="run-custom-task" depends="compile-ant-task">
        <taskdef name="greet"
                 classname="com.example.ant.GreetingTask"
                 classpath="${ant.task.jar}"/>

        <greet message="Hello from a custom Ant task"/>
    </target>
</project>
```

Chạy:

```bash
ant run-custom-task
```

Trình tự thực hiện:

1. compile-ant-task tạo thư mục output và biên dịch lớp Java.
2. jar đóng gói các class thành build/ant-tasks.jar.
3. Target run-custom-task đăng ký tên greet bằng taskdef.
4. Ant tạo task GreetingTask, gán thuộc tính message rồi gọi execute() khi đến phần tử greet.

Trong ví dụ, taskdef được đặt bên trong target chạy sau bước biên dịch. Đây là điểm quan trọng: nếu đăng ký task ở cấp project trước khi JAR được tạo, Ant sẽ cố nạp lớp khi JAR chưa tồn tại.

Trong dự án thực tế, có thể build custom task trong một project riêng hoặc phân phối JAR task cùng build file. Khi đó, taskdef có thể đặt ở cấp project nếu JAR đã có sẵn trước khi Ant đọc build file.

## 5. Khai báo classpath cho lớp task

taskdef và typedef cần tìm thấy lớp được đăng ký cùng mọi dependency mà lớp đó sử dụng. Có thể truyền classpath bằng thuộc tính classpath, tham chiếu classpathref hoặc phần tử lồng nhau.

Dùng thuộc tính classpath:

```xml
<taskdef name="greet"
         classname="com.example.ant.GreetingTask"
         classpath="build/ant-tasks.jar"/>
```

Dùng Path đã khai báo:

```xml
<path id="custom.task.path">
    <pathelement location="build/ant-tasks.jar"/>
    <pathelement location="lib/custom-task-support.jar"/>
</path>

<taskdef name="greet"
         classname="com.example.ant.GreetingTask"
         classpathref="custom.task.path"/>
```

Hoặc khai báo classpath cho một kiểu dữ liệu:

```xml
<typedef name="greeting"
         classname="com.example.ant.Greeting"
         classpathref="custom.task.path"/>
```

Nếu custom task dùng thư viện ngoài, JAR của thư viện đó cũng phải có trong classpath của task. Classpath biên dịch và classpath lúc Ant nạp task có thể khác nhau; hãy bảo đảm cả hai chứa các dependency cần thiết ở đúng giai đoạn.

Ant dùng classloader để nạp định nghĩa. Nếu nhiều task cùng sử dụng một bộ thư viện, thuộc tính loaderRef của các định nghĩa có thể được dùng để chia sẻ classloader theo cấu hình phù hợp. Chỉ dùng khi cần kiểm soát việc nạp lớp; phần lớn custom task nhỏ chỉ cần classpath rõ ràng.

## 6. Đăng ký nhiều task từ file properties

Khi một thư viện cung cấp nhiều task, không cần viết một taskdef cho từng lớp. Có thể tạo file properties ánh xạ tên task với tên class đầy đủ.

Ví dụ file com/example/ant/tasks.properties:

```properties
greet=com.example.ant.GreetingTask
validateConfig=com.example.ant.ValidateConfigTask
generateVersion=com.example.ant.GenerateVersionTask
```

Đăng ký cả nhóm:

```xml
<taskdef resource="com/example/ant/tasks.properties"
         classpath="build/ant-tasks.jar"/>
```

Sau khi đăng ký, build có thể dùng các tên greet, validateConfig và generateVersion như các task thông thường.

Tệp properties phải nằm trong classpath để Ant đọc được resource. Khi JAR chứa file này, resource path là tên bên trong JAR, dùng dấu / và không bao gồm tiền tố filesystem của JAR.

Cách đăng ký theo resource hữu ích khi thư viện muốn công bố một nhóm task có phiên bản đồng bộ. Khi cần đăng ký các kiểu dữ liệu, có thể dùng typedef với resource properties có cùng dạng ánh xạ tên sang class.

## 7. Viết một kiểu dữ liệu tùy chỉnh

Kiểu dữ liệu tùy chỉnh thường kế thừa org.apache.tools.ant.types.DataType. Nó lưu các giá trị cấu hình và cung cấp API để task sử dụng.

Ví dụ lớp Greeting.java:

```java
package com.example.ant;

import org.apache.tools.ant.types.DataType;

public class Greeting extends DataType {
    private String text;
    private String language = "en";

    public void setText(String text) {
        checkAttributesAllowed();
        this.text = text;
    }

    public void setLanguage(String language) {
        checkAttributesAllowed();
        this.language = language;
    }

    public String getText() {
        return text;
    }

    public String getLanguage() {
        return language;
    }
}
```

checkAttributesAllowed() là cơ chế của DataType giúp ngăn việc trộn thuộc tính thông thường với một tham chiếu refid sau khi kiểu dữ liệu đã được cấu hình theo dạng reference.

Đăng ký kiểu bằng typedef:

```xml
<typedef name="greeting"
         classname="com.example.ant.Greeting"
         classpath="build/ant-tasks.jar"/>
```

Sau khi đăng ký, có thể khai báo đối tượng kiểu dữ liệu:

```xml
<greeting id="welcome.message"
          text="Welcome to the build"
          language="en"/>
```

Kiểu dữ liệu có thể được đặt tên bằng id để những thành phần khác tham chiếu khi class và task hỗ trợ cơ chế reference tương ứng. Đối với custom DataType, cần triển khai cách xử lý refid đúng contract của Ant nếu muốn hỗ trợ đầy đủ việc dereference; không nên giả định chỉ kế thừa DataType là mọi getter đã tự giải quyết mọi loại tham chiếu tùy chỉnh.

## 8. Dùng typedef làm phần tử lồng nhau của task

Một custom data type thường hữu ích nhất khi task nhận nó như một phần tử lồng nhau.

Có thể mở rộng GreetingTask để nhận Greeting:

```java
package com.example.ant;

import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Task;

public class GreetingTask extends Task {
    private Greeting greeting;

    public void addConfiguredGreeting(Greeting greeting) {
        if (this.greeting != null) {
            throw new BuildException(
                "Only one greeting element is allowed.",
                getLocation()
            );
        }
        this.greeting = greeting;
    }

    @Override
    public void execute() throws BuildException {
        if (greeting == null || greeting.getText() == null) {
            throw new BuildException(
                "A greeting element with text is required.",
                getLocation()
            );
        }

        log("[" + greeting.getLanguage() + "] " + greeting.getText());
    }
}
```

Đăng ký cả task và data type trước khi dùng:

```xml
<taskdef name="greet"
         classname="com.example.ant.GreetingTask"
         classpath="build/ant-tasks.jar"/>

<typedef name="greeting"
         classname="com.example.ant.Greeting"
         classpath="build/ant-tasks.jar"/>

<target name="say-hello">
    <greet>
        <greeting text="Xin chào" language="vi"/>
    </greet>
</target>
```

Ant nhận ra phần tử greeting tương ứng với kiểu đã đăng ký, tạo và cấu hình đối tượng, sau đó chuyển đối tượng đã cấu hình cho addConfiguredGreeting().

Một số phương thức phổ biến để nhận phần tử lồng nhau:

| Phương thức | Cách hoạt động |
|---|---|
| addConfiguredX(X value) | Ant cấu hình đối tượng con xong rồi mới truyền cho task |
| addX(X value) | Ant truyền đối tượng con theo cơ chế add trước khi cấu hình hoàn tất |
| createX() | Task tự tạo và trả về đối tượng con để Ant cấu hình |

Tên X trong phương thức tương ứng với tên phần tử XML theo quy tắc introspection của Ant. Với cấu hình lồng nhau cần kiểm tra sau khi mọi thuộc tính con đã được gán, addConfiguredX thường là lựa chọn dễ hiểu.

Nếu task chỉ cho phép một phần tử con, nên kiểm tra điều đó trong phương thức add hoặc trong execute() và đưa ra BuildException có thông báo rõ ràng.

## 9. Phân biệt thuộc tính task và phần tử lồng nhau

Ant dùng introspection để ánh xạ XML sang Java:

- Thuộc tính XML message="Hello" thường gọi setMessage("Hello").
- Phần tử lồng nhau greeting được xử lý qua phương thức addConfiguredGreeting, addGreeting hoặc createGreeting.
- Văn bản trực tiếp bên trong phần tử có thể được chuyển qua addText(String) nếu task hỗ trợ.

Ví dụ task nhận cả thuộc tính và phần tử lồng nhau:

```xml
<greet message="Build completed">
    <greeting text="Release package is ready"
              language="en"/>
</greet>
```

Trong thiết kế thực tế, tránh để cùng một thông tin có thể được truyền bằng nhiều cách mà không có quy tắc ưu tiên rõ ràng. Nếu task hỗ trợ cả message và greeting, hãy định nghĩa cách xử lý khi người dùng khai báo cả hai, hoặc từ chối cấu hình mâu thuẫn.

Kiểu dữ liệu cũng có thể được dùng trong những task Ant có sẵn nếu task đó hỗ trợ nested element tương ứng. Việc đăng ký một typedef không tự động làm mọi task có thể nhận kiểu mới; task tiêu thụ vẫn phải có API nested element tương thích.

## 10. Đăng ký task và kiểu dữ liệu bằng antlib

Khi phân phối một thư viện custom task, Ant hỗ trợ antlib để gom các định nghĩa vào một resource XML. File antlib thường được đặt trong JAR, ví dụ com/example/ant/antlib.xml:

```xml
<antlib>
    <taskdef name="greet"
             classname="com.example.ant.GreetingTask"/>

    <typedef name="greeting"
             classname="com.example.ant.Greeting"/>
</antlib>
```

Trong build file, nạp antlib và gắn nó với một namespace URI:

```xml
<project name="sample" xmlns:custom="antlib:com.example.ant">
    <typedef uri="antlib:com.example.ant"
             resource="com/example/ant/antlib.xml"
             classpath="build/ant-tasks.jar"/>

    <target name="run">
        <custom:greet>
            <custom:greeting text="Antlib is ready"
                             language="en"/>
        </custom:greet>
    </target>
</project>
```

Namespace giúp tránh xung đột tên với task hoặc kiểu dữ liệu khác. Ví dụ, hai thư viện có thể cùng định nghĩa một tên task validate, nhưng được gọi bằng hai namespace khác nhau.

Resource antlib phải có mặt trên classpath được cung cấp cho định nghĩa. Khi phân phối JAR, đặt antlib.xml đúng resource path và bảo đảm class cùng dependency của nó cũng nằm trong classpath.

Với một thư viện lớn, antlib thường dễ quản lý hơn nhiều lệnh taskdef và typedef rải rác trong build file. Với một task nhỏ chỉ dùng trong một dự án, đăng ký trực tiếp bằng classname thường đơn giản hơn.

## 11. Kiểm soát tên, namespace và phạm vi đăng ký

Tên task hoặc kiểu dữ liệu là tên phần tử mà người viết build sử dụng. Nên chọn tên ngắn, mô tả đúng hành động hoặc dữ liệu, và nhất quán giữa các phiên bản.

Một số nguyên tắc:

- Dùng namespace khi thư viện có khả năng trùng tên với task hoặc type của dự án khác.
- Giữ tên XML ổn định khi thay đổi implementation bên trong.
- Không đăng ký cùng một tên cho nhiều class khác nhau trong cùng namespace mà không có chủ ý.
- Đặt định nghĩa ở phạm vi project hoặc target phù hợp với thời điểm JAR đã sẵn sàng.
- Nếu task phụ thuộc một thư viện cụ thể, khai báo dependency trong classpath của định nghĩa thay vì dựa vào classpath ngẫu nhiên của máy chạy build.

Các định nghĩa được nạp trong project có thể được dùng ở những target chạy sau khi đăng ký. Nếu định nghĩa nằm bên trong một target, target đó phải chạy trước phần tử dùng tên task hoặc type.

## 12. Lỗi thường gặp khi đăng ký custom task và type

### Ant không tìm thấy class

Kiểm tra tên đầy đủ của class, cấu trúc package bên trong JAR và classpath hoặc classpathref. Tên com.example.ant.GreetingTask phải khớp chính xác với class đã biên dịch.

### NoClassDefFoundError khi task chạy

Lớp chính có thể đã được tìm thấy nhưng một dependency của nó bị thiếu. Đưa các JAR phụ thuộc cần thiết vào classpath của taskdef hoặc typedef.

### Could not create task hoặc class không phải task

Kiểm tra lớp task có constructor công khai không tham số và có kế thừa org.apache.tools.ant.Task hay không. Kiểm tra thêm phiên bản Ant API mà task được biên dịch cùng.

### Attribute ... was not found

Tên thuộc tính XML không ánh xạ tới setter phù hợp. Ví dụ message cần setMessage(...). Kiểm tra chính tả, kiểu tham số và khả năng chuyển đổi giá trị của Ant.

### Nested element không được nhận diện

Kiểm tra kiểu dữ liệu đã được đăng ký bằng typedef trước khi dùng và task có phương thức addConfiguredX, addX hoặc createX phù hợp. Tên phần tử XML phải khớp với tên mà API nested element của task mong đợi.

### Task được đăng ký trước khi JAR được tạo

Nếu taskdef ở cấp project nhưng JAR chỉ được tạo bởi một target, Ant sẽ không thể nạp class lúc đọc build file. Đặt taskdef trong target chạy sau bước build JAR, hoặc cung cấp JAR task có sẵn trước khi bắt đầu build.

### Hai thư viện xung đột dependency

Các custom task có thể yêu cầu phiên bản khác nhau của cùng thư viện. Xem xét classloader, dependency đóng gói và khả năng chia sẻ loaderRef. Tránh đưa nhiều phiên bản không tương thích vào cùng một classloader.

### Build chạy được trên máy này nhưng lỗi trên CI

Máy phát triển có thể vô tình cung cấp JAR qua thư mục Ant lib hoặc classpath toàn cục. Hãy đóng gói dependency cần thiết, khai báo classpath rõ ràng và kiểm thử trên môi trường CI sạch.

## 13. Nguyên tắc thiết kế và phân phối

- Dùng taskdef cho lớp thực hiện hành động trong build và typedef cho lớp biểu diễn dữ liệu.
- Viết custom task kế thừa Task, đặt logic trong execute() và ném BuildException khi không thể tiếp tục.
- Viết custom data type dựa trên DataType hoặc abstraction phù hợp với contract mà task tiêu thụ yêu cầu.
- Dùng setter JavaBean để ánh xạ thuộc tính XML và nested-element methods để nhận phần tử lồng nhau.
- Biên dịch custom task với Ant API và nạp nó bằng classpath có đầy đủ dependency.
- Đặt thời điểm đăng ký sau khi JAR đã sẵn sàng nếu JAR được tạo ngay trong cùng build.
- Dùng resource properties hoặc antlib khi cần công bố nhiều định nghĩa từ một thư viện.
- Dùng namespace để tránh trùng tên giữa các thư viện.
- Kiểm tra lỗi cấu hình sớm và cung cấp thông báo có vị trí build file.
- Phân phối custom task cùng dependency tương thích và kiểm thử bằng một Ant installation sạch.

taskdef và typedef là cầu nối giữa lớp Java và cú pháp XML của Ant. taskdef đưa hành động tùy chỉnh vào đồ thị build; typedef đưa kiểu dữ liệu tùy chỉnh vào cấu hình mà task có thể tiêu thụ. Khi classpath, thời điểm đăng ký và API nested element được thiết kế rõ ràng, custom task có thể được dùng lại trong nhiều project mà vẫn giữ build file dễ đọc.

