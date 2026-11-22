# Khai báo loại annotation, tùy chọn và phiên bản nguồn được hỗ trợ khi viết Annotation Processor (Java 17+)

Một **annotation processor** là chương trình chạy trong **quá trình biên dịch Java** để quan sát các khai báo cùng annotation và thực hiện những công việc như kiểm tra quy ước, báo lỗi bằng compiler diagnostics hoặc sinh file nguồn/tài nguyên. Để compiler biết processor **nhận những annotation type nào**, **hiểu những tùy chọn nào** và **hỗ trợ phiên bản cú pháp Java nào**, Java cung cấp ba meta-annotation chuẩn trong package `javax.annotation.processing`:

~~~java
@SupportedAnnotationTypes("demo.DemoMark")
@SupportedOptions("message")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class DemoProcessor extends AbstractProcessor {
    // Triển khai process(...) để xử lý các vòng biên dịch.
}
~~~

Đoạn trên là **mẫu rút gọn**, không phải file chạy độc lập. Bài này trình bày đầy đủ ý nghĩa, giới hạn, cách tương tác với `javac`, cách lấy tùy chọn, sự khác biệt giữa annotation trên **processor class** và annotation trên **mã nguồn đích**, cùng một ví dụ Java 17 đã kiểm chứng.

## 1. Mục tiêu học tập

Sau bài này bạn có thể:

- Phân biệt **annotation type cần xử lý** với **processor class thực hiện xử lý**.
- Dùng đúng `@SupportedAnnotationTypes` để khai báo tên đầy đủ của các annotation type mà processor nhận biết.
- Dùng `@SupportedOptions` để đăng ký khóa cấu hình, truyền bằng cú pháp `javac -Akey=value` và đọc qua `ProcessingEnvironment.getOptions()`.
- Dùng `@SupportedSourceVersion` cùng `SourceVersion.RELEASE_17`; phân biệt phiên bản **nguồn đang biên dịch** với phiên bản JDK đang chạy processor.
- Hiểu cách `AbstractProcessor` cung cấp `getSupportedAnnotationTypes()`, `getSupportedOptions()` và `getSupportedSourceVersion()` từ những meta-annotation trên.
- Tạo, biên dịch và chạy một processor Java 17+; kiểm tra stdout chuẩn từ processor qua `javac`.
- Nhận biết lựa chọn processor bằng `-processor`, classpath/processorpath, khả năng đăng ký `META-INF/services` và các vòng xử lý.
- Tránh lỗi sai tên annotation, sai tùy chọn, thiếu phiên bản hỗ trợ hoặc nhầm cơ chế compile-time với Reflection runtime.

## 2. Đặt đúng ba lớp khái niệm

Xét tình huống bạn tạo annotation `@DemoMark` để đánh dấu những class cần được kiểm tra trong lúc biên dịch. Có ba đối tượng khác nhau:

1. **Annotation type:** `demo.DemoMark` được khai báo bằng `public @interface DemoMark`. Mã dự án sử dụng `@DemoMark` trên class.
2. **Processor:** `demo.DemoProcessor` là một **class Java** triển khai hợp đồng `javax.annotation.processing.Processor`, thông thường bằng cách kế thừa `AbstractProcessor`. Nó nhận thông tin từ compiler và xử lý các phần tử được đánh dấu.
3. **Meta-annotation cấu hình processor:** `@SupportedAnnotationTypes`, `@SupportedOptions`, `@SupportedSourceVersion` được đặt lên **class processor**, không phải lên class mà processor muốn kiểm tra.

Mô hình:

~~~text
src/demo/DemoMark.java
        |
        |  khai báo @interface DemoMark
        v
src/demo/Example.java: @DemoMark trên class
        |
        |  javac --release 17 -processor demo.DemoProcessor
        v
src/demo/DemoProcessor.java (đã được biên dịch sẵn)
        |
        +--> @SupportedAnnotationTypes("demo.DemoMark")
        +--> @SupportedOptions("message")
        +--> @SupportedSourceVersion(RELEASE_17)
        |
        +--> process(annotations, roundEnv)
                |
                +--> đọc -Amessage=hello từ processingEnv
                +--> tìm class được gắn @DemoMark
                +--> kiểm tra / báo diagnostics / sinh mã nếu cần
~~~

**Quan trọng:** `@SupportedAnnotationTypes` không được gắn trên `@interface DemoMark` để khiến nó tự xử lý chính nó. Processor vẫn cần được biên dịch, được compiler lựa chọn/khám phá và có mã `process(...)` thực thi.

