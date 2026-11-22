# Annotation processing là gì và khi nào nên sinh mã?

## 1. Khái niệm: annotation không tự thực hiện công việc

Annotation trong Java là **metadata gắn với khai báo hoặc vị trí sử dụng kiểu**, ví dụ `@Override`, `@Deprecated`, `@Entity`, `@Builder` hoặc annotation do dự án tự định nghĩa. Bản thân việc viết một annotation **không tự động tạo method, sửa class hay thực thi nghiệp vụ**. Một cơ chế khác phải **đọc** annotation rồi quyết định làm gì.

**Annotation processing** là cơ chế xử lý annotation trong lúc biên dịch bằng API chuẩn **JSR 269** (Java Annotation Processing API) thuộc module `java.compiler`, chủ yếu trong các package:

- `javax.annotation.processing`: `Processor`, `AbstractProcessor`, `ProcessingEnvironment`, `RoundEnvironment`, `Filer`, `Messager`.
- `javax.lang.model` và các package con: mô hình phần tử/chữ ký của chương trình, ví dụ `Element`, `TypeElement`, `ExecutableElement`, `TypeMirror`, `Elements`, `Types`.
- `javax.tools`: các đối tượng file do compiler quản lý như `JavaFileObject`, cùng loại thông báo `Diagnostic.Kind`.

Khi `javac` được cấu hình để chạy annotation processors, compiler đọc các source files, tạo mô hình phần tử và cho processor quan sát các annotation tương ứng. Processor có thể:

1. **Kiểm tra quy tắc ở compile time**, phát lỗi/cảnh báo hữu ích (ví dụ phát hiện cấu hình không hợp lệ).
2. **Sinh Java source**, class file hoặc tài nguyên phụ trợ mà build cần.
3. **Sinh metadata** cho một hệ thống khác đọc, chẳng hạn danh mục các loại được đăng ký.
4. **Không làm gì** nếu annotation không thuộc loại mà processor hỗ trợ hoặc không có đầu vào cần xử lý.

Ví dụ: dự án có `@AutoGreeting` trên `OrderService`; processor có thể sinh lớp `OrderServiceGreeting` chứa API tĩnh. Class mới được biên dịch cùng lượt để code người dùng gọi trực tiếp nó.

**Phân biệt quan trọng:** annotation processing kiểu JSR 269 chạy ở **compile time**, khác với việc ứng dụng dùng reflection lúc chạy để đọc annotation có `RetentionPolicy.RUNTIME`. Nó cũng khác bytecode instrumentation, compiler plugin can thiệp AST nội bộ hoặc runtime proxy. Standard API `Filer` dùng để **tạo file mới**, không phải hợp đồng để sửa AST của class đang biên dịch.

## 2. Annotation được nhìn thấy ở đâu?

Annotation Java khai báo qua `@interface` và thường có hai meta-annotations quan trọng:

- `@Target`: annotation có thể gắn vào đâu (`TYPE`, `METHOD`, `FIELD`, `PARAMETER`, `RECORD_COMPONENT`, ...).
- `@Retention`: annotation tồn tại đến giai đoạn nào.

| Retention | Ý nghĩa | Annotation processor có dùng được? |
| --- | --- | --- |
| `SOURCE` | Annotation thuộc nguồn; thường không ghi vào class file sau khi biên dịch | **Có**, khi processor được chạy trên source chứa annotation |
| `CLASS` | Thông tin có thể được ghi vào class file; không bắt buộc có trong runtime reflection | **Có**, khi mô hình đầu vào cung cấp annotation đó |
| `RUNTIME` | Có thể được runtime reflection truy cập | **Có** ở compile time, và code runtime có thể đọc khi cần |

**Không cần đặt `RUNTIME` chỉ để processor nhìn thấy annotation**. Ví dụ marker phục vụ duy nhất cho code generation thường chọn `SOURCE` để tránh mang metadata không cần thiết sang runtime.

Một annotation `SOURCE` trong file `.class` đã biên dịch thường không còn; nếu một processor chỉ nhận thông tin qua binary mà không có source tương ứng, nó không thể giả định annotation `SOURCE` vẫn có đó. Khi cần xem annotation `SOURCE` của dependency, phải đảm bảo source thật sự được đưa vào compilation và được processor xử lý.

**Type-use annotations** (`ElementType.TYPE_USE`) có cách biểu diễn riêng qua `TypeMirror` / `AnnotatedConstruct`. Không được suy ra rằng mọi annotation trong source đều tự xuất hiện trong `RoundEnvironment.getElementsAnnotatedWith(...)` theo cách giống một annotation trên class. Một processor phân tích type-use cần làm việc với mô hình type phù hợp.

## 3. Dòng thời gian biên dịch và các vòng xử lý

Về ý tưởng, một lần `javac` có annotation processing được cấu hình diễn ra như sau:

```text
.java đầu vào và các dependency
         |
         v
javac đọc nguồn, xây dựng mô hình Element / Type
         |
         v
Round 1: gọi processors cho những annotation phù hợp
         |  \
         |   \-- Filer tạo source/resource mới
         v
Round 2: compiler đưa source mới vào tập xử lý
         |
         v
Các round tiếp nếu tiếp tục sinh source mới
         |
         v
Round cuối: processingOver() == true
         |
         v
Biên dịch các nguồn gốc và nguồn được sinh ra
         |
         v
.class, generated source, diagnostics
```

Sơ đồ diễn đạt cơ chế **logic**, không cố gắng mô tả mọi pha nội bộ của bản `javac` cụ thể. Đặc biệt:

1. Trong một round, processor được hỏi về **các annotation types** mà nó khai báo hỗ trợ.
2. Processor nhận `RoundEnvironment` để lấy các elements tương ứng. Không bắt buộc mỗi round đều có annotation cần xử lý.
3. Nếu tạo source files mới, processor và compiler có thể đi sang round tiếp theo để xử lý các declarations mới.
4. Processor đã được gọi ở một round sẽ còn được gọi trong các round tiếp, gồm round cuối; khi `processingOver()` đúng, không nên tạo source mới với kỳ vọng có thêm round để xử lý chúng.
5. Khi không dùng `-proc:only`, compiler tiếp tục tạo class files cho nguồn ban đầu và nguồn sinh ra, nếu không có lỗi ngăn biên dịch.

Không nên hiểu “một processor được tạo mới cho mỗi round”: instance processor được khởi tạo và có thể tham gia nhiều round trong **một lần compilation**, vì vậy phải thiết kế code tránh viết cùng một file hai lần.

## 4. Khi nào nên sinh mã và khi nào không?

### 4.1. Những tình huống code generation có giá trị

| Nhu cầu | Vì sao sinh mã có ích | Ví dụ kiểu bài toán |
| --- | --- | --- |
| Mã lặp lại có quy luật ổn định | Giảm code boilerplate nhưng vẫn có source/class rõ ràng | Builder, factory, typed adapter |
| Ánh xạ có thể xác định từ kiểu tĩnh | Kiểm tra cấu trúc và tạo lời gọi trực tiếp | DTO mapper, serializer/deserializer |
| Tích hợp cần đăng ký danh sách kiểu | Sinh registry hoặc metadata ngay khi compile | Service index, DI component registry |
| Lỗi cấu hình nên được phát hiện sớm | Compiler có thể báo sai ngay tại phần tử source | Field bắt buộc, cấu hình annotation mâu thuẫn |
| Tránh runtime reflection trên đường nóng | Sinh mã gọi trực tiếp hoặc metadata được chuẩn bị trước | Một số mapper/DI framework |
| Tạo API strongly typed từ schema | Người viết được type checking và IDE completion | Typed client, enum-like schema bindings |

Code generation hợp lý nhất khi **đầu vào có cấu trúc**, quy tắc sinh mã **xác định được**, output **dễ kiểm tra và ổn định**, và chi phí bảo trì generator nhỏ hơn việc tự viết mã lặp đi lặp lại.

### 4.2. Những tình huống không nên sinh mã

- Chỉ có vài dòng logic đơn giản, không lặp lại đáng kể.
- Yêu cầu thay đổi **theo dữ liệu runtime**, cấu hình động hoặc user input sau khi triển khai.
- Logic sinh mã khó debug hơn bản viết tay; developer không nhìn được source được sinh hoặc không có cách test nó.
- Generator phải đọc Internet, thời gian hiện tại, biến ngẫu nhiên hay hệ thống ngoài trong mỗi build mà không khóa inputs, khiến build không tái hiện.
- Muốn **thay đổi thân phương thức của class hiện hữu** bằng API chuẩn; JSR 269/Filer không phải công cụ rewrite AST. Cân nhắc cách thiết kế khác hoặc công cụ chuyên dụng khi thực sự cần.
- Gặp xung đột tên/file generated, phụ thuộc vòng sinh vô hạn hoặc yêu cầu processor dựa vào thứ tự gọi của processor khác.
- Tăng thời gian compile, phức tạp hóa IDE/CI hoặc tạo API bùng nổ mà lợi ích không tương xứng.

**Phân biệt validation và generation:** nhiều annotation processors chỉ kiểm tra và báo lỗi bằng `Messager`; hoàn toàn không cần tạo file. Chỉ sinh mã khi có artifact cụ thể mà người dùng sẽ sử dụng.

## 5. Ví dụ đầy đủ: annotation tạo một lớp Java dùng được ngay trong lượt compile

Ví dụ sau sử dụng **JDK 17 trở lên**, chạy trong một project thông thường không khai báo `module-info.java`. Tên file, tên package và lệnh được viết nhất quán, không yêu cầu thư viện ngoài JDK.

Cấu trúc:

```text
annotation-demo/
├── processor-src/
│   └── processor/
│       └── GreetingProcessor.java
└── src/
    └── demo/
        ├── AutoGreeting.java
        ├── OrderService.java
        └── Main.java
```

