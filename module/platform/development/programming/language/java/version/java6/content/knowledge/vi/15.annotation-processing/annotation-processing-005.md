# RoundEnvironment và các vòng xử lý trong Java Annotation Processing

## 1. Mục tiêu: hiểu vì sao một lần compile có nhiều processing rounds

Annotation processing theo chuẩn Java (JSR 269) cho phép một công cụ chạy **trong lúc biên dịch** để đọc mô hình mã nguồn, kiểm tra annotation, tạo thêm source hoặc class file, và báo diagnostics. Điều này khác hẳn với reflection của JVM sau khi chương trình đã chạy.

Một câu hỏi then chốt: nếu processor tạo ra một file Java mới, file mới đó có thể chứa annotation cần xử lý tiếp. Java giải quyết bằng một chuỗi **vòng xử lý — processing rounds**. Ở mỗi vòng, compiler cung cấp cho processor một đối tượng `RoundEnvironment` mô tả những phần tử thuộc vòng hiện tại và trạng thái xử lý.

**Mental model đúng:**

~~~text
Đầu vào ban đầu: Seed.java có @Generate(2)
             |
             v
Round 1: compiler đưa Seed vào RoundEnvironment
         processor tạo Stage1.java có @Generate(1)
             |
             v
Round 2: compiler xét Stage1.java vừa được tạo
         processor tạo Stage2.java có @Generate(0)
             |
             v
Round 3: compiler xét Stage2.java
         processor không tạo file mới
             |
             v
Final round: processingOver() == true
             |
             v
javac hoàn tất bước biên dịch các nguồn phù hợp
             |
             v
.class sẵn sàng cho ứng dụng nạp và chạy
~~~

Bài này tập trung vào **`RoundEnvironment`, cơ chế rounds và trách nhiệm của processor**. Tất cả ví dụ sử dụng các API `javax.annotation.processing`, `javax.lang.model` và `javax.tools` **vẫn được hỗ trợ ở Java hiện đại**; không dựa vào công cụ `apt` độc lập cũ. Ví dụ biên dịch tương thích **Java 17 trở lên**, với cách bật processing rõ ràng để dùng được cả trên JDK 23+.

## 2. Các đối tượng trong một tác vụ annotation processing

Một processor thường kế thừa `AbstractProcessor` và có vòng đời:

1. Compiler tìm và tạo instance processor đã được cấu hình.
2. Compiler gọi `init(ProcessingEnvironment)` **một lần** cho instance; với `AbstractProcessor`, môi trường được lưu ở `processingEnv`.
3. Compiler thực hiện lần lượt các processing rounds, có thể gọi `process(Set<? extends TypeElement>, RoundEnvironment)` nhiều lần trên **cùng processor instance**.
4. Processor truy vấn `RoundEnvironment`, dùng `Element`/`TypeMirror` để hiểu mô hình, và có thể tạo file qua `processingEnv.getFiler()`.
5. Khi không còn input cần xử lý ở vòng tiếp theo, compiler gọi **final round**; xử lý kết thúc.

| Khái niệm/API | Vai trò chính |
| --- | --- |
| `Processor` / `AbstractProcessor` | Khai báo các annotation được hỗ trợ, xử lý chúng trong nhiều vòng |
| `ProcessingEnvironment` | Dịch vụ dùng xuyên suốt tác vụ compile: `Filer`, `Messager`, `Elements`, `Types`, options |
| `RoundEnvironment` | Góc nhìn **riêng của vòng hiện tại**, không phải toàn bộ project trong mọi vòng |
| `Element`, `TypeElement` | Mô hình khai báo mã Java; không phải một instance ứng dụng hay `Class<?>` runtime |
| `Filer` | Tạo source/class/resource, phối hợp với compiler để đưa source/class mới vào rounds sau |
| `Messager` | Phát NOTE/WARNING/ERROR có gắn ngữ cảnh phần tử |
| `@SupportedAnnotationTypes` | Công bố annotation types mà processor hỗ trợ |
| `@SupportedSourceVersion` hoặc `getSupportedSourceVersion()` | Công bố phiên bản ngôn ngữ được processor hỗ trợ |

`RoundEnvironment` **không phải một biến lưu trạng thái toàn cục**. Mỗi lần `process` được gọi với thông tin của vòng đang xét. Ngược lại, field instance trong processor có thể lưu dữ liệu qua các vòng, vì cùng instance có thể được gọi lại.

## 3. Bốn API quan trọng của RoundEnvironment

`javax.annotation.processing.RoundEnvironment` cung cấp:

| Phương thức | Ý nghĩa chính xác |
| --- | --- |
| `getRootElements()` | Trả các root elements **tham gia vòng hiện tại**, gồm các top-level declarations của compilation units liên quan. Đó có thể là type, package hoặc module; không chỉ class có annotation. |
| `getElementsAnnotatedWith(SomeAnnotation.class)` | Trả các phần tử trong **phạm vi vòng hiện tại** được annotate bởi annotation được hỏi. Có thể gồm field/method/constructor/parameter/record component bên trong root types. |
| `processingOver()` | `true` khi những type tạo ở vòng hiện tại **sẽ không được xét trong một processing round kế tiếp**; dùng để nhận diện final round. |
| `errorRaised()` | `true` nếu **vòng xử lý trước đó** đã phát sinh lỗi; **không phải** trạng thái “có lỗi hay không” của chính vòng hiện tại. |

