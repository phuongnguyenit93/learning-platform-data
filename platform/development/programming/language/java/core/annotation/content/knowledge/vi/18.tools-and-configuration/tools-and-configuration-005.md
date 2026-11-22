# javac: -proc:only, -proc:none, -A và -s trong Java Annotation Processing

## 1. Bốn tùy chọn kiểm soát những việc khác nhau

Annotation processing là một phần của quá trình biên dịch Java. Compiler `javac` có thể nạp các **annotation processor** viết bằng Java, cho phép chúng kiểm tra khai báo, báo diagnostic và sinh thêm các tệp source/class hoặc resource thông qua API chuẩn `javax.annotation.processing` và `javax.annotation.processing.Filer`.

Khi dùng công cụ này, bốn tùy chọn rất dễ nhầm là:

| Tùy chọn | Chức năng chính | Không có nghĩa là |
| --- | --- | --- |
| **`-proc:only`** | Chỉ chạy annotation processing, **không thực hiện giai đoạn biên dịch tạo class file của các source đầu vào** sau đó | Không có nghĩa processor không được sinh `.java` |
| **`-proc:none`** | Biên dịch nhưng **không chạy annotation processor** | Không có nghĩa bỏ qua toàn bộ annotation hoặc bỏ qua bước compiler kiểm tra cú pháp |
| **`-Akey[=value]`** | Truyền một tùy chọn tên/giá trị vào **processor**, do processor tự đọc và diễn giải | Không phải tùy chọn Java system property hay cờ tự động sinh source |
| **`-s directory`** | Chọn thư mục đặt **Java source được annotation processor sinh ra** | Không phải thư mục đặt `.class`; thư mục class output dùng `-d` |

Đặc biệt, `-proc:only` và `-proc:none` là **hai chế độ đối lập**; không đưa cả hai vào cùng một lệnh. `-A` và `-s` thì có thể kết hợp với `-proc:only` hoặc với một lần build vừa xử lý annotation vừa biên dịch.

Mục tiêu của bài là hiểu chính xác chức năng, cách ghép tùy chọn, ví dụ chạy được và những lỗi cấu hình thường gặp. Các ví dụ dùng **Java 17+**, không cần Spring, Lombok hoặc thư viện ngoài JDK.

## 2. Bối cảnh: javac tìm và thực thi processor như thế nào?

Một annotation processor là class thực thi `javax.annotation.processing.Processor`, thường kế thừa `AbstractProcessor`. Processor được compiler khởi tạo, cung cấp `ProcessingEnvironment` và gọi `process(...)` qua các processing rounds.

Các bước có thể diễn ra:

```text
File nguồn .java
  |
  |  javac phân tích nguồn và tìm annotation processor
  v
Annotation processing (có thể gồm nhiều vòng)
  |         |
  |         +-- Messager: báo lỗi/cảnh báo
  |         +-- Filer: sinh file nguồn .java mới
  v
Biên dịch nguồn ban đầu và nguồn đã sinh -> file .class
```

Tùy chế độ:

- `-proc:only`: chạy nhánh xử lý annotation, **không bước biên dịch hoàn chỉnh tiếp theo**.
- `-proc:none`: bỏ nhánh xử lý annotation, đi qua công việc biên dịch thông thường.
- Một lệnh cấu hình processor **không dùng `-proc:only` hoặc `-proc:none`**: thực hiện annotation processing rồi biên dịch; với JDK mới, nên bật processor **tường minh**.

Processor có thể tạo source thông qua:

```java
JavaFileObject source = processingEnv.getFiler()
        .createSourceFile("generated.Hello");
```

Khi đóng writer/stream đúng cách, source mới được compiler xem xét ở các vòng xử lý thích hợp. Tùy chọn `-s` sẽ quyết định thư mục đích cho source file đó; không quyết định processor nào được chạy.

### 2.1. Đừng bỏ qua khác biệt mặc định từ JDK 23

Từ **JDK 23**, `javac` **không còn tự động chạy annotation processor chỉ vì tìm thấy processor trên classpath** khi không có cấu hình xử lý annotation tường minh. Đây là thay đổi nhằm tránh việc vô tình thực thi processor có mặt trên classpath.

Để build có thể tái lập qua phiên bản JDK, hãy dùng các tùy chọn rõ ràng như:

```bash
javac -processor MyProcessor -processorpath path/to/processors ...
```

hoặc các cấu hình xử lý annotation thích hợp của build tool. Nếu dùng `-proc:only`, ta đã thể hiện ý định chỉ xử lý annotation. Có thêm `-processor` sẽ chỉ định **đúng class processor** cần chạy, không trông chờ vào service discovery.

Tùy chọn `-proc:full` có nghĩa **annotation processing + compilation** trên các phiên bản javac hỗ trợ; nó được thêm và được backport sang một số bản cập nhật JDK cũ. Nếu cần chạy trên một bản JDK 17 chưa cập nhật, nên dùng **`-processor` tường minh mà không cần `-proc:full`**, như ví dụ phần sau.

## 3. -proc:only — chỉ xử lý annotation

Cú pháp:

```bash
javac -proc:only -processor SomeProcessor -processorpath processor-classes -s generated Input.java
```

**Ý nghĩa đúng:** Compiler xử lý annotation, có thể báo lỗi và sinh file, nhưng **không thực hiện giai đoạn biên dịch class của các source đang xử lý** sau khi annotation processing kết thúc. Vì vậy `-proc:only` thường dùng cho:

- Kiểm tra ràng buộc annotation trong một bước riêng của pipeline.
- Sinh Java source dựa trên khai báo đầu vào, trước một lệnh biên dịch độc lập.
- Chẩn đoán hoạt động processor mà chưa cần tạo class output cho ứng dụng.
- Tách bước generation với bước compilation để quan sát output dễ hơn.

**Không nên nhầm:** `-proc:only` không đồng nghĩa “không thể tạo file”. Processor vẫn có thể sử dụng `Filer.createSourceFile`, `createResource` hoặc các API thích hợp. `-proc:only` chỉ không biên dịch các source thành class như một lần build thông thường.

Một workflow hai giai đoạn hợp lệ:

```text
Giai đoạn 1: -proc:only
  -> processor kiểm tra annotation
  -> tạo generated/GeneratedGreeting.java

Giai đoạn 2: -proc:none
  -> javac biên dịch Demo.java và generated/GeneratedGreeting.java
  -> tạo các file .class của ứng dụng
```

Ở giai đoạn hai, `-proc:none` giúp tránh chạy lại processor, tránh sinh trùng tệp hoặc biến vòng generation thành vòng lặp build khó kiểm soát.

### 3.1. -proc:only vẫn có thể báo lỗi compilation

“Không biên dịch class file” **không có nghĩa javac bỏ qua việc đọc/kiểm tra source**. Javac vẫn phải phân tích phần đủ để phục vụ annotation processing; processor có thể phát `Diagnostic.Kind.ERROR`, hoặc compiler có thể gặp lỗi nguồn. Một lần chạy `-proc:only` vẫn có thể kết thúc với exit code khác 0.

### 3.2. Kiểm tra đầu ra sau -proc:only

Nếu processor sinh source qua `Filer`, hãy tìm các tệp Java trong thư mục chỉ định bởi `-s`. Không tìm `Demo.class` như dấu hiệu processor thành công: tạo class không phải mục tiêu của `-proc:only`.

Ngược lại, nếu không thấy source mới, cần kiểm tra processor **có thực sự được nạp không**, annotation type có được hỗ trợ không, hoặc processor chỉ thực hiện validation chứ không sinh code.

## 4. -proc:none — biên dịch mà không chạy annotation processor

Cú pháp:

```bash
javac -proc:none -cp processor-classes -d app-classes Demo.java generated/GeneratedGreeting.java
```

Với `-proc:none`, compiler không gọi `Processor.process`. Tuy nhiên:

- Java vẫn có cú pháp annotation và quy tắc ngôn ngữ; source chứa annotation không vì vậy bị xem là text bỏ qua.
- Compiler vẫn xử lý khai báo Java để tạo class; các annotation có retention thích hợp vẫn có thể xuất hiện trong class file theo chính sách retention.
- Không có code được sinh bởi processor trong **lần gọi này**. Nếu code tham chiếu một class vốn phải được processor sinh và class đó chưa có, compiler có thể báo `cannot find symbol`.
- Các source đã được sinh **từ bước trước** vẫn có thể được biên dịch khi liệt kê chúng làm input hoặc cấu hình source path phù hợp.

