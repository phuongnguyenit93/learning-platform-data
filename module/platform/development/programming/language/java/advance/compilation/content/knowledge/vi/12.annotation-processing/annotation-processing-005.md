# Chọn processor bằng -processor và cấu hình đường tìm processor trong javac

Annotation processing trong Java là cơ chế **xử lý annotation tại thời điểm biên dịch** theo API `javax.annotation.processing` (JSR 269). Processor có thể kiểm tra khai báo, phát diagnostic, sinh mã nguồn hoặc resource. Điều đáng chú ý là **có annotation trong source không có nghĩa một processor tương ứng tự chạy**. Trình biên dịch `javac` cần được cấu hình để **tìm được implementation của processor**, **chọn processor cần dùng** và **bật quá trình xử lý** phù hợp với JDK.

Bài học tập trung vào hai quyết định thường bị lẫn: **`-processor` chọn *processor nào***, trong khi **`-processorpath` / `--processor-path` hoặc `--processor-module-path` xác định *tìm và nạp processor ở đâu***. Ta sẽ thiết lập một ví dụ Java 17+ có processor tự sinh class, chạy đầy đủ từ đầu, rồi đối chiếu service discovery, classpath, module path, nhiều processor và các lỗi thường gặp. Special Note của module không có yêu cầu bổ sung.

## 1. Bản đồ cơ chế: source, processor và output là ba vai trò khác nhau

~~~text
Ứng dụng: @GenerateInfo trên Model.java
           │
           │ API annotation có trên compile classpath
           ▼
        javac
           │
           ├── Cấu hình -processor proc.InfoProcessor
           │         → chọn class processor theo tên
           │
           ├── Cấu hình -processorpath ...
           │         → tải implementation và dependencies
           │
           └── Annotation processing rounds
                        │
                        ├── Processor đọc mô hình Element/Type
                        ├── Sinh GeneratedInfo.java qua Filer
                        └── Nguồn sinh mới được đưa vào round tiếp
                                      │
                                      ▼
                         Compile nguồn ban đầu + nguồn sinh
                                      │
                           App.class, GeneratedInfo.class
~~~

Ba loại đường dẫn phải phân biệt:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Compile classpath** `-cp`/`--class-path` | Cho source Java đang biên dịch truy cập annotation API và các dependency ứng dụng | `build/annotations` |
| **Processor path** `-processorpath`/`--processor-path` | Cho `javac` tìm/nạp processor **và các thư viện processor cần để thực thi** | `build/processor:build/annotations` |
| **Source output** `-s` | Nơi Filer ghi source `.java` do processor tạo | `build/generated` |
| **Class output** `-d` | Nơi compiler ghi `.class` của ứng dụng và nguồn sinh | `build/classes` |
| **Processor module path** `--processor-module-path` | Nơi tìm *modular processors*, thay vì loader dựa vào processor classpath | `mods/processors` |
| **Module path** `--module-path` | Nơi tìm module dependency của **source đang biên dịch** | `mods/libraries` |

**Processor là chương trình được `javac` thực thi trong môi trường build**. Nó không phải một class được JVM ứng dụng tự động gọi ở runtime chỉ vì có annotation. Các annotation có retention `SOURCE` có thể biến mất khỏi class file mà vẫn đã được xử lý lúc biên dịch.

Một nguyên tắc quan trọng: compile classpath và processor path **không nên vô tình đồng nhất**. Nếu processor ở trên processor path nhưng annotation API không ở compile classpath, mã có `@GenerateInfo` vẫn có thể báo `cannot find symbol`. Ngược lại, nếu source có thể import annotation nhưng processor implementation không tìm được, việc sinh code sẽ không diễn ra.

## 2. Cú pháp và ý nghĩa những option cần biết

| Option của `javac` | Ý nghĩa |
| --- | --- |
| `-processor p.First,p.Second` | Chỉ định các processor class cụ thể sẽ dùng, **bỏ qua bước tự tìm provider mặc định** |
| `-processorpath path` | Đặt đường tìm processor theo classpath truyền thống |
| `--processor-path path` | Cách viết dài tương đương `-processorpath` |
| `--processor-module-path path` | Đường tìm processor đóng gói thành named module |
| `-proc:none` | Tắt annotation processing, tiếp tục compile source thông thường |
| `-proc:only` | Chạy annotation processing nhưng **không tiếp tục biên dịch thông thường thành class files** |
| `-proc:full` | Yêu cầu cả annotation processing và compile (trên JDK có hỗ trợ option này) |
| `-s directory` | Đặt thư mục đích cho source được sinh |
| `-d directory` | Đặt thư mục đích cho class files |
| `-Akey=value` | Gửi option riêng cho processor, có thể truy cập qua `ProcessingEnvironment.getOptions()` |
| `-XprintRounds` | In thông tin các round của annotation processing |
| `-XprintProcessorInfo` | In processor nào được yêu cầu xử lý annotation nào |

Danh sách sau `-processor` dùng dấu **phẩy**, không dùng dấu cách để phân tách giữa các tên processor. Mỗi mục là **tên class đầy đủ** (fully qualified name) có constructor public không tham số hợp lệ hoặc constructor public mặc định do Java cung cấp, implement `javax.annotation.processing.Processor`. Class phải có mặt trên đường tìm thích hợp để `javac` nạp được.

**Phân biệt `-processor` với `-processorpath`:**

~~~bash
# Chọn class processor cụ thể. Bản thân -processor không phải đường dẫn.
javac -processor proc.InfoProcessor ...

# Chỉ cho compiler biết nơi tìm processor. Có thể kết hợp với discovery.
javac -processorpath build/processor ...

