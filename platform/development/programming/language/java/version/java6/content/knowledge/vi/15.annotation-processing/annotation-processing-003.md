# Processor, AbstractProcessor và vòng đời xử lý Annotation Processing

## Mục tiêu học tập

Annotation processing là cơ chế của Java compiler cho phép phân tích các khai báo có annotation, kiểm tra quy tắc và tạo tệp nguồn hoặc tài nguyên **ngay lúc biên dịch**. Một annotation không tự chạy code; compiler cần được cấu hình để tìm và kích hoạt bộ xử lý (annotation processor) phù hợp.

Sau bài này, bạn có thể:

1. Phân biệt **javax.annotation.processing.Processor** và **AbstractProcessor**, cùng vai trò của **ProcessingEnvironment**, **RoundEnvironment**, **Filer**, **Messager** và mô hình **javax.lang.model**.
2. Giải thích vòng đời **khởi tạo (init) → xử lý theo các rounds (process) → final round**.
3. Hiểu **@SupportedAnnotationTypes**, **@SupportedSourceVersion** và giá trị trả về **true/false** từ **process(...)**.
4. Tạo processor Java 17+ kiểm tra annotation trên top-level class, sinh một tệp Java bằng **Filer.createSourceFile(...)** và để compiler biên dịch tệp sinh ra.
5. Cấu hình processor path, compile classpath, generated-source output, class output; quan sát rounds và chẩn đoán lỗi.
6. Thiết kế processor không tạo trùng file, biết dừng ở final round và cho kết quả tái lập.

**Phạm vi:** Chỉ sử dụng các API và tùy chọn javac còn được hỗ trợ trong Java hiện đại. Ví dụ được kiểm chứng bằng JDK 24 với tùy chọn **--release 17**, có thể thực hiện trên JDK 17 trở lên. Không sử dụng các công cụ annotation processing đã ngừng áp dụng.

## 1. Processor chạy ở đâu?

Giả sử ứng dụng có một class:

~~~java
@GenerateGreeting
public final class Hello {
    // ...
}
~~~

Một processor có thể phát hiện **@GenerateGreeting** và tạo **HelloGenerated.java** trong lúc javac đang biên dịch. Source được tạo có thể được biên dịch cùng source ban đầu và được ứng dụng tham chiếu ngay trong cùng tác vụ.

~~~text
Nguồn .java + annotation
           │
           ▼
          javac
           │
           ├── xác định processor được cấu hình
           ├── khởi tạo instance, gọi init(...)
           ├── round đầu: gọi process(...) trên khai báo được annotate
           │       └── Filer tạo HelloGenerated.java
           ├── round tiếp: phân tích source mới
           ├── round cuối: processingOver() == true
           └── biên dịch source gốc + generated source
                       │
                       ▼
                các tệp .class
~~~

Processor hoạt động trên **mô hình khai báo của compiler**, không cần chạy class đang được biên dịch. Nó thường làm việc với **Element**, **TypeElement**, **ExecutableElement**, **VariableElement** và **TypeMirror**. Điều này khác reflection lúc runtime: một class source mới chưa được tạo ra dưới dạng class JVM để gọi **Class.forName(...)**.

Annotation processing phù hợp khi cần sinh mapper/adapter, đăng ký metadata hoặc kiểm tra quy tắc tĩnh từ annotation. Nó không tự giải quyết dependency injection, không tự đóng gói JAR, không tạo sandbox cho code được sinh.

## 2. Interface Processor và AbstractProcessor

### 2.1. Processor định nghĩa hợp đồng với compiler

**javax.annotation.processing.Processor** là interface được công cụ biên dịch gọi để biết processor hỗ trợ gì, khởi tạo thế nào và xử lý một vòng ra sao.

| Phương thức | Vai trò |
| --- | --- |
| **init(ProcessingEnvironment)** | Nhận môi trường xử lý khi compiler khởi tạo processor |
| **getSupportedAnnotationTypes()** | Công bố tên đầy đủ các annotation mà processor muốn xử lý |
| **getSupportedSourceVersion()** | Công bố source version Java mới nhất mà processor hỗ trợ |
| **getSupportedOptions()** | Công bố tên các tùy chọn nhận từ compiler, chẳng hạn **-Akey=value** |
| **process(Set<? extends TypeElement>, RoundEnvironment)** | Thực hiện xử lý annotation cho một round và cho biết có claim chúng hay không |
| **getCompletions(...)** | Cho phép cung cấp gợi ý nhập giá trị annotation cho công cụ; thường không cần tùy biến |

