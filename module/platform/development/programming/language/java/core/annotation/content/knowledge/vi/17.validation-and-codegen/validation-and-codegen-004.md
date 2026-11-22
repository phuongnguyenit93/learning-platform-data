# Filer: sinh mã nguồn, class file và tài nguyên bằng Java Annotation Processor

## 1. `Filer` là gì và được dùng ở giai đoạn nào?

Trong Java, **annotation processing** (JSR 269) cho phép một processor đọc mô hình chương trình trong lúc biên dịch, kiểm tra quy tắc hoặc **sinh thêm tệp** từ annotation. API tiêu chuẩn chịu trách nhiệm tạo tệp là `javax.annotation.processing.Filer`, được cấp thông qua `ProcessingEnvironment`:

```java
Filer filer = processingEnv.getFiler();
```

Đây là đoạn mã đặt bên trong một annotation processor, chẳng hạn class kế thừa `AbstractProcessor`. `Filer` không phải đối tượng dùng để ghi tùy ý vào mọi thư mục ổ đĩa: nó là giao diện với **công cụ annotation processing** để tạo những tệp mà compiler/build có thể quản lý.

Ba loại sản phẩm chính:

1. **Java source file** (`.java`): sinh một khai báo kiểu, rồi để compiler tiếp tục biên dịch nguồn mới.
2. **Java class file** (`.class`): ghi trực tiếp bytecode hợp lệ của một kiểu, khi processor thật sự có khả năng tạo bytecode.
3. **Auxiliary resource**: sinh metadata, văn bản cấu hình, danh sách định danh hoặc một tệp phụ không được compiler coi là class/source mới để tự xử lý annotation.

Phân biệt các thao tác: `Filer` **tạo tệp đầu ra**, còn `RoundEnvironment`/`javax.lang.model` giúp **đọc mô hình của mã đầu vào**. `Messager` dùng để báo diagnostic lỗi/cảnh báo. Một processor thực tế thường phối hợp cả ba API.

Ví dụ ứng dụng:

- Từ `@GenerateInfo` trên `Widget`, sinh `WidgetGenerated.java`.
- Từ metadata của các class được chú thích, sinh một tệp danh sách `META-INF/...` trong thư mục class output.
- Từ mô hình một kiểu, sinh `.class` bằng bộ sinh bytecode.
- Gắn `originatingElements` để công cụ build hiểu file đầu ra bắt nguồn từ phần tử nào.

## 2. Bốn phương thức chính và loại đối tượng trả về

| API | Kết quả | Ghi hoặc đọc | Mục đích |
|---|---|---|---|
| `createSourceFile(name, origins...)` | `JavaFileObject` | Ghi | Tạo source `.java` của một kiểu |
| `createClassFile(name, origins...)` | `JavaFileObject` | Ghi | Tạo bytecode `.class` hợp lệ |
| `createResource(location, moduleAndPkg, relativeName, origins...)` | `FileObject` | Ghi | Tạo tài nguyên phụ |
| `getResource(location, moduleAndPkg, relativeName)` | `FileObject` | Đọc | Đọc tài nguyên đã có ở location được hỗ trợ |

Giao diện được khai báo trong module Java `java.compiler` (JDK 17). Các kiểu liên quan:

```java
import javax.annotation.processing.Filer;
import javax.annotation.processing.FilerException;
import javax.annotation.processing.ProcessingEnvironment;
import javax.tools.FileObject;
import javax.tools.JavaFileObject;
import javax.tools.StandardLocation;
```

`JavaFileObject` có thể mở luồng ký tự bằng `openWriter()` hoặc byte bằng `openOutputStream()`. `FileObject` cũng cung cấp các thao tác đọc/ghi phù hợp. Mỗi thao tác được kiểm soát bởi file manager của compiler, không nên tự suy đoán đường dẫn vật lý khi đặt tên.

Một điều rất quan trọng: **`createSourceFile` và `createClassFile` đăng ký nguồn/class mới với công cụ**, giúp chúng được xem xét trong **processing round tiếp theo** sau khi luồng ghi được đóng. **`createResource` không đăng ký tệp như Java source/class để tự được xử lý ở round sau**, ngay cả khi tên tệp trông giống `.java` hay `.class`.

## 3. Cơ chế nhiều vòng biên dịch và thời điểm đóng tệp

Một vòng annotation processing (*processing round*) có tập root elements và những annotation type chưa bị processor khác nhận xử lý. Processor có thể dùng `Filer` sinh nguồn hoặc class mới; các tệp ấy được công cụ đưa vào việc xử lý ở round sau.

```text
Round 1 — javac thấy @GenerateInfo trên Widget
    |
    | Processor đọc TypeElement Widget
    | Filer.createSourceFile("demo.WidgetGenerated", Widget)
    | Writer viết nội dung và close()
    v
Round 2 — compiler xét nguồn WidgetGenerated.java mới
    |
    | Processor có thể được gọi tiếp, kể cả tập annotations rỗng
    v
Round cuối — roundEnv.processingOver() == true
    |
    v
Kết thúc annotation processing, compiler hoàn thiện output
```

**Đóng `Writer`/`OutputStream` là một bước có ý nghĩa**, không chỉ để giải phóng tài nguyên. Theo hợp đồng `Filer`, tệp source/class mới được xem xét cho round sau **sau khi luồng ghi của nó được đóng**. Hãy dùng `try-with-resources` để đóng ngay khi nội dung đã hoàn chỉnh.

