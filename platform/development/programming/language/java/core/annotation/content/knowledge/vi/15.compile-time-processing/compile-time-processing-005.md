# RoundEnvironment: phần tử gốc và phần tử được đánh dấu khi xử lý annotation lúc biên dịch

Khi viết **annotation processor** trong Java, điểm khó không chỉ là đọc một annotation mà còn là hiểu **phạm vi dữ liệu của từng vòng xử lý (processing round)**. Java cung cấp interface `javax.annotation.processing.RoundEnvironment` cho việc đó. Hai API rất quan trọng là:

- `roundEnv.getRootElements()` — tập các **phần tử gốc** (root elements) được đưa vào **vòng xử lý hiện tại**.
- `roundEnv.getElementsAnnotatedWith(...)` — tập các **phần tử có annotation cụ thể** thuộc phạm vi mà Java cho phép xét trong vòng hiện tại, bao gồm cả thành viên nằm trong các kiểu được bao gồm; không chỉ các phần tử gốc.

Ví dụ, một source file có class `Account` và method `validate()` được gắn `@Tracked`. `Account` là root type, nhưng `validate()` chỉ là một method nằm trong class: **`validate()` không nằm trong `getRootElements()`**. Tuy nhiên, `getElementsAnnotatedWith(Tracked.class)` có thể trả về **cả `Account` và `validate()`** nếu cả hai được đánh dấu `@Tracked`.

Một processor có thể tạo source mới trong vòng hiện tại. Source được tạo có thể trở thành root trong **vòng tiếp theo**. Vì vậy dữ liệu trả về bởi `RoundEnvironment` **không phải ảnh chụp toàn bộ dự án trong mọi thời điểm**, mà là một góc nhìn theo vòng của compilation.

## 1. Ngữ cảnh: annotation processing khác reflection runtime

Annotation processing chạy ở **giai đoạn biên dịch**, dựa trên API trong module `java.compiler`, đặc biệt:

| Thành phần | Vai trò |
|---|---|
| `Processor` / `AbstractProcessor` | Hợp đồng và lớp nền để hiện thực một annotation processor |
| `ProcessingEnvironment` | Cung cấp `Filer`, `Messager`, `Elements`, `Types` và cấu hình xử lý |
| `RoundEnvironment` | Cung cấp dữ liệu và trạng thái của **vòng hiện tại** |
| `Element` | Mô hình khai báo Java: class, method, field, parameter, package, module... |
| `TypeElement` | `Element` biểu diễn khai báo kiểu, bao gồm class/interface/annotation interface |
| `AnnotationMirror` | Mô hình một lần sử dụng annotation trong dữ liệu compiler |
| `Filer` | Tạo source, class file hoặc resource theo hợp đồng annotation processing |
| `Messager` | Phát note/warning/error tại vị trí khai báo khi compiler đang xử lý |

Đọc annotation bằng `Class.getAnnotation(...)` lúc chạy **không giống** đọc qua `Element`, `AnnotationMirror` và `RoundEnvironment`. Chẳng hạn annotation với retention `SOURCE` có thể được processor nhìn thấy trong lượt biên dịch source, dù lần sử dụng annotation đó bị loại khỏi class file và không đọc được bằng reflection runtime.

Processor thường được gọi theo mẫu:

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    // Xử lý những dữ liệu compiler cung cấp cho vòng này
    return true;
}
```

Đây là **method override trong một processor**, không phải một chương trình Java độc lập. Hai tham số khác nhau:

- `annotations`: các annotation type **được yêu cầu processor này xử lý trong vòng đó**, theo quy tắc chọn processor.
- `roundEnv`: môi trường truy vấn root, phần tử được đánh dấu và trạng thái vòng.

Không nên nhầm `annotations` với danh sách tất cả annotation mà mọi phần tử trong source dùng. Tương tự, `roundEnv.getRootElements()` không phải danh sách “mọi class đã có trên classpath”.

## 2. getRootElements(): thế nào là một phần tử gốc?

API:

```java
Set<? extends Element> roots = roundEnv.getRootElements();
```

Trả về tập các root elements phục vụ annotation processing trong **vòng đang được chạy**. Với compiler Java thông thường, root hay là các **khai báo top-level** của compilation unit, chẳng hạn:

```java
// File Order.java
@Tracked
class Order {
    @Tracked
    void validate() {}
}

class Supplier {}
```

Nếu file này nằm trong các input nguồn của vòng đầu, những root type được đưa vào thường là:

```text
Order
Supplier
```

**`validate()` không phải root:** nó là phần tử member được khai báo **bên trong** `Order`. Việc method được gắn `@Tracked` không biến nó thành root.

Một root type có thể **không được đánh dấu** bằng annotation nào. `Supplier` ở ví dụ này vẫn có thể là root. Ngược lại, một method được đánh dấu nằm bên trong root type **không biến thành root**.

Các điểm cần nhớ:

- Root là phần tử compiler đưa vào processing round, **không nhất thiết là phần tử được đánh dấu**.
- Root thường là khai báo kiểu top-level, nhưng API còn có thể bao gồm package hoặc module elements trong các hoàn cảnh tương ứng.
- Trong các vòng sau, root có thể xuất phát từ **source/class được tạo ở vòng trước**.
- `getRootElements()` trả về một `Set`; **không có hợp đồng đảm bảo thứ tự lặp**. Nếu bài toán đòi output ổn định thì phải sắp xếp tường minh.
- Không có lời hứa rằng lần gọi nào cũng có root: vòng cuối hoặc một tình huống không có dữ liệu mới có thể trả set rỗng.

Trong các dự án lớn, không nên mặc định “mỗi file là một root” hoặc “mọi class trong cùng package đều là root”. Một compilation unit có thể chứa nhiều khai báo top-level; root cũng không được suy ra đơn giản từ tên file.

## 3. getElementsAnnotatedWith(): tìm các khai báo được đánh dấu

`RoundEnvironment` có các overload quan trọng:

```java
Set<? extends Element> a = roundEnv.getElementsAnnotatedWith(Tracked.class);
Set<? extends Element> b = roundEnv.getElementsAnnotatedWith(
        trackedTypeElement);
