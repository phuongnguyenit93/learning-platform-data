# Đóng gói, đăng ký và kiểm tra annotation processor từ một dự án sử dụng

Một annotation processor không tự hoạt động chỉ vì class của nó đã được biên dịch. Để dự án khác dùng được, ta cần **đóng gói processor cùng dependencies phù hợp**, **đăng ký để compiler phát hiện hoặc chọn bằng tên tường minh**, **cấu hình đúng processor path và compile classpath**, rồi **kiểm tra cả generated source lẫn compiled class/output runtime**. Đây là vòng đời quan trọng khi xây dựng processor thành một công cụ có thể tái sử dụng.

Bài này minh họa đầy đủ bằng **Java 17+**, không cần framework bên ngoài: dự án cung cấp processor đóng thành một JAR, dự án ứng dụng có annotation trên một class, processor sinh thêm Java source, `javac` biên dịch generated source và ứng dụng gọi class được sinh ra. Sau đó ta kiểm tra cơ chế service registration, chế độ chọn processor bằng `-processor`, tác động của các option và cách tích hợp vào build system.

## 1. Bức tranh kiến trúc: hai vai trò và ba bộ artifact

~~~text
DỰ ÁN PROCESSOR (được build trước)
  Annotation API: @GenerateGreeting
  Processor implementation: GreetingProcessor implements Processor
  META-INF/services/javax.annotation.processing.Processor
                   |
                   v
       greeting-processor.jar
                   |
             +-----+-------------------+
             |                         |
             v                         v
DỰ ÁN SỬ DỤNG (javac)       Compiler tìm/lấy processor
  @GenerateGreeting         qua -processorpath và SPI
  Trigger.java                          |
  App.java                              v
             +----------> processing rounds
                             |
               Filer.createSourceFile(...)
                             |
                   -s build/generated/
                     GeneratedHello.java
                             |
                             v
                   compile generated source
                             |
                   -d build/classes/
          App.class, Trigger.class, GeneratedHello.class
                             |
                             v
                     java -cp build/classes ...
~~~

Ba nhóm cần phân biệt:

1. **Annotation declaration**: kiểu Java biểu diễn annotation, để mã nguồn của *consumer* dùng được `@GenerateGreeting`. Consumer cần thấy kiểu này trên compile classpath hoặc module path.
2. **Processor implementation**: code chạy **trong quá trình biên dịch**, thao tác trên mô hình elements/types của compiler và sinh output. Compiler phải load được processor từ *processor path* hoặc *processor module path* phù hợp.
3. **Generated code và runtime classes**: source được processor sinh có thể được compiler biên dịch thành class; ứng dụng chạy cần các generated classes và runtime dependencies thích hợp, **không mặc nhiên cần processor implementation** khi đã biên dịch xong.

Ví dụ gọn bên dưới đóng annotation API và processor trong **cùng một JAR** để dễ thử. Trong sản phẩm thật, việc tách thành hai artifact thường tốt hơn: một artifact annotation API nhẹ để consumer compile, một artifact processor để build tool dùng khi annotation processing. Đây là lựa chọn thiết kế, không phải quy tắc bắt buộc của Java.

## 2. Processor phải thực hiện hợp đồng nào?

Một annotation processor được viết bằng API `javax.annotation.processing`, thông thường kế thừa `AbstractProcessor` và override `process(...)`.

Các thành phần quan trọng:

| Thành phần | Vai trò |
| --- | --- |
| `javax.annotation.processing.Processor` | Hợp đồng processor được compiler gọi |
| `AbstractProcessor` | Lớp nền hỗ trợ lifecycle/khai báo metadata |
| `@SupportedAnnotationTypes` | Nêu tên những annotation processor xử lý |
| `@SupportedSourceVersion` | Khai báo source version processor hỗ trợ |
| `process(Set<? extends TypeElement>, RoundEnvironment)` | Xử lý các annotation và elements theo *round* |
| `processingEnv.getFiler()` | Tạo generated source, class hoặc resource bằng cơ chế được compiler quản lý |
| `processingEnv.getMessager()` | Phát diagnostic (NOTE, WARNING, ERROR) cho compiler |
| `RoundEnvironment.processingOver()` | Cho biết round cuối khi processing sắp kết thúc |

**Không gọi trực tiếp method `process(...)` từ ứng dụng tại runtime**. Consumer không biến processor thành một đối tượng nghiệp vụ để tự chạy; compiler/build system thiết lập `ProcessingEnvironment` rồi gọi processor trong quá trình compile.

**Tìm thấy processor chưa có nghĩa processor sinh mã.** Processor phải hỗ trợ annotation phù hợp, có elements cần xử lý, không lỗi trong vòng xử lý, và thực sự gọi một phương thức tạo output như `Filer.createSourceFile(...)`.

## 3. Dự án mẫu: cấu trúc hai nguồn tách biệt

Tạo cây thư mục sau. Các lệnh compile được chạy từ thư mục gốc `sample`, nơi có hai nhánh `processor` và `consumer`:

~~~text
sample/
├── processor/
│   ├── src/
│   │   └── com/acme/
│   │       ├── annotations/
│   │       │   └── GenerateGreeting.java
│   │       └── processor/
│   │           └── GreetingProcessor.java
│   └── resources/
│       └── META-INF/
│           └── services/
│               └── javax.annotation.processing.Processor
├── consumer/
│   └── src/
│       └── com/acme/app/
│           ├── Trigger.java
│           └── App.java
└── build/
    ├── processor-classes/
    ├── greeting-processor.jar
    ├── generated/
    └── classes/
