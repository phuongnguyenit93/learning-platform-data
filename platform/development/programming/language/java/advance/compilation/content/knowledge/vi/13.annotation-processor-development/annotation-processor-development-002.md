# Khai báo annotation hỗ trợ, tùy chọn và SourceVersion

Khi xây dựng một **annotation processor** bằng Java, việc viết mã trong phương thức `process(...)` mới chỉ là một phần công việc. Trình biên dịch `javac` còn cần biết: processor này quan tâm đến **annotation nào**, nhận những **tùy chọn cấu hình `-A`** nào, và được thiết kế để xử lý **phiên bản ngôn ngữ Java** nào. Ba nhóm thông tin ấy được khai báo lần lượt bằng:

- `@SupportedAnnotationTypes` — khai báo tập tên annotation mà processor hỗ trợ;
- `@SupportedOptions` — khai báo tập tên tùy chọn mà processor nhận từ `javac -A...`;
- `@SupportedSourceVersion` — khai báo `SourceVersion` cao nhất processor hỗ trợ.

Ba annotation trên thuộc package `javax.annotation.processing`, còn `SourceVersion` thuộc `javax.lang.model`. Chúng là **metadata dành cho annotation processing tool**, không phải ba annotation để gắn vào lớp nghiệp vụ được xử lý.

Bài học dùng **JDK 17+** và trình biên dịch `javac`. Ví dụ tự xây dựng một processor đọc annotation `@Audited`, lấy option `-Aaudit.prefix=CHECK`, đưa ra chẩn đoán trong khi biên dịch, và sau đó chạy một chương trình Java thông thường. Ngoài cú pháp, phần quan trọng là cách khai báo **đúng và đủ** để processor không nhận nhầm annotation, không giấu lỗi cấu hình và không hứa hỗ trợ phiên bản nguồn chưa được kiểm thử.

## 1. Annotation processing diễn ra ở đâu?

Annotation processing là một cơ chế mở rộng **thời điểm biên dịch**. `javac` có thể tải những processor phù hợp, cung cấp mô hình phần tử/kiểu của mã nguồn và gọi processor qua API `javax.annotation.processing.Processor`.

Một processor điển hình kế thừa `AbstractProcessor`:

~~~java
public final class ExampleProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        return false;
    }
}
~~~

Đây là **đoạn khung minh họa**, chưa là lớp độc lập: cần `import` các kiểu tương ứng và khai báo các metadata hỗ trợ. Ví dụ chạy đầy đủ nằm ở phần 3.

Cơ chế khái quát:

~~~text
Nguồn Java có annotation
      |
      v
javac tìm/nạp processor được chỉ định
      |
      +-- Processor.getSupportedAnnotationTypes()
      +-- Processor.getSupportedOptions()
      +-- Processor.getSupportedSourceVersion()
      |
      v
Round 1: process(annotations, roundEnv)
      |
      +-- có thể kiểm tra các element
      +-- có thể phát thông báo WARNING / ERROR / NOTE
      +-- có thể tạo thêm source/class/resource
      |
      v
Round tiếp theo nếu có nguồn mới được tạo
      |
      v
Round kết thúc; javac tiếp tục/hoàn tất biên dịch
~~~

Processor **không phải chương trình được gọi trực tiếp bằng `java ProcessorClass`**. Nó được môi trường biên dịch tải và điều phối. Một processor có thể kiểm tra cấu trúc mã, báo lỗi biên dịch hoặc sinh file nguồn mới, nhưng không tự động thay thế việc chạy kiểm thử nghiệp vụ.

### Ai cung cấp ba thông tin hỗ trợ?

`AbstractProcessor` có các phương thức tương ứng:

| Method của processor | Annotation khai báo thường dùng | Ý nghĩa |
| --- | --- | --- |
| `getSupportedAnnotationTypes()` | `@SupportedAnnotationTypes` | Những tên annotation mà processor tuyên bố hỗ trợ |
| `getSupportedOptions()` | `@SupportedOptions` | Những **tên key** của option `-A` mà processor nhận |
| `getSupportedSourceVersion()` | `@SupportedSourceVersion` | Phiên bản nguồn Java cao nhất mà processor tự tuyên bố hỗ trợ |

Khi dùng `AbstractProcessor`, annotation là cách ngắn gọn để cung cấp metadata cho các phương thức mặc định tương ứng. Bạn cũng có thể **override** các method này nếu cần tập hỗ trợ động, nhưng cần hiểu rõ sự nhất quán và tránh khai báo một nơi, thực thi một kiểu khác.

## 2. `@SupportedAnnotationTypes`: chọn đúng annotation cần xử lý

Ví dụ:

~~~java
@SupportedAnnotationTypes("demo.ann.Audited")
public final class AuditProcessor extends AbstractProcessor {
    // ...
}
~~~

