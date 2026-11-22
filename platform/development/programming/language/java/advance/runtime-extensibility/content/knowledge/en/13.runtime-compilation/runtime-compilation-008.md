# Quản lý annotation processor và lựa chọn -proc:none khi không cần

Khi ứng dụng Java **biên dịch mã nguồn ngay lúc chạy** bằng JavaCompiler API (JSR 199), quá trình biên dịch có thể làm nhiều việc hơn việc biến file .java thành bytecode. Trình biên dịch còn có thể **khởi chạy annotation processor** theo JSR 269 để kiểm tra khai báo, phát sinh thêm mã nguồn hoặc báo lỗi. Điều này hữu ích khi mã thực sự cần MapStruct, Dagger hoặc một processor được ứng dụng chủ kiểm soát; nhưng với mã do người dùng nhập hoặc một đoạn Java nhỏ không yêu cầu sinh mã, việc chạy processor ngoài ý muốn tạo thêm tác dụng phụ, chi phí và rủi ro.

Vì vậy, mỗi lần biên dịch động phải có chính sách rõ ràng: **khi nào cần xử lý annotation, processor nào được phép chạy, processor được tải từ đâu, và khi nào phải truyền -proc:none**. Đây là một quyết định lúc **biên dịch**, không liên quan trực tiếp đến việc JVM có thể đọc annotation qua reflection sau khi class đã được nạp.

## 1. Annotation processor làm việc gì?

Annotation là metadata gắn với package, class, interface, method, field, parameter và những phần tử Java khác. Nhưng bản thân việc viết @SomeAnnotation **không làm cho compiler tự phát sinh mã**. Annotation processor là một chương trình Java triển khai **javax.annotation.processing.Processor**, thường kế thừa AbstractProcessor, mà javac có thể nạp và gọi trong bước xử lý annotation.

Một processor có thể:

- đọc mô hình khai báo của mã đang biên dịch qua javax.lang.model;
- xác minh quy tắc và ghi Diagnostic.Kind.ERROR/WARNING/NOTE qua Messager;
- sinh Java source, class hoặc resource bằng Filer;
- chạy qua nhiều vòng (round): source mới được sinh có thể lại chứa annotation và được xử lý ở vòng sau.

Ví dụ một processor nhận annotation @GenerateMarker có thể tạo ra class generated.MarkerGenerated. Sau đó javac tiếp tục biên dịch class được sinh nếu đang chạy chế độ biên dịch thông thường.

Một annotation mang RetentionPolicy.SOURCE vẫn có thể được processor nhìn thấy khi biên dịch, mặc dù annotation đó không cần tồn tại để reflection ở runtime đọc. Ngược lại, annotation có RetentionPolicy.RUNTIME cũng **không bắt buộc phải có annotation processor**; chương trình có thể chỉ muốn đọc nó bằng reflection khi class chạy.

**Điểm quan trọng về rủi ro:** processor là mã Java có thể **thực thi trong quá trình biên dịch**. Nó không chỉ là metadata bị động. Processor có thể dùng file system, network, thread hoặc tài nguyên khác theo quyền của tiến trình compiler. Đối với dịch vụ compile-on-demand, danh sách processor là một phần của chính sách cho phép thực thi mã.

## 2. Ba chế độ xử lý annotation của javac

| Tùy chọn | Hành vi | Trường hợp áp dụng |
| --- | --- | --- |
| **-proc:none** | Biên dịch Java thông thường; **không chạy annotation processor** | Mã độc lập, nguồn không đòi hỏi generated code, đầu vào động không có processor đã được duyệt |
| **-proc:only** | Chạy annotation processing nhưng **không thực hiện bước biên dịch class thông thường** sau đó | Tạo source hoặc kiểm tra processor riêng trong pipeline |
| **-proc:full** | Chạy annotation processing rồi biên dịch class | Nguồn cần generated code; dùng khi phiên bản javac hỗ trợ tùy chọn này |

Có thể bỏ hẳn tùy chọn -proc và lựa chọn processor bằng -processor, -processorpath hoặc --processor-module-path. Khi đó việc xử lý annotation có thể được bật theo quy tắc của phiên bản javac đang chạy. Trong hệ thống cần kết quả có thể tái lập, hãy chọn **tường minh** thay vì dựa vào việc compiler có tự dò được processor hay không.