~~~

Thư mục `build` sẽ được tạo khi chạy lệnh. **Không đặt service descriptor nhầm ở `processor/src/META-INF/...` nếu bước đóng gói chỉ copy compiled classes**: nó là *resource* phải được đưa vào JAR với đúng vị trí. Trong ví dụ, resource nằm ở `processor/resources` và được thêm vào JAR ở bước riêng.

### 3.1. Annotation API

**File `processor/src/com/acme/annotations/GenerateGreeting.java`:**

~~~java
package com.acme.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateGreeting {
}
~~~

`RetentionPolicy.SOURCE` phù hợp vì annotation chỉ cần hiện diện trong source để compiler/processor xử lý; ứng dụng không cần đọc annotation này bằng reflection tại runtime. Đây **không** phải điều kiện bắt buộc cho mọi processor: có annotation cần `CLASS` hoặc `RUNTIME` vì lý do khác.

### 3.2. Processor sinh một class cố định cho demo

**File `processor/src/com/acme/processor/GreetingProcessor.java`:**

~~~java
package com.acme.processor;

import com.acme.annotations.GenerateGreeting;
import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("com.acme.annotations.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (generated
                || round.processingOver()
                || round.getElementsAnnotatedWith(GenerateGreeting.class).isEmpty()) {
            return true;
        }

        generated = true;
        try {
            var file = processingEnv.getFiler()
                    .createSourceFile("com.acme.generated.GeneratedHello");

            try (Writer writer = file.openWriter()) {
                writer.write("package com.acme.generated;\n"
                        + "public final class GeneratedHello {\n"
                        + "  private GeneratedHello() {}\n"
                        + "  public static String message() {\n"
                        + "    return \"hello-from-processor\";\n"
                        + "  }\n"
                        + "}\n");
            }
        } catch (IOException ex) {
            throw new IllegalStateException("Source generation failed", ex);
        }
        return true;
    }
}
~~~

Giải thích kỹ:

- `@SupportedAnnotationTypes` phải trỏ đúng **fully qualified name** của annotation; không dùng tên processor, tên module hay tên class được sinh để thay thế.
- `@SupportedSourceVersion(SourceVersion.RELEASE_17)` cho compiler biết processor tuyên bố hỗ trợ mức nguồn 17. Nó không **tự** đặt target release của consumer; lệnh `javac --release 17` mới làm điều đó.
- `getElementsAnnotatedWith(GenerateGreeting.class)` kiểm tra xem round hiện tại có class được đánh dấu annotation. Nếu không có, processor không sinh file.
- `generated` tránh gọi `createSourceFile` lần thứ hai trong các rounds kế tiếp; nếu tạo trùng tên, `Filer` thường báo `FilerException`.
- `createSourceFile("com.acme.generated.GeneratedHello")` nhận **canonical name** của class mới; `Filer` ánh xạ thành `com/acme/generated/GeneratedHello.java` ở source output location.
- `openWriter()` ghi **nội dung Java source hợp lệ**, bao gồm package và class; sau khi writer được đóng, compiler có thể tiếp tục xử lý source đó.
- `return true` báo processor *claim* các annotation đã xử lý của nó; trong một dự án nhiều processor, quyết định claim ảnh hưởng processor nào còn được mời xử lý annotation tương ứng trong round.
- Đây là processor **minh họa sinh đúng một class cố định cho một compilation**. Một công cụ production thường cần sinh theo từng annotated type, tạo tên ổn định không xung đột và truyền *originating elements* cho `Filer`.

Không nên sử dụng `FileWriter` trực tiếp vào một directory tự đoán trong processor: việc tạo source qua `Filer` giúp compiler theo dõi generated file và xử lý ở các round tiếp theo.

## 4. Đăng ký processor bằng Java Service Provider Interface (SPI)

Khi không chỉ định `-processor <class>`, `javac` có thể khám phá processors thông qua **service provider configuration file** nằm trong JAR trên processor search path.

**Tên entry chính xác trong JAR:**

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Đây là một **file văn bản không có đuôi `.txt`**, không phải directory chỉ để trang trí, cũng không phải file `META-INF/services/com.acme.processor.GreetingProcessor`.

**Nội dung file `processor/resources/META-INF/services/javax.annotation.processing.Processor`:**

~~~text
com.acme.processor.GreetingProcessor
~~~

Một dòng là tên class processor đầy đủ. Có thể đăng ký nhiều providers bằng nhiều dòng, và cấu hình service có thể dùng comment theo cú pháp ServiceLoader. Với ví dụ này, một dòng không có comment là rõ ràng nhất.

Yêu cầu quan trọng:

1. Service file phải nằm **đúng entry path trong JAR** được compiler dùng tìm processors.
2. Nội dung trỏ tới class có thật, đúng package, có thể load từ processor path với dependencies cần thiết.
3. Processor class phải triển khai `Processor` (ở đây qua `AbstractProcessor`), có constructor phù hợp cho cơ chế khởi tạo service provider; ví dụ dùng constructor không tham số công khai ngầm định.
4. Tránh chỉ đóng `GreetingProcessor.class` mà quên `GenerateGreeting.class`: implementation tham chiếu annotation class khi chạy.
5. Tên file service không thay đổi theo tên annotation hay tên ứng dụng. Giao diện SPI vẫn là `javax.annotation.processing.Processor`.

