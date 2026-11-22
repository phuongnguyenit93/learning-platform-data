# Tách thư viện annotation, processor và chương trình sử dụng trong Java Core

Khi xây dựng annotation processing trong Java, cách tổ chức đáng tin cậy là **tách ba trách nhiệm thành ba artifact độc lập**:

1. **Annotation API/library**: khai báo `@interface` và những kiểu API mà mã ứng dụng cần biết khi viết `@...`.
2. **Annotation processor**: công cụ **chạy trong lúc biên dịch**, đọc annotation qua Java Language Model, kiểm tra khai báo hoặc sinh mã bằng `Filer`.
3. **Consumer/application**: mã sử dụng annotation và (nếu có) mã được processor tạo ra.

Không nên đặt mọi thứ trong cùng một module rồi mong compiler tự biên dịch và chạy processor vừa được viết trong chính lần compile đó. Việc tách artifact giúp tạo **thứ tự build rõ ràng**, **classpath đúng vai trò**, **tránh vòng phụ thuộc**, dễ kiểm thử và dễ tái sử dụng processor cho nhiều ứng dụng.

Bài này dùng Java 17+ và một ví dụ thực tế gồm **2 JAR đầu vào cùng 1 ứng dụng**. Ví dụ đã được kiểm chứng với `javac --release 17`: processor tạo ra một lớp Java mới, rồi chương trình sử dụng lớp được tạo trong cùng bước biên dịch consumer.

## 1. Mục tiêu học tập

Bạn sẽ biết:

- Chia source thành `annotation-api`, `annotation-processor`, `consumer-app`, không nhầm ba artifact với ba package tùy ý.
- Xác định phụ thuộc biên dịch, phụ thuộc **processor execution** và phụ thuộc runtime.
- Hiểu vì sao processor phải được **biên dịch trước khi được nạp để xử lý** source consumer.
- Phân biệt `-cp`, `-processorpath`, `-processor`, `-s`, `-d` và `--release 17`.
- Hiểu cách `META-INF/services/javax.annotation.processing.Processor` dùng cho service discovery, khác với `@SupportedAnnotationTypes`.
- Viết processor `AbstractProcessor` đơn giản sử dụng `RoundEnvironment`, `Filer.createSourceFile(...)` và `Messager`.
- Biên dịch bằng các lệnh thủ công **trên Bash hoặc PowerShell**, rồi chạy ứng dụng có sử dụng class do processor sinh.
- Chuyển ý tưởng sang Gradle/Maven, hiểu `compileOnly`/`annotationProcessor` và nguồn gốc vòng phụ thuộc.
- Tránh các lỗi thường gặp như `ClassNotFoundException` của processor, `Annotation processor not found`, thiếu generated source, duplicate filer và compiler không thực hiện processing.

## 2. Vì sao cần tách riêng?

Giả sử thư viện có annotation:

~~~java
@GenerateMessage("Hello from compile time")
public class App {}
~~~

Mục tiêu là khi `javac` xử lý `App`, processor tạo class:

~~~java
package demo.generated;

public final class MessageInfo {
    public static final String TEXT = "Hello from compile time";

    private MessageInfo() {}
}
~~~

Và chương trình dùng class tạo ra:

~~~java
System.out.println(MessageInfo.TEXT);
~~~

Để toàn bộ quy trình hoạt động, ta cần giải quyết **ba vấn đề khác nhau**:

- Compiler phải biết `GenerateMessage` là annotation type hợp lệ khi đọc source của consumer.
- Compiler phải **tải và chạy** implementation của processor đã được biên dịch trước, cùng mọi class mà processor phụ thuộc vào.
- Compiler phải đưa source do processor tạo ra vào quá trình biên dịch consumer để `MessageInfo` tồn tại khi consumer chạy.

Nếu trộn ba trách nhiệm, những lỗi như processor chưa có class file, API chưa nằm trên processor path hoặc source sinh ra không được compile rất dễ xảy ra. Đây không phải giới hạn của annotation syntax mà là vấn đề **tổ chức build và môi trường biên dịch**.

## 3. Sơ đồ phụ thuộc đúng

~~~text
annotation-api
  └── demo.api.GenerateMessage       --> annotation-api.jar
                 ^                            ^
                 |                            |
                 | (compile API)              | (consumer compile classpath)
                 |                            |
annotation-processor                 consumer-app
  └── demo.processor.MessageProcessor     ├── demo.app.App (@GenerateMessage)
        |                                  └── demo.app.Main
        ├── implements Processor                   |
        ├── depends on annotation-api.jar         | javac loads processor
        └── produces annotation-processor.jar      v
                                            generated MessageInfo.java
                                                   |
                                                   v
                                             MessageInfo.class
                                                   |
                                                   v
                                         java demo.app.Main
~~~

Các quan hệ quan trọng:

| Artifact | Phải thấy gì khi biên dịch chính nó? | Được dùng ở giai đoạn nào? | Trách nhiệm |
| --- | --- | --- | --- |
| `annotation-api.jar` | Java standard annotation API | Consumer compile classpath, processor compile classpath và processor execution path khi cần | Khai báo contract annotation |
| `annotation-processor.jar` | `annotation-api.jar` và `java.compiler` standard API | Compiler nạp trong bước **compile consumer** | Đọc metadata, validate, sinh mã |
| `consumer-app` | Annotation API và generated types do processor tạo | Compile consumer, rồi ứng dụng chạy | Business logic và sử dụng mã sinh |

Chiều phụ thuộc mong muốn là:

~~~text
annotation-processor ---> annotation-api
consumer-app ---------> annotation-api (compile time)
compiler executing consumer --> annotation-processor (+ its dependencies)
~~~

**Không nên có** chiều `annotation-api → annotation-processor` hoặc `annotation-processor → consumer-app`. Nếu processor import class của consumer, bạn dễ tạo **dependency cycle**: muốn biên dịch app phải có processor; muốn biên dịch processor lại cần app. Trong processor, thay vì import trực tiếp class consumer, hãy dùng `TypeElement`, `Element` và những API mô hình ngôn ngữ để quan sát khai báo đang được biên dịch.

Ba artifact ở đây là **mô-đun xây dựng (build modules/projects)** theo cách gọi thực hành; ví dụ không sử dụng hệ thống Java Platform Module System và không có `module-info.java`. Nếu dùng JPMS thực sự, việc cấu hình `--module-path`/`--processor-module-path` là một biến thể cần xử lý riêng.

## 4. Thiết kế cấu trúc thư mục

Ví dụ sử dụng source tree tối giản để dễ chạy lệnh `javac`:

~~~text
annotation-example/
├── annotation-api/
│   └── src/demo/api/GenerateMessage.java
├── annotation-processor/
│   └── src/demo/processor/MessageProcessor.java
├── consumer-app/
│   └── src/demo/app/
│       ├── App.java
│       └── Main.java
└── build/                        (sinh ra trong quá trình build)
    ├── api/
    ├── processor/
    ├── app/
    ├── generated/
    ├── annotation-api.jar
    └── annotation-processor.jar
~~~

Package của mỗi class vẫn phải khớp vị trí thư mục bên dưới `src`. Một cấu trúc phổ biến hơn trong Gradle/Maven là `src/main/java/demo/...`, nhưng để chạy lệnh bằng tay trong bài, `src/demo/...` giúp ngắn gọn hơn.

Không đưa `build/` vào mã nguồn quản lý phiên bản nếu nó là output tạm: file `.class`, generated sources và JAR đầu ra thường được build lại. Khi làm dự án thực tế, nên sử dụng build tool thay vì tự duy trì hàng loạt lệnh thủ công.

## 5. Artifact 1 — thư viện annotation API

Tạo file **`annotation-api/src/demo/api/GenerateMessage.java`**:

~~~java
package demo.api;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateMessage {
    String value();
}
~~~

**Vì sao `public`?** Source consumer nằm trong package khác (`demo.app`), nên annotation type phải truy cập được từ bên ngoài package `demo.api`.

**Vì sao retention `SOURCE`?** Mục tiêu của demo là **xử lý khi biên dịch**. Compiler phân tích được annotation trong source; không cần giữ annotation ở runtime chỉ để processor tạo file. Nếu ứng dụng thật cần Reflection runtime trên annotation, có thể dùng `CLASS`/`RUNTIME` tùy nhu cầu nhưng đó là một quyết định API riêng.

**Vì sao `@Target(TYPE)`?** Annotation này chỉ được dùng trên các khai báo kiểu phù hợp, ví dụ class. `@Target` giúp compiler kiểm tra vị trí sử dụng.

Annotation API **không import processor**, không gọi `Filer`, không cần `AbstractProcessor` và không phụ thuộc business class của consumer. Đây là JAR mỏng có thể phát hành độc lập để cả processor và consumer cùng tham chiếu.

Khi consumer dùng:

~~~java
@GenerateMessage("Hello from compile time")
public class App {}
~~~

`"Hello from compile time"` là giá trị annotation element `value()`. Mã processor sẽ đọc chuỗi này lúc biên dịch và đưa nó vào generated source.

## 6. Artifact 2 — annotation processor

Tạo file **`annotation-processor/src/demo/processor/MessageProcessor.java`**:

~~~java
package demo.processor;

import demo.api.GenerateMessage;
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

@SupportedAnnotationTypes("demo.api.GenerateMessage")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class MessageProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(
            Set<? extends TypeElement> types,
            RoundEnvironment round) {

        if (round.processingOver()) {
            return false;
        }

        Set<? extends Element> marked =
                round.getElementsAnnotatedWith(GenerateMessage.class);

        if (marked.isEmpty()) {
            return false;
        }

        if (marked.size() != 1 || generated) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Demo expects exactly one marked class");
            return true;
        }

        Element element = marked.iterator().next();
        String value = element.getAnnotation(
                GenerateMessage.class).value();

        // Đơn giản hóa việc sinh Java string literal trong demo.
        if (!value.matches("[A-Za-z ]+")) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Only English letters and spaces allowed",
                    element);
            return true;
        }

        try {
            JavaFileObject output =
                    processingEnv.getFiler().createSourceFile(
                            "demo.generated.MessageInfo", element);

            try (Writer writer = output.openWriter()) {
                writer.write(
                        "package demo.generated;\n"
                        + "public final class MessageInfo {\n"
                        + "  public static final String TEXT = \""
                        + value + "\";\n"
                        + "  private MessageInfo() {}\n"
                        + "}\n");
            }
            generated = true;

        } catch (IOException exception) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Cannot generate: " + exception.getMessage(),
                    element);
        }

        return true;
    }
}
~~~

