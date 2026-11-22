# processingOver(), errorRaised() và vòng xử lý cuối trong Java Annotation Processing

## 1. Bối cảnh: Annotation Processor được gọi theo nhiều vòng

Trong **Java Annotation Processing API** (JSR 269), một annotation processor không nhất thiết chỉ được gọi một lần cho một lệnh `javac`. Bộ biên dịch có thể gọi phương thức `Processor.process(...)` qua **nhiều vòng xử lý (processing rounds)**, đặc biệt khi processor sinh thêm file Java hoặc class file. Các API liên quan có sẵn trong module chuẩn **`java.compiler`**, package **`javax.annotation.processing`** của Java SE, không cần thư viện thứ ba.

Chữ ký `process` thường gặp khi kế thừa `AbstractProcessor`:

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    // Đọc các phần tử ở vòng hiện tại và tùy chọn sinh file.
    return true;
}
```

Trong đó:

- `annotations`: tập các **annotation type** được công cụ yêu cầu processor xử lý trong lần gọi hiện tại; tập này có thể **rỗng**, nhất là vòng cuối.
- `roundEnv`: đối tượng **`RoundEnvironment`** mô tả một vòng. Nó cho biết vòng có phải vòng kết thúc, vòng trước có phát sinh lỗi không và các phần tử nguồn/class liên quan đến vòng này.
- Giá trị boolean của `process`: `true` là **claim** các annotation type đã được giao; `false` là không claim để processor khác có thể xử lý. **Đây không phải cờ “còn vòng tiếp theo” hay “biên dịch thành công”.**

Một quy trình điển hình:

```text
Lệnh javac với file nguồn ban đầu
    |
    v
Vòng 1: xử lý các root từ đầu vào
    |  Processor có thể dùng Filer tạo file nguồn mới
    v
Vòng 2: xử lý các root được tạo từ vòng trước
    |  Không có file mới cần xử lý tiếp
    v
Vòng cuối: processingOver() == true
    |  Dọn dẹp/tổng hợp; không chờ vòng xử lý mới
    v
Hoàn tất quá trình annotation processing
```

Số vòng thường tùy file mới được sinh, processor được kích hoạt, lỗi và cách hoạt động của công cụ. **Không được hard-code** “lúc nào cũng có ba vòng” hoặc “vòng 2 luôn là vòng cuối”.

## 2. Hai phương thức quan trọng của RoundEnvironment

`RoundEnvironment` cung cấp hai phương thức boolean thường gây nhầm lẫn:

| Phương thức | Câu hỏi thật sự được trả lời | Khi nào thường true? | Điều KHÔNG được suy ra |
| --- | --- | --- | --- |
| `processingOver()` | Các kiểu được tạo trong **vòng này** có còn được đem sang một vòng annotation processing tiếp theo không? | Trong vòng xử lý cuối | Không đồng nghĩa có lỗi hay biên dịch thành công |
| `errorRaised()` | Có lỗi được báo ở **vòng xử lý trước đó** không? | Vòng kế tiếp sau vòng đã có error diagnostic | Không phản ánh ngay lập tức lỗi vừa được báo trong chính vòng hiện tại |

Theo tài liệu Java SE 17:

- `processingOver()` **trả `true` nếu những kiểu được tạo trong vòng đang xét không còn được xử lý ở vòng annotation processing tiếp theo**.
- `errorRaised()` **trả `true` nếu có lỗi phát sinh trong vòng xử lý trước**, ngược lại trả `false`.

Cả hai là trạng thái **của vòng**, không phải thuộc tính của từng annotation, từng file hay một bộ đếm tự động. Không có ràng buộc rằng `processingOver() == true` thì `errorRaised() == true`. Một quá trình thành công bình thường có vòng cuối với `processingOver() == true` và `errorRaised() == false`.

### 2.1. Đọc trạng thái bằng API đúng

```java
if (roundEnv.processingOver()) {
    // Vòng cuối: xử lý kết thúc phù hợp.
    return true;
}

