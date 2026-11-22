# Phân biệt classpath của Ant, trình biên dịch, ứng dụng và kiểm thử

Trong một dự án Java dùng Apache Ant, từ “classpath” xuất hiện ở nhiều nơi nhưng không phải lúc nào cũng chỉ cùng một danh sách thư viện. Ant có classpath để nạp chính Ant và các task mở rộng; trình biên dịch cần classpath để tìm các lớp mà mã nguồn tham chiếu; ứng dụng cần classpath khi chạy; còn mã kiểm thử cần thêm các lớp kiểm thử và thư viện test.

Nếu trộn các classpath này vào một danh sách duy nhất, build có thể vô tình dùng thư viện nội bộ của Ant để biên dịch ứng dụng, chạy được trên máy phát triển nhưng thiếu dependency khi triển khai, hoặc đưa JUnit vào artifact sản phẩm. Cách tổ chức tốt là xác định classpath theo đúng giai đoạn và mục đích sử dụng.

## 1. Bốn loại classpath cần phân biệt

| Loại classpath | Ai sử dụng? | Chứa những gì? | Mục đích |
|---|---|---|---|
| Ant runtime classpath | JVM đang chạy Ant và bộ nạp lớp của Ant | Ant core, task mở rộng, thư viện cần để nạp task/type | Giúp Ant khởi động và nhận biết các task, data type, listener |
| Compiler classpath | Trình biên dịch Java được task javac gọi | Lớp đã biên dịch và JAR mà mã nguồn cần tham chiếu | Giúp compiler tìm kiểu dữ liệu và API bên ngoài khi biên dịch |
| Application runtime classpath | JVM chạy ứng dụng | Thư mục class đã biên dịch và dependency cần khi ứng dụng thực thi | Giúp JVM nạp các lớp mà ứng dụng sử dụng lúc chạy |
| Test classpath | Compiler và test runner | Lớp ứng dụng, lớp test, dependency ứng dụng và thư viện kiểm thử | Giúp biên dịch và thực thi test trong đúng môi trường |

Các danh sách này có thể chứa một số JAR giống nhau, nhưng chúng không có cùng phạm vi. Ví dụ, một thư viện logging có thể cần ở cả compiler classpath và application runtime classpath; JUnit thường chỉ cần trong test classpath; thư viện Ant custom task cần trong Ant runtime classpath.

Sơ đồ khái quát:

```text
JVM khởi chạy Ant
    |
    +-- Ant runtime classpath
    |      +-- Ant core
    |      +-- ant-junit / custom task libraries
    |      +-- task definitions
    |
    +-- build.xml
           |
           +-- javac
           |      +-- Compiler classpath
           |      +-- src/main/java
           |      +-- build/classes
           |
           +-- java
           |      +-- Application runtime classpath
           |      +-- build/classes
           |      +-- application libraries
           |
           +-- test runner
                  +-- Test classpath
                  +-- build/classes
                  +-- build/test-classes
                  +-- application and test libraries
```

Điểm quan trọng là Ant điều phối các giai đoạn này, nhưng mỗi công cụ hoặc tiến trình có quy tắc nạp lớp riêng.

## 2. Ant runtime classpath

### 2.1. Dùng để nạp Ant và các thành phần mở rộng

Ant được chạy bên trong một JVM. JVM đó cần tìm được các lớp của Ant core và những thư viện cần thiết để khởi động Ant. Khi build sử dụng task mở rộng hoặc custom task, các lớp triển khai task đó cũng phải được bộ nạp lớp của Ant tìm thấy.

Ví dụ, một dự án sử dụng task tùy chọn JUnit của Ant. Thành phần triển khai task JUnit (thường là thư viện ant-junit phù hợp với bản Ant đang dùng) phải có mặt trong môi trường nạp task của Ant. JUnit framework mà test cần chạy lại là dependency của test runner. Hai thư viện có thể liên quan nhưng có vai trò khác nhau.

Một số cách bổ sung thư viện vào Ant runtime classpath:

- Đặt thư viện mở rộng vào thư mục lib của bản cài Ant, nếu đó là cách quản lý được dự án lựa chọn.
- Dùng tùy chọn dòng lệnh `-lib` để thêm thư mục hoặc JAR vào classpath của Ant trong lần chạy.
- Khai báo classpath riêng cho task/type bằng cấu hình của chính task, ví dụ thuộc tính classpath của taskdef khi nạp custom task.

Ví dụ chạy Ant với một thư viện custom task:

```text
ant -lib tools/ant-tasks/custom-task.jar build
```

Tùy chọn `-lib` tác động đến môi trường nạp lớp của Ant. Nó không tự động thêm JAR đó vào classpath mà task javac dùng để biên dịch ứng dụng, cũng không tự động đưa JAR đó vào classpath của JVM chạy ứng dụng.

### 2.2. Nạp custom task bằng taskdef

Một custom task có thể được khai báo trong build file bằng taskdef. Ví dụ minh họa:

```xml
<taskdef name="custom-check"
         classname="com.example.ant.CustomCheck"
         classpath="tools/ant-tasks/custom-task.jar" />

<target name="check">
    <custom-check />
</target>
```

Thuộc tính classpath ở đây giúp Ant tìm lớp triển khai task. Đây là classpath phục vụ việc nạp task, không phải classpath của mã nguồn ứng dụng.

Nếu custom task còn phụ thuộc vào các thư viện khác, những thư viện đó cũng phải có thể được nạp cùng task. Có thể dùng một path được định nghĩa trước và tham chiếu vào taskdef nếu cấu hình hỗ trợ:

```xml
<path id="custom.task.path">
    <pathelement location="tools/ant-tasks/custom-task.jar" />
    <pathelement location="tools/ant-tasks/helper.jar" />
</path>

<taskdef name="custom-check"
         classname="com.example.ant.CustomCheck"
         classpathref="custom.task.path" />
```

Cần kiểm tra cú pháp theo phiên bản Ant và taskdef đang dùng. Với taskdef, thuộc tính classpathref tham chiếu một path đã định nghĩa; nó có ý nghĩa trong việc nạp task.

### 2.3. Không đưa thư viện Ant vào ứng dụng chỉ vì Ant đã nạp được

Một lỗi thường gặp là cho rằng nếu Ant tìm thấy một JAR thì ứng dụng cũng sẽ tìm thấy JAR đó. Điều này không đúng. Ant runtime classpath chỉ phục vụ tiến trình Ant và các task chạy trong môi trường đó.

Task javac có thuộc tính includeantruntime để điều khiển việc đưa thư viện runtime của Ant vào classpath biên dịch. Thuộc tính này mặc định là true trong task javac; với ứng dụng thông thường, nên đặt:

```xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false" />
```

Việc tắt includeantruntime giúp tránh để mã ứng dụng vô tình phụ thuộc vào lớp của Ant. Nếu ứng dụng thực sự cần một thư viện nào đó, hãy khai báo thư viện đó trong compiler classpath và application runtime classpath tương ứng.

## 3. Compiler classpath

### 3.1. Compiler cần classpath để làm gì?

Khi biên dịch một lớp Java, javac phải phân giải các kiểu mà mã nguồn sử dụng. Ví dụ:

```java
import org.apache.commons.lang3.StringUtils;

public class GreetingService {
    public String normalize(String value) {
        return StringUtils.trimToEmpty(value);
    }
}
```

Nếu mã nguồn dùng thư viện Commons Lang, compiler phải tìm được lớp StringUtils trong classpath. Nếu JAR không có trong compiler classpath, quá trình biên dịch có thể báo lỗi package hoặc symbol không tồn tại.

Trong Ant, compiler classpath thường được khai báo bên trong task javac:

```xml
<path id="app.compile.classpath">
    <fileset dir="lib/compile" includes="*.jar" />
</path>

<target name="compile">
    <mkdir dir="build/classes" />

    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"
           encoding="UTF-8">
        <classpath refid="app.compile.classpath" />
    </javac>
</target>
```

Ở đây, path app.compile.classpath chứa các JAR cần khi biên dịch. Task javac sử dụng path đó để tìm các lớp được mã nguồn tham chiếu.

### 3.2. Compiler classpath không phải sourcepath

