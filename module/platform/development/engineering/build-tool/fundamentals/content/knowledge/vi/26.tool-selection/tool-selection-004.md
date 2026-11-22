# Ant: target và tổ chức quy trình build tường minh

Apache Ant là công cụ build dựa trên XML. Người phát triển mô tả công việc bằng các **task** và tổ chức chúng thành các **target**. Mỗi target đại diện cho một bước hoặc một mục tiêu của quy trình, chẳng hạn tạo thư mục, biên dịch Java, chạy kiểm thử, đóng gói JAR hoặc tạo distribution. Các target có thể khai báo quan hệ phụ thuộc bằng thuộc tính **depends**, nhờ đó Ant biết target nào cần chạy trước target nào.

Ant có cách tổ chức tường minh và mang tính thủ tục: người viết build file chỉ rõ những thao tác cần thực hiện và quan hệ thứ tự giữa chúng. Cách này phù hợp khi nhóm cần kiểm soát chi tiết quy trình build, tích hợp với hệ thống cũ hoặc duy trì một build script XML ổn định.

Để tổ chức build tốt, cần hiểu cấu trúc **build.xml**, project, property, task, target, target dependency graph, classpath và các cơ chế tái sử dụng cấu hình. Một build file rõ ràng giúp người đọc xác định lệnh nào chạy bước nào, vì sao target được thực thi và cách mở rộng quy trình mà không tạo ra chuỗi phụ thuộc khó theo dõi.

## 1. Ant tổ chức build bằng project, target và task

Một build file Ant thường có cấu trúc:

~~~xml
<project name="sample-app" default="build" basedir=".">
    <property name="src.dir" location="src/main/java"/>

    <target name="compile">
        <mkdir dir="build/classes"/>
        <javac srcdir="${src.dir}" destdir="build/classes"/>
    </target>

    <target name="build" depends="compile">
        <jar destfile="build/sample-app.jar" basedir="build/classes"/>
    </target>
</project>
~~~

Ba khái niệm chính:

- **Project** là phần tử gốc của build file. Nó đặt tên, thư mục gốc và target mặc định.
- **Target** là một mục tiêu có tên, có thể chứa task và khai báo phụ thuộc vào target khác.
- **Task** là một thao tác cụ thể, ví dụ mkdir, javac, copy, delete, jar hoặc junit.

Khi chạy target build, Ant thực hiện target compile trước vì build khai báo depends="compile". Sau đó Ant thực hiện các task trong target build theo thứ tự được viết trong XML.

Có thể hình dung:

~~~text
build
  |
  v
compile
  |
  +--> mkdir
  |
  +--> javac
  |
  v
jar
~~~

Sơ đồ trên chỉ minh họa quan hệ của ví dụ. Thực tế, target build phụ thuộc compile và chứa task jar; các task trong target được thực hiện tuần tự theo thứ tự khai báo.

## 2. Build file build.xml

Tên mặc định thường dùng là **build.xml**. Khi chạy Ant từ thư mục có file này, Ant sẽ tìm và sử dụng nó.

Ví dụ cấu trúc:

~~~text
sample-app/
├── build.xml
├── build.properties
├── lib/
│   ├── runtime/
│   └── test/
├── src/
│   ├── main/
│   │   └── java/
│   └── test/
│       └── java/
└── build/
~~~

Có thể chỉ định build file khác bằng tùy chọn -f:

~~~bash
ant -f build-ci.xml build
~~~

Một build file có thể chứa nhiều target, nhưng nên chia target theo mục tiêu rõ ràng. Không nên đặt toàn bộ quy trình trong một target lớn vì khó chạy riêng từng bước, khó xác định nguyên nhân lỗi và khó tái sử dụng.

### Project name, basedir và default

Ví dụ:

~~~xml
<project
    name="sample-app"
    default="build"
    basedir=".">
    ...
</project>
~~~

- name là tên project Ant, có thể dùng trong log và biểu thức property.
- default là target được chạy khi người dùng gọi ant mà không chỉ rõ target.
- basedir là thư mục gốc để phân giải các đường dẫn tương đối trong build file.

Nếu default="build", lệnh:

~~~bash
ant
~~~

sẽ chạy target build trong build file mặc định.

Nếu target mặc định không tồn tại hoặc build file sai cú pháp, Ant báo lỗi trước khi thực hiện các bước build.

## 3. Target là đơn vị tổ chức quy trình

Một target có tên và thường đại diện cho một bước có ý nghĩa trong build:

~~~xml
<target name="clean">
    <delete dir="build"/>
</target>

<target name="compile">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java" destdir="build/classes"/>
</target>

<target name="package" depends="compile">
    <jar destfile="build/sample-app.jar" basedir="build/classes"/>
</target>
~~~

Target có thể:

- Chứa một hoặc nhiều task.
- Phụ thuộc vào target khác qua depends.
- Có điều kiện chạy qua if hoặc unless.
- Có description để hiển thị trong phần trợ giúp.
- Được gọi trực tiếp từ command line hoặc bởi target khác.

Target không nhất thiết tương ứng với một file hoặc một class. Nó biểu diễn một mục tiêu logic như clean, compile, test, package hoặc deploy.

### Task chạy theo thứ tự khai báo

Trong một target, Ant chạy task theo thứ tự từ trên xuống:

~~~xml
<target name="prepare">
    <delete dir="build/tmp"/>
    <mkdir dir="build/tmp"/>
    <copy todir="build/tmp">
        <fileset dir="src/config"/>
    </copy>
</target>
~~~

