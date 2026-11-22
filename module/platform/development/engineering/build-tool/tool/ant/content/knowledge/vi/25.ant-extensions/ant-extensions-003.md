# Tổ chức `antlib.xml` và sử dụng namespace cho thư viện task

Apache Ant cho phép mở rộng buildfile bằng task, datatype và macro do dự án hoặc thư viện bên ngoài cung cấp. Khi số lượng thành phần mở rộng tăng lên, việc đăng ký từng task bằng một lệnh `<taskdef>` riêng lẻ sẽ làm `build.xml` dài và khó bảo trì. Antlib giải quyết vấn đề này bằng cách gom các định nghĩa vào một tệp `antlib.xml`, đóng gói cùng các lớp Java và gọi chúng thông qua XML namespace.

Một antlib có thể chứa định nghĩa task Java, datatype, macro và các định nghĩa Ant khác được hỗ trợ. Buildfile chỉ cần nạp thư viện và khai báo namespace, sau đó gọi task bằng prefix như `<acme:hello/>`. Cách tổ chức này giúp phân biệt task của thư viện với task lõi của Ant, tránh trùng tên và tạo một giao diện XML rõ ràng cho thư viện mở rộng.

## 1. Antlib là gì?

Antlib là cơ chế tổ chức và phân phối các định nghĩa mở rộng của Ant. Một antlib thường gồm:

- Các lớp Java triển khai task hoặc datatype tùy chỉnh.
- Tệp descriptor có tên `antlib.xml`, mô tả tên task, datatype hoặc macro cần đăng ký.
- Các thư viện phụ thuộc mà lớp mở rộng cần để chạy.
- Một cấu trúc package/resource ổn định để Ant tìm descriptor.

Ví dụ, thư viện `acme-ant-tasks.jar` có thể chứa:

```text
acme-ant-tasks.jar
└── com/
    └── example/
        └── ant/
            ├── antlib.xml
            ├── HelloTask.class
            ├── GreetingType.class
            └── internal/
                └── MessageFormatter.class
```

Tệp `antlib.xml` nằm trong resource path `com/example/ant/antlib.xml`, tương ứng package `com.example.ant`. Buildfile có thể sử dụng namespace URI theo quy ước `antlib:com.example.ant` để tham chiếu tới các định nghĩa của thư viện.

Antlib không phải là một cơ chế build độc lập hay một định dạng thay thế `build.xml`. Nó là cách đóng gói các định nghĩa mở rộng để project có thể nạp và sử dụng chúng.

## 2. Cấu trúc của tệp `antlib.xml`

Tệp descriptor có phần tử gốc `<antlib>`. Bên trong có thể khai báo các task và datatype bằng `<taskdef>` và `<typedef>`; ngoài ra có thể đặt các định nghĩa macro hoặc preset task phù hợp.

Ví dụ tối thiểu:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<antlib>
    <taskdef name="hello"
             classname="com.example.ant.HelloTask"/>
</antlib>
```

Định nghĩa này đăng ký task có tên `hello`, ánh xạ tới lớp Java `com.example.ant.HelloTask`.

Một descriptor có thể chứa nhiều định nghĩa:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<antlib>
    <taskdef name="hello"
             classname="com.example.ant.HelloTask"/>

    <taskdef name="copy-report"
             classname="com.example.ant.CopyReportTask"/>

    <typedef name="greeting"
             classname="com.example.ant.GreetingType"/>

    <macrodef name="say-hello">
        <attribute name="who"/>
        <sequential>
            <echo message="Hello, @{who}!"/>
        </sequential>
    </macrodef>
</antlib>
```

Trong ví dụ:

- `taskdef` đăng ký một task được triển khai bằng lớp Java.
- `typedef` đăng ký một datatype để task khác hoặc cấu trúc Ant sử dụng.
- `macrodef` tạo một task macro bằng cách kết hợp các task Ant có sẵn.
- `name` là tên XML local name mà buildfile sẽ sử dụng sau prefix namespace.
- `classname` là tên đầy đủ của lớp Java triển khai task hoặc datatype.

Tên `hello`, `copy-report`, `greeting` và `say-hello` thuộc namespace của antlib khi descriptor được nạp qua URI tương ứng. Hai thư viện có thể cùng định nghĩa local name `hello` mà không xung đột nếu được sử dụng dưới namespace khác nhau.

## 3. Namespace XML và URI của antlib