Một file service bị thiếu thường khiến **auto-discovery không tìm được processor**. Ngược lại, dùng `-processor com.acme.processor.GreetingProcessor` có thể chạy processor dù **không có service descriptor**, vì đó là lựa chọn tường minh bỏ qua bước discovery mặc định. Hai cơ chế cần kiểm thử riêng.

## 5. Đóng gói JAR từ dự án processor

### 5.1. Tạo thư mục output

Trong **Bash hoặc shell Linux/macOS**:

~~~bash
mkdir -p build/processor-classes build/generated build/classes
~~~

Trong **PowerShell**:

~~~powershell
New-Item -ItemType Directory -Force -Path build/processor-classes,build/generated,build/classes
~~~

### 5.2. Biên dịch annotation và implementation

Từ `sample/`:

~~~bash
javac --release 17 -d build/processor-classes processor/src/com/acme/annotations/GenerateGreeting.java processor/src/com/acme/processor/GreetingProcessor.java
~~~

Thành công thường không in stdout. Class output:

~~~text
build/processor-classes/
└── com/acme/
    ├── annotations/GenerateGreeting.class
    └── processor/GreetingProcessor.class
~~~

**Chưa chạy processing trên consumer** ở bước này. Chỉ xây dựng processor class và annotation class. Do tệp service descriptor nằm riêng ở `processor/resources`, nó chưa có trong `build/processor-classes` sau khi chạy `javac`.

### 5.3. Đóng JAR kèm cả class và resource

~~~bash
jar --create --file build/greeting-processor.jar -C build/processor-classes . -C processor/resources .
~~~

Giải thích: `-C build/processor-classes .` đưa toàn bộ nội dung class output vào **gốc JAR**; `-C processor/resources .` đưa resources vào **gốc JAR**. Vì thế service descriptor được lưu đúng ở `META-INF/services/...` chứ không nằm sâu dưới `processor/resources` trong JAR.

Kiểm tra danh sách entries:

~~~bash
jar --list --file build/greeting-processor.jar
~~~

Trong danh sách phải thấy các entries quan trọng:

~~~text
com/acme/annotations/GenerateGreeting.class
com/acme/processor/GreetingProcessor.class
META-INF/services/javax.annotation.processing.Processor
~~~

Các entries như `META-INF/`, `META-INF/MANIFEST.MF` và các thư mục trung gian cũng có thể xuất hiện; thứ tự hiển thị không quan trọng.

**Kiểm tra nội dung service file** bằng cách mở entry từ JAR bằng công cụ xem archive, hoặc giải nén vào một thư mục QA riêng rồi đọc file. Chỉ nhìn thấy tên entry vẫn chưa chứng minh class name bên trong được viết đúng; phải xác nhận nội dung `com.acme.processor.GreetingProcessor`.

### 5.4. Các lỗi đóng gói cần phòng ngừa

- **Sai root:** JAR chứa `processor/resources/META-INF/services/...` thay vì `META-INF/services/...`, khiến SPI không nhận diện.
- **Sai class name:** service file ghi `GreetingProcessor` thay vì full name.
- **Thiếu dependencies:** class processor có mặt nhưng lúc load thiếu class phụ trợ, dẫn tới lỗi ở cơ chế service loading hoặc processor execution.
- **Thêm service descriptor vào compile output trước khi compile processor:** compiler có thể cố load provider **chưa được biên dịch**, sinh lỗi service configuration. Xây processor classes trước, đóng resources vào JAR sau là cách tách rõ.
- **JAR không chứa annotation API:** nếu demo dùng một JAR chung nhưng quên `GenerateGreeting.class`, compiler consumer có thể không nhận biết annotation.
- **Dùng JAR sai version:** pipeline có thể chạy processor cũ không còn khớp annotation/source hiện tại.

## 6. Dự án consumer: tham chiếu class được sinh

Tạo hai file Java mới:

**File `consumer/src/com/acme/app/Trigger.java`:**

~~~java
package com.acme.app;

import com.acme.annotations.GenerateGreeting;

@GenerateGreeting
public final class Trigger {
}
~~~

**File `consumer/src/com/acme/app/App.java`:**

~~~java
package com.acme.app;

import com.acme.generated.GeneratedHello;

public final class App {
    public static void main(String[] args) {
        System.out.println(GeneratedHello.message());
    }
}
~~~

Vào lúc viết hai file này, **chưa có** `GeneratedHello.java` hoặc `GeneratedHello.class` trong consumer source tree. Processor sẽ sinh source còn thiếu khi được gọi.

Sơ đồ dependency:

~~~text
Consumer source:
  Trigger.java --> annotation API GenerateGreeting
  App.java     --> generated type GeneratedHello

Compile:
  annotation API --> compile classpath (consumer nhìn thấy)
  processor implementation --> processor path (javac load processor)
  processor output --> generated source root (-s)
  java bytecode --> classes output (-d)

Run:
  App.class + GeneratedHello.class --> runtime classpath
  processor JAR thường không cần ở runtime
