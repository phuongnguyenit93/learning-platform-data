# Tách processor path, processor module path và classpath ứng dụng khi biên dịch Java

## 1. Vì sao cần ba đường dẫn khác nhau?

Một dự án dùng **annotation processing (JSR 269)** có ít nhất hai vai trò rất khác: mã Java đang được biên dịch và **chương trình processor** mà `javac` nạp để phân tích các annotation, kiểm tra khai báo hoặc sinh thêm mã. Nếu tất cả dependency đều được đưa lên một classpath duy nhất, project có thể vẫn chạy ở một số cấu hình nhưng dễ gặp các vấn đề:

- Compiler không tìm được annotation class trong source (`package ... does not exist`).
- Compiler tìm được annotation nhưng không nạp hoặc không chạy processor, khiến generated type không tồn tại (`cannot find symbol`).
- Processor có JAR nhưng thiếu dependency **của chính processor** khi nạp (`NoClassDefFoundError`, `ServiceConfigurationError`).
- Processor vô tình xuất hiện trên runtime classpath của ứng dụng, làm tăng kích thước và phụ thuộc không cần thiết.
- Nâng lên JDK 23+ khiến việc trông chờ **tự khám phá processor tình cờ trên classpath** không còn hoạt động theo mặc định.
- Trộn `--processor-module-path` và `-processorpath` trong cùng invocation gây lỗi ngay ở tùy chọn compiler.

Ba khái niệm chính:

| Đường dẫn | Ai tiêu thụ? | Chứa gì? | Tùy chọn `javac` |
| --- | --- | --- | --- |
| **Application compile classpath** | Compiler khi resolve các kiểu mà **source ứng dụng** sử dụng | Annotation API, library/compiled classes mà source cần | `-cp`, `-classpath`, `--class-path` |
| **Processor path** | Compiler khi **tìm và nạp processor dạng classpath** | Processor implementation, các dependency của processor | `-processorpath`, `--processor-path` |
| **Processor module path** | Compiler khi **tìm và nạp processor là named module** | Module cung cấp `Processor`, module dependencies | `--processor-module-path` |

**Điểm cốt lõi:** processor path và processor module path là **hai cách khác nhau để triển khai processor**, không phải hai phần bắt buộc luôn phải dùng cùng nhau. Trong một lệnh `javac`, chọn đường dẫn processor thích hợp. Application classpath (hoặc application module path) là cấu hình **độc lập** dành cho mã đang biên dịch.

Không nhầm `--processor-module-path` với `--module-path`: cái trước là nơi nạp **module của processor**; cái sau là nơi resolve **module của chương trình đang build**. Cả hai đều chứa chữ *module*, nhưng phục vụ hai hệ dependency khác nhau.

## 2. Sơ đồ các lớp dependency tại compile time

~~~text
                             JAVAC
                       (compiler process)
                               |
             +-----------------+-----------------+
             |                                   |
             v                                   v
  Resolve chương trình                Nạp và chạy Processor
  (app/annotation API)                (JSR 269, từng round)
             |                                   |
   -classpath / --module-path         -processorpath
             |                         HOẶC
             |                         --processor-module-path
             |                                   |
             +----------+------------------------+
                        |
                        v
              Generated Java source
                        |
                        v
          Compile input + generated sources
                        |
                        v
                    .class files
~~~

Một cách phân loại dependency thực tế:

- **Annotation API artifact:** cung cấp `@Generate`, `@Mapper` hoặc marker annotations; source ứng dụng phải nhìn thấy các kiểu đó khi compile. Nếu annotation chỉ có `RetentionPolicy.SOURCE` và không còn được bytecode/runtime tham chiếu, artifact này có thể chỉ là compile-time dependency.
- **Processor implementation artifact:** cung cấp class implement `javax.annotation.processing.Processor`; compiler phải nạp nó trong quá trình build. Thông thường ứng dụng **không cần** processor implementation khi chạy.
- **Processor's own dependencies:** các JAR/module mà class processor gọi khi nó đang chạy trong compiler. Chúng phải có ở **đường nạp processor**, không phải chỉ ở application classpath.
- **Application libraries:** các kiểu source gọi trong chương trình; đưa vào compile classpath/module path và, nếu bytecode cần khi thực thi, runtime classpath/module path.

Có dự án cố ý đóng gói annotation API và processor trong **cùng một JAR**. Đây là lựa chọn đóng gói được phép, nhưng cần ý thức rằng thêm JAR đó làm compile dependency có thể kéo processor implementation vào phạm vi không cần thiết. Tách thành hai artifact thường giúp kiểm soát vai trò và giới hạn dependency tốt hơn.

## 3. Cơ chế khám phá processor: `-processor`, service provider và JDK 23+

Có hai cách chính để `javac` biết processor nào cần chạy:

1. **Nêu rõ class processor**, ví dụ `-processor ap.GenerateProcessor`, và cung cấp nơi nạp nó (`-processorpath processor.jar` đối với processor trên classpath).
2. **Service-provider discovery**, với file `META-INF/services/javax.annotation.processing.Processor` trong JAR classpath-style, hoặc `provides javax.annotation.processing.Processor with ...` trong module descriptor của named module processor.

Từ **JDK 23**, mặc định `javac` không chạy annotation processors chỉ vì có processor tình cờ xuất hiện trên classpath. Đây là thay đổi quan trọng về hành vi discovery. Hãy cấu hình annotation processing **tường minh**, chẳng hạn qua `-processor`, `-processorpath`, `--processor-module-path` hoặc `-proc:full` nếu compiler hỗ trợ. Với các bản JDK trước, auto-discovery trên classpath có thể từng làm build “tự nhiên hoạt động” nhưng phụ thuộc môi trường và kém an toàn hơn.

Các mode:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `-proc:none` | Không chạy annotation processing. |
| `-proc:only` | Chạy processing nhưng không thực hiện compile bytecode thông thường sau đó. |
| `-proc:full` | Chạy processing và tiếp tục compile. |
| `-processor a.b.X` | Chỉ đích danh class processor; không yêu cầu service file khi load theo classpath với processor path đúng. |
| `-XprintRounds` | In các processing rounds để chẩn đoán. |
| `-XprintProcessorInfo` | In thông tin processor đã được gọi và các annotation được claim. |

**Không đồng nhất `-processorpath` với việc “bật một annotation cụ thể”.** Tùy chọn này chỉ xác định **nơi tìm processor**; processor nào được chọn còn do `-processor`, service registration và quy tắc discovery của compiler. Nếu tự chỉ định `-processor`, nên biết chính xác những processor cần được chạy, không vô tình loại bỏ processor khác vốn cần thiết.

## 4. Ví dụ đầy đủ: tách annotation API, processor và ứng dụng

Ví dụ sử dụng Java 17+ (được kiểm chứng bằng `javac --release 17`). Một annotation `@Generate` đánh dấu class `App`; processor tạo `demo.Generated`; ứng dụng gọi `Generated.say()` dù source này chưa được viết tay.

Cấu trúc ban đầu:

~~~text
project/
  api/
    demo/Generate.java
  processor/
    ap/GenerateProcessor.java
    META-INF/services/javax.annotation.processing.Processor
  app/
    demo/App.java
  processor-module/
    module-info.java
    ap/GenerateProcessor.java
~~~

Thư mục `processor-module/` phục vụ **biến thể modular ở phần 7**; không cần cho lần chạy qua processor path ở phần 5. Hai bản source `GenerateProcessor.java` có cùng nội dung trong ví dụ, nhưng chúng được đóng gói riêng theo hai chiến lược, **không dùng cả hai cùng lúc**.

### 4.1. Tệp `api/demo/Generate.java`

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface Generate {}
~~~

Annotation ở `SOURCE` retention vẫn được processor nhìn thấy trong compilation. Không cần `RUNTIME` retention để compiler xử lý annotation. Việc đánh dấu class cũng không tự sinh code: phải có processor chạy và tạo tệp nguồn.

### 4.2. Tệp `processor/ap/GenerateProcessor.java`

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

@SupportedAnnotationTypes("demo.Generate")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class GenerateProcessor extends AbstractProcessor {
    private boolean made;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment env) {
        if (env.processingOver() || made) {
            return true;
        }

        TypeElement annotation = processingEnv.getElementUtils()
                .getTypeElement("demo.Generate");
        if (annotation == null) {
            return false;
        }

        for (Element element : env.getElementsAnnotatedWith(annotation)) {
            try (Writer writer = processingEnv.getFiler()
                    .createSourceFile("demo.Generated", element)
                    .openWriter()) {
                writer.write("package demo; public final class Generated { "
                        + "public static String say() { return \"generated\"; }}");
                made = true;
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, ex.toString(), element);
            }
        }
        return true;
    }
}
~~~

**Điều đáng chú ý:** processor không import trực tiếp `demo.Generate`; nó khai báo tên annotation bằng chuỗi và dùng mô hình `TypeElement`. Bởi vậy có thể **biên dịch processor độc lập** với `annotations.jar` trong ví dụ. Nếu processor thực sự import `demo.Generate` hoặc gọi một class hỗ trợ thuộc API artifact, dependency đó có thể cần có trên **classpath khi compile processor** và cả **processor path khi chạy processor**.

Các thành phần:
- `@SupportedAnnotationTypes` chọn annotation mà processor hiểu.
- `RoundEnvironment` cung cấp các phần tử tương ứng ở mỗi round.
- `Filer.createSourceFile` tạo Java source; `javac` biên dịch source đó ở các bước tiếp theo.
- `made` ngăn việc tạo trùng `demo.Generated`; code đơn giản này giả định một annotated element. Trong code sản xuất phải xử lý nhiều phần tử, tên file xung đột và incremental build đúng cách.
- `Messager` phát error khi thao tác file thất bại.

