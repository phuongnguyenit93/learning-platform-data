# Định nghĩa chuỗi task tái sử dụng bằng macrodef trong Apache Ant

Khi nhiều target trong một build file cần thực hiện cùng một nhóm thao tác, bạn có thể gặp tình trạng lặp lại các task như tạo thư mục, biên dịch, sao chép tài nguyên, chạy kiểm thử và ghi log. Nếu mỗi nơi tự khai báo một bản gần giống nhau, việc sửa quy trình sẽ tốn công và dễ tạo ra hành vi không nhất quán.

Apache Ant cung cấp task **macrodef** để định nghĩa một task mới từ một chuỗi task có sẵn. Macro có thể nhận tham số, nhận các task lồng từ nơi gọi và chèn chúng vào đúng vị trí trong phần thân. Sau khi định nghĩa, bạn gọi macro như một task Ant thông thường.

Ví dụ, thay vì viết cùng một khối javac ở nhiều target, có thể định nghĩa macro compile-java một lần rồi truyền thư mục nguồn và thư mục đầu ra ở mỗi lần gọi.

## 1. macrodef là gì?

macrodef là task dùng để tạo một task tùy chỉnh từ các task Ant khác. Macro không yêu cầu viết Java class hoặc tạo plugin riêng. Bạn mô tả chuỗi thao tác bằng XML, khai báo những giá trị mà chuỗi thao tác cần nhận, rồi gọi tên macro ở những nơi phù hợp.

Một macro cơ bản có ba phần:

1. Tên task mới.
2. Các attribute và element mà nơi gọi được phép truyền vào.
3. Phần sequential chứa các task sẽ được thực thi.

Cấu trúc tổng quát:

~~~xml
<macrodef name="task-name">
    <attribute name="input"/>
    <element name="extra-tasks" optional="true"/>

    <sequential>
        <echo message="Input: @{input}"/>
        <extra-tasks/>
    </sequential>
</macrodef>
~~~

Sau khi định nghĩa, có thể gọi macro:

~~~xml
<task-name input="sample">
    <extra-tasks>
        <mkdir dir="build/sample"/>
    </extra-tasks>
</task-name>
~~~

Khi Ant thực thi lời gọi, giá trị input được thay vào vị trí @{input}; nội dung bên trong extra-tasks được đưa vào vị trí placeholder tương ứng. Các task trong sequential được chạy theo thứ tự xuất hiện.

### 1.1. macrodef phải được định nghĩa trước khi sử dụng

Thông thường, khai báo macrodef ở cấp project, bên ngoài các target:

~~~xml
<project name="macro-demo" default="build" basedir=".">

    <macrodef name="say-build">
        <attribute name="message"/>
        <sequential>
            <echo message="BUILD: @{message}"/>
        </sequential>
    </macrodef>

    <target name="build">
        <say-build message="Starting compilation"/>
    </target>

</project>
~~~

Định nghĩa macro là một phần của cấu hình project. Lời gọi macro có thể nằm trong target và được thực thi khi target đó chạy.

Không đặt định nghĩa macrodef bên trong một target như thể đó là một thao tác runtime. Hãy định nghĩa task trước, rồi gọi task trong target cần sử dụng.

### 1.2. Macro không phải target mới

Macro tạo ra một task mới, không tạo target mới. Do đó:

- Macro có thể được gọi từ nhiều target.
- Lời gọi macro chạy các task trong phần thân sequential.
- Macro không tự có thuộc tính depends như target.
- Macro không tạo một project độc lập hay một phạm vi property riêng.
- Các property, path reference và tài nguyên của project hiện tại vẫn được sử dụng theo quy tắc thông thường của Ant.

Nếu cần quản lý thứ tự phụ thuộc giữa các giai đoạn lớn của build, hãy dùng target và depends. Nếu cần đóng gói một chuỗi thao tác nhỏ để gọi lại, macrodef là lựa chọn phù hợp.

## 2. Khai báo và sử dụng attribute

Attribute là tham số dạng chuỗi được truyền vào macro khi gọi. Trong phần thân macro, tham chiếu đến attribute bằng cú pháp @{tên}.

