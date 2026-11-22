# Annotation processor và phụ thuộc lúc biên dịch trong Java 17

Annotation trong Java có thể mang metadata để compiler, framework hoặc công cụ build xử lý. Một **annotation processor** là chương trình chạy trong quá trình biên dịch để đọc annotation, kiểm tra mã nguồn và có thể sinh thêm source file, class file hoặc resource.

Annotation processing là một phần của Java Compiler API (JSR 269), không phải cơ chế Reflection tại runtime. Khi cấu hình build, cần tách rõ ba nhóm phụ thuộc:

- **Compile-time dependency:** thư viện cần để compiler biên dịch mã nguồn, chẳng hạn annotation API mà source đang sử dụng.
- **Annotation processor dependency:** thư viện chứa processor và các dependency mà processor cần để chạy trong compiler.
- **Runtime dependency:** thư viện cần có khi ứng dụng thực thi, ví dụ class được sinh ra tham chiếu tới một API runtime.

Ba nhóm này có thể trùng nhau trong một số thư viện, nhưng vai trò của chúng khác nhau. Đặt nhầm processor vào runtime classpath hoặc thiếu annotation API ở compile classpath thường khiến build lỗi hoặc ứng dụng không chạy được.

## 1. Annotation processing là gì?

Annotation processor đọc các annotation trong source code và thực hiện công việc trong lúc compiler biên dịch. Các công việc phổ biến:

- Kiểm tra quy tắc sử dụng annotation và báo lỗi ngay khi compile.
- Sinh implementation, adapter, mapper, builder hoặc metadata.
- Sinh file đăng ký service, resource hoặc cấu hình.
- Tạo mã hỗ trợ serialization, dependency injection hoặc truy cập dữ liệu.
- Kiểm tra sự nhất quán giữa nhiều kiểu trong cùng một lần biên dịch.

Ví dụ, source có annotation:

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

Lập trình viên đánh dấu một class:

~~~java
package demo;

@GenerateGreeting
public class Example {
}
~~~

Một processor có thể phát hiện annotation `@GenerateGreeting` và sinh thêm class `ExampleGreeting` trong cùng package. Sau đó compiler tiếp tục biên dịch source vừa được sinh ra.

### 1.1. Processor chạy lúc compile, không phải mỗi lần chạy ứng dụng

~~~text
Source code + annotation API
          |
          v
       Compiler
          |
          +----> Annotation processor
          |          |
          |          +---- đọc annotation / model
          |          +---- kiểm tra mã nguồn
          |          +---- sinh source / resource
          |                       |
          +<----------------------+
          |
          v
   Các processing round tiếp theo
          |
          v
     Compile source cuối cùng
          |
          v
      .class files
          |
          v
    Chạy ứng dụng trên JVM
~~~

Processor không mặc nhiên được đóng gói vào ứng dụng. Nó thường chỉ cần thiết trong build. Những class và resource do processor tạo ra mới trở thành output của quá trình biên dịch.

### 1.2. Phân biệt annotation processing với Reflection

| Đặc điểm | Annotation processor | Reflection |
|---|---|---|
| Thời điểm | Trong quá trình biên dịch | Khi chương trình chạy |
| API chính | `javax.annotation.processing`, `javax.lang.model` | `java.lang.reflect` |
| Đầu vào | Element/model của source và type | Class/object đã được nạp |
| Có thể sinh source | Có, qua `Filer` | Không phải mục đích của Reflection |
| Có thể báo lỗi compile | Có, qua `Messager` | Không; lỗi xuất hiện khi runtime |
| Có cần annotation giữ đến runtime? | Không nhất thiết | Muốn đọc annotation bằng Reflection thì cần retention phù hợp |

Annotation có `RetentionPolicy.SOURCE` vẫn được processor xử lý vì annotation hiện diện trong source model ở lúc compile. Sau khi compile, annotation đó không được giữ trong class file.

## 2. API cốt lõi của annotation processor

Các kiểu quan trọng trong Java 17 nằm trong module `java.compiler`.

| API | Vai trò |
|---|---|
| `AbstractProcessor` | Lớp cơ sở tiện dụng để viết processor |
| `Processor` | Contract chính của một annotation processor |
| `ProcessingEnvironment` | Cung cấp compiler utilities, filer, messager và options |
| `RoundEnvironment` | Thông tin về annotation và element trong một processing round |
| `Element` | Đại diện class, method, field, parameter hoặc thành phần khai báo |
| `TypeElement` | Đại diện khai báo kiểu như class/interface |
| `TypeMirror` | Đại diện kiểu trong language model |
| `Elements` | Truy vấn và thao tác trên element model |
| `Types` | Kiểm tra quan hệ giữa các kiểu |
| `Filer` | Tạo source file, class file hoặc resource |
| `Messager` | Gửi diagnostic như NOTE, WARNING và ERROR |

Processor nên làm việc với language model thay vì cố nạp class của source đang biên dịch bằng `Class.forName`. Class đó có thể chưa được compile thành bytecode tại thời điểm processor chạy.

