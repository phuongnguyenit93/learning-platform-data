# Cấu trúc AbstractProcessor và ProcessingEnvironment trong Java Annotation Processing

## 1. Mục tiêu và bản chất

**Annotation processing** là cơ chế để Java compiler gọi một chương trình xử lý các annotation và thông tin kiểu/khai báo trong lúc biên dịch. Processor có thể kiểm tra quy ước của code, phát diagnostic và sinh thêm source, class hoặc resource. Nó không phải một callback được kích hoạt khi ứng dụng chạy.

Hai API quan trọng nhất khi tự xây processor chuẩn Java:

- **javax.annotation.processing.AbstractProcessor**: lớp cơ sở triển khai interface Processor, hỗ trợ khai báo annotation types/options/source version và cung cấp điểm mở rộng init/process.
- **javax.annotation.processing.ProcessingEnvironment**: môi trường do compiler cấp khi khởi tạo processor, chứa các công cụ để viết output, thông báo lỗi, đọc mô hình ngôn ngữ và tùy chọn build.

Bài này tập trung trực tiếp vào **cấu trúc của AbstractProcessor và vai trò của ProcessingEnvironment**, với Java 17+, ví dụ chạy được, thứ tự compile hai giai đoạn, nhiều processing rounds, các lỗi thường gặp và hướng phát triển thành processor dùng trong dự án thật.

Sau bài, bạn cần giải thích được: tại sao phải gọi super.init, ý nghĩa boolean trả về từ process, sự khác biệt giữa Element và TypeMirror, các vai trò Filer/Messager/Elements/Types, lý do dùng -processorpath, và vì sao generated source có thể được biên dịch trong cùng invocation.

## 2. Sơ đồ dòng xử lý

~~~text
Các file nguồn .java + annotations
                |
                v
            javac
                |
                v
    Tìm / nạp Processor
                |
                v
    init(ProcessingEnvironment)
                |
                v
      Processing round 1
    process(annotations, roundEnv)
        |           |
        |           +----> Messager: NOTE/WARNING/ERROR
        +----------------> Filer: tạo source mới
                |
                v
      Processing round 2
    Các file sinh mới tham gia input
                |
                v
     ... có thể thêm rounds ...
                |
                v
     Vòng cuối processingOver=true
                |
                v
   Hoàn thành compilation và output .class
~~~

Sơ đồ mang tính khái niệm; không nhằm mô tả đầy đủ thứ tự triển khai nội bộ của javac. Không phải compiler sẽ luôn có đúng ba rounds. Một generated source không nhất thiết có annotation mới; dù vậy nó vẫn có thể xuất hiện ở input của round tiếp theo.

**Phân biệt với Reflection:** Reflection thường quan sát class đã nạp lúc runtime; annotation processor chủ yếu sử dụng javax.lang.model để nghiên cứu các khai báo/kiểu **chưa cần có .class**. Đừng cố nạp class nguồn bằng Class.forName để phân tích annotation trong một processor bình thường.

## 3. AbstractProcessor là gì?

Processor là interface chuẩn khai báo những thao tác một compiler có thể yêu cầu processor thực hiện. AbstractProcessor cung cấp cách triển khai thuận tiện hơn việc implement toàn bộ interface trực tiếp.

Khung Java 17:

~~~java
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.ProcessingEnvironment;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("demo.processor.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    @Override
    public synchronized void init(ProcessingEnvironment env) {
        super.init(env);
        // Lưu các dịch vụ cần dùng từ env.
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        // Xử lý annotation và các elements trong round.
        return true;
    }
}
~~~

**Đây chỉ là khung minh họa:** nó chưa có package/annotation/source app hoàn chỉnh. Project runnable đầy đủ xuất hiện ở phần 7–9.

### Những method quan trọng

| Thành phần | Ý nghĩa |
| --- | --- |
| init(ProcessingEnvironment) | Được compiler gọi để cấp môi trường trước khi xử lý |
| process(Set<? extends TypeElement>, RoundEnvironment) | Xử lý các annotation types và elements được giao trong round |
| getSupportedAnnotationTypes() | Công bố tên các annotation processor có thể xử lý |
| getSupportedSourceVersion() | Công bố mức ngôn ngữ source được processor hỗ trợ |
| getSupportedOptions() | Công bố tên các -A options |
| getCompletions(...) | API gợi ý completion cho giá trị annotation, thường không cần override |
| protected processingEnv | Trường môi trường của AbstractProcessor sau khi init |

AbstractProcessor có khả năng đọc các annotation cấu hình như SupportedAnnotationTypes, SupportedSourceVersion, SupportedOptions để trả thông tin tương ứng. Không khai báo annotation hỗ trợ hoặc source version phù hợp có thể gây warning và khiến processor không được gọi theo cách mong muốn.