Công cụ có thể khởi tạo processor bằng **public constructor không tham số**. Vì vậy các processor được đóng gói để javac tìm và tạo nên cung cấp constructor đó.

### 2.2. AbstractProcessor giúp viết ngắn hơn

**javax.annotation.processing.AbstractProcessor** triển khai sẵn phần lớn các phương thức trên:

- **init(...)** lưu environment vào field protected **processingEnv** và chặn việc khởi tạo cùng một instance nhiều lần.
- **getSupportedAnnotationTypes()**, **getSupportedSourceVersion()**, **getSupportedOptions()** đọc các annotation metadata trên class processor.
- **getCompletions(...)** có implementation mặc định.
- **process(...)** vẫn là phương thức abstract cần triển khai.

Vì vậy một processor thông thường nên **extends AbstractProcessor**, rồi tự định nghĩa nghiệp vụ trong **process(...)**; override **init(...)** nếu cần khởi tạo state.

Metadata mẫu:

~~~java
// Mảnh mã minh họa, không phải chương trình độc lập.
@SupportedAnnotationTypes("demo.annotations.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {
        // ...
        return true;
    }
}
~~~

**@SupportedAnnotationTypes** nhận tên đầy đủ của annotation được hỗ trợ; trong mẫu, đó là **demo.annotations.GenerateGreeting**, không phải tên class Hello hoặc tên processor. **@SupportedSourceVersion(RELEASE_17)** phù hợp ví dụ biên dịch với **--release 17**. Nếu processor được phát hành để hỗ trợ source version cao hơn, cần kiểm thử và khai báo/override phù hợp.

**Ghi chú hiện đại:** Các package **javax.annotation.processing** và **javax.lang.model** vẫn là API chuẩn của module **java.compiler**. Tiền tố **javax** trong các package này vẫn đúng; không tự chuyển sang package khác.

## 3. Vòng đời xử lý: init → nhiều rounds → kết thúc

### 3.1. init(ProcessingEnvironment) chạy khi nào?

Khi compiler đã xác định và khởi tạo processor, nó gọi **init(...)** trước khi giao annotation cần xử lý. Với AbstractProcessor, phải gọi **super.init(environment)** nếu override:

~~~java
// Mảnh mã minh họa nằm bên trong GreetingProcessor.
private Messager messager;

@Override
public synchronized void init(ProcessingEnvironment environment) {
    super.init(environment);
    messager = environment.getMessager();
}
~~~

**init được gọi một lần cho mỗi processor instance**, không phải mỗi round. Không sử dụng **processingEnv** trong constructor vì compiler chưa cung cấp environment khi đó.

State đặt trong instance có thể tồn tại qua các rounds của cùng một tác vụ; đừng lưu trạng thái toàn cục bằng static mutable field rồi vô tình chuyển dữ liệu của một lần biên dịch sang lần khác.

### 3.2. process(...) nhận hai đối số

Chữ ký:

~~~java
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv)
~~~

**annotations** là tập các annotation được giao cho processor trong vòng hiện tại. Nó không phải mọi annotation của toàn bộ dự án.

**roundEnv** cho biết các khai báo thuộc vòng đang xử lý và trạng thái vòng:

| Phương thức | Ý nghĩa |
| --- | --- |
| **getElementsAnnotatedWith(MyAnnotation.class)** | Tập khai báo được gắn annotation tương ứng trong phạm vi round |
| **getRootElements()** | Root elements ứng với các đơn vị biên dịch đầu vào của round |
| **processingOver()** | Đã đến vòng cuối, các type sinh trong vòng này sẽ không có round tiếp theo để xử lý |
| **errorRaised()** | Có lỗi được báo trong **vòng trước** (không phải cờ lỗi của vòng hiện tại) |

Một processor nên kiểm tra vòng cuối trước khi sinh tệp:

~~~java
// Mảnh mã minh họa.
@Override
public boolean process(
        Set<? extends TypeElement> annotations, RoundEnvironment round) {
    if (round.processingOver()) {
        return true;
    }
    // Phân tích các element trong vòng hiện tại và tạo output khi cần.
    return true;
}
~~~

Nếu processor đã được gọi ở một round, công cụ sẽ gọi nó tiếp ở các rounds kế tiếp, kể cả khi không còn annotation phù hợp. **annotations** có thể rỗng; code phải xử lý trường hợp đó.

### 3.3. Rounds được sinh ra như thế nào?

Một processor tạo source mới qua **Filer.createSourceFile(...)**. Compiler sẽ quét nguồn vừa được sinh trong vòng kế và tiếp tục cho đến khi không có nguồn mới để xử lý. Sau cùng có một **final round**, với **processingOver() == true**.

