# Đóng gói và chạy JAR đầu tiên

Sau khi biên dịch mã nguồn Java, bước tiếp theo thường là đóng gói các lớp đã biên dịch thành một tệp JAR để dễ phân phối và chạy. Với Apache Ant, task `jar` tạo archive theo định dạng JAR; task `java` có thể chạy lớp chính hoặc chạy trực tiếp một JAR. Nếu muốn người dùng khởi chạy ứng dụng bằng lệnh ngắn `java -jar`, JAR cần khai báo lớp bắt đầu trong manifest.

Bài học này xây dựng một ứng dụng Java nhỏ, dùng Ant để biên dịch, đóng gói thành executable JAR và chạy ứng dụng. Qua đó, bạn sẽ hiểu cấu trúc JAR, vai trò của manifest, cách truyền tham số và cách xử lý dependency khi ứng dụng cần thư viện bên ngoài.

## 1. JAR là gì?

JAR (Java Archive) là một tệp lưu trữ theo định dạng ZIP, được dùng để gom các thành phần Java vào một gói duy nhất. Một JAR có thể chứa:

- Các tệp bytecode `.class` đã biên dịch.
- Tài nguyên ứng dụng như cấu hình, ảnh, mẫu dữ liệu và tệp văn bản.
- Metadata trong thư mục `META-INF/`, bao gồm manifest.
- Chữ ký số hoặc metadata bổ sung trong những trường hợp cần xác minh nguồn gốc và tính toàn vẹn.

Ví dụ, thay vì gửi nhiều thư mục chứa các tệp class riêng lẻ, bạn có thể gửi một tệp `hello-ant.jar`. JVM đọc các lớp trong JAR như đọc lớp từ một thư mục classpath.

Một JAR thông thường có thể được dùng làm thư viện cho ứng dụng khác. Một **executable JAR** (JAR có thể khởi chạy trực tiếp) còn khai báo lớp chính trong manifest để Java biết cần gọi phương thức `main` nào.

Hai khái niệm này có liên quan nhưng không hoàn toàn giống nhau:

| Loại JAR | Nội dung và cách sử dụng |
|---|---|
| JAR thư viện | Chứa lớp và tài nguyên để ứng dụng khác đưa vào classpath |
| JAR ứng dụng | Chứa các lớp của một ứng dụng; có thể chạy qua classpath và tên lớp chính |
| Executable JAR | Có manifest khai báo `Main-Class`, có thể chạy bằng `java -jar` |

Không phải cứ có đuôi `.jar` là có thể chạy bằng `java -jar`. Nếu manifest không có `Main-Class` hợp lệ, Java không biết điểm bắt đầu của ứng dụng.

## 2. Chuẩn bị ứng dụng Java mẫu

Tạo một thư mục dự án có cấu trúc như sau:

```text
hello-ant/
├── build.xml
└── src/
    └── com/
        └── example/
            └── hello/
                └── Main.java
```

Tệp `Main.java`:

```java
package com.example.hello;

public class Main {

    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "Ant";
        System.out.println("Xin chào, " + name + "!");
    }
}
```

Lớp có một phương thức:

```java
public static void main(String[] args)
```

Đây là điểm vào mà Java launcher có thể gọi. Khi chạy chương trình, các đối số sau tên lớp hoặc tên JAR được truyền vào mảng `args`. Trong ví dụ này, nếu người dùng truyền một đối số thì chương trình in lời chào với giá trị đó; nếu không truyền, chương trình dùng tên mặc định là `Ant`.

Tên package và vị trí tệp cần khớp nhau. Với package `com.example.hello`, mã nguồn nằm trong thư mục `com/example/hello`; sau khi biên dịch, tệp bytecode sẽ nằm trong đường dẫn tương ứng bên dưới thư mục output.

## 3. Viết build.xml để biên dịch và đóng gói

Tạo tệp `build.xml` ở thư mục gốc dự án:

```xml
<project name="hello-ant" default="jar" basedir=".">

    <property name="src.dir" location="${basedir}/src"/>
    <property name="build.dir" location="${basedir}/build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.dir" location="${basedir}/dist"/>
    <property name="jar.file" location="${dist.dir}/hello-ant.jar"/>

    <property name="main.class" value="com.example.hello.Main"/>
    <property name="java.version" value="17"/>

    <target name="clean">
        <delete dir="${build.dir}"/>
        <delete dir="${dist.dir}"/>
    </target>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac
            srcdir="${src.dir}"
            destdir="${classes.dir}"
            includeantruntime="false"
            encoding="UTF-8"
            source="${java.version}"
            target="${java.version}"/>
    </target>

    <target name="jar" depends="compile">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${jar.file}" basedir="${classes.dir}">
            <manifest>
                <attribute
                    name="Main-Class"
                    value="${main.class}"/>
            </manifest>
        </jar>
        <echo message="Đã tạo ${jar.file}"/>
    </target>

    <target name="run" depends="jar">
        <java jar="${jar.file}" fork="true" failonerror="true"/>
    </target>

</project>
```

Ví dụ này dùng Java 17 làm mức source/bytecode minh họa. Hãy đổi thuộc tính `java.version` theo JDK và mức Java mà dự án hỗ trợ. Giá trị `source` và `target` phải được compiler đang dùng hỗ trợ; với JDK mới, có thể cân nhắc thuộc tính `release` của task `javac` để giới hạn cả API nền tảng theo phiên bản mục tiêu khi phiên bản Ant hỗ trợ thuộc tính đó.

### Vai trò của từng phần

**Các property**

- `src.dir`: thư mục mã nguồn.
- `build.dir`: thư mục chứa kết quả trung gian.
- `classes.dir`: nơi lưu bytecode sau khi biên dịch.
- `dist.dir`: nơi chứa sản phẩm có thể phân phối.
- `jar.file`: đường dẫn JAR đầu ra.
- `main.class`: tên đầy đủ của lớp có phương thức `main`, bao gồm package.
- `java.version`: mức Java dùng để biên dịch.

Khai báo đường dẫn bằng property giúp thay đổi cấu trúc dự án tại một nơi. Thuộc tính Ant thường có tính chất chỉ thiết lập một lần; bạn có thể truyền giá trị khác từ dòng lệnh để ghi đè giá trị mặc định khi chạy build.

**Target `clean`**

`delete` xóa output cũ để có thể build lại từ đầu. Target này không bắt buộc phải chạy trước mỗi lần biên dịch, nhưng hữu ích khi muốn loại bỏ bytecode hoặc JAR còn sót lại từ cấu hình trước.

**Target `compile`**

`mkdir` tạo thư mục đích nếu chưa tồn tại. Task `javac` biên dịch các tệp Java tìm thấy trong `src.dir` và ghi bytecode vào `classes.dir`.

Thuộc tính `includeantruntime="false"` tránh đưa thư viện nội bộ của Ant vào classpath biên dịch một cách không chủ ý. Với dự án có dependency, hãy khai báo classpath ứng dụng rõ ràng bằng nested element `<classpath>`.

**Target `jar`**

Target này phụ thuộc vào `compile`, vì vậy Ant thực hiện biên dịch trước khi đóng gói. Task `jar` lấy nội dung trong `classes.dir` và tạo tệp `hello-ant.jar`.

Nested element `<manifest>` thêm metadata vào JAR. Thuộc tính `Main-Class` chỉ ra lớp chính mà Java launcher phải gọi. Giá trị phải là tên lớp đầy đủ, ví dụ `com.example.hello.Main`, không phải đường dẫn `com/example/hello/Main.class`.

**Target `run`**