**super.init(env) rất quan trọng.** Nếu override init mà quên gọi super.init, trường processingEnv của AbstractProcessor và một số cơ chế mặc định có thể không được thiết lập hợp lệ. Đừng sử dụng processingEnv trong constructor hay static initializer trước khi compiler gọi init.

### Boolean trả về từ process

- **true**: processor tuyên bố đã xử lý/claim các annotation types được trao; các processor tiếp theo thông thường không được giao lại chính những types đó.
- **false**: không claim; compiler có thể cho các processor khác cơ hội xử lý những types tương ứng.

**true không có nghĩa “build thành công”.** Processor vẫn có thể báo ERROR qua Messager rồi trả true. Đây là quyết định về phân phối annotation giữa các processors, không phải exit code của javac.

Ví dụ học tập sở hữu duy nhất @GenerateGreeting, nên trả true. Với nhiều processors cùng cần đọc annotation, việc claim phải được thiết kế theo hợp đồng phối hợp.

## 4. ProcessingEnvironment: tập dịch vụ do compiler cấp

ProcessingEnvironment không phải đối tượng do người viết tự tạo bằng new. Compiler cung cấp nó qua init. Các API đáng nhớ:

| Method | Trả về | Dùng để |
| --- | --- | --- |
| getFiler() | Filer | Tạo .java, .class hoặc resource output được compiler quản lý |
| getMessager() | Messager | In diagnostic NOTE/WARNING/ERROR gắn với source element |
| getElementUtils() | Elements | Tìm và khảo sát khai báo class/package/method/field |
| getTypeUtils() | Types | Phân tích TypeMirror, assignability, subtype, erasure |
| getOptions() | Map<String,String> | Đọc cấu hình -Akey=value cho processor |
| getSourceVersion() | SourceVersion | Biết source version của môi trường xử lý |
| getLocale() | Locale | Locale phục vụ việc xây diagnostic |

~~~text
                  ProcessingEnvironment
                          |
          +---------------+---------------+
          |               |               |
        Filer          Messager          Elements
       output        diagnostics     declarations
          |               |               |
     .java/.class       errors          TypeElement
                          |
                       Types
                     TypeMirror
~~~

**Không trộn vai trò:**

- **Filer** ghi output theo luật của compiler. Đừng thay bằng FileWriter tùy ý ghi đè source ban đầu.
- **Messager** là kênh chuẩn để javac/IDE nhận thông báo có mức độ và vị trí. Đừng dùng System.out để giả lập compile error.
- **Elements** hỏi về *khai báo*: package của một class, tên đầy đủ, các member của type.
- **Types** hỏi về *kiểu*: kiểu nào có thể gán cho kiểu nào, subtype, erasure, v.v.

### Element và TypeMirror khác nhau thế nào?

Element biểu diễn một **khai báo/phần tử chương trình**; TypeElement đại diện khai báo kiểu (class/interface...). TypeMirror biểu diễn một **kiểu** theo mô hình type system của compiler, ví dụ List<String>, kiểu primitive hay một kiểu biến generic.

Trong processor, đừng so sánh getSimpleName() như chuỗi rồi kết luận hai TypeElement đại diện cùng một kiểu; hai package có thể có class cùng tên. Nếu cần phân tích quan hệ kiểu, dùng API Types tương ứng.

Snippet minh họa, không độc lập:

~~~java
TypeElement runnableType =
        processingEnv.getElementUtils().getTypeElement("java.lang.Runnable");
boolean matches = processingEnv.getTypeUtils().isAssignable(
        candidate.asType(),
        runnableType.asType());
~~~

candidate phải là một TypeElement đã lấy được từ môi trường xử lý. Tùy logic, Types.isSubtype hoặc các API khác có thể phù hợp hơn; đừng dùng Reflection cho kiểu source chưa biên dịch.

## 5. Vòng đời: init, process và RoundEnvironment

**init** thông thường được gọi một lần cho mỗi instance processor trước khi các vòng xử lý bắt đầu. **process** có thể được gọi nhiều lần trong cùng lượt compile.

RoundEnvironment cung cấp:

- **getElementsAnnotatedWith(AnnotationClass.class)**: các elements được annotation chỉ định trong round.
- **getElementsAnnotatedWith(TypeElement)**: biến thể dùng mô hình compile-time thay vì Class<?>.
- **getRootElements()**: root elements được cung cấp cho round.
- **processingOver()**: thông báo vòng cuối.
- **errorRaised()**: biết có lỗi được báo ở vòng trước theo hợp đồng API.

