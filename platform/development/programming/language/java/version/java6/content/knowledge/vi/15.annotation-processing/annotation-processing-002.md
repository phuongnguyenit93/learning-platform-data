# Phân biệt annotation processor với reflection runtime trong Java

## 1. Hai cơ chế đọc metadata ở hai thời điểm khác nhau

Java có hai cách thường được dùng để xử lý annotation và thông tin cấu trúc lớp, nhưng **chúng không hoạt động cùng giai đoạn**:

- **Annotation processing** dùng API `javax.annotation.processing` và `javax.lang.model` **trong quá trình biên dịch**. Trình biên dịch (`javac`) cung cấp mô hình của các phần tử chương trình; processor có thể xác thực, phát diagnostics hoặc sinh thêm source/resource để compiler xử lý ở các vòng tiếp theo.
- **Runtime reflection** dùng `Class<?>`, `Method`, `Field`, `Constructor` và các phương thức như `getAnnotation(...)` **khi ứng dụng đang chạy**. Reflection quan sát các lớp đã được nạp trong JVM, đọc metadata còn được giữ ở runtime và có thể gọi phương thức/tạo instance nếu được phép.

Cả hai vẫn là **API được hỗ trợ trên Java hiện đại**. Tên package `javax.annotation.processing` **vẫn đúng** trong Java SE hiện hành; không đổi thành `jakarta.annotation.processing`.

| Câu hỏi | Annotation processor | Runtime reflection |
| --- | --- | --- |
| Chạy vào lúc nào? | Trong một tác vụ compile khi annotation processing được bật | Khi JVM đang chạy ứng dụng |
| Đối tượng làm việc chính | `Element`, `TypeElement`, `TypeMirror`, `AnnotationMirror`, `RoundEnvironment` | `Class<?>`, `Method`, `Field`, `Constructor`, `Annotation` |
| Lấy thông tin bằng cách nào? | Compiler cung cấp mô hình source/type qua `ProcessingEnvironment` | Reflection xem metadata của class đã nạp qua class loader |
| Có cần nạp chính lớp đang được phân tích vào JVM ứng dụng không? | **Không**; processor phân tích mô hình compile | **Có**; phải có `Class` tương ứng ở runtime |
| Có thể xử lý annotation `RetentionPolicy.SOURCE` không? | **Có**, khi annotation được trình biên dịch nhìn thấy | **Không** bằng reflection trên `Class`, vì annotation này không tồn tại trong `.class` |
| Có thể sinh source Java? | **Có** với `Filer.createSourceFile(...)` | Reflection không phải cơ chế chuẩn để tạo source trong bước compile |
| Thường dùng cho? | Code generation, kiểm tra contract, tạo adapter/registry, phát cảnh báo compile | Dependency injection/runtime discovery, serialization metadata, runtime routing, gọi phương thức động |
| Xử lý lỗi ở đâu? | Thường qua `Messager`/`Diagnostic.Kind.ERROR` và kết quả compile | Trong code đang chạy: exception, kiểm tra metadata, lỗi truy cập hoặc lời gọi |

**Kết luận cốt lõi:** tên “annotation” không có nghĩa việc đọc nó nhất thiết phải xảy ra lúc runtime. Processor chạy **khi compile** và reflection chạy **sau khi lớp đã được nạp**. Hai cơ chế có thể phối hợp nhưng không thay thế nhau.

## 2. Retention quyết định annotation tồn tại đến giai đoạn nào

`@Retention` điều khiển việc lưu annotation trong artifact:

| `RetentionPolicy` | Trong nguồn | Trong `.class` | Reflection chuẩn tại runtime? | Processor có thể đọc khi compile nguồn? |
| --- | --- | --- | --- | --- |
| `SOURCE` | Có | Không | Không | Có |
| `CLASS` | Có | Có | Không (không thuộc runtime-visible annotations) | Có |
| `RUNTIME` | Có | Có | Có | Có |

Nếu không khai báo `@Retention`, retention mặc định là `CLASS`, **không phải `RUNTIME`**. Khi muốn đọc annotation bằng `Class.getAnnotation(...)` hoặc `getDeclaredAnnotation(...)` ở runtime, hãy khai báo `@Retention(RetentionPolicy.RUNTIME)`.