```java
JavaFileObject output =
        processingEnv.getFiler().createSourceFile(
                "demo.GeneratedExample", sourceElement);

try (Writer writer = output.openWriter()) {
    writer.write(
        "package demo;\n"
        + "public final class GeneratedExample {}\n");
}
```

Đây là **đoạn minh họa bên trong processor**; `sourceElement` phải là một `Element` hợp lệ, và có import `java.io.Writer`/`javax.tools.JavaFileObject` cùng xử lý `IOException`.

Một tệp Java vừa tạo **không trở thành class runtime chỉ vì gọi `createSourceFile`**. Compiler còn phải biên dịch nội dung, nên nguồn sinh ra phải hợp cú pháp, đúng kiểu, đúng tên và tương thích với source level của lượt biên dịch.

Khi `roundEnv.processingOver()` là `true`, không nên tạo thêm source/class với kỳ vọng sẽ có round xử lý thông thường tiếp theo cho tệp ấy. Công việc tổng kết (diagnostic, báo cáo) cần được thiết kế phù hợp vòng cuối.

## 4. `createSourceFile`: sinh một Java source có tên kiểu chính xác

Chữ ký:

```java
JavaFileObject createSourceFile(
        CharSequence name,
        Element... originatingElements) throws IOException;
```

Tham số `name` là **tên chính tắc đầy đủ của kiểu chính** (*canonical, fully qualified name*) sẽ được khai báo trong nguồn sinh ra; ví dụ `"demo.WidgetGenerated"`, **không** phải đường dẫn `"src/demo/WidgetGenerated.java"`.

```java
JavaFileObject file =
        filer.createSourceFile("demo.WidgetGenerated", widgetElement);
```

Với cấu hình `javac -s build/generated`, công cụ thường đặt file này tại:

```text
build/generated/demo/WidgetGenerated.java
```

Đây là minh họa layout classpath thông dụng; `Filer` dựa vào file manager và cấu hình output thực tế.

Nội dung phải khai báo đúng kiểu:

```java
package demo;

public final class WidgetGenerated {
    private WidgetGenerated() {}

    public static String message() {
        return "generated";
    }
}
```

Nguyên tắc:

- `createSourceFile` nhận **tên kiểu**, không nhận chuỗi đường dẫn filesystem.
- Cặp package + tên kiểu khai báo trong nội dung phải nhất quán với `name`.
- Nếu một compilation unit chứa nhiều kiểu top-level, tên file phải tương ứng với kiểu chính, đặc biệt khi có public top-level class.
- Nội dung được ghi theo `Writer` hoặc `OutputStream`; đóng luồng đầy đủ để compiler tiếp tục xử lý.
- Chỉ tạo kiểu mới, không cố “viết đè” chính class nguồn đang được xử lý bằng một source mới cùng tên.

### `-s` và `-d` có vai trò gì?

Với `javac`, tùy chọn `-s <dir>` chỉ định nơi đặt source **do annotation processor sinh ra**; `-d <dir>` chỉ định output cho các class file đã biên dịch và các tài nguyên class output. Tên file trong `createSourceFile` vẫn là tên kiểu, không thay đổi theo `-s`.

Nếu không chỉ rõ `-s`, công cụ có thể sử dụng vị trí mặc định do cấu hình file manager quyết định. Để kết quả build rõ ràng và tránh trộn source tự viết với source sinh ra, nên cấu hình hai output directories riêng.

## 5. Ví dụ hoàn chỉnh Java 17+: tạo source và resource trong cùng processor

Ví dụ này có thể chạy với **JDK 17+**, không cần Maven, Gradle hay thư viện ngoài. Một annotation `@GenerateInfo` trên class `Widget` sẽ làm processor tạo:

- `demo.WidgetGenerated.java` trong **source output**.
- `demo/Widget.info` trong **class output**.

Chương trình `Main` dùng **class được sinh ra** và đọc **resource được sinh ra** khi chạy.

### Cấu trúc mã nguồn ban đầu

```text
src/
└── demo/
    ├── GenerateInfo.java
    ├── GenerateInfoProcessor.java
    ├── Widget.java
    └── Main.java
```

### File 1 — `src/demo/GenerateInfo.java`

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateInfo {
}
```

`SOURCE` đủ vì processor đọc annotation khi biên dịch mã nguồn. Không cần `RUNTIME` trừ khi còn một consumer dùng reflection sau biên dịch.

### File 2 — `src/demo/GenerateInfoProcessor.java`

```java
package demo;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.FileObject;
import javax.tools.JavaFileObject;
import javax.tools.StandardLocation;