### 2.1. AbstractProcessor

Một processor thường kế thừa `AbstractProcessor`:

~~~java
public class GreetingProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        return false;
    }
}
~~~

Các phương thức thường được override:

- `init(ProcessingEnvironment)`: nhận môi trường xử lý.
- `process(...)`: xử lý annotation ở mỗi round.
- `getSupportedAnnotationTypes()`: khai báo loại annotation processor quan tâm.
- `getSupportedSourceVersion()`: khai báo phiên bản source Java được hỗ trợ.
- `getSupportedOptions()`: khai báo các option compiler truyền cho processor.

Có thể khai báo metadata bằng annotation `@SupportedAnnotationTypes`, `@SupportedSourceVersion` và `@SupportedOptions`, hoặc override phương thức tương ứng.

### 2.2. Supported annotation types

~~~java
@SupportedAnnotationTypes("demo.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class GreetingProcessor extends AbstractProcessor {
    // ...
}
~~~

`@SupportedAnnotationTypes` dùng tên đầy đủ của annotation type, gồm package. Có thể hỗ trợ nhiều annotation bằng cách khai báo nhiều tên.

Ký tự wildcard `*` có nghĩa processor quan tâm đến mọi annotation type. Chỉ dùng khi processor thực sự cần quan sát mọi annotation; nếu không, khai báo chính xác loại cần xử lý sẽ rõ ràng và hiệu quả hơn.

### 2.3. Language model thay cho Java Reflection

Trong `process`, `Element` và `TypeElement` mô tả khai báo đang được compiler xử lý:

~~~java
for (Element element : roundEnv.getElementsAnnotatedWith(annotationType)) {
    if (element instanceof TypeElement typeElement) {
        String name = typeElement.getQualifiedName().toString();
        processingEnv.getMessager().printMessage(
                Diagnostic.Kind.NOTE,
                "Đang xử lý " + name,
                typeElement
        );
    }
}
~~~

`TypeElement` là mô hình khai báo kiểu; nó không phải `java.lang.Class<?>`. Các kiểu trong `javax.lang.model` được thiết kế để processor phân tích source và type mà không cần class đã được nạp vào JVM.

## 3. Processing rounds

Annotation processing có thể diễn ra qua nhiều vòng (round). Điều này cho phép processor sinh source mới và để compiler/processor tiếp tục xử lý annotation trong source vừa sinh.

Quy trình đơn giản:

1. Compiler phân tích source ban đầu và tìm annotation.
2. Processor nhận các annotation và element liên quan trong round hiện tại.
3. Processor có thể sinh source hoặc resource qua `Filer`.
4. Compiler phân tích source mới được sinh.
5. Các processor được gọi ở round tiếp theo với annotation xuất hiện trong source mới.
6. Cuối cùng compiler gọi round cuối với `processingOver() == true`.

### 3.1. Kiểm tra round cuối

~~~java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {

    if (roundEnv.processingOver()) {
        return false;
    }

    // Xử lý annotation ở round hiện tại.
    return false;
}
~~~

Ở round cuối, processor có thể tổng kết hoặc báo diagnostic. Không nên dựa vào việc tạo thêm source ở round cuối để mở ra một round xử lý mới; không còn round tiếp theo để xử lý source mới đó.

### 3.2. hasErrorRaised

`roundEnv.errorRaised()` cho biết round trước đã có lỗi được báo hay chưa. Processor có thể dùng thông tin này để tránh sinh output dựa trên dữ liệu đã lỗi.

Không phải processor nào cũng cần xử lý riêng trường hợp đó. Tuy nhiên, processor tạo mã tổng hợp từ nhiều kiểu nên cân nhắc không phát sinh thêm source lỗi khi compilation đã có diagnostic nghiêm trọng.

### 3.3. Giá trị boolean trả về từ process

Giá trị trả về không phải “build thành công hay thất bại”:

- `true`: processor tuyên bố đã xử lý (claim) các annotation type được chuyển cho nó trong round hiện tại.
- `false`: processor không claim các annotation type đó; processor khác có thể tiếp tục xử lý chúng.

Nếu processor chuyên trách một annotation, trả `true` sau khi xử lý annotation đó thường phù hợp. Nếu processor chỉ quan sát hoặc muốn cho processor khác xử lý tiếp, trả `false`.

Lỗi compile nên được báo bằng `Messager` với `Diagnostic.Kind.ERROR`, không phải chỉ bằng giá trị boolean.

## 4. Sinh file bằng Filer

`Filer` là API chính thức để processor tạo file trong quá trình biên dịch. Các thao tác thường dùng:

- `createSourceFile(...)`: tạo source file.
- `createClassFile(...)`: tạo class file.
- `createResource(...)`: tạo resource trong output location.

Không nên tự ghi source được sinh vào thư mục source của dự án bằng `FileWriter` hoặc đường dẫn hard-code. Dùng `Filer` để compiler và build tool quản lý generated output đúng vị trí.

### 4.1. Tạo source file