Ngược lại, annotation chỉ dùng làm đầu vào để compiler sinh code hoàn toàn có thể chọn `SOURCE`, giúp metadata không cần tồn tại trong bytecode cuối cùng. **Không bắt buộc annotation phải có `RUNTIME` mới xử lý được bằng annotation processor**: processor có thể quan sát các annotation trong mô hình biên dịch, kể cả `SOURCE`.

`@Target` là quy tắc khác: nó giới hạn annotation được gắn vào đâu, như `TYPE`, `METHOD`, `FIELD`. Nó không quy định annotation được xử lý ở compile hay runtime.

## 3. Sơ đồ thực tế: cùng một lớp được quan sát ở hai giai đoạn

~~~text
Source code: Customer.java
   @Label("ready")         // SOURCE retention
   @RuntimeLabel("runtime") // RUNTIME retention
            |
            v
      javac + LabelProcessor (compile time)
            |
            +--> RoundEnvironment -> Element/TypeElement
            |          |
            |          +--> đọc @Label("ready")
            |
            +--> Filer tạo CustomerLabelInfo.java
            |
            v
       Customer.class + CustomerLabelInfo.class
            |
            v
      JVM tải và chạy Main
            |
            +--> CustomerLabelInfo.LENGTH == 5
            +--> Customer.class.getAnnotation(Label.class) == null
            +--> Customer.class.getAnnotation(RuntimeLabel.class).value() == "runtime"
~~~

Từ sơ đồ có hai điểm dễ nhầm:

1. **Processor đã đọc được `@Label`** và dùng giá trị để tạo code, dù `@Label` không có mặt ở runtime.
2. **Reflection đọc được `@RuntimeLabel`** vì annotation này được đánh dấu `RUNTIME`; không cần thêm annotation processor nào mới đọc được nó.

## 4. Ví dụ Java 17+: processor tạo lớp, reflection đọc runtime annotation

Ví dụ hoàn chỉnh này dùng **Java SE API**, không cần thư viện ngoài. Chúng ta chủ động chỉ định processor bằng option `-processor` để hoạt động trên cả Java 17 và các JDK mới, kể cả **JDK 23 trở lên**.

Tổ chức mã nguồn:

~~~text
annotation-demo/
└── src/
    └── demo/
        ├── annotations/
        │   ├── Label.java
        │   └── RuntimeLabel.java
        ├── processor/
        │   └── LabelProcessor.java
        └── app/
            ├── Customer.java
            └── Main.java
~~~

Trong các lệnh bên dưới, thư mục `out` chứa lớp biên dịch, còn `generated` chứa source do processor tạo. **Không đặt `Main.java` vào pha biên dịch processor đầu tiên**: lúc đó `CustomerLabelInfo` chưa được sinh ra.

### 4.1. Annotation chỉ phục vụ compile time

Tệp `src/demo/annotations/Label.java`:

~~~java
package demo.annotations;

import java.lang.annotation.*;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface Label {
    String value();
}
~~~

`SOURCE` là lựa chọn có chủ đích. Annotation này hiện diện trong mã nguồn để processor xử lý; sau khi compile, runtime reflection sẽ không thấy `@Label` trên `Customer.class`.

### 4.2. Annotation dành cho runtime reflection

Tệp `src/demo/annotations/RuntimeLabel.java`:

~~~java
package demo.annotations;

import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface RuntimeLabel {
    String value();
}
~~~

`RUNTIME` lưu annotation vào class file theo cách mà các API reflection có thể truy cập. Hai annotation này có cùng dạng thuộc tính `value()`, nhưng **khác chính sách lưu trữ**.

### 4.3. Viết processor dựa trên mô hình biên dịch

Tệp `src/demo/processor/LabelProcessor.java`:

~~~java
package demo.processor;

import demo.annotations.Label;
import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.*;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.*;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("demo.annotations.Label")
public final class LabelProcessor extends AbstractProcessor {
    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.latestSupported();
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (round.processingOver()) return true;

