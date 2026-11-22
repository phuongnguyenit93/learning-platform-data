# Pha annotation processing trong Java compilation pipeline

Annotation processing là giai đoạn xử lý annotation trong quá trình biên dịch Java. Ở giai đoạn này, compiler có thể gọi các **annotation processor** để đọc metadata trên lớp, phương thức, trường hoặc package, kiểm tra quy ước và sinh thêm mã nguồn hoặc tài nguyên. Các tệp nguồn được sinh ra có thể tiếp tục được compiler biên dịch trong cùng lần build.

Annotation processing thường được dùng trong thư viện và framework để giảm mã lặp, tạo implementation tự động, sinh metadata hoặc phát hiện lỗi cấu hình ngay lúc build. Những ví dụ quen thuộc gồm bộ sinh mapper, dependency injection, serializer, metamodel và mã truy cập dữ liệu.

Điểm quan trọng: annotation chỉ là metadata. Việc một phần tử có annotation không tự động sinh mã hay thay đổi hành vi. Một annotation processor tương ứng phải được cấu hình và chạy trong compiler thì phần xử lý đó mới diễn ra.

## 1. Annotation processing nằm ở đâu trong compilation pipeline?

Một mô hình đơn giản của quá trình biên dịch bằng `javac`:

1. **Parse:** đọc mã nguồn, phân tích token và tạo cấu trúc cú pháp.
2. **Enter:** đăng ký thông tin lớp, thành viên và symbol để compiler có thể tham chiếu giữa các kiểu.
3. **Annotation processing:** phát hiện processor phù hợp, gọi processor theo từng round và tiếp nhận các tệp nguồn/tài nguyên được sinh ra.
4. **Attribution và type checking:** phân giải tên, kiểm tra kiểu, overload, generic và các quy tắc ngôn ngữ.
5. **Flow analysis:** kiểm tra một số quy tắc luồng điều khiển, chẳng hạn biến local phải được gán trước khi đọc.
6. **Lowering/desugaring:** chuyển một số cấu trúc ngôn ngữ cấp cao thành dạng nội bộ phù hợp cho các bước sau.
7. **Generate:** tạo bytecode trong các tệp `.class`.

Đây là mô hình khái niệm để hiểu luồng công việc; chi tiết nội bộ và cách chia pha của compiler có thể khác theo phiên bản hoặc implementation.

```text
Mã nguồn + annotation
          |
          v
      Parse / Enter
          |
          v
  Annotation processing
      |           |
      |           +--> Diagnostic: warning / error
      |
      +--> Sinh source / resource
                 |
                 v
       Round tiếp theo của compiler
                 |
                 v
       Type checking / Flow analysis
                 |
                 v
          Generate .class
```

Processor chạy trong tiến trình compiler, thường trên JVM dùng để chạy `javac` hoặc build tool. Nó không phải một bước mà ứng dụng tự chạy mỗi lần khởi động. Nếu ứng dụng cần đọc annotation khi runtime, đó là một cơ chế khác, thường dùng reflection với annotation có `RetentionPolicy.RUNTIME`.

## 2. Annotation và annotation processor khác nhau thế nào?

**Annotation** khai báo metadata:

~~~java
@GenerateGreeting("Java")
public class App {
}
~~~

Trong ví dụ, `@GenerateGreeting` ghi một giá trị gắn với lớp `App`. Annotation có thể mô tả ý định hoặc cung cấp dữ liệu cho compiler, framework hay processor.

**Annotation processor** là chương trình chạy trong lúc biên dịch để đọc metadata đó và thực hiện công việc:

- Kiểm tra annotation được đặt đúng phần tử hay không.
- Kiểm tra kiểu, tên, modifier hoặc quan hệ giữa các phần tử.
- Phát ra warning hoặc error có vị trí nguồn cụ thể.
- Sinh thêm `.java`, `.class` hoặc resource.
- Đọc cấu trúc kiểu thông qua các API model của compiler.

