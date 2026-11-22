# Filer và sinh mã, class hoặc tài nguyên trong Java Annotation Processing

`javax.annotation.processing.Filer` là API chuẩn của Java dùng để **tạo tệp đầu ra trong một lần annotation processing**. Một annotation processor có thể dùng `Filer` để sinh mã nguồn `.java`, ghi trực tiếp bytecode `.class` hoặc tạo các resource như `.txt`, `.json` và tệp metadata. Những tệp đó được quản lý bởi môi trường compiler thay vì tự chọn đường dẫn rồi dùng `Files.write(...)` tùy tiện.

API nằm trong module chuẩn `java.compiler`, đã có từ Java 6 và **vẫn được hỗ trợ trong Java hiện đại**. Khi học hoặc xây công cụ mới, cần chú ý một thay đổi quan trọng của `javac` từ **JDK 23**: annotation processing không còn tự động chạy nếu người dùng không cấu hình hoặc yêu cầu rõ ràng. Vì vậy, ví dụ bên dưới chỉ định processor bằng `-processor`, tương thích với Java 17+.

**Trọng tâm của bài:** chọn đúng `createSourceFile`, `createClassFile` hay `createResource`; viết và đóng output đúng cách; quản lý các vòng xử lý (*rounds*) và tránh lỗi tạo trùng tệp `FilerException`.

## 1. Vai trò của Filer trong Annotation Processing

Luồng xử lý điển hình:

```text
Source code
    |
    +-- @GenerateGreeting trên demo.Demo
    |
    v
javac + annotation processor
    |
    +-- RoundEnvironment: tìm element mang annotation
    |
    +-- ProcessingEnvironment.getFiler()
            |
            +-- createSourceFile("demo.generated.HelloGenerated")
            |         -> .java, compiler xử lý ở round sau
            |
            +-- createClassFile("some.package.Type")
            |         -> .class hợp lệ, do processor tự tạo bytecode
            |
            +-- createResource(CLASS_OUTPUT, "demo.generated", "message.txt")
                      -> resource trong output của build
    |
    v
Compiler biên dịch source gốc + source được sinh ra
    |
    v
Ứng dụng dùng class và resource đã tạo
```

Các thành phần liên quan:

| Thành phần | Nhiệm vụ |
| --- | --- |
| `Processor` / `AbstractProcessor` | Logic xử lý annotation, được `javac` gọi trong các round. |
| `ProcessingEnvironment` | Cung cấp `Filer`, `Messager`, các utilities và compiler options dành cho processor. |
| `RoundEnvironment` | Cho biết element cần xử lý trong round hiện tại, trạng thái round cuối và lỗi round trước. |
| `Filer` | Tạo đầu ra được compiler biết và quản lý. |
| `JavaFileObject` | Đại diện source Java hoặc class file được sinh ra; hỗ trợ `openWriter()` hoặc `openOutputStream()` tùy loại. |
| `FileObject` | Đại diện resource thông thường, ví dụ `message.txt`. |
| `Element` | Phần tử nguồn là nguyên nhân sinh ra output, có thể truyền làm `originatingElements`. |
| `Messager` | Gửi lỗi/cảnh báo từ processor ra hệ thống diagnostics của compiler. |

Lấy `Filer` thông qua `processingEnv.getFiler()` trong một processor đã được compiler khởi tạo, không tự `new Filer()`. `Filer` là interface; các output location, việc kiểm tra trùng và cách mở file do compiler/file manager triển khai.

## 2. Ba phương thức tạo tệp cần phân biệt

| API | Đầu ra | Khi dùng |
| --- | --- | --- |
| `createSourceFile(name, originatingElements...)` | Một `JavaFileObject` để ghi **Java source `.java`** | Sinh model, adapter, mapper, builder hoặc mã Java có thể được compiler biên dịch tiếp. |
| `createClassFile(name, originatingElements...)` | Một `JavaFileObject` để ghi **classfile `.class`** | Processor đã có **bytecode hợp lệ**, muốn ghi class trực tiếp mà không qua source generator. |
| `createResource(location, pkg, relativeName, originatingElements...)` | Một `FileObject` để ghi **resource tùy ý** | Sinh tệp dữ liệu/cấu hình, chẳng hạn `META-INF/services/...` hoặc `message.txt`. |

Ngoài ba phương thức tạo mới, `Filer` còn có `getResource(location, pkg, relativeName)` để đọc resource có thể truy cập từ location phù hợp; đừng nhầm nó với phương thức ghi.

### 2.1. `createSourceFile`

Chữ ký:

```java
JavaFileObject createSourceFile(
        CharSequence name, Element... originatingElements) throws IOException;
```