Classpath thường chứa các lớp đã biên dịch và thư viện JAR. Sourcepath chỉ các thư mục chứa mã nguồn mà compiler có thể tìm thêm khi cần phân giải kiểu.

Trong Ant, task javac có thể khai báo sourcepath riêng:

```xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false">
    <classpath refid="app.compile.classpath" />
    <sourcepath>
        <pathelement location="src/generated/java" />
    </sourcepath>
</javac>
```

Không nên dùng sourcepath để thay thế thư viện JAR trong classpath. Nếu một kiểu chỉ có trong thư viện đã biên dịch, cần đưa thư viện đó vào classpath. Nếu một kiểu được cung cấp dưới dạng mã nguồn bổ sung, sourcepath có thể giúp compiler tìm mã nguồn đó.

### 3.3. Kết quả biên dịch cũng có thể là đầu vào của lần biên dịch sau

Trong dự án nhiều module hoặc nhiều nhóm mã nguồn, output của module nền có thể là dependency của module khác. Ví dụ, khi biên dịch phần adapter cần dùng các lớp đã có trong build/classes:

```xml
<path id="adapter.compile.classpath">
    <pathelement location="build/classes" />
    <fileset dir="lib/compile" includes="*.jar" />
</path>

<target name="compile-adapter">
    <javac srcdir="src/adapter/java"
           destdir="build/adapter-classes"
           includeantruntime="false">
        <classpath refid="adapter.compile.classpath" />
    </javac>
</target>
```

Classpath này gồm output của phần nền và các dependency bên ngoài. Nếu module adapter được biên dịch trước module nền, build cần khai báo dependency giữa các target để bảo đảm output đã tồn tại.

### 3.4. Chỉ đưa dependency biên dịch cần thiết

Không phải mọi thư viện có trên máy đều cần đưa vào compiler classpath. Chỉ thêm các dependency mà mã nguồn thực sự tham chiếu hoặc compiler cần để xử lý cấu hình tương ứng.

Một số dependency chỉ cần khi chạy, ví dụ driver hoặc provider được nạp động bằng tên lớp. Ngược lại, annotation processor hoặc thư viện được dùng trong mã nguồn có thể cần xuất hiện ở compiler classpath hoặc processor path tùy cấu hình compiler. Hãy phân biệt dependency được tham chiếu trực tiếp với dependency được nạp động.

## 4. Application runtime classpath

### 4.1. JVM cần classpath khi chạy ứng dụng

Biên dịch thành công chỉ chứng minh compiler tìm được các kiểu cần thiết trong quá trình biên dịch. Khi ứng dụng chạy, JVM phải tìm được mọi lớp cần nạp tại thời điểm thực thi.

Ví dụ, lớp GreetingService đã biên dịch nhưng khi chạy ứng dụng lại thiếu JAR chứa StringUtils, JVM có thể báo NoClassDefFoundError hoặc ClassNotFoundException tùy thời điểm và cách nạp lớp.

Trong Ant, task java có thể nhận classpath dành cho ứng dụng:

```xml
<path id="app.runtime.classpath">
    <pathelement location="build/classes" />
    <fileset dir="lib/runtime" includes="*.jar" />
</path>

<target name="run" depends="compile">
    <java classname="com.example.Main" fork="true">
        <classpath refid="app.runtime.classpath" />
    </java>
</target>
```

Với fork="true", Ant khởi chạy một JVM riêng cho ứng dụng. Classpath được khai báo trong task java sẽ được dùng cho tiến trình đó. Đây là cách dễ quan sát và kiểm soát khi cần chạy ứng dụng với runtime classpath độc lập với Ant.

### 4.2. Compiler classpath và runtime classpath có thể khác nhau

Một thư viện có thể cần khi biên dịch và cũng cần khi chạy. Nhưng có những thư viện chỉ phục vụ biên dịch hoặc chỉ được nạp ở runtime. Vì vậy, không nên mặc định hai classpath phải giống nhau hoàn toàn.

Ví dụ:

| Loại dependency | Compiler classpath | Application runtime classpath |
|---|---:|---:|
| API mà mã nguồn import và dùng trực tiếp | Có | Thường có |
| Thư viện triển khai được gọi trực tiếp khi chạy | Có nếu mã nguồn cần kiểu của nó | Có |
| Thư viện được nạp động qua ServiceLoader/reflection | Có thể không cần nếu không tham chiếu trực tiếp | Có nếu ứng dụng cần provider |
| Công cụ chỉ dùng để tạo mã hoặc kiểm tra build | Có thể có ở compiler/tool path riêng | Không |
| Thư viện Ant custom task | Không | Không |

Một ví dụ phổ biến là thư viện API compile-time và implementation được cung cấp lúc chạy. Khi đó, compiler chỉ cần API để biên dịch, còn JVM cần implementation tương ứng khi thực thi. Cách tổ chức chính xác phụ thuộc thiết kế thư viện và cách ứng dụng nạp nó.

### 4.3. Khi chạy ứng dụng từ JAR

Nếu ứng dụng được chạy bằng lệnh java với class name, có thể truyền classpath rõ ràng:

```text
java -cp "build/classes;lib/runtime/*" com.example.Main
```

Trên Linux hoặc macOS, dấu phân cách các mục classpath thường là dấu hai chấm:

```text
java -cp "build/classes:lib/runtime/*" com.example.Main
```

Trong Ant, nên dùng data type path thay vì tự nối dấu phân cách theo hệ điều hành. Ant sẽ chuyển đổi đường dẫn phù hợp với nền tảng đang chạy.

Nếu chạy ứng dụng bằng java -jar, JVM dùng manifest của JAR để xác định lớp chính và có thể dùng thuộc tính Class-Path trong manifest để tham chiếu các JAR dependency bên ngoài. Không nên cho rằng có thể kết hợp tùy ý -jar và -cp để thêm classpath bên ngoài: khi dùng -jar, classpath người dùng truyền bằng -cp bị bỏ qua theo quy tắc khởi chạy Java.

Một ứng dụng phát hành theo dạng thư mục có thể được tổ chức như sau:

```text
dist/
├── application.jar
└── lib/
    ├── commons-lang3.jar
    └── logging-api.jar
```

Nếu dùng manifest Class-Path, các đường dẫn thường được ghi tương đối từ vị trí JAR chính, ví dụ lib/commons-lang3.jar. Cần kiểm tra manifest và cấu trúc thư mục thực tế trong gói phát hành.

## 5. Test classpath

### 5.1. Test cần nhiều thành phần hơn application classpath

Test thường tham chiếu trực tiếp các lớp ứng dụng, các lớp test và thư viện test framework. Khi thực thi test, test runner còn cần các dependency ứng dụng mà mã được kiểm thử sử dụng.

Một test classpath điển hình gồm:

- build/classes: các lớp chính đã biên dịch.
- build/test-classes: các lớp test đã biên dịch.
- Các thư viện runtime của ứng dụng.
- Các thư viện test framework và test utilities.
- Tài nguyên test đã được sao chép vào test output hoặc thư mục tài nguyên riêng.

Không đưa các lớp test hoặc JUnit vào application runtime classpath của sản phẩm nếu ứng dụng không cần chúng khi chạy thực tế.

### 5.2. Tách compiler classpath của test

Khi biên dịch test, compiler cần nhìn thấy lớp ứng dụng và các thư viện mà mã test tham chiếu. Ví dụ:

```xml
<path id="test.compile.classpath">
    <pathelement location="build/classes" />
    <fileset dir="lib/application" includes="*.jar" />
    <fileset dir="lib/test" includes="*.jar" />
</path>

<target name="compile-test" depends="compile">
    <mkdir dir="build/test-classes" />

    <javac srcdir="src/test/java"
           destdir="build/test-classes"
           includeantruntime="false"
           encoding="UTF-8">
        <classpath refid="test.compile.classpath" />
    </javac>
</target>
```

Trong ví dụ, test.compile.classpath chứa output ứng dụng, dependency ứng dụng và thư viện test. Nếu mã test dùng JUnit, JUnit API phải có mặt ở đây để compiler phân giải các annotation và assertion mà test sử dụng.

### 5.3. Tách runtime classpath của test