```

Ở ví dụ trên, `trackedTypeElement` là biến kiểu `TypeElement` đại diện cho **định nghĩa annotation `Tracked`**, có thể lấy qua `Elements.getTypeElement(...)` hoặc tham số `annotations` của `process`.

Với một class có method được gắn cùng annotation:

```java
@Tracked
class Order {
    @Tracked
    void validate() {}

    void calculate() {}
}

class Supplier {}
```

Ta có thể quan sát:

| Truy vấn | Ví dụ phần tử trả về |
|---|---|
| `getRootElements()` | `Order`, `Supplier` |
| `getElementsAnnotatedWith(Tracked.class)` | `Order`, `validate()` |
| `getElementsAnnotatedWith(...)` có tìm `calculate()` không? | Không, vì method này không được đánh dấu `@Tracked` |

Điều này rất quan trọng: `getElementsAnnotatedWith` được thiết kế để **tìm element có annotation**, chứ không chỉ lọc top-level roots. API xét những phần tử được bao gồm trong round: các root type, member type lồng bên trong, và những khai báo thành viên, constructor, parameter, type parameter hoặc record component thuộc những phần tử phù hợp, theo quy tắc của Javadoc Java 17. Nó còn xét package/module elements khi thuộc phạm vi xử lý tương ứng.

**Giới hạn phạm vi:** nó không tự duyệt toàn bộ Java classpath hay mọi dependency JAR. Một type chỉ tình cờ được một root tham chiếu không tự động trở thành phần tử nằm trong tập đang xử lý. Muốn kiểm tra một kiểu ngoài phạm vi round, bạn phải chủ động tra cứu bằng các API modeling phù hợp; đừng dùng `getElementsAnnotatedWith` như một công cụ search toàn dự án.

### Có hai overload: TypeElement và Class

**Dùng `TypeElement`:**

```java
TypeElement marker = processingEnv.getElementUtils()
        .getTypeElement("org.example.Tracked");

if (marker != null) {
    Set<? extends Element> matches =
            roundEnv.getElementsAnnotatedWith(marker);
}
```

Đây là *đoạn minh họa bên trong processor*; cần các import tương ứng và một annotation thực sự mang tên `org.example.Tracked`. Thay tên đó bằng fully qualified name trong dự án. Cách này đặc biệt hữu ích khi annotation cần phân tích được cung cấp dưới dạng mô hình compiler, thay vì để code processor nạp class annotation tại runtime.

**Dùng `Class<? extends Annotation>`:**

```java
Set<? extends Element> matches =
        roundEnv.getElementsAnnotatedWith(Tracked.class);
```

Đơn giản khi processor có dependency chứa `Tracked` và class đó được nạp đúng trong môi trường chạy processor. Javadoc lưu ý mô hình runtime `Class` và mô hình type bên trong compiler có thể khác nhau trong vài tình huống classloader/môi trường xử lý. Nếu annotation class không có trong processing environment thích hợp, kết quả không nhất thiết là lỗi mà có thể là không có phần tử phù hợp. Với tooling lớn, `TypeElement`/`AnnotationMirror` thường là cách tách khỏi phụ thuộc runtime class tốt hơn.

Nếu truyền một `TypeElement` không đại diện annotation type vào overload tương ứng, API có thể ném `IllegalArgumentException`. `TypeElement` đại diện class thường không thay thế được kiểu annotation.

## 4. Các vòng xử lý: tại sao không thể coi kết quả là bất biến toàn quá trình?

Annotation processing thực hiện theo **một chuỗi vòng xử lý**. Ở vòng đầu, compiler xử lý các input ban đầu. Nếu processor tạo thêm source/class files, những phần tử mới có thể được đưa vào vòng kế tiếp. Đến vòng kết thúc, compiler gọi processor với trạng thái kết thúc.

Mô hình đơn giản:

```text
Input sources: Example.java
          |
          v
Round 1
  roots: Example, Plain
  marked: @Tracked Example, @Tracked Example.run()
  Processor tạo GeneratedTask.java
          |
          v
Round 2
  roots: GeneratedTask
  marked: @Tracked GeneratedTask
  Không sinh thêm source
          |
          v
Round 3 (final)
  processingOver = true
  roots: rỗng
  marked: rỗng
          |
          v
