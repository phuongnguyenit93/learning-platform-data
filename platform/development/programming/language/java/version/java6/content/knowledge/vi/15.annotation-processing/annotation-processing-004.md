# Annotation processing: Khai báo annotation type, option và source version được hỗ trợ

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **annotation mà mã nguồn sử dụng** (ví dụ `@Marked`) với **metadata trên annotation processor** (ví dụ `@SupportedAnnotationTypes`, `@SupportedOptions`, `@SupportedSourceVersion`).
- Khai báo chính xác annotation type mà processor xử lý, các option `-Akey=value` mà nó nhận, và phiên bản ngôn ngữ Java tối đa nó hỗ trợ.
- Hiểu cách `AbstractProcessor` dùng ba annotation metadata để triển khai `getSupportedAnnotationTypes()`, `getSupportedOptions()` và `getSupportedSourceVersion()`.
- Đọc option trong `ProcessingEnvironment.getOptions()`, phân biệt option **không có giá trị** với option không được cung cấp và biết cách xử lý input sai.
- Viết, biên dịch và chạy thử một processor với JDK 17+; chỉ định processor **tường minh** để hoạt động nhất quán trên JDK hiện đại, bao gồm JDK 23+.
- Nhận biết khác biệt giữa `SourceVersion.RELEASE_17`, `SourceVersion.latestSupported()`, `processingEnv.getSourceVersion()` và `javac --release 17`.

**Phạm vi:** Bài thuộc *Annotation processing* của Java. Các API `javax.annotation.processing`, `javax.lang.model`, `javax.tools` và cách đăng ký processor nêu ở đây **vẫn được hỗ trợ trong Java hiện đại**. Không dựa vào việc javac tự động quét processor trên classpath như một giả định mặc định lỗi thời.

## 1. Bối cảnh: processor khai báo “tôi xử lý cái gì?”

Annotation processing là cơ chế cho phép công cụ biên dịch khám phá và chạy các bộ xử lý annotation trên **mô hình mã nguồn**. Processor có thể kiểm tra điều kiện, phát diagnostic hoặc tạo thêm Java source/resource, thường trong lúc javac đang biên dịch.

Có hai nhóm annotation khác nhau:

1. **Annotation của chương trình đang được biên dịch**, ví dụ `@Marked` trên lớp `Example`. Chúng đại diện cho thông tin mà người viết source muốn cung cấp.
2. **Annotation khai báo khả năng của processor**, ví dụ `@SupportedAnnotationTypes("demo.Marked")`. Chúng nằm trên lớp kế thừa `AbstractProcessor` và cho công cụ xử lý biết processor này có thể làm việc với annotation nào, nhận option gì và hỗ trợ source version nào.

```text
Mã nguồn đang biên dịch:
   @demo.Marked class Example {}
              |
              v
         javac / JSR 269
              |
              +--> chọn processor qua cấu hình -processor / processor path
              |
              +--> hỏi processor:
              |       getSupportedAnnotationTypes()
              |       getSupportedOptions()
              |       getSupportedSourceVersion()
              |
              v
     MarkedProcessor.process(...)
              |
              +--> getElementsAnnotatedWith(...)
              +--> processingEnv.getOptions()
              +--> Messager / Filer
```

Ba thông tin **supported metadata** là một phần hợp đồng `Processor`, không phải “comment” để IDE hiển thị. Nếu khai báo sai, processor có thể không được gọi, bị cảnh báo version hoặc không nhận được những option mong đợi.

**Mục tiêu chính của bài:** khai báo đúng ba phần metadata này, quan sát chúng được API đọc ra và kiểm thử processor thực sự được gọi.

## 2. Ba annotation metadata chuẩn

| Annotation đặt trên lớp processor | Dữ liệu khai báo | API đọc tương ứng |
| --- | --- | --- |
| `@SupportedAnnotationTypes({...})` | Tên đầy đủ của annotation types mà processor hỗ trợ | `getSupportedAnnotationTypes()` → `Set<String>` |
| `@SupportedOptions({...})` | Tên các processor options được hỗ trợ | `getSupportedOptions()` → `Set<String>` |
| `@SupportedSourceVersion(SourceVersion.RELEASE_17)` | **Phiên bản source cao nhất** processor tuyên bố có thể xử lý | `getSupportedSourceVersion()` → `SourceVersion` |

Các annotation trên thuộc package `javax.annotation.processing`. Kiểu `SourceVersion` nằm trong `javax.lang.model`.

Cả ba metadata annotation được thiết kế để đặt trên **lớp processor**. Với processor kế thừa `AbstractProcessor`, các getter có implementation mặc định đọc chính annotation này. Nếu thay bằng implementation tự viết của `Processor`, bạn phải tự triển khai các getter theo hợp đồng tương ứng.

Một ví dụ rút gọn:

```java
@SupportedAnnotationTypes("demo.Marked")
@SupportedOptions({"demo.mode", "demo.audit"})
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class MarkedProcessor extends AbstractProcessor {
    // process(...) được triển khai trong ví dụ chạy đầy đủ bên dưới.
}
```

Đây **chỉ là minh họa khai báo**, chưa phải một chương trình hoàn chỉnh; chương trình đầy đủ có đủ import, `process(...)` và lệnh biên dịch tại mục 6.

### Thế nào là supported metadata?

- **Supported annotation types**: processor quan tâm tới những annotation *nào*.
- **Supported options**: processor hiểu những cấu hình *nào* được truyền qua javac.
- **Supported source version**: processor cam kết hiểu mô hình mã nguồn Java tới *phiên bản nào*.

Chúng không thay thế `@Target`/`@Retention` của annotation nghiệp vụ, không tự kích hoạt một processor chưa được khai báo với công cụ biên dịch và không bảo đảm processor thực sự triển khai đúng logic.

## 3. Khai báo supported annotation types

Cú pháp thường dùng:

```java
@SupportedAnnotationTypes("demo.Marked")
```

`"demo.Marked"` là **chuỗi tên đầy đủ (canonical name)** của annotation interface được xử lý, không phải `Marked.class` và cũng không phải tên lớp processor. Trong ví dụ, mã nguồn chứa `@demo.Marked` hoặc dùng `import demo.Marked; @Marked`.

Có một số cách diễn đạt khác theo hợp đồng `Processor`:

| Chuỗi | Ý nghĩa |
| --- | --- |
| `"demo.Marked"` | Chỉ annotation type cụ thể này. |
| `"demo.*"` | Những annotation interface có tên đầy đủ bắt đầu bằng `demo.`. |
| `"*"` | Tất cả annotation types, kể cả tình huống tập annotation rỗng. |
| `"my.module/demo.Marked"` | Chỉ annotation cụ thể trong named module `my.module` khi môi trường hỗ trợ module. |

**Không lạm dụng `"*"`** để “cho chắc”. Processor sẽ nhận nhiều trường hợp không liên quan, có thể làm tăng công việc và ảnh hưởng cách các processor khác được gọi nếu nhận claim không hợp lý. Với nhiệm vụ cụ thể, dùng danh sách type tên đầy đủ, có thể mở rộng bằng nhiều chuỗi:

```java
@SupportedAnnotationTypes({
    "demo.Marked",
    "demo.AnotherMarker"
})
```

Nếu annotation type không trùng với danh sách supported, processor có thể không được gọi cho type đó. Với `AbstractProcessor`, thiếu `@SupportedAnnotationTypes` khiến getter mặc định trả tập rỗng — không phải lời hứa “hỗ trợ hết”.

**Khác biệt cần nhớ:** `@SupportedAnnotationTypes` đặt **trên processor**. Annotation được xử lý, như `@Marked`, có thể tự khai báo `@Target(ElementType.TYPE)` và `@Retention(RetentionPolicy.SOURCE)`. Đây là metadata khác, có mục đích khác.

## 4. Khai báo supported options và truyền `-A`

Processor có thể cho người sử dụng cấu hình hành vi, ví dụ bật chế độ kiểm tra và ghi log:

```java
@SupportedOptions({"demo.mode", "demo.audit"})
```

Tên được khai báo ở đây là **key thuần túy**, không gồm tiền tố `-A` và không gồm phần `=value`.

Trong javac, có thể truyền:

```text
-Ademo.mode=strict
-Ademo.audit
```

Với các option đó, processor đọc:

```java
String mode = processingEnv.getOptions()
        .getOrDefault("demo.mode", "normal");

boolean audit = processingEnv.getOptions()
        .containsKey("demo.audit");
```

Theo hợp đồng API, `processingEnv.getOptions()` là `Map<String,String>`. Với option **có key nhưng không có value** (như `-Ademo.audit`), giá trị map ứng với key có thể là `null`; do đó `containsKey("demo.audit")` mới trả lời chắc chắn có bật flag hay không. Chỉ gọi `get("demo.audit") != null` có thể cho kết luận sai.

| Trường hợp | `containsKey("demo.mode")` | `get("demo.mode")` |
| --- | --- | --- |
| Không truyền option | `false` | `null` |
| `-Ademo.mode=strict` | `true` | `"strict"` |
| `-Ademo.mode` | `true` | `null` |
| `-Ademo.mode=` | `true` | Thường là chuỗi rỗng, tùy công cụ/triển khai |

**Khai báo option được hỗ trợ không tự kiểm tra giá trị.** Nếu `demo.mode` chỉ chấp nhận `strict` hoặc `normal`, processor phải tự kiểm tra và phát `Diagnostic.Kind.ERROR` khi giá trị ngoài danh sách. Một tên option lạ có thể làm javac cảnh báo “unrecognized processor option”, nhưng không nên xem việc cảnh báo đó thay thế validation nghiệp vụ.