## 3. `@SupportedAnnotationTypes` — khai báo annotation type được xử lý

Khai báo điển hình:

~~~java
import javax.annotation.processing.SupportedAnnotationTypes;

@SupportedAnnotationTypes("demo.DemoMark")
public class DemoProcessor extends AbstractProcessor {
    // ...
}
~~~

Cách dùng:

- Giá trị của annotation là `String[]`: có thể truyền **một tên** như ví dụ hoặc nhiều tên `{"demo.DemoMark", "demo.Check"}`.
- Dùng **tên chuẩn có package** của annotation type, ví dụ `demo.DemoMark`. Chỉ viết `"DemoMark"` khi type nằm trong unnamed package; trong dự án thực tế nên đặt package và dùng tên chính xác.
- Đây là **bộ lọc tên annotation**, không phải danh sách tên class nguồn, không phải tên processor và không phải danh sách package nguồn cần quét.
- `"*"` là một pattern để biểu thị hỗ trợ tất cả annotation types; cũng có những pattern theo namespace cho tên annotation. Dùng wildcard cẩn thận, vì nhận quá nhiều loại có thể gây xử lý ngoài phạm vi.
- Trong trường hợp module system, việc xác định tên có thể xét module-qualified names theo quy tắc của annotation processing API; ví dụ Java 17 dưới đây cố ý dùng package thường và tên đầy đủ đơn giản.

Thông tin được quảng bá qua:

~~~java
Set<String> supported = processor.getSupportedAnnotationTypes();
~~~

Nếu kế thừa `AbstractProcessor` và không ghi đè method, implementation mặc định có thể đọc thông tin từ `@SupportedAnnotationTypes` trên processor class.

**Hệ quả của tên sai:** Ví dụ project có annotation `demo.DemoMark` nhưng bạn khai báo `@SupportedAnnotationTypes("DemoMark")`, processor có thể không được gọi như mong đợi cho annotation đó. Hãy kiểm tra package, chữ hoa/thường và phần định danh của annotation type.

### Nhiều annotation types

~~~java
@SupportedAnnotationTypes({
    "demo.DemoMark",
    "demo.CompileCheck"
})
class MultiProcessor extends AbstractProcessor {
    // ...
}
~~~

Đây là ví dụ về **metadata hỗ trợ**, không phải processor hoàn chỉnh: class trên vẫn cần method `process(...)` để kế thừa `AbstractProcessor` hợp lệ trong một chương trình thực tế.

### Trả về `true`/`false` từ `process(...)`

Chữ ký của processor:

~~~java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    // ...
    return true;
}
~~~

Giá trị `true` nghĩa là processor **claim** các annotation types thuộc lượt xử lý mà nó nhận được, theo quy tắc của hệ thống xử lý annotation; các processor khác không tiếp tục được mời xử lý những annotation types đã claim trong cùng cách điều phối. `false` nghĩa là không claim chúng. Điều này **không** có nghĩa compiler sẽ dừng ngay mọi processing rounds, không có nghĩa mã target tự chạy và cũng không chứng minh processor đã tạo file thành công.

Nếu khai báo `@SupportedAnnotationTypes("*")` và luôn `return true`, hãy lưu ý tác động tới các processor khác. Khi thiết kế thư viện, thường nên đăng ký đúng các annotation types thực sự xử lý thay vì “ôm hết” mà không cần.

## 4. `@SupportedOptions` — khai báo các khóa tùy chọn hỗ trợ

Processor có thể có cấu hình như bật chế độ nghiêm ngặt, chọn tên file đầu ra hoặc đặt một tiền tố. Thay vì hard-code, người dùng đưa option khi biên dịch.

Khai báo:

~~~java
import javax.annotation.processing.SupportedOptions;

@SupportedOptions({"message", "strict"})
class ConfiguredProcessor extends AbstractProcessor {
    // ...
}
~~~

Nguyên tắc:

- Trong `@SupportedOptions` khai báo **tên khóa**, ví dụ `"message"` hoặc `"strict"`; **không** bao gồm tiền tố `-A`.
- Tại command line truyền `-Amessage=hello` hoặc `-Astrict=true` cho `javac`. `-Akey=value` là option **cho annotation processor**, không giống `-Dkey=value` dành cho Java system properties.
- Processor đọc bản đồ khóa–giá trị qua `processingEnv.getOptions()`. Thông thường dùng `get("message")` hoặc kiểm tra `containsKey("strict")`.
- Khi không truyền một option, tra cứu key đó có thể trả `null`. Hãy cung cấp mặc định trong logic của processor nếu cần.
- `@SupportedOptions` **chỉ quảng bá những khóa processor hiểu**, nó không tự parse số, ép boolean, áp dụng default hay kiểm tra giá trị. Chính mã `process(...)` hoặc mã khởi tạo phải kiểm tra.
- Compiler có thể cảnh báo những option `-A...` không được processor nào công nhận. Do đó nên công bố đúng tên các option thực sự được xử lý và dùng chúng nhất quán.

Ví dụ đọc option:

~~~java
String message = processingEnv.getOptions()
        .getOrDefault("message", "default");
boolean strict = Boolean.parseBoolean(
        processingEnv.getOptions().getOrDefault("strict", "false"));
~~~

Đây là đoạn minh họa nằm **bên trong một processor đã được khởi tạo**. Nếu bạn cần kiểm tra `strict` chỉ nhận `true`/`false`, nên tự xác nhận chuỗi; `Boolean.parseBoolean("unexpected")` trả `false` thay vì ném lỗi, dễ che giấu typo trong cấu hình.

### Tùy chọn có namespace

Một processor có thể đặt khóa có cấu trúc, ví dụ `demo.mode`, rồi truyền `-Ademo.mode=fast` và đọc `get("demo.mode")`. Sử dụng một namespace nhất quán đặc biệt hữu ích khi build có nhiều processor, tránh hai thư viện vô tình dùng cùng một key.

`-A...` không quyết định processor nào được tải. Chúng chỉ cung cấp option cho những processor được compiler lựa chọn; để chọn cụ thể processor hãy dùng `-processor` hoặc phương án discovery phù hợp.

## 5. `@SupportedSourceVersion` — phiên bản ngôn ngữ Java được hỗ trợ

Ví dụ:

~~~java
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;

@SupportedSourceVersion(SourceVersion.RELEASE_17)
class Java17Processor extends AbstractProcessor {
    // ...
}
~~~

`SourceVersion` nằm trong package `javax.lang.model`. `RELEASE_17` là hằng enum tương ứng với source version Java 17. Method API có liên quan:

~~~java
SourceVersion sourceVersion = processor.getSupportedSourceVersion();
~~~

Giá trị này nói **processor khai báo hỗ trợ cấu trúc/ngôn ngữ nguồn Java đến phiên bản nào**. Nó **không** có nghĩa:

- Processor tự động biên dịch source thành Java 17 bytecode.
- Processor buộc JVM hiện tại phải là JDK 17.
- Processor đặt phiên bản của annotation type hoặc library.
- Compiler bỏ qua tùy chọn `--release`/`-source` của lệnh biên dịch.
- Bất cứ tính năng mới nào sau Java 17 được processor hỗ trợ chỉ vì JDK đang chạy là phiên bản mới hơn.

Trong ví dụ chính, ta dùng **`javac --release 17`**. Điều này yêu cầu compiler biên dịch theo mức release 17; cả các API Java chuẩn và class file output được giới hạn phù hợp bởi tùy chọn đó. `@SupportedSourceVersion(RELEASE_17)` mô tả mức mà processor tự công bố, không thay thế `--release 17`.

Khi biên dịch bằng JDK mới hơn với `--release 21` trong khi processor chỉ công bố `RELEASE_17`, compiler có thể đưa ra cảnh báo rằng supported source version của processor thấp hơn phiên bản nguồn đang dùng. Hãy chọn chính sách nâng cấp rõ ràng: kiểm tra processor với phiên bản Java mới và cập nhật hỗ trợ khi đã xác minh.

### Có cần dùng phiên bản cố định không?

Dùng `@SupportedSourceVersion(SourceVersion.RELEASE_17)` khi bạn muốn tuyên bố mức hỗ trợ cụ thể, có kiểm thử. Nếu thực sự tương thích các phiên bản mới và muốn đánh giá dựa trên compiler hiện tại, có thể **ghi đè** `getSupportedSourceVersion()`, ví dụ:

~~~java
@Override
public SourceVersion getSupportedSourceVersion() {
    return SourceVersion.latestSupported();
}
~~~

