# Annotation processing: xử lý mã ở vòng tiếp theo và tránh sinh trùng tệp

Trong Java, annotation processor có thể tạo thêm mã nguồn bằng `Filer.createSourceFile(...)`. Mã nguồn vừa tạo **không được xem là một class runtime có sẵn ngay trong callback hiện tại**: công cụ biên dịch đưa những source/class file được tạo và **đóng thành công** vào **vòng annotation processing tiếp theo** để phân tích. Vì vậy, processor cần hiểu vòng đời nhiều vòng (*rounds*) và đảm bảo mỗi tên tệp/kiểu đầu ra chỉ được sinh **một lần trong một lần chạy compiler**.

Hai mục tiêu phải thực hiện cùng lúc:

1. **Nhận diện và xử lý phần tử từ mã sinh trong vòng kế tiếp** khi quy tắc nghiệp vụ yêu cầu; không cố lấy những declaration vừa ghi như thể chúng đã được phân tích trong vòng đang chạy.
2. **Tránh tạo trùng cùng một tệp hoặc tên kiểu** qua nhiều round, nhiều phần tử nguồn hay nhiều processor; xử lý `FilerException` thành diagnostic rõ ràng thay vì âm thầm bỏ qua.

Ví dụ điển hình: vòng 1 đọc `@Emit` trên `Seed` rồi sinh `GeneratedPeer.java`. Vì tệp sinh cũng được gắn `@Emit`, processor nhìn thấy `GeneratedPeer` trong vòng 2 nhưng **không tiếp tục sinh lại cùng tên tệp**. Vòng cuối báo `processingOver() == true`.

## 1. Mỗi lần biên dịch có nhiều round

`javax.annotation.processing.Processor` định nghĩa cơ chế xử lý annotation theo một chuỗi round. Với mỗi round, môi trường `RoundEnvironment` mô tả những phần tử thuộc lượt ấy. Khi một round tạo source/class file hợp lệ, các khai báo được sinh có thể trở thành đầu vào cho lượt sau.

Mô hình thường gặp:

```text
Nguồn ban đầu: @Emit class Seed
          |
          v
Round 1: processor thấy Seed
          |
          | Filer.createSourceFile("demo.GeneratedPeer", Seed)
          | ghi nội dung rồi close Writer
          v
Round 2: javac phân tích GeneratedPeer
          | processor có thể thấy @Emit trên GeneratedPeer
          | không tạo demo.GeneratedPeer lần thứ hai
          v
Final round: processingOver() == true
          |
          v
Hoàn tất công việc annotation processing và biên dịch
```

**Các điểm quan trọng:**

- Những đầu vào gốc có thể được xem là kết quả của một **round 0 giả định**; phần tử của chúng được xử lý trong round thực tế đầu tiên.
- `Processor.process(...)` có thể được gọi nhiều lần cho **cùng một đối tượng processor** trong một compilation run. Vì vậy, field instance giữ trạng thái có thể dùng để tránh sinh lại cùng tên **trong run ấy**.
- Công cụ có thể gọi processor trong những round sau, kể cả khi tập annotation được chuyển vào `process` rỗng; không nên suy luận round kết thúc chỉ từ `annotations.isEmpty()`.
- Tập root elements của một round phản ánh các phần tử đầu vào của round đó, bao gồm những khai báo được sinh ở round trước. Không phải mọi kiểu đã từng thấy đều xuất hiện lại như root ở từng round.
- Tên kiểu được sinh không nhất thiết phải được gắn cùng annotation; processor cần chọn rõ điều kiện nào khiến mã sinh được xử lý tiếp.

Theo hợp đồng `Filer`, source/class files được tạo bằng các phương thức tương ứng được công cụ xem xét cho round sau **khi `Writer` hoặc `OutputStream` đã được đóng**. Đừng giữ stream mở qua các round rồi chờ file được phân tích.

## 2. RoundEnvironment cung cấp các tín hiệu nào?

Các API chính:

| API | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| `getElementsAnnotatedWith(Emit.class)` | Tìm các phần tử mang annotation trong phạm vi round | Chọn chính xác phần tử đang cần xử lý |
| `getRootElements()` | Root elements của round | Quan sát các kiểu được tạo từ round trước |
| `processingOver()` | Đang ở round cuối, mã sinh ở round này không được xử lý tiếp | Dừng sinh mã mới, tổng kết/trả diagnostic thích hợp |
| `errorRaised()` | Cho biết có lỗi được báo trong **round trước đó** | Cân nhắc bỏ sinh thêm khi compilation đã có lỗi |
| `getElementsAnnotatedWith(TypeElement)` | Tra theo mô hình ngôn ngữ, không nhất thiết phải load annotation runtime | Hữu ích khi xử lý khai báo annotation theo compiler model |

Ví dụ cấu trúc callback:

```java
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment roundEnv) {
    if (roundEnv.processingOver()) {
        // Round cuối: không còn vòng tiếp để xử lý tệp mới.
        return true;
    }
    if (roundEnv.errorRaised()) {
        // Có lỗi đã được phát trong vòng ngay trước đó.
        // Quyết định có dừng sinh hay vẫn tổng hợp diagnostic.
    }
    // Xử lý các phần tử thuộc round hiện tại.
    return true;
}
```

Đây là **khung minh họa**, cần nằm trong class processor cùng các import thích hợp. `errorRaised()` **không** có nghĩa rằng một lỗi được phát ngay trong callback hiện tại sẽ tự làm nó đổi thành `true` ở cùng round.

### Khi nào round cuối xuất hiện?

Sau những round xử lý đầu vào và những tệp mới sinh, công cụ có một round cuối mà `processingOver()` trả `true`. Khi đó, **các loại mới sinh sẽ không được subject to một round processing tiếp theo**. Đừng sinh Java source ở round cuối rồi kỳ vọng annotation của nó sẽ được xử lý. Một số tác vụ tổng kết hoặc báo cáo có thể phù hợp ở đây; nếu cần một **resource tổng hợp** như index, cũng phải tuân theo hợp đồng `Filer` và chính sách build.

Không cố điều khiển số round bằng vòng lặp Java trong `process()`. Compiler quản lý rounds; processor phản hồi các sự kiện mà compiler đưa tới.

## 3. Filer, FilerException và quy tắc tạo một lần

`ProcessingEnvironment.getFiler()` trả về `Filer`, có phương thức tạo source, class và resource:

```java
JavaFileObject source = processingEnv.getFiler()
        .createSourceFile("demo.GeneratedPeer", originatingElement);

try (Writer writer = source.openWriter()) {
    writer.write("package demo; public class GeneratedPeer {}");
}
```

Đây là **đoạn minh họa trong processor**, cần các biến/import và cách sinh tên đúng. Dạng tên truyền vào `createSourceFile` là **tên kiểu đầy đủ**, không phải một đường dẫn tùy ý như `../GeneratedPeer.java`. `Filer` tự quyết định thư mục đầu ra tương ứng từ cấu hình compiler, chẳng hạn `-s generated`.

### Quy tắc độc nhất có phạm vi một lần chạy processor

Theo API `Filer` trong Java 17:

- Một pathname chỉ được **tạo một lần trong một compilation run**; lần tạo thứ hai trong cùng run gây `FilerException`.
- Không thể tạo cả source file và class file cho cùng kiểu trong cùng run bằng các lệnh không tương thích.
- Các tệp đầu vào ban đầu được xem là đã được tạo ở **round 0**; cố tạo lại `Seed.java` từ một run đang biên dịch `Seed.java` có thể gây `FilerException`.
- Nếu tệp sinh **từ lần biên dịch trước** đã có trong thư mục output trước lần tạo đầu của run hiện tại, API mô tả rằng nội dung cũ có thể bị xóa/thay thế. Vì vậy, **không** đơn giản dùng `Files.exists(path)` trên ổ đĩa để quyết định "đã sinh trong run này".
- Không nên cố ý ghi đè những tệp ngoài quyền quản lý của processor. Hai processor tranh sinh cùng kiểu là **xung đột thiết kế**, không nên được xử lý bằng cách bỏ qua lỗi.