Ví dụ:

~~~text
Round 1:
    Order.java được annotate @GenerateGreeting
    Processor sinh OrderGreeting.java

Round 2:
    OrderGreeting.java trở thành nguồn mới
    Không có @GenerateGreeting mới

Round 3:
    Round cuối, processingOver() == true
~~~

Vòng cuối thường có tập annotation rỗng. Đừng giả định process chỉ chạy một lần hoặc mọi round đều có element mới. Processor tốt không tạo file trùng tên chỉ vì process được gọi tiếp.

**FilerException:** tạo lại cùng một file output trong một processing invocation, tạo đè tệp input hoặc va chạm giữa nhiều processor có thể dẫn tới FilerException. Hãy đặt tên output duy nhất, kiểm soát round tạo file và báo lỗi thay vì bắt rồi im lặng.

## 6. Dự án thực hành Java 17

Tạo thư mục **processor-lab**:

~~~text
processor-lab/
├── src-processor/
│   └── demo/
│       └── processor/
│           ├── GenerateGreeting.java
│           └── GreetingProcessor.java
├── src-app/
│   └── demo/
│       └── app/
│           ├── Order.java
│           └── Main.java
└── build/
    ├── processor/
    ├── classes/
    └── generated/
~~~

Đường dẫn build sẽ được tạo trước compile. Tách src-processor và src-app để nhìn rõ **hai giai đoạn**: đầu tiên tạo processor .class; tiếp theo dùng processor đó khi compile app. Không cần Maven/Gradle hoặc thư viện ngoài.

### 6.1. src-processor/demo/processor/GenerateGreeting.java

~~~java
package demo.processor;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateGreeting {
}
~~~

@Target(TYPE) cho phép gắn annotation vào các khai báo kiểu. Processor của demo chấp nhận ElementKind.CLASS; nếu gắn lên interface hoặc enum, nó chủ động phát ERROR. RetentionPolicy.SOURCE đủ cho processor đọc annotation trong source; không cần giữ metadata này ở runtime.

Annotation processor **không buộc mọi annotation phải SOURCE retention**. Retention mô tả nơi annotation được giữ, còn sự lựa chọn/chạy processor phụ thuộc compiler và cấu hình annotation processing.

### 6.2. src-processor/demo/processor/GreetingProcessor.java

~~~java
package demo.processor;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.Filer;
import javax.annotation.processing.Messager;
import javax.annotation.processing.ProcessingEnvironment;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.PackageElement;
import javax.lang.model.element.TypeElement;
import javax.lang.model.util.Elements;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.processor.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    private Filer filer;
    private Messager messager;
    private Elements elements;

    @Override
    public synchronized void init(ProcessingEnvironment environment) {
        super.init(environment);
        filer = environment.getFiler();
        messager = environment.getMessager();
        elements = environment.getElementUtils();
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnvironment) {
        if (roundEnvironment.processingOver()) {
            return true;
        }

        for (Element element : roundEnvironment
                .getElementsAnnotatedWith(GenerateGreeting.class)) {
            if (element.getKind() != ElementKind.CLASS) {
                messager.printMessage(Diagnostic.Kind.ERROR,
                        "Only classes are supported", element);
                continue;
            }

            TypeElement type = (TypeElement) element;
            PackageElement packageElement = elements.getPackageOf(type);
            String packageName = packageElement.isUnnamed() ? ""
                    : packageElement.getQualifiedName().toString();
            String simpleName = type.getSimpleName() + "Greeting";
            String qualifiedName = packageName.isEmpty() ? simpleName
                    : packageName + "." + simpleName;

            try {
                JavaFileObject file = filer.createSourceFile(qualifiedName, type);
                try (Writer writer = file.openWriter()) {
                    if (!packageName.isEmpty()) {
                        writer.write("package " + packageName + ";\n\n");
                    }
                    writer.write("public final class " + simpleName + " {\n");
                    writer.write("    private " + simpleName + "() {}\n");
                    writer.write("    public static String message() {\n");
                    writer.write("        return \"Generated for "
                            + type.getSimpleName() + "\";\n");
                    writer.write("    }\n}\n");
                }
                messager.printMessage(Diagnostic.Kind.NOTE,
                        "Generated " + qualifiedName, type);
            } catch (IOException ex) {
                messager.printMessage(Diagnostic.Kind.ERROR,
                        "Cannot generate " + qualifiedName + ": " + ex.getMessage(),
                        type);
            }
        }
        return true;
    }
}
~~~

**Giải thích code:**

