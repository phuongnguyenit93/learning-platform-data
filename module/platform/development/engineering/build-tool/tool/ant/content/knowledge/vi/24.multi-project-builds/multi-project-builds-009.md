# Tránh gọi lặp, vòng phụ thuộc và chia sẻ thư mục đầu ra

## Mục tiêu

Một dự án Ant có thể gồm nhiều target và nhiều buildfile con. Target biên dịch có thể được dùng lại bởi target kiểm thử và đóng gói; module giao diện có thể phụ thuộc module lõi; nhiều module có thể cùng đọc thư viện bên thứ ba. Nếu quan hệ giữa các bước không được tổ chức rõ ràng, build dễ gọi lại cùng công việc nhiều lần, tạo vòng phụ thuộc hoặc ghi đè tệp của module khác.

Ba vấn đề này thường liên quan nhưng có nguyên nhân khác nhau:

- **Gọi lặp** xảy ra khi cùng một bước bị thực thi nhiều lần trong một lần build hoặc qua nhiều build invocation.
- **Vòng phụ thuộc** xảy ra khi target hoặc module phụ thuộc ngược trở lại chính nó thông qua một chuỗi quan hệ.
- **Chia sẻ thư mục đầu ra** xảy ra khi nhiều module cùng ghi class file, report, file sinh tự động hoặc artifact vào một vị trí.

Muốn build ổn định, hãy mô hình hóa thứ tự bằng dependency rõ ràng, chia project theo ranh giới hợp lý và cấp thư mục đầu ra riêng cho từng module. Những phần thực sự dùng chung như thư viện đầu vào hoặc cấu hình bất biến có thể được chia sẻ; các tệp do từng module tạo ra cần có chủ sở hữu rõ ràng.

## 1. Hiểu đồ thị target của Ant

### 1.1. Target và quan hệ depends

Một target có thể khai báo các target phải chạy trước bằng thuộc tính depends:

~~~xml
<target name="init">
    <mkdir dir="build"/>
</target>

<target name="compile" depends="init">
    <javac srcdir="src"
           destdir="build/classes"
           includeantruntime="false"/>
</target>

<target name="test" depends="compile">
    <!-- Chạy test sau khi biên dịch -->
</target>

<target name="package" depends="compile">
    <!-- Đóng gói sau khi biên dịch -->
</target>
~~~

Khi chạy target test, Ant thực hiện init trước compile rồi mới đến test. Khi chạy package, Ant cũng cần init và compile trước package.

Có thể hình dung quan hệ này như một đồ thị có hướng:

~~~text
init
  |
compile
 /     \
test   package
~~~

Mũi tên biểu diễn quan hệ phụ thuộc: target ở phía sau cần target phía trước hoàn tất trước khi bắt đầu.

### 1.2. Ant thực hiện dependency theo thứ tự nào?

Ant duyệt quan hệ depends theo thứ tự được khai báo trong danh sách và thực hiện các target phụ thuộc trước target được yêu cầu. Không nên dựa vào vị trí target trong file build.xml để suy ra thứ tự chạy.

Ví dụ:

~~~xml
<target name="verify" depends="compile,test,package"/>
~~~

Danh sách trên mô tả thứ tự phụ thuộc của verify. Nếu test cũng phụ thuộc compile, Ant nhận ra compile đã được thực hiện trong cùng project invocation và không chạy lại target đó lần thứ hai.

Điều này giúp xây dựng target tổng hợp mà không cần gọi thủ công từng target bằng antcall.

### 1.3. Một target chỉ chạy một lần trong một project invocation

Trong một lần thực thi project Ant, một target được thực hiện tối đa một lần theo cơ chế dependency thông thường, kể cả khi nhiều nhánh trong đồ thị cùng phụ thuộc target đó.

Ví dụ:

~~~xml
<target name="compile-main">
    <echo message="Compile main sources"/>
</target>

<target name="test" depends="compile-main">
    <echo message="Run tests"/>
</target>

<target name="package" depends="compile-main">
    <echo message="Create archive"/>
</target>

<target name="verify" depends="test,package">
    <echo message="Verification completed"/>
</target>
~~~

Khi chạy:

~~~text
ant verify
~~~

compile-main chỉ chạy một lần. Sau đó Ant lần lượt xử lý các nhánh test và package rồi chạy verify.

Đây là lý do nên mô tả quan hệ giữa các bước bằng depends thay vì tự gọi target đã có trong nhiều nơi.

## 2. Tránh gọi lặp bằng depends

### 2.1. Không dùng antcall để thay thế dependency thông thường

Task antcall gọi một target khác trong cùng buildfile, nhưng target được gọi chạy trong một project context mới. Vì vậy, antcall có thể làm một phần công việc đã chạy ở project cha được thực hiện lại trong context con.

Ví dụ không nên dùng:

~~~xml
<target name="compile">
    <javac srcdir="src"
           destdir="build/classes"
           includeantruntime="false"/>
</target>

<target name="test">
    <antcall target="compile"/>
    <echo message="Run tests"/>
</target>

<target name="package">
    <antcall target="compile"/>
    <echo message="Create archive"/>
</target>
~~~

Nếu build cần chạy test rồi package, các lần gọi antcall có thể biên dịch lại cùng nguồn. Ngoài chi phí thời gian, cách này làm cho luồng thực thi khó theo dõi hơn.

Nên khai báo:

~~~xml
<target name="compile">
    <javac srcdir="src"
           destdir="build/classes"
           includeantruntime="false"/>
</target>

<target name="test" depends="compile">
    <echo message="Run tests"/>
</target>

<target name="package" depends="compile">
    <echo message="Create archive"/>
</target>

<target name="verify" depends="test,package"/>
~~~

Ant tự xây dựng thứ tự và tránh thực hiện lại compile trong cùng project invocation.

### 2.2. Khi nào antcall có ích?

Antcall không phải lúc nào cũng sai. Nó có thể hữu ích khi cần chạy lại một target trong project context riêng với bộ parameter khác nhau.

Ví dụ, một target dùng property environment để thực hiện một bước có tham số:

~~~xml
<target name="publish-one">
    <echo message="Publishing to environment: ${release.environment}"/>
</target>

<target name="publish-staging">
    <antcall target="publish-one">
        <param name="release.environment" value="staging"/>
    </antcall>
</target>
~~~

Tuy nhiên, nếu cần thực hiện cùng một chuỗi task cho nhiều module hoặc nhiều bộ tham số, macrodef thường phù hợp hơn. Nếu cần gọi buildfile con, dùng ant hoặc subant.

Antcall tạo project context mới, do đó property, reference và các dependency cần được hiểu theo phạm vi của lần gọi. Không dùng antcall chỉ để tạo một cách viết khác cho depends.

### 2.3. Tái sử dụng chuỗi task bằng macrodef

Macrodef định nghĩa một nhóm task có tham số. Khi gọi macro, Ant thực hiện chuỗi task đó trong project hiện tại, không cần gọi lại target bằng project context mới.

~~~xml
<macrodef name="compile-module">
    <attribute name="source"/>
    <attribute name="output"/>

    <sequential>
        <mkdir dir="@{output}"/>
        <javac srcdir="@{source}"
               destdir="@{output}"
               includeantruntime="false"/>
    </sequential>
</macrodef>

<target name="compile-modules">
    <compile-module source="modules/core/src"
                    output="build/modules/core/classes"/>
    <compile-module source="modules/reporting/src"
                    output="build/modules/reporting/classes"/>
</target>
~~~

Macro có thể nhận các attribute khác nhau cho mỗi lần gọi. Trong ví dụ, hai module dùng chung logic compile nhưng ghi ra hai thư mục riêng.

Macrodef phù hợp khi:

- Nhiều module lặp lại cùng cấu trúc task.
- Khác biệt giữa các lần gọi chỉ là giá trị đầu vào.
- Muốn giữ các bước trong cùng một project context.
- Không cần một buildfile con độc lập.

Nếu các module có dependency phức tạp, target riêng cho từng module vẫn giúp thể hiện thứ tự rõ hơn.

## 3. Tránh vòng phụ thuộc giữa các target

### 3.1. Vòng phụ thuộc trực tiếp

Ví dụ sai:

~~~xml
<target name="compile" depends="test"/>
<target name="test" depends="compile"/>
~~~

compile yêu cầu test chạy trước, trong khi test lại yêu cầu compile chạy trước. Không có thứ tự hợp lệ để bắt đầu.

Ant phát hiện vòng phụ thuộc khi xây dựng thứ tự target và báo lỗi circular dependency. Build không thể tiếp tục theo đồ thị này.

### 3.2. Vòng phụ thuộc gián tiếp

Vòng có thể dài hơn hai target:

~~~xml
<target name="prepare" depends="generate"/>
<target name="generate" depends="compile"/>
<target name="compile" depends="prepare"/>
~~~

Quan hệ là:

~~~text
prepare -> generate -> compile -> prepare
~~~

Dù không có target nào phụ thuộc trực tiếp vào chính nó, chuỗi cuối cùng vẫn quay lại điểm bắt đầu. Đây vẫn là vòng phụ thuộc.

Khi gặp lỗi circular dependency, hãy lần theo toàn bộ chuỗi depends để tìm cạnh tạo vòng. Không chỉ sửa target cuối cùng được nhắc trong thông báo; cần điều chỉnh mô hình phụ thuộc.

### 3.3. Tách bước dùng chung để phá vòng

Giả sử compile cần source đã generate, còn generate lại cần một lớp công cụ đã compile. Nếu cả hai đều nằm trong target compile và generate, chúng có thể tạo vòng.

