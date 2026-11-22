# Tham số mặc định, doubleexpanding và escape trong macro

Trong Apache Ant, `<macrodef>` cho phép định nghĩa một task mới từ một chuỗi task mẫu nằm trong `<sequential>`. Macro hữu ích khi nhiều target cần lặp lại cùng một nhóm thao tác, chẳng hạn tạo thư mục, copy resource, gọi compiler hoặc chạy một công cụ. Thay vì sao chép nguyên chuỗi task ở nhiều nơi, ta định nghĩa macro một lần rồi gọi nó với các tham số khác nhau.

Macro nhận tham số thông qua các phần tử `<attribute>`. Trong thân macro, giá trị của tham số được chèn bằng cú pháp `@{ten-tham-so}`. Một attribute có thể có giá trị mặc định bằng thuộc tính `default`; có thể điều khiển việc mở rộng property trong giá trị truyền vào bằng `doubleexpanding`; và có thể viết ký tự `@{...}` theo nghĩa đen bằng cơ chế escape `@@`.

Ba cơ chế này giải quyết ba tình huống khác nhau:

- `default`: cho phép người gọi bỏ qua một tham số và dùng giá trị đã định nghĩa sẵn.
- `doubleexpanding`: quyết định property reference trong giá trị attribute được mở rộng một lần hay hai lần.
- `@@`: ngăn Ant coi một chuỗi `@{...}` là placeholder cần thay thế của macro.

## 1. Cấu trúc cơ bản của `<macrodef>`

Một macro gồm tên task mới, các attribute đầu vào và phần thân `<sequential>`:

~~~xml
<macrodef name="prepare-output">
    <attribute name="directory"/>
    <sequential>
        <mkdir dir="@{directory}"/>
        <echo message="Prepared directory: @{directory}"/>
    </sequential>
</macrodef>
~~~

Sau khi định nghĩa, có thể gọi macro như một task Ant:

~~~xml
<target name="prepare">
    <prepare-output directory="build/classes"/>
    <prepare-output directory="build/reports"/>
</target>
~~~

Mỗi lần gọi `prepare-output` thực hiện chuỗi task trong `<sequential>` với giá trị attribute tương ứng. Lần gọi đầu tạo `build/classes`; lần gọi sau tạo `build/reports`.

Các điểm cần nhớ:

- `<macrodef>` định nghĩa task mới; nó không tự chạy phần thân khi được khai báo.
- `<attribute>` khai báo tham số mà macro nhận.
- `@{directory}` là vị trí chèn giá trị attribute vào task mẫu.
- Nếu attribute không có `default`, người gọi phải cung cấp giá trị.
- `<sequential>` xác định thứ tự các task được thực hiện trong mỗi lần gọi macro.

Tên attribute không phân biệt chữ hoa và chữ thường khi được tham chiếu. Dù vậy, nên giữ cách viết nhất quán, thường dùng chữ thường và tên có ý nghĩa để build file dễ đọc.

## 2. Attribute bắt buộc và giá trị mặc định

Nếu khai báo attribute mà không có `default`, attribute đó là bắt buộc:

~~~xml
<macrodef name="compile-module">
    <attribute name="source"/>
    <attribute name="destination"/>
    <sequential>
        <mkdir dir="@{destination}"/>
        <javac srcdir="@{source}"
               destdir="@{destination}"
               includeantruntime="false"/>
    </sequential>
</macrodef>
~~~

Người gọi phải truyền cả hai attribute:

~~~xml
<compile-module source="src/main/java"
                destination="build/classes"/>
~~~

Nếu thiếu `source` hoặc `destination`, Ant báo lỗi khi thực hiện macro vì không nhận được attribute bắt buộc.

Để cho phép người gọi bỏ qua một attribute, khai báo `default`:

~~~xml
<macrodef name="prepare-output">
    <attribute name="directory" default="build/output"/>
    <sequential>
        <mkdir dir="@{directory}"/>
        <echo message="Output directory: @{directory}"/>
    </sequential>
</macrodef>
~~~

Có thể gọi mà không truyền `directory`:

~~~xml
<prepare-output/>
~~~

