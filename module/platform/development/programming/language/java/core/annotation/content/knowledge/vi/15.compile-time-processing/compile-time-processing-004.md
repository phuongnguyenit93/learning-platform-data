# Vòng đời `init`, `process` và các vòng xử lý trong Java Annotation Processing

Annotation processing là cơ chế để một **annotation processor** được `javac` gọi trong lúc biên dịch nhằm **đọc mô hình chương trình**, phân tích annotation, báo lỗi/cảnh báo hoặc **sinh thêm source, class hay resource**. Processor không phải một listener được gọi khi ứng dụng chạy; nó hoạt động ở giai đoạn biên dịch và có vòng đời riêng.

Ba ý quan trọng nhất:

1. **`init(ProcessingEnvironment)`** chuẩn bị processor, thường được gọi một lần cho mỗi instance processor trong một lượt xử lý.
2. **`process(Set<? extends TypeElement>, RoundEnvironment)`** được gọi trong những **processing round** để nhận các loại annotation được giao và tập element đầu vào của vòng.
3. **Vòng mới xuất hiện khi có source/class mới được tạo để compiler xử lý**; sau các vòng thông thường sẽ có **vòng kết thúc** (`processingOver() == true`), không phải lời mời sinh thêm source cho vòng tiếp theo.

Mô hình này thuộc API chuẩn `javax.annotation.processing` và hoạt động với JDK 17+.

## 1. Những đối tượng tham gia một lượt annotation processing

| Thành phần | Nhiệm vụ |
| --- | --- |
| `javax.annotation.processing.Processor` | Hợp đồng mà annotation processor phải thực hiện, gồm `init`, `process`, truy vấn annotation/source version/options/completions. |
| `AbstractProcessor` | Lớp tiện ích triển khai một phần `Processor`, cung cấp `processingEnv`, `getSupportedAnnotationTypes()` và các phương thức mặc định. |
| `ProcessingEnvironment` | Các tiện ích được compiler cấp cho processor: `Messager`, `Filer`, `Elements`, `Types`, options, source version... |
| `RoundEnvironment` | Thông tin **riêng cho vòng hiện tại**: root elements, các element gắn annotation, `processingOver()`, `errorRaised()`. |
| `TypeElement` | Mô hình một khai báo kiểu Java; trong `process`, tập `annotations` chứa **các loại annotation** được giao cho processor. |
| `Filer` | Tạo file nguồn, file class hoặc tài nguyên theo quy tắc của processor API. |
| `Messager` | Phát ra diagnostic (NOTE, WARNING, ERROR) tại thời điểm biên dịch. |

Một processor thường kế thừa `AbstractProcessor`, khai báo annotation nó hỗ trợ và phiên bản Java mong muốn:

```java
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;

@SupportedAnnotationTypes("com.example.MyMarker")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class MyProcessor extends AbstractProcessor {
    // init(...) và process(...) được triển khai ở đây.
}
```

Đây chỉ là **khung minh họa**; để trở thành một class concrete có thể biên dịch, nó cần triển khai `process(...)`. Annotation tên `SupportedAnnotationTypes` nêu **tên chuẩn của annotation**, không phải tự tạo ra loại `MyMarker` trong project.

## 2. Bước khám phá processor: phải được compiler nạp

`javac` cần biết processor nào phải gọi. Các cách thông dụng:

- **Chỉ định tường minh** bằng `javac -processor com.example.MyProcessor ...`.
- **Service discovery**: đóng gói processor vào JAR có file `META-INF/services/javax.annotation.processing.Processor` liệt kê tên class processor, rồi để JAR ở đường dẫn tìm processor phù hợp.
- Công cụ build như Maven hoặc Gradle cấu hình annotation processor path và invocation tương ứng.

Processor phải **được biên dịch và có thể nạp trước khi chính nó xử lý mã ứng dụng**. Không nên giả định `javac` sẽ biên dịch một processor từ source và tự phát hiện/chạy processor đó trong cùng lượt nếu chưa được nạp. Ở ví dụ cuối bài, ta biên dịch processor trước, rồi chạy `javac` lần hai với `-processor` để tránh phụ thuộc khám phá tự động.