        for (Element element : round.getElementsAnnotatedWith(Label.class)) {
            if (!(element instanceof TypeElement target)) continue;

            String pkg = processingEnv.getElementUtils()
                    .getPackageOf(target).getQualifiedName().toString();
            String name = target.getSimpleName() + "LabelInfo";
            String fqcn = pkg + "." + name;

            int length = target.getAnnotation(Label.class).value().length();
            try (Writer out = processingEnv.getFiler()
                    .createSourceFile(fqcn, target).openWriter()) {
                out.write("package " + pkg + ";\n"
                        + "public final class " + name + " {\n"
                        + "  private " + name + "() {}\n"
                        + "  public static final int LENGTH = " + length + ";\n"
                        + "}\n");
            } catch (IOException e) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, e.getMessage(), target);
            }
        }
        return true;
    }
}
~~~

Bốn phần then chốt:

- `@SupportedAnnotationTypes("demo.annotations.Label")` khai báo **loại annotation mà processor muốn xử lý**; nó không chạy processor lúc runtime. Tên ở đây là tên đầy đủ của annotation.
- `process(..., RoundEnvironment round)` chạy trong **annotation processing rounds**. `round.getElementsAnnotatedWith(Label.class)` tìm những phần tử ở vòng hiện tại được gắn `@Label`. `round.processingOver()` cho biết đã đến vòng cuối; không sinh thêm file tại vòng này.
- `Element` và `TypeElement` là **mô hình chương trình** do compiler cung cấp. `processingEnv.getElementUtils()` tra cứu thông tin về package/type mà không cần load `Customer` trong JVM ứng dụng.
- `processingEnv.getFiler().createSourceFile(fqcn, target)` tạo file Java mới. Compiler sẽ tiếp tục xử lý file mới ở các vòng kế tiếp và compile nó cùng nguồn ban đầu.

**Chi tiết đặc biệt quan trọng:** mã processor gọi `target.getAnnotation(Label.class)`. Đó là phương thức trên **`javax.lang.model.element.Element`**, dùng để tạo góc nhìn về annotation từ **mô hình biên dịch**; nó **không đồng nghĩa** với `Customer.class.getAnnotation(Label.class)` của runtime reflection. Dù giống tên, hai receiver (`Element` so với `Class<?>`) và bối cảnh dữ liệu khác nhau. Trong ví dụ, processor đọc được `@Label("ready")` ở compile time mặc dù retention của nó là `SOURCE`.

Processor này tạo một lớp có hậu tố `LabelInfo` và một hằng `LENGTH` bằng số ký tự của giá trị annotation. Với `"ready"`, giá trị đó là `5`; ví dụ dùng số nguyên để code generation đơn giản và tránh các vấn đề escape chuỗi. Processor chỉ xử lý type nằm trong **package có tên** như `demo.app`; dự án thực tế cần bổ sung validation cho default package, các tên class trùng và trường hợp đầu vào phức tạp.

`process(...)` trả `true` để **claim** những annotation mà processor này xử lý, không phải trả về “compile thành công”. Nếu xử lý gặp lỗi, `Messager` có thể phát `Diagnostic.Kind.ERROR` để compile thất bại. Không nên dùng giá trị trả về của `process` thay thế hệ thống diagnostics.

### 4.4. Lớp nguồn có hai annotation

Tệp `src/demo/app/Customer.java`:

~~~java
package demo.app;

import demo.annotations.Label;
import demo.annotations.RuntimeLabel;

@Label("ready")
@RuntimeLabel("runtime")
public final class Customer {}
~~~

`@Label` làm đầu vào cho processor sinh lớp `CustomerLabelInfo`; `@RuntimeLabel` được giữ đến runtime và sẽ được đọc trong `Main`.

### 4.5. Mã ứng dụng chạy sau khi compile

Tệp `src/demo/app/Main.java`:

~~~java
package demo.app;

import demo.annotations.Label;
import demo.annotations.RuntimeLabel;

public final class Main {
    public static void main(String[] args) {
        System.out.println("generated-length=" + CustomerLabelInfo.LENGTH);
        System.out.println("source-retention-visible="
                + (Customer.class.getAnnotation(Label.class) != null));
        System.out.println("runtime-label="
                + Customer.class.getAnnotation(RuntimeLabel.class).value());
    }
}
~~~

`Main` truy cập lớp **`CustomerLabelInfo` chưa tồn tại trong source ban đầu**; nó chỉ biên dịch thành công vì processor sinh file ở vòng biên dịch. Hai dòng reflection không hề gọi processor: chúng đọc `Class<?>` của `Customer` trong JVM đang chạy.

## 5. Biên dịch hai pha và chạy