Ví dụ:

~~~xml
<macrodef name="make-dir">
    <attribute name="path"/>

    <sequential>
        <mkdir dir="@{path}"/>
        <echo message="Created directory: @{path}"/>
    </sequential>
</macrodef>

<target name="prepare">
    <make-dir path="build/classes"/>
    <make-dir path="build/reports"/>
</target>
~~~

Hai lần gọi dùng cùng một quy trình nhưng truyền giá trị path khác nhau. Khi cần thay đổi cách tạo thư mục hoặc cách ghi log, bạn chỉ cần sửa phần định nghĩa macro.

### 2.1. Attribute bắt buộc

Khi khai báo attribute mà không có default, nơi gọi phải truyền giá trị:

~~~xml
<macrodef name="compile-source">
    <attribute name="src"/>
    <attribute name="dest"/>

    <sequential>
        <mkdir dir="@{dest}"/>
        <javac
            srcdir="@{src}"
            destdir="@{dest}"
            includeantruntime="false"/>
    </sequential>
</macrodef>
~~~

Lời gọi hợp lệ:

~~~xml
<compile-source src="src/main/java" dest="build/classes"/>
~~~

Nếu bỏ src hoặc dest, Ant báo lỗi vì macro thiếu attribute bắt buộc. Cách khai báo này hữu ích khi thiếu tham số sẽ làm thao tác không thể thực hiện đúng.

### 2.2. Attribute có giá trị mặc định

Có thể dùng thuộc tính default để cung cấp giá trị khi nơi gọi không truyền attribute đó:

~~~xml
<macrodef name="compile-source">
    <attribute name="src"/>
    <attribute name="dest"/>
    <attribute name="encoding" default="UTF-8"/>
    <attribute name="debug" default="true"/>

    <sequential>
        <mkdir dir="@{dest}"/>
        <javac
            srcdir="@{src}"
            destdir="@{dest}"
            encoding="@{encoding}"
            debug="@{debug}"
            includeantruntime="false"/>
    </sequential>
</macrodef>
~~~

Có thể gọi mà không cần khai báo encoding và debug:

~~~xml
<compile-source src="src/main/java" dest="build/classes"/>
~~~

Hoặc ghi đè giá trị mặc định ở một lần gọi cụ thể:

~~~xml
<compile-source
    src="src/legacy"
    dest="build/legacy-classes"
    encoding="ISO-8859-1"
    debug="false"/>
~~~

Giá trị mặc định giúp macro dễ sử dụng khi đa số lời gọi cùng dùng một cấu hình. Chỉ đưa vào default những giá trị thực sự có thể dùng an toàn cho các trường hợp gọi khác nhau.

### 2.3. Mô tả attribute

Có thể thêm description để giải thích ý nghĩa tham số ngay trong định nghĩa:

~~~xml
<macrodef name="copy-resource">
    <attribute name="source" description="File nguồn cần sao chép"/>
    <attribute name="destination" description="Thư mục nhận file"/>
    <sequential>
        <copy file="@{source}" todir="@{destination}"/>
    </sequential>
</macrodef>
~~~

Description không thay đổi cách macro chạy. Nó giúp người đọc build file hiểu ý nghĩa của attribute mà không cần lần theo mọi lần gọi.

### 2.4. Attribute khác property của Ant

Cú pháp @{name} là placeholder của macrodef. Nó khác cú pháp property của Ant:

| Cú pháp | Mục đích |
|---|---|
| Dollar-brace property reference | Đọc giá trị property của Ant. |
| @{attribute} | Chèn giá trị attribute của lần gọi macro hiện tại. |

Ví dụ:

~~~xml
<property name="build.root" location="build"/>

<macrodef name="compile-module">
    <attribute name="module"/>
    <sequential>
        <javac
            srcdir="src/@{module}"
            destdir="${build.root}/@{module}"
            includeantruntime="false"/>
    </sequential>
</macrodef>

<target name="compile">
    <compile-module module="core"/>
    <compile-module module="web"/>
