# Processor, AbstractProcessor và ProcessingEnvironment — Annotation Processing trong Java

## 1. Vì sao annotation cần processor ở thời điểm biên dịch?

Trong Java, một annotation như `@GenerateGreeting` chỉ là **metadata** được viết trong mã nguồn. Khai báo nó không có nghĩa JVM tự động sinh class, kiểm tra nghiệp vụ hay thực thi method khác.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface GenerateGreeting {
}
~~~

Để thực hiện công việc dựa trên annotation **trong lúc biên dịch**, Java có chuẩn **JSR 269 / Pluggable Annotation Processing API**. Compiler như `javac` có thể nạp một **annotation processor** để đọc mô hình chương trình, phát diagnostic và sinh thêm mã nguồn hoặc tài nguyên.

Ba thành phần cốt lõi có mối quan hệ:

- **`javax.annotation.processing.Processor`**: interface định nghĩa *hợp đồng và vòng đời* của processor.
- **`javax.annotation.processing.AbstractProcessor`**: abstract class implements `Processor`, cung cấp phần triển khai mặc định và trường ngữ cảnh; ta kế thừa để bớt boilerplate.
- **`javax.annotation.processing.ProcessingEnvironment`**: ngữ cảnh compiler được cấp khi khởi tạo, cung cấp `Filer`, `Messager`, `Elements`, `Types`, options và thông tin phiên biên dịch.

Một thành phần liên quan nhưng **không đồng nghĩa** với `ProcessingEnvironment` là **`RoundEnvironment`**: dữ liệu và trạng thái của *từng vòng xử lý annotation*.

~~~text
Mã nguồn @GenerateGreeting
             |
             v
javac tìm và nạp Processor
             |
             v
init(ProcessingEnvironment)  — chuẩn bị dịch vụ
             |
             v
process(..., RoundEnvironment)  — đọc elements của một round
             |
             +-- Elements / Types: phân tích mô hình source
             +-- Messager: lỗi / cảnh báo / ghi chú
             +-- Filer: tạo Java source / class / resource mới
             |
             v
javac xử lý source được sinh ở round tiếp theo
             |
             v
Mã .class và tài nguyên của ứng dụng
~~~

Tất cả API này thuộc JDK chuẩn, thường trong module **`java.compiler`**. Package Java 17 vẫn có tên **`javax.annotation.processing`**, không phải `jakarta.annotation.processing`.

## 2. `Processor`: hợp đồng của một compiler plugin

`Processor` là interface công khai xác định những phương thức một annotation processor phải cung cấp.

| Phương thức | Chức năng |
| --- | --- |
| `init(ProcessingEnvironment env)` | Được compiler gọi để khởi tạo và cấp môi trường |
| `getSupportedAnnotationTypes()` | Liệt kê annotation types mà processor quan tâm |
| `getSupportedSourceVersion()` | Mức Java source language processor tuyên bố hỗ trợ |
| `getSupportedOptions()` | Các tên tùy chọn `-Akey=value` processor nhận biết |
| `process(Set<? extends TypeElement> annotations, RoundEnvironment roundEnv)` | Xử lý các annotation types/phần tử trong một round |
| `getCompletions(Element, AnnotationMirror, ExecutableElement, String)` | Có thể cung cấp gợi ý hoàn thành giá trị annotation trong công cụ hỗ trợ |

Khi triển khai trực tiếp `Processor`, phải viết đầy đủ hợp đồng. Phần lớn processor thông thường **kế thừa `AbstractProcessor`** thay vì implements interface trực tiếp.

### `getSupportedAnnotationTypes()`

Processor cần nói rõ loại annotation mà nó sẽ nhận:

~~~java
@SupportedAnnotationTypes("demo.GenerateGreeting")
~~~

Đây là meta-annotation trên **lớp processor**. Giá trị là tên đầy đủ của annotation type cần xử lý; trong ví dụ là `demo.GenerateGreeting`.

Có thể hỗ trợ nhiều tên, thậm chí mẫu `"*"` để nhận mọi annotation type. Nhưng `"*"` cần cân nhắc vì việc claim quá rộng có thể làm ảnh hưởng cách những processor khác được compiler điều phối. Không nên dùng `"*"` chỉ để tránh viết tên annotation.

**Điều quan trọng:** `@SupportedAnnotationTypes` không phải cách *đăng ký* processor. Nó chỉ cung cấp thông tin sau khi processor đã được nạp; phải chỉ định processor qua `-processor` hoặc đăng ký service phù hợp.