Hãy tách phần công cụ thành target riêng:

~~~xml
<target name="compile-generator">
    <javac srcdir="tools/generator"
           destdir="build/generator-classes"
           includeantruntime="false"/>
</target>

<target name="generate" depends="compile-generator">
    <java classname="com.example.Generator"
          fork="true"
          failonerror="true">
        <classpath>
            <pathelement location="build/generator-classes"/>
        </classpath>
    </java>
</target>

<target name="compile-app" depends="generate">
    <javac srcdir="src"
           destdir="build/classes"
           includeantruntime="false"/>
</target>
~~~

Luồng mới:

~~~text
compile-generator
       |
    generate
       |
  compile-app
~~~

Cách tách này làm rõ rằng generator là công cụ build, còn ứng dụng là sản phẩm được tạo ra sau bước generate.

### 3.4. Không tạo vòng runtime bằng antcall

Vòng depends được Ant phát hiện trước khi thực thi. Nhưng việc một target gọi lại chính nó qua antcall là vòng điều khiển lúc runtime:

~~~xml
<target name="publish">
    <antcall target="publish"/>
</target>
~~~

Mỗi lần gọi lại tạo thêm một lần thực thi target trong project context mới. Nó có thể tiếp tục đệ quy cho đến khi gặp lỗi hoặc cạn tài nguyên.

Không dùng antcall để lặp. Với danh sách giá trị hữu hạn, hãy dùng macrodef hoặc task phù hợp với resource collection. Với nhiều buildfile con, hãy dùng subant hoặc ant cùng một danh sách module được xác định rõ.

## 4. Mô hình dependency giữa nhiều module

### 4.1. Biểu diễn dependency thực tế

Giả sử ứng dụng có ba module:

- core chứa mô hình và logic dùng chung.
- service phụ thuộc core.
- web phụ thuộc service và core.

Đồ thị module:

~~~text
core
  |
service
  |
web
~~~

Nếu web cũng tham chiếu trực tiếp core, dependency có thể được mô tả như sau:

~~~text
core -----> service -----> web
  ______________________/
~~~

Build phải biên dịch core trước service và biên dịch service trước web. Không nên để mỗi buildfile tự đoán thứ tự bằng cách quét thư mục module.

### 4.2. Khai báo thứ tự ở project điều phối

Buildfile gốc có thể điều phối từng module bằng task ant:

~~~xml
<project name="application" default="compile-all" basedir=".">
    <property name="root.dir" location="."/>

    <target name="compile-core">
        <ant dir="modules/core"
             antfile="build.xml"
             target="compile"
             inheritall="false"/>
    </target>

    <target name="compile-service" depends="compile-core">
        <ant dir="modules/service"
             antfile="build.xml"
             target="compile"
             inheritall="false">
            <property name="core.classes"
                      value="${root.dir}/modules/core/build/classes"/>
        </ant>
    </target>

    <target name="compile-web" depends="compile-service">
        <ant dir="modules/web"
             antfile="build.xml"
             target="compile"
             inheritall="false">
            <property name="core.classes"
                      value="${root.dir}/modules/core/build/classes"/>
            <property name="service.classes"
                      value="${root.dir}/modules/service/build/classes"/>
        </ant>
    </target>

    <target name="compile-all" depends="compile-web"/>
</project>
~~~

Các target trong project gốc mô tả thứ tự dependency. Mỗi task ant chạy buildfile của module trong project context riêng.

Ở đây, compile-service phụ thuộc compile-core; compile-web phụ thuộc compile-service. Khi chạy compile-all, Ant thực hiện các module theo đúng chuỗi đó.

### 4.3. Buildfile của module con

Ví dụ buildfile của module service:

~~~xml
<project name="service" default="compile" basedir=".">
    <property name="classes.dir" location="build/classes"/>
    <property name="core.classes" value=""/>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>

        <javac srcdir="src"
               destdir="${classes.dir}"
               includeantruntime="false">
            <classpath>
                <pathelement location="${core.classes}"/>
            </classpath>
        </javac>
    </target>
</project>
~~~

Property core.classes được project gốc truyền vào qua phần tử property lồng trong task ant. Buildfile con không cần biết module core nằm ở đâu trong repository; nó chỉ cần nhận đường dẫn dependency.

Nếu module không có dependency đó, không cần khai báo property hoặc classpath tương ứng.

### 4.4. Dùng subant cho nhiều buildfile cùng loại

Khi cần chạy cùng một target trên nhiều project con độc lập, task subant có thể lặp qua một buildpath:

~~~xml
<target name="compile-independent-modules">
    <subant target="compile"
            failonerror="true"
            inheritall="false">
        <buildpath>
            <fileset dir="modules">
                <include name="commons/build.xml"/>
                <include name="reporting/build.xml"/>
                <include name="notifications/build.xml"/>
            </fileset>
        </buildpath>

        <property name="release.version" value="${release.version}"/>
    </subant>
