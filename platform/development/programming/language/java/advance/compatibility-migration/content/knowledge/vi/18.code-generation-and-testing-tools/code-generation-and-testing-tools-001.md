# Annotation processor và thay đổi cơ chế kích hoạt theo JDK

Trong chương **Sinh mã và công cụ test** thuộc **Java Advance Compatibility Migration**, annotation processing là một điểm dễ gây lỗi khi nâng JDK: source Java không thay đổi, dependency vẫn tồn tại và lệnh biên dịch có thể không báo lỗi về chính annotation, nhưng **mã nguồn từng được sinh ra ở bước compile lại biến mất**.

Nguyên nhân điển hình là quá trình build trước đây vô tình dựa vào việc **javac tự quét classpath để tìm annotation processor**. Từ **JDK 23**, khi không có cấu hình annotation processing tường minh, javac **không tự kích hoạt annotation processing** theo mặc định như trước. JDK 21 và 22 đã có thông báo nhắc về việc phụ thuộc vào implicit processing. Do đó, nâng compiler lên phiên bản mới có thể làm một module mất generated code dù ứng dụng vẫn dùng cùng các annotation. 

Bài học trình bày cơ chế annotation processing, những thay đổi qua JDK, cách cấu hình **javac, Gradle và Maven**, rủi ro với Lombok/MapStruct/JPA metamodel và công cụ test, cách xử lý annotation processors chạy bằng JDK mới nhưng sinh bytecode cho target cũ, cùng chiến lược migration an toàn.

> **Phạm vi:** annotation processing ở **compile time** dựa trên JSR 269 và gói **javax.annotation.processing**. Đây không phải reflection đọc annotation ở runtime, không phải mọi loại source generator, và cũng không đồng nghĩa với Java agents hoặc compiler plugins tùy chỉnh.

## 1. Phân biệt annotation với annotation processor

Một annotation chỉ là metadata được định nghĩa trong Java. Việc đặt annotation lên class **không tự bảo đảm** có source code được sinh ra.

Ví dụ annotation do ứng dụng định nghĩa:

~~~java
package example.annotation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateGreeting {
    String value();
}
~~~

Source sử dụng:

~~~java
package example.app;

import example.annotation.GenerateGreeting;

@GenerateGreeting("Hello")
public class Greeter {
}
~~~

Nếu không có processor được kích hoạt, annotation vẫn hợp lệ, class **Greeter** vẫn có thể được biên dịch, nhưng một class như **GreeterGenerated** sẽ không tự xuất hiện.

Annotation processor là một **chương trình chạy trong quá trình biên dịch**. Nó có thể:

- Tìm các annotation được hỗ trợ.
- Phân tích phần tử chương trình thông qua model của compiler.
- Tạo Java source hoặc resource bằng **Filer**.
- Tạo diagnostics thông qua **Messager**.
- Làm việc qua nhiều vòng xử lý khi source mới được tạo.
- Khiến compiler biên dịch cả source đã sinh ra.

Processor có thể sinh code của mapper, dependency injection, JPA metamodel, builder hoặc metadata. Tuy vậy, **một số công cụ như Lombok còn sử dụng cơ chế và tích hợp sâu với compiler**; không được xem chúng chỉ tương tác qua API JSR 269 thuần túy.

### 1.1. Hai dependency thường khác nhau

| Thành phần | Có nhiệm vụ gì? | Ví dụ |
|---|---|---|
| Annotation API | Cho source tham chiếu đến annotation | GenerateGreeting, Mapper, Entity |
| Annotation processor | Chạy lúc compile, tạo code hoặc metadata | GreetingProcessor, MapStruct processor |
| Generated source | Java source do processor tạo | GreeterGenerated.java |
| Generated class | Bytecode được compiler tạo từ source gốc/sinh ra | GreeterGenerated.class |
| Runtime library | Thư viện chương trình cần khi chạy | Tùy từng framework |
| Test annotation processor | Processor chạy cho test source | Có thể tách khỏi main compilation |

Với một số công cụ, annotation API và processor nằm **cùng một JAR**; với công cụ khác, chúng nằm ở artifact khác nhau. Không nên suy luận rằng thêm một dependency ở **implementation** hoặc **compileOnly** đương nhiên làm processor được thực thi trên mọi JDK.

### 1.2. Vì sao lỗi có thể xuất hiện muộn?

Nếu source chính có đoạn:

~~~java
GreeterGenerated.sayHello();
~~~

khi processor không chạy, compile có thể lỗi **cannot find symbol** ngay.

Nhưng nếu processor chỉ sinh service metadata hoặc JPA metamodel dùng ở một module khác, module hiện tại có thể build thành công mà không sinh artifact cần thiết. Lỗi chỉ xuất hiện khi:

- Module khác compile.
- Framework tìm generated implementation ở runtime.
- Test integration chạy.
- Build package/CI kiểm tra resource.
- Một chức năng ít dùng được gọi.

Vì thế, kiểm chứng chỉ bằng exit code của một lệnh compile là chưa đủ để kết luận annotation processing hoạt động như baseline.

## 2. Cơ chế JSR 269 trong javac

API tiêu chuẩn gồm các lớp/giao diện như:

- **javax.annotation.processing.Processor**
- **javax.annotation.processing.AbstractProcessor**
- **javax.annotation.processing.RoundEnvironment**
- **javax.annotation.processing.ProcessingEnvironment**
- **javax.annotation.processing.Filer**
- **javax.annotation.processing.Messager**
- **javax.lang.model.element.\***
- **javax.lang.model.type.\***
- **javax.lang.model.util.\***

Tên package vẫn là **javax.annotation.processing** trong API chuẩn của JDK. Không chuyển sang **jakarta.annotation.processing** chỉ vì dự án nâng Spring Boot/Jakarta EE. Đổi namespace của JPA từ **javax.persistence** sang **jakarta.persistence** là một vấn đề khác.

### 2.1. Compiler thực hiện những bước nào?

~~~text
Java source + classpath/module path
                 |
                 v
       javac nạp processors
                 |
                 v
       Round 1: đọc annotations
                 |
                 +--> Processor sinh Java source/resource
                 |
                 v
       Round 2: xét source mới
                 |
                 +--> Có thể sinh thêm source
                 |
                 v
       Các round tiếp theo
                 |
                 v
       Final round / processing over
                 |
                 v
       Compile source gốc và source sinh ra
                 |
                 v
       .class files + resources
~~~

Processor được gọi qua các **round**. Nếu tạo thêm Java source ở một round, compiler có thể thực hiện round tiếp theo để các processor khác xử lý source mới.

Đừng giả định mọi processor chỉ chạy đúng một lần. Nếu processor lưu trạng thái giữa các round hoặc ghi trùng file đã tồn tại, nó có thể gặp **FilerException** hoặc tạo output không quyết định được.

### 2.2. Processor đọc source bằng language model

Một processor đúng chuẩn thường thao tác với **TypeElement**, **ExecutableElement**, **VariableElement** và **TypeMirror** thay vì nạp trực tiếp class đang được compile bằng **Class.forName**.

Source đang được biên dịch chưa chắc đã có bytecode để class loader có thể nạp. Cố dùng reflection runtime để khám phá annotation trong processor có thể thất bại, đặc biệt khi code chưa compile hoặc classpath/module path khác biệt.

### 2.3. Service discovery

Một processor JAR có thể khai báo:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nội dung file là tên đầy đủ của class processor:

~~~text
example.processor.GreetingProcessor
~~~

Khi javac được cấu hình để tìm processor trên processor path/classpath và không giới hạn danh sách processor cụ thể, nó có thể dùng cơ chế service provider để phát hiện processor.

Tuy nhiên, **JDK 23 không tự động quét một classpath thông thường để bật annotation processing khi không có tùy chọn cấu hình liên quan**. JAR có service file nhưng chỉ nằm trong dependency classpath không đủ để bảo đảm processor được chạy.

## 3. Thay đổi quan trọng qua các JDK

### 3.1. Trước JDK 23: implicit annotation processing

Với nhiều phiên bản JDK trước JDK 23, khi không cấu hình annotation processing tường minh, javac có thể tự tìm processor trên classpath và chạy chúng.

Ví dụ một dự án legacy chỉ thêm JAR có processor vào classpath:

~~~bash
javac -cp "deps/*" -d out src/example/app/Greeter.java
~~~

Nếu processor xuất hiện trong classpath và cấu hình phù hợp, ở các JDK cũ processor có thể chạy mà nhóm phát triển **không hề ghi khai báo processor riêng**.

Đây là phụ thuộc ngầm:

~~~text
Processor JAR tình cờ nằm trên classpath
                 |
                 v
javac cũ tự phát hiện
                 |
                 v
Generated source xuất hiện
~~~

Rủi ro của kiểu mặc định này là JAR dependency có thể chứa processor không chủ ý; khi thay dependency graph, processor được kích hoạt cũng có thể thay đổi.

### 3.2. JDK 21 và 22: thông báo cảnh báo quá trình chuyển đổi

JDK 21 bắt đầu phát một **note** khi implicit annotation processing diễn ra mà không có cấu hình xử lý annotation tường minh. Mục đích là báo trước rằng mặc định này có thể bị tắt trong release tương lai.

Không nên giải quyết bằng cách chỉ ẩn note qua tùy chọn lint. Việc ẩn thông báo không có nghĩa build đã được cấu hình chủ động và sẽ tiếp tục tạo code trên JDK mới.

### 3.3. JDK 23: yêu cầu cấu hình rõ ràng

Từ **JDK 23**, khi không có tùy chọn yêu cầu/cấu hình annotation processing, javac mặc định **không chạy processors**. Muốn chạy, cần một cách kích hoạt tường minh như:

- **-processor** với tên processor muốn chạy.
- **--processor-path** hoặc **-processorpath**.
- **--processor-module-path** với modular processor.
- **-proc:full** để yêu cầu xử lý annotation và compile.
- **-proc:only** để chỉ chạy annotation processing.

Điểm quan trọng: **đặt một processor JAR trên classpath thông thường mà không có cấu hình annotation processing khác không còn là cách đáng tin cậy từ JDK 23**.

### 3.4. Bảng tóm tắt

| Công cụ/phiên bản | Nếu processor chỉ nằm trên classpath và không có cấu hình APT | Hướng migration |
|---|---|---|
| JDK trước 21 | Có thể được tự tìm và chạy theo mặc định | Chuyển sang khai báo explicit |
| JDK 21 | Có thể chạy, kèm note khi implicit processing | Không chỉ ẩn note; khai báo processor |
| JDK 22 | Mặc định implicit processing trong release chính thức; có note | Chuẩn bị cho thay đổi JDK 23 |
| JDK 23 trở lên | Không tự kích hoạt khi thiếu cấu hình APT | Dùng processor path/danh sách processor rõ ràng |
| Build tool với cấu hình processor riêng | Phụ thuộc cách tool sinh tùy chọn javac | Kiểm tra compiler command/dependency graph thực tế |

**Lưu ý về lịch sử JDK 22:** đã từng có thử nghiệm thay đổi mặc định trong các bản early-access; khi đánh giá migration thực tế, dùng tài liệu release chính thức và phiên bản javac đang chạy thay vì suy luận từ một bản thử nghiệm.

### 3.5. Đây là thay đổi mặc định của javac, không phải bỏ JSR 269

JDK 23 **không loại bỏ annotation processing**. API Processor, các rounds và công cụ sinh mã vẫn tồn tại. Thay đổi nằm ở **điều kiện kích hoạt**.

Không nên sửa annotation trong hàng trăm source file khi nguyên nhân chỉ là build không đưa processor lên đúng path.

## 4. Những tùy chọn javac cần nhớ

| Tùy chọn | Vai trò | Lưu ý |
|---|---|---|
| **-processor** | Chỉ định tên đầy đủ processor class cần chạy | Bỏ qua discovery mặc định để chọn processor rõ |
| **--processor-path** | Đường dẫn chứa processor và dependency của nó | Cũng kích hoạt xử lý theo javac khi phù hợp |
| **-processorpath** | Dạng tên tùy chọn tương đương processor path | Thường gặp ở build script cũ |
| **--processor-module-path** | Tìm processor trong các module | Cần processor được đóng gói/cấu hình modular phù hợp |
| **-proc:none** | Không chạy annotation processing | Có ích khi xác minh code độc lập với processor |
| **-proc:only** | Chỉ thực hiện annotation processing | Không hoàn tất compile bình thường |
| **-proc:full** | Chạy annotation processing rồi compile | Cho phép yêu cầu processing rõ trên JDK mới |
| **-s directory** | Vị trí lưu generated source | Khác với đường dẫn output class |
| **-d directory** | Vị trí lưu class files | Không có nghĩa generated source nằm ở đây |
| **-Akey=value** | Truyền option vào annotation processor | Tên key do processor quyết định |
| **-XprintRounds** | Quan sát các processing rounds | Dùng khi cần chẩn đoán |
| **-XprintProcessorInfo** | Quan sát processor/annotation processing | Dùng khi cần chẩn đoán |

### 4.1. Ưu tiên chọn processor cụ thể

Ví dụ minh họa:

~~~bash
javac ^
  -cp "lib/annotation-api.jar" ^
  -processorpath "lib/greeting-processor.jar" ^
  -processor example.processor.GreetingProcessor ^
  -s generated-src ^
  -d classes ^
  src/example/app/Greeter.java
~~~

Dấu **^** là ký tự nối dòng của Windows cmd. Trên macOS/Linux, dùng dấu **\\** hoặc viết trên một dòng; phân tách path trên Windows là **;**, trên hệ Unix thường là **:**.

Ví dụ trên giả định JAR của processor có đủ dependency hoặc processor path đã liệt kê tất cả dependency cần thiết. Khi thiếu dependency của processor, lỗi có thể là **NoClassDefFoundError** hoặc lỗi nạp processor trong lúc compile.

Tách rõ:

~~~text
Compile classpath:
  annotation-api.jar
  + các type mà source tham chiếu

Processor path:
  greeting-processor.jar
  + dependency của chính processor
~~~

Hai path có thể chứa một số JAR chung khi cần, nhưng không nên đặt tất cả compile/runtime dependencies vào processor path một cách vô ý.

### 4.2. -proc:full giúp giữ hành vi, nhưng không phải thiết kế tốt nhất

Một biện pháp chuyển tiếp:

~~~bash
javac -proc:full -cp "lib/*" -d classes src/example/app/Greeter.java
~~~

Nó yêu cầu annotation processing hoạt động trở lại theo cách có thể tìm processor trên classpath.

Tuy nhiên, nếu mục tiêu là build an toàn và tái lập được, **khoanh đúng processor trên processor path và/hoặc nêu rõ tên processor** thường tốt hơn. Dùng **-proc:full** với classpath rộng có thể lại kích hoạt những processor không mong muốn có trong dependency.