### `getSupportedSourceVersion()`

Một processor viết và kiểm thử với cú pháp Java 17 có thể khai báo:

~~~java
@SupportedSourceVersion(SourceVersion.RELEASE_17)
~~~

Với import `javax.annotation.processing.SupportedSourceVersion` và `javax.lang.model.SourceVersion`. Đây là **source language level**, không phải phiên bản bytecode mà processor sinh ra hay phiên bản JRE dùng để chạy ứng dụng.

Ngoài annotation trên, subclass có thể override `getSupportedSourceVersion()`; nên đảm bảo giá trị công bố phản ánh năng lực đã kiểm thử.

### `getSupportedOptions()`

Compiler cho truyền tham số riêng cho processor:

~~~bash
javac -Agreeting.strict=true ...
~~~

Processor có thể công bố `@SupportedOptions("greeting.strict")` và đọc:

~~~java
String raw = processingEnv.getOptions()
        .getOrDefault("greeting.strict", "false");
boolean strict = Boolean.parseBoolean(raw);
~~~

Đây là fragment thuộc class processor. `getOptions()` trả về `Map<String, String>`; processor tự quyết định cách parse và kiểm tra hợp lệ. Lưu ý `Boolean.parseBoolean("garbage")` trả `false`, không tự phát diagnostic lỗi; nếu cần strict validation phải tự kiểm tra chuỗi.

## 3. `AbstractProcessor`: cách triển khai thông dụng

`AbstractProcessor` là lớp nền thực thi nhiều phần của `Processor`. Đáng chú ý, nó giữ trường:

~~~java
protected ProcessingEnvironment processingEnv;
~~~

Compiler gọi `init(ProcessingEnvironment)` và lớp nền thiết lập trường này. Subclass thường chỉ cần định nghĩa xử lý chính:

~~~java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    // Đọc phần tử được đánh dấu; kiểm tra; sinh source nếu cần.
    return true;
}
~~~

**Đây chỉ là fragment phương thức**; phần ví dụ chạy đầy đủ ở dưới cung cấp class, imports, annotation và build commands.

`AbstractProcessor` đọc các `@SupportedAnnotationTypes`, `@SupportedOptions`, `@SupportedSourceVersion` để thực thi mặc định các phương thức truy vấn tương ứng. Nó **không tự hiểu nghiệp vụ** của một annotation tùy chỉnh, không tự viết file source, và không tự tạo runtime interception.

Nếu cần ghi đè `init` để khởi tạo thêm tài nguyên, phải gọi lớp cha:

~~~java
@Override
public synchronized void init(ProcessingEnvironment env) {
    super.init(env);
    // Chuẩn bị state bổ sung.
}
~~~

Không được tự khởi tạo bằng cách `new ProcessingEnvironment()`: nó là interface do compiler cung cấp. Cũng không nên giữ đối tượng này làm biến toàn cục để tái sử dụng tùy tiện giữa các phiên biên dịch.

### `process` trả `boolean` có nghĩa gì?

- `true`: processor **claim** tập annotation types được chuyển vào tham số `annotations` của round, để các processor đến sau không tiếp tục nhận chúng như những types chưa được claim.
- `false`: processor **không claim** chúng; processor khác vẫn có cơ hội nhận và xử lý.

`true` không phải “biên dịch thành công”, `false` không phải “biên dịch lỗi”, và việc claim không có nghĩa compiler dừng mọi vòng xử lý.

Muốn báo lỗi thực sự phải dùng:

~~~java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Invalid use of @GenerateGreeting",
        element);
~~~

Đoạn này là fragment; `element` là phần tử đang bị kiểm tra và `Diagnostic` thuộc `javax.tools`. Compiler có thể gắn diagnostic với vị trí phần tử trong source. Đừng dùng `return false` thay cho việc phát lỗi.

## 4. `ProcessingEnvironment`: các dịch vụ compiler cấp cho processor

`ProcessingEnvironment` được truyền vào `init` **một lần khi khởi tạo processor**, giữ ngữ cảnh chung trong một lượt annotation-processing. Các phương thức thiết yếu:

| Phương thức | Kiểu trả về | Công dụng |
| --- | --- | --- |
| `getFiler()` | `Filer` | Tạo source, class hoặc resource file |
| `getMessager()` | `Messager` | In diagnostic `ERROR`, `WARNING`, `NOTE`... |
| `getElementUtils()` | `Elements` | Truy vấn declaration elements, package, tên, kiểu được khai báo |
| `getTypeUtils()` | `Types` | Xử lý `TypeMirror`, quan hệ subtype/assignability |
| `getOptions()` | `Map<String,String>` | Nhận option do công cụ truyền bằng `-A` |
| `getSourceVersion()` | `SourceVersion` | Biết language source level mà môi trường đang sử dụng |
| `getLocale()` | `Locale` | Locale của môi trường (có thể `null`) |

Cần phân biệt `ProcessingEnvironment` với `RoundEnvironment`: **một bên là hạ tầng và dịch vụ**, một bên chứa trạng thái và phần tử của **round hiện tại**. Đừng coi chúng như hai tên của cùng một đối tượng.

### `Filer` — sinh tệp theo quy tắc của compiler

Ví dụ:

~~~java
JavaFileObject file = processingEnv.getFiler()
        .createSourceFile("demo.SampleGreeting", element);
~~~

Đoạn này là fragment, dùng `javax.tools.JavaFileObject`. `Filer` quản lý tệp sinh trong phiên biên dịch:

- Tên được truyền là tên đầy đủ của source type.
- Tham số `element` là **originating element**, giúp công cụ build biết file sinh có nguồn gốc từ khai báo nào.
- `-s build/generated` chỉ định thư mục source output của `javac`.
- Compiler có thể xét source mới trong các processing rounds tiếp theo.
- Không được tạo lại một tên/path đã được tạo trong cùng lượt xử lý. Có thể nhận `FilerException` (là `IOException`).

Dùng **try-with-resources** để đóng `Writer` sau khi ghi đầy đủ source, tránh làm compiler nhận tệp chưa hoàn tất.

### `Messager` — diagnostic có mức độ

`Messager.printMessage` có nhiều overload, có thể gắn thông báo với `Element`, `AnnotationMirror` hoặc annotation value phù hợp. Các mức thông dụng:

- `Diagnostic.Kind.ERROR`: lỗi compile-time.
- `Diagnostic.Kind.WARNING`: cảnh báo.
- `Diagnostic.Kind.MANDATORY_WARNING`: cảnh báo bắt buộc.
- `Diagnostic.Kind.NOTE`: thông tin.

Để thông báo có vị trí nguồn rõ, truyền thêm phần tử được đánh dấu khi có thể. `System.out.println` không thay thế diagnostic: nó không có tính chất compiler error và thường không chỉ ra vị trí source phù hợp.

### `Elements` khác `Types`

Annotation processor không nhất thiết có các `Class<?>` runtime của đối tượng đang được biên dịch. Nó thường thao tác trên mô hình:

- `TypeElement`: khai báo class/interface/annotation type.
- `ExecutableElement`: method, constructor và thành phần gọi được của mô hình source.
- `VariableElement`: field, parameter, enum constant... theo loại.
- `TypeMirror`: kiểu Java mà declaration/expression biểu diễn.

`processingEnv.getElementUtils()` làm việc với **phần tử khai báo**. `processingEnv.getTypeUtils()` làm việc với **kiểu**.

Ví dụ, một class có type parameter `T`: `TypeElement` diễn tả **khai báo class**, còn `TypeMirror` diễn tả **kiểu của class hoặc các kiểu xuất hiện bên trong**. Nếu muốn so sánh kiểu trả về của một method, thường dùng `Types.isSameType`, không dùng `Class.forName`.

## 5. `RoundEnvironment`: mô hình của mỗi vòng xử lý

Trong `process(..., RoundEnvironment roundEnv)`, các API hay dùng:

~~~java
roundEnv.getElementsAnnotatedWith(GenerateGreeting.class);
roundEnv.getRootElements();
roundEnv.processingOver();
roundEnv.errorRaised();
~~~

- `getElementsAnnotatedWith(...)` giúp tìm những phần tử mang annotation type trong round hiện tại, theo quy tắc API.
- `getRootElements()` trả **root elements của round**, không phải toàn bộ các class của mọi thư viện trên classpath.
- `processingOver()` báo **round xử lý cuối cùng**, không nên mong source tạo trong round ấy sẽ được biên dịch ở round tiếp theo.
- `errorRaised()` báo có error diagnostic từ round trước theo mô hình annotation processing; không phải bộ bắt exception tổng quát.