Annotation processing kết thúc
```

Đây là hình dung dựa trên một thí nghiệm cụ thể ở phần 5; số vòng thực tế tùy đầu vào và những file phát sinh. **Mỗi vòng có tập roots và tập annotated elements riêng**. Đừng chỉ lưu `getRootElements()` của vòng đầu rồi cho rằng nó đã bao gồm mọi class mà processor tạo sau đó.

Một processor cũng không nên tự gọi `process(...)` để tạo vòng mới; **công cụ biên dịch** quản lý vòng. Việc tạo source/class thông qua `Filer` là một trong các lý do một vòng tiếp theo được thiết lập.

## 5. Thí nghiệm Java 17 chạy được: in roots, marked và tạo vòng kế tiếp

Thí nghiệm này gồm **ba tệp nguồn đầu vào** đặt cùng một thư mục. Để các lệnh ngắn và nhìn rõ tên phần tử, ví dụ dùng *default package*. Trong dự án thực tế, hãy dùng package có tên và cấu hình fully qualified annotation type.

### File 1: Tracked.java

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.SOURCE)
@Target({ElementType.TYPE, ElementType.METHOD})
public @interface Tracked {}
```

- `@Retention(SOURCE)` cho phép annotation được nhìn thấy lúc xử lý mã nguồn, nhưng lần sử dụng `@Tracked` không được giữ trong bytecode đã build.
- `@Target({TYPE, METHOD})` cho phép đánh dấu class và method; vì thế thí nghiệm có thể chứng minh một method được đưa vào tập **annotated elements**, dù không phải root.

### File 2: RoundDemoProcessor.java

```java
import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import java.util.stream.Collectors;
import javax.annotation.processing.*;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.*;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("Tracked")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class RoundDemoProcessor extends AbstractProcessor {
    private int round = 0;
    private boolean created = false;

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment env) {
        round++;

        String roots = env.getRootElements().stream()
                .map(e -> e.getSimpleName().toString())
                .sorted().collect(Collectors.joining(","));

        String marked = env.getElementsAnnotatedWith(Tracked.class).stream()
                .map(e -> e.getKind() + ":" + e.getSimpleName())
                .sorted().collect(Collectors.joining(","));

        System.out.println("round=" + round
                + " over=" + env.processingOver()
                + " errorRaised=" + env.errorRaised());
        System.out.println("roots=[" + roots + "]");
        System.out.println("marked=[" + marked + "]");

        if (!env.processingOver() && !created) {
            created = true;
            try {
                JavaFileObject file = processingEnv.getFiler()
                        .createSourceFile("GeneratedTask");
                try (Writer writer = file.openWriter()) {
                    writer.write("@Tracked class GeneratedTask {}\n");
                }
            } catch (IOException ex) {
                throw new IllegalStateException(ex);
            }
        }
        return true;
    }
}
```

Phân tích các phần quan trọng:

1. `@SupportedAnnotationTypes("Tracked")` khai báo processor muốn xử lý annotation `Tracked`. Trong ứng dụng có package, cần dùng tên chính xác theo cơ chế khai báo các annotation type được hỗ trợ.
2. `@SupportedSourceVersion(RELEASE_17)` khai báo phiên bản source được processor hỗ trợ ở ví dụ.
3. `getRootElements()` trả tập root của **round hiện tại**. Ta lấy `getSimpleName()` để hiển thị.
4. `getElementsAnnotatedWith(Tracked.class)` trả các element có `@Tracked` trong round; `getKind()` giúp phân biệt `CLASS` với `METHOD`.
5. Cả hai tập đều được `sorted()` để **ổn định kết quả in**, vì tập `Set` không có thứ tự được bảo đảm.
6. `created` ngăn tạo `GeneratedTask.java` nhiều lần. `Filer` không phải API để ghi đi ghi lại một tên file mỗi round.
7. `createSourceFile(...)` kết hợp `openWriter()` ghi một source Java mới. Processor sinh class có `@Tracked` để chứng minh nó sẽ được tìm thấy trong round tiếp theo.
8. `return true` nghĩa là processor tuyên bố đã xử lý (*claim*) những annotation type được giao trong round theo quy tắc Java. Nó không có nghĩa mọi annotation hiện có trong toàn bộ project đã được xử lý xong, và không điều khiển có hay không một vòng tiếp theo.
9. Đoạn code chỉ in thông tin qua `System.out` để học cơ chế. Processor thực tế nên dùng `Messager` để báo diagnostic kèm source location.

### File 3: Example.java

```java
@Tracked
class Example {
    @Tracked
    void run() {}
}

class Plain {}
```

`Example` là top-level class có `@Tracked`. `run()` là method có `@Tracked`. `Plain` là top-level class **không** có annotation `Tracked`.

### Biên dịch và chạy processor

Trong thư mục chứa ba file, trước tiên biên dịch định nghĩa annotation và processor:

```bash
javac --release 17 Tracked.java RoundDemoProcessor.java
```

Sau đó gọi processor **tường minh** để xử lý source đang học:

```bash
javac --release 17 -cp . -processorpath . -processor RoundDemoProcessor Example.java
```

Output chính xác trong thí nghiệm Java 17:

```text
round=1 over=false errorRaised=false
roots=[Example,Plain]
marked=[CLASS:Example,METHOD:run]
round=2 over=false errorRaised=false
roots=[GeneratedTask]
marked=[CLASS:GeneratedTask]
round=3 over=true errorRaised=false
roots=[]
marked=[]
```