Khi đó macro sử dụng `build/output`. Nếu truyền giá trị riêng, giá trị người gọi cung cấp được dùng thay cho default:

~~~xml
<prepare-output directory="build/reports"/>
~~~

Giá trị `build/reports` được dùng cho lần gọi này. Giá trị mặc định chỉ là fallback, không phải giá trị cố định áp đặt lên mọi lần gọi.

### 2.1. Dùng property trong giá trị mặc định

Default có thể chứa property của Ant. Ví dụ:

~~~xml
<property name="build.dir" location="build"/>

<macrodef name="make-classes-dir">
    <attribute name="directory" default="${build.dir}/classes"/>
    <sequential>
        <mkdir dir="@{directory}"/>
        <echo message="Classes directory: @{directory}"/>
    </sequential>
</macrodef>

<target name="prepare">
    <make-classes-dir/>
</target>
~~~

Macro sử dụng `${build.dir}/classes` làm giá trị mặc định. Khi `build.dir` là `build`, thư mục được tạo là `build/classes`.

Có thể truyền một đường dẫn khác khi cần:

~~~xml
<make-classes-dir directory="build/classes-debug"/>
~~~

Khi dự án có nhiều macro cùng dùng thư mục gốc, property giúp thay đổi cấu hình ở một nơi. Default vẫn cho phép người gọi tùy chỉnh một lần gọi cụ thể.

### 2.2. Giá trị mặc định có thể dựa trên attribute khai báo trước

Ant cho phép dùng attribute đã khai báo trước đó để tạo default cho attribute tiếp theo:

~~~xml
<macrodef name="package-module">
    <attribute name="module"/>
    <attribute name="destination" default="dist/@{module}.jar"/>
    <sequential>
        <echo message="Module: @{module}"/>
        <echo message="Destination: @{destination}"/>
    </sequential>
</macrodef>

<target name="package">
    <package-module module="core"/>
    <package-module module="web" destination="dist/web-app.jar"/>
</target>
~~~

Với lần gọi đầu, `module` là `core`, nên default của `destination` trở thành `dist/core.jar`. Lần gọi thứ hai truyền `destination` tường minh nên dùng `dist/web-app.jar`.

**Thứ tự khai báo có ý nghĩa.** Attribute dùng để tạo default phải được khai báo trước attribute tham chiếu đến nó:

~~~xml
<macrodef name="example">
    <attribute name="first"/>
    <attribute name="second" default="@{first}"/>
    <sequential>
        <echo message="first=@{first}; second=@{second}"/>
    </sequential>
</macrodef>
~~~

Khi gọi `<example first="value"/>`, cả `first` và `second` đều có giá trị `value`. Nếu đảo thứ tự khai báo, tại thời điểm xử lý default của `second`, attribute `first` chưa được thiết lập; Ant không thể dùng giá trị của nó theo cách trên.

### 2.3. Default rỗng và attribute tùy chọn

Có thể đặt default là chuỗi rỗng nếu macro cần cho phép bỏ qua attribute nhưng vẫn muốn placeholder có giá trị:

~~~xml
<macrodef name="run-check">
    <attribute name="config" default=""/>
    <sequential>
        <echo message="Config argument: @{config}"/>
    </sequential>
</macrodef>
~~~

Khi gọi `<run-check/>`, `@{config}` được thay bằng chuỗi rỗng. Điều này khác với attribute bắt buộc bị thiếu: với default rỗng, người gọi đã được phép bỏ qua tham số.

Hãy cân nhắc task bên trong có chấp nhận chuỗi rỗng hay không. Nếu task cần một đường dẫn hợp lệ, default rỗng có thể khiến lỗi chỉ xuất hiện ở bước thực thi sau đó. Trong trường hợp ấy, default có ý nghĩa như `config/default.xml` hoặc một giá trị bắt buộc rõ ràng thường dễ hiểu hơn.

## 3. Phân biệt `${property}` và `@{attribute}`

Trong build file Ant, hai cú pháp này có vai trò khác nhau:

| Cú pháp | Ý nghĩa | Nguồn giá trị |
|---|---|---|
| `${build.dir}` | Property expansion | Property của Ant |
| `@{directory}` | Macro attribute substitution | Attribute truyền vào macro hoặc giá trị default |
| `@@{directory}` | Escape macro placeholder | Giữ lại chuỗi literal `@{directory}` |
| `$${build.dir}` | Escape property expansion | Giữ lại chuỗi literal `${build.dir}` sau một lượt mở rộng |

Ví dụ:

~~~xml
<property name="build.dir" value="build"/>

<macrodef name="show-location">
    <attribute name="directory" default="${build.dir}/classes"/>
    <sequential>
        <echo message="Ant property: ${build.dir}"/>
        <echo message="Macro attribute: @{directory}"/>
    </sequential>
</macrodef>

<show-location/>
~~~

Trong macro:

- `${build.dir}` lấy property `build.dir` của project.
- `@{directory}` lấy attribute `directory` của lần gọi macro; nếu không truyền, nó dùng default.

Không dùng `${directory}` để tham chiếu macro attribute. Nếu project không có property tên `directory`, biểu thức đó sẽ không nhận giá trị attribute của macro.

## 4. `doubleexpanding` là gì?

Từ Apache Ant 1.8.3, `<attribute>` của `<macrodef>` có thuộc tính `doubleexpanding`. Thuộc tính này quyết định property reference nằm trong giá trị attribute được mở rộng hai lần hay chỉ một lần.

Giá trị mặc định là `true`:

~~~xml
<macrodef name="show-message">
    <attribute name="message"/>
    <sequential>
        <echo message="@{message}"/>
    </sequential>
</macrodef>
~~~

Khi macro được gọi, Ant thực hiện property expansion trước khi thay macro attribute và thêm một lượt property expansion sau khi thay placeholder `@{...}`. Hành vi hai lượt này hỗ trợ những macro cần giá trị property được hình thành thông qua bước thay thế attribute.

Trong phần lớn macro thông thường, người viết chỉ muốn chèn giá trị người gọi đã cung cấp. Nhưng nếu giá trị đó chứa một chuỗi trông giống property reference, lượt mở rộng thứ hai có thể đánh giá nó thành giá trị property thật. Đây là lý do cần hiểu `doubleexpanding` khi muốn truyền nguyên văn `${...}` qua macro.

### 4.1. Ví dụ property bị mở rộng hai lần

Giả sử project có property `basedir` do Ant cung cấp. Macro sau dùng mặc định `doubleexpanding="true"`:

~~~xml
<macrodef name="echo-value">
    <attribute name="message"/>
    <sequential>
        <echo message="@{message}"/>
    </sequential>
</macrodef>

<target name="show">
    <echo message="Ant basedir is ${basedir}"/>
    <echo-value message="$${basedir}"/>
</target>
~~~

`$${basedir}` dùng escape property ở lượt đầu để tạo ra chuỗi `${basedir}`. Khi macro thay `@{message}`, chuỗi `${basedir}` được đưa vào task `<echo>`. Do `doubleexpanding` mặc định là `true`, lượt property expansion tiếp theo đánh giá `${basedir}` và in ra giá trị thư mục thực tế.

Kết quả là dòng thứ hai cũng in giá trị `basedir`, thay vì in nguyên văn `${basedir}`. Đây là hành vi được Ant FAQ mô tả cho macro attribute.

### 4.2. Tắt double expansion

Nếu muốn property reference được truyền qua macro dưới dạng văn bản, đặt `doubleexpanding="false"` trên attribute:

~~~xml
<macrodef name="echo-literal">
    <attribute name="message" doubleexpanding="false"/>
    <sequential>
        <echo message="@{message}"/>
    </sequential>
</macrodef>

<target name="show-literal">
    <echo-literal message="$${basedir}"/>
</target>
~~~

Với `doubleexpanding="false"`, Ant chỉ thực hiện lượt property expansion đầu tiên. `$${basedir}` trở thành `${basedir}`, nhưng lượt mở rộng sau khi thay macro attribute bị bỏ qua cho attribute này. Vì vậy, nội dung được in ra là chuỗi literal `${basedir}`.

