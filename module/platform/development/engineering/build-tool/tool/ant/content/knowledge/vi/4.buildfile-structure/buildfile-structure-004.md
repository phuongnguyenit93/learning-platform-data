# Target mặc định và thời điểm chạy các task ở cấp project

Trong Apache Ant, `default` của thẻ `<project>` chỉ định target mặc định: target Ant sẽ chạy khi người dùng gọi build mà không nêu tên target. Bên cạnh các task nằm bên trong target, `build.xml` còn có thể khai báo task trực tiếp dưới `<project>`. Những task này được gọi là **top-level tasks** (task ở cấp project). Ant thực hiện chúng trước khi bắt đầu chạy bất kỳ target nào.

Hai cơ chế này giải quyết hai vấn đề khác nhau. Default target chọn điểm bắt đầu của luồng build; top-level tasks thực hiện công việc khởi tạo ở cấp project trước luồng đó. Muốn hiểu một lệnh Ant sẽ chạy những gì, cần xem cả target được chọn, dependency của target và các task đặt ngoài target.

## 1. Target mặc định là gì?

Một Ant project thường khai báo target mặc định bằng thuộc tính `default` của phần tử `<project>`:

~~~xml
<project name="sample-app" default="dist" basedir=".">

    <target name="init">
        <mkdir dir="build/classes"/>
    </target>

    <target name="compile" depends="init">
        <!-- Compile source code -->
    </target>

    <target name="dist" depends="compile">
        <!-- Create the distributable artifact -->
    </target>

</project>
~~~

Trong ví dụ này, `dist` là default target. Khi chạy lệnh:

~~~bash
ant
~~~

Ant chọn target `dist`. Trước khi thực hiện nội dung của `dist`, Ant thực hiện các target mà `dist` phụ thuộc: `compile`, rồi `init` theo dependency graph. Như vậy, default target là điểm bắt đầu của build khi dòng lệnh không yêu cầu một target cụ thể.

Tên target mặc định không bắt buộc phải là `dist`, `build` hay `main`. Nó có thể là bất kỳ target đã khai báo nào, kể cả target `help` chỉ hiển thị hướng dẫn. Thuộc tính `default` là tên target, không phải một lệnh shell hay một task.

### 1.1. Default target chỉ được dùng khi không chỉ định target

Nếu người dùng gọi Ant kèm tên target, Ant thực hiện target được yêu cầu và các dependency của nó. Default target không tự động chạy thêm.

Ví dụ với project có `default="dist"`:

~~~bash
# Chạy target dist vì không chỉ định target
ant

# Chỉ chạy target compile cùng các dependency của nó
ant compile

# Chạy clean rồi dist theo thứ tự được yêu cầu trên command line
ant clean dist
~~~

Khi gọi `ant compile`, Ant không chạy `dist` chỉ vì `dist` là target mặc định. Khi gọi `ant clean dist`, Ant xử lý các target được yêu cầu theo thứ tự trên command line; dependency của mỗi target được thực hiện trước target đó. Một target đã được thực hiện trong cùng lượt chạy project sẽ không bị thực hiện lặp lại chỉ vì target khác cũng phụ thuộc vào nó.

Nếu không khai báo `default`, người chạy nên chỉ định target rõ ràng thay vì trông chờ Ant tự chọn target đầu tiên trong file. Ví dụ:

~~~bash
ant -f build.xml compile
~~~

### 1.2. Default target không phải target đầu tiên trong file

Ant không dùng vị trí đầu tiên của `<target>` để thay thế ý nghĩa của thuộc tính `default`. Target mặc định được xác định bởi giá trị `default` trên `<project>`.

~~~xml
<project name="sample-app" default="release">

    <target name="help">
        <echo message="Use ant compile, ant test or ant release"/>
    </target>

    <target name="clean">
        <delete dir="build"/>
    </target>

    <target name="compile" depends="clean">
        <echo message="Compile application"/>
    </target>

    <target name="release" depends="compile">
        <echo message="Prepare release"/>
    </target>

</project>
~~~

Ở đây `help` được khai báo trước, nhưng lệnh `ant` vẫn chọn `release`. Muốn xem hướng dẫn, người dùng phải gọi `ant help`. Thứ tự khai báo target trong XML không thay thế cấu hình default.