**Không nhầm -proc:none với -implicit:none.** -implicit:none điều khiển việc javac có phát sinh .class cho các source được tìm thấy ngầm hay không; nó **không thay thế chính sách tắt annotation processing**. Tương tự, --release 17 quy định ngôn ngữ/API/bytecode mục tiêu, chứ không khiến processor tự động tắt.

### Thay đổi quan trọng từ JDK 23

Trong các phiên bản javac **đến JDK 22**, khi không có -proc:none, trình biên dịch có thể tự khám phá processor trên đường tìm kiếm (mặc định classpath nếu không có processor path riêng). Đây từng là hành vi dễ bị kích hoạt ngoài ý muốn khi dependency tình cờ chứa file đăng ký processor.

**Từ JDK 23**, annotation processing **không tự bật chỉ vì một processor có mặt trên classpath**. Cần cấu hình hoặc yêu cầu xử lý annotation tường minh, chẳng hạn -processor, -processorpath, --processor-module-path, -proc:only hoặc -proc:full. Sự thay đổi này là chính sách của **javac đang chạy**, không phải của phiên bản bytecode đích.

Ví dụ chương trình đang chạy **JDK 24** và truyền --release 17 vẫn dùng quy tắc khám phá processor của javac 24; --release không hoàn nguyên mặc định xử lý annotation về JDK 17.

Tùy chọn -proc:full đã được đưa trở lại một số bản cập nhật JDK 17 (ví dụ 17.0.11 trở lên), nhưng không nên giả định mọi bản 17 cũ đều nhận tùy chọn đó. Khi cần chạy trên nhiều bản JDK 17, lựa chọn processor tường minh bằng -processor và -processorpath, hoặc tắt bằng -proc:none, là cách rõ ràng. Luôn kiểm tra javac -version và javac --help của JDK triển khai thực tế.

Tài liệu về thay đổi: OpenJDK/Inside Java, “JDK 23: Changes Default Annotation Processing Policy” — https://inside.java/2024/06/18/quality-heads-up/

## 3. Processor được tìm từ đâu?

Một lỗi rất thường gặp là trộn lẫn **classpath của mã được biên dịch** với **processor path**:

| Tùy chọn | Đường dẫn dùng cho | Ghi chú |
| --- | --- | --- |
| -classpath / -cp | Kiểu, annotation API và thư viện mà source Java cần để biên dịch | Không được lẫn với processor path trong môi trường cần cô lập |
| -processorpath / --processor-path | Class/JAR của processor và các dependency để chạy processor | Đặt rõ khi cần processor; không cho mọi classpath dependency tự được chọn |
| --processor-module-path | Module path dùng để tìm processor được đóng gói theo module | Dùng khi processor là named module phù hợp |
| -processor a.b.FooProcessor | Danh sách tên class processor được chọn tường minh, phân cách bằng dấu phẩy | Bỏ qua khám phá processor mặc định |
| -Akey=value | Option chuyển cho processor | Processor quyết định ý nghĩa; không phải tùy chọn javac chung |
| -s directory | Thư mục ghi **Java source được sinh** | Hữu ích để kiểm tra generated code |
| -d directory | Thư mục ghi **class file kết quả** | Nên khác giữa các tác vụ biên dịch |
| -XprintRounds, -XprintProcessorInfo | In thêm thông tin vòng và processor đã gọi (tùy chọn javac) | Dùng để chẩn đoán khi processor không chạy |

Một processor được đăng ký để javac tự khám phá bằng file:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nội dung gồm tên lớp processor, mỗi dòng một tên, ví dụ:

~~~text
demo.MarkerProcessor
~~~

Nhưng nếu chỉ cho phép **một processor cụ thể**, có thể truyền -processor demo.MarkerProcessor và -processorpath chỉ chứa processor được phê duyệt cùng dependency của nó. Ví dụ runnable phía dưới dùng chính cách này nên **không cần** tạo file META-INF/services. Đây là hai cơ chế chọn processor khác nhau, không phải hai file cần bắt buộc đồng thời.

Trong ứng dụng compile-on-demand, đừng lấy nguyên java.class.path của tiến trình host làm processor path theo mặc định. Host có thể mang thêm dependency và processor vô tình nằm trong đó. Hãy tạo **danh sách processor/JAR được phép** và dùng classpath biên dịch độc lập. Chỉ khi đã kiểm soát môi trường và cần processor, mới cấp đường dẫn để compiler tải và chạy nó.

## 4. Khi nào nên chọn -proc:none?