Một annotation có thể không có processor nào xử lý. Trong trường hợp đó, compiler vẫn có thể giữ annotation theo retention policy và biên dịch lớp như bình thường, miễn là không có quy tắc ngôn ngữ hoặc compiler khác làm build thất bại.

### 2.1. Retention policy

`@Retention` quyết định annotation được giữ ở đâu:

| Retention | Ý nghĩa |
|---|---|
| `SOURCE` | Chỉ có trong mã nguồn, bị loại khỏi class file sau biên dịch |
| `CLASS` | Được lưu trong class file, nhưng không được reflection runtime thông thường trả về |
| `RUNTIME` | Được lưu trong class file và có thể đọc bằng reflection lúc chạy |

Annotation processor làm việc trong quá trình biên dịch và có thể đọc annotation trên các element mà compiler cung cấp. Nếu annotation chỉ phục vụ code generation hoặc kiểm tra lúc build, `SOURCE` thường là lựa chọn phù hợp. Nếu framework cần đọc annotation bằng reflection khi ứng dụng chạy, annotation thường phải dùng `RUNTIME`.

### 2.2. Annotation được compiler xử lý sẵn và annotation processor

Không phải mọi annotation đều cần một processor riêng. Ví dụ `@Override` được compiler hiểu để kiểm tra phương thức có override hợp lệ hay không. Đây là quy tắc ngôn ngữ/compiler, không phải bằng chứng rằng một processor bên ngoài đang chạy.

Ngược lại, một annotation tùy chỉnh như `@GenerateGreeting` chỉ có tác dụng sinh mã khi processor tương ứng được chạy và xử lý nó.

## 3. JSR 269 và các API chuẩn

Java cung cấp API annotation processing chuẩn theo JSR 269, trong package `javax.annotation.processing` và các package model liên quan.

Các thành phần quan trọng:

| API | Vai trò |
|---|---|
| `AbstractProcessor` | Lớp cơ sở thường dùng để viết processor |
| `Processor` | Interface định nghĩa hợp đồng của processor |
| `ProcessingEnvironment` | Cung cấp tiện ích và dịch vụ trong lúc xử lý |
| `RoundEnvironment` | Cung cấp các phần tử có annotation trong một round |
| `Element` | Mô tả phần tử Java như class, method, field hoặc package |
| `TypeElement` | Mô tả một khai báo kiểu |
| `Elements` | Tra cứu và thao tác với mô hình khai báo |
| `Types` | So sánh và phân tích kiểu Java |
| `Filer` | Tạo source file, class file và resource |
| `Messager` | Gửi diagnostic warning/error đến compiler |

Processor thường không phân tích mã nguồn bằng cách tìm chuỗi hoặc regex. Thay vào đó, nó dùng `Element`, `TypeMirror`, `Elements` và `Types` để làm việc với mô hình ngôn ngữ đã được compiler dựng lên. Cách này hiểu được package, kiểu generic, modifier và quan hệ kế thừa chính xác hơn.

### 3.1. Vòng đời của một processor

Một processor thường thực hiện các bước:

1. Compiler khởi tạo processor và cung cấp `ProcessingEnvironment`.
2. Processor khai báo loại annotation mà nó quan tâm và phiên bản ngôn ngữ hỗ trợ.
3. Compiler gọi `process(...)` trong từng round.
4. Processor đọc element và annotation từ `RoundEnvironment`.
5. Processor có thể phát warning/error hoặc tạo source/resource qua `Filer`.
6. Nếu có source mới, compiler đưa chúng vào round tiếp theo.
7. Khi không còn source mới, compiler gọi round cuối với `processingOver() == true`.

Một processor có thể được gọi nhiều lần trong cùng lần biên dịch. Không nên giả định `process(...)` chỉ chạy đúng một lần.

## 4. Processing rounds — cơ chế nhiều vòng