### 5.1. Định nghĩa annotation

File **`src/demo/AutoGreeting.java`**:

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface AutoGreeting {
}
```

`@Target(TYPE)` cho phép annotation trên class/interface/enum...; processor ở dưới chỉ chấp nhận **class** và báo lỗi nếu loại khai báo khác. `RetentionPolicy.SOURCE` là đủ vì annotation chỉ dùng trong quá trình biên dịch.

### 5.2. Khai báo sử dụng annotation

File **`src/demo/OrderService.java`**:

```java
package demo;

@AutoGreeting
public final class OrderService {
}
```

Không có file `OrderServiceGreeting.java` trong cây nguồn do lập trình viên viết; processor sẽ tạo nó.

### 5.3. Main gọi một class chưa tồn tại trước khi compile

File **`src/demo/Main.java`**:

```java
package demo;

public class Main {
    public static void main(String[] args) {
        System.out.println(OrderServiceGreeting.message());
    }
}
```

Nếu **không chạy processor**, compiler sẽ không tìm thấy `OrderServiceGreeting` và báo lỗi. Khi cấu hình processor đúng, class được sinh ra và compiler có thể giải quyết tên ngay trong lần biên dịch ấy.

### 5.4. Viết processor bằng API chuẩn

File **`processor-src/processor/GreetingProcessor.java`**:

```java
package processor;

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

@SupportedAnnotationTypes("demo.AutoGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        for (TypeElement annotation : annotations) {
            for (Element element
                    : roundEnv.getElementsAnnotatedWith(annotation)) {

                if (element.getKind() != ElementKind.CLASS) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "@AutoGreeting requires a class",
                            element);
                    continue;
                }

                TypeElement type = (TypeElement) element;
                String packageName = processingEnv.getElementUtils()
                        .getPackageOf(type).getQualifiedName().toString();
                String simpleName = type.getSimpleName() + "Greeting";
                String fullName = packageName + "." + simpleName;

                try {
                    JavaFileObject file = processingEnv.getFiler()
                            .createSourceFile(fullName, type);

                    try (Writer writer = file.openWriter()) {
                        writer.write("package " + packageName + ";\n");
                        writer.write("public final class " + simpleName + " {\n");
                        writer.write("  private " + simpleName + "() {}\n");
                        writer.write("  public static String message() {\n");
                        writer.write("    return \"Hello from processor\";\n");
                        writer.write("  }\n");
                        writer.write("}\n");
                    }
                } catch (IOException e) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "Cannot generate " + fullName + ": " + e,
                            element);
                }
            }
        }
        return true;
    }
}
```

**Tại sao đoạn code dùng các API này?**

- `@SupportedAnnotationTypes("demo.AutoGreeting")` khai báo loại annotation có thể được processor xử lý.
- `@SupportedSourceVersion(SourceVersion.RELEASE_17)` công bố mức source tối đa mà phiên bản processor ví dụ này hỗ trợ; không phải cờ điều khiển `javac` target. Dùng `--release 17` trong các lệnh để thống nhất bài thử.
- `annotations` nhận các `TypeElement` đại diện annotation types mà framework yêu cầu xử lý trong round. Dùng `getElementsAnnotatedWith(TypeElement)` giúp không cần nạp annotation class bằng reflection trong classloader của processor.
- `ElementKind.CLASS` kiểm tra đúng loại declaration trước khi tạo class; `TypeElement` biểu diễn khai báo kiểu trong mô hình compiler.
- `Elements.getPackageOf(type)` đọc package; `Filer.createSourceFile(fullName, type)` yêu cầu compiler quản lý **một source file mới** và ghi nhận originating element để hỗ trợ công cụ build.
- `Messager.printMessage(ERROR, ..., element)` tạo diagnostic gắn với phần tử, dễ tìm trong IDE/CI. Không dùng `System.out.println` như cơ chế báo lỗi.
- `process(...)` trả `true` nghĩa là processor **claim** các annotation types được yêu cầu, để processor tiếp theo không tiếp tục xử lý chúng dưới cơ chế claim thông thường. Điều này là quyết định có chủ ý, không phải “đã tạo file thành công” theo nghĩa trả về của hàm.
- `processingOver()` nhận diện round cuối; processor không cố tạo thêm mã ở round này.

**Giới hạn ví dụ:** processor sinh tên class dựa trên simple name. Nó phù hợp lớp top-level như `demo.OrderService`; với nested classes, nhiều khai báo cùng simple name, nhiều processors hoặc quy tắc đặt tên phức tạp, phải thiết kế tên generated ổn định và tránh trùng. Ví dụ không nhằm xử lý mọi dạng cấu trúc Java.

## 6. Biên dịch processor trước, rồi dùng nó trong javac

Processor cần được **biên dịch trước khi `javac` chạy nó**. Nếu processor và code ứng dụng nằm trong cùng một nhóm source mà processor chưa tồn tại dưới dạng class, đừng mong compiler tự “vừa viết processor vừa thực thi nó” trong lượt này.

Đứng tại thư mục `annotation-demo`, tạo ba output directories:

```bash
# Linux/macOS
mkdir -p build/processor build/generated build/classes
```

```powershell
# Windows PowerShell
New-Item -ItemType Directory -Force build/processor,build/generated,build/classes | Out-Null
```

### 6.1. Bước A: compile riêng processor

```bash
javac --release 17 -d build/processor processor-src/processor/GreetingProcessor.java
```

Vì processor chỉ tham chiếu API chuẩn của JDK, bước này không cần dependency annotation `demo.AutoGreeting`. Artifact tạo ra:

```text
build/processor/processor/GreetingProcessor.class
```

### 6.2. Bước B: compile ứng dụng và chạy processor

Dùng lệnh bên dưới cho Linux/macOS **và** Windows PowerShell (đường dẫn không chứa dấu cách trong ví dụ):

```bash
javac --release 17 \
  -processorpath build/processor \
  -processor processor.GreetingProcessor \
  -s build/generated \
  -d build/classes \
  src/demo/AutoGreeting.java \
  src/demo/OrderService.java \
  src/demo/Main.java