**Chọn -proc:none theo mặc định** nếu bài toán chỉ cần kiểm tra cú pháp, biên dịch một class Java cơ bản, hoặc biên dịch đoạn mã được cung cấp bên ngoài mà không có yêu cầu chính thức về generated code. Tùy chọn này ngăn javac kích hoạt annotation processor trong tác vụ đó ngay cả khi một JAR processor có mặt trên đường tìm kiếm.

Những trường hợp điển hình:

- Trình biên dịch code snippet cho người học: người dùng nhập class, method hoặc biểu thức Java thuần.
- Dịch vụ xác thực mã nguồn Java trước khi lưu: chỉ cần compiler diagnostics và bytecode.
- Plugin host biên dịch Java từ file tải lên: chưa có danh sách processor đã được thẩm định.
- Biên dịch các lớp có annotation chỉ dùng ở runtime, không yêu cầu processor tạo type hoặc config.
- Biên dịch những nguồn độc lập được tạo sẵn bởi một bước khác: không cần chạy lại processor trong lần compile này.

Tuy nhiên, **đừng tắt processor một cách máy móc** với source vốn phụ thuộc generated type. Ví dụ dự án dùng MapStruct cần class triển khai mapper được sinh; Lombok cần quá trình xử lý để hỗ trợ một số mã nguồn sử dụng cú pháp/phương thức được tạo. Khi dùng -proc:none, compiler có thể báo cannot find symbol, thiếu implementation hoặc build xong nhưng thiếu artifact kỳ vọng. Trong tình huống đó, hoặc phải bật các processor **đúng danh sách đã duyệt**, hoặc biên dịch với generated source/class được chuẩn bị từ pipeline đáng tin.

Một dấu @ trong source **không đủ** để kết luận cần processor; phải đọc hợp đồng của annotation và các dependency được yêu cầu. Ví dụ @Override không cần annotation processor do người dùng cấu hình.

## 5. Ví dụ chạy được: JavaCompiler tại runtime, bật rồi tắt processor

Ta xây dựng một chương trình Java 17+ hoàn chỉnh gồm ba file:

~~~text
src/
  demo/
    GenerateMarker.java
    MarkerProcessor.java
    RuntimeCompileDemo.java
~~~

RuntimeCompileDemo sẽ tự tạo source generated.Task có annotation @GenerateMarker, rồi biên dịch nó **hai lần** vào hai thư mục output khác nhau:

1. **enabled:** chọn processor demo.MarkerProcessor bằng -processor, đặt -processorpath tường minh; processor tạo thêm class generated.MarkerGenerated.
2. **disabled:** truyền -proc:none và không chọn processor; generated.Task vẫn biên dịch vì annotation API có trong classpath, nhưng **không có** generated.MarkerGenerated.

Kết quả được kiểm tra bằng sự tồn tại của **class file** thực tế, không chỉ bằng message của processor.

### 5.1. Định nghĩa annotation

**src/demo/GenerateMarker.java**

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateMarker {}
~~~

Đây chỉ là annotation marker, không có logic thực thi. RetentionPolicy.SOURCE cho phép processor nhận ra annotation trong compilation unit, nhưng compiler không bắt buộc mang annotation này vào runtime class file.

### 5.2. Annotation processor sinh một class

**src/demo/MarkerProcessor.java**

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
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("demo.GenerateMarker")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class MarkerProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (generated || round.processingOver()
                || round.getElementsAnnotatedWith(GenerateMarker.class).isEmpty()) {
            return true;
        }
        generated = true;
        try (Writer out = processingEnv.getFiler()
                .createSourceFile("generated.MarkerGenerated").openWriter()) {
            out.write("package generated; public final class MarkerGenerated {}");
        } catch (IOException ex) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR, ex.getMessage());
        }
        return true;
    }
}
~~~

Các thành phần quan trọng:

- @SupportedAnnotationTypes chỉ rõ annotation mà processor hỗ trợ; khác với việc annotation được import trong chính processor.
- @SupportedSourceVersion xác định mức ngôn ngữ được processor khai báo hỗ trợ. Ví dụ dùng RELEASE_17 và biên dịch target với --release 17.
- RoundEnvironment chứa các phần tử có annotation trong vòng hiện tại. processingOver() giúp nhận biết vòng xử lý cuối.
- Filer.createSourceFile tạo source mới cho compiler, sau đó source được biên dịch trong chế độ xử lý và biên dịch thông thường.
- Biến generated tránh cố sinh **cùng một tên file nhiều lần** giữa các vòng, vốn có thể gây FilerException.