if (roundEnv.errorRaised()) {
    // Có error diagnostic được báo từ vòng trước.
    // Tùy nghiệp vụ, tránh các thao tác sinh output tiếp theo.
}
```

Đoạn trên chỉ là mẫu logic trong `process`, không phải chương trình Java độc lập. **Không cần kiểm tra `errorRaised()` để quyết định vòng cuối**; dùng `processingOver()` cho mục đích đó.

### 2.2. errorRaised không phải phép kiểm tra lỗi của vòng hiện tại

Giả sử processor gọi:

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Cấu hình không hợp lệ");
```

Lệnh này **báo một error diagnostic**. Nhưng đối tượng `RoundEnvironment` của **vòng đang chạy** không vì thế lập tức đổi `errorRaised()` thành `true`. Java đặc tả `errorRaised()` là cờ báo trạng thái lỗi của **vòng trước**.

Vì vậy, cách diễn giải đúng:

```text
Vòng N:
  errorRaised() = false
  Processor báo Diagnostic.Kind.ERROR
  Các processor trong vòng N có thể vẫn được gọi tiếp

Vòng kế tiếp:
  errorRaised() = true
  Vòng này có thể là vòng cuối
```

Nếu processor đã tự xác định cấu hình sai trong vòng hiện tại, hãy **ghi nhận lỗi vào trạng thái của chính processor khi cần** hoặc ngừng phần việc không còn phù hợp; đừng chờ `roundEnv.errorRaised()` ngay trong vòng đó đổi giá trị.

## 3. Vòng xử lý cuối: processingOver() == true

**Vòng cuối (last/final round)** vẫn là một lần gọi `process` theo hợp đồng của annotation processing. Nếu processor đã được yêu cầu xử lý ở một vòng trước, nó sẽ tiếp tục được gọi ở các vòng sau, **bao gồm vòng cuối**, ngay cả khi không còn annotation type nào được giao.

Một mẫu điển hình:

```java
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment roundEnv) {
    if (roundEnv.processingOver()) {
        // Hoàn tất thống kê hoặc dọn trạng thái.
        return true;
    }

    // Xử lý các phần tử của vòng bình thường.
    return true;
}
```

**Những việc hợp lý tại vòng cuối:**

- Tổng kết số lượng phần tử đã xử lý ở các vòng trước.
- Kiểm tra trạng thái nội bộ của processor và thông báo kết quả.
- Phát hành chẩn đoán lỗi/cảnh báo cuối cùng khi cần.
- Giải phóng dữ liệu tạm trong processor.
- Hoàn thiện dữ liệu tổng hợp theo hợp đồng đầu ra đã thiết kế, ví dụ tài nguyên phụ trợ, với hiểu biết rõ về Filer và môi trường build.

**Những việc cần tránh tại vòng cuối:**

- Sinh **source/class file mới với kỳ vọng nó sẽ được xử lý bởi annotation processor ở một vòng tiếp theo**. `processingOver() == true` nói rõ rằng **không có vòng tiếp theo để xử lý các kiểu tạo trong vòng này**.
- Dùng vòng cuối để tạo loại nguồn cần sinh tiếp các loại nguồn khác.
- Giả định tập `annotations` hoặc `getRootElements()` luôn có dữ liệu trong vòng cuối.
- Bắt đầu một chuỗi sinh file chưa thể hoàn thiện.
- Cho rằng gọi `process` ở vòng cuối là lỗi hoặc processor được cấp một instance mới.

**Lưu ý Filer:** `Filer` là API sinh source, class và resource. File source/class được sinh và đóng stream trong vòng bình thường được xem xét ở vòng tiếp theo. Trong vòng cuối, **đừng sinh source/class để được xử lý tiếp**; một số công cụ như `javac` có thể cảnh báo rằng file sinh ở vòng cuối sẽ không được đưa vào annotation processing. Nếu thiết kế phải tạo **resource tổng hợp**, hãy cân nhắc thời điểm cuối phù hợp, quản lý lỗi I/O và đảm bảo không phụ thuộc vào vòng xử lý mới.

