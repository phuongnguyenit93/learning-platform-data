# Cấu trúc XML: phần tử, thuộc tính, nội dung lồng và chú thích

Apache Ant sử dụng XML để mô tả build file. Các chỉ dẫn như project, target và task được biểu diễn bằng phần tử XML; thông tin cấu hình được đặt trong thuộc tính hoặc nội dung lồng bên trong phần tử. Chú thích XML giúp người viết giải thích mục đích của cấu hình mà không làm thay đổi công việc Ant thực thi.

Hiểu cấu trúc XML giúp bạn đọc và viết `build.xml` đúng cú pháp, xác định task nào đang được thực thi, phân biệt cấu hình của task với task con, đồng thời xử lý những lỗi thường gặp như thiếu thẻ đóng, đặt sai thuộc tính hoặc dùng ký tự đặc biệt chưa được escape.

## 1. XML trong build file Ant

XML là ngôn ngữ đánh dấu có cấu trúc. Một tài liệu XML được tạo thành từ các phần tử, thuộc tính, nội dung văn bản và có thể có chú thích. XML quy định cú pháp chung; Ant quy định ý nghĩa của những phần tử cụ thể được dùng trong build file.

Ví dụ:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="sample" default="build" basedir=".">
    <target name="build">
        <echo message="Building the project"/>
    </target>
</project>
```

Trong ví dụ này, XML parser trước tiên đọc cấu trúc tài liệu. Sau đó Ant diễn giải `<project>` là project build, `<target>` là một target và `<echo>` là task in thông báo. Cùng một cú pháp XML có thể mô tả nhiều loại dữ liệu khác nhau; chính ngữ cảnh Ant quyết định phần tử nào có ý nghĩa build.

Một build file cần tuân thủ cả hai lớp quy tắc:

- Quy tắc XML: tài liệu phải well-formed, nghĩa là cấu trúc thẻ, thuộc tính, ký tự và thứ tự phần tử hợp lệ.
- Quy tắc Ant: phần tử, thuộc tính và nội dung lồng phải được Ant hỗ trợ trong vị trí đang sử dụng.

Một tệp có thể hợp lệ về cú pháp XML nhưng vẫn lỗi khi Ant thực thi nếu dùng tên task không tồn tại, đặt thuộc tính sai hoặc lồng phần tử mà task không hỗ trợ.

## 2. Phần tử XML

Phần tử (element) là đơn vị cấu trúc cơ bản của XML. Một phần tử thường có thẻ mở, nội dung và thẻ đóng:

```xml
<target name="build">
    <echo message="Building"/>
</target>
```

`<target>` là thẻ mở, `</target>` là thẻ đóng và phần nội dung nằm giữa hai thẻ là các phần tử con. Tên phần tử được viết sau dấu `<` ở thẻ mở và sau `</` ở thẻ đóng.

### 2.1. Thẻ mở và thẻ đóng

Phần tử có nội dung hoặc phần tử con phải được đóng đúng tên:

```xml
<target name="compile">
    <echo message="Start compiling"/>
</target>
```

Các lỗi như thiếu `</target>`, viết nhầm `</project>` hoặc đặt sai thứ tự đóng thẻ sẽ khiến XML không well-formed. XML không tự suy đoán thẻ đóng mà người viết định sử dụng.

Phần tử XML phân biệt chữ hoa và chữ thường. Vì vậy `<target>` và `<Target>` là hai tên khác nhau. Với các phần tử Ant, hãy dùng đúng cách viết tên task và cấu trúc mà tài liệu Ant quy định.

### 2.2. Phần tử rỗng

Nếu một phần tử không có nội dung và không có phần tử con, XML cho phép viết dạng tự đóng:

```xml
<echo message="Build started"/>
```

Dạng trên tương đương với:

```xml
<echo message="Build started"></echo>
```

Trong build file Ant, các task không cần nội dung lồng thường được viết bằng dạng tự đóng để ngắn gọn. Không được bỏ dấu `/` ở cuối nếu không viết thẻ đóng tương ứng.

### 2.3. Phần tử gốc

Một tài liệu XML well-formed có đúng một phần tử gốc (document element). Với build file Ant, phần tử gốc thông thường là `<project>`:

```xml
<project name="sample" default="build">
    <target name="build">
        <echo message="Build started"/>
    </target>