# Dùng cả hai: rõ ràng về processor được chạy và vị trí nạp nó.
javac -processorpath build/processor -processor proc.InfoProcessor ...
~~~

Dấu `...` trong ba dòng trên biểu diễn các option/source khác cần điền, **không phải cú pháp chạy độc lập**. Ở ví dụ hoàn chỉnh phía dưới sẽ có từng lệnh có thể thực thi.

## 3. Thay đổi quan trọng từ JDK 23: không dựa vào implicit processor discovery

Trước JDK 23, nhiều build tình cờ chạy processor vì JAR chứa service provider nằm trên **class path**. Từ **JDK 23**, `javac` **không kích hoạt annotation processing chỉ vì tình cờ phát hiện processor trên classpath**. Cần cấu hình rõ ràng, chẳng hạn:

- Chỉ định class bằng `-processor`.
- Chỉ định đường tìm processor bằng `-processorpath` hoặc `--processor-module-path`, khi artifact cung cấp thông tin discovery phù hợp.
- Yêu cầu processing bằng `-proc:only` hoặc `-proc:full`, trên JDK hỗ trợ.

Điều này không có nghĩa phải **luôn đặt cả ba option**. Một lệnh `-processor proc.InfoProcessor -processorpath ...` đã minh bạch cả class và vị trí nạp. Một processor JAR có service descriptor có thể được tìm qua `-processorpath ...` khi processing được cấu hình hợp lệ.

JDK 21/22 từng hiển thị cảnh báo/note về implicit processing trong một số lệnh; JDK 23 đổi mặc định để giảm các build tự ý thực thi processor từ classpath. Vì processor có thể chạy mã trong quá trình build, việc liệt kê rõ processor và processor dependencies còn giúp **giảm bề mặt tấn công supply-chain**, cải thiện tính tái lập.

**Kiểm tra đúng compiler thực tế:**

~~~bash
javac -version
javac -help
javac -X
~~~

`-proc:full` không có ở mọi bản vá JDK 17 cũ; phần ví dụ Java 17+ bên dưới dùng **`-processor` và `-processorpath`** nên không phụ thuộc `-proc:full` để minh họa. Không nên nhận định mọi JDK 17.x đều hỗ trợ cùng một tập option mới.

## 4. Khi nào dùng -processor, khi nào để discovery?

**Dùng `-processor` nếu:**

- Cần chọn **đúng** một hoặc vài processor được kiểm soát, dù trong processor path có nhiều provider.
- Muốn build tái lập: không để thêm một JAR ngẫu nhiên làm xuất hiện processor mới.
- Muốn cô lập một processor khi debug, kiểm tra phiên bản hoặc xung đột.
- Triển khai pipeline bảo mật cần danh sách processor được phê duyệt rõ.

**Dùng service discovery nếu:**

- Processor JAR đã đóng gói đúng service provider descriptor.
- Build tool/plugin quản lý danh sách dependency của annotation processor.
- Muốn processor mới được nhận diện theo cơ chế SPI mà không phải sửa `-processor` cho từng class.

Cả hai cách vẫn phải bảo đảm processor có thể **tải được** và annotation phù hợp thực sự xuất hiện trong các root được xử lý. Chỉ định class processor không tự tạo annotation trong source, cũng không khiến mọi method `process` nhất thiết được gọi theo một lịch cố định cho mọi tệp.

**Ví dụ danh sách nhiều processor:**

~~~bash
javac -processor proc.InfoProcessor,proc.CheckerProcessor \
  -processorpath build/processors:build/annotations \
  -cp build/annotations \
  -d build/classes src/app/demo/Model.java
~~~

Đây là **mẫu cú pháp**, chỉ chạy được nếu `proc.CheckerProcessor` đã được biên dịch và mọi đường dẫn tồn tại. Danh sách `-processor` không phải danh sách annotation type mà processor nhận; processor tự công bố các annotation type hỗ trợ qua `@SupportedAnnotationTypes` hoặc API tương ứng.

### Chọn class không đồng nghĩa luôn chạy process()

Có hai pha logic:

1. `javac` **tạo và khởi tạo** processor candidate từ cấu hình.
2. Trong các round, compiler kiểm tra annotation types hiện diện và những type processor hỗ trợ, cùng việc annotation đã được processor khác “claim” chưa, rồi mới quyết định gọi.

Vì vậy, thêm một class vào `-processor` không có nghĩa `process()` được gọi ở mọi round nếu không có annotation phù hợp, trừ những tình huống theo contract của API (ví dụ processor hỗ trợ `"*"`). Để kiểm chứng bằng evidence, dùng `-XprintRounds` và `-XprintProcessorInfo`, không đoán từ việc process được liệt kê.

## 5. Ví dụ hoàn chỉnh Java 17+: processor sinh GeneratedInfo.java

Ta viết một annotation API, một processor, hai file ứng dụng. Processor sẽ sinh class `demo.GeneratedInfo` từ annotation `@GenerateInfo`, và `App` dùng class đó ngay trong **cùng một lời gọi `javac`**. Đây là phép thử mạnh: nếu processor không chạy, ứng dụng không thể biên dịch vì `GeneratedInfo` chưa tồn tại.

### 5.1. Cấu trúc thư mục

~~~text
processor-demo/
├── src/
│   ├── api/
│   │   └── demo/GenerateInfo.java
│   ├── processor/
│   │   └── proc/InfoProcessor.java
│   └── app/
│       └── demo/
│           ├── Model.java
│           └── App.java
└── build/                    # Tạo trong các lệnh phía dưới
    ├── annotations/          # Annotation API đã compile
    ├── processor/            # Processor implementation đã compile
    ├── generated/            # Generated source .java
    └── classes/              # App + generated classes