### 3.1. Vòng cuối không đồng nghĩa “sạch lỗi”

Hai trạng thái có thể xuất hiện:

```text
FINAL: processingOver=true, errorRaised=false  // Kết thúc bình thường
FINAL: processingOver=true, errorRaised=true   // Vòng trước đã báo lỗi
```

Nếu `errorRaised()` là `true` trong vòng cuối, processor nên cân nhắc **không xuất bản artifact tổng hợp được coi là hợp lệ**, bởi quá trình trước đó đã báo lỗi. Tuy nhiên, vẫn có thể in thống kê phục vụ chẩn đoán; chính sách xử lý phụ thuộc mục đích processor.

Nếu `errorRaised()` là `false` trong vòng cuối, cũng **không nên suy ra đây là bằng chứng độc lập rằng tất cả các bước biên dịch/đóng gói sau đó thành công**. Cờ phản ánh lỗi vòng trước trong annotation processing, không phải mã thoát toàn bộ pipeline build.

## 4. Các vòng thường xuất hiện khi dùng Filer

Khi processor gọi:

```java
JavaFileObject file = processingEnv.getFiler()
        .createSourceFile("generated.Example");
```

và đóng `Writer`/output stream đã dùng để ghi file, công cụ annotation processing có thể đưa kiểu vừa được tạo vào **vòng xử lý tiếp theo**. Các round mới không phải do processor tự gọi `process` đệ quy; chúng do compiler orchestration quản lý.

Thường diễn ra:

1. **Vòng ban đầu**: các root tương ứng với file nguồn đầu vào được xét; processor thấy annotation cần xử lý.
2. **Vòng phát sinh**: các source/class file sinh bởi vòng trước trở thành root thích hợp, processor có thể xử lý annotation nằm trên những file đó.
3. **Vòng cuối**: không còn kiểu mới cần xử lý; `processingOver()` chuyển thành `true`.

Một chi tiết hữu ích trong `RoundEnvironment` là `getRootElements()`: nó trả những **root elements tương ứng với đầu ra của vòng trước**. Với vòng đầu, xem các input ban đầu như đầu ra của một “vòng số 0” giả định. Root không nhất thiết chỉ có class; tùy đầu vào còn có thể là package hoặc module.

**Không suy ra số vòng chỉ từ số annotation:** một processor có thể xử lý nhiều annotation trong cùng vòng. Ngược lại, một annotation type có thể xuất hiện ở nhiều vòng nếu có các type mới được sinh ra.

### 4.1. Processor được gọi lại, không phải tạo mới ở mỗi vòng

Công cụ thường khởi tạo một processor (public no-arg constructor), gọi `init`, rồi gọi `process` các vòng phù hợp trên **cùng object processor** của lần biên dịch. Điều này cho phép giữ bộ đếm hoặc dữ liệu tổng hợp trong instance fields:

```java
private int normalRounds;
private boolean generated;
```

Các trường này là **trạng thái cho một phiên xử lý của processor**, không được hiểu là lưu trữ bền vững giữa nhiều lần gọi `javac`. Compiler có thể chạy trong IDE/build daemon theo cách riêng; đừng dựa vào static state hoặc global state như một hợp đồng giữa nhiều lần build.

## 5. Ví dụ Java 17+ hoàn chỉnh: hai vòng thường và vòng cuối

Ví dụ sau có **ba file Java**, không phụ thuộc thư viện ngoài. Một annotation processor sinh thêm file `GeneratedGreeting.java` ở vòng đầu, nhờ đó compiler có thêm một vòng xử lý thường trước khi gọi vòng cuối.

Dùng JDK 17 trở lên với `--release 17` để ví dụ có ngữ nghĩa source Java 17 ổn định ngay cả khi máy đang chạy JDK mới hơn.