`FilerException` kế thừa `IOException`. Khi ghi bằng `createSourceFile`, hãy bắt lỗi và báo diagnostic có ngữ cảnh:

```java
try {
    // createSourceFile(...) và ghi nội dung.
} catch (javax.annotation.processing.FilerException ex) {
    processingEnv.getMessager().printMessage(
            javax.tools.Diagnostic.Kind.ERROR,
            "Trùng tên tệp sinh: " + ex.getMessage());
} catch (java.io.IOException ex) {
    processingEnv.getMessager().printMessage(
            javax.tools.Diagnostic.Kind.ERROR,
            "Không ghi được mã nguồn: " + ex.getMessage());
}
```

Đây là **đoạn minh họa** cần đặt bên trong processor và cung cấp logic `try` thực. Không nên bắt `FilerException` rồi **coi đó là thành công** nếu không chắc một phần tử tương đương đã được tạo hợp lệ: nội dung có thể không trùng, hoặc có hai processor đang ghi không tương thích.

### Originating elements giúp gì?

Trong lời gọi:

```java
processingEnv.getFiler()
        .createSourceFile("demo.GeneratedPeer", sourceElement);
```

`sourceElement` là khai báo được xử lý, ví dụ `TypeElement` cho `Seed`. Nó là **originating element**, gợi ý liên hệ nguyên nhân giữa nguồn đầu vào và file được sinh. Công cụ build incremental có thể sử dụng thông tin này để xác định khi nào cần xử lý lại hoặc xóa sản phẩm cũ; không phải mọi công cụ bắt buộc tận dụng gợi ý đó.

**Không nhầm:** truyền originating element **không** cho phép tạo trùng cùng file. Tính duy nhất của output name vẫn phải được bảo đảm.

## 4. Ba lớp phòng vệ để không tạo trùng

Một processor sinh mã đáng tin thường phối hợp nhiều điều kiện:

1. **Chọn đúng nguồn kích hoạt.** Ví dụ chỉ sinh `GeneratedPeer` nếu xử lý `Seed`, không sinh vì mọi class mang `@Emit`.
2. **Ghi nhận tên đầy đủ đã yêu cầu tạo trong run.** Dùng `Set<String> generatedNames`, với khóa như `"demo.GeneratedPeer"`; không chỉ dùng `"GeneratedPeer"` vì tên ngắn có thể trùng giữa nhiều package.
3. **Để Filer xác nhận tính duy nhất cuối cùng.** Vẫn phải xử lý `FilerException` vì có thể có nguồn đầu vào cùng tên, processor khác, hoặc đường đi không hợp lệ. Set riêng chỉ phòng chống **các lần gọi trùng trong processor của bạn**.

Ví dụ nguyên tắc:

```java
String generatedType = "demo.GeneratedPeer";

if (generatedNames.add(generatedType)) {
    JavaFileObject file = filer.createSourceFile(generatedType, origin);
    // try-with-resources và ghi file ở đây.
}
```

Đây là **mã minh họa**, cần `generatedNames`, `filer`, `origin` được khai báo. `Set.add(...)` trả `true` lần đầu; các round sau trả `false` nếu cùng instance processor còn giữ trạng thái.

**Một Set không đủ giải quyết mọi vấn đề:**

- Nó không tự phối hợp với processor khác trong build.
- Nó chỉ sống trong compilation run và classloader/processor instance tương ứng; build sau bắt đầu lại từ đầu.
- Nếu thêm khóa trước khi tạo file mà `Filer` thất bại, không được đánh dấu tác vụ "thành công" rồi im lặng: phải báo lỗi hoặc áp dụng chính sách phục hồi rõ ràng.
- Nếu muốn sinh **một kiểu cho mỗi nguồn**, khóa cần là tên đầu ra đã suy ra từ mỗi phần tử, không phải một hằng duy nhất.
- Nếu hai nguồn khác nhau tình cờ tạo cùng tên đầu ra, cần xác định quy tắc va chạm, không âm thầm chọn một nguồn bất kỳ.

## 5. Ví dụ Java 17+ độc lập: Round 1 → Round 2 → round cuối