Annotation processing dùng mô hình round để hỗ trợ mã được sinh ra bởi processor.

- **Round đầu tiên:** chứa các source element đầu vào của lần biên dịch.
- **Round tiếp theo:** có thể chứa source file được sinh trong round trước.
- **Round cuối:** `roundEnv.processingOver()` trả về `true`, báo không còn round xử lý annotation thông thường nào tiếp theo.

Ví dụ: `App.java` có annotation `@GenerateGreeting`. Processor đọc annotation và tạo `AppGreeting.java`. Compiler đưa `AppGreeting.java` vào round tiếp theo, rồi kiểm tra kiểu và biên dịch nó cùng phần mã liên quan.

Một vài điểm quan trọng:

- Source được sinh trong một round có thể được xử lý ở round sau.
- Processor có thể sinh thêm source, resource hoặc class file.
- Round cuối thích hợp cho việc tổng kết hoặc kiểm tra cuối; không nên dựa vào round cuối để sinh source cần được xử lý ở round tiếp theo.
- `roundEnv.errorRaised()` cho biết round trước đã có diagnostic loại error hay chưa.
- `return true` từ `process(...)` có nghĩa processor đã claim các annotation được truyền vào; processor khác sẽ không nhận lại các annotation đã được claim trong cùng round. `return false` cho biết processor không claim chúng.

Tránh sinh lặp lại cùng tên file ở nhiều round. `Filer` phát hiện việc tạo file trùng và có thể ném `FilerException`. Thiết kế processor cần có tên output ổn định, duy nhất và chỉ sinh file khi thực sự cần.

## 5. Viết annotation processor đầu tiên

Ta sẽ tạo một annotation `@GenerateGreeting`. Processor đọc giá trị của annotation và sinh một lớp Java có phương thức trả về lời chào.

Ví dụ dùng Java 17 và cú pháp annotation processing chuẩn.

### 5.1. Cấu trúc thư mục

~~~text
project/
  src/
    demo/
      GenerateGreeting.java
      GreetingProcessor.java
      App.java
  processor-out/
  generated-src/
  app-out/
~~~

Ba tệp trong `src/demo` là mã nguồn đầu vào. Các thư mục `processor-out`, `generated-src` và `app-out` là thư mục đầu ra của các lệnh biên dịch.

### 5.2. Khai báo annotation

Tạo `src/demo/GenerateGreeting.java`:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateGreeting {
    String value();
}
~~~

Giải thích:

- `@Target(ElementType.TYPE)` cho phép annotation gắn lên khai báo kiểu như class, interface, enum hoặc record.
- `@Retention(RetentionPolicy.SOURCE)` cho biết annotation chỉ cần tồn tại trong lúc biên dịch.
- `String value()` là phần dữ liệu processor sẽ đọc.

### 5.3. Viết processor

Tạo `src/demo/GreetingProcessor.java`:

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

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateGreeting.class)) {

            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@GenerateGreeting chỉ hỗ trợ class",
                        element);
                continue;
            }

            String greeting =
                    element.getAnnotation(GenerateGreeting.class).value();

            String packageName = processingEnv.getElementUtils()
                    .getPackageOf(element)
                    .getQualifiedName()
                    .toString();

            String generatedName = element.getSimpleName() + "Greeting";
            String qualifiedName = packageName.isEmpty()
                    ? generatedName
                    : packageName + "." + generatedName;

            String packageLine = packageName.isEmpty()
                    ? ""
                    : "package " + packageName + ";\n";

            try {
                JavaFileObject file = processingEnv.getFiler()
                        .createSourceFile(qualifiedName, element);

                try (Writer writer = file.openWriter()) {
                    writer.write(packageLine
                            + "public final class " + generatedName + " {\n"
                            + "    private " + generatedName + "() {}\n"
                            + "    public static String message() {\n"
                            + "        return \"Hello, "
                            + escapeJavaString(greeting)
                            + "!\";\n"
                            + "    }\n"
                            + "}\n");
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Không thể sinh source: " + ex.getMessage(),
                        element);
            }
        }

        return true;
    }

    private static String escapeJavaString(String value) {
        return value.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\r", "\\r")
                .replace("\n", "\\n");
    }
}
~~~

