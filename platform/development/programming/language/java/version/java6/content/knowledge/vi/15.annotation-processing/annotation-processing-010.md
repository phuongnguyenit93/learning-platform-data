# javac: -processor, -processorpath, -proc và -A trong annotation processing

## 1. Mục tiêu và bối cảnh

**Annotation processing (JSR 269)** cho phép Java compiler chạy những **annotation processors** tại thời điểm biên dịch để kiểm tra source code, phát chẩn đoán và sinh thêm source/class/resource files. Các tùy chọn `javac` được nêu trong tiêu đề quyết định **processor nào được chạy, tìm processor ở đâu, có thực hiện processing hay không, và truyền cấu hình gì cho processor**.

Bốn nhóm lựa chọn cần phân biệt:

| Tùy chọn | Câu hỏi nó giải quyết | Ví dụ |
| --- | --- | --- |
| `-processor` | **Chạy processor nào?** | `-processor demo.GenProcessor` |
| `-processorpath` hoặc `--processor-path` | **Tải implementation processor và dependency ở đâu?** | `-processorpath build/proc` |
| `-proc:none` / `-proc:only` / `-proc:full` | **Có xử lý annotation hay biên dịch tiếp không?** | `-proc:only` |
| `-Akey[=value]` | **Truyền thông số riêng gì cho processor?** | `-Ademo.prefix=Hola` |

Kết quả học tập: sau bài này, bạn có thể cấu hình annotation processing tường minh trên **JDK 23+**, xây/lắp một processor JSR 269 theo API hiện hành, xác minh tác động của từng `-proc`, đọc `-A` qua `ProcessingEnvironment.getOptions()` và gỡ lỗi khi processor không chạy hoặc chạy sai.

Bài sử dụng **JDK 17+** cho mã Java (build với `--release 17`) và có kiểm thử thực tế bằng `javac 24`. Dùng đúng API chuẩn thuộc `javax.annotation.processing`, `javax.lang.model` và `javax.tools`; dù có tiền tố `javax`, chúng **vẫn là API Java SE hiện hành**, không đổi sang `jakarta.annotation.processing`.

### Thay đổi quan trọng từ JDK 23

**Từ JDK 23, `javac` không tự chạy annotation processor chỉ do nó tình cờ có trên classpath mà không có cấu hình processor.** Cần yêu cầu hoặc cấu hình annotation processing một cách rõ ràng, ví dụ bằng `-processor`, `--processor-path`, `--processor-module-path`, `-proc:only` hoặc `-proc:full`.

Do đó, một build từng tình cờ chạy processor trên các JDK cũ có thể không còn sinh mã khi chuyển sang JDK 23+. Đây là hành vi an toàn có chủ đích, không phải bug của `@interface`.

> Kiến thức còn hiệu lực: `-processorpath` vẫn là alias được tài liệu `javac` hỗ trợ; `--processor-path` là cách viết dài và rõ hơn. `-proc:full` có trên JDK hiện đại và đã được bổ sung vào các bản cập nhật bảo trì tương ứng của một số nhánh JDK cũ. Ví dụ chính không phụ thuộc vào tính năng mới hơn Java 17 vì dùng `-processor` tường minh.

## 2. Một processor được khởi động như thế nào?

```text
                      javac [options] input.java
                                  |
                  +---------------+----------------+
                  |                                |
            Classpath của app                Processor path
           (-cp / --class-path)     (-processorpath / --processor-path)
                  |                                |
         annotation API, dependency       Processor + dependency build-time
                  |                                |
                  +---------------+----------------+
                                  |
                  Chọn processor / bật xử lý
                     -processor hoặc discovery
                     -proc:{none,only,full}
                                  |
                                  v
                        Processor.init(...)
                                  |
                       ProcessingEnvironment
                      .getOptions()  <-- -Akey=value
                                  |
                                  v
                      Processor.process(...)
                         /              \
                Messager ERROR         Filer sinh Java source
                         \              /
                          compilation task
                                  |
                         -s generated-src
                         -d compiled-classes
```

**Bốn vai trò độc lập:**

1. `-cp` / `--class-path` làm **mã ứng dụng đang compile** nhìn thấy API annotation hoặc thư viện được import.
2. `-processorpath` / `--processor-path` làm **javac** tìm và tải **processor implementation** cùng dependencies của nó. Đó là build-time execution path.
3. `-processor` chỉ đích danh processor class, bỏ qua bước tìm processors bằng service discovery mặc định.
4. `-A` đưa dữ liệu cấu hình vào `processingEnv.getOptions()` để chính processor đọc và quyết định hành vi.

Thực tế thường cần **cả classpath lẫn processor path**. Nếu app import `demo.Gen` mà `demo.Gen` chỉ hiện diện ở processor path, mã ứng dụng vẫn có thể gặp lỗi “package does not exist”. Ngược lại, nếu processor chỉ có trên application classpath nhưng không bật processing theo chính sách hiện hành, nó không nhất thiết được chạy.