Ví dụ này có **ba tệp Java đầu vào**, đặt trong thư mục `demo/`, và một source file `demo/GeneratedPeer.java` được **processor tự sinh**. Không tự tạo trước file GeneratedPeer.

### Tệp 1: demo/Emit.java

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface Emit {}
```

Annotation `@Emit` là tín hiệu cho processor. `RetentionPolicy.SOURCE` phù hợp vì chỉ cần dùng lúc biên dịch; không phải giữ annotation tới runtime.

### Tệp 2: demo/RoundProcessor.java

```java
package demo;

import java.io.IOException;
import java.io.Writer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.Emit")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class RoundProcessor extends AbstractProcessor {
    private final Set<String> written = new HashSet<>();
    private int round;

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment env) {
        round++;

        if (env.processingOver()) {
            System.out.println("round=" + round + " processingOver=true");
            return true;
        }

        List<String> found = new ArrayList<>();

        for (Element e : env.getElementsAnnotatedWith(Emit.class)) {
            found.add(e.getSimpleName().toString());

            if (e.getSimpleName().contentEquals("Seed")
                    && written.add("demo.GeneratedPeer")) {
                try {
                    JavaFileObject source = processingEnv.getFiler()
                            .createSourceFile("demo.GeneratedPeer", e);

                    try (Writer out = source.openWriter()) {
                        out.write("package demo;\n"
                                + "@Emit public class GeneratedPeer {\n"
                                + "  public static String message() { return \"generated\"; }\n"
                                + "}\n");
                    }
                } catch (IOException ex) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR, ex.toString(), e);
                }
            }
        }

        Collections.sort(found);
        System.out.println("round=" + round
                + " seen=" + String.join(",", found));
        return true;
    }
}
```

Giải thích từng phần:

- `@SupportedAnnotationTypes("demo.Emit")` yêu cầu processor nhận diện annotation `demo.Emit`; việc dùng tên đầy đủ tránh nhập nhằng package.
- `@SupportedSourceVersion(SourceVersion.RELEASE_17)` mô tả phiên bản ngôn ngữ mà processor hỗ trợ. Ví dụ biên dịch với `--release 17` để tương thích.
- `written` là `HashSet` được lưu trong **instance processor** qua các round của lần biên dịch.
- `round` tăng mỗi lần processor được gọi; dùng **chỉ để minh họa thứ tự**, không nên dùng con số round làm điều kiện định danh file.
- `if (env.processingOver())` dừng sinh mã ở round cuối.
- Chỉ `Seed` kích hoạt sinh kiểu `demo.GeneratedPeer`. Khi `GeneratedPeer` mang `@Emit` xuất hiện ở vòng sau, nó vẫn được quan sát/in log nhưng **không tiếp tục tạo file**.
- `written.add(...)` ngăn processor yêu cầu `Filer` tạo lại đúng tên ấy ở các lượt sau trong cùng run.
- `createSourceFile("demo.GeneratedPeer", e)` gắn `Seed` làm originating element.
- `try (Writer out = ...)` **đóng file đúng thời điểm** để công cụ đưa nguồn đã sinh vào round sau.
- `Diagnostic.Kind.ERROR` đảm bảo lỗi sinh mã không bị nuốt đi; với hệ thống thật nên bổ sung lý do va chạm/tên file trong thông báo.

Ví dụ này cố ý chỉ sinh **một file** và kiểm tra tên nguồn bằng `getSimpleName()` để dễ quan sát. Khi áp dụng thật, phải dùng `TypeElement.getQualifiedName()` hoặc mô hình package cùng tên đầy đủ, tránh nhầm hai class cùng tên ngắn ở các package khác nhau.

### Tệp 3: demo/Seed.java

```java
package demo;

