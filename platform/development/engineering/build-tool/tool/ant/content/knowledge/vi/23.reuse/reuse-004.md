# Truyền phần tử lồng, phần tử implicit và nội dung text

Trong Apache Ant, `macrodef` cho phép định nghĩa một nhóm task có thể gọi lại như một task mới. Một macro có thể nhận giá trị thuộc tính, nhận các phần tử XML lồng từ nơi gọi và nhận cả đoạn văn bản nằm trực tiếp bên trong phần tử macro. Ba cách truyền dữ liệu này giúp macro vừa tái sử dụng được logic build, vừa để target gọi macro quyết định những chi tiết thay đổi theo từng trường hợp.

Khi thiết kế macro, cần phân biệt rõ:

- **Attribute** truyền một giá trị đơn như tên thư mục, chế độ hoặc tên module.
- **Nested element** truyền một cấu trúc XML có thể chứa task hoặc cấu hình con.
- **Implicit element** cho phép người gọi đặt trực tiếp các phần tử con mà không phải bọc chúng trong một thẻ có tên đã khai báo.
- **Text content** truyền nội dung văn bản nằm giữa thẻ mở và thẻ đóng của macro.

Các thành phần này được khai báo trong `macrodef` rồi được sử dụng trong phần `<sequential>` của macro.

## 1. Cấu trúc cơ bản của macrodef

Một macro được định nghĩa bằng task `<macrodef>`. Thuộc tính `name` đặt tên task mới; `<attribute>` khai báo tham số dạng giá trị; `<element>` khai báo tham số dạng phần tử lồng; `<text>` khai báo vùng văn bản; `<sequential>` chứa các task sẽ chạy mỗi lần macro được gọi.

```xml
<macrodef name="say-hello">
    <attribute name="who" />
    <sequential>
        <echo message="Hello, @{who}!" />
    </sequential>
</macrodef>

<target name="demo">
    <say-hello who="Ant" />
</target>
```

Khi target `demo` chạy, Ant mở rộng macro và thực thi task `echo` với giá trị `who` được truyền vào. Cú pháp `@{who}` là phép thay thế tham số của macro. Nó khác `${property}`: `${...}` tham chiếu property của Ant, còn `@{...}` tham chiếu attribute hoặc text được khai báo trong macrodef.

Một macro có thể kết hợp cả hai loại giá trị:

```xml
<property name="build.dir" value="build" />

<macrodef name="make-module-dir">
    <attribute name="module" />
    <sequential>
        <mkdir dir="${build.dir}/@{module}" />
    </sequential>
</macrodef>

<target name="prepare">
    <make-module-dir module="core" />
    <make-module-dir module="web" />
</target>
```

Property `${build.dir}` lấy giá trị từ cấu hình project; `@{module}` lấy giá trị của lần gọi macro hiện tại. Vì vậy cùng một macro có thể tạo thư mục cho nhiều module.

## 2. Truyền một nested element có tên rõ ràng

Khi macro cần nhận một cấu trúc XML, hãy khai báo `<element name="..." />`. Trong phần `<sequential>`, đặt một phần tử cùng tên để chỉ vị trí Ant chèn nội dung do nơi gọi truyền vào.

Ví dụ macro sao chép một nhóm tệp:

```xml
<macrodef name="copy-selected-files">
    <attribute name="from" />
    <attribute name="to" />
    <element name="selection" />

    <sequential>
        <copy todir="@{to}">
            <fileset dir="@{from}">
                <selection />
            </fileset>
        </copy>
    </sequential>
</macrodef>
```

Nơi gọi truyền nội dung cho `selection`:

```xml
<target name="copy-config">
    <copy-selected-files from="src" to="build/config">
        <selection>
            <include name="**/*.xml" />
            <include name="**/*.properties" />
            <exclude name="**/draft/**" />
        </selection>
    </copy-selected-files>
</target>
```

Khi macro được mở rộng, nội dung của `<selection>` tại nơi gọi được đưa vào vị trí `<selection />` trong phần `<fileset>`. Nhờ vậy, macro chịu trách nhiệm cấu trúc chung của task `copy`, còn target gọi macro quyết định mẫu include/exclude.

Phần tử lồng có thể chứa nhiều phần tử con, chẳng hạn `<include>`, `<exclude>`, `<pathelement>`, `<fileset>` hoặc cấu hình mà task bên trong macro chấp nhận. Macro không cần biết chi tiết của mọi phần tử con; nó chỉ chuyển nguyên cấu trúc được cung cấp tới vị trí placeholder.

## 3. Phần tử lồng tùy chọn

