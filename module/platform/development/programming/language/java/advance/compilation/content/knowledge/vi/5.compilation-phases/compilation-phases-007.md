# Vị trí của annotation processing trong chu trình biên dịch Java

## 1. Annotation processing nằm ở đâu?

**Annotation processing** là bước mở rộng của trình biên dịch Java, nơi một hoặc nhiều *annotation processor* đọc mô hình khai báo của chương trình (class, interface, method, field, annotation...) và có thể tạo thêm tệp nguồn, tệp tài nguyên hoặc phát thông báo chẩn đoán. API tiêu chuẩn là **JSR 269** trong các package `javax.annotation.processing`, `javax.lang.model` và `javax.tools`. Chữ `javax` ở đây vẫn là tên package của Java SE hiện đại; không đổi thành `jakarta.annotation.processing`.

Trong cách hình dung đơn giản với `javac`, annotation processing diễn ra **sau khi compiler có đủ thông tin từ source để lập mô hình phần tử ban đầu và trước khi hoàn tất kiểm tra, hạ cú pháp và sinh bytecode cho toàn bộ chương trình**. Nếu processor tạo thêm Java source, compiler phải đưa source đó trở lại pipeline để xử lý và biên dịch.

~~~text
.java ban đầu
    |
    v
Đọc/giải mã source -> parse cú pháp -> ghi nhận khai báo và symbol ban đầu
    |
    v
+------------------------------------------------------+
| ANNOTATION PROCESSING — JSR 269                      |
| Round 1: xử lý các phần tử trong source đầu vào       |
|   -> processor có thể sinh thêm .java / .class        |
| Round 2, 3, ...: xử lý các tệp vừa phát sinh (nếu có) |
| Round cuối: thông báo processingOver = true          |
+------------------------------------------------------+
    |
    v
Phân tích kiểu và ràng buộc ngữ nghĩa còn lại
    -> kiểm tra luồng điều khiển, definite assignment
    -> hạ cú pháp (desugaring), chuẩn bị biểu diễn thấp hơn
    -> sinh bytecode .class
~~~

Sơ đồ mô tả **quan hệ logic** của các bước, không khẳng định rằng `javac` luôn hoàn tất toàn bộ type attribution sau processing hoặc không hề kiểm tra kiểu trước khi gọi processor. Compiler có thể cần resolve/attribute một phần cây để cung cấp mô hình khai báo cho processor; tiến trình xử lý nội bộ còn có thể thay đổi theo bản JDK. Hợp đồng quan trọng là processor nhận *language model* của các phần tử và các round, có thể sinh thêm đầu vào cho cùng lần biên dịch, rồi `javac` mới kết thúc xử lý tất cả tệp cần biên dịch.

**Điểm phân biệt:** annotation processing là hoạt động **compile-time**, không phải việc JVM quét annotation và chạy logic khi ứng dụng đã khởi động. Một annotation có `RetentionPolicy.RUNTIME` có thể còn được thấy bởi reflection ở runtime, nhưng việc có hay không có runtime retention **không quyết định** processor có thể xử lý annotation trong lúc compile.

## 2. Vì sao compiler phải có bước này?

Ví dụ một class mang `@GenerateGreeting`, còn ứng dụng sử dụng `GeneratedGreeting` dù mã nguồn của lớp đó chưa được viết tay. Nếu một processor tạo tệp `GeneratedGreeting.java` trong khi biên dịch, chương trình cuối cùng vẫn có thể hợp lệ:

~~~java
@GenerateGreeting
class Marked {}

// Ở một tệp Java khác:
System.out.println(GeneratedGreeting.message());
~~~

Hai dòng minh họa trên **không phải một chương trình Java độc lập**. Quy trình đầy đủ ở phần 5 sẽ tạo lớp và chạy được.

Không có annotation processing (và không có class `GeneratedGreeting` sẵn trên classpath), compiler không thể resolve tham chiếu `GeneratedGreeting`. Với processing được cấu hình đúng, processor tạo source trước khi biên dịch kết thúc; source mới được nhập vào các round và biên dịch cùng các source liên quan.

Các ứng dụng phổ biến: tạo mã mapping, tạo metadata, kiểm tra quy tắc thiết kế ở compile-time, tạo mã đăng ký dịch vụ, sinh factory/builder hoặc hỗ trợ framework. Tuy nhiên, cơ chế tiêu chuẩn **không tự sửa phương thức trong một class đã viết**; nhiều thư viện “làm thay đổi cú pháp nhìn thấy” dựa thêm vào plugin hoặc API nội bộ của compiler.