`javax.annotation.processing` là package Java SE chuẩn ngay cả trên JDK hiện đại. Không đổi sang `jakarta.annotation.processing` chỉ vì một số Java EE/Jakarta EE APIs có tên `jakarta.*`.

### 4.3. Tệp `app/demo/App.java`

~~~java
package demo;

@Generate
public class App {
    public static void main(String[] args) {
        System.out.println(Generated.say());
    }
}
~~~

Chưa có file `Generated.java` do lập trình viên tạo. Lệnh compile không chạy processor và không cung cấp generated class sẽ báo lỗi `cannot find symbol` tại `Generated.say()`, mặc dù annotation API đã được resolve.

### 4.4. Service descriptor cho processor trên classpath

Tệp văn bản **`processor/META-INF/services/javax.annotation.processing.Processor`** có duy nhất tên implementation:

~~~text
ap.GenerateProcessor
~~~

Dòng này cho cơ chế service-provider discovery biết class nào cung cấp dịch vụ `Processor`. Nếu dùng `-processor ap.GenerateProcessor` trực tiếp, service descriptor **không bắt buộc** cho ví dụ, nhưng khi đóng gói JAR cho build tool hoặc discovery thì cần đăng ký hợp lệ.

## 5. Chạy processor dạng JAR với `-processorpath`

Tại thư mục `project/`, tạo các output directories (Bash):

~~~bash
mkdir -p api-classes processor-classes app-classes generated
~~~

### 5.1. Biên dịch và đóng gói annotation API

~~~bash
javac --release 17 -encoding UTF-8 \
  -d api-classes api/demo/Generate.java

jar --create --file annotations.jar -C api-classes .
~~~

JAR `annotations.jar` phải có entry `demo/Generate.class`; nó là artifact để **source app resolve annotation**.

### 5.2. Biên dịch và đóng gói processor

~~~bash
javac --release 17 -encoding UTF-8 \
  -d processor-classes processor/ap/GenerateProcessor.java

jar --create --file processor.jar \
  -C processor-classes . \
  -C processor META-INF/services/javax.annotation.processing.Processor
~~~

Sau khi đóng gói, `processor.jar` chứa:
- `ap/GenerateProcessor.class`
- `META-INF/services/javax.annotation.processing.Processor`

**Không cần** thêm `processor.jar` vào application classpath của `App.java` chỉ để processor chạy. Cần truyền nó qua **processor path**, và application source chỉ cần `annotations.jar` để resolve `@Generate`.

### 5.3. Lệnh biên dịch ứng dụng tách biệt hai đường dẫn

~~~bash
javac --release 17 -encoding UTF-8 \
  -cp annotations.jar \
  -processorpath processor.jar \
  -processor ap.GenerateProcessor \
  -XprintRounds \
  -s generated \
  -d app-classes \
  app/demo/App.java
~~~

Hai tham số quan trọng nhất:

- **`-cp annotations.jar`**: `javac` đọc kiểu `demo.Generate` mà source ứng dụng sử dụng; đây là compile classpath **của ứng dụng**.
- **`-processorpath processor.jar`**: `javac` tìm và nạp `ap.GenerateProcessor`; đây là classpath **của compiler plugin/processor**, độc lập với application classpath.