Ở đây, Ant xóa thư mục tạm, tạo lại thư mục rồi sao chép cấu hình. Nếu đảo thứ tự, thao tác delete có thể xóa file vừa được copy.

Vì vậy, thứ tự task trong một target là một phần của logic build và cần được viết có chủ đích.

## 4. depends và thứ tự giữa các target

Thuộc tính depends khai báo những target phải được thực hiện trước target hiện tại.

Ví dụ:

~~~xml
<target name="init">
    <mkdir dir="build/classes"/>
</target>

<target name="compile" depends="init">
    <javac
        srcdir="src/main/java"
        destdir="build/classes"
        includeantruntime="false"/>
</target>

<target name="package" depends="compile">
    <jar
        destfile="build/sample-app.jar"
        basedir="build/classes"/>
</target>
~~~

Khi chạy:

~~~bash
ant package
~~~

Ant thực hiện init, sau đó compile, cuối cùng package.

Có thể khai báo nhiều dependency:

~~~xml
<target name="verify" depends="compile,compile-tests,test"/>
~~~

Danh sách depends được phân tách bằng dấu phẩy. Ant xử lý các dependency trước target hiện tại; thứ tự khai báo trong danh sách được tôn trọng khi sắp xếp các prerequisite.

### Target dùng chung chỉ chạy một lần trong một invocation

Giả sử:

~~~xml
<target name="init">
    <mkdir dir="build"/>
</target>

<target name="compile" depends="init">
    ...
</target>

<target name="test" depends="init">
    ...
</target>

<target name="build" depends="compile,test">
    ...
</target>
~~~

Khi chạy build, target init là dependency của cả compile và test nhưng chỉ được thực hiện một lần trong cùng invocation của Ant.

Điều này giúp target dependency graph tránh thực thi lặp lại một target dùng chung.

### depends không phải lệnh gọi hàm

depends mô tả quan hệ trong đồ thị target. Nó không truyền tham số riêng cho target và không tạo một project context mới.

Nếu một target cần nhiều biến thể cấu hình, nên dùng property, target có điều kiện hoặc tách build file theo trách nhiệm. Không nên tạo chuỗi antcall lồng nhau chỉ để thay đổi vài giá trị.

## 5. Target graph và cách Ant thực hiện build

Các target tạo thành một đồ thị có hướng. Target được yêu cầu là điểm bắt đầu; Ant lần theo các quan hệ depends để tìm những target cần thực hiện.

Ví dụ:

~~~text
                 build
                /     \
               v       v
          compile     test
              |         |
              v         v
             init   compile-tests
                         |
                         v
                      compile
~~~

Trong ví dụ này:

- build cần compile và test.
- compile cần init.
- test cần compile-tests.
- compile-tests cần compile.
- init là target dùng chung và chỉ chạy một lần.

Ant phải thực hiện target phụ thuộc trước target yêu cầu. Một target không được gọi trực tiếp và cũng không phải dependency của target khác sẽ không tự chạy.

### Dependency cycle

Target dependency phải tạo thành đồ thị có thể sắp xếp thứ tự. Nếu A phụ thuộc B và B phụ thuộc A, Ant không thể xác định thứ tự hợp lệ.

Ví dụ sai:

~~~xml
<target name="compile" depends="package"/>
<target name="package" depends="compile"/>
~~~

Khi có chu trình, Ant báo lỗi circular dependency hoặc thông báo tương đương. Cần tách bước chuẩn bị, biên dịch và đóng gói theo hướng một chiều.

Một cấu trúc thường gặp:

~~~text
init -> compile -> test -> package -> dist
~~~

Mũi tên biểu thị prerequisite được thực hiện trước target cần nó.

## 6. Target mặc định và gọi target từ command line

Nếu build file khai báo:

~~~xml
<project name="sample-app" default="build">
~~~

thì:

~~~bash
ant
~~~

sẽ chạy target build.

Có thể chỉ định một target:

~~~bash
ant compile
~~~

Hoặc nhiều target:

~~~bash
ant clean build
~~~

Khi chỉ định nhiều target trên command line, Ant thực hiện chúng theo thứ tự yêu cầu. Trong ví dụ clean build, clean được chạy trước, sau đó build và các dependency của build.

Có thể gọi nhiều target cùng lúc:

~~~bash
ant clean test package
~~~

Cần hiểu rằng mỗi target được yêu cầu vẫn có dependency riêng. Target đã được thực hiện trong cùng invocation sẽ không bị thực hiện lại chỉ vì xuất hiện thêm trong danh sách yêu cầu.

### Xem target có sẵn

~~~bash
ant -p
~~~

hoặc:

~~~bash
ant -projecthelp
~~~

Các target có description phù hợp sẽ được hiển thị trong phần trợ giúp. Vì vậy, nên thêm description cho các target công khai như clean, compile, test, package, dist và deploy.

## 7. Property: cấu hình build bằng giá trị có tên

Property cho phép đặt giá trị có tên và sử dụng lại trong build file.

Ví dụ:

~~~xml
<property name="src.dir" location="src/main/java"/>
<property name="build.dir" location="build"/>
<property name="classes.dir" location="${build.dir}/classes"/>
<property name="jar.name" value="sample-app.jar"/>
~~~

Dùng property:

~~~xml
<target name="compile">
    <mkdir dir="${classes.dir}"/>
    <javac
        srcdir="${src.dir}"
        destdir="${classes.dir}"
        includeantruntime="false"/>
</target>
~~~

Property giúp tránh lặp lại đường dẫn và cho phép thay đổi cấu hình ở một nơi.

### Property thường là immutable

