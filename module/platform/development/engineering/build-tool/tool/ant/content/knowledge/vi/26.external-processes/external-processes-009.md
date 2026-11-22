# Viết script với script, scriptdef và bổ sung engine JSR-223 cho JDK cần dùng

## Mục tiêu

Apache Ant có thể chạy một đoạn mã trong buildfile hoặc định nghĩa một task mới bằng một ngôn ngữ script. Hai task liên quan là:

- **script** thực thi một đoạn script ngay tại vị trí khai báo. Có thể viết nội dung trực tiếp trong XML hoặc đặt trong tệp riêng.
- **scriptdef** định nghĩa một task Ant mới bằng script. Sau khi khai báo, task đó có thể được gọi như các task Ant khác và nhận attribute hoặc nested element do người viết định nghĩa.

Cả hai task có thể sử dụng ngôn ngữ được hỗ trợ bởi Apache BSF hoặc JSR-223. JSR-223 cung cấp API để Java tìm và chạy script engine; nó không tự cung cấp engine cho mọi ngôn ngữ. Vì vậy, ngoài JDK và Ant, build cần có engine tương ứng và các thư viện phụ thuộc của engine đó.

Điều này đặc biệt quan trọng với JavaScript. Nashorn từng được tích hợp trong JDK, nhưng đã bị loại bỏ từ JDK 15. Một buildfile dùng JavaScript qua JSR-223 trên JDK 15 trở lên phải bổ sung engine bên ngoài, chẳng hạn GraalJS, và các thư viện cần thiết theo phiên bản engine được chọn.

## 1. Khi nào nên dùng script hoặc scriptdef?

### 1.1. Dùng script cho một đoạn xử lý ngắn

Task script phù hợp khi cần thực hiện một đoạn logic nhỏ trong một target, ví dụ:

- Đọc property và tạo thông báo có điều kiện.
- Duyệt kết quả của một resource collection.
- Gọi một API Java mà các task Ant có sẵn không thể biểu đạt trực tiếp.
- Tạo một task Ant khác theo dữ liệu đã tính toán.
- Kết nối một số bước xử lý mà nếu viết bằng XML sẽ trở nên quá dài.

Ví dụ:

~~~xml
<project name="script-example" default="show" basedir=".">
    <property name="application.name" value="Sample App"/>
    <property name="release.version" value="2.4.0"/>

    <target name="show">
        <script language="groovy" manager="javax">
            def name = project.getProperty("application.name")
            def version = project.getProperty("release.version")
            self.log("Preparing " + name + " version " + version)
        </script>
    </target>
</project>
~~~

Đoạn script lấy giá trị từ Ant Project rồi ghi log qua task instance. Biến project là tham chiếu đến project đang chạy; self là tham chiếu đến chính task script.

### 1.2. Dùng scriptdef khi logic cần tái sử dụng

Nếu cùng một đoạn logic được gọi ở nhiều target hoặc nhiều buildfile, có thể đóng gói nó thành task tùy chỉnh bằng scriptdef.

Ví dụ, thay vì lặp lại đoạn kiểm tra tệp ở nhiều nơi, định nghĩa task require-file:

~~~xml
<scriptdef name="require-file"
           language="groovy"
           manager="javax">
    <attribute name="path"/>
    <![CDATA[
        def path = attributes.get("path")
        if (path == null || path.trim().isEmpty()) {
            self.fail("Attribute path is required")
        }

        def file = new File(path)
        if (!file.isFile()) {
            self.fail("Required file does not exist: " + path)
        }

        self.log("Verified file: " + file.absolutePath)
    ]]>
</scriptdef>

<target name="verify-release">
    <require-file path="dist/sample-app.jar"/>
    <require-file path="dist/checksums/sample-app.sha256"/>
</target>
~~~

Sau khi định nghĩa, require-file được sử dụng như một task Ant thông thường. Task có thể được gọi nhiều lần với các giá trị path khác nhau.

### 1.3. So sánh hai task

| Tiêu chí | script | scriptdef |
|---|---|---|
| Mục đích | Chạy một đoạn mã tại chỗ | Định nghĩa task Ant mới |
| Cách gọi | Đặt trực tiếp trong target | Khai báo một lần rồi gọi theo tên task |
| Tham số | Đọc property, reference hoặc bean được cấp | Khai báo attribute và nested element riêng |
| Tái sử dụng | Thường phải lặp hoặc tách script ra file | Có thể gọi lại task nhiều lần |
| Phù hợp | Xử lý ngắn, riêng cho một target | Logic lặp lại trong build |
| Khả năng mở rộng | Có thể truy cập Ant Project API | Có thể đóng gói giao diện task riêng |

Không nên dùng script chỉ để thay thế những task Ant tiêu chuẩn đã có như copy, javac, jar hoặc condition. Task có sẵn thường dễ đọc, dễ chẩn đoán và ít phụ thuộc engine hơn.

Nếu logic scriptdef trở nên phức tạp, có nhiều trạng thái, cần kiểm thử đơn vị hoặc được nhiều dự án dùng chung, hãy cân nhắc viết custom task bằng Java. Scriptdef rất hữu ích để đóng gói logic nhỏ hoặc thử nghiệm, nhưng không phải lúc nào cũng là lựa chọn lâu dài cho một thành phần lớn.

## 2. Cách Ant chạy script

### 2.1. Thuộc tính language

Cả script và scriptdef đều cần thuộc tính language. Giá trị phải là tên ngôn ngữ mà scripting manager và engine tương ứng nhận diện.

Ví dụ:

~~~xml
<script language="groovy" manager="javax">
    println("Hello from Groovy")
</script>
~~~