### 1.3. Default target và dependency là hai cấp lựa chọn khác nhau

`default` chọn target gốc khi không có target trên command line. `depends` xác định các target phải được chạy trước target đó.

~~~xml
<project name="sample-app" default="package">

    <target name="init">
        <mkdir dir="build/classes"/>
    </target>

    <target name="compile" depends="init">
        <echo message="Compile source"/>
    </target>

    <target name="test" depends="compile">
        <echo message="Run tests"/>
    </target>

    <target name="package" depends="test">
        <echo message="Create JAR"/>
    </target>

</project>
~~~

Lệnh `ant` chọn `package`, rồi đi ngược qua dependency để thực hiện `init`, `compile`, `test` và cuối cùng là `package`. Lệnh `ant compile` chỉ cần `init` và `compile`. Không có target nào tự chạy chỉ vì nó xuất hiện trong file.

## 2. Task ở cấp project là gì?

Một task ở cấp project là task được khai báo trực tiếp bên trong `<project>`, không nằm trong phần thân của `<target>` nào.

~~~xml
<project name="sample-app" default="compile">

    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <echo message="Preparing Ant project"/>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <echo message="Compile application"/>
    </target>

</project>
~~~

Trong ví dụ trên:

- Hai task `<property>` được khai báo ở cấp project.
- Task `<echo>` đầu tiên cũng ở cấp project.
- Các task `<mkdir>` và `<echo>` bên trong target `compile` chỉ chạy khi target `compile` được thực hiện.

Task ở cấp project thường được dùng để nạp property, khai báo task mở rộng, chuẩn bị cấu hình chung hoặc in thông tin khởi tạo. Chúng không thuộc dependency graph của target và không cần target khác phụ thuộc vào chúng.

Một số cấu hình thường đặt ở cấp project gồm:

- `<property>` để nạp file cấu hình, lấy biến môi trường hoặc đặt giá trị mặc định.
- `<taskdef>` và `<typedef>` để đăng ký task hoặc data type mở rộng.
- `<echo>` để in thông tin khởi tạo hoặc thông báo về cấu hình build.
- Các task cấu hình khác cần có sẵn trước khi target được thực hiện.

Các data type như `<path>` cũng có thể được khai báo ở cấp project với `id` để target tham chiếu. Cần phân biệt việc khai báo một data type/reference với task thực thi công việc: ví dụ `<path>` mô tả một tập đường dẫn, còn `<javac>` thực hiện biên dịch.

## 3. Task cấp project chạy vào thời điểm nào?

Ant thực hiện các top-level tasks trước khi bắt đầu thực hiện bất kỳ target nào trong project. Các top-level tasks được chạy theo thứ tự chúng xuất hiện ở cấp project trong build file.

Có thể hình dung thứ tự tổng quát như sau:

~~~text
Gọi lệnh ant
     |
     v
Khởi động JVM chạy Ant
     |
     v
Đọc và cấu hình build project
     |
     v
Thực hiện top-level tasks
(theo thứ tự khai báo ở cấp project)
     |
     v
Chọn target cần chạy
(default nếu command line không nêu target)
     |
     v
Thực hiện các dependency của target
     |
     v
Thực hiện task trong target
     |
     v
Kết thúc lượt chạy project
~~~

Ví dụ:

~~~xml
<project name="sample-app" default="package">

    <echo message="A. Top-level task"/>
    <property name="build.dir" location="build"/>

    <target name="init">
        <echo message="B. init target"/>
    </target>

    <target name="compile" depends="init">
        <echo message="C. compile target"/>
    </target>

    <target name="package" depends="compile">
        <echo message="D. package target"/>
    </target>

</project>
~~~

Khi chạy `ant`, thứ tự thông báo là:

~~~text
A. Top-level task
B. init target
C. compile target
D. package target
~~~

Nếu chạy `ant compile`, thứ tự là:

~~~text
A. Top-level task
B. init target
C. compile target
~~~

Task cấp project vẫn chạy dù target mặc định `package` không được chọn. Target `package` không chạy trong lượt `ant compile`, nhưng top-level tasks vẫn đã được thực hiện trước khi Ant chạy `compile`.