**Vì sao ba vòng?**

- **Round 1:** `Example` và `Plain` là roots ban đầu. `getElementsAnnotatedWith` thấy `Example` và method `run`, không thấy `Plain`. Processor tạo tệp `GeneratedTask.java`.
- **Round 2:** compiler đưa type mới `GeneratedTask` vào round; vì `GeneratedTask` được gắn `@Tracked`, nó có trong cả `roots` và `marked`. Processor không tạo thêm source do cờ `created` đã bật.
- **Round 3:** vòng xử lý cuối có `processingOver() == true` và không có root mới trong thí nghiệm. Lúc này `roundEnv.getRootElements()` và `getElementsAnnotatedWith(...)` đều trả tập rỗng.
- `errorRaised()` ở cả ba vòng là `false` vì không có diagnostic loại error ở những vòng trước.

Số dòng và thứ tự kết quả đã được chủ động ổn định bằng sắp xếp trong code. Tuy nhiên, một project có processor khác, các nguồn input khác hoặc nguồn phát sinh bổ sung có thể có **các vòng và tập phần tử khác**. Output trên là kết quả của chính ba file và câu lệnh minh họa.

Bài học mấu chốt: **getRootElements tìm root, getElementsAnnotatedWith tìm khai báo mang annotation; cả hai chỉ nói về round đang xử lý.**

## 6. getRootElements có phải mọi phần tử lồng bên trong không?

Không. `Element` tạo thành cấu trúc phân cấp. Từ một `TypeElement` của class, có thể lấy `getEnclosedElements()` để thấy các member được khai báo trực tiếp ở bên trong:

```java
for (Element root : roundEnv.getRootElements()) {
    System.out.println("ROOT " + root.getSimpleName());

    for (Element enclosed : root.getEnclosedElements()) {
        System.out.println("  CHILD " + enclosed.getKind()
                + " " + enclosed.getSimpleName());
    }
}
```

Đây là đoạn code **nằm trong method của processor** có biến `roundEnv` hợp lệ và import `Element`. Nó giúp duyệt **một cấp khai báo lồng**, chứ không tự đi sâu toàn bộ cây. Nếu cần đệ quy, có thể duyệt `getEnclosedElements()` hoặc sử dụng `ElementScanner` trong `javax.lang.model.util`.

Những lưu ý:

- `getRootElements()` không trả tất cả member theo dạng phẳng.
- `getEnclosedElements()` lấy các **khai báo bao trong** một element, không tự xác định chúng có annotation cần tìm.
- Với nhiệm vụ “tìm `@Tracked` trong phạm vi round”, `getElementsAnnotatedWith(Tracked.class)` thường ngắn và ít lỗi hơn tự duyệt cây bằng tay.
- Nếu yêu cầu kiểm tra mọi member hoặc quy tắc đặc biệt không chỉ dựa trên một annotation, duyệt element tree mới là cách hữu ích.

Ví dụ với class có nested class:

```java
class Container {
    @Tracked
    static class Nested {}

    @Tracked
    void run() {}
}
```

`Container` là top-level root khi source này thuộc round. `Nested` là member type; `run` là member method. Chúng **không trở thành root độc lập** chỉ vì được đánh dấu annotation. Tuy nhiên, khi nằm trong những type mà API xem là *included* trong round, chúng có thể xuất hiện trong `getElementsAnnotatedWith(Tracked.class)`.

## 7. processingOver và errorRaised: ý nghĩa khác nhau

`RoundEnvironment` cung cấp hai phép kiểm tra trạng thái:

```java
boolean over = roundEnv.processingOver();
boolean hadErrors = roundEnv.errorRaised();
```

| API | Điều thực sự trả lời |
|---|---|
| `processingOver()` | Có phải vòng này là vòng kết thúc, nghĩa là các kiểu được tạo ở vòng này sẽ **không được xử lý trong một vòng tiếp theo**? |
| `errorRaised()` | Có diagnostic dạng lỗi phát sinh trong **vòng trước** hay không? |

**Không nhầm trạng thái vòng với tình trạng lỗi.** `processingOver() == true` không có nghĩa compile thất bại. Trong thí nghiệm đã chạy, vòng cuối có `over=true` và `errorRaised=false`.

Một pattern thông thường:

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {

    if (roundEnv.processingOver()) {
        // Hoàn tất thống kê/trạng thái, không cố sinh thêm nguồn
        return true;
    }

    for (Element element
            : roundEnv.getElementsAnnotatedWith(Tracked.class)) {
        // Xử lý element được đánh dấu của vòng này
    }
    return true;
}
```

Đoạn trên là minh họa trong processor; trong ví dụ thật cần dùng tên annotation được processor hỗ trợ. Những tác vụ sinh thêm source nên được thực hiện trong vòng **chưa kết thúc**, không kỳ vọng rằng một tệp tạo ở final round còn được compiler đem sang một round mới.

`errorRaised` phản ánh trạng thái **prior round**, nên không nên diễn giải `errorRaised() == false` là cam kết toàn bộ phép biên dịch chắc chắn thành công về sau. Processor có thể dùng `Messager` để phát lỗi trong chính round hiện tại; thông tin đó sẽ ảnh hưởng tới các bước xử lý tiếp theo.

Khi có lỗi, hãy để công cụ compiler quyết định các vòng tiếp theo theo hợp đồng; đừng gắn cứng chương trình vào giả định “mọi run đều có chính xác ba round”.

## 8. Vì sao GeneratedTask không có ở getRootElements của vòng đầu?

Ở thí nghiệm, processor ghi:

```java
JavaFileObject file = processingEnv.getFiler()
        .createSourceFile("GeneratedTask");