Dùng terminal ở thư mục `annotation-demo`.

Trước hết tạo hai thư mục output. Trên Linux/macOS (Bash):

~~~bash
mkdir -p out generated
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out, generated | Out-Null
~~~

**Pha 1 — biên dịch annotation types và chính processor**, chưa cần processor chạy:

~~~bash
javac -encoding UTF-8 --release 17 -proc:none -d out src/demo/annotations/Label.java src/demo/annotations/RuntimeLabel.java src/demo/processor/LabelProcessor.java
~~~

Lệnh này tạo các `.class` của hai annotation và `LabelProcessor` trong `out`. `-proc:none` có nghĩa “compile bình thường nhưng không chạy annotation processors”. Khi chính processor chưa được build xong, ta không muốn vô tình chạy processor khác từ classpath.

**Pha 2 — chạy processor khi biên dịch lớp ứng dụng**:

~~~bash
javac -encoding UTF-8 --release 17 -cp out -processorpath out -processor demo.processor.LabelProcessor -s generated -d out src/demo/app/Customer.java src/demo/app/Main.java
~~~

Các option đóng vai trò độc lập:

| Option | Vai trò |
| --- | --- |
| `--release 17` | Compile theo mức Java SE 17 để kiểm tra khả năng tương thích của ví dụ |
| `-cp out` | Giúp compile thấy `Label`, `RuntimeLabel` và các type đã build ở pha 1 |
| `-processorpath out` | Đưa `LabelProcessor` và các class cần thiết vào đường tìm processor |
| `-processor demo.processor.LabelProcessor` | **Chọn và bật rõ ràng processor**; không phụ thuộc auto-discovery mặc định |
| `-s generated` | Nơi lưu source file do processor tạo |
| `-d out` | Nơi lưu `.class` của ứng dụng và các source được tạo |

Cả hai lệnh `javac` chỉ dùng đường dẫn tương đối và có thể chạy trên Bash hoặc PowerShell. Trong dự án production, processor thường nằm ở dependency artifact riêng thay vì đặt cùng output directory; cách đặt vào `out` ở đây giúp ví dụ độc lập, dễ chạy.

**Pha 3 — chạy ứng dụng**, khi compiler đã hoàn tất:

~~~bash
java -cp out demo.app.Main
~~~

**Standard output chính xác:**

~~~text
generated-length=5
source-retention-visible=false
runtime-label=runtime
~~~

File nguồn sinh ra sẽ nằm ở `generated/demo/app/CustomerLabelInfo.java` với nội dung tương đương:

~~~java
package demo.app;

public final class CustomerLabelInfo {
  private CustomerLabelInfo() {}
  public static final int LENGTH = 5;
}
~~~

Bytecode của lớp này được compile vào `out/demo/app/CustomerLabelInfo.class` trong cùng tác vụ biên dịch pha 2. Giá trị `5` đến từ **annotation processor tại compile time**, chứ không phải `Main` đọc `@Label` bằng reflection.

Trong một lần chạy kiểm thử với OpenJDK 24 và option `--release 17`, file sinh ra xuất hiện đúng vị trí, chương trình in chính xác ba dòng nói trên.

## 6. Vòng xử lý và điều kiện nạp processor

### 6.1. Processor được chạy như thế nào?

Một chu kỳ compile có annotation processing thường gồm:

1. `javac` lấy processor được cấu hình cho tác vụ compile.
2. Processor nhận `ProcessingEnvironment` chứa `Filer`, `Messager`, `Elements` và `Types`.
3. `javac` gọi `process(...)` với `RoundEnvironment` của vòng hiện tại.
4. Processor kiểm tra các `Element` được annotate, phát diagnostics hoặc sinh source qua `Filer`.
5. Nếu có source mới được sinh, compiler sẽ xét tiếp ở các vòng kế tiếp.
6. Compiler gọi một vòng cuối có `processingOver() == true` để kết thúc việc processing.
7. Khi full compilation được bật, compiler tạo class files của các source thích hợp; **processor không tự thực thi ứng dụng vừa compile**.