Đây là một lựa chọn thiết kế nâng cao. `latestSupported()` không chứng minh mã processor của bạn đã xử lý đúng mọi tính năng source mới; cần test thật. Nếu override method này, kết quả method override là nguồn trả lời API thay vì mặc định của `AbstractProcessor` dựa trên `@SupportedSourceVersion`.

## 6. Ví dụ Java 17+ trọn vẹn: processor đọc đủ ba cấu hình

Bài thực hành dùng **ba file Java** cùng package `demo` và một thư mục output `build`. Processor được biên dịch trước; sau đó `javac` mới nạp nó để xử lý file đích. Cách làm này không cần thiết lập cơ chế ServiceLoader vì ta chỉ định processor tường minh bằng `-processor`.

### 6.1. `src/demo/DemoMark.java` — định nghĩa annotation đích

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface DemoMark {}
~~~

`DemoMark` chỉ đánh dấu khai báo kiểu; retention `SOURCE` đã **đủ** cho annotation processor tại compile-time. Không cần `RUNTIME` để `javac` đưa annotation này cho processor.

### 6.2. `src/demo/DemoProcessor.java` — khai báo processor

~~~java
package demo;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedOptions;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("demo.DemoMark")
@SupportedOptions("message")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class DemoProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        int count =
                roundEnv.getElementsAnnotatedWith(DemoMark.class).size();

        if (count > 0) {
            System.out.println("types="
                    + String.join(",", getSupportedAnnotationTypes()));
            System.out.println("options="
                    + String.join(",", getSupportedOptions()));
            System.out.println("version=" + getSupportedSourceVersion());
            System.out.println("message="
                    + processingEnv.getOptions().get("message"));
            System.out.println("marked=" + count);
        }

        return true;
    }
}
~~~

Điểm nổi bật:

- Class kế thừa `AbstractProcessor`, do đó được cung cấp `ProcessingEnvironment` qua việc compiler khởi tạo processor và gọi `init(...)` theo hợp đồng API.
- `getSupportedAnnotationTypes()`, `getSupportedOptions()`, `getSupportedSourceVersion()` được `AbstractProcessor` triển khai dựa vào ba annotation khai báo trên `DemoProcessor`.
- `roundEnv.getElementsAnnotatedWith(DemoMark.class)` trả các element được gắn `@DemoMark` trong lượt xử lý hiện tại; trong demo có một class.
- `roundEnv.processingOver()` dùng để nhận biết vòng cuối, nơi không nên tiếp tục sinh mã mới; demo bỏ qua in ở vòng cuối để stdout ổn định.
- `count > 0` tránh in bản tóm tắt trong các vòng compiler không có element phù hợp.
- Code chọn `System.out.println(...)` **chỉ để bài học có stdout có thể kiểm chứng**. Processor production thường dùng `processingEnv.getMessager().printMessage(Diagnostic.Kind.NOTE, ...)` cho thông tin hoặc `ERROR` khi phát hiện vi phạm, vì diagnostics tích hợp compiler tốt hơn.
- `return true` thông báo processor đã claim các annotation types xử lý trong round theo quy tắc API; không phải trả kết quả `true`/`false` từ một phép validation duy nhất.

### 6.3. `src/demo/Example.java` — code được xử lý

~~~java
package demo;

@DemoMark
public class Example {}
~~~

Đây là class nguồn mục tiêu; không cần `main`. Processor đọc class này trong lúc `javac` biên dịch, không phải qua `java Example`.

### 6.4. Biên dịch rồi kích hoạt processor

Từ **thư mục cha của `src`**, chạy theo thứ tự:

~~~bash
javac --release 17 -d build src/demo/DemoMark.java src/demo/DemoProcessor.java

javac --release 17 \
  -cp build \
  -processorpath build \
  -processor demo.DemoProcessor \
  -Amessage=hello \
  -d build \
  src/demo/Example.java
~~~