Một processor có thể được gọi **nhiều lần**. Nếu nó sinh source mới, `javac` có thể chạy thêm round để xem xét source mới. Đừng giả định `process` chỉ được gọi đúng một lần trên một compile hoặc toàn bộ source luôn xuất hiện trong lần gọi đầu tiên.

**Processor chuẩn không phải API biến đổi AST tùy ý.** JSR 269 chủ yếu cho đọc mô hình source, báo lỗi/cảnh báo, sinh thêm tệp. Các công cụ sửa AST trực tiếp dùng cơ chế khác, không thuộc hợp đồng công khai của `Processor`.

## 6. Demo Java 17 độc lập: processor tạo source rồi chương trình dùng class vừa sinh

Ví dụ dưới đây chỉ cần **JDK 17+**, không cần framework hay dependency ngoài. Sử dụng cấu trúc ban đầu:

~~~text
src/
  demo/
    GenerateGreeting.java
    GreetingProcessor.java
    Sample.java
~~~

Chương trình `Sample` sẽ tham chiếu `SampleGreeting`, một class do processor tạo **trong bước compile**, nên trước đó nó chưa có source.

### 6.1. Tệp `src/demo/GenerateGreeting.java`

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateGreeting {
}
~~~

`SOURCE` đủ dùng vì processor chạy khi biên dịch. Không cần runtime reflection để đọc annotation này.

### 6.2. Tệp `src/demo/GreetingProcessor.java`

~~~java
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
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateGreeting.class)) {

            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@GenerateGreeting requires a class",
                        element);
                continue;
            }

            String simpleName = element.getSimpleName().toString();
            String generatedName = simpleName + "Greeting";
            String qualifiedName = "demo." + generatedName;

            try {
                JavaFileObject file = processingEnv.getFiler()
                        .createSourceFile(qualifiedName, element);

                try (Writer writer = file.openWriter()) {
                    writer.write("package demo;\n");
                    writer.write("public final class " + generatedName + " {\n");
                    writer.write("    private " + generatedName + "() {}\n");
                    writer.write("    public static String message() {\n");
                    writer.write("        return \"Generated for " + simpleName + "\";\n");
                    writer.write("    }\n");
                    writer.write("}\n");
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Failed to generate " + qualifiedName
                                + ": " + ex.getMessage(),
                        element);
            }
        }

        return true;
    }
}
~~~

**Giải thích:**

1. `extends AbstractProcessor` dùng implementation nền của interface `Processor`; compiler tự gọi `init` và cung cấp `ProcessingEnvironment`.
2. `@SupportedAnnotationTypes` công bố annotation quan tâm; `@SupportedSourceVersion` công bố Java 17.
3. `RoundEnvironment.getElementsAnnotatedWith` tìm các khai báo có annotation.
4. `@Target(TYPE)` của annotation cho phép khai báo nhiều loại kiểu, nhưng processor **chủ động yêu cầu** `ElementKind.CLASS`. Đây là kiểm tra riêng ngoài target.
5. `Filer.createSourceFile` tạo `demo.SampleGreeting`. Ghi và đóng `Writer` để compiler xử lý source.
6. `Messager` báo lỗi nếu annotation sai loại element hoặc không thể sinh file.
7. `return true` claim annotation type; không mang nghĩa “không có lỗi”.

Ví dụ cố ý dùng package `demo` cố định để mã dễ theo dõi. Một processor tổng quát nên lấy package của element bằng `processingEnv.getElementUtils().getPackageOf(element)`, giải quyết tên trùng và tránh giả định mọi class đều trong package `demo`.

### 6.3. Tệp `src/demo/Sample.java`

~~~java
package demo;

@GenerateGreeting
public class Sample {
    public static void main(String[] args) {
        System.out.println(SampleGreeting.message());
    }
}
~~~

Khi compiler chạy với processor, nó sẽ tạo source `SampleGreeting.java` trước khi hoàn thành việc biên dịch chương trình này.

### 6.4. Lệnh biên dịch/chạy theo đúng thứ tự

Tại thư mục cha của `src`, trên PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/processor, build/classes, build/generated | Out-Null
~~~

**Bước 1 — biên dịch processor và annotation type:**

~~~bash
javac -encoding UTF-8 -d build/processor src/demo/GenerateGreeting.java src/demo/GreetingProcessor.java
~~~