~~~java
JavaFileObject sourceFile =
        processingEnv.getFiler().createSourceFile(
                "demo.ExampleGreeting",
                originatingElement
        );

try (Writer writer = sourceFile.openWriter()) {
    writer.write("""
            package demo;

            public final class ExampleGreeting {
                public static String message() {
                    return "Hello from generated code";
                }
            }
            """);
}
~~~

Đối số đầu tiên là qualified name của kiểu cần sinh. Đối số `originatingElement` liên kết file được sinh với phần tử nguồn đã dẫn tới việc sinh file; điều này hữu ích cho công cụ build và incremental processing.

Tên file phải duy nhất trong một lần biên dịch. Nếu processor cố tạo cùng một source nhiều lần, `Filer` có thể ném `FilerException`.

### 4.2. Tránh ghi trùng output

~~~java
processingEnv.getFiler().createSourceFile("demo.GeneratedConfig");
processingEnv.getFiler().createSourceFile("demo.GeneratedConfig");
~~~

Hai lần tạo cùng tên trong một compilation không hợp lệ. Processor nên xác định tên output ổn định và bảo đảm mỗi output chỉ được tạo một lần.

Nếu có nhiều annotation dẫn tới cùng một output, hãy gom dữ liệu cần thiết trước khi sinh file hoặc dùng một cấu trúc theo dõi tên đã tạo trong processor instance. Với output tổng hợp, cần thu thập các input phù hợp trước khi tạo file cuối cùng.

### 4.3. Tạo resource

~~~java
FileObject resource = processingEnv.getFiler().createResource(
        StandardLocation.CLASS_OUTPUT,
        "",
        "META-INF/demo/generated-index.txt"
);

try (Writer writer = resource.openWriter()) {
    writer.write("demo.ExampleGreeting\n");
}
~~~

Resource được ghi vào output location do compiler/build tool quản lý, không cần tự đoán đường dẫn `build/classes` hoặc `target/classes`.

### 4.4. Messager để báo lỗi đúng vị trí

~~~java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "@GenerateGreeting chỉ áp dụng cho class",
        element
);
~~~

Các loại diagnostic:

| Kind | Ý nghĩa |
|---|---|
| `ERROR` | Lỗi; compilation thất bại |
| `WARNING` | Cảnh báo; compiler vẫn có thể tiếp tục |
| `MANDATORY_WARNING` | Cảnh báo bắt buộc theo quy tắc compiler |
| `NOTE` | Thông tin |
| `OTHER` | Diagnostic khác |

Truyền `Element` giúp diagnostic gắn với vị trí khai báo liên quan, dễ sửa hơn thông báo chỉ chứa text.

## 5. Ví dụ processor hoàn chỉnh

Ví dụ sau tạo một class có phương thức `message()` cho mỗi class được đánh dấu `@GenerateGreeting`. Processor nhận diện annotation qua tên đầy đủ trong language model, nên processor không cần import annotation API vào code của chính nó.

### 5.1. Annotation API

File `annotation-api/src/main/java/demo/GenerateGreeting.java`:

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

### 5.2. Processor implementation

File `processor/src/main/java/demo/processor/GreetingProcessor.java`:

~~~java
package demo.processor;

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
import javax.lang.model.element.PackageElement;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class GreetingProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return false;
        }

        TypeElement annotationType = processingEnv
                .getElementUtils()
                .getTypeElement("demo.GenerateGreeting");

        if (annotationType == null) {
            return false;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(annotationType)) {

            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@GenerateGreeting chỉ áp dụng cho class",
                        element
                );
                continue;
            }

            TypeElement type = (TypeElement) element;
            PackageElement packageElement =
                    processingEnv.getElementUtils().getPackageOf(type);

            String packageName =
                    packageElement.isUnnamed()
                            ? ""
                            : packageElement.getQualifiedName().toString();

            String generatedName = type.getSimpleName() + "Greeting";
            String qualifiedName = packageName.isEmpty()
                    ? generatedName
                    : packageName + "." + generatedName;

            try {
                JavaFileObject file = processingEnv.getFiler()
                        .createSourceFile(qualifiedName, type);

                try (Writer writer = file.openWriter()) {
                    if (!packageName.isEmpty()) {
                        writer.write("package " + packageName + ";\n\n");
                    }

                    writer.write("public final class " + generatedName + " {\n");
                    writer.write("    private " + generatedName + "() {}\n");
                    writer.write("    public static String message() {\n");
                    writer.write("        return \"Hello from generated code\";\n");
                    writer.write("    }\n");
                    writer.write("}\n");
                }

            } catch (IOException e) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Không thể sinh " + qualifiedName + ": "
                                + e.getMessage(),
                        type
                );
            }
        }

        return true;
    }
}
~~~

Processor kiểm tra loại element trước khi cast, lấy package từ `Elements`, sinh source qua `Filer` và báo lỗi qua `Messager`. Ví dụ cố ý đơn giản để minh họa API; processor thực tế cần xử lý tên lồng nhau, nhiều loại element, trùng output và các quy tắc nghiệp vụ riêng.