### 3.1. getRootElements() không có nghĩa “tất cả class của project”

Ở vòng đầu, tập roots thường chứa các declaration đầu vào mà tác vụ compiler đang xử lý. Khi processor sinh source mới, roots của vòng tiếp theo tương ứng với các declaration được tạo từ vòng trước đó. Một root có thể chứa nhiều member/annotation.

Ví dụ trong bài thực hành: pha compile thứ hai chỉ đưa `Seed.java` làm nguồn đầu vào nên `getRootElements()` lần lượt chứa `Seed`, `Stage1` rồi `Stage2` trong ba vòng không-final. Nếu đưa cả `Main.java` vào cùng lệnh compile ấy, round đầu có thể chứa thêm `Main`; không được lấy log một fixture làm quy luật bất biến cho mọi chương trình.

**Đừng dùng `getRootElements().isEmpty()` để suy ra chắc chắn đã đến final round.** Trạng thái kết thúc được công bố bằng `processingOver()`. Một vòng có thể không có phần tử được annotate mà processor đang quan tâm, và processor vẫn được gọi.

### 3.2. getElementsAnnotatedWith() phụ thuộc vòng

Với:

~~~java
for (Element element : round.getElementsAnnotatedWith(Generate.class)) {
    // Kiểm tra các phần tử được @Generate trong vòng này
}
~~~

đây là **đoạn minh họa nằm trong `process(...)`**, không phải chương trình độc lập.

Kết quả không phải toàn bộ các class từng được annotate trước đó. Vòng hai của ví dụ thấy `Stage1` mới sinh ra, chứ không bắt buộc lặp lại `Seed` ở vòng một. Nếu muốn tổng hợp thông tin qua nhiều vòng, processor phải **tự tích lũy trạng thái cần thiết** và giữ đủ thông tin cho đầu ra.

Hai overload thường dùng:

~~~java
round.getElementsAnnotatedWith(Generate.class);
round.getElementsAnnotatedWith(
        processingEnv.getElementUtils().getTypeElement("demo.Generate"));
~~~

Đây là các **đoạn trích**. Overload đầu nhận đối tượng `Class<? extends Annotation>` của annotation type mà processor biết rõ; overload thứ hai nhận `TypeElement` từ mô hình compiler. Nếu processor phân tích các annotation type động hoặc không muốn phụ thuộc vào việc tải annotation class, hướng `TypeElement`/`AnnotationMirror` thường phù hợp hơn.

Các phiên bản hiện đại còn có `getElementsAnnotatedWithAny(...)` để lấy hợp của nhiều loại annotation. Không cần tự diễn dịch một tập roots thành “mọi annotation ở mọi dependency”; `RoundEnvironment` giới hạn các declarations được **included in this round**.

### 3.3. processingOver() chỉ tình trạng final round

Hãy xử lý final round trước khi sinh source:

~~~java
if (round.processingOver()) {
    // Có thể hoàn tất thống kê, kiểm tra và báo diagnostics.
    return true;
}
~~~

Đây là **đoạn trong processor**. Những type được sinh trong final round **không có processing round tiếp theo để xử lý**, nên thiết kế an toàn là hoàn thành sinh các source cần vòng tiếp theo **trước final round**. Nếu muốn xuất một resource tổng hợp cuối cùng, có thể xem xét viết tài nguyên trong final round, miễn là tuân thủ các quy tắc của `Filer`, không dựa vào việc compiler xử lý annotation từ tài nguyên ấy.

Mốc “vòng cuối” không đơn giản là một số cố định như 2 hoặc 3. Số rounds phụ thuộc vào dữ liệu đầu vào, các processor đang chạy và những file được sinh ra.

### 3.4. errorRaised() báo lỗi của vòng *trước*

`round.errorRaised()` theo hợp đồng trả về `true` khi **một lỗi phát sinh ở vòng trước**. Nó không hứa sẽ trả về `true` ngay khi processor vừa gọi `Messager.printMessage(Diagnostic.Kind.ERROR, ...)` trong chính vòng hiện tại.

Ví dụ logic chẩn đoán:

~~~java
System.out.println("previous-round-error=" + round.errorRaised());
if (round.processingOver() && round.errorRaised()) {
    // Phát hiện đã có lỗi từ vòng trước;
    // không giả định kết quả build là hợp lệ.
}
~~~

Trong bài thực hành không có lỗi compile nên mọi vòng đều in `errorPrevious=false`. Đừng dùng `errorRaised() == false` như một sự đảm bảo **toàn bộ lần biên dịch** sẽ thành công; compiler còn có thể phát hiện các lỗi khác sau bước processing.

## 4. Khi nào có một vòng mới?

Theo ngữ nghĩa `Processor` và `Filer`:

1. Đầu vào ban đầu của tác vụ được coi như kết quả của một **“vòng 0” giả định**; vòng processing đầu tiên nhận chúng.
2. Processor có thể tạo Java source bằng `Filer.createSourceFile(...)` hoặc class file bằng `Filer.createClassFile(...)`.
3. Sau khi writer/output stream tương ứng được **đóng**, những file source/class mới này được công cụ xử lý xem xét ở processing round sau.
4. Các processor đã được gọi trong một vòng sẽ tiếp tục được gọi ở các vòng sau, bao gồm **final round**, kể cả khi không còn annotation type quan tâm trong vòng ấy.
5. Khi không còn source/class mới cần xét qua một vòng tiếp theo, công cụ tiến đến vòng cuối rồi kết thúc annotation processing; nếu không chọn `-proc:only`, công việc biên dịch thích hợp tiếp tục hoàn tất.

**Quan trọng:** `Filer.createResource(...)` tạo tài nguyên phụ trợ (text, JSON, service file, ...) nhưng không đồng nghĩa thêm source/class cần xử lý ở round mới. Nếu cần tiếp tục annotation processing, sinh **Java source/class** với API dành cho nó, không kỳ vọng việc ghi một file resource tự gây ra vòng mới.

### 4.1. File phải được đóng đúng thời điểm

Khi tạo file:

~~~java
try (Writer w = processingEnv.getFiler()
        .createSourceFile("demo.GeneratedType", originatingElement)
        .openWriter()) {
    w.write("package demo; public final class GeneratedType {}");
}
~~~

Đây là **đoạn minh họa trong `process`**, có biến `originatingElement` là `Element` đã nhận từ compiler. `try-with-resources` bảo đảm writer được đóng, cho công cụ biết tệp đã viết xong và có thể xét trong vòng tiếp theo.

`originatingElement` không làm file tự động có annotation; nó là thông tin xuất xứ có ích cho hệ thống build/incremental processing. Khi processor tổng hợp từ nhiều nguồn, có thể truyền nhiều originating elements phù hợp.

### 4.2. Một tên file chỉ tạo một lần trong mỗi lần chạy processing

`Filer` không cho một processor tạo lặp file cùng path/type trong cùng tác vụ processing. Gọi `createSourceFile("demo.Stage1", ...)` lần thứ hai cho cùng tên trong cùng run thường gây `FilerException`. Lỗi này có thể xuất hiện khi:

- Processor xử lý lại element cũ mà không kiểm tra trạng thái;
- Hai processor khác nhau cố tạo cùng fully-qualified type;
- Tên generated type không đủ duy nhất;
- Processor cố tạo file trùng với compilation unit đầu vào.

Đừng “sửa” bằng cách bắt `FilerException` rồi lặng lẽ bỏ qua mọi trường hợp. Nên tạo tên xác định, theo dõi thứ đã sinh và báo lỗi rõ ràng. Việc chạy **một build mới** trên artifact cũ là vấn đề khác: dọn output hoặc quản lý incremental build cho đúng để không lẫn source/class đời trước.

### 4.3. Đừng sinh mã vô hạn

Nếu processor mỗi vòng đều sinh một class mới lại có annotation khiến processor tiếp tục sinh thêm class, compiler sẽ phải xử lý nhiều vòng không cần thiết, có thể dẫn tới tiêu thụ tài nguyên và lỗi build. Thiết kế generator phải có **điều kiện dừng**: giới hạn số bước, nhận dạng đã xử lý, hoặc tạo ra type không còn annotation kích hoạt generator.

Ví dụ bên dưới dùng giá trị `@Generate(2)` rồi giảm còn `1` và `0`. Khi giá trị bằng `0`, processor không sinh file mới, nên vòng sau là final round.

## 5. Bài thực hành đầy đủ: theo dõi bốn processing rounds

Bài lab sử dụng **5 file Java** trong hai pha compile và một pha chạy. Có thể chạy trên **JDK 17+**, không cần Maven/Gradle/thư viện ngoài.

Cấu trúc:

~~~text
round-demo/
└── src/
    └── demo/
        ├── Generate.java
        ├── ChainProcessor.java
        ├── Seed.java
        └── Main.java
~~~

Bốn file mã nguồn được liệt kê dưới đây; những file `Stage1.java` và `Stage2.java` sẽ được compiler tạo về sau trong thư mục `generated`, vì thế **không viết chúng bằng tay**.

### 5.1. Định nghĩa annotation chỉ dùng lúc compile

Tệp `src/demo/Generate.java`:

~~~java
package demo;

import java.lang.annotation.*;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface Generate {
    int value();
}
~~~

`@Retention(SOURCE)` đủ cho processor truy vấn annotation trong compile, dù Java reflection runtime không thấy annotation này trong `Seed.class`. `value()` là số bước còn được phép sinh để có điểm dừng.

### 5.2. Processor ghi log mỗi round và sinh type kế tiếp

Tệp `src/demo/ChainProcessor.java`:

~~~java
package demo;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import java.util.stream.Collectors;
import javax.annotation.processing.*;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.*;

