# Messager và thông báo gắn vào phần tử nguồn trong Annotation Processing (Java 17+)

## 1. Messager giải quyết vấn đề gì?

Trong **Java Annotation Processing**, processor kiểm tra mã nguồn thông qua mô hình `Element` và `AnnotationMirror`. Khi annotation không hợp lệ, nếu chỉ gọi `System.out.println(...)` hoặc ném một exception chung, developer khó biết **file nào, dòng nào, annotation hoặc giá trị nào** đang sai. Cơ chế chính thức dành cho việc báo lỗi là **`javax.annotation.processing.Messager`**.

`Messager` cho phép processor xuất **error**, **warning**, **mandatory warning** hoặc **note** theo định dạng mà công cụ biên dịch và IDE có thể tiếp nhận. Quan trọng hơn, processor có thể truyền **`Element`, `AnnotationMirror` và `AnnotationValue`** làm *gợi ý vị trí nguồn*, giúp thông báo gắn với khai báo, annotation hoặc thuộc tính trong annotation cụ thể.

Ví dụ khai báo:

```java
@Label("  ")
class Sample {}
```

Nếu `@Label.value()` không được để trống, một processor tốt cần chỉ vào giá trị chuỗi `"  "`, thay vì chỉ báo mơ hồ rằng “config is invalid”.

**Ý chính:** `Messager` là một phần của **Annotation Processing API hiện vẫn được hỗ trợ trên Java 17+**. Processor nhận đối tượng từ `ProcessingEnvironment.getMessager()` và gọi trong quá trình `process(...)`. Thông báo có thể được javac in ra, IDE gạch chân hoặc Java Compiler API thu qua `DiagnosticListener`.

Mục tiêu:
1. Phân biệt `Messager` với `System.out`, exception và `DiagnosticCollector`.
2. Hiểu bốn overload `printMessage(...)` và độ chính xác vị trí.
3. Phân biệt các loại `Diagnostic.Kind` và tác động của `ERROR`.
4. Lấy `Element`, `AnnotationMirror` và `AnnotationValue` hợp lệ để báo lỗi trúng chỗ.
5. Chạy ví dụ Java 17+ có **warning ở khai báo class** và **error tại giá trị annotation**.
6. Tích hợp processor trong Gradle/Maven và kiểm thử diagnostics đáng tin.

## 2. Messager nằm ở đâu trong pipeline javac?

```text
                Nguồn Java
                    |
             JavaCompiler / javac
                    |
                Processor
        (AbstractProcessor.process)
                    |
         ProcessingEnvironment
               /         \
    ElementUtils/Types   Messager
              |             |
          Element           +-- NOTE / WARNING / ERROR
          AnnotationMirror       |
          AnnotationValue        +-- vị trí source hint:
                                  element / annotation / value
                                        |
                                 DiagnosticListener
                                  / DiagnosticCollector
                                        |
                            IDE, console, build log, CI
```

Các kiểu cần biết:

| API | Vai trò |
| --- | --- |
| `AbstractProcessor` hoặc `Processor` | Điểm mở rộng xử lý annotation trong các **round** của compiler. |
| `ProcessingEnvironment` | Cấp công cụ của processor, trong đó có `getMessager()`, `getElementUtils()`, `getTypeUtils()` và `getFiler()`. |
| `Messager` | Báo lỗi/cảnh báo/ghi chú, có thể gắn *source position hint*. |
| `Element` | Mô hình một khai báo, như class, method, field, parameter. |
| `AnnotationMirror` | Mô hình một annotation áp dụng trên element. |
| `AnnotationValue` | Mô hình giá trị thành phần của annotation. |
| `Diagnostic.Kind` | Phân loại mức độ thông báo: `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, `OTHER`. |
| `DiagnosticCollector` | Công cụ **phía gọi compiler**, thu kết quả diagnostic từ compilation task. |

Bên trong processor:

```java
Messager messager = processingEnv.getMessager();
messager.printMessage(
        Diagnostic.Kind.ERROR,
        "The annotated declaration is invalid",
        element);