Theo `Processor.getSupportedOptions()`, mỗi tên option phải là chuỗi các định danh hợp lệ phân tách bằng dấu chấm. `demo.mode` hợp lệ; tên chứa dấu gạch ngang như `demo-mode` không tuân theo dạng này.

## 5. Khai báo source version được hỗ trợ

Ví dụ cố định Java 17:

```java
@SupportedSourceVersion(SourceVersion.RELEASE_17)
```

Nghĩa là processor tuyên bố phiên bản source **cao nhất đã hỗ trợ** là Java 17. Đây không phải “phiên bản Java tối thiểu để chạy processor” và không thay thế các options của compiler.

Có ba khái niệm dễ nhầm:

| Giá trị | Câu hỏi được trả lời |
| --- | --- |
| `processor.getSupportedSourceVersion()` | Processor này *tuyên bố xử lý tới Java language level nào*? |
| `processingEnv.getSourceVersion()` | Lượt annotation processing hiện tại *đang được cấu hình cho source version nào*? |
| `SourceVersion.latestSupported()` | Runtime/model API hiện tại *hỗ trợ đầy đủ source version nào*? |

Nếu chạy `javac --release 17 ...` trên JDK 24, processor khai báo `RELEASE_17` và compiler xử lý source Java 17 là nhất quán. `RELEASE_17` không được tự cập nhật thành phiên bản JDK host.

Nếu build thay thành `--release 21` nhưng processor vẫn khai báo `RELEASE_17`, javac có thể phát **cảnh báo processor hỗ trợ source version thấp hơn source đang biên dịch**. Đây là dấu hiệu cần kiểm tra khả năng tương thích, không phải lý do nên tắt mọi cảnh báo.

### Cố định version hay chọn version động?

**Cách cố định:**

```java
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class MarkedProcessor extends AbstractProcessor {
    // ...
}
```

Ưu điểm: hợp đồng rõ ràng và compiler cảnh báo khi ứng dụng nâng source level mà processor chưa được chứng nhận tương thích. Nhược điểm: khi nâng target Java, đội phát triển phải kiểm thử processor và cập nhật metadata nếu thích hợp.

**Cách động** (khi processor thực sự hỗ trợ mô hình source do JDK hiện hành cung cấp):

```java
@Override
public SourceVersion getSupportedSourceVersion() {
    return SourceVersion.latestSupported();
}
```

Đây là **đoạn minh họa thay thế**, không nên đặt cùng `@SupportedSourceVersion(RELEASE_17)` rồi hy vọng annotation vẫn quyết định; getter được override sẽ là giá trị thực trả ra. `latestSupported()` trả phiên bản được môi trường thực thi hỗ trợ đầy đủ, không có nghĩa processor của bạn tự nhiên hiểu mọi cú pháp mới. **Chỉ dùng cách động nếu logic processor đã được thiết kế và kiểm thử cho các bản Java mới.**

Để nhận biết source level của một lượt xử lý hiện tại:

```java
SourceVersion currentSource = processingEnv.getSourceVersion();
```

Lời gọi này chỉ dùng khi processor đã được công cụ khởi tạo bằng `init(...)`, vì `processingEnv` do `AbstractProcessor` thiết lập. Đọc `processingEnv` ngay trong constructor chưa đúng vòng đời.

**Đặc biệt:** `--release 17` là option của compiler để biên dịch *source mục tiêu* theo Java 17. `@SupportedSourceVersion(RELEASE_17)` là metadata của *processor*. Dùng cả hai phù hợp giúp demo tránh cảnh báo version không cần thiết; không đánh đồng chúng.

## 6. Ví dụ Java 17+ chạy đầy đủ: annotation, processor, option và kiểm tra metadata

Ta xây ví dụ gồm:

- `demo.Marked`: annotation trong source code.
- `demo.Example`: lớp được gắn `@Marked`.
- `demo.processor.MarkedProcessor`: annotation processor nhận annotation type `demo.Marked`, hai option `demo.mode` và `demo.audit`, source version `RELEASE_17`.
- `demo.processor.MetadataCheck`: chương trình Java đọc trực tiếp ba getter để chứng minh metadata.
- Processor tạo file kiểm tra `processor-proof.txt` bằng `Filer`; nội dung file cho biết đã xử lý lớp nào và option có được nhận hay không.

### 6.1. Cấu trúc dự án

```text
annotation-demo/
├── processor/
│   └── demo/
│       └── processor/
│           ├── MarkedProcessor.java
│           └── MetadataCheck.java
├── src/
│   └── demo/
│       ├── Marked.java
│       └── Example.java
└── out/
    ├── processor/      (được tạo khi build)
    └── classes/        (được tạo khi build)
```

Lưu file đúng tên package/public class. Khi bắt đầu, `out` có thể chưa tồn tại; tạo hai thư mục đầu ra như lệnh phía dưới.