## 3. `-processor`: chọn processor chạy

Cú pháp:

```text
-processor class1[,class2,class3...]
```

Ví dụ:

```bash
-processor demo.GenProcessor
```

`demo.GenProcessor` là **tên lớp Java fully qualified** triển khai `javax.annotation.processing.Processor` (thường kế thừa `AbstractProcessor`). Nếu muốn chạy nhiều processor, viết danh sách tên bằng dấu phẩy, ví dụ `-processor com.acme.Checker,com.acme.Generator`; không thêm khoảng trắng tùy tiện vào danh sách.

Khi `-processor` được khai báo:

- `javac` sử dụng **danh sách tên được chỉ định**, thay vì chỉ dựa vào việc quét `META-INF/services` để khám phá các processor.
- Mỗi processor vẫn phải là class có thể được compiler **load** cùng dependencies của nó từ path phù hợp.
- Processor quyết định annotation nào mình hỗ trợ qua `@SupportedAnnotationTypes` hoặc `getSupportedAnnotationTypes()`.
- `-processor` không tạo ra implementation từ source chưa biên dịch; **build processor trước** rồi mới dùng nó compile dự án ứng dụng.
- Nếu tên processor sai, implementation không có trên search path hoặc không thể load, compiler báo lỗi thay vì lặng lẽ bỏ qua.

`-processor` đặc biệt phù hợp khi cần **build có thể tái lập và kiểm soát processor nào được quyền chạy**. Để discovery tự động, phải có service provider registration hoặc JPMS provider phù hợp, và annotation processing cũng phải được bật.

### Khi cần nhiều processor

`-processor p.A,p.B` cho biết processors cần chạy; tuy nhiên đừng dựa vào **thứ tự gọi `process(...)`** như một hợp đồng nghiệp vụ. Annotation processing có nhiều rounds và các processors có thể claim annotation types. Nếu các processor cùng xử lý một annotation, cần hiểu việc `process(...)` trả `true`/`false` và ownership của generated files.

## 4. `-processorpath` và `--processor-path`: tìm implementation

Cú pháp tương đương theo tài liệu `javac` hiện hành:

```text
-processorpath path
--processor-path path
```

Ví dụ:

```bash
-processorpath build/proc
```

Trong đó `path` là danh sách directories/JAR chứa **class processor** và thư viện nó cần. Dấu phân cách nhiều phần tử tuân theo nền tảng:

| Nền tảng | Path separator | Ví dụ |
| --- | --- | --- |
| Linux/macOS | `:` | `--processor-path "build/proc:libs/helper.jar"` |
| Windows | `;` | `--processor-path "build/proc;libs/helper.jar"` |

Trên Windows PowerShell cần quote nếu chuỗi có dấu cách hoặc semicolon để tránh shell hiểu nhầm. Hãy sử dụng path chính xác, kiểm tra file/JAR thực sự tồn tại và có các dependencies của processor.

**Khi không đặt processor path**, tài liệu `javac` nói **user classpath** được dùng làm nơi tìm processor. Tuy nhiên đó chỉ là **nơi tìm**, không đồng nghĩa tự bật processing theo mặc định mới của JDK 23+.

**Khi đặt processor path riêng**, đừng mặc định các thư viện chỉ xuất hiện trên `-cp` cũng có sẵn cho processor; cần đưa dependencies mà processor load vào processor path. Đây là cách giảm việc một compile-time plugin phụ thuộc tình cờ vào thư viện của ứng dụng.

### Khác với `-cp`

```bash
-cp build/proc
-processorpath build/proc
```

Hai cờ có cùng chuỗi directory trong ví dụ học tập nhưng **khác trách nhiệm**: `-cp` cho source ứng dụng biết `demo.Gen`; `-processorpath` giúp javac biết `demo.GenProcessor`. Trong ứng dụng lớn, chúng có thể là các artifact khác nhau: `annotations-api.jar` trên application compile classpath và `annotation-processor.jar` cùng dependencies trên processor path.

### Với processor dạng Java module (JPMS)

Nếu processor được đóng gói thành **named module**, dùng `--processor-module-path` và cấu hình service provider bằng `provides javax.annotation.processing.Processor with ...` trong `module-info.java` của processor module. Đừng nhầm processor module path với `--module-path` của ứng dụng đang biên dịch.

## 5. `-proc:none`, `-proc:only`, `-proc:full`: chế độ xử lý

Cú pháp:

```text
-proc:none
-proc:only
-proc:full
```

| Chế độ | Annotation processor có chạy? | Compiler có làm bước biên dịch class thông thường tiếp theo? | Tình huống |
| --- | --- | --- | --- |
| `-proc:none` | **Không** | **Có** | Muốn compile mã không dùng processor; điều tra vấn đề processing hoặc giảm bề mặt thực thi. |
| `-proc:only` | **Có**, nếu được chọn/tìm thấy | **Không** | Chạy validator hoặc xem generated source mà không làm bước biên dịch class thông thường. |
| `-proc:full` | **Có**, nếu được chọn/tìm thấy | **Có** | Annotation processing rồi biên dịch trọn vẹn nguồn gốc và nguồn được sinh. |