@SupportedAnnotationTypes("demo.Generate")
public final class ChainProcessor extends AbstractProcessor {
    private int roundNumber;

    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.latestSupported();
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        roundNumber++;
        String roots = round.getRootElements().stream()
                .map(e -> e.getSimpleName().toString())
                .sorted()
                .collect(Collectors.joining(","));
        if (roots.isEmpty()) roots = "none";

        System.out.println("round=" + roundNumber
                + " over=" + round.processingOver()
                + " errorPrevious=" + round.errorRaised()
                + " roots=" + roots);

        if (round.processingOver()) return true;

        for (Element e : round.getElementsAnnotatedWith(Generate.class)) {
            if (!(e instanceof TypeElement)) continue;
            int remaining = e.getAnnotation(Generate.class).value();
            if (remaining <= 0) continue;

            String name = "Stage" + (3 - remaining);
            String fqcn = "demo." + name;
            try (Writer w = processingEnv.getFiler()
                    .createSourceFile(fqcn, e).openWriter()) {
                w.write("package demo;\n"
                        + "@Generate(" + (remaining - 1) + ")\n"
                        + "public final class " + name + " {}\n");
            } catch (IOException ex) {
                throw new IllegalStateException("Cannot generate " + fqcn, ex);
            }
            System.out.println("generated=" + name);
        }
        return true;
    }
}
~~~

**Giải thích từng phần quan trọng:**

- `@SupportedAnnotationTypes("demo.Generate")` cho compiler biết loại annotation mà processor xử lý. Nó **không** tự kích hoạt processor; vẫn phải cấu hình `javac` rõ ràng.
- `getSupportedSourceVersion()` trả phiên bản mà processor hỗ trợ. Ví dụ dùng `latestSupported()` từ API chuẩn; lệnh compile sử dụng `--release 17` để giữ source/code output tương thích Java 17.
- `roundNumber` là field của **processor instance**, không phải field của `RoundEnvironment`. Vì cùng instance được gọi qua nhiều vòng, counter lần lượt tăng 1 → 4 trong lab.
- `getRootElements()` lấy danh sách roots của vòng hiện tại. `sorted()` giúp thứ tự log ổn định nếu có nhiều root; fixture này chỉ có một root ở mỗi vòng không-final.
- `if (round.processingOver()) return true;` đảm bảo processor không cố tạo file trong final round.
- `getElementsAnnotatedWith(Generate.class)` chọn các phần tử được annotate trong vòng hiện tại. `instanceof TypeElement` giới hạn generator vào khai báo kiểu, phù hợp `@Target(TYPE)`.
- `remaining = ...value()` đọc giá trị annotation trong **compiler model**; không yêu cầu nạp class `Seed` tại runtime.
- `name = "Stage" + (3 - remaining)` tạo tên `Stage1` khi `remaining=2`, và `Stage2` khi `remaining=1`. Với `remaining=0`, vòng đó không gọi `Filer`.
- `createSourceFile(fqcn, e)` tạo một Java source mới, truyền `e` làm originating element. Writer được đóng ngay trong `try-with-resources` để generated source được xét trong vòng sau.
- `return true` báo processor **claim annotation types** đang xử lý, **không** có nghĩa “compiler thành công” hoặc “kết thúc xử lý mọi rounds”.

Bài lab cố ý in ra `System.out` để dễ quan sát rounds. Trong processor production nên dùng `processingEnv.getMessager()` cho diagnostics có mức độ rõ ràng; không xây hệ thống CI dựa vào việc parse những dòng debug `System.out` như một giao diện bất biến.

### 5.3. Input duy nhất cho processor

Tệp `src/demo/Seed.java`:

~~~java
package demo;

@Generate(2)
public final class Seed {}
~~~

`Seed` kích hoạt lần sinh thứ nhất. Processor sẽ tự tạo `Stage1` có `@Generate(1)`, sau đó `Stage2` có `@Generate(0)`. Không cần khai báo trước hai lớp này.

### 5.4. Ứng dụng chạy sau khi compile hoàn tất

Tệp `src/demo/Main.java`:

~~~java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("runtime=" + Stage2.class.getName());
    }
}
~~~

`Main` chỉ dùng class `Stage2` sau khi quá trình processing và compilation đã tạo được `Stage2.class`. Việc chạy `Main` **không gọi lại processor**; compiler đã sinh và biên dịch class trước đó.

## 6. Lệnh javac chuẩn và stdout đã kiểm chứng

Từ thư mục `round-demo`, tạo hai output directories.

Trên Linux/macOS (Bash):

~~~bash
mkdir -p out generated
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out, generated | Out-Null
~~~

### Pha A — biên dịch annotation type và processor

~~~bash
javac -encoding UTF-8 --release 17 -proc:none -d out src/demo/Generate.java src/demo/ChainProcessor.java
~~~

`-proc:none` tắt annotation processing ở pha bootstrap. Pha này chỉ tạo `Generate.class` và `ChainProcessor.class` để compiler có thể dùng trong bước sau.

### Pha B — bật processor tường minh và compile Seed

~~~bash
javac -encoding UTF-8 --release 17 -cp out -processorpath out -processor demo.ChainProcessor -s generated -d out src/demo/Seed.java
~~~

Các option:

| Option | Tác dụng |
| --- | --- |
| `--release 17` | Biên dịch theo API/source/bytecode của Java 17 |
| `-cp out` | Giúp compiler resolve annotation type `demo.Generate` đã build |
| `-processorpath out` | Nơi javac tìm chính processor và dependency của processor |
| `-processor demo.ChainProcessor` | Chọn processor cụ thể và **bật annotation processing** |
| `-s generated` | Nơi lưu file `.java` do `Filer` tạo |
| `-d out` | Nơi compiler ghi các file `.class` |

Không cần service descriptor `META-INF/services/javax.annotation.processing.Processor` vì lệnh đã nêu đích danh processor bằng `-processor`. Cách cấu hình rõ ràng này cũng phù hợp với thay đổi mặc định của `javac` từ JDK 23.

### Pha C — biên dịch Main và chạy ứng dụng

~~~bash
javac -encoding UTF-8 --release 17 -proc:none -cp out -d out src/demo/Main.java
java -cp out demo.Main
~~~

Chúng ta dùng `-proc:none` ở pha C vì không cần chạy lại annotation processor khi compile `Main`. Thư mục `out` đã có `Stage2.class` từ pha B.

**Output đúng của hai lệnh ở pha B và C**, theo thứ tự:

~~~text
round=1 over=false errorPrevious=false roots=Seed
generated=Stage1
round=2 over=false errorPrevious=false roots=Stage1
generated=Stage2
round=3 over=false errorPrevious=false roots=Stage2
round=4 over=true errorPrevious=false roots=none
runtime=demo.Stage2
~~~

Đây là kết quả đã được chạy với **OpenJDK 24** và các lệnh `--release 17`. Khi compiler dùng đúng fixture và chỉ processor này, không có lỗi, các round tiến triển như trên.

Sau pha B phải có:

~~~text
generated/demo/Stage1.java
generated/demo/Stage2.java
out/demo/Seed.class
out/demo/Stage1.class
out/demo/Stage2.class
~~~

Các file Java sinh ra về bản chất có nội dung:

~~~java
// generated/demo/Stage1.java
package demo;
@Generate(1)
public final class Stage1 {}
~~~

~~~java
// generated/demo/Stage2.java
package demo;
@Generate(0)
public final class Stage2 {}
~~~

Hai khối trên minh họa **hai file khác nhau** và tên file được ghi trong comment, không phải hai class public đặt chung một source file.

## 7. Phân tích chính xác từng round

| Round | `processingOver()` | `getRootElements()` | `getElementsAnnotatedWith(Generate.class)` | Hành động |
| --- | --- | --- | --- | --- |
| 1 | `false` | `Seed` | `Seed` với `@Generate(2)` | Sinh `Stage1.java` chứa `@Generate(1)` |
| 2 | `false` | `Stage1` | `Stage1` với `@Generate(1)` | Sinh `Stage2.java` chứa `@Generate(0)` |
| 3 | `false` | `Stage2` | `Stage2` với `@Generate(0)` | Không tạo thêm file |
| 4 — final | `true` | Trống (`none`) trong fixture này | Trống | Không sinh file; kết thúc processing |

**Vì sao vẫn có round 3?** Vì `Stage2.java` đã được tạo và đóng ở vòng 2 nên được compiler đem vào vòng 3, dù `@Generate(0)` không yêu cầu sinh tiếp.

**Vì sao vẫn có round 4?** Sau một vòng không sinh thêm source/class cần processing, compiler tiến đến **final round** để kết thúc vòng đời processor. Processor từng tham gia các vòng trước vẫn được gọi ở vòng cuối. Trong ví dụ, `processingOver() == true` là tín hiệu chính xác; `roots=none` chỉ là đặc điểm của fixture.

**Vì sao `errorPrevious=false` ở cả bốn vòng?** Không có processor nào phát diagnostics dạng ERROR trong fixture, nên không có lỗi của vòng trước để báo. Nếu ở một vòng processor gọi `Messager.printMessage(Diagnostic.Kind.ERROR, ...)`, tình trạng lỗi sẽ được báo ở vòng tiếp theo theo ngữ nghĩa `errorRaised()`, và compilation thất bại.

**Vì sao processor được gọi ở round 4 dù không còn `@Generate`?** Vì hợp đồng `Processor` yêu cầu processor đã được hỏi xử lý ở một vòng phải tiếp tục được hỏi ở các vòng sau, kể cả vòng cuối. Tập `annotations` truyền vào `process` có thể rỗng; processor không nên ngầm giả định “không có annotation thì không bao giờ được gọi”.

## 8. Khác nhau giữa ba điều kiện dễ nhầm

| Kiểm tra | Nghĩa thực tế | Có phải điều kiện kết thúc rounds? |
| --- | --- | --- |
| `annotations.isEmpty()` | Trong lần gọi `process` hiện tại, không có annotation types được chỉ định để processor xử lý/claim | **Không** |
| `round.getElementsAnnotatedWith(Generate.class).isEmpty()` | Không tìm thấy phần tử `@Generate` thuộc phạm vi vòng hiện tại | **Không** |
| `round.processingOver()` | Những type sinh ở vòng này sẽ không được xử lý trong vòng kế tiếp; đây là final round | **Có**, đây là tín hiệu chính thức |