~~~

## 7. Kiểm thử quan trọng nhất: tự động phát hiện processor từ JAR

Chạy từ gốc `sample/` sau khi đã có `build/greeting-processor.jar`:

~~~bash
javac --release 17 -cp build/greeting-processor.jar -processorpath build/greeting-processor.jar -s build/generated -d build/classes consumer/src/com/acme/app/Trigger.java consumer/src/com/acme/app/App.java
~~~

Đây là lời gọi **không có `-processor`**. Nó dùng service descriptor trong JAR để tìm `GreetingProcessor`.

Từng option có vai trò riêng:

| Option | Ý nghĩa trong demo |
| --- | --- |
| `--release 17` | Đặt mức source/API/bytecode Java 17 |
| `-cp build/greeting-processor.jar` | Cho source consumer nhìn thấy `com.acme.annotations.GenerateGreeting` |
| `-processorpath build/greeting-processor.jar` | Chỉ định nơi `javac` tìm implementation và service descriptor |
| `-s build/generated` | Nơi `Filer.createSourceFile` đặt `GeneratedHello.java` |
| `-d build/classes` | Nơi `javac` đặt class files của cả nguồn viết tay và nguồn được sinh |
| `consumer/src/...` | Những input source files cần compile |

Cung cấp `-processorpath` là **cấu hình annotation processing tường minh**. Nó cũng tránh phụ thuộc vào việc compiler tìm processor tình cờ trên compile classpath. Từ JDK 23, `javac` không còn tự động bật annotation processing chỉ vì phát hiện processor trên classpath **nếu không có lựa chọn cấu hình xử lý annotation**; vì vậy build nên chủ động cung cấp processor path hoặc processor names, hoặc option `-proc:full` trên JDK hỗ trợ. Ví dụ dùng processor path tường minh và tương thích Java 17+.

**Kết quả sau khi compile thành công:**

~~~text
build/
├── generated/
│   └── com/acme/generated/GeneratedHello.java
└── classes/
    ├── com/acme/app/
    │   ├── Trigger.class
    │   └── App.class
    └── com/acme/generated/GeneratedHello.class
~~~

Generated source chứa một class có package `com.acme.generated`, phương thức tĩnh `message()` trả chuỗi `"hello-from-processor"`. `javac` xử lý source mới qua annotation processing rounds rồi biên dịch nó trong cùng compilation bình thường.

### Chạy consumer

~~~bash
java -cp build/classes com.acme.app.App
~~~

**Stdout chính xác:**

~~~text
hello-from-processor
~~~

Ở runtime, classpath chứa `App.class` và `GeneratedHello.class` là đủ trong demo. Annotation retention `SOURCE` và việc processor chỉ phục vụ compile khiến JAR processor **không cần trên runtime classpath**. Điều này có thể khác với processor thực tế sinh source phụ thuộc một thư viện runtime riêng.

**Bằng chứng auto-discovery thành công** là: đã **không** đặt `-processor` trong compile command; generated source xuất hiện; class được biên dịch; app chạy ra output đúng. Khi cần xem tên processor được gọi, thêm `-XprintProcessorInfo` ở phần chẩn đoán.

## 8. Chọn processor tường minh bằng `-processor`

Nếu muốn thử implementation mà **không phụ thuộc service-discovery**, chỉ rõ full processor class name:

~~~bash
javac --release 17 -cp build/greeting-processor.jar -processorpath build/greeting-processor.jar -processor com.acme.processor.GreetingProcessor -s build/explicit-generated -d build/explicit-classes consumer/src/com/acme/app/Trigger.java consumer/src/com/acme/app/App.java
~~~

Tạo trước hai output root mới `build/explicit-generated` và `build/explicit-classes` nếu chưa có; đừng trộn với output từ lượt compile trước.

Chạy:

~~~bash
java -cp build/explicit-classes com.acme.app.App
~~~

Stdout vẫn:

~~~text
hello-from-processor
~~~

**Hai dạng kiểm thử phát hiện hai nhóm lỗi khác nhau:**

- **Auto-discovery** dùng `META-INF/services/javax.annotation.processing.Processor`. Nếu processor class chạy với `-processor` nhưng không chạy ở chế độ auto, hãy kiểm tra service file path/content và processor path.
- **Explicit selection** dùng `-processor`. Nếu ngay cả dạng tường minh cũng thất bại, hãy kiểm tra class/dependencies, processor code, annotation matching, exceptions và đường output.

`-processor` **không đồng nghĩa** `-processorpath`: một option đặt **tên implementation được chọn**, option kia đặt **vị trí tìm implementation**.

## 9. Thử chế độ `-proc:only` và `-proc:none`

### `-proc:only`: xử lý annotation, chưa compile class thông thường

~~~bash
javac --release 17 -cp build/greeting-processor.jar -processorpath build/greeting-processor.jar -proc:only -s build/only-generated -d build/only-classes consumer/src/com/acme/app/Trigger.java consumer/src/com/acme/app/App.java
~~~

Hãy sử dụng output roots sạch `build/only-generated` và `build/only-classes` để đối chiếu. Kết quả của demo:

~~~text
build/only-generated/
└── com/acme/generated/GeneratedHello.java

build/only-classes/
    (không có các file .class của ứng dụng)
~~~