Đây là **class processor hoàn chỉnh** dùng Java 17. Những thành phần đáng chú ý:

1. `@SupportedAnnotationTypes("demo.api.GenerateMessage")` thông báo processor hỗ trợ annotation type với **tên đủ package**. Tên `demo.processor.MessageProcessor` là tên class processor, không được đặt vào `@SupportedAnnotationTypes`.
2. `@SupportedSourceVersion(SourceVersion.RELEASE_17)` công bố hỗ trợ source level 17. Nó không thay thế `javac --release 17`.
3. `AbstractProcessor` cung cấp `processingEnv`, môi trường chứa `Filer`, `Messager` và `Elements/Types`.
4. `RoundEnvironment.getElementsAnnotatedWith(...)` lấy các khai báo có `@GenerateMessage` trong **vòng processing hiện tại**.
5. `processingOver()` nhận biết vòng cuối. Processor có thể được gọi nhiều round; không nên giả định chỉ một callback.
6. `Filer.createSourceFile("demo.generated.MessageInfo", element)` tạo **source Java mới** và khai báo `element` là originating element, hữu ích cho tooling/incremental build.
7. `Writer` ghi **source code Java**, không phải trực tiếp tạo bytecode. Sau đó compiler có thể xử lý source sinh ra ở những round tiếp theo và biên dịch nó.
8. `generated` tránh cố tạo lại cùng một file trong cùng lần chạy processor. `Filer` có quy tắc không được tạo cùng tên output nhiều lần; cố làm vậy có thể gây `FilerException`.
9. `Messager` gửi diagnostics qua compiler. Khi gặp dữ liệu không hợp lệ hoặc I/O lỗi, demo báo `Diagnostic.Kind.ERROR`; đây tốt hơn việc chỉ in `System.out` hoặc nuốt exception.
10. `return true` có nghĩa processor **claim** những annotation types được cung cấp theo hợp đồng processor; không có nghĩa lệnh `java` đã chạy ứng dụng.

**Giới hạn chủ ý của demo:** Processor này chỉ hỗ trợ **đúng một class được đánh dấu** cho một đầu ra có tên cố định `demo.generated.MessageInfo`. Nếu có nhiều class `@GenerateMessage`, phải thiết kế lại tên class sinh hoặc cơ chế tổng hợp; demo báo lỗi thay vì âm thầm ghi đè. Nó cũng chỉ chấp nhận chữ cái tiếng Anh và khoảng trắng để ghép một chuỗi Java literal an toàn bằng cách đơn giản. Trong thư viện thực tế, hãy tạo/làm escape Java string literal đúng chuẩn, hoặc dùng API sinh mã, thay vì nối tùy ý dữ liệu người dùng vào source.

### Vì sao processor cần annotation API trên classpath của nó?

Trong file trên có dòng:

~~~java
import demo.api.GenerateMessage;
~~~

và phương thức:

~~~java
element.getAnnotation(GenerateMessage.class);
~~~

Do đó processor **phải thấy `GenerateMessage.class`** khi biên dịch processor và khi compiler **nạp, chạy** processor. Đây là hai thời điểm khác nhau. Ở ví dụ thủ công, ta đưa `annotation-api.jar` vào:

- `-cp` khi biên dịch `MessageProcessor.java`.
- `-processorpath` khi `javac` nạp processor để compile app.

Nếu thiếu API JAR trên processor path, lỗi có thể là `NoClassDefFoundError: demo/api/GenerateMessage` hoặc dạng lỗi loading tương ứng, dù consumer compile classpath đã có API JAR. Nguyên tắc: **processor path là class-loading environment của processor và dependencies của nó**, không chỉ là vị trí chứa một class processor.

## 7. Artifact 3 — chương trình consumer

### 7.1. `consumer-app/src/demo/app/App.java`

~~~java
package demo.app;

import demo.api.GenerateMessage;

@GenerateMessage("Hello from compile time")
public class App {}
~~~

Đây là source mà compiler/processor đọc. Class `App` không gọi `MessageProcessor` và không cần import processor implementation.

### 7.2. `consumer-app/src/demo/app/Main.java`

~~~java
package demo.app;

import demo.generated.MessageInfo;

public class Main {
    public static void main(String[] args) {
        System.out.println(MessageInfo.TEXT);
    }
}
~~~