@SupportedAnnotationTypes("demo.GenerateInfo")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class GenerateInfoProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateInfo.class)) {

            if (!(element instanceof TypeElement type)) {
                continue;
            }

            String pkg = processingEnv.getElementUtils()
                    .getPackageOf(type)
                    .getQualifiedName()
                    .toString();
            String name = type.getSimpleName().toString();
            String generatedType = pkg + "." + name + "Generated";

            try {
                JavaFileObject javaFile =
                        processingEnv.getFiler()
                                .createSourceFile(generatedType, type);

                try (Writer writer = javaFile.openWriter()) {
                    writer.write("package " + pkg + ";\n\n"
                            + "public final class " + name
                            + "Generated {\n"
                            + "    private " + name + "Generated() {}\n"
                            + "    public static String message() {\n"
                            + "        return \"generated: " + name
                            + "\";\n"
                            + "    }\n"
                            + "}\n");
                }

                FileObject resource =
                        processingEnv.getFiler().createResource(
                                StandardLocation.CLASS_OUTPUT,
                                pkg,
                                name + ".info",
                                type);

                try (Writer writer = resource.openWriter()) {
                    writer.write(name + "\n");
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate files for " + name
                                + ": " + ex.getMessage(),
                        element);
            }
        }

        return true;
    }
}
```

Đây là **toàn bộ processor**, không phải pseudocode:

- `@SupportedAnnotationTypes("demo.GenerateInfo")` đăng ký annotation type được xử lý.
- `roundEnv.getElementsAnnotatedWith(GenerateInfo.class)` tìm những element gắn annotation trong round.
- `TypeElement` đại diện cho class/interface đang xét; ví dụ này tạo file cho `Widget`.
- `getPackageOf(type)` lấy package để sinh tên `demo.WidgetGenerated` và đặt resource đúng package.
- `createSourceFile(..., type)` và `createResource(..., type)` đều nhận `type` làm **originating element**.
- Hai khối `try-with-resources` đóng Writer trước khi round kết thúc.
- `IOException` được chuyển thành diagnostic `ERROR`, không bị bỏ qua im lặng.
- `return true` tuyên bố processor nhận xử lý annotation types đã được giao; boolean này **không** biểu diễn build thành công hay thất bại.

Để giữ ví dụ nhỏ, processor chỉ có tác dụng với class trong named package và tên class Java hợp lệ; bài này dùng duy nhất package `demo`. Khi làm thư viện tổng quát, cần xử lý cả trường hợp unnamed package, trùng tên sinh ra và nhiều class được đánh dấu.

### File 3 — `src/demo/Widget.java`

```java
package demo;

@GenerateInfo
public class Widget {
}
```

### File 4 — `src/demo/Main.java`

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class Main {
    public static void main(String[] args) throws IOException {
        System.out.println(WidgetGenerated.message());

        try (InputStream input =
                Main.class.getResourceAsStream("Widget.info")) {

            if (input == null) {
                throw new IOException("Missing demo/Widget.info");
            }

            String value = new String(
                    input.readAllBytes(), StandardCharsets.UTF_8).trim();
            System.out.println("resource: " + value);
        }
    }
}
```

`Main.class.getResourceAsStream("Widget.info")` tra tài nguyên **tương đối với package `demo` của `Main`**, nghĩa là tìm `demo/Widget.info` trong classpath. Tên không có dấu `/` đầu chuỗi là có chủ ý.

### Lệnh build và chạy

Tại thư mục chứa `src`, tạo ba thư mục output trước. Với Bash (Linux/macOS/Git Bash):

```bash
mkdir -p build/processor build/classes build/generated
```

Trên Windows PowerShell, có thể dùng:

```powershell
New-Item -ItemType Directory -Force build/processor, build/classes, build/generated | Out-Null
```

Sau đó chạy các lệnh `javac`/`java` dưới đây trong terminal có JDK 17+ và tại đúng thư mục:

```bash
javac -d build/processor src/demo/GenerateInfo.java src/demo/GenerateInfoProcessor.java

javac -cp build/processor -processorpath build/processor -processor demo.GenerateInfoProcessor -s build/generated -d build/classes src/demo/Widget.java src/demo/Main.java

java -cp build/classes demo.Main
```

**Stdout của lệnh `java` cuối cùng:**

```text
generated: Widget
resource: Widget
```

Compiler có thể hiển thị diagnostic/cảnh báo riêng tùy môi trường; hai dòng trên là stdout của **ứng dụng chạy**, không phải một “log bắt buộc” của compiler.

Sau khi biên dịch, cấu trúc output điển hình:

```text
build/
├── processor/
│   └── demo/
│       ├── GenerateInfo.class
│       └── GenerateInfoProcessor.class
├── generated/
│   └── demo/
│       └── WidgetGenerated.java
└── classes/
    └── demo/
        ├── Widget.class
        ├── WidgetGenerated.class
        ├── Main.class
        └── Widget.info
```

Đây là lý do `Main` có thể dùng `WidgetGenerated`: processor đã tạo source và compiler xử lý nó trong các round thích hợp của **cùng lệnh `javac`**.

Nếu chạy lại lệnh build, nên làm sạch hoặc quản lý nhất quán artifact cũ và đầu ra sinh mã. Trong **mỗi một lượt chạy annotation processing**, không được gọi `createSourceFile` hai lần cho cùng tên kiểu; điều này khác với việc tạo lại file output trong **hai lượt build riêng biệt**.

## 6. `createResource`: sinh file phụ có tên tương đối

Chữ ký Java:

```java
FileObject createResource(
        JavaFileManager.Location location,
        CharSequence moduleAndPkg,
        CharSequence relativeName,
        Element... originatingElements) throws IOException;
```

Ba nhóm tham số:

- `location`: vị trí logic, phổ biến là `StandardLocation.CLASS_OUTPUT` hoặc `StandardLocation.SOURCE_OUTPUT`.
- `moduleAndPkg`: package hoặc module/package (đối với môi trường module), ví dụ `"demo"`.
- `relativeName`: tên/đường dẫn tương đối bên trong package, ví dụ `"Widget.info"` hay `"META-INF/my-tool/index.txt"` khi dùng package rỗng.

Ví dụ minh họa:

```java
FileObject out = processingEnv.getFiler().createResource(
        StandardLocation.CLASS_OUTPUT,
        "demo",
        "Widget.info",
        originElement);

try (Writer writer = out.openWriter()) {
    writer.write("Widget\n");
}
```

Đây là mảnh mã bên trong processor, cần các import và biến `originElement` thích hợp.

Khi `-d build/classes` và package `demo` được dùng như trong ví dụ hoàn chỉnh, tệp tài nguyên nằm tương ứng tại `build/classes/demo/Widget.info`. Đây là nơi ứng dụng runtime có thể đọc bằng classpath nếu artifact giữ lại resource ấy.

Các lưu ý:

- `createResource` dùng **đường dẫn tương đối**, không nhận đường dẫn tuyệt đối kiểu `C:\...` hoặc `/tmp/...`.
- `relativeName` phải khác rỗng, không có segment `.` hay `..`; ký tự phân tách segment trong tên tương đối là dấu `/`.
- Nếu `moduleAndPkg` là chuỗi rỗng, tên tương đối được hiểu tại gốc của location.
- Với môi trường JPMS, `moduleAndPkg` có thể mang tiền tố `moduleName/package.name` và công cụ có thể cần xác định module đích.
- Một resource được tạo bởi `createResource` **không được tự đưa vào processing round mới** chỉ vì tên nó kết thúc bằng `.java`.
- Không chọn tên resource đụng cùng đường dẫn với một source/class được tạo qua các phương thức khác.

### `CLASS_OUTPUT` và `SOURCE_OUTPUT`

| Location | Vai trò thường dùng | Điểm cần nhớ |
|---|---|---|
| `StandardLocation.CLASS_OUTPUT` | Tài nguyên được đóng gói cùng class/runtime artifact | Thường trỏ tới vùng `-d` |
| `StandardLocation.SOURCE_OUTPUT` | Tài nguyên bổ trợ đặt cùng cây source sinh ra | Thường trỏ tới vùng `-s` |

Đây là các **vị trí logic mà file manager phải hỗ trợ** cho Filer. Hãy kiểm tra cấu hình build thực tế thay vì tự giả định luôn có cùng đường dẫn vật lý trên mọi compiler.

Ví dụ file metadata để đóng gói JAR có thể cần `CLASS_OUTPUT`; file chỉ phục vụ sinh tài liệu/source khác có thể phù hợp `SOURCE_OUTPUT`.

## 7. `getResource`: đọc tài nguyên đã có, không phải sinh mới

Chữ ký:

```java
FileObject getResource(
        JavaFileManager.Location location,
        CharSequence moduleAndPkg,
        CharSequence relativeName) throws IOException;
```

Đọc một file phụ có sẵn bằng `openReader(...)` hoặc `openInputStream()`:

```java
FileObject resource = processingEnv.getFiler().getResource(
        StandardLocation.CLASS_OUTPUT,
        "demo",
        "previous-report.txt");

try (java.io.Reader reader = resource.openReader(true)) {
    char[] buffer = new char[1024];
    int n;
    while ((n = reader.read(buffer)) >= 0) {
        // Xử lý đúng n ký tự vừa đọc.
    }
}
```

Đây là mảnh minh họa trong processor; file `demo/previous-report.txt` phải tồn tại và location phải có khả năng đọc. `openReader(true)` dùng chính sách bỏ qua lỗi mã hóa theo API FileObject; code production cần quy định encoding và xử lý trường hợp file thiếu.

**Không được** coi `getResource` là cách “đọc lại ngay” một resource đã được mở để ghi bằng `createResource` trong cùng lượt chạy. Theo hợp đồng Filer, nếu cùng pathname đã được mở để ghi trong processing run, `getResource` có thể ném `FilerException`. Cần tổ chức input và output rõ ràng, hoặc giữ dữ liệu trong bộ nhớ khi vừa sinh xong thay vì tạo file rồi đọc lại nó.

`getResource` không nhận `originatingElements` vì nó chỉ đọc. Nếu cần phân tích file từ dependency hoặc classpath, `getResource` có thể được hỗ trợ tại những location nhất định tùy file manager; `CLASS_OUTPUT` và `SOURCE_OUTPUT` là hai location được bảo đảm, còn các location khác cần kiểm tra khả năng hỗ trợ của công cụ.

## 8. `createClassFile`: ghi **bytecode**, không ghi Java source

Chữ ký:

```java
JavaFileObject createClassFile(
        CharSequence name,
        Element... originatingElements) throws IOException;
```

`createClassFile` thích hợp khi processor có **nội dung class-file binary hợp lệ**, ví dụ từ một bộ sinh bytecode. Khác với `createSourceFile`, ở đây bạn không được viết text Java:

```java
// CHỈ LÀ MẢNH MINH HỌA — validClassBytes phải được tạo hợp lệ.
JavaFileObject classOut =
        processingEnv.getFiler().createClassFile(
                "demo.GeneratedBytecode", originElement);

try (java.io.OutputStream out = classOut.openOutputStream()) {
    out.write(validClassBytes);
}
```