`-proc:only` chạy annotation processing mà **không đi đến compilation class thông thường**. Đây là chế độ hữu ích khi cần inspect generated code trước khi compile nó ở bước riêng.

### `-proc:none`: compile mà không chạy annotation processor

Với output mới và không cung cấp generated type ở classpath, lệnh:

~~~bash
javac --release 17 -proc:none -cp build/greeting-processor.jar -d build/no-processing-classes consumer/src/com/acme/app/Trigger.java consumer/src/com/acme/app/App.java
~~~

sẽ **cố ý thất bại** vì `App.java` import `com.acme.generated.GeneratedHello` nhưng processor không tạo class đó. Lỗi compiler có thể nói package `com.acme.generated` không tồn tại hoặc cannot find symbol; văn bản chẩn đoán thay đổi theo JDK.

Đây là phép thử hữu ích để xác định consumer có **thật sự phụ thuộc** generated code hay không. Khi kiểm thử, tránh để `GeneratedHello.class` cũ vô tình nằm trên compile classpath, vì nó có thể che giấu việc processor không chạy.

### Nếu muốn compile generated source riêng

Sau `-proc:only`, có thể chạy một lần compile tường minh, **tắt processor** để không sinh trùng:

~~~bash
javac --release 17 -proc:none -cp build/greeting-processor.jar -d build/manual-classes consumer/src/com/acme/app/Trigger.java consumer/src/com/acme/app/App.java build/only-generated/com/acme/generated/GeneratedHello.java
~~~

Lúc này `App.java` compile được vì generated source được liệt kê trực tiếp. Đây là pipeline **hai bước do build tự điều phối**, khác với pipeline một lượt `javac` ở phần 7. Trong pipeline một lượt bình thường, không cần compile lại `GeneratedHello.java` bằng tay.

## 10. Chẩn đoán processor discovery và processing rounds

Thêm option quan sát:

~~~bash
javac --release 17 -cp build/greeting-processor.jar -processorpath build/greeting-processor.jar -XprintRounds -XprintProcessorInfo -s build/debug-generated -d build/debug-classes consumer/src/com/acme/app/Trigger.java consumer/src/com/acme/app/App.java
~~~

Với output roots mới/sạch, compiler có thể in về các processing rounds:

- Round đầu nhìn thấy `@GenerateGreeting` trên `Trigger`; processor được gọi và sinh `GeneratedHello.java`.
- Round tiếp theo có source mới `GeneratedHello.java`, nên có thể thấy thêm một round.
- Round kết thúc có `processingOver() == true`; processor trong ví dụ không tạo thêm file.

**Không đưa chẩn đoán của `javac` vào bảng stdout của ứng dụng**. `-XprintRounds` và `-XprintProcessorInfo` tạo output phụ thuộc compiler, thường đi qua diagnostic streams và có thể đổi định dạng. Khi kiểm tra tự động, ưu tiên xác nhận artifact cụ thể và nội dung chương trình thay vì so sánh toàn bộ log theo ký tự.

### Danh sách kiểm thử có thể tự động hóa

| Kiểm tra | Quan sát mong muốn |
| --- | --- |
| JAR có service descriptor | `jar --list --file ...` thấy đúng `META-INF/services/javax.annotation.processing.Processor` |
| Service file trỏ đúng FQCN | Nội dung là `com.acme.processor.GreetingProcessor` |
| Auto-discovery | Không cần `-processor` mà `GeneratedHello.java` vẫn được tạo |
| Tạo source | `build/generated/com/acme/generated/GeneratedHello.java` tồn tại |
| Tạo class | `build/classes/com/acme/generated/GeneratedHello.class` tồn tại |
| Chạy application | Stdout chính xác `hello-from-processor` |
| Explicit selection | `-processor com.acme.processor.GreetingProcessor` sinh cùng kết quả |
| Processing only | `-proc:only` tạo Java source, không tạo class app |
| Processor disabled | `-proc:none` trên output sạch làm consumer thiếu generated type |
| Kịch bản sửa annotation/processor | Clean build không còn stale class/source của bản trước |

Có thể dùng `javap -p build/classes/com/acme/generated/GeneratedHello.class` để xác nhận method tồn tại trong bytecode. Điều này kiểm tra class output, không chỉ generated source.

## 11. Đưa JAR vào dự án thực tế: classpath, Gradle và Maven

### 11.1. Processor path không phải compile classpath

Với demo, cùng một JAR xuất hiện trên **cả hai** đường dẫn vì JAR chứa cả annotation API lẫn processor:

~~~text
-cp build/greeting-processor.jar
-processorpath build/greeting-processor.jar
~~~

Hai option phục vụ hai mục đích khác nhau:

- **Compile classpath** cho consumer đọc những class/annotations mà source của nó trực tiếp tham chiếu.
- **Processor path** cho compiler load processor implementation và dependencies của processor, đồng thời tìm service providers.

Trong codebase thật nên cân nhắc tách:

~~~text
greeting-annotations.jar   -> compileOnly / compile classpath
greeting-processor.jar     -> annotationProcessor / processor path
generated-runtime.jar      -> chỉ thêm nếu generated classes thật sự cần runtime API này
~~~

Nếu processor implementation dùng dependency khác như code-generation library, dependency đó phải được cung cấp cho processor classloader. Nếu source **được sinh** import một runtime API, consumer compile/runtime cũng phải có API ấy ở nơi thích hợp. Không nhầm hai tập dependencies.