Tên ngôn ngữ không nhất thiết là phần mở rộng của tệp script. Nó thường được ánh xạ đến một hoặc nhiều tên do ScriptEngineFactory công bố. Ví dụ, engine JavaScript có thể đăng ký các alias như javascript, JavaScript hoặc js.

Nếu engine không đăng ký alias mà buildfile sử dụng, Ant sẽ không tìm được engine dù JAR đã có trên máy. Hãy kiểm tra tên được engine công bố thay vì đoán dựa vào tên file.

### 2.2. Thuộc tính manager

Từ Ant 1.7, hai task hỗ trợ thuộc tính manager để chọn cơ chế thực thi:

| Giá trị | Cách hoạt động |
|---|---|
| auto | Thử BSF trước; nếu không có engine BSF phù hợp thì dùng JSR-223 |
| bsf | Dùng Apache BSF scripting manager |
| javax | Dùng JSR-223 scripting manager qua API javax.script |

Mặc định là auto. Nếu dự án đã chọn engine JSR-223 cụ thể, đặt manager="javax" giúp cấu hình rõ ràng và tránh việc môi trường có thêm BSF engine làm thay đổi cách chọn.

Ví dụ:

~~~xml
<script language="groovy" manager="javax">
    println("Run through JSR-223")
</script>
~~~

Nếu dùng BSF:

~~~xml
<script language="jython" manager="bsf">
    print "Run through BSF"
</script>
~~~

Không phải mọi ngôn ngữ đều có engine cho cả hai manager. Hãy kiểm tra tài liệu của engine và phiên bản Ant đang dùng.

### 2.3. API JSR-223 và engine là hai thành phần khác nhau

JDK cung cấp Java Scripting API trong package javax.script. API này có các lớp như:

- ScriptEngineManager: tìm engine và tạo engine theo tên.
- ScriptEngineFactory: mô tả một engine, tên ngôn ngữ và các alias.
- ScriptEngine: đánh giá một đoạn script.
- Compilable: hỗ trợ biên dịch trước script nếu engine triển khai interface này.
- Invocable: cho phép gọi function hoặc method trong script nếu engine hỗ trợ.

Nhưng API không đồng nghĩa với việc JDK có sẵn engine cho JavaScript, Groovy hoặc Python.

Một engine JSR-223 là phần triển khai riêng. Khi engine được cài, ScriptEngineManager có thể phát hiện nó qua cơ chế service provider của Java, thường thông qua metadata trong JAR tại META-INF/services/javax.script.ScriptEngineFactory.

Có thể hình dung:

~~~text
Ant <script> / <scriptdef>
          |
          v
    Scripting manager
       /       \
      /         \
    BSF       JSR-223
                 |
                 v
        ScriptEngineManager
                 |
                 v
          ScriptEngine
                 |
                 v
        Ngôn ngữ script
~~~

Nếu chỉ có JDK nhưng không có engine phù hợp, JSR-223 manager vẫn tồn tại nhưng không thể thực thi ngôn ngữ đó.

## 3. JDK cần engine nào?

### 3.1. JavaScript trên JDK 8 đến JDK 14

Nashorn là JavaScript engine được tích hợp trong JDK 8 đến JDK 14. Có thể dùng task script với manager javax:

~~~xml
<script language="javascript" manager="javax">
    var message = "Hello from JavaScript";
    self.log(message);
</script>
~~~

Nashorn bị deprecated để loại bỏ từ JDK 11 và đã bị loại bỏ trong JDK 15. Do đó, một buildfile chạy được trên JDK 8 hoặc 11 có thể không tìm thấy JavaScript engine khi chuyển sang JDK 17, 21 hoặc các JDK mới hơn.

Không nhầm việc package javax.script vẫn có trong JDK với việc JavaScript engine vẫn còn. API JSR-223 vẫn có thể dùng để nạp engine bên ngoài.

### 3.2. JavaScript trên JDK 15 trở lên

Với JDK 15+, cần cài một JavaScript engine bên ngoài có hỗ trợ JSR-223. GraalJS là một lựa chọn thường được dùng để thay thế các buildfile từng chạy trên Nashorn.

GraalJS có thể đăng ký các alias như Graal.js, js, JavaScript và javascript, tùy phiên bản và cách đóng gói. Cần dùng đúng phiên bản engine tương thích với JDK và Ant của dự án.

Apache Ant ghi rõ GraalJS không phải bản thay thế hoàn toàn tương thích với Nashorn. Những script dựa vào API riêng hoặc hành vi tương thích của Nashorn có thể cần chỉnh sửa khi chuyển engine.

Các thành phần cần thiết phụ thuộc phiên bản GraalJS. Tài liệu Ant liệt kê các thư viện như JavaScript engine, JSR-223 script engine, GraalVM SDK, Truffle API, regex và ICU. Một số bản phát hành mới yêu cầu cấu hình module path cho JSR-223 engine. Không nên chỉ chép một JAR duy nhất rồi giả định mọi phụ thuộc đã được đáp ứng.

### 3.3. Ngôn ngữ khác như Groovy hoặc Python

JSR-223 không chỉ dành cho JavaScript. Có thể dùng các engine khác nếu có implementation tương thích, ví dụ:

- Groovy với module cung cấp JSR-223 engine.
- Python qua Jython nếu phiên bản phù hợp và có engine tương ứng.
- Ruby hoặc các ngôn ngữ khác nếu có implementation hỗ trợ JSR-223.

Cần phân biệt ngôn ngữ và engine. Việc cài một runtime ngôn ngữ hoặc thêm một JAR thư viện thông thường chưa chắc đã cung cấp ScriptEngineFactory. Hãy xác nhận engine cụ thể hỗ trợ JSR-223 và có thể được ScriptEngineManager phát hiện.

