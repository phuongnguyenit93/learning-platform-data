# Giới hạn của API chuẩn: sinh tệp so với sửa cây cú pháp bằng công cụ riêng

## 1. Annotation processor có thể làm gì và không thể làm gì?

Khi đặt annotation lên một class Java, nhiều người mong compiler tự thêm field, getter, constructor hay chỉnh sửa method của chính class đó. Cần phân biệt **hai nhóm khả năng hoàn toàn khác nhau**:

1. **Annotation processing chuẩn (JSR 269):** phân tích cấu trúc khai báo, kiểm tra quy tắc, báo lỗi/cảnh báo và **sinh tệp mới** (Java source, class file hoặc tài nguyên) thông qua `Filer`.
2. **Biến đổi cây cú pháp/compiler AST:** can thiệp vào cấu trúc của một compilation unit đã tồn tại, chẳng hạn **chèn method mới vào class đang compile**. JSR 269 và `Filer` **không cung cấp API chuẩn, được bảo đảm để làm việc này**; cần cơ chế chuyên dụng, công cụ rewrite hoặc các API/compiler internals khác.

Ví dụ:

~~~java
@GenerateGreeting
class Client {}
~~~

Một processor chuẩn có thể **tạo thêm** class `ClientGreeting`:

~~~java
final class ClientGreeting {
    static String text() {
        return "Hello, Client!";
    }
}
~~~

Nhưng chỉ với `Filer`, nó không thể bổ sung trực tiếp method `text()` vào **`Client`**, rồi khiến `new Client().text()` trở thành lời gọi hợp lệ trên chính class nguồn. Đó là khác biệt giữa **sinh một đơn vị biên dịch mới** và **sửa một đơn vị biên dịch đã có**.

### Sơ đồ luồng biên dịch

~~~text
Source files ban đầu: Client.java, Main.java, annotation type
         |
         v
javac phân tích source / type / symbol
         |
         +--> javax.lang.model (Element, TypeMirror, AnnotationMirror)
         |         đọc khai báo và annotation
         |
         +--> Processor / RoundEnvironment
         |       +-- Messager: báo lỗi / cảnh báo / ghi chú
         |       +-- Filer: sinh FILE MỚI
         |               ClientGreeting.java
         |
         +--> Round tiếp theo có thể xử lý source mới
         |
         v
Biên dịch .class để chạy / đóng gói
         
Muốn sửa trực tiếp AST của Client:
  cần cơ chế compiler-specific hoặc source rewriter riêng,
  KHÔNG phải thao tác chuẩn của Filer.
~~~

Annotation processor chạy **khi biên dịch**, không phải lúc ứng dụng đang chạy. Annotation có retention `SOURCE` vẫn hoàn toàn hữu dụng để kích hoạt processor.

## 2. Những API chuẩn của annotation processing

JSR 269 được cung cấp trong module `java.compiler` của JDK. Các thành phần tiêu biểu:

| Thành phần | Trách nhiệm chính | Không bảo đảm |
|---|---|---|
| `Processor` / `AbstractProcessor` | Nhận các vòng xử lý và annotation được hỗ trợ | Thêm method vào class nguồn |
| `RoundEnvironment` | Tìm elements trong một vòng, kiểm tra `processingOver()` | Sửa trực tiếp AST |
| `Element`, `TypeElement`, `ExecutableElement` | Mô tả class/method/field/parameter | Setter chuẩn để biến đổi khai báo |
| `TypeMirror`, `Types` | Phân tích và so sánh kiểu | Rewrite cú pháp |
| `AnnotationMirror`, `AnnotationValue` | Đọc metadata trong compiler, kể cả annotation `SOURCE` | Chạy hành vi nghiệp vụ của annotation |
| `Elements`, `ElementFilter` | Tra cứu type, lọc field/method và các cấu trúc | Đổi bytecode của class hiện có |
| `Messager` | Báo `ERROR`, `WARNING`, `NOTE` ở vị trí khai báo | Tạo hoặc cập nhật file |
| `Filer` | Sinh source/class/resource **mới** trong output được tool quản lý | Vào một class nguồn và thay cây cú pháp |

Một processor có thể được định nghĩa bằng:

~~~java
@SupportedAnnotationTypes("demo.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class GreetingProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {
        // Đọc declarations, báo diagnostics, sinh file.
        return true;
    }
}
~~~