</target>
~~~

Subant gọi target compile trong từng buildfile được tìm thấy qua buildpath. Ví dụ chỉ phù hợp khi các module được liệt kê có thể biên dịch độc lập hoặc dependency của chúng đã sẵn sàng.

Nếu module B cần output của module A, không nên dựa vào thứ tự file trong fileset để thể hiện dependency. Hãy tạo target điều phối riêng và khai báo depends rõ ràng.

### 4.5. Chọn ant hay subant?

| Nhu cầu | Cách phù hợp |
|---|---|
| Gọi một buildfile con cụ thể | ant |
| Gọi cùng một target trên một tập buildfile | subant |
| Thể hiện thứ tự giữa các target trong cùng project | depends |
| Tái sử dụng một chuỗi task có tham số | macrodef |
| Gọi target khác trong cùng buildfile với context riêng | antcall, khi thực sự cần |
| Chia sẻ cấu hình build chung giữa các file trong cùng project | import hoặc include, tùy cấu trúc |

## 5. Kiểm soát property và reference giữa các project

### 5.1. Property không tự chảy ngược từ project con về project cha

Task ant và subant tạo project context cho buildfile con. Property được tạo trong project con không tự động trở thành property của project cha.

Ví dụ, nếu child buildfile tạo:

~~~xml
<property name="compiled.module.path"
          location="build/classes"/>
~~~

Project gốc không thể mặc nhiên đọc được property compiled.module.path sau khi child build kết thúc.

Nếu cần truyền thông tin từ child về parent, hãy dùng artifact hoặc metadata file được ghi vào một vị trí đã quy ước, rồi để parent đọc lại bằng task phù hợp. Không thiết kế luồng điều phối dựa vào giả định property của child sẽ quay trở lại parent.

### 5.2. Kiểm soát inheritAll

Task ant và subant có thuộc tính inheritAll để điều khiển việc truyền property từ project cha sang project con. Giá trị mặc định của Ant task là true.

Nếu để mặc định, các property từ parent có thể ảnh hưởng đến giá trị mặc định mà child buildfile định nghĩa. Điều này có thể gây lỗi khi nhiều module cùng dùng tên property như build.dir, classes.dir hoặc output.dir.

Ví dụ rủi ro:

~~~xml
<property name="build.dir" location="build"/>

<target name="compile-core">
    <ant dir="modules/core" target="compile"/>
</target>

<target name="compile-web">
    <ant dir="modules/web" target="compile"/>
</target>
~~~

Nếu build.dir của parent được truyền sang child, cả hai module có thể nhận cùng đường dẫn output thay vì mỗi module dùng thư mục build riêng theo basedir của nó.

Có thể giảm việc kế thừa ngầm bằng:

~~~xml
<ant dir="modules/core"
     target="compile"
     inheritall="false"/>
~~~

Khi đặt inheritAll=false, hãy truyền tường minh các property mà child thực sự cần:

~~~xml
<ant dir="modules/web"
     target="compile"
     inheritall="false">
    <property name="release.version" value="${release.version}"/>
    <property name="core.classes"
              value="${root.dir}/modules/core/build/classes"/>
</ant>
~~~

Các property do dòng lệnh cung cấp và các property được truyền tường minh cần được xem xét theo quy tắc kế thừa của Ant. Đừng dựa vào việc child sẽ nhận mọi property nếu buildfile đã chủ động tắt inheritAll.

### 5.3. Property của Ant là bất biến

Property của Ant chỉ được thiết lập một lần. Khi một property đã có giá trị, khai báo sau với cùng tên không ghi đè giá trị cũ.

Điều này có thể gây nhầm lẫn nếu cùng một project cố đặt build.dir khác nhau cho từng module:

~~~xml
<property name="build.dir" value="build/core"/>
<property name="build.dir" value="build/web"/>
~~~

Dòng thứ hai không thay giá trị đã được thiết lập bởi dòng đầu. Không thể dùng property thông thường như biến vòng lặp để thay đổi output directory liên tục.

Giải pháp:

- Dùng property có tên riêng cho từng module, chẳng hạn core.build.dir và web.build.dir.
- Dùng macrodef với attribute cho các bước lặp.
- Dùng buildfile con với basedir và property cục bộ riêng.
- Chạy các module trong project context riêng qua ant hoặc subant.

### 5.4. Reference không giống property

Path, FileSet và một số đối tượng Ant có thể được đăng ký thành reference bằng ID. Việc kế thừa reference giữa các project được điều khiển riêng với property.

Task ant và subant có thuộc tính inheritRefs; mặc định không tự kế thừa toàn bộ reference của parent. Khi cần dùng chung classpath hoặc resource collection, có thể khai báo lại trong child hoặc truyền reference theo cơ chế Ant hỗ trợ.