Trong ví dụ đơn giản này, processor tạo một class dùng để minh họa. Processor thực tế cần quyết định quy tắc tên class, nhiều annotated element, dependency và cách báo lỗi nhất quán; đừng tự sinh một class cố định cho mỗi annotation nếu chúng có thể trùng tên.

### 5.3. Host gọi JavaCompiler với chính sách xử lý riêng

**src/demo/RuntimeCompileDemo.java**

~~~java
package demo;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class RuntimeCompileDemo {
    private static void compile(boolean enableProcessor) throws Exception {
        String mode = enableProcessor ? "enabled" : "disabled";
        Path dir = Path.of("build", "dynamic", mode);
        Path source = dir.resolve("src/generated/Task.java");
        Path classes = dir.resolve("classes");
        Path generatedSources = dir.resolve("generated-sources");
        Files.createDirectories(source.getParent());
        Files.createDirectories(classes);
        Files.createDirectories(generatedSources);
        Files.writeString(source,
                "package generated; import demo.GenerateMarker; " +
                "@GenerateMarker public class Task {}",
                StandardCharsets.UTF_8);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A JDK is required");
        }
        String cp = System.getProperty("java.class.path");
        List<String> options = new ArrayList<>(List.of(
                "--release", "17", "-encoding", "UTF-8",
                "-classpath", cp, "-d", classes.toString(),
                "-s", generatedSources.toString()));

        if (enableProcessor) {
            options.addAll(List.of(
                    "-processorpath", cp,
                    "-processor", "demo.MarkerProcessor"));
        } else {
            options.add("-proc:none");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        boolean success;
        try (StandardJavaFileManager files =
                     compiler.getStandardFileManager(
                             diagnostics, null, StandardCharsets.UTF_8)) {
            Iterable<? extends JavaFileObject> units =
                    files.getJavaFileObjects(source.toFile());
            success = Boolean.TRUE.equals(
                    compiler.getTask(null, files, diagnostics,
                            options, null, units).call());
        }
        if (!success) {
            throw new IllegalStateException(
                    diagnostics.getDiagnostics().toString());
        }
        boolean generated = Files.exists(classes.resolve(
                "generated/MarkerGenerated.class"));
        System.out.println(mode + ": compiled=" + success +
                ", generated=" + generated);
        if (generated != enableProcessor) {
            throw new IllegalStateException(
                    "Unexpected processor behavior");
        }
    }

    public static void main(String[] args) throws Exception {
        compile(true);
        compile(false);
    }
}
~~~

Trong chương trình này, javac chạy **ngay trong JVM của ứng dụng** qua javax.tools.JavaCompiler; không phải chạy ProcessBuilder để gọi một tiến trình javac bên ngoài. getSystemJavaCompiler() thường có sẵn khi chạy JDK đầy đủ hoặc runtime image chứa compiler phù hợp; nếu trả null, ứng dụng phải báo lỗi khả năng compiler không có. Nó không tự tải JDK về.

**JavaCompiler.getTask** nhận options gần giống javac CLI. Biến enableProcessor là quyết định của host, không nên lấy trực tiếp một chuỗi tùy chọn bất kỳ từ input không tin cậy. Khi bật, -processorpath và -processor được thêm vào, còn khi tắt, -proc:none được thêm vào. Đầu vào Java ở cả hai chế độ có cùng annotation, do đó khác biệt class được sinh là do **chính sách xử lý**, không do thay source.

Để ví dụ dễ chạy, biến cp lấy chính classpath của chương trình demo, trong đó có cả annotation API và processor. **Đây là cách viết tối giản cho ví dụ, không phải cách phân quyền processor trong sản phẩm.** Với runtime compiler phục vụ nhiều người dùng, tách processor path khỏi compiler classpath, giới hạn JAR đã duyệt và giữ đường dẫn output riêng cho từng yêu cầu.

### 5.4. Biên dịch và chạy chương trình demo

Chạy ở thư mục chứa src, với **JDK 17 hoặc mới hơn**. Với Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path out/classes | Out-Null

javac --release 17 -proc:none -encoding UTF-8 -d out/classes src/demo/GenerateMarker.java src/demo/MarkerProcessor.java src/demo/RuntimeCompileDemo.java

java -cp out/classes demo.RuntimeCompileDemo
~~~