`-classpath` dùng để tìm các class khi biên dịch mã ứng dụng; `-processorpath` có thể dùng để chọn đường tìm processor (nếu không chỉ định, việc tìm processor tùy cơ chế tùy chọn `javac`). Với project có module path và processor module, có các tùy chọn riêng; không nên nhầm module path cho ứng dụng với processor path.

Processor nhận **mô hình code** (`Element`, `TypeMirror`) thông qua compiler, không nhận object runtime được dựng bằng `new` hoặc annotation proxy từ `Class.getAnnotation(...)`.

## 3. `init(ProcessingEnvironment)`: khởi tạo một lần

Khi compiler đã tạo instance processor, nó gọi:

```java
@Override
public synchronized void init(ProcessingEnvironment env) {
    super.init(env);
    // Chuẩn bị trạng thái, đọc options, kiểm tra cấu hình.
}
```

Trong `AbstractProcessor`, `super.init(env)` gắn `processingEnv`, kiểm tra các ràng buộc khởi tạo và giúp các phương thức khác truy cập môi trường. Hãy gọi `super.init(env)` khi override. Không nên gọi `init` thủ công từ code ứng dụng.

Một vài API có ích sau `init`:

```java
processingEnv.getMessager();       // Báo lỗi/cảnh báo/note cho compiler
processingEnv.getFiler();          // Tạo source/class/resource
processingEnv.getElementUtils();   // Tìm hiểu khai báo Element
processingEnv.getTypeUtils();      // Phân tích TypeMirror
processingEnv.getOptions();        // Options -A... do compiler cung cấp
```

`init` phù hợp với các việc **thực hiện một lần**: đọc cấu hình `-A`, tạo map/set giữ trạng thái đã xử lý, chuẩn bị helper. Không cần truy cập source code bằng Reflection runtime.

Phân biệt vòng đời:

- **Instance processor** nhận `init` một lần trong một lượt xử lý của compiler, sau đó có thể nhận **nhiều lần `process`**.
- Một lần gọi `javac` mới là một lượt biên dịch mới và có thể tạo **instance mới**; biến instance không bảo đảm lưu state giữa các lệnh build.
- Không lưu `ProcessingEnvironment` trong biến `static` dùng xuyên nhiều compiler task. Môi trường này thuộc một lượt biên dịch.

## 4. `process(...)`: nhận annotations và elements của vòng hiện tại

Chữ ký chuẩn:

```java
@Override
public boolean process(
        java.util.Set<? extends javax.lang.model.element.TypeElement> annotations,
        javax.annotation.processing.RoundEnvironment roundEnv
) {
    return true;
}
```

Tham số đầu tiên `annotations` là tập **annotation types đã được môi trường giao cho processor ở vòng này**, không phải tập tất cả class đã gắn annotation, cũng không phải một danh sách **giá trị runtime**. Muốn tìm những khai báo cụ thể:

```java
for (javax.lang.model.element.TypeElement annotationType : annotations) {
    for (javax.lang.model.element.Element element :
            roundEnv.getElementsAnnotatedWith(annotationType)) {
        // Đọc element và metadata bằng javax.lang.model.
    }
}
```

Các phương thức cốt lõi trên `RoundEnvironment`:

| API | Ý nghĩa |
| --- | --- |
| `getRootElements()` | Tập root elements của **vòng hiện tại**; vòng đầu thường là các top-level types/nguồn đầu vào, vòng sau có thể là khai báo mới do generator tạo. |
| `getElementsAnnotatedWith(TypeElement)` | Tìm các element được annotate bằng loại được truyền trong mô hình của vòng hiện tại. |
| `getElementsAnnotatedWith(Class<? extends Annotation>)` | Cách truy vấn bằng class annotation khi processor có thể nạp annotation type này; cách dùng `TypeElement` thường giúp hạn chế phụ thuộc runtime classloader. |
| `processingOver()` | Có phải vòng **kết thúc** hay không. |
| `errorRaised()` | Có diagnostic `ERROR` phát sinh **trong vòng trước đó** hay không. |