**Bước 2 — biên dịch ứng dụng và kích hoạt processor tường minh:**

~~~bash
javac -encoding UTF-8 -cp build/processor -processorpath build/processor -processor demo.GreetingProcessor -s build/generated -d build/classes src/demo/Sample.java
~~~

Tùy chọn:

- `-cp build/processor`: để `javac` phân giải được `demo.GenerateGreeting` khi biên dịch `Sample`.
- `-processorpath build/processor`: để compiler nạp `GreetingProcessor`.
- `-processor demo.GreetingProcessor`: chỉ định processor bằng tên đầy đủ.
- `-s build/generated`: nơi đặt Java **source** sinh ra.
- `-d build/classes`: nơi đặt class files của ứng dụng.

Sau bước 2 có thể quan sát:

~~~text
build/generated/demo/SampleGreeting.java
build/classes/demo/Sample.class
build/classes/demo/SampleGreeting.class
~~~

Các đường dẫn trên là **kết quả dự kiến của build thành công**, không phải tệp có sẵn ngay sau khi chỉ viết ba source ban đầu.

**Bước 3 — chạy chương trình:**

~~~bash
java -cp build/classes demo.Sample
~~~

**Stdout chính xác:**

~~~text
Generated for Sample
~~~

Lệnh `java` chỉ chạy `Sample` và `SampleGreeting` đã biên dịch. Processor không cần chạy lại ở runtime. Các diagnostic của `javac`, nếu xuất hiện, thuộc **giai đoạn compile**, không phải stdout của chương trình.

### 6.5. Vai trò của các rounds trong ví dụ

1. Compiler nạp `demo.GreetingProcessor` từ processor path.
2. Processor được khởi tạo, nhận `ProcessingEnvironment`.
3. Trong round có khai báo `Sample`, `process` gặp `@GenerateGreeting`.
4. Processor tạo Java source `SampleGreeting.java` qua `Filer`.
5. Compiler xem xét source mới trong round tiếp theo và biên dịch class phát sinh.
6. Runtime gọi `SampleGreeting.message()` và in `Generated for Sample`.

Đây là cách **compiler plugin tạo mã ở build time**, không phải cơ chế method interception hay reflection runtime.

## 7. Cách đăng ký processor cho compiler

Ví dụ đã dùng `-processor demo.GreetingProcessor` nên không cần auto-discovery. Trong thư viện dùng lại, processor thường được đóng gói thành JAR với service provider metadata:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nội dung file:

~~~text
demo.GreetingProcessor
~~~

Khi compiler được cấu hình cho phép khám phá annotation processors từ processor path, có thể nạp implementation được khai báo trong service file. Với Java modules còn có cơ chế khai báo service thích hợp qua module descriptor; một vài toolchain/phiên bản JDK có chính sách discovery khác nhau. Để build ổn định, khai báo rõ **processor path và processor activation** theo tài liệu công cụ.

Cần phân biệt:

- `@SupportedAnnotationTypes`: cho biết **processor đã nạp** hỗ trợ annotation nào.
- Service registration hoặc `-processor`: cho biết **compiler cần nạp implementation nào**.
- `@Retention(SOURCE)`: cho biết **metadata có tồn tại sau compile không**, không phải cách đăng ký processor.

Processor JAR thường là dependency dùng **khi compile**; runtime của ứng dụng chỉ cần các class/tài nguyên đã sinh và những dependency runtime thực sự cần.

## 8. Phân biệt `ProcessingEnvironment` và `RoundEnvironment` qua mã

Một đoạn xử lý method minh họa (không phải chương trình độc lập):

~~~java
for (Element element : roundEnv.getElementsAnnotatedWith(MyMarker.class)) {
    if (element.getKind() == ElementKind.METHOD) {
        ExecutableElement method = (ExecutableElement) element;
        TypeMirror resultType = method.getReturnType();

        boolean returnsVoid = processingEnv.getTypeUtils()
                .isSameType(
                        resultType,
                        processingEnv.getTypeUtils()
                                .getNoType(TypeKind.VOID));

        if (returnsVoid) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.WARNING,
                    "Annotated method returns void",
                    method);
        }
    }
}
~~~

Đoạn này giả định processor đã khai báo `MyMarker`, có biến `roundEnv`, cùng imports `ExecutableElement`, `TypeMirror`, `TypeKind`, `ElementKind`, `Diagnostic`.

