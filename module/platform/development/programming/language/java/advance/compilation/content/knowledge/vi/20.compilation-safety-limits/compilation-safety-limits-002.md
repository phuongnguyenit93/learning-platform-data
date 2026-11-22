# Processor và plugin là mã thực thi trong môi trường biên dịch

## 1. Vì sao đây là vấn đề an toàn của quá trình build?

Khi chạy **javac**, chúng ta thường nghĩ trình biên dịch chỉ đọc mã nguồn Java, kiểm tra kiểu và tạo tệp `.class`. Tuy nhiên, một số thành phần được nạp vào quá trình biên dịch là **mã Java thực sự được thực thi**, chứ không chỉ là dữ liệu để phân tích:

- **Annotation processor** sử dụng API `javax.annotation.processing` (JSR 269) để xử lý phần tử chương trình và annotation qua các vòng biên dịch. Processor có thể sinh mã nguồn/tài nguyên, phát diagnostic và gọi các API Java khác.
- **Plugin của javac** triển khai `com.sun.source.util.Plugin`, có thể được kích hoạt bằng `-Xplugin` và thường đăng ký `TaskListener` để quan sát các giai đoạn compilation.
- **Plugin/task của Gradle, Maven và các công cụ build** cũng thực thi mã trong quá trình chuẩn bị/biên dịch, nhưng nằm ở cơ chế riêng của build tool; chúng không phải annotation processor hay javac plugin.

Từ góc nhìn bảo mật, một JAR có tên “processor”, “compiler plugin”, “codegen” hoặc “linter” vẫn là mã bên thứ ba. Nếu được thực thi, mã đó có thể sử dụng quyền của tiến trình đang chạy build: đọc tệp mà tài khoản build có quyền truy cập, đọc biến môi trường, ghi tệp, gọi tiến trình khác hoặc kết nối mạng nếu hệ điều hành/môi trường cho phép. **Annotation hoặc tên tùy chọn không tạo ra sandbox.**

Điều này đặc biệt quan trọng trên máy lập trình viên và CI, nơi có thể tồn tại khóa truy cập kho mã, token deploy, thông tin đăng nhập registry, biến môi trường chứa bí mật, hoặc quyền ghi artifact phát hành. Một phụ thuộc runtime thông thường được đưa lên classpath **không đương nhiên được chạy** chỉ vì nó được tìm thấy; rủi ro phát sinh khi build thực sự nạp và gọi một extension, hoặc khi chính task/build script chủ động chạy mã.

**Mục tiêu bài học:** nhận diện chính xác thời điểm processor/plugin được chạy, phân biệt từng con đường kích hoạt, kiểm thử bằng bằng chứng quan sát được và áp dụng nguyên tắc quyền tối thiểu cho việc biên dịch. Chủ đề thuộc phạm vi **an toàn và giới hạn** của Java compilation; không nhằm biến việc viết processor/plugin thành cơ chế bỏ qua kiểm soát.

## 2. Phân biệt các con đường nạp và kích hoạt

| Thành phần | Điểm vào thực thi | Cách chọn hoặc cấu hình điển hình | Phạm vi tác động |
| --- | --- | --- | --- |
| Annotation processor | `Processor.init(...)`, `process(...)` | `-processor`, `-processorpath` / `--processor-path`, `--processor-module-path`, tùy chọn `-proc` | Xử lý mô hình mã nguồn, sinh source/resource, diagnostic; vẫn là code Java có quyền hệ điều hành của process |
| javac plugin | `Plugin.init(JavacTask, String...)` | `-Xplugin:Name`, Java ServiceLoader của `com.sun.source.util.Plugin` | Quan sát/can thiệp theo API plugin vào tiến trình compiler |
| Build plugin/task | Plugin application, task configuration/execution, lifecycle hooks | Gradle `plugins`, Maven plugin execution, custom build script | Có thể chạy trước, sau hoặc quanh compiler; quyền của build runner |
| Annotation được khai báo trong source | Metadata `@Something` | Java source | Tự nó **không** chạy processor; việc chạy phụ thuộc compiler/build configuration |
| JAR trên compile classpath | Định nghĩa kiểu/symbol cho compiler | `-classpath`, `--class-path` | Không tự suy ra mọi class trong JAR đều được thực thi; nhưng cần kiểm tra processor discovery và công cụ build tương ứng |