Trong Ant, property thông thường được đặt một lần. Nếu một property đã có giá trị, lệnh property tiếp theo không ghi đè nó.

Ví dụ:

~~~xml
<property name="build.mode" value="development"/>
<property name="build.mode" value="production"/>
~~~

Giá trị cuối cùng vẫn là development vì property đã được đặt trước.

Đây là đặc điểm quan trọng khi kết hợp command-line property, property file và build script.

### Truyền property từ command line

~~~bash
ant -Dbuild.version=2.3.0 package
~~~

Trong build file:

~~~xml
<property name="build.version" value="1.0.0"/>

<target name="package">
    <jar destfile="build/sample-app-${build.version}.jar"
         basedir="build/classes"/>
</target>
~~~

Property truyền bằng -D là user property và được giữ ưu tiên so với property thông thường trong build file. Do đó, người chạy build có thể chọn version mà không cần sửa XML.

### Nạp property file

~~~xml
<property file="build.properties"/>
~~~

Ví dụ build.properties:

~~~properties
java.release=17
build.version=1.2.0
app.main.class=com.example.app.Main
~~~

Có thể kết hợp:

~~~xml
<property file="build.properties"/>
<property name="build.dir" location="build"/>
~~~

Nên tách cấu hình môi trường khỏi logic target nếu nhiều môi trường cần các giá trị khác nhau.

## 8. Property file và cấu hình theo môi trường

Một build có thể có nhiều file cấu hình:

~~~text
build.properties
config/
├── dev.properties
├── test.properties
└── production.properties
~~~

Có thể chọn file qua command line:

~~~bash
ant -Denv=test -Dconfig.file=config/test.properties build
~~~

Trong build file:

~~~xml
<property file="build.properties"/>
<property name="config.file" value="config/dev.properties"/>
<property file="${config.file}"/>
~~~

Do property trong Ant thường không thể ghi đè sau khi đã được đặt, cần chú ý thứ tự nạp file và property từ command line. Property -D có thể cung cấp giá trị trước khi build file được xử lý.

Ví dụ trên chỉ là cách tổ chức đơn giản. Với cấu hình có secret, không nên commit password hoặc token vào properties file. Hãy lấy thông tin nhạy cảm từ secret store hoặc môi trường CI và tránh in chúng ra log.

## 9. Target có điều kiện: if và unless

Target có thể chạy có điều kiện dựa trên sự tồn tại của property.

Ví dụ:

~~~xml
<target name="publish" depends="package" if="release.enabled">
    <echo message="Publishing release artifact"/>
</target>
~~~

Target publish chỉ thực hiện các task bên trong khi property release.enabled đã được đặt.

Có thể dùng unless để chạy khi property chưa được đặt:

~~~xml
<target name="test" depends="compile-tests" unless="skip.tests">
    <echo message="Running tests"/>
    ...
</target>
~~~

Chạy với:

~~~bash
ant -Dskip.tests=true build
~~~

thì các task bên trong target test bị bỏ qua.

### if/unless cơ bản kiểm tra sự tồn tại của property

Với cú pháp thuộc tính if và unless cơ bản, Ant kiểm tra property đã được đặt hay chưa, không đánh giá chuỗi "true" hoặc "false" như một biểu thức boolean.

Ví dụ:

~~~bash
ant -Dskip.tests=false build
~~~

Property skip.tests vẫn được đặt, vì vậy target có unless="skip.tests" vẫn bị bỏ qua.

Nếu muốn biểu diễn điều kiện phức tạp, có thể dùng task condition để tạo property theo điều kiện hoặc các cú pháp condition hiện đại của Ant. Cần phân biệt rõ giá trị property với trạng thái property đã tồn tại.

### Dependency vẫn chạy trước khi điều kiện target được xét

Nếu target có depends, các target dependency được thực hiện trước khi Ant kiểm tra điều kiện if/unless của target hiện tại.

Ví dụ:

~~~xml
<target name="test" depends="compile-tests" unless="skip.tests">
    <junit .../>
</target>
~~~

Khi skip.tests được đặt, target compile-tests vẫn có thể chạy vì nó là dependency của test; chỉ các task trong target test bị bỏ qua.

Nếu muốn bỏ qua cả việc biên dịch test, cần thiết kế dependency graph và điều kiện ở các target phù hợp, không chỉ đặt unless ở target test.

## 10. Property và condition

Task condition có thể đặt property khi một điều kiện được thỏa mãn.

Ví dụ:

~~~xml
<condition property="is.windows">
    <os family="windows"/>
</condition>
~~~

Sau đó:

~~~xml
<target name="windows-setup" if="is.windows">
    <echo message="Configuring Windows build"/>
</target>
~~~

Có thể dùng điều kiện kiểm tra file:

~~~xml
<condition property="config.exists">
    <available file="config/app.properties"/>
</condition>
~~~

Các điều kiện thường dùng gồm OS family, file hoặc resource có tồn tại, property có giá trị phù hợp và một số điều kiện logic như and, or, not.

Property chỉ được đặt nếu điều kiện thỏa mãn. Vì property thông thường không thể ghi đè, hãy thiết kế tên property riêng cho từng điều kiện và tránh dùng lại một property với nhiều ý nghĩa.

## 11. Path và classpath

Java build thường cần classpath cho compiler, test runner và chương trình thực thi. Ant cung cấp phần tử path để tập hợp các vị trí class hoặc JAR.

Ví dụ:

~~~xml
<path id="compile.classpath">
    <fileset dir="lib/runtime">
        <include name="*.jar"/>
    </fileset>