Các điểm cần hiểu:

- `@SupportedAnnotationTypes` khai báo processor xử lý `demo.GenerateGreeting`.
- `@SupportedSourceVersion` khai báo mức Java mà processor hỗ trợ.
- `AbstractProcessor` cung cấp các tiện ích cơ bản và yêu cầu triển khai `process(...)`.
- `RoundEnvironment` tìm các phần tử có annotation trong round hiện tại.
- `Element` mô tả phần tử nguồn; `ElementKind.CLASS` giúp giới hạn processor vào class.
- `processingEnv.getElementUtils()` lấy package của class để sinh mã vào cùng package.
- `Filer.createSourceFile(...)` tạo source file trong output được quản lý bởi compiler.
- `Messager` gửi lỗi có gắn với element để IDE/compiler có thể chỉ vị trí.
- `escapeJavaString(...)` escape dấu gạch chéo ngược, dấu ngoặc kép và xuống dòng để giá trị annotation trở thành literal Java hợp lệ.

Trong ví dụ, mỗi class được gắn annotation tạo một lớp riêng có hậu tố `Greeting`. Khi xây dựng processor dùng trong dự án thật, cần kiểm tra tên output, xử lý trường hợp trùng tên và xác định rõ annotation hợp lệ trên những loại element nào.

### 5.4. Sử dụng annotation

Tạo `src/demo/App.java`:

~~~java
package demo;

@GenerateGreeting("Java")
public class App {
    public static void main(String[] args) {
        System.out.println(AppGreeting.message());
    }
}
~~~

Mã nguồn tham chiếu `AppGreeting`, dù lớp đó chưa được viết thủ công. Processor sẽ sinh lớp này trong lúc biên dịch.

### 5.5. Biên dịch processor và ứng dụng

Từ thư mục `project`, tạo các thư mục đầu ra. Trong PowerShell:

~~~powershell
New-Item -ItemType Directory -Force processor-out, generated-src, app-out | Out-Null
~~~

Bước 1 — biên dịch annotation và processor:

~~~text
javac -proc:none -d processor-out src/demo/GenerateGreeting.java src/demo/GreetingProcessor.java
~~~

Ở bước này, `-proc:none` tắt annotation processing. Ta đang biên dịch chính processor, vì vậy chưa cần chạy processor.

Bước 2 — biên dịch ứng dụng và kích hoạt processor:

~~~text
javac -cp processor-out -processorpath processor-out -processor demo.GreetingProcessor -s generated-src -d app-out src/demo/App.java
~~~

Ý nghĩa các tùy chọn:

- `-cp processor-out`: compiler tìm annotation `GenerateGreeting` trong thư mục này.
- `-processorpath processor-out`: compiler tìm class processor và dependency của processor ở đây.
- `-processor demo.GreetingProcessor`: yêu cầu compiler chạy processor có tên đầy đủ này.
- `-s generated-src`: đặt các source file được sinh vào thư mục `generated-src`.
- `-d app-out`: đặt class file đầu ra vào `app-out`.

Sau bước 2, thư mục `generated-src` có source được sinh tương tự:

~~~java
package demo;

public final class AppGreeting {
    private AppGreeting() {}

    public static String message() {
        return "Hello, Java!";
    }
}
~~~

Compiler tiếp tục biên dịch source được sinh trong các round kế tiếp. Vì vậy `AppGreeting.class` cũng được tạo trong `app-out`.

Bước 3 — chạy ứng dụng:

~~~text
java -cp app-out demo.App
~~~

Stdout:

~~~text
Hello, Java!
~~~

