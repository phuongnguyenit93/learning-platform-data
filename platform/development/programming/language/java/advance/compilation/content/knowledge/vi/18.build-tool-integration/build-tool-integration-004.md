# Tách phụ thuộc ứng dụng với phụ thuộc annotation processor trong Java build

## 1. Mục tiêu học tập

Trong một dự án Java, thư viện mà **ứng dụng cần để biên dịch hoặc chạy** không nhất thiết là thư viện mà **javac cần nạp để xử lý annotation trong lúc build**. Nếu đưa tất cả vào cùng một classpath, dự án có thể vẫn build được nhưng dễ phát sinh classpath phình to, processor chạy ngoài ý muốn, xung đột phiên bản, rủi ro bảo mật chuỗi build và lỗi runtime khó chẩn đoán.

Bài này giải thích cách tách rành mạch:

- **Annotation API**: những annotation type mà source ứng dụng import và gắn lên class, method hoặc field.
- **Annotation processor implementation**: mã chạy **trong quá trình biên dịch**, thường extends AbstractProcessor và sử dụng Filer, Messager, Elements, Types.
- **Phụ thuộc compile-time của ứng dụng**: class/JAR javac cần để type-check source ứng dụng.
- **Phụ thuộc runtime của ứng dụng**: class/JAR JVM thực sự cần để chạy chương trình đã biên dịch.
- **Phụ thuộc runtime của processor**: class/JAR mà chính annotation processor cần để chạy trong process biên dịch.
- **Generated code và các dependency của nó**: nguồn mới do processor tạo có thể được biên dịch cùng ứng dụng và có yêu cầu phụ thuộc riêng.

Ví dụ trọng tâm dùng **Java 17+** với ba phần tách biệt: annotation-api, processor, app. Ta tự chạy javac bằng các path riêng, xác minh code generation và stdout, sau đó ánh xạ sang Gradle và Maven. Cuối bài có sơ đồ quyết định, lỗi thực tế và bài tập.

**Điểm quan trọng nhất:** annotation processor là **build-time executable code**. Nó không nên tự động được đưa vào application runtime chỉ vì source ứng dụng sử dụng một annotation mà processor hiểu.

## 2. Một Java build có nhiều đường tìm class

Xét ba nơi javac/JVM phải tìm thành phần:

~~~text
                     BUILD TIME
+--------------------------------------------------+
| Source ứng dụng: Order.java, Main.java           |
|          |                                       |
|          +--> Compile classpath                  |
|          |       Annotation API                  |
|          |       Các API được source import      |
|          |                                       |
|          +--> Processor path                     |
|                  MetaProcessor implementation     |
|                  Dependencies của processor       |
|                           |                      |
|                           v                      |
|                    Filer tạo OrderMeta.java       |
|                           |                      |
|                           v                      |
|                javac tạo các .class               |
+--------------------------------------------------+
                           |
                           v
                     RUNTIME
                  Application JVM
                           |
                           v
                  Main.class + OrderMeta.class
                  + runtime dependencies cần thiết
~~~

Compile classpath và processor path có mục đích riêng:

| Đường/cấu hình | Ai sử dụng? | Chứa gì? |
| --- | --- | --- |
| -classpath hoặc -cp của javac | Compiler khi phân giải kiểu của source | Annotation API, thư viện mà code ứng dụng import, các API generated source cần |
| -processorpath của javac | Cơ chế nạp annotation processors | Processor implementation và những dependency processor cần để chạy |
| -d của javac | Compiler ghi output | Các class được biên dịch của ứng dụng và generated source |
| -s của javac | Filer/compiler ghi generated source | Source Java mới, ví dụ OrderMeta.java |
| -classpath hoặc -cp của java | JVM khi chạy ứng dụng | Application classes và những runtime dependency thực sự cần |
| --module-path / --processor-module-path | Cơ chế named modules khi cấu hình JPMS | Module artifacts và processor modules theo đúng ngữ cảnh |

**-d không phải -cp.** Chỉ định output directory không tự làm mọi input compiler hay runtime tìm được class ở nơi đó. Tương tự, chỉ đặt processor JAR vào compile classpath không phải một cách cấu hình rõ ràng để compiler nạp processor.

Có thể dùng cùng một JAR ở nhiều path khi thực sự cần; vấn đề là **phân tách vai trò**, không ép mỗi JAR chỉ được xuất hiện ở đúng một path trong mọi tình huống.

## 3. Vì sao annotation API và processor implementation nên tách?

Một annotation type đơn giản có thể chỉ là:

~~~java
package demo.ann;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateMeta {
}
~~~

Để source ứng dụng viết @GenerateMeta, javac phải nhìn thấy **demo.ann.GenerateMeta** trong compile classpath hoặc module path thích hợp. Nhưng khi chương trình chạy, annotation với SOURCE retention không được giữ trong class file, và nếu generated code không dùng annotation này thì runtime thường **không cần** annotation-api.

Ngược lại, một implementation processor như demo.proc.MetaProcessor chứa logic lập trình để phân tích elements, truy cập compiler utilities và tạo file. Đây là code được **javac chạy lúc biên dịch**. Chỉ một đoạn generated source đã hoàn tất không đồng nghĩa JVM cần tải MetaProcessor.

### Cấu trúc artifact khuyến nghị

~~~text
annotation-api/
    GenerateMeta.java  --> annotation-api.jar

processor/
    MetaProcessor.java --> processor.jar

app/
    Order.java
    Main.java          --> app classes / app.jar
                            + generated OrderMeta.class
~~~

Quan hệ cần có:

~~~text
app source  --------compile-time-------> annotation-api
javac       --------processor-path-----> processor
processor   --------build dependency---> processor utilities, nếu có
generated output ----runtime dependency-> chỉ những API mà output thật sự gọi
~~~

Việc tách artifact làm rõ phạm vi phụ thuộc. Với một processor lớn, implementation có thể mang thêm parser, codegen library hoặc utility riêng. Những JAR đó không nên đi vào package ứng dụng chỉ vì processor dùng chúng.

### Trường hợp cần annotation ở runtime

Không phải annotation API nào cũng chỉ có vai trò compile-time:

- **RetentionPolicy.SOURCE**: annotation bị bỏ khỏi .class; nếu không có tham chiếu runtime khác, annotation-api có thể chỉ cần khi compile.
- **RetentionPolicy.CLASS**: metadata có thể được giữ trong .class nhưng Reflection runtime thường không hiển thị theo cách runtime-retained annotations. Nhu cầu đóng gói annotation-api phụ thuộc các công cụ và cách class được sử dụng.
- **RetentionPolicy.RUNTIME**: annotation có thể được truy cập qua Reflection; nếu chương trình/framework cần load type annotation lúc chạy, annotation-api có thể là **runtime dependency** thật.

Quyết định dùng compileOnly, provided hay implementation phải dựa trên **nhu cầu runtime thực tế**, không chỉ vì artifact chứa annotation.

## 4. Processor path là một loại execution dependency

Trong javac, processor có thể được lựa chọn tường minh bằng:

~~~sh
-processorpath build/processor -processor demo.proc.MetaProcessor
~~~

Điều này bảo javac nơi nạp implementation và processor class nào sẽ được chạy. Nếu processor cần thêm JAR trợ giúp ở runtime của nó, các dependency đó phải có mặt theo cơ chế nạp processor phù hợp.

**Processor không chỉ là metadata**: mã Java của processor thực thi trong quá trình build. Nếu plugin không đáng tin, nó có thể chạy với quyền của build process, truy cập file và tạo tác dụng phụ. Vì vậy tách processor path còn giúp rà soát **build supply chain** và kiểm soát phiên bản.

Một processor thường extends AbstractProcessor, nhận ProcessingEnvironment trong init rồi tạo file qua Filer khi process được gọi. Các lớp API này thuộc module java.compiler của JDK, không đòi hỏi một JAR bên ngoài riêng chỉ vì namespace bắt đầu bằng javax.

### Phân biệt discovery và explicit selection

Có hai cách chọn processor phổ biến:

1. **Chỉ định bằng -processor**: liệt kê qualified class name, có tính xác định và không cần service descriptor.
2. **Service discovery**: trong processor JAR có META-INF/services/javax.annotation.processing.Processor ghi tên implementation, và compiler/toolchain được cấu hình cho phép tìm processor.

Không mặc định rằng chỉ cần bỏ processor JAR vào classpath là mọi JDK luôn tự chạy nó. Từ Java 23, mặc định của javac về annotation processing được siết chặt: nên cấu hình processor/processor path hoặc chế độ xử lý **tường minh**. Các build tool cũng có chính sách riêng. Ví dụ xuyên suốt bài dùng -processor để hành vi không phụ thuộc discovery.

## 5. Dự án Java 17 đầy đủ với ba phần độc lập

Tạo thư mục **annotation-deps-lab** với cấu trúc:

~~~text
annotation-deps-lab/
├── src/
│   ├── annotation-api/
│   │   └── demo/ann/GenerateMeta.java
│   ├── processor/
│   │   └── demo/proc/MetaProcessor.java
│   └── app/
│       └── demo/app/
│           ├── Order.java
│           └── Main.java
└── build/
    ├── api/             # Annotation .class
    ├── processor/       # Processor .class
    ├── generated/       # Generated .java
    └── app/             # Application và generated .class
~~~

Mỗi file Java bên dưới có nội dung đầy đủ. Bài cố ý chọn một processor có thể đọc annotation bằng **TypeElement** mà không import annotation class. Nhờ đó processor implementation có thể biên dịch độc lập với annotation-api trong ví dụ, giúp ta nhìn rõ sự tách biệt các path. Trong một processor khác có dùng trực tiếp GenerateMeta.class hoặc annotation values thông qua loại annotation cụ thể, implementation **có thể cần annotation-api trên processor path của chính nó**; đây là chuyện bình thường, không phá vỡ mục tiêu tách vai trò.

### 5.1. src/annotation-api/demo/ann/GenerateMeta.java

~~~java
package demo.ann;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateMeta {}
~~~

@Target(TYPE) cho phép gắn annotation vào các khai báo kiểu. Processor mẫu chỉ chấp nhận **class**, vì nó chủ động kiểm tra ElementKind.CLASS và báo diagnostic nếu mục tiêu khác.

### 5.2. src/processor/demo/proc/MetaProcessor.java

~~~java
package demo.proc;

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

@SupportedAnnotationTypes("demo.ann.GenerateMeta")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class MetaProcessor extends AbstractProcessor {
    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (round.processingOver()) {
            return true;
        }

        for (TypeElement annotationType : annotations) {
            for (Element element :
                    round.getElementsAnnotatedWith(annotationType)) {
                if (element.getKind() != ElementKind.CLASS) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "Only classes supported", element);
                    continue;
                }

                TypeElement type = (TypeElement) element;
                String pkg = processingEnv.getElementUtils()
                        .getPackageOf(type).getQualifiedName().toString();
                String simple = type.getSimpleName() + "Meta";
                String qualified =
                        pkg.isEmpty() ? simple : pkg + "." + simple;

                try {
                    JavaFileObject file = processingEnv.getFiler()
                            .createSourceFile(qualified, type);
                    try (Writer writer = file.openWriter()) {
                        if (!pkg.isEmpty()) {
                            writer.write("package " + pkg + ";\n");
                        }
                        writer.write("public final class "
                                + simple + " {\n");
                        writer.write("  private " + simple + "() {}\n");
                        writer.write(
                                "  public static String text() { return "
                                + "\"Meta for " + type.getSimpleName()
                                + "\"; }\n");
                        writer.write("}\n");
                    }
                } catch (IOException ex) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "Generation failed: " + ex.getMessage(),
                            element);
                }
            }
        }
        return true;
    }
}
~~~

**Các điểm quan trọng trong processor:**

1. SupportedAnnotationTypes công bố qualified name của annotation dưới dạng chuỗi. Processor không cần import demo.ann.GenerateMeta trong mã nguồn của chính nó.
2. SupportedSourceVersion khai báo mức Java 17 được hỗ trợ.
3. processingEnv là field do AbstractProcessor cung cấp sau khi compiler gọi init.
4. RoundEnvironment và Set<TypeElement> cung cấp annotations của round; process có thể được gọi nhiều lần.
5. getElementsAnnotatedWith(TypeElement) tìm elements mang annotation trong round.
6. Elements.getPackageOf giúp tìm đúng package của class nguồn.
7. Filer.createSourceFile tạo một source file mới theo qualified name, ở đây là OrderMeta.
8. Writer được đóng bởi try-with-resources. Nội dung generated source sẽ được compiler đưa vào round tiếp theo khi thích hợp.
9. Messager báo ERROR nếu target không hợp lệ hoặc không tạo được output.
10. return true **claim annotation**, không phải một Boolean báo toàn bộ build chắc chắn thành công.