Target `run` phụ thuộc vào `jar`, nên ứng dụng được biên dịch và đóng gói trước khi chạy. Thuộc tính `jar` của task `java` yêu cầu Ant chạy JAR đó; `fork="true"` chạy trong tiến trình JVM riêng, còn `failonerror="true"` khiến build thất bại nếu chương trình kết thúc với lỗi.

## 4. Chạy build và tạo JAR

Mở terminal tại thư mục `hello-ant`. Trước tiên, kiểm tra công cụ:

```bash
ant -version
java -version
javac -version
```

Ant cần chạy được, và môi trường biên dịch cần có JDK tương thích. Nếu chỉ có JRE hoặc không có compiler phù hợp, target `compile` có thể thất bại.

Chạy target mặc định:

```bash
ant
```

Vì project khai báo `default="jar"`, lệnh trên tương đương với:

```bash
ant jar
```

Nếu build thành công, thư mục dự án có dạng:

```text
hello-ant/
├── build/
│   └── classes/
│       └── com/
│           └── example/
│               └── hello/
│                   └── Main.class
├── dist/
│   └── hello-ant.jar
├── build.xml
└── src/
    └── com/
        └── example/
            └── hello/
                └── Main.java
```

Trong cấu trúc này:

- `src/` là mã nguồn do lập trình viên quản lý.
- `build/classes/` là kết quả biên dịch trung gian.
- `dist/` là nơi chứa JAR để phân phối.

Bạn cũng có thể truyền giá trị property khi chạy Ant:

```bash
ant -Djava.version=17 clean jar
```

Lệnh trên đặt mức Java là 17 cho lần chạy này, sau đó thực hiện `clean` và `jar`. Nếu đổi giá trị thành một phiên bản khác, JDK đang dùng phải hỗ trợ mức đó.

## 5. Kiểm tra nội dung bên trong JAR

JAR là archive ZIP nên có thể kiểm tra nội dung bằng công cụ `jar` đi kèm JDK:

```bash
jar tf dist/hello-ant.jar
```

Kết quả có thể tương tự:

```text
META-INF/
META-INF/MANIFEST.MF
com/
com/example/
com/example/hello/
com/example/hello/Main.class
```

Điều cần xác nhận là:

1. `Main.class` có trong đường dẫn khớp với package.
2. `META-INF/MANIFEST.MF` tồn tại.
3. Manifest có thuộc tính `Main-Class` với đúng tên lớp chính.

Có thể xem manifest bằng cách giải nén JAR hoặc dùng công cụ ZIP. Nội dung sẽ có dạng:

```text
Manifest-Version: 1.0
Main-Class: com.example.hello.Main
```

Ant tự tạo manifest hợp lệ khi dùng nested element `<manifest>`; bạn không cần tự nối chuỗi hoặc tự xử lý định dạng dòng của manifest.

## 6. Chạy executable JAR

Khi JAR có `Main-Class`, có thể chạy từ terminal:

```bash
java -jar dist/hello-ant.jar
```

Kết quả:

```text
Xin chào, Ant!
```

Truyền đối số cho chương trình bằng cách đặt chúng sau đường dẫn JAR:

```bash
java -jar dist/hello-ant.jar Java
```

Kết quả:

```text
Xin chào, Java!
```

Lệnh `java -jar` đọc `Main-Class` từ manifest và gọi phương thức `main` của lớp đó. Các giá trị theo sau tên JAR được chuyển thành phần tử của `String[] args`.

Bạn cũng có thể chạy thông qua Ant:

```bash
ant run
```

Nếu muốn truyền một đối số cố định trong target, thêm nested element `<arg>`:

```xml
<target name="run" depends="jar">
    <java jar="${jar.file}" fork="true" failonerror="true">
        <arg value="Java"/>
    </java>
</target>
```

Đối số trong ví dụ được truyền cho ứng dụng, không phải tham số cấu hình của Ant.

## 7. Truyền tài nguyên vào JAR