</project>
```

Các target phải nằm trong project. Không đặt hai phần tử `<project>` ngang hàng trong cùng một build file, và không đặt `<target>` ở ngoài phần tử gốc.

Tệp có thể có khai báo XML ở đầu và chú thích ở ngoài phần tử gốc, nhưng toàn bộ nội dung tài liệu vẫn chỉ có một document element.

## 3. Thuộc tính XML

Thuộc tính (attribute) bổ sung thông tin cho phần tử. Thuộc tính được viết bên trong thẻ mở, theo dạng `tên="giá trị"` hoặc `tên='giá trị'`.

Ví dụ:

```xml
<project name="sample" default="build" basedir=".">
    <target name="build">
        <echo message="Build started"/>
    </target>
</project>
```

Trong phần tử `<project>`, `name`, `default` và `basedir` là tên thuộc tính; `sample`, `build` và `.` là các giá trị tương ứng. Trong `<echo>`, `message` là thuộc tính chứa thông báo cần in.

### 3.1. Cách viết thuộc tính

Mỗi thuộc tính phải có tên và giá trị đặt trong dấu nháy đơn hoặc nháy kép. Hai cách viết sau đều hợp lệ:

```xml
<target name="compile">
    <echo message="Compile started"/>
</target>
```

```xml
<target name='compile'>
    <echo message='Compile started'/>
</target>
```

Không được bỏ dấu nháy quanh giá trị. Không khai báo lặp cùng một tên thuộc tính trên một phần tử, ví dụ `name="one" name="two"`, vì đó là XML không hợp lệ.

Tên thuộc tính phân biệt chữ hoa và chữ thường. Với Ant, giá trị thuộc tính còn phải đúng kiểu và đúng ý nghĩa mà phần tử yêu cầu. Ví dụ, `default` của `<project>` là tên target, còn `message` của `<echo>` là nội dung thông báo.

### 3.2. Thuộc tính khác với phần tử con

Thuộc tính mô tả một giá trị trực tiếp của phần tử. Phần tử con biểu diễn một cấu trúc riêng, có thể chứa thuộc tính hoặc phần tử con khác.

Ví dụ:

```xml
<target name="build" depends="prepare">
    <echo message="Building application"/>
</target>
```

Ở đây `name` và `depends` là thuộc tính của `<target>`. `<echo>` là phần tử con, đại diện cho một task được thực thi trong target.

Không thể tùy ý đổi một thuộc tính thành phần tử con hoặc ngược lại. Cách biểu diễn nào được chấp nhận phụ thuộc vào định nghĩa của phần tử Ant đang sử dụng.

### 3.3. Giá trị thuộc tính và ký tự đặc biệt

XML dùng một số ký tự làm dấu cú pháp. Khi cần đưa chúng vào giá trị thuộc tính hoặc nội dung văn bản, phải dùng entity reference phù hợp.

| Ký tự cần biểu diễn | Cách viết XML | Ý nghĩa |
|---|---|---|
| `&` | `&amp;` | Dấu và |
| `<` | `&lt;` | Dấu nhỏ hơn |
| `>` | `&gt;` | Dấu lớn hơn; có thể viết trực tiếp trong phần lớn ngữ cảnh XML, nhưng entity giúp biểu diễn rõ ràng |
| `"` | `&quot;` | Dấu nháy kép khi giá trị thuộc tính dùng nháy kép |
| `'` | `&apos;` | Dấu nháy đơn khi giá trị thuộc tính dùng nháy đơn |

Ví dụ, nếu muốn in biểu thức `a < b` bằng task `<echo>`, có thể viết:

```xml
<echo message="Điều kiện a &lt; b đang được kiểm tra"/>
```

Nếu giá trị chứa dấu `&`, hãy viết `&amp;`:

```xml
<echo message="Research &amp; Development"/>
```