Chuỗi là **tên đầy đủ (canonical name)** của annotation được hỗ trợ, gồm package và tên kiểu: `demo.ann.Audited`. Đừng ghi `"Audited"` nếu annotation thực tế nằm trong package `demo.ann` và bạn muốn processor hỗ trợ kiểu ấy.

Nhiều annotation:

~~~java
@SupportedAnnotationTypes({
    "demo.ann.Audited",
    "demo.ann.Tracked"
})
~~~

Mẫu thứ hai là **minh họa metadata**, chưa phải một processor chạy được vì chưa có thân lớp đầy đủ. Hai tên phải trỏ tới các annotation thực tế mà processor biết xử lý.

Với cơ chế pattern hỗ trợ của `Processor`, `"*"` là biểu thức bao quát **tất cả các annotation types**:

~~~java
@SupportedAnnotationTypes("*")
~~~

Nên chỉ dùng `"*"` khi processor thực sự có mục đích quan sát/xử lý phạm vi rộng. Việc khai báo quá rộng có thể khiến processor được gọi ở nhiều trường hợp không liên quan và có nguy cơ **claim** annotation mà processor khác cần xử lý.

### “Supported” không đồng nghĩa “mọi lớp đều bị xử lý”

`javac` lựa chọn và gọi processor trong các vòng xử lý dựa trên annotation hiện có, tập annotation được tuyên bố hỗ trợ và các processor khác. Trong `process`, bạn còn cần truy xuất đúng phần tử:

~~~java
for (Element element : roundEnv.getElementsAnnotatedWith(Audited.class)) {
    // Xử lý phần tử mang @Audited.
}
~~~

Đây là **đoạn minh họa bên trong `process`**, không phải tệp Java độc lập.

Nếu processor khai báo hỗ trợ `demo.ann.Audited` nhưng lại tìm `@AnotherType` không liên quan, metadata và hành vi thực tế không khớp. Bộ công cụ không tự hiểu ý định bên trong processor. Hãy viết metadata mô tả **đúng những annotation mà mã xử lý**.

### Giá trị trả về của `process` không phải trạng thái thành công

`process(...)` trả về `boolean` để cho biết processor **có claim những annotation được đưa vào vòng xử lý hiện tại hay không**:

- `return true;`: processor tuyên bố xử lý các annotation types được giao trong lượt đó; các processor tiếp theo thường không còn nhận chính các annotation đó trong cùng round.
- `return false;`: không claim, cho phép processor khác cũng xét annotation theo cơ chế phân phối của công cụ.

Giá trị này **không phải** câu trả lời “compile thành công” hay “đã tìm thấy bao nhiêu element”. Nếu cần báo lỗi, dùng `Messager.printMessage(Diagnostic.Kind.ERROR, ...)` để compiler nhận được diagnostic; đừng mong `return false` tự khiến build fail.

## 3. Dự án chạy được: annotation, processor và ứng dụng

Ta tạo ba file Java, biên dịch **processor trước**, sau đó dùng processor để biên dịch ứng dụng. Đây là ví dụ JDK 17+ thuần, không cần Maven hoặc thư viện bên ngoài.

Cây thư mục dự kiến:

~~~text
processor-demo/
├── src/
│   ├── demo/
│   │   ├── ann/
│   │   │   └── Audited.java
│   │   └── proc/
│   │       └── AuditProcessor.java
│   └── ...
├── appsrc/
│   └── demo/
│       └── app/
│           └── Main.java
└── build/
    ├── processor/
    └── app/
~~~

Mọi lệnh sau chạy từ thư mục gốc `processor-demo`. Trên Linux/macOS, tạo hai thư mục đầu ra:

~~~sh
mkdir -p build/processor build/app
~~~

Trên Windows PowerShell, dùng một cách tương đương:

~~~powershell
New-Item -ItemType Directory -Force build/processor, build/app | Out-Null
~~~

Bạn cũng có thể để IDE tạo các thư mục; không cần chạy cả hai biến thể. Các tệp nguồn phải được lưu vào đúng đường dẫn đã nêu.

### 3.1. Khai báo annotation mà ứng dụng sử dụng

**`src/demo/ann/Audited.java`:**

~~~java
package demo.ann;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface Audited {
    String value();
}
~~~

`@Target(TYPE)` quy định `@Audited` có thể đặt trên khai báo kiểu như class. `@Retention(SOURCE)` nói rằng annotation này chỉ cần thiết trong mã nguồn/biên dịch, không cần giữ trong classfile để reflection lúc chạy đọc được. Hai annotation trên thuộc **định nghĩa của annotation nghiệp vụ**, hoàn toàn khác ba annotation `@Supported...` dùng để cấu hình processor.

Giá trị `value()` sẽ cho processor một nhãn mô tả. Bài học không dùng retention `RUNTIME` vì kết quả mong muốn chỉ là một thông báo lúc biên dịch, không phải metadata cho ứng dụng chạy.