**Lưu ý thời điểm:** `errorRaised()` không nhất thiết báo lỗi vừa được `Messager.printMessage(ERROR, ...)` gửi **ngay trong lần `process` hiện tại**. Cần hiểu nó là trạng thái lỗi từ vòng trước theo hợp đồng `RoundEnvironment`.

Với nhiều annotation types, một processor có thể được yêu cầu xử lý một số loại trong vòng này và những loại khác được giao cho processor khác. Không nên mặc định `annotations` là tập đầy đủ mọi annotation xuất hiện trong cả chương trình.

## 5. Giá trị `boolean` của `process`: claim annotation

Giá trị trả về của `process` có ý nghĩa **claim** (*nhận trách nhiệm xử lý*) những loại annotation được giao:

- `return true;`: processor **claim** các annotation types mà nó nhận trong vòng này. Trong cùng round, các processor phía sau thường sẽ **không được yêu cầu xử lý chính những annotation types đã claim**.
- `return false;`: processor **không claim**; các processor khác vẫn có thể được giao loại annotation tương ứng.

Giá trị này **không** mang nghĩa “biên dịch thành công / thất bại”. Để báo lỗi có thể chặn compilation, hãy dùng `Messager` với `Diagnostic.Kind.ERROR`:

```java
processingEnv.getMessager().printMessage(
        javax.tools.Diagnostic.Kind.ERROR,
        "Cấu hình annotation không hợp lệ"
);
```

Một processor trả `true` vẫn có thể phát diagnostic ERROR; một processor trả `false` không có nghĩa compiler phải dừng. `process` cũng không phải thao tác trả dữ liệu được sinh ra: source/class mới xuất hiện do gọi `Filer`, không phải do `return true`.

**Chọn claim có chủ đích.** Nếu processor là nơi chịu trách nhiệm chính duy nhất cho một annotation, `true` thường phù hợp. Nếu nhiều processor cần cùng đọc loại metadata ấy, cần cân nhắc phối hợp và lựa chọn claim; đừng dùng wildcard `"*"` một cách thiếu kiểm soát rồi claim cả những loại annotation không thuộc nhiệm vụ của mình.

## 6. Processing rounds: tại sao có nhiều vòng?

Một lần biên dịch có thể gồm nhiều **round**. Compiler xử lý những source/class đã có, gọi processor, sau đó đưa các file **mới được sinh** vào vòng tiếp theo. Cách này cho phép generator thứ hai nhìn thấy kiểu được generator thứ nhất phát ra.

Sơ đồ thường gặp:

```text
Compiler nạp processor
        |
        v
      init()
        |
        v
Round 1: source ban đầu → process(..., roundEnv1)
        |       Filer tạo GeneratedA.java
        v
Round 2: GeneratedA.java → process(..., roundEnv2)
        |       Filer tạo GeneratedB.java
        v
Round 3: GeneratedB.java → process(..., roundEnv3)
        |       không có file Java/class mới
        v
Final round: processingOver() == true
        |
        v
Compiler hoàn tất những bước biên dịch còn lại
```

Không phải mọi compiler invocation luôn có chính xác ba round thông thường hoặc số lượng được cố định trước. Số round tùy các file phát sinh, lỗi, processor tham gia và các quy tắc processing.

Mỗi lần `process` có một **`RoundEnvironment` mới**. `getRootElements()` ở round kế tiếp không phải luôn là “tất cả các root của project”; các root mới có thể là những source/class mới vừa được generator tạo. Muốn giữ danh sách đã xét ở các vòng trước, processor phải **tự lưu trạng thái** trong instance (ví dụ `Set<String>`).

Một lượt xử lý kết thúc bằng vòng có `processingOver() == true`, dù trong thực tế compiler có thể gặp lỗi. Khi processing over, compiler không bắt đầu một vòng annotation processing mới để xử lý những type do `process` ở vòng kết thúc cố tạo thêm.

