# JSR 269 và sinh, kiểm tra mã ở thời điểm biên dịch

## 1. JSR 269 là gì và giải quyết bài toán nào?

**JSR 269 (Pluggable Annotation Processing API)** là cơ chế chuẩn của Java SE cho phép công cụ biên dịch gọi các **annotation processor** để xem mô hình mã nguồn, kiểm tra quy tắc và tạo thêm source/class/resource ngay trong quá trình biên dịch. API này tiếp tục được dùng trong Java hiện đại, kể cả khi nhãn chủ đề trong lộ trình là Java 6.

Hai trường hợp sử dụng cốt lõi:

- **Code generation:** Từ một class có `@GenerateGreeting("Xin chao")`, processor tạo `GreeterGenerated.java` có phương thức `message()`. Java compiler tiếp tục biên dịch file mới thành `GreeterGenerated.class` trong cùng compilation invocation.
- **Compile-time validation:** Nếu giá trị annotation trống, processor gửi `Diagnostic.Kind.ERROR`, khiến compilation thất bại với thông báo gắn vào khai báo sai. Lỗi được phát hiện ở build thay vì đợi chương trình chạy.

Các API chính vẫn nằm trong namespace `javax` được Java SE hỗ trợ:

| Package | Công cụ chính | Vai trò |
| --- | --- | --- |
| `javax.annotation.processing` | `Processor`, `AbstractProcessor`, `ProcessingEnvironment`, `RoundEnvironment`, `Filer`, `Messager` | Giao thức processor, nhiều vòng xử lý, sinh tệp và thông báo lỗi. |
| `javax.lang.model.element` | `Element`, `TypeElement`, `ExecutableElement`, `VariableElement`, `ElementKind` | Đại diện các khai báo class, method, field trong mã nguồn. |
| `javax.lang.model.type` | `TypeMirror` | Đại diện kiểu Java, kể cả các class đang được biên dịch. |
| `javax.lang.model.util` | `Elements`, `Types` | Tra cứu phần tử, so sánh và kiểm tra quan hệ kiểu. |
| `javax.tools` | `JavaFileObject`, `Diagnostic`, `JavaCompiler` | Đối tượng file và tích hợp với compiler. |

**Lưu ý:** Java SE dùng `javax.annotation.processing`, không phải `jakarta.annotation.processing`. Đừng tự đổi namespace JSR 269 chỉ vì một số thư viện Jakarta EE đổi sang `jakarta.*`.

Bài học này dùng **Java 17+**, có chương trình chạy được, giải thích các vòng xử lý, cách triển khai processor, sinh file và báo lỗi, cùng cấu hình phù hợp với thay đổi của `javac` từ JDK 23.

## 2. Annotation processing nằm ở bước nào?

```text
.java ban đầu
 └─ Greeter.java: @GenerateGreeting("Xin chao")
             │
             ▼
        javac / compiler
             │
             ├─ phân tích khai báo, xây Element / TypeMirror
             └─ chọn và gọi GreetingProcessor.process(...)
                    │
                    ├─ kiểm tra dữ liệu annotation
                    │     └─ sai -> Messager ERROR -> compile thất bại
                    │
                    └─ hợp lệ -> Filer.createSourceFile(...)
                                   └─ GreeterGenerated.java
                                         │
                                         ▼
                                  vòng xử lý kế tiếp
                                         │
                                         ▼
                                 biên dịch source gốc
                                 và source được sinh
                                         │
                                         ▼
                                      .class
```

Processor không cần khởi động ứng dụng, không thực thi `main()` và không dùng runtime reflection để đọc những class chưa được biên dịch. Nó đọc **compile-time model** do compiler cung cấp.

### Phân biệt bốn hoạt động dễ nhầm

1. **Annotation metadata:** `@interface` định nghĩa dữ liệu gắn lên code; bản thân annotation không tự sinh file hoặc báo lỗi.
2. **JSR 269 processor:** Java code được công cụ biên dịch lựa chọn và chạy lúc compile; có thể sinh *file mới* và diagnostic.
3. **Runtime reflection:** Đọc annotation sau khi class đã được load, chỉ có thể thấy annotation với retention thích hợp như `RUNTIME`.
4. **AST/bytecode rewriting:** Chỉnh cấu trúc source/bytecode hiện có bằng compiler extension hoặc bytecode tool; đây không phải chức năng chuẩn của `Filer`/JSR 269.

JSR 269 **không cho phép processor tùy tiện sửa file nguồn hiện có** theo hợp đồng công khai. Một bộ code generator portable nên sinh lớp mới, adapter, mapper, validator hoặc resource thông qua `Filer`.