### 5.3. Đăng ký processor qua Service Provider

Tạo file:

`processor/src/main/resources/META-INF/services/javax.annotation.processing.Processor`

Nội dung:

~~~text
demo.processor.GreetingProcessor
~~~

Đây là Java Service Provider configuration. Khi file được đóng gói vào JAR, `javac` có thể tìm processor qua cơ chế service loading nếu JAR nằm trên processor path hoặc classpath được dùng để tìm processor.

Có thể chỉ định tên processor tường minh bằng tùy chọn `-processor`, kể cả khi đã đăng ký service.

## 6. Chạy javac với processor

Quá trình build thủ công có thể tách thành ba phần: compile annotation API, compile processor và compile ứng dụng.

Giả sử cấu trúc:

~~~text
project/
├── annotation-api/
│   └── src/main/java/demo/GenerateGreeting.java
├── processor/
│   ├── src/main/java/demo/processor/GreetingProcessor.java
│   └── src/main/resources/META-INF/services/
│       └── javax.annotation.processing.Processor
└── app/
    └── src/main/java/demo/
        ├── Example.java
        └── Runner.java
~~~

### 6.1. Compile annotation API

~~~bash
javac --release 17 -d annotation-api/out \
    annotation-api/src/main/java/demo/GenerateGreeting.java

jar --create --file annotation-api.jar \
    -C annotation-api/out .
~~~

JAR này chứa annotation type để source ứng dụng có thể import.

### 6.2. Compile và đóng gói processor

~~~bash
javac --release 17 -d processor/out \
    processor/src/main/java/demo/processor/GreetingProcessor.java

jar --create --file greeting-processor.jar \
    -C processor/out . \
    -C processor/src/main/resources .
~~~

Processor trong ví dụ chỉ dùng JDK API, nên không cần annotation API trên compile classpath của processor. Processor phức tạp hơn có thể cần dependency riêng để chạy.

### 6.3. Source ứng dụng

File `app/src/main/java/demo/Example.java`:

~~~java
package demo;

@GenerateGreeting
public class Example {
}
~~~

File `app/src/main/java/demo/Runner.java`:

~~~java
package demo;

public class Runner {
    public static void main(String[] args) {
        System.out.println(ExampleGreeting.message());
    }
}
~~~

### 6.4. Chạy annotation processing và compile

Tạo thư mục output trước:

~~~bash
mkdir -p app/generated app/classes
~~~

Compile:

~~~bash
javac --release 17 \
    -classpath annotation-api.jar \
    -processorpath greeting-processor.jar \
    -processor demo.processor.GreetingProcessor \
    -s app/generated \
    -d app/classes \
    app/src/main/java/demo/Example.java \
    app/src/main/java/demo/Runner.java
~~~

Ý nghĩa các option:

| Option | Vai trò |
|---|---|
| `--release 17` | Compile theo API và ngôn ngữ Java 17 |
| `-classpath` | Classpath cho source ứng dụng và dependency cần khi compile |
| `-processorpath` | Nơi tìm processor và dependency để chạy processor |
| `-processor` | Chỉ định processor cần chạy |
| `-s` | Thư mục chứa source được sinh |
| `-d` | Thư mục chứa class file đầu ra |

Compiler xử lý `Example`, processor sinh `ExampleGreeting.java` trong `app/generated`, sau đó compiler biên dịch source được sinh vào `app/classes`.

Chạy trên Linux/macOS:

~~~bash
java -cp app/classes:annotation-api.jar demo.Runner
~~~

Kết quả:

~~~text
Hello from generated code
~~~

Trên Windows, dấu phân cách classpath là `;` thay vì `:`:

~~~powershell
java -cp "app/classes;annotation-api.jar" demo.Runner
~~~

### 6.5. Kiểm soát annotation processing

Một số option hữu ích của `javac`:

| Option | Tác dụng |
|---|---|
| `-proc:none` | Không chạy annotation processing |
| `-proc:only` | Chỉ chạy annotation processing, không thực hiện compile thông thường |
| `-processor A,B` | Chỉ định processor theo tên đầy đủ |
| `-processorpath path` | Classpath dành cho processor |
| `--processor-module-path path` | Module path dành cho processor dạng module |
| `-s directory` | Nơi ghi source được sinh |
| `-Akey=value` | Truyền option cho processor |

Trong Java 17, annotation processing có thể được phát hiện tự động qua service provider trên các path phù hợp. Tuy nhiên, cấu hình processor path và processor rõ ràng giúp build dễ tái lập, tránh chạy nhầm processor vô tình có trên compile classpath.

Từ JDK 23, `javac` thay đổi mặc định về việc tự động chạy processor được phát hiện trên classpath. Build cần cấu hình processor tường minh để không phụ thuộc default giữa các phiên bản JDK.

## 7. Ba loại phụ thuộc cần tách riêng

Đây là phần quan trọng khi cấu hình Maven hoặc Gradle.

### 7.1. Compile-time dependency

Đây là dependency mà source ứng dụng cần nhìn thấy để biên dịch.

~~~java
import demo.GenerateGreeting;