## 3. Các thành phần của JSR 269 và vai trò

| Thành phần | Vai trò |
| --- | --- |
| `javax.annotation.processing.Processor` | Giao diện mà compiler gọi ở từng round. |
| `AbstractProcessor` | Lớp cơ sở tiện dụng để viết processor. |
| `ProcessingEnvironment` | Truy cập `Filer`, `Messager`, `Elements`, `Types`, các tùy chọn `-A...`. |
| `RoundEnvironment` | Cho biết root elements của round, phần tử có annotation, tình trạng kết thúc và lỗi. |
| `TypeElement`, `Element`, `TypeMirror` | Mô hình khai báo và kiểu Java ở compile-time; khác các đối tượng `Class<?>` của reflection runtime. |
| `Filer` | Tạo source, class hoặc resource; compiler quản lý đường dẫn đầu ra và phát hiện việc ghi lặp. |
| `Messager` | Phát note, warning và error kèm vị trí phần tử để `javac` báo chẩn đoán. |
| `@SupportedAnnotationTypes` | Khai báo tên annotation (hoặc pattern) mà processor hỗ trợ. |
| `@SupportedSourceVersion` | Khai báo mức source language mà processor hỗ trợ. |

Một processor thường implement:

~~~java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    // Đọc mô hình các phần tử và có thể sinh tệp ở round hiện tại.
    return true;
}
~~~

Đây là **trích đoạn phương thức** thuộc một class processor, không phải tệp Java độc lập. Tham số `annotations` chứa các annotation type được yêu cầu xử lý ở round đó; có thể rỗng, kể cả ở round cuối. `true` nghĩa là processor **claim** các annotation mà nó xử lý để các processor tiếp theo không được hỏi về cùng annotation theo cơ chế lựa chọn processor; `false` cho phép processor khác tiếp tục được xét. Boolean này **không phải cờ thành công/thất bại**, cũng không quyết định trực tiếp việc tạo round mới. Round mới gắn với các tệp mới được processor tạo ra.

Processor có thể được gọi qua service provider discovery hoặc chỉ đích danh bằng CLI. Nó chạy trong **JVM của công cụ biên dịch** và có classpath/module path riêng cho dependencies của processor. Mã do processor tạo sẽ được **biên dịch thành chương trình đích**; hai môi trường cần được phân biệt khi khai báo dependency.

## 4. Các round và vị trí tạo source

Hãy xem một lần biên dịch có processor:

1. `javac` đọc các source ban đầu, xây dựng phần mô hình ngôn ngữ cần thiết và tìm processor phù hợp.
2. **Round 1:** processor nhận các root elements của source đầu vào. Nó có thể đọc phần tử được đánh dấu annotation, phát diagnostic và gọi `Filer.createSourceFile(...)`.
3. **Round 2:** nếu round trước tạo Java source/class mới được compiler đưa vào xử lý, compiler cung cấp các root elements mới. Những processor đã tham gia có thể tiếp tục được gọi. Không coi đây là một lần chạy `javac` mới.
4. **Các round tiếp theo:** chu trình lặp khi vẫn có đầu vào mới. Processor nên tránh liên tục sinh thêm tệp không cần thiết.
5. **Round kết thúc:** `roundEnv.processingOver()` bằng `true`. Đây là cơ hội hoàn tất công việc, dọn trạng thái hoặc kiểm tra tổng hợp. **Không dựa vào việc sinh thêm Java source trong round cuối để nó được xử lý ở một round mới.**
6. Sau khi processing kết thúc và không có lỗi ngăn cản, compiler tiếp tục những phần phân tích/biên dịch cần thiết và tạo bytecode cho các lớp cần sinh `.class`.

Hai trạng thái dễ nhầm:

- `processingOver()`: đánh dấu **round cuối**. Nó không có nghĩa `process()` đã được gọi với cùng các annotated elements của round đầu.
- `errorRaised()`: báo rằng có lỗi được nêu ra **ở round trước**. Nó không đồng nghĩa mọi lỗi đều đã được kiểm tra xong tại thời điểm gọi, và processor vẫn cần xử lý an toàn trong final round.