~~~

Tất cả lệnh Bash giả định bạn đứng tại thư mục `processor-demo`, có JDK 17+ cung cấp cả `javac`, `java` và `jar`. Ví dụ dùng dấu `:` làm phân cách path (Linux/macOS); Windows dùng dấu `;` và cú pháp tạo thư mục tương ứng.

### 5.2. Tệp annotation: src/api/demo/GenerateInfo.java

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateInfo {
}
~~~

`@Target(TYPE)` giới hạn annotation dùng trên các khai báo kiểu như class. `@Retention(SOURCE)` phù hợp ví dụ: cần annotation trong lúc compile, không cần đưa vào metadata runtime. Annotation này không tự sinh ra class; processor mới thực hiện việc đó.

### 5.3. Processor: src/processor/proc/InfoProcessor.java

~~~java
package proc;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.GenerateInfo")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class InfoProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver() || generated || annotations.isEmpty()) {
            return false;
        }

        try {
            JavaFileObject file = processingEnv.getFiler()
                    .createSourceFile("demo.GeneratedInfo");

            try (Writer out = file.openWriter()) {
                out.write("package demo;\n");
                out.write("public final class GeneratedInfo {\n");
                out.write("    private GeneratedInfo() {}\n");
                out.write("    public static String value() {\n");
                out.write("        return \"generated: ok\";\n");
                out.write("    }\n");
                out.write("}\n");
            }

            generated = true;
        } catch (IOException ex) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR, "Cannot generate source: " + ex);
        }
        return true;
    }
}
~~~

**Giải thích:**

- `AbstractProcessor` cung cấp implementation thuận tiện của `Processor`.
- `@SupportedAnnotationTypes("demo.GenerateInfo")` thông báo processor quan tâm đến annotation đầy đủ tên package; không viết `"GenerateInfo"` thiếu package.
- `@SupportedSourceVersion(RELEASE_17)` khai báo mức source mà processor hỗ trợ. Không phải cơ chế để biến annotation processor thành thư viện runtime Java 17 một cách tự động; class file của processor còn phụ thuộc JDK và option dùng để biên dịch nó.
- `process(...)` nhận những annotation type được framework giao cho round hiện tại và một `RoundEnvironment`; `annotations.isEmpty()` là hàng rào để không tạo source khi không có annotation phù hợp.
- `generated` chặn việc tạo trùng một file ở các round kế tiếp. Processor được tạo **một instance cho mỗi lần chạy**, không phải một instance mới trong mọi round.
- `Filer.createSourceFile` tạo Java source; compiler có thể đưa nguồn mới vào round tiếp rồi biên dịch cùng nguồn ban đầu.
- `return true` cho biết processor **claim** các annotation được giao; các processor được xét sau sẽ không tiếp tục được giao cùng annotation type trong round đó.
- Khi file không tạo được, `Messager` phát diagnostic ở build; exception không được lặng lẽ bỏ qua.

Mã ở đây dùng tên output cố định `demo.GeneratedInfo` để dễ quan sát. Trong processor thực tế, hãy xây tên theo từng annotated element, kiểm tra xung đột và không tạo cùng một path ở nhiều round. Nếu hai processor cùng cố ghi file đó, `FilerException`/diagnostic có thể xuất hiện.

### 5.4. Ứng dụng: Model.java và App.java

**`src/app/demo/Model.java`**

~~~java
package demo;

@GenerateInfo
public final class Model {
}
~~~

**`src/app/demo/App.java`**

~~~java
package demo;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(GeneratedInfo.value());
    }
}
~~~

`GeneratedInfo` chưa có tệp Java ban đầu và chỉ xuất hiện khi processing tạo source. `App` tham chiếu trực tiếp class được sinh để kiểm tra rằng cả **annotation discovery**, **processor loading**, **rounds** và **compilation** đều hoàn tất.

### 5.5. Biên dịch annotation API và processor trước

~~~bash
mkdir -p build/annotations build/processor build/generated build/classes

javac --release 17 \
  -d build/annotations \
  src/api/demo/GenerateInfo.java

javac --release 17 \
  -cp build/annotations \
  -d build/processor \
  src/processor/proc/InfoProcessor.java
~~~

Sau hai bước này có:

~~~text
build/annotations/demo/GenerateInfo.class
build/processor/proc/InfoProcessor.class
~~~

Lý do **tách pha bootstrap**: `javac` cần **load một processor đã biên dịch** trước khi processor xử lý app source. Không thể chỉ đưa `InfoProcessor.java` chưa biên dịch vào `-processorpath` và kỳ vọng compiler tự compile processor từ mã nguồn cùng lượt.

### 5.6. Gọi javac với cả -processor và -processorpath

~~~bash
javac --release 17 \
  -cp build/annotations \
  -processorpath build/processor:build/annotations \
  -processor proc.InfoProcessor \
  -s build/generated \
  -d build/classes \
  src/app/demo/Model.java src/app/demo/App.java
~~~

Ở lệnh này:

- `-cp build/annotations` cho source `Model` biết `demo.GenerateInfo`.
- `-processorpath build/processor:build/annotations` cho loader biết implementation `proc.InfoProcessor` và annotation API/dependency mà processor có thể cần. Demo processor dùng tên annotation ở dạng chuỗi, nhưng thiết lập path rõ ràng vẫn hữu ích cho ví dụ thực tế.
- `-processor proc.InfoProcessor` chỉ định **đúng** processor cần chạy; không cần service descriptor cho mode này.
- `-s build/generated` lưu nguồn sinh vào `build/generated/demo/GeneratedInfo.java`.
- `-d build/classes` ghi `App.class`, `Model.class` và `GeneratedInfo.class` vào package tương ứng.

