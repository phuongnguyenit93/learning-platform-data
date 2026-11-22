# Chuyên biệt hóa task hoặc kiểu dữ liệu bằng presetdef trong Apache Ant

Trong một buildfile, nhiều target thường gọi cùng một task với một nhóm thuộc tính và phần tử con giống nhau. Ví dụ, mọi lần biên dịch đều cần `debug="true"`, `includeantruntime="false"`, encoding UTF-8 và cùng một compiler argument; nhiều thao tác copy cũng cần giữ timestamp hoặc loại thư mục rỗng theo một chính sách thống nhất. Nếu lặp lại cấu hình đó ở mọi nơi, buildfile dài hơn và các target dễ lệch nhau khi có thay đổi.

Apache Ant cung cấp task `<presetdef>` để tạo một định nghĩa mới dựa trên task hoặc kiểu dữ liệu đã có, đồng thời đặt trước một số thuộc tính hoặc phần tử con. Khi sử dụng định nghĩa mới, người viết chỉ cần cung cấp phần cấu hình khác nhau của từng lần gọi.

`presetdef` hữu ích để chuẩn hóa cấu hình lặp lại mà vẫn giữ nguyên task hoặc datatype nền. Nó không tạo một thuật toán build mới và cũng không thêm logic điều kiện hay tham số tùy ý như `macrodef`.

## 1. presetdef là gì?

`<presetdef>` tạo một định nghĩa mới dựa trên một định nghĩa Ant hiện có. Phần tử con trực tiếp của `presetdef` là task hoặc datatype nền, bên trong đó khai báo những thuộc tính và nested element muốn đặt trước.

Ví dụ:

~~~xml
<presetdef name="project.javac">
    <javac debug="true"
           deprecation="true"
           includeantruntime="false"
           encoding="UTF-8" />
</presetdef>
~~~

Định nghĩa này tạo task mới có tên `project.javac`, dựa trên task `javac`. Khi gọi:

~~~xml
<project.javac srcdir="src/main/java"
               destdir="build/classes" />
~~~

Ant thực hiện task javac với các mặc định đã đặt trước, đồng thời nhận thêm srcdir và destdir từ nơi gọi.

Một preset có thể đặt trước:

- Thuộc tính của task hoặc datatype nền.
- Nested element như classpath, compilerarg, fileset hoặc manifest, nếu thành phần nền hỗ trợ.
- Văn bản con khi kiểu nền cho phép nội dung dạng text.

Từ Apache Ant 1.6, `presetdef` có sẵn trong Ant. Nó nhận thuộc tính `name` để đặt tên định nghĩa mới và tùy chọn `uri` để đưa định nghĩa vào namespace.

## 2. Cấu trúc và cách khai báo

Cấu trúc tổng quát:

~~~xml
<presetdef name="ten-moi">
    <task-hoac-datatype-goc
        thuoc-tinh-mac-dinh="gia-tri">
        <!-- nested element muốn đặt trước -->
    </task-hoac-datatype-goc>
</presetdef>
~~~

Các thành phần:

| Thành phần | Vai trò |
|---|---|
| `presetdef` | Khai báo định nghĩa preset |
| `name` | Tên mới được dùng khi gọi preset |
| Phần tử con trực tiếp | Task hoặc datatype gốc mà preset dựa trên |
| Thuộc tính bên trong | Giá trị được đặt trước cho mỗi lần sử dụng |
| Nested element bên trong | Cấu hình con được gắn vào mỗi lần sử dụng |

Tên preset nên thể hiện mục đích hoặc quy ước của dự án, chẳng hạn:

- `project.javac`: cấu hình biên dịch Java chung.
- `project.test.javac`: cấu hình biên dịch mã test.
- `project.copy.resources`: quy tắc copy tài nguyên.
- `project.compile.path`: classpath chuẩn cho biên dịch.

Nên dùng tên riêng có tiền tố của dự án để tránh nhầm với task có sẵn của Ant hoặc preset được nạp từ thư viện khác.