~~~text
Round 1: Hello.java (có @GenerateGreeting)
           └── tạo HelloGenerated.java
Round 2: HelloGenerated.java (không có annotation cần xử lý)
           └── không tạo source mới
Round 3: final round
           └── processingOver() == true
~~~

Đây là ví dụ cụ thể được quan sát trên OpenJDK 24; **số rounds không cố định**. Nếu generated source có thêm annotation phù hợp, hoặc nhiều processor sinh source nối tiếp, có thể có nhiều rounds hơn. Không ràng buộc logic nghiệp vụ vào việc “vòng 2 luôn là vòng cuối”.

Nếu một processor liên tục tạo thêm source mới qua các rounds, compiler có thể phải làm nhiều việc ngoài dự kiến. Thiết kế output ổn định và điểm dừng rõ ràng.

### 3.4. process(...) trả true hay false?

Giá trị boolean là **quyết định claim annotation**, không phải “biên dịch đã thành công”:

| Giá trị | Nghĩa |
| --- | --- |
| **true** | Processor claim các annotation được giao trong round; processor khác sẽ không tiếp tục được yêu cầu xử lý những annotation đó theo cơ chế phân phối |
| **false** | Processor không claim; những processor khác vẫn có thể được giao annotation đó |

Processor chịu trách nhiệm **sinh code** cho một annotation riêng thường trả **true**. Processor chỉ **kiểm tra/quan sát** và muốn processor khác tiếp tục xử lý có thể trả **false**.

Cẩn thận khi hỗ trợ mọi annotation bằng **"*"**: nếu luôn trả **true**, một processor đa dụng có thể claim toàn bộ annotation và vô tình cản processor khác.

**Không dùng false để báo lỗi biên dịch.** Khi gặp khai báo không hợp lệ, dùng **Messager** với **Diagnostic.Kind.ERROR** và vị trí **Element** tương ứng.

## 4. ProcessingEnvironment cung cấp những gì?

**ProcessingEnvironment** là cổng vào các tiện ích compile-time:

| API | Dùng để |
| --- | --- |
| **getFiler()** | Tạo source, class hoặc resource thuộc output của compilation |
| **getMessager()** | Gửi NOTE/WARNING/ERROR gắn với khai báo nguồn |
| **getElementUtils()** | Tra cứu class/package, thao tác và đọc cấu trúc **Element** |
| **getTypeUtils()** | Phân tích quan hệ kiểu, gán kiểu và **TypeMirror** |
| **getOptions()** | Đọc tùy chọn processor (ví dụ **-Ademo.strict=true**) |
| **getSourceVersion()** | Xem source version của môi trường xử lý |
| **getLocale()** | Xem locale hiện hành nếu có |

**javax.lang.model** mô tả chương trình đang được biên dịch:

- **Element** mô tả khai báo như package, type, method, field, parameter.
- **TypeElement** mô tả một type có tên và cấu trúc.
- **ElementKind** giúp phân biệt CLASS, INTERFACE, METHOD, RECORD...
- **NestingKind** phân biệt TOP_LEVEL, MEMBER, LOCAL, ANONYMOUS.
- **TypeMirror** biểu diễn type theo compiler; dùng **Types** để so sánh thay vì phụ thuộc vào reflection.

Trong ví dụ, processor chỉ cho phép annotation trên **top-level class**. Nó kiểm tra cả **ElementKind.CLASS** và **NestingKind.TOP_LEVEL** rồi mới tạo source.

## 5. Filer và quy tắc sinh file

Công cụ chuẩn để sinh source là **processingEnv.getFiler()**:

~~~java
// Mảnh mã minh họa: type là TypeElement nguồn.
JavaFileObject generated = processingEnv.getFiler()
        .createSourceFile("demo.app.HelloGenerated", type);
try (Writer writer = generated.openWriter()) {
    writer.write("package demo.app;\n");
    writer.write("public final class HelloGenerated {}\n");
}
~~~

**createSourceFile(...)** nhận **tên type đầy đủ (qualified name)**, không nhận tên đường dẫn vật lý. Với file manager chuẩn và option **-s build/generated**, compiler tạo vị trí tương ứng **build/generated/demo/app/HelloGenerated.java**.

**Originating element** là **type** truyền vào cuối createSourceFile; đây là khai báo làm nguồn cho generated artifact, hữu ích cho công cụ build và incremental processing.

Quy tắc cần ghi nhớ:

1. **Một tên/path được tạo một lần trong một processing run.** Cố tạo lại cùng type/file có thể ném **FilerException**, một kiểu **IOException**.
2. Không tạo một generated file có danh tính trùng source input của compiler. Các input ban đầu được xem như đã thuộc **round 0**.
3. Tên output phải ổn định và đủ duy nhất cho từng type. Với nhiều processor, cần có quy tắc ownership để không tạo trùng tên.
4. Đóng **Writer/OutputStream** sau khi tạo nội dung. Nếu lỗi I/O, báo Diagnostic.ERROR hoặc làm task thất bại rõ ràng.
5. **Không sinh source trong final round** rồi mong compiler đưa nó vào vòng xử lý mới.
6. Đừng để mọi round cùng sinh một output cố định: chỉ xử lý các element phù hợp và kiểm soát generated names.

**-s** là thư mục source do processor sinh; **-d** là đích class output. Tài nguyên khác sinh qua **Filer.createResource(...)** có kiểu và vị trí riêng.

## 6. Ví dụ hoàn chỉnh Java 17+: processor tạo HelloGenerated

Ví dụ có **3 file source viết tay**. Khi compiler xử lý class **Hello**, processor sinh thêm **HelloGenerated.java** và javac biên dịch cả hai. Không dùng thư viện ngoài JDK.

### 6.1. Cấu trúc trước khi chạy

~~~text
annotation-demo/
└── src/
    └── demo/
        ├── annotations/GenerateGreeting.java
        ├── processor/GreetingProcessor.java
        └── app/Hello.java
~~~

Tạo các file tại đúng đường dẫn tương ứng, rồi chạy lệnh ở thư mục **annotation-demo**.

### 6.2. Định nghĩa annotation

**src/demo/annotations/GenerateGreeting.java**

~~~java
package demo.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateGreeting {}
~~~

Annotation **@Retention(SOURCE)** thích hợp khi mục đích chỉ là xử lý ở compile time, không cần giữ annotation để đọc bằng reflection lúc chạy. **@Target(TYPE)** cho phép nhiều loại type; processor sẽ kiểm tra chặt hơn, chỉ nhận top-level class.

### 6.3. Viết processor

**src/demo/processor/GreetingProcessor.java**

~~~java
package demo.processor;

import demo.annotations.GenerateGreeting;
import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.Messager;
import javax.annotation.processing.ProcessingEnvironment;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.NestingKind;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.annotations.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    private Messager messager;

    public GreetingProcessor() {}

    @Override
    public synchronized void init(ProcessingEnvironment environment) {
        super.init(environment);
        messager = environment.getMessager();
    }

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations, RoundEnvironment round) {
        if (round.processingOver()) {
            return true;
        }

        for (Element element : round.getElementsAnnotatedWith(
                GenerateGreeting.class)) {
            if (element.getKind() != ElementKind.CLASS
                    || ((TypeElement) element).getNestingKind()
                    != NestingKind.TOP_LEVEL) {
                messager.printMessage(Diagnostic.Kind.ERROR,
                        "@GenerateGreeting requires a top-level class", element);
                continue;
            }

            TypeElement type = (TypeElement) element;
            String pkg = processingEnv.getElementUtils()
                    .getPackageOf(type).getQualifiedName().toString();
            String generatedName = type.getSimpleName() + "Generated";
            String fullName = pkg.isEmpty()
                    ? generatedName : pkg + "." + generatedName;

            try {
                JavaFileObject output = processingEnv.getFiler()
                        .createSourceFile(fullName, type);
                try (Writer writer = output.openWriter()) {
                    if (!pkg.isEmpty()) {
                        writer.write("package " + pkg + ";\n\n");
                    }
                    writer.write("public final class " + generatedName + " {\n");
                    writer.write("    private " + generatedName + "() {}\n");
                    writer.write("    public static String message() {\n");
                    writer.write("        return \"Hello, generated!\";\n");
                    writer.write("    }\n");
                    writer.write("}\n");
                }
            } catch (IOException error) {
                messager.printMessage(Diagnostic.Kind.ERROR,
                        "Cannot create " + fullName + ": " + error.getMessage(),
                        element);
            }
        }
        return true;
    }
}
~~~

Phân tích code:

- Constructor **public** cho phép tool khởi tạo processor.
- **init(...)** gọi super rồi lưu **Messager**; **processingEnv** được dùng trong process để lấy **Elements** và **Filer**.
- **processingOver()** được kiểm tra trước khi sinh output, tránh tạo code ở vòng cuối.
- **getElementsAnnotatedWith(GenerateGreeting.class)** chỉ xét những khai báo tương ứng trong round hiện tại.
- Processor báo **ERROR** khi annotation không đặt trên top-level class.
- Tên output lấy từ package và simple name của class nguồn: **demo.app.Hello** → **demo.app.HelloGenerated**.
- **createSourceFile(fullName, type)** gắn originating element và tạo tệp nguồn; try-with-resources đảm bảo Writer được đóng.
- **return true** claim annotation **GenerateGreeting** sau khi xử lý, không có nghĩa task chắc chắn thành công.

### 6.4. Viết class sử dụng generated code

**src/demo/app/Hello.java**

~~~java
package demo.app;

import demo.annotations.GenerateGreeting;

@GenerateGreeting
public final class Hello {
    public static void main(String[] args) {
        System.out.println(HelloGenerated.message());
    }
}
~~~

Khi viết file, **HelloGenerated** chưa tồn tại. Compiler chỉ tìm được nó khi processor chạy thành công và generated source được đưa vào cùng tác vụ.

### 6.5. Biên dịch và chạy (Bash/Linux/macOS)

Tại thư mục gốc **annotation-demo**, dùng JDK 17+:

~~~bash
mkdir -p build/processor build/classes build/generated

javac -encoding UTF-8 --release 17 -d build/processor \
  src/demo/annotations/GenerateGreeting.java \
  src/demo/processor/GreetingProcessor.java

javac -encoding UTF-8 --release 17 \
  -cp build/processor \
  -processorpath build/processor \
  -processor demo.processor.GreetingProcessor \
  -s build/generated \
  -d build/classes \
  src/demo/app/Hello.java

java -cp "build/classes:build/processor" demo.app.Hello
~~~

**Stdout của lệnh java cuối cùng:**

~~~text
Hello, generated!
~~~

Lúc không có lỗi/cảnh báo và chưa bật diagnostic flags, các lệnh **javac** thường không in thông tin thành công.

### 6.6. Lệnh tương ứng trên Windows PowerShell

Dấu phân cách classpath của Windows là **;**, các lệnh javac có thể viết trên một dòng:

~~~powershell
New-Item -ItemType Directory -Force build/processor,build/classes,build/generated | Out-Null
javac -encoding UTF-8 --release 17 -d build/processor src/demo/annotations/GenerateGreeting.java src/demo/processor/GreetingProcessor.java
javac -encoding UTF-8 --release 17 -cp build/processor -processorpath build/processor -processor demo.processor.GreetingProcessor -s build/generated -d build/classes src/demo/app/Hello.java
java -cp "build/classes;build/processor" demo.app.Hello
~~~

**Stdout:** vẫn là **Hello, generated!**.

### 6.7. Các file được tạo

Sau khi chạy:

~~~text
build/
├── processor/
│   └── demo/
│       ├── annotations/GenerateGreeting.class
│       └── processor/GreetingProcessor.class
├── generated/
│   └── demo/app/HelloGenerated.java
└── classes/
    └── demo/app/
        ├── Hello.class
        └── HelloGenerated.class
~~~

Nội dung của **HelloGenerated.java**:

~~~java
package demo.app;

public final class HelloGenerated {
    private HelloGenerated() {}
    public static String message() {
        return "Hello, generated!";
    }
}
~~~

**Kiểm chứng thực tế:** ví dụ đã biên dịch và chạy với OpenJDK 24.0.2 và **--release 17**. File **HelloGenerated.java**, **HelloGenerated.class** đều được tạo; stdout chính xác là **Hello, generated!**.

Chú ý cách tổ chức đường dẫn:

- **build/processor** chứa lớp processor và annotation. **-processorpath** để nạp processor cùng dependency của nó.
- **-cp build/processor** để mã **Hello.java** phân giải import annotation.
- **-s build/generated** lưu Java source do processor tạo qua Filer.
- **-d build/classes** lưu bytecode của các lớp ứng dụng, bao gồm generated class.
- **java -cp** thiết lập runtime classpath. Tài nguyên cần tại runtime phụ thuộc code đã biên dịch; processor path và runtime classpath là hai khái niệm riêng.

## 7. Quan sát các rounds bằng -XprintRounds

Chạy lại bước compile ứng dụng và thêm **-XprintRounds**:

~~~bash
javac -encoding UTF-8 --release 17 \
  -XprintRounds \
  -cp build/processor \
  -processorpath build/processor \
  -processor demo.processor.GreetingProcessor \
  -s build/generated -d build/classes \
  src/demo/app/Hello.java
~~~

OpenJDK 24.0.2 hiển thị thông tin rounds như sau (khoảng trắng/cách định dạng có thể phụ thuộc JDK):