Với nhiều module, khai báo Path trong từng buildfile con thường dễ hiểu hơn việc chia sẻ một reference có phạm vi toàn project. Nó giúp mỗi module mô tả rõ dependency thực tế của chính nó.

## 6. Chia sẻ thư mục đầu ra an toàn

### 6.1. Vì sao không nên dùng chung build/classes?

Giả sử hai module cùng ghi vào:

~~~text
build/classes/
~~~

Module core tạo com/example/Config.class, còn module web cũng có lớp cùng đường dẫn. Nếu cả hai ghi vào một thư mục, lớp có thể bị ghi đè hoặc bị trộn lẫn. Sau đó, classpath không còn thể hiện rõ lớp nào thuộc module nào.

Các đầu ra khác cũng có thể va chạm:

- Test report có tên trùng nhau.
- Tệp sinh tự động có cùng tên.
- Tệp resource được copy với cùng đường dẫn tương đối.
- JAR output dùng chung tên.
- File stamp hoặc cache incremental bị module khác thay đổi.

Mỗi module nên sở hữu một thư mục build riêng.

### 6.2. Quy ước output theo module

Ví dụ cấu trúc:

~~~text
project/
├── build.xml
├── modules/
│   ├── core/
│   │   ├── build.xml
│   │   └── build/
│   │       ├── classes/
│   │       ├── test-classes/
│   │       ├── reports/
│   │       └── generated/
│   ├── service/
│   │   ├── build.xml
│   │   └── build/
│   │       ├── classes/
│   │       ├── test-classes/
│   │       ├── reports/
│   │       └── generated/
│   └── web/
│       ├── build.xml
│       └── build/
│           ├── classes/
│           ├── test-classes/
│           ├── reports/
│           └── generated/
└── dist/
~~~

Các module có thể cùng dùng tên tương đối build/classes vì basedir của mỗi child project khác nhau. Đường dẫn vật lý thực tế vẫn tách biệt.

### 6.3. Định nghĩa output dựa trên basedir của module

Trong buildfile của từng module:

~~~xml
<project name="core" default="compile" basedir=".">
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="test.classes.dir" location="${build.dir}/test-classes"/>
    <property name="reports.dir" location="${build.dir}/reports"/>
    <property name="generated.dir" location="${build.dir}/generated"/>

    <target name="prepare">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${test.classes.dir}"/>
        <mkdir dir="${reports.dir}"/>
        <mkdir dir="${generated.dir}"/>
    </target>
</project>
~~~

Khi Ant chạy buildfile này với basedir là modules/core, các output được tạo trong modules/core/build. Buildfile service có cùng cấu trúc nhưng output nằm trong modules/service/build.

Không cần đặt tên property khác nhau trong từng module nếu mỗi module chạy trong project context riêng và không nhận một property build.dir dùng chung từ parent.

### 6.4. Tách output của compile, test và report

Một module nên tách ít nhất:

| Thư mục | Nội dung |
|---|---|
| build/classes | Lớp production đã biên dịch |
| build/test-classes | Lớp kiểm thử đã biên dịch |
| build/generated | Mã nguồn hoặc tài nguyên được sinh |
| build/reports | Test report, coverage report hoặc log có cấu trúc |
| build/tmp | Tệp trung gian |
| dist | Artifact sẵn sàng phân phối, nếu module sở hữu bản phát hành riêng |

Tách các thư mục giúp clean, incremental build và kiểm tra artifact chính xác hơn.

### 6.5. Thư mục dùng chung chỉ nên chứa đầu vào hoặc kết quả tổng hợp

Một số dữ liệu có thể dùng chung an toàn:

- Thư viện bên thứ ba chỉ đọc.
- File cấu hình chung không bị sửa trong lúc build.
- Script hoặc template dùng để sinh mã.
- Artifact đầu ra đã hoàn thành và được module khác đọc.

Nếu cần tổng hợp output, hãy để từng module ghi vào thư mục riêng rồi copy hoặc assemble kết quả vào thư mục tổng hợp:

~~~xml
<target name="assemble-distribution" depends="compile-core,compile-service,compile-web">
    <mkdir dir="dist/lib"/>

    <copy file="modules/core/build/core.jar" todir="dist/lib"/>
    <copy file="modules/service/build/service.jar" todir="dist/lib"/>
    <copy file="modules/web/build/web.jar" todir="dist/lib"/>
</target>
~~~

Thư mục dist là output của target tổng hợp. Các module không nên đồng thời ghi trực tiếp vào dist nếu chúng có thể tạo tên tệp trùng hoặc chạy song song.

## 7. Clean và quản lý output cũ

### 7.1. Clean chỉ xóa output do module sở hữu

Trong mỗi module:

~~~xml
<target name="clean">
    <delete dir="${build.dir}"/>
</target>
~~~

Target clean chỉ xóa thư mục build của module hiện tại. Không để clean của module con xóa thư mục build chung của repository nếu các module khác cũng lưu output ở đó.