## 3. Thuộc tính đặt trước có thể được ghi đè khi gọi

Giá trị khai báo trong preset đóng vai trò mặc định. Khi sử dụng định nghĩa mới, thuộc tính được truyền trực tiếp tại nơi gọi có thể ghi đè giá trị đã đặt trước.

Ví dụ:

~~~xml
<presetdef name="project.javac">
    <javac debug="true"
           deprecation="true"
           includeantruntime="false"
           encoding="UTF-8" />
</presetdef>

<target name="compile-main">
    <project.javac srcdir="src/main/java"
                   destdir="build/classes" />
</target>

<target name="compile-generated">
    <project.javac srcdir="build/generated"
                   destdir="build/generated-classes"
                   debug="false" />
</target>
~~~

Ở target compile-main, debug giữ giá trị true từ preset. Ở target compile-generated, debug được đặt thành false tại nơi gọi nên giá trị này thay thế mặc định true.

Các thuộc tính không được truyền tại nơi gọi tiếp tục sử dụng giá trị trong preset. Vì vậy, preset giúp tập trung quy ước chung nhưng vẫn cho phép ngoại lệ có chủ đích.

Nếu thuộc tính được đặt trước là đường dẫn, hãy cân nhắc dùng property để dễ thay đổi theo môi trường:

~~~xml
<property name="project.encoding" value="UTF-8" />
<property name="project.debug" value="true" />

<presetdef name="project.javac">
    <javac debug="${project.debug}"
           includeantruntime="false"
           encoding="${project.encoding}" />
</presetdef>
~~~

Cách này giúp định nghĩa preset không phải chứa các giá trị rải rác ở nhiều nơi. Lưu ý property của Ant thông thường bất biến sau khi được thiết lập; hãy nạp cấu hình hoặc khai báo property trước khi dùng preset nếu muốn giá trị đó có hiệu lực.

## 4. Đặt trước nested element

Preset không chỉ đặt thuộc tính. Nó còn có thể đặt trước các nested element của task nền.

Ví dụ, mọi lần biên dịch đều cần thêm compiler argument:

~~~xml
<presetdef name="project.javac">
    <javac debug="true"
           includeantruntime="false"
           encoding="UTF-8">
        <compilerarg value="-Xlint:deprecation" />
    </javac>
</presetdef>

<target name="compile">
    <mkdir dir="build/classes" />

    <project.javac srcdir="src/main/java"
                   destdir="build/classes" />
</target>
~~~

Khi gọi `project.javac`, Ant sử dụng thuộc tính và compilerarg đã đặt trước. Người gọi không cần khai báo lại compilerarg ở mọi target.

Có thể đặt trước classpath hoặc các thành phần khác:

~~~xml
<presetdef name="project.javac">
    <javac debug="true"
           includeantruntime="false"
           encoding="UTF-8">
        <classpath>
            <pathelement location="build/shared-classes" />
            <fileset dir="lib">
                <include name="**/*.jar" />
            </fileset>
        </classpath>
    </javac>
</presetdef>
~~~

Sau đó:

~~~xml
<project.javac srcdir="src/main/java"
               destdir="build/classes" />
~~~

Task javac nhận classpath chung mà không cần lặp danh sách thư viện.

### 4.1. Lưu ý khi task có nested element dạng đơn

Một số task cho phép nhiều nested element cùng loại, ví dụ nhiều compilerarg hoặc nhiều fileset. Một số task chỉ cho phép một nested element có tên nhất định, ví dụ một classpath hoặc một manifest.

Khi preset đã đặt một nested element dạng đơn, không nên mặc định rằng nơi gọi có thể khai báo thêm một nested element cùng loại. Khả năng kết hợp phụ thuộc vào API của task nền và cách task xử lý phần tử con. Nếu task chỉ chấp nhận một classpath, hai classpath có thể gây lỗi hoặc không có ý nghĩa như mong muốn.