~~~text
Round 1:
    input files: {demo.app.Hello}
    annotations: [demo.annotations.GenerateGreeting]
    last round: false
Round 2:
    input files: {demo.app.HelloGenerated}
    annotations: []
    last round: false
Round 3:
    input files: {}
    annotations: []
    last round: true
~~~

Đây là **diagnostic output của javac**, không phải stdout của chương trình Hello. Diễn giải:

1. **Round 1**: class **Hello** có annotation, processor tạo **HelloGenerated.java**.
2. **Round 2**: source vừa tạo được xét; không có annotation phù hợp nên processor không tạo thêm file.
3. **Round 3**: final round; **processingOver() == true**, processor không sinh source nữa.
4. Sau processing, javac biên dịch các source theo cấu hình, tạo **.class**.

**-XprintProcessorInfo** cũng hữu ích khi cần biết processor nào chạy và claim annotation nào. Không dùng văn bản này làm dữ liệu đầu ra nghiệp vụ cố định vì định dạng phụ thuộc tool/JDK.

## 8. Kích hoạt processor trên JDK hiện đại

### 8.1. Cấu hình tường minh

Lệnh ví dụ dùng **-processor demo.processor.GreetingProcessor**: javac biết chính xác processor cần gọi, dù không có service descriptor.

Các option quan trọng:

| Option | Ý nghĩa |
| --- | --- |
| **-processor p.Name** | Chỉ định các processor cần chạy |
| **-processorpath / --processor-path** | Nơi tìm lớp và dependency của processor |
| **--processor-module-path** | Nơi tìm processor được đóng gói theo named modules |
| **-classpath / -cp** | Nơi tìm dependency cho source đang biên dịch |
| **-s dir** | Đích generated source |
| **-d dir** | Đích bytecode |
| **-proc:full** | Chạy annotation processing và biên dịch |
| **-proc:only** | Chỉ chạy processing, không thực hiện compile bytecode thông thường sau đó |
| **-proc:none** | Tắt annotation processing |
| **--release 17** | Chọn source/API và bytecode tương thích Java 17 |
| **-XprintRounds**, **-XprintProcessorInfo** | In thông tin chẩn đoán |

**Không dựa vào tự kích hoạt ngầm.** Các JDK hiện đại yêu cầu cấu hình processing rõ ràng; việc một processor JAR xuất hiện tình cờ trên classpath không đồng nghĩa processor sẽ chạy. Khai báo **-processor**, processor path hoặc cấu hình annotation processing của build tool tương ứng. Điều này đặc biệt quan trọng khi chuyển từ các JDK cũ sang JDK 23 trở lên.

### 8.2. Khám phá processor bằng service descriptor

Nếu không muốn truyền **-processor** thủ công, cách đăng ký qua service provider vẫn còn được hỗ trợ. Provider JAR chứa resource:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nội dung:

~~~text
demo.processor.GreetingProcessor
~~~

Khi annotation processing được cấu hình và processor path chứa JAR này, javac có thể khám phá processor tương ứng. Đảm bảo descriptor nằm trong artifact cuối cùng, không bị mất khi đóng gói/shading. Nếu sử dụng **named modules**, có thể khai báo **provides javax.annotation.processing.Processor with ...** và đặt processor trên module path thích hợp.

Ví dụ của bài dùng **-processor tường minh**, nên không cần tạo descriptor này để chạy.

### 8.3. JavaCompiler API cũng có thể gọi processor

Trong ứng dụng dùng **javax.tools.JavaCompiler**, bạn có thể truyền options cho **CompilationTask** hoặc dùng **CompilationTask.setProcessors(...)** để cấp các **Processor instances** trước khi gọi **call()**.

Ví dụ options **minh họa, không phải chương trình độc lập**:

~~~java
List<String> options = List.of(
        "--release", "17",
        "-processorpath", "build/processor",
        "-processor", "demo.processor.GreetingProcessor",
        "-s", "build/generated",
        "-d", "build/classes");
~~~

Hãy xem việc nạp processor và việc phân giải classpath của source là hai phạm vi: processor chạy trong môi trường công cụ; source được kiểm tra trong môi trường compile. **-processorpath** không tự thay thế **-cp** khi source import type từ annotation API.