Tại thời điểm viết source, `MessageInfo.java` **chưa tồn tại** trong source tree. Nó xuất hiện trong quá trình compile app do processor tạo ra. Vì vậy **đừng biên dịch `Main.java` riêng lẻ trước khi bật processing** rồi kết luận project bị lỗi. Một compilation task chứa cả hai source `App.java` và `Main.java`, với processor được cấu hình đúng, cho phép `javac` phân tích generated source để giải quyết `demo.generated.MessageInfo`.

Đây là một use case quan trọng của annotation processors trong thực tế: người lập trình consumer dùng những type được tạo dựa trên cấu trúc khai báo, nhưng không cần import hay gọi processor bằng mã runtime.

## 8. Build thật bằng JDK 17+: API → processor → consumer

Đứng tại thư mục gốc `annotation-example` như sơ đồ.

### 8.1. Trên Bash/Linux/macOS

~~~bash
mkdir -p build/api build/processor build/app build/generated

# 1. Biên dịch và đóng gói annotation API.
javac --release 17 -proc:none -d build/api \
  annotation-api/src/demo/api/GenerateMessage.java
jar --create --file build/annotation-api.jar -C build/api .

# 2. Biên dịch processor, phụ thuộc vào annotation API.
javac --release 17 -proc:none \
  -cp build/annotation-api.jar \
  -d build/processor \
  annotation-processor/src/demo/processor/MessageProcessor.java
jar --create --file build/annotation-processor.jar \
  -C build/processor .

# 3. Biên dịch consumer và chạy processor đã đóng gói.
javac --release 17 \
  -cp build/annotation-api.jar \
  -processorpath build/annotation-processor.jar:build/annotation-api.jar \
  -processor demo.processor.MessageProcessor \
  -s build/generated \
  -d build/app \
  consumer-app/src/demo/app/App.java \
  consumer-app/src/demo/app/Main.java

# 4. Chạy ứng dụng vừa được biên dịch.
java -cp build/app:build/annotation-api.jar demo.app.Main
~~~