try (Writer writer = file.openWriter()) {
    writer.write("@Tracked class GeneratedTask {}\n");
}
```

Tệp này **không phải input ban đầu của vòng đầu**. Nó được tạo khi processor đang ở Round 1, nên được compiler thu nhận để xử lý ở Round 2.

Hệ quả:

- **Round 1:** `roots=[Example,Plain]`; chưa có `GeneratedTask` trong tập root của round.
- **Round 2:** `roots=[GeneratedTask]`, vì đây là type mới được tạo bởi round trước.
- **Round 3:** không có type mới nên `roots=[]` trong thí nghiệm.

Không được hiểu `getRootElements()` là “mọi type đã từng thấy”. Nếu muốn tích lũy kết quả qua nhiều vòng, processor phải quản lý dữ liệu tổng hợp của chính nó một cách có chủ ý:

```java
private final Set<String> processedNames = new java.util.TreeSet<>();

@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    if (!roundEnv.processingOver()) {
        for (Element element
                : roundEnv.getElementsAnnotatedWith(Tracked.class)) {
            processedNames.add(element.toString());
        }
    }
    return true;
}
```

Đây là **đoạn minh họa trong processor**, không độc lập; cần import `Set`, `TypeElement`, `RoundEnvironment`, `Element`. Tập `processedNames` của instance processor có thể tích lũy tên qua rounds. Trong một implementation thật, nếu cần danh tính phân biệt overload/method cùng tên, chỉ lưu `element.toString()` có thể không đủ; hãy thiết kế khóa ổn định gồm loại element, owner/type và chữ ký khi thích hợp.

Không lưu tham chiếu tới `RoundEnvironment` hoặc `Element` để sử dụng tùy tiện ngoài vòng xử lý hay sau khi compilation kết thúc; đó là các đối tượng được cung cấp trong ngữ cảnh compiler. Thường tốt hơn là trích xuất thông tin cần thiết rồi lưu vào model riêng.

## 9. Tập annotations truyền vào process khác tập marked như thế nào?

Mỗi lần gọi:

```java
boolean process(
    Set<? extends TypeElement> annotations,
    RoundEnvironment roundEnv)
```

có **hai bộ dữ liệu trả lời hai câu hỏi**:

| Dữ liệu | Câu hỏi |
|---|---|
| `annotations` | Những **loại annotation** nào được compiler giao cho processor này xử lý trong round? |
| `roundEnv.getElementsAnnotatedWith(Tracked.class)` | Những **phần tử khai báo** nào trong phạm vi round có `@Tracked`? |

Chẳng hạn `annotations` có thể gồm `Tracked` (một `TypeElement`), còn `getElementsAnnotatedWith(Tracked.class)` có thể gồm `Example` và `run()` (hai `Element` mang annotation). Nhầm lẫn `TypeElement` biểu diễn annotation *type* với `Element` biểu diễn khai báo được *đánh dấu* dễ dẫn đến việc xử lý nhầm lớp thay vì method.

Trong một processor hỗ trợ nhiều annotation:

```java
@SupportedAnnotationTypes({
    "org.example.Command",
    "org.example.Query"
})
public class RouterProcessor extends AbstractProcessor {
    // ...
}
```

Có thể duyệt các `TypeElement` trong `annotations` rồi gọi `getElementsAnnotatedWith(annotationType)` cho từng loại, nếu điều đó đúng với thiết kế. Đây là **mẫu cấu hình minh họa**, không phải đoạn độc lập; package và hai annotation phải tồn tại thật khi triển khai.

`return true` nói processor **claim** những annotation type đã nhận. `return false` để các processor khác có cơ hội xử lý chúng theo quy tắc của compiler. Giá trị return không phải điều kiện “process thành công không có error” và cũng không bảo đảm không còn vòng xử lý mới nếu có source được tạo.

## 10. Các phần tử không phải type: method, field, parameter, constructor, record component

Trong Java, annotation có thể được đặt tại nhiều loại declaration tùy `@Target`. Một processor có thể cần xử lý đúng loại element, chẳng hạn chỉ cho phép `@Tracked` trên method.

Giả sử annotation cho phép dùng trên method:

```java
import java.lang.annotation.*;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.SOURCE)
@interface Handler {}