Với cấu hình cần mở rộng theo từng lần gọi, hãy chọn một trong các cách:

- Đặt trước một Path có thể tái sử dụng và thiết kế nó để nhận thêm các phần tử cần thiết.
- Tạo các preset khác nhau cho từng trường hợp.
- Để nested element biến đổi ở nơi gọi, chỉ preset các thuộc tính ổn định.
- Dùng `macrodef` nếu cần tạo giao diện có tham số hoặc logic lắp ghép phức tạp hơn.

Không nên đặt trước quá nhiều cấu hình con nếu điều đó khiến nơi gọi khó biết task thực sự đang nhận những gì.

## 5. Chuyên biệt hóa task javac cho mã nguồn chính và mã test

Một ứng dụng thường có hai nhóm mã nguồn:

- Mã ứng dụng trong `src/main/java`.
- Mã kiểm thử trong `src/test/java`.

Cả hai có thể dùng cùng encoding và quy tắc compiler, nhưng classpath và thư mục đích khác nhau. Có thể tạo preset chung và preset chuyên biệt hơn.

~~~xml
<property name="main.classes" location="build/classes" />
<property name="test.classes" location="build/test-classes" />
<property name="junit.jar" location="lib/junit.jar" />

<presetdef name="project.javac">
    <javac debug="true"
           deprecation="true"
           includeantruntime="false"
           encoding="UTF-8" />
</presetdef>

<presetdef name="project.test.javac">
    <javac debug="true"
           deprecation="true"
           includeantruntime="false"
           encoding="UTF-8">
        <classpath>
            <pathelement location="${main.classes}" />
            <pathelement location="${junit.jar}" />
        </classpath>
    </javac>
</presetdef>

<target name="compile-main">
    <mkdir dir="${main.classes}" />
    <project.javac srcdir="src/main/java"
                   destdir="${main.classes}" />
</target>

<target name="compile-test" depends="compile-main">
    <mkdir dir="${test.classes}" />
    <project.test.javac srcdir="src/test/java"
                        destdir="${test.classes}" />
</target>
~~~

Preset project.javac chuẩn hóa các tùy chọn chung. Preset project.test.javac đặt thêm classpath để mã test nhìn thấy lớp ứng dụng và JUnit.

Trong ví dụ này, hai preset có tên riêng nên người đọc biết ngay mục đích sử dụng. Nếu muốn thay đổi classpath của test, có thể sửa tại một nơi thay vì tìm tất cả target biên dịch test.

## 6. Chuyên biệt hóa task copy

Task copy thường được gọi nhiều lần để đưa resource, cấu hình hoặc file phát hành đến thư mục đích. Có thể đặt trước một chính sách chung:

~~~xml
<presetdef name="project.copy.resources">
    <copy overwrite="false"
          preservelastmodified="true"
          includeEmptyDirs="false"
          filtering="false" />
</presetdef>
~~~

Sử dụng:

~~~xml
<target name="copy-config">
    <project.copy.resources todir="build/config">
        <fileset dir="config">
            <include name="**/*.properties" />
            <include name="**/*.xml" />
            <exclude name="local/**" />
        </fileset>
    </project.copy.resources>
</target>

<target name="copy-templates">
    <project.copy.resources todir="build/templates">
        <fileset dir="src/main/templates">
            <include name="**/*" />
        </fileset>
    </project.copy.resources>
</target>
~~~

Cả hai target cùng dùng chính sách:

- Không ghi đè file đích mới hơn nguồn.
- Giữ timestamp sửa đổi của file nguồn.
- Không tạo các thư mục rỗng không cần thiết.
- Không bật filtering nội dung file.

Các FileSet vẫn khác nhau theo thư mục nguồn và mẫu chọn file. Preset giúp chuẩn hóa hành vi của task, còn FileSet xác định dữ liệu cụ thể cần xử lý.

## 7. presetdef cho kiểu dữ liệu