Dấu `\` dùng để nối dòng theo Bash/POSIX. Trên Windows cần dấu phân cách classpath/processorpath `;`, không phải `:`.

### 8.2. Trên Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force build/api,build/processor,build/app,build/generated

javac --release 17 -proc:none -d build/api annotation-api/src/demo/api/GenerateMessage.java
jar --create --file build/annotation-api.jar -C build/api .

javac --release 17 -proc:none -cp build/annotation-api.jar -d build/processor annotation-processor/src/demo/processor/MessageProcessor.java
jar --create --file build/annotation-processor.jar -C build/processor .

javac --release 17 -cp build/annotation-api.jar -processorpath "build/annotation-processor.jar;build/annotation-api.jar" -processor demo.processor.MessageProcessor -s build/generated -d build/app consumer-app/src/demo/app/App.java consumer-app/src/demo/app/Main.java

java -cp "build/app;build/annotation-api.jar" demo.app.Main
~~~

Các file mã Java giống **chính xác** như đã viết ở phần 5–7. Không tạo source `MessageInfo.java` bằng tay.

### 8.3. Kết quả có thể kiểm tra

Stdout của lệnh `java` cuối:

~~~text
Hello from compile time
~~~

Sau khi biên dịch, hai output quan trọng tồn tại:

~~~text
build/generated/demo/generated/MessageInfo.java
build/app/demo/generated/MessageInfo.class
~~~

File source do processor viết có nội dung:

~~~java
package demo.generated;

public final class MessageInfo {
    public static final String TEXT = "Hello from compile time";
    private MessageInfo() {}
}
~~~

**Đã kiểm chứng:** Ví dụ này được biên dịch thực tế bằng `javac --release 17` trên JDK hỗ trợ Java 17, đóng gói hai JAR, chạy processor ở giai đoạn compile consumer, xác nhận generated source tồn tại và chạy ứng dụng cho đúng stdout ở trên.

Không nên hiểu output của processor là output của lệnh `java`: **processor chạy lúc `javac` đang compile**, còn dòng `Hello from compile time` được in khi `java demo.app.Main` chạy. Nếu muốn quan sát các vòng annotation processing của compiler, có thể thử `javac -XprintRounds -XprintProcessorInfo ...` trên compiler hỗ trợ các tùy chọn đó; đây là đầu ra chẩn đoán, không phải phần của stdout ứng dụng.

## 9. Hiểu chính xác các đường dẫn và tùy chọn `javac`

| Tùy chọn | Mục đích trong ví dụ |
| --- | --- |
| `--release 17` | Biên dịch source/API/bytecode theo Java 17; không tự kích hoạt processor |
| `-proc:none` | Tắt annotation processing khi biên dịch trước API và processor |
| `-cp build/annotation-api.jar` | Cho **source consumer** thấy `GenerateMessage` |
| `-processorpath processor.jar:api.jar` | Cho **JVM chạy javac** tìm processor và dependency của processor |
| `-processor demo.processor.MessageProcessor` | Chọn implementation processor rõ ràng, không cần ServiceLoader discovery |
| `-s build/generated` | Quy định nơi compiler đặt **generated Java source** |
| `-d build/app` | Quy định nơi compiler đặt **compiled class files** của consumer và generated types |
| `jar --create --file ...` | Đóng gói những class files đã biên dịch thành JAR |
| `java -cp ... demo.app.Main` | Chạy chương trình consumer sau khi compiler hoàn tất |

**`-cp` khác `-processorpath`.** Compiler xử lý source `App.java` cần nhìn thấy annotation API qua compile classpath. Nhưng class loader của processor cần thấy implementation processor cùng dependencies của nó trên processor path. Đưa `annotation-api.jar` lên **cả hai** là có chủ đích, không phải sao chép dư thừa trong demo.

**`-s` khác `-d`.** `-s` chứa `.java` được processor tạo; `-d` chứa `.class` mà compiler xuất ra. Không được suy luận rằng chỉ cần thấy `MessageInfo.java` tức là class đã được biên dịch hoặc ứng dụng sẽ chạy được.

**`-processor` khác `@SupportedAnnotationTypes`.** `-processor` chỉ **class implementation** được gọi; meta-annotation khai báo **loại annotation mà implementation nhận diện**. Cả hai cần đúng nhưng trả lời hai câu hỏi khác nhau.

**`--release` khác `@SupportedSourceVersion`.** Một cái điều khiển độ tương thích source/API/bytecode của compile, một cái là capability statement trên processor. Nên kiểm thử processor với toolchain định hỗ trợ.

### Runtime dependency có cần annotation API?

Trong demo, `GenerateMessage` có retention `SOURCE` và code runtime `Main` chỉ đọc `MessageInfo.TEXT`. Lệnh `java` cho thêm `annotation-api.jar` vào classpath để dễ hiểu mô hình ba artifact, nhưng **điều này không bắt buộc đối với mọi ứng dụng chỉ dùng annotation nguồn**. Nếu artifact app/runtime khác có trực tiếp tham chiếu API annotation hay library khác, phải bổ sung runtime dependencies tương ứng.

Không nên tự động đặt **processor JAR** vào runtime classpath của ứng dụng. Processor chỉ là build-time tool; ứng dụng demo **không cần** `MessageProcessor.class` để chạy.

## 10. Processor discovery bằng ServiceLoader

Ví dụ chính dùng `-processor` nên không cần file đăng ký service. Để compiler có thể **phát hiện** processor khi processor JAR xuất hiện trên processor search path, cơ chế service provider configuration phổ biến là tạo resource trong processor artifact:

~~~text
annotation-processor/
└── resources/
    └── META-INF/
        └── services/
            └── javax.annotation.processing.Processor
~~~

Nội dung file `javax.annotation.processing.Processor`:

~~~text
demo.processor.MessageProcessor
~~~

Đây là **tên class processor**, không phải tên annotation type `demo.api.GenerateMessage`.

Khi đóng gói, đường dẫn bên trong JAR cần chính xác:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nếu tự đóng gói bằng `jar`, hãy thêm resource vào processor JAR, ngoài compiled classes. Khi dùng Gradle/Maven với source layout chuẩn, đặt file trong `annotation-processor/src/main/resources/META-INF/services/...` sẽ giúp build tool thông thường đưa resource vào JAR.

`@SupportedAnnotationTypes` chỉ thông báo processor xử lý annotation nào; **nó không tự tạo file dịch vụ hay đăng ký processor**. Các cơ chế khác như thư viện auto-service có thể giúp sinh file này, nhưng bản thân Java Core không tự tạo đăng ký service khi thấy `@SupportedAnnotationTypes`.

**Lưu ý theo phiên bản JDK:** Cách annotation processing được bật/mặc định trong `javac` đã thay đổi theo đời JDK và cấu hình build tool. Để build có thể lặp lại, luôn cấu hình rõ processor dependency/processor path và hình thức kích hoạt/nhận diện, không trông đợi đơn giản “thêm JAR vào classpath là tự chạy”. Với bài thực hành dùng `-processor` là cách xác định, và demo đã kiểm chứng khi compile Java 17.

## 11. Tổ chức bằng Gradle: tách compile dependency và processor dependency

Trong multi-project Gradle, các module có thể tên:

~~~text
settings.gradle
annotation-api/
annotation-processor/
consumer-app/
~~~

Nội dung `settings.gradle` minh họa:

~~~groovy
rootProject.name = 'annotation-example'
include 'annotation-api', 'annotation-processor', 'consumer-app'
~~~

Cả ba project dùng plugin `java-library`/`java`/`application` phù hợp và toolchain Java 17. Trong `annotation-processor/build.gradle`, khai báo processor phụ thuộc vào API:

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation project(':annotation-api')
}
~~~

Với `consumer-app/build.gradle`:

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    compileOnly project(':annotation-api')
    annotationProcessor project(':annotation-processor')
    annotationProcessor project(':annotation-api')
}

application {
    mainClass = 'demo.app.Main'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '-processor', 'demo.processor.MessageProcessor'
    ]
}
~~~

Đây là **minh họa cấu hình Gradle**, giả định bạn di chuyển source tới layout Gradle `src/main/java` và tạo cấu hình/plugin Java tương ứng cho `annotation-api`. Cấu hình `-processor` tường minh nên không cần ServiceLoader cho demo; trong dự án đã đóng gói đăng ký processor bằng service file, thường có thể bỏ compilerArgs thủ công và để processor được phát hiện qua dependency đúng configuration.

Giải thích các configuration:

- `implementation project(':annotation-api')` **trong processor module**: processor cần API để biên dịch và chạy.
- `compileOnly project(':annotation-api')` **trong consumer**: annotation API dùng để compile source nhưng không mặc định là runtime dependency; phù hợp với `SOURCE`-only ví dụ. Nếu consumer cần API cả runtime, dùng `implementation` thay vì `compileOnly`.
- `annotationProcessor project(':annotation-processor')`: Gradle đưa processor lên **processor path** của task compile consumer, không đồng nghĩa đóng gói processor vào ứng dụng.
- `annotationProcessor project(':annotation-api')`: đưa API vào processor execution path một cách tường minh, tránh thiếu dependency khi processor gọi `GenerateMessage.class`. Trong một build có dependency metadata/transitive runtime đầy đủ, API có thể đã được đưa vào processor path thông qua dependency processor; cấu hình minh họa ghi rõ để người học nhìn thấy hai phía.
- `tasks.withType(JavaCompile)...-processor`: kích hoạt processor class được chỉ định rõ ngay cả khi chưa đóng gói `META-INF/services`.

Khi chuyển sang Gradle, hãy để công cụ quản lý thứ tự build thông qua dependency graph, thay vì tự gọi `javac` thủ công. `consumer-app` không phải là dependency của `annotation-processor`; chúng được nối với nhau qua API và compilation task.

### Với Maven thì sao?

Maven cũng nên có ba artifact/child modules riêng, ví dụ:

~~~text
parent
├── annotation-api
├── annotation-processor
└── consumer-app
~~~

- POM của **processor** phụ thuộc annotation API.
- POM của **consumer** khai báo annotation API làm dependency cần cho compile. Nếu retention/source-only và không cần runtime, có thể thiết kế scope tùy mô hình phụ thuộc; không ép `provided` thay thế một cách máy móc khi app thực sự cần API runtime.
- Cấu hình Maven Compiler Plugin để đưa **processor artifact và những dependencies cần thiết** lên annotation processor path; trong những phiên bản plugin mới có thể dùng cơ chế khai báo processor dependency tương ứng. Khi muốn chủ động xác định processor, khai báo processor class theo cấu hình được plugin hỗ trợ.
- Đảm bảo công cụ/build được kiểm thử với JDK 17 và cấu hình annotation processing tường minh. Tên option và DSL chi tiết phụ thuộc phiên bản Maven Compiler Plugin; kiểm tra tài liệu của đúng phiên bản đang sử dụng trước khi sao chép POM.

**Ý nghĩa quan trọng hơn một cú pháp Gradle/Maven cụ thể:** annotation API và processor là **hai artifact khác nhau**, có các vai trò dependency khác nhau. Consumer không nên cần processor JAR trong runtime classpath chỉ để chạy business logic.

## 12. Kịch bản lỗi thường gặp và cách xử lý

### 12.1. `Annotation processor '...' not found`

**Triệu chứng:** `javac` không tìm được `demo.processor.MessageProcessor`.

Kiểm tra:

1. Processor đã được biên dịch ra `.class` trong JAR chưa?
2. `-processorpath` có trỏ đúng JAR và không nhầm folder source?
3. `-processor` có dùng **fully qualified class name** `demo.processor.MessageProcessor`?
4. Class processor có `public` và có public constructor no-arg phù hợp không? Với class public không tự định nghĩa constructor, Java cung cấp constructor không tham số mặc định phù hợp.
5. Processor có đang dùng cách chạy module-path/JPMS khác với ví dụ classpath không?

### 12.2. `NoClassDefFoundError: demo/api/GenerateMessage` khi nạp processor

Processor import và gọi `GenerateMessage.class` nhưng API JAR thiếu trên processor execution path. Cần bổ sung **annotation-api.jar** vào processorpath hoặc đóng gói/khai báo runtime dependency đúng cách. Chỉ đặt API JAR ở `-cp` consumer không đảm bảo processor class loader nhìn thấy nó.

### 12.3. Consumer không biên dịch được annotation type

Nếu `App.java` báo không thấy `demo.api.GenerateMessage`, vấn đề thường là **consumer compile classpath** thiếu `annotation-api.jar`. Bổ sung `-cp build/annotation-api.jar` hoặc dependency `compileOnly/implementation` tương đương.

### 12.4. Processor không chạy nhưng consumer vẫn compile được

Có thể bạn chưa bật processing, thiếu `-processor`, thiếu service descriptor, sai processor path hoặc toolchain có chính sách auto-discovery khác. Đừng kết luận chỉ vì `GenerateMessage` được compiler chấp nhận thì processor đã xử lý.

Kiểm tra output `build/generated/.../MessageInfo.java` hoặc dùng option theo dõi processor/rounds. Với demo, vì `Main` import generated type, nếu processor không chạy, compilation sẽ không giải quyết được `demo.generated.MessageInfo`; đây là cách phát hiện lỗi bằng kết quả compile.

### 12.5. `cannot find symbol MessageInfo`

Đừng tự chép class generated vào source module để “chữa cháy” rồi giữ hai bản. Hãy xác minh `Main.java` và `App.java` được compile trong một task có processor đang chạy và Filer đã tạo source ở đúng package.

### 12.6. `FilerException: Attempt to recreate a file for type ...`

Một processor tạo cùng fully qualified name hơn một lần trong cùng lần compilation, hoặc có class/file trùng tên mà compiler đã xử lý. Cần đảm bảo mỗi generated type chỉ được tạo một lần, quản lý state qua processing rounds và đặt tên output không xung đột với source do người dùng viết. Trong demo có cờ `generated` để tránh lặp.

### 12.7. Vòng phụ thuộc giữa API, processor và consumer

Lỗi kiến trúc:

~~~text
consumer needs processor
processor imports consumer classes
consumer cannot compile before processor
~~~

Hướng sửa: khai báo annotation ở API riêng; processor chỉ import API và xem class consumer thông qua `Element`/`TypeMirror` do compiler cung cấp. Nếu processor cần một contract chung, chuyển contract đó vào API hoặc artifact chung phù hợp, **không** import app.

### 12.8. Đưa processor vào `implementation` của consumer

Khi processor chỉ là compile-time tool, để nó ở runtime dependencies làm tăng kích thước artifact và dễ tạo xung đột classloading. Dùng cấu hình processor-path/`annotationProcessor` phù hợp. Chỉ đưa processor vào runtime khi có nhu cầu đặc biệt đã được thiết kế rõ ràng, không phải để xử lý `@GenerateMessage` thông thường.

### 12.9. Bỏ sót service file trong JAR

Nếu dùng auto-discovery, JAR phải chứa đúng `META-INF/services/javax.annotation.processing.Processor` và tên processor implementation. Đặt resource ở sai đường dẫn, đặt tên annotation type thay processor hoặc không đóng gói resource vào JAR đều làm discovery thất bại.

### 12.10. Chỉ test trên một JDK rồi xem là mọi bản JDK đều tương đương

Processor thực thi trong môi trường compiler; cấu hình discovery/toolchain và source language level có thể thay đổi. Giữ `--release`, test JDK mục tiêu, kiểm tra `@SupportedSourceVersion` và dùng compiler configuration tường minh. Không trông chờ auto-process chỉ từ một JAR được thêm ngẫu nhiên vào classpath.

### 12.11. Ghép chuỗi Java source từ dữ liệu người dùng mà không escape

Demo chỉ cho phép `[A-Za-z ]+` để tạo Java string literal một cách đơn giản. Processor thực tế phải escape dấu nháy kép, backslash, newline và các trường hợp Unicode phù hợp hoặc dùng thư viện sinh code. Nếu bỏ validation rồi nối trực tiếp annotation value vào generated source, mã sẽ dễ sai cú pháp, có nguy cơ tạo source không theo ý định.

### 12.12. Nhầm source retention với runtime accessibility

`@Retention(SOURCE)` đủ để processor xử lý ngay trong compile phase; nhưng chương trình chạy không thể dựa vào `App.class.getAnnotation(GenerateMessage.class)` để lấy annotation qua Reflection runtime. Nếu runtime feature cần nó, dùng retention `RUNTIME` và thiết kế API/runtime dependency tương ứng.

## 13. Checklist QA cho ba artifact

| Câu hỏi | Tiêu chí đạt |
| --- | --- |
| Annotation API đã tách riêng chưa? | Chứa `public @interface GenerateMessage`, không phụ thuộc processor/consumer |
| Processor phụ thuộc API đúng chiều? | `annotation-processor → annotation-api` |
| Consumer cần loại dependency nào? | Annotation API trên compile path; processor trên processor path |
| API JAR nằm trên processor execution path chưa? | Có nếu processor load/import annotation type đó |
| Processor được compiler lựa chọn rõ? | `-processor demo.processor.MessageProcessor` hoặc discovery hợp lệ |
| Compiler có chạy processing? | Có, không bị `-proc:none` tại bước compile consumer |
| Build order đúng? | Compile API → compile processor → compile consumer |
| Generated source ở đâu? | `build/generated/demo/generated/MessageInfo.java` |
| Generated class ở đâu? | `build/app/demo/generated/MessageInfo.class` |
| Ứng dụng in gì? | `Hello from compile time` |
| Có vòng phụ thuộc vào consumer trong processor? | Không |
| Source level nhất quán? | Demo dùng `javac --release 17` ở mọi bước |

### Gợi ý kiểm tra nâng cao

Nếu dự án thực tế lớn hơn demo, hãy kiểm thử ít nhất ba kịch bản:

1. **Không có annotation được đánh dấu:** processor không tạo source vô cớ; chương trình không phụ thuộc vào generated class chưa tồn tại trong kịch bản này.
2. **Annotation hợp lệ:** đúng class được tạo, source và bytecode đều compile, ứng dụng dùng được API sinh ra.
3. **Annotation không hợp lệ/được dùng quá nhiều lần:** compiler phát diagnostics dễ hiểu, không tạo duplicate source và không dùng giá trị đầu vào làm Java literal thiếu escape.

Ngoài ra, build sạch (`clean build`) cần tái tạo tất cả files generated. Nếu xóa mỗi generated source rồi không chạy processor ở build kế tiếp, ứng dụng không nên vô tình “qua được” nhờ class cũ trong thư mục output.

## 14. Bài tập tự thực hành

1. **Đổi giá trị annotation:** Thay `@GenerateMessage("Hello from compile time")` bằng `@GenerateMessage("Build is ready")` rồi rebuild consumer. Dự đoán source generated và stdout.
2. **Đọc đường đi:** Tạm loại `annotation-api.jar` ra khỏi compile classpath consumer; xem lỗi compiler và giải thích khác với việc loại API JAR ra khỏi processor path.
3. **Thiếu processor:** Bỏ `-processor demo.processor.MessageProcessor` mà không cài service descriptor. Quan sát khả năng compiler tìm processor trên môi trường đó; không đánh đồng với build có discovery đã cấu hình.
4. **Kiểm tra source generation:** Sau compile, mở `build/generated/demo/generated/MessageInfo.java` và kiểm tra constant. Xác nhận class tương ứng có trong `build/app`.
5. **Lỗi duplicate:** Gắn `@GenerateMessage` trên hai class và xem diagnostic demo "expects exactly one marked class"; đề xuất cách cải tiến đặt tên generated type dựa vào `Element.getSimpleName()` để hỗ trợ nhiều class.
6. **Dùng Messager:** Thử giá trị `@GenerateMessage("Hello!")`. Processor giới hạn ký tự sẽ báo lỗi compile. Giải thích vì sao diagnostic compile-time hữu ích hơn để lỗi Java source sinh ra.
7. **Đăng ký service:** Thêm file `META-INF/services/javax.annotation.processing.Processor` vào processor JAR, chứa `demo.processor.MessageProcessor`, và thử loại bỏ `-processor` trong một build có annotation processing/discovery được bật rõ.
8. **Tách runtime:** Thử chạy chỉ với `java -cp build/app demo.app.Main`. Phân tích vì sao với ví dụ `SOURCE`-only và class generated chỉ chứa `String`, processor và annotation API JAR không cần được ứng dụng nạp ở runtime trong trường hợp này.
9. **Gradle:** Đổi thư mục Java sources sang `src/main/java`. Cấu hình ba subprojects, xác minh `annotationProcessor` cho consumer và `implementation` cho processor, rồi chạy compile clean.
10. **Maven:** Tạo parent project có ba artifact và cấu hình Maven Compiler Plugin phiên bản phù hợp; giải thích vai trò processor path và regular classpath.
11. **Đổi retention:** Thay `SOURCE` bằng `RUNTIME` và bổ sung một truy vấn Reflection runtime. Điều chỉnh runtime dependency rồi phân biệt chức năng processor và chức năng đọc annotation lúc chạy.
12. **Thiết kế API nâng cao:** Khi consumer A/B cùng dùng processor, xem cách phát hành một API JAR và một processor JAR thành các phiên bản tương thích. Trình bày cách giảm yêu cầu runtime dependency của consumer.

## 15. Tổng kết

Tách **annotation API**, **annotation processor** và **consumer** không chỉ làm mã sạch hơn; nó phản ánh đúng ba môi trường:

- **Định nghĩa contract**: `annotation-api.jar` được chia sẻ với source consumer và processor.
- **Thực thi tại compile time**: `annotation-processor.jar` được `javac` nạp cùng các dependencies của nó, phát hiện annotation và có thể sinh source.
- **Chạy ứng dụng**: consumer sử dụng bytecode đã biên dịch và generated classes; thường **không cần** processor trong runtime classpath.

Cốt lõi là **đúng chiều phụ thuộc, đúng build order và đúng compiler paths**. `-cp` phục vụ việc giải quyết kiểu cho source, `-processorpath` phục vụ việc tải processor, `-processor` hoặc service provider quyết định processor nào chạy, `-s` chứa source được sinh và `-d` chứa class files. Khi đặt các phần đúng vai trò, annotation processing trở thành một bước build có thể kiểm chứng, không phải hành vi tự động khó đoán.

### Tài liệu tham khảo

- [Oracle Java SE 17 — javac command: `--release`, `-cp`, `-processorpath`, `-processor`, `-s` và annotation processing](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html).
- [Java SE 17 API — Processor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html).
- [Java SE 17 API — AbstractProcessor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html).
- [Java SE 17 API — Filer](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html).
- [Java SE 17 API — RoundEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html).
- [Java SE 17 API — SupportedAnnotationTypes](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/SupportedAnnotationTypes.html).
- [Java SE 17 API — SupportedSourceVersion](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/SupportedSourceVersion.html).