1. SupportedAnnotationTypes chỉ ra qualified name của annotation mà processor tiếp nhận.
2. SupportedSourceVersion khai báo mức ngôn ngữ Java 17 mà processor đã thiết kế hỗ trợ.
3. init gọi super.init trước khi lấy Filer, Messager, Elements.
4. process bỏ qua sinh file khi processingOver() đúng.
5. getElementsAnnotatedWith lấy các nguồn trong round mang @GenerateGreeting.
6. Processor kiểm tra element có ElementKind.CLASS trước khi cast sang TypeElement.
7. Elements.getPackageOf lấy package. Qualified name của output là tên class + Greeting trong package tương ứng.
8. Filer.createSourceFile tạo nguồn mới, writer ghi mã Java và đóng bằng try-with-resources.
9. Messager NOTE chỉ ra output được tạo; lỗi IOException được chuyển thành diagnostic ERROR.
10. return true có nghĩa claim loại annotation này, không có nghĩa bảo đảm toàn bộ build thành công.

**Giới hạn của demo:** kiểu được annotate chỉ cần là class; code không xử lý mọi trường hợp va chạm tên với nested classes, nhiều class cùng simple name hay generated type đã có. Đây là điểm cần mở rộng nếu dùng thực tế. Tên lớp hợp lệ từ getSimpleName() giúp nguồn mẫu không phải escape dữ liệu đầu vào tùy ý; nếu output của bạn ghép dữ liệu chuỗi từ annotation value, cần escape Java string literal an toàn.

Các API javax.annotation.processing và javax.lang.model ở JDK 17 thuộc module **java.compiler**, không cần cài dependency bên ngoài chỉ vì tên package có tiền tố javax.

### 6.3. src-app/demo/app/Order.java

~~~java
package demo.app;

import demo.processor.GenerateGreeting;

@GenerateGreeting
public final class Order {
}
~~~

Order được đánh dấu @GenerateGreeting. Processor sẽ sinh **demo.app.OrderGreeting**, cùng package với Order.

### 6.4. src-app/demo/app/Main.java

~~~java
package demo.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println(OrderGreeting.message());
    }
}
~~~

Trong dự án nguồn **không có OrderGreeting.java ban đầu**. javac sẽ thấy generated source ở vòng annotation processing tiếp theo và biên dịch nó; vì vậy tham chiếu OrderGreeting ở Main trở nên hợp lệ trong cùng compilation invocation.

## 7. Compile processor trước, compile app sau

Dùng **JDK 17 hoặc mới hơn** và mở terminal tại gốc processor-lab.

~~~sh
javac -version
java -version
~~~

Tạo thư mục output, chọn một lệnh phù hợp với shell:

~~~bash
# Bash trên macOS/Linux
mkdir -p build/processor build/classes build/generated
~~~

~~~powershell
# PowerShell trên Windows
New-Item -ItemType Directory -Path build/processor,build/classes,build/generated -Force | Out-Null
~~~

### Giai đoạn A — Biên dịch processor

~~~sh
javac --release 17 -d build/processor src-processor/demo/processor/GenerateGreeting.java src-processor/demo/processor/GreetingProcessor.java
~~~

Các file .class sẽ xuất hiện trong build/processor/demo/processor. Processor cần được biên dịch trước để compiler có thể nạp implementation trong giai đoạn tiếp theo. Đừng dùng java để chạy GreetingProcessor như ứng dụng có main.

### Giai đoạn B — Yêu cầu javac chạy processor

~~~sh
javac --release 17 -cp build/processor -processorpath build/processor -processor demo.processor.GreetingProcessor -s build/generated -d build/classes src-app/demo/app/Order.java src-app/demo/app/Main.java
~~~

| Tùy chọn | Vai trò |
| --- | --- |
| --release 17 | Biên dịch theo mức Java 17 |
| -cp build/processor | Nơi source app tra cứu annotation GenerateGreeting.class |
| -processorpath build/processor | Nơi javac tải implementation processor |
| -processor demo.processor.GreetingProcessor | Chọn processor chính xác, không phụ thuộc auto-discovery |
| -s build/generated | Nơi ghi generated **source .java** |
| -d build/classes | Nơi ghi .class cho app và generated types |

Ở demo, annotation API và implementation nằm cùng build/processor nên cả -cp và -processorpath trỏ đến một nơi. Trong dự án sản xuất, thường tách annotation API artifact khỏi processor implementation artifact; hai path có mục đích khác nhau.

Sau lệnh, javac có thể in NOTE dạng:

~~~text
src-app/demo/app/Order.java:...: Note: Generated demo.app.OrderGreeting
~~~

Đây là **diagnostic javac**, không phải stdout của ứng dụng. Dòng/caret có thể khác theo JDK.

Xem generated source:

~~~text
build/generated/demo/app/OrderGreeting.java
~~~

Nội dung:

~~~java
package demo.app;

public final class OrderGreeting {
    private OrderGreeting() {}
    public static String message() {
        return "Generated for Order";
    }
}
~~~

Và generated bytecode ở build/classes/demo/app/OrderGreeting.class cùng Order.class, Main.class.

### Giai đoạn C — Chạy app

~~~sh
java -cp build/classes demo.app.Main
~~~

**Stdout chính xác:**

~~~text
Generated for Order
~~~

Dự án này không cần build/processor trong runtime classpath: annotation có SOURCE retention, và generated output không gọi code của processor khi chạy. Trong dự án khác, runtime dependencies vẫn phải cung cấp nếu code thực thi thật sự tham chiếu tới chúng.

## 8. Quan sát rounds khi cần debug

Javac hỗ trợ option chẩn đoán:

~~~sh
javac -XprintRounds --release 17 -cp build/processor -processorpath build/processor -processor demo.processor.GreetingProcessor -s build/generated -d build/classes src-app/demo/app/Order.java src-app/demo/app/Main.java
~~~

Khi thử chạy lại từ đầu, nên dùng **output riêng mới hoặc làm sạch đúng các thư mục output của ví dụ** để tránh nhầm generated files cũ. Không xóa các file thuộc workspace khác.

Một bản log minh họa:

~~~text
Round 1:
    input files: {demo.app.Order, demo.app.Main}
    annotations: [demo.processor.GenerateGreeting]
    last round: false
Round 2:
    input files: {demo.app.OrderGreeting}
    annotations: []
    last round: false
Round 3:
    input files: {}
    annotations: []
    last round: true
~~~

Đây là **mẫu có ý nghĩa giải thích**, không cam kết thứ tự/định dạng output của mọi JDK. Điểm cần quan sát: Order mang annotation ở round đầu; OrderGreeting được sinh và trở thành input mới; vòng cuối có processingOver()==true.

Javac còn có -XprintProcessorInfo để tìm hiểu processor nào được chạy và annotation nào được giao. Các option -X mang tính chẩn đoán; khi dùng JDK khác, tham khảo javac -help-extra.

**Không nên gọi createSourceFile ở final round:** các file được sinh trong vòng cuối không thể tham gia lượt annotation processing mới bình thường theo cách bạn mong đợi. Demo chỉ sinh khi processingOver() false.

## 9. Filer: sinh file và tránh tạo trùng

Filer quản lý output được sinh bởi processor. Những method thường dùng:

| Method | Dùng để tạo |
| --- | --- |
| createSourceFile(qualifiedName, originatingElements...) | File .java mới |
| createClassFile(binaryName, originatingElements...) | File .class do generator tự tạo |
| createResource(location, packageName, relativeName, originatingElements...) | File resource tại location được API hỗ trợ |

Cấu trúc thao tác điển hình:

~~~java
JavaFileObject file = filer.createSourceFile(qualifiedName, originatingType);
try (Writer writer = file.openWriter()) {
    writer.write("public final class Sample {}");
}
~~~

Đoạn này chỉ minh họa API; không phải chương trình độc lập để chạy bằng java. originatingType là element nguồn tương ứng với generated file, hỗ trợ compiler/build tool nhận biết quan hệ đầu vào–đầu ra. Đây là thông tin hữu ích cho một số hệ thống incremental compilation, **không tự bảo đảm** processor được incremental an toàn.

### Vì sao không dùng FileWriter tự ghi vào src-app?

- Compiler không nhất thiết nhìn file tự ghi như một output hợp lệ của annotation processing ở vòng tiếp theo.
- Ghi đè source của người dùng là side effect khó kiểm soát.
- Dễ lỗi đường dẫn khi chuyển IDE, Maven/Gradle, Windows/Linux.
- Khó dùng build cache/incremental tooling đúng cách.

Filer áp dụng quy tắc output, quản lý file được tạo và có cơ chế ngăn trùng file identity trong một invocation. Đóng Writer giúp compiler nhận được file hoàn chỉnh.

### FilerException và output collision

FilerException là một IOException có thể xuất hiện khi:

- Hai annotated elements cùng sinh đúng một qualified source name.
- Một processor cố tạo lại file đã tạo trong invocation hiện tại.
- Nguồn do processor sinh trùng với source đã là input.
- Nhiều processors sinh cùng một output.

Cách sửa: định nghĩa quy tắc đặt tên ổn định, kiểm tra phạm vi hỗ trợ của annotations, xử lý nested classes và va chạm tên, sinh mỗi output một lần. Đừng bắt lỗi rồi làm như build thành công vì code client có thể thiếu generated type hoặc nạp artifact cũ.