## 3. Chính sách JDK hiện hành: phải cấu hình annotation processing rõ ràng

Từ **JDK 23**, `javac` không còn mặc định chạy mọi processor chỉ vì chúng xuất hiện trên classpath mà không có cấu hình xử lý annotation. Cơ chế này giúp giảm các processor vô tình chạy trong build. Các cách cấu hình rõ ràng gồm:

- `-processor demo.processor.GreetingProcessor`: chỉ định processor class cụ thể.
- `--processor-path path` (hoặc `-processorpath path`): nơi tìm processor.
- `--processor-module-path path`: nơi tìm processor triển khai dưới dạng module JPMS.
- `-proc:full`: yêu cầu annotation processing rồi compile; `-proc:only`: chỉ processing; `-proc:none`: tắt processing.

Ví dụ đáng tin cậy và tương thích JDK 17+:

```bash
javac --release 17 -cp build/processor \
  --processor-path build/processor \
  -processor demo.processor.GreetingProcessor \
  -s build/generated -d build/classes \
  app/demo/app/Greeter.java app/demo/app/Main.java
```

`-processor` loại bỏ sự phụ thuộc vào thứ tự/quy tắc tự động khám phá. `--processor-path` chứa class processor và dependency của nó. `-cp` cho source ứng dụng thấy annotation API. `-s` chỉ đường dẫn source được sinh, `-d` chỉ đường dẫn compiled class.

Đối với build tool như Gradle hay Maven, phải cấu hình processor dependency/path và processor selection có chủ đích. Không dựa vào implicit classpath scanning từ các workflow cũ trước JDK 23.

## 4. Những thành phần quan trọng của API

### 4.1. `Processor` và `AbstractProcessor`

`Processor` là interface xác định vòng đời: framework khởi tạo processor, gọi `init(ProcessingEnvironment)`, xem metadata mà processor hỗ trợ rồi gọi `process(Set<? extends TypeElement>, RoundEnvironment)`. `AbstractProcessor` là lớp nền tiện ích nên dùng cho processor thông thường.

```java
@SupportedAnnotationTypes("demo.api.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        // Duyệt các phần tử được annotate, kiểm tra, sinh file.
        return true;
    }
}
```

Đoạn này là **khung processor**; ví dụ phần 6 có đầy đủ imports và implementation.

`@SupportedAnnotationTypes` khai báo **tên đầy đủ** của annotation được xử lý. `@SupportedSourceVersion(RELEASE_17)` phù hợp với compilation target `--release 17` của ví dụ. Nếu dự án hỗ trợ ngôn ngữ Java phiên bản khác, phải xem xét source version mà processor công bố; không vô tình dùng cú pháp mới hơn target.

`process(...)` trả `true` nghĩa là processor **claim** những annotation types được yêu cầu xử lý để những processor khác không tiếp tục được hỏi về cùng types ấy trong quá trình tìm processor. `true` **không có nghĩa toàn bộ compilation thành công**; một lỗi `Messager.ERROR` vẫn khiến compiler thất bại.

### 4.2. `ProcessingEnvironment`

`AbstractProcessor` giữ `protected processingEnv` sau `init(...)`. Từ đó gọi:

| API | Công việc |
| --- | --- |
| `processingEnv.getFiler()` | Tạo source/class/resource file mới. |
| `processingEnv.getMessager()` | Gửi error/warning/note gắn với source. |
| `processingEnv.getElementUtils()` | Tra package, type, symbol và metadata của các elements. |
| `processingEnv.getTypeUtils()` | So sánh, xét assignability/erasure của `TypeMirror`. |
| `processingEnv.getOptions()` | Đọc options được truyền qua `-Akey=value`. |
| `processingEnv.getSourceVersion()` | Xem source version của môi trường xử lý. |

### 4.3. `RoundEnvironment`

`roundEnv.getElementsAnnotatedWith(GenerateGreeting.class)` cung cấp những elements có annotation mục tiêu trong vòng hiện tại. `roundEnv.getRootElements()` là các phần tử gốc được đưa vào vòng đó. `processingOver()` báo **vòng cuối**; `errorRaised()` phản ánh lỗi ở vòng trước theo hợp đồng API.

Processor có thể được gọi **nhiều lần trong một invocation javac**; vì vậy code không nên giả định `process` chỉ chạy một lần.

### 4.4. `Element` và `TypeMirror` thay cho reflection

Ví dụ:

```java
if (element.getKind() == ElementKind.CLASS) {
    TypeElement type = (TypeElement) element;
    String simpleName = type.getSimpleName().toString();
    String pkg = processingEnv.getElementUtils()
            .getPackageOf(type).getQualifiedName().toString();
}
```