**Quan trọng:** `-proc:only` không có nghĩa **không một processor nào có thể tạo file .class**. Một processor có thể tự tạo class file qua `Filer.createClassFile(...)`. Nó có nghĩa compiler không thực hiện **bước biên dịch class thông thường sau annotation processing**. Trong ví dụ phần 7, processor chỉ sinh Java source nên `-proc:only` không cho ra compiled `GreeterGenerated.class`.

`-proc:none` không xóa annotation khỏi mã. `@Gen` vẫn được compiler phân tích như annotation type thông thường; chỉ có **processor không được chạy**, nên `GreeterGenerated` không được sinh. Nếu chương trình có source `Main` tham chiếu `GreeterGenerated`, build `-proc:none` sẽ lỗi “cannot find symbol” trừ khi class này đã tồn tại sẵn trên compile classpath hoặc source input.

### Khi không ghi `-proc`

Trên JDK 23+ hiện hành, nếu người dùng đã **cấu hình xử lý tường minh** bằng tùy chọn như `-processor` hoặc `--processor-path`, `javac` có thể thực hiện processing và biên dịch đầy đủ dù không ghi `-proc:full`. Nếu không có cấu hình processing, mặc định processing sẽ không tự chạy chỉ dựa vào processor tình cờ xuất hiện trên classpath.

Lưu ý rằng `-Akey=value` chỉ cung cấp option cho processor; **không nên xem `-A` một mình là lệnh chắc chắn bật processing**. Khi build có processor bắt buộc, luôn cấu hình `-processor` hoặc processor path/discovery và policy rõ ràng.

### `-proc:full` và tính tương thích

`-proc:full` được giới thiệu trên các nhánh JDK hiện đại và đã được backport sang các bản cập nhật bảo trì như OpenJDK/Oracle JDK **17.0.11**. Nếu dùng JDK 17 rất cũ không có option này, hãy cập nhật JDK hoặc dùng `-processor` tường minh như demo chính. Không cần quay về workflow discovery ngầm cũ.

## 6. `-Akey[=value]`: truyền tham số riêng cho processor

Cú pháp:

```text
-Akey
-Akey=value
```

Ví dụ:

```bash
-Ademo.prefix=Hola
```

`javac` **không diễn giải giá trị nghiệp vụ** của `demo.prefix`; nó đưa option này tới `ProcessingEnvironment.getOptions()`:

```java
Map<String, String> opts = processingEnv.getOptions();
String prefix = opts.get("demo.prefix"); // Ví dụ: "Hola"
```

Đây là đoạn nằm trong processor, chưa phải chương trình độc lập. Với `-Ademo.prefix=Hola`, map chứa entry `"demo.prefix" -> "Hola"`. Với `-Ademo.prefix` **không có dấu bằng/giá trị**, API nói giá trị trong map là **`null`**. Nếu key không có mặt, `opts.containsKey("demo.prefix")` trả `false`; cần phân biệt “key không được truyền” với “key có mặt nhưng giá trị null”.

`key` phải có dạng hợp lệ: **một hoặc nhiều Java identifier phân tách bằng dấu chấm**. Thực hành nên dùng tên có namespace như `demo.prefix` hoặc `org.example.generateMode` để giảm va chạm. Không đặt khoảng trắng giữa `-A`, key và `=value` theo cú pháp.

### Công bố option được hỗ trợ

Kế thừa `AbstractProcessor` và khai báo:

```java
@SupportedOptions("demo.prefix")
public final class GenProcessor extends AbstractProcessor {
    // ...
}
```

Hoặc override `getSupportedOptions()` nếu cần danh sách động. `javac` có thể cảnh báo về option `-A` không được processor nào công bố hỗ trợ; hãy coi cảnh báo này là tín hiệu kiểm tra lỗi đánh máy hoặc cấu hình sai.

`@SupportedOptions` **không tự validate nội dung value**. Processor phải tự kiểm tra `prefix` có hợp lệ với mục tiêu tạo mã hay không. Ví dụ phần 7 chỉ cho phép chữ ASCII để sinh Java string literal mà không cần encoder ký tự phức tạp; nếu người dùng truyền số hoặc dấu nháy, processor gửi `Diagnostic.Kind.ERROR`.

### Windows PowerShell 5.1: nhớ quote `-A`

Trong lệnh PowerShell, nên dùng:

```powershell
javac ... '-Ademo.prefix=Hola' ...
```

Dấu nháy đơn ở đây được shell bỏ đi trước khi chuyển đối số nguyên vẹn cho javac. Nếu viết `-Ademo.prefix=Hola` không quote trong một số ngữ cảnh PowerShell 5.1, shell có thể phân tách đối số sai thành một flag không hợp lệ. Với Bash/Zsh, `-Ademo.prefix=Hola` dùng bình thường khi value không có ký tự shell đặc biệt.