```

Đây là **snippet**, không phải chương trình độc lập: `element` phải là `Element` đã lấy từ compiler round hiện tại. `processingEnv` do `AbstractProcessor` quản lý sau khi processor được khởi tạo qua `init(...)`; không cần tự tạo đối tượng `Messager`.

Một công cụ compile dùng Java Compiler API có thể cung cấp `DiagnosticCollector<JavaFileObject>` trong `JavaCompiler.getTask(...)`. Khi processor gọi `Messager.printMessage(...)`, diagnostic trở thành một phần của kết quả compiler; không có hợp đồng bắt buộc rằng nội dung đó phải xuất hiện trực tiếp trên `System.err`.

## 3. Bốn overload printMessage: chọn mức gắn vị trí

Java SE 17 và các bản Java mới vẫn cung cấp các overload này:

| Overload | Gợi ý vị trí | Khi nào chọn |
| --- | --- | --- |
| `printMessage(kind, msg)` | Không gắn khai báo cụ thể | Lỗi/cảnh báo chung của processor, cấu hình toàn cục. |
| `printMessage(kind, msg, element)` | Khai báo của `Element` | Sai tên class, method, field hoặc cấu trúc của một phần tử. |
| `printMessage(kind, msg, element, annotationMirror)` | Annotation nằm trên element | Sai annotation hoặc quan hệ giữa các annotation. |
| `printMessage(kind, msg, element, annotationMirror, annotationValue)` | Giá trị cụ thể bên trong annotation | Sai chuỗi/số/enum/class trong thuộc tính của annotation. |

Các chữ ký thực tế:

```java
void printMessage(Diagnostic.Kind kind, CharSequence msg);

void printMessage(Diagnostic.Kind kind, CharSequence msg,
                  Element e);

void printMessage(Diagnostic.Kind kind, CharSequence msg,
                  Element e, AnnotationMirror a);

void printMessage(Diagnostic.Kind kind, CharSequence msg,
                  Element e, AnnotationMirror a, AnnotationValue v);
```

Bốn dòng trên là **khai báo API**, không phải các phương thức tự viết trong cùng class.

**Ràng buộc quan trọng:**
- `e` phải mô tả phần tử thực sự liên quan đến lỗi.
- `a` phải là annotation mirror được áp dụng trên chính `e`.
- `v` phải là giá trị thuộc annotation `a`, không phải object `String` thông thường hoặc giá trị giả do ứng dụng tự dựng.
- Các đối tượng đó nên được lấy từ **mô hình compiler đang xử lý**. Không giữ rồi tái sử dụng `Element`/`AnnotationMirror` từ một compilation task khác.

Độ chính xác là **gợi ý vị trí**, không phải bảo đảm tọa độ tuyệt đối. Theo API, công cụ có thể không tìm được vị trí hoặc chỉ định vị gần đúng, nhất là phần tử lấy từ compiled class, annotation được tổng hợp, giá trị mặc định không hiện trong source, hoặc các compiler/IDE khác nhau.

Ví dụ cùng một lỗi:

```java
messager.printMessage(
        Diagnostic.Kind.ERROR, "Invalid label");

messager.printMessage(
        Diagnostic.Kind.ERROR, "Invalid label", element);

messager.printMessage(
        Diagnostic.Kind.ERROR, "Invalid label", element, mirror);

messager.printMessage(
        Diagnostic.Kind.ERROR, "Invalid label", element, mirror, value);