```

Các dấu `\` cuối dòng là cú pháp nối dòng của shell POSIX, **không** phải cú pháp Windows PowerShell. Trên PowerShell, dùng một dòng tương đương:

```powershell
javac --release 17 -processorpath build/processor -processor processor.GreetingProcessor -s build/generated -d build/classes src/demo/AutoGreeting.java src/demo/OrderService.java src/demo/Main.java
```

Khi xử lý `@AutoGreeting`, processor tạo file:

```text
build/generated/demo/OrderServiceGreeting.java
```

Nội dung file được sinh ra:

```java
package demo;

public final class OrderServiceGreeting {
  private OrderServiceGreeting() {}
  public static String message() {
    return "Hello from processor";
  }
}
```

Compiler tiếp tục biên dịch code nguồn ban đầu **và** source mới được tạo để có thể dùng `OrderServiceGreeting` từ `Main`. Output class chính:

```text
build/classes/
└── demo/
    ├── AutoGreeting.class
    ├── Main.class
    ├── OrderService.class
    └── OrderServiceGreeting.class
```

### 6.3. Chạy chương trình

```bash
java -cp build/classes demo.Main
```

Stdout kỳ vọng chính xác trên JDK 17+:

```text
Hello from processor
```

**Điều cần phân biệt:** `-s` chỉ định nơi ghi **source được sinh**, còn `-d` chỉ định nơi ghi **class files**. Generated source có thể được compiler biên dịch trong cùng compilation unit nhưng file `.java` vẫn là artifact riêng để đọc/kiểm tra. Nếu một trong các lệnh build thất bại, không dùng class file cũ để kết luận processor chạy thành công.

## 7. Chỉ định processor, discovery và thay đổi mặc định theo JDK

Có hai cách phổ biến để tìm processor:

1. **Liệt kê rõ tên processor** với `-processor processor.GreetingProcessor` và đặt class của nó trong `-processorpath` (như bài thực hành).
2. **Service discovery** bằng file `META-INF/services/javax.annotation.processing.Processor` trong JAR/thư mục processor path; nội dung liệt kê tên triển khai `Processor`, mỗi dòng một tên đầy đủ. Build tool thường đưa JAR processor lên riêng một processor path.

Cách thứ hai hữu ích cho thư viện processor được đóng gói để tái sử dụng, nhưng phải hiểu thay đổi phiên bản JDK:

- **JDK 21:** `javac` có thể tự phát hiện processor trên classpath theo cơ chế cũ nếu không cấu hình rõ; nó cảnh báo/thông báo về việc phụ thuộc implicit discovery trong một số tình huống.
- **JDK 23 trở lên:** mặc định **không tự chạy annotation processing chỉ vì có processor tình cờ nằm trên classpath**. Muốn chạy cần cấu hình processor/discovery path hoặc yêu cầu processing tường minh, ví dụ `-processor`, `--processor-path`, `--processor-module-path`, `-proc:full`.
- **`-proc:none`:** tắt xử lý annotation.
- **`-proc:only`:** chỉ chạy annotation processing, không thực hiện giai đoạn biên dịch class files của các source theo cách thông thường.
- **`-proc:full`:** yêu cầu thực hiện annotation processing và compilation; trên các compiler hỗ trợ cờ này, đây là cách cấu hình tường minh.

**Đối với build có codegen, hãy cấu hình processor một cách rõ ràng**, không dựa vào default discovery khác nhau giữa các bản JDK. Lệnh trong ví dụ dùng đồng thời `-processorpath` và `-processor` nên mô tả trực tiếp processor nào cần chạy. Khi chạy JDK cũ hơn, kiểm tra việc hỗ trợ các giá trị `-proc` theo phiên bản và bản update; ví dụ source code đã chọn Java 17 không có nghĩa mọi bản JDK 17 đều cung cấp cùng cờ compiler mới.

## 8. Các vòng xử lý: vì sao source vừa sinh có thể được compiler nhận diện?

Trong ví dụ:

- **Round đầu:** compiler đọc `OrderService` mang `@AutoGreeting` và gọi `GreetingProcessor`.
- Processor ghi `OrderServiceGreeting.java` bằng `Filer`.
- **Round tiếp:** file generated trở thành nguồn đầu vào của vòng sau. Vì class được sinh không mang `@AutoGreeting`, processor không cần tạo thêm source.
- **Round cuối:** `processingOver()` đúng; processor trả về mà không ghi thêm file.
- Compiler tạo class files từ nguồn ban đầu và generated source, miễn là không có lỗi.

Có thể quan sát bằng tùy chọn `javac`:

```bash
javac --release 17 -XprintRounds -XprintProcessorInfo -processorpath build/processor -processor processor.GreetingProcessor -s build/generated -d build/classes src/demo/AutoGreeting.java src/demo/OrderService.java src/demo/Main.java
```

Các cờ này in diagnostic về rounds và processor được gọi, nhưng nội dung/vị trí log chi tiết phụ thuộc phiên bản compiler. Không cần ép các dòng log thành một output cố định để xác định tính đúng của bài. Cần kiểm tra file generated cùng kết quả chạy cuối.

Đừng tạo mã ở round cuối với kỳ vọng compiler sẽ mở round mới. Tránh quy trình processor A nhất định phải tạo file trước thì processor B mới có thể chạy **trong cùng round theo một thứ tự bất biến**; API chuẩn khuyến khích processors hoạt động độc lập, deterministic và không dựa vào thứ tự xử lý ngầm.

## 9. Filer, Messager, Elements và Types: công cụ cốt lõi

| API | Vai trò | Khi cần dùng |
| --- | --- | --- |
| `RoundEnvironment` | Xác định annotation/element đang được xử lý, trạng thái final round | Mỗi lần `process` |
| `Element`, `TypeElement` | Mô hình khai báo class, interface, method, field | Phân tích source tĩnh |
| `TypeMirror` | Mô hình kiểu trong compile-time Java language model | Kiểm tra kiểu, generics, subtype |
| `Elements` (`processingEnv.getElementUtils()`) | Tìm kiếm và đọc tên, package, annotations, members | Sinh code theo cấu trúc declaration |
| `Types` (`processingEnv.getTypeUtils()`) | Kiểm tra assignability, subtyping, erasure, các phép biến đổi kiểu | Validation typed mapper, adapter |
| `Filer` | Tạo source/class/resource output | Khi có artifact cần sinh |
| `Messager` | Báo NOTE/WARNING/ERROR có vị trí liên quan | Validation và diagnostics |
| `ProcessingEnvironment.getOptions()` | Đọc `-Akey=value` tùy chọn riêng cho processor | Config generator một cách có khai báo |

Ví dụ, processor kiểm tra một method có kiểu trả về phù hợp nên dùng `TypeMirror` và `Types`, **không** sử dụng `Class.forName(...)` để cố tải lớp đang được compile. Class của source có thể chưa tồn tại trong processor runtime; ClassLoader và compile-time model là hai thế giới khác nhau.

Cẩn trọng khi sinh chuỗi Java source: dữ liệu từ annotation có thể chứa dấu nháy, xuống dòng, backslash hoặc tên không hợp lệ. Ví dụ trong bài chỉ sinh **hằng chuỗi cố định**, tránh nhu cầu escape input. Generator thực tế cần escape literal đúng ngữ pháp Java, validate identifiers, kiểm soát package names và xử lý encoding phù hợp.

### Filer không phải API chỉnh sửa source cũ

`Filer.createSourceFile(...)` tạo một file mới với tên fully qualified. Trong cùng một compilation run, cố tạo **hai lần cùng một tên** sẽ dẫn tới `FilerException`; xung đột với một file source đầu vào cũng là lỗi. Filer nhận originating elements để build systems có thể biết output xuất phát từ đầu vào nào; điều này giúp incremental compilation nhưng không tự làm mọi processor trở nên incremental.

Không viết đè source người dùng, tự động sửa class đang được xử lý hoặc dùng đường dẫn tùy tiện thay cho Filer trong lúc build: các cách này làm hỏng ranh giới quyền sở hữu file, phá IDE và khiến quá trình build khó tái hiện.

## 10. Tách processor path khỏi application classpath

Một annotation processor **chạy trong môi trường thực thi compiler**, dù nó đọc một mô hình chương trình đang được biên dịch. Điều này làm rõ hai tập dependency khác nhau:

- **Application compile classpath:** dependencies mà source ứng dụng được phép tham chiếu khi compile.
- **Processor path:** JAR/classes của processor và dependencies cần thiết **để chính processor thực thi**.

Với ví dụ, `-processorpath build/processor` chứa implementation của `GreetingProcessor`; `src/demo/AutoGreeting.java` được cung cấp dưới dạng source để compiler thấy annotation. Processor không cần tham chiếu class annotation trực tiếp nên không cần thêm annotation JAR vào processor path.

Nếu processor của bạn tự import một annotation class cụ thể thay vì dùng `TypeElement`, processor sẽ cần annotation class đó trên processor classpath khi **compile và load processor**. Nếu processor sử dụng thư viện template hoặc parser, các dependencies cần thiết cũng phải được đưa vào processor path.

Không nên đặt mọi thư viện ứng dụng lên processor path không cần thiết. Vì processors là **chương trình thực thi trong build**, một processor từ dependency không tin cậy có thể đọc file, môi trường và tạo output; nên pin versions, kiểm tra nguồn cung, chỉ bật processors được chấp thuận và không cung cấp secrets vô hạn cho job compile.

Đối với JPMS, `--processor-module-path` dùng tìm processor được đóng gói thành modules; đừng hoán đổi cơ học với `--module-path` của ứng dụng. Xem đúng tài liệu `javac` cho cấu trúc module đang dùng.

## 11. Build tool và IDE: làm codegen ổn định

### 11.1. Trong Gradle

Khi dùng Gradle Java plugin, thường khai báo riêng các dependencies phục vụ compile-time API và processor. Ví dụ ký hiệu (cần thay tọa độ artifact bằng dependency thật do dự án chọn):

```groovy
dependencies {
    compileOnly 'example:annotations:1.0'
    annotationProcessor 'example:generator:1.0'
}
```

Đây là **đoạn Gradle DSL minh họa, không phải một project có dependency tồn tại thật**. `compileOnly` phù hợp khi annotation API chỉ cần lúc compile; `annotationProcessor` đưa processor vào processor path do Gradle quản lý. Một số framework cần annotation API ở runtime, khi đó dependency scope phải thay đổi tương ứng. Cấu hình `testAnnotationProcessor` hoặc các source sets khác khi test code cũng sử dụng annotation processors.

Gradle có thể quản lý generated sources và incremental compilation, nhưng không đảm bảo mọi processor đều hỗ trợ incremental. Trong build nghiêm túc, dùng dependency locking/verification, kiểm tra toolchain, options và generated output directory thay vì dựa vào generated files tình cờ còn từ lần build trước.

### 11.2. Trong Maven

Maven Compiler Plugin có các cấu hình cho annotation processors và processor paths/processor dependencies; cách viết cụ thể phụ thuộc **phiên bản Maven/JDK/plugin**. Hãy đọc tài liệu plugin đang được dùng thay vì giả định một cấu hình cũ phù hợp với JDK 23+. Các điểm phải xác định:

- Processor nào được phép chạy và version/JAR thực tế của nó.
- Source/target hoặc `release` mà compiler sử dụng.
- Generated sources directory, compile classpath và processor dependency isolation.
- Có chạy xử lý trong test compilation hay không.

Với codegen quan trọng, cố định Maven Wrapper/plugin versions và build trên JDK có cấu hình processing tường minh.

### 11.3. IDE và CI

IDE chỉ nhận ra class generated khi cấu hình annotation processing phù hợp và generated source directory được IDE đánh dấu đúng. Khi gặp “command line build được nhưng IDE đỏ”, kiểm tra trạng thái bật processors, compiler JDK, processor path, output directory và các plugin IDE cần thiết.

**Không commit generated sources một cách mù quáng.** Nếu generated code là artifact có thể tạo lại từ source và generator đã khóa, thường quản lý nó trong build output, không sửa tay. Một số dự án có lý do lưu generated sources để review hoặc phát hành SDK; khi đó cần nêu chính sách rõ ràng và kiểm tra output không bị drift.

## 12. Chất lượng của generated code và khả năng tái hiện

Nếu một processor sinh mã, coi output là code thật cần kiểm thử:

1. **Deterministic:** cùng input/versions/options phải cho cùng output về mặt nội dung có ý nghĩa. Sắp xếp các phần tử theo thứ tự ổn định nếu thứ tự đầu ra ảnh hưởng artifacts.
2. **Không đọc dữ liệu ẩn không được khai báo:** hạn chế thời gian hiện tại, random ID, đường dẫn máy và network trong generated output.
3. **Tên file/class ổn định:** tránh collision khi nhiều elements có simple name giống nhau, nested types hay nhiều processors cùng tạo một artifact.
4. **Không ghi trùng file:** mỗi tên chỉ tạo một lần trong một run; xử lý round cuối và duplicate gracefully.
5. **Nguồn gốc rõ:** truyền originating elements cho `Filer` khi thích hợp và giữ generated source directory dễ inspect.
6. **Diagnostics tốt:** báo lỗi lên phần tử cấu hình sai, giải thích cách sửa; không nuốt `IOException` hoặc biến mọi lỗi thành thành công giả.
7. **Không sinh source không hợp lệ:** escape giá trị và validate identifier/package/types; kiểm tra bằng compiler thật.
8. **API được quản lý:** thay đổi tên/class generated có thể phá consumers; versioning processor và annotation API phải phối hợp.
9. **Tránh phụ thuộc vòng:** processor không nên cần output của chính nó mới có thể khởi động; tránh thiết kế gây phát mã qua rounds không giới hạn.
10. **Compile/test generated code:** có unit tests cho processor, negative tests cho cấu hình sai và integration tests chứng minh client gọi generated API được.

Một generator tốt nên có **hợp đồng nhỏ, rõ ràng và dễ dự đoán**. Nếu một rule thay đổi nhỏ nhưng làm bùng nổ số lượng lớp sinh ra hoặc diagnostics khó hiểu, chi phí build có thể vượt lợi ích.

## 13. Những lỗi điển hình và cách điều tra

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra |
| --- | --- | --- |
| `cannot find symbol: OrderServiceGreeting` | Processor không chạy, không được discover, hoặc không sinh file | `-processor` / `-processorpath`, `-proc`, generated source directory, diagnostics |
| `Annotation processor ... not found` | Class processor chưa compile, sai tên, thiếu dependency hoặc processor path | Xem `build/processor`/JAR và fully qualified processor name |
| `FilerException: Attempt to recreate a file` | Processor hoặc processor khác cố tạo trùng source/class trong cùng run | Tên generated, rounds, output ownership, duplicate inputs |
| Code generated nhưng IDE không resolve | IDE chưa bật annotation processing hoặc chưa nhận generated source root | Cấu hình IDE và generated paths |
| Chạy được trên JDK 21 nhưng processor không chạy trên JDK 23 | Phụ thuộc mặc định implicit discovery cũ | Cấu hình processing tường minh |
| Processor có `@SupportedSourceVersion` thấp hơn source | Khai báo source version của processor không phù hợp compilation | Cập nhật processor và source-version policy |
| Generated class thiếu method/khác kỳ vọng | Generator version, annotation value hoặc build cache cũ | Version/hash dependencies, clean build, generated source |
| `NoClassDefFoundError` trong processor | Thiếu dependency của chính processor trên processor path | Tách processor path khỏi application dependencies |
| Generated Java lỗi cú pháp | Escape string/identifier sai, import thiếu, tên class trùng | Mở `-s` output, kiểm tra diagnostics và generated source |
| Build kéo dài qua nhiều rounds | Processor sinh thêm source không dừng, phụ thuộc lẫn nhau | `-XprintRounds`, điều kiện tạo file, final-round guard |

**Không đọc log qua một dòng duy nhất.** Kết hợp source annotation, lệnh compiler thực tế, processor path, danh sách generated files và diagnostics. `-XprintRounds` / `-XprintProcessorInfo` hỗ trợ xác định processor có chạy và nhận annotation type nào.

## 14. Khi chỉ cần kiểm tra compile-time, không nhất thiết sinh file

Một processor có thể phát lỗi khi phát hiện cấu hình sai:

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "A required annotation value is missing",
        element);
```