### 11.2. Gradle Java plugin

Một cấu hình minh họa khi đã có hai artifact được xuất bản:

~~~kotlin
// build.gradle.kts của consumer - minh họa các dependency coordinates
plugins {
    java
}

dependencies {
    compileOnly("com.acme:greeting-annotations:1.0.0")
    annotationProcessor("com.acme:greeting-processor:1.0.0")
}
~~~

Những coordinates trên là **ví dụ giả định**; chỉ hoạt động sau khi bạn thật sự xuất bản artifacts tương ứng vào repository đã cấu hình. `annotationProcessor` cho Gradle biết dependency dành cho compile-time processing, không phải runtime. `compileOnly` có thể phù hợp với SOURCE-retained annotation nếu runtime không cần nó; nếu code/runtime cần annotation API thì chọn scope phù hợp hơn.

Gradle thường quản lý generated-source root và classes root trong build directory. Không cần tự áp dụng `-s`/`-d` thủ công nếu plugin đã cấu hình đúng; khi debug có thể kiểm tra compiler arguments và output của task `compileJava`.

Với demo **một JAR chưa xuất bản**, Gradle consumer có thể dùng file dependency sau khi copy JAR tới thư mục `libs`:

~~~kotlin
dependencies {
    compileOnly(files("libs/greeting-processor.jar"))
    annotationProcessor(files("libs/greeting-processor.jar"))
}
~~~

Đây là ví dụ cấu hình file địa phương; file `libs/greeting-processor.jar` phải tồn tại. Đừng sao chép đồng thời cả hai phương án trừ khi thực sự cần chúng.

### 11.3. Maven Compiler Plugin

Với cấu trúc artifact tách biệt, một cấu hình minh họa:

~~~xml
<dependencies>
  <dependency>
    <groupId>com.acme</groupId>
    <artifactId>greeting-annotations</artifactId>
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
            <groupId>com.acme</groupId>
            <artifactId>greeting-processor</artifactId>
            <version>1.0.0</version>
          </path>
        </annotationProcessorPaths>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Đây là **đoạn `pom.xml` minh họa**, không phải POM độc lập đầy đủ. Trong dự án thực tế phải dùng version plugin phù hợp, artifact phải có trong repositories và dependency graph phải bao gồm mọi thư viện processor cần. Với Maven/compiler plugin đời mới, cấu hình processor dependencies có thể có hình thức khác; mục tiêu vẫn là **tách compile dependencies và processor dependencies**.

Đừng tự thêm generated-source directory vào compile source roots trong cùng một task nếu compiler/plugin đã quản lý generated sources. Làm vậy có thể gây duplicate class hoặc tạo source nhiều lần.

## 12. Processor đóng gói theo JPMS: không nhầm với classpath SPI

Ví dụ trên dùng **JAR trên processor path**, nên đăng ký bằng:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nếu triển khai processor thành **named module**, module descriptor có thể khai báo một service provider:

~~~java
module com.acme.processor {
    requires java.compiler;
    provides javax.annotation.processing.Processor
        with com.acme.processor.GreetingProcessor;
}
~~~

Đoạn này là **minh họa `module-info.java`** cho phương án modular processor. Cần thêm exports/requires phù hợp nếu annotation API và processor nằm trong những module khác nhau; không thể chỉ dán descriptor vào dự án mẫu trên rồi mặc nhiên biên dịch được.

Khi dùng module-based processor discovery, option liên quan là `--processor-module-path` thay vì `-processorpath`. Với classpath JAR không mô-đun hóa, dùng service file `META-INF/services` như ví dụ chính. Phải hiểu rõ bạn đang dùng **classpath-service registration** hay **module-provides registration**; chúng có quy tắc phân giải và packaging khác nhau.

## 13. Lưu ý khác biệt JDK 17, JDK 21 và JDK 23+

Trên những JDK cũ hơn, `javac` có thể thực hiện annotation processing ngầm định nếu thấy processor service descriptor trên classpath. Từ **JDK 23**, annotation processing mặc định bị tắt khi **không có cấu hình rõ ràng** cho processing. Đây là thay đổi giúp hạn chế chạy processor ngoài dự kiến.

Để build dễ kiểm tra và giảm rủi ro:

- Đặt processor dependencies trên processor path/module path riêng; không dựa vào việc JAR tình cờ có trên runtime/compile classpath.
- Dùng `-processor FQCN` khi muốn xác thực một implementation tường minh, **hoặc** dùng service descriptor với `-processorpath` để kiểm tra discovery.
- `-proc:full` yêu cầu processing rồi compilation trên các JDK hỗ trợ option. Option này được đưa vào JDK 21 và được backport tới một số update releases như JDK 17.0.11; không nên giả định mọi bản JDK 17 cũ đều hiểu nó. Ví dụ chính tránh cần option này bằng processor path tường minh.
- `-proc:only` vẫn phục vụ generated-source inspection; `-proc:none` tắt processing rõ ràng.
- Chạy cả `javac -version` và `java -version` khi chẩn đoán môi trường: compiler có thể không cùng phiên bản runtime dùng triển khai.