`validClassBytes` trong đoạn này là biến giả định chứa **đầy đủ định dạng JVM ClassFile**, không phải chuỗi `"public class ..."`. Mã trên **không chạy độc lập** vì chưa cung cấp bộ sinh bytecode, là lựa chọn phù hợp khi chỉ cần hiểu API.

Nếu ghi source text vào `createClassFile`, compiler/JVM không biến nó thành `.class` hợp lệ. Muốn sinh Java source, dùng `createSourceFile` và để `javac` chịu trách nhiệm biên dịch.

Tên `"demo.GeneratedBytecode"` là **binary name** của class được ghi, không phải đường dẫn `"demo/GeneratedBytecode.class"`. Bộ sinh bytecode cần bảo đảm tên bên trong classfile, các cấu trúc constant pool, method descriptors và phiên bản class file tương thích với môi trường biên dịch/chạy.

Theo Filer, class file được tạo và đóng luồng cũng được công cụ xem xét cho **các round tiếp theo**. Điều đó không có nghĩa class file luôn được class loader của processor nạp để có thể dùng như một class Java runtime trong chính processor.

### Nên chọn `createSourceFile` hay `createClassFile`?

- **Ưu tiên `createSourceFile`** nếu mục tiêu là sinh Java API từ annotation: dễ đọc, dễ debug, compiler kiểm tra cú pháp và tương thích source level.
- Dùng **`createClassFile`** nếu thực sự cần xuất class binary, có bộ sinh bytecode đúng chuẩn và biết cách kiểm tra tính hợp lệ.
- Dùng **`createResource`** cho thông tin không cần compiler xem như một kiểu Java.

Một file `.class` do processor tạo cũng không thể dùng để tùy tiện sửa class đầu vào; Filer kiểm soát tính duy nhất của các type/file được tạo.

## 9. `originatingElements`: vì sao nên truyền phần tử nguồn?

Các phương thức tạo file nhận `Element... originatingElements`. Đây là những phần tử (class, interface, package, module...) **gây ra quyết định sinh file**.

Ví dụ:

```java
TypeElement widget = ...; // Lấy từ mô hình annotation processing.

JavaFileObject generated =
        processingEnv.getFiler().createSourceFile(
                "demo.WidgetGenerated",
                widget);
```

Đoạn là mảnh minh họa, chưa độc lập vì `widget` cần được truy xuất qua `RoundEnvironment` hoặc `Elements`.

**Tác dụng:**

- Cung cấp quan hệ phụ thuộc giữa input và output để công cụ build/incremental processing có thể sử dụng.
- Giúp một số môi trường quyết định khi nào cần chạy lại processor hoặc xóa tệp sinh ra nếu nguồn thay đổi.
- Làm rõ tính truy vết khi một processor sinh nhiều files.

**Không nên hiểu sai:**

- `originatingElements` **không** tự tạo file, không điều chỉnh nội dung và không thay thế `Writer`.
- Không bảo đảm mọi build tool đều dùng thông tin ấy giống nhau; công cụ không hỗ trợ incremental có thể bỏ qua.
- Không bắt buộc truyền một element nếu thực sự không có nguồn gốc phù hợp, nhưng nên truyền đúng các nguồn nhân quả khi có.
- Nếu output phụ thuộc **nhiều** source elements, cần cung cấp danh sách phù hợp thay vì chỉ truyền một nguồn không đủ đại diện.

Ví dụ một index sinh từ nhiều class có thể dùng:

```java
Element[] origins = collectedElements.toArray(Element[]::new);
FileObject index = processingEnv.getFiler().createResource(
        StandardLocation.CLASS_OUTPUT,
        "",
        "META-INF/my-tool/index.txt",
        origins);
```

Đây là mảnh code minh họa, giả định `collectedElements` đã được xây dựng và import `Element`/`FileObject`. Hành vi incremental thực tế vẫn tùy môi trường build và kiểu processor.

## 10. Quy tắc **tạo một lần** và `FilerException`

`Filer` có nguyên tắc rất quan trọng: **trong một lượt chạy annotation processing, một pathname chỉ được tạo một lần**. Ngoài ra, không được tạo source file và class file **cho cùng một type name** trong lượt chạy ấy.

Ví dụ cố ý sai:

```java
Filer filer = processingEnv.getFiler();

filer.createSourceFile("demo.WidgetGenerated");
filer.createSourceFile("demo.WidgetGenerated"); // FilerException
```

Chỉ là mảnh minh họa; khi dùng thực tế, mỗi đối tượng file đầu ra phải được ghi và đóng đúng cách. Lời gọi tạo thứ hai cùng tên trong **cùng lượt processing** vi phạm quy tắc, kể cả nếu nó diễn ra ở processing round khác.

Một lỗi khác:

```java
filer.createSourceFile("demo.WidgetGenerated");
filer.createClassFile("demo.WidgetGenerated"); // Xung đột cùng kiểu
```

Công cụ cũng xem các **input ban đầu** như đã được tạo ở “round 0”. Vì vậy, nếu `demo.Widget` là source ban đầu đang biên dịch, processor không thể dùng `createSourceFile("demo.Widget")` để thay thế nội dung của chính kiểu ấy.

