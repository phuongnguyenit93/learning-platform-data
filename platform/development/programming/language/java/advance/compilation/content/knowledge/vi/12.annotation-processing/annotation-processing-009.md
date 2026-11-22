# Theo dõi vòng xử lý annotation và chẩn đoán processor không được gọi

**Annotation processing** là cơ chế để công cụ biên dịch Java gọi các *annotation processor* nhằm đọc mô hình khai báo, kiểm tra quy ước hoặc sinh source/resource bổ sung. Processor triển khai API `javax.annotation.processing.Processor`, thường kế thừa `AbstractProcessor`; compiler cung cấp `ProcessingEnvironment` và gọi `process(...)` khi processor phù hợp với các annotation của vòng xử lý.

Khi annotation processor “không chạy”, có nhiều nguyên nhân khác nhau: processing bị tắt; processor không được tìm thấy; service registration sai; annotation được khai báo ở namespace khác; supported annotation types không khớp; processor được phát hiện nhưng không được chọn để chạy; processor chạy nhưng không có element phù hợp; processor bị processor khác claim annotation; hoặc file sinh ra nằm ở output khác dự kiến. Vì vậy phải phân biệt **discovery → invocation → annotation matching → processing rounds → file generation** trước khi sửa.

Trong JDK 23 trở đi, `javac` không còn chủ động tìm và chạy processor chỉ vì trên classpath có processor khi không có cấu hình xử lý annotation rõ ràng. Trên JDK 21/22, hành vi mặc định lịch sử khác. Muốn bản dựng tái lập, **khai báo tường minh processor và processor path**, đồng thời quan sát diagnostic và generated files thay vì dựa vào mặc định của JDK.

## 1. Vòng xử lý annotation là gì?

Compiler làm việc với một tập các *root elements* trong vòng đầu tiên, thông thường là những top-level declarations của các compilation units được biên dịch. Một processor có thể đọc các element có annotation được hỗ trợ và dùng `Filer` tạo thêm file nguồn. Những source mới có thể trở thành root elements ở **vòng kế tiếp**. Cuối quá trình có một vòng kết thúc cho phép processor biết rằng sẽ không còn vòng xử lý source mới.

```text
Source được đưa vào javac
        |
        v
 Round 1: roots ban đầu
   - tìm annotation được hỗ trợ
   - gọi processor được chọn
   - processor có thể tạo Generated.java
        |
        v
 Round 2: roots từ source vừa tạo
   - xem annotation mới xuất hiện
   - tiếp tục gọi processor đã hoạt động
   - processor có thể tạo thêm source
        |
       ...
        |
        v
 Final round: processingOver() == true
        |
        v
 Compiler tiếp tục các bước biên dịch và sinh .class
```

Đây là sơ đồ khái niệm. Số vòng phụ thuộc việc có file mới, processor và triển khai compiler. **Không mặc định mọi lần chạy có đúng hai hoặc ba vòng**; đừng dùng số vòng cố định làm điều kiện build thành công.

`RoundEnvironment` cung cấp các tín hiệu quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `getRootElements()` | Những root elements được đưa tới vòng hiện tại, thường bao gồm các kiểu tạo trong vòng trước |
| `getElementsAnnotatedWith(...)` | Các element thuộc phạm vi round có annotation được hỏi |
| `processingOver()` | `true` khi vòng này là vòng cuối; output sinh ở vòng ấy sẽ không được xử lý trong một vòng kế tiếp |
| `errorRaised()` | `true` nếu vòng **trước** đã có error được báo |

`processingOver()` có thể là `true` dù `getRootElements()` trống. Không nên cố sinh source mới trong final round rồi chờ compiler quay lại xử lý nó. `errorRaised()` không phải là đồng hồ đếm tổng lỗi hay dấu hiệu khẳng định processor “chưa chạy”.

## 2. Quy trình discovery và invocation

Một processor chỉ được gọi nếu nhiều bước đều phù hợp:

1. **Processing được bật:** `javac` phải ở chế độ chạy annotation processing.
2. **Compiler tìm thấy class của processor:** classpath, processor path hoặc processor module path được cấu hình đúng.
3. **Processor có thể được phát hiện:** qua `-processor tên.Class`, qua service loader đăng ký đúng, hoặc cơ chế do tool cung cấp.
4. **Processor hỗ trợ annotation trong vòng:** kết quả `getSupportedAnnotationTypes()`, thường khai báo bởi `@SupportedAnnotationTypes`, phải phù hợp với các annotation mà công cụ muốn xử lý; `"*"` biểu thị processor phổ quát.
5. **Processor được chọn và gọi:** compiler gọi `init` rồi `process` theo giao thức. Annotation có thể đã được một processor khác claim, ảnh hưởng việc processor phía sau được yêu cầu xử lý.
6. **Processor thực hiện công việc đúng:** duyệt `RoundEnvironment`, sinh file hoặc phát diagnostic, tránh lỗi/exception.
7. **Output được sử dụng đúng:** generated source/class/resources nằm ở các output location đang được compiler hoặc build tool sử dụng.