Tùy chọn này hữu ích khi macro cần chuyển tiếp biểu thức property cho một task hoặc file cấu hình xử lý ở giai đoạn sau, hoặc khi chuỗi `${...}` là nội dung cần giữ nguyên.

### 4.3. `doubleexpanding` được đặt trên từng attribute

Có thể chọn chính sách khác nhau cho từng tham số:

~~~xml
<macrodef name="write-template">
    <attribute name="output"/>
    <attribute name="template-text" doubleexpanding="false"/>
    <sequential>
        <echo file="@{output}" message="@{template-text}"/>
    </sequential>
</macrodef>
~~~

Ở đây `output` vẫn dùng mặc định double expansion; `template-text` tắt lượt thứ hai để giữ nguyên property-like syntax trong nội dung template. Điều này giúp macro kiểm soát riêng tham số nào cần được Ant đánh giá và tham số nào chỉ là dữ liệu văn bản.

`doubleexpanding` không phải thuộc tính của toàn bộ `<macrodef>`; nó được khai báo trên từng phần tử `<attribute>`. Nó được hỗ trợ từ Ant 1.8.3. Nếu build phải chạy với Ant cũ hơn, không thể dựa vào thuộc tính này; cần kiểm tra phiên bản Ant tối thiểu hoặc thiết kế cách truyền dữ liệu khác.

## 5. Escape macro placeholder bằng `@@`

Trong thân macro, `@{name}` có ý nghĩa là thay thế bằng giá trị attribute `name`. Nếu muốn tạo ra chuỗi literal `@{name}` mà không thay thế, dùng `@@{name}`:

~~~xml
<macrodef name="show-token">
    <attribute name="name"/>
    <sequential>
        <echo message="Expanded token: @{name}"/>
        <echo message="Literal token: @@{name}"/>
    </sequential>
</macrodef>

<target name="demo">
    <show-token name="module"/>
</target>
~~~

Dòng đầu in `module`. Dòng thứ hai in nguyên văn `@{name}`. Cặp `@@` được dùng để escape ký tự `@` và ngăn Ant coi chuỗi tiếp theo là macro placeholder.

Cơ chế này tương ứng với escape property bằng `$$`:

| Muốn giữ nguyên | Cú pháp escape | Ý nghĩa |
|---|---|---|
| `@{name}` | `@@{name}` | Không thay macro attribute `name` |
| `${build.dir}` | `$${build.dir}` | Không mở rộng property trong lượt expansion đó |

Đây là hai bộ ký hiệu khác nhau. `@@` escape ký tự `@` cho macro attribute; `$$` escape ký tự `$` cho property expansion. Không dùng lẫn hai cách.

## 6. Kết hợp default, doubleexpanding và escape

Một macro có thể vừa có default, vừa giữ một tham số dạng literal, vừa thay một macro attribute khác:

~~~xml
<property name="build.dir" location="build"/>

<macrodef name="write-config-example">
    <attribute name="file" default="${build.dir}/config/example.txt"/>
    <attribute name="property-expression" default="$${build.dir}"
               doubleexpanding="false"/>
    <sequential>
        <mkdir dir="${build.dir}/config"/>
        <echo file="@{file}"
              message="Property expression: @{property-expression}; macro token: @@{file}"/>
    </sequential>
</macrodef>

<target name="generate-example">
    <write-config-example/>
</target>
~~~

Trong ví dụ:

- `file` có default là `${build.dir}/config/example.txt`, nên người gọi không cần truyền đường dẫn.
- `property-expression` có default `$${build.dir}` và tắt double expansion để giữ `${build.dir}` dưới dạng literal.
- `@{file}` được thay bằng đường dẫn file thực tế.
- `@@{file}` được giữ lại thành chuỗi `@{file}`.

Ví dụ này minh họa ba lớp xử lý riêng. Trong build thực tế, cần kiểm tra thời điểm property được thiết lập và nội dung cần ghi ra file để bảo đảm kết quả đúng với mục đích.

## 7. Default của attribute và thứ tự khai báo