`FilerException` kế thừa `IOException`. Bạn có thể bắt riêng để thông báo đúng nguyên nhân:

```java
try {
    // Tạo một file mới qua Filer.
} catch (javax.annotation.processing.FilerException ex) {
    processingEnv.getMessager().printMessage(
            javax.tools.Diagnostic.Kind.ERROR,
            "Duplicate generated file: " + ex.getMessage());
} catch (java.io.IOException ex) {
    processingEnv.getMessager().printMessage(
            javax.tools.Diagnostic.Kind.ERROR,
            "I/O error: " + ex.getMessage());
}
```

Ví dụ là khung xử lý ngoại lệ minh họa, không gồm lời gọi tạo file cụ thể trong khối `try`.

### Phân biệt “đã có từ build trước” với “đã tạo trong run này”

Java Filer quy định: nếu một output pathname đã có trước **lần tạo đầu tiên** của lượt xử lý, nội dung cũ của file ấy có thể được xóa/thay bằng output mới. `FilerException` chủ yếu bảo đảm **không tạo lại cùng đường dẫn trong một processing run**, chứ không phải cơ chế chống ghi đè vĩnh viễn mọi file đã tồn tại trên ổ đĩa.

Do đó, không được dựa vào Filer như một công cụ bảo toàn file thủ công. Hãy dành output directory riêng cho mã sinh, tránh trỏ output tới thư mục chứa source do con người sửa.

### Phòng tránh `FilerException` trong nhiều rounds

- Dùng quy tắc tên **xác định và không xung đột** từ input, ví dụ `pkg + "." + simpleName + "Generated"`.
- Chỉ sinh file khi tìm thấy đúng phần tử nguồn của round, không gọi create vô điều kiện mỗi khi `process` chạy.
- Nếu processor tạo nhiều tệp từ nhiều input, theo dõi tên đã tạo bằng một `Set<String>` duy trì trên processor instance để tránh tạo lại trong các round khác.
- Khi `roundEnv.processingOver()` là `true`, xử lý tổng kết thay vì cố sinh type mới.
- Nếu hai processor khác nhau sinh cùng tên kiểu hoặc cùng pathname, phối hợp naming/ownership. Claim annotation type không tự giải quyết xung đột output name.
- Khi báo lỗi, đính kèm `Element` nguồn qua `Messager` để người dùng biết metadata nào dẫn đến tên trùng.

## 11. Tên kiểu, tên resource và module cần đúng ngữ nghĩa

Ba họ API có quy tắc đặt tên khác nhau:

| API | Tham số định danh chính | Ví dụ |
|---|---|---|
| `createSourceFile` | Tên canonical/FQN của kiểu chính hoặc `.package-info` khi tạo package-info | `"demo.WidgetGenerated"` |
| `createClassFile` | Binary name của kiểu hoặc `.package-info` cho named package | `"demo.WidgetGenerated"` |
| `createResource` | `location` + `moduleAndPkg` + `relativeName` | `CLASS_OUTPUT`, `"demo"`, `"Widget.info"` |
| `getResource` | Cùng ba tham số vị trí/tên | `CLASS_OUTPUT`, `"demo"`, `"Widget.info"` |

Với kiểu nested, **canonical name** và **binary name** có thể khác nhau (ví dụ dấu `.` so với `$`). Cần dùng tên đúng yêu cầu từng API, đặc biệt khi tạo classfile trực tiếp.

### `package-info`

`Filer` có thể tạo source cho thông tin package bằng một tên như `"demo.package-info"`. Tệp tạo ra là `package-info.java` trong package tương ứng. `createClassFile` có trường hợp cho `package-info.class` của named package.

Nên chỉ dùng khi nhiệm vụ thật sự cần sinh package metadata và không xung đột file `package-info.java` hoặc `package-info.class` đã được compiler/build tạo.

### JPMS và nhiều module

Trong môi trường module (Java 9+), tên tạo source/class có thể mang prefix module, ví dụ `"billing.api/demo.WidgetGenerated"` theo cú pháp API. Với resource, `moduleAndPkg` có dạng `"billing.api/demo"` khi công cụ yêu cầu module đích.

Nếu module đích không thể suy ra, không writable hoặc cấu hình location không hỗ trợ module prefix, Filer có thể ném `FilerException`. Trong dự án multi-module, đừng áp dụng máy móc ví dụ classpath đơn giản mà bỏ qua module path và cấu hình build.

## 12. Ghi đúng mã hóa, đóng luồng và quản lý lỗi

Khi dùng `openWriter()`, charset có thể do implementation và tùy chọn compiler như `-encoding` quyết định. Với mã Java/metadata có dấu tiếng Việt, **đừng mặc định mọi môi trường đều ghi UTF-8 giống nhau**.

Có thể chọn UTF-8 tường minh qua `OutputStreamWriter`:

```java
JavaFileObject javaFile =
        filer.createSourceFile("demo.GeneratedUtf8", origin);

try (java.io.Writer writer = new java.io.OutputStreamWriter(
        javaFile.openOutputStream(),
        java.nio.charset.StandardCharsets.UTF_8)) {

    writer.write("package demo;\n"
            + "public class GeneratedUtf8 {}\n");
}
```