@Emit
public class Seed {
    public static void main(String[] args) {
        System.out.println(GeneratedPeer.message());
    }
}
```

Điểm đáng chú ý: `Seed` **tham chiếu `GeneratedPeer` khi mã đó chưa có ở source đầu vào**. `javac` và processor làm việc cùng lần biên dịch có thể giải quyết tham chiếu ấy sau khi source `GeneratedPeer.java` được tạo và phân tích ở round tiếp.

### Biên dịch và chạy

Từ thư mục gốc chứa `demo/`:

```bash
javac --release 17 -encoding UTF-8 -d out demo/Emit.java demo/RoundProcessor.java
javac --release 17 -encoding UTF-8 -cp out -processorpath out -processor demo.RoundProcessor -s generated -d out demo/Seed.java
java -cp out demo.Seed
```

**Với lệnh trên**, cần dùng thư mục output `out` và `generated` có thể ghi được; `javac` sẽ tạo các thư mục/package output cần thiết theo cấu hình. Nếu công cụ hoặc môi trường yêu cầu, hãy tạo thư mục gốc `out` và `generated` trước.

Lệnh thứ nhất tạo `Emit.class` và `RoundProcessor.class` để compiler có thể load processor. Lệnh thứ hai xử lý `Seed.java` bằng processor, sinh `generated/demo/GeneratedPeer.java` rồi biên dịch cả các source phù hợp thành class files trong `out`. Lệnh cuối cùng chạy `Seed.main`.

Trong môi trường Java 17+ đã kiểm chứng, **stdout từ lệnh javac thứ hai** là:

```text
round=1 seen=Seed
round=2 seen=GeneratedPeer
round=3 processingOver=true
```

**Stdout của lệnh java** là:

```text
generated
```

Các dòng `round=...` đến từ `System.out.println` trong processor; chúng **không phải** stdout của chương trình runtime `Seed`. Khi bật log compiler hoặc dùng JDK khác, `javac` có thể in diagnostic bổ sung; đầu ra trên mô tả lần chạy sạch, có đúng ba source đầu vào và một processor này.

### Vì sao generated code được xử lý ở vòng 2?

File sinh có chứa:

```java
package demo;

@Emit
public class GeneratedPeer {
    public static String message() {
        return "generated";
    }
}
```

Đây là **nội dung tương đương** với chuỗi mà processor đã ghi, được trình bày lại để dễ đọc; **không tạo file này bằng tay trước lần biên dịch thử**.

Vòng 1 thấy `Seed`, tạo và đóng file. Vòng 2 thấy `GeneratedPeer` như một kiểu mới mang `@Emit`. Lời gọi `getElementsAnnotatedWith(Emit.class)` trả về các phần tử phù hợp của **round đó**, không tự bắt đầu phân tích một bản sao của `Seed`. Cơ chế guard khiến `GeneratedPeer` không kích hoạt tạo trùng `demo.GeneratedPeer`.

Nếu bỏ cả điều kiện tên `Seed` lẫn Set `written` mà cố tạo `demo.GeneratedPeer` mỗi lần thấy `@Emit`, vòng 2 sẽ yêu cầu tạo cùng pathname lần nữa. `Filer` phải từ chối theo quy tắc của nó và phát sinh `FilerException`.

## 6. Khác nhau giữa “file đã sinh” và “kiểu đã được xử lý”

Một mã nguồn mới thường đi qua các trạng thái:

```text
Chưa được tạo
   |
   v
Đã gọi createSourceFile
   |
   v
Writer mở, nội dung đang được ghi
   |
   v
Writer đóng thành công
   |
   v
Compiler nhận file để phân tích ở round sau
   |
   v
Các Element/TypeMirror mới có thể xuất hiện
   |
   v
Tạo class file theo quy trình biên dịch
```

Cần tránh một số giả định:

- `createSourceFile(...)` **trả JavaFileObject**, không trả `TypeElement` cho class mới. Không ép cast hoặc gọi `Class.forName()` ngay trong callback đang ghi.
- Đừng tạo một Java source rồi tự đưa nó vào `roundEnv.getRootElements()` trong cùng round; tập root do công cụ cung cấp.
- Việc sinh source không bảo đảm compilation thành công nếu source có lỗi cú pháp, tên public class không khớp hoặc dependency chưa được giải quyết.
- `processingOver()==true` nghĩa là **không có round tiếp để xử lý kiểu mới tạo**, không có nghĩa “mọi output của build chắc chắn đã thành công”.
- Với `-proc:only`, compiler chỉ thực hiện annotation processing; source có thể được sinh nhưng bạn không nên kỳ vọng class files runtime của ứng dụng được tạo giống lệnh biên dịch thông thường.

Cũng cần phân biệt **các round trong cùng một compilation run** với **các lần build khác nhau**. Set `written` trong processor giúp ngăn trùng trong một run; chạy `javac` lần sau tạo một processor instance mới và một trạng thái mới.

## 7. Khi nhiều nguồn cùng sinh một tên tệp

Trong ví dụ gọn, chỉ có một `Seed`. Nhưng processor thật có thể gặp:

```java
@GenerateAdapter
class Alpha {}