@GenerateGreeting
public class Example {
}
~~~

Source cần annotation type `demo.GenerateGreeting` trên compile classpath. Nếu không có annotation API, compiler báo không tìm thấy package hoặc symbol.

Annotation API có thể cần:

- `compileOnly` nếu annotation chỉ dùng khi compile và không cần hiện diện ở runtime.
- `implementation` nếu module ứng dụng cần annotation API lúc runtime.
- `api` trong thư viện nếu annotation xuất hiện trên public API và người dùng thư viện cần đọc/biên dịch với kiểu annotation đó.

Chọn scope theo hợp đồng thư viện, không chọn chỉ dựa vào việc annotation processor cần nó.

### 7.2. Annotation processor dependency

Processor là chương trình chạy trong compiler. Nó cần được đặt trên processor path do build tool quản lý.

Processor thường không cần có mặt trong runtime classpath của ứng dụng. Đưa nó vào runtime chỉ làm artifact ứng dụng có dependency không cần thiết và có thể kéo theo thư viện hỗ trợ của processor.

Một processor cũng có thể cần dependency riêng để thực thi, chẳng hạn thư viện phân tích schema hoặc template engine. Các dependency đó phải có trên processor path cùng processor.

### 7.3. Runtime dependency

Code được sinh ra có thể tham chiếu tới một API runtime:

~~~java
public final class GeneratedMapper {
    public static Result map(Source source) {
        return RuntimeMappingSupport.convert(source);
    }
}
~~~

Nếu `GeneratedMapper` gọi `RuntimeMappingSupport`, ứng dụng cần thư viện chứa class đó trên runtime classpath. Chỉ khai báo nó ở `annotationProcessor` là không đủ.

Ngược lại, nếu processor chỉ sinh mã Java thuần không tham chiếu tới thư viện runtime, processor artifact có thể hoàn toàn vắng mặt khi ứng dụng chạy.

### 7.4. Bảng phân biệt

| Loại | Dùng khi nào? | Ví dụ cấu hình Gradle |
|---|---|---|
| Annotation API cần compile | Source import annotation | `compileOnly` hoặc `implementation` |
| Processor implementation | Compiler cần chạy processor | `annotationProcessor` |
| Processor cho test source | Test có annotation cần xử lý | `testAnnotationProcessor` |
| Runtime support API | Generated code gọi API lúc chạy | `implementation` hoặc `api` |
| Annotation API là public contract | Consumer phải nhìn thấy annotation trong public API | `api` |

Một dependency có thể thuộc nhiều configuration nếu nó thực sự phục vụ nhiều giai đoạn, nhưng hãy xác định lý do rõ ràng cho từng configuration.

## 8. Cấu hình Gradle cho Java 17

Với Gradle Java plugin, configuration `annotationProcessor` dành cho processor chạy khi biên dịch main source set. `testAnnotationProcessor` dành cho processor của test source set.

Ví dụ Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    // Annotation được source sử dụng, không cần ở runtime.
    compileOnly 'com.example:annotation-api:1.0'

    // Processor chạy trong quá trình compileJava.
    annotationProcessor 'com.example:greeting-processor:1.0'

    // Nếu test source cũng dùng annotation này:
    testCompileOnly 'com.example:annotation-api:1.0'
    testAnnotationProcessor 'com.example:greeting-processor:1.0'

    // Thư viện mà generated code gọi khi runtime (nếu có).
    implementation 'com.example:generated-runtime-support:1.0'
}
~~~

Nếu annotation nằm trong public API của library và consumer cần nhìn thấy nó, dùng `api` thay cho `compileOnly` khi dự án áp dụng `java-library` plugin và hợp đồng API yêu cầu điều đó.

### 8.1. Kotlin DSL

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    compileOnly("com.example:annotation-api:1.0")
    annotationProcessor("com.example:greeting-processor:1.0")

    testCompileOnly("com.example:annotation-api:1.0")
    testAnnotationProcessor("com.example:greeting-processor:1.0")

    implementation("com.example:generated-runtime-support:1.0")
}
~~~

### 8.2. Kiểm tra dependency đã vào đúng configuration

Có thể xem dependency tree:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration annotationProcessor
./gradlew dependencies --configuration runtimeClasspath
~~~

Ba cây dependency trả lời ba câu hỏi khác nhau:

- Compiler có nhìn thấy annotation API và kiểu cần compile không?
- Processor cùng dependency để chạy có được phân giải không?
- Ứng dụng có thư viện cần thiết khi chạy không?

Đừng dùng `runtimeClasspath` để kiểm tra processor path.

### 8.3. Incremental annotation processing trong Gradle

Gradle có thể incremental compile với processor được khai báo incremental đúng cách. Processor cần được phân loại theo cách nó tạo output:

- **Isolating:** mỗi output chỉ phụ thuộc vào một input element cụ thể.
- **Aggregating:** output tổng hợp phụ thuộc vào nhiều input element.
- **Dynamic:** processor xác định loại hành vi trong lúc chạy theo cơ chế Gradle hỗ trợ.