**Không có bảo đảm mọi annotation được processor xử lý đúng một lần trong toàn bộ invocation.** Mô hình round có thể đưa root elements mới, annotation khác và lần gọi final với annotation set rỗng. Trạng thái chung giữa các round nên được quản lý cẩn thận; quá trình incremental build cũng có những invocation độc lập.

## 5. Ví dụ đầy đủ: processor tạo một lớp mà ứng dụng sử dụng

Dùng **JDK 17 trở lên**. Ví dụ này được kiểm chứng bằng `javac --release 17`: processor tạo `demo.GeneratedGreeting` trong round 1; round 2 nhận source sinh ra; round 3 kết thúc; class `demo.App` chạy và in `Hello generated!`.

### 5.1. Cấu trúc nguồn ban đầu

~~~text
project/
  src/
    ap/
      GreetingProcessor.java
    demo/
      GenerateGreeting.java
      Marked.java
      App.java
  build/
    processor-classes/
    classes/
    generated/
~~~

Các thư mục `build` ban đầu trống; `javac` sẽ điền class và generated source tương ứng.

**Tệp `src/demo/GenerateGreeting.java`:**

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateGreeting {}
~~~

`SOURCE` nghĩa là annotation phục vụ mã nguồn và không cần xuất hiện trong class file ở runtime. Processor vẫn có thể nhận nó ngay trong compile.

**Tệp `src/ap/GreetingProcessor.java`:**

~~~java
package ap;

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

@SupportedAnnotationTypes("demo.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    private boolean created;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {
        if (round.processingOver() || created) {
            return false;
        }

        TypeElement annotation = processingEnv.getElementUtils()
                .getTypeElement("demo.GenerateGreeting");
        if (annotation == null) {
            return false;
        }

        for (Element element : round.getElementsAnnotatedWith(annotation)) {
            try (Writer writer = processingEnv.getFiler()
                    .createSourceFile("demo.GeneratedGreeting", element)
                    .openWriter()) {
                writer.write("package demo; public final class GeneratedGreeting { "
                        + "public static String message() { return \"Hello generated!\"; } }");
                created = true;
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, ex.toString(), element);
            }
        }
        return true;
    }
}
~~~

Giải thích:
- `@SupportedAnnotationTypes` khai báo processor chuyên xử lý `demo.GenerateGreeting`.
- `getTypeElement` và `getElementsAnnotatedWith` truy cập **mô hình khai báo** do compiler cung cấp.
- `createSourceFile("demo.GeneratedGreeting", element)` tạo Java source theo tên đầy đủ, đặt `element` làm phần tử gốc có liên quan (*originating element*) để hỗ trợ công cụ build theo dõi phụ thuộc.
- `try-with-resources` đóng `Writer` để compiler nhận source đã viết xong. Cờ `created` tránh tạo cùng file thêm lần nữa. Trong code sản xuất cần thêm chiến lược phát hiện xung đột tên và xử lý nhiều annotated elements; bài này cố ý có một phần tử mẫu.
- Khi `Messager` phát `ERROR`, compiler thường không thể tạo output thành công. `return true` vẫn chỉ nói về **claim annotation**.

**Tệp `src/demo/Marked.java`:**

~~~java
package demo;

@GenerateGreeting
public class Marked {}
~~~

**Tệp `src/demo/App.java`:**

~~~java
package demo;

public class App {
    public static void main(String[] args) {
        System.out.println(GeneratedGreeting.message());
    }
}
~~~

Chưa có `GeneratedGreeting.java` trong `src/demo`; đó chính là source sẽ được tạo ở processing round.

### 5.2. Biên dịch theo hai lần gọi `javac`

Từ thư mục `project`, tạo các thư mục `build/processor-classes`, `build/classes` và `build/generated`. Trong Bash, có thể dùng:

~~~bash
mkdir -p build/processor-classes build/classes build/generated
~~~

Trong PowerShell, có thể dùng `New-Item -ItemType Directory -Force` cho ba đường dẫn này. Dưới đây là hai invocation riêng biệt để thứ tự bootstrap rõ ràng.

**Lần 1: biên dịch annotation và processor trước**, để compiler ở lần tiếp theo có thể load `ap.GreetingProcessor`:

~~~bash
javac --release 17 -encoding UTF-8 -d build/processor-classes \
  src/demo/GenerateGreeting.java src/ap/GreetingProcessor.java
~~~