- `roundEnv` **cung cấp các elements của vòng hiện tại**.
- `ElementKind` giúp xác định phần tử là method.
- `ExecutableElement` cung cấp mô hình khai báo method.
- `TypeMirror` mô tả return type.
- `processingEnv.getTypeUtils()` hỗ trợ so sánh kiểu, còn `getMessager()` gửi compiler warning.

Không nên thay toàn bộ mô hình này bằng `Class.forName("demo.SomeClass")`. Source đang được compile có thể chưa có class file để nạp, và reflection runtime không đại diện đầy đủ cho source models ở thời điểm compiler hoạt động.

## 9. Quản lý vòng xử lý và source generation an toàn

### Không tạo lại cùng file

`Filer` có thể báo `FilerException` khi processor cố tạo lại cùng type/path trong cùng một annotation processing run. Processor thực tế phải quản lý tên sinh, loại phần tử và tình huống nhiều source requests dẫn đến cùng tên.

### Không kỳ vọng `getRootElements()` chứa mọi source của project

Mỗi round có tập root khác nhau. Source do processor tạo có thể trở thành root trong round sau; compiler không nhất thiết đưa toàn bộ classpath vào `getRootElements()` hay gọi lại đúng tập cũ.

### Không tạo source mới ở vòng cuối để mong compile round tiếp theo

`processingOver()` đánh dấu round cuối. Processor nên tạo file ở các vòng thích hợp trước đó; có thể phát diagnostic ở cuối nhưng đừng kỳ vọng compiler xử lý các source phát sinh muộn như một round bình thường.

### Không dùng `return false` làm công cụ báo lỗi

Nếu một element vi phạm ràng buộc, dùng `Messager.printMessage(ERROR, ..., element)`. Giá trị return từ `process` chủ yếu liên quan đến **claiming annotations**, không phải kiểm soát tình trạng thành công của toàn bộ compilation.

### Không tự sửa AST bằng API không thuộc hợp đồng

JSR 269 là chuẩn để **kiểm tra khai báo, truy vấn type models, phát diagnostics và sinh file**. Việc rewrite code hiện có, sửa AST compiler nội bộ hay tự động thay method body không được `Processor` hứa hẹn.

## 10. So sánh processor compile-time với reflection runtime

| Nội dung | Annotation Processing (JSR 269) | Reflection runtime |
| --- | --- | --- |
| Thời điểm | Build / compile `javac` | JVM đang chạy ứng dụng |
| API | `Processor`, `AbstractProcessor`, `ProcessingEnvironment`, `RoundEnvironment` | `Class`, `Method`, `Field`, `AnnotatedElement` |
| Phần tử/kiểu | `Element`, `TypeElement`, `TypeMirror` | `Class<?>`, đối tượng reflection |
| `@Retention` | `SOURCE` thường đủ | Thường cần `RUNTIME` |
| Kết quả thường gặp | Lỗi/cảnh báo compile-time, source/resource mới | Kiểm tra metadata, định tuyến, validation runtime |
| Công cụ ghi file | `Filer` | Không phải nhiệm vụ của reflection |
| Công cụ báo lỗi | `Messager` / compiler diagnostics | Exceptions/logging của ứng dụng |

Ví dụ `@GenerateGreeting` có `SOURCE` retention nhưng processor vẫn xử lý được vì nó chạy **trước khi source annotation bị loại khỏi class file**. Tại runtime, `Sample.class.getAnnotation(GenerateGreeting.class)` không trả annotation đó chỉ vì processor đã sinh thành công `SampleGreeting`.

## 11. Lỗi thường gặp

**Lỗi 1 — chỉ viết `@interface` và tưởng có processor.** Annotation là metadata; phải viết và kích hoạt implementation của `Processor`.

**Lỗi 2 — nhầm `@SupportedAnnotationTypes` với service registration.** Một cái khai báo annotation supported; cái còn lại khiến compiler nạp processor.

**Lỗi 3 — không biên dịch processor trước khi sử dụng `-processor`.** Processor class phải load được từ processor path.

**Lỗi 4 — nhầm `processingEnv` với `roundEnv`.** Cái đầu chứa services cho phiên compile; cái sau chứa dữ liệu mỗi round.

**Lỗi 5 — dùng reflection để truy vấn source chưa được biên dịch.** Dùng `Element`, `TypeElement`, `TypeMirror`, `Elements`, `Types` là phù hợp.