XML namespace cho phép phân biệt các phần tử có cùng local name nhưng thuộc những thư viện khác nhau. Trong Ant, namespace được khai báo bằng thuộc tính `xmlns` trên phần tử `<project>` hoặc một phần tử XML phù hợp.

Ví dụ:

```xml
<project name="antlib-demo"
         default="run"
         xmlns:acme="antlib:com.example.ant">

    <target name="run">
        <acme:hello/>
    </target>

</project>
```

Ở đây:

- `acme` là prefix do người viết buildfile chọn.
- `antlib:com.example.ant` là namespace URI theo quy ước antlib.
- `hello` là local name đã được khai báo trong descriptor.
- `<acme:hello/>` gọi task `hello` thuộc thư viện `com.example.ant`.

Prefix không phải tên package Java và cũng không phải tên file JAR. Nó chỉ là bí danh XML trong phạm vi document. Có thể chọn prefix khác, ví dụ `custom`, miễn URI vẫn trỏ tới cùng antlib:

```xml
<project name="antlib-demo"
         xmlns:custom="antlib:com.example.ant">
    <target name="run">
        <custom:hello/>
    </target>
</project>
```

Namespace URI có ý nghĩa nhận diện thư viện, còn prefix chỉ giúp viết XML ngắn gọn. Vì vậy, không nên gắn logic của chương trình vào prefix `acme`; điều quan trọng là URI và local name.

## 4. Quy tắc ánh xạ `antlib:` tới `antlib.xml`

Theo quy ước thông dụng, URI:

```text
antlib:com.example.ant
```

được ánh xạ tới resource:

```text
com/example/ant/antlib.xml
```

Do đó, khi tạo JAR, descriptor cần nằm đúng vị trí trong archive. Nếu tệp được đặt nhầm thành `antlib.xml` ở thư mục gốc trong khi namespace đang dùng `antlib:com.example.ant`, Ant sẽ không tìm thấy descriptor theo resource path tương ứng.

Mối liên hệ có thể hình dung như sau:

```text
Namespace URI: antlib:com.example.ant
                     |
                     v
Resource path: com/example/ant/antlib.xml
                     |
                     v
             <antlib> descriptor
                     |
          +----------+----------+
          |                     |
          v                     v
      taskdef                 typedef
          |                     |
          v                     v
    HelloTask.class        GreetingType.class
```

Package path của descriptor phải khớp với phần package trong URI. Các lớp Java được khai báo trong descriptor phải có mặt trong classpath của Ant khi antlib được nạp.

## 5. Đăng ký antlib tường minh bằng `<taskdef>`

Trong nhiều dự án, cách rõ ràng nhất là khai báo task library JAR trong classpath và nạp descriptor bằng `<taskdef>`. Ví dụ:

```xml
<project name="antlib-demo"
         default="run"
         xmlns:acme="antlib:com.example.ant">

    <path id="acme.ant.classpath">
        <pathelement location="lib/acme-ant-tasks.jar"/>
        <pathelement location="lib/acme-ant-support.jar"/>
    </path>

    <taskdef uri="antlib:com.example.ant"
             resource="com/example/ant/antlib.xml"
             classpathref="acme.ant.classpath"/>

    <target name="run">
        <acme:hello message="Build started"/>
    </target>

</project>
```

Các thuộc tính quan trọng:

- `uri`: namespace mà các định nghĩa trong descriptor được đăng ký.
- `resource`: đường dẫn resource tới `antlib.xml` bên trong classpath.
- `classpathref`: Path chứa JAR có descriptor, lớp task và dependency cần thiết.

Khi `<taskdef>` nạp resource antlib với URI, Ant đọc descriptor và đăng ký những định nghĩa được khai báo bên trong namespace đó. Sau khi nạp, target có thể sử dụng các phần tử có prefix `acme`.

Nếu thư viện chỉ cung cấp datatype hoặc muốn đăng ký định nghĩa theo kiểu typedef, có thể dùng cơ chế `<typedef>` tương ứng. Với descriptor antlib có cả task và datatype, hãy dùng cách nạp descriptor được tài liệu Ant của phiên bản đang dùng hỗ trợ; tránh đăng ký lặp cùng một resource dưới nhiều URI nếu không có chủ đích.

## 6. Nạp antlib tự động qua classpath