## 9. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| **cannot find symbol: HelloGenerated** | Processor không chạy, không match annotation hoặc không sinh source thành công | Kiểm tra option **-processor**, **@SupportedAnnotationTypes**, processor path và generated directory |
| **Annotation processor '...' not found** | Sai full class name, thiếu class/JAR hoặc dependency trên processor path | Kiểm tra package, constructor, vị trí artifact và dependency |
| Build lên JDK mới thì processor không chạy | Dựa vào kích hoạt processing ngầm của JDK trước | Cấu hình processing/processor dependencies tường minh |
| **Attempt to recreate a file for type ...** | Hai round/processor cố tạo cùng type trong cùng processing run | Kiểm soát generated names và ownership; không tạo lặp |
| **FilerException** | Trùng source input/generated type hoặc file path | Đảm bảo mỗi tên nguồn được tạo một lần |
| Processor được gọi nhưng không tạo source | Không có annotated element trong round, hoặc là final round | Xem **-XprintRounds**, matching annotation và **processingOver()** |
| Annotation đặt sai loại khai báo | Điều kiện validation không thỏa | Báo Diagnostic.Kind.ERROR gắn với element thay vì crash |
| Processor ném exception | Lỗi code processor hoặc dependency lúc compile | Đọc stack trace/root cause, kiểm thử riêng processor |
| Generated .java có nhưng thiếu .class | Compilation không thành công hoặc đang dùng **-proc:only** | Đọc compiler diagnostics, kiểm tra **-d**, **-proc** |
| Processor chạy lặp nhưng output bị trùng | Không phân biệt các rounds, tên output cố định | Chỉ sinh cho element mới, theo dõi các tên đã tạo |
| IDE chạy được nhưng CI lỗi | Khác JDK/processor path/classpath/flags | Ghim cấu hình trong build và kiểm thử bằng CLI |
| **Supported source version ... less than -source ...** | Processor tuyên bố hỗ trợ source thấp hơn mức javac dùng | Cập nhật và kiểm thử processor trước khi tăng version hỗ trợ |

### Báo lỗi đúng chỗ bằng Messager

Khi annotation được đặt sai hoặc thiếu điều kiện, dùng Diagnostic.ERROR:

~~~java
// Mảnh code minh họa; cần messager và Element element.
messager.printMessage(
        Diagnostic.Kind.ERROR,
        "Annotation requires a top-level class",
        element);
~~~

Error được gắn với element giúp javac hiển thị lỗi tại vị trí nguồn. **roundEnv.errorRaised()** ở vòng sau có thể cho biết đã có ERROR ở vòng trước.

Nếu Filer ném IOException, ví dụ bắt lỗi và báo **Diagnostic.Kind.ERROR**. Đừng nuốt lỗi rồi báo build thành công giả; cũng đừng dùng **return false** để thay cho diagnostic.

### Lỗi trùng file: không được suy ra rằng retry sẽ ổn

Filer quản lý tên type/path trong phạm vi một processing run. Nhiều lần tạo cùng tên có thể ném FilerException, kể cả giữa hai processor. Không retry ghi đè mù quáng. Hãy kiểm tra:

- Tên class được sinh có đủ package và đủ duy nhất chưa?
- Có nhiều source class cùng tạo một generated class name không?
- Processor có lặp lại việc sinh output cũ ở round sau không?
- Có processor khác tạo cùng type không?
- Có cố tạo file trùng một input ban đầu không?

Nếu processor cần source tổng hợp từ nhiều annotated elements, định nghĩa cách gom input và tạo artifact **một lần** với originating elements thích hợp.

## 10. Thiết kế processor trong dự án thực tế

### 10.1. Phân tách các pha

Một processor có thể tách thành:

~~~text
RoundEnvironment
      │
      ▼
thu thập annotated elements
      │
      ▼
validate (Element/TypeMirror)
      │
      ▼
xây model trung gian
      │
      ▼
tạo source text ổn định
      │
      ▼
Filer.createSourceFile(...)
      │
      ▼
Messager báo ERROR/WARNING nếu cần
~~~

Khi logic đủ phức tạp, nên tách hàm validate và render để kiểm thử độc lập. **process(...)** giữ vai trò điều phối.

### 10.2. Vòng đời và dữ liệu

- Processor có thể được gọi nhiều rounds trong một compilation, vì vậy state theo compilation nên nằm trong instance và được khởi tạo trong **init(...)**.
- Tránh static mutable state dùng chung giữa nhiều compilation hoặc build tasks.
- Không phụ thuộc vào thứ tự duyệt của **Set** hay thứ tự chạy không được bảo đảm của các processor.
- Chỉ công bố artifact thành công, không giữ generated output chưa hoàn chỉnh nếu javac đã báo lỗi.
- Truyền originating elements tương ứng vào Filer, giúp các công cụ incremental build hiểu đầu vào liên quan.
- Dùng generated names ổn định để cùng input tạo cùng output; kiểm thử build lặp để tránh stale/generated code sai.