Project gốc có thể điều phối clean:

~~~xml
<target name="clean-core">
    <ant dir="modules/core" target="clean" inheritall="false"/>
</target>

<target name="clean-service" depends="clean-core">
    <ant dir="modules/service" target="clean" inheritall="false"/>
</target>

<target name="clean-web" depends="clean-service">
    <ant dir="modules/web" target="clean" inheritall="false"/>
</target>

<target name="clean-all" depends="clean-web">
    <delete dir="dist"/>
</target>
~~~

Ở đây, mỗi module xóa output riêng; project gốc xóa thư mục phân phối tổng hợp sau khi các module đã clean.

Nếu module không phụ thuộc nhau, các target clean có thể được tổ chức đơn giản hơn. Không chạy clean song song với compile hoặc test trên cùng một thư mục.

### 7.2. Không để output cũ che lỗi dependency

Nếu build chỉ copy các file mới mà không xóa class cũ, thư mục output có thể còn những lớp không còn trong source. Một lần chạy sau có thể biên dịch thành công vì lớp cũ vẫn tồn tại, dù dependency hoặc source hiện tại không còn đúng.

Với build có cấu trúc output rõ ràng, clean có thể xóa output riêng của module trước khi build lại. Với incremental build, hãy bảo đảm task quản lý đúng các tệp đã bị xóa hoặc đổi tên.

Không dùng một thư mục classes dùng chung lâu dài cho nhiều module rồi dựa vào clean thủ công để sửa mọi va chạm.

### 7.3. Tránh clean nhầm thư mục

Đường dẫn output nên được chuẩn hóa và kiểm soát. Tránh property build.dir trỏ đến thư mục gốc của repository hoặc thư mục chứa source.

Ví dụ an toàn hơn:

~~~xml
<property name="build.dir" location="build"/>
<target name="clean">
    <delete dir="${build.dir}"/>
</target>
~~~

Không đặt build.dir thành "." hoặc thư mục cha chứa source, vì delete có thể xóa dữ liệu ngoài phạm vi output của module.

## 8. Build song song và tranh chấp output

Một số quy trình có thể chạy module độc lập song song để rút ngắn thời gian. Tuy nhiên, chỉ nên làm khi dependency và output được cô lập.

Trước khi bật chạy song song, hãy xác nhận:

- Các module không cần output của nhau trong cùng giai đoạn.
- Mỗi module có classes, reports, generated và tmp riêng.
- Không có hai task ghi cùng một artifact hoặc file manifest.
- Không có target clean chạy đồng thời với compile.
- Cache hoặc thư mục dùng chung có cơ chế đồng bộ thích hợp.
- Các task không sửa một resource đầu vào dùng chung.

Nếu hai module cùng ghi build/classes, chạy tuần tự cũng có thể gây lỗi; chạy song song làm vấn đề khó tái hiện hơn.

Với subant, có thể bật thuộc tính parallel trong các trường hợp các buildfile độc lập. Không bật chỉ vì muốn build nhanh. Hãy thiết kế dependency và thư mục output trước, sau đó mới cân nhắc song song.

Ví dụ tổ chức subant cho các module độc lập:

~~~xml
<subant target="compile"
        parallel="true"
        failonerror="true"
        inheritall="false">
    <buildpath>
        <fileset dir="modules">
            <include name="commons/build.xml"/>
            <include name="reporting/build.xml"/>
            <include name="notifications/build.xml"/>
        </fileset>
    </buildpath>
</subant>
~~~

Ví dụ chỉ an toàn nếu các module không cần output của nhau và mỗi module tự quản lý output riêng. Nếu reporting phụ thuộc commons, hãy biên dịch commons trước bằng target riêng rồi mới chạy phần song song còn lại.

## 9. Tổ chức một build nhiều module hoàn chỉnh

Ví dụ sau cho thấy project gốc điều phối ba module có dependency theo thứ tự và mỗi module giữ output riêng.

### 9.1. Cấu trúc thư mục

~~~text
project/
├── build.xml
├── modules/
│   ├── core/
│   │   ├── build.xml
│   │   └── src/
│   ├── service/
│   │   ├── build.xml
│   │   └── src/
│   └── web/
│       ├── build.xml
│       └── src/
└── dist/
~~~

### 9.2. Buildfile của module core

~~~xml
<project name="core" default="compile" basedir=".">
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="src"
               destdir="${classes.dir}"
               includeantruntime="false"/>
        <jar destfile="${build.dir}/core.jar"
             basedir="${classes.dir}"/>
    </target>

    <target name="clean">
        <delete dir="${build.dir}"/>
    </target>
</project>
~~~

### 9.3. Buildfile của module service