Thứ tự XML giữa các target không có nghĩa là Ant thực thi lần lượt tất cả target từ trên xuống dưới. Chỉ target được yêu cầu, default target và các dependency của chúng mới tham gia lượt chạy. Quy tắc thứ tự xuất hiện ở cấp project áp dụng cho các top-level tasks với nhau.

## 4. Top-level tasks không thuộc dependency graph

Một điểm quan trọng là task ở cấp project không phải target. Vì vậy, chúng không có thuộc tính `depends` để yêu cầu một target khác chạy trước, và target cũng không thể tham chiếu trực tiếp tới chúng như một dependency.

Ví dụ sau không hợp lệ về ý tưởng cấu trúc:

~~~xml
<project name="sample-app" default="compile">

    <target name="compile" depends="prepare-config">
        <javac srcdir="src" destdir="build/classes"/>
    </target>

    <property name="build.dir" location="build"/>

</project>
~~~

`depends` chỉ nhận tên target. `prepare-config` phải là một target thực sự nếu được liệt kê trong dependency. Một task `<property>` ở cấp project không tạo ra target có tên tương ứng.

Nếu một bước cần chạy theo dependency, hãy đặt nó trong target:

~~~xml
<project name="sample-app" default="compile">

    <target name="prepare-config">
        <echo message="Prepare configuration"/>
        <mkdir dir="build"/>
    </target>

    <target name="compile" depends="prepare-config">
        <javac srcdir="src/main/java"
               destdir="build/classes"
               includeantruntime="false"/>
    </target>

</project>
~~~

Lúc này `prepare-config` chỉ chạy khi nó nằm trong luồng dependency của target được gọi. Nếu người dùng gọi một target không phụ thuộc `prepare-config`, bước chuẩn bị đó sẽ không chạy.

Ngược lại, nếu công việc là cấu hình chung bắt buộc trước mọi target, task cấp project có thể phù hợp. Ví dụ, nạp property file hoặc đăng ký task mở rộng thường phải sẵn sàng trước khi target bắt đầu.

## 5. Top-level tasks vẫn chạy khi gọi target tường minh

Một nhầm lẫn thường gặp là nghĩ rằng chỉ task nằm trong target được chọn mới chạy. Thực tế, top-level tasks đã được thực hiện trước khi Ant bắt đầu target được yêu cầu.

~~~xml
<project name="sample-app" default="release">

    <echo message="Build configuration is loading"/>
    <property file="build.properties"/>

    <target name="help">
        <echo message="Available targets: compile, test, release"/>
    </target>

    <target name="compile">
        <echo message="Compile source"/>
    </target>

    <target name="release" depends="compile">
        <echo message="Prepare release"/>
    </target>

</project>
~~~

Khi gọi `ant help`, Ant vẫn thực hiện `echo` và nạp `build.properties` ở cấp project, sau đó mới chạy target `help`. Khi gọi `ant compile`, hai task cấp project đó vẫn chạy trước target `compile`.

Điều này có hệ quả thực tế: không đặt thao tác nặng hoặc có side effect vào cấp project nếu chỉ một số target cần nó. Ví dụ, không nên tải dependency lớn, xóa thư mục, gọi dịch vụ từ xa hoặc triển khai ứng dụng bằng top-level task chỉ vì muốn cấu hình một target. Những thao tác đó có thể xảy ra cả khi người dùng chỉ gọi target `help`, `clean` hoặc một target không liên quan.

Nếu thao tác chỉ cần cho một luồng cụ thể, hãy đặt nó trong target chuyên trách và nối bằng `depends`. Cách đó làm cho thời điểm thực thi rõ ràng và dễ kiểm soát hơn.

## 6. Thứ tự giữa các top-level tasks và ảnh hưởng của property

Các top-level tasks chạy theo thứ tự xuất hiện ở cấp project. Thứ tự này đặc biệt quan trọng với task `<property>` vì property của Ant có tính chất chỉ thiết lập giá trị một lần: khi một property đã được đặt, một lần `<property>` sau đó với cùng tên thường không ghi đè giá trị cũ.

Ví dụ:

~~~xml
<project name="sample-app" default="show-version">

    <property file="build.properties"/>
    <property name="release.version" value="0.1.0-SNAPSHOT"/>

    <target name="show-version">
        <echo message="Version: ${release.version}"/>
    </target>

</project>
~~~

Nếu `build.properties` chứa:

~~~properties
release.version=2.3.0
~~~

thì property file được nạp trước và giá trị `2.3.0` được giữ. Giá trị mặc định `0.1.0-SNAPSHOT` chỉ được sử dụng nếu file không cung cấp property đó.

Nếu đảo thứ tự:

~~~xml
<property name="release.version" value="0.1.0-SNAPSHOT"/>
<property file="build.properties"/>
~~~

thì giá trị mặc định đã được đặt trước; property file không thay thế giá trị đó. Vì vậy, khi thiết kế cấu hình, hãy nạp nguồn có độ ưu tiên cao trước và đặt giá trị fallback sau.

Property truyền từ command line, ví dụ `-Drelease.version=2.4.0`, là user property và có độ ưu tiên cao hơn các giá trị được đặt bằng task `<property>` thông thường. Có thể chạy:

~~~bash
ant -Drelease.version=2.4.0 show-version
~~~

Khi đó target dùng giá trị `2.4.0`, kể cả khi property file hoặc giá trị mặc định khai báo một phiên bản khác.

Thứ tự cấu hình thường gặp:

~~~text
Property truyền từ command line (-D)
              |
              v
Property lấy từ file cấu hình
              |
              v
Giá trị mặc định trong build.xml
              |
              v
Target sử dụng property
~~~

Đây là thứ tự ưu tiên nên chủ động thiết kế; hãy nhớ rằng cơ chế property của Ant là first value wins đối với các lần thiết lập thông thường, trong khi user properties truyền từ command line có ưu tiên riêng.

## 7. Dùng top-level task để nạp cấu hình và đăng ký task mở rộng

Một build file có thể dùng top-level tasks để chuẩn bị những khả năng mà nhiều target cùng cần.

Ví dụ nạp biến môi trường và property file:

~~~xml
<project name="sample-app" default="compile">

    <property environment="env"/>
    <property file="build.properties"/>
    <property name="build.dir" location="build"/>

    <target name="show-environment">
        <echo message="JAVA_HOME=${env.JAVA_HOME}"/>
        <echo message="Build directory=${build.dir}"/>
    </target>

    <target name="compile">
        <mkdir dir="${build.dir}/classes"/>
        <javac srcdir="src/main/java"
               destdir="${build.dir}/classes"
               includeantruntime="false"/>
    </target>

</project>
~~~

Task `<property environment="env"/>` đưa các biến môi trường vào namespace `env`, cho phép tham chiếu như `${env.JAVA_HOME}`. Property file có thể cung cấp cấu hình riêng của dự án. Các target sử dụng cùng giá trị đã được chuẩn bị.

Task `<taskdef>` cũng thường được khai báo ở cấp project để đăng ký task mở rộng trước khi target sử dụng nó:

~~~xml
<project name="sample-app" default="verify">

    <path id="custom.tasks.classpath">
        <fileset dir="tools">
            <include name="*.jar"/>
        </fileset>
    </path>

    <taskdef resource="com/example/ant/tasks.properties"
             classpathref="custom.tasks.classpath"/>

    <target name="verify">
        <!-- Gọi custom task đã được đăng ký ở cấp project. -->
        <checkconfiguration/>
    </target>

</project>
~~~

Ví dụ minh họa cách đăng ký task theo resource; tên resource, JAR và tên task phải khớp với thư viện mở rộng thực tế. Nếu target dùng task trước khi task được đăng ký, Ant có thể báo không nhận diện task. Đặt cấu hình đăng ký ở cấp project giúp task sẵn sàng trước khi target được thực thi.

Không phải mọi khai báo đều cần là top-level task. Chỉ đưa cấu hình lên cấp project khi nó thực sự là phần chuẩn bị chung của project. Cấu hình chỉ phục vụ một target nên nằm gần target đó để người đọc thấy được phạm vi sử dụng.

## 8. Điều kiện của target không điều khiển top-level tasks