### 3.4. Bảng quyết định theo JDK

| Môi trường | JavaScript engine | Cách cấu hình |
|---|---|---|
| JDK 8–10 | Nashorn được tích hợp | Có thể dùng manager="javax" và language="javascript" |
| JDK 11–14 | Nashorn còn tồn tại nhưng đã deprecated | Có thể tiếp tục dùng trong giai đoạn chuyển đổi; nên lập kế hoạch thay thế |
| JDK 15 trở lên | Nashorn đã bị loại bỏ | Bổ sung engine JSR-223 bên ngoài như GraalJS |
| JDK bất kỳ có engine Groovy | Groovy JSR-223 engine tương ứng | Cài engine và runtime dependencies, rồi dùng language="groovy" |
| JDK bất kỳ có engine khác | Phụ thuộc implementation | Kiểm tra alias, phiên bản JDK và cách nạp engine |

Không dùng bảng này thay cho ma trận tương thích của engine. Cùng một ngôn ngữ có thể có nhiều bản engine với yêu cầu JDK khác nhau.

## 4. Bổ sung engine vào Ant classpath

### 4.1. Các vị trí có thể cài thư viện

Ant có thể nạp thư viện tùy chọn và scripting engine từ một số vị trí:

- ANT_HOME/lib: thư viện dùng chung cho mọi build chạy bằng bản Ant đó.
- Thư mục .ant/lib trong home của người dùng: thư viện dành cho tài khoản đang chạy Ant.
- Tham số dòng lệnh -lib: bổ sung thư viện cho một lần chạy hoặc một dự án.
- Classpath riêng của task script hoặc scriptdef: phù hợp khi muốn project tự mô tả dependency của engine.

Tài liệu Ant khuyến nghị quản lý dependency qua cơ chế của Ant thay vì thêm toàn bộ JAR vào biến môi trường CLASSPATH toàn hệ thống. Việc đặt JAR vào CLASSPATH chung có thể làm các ứng dụng Java khác vô tình nhìn thấy thư viện không cần thiết.

### 4.2. Bổ sung qua -lib

Ví dụ chạy Ant và bổ sung thư mục chứa engine:

~~~text
ant -lib lib/script-engine -f build.xml run-script
~~~

Nếu engine có nhiều JAR phụ thuộc, hãy đặt đầy đủ các JAR cần thiết trong thư mục hoặc các vị trí được nạp. Với những thư viện được phân phối theo module hoặc yêu cầu module path, cần làm theo hướng dẫn riêng của engine; -lib chỉ bổ sung classpath của Ant, không tự thay thế mọi cấu hình module path.

### 4.3. Bổ sung qua ANT_HOME/lib hoặc user .ant/lib

Có thể cài thư viện vào ANT_HOME/lib để mọi build dùng cùng một Ant installation đều thấy engine. Cách này phù hợp với môi trường CI được quản lý tập trung, nhưng cần ghi lại phiên bản engine để tránh máy phát triển và CI dùng các phiên bản khác nhau.

Thư mục .ant/lib trong home của người dùng chỉ áp dụng cho tài khoản đó. Nếu build chạy dưới service account hoặc runner CI khác, thư viện cài trong home cá nhân sẽ không tự xuất hiện.

### 4.4. Dùng classpath của task

Task script hỗ trợ thuộc tính classpath hoặc classpathref. Classpath này được dùng làm context classloader cho script và để tìm implementation ngôn ngữ:

~~~xml
<path id="script.engine.classpath">
    <fileset dir="lib/script-engine">
        <include name="*.jar"/>
    </fileset>
</path>

<target name="run-script">
    <script language="groovy"
            manager="javax"
            classpathref="script.engine.classpath">
        println("Engine is available")
    </script>
</target>
~~~

Cách này giúp buildfile mô tả rõ thư viện script engine mà target cần. Nó cũng tránh phải cài thư viện riêng vào home của từng người dùng.

Task scriptdef cũng hỗ trợ classpath và classpathref. Có thể dùng chung một Path cho nhiều định nghĩa:

~~~xml
<scriptdef name="validate-input"
           language="groovy"
           manager="javax"
           classpathref="script.engine.classpath">
    <attribute name="file"/>
    <![CDATA[
        def file = new File(attributes.get("file"))
        if (!file.isFile()) {
            self.fail("Input file does not exist")
        }
        self.log("Input file is ready")
    ]]>
</scriptdef>
~~~

Classpath phải chứa engine và các dependency runtime cần thiết. Nếu engine được nạp bằng module path thay vì classpath, hãy cấu hình JVM theo yêu cầu của phiên bản engine.

### 4.5. Dùng fetch.xml để lấy dependency tùy chọn của Ant

Ant có file fetch.xml để tải phần lớn thư viện phụ thuộc của các optional task:

~~~text
ant -f fetch.xml -Ddest=system
~~~

Lệnh này thường được chạy từ thư mục cài đặt Ant. Nó có thể tải các thư viện tùy chọn của Ant, nhưng không có nghĩa là mọi scripting engine bên thứ ba hoặc mọi phiên bản GraalJS đều được cài tự động.

Hãy xem bảng Library Dependencies trong tài liệu cài đặt Ant và tài liệu engine tương ứng. Với engine bên ngoài, có thể cần tải thêm các thư viện transitive hoặc cấu hình riêng.

## 5. Cấu hình GraalJS cho Ant

### 5.1. Quản lý đúng bộ JAR

Với JDK 15 trở lên, nếu dùng GraalJS qua JSR-223, cần có implementation ScriptEngine và runtime của GraalJS tương ứng. Bộ dependency thay đổi theo phiên bản GraalVM/GraalJS.

Các tên thư viện có thể gặp trong tài liệu và bản phân phối gồm:

| Thành phần | Vai trò |
|---|---|
| JavaScript engine | Thực thi ngôn ngữ JavaScript |
| JSR-223 script engine | Cung cấp lớp ScriptEngineFactory để Java tìm engine |
| GraalVM SDK / Polyglot | API và runtime hỗ trợ ngôn ngữ |
| Truffle API | Nền tảng thực thi guest language |
| Regex runtime | Hỗ trợ biểu thức chính quy của engine |
| ICU | Hỗ trợ một số chức năng Unicode và locale |

Không lấy một danh sách JAR từ phiên bản GraalJS cũ rồi dùng nguyên cho phiên bản mới. Hãy dùng dependency metadata của đúng release, tốt nhất thông qua Maven/Ivy hoặc một quy trình dependency resolution có khóa phiên bản.

### 5.2. Khai báo Path trong Ant

Nếu phiên bản GraalJS được chọn hỗ trợ nạp qua classpath, có thể khai báo Path chứa các JAR đã resolve:

~~~xml
<path id="graaljs.classpath">
    <fileset dir="lib/graaljs">
        <include name="*.jar"/>
    </fileset>
</path>

<target name="run-javascript">
    <script language="javascript"
            manager="javax"
            classpathref="graaljs.classpath">
        var File = Java.type("java.io.File");
        var file = new File("build/output.jar");
        self.log("Output exists: " + file.isFile());
    </script>
</target>
~~~

Ví dụ minh họa cấu trúc task; thư mục lib/graaljs phải chứa đầy đủ engine và runtime dependencies tương thích. Một số bản GraalJS hiện đại yêu cầu JSR-223 engine trên module path. Trong trường hợp đó, cấu hình JVM/module path theo tài liệu GraalJS thay vì chỉ dựa vào classpathref.

### 5.3. Cú pháp Java interoperability

Nashorn và GraalJS có nhiều điểm tương đồng nhưng không hoàn toàn giống nhau. Ví dụ cú pháp Java.type:

~~~javascript
var File = Java.type("java.io.File");
var file = new File("build/output.jar");
print(file.exists());
~~~

Các script dùng API riêng của Nashorn như nashorn:mozilla_compat.js hoặc dựa vào hành vi JavaAdapter có thể cần chỉnh sửa. Hãy kiểm tra Nashorn Migration Guide khi chuyển script cũ sang GraalJS.

### 5.4. Quyền truy cập Java từ GraalJS

Ant có cơ chế tích hợp để script truy cập các đối tượng Ant. Tài liệu Ant mô tả việc bật quyền truy cập phù hợp của GraalJS để script có thể dùng Ant objects và chế độ tương thích Nashorn mặc định trong cấu hình được hỗ trợ.

Quyền truy cập Java rộng làm script có thể thực hiện nhiều thao tác mà một task Java có thể làm. Vì vậy, chỉ chạy script từ nguồn tin cậy. Không coi JSR-223 hoặc GraalJS là sandbox để chạy mã do người dùng bên ngoài cung cấp.

## 6. Viết script trực tiếp trong build.xml

### 6.1. Inline script và CDATA

Khi script chứa ký tự như dấu nhỏ hơn, dấu lớn hơn hoặc ký tự XML đặc biệt, hãy đặt nội dung trong CDATA:

~~~xml
<script language="groovy" manager="javax">
    <![CDATA[
        def version = project.getProperty("release.version")
        if (version == null || version.trim().isEmpty()) {
            throw new org.apache.tools.ant.BuildException(
                "Property release.version is required"
            )
        }
        self.log("Release version: " + version)
    ]]>
</script>
~~~

CDATA giúp parser XML không diễn giải nội dung script như markup. Không đặt chuỗi đóng CDATA bên trong script nếu không xử lý cách thoát phù hợp.

### 6.2. Tách script ra file riêng

Khi script dài hơn vài dòng, đặt nó trong file riêng:

~~~text
project/
├── build.xml
└── scripts/
    └── check-release.groovy
~~~

Nội dung check-release.groovy:

~~~groovy
def version = project.getProperty("release.version")
if (version == null || version.trim().isEmpty()) {
    throw new org.apache.tools.ant.BuildException(
        "Property release.version is required"
    )
}
self.log("Release version: " + version)
~~~

Buildfile:

~~~xml
<script language="groovy"
        manager="javax"
        src="scripts/check-release.groovy"
        encoding="UTF-8"
        classpathref="script.engine.classpath"/>
~~~

Thuộc tính encoding được hỗ trợ từ Ant 1.10.2. Nếu bỏ qua, Ant sử dụng encoding mặc định của JVM. Với source file có dấu hoặc nội dung đa ngôn ngữ, nên chỉ định UTF-8 rõ ràng.

### 6.3. Truy cập property và reference

Task script có thể truy cập Project API qua biến project. Ví dụ:

~~~xml
<property name="source.dir" location="src"/>
<path id="compile.path">
    <pathelement location="lib/example.jar"/>
</path>

<script language="groovy" manager="javax">
    def sourceDir = project.getProperty("source.dir")
    def compilePath = project.getReference("compile.path")

    self.log("Source directory: " + sourceDir)
    self.log("Compile path reference: " + compilePath)
</script>
~~~

Cách gọi project.getProperty và project.getReference rõ ràng hơn việc phụ thuộc vào các biến tự động được tạo từ mọi property hoặc reference.

## 7. setbeans và các đối tượng Ant trong script

### 7.1. setbeans của task script

Task script có thuộc tính setbeans. Khi true, Ant đưa property, reference và target có tên hợp lệ vào script dưới dạng biến.

Mặc định của script là true. Ví dụ:

~~~xml
<property name="message" value="Hello"/>