`name` là tên canonical/fully qualified của type cần khai báo, ví dụ `"demo.generated.HelloGenerated"`, **không phải** `"demo/generated/HelloGenerated.java"` hay chuỗi có đuôi `.java`. Compiler sẽ đặt file vào source-output location phù hợp. Với cấu hình đơn giản không dùng `-s`, `javac` có thể đặt generated source dưới class output directory; đừng hardcode đường dẫn vật lý.

Ghi source bằng `JavaFileObject.openWriter()` trong `try-with-resources` rồi đóng ngay. Source phải là Java hợp lệ và phải khai báo package/class phù hợp với tên đã yêu cầu.

```java
JavaFileObject source = filer.createSourceFile(
        "demo.generated.HelloGenerated", annotatedElement);

try (Writer writer = source.openWriter()) {
    writer.write("""
            package demo.generated;
            public final class HelloGenerated {
                private HelloGenerated() {}
                public static String message() {
                    return "Hello from Filer";
                }
            }
            """);
}
```

Đây là **đoạn code nằm bên trong processor**, với `filer`, `annotatedElement` đã có và import `JavaFileObject`, `Writer`. Source vừa tạo sẽ được compiler xem xét trong **round kế tiếp**; sau đó, khi biên dịch hoàn tất, compiler có thể tạo `HelloGenerated.class` từ source này.

### 2.2. `createClassFile`

Chữ ký:

```java
JavaFileObject createClassFile(
        CharSequence name, Element... originatingElements) throws IOException;
```

`name` là binary name của type, ví dụ `"demo.generated.BytecodeType"`, **không phải** đường dẫn `.class`. Processor phải ghi **dữ liệu classfile hợp lệ ở dạng byte**:

```java
// Đoạn code minh họa nằm bên trong processor.
// validClassBytes phải được tạo trước bằng công cụ tạo bytecode hợp lệ.
JavaFileObject classFile = filer.createClassFile(
        "demo.generated.BytecodeType", annotatedElement);
try (OutputStream stream = classFile.openOutputStream()) {
    stream.write(validClassBytes);
}
```

Đoạn này **không chạy độc lập**: `validClassBytes` cần là `byte[]` chứa classfile tuân theo format/JVM version tương ứng; `filer` và `annotatedElement` phải có sẵn. Có thể tạo bytes bằng thư viện bytecode phù hợp (ví dụ ASM/Byte Buddy với phiên bản hỗ trợ target Java) hoặc **Class-File API `java.lang.classfile` từ JDK 24+** nếu chọn toolchain mới hơn. Không ghi Java source text vào `openOutputStream()` rồi đặt tên `.class`.

**Quy tắc:** nếu chỉ muốn sinh một Java class bình thường, `createSourceFile` là phương án đơn giản và dễ kiểm thử hơn. Để compiler tự dịch `.java` thành `.class`, **không cần gọi thêm `createClassFile` cho cùng tên type**. Việc cố tạo cả source và classfile có cùng tên trong một lần processing có thể gây `FilerException`.

### 2.3. `createResource`

Chữ ký:

```java
FileObject createResource(
        JavaFileManager.Location location,
        CharSequence pkg,
        CharSequence relativeName,
        Element... originatingElements) throws IOException;
```

Ví dụ sinh resource nằm bên cạnh class files:

```java
FileObject resource = filer.createResource(
        StandardLocation.CLASS_OUTPUT,
        "demo.generated",
        "message.txt",
        annotatedElement);

try (Writer writer = resource.openWriter()) {
    writer.write("resource from Filer\n");
}
```

- `StandardLocation.CLASS_OUTPUT`: resource được ghi vào vùng output dành cho class, phù hợp cho tài nguyên cần **đóng gói vào JAR/runtime**.
- `StandardLocation.SOURCE_OUTPUT`: phù hợp cho tài nguyên đặt bên output của generated sources, nếu toolchain đã cấu hình location này.
- `pkg` là tên package, ví dụ `"demo.generated"`, không chứa dấu `/` thay cho dấu `.`. Có thể dùng chuỗi rỗng cho package không tên khi phù hợp.
- `relativeName` là tên tương đối như `"message.txt"` hoặc `"META-INF/services/com.example.Service"` khi package rỗng, **không dùng path tuyệt đối hoặc các thành phần `..`**.
- Resource này không tự được coi là source hoặc class mới để đưa vào các round xử lý tiếp theo, kể cả khi phần đuôi tình cờ là `.java` hoặc `.class`.

Không dùng `createResource` để lách cơ chế `createSourceFile` khi muốn compiler tự nhận một source mới. Dùng đúng loại file tạo sẽ làm cách compiler theo dõi output rõ ràng hơn.

## 3. Ví dụ đầy đủ: một annotation, processor sinh Java source và runtime resource

Ví dụ này chạy trên **JDK 17 trở lên**, đã được kiểm thử end-to-end trên JDK 24. Ta định nghĩa annotation `@GenerateGreeting`; khi thấy annotation này, processor sinh:

- `demo.generated.HelloGenerated.java` — mã nguồn Java mới;
- `demo.generated.HelloGenerated.class` — file được `javac` tạo **từ nguồn mới**;
- `demo/generated/message.txt` — resource do `Filer.createResource` tạo trực tiếp.

Ứng dụng `demo.App` gọi method từ generated class và đọc resource. Từng file bên dưới độc lập, không dùng framework hoặc dependency ngoài JDK.

### 3.1. Cấu trúc dự án

```text
filer-demo/
  src/
    processor/
      example/
        GreetingProcessor.java
    app/
      demo/
        GenerateGreeting.java
        Demo.java
        App.java
  build/                     (được tạo khi biên dịch)
    processor/
    classes/
```

### 3.2. Viết processor

**Tệp `src/processor/example/GreetingProcessor.java`**

```java
package example;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.FileObject;
import javax.tools.JavaFileObject;
import javax.tools.StandardLocation;

@SupportedAnnotationTypes("demo.GenerateGreeting")
public final class GreetingProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.latestSupported();
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        if (roundEnv.processingOver() || annotations.isEmpty() || generated) {
            return false;
        }
        TypeElement marker = processingEnv.getElementUtils()
                .getTypeElement("demo.GenerateGreeting");
        if (marker == null) {
            return false;
        }
        var annotated = roundEnv.getElementsAnnotatedWith(marker);
        if (annotated.isEmpty()) {
            return false;
        }
        Element origin = annotated.iterator().next();
        generated = true;
        try {
            JavaFileObject source = processingEnv.getFiler()
                    .createSourceFile("demo.generated.HelloGenerated", origin);
            try (Writer writer = source.openWriter()) {
                writer.write("""
                        package demo.generated;
                        public final class HelloGenerated {
                            private HelloGenerated() {}
                            public static String message() {
                                return "Hello from Filer";
                            }
                        }
                        """);
            }
            FileObject resource = processingEnv.getFiler()
                    .createResource(StandardLocation.CLASS_OUTPUT,
                            "demo.generated", "message.txt", origin);
            try (Writer writer = resource.openWriter()) {
                writer.write("resource from Filer\n");
            }
        } catch (IOException e) {
            processingEnv.getMessager().printMessage(Diagnostic.Kind.ERROR,
                    "Filer failed: " + e.getMessage(), origin);
        }
        return true;
    }
}
```

**Ý nghĩa của code:**

1. `@SupportedAnnotationTypes("demo.GenerateGreeting")` khai báo annotation mà processor nhận diện. Processor không cần import class annotation đó để được biên dịch trước ứng dụng.
2. `AbstractProcessor` cung cấp `processingEnv` sau khi được compiler khởi tạo. `getSupportedSourceVersion()` trả version mà compiler runtime hỗ trợ, tránh hardcode một bản Java thấp trong môi trường mới.
3. `process(...)` có thể được gọi nhiều lần. `roundEnv.processingOver()` nhận biết round cuối, `generated` bảo vệ ví dụ khỏi tạo cùng output hai lần.
4. `getElementsAnnotatedWith(marker)` lấy các element mang annotation. Trong ví dụ chỉ có một element `Demo`; `iterator().next()` được dùng làm `originatingElement`.
5. `createSourceFile` tạo class source có tên đầy đủ `demo.generated.HelloGenerated`; `try-with-resources` đóng `Writer` để compiler nhận được nội dung hoàn chỉnh.
6. `createResource` tạo `message.txt` trong `CLASS_OUTPUT`; khi đóng gói JAR, resource này cần được đóng gói cùng class.
7. Nếu quá trình tạo/ghi file thất bại, `Messager` báo một compiler `ERROR` có vị trí gắn với `origin`. Việc chỉ `printStackTrace` hoặc nuốt `IOException` sẽ khiến build khó chẩn đoán.
8. `return true` ở nhánh xử lý thành công thông báo processor đã claim annotation tương ứng, không nhờ processor khác tiếp tục xử lý cùng annotation trong round đó.

**Giới hạn có chủ đích:** đây là processor cho **một generated type/resource cố định**. Nếu nhiều class cùng `@GenerateGreeting` cần tạo artifact riêng, không thể dùng một tên output cố định cho tất cả. Hãy dẫn xuất tên từ element, tạo từng output duy nhất, lưu tập tên đã sinh và xác định rõ quan hệ originating element.

### 3.3. Annotation phía ứng dụng

**Tệp `src/app/demo/GenerateGreeting.java`**

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateGreeting {}
```

`RetentionPolicy.SOURCE` đủ cho nhiệm vụ compile-time: compiler nhìn thấy annotation để processor xử lý, nhưng runtime không cần giữ metadata này. Không đổi sang runtime retention nếu ứng dụng không cần reflection đọc annotation khi chạy.

### 3.4. Class mang annotation

**Tệp `src/app/demo/Demo.java`**

```java
package demo;