### 5.1. File DemoTag.java

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@interface DemoTag {}
```

`DemoTag` không cần `RUNTIME` retention: annotation processor **đọc cấu trúc trong quá trình biên dịch**, không dùng reflection runtime. Vì không khai báo `@Retention`, chính sách mặc định của annotation là `CLASS`; điều đó không cản trở processor tìm annotation trong source.

### 5.2. File Demo.java

```java
@DemoTag
class Demo {}
```

`Demo` là type ban đầu được gắn `DemoTag`, để processor có annotation type cần xử lý.

### 5.3. File RoundLifecycleProcessor.java

```java
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

@SupportedAnnotationTypes("DemoTag")
@SupportedOptions("fail")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class RoundLifecycleProcessor extends AbstractProcessor {
    private int normalRounds;
    private boolean generated;

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        if (roundEnv.processingOver()) {
            System.out.println("FINAL processingOver=" + roundEnv.processingOver()
                    + " errorRaised=" + roundEnv.errorRaised());
            return true;
        }

        normalRounds++;
        Set<? extends Element> targets =
                roundEnv.getElementsAnnotatedWith(DemoTag.class);
        System.out.println("ROUND " + normalRounds
                + " processingOver=" + roundEnv.processingOver()
                + " errorRaised=" + roundEnv.errorRaised()
                + " targets=" + targets.size());

        if ("true".equals(processingEnv.getOptions().get("fail"))) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR, "simulated error");
            return true;
        }

        if (!generated) {
            generated = true;
            try (Writer writer = processingEnv.getFiler()
                    .createSourceFile("GeneratedGreeting").openWriter()) {
                writer.write("@DemoTag class GeneratedGreeting {}\n");
            } catch (IOException e) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, e.getMessage());
            }
        }
        return true;
    }
}
```

**Các điểm chủ chốt trong processor:**

- `@SupportedAnnotationTypes("DemoTag")` khai báo loại annotation mà processor hỗ trợ. Tên ở default package chỉ dùng cho demo; dự án thật nên đặt package rõ ràng.
- `@SupportedSourceVersion(RELEASE_17)` công bố phiên bản ngôn ngữ được processor hỗ trợ; tùy môi trường build có thể chọn phiên bản phù hợp khác.
- `@SupportedOptions("fail")` khai báo tùy chọn `-Afail=true` để minh họa kịch bản lỗi có kiểm soát ở mục 6.
- Vòng cuối được nhận biết **trước khi** tăng bộ đếm hay gọi `Filer`; nhánh `processingOver()` chỉ tổng kết.
- Ở vòng thường, `getElementsAnnotatedWith(DemoTag.class)` lấy các root/phần tử mang `@DemoTag` thuộc phạm vi vòng hiện tại.
- `generated` ngăn processor tạo lại cùng một file `GeneratedGreeting` ở vòng sau; nếu tạo lại cùng pathname, `Filer` có thể ném `FilerException`.
- Dòng viết source dùng `\n` trong Java string để tạo một ký tự xuống dòng ở file sinh, không phải hai ký tự `\` và `n`.
- `return true` **claim annotation type**, không dừng pipeline annotation processing.

### 5.4. Lệnh biên dịch và chạy processor

Tạo ba file trong **cùng một thư mục rỗng**. Mở terminal tại thư mục ấy. Ví dụ bằng shell hỗ trợ `mkdir -p`:

```bash
mkdir -p build generated

javac --release 17 -d build DemoTag.java RoundLifecycleProcessor.java

javac --release 17 -cp build -processorpath build \
  -processor RoundLifecycleProcessor \
  -d build -s generated Demo.java