**Lần 2: biên dịch ứng dụng có bật processor cụ thể**:

~~~bash
javac --release 17 -encoding UTF-8 \
  -cp build/processor-classes \
  -processorpath build/processor-classes \
  -processor ap.GreetingProcessor \
  -XprintRounds \
  -s build/generated \
  -d build/classes \
  src/demo/Marked.java src/demo/App.java
~~~

Dấu `\` nối dòng ở trên dùng cho **Bash**; trong PowerShell hoặc `cmd.exe` hãy đặt mỗi lệnh `javac` trên một dòng hoặc dùng ký hiệu nối dòng tương ứng với shell.

Giải nghĩa các tùy chọn then chốt:
- `-processor ap.GreetingProcessor`: chọn chính xác processor phải chạy; không cần service descriptor cho ví dụ này.
- `-processorpath build/processor-classes`: nơi compiler tìm và load processor cùng dependencies của nó.
- `-cp build/processor-classes`: nơi source ứng dụng tìm được định nghĩa annotation `demo.GenerateGreeting`.
- `-s build/generated`: đích lưu **source do processor tạo**.
- `-d build/classes`: đích lưu **bytecode sau biên dịch**.
- `-XprintRounds`: in thông tin các round để quan sát; đây là tùy chọn chẩn đoán của `javac`.

Đầu ra chẩn đoán quan sát được với `javac` khi thử ví dụ:

~~~text
Round 1:
    input files: {demo.Marked, demo.App}
    annotations: [demo.GenerateGreeting]
    last round: false
Round 2:
    input files: {demo.GeneratedGreeting}
    annotations: []
    last round: false
Round 3:
    input files: {}
    annotations: []
    last round: true
~~~

Khoảng trắng và cách trình bày của `-XprintRounds` có thể thay đổi tùy JDK. Điểm đáng quan sát là `demo.GeneratedGreeting` xuất hiện ở **round 2**, dù không nằm trong các input `src/...java` ban đầu. Round 3 là round kết thúc, không phải giai đoạn compile một lần nữa.

Sau đó chạy:

~~~bash
java -cp build/classes demo.App
~~~

Stdout chính xác:

~~~text
Hello generated!
~~~

Các artifact quan trọng:

~~~text
build/
  generated/
    demo/
      GeneratedGreeting.java
  processor-classes/
    ap/
      GreetingProcessor.class
    demo/
      GenerateGreeting.class
  classes/
    demo/
      App.class
      Marked.class
      GeneratedGreeting.class
~~~

Lưu ý `GenerateGreeting.class` nằm ở `processor-classes` vì đã biên dịch trong lần đầu; nó không nhất thiết xuất hiện lại dưới `build/classes` khi lần thứ hai chỉ truyền `Marked.java` và `App.java`. Khi đóng gói ứng dụng, hãy quản lý dependency của annotation API và processor theo phạm vi thật sự cần thiết. Processor không nhất thiết phải nằm trên runtime classpath chỉ vì nó đã chạy trong build.

### 5.3. Tại sao biên dịch thành công dù App gọi lớp chưa tồn tại?

Ở đầu lần gọi thứ hai, `javac` đã biết `App` tham chiếu `GeneratedGreeting`, nhưng chưa thể hoàn tất tất cả kiểm tra liên kết kiểu. Processor tạo `build/generated/demo/GeneratedGreeting.java` trong round đầu. Compiler thêm tệp này như một source của round tiếp theo và dùng định nghĩa nó để hoàn tất biên dịch. Nếu loại bỏ tùy chọn processor, không có source/class `GeneratedGreeting` khác và thư mục `build/classes` sạch, build sẽ báo lỗi kiểu `cannot find symbol`.

Chính vì cần phối hợp các round mà annotation processing **nằm trong pipeline compile**, không phải một bước script xảy ra sau khi mọi `.class` đã được sinh.

## 6. Cách javac phát hiện processor

Ngoài `-processor` chỉ đích danh, một JAR chứa processor có thể có tệp:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Với nội dung là tên đầy đủ của implementation, ví dụ:

~~~text
ap.GreetingProcessor
~~~

Service provider discovery giúp `javac` tìm processor trên **processor path**. Nếu package nằm trong module Java được cấu hình theo module path, cơ chế cung cấp processor bằng `module-info.java` và `--processor-module-path` cũng có thể dùng. Ví dụ ở phần 5 sử dụng `-processor` vì nó làm rõ processor nào chạy, giảm phụ thuộc vào discovery.

**Thay đổi quan trọng từ JDK 23:** `javac` **không còn tự động chạy processor chỉ vì tình cờ tìm thấy nó trên classpath** nếu invocation không có cấu hình processing tường minh. Để chủ động bật processing, đặt `-processor`, `-processorpath`/`--processor-path`, `--processor-module-path` hoặc chính sách `-proc:full` hay `-proc:only` phù hợp. Chính sách cũ tự discovery theo classpath có thể gây chạy các processor không chủ ý; tốt nhất **chỉ rõ processor và đường dẫn cần thiết**.

Các chế độ xử lý:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `-proc:none` | Tắt annotation processing; `javac` vẫn biên dịch Java source thông thường. |
| `-proc:only` | Chạy annotation processing, không thực hiện bước compile bytecode thông thường sau processing. Phù hợp khi chỉ cần output do processor sinh. |
| `-proc:full` | Chạy annotation processing **và** tiếp tục biên dịch. |
| `-processor a.b.Processor` | Chỉ định danh sách processor tường minh; ví dụ phần 5 dùng cách này. |
| `-processorpath ...` | Đường dẫn để nạp processor; nếu không cấu hình, công cụ có thể tìm trên classpath theo chính sách phiên bản JDK. |

`-proc:full` là lựa chọn rõ ràng cho công cụ hỗ trợ nó; trên các bản cập nhật JDK cũ, mức hỗ trợ cụ thể phụ thuộc version. Ví dụ trong bài sử dụng `-processor` nên chạy được với JDK 17 trở lên mà không cần phụ thuộc hành vi tự discovery mặc định.

Thông số `-Akey=value` truyền tùy chọn riêng cho processor, truy cập từ `processingEnv.getOptions()`; nó **không** tự bật hoặc tìm processor khi compiler chưa được cấu hình thực thi processor.

## 7. Ranh giới giữa annotation processor và các giai đoạn compiler

Annotation processor tiêu chuẩn có quyền được định nghĩa qua **language model** và **Filer**:

- Đọc tên, modifier, kiểu, method, field, annotation của khai báo.
- Kiểm tra kiểu qua `Types`, tra cứu symbol qua `Elements`.
- Phát diagnostic dùng `Messager`.
- Tạo source/class/resource qua `Filer`, để compiler và build tool xử lý.

Processor tiêu chuẩn **không có hợp đồng sửa trực tiếp AST của class đang có**, không bảo đảm được gọi tại một điểm cố định trong mọi bước phân tích nội bộ của `javac`, và không nhận callback cho từng lệnh bytecode. Những công cụ muốn thay đổi AST hoặc gắn sâu vào compiler có thể dùng `com.sun.source.util.Plugin`, API `com.sun.source.tree`, `TaskListener` hoặc nội bộ `javac`, nhưng đó là cơ chế khác với JSR 269 thuần túy, có ràng buộc và độ ổn định riêng.

Khác biệt với các hoạt động hay bị lẫn:

| Cơ chế | Thời điểm | Đầu vào và kết quả chính |
| --- | --- | --- |
| **Annotation processing (JSR 269)** | Trong compile, qua processing rounds | Đọc khai báo/annotation, kiểm tra, tạo source/class/resource. |
| **Lombok và compiler internals** | Tích hợp vào compilation, ngoài hợp đồng JSR 269 thuần túy | Có thể can thiệp cấu trúc AST/bytecode qua cách riêng. |
| **Reflection** | Runtime | Đọc metadata của các class đã nạp. |
| **Java agent / instrumentation** | Khi load hoặc chạy class, tùy cơ chế | Biến đổi bytecode runtime. |
| **KAPT / KSP** | Pipeline build cho Kotlin | Có cơ chế riêng để truy cập biểu diễn chương trình Kotlin; không đánh đồng với javac JSR 269. |
| **Pre-build code generation** | Trước lần gọi compiler, do task build riêng | Tạo source trước rồi đưa vào source set để compile. |

## 8. Build tool và đường dẫn sinh source

Trong dự án thực, Maven hoặc Gradle thường tạo đường dẫn compile/processor path và gọi compiler thay lập trình viên. Mô hình vẫn là:

~~~text
Resolve dependencies + processors
             |
             v
Compile task invokes javac with processor configuration
             |
             +--> annotation processing rounds
             |      +--> generated sources / resources
             |
             +--> compile original + generated Java sources
             |
             v
Classes output + generated-source output
~~~

**Maven:** các phiên bản Maven Compiler Plugin hỗ trợ `annotationProcessorPaths` hoặc khai báo dependencies processor bằng cơ chế tương ứng của phiên bản plugin. Cần cấu hình processor rõ ràng, đặc biệt khi nâng JDK 23+. Kiểm tra phiên bản Maven Compiler Plugin và effective POM trước khi sao chép cấu hình; tên phần tử cấu hình khác nhau giữa các thế hệ plugin. Phân biệt **compile dependency** cho mã nguồn dùng annotation với **processor dependency** để công cụ biên dịch chạy processor.

**Gradle (Java plugin):** dependency cho annotation processor thường khai báo qua configuration `annotationProcessor`, chẳng hạn:

~~~groovy
dependencies {
    compileOnly 'example:annotations:1.0'
    annotationProcessor 'example:processor:1.0'
}
~~~

Đây là **đoạn mẫu** trong `build.gradle`, không phải dependency có thật để tải trực tiếp; thay bằng tọa độ artifact của thư viện thực tế. Gradle cấu hình annotation processor path cho các tác vụ `JavaCompile` và theo dõi generated sources. Nhiều plugin cung cấp compile-only annotation API và processor artifact riêng để tránh đưa processor lên runtime classpath.

Khi có lỗi “generated class not found”, kiểm tra:
1. Processor thực sự được load và chạy chưa (thông số và phiên bản JDK)?
2. Annotation có được processor hỗ trợ và xuất hiện trong round đầu chưa?
3. Processor có sinh đúng package/tên file không; tệp được tạo có lỗi compile không?
4. IDE và build tool có dùng cùng generated-source directory và cùng compiler invocation không?
5. Incremental compilation/caching có bỏ sót input, output hoặc dependencies của processor không?

Đừng sửa bằng cách copy thủ công generated `.java` vào thư mục source chính nếu bản thân processor đã là nguồn sự thật; cách đó dễ tạo duplicate class và làm output cũ che lỗi generation.

## 9. Diagnostic, lỗi và kiểm thử processor

Các công cụ hữu ích khi điều tra:

~~~bash
javac -XprintRounds -XprintProcessorInfo ...
~~~

Lệnh trên là **mẫu tùy chọn**, dấu `...` cần được thay bằng đầy đủ classpath, processor path, processor name và tên tệp nguồn như phần 5. `-XprintRounds` thể hiện các round; `-XprintProcessorInfo` hiển thị processor được hỏi/claim annotation nào. Khi cần kiểm tra pipeline mà không sinh bytecode thông thường, có thể dùng `-proc:only`. Khi muốn loại bỏ processing để xác định lỗi do bước này gây ra, dùng `-proc:none` với source không phụ thuộc vào generated classes.

Các lỗi thường gặp:

- **Processor không chạy:** không được chỉ định, thiếu service descriptor, thiếu `-processorpath`, không tương thích JDK, hoặc quy tắc mặc định JDK 23+ đã tắt discovery ngầm.
- **`Annotation processor ... not found`:** processor implementation chưa được biên dịch/đóng gói, sai tên đầy đủ hoặc processor path không chứa artifact cần thiết.
- **`FilerException: Attempt to recreate a file`:** processor tạo lại cùng một Filer path trong một lần processing, hoặc xung đột với nguồn đã có. Dùng tên file đúng và bảo vệ logic sinh trong nhiều round.
- **`cannot find symbol` đối với generated type:** processor chưa sinh file, sinh sai package, source sinh ra có lỗi cú pháp hoặc compiler không nhận source output.
- **`NoClassDefFoundError` khi load processor:** dependency cần **khi chạy processor** không có trên processor path, dù compile dependency của ứng dụng có thể đầy đủ.
- **Biên dịch một lượt chạy được, lượt sau thất bại:** output cũ, cache, incremental metadata hoặc điều kiện sinh file phụ thuộc đầu vào không được khai báo.
- **Processor tạo source mãi:** mỗi round sinh một file mới làm chu trình kéo dài; phải thiết kế điều kiện dừng. Không cố định logic theo số round mặc định.
- **`@SupportedSourceVersion` thấp hơn source level:** có thể xuất hiện warning; cập nhật mức hỗ trợ thực tế và kiểm tra tính tương thích của processor.

Một kiểm thử có giá trị cần chạy trên **thư mục output sạch**, xác nhận đúng tệp `.java` được sinh, compile class dùng generated type, và kiểm tra diagnostic âm tính với input không hợp lệ. Dùng compiler thật hoặc `JavaCompiler` API giúp test sát hành vi production. Với processor phục vụ incremental build, kiểm tra thêm việc thay đổi/xóa annotated elements có loại bỏ hoặc cập nhật output đúng không.

## 10. Các hiểu nhầm điển hình

1. **“Processor chỉ chạy sau khi mọi class đã thành bytecode.”** Sai; processor phải có cơ hội sinh source trước khi compile kết thúc để các class khác sử dụng.
2. **“Processor sửa trực tiếp code gốc.”** JSR 269 chuẩn chủ yếu đọc mô hình và tạo file mới; can thiệp AST là giải pháp khác.
3. **“Một invocation = một lần gọi `process()`.”** Sai; processor có thể được gọi qua nhiều round và một final round.
4. **“`return true` nghĩa là xử lý thành công.”** Sai; nó biểu thị annotation đã được claim.
5. **“Annotation phải có RUNTIME retention để processor thấy.”** Sai; `RetentionPolicy.SOURCE` cũng được xử lý khi compiler đọc source.
6. **“`-s` là thư mục chứa `.class`.”** Sai; `-s` cho generated sources, `-d` cho class output thông thường.
7. **“Chỉ cần thêm processor JAR vào classpath là mọi JDK sẽ tự chạy.”** Sai, đặc biệt từ JDK 23; cấu hình processing tường minh.
8. **“Processor phải có mặt khi chạy ứng dụng.”** Không nhất thiết; chỉ những thư viện mà bytecode ứng dụng cần ở runtime mới phải có tại runtime.
9. **“Round 2 là một lần gọi javac khác.”** Sai; nhiều round có thể diễn ra trong cùng một compile invocation.
10. **“Generated Java không cần compile.”** Sai; source do processor sinh cần được compiler phân tích và chuyển thành class nếu ứng dụng dùng nó.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Một processor tạo `Foo.java` ở round 1. `Foo` thường được nhìn thấy ở đâu tiếp theo? **Trong round tiếp theo** và được compiler biên dịch nếu processing/compile tiếp tục thành công.

**Câu 2.** Vì sao ở round cuối `processingOver()` là `true`? **Compiler đã xác định annotation processing sắp kết thúc**; processor không nên kỳ vọng tạo source ở đây để có thêm processing round.

**Câu 3.** Sự khác nhau giữa `-proc:only` và `-proc:full`? **`only` chỉ chạy processing; `full` chạy processing và biên dịch thông thường.**

**Câu 4.** Một dự án nâng từ JDK 17 lên JDK 23, processor không chạy nữa dù JAR vẫn ở classpath. Kiểm tra gì trước? **Cấu hình processing tường minh** qua processor name/path hoặc chế độ phù hợp, cùng log compile và dependency của processor.

**Câu 5.** Dùng `Class.getAnnotation` ở runtime có thay được việc sinh source bằng processor không? **Không.** Reflection chỉ truy cập metadata của class đã có và không can thiệp các round compile của `javac`.

**Câu 6.** `GeneratedGreeting.java` được tạo ở `build/generated`; vì sao có `GeneratedGreeting.class` trong `build/classes`? **Vì compiler biên dịch source được sinh như một phần của lần compile**, không phải `Filer.createSourceFile` tự biến file thành bytecode.

### Tài liệu để đối chiếu

- [JSR 269 — Pluggable Annotation Processing API](https://jcp.org/en/jsr/detail?id=269)
- [The javac Command — Annotation Processing](https://docs.oracle.com/en/java/javase/23/docs/specs/man/javac.html)
- [JDK 23: Changes to Default Annotation Processing Policy](https://inside.java/2024/06/18/quality-heads-up/)

**Ghi nhớ:** annotation processing là một phần **nằm giữa việc lập mô hình source ban đầu và hoàn tất biên dịch**, vận hành qua các *round*. Nó có thể tạo source mới để compiler tiếp tục xử lý trong cùng invocation; muốn hành vi build nhất quán phải cấu hình processor và đường dẫn đầu ra một cách tường minh, đặc biệt từ JDK 23.