</path>
~~~

Dùng path trong javac:

~~~xml
<javac
    srcdir="src/main/java"
    destdir="build/classes"
    includeantruntime="false">
    <classpath refid="compile.classpath"/>
</javac>
~~~

Có thể kết hợp nhiều thành phần:

~~~xml
<path id="runtime.classpath">
    <pathelement location="build/classes"/>
    <fileset dir="lib/runtime">
        <include name="*.jar"/>
    </fileset>
</path>
~~~

Dùng path cho task java:

~~~xml
<java classname="com.example.app.Main" fork="true" failonerror="true">
    <classpath refid="runtime.classpath"/>
</java>
~~~

### path khác fileset

- **path** mô tả một tập hợp vị trí dùng làm classpath hoặc đường dẫn.
- **fileset** chọn tập hợp file theo thư mục và pattern.
- **pathelement** thêm một file hoặc thư mục vào path.
- **fileset** có thể được nhúng vào path để chọn các JAR theo pattern.

Dùng path id giúp khai báo classpath một lần và tham chiếu từ nhiều target. Điều này giảm lặp lại và giúp dependency rõ ràng hơn.

## 12. Tổ chức target cho một Java build

Một quy trình Java thường có các target:

| Target | Mục đích |
|---|---|
| **init** | Tạo thư mục và chuẩn bị cấu hình |
| **clean** | Xóa output sinh ra |
| **compile** | Biên dịch source chính |
| **compile-tests** | Biên dịch source test |
| **test** | Chạy test |
| **jar** | Tạo JAR |
| **dist** | Tạo distribution |
| **run** | Chạy ứng dụng |
| **build** | Gom các bước cần thiết để tạo sản phẩm |

Một dependency chain phổ biến:

~~~text
init
 |
 v
compile
 |
 v
compile-tests
 |
 v
test
 |
 v
jar
 |
 v
dist
~~~

Không phải mọi project đều phải dùng chính xác chuỗi này. Ví dụ, target jar có thể không cần phụ thuộc test trong lúc phát triển nhanh; nhưng target build phát hành thường nên bao gồm kiểm thử bắt buộc.

## 13. Ví dụ build.xml cho Java application

Ví dụ dưới đây minh họa một build có các target init, clean, compile, compile-tests, test, jar, dist, run và build. Dự án giả định có JUnit 4 trong thư mục lib/test và các dependency runtime trong lib/runtime.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="sample-app" default="build" basedir=".">

    <property file="build.properties"/>

    <property name="src.main.dir" location="src/main/java"/>
    <property name="src.test.dir" location="src/test/java"/>
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="test.classes.dir" location="${build.dir}/test-classes"/>
    <property name="reports.dir" location="${build.dir}/reports"/>
    <property name="dist.dir" location="${build.dir}/dist"/>

    <property name="java.release" value="17"/>
    <property name="build.version" value="1.0.0"/>
    <property name="main.class" value="com.example.app.Main"/>

    <path id="runtime.dependencies">
        <fileset dir="lib/runtime">
            <include name="*.jar"/>
        </fileset>
    </path>

    <path id="test.dependencies">
        <fileset dir="lib/test">
            <include name="*.jar"/>
        </fileset>
    </path>

    <target name="init" description="Creates build directories">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${test.classes.dir}"/>
        <mkdir dir="${reports.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="clean" description="Removes generated build output">
        <delete dir="${build.dir}"/>
    </target>

    <target name="compile" depends="init"
            description="Compiles application source">
        <javac
            srcdir="${src.main.dir}"
            destdir="${classes.dir}"
            release="${java.release}"
            encoding="UTF-8"
            debug="true"
            includeantruntime="false">
            <classpath refid="runtime.dependencies"/>
        </javac>
    </target>

    <target name="compile-tests" depends="compile"
            description="Compiles test source">
        <javac
            srcdir="${src.test.dir}"
            destdir="${test.classes.dir}"
            release="${java.release}"
            encoding="UTF-8"
            debug="true"
            includeantruntime="false">
            <classpath>
                <pathelement location="${classes.dir}"/>
                <path refid="runtime.dependencies"/>
                <path refid="test.dependencies"/>
            </classpath>
        </javac>
    </target>

    <target name="test" depends="compile-tests"
            description="Runs unit tests">
        <junit printsummary="yes"
               haltonfailure="yes"
               fork="true">
            <classpath>
                <pathelement location="${classes.dir}"/>
                <pathelement location="${test.classes.dir}"/>
                <path refid="runtime.dependencies"/>
                <path refid="test.dependencies"/>
            </classpath>

            <formatter type="plain" usefile="false"/>

            <batchtest todir="${reports.dir}">
                <fileset dir="${test.classes.dir}">
                    <include name="**/*Test.class"/>
                </fileset>
            </batchtest>
        </junit>
    </target>

    <target name="jar" depends="compile"
            description="Packages application JAR">
        <jar destfile="${dist.dir}/${ant.project.name}-${build.version}.jar"
             basedir="${classes.dir}">
            <manifest>
                <attribute name="Main-Class" value="${main.class}"/>
            </manifest>
        </jar>
    </target>

    <target name="dist" depends="jar"
            description="Creates application distribution">
        <mkdir dir="${dist.dir}/lib"/>
        <copy todir="${dist.dir}/lib">
            <fileset dir="lib/runtime">
                <include name="*.jar"/>
            </fileset>
        </copy>
    </target>

    <target name="run" depends="compile"
            description="Runs application">
        <java classname="${main.class}"
              fork="true"
              failonerror="true">
            <classpath>
                <pathelement location="${classes.dir}"/>
                <path refid="runtime.dependencies"/>
            </classpath>
        </java>
    </target>

    <target name="build" depends="test,dist"
            description="Compiles, tests and packages the application">
        <echo message="Build completed: ${dist.dir}"/>
    </target>