Khi chạy test, test runner cần cả lớp chính lẫn lớp test:

```xml
<path id="test.runtime.classpath">
    <pathelement location="build/classes" />
    <pathelement location="build/test-classes" />
    <fileset dir="lib/application" includes="*.jar" />
    <fileset dir="lib/test" includes="*.jar" />
</path>
```

Với Ant JUnit task, có thể tham chiếu classpath này:

```xml
<target name="test" depends="compile-test">
    <junit fork="true" printsummary="true" haltonfailure="true">
        <classpath refid="test.runtime.classpath" />
        <formatter type="plain" usefile="false" />
        <batchtest>
            <fileset dir="build/test-classes"
                     includes="**/*Test.class" />
        </batchtest>
    </junit>
</target>
```

Đây là ví dụ cho test runner tương thích với Ant JUnit task. Dự án phải có task Ant JUnit phù hợp và thư viện JUnit tương ứng. Thành phần Ant JUnit cần được Ant nạp trong Ant runtime classpath; JUnit framework và các thư viện test cần có trong test runtime classpath của tiến trình test. Hai vị trí này có thể chứa các JAR khác nhau và không nên nhầm lẫn.

Với test framework hoặc runner khác, cấu hình task và classpath có thể khác. Nguyên tắc vẫn giống nhau: test runner phải tìm được lớp test, lớp ứng dụng và mọi dependency cần thiết khi thực thi.

### 5.4. Tài nguyên test cũng cần được đưa vào test runtime

Nếu test đọc tệp trong src/test/resources, build phải sao chép các tệp đó vào output mà test runner sử dụng. Ví dụ:

```xml
<target name="process-test-resources">
    <mkdir dir="build/test-classes" />
    <copy todir="build/test-classes">
        <fileset dir="src/test/resources" />
    </copy>
</target>

<target name="compile-test"
        depends="compile,process-test-resources">
    <javac srcdir="src/test/java"
           destdir="build/test-classes"
           includeantruntime="false">
        <classpath refid="test.compile.classpath" />
    </javac>
</target>
```

Sau khi copy, test có thể nạp tài nguyên qua classpath nếu dùng đường dẫn tương đối phù hợp. Tài nguyên test không nên bị đưa vào JAR ứng dụng.

## 6. Tổ chức các path riêng trong build.xml

Một build file dễ bảo trì thường định nghĩa các path theo mục đích thay vì một path chung tên classpath. Ví dụ:

```xml
<project name="classpath-example" default="test" basedir=".">

    <property name="build.dir" location="${basedir}/build" />
    <property name="main.classes" location="${build.dir}/classes" />
    <property name="test.classes" location="${build.dir}/test-classes" />

    <!-- Dependency ứng dụng có thể cần ở cả compile và runtime. -->
    <path id="app.dependencies">
        <fileset dir="${basedir}/lib/application" includes="*.jar" />
    </path>

    <!-- Compiler cần các dependency ứng dụng. -->
    <path id="app.compile.classpath">
        <path refid="app.dependencies" />
    </path>

    <!-- JVM ứng dụng cần output chính và dependency runtime. -->
    <path id="app.runtime.classpath">
        <pathelement location="${main.classes}" />
        <path refid="app.dependencies" />
    </path>

    <!-- Compiler test cần lớp chính và thư viện test. -->
    <path id="test.compile.classpath">
        <pathelement location="${main.classes}" />
        <path refid="app.dependencies" />
        <fileset dir="${basedir}/lib/test" includes="*.jar" />
    </path>

    <!-- Test runner cần cả lớp chính, lớp test và dependency test. -->
    <path id="test.runtime.classpath">
        <pathelement location="${main.classes}" />
        <pathelement location="${test.classes}" />
        <path refid="app.dependencies" />
        <fileset dir="${basedir}/lib/test" includes="*.jar" />
    </path>

    <target name="compile">
        <mkdir dir="${main.classes}" />
        <javac srcdir="${basedir}/src/main/java"
               destdir="${main.classes}"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath refid="app.compile.classpath" />
        </javac>
    </target>

    <target name="run" depends="compile">
        <java classname="com.example.Main" fork="true">
            <classpath refid="app.runtime.classpath" />
        </java>
    </target>

    <target name="process-test-resources">
        <mkdir dir="${test.classes}" />
        <copy todir="${test.classes}">
            <fileset dir="${basedir}/src/test/resources" />
        </copy>
    </target>

    <target name="compile-test"
            depends="compile,process-test-resources">
        <javac srcdir="${basedir}/src/test/java"
               destdir="${test.classes}"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath refid="test.compile.classpath" />
        </javac>
    </target>

    <!-- Cấu hình test runner được bổ sung theo framework của dự án. -->
    <target name="test" depends="compile-test">
        <echo message="Run tests with test.runtime.classpath" />
    </target>

</project>
```