class PaymentService {
    @Handler
    void pay() {}
}
```

Processor có thể lọc:

```java
for (Element e : roundEnv.getElementsAnnotatedWith(Handler.class)) {
    if (e.getKind() != ElementKind.METHOD) {
        continue;
    }
    ExecutableElement method = (ExecutableElement) e;
    System.out.println(method.getSimpleName());
}
```

Đây là code minh họa trong `process`, với `ElementKind`, `ExecutableElement` và `Handler` đã import/khai báo hợp lệ. `pay()` không phải root, nhưng có thể được `getElementsAnnotatedWith` trả về vì nó là declaration được đánh dấu và nằm trong type của round.

Tương tự:

- `ElementKind.FIELD`: field declaration.
- `ElementKind.CONSTRUCTOR`: constructor declaration.
- `ElementKind.PARAMETER`: method/constructor parameter.
- `ElementKind.TYPE_PARAMETER`: declaration của type parameter.
- `ElementKind.RECORD_COMPONENT`: thành phần record (Java 17 hỗ trợ).

Không thể cast mọi `Element` thành `TypeElement`. Hãy kiểm tra `getKind()` hoặc `instanceof` và dùng interface modeling đúng: `TypeElement` cho kiểu; `ExecutableElement` cho method/constructor; `VariableElement` cho field/parameter; `RecordComponentElement` cho record component.

Một số chú thích thuộc **type-use** thay vì **declaration**. Ví dụ `List<@NonNull String>` là annotation trên một type argument; không nên mặc định mọi type-use annotation đều trở thành một `Element` riêng trong `getElementsAnnotatedWith`. Khi cần phân tích kiểu được annotate, hãy làm việc với mô hình `TypeMirror` và `AnnotationMirror` của các kiểu, không chỉ quét declarations.

## 11. Đặc điểm mở rộng: @Inherited và repeatable annotation

**Annotation có `@Inherited`:** Javadoc Java 17 nêu rõ `getElementsAnnotatedWith(...)` có thể trả phần tử được annotation **trực tiếp hoặc được kế thừa**. Vì vậy không nên định nghĩa API này thành “chỉ những dòng source có ký hiệu `@X` ngay trước declaration”. Khi cần phân biệt declared annotation và inherited behavior, phải cân nhắc luật `@Inherited` cùng mô hình compiler tương ứng.

Lưu ý `@Inherited` có phạm vi **kế thừa theo superclass của class**, không có nghĩa mọi method override hoặc interface implementation tự kế thừa annotation. Việc một type được tính là *included in round* vẫn là điều kiện của `RoundEnvironment`; `@Inherited` không làm một type ở xa trên classpath tự xuất hiện trong mọi vòng.

**Repeatable annotation:** nếu `@Tag` được khai báo `@Repeatable(Tags.class)`, có thể xuất hiện nhiều lần trên cùng declaration. `RoundEnvironment` Java 17 có API:

```java
getElementsAnnotatedWithAny(TypeElement... annotations)
getElementsAnnotatedWithAny(
    Set<Class<? extends Annotation>> annotations)