Chỉ thấy class processor trong JAR **không chứng minh nó được khởi tạo**. Chỉ thấy một annotation trên source **không chứng minh processor sẽ xử lý nó**. Một annotation có thể mang `RetentionPolicy.SOURCE` và vẫn được annotation processor xử lý trong lúc compile; retention runtime không phải điều kiện bắt buộc.

Theo API `Processor`, compiler có thể gọi `process` nhiều lần **trên cùng instance**, gồm những vòng không còn annotation cần xử lý, nếu processor đã được chọn trong vòng trước. Không nên tạo state toàn cục giả định rằng luôn có một processor object mới cho mỗi vòng.

## 3. Các tùy chọn javac cần biết

| Tùy chọn | Công dụng |
| --- | --- |
| `-processor demo.MarkProcessor` | Chỉ định chính xác processor cần gọi, bỏ qua bước tự dò tên processor từ service registration |
| `-processorpath path` hoặc `--processor-path path` | Đường dẫn dùng để tìm processor trên classpath processor |
| `--processor-module-path path` | Module path để tìm processor đóng gói theo module |
| `-proc:none` | Tắt annotation processing, vẫn tiến hành biên dịch |
| `-proc:only` | Chạy annotation processing mà không thực hiện bước sinh class thông thường sau đó |
| `-proc:full` | Chạy annotation processing rồi biên dịch đầy đủ; hỗ trợ từ JDK 21, được backport ở các bản cập nhật JDK cũ nhất định |
| `-XprintRounds` | In thông tin các vòng annotation processing |
| `-XprintProcessorInfo` | In thông tin processor được yêu cầu xử lý annotation nào |
| `-s path` | Chọn thư mục ghi **generated source** |
| `-d path` | Chọn thư mục ghi **compiled class** |
| `-Akey=value` | Truyền option do processor khai báo hỗ trợ; compiler không tự hiểu semantics của `key` |

`-XprintRounds` và `-XprintProcessorInfo` là **cờ phục vụ chẩn đoán** của `javac`. Nội dung, số dòng, thứ tự và vị trí in phụ thuộc phiên bản/compiler; dùng để quan sát trong log, không biến văn bản của chúng thành giao thức bắt buộc cho automation.

`-processorpath` là nơi **nạp class processor**, không đồng nghĩa đường dẫn biên dịch các kiểu nghiệp vụ. Những annotation và dependency mà source ứng dụng cần vẫn phải có trên compile classpath hoặc module path tương ứng. Nếu processor phụ thuộc một thư viện helper khi chạy, helper ấy cũng phải nằm trên processor path hoặc cấu hình class loader của processor.

Để kiểm tra cờ khả dụng của JDK đang dùng, chạy `javac -version`, `javac -help` và `javac -X`. Đừng dựa vào cùng một default giữa JDK 17, 21 và 23+.

## 4. JDK 23 thay đổi mặc định annotation processing

Với `javac` tới JDK 22, nếu processor hiện diện theo cơ chế tìm kiếm trên classpath, nhiều build cũ tự chạy processing **mà không khai báo option xử lý annotation rõ ràng**. JDK 21/22 có thông báo cảnh báo về kiểu cấu hình phụ thuộc vào default này.

**Từ JDK 23**, khi không có cấu hình/request xử lý annotation tường minh, `javac` **không mặc định chạy annotation processor**. Có thể chỉ định:

```bash
javac -processor demo.MarkProcessor -processorpath build/processor ...
```

hoặc cơ chế khác như cấu hình đường dẫn processor thích hợp, `-proc:full` hay `-proc:only` theo phiên bản.

Nếu build nâng JDK và plötzlich không có generated class như `MapperImpl` hoặc `QCustomer`, hãy kiểm tra compile arguments. Một processor JAR tình cờ nằm trên classpath trước đây **không đủ để kết luận** nó sẽ tự được chạy trên JDK mới.

`-proc:full` chỉ yêu cầu chạy xử lý annotation và compile; nó **không tạo processor từ hư không**. Cần một processor có thể được tìm thấy hoặc được chỉ định. Với processor mình kiểm soát, `-processor` cộng processor path tường minh giúp kết quả dễ kiểm chứng hơn.

Cần phân biệt thay đổi compiler với quyết định của Maven Compiler Plugin, Gradle JavaCompile, IDE hoặc tool khác: chúng có thể truyền option riêng và có cơ chế incremental compilation. Đọc **command/compiler arguments thực tế** của task trước khi kết luận “JDK không chạy processor”.

## 5. Ví dụ Java 17+ tự biên dịch: processor sinh source qua nhiều vòng

Ví dụ dưới đây có một annotation `@Mark`, một processor `MarkProcessor` và một class `Example` phụ thuộc vào class `Generated` được processor tạo ra. Nó không cần thư viện ngoài JDK.