Đây là **đoạn code minh họa bên trong method `process`** với biến `element` đang có sẵn; không phải chương trình Java độc lập. Khi dùng `Diagnostic.Kind.ERROR`, compiler có thể báo compilation thất bại dù processor không tạo nguồn nào. Các công cụ như kiểm tra convention của DTO/API, quy tắc đặt tên đặc biệt hoặc annotation combinations có thể đạt mục tiêu chỉ bằng validation.

Một nguyên tắc thiết kế hữu ích:

- Nếu muốn **báo lỗi sớm** → ưu tiên validation.
- Nếu muốn **tạo API/metadata tĩnh lặp lại và có quy luật** → cân nhắc code generation.
- Nếu hành vi thật sự phải **thay đổi lúc chạy** → cân nhắc cấu hình runtime, reflection, service loading hoặc cách khác phù hợp.
- Nếu mục tiêu là **sửa AST/bytecode của class hiện có** → JSR 269 không cung cấp hợp đồng chuẩn cho việc đó; dùng phương án chuyên dụng và hiểu tính phụ thuộc compiler.

## 15. Thử nghiệm đối chứng: bật và tắt processor

Sau khi đã compile `GreetingProcessor`, thử với **output mới/sạch**:

### 15.1. Bật processor rõ ràng

```bash
javac --release 17 -processorpath build/processor -processor processor.GreetingProcessor -s build/generated -d build/classes src/demo/AutoGreeting.java src/demo/OrderService.java src/demo/Main.java
```