Ví dụ này minh họa toàn bộ luồng: annotation cung cấp dữ liệu, processor đọc dữ liệu, `Filer` tạo source và compiler biên dịch source đó để ứng dụng sử dụng.

## 6. Khám phá các API quan trọng

### 6.1. `Element` và `TypeMirror`

`Element` biểu diễn một khai báo trong chương trình, chẳng hạn:

- `PackageElement`: package.
- `TypeElement`: class, interface, enum hoặc record.
- `ExecutableElement`: method hoặc constructor.
- `VariableElement`: field, parameter hoặc biến local.
- `TypeParameterElement`: tham số kiểu generic.

`TypeMirror` biểu diễn một kiểu dữ liệu. Processor có thể lấy kiểu trả về, kiểu tham số, kiểu generic và so sánh kiểu qua `Types`.

Không nên dùng `element.toString()` làm cách phân tích kiểu tổng quát. Hãy dùng `TypeMirror`, `Types` và `Elements` để kiểm tra kiểu theo mô hình ngôn ngữ.

### 6.2. `Elements` và `Types`

`Elements` hỗ trợ:

- Tra cứu package và type theo tên đầy đủ.
- Lấy package chứa một element.
- Đọc thông tin annotation và thành viên.
- Lấy tên nhị phân hoặc tên đầy đủ của kiểu.

`Types` hỗ trợ:

- Kiểm tra hai kiểu có tương thích hoặc cùng kiểu hay không.
- Kiểm tra subtype và assignability.
- Xóa generic type bằng erasure.
- Làm việc với declared type, array type, executable type và type variable.

Các API này giúp processor xác nhận hợp đồng kiểu. Ví dụ processor có thể kiểm tra class được annotation có implement một interface yêu cầu hay không trước khi sinh adapter.

### 6.3. `Filer`

`Filer` là API chuẩn để tạo output trong quá trình annotation processing:

- `createSourceFile(...)`: tạo tệp `.java`.
- `createClassFile(...)`: tạo class file.
- `createResource(...)`: tạo resource trong một location và package tương ứng.

Dùng `Filer` thay vì ghi file tùy ý vào thư mục source của dự án. Compiler và build tool cần biết file nào được sinh, vị trí output và mối liên hệ với source đầu vào để quản lý round, incremental build và diagnostic.

Không sửa source file đầu vào bằng processor. Nếu cần sinh mã thay thế, tạo file mới với tên hợp lệ và không trùng.

### 6.4. `Messager`

Dùng `Messager` để báo kết quả xử lý:

~~~java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.WARNING,
        "Annotation này đang được dùng theo cách cũ",
        element);
~~~

Các loại diagnostic thường dùng:

- `NOTE`: thông tin.
- `WARNING`: cảnh báo, thường không làm compiler thất bại.
- `MANDATORY_WARNING`: cảnh báo bắt buộc được báo.
- `ERROR`: lỗi làm lần biên dịch thất bại.

Nên gắn diagnostic với element hoặc annotation value khi có thể. IDE có thể dùng thông tin đó để đưa người phát triển đến đúng vị trí.

## 7. Phát hiện và cấu hình processor

Có hai cách phổ biến để compiler biết processor cần chạy.

### 7.1. Chỉ định tường minh bằng `-processor`

Ví dụ:

~~~text
javac -processorpath processor-out -processor demo.GreetingProcessor -d out src/demo/App.java
~~~

`-processor` nhận tên đầy đủ của processor. Đây là cách rõ ràng và dễ kiểm soát khi thử nghiệm hoặc chẩn đoán một processor cụ thể.

### 7.2. Tự phát hiện qua service provider

Một thư viện processor có thể đóng gói tệp:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nội dung là tên đầy đủ của từng processor, mỗi tên trên một dòng:

~~~text
demo.GreetingProcessor
~~~

Khi processor nằm trên processor path và được compiler phát hiện qua service provider, compiler có thể tự nạp nó mà không cần `-processor` chỉ rõ từng tên.