Với giá trị có khoảng trắng hoặc ký tự cần escape, phải quote theo **shell đang dùng**. Ví dụ giá trị `Hello World`:

```bash
javac '-Ademo.prefix=Hello World' ...
```

Đây là minh họa **cú pháp truyền option**, không phải input hợp lệ cho processor ví dụ ở phần 7 (processor đó cố ý chỉ chấp nhận chữ ASCII không có khoảng trắng). Cũng không chèn secrets vào `-A` vì command lines và logs có thể lộ giá trị.

## 7. Demo độc lập: chạy đủ `-processor`, `-processorpath`, `-proc` và `-A`

Demo tạo annotation `@Gen`, processor `GenProcessor` và ứng dụng `Greeter`. Processor nhận `-Ademo.prefix=Hola`, sinh source `demo.GreeterGenerated` trả chuỗi `"Hola Greeter"`. Nó từ chối `-Ademo.prefix=123` bằng compiler error.

### 7.1. Cấu trúc file

```text
processor-options-demo/
├── src/
│   └── demo/
│       ├── Gen.java
│       └── GenProcessor.java
├── app/
│   └── demo/
│       ├── Greeter.java
│       └── Main.java
└── build/                   # Sinh khi làm các bài test
    ├── proc/                # annotation API và processor classes
    ├── full/                # compiled application classes
    ├── gen/                 # source do processor sinh
    ├── only/                # class output của chế độ -proc:only
    ├── onlygen/             # source do -proc:only sinh
    └── none/                # compiled classes của -proc:none
```

### 7.2. `src/demo/Gen.java`

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface Gen {}
```

`RetentionPolicy.SOURCE` đủ để compiler tìm annotation; processor không cần annotation tồn tại trong bytecode sau compile. Tên `Gen` là API metadata, không tự tạo `GreeterGenerated`.

### 7.3. `src/demo/GenProcessor.java`

```java
package demo;

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
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.Gen")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
@SupportedOptions("demo.prefix")
public final class GenProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {

        if (round.processingOver()) {
            return true;
        }

        String prefix = processingEnv.getOptions()
                .getOrDefault("demo.prefix", "Hi");

        for (Element element :
                round.getElementsAnnotatedWith(Gen.class)) {

            // Giới hạn demo để source sinh ra luôn có Java literal hợp lệ.
            if (!prefix.matches("[A-Za-z]+")) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "demo.prefix must contain only ASCII letters",
                        element);
                continue;
            }

            String binaryName = "demo."
                    + element.getSimpleName() + "Generated";

            try {
                JavaFileObject output = processingEnv.getFiler()
                        .createSourceFile(binaryName, element);

                try (Writer writer = output.openWriter()) {
                    writer.write(
                            "package demo; public final class "
                                    + element.getSimpleName()
                                    + "Generated { public static String "
                                    + "message() { return \""
                                    + prefix + " "
                                    + element.getSimpleName()
                                    + "\"; } }");
                }
            } catch (IOException e) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        e.getMessage(), element);
            }
        }
        return true;
    }
}
```

**Các lựa chọn thiết kế:**

- `@SupportedAnnotationTypes("demo.Gen")` khai báo annotation cần xử lý.
- `@SupportedSourceVersion(SourceVersion.RELEASE_17)` phù hợp với `--release 17` trong các lệnh.
- `@SupportedOptions("demo.prefix")` giúp công bố option `-Ademo.prefix=...`.
- `processingEnv.getOptions()` đọc cấu hình từ compiler, không đọc environment variable hoặc command line trong processor.
- `@SupportedOptions` không thay thế kiểm tra value. `matches("[A-Za-z]+")` từ chối `123`, giá trị rỗng, dấu nháy hoặc khoảng trắng để phép nối chuỗi tạo **Java code hợp lệ** trong demo.
- `Filer.createSourceFile` tạo file source mới, truyền `element` làm originating element.
- `try-with-resources` đóng writer để compiler xử lý generated file ở những round tiếp theo.
- `return true` claim annotation types, không có nghĩa compile thành công nếu đã phát diagnostic ERROR.

**Giới hạn ví dụ:** giả định annotated class trong package `demo`, tên class không va chạm với generated classes khác và tiền tố chỉ là chữ cái Latin ASCII. Trong code generator thực tế, cần tính package qua `Elements.getPackageOf`, quy tắc tránh trùng binary name và encoder Java literal đầy đủ cho input bất kỳ. Ví dụ này tập trung vào **chính sách các tùy chọn `javac`**, không triển khai một framework code generation tổng quát.

### 7.4. `app/demo/Greeter.java`

```java
package demo;