Các path có trách nhiệm riêng:

- app.dependencies là tập dependency dùng chung của ứng dụng.
- app.compile.classpath phục vụ compiler.
- app.runtime.classpath phục vụ JVM chạy ứng dụng.
- test.compile.classpath phục vụ compiler biên dịch test.
- test.runtime.classpath phục vụ test runner.

Ví dụ để target test in thông báo thay vì chạy framework cụ thể, nhằm giữ phần cấu hình runner độc lập với JUnit hoặc framework khác. Khi tích hợp test runner, hãy dùng test.runtime.classpath ở đúng phần tử classpath mà runner hỗ trợ.

Nếu thư viện ứng dụng chỉ cần lúc chạy mà mã nguồn không tham chiếu trực tiếp, có thể chỉ đưa nó vào app.runtime.classpath. Nếu mã nguồn cần API của thư viện đó, thêm nó vào app.compile.classpath. Tránh đưa toàn bộ thư viện test vào app.dependencies vì như vậy sẽ làm classpath ứng dụng bị lẫn dependency chỉ dành cho test.

## 7. Classpath khi đóng gói và triển khai

Classpath trong build không tự động được giữ lại sau khi đóng gói. Khi tạo JAR, task jar thường đóng gói các lớp và tài nguyên được chỉ định; nó không tự nhúng mọi JAR trong compiler classpath vào artifact.

Có ba cách triển khai dependency phổ biến:

1. Phát hành JAR ứng dụng cùng thư mục lib chứa dependency và chạy bằng classpath rõ ràng.
2. Ghi các dependency tương đối vào manifest Class-Path của JAR và giữ nguyên cấu trúc thư mục phát hành.
3. Tạo một JAR tổng hợp chứa lớp ứng dụng và dependency (fat/uber JAR) bằng một quy trình đóng gói chuyên biệt, có xử lý tài nguyên và metadata trùng lặp.

Không nên nhầm compiler classpath với danh sách thư viện sẽ được đóng gói. Nếu build thành công nhưng gói phát hành thiếu JAR runtime, ứng dụng vẫn có thể lỗi khi chạy trên máy khác.

Với gói thư mục, có thể đặt JAR ứng dụng và thư viện cạnh nhau:

```text
dist/
├── app.jar
└── lib/
    ├── dependency-a.jar
    └── dependency-b.jar
```

Script khởi chạy cần tạo runtime classpath trỏ tới app.jar và các JAR trong lib. Nếu dùng manifest Class-Path, đường dẫn trong manifest phải khớp vị trí thực tế trong gói.

## 8. Classpath và module-path của Java

Classpath là cơ chế truyền thống để JVM và compiler tìm các lớp thuộc unnamed module. Với dự án Java modular sử dụng module-info.java, có thể cần module-path thay vì chỉ classpath.

Trong task javac, Ant có các thuộc tính/phần tử hỗ trợ module path tùy phiên bản Ant và JDK. Khi làm việc với module system, cần phân biệt:

- classpath: các lớp và JAR trên classpath, thường thuộc unnamed module.
- module-path: các module được định danh và phân giải theo module system.
- processor path: đường dẫn riêng cho annotation processor nếu cấu hình compiler yêu cầu.

Không nên chuyển JAR giữa classpath và module-path một cách tùy tiện. Cách phân giải module, khả năng truy cập package và cách khai báo dependency khác nhau. Nếu dự án chưa dùng module-info.java, classpath vẫn là cơ chế thông dụng; nếu đã modular hóa, hãy thiết kế và kiểm tra module-path theo cấu trúc module của dự án.