Khi một default tham chiếu attribute khác, thứ tự trong macro definition rất quan trọng:

~~~xml
<macrodef name="report-paths">
    <attribute name="module"/>
    <attribute name="report-dir" default="build/reports/@{module}"/>
    <attribute name="summary-file" default="@{report-dir}/summary.txt"/>
    <sequential>
        <echo message="Module: @{module}"/>
        <echo message="Report directory: @{report-dir}"/>
        <echo message="Summary: @{summary-file}"/>
    </sequential>
</macrodef>

<target name="reports">
    <report-paths module="api"/>
</target>
~~~

Ở đây:

1. `module` là attribute bắt buộc.
2. `report-dir` có default được tạo từ `module` đã khai báo trước.
3. `summary-file` có default được tạo từ `report-dir` đã khai báo trước.
4. Macro body sử dụng các giá trị đã được xác định.

Nếu một attribute default phụ thuộc vào một attribute khác, hãy khai báo attribute nguồn trước. Điều này giúp người đọc hiểu chuỗi giá trị và tránh default nhận một placeholder chưa được thiết lập.

Không nên tạo chuỗi phụ thuộc quá dài giữa nhiều default. Nếu macro có quá nhiều tham số suy ra từ nhau, cân nhắc dùng property ở project scope hoặc chia macro thành các bước nhỏ hơn để cấu hình dễ đọc.

## 8. Macro có nested element và text

Ngoài attribute, macro còn có thể nhận nested element để người gọi chèn một nhóm task vào vị trí xác định trong template:

~~~xml
<macrodef name="with-output-dir">
    <attribute name="dir" default="build/output"/>
    <element name="actions" optional="true"/>
    <sequential>
        <mkdir dir="@{dir}"/>
        <actions/>
    </sequential>
</macrodef>

<target name="generate">
    <with-output-dir dir="build/generated">
        <actions>
            <echo message="Generate files here"/>
        </actions>
    </with-output-dir>
</target>
~~~

`<element name="actions" optional="true"/>` khai báo nested element có thể được bỏ qua. Khi người gọi cung cấp `<actions>`, nội dung bên trong được chèn tại `<actions/>` trong macro body.

Có thể đặt `implicit="true"` để các nested element của lần gọi macro được đưa trực tiếp vào element đó mà không cần wrapper có tên:

~~~xml
<macrodef name="with-output-dir">
    <attribute name="dir" default="build/output"/>
    <element name="actions" optional="true" implicit="true"/>
    <sequential>
        <mkdir dir="@{dir}"/>
        <actions/>
    </sequential>
</macrodef>

<with-output-dir dir="build/generated">
    <echo message="Generate files here"/>
</with-output-dir>
~~~

Một macro chỉ có thể có một element implicit. Nested element là cách truyền cấu trúc task; không nên cố đưa toàn bộ XML task sequence vào attribute dạng chuỗi.

Nếu muốn nhận văn bản thuần nằm trực tiếp bên trong macro call, dùng `<text>`:

~~~xml
<macrodef name="write-message">
    <text name="content" trim="true"/>
    <sequential>
        <echo>@{content}</echo>
    </sequential>
</macrodef>

<write-message>
    Hello from a reusable macro
</write-message>
~~~

`trim="true"` loại khoảng trắng ở đầu và cuối phần text. Nếu không khai báo `<text>`, nội dung text trực tiếp bên trong macro invocation sẽ bị xem là không hợp lệ. Nested element và text có cơ chế riêng; `default` và `doubleexpanding` được áp dụng cho attribute, không phải cách cấu hình chung cho mọi loại nội dung.

## 9. Khi nào nên bật hoặc tắt doubleexpanding?

Có thể dùng các quy tắc thực tế sau:

| Tình huống | Cấu hình nên cân nhắc | Lý do |
|---|---|---|
| Attribute chứa đường dẫn/property cần được Ant giải quyết bình thường | Giữ mặc định `doubleexpanding="true"` | Hành vi tương thích mặc định của macrodef |
| Muốn truyền literal `${property}` qua macro | `doubleexpanding="false"` và escape `$` ở nơi gọi khi cần | Tránh lượt property expansion thứ hai |
| Muốn in literal `@{attribute}` từ macro body | Viết `@@{attribute}` | Tránh thay thế macro placeholder |
| Default phụ thuộc attribute trước đó | Khai báo attribute nguồn trước | Giá trị nguồn có sẵn khi Ant tạo default |
| Macro nhận task sequence tùy biến | Dùng `<element>` | Giữ cấu trúc task thay vì đóng gói XML thành chuỗi |
| Macro nhận văn bản thuần | Dùng `<text>` | Xác định cách Ant xử lý nested text |

Không nên đặt `doubleexpanding="false"` cho mọi attribute theo thói quen. Nếu giá trị cần property expansion bình thường, tắt lượt thứ hai có thể khiến chuỗi `${...}` còn nguyên và task nhận một đường dẫn chưa được giải quyết. Ngược lại, giữ `true` khi muốn bảo toàn literal property expression có thể khiến chuỗi bị đánh giá ngoài ý muốn.

Hãy quyết định dựa trên hợp đồng của từng attribute: nó nhận một giá trị đã được Ant mở rộng, hay nhận một đoạn văn bản cần chuyển tiếp nguyên trạng?

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ant báo thiếu attribute khi gọi macro | Attribute không có `default` và người gọi không truyền | Truyền giá trị hoặc khai báo default phù hợp |
| Giá trị default chứa `@{other}` nhưng không được thay | Attribute tham chiếu chưa được khai báo trước | Sắp xếp lại thứ tự khai báo attribute |
| `${...}` bị mở rộng thành giá trị ngoài ý muốn | Macro attribute dùng double expansion mặc định | Đặt `doubleexpanding="false"` cho attribute cần giữ literal |
| Muốn in `@{name}` nhưng nhận giá trị thay thế | Macro parser coi đó là placeholder | Dùng `@@{name}` trong macro body |
| `${property}` xuất hiện nguyên văn trong đường dẫn | Property expansion bị escape hoặc lượt mở rộng thứ hai bị tắt | Kiểm tra `$${...}` và `doubleexpanding` |
| Ant không nhận `doubleexpanding` | Phiên bản Ant thấp hơn 1.8.3 | Nâng Ant hoặc thiết kế macro không phụ thuộc thuộc tính này |
| Nested task bị báo lỗi | Macro chưa khai báo `<element>` hoặc element bắt buộc bị thiếu | Khai báo element và đặt `optional` đúng nhu cầu |
| Text trực tiếp trong macro invocation bị lỗi | Chưa khai báo `<text>` | Thêm `<text name="...">` hoặc chuyển nội dung sang nested element |
| Macro khó hiểu do quá nhiều default phụ thuộc nhau | Thiết kế tham số quá phức tạp | Đơn giản hóa interface hoặc tách macro |

Khi debug, hãy in giá trị macro attribute bằng `<echo>` trong thân macro, kiểm tra property có tồn tại trước khi gọi macro và thử riêng từng trường hợp: truyền tường minh, bỏ qua để dùng default, truyền literal `${...}` và in literal `@{...}`.

## 11. Ví dụ hoàn chỉnh: macro compile với default và tham số tùy chỉnh

Ví dụ sau định nghĩa macro compile có source directory bắt buộc, destination mặc định, encoding mặc định và một tham số tùy chọn để bật debug:

~~~xml
<project name="macro-build" default="compile-all">

    <property name="build.dir" location="build"/>

    <macrodef name="compile-java">
        <attribute name="source"/>
        <attribute name="destination" default="${build.dir}/classes"/>
        <attribute name="encoding" default="UTF-8"/>
        <attribute name="debug" default="true"/>
        <sequential>
            <mkdir dir="@{destination}"/>
            <echo message="Compile @{source} -> @{destination}"/>
            <javac srcdir="@{source}"
                   destdir="@{destination}"
                   encoding="@{encoding}"
                   debug="@{debug}"
                   includeantruntime="false"/>
        </sequential>
    </macrodef>

    <target name="compile-main">
        <compile-java source="src/main/java"/>
    </target>

    <target name="compile-test" depends="compile-main">
        <compile-java source="src/test/java"
                      destination="${build.dir}/test-classes"
                      debug="true"/>
    </target>

    <target name="compile-all" depends="compile-test"/>

