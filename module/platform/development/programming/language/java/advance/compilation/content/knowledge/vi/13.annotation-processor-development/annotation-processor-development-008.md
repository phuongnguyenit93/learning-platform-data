# Xử lý `processingOver`, `errorRaised` và dữ liệu qua nhiều vòng trong annotation processor

Một annotation processor không chỉ có nhiệm vụ đọc annotation rồi tạo một file. Trong **JSR 269**, một lần gọi `javac` có thể thực hiện nhiều **processing rounds**: mã nguồn/class mới được processor tạo ra ở vòng trước trở thành đối tượng để phân tích trong vòng sau, và những processor đã tham gia tiếp tục nhận lời gọi `process(...)`, kể cả **vòng cuối**. Muốn xây dựng processor đáng tin cậy, cần quản lý **trạng thái qua nhiều vòng**, xử lý đúng tín hiệu **`RoundEnvironment.processingOver()`** và **`RoundEnvironment.errorRaised()`**, đồng thời tránh tạo file trùng và không xem vòng cuối là một cơ hội phát sinh mã mới.

Bài học này giải thích chi tiết các điều kiện, cung cấp processor Java 17 hoàn chỉnh vừa sinh source vừa ghi nhận các kiểu đã thấy ở nhiều vòng, rồi đưa ra tình huống cố ý phát sinh diagnostic error để chứng minh `errorRaised()` không giống `processingOver()`.

## 1. Vòng xử lý và ba loại trạng thái khác nhau

Trong một invocation của công cụ biên dịch:

1. `javac` có tập source/class file ban đầu, các root elements và annotation types có thể được xử lý.
2. Processor được chọn được gọi `process(annotations, roundEnv)` cho round hiện tại.
3. File `.java`/`.class` mới được tạo qua `Filer` và đóng writer/stream đúng cách sẽ được xét ở **round tiếp theo**.
4. Một round không tạo thêm kiểu nguồn/class mới để xử lý dẫn tới **final round**. Những processor đã được gọi ở round trước nhận lần gọi cuối để tổng kết.
5. Nếu build không dừng vì lỗi hoặc không dùng chế độ chỉ xử lý, công cụ tiếp tục hoàn tất compilation.

Sơ đồ ví dụ:

```text
Input: demo.Main @Tracked("root")
             |
             v
       Round 1: process(Main)
       state = {"demo.Main"}
       Filer sinh demo.Generated
             |
             v
       Round 2: process(Generated)
       state = {"demo.Main","demo.Generated"}
       không sinh file tiếp
             |
             v
       Final round: processingOver() == true
       không sinh thêm source/class
       tổng kết state và prior errors
             |
             v
       Compiler hoàn tất hoặc báo thất bại
```

Trong sơ đồ, **state** tồn tại qua nhiều lần gọi `process` của **cùng processor instance**. Nhưng đối tượng `RoundEnvironment` phản ánh **round cụ thể**, không phải toàn bộ lịch sử.

| Thứ cần kiểm tra | Nguồn | Ý nghĩa |
| --- | --- | --- |
| Round hiện tại có kết thúc processing không? | `roundEnv.processingOver()` | `true` ở final round; kiểu sinh trong round này không được đưa sang một processing round mới |
| Vòng trước có báo error không? | `roundEnv.errorRaised()` | `true` nếu đã phát sinh error trong **prior round**, không phải “tổng trạng thái build” |
| Những root elements của round hiện tại là gì? | `roundEnv.getRootElements()` | Các root declarations được đưa vào round đó |
| Những elements có annotation phù hợp? | `roundEnv.getElementsAnnotatedWith(...)` | Những elements khớp trong phạm vi round hiện tại |
| Processor đã gặp những type nào từ đầu? | **State do processor tự lưu** | Ví dụ `Set<String> observedTypes`, không có sẵn qua một `RoundEnvironment` |
| Đã sinh một type cụ thể chưa? | **State của processor + `Filer`** | Ngăn tạo trùng output trong cùng invocation |

**Nhầm lẫn phổ biến:** `getElementsAnnotatedWith(...)` trả về tập rỗng **không chứng minh đã đến final round**. Một generated type có thể không mang annotation processor quan tâm; processor đã tham gia trước đó vẫn tiếp tục được gọi.

## 2. `processingOver()`: nhánh xử lý vòng cuối

API `RoundEnvironment.processingOver()` có mô tả: trả `true` nếu các type sinh ra trong round này **không được đưa vào một subsequent round of annotation processing**. Đây là tiêu chí để nhận biết vòng cuối trong processor.