Bản demo được thiết kế cho top-level class đơn giản. Trong processor sản xuất cần tính đến class lồng nhau, tên generated trùng, nhiều targets, annotation values và luật escape source. Đặc biệt không sinh cùng qualified output hai lần trong cùng invocation; Filer có thể ném FilerException nếu gặp va chạm.

### 5.3. src/app/demo/app/Order.java

~~~java
package demo.app;

import demo.ann.GenerateMeta;

@GenerateMeta
public final class Order {}
~~~

Order.java **phải** nhìn thấy annotation API khi compile, vì nó trực tiếp import và sử dụng GenerateMeta.

### 5.4. src/app/demo/app/Main.java

~~~java
package demo.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println(OrderMeta.text());
    }
}
~~~

Main.java cố ý tham chiếu **OrderMeta**, một class chưa có trong source ban đầu. Processor sinh OrderMeta.java trong lúc javac thực hiện annotation processing, rồi generated source được compile thành OrderMeta.class trước khi ứng dụng chạy.

### Vì sao processor không được import vào Main?

Main không dùng MetaProcessor và không cần biết implementation processor. Nó chỉ gọi method của **generated class**. Đây chính là ranh giới giữa **build-time code generator** và **application runtime**.

## 6. Biên dịch ba giai đoạn bằng javac

Mở terminal ở gốc annotation-deps-lab, xác nhận dùng JDK 17+:

~~~sh
javac -version
java -version
~~~

Tạo các thư mục output. Chỉ dùng một biến thể phù hợp shell.

~~~bash
# Bash trên macOS/Linux
mkdir -p build/api build/processor build/generated build/app
~~~

~~~powershell
# PowerShell trên Windows
New-Item -ItemType Directory -Path build/api,build/processor,build/generated,build/app -Force | Out-Null
~~~

### 6.1. Biên dịch annotation API

~~~sh
javac --release 17 -d build/api src/annotation-api/demo/ann/GenerateMeta.java
~~~

Đầu ra:

~~~text
build/api/demo/ann/GenerateMeta.class
~~~

Chỉ có annotation class trong output API. Đây là compile dependency tối thiểu mà source Order.java cần để được type-check.

### 6.2. Biên dịch implementation processor

~~~sh
javac --release 17 -d build/processor src/processor/demo/proc/MetaProcessor.java
~~~

Đầu ra:

~~~text
build/processor/demo/proc/MetaProcessor.class
~~~

Lệnh này **không cần -cp build/api** vì processor mẫu nhận TypeElement từ tham số annotations và dùng tên annotation ở SupportedAnnotationTypes, chứ không tham chiếu trực tiếp GenerateMeta.class.

Trong processor thực tế nếu có import demo.ann.GenerateMeta hoặc sử dụng các dependency khác, lệnh biên dịch processor phải cung cấp chúng trên compile classpath phù hợp; và giai đoạn nạp processor cũng phải có những runtime dependencies đó trên processor path.

### 6.3. Compile ứng dụng và kích hoạt processor

~~~sh
javac --release 17 -cp build/api -processorpath build/processor -processor demo.proc.MetaProcessor -s build/generated -d build/app src/app/demo/app/Order.java src/app/demo/app/Main.java
~~~

Ý nghĩa từng flag:

| Flag | Nhóm vai trò | Giải thích |
| --- | --- | --- |
| --release 17 | Compiler target | Kiểm tra API/ngôn ngữ và sinh bytecode phù hợp Java 17 |
| -cp build/api | Application compile classpath | Source Order.java nhìn thấy demo.ann.GenerateMeta |
| -processorpath build/processor | Build-time processor classpath | Compiler nạp demo.proc.MetaProcessor |
| -processor demo.proc.MetaProcessor | Chọn processor | Không phụ thuộc discovery mặc định |
| -s build/generated | Generated source output | OrderMeta.java do Filer tạo |
| -d build/app | Class output | Order.class, Main.class, OrderMeta.class |
| Order.java và Main.java | Source input | Những source ứng dụng ban đầu |

**Kết quả cần kiểm tra:**

~~~text
build/generated/demo/app/OrderMeta.java
build/app/demo/app/Order.class
build/app/demo/app/Main.class
build/app/demo/app/OrderMeta.class
~~~

Generated source dự kiến:

~~~java
package demo.app;
public final class OrderMeta {
  private OrderMeta() {}
  public static String text() { return "Meta for Order"; }
}
~~~

Trong ví dụ này, **không** có file demo/proc/MetaProcessor.class trong build/app. Nó vẫn nằm trong build/processor. Đó là bằng chứng rằng output ứng dụng được tách khỏi implementation processor.

**Cảnh báo về chạy lại:** nếu trước đó bạn đã tạo generated source từ build khác, nên dùng output riêng sạch hoặc dọn đúng bốn thư mục build của bài trước khi làm lại. Đừng tự tạo OrderMeta.java trong src/app vì có thể gây va chạm với Filer.

### 6.4. Chạy ứng dụng

~~~sh
java -cp build/app demo.app.Main
~~~

**Stdout chính xác của ví dụ (đã kiểm chứng với javac --release 17):**

~~~text
Meta for Order
~~~

Runtime chỉ cần build/app. Trong bản demo này, không cần đặt build/processor hay build/api vào runtime classpath: generated code không gọi MetaProcessor và annotation có SOURCE retention.

Nếu bạn thay annotation thành một loại được code runtime đọc bằng Reflection, hoặc generated source gọi một runtime library khác, **phải cung cấp dependency runtime cần thiết**. Đừng tổng quát hóa cấu hình tối giản của demo thành luật cho mọi annotation processor.

## 7. Ba câu hỏi xác định dependency cần đặt ở đâu

Với một artifact bất kỳ, hãy hỏi:

**Câu 1: Source ứng dụng có import/tham chiếu type trong artifact này không?** Nếu có, artifact đó cần nằm trên **application compile classpath** (hoặc module path) tương ứng. Ví dụ: Order.java import GenerateMeta nên cần annotation API.

