# Xây build Java console với compile, test, jar, run và clean bằng Apache Ant

Trong bài thực hành này, bạn sẽ tự tạo một ứng dụng **Java console** nhỏ và dùng **Apache Ant** để điều khiển toàn bộ vòng đời build: biên dịch mã nguồn, chạy kiểm thử, đóng gói thành file JAR có thể thực thi, chạy chương trình và dọn các file được sinh ra. Cuối bài, chỉ cần một file `build.xml` và các lệnh `ant`, bạn có thể thực hiện lại quy trình trên máy khác mà không phải biên dịch thủ công từng file `.java`.

Ứng dụng mẫu nhận tên người dùng rồi in câu chào. Mã nghiệp vụ được tách khỏi lớp `main` để có thể kiểm thử độc lập. Các bài test dùng một **test runner Java đơn giản** nên dự án thực hành không cần tải JUnit hay thêm thư viện bên ngoài. Đây là một lựa chọn có chủ ý để tập trung vào luồng build Ant; với dự án lớn, bạn có thể thay runner này bằng JUnit hoặc framework kiểm thử phù hợp.

## 1. Kết quả cần đạt và luồng công việc

Sau khi hoàn thành, bạn sẽ có thể:

1. Viết project Ant với `<project>`, property, target và quan hệ `depends`.
2. Dùng `<javac>` để biên dịch code ứng dụng vào `build/classes`.
3. Biên dịch mã test riêng và dùng `<java>` để chạy test, làm build thất bại nếu test sai.
4. Tạo `dist/java-console-ant.jar` bằng `<jar>`, kèm `Main-Class` trong manifest.
5. Chạy ứng dụng bằng cả target `run` và lệnh `java -jar`.
6. Dùng `clean` để loại bỏ đúng các thư mục output trước khi build lại.

Đồ thị target cuối cùng:

~~~mermaid
flowchart TD
    I[init<br/>Tạo thư mục] --> C[compile<br/>Biên dịch ứng dụng]
    C --> TC[compile-test<br/>Biên dịch test]
    TC --> T[test<br/>Chạy kiểm thử]
    T --> J[jar<br/>Đóng gói JAR]
    C --> R[run<br/>Chạy class]
    J --> RJ[run-jar<br/>Chạy JAR]
    CL[clean<br/>Xóa output cũ]
~~~

Target `clean` độc lập với nhánh build: người chạy quyết định có cần xóa output trước hay không. Target `jar` phụ thuộc `test`, vì vậy việc đóng gói chỉ diễn ra sau khi các bài kiểm thử hoàn thành thành công. Target `run` có thể chạy ứng dụng từ các class đã biên dịch mà không cần tạo JAR.

## 2. Chuẩn bị môi trường

Bài tập giả định:

- Có **JDK 17 trở lên** (ví dụ JDK 17 hoặc JDK 21), không chỉ JRE; thuộc tính `release="17"` trong `<javac>` yêu cầu compiler hỗ trợ mức Java 17.
- Có Apache Ant phiên bản 1.10.x tương thích với JDK đang dùng và hỗ trợ thuộc tính `release` của task `<javac>`.
- Lệnh `java`, `javac` và `ant` có thể gọi từ terminal.
- Terminal có thể ghi file vào thư mục dự án; ví dụ được lưu dưới dạng UTF-8.

Kiểm tra:

~~~bash
java -version
javac -version
ant -version
~~~

Ví dụ kết quả có thể tương tự:

~~~text
openjdk version "21.x" ...
javac 21.x
Apache Ant(TM) version 1.10.x compiled on ...
~~~

Các phiên bản trên chỉ minh họa; không cần kết quả trùng từng ký tự. Nếu `javac` không được nhận diện dù `java` hoạt động, hãy kiểm tra JDK và cấu hình `JAVA_HOME`/`PATH`. Trên Windows dùng PowerShell hoặc Command Prompt; trên Linux/macOS dùng terminal thông thường.

Tạo thư mục dự án và các thư mục nguồn:

~~~text
java-console-ant/
├── build.xml
├── src/
│   ├── main/
│   │   └── java/
│   │       └── demo/
│   │           └── console/
│   │               ├── App.java
│   │               └── Greeter.java
│   └── test/
│       └── java/
│           └── demo/
│               └── console/
│                   └── GreeterTest.java
├── build/                   # Ant sinh ra sau khi chạy
│   ├── classes/
│   └── test-classes/
└── dist/                    # Ant sinh ra sau khi đóng gói
    └── java-console-ant.jar
~~~

Ban đầu chỉ tạo `build.xml` và ba file `.java` trong `src/`. Các thư mục `build/`, `dist/` và file `.jar` là output của Ant, **không cần tạo thủ công**. Đặt thư mục output tách khỏi `src/` để thao tác `clean` không xóa mã nguồn.

## 3. Viết mã ứng dụng Java console

Chương trình có hai lớp: `Greeter` chứa chức năng tạo lời chào, còn `App` nhận đối số dòng lệnh và in kết quả.

### 3.1. Lớp nghiệp vụ `Greeter.java`

Tạo file `src/main/java/demo/console/Greeter.java`:

~~~java
package demo.console;

public final class Greeter {

    private Greeter() {
        // Lop tien ich, khong can tao instance.
    }

    public static String greet(String input) {
        String name = (input == null || input.isBlank())
                ? "bạn"
                : input.strip();

        return "Xin chào, " + name + "!";
    }
}
~~~

Quy tắc của `greet`:

- Với `"An"`, trả về `"Xin chào, An!"`.
- Với `""`, `"   "` hoặc `null`, dùng tên mặc định `"bạn"`.
- Với `"  Lan  "`, loại bỏ khoảng trắng ở hai đầu và trả về `"Xin chào, Lan!"`.

Hai phương thức `String.isBlank()` và `String.strip()` có trong các phiên bản Java hiện đại, bao gồm Java 17. Việc tách logic này giúp test trực tiếp, không cần đọc hay phân tích output của console.

### 3.2. Điểm vào `App.java`

Tạo `src/main/java/demo/console/App.java`:

~~~java
package demo.console;

public final class App {

    private App() {
    }

    public static void main(String[] args) {
        String name = args.length == 0
                ? ""
                : String.join(" ", args);

        System.out.println(Greeter.greet(name));
    }
}
~~~

`main(String[] args)` là điểm vào của ứng dụng console. Nếu không có đối số, chương trình chào `bạn`; nếu có, ghép các đối số thành tên. Sau khi build xong, bạn sẽ chạy chương trình này bằng Ant hoặc bằng JAR độc lập.

### 3.3. Tại sao cấu trúc package phải khớp đường dẫn?

Hai file khai báo:

~~~java
package demo.console;
~~~

Vì vậy nên đặt chúng dưới `src/main/java/demo/console/`. Khi `<javac>` biên dịch, Ant ghi các class theo package:

~~~text
build/classes/
└── demo/
    └── console/
        ├── App.class
        └── Greeter.class
~~~

Tên lớp đầy đủ (**fully qualified class name**) của điểm vào là `demo.console.App`. Đây sẽ là giá trị của property `main.class` và thuộc tính `Main-Class` trong JAR manifest.

## 4. Viết test runner Java không cần thư viện ngoài

Tạo `src/test/java/demo/console/GreeterTest.java`:

~~~java
package demo.console;

public final class GreeterTest {

    private static int passed = 0;

    private GreeterTest() {
    }

    public static void main(String[] args) {
        expect("Xin chào, An!", Greeter.greet("An"));
        expect("Xin chào, bạn!", Greeter.greet(""));
        expect("Xin chào, bạn!", Greeter.greet("   "));
        expect("Xin chào, bạn!", Greeter.greet(null));
        expect("Xin chào, Lan!", Greeter.greet("  Lan  "));

        System.out.println("PASS: " + passed + " checks");
    }

    private static void expect(String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected [" + expected + "], got [" + actual + "]"
            );
        }
        passed++;
    }
}
~~~

Đây là một chương trình Java bình thường với phương thức `main`, nhưng chức năng của nó là kiểm tra các đầu ra kỳ vọng. Nếu mọi điều kiện đúng, chương trình in `PASS: 5 checks` và kết thúc bình thường. Nếu một điều kiện sai, `AssertionError` không được bắt, JVM thoát với mã lỗi khác 0.

Chính **mã thoát** này sẽ được Ant sử dụng để quyết định target `test` thành công hay thất bại. Trong bài này không cần phụ thuộc JUnit. Tuy nhiên test runner tự viết chưa có tính năng của các framework chuyên dụng như discovery, reporting, fixture hay tích hợp IDE/CI phong phú; về lâu dài, dự án lớn nên dùng framework phù hợp.

## 5. Khai báo `build.xml` hoàn chỉnh

