# Ánh xạ thuộc tính XML qua setter và chuyển đổi kiểu

Khi viết một custom task cho Apache Ant, người dùng cấu hình task trong `build.xml` bằng các thuộc tính XML. Ví dụ:

```xml
<report source="data/input.csv"
        output="build/report.txt"
        verbose="true"
        maxrows="250"/>
```

Các giá trị trong XML được Ant chuyển vào đối tượng Java của task. Cơ chế này dựa trên introspection: Ant tìm phương thức setter tương ứng với tên thuộc tính, chuyển giá trị từ chuỗi XML sang kiểu tham số mà setter yêu cầu, rồi gọi phương thức đó. Vì vậy, tên và kiểu của setter là một phần của giao diện cấu hình mà custom task cung cấp cho người viết build file.

## 1. Ánh xạ tên thuộc tính XML sang setter

Với mỗi thuộc tính XML mà task hỗ trợ, lớp Java cần có một phương thức `public void` nhận đúng một tham số. Tên phương thức bắt đầu bằng `set`, tiếp theo là tên thuộc tính với chữ cái đầu viết hoa. Ví dụ, thuộc tính XML `file` được ánh xạ tới `setFile`:

```java
package com.example.ant;

import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Task;

public class ReportTask extends Task {
    private String file;

    public void setFile(String file) {
        this.file = file;
    }

    @Override
    public void execute() throws BuildException {
        log("Reading " + file);
    }
}
```

Khi Ant đọc:

```xml
<report file="data/input.csv"/>
```

nó tìm setter `setFile(...)` trên lớp `ReportTask` và truyền giá trị `data/input.csv` vào phương thức đó. Trong build file, tên attribute là `file`; trong Java, tên setter là `setFile`. Ant không yêu cầu tạo getter tương ứng để nhận giá trị cấu hình.

Quy ước thường dùng là viết attribute XML bằng chữ thường và dùng setter có chữ cái đầu của tên attribute viết hoa, chẳng hạn `output` → `setOutput`, `verbose` → `setVerbose`, `maxrows` → `setMaxrows`. Ant không quá nhạy với cách viết hoa các chữ sau ký tự đầu trong tên setter, nhưng dùng một quy ước nhất quán giúp code dễ đọc.

Setter phải có dạng `public void setX(T value)`. Phương thức trả về giá trị, setter không `public`, hoặc setter nhận nhiều tham số không đáp ứng quy ước introspection thông thường của Ant.

## 2. Ant xử lý giá trị thuộc tính khi nào?

Các task trong build file được phân tích thành cấu trúc nội bộ khi Ant đọc project. Khi target thực thi, Ant tạo đối tượng task, gọi `init()`, cấu hình thuộc tính qua các setter tương ứng rồi mới gọi `execute()`.

Luồng đơn giản có thể hình dung như sau:

```text
XML trong build.xml
        |
        v
Ant nhận diện tên task và thuộc tính
        |
        v
Tạo đối tượng custom task khi target chạy
        |
        v
Mở rộng property trong giá trị XML
        |
        v
Tìm setter tương ứng và chuyển đổi kiểu
        |
        v
Gọi setX(value)
        |
        v
Gọi execute()
```

Ant luôn mở rộng property trước khi truyền giá trị attribute cho setter. Ví dụ:

```xml
<property name="report.file" location="data/input.csv"/>

<target name="report">
    <report file="${report.file}"/>
</target>
```

Setter `setFile` nhận giá trị sau khi `${report.file}` được thay thế. Nếu property không tồn tại, biểu thức chưa được giải quyết có thể vẫn xuất hiện trong chuỗi nhận được; task nên kiểm tra các đầu vào cần thiết và báo lỗi có ngữ cảnh bằng `BuildException`.

