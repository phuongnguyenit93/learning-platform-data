# Annotation processor và compiler arguments

Trong Java, **annotation processor** là chương trình chạy trong quá trình biên dịch để phân tích annotation, kiểm tra quy tắc hoặc sinh thêm source/resource. Các công cụ như trình tạo mapper, metadata, adapter hoặc mã boilerplate thường dùng cơ chế này.

Trong Java Platform Module System (JPMS), cần phân biệt rõ **module path của ứng dụng được biên dịch** và **đường dẫn dùng để tìm annotation processor**. Một JAR chứa processor không nhất thiết là dependency runtime của ứng dụng. Việc đặt nó đúng chỗ, khai báo cách phát hiện processor và truyền chính xác compiler arguments quyết định processor có chạy hay không.

Đây là chủ đề thuộc nhóm *Build tools*: tập trung vào `javac`, Maven, Gradle, cách đóng gói processor và chẩn đoán các lỗi build khi chuyển dự án sang named modules.

## 1. Annotation processor làm việc ở giai đoạn nào?

Một luồng biên dịch thông thường có thể hình dung:

    Java source có annotation
             |
             v
    javac phân tích source + module graph
             |
             v
    Annotation processing rounds
      - tìm các annotation hỗ trợ
      - đọc cấu trúc source bằng Element/TypeMirror
      - sinh thêm source hoặc resource bằng Filer
             |
             v
    javac biên dịch source ban đầu và source đã sinh
             |
             v
    .class trong output directory/JAR

API chuẩn thuộc module `java.compiler`, đặc biệt:

- `javax.annotation.processing.Processor`: hợp đồng của processor.
- `javax.annotation.processing.AbstractProcessor`: lớp nền tiện dụng.
- `javax.annotation.processing.RoundEnvironment`: thông tin của một vòng xử lý.
- `javax.annotation.processing.ProcessingEnvironment`: truy cập `Messager`, `Filer`, `Elements`, `Types`, `Options`.
- `javax.lang.model.element.Element` và `TypeElement`: biểu diễn cấu trúc Java ở compile time.
- `javax.lang.model.type.TypeMirror`: biểu diễn kiểu theo mô hình ngôn ngữ Java.

Annotation processing không phải runtime reflection và không cần chạy ứng dụng để sinh mã. Processor chạy trong môi trường biên dịch và có thể tạo tệp mới trước khi `javac` hoàn thành biên dịch.

## 2. Annotation khác processor

Annotation là metadata đặt trên source hoặc declaration:

    package com.example.app;

    import java.lang.annotation.ElementType;
    import java.lang.annotation.Retention;
    import java.lang.annotation.RetentionPolicy;
    import java.lang.annotation.Target;

    @Target(ElementType.TYPE)
    @Retention(RetentionPolicy.SOURCE)
    public @interface GenerateGreeting {
    }

Class dùng annotation:

    package com.example.app;

    @GenerateGreeting
    public class OrderService {
    }

`@Retention(SOURCE)` phù hợp khi annotation chỉ cần cho compile-time processing; annotation không bắt buộc được giữ lại ở runtime. Processor sẽ đọc mô hình mã nguồn và có thể sinh thêm class.

Một processor có thể hỗ trợ nhiều annotation. Hãy tách trách nhiệm:

- Annotation type khai báo dữ liệu hoặc dấu hiệu trong source.
- Processor đọc và xử lý annotation theo vòng biên dịch.
- Compiler quản lý tiến trình xử lý, output và việc biên dịch mã đã sinh.
- Build tool quyết định processor nằm ở đâu và truyền argument nào cho compiler.

Chỉ tạo annotation type không khiến bất kỳ mã nào tự động được sinh. Phải có processor được đăng ký và annotation processing được kích hoạt.

## 3. Viết một processor tối thiểu