Ngoài task, phần tử con trực tiếp của `presetdef` có thể là một datatype. Tài liệu Ant cho phép nested element này là bất kỳ type hoặc task đã được định nghĩa; vì vậy có thể tạo một kiểu dữ liệu mới dựa trên Path, FileSet hoặc datatype khác.

Điều này hữu ích khi nhiều task cần cùng một nhóm đường dẫn hoặc quy tắc chọn file.

### 7.1. Tạo preset cho Path

Ví dụ, nhiều task cần classpath chứa thư mục lớp dùng chung và tất cả JAR trong thư mục lib:

~~~xml
<presetdef name="project.compile.path">
    <path>
        <pathelement location="build/shared-classes" />
        <fileset dir="lib">
            <include name="**/*.jar" />
        </fileset>
    </path>
</presetdef>
~~~

Khi dùng trong task javac:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false">
    <project.compile.path />
</javac>
~~~

`project.compile.path` là preset datatype dựa trên Path. Nó có thể được đặt vào vị trí mà task nền chấp nhận một Path, chẳng hạn nested classpath của javac.

Có thể tạo một preset riêng cho classpath chạy nếu ứng dụng cần thêm thư mục output của chính nó:

~~~xml
<presetdef name="project.runtime.path">
    <path>
        <pathelement location="build/classes" />
        <pathelement location="build/shared-classes" />
        <fileset dir="lib">
            <include name="**/*.jar" />
        </fileset>
    </path>
</presetdef>

<java classname="com.example.Main" fork="true">
    <project.runtime.path />
</java>
~~~

Preset project.runtime.path chứa output của ứng dụng, thư mục lớp dùng chung và các JAR runtime. Task java nhận đúng một Path qua nested element này, nên classpath chạy được mô tả trọn vẹn trong một định nghĩa.

### 7.2. Kết hợp preset Path với Path thông thường

Có thể dùng preset Path bên trong một Path mới để bổ sung các vị trí riêng:

~~~xml
<path id="test.classpath">
    <project.compile.path />
    <pathelement location="build/test-classes" />
    <pathelement location="lib/junit.jar" />
</path>
~~~

Sau đó:

~~~xml
<junit>
    <classpath refid="test.classpath" />
</junit>
~~~

Path test.classpath kế thừa các phần tử đã được định nghĩa trong project.compile.path và bổ sung thư mục test cùng JUnit. Cách này giúp tránh sao chép danh sách JAR ở nhiều nơi.

Khi ghép Path, hãy chú ý các vị trí trùng lặp hoặc nhiều phiên bản cùng một thư viện. Thứ tự classpath có thể ảnh hưởng đến lớp nào được nạp khi có tên lớp trùng nhau.

### 7.3. Tạo preset cho FileSet

Có thể chuyên biệt hóa FileSet để dùng chung một bộ lọc:

~~~xml
<presetdef name="project.source.files">
    <fileset>
        <include name="**/*.java" />
        <exclude name="**/generated/**" />
        <exclude name="**/*Test.java" />
    </fileset>
</presetdef>
~~~

Khi cần chọn file từ một thư mục gốc, dùng preset ở nơi chấp nhận FileSet và cung cấp thuộc tính dir:

~~~xml
<copy todir="build/sources">
    <project.source.files dir="src/main/java" />
</copy>
~~~

Preset giữ lại các include/exclude chung, còn dir được cung cấp ở nơi gọi. Như vậy, nhiều FileSet có thể dùng cùng chính sách lọc mà vẫn quét các thư mục khác nhau.

## 8. Property được phân giải khi preset được sử dụng

Một đặc điểm quan trọng là các property reference trong thuộc tính hoặc nested text của preset được phân giải khi preset được sử dụng, không phải ngay khi khai báo định nghĩa.

Ví dụ:

~~~xml
<target name="show-modes">
    <presetdef name="project.show.mode">
        <echo message="Current mode: ${build.mode}" />
    </presetdef>

    <property name="build.mode" value="development" />
    <project.show.mode />