Tại thời điểm build, **annotation processor là mã thực thi** có thể đọc tài nguyên và tạo file theo quyền của quá trình biên dịch. Chỉ sử dụng processor artifacts từ nguồn đáng tin cậy, quản lý versions và kiểm tra dependency supply chain; không xem chúng là “annotations thụ động” vô hại.

## 14. Lỗi phổ biến khi đóng gói và sử dụng processor

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Compile không thấy generated class | Processor không chạy, không có annotation, hoặc source generation lỗi | Kiểm tra processor path, service file, `-XprintProcessorInfo`, `-s` |
| `Annotation processor ... not found` | Sai class name hoặc thiếu implementation/dependencies | Kiểm tra `-processor`, `jar --list`, processor path |
| `Bad service configuration file` / `Provider ... not found` | Service entry sai FQCN, class không public/load được hoặc dependency thiếu | Xác minh nội dung service file và JAR |
| Chạy với `-processor` được, auto-discovery không chạy | Thiếu/sai `META-INF/services` hoặc processor search path | Dùng hai chế độ test riêng, xem JAR entries |
| Consumer không nhận diện `@GenerateGreeting` | Annotation API thiếu khỏi compile classpath/module path | Thêm artifact annotation API thích hợp |
| `FilerException: Attempt to recreate a file...` | Processor tạo cùng file nhiều rounds hoặc trùng source hiện có | Chặn tạo trùng, chọn tên output ổn định, clean build |
| Generated source có nhưng class không có | `-proc:only`, compilation lỗi hoặc `-d` sai | Kiểm tra `-proc`, compiler diagnostics và class output |
| Class có nhưng app không chạy | Runtime classpath/module path thiếu generated class hoặc runtime API | Kiểm tra class directory và dependencies triển khai |
| Java source sinh sai package | Truyền sai canonical name cho `Filer.createSourceFile` hoặc ghi content package không khớp | Kiểm tra cả tên tạo file và `package` trong generated source |
| Processor được gọi nhưng không sinh file | `getElementsAnnotatedWith(...)` rỗng; annotation type khác; guard `generated` cản; processor chọn sai | Kiểm tra annotation names/rounds và điều kiện sinh |
| Một version JDK chạy, version khác không | Thay đổi default discovery; processor source-version support; API/compiler options | Cấu hình processing tường minh và test JDK matrix |
| Generated class từ lần trước che lỗi | Stale files trên compile classpath hoặc output không clean | Chạy với output roots mới và khóa đường tìm kiếm |
| Build thành công nhưng package JAR thiếu generated class | Đóng gói nhầm directory hay task ordering | Kiểm tra application artifact và `jar --list` |

### Hướng debug hiệu quả theo thứ tự

1. **Kiểm tra artifact processor:** JAR tồn tại? Có service descriptor đúng path? Có class implementation và annotation/dependencies không?
2. **Kiểm tra compiler arguments:** compile classpath có annotation API không? Processor path có implementation không? JDK có bật processing không?
3. **Kiểm tra rounds:** processor có được gọi? Nó có nhìn thấy `@GenerateGreeting` không? Có exception/diagnostic nào không?
4. **Kiểm tra source output:** có `GeneratedHello.java` trong thư mục `-s` và package đúng không?
5. **Kiểm tra bytecode:** có `GeneratedHello.class` trong `-d` không? App.class có compile thành công không?
6. **Kiểm tra runtime/deployment:** generated class và dependencies thật sự có trên runtime classpath/module path không?
7. **Kiểm tra reproducibility:** từ output sạch, compile có tạo lại artifact giống expectation không, hay chỉ hoạt động do file cũ?

Không sửa lỗi discovery bằng cách **đưa bừa mọi JAR vào classpath runtime**. Phải tìm đúng ranh giới compiler/processor/runtime.

## 15. Chiến lược kiểm thử processor nghiêm túc

Ví dụ chạy được ở trên là một *smoke test*, nhưng processor tái sử dụng cần thêm các nhóm kiểm thử:

### 15.1. Positive compilation tests

Với một hoặc nhiều declarations được annotate hợp lệ, xác nhận:

- Processor thực thi mà không có `Diagnostic.Kind.ERROR`.
- Generated file có tên canonical/package đúng.
- Generated source hợp cú pháp, compile thành công và kết quả runtime đúng khi áp dụng.
- Với nhiều annotation targets, generated names không trùng; các files được tạo một lần mỗi compilation.
- Generated code đúng với `--release` và không gọi API quá mới so với target.

### 15.2. Negative compilation tests

Cố ý đưa input không hợp lệ và xác nhận **compiler diagnostic có chủ đích**, không chỉ exception stack trace. Ví dụ processor chỉ hỗ trợ public class nhưng user đánh dấu interface: có thể dùng `Messager.printMessage(Diagnostic.Kind.ERROR, "...", element)` để chỉ ra vì sao sai.

Các lỗi cần thử: thiếu required annotations, annotation dùng trên loại element không được hỗ trợ, tên generated type đã tồn tại, API compiler level không phù hợp, processor path thiếu dependency và source generated bị lỗi.

### 15.3. Service-discovery integration tests

Đóng JAR **giống bản sẽ phát hành**, rồi compile một consumer project bằng **chính JAR ấy**, **không dùng `-processor`**, để kiểm chứng SPI. Sau đó chạy phép thử chọn tường minh `-processor` để phân tách lỗi packaging/discovery và lỗi implementation.

