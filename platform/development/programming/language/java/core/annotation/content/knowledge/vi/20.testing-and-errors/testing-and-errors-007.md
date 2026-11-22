# Chẩn đoán annotation processor không được phát hiện hoặc không được gọi

Khi dùng annotation processing (JSR 269), một lỗi phổ biến là mã Java vẫn biên dịch nhưng tệp sinh ra không xuất hiện, hoặc processor không in bất kỳ chẩn đoán nào. Hai tình huống này khác nhau: **processor chưa được trình biên dịch phát hiện/tải** và **processor đã được tải nhưng không nhận annotation hay không tạo kết quả**. Cách sửa phụ thuộc vào việc xác định chính xác chặng bị đứt.

## 1. Hiểu chuỗi xử lý để khoanh vùng lỗi

Trong một lần biên dịch có annotation processing, luồng thông thường là:

1. `javac` được cấu hình cho phép annotation processing; từ JDK 23, không nên trông chờ việc tự quét classpath nếu không cấu hình AP rõ ràng.
2. Compiler xác định **processor path** (hoặc processor module path), tìm processor qua service provider / JPMS hoặc danh sách `-processor` chỉ định tường minh.
3. JVM của trình biên dịch tải và khởi tạo lớp implement `javax.annotation.processing.Processor`; với `AbstractProcessor`, compiler gọi `init(ProcessingEnvironment)`.
4. Compiler xem các loại annotation mà processor hỗ trợ qua `getSupportedAnnotationTypes()`, rồi gọi `process(...)` trong những round phù hợp.
5. Processor dùng `RoundEnvironment` và `Filer` / `Messager` để xử lý phần tử, có thể sinh source/resource/class; source mới có thể dẫn đến round tiếp theo.
6. Compiler hoàn tất round cuối (`processingOver() == true`) rồi biên dịch code, trừ khi chạy `-proc:only`.

**Không tìm thấy processor** thường xảy ra ở bước 1–3; **có processor nhưng không chạy code xử lý dự kiến** thường xảy ra ở bước 4–5. **Không có file sinh ra** chưa đủ chứng minh processor không được gọi: processor có thể chỉ kiểm tra/lập báo cáo, gặp không có phần tử khớp, dừng ở round cuối, hoặc bị lỗi khi tạo file.

| Dấu hiệu | Giả thuyết ưu tiên | Cách xác nhận |
| --- | --- | --- |
| Không có thông tin processor trong log | AP bị tắt, processor path thiếu hoặc service chưa đăng ký | Kiểm tra `-proc`, `-processorpath`, `-processor`; thử `-XprintProcessorInfo` |
| Lỗi `Annotation processor '…' not found` | Lớp nêu trong `-processor` không có trong processor path hoặc không tải được | `jar --list`, tên lớp đầy đủ, dependency của processor |
| Lỗi `Bad service configuration file` / `Provider … not found` | File service chứa tên sai, thiếu lớp, hoặc classloader không tải được | Mở `META-INF/services/javax.annotation.processing.Processor` và kiểm tra JAR |
| Processor xuất hiện nhưng không có phần tử được xử lý | Tên annotation hỗ trợ sai, annotation không có trong sources được biên dịch | `@SupportedAnnotationTypes`, `RoundEnvironment`, `-XprintRounds` |
| Log có round và `process` nhưng file không sinh | Logic/filter, `Filer`, vị trí output hoặc bản build cũ | In diagnostic và kiểm tra `-s`, thư mục generated sources |
| Chạy được bằng `javac`, lỗi trong Maven/Gradle/IDE | Cấu hình đường dẫn processor của từng công cụ khác nhau | So sánh compiler args, JDK toolchain, task và cache |

## 2. Kiểm tra lớp processor và cơ chế đăng ký

Một annotation processor tiêu chuẩn thường kế thừa `AbstractProcessor` và phải có:

- Lớp public, có constructor không tham số khả dụng và biên dịch thành `.class`; dùng import đúng gói `javax.annotation.processing` (không nhầm thành `jakarta.annotation`).
- Danh sách annotation được hỗ trợ qua `@SupportedAnnotationTypes("com.example.MyAnnotation")` hoặc override `getSupportedAnnotationTypes()`. Tên phải là tên đủ gói; `"*"` có nghĩa hỗ trợ mọi annotation, chủ yếu phù hợp khi thật sự cần.
- Source version phù hợp qua `@SupportedSourceVersion(...)` hoặc `getSupportedSourceVersion()`.
- Service provider configuration tại **đúng** đường dẫn `META-INF/services/javax.annotation.processing.Processor` trong JAR processor; nội dung là tên lớp đầy đủ, mỗi dòng một processor. Đây là tên interface, không phải tên annotation.
- Khi dùng **processor module path** của JPMS, module processor được khai báo phù hợp, ví dụ `provides javax.annotation.processing.Processor with demo.DemoProcessor;` trong `module-info.java`, thay vì chỉ trông cậy vào cơ chế service của classpath.

Phân biệt các đường dẫn:

- `-classpath` / `-cp`: cần cho **mã nguồn ứng dụng** tham chiếu các lớp, ví dụ kiểu annotation `@DemoMark`.
- `-processorpath` / `--processor-path`: nơi compiler **tìm và tải processor cùng những dependency của nó**. Nếu đã khai báo đường dẫn riêng, chỉ thêm JAR vào classpath ứng dụng không đảm bảo processor được tìm thấy.
- `--processor-module-path`: đường dẫn dành cho processor đóng gói theo JPMS; không dùng đồng thời như một giải pháp mù với classpath.
- `-processor demo.DemoProcessor`: gọi đích danh processor và **bỏ qua bước tự discovery từ service file**; hữu ích để phân biệt lỗi đăng ký service với lỗi load class.
- `-proc:none`: tắt annotation processing; `-proc:only`: chỉ chạy processor, chưa compile kết quả; `-proc:full`: xử lý annotation rồi compile.

Từ **JDK 23**, `javac` không tự chạy annotation processor chỉ vì tình cờ thấy nó trên classpath. Hãy khai báo rõ processor được phép chạy bằng `-processor` và đường dẫn phù hợp; `-proc:full` là lựa chọn tương thích khi đã kiểm soát processor path. Trong build thực tế, nên dùng danh sách processor minh bạch, tránh vô tình chạy các processor ngoài dự kiến. Kiểm tra phiên bản compiler thật bằng `javac -version` hoặc log toolchain của build, thay vì chỉ nhìn `java -version` trên terminal.

## 3. Thí nghiệm tối thiểu có thể chạy với Java 17+

Ví dụ sau tạo một annotation nguồn và processor chỉ ghi diagnostic. Nó cho phép kiểm tra từng bước mà không phụ thuộc Lombok, MapStruct, framework hay generated file.

Cấu trúc:

```text
src/
  processor/demo/DemoMark.java
  processor/demo/DemoProcessor.java
  app/demo/App.java
resources/
  META-INF/services/javax.annotation.processing.Processor
```

Tệp `src/processor/demo/DemoMark.java`:

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface DemoMark {}
```

Tệp `src/processor/demo/DemoProcessor.java`:

```java
package demo;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("demo.DemoMark")
public final class DemoProcessor extends AbstractProcessor {
    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.latestSupported();
    }

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        if (roundEnv.processingOver()) {
            return false;
        }
        for (Element element : roundEnv.getElementsAnnotatedWith(DemoMark.class)) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.NOTE,
                    "DemoProcessor saw " + element.getSimpleName(),
                    element);
        }
        return false;
    }
}
```

Tệp `src/app/demo/App.java`:

```java
package demo;