</project>
~~~

### Lưu ý về ví dụ

- Thuộc tính release của javac yêu cầu phiên bản Ant và JDK có hỗ trợ phù hợp; ví dụ giả định môi trường hiện đại có JDK 17.
- Task junit là task tùy chọn của Ant và cần JUnit cùng phần hỗ trợ Ant JUnit tương ứng có trong môi trường Ant.
- JUnit 4 được giả định trong ví dụ. Nếu dùng JUnit 5, cần cấu hình launcher/platform hoặc một test runner tương thích khác.
- Các thư mục lib/runtime và lib/test phải tồn tại nếu build được cấu hình để đọc chúng; có thể bổ sung điều kiện hoặc tạo thư mục phù hợp với repository.
- Target dist tạo JAR và sao chép runtime library; ví dụ chưa tạo script khởi chạy.
- Artifact được đặt trong build/dist. Target clean xóa toàn bộ thư mục build.

Ví dụ này cho thấy cách tổ chức các bước theo target và dependency. Trong dự án thực tế, cần điều chỉnh dependency, test framework, Java version và cấu trúc distribution theo ứng dụng.

## 14. Target test và tích hợp JUnit

Ant có task junit để chạy test dựa trên JUnit. Task này thường cần:

- JUnit library.
- Phần tích hợp Ant JUnit có trong cài đặt Ant.
- Classpath chứa production classes, test classes và dependency test.
- Quy tắc tìm test class.
- Formatter và nơi lưu report.

Ví dụ:

~~~xml
<target name="test" depends="compile-tests">
    <junit printsummary="yes" haltonfailure="yes" fork="true">
        <classpath>
            <pathelement location="build/classes"/>
            <pathelement location="build/test-classes"/>
            <fileset dir="lib/test">
                <include name="*.jar"/>
            </fileset>
        </classpath>

        <formatter type="xml"/>
        <batchtest todir="build/reports">
            <fileset dir="build/test-classes">
                <include name="**/*Test.class"/>
            </fileset>
        </batchtest>
    </junit>
</target>
~~~

Thuộc tính haltonfailure="yes" khiến task báo lỗi nếu test thất bại. fork="true" chạy test trong JVM con, giúp tách một số trạng thái JVM khỏi tiến trình Ant.

Với JUnit 5, cần chọn cách chạy phù hợp như JUnit Platform Console Launcher hoặc một integration phù hợp. Không nên giả định task junit cổ điển tự động hỗ trợ mọi tính năng của JUnit 5.

## 15. Target clean và clean build

Target clean thường xóa output được tạo trong quá trình build:

~~~xml
<target name="clean" description="Removes build output">
    <delete dir="build"/>
</target>
~~~

Chạy:

~~~bash
ant clean
~~~

Build từ đầu:

~~~bash
ant clean build
~~~

Nếu target build phụ thuộc test và dist, Ant thực hiện clean trước, sau đó build theo graph.

Không nên đặt source hoặc file cấu hình quan trọng trong thư mục build nếu clean sẽ xóa chúng. Thư mục build nên chỉ chứa output có thể tạo lại.

### Clean riêng từng loại output

Với build lớn, có thể tạo các target clean riêng:

~~~xml
<target name="clean-classes">
    <delete dir="build/classes"/>
</target>

<target name="clean-reports">
    <delete dir="build/reports"/>
</target>

<target name="clean" depends="clean-classes,clean-reports">
    <delete dir="build/dist"/>
</target>
~~~

Tuy nhiên, nếu clean là thao tác tổng thể, thường đơn giản hơn khi xóa toàn bộ build directory. Chỉ chia nhỏ khi quy trình có nhu cầu rõ ràng, ví dụ giữ report để điều tra.

## 16. Macrodef: tái sử dụng chuỗi task

Nếu nhiều target cần lặp lại cùng một nhóm thao tác, Ant hỗ trợ macrodef để định nghĩa một macro task.

Ví dụ:

~~~xml
<macrodef name="ensure-directory">
    <attribute name="path"/>
    <sequential>
        <mkdir dir="@{path}"/>
    </sequential>
</macrodef>
~~~

Dùng macro:

~~~xml
<target name="init">
    <ensure-directory path="${classes.dir}"/>
    <ensure-directory path="${reports.dir}"/>
</target>
~~~

Macro giúp tái sử dụng một chuỗi task mà không cần copy/paste. Attribute của macro dùng cú pháp @{name}, khác với property expansion syntax trong build file.

Có thể dùng macro cho các thao tác lặp lại như tạo thư mục chuẩn, copy resource theo quy tắc chung, tạo archive với cấu trúc giống nhau hoặc chạy một nhóm bước kiểm tra.

Không nên tạo macro quá tổng quát khiến người đọc phải theo dõi nhiều tầng tham số mới hiểu được hành vi.

## 17. Import và include build file

Khi build file lớn, có thể tách target dùng chung sang file khác.

Ví dụ:

~~~text
build.xml
build.properties
ant/
├── java.xml
├── test.xml
└── package.xml
~~~

Trong build.xml:

~~~xml
<project name="sample-app" default="build" basedir=".">
    <import file="ant/java.xml"/>
    <import file="ant/test.xml"/>
    <import file="ant/package.xml"/>
</project>
~~~