Điều kiện thứ ba là thứ nên dùng để xác định phần code dành cho final round. Hai điều kiện đầu chỉ nói về dữ liệu mà processor quan sát trong một lần gọi, không quyết định toàn bộ tiến trình compile.

Một processor có thể được gọi với tập annotation rỗng trong final round hoặc một vòng tiếp theo dù không còn phần tử có annotation được hỗ trợ. Nếu cần phát hiện đúng loại dữ liệu quan trọng trong rounds, hãy kiểm tra bằng `getElementsAnnotatedWith(...)` thay vì dựa vào `annotations.size()` như “số phần tử code”.

## 9. Trạng thái xuyên rounds và thiết kế processor an toàn

### 9.1. Có thể lưu thông tin từ nhiều rounds

Vì cùng processor instance tiếp tục tham gia những vòng sau, bạn có thể lưu dữ liệu thu thập được ở field:

~~~java
// Một phần của lớp processor, không phải chương trình độc lập:
private final java.util.Set<String> seenTypes =
        new java.util.TreeSet<>();

@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment round) {
    if (!round.processingOver()) {
        for (Element e : round.getElementsAnnotatedWith(Generate.class)) {
            seenTypes.add(e.toString());
        }
    } else {
        processingEnv.getMessager().printMessage(
                javax.tools.Diagnostic.Kind.NOTE,
                "Observed types: " + seenTypes);
    }
    return true;
}
~~~

Đoạn trên minh họa **tích lũy dữ liệu và báo kết quả ở vòng cuối**, chưa thực hiện code generation. `TreeSet` giúp đầu ra có thứ tự ổn định nếu nhiều `Element` được phát hiện.

Trong project thực tế, nên giữ thông tin **độc lập với các đối tượng vòng đời nhạy cảm** (ví dụ tên type, khóa metadata) thay vì cố dùng lại `RoundEnvironment` hay các `Element` cũ trong những ngữ cảnh công cụ không cam kết hỗ trợ. Nếu cần tạo một file tổng hợp, phải thiết kế nó đúng với quy tắc về final round và incremental processing.

### 9.2. Tránh đoán thứ tự xử lý Element

`RoundEnvironment.getRootElements()` và `getElementsAnnotatedWith(...)` trả về **Set**. Khi nhiều elements cùng thuộc một vòng, không nên khẳng định thứ tự duyệt như là hợp đồng nghiệp vụ. Muốn code generation ổn định, sắp xếp theo tên nhị phân/qualified name phù hợp.

Trong lab, chúng ta cố ý chỉ đưa một annotated root ở từng vòng, còn log `roots` được `sorted()` để tránh phụ thuộc vào thứ tự `Set`.

### 9.3. Tránh phụ thuộc vào thứ tự processor khác

Khi có nhiều annotation processors trong một lần compile, chúng cùng chia sẻ môi trường xử lý. Thiết kế tốt tránh giả định processor A chắc chắn sinh xong một loại file trước khi B kiểm tra nó trong cùng một vòng.

Nếu processor B cần phản ứng với source được A sinh, nó có thể nhìn thấy kết quả trong **vòng kế tiếp** sau khi file được đóng và được compiler đưa vào processing. Các processor nên độc lập, deterministic và tránh tạo output trùng tên.

### 9.4. Trạng thái giữa các lần build là chuyện khác

Field `roundNumber` và tập `seenTypes` chỉ sống trong **một processor instance của một tác vụ processing**. Không giả định field này được giữ lại qua các lần `javac` độc lập. Ngược lại, generated files nằm trên disk có thể còn lại sau nhiều lần build; vì thế test nên dùng output sạch, và build tool/incremental compiler cần tự quản lý cache, dependency và xóa output đã lỗi thời.

## 10. Báo lỗi đúng giai đoạn: Messager, errorRaised và kết quả compiler

Khi phát hiện annotation bất hợp lệ, processor nên tạo **diagnostic** bằng `Messager`:

~~~java
// Đoạn trong processor, e là Element cần báo lỗi:
processingEnv.getMessager().printMessage(
        javax.tools.Diagnostic.Kind.ERROR,
        "@Generate value must be non-negative", e);
~~~

Dùng `Diagnostic.Kind.ERROR` giúp báo lỗi gắn với source element, và có thể làm toàn bộ lần compile không thành công. So với `System.out.println`, diagnostic mang ý nghĩa chính thức hơn cho công cụ build và IDE.

Có ba khía cạnh khác nhau:

- `Messager.printMessage(ERROR, ...)` **phát hiện và báo một lỗi** trong vòng hiện tại.
- `RoundEnvironment.errorRaised()` **báo rằng vòng trước đã có lỗi**; vì vậy không thể dùng nó để kiểm tra ngay chính dòng `printMessage(ERROR)` vừa thực thi.
- `JavaCompiler.CompilationTask.call()` hoặc exit code của `javac` phản ánh **kết quả của toàn bộ compilation**. `process(...)` trả `true` hay `false` chỉ có ý nghĩa về việc **claim annotation types**, không phải trạng thái build.