### 3.2. Viết processor và khai báo ba nhóm hỗ trợ

**`src/demo/proc/AuditProcessor.java`:**

~~~java
package demo.proc;

import demo.ann.Audited;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedOptions;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("demo.ann.Audited")
@SupportedOptions("audit.prefix")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class AuditProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        String prefix = processingEnv.getOptions()
                .getOrDefault("audit.prefix", "AUDIT");

        if (prefix == null || prefix.isBlank()) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "audit.prefix phải có nội dung");
            return true;
        }

        for (Element element
                : roundEnv.getElementsAnnotatedWith(Audited.class)) {

            String label = element.getAnnotation(Audited.class).value();

            if (label.isBlank()) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@Audited.value không được rỗng",
                        element);
            } else {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.NOTE,
                        prefix + ": " + element.getSimpleName()
                                + " / " + label,
                        element);
            }
        }

        return true;
    }
}
~~~

Điểm cốt lõi:

1. `@SupportedAnnotationTypes("demo.ann.Audited")` giới hạn annotation types mà processor nhận xử lý.
2. `@SupportedOptions("audit.prefix")` tuyên bố processor hiểu **key `audit.prefix`**.
3. `@SupportedSourceVersion(SourceVersion.RELEASE_17)` tuyên bố mức nguồn Java 17.
4. `processingEnv.getOptions()` đọc các option `-A` được công cụ truyền cho processor; nếu không có key, ví dụ chọn mặc định `AUDIT`.
5. `roundEnv.getElementsAnnotatedWith(Audited.class)` chỉ truy xuất các phần tử có `@Audited` trong round hiện tại.
6. `Messager` gửi diagnostics cho compiler. `Kind.NOTE` là ghi chú thông tin, còn `Kind.ERROR` làm biên dịch thất bại theo cơ chế bình thường.
7. `return true` claim annotation mà processor đã nhận; không có ý nghĩa “mã nguồn đã biên dịch thành công”.

Phần `if (roundEnv.processingOver())` minh họa rằng processor có thể được gọi thêm trong **round kết thúc**. Trong ví dụ này không tạo thêm source file, nên không cần thực thi logic kiểm tra annotation ở round cuối.

### 3.3. Viết ứng dụng sử dụng annotation

**`appsrc/demo/app/Main.java`:**

~~~java
package demo.app;

import demo.ann.Audited;

@Audited("entrypoint")
public final class Main {
    public static void main(String[] args) {
        System.out.println("Hello, processor");
    }
}
~~~

Application vẫn là một lớp Java bình thường. Processor quan sát metadata `@Audited` trong quá trình biên dịch; bản thân `Main.main` không gọi phương thức `process`.

## 4. Biên dịch processor rồi biên dịch ứng dụng

### Bước 1: biên dịch annotation và processor

~~~sh
javac --release 17 -encoding UTF-8 -d build/processor src/demo/ann/Audited.java src/demo/proc/AuditProcessor.java
~~~

Lệnh này tạo các classfile cần thiết dưới `build/processor`, ví dụ:

~~~text
build/processor/
├── demo/ann/Audited.class
└── demo/proc/AuditProcessor.class
~~~

Ta biên dịch annotation và processor **cùng lượt** để `AuditProcessor` tham chiếu được tới `Audited.class`. `--release 17` yêu cầu tương thích nguồn, bytecode và API nền tảng Java 17 cho lần biên dịch này. JDK dùng để chạy compiler cần hỗ trợ `--release 17`.

### Bước 2: chỉ định processor khi biên dịch ứng dụng

~~~sh
javac --release 17 -encoding UTF-8 -cp build/processor -processorpath build/processor -processor demo.proc.AuditProcessor -Aaudit.prefix=CHECK -d build/app appsrc/demo/app/Main.java
~~~

Ý nghĩa từng nhóm:

| Tùy chọn | Ý nghĩa trong ví dụ |
| --- | --- |
| `--release 17` | Biên dịch mã ứng dụng theo mức tương thích Java 17 |
| `-cp build/processor` | Cho mã nguồn `Main.java` tìm annotation `demo.ann.Audited` |
| `-processorpath build/processor` | Cho compiler tìm lớp processor và các phụ thuộc khi nạp processor |
| `-processor demo.proc.AuditProcessor` | **Chọn tường minh** processor cần chạy |
| `-Aaudit.prefix=CHECK` | Gửi option key `audit.prefix` với giá trị `CHECK` |
| `-d build/app` | Thư mục đầu ra của `Main.class` |

Lựa chọn `-processor` tường minh rất quan trọng: thí nghiệm **không cần** thiết lập service provider file, cũng không dựa vào cách tự động phát hiện processor khác nhau giữa bản JDK/build tool. Vì vậy có thể tập trung đúng ba metadata đang học.