Mọi lời gọi vào processor xảy ra như một phần của **quá trình build/compile**. Processor là code Java chạy trong môi trường compiler, vì vậy **có thể có side effects khi biên dịch** (đọc file, ghi file, truy cập dịch vụ nếu môi trường cho phép). Không xem annotation processing là hoạt động “chỉ đọc, không thực thi code”. Khác biệt là processor chạy **code của công cụ build**, còn runtime reflection thao tác với code và metadata của ứng dụng đã nạp.

### 6.2. Thay đổi quan trọng từ JDK 23

Trên các phiên bản `javac` hiện đại, phải **cấu hình annotation processing rõ ràng**. Kể từ **JDK 23**, `javac` không còn tự động quét classpath và chạy các annotation processor chỉ vì chúng tình cờ có mặt khi không có option processing liên quan.

Các cách bật có chủ đích gồm:

- `-processor demo.processor.LabelProcessor` để chọn processor cụ thể (như ví dụ).
- `-processorpath <đường-dẫn>` hoặc `--processor-path <đường-dẫn>` để khai báo đường tìm kiếm processor.
- `--processor-module-path <đường-dẫn>` khi dùng processor ở module path.
- `-proc:full` để yêu cầu annotation processing **và** compilation; `-proc:only` chỉ chạy processing mà không compile tiếp, `-proc:none` vô hiệu hóa processing.

**Thực hành tốt:** cấu hình tường minh processor và processor path trong build để có kết quả ổn định, tránh vô tình thực thi processor từ dependency lạ. Trong demo, pha 2 có cả `-processorpath` lẫn `-processor` nên không phụ thuộc hành vi implicit mặc định của phiên bản JDK.

Có thể đóng gói auto-discovery processor classpath qua resource `META-INF/services/javax.annotation.processing.Processor` chứa dòng `demo.processor.LabelProcessor`. Tuy nhiên, resource này **chỉ hỗ trợ cơ chế khám phá**, không có nghĩa mọi `javac` mới đều tự bật processing nếu không có option cấu hình. Ví dụ cố ý dùng `-processor` để bỏ qua bước tạo service descriptor và đảm bảo hành vi nhất quán.

### 6.3. Source retention không làm processor mất dữ liệu

Nếu đổi `@Label` sang `RUNTIME`, một processor đã được bật vẫn có thể xử lý nó trong compile. Ngược lại, nếu giữ `SOURCE` thì processor vẫn đọc được trong compile dù runtime reflection không thấy.

`@Retention` điều khiển **annotation được lưu đến giai đoạn nào**; việc processor có chạy hay không phụ thuộc vào **cấu hình compiler và loại annotation được processor hỗ trợ**. Đừng dùng retention để bật/tắt processor.

### 6.4. Vì sao reflection không thể thay processor để tạo `CustomerLabelInfo`?

Tại thời điểm `javac` compile `Main`, tên type `CustomerLabelInfo` phải được compiler resolve. Runtime reflection chỉ hoạt động **sau** khi code đã compile và đang chạy, nên không thể tự điền type còn thiếu vào compilation trước đó.

Ngược lại, annotation processor không phù hợp để trả lời câu hỏi như “đối tượng hiện tại có annotation `@RuntimeLabel` nào?” khi yêu cầu xảy ra sau khi deploy. Câu hỏi đó thuộc về runtime reflection hoặc metadata đã được compile sẵn.

## 7. Chọn đúng API để tránh nhầm lẫn

| Mục tiêu | Cách phù hợp |
| --- | --- |
| Sinh repository/adapter/helper trước khi chạy | Processor + `Filer` |
| Kiểm tra rằng field/method được annotate đúng quy tắc ngay khi compile | Processor + `Element`/`TypeMirror` + `Messager` |
| Đọc tên, kiểu, generic metadata trong source đang được compile | `javax.lang.model` |
| Tìm annotation `RUNTIME` của một lớp đã được nạp | `Class.getAnnotation(...)` hoặc `getDeclaredAnnotation(...)` |
| Liệt kê method/field của một lớp khi ứng dụng chạy | `Class.getDeclaredMethods()`, `getDeclaredFields()` |
| Chọn handler theo annotation trên class/method tại runtime | Reflection đọc annotation `RUNTIME`, sau đó xử lý theo contract |
| Đảm bảo lỗi sai annotation làm build thất bại | Processor phát `Diagnostic.Kind.ERROR` |
| Dùng kết quả processor trong ứng dụng mà không reflection annotation | Generate type/constants/resources và compile chúng |