@DemoMark
public class App {
    public static void main(String[] args) {
        System.out.println("Application runs");
    }
}
```

Nội dung **nguyên văn** của `resources/META-INF/services/javax.annotation.processing.Processor`:

```text
demo.DemoProcessor
```

Tại thư mục gốc ví dụ, chạy các lệnh Bash sau (có thể tạo thư mục tương ứng bằng PowerShell trên Windows):

```bash
mkdir -p build/processor-classes build/classes
javac -d build/processor-classes src/processor/demo/DemoMark.java src/processor/demo/DemoProcessor.java
jar --create --file build/demo-processor.jar -C build/processor-classes . -C resources META-INF
jar --list --file build/demo-processor.jar
javac -cp build/demo-processor.jar -processorpath build/demo-processor.jar -proc:full -XprintRounds -XprintProcessorInfo -d build/classes src/app/demo/App.java
java -cp build/classes:build/demo-processor.jar demo.App
```

**Kết quả mong đợi:** lệnh `jar --list` có `demo/DemoProcessor.class`, `demo/DemoMark.class` và `META-INF/services/javax.annotation.processing.Processor`. Ở bước `javac`, diagnostic chứa `DemoProcessor saw App`; `-XprintRounds` thể hiện round xử lý và `-XprintProcessorInfo` cho biết processor được chọn. Thứ tự/định dạng chi tiết của diagnostic tùy phiên bản JDK; chúng thường xuất hiện trên stderr của compiler, không phải stdout của `java`. Lệnh chạy ứng dụng in chính xác:

```text
Application runs
```

Ở Windows, classpath cho lệnh `java` dùng dấu `;` thay vì dấu `:`. Nếu chỉ cần thử processor mà không tạo `App.class`, thay `-proc:full` bằng `-proc:only` và **không chạy** lệnh `java` ở cuối.

**Phép thử phân biệt lỗi discovery:** giữ nguyên các tham số và thêm `-processor demo.DemoProcessor` vào lệnh `javac`. Nếu cách này hoạt động còn bản dùng service tự động không hoạt động, hãy kiểm tra đường dẫn/nội dung file service trong JAR hoặc kiểu module path. Nếu cả hai không hoạt động, hãy kiểm tra processor path, classloading, phiên bản JDK và lỗi trong processor. Thử bằng một bản build sạch để tránh nhầm với class sinh từ lần trước.

## 4. Quy trình chẩn đoán có thứ tự

### Bước A — Xác nhận compiler có chạy annotation processing

Chạy lệnh build có hiển thị compiler arguments. Kiểm tra `-proc:none`, các lựa chọn bật xử lý, phiên bản JDK và có thực sự biên dịch tệp chứa annotation hay không. Với JDK 23+, nếu chỉ có dependency bình thường trên compile classpath, cấu hình AP có thể chưa đủ. Thử trực tiếp bằng `javac -proc:only -processor ... -processorpath ...` để cô lập việc biên dịch sau xử lý.

`-XprintRounds` hiển thị vòng xử lý, `-XprintProcessorInfo` hiển thị processor/annotation được hỏi; không thấy output trong dự án đã up-to-date không nhất thiết là lỗi processor vì compiler có thể **không được gọi** ở lần build đó. Dùng clean/rebuild có kiểm soát và xác nhận task thực thi.

### Bước B — Xác nhận JAR và service thực sự được đóng gói

Xem nội dung JAR đã xuất bản hoặc được build sử dụng:

```bash
jar --list --file path/to/processor.jar
```

Tìm đúng `META-INF/services/javax.annotation.processing.Processor`, class processor và dependency phù hợp. Việc đặt file service ở `src/main/java` thay vì resources, sai chữ hoa/chữ thường, ghi tên lớp ngắn thay cho tên đủ gói, hoặc không đưa resources vào JAR là nguyên nhân thường gặp. Với processor cùng một module đang được build, compiler không thể load một processor **chưa được compile** trong chính đợt ấy như JAR sẵn có; nên biên dịch/publish processor trước hoặc tách module.

### Bước C — Phân biệt không load được với không match annotation

Bật `-processor demo.DemoProcessor` để bỏ qua service discovery. Nếu báo `not found` hoặc `NoClassDefFoundError`, kiểm tra class, package, các dependency của processor trong processor path, khả năng tương thích phiên bản bytecode (`UnsupportedClassVersionError`) và cấu hình JPMS. Lỗi `ExceptionInInitializerError` có thể đến từ static initializer hoặc constructor của processor; đọc đầy đủ stack trace gốc.

Nếu processor đã được chọn nhưng code của `process` không chạy như dự kiến, kiểm tra `@SupportedAnnotationTypes`, annotation type đang dùng trong source và source set thực sự compile. `@Retention(RetentionPolicy.SOURCE)` vẫn phù hợp cho xử lý ở compile time; không cần đổi thành RUNTIME chỉ để processor tìm thấy annotation. Với filter theo package/element kind, hãy ghi diagnostic rõ số phần tử match; đừng dựa vào `System.out.println` làm kênh chẩn đoán chính.

### Bước D — Phân biệt processor được gọi với tạo output thất bại

Một processor xử lý nhiều round. Đừng viết logic “chỉ round đầu” mà không hiểu source được tạo ở round sau; kiểm tra `roundEnv.processingOver()` và `roundEnv.errorRaised()`. Khi processor tạo file qua `Filer.createSourceFile`, dùng đúng tên đầy đủ và kiểm soát tạo trùng: `FilerException: Attempt to recreate a file for type ...` thường chỉ ra cùng tên file bị tạo nhiều lần trong một lần biên dịch. Nếu gọi `Filer.createResource`, kiểm tra đúng `StandardLocation`, package và tên relative path.

Tệp source sinh ra có thể nằm tại thư mục `-s` hoặc thư mục generated sources do công cụ build đặt; `-d` là output cho class files. Không tìm thấy source trong thư mục class output chưa có nghĩa `Filer` không chạy. Khi `-proc:only`, source generation có thể xảy ra nhưng application class chưa được tạo; đây là hành vi chủ định.

### Bước E — So sánh đúng môi trường build

**Gradle (Groovy DSL):** processor cần khai báo trong cấu hình `annotationProcessor` của source set được biên dịch, thay vì chỉ `implementation`. Ví dụ với hai project đã tồn tại:

```groovy
dependencies {
    implementation project(':annotation-api')
    annotationProcessor project(':demo-processor')
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-XprintRounds', '-XprintProcessorInfo']
}
```

Trong ví dụ này `annotation-api` chứa kiểu annotation còn `demo-processor` chứa processor; tên project chỉ là minh họa. Chạy `./gradlew clean compileJava --info` và đọc task thực thi/processor path. Với test sources, dùng `testAnnotationProcessor` khi processor cần cho `compileTestJava`. Khi dùng build cache/incremental compilation, kiểm tra task có thật sự chạy trước khi kết luận về processor; đừng xóa cache toàn hệ thống theo phản xạ.

**Maven (Compiler Plugin 3.x):** khai báo `annotationProcessorPaths` để Maven cung cấp đường dẫn riêng; nếu muốn cố định processor, dùng `annotationProcessors`. Ví dụ cấu hình bên trong `maven-compiler-plugin` với tọa độ cần thay bằng artifact thật:

```xml
<configuration>
  <release>17</release>
  <annotationProcessorPaths>
    <path>
      <groupId>com.example</groupId>
      <artifactId>demo-processor</artifactId>
      <version>1.0.0</version>
    </path>
  </annotationProcessorPaths>
  <annotationProcessors>
    <annotationProcessor>demo.DemoProcessor</annotationProcessor>
  </annotationProcessors>
  <compilerArgs>
    <arg>-XprintRounds</arg>
    <arg>-XprintProcessorInfo</arg>
  </compilerArgs>