Kết quả: processor tạo `OrderServiceGreeting.java`, compiler tạo class và `demo.Main` in `Hello from processor` khi chạy.

### 15.2. Tắt processor

```bash
javac --release 17 -proc:none -d build/without-processor src/demo/AutoGreeting.java src/demo/OrderService.java src/demo/Main.java
```

Nếu `build/without-processor` không chứa class cũ và compile classpath không chứa `OrderServiceGreeting` ở nơi khác, lệnh này **thất bại** vì `Main` tham chiếu class chưa được sinh. Đây là phép thử để xác nhận chính processor là nguồn tạo API đó.

### 15.3. Chỉ chạy annotation processing

```bash
javac --release 17 -proc:only -processorpath build/processor -processor processor.GreetingProcessor -s build/only-generated -d build/only-classes src/demo/AutoGreeting.java src/demo/OrderService.java src/demo/Main.java
```

Đối với chế độ `-proc:only`, hãy kiểm tra generated sources và diagnostics; không kỳ vọng đây là bước tạo đầy đủ class files để chạy `demo.Main`. Nếu muốn chạy ứng dụng, phải có giai đoạn compilation tạo các `.class` tương ứng. Đừng giả định generated file tự trở thành runtime class.

**Giữ môi trường sạch** khi so sánh. Nếu thư mục output chứa `OrderServiceGreeting.class` từ một lần compile trước, một phép thử tắt processor có thể bị che khuất. Trong dự án thật, dùng clean build hoặc các output directories tách biệt và ghi rõ classpath.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `@Retention(SOURCE)` có khiến annotation processor không đọc được annotation không?