**Phân biệt kỹ hai `getAnnotation`:**

~~~java
// Trong annotation processor, target là TypeElement:
Label metadata = target.getAnnotation(Label.class);

// Trong ứng dụng runtime, Customer.class là Class<?>:
Label runtimeMetadata = Customer.class.getAnnotation(Label.class);
~~~

Hai dòng trên là **đoạn minh họa trong các ngữ cảnh khác nhau**, không phải một chương trình độc lập. Trong ví dụ này, `metadata` ở compiler trả giá trị `"ready"`, còn `runtimeMetadata` là `null` vì `@Label` dùng `RetentionPolicy.SOURCE`. Trên mô hình compiler, `Element.getAnnotation(...)` cung cấp proxy dữ liệu annotation; nó không yêu cầu đối tượng `Class<Customer>` tại runtime.

Khi cần đọc annotation mà không muốn phụ thuộc vào việc lớp annotation đã được load sẵn bởi chính processor, có thể dùng `Element.getAnnotationMirrors()`, `AnnotationMirror`, `AnnotationValue` và `Elements.getElementValuesWithDefaults(...)`. Đây là cách làm việc ở mức mô hình annotation của compiler, đặc biệt hữu ích trong processor tổng quát. Ví dụ sử dụng `Element.getAnnotation(Label.class)` vì processor biết trước annotation type và có dependency tương ứng.

## 8. Kiểm thử và debug hai cơ chế

### 8.1. Kiểm thử processor

Test compile-time nên kiểm tra ít nhất:

1. **Processor được kích hoạt**: source `Customer` có `@Label` và compiler dùng `-processor demo.processor.LabelProcessor`.
2. **Source tạo ra có thật**: tồn tại `generated/demo/app/CustomerLabelInfo.java`.
3. **Source tạo ra biên dịch được**: tồn tại `out/demo/app/CustomerLabelInfo.class`.
4. **Nội dung sinh chính xác**: `LENGTH == 5` với `@Label("ready")`.
5. **Dữ liệu không hợp lệ được báo đúng**: khi có quy tắc validation, processor nên phát `Diagnostic.Kind.ERROR` thay vì chỉ in ra `System.out`.
6. **Nhiều vòng xử lý không sinh trùng tên**: không gọi `Filer.createSourceFile` nhiều lần cho cùng type trong một tác vụ; nếu làm vậy sẽ có `FilerException`.

Bài demo tạo file từ type `Customer` ở vòng được annotate, không tạo file ở vòng `processingOver()`. Với processor phức tạp phải quản lý tập tên đã sinh và xử lý nhiều nguồn/rounds một cách xác định.

**Thử bật/tắt:** trên một output sạch, nếu biên dịch ứng dụng với `-proc:none` và không có sẵn `CustomerLabelInfo`, dòng `CustomerLabelInfo.LENGTH` trong `Main` không resolve được. Đây là dấu hiệu **processor chưa sinh type**, không phải “reflection không tìm thấy annotation”. Không dùng output cũ để thử kịch bản này vì file `CustomerLabelInfo.class` của lần build trước có thể che lỗi.

### 8.2. Kiểm thử reflection runtime

Test runtime nên kiểm tra:

~~~java
// Đoạn minh họa bên trong một phương thức Java:
boolean sourceVisible = Customer.class.getAnnotation(Label.class) != null;
boolean runtimeVisible = Customer.class.getAnnotation(RuntimeLabel.class) != null;
if (sourceVisible || !runtimeVisible) {
    throw new AssertionError("Unexpected retention behavior");
}
~~~

Nó kiểm tra **metadata trong class file thực sự đang chạy**, tách biệt khỏi việc processor có được bật hay không. Nếu `@RuntimeLabel` bị đổi sang `SOURCE` hoặc `CLASS`, việc đọc bằng reflection chuẩn sẽ không còn thấy nó.

Không lẫn `getAnnotation` với `getDeclaredAnnotation` khi kiểm tra annotation trên lớp kế thừa: `getAnnotation` có thể xét annotation `@Inherited` trên lớp cha, còn `getDeclaredAnnotation` chỉ xét annotation khai báo trực tiếp. Trong ví dụ `Customer` không có cấu trúc kế thừa đáng chú ý nên hai phương thức cho cùng kết quả trực tiếp.