@Gen
public final class Greeter {}
```

### 7.5. `app/demo/Main.java`

```java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println(GreeterGenerated.message());
    }
}
```

Lúc đầu **không có** `GreeterGenerated.java` trong cây app. Nó chỉ xuất hiện khi processor thực sự được chạy.

### 7.6. Lệnh xây processor trước

**Linux/macOS:**

```bash
mkdir -p build/proc build/full build/gen build/only build/onlygen build/none
javac --release 17 -d build/proc \
  src/demo/Gen.java src/demo/GenProcessor.java
```

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force build/proc,build/full,build/gen,build/only,build/onlygen,build/none | Out-Null
javac --release 17 -d build/proc src/demo/Gen.java src/demo/GenProcessor.java
```

Processor phải **được biên dịch trước** vì javac cần load class `demo.GenProcessor` để xử lý annotation trong bước kế tiếp. `build/proc` ở đây chứa cả `Gen.class` và `GenProcessor.class`; trong dự án lớn nên phân tách annotation API JAR và processor JAR cho sạch dependencies.

### 7.7. Test 1 — `-processor` + `-processorpath` + `-A`

**Linux/macOS:**

```bash
javac --release 17 \
  -cp build/proc \
  -processorpath build/proc \
  -processor demo.GenProcessor \
  -Ademo.prefix=Hola \
  -s build/gen -d build/full \
  app/demo/Greeter.java app/demo/Main.java

java -cp build/full demo.Main
```

**Windows PowerShell:**

```powershell
javac --release 17 -cp build/proc -processorpath build/proc -processor demo.GenProcessor '-Ademo.prefix=Hola' -s build/gen -d build/full app/demo/Greeter.java app/demo/Main.java
java -cp build/full demo.Main
```

**Stdout chính xác của ứng dụng:**

```text
Hola Greeter
```

Sau khi chạy thành công, hai file tiêu biểu tồn tại:

```text
build/gen/demo/GreeterGenerated.java
build/full/demo/GreeterGenerated.class
```

Dòng `-A` quyết định prefix, `-processor` chọn implementation, `-processorpath` làm compiler tìm được implementation; `-s` là generated source output, `-d` là compiled class output. Không cần viết thêm `-proc:full` ở test này vì `-processor` đã yêu cầu processing tường minh.

### 7.8. Test 2 — `-proc:only`: sinh source nhưng không biên dịch class thường

**Linux/macOS:**

```bash
javac --release 17 \
  -cp build/proc \
  --processor-path build/proc \
  -processor demo.GenProcessor \
  -proc:only \
  -Ademo.prefix=Only \
  -s build/onlygen -d build/only \
  app/demo/Greeter.java
```

**Windows PowerShell:**

```powershell
javac --release 17 -cp build/proc --processor-path build/proc -processor demo.GenProcessor -proc:only '-Ademo.prefix=Only' -s build/onlygen -d build/only app/demo/Greeter.java
```

**Quan sát trong fixture này:**

| Đường dẫn | Kết quả |
| --- | --- |
| `build/onlygen/demo/GreeterGenerated.java` | **Có**: processor vẫn sinh source. |
| `build/only/demo/GreeterGenerated.class` | **Không**: javac không thực hiện bước compile class sau processing. |

Điều này kiểm chứng sự khác nhau giữa **processor tạo source file** và **compiler chuyển source thành class**. Lệnh `--processor-path` là alias tương đương `-processorpath`, không phải một cơ chế khác.

Nếu chỉ muốn kiểm tra quy tắc annotation hoặc xuất mã sinh mà không build class cuối, `-proc:only` là chế độ phù hợp. Không dùng nó rồi kỳ vọng `java -cp build/only demo.Main` hoạt động khi class chưa được biên dịch.

### 7.9. Test 3 — `-proc:none`: compile nguồn gốc, không sinh class phụ

**Linux/macOS:**

```bash
javac --release 17 -cp build/proc -proc:none \
  -d build/none app/demo/Greeter.java
```

**Windows PowerShell:**

```powershell
javac --release 17 -cp build/proc -proc:none -d build/none app/demo/Greeter.java
```

**Quan sát:**

| Đường dẫn | Kết quả |
| --- | --- |
| `build/none/demo/Greeter.class` | **Có**: mã nguồn gốc được biên dịch. |
| `build/none/demo/GreeterGenerated.class` | **Không**: processor không chạy. |

Chỉ biên dịch `Greeter.java` ở đây. Nếu đưa `Main.java` vào cùng lệnh `-proc:none`, nó sẽ tham chiếu `GreeterGenerated` chưa được sinh, nên compilation có thể thất bại do thiếu symbol. Đây là hậu quả bình thường của việc tắt processor, **không phải `-proc:none` làm hỏng annotation type**.

### 7.10. Test 4 — `-A` sai: processor phát ERROR và build fail

**Linux/macOS:**