Ant có thể tìm antlib descriptor theo namespace URI khi descriptor nằm trên classpath có thể truy cập bởi classloader dùng để nạp task. Điều này cho phép buildfile dùng namespace mà không cần viết riêng một lệnh đăng ký cho từng task.

Ví dụ namespace:

```xml
<project name="antlib-auto-demo"
         default="run"
         xmlns:acme="antlib:com.example.ant">

    <target name="run">
        <acme:hello message="Hello from antlib"/>
    </target>

</project>
```

Để cách nạp tự động hoạt động, JAR chứa descriptor và các lớp mở rộng phải nằm trong classpath mà Ant sử dụng để tìm antlib. Có thể cung cấp thư viện khi khởi chạy Ant bằng tùy chọn `-lib`, hoặc cấu hình classloader của Ant theo môi trường build.

Ví dụ:

```sh
ant -lib lib/acme-ant-tasks.jar run
```

Nếu antlib cần thư viện hỗ trợ khác, thêm chúng vào vị trí classpath phù hợp hoặc dùng một thư mục chứa các JAR cần thiết theo quy tắc của Ant. Không giả định rằng chỉ vì JAR được đặt trong thư mục `lib` của project thì Ant tự động tải nó như dependency của buildfile; classpath của ứng dụng Java và classpath dùng để nạp task của Ant là hai phạm vi khác nhau.

Với build cần rõ ràng và dễ đọc trong repository, đăng ký tường minh bằng `<taskdef uri="..." resource="..." classpathref="..."/>` thường giúp thấy trực tiếp thư viện được sử dụng và vị trí của nó.

## 7. Triển khai một custom task Java

Task Java thường kế thừa `org.apache.tools.ant.Task`. Các thuộc tính XML được Ant ánh xạ tới các setter Java theo quy tắc JavaBean. Ví dụ, thuộc tính `message` được ánh xạ tới phương thức `setMessage(String)`.

```java
package com.example.ant;

import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Task;

public class HelloTask extends Task {

    private String message;

    public void setMessage(String message) {
        this.message = message;
    }

    @Override
    public void execute() throws BuildException {
        if (message == null || message.isEmpty()) {
            throw new BuildException("Attribute 'message' is required.");
        }

        log(message);
    }
}
```

Descriptor `antlib.xml`:

```xml
<antlib>
    <taskdef name="hello"
             classname="com.example.ant.HelloTask"/>
</antlib>
```

Buildfile sử dụng task:

```xml
<project name="hello-antlib"
         default="run"
         xmlns:acme="antlib:com.example.ant">

    <path id="acme.ant.classpath">
        <pathelement location="lib/acme-ant-tasks.jar"/>
    </path>

    <taskdef uri="antlib:com.example.ant"
             resource="com/example/ant/antlib.xml"
             classpathref="acme.ant.classpath"/>

    <target name="run">
        <acme:hello message="Hello from a custom Ant task"/>
    </target>

</project>
```

Khi Ant thực thi `<acme:hello>`, nó tạo instance của `HelloTask`, gọi setter `setMessage` với giá trị thuộc tính `message`, sau đó gọi `execute()`. Task có thể dùng `log()` để ghi thông tin và ném `BuildException` khi điều kiện thực thi không hợp lệ.

Task tùy chỉnh nên giữ trách nhiệm hẹp, dùng exception của Ant để báo lỗi build và không tự gọi `System.exit()`. Việc gọi `System.exit()` có thể kết thúc toàn bộ tiến trình Ant, khiến các target khác và báo cáo cuối build không được thực hiện.

## 8. Đăng ký datatype bằng `<typedef>`

Datatype tùy chỉnh thường kế thừa `org.apache.tools.ant.types.DataType` hoặc một lớp datatype thích hợp. Nó biểu diễn cấu hình hoặc dữ liệu có thể được task khác sử dụng.

Ví dụ descriptor có cả task và datatype:

```xml
<antlib>
    <taskdef name="hello"
             classname="com.example.ant.HelloTask"/>

    <typedef name="greeting"
             classname="com.example.ant.GreetingType"/>
</antlib>
```

Một datatype đơn giản có thể chứa thuộc tính cấu hình:

```java
package com.example.ant;

import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.types.DataType;

public class GreetingType extends DataType {

    private String text;

    public void setText(String text) {
        this.text = text;
    }

    public String getText() {
        if (text == null) {
            throw new BuildException("Greeting text has not been configured.");
        }
        return text;
    }
}
```