Lưu ý rằng property expansion trên attribute không đồng nghĩa mọi nội dung XML đều được mở rộng. Với text nằm trực tiếp giữa thẻ mở và thẻ đóng, Ant chuyển nội dung đó qua `addText(String)` nếu task có phương thức này; Ant không tự mở rộng property trong nested text. Nếu cần, task phải chủ động gọi `getProject().replaceProperties(text)`.

## 3. Chuyển đổi kiểu tự động

Nếu setter nhận `String`, Ant truyền chuỗi sau khi mở rộng property. Nếu setter nhận kiểu khác, Ant có thể chuyển giá trị XML sang kiểu Java tương ứng. Những kiểu thường gặp được mô tả dưới đây.

| Kiểu tham số setter | Cách Ant chuyển đổi |
|---|---|
| `String` | Truyền chuỗi sau property expansion |
| `boolean` | `true`, `yes`, `on` được hiểu là `true`; các giá trị khác được chuyển thành `false` |
| `char` / `Character` | Lấy ký tự đầu tiên của giá trị |
| Kiểu primitive số như `int`, `long`, `short`, `double` | Phân tích chuỗi thành kiểu số tương ứng; giá trị không hợp lệ gây lỗi cấu hình |
| `File` | Chuyển thành đường dẫn; đường dẫn tương đối được tính từ `basedir` của Ant project |
| `Resource` | Được xử lý như `File`, rồi tạo `FileResource` (từ Ant 1.8) |
| `Path` | Tách danh sách đường dẫn bằng `:` hoặc `;`; phần tử tương đối được tính từ `basedir` |
| `Class` | Tải lớp có tên được chỉ định bằng system class loader |
| Kiểu khác có constructor nhận một `String` | Ant gọi constructor đó với giá trị XML |
| `EnumeratedAttribute` | Ant tạo đối tượng và gọi `setValue()`; giá trị phải thuộc tập cho phép |
| Java `enum` | Ant tìm enum constant khớp với tên được truyền (hỗ trợ từ Ant 1.7.0) |

### Chuỗi (`String`)

Đây là kiểu đơn giản nhất và phù hợp với tên, mô tả hoặc giá trị mà task cần tự phân tích:

```java
private String format;

public void setFormat(String format) {
    this.format = format;
}
```

```xml
<report format="html"/>
```

Ant không tự giới hạn tập giá trị của chuỗi. Nếu task chỉ chấp nhận `html`, `xml` hoặc `text`, code task phải kiểm tra giá trị và báo lỗi khi nhận giá trị không hợp lệ, hoặc dùng kiểu enum/`EnumeratedAttribute` để khai báo tập giá trị ngay ở lớp cấu hình.

### Boolean

Với setter nhận `boolean`, Ant xem `true`, `yes` và `on` là đúng; các giá trị khác được chuyển thành `false`:

```java
private boolean verbose;

public void setVerbose(boolean verbose) {
    this.verbose = verbose;
}
```

```xml
<report verbose="yes"/>
```

Trong ví dụ, `verbose` nhận giá trị `true`. Nên dùng `true` hoặc `false` trong build file để thể hiện ý định rõ ràng. Vì các chuỗi khác `true`, `yes`, `on` đều thành `false`, một lỗi đánh máy như `verbsoe="true"` thường không tương đương với việc đặt `verbose="false"`: trường hợp đầu tiên còn là attribute không được task hỗ trợ và Ant sẽ báo lỗi.

### Kiểu số và ký tự

Các kiểu primitive số như `int`, `long`, `float`, `double`, `short` và `byte` được phân tích từ chuỗi:

```java
private int maxrows;

public void setMaxrows(int maxrows) {
    this.maxrows = maxrows;
}
```

```xml
<report maxrows="250"/>
```

Nếu giá trị là `many`, Ant không thể chuyển thành `int` và quá trình cấu hình task thất bại trước khi `execute()` chạy. Với `char` hoặc `Character`, Ant lấy ký tự đầu tiên, ví dụ `separator=","` tạo ký tự dấu phẩy. Nếu task yêu cầu đúng một ký tự, nên tự kiểm tra chuỗi đầu vào trước khi chuyển đổi hoặc dùng setter `String` để kiểm tra độ dài rõ ràng.