@GenerateGreeting
public final class Demo {}
```

Processor sẽ tìm thấy `Demo` và dùng element đó làm nguồn gốc của các output.

### 3.5. Ứng dụng đọc generated outputs

**Tệp `src/app/demo/App.java`**

```java
package demo;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class App {
    public static void main(String[] args) throws Exception {
        System.out.println(demo.generated.HelloGenerated.message());
        try (InputStream input = App.class.getClassLoader()
                .getResourceAsStream("demo/generated/message.txt")) {
            if (input == null) {
                throw new IllegalStateException("Resource missing");
            }
            System.out.println(new String(input.readAllBytes(),
                    StandardCharsets.UTF_8).trim());
        }
    }
}
```

Mặc dù `HelloGenerated.java` chưa tồn tại khi bắt đầu compile ứng dụng, processor tạo nó trong round đầu, compiler thu nhận nó ở round kế tiếp và biên dịch cùng ứng dụng. Điều đó giải thích vì sao `App.java` có thể tham chiếu class vừa được sinh ra **trong cùng một lần `javac`**.

### 3.6. Biên dịch và chạy

Trong thư mục `filer-demo`, dùng Bash (Linux/macOS):

```bash
mkdir -p build/processor build/classes
javac --release 17 -d build/processor src/processor/example/GreetingProcessor.java
javac --release 17 -processorpath build/processor -processor example.GreetingProcessor -d build/classes src/app/demo/GenerateGreeting.java src/app/demo/Demo.java src/app/demo/App.java
java -cp build/classes demo.App
```

Trên PowerShell (Windows), dùng các lệnh tương đương:

```powershell
New-Item -ItemType Directory -Force build/processor,build/classes | Out-Null
javac --release 17 -d build/processor src/processor/example/GreetingProcessor.java
javac --release 17 -processorpath build/processor -processor example.GreetingProcessor -d build/classes src/app/demo/GenerateGreeting.java src/app/demo/Demo.java src/app/demo/App.java
java -cp build/classes demo.App
```

**Stdout của lệnh `java` — đã kiểm chứng trên JDK 24:**

```text
Hello from Filer
resource from Filer
```

Kiểm tra thư mục đầu ra sau biên dịch:

```text
build/
  processor/
    example/GreetingProcessor.class
  classes/
    demo/
      GenerateGreeting.class
      Demo.class
      App.class
      generated/
        HelloGenerated.java
        HelloGenerated.class
        message.txt
```

Đường dẫn chính xác của `HelloGenerated.java` có thể khác khi dùng `-s` để chỉ định source output; ví dụ kiểm thử này không dùng `-s` nên `javac` đặt source sinh ra dưới `build/classes`. `HelloGenerated.class` được compiler sinh từ `.java` do processor viết, **không phải** do `Filer.createClassFile`.

## 4. Vì sao phải biên dịch processor trước?

`javac` cần tải **class của annotation processor** để gọi `process(...)`. Nếu class đó chỉ mới là source chưa được biên dịch và không nằm trên processor path, compiler không có processor sẵn để chạy. Vì vậy ví dụ chia hai bước:

1. `javac --release 17 -d build/processor ...GreetingProcessor.java` tạo processor class.
2. `javac ... -processorpath build/processor -processor example.GreetingProcessor ...` tải đúng processor, chạy các round và biên dịch ứng dụng.

Từ **JDK 23**, `javac` không tự chạy annotation processors chỉ vì tình cờ có chúng trên classpath khi không có cấu hình xử lý rõ ràng. Dùng `-processor` (đồng thời xác định processor path) như trên là lựa chọn dễ kiểm soát và có ý nghĩa bảo mật. Cũng có thể bật `-proc:full`, hoặc cấu hình processor path/module path theo dự án, nhưng **không nên vô tình chạy mọi processor không được kiểm soát**. `-proc:none` tắt processing; `-proc:only` chạy processing mà không biên dịch class output thông thường.

Nếu muốn khám phá processor qua Java SPI thay vì tên class tường minh, processor JAR thường chứa:

```text
META-INF/services/javax.annotation.processing.Processor
```

với một dòng:

```text
example.GreetingProcessor
```

Với cơ chế này, cần cấu hình processor search path/processing ở `javac` hoặc build tool phù hợp. File service registration **không thay thế yêu cầu cấu hình explicit trên JDK 23+**. Ví dụ chính dùng `-processor` nên **không cần** tạo descriptor trên.

Với dự án Maven/Gradle, hãy khai báo processor như **annotation processor dependency** riêng biệt, cố định toolchain và phiên bản processor thay vì trộn dependency của processor vào runtime dependencies của ứng dụng.

## 5. Annotation processing diễn ra qua nhiều rounds

Một processor không phải chỉ được chạy một lần. Khi sinh source hoặc class file, compiler có thể đưa những type mới thành đầu vào của vòng xử lý kế tiếp.

Ví dụ:

```text
Round 1:
  Root elements: Demo (@GenerateGreeting)
  Processor -> HelloGenerated.java + message.txt