### 8.3. Bảng chẩn đoán lỗi

| Hiện tượng | Nhóm nguyên nhân | Hướng kiểm tra |
| --- | --- | --- |
| Không có `CustomerLabelInfo.java` | Processor không chạy, sai `-processor`/`-processorpath`, sai supported annotation | Kiểm tra lệnh `javac` pha 2, chính xác tên processor và `@SupportedAnnotationTypes` |
| Có source sinh ra nhưng compile không được | Source mà processor ghi bị lỗi hoặc dependency của type sinh ra không có | Xem file trong `generated` và compiler diagnostics |
| `FilerException` | Processor cố tạo lại cùng tên file trong một lần compile, hoặc đụng input tồn tại | Kiểm tra tên FQN, output và xử lý rounds |
| `Customer.class.getAnnotation(Label.class) == null` | **Đúng dự kiến** do `SOURCE` retention | Không “sửa” bằng cách bật processor lại |
| `Customer.class.getAnnotation(RuntimeLabel.class) == null` | Thiếu `RUNTIME` retention, đọc sai class, annotation không khai báo đúng chỗ | Soát `@Retention`, `@Target`, class/runtime classpath |
| Source sinh có giá trị cũ | Incremental build/cache hoặc output cũ | Xóa output test, xác thực input và generated source của build hiện tại |
| Processor lỗi khi compile trên máy khác | Khác JDK, thiếu processor dependency, khác toolchain | Ghim toolchain, source release và cấu hình processor rõ ràng |

### 8.4. Bộ test nào cần chạy ở đâu?

- **Compile-testing**: chạy `javac` (hoặc JavaCompiler API) với bộ source fixture, assert diagnostics, generated sources và output classes.
- **Runtime test**: chạy `Main` hoặc test JVM bình thường, assert kết quả của class đã compile và runtime-visible annotations.
- **Integration test**: chạy build thật trong môi trường CI có cùng version toolchain; đảm bảo processor dependency được phân loại là processor, không chỉ nằm trong runtime classpath.

Không nên test processor bằng cách chỉ gọi `Class.forName("demo.processor.LabelProcessor")` ở runtime: có class processor chưa chứng minh nó đã được `javac` kích hoạt trong nhiệm vụ compile.

## 9. Các giới hạn và lưu ý thiết kế hiện đại

- **Processor là công cụ build, không phải plugin runtime:** Java SE annotation processing (JSR 269) chạy trong tác vụ compile. Khi người dùng cần cấu hình động sau deploy, không trông chờ processor tự chạy lại trong JVM sản phẩm.
- **Reflection có chi phí và ràng buộc runtime:** cần metadata còn tồn tại (`RUNTIME`), class loader phù hợp, và có thể gặp giới hạn truy cập trên named modules. `Class.getAnnotation` đọc metadata, còn `Method.invoke`, `Field.set` là thao tác khác có thể thay đổi hành vi chương trình.
- **Compile-time model khác runtime class:** `TypeMirror` và `TypeElement` mô tả kiểu/chương trình mà compiler đang xử lý. Không nên chuyển mọi `TypeMirror` thành `Class<?>` bằng `Class.forName`, vì nhiều type chưa biên dịch hoặc không có ở runtime hiện tại.
- **Processor có thể ném lỗi hoặc ghi file khi compile:** nó là Java code được thực thi bởi compiler. Chỉ cho phép processor từ nguồn tin cậy, giới hạn processor path và dùng CI/build isolation khi cần; không coi compilation là “không chạy code”.
- **Không sửa source đầu vào trong processor:** dùng `Filer` để tạo file mới, `Messager` để báo lỗi. Đừng ghi đè trực tiếp source của người dùng hoặc thao tác với class internals của `javac` không thuộc API chuẩn.
- **Tính nhất quán của generated code:** tạo tên type ổn định, không phát sinh xung đột, không giả định thứ tự tùy ý của các `Element`; cân nhắc incremental build, recompile và dependency giữa generated files.
- **Named modules:** Annotation processor dùng API từ module `java.compiler`; `javac` nằm trong module `jdk.compiler` của JDK. Processor có thể khai báo qua `--processor-module-path` khi dùng JPMS. Ví dụ ở đây cố ý dùng classpath để tập trung vào sự khác nhau giữa processing và reflection.
- **Không dùng cơ chế compiler cũ đã bỏ hỗ trợ:** áp dụng `javax.annotation.processing`/`javax.lang.model` cùng `javac` hiện hành, thay vì các công cụ `apt` độc lập đời cũ.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Processor có thể đọc annotation được khai báo `@Retention(RetentionPolicy.SOURCE)` không?