Đây là **đoạn minh họa trong processor**; `element` đã được cung cấp từ `RoundEnvironment`. `TypeElement` không phải `Class<?>`, vì class đang compile có thể chưa có bytecode để load.

Để kiểm tra field/method, duyệt `type.getEnclosedElements()`, phân loại bằng `ElementKind` rồi cast sang `VariableElement` hoặc `ExecutableElement`. Với kiểu Java và generics, sử dụng `TypeMirror` và `Types`. Tránh so sánh kiểu bằng `toString()` hoặc gọi `Class.forName` trên source của người dùng.

## 5. Processing rounds và quy tắc sinh file

Annotation processing chạy qua các **vòng**:

1. **Vòng đầu:** compiler phân tích nguồn đầu vào, tìm annotation, gọi processor phù hợp.
2. **Processor sinh source:** ví dụ `Filer.createSourceFile("demo.app.GreeterGenerated", origin)`; processor ghi nội dung và đóng `Writer`.
3. **Vòng tiếp theo:** source được sinh tham gia phân tích tiếp; processor có thể được gọi lại. Các annotation mới trong generated source có thể được xử lý trong vòng sau.
4. **Vòng kết thúc:** `roundEnv.processingOver() == true`; processor có thể tổng kết nhưng không nên sinh file mới.
5. **Biên dịch:** nếu không chọn `-proc:only` và không có lỗi, compiler tạo class files từ nguồn ban đầu và nguồn đã sinh.

Code ứng xử với vòng cuối:

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {

    if (roundEnv.processingOver()) {
        return true;
    }
    for (Element e :
            roundEnv.getElementsAnnotatedWith(GenerateGreeting.class)) {
        // Tạo source mới từ element thực sự trong vòng hiện tại.
    }
    return true;
}
```

Đừng gọi `createSourceFile` vô điều kiện mỗi vòng. `Filer` sẽ phát hiện cố tạo **cùng đường dẫn/tên output** nhiều lần trong một compilation invocation và có thể ném `FilerException`.

### Vì sao phải dùng `Filer` và đóng `Writer`?

`Filer` đăng ký output với compiler để generated sources được xử lý ở vòng tiếp theo. Nếu code processor tự ghi file vào `src/main/java` bằng `Files.writeString`, compiler/build tool không nhất thiết quản lý file đó như generated source hợp lệ, còn dễ vô tình sửa mã developer.

`Filer` hỗ trợ:

- `createSourceFile(name, originatingElements...)`: file nguồn Java mới.
- `createClassFile(name, originatingElements...)`: class file mới.
- `createResource(location, pkg, relativeName, originatingElements...)`: resource khác.
- `getResource(location, pkg, relativeName)`: đọc resource trong location thích hợp.

**Originating elements** giúp thể hiện quan hệ giữa source ban đầu và output, hữu ích cho build tools/incremental compilation. `createSourceFile` cần **fully qualified name**, ví dụ `demo.app.GreeterGenerated`, không phải đường dẫn `demo/app/GreeterGenerated.java`.

`Filer` không được thiết kế để ghi đè tệp source ban đầu hay cùng một generated file nhiều lần. Nếu có hai annotation yêu cầu tạo cùng binary name, hãy báo lỗi hoặc đặt tên không xung đột, đừng nuốt `FilerException`.

## 6. Ví dụ chạy được: sinh source và kiểm tra annotation trong JDK 17+

Ví dụ có bốn file Java ban đầu: annotation, processor, class được gắn annotation và main. Nó sinh thêm `GreeterGenerated.java`, biên dịch class đó và chạy `message()`. Processor cũng kiểm tra dữ liệu sai.

### 6.1. Cấu trúc thư mục

```text
jsr269-demo/
├── src/
│   └── demo/
│       ├── api/
│       │   └── GenerateGreeting.java
│       └── processor/
│           └── GreetingProcessor.java
├── app/
│   └── demo/
│       └── app/
│           ├── Greeter.java
│           └── Main.java
├── bad/
│   └── demo/
│       └── app/
│           └── Bad.java
└── build/
    ├── processor/       # classes của annotation/processor
    ├── classes/         # class files ứng dụng
    └── generated/       # Java source do Filer tạo
```

### 6.2. `src/demo/api/GenerateGreeting.java`

```java
package demo.api;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateGreeting {
    String value();
}
```

`@Target(TYPE)` cho phép annotation trên các khai báo kiểu tương ứng; processor sẽ kiểm tra thêm yêu cầu **phải là class**. `@Retention(SOURCE)` phù hợp vì annotation chỉ cần được đọc khi compile, không cần reflection runtime. `value()` cho phép cú pháp `@GenerateGreeting("Xin chao")`.

### 6.3. `src/demo/processor/GreetingProcessor.java`

```java
package demo.processor;