Mẫu xử lý đáng dùng:

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    if (roundEnv.processingOver()) {
        // Tổng kết hoặc kiểm tra cuối cùng.
        // Không phát sinh class/source file cần processor xử lý tiếp.
        return true;
    }

    // Phân tích elements và có thể tạo source/class.
    return true;
}
```

Đây là **mảnh phương thức** bên trong một `AbstractProcessor`, chưa phải một class có imports đầy đủ.

### Được làm gì ở vòng cuối?

- Đọc **trạng thái tích lũy** đã lưu từ những round trước.
- In diagnostics bằng `Messager` để cho biết kết quả hoặc phát hiện thiếu dữ liệu, khi có lý do phù hợp.
- Kiểm tra các điều kiện invariant, ví dụ một nhóm annotation bắt buộc phải sinh ra một kiểu đã được ghi nhận.
- Giải phóng hoặc đóng tài nguyên do processor quản lý, nếu có.
- Ghi nhận `errorRaised()` của **vòng liền trước** để tránh báo kết luận thành công sai.

### Không nên làm gì ở vòng cuối?

- Tạo `.java`/`.class` mà processor khác phải xử lý trong một round mới: **không có round tiếp theo để thực hiện điều đó**.
- Dùng `createSourceFile` ở final để xây một type mà source ứng dụng sẽ import; cách này có thể làm compiler cảnh báo và không xử lý file mới như mong đợi.
- Gọi `processingOver() == true` là bằng chứng compiler đã thành công. Final round cũng có thể diễn ra trong luồng xử lý lỗi.
- Giả định final round luôn là round số 2 hoặc số 3. Số vòng phụ thuộc các file được tạo và quá trình xử lý thực tế.

**Lưu ý tinh tế:** Một processor có thể tạo **resource** ở giai đoạn phù hợp, nhưng resource tạo qua `Filer.createResource` không được coi như source/class mới để thúc đẩy annotation round. Với mã nguồn/class mới, hãy sinh **trước** final round. Nếu cần artifact tổng hợp cuối cùng dạng `.java`, bạn phải thiết kế để quyết định nội dung ở round bình thường có đủ dữ liệu, hoặc dùng cơ chế build khác cho bước tổng hợp; không tự kỳ vọng “final round tạo source rồi compiler sẽ chạy lại”.

## 3. `errorRaised()`: đúng là lỗi của *prior round*

Theo tài liệu Java SE 17, `RoundEnvironment.errorRaised()` trả `true` **nếu một lỗi đã được báo trong vòng xử lý trước**. Vì vậy:

- Ở round đầu, khi chưa có round xử lý thực tế nào trước đó, thường không có lỗi prior round để báo.
- Nếu processor phát `Diagnostic.Kind.ERROR` ở round 1, **round kế tiếp** sẽ được cung cấp tín hiệu `errorRaised() == true`.
- Nếu một round có warning nhưng không có error, `errorRaised()` không được bật chỉ vì warning.
- `errorRaised() == false` **không bảo đảm** quá trình compile cuối cùng sẽ thành công; ví dụ vẫn còn lỗi type checking/phân giải được phát hiện sau processing.

Giả sử:

```text
Round 1:
  processingOver=false
  errorRaised=false
  processor phát ERROR

Round cuối sau đó:
  processingOver=true
  errorRaised=true
  processor biết prior round đã lỗi
```

Đây là **dòng trạng thái điển hình** cho một lỗi được processor phát hiện ở vòng đầu. Một trường hợp phức tạp với nhiều rounds có thể cần theo dõi lỗi **lịch sử**, vì `errorRaised()` chỉ trực tiếp nói về vòng trước đó.

### Lưu lỗi qua nhiều vòng

Một processor muốn biết “đã từng thấy lỗi do vòng trước báo” có thể duy trì state:

```java
private boolean observedPriorRoundError;