## 10. Messager: gửi diagnostic đúng chuẩn

Messager giúp compiler/IDE gắn thông báo với nguồn:

~~~java
messager.printMessage(
        Diagnostic.Kind.ERROR,
        "Only classes are supported",
        element);
~~~

Một số Diagnostic.Kind:

- **NOTE**: thông tin quá trình xử lý.
- **WARNING**: cảnh báo.
- **MANDATORY_WARNING**: cảnh báo bắt buộc theo hợp đồng compiler.
- **ERROR**: lỗi biên dịch.

Với overload nhận Element, thông báo được gắn với khai báo nguồn. Có overload nhận AnnotationMirror/AnnotationValue để chỉ chính xác một annotation hoặc value sai.

**System.out không phải kênh thay thế Messager.** Nếu một annotation có cấu hình thiếu hoặc một kiểu không thỏa yêu cầu, hãy báo ERROR có ích, nêu lý do và hướng sửa. Chỉ log stack trace hoặc ném exception vô hướng làm người dùng khó tìm lỗi.

Trong ví dụ, một interface được @GenerateGreeting là một annotation target hợp lệ về cú pháp (@Target(TYPE)) nhưng **không hợp lệ theo policy của processor**. Processor sẽ báo Only classes are supported. Đây là lỗi validation của processor chứ không phải lỗi định nghĩa annotation.

## 11. Elements, Types và kiểm tra source ở compile-time

### Elements và TypeElement

Trong demo:

~~~java
PackageElement packageElement = elements.getPackageOf(type);
String packageName = packageElement.isUnnamed() ? ""
        : packageElement.getQualifiedName().toString();
~~~

API Elements cung cấp thông tin package chính xác hơn việc tách chuỗi đường dẫn .java thủ công. Với nested class hoặc generics, không nên chỉ dựa vào simple name để suy luận package/binary name.

### Types và TypeMirror

Nếu cần processor chỉ chấp nhận class implement Runnable, code sản xuất có thể lấy TypeElement tương ứng java.lang.Runnable rồi kiểm tra bằng Types.isAssignable. Đây là kiểm tra trên mô hình kiểu compile-time; việc so sánh chuỗi tên ngắn không đủ vì hai types có thể cùng simple name.

Snippet không độc lập:

~~~java
TypeElement runnableType =
        processingEnv.getElementUtils().getTypeElement("java.lang.Runnable");
boolean valid = processingEnv.getTypeUtils().isAssignable(
        candidate.asType(),
        runnableType.asType());
~~~

candidate cần là TypeElement đã có. Tùy trường hợp, có thể cần kiểm tra null, subtype, generic bounds hoặc erasure để quy tắc thực sự khớp yêu cầu nghiệp vụ. Dùng đúng API mô hình kiểu tốt hơn Reflection khi source chưa có bytecode.

### Options từ compiler

Bên ngoài có thể truyền:

~~~sh
javac -Agreeting.mode=short ...
~~~

Trong processor mở rộng, khai báo @SupportedOptions("greeting.mode") hoặc override getSupportedOptions. Đọc:

~~~java
String mode = processingEnv.getOptions()
        .getOrDefault("greeting.mode", "default");
~~~

Đoạn là **minh họa cho phần mở rộng**; bản GreetingProcessor runnable của bài không hỗ trợ greeting.mode nên thêm option này **không tự thay đổi output**. Đừng nhầm đoạn minh họa với tính năng đã cài.

Options là dữ liệu đầu vào, cần validate. Khi tạo Java source từ text cấu hình do người dùng nhập, phải escape chuỗi theo cú pháp Java; không nối trực tiếp text không đáng tin vào string literal hoặc source code.

## 12. -processor, discovery và packaging

Bản demo dùng:

~~~text
-processorpath build/processor
-processor demo.processor.GreetingProcessor
~~~

Cách này buộc javac chọn processor cụ thể, dễ tái hiện. Nếu thiếu implementation trên processor path, có thể gặp lỗi processor not found.

Một cơ chế khác là **service registration**. JAR processor kiểu classpath có thể chứa:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nội dung:

~~~text
demo.processor.GreetingProcessor
~~~

Khi toolchain cho phép discovery, compiler có thể tìm processor được khai báo trong service metadata. Tuy nhiên **không nên dựa vào việc processor luôn tự chạy chỉ vì JAR có trong classpath**: mặc định discovery và chính sách annotation processing thay đổi giữa các bản JDK và build tools. Lệnh của bài chọn processor rõ ràng để kiểm chứng được.