Các file được import có thể cung cấp target, property và macro dùng trong build chính. Điều này giúp chia cấu hình theo trách nhiệm.

Ant cũng có phần tử include để đưa build file khác vào. Import và include có quy tắc đặt tên/override target khác nhau; khi dùng, nên xem tài liệu Ant tương ứng và đặt tên target có namespace rõ để tránh xung đột.

Không nên tách file quá nhỏ nếu điều đó làm người đọc phải mở nhiều nơi để hiểu một target đơn giản. Mục tiêu là giảm độ phức tạp, không chỉ tăng số lượng file.

## 18. antcall và ant task: gọi target hoặc build khác

Ant có task antcall để gọi một target trong cùng build file:

~~~xml
<target name="build-release">
    <antcall target="package">
        <param name="release.mode" value="true"/>
    </antcall>
</target>
~~~

antcall tạo một lần thực thi target với project context mới dựa trên build hiện tại. Nó có thể làm target và dependency được đánh giá lại trong lần gọi đó.

Vì vậy, không nên dùng antcall thay cho depends trong các quan hệ phụ thuộc thông thường. Nếu build-release chỉ cần package chạy trước, hãy dùng:

~~~xml
<target name="build-release" depends="package">
    <echo message="Release package is ready"/>
</target>
~~~

Task ant có thể gọi một build file khác:

~~~xml
<target name="build-docs">
    <ant antfile="docs/build.xml" target="build"/>
</target>
~~~

Cách này hữu ích khi dự án có sub-build độc lập. Tuy nhiên, cần truyền property và thư mục làm việc có chủ đích để tránh phụ thuộc ngầm vào trạng thái của build cha.

## 19. Fileset, pattern và resource

Fileset cho phép chọn file theo thư mục và pattern.

Ví dụ:

~~~xml
<fileset dir="src/main/resources">
    <include name="**/*.properties"/>
    <exclude name="**/local-dev.properties"/>
</fileset>
~~~

Các pattern thường gặp:

- **\*.java**: file Java ở thư mục được xét.
- **\*\*/\*.java**: file Java ở mọi thư mục con.
- **\*\*/\*.properties**: mọi file properties trong cây thư mục.
- **\*\*/\*Test.class**: các class test có hậu tố Test.

Dùng fileset trong copy:

~~~xml
<copy todir="build/classes">
    <fileset dir="src/main/resources">
        <include name="**/*"/>
    </fileset>
</copy>
~~~

Dùng fileset trong jar:

~~~xml
<jar destfile="build/app.jar">
    <fileset dir="build/classes"/>
</jar>
~~~

Fileset giúp build file mô tả rõ file nào được đưa vào output. Khi đóng gói, hãy kiểm tra include/exclude để tránh đưa file local, secret hoặc dữ liệu không cần thiết vào artifact.

## 20. Tổ chức build theo môi trường và biến thể

Ant có thể dùng property để chọn chế độ build:

~~~xml
<target name="build-dev" depends="compile">
    <echo message="Building development variant"/>
</target>

<target name="build-release" depends="compile,test">
    <echo message="Building release variant"/>
</target>
~~~

Có thể gọi trực tiếp:

~~~bash
ant build-dev
ant build-release
~~~

Một cách khác là dùng property và điều kiện target:

~~~xml
<target name="package" depends="compile" if="release.enabled">
    <jar destfile="build/app-release.jar" basedir="build/classes"/>
</target>
~~~

Chạy:

~~~bash
ant -Drelease.enabled=true package
~~~

Ant không có profile tích hợp giống Maven theo cùng mô hình. Có thể mô phỏng các biến thể bằng property, target có điều kiện, property file hoặc build file riêng.

Hãy giữ tên target thể hiện mục tiêu. Ví dụ build-dev và build-release dễ hiểu hơn một target package có nhiều nhánh điều kiện lồng nhau.

## 21. Kiểm soát lỗi và mã thoát

Task có thể báo lỗi khi thao tác thất bại. Ant thường dừng build khi task thất bại, trừ khi cấu hình task hoặc target cho phép tiếp tục.

Ví dụ task java:

~~~xml
<java classname="com.example.app.Main"
      fork="true"
      failonerror="true">
    <classpath refid="runtime.classpath"/>
</java>
~~~

failonerror="true" khiến Ant đánh dấu lỗi nếu chương trình Java trả mã khác 0.

Khi Ant build thất bại, tiến trình Ant trả mã thoát khác 0 cho shell hoặc CI. Vì vậy, CI có thể dùng mã thoát để quyết định bước tiếp theo.

Không nên cấu hình bỏ qua lỗi hoặc failonerror sai mục đích để che lỗi. Nếu một bước là bắt buộc cho release, build phải thất bại khi bước đó không hoàn thành.

## 22. Logging và chẩn đoán build Ant

Ant cung cấp các mức log và tùy chọn chẩn đoán.

Chạy với mức verbose:

~~~bash
ant -verbose build
~~~

Chạy debug:

~~~bash
ant -debug build
~~~

Xem thông tin chẩn đoán môi trường Ant:

~~~bash
ant -diagnostics
~~~

Một số tùy chọn thường dùng:

| Tùy chọn | Mục đích |
|---|---|
| **-quiet** | Giảm output |
| **-verbose** | Hiển thị nhiều thông tin thực thi |
| **-debug** | Log rất chi tiết |
| **-projecthelp** hoặc **-p** | Liệt kê target có mô tả |
| **-diagnostics** | In thông tin môi trường và cấu hình Ant |
| **-f file** | Dùng build file được chỉ định |
| **-Dname=value** | Đặt property từ command line |
| **-keep-going** | Tiếp tục các target độc lập khi có lỗi, trong giới hạn dependency |