```bash
mkdir -p build/bad
javac --release 17 -cp build/proc \
  -processorpath build/proc \
  -processor demo.GenProcessor \
  -Ademo.prefix=123 \
  -d build/bad app/demo/Greeter.java
```

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force build/bad | Out-Null
javac --release 17 -cp build/proc -processorpath build/proc -processor demo.GenProcessor '-Ademo.prefix=123' -d build/bad app/demo/Greeter.java
$LASTEXITCODE
```

**Kết quả mong đợi:** javac exit code khác 0, có diagnostic:

```text
error: demo.prefix must contain only ASCII letters
```

Fixture trên OpenJDK 24 báo `1 error`, exit code `1`. Dòng/đường dẫn in trong stderr sẽ khác tùy nơi đặt project và phiên bản compiler; test tốt nên kiểm tra có lỗi và build thất bại, không so khớp nguyên văn toàn bộ đường dẫn.

**Suy luận đúng:** compiler **đã chạy** processor và **đã truyền** `-A` thành công; lỗi đến từ điều kiện nghiệp vụ trong processor, không phải `javac` tự hiểu rằng `123` là sai.

## 8. `-proc:full` và discovery bằng `META-INF/services`

Lệnh trên chọn class processor bằng `-processor` nên không yêu cầu service registration. Nếu muốn một thư viện processor được **khám phá tự động qua ServiceLoader**, package resource:

```text
META-INF/services/javax.annotation.processing.Processor
```

Nội dung:

```text
demo.GenProcessor
```

Đặt resource này vào JAR hoặc thư mục nằm trên **processor path**, cùng với bytecode implementation. Khi đó có thể chạy kiểu sau (đoạn minh họa giả định registration đã được tạo và processor/dependencies thực sự nhìn thấy được):

```bash
javac --release 17 -cp build/proc \
  --processor-path build/proc \
  -proc:full \
  -Ademo.prefix=Hola \
  -s build/gen -d build/full \
  app/demo/Greeter.java app/demo/Main.java
```

`-proc:full` yêu cầu processing và compilation. `--processor-path` chỉ định nơi khám phá, `META-INF/services` cung cấp class name cho discovery. Nếu không có resource đăng ký và không có `-processor`, việc processor class nằm trong folder **không đủ** để javac biết nó là processor cần chạy.

Nếu dùng processor module JPMS, service có thể được khai báo trong `module-info.java` và đường tìm qua `--processor-module-path`. Không lẫn với application classpath/module path.

**Lưu ý về việc bật processor:** riêng việc đưa JAR vào classpath của ứng dụng **không đủ** dưới chính sách JDK 23+ nếu không có một option bật/cấu hình annotation processing. Khi có `--processor-path`, `-processor`, `-proc:full` hoặc `-proc:only`, javac biết ý định processing rõ ràng.

## 9. Kết nối với JavaCompiler API thay vì gọi lệnh ngoài

Trong ứng dụng Java gọi `javax.tools.JavaCompiler` trực tiếp, các compiler options cũng có thể được đưa vào `JavaCompiler.getTask(...)`:

```java
List<String> options = List.of(
        "--release", "17",
        "--processor-path", "build/proc",
        "-processor", "demo.GenProcessor",
        "-Ademo.prefix=Hola",
        "-s", "build/gen",
        "-d", "build/full"
);

JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, diagnostics, options,
        null, compilationUnits);