<script language="groovy" manager="javax" setbeans="true">
    self.log(message)
</script>
~~~

Nếu setbeans="false", chỉ các biến project và self được cung cấp theo cơ chế này. Khi đó, hãy lấy property qua project.getProperty:

~~~xml
<script language="groovy" manager="javax" setbeans="false">
    def message = project.getProperty("message")
    self.log(message)
</script>
~~~

Với buildfile lớn, setbeans="false" giúp tránh xung đột tên biến và làm rõ dữ liệu script sử dụng.

### 7.2. setbeans của scriptdef

Scriptdef cũng hỗ trợ setbeans, nhưng mặc định khác script. Từ Ant 1.10.13, giá trị mặc định của scriptdef là false để giữ tương thích hành vi cũ. Nếu cần truy cập property, reference hoặc target bằng tên biến, hãy đặt setbeans="true" tường minh.

Không nên giả định script và scriptdef có cùng giá trị mặc định cho setbeans.

### 7.3. Hai biến đặc biệt project và self

- project đại diện cho Ant Project đang thực thi build.
- self đại diện cho instance task đang chạy.

Trong scriptdef, self có thể dùng để ghi log và gọi self.fail(message) nhằm ném BuildException nếu dữ liệu đầu vào không hợp lệ. Trong script thông thường, có thể dùng self.log để ghi log và ném BuildException Java khi cần làm target thất bại.

## 8. Định nghĩa task mới bằng scriptdef

### 8.1. Khai báo attribute

Scriptdef cho phép khai báo các attribute mà task mới chấp nhận:

~~~xml
<scriptdef name="require-version"
           language="groovy"
           manager="javax"
           setbeans="false">
    <attribute name="value"/>
    <![CDATA[
        def version = attributes.get("value")
        if (version == null || version.trim().isEmpty()) {
            self.fail("Attribute value must not be empty")
        }
        self.log("Using version " + version)
    ]]>
</scriptdef>

<target name="prepare-release">
    <require-version value="2.4.0"/>
</target>
~~~

Các attribute được truy cập qua collection attributes. Giá trị không được truyền vào có thể trả về null; script phải tự kiểm tra nếu đó là giá trị bắt buộc.

### 8.2. Tên attribute và element được chuyển thành chữ thường

Ant chuyển tên attribute và nested element sang chữ thường khi đưa vào collection attributes và elements.

Ví dụ, nếu khai báo:

~~~xml
<attribute name="ReleaseVersion"/>
~~~

thì script truy cập bằng:

~~~groovy
attributes.get("releaseversion")
~~~

Không dùng "ReleaseVersion" làm key khi đọc collection. Nên khai báo tên attribute bằng chữ thường ngay từ đầu để tránh nhầm lẫn.

### 8.3. Giá trị mặc định cho attribute

Từ Ant 1.10.13, attribute của scriptdef có thể khai báo default:

~~~xml
<scriptdef name="require-file"
           language="groovy"
           manager="javax">
    <attribute name="path"/>
    <attribute name="minsize" default="1"/>
    <![CDATA[
        def path = attributes.get("path")
        def minSize = Long.parseLong(attributes.get("minsize"))

        def file = new File(path)
        if (!file.isFile()) {
            self.fail("File does not exist: " + path)
        }
        if (file.length() < minSize) {
            self.fail("File is smaller than the required size")
        }
        self.log("File check passed")
    ]]>
</scriptdef>
~~~

Nếu cần chạy trên Ant cũ hơn 1.10.13, không dùng thuộc tính default; hãy xử lý giá trị null trong script.

### 8.4. Nhận nested element

Scriptdef có thể hỗ trợ nested element như fileset hoặc path:

~~~xml
<scriptdef name="report-files"
           language="groovy"
           manager="javax">
    <attribute name="label"/>
    <element name="fileset" type="fileset"/>
    <![CDATA[
        def label = attributes.get("label")
        def sets = elements.get("fileset")

        if (sets == null || sets.isEmpty()) {
            self.fail("At least one fileset is required")
        }

        self.log("Report: " + label)
        self.log("Fileset count: " + sets.size())

        for (int i = 0; i < sets.size(); i++) {
            def fileset = sets.get(i)
            self.log("Base directory: " + fileset.getDir(project))
        }
    ]]>
</scriptdef>

<target name="inspect">
    <report-files label="Java sources">
        <fileset dir="src">
            <include name="**/*.java"/>
        </fileset>
        <fileset dir="generated-src">
            <include name="**/*.java"/>
        </fileset>
    </report-files>
</target>
~~~

Collection elements có thể chứa nhiều instance của cùng một nested element. Vì vậy, elements.get("fileset") trả về danh sách và script có thể duyệt theo index.

Nếu nested element không được truyền vào, collection có thể trả về null. Hãy kiểm tra trước khi gọi size hoặc truy cập phần tử.

### 8.5. self.text và nội dung lồng trực tiếp

Scriptdef có thể nhận văn bản trực tiếp bên trong task. Nội dung đó có thể được đọc qua self.text:

~~~xml
<scriptdef name="print-message"
           language="groovy"
           manager="javax">
    <![CDATA[
        self.log("Message: " + self.text)
    ]]>
</scriptdef>

<target name="show">
    <print-message>
        Build is preparing the release.
    </print-message>
</target>
~~~

Cách này phù hợp khi task tùy chỉnh nhận một đoạn text đơn giản. Nếu dữ liệu có cấu trúc, attribute hoặc nested element thường rõ ràng hơn.

### 8.6. Dùng namespace để tránh trùng tên task

Scriptdef hỗ trợ thuộc tính uri để đặt task trong namespace riêng:

~~~xml
<project name="scriptdef-namespace"
         xmlns:custom="https://example.org/ant/custom">
    <scriptdef name="check-file"
               uri="https://example.org/ant/custom"
               language="groovy"
               manager="javax">
        <attribute name="path"/>
        <![CDATA[
            def file = new File(attributes.get("path"))
            if (!file.isFile()) {
                self.fail("File not found")
            }
        ]]>
    </scriptdef>

    <target name="verify">
        <custom:check-file path="dist/app.jar"/>
    </target>
</project>
~~~

Namespace giúp tránh xung đột với task cùng tên được cung cấp bởi Ant hoặc Antlib khác.

## 9. Các tùy chọn nâng cao của scriptdef

### 9.1. Thuộc tính src và encoding

Có thể đặt scriptdef trong tệp riêng bằng thuộc tính src. Ant hỗ trợ encoding từ phiên bản 1.10.2:

~~~xml
<scriptdef name="validate-release"
           language="groovy"
           manager="javax"
           src="scripts/validate-release.groovy"
           encoding="UTF-8"
           classpathref="script.engine.classpath"/>
~~~

Cách này giúp tách phần xử lý khỏi XML và thuận tiện hơn khi script có nhiều dòng.

### 9.2. compiled

Từ Ant 1.10.2, scriptdef có thuộc tính compiled. Nếu true, Ant cố gắng biên dịch script trước lần thực thi đầu tiên khi manager là javax và engine triển khai javax.script.Compilable.

~~~xml
<scriptdef name="check-name"
           language="groovy"
           manager="javax"
           compiled="true">
    <attribute name="value"/>
    <![CDATA[
        def value = attributes.get("value")
        if (value == null || value.trim().isEmpty()) {
            self.fail("value is required")
        }
    ]]>
</scriptdef>
~~~

Biên dịch trước có thể giảm chi phí khi task được gọi nhiều lần, nhưng chỉ có tác dụng nếu engine hỗ trợ Compilable. Giá trị mặc định là false. Hãy đo hiệu năng trước khi bật vì không phải engine nào cũng triển khai tính năng này.

### 9.3. loaderRef

Thuộc tính loaderRef cho phép nhiều scriptdef dùng chung classloader được tạo từ classpath đã khai báo:

~~~xml
<scriptdef name="task-one"
           language="groovy"
           manager="javax"
           classpathref="script.engine.classpath"
           loaderRef="shared.script.loader">
    <![CDATA[
        self.log("Task one")
    ]]>
</scriptdef>

<scriptdef name="task-two"
           language="groovy"
           manager="javax"
           classpathref="script.engine.classpath"
           loaderRef="shared.script.loader">
    <![CDATA[
        self.log("Task two")
    ]]>
</scriptdef>
~~~

Cách này có thể giảm việc tạo nhiều classloader cho cùng một bộ thư viện engine khi có nhiều định nghĩa. Chỉ chia sẻ loader khi các script thực sự dùng cùng một dependency set tương thích.

### 9.4. Resource collection làm nguồn script

Từ Ant 1.7.1, scriptdef có thể nạp script từ resource collection lồng bên trong. Điều này hữu ích khi script nằm trong tài nguyên được quản lý bởi FileSet, Path hoặc một collection khác.

Với build thông thường, dùng src trỏ đến file script thường dễ đọc hơn. Resource collection phù hợp khi dự án đã quản lý script như một nhóm tài nguyên.

## 10. Ví dụ hoàn chỉnh: dùng scriptdef để kiểm tra artifact trước khi đóng gói

Ví dụ sau định nghĩa task kiểm tra artifact có tồn tại, có kích thước tối thiểu và có phần mở rộng mong muốn.

~~~xml
<project name="scripted-release" default="verify" basedir=".">
    <property name="artifact.file" location="dist/sample-app.jar"/>
    <property name="minimum.bytes" value="1024"/>

    <path id="script.engine.classpath">
        <fileset dir="lib/script-engine">
            <include name="*.jar"/>
        </fileset>
    </path>

    <scriptdef name="verify-artifact"
               language="groovy"
               manager="javax"
               classpathref="script.engine.classpath">
        <attribute name="file"/>
        <attribute name="minbytes" default="1"/>
        <![CDATA[
            def path = attributes.get("file")
            def minBytes = Long.parseLong(attributes.get("minbytes"))

            if (path == null || path.trim().isEmpty()) {
                self.fail("file attribute is required")
            }

            def artifact = new File(path)
            if (!artifact.isFile()) {
                self.fail("Artifact does not exist: " + path)
            }

            if (!artifact.name.endsWith(".jar")) {
                self.fail("Expected a JAR artifact")
            }

            if (artifact.length() < minBytes) {
                self.fail("Artifact is smaller than the required size")
            }

            self.log("Artifact verified: " + artifact.name)
            self.log("Size: " + artifact.length() + " bytes")
        ]]>
    </scriptdef>

    <target name="verify">
        <verify-artifact file="${artifact.file}"
                         minbytes="${minimum.bytes}"/>
    </target>
</project>
~~~

Ví dụ giả định thư viện Groovy JSR-223 và các dependency của nó đã được cài trong lib/script-engine. Nếu dùng engine khác, thay language, manager và classpath cho phù hợp.

Task verify-artifact có thể được gọi trong nhiều target khác nhau mà không phải sao chép đoạn script. Nếu cần kiểm tra nhiều loại artifact, có thể thêm attribute hoặc nested element thay vì viết thêm một task gần giống.

## 11. Kiểm tra engine JSR-223 đã được nạp hay chưa

### 11.1. Dùng ScriptEngineManager

Có thể viết một chương trình Java nhỏ để liệt kê engine mà JVM nhìn thấy:

~~~java
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;