Nếu một nested element không bắt buộc, khai báo `optional="true"`:

```xml
<macrodef name="copy-tree">
    <attribute name="from" />
    <attribute name="to" />
    <element name="selection" optional="true" />

    <sequential>
        <copy todir="@{to}">
            <fileset dir="@{from}">
                <selection />
            </fileset>
        </copy>
    </sequential>
</macrodef>
```

Có thể gọi macro mà không truyền `selection`:

```xml
<copy-tree from="src/assets" to="build/assets" />
```

Khi đó, placeholder tùy chọn không đóng góp nội dung bổ sung. Trong ví dụ, `fileset` không có include/exclude do người gọi truyền nên dùng phạm vi mặc định của nó.

Nếu element không được đánh dấu optional, người gọi phải cung cấp phần tử đó. Hãy chọn trạng thái bắt buộc hay tùy chọn theo ý nghĩa của macro: nếu thiếu cấu hình làm thao tác không xác định hoặc không an toàn, nên để element bắt buộc để Ant báo lỗi ngay tại nơi gọi.

## 4. Truyền nhiều loại nested element

Một macro có thể khai báo nhiều phần tử lồng với tên khác nhau. Mỗi phần tử được đặt tại vị trí riêng trong phần `<sequential>`. Khi placeholder cần chèn các phần tử con vào bên trong một nested element hiện có, hãy đặt nó ở đúng cấp để sau khi mở rộng, cấu trúc cuối cùng vẫn phù hợp với task Ant.

Ví dụ macro biên dịch Java nhận classpath và các tùy chọn compiler riêng:

```xml
<macrodef name="compile-java">
    <attribute name="src" />
    <attribute name="dest" />
    <element name="classpath" optional="true" />
    <element name="compiler-options" optional="true" />

    <sequential>
        <mkdir dir="@{dest}" />
        <javac srcdir="@{src}" destdir="@{dest}" includeantruntime="false">
            <classpath>
                <classpath />
            </classpath>
            <compiler-options />
        </javac>
    </sequential>
</macrodef>

<target name="compile-app">
    <compile-java src="src/main/java" dest="build/classes">
        <classpath>
            <pathelement location="lib/api.jar" />
            <fileset dir="lib/runtime">
                <include name="*.jar" />
            </fileset>
        </classpath>
        <compiler-options>
            <compilerarg value="-Xlint:unchecked" />
            <compilerarg value="-Xlint:deprecation" />
        </compiler-options>
    </compile-java>
</target>
```

Nội dung của `<classpath>` được chèn bên trong nested `<classpath>` của `javac`; các phần tử `<compilerarg>` được chèn trực tiếp vào `javac` tại vị trí `<compiler-options />`. Wrapper `compiler-options` chỉ là tên đầu vào của macro; sau khi mở rộng, nó không còn là một phần tử mà task `javac` phải hiểu.

Ở ví dụ này, người gọi có thể thay đổi thư viện và compiler options theo module mà không phải viết lại cấu trúc `javac`. Cách tổ chức tương tự có thể dùng để nhận `fileset`, `patternset`, formatter hoặc các cấu hình nested khác, miễn là placeholder được đặt ở đúng vị trí mà task cha chấp nhận.

## 5. Phần tử implicit là gì?

Thông thường, một nested element phải được bọc trong thẻ có tên đã khai báo. Ví dụ macro khai báo `<element name="steps" />` thì người gọi phải viết `<steps>...</steps>`.

Với `implicit="true"`, macro cho phép người gọi bỏ thẻ bao đó và đặt trực tiếp các task con bên trong lời gọi macro. Điều này hữu ích khi macro được thiết kế như một khối bao quanh một chuỗi task do caller quyết định.

```xml
<macrodef name="with-report-directory">
    <attribute name="dir" />
    <element name="actions" implicit="true" />

    <sequential>
        <mkdir dir="@{dir}" />
        <echo message="Preparing report directory @{dir}" />
        <actions />
    </sequential>
</macrodef>
```

Nơi gọi không cần viết `<actions>`:

```xml
<target name="generate-report">
    <with-report-directory dir="build/reports">
        <echo message="Creating XML report" />
        <xslt
            in="build/results/report.xml"
            out="build/reports/report.html"
            style="src/xsl/report.xsl" />
        <echo message="Report generated" />
    </with-report-directory>
</target>
```

Các task `echo` và `xslt` được caller đặt trực tiếp trở thành nội dung của element implicit. Trong macro body, placeholder `<actions />` là vị trí Ant chèn chuỗi task đó. Vì thế, macro kiểm soát những bước chung trước và sau, còn người gọi cung cấp công việc cụ thể ở giữa.