**Đáp án:** Không. Processor có thể đọc annotation trên source trong compile time. Retention SOURCE chỉ có nghĩa annotation đó không phải runtime metadata sau compilation.

**Câu 2.** Nếu muốn processor tạo `OrderServiceGreeting.java`, API chuẩn nào phụ trách tạo file?

**Đáp án:** `ProcessingEnvironment.getFiler().createSourceFile(...)`. Nên truyền originating elements khi phù hợp và không tạo trùng tên trong cùng compilation.

**Câu 3.** Vì sao phải compile `GreetingProcessor.java` trước khi chạy nó trong ví dụ?

**Đáp án:** `javac` cần load một implementation `Processor` đã có dạng class (hoặc processor JAR), đặt đúng processor path. Mã nguồn processor chưa compile không tự trở thành processor thực thi trong cùng lượt biên dịch ứng dụng.

**Câu 4.** `process(...)` trả `true` có nghĩa “mọi file sinh mã thành công” không?

**Đáp án:** Không. `true` nghĩa là processor claim các annotation types được giao xử lý trong round; việc thành công/thất bại của generation phải được phản ánh qua output và diagnostics.

**Câu 5.** Vì sao processor không nên gọi `Class.forName("demo.OrderService")` để khám phá method của class đang compile?

**Đáp án:** Class đang được compile có thể chưa tồn tại ở runtime của processor. Cần dùng mô hình `Element` / `TypeMirror` qua `Elements` và `Types`.

