# Đăng ký annotation processor trong hệ mô-đun Java (JPMS)

Từ Java 9, **Java Platform Module System (JPMS)** cho phép đóng gói một annotation processor thành **named module** và công bố nó như một **service provider**. Thay vì chỉ đặt tên lớp processor trong tệp **META-INF/services**, mô-đun cung cấp processor khai báo trong **module-info.java**:

~~~java
module demo.processor {
    requires java.compiler;

    provides javax.annotation.processing.Processor
        with demo.proc.GreetingProcessor;
}
~~~

Khi được cấu hình với **--processor-module-path**, công cụ **javac** có thể khám phá và nạp processor từ mô-đun đã công bố service. Điều này không đồng nghĩa ứng dụng phải phụ thuộc runtime vào module processor. Processor chạy trong quá trình biên dịch, còn ứng dụng được biên dịch có mô-đun và module path riêng.

Bài này trình bày đầy đủ cách đăng ký, đóng gói và thực thi processor trong JPMS, các tùy chọn của javac, sự khác biệt với classpath truyền thống và một ví dụ **Java 17+ đã kiểm chứng bằng biên dịch/chạy thực tế ở chế độ --release 17**.

## 1. Ba khái niệm cần phân biệt

**Annotation type** là kiểu được khai báo bằng **@interface** và gắn trên mã nguồn, chẳng hạn **@GenerateGreeting**.

**Annotation processor** là một class triển khai **javax.annotation.processing.Processor**, thường kế thừa **AbstractProcessor**. Nó nhận mô hình khai báo/kiểu từ compiler, phân tích annotation và có thể sinh source hoặc báo diagnostic.

**Named module** là đơn vị mô-đun có tên, được khai báo bằng **module-info.java**. JPMS xác định dependency và service provider qua các directive như **requires**, **exports**, **uses** và **provides**.

Một dự án có thể tách các vai trò này như sau:

~~~text
demo.annotations                    demo.processor
  khai báo @GenerateGreeting          triển khai GreetingProcessor
  exports demo.api                    requires java.compiler
          │                           provides Processor with ...
          ▼                                      │
demo.app                                         │
  requires demo.annotations                      │
  dùng @GenerateGreeting                         │
          │                                      │
          └──────── javac khi biên dịch ─────────┘
                        │
                Processor tạo source
                        │
           demo.generated.Greeting
           thuộc module demo.app
~~~