Đây chỉ là **khung minh họa**, chưa có imports hoặc body đầy đủ. Mục 5 sẽ có phiên bản hoàn chỉnh, biên dịch và chạy được trên Java 17+.

## 3. `Filer` sinh những loại tệp nào?

Processor lấy `Filer` từ môi trường compile:

~~~java
Filer filer = processingEnv.getFiler();
~~~

Các API chính:

| Phương thức | Ý nghĩa |
|---|---|
| `createSourceFile("demo.Generated", origins...)` | Tạo **Java source mới**, trả `JavaFileObject` để ghi nội dung |
| `createClassFile("demo.Generated", origins...)` | Tạo **class file mới**, processor tự ghi bytecode hợp lệ |
| `createResource(location, moduleAndPkg, relativeName, origins...)` | Tạo tài nguyên mới, ví dụ registry, service descriptor hoặc metadata |
| `getResource(location, moduleAndPkg, relativeName)` | Truy cập tài nguyên đã có để đọc |

**`createSourceFile` không tự viết getter:** nó chỉ tạo một file đích mới. Processor cần ghi **toàn bộ source code** của type mới vào `Writer`.

~~~java
JavaFileObject output = processingEnv.getFiler()
        .createSourceFile("demo.ClientGreeting", sourceElement);
try (Writer writer = output.openWriter()) {
    writer.write("package demo;\n"
            + "public final class ClientGreeting {}\n");
}
~~~

Đây là **snippet API trong processor**, không phải file Java độc lập: nó đòi hỏi `processingEnv`, `sourceElement` và các imports/exception handling.

Các điểm bắt buộc hiểu:

- Tên `demo.ClientGreeting` được compiler/tool ánh xạ thành đường dẫn source output như `generated/demo/ClientGreeting.java`. Không truyền đường dẫn tùy ý tới tệp source người dùng để “sửa”.
- `originatingElements` chỉ ra các khai báo nguồn tạo ra output; đây là gợi ý hữu ích cho build tool về dependency/incremental processing, không bảo đảm build incremental tự đúng trong mọi môi trường.
- **Phải đóng** `Writer` hoặc `OutputStream`. Source và class file được tạo qua Filer mới được tool nhận diện để xử lý trong vòng tiếp theo sau khi stream đóng.
- `createClassFile` đòi **bytecode class thật**, không phải chuỗi mã nguồn Java rồi đổi đuôi `.class`.
- `createResource` tạo tài nguyên. **Resource không tự được đăng ký thành source/class input của round kế tiếp**, ngay cả nếu bạn đặt một tên tài nguyên trông giống file Java.

### Một sắc thái quan trọng về output đã tồn tại

“Filer tạo file mới” nghĩa là tạo theo **mô hình output do compilation tool quản lý**, không phải khẳng định pathname trên đĩa chưa từng tồn tại. Trong **một invocation**:

- Một pathname chỉ được tạo **một lần**; tạo lần hai sẽ gây `FilerException`.
- Input files ban đầu được coi như đã xuất hiện ở vòng đầu, nên không thể tạo source/class tương ứng với chúng để sửa chúng.
- Nếu pathname của một generated output **từ invocation trước** đã tồn tại trên đĩa, tool có thể ghi lại output đó vào lần build mới theo hợp đồng của Filer.
- Processor **không được cố ý overwrite file không phải generated artifact**, đặc biệt không được coi Filer như quyền sửa tùy ý tệp người dùng.

Đây là lý do `Filer` **không thể thay thế một source editor**. Bạn cũng không nên làm việc đó bằng cách viết trực tiếp vào `src/main/java` từ processor.

## 4. Vòng xử lý annotation (*processing rounds*)

Annotation processing thường có **nhiều vòng**, không phải một method `process()` chạy duy nhất một lần:

~~~text
Round 1: compiler thấy @GenerateGreeting trên Client
         -> processor sinh ClientGreeting.java, đóng Writer
Round 2: compiler tiếp nhận/generated source mới
         -> nếu có annotation khác, processor tương ứng có thể chạy
Final round:
         -> round.processingOver() == true
         -> không có round xử lý tiếp theo cho output mới
~~~

Sơ đồ là trường hợp điển hình, không phải lịch trình chính xác cho mọi compiler implementation.

`RoundEnvironment` cung cấp:

- `getElementsAnnotatedWith(TypeElement)`: các elements mang annotation cụ thể ở vòng hiện tại.
- `getRootElements()`: các root elements được compiler cung cấp ở vòng đó.
- `processingOver()`: báo vòng xử lý kết thúc.

Vì processor có thể được gọi nhiều lần, **tránh tạo lại cùng một class source ở các vòng khác nhau**. Hợp đồng Filer coi việc tạo lại cùng pathname trong một invocation là lỗi.

Tùy mục tiêu, processor có thể trả `true` để claim annotation types được hỗ trợ hoặc `false` để processor khác cũng xem xét. Giá trị trả về **không quyết định việc sửa AST**.

## 5. Thực hành Java 17+: tạo `ClientGreeting` từ annotation

Bài thực hành có **bốn tệp nguồn**. Chúng ta dùng processor mặc định package (*default package*) để lệnh CLI ngắn, còn các lớp nghiệp vụ đặt trong package `demo`.

Ban đầu:

~~~text
project/
├── GreetingProcessor.java
└── src/
    └── demo/
        ├── GenerateGreeting.java
        ├── Client.java
        └── Main.java
~~~

### 5.1. `GreetingProcessor.java`

~~~java
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
public class GreetingProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {
        if (round.processingOver()) return true;

        TypeElement marker = processingEnv.getElementUtils()
                .getTypeElement("demo.GenerateGreeting");
        if (marker == null) return false;

        for (Element element : round.getElementsAnnotatedWith(marker)) {
            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Only classes are supported",
                        element);
                continue;
            }

            String simple = element.getSimpleName().toString();
            String generated = simple + "Greeting";
            try {
                JavaFileObject source = processingEnv.getFiler()
                        .createSourceFile("demo." + generated, element);
                try (Writer writer = source.openWriter()) {
                    writer.write("package demo;\n"
                            + "public final class " + generated + " {\n"
                            + "  private " + generated + "() {}\n"
                            + "  public static String text() {\n"
                            + "    return \"Hello, " + simple + "!\";\n"
                            + "  }\n"
                            + "}\n");
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, ex.getMessage(), element);
            }
        }
        return true;
    }
}
~~~

Giải thích:

1. `@SupportedAnnotationTypes("demo.GenerateGreeting")` chỉ rõ annotation processor xử lý.
2. `getTypeElement(...)` lấy symbol của annotation type qua compiler model.
3. `round.getElementsAnnotatedWith(marker)` tìm các declaration được annotate.
4. `ElementKind.CLASS` giới hạn demo cho class; dù annotation `@Target(TYPE)` cũng có thể gắn vào type khác, demo cố ý từ chối.
5. `element.getSimpleName()` của `Client` là `Client`; generated name là `ClientGreeting`.
6. `createSourceFile("demo.ClientGreeting", element)` **tạo class mới**, không thay `Client`.
7. `try-with-resources` đóng writer để tool có thể xử lý source.
8. Lỗi `IOException`/`FilerException` được báo qua `Messager` để build nhận thông tin.

**Giới hạn cố ý:** demo hard-code package `demo` và được thiết kế cho các class top-level đơn giản. Processor sản xuất cần xử lý package bằng `Elements.getPackageOf`, nested types, trùng tên, module, validation, escaping và nhiều compiler configurations.

### 5.2. `src/demo/GenerateGreeting.java`

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateGreeting {}
~~~

`SOURCE` là đủ cho annotation processor vì nó quan sát metadata **khi đang compile**. Không cần `RUNTIME` chỉ để sinh mã.

### 5.3. `src/demo/Client.java`

~~~java
package demo;

@GenerateGreeting
public class Client {}
~~~

Class `Client` không có method `text()` và processor không sửa `Client.java`. Đặt annotation không biến `new Client().text()` thành lời gọi hợp lệ.

### 5.4. `src/demo/Main.java`

~~~java
package demo;

public class Main {
    public static void main(String[] args) {
        System.out.println(ClientGreeting.text());
    }
}
~~~

`Main` gọi class **được tạo riêng**. Compiler tiếp nhận output qua vòng xử lý và có thể giải quyết tên `ClientGreeting` khi biên dịch ứng dụng.

### 5.5. Lệnh chạy

Tại thư mục `project`, trên Bash:

~~~bash
mkdir -p processor-classes generated classes