## 7. Vòng kết thúc: `processingOver()` và `errorRaised()`

Cách viết thường gặp:

```java
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment roundEnv) {
    if (roundEnv.processingOver()) {
        // Kết thúc, ghi chẩn đoán tổng kết hoặc dọn trạng thái tạm.
        return true;
    }

    // Chỉ trong vòng thông thường: đọc element và tạo source nếu cần.
    return true;
}
```

Đây là **snippet minh họa**, cần import `Set`, `TypeElement` và được đặt trong class processor.

Vòng kết thúc hữu ích để ghi **tổng kết**, phát những cảnh báo về dữ liệu chưa hoàn chỉnh, hoặc thực hiện logic cuối lượt. Tuy nhiên, nếu tạo thêm source/class trong vòng kết thúc, sẽ **không có vòng annotation processing tiếp theo dành cho file mới đó**; việc cố tạo file ở giai đoạn này có thể gây cảnh báo/lỗi hoặc đầu ra không được xử lý như kỳ vọng. Vì vậy, hãy sinh source trong các vòng thông thường.

`roundEnv.errorRaised()` cho biết đã phát sinh lỗi trong **vòng trước**. Nếu chương trình có bước tổng kết hoặc quyết định sinh metadata cuối, có thể kiểm tra cờ này để tránh xuất báo cáo “thành công” khi đã có lỗi.

Dùng `processingOver()` rõ ràng tốt hơn suy luận round cuối bằng việc `annotations.isEmpty()` hoặc `roundEnv.getRootElements().isEmpty()`. Một vòng thông thường có thể không có annotation type được giao cho **processor cụ thể** dù compilation vẫn còn tiếp diễn; ngược lại, vòng kết thúc là trạng thái chính thức do API báo.

## 8. Ví dụ Java 17+ chạy được: một processor đi qua ba vòng

Ta xây dựng ví dụ nhỏ không dùng thư viện ngoài. Processor nhận `@DemoTag` trên một class, tạo thêm **`GeneratedGreeting.java`** có cùng annotation, nhờ đó compiler có thêm một vòng thông thường để xử lý nguồn mới trước vòng kết thúc.

Tạo bốn file **cùng một thư mục** với đúng tên sau.