**Thực hành tốt khi có lỗi:** tránh sinh thêm nhiều type sau khi phát hiện dữ liệu sai trầm trọng; báo diagnostic có ngữ cảnh và để compiler hoàn thành cơ chế xử lý kết thúc. Không nuốt exception rồi in thông báo kiểu “success”.

## 11. Lưu ý về cấu hình javac trên Java hiện đại

Kể từ **JDK 23**, `javac` không còn tự động chạy annotation processors chỉ vì chúng vô tình xuất hiện trên classpath khi không có cấu hình processing tường minh. Hãy chỉ định processor/path hoặc một tùy chọn bật processing tương ứng:

- `-processor demo.ChainProcessor`: chọn processor đích danh (được dùng trong lab).
- `-processorpath out` hay `--processor-path out`: cấu hình đường tìm processor classpath.
- `--processor-module-path ...`: tìm processor triển khai trong named module.
- `-proc:full`: yêu cầu annotation processing cùng compilation.
- `-proc:only`: chỉ chạy processing, không thực hiện bước compile thông thường sau đó.
- `-proc:none`: vô hiệu hóa annotation processing.

Nếu một project dựa vào service descriptor `META-INF/services/javax.annotation.processing.Processor` để tự khám phá processor, resource đó chỉ giải quyết **khám phá**, không được xem là bảo đảm processing luôn bật theo mặc định trên JDK 23+. Cần thiết lập build toolchain và processor dependencies tường minh để bảo đảm các rounds thực sự được chạy.

**Trong lab,** pha B vừa khai báo `-processorpath out`, vừa khai báo `-processor demo.ChainProcessor` nên trên JDK hiện đại hành vi là xác định. Pha A/C dùng `-proc:none` tránh kích hoạt processor không cần thiết.

Có thể thêm `-XprintRounds` và `-XprintProcessorInfo` khi nghiên cứu hành vi của `javac`. Đây là **tùy chọn chẩn đoán của javac**, không phải API ổn định để chương trình parse output; nếu dùng, không viết test phụ thuộc tuyệt đối vào định dạng log nội bộ của compiler.

## 12. Kiểm thử nhiều rounds và các lỗi phổ biến

### 12.1. Assertions có giá trị hơn chỉ quan sát stdout

Với bài lab có mục tiêu kiểm thử, kiểm tra:

1. Lệnh biên dịch processor ở pha A **thành công**.
2. Pha B được bật processor tường minh và **thành công**.
3. `generated/demo/Stage1.java` và `generated/demo/Stage2.java` tồn tại, có annotation lần lượt `@Generate(1)` và `@Generate(0)`.
4. `out/demo/Stage1.class` và `out/demo/Stage2.class` tồn tại.
5. Trình tự rounds có trạng thái `false, false, false, true` ở `processingOver()` trong fixture này.
6. Khi chạy `demo.Main`, chương trình in đúng `runtime=demo.Stage2`.
7. Nếu đổi `@Generate(2)` thành `@Generate(0)` trên **output sạch**, không có file `Stage1.java` hoặc `Stage2.java` được sinh; processing vẫn có vòng kết thúc.

Kiểm tra này phân biệt **annotation processing rounds** với **runtime loading** của `Main`. `Main` chỉ chứng minh class được compiler tạo ra có thể dùng sau khi build; nó không làm rounds chạy tiếp.

### 12.2. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Processor không in round nào | Annotation processing chưa bật; sai `-processor`, classpath hoặc processor path | Kiểm tra lệnh `javac`; trên JDK 23+ luôn cấu hình tường minh |
| Processor chỉ thấy input ban đầu | Không có source/class mới được tạo hoặc writer chưa được đóng | Dùng `Filer` đúng API; đóng writer/output stream trước khi kết thúc round |
| `getElementsAnnotatedWith` rỗng | Không có annotation đó trong tập declarations của vòng này | Kiểm tra tên annotation, `@Target`, `@SupportedAnnotationTypes` và roots |
| Processor tiếp tục sinh quá nhiều vòng | File mới vẫn chứa annotation làm trigger mà không có điểm dừng | Giới hạn các bước sinh, lưu trạng thái, tránh vòng lặp tạo source vô hạn |
| `FilerException` | Tạo trùng file/type name trong cùng processing run | Thiết kế tên duy nhất, không tạo lại trong các vòng sau |
| `round.errorRaised()` chưa báo `true` ngay khi vừa phát ERROR | Nó phản ánh trạng thái lỗi của **vòng trước** | Đừng đọc nó như biến trạng thái lỗi của vòng đang chạy |
| Processor không thấy `Stage1` ở cùng vòng vừa tạo | Source/class mới được xem xét ở **vòng sau** | Chờ round tiếp theo; không coi file vừa tạo là root của round hiện tại |
| Có file resource nhưng không có round mới | `createResource` không đưa resource làm source/class mới để xử lý | Nếu cần round mới, dùng `createSourceFile`/`createClassFile` đúng hợp đồng |
| Generated code vẫn xuất hiện sau khi tắt processor | Còn output cũ hoặc incremental cache | Dùng thư mục test sạch, kiểm tra artifact thực tế |
| Không thấy compilation failure dù processor trả `false` | `false` chỉ là “không claim annotation types” | Báo lỗi bằng `Messager` khi cần |