```

Đây là **snippet minh họa**: `messager`, `element`, `mirror` và `value` phải được lấy từ processor và phải chỉ đến cùng quan hệ element–annotation–value hợp lệ. Khi có thể, ưu tiên overload **chi tiết nhất phù hợp vấn đề**, vì IDE và compiler có thêm dữ liệu để trỏ đến vị trí nguồn.

## 4. Diagnostic.Kind: loại thông báo và tác động

| Kind | Ý nghĩa | Cách dùng phù hợp |
| --- | --- | --- |
| `ERROR` | Lỗi biên dịch do processor báo. | Annotation không đáp ứng ràng buộc bắt buộc; compilation phải thất bại. |
| `WARNING` | Cảnh báo thông thường; biên dịch có thể tiếp tục. | Hành vi đáng ngờ hoặc cấu hình không khuyến khích nhưng chưa bắt buộc sửa. |
| `MANDATORY_WARNING` | Cảnh báo phải được công cụ báo theo hợp đồng diagnostic. | Vấn đề được đánh dấu là cần thông báo bắt buộc theo quy tắc tool. Không dùng để thay `ERROR`. |
| `NOTE` | Ghi chú/thông tin bổ trợ. | Thông tin ngắn, có ích khi debug; tránh quá nhiều dòng. |
| `OTHER` | Thông báo không thuộc bốn nhóm trên. | Hiếm khi hữu ích cho validation nghiệp vụ; ưu tiên kind rõ nghĩa. |

Các nguyên tắc:
- Gọi `messager.printMessage(Diagnostic.Kind.ERROR, "...", e)` **đánh dấu lỗi compiler**, thay vì cần ném exception để dừng processor. Processor nên tiếp tục an toàn để báo thêm lỗi có ích trong cùng lượt.
- Một warning **không mặc định làm compilation thất bại**, nhưng cấu hình build như `-Werror` có thể nâng warning thành lỗi.
- Lỗi có thể được IDE báo trực quan hoặc được tool thu lại; đừng đánh giá mức độ thành công bằng cách tìm kiếm chuỗi “error” trong console.
- `NOTE` không nên chứa dữ liệu bí mật hoặc source người dùng có thông tin nhạy cảm. Build logs thường được lưu trên CI.
- Không bắt buộc có đúng một diagnostic cho một lỗi logic, nhưng nên **tránh trùng** cùng thông báo qua nhiều round.

## 5. Lấy Element, AnnotationMirror và AnnotationValue đúng cách

Thông thường, `process(...)` được truyền tập `TypeElement` đại diện annotation được xử lý và `RoundEnvironment`. Có thể lấy các phần tử liên quan bằng:

```java
for (TypeElement annotation : annotations) {
    for (Element element :
            roundEnv.getElementsAnnotatedWith(annotation)) {
        // element là khai báo sử dụng annotation đó
    }
}
```

Đây là snippet đặt trong phương thức `process(...)`. Không nên dùng reflection runtime như `Class.getAnnotation(...)` để phân tích source: annotation processor hoạt động trên **mô hình biên dịch**, bao gồm cả class chưa được tạo bytecode.

Để tìm annotation cụ thể trên element:

```java
for (AnnotationMirror mirror : element.getAnnotationMirrors()) {
    if (!mirror.getAnnotationType().asElement()
            .equals(annotation)) {
        continue;
    }
    // mirror tương ứng với TypeElement của annotation đang xử lý
}
```

Đoạn này cũng là snippet, biến `annotation` là `TypeElement` của annotation; `element` là khai báo trong compiler round hiện tại.

Để lấy giá trị viết tường minh trong annotation:

```java
for (var entry : mirror.getElementValues().entrySet()) {
    if (entry.getKey().getSimpleName().contentEquals("value")) {
        AnnotationValue value = entry.getValue();
        Object raw = value.getValue();
        // Kiểm tra raw theo kiểu tương ứng của annotation member.
    }
}
```

`getElementValues()` chỉ trả các giá trị **được ghi tường minh** trong annotation. Nếu muốn áp dụng cả default values, dùng `processingEnv.getElementUtils().getElementValuesWithDefaults(mirror)` để lấy kết quả logic hoàn chỉnh. Tuy vậy, default value **không xuất hiện ở source sử dụng annotation**, nên không thể kỳ vọng diagnostic trỏ vào một literal không tồn tại. Khi giá trị mặc định dẫn tới lỗi, hãy gắn lỗi vào annotation hoặc element.

**Đừng ép tất cả `AnnotationValue` thành `String`.** Giá trị có thể là primitive, `String`, enum constant, `TypeMirror`, nested annotation hoặc list giá trị (array). Xử lý theo hợp đồng kiểu annotation, ví dụ dùng `instanceof String` khi member khai báo `String value()`.

## 6. Chương trình Java 17+ chạy được: diagnostic trỏ đến class và literal

Ví dụ này nằm trong **một file** `MessagerDemo.java`. Nó:
1. Tạo nguồn Java ảo chứa annotation `@Label("  ")` và class `Sample`.
2. Dùng `JavaCompiler` gọi annotation processor trực tiếp bằng `task.setProcessors(...)`.
3. Processor phát `WARNING` gắn với `Element` của class, và `ERROR` gắn với `AnnotationValue`.
4. `DiagnosticCollector` thu diagnostic, chương trình in kiểu, số dòng và thông điệp.

Cách này **không phụ thuộc processor discovery ngầm** và hoạt động trên JDK 17+. Chọn `--release 17` và `-proc:only` để chạy annotation processing mà không cần tạo `.class` cho source ví dụ.

### 6.1. Mã nguồn đầy đủ MessagerDemo.java

```java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.Messager;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.AnnotationMirror;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class MessagerDemo {

    @SupportedAnnotationTypes("demo.Label")
    @SupportedSourceVersion(SourceVersion.RELEASE_17)
    public static final class CheckProcessor extends AbstractProcessor {
        @Override
        public boolean process(
                Set<? extends TypeElement> annotations,
                RoundEnvironment round) {

            if (round.processingOver()) {
                return true;
            }

            Messager messager = processingEnv.getMessager();

            for (TypeElement annotation : annotations) {
                for (Element element :
                        round.getElementsAnnotatedWith(annotation)) {

                    // Cảnh báo gắn vào khai báo class Sample.
                    messager.printMessage(
                            Diagnostic.Kind.WARNING,
                            "checking " + element.getSimpleName(),
                            element);

                    for (AnnotationMirror mirror :
                            element.getAnnotationMirrors()) {
                        if (!mirror.getAnnotationType()
                                .asElement().equals(annotation)) {
                            continue;
                        }

                        for (var entry :
                                mirror.getElementValues().entrySet()) {

                            if (entry.getKey().getSimpleName()
                                    .contentEquals("value")
                                    && entry.getValue().getValue()
                                            instanceof String value
                                    && value.isBlank()) {

                                // Gắn lỗi vào literal "  " trong @Label.
                                messager.printMessage(
                                        Diagnostic.Kind.ERROR,
                                        "label must not be blank",
                                        element, mirror, entry.getValue());
                            }
                        }
                    }
                }
            }
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "A JDK with jdk.compiler is required");
        }

        String code = """
                package demo;
                @interface Label { String value(); }
                @Label("  ")
                class Sample {}
                """;

        JavaFileObject source = new SimpleJavaFileObject(
                URI.create("string:///demo/Sample.java"),
                JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(
                    boolean ignoreEncodingErrors) {
                return code;
            }
        };

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT,
                             StandardCharsets.UTF_8)) {

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null,
                    manager,
                    diagnostics,
                    List.of("--release", "17", "-proc:only"),
                    null,
                    List.of(source));

            // Chỉ định processor chủ động, không dựa vào auto-discovery.
            task.setProcessors(List.of(new CheckProcessor()));

            boolean compiled = Boolean.TRUE.equals(task.call());
            System.out.println("success=" + compiled);

            for (var diagnostic : diagnostics.getDiagnostics()) {
                if (diagnostic.getKind() == Diagnostic.Kind.WARNING
                        || diagnostic.getKind()
                                == Diagnostic.Kind.ERROR) {
                    System.out.println(
                            diagnostic.getKind()
                            + " line=" + diagnostic.getLineNumber()
                            + " message="
                            + diagnostic.getMessage(Locale.ROOT));
                }
            }
        }
    }
}
```

### 6.2. Biên dịch, chạy và stdout

Đứng trong thư mục chứa `MessagerDemo.java`, dùng **JDK 17 trở lên**:

```bash
javac MessagerDemo.java
java MessagerDemo
```

Với javac/JDK đã kiểm chứng, stdout chính xác:

```text
success=false
WARNING line=4 message=checking Sample
ERROR line=3 message=label must not be blank
```

**Vì sao dòng 4 và dòng 3?**
- Chuỗi `code` tạo source có dòng 1 là `package demo;`, dòng 2 là khai báo `@interface Label`, dòng 3 là `@Label("  ")` và dòng 4 là `class Sample {}`.
- Overload nhận `Element` báo warning vào khai báo `Sample` ở **dòng 4**.
- Overload nhận `Element, AnnotationMirror, AnnotationValue` báo lỗi vào **giá trị thuộc annotation ở dòng 3**.
- `success=false` là hợp lý vì processor đã phát `Diagnostic.Kind.ERROR`; không phải vì Java source sai cú pháp.
- `-proc:only` chạy processor mà không tạo class output của source `demo.Sample`. Nếu bỏ option này và dùng chế độ biên dịch đầy đủ, vẫn có thể nhận diagnostic, nhưng khi có `ERROR` task không thành công.

Thông báo, vị trí chính xác và thứ tự diagnostic có thể khác theo compiler/IDE, đặc biệt khi source được sinh hoặc vị trí không khả dụng. Output trên cố định cho **javac được dùng kiểm thử** với source này; ứng dụng production không nên so sánh nguyên văn toàn bộ câu chữ hoặc số dòng mà không kiểm soát compiler và source.

### 6.3. Thử nghiệm thay đổi code

Để xem trường hợp **không lỗi**, thay dòng annotation trong chuỗi source từ:

```java
@Label("  ")
```

thành:

```java
@Label("valid")
```

Hai dòng là snippet của **source bên trong text block**, không phải chương trình riêng. Khi chạy lại:
- Processor vẫn báo `WARNING` từ ví dụ (vì dòng warning được gọi vô điều kiện cho class được annotate).
- Không có `ERROR` “label must not be blank”.
- `task.call()` trả `true` trong môi trường compiler hợp lệ, kể cả khi dùng `-proc:only`.

Trong processor dùng thực tế, chỉ báo `WARNING` khi có vấn đề thực sự và cân nhắc tránh phát warning ở mọi phần tử như bản demo minh họa.

## 7. Báo lỗi vào annotation và annotation value một cách chính xác

Giả sử annotation có hai thuộc tính:

```java
@interface Route {
    String path();
    String method() default "GET";
}