## 4. Chuyển đổi đường dẫn với `File` và `Path`

`File` và `Path` rất hữu ích trong custom task vì Ant hiểu ngữ cảnh project và `basedir` khi chuyển đổi.

### `File`

Setter nhận `java.io.File`:

```java
private File source;

public void setSource(File source) {
    this.source = source;
}
```

Build file:

```xml
<report source="data/input.csv"/>
```

Nếu giá trị là đường dẫn tương đối, Ant diễn giải nó tương đối với `basedir` của project. Nếu giá trị là đường dẫn tuyệt đối, Ant giữ ý nghĩa đường dẫn tuyệt đối đó. Điều này giúp task không phải tự nối `basedir` vào mọi đường dẫn tương đối.

Trong `execute()`, task vẫn nên kiểm tra file có tồn tại và có thể đọc hay không:

```java
if (source == null || !source.isFile()) {
    throw new BuildException("Source file does not exist: " + source);
}
```

Chuyển đổi thành `File` chỉ tạo đối tượng đường dẫn; nó không đảm bảo file thực sự tồn tại.

### `Path`

`org.apache.tools.ant.types.Path` biểu diễn danh sách đường dẫn, thường dùng cho classpath hoặc danh sách thư mục đầu vào:

```java
import org.apache.tools.ant.types.Path;

private Path classpath;

public void setClasspath(Path classpath) {
    this.classpath = classpath;
}
```

Build file có thể truyền chuỗi path:

```xml
<report classpath="lib/parser.jar;lib/formatter.jar"/>
```

Ant tách các phần tử path bằng dấu `:` hoặc `;` và phân giải phần tử tương đối từ `basedir`. Với classpath phức tạp, nested `<classpath>` thường dễ đọc hơn chuỗi attribute:

```xml
<report>
    <classpath>
        <pathelement location="lib/parser.jar"/>
        <pathelement location="lib/formatter.jar"/>
    </classpath>
</report>
```

Để nhận nested `<classpath>` theo cách này, custom task cần thêm phương thức tạo hoặc nhận nested element, ví dụ `createClasspath()` trả về một `Path`, hoặc `addClasspath(Path path)`. Chuyển đổi attribute `classpath="..."` và hỗ trợ nested element là hai cơ chế cấu hình khác nhau.

## 5. Dùng constructor nhận `String`

Ant có thể tạo một đối tượng từ giá trị XML nếu kiểu tham số setter có constructor nhận một `String`. Điều này hữu ích với các lớp giá trị tự định nghĩa hoặc các kiểu thư viện đã có constructor phù hợp.

Ví dụ một kiểu `Endpoint`:

```java
public class Endpoint {
    private final String value;

    public Endpoint(String value) {
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException("Endpoint must not be empty");
        }
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
```

Task có thể nhận trực tiếp kiểu đó:

```java
private Endpoint endpoint;

public void setEndpoint(Endpoint endpoint) {
    this.endpoint = endpoint;
}
```

```xml
<report endpoint="https://reports.example.test/api"/>
```

Ant gọi constructor `Endpoint(String)` để tạo đối tượng trước khi gọi `setEndpoint`. Nếu constructor từ chối giá trị, lỗi xảy ra trong giai đoạn cấu hình task. Vì constructor được gọi từ dữ liệu build file, nên thông báo lỗi nên nêu rõ giá trị không hợp lệ và cách sửa.

## 6. Giới hạn giá trị bằng `EnumeratedAttribute`

Khi attribute chỉ nhận một tập giá trị cố định, có thể tạo kiểu con của `org.apache.tools.ant.types.EnumeratedAttribute`. Kiểu này khai báo danh sách giá trị hợp lệ trong `getValues()`:

```java
import org.apache.tools.ant.types.EnumeratedAttribute;

public static class ReportFormat extends EnumeratedAttribute {
    @Override
    public String[] getValues() {
        return new String[] { "html", "xml", "text" };
    }
}
```

Task dùng kiểu đó trong setter:

```java
private ReportFormat format;

public void setFormat(ReportFormat format) {
    this.format = format;
}
```

Build file:

```xml
<report format="html"/>
```

Nếu người dùng viết `format="pdf"`, Ant báo lỗi vì `pdf` không thuộc tập giá trị mà `ReportFormat` cho phép. Cách này giúp mô tả hợp đồng XML ngay tại kiểu Java, thay vì để task nhận chuỗi bất kỳ rồi tự kiểm tra ở nhiều nơi.

## 7. Dùng Java `enum` làm kiểu attribute

Từ Ant 1.7.0, setter có thể nhận Java enum. Ant tìm enum constant khớp với giá trị được khai báo trong XML:

```java
public enum ReportMode {
    compact,
    detailed
}

private ReportMode mode;

public void setMode(ReportMode mode) {
    this.mode = mode;
}
```

```xml
<report mode="detailed"/>
```

Giá trị trong build file phải khớp tên enum constant được khai báo. Ant dùng tên constant, không dùng kết quả `toString()` đã override. Vì vậy, nếu enum dùng quy ước Java thông thường như `DETAILED`, build file phải dùng đúng `mode="DETAILED"`. Có thể đặt tên constant chữ thường nếu muốn XML dễ đọc hơn, như ví dụ `compact` và `detailed`.

`enum` phù hợp khi code task có thể dùng kiểu enum trực tiếp trong logic Java. `EnumeratedAttribute` hữu ích khi muốn theo mô hình attribute truyền thống của Ant hoặc cần kiểm soát tập giá trị bằng lớp riêng. Cả hai đều giúp từ chối giá trị ngoài danh sách.

## 8. Tránh overload setter cho cùng một attribute

Không nên khai báo nhiều setter cùng tên logic nhưng nhận các kiểu khác nhau:

```java
public void setCount(String count) { ... }
public void setCount(int count) { ... }
```

Ant luôn ưu tiên setter nhận `String` thấp hơn setter có kiểu cụ thể hơn. Nếu vẫn còn nhiều setter cụ thể có thể được chọn, chỉ một phương thức được gọi và lựa chọn có thể phụ thuộc cách JVM triển khai reflection; không nên dựa vào thứ tự đó.

Thiết kế rõ ràng hơn là chọn một kiểu duy nhất cho mỗi attribute:

```java
public void setCount(int count) {
    if (count < 0) {
        throw new BuildException("count must be zero or greater");
    }
    this.count = count;
}
```

Nếu cần chấp nhận nhiều dạng đầu vào, hãy nhận `String` duy nhất rồi tự phân tích theo quy tắc được tài liệu hóa, hoặc tạo các attribute khác tên với ý nghĩa khác nhau. Không để Ant phải lựa chọn giữa nhiều setter tương ứng cùng một attribute.

## 9. Ví dụ hoàn chỉnh về custom task

Ví dụ sau kết hợp nhiều kiểu setter trong cùng task. Nó minh họa ánh xạ attribute XML và nơi kiểm tra dữ liệu trước khi xử lý thật:

```java
package com.example.ant;

import java.io.File;
import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Task;
import org.apache.tools.ant.types.EnumeratedAttribute;
import org.apache.tools.ant.types.Path;

public class ReportTask extends Task {
    private File source;
    private File output;
    private boolean verbose;
    private int maxrows = 100;
    private Path classpath;
    private Format format;

    public void setSource(File source) {
        this.source = source;
    }

    public void setOutput(File output) {
        this.output = output;
    }

    public void setVerbose(boolean verbose) {
        this.verbose = verbose;
    }

    public void setMaxrows(int maxrows) {
        this.maxrows = maxrows;
    }

    public void setClasspath(Path classpath) {
        this.classpath = classpath;
    }

    public void setFormat(Format format) {
        this.format = format;
    }

    @Override
    public void execute() throws BuildException {
        if (source == null || !source.isFile()) {
            throw new BuildException("source must point to an existing file");
        }
        if (output == null) {
            throw new BuildException("The output attribute is required");
        }
        if (maxrows <= 0) {
            throw new BuildException("maxrows must be greater than zero");
        }

        if (verbose) {
            log("Source: " + source);
            log("Output: " + output);
            log("Format: " + (format == null ? "html" : format.getValue()));
            log("Classpath: " + classpath);
        }

        // Thực hiện xử lý báo cáo tại đây.
    }

    public static class Format extends EnumeratedAttribute {
        @Override
        public String[] getValues() {
            return new String[] { "html", "xml", "text" };
        }
    }
}
```

Đăng ký task sau khi lớp Java đã được biên dịch và có mặt trong classpath của Ant:

```xml
<taskdef name="report"
         classname="com.example.ant.ReportTask"
         classpath="build/ant-tasks"/>

<property name="report.source" location="data/input.csv"/>
<property name="report.output" location="build/report.html"/>

<target name="create-report">
    <report source="${report.source}"
            output="${report.output}"
            verbose="yes"
            maxrows="250"
            format="html"
            classpath="lib/parser.jar;lib/formatter.jar"/>
</target>
```

Trong lần gọi này:

- `source` và `output` được chuyển thành `File`, với đường dẫn tương đối được giải quyết theo `basedir`.
- `verbose="yes"` được chuyển thành boolean `true`.
- `maxrows="250"` được chuyển thành `int`.
- `format="html"` tạo một đối tượng `Format` có giá trị hợp lệ.
- `classpath` được chuyển thành Ant `Path`.

Task vẫn phải tự kiểm tra các điều kiện nghiệp vụ như file có tồn tại, output có thể ghi và số dòng có hợp lệ. Việc Ant chuyển đổi kiểu thành công chỉ xác nhận giá trị có thể biểu diễn bằng kiểu Java đó; nó không xác nhận dữ liệu phù hợp với yêu cầu của ứng dụng.

## 10. Attribute động và nested element

Setter thông thường phù hợp khi tập attribute đã biết trước. Nếu custom task cần nhận các attribute không biết tên từ trước, có thể triển khai `org.apache.tools.ant.DynamicAttribute` với phương thức `setDynamicAttribute(String name, String value)`. Cách này thường dùng cho task có một tập tên thuộc tính do người dùng tự định nghĩa. Task phải tự kiểm tra tên, chuyển đổi kiểu và báo lỗi cho attribute không được hỗ trợ.

Khi dữ liệu có cấu trúc XML lồng nhau, không nên nhồi toàn bộ vào một attribute dạng chuỗi. Ant hỗ trợ nested element qua các phương thức `createX()`, `addX(...)` hoặc `addConfiguredX(...)`. Các attribute trên đối tượng nested cũng được xử lý bằng setter theo cùng nguyên tắc introspection.

Ví dụ task nhận nested `<fileset>` thường khai báo một phương thức tạo hoặc thêm `FileSet`, sau đó sử dụng danh sách fileset trong `execute()`. Chọn nested element khi người dùng cần truyền nhiều thuộc tính hoặc nhiều phần tử con có cấu trúc.

## 11. Lỗi thường gặp và cách xử lý