Một test chỉ gọi trực tiếp class processor hoặc instantiate nó mà **không chạy `javac` thật** chưa đủ chứng minh JAR service registration hoạt động.

### 15.4. Cross-version và clean build

Dùng JDK tối thiểu được công bố và JDK mục tiêu mới hơn, chạy lần đầu từ output sạch. Xác nhận cả đường `-s`/`-d` và kiểm tra regression khi processor được nâng version. Nếu dùng incremental compilation, kiểm tra xóa annotation có xóa artifact cũ đúng chính sách build, và task ordering không dùng stale generated source.

## 16. Câu hỏi tự kiểm tra

**1. Vì sao chỉ có `GreetingProcessor.class` trong JAR mà auto-discovery không chạy?**  
Có thể thiếu service descriptor đúng path hoặc nội dung FQCN sai; processor class đơn lẻ không đảm bảo được compiler khám phá.

**2. Đường dẫn service file là gì?**  
`META-INF/services/javax.annotation.processing.Processor` ở root của JAR trên processor path (với classpath-service registration).

**3. Có service file đúng nhưng class implementation không có trên processor path, chuyện gì xảy ra?**  
Compiler không thể load provider, có thể báo lỗi service configuration hoặc không thực hiện compilation như mong đợi.

**4. Vì sao ví dụ dùng cùng JAR ở `-cp` và `-processorpath`?**  
JAR demo gộp annotation API và processor. `-cp` phục vụ source consumer, `-processorpath` phục vụ compiler load processor. Trong thực tế hai artifact có thể được tách.

**5. Nếu bỏ `-processor` mà processing vẫn chạy, đã kiểm chứng điều gì?**  
Đã kiểm chứng phần service discovery của JAR, với điều kiện compiler được cấu hình tìm processors ở đúng processor path.

**6. `-proc:only` có làm cho chương trình `App` chạy được luôn không?**  
Không. Nó chỉ chạy processing; cần bước compile để tạo class output.

**7. `-proc:none` là gì?**  
Tắt annotation processing. Consumer trong demo sẽ không biên dịch nếu chưa có generated type từ nguồn/bytecode khác.

**8. Nên deploy processor implementation cùng ứng dụng không?**  
Thường không cần sau khi source generated đã được compile, trừ khi có một yêu cầu runtime độc lập; generated code có thể cần runtime library riêng.

**9. Tại sao một bộ test chỉ chọn processor tường minh chưa đủ cho bản phát hành?**  
Nó bỏ qua kiểm thử service descriptor/auto-discovery, vốn là bước thiết yếu nếu người dùng trông đợi phát hiện tự động.

**10. Dùng JDK mới thấy processor không chạy khi chỉ thêm JAR vào classpath, cần xem gì?**  
Kiểm tra thay đổi default annotation processing từ JDK 23; khai báo `-processorpath`, `-processor` hoặc `-proc:full` khi phù hợp, và xác nhận JDK version.

## 17. Checklist phát hành

- [ ] Annotation API và processor code biên dịch đúng release Java hỗ trợ.
- [ ] Processor khai báo supported annotations/source version, không tạo output trùng.
- [ ] JAR chứa processor class, các dependencies cần thiết và service descriptor đúng FQCN.
- [ ] Service descriptor nằm đúng tại `META-INF/services/javax.annotation.processing.Processor`.
- [ ] Consumer thấy annotation API trên compile classpath/module path.
- [ ] Compiler load processor từ processor path/module path rõ ràng; không dựa vào auto-processing ngầm định.
- [ ] Integration test tự động **không dùng `-processor`** chứng minh SPI chạy.
- [ ] Test tường minh `-processor` phân biệt lỗi discovery và implementation.
- [ ] Generated `.java` xuất hiện ở `-s`; generated `.class` có ở `-d`.
- [ ] `-proc:only` và `-proc:none` được hiểu đúng khi tách build pipeline.
- [ ] Ứng dụng consumer thực sự chạy được với classpath/module path và dependency runtime phù hợp.
- [ ] Clean build và kiểm thử JDK versions mục tiêu không phụ thuộc stale artifacts.
- [ ] Processor được coi là executable build dependency và được kiểm soát nguồn gốc, version, bảo mật.

## Tài liệu chính thức

- [Oracle JDK 17 — `javac` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): processor options, annotation processing, service discovery, `-processorpath`, `-s` và `-d`.
- [Java 17 API — `Processor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html) và [`AbstractProcessor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): hợp đồng và vòng đời processor.
- [Java 17 API — `Filer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html): tạo source/class/resource files.
- [Inside Java — Annotation Processing Change in JDK 23](https://inside.java/2024/06/18/quality-heads-up/): thay đổi chính sách bật annotation processing mặc định và `-proc:full`.

**Kết luận:** Một processor sẵn sàng được tái sử dụng phải **được build**, **đóng gói kèm service registration chính xác**, **được compiler của consumer tìm thấy**, **sinh output đúng** và **vượt qua kiểm thử compile/runtime**. Service descriptor xác thực *discovery*; `-processor` xác thực *implementation*; `-s` và `-d` xác thực *source/class generation*; còn clean build, dependency separation và version tests xác thực tính đáng tin cậy khi sử dụng từ dự án khác.