Lệnh javac đầu dùng -proc:none khi **biên dịch chính các lớp công cụ demo**, để không phát hiện và chạy processor nào trong bootstrap compile. Khi chương trình bắt đầu, nó sẽ tự gọi compiler lần lượt với policy enabled rồi disabled.

Trên Linux/macOS, thay lệnh tạo thư mục bằng:

~~~bash
mkdir -p out/classes
~~~

Hai lệnh javac/java còn lại giữ nguyên. Code dùng System.getProperty("java.class.path") nên dấu phân cách classpath thích hợp với nền tảng do Java cung cấp.

**Stdout chính xác của chương trình:**

~~~text
enabled: compiled=true, generated=true
disabled: compiled=true, generated=false
~~~

Đây là kết quả đã được kiểm chứng thực tế với javac --release 17, chạy chương trình trên JDK mới hơn. JavaCompiler tạo được generated.Task.class ở **cả hai** thư mục. Chỉ chế độ enabled mới có **generated.MarkerGenerated.class** và file source tương ứng trong generated-sources.

Cách đọc kết quả:

- compiled=true ở cả hai lượt chứng minh annotation @GenerateMarker không tự yêu cầu có processor để source cơ bản biên dịch.
- generated=true ở lượt đầu chứng minh processor đã được chọn, được nạp và tạo source rồi compiler biên dịch source đó.
- generated=false ở lượt sau chứng minh -proc:none loại bỏ xử lý annotation trong tác vụ biên dịch này.
- Hai thư mục output riêng giúp tránh việc class còn sót lại từ lượt trước làm sai kết quả. Khi kiểm tra hệ thống thật, cũng cần xóa/đổi namespace output phù hợp thay vì dùng một thư mục sinh mã chung cho nhiều người dùng.

Nếu thiếu annotation API khỏi -classpath, target sẽ không biết @GenerateMarker và compile lỗi **dù đã tắt processor**. -proc:none không làm biến mất những annotation class mà source cần trong bước kiểm tra kiểu.

## 6. Lựa chọn processor bằng API JavaCompiler thay cho dò tự động

Lựa chọn trong ví dụ dựa trên **-processor tên-lớp**. Ngoài ra, JavaCompiler.CompilationTask còn có phương thức setProcessors(Iterable<? extends Processor>) để host cung cấp các **instance processor** được lựa chọn trực tiếp.

Ý tưởng của nhánh sử dụng instance là:

~~~java
JavaCompiler.CompilationTask task =
        compiler.getTask(null, files, diagnostics, options, null, units);
task.setProcessors(List.of(new MarkerProcessor()));
boolean ok = Boolean.TRUE.equals(task.call());
~~~

Đây là **đoạn minh họa thay thế** đặt trong method có các biến compiler, files, diagnostics, options, units được tạo như ví dụ hoàn chỉnh, không phải chương trình độc lập. Khi dùng setProcessors, không đồng thời yêu cầu -processor chọn một tập khác; xác định một cơ chế lựa chọn có kiểm soát. Nếu muốn vô hiệu hóa hoàn toàn xử lý annotation, chọn -proc:none và không cung cấp processor.

Cách cung cấp instance giúp host quản lý rõ processor object, nhưng **không phải sandbox**: mã constructor/process của processor vẫn thực thi trong JVM host. Với processor từ JAR, code nạp class và tạo instance phải được quản lý độc lập, tránh để dependency/JAR chưa được duyệt đi vào class loader của compiler.

Trong tác vụ compile-on-demand thực tế, nên định nghĩa chính sách đầu vào, chẳng hạn:

~~~text
CompilationPolicy {
    languageRelease = 17
    annotationProcessing = DISABLED | EXPLICIT
    allowedProcessors = [định danh đã duyệt]
    compilerClasspath = [annotation API và dependency biên dịch]
    processorPath = [chỉ processor JAR và dependency cần thiết]
    sourceOutput = thư mục riêng
    classOutput = thư mục riêng
}
~~~

Khối trên là **mô tả chính sách** chứ không phải một class Java runnable. Việc xuất phát từ chính sách cố định giúp ngăn một request tự ý thêm -processorpath, -proc:full, -Xplugin hoặc những flag làm thay đổi quá trình biên dịch.

## 7. Độ tin cậy và vòng đời của processor trong runtime compiler