## 9. Chẩn đoán lỗi classpath

| Biểu hiện | Nguyên nhân có thể xảy ra | Classpath cần kiểm tra |
|---|---|---|
| Ant báo không tìm thấy custom task | Thiếu JAR task mở rộng hoặc dependency của task | Ant runtime classpath, taskdef classpath |
| javac báo package hoặc symbol không tồn tại | Thiếu thư viện mà mã nguồn tham chiếu | Compiler classpath |
| Biên dịch thành công nhưng chạy báo NoClassDefFoundError | Dependency có lúc biên dịch nhưng thiếu lúc chạy | Application runtime classpath |
| Chạy test báo không tìm thấy lớp test | Test output chưa được tạo hoặc không có trong classpath runner | Test runtime classpath |
| Test không nhận ra annotation hoặc assertion | JUnit API thiếu khi biên dịch test | Test compiler classpath |
| Test khởi chạy nhưng thiếu thư viện ứng dụng | Test runner chưa có dependency runtime của ứng dụng | Test runtime classpath |
| Ứng dụng chạy trên máy phát triển nhưng lỗi trên máy khác | Máy phát triển có JAR ngoài build hoặc runtime classpath phát hành thiếu dependency | Application runtime classpath trong gói triển khai |
| Ứng dụng thấy lớp của Ant ngoài dự kiến | includeantruntime bật hoặc classpath dùng chung chứa thư viện Ant | Compiler classpath và Ant runtime leakage |

Một số lệnh và cách kiểm tra hữu ích:

- Chạy Ant với `-verbose` để xem task và quá trình build chi tiết hơn.
- In đường dẫn đã cấu hình bằng pathconvert và echo.
- Kiểm tra nội dung JAR bằng lệnh jar tf.
- Chạy JVM với tùy chọn `-verbose:class` khi cần quan sát lớp được nạp; chỉ dùng khi JVM được fork và có thể truyền JVM argument.
- So sánh classpath trong build với cấu trúc thư mục thực tế của gói phát hành.

Ví dụ in một path ra log Ant:

```xml
<pathconvert property="app.runtime.classpath.text">
    <path refid="app.runtime.classpath" />
</pathconvert>

<echo message="Application runtime classpath: ${app.runtime.classpath.text}" />
```

Pathconvert giúp xem các mục path sau khi Ant chuyển chúng thành chuỗi đường dẫn của hệ điều hành. Khi cần kiểm tra chính xác một classpath, hãy in đúng path được task sử dụng thay vì in một path khác có tên gần giống.

## 10. Nguyên tắc tổ chức classpath

- Dùng tên riêng cho từng mục đích: ant task path, app compile path, app runtime path, test compile path và test runtime path.
- Không đưa thư viện Ant vào classpath ứng dụng chỉ để sửa lỗi thiếu dependency.
- Đặt includeantruntime="false" cho javac của ứng dụng thông thường, rồi khai báo rõ các thư viện cần thiết.
- Đưa output ứng dụng vào classpath test để test có thể truy cập các lớp chính.
- Đưa output test và thư viện test vào test runtime classpath, không đưa chúng vào artifact ứng dụng.
- Xác nhận runtime dependencies được phát hành cùng ứng dụng hoặc được tham chiếu đúng trong manifest.
- Dùng path và refid để tái sử dụng danh sách đường dẫn mà không nối chuỗi thủ công.
- Nếu dùng module-info.java, kiểm tra cả module-path thay vì chỉ nhìn classpath.
- Kiểm tra classpath trong môi trường CI và trên gói phát hành, không chỉ trên máy phát triển.

Khi phân biệt rõ classpath của Ant, compiler, ứng dụng và kiểm thử, mỗi giai đoạn sẽ nhận đúng thư viện mà nó cần. Điều này giúp build ít phụ thuộc vào môi trường máy cá nhân, tránh rò rỉ thư viện công cụ vào sản phẩm và làm cho lỗi thiếu dependency dễ xác định hơn.