Round 2:
  Compiler thấy HelloGenerated là source mới
  Processor được gọi tiếp dù có thể không có @GenerateGreeting mới

Final round:
  roundEnv.processingOver() == true
  Không còn round xử lý mới dành cho source/class sinh tiếp
```

### Quy tắc cần nhớ

- `roundEnv.processingOver()` cho biết round cuối; **đừng sinh source/class kỳ vọng compiler sẽ xử lý ở một round kế tiếp sau round cuối**.
- `roundEnv.errorRaised()` cho biết lỗi được báo ở round trước; điều này giúp processor tránh sinh output không hợp lệ tiếp.
- Một processor có thể được gọi ở các round tiếp theo ngay cả khi `annotations.isEmpty()`. Đừng giả định `process` chỉ chạy khi thấy annotation.
- Nếu mỗi round đều tạo cùng file, lần tạo thứ hai sẽ vấp `FilerException`. Biến `generated` trong ví dụ bảo vệ đúng trường hợp một output cố định.
- Với code generator nhiều file, dùng danh sách/tập output names riêng, không chỉ một boolean dùng chung cho mọi element.
- Các source/class sinh ra theo `createSourceFile` hoặc `createClassFile` được môi trường processing ghi nhận phù hợp với loại artifact; resource tạo qua `createResource` **không kích hoạt processing round chỉ vì có tên giống `.java`**.
- Đừng dùng `Files.writeString(Path.of("build/..."))` thay cho Filer nếu cần compiler và build tool theo dõi artifact do processor tạo ra.

Mỗi compilation invocation có một vòng đời processing riêng. Biến trạng thái trong processor chỉ cần quản lý trong phiên processor đó; không nên dùng static global cache dựa trên giả định sẽ không có nhiều compilation task hoặc classloader.

## 6. Quy tắc tạo tệp và `FilerException`

Theo hợp đồng Filer, **một pathname chỉ có thể được tạo một lần trong cùng một lần annotation processing**. Điều này bao gồm việc hai processor tranh cùng output name hoặc một processor gọi `createSourceFile` lặp lại ở các round.

Các tình huống thường gây `FilerException`:

1. Gọi `createSourceFile("demo.Generated")` hai lần trong một lần processing.
2. Cố tạo `.java` và `.class` cho **cùng tên type** trong cùng invocation.
3. Cố ghi đè type đã nằm trong input source/class files của compilation invocation.
4. Truyền tên type hoặc resource không hợp lệ.
5. Target module của file được sinh ra không thể xác định hoặc không được phép ghi, khi xử lý trong môi trường module.

Một lưu ý dễ hiểu sai: `Filer` có thể xóa/ghi lại một output **đã tồn tại từ lần build trước** khi tạo tệp đó *lần đầu trong invocation mới*, tùy file manager. Điều này **không cho phép processor cố ý ghi đè source do developer duy trì hoặc file không do processor tạo**. Không dùng Filer như một công cụ chỉnh sửa file người dùng. Hãy sinh artifact vào vùng output do build tool quản lý.

### Vì sao cần đóng Writer/OutputStream?

Khi gọi `createSourceFile` hoặc `createResource`, processor mới nhận handle để ghi nội dung. Nếu không đóng stream, output có thể không được hoàn thiện, compiler có thể không nhìn thấy source đúng thời điểm hoặc build thất bại. Dùng:

```java
try (Writer writer = file.openWriter()) {
    writer.write(content);
}
```

Đây là mẫu code **minh họa**, với `file` và `content` đã có trong processor. Đừng mở cả `openWriter()` lẫn `openOutputStream()` để ghi cùng một output, và đừng tạo nhiều handles rồi ghi đè không kiểm soát.

### Báo lỗi thay vì che giấu lỗi

`FilerException` là subtype của `IOException`. Một processor có thể bắt riêng để đưa thông báo rõ ràng:

```java
try {
    // createSourceFile hoặc createResource ...
} catch (javax.annotation.processing.FilerException e) {
    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.ERROR, "Duplicate generated output: " + e.getMessage());
} catch (IOException e) {
    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.ERROR, "I/O generating output: " + e.getMessage());
}
```

Đây là **đoạn minh họa**, chưa phải method độc lập; trong ứng dụng thật cần log ngữ cảnh tên file, annotation/element gây lỗi và phân loại tình huống phù hợp. Đừng im lặng bỏ qua duplicate nếu nó thể hiện một bug trong generator: output có thể thiếu hoặc sai.

## 7. `originatingElements` và incremental builds

Cả ba phương thức tạo output đều có tham số varargs `Element... originatingElements`.

```java
JavaFileObject source = filer.createSourceFile(
        "demo.generated.HelloGenerated", origin);