**Lỗi 6 — dùng `System.out.println` để báo compile error.** Nó không phải diagnostic compiler. Dùng `Messager`.

**Lỗi 7 — sinh file trùng tên trong nhiều rounds.** `Filer` có thể từ chối. Thiết kế tên file duy nhất và kiểm soát điều kiện tạo.

**Lỗi 8 — không đóng stream/writer tạo file.** Compiler có thể không thấy file source hoàn chỉnh; dùng try-with-resources.

**Lỗi 9 — coi `process() == true` nghĩa là compilation thành công.** Đó là claiming semantics; error diagnostics mới tác động tới kết quả biên dịch.

**Lỗi 10 — tưởng `@Retention(RUNTIME)` luôn cần thiết để processor đọc annotation.** Processor tại compile-time đọc được `SOURCE` annotation.

**Lỗi 11 — tưởng `AbstractProcessor` tự sinh code.** Nó chỉ cung cấp phần triển khai mặc định; logic thực tế nằm trong `process`.

**Lỗi 12 — lẫn processor path với application runtime classpath.** Tách dependency compile-time và runtime cho đúng mục đích.

## 12. Bài tập và câu hỏi ôn tập

**Câu 1.** `Processor`, `AbstractProcessor` và `ProcessingEnvironment` khác nhau thế nào?

**Đáp án:** `Processor` là interface hợp đồng; `AbstractProcessor` là lớp nền triển khai sẵn một phần; `ProcessingEnvironment` là ngữ cảnh compiler cấp khi khởi tạo.

**Câu 2.** Nếu `process` trả `false`, compiler có nhất thiết dừng do lỗi không?

**Đáp án:** Không. `false` nghĩa là chưa claim annotation types của round; muốn báo lỗi sử dụng `Messager` với `Diagnostic.Kind.ERROR`.

**Câu 3.** Vì sao `@Retention(SOURCE)` là đủ cho `@GenerateGreeting` trong ví dụ?

**Đáp án:** Processor chỉ cần nhìn metadata trong quá trình compile, còn ứng dụng chạy file đã sinh, không cần truy cập annotation gốc tại runtime.

**Câu 4.** Tại sao phải biên dịch `GreetingProcessor.java` trước `Sample.java`?

**Đáp án:** `javac -processor demo.GreetingProcessor` cần nạp một processor đã có class file. Processor sau đó mới sinh `SampleGreeting.java` để `Sample` tham chiếu được.

**Câu 5.** `Filer` và `Messager` khác nhau ở đâu?

**Đáp án:** `Filer` tạo source/class/resource; `Messager` phát compiler diagnostics.

**Câu 6.** Vì sao `getRootElements()` không nên được dùng như danh sách mọi class trong toàn bộ dự án?

**Đáp án:** Nó chỉ mô tả root elements thuộc một processing round; round sau có thể chứa những source mới được tạo.

**Bài thực hành:** Sau khi chạy ví dụ, viết thêm `src/demo/Report.java` với `@GenerateGreeting`, rồi đưa cả `Sample.java` và `Report.java` vào lệnh `javac` ở bước 2. Quan sát `SampleGreeting.java` và `ReportGreeting.java` xuất hiện. Tiếp theo gắn `@GenerateGreeting` lên một interface và xem diagnostic `@GenerateGreeting requires a class` do processor phát ra. Cuối cùng, thử bỏ `-processor demo.GreetingProcessor` trong một **build sạch không có service registration** và giải thích vì sao `SampleGreeting` không được tạo.

## 13. Tài liệu API Java SE 17

- [`Processor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html): vòng đời, hỗ trợ annotation, claiming và options.
- [`AbstractProcessor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): lớp nền và `processingEnv`.
- [`ProcessingEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html): `Filer`, `Messager`, `Elements`, `Types`, options.
- [`RoundEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): root elements, trạng thái processing round và truy vấn annotation.
- [`Filer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html): sinh source/class/resource đúng chuẩn.
- [`Messager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Messager.html): compiler diagnostics.

**Ghi nhớ:** `Processor` đặt ra hợp đồng, `AbstractProcessor` giúp triển khai, `ProcessingEnvironment` cấp dịch vụ và `RoundEnvironment` mang dữ liệu từng vòng. Nắm rõ vai trò ấy sẽ giúp bạn viết processor để kiểm tra và sinh mã đúng thời điểm biên dịch, mà không nhầm sang cơ chế runtime.