### 4.3. -proc:only dùng khi nào?

~~~bash
javac -proc:only \
  -processorpath "lib/greeting-processor.jar" \
  -processor example.processor.GreetingProcessor \
  -s generated-src \
  -cp "lib/annotation-api.jar" \
  src/example/app/Greeter.java
~~~

Ví dụ dành cho shell Unix. Đây là bước **xử lý annotation**, không phải compile ra đầy đủ class files như **-proc:full**.

Có thể dùng nó để tách bước generate trong một workflow chuyên biệt, nhưng cần quản lý source/generated directories, thứ tự các processor và lần compile tiếp theo. Không chuyển mọi build sang **-proc:only** rồi mong có artifact chạy được.

### 4.4. --release không chọn JDK chạy processor

Ví dụ:

~~~bash
javac --release 17 \
  -processorpath "lib/processor.jar" \
  -processor example.processor.GreetingProcessor \
  -d classes \
  src/example/app/Greeter.java
~~~

Nếu lệnh trên chạy bằng **javac của JDK 23**, annotation processor đang thực thi trong môi trường compiler JDK 23, còn **--release 17** điều khiển ngôn ngữ/API target và class file được tạo cho source ứng dụng.

Điều đó có nghĩa:

- Processor phải tương thích với JDK chạy javac.
- Generated Java source phải phù hợp với target release.
- Dependency runtime của ứng dụng phải phù hợp target release.
- Nếu processor tự ghi bytecode thay vì chỉ sinh source, cần kiểm soát classfile version và công cụ bytecode tương ứng.

Không suy luận rằng **--release 17** tự khiến Lombok, MapStruct hoặc một processor legacy “chạy trên JDK 17”.

## 5. Ví dụ tự xây dựng annotation processor

Một processor đơn giản sẽ giúp nhìn rõ vị trí kích hoạt.

### 5.1. Annotation API

File **example/annotation/GenerateGreeting.java**:

~~~java
package example.annotation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateGreeting {
    String value();
}
~~~

### 5.2. Processor

File **example/processor/GreetingProcessor.java**:

~~~java
package example.processor;

import example.annotation.GenerateGreeting;

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

@SupportedAnnotationTypes("example.annotation.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateGreeting.class)) {

            if (!(element instanceof TypeElement type)) {
                continue;
            }

            String packageName =
                processingEnv.getElementUtils()
                    .getPackageOf(type)
                    .getQualifiedName()
                    .toString();

            String generatedName =
                type.getSimpleName() + "Generated";

            String qualifiedName = packageName.isEmpty()
                ? generatedName
                : packageName + "." + generatedName;

            String value =
                type.getAnnotation(GenerateGreeting.class).value();

            try {
                JavaFileObject file =
                    processingEnv.getFiler()
                        .createSourceFile(qualifiedName, type);

                try (Writer out = file.openWriter()) {
                    if (!packageName.isEmpty()) {
                        out.write("package " + packageName + ";\\n");
                    }
                    out.write(
                        "public final class " + generatedName + " {\\n"
                    );
                    out.write(
                        "  private " + generatedName + "() {}\\n"
                    );
                    out.write(
                        "  public static String text() { return \\\""
                        + escapeJava(value) + "\\\"; }\\n"
                    );
                    out.write("}\\n");
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Cannot generate " + qualifiedName + ": " + ex,
                    element
                );
            }
        }
        return true;
    }

    private static String escapeJava(String input) {
        return input
            .replace("\\\\", "\\\\\\\\")
            .replace("\\\"", "\\\\\\\"");
    }
}
~~~

Ví dụ này minh họa API JSR 269; khi viết generator production nên dùng công cụ tạo source có xử lý escaping đầy đủ hơn, đặc biệt ký tự xuống dòng/control characters và Java syntax hợp lệ. Cần tránh tạo trùng file ở nhiều rounds.

**Điểm cần hiểu:** annotation processor chạy trong quá trình compile source của consumer; nó không phải class mà ứng dụng cần gọi khi chạy production.

### 5.3. Service registration

Nếu muốn processor được phát hiện tự động trên **processor path**, đóng gói file:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nội dung:

~~~text
example.processor.GreetingProcessor
~~~

Nếu sử dụng tùy chọn **-processor example.processor.GreetingProcessor**, tên processor đã được chỉ rõ; service discovery không còn là điều kiện duy nhất.

### 5.4. Source consumer

~~~java
package example.app;

import example.annotation.GenerateGreeting;

@GenerateGreeting("Hello migration")
public class Greeter {
    public static void main(String[] args) {
        System.out.println(GreeterGenerated.text());
    }
}
~~~

Khi processor thực sự chạy, nó tạo **GreeterGenerated.java**. Compiler có thể tiếp tục compile source đó trong cùng lượt biên dịch.

Khi processor bị vô hiệu hóa, **GreeterGenerated** không tồn tại nếu build sạch; code consumer cần nó sẽ báo không tìm thấy symbol.

### 5.5. Vì sao phải build sạch?

Nếu thư mục output còn **GreeterGenerated.class** từ lần build trước, dù processor không chạy, compile hoặc chạy ứng dụng có thể vẫn thành công. Điều này khiến lỗi bị che trên máy developer nhưng lộ trên CI fresh checkout.

Cần phân biệt:

- **Output do processor hiện tại sinh.**
- **File stale còn từ build cũ.**
- **Source generated đã được commit có chủ đích.**
- **Class nằm trong dependency JAR khác.**

Một migration đúng phải xác định provenance của generated code, không chỉ tìm thấy file trong directory.

## 6. Gradle: khai báo annotationProcessor rõ ràng

Với Gradle Java/Java Library plugin, cấu hình **annotationProcessor** dùng để đưa processor lên processor path.

Ví dụ Groovy DSL:

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    // API annotation xuất hiện trong source
    compileOnly 'org.projectlombok:lombok:1.18.34'

    // Processor chạy ở compile time
    annotationProcessor 'org.projectlombok:lombok:1.18.34'
}
~~~

Phiên bản Lombok là **ví dụ về cú pháp**, không phải khuyến nghị một phiên bản cụ thể cho mọi JDK. Khi nâng JDK, chọn phiên bản processor được nhà cung cấp tuyên bố hỗ trợ **JDK chạy compiler**.

### 6.1. implementation khác annotationProcessor

~~~groovy
dependencies {
    implementation 'example:annotation-api:1.0'

    annotationProcessor 'example:greeting-processor:1.0'
}
~~~

**implementation** cung cấp dependency cho quá trình compile/run của source ứng dụng theo mô hình Gradle. **annotationProcessor** là nơi Gradle tìm processor để thực thi.

Đặt chỉ:

~~~groovy
dependencies {
    implementation 'example:greeting-processor:1.0'
}
~~~

không phải phương án đáng tin cậy để yêu cầu Gradle chạy processor. Build tool có thể chủ động tách compile classpath và processor path; việc phụ thuộc implicit discovery còn gặp thay đổi mặc định của javac từ JDK 23.

### 6.2. Main và test là hai lượt compile khác nhau

Một dự án có thể cần annotation processing khi compile **src/test/java**:

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok:1.18.34'
    annotationProcessor 'org.projectlombok:lombok:1.18.34'

    testCompileOnly 'org.projectlombok:lombok:1.18.34'
    testAnnotationProcessor 'org.projectlombok:lombok:1.18.34'
}
~~~

