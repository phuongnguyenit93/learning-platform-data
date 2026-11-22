# Thiết lập classpath, sourcepath và includeAntRuntime

## Mục tiêu

Khi biên dịch Java bằng task `javac` của Apache Ant, compiler cần biết nơi tìm các lớp phụ thuộc và các tệp nguồn liên quan. Ant cung cấp ba cấu hình thường gặp:

- **classpath** chỉ định các lớp đã biên dịch và thư viện mà mã nguồn cần tham chiếu.
- **sourcepath** chỉ định nơi compiler có thể tìm thêm mã nguồn Java khi cần phân giải một kiểu chưa được cung cấp dưới dạng lớp đã biên dịch.
- **includeAntRuntime** quyết định có thêm các thư viện runtime của chính Ant vào classpath biên dịch hay không.

Ba cấu hình này có liên quan nhưng không thay thế cho nhau. Một buildfile có thể tìm thấy mã nguồn trong `srcdir` nhưng vẫn không biên dịch được vì thiếu thư viện trên classpath. Tương tự, có thể biên dịch thành công trên máy phát triển nhờ Ant runtime được thêm ngầm vào classpath, nhưng thất bại ở môi trường khác khi cấu hình hoặc phiên bản Ant thay đổi.

Bài này giải thích cách phân biệt từng đường dẫn, cách khai báo chúng bằng Path để tái sử dụng, và cách kiểm soát Ant runtime để build dễ tái lập.

## 1. Bối cảnh: task javac biên dịch từ đâu?

Task `javac` nhận các tệp nguồn, gọi Java compiler và ghi các tệp `.class` vào thư mục đích.

Ví dụ tối thiểu:

~~~xml
<project name="compile-demo" default="compile" basedir=".">
    <property name="src.dir" location="src"/>
    <property name="classes.dir" location="build/classes"/>

    <target name="prepare">
        <mkdir dir="${classes.dir}"/>
    </target>

    <target name="compile" depends="prepare">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"/>
    </target>
</project>
~~~

Trong ví dụ:

- `srcdir` là nơi Ant tìm các tệp nguồn cần biên dịch.
- `destdir` là nơi ghi các lớp đã biên dịch.
- `includeantruntime="false"` yêu cầu Ant không tự thêm thư viện runtime của Ant vào classpath của lần biên dịch.

Nếu mã nguồn chỉ dùng các lớp thuộc Java platform và các lớp khác trong cùng đợt biên dịch, cấu hình này có thể đủ. Khi mã nguồn phụ thuộc vào thư viện bên ngoài hoặc mã nguồn ở một vị trí khác, cần cấu hình thêm classpath hoặc sourcepath.

## 2. Classpath: nơi tìm lớp và thư viện phụ thuộc

### 2.1. Classpath chứa gì?

Classpath là danh sách các vị trí mà Java compiler tìm các lớp đã biên dịch và thư viện cần thiết để kiểm tra kiểu, phương thức và trường được tham chiếu từ mã nguồn.

Các phần tử phổ biến gồm:

- Thư mục chứa các tệp `.class` đã biên dịch.
- Tệp JAR chứa các lớp thư viện.
- Các thư mục đầu ra của module khác mà module hiện tại phụ thuộc.

Ví dụ, mã nguồn sử dụng một lớp trong `lib/logging-api.jar`. Compiler cần tìm được JAR đó trong classpath, nếu không sẽ báo lỗi như `package ... does not exist` hoặc `cannot find symbol`.

### 2.2. Khai báo classpath trực tiếp trong javac

Có thể khai báo thuộc tính `classpath`:

~~~xml
<javac srcdir="src"
       destdir="build/classes"
       classpath="lib/logging-api.jar"
       includeantruntime="false"/>
~~~

Khi có nhiều phần tử, thuộc tính classpath dùng chuỗi đường dẫn phân cách theo hệ điều hành. Dấu phân cách thường là dấu chấm phẩy trên Windows và dấu hai chấm trên Unix-like.