Không viết trực tiếp `message="Research & Development"`, vì dấu `&` mở đầu một entity reference trong XML. Parser có thể báo lỗi nếu phần tiếp theo không tạo thành entity hợp lệ.

Khi cần chứa dấu nháy trùng với dấu bao quanh thuộc tính, hãy dùng entity tương ứng hoặc đổi loại dấu nháy bao quanh. Ví dụ:

```xml
<echo message="The word &quot;build&quot; is used here"/>
```

## 4. Nội dung lồng và quan hệ cha-con

Nội dung lồng (nested content) là nội dung nằm bên trong một phần tử. Nội dung đó có thể là văn bản, phần tử con hoặc sự kết hợp của chúng theo quy tắc XML và quy tắc của Ant.

Trong build file, các phần tử thường tạo thành một cây cấu trúc:

```xml
<project name="sample" default="build">
    <target name="build">
        <echo message="Building"/>
    </target>
</project>
```

Có thể đọc quan hệ cha-con như sau:

```text
project
└── target
    └── echo
```

`project` là cha của `target`; `target` là cha của `echo`. Phần tử `echo` đồng thời là con của `target` và là hậu duệ của `project`. Cấu trúc lồng thể hiện ngữ cảnh mà mỗi phần tử thuộc về.

### 4.1. Thứ tự lồng phải đúng

Các phần tử phải được đóng theo thứ tự ngược lại với thứ tự mở. Ví dụ sau hợp lệ:

```xml
<project name="sample" default="build">
    <target name="build">
        <echo message="Building"/>
    </target>
</project>
```

Ví dụ sau không hợp lệ vì đóng `project` trước khi đóng `target`:

```xml
<project name="sample" default="build">
    <target name="build">
        <echo message="Building"/>
</project>
    </target>
```

XML không cho phép các phần tử chồng lấn. Mỗi phần tử con phải được đóng hoàn toàn trước khi phần tử cha được đóng.

### 4.2. Phần tử lồng trong task Ant

Ant hỗ trợ một số task nhận cấu hình lồng để mô tả dữ liệu phức tạp hơn. Ví dụ, task `<copy>` có thể nhận một `<fileset>` để chỉ định tập tin cần sao chép:

```xml
<target name="copy-resources">
    <copy todir="build/resources">
        <fileset dir="src">
            <include name="**/*.properties"/>
            <exclude name="**/secret.properties"/>
        </fileset>
    </copy>
</target>
```

Trong cấu trúc này:

- `<copy>` là task thực hiện thao tác sao chép; `todir` là thuộc tính chỉ định thư mục đích.
- `<fileset>` là cấu hình lồng mô tả tập tin nguồn; `dir` chỉ định thư mục gốc để tìm tập tin.
- `<include>` chọn các đường dẫn phù hợp với mẫu `**/*.properties`.
- `<exclude>` loại bỏ các đường dẫn phù hợp với mẫu `**/secret.properties` khỏi tập được chọn.

Ant xử lý cấu trúc lồng theo hợp đồng của task và datatype tương ứng. Không phải task nào cũng chấp nhận `<fileset>`, `<include>` hoặc một phần tử bất kỳ. Nếu lồng sai phần tử, Ant có thể báo lỗi rằng phần tử lồng không được hỗ trợ.

Một ví dụ khác là cấu hình classpath cho task `<javac>`:

```xml
<target name="compile">
    <mkdir dir="build/classes"/>
    <javac srcdir="src" destdir="build/classes">
        <classpath>
            <pathelement location="lib/example.jar"/>
        </classpath>
    </javac>
</target>
```

Ở đây `<classpath>` lồng trong `<javac>` mô tả classpath dùng khi biên dịch; `<pathelement>` cung cấp một vị trí thư viện. Các phần tử lồng này có ý nghĩa vì task `javac` hỗ trợ cấu trúc classpath.

### 4.3. Nội dung văn bản bên trong phần tử

XML cũng cho phép nội dung văn bản giữa thẻ mở và thẻ đóng:

```xml
<description>
    Build file dùng để biên dịch và đóng gói ứng dụng.
</description>
```