Với processor được đóng gói thành named module, module descriptor có thể khai báo service provider bằng `provides javax.annotation.processing.Processor with ...`. Cấu hình module và module path phải phù hợp với cách compiler nạp processor.

Khi cần build tái hiện được, hãy cấu hình processor path và dependency một cách tường minh. Việc dựa vào classpath chung để vô tình phát hiện processor có thể làm build khó kiểm soát và gây khác biệt giữa máy cá nhân, IDE và CI.

## 8. Các tùy chọn `javac` liên quan đến annotation processing

| Tùy chọn | Công dụng |
|---|---|
| `-processorpath` / `--processor-path` | Chỉ định nơi tìm annotation processor và dependency của nó |
| `-processor` | Chỉ định tên processor cần chạy |
| `-proc:none` | Tắt annotation processing |
| `-proc:only` | Chỉ chạy annotation processing, không thực hiện biên dịch thông thường |
| `-s directory` | Chỉ định nơi lưu source file được sinh |
| `-d directory` | Chỉ định nơi lưu class file |
| `-Akey=value` | Truyền tùy chọn cho processor |
| `-XprintRounds` | In thông tin về các processing round |
| `-XprintProcessorInfo` | In thông tin processor được gọi và annotation được xử lý |

Ví dụ chẩn đoán round và processor:

~~~text
javac -XprintRounds -XprintProcessorInfo -cp processor-out -processorpath processor-out -processor demo.GreetingProcessor -s generated-src -d app-out src/demo/App.java
~~~

Các tùy chọn bắt đầu bằng `-X` là tùy chọn nâng cao; kiểm tra `javac --help` và tài liệu của JDK cụ thể nếu compiler không hỗ trợ một tùy chọn.

### 8.1. Truyền cấu hình cho processor bằng `-A`

Processor có thể khai báo các option được hỗ trợ bằng `@SupportedOptions` hoặc override `getSupportedOptions()`.

Ví dụ lệnh:

~~~text
javac -Aconfig=production -processorpath processor-out -processor demo.GreetingProcessor -d out src/demo/App.java
~~~

Trong processor, đọc giá trị bằng:

~~~java
String config = processingEnv.getOptions().get("config");
~~~

Option của processor là cấu hình compile-time. Nó không tự động trở thành system property trong JVM chạy ứng dụng.

## 9. Annotation processing trong Maven và Gradle

Trong dự án thật, build tool nên quản lý processor như một dependency riêng. Tách dependency chứa annotation/API khỏi dependency chứa processor giúp tránh đưa compiler plugin vào runtime classpath của ứng dụng.

### 9.1. Maven

Ví dụ cấu hình Maven Compiler Plugin:

~~~xml
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
                <version>1.0.0</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
~~~

Nếu annotation được đóng gói thành artifact riêng, khai báo artifact annotation như dependency compile-time của ứng dụng. Processor và các dependency chỉ phục vụ xử lý lúc biên dịch được đưa vào `annotationProcessorPaths`.

Chạy build:

~~~text
mvn clean compile
~~~

Tên artifact, phiên bản plugin và dependency trong ví dụ là minh họa; thay bằng tọa độ thực tế của dự án.

### 9.2. Gradle

Ví dụ Gradle Kotlin DSL:

~~~kotlin
dependencies {
    compileOnly("com.example:greeting-annotations:1.0.0")
    annotationProcessor("com.example:greeting-processor:1.0.0")
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

- `compileOnly` cung cấp annotation API khi biên dịch ứng dụng nhưng không tự đưa dependency đó vào runtime.
- `annotationProcessor` đặt processor vào configuration riêng dành cho annotation processing.
- `toolchain` chọn JDK dùng để build theo phiên bản đã chỉ định.

Chạy:

~~~text
./gradlew clean compileJava
~~~

Trên Windows thường dùng:

~~~text
gradlew.bat clean compileJava
~~~

Gradle quản lý thư mục source được sinh và output của annotation processor trong build directory. Không nên commit output sinh tự động nếu dự án không có yêu cầu riêng.

## 10. Các lỗi thường gặp

### Processor không được gọi

**Biểu hiện:** annotation có trong source nhưng không có source/resource nào được sinh.

**Nguyên nhân có thể:**

- Processor không nằm trên processor path.
- Tên trong `-processor` sai.
- Service provider file thiếu hoặc sai tên.
- Processor không hỗ trợ annotation đang dùng.
- Build tool chưa cấu hình annotation processor dependency.
- Annotation processing bị tắt bằng `-proc:none`.

**Cách xử lý:** kiểm tra processor path, tên đầy đủ, service provider và cấu hình build. Thử chỉ định tường minh `-processor` và dùng `-XprintRounds -XprintProcessorInfo` để xem compiler có gọi processor không.

### `cannot find symbol` cho lớp được sinh

**Biểu hiện:** ứng dụng tham chiếu lớp sinh tự động nhưng compiler báo không tìm thấy.

**Nguyên nhân có thể:**

- Processor chưa chạy hoặc không nhận diện annotation.
- Processor tạo tên package/tên lớp khác với tên ứng dụng gọi.
- Processor báo lỗi trước khi tạo file.
- Source file được ghi trực tiếp ngoài `Filer` nên compiler không đưa vào round.
- Output source/class path hoặc build cache không đồng bộ.

**Cách xử lý:** kiểm tra source output từ `-s`, diagnostic của processor, tên đầy đủ của lớp sinh và cấu hình processor trong build tool. Xóa build output cũ bằng clean build nếu có bằng chứng output stale.

### `FilerException: Attempt to recreate a file`

**Nguyên nhân:** processor cố tạo cùng một source/resource nhiều lần, thường do xử lý lại cùng element ở nhiều round hoặc nhiều processor cùng sinh một tên.

**Cách xử lý:** chọn tên output duy nhất, kiểm soát round, tránh sinh file khi không cần và xác định quyền sở hữu tên output giữa các processor.

### `NoClassDefFoundError` khi compiler nạp processor

**Nguyên nhân:** processor có dependency nhưng dependency đó không nằm trên processor path hoặc phiên bản không tương thích.

**Cách xử lý:** thêm dependency cần thiết vào cấu hình annotation processor riêng của Maven/Gradle hoặc processor path. Runtime classpath của ứng dụng không thay thế processor path trong lúc biên dịch.

### Processor báo không hỗ trợ source version

**Nguyên nhân:** processor khai báo source version cũ hơn phiên bản ngôn ngữ mà compiler đang dùng hoặc processor chưa được cập nhật.

**Cách xử lý:** cập nhật processor và `@SupportedSourceVersion` theo mức ngôn ngữ mà processor đã kiểm thử. Không khai báo một source version mới hơn chỉ để tắt warning nếu processor chưa thật sự hỗ trợ các cấu trúc đó.

### Build chạy khác nhau giữa IDE và CI

**Nguyên nhân:** IDE và CI dùng JDK, processor path, option `-A`, dependency hoặc cấu hình incremental build khác nhau.

**Cách xử lý:** đưa cấu hình processor vào build tool, thống nhất JDK/toolchain và dependency version, rồi chạy clean build trong môi trường CI.

## 11. Thiết kế annotation processor tốt

Một processor ổn định cần chú ý:

1. **Xử lý đúng phạm vi annotation:** khai báo `@SupportedAnnotationTypes` chính xác, kiểm tra element kind và báo lỗi dễ hiểu.
2. **Không giả định thứ tự xử lý:** nhiều processor có thể chạy trong một round; không dựa vào thứ tự không được bảo đảm.
3. **Hỗ trợ nhiều round:** tránh tạo file trùng và xử lý đúng source được sinh từ round trước.
4. **Dùng `Filer`:** để compiler và build tool quản lý output.
5. **Dùng `Messager`:** báo lỗi gắn với element thay vì ném exception chung chung.
6. **Tôn trọng kiểu Java:** dùng `Elements`, `Types`, `Element` và `TypeMirror`, không phân tích source bằng regex.
7. **Giữ output xác định:** cùng input và option nên tạo cùng nội dung output; tránh phụ thuộc thời gian, thư mục máy cá nhân hoặc thứ tự file không ổn định.
8. **Công bố option:** khai báo `@SupportedOptions` và kiểm tra giá trị đầu vào.
9. **Không sửa source gốc:** sinh tệp mới có tên duy nhất và để build tool quản lý.
10. **Tương thích phiên bản:** khai báo source version phù hợp và kiểm thử processor với JDK/toolchain mục tiêu.

Annotation processor là mã thực thi trong quá trình build, vì vậy chỉ thêm processor từ nguồn đáng tin cậy. Một processor có thể đọc mã nguồn và thực hiện các thao tác mà tài khoản chạy build được phép thực hiện; quản lý nó như một plugin build có quyền thực thi mã.

## 12. Khi nào nên dùng annotation processing?

Annotation processing phù hợp khi thông tin cần thiết đã có trong cấu trúc Java và có thể kiểm tra hoặc chuyển thành mã lúc biên dịch:

- Sinh implementation từ interface hoặc annotation.
- Tạo mapper giữa các kiểu dữ liệu.
- Sinh builder, adapter hoặc metadata.
- Kiểm tra quy tắc kiến trúc hoặc API.
- Sinh registry, serializer hoặc schema.
- Báo lỗi cấu hình trước khi ứng dụng chạy.

Không nên dùng processor chỉ để thay thế một đoạn code ngắn mà không có lợi ích rõ ràng. Processor làm build phức tạp hơn, cần quản lý phiên bản, tương thích compiler và cấu hình IDE/CI.

Nếu yêu cầu chỉ là đọc annotation khi chương trình chạy, dùng reflection và retention phù hợp. Nếu cần thay đổi mã nguồn rộng hoặc biến đổi cú pháp phức tạp, hãy đánh giá công cụ compiler/plugin chuyên dụng thay vì cố ép annotation processing làm nhiệm vụ ngoài thiết kế.

## 13. Checklist chẩn đoán annotation processing

- [ ] Annotation có khai báo `@Target` và `@Retention` phù hợp.
- [ ] Processor mở rộng `AbstractProcessor` và triển khai `process(...)`.
- [ ] `@SupportedAnnotationTypes` khớp tên annotation đầy đủ.
- [ ] `@SupportedSourceVersion` phản ánh phiên bản processor đã hỗ trợ.
- [ ] Processor và dependency nằm trên processor path.
- [ ] Annotation API nằm trên compile classpath/module path của ứng dụng.
- [ ] Processor được phát hiện bằng `-processor` hoặc service provider hợp lệ.
- [ ] `-proc:none` không vô tình tắt processing.
- [ ] Source được sinh qua `Filer`, không ghi thủ công vào source tree.
- [ ] `-s` và `-d` trỏ đến output directory phù hợp.
- [ ] Không có lỗi `Messager` hoặc trùng tên output.
- [ ] Generated source được compiler xử lý trong round tiếp theo.
- [ ] Maven/Gradle/IDE/CI dùng cùng cấu hình processor và JDK.
- [ ] Chạy clean build và kiểm tra output sinh ra.

Annotation processing là cầu nối giữa metadata trong source và mã được tạo tự động ngay trong quá trình biên dịch. Khi hiểu vị trí của nó trong compilation pipeline, cơ chế rounds, các API `Filer`/`Messager` và cách cấu hình processor path, bạn có thể xây dựng code generator có kiểm soát, dễ chẩn đoán và tái hiện nhất quán giữa máy phát triển với CI.