</configuration>
```

Chạy `mvn -X clean compile` để xem JDK, dependency và plugin thực dùng; Maven Compiler Plugin 4.x với Maven 4 còn hỗ trợ khai báo dependency loại `processor` / `classpath-processor` / `modular-processor`, nên đối chiếu đúng major version. `annotationProcessorPaths` không tự cung cấp annotation API cho ứng dụng nếu annotation API không có trong compile dependencies.

**IDE:** IntelliJ IDEA/Eclipse có thể dùng compiler riêng, chạy build qua Gradle/Maven hoặc có cấu hình annotation processing độc lập. Kiểm tra bật annotation processing, processor path, generated sources root và việc IDE dùng cùng JDK/build tool với CLI. Nếu CLI chạy được mà IDE không, tập trung vào cấu hình IDE và delegation trước khi sửa source processor.

## 5. Những nhầm lẫn dễ dẫn đến sửa sai

- **“Có `@Retention(RUNTIME)` mới được xử lý.”** Sai: annotation processor làm việc với mô hình source/compile time; `SOURCE` là lựa chọn hợp lệ.
- **“Có processor JAR trong `implementation` là tự chạy.”** Không chắc, nhất là từ JDK 23 và khi Gradle/Maven dùng processor path riêng.
- **“`-processor` và service file luôn bắt buộc đi cùng nhau.”** Không: `-processor` chỉ định đích danh và giúp bỏ qua discovery. Service file phục vụ cơ chế tự tìm processor trên classpath processor.
- **“Không thấy `System.out` nghĩa là `process` chưa chạy.”** Không đủ bằng chứng; dùng `Messager`, `-XprintRounds` và `-XprintProcessorInfo`.
- **“`-proc:only` lỗi vì không có `.class` của ứng dụng.”** Đây là chế độ chỉ xử lý annotation; dùng `-proc:full` nếu muốn compile tiếp.
- **“Xây dựng thành công tức là file generated phải có.”** Processor có thể không match annotation, có thể không sinh file hoặc task không chạy lại.
- **“Cứ đổi `@SupportedAnnotationTypes` thành `"*"` là ổn.”** Có thể che mất việc khai báo sai và khiến processor nhận nhiều annotation ngoài ý muốn; nên dùng đúng tên đủ gói.

## 6. Checklist khi nhận một báo cáo lỗi

1. Ghi lại **JDK của compiler** và lệnh compiler arguments thực tế; có `-proc:none` hoặc thiếu cấu hình AP trên JDK 23+ không?
2. Chứng minh **task biên dịch đã chạy**, source chứa annotation có nằm trong source set đó không?
3. Đọc **processor path**; kiểm tra JAR, class, dependency và service file (hoặc `provides` trên JPMS).
4. Chạy **`-XprintRounds` + `-XprintProcessorInfo`**; thử **`-processor fully.qualified.Processor`** để tách lỗi discovery khỏi lỗi load và matching.
5. Nếu processor đã chạy, ghi diagnostic bằng **`Messager`**, kiểm tra annotation name, các round, `Filer` và thư mục output.
6. Đối chiếu giữa **CLI và Gradle/Maven/IDE**, kiểm tra build cache, test source set và phiên bản compiler/plugin.

Ghi lại lệnh tái hiện tối thiểu, lỗi đầy đủ và sự khác biệt trước/sau khi sửa. Khi xác định được nguyên nhân, đưa cấu hình processor rõ ràng vào build để lỗi không tái diễn khi nâng JDK hoặc chuyển môi trường.

## Tài liệu tra cứu

- Oracle, `javac` (tùy chọn `-processor`, `-processorpath`, `-proc`, `-XprintRounds`, `-XprintProcessorInfo`): https://docs.oracle.com/en/java/javase/23/docs/specs/man/javac.html
- Inside Java, thay đổi chính sách annotation processing mặc định từ JDK 23: https://inside.java/2024/06/18/quality-heads-up/
- Apache Maven Compiler Plugin, cấu hình annotation processors: https://maven.apache.org/plugins/maven-compiler-plugin-4.x/examples/annotation-processor.html