Ví dụ dưới đây tạo class `com.example.app.generated.GreetingGenerated` khi gặp `@GenerateGreeting`.

    package com.example.processor;

    import java.io.IOException;
    import java.io.Writer;
    import java.util.Set;

    import javax.annotation.processing.AbstractProcessor;
    import javax.annotation.processing.RoundEnvironment;
    import javax.annotation.processing.SupportedAnnotationTypes;
    import javax.lang.model.SourceVersion;
    import javax.lang.model.element.Element;
    import javax.lang.model.element.TypeElement;
    import javax.tools.Diagnostic;
    import javax.tools.JavaFileObject;

    @SupportedAnnotationTypes("com.example.app.GenerateGreeting")
    public final class GreetingProcessor extends AbstractProcessor {
        @Override
        public SourceVersion getSupportedSourceVersion() {
            return SourceVersion.latestSupported();
        }

        @Override
        public boolean process(
                Set<? extends TypeElement> annotations,
                RoundEnvironment roundEnv) {

            if (roundEnv.processingOver() || annotations.isEmpty()) {
                return false;
            }

            for (TypeElement annotation : annotations) {
                for (Element ignored :
                        roundEnv.getElementsAnnotatedWith(annotation)) {
                    String name =
                            "com.example.app.generated.GreetingGenerated";

                    try {
                        JavaFileObject source =
                                processingEnv.getFiler()
                                        .createSourceFile(name);

                        try (Writer out = source.openWriter()) {
                            out.write(
                                "package com.example.app.generated;\n" +
                                "public final class GreetingGenerated {\n" +
                                "  public static String message() {\n" +
                                "    return \"Hello from processor\";\n" +
                                "  }\n" +
                                "}\n"
                            );
                        }
                    } catch (IOException e) {
                        processingEnv.getMessager().printMessage(
                                Diagnostic.Kind.ERROR, e.toString());
                    }
                    return true;
                }
            }
            return false;
        }
    }

Đây là ví dụ nhỏ nhất cho tình huống một class mang annotation. Processor thực tế cần xử lý **nhiều phần tử**, tránh tạo cùng một file nhiều lần và dùng originating elements phù hợp khi sinh tệp để hỗ trợ incremental builds.

Nếu gọi `Filer.createSourceFile(...)` nhiều lần cho cùng một tên file trong một lần compilation, compiler có thể báo lỗi `FilerException`. Processor không nên tạo lại file đã sinh ở vòng trước.

## 4. Annotation processing diễn ra theo nhiều rounds

Một lần compiler chạy processor có thể gồm nhiều vòng (*rounds*).

Trong vòng đầu, processor nhận các annotation có mặt trong source. Khi processor tạo thêm source, compiler phân tích source mới và có thể mở vòng tiếp theo. Một vòng cuối thông báo quá trình processing sắp hoàn tất bằng `roundEnv.processingOver()`.

Điều này quan trọng khi thiết kế generator:

- Không giả định tất cả class cần dùng đã xuất hiện ngay vòng đầu.
- Không tạo lại một class mang cùng tên ở nhiều vòng.
- Dùng `RoundEnvironment.getElementsAnnotatedWith(...)` để lấy phần tử hợp lệ.
- Phân biệt việc processor **claim** một annotation với việc chặn mọi processor khác: giá trị boolean của `process` cho biết các annotation được claim hay chưa.
- Báo lỗi bằng `Messager` thay vì chỉ in ra standard output.

Để quan sát rounds, dùng:

    javac -XprintRounds -XprintProcessorInfo ...

Các cờ `-X` chủ yếu hỗ trợ chẩn đoán compiler. Chúng không nên được hiểu là tùy chọn cấu hình logic nghiệp vụ của processor.

## 5. Hai đường tìm processor: processor path và processor module path

JPMS làm rõ hai cách để compiler tìm processor:

| Tùy chọn | Dùng cho | Cách đăng ký processor thường gặp |
|---|---|---|
| `--processor-path path` hoặc `-processorpath path` | Processor JAR được nạp theo classpath riêng của compiler | `META-INF/services/javax.annotation.processing.Processor` |
| `--processor-module-path path` | Processor được phân phối dưới dạng module | `provides javax.annotation.processing.Processor with ...` trong descriptor |
| `--module-path path` | Dependency/module của **source đang được biên dịch** | `requires` trong source module |
| `--class-path path` hoặc `-cp` | Dependency classpath của source đang được biên dịch | Các class/JAR thường, không tự là processor path được tách riêng khi đã cấu hình path processor |

**Điểm cốt lõi:** `--module-path` và `--processor-module-path` giải quyết hai mục đích khác nhau. Đặt processor JAR lên application module path không đồng nghĩa compiler chắc chắn sẽ chạy processor đó.

Tương tự, dependency dùng để biên dịch annotation type cần được tìm thấy bởi source compilation; còn JAR thực thi processor cần được compiler tìm qua processor path hoặc processor module path. Hai tập dependency có thể giao nhau nhưng không phải một.

## 6. Khai báo processor JAR dạng classpath

Nếu processor được đóng gói trong JAR truyền thống, có thể đăng ký qua service configuration file:

    META-INF/services/javax.annotation.processing.Processor

Nội dung:

    com.example.processor.GreetingProcessor

Trong trường hợp có nhiều processor, ghi tên đầy đủ của mỗi processor trên một dòng riêng.