`-processor ap.GenerateProcessor` làm việc chọn processor trở nên tường minh. `-s generated` chỉ đường dẫn generated Java sources; `-d app-classes` là output class files. Trên Windows PowerShell/cmd, đặt mỗi invocation thành **một dòng** hoặc đổi cú pháp nối dòng cho phù hợp: dấu `\` trong ví dụ là của Bash.

Đầu ra round quan trọng từ phép thử với `javac` (thụt lề trong log có thể thay đổi theo JDK):

~~~text
Round 1:
    input files: {demo.App}
    annotations: [demo.Generate]
    last round: false
Round 2:
    input files: {demo.Generated}
    annotations: []
    last round: false
Round 3:
    input files: {}
    annotations: []
    last round: true
~~~

Round 1 xử lý source đầu vào; round 2 nhận tệp `demo.Generated` do processor tạo; round 3 là round kết thúc. Không có ba lần gọi `javac` ở đây: **ba round diễn ra trong cùng invocation ứng dụng**.

Chạy:

~~~bash
java -cp app-classes demo.App
~~~

Stdout chính xác:

~~~text
generated
~~~

`annotations.jar` không bắt buộc có mặt trong **runtime classpath của ví dụ này**: annotation `@Generate` có `SOURCE` retention và ứng dụng không cần gọi class annotation ở runtime. Đây là đặc điểm của **chính ví dụ này**, không phải quy tắc rằng mọi annotation API đều có thể loại khỏi runtime. Nếu annotation có `RUNTIME` retention và framework dùng reflection, hoặc mã runtime dùng API annotation, hãy cung cấp artifact phù hợp.

Các output tương ứng:

~~~text
annotations.jar       # chứa demo/Generate.class
processor.jar         # chứa ap/GenerateProcessor.class + service descriptor
generated/
  demo/Generated.java
app-classes/
  demo/App.class
  demo/Generated.class
~~~

### 5.4. Nếu không chỉ đích danh processor?

Vì `processor.jar` đã có service descriptor, cũng có thể dùng:

~~~bash
javac --release 17 -encoding UTF-8 \
  -cp annotations.jar \
  -processorpath processor.jar \
  -s generated -d app-classes app/demo/App.java
~~~

Với `javac 24.0.2`, cấu hình processor path tường minh cho phép discovery của service provider; ví dụ biên dịch thành công. Đừng dựa vào việc processor được nạp **chỉ vì JAR hiện diện đâu đó trên application classpath**, đặc biệt từ JDK 23.

## 6. Nếu processor path có dependency thì đặt ở đâu?

Giả sử `ap.GenerateProcessor` gọi một thư viện hỗ trợ `com.acme.codegen.WriterHelper` nằm trong `codegen-helper.jar`. Thư viện đó phải đọc được khi **processor đang chạy trong compiler**.

Trong trường hợp processor classpath-style trên Bash/macOS/Linux:

~~~bash
javac --release 17 -encoding UTF-8 \
  -cp annotations.jar \
  -processorpath "processor.jar:codegen-helper.jar" \
  -processor ap.GenerateProcessor \
  -d app-classes app/demo/App.java
~~~

Trên Windows, dùng `-processorpath "processor.jar;codegen-helper.jar"`.

`codegen-helper.jar` ở đây là **tên minh họa**, không phải artifact tồn tại trong ví dụ phần 5. Lệnh sẽ chỉ chạy khi thư viện thực sự tồn tại và processor cần nó được biên dịch tương ứng.

Nếu thiếu dependency khi load hoặc trong lúc processor thực thi, có thể gặp:

~~~text
java.lang.NoClassDefFoundError: com/acme/codegen/WriterHelper
~~~

hoặc lỗi service loading/processor khởi tạo, tùy điểm phát sinh. Thêm `codegen-helper.jar` vào **application classpath** không bảo đảm sửa được thiếu dependency **trên processor path** nếu javac đang dùng processor loader tách biệt. Ngược lại, thư viện mà source ứng dụng import phải nằm trên application compile path; chỉ thêm vào processor path cũng không đủ.

**Tách dependency là một ranh giới logic và công cụ build**, không phải sandbox bảo mật tuyệt đối. Annotation processor chạy mã Java trong quá trình biên dịch, có thể truy cập tệp, môi trường và tài nguyên mà tiến trình compiler có quyền. Chỉ chạy processor từ nguồn đáng tin, khóa version và xem xét dependency supply chain.

## 7. Processor là named module: dùng `--processor-module-path`

Khi muốn đóng gói processor dưới dạng **JPMS named module**, dùng Java module descriptor với service `provides` thay vì service file kiểu classpath.

Tạo **`processor-module/module-info.java`**:

~~~java
module demo.processor {
    requires java.compiler;
    provides javax.annotation.processing.Processor
            with ap.GenerateProcessor;
}
~~~

Tạo **`processor-module/ap/GenerateProcessor.java`** có **nội dung hoàn toàn giống** `processor/ap/GenerateProcessor.java` ở phần 4.2. Không cần copy service descriptor `META-INF/services` vào module JAR cho ví dụ modular này: provider được khai báo ở `module-info.java`.

Giải thích:
- `requires java.compiler`: processor dùng API Java Compiler (JSR 269).
- `provides ... with ap.GenerateProcessor`: đăng ký implementation `Processor` để compiler discover từ processor module path.
- Không phải export package `ap` chỉ để code ứng dụng import class processor; **source ứng dụng không cần tham chiếu implementation**. Java module service loading có cơ chế riêng cho provider.
- Module `demo.processor` là module của **công cụ chạy lúc compile**, không phải module bắt buộc của ứng dụng.

### 7.1. Build processor module

~~~bash
mkdir -p processor-module-classes generated-mod app-classes-mod

javac --release 17 -encoding UTF-8 \
  -d processor-module-classes \
  processor-module/module-info.java \
  processor-module/ap/GenerateProcessor.java

jar --create --file processor-mod.jar -C processor-module-classes .
~~~

Kiểm tra bằng:

~~~bash
jar --describe-module --file processor-mod.jar
~~~

Kết quả cần thể hiện module `demo.processor`, dependency `java.compiler` và provider `ap.GenerateProcessor`. Output dạng dòng/phiên bản có thể khác giữa các bản JDK.

### 7.2. Dùng processor module path, còn App vẫn dùng classpath

~~~bash
javac --release 17 -encoding UTF-8 \
  -cp annotations.jar \
  --processor-module-path processor-mod.jar \
  -XprintRounds \
  -s generated-mod \
  -d app-classes-mod \
  app/demo/App.java
~~~

Không có `-processorpath` trong lệnh này. Compiler khám phá processor qua **module service descriptor** và xử lý annotation của source ứng dụng. `App.java` và `annotations.jar` trong ví dụ vẫn theo mô hình classpath/unnamed module: **processor dùng module path không buộc cả ứng dụng cũng thành named module**.

Với `javac 24.0.2`, ví dụ đã kiểm chứng: sinh `generated-mod/demo/Generated.java`, in ba processing rounds như phần 5 và chạy:

~~~bash
java -cp app-classes-mod demo.App
~~~

Stdout:

~~~text
generated
~~~

Nếu processor module cần module phụ thuộc riêng, các dependency đó phải được giải quyết trong **processor module layer** theo JPMS. Không chỉ nối thêm JAR vào application classpath rồi kỳ vọng module processor tự đọc được. Với dependency đóng gói là automatic module, phải cân nhắc tên module, readability và khả năng tương thích khi module hóa.

### 7.3. Có thể bật cả `-processorpath` và `--processor-module-path`?

**Không.** Khi thử cùng một invocation:

~~~bash
javac --release 17 \
  -cp annotations.jar \
  -processorpath processor.jar \
  --processor-module-path processor-mod.jar \
  -d app-classes app/demo/App.java
~~~

`javac 24.0.2` báo:

~~~text
error: illegal combination of -processorpath and --processor-module-path
~~~

Đừng giải quyết bằng cách truyền hai đường dẫn để “tìm processor ở cả hai nơi”. Hãy chọn **một chiến lược nạp processor** cho compile invocation. Nếu ứng dụng cần nhiều processor có cách đóng gói khác nhau, cần tổ chức lại cách đóng gói/cấu hình ở mức build tool và đảm bảo compiler có thể nạp chúng theo cơ chế được hỗ trợ, thay vì đặt hai cờ loại trừ nhau.

## 8. Phân biệt application module path và processor module path

Một ứng dụng module hóa có thể có:

~~~java
module demo.app {
    requires demo.annotations;
}
~~~

Đây là **ví dụ `module-info.java` cho một ứng dụng JPMS khác**; `demo.annotations` cần thật sự là module mà application đọc được, có package được export. Nó **không thuộc các tệp runnable ở phần 4**, nơi `annotations.jar` chỉ là JAR thông thường trên `-cp`.

Với JPMS, có thể có **bốn** trục cần nhận diện:

| Trục | Chứa | Mục tiêu |
| --- | --- | --- |
| `--class-path` | Thư viện/class dùng bởi source theo unnamed module | Resolve symbols của ứng dụng |
| `--module-path` | Các named/automatic module của chương trình | Resolve và kiểm tra readability/exports của ứng dụng |
| `--processor-path` | Processor JAR + classpath dependencies | Load classpath-based processors |
| `--processor-module-path` | Processor module + module dependencies | Load modular processors |

Trong một invocation có thể dùng **application module path** cùng với **processor module path** nếu project module hóa và processor modular. Hai tùy chọn này không bị loại trừ nhau vì chúng phục vụ những vai trò khác nhau. Sự loại trừ là giữa **processor path** và **processor module path**.

Đối với một dự án JPMS, package của annotation có thể tồn tại nhưng không accessible nếu module descriptor của ứng dụng thiếu `requires` hoặc module thư viện không `exports` package. Đó là bài toán **module readability/exports** khác với “processor không được nạp”.

## 9. Thực nghiệm âm tính: biết mình thiếu đường dẫn nào

### 9.1. Chỉ có annotation API, không chạy processor

Ví dụ dùng `-proc:none`:

~~~bash
javac --release 17 -encoding UTF-8 \
  -cp annotations.jar \
  -proc:none -d app-classes app/demo/App.java
~~~

Lệnh chủ ý **thất bại** khi output sạch và chưa có `demo.Generated`:

~~~text
error: cannot find symbol
        System.out.println(Generated.say());
                           ^
  symbol:   variable Generated
  location: class App
~~~

`@Generate` đã resolve được vì `annotations.jar` có trên application classpath. Lỗi xảy ra ở **generated type** do processing bị tắt.

### 9.2. Thiếu annotation API trên compile classpath

Nếu chỉ truyền `-processorpath processor.jar` mà không đưa `annotations.jar` vào app compile path, source `@Generate` có thể thất bại với:

~~~text
error: cannot find symbol
@Generate
 ^
  symbol: class Generate
~~~

Processor thấy mình qua processor path **không đồng nghĩa source app cũng nhìn thấy các annotation type**. Tương tự, nếu annotation thuộc package khác, import sẽ có thể báo `package ... does not exist`.

### 9.3. Processor có mà không được chọn/chạy

Nếu processor JAR nằm trên app classpath mà không có cấu hình processing tường minh, hành vi phụ thuộc compiler/JDK và các flags. Với JDK 23+ không trông chờ implicit processing; compiler có thể không chạy processor, nên generated class vẫn thiếu. Cách đúng: cấp đúng processor path/module path và yêu cầu discovery hoặc chỉ định processor.

### 9.4. Thiếu dependency của processor

Khi `javac` báo lỗi trong lúc load processor (`NoClassDefFoundError` / provider initialization), hãy kiểm tra **processor dependency graph**. Đừng chữa bằng cách thêm tất cả dependency vào application runtime path: đó là tập khác.

### 9.5. Processor sinh source nhưng app vẫn không compile

Kiểm tra generated source trong `-s` có đúng package/kiểu hay không, processor có ném error không, round có nhận source mới không, source sinh ra có compile error không. Đừng giả định mọi `cannot find symbol` đều do một path thiếu; processor có thể tạo sai tên hoặc không thỏa điều kiện sinh.

## 10. Build tool: cấu hình dependency theo vai trò

Trong dự án thực, developer thường không tự gõ `javac` từng lần; Maven và Gradle dựng compiler arguments. Cách đặt dependency cần giữ ranh giới chức năng giống như lệnh tay.

### 10.1. Gradle Java plugin

Ví dụ Groovy DSL (`build.gradle`):

~~~groovy
plugins {
    id 'java'
}

dependencies {
    compileOnly 'com.example:annotations-api:1.0.0'
    annotationProcessor 'com.example:generate-processor:1.0.0'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
~~~

Đây là **cấu hình minh họa**: `com.example:annotations-api:1.0.0` và `com.example:generate-processor:1.0.0` không phải artifact được khẳng định tồn tại. Thay bằng tọa độ thực tế của thư viện.

- `compileOnly`: cung cấp annotation API cho source compile; không tự thêm vào runtime classpath. Chỉ phù hợp khi ứng dụng thật sự **không cần** dependency đó ở runtime.
- `annotationProcessor`: dependency dành cho processor path của tác vụ `JavaCompile`; không đồng nghĩa `implementation`.
- `implementation`: dùng cho library mà source ứng dụng cần cả compile và runtime.
- `runtimeOnly`: không cấp class cho source import tại compile time.

Nếu có Java test source cũng dùng annotation processor, cần quan tâm `testAnnotationProcessor` và dependencies/source sets của test. Với Kotlin/KAPT/KSP, cấu hình processor phải qua plugin tương ứng; không gộp các hệ processing với JSR 269 thuần Java.

Khi dùng processor là **JPMS named module**, kiểm tra Gradle JavaCompile/Gradle plugin version và cách nó dựng `--processor-module-path`. `annotationProcessor` là **dependency configuration** của Gradle, còn `--processor-module-path` là **tùy chọn javac**; không thể mặc định khẳng định mọi Gradle version sẽ tự suy ra chiến lược nạp module processor từ một dependency mang `module-info.class`.

### 10.2. Maven Compiler Plugin

Với các phiên bản Maven Compiler Plugin hỗ trợ `annotationProcessorPaths`, có thể tách annotation API dependency với processor artifact:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>annotations-api</artifactId>
        <version>1.0.0</version>
        <scope>provided</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <release>17</release>
                <annotationProcessorPaths>
                    <path>
                        <groupId>com.example</groupId>
                        <artifactId>generate-processor</artifactId>
                        <version>1.0.0</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là **đoạn POM** để đặt trong một `<project>` hoàn chỉnh, không phải POM tự chạy độc lập; tọa độ dependency chỉ minh họa. `provided` trong Maven vẫn đưa dependency lên **compile classpath**, nhưng giả định môi trường cung cấp dependency nếu cần khi runtime; với annotation `SOURCE` không dùng runtime, đây có thể là một lựa chọn phù hợp. Nếu annotation có vai trò runtime, scope phải được xét lại.

Cách thiết lập processor path hoặc processor module path ở Maven **phụ thuộc phiên bản Maven Compiler Plugin** và cấu hình loại dependency. Plugin 3.x phổ biến dùng `annotationProcessorPaths`; các phiên bản plugin mới có thêm cơ chế dependency chuyên dụng (processor/classpath-processor/modular-processor). Cần xem tài liệu **đúng phiên bản** và effective POM, không giả định một cấu hình cũ tự xử lý modular processor đúng trên mọi JDK.

### 10.3. Quy tắc chung cho build tool

1. **Annotation API** ở compile classpath hoặc application module path nếu source import annotation.
2. **Processor implementation** ở processor path hoặc processor module path; tránh đưa vào runtime artifact nếu không cần.
3. **Dependency của processor** ở đúng classpath/module path phục vụ processor loader.
4. **Generated sources** được compile task theo dõi, đặt ở output riêng, không sửa thủ công.
5. **JDK 23+** có chính sách processor discovery mới: kiểm tra compiler arguments thay vì dựa vào việc classpath tình cờ chứa processor.
6. **Gradle/Maven compiler versions và JDK toolchain** phải tương thích với kiểu nạp processor đang dùng.

## 11. Kiểm tra đường dẫn bằng các công cụ của JDK

### Liệt kê nội dung artifact

~~~bash
jar tf annotations.jar
jar tf processor.jar
jar tf processor-mod.jar
~~~

Kết quả cần phân biệt:
- `annotations.jar` chứa `demo/Generate.class`.
- `processor.jar` chứa `ap/GenerateProcessor.class` và service descriptor trong `META-INF/services`.
- `processor-mod.jar` chứa `module-info.class` và `ap/GenerateProcessor.class`; module descriptor là nơi `provides`.

### Xác minh processor modular

~~~bash
jar --describe-module --file processor-mod.jar
~~~

Kiểm tra module name, `requires java.compiler` và `provides javax.annotation.processing.Processor with ap.GenerateProcessor`.

### Xem processor có được gọi thật không

~~~bash
javac --release 17 -encoding UTF-8 \
  -cp annotations.jar \
  -processorpath processor.jar \
  -processor ap.GenerateProcessor \
  -XprintRounds -XprintProcessorInfo \
  -s generated -d app-classes app/demo/App.java
~~~

Nếu round đầu không có annotation được kỳ vọng, kiểm tra tên annotation, `@SupportedAnnotationTypes` và source đầu vào. Nếu processor không xuất hiện, kiểm tra loader path và service/processor name. Nếu source được sinh nhưng compile fail, đọc diagnostic từ generated Java file; đường dẫn khác nhau không thể thay cho việc xử lý lỗi nội dung.

### Xem javac hỗ trợ flags nào

~~~bash
javac --help
javac -version
~~~

Đặc biệt khi làm việc với Java 17, 21, 23+, kiểm tra invocation thực tế của compiler, không chỉ giá trị `java -version` in từ một terminal khác.

## 12. Những ngộ nhận cần tránh

**Ngộ nhận 1: “Processor JAR phải luôn nằm trên application classpath.”** Sai. Processor có đường nạp riêng; app chỉ cần các API được source hoặc runtime sử dụng.

**Ngộ nhận 2: “Tôi đã thêm annotations.jar vào -processorpath nên @Generate phải được resolve.”** Không đúng nếu source cần kiểu này mà compile classpath/module path không chứa nó. Hai loader phục vụ hai nhiệm vụ.

**Ngộ nhận 3: “Processor path và processor module path dùng đồng thời sẽ tăng khả năng tìm thấy processor.”** Trên `javac` tiêu chuẩn, đây là kết hợp không hợp lệ.

**Ngộ nhận 4: “Processor là named module thì ứng dụng cũng bắt buộc có module-info.java.”** Sai. Ví dụ ở phần 7 cho thấy processor module path và app classpath có thể cùng tồn tại.

**Ngộ nhận 5: “Mọi JDK đều tự quét processor trên classpath ứng dụng.”** Không. JDK 23+ thay đổi mặc định; cấu hình tường minh an toàn và tái lập hơn.

**Ngộ nhận 6: “Processor dependency có thể thay bằng runtimeOnly.”** Sai. `runtimeOnly` của ứng dụng không cung cấp dependency cho JVM đang chạy processor trong compiler khi processor path riêng đã được thiết lập.

**Ngộ nhận 7: “Compiler tạo source xong là ứng dụng tự chạy được, dù compile có lỗi.”** Sai. Generated source vẫn cần được phân tích và biên dịch, đúng classpath/module graph và không có lỗi ngữ nghĩa.

**Ngộ nhận 8: “Chỉ cần một --module-path cho tất cả.”** Sai. Application modules và processor modules có vai trò khác nhau; processor module path không phải application module path.

**Ngộ nhận 9: “Tách processor path là sandbox an toàn.”** Sai. Nó giúp kiểm soát dependency/discovery, không cô lập quyền truy cập của mã processor chạy trong compiler.

**Ngộ nhận 10: “Generated class không thấy nghĩa là processor không được nạp.”** Chưa chắc. Processor có thể được gọi nhưng không match annotation, sinh sai package, phát error, hoặc output bị loại khỏi compile task.

## 13. Quy trình chẩn đoán nhanh

Khi báo `package ... does not exist`, `cannot find symbol`, `Processor ... not found` hoặc `NoClassDefFoundError` trong build có annotation processing, đi theo thứ tự:

1. **Xác định đối tượng lỗi**: annotation type của source, processor implementation, dependency của processor, hay generated class?
2. **Đọc compiler invocation**: ghi lại chính xác `-cp`, `--module-path`, `-processorpath`, `--processor-module-path`, `-processor`, `-proc:...` và phiên bản `javac`.
3. **Kiểm tra JAR/module thực tế**: `jar tf`, `jar --describe-module`, package và class names.
4. **Kiểm tra discovery**: service descriptor cho processor JAR hoặc `provides` trong module descriptor; với JDK 23+, đừng trông chờ classpath discovery ngầm.
5. **Bật `-XprintRounds`**: xem annotation có được xử lý, generated class có xuất hiện ở round sau không.
6. **Kiểm tra processor dependencies**: nếu crash khi load processor, sửa processor path/module path, không sửa bừa application path.
7. **Kiểm tra generated source/output**: `-s` cho source, `-d` cho `.class`; đừng nhầm hai đường dẫn.
8. **Làm sạch build và thử lại**: tránh `.class` hoặc source generated cũ che mất nguyên nhân.
9. **Cố định cấu hình trong Maven/Gradle**: bảo đảm IDE và CI dùng cùng dependency graph, toolchain và processor mode.

Ví dụ phân loại:

| Triệu chứng | Kiểm tra trước |
| --- | --- |
| Không thấy `@Generate` | `annotations.jar` trên app compile classpath/module path |
| Không thấy `ap.GenerateProcessor` | Processor implementation JAR/module có đúng ở processor path/module path không |
| `NoClassDefFoundError` từ code processor | Dependency của processor loader thiếu hoặc không đọc được |
| `Generated` không tồn tại | Processor có chạy, match annotation và sinh source đúng không |
| `illegal combination of -processorpath and --processor-module-path` | Bỏ một trong hai chiến lược, cấu hình thống nhất |
| Build chạy trên JDK 17 nhưng không chạy trên JDK 23+ | Kiểm tra implicit processor discovery và explicit processing flags |
| Compilation pass nhưng runtime thiếu helper của ứng dụng | Kiểm tra runtime classpath/module path; không dùng processor path để “sửa” runtime |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Source `App.java` import `demo.Generate`, processor JAR ở `-processorpath` nhưng annotations.jar không nằm trên `-cp`. Vì sao lỗi?  
**Đáp án:** Compile classpath của **ứng dụng** không thấy annotation API. Processor path không thay thế tập resolve symbols của source.

**Câu 2.** Processor `ap.GenerateProcessor` gọi library hỗ trợ riêng ở `helper.jar`. Thêm `helper.jar` vào đâu khi processor đang được nạp từ `-processorpath`?  
**Đáp án:** Cần bảo đảm nó có trên processor path cùng processor, chẳng hạn `-processorpath "processor.jar:helper.jar"` trên Unix hoặc `"processor.jar;helper.jar"` trên Windows.

**Câu 3.** Có thể compile app không module hóa nhưng dùng processor modular qua `--processor-module-path` không?  
**Đáp án:** Có. Ví dụ phần 7 dùng `-cp annotations.jar` và `--processor-module-path processor-mod.jar` trong cùng invocation.

**Câu 4.** Named module processor đăng ký implementation với cơ chế nào?  
**Đáp án:** `provides javax.annotation.processing.Processor with ap.GenerateProcessor;` trong `module-info.java`, cộng với dependency `requires java.compiler` tương ứng.

**Câu 5.** Dùng đồng thời `-processorpath` và `--processor-module-path` có hợp lệ không?  
**Đáp án:** Không; `javac` từ chối kết hợp này.

**Câu 6.** Vì sao Java 23+ có thể không sinh class dù processor JAR có trong application classpath?  
**Đáp án:** Không nên phụ thuộc auto-discovery ngầm. Cần cấu hình processor execution tường minh theo JDK và build tool.

**Câu 7.** Đặt `@Generate` là `SOURCE` retention có cản processor nhận annotation khi compile không?  
**Đáp án:** Không. Compiler nhìn được annotation trong source ở processing round.

**Câu 8.** Processor là compile-time dependency thì có cần đặt trên runtime classpath của ứng dụng không?  
**Đáp án:** Thường không. Chỉ đưa vào runtime các thư viện mà bytecode/runtime logic thực sự cần.

**Câu 9.** Có đúng mọi `cannot find symbol` trong dự án dùng processor đều do processor path thiếu không?  
**Đáp án:** Không. Có thể annotation API thiếu, processor không match, class generated bị sai tên, hoặc source/generated source có lỗi Java độc lập.

## 15. Tài liệu chuẩn để đối chiếu

- [Java 17 javac command — annotation processing và các path](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Java 24 javac command — processor options](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
- [JSR 269 — Pluggable Annotation Processing API](https://jcp.org/en/jsr/detail?id=269)
- [Java Platform Module System — `provides` và `requires`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)
- [Gradle Java Plugin: dependencies for annotation processing](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Maven Compiler Plugin documentation](https://maven.apache.org/plugins/maven-compiler-plugin/)

**Kết luận:** Hãy tách **dependency mà source ứng dụng cần resolve** khỏi **dependency cần để compiler nạp processor**. Dùng `-cp`/application module path cho mã ứng dụng; chọn một trong `-processorpath` hoặc `--processor-module-path` cho processor; cấu hình discovery tường minh, đặc biệt từ JDK 23. Sau cùng, kiểm tra generated files, compiler rounds và runtime dependencies riêng biệt.