Ứng dụng thực tế thường cần tệp cấu hình hoặc tài nguyên khác. Các tệp này phải được đưa vào JAR nếu chương trình đọc chúng từ classpath.

Giả sử dự án có thêm:

```text
src/
├── com/example/hello/Main.java
└── config/
    └── greeting.txt
```

Có thể mở rộng target `compile` để sao chép tài nguyên vào cùng thư mục output:

```xml
<target name="compile">
    <mkdir dir="${classes.dir}"/>

    <javac
        srcdir="${src.dir}"
        destdir="${classes.dir}"
        includeantruntime="false"
        encoding="UTF-8"
        source="${java.version}"
        target="${java.version}"/>

    <copy todir="${classes.dir}">
        <fileset dir="${src.dir}">
            <exclude name="**/*.java"/>
        </fileset>
    </copy>
</target>
```

Vì task `jar` đóng gói toàn bộ nội dung của `classes.dir`, tệp `config/greeting.txt` cũng được đưa vào JAR. Cách này phù hợp với cấu trúc ví dụ nhỏ. Trong dự án lớn, nên tách mã nguồn và tài nguyên thành hai thư mục rõ ràng, chẳng hạn `src/main/java` và `src/main/resources`, rồi cấu hình `javac` và `copy` theo từng thư mục.

Khi đọc tài nguyên nằm trong JAR, ứng dụng nên dùng classloader, ví dụ:

```java
try (var input = Main.class.getClassLoader()
        .getResourceAsStream("config/greeting.txt")) {
    if (input == null) {
        throw new IllegalStateException("Không tìm thấy greeting.txt");
    }
    // Đọc nội dung từ input
}
```

Đường dẫn resource được tính từ gốc classpath, không phải từ thư mục làm việc của terminal.

## 8. JAR có dependency bên ngoài

Task `jar` mặc định đóng gói những tệp được chỉ định trong `basedir` hoặc fileset. Nó **không tự động gom các dependency JAR** mà ứng dụng sử dụng vào bên trong JAR đầu ra.

Ví dụ, nếu mã nguồn tham chiếu một thư viện nằm trong `lib/example-library.jar`, cần xử lý hai việc riêng:

1. Đưa thư viện vào classpath khi biên dịch và chạy.
2. Làm cho JVM tìm thấy thư viện khi người dùng khởi chạy ứng dụng đã đóng gói.

Một cách phổ biến là phân phối JAR ứng dụng cùng thư mục `lib/` và khai báo `Class-Path` trong manifest.

Giả sử cấu trúc dự án:

```text
hello-ant/
├── build.xml
├── lib/
│   └── example-library.jar
└── src/
    └── com/example/hello/Main.java
```

Khai báo path dependency:

```xml
<path id="application.classpath">
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
</path>
```

Thêm classpath vào task `javac`:

```xml
<javac
    srcdir="${src.dir}"
    destdir="${classes.dir}"
    includeantruntime="false"
    encoding="UTF-8">
    <classpath refid="application.classpath"/>
</javac>
```

Khi đóng gói, sao chép các dependency vào thư mục phân phối và khai báo đường dẫn tương đối trong manifest:

```xml
<target name="jar" depends="compile">
    <mkdir dir="${dist.dir}/lib"/>

    <copy todir="${dist.dir}/lib">
        <fileset dir="lib">
            <include name="*.jar"/>
        </fileset>
    </copy>

    <jar destfile="${jar.file}" basedir="${classes.dir}">
        <manifest>
            <attribute
                name="Main-Class"
                value="${main.class}"/>
            <attribute
                name="Class-Path"
                value="lib/example-library.jar"/>
        </manifest>
    </jar>
</target>
```

Nếu có nhiều dependency, giá trị `Class-Path` chứa các URI tương đối, phân tách bằng dấu cách, ví dụ:

```text
Class-Path: lib/example-library.jar lib/logging.jar
```