~~~xml
<project name="service" default="compile" basedir=".">
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="core.classes" value=""/>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="src"
               destdir="${classes.dir}"
               includeantruntime="false">
            <classpath>
                <pathelement location="${core.classes}"/>
            </classpath>
        </javac>
        <jar destfile="${build.dir}/service.jar"
             basedir="${classes.dir}"/>
    </target>

    <target name="clean">
        <delete dir="${build.dir}"/>
    </target>
</project>
~~~

### 9.4. Buildfile của module web

~~~xml
<project name="web" default="compile" basedir=".">
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="core.classes" value=""/>
    <property name="service.classes" value=""/>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="src"
               destdir="${classes.dir}"
               includeantruntime="false">
            <classpath>
                <pathelement location="${core.classes}"/>
                <pathelement location="${service.classes}"/>
            </classpath>
        </javac>
        <jar destfile="${build.dir}/web.jar"
             basedir="${classes.dir}"/>
    </target>

    <target name="clean">
        <delete dir="${build.dir}"/>
    </target>
</project>
~~~

### 9.5. Buildfile điều phối ở thư mục gốc

~~~xml
<project name="multi-module" default="package" basedir=".">
    <property name="root.dir" location="."/>

    <target name="compile-core">
        <ant dir="modules/core"
             antfile="build.xml"
             target="compile"
             inheritall="false"/>
    </target>

    <target name="compile-service" depends="compile-core">
        <ant dir="modules/service"
             antfile="build.xml"
             target="compile"
             inheritall="false">
            <property name="core.classes"
                      value="${root.dir}/modules/core/build/classes"/>
        </ant>
    </target>

    <target name="compile-web" depends="compile-service">
        <ant dir="modules/web"
             antfile="build.xml"
             target="compile"
             inheritall="false">
            <property name="core.classes"
                      value="${root.dir}/modules/core/build/classes"/>
            <property name="service.classes"
                      value="${root.dir}/modules/service/build/classes"/>
        </ant>
    </target>

    <target name="package" depends="compile-web">
        <mkdir dir="dist"/>
        <copy file="modules/core/build/core.jar" todir="dist"/>
        <copy file="modules/service/build/service.jar" todir="dist"/>
        <copy file="modules/web/build/web.jar" todir="dist"/>
    </target>

    <target name="clean-core">
        <ant dir="modules/core" target="clean" inheritall="false"/>
    </target>

    <target name="clean-service" depends="clean-core">
        <ant dir="modules/service" target="clean" inheritall="false"/>
    </target>

    <target name="clean-web" depends="clean-service">
        <ant dir="modules/web" target="clean" inheritall="false"/>
    </target>

    <target name="clean" depends="clean-web">
        <delete dir="dist"/>
    </target>
</project>
~~~

Chạy:

~~~text
ant package
~~~

Project gốc điều phối compile-core, compile-service và compile-web theo quan hệ depends. Mỗi child project có basedir riêng nên property build.dir trỏ đến thư mục build của module tương ứng. Các JAR cuối cùng được copy vào dist sau khi mọi module đã biên dịch.

Ví dụ dùng thư mục classes của module dependency làm classpath. Nếu module cần dùng artifact JAR thay vì class file trực tiếp, hãy truyền đường dẫn JAR tương ứng và bảo đảm task compile chạy sau khi artifact đó được tạo.

## 10. Cách chọn công cụ điều phối

| Tình huống | Cách nên dùng | Lý do |
|---|---|---|
| Target cần một target khác chạy trước | depends | Ant quản lý thứ tự và tránh gọi lại trong cùng project |
| Nhiều nhánh cùng cần compile | Cùng depends vào compile | Target compile được thực hiện một lần trong project invocation |
| Cùng chuỗi task lặp với nhiều đường dẫn | macrodef | Tham số hóa logic mà không tạo project context mới |
| Gọi buildfile con một lần | ant | Mỗi module có project và basedir riêng |
| Gọi cùng target trên tập buildfile | subant | Lặp theo buildpath đã khai báo |
| Chạy lại target với property context khác | antcall, có chủ đích | Tạo lần thực thi target riêng; cần chú ý dependency lặp |
| Module có dependency giữa nhau | Target điều phối với depends | Thứ tự module được biểu diễn rõ |
| Nhiều module tạo output | Output riêng theo basedir/module | Tránh ghi đè class, report và artifact |

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Compile chạy nhiều lần | Dùng antcall ở nhiều target để gọi compile | Đưa compile vào depends chung |
| Target bị gọi đệ quy | antcall quay lại target hiện tại hoặc chuỗi target tạo vòng | Xóa vòng gọi, dùng depends hoặc macrodef |
| Ant báo circular dependency | Đồ thị depends có chu trình trực tiếp hoặc gián tiếp | Vẽ lại quan hệ và tách target dùng chung |
| Module chạy sai thứ tự | Dựa vào thứ tự quét thư mục hoặc vị trí target trong XML | Khai báo dependency rõ trong project gốc |
| Module dùng nhầm build.dir | Parent truyền property cùng tên xuống child | Dùng inheritAll=false và truyền property cần thiết |
| Child không nhận property cần thiết | Đã tắt inheritAll nhưng quên truyền property | Thêm nested property trong ant/subant |
| Parent không đọc được property child tạo | Nhầm phạm vi property giữa hai project | Ghi metadata/artifact ra file rồi đọc lại |
| Path hoặc reference không tồn tại trong child | Reference không được kế thừa | Khai báo Path trong child hoặc truyền reference có chủ đích |
| Class file bị ghi đè | Nhiều module dùng chung destdir | Tách classes.dir theo module |
| Test report bị trùng | Nhiều module ghi cùng tên report vào một thư mục | Dùng reports dir riêng hoặc tên report có module prefix |
| Clean xóa nhầm output module khác | Clean dùng chung build.dir | Mỗi module chỉ clean thư mục nó sở hữu |
| Build song song lúc được lúc lỗi | Hai task ghi cùng file hoặc phụ thuộc output chưa hoàn tất | Cô lập output và khai báo dependency trước khi bật parallel |
| Build thành công nhưng dùng class cũ | Output còn tệp từ lần build trước | Clean output riêng hoặc quản lý incremental build đúng cách |