Processor công bố metadata trong resource:

`META-INF/gradle/incremental.annotation.processors`

Ví dụ:

~~~text
demo.processor.GreetingProcessor,isolating
~~~

Chỉ khai báo `isolating` nếu mỗi output thực sự chỉ phụ thuộc vào originating element được truyền cho `Filer`. Nếu processor tổng hợp danh sách tất cả class đã đánh dấu để sinh một registry duy nhất, nó là aggregating.

Truyền originating elements cho `Filer` là một phần quan trọng của việc cho build tool biết quan hệ giữa input và generated output. Khai báo sai có thể khiến incremental build bỏ sót thay đổi hoặc tạo kết quả cũ.

## 9. Cấu hình Maven cho Java 17

Maven Compiler Plugin có thể cấu hình processor path riêng. Ví dụ:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<dependencies>
    <!-- Annotation API để source ứng dụng biên dịch. -->
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>annotation-api</artifactId>
        <version>1.0</version>
        <scope>provided</scope>
    </dependency>

    <!-- Runtime support nếu generated code cần thư viện này. -->
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>generated-runtime-support</artifactId>
        <version>1.0</version>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <annotationProcessorPaths>
                    <path>
                        <groupId>com.example</groupId>
                        <artifactId>greeting-processor</artifactId>
                        <version>1.0</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Trong ví dụ:

- `annotation-api` nằm trong dependency của project để source compile được.
- `greeting-processor` nằm trong `annotationProcessorPaths`, là processor dependency.
- `generated-runtime-support` nằm ở dependency runtime vì generated code dùng nó khi chạy.
- `maven.compiler.release` và `<release>17</release>` yêu cầu compile theo Java 17.

`provided` phù hợp khi annotation API cần trong compile nhưng môi trường chạy không cần artifact đó. Nếu annotation là một phần public API mà consumer cần có trên compile classpath, cần chọn scope và cách publish phù hợp thay vì dùng `provided` một cách máy móc.

### 9.1. Processor path và dependency thông thường

`annotationProcessorPaths` tách processor khỏi classpath ứng dụng. Nếu processor có dependency để chạy, Maven Compiler Plugin cần phân giải chúng trên processor path theo cấu hình plugin.

Đừng khai báo processor như dependency runtime chỉ để compiler tìm thấy nó. Hãy cấu hình rõ trong plugin.

### 9.2. Xem generated sources

Maven Compiler Plugin thường quản lý thư mục generated source trong `target/generated-sources/annotations`. Có thể mở thư mục đó để đọc mã được sinh khi debug.

Generated source là build output. Không chỉnh sửa trực tiếp file ở thư mục này vì lần build sau có thể sinh lại và ghi đè thay đổi.

## 10. Annotation processor trên module path (JPMS)

Nếu processor được đóng gói như named module, module descriptor có thể khai báo service provider.

Ví dụ `module-info.java` của processor:

~~~java
module com.example.greeting.processor {
    requires java.compiler;

    provides javax.annotation.processing.Processor
            with demo.processor.GreetingProcessor;
}
~~~

`requires java.compiler` cho phép processor dùng các API annotation processing và language model. `provides` đăng ký processor theo Java module service mechanism.

Với `javac`, có thể chỉ định processor module path:

~~~bash
javac --release 17 \
    --processor-module-path processor-modules \
    -processor demo.processor.GreetingProcessor \
    -classpath annotation-api.jar \
    -s generated \
    -d classes \
    src/demo/Example.java
~~~

Cấu hình module path và dependency module phụ thuộc cách đóng gói JAR. Với processor dạng classpath JAR thông thường, dùng `-processorpath` là đủ; không cần tạo module chỉ để viết processor đơn giản.

### 10.1. Phân biệt các loại path

- `--module-path`: module path của dependency ứng dụng.
- `--processor-module-path`: module path dành cho processor dạng module.
- `-classpath`: classpath compile thông thường.
- `-processorpath`: classpath dành cho processor.

Các path này phục vụ những mục đích khác nhau. Một thư viện có thể cần được đặt ở nhiều path nếu nó thực sự cung cấp API cho ứng dụng và cũng là dependency mà processor cần dùng.

## 11. Annotation retention và phụ thuộc của annotation API

`RetentionPolicy` xác định annotation tồn tại ở đâu:

| Retention | Tồn tại ở đâu? | Mục đích thường gặp |
|---|---|---|
| `SOURCE` | Source trong quá trình compile, không lưu trong class file | Annotation chỉ dành cho compiler/processor |
| `CLASS` | Được lưu trong class file, nhưng không nhất thiết có ở Reflection runtime | Metadata cho compiler/tool |
| `RUNTIME` | Lưu trong class file và có thể đọc bằng Reflection | Framework cần inspect annotation lúc chạy |

Không cần đặt annotation thành `RUNTIME` chỉ vì annotation processor cần đọc nó. Processor hoạt động trong compile phase nên có thể xử lý annotation `SOURCE`.

Ví dụ:

~~~java
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateGreeting {
}
~~~