Compiler tạo code mới trong quá trình annotation processing và biên dịch chúng. Không cần gọi `javac` lần thứ hai để compile `build/generated/demo/GeneratedInfo.java` trong ví dụ này.

Chạy chương trình:

~~~bash
java -cp build/classes demo.App
~~~

**Stdout chính xác từ App:**

~~~text
generated: ok
~~~

Không cần đặt processor implementation trên runtime classpath khi chỉ chạy `demo.App`. Processor phục vụ quá trình build; generated class mới là thứ ứng dụng dùng ở runtime. Annotation `@GenerateInfo` có `RetentionPolicy.SOURCE` nên cũng không phải dependency runtime cho ví dụ này.

### 5.7. Bằng chứng processor đã tạo code

Đầu ra cần kiểm tra:

~~~text
build/generated/demo/GeneratedInfo.java
build/classes/demo/GeneratedInfo.class
build/classes/demo/Model.class
build/classes/demo/App.class
~~~

Nếu biên dịch lỗi vì `GeneratedInfo` chưa tồn tại, kiểm tra ngay phần chọn processor, đường tìm processor, service registration và diagnostics. Đừng sửa vội `App.java` để che lấp việc processor chưa chạy.

## 6. Thử phương án service discovery: không đặt -processor

`-processor` không bắt buộc khi processor được **công bố như một service provider** theo cơ chế SPI classpath. File service phải nằm đúng đường dẫn bên trong processor output directory hoặc JAR:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

**Nội dung duy nhất của service file trong demo:**

~~~text
proc.InfoProcessor
~~~

Từ thư mục `processor-demo`, tạo metadata service:

~~~bash
mkdir -p build/processor/META-INF/services
printf '%s\n' 'proc.InfoProcessor' \
  > build/processor/META-INF/services/javax.annotation.processing.Processor
~~~

Sau đó để riêng output của lần build thử này, xóa/chuyển output **chỉ trong thư mục demo của bạn** rồi tạo lại:

~~~bash
rm -rf build/classes build/generated
mkdir -p build/classes build/generated

javac --release 17 \
  -cp build/annotations \
  -processorpath build/processor:build/annotations \
  -s build/generated \
  -d build/classes \
  src/app/demo/Model.java src/app/demo/App.java

java -cp build/classes demo.App
~~~

Lệnh chạy cuối tiếp tục in:

~~~text
generated: ok
~~~

Ở lượt compile này, **không có `-processor`**. `javac` tìm service file trên processor path, biết processor class `proc.InfoProcessor` và gọi theo annotation phù hợp. Đây là **discovery**. Nó khác với lựa chọn tường minh, bởi processor artifact có thể quảng cáo một hoặc nhiều provider qua service metadata.

Lưu ý: `rm -rf` là lệnh xóa đệ quy. Ví dụ chỉ dùng khi bạn chắc chắn đang đứng tại thư mục `processor-demo` và các thư mục `build/classes`, `build/generated` là **output riêng của demo**; tuyệt đối không sao chép lệnh xóa sang thư mục dự án khác nếu không kiểm tra. Không xóa `build/processor` vì đang chứa implementation và service file.

### Khi nào service file không được nhận diện?

- Đặt sai tên file, ví dụ `META-INF/service` (thiếu `s`) hoặc tên service không phải `javax.annotation.processing.Processor`.
- Đặt file cạnh JAR thay vì **bên trong JAR** hoặc root một directory entry của processor path.
- Viết tên class không đầy đủ; class không `public`/không có constructor public không tham số; class không implement `Processor`.
- Processor class/dependency bị thiếu khiến loader ném exception.
- Chỉ khai service metadata nhưng không kích hoạt processing hợp lệ trên JDK 23+.
- Dùng `-proc:none` rồi kỳ vọng processor chạy.

Có thể đóng gói processor implementation và service file trong JAR qua `jar --create --file ...`; cấu trúc entry bên trong JAR phải đúng. Một JAR có cả processor và annotation API có thể được thiết kế riêng, nhưng không nên ép tất cả dependency processor vào compile classpath của app nếu không cần thiết.

## 7. Vì sao -cp khác -processorpath?

Đây là nguồn nhầm lẫn lớn nhất khi cấu hình Lombok, MapStruct, Dagger, AutoService hoặc processor tự viết.

**Trường hợp A:** annotation có trên `-cp`, implementation không có trên `-processorpath`.

~~~text
javac ... -cp build/annotations -processorpath empty_processors \
  -processor proc.InfoProcessor ...
~~~

Lệnh này **không chạy được** nếu `empty_processors` không có processor: compiler thường báo `Annotation processor 'proc.InfoProcessor' not found`. Đây là **mẫu lỗi**, không phải lệnh đầy đủ cần chạy.

**Trường hợp B:** implementation nằm trên processor path, annotation API lại không có trên compile classpath.

Khi compile `Model.java` chứa `@GenerateInfo`, compiler có thể không tìm được `demo.GenerateInfo`. Thêm processor implementation **không tự** làm annotation API thành dependency để source import.

**Trường hợp C:** chỉ cấu hình `-cp` mà mong JDK 23+ tự phát hiện provider.