Trong Ant, phần tử `<description>` ở cấp project có thể mô tả mục đích của build file. Một số task cũng cho phép nội dung văn bản trực tiếp hoặc phần tử con. Hãy kiểm tra tài liệu của task để biết nội dung nào được chấp nhận.

Không nên giả định rằng mọi khoảng trắng hoặc văn bản nằm giữa hai thẻ đều bị bỏ qua. Với các phần tử có xử lý nội dung văn bản, khoảng trắng và xuống dòng có thể là dữ liệu. Hãy giữ định dạng nhất quán và chỉ đặt nội dung ở vị trí mà phần tử hỗ trợ.

## 5. Chú thích XML

Chú thích (comment) dùng để giải thích cấu hình cho người đọc. XML parser bỏ qua nội dung chú thích khi xây dựng cấu trúc tài liệu, vì vậy Ant không thực thi nội dung được viết trong comment.

Cú pháp:

```xml
<!-- Đây là chú thích XML -->
```

Ví dụ trong build file:

```xml
<project name="sample" default="build">

    <!-- Target mặc định để chạy quy trình build -->
    <target name="build">
        <!-- In thông báo để xác nhận target đã được gọi -->
        <echo message="Building project"/>
    </target>

</project>
```

Chú thích có thể đặt giữa các phần tử ở những vị trí XML cho phép, chẳng hạn trước project, giữa các target hoặc giữa các task trong một target. Dùng comment để ghi rõ lý do của cấu hình, yêu cầu đặc biệt hoặc cách dùng một nhóm target.

### 5.1. Quy tắc viết comment

Một comment bắt đầu bằng `<!--` và kết thúc bằng `-->`. Nội dung comment không được chứa chuỗi `--` liên tiếp. Vì vậy, ví dụ sau không hợp lệ:

```xml
<!-- Không dùng dấu gạch nối kép -- trong comment -->
```

Comment XML không được lồng comment khác bên trong. Nếu cần tạm thời vô hiệu hóa một đoạn cấu hình, hãy kiểm tra ranh giới comment để tránh tạo chuỗi mở/đóng không hợp lệ.

Không đặt comment bên trong dấu nháy của một thuộc tính với ý định chú thích một phần giá trị. Ví dụ sau không hợp lệ vì comment không thể xuất hiện bên trong giá trị thuộc tính:

```xml
<target name="build <!-- main target -->">
</target>
```

Hãy đặt comment bên ngoài thẻ:

```xml
<!-- Target chính của build -->
<target name="build">
    <echo message="Building"/>
</target>
```

### 5.2. Comment không phải task

Nội dung trong comment không được Ant thực thi. Ví dụ:

```xml
<target name="build">
    <!-- <echo message="This line is not executed"/> -->
    <echo message="This line is executed"/>
</target>
```

Khi chạy target `build`, chỉ task `<echo>` nằm ngoài comment được thực thi. Comment không thay thế cơ chế điều kiện, thuộc tính hoặc target phụ thuộc của Ant; nó chỉ ghi chú hoặc tạm ẩn văn bản XML.

Không nên dùng comment để duy trì lâu dài những đoạn cấu hình cũ không còn cần thiết. Nếu một cấu hình không còn được sử dụng, hãy xử lý nó theo quy trình quản lý build file của dự án để người đọc không nhầm lẫn giữa cấu hình hiện hành và ví dụ đã bỏ.

## 6. Khai báo XML và định dạng tài liệu

Ở đầu build file có thể đặt khai báo XML:

```xml
<?xml version="1.0" encoding="UTF-8"?>
```

`version` chỉ định phiên bản XML; `encoding` cho biết cách mã hóa ký tự của tệp. Nếu khai báo UTF-8, hãy lưu file thật sự bằng UTF-8 để các ký tự tiếng Việt được đọc chính xác.

Khai báo XML, nếu có, phải xuất hiện ở đầu tài liệu, trước phần tử gốc và trước comment hoặc nội dung khác. Không chèn dòng trống hay comment lên trước khai báo XML.