Nếu chỉ cấu hình **annotationProcessor**, source test trực tiếp dùng annotation có thể thiếu processor trong task compileTestJava tùy dependency/configuration.

Cần tách câu hỏi:

- Processor có cần cho production source không?
- Processor có cần cho test source không?
- Annotation API được test source dùng ra sao?
- Generated code được tiêu thụ ở source set nào?

### 6.3. Không hardcode generated directory rồi tự compile hai lần

Gradle quản lý generated sources từ annotation processing qua compile task. Nếu tạo thủ công một task sinh source và lại thêm output vào source set không đúng, có thể gây:

- Duplicate class.
- Compile theo sai thứ tự.
- Generated file stale.
- Không khai báo input/output đầy đủ, làm incremental build sai.
- Build cache chứa output không quyết định.

Ưu tiên dùng cơ chế processor được Gradle hỗ trợ. Nếu cần custom task, khai báo rõ ownership và dependency graph.

### 6.4. Dùng Java toolchains để biết javac nào thực sự chạy

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(23)
    }
}
~~~

Toolchain ảnh hưởng JDK compiler dùng cho task Java tương ứng; nó không tự bảo đảm mọi plugin/process trong build chạy trên cùng JDK. Hãy xác định JVM của Gradle daemon, compiler và test executor riêng nếu lỗi xuất hiện ở một giai đoạn cụ thể.

**Không dùng sourceCompatibility/targetCompatibility hoặc --release để kết luận processor chạy trên một JDK cũ.** Chúng mô tả target code, không thay compiler implementation.

### 6.5. Chẩn đoán annotation processing trong Gradle

Khi kiểm tra dự án thật có thể dùng:

~~~bash
./gradlew clean compileJava --info
./gradlew compileTestJava --info
./gradlew dependencies --configuration annotationProcessor
./gradlew dependencies --configuration testAnnotationProcessor
~~~

Trong bài học này, lệnh chỉ là hướng dẫn thực hành. Với một migration thực tế, cần kiểm tra Gradle wrapper/version hỗ trợ JDK mục tiêu trước khi thử các lệnh.

Có thể tạm thêm compiler arguments phục vụ chẩn đoán:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '-XprintRounds',
        '-XprintProcessorInfo'
    ]
}
~~~

Các arguments này nên được dùng có kiểm soát; không cần giữ log quá chi tiết cho mọi CI build nếu gây nhiễu.

## 7. Maven 3: compiler plugin và annotationProcessorPaths

Với Maven 3 và Maven Compiler Plugin 3.x, cách cấu hình quen thuộc là **annotationProcessorPaths**.

Ví dụ:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.14.1</version>
      <configuration>
        <release>21</release>
        <annotationProcessorPaths>
          <path>
            <groupId>org.mapstruct</groupId>
            <artifactId>mapstruct-processor</artifactId>
            <version>1.6.3</version>
          </path>
        </annotationProcessorPaths>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Các version trong ví dụ chỉ minh họa cấu trúc. Thực tế cần kết hợp version của annotation API, processor, Maven Compiler Plugin, JDK và framework mục tiêu theo tài liệu nhà cung cấp.

Thông thường module source còn cần dependency **org.mapstruct:mapstruct** để tham chiếu annotation **@Mapper**. Processor artifact riêng không thay thế annotation API.

### 7.1. Chỉ định annotationProcessors nếu cần

~~~xml
<configuration>
  <annotationProcessors>
    <annotationProcessor>
      org.mapstruct.ap.MappingProcessor
    </annotationProcessor>
  </annotationProcessors>
</configuration>
~~~

Cấu hình cụ thể phải phù hợp artifact processor thực sự; nếu ứng dụng dùng nhiều processor, liệt kê đầy đủ các processor cần chạy hoặc chọn cơ chế processor path được quản lý tường minh.

Một processor có thể phụ thuộc processor khác hoặc hỗ trợ thứ tự/phối hợp đặc thù. Không nên tùy tiện loại một processor chỉ vì không thấy source của nó dùng annotation trực tiếp.

### 7.2. proc=full là biện pháp chuyển tiếp

Các phiên bản Maven Compiler Plugin có hỗ trợ cấu hình **proc** có thể truyền **-proc:full**:

~~~xml
<configuration>
  <proc>full</proc>
</configuration>
~~~

Điều này có thể giúp duy trì behavior trên JDK 23 khi dự án legacy chưa tách processors. Nhưng nó không bảo đảm chỉ chạy những processor mà nhóm tin cậy.

Một hướng bền vững hơn là định nghĩa **annotationProcessorPaths** và/hoặc danh sách processor rõ ràng, rồi kiểm tra dependency transitive của processor.

### 7.3. Lưu ý testCompile

Maven Compiler Plugin cũng compile source tests; cấu hình đường đi processor và dependency cho test phải được xác nhận riêng theo plugin version và cách tổ chức module. Không kết luận test annotation processing hoạt động chỉ vì **mvn compile** thành công.

## 8. Maven 4 và Compiler Plugin 4.x

Với Maven 4 và Maven Compiler Plugin 4.x, tài liệu chính thức giới thiệu cách khai báo processor bằng dependencies có **type** thích hợp, chẳng hạn:

- **processor**
- **classpath-processor**
- **modular-processor**

Ví dụ mang tính cấu trúc:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.mapstruct</groupId>
    <artifactId>mapstruct</artifactId>
    <version>1.6.3</version>
  </dependency>
  <dependency>
    <groupId>org.mapstruct</groupId>
    <artifactId>mapstruct-processor</artifactId>
    <version>1.6.3</version>
    <type>classpath-processor</type>
  </dependency>
</dependencies>
~~~

Cần dùng cách khai báo khớp với plugin và JDK thực tế. **annotationProcessorPaths** thuộc hướng Maven Compiler Plugin 3.x và đã được thay bằng dependency types trong hướng dẫn 4.x.

Không copy cấu hình Maven 4 vào dự án Maven 3 rồi giả định type processor được xử lý giống nhau. Xác định versions đang dùng trước khi migration.

### 8.1. Tại sao Maven phân biệt classpath processor với modular processor?

Processor được đóng gói và phát hiện theo module path có yêu cầu khác processor JAR truyền thống trên classpath. Nếu chọn sai loại path:

- Processor có thể không được tìm thấy.
- Service provider metadata không khớp.
- Dependencies của processor không đọc được theo module graph.
- Processor không có quyền truy cập compiler APIs hoặc module cần thiết.

Chỉ sử dụng **modular-processor** khi processor artifact thực sự được tổ chức để chạy theo cơ chế module phù hợp. Không suy luận dựa trên tên artifact.

## 9. Khi module có module-info.java

JPMS ảnh hưởng cách khai báo dependency ở compile time và cách tìm processors.

Ví dụ module ứng dụng:

~~~java
module example.app {
    requires example.annotation.api;
}
~~~

Trong khi đó, processor có thể nằm trên **processor path** và không cần được khai báo như runtime dependency trong module-info của ứng dụng. Nếu processor được viết như một named module, có thể cần **provides javax.annotation.processing.Processor with ...** trong descriptor và được tìm trên **--processor-module-path**.

Ví dụ processor module minh họa:

~~~java
module example.greeting.processor {
    requires java.compiler;
    requires example.annotation.api;

    provides javax.annotation.processing.Processor
        with example.processor.GreetingProcessor;
}
~~~