import demo.api.GenerateGreeting;
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

@SupportedAnnotationTypes("demo.api.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        if (roundEnv.processingOver()) {
            return true;
        }
        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateGreeting.class)) {
            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@GenerateGreeting requires a class", element);
                continue;
            }
            TypeElement type = (TypeElement) element;
            String value = type.getAnnotation(GenerateGreeting.class).value();
            if (value.isBlank()) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Greeting text must not be blank", element);
                continue;
            }

            String pkg = processingEnv.getElementUtils()
                    .getPackageOf(type).getQualifiedName().toString();
            String simpleName = type.getSimpleName() + "Generated";
            String binaryName = pkg.isEmpty()
                    ? simpleName : pkg + "." + simpleName;

            try {
                JavaFileObject output = processingEnv.getFiler()
                        .createSourceFile(binaryName, type);
                try (Writer writer = output.openWriter()) {
                    if (!pkg.isEmpty()) {
                        writer.write("package " + pkg + ";\n");
                    }
                    writer.write("public final class " + simpleName + " {\n");
                    writer.write("  private " + simpleName + "() {}\n");
                    writer.write("  public static String message() {\n");
                    writer.write("    return \"" + escape(value) + "\";\n");
                    writer.write("  }\n}\n");
                }
            } catch (IOException e) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot create " + binaryName + ": " + e.getMessage(),
                        element);
            }
        }
        return true;
    }

    private static String escape(String value) {
        return value.replace("\\", "\\\\")
                    .replace("\"", "\\\"")
                    .replace("\n", "\\n")
                    .replace("\r", "\\r")
                    .replace("\t", "\\t");
    }
}
```

**Phân tích luồng xử lý:**

1. `@SupportedAnnotationTypes` đăng ký đúng tên đầy đủ của annotation; `@SupportedSourceVersion(RELEASE_17)` nhất quán với `--release 17`.
2. `getElementsAnnotatedWith` tìm các phần tử được gắn annotation trong mỗi vòng.
3. `ElementKind.CLASS` từ chối interface/loại khai báo không hợp lệ; `value.isBlank()` từ chối chuỗi rỗng hoặc toàn khoảng trắng.
4. `Messager.printMessage(ERROR, ..., element)` tạo compiler diagnostic tại vị trí người dùng có thể sửa.
5. `getPackageOf` và `getSimpleName` tạo tên `demo.app.GreeterGenerated`; `Filer.createSourceFile` tạo file mới gắn với originating element `type`.
6. `try (Writer ...)` đảm bảo đóng file đã sinh để compiler có thể xử lý ở các vòng tiếp theo.
7. `return true` claim annotation type; việc báo `ERROR` vẫn khiến toàn bộ compilation thất bại.

`escape` trong ví dụ xử lý backslash, dấu nháy, newline, carriage return và tab. Với code generator production chấp nhận dữ liệu tùy ý, cần encoder Java string literal tổng quát hơn (bao gồm mọi control character và các trường hợp Unicode đặc biệt), đồng thời test riêng.

Quy tắc đặt tên của demo dành cho **top-level class names không va chạm**. Với nested classes, overload names và output dùng chung, cần chính sách đặt tên unique; processor hiện tại sẽ báo error nếu `Filer` từ chối output trùng.

### 6.4. `app/demo/app/Greeter.java`

```java
package demo.app;
import demo.api.GenerateGreeting;

@GenerateGreeting("Xin chao")
public final class Greeter {}
```

### 6.5. `app/demo/app/Main.java`

```java
package demo.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println(GreeterGenerated.message());
    }
}
```

Dù lúc đầu chưa có `GreeterGenerated.java`, javac có thể biên dịch `Main` trong cùng lần xử lý: processor tạo source ở một round, rồi compiler phân tích/biên dịch source đã sinh.

### 6.6. Biên dịch và chạy trên Linux/macOS

Chạy tại thư mục `jsr269-demo`:

```bash
mkdir -p build/processor build/classes build/generated

javac --release 17 -d build/processor \
  src/demo/api/GenerateGreeting.java \
  src/demo/processor/GreetingProcessor.java

javac --release 17 \
  -cp build/processor \
  --processor-path build/processor \
  -processor demo.processor.GreetingProcessor \
  -s build/generated \
  -d build/classes \
  app/demo/app/Greeter.java \
  app/demo/app/Main.java