**Câu 2: Processor implementation có nạp/gọi class trong artifact này khi build không?** Nếu có, artifact đó cần ở **processor execution path**, và trong compile classpath của processor khi xây chính processor. Ví dụ: nếu MetaProcessor dùng một thư viện code generation, thư viện đó phục vụ processor chứ không phải tự động trở thành dependency runtime của ứng dụng.

**Câu 3: Bytecode ứng dụng hoặc generated code có cần artifact này khi chạy không?** Nếu có, artifact phải xuất hiện trên **application runtime classpath** hoặc module path. Ví dụ: nếu OrderMeta.text() gọi một helper thuộc com.example.runtime.Helper, helper đó là runtime dependency thật.

Đây là ba phép kiểm tra riêng. **Cùng một artifact có thể trả có cho nhiều câu hỏi**. Mục tiêu là đặt nó đúng những nơi thực sự cần, tránh lẫn phạm vi.

### Bảng quyết định ví dụ

| Artifact | Compile app | Execute processor | Run app |
| --- | --- | --- | --- |
| annotation-api.jar với SOURCE annotation của demo | Có | Không cần ở demo | Không cần |
| processor.jar của demo | Không | Có | Không |
| processor-util.jar chỉ do processor dùng | Không | Có nếu processor phụ thuộc | Không |
| runtime-helper.jar do generated class gọi | Có nếu generated source import nó | Không, trừ khi processor cũng dùng | Có |
| logging library do cả app và processor gọi | Có với app nếu source import | Có với processor | Có với app nếu bytecode gọi |
| JDK java.compiler API | JDK cung cấp khi build processor | JDK cung cấp | Không cần processor classes lúc app chạy |

Không nên nhầm giữa **artifact dependency của processor project** và **dependency do app cần tại runtime**. Một build tool có thể tải cả hai trong quá trình build nhưng chúng không thuộc cùng classloader hoặc classpath.

## 8. Trường hợp processor cần annotation-api để chạy

Bản demo chọn TypeElement nên implementation không tham chiếu GenerateMeta.class trực tiếp. Nhưng một processor phổ biến có thể viết:

~~~java
for (Element element :
        round.getElementsAnnotatedWith(GenerateMeta.class)) {
    // Đọc hoặc xử lý annotation.
}
~~~

Đây chỉ là snippet **không độc lập**, giả sử processor đã import GenerateMeta và có biến round phù hợp. Khi đó:

1. Processor project cần **compile dependency** vào annotation-api.
2. Compiler khi nạp processor cần tìm được GenerateMeta.class trong **processor execution dependencies**.
3. Source app cũng cần annotation-api trên **application compile path**.
4. Runtime app **chỉ** cần annotation-api nếu ứng dụng thực sự sử dụng nó ở runtime.

Có thể cùng annotation-api.jar xuất hiện trên hai classpaths khác nhau mà vẫn là thiết kế tách biệt đúng. Đừng để thiếu class lúc processor load chỉ vì đã có annotation-api ở classpath của ứng dụng: classloader/path của processor có thể được cô lập.

Ngược lại, đừng đặt processor.jar vào compile classpath app chỉ để khắc phục một lỗi thiếu annotation-api. Hãy tạo artifact annotation-api riêng và chỉ đưa đúng API vào compile path.

## 9. Gradle Java: compileOnly, implementation và annotationProcessor

Với Gradle Java plugin, những configuration thường gặp:

| Configuration | Ý nghĩa chính | Có thuộc runtime app mặc định không? |
| --- | --- | --- |
| implementation | Dependency code ứng dụng dùng và có thể cần lúc chạy | Có trong runtime dependency graph |
| api | API dependency được công khai cho consumers khi dùng java-library plugin | Có, và còn ảnh hưởng compile classpath downstream |
| compileOnly | Chỉ cần để compile source hiện tại | Không |
| runtimeOnly | Không cần compile, nhưng cần khi chạy | Có |
| annotationProcessor | Dependency để thực thi javac annotation processor | Không tự động trở thành implementation/runtime |
| testImplementation | Dependency cho compile/run tests | Trong test scope, không phải runtime chính của app |
| testAnnotationProcessor | Processor dùng khi compile test sources | Không tự động đi vào runtime chính của app |

**Cấu hình lý tưởng cho app của demo:**

~~~groovy
dependencies {
    compileOnly project(':annotation-api')
    annotationProcessor project(':processor')
}
~~~

Tại đây annotation-api phục vụ compile code, processor phục vụ chạy generator. Không phải cứ có annotationProcessor project(':processor') thì app source tự import được GenerateMeta; nó phải nhìn thấy annotation-api trong compile scope riêng.

### Cấu trúc multi-project Gradle

Chuyển source demo sang bố cục Java plugin thông thường:

~~~text
annotation-deps-gradle/
├── settings.gradle
├── build.gradle
├── annotation-api/
│   └── src/main/java/demo/ann/GenerateMeta.java
├── processor/
│   └── src/main/java/demo/proc/MetaProcessor.java
└── app/
    └── src/main/java/demo/app/
        ├── Order.java
        └── Main.java
~~~

**settings.gradle:**

~~~groovy
rootProject.name = 'annotation-deps-gradle'
include 'annotation-api', 'processor', 'app'
~~~

**build.gradle ở root:**

~~~groovy
subprojects {
    apply plugin: 'java'

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(17)
        }
    }
}

project(':app') {
    dependencies {
        compileOnly project(':annotation-api')
        annotationProcessor project(':processor')
    }

    tasks.named('compileJava', JavaCompile) {
        options.compilerArgs += [
            '-processor', 'demo.proc.MetaProcessor'
        ]
    }
}
~~~

Đây là một cấu hình Gradle **Groovy DSL cho các source Java ở trên**. Nó chọn processor tường minh; vì vậy không bắt buộc thêm service file vào processor project. Toolchain yêu cầu Gradle/JDK phù hợp, và môi trường cần có Gradle (hoặc wrapper) để chạy. Code processor trong ví dụ **không** dùng trực tiếp annotation class nên project processor không cần khai báo dependency vào annotation-api; nếu đổi cách cài processor, cập nhật dependency tương ứng.

Với thiết lập đúng, chạy từ root dự án:

~~~sh
gradle :app:classes
gradle :app:run
~~~

**Lưu ý:** lệnh :app:run chỉ có khi bạn cấu hình thêm plugin **application** và mainClass cho app; project Java plugin tối giản ở trên **chưa định nghĩa run task**. Để tránh phụ thuộc cấu hình chưa có, hãy dùng lệnh build thực sự áp dụng được:

~~~sh
gradle :app:classes
~~~

Sau đó có thể chạy ứng dụng từ các class outputs của Gradle theo đường dẫn do version/toolchain sử dụng, hoặc thêm cấu hình application plugin như dưới đây.

### Bổ sung application plugin để chạy bằng Gradle

Thay phần project(':app') ở root bằng dạng tương đương sau:

~~~groovy
project(':app') {
    apply plugin: 'application'

    application {
        mainClass = 'demo.app.Main'
    }

    dependencies {
        compileOnly project(':annotation-api')
        annotationProcessor project(':processor')
    }

    tasks.named('compileJava', JavaCompile) {
        options.compilerArgs += [
            '-processor', 'demo.proc.MetaProcessor'
        ]
    }
}
~~~

Khi đã bổ sung application plugin, mới chạy:

~~~sh
gradle :app:run
~~~

**Stdout chương trình chính** vẫn là:

~~~text
Meta for Order
~~~

Gradle sẽ in thêm task logs, trạng thái build hoặc thông tin môi trường, nên toàn bộ output terminal **không chỉ gồm một dòng** trên. Đừng coi đây là output chính xác của toàn bộ Gradle CLI.

### Nếu processor có dependency riêng trong Gradle

Giả sử MetaProcessor cần một thư viện xử lý mã tại build time:

~~~groovy
project(':processor') {
    dependencies {
        implementation 'com.example:processor-util:1.0.0'
    }
}
~~~

Đoạn trên là **minh họa cấu hình**, không phải dependency có thật đã được tạo trong project demo. Khi app khai báo annotationProcessor project(':processor'), những runtime dependencies cần thiết của processor project thường được đưa vào processor configuration thông qua resolution graph phù hợp. Chúng **không** tự động xuất hiện trong app implementation chỉ vì app dùng processor.

Nếu generated code lại gọi processor-util, phải xem nó là dependency runtime của app và khai báo riêng theo hợp đồng thực tế. Processor implementation dependencies và generated-code runtime dependencies không đồng nhất.

### Vì sao không khai báo processor ở implementation?

~~~groovy
dependencies {
    implementation project(':processor')  // Không phù hợp cho demo
}
~~~

Dòng này đưa processor project vào dependency graph của ứng dụng nhưng **không biểu diễn rõ mục đích javac phải chạy processor**. Nó có thể khiến runtime app mang theo implementation và thư viện phụ, tăng kích thước đóng gói hoặc gây xung đột.

Sửa bằng annotationProcessor cho processor, và compileOnly/implementation cho annotation API tùy retention/runtime cần thiết.

## 10. Maven: dependency thường và annotationProcessorPaths

Với Maven, app dependencies được khai báo trong dependencies, còn annotation processors có thể được cấu hình riêng trong **maven-compiler-plugin**.

Giả sử một Maven reactor chứa ba module tương ứng và bạn đã có các artifact:

~~~text
demo:annotation-api:1.0.0
demo:processor:1.0.0
demo:app:1.0.0
~~~

Đây là tọa độ **minh họa cho dự án của bạn**, không phải artifact được hứa đã có trên Maven Central.

Trong **pom.xml của app**, ví dụ với Maven Compiler Plugin 3.x:

~~~xml
<dependencies>
    <dependency>
        <groupId>demo</groupId>
        <artifactId>annotation-api</artifactId>
        <version>1.0.0</version>
        <scope>provided</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
            <configuration>
                <release>17</release>
                <annotationProcessorPaths>
                    <path>
                        <groupId>demo</groupId>
                        <artifactId>processor</artifactId>
                        <version>1.0.0</version>
                    </path>
                </annotationProcessorPaths>
                <annotationProcessors>
                    <annotationProcessor>
                        demo.proc.MetaProcessor
                    </annotationProcessor>
                </annotationProcessors>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

**Đây là phần cấu hình dành cho một POM đã có project coordinates và Maven reactor tương ứng**, không phải một pom.xml độc lập hoàn chỉnh. Mục tiêu là cho thấy chỗ khai báo **annotation-api** và **processor** khác nhau. Plugin version 3.14.1 là một phiên bản ví dụ của nhánh 3.x, không phải khẳng định đó là bản mới nhất tại mọi thời điểm. Maven Compiler Plugin 4.x/Maven 4 có các cách khai báo processor dependency mới; cần tham khảo tài liệu của đúng phiên bản đang dùng khi nâng cấp.

Trong demo, annotation API có SOURCE retention, không được code runtime dùng nên scope provided giúp app compile nhưng không yêu cầu dependency đó trong runtime graph thông thường. Nếu runtime thực sự cần annotation API, hãy dùng scope phù hợp với nhu cầu runtime thay vì provided.

**annotationProcessorPaths** là processor execution path được compiler plugin xây. Nếu processor có runtime dependencies, những dependencies đó cũng cần được resolve đầy đủ trên processor path. Với một processor có import annotation-api trực tiếp, có thể cần thêm annotation-api vào processor artifact dependency graph hoặc processor path, tùy cách xuất bản.

### Quy tắc lựa chọn processor trong Maven

- annotationProcessorPaths cho biết processor artifact nào được dùng khi compile.
- annotationProcessors cho phép chọn class processor tường minh, tương tự -processor của javac.
- Nếu dùng service discovery, processor JAR phải có descriptor hợp lệ và phiên bản plugin/JDK phải cấu hình để discovery được phép.
- Không nên chỉ thêm processor vào dependencies scope compile rồi mong nó được nạp/run như một annotation processor ở mọi cấu hình.

### Cẩn thận với scope của Maven

| Scope Maven | Khái niệm gần nhất | Ghi chú |
| --- | --- | --- |
| compile | Dependency compile và thường runtime | Không tương đương annotation processor execution path |
| provided | Có lúc compile/test, thường không được đưa vào runtime thông thường | Phù hợp khi runtime/container cung cấp hoặc dependency chỉ phục vụ compile |
| runtime | Không cần khi compile source, cần khi chạy | Generated code hoặc service runtime có thể cần |
| test | Chỉ cho code/test lifecycle | Processor cho tests có thể cần cấu hình riêng |

Maven provided **không phải bản sao tuyệt đối** của Gradle compileOnly về tất cả quy tắc transitivity và packaging. Hãy kiểm tra dependency tree, artifact packaging và việc chạy thật thay vì dựa vào việc tên scope “gần giống”.