Các đường dẫn được phân giải tương đối với vị trí JAR ứng dụng. Vì vậy, nếu `hello-ant.jar` nằm trong `dist/`, thư viện ở `dist/lib/example-library.jar` có thể được tham chiếu bằng `lib/example-library.jar`. Không nên ghi đường dẫn tuyệt đối trên máy phát triển vì máy khác sẽ không có cùng cấu trúc thư mục.

### Có nên tạo một fat JAR?

Một số dự án muốn tạo một JAR duy nhất chứa cả lớp ứng dụng và nội dung dependency. Cách đóng gói này thường được gọi là **fat JAR** hoặc **uber JAR**.

Task `jar` đơn giản ở trên không tự tạo fat JAR. Có thể ghép nội dung từ các dependency bằng fileset hoặc cơ chế đóng gói phù hợp, nhưng cần xử lý cẩn thận:

- Nhiều dependency có thể chứa tệp trùng tên.
- Các tệp service provider trong `META-INF/services` có thể cần được hợp nhất thay vì ghi đè.
- Chữ ký số cũ trong `META-INF` có thể không còn hợp lệ sau khi nội dung JAR bị thay đổi.
- Manifest của các thư viện có thể chứa thuộc tính không phù hợp khi ghép.
- License và notice của dependency vẫn phải được phân phối theo yêu cầu.

Với ứng dụng nhỏ, JAR ứng dụng đi kèm thư mục `lib/` thường dễ hiểu và dễ kiểm soát hơn. Chỉ tạo fat JAR khi dự án thực sự cần cách phân phối đó và có quy tắc xử lý metadata của dependency.

## 9. Chạy JAR bằng classpath khi không dùng manifest

Không phải JAR nào cũng cần executable manifest. Nếu JAR chỉ là thư viện hoặc bạn muốn tự chỉ định lớp chính, có thể chạy bằng classpath:

```bash
java -cp dist/hello-ant.jar com.example.hello.Main
```

Khi có dependency bên ngoài, thêm chúng vào classpath. Dấu phân tách phần tử classpath là dấu chấm phẩy trên Windows và dấu hai chấm trên Linux/macOS:

```text
Windows: java -cp "dist/hello-ant.jar;dist/lib/*" com.example.hello.Main
Linux/macOS: java -cp "dist/hello-ant.jar:dist/lib/*" com.example.hello.Main
```

Ở chế độ `java -jar`, Java sử dụng manifest để tìm lớp chính và classpath của JAR; tùy chọn classpath bên ngoài không được dùng theo cách thông thường như khi chạy với `-cp`. Vì vậy, hãy chọn một cách khởi chạy phù hợp với cách phân phối ứng dụng và dependency.

Trong Ant, có thể dùng task `java` với `classname` và nested classpath:

```xml
<target name="run-with-classpath" depends="compile">
    <java
        classname="${main.class}"
        fork="true"
        failonerror="true">
        <classpath>
            <pathelement location="${classes.dir}"/>
            <fileset dir="lib">
                <include name="*.jar"/>
            </fileset>
        </classpath>
    </java>
</target>
```

Cách này gọi trực tiếp lớp chính từ output biên dịch và dependency; nó không cần manifest `Main-Class`. Đây cũng là cách hữu ích để kiểm tra ứng dụng trước khi đóng gói.

## 10. Một số lỗi thường gặp