Đây là mô hình minh họa; processor phải được đóng gói cùng dependencies/descriptor phù hợp. **requires java.compiler** cung cấp API chuẩn JSR 269.

### 9.1. API JSR 269 không thuộc jdk.compiler internals

**javax.annotation.processing** và phần lớn language-model APIs thuộc module **java.compiler**, là API chuẩn.

Một số công cụ nâng cao lại dựa trên **com.sun.tools.javac.\*** thuộc phần implementation của **jdk.compiler**. Đây là ranh giới khác:

- JDK nâng version có thể thay internal compiler AST.
- Strong encapsulation có thể chặn truy cập implementation internals.
- **--add-exports** và **--add-opens** đôi khi xuất hiện như workaround trong tài liệu vendor.
- Workaround cho một JDK không bảo đảm vẫn đúng ở JDK tiếp theo.

Không nên tự thêm cờ mở tất cả package **jdk.compiler** khi gặp lỗi processor. Trước hết xác định processor/version và mức hỗ trợ JDK chính thức.

### 9.2. Một build modular cần xem cả hai module graph

Có thể tồn tại:

1. Module graph của **source ứng dụng** đang compile.
2. Module/path để **nạp processor** và dependency của nó.

Cấu hình đúng cho module app không tự động bảo đảm processor được tìm đúng. Ngược lại, processor chạy tốt không có nghĩa generated source tương thích module-info của ứng dụng.

## 10. Lombok: trường hợp đặc biệt khi nâng JDK

Lombok dùng annotation như **@Getter**, **@Builder**, **@RequiredArgsConstructor** để biến đổi code ở quá trình compile. Dù gắn vào annotation processing, Lombok có tích hợp vào cấu trúc compiler sâu hơn nhiều processor chỉ dùng model/Filer.

Ví dụ:

~~~java
import lombok.Getter;

@Getter
public class Order {
    private final String id;

    public Order(String id) {
        this.id = id;
    }
}
~~~

Khi nâng JDK, Lombok cũ có thể:

- Không nạp được một compiler internal type.
- Thất bại vì javac AST internals thay đổi.
- Gặp lỗi access tới module **jdk.compiler**.
- Không sinh getter, builder hoặc constructor như trước.
- Hoạt động trong IDE nhưng không hoạt động ở command-line compiler.
- Hoạt động khi compiler là JDK cũ nhưng thất bại trên JDK mới dù **--release** giữ nguyên.

### 10.1. Hướng giải quyết

1. Ghi JDK chạy compiler, Gradle/Maven và Lombok versions.
2. Nâng Lombok lên bản hỗ trợ JDK mục tiêu theo thông báo chính thức.
3. Khai báo Lombok trong processor path phù hợp.
4. Nếu source test dùng Lombok, cấu hình test annotation processing.
5. Rebuild sạch để tránh class file/generated output cũ.
6. Kiểm tra IDE plugin/import settings riêng nếu IDE sử dụng compiler khác.
7. Không xem workaround **--add-opens** là giải pháp dài hạn.

Ví dụ Gradle:

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok:VERSION_HO_TRO_JDK'
    annotationProcessor 'org.projectlombok:lombok:VERSION_HO_TRO_JDK'

    testCompileOnly 'org.projectlombok:lombok:VERSION_HO_TRO_JDK'
    testAnnotationProcessor 'org.projectlombok:lombok:VERSION_HO_TRO_JDK'
}
~~~

Tên **VERSION_HO_TRO_JDK** là placeholder phải thay bằng release thật. Không để nguyên placeholder trong build production.

## 11. MapStruct: generated mapper và processor path

MapStruct thường có:

- **mapstruct**: annotation API và runtime integration cần thiết.
- **mapstruct-processor**: phần sinh implementation khi compile.

Ví dụ:

~~~java
import org.mapstruct.Mapper;

@Mapper
public interface CustomerMapper {
    CustomerDto toDto(CustomerEntity entity);
}
~~~

Processor có thể sinh một class như **CustomerMapperImpl**. Nếu processor không chạy:

- Source interface vẫn compile được vì annotation API tồn tại.
- Generated implementation không có trong clean build.
- Compile/test/runtime thiếu implementation theo cách framework tìm mapper.
- CI có thể thất bại khác local nếu local còn generated files.

### 11.1. Cấu hình Gradle

~~~groovy
dependencies {
    implementation 'org.mapstruct:mapstruct:VERSION_DUOC_CHON'
    annotationProcessor 'org.mapstruct:mapstruct-processor:VERSION_DUOC_CHON'
}
~~~

Điểm quan trọng là processor nằm trong **annotationProcessor**, không chỉ trong **implementation**.

### 11.2. Kết hợp Lombok và MapStruct

Một module dùng cả Lombok và MapStruct cần quan tâm cách hai công cụ phối hợp với các type được Lombok tạo/biến đổi. Tùy phiên bản, có thể cần artifact tích hợp được vendor khuyến nghị.

Không sửa bằng cách thay thứ tự ngẫu nhiên các dependency cho đến khi compile qua. Hãy xác định phiên bản được hỗ trợ của Lombok, MapStruct và công cụ tích hợp, rồi ghi rõ processor dependencies.

### 11.3. Generated source và contract

Generated mapper implementation phải được xem là build output. Không nên dùng source generated cũ đã commit hoặc stale trong build directory để che lỗi mới. Nếu cần kiểm tra sự thay đổi mapping giữa release, so sánh behavior của mapper với sample dữ liệu, không chỉ kiểm tra tên file **MapperImpl** tồn tại.

## 12. JPA metamodel, QueryDSL và framework codegen

Annotation processing có thể sinh các type hỗ trợ query type-safe.

Ví dụ JPA Criteria metamodel:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class CustomerEntity {
    @Id
    private Long id;

    private String name;
}
~~~

Một JPA metamodel processor có thể sinh class như **CustomerEntity_**. Code khác có thể dùng:

~~~java
root.get(CustomerEntity_.name);
~~~

Nếu processor không chạy, type metamodel không được sinh và compile có thể thất bại.

### 12.1. Đổi javax sang jakarta là thay đổi khác với JDK 23

Trong các migration Java EE → Jakarta EE, annotation namespace có thể chuyển từ:

~~~text
javax.persistence.Entity
~~~

sang:

~~~text
jakarta.persistence.Entity
~~~

Processor cũ chỉ hỗ trợ annotation javax có thể không nhận diện annotation jakarta dù nó vẫn được chạy. Khi đó cần phân biệt hai câu hỏi:

1. Processor **có được kích hoạt** hay không?
2. Processor **có hỗ trợ annotations và framework version hiện tại** hay không?

Thêm **-proc:full** không tự khiến một processor cũ nhận biết **jakarta.persistence.Entity**.

### 12.2. QueryDSL và các processor khác

Một dự án có thể dùng QueryDSL, AutoValue, Dagger, Immutables, Hibernate Processor hoặc công cụ nội bộ. Với mỗi công cụ, ghi rõ:

- Annotation API artifact.
- Processor artifact.
- Processor class hoặc service registration.
- Java/JDK compatibility.
- Output type và vị trí lưu.
- Transitive dependencies.
- Test source requirements.
- Runtime library nếu có.

Không dùng chung một kết luận “mọi processor hoạt động như MapStruct”; một số sinh source, một số sinh resources, một số tạo lỗi compile, một số tích hợp compiler internals.

## 13. Annotation processor và công cụ kiểm thử