**Câu 6.** Một build chạy annotation processing trên JDK 21 mà không có cấu hình nào. Đến JDK 23 generated classes biến mất. Nguyên nhân có thể là gì?

**Đáp án:** Từ JDK 23 không còn tự chạy processors chỉ vì vô tình tìm được trên classpath. Đặt processor/discovery path hoặc `-proc:full` tường minh, kiểm tra JDK và build tool.

**Câu 7.** Một processor chỉ cần kiểm tra annotation value và báo lỗi nếu sai. Có bắt buộc phải sinh Java source không?

**Đáp án:** Không. Dùng `Messager` phát diagnostic là đủ; code generation chỉ phù hợp khi cần một artifact cụ thể.

**Câu 8.** Có nên sinh tên class bằng simple name của mọi nested type mà không xét owner/package không?

**Đáp án:** Không. Nhiều kiểu có thể trùng simple name và tạo collision. Generator cần quy tắc đặt tên đầy đủ, ổn định và kiểm tra xung đột.

## 17. Nguồn tham khảo chính thức

- **Oracle JDK 21 `javac` — Annotation Processing:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — cơ chế rounds, `-processor`, `-processorpath`, `-proc`, `-s`, `-XprintRounds`.
- **JDK 23 Release Notes:** https://www.oracle.com/java/technologies/javase/23all-relnotes.html — thay đổi default annotation processing; yêu cầu cấu hình rõ ràng.
- **Java SE 21 `Processor` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/Processor.html — lifecycle, `process` và claiming semantics.
- **Java SE 21 `RoundEnvironment` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html — rounds, `getElementsAnnotatedWith` và `processingOver`.
- **Java SE 21 `Filer` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/Filer.html — tạo source/class/resource và các ràng buộc file.
- **Java SE 21 `ProcessingEnvironment` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html — access tới `Elements`, `Types`, `Filer` và `Messager`.

**Kết luận:** annotation processing là một bước compile-time dùng mô hình chương trình để **kiểm tra quy tắc hoặc sinh mã/tài nguyên mới**. Nên sinh mã khi output có quy luật, mang giá trị type-safe và tái hiện được; nên dùng validation nếu chỉ cần báo sai, và chọn cơ chế runtime khi yêu cầu thật sự động. Cấu hình processors tường minh, quản lý generated sources và test cả code được sinh là những yếu tố quyết định để giải pháp hoạt động ổn định.