javac --release 17 -d processor-classes GreetingProcessor.java

javac --release 17 \
  -cp processor-classes \
  -processorpath processor-classes \
  -processor GreetingProcessor \
  -s generated \
  -d classes \
  src/demo/GenerateGreeting.java \
  src/demo/Client.java \
  src/demo/Main.java

java -cp classes demo.Main
~~~

Trong PowerShell/CMD, dùng lệnh `javac` thứ hai trên **một dòng** hoặc nối dòng theo cú pháp shell đó; ký tự `\` ở cuối dòng phía trên dành cho Bash.

**Stdout đã kiểm chứng:**

~~~text
Hello, Client!
~~~

Tệp được sinh:

~~~text
generated/demo/ClientGreeting.java
~~~

Nội dung generated source:

~~~java
package demo;
public final class ClientGreeting {
  private ClientGreeting() {}
  public static String text() {
    return "Hello, Client!";
  }
}
~~~

Có thể kiểm tra thêm `classes/demo/ClientGreeting.class` sau compilation. Bài này đã được chạy thành công với `javac --release 17`, processor sinh đúng file và `java -cp classes demo.Main` in đúng dòng trên.

**Lưu ý `-proc:only`:** Nếu thêm `-proc:only` vào `javac`, compiler chỉ chạy annotation processors và không hoàn tất bước sinh class thường cho ứng dụng; không thể giả định sau đó `java demo.Main` chạy ngay mà không có compilation khác.

## 6. `FilerException` không phải tín hiệu “cần ghi đè class cũ”

Trong cùng một invocation, đoạn này **cố ý sai**:

~~~java
filer.createSourceFile("demo.ClientGreeting", sourceElement);
// Processor tạo cùng tên thêm lần nữa trong invocation:
filer.createSourceFile("demo.ClientGreeting", sourceElement);
~~~

Lần thứ hai vi phạm hợp đồng và có thể ném `FilerException`. Tương tự, cố tạo `demo.Client` khi `demo.Client` đã là source input không được dùng để “bơm method” vào class hiện tại.

Nguyên nhân khác:

- Hai processor cùng muốn tạo một fully qualified name.
- Một processor tạo source file và class file ứng với cùng một type.
- Generated name không hợp lệ hoặc không thể chọn output module.
- Resource pathname bị tạo lại trong một invocation.

Giải pháp là **thiết kế generated names ổn định, không xung đột** và tạo mỗi file một lần; không retry đè file hoặc âm thầm bỏ qua lỗi.

### Sinh resource riêng

Snippet trong processor:

~~~java
import javax.tools.FileObject;
import javax.tools.StandardLocation;
import java.io.Writer;

FileObject file = processingEnv.getFiler().createResource(
        StandardLocation.CLASS_OUTPUT,
        "",
        "META-INF/example/registry.txt",
        sourceElement);
try (Writer writer = file.openWriter()) {
    writer.write("demo.Client\n");
}
~~~

Đoạn trên không phải standalone program (cần môi trường `processingEnv` và xử lý exception). Resource output có đường dẫn tương đối do tool quản lý. Nếu nhiều element muốn đóng góp nội dung vào **cùng registry**, hãy thu thập dữ liệu rồi ghi file **một lần**, không mở đi mở lại cùng pathname.

### Sinh class file trực tiếp

`createClassFile("demo.Generated", ...)` đòi processor ghi **dữ liệu `.class` đúng định dạng JVM**; không thể ghi Java source text vào file này. Khi chưa cần kỹ thuật bytecode riêng, `createSourceFile` là lựa chọn dễ kiểm thử và cho phép javac kiểm tra cú pháp, generic types cùng các quy tắc ngôn ngữ.

## 7. `Element` không phải cây cú pháp có setter

Một processor có thể đọc:

~~~java
for (Element e : round.getElementsAnnotatedWith(marker)) {
    System.out.println(e.getKind());
    System.out.println(e.getSimpleName());
    System.out.println(e.getEnclosedElements());
}
~~~

Nhưng JSR 269 không cung cấp các method như:

~~~java
// PSEUDOCODE CỐ Ý KHÔNG PHẢI JAVA API:
e.addMethod("getId", ...);
e.removeField("password");
e.replaceMethodBody(...);
~~~

`Element` là mô hình **khai báo**, còn `TypeMirror` mô tả **kiểu Java**. `getEnclosedElements()` cung cấp danh sách các khai báo, không phải một danh sách để bạn chèn method rồi compiler tự đồng bộ tất cả symbol tables, type attribution và bytecode.

Một processor có thể **tạo class mới tương tác với class cũ**, nhưng không vì thế mà class cũ được sửa.

## 8. Compiler Tree API: đọc AST khác với sửa AST

JDK cung cấp Compiler Tree API thuộc module `jdk.compiler`:

- `com.sun.source.tree.Tree` cùng `ClassTree`, `MethodTree`, `VariableTree`, `AnnotationTree`...
- `com.sun.source.util.Trees` để liên hệ `Element` với cây nguồn khi có.
- `TreePath`, `TreePathScanner`, `TreeScanner` để duyệt cây.
- `SourcePositions` để tìm vị trí cú pháp trong compilation unit.

Ví dụ **đọc** cây trong processor chạy bằng javac:

~~~java
import com.sun.source.tree.Tree;
import com.sun.source.util.Trees;

// Trong AbstractProcessor, với Element element hợp lệ:
Trees trees = Trees.instance(processingEnv);
Tree tree = trees.getTree(element);
if (tree != null) {
    System.out.println(tree.getKind());
}
~~~

Snippet cần đặt trong processor phù hợp, không tự biên dịch độc lập. Với phần tử không có source tree phù hợp, `getTree(...)` có thể trả `null`; tùy compiler/tool có hỗ trợ `Trees` hay không.

**Ranh giới cần nhớ:** Compiler Tree API công khai cung cấp các interface phục vụ **truy vấn và duyệt AST**, nhưng không có một cơ chế AST rewrite tổng quát được cam kết như `addMethod(ClassTree, ...)`. Việc truy cập được cây nguồn không trao quyền sửa node bằng một setter chuẩn khiến javac tiếp nhận sự thay đổi.

## 9. Compiler-specific tools, plugin và can thiệp AST nội bộ

Một số thư viện/công cụ có thể bổ sung code như thể nó nằm trong class đã viết. Nhưng cần phân biệt các con đường:

| Cách làm | Tác dụng | Đánh đổi |
|---|---|---|
| **JSR 269 + Filer** | Sinh source/class/resource **mới** | Không trực tiếp mutate class đã có |
| **Javac plugin qua `com.sun.source.util.Plugin`** | Tích hợp compiler, đăng ký `TaskListener` và quan sát các phase | Public plugin API không có sẵn AST editor tổng quát |
| **Javac internals** | Can thiệp các đối tượng như `com.sun.tools.javac.tree.JCTree`, `TreeMaker`, symbols | Phụ thuộc compiler implementation, JDK version, module access, IDE |
| **Source-to-source rewriting** | Dùng parser/refactoring engine tạo phiên bản source mới trước khi compile | Cần quản lý source ownership, formatting, imports và quá trình đồng bộ |
| **Bytecode transformation** | Sửa/tạo mã `.class` ở pipeline khác | Không làm source Java tự có method tại compile-time; phải đồng bộ classpath |
| **Runtime proxy/instrumentation** | Tạo wrapper/proxy hoặc thay đổi hành vi lúc chạy | Không đồng nghĩa sửa declaration trong source |

Ví dụ những annotation hỗ trợ getter như Lombok có thể dựa vào compiler-specific integration. **Đừng suy từ kết quả có getter đến kết luận rằng `Filer` có API thêm method vào class nguồn.**

Tương tự, thư viện sinh source có cấu trúc (ví dụ JavaPoet) làm **công việc viết source mới** dễ hơn, nhưng cuối cùng vẫn cần lưu nó như generated source; riêng thư viện đó không biến JSR 269 thành cơ chế sửa AST.

### Khi nào thực sự cần công cụ không chuẩn?

Nếu requirement là **`new Client().getName()` phải biên dịch được dù class nguồn không khai báo getter**, generated companion đơn thuần không đáp ứng. Cần đổi contract ứng dụng hoặc triển khai compiler-specific source/AST transformation, với câu hỏi kỹ thuật cụ thể:

- Có cần hỗ trợ cả javac, Eclipse compiler, IDE index và annotation processing trong CI không?
- Có dựa vào internal API bị encapsulate trong module `jdk.compiler` không?
- Compiler phase nào xử lý transformation? Symbol/type attribution sẽ được cập nhật như thế nào?
- Các version JDK mới có thay internal tree classes hoặc thứ tự compiler phase không?
- Có đủ regression tests cho compile, IDE, runtime, incremental build không?

Không thể cho rằng một tổ hợp tùy ý của `--add-exports` hoặc `--add-opens` sẽ giải quyết mọi rủi ro; các thiết lập module và compiler internals có thể khác nhau theo công cụ.

## 10. Những thiết kế thay thế tránh sửa class nguồn

### Sinh companion/helper

~~~java
@GenerateGreeting
class Client {}
// Sinh ra class ClientGreeting ở file mới.
~~~

Caller dùng `ClientGreeting.text()` hoặc các helper phù hợp. Đây là cách được ví dụ ở mục 5 chứng minh.

### Sinh adapter hoặc implementation

Với một interface đã có:

~~~java
interface Mapper<T> {
    String encode(T value);
}

class Client {
    String id;
}
~~~

Processor có thể sinh `ClientMapper implements Mapper<Client>`. Thực tế này thường đủ cho serializer, mapper, RPC client hoặc dependency injection binding.

### Sinh factory/builder riêng

Processor tạo `ClientFactory` hoặc `ClientBuilder` dựa vào constructor/setter/accessibility đã tồn tại. Nó **không tạo thêm constructor bên trong Client**: factory trả instance theo các API hợp lệ đã có.

### Sinh subclass

Nếu type nguồn có thể được kế thừa (không `final`), có constructor/visibility phù hợp, generator có thể tạo subclass với method mới. Tuy nhiên, **static type của superclass không tự có method của subclass**; subclass không thể override final/private method và không thể sửa những ràng buộc inheritance của Java.

### Sinh mã ở output directory riêng

Generated sources nên nằm trong output build riêng (`generated/`, `build/generated/...` hoặc tương tự), được IDE/build system nhận diện. Tránh trộn tệp do processor sở hữu với source do developer chỉnh sửa; điều này hỗ trợ clean builds, tránh merge conflicts và giúp truy dấu lỗi.

## 11. Kiểm thử, cảnh báo và incremental build

### Kiểm thử processor tối thiểu

Một bài test đáng tin cần chứng minh:

1. Compiler nhận đúng annotation type và processor.
2. Generated file xuất hiện ở output path đúng.
3. Nội dung generated source hợp lệ theo Java source version.
4. Generated class có thể được compiler tiếp nhận và tham chiếu từ code khác.
5. Khi annotation sai vị trí, processor phát diagnostic rõ ràng.
6. Khi nhiều inputs, generated type names không trùng nhau.
7. Vòng cuối không tạo vô hạn tệp.
8. Incremental/clean build không để output cũ gây kết quả giả.

Lệnh `-processor GreetingProcessor` trong ví dụ **chủ động bật processor**; do đó không cần phụ thuộc vào cơ chế service discovery mặc định của toolchain. Trong dự án lớn, processor thường được đóng gói JAR và có cấu hình tương ứng trong Maven/Gradle/IDE.

### Dùng `Messager` để báo lỗi

~~~java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Only classes are supported",
        element);
~~~

Processor nên kiểm tra type, tên, visibility và các điều kiện cần thiết **trước khi tạo file**, thay vì cố sửa code nguồn của người dùng. Diagnostic rõ ràng giúp lỗi build có vị trí và cách khắc phục.

### Vấn đề về incremental build

`originatingElements` giúp môi trường build suy luận sự phụ thuộc từ generated output về input. Nhưng hiệu quả incremental còn tùy quy ước processor, tool và loại output (isolating/aggregating). Đừng khẳng định mọi processor có `originatingElements` sẽ luôn incremental-safe.

Khi generator tạo **một registry chung** từ nhiều class, nó khác bài toán **mỗi input sinh một class riêng**. Phải tổng hợp dữ liệu, chỉ tạo output một lần trong invocation và xác định dependency semantics phù hợp.

### Bảo mật và tin cậy toolchain

Annotation processor là code **thực thi trong giai đoạn build**, có thể chạy logic bên ngoài việc đọc annotation đơn giản. Chỉ bật processor đáng tin cậy và giới hạn dependency/processor path trong pipeline. Không đánh đồng việc “source chỉ có annotation” với việc processor không có side effects.

## 12. Sai lầm thường gặp

**“Có `@Retention(RUNTIME)` thì processor mới thấy annotation.”** Sai. Processor làm việc tại thời điểm biên dịch; retention `SOURCE` thường đủ. `RUNTIME` chỉ cần nếu ứng dụng còn phải tra metadata bằng reflection lúc chạy.

**“`Filer.createSourceFile` có thể ghi đè `Client.java` rồi chèn getter.”** Sai về hợp đồng. Input ban đầu không thể được tạo lại qua Filer như một type mới trong cùng invocation; công cụ không có API chuẩn sửa AST input.

**“`Element.getEnclosedElements()` trả danh sách mutable nên chỉ cần thêm `ExecutableElement`.”** Không có bảo đảm như vậy; symbol/type compiler không được tái cấu trúc qua mutation tùy ý của một collection.

**“Có `Trees.getTree(...)` là có AST editor chính thức.”** Sai. Public Compiler Tree API chủ yếu để quan sát/duyệt; mutation của internal compiler nodes là vấn đề khác.

**“Processor chỉ chạy một lần.”** Sai. Có nhiều rounds. Mỗi generated pathname chỉ tạo một lần trong invocation; phải phòng ngừa `FilerException`.

**“`createClassFile` nhận source Java text.”** Sai. API đó ghi tệp class binary; muốn để javac biên dịch source mới, dùng `createSourceFile`.

**“Plugin javac chính thức đồng nghĩa có public method thêm field vào AST.”** Sai. Plugin API có cơ chế init/task events; chỉnh sửa nội bộ cần công cụ/cách tiếp cận riêng và có rủi ro compatibility.

**“Runtime proxy làm IDE nhìn thấy getter không tồn tại trong source.”** Không tự động. Compile-time symbol model và runtime dynamic proxy là hai vấn đề khác nhau.

## 13. Checklist trước khi chọn công nghệ

- [ ] Yêu cầu là **sinh type/resource mới** hay **đổi declaration đang có**?
- [ ] Có thể thiết kế generated companion, adapter, mapper, factory hoặc builder thay vì mutate AST không?
- [ ] Nếu dùng JSR 269, processor có xác định đúng `@SupportedAnnotationTypes` và `ElementKind` không?
- [ ] `Filer` đã tạo tên output hợp lệ/duy nhất, truyền `originatingElements` và đóng writer chưa?
- [ ] Có xử lý nhiều rounds, `processingOver()` và các tình huống `FilerException` chưa?
- [ ] Generated source nằm trong output directory, được javac và IDE công nhận chưa?
- [ ] Có phân biệt `-s`, `-d`, `-processorpath` và `-proc:only` không?
- [ ] Nếu dùng `Trees`, chỉ đọc/duyệt hay thật sự cần sửa AST?
- [ ] Nếu cần compiler-specific internals, đã đánh giá rõ version JDK, compiler plugin, module access, IDE và regression tests chưa?
- [ ] Có build/test theo Java version mục tiêu và so khớp generated source/runtime output không?

## 14. Tài liệu chính thức

- [Java SE 17 — `Filer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html): hợp đồng sinh source/class/resource, originating elements, round và file trùng.
- [Java SE 17 — `FilerException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/FilerException.html): lý do tool từ chối tạo file.
- [Java SE 17 — `Processor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html): processor và các processing rounds.
- [Java SE 17 — `RoundEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): root elements, annotation lookup và vòng cuối.
- [Java SE 17 — `ProcessingEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html): `getFiler()`, `getMessager()`, `getElementUtils()`.
- [Java SE 17 — `Trees`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/Trees.html): ánh xạ symbol với cây nguồn.
- [Java SE 17 — `com.sun.source.tree`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/tree/package-summary.html): các interface của source AST.
- [Java SE 17 — `javac Plugin`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/Plugin.html): khả năng tích hợp plugin javac.

**Ghi nhớ:** API annotation processing chuẩn **đọc và kiểm tra khai báo, báo diagnostic, sinh file mới**. `Filer` không chỉnh sửa trực tiếp class/AST đã có. Nếu bài toán cần thêm method vào đúng class gốc mà source không chứa method đó, phải thay thiết kế API hoặc chủ động chọn một công cụ biến đổi source/compiler/bytecode ngoài JSR 269 với mức độ rủi ro và khả năng tương thích riêng.