Đây là mảnh minh họa bên trong processor, `origin` phải là `Element` hợp lệ. Khi dùng `openWriter()` trực tiếp, hãy thiết lập encoding của `javac`/build pipeline một cách rõ ràng. Bất kể cách nào, **đóng luồng** để compiler có thể nhìn thấy tệp hoàn chỉnh.

Những việc khác cần lưu ý:

- Tạo nội dung Java hợp lệ với source version mà processor/build sử dụng.
- Với classfile binary, ghi bytes hợp lệ và khớp phiên bản JVM; không ghi text qua `Writer`.
- Không mở nhiều Writer/OutputStream cho cùng file object để ghi cạnh tranh.
- Không nuốt `IOException`. Báo diagnostic rõ ràng hoặc để công cụ xử lý theo contract.
- Với resource text, thống nhất encoding cho cả bên ghi và bên đọc.
- Không dùng resource file để “lén” tạo một Java source/class mà compiler tự nhận ra; `createResource` không đăng ký tệp kiểu ấy cho round kế tiếp.

## 13. Lỗi thường gặp khi dùng `Filer`

### 13.1. Sinh source nhưng không có round sau nhận file

**Triệu chứng:** Generated source không được biên dịch như kỳ vọng.

**Kiểm tra:** code có thật sự gọi `createSourceFile` không? `Writer` có được đóng không? Processor có sinh ở round cuối không? Tên type/package có đúng và source có biên dịch được không?

Sửa bằng cách sinh source trong round phù hợp, đóng Writer và kiểm tra compiler diagnostics cùng đường dẫn output.

### 13.2. Truyền path filesystem vào `createSourceFile`

Sai:

```java
filer.createSourceFile("src/demo/WidgetGenerated.java");
```

Đúng:

```java
filer.createSourceFile("demo.WidgetGenerated");
```

Hai dòng là mảnh minh họa trong processor. Filer nhận **tên kiểu**, còn đường dẫn file do file manager xác định.

### 13.3. Sinh cùng tên ở nhiều round

Sai:

```java
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment roundEnv) {
    filer.createSourceFile("demo.AlwaysGenerated"); // Giả định có filer, throws IOException
    return true;
}
```

Đây là mã **cố ý sai/không độc lập**, vì phải xử lý `IOException` và quá trình gọi `process` có thể lặp qua nhiều round. Nếu gọi tạo cùng tên lần hai, Filer sẽ ném `FilerException`. Chỉ tạo khi có input tương ứng và theo dõi tên đã tạo.

### 13.4. Dùng `createResource` để “sinh Java class”

Nếu tạo `WidgetGenerated.java` bằng `createResource`, compiler không tự đăng ký tệp đó để xử lý như source mới. Dùng `createSourceFile` cho Java source.

### 13.5. Ghi Java text vào `createClassFile`

`createClassFile` yêu cầu **classfile bytes**, không phải Java source. Nếu mục tiêu là sinh code dễ debug, hãy dùng `createSourceFile`.

### 13.6. Không truyền `originatingElements`

Điều này **không nhất thiết là lỗi biên dịch**, nhưng khiến một số build tool khó theo dõi dependency cho incremental compilation. Nếu output phát sinh từ một class/element cụ thể, truyền nguồn phù hợp.

### 13.7. Tên resource không tương đối

Các tên như `"../secret.txt"`, `"/absolute.txt"` hoặc chuỗi rỗng là không hợp lệ cho `relativeName`. Dùng tên tương đối rõ ràng như `"META-INF/my-tool/index.txt"` với package thích hợp. Tránh trùng đường dẫn output của công cụ khác.

### 13.8. Mong `getResource` đọc lại file vừa tạo cùng run

Filer có thể từ chối việc lấy resource cho đường dẫn đã được mở để ghi, kể cả mục đích là kiểm tra ngay. Để xác thực output, kiểm tra dữ liệu trước khi ghi hoặc dùng bước kiểm tra sau build; không giả định `getResource` cho phép mọi dạng read-after-write trong cùng run.

### 13.9. Tạo file nhưng không xử lý `IOException`

Lỗi truy cập file, tên type sai, module không ghi được hoặc xung đột tên có thể gây exception. Bắt lỗi có mục đích và báo qua `Messager`; đừng chỉ log ra `System.out` rồi để compiler cho rằng mọi thứ đã ổn.

### 13.10. Nhầm claim của `process` với quyền ghi file

`return true` trong `process` chỉ claim các annotation types được giao trong round; nó không cấp quyền vượt mọi quy tắc Filer, không tránh xung đột file name và không bảo đảm compiler build thành công.

## 14. Bài tập tự kiểm tra

Giả sử processor gặp:

```java
@GenerateInfo
class Invoice {}
```

Với quy tắc sinh `InvoiceGenerated.java` và `Invoice.info`, hãy trả lời:

1. Muốn sinh `demo.InvoiceGenerated.java`, nên gọi `createSourceFile("demo.InvoiceGenerated")` hay `createResource(..., "InvoiceGenerated.java")`?
2. Sau khi `Writer` của source mới đóng, compiler có thể xem xét file ở round nào?
3. Muốn sinh resource đọc khi chương trình chạy cùng classpath, `CLASS_OUTPUT` hay `SOURCE_OUTPUT` thường phù hợp hơn?
4. Muốn tự tạo `InvoiceGenerated.class` mà không có source Java, `createClassFile` phải ghi nội dung kiểu nào?
5. Có được gọi `createSourceFile("demo.InvoiceGenerated")` hai lần trong cùng lượt xử lý không?
6. Nếu đã có `InvoiceGenerated.java` từ build trước ở output directory, `FilerException` có bảo đảm tuyệt đối không chạm file đó không?
7. `originatingElements` giúp công cụ build hiểu điều gì?
8. `createResource(CLASS_OUTPUT, "demo", "Invoice.info")` có tự đăng ký `Invoice.info` làm Java class cho round sau không?
9. Nếu gọi `getResource` với đúng pathname đã được mở để ghi trong processing run, chuyện gì có thể xảy ra?
10. Muốn kiểm tra lỗi bất hợp lệ trong mã nguồn annotation, nên dùng `Messager` hay giá trị boolean `return false` để báo lỗi compiler?
11. `createSourceFile("demo.Invoice")` có hợp lệ khi `Invoice.java` là input ban đầu của chính lượt `javac`?
12. Trong project nhiều module, có thể luôn bỏ qua việc xác định module đích khi sinh file không?

**Đáp án:**

1. **`createSourceFile`** vì cần compiler đăng ký và xử lý Java source mới.
2. **Round tiếp theo**, sau khi Writer được đóng và nếu môi trường xử lý tiếp theo phù hợp.
3. **`CLASS_OUTPUT`** thường phù hợp để resource nằm trong runtime artifact/classpath.
4. **Bytecode JVM ClassFile hợp lệ**, không phải chuỗi Java source.
5. **Không.** Tạo lại cùng pathname trong một processing run gây `FilerException`.
6. **Không.** File tồn tại trước lần tạo đầu trong run có thể bị xóa/thay theo hợp đồng Filer.
7. **Quan hệ nguồn gốc/dependency** của generated file, hữu ích cho một số công cụ incremental.
8. **Không.** Resource không tự được đăng ký như source/class mới cho rounds.
9. Có thể bị **`FilerException`** do Filer kiểm soát read/write cùng pathname.
10. **`Messager`**, ví dụ `Diagnostic.Kind.ERROR`; boolean `process` chỉ liên quan claim annotation types.
11. **Không.** Input ban đầu được xem là đã tạo ở round 0; không được tạo lại source cùng type.
12. **Không.** Có trường hợp công cụ không suy ra module đích hoặc location không hỗ trợ cách chỉ định module, dẫn tới `FilerException`.

## 15. Checklist khi viết annotation processor sinh file

- [ ] Đã xác định output là Java source, classfile bytes hay auxiliary resource.
- [ ] Sử dụng `processingEnv.getFiler()` thay vì ghi tùy tiện vào source tree bằng filesystem API.
- [ ] Với Java source, dùng `createSourceFile(FQN, origins...)`, không truyền đường dẫn `.java`.
- [ ] Với classfile, dùng `createClassFile(binaryName, origins...)` và chỉ ghi bytecode hợp lệ.
- [ ] Với resource, dùng `createResource(location, moduleAndPkg, relativeName, origins...)`.
- [ ] Chọn `SOURCE_OUTPUT`/`CLASS_OUTPUT` đúng mục đích; hiểu `-s` và `-d`.
- [ ] Đóng `Writer`/`OutputStream` bằng `try-with-resources` trước khi compiler cần xử lý tệp.
- [ ] Không cố tạo lại cùng pathname trong một run hoặc tạo source/class cùng type name.
- [ ] Tránh tạo trùng input đã có từ round 0; đặt tên generated types riêng.
- [ ] Truyền `originatingElements` tương ứng với nguồn thật khi có.
- [ ] Xử lý `IOException`/`FilerException` và báo diagnostic bằng `Messager`.
- [ ] Xử lý nhiều rounds, tập annotations rỗng, và `processingOver()` hợp lý.
- [ ] Với Java source, kiểm tra package, tên public class, source version và encoding.
- [ ] Với resource, dùng relative name hợp lệ; không kỳ vọng resource tự mở round mới.
- [ ] Nếu có nhiều processors/modules, kiểm tra quyền tạo file, tên output và module đích.
- [ ] Biên dịch và chạy ví dụ kiểm tra cả generated source/class lẫn resource trong artifact cuối.

## 16. Tài liệu chính thức và tổng kết

- [Java SE 17 — `Filer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html): hợp đồng về source/class/resource, rounds, nguồn gốc, cách đặt tên và `FilerException`.
- [Java SE 17 — `FilerException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/FilerException.html): những tình huống tạo file không hợp lệ.
- [Java SE 17 — `RoundEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): lấy elements theo annotation và nhận diện round cuối.
- [Java SE 17 — `ProcessingEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html): truy cập `getFiler()` và các dịch vụ khác của processor.

**Tóm lại:** `Filer` là “cửa ghi” chính thức của annotation processor. `createSourceFile` sinh Java source cho round tiếp theo, `createClassFile` xuất bytecode hợp lệ, `createResource` tạo file phụ nhưng không đăng ký nó như source/class, còn `getResource` đọc tài nguyên đã có. Tên đúng, đóng luồng, originating elements, lựa chọn output location và nguyên tắc tạo một lần là các yếu tố quyết định một processor sinh mã ổn định.