**Ví dụ thực tế:** Dùng `-proc:none` khi kiểm tra compilation thuần, tránh processor ở môi trường không tin cậy hoặc thực hiện giai đoạn compile thứ hai sau `-proc:only`.

`-proc:none` không phải tùy chọn “tắt annotation của Java”. Nó chỉ **tắt các annotation processor** được compiler chạy trong bước ấy.

### 4.1. Khi nào -proc:none khiến build thất bại?

Một class viết:

```java
System.out.println(GeneratedGreeting.message());
```

sẽ không thể biên dịch nếu `GeneratedGreeting` chưa được cung cấp dưới dạng source hoặc class. Nếu dự án trông chờ processor tự tạo nó mà lại dùng `-proc:none` ngay từ đầu, lỗi này là **đúng và dễ dự đoán**.

Khi muốn biên dịch mà vẫn sinh code, đừng dùng `-proc:none`; hoặc chạy generation trong một bước trước rồi bảo đảm source sinh ra được đưa vào compilation.

## 5. -Akey[=value] — truyền cấu hình cho processor

Cú pháp:

```bash
javac -processor SomeProcessor -Akey=value Input.java
javac -processor SomeProcessor -Aflag Input.java
javac -processor SomeProcessor -Acompany.region=west Input.java
```

`-A` cung cấp **processor-specific options**: tên key gồm một hoặc nhiều định danh Java ngăn cách bằng dấu chấm, thường viết `-Akey=value`. Dạng không có `=value` dùng cho cờ không có giá trị. Không tách `-A` và key thành hai đối số shell riêng.

Processor đọc qua:

```java
String salutation = processingEnv
        .getOptions().getOrDefault("salutation", "Hello");
```

`getOptions()` trả một `Map<String, String>` chứa tùy chọn được `javac` đưa vào cho annotation processing. **Bản thân javac không hiểu ý nghĩa nghiệp vụ của `salutation`**; processor quyết định nó dùng để thay đổi nội dung sinh, bật log hoặc áp dụng một quy tắc nào đó.

Processor nên khai báo tùy chọn hỗ trợ qua:

```java
@SupportedOptions("salutation")
```

hoặc override `getSupportedOptions()`. Nếu truyền key không được processor nào hỗ trợ, `javac` có thể cảnh báo kiểu “unrecognized processor options”; đừng xem `-A` là một tùy chọn compiler tổng quát.

### 5.1. Một số quy tắc thực hành

- **Cấu hình rõ ràng:** chọn tên như `salutation`, `project.region`; không tạo key mơ hồ hoặc phụ thuộc vị trí argument.
- **Giá trị mặc định:** processor tự cung cấp default phù hợp khi key không có trong map.
- **Kiểm tra giá trị:** nếu option phải là integer, boolean hoặc enum, hãy parse/validate trong processor và dùng `Messager.ERROR` khi sai.
- **Shell quoting:** khi value chứa khoảng trắng, dấu nháy hoặc ký tự đặc biệt, dùng quoting phù hợp với Bash/PowerShell; shell quyết định cách gửi argv vào javac.
- **Không nhầm với `-Dname=value` hoặc biến môi trường:** đó là cơ chế cấu hình khác, không tự xuất hiện trong `ProcessingEnvironment.getOptions()`.
- **Không dùng cho secrets:** tham số command-line có thể hiển thị trong build logs, lịch sử shell hoặc thông tin process; không nhúng token/password vào generated source.

`-A` **không phải cơ chế bật annotation processing độc lập đáng tin cậy**. Hãy chỉ định processor/processor path hoặc `-proc` phù hợp tường minh; khi dùng `-proc:none`, không có processor nào sử dụng `-A`.

## 6. -s directory — thư mục Java source được sinh

Cú pháp:

```bash
javac -processor SomeProcessor -s generated-sources Input.java
```

`-s` đặt **source output directory** cho Java source files được tạo bởi compiler/annotation processor qua cơ chế thích hợp. Chẳng hạn, processor gọi:

```java
processingEnv.getFiler().createSourceFile("com.example.GeneratedMapper");
```

với `-s generated-sources` thường tạo ra:

```text
generated-sources/
  com/
    example/
      GeneratedMapper.java
```

Trong trường hợp có module, javac có thể tổ chức thư mục theo **module hierarchy trước package hierarchy**. Không nên giả định tất cả dự án đều ghi source ở root của `-s`.

**Phân biệt `-s` với `-d`:**

| Tùy chọn | Đầu ra chính | Ví dụ |
| --- | --- | --- |
| `-s generated` | Java source `.java` được sinh ra | `generated/GeneratedGreeting.java` |
| `-d app-classes` | Bytecode `.class` sau khi biên dịch | `app-classes/Demo.class` |
| `-processorpath processor-classes` | **Đầu vào**, nơi tìm processor và các dependency của nó | `processor-classes/GreetingProcessor.class` |
| `-cp processor-classes` | **Đầu vào**, classpath dùng để phân giải các type của chương trình đang biên dịch | `processor-classes/GenerateGreeting.class` |

`-s` **không tự kích hoạt processor**, không tự tạo annotation và không có nghĩa tất cả source đầu vào đều được copy vào đó. Nếu không có processor sinh Java source, thư mục `-s` có thể rỗng.

Đầu ra source nên nằm trong thư mục riêng, không lẫn mã nguồn viết tay; khi build lặp lại cần tránh file cũ gây build sai hoặc ném `FilerException` vì sinh trùng path trong một phiên processor.

## 7. Ví dụ Java 17+ hoàn chỉnh: hai bước và biên dịch một bước

Ví dụ gồm **ba file Java** trong cùng một thư mục làm việc rỗng, chỉ dùng API chuẩn JDK. Processor đọc `@GenerateGreeting`, nhận tùy chọn `-Asalutation`, rồi dùng `Filer` sinh class `GeneratedGreeting` với phương thức `message()`. Chúng ta so sánh:

1. **`-proc:only`** để sinh `.java`, sau đó **`-proc:none`** để biên dịch và chạy.
2. Chạy processor và biên dịch **trong cùng một lệnh** (không dùng `-proc:only`/`-proc:none`, chỉ định `-processor` tường minh).
3. **`-s`** cho biết file sinh nằm ở đâu; **`-A`** đổi giá trị câu chào.

### 7.1. File GenerateGreeting.java

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateGreeting {
    String name();
}
```

`SOURCE` retention là đủ: processor chạy khi biên dịch, không cần runtime reflection đọc annotation này. Ví dụ sử dụng default package để lệnh chạy ngắn; trong dự án thực tế nên dùng package có tên rõ ràng.

### 7.2. File GreetingProcessor.java

```java
import java.io.IOException;
import java.io.Writer;
import java.util.Set;