</target>
~~~

Property build.root là cấu hình chung của project. Attribute module thay đổi theo từng lần gọi. Kết hợp hai loại này giúp tách cấu hình dùng chung khỏi tham số riêng của thao tác.

## 3. Nhận task lồng bằng element

Attribute phù hợp với các giá trị đơn như đường dẫn, tên module, encoding hoặc cờ boolean. Khi muốn nơi gọi truyền vào một nhóm task hoặc cấu hình XML có cấu trúc, hãy khai báo element.

Element được khai báo bằng phần tử element bên trong macrodef. Trong phần thân macro, dùng một phần tử cùng tên làm vị trí chèn nội dung.

### 3.1. Element bắt buộc

Ví dụ macro nhận một nhóm task để chạy sau khi tạo thư mục:

~~~xml
<macrodef name="prepare-and-run">
    <attribute name="workdir"/>
    <element name="steps"/>

    <sequential>
        <mkdir dir="@{workdir}"/>
        <steps/>
    </sequential>
</macrodef>
~~~

Khi gọi macro, phải cung cấp element steps:

~~~xml
<prepare-and-run workdir="build/generated">
    <steps>
        <echo message="Preparing generated sources"/>
        <copy todir="build/generated">
            <fileset dir="src/generated-template"/>
        </copy>
    </steps>
</prepare-and-run>
~~~

Nội dung bên trong steps được chèn vào vị trí <steps/> trong sequential. Macro thực hiện mkdir trước, sau đó mới chạy echo và copy.

Element cho phép nơi gọi truyền cấu trúc task linh hoạt mà không cần tạo attribute riêng cho từng tùy chọn.

### 3.2. Element tùy chọn

Nếu một số lần gọi không cần task bổ sung, khai báo optional="true":

~~~xml
<macrodef name="compile-with-options">
    <attribute name="src"/>
    <attribute name="dest"/>
    <element name="compiler-options" optional="true"/>

    <sequential>
        <mkdir dir="@{dest}"/>
        <javac
            srcdir="@{src}"
            destdir="@{dest}"
            includeantruntime="false">
            <compiler-options/>
        </javac>
    </sequential>
</macrodef>
~~~

Lời gọi không truyền compiler-options:

~~~xml
<compile-with-options src="src/main/java" dest="build/classes"/>
~~~

Lời gọi có truyền compiler-options:

~~~xml
<compile-with-options src="src/main/java" dest="build/classes">
    <compiler-options>
        <compilerarg value="-Xlint:unchecked"/>
        <compilerarg value="-parameters"/>
    </compiler-options>
</compile-with-options>
~~~

Trong ví dụ, các compilerarg được đặt vào bên trong javac tại vị trí compiler-options. Element tùy chọn giúp macro hỗ trợ trường hợp đơn giản mà không buộc mọi lời gọi phải cung cấp một khối rỗng.

Tên placeholder trong macrodef phải khớp với tên element khai báo. Nếu khai báo element tên compiler-options nhưng trong sequential lại dùng một tên khác, Ant không thể thay nội dung đúng vị trí.

### 3.3. Dùng nhiều element

Một macro có thể khai báo nhiều element để nhận các nhóm nội dung khác nhau:

~~~xml
<macrodef name="copy-and-verify">
    <attribute name="source"/>
    <attribute name="destination"/>
    <element name="copy-options" optional="true"/>
    <element name="after-copy" optional="true"/>

    <sequential>
        <copy file="@{source}" todir="@{destination}">
            <copy-options/>
        </copy>
        <after-copy/>
    </sequential>
</macrodef>
~~~

Lời gọi:

~~~xml
<copy-and-verify
    source="config/app.properties"
    destination="build/config">
    <copy-options>
        <filterset>
            <filter token="ENVIRONMENT" value="staging"/>
        </filterset>
    </copy-options>
    <after-copy>
        <echo message="Configuration copied"/>
    </after-copy>
</copy-and-verify>
~~~