Một macro chỉ nên có một element được đánh dấu implicit. Nếu cần nhiều vùng nội dung có tên riêng, hãy dùng các element tường minh như `<before>`, `<actions>` và `<after>` để tránh nhập nhằng nội dung nào thuộc vị trí nào.

## 6. So sánh nested element tường minh và implicit element

Hai cách truyền element giải quyết các nhu cầu khác nhau:

| Cách khai báo | Cách gọi macro | Khi phù hợp |
|---|---|---|
| `<element name="files" />` | `<files>...</files>` | Caller truyền một cấu trúc có ý nghĩa cụ thể, ví dụ fileset hoặc classpath |
| `<element name="actions" implicit="true" />` | Đặt trực tiếp task con bên trong macro call | Macro đóng vai trò wrapper quanh một chuỗi task do caller quyết định |
| `<element name="options" optional="true" />` | Có thể bỏ `<options>` | Cấu hình bổ sung không bắt buộc |

Element tường minh giúp buildfile dễ đọc khi macro nhận nhiều nhóm cấu hình. Implicit element làm lời gọi ngắn và tự nhiên hơn, nhưng cũng làm tên của nhóm task do macro bao bọc ít hiển thị hơn. Nếu macro có nhiều mục đích hoặc nhiều vùng chèn nội dung, ưu tiên element có tên riêng.

## 7. Truyền nội dung text bằng thẻ text

Khi macro cần nhận một đoạn văn bản thay vì một phần tử XML, khai báo `<text name="..." />`. Nội dung nằm trực tiếp giữa thẻ mở và thẻ đóng của macro sẽ được gán cho tên text đó.

```xml
<macrodef name="log-message">
    <attribute name="level" default="INFO" />
    <text name="message" trim="true" />

    <sequential>
        <echo message="[@{level}] @{message}" />
    </sequential>
</macrodef>

<target name="demo-log">
    <log-message level="WARN">Disk space is low</log-message>
</target>
```

Macro nhận:

- `level` từ attribute của lời gọi, hoặc dùng giá trị mặc định `INFO` nếu caller bỏ qua.
- `message` từ nội dung text giữa hai thẻ.
- `trim="true"` yêu cầu loại bỏ khoảng trắng ở đầu và cuối đoạn text trước khi thay thế.

Trong macro body, `@{message}` được thay bằng văn bản caller truyền vào. Text phù hợp cho thông báo, nhãn, mô tả hoặc một đoạn giá trị đơn giản. Nếu cần truyền một cấu trúc gồm nhiều task hay cấu hình con, hãy dùng nested element.

## 8. Text nhiều dòng và khoảng trắng

Nội dung text có thể chứa nhiều dòng:

```xml
<macrodef name="write-notice">
    <attribute name="file" />
    <text name="content" trim="true" />

    <sequential>
        <echo file="@{file}" message="@{content}" />
    </sequential>
</macrodef>

<target name="create-notice">
    <write-notice file="build/NOTICE.txt">
        This artifact is generated by the build.
        Check the release metadata before distribution.
    </write-notice>
</target>
```

Khi text nhiều dòng, xuống dòng và khoảng trắng có thể trở thành một phần của giá trị truyền vào. Nếu định dạng đầu ra cần giữ chính xác khoảng trắng, không bật trim một cách tùy tiện; hãy thử với nội dung có dòng trống, thụt lề và dấu cách ở cuối dòng.

`trim` điều khiển việc loại bỏ khoảng trắng ở hai đầu vùng text, không phải một công cụ định dạng nội dung nhiều dòng. Nó không thay thế các thao tác chuẩn hóa newline hoặc chuyển đổi encoding.

Nếu nội dung text có ký tự XML đặc biệt như `<`, `>` hoặc `&`, phải escape theo cú pháp XML:

```xml
<log-message level="INFO">Use &lt;target&gt; to declare a target.</log-message>
```

Không thể đặt một thẻ XML tùy ý trong vùng text rồi mong macro coi nó là chuỗi thuần. Nếu cần truyền markup/task, khai báo nested element tương ứng.

## 9. Kết hợp attribute, nested element và text

Một macro có thể nhận đồng thời nhiều loại đầu vào. Ví dụ, macro tạo một báo cáo nhận tên báo cáo qua attribute, nhận classpath qua nested element, nhận một nhóm test qua element khác và nhận mô tả qua text:

```xml
<macrodef name="run-test-suite">
    <attribute name="suite" />
    <attribute name="reportdir" default="build/reports" />
    <element name="classpath" optional="true" />
    <element name="test-files" />
    <text name="description" optional="true" trim="true" />

    <sequential>
        <echo message="Running suite @{suite}: @{description}" />
        <mkdir dir="@{reportdir}" />

        <junit fork="true" haltonfailure="true" printsummary="yes">
            <classpath>
                <pathelement location="build/classes/main" />
                <classpath />
            </classpath>
            <formatter type="plain" />
            <batchtest todir="@{reportdir}/@{suite}">
                <test-files />
            </batchtest>
        </junit>
    </sequential>
</macrodef>
```

Caller cung cấp từng phần:

```xml
<target name="unit-tests">
    <run-test-suite suite="unit" reportdir="build/reports">
        <classpath>
            <pathelement location="build/classes/unit" />
            <pathelement location="lib/junit.jar" />
        </classpath>

        <test-files>
            <fileset dir="build/classes/unit">
                <include name="**/*Test.class" />
            </fileset>
        </test-files>

        Fast unit test suite for the core module.
    </run-test-suite>
</target>
```

Ở đây:

- `suite` và `reportdir` là attribute.
- `classpath` là nested element có tên rõ ràng.
- `test-files` là nested element chứa fileset.
- Nội dung văn bản ở cuối lời gọi là `description`.
- `sequential` xác định cách ghép các giá trị đó vào task `junit`.

Ví dụ minh họa cách truyền dữ liệu cho macro; cấu hình JUnit thực tế cần tương thích với phiên bản JUnit/Ant được dùng và quy tắc chọn test class của dự án.

## 10. Phân biệt macro text với property expansion

Ant có nhiều lớp thay thế giá trị, và dễ nhầm lẫn khi dùng macro:

| Cú pháp | Ý nghĩa | Ví dụ |
|---|---|---|
| `${name}` | Property của Ant | `${build.dir}` |
| `@{name}` | Attribute hoặc text parameter của macro | `@{module}` |
| `<element-name />` trong macro body | Vị trí chèn nội dung nested element | `<classpath />` |
| XML text giữa thẻ macro | Nội dung được nhận bởi khai báo `<text>` | `<log>Build started</log>` |

Ví dụ kết hợp property và macro attribute:

```xml
<property name="output.root" value="build/output" />

<macrodef name="make-output">
    <attribute name="module" />
    <sequential>
        <mkdir dir="${output.root}/@{module}" />
    </sequential>
</macrodef>
```

Property expansion và macro expansion diễn ra trong quá trình Ant cấu hình và mở rộng macro. Khi giá trị truyền vào chứa chuỗi có dạng `${...}` hoặc `@{...}`, cần hiểu cơ chế mở rộng của phiên bản Ant và thuộc tính `doubleexpanding` nếu macro có dùng giá trị qua nhiều tầng. Không nên truyền chuỗi có cú pháp expansion lồng nhau mà không xác định rõ nó cần được mở rộng ở tầng nào.

## 11. Element implicit và phạm vi nội dung

Implicit element gom các phần tử con trực tiếp của lời gọi macro vào một vùng nội dung đã khai báo. Điều đó không có nghĩa mọi phần tử XML ở bất kỳ cấp nào trong lời gọi đều được chuyển thành implicit content; chỉ các phần tử con ở vị trí lời gọi macro mới thuộc vùng này.

Ví dụ:

```xml
<macrodef name="around-task">
    <attribute name="label" />
    <element name="body" implicit="true" />
    <sequential>
        <echo message="Begin @{label}" />
        <body />
        <echo message="End @{label}" />
    </sequential>
</macrodef>

<target name="demo">
    <around-task label="compile">
        <mkdir dir="build/classes" />
        <javac srcdir="src" destdir="build/classes" />
    </around-task>
</target>
```

Các task `mkdir` và `javac` là nội dung implicit. Chúng được chèn vào đúng vị trí `<body />`, giữa hai task `echo`. Macro không tự chuyển các phần tử con bên trong một nested element tường minh khác thành nội dung implicit của nó.

Vì implicit element nhận trực tiếp các task caller cung cấp, hãy đặt nó ở vị trí trong macro body phù hợp với loại nội dung mà caller được phép truyền. Ví dụ, nếu macro đặt `<body />` bên trong `<sequential>`, caller có thể truyền một chuỗi task. Nếu đặt placeholder trong `<fileset>`, nội dung caller phải phù hợp với nested elements mà `fileset` chấp nhận.

## 12. Khi nào nên dùng từng cách truyền dữ liệu?

Chọn cách truyền dựa trên bản chất dữ liệu:

| Nhu cầu | Cách dùng | Ví dụ |
|---|---|---|
| Một giá trị đơn | `<attribute>` | Tên module, đường dẫn, chế độ |
| Một cấu hình XML có kiểu rõ ràng | `<element>` | Classpath, fileset, formatter |
| Một chuỗi task tùy biến do caller quyết định | `<element implicit="true">` | Các bước trước/sau trong wrapper macro |
| Một đoạn văn bản | `<text>` | Thông báo, mô tả, nội dung notice |
| Cấu hình có thể bỏ qua | `optional="true"` trên element/text hoặc `default` trên attribute | Classpath bổ sung hoặc mô tả tùy chọn |

Tránh dùng text để truyền một cấu trúc XML cần Ant thực thi. Tránh dùng implicit element khi macro có nhiều vùng chèn nội dung độc lập. Dùng element có tên riêng khi người đọc cần thấy rõ caller đang cung cấp loại cấu hình nào.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ant báo thiếu nested element | Element không optional nhưng lời gọi macro không truyền nó | Thêm element bắt buộc hoặc khai báo `optional="true"` nếu thực sự có thể bỏ qua |
| Nội dung nested không xuất hiện trong task | Tên placeholder trong `sequential` không khớp tên khai báo | Dùng cùng tên trong `<element name>` và placeholder |
| Caller phải viết wrapper dù muốn truyền task trực tiếp | Element chưa được đánh dấu `implicit="true"` | Đánh dấu một element là implicit nếu thiết kế macro chỉ cần một vùng nội dung không bọc |
| Các task caller truyền được đặt sai vị trí | Placeholder nằm ở sai cấp trong macro body | Đặt placeholder tại vị trí mà task cha thực sự chấp nhận các nested element đó |
| Text bị mất khoảng trắng đầu/cuối | Đã bật `trim="true"` | Bỏ trim nếu nội dung cần giữ khoảng trắng biên |
| Text có ký tự `<` hoặc `&` làm XML lỗi | Chưa escape ký tự đặc biệt | Dùng `&lt;`, `&gt;`, `&amp;` hoặc CDATA khi thích hợp |
| `${...}` bị thay bằng giá trị property ngoài ý muốn | Nhầm property expansion với macro parameter | Dùng `@{...}` cho attribute/text của macro và kiểm soát expansion lồng nhau |
| Macro khó gọi vì có quá nhiều phần tử lồng | Macro đang nhận nhiều vùng cấu hình khác nhau nhưng tên hoặc trách nhiệm chưa rõ | Chia macro theo trách nhiệm hoặc dùng element có tên mô tả rõ |
| Implicit content nhận task không phù hợp | Macro cho phép caller truyền nội dung quá tự do | Dùng nested element tường minh để giới hạn cấu trúc và làm rõ hợp đồng |

Khi một macro không mở rộng như mong muốn, hãy kiểm tra khai báo đầu vào trước: attribute, element và text đã được định nghĩa chưa; tên placeholder có khớp không; element có optional/implicit đúng mục đích không; và nội dung sau khi chèn có hợp lệ ở vị trí task nhận nó không.

## 14. Quy trình thiết kế macro có nested element và text

Khi tạo macro để tái sử dụng trong buildfile, có thể tiến hành theo trình tự sau:

1. Xác định phần logic build cố định và phần dữ liệu thay đổi giữa các lần gọi.
2. Dùng `<attribute>` cho các giá trị đơn như tên, thư mục, cờ hoặc chế độ; đặt `default` nếu có giá trị mặc định hợp lý.
3. Dùng `<element>` cho cấu hình XML có cấu trúc và đặt placeholder cùng tên trong `<sequential>`.
4. Đặt `optional="true"` chỉ khi macro có hành vi hợp lệ khi thiếu element.
5. Dùng `implicit="true"` khi caller cần truyền trực tiếp một chuỗi task vào một vùng duy nhất của macro.
6. Dùng `<text>` cho nội dung văn bản và quyết định rõ có cần `trim` hay không.
7. Đặt placeholder ở đúng vị trí nested element mà task bên trong chấp nhận.
8. Gọi macro với một trường hợp tối thiểu, một trường hợp có đủ phần tử tùy chọn và một trường hợp có text nhiều dòng.

`macrodef` cho phép đóng gói quy trình build mà vẫn giữ quyền cấu hình cho nơi gọi. Attribute truyền giá trị đơn, nested element truyền cấu trúc XML, implicit element nhận chuỗi task trực tiếp và text nhận nội dung văn bản. Chọn đúng loại đầu vào giúp macro dễ đọc, dễ gọi lại và thể hiện rõ hợp đồng giữa phần logic dùng chung với target sử dụng nó.