Ví dụ annotation processor có thể nhận được `RoundEnvironment`, duyệt các `TypeElement` và sử dụng `Filer` để ghi lớp Java mới. Ngoài chức năng chính đáng, một processor giả mạo vẫn có khả năng thực thi code khi compiler gọi nó. Tương tự, plugin javac được chọn bởi tên `getName()` và cấu hình dịch vụ, sau đó compiler gọi `init(...)`.

**Trình tự khái niệm** của một lượt compile có processor:

~~~text
Lệnh build hoặc IDE
    │
    ├─ Chuẩn bị JDK, source, classpath, processor path và options
    │
    ├─ javac bắt đầu compilation
    │    ├─ Chọn/nạp processor nếu annotation processing được bật
    │    ├─ Gọi processor qua một hoặc nhiều processing round
    │    ├─ Nhận source/resource được sinh
    │    └─ Phân tích kiểu và tạo bytecode theo chính sách -proc
    │
    └─ Trả exit status, diagnostics và artifact
~~~

Thứ tự chi tiết giữa từng compiler phase và hook có thể phụ thuộc compiler/toolchain. `javac` plugin có lifecycle riêng; build plugin còn có thể chạy **trước khi gọi javac**. Vì vậy, `-proc:none` chỉ là công tắc cho annotation processing trong javac, **không vô hiệu hóa** mọi plugin của compiler, plugin của build tool hoặc lệnh tùy biến trong build.

## 3. Annotation processor được phát hiện và chạy như thế nào?

### 3.1. Cơ chế chuẩn của JSR 269

Một annotation processor triển khai `javax.annotation.processing.Processor` hoặc kế thừa `AbstractProcessor`. Compiler tạo instance, gọi `init`, rồi `process` qua các round. Processor có thể:

1. Đọc mô hình source/type/annotation qua `Elements`, `Types` và `RoundEnvironment`.
2. Phát `Diagnostic.Kind.NOTE`, `WARNING` hoặc `ERROR` qua `Messager`.
3. Tạo source hoặc resource qua `Filer`. Source mới có thể tham gia round tiếp theo.
4. Thực thi bất kỳ mã Java nào mà tiến trình và chính sách OS/container cho phép, kể cả I/O ngoài nhu cầu code generation.

Processor có thể được chọn rõ bằng **`-processor fqcn`**, hoặc được compiler phát hiện qua service provider configuration, thường là file:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

File service chứa tên đầy đủ của lớp processor, mỗi dòng một provider. Các processor class phải nằm ở nơi compiler tìm processor, như **`-processorpath`** (classpath dành riêng cho processor) hoặc **`--processor-module-path`** với thiết lập module thích hợp. Việc khai báo annotation trong source **không tự chỉ định processor đáng tin cậy**.

### 3.2. Khác biệt mặc định giữa phiên bản JDK

Đây là điểm dễ gây sai sót khi nâng JDK:

- Trên JDK 21–22, một số lệnh `javac` có thể tìm và chạy processor từ classpath dù người dùng chưa cấu hình processing rõ ràng; javac đời này có thông báo cảnh báo về cách phát hiện ngầm.
- **Từ JDK 23**, khi không có cấu hình processing tường minh, annotation processing mặc định **không chạy**. Muốn xử lý annotation phải cung cấp tùy chọn như `-processor`, `-processorpath`, `--processor-module-path`, `-proc:only` hoặc `-proc:full` phù hợp. Không nên cho rằng “nâng cấp JDK” vẫn chạy code generation ngầm như trước.
- **`-proc:none`**: biên dịch nhưng tắt annotation processing.
- **`-proc:only`**: chỉ chạy annotation processing, không thực hiện đầy đủ bước tạo class như compile thông thường.
- **`-proc:full`**: chạy annotation processing rồi biên dịch. Tùy chọn này có sẵn trong JDK mới và đã được backport vào một số bản cập nhật JDK 17/11; với một JDK 17 cụ thể, hãy xác minh phiên bản cập nhật trước khi mặc định dùng nó.