@Route(path = "", method = "POST")
class Resource {}
```

Khi kiểm tra `path` rỗng, nên tìm `AnnotationMirror` của `Route` và `AnnotationValue` tương ứng với `path`, rồi dùng overload bốn đối số:

```java
messager.printMessage(
        Diagnostic.Kind.ERROR,
        "path must not be blank",
        resourceElement,
        routeMirror,
        pathAnnotationValue);
```

Đây là **snippet minh họa**, không độc lập: `resourceElement`, `routeMirror` và `pathAnnotationValue` được lấy từ model của compilation task hiện tại. Không gắn mọi lỗi vào class nếu có thể định vị chính xác thuộc tính annotation gây lỗi.

Nếu giá trị `method` sử dụng default `"GET"` và người viết chỉ ghi `@Route(path="/x")`, thì:
- `routeMirror.getElementValues()` **không có** entry `method` do nó không được viết tường minh.
- `Elements.getElementValuesWithDefaults(routeMirror)` có thể trả giá trị logic `"GET"`.
- Nếu default đó là nguyên nhân phát sinh lỗi, không có literal `method = "GET"` trên source khai báo `Resource` để trỏ vào; hãy đặt hint lên annotation/class và trình bày rõ nguyên nhân trong message.

Với annotation repeatable, phần tử có thể hiển thị qua container annotation; processor cần hỗ trợ container và cấu trúc mô hình tương ứng. Không giả định `getAnnotationMirrors()` luôn trả annotation lặp theo đúng một hình dạng trong mọi tình huống.

## 8. Tổ chức annotation processor thực tế

Ví dụ một processor thường được đóng gói thành JAR riêng:

```text
app/
  src/main/java/...