### 10.3. Tương thích Java

**@SupportedSourceVersion** của processor và **--release** của source được biên dịch liên quan nhưng không đồng nhất. Processor là code Java được **thực thi trong JVM chạy javac**; source ứng dụng được kiểm tra theo **--release**. Nếu processor được biên dịch cho Java 21 nhưng CI chỉ có JDK 17, chỉ đổi **--release** của ứng dụng sẽ không giúp load processor.

Khi source được biên dịch theo **named modules (JPMS)**, phải kiểm tra module path, package/module của generated type và vị trí output phù hợp. Ví dụ ở đây cố ý dùng classpath để tập trung vào lifecycle cơ bản.

### 10.4. Bảo mật

Annotation processor chạy code trong **môi trường build**, có thể có quyền đọc source, file hệ thống hoặc mạng theo quyền của tiến trình. Processor không đáng tin cậy có thể gây tác động trước cả khi ứng dụng được phát hành.

Vì vậy hãy kiểm soát nguồn JAR processor, dependency và phiên bản; giới hạn quyền/mạng của CI theo chính sách; không in bí mật vào diagnostics; kiểm soát kích thước output và các vòng sinh code.

**Lựa chọn processor tường minh** giúp dễ kiểm toán, nhưng không tự tạo sandbox. Không coi generated source là đáng tin chỉ vì nó được tạo trong compiler.

## 11. Kiểm thử có ý nghĩa

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| Top-level class có annotation | Generated source và compiled class tồn tại, chương trình gọi được |
| Không có annotation | Không sinh type ngoài hợp đồng |
| Annotation gắn vào interface | Có Diagnostic.ERROR đúng element |
| Annotation gắn vào nested class | Có Diagnostic.ERROR |
| Hai class khác tên cùng package | Generated names duy nhất, không trùng output |
| Hai processor tạo cùng qualified name | Compiler báo xung đột Filer |
| **-proc:none** | Processor không chạy; nếu consumer dùng generated type thì compile thất bại |
| **-proc:only** | Processing có thể sinh .java, nhưng không biên dịch .class thông thường |
| Thiếu processor trên processor path | Compiler báo lỗi nạp processor |
| Build lại cùng source | Generated code/diagnostics ổn định và không phụ thuộc vào output cũ |

Có thể dùng **JavaCompiler API** và **DiagnosticCollector** để xây kiểm thử compile có chủ đích, rồi xác minh nội dung output và lỗi. Với dự án thật, cần thêm kiểm thử biên dịch **artifact processor đã đóng gói**, bởi cấu hình discovery/path có thể khác khi chạy trong IDE và CI.

## 12. Bài tập

1. Tạo hai top-level class khác package cùng có **@GenerateGreeting**. Kiểm tra hai generated class được tạo theo package tương ứng.
2. Gắn annotation vào nested class và vào interface; quan sát thông báo lỗi rồi giải thích vì sao processor không sinh code.
3. Bật đồng thời **-XprintRounds** và **-XprintProcessorInfo**. Giải thích khi nào annotation set rỗng và vì sao processor vẫn có thể được gọi.
4. Thử đổi **return true** thành **return false** và thêm một processor giám sát; quan sát cơ chế claim.
5. Cố tình để hai annotated types sinh cùng generated qualified name và tìm nguyên nhân FilerException.
6. Thử **-proc:only** và **-proc:none** riêng, đối chiếu số file generated source/class.
7. Viết compile test xác nhận **HelloGenerated.java** được sinh, **HelloGenerated.class** xuất hiện khi compile thành công và chương trình in đúng **Hello, generated!**.

## Ghi nhớ

**Processor** là hợp đồng; **AbstractProcessor** giúp triển khai gọn; **ProcessingEnvironment** cung cấp Filer, Messager và tiện ích mô hình source. **init(...)** chạy một lần cho processor instance, **process(...)** có thể chạy qua nhiều rounds; **processingOver()** đánh dấu vòng cuối. **return true** chỉ claim annotation, còn lỗi nên được báo bằng **Diagnostic.ERROR**. Generated source phải có tên duy nhất, tạo theo contract của Filer, và processor cần được cấu hình rõ ràng trong JDK hiện đại.

**Tài liệu chính thức để đối chiếu:**

- [Processor — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/Processor.html)
- [AbstractProcessor — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html)
- [RoundEnvironment — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html)
- [ProcessingEnvironment — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html)
- [Filer — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/Filer.html)
- [javac và annotation processing — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)