Để tránh phụ thuộc vào hành vi ngầm giữa các JDK, hãy **chỉ định rõ processor nào được phép chạy** và tách **processor path** khỏi dependency dùng để biên dịch mã ứng dụng. Cách bật processing không tự chứng minh JAR là đáng tin; vẫn phải xác minh nguồn gốc artifact.

Nguồn tham khảo: [OpenJDK — thay đổi chính sách JDK 23](https://inside.java/2024/06/18/quality-heads-up/), [Oracle — JDK 23 release notes](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html).

## 4. Ví dụ chạy được: processor sinh lớp ngay trong thời gian biên dịch

Ví dụ này dùng duy nhất API công khai của JDK, không cần Maven/Gradle hay thư viện ngoài. Processor sẽ in một diagnostic và sinh `demo.Generated`; ứng dụng phụ thuộc vào lớp sinh ra. Nhờ thế, ta quan sát được **sự khác nhau giữa compiler có chạy và không chạy processor**.

Cấu trúc tệp:

~~~text
processor-demo/
├── processor/
│   └── demo/
│       └── ProbeProcessor.java
├── app/
│   └── demo/
│       └── App.java
└── build/
    ├── processor/          # compiler output của processor
    ├── generated/          # source do processor sinh
    ├── classes/            # bytecode ứng dụng
    └── no-processor/       # output cho phép thử âm
~~~

### 4.1. Mã của processor

**processor/demo/ProbeProcessor.java**:

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
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("*")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class ProbeProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {
        if (generated || round.processingOver()) {
            return false;
        }

        generated = true;
        processingEnv.getMessager().printMessage(
            Diagnostic.Kind.NOTE, "PROBE_PROCESSOR_EXECUTED");

        try {
            JavaFileObject output = processingEnv.getFiler()
                    .createSourceFile("demo.Generated");
            try (Writer writer = output.openWriter()) {
                writer.write(
                    "package demo; public final class Generated { " +
                    "public static String value() { return \"ok\"; } }");
            }
        } catch (IOException e) {
            processingEnv.getMessager().printMessage(
                Diagnostic.Kind.ERROR, e.getMessage());
        }
        return false;
    }
}
~~~

**Giải thích từng phần:**

- `@SupportedAnnotationTypes("*")` khiến ví dụ giáo dục này có thể được gọi dù source không khai báo annotation riêng. Trong dự án thật, nên giới hạn tên annotation cần xử lý thay vì `*`, tránh công việc thừa và sự tương tác ngoài dự kiến.
- `@SupportedSourceVersion(RELEASE_17)` khai báo mức Java source processor hỗ trợ. Processor được compiler gọi khi cấu hình processing cho phép; annotation này không tự kích hoạt processing.
- Biến `generated` ngăn processor cố tạo cùng tệp trong các round tiếp theo. `round.processingOver()` tránh sinh thêm source ở round cuối.
- `Filer.createSourceFile` yêu cầu compiler quản lý tệp sinh ra; nếu tên đã được tạo trong cùng lượt xử lý, có thể xuất hiện lỗi `FilerException`.
- Dòng `NOTE` hiển thị dấu vết **process() thực sự được gọi**. Nếu việc tạo source thất bại, processor báo `ERROR`, làm ca dương không còn thành công.

### 4.2. Mã sử dụng lớp được sinh

**app/demo/App.java**:

~~~java
package demo;

public final class App {
    public static void main(String[] args) {
        System.out.println(Generated.value());
    }
}
~~~

Tệp này **không tự biên dịch được** nếu `Generated` không xuất hiện trong source/classpath. Đó là đối chứng chủ đích, giúp kiểm tra processor đã chạy và cung cấp lớp mới.

### 4.3. Biên dịch processor, chạy hai ca đối chứng