### 6.2. Annotation trong source: `src/demo/Marked.java`

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface Marked {}
```

`@Target(ElementType.TYPE)` giới hạn chỗ áp dụng annotation này cho những declaration kiểu thích hợp, ví dụ class. `@Retention(RetentionPolicy.SOURCE)` cho biết annotation phục vụ kiểm tra/biên dịch và không cần giữ trong bytecode để reflection runtime tìm thấy.

**Đây không phải `@SupportedAnnotationTypes`**: `@Marked` nằm trên các declaration của người dùng; còn `@SupportedAnnotationTypes` nằm trên processor và cho javac biết processor đó xử lý `@Marked`.

### 6.3. Mã sử dụng annotation: `src/demo/Example.java`

```java
package demo;

@Marked
public class Example {}
```

`Example` có một annotation. Khi javac nhận source này và processor được cấu hình, `MarkedProcessor` có thể tìm `Example` qua `roundEnv.getElementsAnnotatedWith(...)`.

### 6.4. Processor đầy đủ: `processor/demo/processor/MarkedProcessor.java`

```java
package demo.processor;

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
import javax.tools.FileObject;
import javax.tools.StandardLocation;

@SupportedAnnotationTypes("demo.Marked")
@SupportedOptions({"demo.mode", "demo.audit"})
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class MarkedProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        if (roundEnv.processingOver() || generated) {
            return true;
        }

        String mode = processingEnv.getOptions()
                .getOrDefault("demo.mode", "normal");
        boolean audit = processingEnv.getOptions().containsKey("demo.audit");

        for (TypeElement annotation : annotations) {
            for (Element element : roundEnv.getElementsAnnotatedWith(annotation)) {
                try {
                    FileObject report = processingEnv.getFiler().createResource(
                            StandardLocation.CLASS_OUTPUT, "",
                            "processor-proof.txt", element);
                    try (Writer writer = report.openWriter()) {
                        writer.write("type=" + element.getSimpleName() + "\n");
                        writer.write("mode=" + mode + "\n");
                        writer.write("audit=" + audit + "\n");
                    }
                    generated = true;
                } catch (IOException e) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "Could not write processor report: " + e.getMessage(),
                            element);
                }
            }
        }
        return true;
    }
}
```

Đọc những dòng quyết định:

1. Ba annotation `@Supported...` công bố **supported metadata** của processor.
2. Lớp kế thừa `AbstractProcessor` để dùng các getter mặc định và `processingEnv`.
3. `process(...)` nhận tập các `TypeElement` annotation mà compiler quyết định cung cấp trong một round và `RoundEnvironment` chứa những phần tử tương ứng.
4. `roundEnv.processingOver()` cho biết vòng xử lý cuối; demo không tạo thêm resource ở vòng cuối.
5. `getOptions()` lấy hai option. `demo.audit` được phát hiện bằng `containsKey` nên hoạt động kể cả khi truyền flag không có value.
6. `getElementsAnnotatedWith(annotation)` truy cập các declaration có annotation tương ứng; trong demo là `Example`.
7. `Filer.createResource(StandardLocation.CLASS_OUTPUT, ... )` ghi một file **báo cáo** vào output của compiler. Đây là hiệu ứng kiểm chứng processor đã chạy, không phải hành vi bắt buộc của mọi annotation processor.
8. `Messager.printMessage(ERROR,...)` chuyển lỗi ghi resource thành diagnostic compilation thay vì nuốt ngoại lệ.
9. `return true` báo cho infrastructure rằng processor **đã claim** các annotation types được nhận trong lượt xử lý; không tự làm các processor khác chạy hay tự bỏ qua lỗi compile.

**Giới hạn có chủ đích của ví dụ:** chỉ có một lớp `@Marked`. Resource `processor-proof.txt` được tạo **một lần** cho mục tiêu minh họa. Khi xây processor hỗ trợ hàng chục phần tử, cần tổng hợp dữ liệu và phát file đúng một lần, đồng thời lưu ý `Filer` không cho tạo lại cùng một file trong cùng lượt processing. `generated` ngăn tạo lại ở round sau; ứng dụng production cũng phải tránh ghi trùng giữa nhiều phần tử trong **cùng round**.

### 6.5. Chương trình đọc metadata: `processor/demo/processor/MetadataCheck.java`

```java
package demo.processor;

import java.util.TreeSet;

public final class MetadataCheck {
    public static void main(String[] args) {
        var processor = new MarkedProcessor();
        System.out.println("annotations=" +
                processor.getSupportedAnnotationTypes());
        System.out.println("options=" +
                new TreeSet<>(processor.getSupportedOptions()));
        System.out.println("source=" +
                processor.getSupportedSourceVersion());
    }
}
```

Chương trình này **chỉ đọc metadata**, không tự thực hiện annotation processing. Việc khởi tạo `MarkedProcessor` chỉ để gọi ba getter hợp lệ trong trường hợp này; `process(...)` cần được javac khởi tạo processor bằng `init(...)` và cung cấp rounds.

`TreeSet` sắp xếp option names để output ổn định, vì `Set` nói chung không bảo đảm thứ tự.

### 6.6. Build và chạy trên Windows PowerShell

Từ thư mục gốc `annotation-demo`, chạy:

```powershell
New-Item -ItemType Directory -Force out\processor, out\classes | Out-Null