Ví dụ biên dịch source với processor JAR riêng:

    javac --processor-path libs/greeting-processor.jar
          -processor com.example.processor.GreetingProcessor
          -s build/generated
          -d build/classes
          src/com/example/app/*.java

Các ký hiệu xuống dòng chỉ để trình bày; khi chạy shell, hãy đặt lệnh trên một dòng hoặc dùng ký tự nối dòng phù hợp.

`-processor` chỉ định cụ thể processor cần chạy, bỏ qua bước khám phá processor mặc định. Nếu đã có file `META-INF/services` hợp lệ và processor path được cấu hình, không nhất thiết phải ghi `-processor`; công cụ có thể phát hiện processor qua service configuration.

Với JAR classpath, processor thường cần **public constructor không tham số** để ServiceLoader của compiler khởi tạo.

## 7. Khai báo processor dưới dạng named module

Với named module `com.example.processor`, descriptor có thể là:

    module com.example.processor {
        requires java.compiler;

        provides javax.annotation.processing.Processor
            with com.example.processor.GreetingProcessor;
    }

Ý nghĩa:

- `requires java.compiler`: processor dùng API `javax.annotation.processing` và `javax.lang.model`.
- `provides ... with ...`: đăng ký implementation của service `Processor`.
- `GreetingProcessor` là lớp provider trong module; ví dụ kế thừa `AbstractProcessor`.

Nếu processor dùng thư viện bên thứ ba, cần cung cấp các dependency đó trong môi trường processor module path sao cho module graph của processor resolve được.

Ví dụ compiler nhận named-module processor:

    javac --module-path libs
          --processor-module-path processor-mods
          --module-source-path src
          -d out
          -m com.example.app

Trong lệnh này:

- `libs` chứa các module application cần để compile source.
- `processor-mods` chứa processor module và những module phụ thuộc cần thiết cho processor.
- `src` là source module layout.
- `-m com.example.app` chỉ định source module cần compile.

Đừng nhầm `provides javax.annotation.processing.Processor` trong **processor module** với `uses` hoặc `provides` của service nghiệp vụ mà ứng dụng sẽ sử dụng ở runtime. Processor là công cụ phục vụ **compile time**.

## 8. Các compiler arguments quan trọng

| Argument | Công dụng |
|---|---|
| `-processor p1,p2` | Chạy danh sách processor theo tên, thay cho discovery mặc định |
| `--processor-path path` | Chỉ định classpath dành cho processor |
| `--processor-module-path path` | Chỉ định module path dành cho processor |
| `-proc:none` | Tắt annotation processing |
| `-proc:only` | Chỉ chạy annotation processing, không làm bước compilation tiếp theo |
| `-proc:full` | Chạy annotation processing rồi tiếp tục compilation |
| `-Akey=value` | Truyền option dành riêng cho processor |
| `-s directory` | Thư mục output cho Java source do processor sinh |
| `-d directory` | Thư mục chứa class được compiler tạo |
| `-XprintRounds` | In thông tin các vòng annotation processing |
| `-XprintProcessorInfo` | In thông tin processor được gọi và annotation xử lý |
| `--module-path path` | Dependency modules cho source compilation |
| `--module-source-path path` | Tổ chức nhiều source modules |
| `--release version` | Compile theo API và class-file target của bản Java được chỉ định |

Các tùy chọn `-A` và `-processor` phục vụ processor; `--module-path` và `--release` phục vụ tổng thể quá trình biên dịch. Việc đặt đúng nhóm argument giúp tránh lỗi đưa một tùy chọn cho JVM chạy ứng dụng thay vì JVM/compiler thực thi annotation processing.

## 9. JDK 23 trở lên: annotation processing không còn bật ngầm

Một thay đổi quan trọng từ **JDK 23** là `javac` không còn tự động tìm và chạy processor trên classpath khi lệnh biên dịch không có cấu hình annotation processing tường minh.

Trước đó, một JAR vô tình chứa processor service file trên classpath có thể khiến processor chạy dù build không chủ động bật. Với JDK 23 trở lên, cần cấu hình rõ, ví dụ một trong các cách:

    javac -proc:full ...

    javac --processor-path processor-libs ...

    javac --processor-module-path processor-mods ...

    javac -processor com.example.processor.GreetingProcessor ...

`-proc:full` yêu cầu cả processing và compilation. Một số dòng JDK cũ chỉ hỗ trợ `-proc:none` hoặc `-proc:only`; hỗ trợ `-proc:full` đã được bổ sung trong các bản cập nhật nhất định.

Với build lâu dài, tốt nhất là **khai báo tường minh tập processor được tin cậy** và processor path/module path thay vì phụ thuộc vào cơ chế quét classpath ngầm. Điều này giúp build dễ tái lập hơn và tránh chạy processor ngoài dự kiến.

Khi nâng JDK mà các class generated đột nhiên biến mất, cần kiểm tra trước xem annotation processing còn được bật hay không, chứ không chỉ xem dependency của application có thay đổi không.

## 10. Truyền tham số -A vào processor

Processor có thể định nghĩa option riêng. Ví dụ, muốn cấu hình prefix cho class được sinh:

    javac --processor-path libs/greeting-processor.jar
          -Acodegen.prefix=Demo
          -d out
          src/com/example/app/*.java

Bên trong processor:

    String prefix = processingEnv
            .getOptions()
            .getOrDefault("codegen.prefix", "Default");

Nên khai báo danh sách option được hỗ trợ:

    @SupportedOptions("codegen.prefix")
    public final class GreetingProcessor
            extends AbstractProcessor {
        // ...
    }

Nếu annotation `@SupportedAnnotationTypes` và `@SupportedOptions` được sử dụng, các tên phải khớp với annotation hoặc option thực tế.

`-Acodegen.prefix=Demo` được `javac` chuyển tới processor. Nó không tương đương với:

    -Dcodegen.prefix=Demo

`-D` là system property của JVM nếu được truyền cho JVM phù hợp; `-A` là giao diện option của annotation processor.

## 11. Phân biệt argument cho javac và argument cho JVM biên dịch

Không phải mọi flag liên quan đến module đều truyền ở cùng tầng.

- `--module-path` của `javac` cho biết các module để compiler **biên dịch source**.
- `--processor-module-path` cho biết các module để compiler **tìm processor**.
- `-A...` cấu hình processor.
- `-J...` chuyển option cho **JVM đang chạy công cụ javac** khi gọi `javac` command-line launcher.

Sự khác biệt đặc biệt quan trọng nếu một processor đời cũ phụ thuộc vào API nội bộ của `jdk.compiler`, chẳng hạn package bắt đầu bằng `com.sun.tools.javac`. Những API đó không phải public compiler API ổn định.

Nếu công cụ thật sự phải truy cập package nội bộ từ unnamed module của compiler, một workaround có thể cần cờ JVM dạng:

    -J--add-exports=jdk.compiler/com.sun.tools.javac.tree=ALL-UNNAMED

Đây chỉ là ví dụ về **cấp quyền cho JVM thực thi javac**, không phải cách mở quyền tự động cho mọi module compile target. Với processor ở named module, module đích phải được xác định chính xác và có thể cần cấu hình khác.

Ưu tiên cập nhật processor để dùng `javax.annotation.processing` và `javax.lang.model` chuẩn; không nên dựa lâu dài vào API nội bộ `com.sun.tools.javac` vì các API này có thể thay đổi giữa các bản JDK.

## 12. Source được sinh thuộc module nào?

Nếu `javac` đang biên dịch named module `com.example.app`, source do processor tạo ra cho module đó sẽ được compiler xử lý như phần source compilation của module tương ứng theo cấu hình đầu ra.

Ví dụ processor sinh:

    package com.example.app.generated;

    public final class GreetingGenerated {
        public static String message() {
            return "Hello from processor";
        }
    }

Nếu class generated chỉ được sử dụng **bên trong** `com.example.app`, không cần export package `com.example.app.generated`.

Nếu module khác cần gọi trực tiếp API public của package generated, module `com.example.app` phải export package đó:

    module com.example.app {
        exports com.example.app.generated;
    }

Việc sinh class không tự động thêm `exports`, `requires` hoặc `opens` vào module descriptor.

Nếu processor sinh source phụ thuộc vào thư viện khác, `javac` cần nhìn thấy dependency đó ở module path/classpath của source compilation. Dependency của chính processor không mặc nhiên trở thành dependency đọc được bởi module ứng dụng.

## 13. Generated sources và file output

Các thư mục cần tách rõ:

    project/
      src/
      build/
        generated/
        classes/
      processor-libs/

- `src`: source do dự án quản lý.
- `build/generated`: source sinh ra bởi annotation processing.
- `build/classes`: file `.class` sau compilation.
- `processor-libs`: processor JAR và dependency processor.

Có thể dùng:

    -s build/generated
    -d build/classes

Thông thường không nên ghi đè file source do lập trình viên quản lý bằng kết quả sinh tự động. Build tool nên cấu hình generated directory nằm trong phạm vi build output, được dọn bằng clean task và không trùng với source root chính.

Nếu IDE không thấy class generated trong quá trình phát triển, hãy kiểm tra dự án có bật annotation processing không và IDE có đánh dấu generated source directory phù hợp hay không. Việc `javac` chạy thành công chưa chắc đồng nghĩa mọi IDE tự cập nhật ngay cấu hình nguồn sinh.

## 14. Cấu hình Maven Compiler Plugin

Trong dự án Maven, các processor thường được đưa vào cấu hình riêng của `maven-compiler-plugin`, thay vì chỉ khai báo như dependency runtime.

Ví dụ với processor JAR dạng classpath, dùng `annotationProcessorPaths`:

    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <configuration>
        <annotationProcessorPaths>
          <path>
            <groupId>com.example</groupId>
            <artifactId>greeting-processor</artifactId>
            <version>1.0.0</version>
          </path>
        </annotationProcessorPaths>
      </configuration>
    </plugin>

Ví dụ trên chỉ mô tả phần cấu hình liên quan; dự án vẫn cần có plugin version và cấu hình JDK phù hợp.

Khi cần lựa chọn processor tường minh, plugin có thể nhận thêm cấu hình tên processor (tùy phiên bản). Không nên giả định chỉ thêm dependency `greeting-processor` trong `dependencies` là đủ, nhất là khi dùng JDK 23 trở lên.

Với **modular annotation processors**, cách cấu hình phụ thuộc phiên bản Maven Compiler Plugin. Một số phiên bản mới hỗ trợ dependency type hoặc cơ chế cấu hình riêng cho processor trên module path; cần chọn đúng kiểu processor của artifact. Không tự đưa `--processor-module-path` và `--processor-path` vào cùng một cấu hình chỉ vì chưa rõ JAR thuộc loại nào.

Khi nâng Maven/JDK mà generated source mất đi, hãy kiểm tra log lệnh compiler thực tế và các tùy chọn processor được truyền, không chỉ kiểm tra POM có chứa artifact processor hay không.

## 15. Cấu hình Gradle

Với Gradle Java plugin, có dependency configuration chuyên dùng cho annotation processors:

    plugins {
        id 'java'
    }

    dependencies {
        implementation 'com.example:annotations-api:1.0.0'
        annotationProcessor 'com.example:greeting-processor:1.0.0'
    }

`implementation` cung cấp dependency cho source application. `annotationProcessor` cung cấp processor cho Java compilation task. Cả hai có thể cần thiết nếu source dùng annotation type từ một thư viện, còn processor là artifact riêng.

Trong test source set, có thể cần:

    dependencies {
        testImplementation 'com.example:annotations-api:1.0.0'
        testAnnotationProcessor 'com.example:greeting-processor:1.0.0'
    }

Nếu dự án dùng JPMS, có thể bật module path inference cho Java plugin:

    java {
        modularity.inferModulePath = true
    }

Tuy nhiên, module path inference của application không tự đảm bảo mọi processor được cấu hình theo processor module path. Hãy kiểm tra phiên bản Gradle, plugin và cách artifact processor được đóng gói.

Khi cần truyền `-A` cho task `JavaCompile` cụ thể:

    tasks.withType(JavaCompile).configureEach {
        options.compilerArgs += [
            '-Acodegen.prefix=Demo'
        ]
    }

Chỉ truyền argument được processor hỗ trợ. Đưa processor JAR vào `runtimeOnly` không phải cách thông thường để kích hoạt annotation processing trong compile task.

## 16. Unit test và testAnnotationProcessor

Nhiều dự án dùng annotation processing không chỉ ở `src/main/java` mà còn trong test fixtures và `src/test/java`. Vì compile main và compile test thường là các task khác nhau, processor configuration cũng có thể tách biệt.

Ví dụ:

- Main source dùng `annotationProcessor`.
- Test source dùng `testAnnotationProcessor`.
- Generated source của main và test thường nằm trong output directories khác nhau.
- Một processor có thể cần quyền truy cập module khác khi compile test.
- Test JVM không tự chạy annotation processor: processing thường diễn ra khi compile test sources.

Một test hữu ích có thể biên dịch một source mẫu có annotation rồi xác nhận class generated xuất hiện trong output. Đừng chỉ kiểm tra processor JAR đã được resolve làm dependency; cần chắc chắn processor thực sự được gọi.

## 17. Chẩn đoán processor không chạy

Khi generated class bị thiếu, hãy đi theo thứ tự:

1. **Xác nhận JDK:** đang dùng JDK nào? Với JDK 23 trở lên, annotation processing có được bật tường minh không?
2. **Xác nhận artifact:** processor JAR đã được tải và nằm trong processor path/module path không?
3. **Xác nhận kiểu đóng gói:** JAR dùng `META-INF/services` hay named module có `provides`?
4. **Xác nhận annotation type:** `@SupportedAnnotationTypes` có khớp tên đầy đủ của annotation không?
5. **Xác nhận source:** annotation có thực sự xuất hiện trên phần tử đang compile không?
6. **Xác nhận rounds:** dùng `-XprintRounds` và `-XprintProcessorInfo` để xem processor có được gọi không.
7. **Xác nhận output:** generated source được ghi vào thư mục nào, class generated có được compile và đóng gói không?
8. **Xác nhận lỗi Filer:** processor có sinh trùng file trong một compilation không?
9. **Xác nhận module graph:** dependency của processor và dependency của application đã nằm đúng path chưa?

Thông báo thường gặp:

| Triệu chứng | Hướng chẩn đoán |
|---|---|
| `Annotation processor ... not found` | Sai tên class trong `-processor`, JAR không nằm trên processor path/module path |
| Generated class không tồn tại | Processing không được bật, annotation không khớp hoặc processor không tạo file |
| `FilerException: Attempt to recreate a file` | Processor tạo trùng tên source/resource trong một lần compile |
| `NoClassDefFoundError` trong processor | Thiếu dependency của chính processor trên processor path/module path |
| `package ... is not visible` | Source module thiếu readability hoặc module chứa package chưa export |
| `IllegalAccessError` khi processor dùng API nội bộ | JDK strong encapsulation hoặc phiên bản processor không tương thích |
| IDE build được nhưng CI lỗi | JDK/toolchain/argument/processor path giữa IDE và CI không nhất quán |

Các lỗi nói trên thuộc những tầng khác nhau. Một generated class thiếu vì processor không chạy sẽ không được sửa bằng cách `--add-opens` ngẫu nhiên vào module source.

## 18. Những nhầm lẫn thường gặp

- **Tưởng annotation và processor là một.** Annotation khai báo metadata, còn processor là chương trình compile time đọc annotation đó.
- **Tưởng processor JAR trên runtime classpath là đủ.** Processor cần hiện diện trong môi trường compilation và được kích hoạt.
- **Tưởng `--module-path` cũng là `--processor-module-path`.** Một path dành cho module đang được biên dịch, một path dành cho processor module.
- **Tưởng `-proc:only` tạo đầy đủ class files như compile thông thường.** Nó chỉ thực hiện annotation processing, không tiếp tục bước compilation đầy đủ.
- **Tưởng generated source tự được export khỏi named module.** Package generated vẫn chịu module descriptor.
- **Tưởng JDK 23 trở lên vẫn quét processor trên classpath ngầm giống các bản cũ.** Cần cấu hình processing tường minh.
- **Tưởng `-Akey=value` là JVM system property.** `-A` cung cấp option cho annotation processor.
- **Tưởng `-J` và `--module-path` tác động cùng một tầng.** `-J` chuyển option đến JVM đang chạy compiler tool.
- **Tưởng Maven/Gradle runtime dependency là đủ để processor hoạt động.** Hãy dùng configuration hoặc plugin setup dành riêng cho processors.
- **Tưởng processor luôn là một named module.** Processor JAR classpath với `META-INF/services` vẫn là cơ chế hợp lệ.

## Ghi nhớ

- API annotation processing chuẩn thuộc module `java.compiler`.
- Processor có thể đăng ký qua `META-INF/services/javax.annotation.processing.Processor` hoặc `provides javax.annotation.processing.Processor with ...` trong named processor module.
- `--processor-path` và `--processor-module-path` dùng để tìm processor; `--module-path` dành cho modules của source compilation.
- `-processor` chọn processor tường minh; `-Akey=value` truyền cấu hình; `-s` và `-d` điều khiển output.
- Từ JDK 23, hãy bật hoặc cấu hình annotation processing tường minh; `-proc:full` là một cách yêu cầu processing rồi compile.
- Maven và Gradle nên tách processor dependencies khỏi dependency runtime của ứng dụng.
- Khi debug, quan sát vòng processing và output trước khi sửa module access flags.

Một build JPMS ổn định cần phân biệt ba lớp: **source module graph**, **processor discovery**, và **JVM/compiler options**. Khi đặt đúng processor path, service registration và compiler arguments, annotation processors có thể hoạt động nhất quán ngay cả khi ứng dụng được chia thành nhiều named modules.