## 11. Annotation processor và generated code có thể cần hai bộ dependency khác nhau

Ví dụ processor dùng **JavaPoet** hoặc một thư viện template để tạo Java source. Library đó phục vụ **generator**. Một generated class chỉ gồm các lời gọi Java SDK không cần JavaPoet ở runtime.

Ngược lại, generator có thể phát ra code:

~~~java
package demo.app;

public final class OrderMeta {
    public static String text() {
        return com.example.runtime.Texts.format("Order");
    }
}
~~~

Đây là **đoạn nguồn generated minh họa**, không thuộc demo runnable đã kiểm thử. Vì OrderMeta.class tham chiếu com.example.runtime.Texts, runtime app phải có thư viện chứa Texts; compile generated source cũng cần nhìn thấy nó. Việc đưa thư viện này **chỉ** vào annotationProcessor configuration sẽ không đủ.

Cách tư duy:

~~~text
Generator dùng helper A để tạo source
  -> A cần ở processor execution path.

Source tạo ra gọi helper B khi chạy
  -> B cần ở application compile + runtime dependency path.

Annotation type C chỉ dùng khi compile
  -> C cần ở application compile path; runtime tùy retention/cách dùng.
~~~

Những tình huống đặc biệt như generated class dùng annotation có RUNTIME retention hoặc interface từ annotation processor runtime library cần được đánh giá riêng. Không có luật “tất cả thư viện liên quan annotation đều compileOnly”.

## 12. Rủi ro khi trộn đường nạp processor với app

### Classpath pollution

Nếu đưa processor.jar và toàn bộ dependencies vào implementation của app, classpath chứa nhiều class không cần khi chạy. Điều này có thể làm package/JAR lớn, tăng nguy cơ va chạm phiên bản thư viện, hoặc tạo sự phụ thuộc vô tình vào API chỉ dành cho build.

### Processor bị kích hoạt ngoài ý muốn

Một processor JAR có service descriptor có thể bị compiler phát hiện trong một số cấu hình, khiến build chạy processor khi tác giả không dự kiến. Cấu hình processor path riêng và explicit selection giúp hành vi dễ kiểm chứng hơn.

### Conflict giữa versions

Ứng dụng dùng phiên bản X của một thư viện, trong khi processor cần phiên bản Y cho code generation. Nếu dồn cả hai vào một classpath, conflict có thể xuất hiện ngay trong build hoặc trong package runtime. Tách configurations cho phép quản lý đồ thị dependency riêng và kiểm thử độc lập.

### Build security

Annotation processor chạy code khi compilation diễn ra. Một dependency processor bị xâm nhập không phải “chỉ là annotation”; nó có thể thực thi logic trong build process. Cần pin/kiểm soát version, nguồn artifact và plugin trust, review thay đổi processor, và tránh chạy processor không rõ xuất xứ.

### Reproducibility

Khi compiler chọn processor tự động từ classpath không kiểm soát, một dependency thêm vào có thể thay đổi generated output. Nên cấu hình processor path, version và selector rõ ràng; giữ source generated deterministic và tránh timestamp/ngẫu nhiên không cần thiết.

## 13. Nếu build dùng Java modules (JPMS)

Ví dụ chạy được ở phần 5–6 sử dụng classpath để cô lập từng vai trò. Khi chuyển sang named modules, bạn cần phân biệt thêm:

- **Application module path**: modules mà app source đọc để compile hoặc app runtime phân giải.
- **Processor module path**: named modules chứa processors và dependency của chúng khi dùng cơ chế module-aware processor loading.
- **Processor path thông thường**: processor được nạp theo classpath-based mechanism, thường bằng -processorpath.
- **module-info.java**: requires/exports/opens của ứng dụng hoặc processor module tùy thiết kế.

Không nhầm **--processor-module-path** với **--module-path** của ứng dụng. Đó là hai ngữ cảnh phân giải khác nhau. Một processor có thể được đóng gói như một named module cung cấp service javax.annotation.processing.Processor qua provides, nhưng đó là phương án packaging riêng cần xem đúng tài liệu JDK.

Một annotation API được app dùng qua JPMS cũng phải có module descriptor hoặc automatic module name phù hợp và quan hệ requires ở app. Chỉ chuyển -cp sang --module-path không tự giải quyết dependency graph, split packages hay service discovery.

**Tóm lại:** JPMS bổ sung ràng buộc modules nhưng không thay nguyên tắc phải phân biệt **compiler/plugin execution dependencies** với **runtime dependencies của ứng dụng**.

## 14. Những sai lầm cấu hình thường gặp và cách sửa

| Hiện tượng | Lỗi cấu hình có thể | Kiểm tra/sửa |
| --- | --- | --- |
| cannot find symbol GenerateMeta | Annotation API không có trên application compile classpath | Thêm annotation-api vào compileOnly/compile scope phù hợp |
| Annotation processor not found | Processor implementation không có trên processor path, tên class sai | Kiểm tra -processorpath, -processor và artifact processor |
| NoClassDefFoundError khi nạp processor | Processor cần library hoặc annotation type nhưng processor path thiếu | Bổ sung dependency của processor vào processor execution path |
| cannot find symbol OrderMeta | Processor không chạy hoặc không sinh file | Kiểm tra processor selection, -s, diagnostic và generated source |
| FilerException: Attempt to recreate a file | Output generated trùng hoặc stale build pipeline | Kiểm tra naming, rounds, input sources và output sạch |
| Generated source compile lỗi thiếu type | Generated code gọi API chưa có trên compile classpath app | Thêm đúng thư viện API/runtime của generated code |
| App build pass nhưng runtime NoClassDefFoundError | Runtime classpath thiếu dependency do app hoặc generated bytecode gọi | Kiểm tra runtime dependency graph và packaging |
| Processor ở app jar | Nhầm implementation thay vì annotationProcessor/provided | Chuyển sang processor-specific configuration |
| Processor không tự chạy trên JDK mới | Phụ thuộc discovery mặc định | Chọn processor và processor path explicit |
| Test classes không có generated type | Chưa cấu hình test annotation processing riêng hoặc output riêng | Kiểm tra testAnnotationProcessor và test source set |
| Gradle :app:run không tồn tại | Chỉ dùng Java plugin, thiếu application plugin | Cấu hình application plugin/mainClass hoặc chạy java trực tiếp |
| Maven processor có nhưng app vẫn thiếu annotation type | annotationProcessorPaths không tự đưa API vào application source compile path | Khai báo annotation-api trong dependencies đúng scope |