</target>
~~~

Khi project.show.mode được thực hiện, Ant phân giải ${build.mode} theo giá trị hiện có tại thời điểm sử dụng. Vì property đã được đặt thành development trước lần gọi, thông báo sẽ dùng giá trị đó.

Điều này hữu ích khi preset được khai báo ở cấp project nhưng các property chỉ có sẵn trong target hoặc trong build con. Có thể dùng cùng một preset trong các lần gọi khác nhau và nhận property theo ngữ cảnh lúc sử dụng.

Tuy nhiên, cần nhớ property Ant thông thường không thể thay đổi sau khi đã được thiết lập. Nếu build.mode đã được đặt trước đó, một lần khai báo property khác sẽ không thay thế nó. Việc phân giải muộn không biến property thành biến có thể gán lại.

## 9. Đặt preset trong antlib và sử dụng namespace

Khi một nhóm preset được chia sẻ giữa nhiều buildfile, có thể đóng gói định nghĩa vào Antlib. Antlib cho phép định nghĩa task, datatype và preset theo một namespace riêng.

Ví dụ file antlib.xml trong JAR thư viện:

~~~xml
<antlib>
    <presetdef name="javac">
        <javac debug="true"
               deprecation="true"
               includeantruntime="false"
               encoding="UTF-8" />
    </presetdef>
</antlib>
~~~

Giả sử file nằm trong JAR ở resource `com/example/build/antlib.xml`, buildfile có thể nạp và sử dụng namespace:

~~~xml
<project name="sample" default="compile"
         xmlns:build="antlib:com.example.build">

    <target name="compile">
        <build:javac srcdir="src/main/java"
                     destdir="build/classes" />
    </target>
</project>
~~~

Namespace giúp phân biệt preset của thư viện với task cùng tên trong Ant hoặc trong các Antlib khác. Đây là cách phù hợp khi nhóm muốn chia sẻ quy ước build giữa nhiều repository.

Trong một buildfile nhỏ, có thể khai báo preset trực tiếp với tên có tiền tố như project.javac. Với thư viện dùng chung, namespace tạo ranh giới rõ ràng hơn.

## 10. presetdef khác macrodef, typedef và taskdef như thế nào?

Các cơ chế này đều tạo hoặc mở rộng định nghĩa trong Ant nhưng phục vụ mục đích khác nhau.

| Cơ chế | Dùng khi nào? | Điều nó cung cấp |
|---|---|---|
| presetdef | Muốn dùng task/datatype có sẵn với một số thuộc tính hoặc phần tử con được đặt trước | Định nghĩa mới dựa trên type hiện có |
| macrodef | Muốn đóng gói chuỗi task thành một task macro và nhận tham số do người gọi truyền | Attribute, text, nested element và logic gồm nhiều task |
| typedef | Muốn đăng ký một datatype do lớp Java triển khai | Tên mới cho implementation của datatype |
| taskdef | Muốn đăng ký một task do lớp Java triển khai | Tên task mới cho implementation |
| antlib | Muốn đóng gói nhiều định nghĩa và tài nguyên Ant thành thư viện | Namespace và tập định nghĩa có thể tái sử dụng |

### 10.1. presetdef so với macrodef

Dùng presetdef khi chỉ cần cấu hình sẵn một task hiện có:

~~~xml
<presetdef name="project.echo">
    <echo level="info" />
</presetdef>

<project.echo message="Build started" />
~~~

Dùng macrodef khi cần tạo một thao tác gồm nhiều task hoặc cần tham số riêng:

~~~xml
<macrodef name="project.compile-and-copy">
    <attribute name="src" />
    <attribute name="dest" />

    <sequential>
        <mkdir dir="@{dest}" />
        <javac srcdir="@{src}"
               destdir="@{dest}"
               includeantruntime="false" />
        <copy todir="@{dest}">
            <fileset dir="@{src}">
                <include name="**/*.properties" />
            </fileset>
        </copy>
    </sequential>