FileObject resource = filer.createResource(
        StandardLocation.CLASS_OUTPUT,
        "demo.generated",
        "message.txt",
        origin);
```

`origin` ở đây là `Element` của `demo.Demo` đã mang annotation và **gây ra việc sinh output**. Thông tin này có thể giúp các hệ thống build incremental hiểu source nào liên quan đến artifact nào, từ đó quyết định chạy lại processor/xóa output khi input thay đổi.

- Nên truyền element nguyên nhân một cách chính xác, không truyền bừa mọi element.
- Có thể truyền nhiều elements nếu artifact tổng hợp phụ thuộc vào nhiều source; cần cân nhắc giới hạn incremental processing của build tool.
- `originatingElements` là **thông tin nguồn gốc**, không phải nội dung file, không phải quyền truy cập filesystem và không tự bảo đảm mọi build tool sẽ hỗ trợ incremental chính xác.
- Với output sinh từ một global registry hoặc nhiều input, tài liệu build tool có thể yêu cầu phân loại processor kiểu *aggregating* thay vì *isolating*; cách khai báo phụ thuộc hệ thống build, không nằm trong `Filer` thuần.
- Nếu build tool không dùng thông tin nguồn gốc, tính đúng đắn của generated source vẫn không thay đổi.

## 8. Tài nguyên gì nên sinh qua `createResource`?

Ngoài `message.txt`, có thể dùng cho:

| Loại resource | Ví dụ | Lưu ý |
| --- | --- | --- |
| Metadata | `META-INF/services/com.example.Service` | Chỉ tạo khi công cụ của bạn thực sự cần Java SPI descriptor; tránh đăng ký class không tồn tại. |
| Cấu hình | `META-INF/mytool/index.json` | Định nghĩa format và khả năng tương thích phiên bản. |
| Schema | `schema/generated.json` | Cần serialization/escaping hợp lệ, không viết chuỗi JSON bằng cách ghép thủ công thiếu kiểm soát. |
| Danh mục | `generated/known-types.txt` | Tránh nội dung phụ thuộc vào iteration order không xác định. |
| Resource runtime | `demo/generated/message.txt` | Chọn `CLASS_OUTPUT` để có thể đóng gói cùng class files. |

**Hai câu hỏi chọn location:**

1. Resource có cần được tải lúc chạy bằng classloader? Thường chọn `CLASS_OUTPUT`.
2. Resource chỉ phục vụ lần sinh nguồn/để developer kiểm tra? Xem xét `SOURCE_OUTPUT` và quy định của build tool; tách rõ runtime artifact với source artifact.

`createResource` không sinh type mới, vì vậy việc đặt tên `"Example.java"` trong resource sẽ không khiến compiler tự biên dịch nó. Muốn tạo source Java, gọi `createSourceFile`; muốn tạo classfile hợp lệ, gọi `createClassFile`.

Khi resource được đưa vào JAR, bạn có thể kiểm tra bằng `jar tf app.jar` hoặc đọc bằng `ClassLoader.getResourceAsStream(...)`. Trong JPMS, resource trong module còn chịu các quy tắc truy cập/đóng gói resource của module; cách đọc bằng classloader của ví dụ chỉ minh họa **classpath**.

## 9. Source output và class output khác nhau ra sao?

- **`SOURCE_OUTPUT`** chứa generated Java sources hoặc tài nguyên đi cùng generated source; `javac -s <directory>` cho phép chọn nơi đặt sources do annotation processor tạo.
- **`CLASS_OUTPUT`** chứa `.class` và resource cần đi cùng compiled classes; `javac -d <directory>` chỉ định nơi đặt class output.
- Với project multi-module/JPMS, output có thể được tổ chức theo module. Filer hỗ trợ tên type với module prefix trong tình huống thích hợp, nhưng **không nên ép tất cả module cùng ghi vào một package/output path tùy tiện**. Cần đọc đúng module-location contract trước khi hỗ trợ một processor modular.
- Không lấy đường dẫn output thật bằng cách giả định mọi môi trường đều có `build/classes` hoặc `target/classes`. Dùng `Filer` và build tool để quyết định placement.
- Ghi `createSourceFile` với tên type hợp lệ; compiler có thể quyết định output path và các round.
- Ghi `createClassFile` với bytes đúng format; compiler không chuyển text Java thành bytecode chỉ vì tên output có đuôi class.

Ví dụ minh họa điều chỉnh thư mục output khi chạy `javac`:

```bash
javac --release 17 -processorpath build/processor -processor example.GreetingProcessor -s build/generated-sources -d build/classes src/app/demo/GenerateGreeting.java src/app/demo/Demo.java src/app/demo/App.java
```

**Đoạn lệnh này cần tạo sẵn thư mục `build/generated-sources`** hoặc bảo đảm toolchain tạo thư mục tương ứng, đồng thời có processor class đã biên dịch như mục 3. Khi dùng `-s`, `HelloGenerated.java` sẽ ở `build/generated-sources/demo/generated/`, trong khi `HelloGenerated.class` và `message.txt` vẫn thuộc `CLASS_OUTPUT`.

## 10. Vấn đề an toàn và độ tin cậy của code generation

Một annotation processor **là code thực thi trong quá trình build**. Không coi processor nhận từ dependency không đáng tin là “dữ liệu chỉ để đọc”. Các thực hành nên áp dụng:

1. Chỉ cấu hình **processor đã được kiểm duyệt** trong compiler/build tool; tách processor dependencies khỏi runtime dependencies.
2. Dùng `-processor` hoặc processor path/module path tường minh; từ JDK 23+, `javac` có chính sách không tự động chạy processor khi thiếu cấu hình xử lý.
3. Sinh output vào location do Filer quản lý, **không sửa** code do người dùng viết, config riêng hoặc tệp ngoài build output.
4. Đặt tên type và resource hợp lệ; nếu tên xuất phát từ annotation parameters, validate và sanitize trước khi tạo.
5. Escape Java literals, Unicode, JSON, XML hoặc nội dung resource được sinh theo format tương ứng. Dùng builder/template có test thay vì nối chuỗi tùy tiện.
6. Giữ codegen **deterministic**: cùng input/configuration nên cho output giống nhau. Không để timestamp, locale, hash iteration hay randomness quyết định file naming nếu không cần.
7. Dùng `Messager` báo lỗi cho annotation element gây vấn đề để developer sửa được nhanh; không nuốt exception.
8. Test với **clean build**, **incremental build** và nhiều round; xác nhận output cũ không bị giữ ngoài ý muốn khi xóa annotation.
9. Đóng file handles, giới hạn lượng source/resource sinh ra, tránh recursion vô hạn tạo tên type mới qua mỗi round.
10. Thực hiện kiểm tra code được sinh ra dưới cùng Java release/toolchain mục tiêu, không chỉ biên dịch processor thành công.

## 11. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân phổ biến | Cách xử lý |
| --- | --- | --- |
| `javac` không chạy processor trên JDK 23+ | Không có cấu hình annotation processing tường minh. | Dùng `-processor` cùng processor path như ví dụ hoặc cấu hình build tool thích hợp. |
| `Annotation processor not found` | Class processor chưa biên dịch, tên `-processor` sai hoặc thiếu processor path. | Kiểm tra `GreetingProcessor.class` và `-processorpath`. |
| `FilerException: Attempt to recreate a file` | Tạo cùng tên file ở hai round/processor, hoặc cố sinh output trùng input type. | Đảm bảo tên output duy nhất; có state chống ghi trùng trong một invocation. |
| `cannot find symbol: HelloGenerated` | Processor không chạy, generated source không được đóng hoặc source sai package/name. | Kiểm tra round, log `Messager`, output source và tham số `javac`. |
| `resource missing` lúc runtime | Resource không được đóng gói vào class output/JAR hoặc path tải resource sai. | Kiểm tra `CLASS_OUTPUT`, `jar tf`, classpath/module resource accessibility. |
| Có `.java` nhưng không có `.class` | Generated Java source không hợp lệ hoặc compile thất bại. | Xem diagnostics của compiler; sinh đúng package, class name và cú pháp Java. |
| File `.class` không hợp lệ | Dùng `createClassFile` nhưng ghi text/source hay bytecode sai version/format. | Sinh bytes bằng thư viện/API classfile hỗ trợ target, kiểm thử `javap` và Java runtime. |
| `createResource` bị từ chối | Tên relative không hợp lệ, output location không writable hoặc file trùng. | Dùng relativeName hợp lệ, location chuẩn và chỉ tạo một lần. |
| Build incremental không cập nhật output | Thiếu/khai báo sai originating elements hoặc generator không deterministic. | Truyền `Element` gây output; cấu hình build tool và test incremental. |
| Hai processor tạo cùng metadata | Cả hai ghi một pathname, gây `FilerException`. | Phối hợp trách nhiệm sinh resource hoặc dùng cơ chế hợp nhất do build tool quản lý. |
| Processor cố tạo file trong round cuối | Không còn round tiếp theo để xem source mới. | Sinh sớm khi còn annotation đầu vào, kiểm tra `processingOver()`. |
| Code generator làm sửa file người dùng | Dùng `Files.write` tùy tiện ngoài output folder. | Dùng `Filer`; không overwrite code không do generator sở hữu. |

## 12. Bài tập mở rộng

**Bài tập A — thay đổi nội dung resource.** Trong processor mục 3, đổi `writer.write("resource from Filer\n")` thành nội dung khác, clean output rồi biên dịch lại. Dự đoán stdout từ `App`; giải thích vì sao runtime đọc resource từ `CLASS_OUTPUT`.

**Bài tập B — tạo source theo từng element.** Thay vì chỉ một `HelloGenerated`, đánh dấu hai class bằng annotation rồi sinh tên type duy nhất theo `Element.getSimpleName()`. Dùng `originatingElements` của từng class để tạo nguồn gốc tương ứng. Viết test chạy cùng task và kiểm tra không phát sinh `FilerException`.

**Bài tập C — hiểu trùng output.** Bỏ biến `generated` và cố ý tạo cùng source/resource ở nhiều round. Quan sát compiler diagnostics thay vì dùng behavior đó trong production; khôi phục guard. Không sửa source của người dùng để “xử lý” duplicate.

**Bài tập D — output riêng.** Thêm `-s build/generated-sources` và xác nhận source ở thư mục mới nhưng `.class`/resource được đặt theo class output. Đóng gói JAR rồi dùng `jar tf` kiểm tra resource.

**Bài tập E — processor không tự chạy.** Trên JDK 23+, thử lệnh compile không cấu hình processing explicit và so sánh với `-processor`. Tập trung vào chính sách và tính an toàn, tránh suy luận rằng annotation chỉ có mặt trong source là compiler sẽ tự chạy codegen.

## 13. Câu hỏi kiểm tra kiến thức

**Câu 1.** Khi muốn tạo Java source `demo.generated.HelloGenerated`, dùng `createSourceFile("demo/generated/HelloGenerated.java")` được không?

**Đáp án:** Không đúng hợp đồng tên. `createSourceFile` nhận canonical fully qualified type name, nên dùng `"demo.generated.HelloGenerated"`; compiler quyết định đường dẫn `.java`.

**Câu 2.** Vì sao ví dụ không gọi `createClassFile` để tạo `HelloGenerated.class`?

**Đáp án:** `createSourceFile` đã sinh `HelloGenerated.java`; compiler tự biên dịch source được tạo sang classfile. `createClassFile` chỉ dành cho trường hợp processor đã có bytecode hợp lệ muốn ghi trực tiếp.

**Câu 3.** Tạo `createResource(CLASS_OUTPUT, "demo.generated", "message.txt")` có tạo thêm một processing round không?

**Đáp án:** Không chỉ vì resource đó. Resource bình thường không được đăng ký như source/class mới để compiler phân tích annotation; source/class mới sinh theo Filer mới có vai trò trong các round.

**Câu 4.** `FilerException` thường báo điều gì?

**Đáp án:** Thường là tạo lại pathname/type đã được tạo trong cùng annotation processing invocation, hoặc tên/output không hợp lệ. Cần tìm nguyên nhân trùng hoặc sai input, không tự nuốt exception.

**Câu 5.** Vì sao nên truyền `originatingElements`?

**Đáp án:** Để gắn output với element gây ra nó, giúp hệ thống build incremental có thông tin phụ thuộc; không tự đảm bảo mọi build tool đều tận dụng thông tin đó.

**Câu 6.** Tại sao trên JDK 23+ cần khai báo processor tường minh?

**Đáp án:** Vì `javac` không còn mặc định chạy annotation processors chỉ vì chúng tình cờ xuất hiện trên classpath khi không có cấu hình xử lý. Cần cấu hình `-processor`, processor path/module path hoặc chế độ `-proc` thích hợp.

## 14. Tài liệu chính thức và tiếp tục học

- [Filer — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/annotation/processing/Filer.html): quy tắc tạo source/class/resource, hạn chế tạo trùng và `originatingElements`.
- [FilerException — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/annotation/processing/FilerException.html): ngoại lệ của môi trường file generation.
- [AbstractProcessor — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): base class cho custom processor.
- [RoundEnvironment — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): các round và element annotations.
- [ProcessingEnvironment — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html): lấy Filer, Messager, Elements/Types utilities.
- [The javac Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): `-processor`, `--processor-path`, `-proc`, `-s` và `-d`.
- [JDK 23 Release Notes — annotation processing default](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html): thay đổi cần cấu hình annotation processing tường minh.

**Ghi nhớ:** `Filer` là cổng tạo artifact do compiler quản lý trong annotation processing. Dùng **`createSourceFile`** khi sinh Java source để javac biên dịch tiếp, **`createClassFile`** khi thực sự có bytecode hợp lệ và **`createResource`** để ghi dữ liệu không phải type. Gắn đúng originating elements, không tạo trùng trong một run, xử lý rounds/FilerException và cấu hình processor rõ ràng trên JDK hiện hành.