Annotation processor có quyền thực thi mã ngay trong lúc compilation task chạy. Dùng -processorpath **giúp chọn và tổ chức dependency**, nhưng không giới hạn các quyền hệ điều hành của processor. Đặt processor trong class loader riêng cũng chỉ tách namespace, không tự tạo ranh giới an toàn.

Khi mã hoặc processor không đáng tin, cần quyết định riêng những vấn đề sau:

1. **Không có yêu cầu generated code:** truyền -proc:none; không để processor được dò tự động qua JAR đi kèm.
2. **Có yêu cầu generated code được hỗ trợ:** chỉ cho phép những processor đã được duyệt bằng -processor hoặc setProcessors, cùng bộ artifact và version đã kiểm thử.
3. **Có khả năng thực thi mã không đáng tin:** xem xét chạy tác vụ biên dịch trong **tiến trình/OS container hạn chế quyền**, có giới hạn CPU, bộ nhớ, thời gian, file system và network. -proc:none chỉ tắt annotation processing; nó **không biến việc biên dịch hoặc chạy bytecode thành sandbox tuyệt đối**.
4. **Giới hạn đầu ra:** dùng thư mục làm việc tách biệt, không để processor ghi tràn vào workspace của ứng dụng hoặc thay đổi artifact của người khác.
5. **Giám sát và lỗi:** thu thập Compiler Diagnostics, exception gốc, processor version, source release, thời gian và file được sinh. Tránh đưa nội dung nhạy cảm vào log/error trả cho người gửi mã.
6. **Khả năng lặp lại:** cố định phiên bản javac, -processor, processor path, annotation API và options -A; đóng băng input nếu cần build reproducibility.

Nên nhớ rằng source Java được compile **không mặc nhiên được chạy** bởi chương trình host khi JavaCompiler trả kết quả. Tuy nhiên processor **đã chạy** nếu annotation processing được bật; và nếu host sau đó class-load/khởi tạo/gọi generated bytecode thì đó là một bước thực thi mới cần chính sách riêng.

## 8. Quản lý các vòng sinh mã và lỗi Filer

Một processor có thể sinh source ở một vòng, rồi compiler lại gọi processor ở vòng tiếp theo để xử lý source mới. Khi nhiều vòng phát sinh, một processor phải tránh viết lại **cùng đường dẫn/file** trong cùng compilation.

Ví dụ MarkerProcessor dùng biến generated để đảm bảo chỉ gọi createSourceFile("generated.MarkerGenerated") một lần. Khi Filer gặp nỗ lực tạo trùng file trong một lần compile, nó có thể báo FilerException. Nếu một processor khác cũng tạo cùng tên class, build có thể thất bại do xung đột; không được xử lý bằng cách âm thầm bỏ lỗi và chọn ngẫu nhiên đầu ra.

Các biện pháp hữu ích:

- Sinh tên class từ tên/type của phần tử được xử lý, có chiến lược tránh trùng thay vì sinh một tên cố định cho mọi annotation.
- Đánh dấu phần tử đã xử lý hoặc kiểm tra vòng khi cần; dùng round.processingOver() để biết giai đoạn kết thúc.
- Đưa lỗi vào Messager với thông tin phần tử (Element) giúp javac định vị lỗi biên dịch.
- Không đặt logic có tác dụng phụ tùy ý trong mọi vòng, vì số vòng thay đổi khi generated source chứa annotation mới.
- Với tác vụ độc lập, dùng output folder tách biệt và không giữ cache processor/source cũ nếu chưa thiết kế incremental compilation.
- Khi debug, thử -XprintRounds và -XprintProcessorInfo trên javac tương thích để biết processor thực sự được gọi ở vòng nào.

Trong ví dụ runnable, kiểm tra file generated.MarkerGenerated.class còn có lợi hơn việc chỉ nhìn dòng log processor, bởi nó xác minh pipeline **generate source → compile generated source** đã hoàn tất.

## 9. Khi -proc:none làm biên dịch lỗi, cần xử lý ra sao?