</macrodef>

<project.compile-and-copy src="src/main/java"
                          dest="build/classes" />
~~~

Macrodef cung cấp placeholder như `@{src}` và `@{dest}`. Presetdef không tạo placeholder mới như vậy; nó chỉ đặt trước thuộc tính hoặc nested element mà task nền đã hỗ trợ.

### 10.2. presetdef so với typedef

Dùng typedef khi có lớp Java triển khai datatype mới:

~~~xml
<typedef name="my.resource.list"
        classname="com.example.ant.ResourceList"
        classpath="lib/custom-ant-types.jar" />
~~~

Dùng presetdef khi đã có một datatype như Path hoặc FileSet và chỉ muốn cấu hình sẵn một số phần tử:

~~~xml
<presetdef name="project.resource.path">
    <path>
        <pathelement location="build/resources" />
        <fileset dir="lib">
            <include name="*.jar" />
        </fileset>
    </path>
</presetdef>
~~~

Không cần viết lớp Java mới cho preset này. Ant tạo định nghĩa mới từ Path hiện có.

## 11. Phân chia preset theo mục đích

Một buildfile lớn có thể có nhiều preset. Nên đặt tên theo trách nhiệm để người đọc hiểu cấu hình được áp dụng.

Ví dụ:

~~~xml
<presetdef name="project.javac.main">
    <javac debug="true"
           includeantruntime="false"
           encoding="UTF-8" />
</presetdef>

<presetdef name="project.javac.test">
    <javac debug="true"
           includeantruntime="false"
           encoding="UTF-8">
        <classpath>
            <pathelement location="build/classes" />
            <pathelement location="lib/junit.jar" />
        </classpath>
    </javac>
</presetdef>

<presetdef name="project.copy.config">
    <copy overwrite="false"
          preservelastmodified="true"
          includeEmptyDirs="false" />
</presetdef>

<presetdef name="project.release.zip">
    <zip duplicate="fail"
         encoding="UTF-8"
         update="false" />
</presetdef>
~~~

Mỗi preset phục vụ một vai trò cụ thể:

- project.javac.main dành cho mã ứng dụng.
- project.javac.test dành cho mã kiểm thử.
- project.copy.config dành cho cấu hình.
- project.release.zip dành cho archive phát hành.

Nếu có một nhóm thuộc tính giống nhau ở mọi nơi, đặt nó trong preset chung. Nếu hai nhóm có chính sách khác nhau, tạo hai preset thay vì thêm nhiều ngoại lệ tại nơi gọi.

## 12. Các lỗi thường gặp

### 12.1. Dùng tên preset trùng với task có sẵn

Đặt preset tên javac hoặc copy có thể gây nhầm lẫn với task chuẩn. Hãy dùng tiền tố riêng như project.javac hoặc namespace Antlib để tránh va chạm và giúp người đọc nhận ra định nghĩa tùy chỉnh.

### 12.2. Nghĩ rằng preset tạo thêm thuộc tính tùy ý

Preset không tự định nghĩa attribute mới. Mọi thuộc tính truyền vào nơi gọi phải được task hoặc datatype nền hỗ trợ. Nếu cần tham số mới, hãy xem xét macrodef hoặc viết task riêng.

### 12.3. Mong nested element được ghép theo cách không được hỗ trợ

Preset chuyển nested element đã khai báo vào type nền. Nếu type nền chỉ nhận một classpath hoặc manifest, thêm một phần tử cùng loại ở nơi gọi có thể gây lỗi. Hãy hiểu API của task gốc trước khi đặt trước cấu hình con.

### 12.4. Property chưa có giá trị tại thời điểm sử dụng

Nếu preset tham chiếu ${lib.dir} nhưng property chưa được thiết lập khi task được thực hiện, đường dẫn có thể không đúng như mong đợi. Khai báo hoặc nạp property trước khi gọi preset.