Từ JDK 23, không nên dựa vào implicit processing này. Chọn processor explicit qua `-processor` hoặc cấu hình processor path/discovery hay `-proc:full` một cách rõ ràng. Với build tools, dùng dependency configuration dành cho processors.

**Trường hợp D:** đặt dependency runtime của processor lên classpath ứng dụng nhưng quên processor path.

Nếu đã chỉ định `-processorpath`, nó là vùng tìm loader của processors; đừng giả định một JAR nằm ở `-cp` sẽ tự có mặt trên processor path. Hãy thêm JAR cần thiết vào đúng nơi processor loader nhìn thấy.

### Một ví dụ thực tế về nhiều JAR phụ thuộc

Trên Linux/macOS:

~~~bash
javac \
  -cp libs/annotations.jar:libs/application-api.jar \
  -processorpath libs/my-processor.jar:libs/processor-helper.jar:libs/annotations.jar \
  -processor com.example.build.MyProcessor \
  -d out \
  src/main/java/com/example/App.java
~~~

Đây là **mẫu áp dụng**, không phải project chạy độc lập: thay tên class/JAR/source bằng artifact thật. Trên Windows đổi dấu `:` trong các danh sách path thành `;`.

Không đưa tất cả JAR của ứng dụng vào processor path mà không có mục đích, vì mỗi dependency processor là mã có thể bị load khi build; cách tốt là giới hạn processor path ở processor và các dependency cần để chính processor thực thi.

## 8. Modular annotation processors: --processor-module-path

Trong Java module system, processor có thể được đóng gói thành **named module** cung cấp service bằng `provides ... with ...`. Khi đó dùng:

~~~text
--processor-module-path path
~~~

thay cho processor classpath truyền thống. Ví dụ descriptor của một **processor module riêng**:

~~~java
module com.example.codegen {
    requires java.compiler;
    provides javax.annotation.processing.Processor
            with com.example.codegen.MyProcessor;
}
~~~

Đây là **minh họa module-info.java**, không phải phần bổ sung trực tiếp vào demo classpath ở mục 5; cần một processor class `com.example.codegen.MyProcessor` thực sự tồn tại, implement `Processor` và được build thành module. `java.compiler` cung cấp các package `javax.annotation.processing`, `javax.lang.model`, `javax.tools`.

Ví dụ template cho project có modular processor đã đóng gói:

~~~bash
javac \
  --processor-module-path mods/processors \
  --module-path mods/application-libraries \
  -d out \
  src/app/module-info.java src/app/com/example/app/Main.java
~~~

Cú pháp ở trên **chỉ là khung cấu hình**: cần điền module, source, dependency thực tế. Compiler tìm providers của service trong các module trên processor module path. Khi dùng module path, chú ý:

- Provider phải được **công bố đúng** qua module service declaration.
- Processor module và dependencies phải load được với module access phù hợp.
- Đừng đồng nhất `--processor-module-path` với `--module-path` dành cho **application modules**.
- Tránh cấu hình đồng thời các cơ chế processor path và processor module path một cách mơ hồ; chọn đúng mô hình package artifact.

Processor có thể chạy trên JDK dùng để build mới hơn so với release của code được sinh. Nhưng source/generated code cuối cùng vẫn phải tuân theo `--release` của ứng dụng. Để hỗ trợ nhiều JDK build, kiểm tra cả **runtime requirement của processor** và **target requirement của mã đầu ra**.

## 9. Nhiều processor trong một compile: annotation claiming và round

Annotation processing thường có **nhiều round**. Mỗi round processor nhận các element có annotation phù hợp; khi một processor sinh nguồn mới bằng `Filer`, compiler có thể xử lý các source đó ở round tiếp theo.

~~~text
Round 1: Model.java có @GenerateInfo
    └── InfoProcessor → sinh GeneratedInfo.java
                    │
                    ▼
Round 2: generated source đi vào input của round tiếp
                    │
                    ▼
Final round: processingOver() == true
                    │
                    ▼
Compilation: App, Model và GeneratedInfo → .class
~~~

Sơ đồ mang tính khái niệm; số lượng round, annotation hiện diện và trình tự gọi có thể khác tùy bộ processor và nguồn sinh. Processor đã được gọi trong một round sẽ còn được framework gọi ở những round tiếp theo theo contract, kể cả round cuối; vì vậy cần xem `roundEnv.processingOver()` và tránh tạo lại file.

### Claiming: true và false nghĩa là gì?

Phương thức `process(Set<? extends TypeElement>, RoundEnvironment)` trả:

- `true`: processor **claim** các annotation type trong tập `annotations` đang được giao; không tiếp tục giao chúng cho các processor xét sau trong round.
- `false`: không claim, có thể cho processor khác cũng xử lý những annotation đó theo cơ chế discovery/matching.

Đừng dùng `return true` để “đảm bảo processor nào đó chạy trước”; thứ tự discovery, claim và tập annotation giao cho processor có cơ chế riêng. Nhiều processor cùng sửa file/source có thể tạo conflict. Nếu processor phụ thuộc source được processor khác tạo, hãy thiết kế theo **rounds và Filer outputs** thay vì tự giả định invocation order.

### Vì sao processor không nên tự compile output?

API `Filer` chịu trách nhiệm tạo source/class/resource theo contract. Khi compiler còn tiếp tục processing và compilation, generated source được đưa vào workflow. Tự gọi `javac` lồng bên trong `process` thường làm phức tạp class loader, dependency, duplicate outputs và chẩn đoán; chỉ làm khi thật sự cần quy trình riêng.

## 10. Đọc log -XprintRounds và -XprintProcessorInfo

Để xem demo hoạt động, chạy lệnh ở mục 5.6 với hai option diagnostic thêm vào:

~~~bash
javac --release 17 \
  -cp build/annotations \
  -processorpath build/processor:build/annotations \
  -processor proc.InfoProcessor \
  -XprintRounds -XprintProcessorInfo \
  -s build/generated -d build/classes \
  src/app/demo/Model.java src/app/demo/App.java
~~~

Trước khi chạy lại từ đầu với processor sinh tên file cố định, hãy đảm bảo `build/generated` và `build/classes` là các output sạch của **demo**; generated files cũ có thể khiến việc tạo lại hoặc compile trở nên khó hiểu. Hai cờ chỉ in thông tin chẩn đoán, không tự bật processor nếu cấu hình chính sai.

Bạn có thể thấy thông tin kiểu:

~~~text
Round 1:
    input files: {...}
    annotations: [...]
    last round: false
Processor proc.InfoProcessor matches [...] and returns true.
...
~~~

Đây là **minh họa format log**, không phải output chính xác cam kết cho mọi JDK. Số round và cách in chi tiết phụ thuộc compiler, annotation và generated sources. Với demo, **bằng chứng đáng tin nhất** vẫn là class được tạo và chạy ra `generated: ok`.

Khi log không có processor mình mong đợi, kiểm tra tuần tự:

1. Có cấu hình `-processor` hoặc discovery/processing flag đúng với JDK không?
2. Tên đầy đủ của processor class có chính xác không?
3. Processor và dependencies có load được từ processor path/module path không?
4. `@SupportedAnnotationTypes` có khớp annotation xuất hiện trong nguồn đang xét không?
5. Có processor khác đã claim annotation trước không?
6. Source có được liệt kê/đọc trong lượt biên dịch hiện tại không, hay chỉ là một dependency cũ?

## 11. -proc:none, -proc:only và -proc:full

Ba chế độ không giống nhau:

| Chế độ | Xử lý annotation | Compile .class thông thường |
| --- | --- | --- |
| `-proc:none` | Không | Có |
| `-proc:only` | Có, khi cấu hình có processor phù hợp | **Không** thực hiện giai đoạn compile class bình thường |
| `-proc:full` | Có, khi được cấu hình/được tìm thấy | Có |

`-proc:only` thích hợp khi bạn muốn chạy bước kiểm tra annotation hoặc **chỉ sinh source** để xem kết quả rồi quyết định build tiếp. Nhưng đừng mong `App.class` được sinh chỉ vì `-d` có mặt. Một pipeline dùng `-proc:only` có thể có generated source mà chưa có bytecode.

Trên các JDK 17 rất cũ, `-proc:full` có thể chưa được backport. Cách chọn processor tường minh như `-processor proc.InfoProcessor` trên `-processorpath` phù hợp cho demo mà không phải dựa vào option mới đó. Trên JDK 23+, xác định processing rõ ràng đặc biệt quan trọng.

### Kiểm tra negative test

Nếu xử lý demo trên **output sạch** bằng `-proc:none`:

~~~bash
javac --release 17 \
  -proc:none \
  -cp build/annotations \
  -d build/classes \
  src/app/demo/Model.java src/app/demo/App.java
~~~

Lệnh sẽ **không có generated class `GeneratedInfo`** vì processor bị tắt. Do `App` đang tham chiếu class đó, trên output sạch compile thất bại với lỗi tìm symbol. Nếu class cũ vẫn nằm trong output/classpath, kết quả có thể khác; đây là lý do phải làm sạch output cho test logic processing. Không khẳng định mọi source có annotation đều sẽ compile thất bại với `-proc:none`: chúng vẫn có thể biên dịch được nếu không phụ thuộc generated code.

## 12. Truyền option riêng bằng -A và kiểm tra cấu hình

Annotation processor đôi khi cần cấu hình riêng như package đích, chế độ strict hoặc tên file. Dùng:

~~~text
-Acodegen.mode=debug
-Acodegen.outputPackage=com.example.generated
~~~

Processor đọc qua:

~~~java
String mode = processingEnv.getOptions().getOrDefault(
        "codegen.mode", "default");
~~~

Đoạn này là **snippet nằm trong processor**, không phải chương trình Java standalone. Một processor nên khai báo option hỗ trợ qua `@SupportedOptions({"codegen.mode", "codegen.outputPackage"})` hoặc `getSupportedOptions()` để compiler nhận biết. Giá trị là text; processor phải tự kiểm tra hợp lệ. `javac` không tự biến `-Acodegen.mode=debug` thành một hành vi cụ thể nếu processor không đọc nó.

Chú ý `-A` có dạng `-Akey[=value]`, không đặt dấu cách giữa `-A` và key. Với giá trị chứa whitespace cần quoting theo shell và cú pháp option. Không nhầm `-A` với application argument truyền tới `main(String[] args)`.

### Processor output phải tái lập

Trong code generation production:

- Tránh phụ thuộc thứ tự phần tử khi API không đảm bảo; nếu cần, sort theo fully qualified name.
- Không ghi thời điểm build hay đường dẫn tuyệt đối vào file generated nếu không có yêu cầu.
- Phát diagnostic rõ ràng khi cấu hình sai; đừng nuốt exception.
- Không đọc file từ đường dẫn tùy ý hoặc truy cập network khi không cần, vì processor chạy trong môi trường build.
- Hạn chế quyền và dependency của processor như với một tool build có khả năng thực thi mã.

## 13. Processor path, module path và Java version

Đường tìm processor được cấu hình cho **môi trường thực thi của compiler**; source đang biên dịch lại có **ngữ cảnh kiểu/API** riêng. Điều đó dẫn đến một số tình huống:

- Processor class compiled cho Java 21 không load được nếu chạy `javac` bằng JDK 17 (có thể `UnsupportedClassVersionError` hoặc thông báo processor load failure), **dù** target source chỉ là `--release 8`.
- Processor chạy bằng JDK 21 nhưng sinh Java source dùng API Java 21, trong khi app compile `--release 17` sẽ bị compiler từ chối. Processor phải sinh mã tương thích target application.
- Với processor module path, provider module `requires java.compiler` và có thể cần `requires`/`opens`/`exports` cho những module processor dependencies; đây là ràng buộc lúc **thực thi processor**, không phải module descriptor của application.
- `--module-path` tìm dependency của ứng dụng có module; `--processor-module-path` tìm processor module; các path không thay thế được nhau.
- `-J-Xmx1g` điều chỉnh JVM chạy trình biên dịch khi dùng launcher `javac`, không phải tham số `-A` và không phải heap size của ứng dụng sau triển khai.

Thực hành: ghi nhận `javac -version`, processor artifact version, target release, cả compile classpath và processor path. Đặc biệt trong CI, build tool có thể chọn một JDK khác với `java` trên shell; không kết luận source target từ tên image Docker hoặc nhãn job đơn thuần.

## 14. Processor trong Maven và Gradle

Các build tool thường cung cấp cấu hình **riêng cho processor dependency** và app compile dependency.

### Maven

Với các phiên bản Maven Compiler Plugin hỗ trợ `annotationProcessorPaths`, ví dụ minh họa trong `pom.xml`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.0</version>
            <configuration>
                <release>17</release>
                <annotationProcessorPaths>
                    <path>
                        <groupId>com.example</groupId>
                        <artifactId>my-processor</artifactId>
                        <version>1.0.0</version>
                    </path>
                </annotationProcessorPaths>
                <annotationProcessors>
                    <annotationProcessor>com.example.ProcessorImpl</annotationProcessor>
                </annotationProcessors>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là **ví dụ cấu hình**, không phải dự án tự chạy: tọa độ Maven và processor class phải thay bằng artifact thực. `annotationProcessorPaths` điều khiển nơi tìm processor, `annotationProcessors` tương ứng việc chọn tên processor; `release` đặt target source/API. Khi project dùng annotation API trong source, hãy khai thêm dependency annotation API trong phần dependencies của project theo nhu cầu.

Plugin version, cách cấu hình processor module path và tương thích Maven/JDK có thể thay đổi; hãy đối chiếu tài liệu của **phiên bản plugin đang dùng**. Không nên sao chép mẫu như một “phiên bản chuẩn duy nhất” cho mọi repository.

### Gradle (Groovy DSL)

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    compileOnly 'com.example:my-annotations:1.0.0'
    annotationProcessor 'com.example:my-processor:1.0.0'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.compilerArgs += [
        '-processor', 'com.example.ProcessorImpl'
    ]
}
~~~

`annotationProcessor` khai dependency mà Gradle đặt trên processor path; `compileOnly` cho source thấy annotation API nhưng không nhất thiết đóng nó vào runtime. Trong project thật, annotation có retention `RUNTIME` hoặc được dùng lúc chạy có thể cần cách khai dependency khác. `options.compilerArgs` là ví dụ khi muốn **chỉ định processor tường minh**; nếu JAR đã cung cấp service discovery và build có processor path đúng, có thể không cần ép danh sách này.

Không tự đặt một processor JAR vào `implementation` rồi kỳ vọng Gradle/JDK23 trở lên chạy codegen. Tách `annotationProcessor` khỏi runtime/application dependencies giúp pipeline rõ ràng và tránh vô tình đóng công cụ build vào distribution.

## 15. Những lỗi thường gặp và hướng giải quyết

| Lỗi/triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `Annotation processor 'x.Y' not found` | Tên class sai, processor chưa compile, processor path không chứa output/JAR | Kiểm tra FQCN, `jar tf`, root path, JVM/JDK của compiler |
| `Bad service configuration file` | Service descriptor sai tên hoặc class provider lỗi | Kiểm tra `META-INF/services/javax.annotation.processing.Processor` và class public |
| `NoClassDefFoundError` khi load processor | Thiếu thư viện của chính processor trên processor path | Thêm processor dependencies vào path, không chỉ `-cp` của app |
| Annotation API không tìm thấy trong source | Thiếu annotation artifact ở compile classpath/module path | Thêm dependency dùng để compile app |
| Annotation được nhận diện nhưng code không sinh | Không chọn processor; `-proc:none`; annotation không match; processor không tạo file | Dùng `-XprintRounds`, kiểm tra `@SupportedAnnotationTypes`, logging/diagnostics |
| `FilerException: Attempt to recreate a file` | Processor ghi cùng output nhiều round hoặc nhiều processor | Guard theo round/element, tên file duy nhất, output sạch |
| Dùng JDK 23+ mà thiếu generated code | Trông chờ implicit processor discovery từ classpath | Dùng processor path/explicit `-processor`/cấu hình build tool |
| `UnsupportedClassVersionError` của processor | Processor được compile bằng Java cao hơn build JDK | Dùng processor hỗ trợ JDK build hoặc nâng JDK build |
| Generated source có API/cú pháp quá mới | Processor không tuân thủ `--release` app | Sửa generator hoặc target, kiểm tra output |
| Source sinh ra nhưng `.class` chưa có | `-proc:only` hoặc compile bị lỗi | Dùng processing + compile khi muốn .class |
| Hai processor “tranh” cùng annotation | Claiming và discovery order, processor quá tham lam | Kiểm tra annotation hỗ trợ và `return true/false` |
| `-processorpath` ở Windows không tìm được JAR | Dùng `:` thay vì `;` giữa các path entries | Dùng dấu phân cách path theo OS |
| Processor chạy lặp khác ý định ở CI | Nguồn sinh cũ, incremental cache, output chưa sạch | Reproduce trên output sạch và kiểm tra build tool |