</project>
~~~

Lần gọi `compile-main` chỉ truyền `source`; các attribute `destination`, `encoding` và `debug` dùng default. Lần gọi `compile-test` truyền `destination` riêng nhưng vẫn dùng default encoding và debug. Cả hai dùng chung một macro nên chuỗi task compile được định nghĩa một lần.

Ví dụ này minh họa tái sử dụng task sequence. Trong dự án thật, compile test thường cần classpath chứa class main và thư viện test; có thể mở rộng macro bằng nested element cho classpath hoặc tạo macro riêng nếu interface bắt đầu quá phức tạp.

## 12. Lưu ý về khả năng tương thích phiên bản Ant

`<macrodef>` có từ Ant 1.6. Một số tính năng được bổ sung ở các phiên bản sau:

| Tính năng | Phiên bản tối thiểu theo tài liệu Ant |
|---|---|
| `<macrodef>` | Ant 1.6 |
| `<attribute description="...">` | Ant 1.6.1 |
| `<element implicit="true">` | Ant 1.6.2 |
| `<attribute doubleexpanding="...">` | Ant 1.8.3 |
| `<text>` | Ant 1.6.1 |

Nếu build cần chạy trên nhiều agent, hãy thống nhất phiên bản Ant tối thiểu. Một build file dùng `doubleexpanding` nhưng chạy trên Ant cũ có thể không được chấp nhận. Nên ghi rõ phiên bản Ant trong hướng dẫn dự án và kiểm tra `ant -version` trên CI.

## 13. Nguyên tắc thiết kế macro dễ bảo trì

- Chỉ khai báo attribute mà macro thực sự cần.
- Dùng default cho giá trị phổ biến, ổn định và có ý nghĩa.
- Để attribute bắt buộc khi không có default an toàn.
- Khai báo attribute nguồn trước attribute có default tham chiếu nó.
- Dùng `@{name}` cho macro attribute, `${name}` cho Ant property.
- Chỉ tắt double expansion cho attribute cần giữ property reference nguyên văn.
- Dùng `@@{...}` khi macro body phải tạo chuỗi literal giống placeholder.
- Dùng nested `<element>` để nhận task sequence và `<text>` để nhận văn bản.
- Giữ macro có một trách nhiệm rõ ràng; không biến nó thành một build language quá phức tạp.
- Ghi mô tả cho attribute khi macro được dùng bởi nhiều nhóm hoặc nhiều build file.

Macro tốt giúp build file ngắn hơn và đồng nhất hơn. Nếu mỗi lần gọi phải truyền quá nhiều tham số hoặc phải hiểu nhiều lớp escape, có thể interface macro đang quá phức tạp. Khi đó, hãy đưa giá trị dùng chung vào property/reference hoặc chia macro thành các đơn vị nhỏ hơn.

## Kết luận

Trong `<macrodef>`, attribute không có `default` là bắt buộc; có `default` thì người gọi được phép bỏ qua và dùng giá trị dự phòng. Macro thay attribute bằng cú pháp `@{name}`. Thuộc tính `doubleexpanding` trên từng attribute quyết định property reference được mở rộng hai lần hay một lần; mặc định là `true`, còn `false` hữu ích khi cần giữ literal `${...}` sau khi truyền qua macro. Để giữ nguyên macro placeholder `@{name}` trong thân macro, dùng `@@{name}`. Nắm rõ ba cơ chế này giúp tạo macro tái sử dụng có interface rõ ràng và tránh việc property hoặc placeholder bị mở rộng ngoài ý muốn.

## Tài liệu tham khảo

- [Apache Ant MacroDef Task](https://ant.apache.org/manual/Tasks/macrodef.html)
- [Apache Ant FAQ – Properties are expanded twice in my macrodef'ed tasks](https://ant.apache.org/faq.html)
- [Apache Ant Property Expansion](https://ant.apache.org/manual/properties.html)