### File 1: `DemoTag.java`

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface DemoTag {
}
```

Annotation `DemoTag` dùng retention `SOURCE` vì processor đọc **mô hình source trong lúc biên dịch**, không cần giữ marker tới runtime. Nó áp dụng lên khai báo kiểu (`TYPE`).

### File 2: `RoundProbeProcessor.java`

```java
import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.ProcessingEnvironment;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("DemoTag")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class RoundProbeProcessor extends AbstractProcessor {
    private int roundCount = 0;
    private boolean generated = false;

    @Override
    public synchronized void init(ProcessingEnvironment env) {
        super.init(env);
        System.out.println("init");
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        int hits = 0;
        for (TypeElement annotationType : annotations) {
            hits += roundEnv.getElementsAnnotatedWith(annotationType).size();
        }

        roundCount++;
        System.out.println("round=" + roundCount
                + ", over=" + roundEnv.processingOver()
                + ", hits=" + hits);

        if (!roundEnv.processingOver() && !generated) {
            generated = true;
            try {
                JavaFileObject source =
                        processingEnv.getFiler().createSourceFile("GeneratedGreeting");

                try (Writer writer = source.openWriter()) {
                    writer.write(
                            "@DemoTag\n"
                          + "public final class GeneratedGreeting {\n"
                          + "    public static String message() {\n"
                          + "        return \"generated\";\n"
                          + "    }\n"
                          + "}\n"
                    );
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, ex.toString());
            }
        }
        return true;
    }
}
```

Giải thích trạng thái instance:

- `init()` in một dòng `init` khi processor được khởi tạo cho compiler task.
- `roundCount` tăng trong mỗi lần `process`.
- `hits` đếm các element được gắn annotation types thuộc tập `annotations` giao cho processor ở **vòng này**.
- `generated` bảo vệ khỏi việc ghi trùng **cùng một file** qua các round. Không có cờ này, gọi `createSourceFile("GeneratedGreeting")` lần hai có thể gây `FilerException`, vì Filer không cho cùng processor run tạo lại một file đã tạo.
- `!roundEnv.processingOver()` ngăn tạo file trong **vòng kết thúc**.
- `return true` thông báo processor claim `DemoTag`, không phải giá trị báo thành công của việc ghi file.

Ở ví dụ minh họa log dùng `System.out.println` để dễ theo dõi thứ tự lifecycle; trong processor thực tế, hãy dùng `Messager` cho thông báo có ý nghĩa compiler (NOTE/WARNING/ERROR), và hạn chế xuất log tùy ý nếu build cần output sạch.

### File 3: `Example.java`

```java
@DemoTag
public class Example {
    public static void main(String[] args) {
        System.out.println(GeneratedGreeting.message());
    }
}
```

`Example.java` cố ý gọi một class **chưa có trong source ban đầu**. `GeneratedGreeting` được processor tạo ở round 1, sau đó compiler có thể đưa nó vào các bước xử lý và biên dịch để `Example` tham chiếu được.

### Biên dịch và chạy

Thực hiện lần lượt trong thư mục chứa ba file `.java` vừa tạo:

```bash
mkdir out
javac -encoding UTF-8 DemoTag.java RoundProbeProcessor.java
javac -encoding UTF-8 -cp . -processorpath . -processor RoundProbeProcessor -d out Example.java
java -cp out Example
```

**Kết quả thông thường của lệnh `javac` thứ hai** (thông điệp do processor in ra `stdout`):

```text
init
round=1, over=false, hits=1
round=2, over=false, hits=1
round=3, over=true, hits=0
```

Lệnh chạy ứng dụng in:

```text
generated
```

Vì sao có ba lần `process`?

1. **Round 1:** compiler nhìn thấy `Example` có `@DemoTag`; processor được gọi với `hits=1` rồi dùng `Filer` tạo `GeneratedGreeting.java` cũng được đánh dấu `@DemoTag`.
2. **Round 2:** compiler xử lý source mới sinh ra, nên processor lại nhận `@DemoTag` trên `GeneratedGreeting`, `hits=1`. Vì `generated == true`, processor không tạo thêm file mới.
3. **Round 3:** không còn source/class mới cần xử lý trong một vòng tiếp theo, nên compiler gọi **final round** với `processingOver() == true`. `hits=0` và processor không tạo file mới.

Trong ví dụ này không có lỗi, nên `errorRaised()` sẽ là `false` ở những round đang xét. Không cần dựa vào nó để điều khiển số round.

`javac` có thể phát thêm thông tin khác tùy option và môi trường build; phần log được liệt kê trên là **các dòng do chính ví dụ in**, không bao gồm thông điệp từ wrapper hoặc IDE. Dùng `java -cp out Example` vẫn chạy vì class `Example` và `GeneratedGreeting` được tạo vào thư mục `out`; annotation `DemoTag` có retention `SOURCE` nên không cần nạp để Reflection runtime đọc.

**Chú ý:** Processor được khai báo hỗ trợ tên `"DemoTag"` vì ví dụ dùng package mặc định cho dễ thao tác trong một thư mục. Với project thật, nên đặt class vào package tường minh và ghi tên annotation đầy đủ, ví dụ `@SupportedAnnotationTypes("com.example.annotations.DemoTag")`, rồi cấu hình processor path phù hợp.

## 9. Giữ trạng thái giữa các vòng và tránh tạo trùng

Một lỗi thường gặp là coi mỗi lần `process` như một chương trình hoàn toàn mới. Thực tế cùng một instance processor được gọi qua các vòng của cùng lượt annotation processing, nên field instance giúp lưu trạng thái:

```java
private final Set<String> processedTypes = new HashSet<>();
```

Trong `process`, có thể lưu tên chuẩn `TypeElement.getQualifiedName().toString()` cho các kiểu đã xử lý. Khi gặp lại kiểu cũ, bỏ qua nếu quy trình không yêu cầu xử lý lại.

Ví dụ **minh họa** (cần import `Set`, `HashSet`, `Element`, `TypeElement` và đặt trong processor):

```java
for (Element element : roundEnv.getElementsAnnotatedWith(annotationType)) {
    if (element instanceof TypeElement type) {
        String name = type.getQualifiedName().toString();
        if (processedTypes.add(name)) {
            // Sinh một output duy nhất cho type này nếu cần.
        }
    }
}
```

Đối với generator, chọn **tên output ổn định** và xác định rõ mỗi output được tạo một lần. `Filer` theo dõi file được tạo trong một processing run; nếu gọi `createSourceFile` hai lần với cùng tên, `FilerException` là hành vi bình thường cần xử lý, không phải lỗi lạ của IDE.

Tránh lưu toàn bộ `Element` qua nhiều vòng nếu cần độ bền vững lâu dài; khi chỉ cần định danh, có thể lưu **tên chuẩn** và tra lại bằng `Elements` khi phù hợp. Một `Element` nằm trong mô hình compiler của lượt hiện tại, không phải object domain bền vững xuyên nhiều build.

## 10. Phân biệt `Filer`, `Messager` và `System.out`

Trong quá trình xử lý, processor thường làm ba việc:

1. **Kiểm tra** khai báo được gắn annotation bằng `Element`/`TypeMirror`.
2. **Báo kết quả chẩn đoán** bằng `Messager`.
3. **Sinh file** mới bằng `Filer` (khi thực sự cần).

Ví dụ báo lỗi có gắn vị trí element:

```java
processingEnv.getMessager().printMessage(
        javax.tools.Diagnostic.Kind.ERROR,
        "Chỉ được dùng annotation trên class hợp lệ",
        element
);
```

`element` ở đây là biến `Element` đã lấy từ `RoundEnvironment`, và snippet cần đặt trong phương thức xử lý phù hợp. Việc báo `ERROR` có thể khiến build thất bại; **trả về `false` không thay thế được việc gửi diagnostic**.

`Messager` giúp IDE và compiler hiển thị lỗi/cảnh báo gắn vị trí nguồn phù hợp. `System.out` chỉ là xuất text của tiến trình processor, không có cấu trúc diagnostic như compiler API; dùng để minh họa lifecycle thì được, nhưng khi phát triển thư viện nên ưu tiên `Messager`.

`Filer` không phải API để sửa source của người dùng tùy ý. Nó hỗ trợ **tạo** file mới tại những vị trí compiler quản lý; ghi đè output cũ trong cùng processing run hoặc tự thay thế mã đang biên dịch dễ gây xung đột.

## 11. Vòng đời và quy tắc xử lý lỗi

Một processor chất lượng cần phân biệt ba cấp lỗi:

| Cấp | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Annotation không hợp lệ | Thiếu thuộc tính bắt buộc về mặt nghiệp vụ, target sai | `Messager.printMessage(ERROR, ...)` gắn với element. |
| Lỗi sinh file | `FilerException`, không ghi được source, trùng tên | Phát diagnostic với thông tin cụ thể; không âm thầm nuốt lỗi. |
| Lỗi từ mã được sinh | File `.java` được tạo nhưng không compile được | Sửa logic generator, tên type/package/import; theo dõi round xảy ra lỗi. |

`RoundEnvironment.errorRaised()` **không thay thế** cơ chế xử lý `try/catch` khi tạo file. Nó chỉ cho biết đã có lỗi trong vòng trước đó. Ngay khi không thấy lỗi từ vòng trước, thao tác Filer hiện tại vẫn có thể thất bại.

Nếu processor phát ERROR ở vòng thường, compiler có thể tiếp tục một số công việc cần thiết để tổng kết rồi báo build thất bại. **Không** suy luận từ việc `processingOver()==true` rằng build chắc chắn thành công. Một final round có thể xuất hiện dù các vòng trước đã lỗi.

Với generator phát nhiều file có phụ thuộc nhau, nên thiết kế output sao cho:
- Không cần file vừa sinh ra được phản hồi ngược trong **chính vòng hiện tại**; nó thường được xử lý trong round tiếp theo.
- Không lặp vô tận việc sinh thêm file từ input sinh ra bởi chính mình.
- Không phụ thuộc thứ tự iteration của `Set<? extends TypeElement>` hay `getRootElements()`, vì không có thứ tự duyệt nguồn được bảo đảm.
- Khi đã báo lỗi, không công bố rằng tất cả source đã được sinh thành công.

## 12. Giao tiếp giữa nhiều processor

Trong một lượt biên dịch có thể có nhiều processor cùng tham gia. Compiler chịu trách nhiệm tổ chức các round và quyết định giao những annotation type phù hợp cho processor:

```text
Round 1: @InputModel ở mã nguồn
    ├─ Processor A đọc mô hình, sinh GeneratedDto.java
    └─ Processor B xử lý annotation khác đã được giao