checks-api/
  src/main/java/demo/validation/Label.java
checks-processor/
  src/main/java/demo/validation/LabelProcessor.java
  src/main/resources/META-INF/services/
    javax.annotation.processing.Processor
```

**Những điểm thiết kế quan trọng:**
1. **Annotation API** và **processor implementation** là hai vai trò riêng. Code ứng dụng cần thấy annotation khi compile; bản processor chạy trong môi trường công cụ build.
2. Đăng ký processor bằng file `META-INF/services/javax.annotation.processing.Processor` chứa **tên đầy đủ của class processor** theo SPI chuẩn; hoặc chỉ định processor rõ ràng bằng `-processor`/`CompilationTask.setProcessors`. Nếu dùng named module, có thể khai báo `provides javax.annotation.processing.Processor with ...` theo JPMS.
3. Bộ build nên chọn **processor path/processor module path** riêng; không đặt processor tùy tiện vào runtime artifact.
4. Trong Gradle, sử dụng cấu hình `annotationProcessor`; với Maven, khai báo processor theo cấu hình phiên bản plugin đang dùng thay vì dựa vào processor bất kỳ trên application classpath.
5. Với JDK hiện đại, đặc biệt từ JDK 23 trở đi, **cấu hình annotation processing một cách tường minh** để tránh phụ thuộc vào cơ chế tự tìm processor ngầm. Nếu cần tắt hẳn processing, sử dụng `-proc:none`.

Ví dụ phần dependency trong **Gradle Groovy DSL**, với các project đã khai báo đúng:

```groovy
dependencies {
    compileOnly project(':checks-api')
    annotationProcessor project(':checks-processor')
}
```

Đây là **snippet build.gradle**, không phải Java code. Khi annotation cần ở runtime, dùng dependency scope phù hợp với `@Retention` và runtime architecture; `compileOnly` chỉ là ví dụ cho annotation dùng ở compile time. Nếu processor trực tiếp phụ thuộc annotation API, bản processor cần khai báo và đóng gói dependency đúng phía **processor classpath** của Gradle.

Với **Maven**, dùng cấu hình rõ ràng để khai báo annotation processor và đường tìm kiếm của nó theo phiên bản Maven Compiler Plugin được chọn, đồng thời bảo đảm annotation API có mặt trên compile classpath. Kiểm chứng bằng lệnh build thực tế và log processor: không được kết luận rằng JAR processor đã nằm trong dependencies thì processor sẽ chắc chắn được thực thi.

## 9. Khi nào dùng Messager, khi nào dùng exception hoặc logging?

| Nhu cầu | Công cụ phù hợp | Lý do |
| --- | --- | --- |
| Người dùng khai báo annotation sai | `Messager.printMessage(ERROR, ..., element, mirror, value)` | Đây là lỗi **nguồn Java của consumer**; nên chỉ rõ chỗ cần sửa. |
| Cảnh báo một field/method không tối ưu | `Messager.printMessage(WARNING, ..., element)` | IDE có thể gắn warning vào khai báo. |
| Thông tin chung về cấu hình processor | `Messager.printMessage(NOTE, ...)` | Có thể hiển thị trong compiler/IDE mà không gắn vào source. |
| Processor gặp lỗi môi trường không thể phục hồi | Exception có thông tin nguyên nhân; có thể thêm diagnostic thích hợp | Không phải mọi lỗi đều thuộc về annotation của người dùng. |
| Theo dõi hiệu năng, telemetry nội bộ | Logger của môi trường build (cẩn trọng) | Logging không thay thế diagnostics gắn vào source. |
| Ứng dụng gọi JavaCompiler muốn thu lỗi | `DiagnosticListener` hoặc `DiagnosticCollector` | Bên ngoài processor, lấy thông tin chuẩn về loại lỗi, file, line và message. |

Tránh lạm dụng `System.out.println` trong processor: stdout có thể không được IDE định tuyến thành lỗi, không có vị trí gắn nguồn, khó machine-read và làm nhiễu logs. Cũng tránh dùng `throw new IllegalArgumentException(...)` cho mỗi lỗi khai báo của developer: exception thường làm thất bại processor mà không gắn chính xác nguồn, thậm chí ngăn báo các lỗi khác.

## 10. Annotation processing có nhiều round

Processor có thể được gọi nhiều lần trong một compilation task. Khi processor sinh source mới bằng `Filer`, compiler có thể mở thêm round; cuối quá trình có round hoàn tất với `roundEnv.processingOver() == true`.

Vì vậy:
- Với thông báo gắn vào element, chỉ duyệt và báo lỗi cho các phần tử liên quan trong round hiện tại.
- Đừng giữ reference `Element` và `AnnotationMirror` cho các compilation task khác; đây là model của compiler environment.
- Cân nhắc việc mỗi round nhận các phần tử mới hay cũ, tránh lặp cùng một message cho cùng điều kiện.
- Trong final round, tránh cố tạo source mới khi processing sắp kết thúc; hãy tổng hợp diagnostic thật cần thiết.
- `roundEnv.errorRaised()` cho biết liệu một round trước đã có error được báo; processor có thể cân nhắc tránh phát sinh thêm output khi compilation đã không hợp lệ.
- Giá trị trả về của `process(...)` nói processor có **claim** các annotation đang xử lý hay không, không phải boolean compile success. **`return true` không thay thế `Messager(ERROR,...)`**, và `return false` không tự làm compilation thất bại.

Đoạn tham khảo:

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {

    if (roundEnv.processingOver()) {
        return true;
    }

    // Validate current round's annotated elements.
    // Use processingEnv.getMessager().printMessage(...) as needed.
    return true;
}
```