XML không yêu cầu thụt lề theo một số lượng dấu cách cố định. Thụt lề không làm thay đổi quan hệ cha-con, nhưng giúp người đọc nhận biết cấu trúc lồng. Nên chọn một kiểu thụt lề nhất quán, thường là bốn dấu cách hoặc hai dấu cách, và dùng thống nhất trong toàn bộ build file.

Ví dụ định dạng dễ đọc:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="sample" default="build" basedir=".">
    <description>
        Build ứng dụng mẫu.
    </description>

    <target name="prepare">
        <mkdir dir="build"/>
    </target>

    <target name="build" depends="prepare">
        <echo message="Build directory is ready"/>
    </target>
</project>
```

Khoảng trắng giữa các phần tử giúp phân tách các nhóm cấu hình. Không chèn khoảng trắng tùy tiện vào giá trị thuộc tính nếu khoảng trắng đó có thể làm thay đổi đường dẫn, tên hoặc dữ liệu mà task nhận.

## 7. Kết hợp thuộc tính Ant và cú pháp XML

Trong build file, Ant thường dùng biểu thức thuộc tính như `${build.dir}`. Đây là cú pháp thay thế thuộc tính của Ant được đặt bên trong giá trị XML:

```xml
<project name="sample" default="build" basedir=".">
    <property name="build.dir" value="build"/>

    <target name="prepare">
        <mkdir dir="${build.dir}"/>
    </target>
</project>
```

XML parser trước tiên đọc giá trị thuộc tính `dir` là chuỗi `${build.dir}`. Trong quá trình xử lý build, Ant thay thế biểu thức bằng giá trị thuộc tính đã khai báo, ở đây là `build`.

Khi viết build file, cần phân biệt hai cơ chế:

- XML xử lý cấu trúc thẻ, dấu nháy, entity reference và comment.
- Ant xử lý các quy ước riêng của build như `${property}`, target, task và dependency.

Một chuỗi có thể hợp lệ với Ant nhưng vẫn phải tuân thủ cú pháp XML trước khi Ant có thể đọc nó. Ví dụ, nếu giá trị Ant cần có dấu `&` theo nghĩa ký tự thông thường, vẫn phải escape thành `&amp;` trong XML.

## 8. Lỗi XML thường gặp trong build file

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `The element type ... must be terminated` hoặc lỗi thẻ chưa đóng | Thiếu thẻ đóng hoặc viết sai tên thẻ đóng | Đối chiếu từng cặp thẻ mở/đóng và kiểm tra phần tử lồng sâu nhất trước |
| `The markup in the document following the root element must be well-formed` | Có nội dung hoặc phần tử gốc thứ hai sau khi project đã đóng | Bảo đảm build file chỉ có một phần tử gốc `<project>`; di chuyển nội dung thừa vào trong project hoặc xóa nó |
| `Attribute ... was already specified` | Một phần tử khai báo trùng tên thuộc tính | Xóa thuộc tính trùng và giữ một giá trị duy nhất |
| `The value of attribute ... must not contain the '<' character` | Có dấu `<` trực tiếp trong giá trị thuộc tính | Thay bằng `&lt;` hoặc biểu diễn nội dung theo cấu trúc phù hợp |
| Lỗi entity reference hoặc `The entity name must immediately follow the '&'` | Dùng dấu `&` trực tiếp hoặc viết entity sai | Dùng `&amp;`, `&lt;`, `&gt;`, `&quot;` hoặc `&apos;` phù hợp |
| `Content is not allowed in prolog` | Có ký tự hoặc nội dung không hợp lệ trước phần tử gốc, thường do khai báo XML đặt sai vị trí hoặc mã hóa không khớp | Kiểm tra byte đầu tệp, khai báo XML và encoding thực tế |
| Ant báo nested element không được hỗ trợ | Phần tử con không thuộc cấu trúc mà task cha chấp nhận | Đọc tài liệu task và đặt đúng nested element vào đúng task |
| Ant báo không tìm thấy task hoặc target | Tên phần tử không phải task được Ant nhận diện, hoặc tên target được gọi chưa khai báo | Kiểm tra tên phần tử, tên target và taskdef nếu đang dùng custom task |

Khi gặp lỗi, hãy đọc vị trí dòng và cột mà XML parser hoặc Ant báo. Lỗi được phát hiện tại một dòng đôi khi bắt nguồn từ thẻ mở hoặc dấu nháy bị thiếu ở dòng trước đó. Kiểm tra từ vị trí lỗi ngược lên phần tử cha gần nhất thường giúp tìm nguyên nhân nhanh hơn.

## 9. Ví dụ tổng hợp

Ví dụ sau kết hợp phần tử gốc, thuộc tính, nội dung lồng, task, comment và entity reference trong một build file:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="xml-structure-demo" default="build" basedir=".">

    <!-- Thư mục chứa đầu ra của build -->
    <property name="build.dir" value="build"/>

    <description>
        Ví dụ minh họa cấu trúc XML trong Apache Ant.
    </description>

    <!-- Chuẩn bị thư mục đầu ra -->
    <target name="prepare">
        <mkdir dir="${build.dir}"/>
    </target>

    <!-- Target mặc định phụ thuộc vào prepare -->
    <target name="build" depends="prepare">
        <echo message="Output directory: ${build.dir}"/>
        <echo message="Research &amp; Development"/>
        <copy todir="${build.dir}/resources">
            <fileset dir="src">
                <include name="**/*.properties"/>
            </fileset>
        </copy>
    </target>

</project>
```