@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    observedPriorRoundError |= roundEnv.errorRaised();
    if (roundEnv.processingOver()) {
        // Có thể dùng observedPriorRoundError để tránh báo success.
        return true;
    }
    return true;
}
```

Đây là **mảnh minh họa**, không phải tệp độc lập. Giá trị này chỉ tích lũy những lỗi mà API `errorRaised` đã phơi bày khi processor nhận các round tương ứng. Nếu **chính processor** phát error ở round hiện tại và cần một cờ tổng hợp ngay lập tức, hãy tự đặt `hasReportedError = true` tại lúc gọi `Messager.printMessage(ERROR, ...)`; đừng đợi `errorRaised` cập nhật trong cùng lời gọi.

Bảng ba trạng thái quan trọng:

| Trạng thái | Diễn giải đúng |
| --- | --- |
| `processingOver=false, errorRaised=false` | Round thường; vòng trước chưa báo lỗi theo API; có thể tiếp tục xử lý/sinh file |
| `processingOver=true, errorRaised=false` | Round cuối; không có tín hiệu lỗi ở vòng trước; **không** chứng minh compilation sẽ thành công |
| `processingOver=true, errorRaised=true` | Round cuối, prior round đã báo error; không cố sinh tiếp để “cứu” build |

Không lấy bảng trên để hứa compiler sẽ **luôn** đưa ra mọi tổ hợp trạng thái trên mọi chương trình. Nó là bảng diễn giải hai flags khi processor nhận chúng.

## 4. Trạng thái được lưu qua các vòng ở đâu?

Theo hợp đồng `Processor`, compiler **không khởi tạo processor object mới mỗi round**. Sau khi `init(ProcessingEnvironment)` được gọi, cùng processor instance nhận các lần gọi `process` thuộc invocation đó.

Ví dụ state:

```java
private final Set<String> seenTypeNames = new TreeSet<>();
private final Set<String> emittedTypeNames = new HashSet<>();
private int calls;
private boolean emittedAnySource;
private boolean hasReportedError;
```

Các trường trên là **mảnh khai báo**, phải đặt vào class có các imports phù hợp; không phải file `.java` độc lập.

Ý nghĩa:

- `seenTypeNames` lưu **tên kiểu ổn định dạng String** từ nhiều rounds để dùng ở final.
- `emittedTypeNames` ghi nhận tên types đã được sinh, tránh gọi `Filer.createSourceFile` hai lần cho cùng tên.
- `calls` đếm số lần processor nhận `process` trong invocation đang chạy; **không** phải số rounds toàn bộ compiler nếu processor được chọn muộn.
- `emittedAnySource` dành cho processor chỉ được phép sinh một artifact trong invocation.
- `hasReportedError` giúp nhận diện lỗi processor tự báo ngay khi phát ra diagnostic.

### Vì sao nên lưu tên thay vì giữ `Element`/`TypeMirror` quá lâu?

`Element` và `TypeMirror` được compiler cung cấp trong processing environment và gắn với mô hình chương trình đang được xử lý. Khi mã mới xuất hiện qua rounds, mô hình có thể phát triển và các đối tượng model có quy tắc riêng. Lưu **String, primitive, DTO bất biến hoặc dữ liệu tổng hợp nhỏ** thường dễ hiểu, dễ kiểm thử hơn giữ tham chiếu model rồi sử dụng tùy ý nhiều rounds.

Không đem processor instance hay state giữa **hai compilation invocations** khác nhau làm nguồn sự thật. Dù một hệ build có thể dùng JVM daemon lâu dài, API chuẩn không bảo đảm trạng thái field của processor instance là bộ nhớ bền vững giữa hai lần build. Muốn incremental build đúng, dùng đầu vào/đầu ra được build tool quản lý và **originating elements** của `Filer`.

### State cần deterministic

Tập được `getElementsAnnotatedWith(...)` trả về có thể không có thứ tự phù hợp để dùng làm thứ tự xuất file hoặc serialization. Nếu muốn log/tạo output ổn định, **sắp xếp tên** (ví dụ `TreeSet`) trước khi tổng hợp. Nếu hai rounds cùng cung cấp một type name (hoặc processor được gọi lại trong hoàn cảnh đặc biệt), sử dụng `Set` để tránh đếm trùng theo chính sách đã chọn.

Với **aggregating processor** sinh một artifact từ nhiều phần của source, xác định rõ khi nào đã thu đủ dữ liệu. `processingOver()` phù hợp để **kiểm tra/tổng kết**, nhưng không phải thời điểm hợp lệ để tạo một Java source mới cần được xử lý tiếp. Những generator phức tạp cần cấu trúc giao thức nhiều rounds hoặc tách bước aggregation sang build task khác.

## 5. Ví dụ Java 17 hoàn chỉnh: giữ state, sinh type rồi tổng kết ở final

Ví dụ này gồm annotation `@Tracked`, processor `TrackingProcessor` và ứng dụng `Main`. Processor thực hiện:

1. Nhận `demo.Main` có `@Tracked("root")` ở round 1.
2. Lưu tên `demo.Main` và **sinh source** `demo.Generated` (cũng có `@Tracked("generated")`).
3. Ở round 2, nhận `demo.Generated`, tích lũy vào cùng `Set<String>`; không sinh lại file.
4. Ở final round, đọc `processingOver` và `errorRaised`, in diagnostic `NOTE` với tập tên đã quan sát rồi trả về. Không sinh mã trong final.
5. Ứng dụng gọi `Generated.message()` sau khi compiler biên dịch file nguồn vừa sinh.

### 5.1. Cấu trúc dự án

```text
project/
└── src/
    ├── demo/
    │   ├── Tracked.java
    │   └── Main.java
    └── processor/
        └── TrackingProcessor.java
```

Nội dung **`src/demo/Tracked.java`**:

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface Tracked {
    String value();
}
```

`RetentionPolicy.SOURCE` đủ cho processor xử lý source; không yêu cầu annotation xuất hiện trong runtime class file. `Target(TYPE)` giới hạn chú thích cho các type declarations.

Nội dung **`src/processor/TrackingProcessor.java`**:

```java
package processor;

import demo.Tracked;
import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import java.util.TreeSet;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.Tracked")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class TrackingProcessor extends AbstractProcessor {
    private final Set<String> observedTypes = new TreeSet<>();
    private boolean generated;
    private boolean sawPriorError;
    private boolean reportedOwnError;
    private int calls;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        calls++;
        sawPriorError |= roundEnv.errorRaised();

        if (roundEnv.processingOver()) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.NOTE,
                    "calls=" + calls
                    + ", types=" + String.join(",", observedTypes)
                    + ", priorError=" + sawPriorError
                    + ", ownError=" + reportedOwnError);
            return true;
        }

        Element mainOrigin = null;

        for (Element element :
                roundEnv.getElementsAnnotatedWith(Tracked.class)) {
            if (element.getKind() != ElementKind.CLASS) {
                continue;
            }

            TypeElement type = (TypeElement) element;
            String fullName = type.getQualifiedName().toString();
            observedTypes.add(fullName);

            String label = element.getAnnotation(Tracked.class).value();
            if ("reject".equals(label)) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Rejected @Tracked value on " + fullName,
                        element);
                reportedOwnError = true;
            }

            if ("demo.Main".equals(fullName) && !reportedOwnError) {
                mainOrigin = element;
            }
        }

        if (!generated && mainOrigin != null) {
            try {
                JavaFileObject output = processingEnv.getFiler()
                        .createSourceFile("demo.Generated", mainOrigin);
                try (Writer writer = output.openWriter()) {
                    writer.write(
                            "package demo;\n"
                            + "@Tracked(\"generated\")\n"
                            + "public final class Generated {\n"
                            + "  private Generated() {}\n"
                            + "  public static String message() {\n"
                            + "    return \"Hello across rounds\";\n"
                            + "  }\n"
                            + "}\n");
                }
                generated = true;
            } catch (IOException exception) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate demo.Generated: "
                                + exception.getMessage(),
                        mainOrigin);
                reportedOwnError = true;
            }
        }

        return true;
    }
}
```

**Phân tích processor:**

- Hai annotation `@Supported...` mô tả annotation type và source version processor hỗ trợ.
- `observedTypes` là `TreeSet<String>` giữ **tên kiểu** qua rounds với thứ tự tăng dần ổn định; không lưu `Element` sau round.
- `generated` được chuyển `true` **sau khi writer đã đóng thành công**; processor không cố tạo `demo.Generated` nhiều lần.
- `calls` đếm số lần **processor này** được gọi trong invocation, không phải số round của các processors khác.
- `sawPriorError |= roundEnv.errorRaised()` tích lũy **tín hiệu lỗi của prior round**.
- `reportedOwnError` đặt ngay lúc processor gọi `printMessage(ERROR, ...)`. Đó là state do processor quản lý; nó khác với cờ do `RoundEnvironment` cung cấp.
- `mainOrigin` là originating element truyền cho `Filer.createSourceFile`, hữu ích cho hệ build incremental.
- `try (Writer ...)` đóng luồng ghi, cho phép compiler nhận biết generated source cho vòng sau.
- `roundEnv.processingOver()` được kiểm tra **trước** vòng lặp và thao tác `Filer`; final chỉ in tổng kết.
- `return true` nghĩa là processor **claim** annotation types nó được yêu cầu xử lý, không phải điều khiển dừng processing.

Với ví dụ nhỏ có một `Main` duy nhất, cờ boolean `generated` là đủ. Nếu sinh class theo từng annotated element trong dự án thật, dùng một `Set<String> generatedTypeNames` và chiến lược naming/idempotency để tránh bỏ sót hoặc tạo trùng.

Nội dung **`src/demo/Main.java`**:

```java
package demo;

@Tracked("root")
public final class Main {
    public static void main(String[] args) {
        System.out.println(Generated.message());
    }
}
```

`Generated` **chưa có trong source tree ban đầu**. Đây là ví dụ chủ ý cho phép `javac` nhận class được processor tạo trong quá trình annotation processing.

### 5.2. Biên dịch annotation và processor trước

Từ thư mục `project`, với JDK 17+ hỗ trợ target 17:

```sh
javac --release 17 -encoding UTF-8 -proc:none -d build/processor src/demo/Tracked.java src/processor/TrackingProcessor.java
```

Bước này xuất ít nhất:

```text
build/processor/
├── demo/Tracked.class
└── processor/TrackingProcessor.class
```

Dùng `-proc:none` vì lúc bootstrap chưa cần chạy processor. Nếu `javac` thành công, nó thường không in thông báo.

### 5.3. Biên dịch ứng dụng và chạy processor

```sh
javac --release 17 -encoding UTF-8 -cp build/processor -processorpath build/processor -processor processor.TrackingProcessor -s build/generated -d build/classes -XprintRounds -XprintProcessorInfo src/demo/Main.java
```

Ý nghĩa:

| Option | Vai trò |
| --- | --- |
| `-cp build/processor` | Cho app và generated source tra được annotation class `demo.Tracked` trong lúc compile |
| `-processorpath build/processor` | Cho công cụ tìm và nạp processor class |
| `-processor processor.TrackingProcessor` | Chọn processor tường minh; không cần service file |
| `-s build/generated` | Vị trí generated `.java` của `Filer.createSourceFile` |
| `-d build/classes` | Thư mục class files của ứng dụng và generated types |
| `-XprintRounds` | In thông tin root elements và annotations theo từng round |
| `-XprintProcessorInfo` | In thông tin processors được gọi/đã claim annotation |

Khi biên dịch thành công, cấu trúc đầu ra có dạng:

```text
build/
├── processor/
│   ├── demo/Tracked.class
│   └── processor/TrackingProcessor.class
├── generated/
│   └── demo/Generated.java
└── classes/
    └── demo/
        ├── Generated.class
        └── Main.class
```

### 5.4. Chạy chương trình và diễn giải log

```sh
java -cp build/classes demo.Main
```

**Stdout chính xác của chương trình:**

```text
Hello across rounds
```