Không nên tự ghép chuỗi bằng dấu phân cách cố định nếu buildfile cần chạy trên nhiều hệ điều hành. Path của Ant xử lý việc phân cách theo nền tảng và dễ tái sử dụng hơn.

### 2.3. Khai báo bằng Path

Có thể định nghĩa một Path có ID rồi tham chiếu bằng `classpathref` hoặc nested element:

~~~xml
<path id="compile.classpath">
    <pathelement location="lib/logging-api.jar"/>
    <pathelement location="lib/json-core.jar"/>
    <pathelement location="build/shared-classes"/>
</path>

<javac srcdir="src"
       destdir="build/classes"
       classpathref="compile.classpath"
       includeantruntime="false"/>
~~~

Path cho phép kết hợp nhiều loại phần tử. Ví dụ, có thể dùng FileSet để lấy tất cả JAR trong một thư mục:

~~~xml
<path id="compile.classpath">
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
    <pathelement location="build/shared-classes"/>
</path>
~~~

Cách này tự động đưa các JAR phù hợp vào classpath mà không cần liệt kê từng tệp.

Cũng có thể viết nested element trong javac:

~~~xml
<javac srcdir="src"
       destdir="build/classes"
       includeantruntime="false">
    <classpath>
        <pathelement location="lib/logging-api.jar"/>
        <fileset dir="lib">
            <include name="*.jar"/>
        </fileset>
    </classpath>
</javac>
~~~

Dùng `classpathref` khi Path đã được khai báo ở nơi khác và cần chia sẻ giữa nhiều target. Dùng nested `classpath` khi danh sách phụ thuộc chỉ phục vụ một task và muốn giữ cấu hình tại chỗ.

### 2.4. Thứ tự phần tử trong classpath

Classpath là một danh sách có thứ tự. Khi có nhiều vị trí cùng chứa một lớp với cùng tên đầy đủ, vị trí xuất hiện trước có thể được compiler hoặc class loader ưu tiên tùy ngữ cảnh.

Ví dụ, nếu cả `lib/old-api.jar` và `lib/new-api.jar` cùng chứa một lớp có tên giống nhau, việc đưa cả hai vào classpath có thể làm kết quả phụ thuộc thứ tự. Tránh giữ nhiều phiên bản của cùng thư viện trong một classpath nếu không có chủ đích.

Hãy kiểm tra các JAR trùng hoặc thư mục lớp cũ khi gặp lỗi liên quan đến API không tương thích, phương thức không tồn tại hoặc kiểu được nạp từ một phiên bản khác dự kiến.

### 2.5. Classpath biên dịch khác classpath chạy ứng dụng

Classpath dùng khi biên dịch phải chứa các thư viện cần để compiler hiểu mã nguồn. Classpath khi chạy ứng dụng phải chứa các lớp cần thiết lúc JVM thực thi.

Hai danh sách thường có phần giao nhau nhưng không bắt buộc giống nhau:

- Một thư viện chỉ dùng trong quá trình biên dịch hoặc xử lý annotation có thể không cần trong runtime.
- Một thư viện được tải động khi chạy có thể không được mã nguồn tham chiếu trực tiếp.
- Các lớp đầu ra của module khác thường cần có trên classpath khi biên dịch module hiện tại.

Vì vậy, nên đặt tên rõ như `compile.classpath` và `runtime.classpath` thay vì dùng một Path chung cho mọi mục đích.

## 3. Sourcepath: nơi tìm thêm mã nguồn Java

### 3.1. Sourcepath khác srcdir như thế nào?

Hai thuộc tính này thường bị nhầm lẫn:

| Thành phần | Vai trò |
|---|---|
| `srcdir` | Các thư mục nguồn mà task javac quét để xác định các tệp cần biên dịch |
| `sourcepath` | Các thư mục mà Java compiler có thể tìm thêm tệp nguồn khi phân giải kiểu cần thiết |
| `classpath` | Các thư mục lớp và thư viện đã biên dịch mà compiler cần tham chiếu |

Ví dụ, project có cấu trúc:

~~~text
project/
├── src/
│   └── app/
│       └── Main.java
├── shared-src/
│   └── common/
│       └── TextUtil.java
├── lib/
│   └── external-api.jar
└── build/
~~~

Main.java sử dụng `common.TextUtil`. Nếu `TextUtil` chưa được biên dịch thành `.class`, compiler cần biết nơi tìm tệp nguồn `TextUtil.java`. Đó là vai trò của sourcepath.

Nếu `TextUtil` đã được biên dịch thành lớp trong một thư mục output, thư mục đó có thể được đưa vào classpath thay vì tìm lại mã nguồn.

### 3.2. Khai báo sourcepath

Task javac hỗ trợ thuộc tính `sourcepath` và tham chiếu Path tương ứng. Ví dụ:

~~~xml
<javac srcdir="src"
       destdir="build/classes"
       sourcepath="shared-src"
       includeantruntime="false"/>
~~~

Khi cần nhiều thư mục nguồn, có thể khai báo Path:

~~~xml
<path id="compile.sourcepath">
    <pathelement location="src"/>
    <pathelement location="shared-src"/>
    <pathelement location="build/generated/sources"/>
</path>

<javac srcdir="src"
       destdir="build/classes"
       sourcepathref="compile.sourcepath"
       includeantruntime="false"/>
~~~

Sourcepath có thể bao gồm thư mục nguồn chính, thư mục nguồn dùng chung hoặc mã nguồn được sinh tự động. Hãy đưa vào đúng những vị trí mà compiler cần tìm nguồn bổ sung.

### 3.3. Sourcepath không phải classpath

Không nên đưa mọi thư mục nguồn vào classpath chỉ vì compiler cần tìm một lớp. Classpath được thiết kế để tìm các lớp đã biên dịch và thư viện; sourcepath được dùng để tìm mã nguồn.

Giả sử project có:

- `shared-src/common/TextUtil.java`
- `build/shared-classes/common/TextUtil.class`

Nếu muốn compiler dùng lớp đã biên dịch, thêm `build/shared-classes` vào classpath. Nếu muốn compiler tìm và biên dịch nguồn khi cần, thêm `shared-src` vào sourcepath.

Chọn một cách theo quy trình build. Nếu cùng một lớp tồn tại ở cả sourcepath và classpath với phiên bản khác nhau, có thể xảy ra nhầm lẫn về phiên bản được dùng.

### 3.4. Sourcepath và biên dịch ngầm

Java compiler có thể tìm mã nguồn của kiểu phụ thuộc qua sourcepath và biên dịch nguồn đó khi cần, tùy tùy chọn và hành vi của compiler. Điều này có thể tiện trong dự án nhỏ, nhưng làm cho phạm vi biên dịch khó nhìn thấy hơn nếu build không quản lý nguồn rõ ràng.

Với build lớn, thường dễ dự đoán hơn khi liệt kê các thư mục nguồn cần biên dịch trong cấu hình Ant và quản lý các module phụ thuộc theo target riêng. Sourcepath khi đó phục vụ đúng mục đích tìm nguồn bổ sung, không trở thành một cách thay thế cho cấu trúc compile target.

### 3.5. Giá trị mặc định và khi nào nên khai báo rõ

Nếu không đặt sourcepath, task và compiler sử dụng cấu hình mặc định của chúng; trong nhiều cấu hình Ant, mặc định này gắn với các thư mục nguồn đã chỉ định bằng srcdir. Tuy nhiên, khi dự án có thư mục nguồn dùng chung hoặc generated source nằm ngoài srcdir, hãy khai báo sourcepath rõ ràng để tránh phụ thuộc vào mặc định.

## 4. includeAntRuntime: có đưa thư viện Ant vào classpath không?

### 4.1. Ý nghĩa thuộc tính

Task javac có thuộc tính `includeAntRuntime`. Thuộc tính này điều khiển việc các thư viện runtime của Ant có được thêm vào classpath dùng để biên dịch hay không.

Giá trị mặc định của thuộc tính này là `true`. Nghĩa là nếu không chỉ định, Ant có thể thêm các thư viện runtime của chính nó vào classpath biên dịch.