Ký hiệu `\` dùng để xuống dòng lệnh theo **shell Bash/POSIX**. Trên Windows PowerShell, hãy viết toàn bộ lệnh thứ hai trên một dòng (hoặc dùng cách nối dòng của PowerShell), ví dụ:

~~~powershell
javac --release 17 -cp build -processorpath build -processor demo.DemoProcessor -Amessage=hello -d build src/demo/Example.java
~~~

Ý nghĩa:

- Bước đầu tạo `build/demo/DemoMark.class` và `build/demo/DemoProcessor.class`. Nếu thư mục `build` chưa có, `javac -d build` có thể yêu cầu bạn tạo thư mục trước trong một số môi trường; cách chắc chắn là tạo `build` trước khi chạy.
- `-cp build` khiến `DemoMark` và các class phụ thuộc sẵn có cho việc compile `Example`.
- `-processorpath build` chỉ nơi compiler tìm class của annotation processor. Dự án thật thường dùng processor JAR nằm trên processor path riêng.
- `-processor demo.DemoProcessor` **chỉ định processor theo tên đầy đủ**, không trông chờ auto-discovery.
- `-Amessage=hello` cung cấp option `message` với giá trị `hello`.
- `--release 17` giữ ví dụ ở phiên bản Java 17; compiler JDK 17 hoặc mới hơn cần hỗ trợ release này.
- `-d build` là thư mục đích của class files biên dịch từ mã nguồn target.

**Stdout của bước `javac` thứ hai:**

~~~text
types=demo.DemoMark
options=message
version=RELEASE_17
message=hello
marked=1
~~~

Các dòng trên đã được kiểm chứng bằng `javac --release 17` trên JDK có hỗ trợ release 17. Compiler thông thường không thêm các dòng khác nếu không có warning/error; khi IDE hoặc công cụ build bọc compiler, giao diện hiển thị diagnostics/stdout có thể khác.

**Diễn giải từng dòng:**

1. `types=demo.DemoMark` xác nhận processor công bố nhận `demo.DemoMark`.
2. `options=message` xác nhận `@SupportedOptions` đăng ký khóa `message`.
3. `version=RELEASE_17` là giá trị `SourceVersion` mà processor khai báo.
4. `message=hello` xác nhận `processingEnv.getOptions().get("message")` đọc đúng option được truyền.
5. `marked=1` xác nhận `RoundEnvironment` thấy một khai báo `@DemoMark` trong round liên quan.

Nếu bỏ `-Amessage=hello`, dòng `message=...` có thể in `null` do processor demo không có fallback; trong code thực tế nên xử lý thiếu tùy chọn.

## 7. Processor hoạt động qua các vòng xử lý (rounds)

Annotation processing không phải một callback duy nhất cho toàn bộ dự án. Compiler có thể tổ chức **nhiều round**, đặc biệt khi processor sinh file nguồn mới qua `Filer`. Mỗi vòng `process(...)` được cung cấp:

- `Set<? extends TypeElement> annotations`: các annotation types được cung cấp cho processor trong round.
- `RoundEnvironment roundEnv`: môi trường truy vấn các element tham gia round hiện tại và trạng thái vòng xử lý.
- `roundEnv.getElementsAnnotatedWith(...)` để tìm những element có annotation type đang xét.
- `roundEnv.processingOver()` để biết vòng cuối cùng, khi không còn round mới sinh ra từ những source files được tạo.

Trong ví dụ, processor **không tạo file mới**, nên có một round chứa `Example` và round kết thúc. Mã chủ động không in khi `processingOver()` là `true`; đây là cách giữ stdout dễ dự đoán khi dạy học.

`getSupportedAnnotationTypes()` mô tả processor **có thể xử lý loại annotation nào**, không cam kết round nào cũng có một element được gắn annotation đó. Vì vậy `count` có thể bằng 0, nhất là khi compiler xử lý nhiều vòng hoặc nhiều source files. Không nên ném lỗi chỉ vì một round thiếu loại annotation mà processor hỗ trợ.

## 8. Processor được chọn hoặc khám phá như thế nào?

Ba annotation `@Supported...` **mô tả** một processor; chúng **không tự đăng ký** nó cho mọi lần chạy `javac`. Compiler phải tìm được processor:

**Cách 1 — chỉ định rõ**, phù hợp bài thực hành:

~~~bash
javac -processor demo.DemoProcessor -processorpath build -cp build src/demo/Example.java
~~~

Cách này có thể kết hợp `--release 17`, `-Amessage=hello` và `-d build` như ví dụ chính. Ưu điểm là dễ kiểm soát processor nào được thực thi, không phụ thuộc vào bản ghi ServiceLoader.

**Cách 2 — đăng ký service provider** trong một JAR hoặc classpath mà compiler dùng để khám phá processor:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nội dung file service là tên class processor đầy đủ, chẳng hạn:

~~~text
demo.DemoProcessor
~~~

Đây là **nội dung file service**, không phải lệnh Bash và không phải mã Java. Khi processor có mặt đúng đường dẫn tìm kiếm và môi trường compiler bật/cho phép annotation processing, cơ chế service discovery có thể nạp processor. Khi đóng gói JAR, phải giữ nguyên đường dẫn `META-INF/services/...`. Với các JDK và cấu hình build hiện đại, chính sách xử lý annotation mặc định có thể khác nhau, nên build sản phẩm phải khai báo rõ processor path/processing configuration thay vì đoán compiler luôn tự chạy processor.

**Không đặt** tên class annotation `demo.DemoMark` vào file service; service yêu cầu implementation của `javax.annotation.processing.Processor` như `demo.DemoProcessor`.

**Cách 3 — API biên dịch trong ứng dụng**: `JavaCompiler` và tooling có thể cấu hình processor theo chương trình, nhưng đó là chủ đề nâng cao. Trong bài này dùng command line `javac` là đủ rõ cơ chế.

### `-proc:only` và `-proc:none`

- `-proc:only` yêu cầu chạy annotation processing **mà không tiếp tục giai đoạn compile thông thường để tạo class files từ source target**, thích hợp kiểm thử processor hoặc sinh source.
- `-proc:none` tắt annotation processing khi compile.
- Để yêu cầu processing một cách rõ ràng, có thể dùng `-processor` như bài thực hành; khi thử với JDK mới, đừng chỉ trông chờ “đã có processor JAR là compiler tự chạy”.

Lưu ý `-proc:only` không giúp process một processor chưa được biên dịch/nạp hợp lệ. `DemoProcessor` vẫn phải có mặt trước trên `-processorpath`.

## 9. Đăng ký bằng annotation và ghi đè bằng method

`AbstractProcessor` đọc các annotation chuẩn để đáp ứng các method của interface `Processor`. Ba cặp cần nhớ:

| Meta-annotation trên processor class | Method tương ứng | Loại dữ liệu |
| --- | --- | --- |
| `@SupportedAnnotationTypes({...})` | `getSupportedAnnotationTypes()` | `Set<String>` |
| `@SupportedOptions({...})` | `getSupportedOptions()` | `Set<String>` |
| `@SupportedSourceVersion(SourceVersion.RELEASE_17)` | `getSupportedSourceVersion()` | `SourceVersion` |

Nếu một implementation **ghi đè** các method này, compiler sẽ sử dụng giá trị mà method override trả về. Ví dụ có thể hỗ trợ một tập annotation types được xác định bởi mã processor:

~~~java
@Override
public Set<String> getSupportedAnnotationTypes() {
    return Set.of("demo.DemoMark", "demo.CompileCheck");
}
~~~

Đây là đoạn minh họa trong thân một processor, cần `import java.util.Set;`. Với mức độ nâng cao, method override cũng có thể phụ thuộc vào trạng thái compiler theo API contract, nhưng phải tránh giả định `processingEnv` đã được khởi tạo ở mọi thời điểm nếu method được truy vấn trước/ngoài initialization sequence tương ứng.

Đối với bài học nhập môn, **ưu tiên ba annotation khai báo tĩnh**: dễ đọc, dễ kiểm tra và cho thấy đúng mục đích của metadata chuẩn.

Đừng nhầm `@SupportedAnnotationTypes` với `@Target`. `@Target` áp dụng trên annotation type mà bạn tự định nghĩa, ví dụ `@DemoMark` chỉ đặt trên `TYPE`; còn `@SupportedAnnotationTypes` công bố khả năng nhận diện một annotation type **ở phía processor**. Cũng vậy, `@Retention(SOURCE)` của `DemoMark` không thay thế `@SupportedSourceVersion` của processor: một cái nói về **thời gian giữ annotation**, một cái nói về **phiên bản nguồn được hỗ trợ**.

## 10. Các lỗi thường gặp và cách tự kiểm tra

**1. Sai tên package trong `@SupportedAnnotationTypes`.** Nếu dùng `"DemoMark"` nhưng type thực sự là `demo.DemoMark`, processor không nhận đúng annotation. In `getSupportedAnnotationTypes()` và kiểm tra tên đầy đủ.

**2. Đặt `@SupportedAnnotationTypes` lên annotation type thay vì processor class.** Meta-annotation này cấu hình implementation processor; type đích chỉ cần khai báo những meta-annotation phù hợp `@Target`, `@Retention` của nó.

**3. Quên khai báo `@SupportedOptions` nhưng truyền `-Amessage=hello`.** Compiler có thể cảnh báo option không được processor nào nhận biết. Đăng ký `"message"` ở processor, không viết `"-Amessage"`.

**4. Tưởng `@SupportedOptions` tự validate giá trị.** Khóa được công bố không bảo đảm `message` không rỗng hay `strict` là boolean hợp lệ. Hãy tự xác minh giá trị từ `processingEnv.getOptions()` và báo lỗi rõ khi cấu hình sai.

**5. Nhầm `-A` với `-D`.** `-Aname=value` đưa dữ liệu vào annotation processing environment; `-Dname=value` là Java system property của quá trình JVM thích hợp. Hai kênh này không được trao đổi tự động.

**6. Nhầm `@SupportedSourceVersion(RELEASE_17)` với `--release 17`.** Meta-annotation công bố hỗ trợ của processor; command-line `--release` kiểm soát compile target/source API. Nên dùng cả hai đúng vai trò khi kiểm thử.

**7. Biên dịch source target trước khi processor có mặt.** Cần xây dựng processor JAR/classes trước, cấu hình classpath/processorpath, rồi compile những source cần xử lý. Với demo dùng hai lệnh `javac` riêng biệt.

**8. Nhầm classpath với processorpath.** Classpath giúp compiler giải quyết các type được dùng trong source; processor path là nơi compiler tải processor. Demo đặt `build` ở cả hai vì chứa chung `DemoMark` và `DemoProcessor`, nhưng dự án lớn có thể tách các artifact.

**9. Tưởng retention `RUNTIME` mới cho phép compile-time processor đọc annotation.** Annotation có `SOURCE` vẫn được processor nhận khi compiler phân tích mã nguồn; ví dụ `@DemoMark` minh họa chính điều đó.

**10. Cho rằng processor sẽ luôn được chạy khi có class processor.** Không đúng: cần cấu hình annotation processing và cơ chế lựa chọn/khám phá. `-processor demo.DemoProcessor` giúp xác nhận rõ.

**11. In ở mọi processing round và tưởng processor bị gọi lỗi.** Annotation processing có nhiều vòng; khi cần output một lần, kiểm tra `processingOver()` hoặc tổ chức state phù hợp, tránh giả định `process` chỉ được gọi một lần.

**12. Không phân biệt `return true` và `return false`.** Đây là quyết định claim annotation types trong vòng xử lý, không phải mức độ thành công của compiler hay giá trị của annotation.

**13. Công bố wildcard `"*"` một cách tùy tiện.** Processor có thể nhận rộng hơn mục tiêu, nhất là nếu luôn claim annotation types. Hãy giới hạn đúng package/types khi có thể và viết test tích hợp với các processor khác.

**14. Giữ cố định `RELEASE_17` nhưng không test khi nâng Java source.** Khi compiler đang biên dịch release mới hơn, processor có thể cảnh báo hoặc gặp cấu trúc ngôn ngữ mới mà code xử lý chưa hỗ trợ. Test, điều chỉnh mức hỗ trợ và tránh tự tuyên bố `latestSupported()` nếu chưa xác minh.

**15. Dùng `System.out` làm kênh báo lỗi sản phẩm.** Mã bài học dùng stdout để dễ kiểm chứng; processor thực tế nên ưu tiên `Messager` cho diagnostics, đặc biệt `Diagnostic.Kind.ERROR` khi muốn compiler báo lỗi.

## 11. Bài tập thực hành theo độ khó tăng dần

1. Chạy ba file `DemoMark`, `DemoProcessor`, `Example` đúng như ví dụ. Giải thích mỗi dòng stdout và cho biết annotation type nào được processor nhận.
2. Đổi `-Amessage=hello` thành `-Amessage=team`. Kiểm chứng rằng dòng `message=team` thay đổi nhưng tập supported types/source version không đổi.
3. Bỏ `-Amessage`. Quan sát giá trị đọc được trong demo và bổ sung logic mặc định để không in `null`.
4. Thêm option `strict` vào `@SupportedOptions({"message", "strict"})`. Truyền `-Astrict=true`; viết kiểm tra chỉ chấp nhận `true` và `false` rồi dùng `Messager` để báo lỗi khi nhập sai.
5. Tạo thêm `@interface CompileCheck` ở package `demo` và đặt `@SupportedAnnotationTypes({"demo.DemoMark", "demo.CompileCheck"})`. Kiểm tra processor nhận hai loại và điều chỉnh logic `process` để đếm riêng từng loại.
6. Bỏ dấu `@DemoMark` trên `Example` rồi compile. Kiểm tra processor có còn được gọi hay không theo cấu hình sử dụng và vì sao `count > 0` giúp tránh output không liên quan.
7. Thay annotation target `DemoMark` từ `TYPE` sang `METHOD`; thử gắn trên class để xem compiler báo lỗi và phân biệt với filter của `@SupportedAnnotationTypes`.
8. Thay `@Retention(SOURCE)` bằng `CLASS` hoặc `RUNTIME` cho `DemoMark`. Giải thích vì sao compile-time processing vẫn có thể nhìn thấy annotation trong cả ba trường hợp khi mã nguồn được biên dịch.
9. Chạy `javac --release 17 -proc:only ...` để quan sát chỉ chạy processing; sau đó thử `-proc:none` và kiểm tra sự khác biệt. Luôn giữ processor được biên dịch sẵn và compiler options nhất quán.
10. Thay `@SupportedSourceVersion(SourceVersion.RELEASE_17)` bằng việc override `getSupportedSourceVersion()`, trả về `SourceVersion.latestSupported()`. So sánh kết quả trên JDK hiện có và thảo luận rủi ro công bố mức chưa được test.
11. Đóng gói processor thành JAR và thử đăng ký `META-INF/services/javax.annotation.processing.Processor`. So sánh discovery tự động với cách chỉ định tường minh `-processor`; xem chính sách JDK/build tool đang dùng.
12. Viết một validation processor cho `@NonEmptyName` đặt trên class; dùng `processingEnv.getMessager().printMessage(Diagnostic.Kind.ERROR, ..., element)` nếu tên class vi phạm, rồi chứng minh `javac` báo lỗi dù chương trình target chưa chạy.

## 12. Checklist trước khi áp dụng vào dự án

| Câu hỏi | Bạn cần trả lời được |
| --- | --- |
| Processor là class hay annotation type? | Là class triển khai `Processor`, thường kế thừa `AbstractProcessor` |
| Supported annotation types khai báo ở đâu? | `@SupportedAnnotationTypes` trên processor |
| Giá trị `@SupportedAnnotationTypes` thường là gì? | Tên đầy đủ như `"demo.DemoMark"` |
| `@SupportedOptions("message")` đọc giá trị ở đâu? | `processingEnv.getOptions().get("message")` |
| Command-line option truyền thế nào? | `javac -Amessage=hello` |
| Source version processor công bố bằng gì? | `@SupportedSourceVersion(SourceVersion.RELEASE_17)` hoặc override method tương ứng |
| `--release 17` có giống `@SupportedSourceVersion` không? | Không; một cái điều khiển compiler target, một cái mô tả processor hỗ trợ |
| Dùng `@Retention(SOURCE)` trên annotation đích được không? | Được cho compile-time annotation processing |
| Làm sao chắc processor được chạy? | Cấu hình đúng đường dẫn và `-processor` hoặc cơ chế discovery |
| `process(...)` có thể chạy nhiều lần? | Có, theo các rounds |
| `return true` nghĩa là gì? | Claim những annotation types thuộc round theo hợp đồng xử lý |

**Kết luận:** ba meta-annotation chuẩn trên processor **công bố phạm vi, cấu hình và mức nguồn được hỗ trợ** để compiler điều phối xử lý. Chúng không thay thế việc biên dịch/đăng ký processor, không tự validate các option và không quyết định phiên bản bytecode của chương trình. Khi bạn hiểu rõ `@SupportedAnnotationTypes`, `@SupportedOptions`, `@SupportedSourceVersion` và cách chúng tương tác với `AbstractProcessor`, `ProcessingEnvironment` và `javac`, bạn đã có nền tảng vững để phát triển annotation processor Java Core thực tế.

### Tài liệu tham khảo

- [Java SE 17 — SupportedAnnotationTypes](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/SupportedAnnotationTypes.html).
- [Java SE 17 — SupportedOptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/SupportedOptions.html).
- [Java SE 17 — SupportedSourceVersion](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/SupportedSourceVersion.html).
- [Java SE 17 — AbstractProcessor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html).
- [Java SE 17 — Processor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html).
- [Java SE 17 — ProcessingEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html).
- [Java SE 17 — SourceVersion](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/SourceVersion.html).
- [Java SE 17 — javac options (`-A`, `-processor`, `-processorpath`, `--release`)](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html).