Các lệnh `-XprintRounds` và `-XprintProcessorInfo` phát diagnostics trong quá trình compile, **không phải stdout của chương trình `Main`**. Vì trình bày và thứ tự có thể thay đổi theo JDK, đừng kiểm thử bằng cách so sánh toàn bộ log compiler từng ký tự.

Luồng xử lý dự kiến:

| Round | Roots liên quan | Annotations | Processor xử lý gì? |
| --- | --- | --- | --- |
| 1 | `demo.Main` | `demo.Tracked` | Ghi nhận `demo.Main`, sinh `demo.Generated.java` |
| 2 | `demo.Generated` | `demo.Tracked` | Ghi nhận `demo.Generated`; cờ `generated` chặn việc tạo lại |
| 3, final | Không có root mới | Không có | `processingOver() == true`; chỉ báo NOTE kết quả |

Diagnostic `NOTE` cuối thông thường có **nội dung cốt lõi**:

```text
calls=3, types=demo.Generated,demo.Main, priorError=false, ownError=false
```

Đây là **nội dung thông điệp mà source processor ghép thành**, không phải bản sao cam kết của toàn bộ dòng log `javac` (có thể có tiền tố `Note:`, khoảng trắng hoặc vị trí khác). `TreeSet` sắp xếp `demo.Generated` trước `demo.Main`.

Processor không cần tạo file vào final để đợi “vòng 4”; mã đã tạo từ round 1 được compiler nhận diện ở round 2 và biên dịch xong trong cùng invocation.

## 6. Thử `errorRaised()` bằng một trường hợp cố ý biên dịch thất bại

Để xem processor phản ứng với error, tạo **một source độc lập** `src/demo/Rejected.java`:

```java
package demo;

@Tracked("reject")
public final class Rejected {
}
```

`TrackingProcessor` có nhánh:

```java
if ("reject".equals(label)) {
    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.ERROR,
            "Rejected @Tracked value on " + fullName,
            element);
    reportedOwnError = true;
}
```

Đây là **mảnh trích có thật trong class processor đầy đủ**, không phải file riêng. Khi `Rejected` được xử lý, processor phát một `ERROR`. Dùng output riêng để không nhầm với build thành công của `Main`:

```sh
javac --release 17 -encoding UTF-8 -cp build/processor -processorpath build/processor -processor processor.TrackingProcessor -s build/rejected-generated -d build/rejected-classes -XprintRounds src/demo/Rejected.java
```

**Kết quả dự kiến:** Compilation thất bại (exit code khác 0), diagnostic chứa thông điệp `Rejected @Tracked value on demo.Rejected`. Không có output `demo.Generated` từ ví dụ negative này, vì processor chỉ phát sinh `Generated` khi gặp `demo.Main`.

Trong luồng phổ biến:

- Round đầu có `processingOver=false`, `errorRaised=false` trước khi processor gửi `ERROR`.
- Khi compiler gọi processor ở round kế tiếp/final, `errorRaised()` báo `true` do error ở prior round.
- `reportedOwnError` đã `true` **ngay trong round đầu**, vì processor tự cập nhật trước khi trả từ `process`.
- `sawPriorError` thành `true` khi compiler báo lỗi previous round.
- Final round vẫn **không** được diễn giải là “build đã sửa xong”.

Thông điệp NOTE tổng kết có thể chứa:

```text
calls=2, types=demo.Rejected, priorError=true, ownError=true
```

Đây là một **kịch bản thường gặp** khi processor được gọi ở round đầu rồi final; log chi tiết và số lần gọi có thể khác nếu công cụ tạo thêm round hoặc phát sinh thêm lỗi. Không dùng `calls == 2` làm assertion bắt buộc cho mọi JDK hay mọi tập source.

### Nếu processor phát `ERROR` thì có phải throw exception?

**Không.** `Messager.printMessage(Diagnostic.Kind.ERROR, ...)` là cách thông thường để phản hồi một vấn đề nguồn với diagnostic. Ném exception chưa xử lý từ `process` có thể khiến công cụ dừng các processor khác và làm lỗi khó đọc hơn; chỉ ném nếu thật sự không còn cách khôi phục hay báo lỗi hợp lý.

Đồng thời, nếu lỗi được phát trong một round, code processor không nên cố tạo những type vốn sẽ là artifact thành công rồi báo `“success”` ở final. Processor có thể thu thập thêm diagnostics nhưng phải tôn trọng thực tế compilation sẽ thất bại.

## 7. Giữ dữ liệu qua nhiều vòng mà không tạo mã trùng

Một thiết kế processor thực tế thường có **hai tập dữ liệu**:

- **Input-derived state**: những type/field/method đã được quan sát, trạng thái validation, các quan hệ cần tổng hợp.
- **Output-derived state**: tập tên các files đã được yêu cầu tạo, các files đã đóng writer thành công, các lỗi tạo file.

Gợi ý cấu trúc:

```java
private final Set<String> seen = new TreeSet<>();
private final Set<String> emitted = new HashSet<>();
private boolean hadValidationError;
```

Đây là **mảnh khai báo**. Hãy import `java.util.Set`, `TreeSet` và `HashSet` khi đưa vào processor hoàn chỉnh.

Với mỗi element:

1. Lấy **tên ổn định** chẳng hạn `((TypeElement) e).getQualifiedName().toString()`.
2. Validate annotation/options và ghi trạng thái.
3. Nếu cần sinh type `pkg.GeneratedX`, kiểm tra tên đó trong `emitted` hoặc tập được quản lý.
4. Gọi `Filer.createSourceFile` đúng tên; viết mã hợp lệ và đóng writer.
5. Ghi nhận kết quả tạo file thành công.
6. Ở round sau, xử lý những root mới nhưng không tự phát sinh trùng.
7. Ở final, chỉ kiểm tra dữ liệu/tổng kết; không sinh source/class mới.

### Vì sao `FilerException` quan trọng?

`Filer` có quy tắc không được tạo **cùng pathname/type nhiều lần trong một invocation**, bao gồm các trường hợp trùng với một input type hoặc giữa source/class files cùng tên. Nếu processor tạo `demo.Generated` ở round 1 rồi cố gọi `createSourceFile("demo.Generated")` lần nữa ở round 2, tool thường báo `FilerException` kiểu “Attempt to recreate a file for type ...”.

**Không giải quyết bằng xóa file tùy tiện** trong lúc compiler đang chạy. Sửa điều kiện sinh type, ownership giữa processors và naming scheme. File còn tồn tại từ một invocation cũ và việc tái tạo cùng file **trong một invocation** là hai vấn đề khác nhau; cần phân biệt output cũ/stale với quy tắc recreate của `Filer`.

Generated **resource** từ `Filer.createResource` không tự tạo thêm một processing round như source/class. Chỉ tạo một file mang đuôi `.java` bằng `Files.write` bên ngoài `Filer` cũng không được compiler đảm bảo đưa vào vòng sau.

## 8. `return true`/`false` không liên quan trực tiếp đến việc kết thúc round

`process(...)` trả về boolean để xác nhận processor có **claim annotation types** được giao hay không.

- `true`: processor nhận trách nhiệm cho các annotation types, những processors phía sau không tiếp tục được yêu cầu xử lý chính những annotations đã claim theo discovery.
- `false`: không claim, để các processors khác còn có thể xử lý.
- Không có ý nghĩa `true = compilation success` hoặc `false = ERROR`.
- Không có ý nghĩa `false = compiler sẽ làm round mới` hoặc `true = round cuối`.

Processor `@SupportedAnnotationTypes("*")` (universal processor) chỉ để audit/validate thường nên `return false`; trả `true` với `"*"` có thể chiếm annotation types khiến processors khác không được chạy như mong đợi.

Với processor `@Tracked` của ví dụ, `return true` là một lựa chọn claim annotation mà nó kiểm soát. Số round vẫn đến từ mã được sinh và điều kiện dừng, **không phải** giá trị boolean của `process`.

## 9. Những bẫy trong việc giữ `Element` và mô hình compiler

Một processor mới thường muốn đưa `Element` của round 1 vào `List<Element>` rồi dùng trực tiếp ở final round. Cần thận trọng:

- `Element`, `TypeMirror`, `AnnotationMirror` là **đối tượng model** gắn với processing environment, không phải các DTO bất biến độc lập với compiler.
- Compiler có thể bổ sung generated types ở các rounds sau; những tra cứu trạng thái tổng thể có thể thay đổi.
- Khi chỉ cần **tên kiểu, tên field, kiểu dạng text, enum constants hoặc thông tin annotation được xác minh**, nên trích xuất thành dữ liệu nhỏ phù hợp để giữ qua rounds.
- Khi cần phân tích types của current round, dùng `processingEnv.getElementUtils()`/`getTypeUtils()` và `roundEnv.getRootElements()` trong phạm vi API hỗ trợ.
- Không dùng Java runtime reflection như `Class.forName` để nạp class ứng dụng đang được biên dịch rồi kỳ vọng luôn tìm thấy class mới; những class đó có thể chưa tồn tại ở runtime của processor.
- Không giữ state xuyên hai compiler invocations vì một daemon/build tool có thể thay đổi cách tạo processor instances.

### Dữ liệu tổng hợp và incremental build

Một generated file có thể do một annotated class tạo ra (**isolating**) hoặc do tổng hợp nhiều annotated classes (**aggregating**). Đây là thuật ngữ thường gặp ở build tools; **không phải hai loại processor API mới** của JSR 269. Các build tools có thể yêu cầu metadata/cấu hình riêng để hỗ trợ incremental annotation processing.

Truyền `originatingElements` cho `Filer` giúp công cụ biết nguồn gốc tạo file. Nếu processor phụ thuộc vào tài nguyên không được khai báo hoặc thứ tự set không ổn định, clean build có thể đúng nhưng incremental build cho ra artifact cũ/sai. Cần kiểm thử cả hai loại build với output do build tool quản lý.

## 10. Không phải mọi điều kiện lỗi đều xuất hiện qua `errorRaised()` ngay lập tức

Khi code processor gặp lỗi, có thể có ba nguồn tín hiệu:

| Nguồn | Được thấy ở đâu? | Xử lý |
| --- | --- | --- |
| Processor tự validate và phát `Diagnostic.Kind.ERROR` | Ngay trong vòng hiện tại, do processor biết lúc phát | Đặt cờ nội bộ `reportedOwnError`, không sinh artifact thành công |
| Compiler thông báo error từ round trước | `roundEnv.errorRaised()` trong vòng tiếp theo | Lưu cờ tích lũy nếu cần biết lịch sử |
| Compiler phát hiện lỗi sau khi processors đã chạy | Các pha compile/type/link khác, không nhất thiết phản ánh ngược vào processor | Không kết luận compilation thành công chỉ vì final không thấy error |

Điều này giải thích tại sao **final round không phải một callback "onSuccess"**. Nó chỉ là callback cuối của annotation-processing lifecycle. Một processor có thể in log tổng kết, nhưng build tool/`javac` mới có quyền xác định exit status sau toàn bộ compilation.

Nếu thiết kế một artifact cần thể hiện “build thành công”, không tạo nó quá sớm dựa trên `!errorRaised()`; thay vào đó để **build system** quản lý marker/success artifact sau khi compiler trả exit code thành công.

## 11. Một ví dụ về dữ liệu giữa nhiều processors

Giả sử hai processors phối hợp:

- `ModelProcessor` thấy `@Model` trên class A và sinh `generated.DescriptorA` có `@Descriptor`.
- `DescriptorProcessor` thấy `@Descriptor` trên generated source và sinh thêm một mapper.

Điểm quan trọng: `DescriptorProcessor` không nên dựa vào việc **được gọi sau `ModelProcessor` trong cùng round** để lập tức tìm thấy `DescriptorA`. Generated source được đưa vào **round tiếp theo** theo hợp đồng `Filer`. Nếu mỗi processor cố tình tạo tiếp file mới mãi, toàn bộ invocation không hội tụ và có thể thành vòng xử lý dài bất thường.

Quy tắc phối hợp:

1. **Orthogonality:** một processor không nên đổi kết quả chỉ vì có processor khác không liên quan.
2. **Consistency:** cùng đầu vào → cùng đầu ra.
3. **Commutativity:** thứ tự xử lý những input độc lập không làm đổi kết quả cuối.
4. **Independence:** tránh yêu cầu output của processor khác phải xuất hiện ngay trong cùng round.
5. **No duplicate generation:** mỗi type được sinh có một chủ sở hữu.
6. **Finite progression:** chuỗi generated types phải có điều kiện dừng rõ ràng.
7. **Clear diagnostics:** lỗi validation được báo gắn với source element cụ thể khi có thể.

Các nguyên tắc này phù hợp hướng dẫn tính bền vững của API `Processor`, đặc biệt khi IDE, compiler và build tools khác nhau chạy cùng processor.

## 12. Công cụ quan sát và cách giải thích log

| Option `javac` | Tác dụng |
| --- | --- |
| `-processor processor.TrackingProcessor` | Chỉ định rõ processor muốn chạy |
| `-processorpath path` | Đường dẫn nạp processor |
| `-cp path` | Classpath dùng tra cứu annotations/dependencies trong source |
| `-s path` | Generated **source** output directory |
| `-d path` | Compiled **class** output directory |
| `-XprintRounds` | In round number, roots và annotation types theo cách của `javac` |
| `-XprintProcessorInfo` | In processors được gọi và annotation types liên quan |
| `-proc:only` | Chỉ chạy annotation processing, không làm bước compile class files thông thường |
| `-proc:none` | Tắt annotation processing |
| `-Akey=value` | Truyền option do processor khai báo hỗ trợ |

Khi quan sát `-XprintRounds`:

- Không coi **round number** là persistent ID qua incremental builds.
- Không kiểm thử chính xác thứ tự/nội dung mọi dòng stderr của compiler giữa các JDKs.
- Xác nhận type do processor tạo ở round n có mặt trong **round n+1**.
- Xác nhận final round báo `processingOver() == true` nếu processor ghi thông tin.
- Xác nhận generated files ở `-s` và compiled classes ở `-d` đúng như mong đợi.
- Đừng nhầm `-XprintProcessorInfo` với `System.out.println` do chương trình `Main` viết.

Khi chỉ muốn kiểm tra generated source:

```sh
javac --release 17 -encoding UTF-8 -cp build/processor -processorpath build/processor -processor processor.TrackingProcessor -s build/only-sources -d build/only-classes -proc:only -XprintRounds src/demo/Main.java
```

Đây là **lệnh riêng**, sử dụng output directories khác với ví dụ chạy đầy đủ. `-proc:only` không thực hiện bước compile final application classes thông thường; đừng kỳ vọng `Main.class` được xuất như ở `-proc:full`/normal compile. Với processor tự tạo class file qua `Filer.createClassFile` vẫn có những output tùy định nghĩa; phân biệt source processing với bước compile cuối.