Target có thể dùng `if` hoặc `unless` để quyết định task bên trong target có được thực hiện hay không. Các thuộc tính này kiểm tra sự tồn tại của property. Chúng không áp dụng ngược lên top-level tasks.

Ví dụ:

~~~xml
<project name="sample-app" default="build">

    <condition property="is.windows">
        <os family="windows"/>
    </condition>

    <echo message="Project configuration initialized"/>

    <target name="windows-setup" if="is.windows">
        <echo message="Run Windows-specific setup"/>
    </target>

    <target name="build" depends="windows-setup">
        <echo message="Build application"/>
    </target>

</project>
~~~

Task `<condition>` và `<echo>` ở cấp project vẫn được thực hiện trước khi target bắt đầu. Nếu property `is.windows` được đặt, các task trong `windows-setup` mới được thực hiện. Nếu property không được đặt, phần thân của target `windows-setup` bị bỏ qua.

Cần lưu ý rằng điều kiện `if`/`unless` của target không biến target thành một dependency tùy chọn: các target được khai báo trong `depends` vẫn được xét và thực hiện theo dependency graph; điều kiện kiểm soát phần task bên trong target. Vì vậy, nếu cần bỏ qua cả một nhánh công việc, hãy thiết kế dependency và target điều kiện cẩn thận, thay vì nghĩ rằng `if` sẽ ngăn toàn bộ target đó xuất hiện trong luồng.

## 9. Top-level tasks và target khi có nhiều target được gọi

Một lần gọi Ant có thể chỉ định nhiều target:

~~~bash
ant clean compile test
~~~

Trong một project invocation, các top-level tasks được thực hiện trước. Sau đó Ant xử lý các target theo thứ tự được yêu cầu trên command line, đồng thời thực hiện dependency trước target cần chạy. Target đã chạy rồi sẽ không bị chạy lại trong cùng invocation chỉ vì target tiếp theo cũng phụ thuộc vào nó.

Ví dụ:

~~~xml
<project name="sample-app" default="release">

    <echo message="Project-level initialization"/>

    <target name="clean">
        <echo message="Clean"/>
    </target>

    <target name="compile">
        <echo message="Compile"/>
    </target>

    <target name="test" depends="compile">
        <echo message="Test"/>
    </target>

    <target name="release" depends="test">
        <echo message="Release"/>
    </target>

</project>
~~~

Lệnh `ant clean release` có thứ tự khái quát:

~~~text
Project-level initialization
clean
compile
 test
release
~~~

`compile` và `test` chạy vì dependency của `release`; `clean` chạy trước vì được nêu trước trên command line. Task cấp project chỉ chạy một lần trước các target, không lặp lại trước từng target được liệt kê.

Nếu một target gọi build khác bằng task `<ant>` hoặc `<subant>`, build con có project context riêng. Build con sẽ đọc cấu hình project của nó, thực hiện top-level tasks của nó và chọn target theo target được yêu cầu hoặc default của build con. Không nên nhầm top-level tasks của build cha với top-level tasks của build con.

## 10. Khi nào nên đặt task ở cấp project, khi nào nên đặt trong target?

Hãy chọn vị trí theo thời điểm và phạm vi cần thực hiện.

| Nhu cầu | Vị trí phù hợp | Lý do |
|---|---|---|
| Nạp property file dùng chung | Cấp project | Các target cần cấu hình trước khi bắt đầu |
| Đăng ký custom Ant task dùng ở nhiều target | Cấp project | Task cần được nhận diện trước khi target sử dụng |
| In thông tin cấu hình chung | Cấp project | Muốn thông báo xuất hiện ở mọi lần chạy project |
| Tạo thư mục build chỉ khi compile | Target `init` hoặc `compile` | Chỉ cần khi luồng compile được gọi |
| Xóa thư mục đầu ra | Target `clean` | Không nên xóa dữ liệu khi người dùng chỉ gọi `help` hoặc target khác |
| Biên dịch mã nguồn | Target `compile` | Là một bước nghiệp vụ build có thể được chọn và phụ thuộc rõ ràng |
| Chạy test | Target `test` | Chỉ chạy khi luồng test/verify yêu cầu |
| Upload hoặc deploy | Target riêng có điều kiện | Là hành động có side effect, cần được gọi tường minh hoặc qua pipeline đã kiểm soát |