java -cp build/classes demo.app.Main
```

### 6.7. Biên dịch và chạy trên Windows PowerShell

Không cần dùng cú pháp nối dòng; nhập các lệnh sau riêng rẽ:

```powershell
New-Item -ItemType Directory -Force build/processor,build/classes,build/generated | Out-Null
javac --release 17 -d build/processor src/demo/api/GenerateGreeting.java src/demo/processor/GreetingProcessor.java
javac --release 17 -cp build/processor --processor-path build/processor -processor demo.processor.GreetingProcessor -s build/generated -d build/classes app/demo/app/Greeter.java app/demo/app/Main.java
java -cp build/classes demo.app.Main
```

**Stdout từ ứng dụng:**

```text
Xin chao
```

Sau khi biên dịch thành công, bạn có những file:

```text
build/generated/demo/app/GreeterGenerated.java
build/classes/demo/app/Greeter.class
build/classes/demo/app/GreeterGenerated.class
build/classes/demo/app/Main.class
```

**Nội dung generated source tương ứng:**

```java
package demo.app;
public final class GreeterGenerated {
  private GreeterGenerated() {}
  public static String message() {
    return "Xin chao";
  }
}
```

`-s build/generated` là nơi `Filer` ghi **generated Java source**, còn `-d build/classes` là nơi compiler ghi **class files**. Không cần gọi javac lần thứ ba để compile `GreeterGenerated.java`; compiler đưa generated source vào những bước xử lý tiếp theo của invocation thứ hai.

Tách bước build processor và bước build application giúp bảo đảm implementation processor đã tồn tại khi javac cần load và chạy nó. Dùng `-processor` và `--processor-path` làm hành vi ổn định trên JDK 17, 21, 23 và các bản mới hơn.

## 7. Kiểm thử negative case: annotation sai phải làm build thất bại

Tạo `bad/demo/app/Bad.java`:

```java
package demo.app;
import demo.api.GenerateGreeting;

@GenerateGreeting("   ")
public final class Bad {}
```

Sau khi đã build processor ở phần 6, chạy:

```bash
mkdir -p build/bad build/bad-generated
javac --release 17 \
  -cp build/processor \
  --processor-path build/processor \
  -processor demo.processor.GreetingProcessor \
  -s build/bad-generated -d build/bad \
  bad/demo/app/Bad.java
```

Trên PowerShell, tạo thư mục tương ứng và chạy lệnh javac này **trên một dòng**, giữ nguyên các tham số.

**Kết quả:** javac kết thúc khác 0 và ghi diagnostic chứa:

```text
error: Greeting text must not be blank
```

Với fixture đã kiểm thử trên OpenJDK 24, compiler báo `1 error`, exit code `1`. Đường dẫn, dòng/cột in ra còn phụ thuộc nơi đặt file; không lấy toàn bộ stderr làm expected output cố định. Test nên kiểm tra build fail và thông báo hoặc `Diagnostic.Kind.ERROR`.

Nếu annotation được đặt trên interface, processor cũng sẽ báo lỗi với nội dung `@GenerateGreeting requires a class`. Cơ chế này giúp xác định lỗi ngay trong IDE/CI thay vì đợi khi class chạy.

## 8. `Messager` và cách thiết kế validation

`Messager` là đường báo diagnostic đúng của JSR 269:

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Greeting text must not be blank",
        element);
```

Khác biệt giữa các mức:

| Kind | Cách dùng |
| --- | --- |
| `ERROR` | Vi phạm điều kiện bắt buộc, compilation thất bại. |
| `WARNING` | Cảnh báo mà compilation vẫn có thể thành công. |
| `MANDATORY_WARNING` | Cảnh báo bắt buộc theo công cụ. |
| `NOTE` | Ghi chú hỗ trợ debug/build logs. |

Ưu tiên overload nhận `Element` để compiler gắn vị trí lỗi vào source. Khi cần vị trí cụ thể trong annotation, có những overload gắn `AnnotationMirror` và `AnnotationValue`.

Dùng `System.out.println` để báo lỗi chỉ in chữ và **không thay đổi kết quả build**. Dùng `Messager.ERROR` nếu muốn chặn mã sai.

### Kiểm tra kiểu, modifier và phần tử lồng nhau

`Element` có `getKind()` và `getModifiers()`. Với method:

```java
if (element.getKind() == ElementKind.METHOD) {
    ExecutableElement method = (ExecutableElement) element;
    boolean isPrivate =
            method.getModifiers().contains(Modifier.PRIVATE);
    boolean noArguments = method.getParameters().isEmpty();
}
```