Ví dụ:

~~~xml
<javac srcdir="src"
       destdir="build/classes"
       includeantruntime="true"/>
~~~

Khi đó, mã nguồn có thể tham chiếu các lớp của Ant mà không cần khai báo chúng trực tiếp trong classpath.

### 4.2. Vì sao nên cân nhắc đặt false?

Với ứng dụng Java thông thường, mã nguồn thường chỉ nên phụ thuộc vào:

- Java platform hoặc JDK tương ứng.
- Các thư viện ứng dụng đã khai báo rõ trong classpath.
- Các module nội bộ mà build đã biên dịch trước.

Nếu để `includeAntRuntime="true"`, ứng dụng có thể vô tình biên dịch được nhờ một lớp nằm trong Ant runtime dù buildfile không khai báo dependency đó. Máy khác dùng phiên bản Ant khác có thể có thư viện hoặc phiên bản lớp khác, khiến kết quả biên dịch không nhất quán.

Vì vậy, với ứng dụng thông thường, thường nên dùng:

~~~xml
<javac srcdir="src"
       destdir="build/classes"
       classpathref="compile.classpath"
       includeantruntime="false"/>
~~~

Khi đặt false, các dependency cần thiết phải được khai báo rõ ràng trong classpath. Điều này giúp build minh bạch và dễ tái lập hơn.

### 4.3. Khi nào cần includeAntRuntime=true?

Một trường hợp hợp lý là khi đang biên dịch mã nguồn cho một custom Ant task hoặc một thành phần trực tiếp sử dụng API của Ant, ví dụ lớp kế thừa `org.apache.tools.ant.Task`.

~~~java
package example.ant;

import org.apache.tools.ant.Task;

public class HelloTask extends Task {
    @Override
    public void execute() {
        log("Hello from a custom Ant task");
    }
}
~~~

Mã nguồn này cần tìm lớp `org.apache.tools.ant.Task`. Có thể để Ant runtime được thêm vào classpath:

~~~xml
<javac srcdir="src"
       destdir="build/custom-ant-tasks"
       includeantruntime="true"/>
~~~

Hoặc tắt includeAntRuntime rồi khai báo API Ant một cách tường minh:

~~~xml
<path id="custom-task.classpath">
    <pathelement location="${ant.home}/lib/ant.jar"/>
</path>

<javac srcdir="src"
       destdir="build/custom-ant-tasks"
       classpathref="custom-task.classpath"
       includeantruntime="false"/>
~~~

Cách thứ hai giúp buildfile thể hiện rõ dependency trực tiếp của custom task. Tùy phiên bản Ant và API được dùng, custom task có thể cần thêm thư viện Ant khác; hãy khai báo đúng các thư viện mà mã nguồn thực sự tham chiếu.

### 4.4. Phân biệt includeAntRuntime và includeJavaRuntime

Hai thuộc tính có tên gần giống nhưng điều khiển hai nhóm thư viện khác nhau:

| Thuộc tính | Ý nghĩa |
|---|---|
| `includeAntRuntime` | Thêm hoặc không thêm các thư viện runtime của Ant vào classpath biên dịch |
| `includeJavaRuntime` | Có đưa các thư viện runtime của Java đang chạy vào classpath hay không |

`includeJavaRuntime` mặc định là false. Với Java compiler hiện đại, các lớp nền tảng được cung cấp theo cơ chế của JDK/toolchain, nên không nên bật thuộc tính này chỉ để “cho chắc”.

Nếu cần biên dịch cho một Java platform cụ thể, hãy cấu hình đúng JDK và các tùy chọn tương thích như source, target hoặc release theo phiên bản Ant và compiler đang dùng. Không dùng includeJavaRuntime để thay thế cấu hình toolchain.

## 5. Khai báo Path để quản lý classpath và sourcepath

### 5.1. Tách các Path theo mục đích

Một buildfile dễ bảo trì thường định nghĩa các Path có tên theo mục đích:

~~~xml
<project name="path-configuration" default="compile" basedir=".">
    <property name="src.dir" location="src/main/java"/>
    <property name="shared.src.dir" location="shared-src"/>
    <property name="classes.dir" location="build/classes"/>
    <property name="lib.dir" location="lib"/>

    <path id="compile.classpath">
        <fileset dir="${lib.dir}">
            <include name="*.jar"/>
        </fileset>
        <pathelement location="build/shared-classes"/>
    </path>

    <path id="compile.sourcepath">
        <pathelement location="${src.dir}"/>
        <pathelement location="${shared.src.dir}"/>
    </path>

    <target name="prepare">
        <mkdir dir="${classes.dir}"/>
    </target>

    <target name="compile" depends="prepare">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               classpathref="compile.classpath"
               sourcepathref="compile.sourcepath"
               includeantruntime="false"
               encoding="UTF-8"/>
    </target>
</project>
~~~

Trong ví dụ:

- `compile.classpath` chứa JAR và thư mục lớp đã biên dịch.
- `compile.sourcepath` chứa các thư mục có mã nguồn bổ sung.
- `src.dir` xác định các nguồn chính mà Ant đưa vào lần biên dịch.
- `includeantruntime="false"` ngăn Ant runtime trở thành dependency ngầm của ứng dụng.

### 5.2. Dùng classpathref cho nhiều target

Nếu nhiều target cần cùng dependency, Path có ID giúp tái sử dụng:

~~~xml
<path id="compile.classpath">
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
</path>

<path id="test.classpath">
    <path refid="compile.classpath"/>
    <pathelement location="build/classes"/>
</path>

<target name="compile-main">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           classpathref="compile.classpath"
           includeantruntime="false"/>
</target>

<target name="compile-test" depends="compile-main">
    <javac srcdir="src/test/java"
           destdir="build/test-classes"
           classpathref="test.classpath"
           includeantruntime="false"/>
</target>
~~~

Ở ví dụ này, test code dùng các thư viện ngoài trong `compile.classpath` và cần thêm lớp ứng dụng đã biên dịch trong `build/classes`. Path `test.classpath` ghép hai nhóm này thành classpath riêng cho bước biên dịch test.

### 5.3. Classpath cho nhiều module

Khi module B phụ thuộc module A, thư mục output của A cần có trong classpath khi biên dịch B:

~~~xml
<path id="module-b.classpath">
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
    <pathelement location="build/module-a/classes"/>
</path>

<target name="compile-module-b" depends="compile-module-a">
    <mkdir dir="build/module-b/classes"/>
    <javac srcdir="module-b/src"
           destdir="build/module-b/classes"
           classpathref="module-b.classpath"
           includeantruntime="false"/>
</target>
~~~

Dependency của target bảo đảm module A được biên dịch trước. Classpath sau đó trỏ đến output đã tạo của A. Nếu bỏ dependency hoặc chỉ định sai thư mục output, compiler có thể báo không tìm thấy các kiểu thuộc module A.

## 6. Một ví dụ đầy đủ với srcdir, classpath, sourcepath và includeAntRuntime

Giả sử project có cấu trúc:

~~~text
project/
├── build.xml
├── src/
│   └── app/
│       └── Main.java
├── shared-src/
│   └── common/
│       └── TextUtil.java
├── lib/
│   └── logging-api.jar
└── build/
    ├── classes/
    └── generated/
        └── sources/
~~~

Mã nguồn Main.java dùng một thư viện ngoài và một lớp từ shared-src.

Buildfile:

~~~xml
<project name="compile-with-paths" default="compile" basedir=".">
    <property name="src.dir" location="src"/>
    <property name="shared.src.dir" location="shared-src"/>
    <property name="generated.src.dir" location="build/generated/sources"/>
    <property name="classes.dir" location="build/classes"/>
    <property name="lib.dir" location="lib"/>

    <path id="compile.classpath">
        <fileset dir="${lib.dir}">
            <include name="*.jar"/>
        </fileset>
    </path>

    <path id="compile.sourcepath">
        <pathelement location="${src.dir}"/>
        <pathelement location="${shared.src.dir}"/>
        <pathelement location="${generated.src.dir}"/>
    </path>

    <target name="prepare">
        <mkdir dir="${classes.dir}"/>
    </target>

    <target name="compile" depends="prepare">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               classpathref="compile.classpath"
               sourcepathref="compile.sourcepath"
               includeantruntime="false"
               includejavaruntime="false"
               encoding="UTF-8"
               debug="true"/>
    </target>