Đây là snippet của một subclass `AbstractProcessor` có cấu hình annotation types phù hợp. Phần chú thích mô tả chỗ đặt logic validation, không phải processor đầy đủ.

## 11. Kiểm thử diagnostics đúng cách

Chỉ gọi `javac` và tìm dòng có từ “error” là không đủ cho test compiler integration. Hãy kiểm tra bằng `JavaCompiler` và `DiagnosticCollector` hoặc một thư viện kiểm thử compiler phù hợp (nếu dự án đã dùng), dựa trên các thuộc tính có cấu trúc:

```java
boolean hasExpectedError = diagnostics.getDiagnostics()
        .stream()
        .anyMatch(d ->
                d.getKind() == Diagnostic.Kind.ERROR
                && d.getMessage(Locale.ROOT)
                        .contains("label must not be blank"));
```

Đây là **snippet** khi biến `diagnostics` đã tồn tại trong test. Kiểm tra thêm `task.call() == false` với validation error. Khi kiểm soát chính xác source string và compiler, có thể kiểm tra `getLineNumber()`, `getColumnNumber()` và `getSource()`; nhưng đừng giả định mọi compiler/IDE luôn trả cùng vị trí hoặc cùng định dạng message.

Một bộ kiểm thử tốt nên có:
- **Valid annotation**: không có `ERROR` và compilation thành công.
- **Invalid literal**: có `ERROR` đúng text, tốt nhất gắn `AnnotationValue` của member sai.
- **Sai khai báo element**: cảnh báo/lỗi gắn với `Element`.
- **Default value**: lỗi được mô tả đúng dù giá trị không được ghi tường minh trên source.
- **Nhiều lỗi trong cùng file**: processor không dừng ở lỗi đầu tiên, tránh diagnostic trùng bất ngờ.
- **Nhiều rounds**: tránh báo trùng hoặc sinh source sau final round.
- **Compiler/build integration**: processor thực sự chạy trên Java toolchain mục tiêu, kể cả khi cấu hình processor paths khác nhau.