Task khác có thể nhận datatype này qua nested element nếu triển khai phương thức `addConfiguredGreeting(GreetingType greeting)` hoặc cơ chế lồng tương ứng. Ant sẽ tạo datatype, cấu hình thuộc tính của nó, rồi chuyển đối tượng cho task chứa.

Ví dụ về cách sử dụng ở mức ý tưởng:

```xml
<acme:notify>
    <acme:greeting text="Build completed"/>
</acme:notify>
```

Để phần tử lồng này hoạt động, lớp task `NotifyTask` cần khai báo phương thức nhận đúng kiểu `GreetingType`. Nếu task không cung cấp setter hoặc phương thức `add...` tương ứng, Ant không biết cách đưa datatype vào task và sẽ báo lỗi cấu hình.

## 9. Đóng gói thư viện task thành JAR

Antlib descriptor phải được đóng gói như resource trong JAR, đúng resource path. Ví dụ cấu trúc dự án thư viện:

```text
acme-ant-tasks/
├── build.xml
├── src/main/java/
│   └── com/example/ant/
│       ├── HelloTask.java
│       └── GreetingType.java
└── src/main/resources/
    └── com/example/ant/
        └── antlib.xml
```

Sau khi biên dịch, task `<jar>` có thể đóng gói class và resource:

```xml
<project name="acme-ant-tasks" default="jar" basedir=".">

    <property name="classes.dir" location="build/classes"/>
    <property name="resources.dir" location="src/main/resources"/>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="src/main/java"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8"/>
    </target>

    <target name="jar" depends="compile">
        <mkdir dir="dist"/>
        <jar destfile="dist/acme-ant-tasks.jar" basedir="${classes.dir}">
            <fileset dir="${resources.dir}"/>
        </jar>
    </target>

</project>
```

Sau khi tạo JAR, cần xác nhận archive có:

```text
com/example/ant/antlib.xml
com/example/ant/HelloTask.class
com/example/ant/GreetingType.class
```

Có thể xem nội dung bằng:

```sh
jar tf dist/acme-ant-tasks.jar
```

Nếu descriptor không nằm đúng package path, namespace `antlib:com.example.ant` sẽ không tìm được resource tương ứng. Nếu class không có trong JAR hoặc dependency bị thiếu, descriptor có thể được đọc nhưng task vẫn không được khởi tạo thành công.

## 10. Quản lý dependency của thư viện task

Custom task có thể phụ thuộc vào các thư viện bên ngoài. Ví dụ task dùng thư viện JSON, HTTP hoặc parser riêng. Những dependency này phải có trong classloader dùng để nạp task.

Có thể khai báo một Path chứa toàn bộ thư viện:

```xml
<path id="acme.ant.classpath">
    <pathelement location="lib/acme-ant-tasks.jar"/>
    <fileset dir="lib/acme-ant-dependencies" includes="*.jar"/>
</path>

<taskdef uri="antlib:com.example.ant"
         resource="com/example/ant/antlib.xml"
         classpathref="acme.ant.classpath"/>
```

Không nên trộn dependency của task mở rộng với dependency runtime của ứng dụng nếu chúng có phiên bản hoặc phạm vi khác nhau. Task mở rộng chạy trong JVM Ant; dependency của ứng dụng được đưa vào classpath hoặc modulepath của ứng dụng khi compile/run. Hai classpath có thể chứa một số JAR giống nhau, nhưng mục đích của chúng khác nhau.

Nếu nhiều antlib dùng chung một dependency nhưng yêu cầu phiên bản không tương thích, có thể xảy ra xung đột classloader. Khi đó, hãy kiểm tra cách Ant tạo classloader cho taskdef và cân nhắc tách phiên bản thư viện, dùng `loaderref` phù hợp hoặc cô lập công cụ trong một tiến trình build riêng.

## 11. Dùng namespace để tránh xung đột tên task

Giả sử hai thư viện đều cung cấp task local name `validate`:

```xml
<project name="namespace-demo"
         xmlns:db="antlib:com.example.database"
         xmlns:security="antlib:com.example.security">

    <target name="verify">
        <db:validate connection="inventory"/>
        <security:validate policy="release"/>
    </target>

</project>
```

Hai phần tử có cùng local name nhưng thuộc hai namespace khác nhau. Ant biết phải sử dụng định nghĩa nào dựa trên URI được gắn với prefix.