import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedOptions;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("GenerateGreeting")
@SupportedOptions("salutation")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        if (roundEnv.processingOver()) {
            System.out.println("PROCESSOR final");
            return true;
        }

        for (Element element : roundEnv
                .getElementsAnnotatedWith(GenerateGreeting.class)) {
            if (generated) {
                continue;
            }
            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Only classes supported", element);
                continue;
            }

            String name = element
                    .getAnnotation(GenerateGreeting.class).name();
            String salutation = processingEnv.getOptions()
                    .getOrDefault("salutation", "Hello");

            // Giới hạn input để sinh Java string literal an toàn trong demo.
            if (!name.matches("[A-Za-z]+")
                    || !salutation.matches("[A-Za-z]+")) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Use letters A-Z for name and salutation",
                        element);
                continue;
            }

            try (Writer writer = processingEnv.getFiler()
                    .createSourceFile("GeneratedGreeting", element)
                    .openWriter()) {
                writer.write("public final class GeneratedGreeting {\n");
                writer.write("  private GeneratedGreeting() {}\n");
                writer.write("  public static String message() { return \""
                        + salutation + ", " + name + "\"; }\n");
                writer.write("}\n");

                generated = true;
                System.out.println("PROCESSOR generated");
            } catch (IOException e) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, e.getMessage(), element);
            }
        }

        return true;
    }
}
```

**Đọc processor:**

- `@SupportedAnnotationTypes("GenerateGreeting")` cho biết processor xử lý annotation nào. Tên này không có package trong ví dụ; khi dùng package, khai báo **fully qualified name**.
- `@SupportedOptions("salutation")` công bố key được hỗ trợ bởi `-Asalutation=...`.
- `processingEnv.getOptions()` đọc giá trị thực; nếu key thiếu, dùng `Hello`.
- `Filer.createSourceFile("GeneratedGreeting", element)` tạo file nguồn Java mang type `GeneratedGreeting`; `element` gắn thông tin originating element để công cụ build có thể theo dõi quan hệ.
- `generated` là trạng thái của processor trong một phiên, tránh cố tạo cùng tên file nhiều lần.
- `processingOver()` dùng để xử lý vòng cuối; processor không sinh type mới trong vòng kết thúc.
- Code chỉ chấp nhận ký tự A–Z để giữ phần tạo Java string literal đơn giản và an toàn. Trong processor thực tế hỗ trợ Unicode/ký tự tùy ý, phải encode/escape chuỗi đúng quy tắc Java literal; không nối input chưa kiểm soát vào source.

`process` trả `true` để claim annotation type; nó **không** có nghĩa đã ngừng các processing rounds.

### 7.3. File Demo.java

```java
@GenerateGreeting(name = "Lan")
public class Demo {
    public static void main(String[] args) {
        System.out.println(GeneratedGreeting.message());
    }
}
```

`Demo` cố ý tham chiếu `GeneratedGreeting` dù class ấy chưa được viết sẵn: processor phải sinh nó trước khi ứng dụng có thể biên dịch/chạy.

### 7.4. Bước 1 — biên dịch annotation và processor

Tạo thư mục để lưu bytecode processor và output demo, từ thư mục chứa ba file chạy:

```bash
mkdir -p processor-classes generated app-classes full-classes full-sources
javac --release 17 -d processor-classes GenerateGreeting.java GreetingProcessor.java
```

Lệnh này tạo `GenerateGreeting.class` và `GreetingProcessor.class` trong `processor-classes`. Tùy chọn `--release 17` bảo đảm nguồn và API dùng Java 17. Các lệnh ví dụ dưới đây dùng Bash trên Linux/macOS; trên Windows PowerShell, tạo thư mục bằng `New-Item -ItemType Directory -Force` và thay dấu phân cách classpath `:` bằng `;`.

### 7.5. Bước 2 — chỉ annotation processing bằng -proc:only

```bash
javac --release 17 -cp processor-classes \
  -processorpath processor-classes \
  -processor GreetingProcessor \
  -proc:only -Asalutation=Hello \
  -s generated Demo.java
```

Kết quả **stdout của processor**:

```text
PROCESSOR generated
PROCESSOR final
```

Sau lệnh này, file `generated/GeneratedGreeting.java` được tạo; nội dung tương đương:

```java
public final class GeneratedGreeting {
    private GeneratedGreeting() {}
    public static String message() { return "Hello, Lan"; }
}
```

**Quan trọng:** `-proc:only` không tạo `Demo.class` hoặc `GeneratedGreeting.class` cho ứng dụng. Lệnh cũng không chạy `main` của `Demo`. Đây là tác vụ **compile-time generation**, không phải chạy ứng dụng.

### 7.6. Bước 3 — biên dịch nguồn có sẵn bằng -proc:none

```bash
javac --release 17 -proc:none -cp processor-classes \
  -d app-classes Demo.java generated/GeneratedGreeting.java

java -cp processor-classes:app-classes Demo
```

Kết quả của **ứng dụng**:

```text
Hello, Lan
```

Ở bước này, `javac` biên dịch `Demo.java` cùng `GeneratedGreeting.java` đã sinh, và `-proc:none` bảo đảm processor **không chạy lại**. `-cp processor-classes` giúp compiler tìm annotation `GenerateGreeting.class`; khi chạy ứng dụng, `Demo` sử dụng `GeneratedGreeting.class` trong `app-classes`.

**Thử lỗi có chủ đích:** nếu chỉ biên dịch `Demo.java` với `-proc:none`, không đưa `GeneratedGreeting.java` hoặc `.class` vào source/class path, compiler sẽ báo lỗi không tìm được `GeneratedGreeting`.

### 7.7. Cách khác — một lệnh vừa xử lý vừa biên dịch

Không dùng `-proc:only` và `-proc:none`, nhưng vẫn **nêu processor rõ ràng** để tránh phụ thuộc JDK 23+ default:

```bash
javac --release 17 -cp processor-classes \
  -processorpath processor-classes \
  -processor GreetingProcessor \
  -Asalutation=Hi \
  -s full-sources -d full-classes Demo.java