Khi processor gặp `@Audited("entrypoint")`, nó gửi một diagnostic `NOTE` về phần tử. Trình biên dịch có thể hiển thị dòng chứa nội dung tương tự:

~~~text
CHECK: Main / entrypoint
~~~

Đây là **nội dung thông điệp do processor tạo**, không phải bản sao toàn bộ stdout/stderr `javac`. Tùy JDK, vị trí dấu mũ, đường dẫn nguồn và tiền tố như `Note:` có thể khác. Compiler thường đưa diagnostics ra luồng thông báo của công cụ, **không nên xem NOTE là stdout từ ứng dụng**.

### Bước 3: chạy lớp ứng dụng

~~~sh
java -cp build/app demo.app.Main
~~~

**Stdout chính xác:**

~~~text
Hello, processor
~~~

Ở đây `-cp build/app` là đủ để chạy chương trình đơn giản, vì `@Audited` có retention `SOURCE` và bytecode của `Main` không cần dùng API annotation khi chạy. Trong ứng dụng phức tạp hơn, runtime classpath phải chứa mọi dependency thực tế cần thiết; `-processorpath` chỉ phục vụ nạp processor khi biên dịch.

### Thí nghiệm bỏ tùy chọn

Biên dịch ứng dụng lại mà bỏ `-Aaudit.prefix=CHECK` nhưng vẫn giữ các tùy chọn khác. Processor sử dụng giá trị mặc định `AUDIT` trong đoạn:

~~~java
processingEnv.getOptions()
        .getOrDefault("audit.prefix", "AUDIT");
~~~

Thông điệp do processor tạo khi ấy là:

~~~text
AUDIT: Main / entrypoint
~~~

Điều này chứng minh `@SupportedOptions` không tự cung cấp giá trị mặc định; **giá trị mặc định do chính code processor quyết định**.

## 5. `@SupportedOptions` và cú pháp `-A`

Tùy chọn annotation processing theo dạng:

~~~text
-Akey
-Akey=value
~~~

Ví dụ:

~~~sh
javac -Aaudit.prefix=CHECK ...
~~~

Dòng lệnh trên là **minh họa cú pháp**, không phải lệnh độc lập vì còn dấu ba chấm. Dùng nguyên lệnh đầy đủ ở phần 4 để thử.

Trong processor:

~~~java
String value = processingEnv.getOptions().get("audit.prefix");
~~~

Đây là **đoạn đặt trong processor**, nơi `processingEnv` đã được `AbstractProcessor` khởi tạo. Nếu người dùng truyền `-Aaudit.prefix=CHECK` thì giá trị là `"CHECK"`; nếu không truyền thì `get` trả `null`. Với một option chỉ có key mà không có `=...`, giá trị được công cụ biểu diễn có thể là `null`; khi code cần chuỗi, phải kiểm tra rõ.

Ví dụ bài này dùng:

~~~java
@SupportedOptions("audit.prefix")
~~~

Nó chỉ khai báo **tên key** mà processor công nhận, không tự kiểm chứng rằng chuỗi giá trị dài bao nhiêu, có hợp lệ theo nghiệp vụ không hoặc có nằm trong tập giá trị cho phép không. Việc kiểm tra nằm trong code `process` hoặc `init` do tác giả viết.

### Thế nào là option hợp lệ?

Một thiết kế tốt cần mô tả:

- **Key:** tên chính xác như `audit.prefix`, phân biệt chính tả và dấu chấm.
- **Kiểu giá trị:** ví dụ chuỗi không rỗng hoặc một tập giá trị `strict|lenient`.
- **Giá trị mặc định:** ví dụ `AUDIT` khi không cung cấp.
- **Hành vi khi sai:** phát `ERROR`, không tự đoán.
- **Phạm vi tác động:** chỉ thay đổi prefix của diagnostic, không điều khiển mã runtime.

Với option kiểu enum, có thể dùng kiểm tra tường minh và đưa ra thông báo đầy đủ thay vì chấp nhận chuỗi bất kỳ. Ví dụ, nếu người dùng truyền `-Aaudit.prefix=`, `String.isBlank()` trong processor trên dẫn đến một diagnostic `ERROR`; trình biên dịch sẽ thất bại để người dùng sửa cấu hình.

Một key typo như `-Aaudit.prefx=CHECK` **không được hỗ trợ** bởi `@SupportedOptions("audit.prefix")`. `javac` có thể phát thông báo về option không được processor nào nhận; dù công cụ có cảnh báo hay không, processor của chúng ta cũng **không đọc được giá trị dưới key đúng**, nên quay về mặc định `AUDIT`. Hãy kiểm tra cả compiler log và kết quả để phát hiện lỗi nhập key.

### Nhiều option

Khi processor có nhiều cấu hình, có thể khai báo:

~~~java
@SupportedOptions({"audit.prefix", "audit.mode"})
~~~

và đọc:

~~~java
String prefix = processingEnv.getOptions().get("audit.prefix");
String mode = processingEnv.getOptions().get("audit.mode");
~~~

Đây là **đoạn minh họa**, không yêu cầu thêm `audit.mode` vào ví dụ chạy hiện tại. Việc công bố một key chỉ nên thực hiện khi processor đã có code/contract xử lý key đó. Tránh liệt kê các key chưa dùng chỉ để dập cảnh báo “unrecognized processor option”.

## 6. `@SupportedSourceVersion` và `SourceVersion`

`SourceVersion` là một enum trong package `javax.lang.model`, với các hằng như `RELEASE_8`, `RELEASE_11`, `RELEASE_17`, `RELEASE_21` tùy JDK cung cấp. Processor viết cho JDK 17 có thể khai báo:

~~~java
@SupportedSourceVersion(SourceVersion.RELEASE_17)
~~~

Điều này tuyên bố **mức phiên bản nguồn mới nhất processor hỗ trợ**. Nó không chuyển JVM sang Java 17 và không có nghĩa processor chỉ được dùng đúng với Java 17: với các mức nguồn thấp hơn trong phạm vi công cụ hỗ trợ, processor có thể vẫn chạy.

**Phân biệt hai cấu hình:**

- `javac --release 17`: yêu cầu compile source/bytecode và API nền tảng theo Java 17.
- `@SupportedSourceVersion(RELEASE_17)`: metadata của **processor** về mức ngôn ngữ mà nó hiểu.

Khi dùng compiler JDK mới hơn và biên dịch nguồn ở phiên bản mới hơn 17, processor tuyên bố tối đa `RELEASE_17` có thể làm `javac` phát warning dạng “supported source version ... less than -source ...”. Warning đó nhắc tác giả processor **kiểm tra và cập nhật cam kết tương thích**, không phải cứ thay số là processor tự hiểu toàn bộ cấu trúc ngôn ngữ mới.

### Khi nào nên dùng `SourceVersion.latestSupported()`?

Nếu processor thực sự làm việc tốt với nhiều phiên bản Java và được kiểm thử tương ứng, tác giả có thể override:

~~~java
@Override
public SourceVersion getSupportedSourceVersion() {
    return SourceVersion.latestSupported();
}
~~~

Đây là đoạn minh họa trong class processor có `import javax.lang.model.SourceVersion;`. Nó lấy phiên bản nguồn mới nhất **JDK hiện đang chạy công cụ** hỗ trợ. Điều đó tránh phải cập nhật enum hằng cố định mỗi lần nâng JDK, nhưng **là một lời cam kết hỗ trợ rộng hơn** và cần test phù hợp.

Đừng chọn `latestSupported()` chỉ để warning biến mất: nếu processor phân tích `Tree API`, biểu thức, cú pháp hoặc mô hình kiểu theo giả định cũ, Java mới có thể phá vỡ những giả định ấy. Với thư viện processor phát hành cho người khác, công bố danh sách JDK/source được hỗ trợ dựa trên kiểm thử thực tế.

Một sự thật khác: nếu processor **được biên dịch thành bytecode Java 21**, JVM 17 không thể nạp được nó chỉ vì code trả về `RELEASE_17`. Muốn processor chạy trên JDK 17, bản thân artifact processor phải được biên dịch tương thích (ví dụ `--release 17`) và không dùng API runtime mới không có ở JDK 17.

## 7. Ba cách khai báo metadata: annotation, override, công cụ build

### Annotation là cách ngắn nhất

Trong phần lớn processor tĩnh:

~~~java
@SupportedAnnotationTypes("demo.ann.Audited")
@SupportedOptions("audit.prefix")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class AuditProcessor extends AbstractProcessor {
    // ...
}
~~~

Các metadata nằm ngay trên class, dễ review cùng code xử lý. Đây là **khung minh họa**, không thay thế bản class đầy đủ ở phần 3.

### Override cho tập hỗ trợ động

Processor có thể override ba phương thức:

~~~java
@Override
public Set<String> getSupportedAnnotationTypes() {
    return Set.of("demo.ann.Audited");
}

@Override
public Set<String> getSupportedOptions() {
    return Set.of("audit.prefix");
}

@Override
public SourceVersion getSupportedSourceVersion() {
    return SourceVersion.RELEASE_17;
}
~~~

Đây là các method minh họa trong class extends `AbstractProcessor`, với `import java.util.Set;` và `import javax.lang.model.SourceVersion;`. Nếu override, nên chọn **một nơi làm nguồn sự thật** về metadata; tránh để annotation và method trả các tập khác nhau khiến người duy trì hiểu sai.

### Cấu hình compiler không thay thế metadata processor