Cây thư mục:

```text
apt-lab/
  src/
    demo/
      Mark.java
      Example.java
    processor/
      demo/
        MarkProcessor.java
  build/
    processor/       (tạo trước, ban đầu trống)
    classes/         (tạo trước, ban đầu trống)
    generated/       (tạo trước, ban đầu trống)
```

### File 1: src/demo/Mark.java

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface Mark {
}
```

`SOURCE` retention làm annotation khả dụng lúc xử lý source, không nhất thiết được ghi để đọc qua reflection runtime. Processor không cần annotation có `RUNTIME` retention.

### File 2: src/processor/demo/MarkProcessor.java

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
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.Mark")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class MarkProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {

        processingEnv.getMessager().printMessage(
                Diagnostic.Kind.NOTE,
                "round: final=" + round.processingOver()
                        + ", roots=" + round.getRootElements().size()
                        + ", errorBefore=" + round.errorRaised()
        );

        if (round.processingOver()) {
            return true;
        }

        Set<? extends Element> matched =
                round.getElementsAnnotatedWith(Mark.class);

        if (!generated && !matched.isEmpty()) {
            try {
                JavaFileObject file = processingEnv.getFiler()
                        .createSourceFile("demo.Generated");

                try (Writer writer = file.openWriter()) {
                    writer.write(
                            "package demo;\n"
                            + "public final class Generated {\n"
                            + "  private Generated() {}\n"
                            + "  public static String text() {\n"
                            + "    return \"generated\";\n"
                            + "  }\n"
                            + "}\n"
                    );
                }

                generated = true;
            } catch (IOException exception) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "generation failed: " + exception.getMessage()
                );
            }
        }

        return true;
    }
}
```

Những điểm đáng quan sát:

- `@SupportedAnnotationTypes("demo.Mark")` là tên đầy đủ của annotation mà processor nhận.
- `@SupportedSourceVersion(RELEASE_17)` khai báo hỗ trợ Java 17; lab biên dịch với `--release 17` để nhất quán.
- `getRootElements()` giúp nhận biết roots của vòng hiện tại.
- `getElementsAnnotatedWith(Mark.class)` trả các element mang `@Mark` trong phạm vi round; ở vòng sinh source mới, tập đó có thể rỗng.
- `processingOver()` nhận ra vòng cuối để không sinh file mới lúc không còn vòng tiếp.
- Cờ `generated` ngăn tạo lại cùng fully qualified name ở nhiều round.
- `Filer.createSourceFile("demo.Generated")` tạo file Java mới ở source output location; `Writer` phải được đóng để nội dung được compiler xử lý.
- `Messager` phát `NOTE` và `ERROR` để người vận hành quan sát qua compiler diagnostics. Nó tốt hơn ghi log tùy ý vào stdout.
- `return true` có nghĩa processor **claim những annotation types được yêu cầu xử lý**. Nếu processor universal (`"*"`) return true, nó có thể ngăn processor khác nhận annotation; không dùng hành vi ấy một cách vô tình.

### File 3: src/demo/Example.java

```java
package demo;

@Mark
public class Example {
    public static void main(String[] args) {
        System.out.println(Generated.text());
    }
}
```

`Generated` chưa tồn tại trước khi build. Nếu processing hoạt động, processor sinh nó và compiler biên dịch cùng chương trình. Nếu processing bị tắt, compiler thường báo không phân giải được `Generated`.

### Chạy theo hai bước để tránh vòng tự khởi tạo processor

Chạy từ thư mục `apt-lab`. Tạo ba output directory; với Bash:

```bash
mkdir -p build/processor build/classes build/generated
```