### Chẩn đoán theo ranh giới

Bắt đầu với ba câu hỏi:

1. Compiler có nhìn thấy **annotation type** trong source?
2. Compiler có nạp/khởi tạo được **processor implementation** với đầy đủ runtime dependencies của processor?
3. Generated source/class có biên dịch và chạy được với **application dependencies**?

Nếu lỗi nằm ở câu 1, kiểm tra app compile path. Nếu lỗi ở câu 2, kiểm tra processor path. Nếu lỗi ở câu 3, kiểm tra generated output và app compile/runtime path. Không nên sửa ngẫu nhiên tất cả scopes chỉ để hết lỗi.

## 15. Kiểm chứng rằng processor không rò rỉ vào ứng dụng

Bài demo có thể được kiểm tra bằng một chuỗi quan sát:

1. Trước giai đoạn build app, build/api có GenerateMeta.class.
2. build/processor có MetaProcessor.class nhưng build/app chưa có processor class.
3. Sau compile app, build/generated có OrderMeta.java và build/app có OrderMeta.class.
4. Chạy java -cp build/app demo.app.Main được stdout **Meta for Order**.
5. Không có demo/proc/MetaProcessor.class trong build/app.

Lưu ý việc class không nằm trong build/app **chưa bảo đảm** một Gradle/Maven packaging phức tạp không đưa processor.jar vào output cuối qua dependency khác. Với build tool thật, cần kiểm tra thêm dependency graphs và artifact đóng gói.

### Kiểm tra Gradle

Trong project Gradle, các lệnh hữu ích:

~~~sh
gradle :app:dependencies --configuration compileClasspath
gradle :app:dependencies --configuration annotationProcessor
gradle :app:dependencies --configuration runtimeClasspath
~~~

So sánh kết quả của ba configurations. Annotation API, processor implementation và runtime-only dependencies nên xuất hiện đúng ở những nơi được thiết kế. Tên configuration cụ thể còn phụ thuộc plugins/source sets được sử dụng.

### Kiểm tra Maven

Trong Maven, dùng dependency tree của app để xem những artifact thuộc normal dependencies, sau đó xem configuration của maven-compiler-plugin để biết annotationProcessorPaths. Tùy phiên bản plugin, processor dependencies có thể không xuất hiện như một application dependency thông thường. Không lấy dependency:tree làm bằng chứng duy nhất cho toàn bộ processor path.

### Đối chiếu JAR đóng gói

Nếu app cuối cùng là executable JAR/fat JAR, hãy kiểm tra danh sách libraries được package. Implementation processor không nên nằm trong runtime bundle của demo, trừ khi có một lý do runtime riêng thật sự. Với Spring Boot hay shadow JAR, packaging plugins có quy tắc riêng; kiểm tra artifact cuối sau build.

## 16. Processor dependencies và test scope

Khi test sử dụng annotation processing, cần phân biệt:

- **Main source set**: processor tạo generated classes cho ứng dụng chính.
- **Test source set**: test sources cũng có thể dùng annotation để generate helper dành riêng cho tests.
- **Processor unit tests**: chính processor project có test dependencies và có thể compile các nguồn kiểm thử để xác minh generated files/diagnostics.

Trong Gradle Java plugin, testAnnotationProcessor dành cho processors của test compile path. Nếu chỉ cấu hình annotationProcessor cho main compile, test compile có thể không nhận processor theo cách bạn mong muốn. Tuy nhiên generated classes từ main output có thể được test code sử dụng thông qua việc test source set phụ thuộc vào main classes; điều đó khác với việc processor được chạy lại cho test sources.

Một chiến lược kiểm thử tốt:

1. Test annotation API không cần processor implementation.
2. Test processor riêng với input nguồn hợp lệ và input sai annotation.
3. Kiểm tra generated output, diagnostics và javac exit status.
4. Test ứng dụng bằng runtime dependencies thật, **không để processor implementation vô tình che thiếu runtime dependency**.
5. Nếu test source cần processor, cấu hình test-specific processor path rõ ràng.

## 17. Khác biệt với Kotlin KAPT/KSP và các code generators khác

Annotation processing trong bài là **JSR 269/javac** cho Java sources. Với Kotlin, các dự án có thể dùng kapt hoặc KSP, với configurations và cơ chế code generation riêng.

Điểm chung về kiến trúc vẫn là tách:

~~~text
Application API dependencies
        !=
Build-time code generator dependencies
        !=
Generated-code runtime dependencies
~~~

Nhưng không copy nguyên cú pháp Gradle annotationProcessor sang kapt/ksp và cho rằng nó xử lý mọi Kotlin source. Khi dự án hỗn hợp Java/Kotlin, phải kiểm tra plugin compiler và source set tương ứng.

Tương tự, protobuf, OpenAPI và các generators chạy trước javac có thể là build plugins thay vì annotation processors. Phân biệt lifecycle và đầu ra của generator để cấu hình dependencies đúng vị trí.

## 18. Một số vấn đề nâng cao cần biết

### Annotation retention không quyết định mọi runtime dependency

Đừng tuyên bố SOURCE annotation nghĩa là “không bao giờ cần annotation-api ở runtime” trong bất cứ project nào. Nếu runtime code trực tiếp sử dụng interface hoặc helper nằm cùng artifact annotation-api, dependency vẫn cần. Ngược lại, processor không tự trở thành runtime dependency chỉ vì annotation retention là RUNTIME.

### Dependency graph của processor có tính độc lập nhưng không tuyệt đối

Build tools có thể có classloader sharing, worker isolation hoặc cache khác nhau. Điều bạn cần tin cậy là **hợp đồng configuration mà tool cung cấp**, không giả định về từng classloader implementation. Hãy test khi đưa processor sang Gradle/Maven/JDK mới.

### Incremental compilation

Generated files nên có tên xác định và quan hệ rõ với annotated elements. Filer.createSourceFile cho phép truyền originating elements để hỗ trợ công cụ build hiểu nguồn sinh. Tuy nhiên một processor có trở thành incremental-safe hay không còn tùy kiểu processor, cách đọc input, file outputs và quy tắc của build tool. Không chỉ cần tách dependency là incremental build tự động đúng.

### Processor và build cache