Nếu một framework runtime cũng cần đọc annotation, khi đó mới cân nhắc `RUNTIME` và dependency annotation phải có mặt ở runtime theo thiết kế.

### 11.1. Annotation API có thể là một artifact riêng

~~~text
library-annotations
    +-- các annotation type
    +-- không chứa processor implementation

library-processor
    +-- AbstractProcessor implementation
    +-- service registration
    +-- phụ thuộc annotation API nếu cần

application
    +-- compile dependency tới annotation API
    +-- annotationProcessor dependency tới processor
    +-- runtime dependency tới generated-code support nếu cần
~~~

Cách tách này giảm việc kéo processor và dependency build-time vào ứng dụng cuối. Nó cũng giúp versioning annotation API và processor rõ ràng hơn.

## 12. Những lỗi thường gặp khi cấu hình processor

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Annotation không tìm thấy khi compile | Thiếu annotation API trên compile classpath | Thêm compile dependency phù hợp |
| Processor không chạy | JAR thiếu service registration hoặc processor path sai | Kiểm tra service file, `-processorpath` và tên processor |
| Processor chạy nhưng không thấy annotation | `@SupportedAnnotationTypes` sai tên hoặc annotation không nằm trong source đang compile | Kiểm tra qualified name và source set |
| `NoClassDefFoundError` trong processor | Thiếu dependency runtime của processor trên processor path | Thêm dependency đó vào processor configuration |
| Generated source không xuất hiện | Processor không gọi `Filer`, điều kiện xử lý không thỏa hoặc round đã kết thúc | Kiểm tra `process`, diagnostic và generated-source directory |
| `FilerException: Attempt to recreate a file` | Sinh cùng output nhiều lần hoặc output đã tồn tại trong compilation | Đảm bảo tên output duy nhất và chỉ tạo một lần |
| Generated code compile được nhưng runtime lỗi | Thiếu thư viện mà generated code tham chiếu | Thêm runtime dependency tương ứng |
| IDE và command-line build khác kết quả | IDE/build tool dùng processor path hoặc generated source setup khác | Đồng bộ cấu hình annotation processor của IDE và build |
| Incremental build cho kết quả cũ | Processor khai báo incremental sai hoặc không cung cấp originating elements | Sửa metadata isolating/aggregating và Filer usage |
| Compile chậm bất thường | Processor xử lý quá nhiều element hoặc quét package rộng | Giới hạn supported annotations và tối ưu việc duyệt model |

## 13. Thiết kế processor an toàn và dễ bảo trì

Annotation processor chạy trong quá trình build, nhưng nó vẫn là code thực thi trên máy developer hoặc CI. Chỉ thêm processor dependency từ nguồn tin cậy; processor có thể đọc file, truy cập môi trường và thực hiện hành động mà tiến trình build được phép làm.

Các nguyên tắc nên áp dụng:

1. Chỉ xử lý annotation mà processor thực sự hỗ trợ.
2. Kiểm tra loại element trước khi cast.
3. Báo lỗi bằng `Messager` và gắn diagnostic vào element phù hợp.
4. Dùng `Filer` thay cho ghi file trực tiếp.
5. Đặt tên generated type ổn định và tránh sinh trùng.
6. Truyền originating elements để build tool theo dõi nguồn.
7. Không phụ thuộc vào đường dẫn tuyệt đối trên máy developer.
8. Không dùng API nội bộ `com.sun.*` nếu không có lý do đặc biệt.
9. Tránh nạp class đang biên dịch bằng Reflection; dùng `Element`, `TypeMirror`, `Elements` và `Types`.
10. Kiểm thử cả source hợp lệ, source sai và nhiều round.
11. Giữ processor artifact tách khỏi runtime dependency nếu ứng dụng không cần nó khi chạy.
12. Chỉ khai báo incremental processing khi loại isolating/aggregating phản ánh đúng cách sinh output.

### 13.1. Truyền option cho processor

Processor có thể nhận option từ compiler:

~~~bash
javac -Aconfig=production -AgeneratedPackage=demo.generated ...
~~~

Khai báo option hỗ trợ:

~~~java
@SupportedOptions({"config", "generatedPackage"})
public class GreetingProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        String targetPackage = processingEnv.getOptions()
                .getOrDefault("generatedPackage", "demo.generated");

        // Dùng targetPackage khi tạo source.
        return true;
    }
}
~~~

Khai báo option giúp build cấu hình processor mà không hard-code môi trường vào source. Nên xác thực giá trị option và báo lỗi rõ ràng nếu cấu hình không hợp lệ.

### 13.2. Không dùng processor để thay thế runtime logic

Processor phù hợp cho kiểm tra cấu trúc, sinh mã tĩnh và metadata tại build. Nếu dữ liệu chỉ có khi ứng dụng chạy, annotation processor không thể thay thế xử lý runtime cho dữ liệu đó.

Ví dụ: processor có thể sinh mapper từ khai báo class và annotation đã biết lúc compile; nó không thể đọc giá trị của request đến từ người dùng khi ứng dụng đang chạy.