```

Trong PowerShell, có thể tạo thư mục bằng `New-Item -ItemType Directory -Force build, generated` rồi viết lệnh `javac` trên một dòng; ký tự nối dòng `\` trong block `bash` **không phải** cú pháp nối dòng của PowerShell.

Ý nghĩa các cờ:

| Cờ | Tác dụng |
| --- | --- |
| `--release 17` | Biên dịch theo API và ngữ nghĩa Java 17 |
| `-d build` | Ghi các file `.class` vào thư mục `build` |
| `-cp build` | Cho compiler thấy `DemoTag.class` đã biên dịch |
| `-processorpath build` | Chỉ định nơi nạp `RoundLifecycleProcessor.class` cùng các dependency cần thiết |
| `-processor RoundLifecycleProcessor` | Yêu cầu compiler chạy processor cụ thể, không phụ thuộc service discovery |
| `-s generated` | Ghi source file do annotation processor sinh ra vào thư mục `generated` |

Với các file trên, khi gọi `javac` cho `Demo.java`, processor in ra stdout:

```text
ROUND 1 processingOver=false errorRaised=false targets=1
ROUND 2 processingOver=false errorRaised=false targets=1
FINAL processingOver=true errorRaised=false
```

Kết quả này đã được đối chiếu với JDK 21 dùng `--release 17`. Đây là **stdout do processor in ra**, không phải kết quả chạy một class có `main`.

Giải thích:

1. Vòng 1 nhận `Demo` có `@DemoTag`, nên `targets=1`. Processor sinh file mới `GeneratedGreeting.java`.
2. Vòng 2 nhận type `GeneratedGreeting` được sinh và có `@DemoTag`, nên `targets=1` lần nữa. Vì `generated=true`, không có file mới nào được sinh tiếp.
3. Vòng cuối được gọi với `processingOver=true`. Không có error diagnostic từ vòng trước, nên `errorRaised=false`.

Sau build, file `GeneratedGreeting.java` xuất hiện trong `generated`. `javac` cũng biên dịch type vừa sinh ra theo quy trình công cụ, nhưng **số vòng thuộc xử lý annotation**, không nên lẫn với số bước link/packaging.

### 5.5. Thử thêm -XprintRounds

Có thể thêm tùy chọn `-XprintRounds` vào lệnh `javac` thứ hai để compiler in thông tin bổ sung về từng vòng. Các dòng in bởi `javac` sẽ xuất hiện **ngoài stdout từ `System.out.println` trong processor**; thứ tự/thông tin chi tiết tùy phiên bản công cụ.

`-XprintRounds` rất hữu ích để chẩn đoán vì hiển thị các input, tập annotation và trạng thái vòng. Nó là **tùy chọn của javac**, không phải một phương thức của `RoundEnvironment`.

## 6. Ví dụ lỗi: errorRaised() xuất hiện ở vòng kế tiếp

Processor ở mục 5 đã khai báo `@SupportedOptions("fail")`. Muốn mô phỏng lỗi, chạy lệnh build cho file `Demo.java` với tùy chọn:

```bash
javac --release 17 -cp build -processorpath build \
  -processor RoundLifecycleProcessor -Afail=true \
  -d build -s generated Demo.java
```

Lần biên dịch này **được dự kiến sẽ thất bại**, vì processor gọi `Messager.printMessage(Diagnostic.Kind.ERROR, "simulated error")`.

Các dòng **stdout do processor** trong trường hợp thử nghiệm:

```text
ROUND 1 processingOver=false errorRaised=false targets=1
FINAL processingOver=true errorRaised=true
```

Công cụ `javac` còn in diagnostic lỗi (ví dụ `error: simulated error`) trên luồng chẩn đoán; vị trí hiển thị, số lỗi và định dạng có thể khác theo môi trường. **Exit code là non-zero** vì đã có error diagnostic.

Diễn giải chính xác:

- Khi vào vòng 1, **chưa có lỗi của vòng trước**, nên `errorRaised=false`.
- Processor tự báo **ERROR trong vòng 1**. Giá trị `roundEnv.errorRaised()` của vòng 1 không tự thay đổi tức thì.
- Vòng kế tiếp là vòng cuối, `processingOver=true` và `errorRaised=true`, báo lỗi ở vòng trước.
- Kịch bản lỗi cố ý **không tạo `GeneratedGreeting`**, nên không có vòng thường thứ hai để xử lý nguồn mới.

Không được định nghĩa `errorRaised()` là “vòng hiện tại đang có lỗi” hoặc “toàn bộ lệnh javac chắc chắn sẽ thất bại ngay thời điểm truy vấn”. Tương tự, `processingOver()` đúng ở vòng cuối kể cả khi **không hề phát sinh lỗi**.

## 7. Quan hệ giữa errorRaised(), Messager và việc tiếp tục xử lý

### 7.1. Lỗi qua Messager khác exception chưa được xử lý

Trong annotation processor, cách thông dụng để báo lỗi có kiểm soát là:

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR, "Giá trị annotation không hợp lệ");
```