Khi điều tra lỗi, bắt đầu bằng -verbose nếu log thường không đủ. Dùng -debug khi cần xem sâu hơn, vì output có thể rất lớn.

### Tìm lỗi theo thứ tự

1. Xác định target và task cuối cùng được thực hiện.
2. Đọc thông báo lỗi cụ thể từ task.
3. Kiểm tra property, đường dẫn và classpath được truyền vào.
4. Kiểm tra dependency target có chạy trước không.
5. Kiểm tra phiên bản JDK, Ant và task library.
6. Tái hiện target nhỏ nhất thay vì chạy toàn bộ build.
7. Chạy lại với verbose hoặc debug khi cần.

## 23. Tính incremental của task Ant

Ant có thể tránh một số công việc lặp lại tùy task và cách khai báo input/output. Ví dụ javac thường chỉ biên dịch source cần cập nhật dựa trên timestamp của source và class tương ứng.

Tuy nhiên, Ant không có task graph và input snapshot/cache model tổng quát giống Gradle. Người viết build file cần hiểu hành vi incremental của từng task và tránh giả định mọi task đều tự phát hiện mọi loại thay đổi.

Ví dụ javac:

~~~xml
<javac
    srcdir="src/main/java"
    destdir="build/classes"
    includeantruntime="false"
    debug="true"/>
~~~

Task javac có thể bỏ qua class không cần biên dịch lại theo kiểm tra source/class. Nhưng nếu một dependency JAR thay đổi mà task không nhận diện đúng ảnh hưởng hoặc output cũ còn tồn tại, cần kiểm tra classpath, timestamp và cách task được cấu hình.

Một số cách giúp build dễ tái lập:

- Khai báo rõ source directory và destination.
- Dùng clean khi cần tạo output từ trạng thái sạch.
- Đảm bảo task copy/delete xử lý đúng file bị xóa.
- Không để nhiều target ghi vào cùng output directory theo các quy tắc mâu thuẫn.
- Tách generated source và source gốc.
- Kiểm tra artifact sau khi package.

## 24. Ant và lựa chọn công cụ build

Ant phù hợp với một số tình huống:

- Dự án Java cũ đã có build.xml ổn định.
- Nhóm cần điều khiển trực tiếp thứ tự task.
- Quy trình build có nhiều thao tác file hoặc công cụ ngoài.
- Hệ thống build được tùy biến mạnh theo quy trình riêng.
- Cần tích hợp với script và tool hiện có.

Một số khác biệt tổng quát:

| Tiêu chí | Ant | Maven | Gradle |
|---|---|---|---|
| Cấu hình chính | XML build file | XML POM | Groovy/Kotlin DSL |
| Cách tổ chức | Target và task tường minh | Lifecycle và plugin conventions | Task graph và plugin model |
| Dependency management | Có thể cấu hình qua path/task; thường cần tổ chức thêm | Tích hợp dependency model | Tích hợp dependency configurations/variants |
| Quy trình | Người viết mô tả target và thứ tự | Theo lifecycle chuẩn và plugin | Task graph linh hoạt, có thể cấu hình |
| Reuse | Macro, import, taskdef | Plugin và parent POM | Plugin, convention plugin, build logic |
| Trường hợp thường gặp | Legacy hoặc workflow tùy chỉnh | Dự án theo convention Maven | Build hiện đại cần tùy biến và tối ưu |

Ant không phải lựa chọn lỗi thời trong mọi trường hợp. Nếu một hệ thống đã có build file rõ ràng, ổn định và đáp ứng nhu cầu, tiếp tục dùng Ant có thể hợp lý. Nếu dự án cần dependency management, multi-module conventions và incremental/cache capabilities phong phú, cần cân nhắc Maven hoặc Gradle theo yêu cầu.

## 25. Best practices khi tổ chức Ant build

### Đặt tên target theo hành động và mục tiêu

Tên như init, clean, compile, test, jar, dist dễ hiểu và có tính quy ước. Tránh tên chung như step1 hoặc taskA.

### Mỗi target nên có trách nhiệm rõ

Target compile chỉ nên tập trung biên dịch. Target test tập trung chạy kiểm thử. Target dist tạo cấu trúc phân phối. Target build kết hợp các bước cần thiết.

### Khai báo dependency tường minh

Dùng depends để thể hiện quan hệ bắt buộc. Không dựa vào việc người dùng tình cờ gọi target theo một thứ tự đúng.

### Đặt description cho target công khai

Ví dụ:

~~~xml
<target name="test"
        depends="compile-tests"
        description="Runs unit tests">
    ...
</target>
~~~

Điều này giúp ant -p hiển thị hướng dẫn hữu ích.

### Tách property khỏi logic

Đưa thư mục, version và cấu hình môi trường thành property. Dùng property file cho cấu hình không nhạy cảm và command line cho giá trị cần thay đổi theo lần chạy.

### Dùng path id cho classpath dùng chung

Không lặp lại cùng một danh sách JAR ở nhiều target. Đặt path id rõ như compile.classpath, test.classpath và runtime.classpath.

### Tránh antcall nếu depends đủ dùng

depends thể hiện dependency trực tiếp và dễ đọc hơn. antcall phù hợp với một số trường hợp gọi lại target có tham số, nhưng có thể làm build khó theo dõi vì tạo project context mới.

### Giữ output trong build directory

Clean có thể xóa build directory mà không ảnh hưởng source hoặc cấu hình. Không lưu dữ liệu quan trọng trong đó.