Có thể dùng kiểm thử với **`-Werror`** để bảo đảm CI từ chối warning, nhưng không áp dụng máy móc: một demo như `MessagerDemo` cố tình có warning, vì vậy khi bật `-Werror` có thể thay đổi trạng thái compilation. Cần thống nhất chính sách cảnh báo của dự án.

## 12. Phân tích lỗi phổ biến

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Processor chạy nhưng chỉ có dòng chung không trỏ source | Gọi `printMessage(kind,msg)` không có `Element` | Gắn `Element` hoặc annotation/value phù hợp. |
| Error chỉ vào class thay vì literal annotation | Dùng overload 3 đối số trong khi có `AnnotationValue` | Lấy `AnnotationMirror` và member value, dùng overload chi tiết nhất. |
| Chọn overload 5 đối số nhưng vị trí vẫn gần đúng | Không có mapping nguồn chính xác, element đến từ classfile hoặc default value | Chấp nhận giới hạn API, mô tả context rõ trong message. |
| `getElementValues()` không thấy member có default | API chỉ trả member được ghi tường minh | Dùng `getElementValuesWithDefaults(...)` khi cần. |
| Processor không chạy | Chưa cấu hình processor path/module path, service provider hoặc processor explicit | Dùng `-processor` hoặc `task.setProcessors`; cấu hình Gradle/Maven tường minh. |
| `ERROR` làm build fail | Đây là hành vi đúng khi điều kiện validation bắt buộc bị vi phạm | Sửa annotation trong code người dùng; không bỏ qua lỗi. |
| Warning biến thành build failure | Build bật `-Werror` | Quyết định policy hoặc sửa warning, không đánh đổi bằng cách nuốt diagnostic. |
| Một lỗi bị báo nhiều lần | Logic chạy ở nhiều round hoặc duyệt chồng lặp | Giới hạn kiểm tra theo round/element; theo dõi trường hợp đã báo nếu cần. |
| Processor báo “class not found” với source chưa compile | Dùng reflection thay vì annotation model API | Dùng `TypeElement`/`TypeMirror` và `Elements`/`Types` của compile environment. |
| Dùng `System.out` thấy trong terminal nhưng IDE không đánh dấu | Không phải compiler diagnostic | Chuyển sang `Messager`. |
| Test fail vì message/line thay đổi giữa JDK | So khớp output javac quá cứng | Kiểm tra `Kind` và thông điệp do bạn kiểm soát; pin compiler khi cần kiểm tra vị trí chi tiết. |

## 13. Bảo đảm an toàn và hiệu quả của processor