java -cp processor-classes:full-classes Demo
```

Kết quả của processor và ứng dụng:

```text
PROCESSOR generated
PROCESSOR final
Hi, Lan
```

Trong chế độ này:

- `full-sources/GeneratedGreeting.java` chứa source do processor sinh, với nội dung `"Hi, Lan"`.
- `full-classes/` chứa bytecode được biên dịch của `Demo` và `GeneratedGreeting`.
- Không cần một lệnh `javac` thứ hai cho source sinh: compiler kết hợp processing + compilation trong cùng lần gọi.
- Bộ ví dụ **đã được kiểm thử trên JDK 21** bằng `--release 17`; các lệnh có processor tường minh giúp phù hợp với cả môi trường JDK 17+ và chính sách mới từ JDK 23.

**Lưu ý stdout:** Đây là ví dụ tối giản nên processor in hai dòng cố định; compiler khác hoặc build tool có thể bổ sung diagnostic/note của riêng nó. Đừng dùng thứ tự log của một build phức tạp làm hợp đồng nghiệp vụ.

## 8. Các kịch bản kết hợp tùy chọn

| Lệnh hoặc nhóm tùy chọn | Kết quả kỳ vọng |
| --- | --- |
| `-proc:only -processor GreetingProcessor -Asalutation=Hello -s generated` | Processor chạy, có thể sinh source vào `generated`; không build class của ứng dụng |
| `-proc:none -d app-classes` | Chỉ compile; không chạy processor; source sinh từ lần trước phải được cung cấp riêng |
| `-processor GreetingProcessor -Asalutation=Hi -s full-sources -d full-classes` | Chạy processor rồi compile theo flow đầy đủ |
| `-proc:none -Asalutation=Hi` | Không có processor được chạy để sử dụng option; không mong source mới |
| `-proc:only -s generated` nhưng không có processor hợp lệ | Có thể không sinh source; kiểm tra cấu hình processor và diagnostic |
| `-proc:none -s generated` | `-s` không tự sinh Java source khi annotation processing bị tắt |

Để processor được nạp thành công, cần phân biệt ba đường dẫn:

- `-processorpath`: đường dẫn để tìm và nạp processor, và các dependency cần thiết của processor.
- `-cp`: classpath cho các type mà chương trình đang biên dịch tham chiếu, gồm annotation type nếu cần.
- `-s`: **đầu ra** source được processor tạo, không phải đường dẫn tìm processor.

Nếu dự án modular, có thể cần `--processor-module-path` hoặc cấu hình module path thay cho classpath; không tự áp dụng nguyên xi ví dụ default-package vào cấu trúc module thật.

## 9. Cảnh báo về build tái lập và an toàn

### 9.1. Không phụ thuộc implicit processor discovery

Ở JDK 23+, javac yêu cầu cấu hình annotation processing tường minh trong các trường hợp vốn trước đây có thể tự khám phá processor trên classpath. Một build “có chạy trên máy cũ nhưng không sinh code trên máy mới” thường do phụ thuộc implicit discovery.

Khắc phục: khai báo processor với `-processor` hoặc build tool plugin hỗ trợ đầy đủ processor path/annotation processing. Kiểm tra bằng `-XprintProcessorInfo` hoặc các lựa chọn chẩn đoán phù hợp nếu compiler hỗ trợ.

### 9.2. Dùng thư mục output sạch

Generated Java source là artifact build. Nếu chạy hai lần mà giữ source của lần trước và đồng thời chạy lại processor, dễ sinh xung đột tên type hoặc dùng artifact cũ. Thiết kế các output directory riêng cho từng chế độ và clean đúng thư mục build khi cần, không xóa nhầm mã nguồn viết tay.

### 9.3. Bảo vệ ranh giới trust

Annotation processor là **mã Java được thực thi trong quá trình build**, nên `-processorpath` cần được kiểm soát như một dependency thực thi. Không nạp processor từ nguồn không đáng tin chỉ để đọc annotation. `-proc:none` có thể hữu ích khi cần compiler không thực thi processor không được chấp nhận, nhưng dự án lệ thuộc mã sinh có thể không compile được nếu không cung cấp artifact đã được tạo an toàn.

### 9.4. Giới hạn của -A và dữ liệu nhạy cảm

`-A` hợp với cấu hình đơn giản như tên profile hoặc mode generation, không phù hợp để đưa password/token lên command line. Build logs hoặc tooling có thể ghi lại tham số. Processor cũng có thể viết tùy chọn vào mã sinh nếu được thiết kế như vậy, nên cần kiểm soát giá trị.

### 9.5. Đừng nhầm success của processor với success của build

Một processor có thể sinh source hợp lệ nhưng source ấy gặp lỗi ở bước compilation; `-proc:only` thành công **không bảo đảm** bước `-proc:none` tiếp theo sẽ thành công. Ngược lại, `-proc:none` biên dịch thành công với class đã có cũng không chứng minh annotation validation đã chạy ở lần build hiện tại.

Trong CI, nếu yêu cầu cả generation và compilation, pipeline nên kiểm tra exit code của **cả hai giai đoạn** (hoặc dùng chế độ full với processor tường minh) thay vì chỉ xem một thư mục generated tồn tại.

## 10. Lỗi thường gặp và cách sửa

**1. Nghĩ -proc:only phải sinh .class.** Sai. `-proc:only` chỉ thực hiện annotation processing, không tạo class output của chương trình như compilation bình thường. Biên dịch các Java source phù hợp ở bước kế tiếp.

**2. Dùng -proc:none nhưng trông chờ processor sinh type.** Sai. Nếu code cần generated class, phải sinh trước hoặc bật processing.

**3. Dùng -s thay cho -d.** `-s` dành cho generated `.java`; `-d` dành cho compiled `.class`.

**4. Tưởng -A bật annotation processing.** `-A` truyền tùy chọn cho processor đang được chạy. Hãy cấu hình processor tường minh và kiểm tra `@SupportedOptions`.

**5. Viết -A salutation=Hello thành các đối số rời.** Dùng `-Asalutation=Hello`, giữ liền key với `-A`.

**6. Truyền key không được processor công bố.** `javac` có thể cảnh báo key không được processor nhận diện. Khai báo `@SupportedOptions` hoặc `getSupportedOptions()` hợp lệ.

**7. Nhầm processorpath và classpath.** Processor có thể được nạp nhưng compiler không tìm thấy annotation type; hoặc compiler thấy annotation nhưng processor không được nạp. Cần cấu hình cả hai khi cần.

**8. Không chỉ định processor trên JDK mới.** Dựa vào tự phát hiện processor trên classpath có thể khiến annotation processing không chạy từ JDK 23. Dùng `-processor` hoặc thiết lập build phù hợp.

**9. Truyền tùy chọn có dấu cách mà không escape/quote.** Shell tách đối số trước khi javac nhận. Dùng cú pháp quoting tương thích môi trường chạy.

**10. Chỉ kiểm tra file generated đã tồn tại mà không xem timestamp/build.** File cũ có thể làm chương trình compile được mà không chứng minh processor vừa chạy. Dùng output sạch và log của processor.

**11. Nghĩ -proc:only đảm bảo mọi code đã hợp lệ.** Compiler không thực hiện giai đoạn biên dịch class hoàn chỉnh; chạy bước compilation riêng để phát hiện lỗi liên quan symbol hoặc generated source.

**12. Đưa option của javac vào getOptions().** `ProcessingEnvironment.getOptions()` phản ánh các tùy chọn `-A` dành cho processor, không phải mọi cờ `javac` như `-s` hay `-proc`.

**13. Nghĩ -s tự tạo source dù không có processor.** Thư mục `-s` chỉ định chỗ ghi; cần code processor gọi Filer để có file sinh.

**14. Ghép -proc:only và -proc:none trong cùng lệnh.** Hai chế độ không phải cờ cộng dồn. Chọn đúng một mục đích cho mỗi lần gọi `javac`.

## 11. Checklist khi cấu hình annotation processing trong dự án

1. Xác định processor class nào cần chạy; nên chỉ định tường minh qua build tool hoặc `-processor`.
2. Kiểm tra dependency của processor và `-processorpath`/processor module path.
3. Xác minh source code nhìn thấy annotation type qua classpath/module path.
4. Quyết định **chỉ sinh/kiểm tra** (`-proc:only`) hay **xử lý kèm biên dịch**.
5. Nếu tách hai bước, dùng `-proc:none` ở bước compile để không chạy lại processor; bao gồm generated source/class đầu vào thích hợp.
6. Đặt thư mục Java source sinh ra với `-s`; class output với `-d`.
7. Khai báo các key `-A` mà processor hỗ trợ và validate giá trị đầu vào.
8. Tắt phụ thuộc implicit discovery, nhất là trên JDK 23 trở lên.
9. Kiểm tra log/error code, artifact sinh và class output sau mỗi bước.
10. Thử trên bản JDK của CI, cấu hình thư mục build sạch và không nhập lẫn generated code vào source viết tay.

## 12. Bài tập thực hành

1. **Đổi cấu hình -A:** Chạy lại ví dụ với `-Asalutation=Welcome`. Dự đoán nội dung `GeneratedGreeting.java` và kết quả chạy ứng dụng. Giải thích tại sao javac tự nó không hiểu ý nghĩa `Welcome`.
2. **Bỏ -A:** Bỏ `-Asalutation=...` khỏi lệnh chạy processor. Dự đoán giá trị mặc định `Hello` do code processor sử dụng.
3. **Tách nguồn/class:** Đổi `-s generated` thành `-s source-out` nhưng giữ `-d app-classes`. Kiểm tra đúng thư mục xuất hiện `.java` và `.class`.
4. **Tắt processor:** Thử `javac -proc:none -cp processor-classes -d app-classes Demo.java` khi không có generated type trước đó. Ghi lại lỗi symbol và sửa bằng cách cung cấp source đã sinh.
5. **Hai bước và một bước:** So sánh hai pipeline ở mục 7 về danh sách file đầu ra. Nêu lợi ích của việc tách generation và điểm cần chú ý về artifact stale.
6. **Key không khai báo:** Truyền `-Aunknown.option=yes`. Quan sát cảnh báo từ javac và sửa `@SupportedOptions` nếu processor thực sự cần key đó.
7. **Lỗi giá trị:** Thử `-Asalutation=Hello123`. Processor sẽ báo ERROR vì demo chỉ chấp nhận chữ cái ASCII; giải thích đây là logic của processor chứ không phải quy tắc chung của `-A`.
8. **Kiểm thử JDK:** Kiểm tra compiler đang dùng bằng `javac -version`. So sánh kết quả khi có/không có `-processor`, đặc biệt từ JDK 23.
9. **Phân tích an toàn:** Nếu processor nằm trong dependency lạ, giải thích vì sao build tự thực thi nó có rủi ro và khi nào `-proc:none` giúp hạn chế khả năng thực thi ngoài ý muốn.
10. **Module hóa:** Thiết kế cấu trúc package/module riêng cho annotation và processor; xác định cần thay đổi `@SupportedAnnotationTypes`, đường dẫn processor và nơi ghi source.

## 13. Tài liệu tham khảo chuẩn

- [javac — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): mô tả chính thức `-proc:only`, `-proc:none`, `-Akey[=value]`, `-s`, `-d`, `-processor`, `-processorpath`.
- [Processor — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html): cách compiler tìm/gọi processor, xử lý các rounds và đọc supported options.
- [ProcessingEnvironment — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html): phương thức `getOptions()`, `getFiler()`, `getMessager()`.
- [Filer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html): tạo source/class/resource trong các rounds.
- [Thay đổi chính sách annotation processing của JDK 23 — OpenJDK Quality Outreach](https://inside.java/2024/06/18/quality-heads-up/): giải thích vì sao nên bật processor tường minh.

**Ghi nhớ:** `-proc:only` là **chỉ xử lý annotation**, `-proc:none` là **biên dịch không xử lý annotation**, `-A` là **tùy chọn gửi cho processor** và `-s` là **thư mục chứa Java source do processor sinh**. Ghép đúng các cờ với `-processor`, `-processorpath`, `-cp` và `-d` để build có thể tái lập trên nhiều phiên bản JDK.