Tạo file `build.xml` ở gốc dự án với nội dung sau:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="java-console-ant"
         default="jar"
         basedir=".">

    <!-- 1. Duong dan source va output. -->
    <property name="main.src.dir" location="src/main/java"/>
    <property name="test.src.dir" location="src/test/java"/>
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="test.classes.dir" location="${build.dir}/test-classes"/>
    <property name="dist.dir" location="dist"/>

    <!-- 2. Ten class va artifact. -->
    <property name="main.class" value="demo.console.App"/>
    <property name="test.class" value="demo.console.GreeterTest"/>
    <property name="jar.name" value="java-console-ant.jar"/>
    <property name="run.name" value="Ant"/>

    <!-- 3. Classpath dung de chay app va test. -->
    <path id="main.classpath">
        <pathelement location="${classes.dir}"/>
    </path>

    <path id="test.classpath">
        <pathelement location="${classes.dir}"/>
        <pathelement location="${test.classes.dir}"/>
    </path>

    <!-- 4. Don output duoc sinh ra. -->
    <target name="clean" description="Remove generated files">
        <delete dir="${build.dir}" failonerror="true"/>
        <delete dir="${dist.dir}" failonerror="true"/>
    </target>

    <!-- 5. Tao thu muc cho viec build. -->
    <target name="init" description="Create build directories">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${test.classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <!-- 6. Bien dich ma ung dung. -->
    <target name="compile"
            depends="init"
            description="Compile application Java sources">
        <javac srcdir="${main.src.dir}"
               destdir="${classes.dir}"
               encoding="UTF-8"
               release="17"
               includeantruntime="false"/>
    </target>

    <!-- 7. Bien dich test va tham chieu classes cua app. -->
    <target name="compile-test" depends="compile">
        <javac srcdir="${test.src.dir}"
               destdir="${test.classes.dir}"
               encoding="UTF-8"
               release="17"
               includeantruntime="false">
            <classpath refid="test.classpath"/>
        </javac>
    </target>

    <!-- 8. Chay test; JVM tra ma loi thi Ant that bai. -->
    <target name="test"
            depends="compile-test"
            description="Run Java checks">
        <java classname="${test.class}"
              fork="true"
              failonerror="true">
            <classpath refid="test.classpath"/>
        </java>
    </target>

    <!-- 9. Dong goi class ung dung thanh JAR co Main-Class. -->
    <target name="jar"
            depends="test"
            description="Test and package executable JAR">
        <jar destfile="${dist.dir}/${jar.name}"
             basedir="${classes.dir}">
            <manifest>
                <attribute name="Main-Class" value="${main.class}"/>
            </manifest>
        </jar>
    </target>

    <!-- 10. Chay app truc tiep tu classes, chua can JAR. -->
    <target name="run"
            depends="compile"
            description="Run application from classes">
        <java classname="${main.class}"
              fork="true"
              failonerror="true">
            <classpath refid="main.classpath"/>
            <arg value="${run.name}"/>
        </java>
    </target>

    <!-- 11. Dong goi va chay JAR. -->
    <target name="run-jar"
            depends="jar"
            description="Test, package and run JAR">
        <java jar="${dist.dir}/${jar.name}"
              fork="true"
              failonerror="true">
            <arg value="${run.name}"/>
        </java>
    </target>
</project>
~~~

**Lưu ý:** toàn bộ file XML ở trên là một ví dụ độc lập. Bạn có thể lưu nguyên vẹn để thực hành, với đúng ba file Java đã tạo. Phần `<jar>` đóng gói từ `classes.dir`, vì vậy JAR cuối cùng chứa class ứng dụng mà **không chứa class test** ở `test-classes`.

## 6. Hiểu cấu trúc `build.xml` trước khi chạy

### `<project>`: tên, target mặc định và thư mục gốc

~~~xml
<project name="java-console-ant" default="jar" basedir=".">
~~~

- `name` giúp nhận diện project trong log.
- `default="jar"` có nghĩa khi chạy `ant` mà không nêu target, Ant thực thi target `jar`.
- `basedir="."` đặt gốc để diễn giải đường dẫn tương đối của build. Đây là lý do ta không phải ghi đường dẫn tuyệt đối của từng máy.

Trong Ant, file project phải là XML hợp lệ; thiếu thẻ đóng, tên task viết nhầm hoặc đường dẫn sai có thể khiến build thất bại trước khi chương trình Java chạy.

### `<property>`: dùng chung thông số

~~~xml
<property name="main.src.dir" location="src/main/java"/>
<property name="classes.dir" location="${build.dir}/classes"/>
<property name="main.class" value="demo.console.App"/>
~~~

`location` phù hợp với đường dẫn file/thư mục; `value` phù hợp với chuỗi như tên lớp hoặc tên artifact. Tên property được tham chiếu bằng `${...}`. Các property thông thường được gán một lần: thứ tự định nghĩa quan trọng nếu property này phụ thuộc property khác.

Ví dụ, `build.dir` phải được xác lập trước khi Ant đánh giá `classes.dir` trong cấu hình này. Có thể thay đổi giá trị cấu hình bằng `-D` khi chạy Ant, nhưng không nên tự ý cho thư mục build trỏ vào thư mục mã nguồn, vì target `clean` sẽ xóa đường dẫn đó.

### `<path>` và `<classpath>`: chỉ rõ class Ant/Java được nạp từ đâu

~~~xml
<path id="test.classpath">
    <pathelement location="${classes.dir}"/>
    <pathelement location="${test.classes.dir}"/>
</path>
~~~

Khi chạy test, JVM cần cả class test `GreeterTest.class` và class nghiệp vụ `Greeter.class`. Khi chạy ứng dụng, JVM chỉ cần class chính trong `classes.dir`. Việc tách hai classpath này làm rõ phần nào được dùng trong quá trình kiểm thử và phần nào là ứng dụng.

`id` đặt tên tham chiếu; `refid` sử dụng lại tham chiếu đó ở task khác. Ant/Java sẽ dùng dấu phân cách classpath phù hợp với hệ điều hành; không cần viết thủ công dấu `;` trên Windows hay dấu `:` trên Unix trong ví dụ này.

### `depends`: biểu diễn quan hệ giữa các target

~~~xml
<target name="test" depends="compile-test">
    ...
</target>

<target name="jar" depends="test">
    ...
</target>
~~~

Khi chạy `ant jar`, Ant thực hiện các target phụ thuộc cần thiết trước:

~~~text
init
  -> compile
      -> compile-test
          -> test
              -> jar
~~~

Khi chạy `ant run`, đường đi ngắn hơn:

~~~text
init -> compile -> run
~~~

Quan hệ phụ thuộc giúp người dùng không phải nhớ gọi thủ công tất cả bước tiền đề. Target `clean` không nằm trong dependency của `jar` để build có thể tận dụng class đã biên dịch khi nguồn không thay đổi.

## 7. Bước thực hành 1 — chạy `compile`

Mở terminal ở thư mục chứa `build.xml`:

~~~bash
ant -f build.xml compile
~~~

Kết quả log điển hình (đường dẫn và số dòng có thể khác):

~~~text
Buildfile: .../java-console-ant/build.xml

init:
    [mkdir] Created dir: .../java-console-ant/build/classes
    [mkdir] Created dir: .../java-console-ant/build/test-classes
    [mkdir] Created dir: .../java-console-ant/dist

compile:
    [javac] Compiling 2 source files to .../build/classes

BUILD SUCCESSFUL
Total time: ...
~~~

Quan sát thư mục `build/classes`:

~~~text
build/classes/
└── demo/
    └── console/
        ├── App.class
        └── Greeter.class
~~~

Điểm cần hiểu:

- `<mkdir>` chuẩn bị thư mục trước khi biên dịch.
- `<javac>` đọc `src/main/java` và ghi file `.class` vào `build/classes`.
- `encoding="UTF-8"` giúp compiler đọc đúng ký tự tiếng Việt trong source.
- `release="17"` yêu cầu biên dịch theo API/ngôn ngữ của Java 17.
- `includeantruntime="false"` tránh tự động đưa các thư viện Ant vào classpath của ứng dụng.

Chạy lại cùng lệnh mà không sửa source:

~~~bash
ant -f build.xml compile
~~~

Thông thường `<javac>` chỉ biên dịch những file mà nó xác định cần cập nhật; vì vậy log lần thứ hai có thể không còn dòng `Compiling 2 source files`. Đó là đặc trưng của **build tăng dần**. Nếu muốn quan sát quá trình biên dịch từ đầu, dùng `clean` trước.

## 8. Bước thực hành 2 — biên dịch và chạy `test`

Chạy:

~~~bash
ant -f build.xml test
~~~

Ant thực hiện `init`, `compile`, `compile-test` rồi `test`. Ví dụ output:

~~~text
compile-test:
    [javac] Compiling 1 source file to .../build/test-classes

test:
     [java] PASS: 5 checks

BUILD SUCCESSFUL
Total time: ...
~~~

### Vì sao phải biên dịch test riêng?

Mã nguồn kiểm thử nằm ở `src/test/java`, không thuộc `src/main/java`. Nếu chỉ biên dịch class ứng dụng, JVM chưa có `GreeterTest.class`. Target `compile-test` tạo file test:

~~~text
build/test-classes/
└── demo/
    └── console/
        └── GreeterTest.class
~~~

Lệnh `<javac>` của test dùng classpath chứa output của ứng dụng, vì `GreeterTest` gọi `Greeter.greet(...)`. Khi chạy test, `test.classpath` chứa cả hai nhóm `.class`.

### Vì sao `fork="true"` và `failonerror="true"` quan trọng?

~~~xml
<java classname="${test.class}"
      fork="true"
      failonerror="true">
    <classpath refid="test.classpath"/>
</java>
~~~

- `fork="true"` khiến Ant chạy chương trình test trong JVM con thay vì thực thi trong cùng JVM với Ant. Điều này tách trạng thái chương trình và giúp quản lý mã thoát.
- `failonerror="true"` yêu cầu Ant báo lỗi nếu chương trình Java kết thúc không thành công; nhờ đó build không đi tiếp tới `jar` khi kiểm thử thất bại.

### Chủ động tạo một test thất bại để thấy Ant dừng build

Để thử cơ chế này, tạm đổi một dòng trong `GreeterTest.java`:

~~~java
expect("Xin chào, Sai!", Greeter.greet("An"));
~~~

Sau đó chạy:

~~~bash
ant -f build.xml jar
~~~

`Greeter.greet("An")` thực tế trả về `"Xin chào, An!"`, nên test ném `AssertionError`. Output có thể tương tự:

~~~text
test:
     [java] Exception in thread "main" java.lang.AssertionError:
     [java] Expected [Xin chào, Sai!], got [Xin chào, An!]

BUILD FAILED
.../build.xml:...: Java returned: 1
~~~

Vì `jar` phụ thuộc `test`, Ant **không thực thi task đóng gói trong target `jar` của lượt chạy thất bại**. Lưu ý: nếu từ lượt build trước đã tồn tại file `dist/java-console-ant.jar`, nó vẫn có thể còn trên đĩa; việc test lỗi không tự động xóa artifact cũ.

Sau khi quan sát, **khôi phục lại**:

~~~java
expect("Xin chào, An!", Greeter.greet("An"));
~~~

Và chạy lại `ant -f build.xml test` để xác nhận kiểm thử thành công.

## 9. Bước thực hành 3 — tạo JAR có thể thực thi

Khi test đã đúng:

~~~bash
ant -f build.xml jar
~~~

Hoặc đơn giản:

~~~bash
ant -f build.xml
~~~

Vì `default="jar"`, hai lệnh cùng chọn target cuối là `jar`. Ant thực hiện đủ dependency, rồi chạy:

~~~xml
<jar destfile="${dist.dir}/${jar.name}"
     basedir="${classes.dir}">
    <manifest>
        <attribute name="Main-Class" value="${main.class}"/>
    </manifest>
</jar>
~~~

`destfile` xác định tên file JAR đầu ra; `basedir` xác định thư mục được đóng gói. Manifest chứa tên lớp `main` đầy đủ. Sau khi thực hiện, ta có:

~~~text
dist/
└── java-console-ant.jar
~~~

Nội dung JAR về cơ bản:

~~~text
META-INF/
└── MANIFEST.MF
demo/
└── console/
    ├── App.class
    └── Greeter.class
~~~

Không nên có `GreeterTest.class` vì JAR chỉ đóng gói `build/classes`. Đây là lý do cần tách `classes.dir` và `test.classes.dir` từ đầu.

### Kiểm tra nội dung archive và manifest

JDK cung cấp công cụ `jar`:

~~~bash
jar tf dist/java-console-ant.jar
~~~

Lệnh này liệt kê nội dung JAR; tìm `App.class`, `Greeter.class` và `META-INF/MANIFEST.MF`. Nếu muốn xem nội dung manifest, có thể dùng công cụ giải nén hoặc chức năng của IDE để đọc file `META-INF/MANIFEST.MF` trong archive. Manifest kỳ vọng có thông tin tương đương:

~~~text
Manifest-Version: 1.0
Main-Class: demo.console.App
~~~

Ant/JAR có thể bổ sung các thuộc tính manifest khác. Điều cần xác nhận là `Main-Class` trỏ đến đúng `demo.console.App`, nơi có phương thức `public static void main(String[] args)`.

### Chạy JAR trực tiếp bằng Java

~~~bash
java -jar dist/java-console-ant.jar
~~~

Kết quả:

~~~text
Xin chào, bạn!
~~~

Truyền tên:

~~~bash
java -jar dist/java-console-ant.jar An
~~~

Kết quả:

~~~text
Xin chào, An!
~~~

Nếu JAR không có `Main-Class`, Java có thể báo `no main manifest attribute`. Nếu manifest tham chiếu lớp không tồn tại trong archive, lỗi có thể liên quan `Could not find or load main class`. Cả hai tình huống phải được xử lý tại cấu hình đóng gói hoặc đường dẫn output của compiler.

## 10. Bước thực hành 4 — chạy target `run`

Target `run` khởi động ứng dụng từ các file class:

~~~bash
ant -f build.xml run
~~~

Log minh họa:

~~~text
init:

compile:

run:
     [java] Xin chào, Ant!

BUILD SUCCESSFUL
Total time: ...
~~~

Tên `Ant` được lấy từ property mặc định:

~~~xml
<property name="run.name" value="Ant"/>
~~~

Muốn truyền tên khác:

~~~bash
ant -f build.xml -Drun.name=Lan run
~~~

Kết quả:

~~~text
[java] Xin chào, Lan!
~~~

Nếu giá trị chứa dấu cách, đặt đối số `-D` trong dấu nháy:

~~~bash
ant -f build.xml "-Drun.name=Lan Anh" run
~~~

Giá trị `run.name` được truyền qua:

~~~xml
<arg value="${run.name}"/>
~~~

`<arg value="...">` truyền toàn bộ giá trị như một đối số Java, kể cả khi có khoảng trắng. Nếu dùng `<arg line="...">`, việc tách nhiều đối số sẽ theo quy tắc phân tích riêng; ở đây chỉ muốn truyền một tên nên `value` dễ dự đoán hơn.

### `run` và `run-jar` khác nhau như thế nào?

| Target | Nguồn chạy | Các bước cần hoàn thành | Khi nào dùng? |
|---|---|---|---|
`run` | `build/classes` | `init → compile → run` | Phát triển nhanh, chạy ứng dụng mà chưa cần đóng gói |
`run-jar` | `dist/java-console-ant.jar` | `init → compile → compile-test → test → jar → run-jar` | Kiểm tra artifact sau khi đóng gói |
Lệnh `java -jar ...` | JAR đã tồn tại | Không tự gọi Ant | Kiểm tra file phân phối hoặc chạy ứng dụng độc lập |

Thử:

~~~bash
ant -f build.xml -Drun.name=Minh run-jar
~~~

Target `run-jar` yêu cầu test và đóng gói trước khi chạy; khi chạy ứng dụng từ JAR, lời chào vẫn đến từ mã nguồn `Greeter` đã biên dịch.

## 11. Bước thực hành 5 — `clean` và clean build

Chạy:

~~~bash
ant -f build.xml clean
~~~

Task `<delete>` xóa hai thư mục output:

~~~xml
<target name="clean">
    <delete dir="${build.dir}" failonerror="true"/>
    <delete dir="${dist.dir}" failonerror="true"/>
</target>
~~~

Sau đó, `build/classes`, `build/test-classes` và file JAR cũ không còn. Các file mã nguồn trong `src/` và `build.xml` phải được giữ nguyên.

Muốn dọn và tạo lại toàn bộ artifact trong một lệnh:

~~~bash
ant -f build.xml clean jar
~~~

Ant thực hiện target `clean` trước, rồi chạy các dependency của `jar` và tạo JAR mới. Đây là **clean build** trong cấu trúc bài học.

### Vì sao không để `jar depends="clean,test"`?

Nếu target `jar` luôn phụ thuộc `clean`, mỗi lần đóng gói đều xóa file class cũ trước khi biên dịch, kể cả khi source không thay đổi. Điều này loại bỏ lợi ích của build tăng dần và có thể khiến vòng lặp phát triển chậm hơn.

Trong dự án thực tế, CI có thể chọn chủ động chạy `clean jar` để tăng tính tái lập; người phát triển có thể chỉ chạy `jar` hoặc `run` khi cần. Luồng chính phải thể hiện lựa chọn này rõ ràng, không nên ép mọi thao tác đều bắt đầu bằng xóa output.

### Chỉ xóa output do build sở hữu

Đặt `build.dir` và `dist.dir` thành các đường dẫn dự án có thể xóa an toàn. Không trỏ các property này đến `src/`, thư mục chứa tài liệu hoặc thư mục chung của người dùng. Nếu file đang được tiến trình Java khác mở, việc xóa có thể thất bại trên một số hệ điều hành; hãy dừng tiến trình liên quan rồi chạy lại, thay vì bỏ qua lỗi và dùng artifact cũ.

## 12. Toàn bộ lệnh thường dùng

| Mục đích | Lệnh | Kết quả |
|---|---|---|
Xem mục tiêu có mô tả | `ant -f build.xml -projecthelp` | Danh sách target và mô tả |
Biên dịch ứng dụng | `ant -f build.xml compile` | Class trong `build/classes` |
Chạy test | `ant -f build.xml test` | Test thành công hoặc build thất bại |
Đóng gói JAR | `ant -f build.xml jar` | `dist/java-console-ant.jar` |
Build theo target mặc định | `ant -f build.xml` | Tương đương chọn `jar` |
Chạy từ class | `ant -f build.xml run` | Ứng dụng chạy với tên mặc định |
Chạy với tham số | `ant -f build.xml -Drun.name=Lan run` | In lời chào cho `Lan` |
Tạo rồi chạy JAR | `ant -f build.xml run-jar` | Test, đóng gói và khởi động artifact |
Chạy JAR độc lập | `java -jar dist/java-console-ant.jar An` | Không gọi Ant |
Dọn output | `ant -f build.xml clean` | Xóa `build/` và `dist/` |
Build sạch | `ant -f build.xml clean jar` | Xóa output, biên dịch, test và đóng gói lại |

Lưu ý rằng `ant clean jar` là **hai target được yêu cầu theo thứ tự**, không phải một target tên `clean jar`. Ant sẽ không xóa mã nguồn nếu `clean` chỉ nhắm đúng hai thư mục output như trong `build.xml` của bài.

## 13. Các lỗi thường gặp khi thực hành

### 13.1. `Unable to find a javac compiler` hoặc `javac` không được nhận diện

**Triệu chứng:** Ant có thể chạy nhưng target `compile` thất bại vì không tìm được Java compiler.

**Kiểm tra:** chạy `javac -version`, xác nhận đang dùng JDK và kiểm tra `JAVA_HOME`/`PATH`. Ant cần truy cập compiler tương thích với mức `release` đang yêu cầu. Nếu bạn dùng JDK thấp hơn 17, hãy nâng JDK cho bài thực hành hoặc thay đổi yêu cầu phiên bản một cách có chủ đích.

### 13.2. `release` không được hỗ trợ hoặc sai phiên bản Java

**Triệu chứng:** phiên bản Ant quá cũ không nhận thuộc tính `release`, hoặc compiler báo không hỗ trợ release yêu cầu.

**Kiểm tra:** `ant -version` và `javac -version`. Ví dụ này giả định JDK 17+ và Ant 1.10.x phù hợp. Không nên chỉ xóa thuộc tính `release` để che khác biệt phiên bản, vì khi đó ứng dụng có thể vô tình dùng API không phù hợp với runtime mục tiêu.

### 13.3. Lỗi `package demo.console does not exist` hoặc `cannot find symbol` khi biên dịch test

**Nguyên nhân có thể:** test chưa thấy class ứng dụng hoặc package/path chưa khớp.

**Kiểm tra:** target `compile-test` phải phụ thuộc `compile`, classpath test phải chứa `build/classes`, và `GreeterTest.java` phải khai báo đúng `package demo.console;`. Tên class được gọi phải đúng chữ hoa/thường.

### 13.4. `Could not find or load main class demo.console.App`

**Nguyên nhân có thể:** tên `main.class` sai, file `App.class` chưa được biên dịch hoặc classpath không chứa `build/classes`.

**Kiểm tra:** trong `build/classes/demo/console/` phải có `App.class`. Không đặt `main.class` thành đường dẫn file `demo/console/App.class`; Java yêu cầu tên lớp đầy đủ `demo.console.App`.

### 13.5. `no main manifest attribute` khi chạy `java -jar`

**Nguyên nhân:** JAR thiếu thuộc tính `Main-Class` trong `META-INF/MANIFEST.MF`.

**Kiểm tra:** target `jar` có `<manifest>` với `<attribute name="Main-Class" value="..."/>`. Sau khi sửa, chạy lại `ant clean jar` rồi kiểm tra đúng file JAR mới được tạo, tránh vô tình chạy bản cũ ở đường dẫn khác.

### 13.6. Test in `AssertionError` rồi `BUILD FAILED`

**Đây là kết quả mong muốn nếu kiểm thử sai.** Đọc hai giá trị `Expected` và `got`, tìm phương thức cần sửa hoặc dữ liệu kỳ vọng chưa đúng. `failonerror="true"` giúp pipeline không đóng gói một phiên bản đang lỗi test.

Nếu trong `dist/` còn JAR từ build trước, đừng nhầm file đó với artifact vừa được tạo trong lượt test thất bại.

### 13.7. Chạy `ant jar` thành công nhưng output không như kỳ vọng

**Kiểm tra:** có đang chạy đúng `build.xml` không? Đường dẫn `src/main/java` và `dist/` có đúng project hiện tại không? Source mới đã được lưu trước khi build chưa? Có nhiều bản JAR cùng tên ở những thư mục khác nhau không?

Nếu nghi output cũ, chạy `ant -f build.xml clean jar` rồi dùng `jar tf` để xem nội dung. Đừng sửa task `<jar>` khi lỗi thực tế là chạy nhầm artifact.

### 13.8. Không xóa được `build/` hoặc `dist/`

**Nguyên nhân có thể:** JAR/file log đang được một process khác sử dụng, quyền của thư mục không phù hợp hoặc tiến trình khác cùng thao tác output.

**Kiểm tra:** đóng JVM đang chạy ứng dụng, IDE/trình xem archive có thể giữ file, và kiểm tra quyền truy cập. Trên Windows, handle có thể chặn xóa file; trên Linux/macOS, việc xóa file đang mở có hành vi khác. Không dùng `failonerror="false"` như giải pháp mặc định vì có thể tạo ra kết quả không sạch.

### 13.9. Ký tự tiếng Việt bị lỗi

**Kiểm tra:** ba file Java phải được lưu dưới dạng UTF-8, task `<javac>` có `encoding="UTF-8"` và terminal hiển thị Unicode đúng. Ở Windows, vấn đề còn có thể đến từ code page/font của terminal; không nhầm lỗi hiển thị với lỗi logic Java hoặc lỗi compiler.

## 14. Quan sát log để hiểu Ant đã làm gì

Log Ant thường được chia theo tên target:

~~~text
Buildfile: .../build.xml

init:
    [mkdir] ...

compile:
    [javac] ...

compile-test:
    [javac] ...

test:
     [java] PASS: 5 checks

jar:
      [jar] Building jar: .../dist/java-console-ant.jar

BUILD SUCCESSFUL
Total time: ...
~~~

Một số task có thể không in nhiều dòng nếu không có việc mới, đặc biệt với build tăng dần. Đừng suy ra target không chạy chỉ vì không thấy dòng `[javac] Compiling...`; hãy đối chiếu tên target và trạng thái output.

Khi cần thêm chi tiết:

~~~bash
ant -f build.xml -verbose jar
~~~

Hoặc:

~~~bash
ant -f build.xml -debug jar
~~~

`-verbose` và `-debug` giúp quan sát đường dẫn, task và classpath rõ hơn, nhưng tạo log dài hơn. Dùng chúng khi chẩn đoán, không cần bật thường xuyên cho mọi lần thực hành.

Nếu Ant báo lỗi:

~~~text
BUILD FAILED
.../build.xml:NN: <thông báo>
~~~

Số dòng trong `build.xml` chỉ tới vị trí task/configuration liên quan. Nếu log compiler báo thêm `src/main/java/.../Greeter.java:NN`, cần mở **file Java** theo số dòng đó để sửa mã nguồn. Nếu test báo `AssertionError`, hãy đối chiếu đầu vào, giá trị kỳ vọng và kết quả thực tế.

## 15. Bài tập mở rộng từ project đã tạo

### Bài 1 — Thêm tên mặc định mới

Đổi trong `build.xml`:

~~~xml
<property name="run.name" value="Người học"/>
~~~

Chạy `ant -f build.xml run`. Sau đó thử ghi đè bằng `-Drun.name=Phuong` và quan sát lời chào thay đổi mà không phải sửa Java. Bài tập này giúp hiểu property của Ant điều khiển tham số thực thi.

### Bài 2 — Tạo test mới cho tên có khoảng trắng ở giữa

Thêm vào `GreeterTest.main`:

~~~java
expect("Xin chào, Lan Anh!", Greeter.greet("  Lan Anh  "));
~~~

Sửa số kiểm tra kỳ vọng trong mô tả kết quả nếu bạn dùng output mới. Chạy `ant test`; vì source test đã thay đổi, Ant cần biên dịch lại lớp test. Bài tập kiểm tra tính độc lập giữa source ứng dụng và source test.

### Bài 3 — Chỉ cho phép tạo JAR khi test thành công

Thử cố tình cho một kỳ vọng sai trong `GreeterTest` rồi chạy `ant clean jar`. Quan sát rằng quá trình dừng ở `test` và file JAR mới không được tạo. Sau đó khôi phục test và chạy lại. So sánh việc có `depends="test"` với việc chỉ dùng `depends="compile"` trong target `jar`, từ đó giải thích vai trò của kiểm thử trong pipeline.

### Bài 4 — Đổi tên artifact mà không sửa Java

Thay:

~~~xml
<property name="jar.name" value="greeting-console.jar"/>
~~~

Chạy `ant clean jar` rồi kiểm tra file mới ở `dist/greeting-console.jar`. Mã Java vẫn có `demo.console.App` làm điểm vào; tên file JAR không cần trùng tên class.

### Bài 5 — Bổ sung tài nguyên vào JAR

Tạo file `src/main/resources/message.txt` và mở rộng `build.xml` bằng target copy tài nguyên:

~~~xml
<property name="resources.dir" location="src/main/resources"/>

<target name="resources" depends="init">
    <copy todir="${classes.dir}">
        <fileset dir="${resources.dir}"/>
    </copy>
</target>
~~~

Sau đó đổi dependency target `jar` từ `depends="test"` thành `depends="test,resources"` để tài nguyên được copy vào `classes.dir` trước khi đóng gói. Lưu ý cần thêm `<property>` ở cấp project và target `resources` ở cấp project, không đặt lồng vào target khác.

Chạy `ant clean jar` và dùng `jar tf` để xem `message.txt` có xuất hiện không. Bài tập minh họa cách thêm một giai đoạn mà vẫn giữ quan hệ phụ thuộc rõ ràng.

### Bài 6 — Thử build từ đầu và build tăng dần

Chạy hai lệnh liên tiếp:

~~~bash
ant -f build.xml clean jar
ant -f build.xml jar
~~~

Quan sát các dòng của `<javac>` trong log. Lần đầu phải tạo class mới, còn lần thứ hai có thể ít công việc biên dịch hơn vì output đã được cập nhật. Từ đó giải thích tại sao target `clean` không nên trở thành dependency bắt buộc của mọi target.

## 16. Nâng cấp khi dự án có nhiều bài test

Test runner `GreeterTest` đủ cho mục đích thực hành điều phối Ant và hiểu mã thoát. Dự án Java thực tế thường chọn JUnit để quản lý nhiều lớp test, assertion, fixture, báo cáo và tích hợp CI. Khi chuyển sang JUnit:

- Test sẽ dùng API của một phiên bản JUnit cụ thể thay vì phương thức `main` tự viết.
- Target biên dịch test cần classpath chứa thư viện kiểm thử và output của ứng dụng.
- Target `test` phải gọi runner tương ứng. Với JUnit 4, Ant có task tùy chọn `<junit>` nhưng cần các thư viện Ant/JUnit tương thích; với JUnit 5 (JUnit Platform), cách tích hợp khác và phải chọn launcher/task phù hợp.
- Mã lỗi kiểm thử vẫn phải khiến Ant báo `BUILD FAILED` để `jar` không chạy tiếp khi test chưa đạt.

Không cần đổi sang JUnit để hoàn thành bài này. Điều cần nắm vững trước là **target test phải thực sự chạy kiểm thử**, nhận biết thất bại và là điều kiện để đóng gói artifact.

## 17. Tự tổng kết vòng đời của project

Một quy trình hoàn chỉnh mà bạn có thể thực hiện từ trạng thái sạch:

~~~bash
# 1. Xóa output của lần build trước
ant -f build.xml clean

# 2. Biên dịch class ứng dụng
ant -f build.xml compile

# 3. Biên dịch test và chạy 5 phép kiểm tra
ant -f build.xml test

# 4. Tạo JAR, tự đảm bảo test được chạy
ant -f build.xml jar

# 5. Chạy ứng dụng từ class
ant -f build.xml -Drun.name=Lan run

# 6. Chạy JAR trực tiếp
java -jar dist/java-console-ant.jar Minh

# 7. Dọn output sau thực hành
ant -f build.xml clean
~~~

Khi đã quen, bạn có thể thay các lệnh ở bước 1–4 bằng:

~~~bash
ant -f build.xml clean jar
~~~

Với Ant, **`compile` tạo bytecode, `test` xác minh hành vi, `jar` tạo artifact, `run` chạy ứng dụng và `clean` trả thư mục output về trạng thái sạch**. Giá trị của `build.xml` là mô tả được mối quan hệ giữa những công việc này: mỗi lần chạy, Ant tự thực hiện các điều kiện tiên quyết và dừng tại bước lỗi, giúp quá trình xây dựng ứng dụng Java console rõ ràng và lặp lại được.