Đầu tiên hãy hỏi: **bài toán có thật sự cần generated output không?** Nếu source chỉ có annotation marker dùng để đánh dấu hoặc đọc ở runtime, -proc:none vẫn hợp lệ. Nếu source tham chiếu một class hoặc method vốn do processor tạo, việc tắt processor sẽ làm thiếu symbol.

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Cùng source, enabled sinh class nhưng disabled không sinh | Processor đúng là nguồn tạo class đó | Xem -s, -d và output JAR |
| -proc:none báo cannot find symbol | Source phụ thuộc generated type hoặc classpath thiếu annotation API | Xác định symbol, phân biệt source được tạo với annotation type |
| Đã bật nhưng processor không chạy | Thiếu -processor/-processorpath, sai tên class, JDK 23+ mặc định không tự khám phá | Log compiler options, kiểm tra processor artifact |
| ServiceLoader-style discovery không tìm processor | Thiếu META-INF/services/javax.annotation.processing.Processor | Kiểm tra JAR bằng jar tf, nội dung descriptor UTF-8 |
| Processor được gọi nhưng không sinh code | Annotation không khớp @SupportedAnnotationTypes, code xử lý không có phần tử phù hợp | Dùng -XprintRounds, diagnostics và test annotation |
| Source generated nhưng không có .class | -proc:only, compile thất bại hoặc output path khác | Kiểm tra -proc, lỗi javac, -s và -d |
| FilerException do file được tạo lại | Hai processor/round cố tạo cùng tên source hoặc class | Sửa chiến lược sinh file, kiểm tra nhiều vòng |
| Khi nâng JDK lên 23+ generated code biến mất | Build dựa vào quét processor ngầm trên classpath | Chuyển sang chọn processor tường minh |
| Compiler mất nhiều thời gian hoặc tác vụ không dừng | Processor thực hiện tính toán/I/O dài hoặc chờ tài nguyên | Giới hạn tài nguyên của tiến trình, đo thời gian và log |

Cũng cần kiểm tra **processor có chạy bằng JDK nào**. --release 17 kiểm soát mức ngôn ngữ của source đích; processor là chương trình chạy trong môi trường compiler hiện hành, nên phải tương thích với JDK đang thực thi JavaCompiler. Không nên suy diễn rằng processor cũng bị chạy bên trong một JVM Java 17 khác chỉ vì target là 17.

## 10. Checklist triển khai compile-on-demand

Trước khi cho phép người dùng hoặc hệ thống bên ngoài gửi Java source để biên dịch:

- **Xác định policy rõ ràng:** DISABLED thì luôn truyền -proc:none; EXPLICIT thì cho phép đúng bộ processor đã xét duyệt.
- **Kiểm tra input/dependency:** Annotation API, source và thư viện dùng để kiểm tra kiểu nằm trên compiler classpath đúng dự kiến.
- **Tách processor path:** Không để các JAR bất kỳ từ request trở thành processor được thực thi. Đóng băng version và danh sách processor cho từng loại tác vụ.
- **Xác nhận JDK:** Ghi lại javac version và sự khác biệt mặc định JDK 17–22 so với 23+; không dựa vào một quy tắc khám phá ngầm.
- **Đặt output riêng:** -d cho class, -s cho source được sinh, mỗi task có workspace; kiểm tra source/class được tạo thực sự và tránh stale output.
- **Thu diagnostics:** Không chỉ đọc Boolean của getTask.call(); giữ lỗi có ý nghĩa về missing symbol, unsupported source, unsupported processor và file generation.
- **Kiểm soát resource:** Processor chạy Java code trong compiler; nếu cần cô lập thực thi thì dùng boundary thích hợp, không chỉ -processorpath.
- **Kiểm thử cả hai nhánh:** Test compile có processor và không processor, cả output lẫn hành vi khi source phụ thuộc generated code.
- **Không tùy tiện bật toàn bộ processor:** Một annotation processor được nhúng trong dependency ngoài ý muốn không phải lý do cho phép nó chạy.

## 11. Tài liệu chuẩn

- Oracle Java SE 17, **The javac Command**, các mục -proc, -processor, -processorpath và Annotation Processing: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Oracle Java SE 17, **JavaCompiler**: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- Oracle Java SE 17, **Processor**: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html
- Oracle Java SE 17, **CompilationTask**: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.CompilationTask.html
- Inside Java/OpenJDK, **JDK 23: Changes Default Annotation Processing Policy**: https://inside.java/2024/06/18/quality-heads-up/

**Nguyên tắc triển khai:** Khi runtime compiler không có yêu cầu rõ ràng phải chạy annotation processor, hãy dùng **-proc:none**. Khi generated code thật sự cần thiết, hãy bật **đúng processor được phép**, cấp đúng processor path, kiểm thử đầu ra và kiểm soát tác vụ biên dịch như một hoạt động có khả năng thực thi mã.