1. **Xác minh logic model, không dựng lại AST bằng chuỗi:** sử dụng `Element`/`AnnotationMirror`/`AnnotationValue` thay cho regex quét source.
2. **Message ngắn và hành động được:** nêu điều kiện sai, tên annotation/member và cách sửa khi có thể. Ví dụ “@Label.value must be nonblank”.
3. **Không tiết lộ dữ liệu nhạy cảm:** nếu annotation chứa secret, tránh đưa literal thật vào `Messager` vì compiler/CI logs có thể lưu dài hạn.
4. **Chọn mức độ đúng:** `ERROR` cho constraint bắt buộc; `WARNING` cho vấn đề có thể tiếp tục; `NOTE` cho thông tin cần thiết.
5. **Kiểm soát source location hint:** chỉ truyền mirror/value thuộc element được xử lý; không giả định line/column được hỗ trợ cho mọi model.
6. **Không lạm dụng exception để báo lỗi người dùng:** dùng `Messager` để compiler và IDE thấy vị trí gắn nguồn.
7. **Cấu hình processor rõ ràng ở build:** đóng gói đúng processor JAR, processor path; kiểm thử trên compiler thực, tránh phụ thuộc discovery không kiểm soát.
8. **Thiết kế cho nhiều round:** không báo trùng, không giữ reference model lâu hơn compilation task, hiểu ý nghĩa `processingOver()` và `errorRaised()`.
9. **Không coi annotation processor là sandbox:** processor là Java code thực thi trong compiler/build process và có thể đọc/ghi tài nguyên theo quyền tiến trình; chỉ sử dụng processor từ nguồn đáng tin.
10. **Giữ tương thích phiên bản:** khai báo `@SupportedSourceVersion` phù hợp compiler target. Processor biên dịch bằng JDK mới cần được kiểm thử trên toolchain mà dự án thực tế sử dụng.

## 14. Câu hỏi ôn tập

**Câu 1.** Sự khác nhau giữa `printMessage(ERROR,"bad")` và `printMessage(ERROR,"bad", element)` là gì?

**Đáp án:** Cả hai đều báo lỗi, nhưng overload nhận `Element` cung cấp gợi ý để định vị lỗi ở khai báo nguồn liên quan.

**Câu 2.** Muốn đánh dấu literal của `@Label("  ")`, phải dùng overload nào?

**Đáp án:** `printMessage(kind, msg, element, annotationMirror, annotationValue)` với giá trị thuộc annotation mirror của chính element đó.

**Câu 3.** `getElementValues()` có trả member đang dùng giá trị default nhưng không được viết trong annotation không?

**Đáp án:** Không. Muốn lấy giá trị logic kèm default, dùng `Elements.getElementValuesWithDefaults(...)`; với default không có literal ở nơi sử dụng, vị trí gắn có thể không cụ thể.

**Câu 4.** Vì sao demo in `success=false` dù Java source `Sample` không sai cú pháp?

**Đáp án:** Processor cố ý phát `Diagnostic.Kind.ERROR` khi giá trị label chỉ có khoảng trắng; compiler đánh dấu compilation không thành công.

**Câu 5.** `process(...)` trả `false` có đồng nghĩa báo lỗi không?

**Đáp án:** Không. Giá trị đó nói về việc processor có nhận xử lý/claim annotations hay không; muốn báo validation error dùng `Messager`.

**Câu 6.** Lời gọi `System.err.println("error")` bên trong processor có tương đương `Messager.ERROR` không?

**Đáp án:** Không. In text thường không tạo compiler diagnostic có `Kind` và thông tin vị trí để IDE/test thu nhận.

## 15. Tài liệu chính thức

- [Java SE 17 — Messager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Messager.html): bốn overload và quy tắc location hint.
- [Java SE 17 — ProcessingEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html): cách processor nhận `Messager`, `Filer`, `Elements` và `Types`.
- [Java SE 17 — AbstractProcessor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): processor implementation.
- [Java SE 17 — RoundEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): các round và truy cập annotation trên elements.
- [Java SE 17 — AnnotationMirror](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationMirror.html): `getElementValues()` và xử lý annotation model.
- [Java SE 17 — Diagnostic](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html): `Kind`, vị trí và message.
- [JDK 25 — javac tool](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `-processor`, `--processor-path`, `-proc:only` và cách cấu hình processing hiện đại.