## 12. Thực hành tốt

- Mô hình hóa target và module thành đồ thị dependency có hướng, không có chu trình.
- Dùng depends để biểu diễn thứ tự trong cùng một project.
- Không gọi target biên dịch nhiều lần bằng antcall nếu dependency thông thường đã đủ.
- Dùng macrodef để tái sử dụng chuỗi task có tham số.
- Dùng ant khi gọi một buildfile con và subant khi lặp qua nhiều buildfile.
- Không dựa vào thứ tự quét thư mục để thể hiện dependency giữa module.
- Đặt inheritAll=false khi muốn tránh property của parent vô tình ghi đè cấu hình cục bộ của child.
- Truyền tường minh property mà module con thực sự cần.
- Nhớ rằng property của Ant là bất biến và property của child không tự trả về parent.
- Mỗi module sở hữu thư mục classes, test-classes, generated, reports và tmp riêng.
- Chỉ chia sẻ đầu vào hoặc thư viện đọc chung; không để nhiều module ghi cùng output.
- Tạo thư mục tổng hợp như dist ở project gốc sau khi các module đã hoàn tất.
- Clean đúng thư mục do module sở hữu.
- Chỉ chạy song song khi module độc lập và output không va chạm.
- Dùng tên artifact có module và phiên bản để tránh ghi đè khi tổng hợp.

## 13. Tự kiểm tra kiến trúc build nhiều dự án

Trước khi đưa build nhiều module vào CI, hãy tự trả lời:

1. Target nào là điểm bắt đầu và target nào là bước cuối?
2. Quan hệ depends có tạo thành đồ thị không chu trình không?
3. Có target nào bị gọi lại qua antcall dù có thể dùng depends không?
4. Có chuỗi antcall nào có thể gọi ngược về target ban đầu không?
5. Các module phụ thuộc nhau theo thứ tự nào?
6. Project gốc có thể hiện dependency module bằng target riêng không?
7. Module độc lập có thể được gom bằng subant không?
8. Các property cần truyền cho child đã được khai báo rõ chưa?
9. inheritAll có làm property build.dir hoặc output.dir của parent lấn át child không?
10. Child có đang mong property hoặc reference tự quay về parent không?
11. Mỗi module có thư mục output riêng cho class, test, report và generated file không?
12. Target clean chỉ xóa output mà module sở hữu không?
13. Có task song song nào cùng ghi vào một thư mục hoặc tệp không?
14. Thư mục tổng hợp chỉ nhận artifact sau khi các module hoàn tất không?
15. Có thể chạy lại build từ workspace sạch mà không phụ thuộc output cũ không?

Khi dùng depends cho quan hệ trong project, ant hoặc subant cho ranh giới giữa các buildfile, và thư mục output riêng cho từng module, build nhiều dự án sẽ dễ hiểu hơn. Việc tách đúng phạm vi cũng giúp phát hiện sớm vòng phụ thuộc, tránh chạy lại công việc không cần thiết và ngăn các module ghi đè kết quả của nhau.

## Tài liệu tham khảo

- [Apache Ant — Targets and depends](https://ant.apache.org/manual/targets.html)
- [Apache Ant — Ant Task](https://ant.apache.org/manual/Tasks/ant.html)
- [Apache Ant — Subant Task](https://ant.apache.org/manual/Tasks/subant.html)
- [Apache Ant — AntCall Task](https://ant.apache.org/manual/Tasks/antcall.html)
- [Apache Ant — MacroDef Task](https://ant.apache.org/manual/Tasks/macrodef.html)
- [Apache Ant — Property Task](https://ant.apache.org/manual/Tasks/property.html)