Nhóm copy-options cấu hình task copy. Nhóm after-copy chạy sau khi copy hoàn thành. Tách các nhóm element theo vai trò giúp lời gọi dễ đọc hơn khi macro có nhiều điểm mở rộng.

## 4. Element implicit để nhận các task trực tiếp

Trong một số macro, bạn muốn nơi gọi đặt các task con trực tiếp bên trong lời gọi mà không cần bọc trong một element có tên riêng. Khi đó có thể khai báo một element với implicit="true".

Ví dụ:

~~~xml
<macrodef name="with-build-log">
    <attribute name="label"/>
    <element name="body" implicit="true"/>

    <sequential>
        <echo message="Starting: @{label}"/>
        <body/>
        <echo message="Finished: @{label}"/>
    </sequential>
</macrodef>
~~~

Gọi macro:

~~~xml
<with-build-log label="copy resources">
    <copy todir="build/resources">
        <fileset dir="src/main/resources"/>
    </copy>
    <echo message="Resource copy step completed"/>
</with-build-log>
~~~

Các task con trực tiếp của with-build-log được nhận bởi element implicit body và được chèn vào vị trí <body/>.

Cách này làm lời gọi gọn, đặc biệt khi macro có ý nghĩa như một wrapper: ghi log trước và sau, thiết lập môi trường hoặc thực hiện thao tác dọn dẹp quanh một nhóm task.

Một macro chỉ nên có một element implicit. Nếu cần nhiều nhóm nội dung có tên và vị trí riêng, hãy khai báo các element thông thường để người gọi phân biệt được chúng.

## 5. Nhận văn bản bằng text

Khi nội dung truyền vào là văn bản thuần thay vì task XML, macrodef có thể khai báo phần tử text.

Ví dụ tạo macro ghi thông báo:

~~~xml
<macrodef name="build-message">
    <attribute name="level" default="INFO"/>
    <text name="message" trim="true"/>

    <sequential>
        <echo message="[@{level}] @{message}"/>
    </sequential>
</macrodef>
~~~

Gọi macro:

~~~xml
<build-message level="INFO">Compiling application</build-message>
<build-message level="WARN">Optional configuration was not found</build-message>
~~~

Giá trị văn bản giữa thẻ mở và thẻ đóng được đưa vào placeholder @{message}. Thuộc tính trim="true" loại bỏ khoảng trắng ở đầu và cuối văn bản trước khi thay thế.

Nếu không cần trim, bỏ thuộc tính này để giữ nguyên khoảng trắng theo nội dung truyền vào. Văn bản phù hợp với thông báo, tên mô tả hoặc một đoạn nội dung đơn giản; nếu cần truyền task Ant hoặc cấu trúc XML, hãy dùng element.

## 6. Quy tắc thay thế và mở rộng giá trị

Khi dùng macrodef, cần phân biệt ba giai đoạn:

1. Ant đọc build file và xử lý property theo cơ chế cấu hình.
2. Khi gọi macro, các attribute và element được nhận từ lời gọi.
3. Macro thay placeholder trong phần thân rồi thực thi chuỗi task đã tạo.

Hiểu quy tắc thay thế giúp tránh lỗi khi giá trị truyền vào có chứa cú pháp giống placeholder hoặc property.

### 6.1. Dùng @{...} đúng vị trí

Ví dụ:

~~~xml
<macrodef name="show-path">
    <attribute name="directory"/>
    <sequential>
        <echo message="Directory is @{directory}"/>
    </sequential>
</macrodef>
~~~

Trong phần thân macro, @{directory} là placeholder. Khi gọi:

~~~xml
<show-path directory="build/classes"/>
~~~

Ant thay placeholder bằng build/classes.

Nếu viết nhầm dollar-brace reference cho directory, Ant sẽ tìm property có tên directory. Property đó không tự được tạo bởi attribute của macro. Hãy dùng đúng cú pháp cho đúng loại dữ liệu.

### 6.2. Escape cú pháp placeholder bằng @@{