### 12.5. Dùng presetdef thay cho macrodef

Nếu cần truyền tham số tùy chỉnh, chạy nhiều task theo thứ tự hoặc có điều kiện riêng, presetdef không đủ. Macrodef phù hợp hơn vì cho phép khai báo attribute và một chuỗi task.

### 12.6. Đặt quá nhiều cấu hình ẩn

Preset giúp giảm lặp lại, nhưng nếu tên quá chung và cấu hình đặt trước quá dài, người đọc khó biết một lần gọi thực sự làm gì. Đặt tên theo mục đích, giữ mỗi preset tập trung vào một quy ước và ghi chú các tác dụng đáng chú ý.

### 12.7. Không kiểm tra phiên bản Ant

presetdef có từ Ant 1.6. Nếu build phải chạy trên môi trường cũ hơn, cần xác nhận phiên bản tối thiểu hoặc dùng cách khai báo task trực tiếp.

## 13. Thực hành tốt

- **Đặt tên theo mục đích.** Dùng project.javac.main, project.copy.resources hoặc project.compile.path thay vì tên quá chung.
- **Chỉ preset phần cấu hình ổn định.** Để các giá trị thay đổi theo target như srcdir, destdir hoặc todir ở nơi gọi.
- **Đặt preset gần phần khai báo build chung.** Khai báo ở cấp project hoặc đóng gói trong Antlib để nhiều target cùng dùng.
- **Dùng property cho giá trị môi trường.** Tập trung đường dẫn, encoding và cờ build trong property thay vì ghi cứng ở nhiều preset.
- **Tách preset theo trách nhiệm.** Biên dịch mã chính, biên dịch test, copy resource và đóng gói có thể cần các quy ước khác nhau.
- **Cẩn thận với nested element đơn.** Không thêm classpath hoặc manifest lần thứ hai nếu task nền không hỗ trợ nhiều phần tử.
- **Dùng preset datatype để chia sẻ cấu hình Path/FileSet.** Điều này giúp classpath và chính sách chọn file nhất quán.
- **Dùng macrodef cho logic có tham số.** Không ép presetdef làm nhiệm vụ của macro.
- **Dùng namespace khi chia sẻ giữa repository.** Antlib namespace giúp tránh trùng tên và làm rõ nguồn định nghĩa.
- **Ghi rõ phiên bản Ant tối thiểu.** presetdef có từ Ant 1.6; các task nền vẫn phải tương thích với phiên bản Ant/JDK của môi trường.

## 14. Kết luận

`presetdef` tạo một định nghĩa mới dựa trên task hoặc datatype hiện có và đặt trước thuộc tính, nested element hoặc nội dung được hỗ trợ. Khi gọi preset, các giá trị mặc định được áp dụng; thuộc tính được truyền trực tiếp tại nơi gọi có thể ghi đè giá trị preset. Các property reference bên trong preset được phân giải khi preset được sử dụng.

Có thể dùng presetdef để chuẩn hóa javac, copy, zip hoặc datatype như Path và FileSet. Điều này giảm lặp lại và giữ cấu hình nhất quán giữa các target. Khi cần thêm tham số tùy ý hoặc đóng gói chuỗi task có logic, hãy dùng macrodef; khi cần đăng ký implementation Java mới, hãy dùng typedef hoặc taskdef. Chọn đúng cơ chế giúp buildfile dễ đọc, dễ chia sẻ và dễ bảo trì.

## Tài liệu tham khảo

- [Apache Ant PresetDef Task](https://ant.apache.org/manual/Tasks/presetdef.html)
- [Apache Ant MacroDef Task](https://ant.apache.org/manual/Tasks/macrodef.html)
- [Apache Ant Typedef Task](https://ant.apache.org/manual/Tasks/typedef.html)
- [Apache Ant Task Overview](https://ant.apache.org/manual/tasksoverview.html)