Nếu processor đọc file bên ngoài mà build tool không biết, sinh nội dung phụ thuộc thời gian hoặc cấu hình toàn cục không khai báo, cache có thể sai. Hãy giới hạn side effects và mô tả inputs rõ ràng. Đây là lý do các processor dễ bảo trì thường cố tạo output deterministic.

### Multi-release JAR và phiên bản JDK

Processor JAR cần chạy được trên JDK đang thực thi compiler, không chỉ trên mức bytecode mà app nhắm tới. Ví dụ app build với --release 17 bằng JDK mới; processor có thể chạy trong compiler process của JDK mới đó. Vì vậy cần kiểm tra cả toolchain của build và khả năng tương thích của processor implementation. Đừng nhầm target bytecode với JVM thực thi processor.

## 19. Bài tập thực hành

**Bài 1 — Phân loại dependency.** Liệt kê annotation-api, processor, processor-util và runtime-helper. Với từng artifact, điền ba cột: app compile, processor execution, app runtime. Giải thích bằng đường gọi thực tế thay vì tên thư viện.

**Bài 2 — Biên dịch thủ công.** Tạo project Java 17 ở phần 5. Chạy ba lệnh javac và java. Vì sao OrderMeta.java không tồn tại trước khi compiler chạy processor nhưng lại có sau khi compile?

**Bài 3 — Loại processor khỏi runtime.** Chạy java -cp build/app demo.app.Main; xác nhận vẫn in Meta for Order. Vì sao không cần -cp build/app:build/processor? Trả lời dựa trên bytecode/runtime dependencies của Main và OrderMeta.

**Bài 4 — Thử thiếu annotation API.** Bỏ -cp build/api ở giai đoạn compile app. Dự đoán import demo.ann.GenerateMeta sẽ thất bại. Việc processor còn nằm trên -processorpath có sửa lỗi type resolution của source app không?

**Bài 5 — Thử thiếu processor.** Giữ annotation API trên -cp nhưng tắt annotation processing bằng -proc:none trong một build sạch. Vì sao Main có thể báo không tìm thấy OrderMeta? Vì annotation type hiện diện không đồng nghĩa generated class đã được tạo.

**Bài 6 — Thêm processor runtime dependency.** Giả sử MetaProcessor dùng helper trong processor-util. Cần khai báo ở project nào và path nào? Nếu app không dùng helper đó khi chạy, vì sao không thêm vào app runtime?

**Bài 7 — Generated runtime dependency.** Sửa generator để OrderMeta gọi một class thuộc runtime-helper.jar. Bổ sung dependency đúng cho generated source compilation và application runtime. Kiểm tra nếu chỉ thêm runtime-helper vào annotationProcessor configuration, lỗi gì có thể xảy ra?

**Bài 8 — Gradle.** Chuyển cấu trúc sang ba subprojects, thêm compileOnly và annotationProcessor đúng chỗ. Tạo application plugin để chạy :app:run và kiểm tra runtimeClasspath không tự chứa processor project.

**Bài 9 — Maven.** Tổ chức ba modules annotation-api/processor/app; khai báo annotation-api ở app dependency và processor trong annotationProcessorPaths. Giải thích vai trò provided/compile theo nhu cầu runtime thực tế.

**Bài 10 — SOURCE và RUNTIME.** Đổi annotation retention thành RUNTIME, thêm code Reflection đọc annotation ở runtime. Tại sao annotation-api có thể trở thành runtime dependency thật, trong khi processor implementation vẫn không phải?

**Bài 11 — Bảo mật build.** Nhóm phụ thuộc nào có code được thực thi ngay khi compile? Vì sao cần pin version và chỉ nạp processor từ nguồn đáng tin?

**Bài 12 — Mixed Java/Kotlin.** Nếu một số source Kotlin dùng kapt hoặc KSP, điều gì không thể mặc định về Gradle annotationProcessor configuration? Trình bày cách kiểm tra toolchain và plugin tương ứng.

## 20. Checklist thiết kế build sạch

- Đã biết annotation API, processor implementation và generated runtime dependencies là ba vai trò khác nhau.
- App source nhìn thấy annotation API trong đúng compile path.
- Processor được lựa chọn tường minh và nạp từ processor-specific path.
- Processor dependencies đầy đủ trong môi trường **chạy processor lúc build**.
- Generated source được compile với những API mà nó tham chiếu.
- App runtime path có những thư viện bytecode app/generated code thật sự cần.
- Không đưa processor implementation vào app implementation chỉ vì muốn nó chạy khi compile.
- Không mặc định SOURCE-retained annotation API luôn/không bao giờ cần ở runtime ngoài ngữ cảnh.
- Đã biết Gradle compileOnly, implementation, annotationProcessor, testAnnotationProcessor khác nhau.
- Đã biết Maven dependency scopes khác annotationProcessorPaths của compiler plugin.
- Đã hiểu vì sao Java 23+ làm cấu hình annotation processing tường minh càng quan trọng.
- Đã xác nhận build sạch, generated file, app output và dependency graph.
- Đã kiểm tra processor không vô tình xuất hiện trong packaged runtime artifact.
- Có kế hoạch bảo trì processor versions, incremental build và build supply chain.

### Tài liệu tham khảo để đọc sâu

- **Java SE 17 API: javax.annotation.processing**, AbstractProcessor, ProcessingEnvironment, Filer và RoundEnvironment.
- **Javac documentation** của JDK đang dùng: -classpath, -processorpath, -processor, -proc, -s, -d, --release, --processor-module-path.
- **Gradle Java Plugin / Java Library Plugin documentation**: implementation, api, compileOnly, annotationProcessor, runtimeOnly, testAnnotationProcessor và toolchains.
- **Maven Compiler Plugin documentation** đúng phiên bản sử dụng: annotationProcessorPaths, annotationProcessors, release và processor dependencies.
- **Java Platform Module System**: module path, processor module path và requires/exports khi dùng named modules.

**Tóm lại:** ứng dụng và annotation processor chạy ở **hai giai đoạn khác nhau**, với mục tiêu và dependency graphs khác nhau. Đưa annotation API vào nơi source cần nó, đưa implementation/dependencies của processor vào nơi compiler chạy nó, và đưa thư viện runtime vào nơi bytecode ứng dụng thực sự dùng. Tách đúng ba vai trò giúp build rõ ràng, kiểm soát được, dễ tái hiện và ít xung đột hơn.