Processor chạy trong **compileJava** và **compileTestJava** (hoặc các task tương đương) có thể khác nhau.

### 13.1. Vì sao test thất bại sau migration?

Ví dụ:

- Main sources đã có processor, test sources chưa khai báo **testAnnotationProcessor**.
- Test fixtures cần generated helper classes.
- Processor cho test source bị JDK 23 tắt vì cấu hình implicit.
- Một library test sử dụng các annotation để sinh metadata.
- Test runner dùng JDK khác compiler.
- Test có generated source stale tại local nhưng không có trong CI.

Nên xác định giai đoạn chính xác:

~~~text
compileJava
    |
    v
Generated main sources/classes
    |
    v
compileTestJava
    |
    v
Generated test sources/classes
    |
    v
Test execution
~~~

Nếu lỗi ở **compileTestJava**, không nên vội sửa **test runtimeClasspath**. Hãy kiểm tra compile classpath/processor path của test source set.

### 13.2. Annotation processor không phải JUnit test engine

JUnit Jupiter sử dụng **@Test** để khám phá và chạy test ở runtime. Việc ứng dụng có **@Test** không có nghĩa nó cần một JSR 269 annotation processor cho JUnit.

Tương tự, các annotation Spring như **@Component** thường được xử lý bằng cơ chế framework/runtime; không phải mọi annotation đều yêu cầu codegen ở compile time.

Cần nhận diện đúng công cụ nào có vai trò compile-time processor trước khi thêm dependency vào annotationProcessor path.

### 13.3. Không nhầm với Kotlin KAPT/KSP

Nếu dự án đa ngôn ngữ có Kotlin:

- **kapt** xử lý nhiều Java annotation processors cho Kotlin thông qua cơ chế riêng.
- **KSP** là hệ sinh thái processor khác với API Java JSR 269 thuần túy.
- Các plugin và version Kotlin/KSP/KAPT có yêu cầu tương thích riêng.

Thêm cấu hình **annotationProcessor** cho Java source không đồng nghĩa đã cấu hình được processor của Kotlin. Nếu có module Kotlin, xác định từng compilation pipeline.

## 14. Compiler runtime, target release và toolchains

Một migration thường có ba con số khác nhau:

| Thành phần | Ví dụ | Ảnh hưởng |
|---|---|---|
| JDK dùng chạy javac | 23 | Compiler API, processor runtime, mặc định APT |
| Target release | 17 | Source rules, Java SE API và class-file target |
| JDK runtime của ứng dụng | 17 hoặc 21 | Khả năng chạy generated bytecode/dependencies |

Ví dụ:

~~~text
JDK 23 javac
     |
     +--> Processor chạy trên JDK 23
     |
     +--> --release 17
              |
              v
     Generated source + bytecode target 17
              |
              v
     Application runtime 17
~~~

Không thể chạy processor chỉ hỗ trợ JDK 17 với kỳ vọng nó sẽ “thấy JDK 17” vì source target là release 17. Processor được nạp bởi compiler và cần tương thích compiler runtime.

### 14.1. Generated source có thể dùng API quá mới

Nếu processor sinh:

~~~java
var text = "hello";
~~~

hoặc dùng một API chỉ có trên JDK mới hơn target, compiler có thể từ chối khi đang dùng **--release** tương ứng. Nếu processor ghi bytecode trực tiếp, giới hạn còn phụ thuộc thư viện bytecode và version class file nó tạo.

Một processor có hỗ trợ chạy trên JDK mới nhưng sinh code dùng Java API quá mới **vẫn có thể phá migration tới runtime cũ**.

### 14.2. Phân biệt JDK chạy build tool và JDK compile

Gradle daemon, Maven process, forked javac, Gradle toolchain và test JVM không luôn là cùng một JDK. Với lỗi annotation processor, cần xác định:

- **javac phiên bản nào đang chạy?**
- **Processor JAR nào đang được nạp?**
- **Module/classpath nào chứa processor?**
- **Source target là release nào?**
- **Output được biên dịch rồi chạy trên JDK nào?**

Không chỉ nhìn **java -version** trong một terminal khác rồi kết luận CI đang dùng đúng compiler.

## 15. Bảo mật chuỗi cung ứng: processor là mã thực thi khi build

Lý do quan trọng của việc thay đổi mặc định JDK 23 là giảm việc vô tình chạy mã trong quá trình build. Annotation processor không phải metadata vô hại: nó là code được javac nạp và thực thi trong môi trường build.

Nếu một dependency không đáng tin cậy chứa service registration cho processor, implicit discovery trước đây có thể khiến processor đó chạy mà developer không chủ động chọn.

Rủi ro có thể bao gồm:

- Đọc biến môi trường build.
- Truy cập file trong workspace.
- Thực hiện network requests nếu môi trường cho phép.
- Tạo hoặc thay generated code không đúng.
- Làm chậm build hoặc gây lỗi không ổn định.
- Thay đổi hành vi theo môi trường CI.
- Dựa vào compiler internals hoặc runtime permissions không mong đợi.

Chính sách nên gồm:

1. Chỉ khai báo processor đã được kiểm soát.
2. Pin version và nguồn dependency.
3. Rà soát transitive processor dependencies.
4. Tách processor path khỏi runtime dependencies.
5. Dùng CI với quyền tối thiểu và bảo vệ secrets.
6. Áp dependency verification/SBOM phù hợp.
7. Không dùng **-proc:full** để quét classpath rộng khi có thể chọn processor cụ thể.
8. Theo dõi thay đổi trong processor service metadata.

**Một build compile thành công không chứng minh processor JAR an toàn.** Đây là vấn đề supply-chain độc lập với độ đúng của generated code.

## 16. Chẩn đoán lỗi khi nâng JDK

### 16.1. Những triệu chứng điển hình

| Triệu chứng | Nguyên nhân thường gặp | Điểm điều tra |
|---|---|---|
| **cannot find symbol** cho generated type | Processor không chạy hoặc output không có | Processor path, javac options |
| **No implementation was created** | Generated implementation thiếu | MapStruct/DI processor |
| **cannot find symbol getX()/builder()** | Lombok không hoạt động | Lombok/JDK support, processor setup |
| JPA metamodel **Entity_** thiếu | JPA processor không chạy hoặc namespace không đúng | jakarta/javax, processor version |
| **Processor ... not found** | Processor class không có trên path được chọn | -processor, processor path, service metadata |
| **NoClassDefFoundError** trong processor | Thiếu dependency của chính processor | Processor dependency graph |
| **IllegalAccessError** đến **jdk.compiler** internals | Processor dùng internal compiler API không tương thích | Lombok/compiler version |
| **InaccessibleObjectException** | Strong encapsulation chặn reflective access | Stack trace, caller module |
| **NoSuchFieldError** từ javac AST | Processor cũ phụ thuộc cấu trúc compiler thay đổi | Vendor/JDK support |
| **UnsupportedClassVersionError** | Processor hoặc dependency được build bằng JDK mới hơn JVM chạy compiler | Class-file version, toolchain |
| **FilerException** | Processor cố tạo file trùng | Output ownership, processing rounds |
| Processor chạy ở IDE nhưng CI không chạy | IDE/compiler/build path khác nhau | Repro CLI clean build |
| Source generated tồn tại local nhưng thiếu trên CI | Output cũ chưa dọn | Build sạch, provenance |
| Compiles but runtime fails | Metadata/resource generated thiếu hoặc lỗi mapping | Contract/integration tests |