**Không có quan hệ \`requires demo.processor\` bắt buộc trong module demo.app.** Thư viện annotation và processor là hai vai trò khác nhau. Ứng dụng cần nhìn thấy kiểu **@GenerateGreeting** lúc biên dịch, nhưng processor được **javac** nạp từ một đường dẫn riêng của môi trường build.

Trong ví dụ này, chúng ta đặt cả ba vai trò vào ba named modules để giải thích rõ ranh giới. Với dự án nhỏ, bạn cũng có thể đặt annotation type và processor chung module, miễn khai báo dependency và service đúng.

## 2. module-info.java của processor: requires và provides

Một module processor tối thiểu:

~~~java
module demo.processor {
    requires java.compiler;

    provides javax.annotation.processing.Processor
        with demo.proc.GreetingProcessor;
}
~~~

Giải thích từng thành phần:

- **module demo.processor**: tên của named module chứa class triển khai processor.
- **requires java.compiler**: cho phép module sử dụng API được module chuẩn **java.compiler** xuất ra: **javax.annotation.processing**, **javax.lang.model**, **javax.tools**.
- **provides javax.annotation.processing.Processor with demo.proc.GreetingProcessor**: công bố **GreetingProcessor** là nhà cung cấp cho service **Processor**; cơ chế tìm service trong môi trường compiler có thể khám phá nó.
- **demo.proc.GreetingProcessor** phải thực sự được định nghĩa trong module **demo.processor** và đáp ứng hợp đồng Processor.
- Với class processor thông thường, nó cần là **public class** có **public no-argument constructor** (constructor mặc định public nếu class public không khai báo constructor khác). **AbstractProcessor** cung cấp phần lớn khung triển khai.

**Không cần \`exports demo.proc\` chỉ để công bố processor qua \`provides\`.** JPMS cho phép service provider được khai báo trong module mà không phải export package triển khai cho các module sử dụng bình thường.

Phân biệt:

~~~java
// Đúng cho module có triển khai processor:
provides javax.annotation.processing.Processor
    with demo.proc.GreetingProcessor;

// Không thay thế được provides:
// exports demo.proc;
~~~

**exports** cho phép module khác truy cập public types trong package theo quan hệ module readability thông thường. **provides** đăng ký một **service provider** để cơ chế service loading tìm được. Chúng là hai chức năng khác nhau.

### Vì sao requires java.compiler chứ không phải requires jdk.compiler?

**java.compiler** là module chứa **API công khai** dành cho annotation processing và language model. **jdk.compiler** là module chứa triển khai/compiler tooling như javac. Một processor chỉ dùng các API chuẩn **javax.annotation.processing** và **javax.lang.model** thường cần **requires java.compiler**, không cần phụ thuộc vào các API nội bộ của javac.

Nếu khai báo sai module dependency, compilation của module processor có thể báo package không visible hoặc không có quyền truy cập. Nên ưu tiên API chuẩn thay vì import lớp nội bộ **com.sun.tools.javac.*** chỉ vì processor được chạy bởi javac.

## 3. Đăng ký module processor khác service file truyền thống như thế nào?

Trước JPMS và với processor chạy trên **classpath/processor path** truyền thống, service discovery thường dựa vào resource:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nội dung là tên đầy đủ của class provider:

~~~text
demo.proc.GreetingProcessor
~~~

Với **named module được nạp bằng processor module path**, cơ chế đăng ký thích hợp là directive **provides ... with ...** trong **module-info.java**. Không cần tệp META-INF/services đó trong ví dụ module processor của bài.

| Tiêu chí | Processor classpath truyền thống | Processor named module |
| --- | --- | --- |
| Cách công bố service | **META-INF/services/javax.annotation.processing.Processor** | **provides ... with ...** trong module-info.java |
| Cách chỉ đường cho javac | **-processorpath** hoặc **--processor-path** | **--processor-module-path** |
| Dependency API xử lý annotation | java.compiler có trên JDK; classpath không khai báo requires | **requires java.compiler** |
| Ranh giới đóng gói | Unnamed module / classpath truyền thống | Named module có descriptor |
| Nơi chứa provider | Class được nạp từ processor path | Class provider thuộc module đã công bố |
| Có cần ứng dụng requires processor? | Không | Không |

Chỉ tồn tại một **module-info.java** trong một JAR không đủ để bảo đảm javac tự khám phá processor. **Phải khai báo provides đúng kiểu service và class implementation, và cấu hình đúng processor module path.**

### Đừng nhầm bốn đường dẫn

**--module-path** (hoặc **-p**) phục vụ việc phân giải **module mà chương trình đang được biên dịch phụ thuộc vào**.

**--processor-module-path** phục vụ việc tìm **processor trong named module** để javac nạp và thực thi trong phiên biên dịch.

**--processor-path** phục vụ tìm **processor theo cơ chế classpath/unnamed module**.

**--class-path** là đường dẫn theo cơ chế classpath truyền thống cho kiểu của ứng dụng; trong một số cấu hình cũ, nó còn là đường tìm processor nếu không có processor path riêng.

Một named module processor được xây dựng đúng mà lại chỉ đưa vào **--module-path** của ứng dụng **không bảo đảm javac sẽ khám phá và chạy nó**. Cũng không nên đưa runtime dependency của ứng dụng vào processor path một cách tùy tiện; hai môi trường có mục đích khác nhau.

## 4. Ví dụ Java 17+ hoàn chỉnh: ba named modules và một processor được tự khám phá

Thí nghiệm dùng:

- **demo.annotations**: module công khai annotation **@GenerateGreeting**.
- **demo.processor**: module chứa **GreetingProcessor** đăng ký bằng **provides**.
- **demo.app**: module ứng dụng dùng annotation và class **Greeting** được processor sinh ra.

Processor sinh **demo.generated.Greeting** với một hằng **TEXT**. Module ứng dụng gọi hằng này lúc chạy. Như vậy, việc javac tự khám phá processor có thể được quan sát qua **tệp source được sinh và stdout**; không cần dựa vào tên class nội bộ của javac.

### 4.1. Cấu trúc thư mục source

~~~text
project/
└── src/
    ├── annotations/
    │   ├── module-info.java
    │   └── demo/
    │       └── api/
    │           └── GenerateGreeting.java
    ├── processor/
    │   ├── module-info.java
    │   └── demo/
    │       └── proc/
    │           └── GreetingProcessor.java
    └── app/
        ├── module-info.java
        └── demo/
            └── app/
                └── Main.java
~~~

Ở đây **src/annotations**, **src/processor** và **src/app** là **tên thư mục quản lý source do ví dụ lựa chọn**; tên module thực tế được xác định bởi **module-info.java**, lần lượt là **demo.annotations**, **demo.processor**, **demo.app**.

### 4.2. Module chứa annotation type

**Tệp src/annotations/module-info.java:**

~~~java
module demo.annotations {
    exports demo.api;
}
~~~

**Tệp src/annotations/demo/api/GenerateGreeting.java:**

~~~java
package demo.api;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateGreeting {
}
~~~

**exports demo.api** cho phép module demo.app sử dụng public annotation type **demo.api.GenerateGreeting**. **@Target(TYPE)** cho phép gắn trên khai báo class. **@Retention(SOURCE)** đủ cho processor đọc trong quá trình biên dịch source, nhưng annotation không được giữ trong class file để reflection runtime đọc.

Module **demo.annotations** không cần **requires java.compiler**, vì mã của annotation này chỉ dùng package **java.lang.annotation**, thuộc **java.base**, vốn được mọi module đọc ngầm định.

### 4.3. Module chứa processor và service registration

**Tệp src/processor/module-info.java:**

~~~java
module demo.processor {
    requires java.compiler;

    provides javax.annotation.processing.Processor
        with demo.proc.GreetingProcessor;
}
~~~

**Tệp src/processor/demo/proc/GreetingProcessor.java:**

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
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.api.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {

        if (round.processingOver() || generated) {
            return true;
        }

        for (TypeElement annotation : annotations) {
            for (Element element :
                    round.getElementsAnnotatedWith(annotation)) {

                try {
                    JavaFileObject file = processingEnv.getFiler()
                            .createSourceFile(
                                    "demo.app/demo.generated.Greeting",
                                    element);

                    try (Writer writer = file.openWriter()) {
                        writer.write("package demo.generated;\n");
                        writer.write("public final class Greeting {\n");
                        writer.write("  private Greeting() {}\n");
                        writer.write(
                                "  public static final String TEXT = "
                                + "\"generated by demo.processor\";\n");
                        writer.write("}\n");
                    }

                    generated = true;
                    return true;

                } catch (IOException ex) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "Generation failed: " + ex.getMessage(),
                            element);
                    return true;
                }
            }
        }

        return true;
    }
}
~~~

**Ý nghĩa trong bài toán đăng ký module:**

1. **GreetingProcessor** kế thừa **AbstractProcessor**, tức có khả năng thực hiện hợp đồng service **Processor**.
2. **@SupportedAnnotationTypes("demo.api.GenerateGreeting")** khai báo annotation type mà processor quan tâm. Nó không thay thế **provides**: một bên là thông tin filter annotation, một bên là service registration.
3. **@SupportedSourceVersion(RELEASE_17)** xác định mức ngôn ngữ mà processor tuyên bố hỗ trợ.
4. **round.getElementsAnnotatedWith(annotation)** tìm các khai báo gắn **@GenerateGreeting** trong một vòng xử lý.
5. **processingEnv.getFiler().createSourceFile(...)** tạo source. Tiền tố **demo.app/** là **tên module chứa class được tạo**, cho biết đích trong trường hợp xử lý named module; phần còn lại **demo.generated.Greeting** là tên đầy đủ của kiểu được sinh.
6. **generated** ngăn việc cố sinh cùng một source nhiều lần qua các processing rounds. Processor có thể được gọi nhiều lần trong một compilation.
7. **return true** cho biết processor claim annotation types nó nhận; không phải tín hiệu thành công của lệnh java chạy ứng dụng.
8. Khi có lỗi ghi tệp, **Messager** nhận **Diagnostic.Kind.ERROR** để compiler báo lỗi có thông tin.

Ví dụ có chủ đích chỉ xử lý **một class** được gắn GenerateGreeting để bảo đảm sinh một file. Một processor dùng trong sản phẩm cần xử lý nhiều annotated elements, nhiều module đầu vào, trùng tên file, trạng thái rounds và diagnostic đầy đủ hơn.

**Không có import tới demo.api.GenerateGreeting trong processor.** Nó nhận kiểu annotation qua **TypeElement** và tên đầy đủ được khai báo trong **@SupportedAnnotationTypes**. Vì thế demo.processor không cần **requires demo.annotations**; đây là cách giữ dependency giữa processor với thư viện annotation đơn giản trong ví dụ.

### 4.4. Module ứng dụng dùng annotation

**Tệp src/app/module-info.java:**

~~~java
module demo.app {
    requires demo.annotations;
}
~~~

**Tệp src/app/demo/app/Main.java:**

~~~java
package demo.app;

import demo.api.GenerateGreeting;
import demo.generated.Greeting;

@GenerateGreeting
public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.TEXT);
    }
}
~~~

Ứng dụng có **requires demo.annotations** để nhìn thấy annotation type được export. **Không có requires demo.processor**, vì processor chỉ là công cụ build-time.

Lúc mới tạo file Main.java, class **demo.generated.Greeting** chưa có trong source do ta tự viết. Nó sẽ được processor sinh ra khi javac biên dịch ứng dụng. Đây là thí nghiệm chứng minh việc service đăng ký trong module-info.java đã được compiler nạp đúng.

### 4.5. Biên dịch theo ba bước

Trong thư mục **project**, tạo các thư mục output. Trên Linux/macOS với bash:

~~~bash
mkdir -p mods/demo.annotations mods/demo.processor mods/demo.app generated
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force mods/demo.annotations,mods/demo.processor,mods/demo.app,generated | Out-Null
~~~

**Bước A: biên dịch annotation module.**

~~~bash
javac --release 17 -proc:none -d mods/demo.annotations src/annotations/module-info.java src/annotations/demo/api/GenerateGreeting.java
~~~

Kết quả quan trọng:

~~~text
mods/demo.annotations/module-info.class
mods/demo.annotations/demo/api/GenerateGreeting.class
~~~

**-proc:none** tránh chạy annotation processing không chủ đích khi đang build những module công cụ ban đầu.

**Bước B: biên dịch processor module.**

~~~bash
javac --release 17 -proc:none -d mods/demo.processor src/processor/module-info.java src/processor/demo/proc/GreetingProcessor.java
~~~

Kết quả quan trọng:

~~~text
mods/demo.processor/module-info.class
mods/demo.processor/demo/proc/GreetingProcessor.class
~~~

Hai module đã biên dịch thành named module vì class file có **module-info.class**. Thư mục **mods** đóng vai trò một module path chứa hai module riêng, mỗi module nằm trong một thư mục con.

**Bước C: biên dịch module ứng dụng với processor module path.**

~~~bash
javac --release 17 --module-path mods --processor-module-path mods -d mods/demo.app -s generated src/app/module-info.java src/app/demo/app/Main.java
~~~

Đây là **lệnh trọng tâm**:

- **--module-path mods**: compiler phân giải **requires demo.annotations** của ứng dụng.
- **--processor-module-path mods**: compiler tìm các **named module** công bố implementation của **javax.annotation.processing.Processor**.
- Trong ví dụ, **demo.processor** có **provides**, nên được khám phá mà **không cần** ghi **-processor demo.proc.GreetingProcessor**.
- **-d mods/demo.app**: đặt class file biên dịch của ứng dụng và generated type vào module output.
- **-s generated**: đặt Java source do processor tạo vào thư mục được chỉ định.
- **--release 17**: kiểm tra source/API Java SE 17 và tạo bytecode tương ứng.

Với cấu trúc biên dịch **một module app** như ví dụ, source được tạo thường có đường dẫn:

~~~text
generated/demo/generated/Greeting.java
~~~

Và class được biên dịch vào:

~~~text
mods/demo.app/demo/generated/Greeting.class
~~~

Đừng nhầm tiền tố **demo.app/** trong tên truyền vào **Filer.createSourceFile** với một folder luôn xuất hiện trong đường dẫn vật lý của generated-src: Filer dùng tiền tố đó để **chỉ rõ named module nhận output**. Đường dẫn thực tế phụ thuộc cách javac/Filer quản lý vị trí output và chế độ biên dịch một hay nhiều module. Khi dùng cấu hình này với javac, kết quả được kiểm chứng là file **generated/demo/generated/Greeting.java**.

**Bước D: chạy ứng dụng theo module path.**

~~~bash
java --module-path mods --module demo.app/demo.app.Main
~~~

**Stdout của lệnh java:**

~~~text
generated by demo.processor
~~~

Các lệnh biên dịch không được trình bày như stdout của Main. Để quan sát javac có thật sự gọi processor, có thể tạm dùng:

~~~bash
javac --release 17 --module-path mods --processor-module-path mods -XprintProcessorInfo -d mods/demo.app -s generated src/app/module-info.java src/app/demo/app/Main.java
~~~

Tùy chọn **-XprintProcessorInfo** yêu cầu javac in thông tin về processor được chạy và annotation mà nó xử lý; output này dành cho chẩn đoán, không phải output ổn định mà ứng dụng cần kiểm thử. Nếu chạy lại, nên làm sạch **generated** và **mods/demo.app** trước để tránh nguồn cũ tồn tại hoặc file được sinh trùng.

### Kiểm chứng thực nghiệm

Ví dụ trên đã được **biên dịch và chạy thành công bằng javac/JDK 21 với --release 17**: javac phát hiện **demo.proc.GreetingProcessor** qua service registration của named module, tạo **Greeting.java**, biên dịch ứng dụng và in đúng chuỗi **generated by demo.processor**. Chế độ --release 17 là kiểm tra tương thích source/API Java 17; nếu cần bảo đảm tuyệt đối cho một bản JDK 17 cụ thể, nên chạy cùng lệnh trên toolchain triển khai thực tế.

## 5. Đóng gói processor module thành modular JAR

Đối với ứng dụng thực tế, processor thường được đóng gói dưới dạng **modular JAR**. Sau Bước B, có thể chạy:

~~~bash
mkdir -p jars
jar --create --file jars/demo.processor.jar -C mods/demo.processor .
~~~

Trên PowerShell, tạo thư mục bằng **New-Item -ItemType Directory -Force jars** trước khi chạy lệnh jar. File JAR chứa **module-info.class** và **demo/proc/GreetingProcessor.class**.

Có thể đặt JAR processor trong một thư mục dành riêng, ví dụ **processor-libs**; sau đó đổi compiler option thành:

~~~bash
javac --release 17 --module-path mods --processor-module-path jars/demo.processor.jar -d mods/demo.app -s generated src/app/module-info.java src/app/demo/app/Main.java
~~~

Đây là lựa chọn sử dụng **JAR thay cho exploded module directory**. Nếu processor phụ thuộc vào các module thư viện khác, phải đặt những module dependency cần thiết trên processor module path thích hợp để JPMS có thể resolve. Vì processor của ví dụ chỉ yêu cầu **java.compiler** (module thuộc JDK), JAR chứa processor là đủ để tải service.

**Lưu ý môi trường:** Nếu đã chạy Bước C và generated/class outputs còn tồn tại, hãy dọn output đích trước khi kiểm chứng một cấu hình đóng gói khác. Nếu không, kết quả thành công có thể chỉ phản ánh artifact còn sót chứ không chứng minh processor trong JAR được nạp lại đúng.

### Cách nhận biết JAR là named module

Có thể kiểm tra module descriptor bằng:

~~~bash
jar --describe-module --file jars/demo.processor.jar
~~~

Phần khai báo quan trọng cần nhìn thấy là **requires java.compiler** và **provides javax.annotation.processing.Processor with demo.proc.GreetingProcessor**. Tên chính xác của những dòng trình bày trong output tùy công cụ, nhưng nội dung service registration phải có.

JAR chỉ nằm trên **--module-path** của ứng dụng chưa đồng nghĩa nó là processor được chạy. Cần cấu hình **--processor-module-path** hoặc cấu hình build tool tương đương.

## 6. JPMS ServiceLoader: uses và provides khác nhau như thế nào?

Cú pháp cung cấp service:

~~~java
module demo.processor {
    requires java.compiler;
    provides javax.annotation.processing.Processor
        with demo.proc.GreetingProcessor;
}
~~~

**provides** được viết ở module **chứa provider**. Với JPMS, dịch vụ **javax.annotation.processing.Processor** được compiler/tooling tiêu thụ qua cơ chế service loading tương ứng.

Một module **tự viết để tiêu thụ service** qua **ServiceLoader.load(Processor.class)** thường cần khai báo **uses javax.annotation.processing.Processor** trong module-info.java của chính nó, tùy thiết kế và quyền đọc module. Tuy nhiên:

- **demo.app không phải service consumer** trong ví dụ: nó chỉ là module đang được biên dịch, không cần **uses Processor**.
- **demo.processor là provider**, nên dùng **provides**, không viết **uses** thay cho provides.
- **javac**/compiler infrastructure chịu trách nhiệm cơ chế phát hiện/khởi tạo processor; bạn không cần thêm **uses** vào app chỉ để javac gọi provider.

**Một nhầm lẫn phổ biến:** Đưa **uses javax.annotation.processing.Processor** vào **module-info.java** của ứng dụng không làm javac tự có processor phù hợp. Phải đăng ký provider tại module chứa processor và cấu hình đường dẫn tìm processor.

## 7. Khi nào dùng -processor tường minh?

Trong ví dụ, **--processor-module-path mods** và directive **provides** đủ để javac khám phá processor.

Trong một số dự án, có thể muốn chỉ định danh sách processor cụ thể qua:

~~~text
-processor demo.proc.GreetingProcessor
~~~

Tùy chọn **-processor** của javac chỉ rõ **tên lớp processor cần chạy**, thay vì quét các processor khả dụng theo discovery mặc định. Nó hữu ích khi muốn kiểm soát chính xác tập processor, hạn chế tác động của những provider khác trên đường tìm hoặc phục vụ chẩn đoán.

Nhưng **-processor** không sửa một module descriptor lỗi, cũng không làm những module dependency bị thiếu tự xuất hiện. Nếu processor được đóng gói dưới dạng named module, vẫn phải sử dụng cấu hình đường dẫn module tương thích để compiler có thể nạp class provider và dependency. Với bài này, nên học đường chính thống **provides + --processor-module-path** trước.

**Tùy chọn -proc:none** tắt annotation processing trong lượt compile. **-proc:only** yêu cầu chỉ thực hiện xử lý annotation mà không tạo class file cho chương trình theo quy trình biên dịch đầy đủ. Với JDK 17, khi muốn processor sinh source và chương trình vẫn được compile, sử dụng cấu hình xử lý thông thường như Bước C, không thêm -proc:only.

**-Akey=value** truyền option cho processor có khai báo/đọc tùy chọn đó qua **ProcessingEnvironment.getOptions()**. Nó không thay thế module registration. Ví dụ hiện tại không định nghĩa một tùy chọn -A riêng.

Một khác biệt liên phiên bản: các bản javac mới có thể thay đổi cách mặc định kích hoạt processor để hạn chế processor bị chạy ngoài ý muốn. Để build tái lập, nên cấu hình đường tìm processor và hành vi processing một cách tường minh theo tài liệu javac của **phiên bản JDK được sử dụng**. Ví dụ đã kiểm chứng theo chế độ **--release 17** và phát hiện provider qua **--processor-module-path**.

## 8. Processor có thể đọc annotation của named module khác như thế nào?

Ở trong processor:

~~~java
@SupportedAnnotationTypes("demo.api.GenerateGreeting")
public final class GreetingProcessor extends AbstractProcessor {
    // ...
}
~~~

Tên đầy đủ của annotation xuất hiện trong annotation-type filter. Trong ví dụ runnable, **demo.processor không có requires demo.annotations** và không import trực tiếp GenerateGreeting; nó nhận TypeElement từ compiler model.

~~~java
for (TypeElement annotation : annotations) {
    for (Element element :
            round.getElementsAnnotatedWith(annotation)) {
        // Phân tích khai báo được gắn annotation.
    }
}
~~~

Nhờ **TypeElement** và **Element**, processor có thể nhìn thấy symbol của mã đang biên dịch mà không nhất thiết có runtime dependency vào class annotation đó.

Nếu processor muốn sử dụng trực tiếp class literal **GenerateGreeting.class** trong code của chính nó, cần cung cấp annotation type cho processor lúc biên dịch và lúc nạp, đồng thời bổ sung dependency module phù hợp nếu đó là một named module. Lựa chọn này có thể hữu ích trong chương trình lớn nhưng tăng sự phụ thuộc; mô hình compiler API thường là cách linh hoạt để viết processor đọc nhiều kiểu.

**Đừng dùng reflection để cố nạp class ứng dụng chưa được biên dịch** bằng Class.forName trong processor. Khi xử lý source, khai báo có thể chưa tồn tại dưới dạng class file. Phải dùng **TypeElement**, **TypeMirror**, **AnnotationMirror** và các API liên quan.

### Sinh mã vào named module nào?

Điểm đặc thù khi sinh source trong JPMS:

~~~java
processingEnv.getFiler().createSourceFile(
    "demo.app/demo.generated.Greeting",
    originatingElement);
~~~

Chuỗi trước dấu **/** là **tên named module**; phần sau là **tên đầy đủ class cần sinh**. Việc chỉ rõ module có ích khi biên dịch nhiều named modules hoặc khi compiler không tự xác định được đích sinh mã.

Một số tình huống compiler có thể suy ra module từ **originating elements**, nhưng không nên suy đoán trong các dự án multi-module phức tạp. Nếu module name/đường source output sai, Filer có thể báo lỗi hoặc tạo mã sai chỗ. Với processor thật, cần kiểm tra Filer API và chế độ biên dịch module của build tool.

## 9. Đọc lỗi cấu hình qua triệu chứng

| Triệu chứng | Khả năng nguyên nhân | Hướng khắc phục |
| --- | --- | --- |
| Processor module biên dịch lỗi vì package **javax.annotation.processing** không visible | Thiếu **requires java.compiler** | Thêm requires vào module-info.java của processor |
| Provider đã có class nhưng processor không chạy | Thiếu **provides ... with ...**, sai service type hoặc sai processor path | Kiểm tra module descriptor và **--processor-module-path** |
| App không nhìn thấy **@GenerateGreeting** | demo.app thiếu **requires demo.annotations** hoặc demo.annotations không export package | Thêm requires/exports và đặt annotation module trên --module-path |
| App báo không tìm thấy **demo.generated.Greeting** | Processor không chạy, failed generation hoặc class generated cũ bị dọn/sai module | Kiểm tra javac diagnostic, -XprintProcessorInfo, -s và Filer |
| Viết **requires demo.processor** trong app nhưng processor vẫn không chạy | requires không đăng ký service cho javac | Sử dụng provides và processor module path |
| Chỉ thêm **META-INF/services** nhưng processor là named module trên module path | Cách công bố service không đúng trường hợp JPMS | Khai báo **provides** trong module-info |
| Chỉ viết **exports demo.proc** | exports không tương đương provides | Khai báo provides đúng service |
| Class provider không public hoặc constructor không phù hợp | Service provider không đáp ứng hợp đồng | Định nghĩa public processor có public no-arg constructor |
| Gọi **createSourceFile(...)** trùng tên ở nhiều processing rounds | Filer không cho tạo cùng tệp lặp lại | Dùng state/định danh output ổn định |
| Dùng **--processor-path** cho named modular processor nhưng kỳ vọng JPMS discovery | Đang chọn cơ chế classpath/unnamed module | Dùng **--processor-module-path** |
| Dùng **--module-path** cho processor nhưng không đặt ở processor module path | Đường phân giải module ứng dụng không phải đường tìm processor | Cấu hình rõ hai đường dẫn |
| Dùng **-proc:none** trong Bước C | Tắt annotation processing | Bỏ -proc:none khi biên dịch app |
| Tưởng processor phải ở runtime module path | Processor phục vụ build, không phải bắt buộc cho ứng dụng đã biên dịch | Tách rõ build-time và runtime |
| Thử nghiệm lặp với tệp được sinh cũ | Kết quả bị nhiễu do artifacts còn tồn tại | Dọn thư mục generated và output app trước mỗi lượt |

**Mẹo kiểm tra tuần tự:** trước tiên xác minh **module-info.class** của processor chứa provides, sau đó xác minh module xuất hiện trên **--processor-module-path**, cuối cùng kiểm tra javac có gọi processor và có tạo source mới hay không. Đừng bắt đầu bằng việc thêm hàng loạt **--add-opens**, **--add-exports** hoặc **requires** không cần thiết; chúng dễ che khuất lỗi cấu hình gốc.

## 10. Sự khác biệt giữa build-time module và runtime module

Khi **javac** xử lý ứng dụng, môi trường chạy của compiler và môi trường chương trình đang được biên dịch là **hai bối cảnh khác nhau**.

- **Processor** được thực thi bởi javac trong quá trình build. Nó cần đọc được API **java.compiler** và các module dependency của chính processor.
- **Mã ứng dụng** đang biên dịch được phân giải theo **--module-path** và các requires/exports của **demo.app**.
- **Mã generated** trong bài được sinh vào **demo.app**, rồi javac biên dịch thành class cùng module với ứng dụng.
- Khi chạy **java --module-path mods --module demo.app/demo.app.Main**, main đọc class đã sinh. Nó không gọi **GreetingProcessor.process(...)**.

Có thể triển khai runtime chỉ với module **demo.app** và module **demo.annotations** nếu ứng dụng còn khai báo requires demo.annotations. Module processor không cần được cung cấp như một dependency runtime nếu ứng dụng không tham chiếu đến nó. Tối ưu phụ thuộc runtime là một lý do phổ biến để tách annotation library và processor module.

**Lưu ý:** Annotation đã khai báo **RetentionPolicy.SOURCE** vẫn đủ để compiler và processor nhìn thấy khi xử lý source; nó không nằm trong class file để runtime reflection đọc lại. Annotation processor không đồng nghĩa với reflection runtime, dù cả hai cùng liên quan annotation.

## 11. Ghi nhớ khi dùng Maven, Gradle và IDE

Với build tool, lệnh javac cụ thể thường được tạo tự động. Dù dùng Maven, Gradle hay IDE, hãy đảm bảo cùng những nguyên tắc:

1. Processor được đóng gói có **module-info.java / module-info.class** với **provides Processor with ProviderClass** chính xác, nếu chạy theo cơ chế named module.
2. Processor được đưa vào **annotation processor module path** hoặc cấu hình tương đương mà build tool thật sự truyền cho javac.
3. Các module annotation/API mà mã ứng dụng import có mặt trên **module path của compilation**, được export và yêu cầu qua **requires**.
4. Mã generated được đưa vào đúng **module** và output compilation, không bị copy nhầm sang thư mục của module processor.
5. Bật chẩn đoán processor và kiểm tra source được sinh sau một lần build sạch.
6. Build lặp phải loại bỏ artifact cũ đúng cách và không tạo trùng class/source cùng tên.

**Không chỉ nhìn thấy processor dependency trong file build rồi kết luận processor đã chạy.** Các phiên bản build tool/IDE khác nhau có tùy chọn phát hiện processor và cơ chế xử lý JPMS riêng. Hãy kiểm tra cấu hình thực tế được chuyển cho javac, đặc biệt sự khác biệt giữa processor path classpath và processor module path.

Một số dự án vẫn dùng processor theo cơ chế classpath dù code ứng dụng được build thành named module. Đây là cấu hình có thể có, nhưng **nó không tương đương với một processor được đăng ký thành named module qua provides**. Chủ đề bài này là đường JPMS chuẩn với **--processor-module-path**.

## 12. Bài tập tự kiểm tra

**Bài 1.** Trong module chứa **GreetingProcessor**, directive nào cần thiết để cung cấp processor service?

~~~java
module training.processor {
    requires java.compiler;
    provides javax.annotation.processing.Processor
        with training.proc.GreetingProcessor;
}
~~~

Đáp án: **provides ... with ...** là directive đăng ký service; **requires java.compiler** cho phép triển khai processor dùng API chuẩn.

**Bài 2.** Nếu chỉ thêm **exports training.proc**, javac có tự động khám phá GreetingProcessor trên processor module path không? **Không phải chỉ vì exports**; package được export không tự đăng ký provider. Phải có **provides** phù hợp hoặc một cơ chế chỉ định processor hợp lệ.

**Bài 3.** Vì sao module ứng dụng dùng **@GenerateGreeting** cần **requires demo.annotations**, nhưng thường không cần **requires demo.processor**? Annotation type là API mà source ứng dụng tham chiếu, còn processor là công cụ compiler nạp ở build-time từ đường dẫn riêng.

**Bài 4.** Phân biệt:

~~~text
--module-path mods
--processor-module-path mods
~~~

Cùng một giá trị đường dẫn **mods** trong thí nghiệm nhưng ý nghĩa khác nhau: dòng đầu dùng để phân giải module của chương trình đang biên dịch, dòng sau dùng để tìm các processor module được công bố qua service.

**Bài 5.** Nếu bỏ **provides** khỏi module-info.java của demo.processor rồi biên dịch lại processor và app, trong trường hợp chỉ dùng processor discovery thì hiện tượng nào có thể xuất hiện? **Processor không được tìm và gọi**, khiến class generated không tồn tại và App không phân giải được **demo.generated.Greeting**.

**Bài 6.** Nếu processor gọi **createSourceFile("demo.app/demo.generated.Greeting", element)**, phần trước dấu / có vai trò gì? Đó là **tên named module sẽ nhận source generated**; nó không phải package.

**Bài 7.** Vì sao annotation có SOURCE retention vẫn được processor dùng trong ví dụ? Vì processor làm việc với source/symbol tại compile time. SOURCE annotation không được giữ trong class file để Java reflection thông thường truy vấn lúc chạy.

**Bài 8.** Có thể nạp processor modular từ **--module-path** của app thay vì **--processor-module-path** không? Chỉ đưa processor vào đường phân giải module app không phải cách cấu hình tìm annotation processor chuẩn của ví dụ; nên dùng **--processor-module-path** để javac nạp service provider đúng vai trò.

## 13. Tài liệu chính thức và đối chiếu

- **Java SE 17 — The javac Command:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html — phần **Annotation Processing**, **--processor-module-path**, **--processor-path**, **--module-path**, **-processor**, **-s**, **-d**, **--release**, **-proc:none**, **-proc:only**.
- **Java SE 17 — Module java.compiler:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/module-summary.html — các package javax.annotation.processing, javax.lang.model và javax.tools do module này export.
- **Java SE 17 — Interface Processor:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html — hợp đồng instantiation và processing rounds.
- **Java SE 17 — Filer:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html — quy tắc tạo source và module prefix cho named modules.
- **JLS Java 17 §7.7.4 — Service Provision:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.4 — ý nghĩa **provides ... with ...** trong module declarations.
- **Java SE 17 — ServiceLoader:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html — cơ chế tìm/nạp service providers.

**Kết luận:** Với annotation processor đóng gói trong một **named module**, hãy khai báo **requires java.compiler** và **provides javax.annotation.processing.Processor with ...** trên **module-info.java** của processor; xây dựng module đó trước, rồi cấu hình **javac --processor-module-path** để tìm provider. **--module-path** giải quyết dependency của mã ứng dụng, còn processor module path giải quyết công cụ xử lý khi biên dịch. Nếu giữ hai vai trò này tách biệt, việc đăng ký và kiểm tra processor trong JPMS sẽ rõ ràng, tái lập và dễ chẩn đoán.