1. **Ant báo task không hỗ trợ attribute.** Kiểm tra tên XML attribute có khớp setter `setX` hay không, setter có `public` và nhận đúng một tham số hay không.
2. **Setter không được gọi.** Kiểm tra task đã được đăng ký bằng `<taskdef>` và class chứa setter có trong classpath của Ant.
3. **Giá trị số gây lỗi cấu hình.** Kiểm tra giá trị XML có thể phân tích thành kiểu số setter yêu cầu hay không. Dùng thông báo lỗi có ngữ cảnh khi task cần giới hạn phạm vi số.
4. **Boolean bất ngờ thành `false`.** Ant chỉ coi `true`, `yes`, `on` là đúng. Dùng các giá trị tường minh và kiểm tra lại tên attribute.
5. **File được tìm ở sai thư mục.** Setter nhận `File` phân giải đường dẫn tương đối theo `basedir` của Ant project. Kiểm tra `basedir` hoặc truyền đường dẫn tuyệt đối bằng property `location`.
6. **Classpath không được tách như mong muốn.** Với setter `Path`, kiểm tra dấu phân tách và các đường dẫn tương đối. Với danh sách phức tạp, dùng nested `<classpath>`.
7. **Enum hoặc `EnumeratedAttribute` từ chối giá trị.** So sánh đúng tên enum constant hoặc giá trị được trả về trong `getValues()`; không dựa vào `toString()` tùy chỉnh của enum.
8. **Overloaded setter được chọn không ổn định.** Chỉ khai báo một setter cho mỗi attribute XML. Ant không đảm bảo lựa chọn giữa nhiều setter cụ thể còn lại.
9. **Task nhận `null` hoặc giá trị chưa hợp lệ.** Ant có thể chuyển kiểu nhưng không kiểm tra mọi điều kiện nghiệp vụ. Kiểm tra đầu vào trong `execute()` và ném `BuildException` với thông báo rõ ràng.
10. **Property trong nested text không được thay.** Property expansion tự động áp dụng cho attribute. Nếu dùng `addText(String)`, hãy gọi `getProject().replaceProperties(text)` khi cần mở rộng property trong nội dung text.

## 12. Quy trình thiết kế attribute cho custom task

Khi tạo một custom task mới, hãy thực hiện theo trình tự:

1. Liệt kê các attribute XML mà người dùng cần cấu hình và chọn tên ngắn, rõ nghĩa.
2. Tạo một setter `public void setX(T value)` cho mỗi attribute.
3. Chọn kiểu Java phù hợp: `String` cho văn bản tự do, `boolean` cho cờ, primitive số cho số liệu, `File` cho một đường dẫn, `Path` cho danh sách đường dẫn, enum hoặc `EnumeratedAttribute` cho tập giá trị giới hạn.
4. Tránh nhiều setter overload cho cùng một attribute.
5. Để Ant thực hiện chuyển đổi chuẩn; chỉ tự parse khi định dạng đầu vào có quy tắc riêng.
6. Kiểm tra điều kiện nghiệp vụ trong task và báo lỗi bằng `BuildException`.
7. Đăng ký task bằng `<taskdef>` và gọi thử từ build file với property expansion.
8. Ghi tài liệu cho mỗi attribute, kiểu dữ liệu, giá trị hợp lệ và cách phân giải đường dẫn.

## Tài liệu tham khảo

- [Apache Ant Manual — Developing with Ant](https://ant.apache.org/manual/develop.html): quy tắc setter, lifecycle, introspection và các kiểu Ant tự chuyển đổi.
- [Apache Ant Manual — Tutorial: Writing Tasks](https://ant.apache.org/manual/tutorial-writing-tasks.html): ví dụ custom task, setter và cách đăng ký task bằng `taskdef`.
- [Apache Ant API — IntrospectionHelper](https://ant.apache.org/manual/api/org/apache/tools/ant/IntrospectionHelper.html): API ánh xạ thuộc tính XML và nested element sang phương thức Java.
- [Apache Ant API — EnumeratedAttribute](https://ant.apache.org/manual/api/org/apache/tools/ant/types/EnumeratedAttribute.html): kiểu attribute giới hạn theo danh sách giá trị hợp lệ.