## 13. Lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `process` được gọi lại với `annotations` rỗng | Processor đã tham gia round trước; current round không có annotation hỗ trợ | Xử lý an toàn empty set; dùng `processingOver` để nhận biết final |
| State chỉ thấy type từ round cuối | Đang ghi đè state hoặc chỉ đọc `getRootElements` một round | Dùng Set/Map ở processor instance để tích lũy |
| `processingOver()` là true nhưng code vẫn gọi `createSourceFile` | Không có final guard | Trả sớm ở final; không sinh class/source mới |
| `errorRaised()` luôn false trong lúc processor vừa gọi ERROR | Nó chỉ báo **prior round** | Lưu cờ nội bộ khi báo error; quan sát vòng kế |
| Final round không có error nhưng compile thất bại | Error xuất hiện ở pha khác hoặc trạng thái chỉ xem prior round | Dựa vào exit code compiler, không coi final là success |
| `FilerException: Attempt to recreate a file` | Tạo cùng type/path hai lần trong invocation | Ghi nhận tên đã tạo, sửa naming/condition |
| Sinh type đúng nhưng không xuất hiện ở round sau | Không dùng Filer, writer chưa đóng, source lỗi hoặc compilation hỏng | Gọi đúng `createSourceFile`, đóng writer, đọc diagnostics |
| Processor chỉ chạy khi gọi tường minh | Service discovery/processor path khác dự kiến | Chọn `-processor` hoặc khai báo service/module provider đúng |
| Tạo vô hạn generated sources | Generator không có điểm cố định hoặc không chặn tái tạo | Thiết kế finite generation, kiểm tra naming và cycles |
| Clean build đúng, incremental build sai | Stale outputs, origin không được khai báo hoặc input tracking thiếu | Kiểm tra originating elements, build tool và outputs |

### Quy trình debug có thứ tự

1. Xác minh `javac -version`, `-processor`, `-processorpath`, `-s`, `-d`, `-proc`.
2. Bật `-XprintRounds` và `-XprintProcessorInfo`; xác nhận processor có được nạp.
3. Kiểm tra từng round: `getRootElements()` và `getElementsAnnotatedWith(...)` có những gì?
4. Xem processor có guard `processingOver` trước khi tạo file không.
5. Khi gặp ERROR, đối chiếu **vòng phát error** với `errorRaised` ở **vòng tiếp theo**, không so trong cùng vòng.
6. Kiểm tra state instance có bị clear/ghi đè nhầm ở mỗi `process` không.
7. Kiểm tra generated filename/package và trạng thái writer đã đóng.
8. Nếu file không xuất hiện ở round tiếp, kiểm tra có phải tạo resource thay vì source/class hay không.
9. Kiểm tra exit code, generated sources/classes, rồi mới chạy ứng dụng.
10. So sánh clean build và incremental build nếu lỗi chỉ tái hiện qua nhiều lần build.

## 14. Checklist trước khi phát hành processor

- [ ] Processor có public no-argument constructor và khai báo supported annotations/source version đúng?
- [ ] Có xử lý **mọi lần gọi** `process`, kể cả empty annotation set và final round?
- [ ] `processingOver()` được kiểm tra trước thao tác sinh mã?
- [ ] `errorRaised()` được hiểu là **lỗi prior round**, không phải success flag?
- [ ] Processor tự lưu lỗi do chính nó phát ngay ở round hiện tại?
- [ ] State qua nhiều vòng được giữ trong instance bằng tên/DTO ổn định, tránh phụ thuộc vô ý vào `Element` cũ?
- [ ] Generated types được tạo bằng `Filer`, đóng stream và không tạo trùng?
- [ ] Dữ liệu tổng hợp có thứ tự deterministic, không phụ thuộc iteration order của set?
- [ ] Quy tắc claim annotation `return true/false` không bị nhầm với round termination?
- [ ] Có test một round bình thường, nhiều rounds sinh mã, final không sinh mã và negative case phát ERROR?
- [ ] Có thử processor khi cùng annotation được processor khác quan sát?
- [ ] Có kiểm tra clean và incremental build, không giữ state qua invocation một cách ngầm định?
- [ ] Có xác nhận application class files và exit code cuối cùng, không chỉ dựa vào NOTE ở final?

**Ghi nhớ:** `processingOver()` cho biết **đây là vòng cuối, không còn vòng annotation processing tiếp theo để xử lý mã mới**. `errorRaised()` cho biết **vòng trước đã báo lỗi**, không phải “build đã thất bại/thành công” theo nghĩa hoàn chỉnh. Trạng thái tích lũy qua nhiều vòng phải do processor lưu trong **cùng instance**, đồng thời cần có quy tắc tránh tạo trùng và kiểm soát lỗi. Với các điều kiện đó, processor sẽ tạo mã đúng lúc và tổng kết đúng nghĩa mà không vô tình kéo dài quá trình biên dịch.

## Tài liệu tham khảo

- Java SE 17, `javax.annotation.processing.RoundEnvironment` — `processingOver`, `errorRaised` và root elements: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html
- Java SE 17, `javax.annotation.processing.Processor` — lifecycle, subsequent rounds, final round và claiming annotations: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html
- Java SE 17, `javax.annotation.processing.Filer` — source/class generation, close streams, no duplicate outputs: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html
- Java SE 17, `javax.annotation.processing.Messager` — diagnostic errors/warnings/notes: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Messager.html
- Oracle JDK 17, *The javac Command* — `-processor`, `-s`, `-d`, `-XprintRounds`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html