Đây là lợi ích quan trọng của antlib: buildfile có thể sử dụng nhiều thư viện task mà không cần đặt tên toàn cục dài hoặc lo ngại trùng tên với task lõi của Ant. Prefix nên ngắn, dễ nhận diện và nhất quán trong toàn bộ buildfile.

Không nên dùng cùng một URI cho hai thư viện có descriptor khác nhau trừ khi chúng được thiết kế để cùng thuộc một antlib. Nếu URI trùng, Ant không thể phân biệt hai bộ định nghĩa theo ý định của người viết.

## 12. Namespace Antlib và namespace URI tùy chỉnh

Quy ước phổ biến là `antlib:<package>` vì Ant có thể ánh xạ package thành resource path của `antlib.xml`. Ví dụ:

```xml
xmlns:acme="antlib:com.example.ant"
```

được kết nối với resource `com/example/ant/antlib.xml`.

Ant cũng cho phép đăng ký định nghĩa với URI namespace cụ thể thông qua các task definition, tùy cách cấu hình. Khi dùng URI không theo quy ước `antlib:`, cần khai báo rõ cách ánh xạ URI tới resource descriptor hoặc định nghĩa task; không nên giả định Ant tự chuyển một URL tùy ý thành package path.

Đối với thư viện mới, dùng `antlib:<package>` thường đơn giản và dễ hiểu nhất. Chọn package name ổn định, tránh đổi namespace chỉ vì thay đổi prefix trong buildfile.

## 13. Tổ chức macro và preset task trong antlib

Antlib không chỉ dành cho Java task. Có thể đóng gói macro để tạo giao diện task dễ dùng hơn cho dự án.

Ví dụ descriptor:

```xml
<antlib>
    <macrodef name="create-report-dir">
        <attribute name="dir"/>
        <sequential>
            <mkdir dir="@{dir}"/>
            <echo message="Report directory ready: @{dir}"/>
        </sequential>
    </macrodef>

    <presetdef name="quiet-copy">
        <copy overwrite="true" verbose="false"/>
    </presetdef>
</antlib>
```

Buildfile:

```xml
<project name="macro-antlib-demo"
         default="prepare"
         xmlns:acme="antlib:com.example.ant">

    <target name="prepare">
        <acme:create-report-dir dir="build/reports"/>
        <acme:quiet-copy file="README.md" tofile="build/README.md"/>
    </target>

</project>
```

`macrodef` đóng gói một chuỗi task thành task mới có attribute riêng. `presetdef` tạo một phiên bản task đã được cấu hình trước. Đưa các định nghĩa này vào antlib giúp nhiều project dùng cùng quy ước mà không phải copy/paste các macro vào từng `build.xml`.

## 14. Thứ tự nạp và vị trí đăng ký

Task hoặc datatype phải được đăng ký trước khi Ant phân tích và thực thi phần tử tương ứng. Với cách đăng ký tường minh, đặt `<taskdef>` ở cấp project trước các target sử dụng namespace:

```xml
<project name="antlib-order-demo"
         xmlns:acme="antlib:com.example.ant">

    <path id="acme.classpath">
        <pathelement location="lib/acme-ant-tasks.jar"/>
    </path>

    <taskdef uri="antlib:com.example.ant"
             resource="com/example/ant/antlib.xml"
             classpathref="acme.classpath"/>

    <target name="run">
        <acme:hello message="Ready"/>
    </target>

</project>
```

Nếu đăng ký trong một target chạy sau target sử dụng task, Ant có thể không nhận diện phần tử ở thời điểm parse buildfile. Đối với taskdef/typedef dùng chung, khai báo ở cấp project giúp buildfile dễ đọc và bảo đảm thứ tự.

## 15. Kiểm tra antlib JAR và namespace

Khi Ant báo không nhận diện task, kiểm tra theo thứ tự:

1. Namespace prefix có được khai báo trên project hoặc phần tử cha không?
2. URI có đúng `antlib:<package>` và khớp với package path không?
3. Descriptor `antlib.xml` có nằm ở resource path dự kiến không?
4. Tên local task trong buildfile có khớp thuộc tính `name` của `taskdef` trong descriptor không?
5. JAR chứa descriptor và các class task đã nằm trong classpath của classloader chưa?
6. Các dependency mà custom task cần có mặt và tương thích không?
7. Lớp task có thể được khởi tạo và có constructor phù hợp không?

Có thể kiểm tra nội dung JAR bằng:

```sh
jar tf lib/acme-ant-tasks.jar
```

Để xác nhận descriptor:

```sh
jar xf lib/acme-ant-tasks.jar com/example/ant/antlib.xml
```

Lệnh thứ hai giải nén riêng descriptor vào thư mục hiện tại. Hãy kiểm tra resource path và nội dung XML. Có thể chạy Ant với log chi tiết để quan sát việc nạp task:

```sh
ant -verbose run
```

## 16. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ant báo unknown element hoặc không nhận diện task | Namespace chưa khai báo hoặc antlib chưa được nạp | Kiểm tra `xmlns`, URI và `<taskdef>`/classpath |
| Không tìm thấy `antlib.xml` | Descriptor đặt sai resource path so với URI | Với `antlib:com.example.ant`, đặt descriptor tại `com/example/ant/antlib.xml` |
| Descriptor được tìm thấy nhưng không tạo được task | Classname sai hoặc class task không có trong classpath | Kiểm tra `classname`, JAR và dependency |
| Task không nhận thuộc tính XML | Thiếu setter tương ứng hoặc tên thuộc tính không khớp JavaBean property | Bổ sung setter public đúng kiểu dữ liệu hoặc sửa attribute |
| Ant báo không thể tạo task instance | Lớp không có constructor phù hợp, lỗi khởi tạo hoặc thiếu dependency | Kiểm tra constructor, stack trace và classpath task library |
| Hai task cùng tên bị gọi nhầm | Dùng chung namespace URI hoặc gọi thiếu prefix | Đặt URI riêng cho mỗi thư viện và dùng prefix tường minh |
| `antlib.xml` không được đóng gói | Tệp nằm ngoài resource directory hoặc task jar chỉ chứa class | Thêm resource directory vào task `<jar>` và kiểm tra bằng `jar tf` |
| Task chạy được trên máy developer nhưng không chạy trong CI | JAR chỉ có trên classpath cục bộ của máy developer | Đưa thư viện vào vị trí build có thể tái tạo và cấu hình classpath rõ ràng |
| Task thiếu lớp phụ thuộc khi chạy | Classpath chỉ có task JAR, thiếu thư viện hỗ trợ | Thêm dependency vào path dùng để nạp antlib |
| Thay đổi descriptor nhưng Ant vẫn dùng định nghĩa cũ | Đang dùng JAR cũ, cache/build output cũ hoặc classloader đã được tạo trước đó | Rebuild JAR, xác nhận đường dẫn và khởi chạy lại Ant trong tiến trình mới |

## 17. Checklist đóng gói và sử dụng antlib

- [ ] Descriptor có tên `antlib.xml` và phần tử gốc `<antlib>` hợp lệ.
- [ ] Resource path của descriptor khớp package trong URI `antlib:<package>`.
- [ ] Các `taskdef` và `typedef` có local name duy nhất trong namespace.
- [ ] Lớp Java và dependency của thư viện có trong classpath của Ant.
- [ ] JAR chứa cả class và resource descriptor.
- [ ] Buildfile khai báo namespace prefix rõ ràng.
- [ ] `<taskdef uri="..." resource="..." classpathref="..."/>` được thực hiện trước khi dùng task nếu nạp tường minh.
- [ ] Prefix được dùng nhất quán và không bị nhầm với package name.
- [ ] Custom task có setter phù hợp với XML attribute và `execute()` xử lý lỗi bằng `BuildException`.
- [ ] Datatype được đăng ký bằng `typedef` và task chứa có phương thức nhận datatype tương ứng.
- [ ] Dependency của task library được phân biệt với dependency runtime của ứng dụng.
- [ ] Đã kiểm tra JAR bằng `jar tf` và chạy thử trong môi trường build sạch.

## 18. Kết luận

Antlib gom các định nghĩa task, datatype và macro vào một descriptor `antlib.xml`, sau đó cung cấp chúng qua XML namespace. URI theo dạng `antlib:<package>` liên kết tới resource `antlib.xml` trong package tương ứng; prefix như `acme` chỉ là bí danh để gọi phần tử. Đóng gói descriptor và các lớp vào JAR, nạp bằng `<taskdef>` với classpath rõ ràng, rồi sử dụng task dưới namespace riêng sẽ giúp thư viện mở rộng dễ phân phối, tránh xung đột tên và tái sử dụng được giữa nhiều buildfile.