| Lỗi hoặc biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `no main manifest attribute` | Manifest không có `Main-Class` | Thêm nested `<manifest>` và khai báo đúng tên lớp chính |
| `Could not find or load main class` | Sai tên lớp, package hoặc classpath | Kiểm tra `Main-Class`, vị trí `.class` và cấu trúc package |
| `Main method not found` | Lớp không có phương thức main đúng chữ ký | Khai báo `public static void main(String[] args)` |
| `UnsupportedClassVersionError` | JAR được biên dịch bằng mức Java mới hơn JVM đang chạy hỗ trợ | Dùng JVM tương thích hoặc biên dịch với mức Java mục tiêu thấp hơn |
| `ClassNotFoundException` hoặc `NoClassDefFoundError` | Thiếu dependency khi chạy | Kiểm tra manifest `Class-Path`, thư mục `lib/` hoặc classpath khởi chạy |
| JAR tạo được nhưng không có lớp ứng dụng | `basedir` trỏ sai thư mục hoặc output compile rỗng | Kiểm tra `destdir` của `javac` và `basedir` của task `jar` |
| Tài nguyên không tìm thấy | Tài nguyên chưa được copy vào JAR hoặc sai đường dẫn resource | Kiểm tra nội dung JAR bằng `jar tf` và đường dẫn classloader |
| Chạy được trong Ant nhưng không chạy khi phát hành | Ant đang cung cấp classpath hoặc cấu hình mà gói phân phối thiếu | Kiểm tra độc lập bằng `java -jar` trên môi trường sạch |

Một quy trình chẩn đoán hiệu quả:

1. Chạy `ant clean jar` để tạo lại output từ mã nguồn hiện tại.
2. Dùng `jar tf dist/hello-ant.jar` kiểm tra lớp và tài nguyên.
3. Đọc `META-INF/MANIFEST.MF` để xác nhận `Main-Class` và `Class-Path`.
4. Chạy trực tiếp bằng `java -jar` để tách lỗi đóng gói khỏi lỗi riêng của target Ant.
5. So sánh phiên bản JDK dùng biên dịch với phiên bản JVM dùng chạy.

Không nên chỉ dựa vào việc target `run` của Ant thành công. Môi trường Ant có thể cung cấp thêm classpath hoặc thuộc tính mà người dùng cuối không có. Hãy thử đúng lệnh khởi chạy mà bạn dự định ghi trong tài liệu phát hành.

## 11. Quy trình build thường dùng

Trong quá trình phát triển, một chuỗi thao tác ngắn gọn là:

```bash
ant clean jar
java -jar dist/hello-ant.jar
```

Khi chỉ cần biên dịch và tạo lại JAR:

```bash
ant jar
```

Khi muốn chạy thông qua build file:

```bash
ant run
```

Khi kiểm tra output:

```bash
jar tf dist/hello-ant.jar
java -jar dist/hello-ant.jar Java
```

Một JAR sẵn sàng phân phối cần có lớp chính và tài nguyên cần thiết, manifest đúng, dependency có thể được tìm thấy và mức Java tương thích với môi trường người dùng. Hãy lưu lại lệnh build và lệnh chạy trong README của dự án để thành viên khác có thể tái tạo kết quả.

## 12. Ghi nhớ

- Task `javac` biên dịch mã nguồn Java thành bytecode; task `jar` đóng gói các tệp output thành JAR.
- `Main-Class` trong `META-INF/MANIFEST.MF` xác định lớp có phương thức `main` mà Java launcher gọi.
- `java -jar app.jar` chạy executable JAR; các đối số phía sau đường dẫn JAR được chuyển cho chương trình.
- JAR không tự động chứa dependency bên ngoài. Có thể phân phối thư viện trong thư mục `lib/` và khai báo manifest `Class-Path`, hoặc dùng classpath khi khởi chạy.
- `basedir` của task `jar` quyết định nội dung được đóng gói; hãy kiểm tra archive bằng `jar tf` khi cần chẩn đoán.
- Một build thành công trong Ant chưa đảm bảo gói chạy độc lập. Hãy kiểm tra bằng đúng lệnh Java mà người dùng cuối sẽ thực thi.

Sau bài học này, bạn đã có quy trình cơ bản để biên dịch ứng dụng Java bằng Ant, tạo executable JAR và chạy nó từ terminal. Đây là nền tảng để tiếp tục đóng gói ứng dụng có tài nguyên, dependency và cấu hình phát hành phức tạp hơn.