### 12.3. Không biến ví dụ thành hệ thống build production một cách máy móc

Bài lab tạo một chain cố ý để thấy cơ chế rounds; không phải mọi processor đều nên sinh file ở nhiều vòng. Trong thực tế, **sinh đầy đủ output có thể từ round đầu** thường đơn giản hơn khi thiết kế cho phép.

Các processor tổng hợp nhiều source có thể cần đợi các types do processor khác tạo ra ở vòng tiếp theo. Khi đó cần quy tắc rõ ràng về naming, originating elements, mô hình cross-round state và không đụng output.

Ngoài ra, processor là **Java code được thực thi trong quá trình build**. Chỉ bật các processor đáng tin cậy, dùng processor path/module path có kiểm soát, không coi “compile-time” là sandbox bảo mật.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Trong lab, vì sao `Stage1` không nằm trong `getRootElements()` của round 1?

**Đáp án:** `Stage1.java` chỉ được `Filer` sinh và đóng **trong** round 1; nó được compiler đưa vào danh sách đầu vào của **round 2**.

**Câu 2.** `getElementsAnnotatedWith(Generate.class)` có tự động trả cả `Seed` và `Stage1` ở round 2 không?

**Đáp án:** Không. Phương thức truy vấn các phần tử annotate **thuộc phạm vi round 2**; trong fixture đó là `Stage1`. Nếu cần nhớ `Seed`, processor phải tự giữ dữ liệu từ round trước.

**Câu 3.** Nếu trong một round `getElementsAnnotatedWith(...)` trả rỗng, có thể kết luận round đó là final không?

**Đáp án:** Không. Dùng `processingOver()` để nhận diện final; tập annotation rỗng chỉ nói về dữ liệu có trong vòng này.

**Câu 4.** Khi processor phát `Diagnostic.Kind.ERROR` ở round hiện tại, `errorRaised()` có bắt buộc phản ánh lỗi ngay ở dòng code tiếp theo không?

**Đáp án:** Không. Theo hợp đồng, `errorRaised()` mô tả **vòng trước**. Việc báo lỗi thuộc `Messager`; kết quả build cần được kiểm tra ở cấp compiler.

**Câu 5.** Processor trả `true` ở final round có giúp compiler bắt buộc build thành công không?

**Đáp án:** Không. Giá trị `true` chỉ báo claim annotation types. Compiler có thể thất bại vì diagnostics, source lỗi hoặc generated code lỗi.

**Câu 6.** Nếu trong `process` tạo một JSON resource bằng `Filer.createResource(...)`, có chắc nó kích hoạt processing round mới không?

**Đáp án:** Không. Tài nguyên phụ trợ không được xử lý như source/class mới của các vòng annotation processing.

**Câu 7.** Trên JDK 23+, chỉ đặt `ChainProcessor.class` trong một thư viện phụ thuộc có đủ để processor luôn tự chạy không?

**Đáp án:** Không. Cần cấu hình tường minh cho annotation processing, ví dụ `-processor` và processor path hoặc tùy chọn `-proc:full` kết hợp cơ chế khám phá thích hợp.

**Bài tập thực hành:** đổi `@Generate(2)` của `Seed` thành `@Generate(3)`, đồng thời sửa thuật toán đặt tên để sinh lần lượt ba stage theo cách tổng quát. Trước khi chạy hãy dự đoán số non-final rounds và số final rounds; sau đó chạy trên thư mục output sạch, kiểm tra files, stdout và điều kiện dừng. Đừng chỉ tăng số bước mà vẫn giữ công thức `3 - remaining` cứng của lab gốc.

## 14. Tài liệu chính thức còn được hỗ trợ

- [Java SE 26 — RoundEnvironment](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): `processingOver`, `errorRaised`, `getRootElements`, `getElementsAnnotatedWith`.
- [Java SE 26 — Processor](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/Processor.html): hợp đồng về rounds, processors được gọi ở rounds tiếp theo và final round.
- [Java SE 26 — AbstractProcessor](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): lớp nền implement processor và lifecycle.
- [Java SE 26 — Filer](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/Filer.html): quy tắc file creation, subsequent rounds, originating elements, `FilerException`.
- [Java SE 26 — Messager](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/Messager.html): diagnostics trong compiler.
- [Java SE 26 — javac](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): cấu hình processor và các lựa chọn processing.
- [JDK 23 Release Notes](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html): thay đổi mặc định của annotation processing trong `javac`.

**Ghi nhớ:** `RoundEnvironment` trả lời **“đang xử lý những phần tử nào trong vòng này, và đã đến vòng cuối chưa?”**. `Filer` quyết định source/class mới nào có thể xuất hiện ở vòng sau; `processingOver()` là tín hiệu kết thúc; `errorRaised()` báo lỗi của **vòng trước**. Thiết kế processor đúng vòng đời giúp generated code ổn định, dễ kiểm thử và phù hợp JDK hiện đại.