Compiler thu thập lỗi chẩn đoán; **vòng hiện tại có thể tiếp tục chạy đến hết**, và `errorRaised()` ở vòng kế tiếp phản ánh rằng có lỗi từ vòng trước.

Ngược lại, **ném uncaught exception** từ processor không phải cơ chế báo validation error chuẩn: công cụ có thể ngừng gọi các processor khác hoặc kết thúc annotation processing bất thường. Với lỗi người dùng có thể sửa như thiếu annotation value, cấu hình sai, nên sử dụng `Messager` và vị trí `Element` cụ thể khi có thể, thay vì ném exception không xử lý.

### 7.2. warning không phải errorRaised

`Diagnostic.Kind.WARNING` hoặc `MANDATORY_WARNING` không phải là `ERROR`. Đừng mặc định một lời cảnh báo khiến `errorRaised=true`. Tuy nhiên, compiler có thể được cấu hình như `-Werror` để coi các warning là điều kiện làm compilation thất bại; tác động tới trạng thái lỗi cụ thể tùy công cụ và cấu hình. Vì vậy tránh thiết kế logic dựa trên dự đoán về `errorRaised()` khi trộn nhiều chính sách warning.

### 7.3. Vì sao không kiểm tra lỗi chỉ ở vòng cuối?

Giả sử processor thấy annotation không hợp lệ ở vòng bình thường nhưng vẫn cố sinh một file Java phụ thuộc vào cấu hình sai. File được sinh có thể tiếp tục lan lỗi hoặc tạo output vô nghĩa.

Cách an toàn là **xác thực trước khi sinh** ở mỗi vòng và giữ cờ nội bộ nếu cần. `errorRaised()` chỉ giúp quan sát chẩn đoán từ vòng trước, **không thay thế việc validation của processor ngay trong vòng hiện tại**.

## 8. Mẫu thiết kế processor để tránh lỗi ở vòng cuối

Một processor thực tế thường cần xử lý ba loại trạng thái:

- **Input theo vòng:** các annotation `Element` và root hiện tại; nên lấy từ `RoundEnvironment` của đúng vòng.
- **Trạng thái tích lũy:** các thông tin cần thống kê qua nhiều vòng; dùng instance field theo một phiên xử lý.
- **Trạng thái cuối:** `processingOver()`, `errorRaised()` và các cờ lỗi riêng để quyết định tổng hợp/xuất dữ liệu.

Ví dụ pseudocode Java:

```java
// Mã phác thảo; cần định nghĩa các kiểu và hàm được gọi.
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment roundEnv) {
    if (roundEnv.processingOver()) {
        if (!roundEnv.errorRaised() && !hasOwnErrors) {
            finishSummary(); // Không sinh thêm nguồn cần vòng mới.
        }
        return true;
    }

    for (Element element : roundEnv.getElementsAnnotatedWith(MyTag.class)) {
        if (!isValid(element)) {
            hasOwnErrors = true;
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR, "Invalid annotation", element);
            continue;
        }
        collect(element);
    }

    generateNewSourcesIfNeeded(); // Chỉ vòng thường.
    return true;
}
```