javac --release 17 -d out\processor processor\demo\processor\MarkedProcessor.java processor\demo\processor\MetadataCheck.java
java -cp out\processor demo.processor.MetadataCheck

javac --release 17 -processorpath out\processor -processor demo.processor.MarkedProcessor '-Ademo.mode=strict' '-Ademo.audit' -d out\classes src\demo\Marked.java src\demo\Example.java

Get-Content out\classes\processor-proof.txt
Test-Path out\classes\demo\Example.class
```

**Lưu ý PowerShell:** Các tham số bắt đầu `-A` được đặt trong dấu nháy đơn như `'-Ademo.mode=strict'` để được chuyển thành **một argument nguyên vẹn** đến `javac`. Trên một số cách gọi PowerShell/Windows native commands, bỏ dấu nháy có thể làm tham số bị tách không như mong muốn.

### 6.7. Lệnh tương đương trên Linux/macOS

```bash
mkdir -p out/processor out/classes

javac --release 17 -d out/processor \
  processor/demo/processor/MarkedProcessor.java \
  processor/demo/processor/MetadataCheck.java

java -cp out/processor demo.processor.MetadataCheck

javac --release 17 \
  -processorpath out/processor \
  -processor demo.processor.MarkedProcessor \
  -Ademo.mode=strict -Ademo.audit \
  -d out/classes \
  src/demo/Marked.java src/demo/Example.java

cat out/classes/processor-proof.txt
test -f out/classes/demo/Example.class && echo class.exists=true
```

Cả hai đường lệnh đều **chủ động nêu tên processor**. `-processorpath out/processor` chứa `MarkedProcessor.class`; `-processor demo.processor.MarkedProcessor` chọn đúng processor. Vì đã cấu hình tường minh, ví dụ không phụ thuộc vào việc javac có tự scan processor trên classpath hay không.

### 6.8. Kết quả đã xác minh với JDK 24

Ba dòng `MetadataCheck`:

```text
annotations=[demo.Marked]
options=[demo.audit, demo.mode]
source=RELEASE_17
```

Nội dung `out/classes/processor-proof.txt`:

```text
type=Example
mode=strict
audit=true
```

Lệnh kiểm tra class cho kết quả `True` trong PowerShell hoặc `class.exists=true` ở lệnh `bash` phía trên.

Những kết quả này chứng minh **cả ba phần metadata** được đọc đúng và processor **đã thực sự được chạy**. Tệp `Example.class` được tạo vì lệnh dùng phương án annotation processing **và biên dịch** — không phải `-proc:only`.

Không có thông báo tùy ý hoặc vị trí dòng/cột nào được dùng làm điều kiện dự đoán stdout. Mã `MetadataCheck`, tên resource và nội dung do processor ghi được kiểm tra thực tế; tài liệu không phụ thuộc vào text compiler warning có thể khác giữa JDK.

## 7. Cách javac phát hiện và kích hoạt processor trong Java hiện đại

Từ JDK 23, javac **không tự thực hiện annotation processing chỉ vì tình cờ thấy processor trên classpath** mà không có cấu hình kích hoạt phù hợp. Cơ chế cũ từng dễ tạo ra những build không lường trước; với hệ thống mới hãy chọn processor và processor path rõ ràng.

Các lựa chọn cần biết:

| Lựa chọn javac | Tác dụng |
| --- | --- |
| `-processor demo.processor.MarkedProcessor` | Chọn trực tiếp processor cần chạy. |
| `-processorpath out/processor` / `--processor-path out/processor` | Chỉ ra nơi tìm processor trong mô hình classpath. |
| `--processor-module-path <path>` | Nơi tìm processor trong mô hình module khi sử dụng JPMS thích hợp. |
| `-proc:only` | Chỉ chạy annotation processing, không thực hiện giai đoạn biên dịch thành class file sau đó. |
| `-proc:full` | Thực hiện annotation processing và biên dịch. |
| `-proc:none` | Không chạy annotation processing. |
| `-Akey=value` / `-Aflag` | Truyền processor-specific options. |

Trong ví dụ, chỉ định `-processor` là cấu hình explicit để javac biết processor phải chạy, bao gồm trên JDK 23+. `-proc:full` cũng là một lựa chọn tường minh khi bạn muốn processing và compilation, nhưng **không nên chỉ bật discovery một cách rộng rãi** nếu ứng dụng phải kiểm soát chính xác processor nào được phép thực thi. Với mã nguồn và dependency không đáng tin cậy, quyền chạy processor nên được quản lý chặt chẽ.

**Phân biệt khả năng và khám phá:**

- `@SupportedAnnotationTypes` **không tự đăng ký** processor với compiler.
- `-processor ...` chọn processor cụ thể; processor đó khai báo annotation types mà nó xử lý.
- Khi không chỉ rõ tên processor, công cụ có thể khám phá processor thông qua cơ chế service provider cấu hình đúng, ví dụ `META-INF/services/javax.annotation.processing.Processor` trên processor path. Đây vẫn là một cơ chế hiện hành, nhưng build hiện đại nên chủ động cấu hình processor path hoặc danh sách processor được tin cậy.
- `@SupportedOptions` chỉ khai báo option được processor nhận; nó không có tác dụng bật annotation processing.

Nếu build dự án Maven/Gradle, dùng cấu hình annotation processor riêng của công cụ build tương ứng, bảo đảm processor classpath tách với dependency runtime khi phù hợp. Không dựa vào giả định mọi plugin build/version sẽ tự quét processor theo cùng một cách.

## 8. Option có giá trị, option dạng cờ và xử lý lỗi

Một processor cần dùng option thường nên đưa ra ba quy tắc:

1. **Tên chính xác** và có namespace, ví dụ `demo.mode` thay vì `mode` để tránh va chạm.
2. **Giá trị có thể nhận** và giá trị mặc định, ví dụ `normal` hoặc `strict`.
3. **Cách xử lý option sai**, ví dụ phát `Diagnostic.Kind.ERROR` để compiler dừng thay vì im lặng dùng giá trị lạ.

Đoạn minh họa thêm vào `process(...)` để kiểm tra `demo.mode`:

```java
String mode = processingEnv.getOptions()
        .getOrDefault("demo.mode", "normal");