</project>
~~~

Luồng xử lý:

1. Ant tìm các tệp nguồn chính trong src.
2. javac dùng compile.classpath để tìm thư viện ngoài.
3. javac dùng compile.sourcepath để tìm thêm mã nguồn cần thiết.
4. Ant không tự thêm thư viện runtime của Ant hoặc Java vào classpath biên dịch theo hai thuộc tính include tương ứng.
5. Các lớp biên dịch được ghi vào build/classes.

Nếu shared-src được biên dịch trong một target riêng và tạo ra các lớp trong thư mục output, có thể chuyển thư mục output đó từ sourcepath sang classpath. Cách tổ chức này làm rõ ranh giới giữa mã nguồn cần biên dịch và lớp đã có sẵn.

## 7. Lưu ý với Java module và JDK hiện đại

Với dự án Java không dùng module, classpath vẫn là cách phổ biến để khai báo thư viện. Nhưng nếu dự án sử dụng Java Platform Module System, một số thư viện có thể phải được đặt trên module path thay vì classpath.

Ant có hỗ trợ các thuộc tính module path trong các phiên bản và compiler phù hợp. Không nên đặt tất cả thư viện vào classpath nếu build đang biên dịch các named module và cần quy tắc module resolution.

Cần phân biệt:

- classpath: các lớp và thư viện trên classpath truyền thống.
- module path: các module được Java module system nhận diện.
- sourcepath: các tệp nguồn Java mà compiler có thể tìm khi phân giải kiểu.
- module source path: cấu trúc nguồn của các module khi dùng cơ chế biên dịch module tương ứng.

Hãy kiểm tra phiên bản Ant, JDK và cú pháp javac mà dự án sử dụng trước khi thêm module path. Với build chưa dùng Java modules, không cần bổ sung cấu hình này.

## 8. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `package ... does not exist` | Thiếu JAR hoặc thư mục lớp trong classpath | Kiểm tra compile.classpath và đường dẫn dependency |
| `cannot find symbol` | Thiếu lớp phụ thuộc, sai phiên bản thư viện hoặc sourcepath không chứa mã nguồn cần thiết | Xác định kiểu bị thiếu rồi bổ sung đúng classpath hoặc sourcepath |
| Build chạy được trên máy này nhưng lỗi trên máy khác | Phụ thuộc ngầm vào Ant runtime hoặc thư viện cài cục bộ | Đặt includeAntRuntime=false và khai báo dependency rõ |
| Mã nguồn dùng lớp từ thư mục khác nhưng compiler không tìm thấy | Sourcepath không trỏ đến thư mục nguồn đó | Thêm thư mục vào sourcepath hoặc tổ chức target biên dịch riêng |
| Dùng nhầm lớp cũ | Classpath có nhiều bản thư viện hoặc output cũ đứng trước bản đúng | Loại bỏ JAR trùng và kiểm tra thứ tự Path |
| Không tạo được thư mục output | destdir chưa tồn tại | Dùng mkdir trong target phụ thuộc trước javac |
| Tạo classpath không tương thích giữa Windows và Linux | Tự nối chuỗi đường dẫn với dấu phân cách cố định | Dùng Path và pathelement của Ant |
| Biên dịch custom Ant task báo thiếu org.apache.tools.ant | Ant runtime không có trong classpath | Bật includeAntRuntime hoặc thêm ant.jar tường minh |
| Dự án module không phân giải được module | Đặt module dependency trên classpath thay vì module path | Cấu hình modulepath theo phiên bản Ant/JDK |

### 8.1. Kiểm tra classpath thực tế