@GenerateAdapter
class Beta {}
```

Đây là **đoạn minh họa**; `GenerateAdapter` cần được khai báo. Nếu cả `Alpha` lẫn `Beta` cùng sinh kiểu cố định `example.Adapter`, một Set chỉ ngăn gọi `Filer` lần thứ hai, nhưng lại khiến một trong hai nguồn **không có mã tương ứng**. Đó là **xung đột thiết kế tên** chứ không phải thành công.

Một chính sách phù hợp thường là:

- Sinh `example.AlphaAdapter` từ `Alpha` và `example.BetaAdapter` từ `Beta`, với tên ổn định theo fully qualified name.
- Nếu có trường hợp hai input ra cùng tên, phát **diagnostic ERROR** giải thích hai nguồn liên quan thay vì âm thầm bỏ qua.
- Nếu chủ đích sinh **một registry chung**, thu thập và gộp dữ liệu theo hợp đồng nhất quán, chọn đúng thời điểm sinh **một lần**, nhưng nhớ rằng các phần tử được sinh về sau có thể thay đổi tập đầu vào. Cần thiết kế rõ có một hay nhiều pha sinh; không tùy tiện chờ tới final round rồi mới sinh Java source sẽ cần round kế tiếp.
- Đính kèm originating elements hợp lệ cho những source ảnh hưởng trực tiếp đến output để hỗ trợ cơ chế incremental của công cụ build.

Không giả định `Set<Element>` hay `HashSet<String>` tự đảm bảo xử lý đúng trường hợp hai processor khác nhau cùng phát output. `Filer` mới là bộ phận kiểm tra ranh giới ghi file cuối cùng trong compilation run.

## 8. Lỗi thường gặp và cách sửa

### Lỗi 1 — Sinh file giống nhau ở mỗi round

Mẫu sai:

```java
@Override
public boolean process(Set<? extends TypeElement> anns,
                       RoundEnvironment env) {
    // SAI: gọi mỗi round mà không xét trạng thái/đầu vào.
    filer.createSourceFile("demo.GeneratedPeer");
    return true;
}
```

Đoạn **cố ý sai** còn thiếu biến `filer`, import và xử lý `IOException`. Vấn đề cốt lõi: lần thứ hai trong cùng run có thể tạo trùng cùng tên, dẫn đến `FilerException`. Cần chỉ sinh khi có nguồn hợp lệ và chưa yêu cầu tạo kiểu đó.

### Lỗi 2 — Sinh Java source ở final round

```java
if (roundEnv.processingOver()) {
    // Sai nếu mong class này còn được processor xử lý trong round sau.
    processingEnv.getFiler().createSourceFile("demo.LateClass");
}
```

Đây là **mã minh họa sai về vòng đời**, đồng thời chưa xử lý checked exception. Final round không dẫn tới một round annotation processing kế tiếp cho `LateClass`. Muốn class được xử lý tiếp, hãy sinh trong round còn hoạt động, theo chính sách đã thiết kế.

### Lỗi 3 — Quên đóng Writer

```java
JavaFileObject file = filer.createSourceFile("demo.Thing", origin);
Writer writer = file.openWriter();
writer.write(sourceCode);
// Thiếu writer.close(): KHÔNG làm thế.
```

Đây là **đoạn minh họa sai**, các biến phải được định nghĩa trong processor thật. Tránh resource leak hoặc file chưa hoàn tất; dùng `try (Writer writer = file.openWriter()) { ... }`. Hợp đồng `Filer` gắn việc chuyển file sang round sau với thao tác đóng stream.

### Lỗi 4 — Nuốt FilerException rồi tiếp tục như đã thành công

```java
try {
    // Sinh file.
} catch (javax.annotation.processing.FilerException ignored) {
    // Sai: có thể che xung đột với input hoặc processor khác.
}
```

Đoạn trên **cố ý minh họa anti-pattern**, không phải quy tắc cần áp dụng. Hãy dùng `Messager` phát diagnostic và giải quyết nguyên nhân.

### Lỗi 5 — Xem nguồn cũ trên đĩa là file đã được tạo trong run

Một file trong `build/generated` có thể là sản phẩm từ run trước. Theo API `Filer`, lần tạo đầu của run có thể thay thế nó. Ngược lại, một input đang được compiler đọc được xem như đã có từ round 0. **Quy tắc “một lần trong run” không đồng nghĩa “nếu file tồn tại trên ổ đĩa thì luôn bỏ qua”.**

### Lỗi 6 — Trộn các tập phần tử từ nhiều round mà không kiểm soát

Nếu processor cần toàn bộ thông tin của nhiều round, hãy ghi nhận theo khóa ổn định và cập nhật trạng thái một cách có chủ đích. Đừng suy ra “`getElementsAnnotatedWith` vòng này rỗng” tức là toàn bộ compilation không có annotation. Ngược lại, đừng vô điều kiện xử lý lại mọi phần tử đã thấy trong các round cũ.

### Lỗi 7 — Dùng tên đơn thay vì tên đầy đủ

`getSimpleName()` cho giá trị `User` với cả `a.User` và `b.User`. Nếu processor sinh `UserAdapter` vào cùng package đích, xung đột có thể xảy ra. Hãy lưu tên đủ package/module thích hợp của output và phân tích duplicate trước khi gọi `Filer`.

### Lỗi 8 — Tưởng return true/false là điều khiển sinh round

`process(...)` trả `true` để **claim các annotation types mà processor đã xử lý**, ảnh hưởng đến processor khác có còn được mời xử lý những annotation ấy hay không. Trả `false` nghĩa là **không claim**. Đây **không** phải công tắc “tiếp tục hay kết thúc các round”; rounds mới do tool quyết định dựa trên processing và các file sinh hợp lệ.

### Lỗi 9 — Giả định mã sinh chắc chắn biên dịch

`Filer` ghi Java source, nhưng không tự kiểm tra hợp đồng của mã Java do bạn tự tạo. Hãy test output: package declaration, tên public class, escape trong chuỗi, encoding, import và các dependency. Một file đã đóng vẫn có thể chứa source lỗi.

## 9. Cách kiểm chứng vòng xử lý với javac

Dùng chính bộ ba tệp ở phần 5 trong một thư mục thử nghiệm sạch:

1. Chạy lệnh biên dịch `Emit.java` và `RoundProcessor.java` trước để processor đã có bytecode.
2. Chạy lệnh biên dịch `Seed.java` với `-processor demo.RoundProcessor`. `-processorpath out` cho biết nơi tải processor; `-cp out` cho phép code ứng dụng và compiler nhận kiểu `demo.Emit`.
3. Kiểm tra ba dòng log round; kết quả mong đợi: `Seed`, `GeneratedPeer`, rồi final.
4. Kiểm tra `generated/demo/GeneratedPeer.java` chỉ chứa một khai báo class tương ứng.
5. Chạy `java -cp out demo.Seed`; chương trình runtime in `generated`.
6. Nếu muốn xem chi tiết round do `javac` báo, thêm `-XprintRounds` vào lệnh biên dịch thứ hai. Đây là tùy chọn hỗ trợ debug của javac, không phải stdout cố định của chương trình.

Khi thử trường hợp duplicate, hãy làm trong một thư mục build riêng và kiểm tra diagnostic. Không cố đưa một lỗi duplicate vào code thực tế rồi suppress chỉ để làm compiler tiếp tục thành công.

### Checklist ngắn cho processor sản xuất

| Câu hỏi | Điều nên xác nhận |
| --- | --- |
| Có xử lý đúng round mới? | `RoundEnvironment` được đọc mỗi lần callback và loại nguồn mới được nhận ở round sau |
| Có dừng ở final round? | Không kỳ vọng source sinh trong final sẽ được xử lý tiếp |
| Có đóng output? | `Writer`/`OutputStream` dùng try-with-resources |
| Có sinh tên ổn định? | Tên đầy đủ của output suy ra xác định từ nguồn |
| Có guard qua nhiều round? | Set tên đã tạo và điều kiện input thích hợp |
| Có phát hiện xung đột nguồn? | Hai nguồn chung output không bị bỏ qua âm thầm |
| Có xử lý FilerException? | Báo diagnostic rõ ràng, không nuốt lỗi |
| Có originating elements? | Truyền các phần tử gốc phù hợp |
| Có hỗ trợ build incremental? | Kiểm tra tài liệu công cụ build và chiến lược aggregating/isolating tương ứng |
| Có test nguồn sinh? | Biên dịch sạch, chạy được, không phụ thuộc tệp cũ |

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Processor ghi `@Emit class A` vào một Java source mới trong round 1 và đóng writer. Nó thường xuất hiện ở round nào?

**Đáp án:** Ở **round kế tiếp**, thường là round 2, nếu file được sinh hợp lệ và tool tiếp tục processing.

**Câu 2.** Vì sao `Set<String> written` dùng trong processor vẫn hữu ích dù Filer đã có quy tắc một lần?

**Đáp án:** Set giúp **tránh chủ động gửi yêu cầu tạo trùng** từ chính processor ở nhiều round. `Filer` vẫn là lớp bảo vệ cuối cùng và có thể báo lỗi khi có xung đột khác.

**Câu 3.** Khi `processingOver()==true`, có nên tạo source cần được xử lý trong round sau?

**Đáp án:** Không. Final round không còn round annotation processing kế tiếp cho source đó.

**Câu 4.** Một tệp `GeneratedPeer.java` tồn tại do lần build hôm trước có đồng nghĩa processor không được sinh tệp này trong lần build hiện tại không?

**Đáp án:** Không nhất thiết. `Filer` quy định tính duy nhất theo **compilation run**, với quy tắc riêng cho tệp cũ trước lần tạo đầu và cho initial inputs.

**Câu 5.** Nếu hai class nguồn đều có cùng tên đơn `User` ở hai package, dùng `getSimpleName()` làm khóa sinh có an toàn không?

**Đáp án:** Không. Hãy dùng tên đầy đủ và tính toán output name một cách xác định.

**Câu 6.** Vì sao phải đóng `Writer` của `createSourceFile`?

**Đáp án:** Để file được ghi xong và công cụ có thể đưa nó vào xử lý ở round tiếp, theo hợp đồng `Filer`.

**Câu 7.** Trả `false` từ `process()` có yêu cầu javac tạo thêm một round không?

**Đáp án:** Không. `false` nghĩa là processor **không claim** các annotation types đã nhận, không phải tín hiệu tạo round.

**Câu 8.** `FilerException` nên được xem là lỗi gì?

**Đáp án:** Nó cho biết yêu cầu tạo file vi phạm các bảo đảm của `Filer` (đặc biệt tạo trùng tên/pathname, xung đột với input hoặc cấu hình). Cần xác định nguyên nhân và báo diagnostic; không mặc định rằng output mong muốn đã có đúng.

## Tài liệu chính thức

- [Java SE 17 — Processor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html).
- [Java SE 17 — RoundEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html).
- [Java SE 17 — Filer](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html).
- [Java SE 17 — FilerException](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/FilerException.html).
- [Java SE 17 — ProcessingEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html).
- [Java SE 17 — AbstractProcessor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html).

**Ghi nhớ:** **Tạo một lần, đóng file, xử lý ở round sau.** Cố định tên đầu ra theo nguồn, duy trì trạng thái tạo file trong run, không cố ghi Java source cần round kế tiếp ở final round và xem `FilerException` là lỗi phải chẩn đoán. Đó là nền tảng của annotation processor tạo mã ổn định.