if (!"normal".equals(mode) && !"strict".equals(mode)) {
    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.ERROR,
            "demo.mode must be normal or strict");
    return true;
}
```

Đây là **đoạn bổ sung**, không phải một lớp chạy độc lập. Thêm nó nếu thực sự cần ràng buộc option; không ghép bản demo nguyên trạng thành một chương trình mới chỉ từ đoạn này.

Đối với `-Ademo.audit`, cách đúng để kiểm tra **có truyền cờ hay không** là:

```java
boolean auditEnabled =
        processingEnv.getOptions().containsKey("demo.audit");
```

Nếu chỉ gọi `get("demo.audit")`, bạn có thể nhận `null` trong cả trường hợp không có key lẫn trường hợp key được truyền không có value.

Cũng không được mặc định mọi option javac đều là processor option. Ví dụ `--release 17` và `-d out/classes` là **compiler options**; không phải các key trong `getOptions()`. Chỉ các processor-specific options đi qua hợp đồng `-A`/API tương đương mới nằm trong map.

## 9. Source version: chính sách nâng Java và kiểm thử tương thích

### 9.1. Vì sao nên khai báo version cụ thể trong library dùng lâu dài?

Một processor có thể duyệt `TypeElement`, `ExecutableElement`, `AnnotationMirror`, type hierarchy, record component hoặc các construct Java mới. Nếu processor chỉ được kiểm thử với Java 17, khai báo `RELEASE_17` làm giới hạn đó minh bạch.

Khi ứng dụng nâng compiler/source target lên Java 21, 24 hoặc 27, cần:

- Chạy integration tests với source level mới thực sự cần hỗ trợ.
- Kiểm tra cách xử lý annotation trên các construct mới khi liên quan.
- Cập nhật `@SupportedSourceVersion` **sau khi kiểm chứng** processor tương thích, hoặc override getter với chiến lược được kiểm soát.
- Phân biệt JDK **chạy processor** với source/bytecode **mà compiler tạo cho ứng dụng**.

### 9.2. `SourceVersion.latestSupported()` không phải lời hứa tự động

`SourceVersion.latestSupported()` là API hiện hành, trả source version được execution environment hỗ trợ đầy đủ. Override getter để trả giá trị này là hợp lệ **khi processor thật sự xử lý đúng mô hình ngôn ngữ mới**.

Nếu processor phụ thuộc cấu trúc AST đặc thù hoặc giả định cú pháp Java 17, việc luôn báo `latestSupported()` có thể **che mất cảnh báo tương thích**. Đừng dùng nó chỉ để “hết warning”. Ngược lại, processor chỉ tìm annotation trên types qua các API chuẩn rất ổn định có thể phù hợp với chiến lược hỗ trợ rộng hơn — nhưng vẫn phải kiểm thử.

### 9.3. Vì sao `processingEnv.getSourceVersion()` lại khác?

`@SupportedSourceVersion` là **khả năng công bố của processor**. `processingEnv.getSourceVersion()` là **môi trường lượt biên dịch đang xử lý**. Processor có thể so sánh hai giá trị để chọn nhánh xử lý, phát cảnh báo hoặc kiểm tra các tính năng yêu cầu source version tối thiểu.

Trong named module, các lớp xử lý annotation nằm ở module chuẩn `java.compiler`. Nếu một processor được đóng gói như named module thì cấu hình service provider/module path khác với ví dụ classpath, nhưng ba metadata getter của `Processor` vẫn mang ý nghĩa tương tự.

## 10. Rounds, claim và vòng đời của processor

Compiler có thể gọi `process(...)` qua **nhiều rounds** nếu có tệp source mới được generated. Cần hiểu rõ:

- Processor được công cụ khởi tạo (`init(ProcessingEnvironment)`), rồi ba getter supported metadata được hỏi trong quy trình xử lý; không phải mỗi lần `process(...)` đều tạo một instance mới.
- `roundEnv.getElementsAnnotatedWith(...)` cung cấp elements liên quan đến annotation trong round.
- `roundEnv.processingOver()` cho biết vòng cuối; thông thường không tạo thêm source/file mới ở vòng này.
- `return true` thể hiện processor **claim** các annotation types mà nó xử lý trong round; `false` để chúng không được claim, cho phép các processor khác tiếp tục xử lý theo quy trình.
- `Filer` giữ nguyên tắc tạo file có tên duy nhất; không gọi `createResource(...)` nhiều lần cho cùng một file trong một run.

Mẫu demo có một lớp `@Marked` và một report; nó không phải framework tổng hợp nhiều annotation. Khi mở rộng, hãy lưu state thích hợp qua các rounds, gom những elements cần xử lý và ghi resource/generate source đúng một lần theo vòng đời phù hợp.

Không dùng `process(...)` để chạy những thao tác tùy ý vào runtime ứng dụng. Đây là giai đoạn **compiler time**, có thể làm tăng thời gian biên dịch và sinh file mà công cụ build phải quản lý.

## 11. Những lỗi hay gặp và cách xử lý

| Triệu chứng | Nguyên nhân điển hình | Hướng sửa |
| --- | --- | --- |
| Processor không được gọi | Chưa chọn/khám phá processor hoặc processor path sai. | Dùng `-processor <fqcn>` và `-processorpath <path>`, xác nhận file `.class` của processor tồn tại. |
| `process(...)` không nhận `@Marked` | `@SupportedAnnotationTypes` khai báo sai tên, ví dụ chỉ `"Marked"` khi type là `demo.Marked`. | Dùng tên annotation canonical, có package đúng. |
| Không nhận `demo.mode` | Quên `-A` hoặc sai key. | Truyền `-Ademo.mode=strict`, khai báo `@SupportedOptions("demo.mode")` và đọc `getOptions()`. |
| Cờ `-Ademo.audit` bị coi là tắt | `get("demo.audit")` trả `null` dù key được truyền không có value. | Dùng `containsKey("demo.audit")`. |
| javac cảnh báo unrecognized processor option | Key chưa được processor nào khai báo hỗ trợ, hoặc nhập sai tên. | Kiểm tra danh sách trong `@SupportedOptions`. |
| javac cảnh báo supported source version thấp | Processor khai báo `RELEASE_17` nhưng compiler xử lý source version mới hơn. | Kiểm thử rồi cập nhật version hỗ trợ; không tắt cảnh báo vô điều kiện. |
| Không có `processor-proof.txt` | Processor chưa chạy, không tìm thấy annotation, hoặc không có permission/output location phù hợp. | Kiểm tra `-processor`, supported types, `-d` và diagnostics. |
| Có report nhưng không có `Example.class` | Biên dịch dùng `-proc:only` hoặc lỗi trong các giai đoạn compile khác. | Dùng processing + compile, xem status và diagnostics; không suy ra class phải có sau `-proc:only`. |
| `FilerException` hoặc lỗi tạo resource trùng | Tạo cùng tên file nhiều lần qua elements/rounds. | Gộp dữ liệu, chỉ tạo resource một lần. |
| `processingEnv` chưa có dữ liệu | Truy cập từ constructor hoặc tự gọi `process` trước khi `init`. | Để compiler quản lý lifecycle hoặc chủ động `init` theo API nếu viết harness thích hợp. |

## 12. Checklist sử dụng trong dự án thật

1. **Xác định annotation type:** package và canonical name đầy đủ của annotation mà processor sẽ xử lý.
2. **Đặt `@SupportedAnnotationTypes` trên processor**, không nhầm với `@Target`/`@Retention` đặt trên annotation nghiệp vụ.
3. **Khai báo đúng `@SupportedOptions`**, chỉ gồm key; document cách truyền `-Akey=value` hoặc `-Aflag`, validate các giá trị có ý nghĩa.
4. **Khai báo version thực sự được kiểm thử** bằng `@SupportedSourceVersion` hoặc override `getSupportedSourceVersion()` có chủ đích.
5. **Chọn processor tường minh:** cấu hình `-processor` / processor path hoặc cấu hình build tool phù hợp, không dựa vào discovery ngầm.
6. **Phân biệt `--release` và supported source version:** một bên là target của compiler, một bên là khả năng processor công bố.
7. **Kiểm thử metadata và hành vi:** gọi getters trực tiếp rồi biên dịch source có annotation, xác nhận output/diagnostics.
8. **Quản lý rounds và file generation:** tránh ghi lại cùng resource nhiều lần.
9. **Đóng gói đúng vị trí:** processor nằm trong dependency dành cho compiler, không đưa vào runtime classpath của ứng dụng nếu không cần.
10. **An toàn:** annotation processors là mã Java **có thể chạy trong quá trình build**. Chỉ cho compiler dùng processor đã tin cậy; cô lập build với code/dependency không đáng tin khi có yêu cầu bảo mật.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `@SupportedAnnotationTypes("demo.Marked")` nên đặt trên `demo.Marked` hay lớp `MarkedProcessor`?

**Đáp:** Trên `MarkedProcessor`. `demo.Marked` là annotation được dùng trong source; metadata `@SupportedAnnotationTypes` khai báo processor hỗ trợ type nào.

**Câu 2.** Trên processor có `@SupportedOptions("demo.mode")`. Để bật chế độ strict khi chạy javac, truyền gì?

**Đáp:** `-Ademo.mode=strict`. Trong processor đọc `processingEnv.getOptions().get("demo.mode")` và kiểm tra giá trị. Không thêm tiền tố `-A` vào tên trong `@SupportedOptions`.

**Câu 3.** Vì sao `getOptions().get("demo.audit") == null` không chứng minh flag không được truyền?

**Đáp:** Option có thể được truyền chỉ với key (`-Ademo.audit`) và value `null`. Dùng `containsKey(...)` để phân biệt không có key với key có mặt nhưng không có value.

**Câu 4.** `@SupportedSourceVersion(RELEASE_17)` nói rằng processor chỉ chạy trên JDK 17?

**Đáp:** Không. Nó nói **source version cao nhất được processor công bố hỗ trợ** là Java 17, không phải yêu cầu phiên bản JVM tối thiểu/tối đa để chạy. Processor vẫn có thể chạy trên JDK 24 để xử lý source `--release 17`.

**Câu 5.** Trên JDK hiện đại, chỉ cần chép processor vào classpath là luôn tự chạy?

**Đáp:** Không. Từ JDK 23 cần cấu hình annotation processing tường minh. Ví dụ sử dụng `-processor demo.processor.MarkedProcessor` và `-processorpath out/processor`.

**Câu 6.** Vì sao `SourceVersion.latestSupported()` không nên được sử dụng chỉ để “dẹp cảnh báo”?

**Đáp:** Nó phản ánh khả năng của execution environment, không tự chứng minh processor của bạn tương thích mọi tính năng Java mới. Chỉ công bố version đã được thiết kế/kiểm thử.

**Câu 7.** Nếu dùng `-proc:only` thì không thấy `Example.class` có nghĩa processor không chạy?

**Đáp:** Không. `-proc:only` chủ động không chạy giai đoạn compilation tạo class thông thường. Cần kiểm tra diagnostics hoặc report processor tạo ra và dùng `-proc:full` hay cấu hình explicit compilation nếu muốn có `.class`.

## Tài liệu đối chiếu chính thức, vẫn còn áp dụng

- [Java SE 27 — `Processor`](https://docs.oracle.com/en/java/javase/27/docs/api/java.compiler/javax/annotation/processing/Processor.html): hợp đồng supported annotation types/options/source version, quy trình `init` và các rounds.
- [Java SE 26 — `AbstractProcessor`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): implementation mặc định của ba getter dựa trên `@Supported...`.
- [Java SE 26 — `SupportedAnnotationTypes`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/SupportedAnnotationTypes.html): cú pháp metadata annotation.
- [Java SE 26 — `SupportedOptions`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/SupportedOptions.html): khai báo processor-specific options.
- [Java SE 26 — `SupportedSourceVersion`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/SupportedSourceVersion.html): khai báo source level tối đa.
- [Java SE 27 — `SourceVersion`](https://docs.oracle.com/en/java/javase/27/docs/api/java.compiler/javax/lang/model/SourceVersion.html): `RELEASE_17`, `latest()` và `latestSupported()`.
- [Oracle JDK 23 Release Notes — thay đổi kích hoạt annotation processing](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html): yêu cầu cấu hình explicit từ JDK 23.

**Ghi nhớ:** `@SupportedAnnotationTypes` trả lời *annotation nào*, `@SupportedOptions` trả lời *option nào*, và `@SupportedSourceVersion` trả lời *tới Java source version nào*. Khai báo trên processor, đối chiếu qua getter của `AbstractProcessor`, kiểm tra hoạt động bằng source có annotation và luôn cấu hình processor rõ ràng trên JDK hiện đại.