**Lưu ý:** một số lỗi chỉ xảy ra khi vào code generation, không nhất thiết ở lúc processor được load. Đừng cho rằng mọi lỗi `cannot find symbol` đều là lỗi processor: có thể do source/package/classpath. Đọc diagnostic đầy đủ, và kiểm chứng generated source trước khi sửa cấu hình vô tội vạ.

## 16. Checklist cấu hình processor đáng tin cậy

1. **Xác định processor FQCN**, annotation types mà nó hỗ trợ và bản Java cần để chạy implementation.
2. **Đặt annotation API** trên compile classpath/module path phù hợp với project source.
3. **Đặt processor implementation và runtime dependencies của nó** trên `--processor-path` hoặc `--processor-module-path` đúng artifact type.
4. **Quyết định chọn explicit hay discovery:** `-processor p.X` cho danh sách cố định; service file hoặc `provides` khi muốn SPI.
5. **Bật processing rõ ràng**, nhất là trên JDK 23+; không dựa vào JAR rơi vào classpath.
6. **Đặt `-s`, `-d`** để quản lý source và bytecode output rõ ràng.
7. **Kiểm tra rounds và generated outputs:** `-XprintRounds`, `-XprintProcessorInfo`, file `.java`/`.class` thực.
8. **Phân biệt `-proc:none`/`-proc:only`/full compilation**, không nhầm chỉ sinh source với đã compile ứng dụng.
9. **Khóa phiên bản processor dependencies** và kiểm thử trên build JDK được hỗ trợ.
10. **Không để processor path chứa mọi app dependency** nếu không cần; audit processor như một phần của toolchain có thể thực thi mã.
11. **Test trên build sạch và CI**, đặc biệt khi đổi JDK, Maven/Gradle hoặc nâng dependency.
12. **Kiểm tra runtime thật:** generated class có mặt trong artifact, nhưng processor bản thân thường không cần đi kèm ứng dụng.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `-processor proc.InfoProcessor` có chỉ ra nơi tìm file `InfoProcessor.class` không?  
**Đáp án:** Không. Nó chọn class processor; cần processor path/module path hoặc cấu hình loading phù hợp để tìm class.

**Câu 2.** `-processorpath libs/tool.jar` có buộc chạy đúng `com.acme.MyProcessor` không?  
**Đáp án:** Không nhất thiết. Nếu dùng discovery, service metadata quyết định provider candidates. Nếu muốn cố định một processor, dùng `-processor com.acme.MyProcessor`.

**Câu 3.** Vì sao app import được annotation nhưng generated class vẫn không có?  
**Đáp án:** Compile classpath đúng chưa đảm bảo processor loader tìm được implementation hoặc processing được enable. Kiểm tra processor path, processor selection, rounds và `-proc:none`.

**Câu 4.** Dùng JDK 23, processor JAR nằm trên `-cp` và service metadata hợp lệ. Có nên mặc định processor tự chạy không?  
**Đáp án:** Không. Từ JDK 23 implicit processing từ classpath bị vô hiệu theo mặc định; cấu hình processor tường minh.

**Câu 5.** `-proc:only` có sinh `App.class` sau khi processing không?  
**Đáp án:** Không thực hiện compilation thông thường. Muốn cả source generation và bytecode, dùng mode processing + compile.

**Câu 6.** `--processor-module-path` và `--module-path` khác nhau thế nào?  
**Đáp án:** Một đường tìm **processor modules** để compiler thực thi chúng; đường còn lại tìm **application modules** cho source đang biên dịch.

**Câu 7.** Vì sao processor có thể được gọi nhiều lần?  
**Đáp án:** Annotation processing có nhiều round; nguồn sinh mới được xử lý ở round tiếp theo; processor phải theo dõi `processingOver()` và tránh ghi cùng file hai lần.

**Câu 8.** Nếu dùng `return true` trong processor, điều đó có nghĩa class được biên dịch thành công không?  
**Đáp án:** Không. Nó claim annotation types được giao, không phải kết quả build; compile có thể vẫn lỗi.

**Câu 9.** Có cần đưa `build/processor` vào runtime classpath của `demo.App` không?  
**Đáp án:** Không đối với demo này; App chỉ dùng `GeneratedInfo` được biên dịch, không gọi processor lúc chạy.

## 18. Ghi nhớ và tham khảo

**`-processor` trả lời “chọn implementation nào?”**; **`-processorpath`/`--processor-path` trả lời “tìm và load implementation cùng dependencies ở đâu?”**; **`--processor-module-path` dành cho modular processor providers**. Compile classpath của source, output `-s`/`-d` và runtime classpath ứng dụng là những thành phần **riêng**. Cấu hình processing phải rõ ràng trên JDK 23+, nên khai báo processor dependency và lựa chọn processor tường minh/qua SPI, không dựa vào discovery ngẫu nhiên.

Nguồn chính thức: [Oracle JDK 25 — javac Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html), [Oracle JDK 17 — Processor interface](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html), [Oracle — JDK 23 release notes (annotation processing disabled by default)](https://www.oracle.com/java/technologies/javase/23all-relnotes.html), [JDK 17 — Filer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html).