Các tùy chọn `-A...`, `-processor` và `-processorpath` được khai báo **khi gọi `javac`**:

- `-Akey=value`: truyền dữ liệu tùy chọn.
- `-processor fully.qualified.ProcessorName`: chọn processor cần chạy.
- `-processorpath path`: nơi compiler tìm processor và dependency khi nạp.
- `-proc:only`: chỉ chạy annotation processing và không thực hiện bước biên dịch thông thường ra classfile ứng dụng.
- `-proc:none`: tắt annotation processing.

Dù build tool đã truyền `-Aaudit.prefix=CHECK`, processor vẫn phải khai báo `audit.prefix` là option được hỗ trợ và tự giải thích cách xử lý giá trị. Ngược lại, chỉ thêm `@SupportedOptions` vào processor không tự thêm `-A...` vào lệnh build.

Một số tool build (Maven, Gradle, IDE) giúp đóng gói/khai báo processor, nhưng **metadata hỗ trợ là hợp đồng của processor**, còn lựa chọn chạy/option là trách nhiệm của build invocation.

## 8. Tải processor: chọn tường minh và tự động phát hiện

Ví dụ sử dụng `-processor demo.proc.AuditProcessor` để không phụ thuộc cơ chế khám phá mặc định. Trong dự án thật, một JAR processor có thể đăng ký thông qua service provider file:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nội dung file là tên class processor:

~~~text
demo.proc.AuditProcessor
~~~

Đây là **cấu hình service provider**, không phải tệp Java và không phải một phần của ba `@Supported...` annotation. Nó có thể cho công cụ phát hiện processor từ vị trí được cấu hình thích hợp trên processor path, tùy chính sách của phiên bản `javac` và build tool.

Không nên khẳng định mọi compiler/JDK phiên bản mới sẽ **tự quét classpath và chạy mọi processor** chỉ vì JAR có service file. Chính sách mặc định annotation processing đã thay đổi qua các phiên bản JDK; với quy trình cần tái lập, hãy **chỉ định rõ processor hoặc cấu hình processor path và chế độ processing** trong build.

Ngoài ra, khi tạo JAR processor cần đóng gói đủ các class phụ thuộc của processor, không chỉ class chính. Trong bài này, `AuditProcessor` phụ thuộc trực tiếp `Audited.class`, nên `build/processor` chứa cả hai. Khi nạp ở môi trường thật, compiler phải tìm được những class ấy trên đường tải processor.

## 9. Các vòng xử lý và ý nghĩa của lựa chọn hỗ trợ

Annotation processing có thể có **nhiều round**. Nếu một processor tạo thêm tệp nguồn hợp lệ, compiler có thể đưa các tệp mới vào round tiếp theo. Do đó:

- `roundEnv.getElementsAnnotatedWith(...)` trả các phần tử phù hợp trong **round hiện tại**, không phải nhất thiết toàn bộ project ở mọi round.
- `roundEnv.processingOver()` cho biết lượt xử lý kết thúc, phù hợp với một số việc tổng kết/chẩn đoán cuối.
- `roundEnv.errorRaised()` cung cấp thông tin về lỗi đã được phát trong xử lý trước đó; không nên dùng để thay `Diagnostic.Kind.ERROR` cho lỗi do processor phát hiện.
- `process` có thể được gọi nhiều lần; code cần tránh tạo trùng file hoặc lặp side effect không mong muốn.
- `getSupportedAnnotationTypes()` là thông tin công cụ dùng để chọn/phân phối annotation types, không quyết định hộ logic xử lý round của bạn.

Nếu processor có nhiều loại annotation, hãy xử lý chúng phù hợp và quyết định rõ khi nào claim. Không cần `return true` nếu processor chỉ quan sát annotation và muốn cho processor khác xử lý tiếp, nhưng việc trả `false` cũng không tự bảo đảm mọi processor được gọi ở mọi bối cảnh. Cần đọc hợp đồng cụ thể của `Processor`.

### Tránh lỗi về phạm vi tên

Giả sử annotation nằm ở `com.company.audit.Audited` nhưng metadata viết:

~~~java
@SupportedAnnotationTypes("demo.ann.Audited")
~~~

Khi đó annotation của ứng dụng không khớp với tên mà processor tuyên bố hỗ trợ; processor có thể không nhận được annotation cần thiết, dù code bên trong `process` đúng về mặt cú pháp.

Đừng dùng `"*"` để che lỗi khai báo tên. Hãy sửa đúng fully qualified name, kiểm tra processor đã được nạp, dùng tùy chọn chẩn đoán các round nếu cần và bảo đảm annotation thực sự có mặt ở nguồn đang biên dịch.