Đây là **đoạn minh họa**, cần import `ExecutableElement` và `Modifier`; không phải một file độc lập. `TypeElement.getEnclosedElements()` cho phép duyệt field/method/nested type. Khi cần kiểm tra subtype, dùng `Types.isAssignable(...)` hoặc `Types.isSubtype(...)` trên `TypeMirror`, không so sánh tên kiểu như chuỗi.

Một annotation có thành viên kiểu `Class<?>` có thể được đọc qua `AnnotationMirror` và `TypeMirror`. Cố lấy giá trị class bằng proxy reflection có thể ném `MirroredTypeException` vì class đích chưa được load; đó là lý do API mô hình kiểu của compiler hữu ích.

## 9. Filer, source output và lỗi trùng

`Filer.createSourceFile(binaryName, originatingElements...)` là điểm tạo Java source mới. Với `demo.app.GreeterGenerated`, Filer ghi file theo cấu hình `-s`; đóng writer thì source mới được đưa vào round sau.

Các lỗi quan trọng:

- **Trùng output name:** Hai annotated types cùng yêu cầu một binary name, hoặc code tạo lại file trong hai rounds, có thể gây `FilerException`.
- **Trùng file với input source:** `Filer` có giới hạn không ghi đè file source/class đầu vào.
- **Thiếu đóng writer:** source có thể chưa được coi là tạo xong, dẫn đến xử lý vòng sau không đúng.
- **Ghi trực tiếp vào cây source của user:** gây mất ownership, làm build khó tái lập và có thể làm hỏng file developer.
- **Source không đúng cú pháp:** file generated vẫn phải tuân theo source version đang được compiler sử dụng; processor không miễn trừ lỗi Java syntax.
- **Generated Java string chưa escape:** dấu nháy, backslash và ký tự điều khiển có thể khiến file generated không compile được.

Đối với processor sinh một file từ nhiều annotated elements, hãy tập hợp và sắp xếp dữ liệu theo khóa ổn định rồi **tạo file đúng một lần**. Đừng phụ thuộc thứ tự iteration của Set/HashMap.

## 10. Tùy chọn `-proc`, processor path và service registration

### Các option nên biết

| Option | Ý nghĩa |
| --- | --- |
| `-processor a.b.MyProcessor` | Chọn processor implementation cụ thể. |
| `--processor-path path` | Cung cấp classpath dùng để load processors. |
| `--processor-module-path path` | Cung cấp processor module path trong mô hình JPMS. |
| `-proc:none` | Không chạy annotation processors. |
| `-proc:only` | Xử lý annotations nhưng không làm bước compile class bình thường. |
| `-proc:full` | Annotation processing rồi compile. |
| `-s dir` | Output cho generated Java source. |
| `-d dir` | Output cho class files. |
| `--release 17` | Mức nguồn/API/bytecode mục tiêu của compiler. |
| `-Akey=value` | Processor-specific options đọc từ `processingEnv.getOptions()`. |

Nếu muốn cung cấp processor trong JAR và để build tool tìm qua `ServiceLoader`, thêm resource:

```text
META-INF/services/javax.annotation.processing.Processor
```

Với nội dung:

```text
demo.processor.GreetingProcessor
```

File này phải được package cùng processor implementation. Nhưng **khả năng tìm thấy processor không đồng nghĩa compiler sẽ tự động chạy nó**: từ JDK 23 cần yêu cầu processing rõ ràng. Demo dùng `-processor` nên không cần file service.

Khi package processor thành JPMS module, có thể khai báo service provider bằng `provides javax.annotation.processing.Processor with ...` và cấu hình `--processor-module-path`. Đừng đánh đồng processor module path với application module path.

### Gradle và Maven

Trong Gradle, thường tách module chứa annotation API khỏi module triển khai processor:

```groovy
dependencies {
    compileOnly project(":greeting-annotations")
    annotationProcessor project(":greeting-processor")
}
```

Đây chỉ là **ý tưởng cấu hình dependencies**; project thật cần khai báo các subprojects, dependencies của processor, service registration hoặc compiler arguments để chỉ định processor. Maven có thể cấu hình processor paths/dependencies và tên processors qua compiler plugin. Điểm cần duy trì là **processor được chọn tường minh** và version của nó được quản lý như dependency build.

## 11. Source version, vòng đời và reproducibility

`@SupportedSourceVersion(SourceVersion.RELEASE_17)` thông báo processor hỗ trợ source 17; ví dụ dùng `--release 17` để đồng nhất. Nếu build thực tế dùng source 21 hoặc 25 nhưng processor vẫn khai báo chỉ hỗ trợ 17, javac có thể cảnh báo supported source version thấp hơn target. Khi thiết kế processor đa phiên bản, cân nhắc override `getSupportedSourceVersion()` và kiểm thử trên các target được công bố; không tự khẳng định code generated hợp lệ cho mọi Java release.