Nếu phần thân macro cần in ra chuỗi có dạng @{name} theo nghĩa văn bản, bạn có thể escape ký tự mở đầu bằng cách viết @@{:

~~~xml
<macrodef name="show-syntax">
    <sequential>
        <echo message="Use @@{attribute} to refer to a macro attribute"/>
    </sequential>
</macrodef>
~~~

Cách viết này giúp macro xuất ra cú pháp placeholder như văn bản thay vì coi đó là một attribute cần thay thế.

### 6.3. doubleexpanding của attribute

Attribute trong macrodef có thể có thuộc tính doubleexpanding. Mặc định, giá trị attribute được mở rộng property lần nữa khi macro được mở rộng. Đặt doubleexpanding="false" nếu muốn tránh lần mở rộng thứ hai đối với giá trị attribute đó.

Ví dụ:

~~~xml
<property name="release.name" value="stable"/>

<macrodef name="print-value">
    <attribute name="value" doubleexpanding="false"/>
    <sequential>
        <echo message="Value: @{value}"/>
    </sequential>
</macrodef>
~~~

Thuộc tính này hữu ích khi giá trị truyền vào có chứa chuỗi giống cú pháp property và bạn cần giữ nguyên chuỗi đó trong quá trình macro expansion.

Chỉ tắt doubleexpanding khi đã hiểu dữ liệu truyền vào. Nếu macro cần tiếp tục mở rộng property tham chiếu trong giá trị attribute, hãy giữ mặc định.

## 7. Ví dụ thực tế: macro biên dịch Java có thể tái sử dụng

Một build file thường biên dịch nhiều phần của ứng dụng. Các bước cơ bản giống nhau: tạo thư mục đầu ra, gọi javac, đặt encoding, giữ thông tin debug và thêm classpath nếu cần.

Có thể định nghĩa macro nhận source, destination và một element tùy chọn chứa dependency:

~~~xml
<macrodef name="compile-java">
    <attribute name="src"/>
    <attribute name="dest"/>
    <attribute name="encoding" default="UTF-8"/>
    <attribute name="debug" default="true"/>
    <element name="dependencies" optional="true"/>

    <sequential>
        <mkdir dir="@{dest}"/>

        <javac
            srcdir="@{src}"
            destdir="@{dest}"
            encoding="@{encoding}"
            debug="@{debug}"
            includeantruntime="false">
            <dependencies/>
        </javac>
    </sequential>
</macrodef>
~~~

Khai báo path dùng chung:

~~~xml
<path id="main.compile.classpath">
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
</path>
~~~

Gọi macro cho mã nguồn chính:

~~~xml
<compile-java
    src="src/main/java"
    dest="build/classes"/>
~~~

Gọi macro cho mã nguồn cần thư viện:

~~~xml
<compile-java
    src="src/integration/java"
    dest="build/integration-classes"
    debug="true">
    <dependencies>
        <classpath refid="main.compile.classpath"/>
    </dependencies>
</compile-java>
~~~

Cả hai lời gọi sử dụng cùng một quy trình biên dịch. Lời gọi thứ hai truyền thêm classpath qua element dependencies; lời gọi đầu tiên bỏ qua element này.

## 8. Ví dụ thực tế: macro chạy test với cấu hình tùy chọn

Có thể dùng macrodef để chuẩn hóa cách chạy test ở nhiều module. Ví dụ, tất cả module đều cần fork JVM, dừng build khi test thất bại và lưu báo cáo vào thư mục riêng.

~~~xml
<macrodef name="run-junit-tests">
    <attribute name="test-classes"/>
    <attribute name="report-dir"/>
    <element name="test-classpath"/>

    <sequential>
        <mkdir dir="@{report-dir}"/>

        <junit
            fork="true"
            forkmode="once"
            printsummary="yes"
            haltonfailure="true">
            <test-classpath/>
            <formatter type="plain"/>
            <batchtest todir="@{report-dir}">
                <fileset dir="@{test-classes}">
                    <include name="**/*Test.class"/>
                </fileset>
            </batchtest>
        </junit>
    </sequential>
</macrodef>
~~~

Khai báo classpath test:

~~~xml
<path id="core.test.classpath">
    <pathelement location="build/classes"/>
    <pathelement location="build/test-classes"/>
    <fileset dir="lib/test">
        <include name="*.jar"/>
    </fileset>
</path>
~~~

Gọi macro:

~~~xml
<target name="test-core">
    <run-junit-tests
        test-classes="build/test-classes"
        report-dir="build/reports/core">
        <test-classpath>
            <classpath refid="core.test.classpath"/>
        </test-classpath>
    </run-junit-tests>
</target>
~~~

Ở đây element test-classpath là điểm mở rộng để caller cung cấp classpath thích hợp. Nếu module khác có bộ thư viện riêng, chỉ cần khai báo path khác rồi truyền vào cùng macro.

Ví dụ dùng task junit của Ant cần có thư viện JUnit và thành phần Ant JUnit tương ứng trên classpath của Ant. Macro chỉ đóng gói cách gọi task, không tự cài đặt các thư viện kiểm thử.

## 9. Ví dụ hoàn chỉnh: build nhiều module bằng macrodef

Giả sử ứng dụng có hai module độc lập:

~~~text
project/
├── build.xml
├── src/
│   ├── core/
│   │   └── com/example/core/
│   └── cli/
│       └── com/example/cli/
└── build/
~~~

Định nghĩa macro compile-java ở cấp project và gọi từ các target:

~~~xml
<project name="macro-multi-module" default="compile-all" basedir=".">

    <property name="build.dir" location="build"/>

    <macrodef name="compile-java">
        <attribute name="src"/>
        <attribute name="dest"/>
        <attribute name="encoding" default="UTF-8"/>
        <element name="dependencies" optional="true"/>

        <sequential>
            <mkdir dir="@{dest}"/>
            <javac
                srcdir="@{src}"
                destdir="@{dest}"
                encoding="@{encoding}"
                includeantruntime="false"
                debug="true">
                <dependencies/>
            </javac>
        </sequential>
    </macrodef>

    <path id="cli.classpath">
        <pathelement location="${build.dir}/core"/>
    </path>

    <target name="clean">
        <delete dir="${build.dir}"/>
    </target>

    <target name="compile-core">
        <compile-java
            src="src/core"
            dest="${build.dir}/core"/>
    </target>

    <target name="compile-cli" depends="compile-core">
        <compile-java
            src="src/cli"
            dest="${build.dir}/cli">
            <dependencies>
                <classpath refid="cli.classpath"/>
            </dependencies>
        </compile-java>
    </target>

    <target name="compile-all" depends="compile-cli">
        <echo message="All modules compiled"/>
    </target>

</project>
~~~

Luồng thực thi:

~~~text
clean (nếu được gọi riêng)
        |
        v
compile-core
        |
        v
compile-cli
        |
        v
compile-all
~~~

Target compile-cli phụ thuộc compile-core vì mã CLI cần lớp đã biên dịch của core. Macro chỉ chuẩn hóa thao tác javac; dependency giữa các giai đoạn vẫn được mô tả bằng depends của target.

Chạy build:

~~~bash
ant clean
ant compile-all
~~~

Có thể thêm module mới bằng một target gọi compile-java với src và dest tương ứng. Nếu module đó cần classpath, truyền element dependencies.

## 10. Kết hợp macrodef với file build dùng chung

Khi nhiều build file trong cùng dự án cần dùng một nhóm macro, bạn có thể đặt các định nghĩa vào một file XML riêng và nạp file đó bằng import.

Ví dụ cấu trúc:

~~~text
project/
├── build.xml
├── build/
│   └── macros.xml
└── src/
~~~

File build/macros.xml:

~~~xml
<project name="shared-macros">
    <macrodef name="ensure-dir">
        <attribute name="path"/>
        <sequential>
            <mkdir dir="@{path}"/>
        </sequential>
    </macrodef>

    <macrodef name="copy-resources">
        <attribute name="source"/>
        <attribute name="destination"/>
        <sequential>
            <mkdir dir="@{destination}"/>
            <copy todir="@{destination}">
                <fileset dir="@{source}"/>
            </copy>
        </sequential>
    </macrodef>
</project>
~~~

File build.xml chính:

~~~xml
<project name="application" default="prepare" basedir=".">
    <import file="build/macros.xml"/>

    <target name="prepare">
        <ensure-dir path="build/classes"/>
        <copy-resources
            source="src/main/resources"
            destination="build/resources"/>
    </target>
</project>
~~~

Import giúp nạp các định nghĩa macro và target từ file khác vào project hiện tại. Với thư viện macro dùng chung, nên đặt tên rõ nghĩa và tránh trùng tên task giữa các file được import.

Khi tách file, đường dẫn tương đối trong các task cần được xác định cẩn thận. Dùng property hoặc location phù hợp để build có thể chạy ổn định dù được gọi từ thư mục làm việc khác.

## 11. macrodef, presetdef và antcall khác nhau thế nào?

Ba cơ chế này đều giúp tái sử dụng cấu hình hoặc thao tác, nhưng giải quyết các vấn đề khác nhau.

| Cơ chế | Mục đích chính | Khi nên dùng |
|---|---|---|
| macrodef | Định nghĩa task mới gồm một chuỗi task, có tham số và element lồng. | Khi nhiều nơi cần thực hiện cùng một quy trình task. |
| presetdef | Tạo một phiên bản task có sẵn với một số thuộc tính hoặc cấu hình mặc định. | Khi chỉ cần chuẩn hóa cách cấu hình một task hiện có. |
| antcall | Gọi một target khác trong cùng build theo cơ chế gọi target của Ant. | Khi muốn thực thi một giai đoạn build đã được mô hình hóa thành target. |

Ví dụ presetdef:

~~~xml
<presetdef name="project-echo">
    <echo level="info" encoding="UTF-8"/>
</presetdef>

<target name="show">
    <project-echo message="Build started"/>
</target>
~~~

presetdef tạo một cấu hình đặt trước cho task echo. Nó không đóng gói chuỗi nhiều task như macrodef.

Ví dụ antcall:

~~~xml
<target name="prepare">
    <mkdir dir="build"/>
</target>

<target name="compile">
    <antcall target="prepare"/>
    <echo message="Compile sources"/>
</target>
~~~

Trong trường hợp chỉ cần gọi target phụ thuộc, dùng depends thường rõ ràng hơn antcall. Macrodef thích hợp khi muốn đóng gói một chuỗi thao tác nhỏ thành một task có tham số, để gọi lại tại nhiều vị trí.

## 12. Các giới hạn và lưu ý khi thiết kế macro

### 12.1. Macro không tạo phạm vi property riêng

Các task trong macro chạy trong project hiện tại. Property được đặt trong macro vẫn tuân theo quy tắc property của Ant, bao gồm nguyên tắc property thông thường chỉ được đặt một lần.

Không nên xem attribute của macro như biến cục bộ có thể ghi đè property toàn cục. Attribute chỉ là giá trị được thay vào nội dung macro khi gọi.

### 12.2. Tránh ID cố định có thể bị trùng

Nếu macro khai báo task có id cố định, nhiều lần gọi có thể tạo ra xung đột ID hoặc reference khó quản lý.

Ví dụ không nên lặp lại một ID cố định trong macro:

~~~xml
<macrodef name="create-path">
    <sequential>
        <path id="temporary.path">
            <pathelement location="build/classes"/>
        </path>
    </sequential>
</macrodef>
~~~

Nếu cần ID, hãy truyền ID qua attribute:

~~~xml
<macrodef name="create-path">
    <attribute name="path-id"/>
    <attribute name="location"/>
    <sequential>
        <path id="@{path-id}">
            <pathelement location="@{location}"/>
        </path>
    </sequential>
</macrodef>
~~~

Lời gọi:

~~~xml
<create-path path-id="core.path" location="build/core"/>
<create-path path-id="web.path" location="build/web"/>
~~~

Hãy bảo đảm mỗi ID được tạo là duy nhất trong project.

### 12.3. Không lạm dụng macro cho một thao tác đơn giản

Nếu chỉ cần gọi mkdir một lần, macro có thể khiến build file dài và khó theo dõi hơn. Macro có giá trị khi cùng một quy trình được sử dụng nhiều lần hoặc khi muốn cung cấp một giao diện ổn định cho các bước phức tạp.

### 12.4. Đặt tên attribute và element theo vai trò

Tên như arg1, arg2, item hoặc extra không giúp người đọc hiểu dữ liệu. Nên dùng tên có nghĩa như source, destination, classpath, compiler-options hoặc after-copy.

Tên element cũng nên thể hiện nhóm task được chèn vào. Ví dụ test-setup và test-cleanup dễ hiểu hơn task1 và task2.

### 12.5. Giữ macro ngắn và có một trách nhiệm rõ

Một macro vừa biên dịch, đóng gói, chạy test, triển khai và gửi thông báo sẽ khó tái sử dụng. Nên chia thành các macro nhỏ như compile-java, copy-resources, run-tests và package-jar. Target chịu trách nhiệm ghép chúng thành quy trình lớn.

### 12.6. Không thay thế dependency graph bằng các task lồng tùy tiện

Macro giúp tái sử dụng chuỗi task bên trong một target. Nó không thay thế mô hình dependency của Ant. Nếu compile-cli cần compile-core, hãy thể hiện điều đó bằng depends để người đọc thấy được thứ tự build.

## 13. Cách xây dựng macrodef dễ bảo trì

Khi cần trừu tượng hóa một nhóm task, có thể làm theo trình tự:

1. Tìm các đoạn task lặp lại và xác định phần nào giống nhau.
2. Tách các giá trị thay đổi thành attribute, ví dụ source, destination, encoding hoặc module.
3. Tách cấu hình XML linh hoạt thành element bắt buộc hoặc tùy chọn.
4. Dùng element implicit nếu macro chỉ cần bọc một nhóm task do nơi gọi cung cấp.
5. Dùng text khi đầu vào là văn bản thuần, không phải task XML.
6. Đặt giá trị default cho những tùy chọn phổ biến và an toàn.
7. Giữ logic theo thứ tự rõ ràng trong sequential.
8. Gọi macro từ target và giữ dependency giữa các target bằng depends.
9. Tránh ID cố định, tên chung chung và macro làm quá nhiều việc.
10. Nếu nhiều build file dùng chung macro, đặt định nghĩa vào file riêng và import một cách có tổ chức.

Khi thiết kế giao diện macro, hãy nghĩ về người sẽ gọi nó: họ cần truyền gì, có thể bỏ qua phần nào, và cần nhìn thấy những bước nào trong build file. Một macro tốt giúp lời gọi ngắn hơn nhưng vẫn thể hiện rõ ý định.

## 14. Ghi nhớ

- **macrodef** định nghĩa task mới từ một chuỗi task Ant.
- **attribute** truyền giá trị đơn; trong thân macro, dùng cú pháp @{name} để tham chiếu.
- **default** cung cấp giá trị mặc định cho attribute khi nơi gọi bỏ qua.
- **element** nhận task hoặc cấu trúc XML lồng; placeholder cùng tên được đặt trong phần thân macro.
- **optional="true"** cho phép bỏ qua element.
- **implicit="true"** nhận các task con trực tiếp của lời gọi macro.
- **text** nhận văn bản thuần và có thể dùng trim để bỏ khoảng trắng đầu/cuối.
- **doubleexpanding** điều khiển việc mở rộng property lần thứ hai đối với giá trị attribute.
- Macro chạy trong project hiện tại và không tạo phạm vi property riêng.
- Dùng **presetdef** để chuẩn hóa một task có sẵn, **antcall/depends** để điều phối target và **macrodef** để tái sử dụng chuỗi task.
- Macro nên có một trách nhiệm rõ, tên tham số có nghĩa và không tạo ID trùng lặp.

Với macrodef, bạn có thể biến các chuỗi task lặp lại thành những task có giao diện rõ ràng, giúp build file Apache Ant ngắn gọn hơn, nhất quán hơn và dễ thay đổi khi quy trình phát triển mở rộng.