Round 2: GeneratedDto.java có @DtoMarker
    └─ Processor C xử lý @DtoMarker (nếu được phát hiện/chọn)
Final round
    └─ Không còn round mới để xử lý source được tạo ở đây
```

Cần chú ý:

- `return true` ảnh hưởng **việc những processor sau có thể tiếp tục được giao cùng annotation type trong round đó**.
- Processor chỉ hỗ trợ một loại annotation cụ thể không nên giả định sẽ được gọi ở mọi round với mọi root, đặc biệt khi không có annotation tương ứng hoặc processor không được chọn.
- `@SupportedAnnotationTypes("*")` khai báo khả năng nhận mọi loại annotation, có thể khiến processor được xem xét ở nhiều tình huống. Nếu processor chỉ để kiểm chứng `@DtoMarker`, nên khai báo đúng annotation được hỗ trợ thay vì `"*"`.
- Output của processor A có thể trở thành input cho B/C ở round kế tiếp nếu chứa loại annotation tương ứng.

Việc `-processor X` chỉ định một processor cụ thể trong ví dụ làm kết quả dễ theo dõi; dự án thực tế có nhiều processor có thể có log theo thứ tự khác nhau. Không dùng số vòng cố định trong test tổng quát khi nhiều generator phối hợp, trừ khi bạn kiểm soát toàn bộ fixture.

## 13. Hỗ trợ phiên bản Java và tùy chọn processor

`@SupportedSourceVersion(SourceVersion.RELEASE_17)` khai báo mức ngôn ngữ mà processor hỗ trợ. Với dự án dùng Java phiên bản cao hơn, có thể cần cập nhật version khai báo hoặc override `getSupportedSourceVersion()` phù hợp. Không nên giả định một processor nhắm Java 17 có thể xử lý cú pháp tương lai mà không thay đổi.

Muốn nhận options từ `javac`, khai báo chúng bằng `@SupportedOptions(...)` hoặc override API tương ứng; khi chạy compiler truyền `-Akey=value`. Trong `init`, truy cập:

```java
String mode = processingEnv.getOptions().get("mode");
```

Đây là snippet dùng trong processor sau khi môi trường đã được khởi tạo. Đừng dùng system properties hoặc đọc file tùy tiện nếu compiler đã cung cấp options được quản lý rõ ràng.

Với service discovery, processor phải được đóng gói và có tên chuẩn đúng; khi dùng modules, kiểm tra cơ chế khai báo service provider và `--processor-module-path`. Cách tổ chức build, classloader và việc lựa chọn processor là **phụ thuộc môi trường biên dịch**, nhưng hợp đồng `init`/`process`/`RoundEnvironment` thuộc API Java.

## 14. Các lỗi hiểu sai phổ biến

| Nhầm lẫn | Giải thích đúng |
| --- | --- |
| `init` được gọi trước mỗi round | **Không**: `init` chuẩn bị instance processor trước các lần `process` của lượt xử lý. |
| `process` chỉ được gọi một lần | **Không**: có thể được gọi qua nhiều round; final round cũng có thể gọi `process`. |
| `annotations` là các annotation object runtime | **Không**: tập `TypeElement` đại diện **annotation types** được giao cho processor. |
| `process(...)` trả `true` tức build thành công | **Không**: đó là claim loại annotation; báo lỗi bằng `Messager`. |
| Source sinh ra được processor xử lý lại ngay trong cùng round | Thông thường **không**: compiler đưa file mới sang round tiếp theo. |
| `getRootElements()` luôn chứa toàn bộ source ban đầu | **Không**: phản ánh root của vòng hiện tại, có thể là generated source mới. |
| `annotations.isEmpty()` có nghĩa `processingOver()` | **Không**: dùng cờ chính thức `roundEnv.processingOver()`. |
| Có thể sinh thêm Java source trong final round để mở thêm round | **Không**: final round không mở thêm vòng xử lý annotation. |
| Gọi `createSourceFile` trùng tên qua hai round thì ghi đè an toàn | **Không**: `Filer` từ chối tạo lại output cùng tên trong một run. |
| Chỉ cần `return false` khi có cấu hình sai | **Không**: phải phát `ERROR` nếu muốn compiler báo lỗi. |
| `errorRaised()` báo ngay mọi lỗi vừa phát ở round này | **Không**: nó phản ánh lỗi ở vòng xử lý trước. |
| Annotation `SOURCE` không thể được annotation processor đọc | **Sai**: annotation processing là hoạt động lúc biên dịch; marker `SOURCE` là trường hợp bình thường. |

## 15. Tự kiểm tra kiến thức

Giả sử một processor nhận annotation `@Model`, mỗi lần xử lý nó sinh một file Java mới có `@Model` trong hai vòng đầu, rồi không sinh thêm. Không có lỗi biên dịch.

1. `init()` được gọi mấy lần cho cùng processor instance? **Một lần**.
2. `process()` có thể được gọi mấy lần? **Nhiều lần**: các vòng có source mới và một final round theo cơ chế xử lý.
3. Khi nào biết chính thức rằng đang ở vòng cuối? **`roundEnv.processingOver()` là `true`**.
4. `roundEnv.getRootElements()` là danh sách mọi class trong project? **Không**; chỉ các root liên quan **vòng hiện tại**.
5. `return true` có đồng nghĩa “không có lỗi”? **Không**; nó claim annotation types được giao.
6. Một class `.java` tạo bằng `Filer` trong round 1 thường được xử lý lúc nào? **Round sau**, không phải một recursive call ngay lập tức bên trong `process` hiện tại.
7. Làm sao tránh tạo lại cùng file trong mọi round? **Lưu trạng thái instance**, chẳng hạn set tên output đã sinh hoặc cờ `generated`.
8. Nếu cần báo cấu hình annotation không hợp lệ? **`Messager.printMessage(ERROR, ...)`**, có thể truyền `Element` để compiler trỏ đúng khai báo.
9. Nên gọi `init(processingEnv)` thủ công từ code ứng dụng không? **Không**; compiler điều phối vòng đời.
10. Có nên coi mọi processor được gọi cùng số vòng và cùng tập annotation types không? **Không**; lựa chọn processor, claim và output mới ảnh hưởng lịch trình.

Để nắm bản chất, hãy xem `init` là **chuẩn bị phiên xử lý**, `process` là **công việc của một vòng**, `Filer` là cách **tạo dữ liệu đầu vào cho các vòng tiếp theo**, còn `processingOver` là **tín hiệu kết thúc**. Một processor đúng nên đọc element có chọn lọc, sinh output tối đa một lần cho mỗi mục tiêu và báo lỗi qua API compiler.

## Tài liệu tham khảo

- [Java SE 17 — `Processor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html): hợp đồng khởi tạo, claim, vòng xử lý và supported annotation types.
- [Java SE 17 — `AbstractProcessor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): tiện ích và hành vi `init`.
- [Java SE 17 — `RoundEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): `processingOver`, `errorRaised`, root elements, tìm element theo annotation.
- [Java SE 17 — `Filer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html): các quy tắc tạo file mới giữa các round.