public class ListScriptEngines {
    public static void main(String[] args) {
        ScriptEngineManager manager = new ScriptEngineManager();

        for (ScriptEngineFactory factory : manager.getEngineFactories()) {
            System.out.println(
                factory.getEngineName() + " : " + factory.getNames()
            );
        }

        if (args.length > 0
                && manager.getEngineByName(args[0]) == null) {
            throw new IllegalStateException(
                "No JSR-223 engine found for: " + args[0]
            );
        }
    }
}
~~~

Chạy chương trình với classpath/module path tương tự môi trường Ant. Nếu muốn kiểm tra JavaScript, truyền alias mà buildfile dùng, ví dụ javascript.

Kết quả cho biết engine nào đã được phát hiện và những alias nào có thể dùng. Nếu không có engine phù hợp, kiểm tra classpath, module path và service provider metadata của các JAR.

### 11.2. Kiểm tra từ chính buildfile

Có thể thêm một target thử engine bằng task script:

~~~xml
<target name="check-script-engine">
    <script language="groovy"
            manager="javax"
            classpathref="script.engine.classpath">
        self.log("JSR-223 engine is available")
    </script>
</target>
~~~

Chạy target này trước khi dùng scriptdef hoặc các target phát hành. Nếu task báo không tìm thấy engine, lỗi nằm ở môi trường engine hoặc cách nạp classloader chứ chưa chắc nằm trong nội dung script.

### 11.3. Kiểm tra Ant và optional libraries

Lệnh:

~~~text
ant -diagnostics
~~~

hiển thị thông tin về Ant installation, các JAR được nạp và một số optional task. Đây là bước hữu ích khi script hoặc scriptdef không được nhận diện hoặc khi Ant không thấy thư viện phụ thuộc.

Cũng có thể chạy fetch.xml để lấy phần lớn thư viện tùy chọn của Ant:

~~~text
ant -f fetch.xml -Ddest=system
~~~

Nhớ rằng fetch.xml không đảm bảo cài mọi engine ngôn ngữ bên thứ ba. Engine JSR-223 vẫn phải được bổ sung theo tài liệu của engine cụ thể.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ant không nhận ra task script hoặc scriptdef | Thiếu thành phần optional hoặc thư viện Ant cần thiết | Kiểm tra phiên bản Ant, optional dependencies và ant -diagnostics |
| Unable to create script engine | Không tìm thấy engine phù hợp với language | Kiểm tra engine JAR, alias và manager |
| Script chạy trên JDK 11 nhưng lỗi trên JDK 17 | Dự án phụ thuộc Nashorn đã bị loại bỏ | Bổ sung engine ngoài như GraalJS và cập nhật script |
| JSR-223 API có nhưng không chạy được JavaScript | Chỉ có API javax.script, chưa có engine | Cài implementation JSR-223 |
| Engine có trong classpath ứng dụng nhưng Ant không tìm thấy | Engine không nằm trong classloader mà task sử dụng | Dùng classpath/classpathref của script hoặc -lib/ANT_HOME/lib |
| Thiếu class khi khởi tạo engine | Thiếu dependency transitive hoặc sai phiên bản | Resolve đầy đủ dependency của engine |
| ScriptEngineManager không liệt kê engine | Thiếu service provider metadata hoặc module không được nạp | Kiểm tra META-INF/services, classpath/module path và tên engine |
| language không khớp | Dùng tên file hoặc tên gọi không phải alias của engine | Liệt kê ScriptEngineFactory.getNames() |
| Groovy syntax error | Engine hoặc phiên bản Groovy không tương thích với script | Kiểm tra Groovy version và cú pháp |
| JavaScript báo lỗi Java.type hoặc API Nashorn | Script cũ phụ thuộc cú pháp riêng Nashorn | Đọc migration guide và chỉnh script cho engine mới |
| scriptdef không đọc được attribute | Sai key chữ hoa/chữ thường hoặc attribute không được khai báo | Dùng key chữ thường và kiểm tra attributes.get |
| Nested element trả về null | Không truyền element hoặc tên element sai | Kiểm tra elements.get trước khi truy cập |
| self.fail không được gọi | Dùng sai biến self hoặc script chưa được thực thi qua scriptdef | Kiểm tra task definition và context |
| Scriptdef hoạt động khác script | setbeans có default khác nhau | Đặt setbeans tường minh và dùng project/self |
| Script chạy quá chậm khi được gọi nhiều lần | Engine khởi tạo hoặc biên dịch lại script | Đánh giá compiled/loaderRef nếu engine hỗ trợ |
| Script tạo target bị lỗi location | Target được tạo động thiếu location riêng | Gán Location hợp lệ và khác nhau cho từng target |

## 13. Bảo mật và khả năng bảo trì

### 13.1. Script chạy với quyền của tiến trình Ant

Script có thể truy cập Ant Project API, tạo task, đọc file và gọi Java API. Nó có thể làm gần như những gì một task Java có thể làm.

Vì vậy:

- Chỉ chạy script nằm trong repository hoặc nguồn đã được tin cậy.
- Không thực thi script được tải từ URL hoặc do người dùng bên ngoài cung cấp mà chưa kiểm soát.
- Không coi JSR-223 là sandbox.
- Không cấp secret hoặc quyền truy cập rộng cho build nếu script không cần.
- Hạn chế setbeans khi không cần phơi toàn bộ property và reference.
- Tránh ghi thông tin nhạy cảm ra log.

### 13.2. Giữ logic script nhỏ và có mục đích

Một script tốt thường làm một việc rõ ràng: xác thực dữ liệu, biến đổi danh sách, gọi một API hoặc điều phối một thao tác không có task tương ứng.

Nếu script phải quản lý nhiều trạng thái, tự xây dựng dependency graph, điều khiển hàng loạt task hoặc chứa nhiều trăm dòng logic, hãy xem xét:

- Chuyển logic thành custom task Java.
- Tách script thành module có kiểm thử riêng.
- Dùng task Ant chuẩn hoặc Antlib nếu chức năng đã tồn tại.
- Tách cấu hình khỏi mã xử lý.

### 13.3. Khóa phiên bản engine

Không nên để build tự động dùng bất kỳ engine nào có sẵn trong máy. Hãy quản lý phiên bản engine và các dependency đi kèm trong build environment.

Điều này giúp:

- Máy phát triển và CI dùng cùng ngôn ngữ runtime.
- Tránh thay đổi hành vi khi JDK được nâng cấp.
- Dễ tái lập build.
- Dễ xác định nguyên nhân khi engine có thay đổi tương thích.

Với GraalJS, cần khóa cùng một release line cho các module engine và runtime. Không trộn các JAR khác phiên bản.

### 13.4. Dùng encoding nhất quán

Script file có thể chứa ký tự Unicode, dấu tiếng Việt hoặc tên tài nguyên đa ngôn ngữ. Chỉ định encoding UTF-8 cho src khi phiên bản Ant hỗ trợ thuộc tính encoding. Đồng thời lưu file script theo đúng encoding đã khai báo.

## 14. Thực hành tốt

- Dùng task Ant chuẩn trước khi quyết định viết script.
- Dùng script cho logic ngắn, riêng trong một target.
- Dùng scriptdef để đóng gói logic lặp thành task có attribute và nested element rõ ràng.
- Chọn manager="javax" hoặc manager="bsf" tường minh khi cần kết quả ổn định.
- Xác nhận language trùng với alias do ScriptEngineFactory công bố.
- Phân biệt API JSR-223 với engine thực thi ngôn ngữ.
- Với JDK 15+, không giả định Nashorn còn tồn tại.
- Bổ sung GraalJS hoặc engine phù hợp và toàn bộ dependency theo đúng phiên bản.
- Dùng classpathref của task khi muốn buildfile tự quản lý engine dependencies.
- Nếu engine yêu cầu module path, cấu hình JVM theo tài liệu engine; classpathref không thay thế module path.
- Dùng src và encoding UTF-8 cho script dài hoặc có Unicode.
- Dùng CDATA cho script inline có ký tự XML đặc biệt.
- Đặt setbeans rõ ràng; ưu tiên false nếu chỉ cần project và self.
- Kiểm tra null khi đọc attribute hoặc nested element.
- Dùng self.fail trong scriptdef để báo lỗi build có chủ đích.
- Chỉ bật compiled khi engine hỗ trợ Compilable và có lợi ích thực tế.
- Dùng loaderRef khi nhiều scriptdef chia sẻ cùng engine classpath.
- Chỉ chạy script tin cậy vì script có thể truy cập Java và Ant API.
- Kiểm tra engine bằng ScriptEngineManager trước khi đưa vào CI.

## 15. Tự kiểm tra trước khi dùng script trong build

Trước khi đưa script hoặc scriptdef vào build chính, hãy tự trả lời:

1. Logic này có thể thực hiện bằng task Ant chuẩn không?
2. Cần chạy một đoạn script hay định nghĩa task mới để tái sử dụng?
3. Engine đang dùng thuộc BSF hay JSR-223?
4. manager đã được đặt rõ ràng chưa?
5. language có khớp alias do engine đăng ký không?
6. JDK đang chạy có tích hợp engine đó hay cần bổ sung engine bên ngoài?
7. Nếu chạy trên JDK 15+, script JavaScript có còn phụ thuộc Nashorn không?
8. Các JAR của engine và dependency đã được nạp vào đúng classpath hoặc module path chưa?
9. ScriptEngineManager có phát hiện engine trong môi trường CI không?
10. setbeans có cần true hay chỉ cần project và self?
11. Scriptdef đã khai báo đầy đủ attribute và nested element chưa?
12. Script có kiểm tra giá trị null hoặc đầu vào không hợp lệ không?
13. Có cần src và encoding UTF-8 để quản lý script dài không?
14. Engine có hỗ trợ Compilable trước khi bật compiled không?
15. Script có thể thực hiện thao tác nhạy cảm nào với quyền của tiến trình Ant?
16. Phiên bản engine và JDK đã được khóa nhất quán giữa máy phát triển và CI chưa?

script giúp thực thi logic script trong một target; scriptdef đóng gói logic thành task Ant mới; JSR-223 cung cấp cơ chế để Java tìm và gọi engine. Khi cấu hình đúng engine cho JDK đang chạy, kiểm soát classpath/module path và giữ script có phạm vi rõ ràng, Ant có thể mở rộng build bằng ngôn ngữ script mà vẫn duy trì cấu trúc buildfile dễ đọc.

## Tài liệu tham khảo

- [Apache Ant — Script Task](https://ant.apache.org/manual/Tasks/script.html)
- [Apache Ant — Scriptdef Task](https://ant.apache.org/manual/Tasks/scriptdef.html)
- [Apache Ant — Installing Ant and Library Dependencies](https://ant.apache.org/manual/install.html)
- [Oracle — Java Scripting API](https://docs.oracle.com/en/java/javase/12/scripting/java-scripting-api.html)
- [Oracle — JDK 15 Release Notes: Removal of Nashorn](https://www.oracle.com/java/technologies/javase/15-relnote-issues.html)
- [GraalJS — Run GraalJS on a Stock JDK](https://github.com/oracle/graaljs/blob/master/docs/user/RunOnJDK.md)
- [GraalVM — ScriptEngine (JSR-223)](https://www.graalvm.org/jdk25/reference-manual/js/ScriptEngine/)