Trong ví dụ này, `<project>` là phần tử gốc và có ba thuộc tính. `<property>` và `<description>` là các phần tử nằm trực tiếp trong project. Hai phần tử `<target>` định nghĩa hai nhóm công việc. Target `build` có thuộc tính `depends="prepare"`, vì vậy Ant thực hiện `prepare` trước khi thực hiện task của `build`.

Bên trong `build`, hai task `<echo>` sử dụng thuộc tính để truyền thông báo. Task `<copy>` có nội dung lồng `<fileset>`, và fileset có phần tử con `<include>`. Comment giải thích vai trò của từng nhóm nhưng không được thực thi. Dấu `&` trong thông báo được viết thành `&amp;` để tài liệu XML hợp lệ.

Chạy lệnh sau từ thư mục chứa file:

```bash
ant
```

Ant chọn target mặc định `build`, thực hiện dependency `prepare`, sau đó chạy các task trong `build`. Để ví dụ sao chép tài nguyên thành công, thư mục `src` cần tồn tại và có thể chứa các tệp `.properties`; nếu chưa có tài nguyên phù hợp, phần task copy có thể không tạo ra tệp nào nhưng cấu trúc build file vẫn minh họa cách lồng XML.

## 10. Nguyên tắc đọc và viết XML trong Ant

- Bắt đầu từ phần tử gốc `<project>`, sau đó lần theo các phần tử con để hiểu cấu trúc build.
- Đọc thuộc tính trên từng phần tử để biết tên, đường dẫn, target mặc định, dependency hoặc tham số task.
- Phân biệt thuộc tính với phần tử con; phần tử con thường biểu diễn một cấu trúc dữ liệu hoặc cấu hình lồng riêng.
- Đóng các phần tử theo đúng thứ tự ngược với thứ tự mở và dùng nhất quán chữ hoa/chữ thường.
- Escape ký tự đặc biệt như `&` và `<` khi chúng xuất hiện trong nội dung hoặc giá trị thuộc tính.
- Dùng comment để giải thích mục đích cấu hình, không dùng comment như một task hoặc một cơ chế điều khiển build.
- Chỉ lồng các phần tử mà task Ant tương ứng hỗ trợ.
- Giữ encoding của tệp nhất quán với khai báo XML, đặc biệt khi build file có nội dung tiếng Việt.

Khi nắm được phần tử, thuộc tính, nội dung lồng và comment, bạn có thể đọc cấu trúc `build.xml` từ ngoài vào trong, hiểu được mỗi cấu hình thuộc về phần nào và tránh phần lớn lỗi cú pháp XML cơ bản trong quá trình xây dựng Ant build file.