**Đáp án:** Có, khi nó được cấu hình chạy trong compile và annotation tồn tại trong mô hình source của compiler. Chính runtime reflection trên `Class` mới không thấy annotation `SOURCE`.

**Câu 2.** `target.getAnnotation(Label.class)` trong `LabelProcessor` và `Customer.class.getAnnotation(Label.class)` trong `Main` có nghĩa như nhau không?

**Đáp án:** Không. Dòng đầu gọi API trên `Element` của mô hình biên dịch; dòng sau gọi reflection trên `Class` trong JVM runtime. Với `SOURCE` retention, kết quả trong ví dụ lần lượt là annotation proxy (đọc được `"ready"`) và `null`.

**Câu 3.** Trên JDK 23+, một dependency chứa class processor trên classpath có đủ bảo đảm processor tự chạy nếu không có cấu hình annotation processing không?

**Đáp án:** Không. Cần cấu hình tường minh như `-processor`, `-processorpath`, `--processor-module-path` hoặc bật `-proc:full`/`-proc:only` phù hợp. Ví dụ dùng `-processor demo.processor.LabelProcessor`.

**Câu 4.** Vì sao `Main` có thể tham chiếu `CustomerLabelInfo` mặc dù file này không nằm trong mã nguồn ban đầu?

**Đáp án:** Processor tạo `CustomerLabelInfo.java` bằng `Filer`; `javac` tiếp tục xử lý generated source qua các vòng biên dịch và tạo class file. Reflection runtime không phải thứ đã tạo class đó.

**Câu 5.** Nếu đổi `RuntimeLabel` sang `RetentionPolicy.CLASS` thì `Customer.class.getAnnotation(RuntimeLabel.class)` còn thấy dữ liệu không?

**Đáp án:** Không. `CLASS` giữ annotation trong file `.class` nhưng không đưa nó vào tập annotation có thể truy cập bằng Java reflection chuẩn tại runtime.

**Câu 6.** `process(...)` trả `true` có nghĩa là compiler đã build thành công không?

**Đáp án:** Không. Nó báo annotation types đã được processor **claim**; compile có thành công hay không phụ thuộc diagnostics và toàn bộ tác vụ biên dịch.

**Bài luyện.** Thêm `@Label("important")` vào một lớp mới `Order` trong `demo.app`, để processor tạo `OrderLabelInfo.LENGTH`. Sửa `Main` để in cả giá trị của `CustomerLabelInfo` và `OrderLabelInfo`. Sau đó, tạo output sạch và chạy lại pha 2; kiểm tra hai generated source riêng biệt và không có `FilerException`.

## 11. Tài liệu chính thức đang áp dụng

- [Java SE 26 — javax.annotation.processing](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/package-summary.html): các interface và lớp của annotation processing chuẩn.
- [Java SE 26 — AbstractProcessor](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): `process`, `processingEnv`, supported types/version.
- [Java SE 26 — RoundEnvironment](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): `getElementsAnnotatedWith` và `processingOver`.
- [Java SE 26 — Element](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/Element.html): mô hình một phần tử của chương trình.
- [Java SE 26 — AnnotatedConstruct](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/AnnotatedConstruct.html): `getAnnotation` trong model compiler.
- [Java SE 26 — java.lang.Class](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html): runtime reflection và truy vấn annotation.
- [Java SE 26 — javac command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): `-processor`, `-processorpath` và `-proc:full`/`only`/`none`.
- [Oracle JDK 23 Release Notes](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html): thay đổi mặc định liên quan đến việc kích hoạt annotation processing.
- [Java Language Specification — Annotation interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6): cú pháp và ngữ nghĩa annotation.

**Ghi nhớ:** processor **đọc mô hình khi compile và có thể sinh code mới**; reflection **đọc class/metadata khi ứng dụng chạy**. `@Retention` quyết định khả năng tồn tại của annotation đến runtime, **không quyết định processor có chạy hay không**.