## 10. Các lỗi điển hình và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Không thấy NOTE do processor tạo | Processor không được chọn/nạp, annotation name không khớp hoặc code chưa chạy qua round có annotation | Kiểm tra `-processor`, processor path và `@SupportedAnnotationTypes` |
| `Annotation processor ... not found` | Class processor hoặc dependency thiếu/sai trên processor path | Kiểm tra đường dẫn và class file |
| Build chạy nhưng `-A...` không có hiệu lực | Key gõ sai, option không được đọc hoặc có mặc định | Kiểm tra `@SupportedOptions` và `processingEnv.getOptions()` |
| Warning “option ... not recognized” | Không có processor nào nhận key ấy | Kiểm tra tên key chính xác và danh sách supported |
| Warning “supported source version ... less than -source ...” | Processor tuyên bố hỗ trợ mức nguồn cũ hơn mức đang biên dịch | Đánh giá tương thích và cập nhật `SourceVersion` có kiểm thử |
| `UnsupportedClassVersionError` khi tải processor | Bytecode processor mới hơn JVM đang chạy compiler | Biên dịch processor với target phù hợp |
| `package demo.ann does not exist` khi compile app | Classpath compile ứng dụng không có annotation class | Kiểm tra `-cp build/processor` |
| Source được tạo nhiều lần gây `FilerException` | Processor ghi trùng cùng đường dẫn qua nhiều round | Quản lý vòng xử lý và tên file đã tạo |

Để xem thêm hoạt động khi compiler chạy processors, `javac` có các tùy chọn chẩn đoán hữu ích:

~~~sh
javac -XprintRounds -XprintProcessorInfo --release 17 -encoding UTF-8 -cp build/processor -processorpath build/processor -processor demo.proc.AuditProcessor -Aaudit.prefix=CHECK -d build/app appsrc/demo/app/Main.java
~~~

Hai cờ `-XprintRounds` và `-XprintProcessorInfo` giúp in thông tin về round, processor/annotation được xét. Dạng thông báo cụ thể có thể khác theo bản JDK; chúng dùng để **điều tra cấu hình**, không phải API runtime của ứng dụng.

### Thử tắt processing để hiểu ranh giới

Giữ classpath cho annotation nhưng thêm `-proc:none` và bỏ lựa chọn `-processor` khỏi lệnh biên dịch, ví dụ:

~~~sh
javac --release 17 -encoding UTF-8 -cp build/processor -proc:none -d build/app appsrc/demo/app/Main.java
~~~

`Main.java` vẫn có thể biên dịch nếu bản thân annotation class có sẵn và mã nguồn hợp lệ; nhưng **AuditProcessor không chạy**, nên sẽ không có NOTE `CHECK: Main / entrypoint`. Điều này chứng minh việc **sử dụng annotation trong code** và việc **công cụ thực sự chạy processor** là hai bước riêng.

Với `-proc:only`, công cụ chạy processors nhưng không tạo classfile ứng dụng như biên dịch bình thường. Nếu muốn chạy `java demo.app.Main` sau đó, bạn cần một lượt biên dịch tạo classfile ứng dụng phù hợp.

## 11. Thiết kế metadata có thể bảo trì

Một processor có chất lượng không chỉ biên dịch được; nó cần có hợp đồng rõ và ổn định:

**Đối với annotation hỗ trợ:** chọn tên đầy đủ, tránh pattern rộng không cần thiết. Nếu thêm annotation mới, cập nhật metadata, code xử lý và kiểm thử cùng lúc. Nếu muốn processor khác cùng xử lý annotation, thiết kế rõ việc claim với `process`.

**Đối với option:** có tài liệu mô tả key, loại giá trị, mặc định, điều kiện hợp lệ và ảnh hưởng tới output. Cấu hình sai nên sinh thông điệp rõ ràng; không âm thầm fallback nếu lỗi có thể làm kết quả build không đúng. Không đưa bí mật nhạy cảm vào NOTE hoặc source generated chỉ vì option có thể truyền bất kỳ chuỗi nào.

**Đối với source version:** chọn mức phù hợp với các cấu trúc Java processor thực sự hiểu. Khi nâng JDK, chạy bộ kiểm thử trên các phiên bản `--release`/`-source` được công bố; không tăng hằng số chỉ để xóa warning.

**Đối với build tái lập:** tách processor artifact khỏi ứng dụng, xác định classpath/processor path rõ ràng, chọn processor tường minh hoặc đăng ký dịch vụ đúng, và kiểm tra build không vô tình dùng processor cũ.

**Đối với chẩn đoán:** dùng `Messager` với mức `ERROR` cho điều kiện không hợp lệ, `WARNING` khi có rủi ro đáng chú ý, `NOTE` cho thông tin ngắn cần thiết. Tránh flood NOTE mỗi round hoặc in dữ liệu nhạy cảm của option ra log CI.

Một quy trình review có thể kiểm tra trực tiếp ba method:

~~~java
getSupportedAnnotationTypes()
getSupportedOptions()
getSupportedSourceVersion()
~~~