Chạy các lệnh sau tại thư mục **processor-demo/**. Trên Linux/macOS có thể tạo thư mục với:

~~~bash
mkdir -p build/processor build/generated build/classes build/no-processor
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path build/processor,build/generated,build/classes,build/no-processor | Out-Null
~~~

Biên dịch **chính processor** trước:

~~~text
javac --release 17 -encoding UTF-8 -d build/processor processor/demo/ProbeProcessor.java
~~~

**Ca âm — vô hiệu hóa annotation processing:**

~~~text
javac --release 17 -proc:none -d build/no-processor app/demo/App.java
~~~

Kỳ vọng: javac trả exit code **khác 0** vì không tìm thấy `Generated`. Một chẩn đoán thường gặp là `cannot find symbol`. Đây là ca kiểm thử cấu hình processing, **không phải** bằng chứng rằng lệnh vô hiệu hóa mọi mã ngoài trong build.

**Ca dương — chọn processor và processor path tường minh:**

~~~text
javac --release 17 -processorpath build/processor -processor demo.ProbeProcessor -s build/generated -d build/classes app/demo/App.java
~~~

Kỳ vọng:

- Exit code javac bằng **0**.
- Compiler in diagnostic dạng `Note: PROBE_PROCESSOR_EXECUTED`.
- Có tệp nguồn được sinh tại **build/generated/demo/Generated.java** và bytecode ứng dụng/lớp sinh tại **build/classes/demo/**.

Chạy ứng dụng (đây là bước runtime bổ sung, không thay thế kiểm tra compilation):

~~~text
java -cp build/classes demo.App
~~~

Stdout chính xác:

~~~text
ok
~~~

**Kiểm chứng:** bộ ví dụ trên đã được chạy với OpenJDK 24.0.2: ca `-proc:none` trả exit code **1** (do `Generated` không tồn tại), ca bật processor in diagnostic `PROBE_PROCESSOR_EXECUTED` và chương trình in đúng `ok`.

Để chạy lại độc lập, cần dùng **thư mục output mới hoặc dọn output cũ**. Nếu vô tình đưa `build/classes` từ lượt dương lên classpath của lượt âm, lớp `Generated` đã biên dịch trước có thể làm ca âm thành công giả. Trên Windows PowerShell 5.1, `Set-Content -Encoding UTF8` tạo BOM cho một số tệp; với source Java 17, nên lưu UTF-8 **không BOM** bằng editor hoặc API phù hợp nếu gặp chẩn đoán ký tự BOM không hợp lệ.

## 5. Ví dụ chạy được: javac plugin được khởi tạo trong compilation

Cơ chế **javac plugin** khác annotation processor. Plugin triển khai `com.sun.source.util.Plugin` thuộc module `jdk.compiler`, và compiler nhận diện theo tên trả từ `getName()`. Plugin được nạp qua Java **ServiceLoader**, với service file `META-INF/services/com.sun.source.util.Plugin`. Thông thường plugin đăng ký `TaskListener`; ví dụ dưới chỉ phát tín hiệu ở `init` để chứng minh mã plugin đã chạy.

Tạo thêm các tệp:

~~~text
processor-demo/
├── plugin/demo/AuditPlugin.java
├── app/demo/Standalone.java
└── build/plugin/META-INF/services/com.sun.source.util.Plugin
~~~

**plugin/demo/AuditPlugin.java**:

~~~java
package demo;

import com.sun.source.util.JavacTask;
import com.sun.source.util.Plugin;

public final class AuditPlugin implements Plugin {
    @Override
    public String getName() {
        return "AuditProbe";
    }

    @Override
    public void init(JavacTask task, String... args) {
        System.err.println("AUDIT_PLUGIN_STARTED");
    }
}
~~~

**app/demo/Standalone.java**:

~~~java
package demo;

public final class Standalone {}
~~~

**build/plugin/META-INF/services/com.sun.source.util.Plugin** phải chứa đúng một dòng:

~~~text
demo.AuditPlugin
~~~

Tạo trước thư mục **build/plugin** và **build/plugin-classes**, đặt service file đúng đường dẫn. Sau đó chạy:

~~~text
javac -encoding UTF-8 -d build/plugin plugin/demo/AuditPlugin.java
jar --create --file build/audit-plugin.jar -C build/plugin .
javac -processorpath build/audit-plugin.jar -Xplugin:AuditProbe -d build/plugin-classes app/demo/Standalone.java
~~~

Dòng cuối kích hoạt plugin có tên **AuditProbe** và vẫn biên dịch lớp `Standalone`. Khi plugin được tìm thấy và nạp thành công, stderr chứa:

~~~text
AUDIT_PLUGIN_STARTED
~~~

**Kiểm chứng:** lệnh này đã chạy thành công trên OpenJDK 24.0.2. `-Xplugin:AuditProbe` là option chọn plugin của **javac**; nó không phải annotation processor và không bị vô hiệu hóa chỉ bởi `-proc:none`. Trong ví dụ này, `-processorpath` được dùng làm đường dẫn tìm extension cho cả cơ chế ServiceLoader của plugin; nếu đường dẫn/JAR/service file sai, compiler không thể nạp plugin.

**Phân biệt mức API:** ví dụ processor ở trên đặt `--release 17` vì dùng API Java 17 chuẩn. `com.sun.source.util.Plugin` là API của compiler JDK, không được xem như một thư viện ứng dụng Java SE phổ quát trên mọi compiler. Khi phát triển plugin thật, cần build và kiểm thử trên phiên bản **javac** mục tiêu, đặc biệt nếu dùng AST internals hoặc các `com.sun.tools.javac.*` API không ổn định.

Nguồn tham khảo: [Plugin API — JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/Plugin.html).

## 6. Vì sao processor/plugin có thể tạo rủi ro supply chain?

Hãy xét một hệ thống CI lấy một processor JAR mới từ kho artifact. CI chạy `javac` với JAR đó trên processor path. Ngay khi được nạp và kích hoạt, processor **đã là mã thực thi trong ngữ cảnh build**, nên có thể làm nhiều hơn việc sinh mã. Các nhóm rủi ro:

| Nhóm rủi ro | Ví dụ tác động có thể có | Cách giảm bề mặt tấn công |
| --- | --- | --- |
| Đọc thông tin nhạy cảm | Build process có quyền đọc biến môi trường, tệp cấu hình chứa token | Không cung cấp secrets cho bước compile khi không cần; quyền truy cập file tối thiểu |
| Ghi file và thay đổi artifact | Processor sinh thêm source/resource hoặc sửa file mà process có quyền ghi | Chạy trên working directory tạm, hạn chế quyền ghi, diff/kiểm tra artifact |
| Kết nối mạng | Mã extension gửi dữ liệu nếu runner có network egress | Giới hạn egress bằng môi trường chạy, proxy hoặc firewall theo chính sách |
| Thực thi lệnh khác | Processor/plugin dùng API tiến trình của Java để chạy công cụ ngoài | Cô lập runner, giảm quyền OS, không mount socket/credential nhạy cảm |
| Không tái lập build | Kết quả phụ thuộc clock, network, máy local hoặc input không khai báo | Ghim phiên bản, kiểm tra input/output, chạy trên môi trường tách biệt |
| Dependency/processor bị tráo | Artifact cùng tên nhưng nội dung đã thay đổi | Ghim phiên bản và checksum/chữ ký, dùng registry tin cậy, rà soát cập nhật |
| Tài nguyên bị tiêu hao | Processor lặp lâu, tạo hàng loạt tệp, dùng RAM lớn | Giới hạn CPU/RAM/thời gian và dung lượng trong container/CI |

Điều quan trọng là **quyền và giới hạn thực tế đến từ môi trường thực thi**, không đến từ annotation metadata. JPMS quản lý khả năng đọc module và exports, nhưng **không phải sandbox hệ điều hành** cho processor. Quy tắc classpath/module path cũng không thay thế kiểm soát mạng hoặc filesystem. Việc chạy processor trong JVM riêng có thể giúp phân tách sự cố, song nếu JVM riêng vẫn có cùng quyền và secrets, việc tách process một mình không tạo ranh giới bảo mật đầy đủ.

Trong một số build tool, compiler hoặc processor chạy trong worker process/daemon; trong cấu hình khác, tác vụ có thể chạy trong tiến trình build hoặc qua fork. Không nên khẳng định mọi processor luôn chạy trong một PID cố định. Nguyên tắc vẫn là xác định **process thực sự nạp extension**, user/permission của nó và các tài nguyên nó có thể truy cập.

## 7. Danh sách kiểm tra cấu hình an toàn trong dự án

### 7.1. Kiểm soát extension nào được chạy

- Cấu hình **processor path** riêng; tránh để một artifact không liên quan lặng lẽ tham gia phát hiện processor.
- Dùng **`-processor`** với danh sách tên đầy đủ khi muốn xác định chính xác processor được phép gọi.
- Nếu không cần annotation processing, đặt **`-proc:none`** tại bước **javac** tương ứng; vẫn phải rà soát javac plugin và build task khác.
- Kiểm tra **`-Xplugin`**, `META-INF/services/com.sun.source.util.Plugin` và đường dẫn JAR khi đang đánh giá compiler plugin.
- Trong Gradle/Maven, kiểm tra dependency dùng cho processor, compiler plugin, buildscript/plugin classpath và các task sinh mã. Những đường dẫn này có quyền/lifecycle khác nhau; việc tắt một đường dẫn không vô hiệu hóa tất cả.

**Gradle — cấu hình minh họa** cho một processor đã được phê duyệt:

~~~groovy
dependencies {
    annotationProcessor("org.example:approved-processor:1.2.3")
}
~~~

Đây là ví dụ **cú pháp Gradle**, không phải tọa độ artifact có thật để tải về. Phải thay bằng dependency đã xác minh; bản thân việc khai báo ở `annotationProcessor` không bảo đảm processor an toàn. Khi cần tắt processing trên một compile task cụ thể có thể cấu hình compiler args tương ứng, rồi kiểm tra command-line javac thực nhận.

### 7.2. Khóa nguồn phụ thuộc và tính tái lập

- Sử dụng dependency lock/version pin và cơ chế verification checksum/signature nếu build tool hỗ trợ.
- Kiểm tra các cập nhật processor/plugin giống như cập nhật mã thực thi, không chỉ review source code dự án.
- Chỉ dùng artifact registry và tài khoản phát hành đã kiểm tra; không chạy file JAR ngẫu nhiên mới tải chỉ vì tên trùng.
- Trong CI, giữ toolchain JDK cố định, ghi lại compiler version, processor/plugin versions và options; kiểm tra generated sources/resource khi chúng là artifact quan trọng.
- Khi một bản cập nhật làm thay đổi file sinh, đọc diff và điều tra thay đổi không tương ứng với yêu cầu chức năng.

### 7.3. Thiết kế runner theo quyền tối thiểu

Một môi trường CI tốt cho compilation thường có tính chất: workspace tạm, user không đặc quyền, filesystem chỉ cho phép ghi tại chỗ cần thiết, CPU/RAM/time limit, network egress được kiểm soát và **không cấp khóa phát hành** cho bước biên dịch nguồn chưa tin cậy. Secrets phục vụ deploy nên chỉ được đưa vào bước deploy đã được phân quyền; không chia sẻ rộng cùng tiến trình build để tiện cấu hình.

Container có thể hữu ích nhưng không tự động an toàn nếu mount đường dẫn nhạy cảm, chạy privileged/root, cấp Docker socket hoặc bật mạng vô hạn. Giới hạn build runner phải có hiệu lực ở lớp OS/container/CI và được kiểm thử thực tế. **Đọc code hoặc chạy compile từ pull request chưa được tin cậy** cần được coi là thực thi mã không tin cậy nếu build gọi processor/plugin.

### 7.4. Ghi dấu vết và phân biệt nguyên nhân lỗi

Hữu ích khi lưu: lệnh javac (đã lọc bí mật), Java version, classpath/processor path, tên processor/plugin được chọn, marker diagnostic hợp lệ và các artifact được sinh ra. Thông điệp NOTE chỉ chứng minh một đoạn code đã chạy; **nó không chứng minh processor không thực hiện tác vụ khác**.

Không in trực tiếp giá trị secret hoặc toàn bộ biến môi trường vào log. Tên processor và path có thể chứa metadata nội bộ; khi công bố log cần thực hiện redaction theo chính sách dự án.

## 8. Kiểm thử ranh giới: một ma trận có thể chạy trong CI

Sau khi chuẩn bị ví dụ hai phần trên, hãy chạy mỗi ca trong **một output directory sạch** và đối chiếu kỳ vọng:

| ID | Thiết lập | Kỳ vọng | Bằng chứng |
| --- | --- | --- | --- |
| C01 | Compile `App.java` với `-proc:none`, không có `Generated` trên classpath/sourcepath | REJECT | javac khác 0; lỗi thiếu `Generated` |
| C02 | `-processorpath` đúng và `-processor demo.ProbeProcessor` | ACCEPT | javac 0; marker `PROBE_PROCESSOR_EXECUTED`; source/class được sinh |
| C03 | Compile `Standalone.java` không có `-Xplugin` | ACCEPT | javac 0; không có marker plugin từ ví dụ |
| C04 | `-Xplugin:AuditProbe` và JAR/service descriptor đúng | ACCEPT | javac 0; stderr có `AUDIT_PLUGIN_STARTED` |
| C05 | Cấu hình `-Xplugin:WrongName` mà không có plugin tên đó | REJECT cấu hình | javac từ chối yêu cầu plugin không tìm thấy |
| C06 | Bỏ processor path khi vẫn chỉ định processor chưa có trên classpath | REJECT cấu hình | javac không tìm được processor |
| C07 | Đưa `Generated.class` cũ vào classpath của C01 | Chỉ dùng như ca phản chứng | C01 có thể biên dịch dù processor không chạy; cho thấy việc kiểm thử thiếu cách ly là sai |

Ca C05/C06 là **kiểm thử cấu hình hạ tầng compiler**, không phải kiểm thử Java source “sai kiểu”. Đừng đưa chúng vào cùng một thống kê với ca âm ngữ nghĩa Java mà không phân loại. Ca C07 chỉ nên chạy trong môi trường thử nghiệm có chủ đích để chứng minh hiện tượng **false positive**, sau đó bỏ đường dẫn lớp cũ.

Một bộ runner tự động cần:

1. Chuẩn bị fixture và compile processor/plugin của chính ví dụ thành công trước khi thử ứng dụng.
2. Dọn/tạo output mới cho từng lượt; chỉ đặt các JAR được định danh vào classpath/processor path.
3. Chạy javac và thu thập exit code **ngay tại lượt đó**, diagnostic, marker và danh sách artifact; phân biệt compiler error với lỗi không khởi chạy được process.
4. Với ACCEPT, yêu cầu exit code **0** và marker/artifact khi hợp đồng ca yêu cầu. Với REJECT, yêu cầu nonzero và nguyên nhân lỗi chính xác. Không được coi mọi exception hay timeout là “negative pass”.
5. Thử đảo kỳ vọng hoặc loại bỏ marker kiểm chứng; runner phải báo FAIL. Đây là bài kiểm tra rằng oracle có khả năng phát hiện lỗi, không chỉ in “PASS” theo exit code.
6. Nếu so sánh thông báo, tránh phụ thuộc vào toàn bộ stderr nguyên văn: locale và phiên bản JDK có thể khác. Ghim phiên bản compiler nếu cần kiểm tra mã diagnostic cụ thể.

## 9. Lỗi hiểu nhầm thường gặp

**“Annotation chỉ là metadata, nên annotation processor cũng không thể gây tác dụng phụ.”** Không đúng. Annotation trong source là metadata, còn processor là lớp Java được compiler thực thi khi được chọn/nạp.

**“Đã bật `--release 17` thì build của tôi không thể chạy code khác.”** Không đúng. `--release` giới hạn ngôn ngữ/API của **mã đích được biên dịch**; nó không phải cơ chế sandbox cho processor/plugin của compiler.

**“Tắt annotation processing là vô hiệu hóa mọi extension của build.”** Không đúng. `-proc:none` chỉ tác động đến annotation processing trong javac; `-Xplugin`, Java agents, compiler wrappers, Gradle/Maven plugins hoặc task tùy biến thuộc cơ chế khác.

**“Đã tách processor path khỏi classpath là an toàn tuyệt đối.”** Không đúng. Tách path giúp kiểm soát nguồn nạp extension và tránh phát hiện ngoài ý muốn; processor được cho phép chạy vẫn có quyền của process/runner.

**“JDK 23 không bao giờ chạy processor nữa.”** Không đúng. JDK 23 thay đổi **mặc định khi không cấu hình tường minh**; người dùng vẫn có thể kích hoạt processing qua các tùy chọn hợp lệ.

**“Không có generated file nghĩa là không có processor đã chạy.”** Không đúng. Processor có thể chỉ kiểm tra mã và phát diagnostic, hoặc chạy rồi không sinh tệp. Cần đo theo hợp đồng riêng của processor/test.

**“Có file `.class` là chắc chắn lần compile vừa chạy thành công.”** Không đúng nếu còn artifact từ lần trước. Phải dùng output sạch và kiểm tra exit code của lượt hiện tại.

**“Mọi bộ compiler đều có cùng plugin API và diagnostic.”** Không đúng. `com.sun.source.util.Plugin` được cung cấp bởi `jdk.compiler` của JDK; compiler khác có thể cung cấp cách mở rộng khác. Thông báo lỗi, mã và thứ tự diagnostic cũng có thể khác.

## 10. Bài thực hành củng cố

**Bài A — xác định processor đã được phép chạy:** triển khai lại ví dụ ở mục 4 trong một workspace tạm. Chạy lần lượt C01 và C02; giải thích vì sao cùng `App.java` lại có kết quả khác nhau. Chỉ rõ tên processor, thư mục chứa binary processor, và file được sinh.

**Bài B — phân biệt plugin với processor:** triển khai mục 5, ghi nhận `AUDIT_PLUGIN_STARTED` ở C04. Chạy thêm `javac -proc:none -processorpath build/audit-plugin.jar -Xplugin:AuditProbe -d build/plugin-classes app/demo/Standalone.java` trong output sạch và giải thích vì sao plugin vẫn được kích hoạt mặc dù annotation processing bị tắt.

**Bài C — kiểm soát môi trường build:** lấy một dự án nhỏ có processor thật. Liệt kê từng đường nạp extension (annotation processor, javac plugin, Gradle/Maven plugin), nguồn artifact, quyền filesystem, khả năng truy cập network và secrets. Thiết kế bản CI giới hạn quyền và chỉ rõ phần nào cần bắt buộc hoạt động. Không yêu cầu cố tình đọc secrets hoặc gửi dữ liệu ra ngoài.

**Tiêu chí hoàn thành:**

- Nêu được ít nhất ba loại mã có thể thực thi trong compile/build và điểm vào của chúng.
- Giải thích chính xác `-processor`, `-processorpath`, `-proc:none`, `-proc:full` và `-Xplugin`, kể cả thay đổi mặc định từ JDK 23.
- Chạy được cặp ca annotation processing bật/tắt và quan sát chẩn đoán cùng bytecode khác biệt.
- Chạy được ví dụ javac plugin có marker khi được khởi tạo.
- Phân biệt compile-time execution với runtime application code, và công tắc javac với cấu hình Gradle/Maven.
- Nêu giới hạn quyền thực tế, xác định rủi ro từ artifact không tin cậy và đề xuất ít nhất ba kiểm soát khả thi: chọn extension rõ ràng, khóa/verify artifact, CI quyền tối thiểu.

**Thông điệp cốt lõi:** một dependency được dùng làm compiler extension phải được đối xử như **mã được phép thực thi**, không chỉ là thư viện kiểu dữ liệu. Biên dịch nguồn không tin cậy cùng processor/plugin không tin cậy trong môi trường có quyền cao có thể biến một bước build thành bề mặt tấn công. Hãy khai báo chính xác extension, quan sát bằng kiểm thử và cô lập quyền ở cấp môi trường thực thi.