Với Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path build/processor,build/classes,build/generated | Out-Null
```

Bước A — **biên dịch annotation type và processor trước**, chưa chạy annotation processing:

```bash
javac --release 17 -encoding UTF-8 -proc:none -d build/processor src/demo/Mark.java src/processor/demo/MarkProcessor.java
```

Ở bước này, output có tối thiểu:

```text
build/processor/demo/Mark.class
build/processor/demo/MarkProcessor.class
```

Bước B — **biên dịch ứng dụng và chỉ định processor tường minh**:

```bash
javac --release 17 -encoding UTF-8 -cp build/processor -processorpath build/processor -processor demo.MarkProcessor -XprintRounds -XprintProcessorInfo -s build/generated -d build/classes src/demo/Example.java
```

Lưu ý:

- `-cp build/processor` giúp compiler tìm annotation `demo.Mark` mà `Example.java` sử dụng.
- `-processorpath build/processor` giúp compiler tìm/nạp `demo.MarkProcessor` và dependency `demo.Mark` của processor.
- `-processor demo.MarkProcessor` chọn processor trực tiếp, không cần tạo `META-INF/services` cho demo.
- `-XprintRounds` và `-XprintProcessorInfo` giúp xem số vòng và các processor được yêu cầu xử lý annotation.
- `-s build/generated` ghi source sinh ra; `-d build/classes` ghi class files.
- `--release 17` làm rõ phiên bản Java target và giữ tương thích với `RELEASE_17`.

Nếu build thành công, source output có:

```text
build/generated/demo/Generated.java
```

Class output có:

```text
build/classes/demo/Example.class
build/classes/demo/Generated.class
```

Chạy:

```bash
java -cp build/classes demo.Example
```

Stdout chương trình chính xác:

```text
generated
```

**Đừng nhầm stdout này với log `javac`.** Cảnh báo/NOTE, Round 1/2/final và thông tin processor có thể được in theo nhiều dòng và thay đổi theo JDK; không cố định nguyên văn chúng. Điều cần xác minh là compiler trả success, processor có NOTE và `-XprintProcessorInfo` thích hợp, generated source/class tồn tại, và chương trình chạy in `generated`.

## 6. Quan sát các round của ví dụ

Trong lần biên dịch B, có thể diễn giải các vòng như sau:

| Vòng | Roots quan trọng | Processor làm gì |
| --- | --- | --- |
| Vòng đầu | `demo.Example` | Phát hiện `@Mark`; tạo `demo.Generated` |
| Vòng tiếp | `demo.Generated` | Không còn `@Mark` trong source mới; processor đã hoạt động nên vẫn có thể nhận lời gọi tiếp |
| Vòng cuối | Có thể rỗng | `round.processingOver() == true`; không tạo source mới |

Compiler chịu trách nhiệm quyết định lịch xử lý thực tế; `-XprintRounds` cho biết vòng nào đã chạy. Nếu một processor sinh nhiều file ở các vòng kế tiếp, số vòng có thể tăng. Nếu processor không sinh file mới, quá trình thường kết thúc sớm hơn.

Khi đọc NOTE từ processor, chú ý `errorRaised()` chỉ phản ánh lỗi đã được báo ở vòng trước. Không thể kết luận toàn bộ build thành công khi một vòng chưa có error: compiler có thể tiếp tục kiểm tra kiểu và phát lỗi ở giai đoạn sau.

**Quan trọng:** `getRootElements()` không phải danh sách mọi class đã tồn tại trên classpath hay trong project; nó là các roots của vòng hiện tại. Processor không được gọi cho từng class một cách máy móc. Tương tự, `getElementsAnnotatedWith(...)` không trả mọi element được chú thích trong toàn bộ dependency graph; nó giới hạn theo mô hình round/annotation của API.

## 7. Tình huống processor thực sự không được gọi

Một số ca điển hình:

### A. Processing bị tắt

```bash
javac --release 17 -cp build/processor -proc:none -d build/classes src/demo/Example.java
```

Trong một output rỗng, lệnh này không chạy `MarkProcessor`, nên không tạo `Generated`; `Example` dùng `Generated` sẽ không biên dịch được. `-proc:none` là cách tắt rõ ràng, thường dùng khi compile chính processor hoặc khi cố ý không chạy APT.

### B. JDK 23+ không có cấu hình processing

Một lệnh chỉ có `-cp` mà không có `-processor`, `--processor-path`, `--processor-module-path`, `-proc:only` hoặc `-proc:full` có thể **không chạy APT trên JDK 23+**. Với JDK 21/22, hành vi mặc định trước đây khác. Sửa bằng cấu hình tường minh và kiểm tra task compiler thật, không suy luận từ mỗi phiên bản JDK được cài trên máy.

### C. Processor không nằm trên processor path

Ví dụ đặt `-processor demo.MarkProcessor` nhưng `-processorpath` không chứa `demo/MarkProcessor.class` hoặc JAR của nó. Compiler có thể báo `Annotation processor 'demo.MarkProcessor' not found`; phải sửa artifact và đường tìm, không phải thêm `import demo.MarkProcessor` vào source nghiệp vụ.

### D. Processor có mặt nhưng annotation không khớp

`@SupportedAnnotationTypes("demo.Mark")` không bắt được một annotation khác như `com.other.Mark` dù cùng simple name `Mark`. Nếu processor chỉ hỗ trợ `demo.Mark` nhưng source đang dùng `@OtherMark`, compiler có thể không chọn processor để chạy vì không có annotation phù hợp.

Với processor phục vụ kiểm tra mọi file ngay cả khi không có annotation, có thể khai báo `@SupportedAnnotationTypes("*")` và trả `false` nếu không muốn claim annotation của processor khác. Đây là lựa chọn thiết kế cần cân nhắc, không phải mẹo bắt mọi lỗi bằng cách claim toàn bộ annotation.

### E. Khai báo service provider sai

Khi không dùng `-processor` và muốn discovery qua classpath processor, JAR cần có file:

```text
META-INF/services/javax.annotation.processing.Processor
```

Nội dung một dòng:

```text
demo.MarkProcessor
```

Đường dẫn phải đúng chữ hoa/thường, tên class fully qualified chính xác, file phải **nằm trong JAR processor**, và processor/dependency phải nạp được. Class processor có thể có mặt nhưng service file thiếu; nếu chỉ chờ auto-discovery, processor sẽ không chạy.

Với named module chứa processor, có thể khai báo `provides javax.annotation.processing.Processor with ...;` và dùng `--processor-module-path` theo quy tắc JPMS. Không mặc định service file dành cho classpath và module descriptor là cùng cơ chế discovery.

### F. Processor đã chạy nhưng “không tạo gì”

Một processor có thể được gọi với `annotations` rỗng hoặc `round.getElementsAnnotatedWith(...)` rỗng, và cố tình không sinh file. Điều này khác với processor không được nạp.

Kiểm tra `-XprintProcessorInfo`, `-XprintRounds` và diagnostic `Messager` trong `process`. Nếu đã có log do `process` phát ra nhưng không có generated source, hãy kiểm tra điều kiện tạo file, tên annotation và `Filer`.

### G. Processor khác claim annotation

Nếu một processor trả `true` để claim annotation type, các processor tiếp theo trong cùng round có thể không được yêu cầu xử lý annotation ấy. Xác minh thứ tự/selection và chính sách claim của từng processor, đặc biệt khi một processor phổ quát dùng `"*"`.

Không nên mặc định “cài thêm processor thứ hai” sẽ làm cả hai cùng nhận một annotation; cần xem từng processor hỗ trợ annotation nào và liệu có claim annotation hay không.

## 8. Processor chạy nhưng file sinh không được tìm thấy

Người học hay kiểm tra nhầm nơi:

| Artifact | Nơi chứa theo lệnh ví dụ | Cách kiểm tra |
| --- | --- | --- |
| Annotation/processor đã biên dịch | `build/processor/demo/*.class` | Kiểm tra class và package path |
| Generated Java source | `build/generated/demo/Generated.java` | Kiểm tra `-s` |
| Generated class | `build/classes/demo/Generated.class` | Kiểm tra `-d` |
| Class chính | `build/classes/demo/Example.class` | Kiểm tra output compile |
| Classpath khi chạy | `build/classes` | Chạy `java -cp build/classes demo.Example` |

`-s` chọn source output location của compiler; `-d` chọn class output location. Tạo source **không tự đảm bảo** một framework hoặc Gradle task khác đã nhận đúng source folder; nếu tool sử dụng build caches hoặc incremental compilation, cần kiểm tra đường output thực tế của task.

Những lỗi khác:

- Processor tạo file bằng `Filer.createResource` (resource), nhưng người dùng lại tìm `.java`; phải xác định đúng API đã gọi.
- Processor viết file bằng `Files.write` vào một đường tùy ý: compiler không nhất thiết biết đó là generated source để thêm vào round.
- Processor tạo file trùng tên đã tồn tại hoặc tạo cùng name hai lần trong một run: `FilerException` có thể xuất hiện; hãy tạo mỗi fully qualified name một lần.
- File đã tạo nhưng `Writer` không được đóng, source chưa hoàn chỉnh; hãy đóng resource đúng cách.
- Class được sinh ở source output nhưng compile thất bại sau đó: cần đọc diagnostic toàn bộ, không suy ra thành công chỉ vì file Java tồn tại.
- Processor chỉ chạy `-proc:only`: generated Java source có thể có nhưng **normal compilation sau processing không chạy**, nên không được kỳ vọng cùng tập class output như `-proc:full`.

**Điều cần nhớ:** phát hiện processor, chạy processor, tạo source và tạo class file là các mốc riêng; mỗi mốc cần bằng chứng tương ứng.

## 9. Gỡ lỗi qua JavaCompiler API và DiagnosticCollector

Khi build một IDE/plugin hoặc công cụ tự gọi compiler, không nên parse văn bản stderr bằng regex cố định. Dùng `javax.tools.JavaCompiler` và `DiagnosticCollector<JavaFileObject>` để thu thập các diagnostic có loại, source và vị trí, kết hợp kết quả `CompilationTask.call()`.

Ví dụ đoạn mã minh họa **trong một phương thức của công cụ**, không phải chương trình độc lập:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("JDK compiler unavailable");
}

DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();

StandardJavaFileManager files =
        compiler.getStandardFileManager(
                diagnostics, java.util.Locale.ROOT,
                java.nio.charset.StandardCharsets.UTF_8);

Iterable<? extends JavaFileObject> inputs =
        files.getJavaFileObjectsFromStrings(
                java.util.List.of("src/demo/Example.java"));

JavaCompiler.CompilationTask task = compiler.getTask(
        null,
        files,
        diagnostics,
        java.util.List.of(
                "--release", "17",
                "-cp", "build/processor",
                "-processorpath", "build/processor",
                "-processor", "demo.MarkProcessor",
                "-s", "build/generated",
                "-d", "build/classes",
                "-XprintRounds"
        ),
        null,
        inputs
);

boolean succeeded = Boolean.TRUE.equals(task.call());
files.close();
```

Để biên dịch đoạn này thành công khi đặt vào class thật, cần import `javax.tools.JavaCompiler`, `javax.tools.ToolProvider`, `javax.tools.DiagnosticCollector`, `javax.tools.JavaFileObject` và `javax.tools.StandardJavaFileManager`; method bao ngoài phải xử lý `IOException` khi gọi `close()`. Các thư mục output phải tồn tại và processor đã được build.

`Diagnostics.getDiagnostics()` (với tên biến `diagnostics` chữ thường) cho phép duyệt các đối tượng `Diagnostic`. API `Diagnostic.Kind`, `getSource()`, `getLineNumber()` và `getMessage(Locale)` hỗ trợ báo cáo có cấu trúc. Tuy nhiên `getMessage` và `getCode` vẫn có thể thay đổi theo compiler; không nên coi toàn bộ text hoặc compiler-specific code là một tiêu chuẩn định danh lỗi cố định.

API chỉ giúp quan sát lỗi do compiler/processor phát ra; nếu processor không được gọi nhưng compilation vẫn thành công vì generated class cũ đang ở classpath, bạn cũng cần kiểm tra input/output sạch và expected processor invocation riêng.

## 10. Quy trình điều tra processor không được gọi

Bắt đầu từ hiện tượng cụ thể: thiếu generated class, không thấy NOTE, hoặc annotation bị bỏ qua.

**Bước 1 — xác định công cụ và phiên bản.** Ghi `javac -version`, Java toolchain, Maven/Gradle compiler plugin, source/release, JDK của worker CI. JDK 23+ có thay đổi default processing.

**Bước 2 — xem lệnh biên dịch thực.** Kiểm tra `-proc:none`, `-proc:only`, `-proc:full`, `-processor`, `-processorpath`, `--processor-module-path`, `-cp` và `-s`. Một IDE có thể tạo command khác CLI.

**Bước 3 — kiểm tra class processor.** Xác định JAR/class có `demo.MarkProcessor` hay chưa; class có public no-argument constructor mặc định không? Có phụ thuộc processor nào thiếu khiến class loader thất bại không?

**Bước 4 — kiểm tra discovery.** Nếu dùng `-processor`, so tên fully qualified. Nếu dùng auto-discovery, kiểm tra file `META-INF/services/javax.annotation.processing.Processor` hoặc module descriptor `provides` phù hợp.

**Bước 5 — quan sát rounds.** Thêm `-XprintRounds` và `-XprintProcessorInfo` ở môi trường debug. Nếu không có round, kiểm tra chế độ processing/discovery; nếu có round nhưng processor vắng, kiểm tra matching/claiming.

**Bước 6 — log từ trong processor.** `processingEnv.getMessager().printMessage(NOTE, ...)` ở `init` hoặc `process` giúp biết đã vào lifecycle nào. Không dựa trên `System.out.println` và thứ tự stdout của nhiều processor như giao thức ổn định.

**Bước 7 — kiểm tra annotation matching.** Tên đầy đủ, retention, target, các annotation lặp lại và container annotation, supported types; với annotation processor hỗ trợ repeatable annotation, cần xét cả annotation lặp và containing annotation theo API.

**Bước 8 — kiểm tra generated output.** Xác định `-s`, `-d`, tên file, file mở/đóng, lỗi `FilerException`; kiểm tra có generated source mới khi chạy build sạch.

**Bước 9 — kiểm tra annotation claim.** Processor trả `true` có thể claim annotation type khỏi các processor sau. Đừng đặt `"*"` với `return true` nếu công cụ chỉ kiểm tra và không cần độc quyền xử lý.

**Bước 10 — phân biệt kết quả.** Processor có chạy nhưng không tạo gì? Processor không được chọn? Processor tạo file nhưng compile fail? Chỉ sau khi định vị đúng mốc mới sửa.

## 11. Các lỗi và triệu chứng thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra phù hợp |
| --- | --- | --- |
| Không có generated class sau nâng JDK | JDK 23+ thay đổi default APT | Xem compiler options; khai báo processor tường minh |
| `-processor ...` nhưng compiler báo not found | Processor class hoặc dependency không nằm ở processor path | Kiểm tra package, jar contents, đường tìm |
| Processor có trong JAR nhưng không hoạt động | Không khai báo `-processor`, service file thiếu hoặc processing chưa bật | Kiểm tra discovery/processor configuration |
| Có rounds nhưng processor không có trong log | Annotation name/matching sai, processor chưa selected, processor khác claim | `-XprintProcessorInfo` và `@SupportedAnnotationTypes` |
| Có NOTE từ processor nhưng không có generated file | Điều kiện trong `process` không thỏa hoặc Filer lỗi | In size annotation/roots; kiểm tra `-s`, Messager, exception |
| Lần build đầu chạy, lần sau processor dường như vắng | Incremental compilation/cache không thực sự gọi lại javac/processor | Làm một lượt build sạch trong môi trường thử |
| `FilerException` vì file trùng | Tạo cùng source name nhiều lần hoặc đụng input hiện có | Theo dõi per-run generated names; tránh tạo lại ở các round |
| Unsupported source version warning | `@SupportedSourceVersion` thấp hơn `--release`/`-source` đang dùng | Đồng bộ source version trong processor và task |
| `getElementsAnnotatedWith` trống | Annotation khác tên, roots vòng hiện tại không chứa element phù hợp hoặc annotation bị claim | Ghi đủ qualified names, roots, rounds |
| `cannot find symbol Generated` | Processor không sinh, file sinh chưa được compile hoặc path/config sai | Kiểm tra cả processor run, `-s`, `-d` và compiler diagnostics |
| Processor ném exception | Lỗi logic hoặc dependency runtime của processor | Đọc stack trace, processor path và resource lifetime |
| Không thấy NOTE trong CI | Log bị lọc/ẩn bởi build tool, hoặc processor chưa được gọi | Kiểm tra compiler task và generated artifacts, bật debug có chọn lọc |

`-XprintProcessorInfo` chỉ mô tả processor được compiler yêu cầu xử lý các annotation type, không đảm bảo processor đã sinh mọi file cần thiết. File tồn tại trong build directory cũng không chứng minh *lượt chạy hiện tại* tạo ra file ấy.

## 12. Annotation processor và build tool

### Maven

Với Maven Compiler Plugin, cấu hình processor nên nằm ở plugin, không phụ thuộc classpath ứng dụng vô tình chứa processor. Cách đặt option phụ thuộc **phiên bản plugin**; những phiên bản hiện đại có cấu hình annotation processor path/dependency và chính sách `proc` riêng. Khi nâng JDK 23+, kiểm tra bản Maven Compiler Plugin đang dùng và lệnh javac/plugin thực sự sinh.

Các dependency dùng **compile time của ứng dụng** và dependency dùng để **nạp processor** có thể khác nhau. Không cho processor artifact vào runtime dependency của ứng dụng nếu chỉ cần trong lúc build; kiểm tra version và transitive dependencies của processor.

Nếu dùng `-proc:none` trong plugin, nó tắt processing cho task; thêm annotation vào source không làm processor chạy. Nếu dùng `-proc:only`, đừng kỳ vọng có cùng tập class output như một build bình thường.

### Gradle

Với Gradle Java Plugin, processor dependency thường khai báo trong cấu hình `annotationProcessor`, khác với `implementation`:

```groovy
dependencies {
    annotationProcessor 'group:processor-artifact:version'
}
```

Dòng trên **minh họa cú pháp**, tên group/artifact/version phải là dependency có thật của dự án; bản thân nó không phải demo runnable không có thư viện ngoài.

Gradle truyền processor path cho `JavaCompile` dựa trên cấu hình task. Nếu processor có trong `implementation` mà không có trong `annotationProcessor`, không được kết luận processor luôn được gọi. Các source set như `test` cần cấu hình processor tương ứng nếu cần generate code trong test.

Incremental annotation processing còn có ràng buộc về processor *isolating* hoặc *aggregating* tùy Gradle/plugin; processor viết ra file tùy ý bên ngoài `Filer` hoặc đọc input không được công cụ theo dõi có thể khiến incremental build không chính xác. Khi debug, tạm thời làm clean build để loại tác động cache; sau đó khôi phục cơ chế incremental đúng, không vô hiệu hóa vĩnh viễn chỉ vì một lần lỗi.

## 13. Thiết kế processor dễ quan sát và an toàn qua các vòng

Một processor có thể tự làm quá trình debug dễ hơn:

- Dùng `Messager` với kind `NOTE`/`WARNING`/`ERROR` phù hợp, có thể gắn `Element` để compiler hiển thị vị trí nguồn.
- Khi tạo file, dùng `Filer`, đóng writer/output stream đúng cách và truyền originating elements nếu có ích cho incremental tooling.
- Không tạo cùng fully qualified type ở nhiều round; state của processor có thể tồn tại suốt compilation.
- Không dựa vào số thứ tự các rounds hoặc thứ tự duyệt của sets để sinh mã có kết quả khác nhau.
- Phân biệt `processingOver()` và `errorRaised()`; không tạo source mới lúc final round.
- Xử lý việc `annotations` rỗng, `getRootElements()` rỗng và annotation không matching bình thường.
- Cân nhắc `return true`/`false` theo contract claim annotation; processor validator phổ quát không nên vô tình claim hết annotation.
- Tránh quét mutable state toàn hệ thống hoặc đọc environment tùy tiện nếu muốn build có thể tái lập.
- Thêm integration test kiểm tra generated source/class và compile status trên toolchain mục tiêu.
- Tránh đưa text diagnostic thành API của processor; nếu cần machine-readable report, tạo schema/artifact riêng do công cụ kiểm soát.

Khi processor có nhiều phiên bản hoặc phối hợp processor khác, ghi phiên bản processor và nguồn dependency tương ứng. Việc nhìn thấy vòng processing không bảo đảm generated code là đúng ngữ nghĩa; nên kiểm thử cả class được sinh.

## 14. Bài tập thực hành

**Bài A — quan sát rounds.** Chạy đúng lab mục 5 với `-XprintRounds`. Hãy chỉ ra vòng đầu có `Example`, vòng kế có `Generated` và vòng cuối đánh dấu `processingOver()`. Số dòng chính xác của log không phải mục tiêu.

**Bài B — thử tắt processing.** Dùng output rỗng và thay option bước B bằng `-proc:none`, đồng thời bỏ `-processor` để tránh cấu hình mâu thuẫn. Chương trình sẽ không có `Generated` nếu không có file cũ cung cấp class đó; giải thích lỗi compile.

**Bài C — sai supported annotation.** Trong processor, sửa `@SupportedAnnotationTypes("demo.Mark")` thành một tên không tồn tại trong inputs, biên dịch lại processor và chạy lab. Quan sát việc matching/selection thay đổi. Khôi phục tên trước khi thử tiếp.

**Bài D — service discovery.** Bỏ `-processor` khỏi lệnh B, đóng gói processor với file `META-INF/services/javax.annotation.processing.Processor` đúng và cấu hình processor path tường minh. So sánh với việc chỉ định processor trực tiếp. Không dùng JDK default làm giả định.

**Bài E — thêm source do processor tạo.** Sửa processor để chỉ sinh `Generated.java` khi có `@Mark`; sau đó đặt `@Mark` trên một class khác. Quan sát generated artifact mới từ vòng đầu, việc class được biên dịch và stdout ứng dụng.

**Bài F — file trùng.** Cố ý viết processor tạo `demo.Generated` hai lần trong một compilation để quan sát `FilerException`. Chỉ thử trên project demo; sau đó sửa bằng bảo đảm mỗi tên được tạo tối đa một lần.

**Bài G — kiểm chứng CI.** Ngoài việc kiểm tra build success, xác minh `build/generated/demo/Generated.java` và `build/classes/demo/Generated.class` ở output sạch. Đó là bằng chứng dễ tự động hóa hơn số dòng `Round 1` trong stderr.

## 15. Checklist khi processor không được gọi

1. `javac -version` và JDK thực tế của task đã được xác định.
2. Có config/request annotation processing rõ ràng, nhất là với JDK 23+.
3. Không có `-proc:none` vô tình.
4. Processor class và dependency của nó nạp được từ đúng processor path/module path.
5. Có `-processor` chính xác hoặc service registration/module provides đúng.
6. `@SupportedAnnotationTypes` khớp annotation fully qualified đang xuất hiện.
7. Không có processor khác claim những annotation mà processor này cần.
8. `-XprintRounds`/`-XprintProcessorInfo` được bật trong lần chẩn đoán.
9. `process` hoặc `init` có diagnostic đủ chứng minh lifecycle, thay vì chỉ nhìn class hiện diện.
10. `Filer` tạo đúng source/resource và không tạo trùng.
11. `-s`/`-d` và compiled generated classes được kiểm tra trong output mới.
12. Build tool không skip compiler task vì cache/incremental logic.
13. Source/annotation version, module path, compiler plugin phù hợp.
14. Build được xác minh bằng exit status, generated artifact và test hành vi, không phụ thuộc định dạng log.

## 16. Kết luận và tài liệu chuẩn

Annotation processing là một quá trình **có discovery, selection, nhiều round và output riêng**. Khi “processor không chạy”, câu hỏi tốt nhất là: **processing có được bật không; processor có được tìm thấy không; annotation có matching và được đưa vào round không; processor có thật sự sinh file không; file ấy có được compile và dùng đúng path không?**

Dùng `-processor`/processor path để kiểm soát phụ thuộc; dùng `-XprintRounds` và `-XprintProcessorInfo` để quan sát; dùng `RoundEnvironment` và `Messager` để hiểu vòng hiện tại; dùng `Filer` đúng contract để sinh file; và kiểm chứng output sạch khi điều tra.

Nguồn tham khảo chính thức:

- [JDK 21 javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `-processor`, `-processorpath`, `-XprintRounds`, `-XprintProcessorInfo`, `-proc`.
- [Processor API JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/Processor.html): discovery, claim annotation và thứ tự lifecycle.
- [RoundEnvironment API JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): roots, errorRaised và processingOver.
- [Filer API JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/Filer.html): cách tạo file và những giới hạn chống ghi đè.
- [Inside Java: JDK 23 annotation processing change](https://inside.java/2024/06/18/quality-heads-up/): thay đổi default và `-proc:full`.