Một quy tắc dễ áp dụng: nếu task phải chạy trước mọi target để project có thể được cấu hình đúng, đặt ở cấp project. Nếu task chỉ cần cho một luồng build nhất định, đặt trong target và dùng `depends` để thể hiện quan hệ.

Không nên dùng top-level task như một nơi gom mọi lệnh build. Làm như vậy khiến lệnh `ant help` hoặc `ant clean` cũng có thể kích hoạt các bước không liên quan, khiến build khó dự đoán và khó kiểm soát side effect.

## 11. Cách lần theo thứ tự chạy khi đọc build.xml

Khi cần biết một lệnh cụ thể sẽ thực hiện những gì, hãy phân tích theo trình tự:

1. Xem thẻ `<project>` để tìm `default`, `name` và `basedir`.
2. Liệt kê các task khai báo trực tiếp dưới `<project>`; ghi nhận thứ tự xuất hiện của chúng.
3. Xác định lệnh gọi Ant có truyền target trên command line hay không. Nếu không, target mặc định được chọn.
4. Với từng target được yêu cầu, lần theo `depends` để xác định các target phụ thuộc và thứ tự thực hiện.
5. Kiểm tra `if`/`unless` của target để biết phần thân target có được thực hiện hay không; nhớ rằng dependency vẫn được xử lý.
6. Đọc các task bên trong target theo thứ tự khai báo.
7. Kiểm tra các task gọi build con như `<ant>` hoặc `<subant>` vì chúng mở một lượt cấu hình và thực thi project khác.

Có thể dùng lệnh sau để liệt kê target và mô tả:

~~~bash
ant -p
~~~

Để xem log chi tiết khi thực hiện target:

~~~bash
ant -verbose compile
~~~

`-p` hỗ trợ xem các target có trong build file; nó không thay thế việc đọc top-level tasks và dependency. `-verbose` giúp theo dõi quá trình chạy, nhưng cần đọc đúng phần log thuộc project và target đang điều tra.

## 12. Các lỗi thiết kế thường gặp

| Vấn đề | Hệ quả | Cách thiết kế lại |
|---|---|---|
| Nghĩ target đầu tiên là default | Lệnh `ant` chạy target ngoài dự kiến hoặc không chạy target mong muốn | Khai báo `default` rõ ràng trên `<project>` |
| Đặt việc xóa hoặc upload ở cấp project | Side effect xảy ra ngay cả khi gọi target không liên quan | Chuyển vào target `clean`, `publish` hoặc `deploy` riêng |
| Dùng task cấp project như dependency | `depends` không tìm thấy target tương ứng | Đặt bước cần điều phối trong một target có tên |
| Đặt property mặc định trước property file | Giá trị trong file không ghi đè được property đã đặt | Nạp file trước, khai báo fallback sau |
| Nghĩ `ant compile` sẽ bỏ qua top-level tasks | Cấu hình hoặc thông báo cấp project vẫn chạy | Đưa công việc chỉ dành cho compile vào target |
| Nghĩ `if` bỏ qua toàn bộ dependency | Các dependency vẫn có thể được thực hiện | Thiết kế graph và điều kiện ở từng target đúng mục đích |
| Build cha và build con dùng chung một lượt target | Khó hiểu thứ tự và trạng thái cấu hình | Theo dõi riêng project invocation của `<ant>`/`<subant>` |

## Kết luận

`default` trên `<project>` xác định target được chọn khi lệnh Ant không nêu target. Target này vẫn chạy theo dependency graph: các target phụ thuộc được thực hiện trước rồi mới tới task trong target. Task khai báo trực tiếp dưới `<project>` là top-level tasks; chúng được thực hiện theo thứ tự khai báo trước khi Ant bắt đầu bất kỳ target nào, kể cả khi người dùng gọi một target tường minh. Vì top-level tasks không thuộc dependency graph và không được điều khiển bởi `if`/`unless` của target, hãy dùng chúng cho cấu hình chung cần có từ đầu project; đặt compile, test, clean, publish và các thao tác chỉ thuộc một luồng cụ thể bên trong target tương ứng.