### Kiểm tra release artifact

Chạy test, kiểm tra manifest, classpath, resource và cấu trúc distribution trước khi phát hành.

## 26. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Target không chạy khi gọi ant | Target không phải default, không được gọi trực tiếp hoặc không thuộc dependency graph | Kiểm tra default và depends |
| Target chạy trước bước chuẩn bị | Thiếu depends hoặc thứ tự task trong target sai | Khai báo prerequisite rõ ràng |
| Circular dependency | Các target phụ thuộc vòng | Thiết kế lại đồ thị theo hướng một chiều |
| Property không nhận giá trị mới | Property đã được đặt trước và không ghi đè | Kiểm tra thứ tự nạp file và dùng -D nếu cần override |
| Target if/unless chạy khác mong đợi | Thuộc tính điều kiện kiểm tra sự tồn tại, không kiểm tra chuỗi true/false | Chỉ đặt property khi điều kiện thực sự đúng |
| Dependency vẫn chạy dù target bị skip | Target dependency được thực hiện trước khi xét if/unless | Đặt điều kiện ở target prerequisite phù hợp |
| javac không tìm thấy class | Compile classpath thiếu JAR hoặc thư mục output | Kiểm tra path và refid |
| JAR thiếu resource | Fileset include sai hoặc resource chưa được copy | Kiểm tra pattern và target chuẩn bị resource |
| Test task không tìm thấy test | JUnit library, Ant JUnit integration hoặc pattern class sai | Kiểm tra classpath và test report |
| Clean xóa nhầm dữ liệu | Source hoặc file quan trọng nằm trong build directory | Chỉ đặt generated output trong thư mục build |
| antcall chạy lặp target | antcall tạo project context mới và gọi lại target | Dùng depends cho dependency thông thường |
| CI báo thành công dù ứng dụng thất bại | Task java không bật failonerror hoặc script nuốt exit code | Bật failonerror và giữ mã thoát chính xác |

## 27. Quy trình thiết kế build Ant từ đầu

Có thể xây dựng build file theo trình tự:

1. Xác định source, resource, test, dependency và output directory.
2. Đặt project name, basedir và default target.
3. Khai báo property cho đường dẫn, version và Java release.
4. Khai báo path cho compile, test và runtime classpath.
5. Tạo target init để chuẩn bị thư mục.
6. Tạo target clean để xóa output có thể tái tạo.
7. Tạo target compile phụ thuộc init.
8. Tạo target compile-tests phụ thuộc compile.
9. Tạo target test phụ thuộc compile-tests.
10. Tạo target jar phụ thuộc compile và đóng gói manifest/resource.
11. Tạo target dist để gom JAR và runtime dependency.
12. Tạo target build tổng hợp các bước bắt buộc.
13. Thêm description cho các target người dùng gọi trực tiếp.
14. Chạy từng target riêng để kiểm tra phạm vi.
15. Chạy clean build để xác minh toàn bộ chuỗi.
16. Chạy trên CI và giữ mã thoát của Ant để pipeline phản ánh đúng kết quả.

Ví dụ lệnh:

~~~bash
# Xem các target công khai
ant -p

# Chạy riêng biên dịch
ant compile

# Chạy kiểm thử
ant test

# Tạo distribution
ant dist

# Xóa output và build lại
ant clean build

# Chạy build với version cụ thể
ant -Dbuild.version=2.0.0 clean build

# Chẩn đoán chi tiết
ant -verbose build
~~~

## 28. Những nguyên tắc cần nhớ

- Ant dùng XML để mô tả **project**, **target** và **task**.
- Project là phần tử gốc; target đại diện cho mục tiêu; task thực hiện thao tác cụ thể.
- Task trong một target chạy theo thứ tự khai báo.
- depends tạo quan hệ prerequisite giữa target; target dependency dùng chung chỉ chạy một lần trong cùng invocation.
- Target không thuộc graph sẽ không tự chạy.
- Target dependency phải tránh chu trình để Ant xác định được thứ tự.
- default xác định target chạy khi gọi ant mà không nêu tên target.
- Property giúp cấu hình đường dẫn và version; property thông thường được đặt một lần.
- -Dname=value truyền property từ command line và có ưu tiên đối với property trong build file.
- if/unless cơ bản kiểm tra property đã được đặt hay chưa; dependency vẫn chạy trước khi điều kiện của target được xét.
- path và fileset giúp tổ chức classpath, resource và tập hợp file.
- Macrodef và import giúp tái sử dụng build logic.
- depends phù hợp hơn antcall cho quan hệ phụ thuộc thông thường.
- clean nên chỉ xóa generated output.
- Task chạy chương trình con cần failonerror phù hợp để lỗi truyền về build và CI.
- Ant hỗ trợ một số incremental behavior ở từng task, nhưng không có mô hình task cache tổng quát như Gradle.
- Build file tốt có target rõ trách nhiệm, dependency tường minh, property tập trung và output dễ tái tạo.

Ant tổ chức quy trình build bằng các target có tên và quan hệ phụ thuộc được khai báo trực tiếp. Khi mỗi target thực hiện một trách nhiệm nhỏ, depends thể hiện thứ tự prerequisite và property/path quản lý cấu hình, build file trở thành bản mô tả rõ ràng về cách dự án được chuẩn bị, biên dịch, kiểm thử và đóng gói. Cấu trúc tường minh này giúp duy trì các quy trình build tùy chỉnh, đặc biệt trong dự án Java hiện hữu cần tích hợp nhiều công cụ và thao tác riêng.