`hasOwnErrors`, `MyTag`, `finishSummary`, `collect`, `isValid` và `generateNewSourcesIfNeeded` là **tên minh họa**, chưa phải class Java độc lập. Mẫu này nhấn mạnh **phân nhánh vòng cuối ngay từ đầu** và tách validation khỏi bước sinh file.

### 8.1. Những lưu ý khi tổng hợp thông tin qua nhiều vòng

- Cùng tên type có thể xuất hiện do source sinh ở các vòng khác nhau; cần dùng key thích hợp và tránh đếm lặp không chủ ý.
- Không giả định thứ tự phần tử từ `Set` là thứ tự ổn định; nếu dùng để sinh resource, sắp xếp rõ ràng khi cần.
- File sinh có thể mang annotation được chính processor này hỗ trợ; tránh sinh mãi một kiểu mới mỗi vòng gây chuỗi xử lý dài không cần thiết.
- Không cố tạo lại một source/class có cùng pathname trong một phiên xử lý; `Filer` có quy tắc chống ghi trùng và có thể ném `FilerException`.
- Khi báo lỗi, đừng tạo ra artifact được coi là hợp lệ nếu dữ liệu nguồn không hợp lệ.
- Khi tích hợp hệ thống build, phân biệt annotation processing của compiler với task chạy app/test sau build; `processingOver()` không phải tín hiệu “đã triển khai sản phẩm”.

## 9. Các lỗi thường gặp

**1. Nhầm processingOver() là “processor đã chạy xong”.** Đây là cờ của vòng cuối đang được gọi; processor vẫn có cơ hội thực hiện logic kết thúc trong lần gọi `process` ấy.

**2. Nhầm errorRaised() là lỗi phát sinh trong chính vòng hiện tại.** Theo Javadoc, đây là lỗi của vòng trước. Khi vừa gọi `Messager.ERROR`, không đợi cờ đổi ngay.

**3. Coi processingOver=true đồng nghĩa có lỗi.** Vòng cuối xảy ra cả khi build bình thường không có error.

**4. Coi errorRaised=false đồng nghĩa toàn bộ pipeline build đã thành công.** Cờ chỉ mô tả lỗi vòng annotation processing trước, không bao phủ mọi giai đoạn compile, test, link hoặc deployment.

**5. Chỉ kiểm tra annotations.isEmpty() để quyết định vòng cuối.** Tập annotation có thể rỗng trong một lần gọi `process`, nhưng chỉ `processingOver()` mới là tín hiệu đúng cho vòng cuối.

**6. Sinh source mới trong vòng cuối rồi chờ nó được xử lý.** Không có vòng tiếp theo để xử lý type được tạo trong vòng cuối. Sinh source/class mới đúng lúc ở vòng thường.

**7. Dùng return true để ngăn những vòng sau.** `return true` claim annotation type, không hủy các round còn lại. Một processor đã được gọi có thể tiếp tục nhận vòng cuối.

**8. Không chống sinh trùng source file.** Mỗi file path chỉ được tạo một lần trong một lần chạy xử lý annotation theo hợp đồng Filer; dùng trạng thái phù hợp để tránh FilerException.

**9. Giả định vòng sau luôn có dữ liệu.** `getRootElements()` và tập annotation có thể rỗng. Code cuối vòng phải chịu được trường hợp không có root.

**10. Giả định sẽ có đúng hai vòng bình thường.** Số vòng phụ thuộc việc sinh file, input và tool; ví dụ này có hai vòng bình thường vì cố ý tạo một source mới ở vòng đầu.

**11. Tạo processor instance mới bằng tay ở mỗi vòng.** Tool thường giữ cùng processor object qua vòng; đừng tự giả định mất trạng thái instance giữa các lần `process`.

**12. Dùng exception chưa được bắt để báo lỗi người dùng.** Ưu tiên Messager chẩn đoán có vị trí; exception chưa xử lý có thể gây dừng xử lý bất thường.

## 10. Checklist khi debug một annotation processor