## 14. Bài tập thực hành

### Bài 1: Phân loại dependency

Một project sử dụng annotation `@GenerateGreeting`, processor sinh class gọi `RuntimeSupport.print()`.

Hãy phân loại:

- JAR chứa `GenerateGreeting`.
- JAR chứa `GreetingProcessor`.
- JAR chứa `RuntimeSupport`.

**Đáp án:**

- Annotation JAR: compile dependency, có thể là `compileOnly`/`provided` nếu không cần runtime.
- Processor JAR: `annotationProcessor` trong Gradle hoặc `annotationProcessorPaths` trong Maven.
- RuntimeSupport JAR: runtime dependency (`implementation` hoặc scope phù hợp) vì generated class gọi nó khi chạy.

### Bài 2: Vì sao processor không chạy?

Source đã import annotation đúng, compile không báo thiếu annotation, nhưng không có generated source.

**Gợi ý kiểm tra:**

- Processor JAR có chứa service registration file không?
- Processor có nằm trên `-processorpath` hoặc `annotationProcessor` configuration không?
- Tên trong service file có đúng fully qualified class name không?
- `@SupportedAnnotationTypes` có đúng package và tên annotation không?
- Processor có tạo file qua `Filer` và có báo diagnostic không?

### Bài 3: Phân biệt SOURCE và RUNTIME

Một annotation chỉ được dùng để sinh code khi compile. Có cần `RetentionPolicy.RUNTIME` không?

**Đáp án:** Không. `SOURCE` đủ cho annotation processor. Chỉ chọn `RUNTIME` nếu ứng dụng hoặc framework cần đọc annotation bằng Reflection lúc chạy.

### Bài 4: Processing rounds

Processor sinh `GeneratedConfig.java` trong round đầu. Compiler xử lý file đó như thế nào?

**Đáp án:** Compiler phân tích source được sinh và có thể gọi processor ở round tiếp theo nếu source đó chứa annotation phù hợp. Sau khi không còn source mới, compiler gọi round cuối với `processingOver() == true`.

### Bài 5: FilerException

Processor nhận 5 class cùng annotation và cả 5 lần đều tạo `demo.Registry`.

**Câu hỏi:** Vì sao lỗi?

**Đáp án:** Cùng một compilation, processor cố tạo một source file cùng qualified name nhiều lần. Hãy gom dữ liệu của các input rồi tạo registry một lần, hoặc sinh output riêng cho từng input nếu thiết kế yêu cầu.

### Bài 6: Compile thành công nhưng runtime lỗi

Generated source gọi `RuntimeSupport.convert`, nhưng project chỉ khai báo RuntimeSupport trong `annotationProcessor`.

**Đáp án:** Processor path chỉ cung cấp dependency để processor chạy lúc compile. Nó không tự đưa RuntimeSupport vào runtime classpath. Cần khai báo thư viện đó trong runtime dependency nếu generated code sử dụng nó khi chạy.

## 15. Ghi nhớ

Khi dùng annotation processor trong Java 17:

1. Annotation processing là compile-time mechanism dựa trên JSR 269.
2. Processor thường kế thừa `AbstractProcessor` và làm việc với `Element`, `TypeElement`, `TypeMirror`.
3. `process` có thể chạy nhiều round; source được sinh có thể được xử lý ở round sau.
4. Dùng `Filer` để tạo source/resource và `Messager` để báo lỗi.
5. Đăng ký processor qua service provider hoặc module `provides`.
6. Tách compile classpath, processor path và runtime classpath.
7. Trong Gradle dùng `annotationProcessor`/`testAnnotationProcessor`; trong Maven cấu hình `annotationProcessorPaths`.
8. Dùng `--release 17` để giữ target Java 17.
9. Generated source là build output; không sửa trực tiếp file đã sinh.
10. Chỉ khai báo incremental processor khi loại isolating/aggregating phản ánh đúng cách sinh output.
11. Chỉ dùng processor dependency đáng tin cậy vì processor thực thi trong môi trường build.
12. Nếu generated code gọi thư viện runtime, phải khai báo runtime dependency riêng.

## 16. Tài liệu tham khảo

- [Oracle Java SE 17 — javax.annotation.processing](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/package-summary.html): API annotation processing, processor lifecycle và processing environment.
- [Oracle Java SE 17 — AbstractProcessor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): lớp cơ sở cho processor.
- [Oracle Java SE 17 — Filer](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html): tạo source, class và resource file.
- [Oracle Java SE 17 — Messager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Messager.html): gửi diagnostic cho compiler.
- [Oracle Java SE 17 — RoundEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): thông tin từng processing round.
- [Oracle Java SE 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): processor path, module path, generated source và compiler options.
- [Gradle — Incremental Annotation Processing](https://docs.gradle.org/current/userguide/java_plugin.html#sec:incremental_annotation_processing): phân loại processor isolating, aggregating và khai báo metadata.
- [Maven Compiler Plugin — Annotation Processor Configuration](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html): cấu hình processor path trong Maven.