Có thể chuyển Path thành chuỗi để xem các phần tử đã cấu hình:

~~~xml
<pathconvert property="compile.classpath.text"
             refid="compile.classpath"/>

<echo message="Compile classpath: ${compile.classpath.text}"/>
~~~

Đặt các task này trong target chẩn đoán hoặc trước javac khi cần tìm nguyên nhân. Đảm bảo ID được tham chiếu đã khai báo.

### 8.2. Kiểm tra sourcepath

In giá trị sourcepath nếu đã tạo Path có ID:

~~~xml
<pathconvert property="compile.sourcepath.text"
             refid="compile.sourcepath"/>

<echo message="Compile sourcepath: ${compile.sourcepath.text}"/>
~~~

Nếu thư mục nguồn cần thiết không xuất hiện, kiểm tra property, đường dẫn tương đối và cấu trúc thư mục.

### 8.3. Kiểm tra phụ thuộc Ant runtime

Nếu ứng dụng thông thường chỉ biên dịch được khi `includeantruntime="true"`, có khả năng mã nguồn đang vô tình dùng một lớp thuộc Ant runtime. Đặt false sẽ giúp phát hiện dependency đó.

Sau khi xác định lớp bị thiếu, hãy quyết định rõ dependency có thực sự cần thiết không. Nếu là thư viện của ứng dụng, thêm nó vào classpath dự án. Nếu là custom Ant task, khai báo API Ant cần thiết một cách tường minh hoặc giữ includeAntRuntime theo chủ đích.

## 9. Thực hành tốt

- Dùng Path có ID để khai báo classpath và sourcepath có thể tái sử dụng.
- Đặt tên Path theo mục đích như compile.classpath, test.classpath và compile.sourcepath.
- Chỉ đưa JAR và thư mục lớp cần thiết vào classpath.
- Dùng sourcepath cho các thư mục mã nguồn cần compiler tìm thêm; không nhầm nó với nơi lưu lớp đã biên dịch.
- Giữ srcdir rõ ràng để Ant xác định tập nguồn chính cần biên dịch.
- Với ứng dụng thông thường, đặt includeAntRuntime=false để tránh phụ thuộc ngầm vào thư viện Ant.
- Nếu biên dịch custom Ant task, khai báo Ant API mà mã nguồn cần.
- Không giữ nhiều phiên bản cùng một thư viện trong classpath nếu không có chủ đích.
- Tạo destdir trước khi chạy javac.
- Dùng Path thay vì tự nối chuỗi đường dẫn có dấu phân cách phụ thuộc hệ điều hành.
- Tách compile classpath và runtime classpath khi hai mục đích có dependency khác nhau.
- Với dự án Java module, phân biệt classpath và module path.

## 10. Tự kiểm tra cấu hình biên dịch

Trước khi chạy target javac, hãy tự trả lời:

1. srcdir có trỏ đến các thư mục nguồn chính cần biên dịch không?
2. destdir đã được tạo và đúng vị trí chưa?
3. Classpath có đủ JAR và thư mục lớp mà mã nguồn tham chiếu không?
4. Có JAR trùng phiên bản hoặc output cũ trong classpath không?
5. Sourcepath có chứa các thư mục mã nguồn bổ sung cần tìm không?
6. Có đang nhầm sourcepath với classpath hoặc srcdir không?
7. includeAntRuntime có nên là false đối với ứng dụng thông thường không?
8. Nếu mã nguồn dùng Ant API, dependency Ant đã được khai báo có chủ đích chưa?
9. Có đang biên dịch named module cần module path thay vì classpath không?
10. Cấu hình có hoạt động giống nhau trên máy phát triển và CI không?

Classpath xác định các lớp đã biên dịch và thư viện mà compiler cần; sourcepath xác định nơi tìm thêm mã nguồn; includeAntRuntime kiểm soát việc Ant runtime có tham gia classpath hay không. Khi ba phần này được khai báo theo đúng vai trò, task javac sẽ có môi trường biên dịch rõ ràng và ít phụ thuộc vào cấu hình ngầm của máy chạy build.