boolean ok = Boolean.TRUE.equals(task.call());
```

Đây là **đoạn minh họa**, không độc lập; `compiler`, `manager`, `diagnostics` và `compilationUnits` phải được khởi tạo qua Compiler API. Một số chương trình lựa chọn cấu hình processor trực tiếp qua `task.setProcessors(...)` thay vì `-processor`, nhưng không nên tùy tiện trộn cả hai cơ chế trong cùng task nếu không hiểu ownership.

Trong Java code, truyền option `"-Ademo.prefix=Hola"` như một phần tử String; không cần thêm dấu nháy kiểu PowerShell. Đừng nối tất cả thành một String có dấu cách rồi đưa như **một** phần tử `List`: Compiler API nhận **danh sách các token option**.

Nếu ứng dụng dùng `StandardJavaFileManager` để thiết lập classpath và output locations, tránh đặt options xung đột cho cùng một location. Hãy coi lựa chọn processor và path là một phần cấu hình build có thể truy vết.

## 10. Khác biệt cần ghi nhớ khi vận hành thực tế

### 10.1. `-processor` khác với `-processorpath`

- `-processor demo.GenProcessor`: **tên implementation** được chạy.
- `-processorpath build/proc`: **nơi javac tìm implementation**.
- `-cp build/proc`: **nơi mã ứng dụng nhìn thấy annotation API**.

Viết một tên class mà không có bytecode tương ứng trên path phù hợp sẽ thất bại. Ngược lại, bytecode có trên path nhưng không được chọn/khám phá đúng cách cũng không tự tạo generated source.

### 10.2. `-A` khác với `-D`, `-J` và environment variables

`-Akey=value` dành riêng cho **annotation processors** trong `ProcessingEnvironment.getOptions()`.

`-J-Dprop=value` là cấu hình JVM thực thi javac, có semantics khác, **không tự biến thành `-A`**. Environment variables cũng không được JSR 269 đưa vào `getOptions()` theo mặc định.

Nếu processor cần tùy chọn về package, prefix, output strategy hay validation mode, xác định khóa `-A` công khai và document nó. Tránh tự đọc JVM system properties hoặc env vars cho settings quan trọng khi mục tiêu là build reproducible.

### 10.3. Option không khai báo hỗ trợ

Nếu truyền `-Ademo.praefix=Hola` nhưng processor chỉ `@SupportedOptions("demo.prefix")`, javac có thể cảnh báo option chưa được processor nào nhận diện. Đây là một **đầu mối chẩn đoán**, không phải lỗi syntax của Java source.

Processor nên kiểm tra giá trị bắt buộc và cung cấp error message hữu ích. Khi áp dụng `-Werror`, các warning cũng có thể khiến build thất bại; cần quyết định chính sách warning có chủ đích.

### 10.4. `-Akey`, `-Akey=` và key không có

`processingEnv.getOptions()` trả map:

- Key **không được truyền**: `containsKey(key) == false`.
- `-Akey` **không có giá trị**: theo `ProcessingEnvironment`, map có key với **value `null`**.
- `-Akey=value`: map có key với value tương ứng.

Đừng dùng `getOrDefault(key, default)` rồi giả định nó trả default khi key **tồn tại với value null**. Nếu muốn hỗ trợ flag không có value, dùng `containsKey`; nếu muốn value bắt buộc, kiểm tra `value == null || value.isBlank()` và báo diagnostic.

Processor demo dùng `getOrDefault("demo.prefix", "Hi")` vì muốn default khi key **không xuất hiện**, còn value null sẽ bị validation từ chối; đây là hành vi có chủ đích.

### 10.5. Không chuyển generated source thành class

Có thể là do `-proc:only`; hoặc processor không chạy; hoặc processor sinh source sai; hoặc compilation thất bại sau processing. Để chẩn đoán:

1. Kiểm tra `-processor` hoặc `META-INF/services` và processor path.
2. Kiểm tra có đang dùng `-proc:none` / `-proc:only` hay không.
3. Kiểm tra `-s` và `-d`; đó là **hai thư mục output khác nhau**.
4. Kiểm tra diagnostics và return code của javac.
5. Có thể bật `-XprintProcessorInfo` và `-XprintRounds` để xem processors/rounds trên javac đang dùng.

Không dùng “file `.java` được tạo” làm bằng chứng **cả compilation đã thành công**; output có thể được tạo trước khi lỗi khác làm compile fail.

### 10.6. Processor là code chạy trong build

Một processor là Java class được javac load và thực thi, không phải annotation metadata vô hại. Nó có thể dùng tài nguyên theo quyền của quá trình build. Trên CI cần pin dependency versions, kiểm soát processor path, tránh processor không tin cậy và cân nhắc isolation phù hợp. `-proc:none` giúp tắt processor, nhưng nếu build cần generated classes thì phải chuẩn bị bước build thay thế hoặc bật đúng processor.

## 11. Bảng chọn cấu hình theo mục tiêu

| Mục tiêu | Cấu hình chính | Lưu ý |
| --- | --- | --- |
| Muốn chạy đúng một processor | `-processor p.MyProcessor` và path phù hợp | Không cần service registration. |
| Muốn javac tìm processor từ một JAR | `--processor-path processor.jar` và service registration | Trên JDK 23+ vẫn phải có cấu hình/bật processing tường minh. |
| Muốn dùng module processor | `--processor-module-path modules` | JPMS provider registration khác classpath SPI. |
| Muốn chỉ kiểm tra/generate source | `-proc:only` cùng processor selection/discovery | Không thực hiện bước biên dịch class thông thường. |
| Muốn compile không chạy processor | `-proc:none` | Nguồn phụ thuộc generated class sẽ cần artifact có sẵn. |
| Muốn xử lý và compile trọn vẹn | `-proc:full` hoặc cấu hình processor tường minh theo javac hiện hành | Khác với tự động discovery ngầm của JDK trước 23. |
| Muốn truyền parameter cho processor | `-Akey=value`, `@SupportedOptions` và `getOptions()` | Processor phải tự validate value. |
| Muốn đổi output generated Java | `-s directory` | Khác `-d` cho class files. |
| Muốn target Java 17 | `--release 17` | Kiểm tra processor hỗ trợ source version tương ứng. |

## 12. Checklist QA khi thêm annotation processor vào dự án

1. **Processor artifact:** implementation đã được biên dịch, load được, có dependencies, thuộc đúng namespace `javax.annotation.processing`.
2. **Annotation API:** source ứng dụng import được annotation trên classpath/module path của mình.
3. **Registration:** nếu dùng `-processor` thì tên class đúng; nếu dùng discovery thì service file hoặc JPMS provider đúng.
4. **Activation:** trên JDK 23+ đã chọn processor path, `-processor` hoặc `-proc:full`/`only` thích hợp; không chỉ dựa vào classpath ngầm.
5. **Mode:** không vô tình dùng `-proc:none` hay `-proc:only` khi cần compiled generated classes.
6. **Custom options:** mọi `-A` có key hợp lệ, được processor công bố hỗ trợ, được validate, có default/required behavior rõ ràng.
7. **Filesystem:** `-s` và `-d` trỏ đến vùng build được quyền ghi và có cơ chế dọn generated files cũ.
8. **Target:** `--release` tương ứng với API/cú pháp mà processor sinh ra; supported source version phù hợp.
9. **Diagnostics:** xem ERROR/WARNING và exit code, không chỉ quan sát log; negative case phải fail như yêu cầu.
10. **Repeatability:** chạy build trong workspace sạch, pin dependencies, kiểm tra file generated và output thực sự.

## 13. Câu hỏi tự kiểm tra

**1. Có `-processorpath build/proc` nhưng processor thiếu service registration và không chỉ định `-processor`, javac có biết chạy class nào không?**  
Không thể mặc định như vậy. Path chỉ cung cấp nơi tìm; với discovery, cần đăng ký implementation đúng dạng. Có thể chỉ định `-processor demo.GenProcessor` để bỏ qua discovery.

**2. `-proc:none` có xóa annotation trong source không?**  
Không. Nó chỉ tắt annotation processing; trình biên dịch vẫn có thể biên dịch source chứa annotation type hợp lệ.

**3. `-proc:only` có luôn cho ra `.class` không?**  
Không có bước biên dịch class thông thường sau processing; processor có thể tự tạo file class qua Filer, nhưng với ví dụ chỉ sinh source, không tạo `GreeterGenerated.class`.

**4. Có phải truyền `-proc:full` cùng `-processor` để bật processor trên JDK 23+?**  
Không bắt buộc: `-processor` đã là cấu hình processing tường minh; `-proc:full` là lựa chọn nêu rõ chế độ processing + compilation.

**5. `-Ademo.prefix=Hola` do javac hiểu như option Java source hay do processor hiểu?**  
Javac truyền key/value vào `ProcessingEnvironment.getOptions()`; processor mới quyết định `Hola` có hợp lệ hay không.

**6. Vì sao nên dùng `@SupportedOptions("demo.prefix")`?**  
Để công bố option mà processor hỗ trợ; giúp công cụ chẩn đoán những options không được công nhận.

**7. Trên Windows, nhiều processor JAR trong `-processorpath` được phân tách ra sao?**  
Bằng `;`, nên quote toàn bộ path string trong PowerShell. Linux/macOS dùng `:`.

**8. Nếu `-Aflag` không có dấu bằng, `getOptions().get("flag")` trả gì?**  
`null` theo `ProcessingEnvironment`; muốn phân biệt key vắng mặt, dùng `containsKey`.

**9. `-cp` và `-processorpath` cùng dùng `build/proc` trong demo có nghĩa hai cờ tương đương không?**  
Không. `-cp` cho application source biết annotation type; processor path giúp javac load implementation processor.

**10. Processor báo ERROR nhưng `process(...)` trả `true` thì build vẫn thành công?**  
Không. `true` chỉ claim annotation types; `Messager.ERROR` khiến compilation thất bại.

## Tài liệu chính thức đang được duy trì

- [Oracle Java SE 26 — `javac` command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): cú pháp hiện hành của `-processor`, `--processor-path`/`-processorpath`, `-proc`, `-A`, `-s`, `-d` và `--release`.
- [Oracle Java SE 26 — `ProcessingEnvironment`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html): `getOptions()`, trường hợp value `null`, `Filer`, `Messager`.
- [Oracle Java SE 26 — `Processor`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/Processor.html) và [`AbstractProcessor`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): khai báo options và hợp đồng xử lý.
- [Oracle Java SE 26 — `SupportedOptions`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/SupportedOptions.html): metadata các tên processor-specific options.
- [Oracle JDK 23 Release Notes](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html): thay đổi chính sách annotation processing mặc định từ JDK 23.
- [Inside Java/OpenJDK — JDK 23 annotation processing policy](https://inside.java/2024/06/18/quality-heads-up/): ý nghĩa `-proc:full` và backport tương thích trên nhánh JDK bảo trì.

**Kết luận:** `-processor` chọn **ai chạy**, `-processorpath`/`--processor-path` cho biết **tìm ở đâu**, `-proc` điều khiển **có processing và có compilation sau processing không**, còn `-A` cung cấp **dữ liệu cho processor**. Hiểu rõ bốn vai trò, cùng yêu cầu bật xử lý tường minh từ JDK 23, sẽ giúp hệ thống code generation và compile-time validation ổn định, dễ debug và an toàn hơn.