và so sánh chúng với hành vi thực tế trong `process(...)`. Đây là cách phát hiện sai khác giữa “processor quảng cáo gì” và “processor làm gì”.

## 12. Bài thực hành

**Bài 1 — Không truyền option.** Biên dịch ứng dụng với `-processor demo.proc.AuditProcessor` nhưng bỏ `-Aaudit.prefix=CHECK`. Giải thích vì sao NOTE dùng prefix mặc định `AUDIT`, và tại sao `@SupportedOptions` không tự cung cấp mặc định.

**Bài 2 — Key bị gõ sai.** Thay `-Aaudit.prefix=CHECK` bằng `-Aaudit.prefx=CHECK`. Quan sát compiler log và thông điệp processor. Phân biệt “option được tuyên bố hỗ trợ” với “giá trị thật lấy từ map”.

**Bài 3 — Tên annotation không khớp.** Trong một bản thử, thay metadata `@SupportedAnnotationTypes("demo.ann.Audited")` thành một tên khác rồi biên dịch lại processor. Dự đoán vì sao phần tử `@Audited` không được processor nhận như trước. Sửa lại tên đầy đủ.

**Bài 4 — Dữ liệu annotation không hợp lệ.** Thay `@Audited("entrypoint")` bằng `@Audited("")`. Processor phát chẩn đoán `ERROR` trên phần tử; giải thích tại sao `return true` không làm lỗi ấy trở thành thành công.

**Bài 5 — SourceVersion.** Dùng JDK hỗ trợ Java cao hơn 17 và biên dịch ứng dụng ở mức nguồn cao hơn 17. Quan sát cảnh báo source version nếu được compiler phát ra; phân biệt việc nâng `SourceVersion` với thay đổi `--release` và việc chạy test tương thích.

**Bài 6 — Tắt processing.** Chạy `-proc:none` như phần 10. Vì sao annotation vẫn có thể tồn tại trong nguồn nhưng processor không tạo NOTE? Khi nào `-proc:only` hữu ích?

**Bài 7 — Thiết kế option thứ hai.** Giả sử muốn hỗ trợ `-Aaudit.mode=strict`. Hãy xác định thay đổi ở `@SupportedOptions`, cách đọc `getOptions()`, giá trị hợp lệ và thông báo khi người dùng truyền sai `audit.mode`.

### Tự đánh giá

1. **`@SupportedAnnotationTypes` dùng để làm gì?** — Tuyên bố tập tên annotation types mà processor hỗ trợ; thông thường dùng fully qualified names.
2. **`"*"` có nên là mặc định?** — Không; nó quá rộng trừ khi processor thật sự có mục đích xử lý bao quát.
3. **`@SupportedOptions` lưu giá trị option không?** — Không; nó tuyên bố key; giá trị được đọc từ `processingEnv.getOptions()`.
4. **`-Aaudit.prefix=CHECK` tác động ở đâu?** — Khi `javac` chạy annotation processing, không phải khi JVM chạy ứng dụng.
5. **`@SupportedSourceVersion(RELEASE_17)` có ép JVM sử dụng Java 17?** — Không; nó là tuyên bố hỗ trợ mức nguồn của processor.
6. **Khác biệt giữa `--release 17` và `RELEASE_17` trong annotation?** — Cái trước cấu hình compilation target; cái sau là metadata khả năng xử lý nguồn của processor.
7. **`process` trả `true` có nghĩa build thành công không?** — Không; đó là việc claim các annotation types được cung cấp.
8. **Khi nào dùng `Messager.ERROR`?** — Khi phát hiện một điều kiện sai phải làm compilation thất bại, chẳng hạn giá trị annotation không hợp lệ.
9. **Vì sao ví dụ có cả `-cp` và `-processorpath`?** — Một bên phục vụ mã ứng dụng nhìn thấy annotation class, một bên phục vụ compiler nạp processor và dependency.
10. **Khi đổi JDK mới, có nên tự động tăng SourceVersion?** — Chỉ sau khi kiểm tra processor hiểu đúng nguồn và mô hình Java mới.
11. **Tại sao không dựa duy nhất vào tự động khám phá processor?** — Vì behavior và cấu hình build/JDK có thể khác; chọn tường minh giúp ví dụ tái lập.

**Kết nối kiến thức:** Một annotation processor đáng tin cậy cần **khai báo chính xác phạm vi annotation**, **định nghĩa rõ hợp đồng tùy chọn** và **công bố mức Java source đã kiểm chứng**. Ba phần metadata đó gắn trực tiếp với cấu hình `javac` và vòng xử lý annotation; hiểu chúng giúp bạn phân biệt lỗi processor không chạy, nhận sai option, hoặc không tương thích phiên bản nguồn — thay vì sửa mò trong code ứng dụng.