1. Xác định compiler và source level (ví dụ `javac --release 17`).
2. Xác định processor thực sự được bật (`-processor` hoặc service discovery phù hợp); có `@SupportedAnnotationTypes` đúng annotation type.
3. Thêm log hiển thị `processingOver()`, `errorRaised()`, số root và số phần tử annotation được tìm thấy **theo từng vòng**.
4. Bật `-XprintRounds` khi dùng `javac` để xem thứ tự vòng và root types.
5. Khi có file sinh, kiểm tra tên file, lúc đóng stream, thư mục `-s` và vòng tiếp theo có nhận type vừa sinh không.
6. Nếu compiler báo `FilerException`, tìm chỗ processor tạo lại pathname giữa các vòng.
7. Nếu không có dữ liệu ở vòng cuối, xem lại khâu tích lũy trước đó; không cố coi annotations rỗng là có lỗi.
8. Nếu `errorRaised=true`, tìm `Diagnostic.Kind.ERROR` từ vòng trước (có thể do processor khác); không quy toàn bộ lỗi về processor hiện tại.
9. Kiểm tra processor không sinh file cần xử lý tiếp tại vòng cuối.
10. Đừng kết luận thành công toàn bộ build chỉ từ `errorRaised=false` ở lần `process` cuối.

## 11. Bài tập thực hành

1. **Không sinh file:** Trong `RoundLifecycleProcessor`, tạm bỏ nhánh `createSourceFile`, sau đó chạy lại `javac`. Dự đoán số vòng bình thường và thời điểm `processingOver=true`.
2. **Sinh thêm tầng:** Sửa processor để tạo thêm một kiểu mới có `@DemoTag` trong vòng bình thường thứ hai, đồng thời kiểm soát bằng bộ đếm để không sinh mãi. Quan sát số vòng bằng `-XprintRounds`.
3. **Báo lỗi:** Chạy `-Afail=true`. Giải thích vì sao dòng vòng 1 vẫn in `errorRaised=false`, còn vòng cuối in `true`.
4. **Giả lập warning:** Đổi `Diagnostic.Kind.ERROR` sang `WARNING` trong chế độ thử nghiệm. So sánh kết quả `errorRaised` khi không bật và khi bật cơ chế `-Werror` của compiler. Ghi nhận sự khác biệt theo công cụ.
5. **Bỏ check processingOver:** Quan sát lỗi thiết kế nếu processor tiếp tục gọi Filer cả ở vòng cuối. Sau đó phục hồi guard `processingOver()`.
6. **Claim annotations:** Đổi `return true` thành `false` rồi giải thích ý nghĩa đối với processor khác, không nhầm với số vòng.
7. **Tổng hợp dữ liệu:** Thêm `Set<String>` lưu tên các `TypeElement` được thấy trong vòng thường; in danh sách đã sắp xếp ở vòng cuối. Đảm bảo dữ liệu không bị tính trùng khi có các root tương tự.

## 12. Tài liệu tham khảo chuẩn

- [RoundEnvironment — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): đặc tả `processingOver()`, `errorRaised()`, `getRootElements()` và `getElementsAnnotatedWith()`.
- [Processor — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html): chuỗi các vòng, việc processor được gọi ở vòng cuối và quy tắc claim annotation types.
- [Filer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html): cách file được sinh ở vòng hiện tại trở thành input cho vòng tiếp theo, quản lý tên file và lỗi trùng.
- [Messager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Messager.html): cách processor báo warning/error diagnostic.

**Ghi nhớ:** `processingOver()` trả lời **“đây có phải vòng cuối, không có vòng xử lý tiếp theo cho type được sinh không?”**; `errorRaised()` trả lời **“vòng trước có báo lỗi không?”**. Khi viết processor, kiểm tra vòng cuối sớm, sinh source trong vòng bình thường, báo lỗi bằng `Messager`, và tránh dùng hai cờ này thay cho trạng thái nghiệp vụ hoặc kết quả cuối cùng của toàn bộ build.