Một instance processor thông thường được dùng xuyên các rounds trong **một compilation run**. Không mặc định một processor object mới được tạo mỗi round. Nếu duy trì trạng thái để tạo index/registry, cần biết vòng nào có dữ liệu và vòng nào kết thúc. Khi build lại nhiều lần, đừng đặt kết quả trong biến `static` rồi coi đó là nguồn dữ liệu chuẩn.

**Khả năng build lặp lại** yêu cầu:

- Cùng source/annotation/options → cùng generated files.
- Thứ tự sinh ổn định, không phụ thuộc iteration ngẫu nhiên.
- Tên output có quy tắc tránh va chạm.
- Chỉ một owner cho mỗi output file.
- Generated sources nằm trong output directory do build tool quản lý.
- Có test khi source thay đổi hoặc annotation bị xóa để bảo đảm build không dùng stale generated artifacts.

`Filer` theo dõi file của compilation hiện tại, nhưng không thay thế toàn bộ hệ thống incremental build. Maven/Gradle quyết định caching, incremental recompilation và cleanup theo plugin/task semantics.

## 12. Bảo mật và quyền thực thi của processor

Annotation processor **là mã Java được thực thi trong build process**, có thể đọc tài nguyên, truy cập mạng hoặc thực hiện hoạt động tương ứng quyền của JVM/compiler. `-proc:none` hoặc chính sách JDK 23 giảm **chạy vô tình**, nhưng không phải sandbox cho processor được chọn.

Chỉ thêm processor đáng tin; pin version; review dependency và quyền của build agent; tránh chạy processor không rõ nguồn trên source/project bí mật. Không giả định annotation source do người dùng nhập là dữ liệu an toàn để chèn thẳng vào Java source do processor tạo.

## 13. Kiểm thử đầy đủ trong CI

| Test | Kỳ vọng |
| --- | --- |
| `@GenerateGreeting("Xin chao")` | Generated `GreeterGenerated.java` tồn tại, compiled class tồn tại, `message()` trả đúng text. |
| `@GenerateGreeting("   ")` | Javac thất bại, có `Diagnostic.Kind.ERROR`. |
| Gắn annotation trên interface | Có error `requires a class`. |
| Nhiều annotated classes | Sinh đúng một output duy nhất cho mỗi class, không có tên trùng. |
| Generated file tạo lại trong cùng invocation | Processor phải tránh trùng, không bỏ qua `FilerException`. |
| Annotation String có `"`, `\`, tab, newline | Generated source vẫn là Java hợp lệ sau escaping. |
| Thay đổi processor path | Chỉ processor đã cấu hình được thực thi. |
| Build trên JDK 23+ | Không phụ thuộc annotation processing mặc định từ classpath. |
| Nhiều rounds | File generated được compiler nhận và biên dịch đúng. |
| Class sai kiểu hoặc thiếu dependency | Diagnostic rõ nguyên nhân, build thất bại. |

Với test programmatic qua `JavaCompiler` và `DiagnosticCollector`, có thể kiểm tra:

```java
boolean success = Boolean.TRUE.equals(task.call());
boolean hasError = diagnostics.getDiagnostics().stream()
        .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);