Một lỗi có thể có nhiều nguyên nhân. **cannot find symbol** không tự chứng minh là do JDK 23; cần xem processor đã được chạy chưa và generated output có xuất hiện không.

### 16.2. Quy trình triage

1. Chụp log đầy đủ của **compile** thất bại.
2. Ghi JDK vendor/version của compiler thực tế.
3. Ghi Gradle/Maven plugin và processor versions.
4. Kiểm tra compiler options có **-processor**, **--processor-path**, **--processor-module-path** hoặc **-proc:full** không.
5. Kiểm tra processor class và transitive dependencies thực sự có trong path.
6. Nếu có thể, bật **-XprintRounds** và **-XprintProcessorInfo** để quan sát.
7. Xác nhận generated source directory sau clean build.
8. Kiểm tra **source/API target** và JDK runtime.
9. Nếu processor đã chạy nhưng không sinh output, xem annotation namespace, supported source version và diagnostics.
10. Sau khi xử lý, chạy test tích hợp/consumer cần generated output.

Đừng thêm hàng loạt cờ **--add-opens** trước khi biết lỗi nằm ở processor activation, discovery hay compiler internals.

### 16.3. Phân biệt "không tìm thấy processor" với "processor không xử lý annotation"

Hai trạng thái khác nhau:

~~~text
A. javac không nạp GreetingProcessor
   -> Không có processing rounds từ processor đó

B. javac đã nạp GreetingProcessor
   -> Nhưng getElementsAnnotatedWith(...) trả rỗng
   -> Có thể annotation không phù hợp, target/namespace khác
~~~

Nếu B xảy ra, việc thêm processor dependency lần nữa không giải quyết được. Cần xem **SupportedAnnotationTypes**, annotation trong source, mô hình module và phiên bản framework.

### 16.4. Chẩn đoán bằng clean build

Để tránh stale generated files, kiểm tra với một output directory sạch. Trên dự án thực, dùng cơ chế clean/build tương ứng của tool trong môi trường được kiểm soát.

Không xóa thủ công cả workspace hoặc file human-owned. Generated directory phải thuộc build tool và có ownership rõ ràng trước khi dọn.

## 17. Incremental compilation và build cache

Annotation processors có thể ảnh hưởng incremental build:

- Processor **isolating** sinh output phụ thuộc vào từng input cụ thể.
- Processor **aggregating** tổng hợp thông tin từ nhiều input.
- Processor không khai báo rõ cách phụ thuộc đầu vào có thể làm Gradle phải chạy lại nhiều hơn.
- Processor sinh output không quyết định (timestamp, random, thứ tự không ổn định) gây cache miss hoặc kết quả không tái lập.
- Build cache có thể che lỗi processor không chạy trong một môi trường nếu output được lấy từ lần build khác.

Một migration nên kiểm tra:

- Build sạch có sinh output đúng.
- Build incremental sau khi sửa annotation có cập nhật output.
- Khi xóa annotation, output không còn stale.
- Cùng input/build settings cho kết quả tương đương giữa local và CI.
- Không có processor ghi ra thư mục không do build tool quản lý.
- Generated files không bị source control hoặc generator khác ghi đè ngoài ý muốn.

Không giải quyết lỗi bằng cách vô hiệu hóa toàn bộ incremental compilation mà không có evidence; nó có thể làm build chậm nhưng vẫn không sửa processor path sai.

## 18. Kế hoạch migration qua JDK 23 trở lên

### Pha A — Inventory

Lập danh sách processor theo module:

| Module | Processor | Annotation API | Output | Test source? | JDK support |
|---|---|---|---|---|---|
| api | MapStruct | mapstruct | MapperImpl | Có/Không | Theo vendor |
| persistence | Hibernate metamodel | jakarta.persistence | Entity_ | Có/Không | Theo vendor |
| domain | Lombok | lombok | Compiler-generated members | Có/Không | Theo vendor |
| plugin | Custom processor | annotation-api | Java source/resources | Có/Không | Nội bộ |

Các hàng là mẫu, không khẳng định một module cụ thể đang sử dụng công cụ nào.

### Pha B — Tách dependencies

- Xác định annotation API cần compile.
- Xác định processor JAR và phụ thuộc transitive.
- Đưa processor lên processor path/configuration chính thức.
- Không dựa vào việc processor tình cờ nằm trong implementation/runtime classpath.
- Pin version theo vendor support.
- Ghi rõ main/test compilation.

### Pha C — Kiểm tra compiler settings

- JDK compile thực tế.
- --release/source/target.
- -processor, --processor-path, --processor-module-path hoặc -proc.
- Module/classpath layout.
- Maven/Gradle compiler plugin versions.
- CI/IDE configuration.

### Pha D — Rebuild và kiểm chứng generated outputs

- Clean build từ artifact/source baseline.
- Quan sát processor rounds khi cần.
- Kiểm tra generated source/class/resource có mặt.
- Kiểm tra generated types compile với target release.
- Chạy consumer/integration tests đại diện.
- Xác minh test annotation processing nếu test source dùng.
- Ghi log, versions và checksum/evidence.

### Pha E — Cutover

- Nâng JDK compiler lên target.
- Giữ processor declaration tường minh.
- Theo dõi build error và runtime behavior.
- Bỏ workaround tạm nếu không còn cần.
- Cập nhật template/build conventions để module mới không lặp lại implicit discovery.
- Đảm bảo các build tool và processor versions không bị lệch giữa môi trường.

## 19. Ma trận kiểm thử đề xuất

| Trường hợp | JDK compile | Cấu hình APT | Kỳ vọng |
|---|---|---|---|
| Baseline | JDK 21 | Implicit classpath discovery | Có thể chạy nhưng phát note |
| Transition | JDK 21 | Explicit processor path | Generated output ổn định |
| Target | JDK 23+ | Không có APT config | Processor không tự kích hoạt |
| Target | JDK 23+ | Explicit processor path/name | Processor chạy nếu tương thích |
| Target | JDK 23+ | -proc:none | Không tạo output APT |
| Target | JDK 23+ | -proc:only | Có output processing, không compile đầy đủ |
| Target | JDK 23+ | -proc:full | Processing + compile theo discovery được phép |
| Cross-target | JDK 23+, --release 17 | Explicit processor config | Generated code phù hợp Java 17 |
| Test source | Target JDK | Test processor path | Generated test sources được tạo |
| IDE | IDE compiler | IDE processing enabled | Output phù hợp CLI |
| Clean CI | Target JDK | Pinned versions | Không dựa vào stale artifacts |

Mục đích không phải chạy mọi tổ hợp cho mọi module; chọn các tình huống phù hợp với processors và support policy thực tế.

### 19.1. Acceptance criteria nên bao gồm artifact cụ thể

Ví dụ với MapStruct:

~~~text
Given: CustomerMapper annotated with @Mapper
When: clean compile on target JDK
Then:
  - Selected MapStruct processor was loaded
  - CustomerMapperImpl was generated
  - Generated implementation compiled
  - Mapper behavior test passed
  - No dependency on stale generated files
~~~

Với JPA metamodel:

~~~text
Given: CustomerEntity with JPA annotations
When: clean compile on target JDK
Then:
  - Processor recognizes the jakarta/javax namespace in use
  - CustomerEntity_ source/class generated
  - Criteria API consumer compiles
~~~

Với Lombok:

~~~text
Given: @Getter / @Builder in source
When: clean compile on target JDK
Then:
  - Lombok version supports the compiler
  - Expected member access in consumer compiles
  - Test source using Lombok also compiles
~~~

Đây là tiêu chí để nhóm kiểm chứng sau khi migration; không thay thế nội dung kiểm thử cụ thể của ứng dụng.

## 20. Những sai lầm thường gặp

### 20.1. Chỉ thêm dependency vào implementation

Processor không nhất thiết được chạy vì dependency hiện diện trong compile/runtime classpath.

**Giải pháp:** dùng **annotationProcessor** với Gradle hoặc processor path/dependency type đúng với Maven version.

### 20.2. Chỉ ẩn note của JDK 21

Ẩn note không thay đổi cơ chế kích hoạt. JDK 23 có thể vẫn không chạy processor.

**Giải pháp:** cấu hình APT rõ ràng.

### 20.3. Dùng -proc:full với classpath rộng và xem là hoàn tất

Nó giúp duy trì hành vi cũ nhưng có thể kích hoạt processor ngoài ý muốn.

**Giải pháp:** giới hạn processor path và danh sách processor được tin cậy.

### 20.4. Cho rằng -release 17 chạy processor bằng JDK 17

Processor chạy trong môi trường compiler đã chọn, không phải target runtime.

**Giải pháp:** kiểm tra JDK compile, processor compatibility và generated code target riêng.

### 20.5. Không tách test processor path

compileJava thành công nhưng compileTestJava thiếu processor.

**Giải pháp:** cấu hình main/test source sets riêng.

### 20.6. Giữ generated files từ build cũ

Mã sinh ra từ lượt compile cũ có thể che lỗi JDK 23 không chạy processor.

**Giải pháp:** clean build có provenance và test từ fresh checkout.

### 20.7. Trộn lỗi JDK 23 với lỗi javax → jakarta

Processor có chạy nhưng không hiểu annotation framework mới.

**Giải pháp:** kiểm tra annotation namespace và vendor processor version.

### 20.8. Tự thêm --add-opens bừa bãi

Một processor không chạy vì thiếu activation không thể được sửa bằng mở quyền module. Với Lombok/compiler internals, workaround có thể phụ thuộc JDK và không bền.

**Giải pháp:** xác định lỗi gốc; nâng processor phù hợp.

### 20.9. Đổi toolchain mà không xét build plugins

JDK compiler mới có thể được Gradle/Maven plugin cũ hỗ trợ không đầy đủ.

**Giải pháp:** xác nhận ma trận hỗ trợ compiler plugin, processor và JDK.

### 20.10. Nhầm JUnit/Spring annotations với annotation processing

Không phải mọi annotation đều kích hoạt processor.

**Giải pháp:** xác định có processor JSR 269 thực sự hay không trước khi cấu hình dependency.

### 20.11. Tạo generated source trong source directory human-owned

Làm lẫn code sinh ra với code được bảo trì thủ công, gây stale files và khó rollback.

**Giải pháp:** dùng build-owned generated output directory, xác định ownership và clean behavior.

### 20.12. Không kiểm soát processor supply chain

Processor chạy code trong build, có thể có quyền truy cập workspace và secrets của CI.

**Giải pháp:** pin artifact, kiểm chứng dependency và chỉ kích hoạt processor cần thiết.

## 21. Checklist trước khi kết luận migration thành công

### Inventory

- [ ] Đã liệt kê processors theo module và source set.
- [ ] Đã phân biệt annotation API và processor artifact.
- [ ] Đã xác nhận phiên bản compiler JDK thực sự được dùng.
- [ ] Đã ghi Gradle/Maven Compiler Plugin versions.
- [ ] Đã xác định output là source, class hay resources.
- [ ] Đã kiểm tra processor nội bộ hoặc dùng javac internals.

### Cấu hình

- [ ] Processor được khai báo explicit trên path thích hợp.
- [ ] Không phụ thuộc implicit discovery từ classpath trên JDK 23+.
- [ ] Đã cấu hình test annotation processing khi cần.
- [ ] Target release và JDK chạy compiler được kiểm tra riêng.
- [ ] Module path/processor module path phù hợp nếu dùng JPMS.
- [ ] Processor dependencies được pin và kiểm soát nguồn.
- [ ] Không mở JDK internals chỉ để che lỗi thiếu activation.

### Kiểm chứng

- [ ] Clean compile sinh đủ generated files.
- [ ] Không phụ thuộc stale output từ build cũ.
- [ ] Generated source compile với target release.
- [ ] Consumer/integration tests đại diện đạt.
- [ ] Main và test source sets được kiểm tra.
- [ ] CI và IDE dùng cấu hình có thể tái lập.
- [ ] Có log/diagnostics về processor thực sự được nạp.
- [ ] Không có thay đổi behavior ngoài dự kiến ở generated code.
- [ ] Có phương án rollback hoặc giữ compiler/processor version cũ khi cần.

### Bảo mật và vận hành

- [ ] Chỉ các processor có chủ đích được phép chạy.
- [ ] Artifact và transitive dependencies được kiểm chứng.
- [ ] CI secrets và quyền môi trường build được kiểm soát.
- [ ] Các workaround tạm có owner, lý do và ngày xem xét lại.
- [ ] Build conventions được cập nhật để các module mới không tái tạo lỗi.

## 22. Nguồn đặc tả và tài liệu đối chiếu

Các nguồn nên đọc theo JDK/tool version đích:

- **JDK 21 Release Notes – cảnh báo implicit annotation processing:** https://www.oracle.com/java/technologies/javase/21-relnote-issues.html
- **JDK 23 Release Notes – annotation processing disabled by default (JDK-8321314):** https://www.oracle.com/java/technologies/javase/23all-relnotes.html
- **OpenJDK Quality Outreach – thay đổi mặc định JDK 23:** https://inside.java/2024/06/18/quality-heads-up/
- **javac command documentation:** https://docs.oracle.com/en/java/javase/23/docs/specs/man/javac.html
- **Package javax.annotation.processing:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/package-summary.html
- **Gradle Java Library Plugin – annotationProcessor:** https://docs.gradle.org/current/userguide/java_library_plugin.html
- **Maven Compiler Plugin 3.14.1 – annotationProcessorPaths:** https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.14.1/compile-mojo.html
- **Maven Compiler Plugin 4.x – annotation processors:** https://maven.apache.org/components/plugins/maven-compiler-plugin-4.x/examples/annotation-processor.html
- **IntelliJ IDEA annotation processing settings:** https://www.jetbrains.com/help/idea/annotation-processors-support.html

Các phiên bản công cụ và tùy chọn có thể tiếp tục thay đổi. Khi migration thực tế, phải đọc release notes của **compiler JDK**, **build tool/compiler plugin** và **processor library** đang dùng, không chỉ đối chiếu một version number.

---

**Kết luận:** Điểm gãy quan trọng khi nâng JDK là **annotation processor từng được kích hoạt ngầm nay cần cấu hình tường minh từ JDK 23**. Hãy xác định processor và dependency thực sự cần, tách processor path khỏi classpath thông thường, kiểm tra source set main/test, bảo đảm processor tương thích với JDK compiler và generated code phù hợp target release. Không giải quyết bằng việc ẩn warning hay dựa vào stale generated files. Một build đáng tin cậy cần khai báo rõ ai được chạy trong giai đoạn compile, tạo ra những artifact nào và chứng cứ nào xác nhận output đúng sau migration.