Nếu đóng gói processor như named Java module, có thể công bố service provider qua module-info.java với provides javax.annotation.processing.Processor with ... theo quy tắc JPMS. Đây là một hướng packaging khác; dự án demo dùng classpath đơn giản.

Trong project Maven/Gradle, dependencies của processor và annotation API có thể được tách ra và khai báo trong các cấu hình dành riêng cho annotation processing. Compiler process được **thực thi với quyền của build process**, nên chỉ chạy processor từ nguồn tin cậy và kiểm soát version.

## 13. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân khả dĩ | Bước sửa |
| --- | --- | --- |
| Annotation processor not found | Stage A chưa compile, sai class name hoặc -processorpath | Kiểm tra build/processor và qualified class name |
| package demo.processor does not exist | App compile thiếu annotation API | Kiểm tra -cp build/processor hoặc annotation dependency |
| cannot find symbol OrderGreeting | Processor không chạy hoặc chưa sinh file | Kiểm tra -processor, build/generated, diagnostic của javac |
| FilerException: Attempt to recreate a file | Sinh trùng qualified name trong compile invocation | Xác định va chạm, tạo một lần |
| Only classes are supported | Annotation đặt vào kiểu không được processor hỗ trợ | Đổi target hoặc mở rộng rule có chủ đích |
| Warning về supported source version | JDK/source level cao hơn mức processor tuyên bố | Kiểm tra @SupportedSourceVersion và --release |
| Generated .java có mà .class không có | Biên dịch source bị lỗi hoặc đang dùng -proc:only | Kiểm tra error và -proc flag |
| Không thấy processor chạy | Discovery bị tắt hoặc processor không được chọn | Chọn tường minh bằng -processor |
| Chạy ra kết quả cũ | Output generated/class stale | Làm sạch **đúng output demo** và build lại |

### -proc:only và -proc:none

- **-proc:only** yêu cầu chạy annotation processing nhưng bỏ qua phần compilation đầy đủ thành .class. Dùng để quan sát generator, không phải lệnh build để chạy app hoàn chỉnh.
- **-proc:none** tắt annotation processing. Với project này, nếu không có OrderGreeting được cung cấp bằng cách khác, Main sẽ không compile vì thiếu type được sinh.

Lệnh chính ở phần 7 không dùng hai flag trên. Khi chuyển sang JDK mới, hãy kiểm tra cấu hình annotation processing rõ ràng vì mặc định của compiler/toolchain có thể thay đổi.

## 14. Thiết kế processor dùng trong dự án thật

Một cấu trúc dễ kiểm soát:

~~~text
GreetingProcessor extends AbstractProcessor
    |
    +-- init(ProcessingEnvironment)
    |     +-- lấy Filer / Messager / Elements / Types
    |     +-- validate supported options
    |
    +-- process(annotations, round)
          +-- đọc annotated elements
          +-- validate kind, type, annotation values
          +-- xây intermediate model
          +-- quyết định tên output duy nhất
          +-- sinh source qua Filer
          +-- thông báo lỗi/cảnh báo qua Messager
~~~

Các quy tắc quan trọng:

1. **Validate trước khi sinh:** đảm bảo kind, type constraints và options hợp lệ trước khi ghi source nửa chừng.
2. **Deterministic output:** input/options giống nhau nên tạo code như nhau; không đưa timestamp/ngẫu nhiên vào source nếu không có lý do.
3. **Tên output ổn định:** xử lý nested types, package, collision với source hiện có và nhiều annotated elements.
4. **Originating elements:** truyền đúng element nguồn vào Filer để hỗ trợ compiler/build tooling hiểu dependency; chỉ vậy chưa đủ để processor tự trở thành incremental-safe.
5. **Không phụ thuộc thứ tự Set:** khi nhiều elements, sắp xếp theo qualified name nếu thứ tự source generated có ý nghĩa.
6. **Không giữ Element/TypeMirror từ compile invocation cũ:** mô hình compiler có vòng đời riêng, tránh static cache gây stale data.
7. **Không sửa source do người dùng viết:** API chuẩn JSR 269 chủ yếu hỗ trợ đọc model và sinh output mới. AST mutation là cơ chế compiler-specific, không được AbstractProcessor bảo đảm.
8. **Bảo vệ build:** processor là mã chạy ở thời gian build; không tự ý tải processor lạ hoặc cấp quyền nhạy cảm.

### Kiểm thử một processor

Tối thiểu cần kiểm tra:

- Với Order.java hợp lệ, sinh đúng demo.app.OrderGreeting.java.
- Generated source được javac compile thành .class trong cùng build.
- Chạy Main in đúng Generated for Order.
- Annotation trên kiểu không hỗ trợ tạo ERROR đúng vị trí.
- Việc trùng tên output không bị im lặng nuốt lỗi.
- Khi annotation vắng mặt, không sinh source thừa.
- Khi thay đổi input, build mới dùng generated code mới chứ không artifact cũ.

Có thể dùng JavaCompiler API từ javax.tools, thư mục test tạm hoặc thư viện hỗ trợ annotation processor tests để kiểm tra file output và diagnostics, không chỉ xem NOTE.

## 15. Bài tập vận dụng

**Bài 1 — Nhận diện dịch vụ.** Nếu muốn tạo source, báo compile error, lấy package của class và kiểm tra quan hệ kiểu, bạn chọn Filer/Messager/Elements/Types tương ứng nào? Tại sao Reflection không phù hợp khi đang phân tích source?

**Bài 2 — Quan sát round.** Dùng -XprintRounds. Giải thích vì sao OrderGreeting được compiler xử lý ở round tiếp theo dù nó không có @GenerateGreeting, và tại sao process có thể được gọi với tập annotation rỗng.

**Bài 3 — Đổi class nguồn.** Đổi Order thành Invoice, đổi Main để gọi InvoiceGreeting.message(). Biên dịch sạch. Stdout dự kiến:

~~~text
Generated for Invoice
~~~

Giải thích cách Elements.getPackageOf và TypeElement.getSimpleName dẫn đến tên generated class.

**Bài 4 — Validate annotation.** Gắn @GenerateGreeting lên interface để thấy NOTE/ERROR do processor quyết định. Sửa lại thành class và compile thành công.

**Bài 5 — Thử Filer collision.** Chọn tình huống hai sources làm generator nhắm cùng qualifiedName. Vì sao Filer từ chối tạo lại? Hãy đề xuất quy tắc naming tránh trùng.

**Bài 6 — Tách dependency.** Giả sử annotation API được đóng vào annotation-api.jar và processor implementation vào processor.jar. Chỉ ra vai trò của compile classpath và processor path trong stage B.

**Bài 7 — Service registration.** Nêu đường dẫn META-INF/services và dòng qualified name dùng khi auto-discovery được bật. Giải thích vì sao -processor tường minh không cần dựa vào discovery.

**Bài 8 — Options.** Thêm SupportedOptions("greeting.mode"), đọc getOptions(), validate giá trị và tạo output khác khi mode=short. Nhớ escape output text và viết test cho giá trị không hợp lệ.

## 16. Checklist kiến thức

- Hiểu annotation processor chạy lúc compile, không phải runtime Reflection.
- AbstractProcessor là base class của Processor và cung cấp processingEnv.
- init được gọi trước process và cần super.init.
- ProcessingEnvironment cung cấp Filer, Messager, Elements, Types, Options, SourceVersion và Locale.
- Element/TypeElement là khai báo; TypeMirror là kiểu; không nhầm hai mô hình.
- process có thể chạy nhiều rounds; boolean return biểu thị claim annotation.
- RoundEnvironment cho biết elements, root elements và processingOver.
- Filer tạo output một lần theo qualified name; đóng Writer và xử lý FilerException hợp lý.
- Messager giúp in diagnostic đúng chuẩn, thay vì dựa vào System.out.
- Processor class phải được compile trước để javac tải bằng -processorpath.
- -cp, -processorpath, -processor, -s và -d có vai trò khác nhau.
- Có thể xem generated source và chạy generated bytecode, nhưng cần phân biệt output compile với stdout chương trình.
- Auto-discovery/service metadata không thay thế việc cấu hình rõ processor trong mọi toolchain.
- Thiết kế production phải xét va chạm output, incremental behavior, diagnostics và kiểm thử.

### Tài liệu chuẩn để đọc sâu

- Java SE 17 API: **javax.annotation.processing.AbstractProcessor**, **Processor**, **ProcessingEnvironment**, **RoundEnvironment**, **Filer**, **Messager**.
- Java SE 17 API: **javax.lang.model.element**, **javax.lang.model.type**, **javax.lang.model.util**.
- Tài liệu chính thức **javac**: -processor, -processorpath, -proc:only, -s, -XprintRounds và compiler options liên quan.
- **JSR 269**: Pluggable Annotation Processing API.

**Ghi nhớ:** AbstractProcessor định nghĩa bộ khung processor và các callback; ProcessingEnvironment cung cấp dịch vụ làm việc với compiler; RoundEnvironment cung cấp dữ liệu của từng vòng. Khi kết hợp đúng ba thành phần với Filer, Messager và mô hình Elements/Types, bạn có thể tạo mã mới có kiểm soát ngay trong quy trình biên dịch Java.