```

Hai overload này trả tập hợp các element được đánh dấu bởi **ít nhất một** annotation type được đưa vào. Javadoc chỉ rõ chúng có thể hữu ích khi xử lý annotation lặp và annotation container cùng lúc. Do đó nếu thiết kế processor phục vụ repeatable annotation, cần xem cả `Tag` và `Tags` chứ không giả định một lần tra `Tag` sẽ biểu diễn đầy đủ tất cả cấu trúc container ở mọi dạng biên dịch.

Các API “Any” dùng ngữ nghĩa **hợp của các tập element**, không trả danh sách mỗi lần xuất hiện annotation theo đúng số lần annotation được viết. Nếu muốn đọc từng instance `Tag` cùng giá trị của nó, processor còn cần dùng `getAnnotationMirrors()` hoặc API phù hợp trên element, theo cơ chế khai triển repeatable.

## 12. Ví dụ xử lý marker từ source và nguồn đã biên dịch

Nếu chỉ nhìn annotation trực tiếp trên source, processor có thể đọc một annotation retention SOURCE vì nó tồn tại trong mã nguồn đang được xử lý. Nhưng khi dự án sau này chỉ nhận **một file class/JAR đã biên dịch**, lần sử dụng annotation SOURCE không còn trong binary.

Điều đó tạo khác biệt:

| Tình huống | Điều được nhìn thấy |
|---|---|
| Biên dịch `Example.java` với `@Tracked` SOURCE và processor tương ứng | Processor có thể thấy `@Tracked` trong current round |
| Dùng `javap -v Example` sau khi biên dịch | Annotation SOURCE không được lưu trên `Example.class` |
| Project khác chỉ thêm `Example.class` vào classpath rồi chạy processor trên một file khác | Processor không thể tái dựng `@Tracked` trên `Example` từ binary |
| Processor tạo `GeneratedTask.java` với `@Tracked` trong round 1 | Compiler có thể đưa `GeneratedTask` vào round 2, processor thấy annotation SOURCE ở nguồn mới |

Chọn retention và luồng build phù hợp với nơi cần tiêu thụ annotation. `RoundEnvironment` là API compile time, nhưng nó không đảo ngược được quyết định retention nếu metadata đã bị loại khỏi binary nguồn vào.

## 13. Lỗi phổ biến khi dùng RoundEnvironment

### Lỗi 1 — Duyệt roots rồi tưởng đã có mọi annotated method

```java
for (Element element : roundEnv.getRootElements()) {
    if (element.getAnnotation(Tracked.class) != null) {
        // Phát hiện annotated root thôi
    }
}
```

Đoạn trên **không** tự tìm `@Tracked` trên `run()`. Nếu cần mọi khai báo được đánh dấu và API hỗ trợ loại đó, hãy dùng `getElementsAnnotatedWith(Tracked.class)`. Hoặc triển khai quét đệ quy đúng trên element tree nếu cần logic tùy chỉnh hơn.

### Lỗi 2 — Dùng getRootElements để dò mọi type trong dependency

API chỉ nói về roots trong processing round, không phải toàn bộ classpath. Với việc tra cứu type theo tên, dùng `Elements.getTypeElement(...)` rồi phân tích cấu trúc của type nếu tool thực sự cần.

### Lỗi 3 — Giả sử mọi vòng có cùng danh sách elements

Các vòng thay đổi khi source được sinh thêm. Processor cần xử lý **vòng hiện tại** và nếu phải tổng hợp toàn bộ thông tin thì quản lý trạng thái rõ ràng. Không được kết luận đã xử lý toàn bộ từ Round 1 chỉ vì một lần scan thành công.

### Lỗi 4 — Sinh cùng một file trong mọi vòng

```java
// Sai về quy trình nếu thực hiện lặp lại trên mỗi round:
processingEnv.getFiler().createSourceFile("GeneratedTask");
```

`Filer` không cho processor tạo lại cùng một pathname nhiều lần trong một lượt xử lý. Hãy kiểm tra cờ sinh file, loại input và điều kiện tạo, hoặc dùng quy tắc chỉ tạo khi cần.

### Lỗi 5 — Sinh mã ở processingOver=true rồi kỳ vọng có thêm vòng

`processingOver()` xác nhận vòng kết thúc; kiểu được tạo ở vòng đó **không được xử lý bởi round tiếp theo**. Dành thao tác tổng kết không yêu cầu xử lý type mới cho vòng cuối.

### Lỗi 6 — Nhầm errorRaised là “round hiện tại có lỗi hay không”

`errorRaised()` phản ánh lỗi của **round trước**. Lỗi phát sinh trong current round có thể được compiler báo sau khi processor thực hiện; không dùng false làm cam kết toàn compilation an toàn.

### Lỗi 7 — Trông chờ thứ tự Set là thứ tự source

`Set<? extends Element>` không bảo đảm một thứ tự để lưu ý nghĩa nghiệp vụ hoặc stdout. Nếu order quan trọng, sắp xếp theo khóa có ý nghĩa và kiểm tra trường hợp khai báo trùng tên.

### Lỗi 8 — Nhầm Class với TypeElement

Khi dùng overload `getElementsAnnotatedWith(Class<? extends Annotation>)`, class annotation cần hiện diện trong runtime context của processor. Khi cần linh hoạt với mô hình compiler, dùng overload `TypeElement` và tên đầy đủ của annotation, tránh phụ thuộc class loader không cần thiết.

### Lỗi 9 — Dùng mỗi getElementsAnnotatedWith để phân tích type-use annotations

Type-use metadata nằm trên những vị trí **sử dụng kiểu**, không nhất thiết trở thành declaration `Element`. Để kiểm tra `List<@NonNull String>` hoặc kiểu trả về phức tạp, hãy phân tích `TypeMirror`/`AnnotationMirror` thay vì chỉ mong tìm được một element qua marker trên type argument.

### Lỗi 10 — Coi return true là ngắt compiler hoặc bảo đảm build thành công

`return true` có ý nghĩa claim annotation types ở round theo chính sách chọn processor. Nó không làm compiler bỏ qua lỗi kiểu và không ngăn source generated kích hoạt round mới. Muốn báo một vi phạm, dùng `Messager.printMessage(Diagnostic.Kind.ERROR, ...)`.

## 14. Quy trình thiết kế processor tin cậy

Khi tạo một processor mới, có thể làm theo quy trình:

1. **Định nghĩa annotation rõ target và retention:** cần áp dụng ở class, method hay element nào? Có cần compiler đọc SOURCE không?
2. **Đăng ký annotation types được hỗ trợ:** `@SupportedAnnotationTypes(...)` hoặc override `getSupportedAnnotationTypes()`; nếu nhiều processor cùng xử lý thì xác định ý nghĩa claim.
3. **Xác định tập đầu vào:** dùng `getElementsAnnotatedWith` khi chỉ quan tâm annotated declarations, hoặc dùng roots và duyệt cây khi cần quy tắc tổng thể.
4. **Kiểm tra kind/type:** không cast vô điều kiện thành `TypeElement`. Lấy dữ liệu từ `Element`, `ExecutableElement` và `TypeMirror` tùy nhu cầu.
5. **Phân biệt rounds:** chỉ tạo file nếu cần, đảm bảo không trùng tên, không coi final round là nơi tạo source cho vòng sau.
6. **Phát lỗi đúng nơi:** dùng `Messager` để gắn diagnostic vào `Element`. Dùng `System.out` chỉ cho ví dụ quan sát và debug đơn giản.
7. **Thiết kế tích lũy thông tin nếu cần:** ví dụ index các annotated elements qua nhiều round, xử lý duplicate và output deterministic.
8. **Test cả source ban đầu và source generated:** kiểm tra Round 1, Round 2, final round, method lồng trong root, root không annotation, error và compile behavior.
9. **Tích hợp vào build đúng cách:** processor phải được discover/explicitly invoked; thêm annotation jar thôi không đảm bảo processor chạy. Với nhiều module/package, giữ đúng processor path và annotation classpath.
10. **Đo chất lượng bằng kết quả biên dịch thật:** đảm bảo mã hợp lệ qua, mã sai tạo diagnostic có ý nghĩa, file sinh ra tồn tại đúng và không lặp.

Một processor khỏe là processor hiểu rõ **các element nằm trong processing round nào** và **quy tắc annotation của mình**, thay vì đơn giản lặp khắp các roots và giả định đã duyệt hết.

## 15. Bài tập tự kiểm tra

### Bài 1 — Roots và annotated elements

```java
@Tracked
class Report {
    @Tracked void render() {}
    void save() {}
}