```

Đây là **đoạn minh họa** dùng `task` và `diagnostics` đã được khởi tạo, không phải chương trình độc lập. Dự án nên assert `success` cho positive case và `!success && hasError` cho negative case; không cố định toàn bộ văn bản diagnostic vì phiên bản JDK/locale/path có thể làm nó khác nhau.

Để quan sát rounds khi debug, `javac` có `-XprintRounds` và `-XprintProcessorInfo`. Không nên lấy log debug từ các option này làm hợp đồng ổn định giữa các bản JDK.

## 14. Các lỗi thường gặp cần tránh

1. **Chỉ định nghĩa `@interface` rồi chờ code được sinh.** Annotation cần processor được load và chạy mới có tác dụng.
2. **Quên cấu hình processing trên JDK 23+.** Dùng `-processor`, processor path hoặc `-proc` theo thiết kế.
3. **Biên dịch processor cùng lúc với nguồn cần xử lý nó.** Hãy build processor artifact trước khi compile ứng dụng.
4. **Dùng runtime reflection cho source đang compile.** Đọc `Element`, `TypeMirror` thay vì cố `Class.forName`.
5. **Quên `processingOver()`.** Không tạo file ở final round; chú ý processor có thể chạy nhiều rounds.
6. **Trả `true` và tưởng mọi thứ hợp lệ.** `true` chỉ claim annotation; diagnostic ERROR vẫn làm build fail.
7. **Nuốt lỗi `IOException`/`FilerException`.** Báo lỗi gắn vào originating element; tránh tạo artifact thiếu dữ liệu.
8. **Ghi source trực tiếp vào `src/main/java`.** Dùng `Filer` để tool biết về generated sources.
9. **Không đóng writer.** Dùng `try-with-resources`, bảo đảm generated file hoàn tất.
10. **Đặt output name theo simple name mà không xử lý collision.** Với nested class hoặc nhiều origin, nên có naming policy rõ.
11. **Nhầm `@Retention(SOURCE)` với annotation không thể xử lý.** Processor hoạt động ở compile-time nên SOURCE vẫn được nhận diện.
12. **Dùng `TypeMirror.toString()` như phép so sánh kiểu.** Sử dụng `Types.isSameType`, `isAssignable` hoặc API tương ứng.
13. **Sinh code thiếu escaping.** Kiểm thử các ký tự đặc biệt trước khi ghi literal vào file Java.
14. **Giả định generated class sẽ tồn tại ngay trước khi javac chạy.** Nó được tạo trong rounds, phải cấu hình processor để compiler nhận.
15. **Bỏ qua nguồn gốc và tính xác định của generated files.** Passing originating elements, sắp xếp ổn định và tests giúp build dễ bảo trì.
16. **Cho rằng processor được sandbox bởi compiler.** Processor có khả năng chạy code trong build, cần quản lý trust và dependencies.

## 15. Câu hỏi tự kiểm tra

**1. Annotation processing chạy khi nào?**  
Trong lúc biên dịch. Không cần khởi chạy `main` và không dùng runtime reflection trên bytecode đã tải.

**2. `Filer.createSourceFile` có sửa file gốc được không?**  
Không. Nó tạo file nguồn **mới** được compiler đăng ký, có quy tắc chống trùng.

**3. Source generated ở một round có được biên dịch trong cùng invocation javac không?**  
Có, nếu task được cấu hình processing và compilation bình thường, không dùng `-proc:only`.

**4. `roundEnv.processingOver()` giúp gì?**  
Nhận biết vòng cuối, tránh tạo source/class mới ở giai đoạn không còn round xử lý kế tiếp.

**5. `process(...)` trả `true` và gửi `ERROR` thì build thế nào?**  
Build thất bại. `true` chỉ nghĩa claim các annotation types.

**6. `@Retention(SOURCE)` có đủ cho processor không?**  
Có. Annotation được compiler xử lý trong source, không cần giữ ở runtime.

**7. Vì sao dùng `TypeElement` thay vì `Class<?>`?**  
Class đang compile có thể chưa load được; `TypeElement` là mô hình mã nguồn/kiểu phù hợp tại compile-time.

**8. Trên JDK 23+, chỉ để processor JAR trên classpath có bảo đảm nó chạy không?**  
Không. Cần processor configuration rõ ràng.

**9. Vì sao truyền `type` vào `createSourceFile(binaryName, type)`?**  
Để ghi nhận originating element, hữu ích cho quản lý output và incremental build.

**10. Từ source hợp lệ, ai tạo `GreeterGenerated.class`?**  
Processor tạo `GreeterGenerated.java`, còn **Java compiler** biên dịch source ấy thành `.class`.

## Tài liệu API chính thức còn hiệu lực

- [Java SE 26 — `javax.annotation.processing`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/package-summary.html).
- [Java SE 26 — `Processor`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/Processor.html), [`AbstractProcessor`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html).
- [Java SE 26 — `ProcessingEnvironment`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html), [`RoundEnvironment`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html).
- [Java SE 26 — `Filer`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/Filer.html), [`Messager`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/Messager.html).
- [Java SE 26 — `Element`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/Element.html), [`TypeMirror`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html).
- [Java SE 26 — lệnh `javac`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html), gồm `-processor`, `--processor-path`, `-proc`, `-s` và `-d`.
- [Oracle JDK 23 Release Notes — annotation processing disabled by default](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html), xác nhận việc yêu cầu cấu hình tường minh từ JDK 23.

JSR 269 vẫn là con đường tiêu chuẩn để **sinh các Java source mới và phát hiện lỗi hợp đồng ngay tại compile-time**. Một processor tốt sử dụng mô hình `Element`/`TypeMirror`, tạo output qua `Filer`, báo lỗi qua `Messager`, xử lý rounds đúng cách và được cấu hình minh bạch để hoạt động ổn định trên những JDK đang được hỗ trợ.