class Plain {}
```

Nếu source này là input của vòng đầu và `@Tracked` có target TYPE/METHOD, `getRootElements()` và `getElementsAnnotatedWith(Tracked.class)` thường chứa gì?

**Đáp án:** roots là `Report` và `Plain`; annotated elements gồm `Report` và method `render()`. `save()` không được đánh dấu nên không nằm trong tập marked.

### Bài 2 — Root type không có annotation

Tại sao `Plain` vẫn có trong roots dù không có `@Tracked`?

**Đáp án:** root được quyết định bởi dữ liệu đầu vào của processing round, không phải bởi việc có marker annotation đang tìm.

### Bài 3 — Sinh source

Processor tạo `@Tracked class GeneratedTask` ở Round 1. Loại này nằm trong roots của vòng nào?

**Đáp án:** thường là **Round 2**, vòng tiếp theo tiếp nhận nguồn được sinh. Nó chưa nằm trong roots của Round 1.

### Bài 4 — Vòng cuối

`processingOver() == true` có đồng nghĩa `errorRaised() == true` không?

**Đáp án:** không. Một vòng kết thúc bình thường có thể có `processingOver=true` và `errorRaised=false`.

### Bài 5 — TypeElement và Class

Khi annotation đang được biểu diễn bằng mô hình compiler `TypeElement` và không muốn phụ thuộc vào việc nạp runtime class trong processor, nên gọi overload nào?

**Đáp án:** `getElementsAnnotatedWith(TypeElement)`, với một `TypeElement` đúng là khai báo annotation type.

### Bài 6 — ElementKind

Processor thấy `@Tracked` trên một method; có được ép trực tiếp `(TypeElement) element` không?

**Đáp án:** không. Method là `ExecutableElement`, thường có `ElementKind.METHOD`. Cần kiểm tra loại phần tử rồi dùng interface đúng.

### Bài 7 — @Inherited

Theo Javadoc, `getElementsAnnotatedWith` có chỉ trả annotation được khai báo trực tiếp không?

**Đáp án:** không bắt buộc. Nó có thể xem annotation được kế thừa theo ngữ nghĩa Java nếu type phù hợp nằm trong round; giới hạn superclass/class của `@Inherited` vẫn áp dụng.

### Bài 8 — Chọn công cụ

Nếu muốn phát hiện một qualifier `@NonNull` trên type argument trong `List<@NonNull String>`, chỉ gọi `getElementsAnnotatedWith(NonNull.class)` có đủ không?

**Đáp án:** không nên dựa vào đó. Đây là type-use annotation; cần đọc mô hình type và các annotation mirrors ở đúng vị trí kiểu.

### Bài 9 — Set và thứ tự

Tại sao ví dụ dùng `sorted()` trước khi in roots và marked?

**Đáp án:** tập trả về là `Set` không bảo đảm thứ tự duyệt; sắp xếp giúp output của ví dụ ổn định và dễ so sánh.

### Bài 10 — Trách nhiệm của Filer

Vì sao processor có cờ `created` và kiểm tra `!env.processingOver()` trước `createSourceFile`?

**Đáp án:** tránh tạo trùng file trong nhiều rounds và tránh sinh source ở vòng không còn xử lý type mới.

## 16. Tổng kết và tài liệu tham khảo

**Ba câu cần nhớ:**

1. `getRootElements()` là **root elements của vòng hiện tại**, thường là các kiểu top-level; **không phải toàn bộ member hay toàn bộ dependency**.
2. `getElementsAnnotatedWith(...)` tìm **khai báo có annotation tương ứng trong phạm vi round**, bao gồm thành viên được đánh dấu bên trong root/nested types; có thể tính cả annotation kế thừa theo quy tắc Java.
3. `processingOver()` và `errorRaised()` thể hiện **trạng thái xử lý**, trong khi source được tạo bởi `Filer` có thể mang lại các root mới ở **vòng tiếp theo**.

Tài liệu chính thức Java SE 17:

- [RoundEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html) — hợp đồng `getRootElements`, `getElementsAnnotatedWith`, `getElementsAnnotatedWithAny`, `processingOver` và `errorRaised`.
- [Processor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html) — chuỗi rounds, lựa chọn/claim annotation type và vòng cuối.
- [AbstractProcessor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html) — lớp cơ sở để triển khai processor.
- [Filer](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html) — tạo source/class/resource file trong annotation processing, các giới hạn tạo file.
- [Element](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/Element.html) — mô hình declaration, loại và các enclosed elements.
- [javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) — `-processor` và `-processorpath` khi kích hoạt processor.
