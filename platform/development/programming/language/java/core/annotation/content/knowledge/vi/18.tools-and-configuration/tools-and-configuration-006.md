# Theo dõi vòng annotation processing bằng `-XprintRounds` và `-XprintProcessorInfo`

Trong Java, annotation processor chạy **khi biên dịch**, có thể được gọi qua nhiều vòng (*processing rounds*) và có thể tạo source/class mới để compiler xử lý ở vòng kế tiếp. Khi build phát sinh file thiếu, trùng, processor không được gọi hoặc log khác dự kiến, hai tùy chọn chẩn đoán của `javac` đặc biệt hữu ích:

- **`-XprintRounds`**: in thông tin các vòng xử lý annotation, gồm vòng đầu và các vòng tiếp theo.
- **`-XprintProcessorInfo`**: in thông tin về **những loại annotation mà một processor được yêu cầu xử lý**.

Đây là hai **tùy chọn của trình biên dịch `javac`**, không phải Java annotation, không phải option do ứng dụng tự định nghĩa và cũng không phải một API runtime. Chúng giúp quan sát hoạt động compiler mà **không cần sửa mã của processor chỉ để thêm lệnh `System.out.println`**. Chúng không thay thế việc xử lý lỗi, kiểm thử hay ghi chẩn đoán bằng `Messager`.

## 1. Tại sao cần nhìn thấy từng processing round?

Một lượt xử lý annotation không bắt buộc chỉ gồm một lần gọi `process(...)`. Nếu processor tạo một source file mới, compiler có thể đọc file đó trong **vòng tiếp theo**. Mỗi round có input riêng, tập annotation riêng và trạng thái kết thúc riêng.

Một chuỗi điển hình:

```text
javac nhận Source.java
        |
        v
Round 1: xử lý Source.java
        |     Processor sinh GeneratedA.java
        v
Round 2: xử lý GeneratedA.java
        |     Không sinh thêm Java source/class
        v
Final round: processingOver() == true
        |
        v
Kết thúc annotation processing
```

Khi bật `-XprintRounds`, người phát triển có thể trả lời các câu hỏi:

1. Compiler có thực sự bắt đầu annotation processing không?
2. Có bao nhiêu round đã xảy ra?
3. Ở mỗi round, source/type đầu vào nào được compiler ghi nhận?
4. Annotation nào có mặt trong round?
5. Round nào là vòng kết thúc (*last round*)?
6. Một generated source có được đưa sang round kế tiếp hay không?

Khi bật **cả hai** option, ta còn xem được thông tin về processor được giao xử lý những annotation nào và, tùy phiên bản JDK, thông tin liên quan tới việc processor **claim** annotation.

Lưu ý: các dòng do `-XprintRounds` hiển thị là **log compiler**, không phải dữ liệu ứng dụng in khi chạy bằng lệnh `java`.

## 2. Hai option giống và khác nhau thế nào?

| Tùy chọn | Quan sát chính | Câu hỏi hữu ích |
| --- | --- | --- |
| `-XprintRounds` | Các round của annotation processing: input files, annotations, last-round status. | “Tại sao có ba vòng? Generated source có xuất hiện ở vòng hai không?” |
| `-XprintProcessorInfo` | Processor nào được yêu cầu xử lý loại annotation nào. | “Processor có được chọn/được gọi cho `@TraceTag` không?” |
| Dùng **cả hai** | Góc nhìn theo **round** và theo **processor**. | “Trong round hai compiler thấy marker nào và giao cho processor nào?” |

Cú pháp là **hai token độc lập**, đúng chính tả và chữ hoa:

```bash
javac -XprintRounds -XprintProcessorInfo ...
```

Đừng viết `@XprintRounds`, `--XprintRounds`, `-XprintRound` hay truyền như option của chương trình qua `java`.

Hai option này thuộc nhóm `-X` của **`javac`**. Có thể kiểm tra option được JDK đang dùng hỗ trợ bằng:

```bash
javac -X
```

Danh sách `-X` có thể khác nhau giữa các JDK. Để kết quả chẩn đoán có ý nghĩa, cần xác nhận đang chạy **đúng `javac` của toolchain build** chứ không chỉ `java` dùng khi chạy ứng dụng.

## 3. Cách đọc thông tin của `-XprintRounds`

Một đoạn **log minh họa theo định dạng quen thuộc của OpenJDK `javac`**:

```text
Round 1:
    input files: {Input}
    annotations: [TraceTag]
    last round: false
Round 2:
    input files: {GeneratedInput}
    annotations: [TraceTag]
    last round: false
Round 3:
    input files: {}
    annotations: []
    last round: true
```

Các dòng trên diễn tả một trường hợp có processor sinh thêm `GeneratedInput.java` ở vòng một. **Đây là ví dụ biểu diễn thông tin, không phải cam kết byte-for-byte của mọi bản JDK**: dấu phân cách, thứ tự, tên kiểu, cách hiển thị hoặc việc có thêm dòng khác có thể thay đổi theo phiên bản và ngữ cảnh.

Các trường quan trọng:

- **`Round N`**: thứ tự vòng xử lý annotation tính trong lượt biên dịch hiện tại.
- **`input files`**: các root/type đầu vào được compiler báo cho round đó; không đồng nghĩa với toàn bộ source file của repository.
- **`annotations`**: các **annotation types** hiện diện trong đầu vào được phát hiện trong round; không phải danh sách giá trị element annotation hay object runtime.
- **`last round: false`**: một vòng xử lý thông thường. Processor có thể phân tích và sinh source/class mới.
- **`last round: true`**: vòng cuối cùng để kết thúc processing. Tương ứng về mặt ý nghĩa với `RoundEnvironment.processingOver()`.

**Số lượng vòng không phải hằng số.** Một processor chỉ phân tích không sinh file có thể chỉ dẫn tới một vòng thông thường cộng vòng kết thúc. Nếu nhiều processor tiếp tục sinh file ở các round kế tiếp, số lượng vòng thông thường có thể tăng. Khi có lỗi build, cách diễn tiến cũng có thể khác một ví dụ không lỗi.

Đừng giả định rằng thấy `last round: true` nghĩa là biên dịch **thành công**: quá trình processing có thể kết thúc sau khi compiler/processor đã phát sinh lỗi.

## 4. Cách đọc `-XprintProcessorInfo`

Option này trả lời “**processor nào được yêu cầu xử lý những loại annotation nào?**”, không trả lời “processor đã tạo file nào?” và cũng không chứng minh processor xử lý đúng logic.

Một dạng output thường gặp của `javac`, dùng làm **minh họa**:

```text
Processor TraceProcessor matches [TraceTag] and returns true.
```

Ý nghĩa các thành phần:

- `TraceProcessor`: processor cụ thể compiler đã chọn/gọi.
- `matches [TraceTag]`: loại annotation mà compiler giao cho processor ở bước ấy.
- `returns true`: khi định dạng này được in, biểu thị giá trị trả về của `process` trong lần xử lý được báo. **`true` nghĩa processor claim loại annotation được giao, không phải build thành công.**

Thông tin cần hiểu đúng:

1. `@SupportedAnnotationTypes(...)` chỉ **khai báo** phạm vi processor hỗ trợ; điều đó không đồng nghĩa processor sẽ được gọi cho mọi annotation trong project.
2. Tập annotation được giao phụ thuộc **round hiện tại, cách lựa chọn processor và claim của các processor trước**.
3. Nếu `process(...)` trả `false`, processor không claim những annotation được giao, vì thế chúng còn có thể được processor khác xử lý.
4. Nếu không có annotation thích hợp, processor không được tìm thấy hoặc annotation processing bị vô hiệu hóa, có thể không xuất hiện dòng tương ứng.
5. Việc processor được in trong log không bảo đảm nó đã gọi `Filer`, đã tạo source hoặc đã ghi lỗi đúng chỗ.

**Không dùng `-XprintProcessorInfo` như công cụ đo thời gian thực thi hoặc bộ đếm độ phức tạp.** Nó là chẩn đoán chọn/giao processor. Muốn biết chính xác một processor sinh file nào, cần quan sát output directory, diagnostic hoặc instrumentation thích hợp.

## 5. Ví dụ hoàn chỉnh Java 17+: bật cả hai tùy chọn

Ví dụ này có **ba file Java do người học tạo**. Processor sẽ tự sinh **file Java thứ tư** trong quá trình biên dịch, nhờ đó ta thấy rõ có nhiều round. Không cần Maven, Gradle hay thư viện ngoài JDK.

Mục tiêu:

- Một class `Input` có `@TraceTag`.
- `TraceProcessor` được chỉ định rõ bằng `-processor`, nhận `@TraceTag`.
- Ở vòng đầu, processor tạo `GeneratedInput.java`, cũng mang `@TraceTag`.
- Ở vòng tiếp theo, compiler xử lý source mới nhưng processor **không tạo thêm file**.
- Cuối cùng có final round, nơi processor không sinh source.

### File 1 — `TraceTag.java`

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface TraceTag {
}
```

Annotation có retention `SOURCE` vì processor cần metadata trong quá trình **biên dịch**, không cần truy vấn lúc runtime.

### File 2 — `TraceProcessor.java`

```java
import java.io.IOException;
import java.io.Writer;
import java.util.Set;

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

@SupportedAnnotationTypes("TraceTag")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class TraceProcessor extends AbstractProcessor {
    private boolean generated = false;

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (round.processingOver()) {
            return true;
        }

        for (Element element : round.getElementsAnnotatedWith(TraceTag.class)) {
            if (element.getKind() != ElementKind.CLASS || generated) {
                continue;
            }

            generated = true;
            try {
                JavaFileObject output = processingEnv.getFiler()
                        .createSourceFile("GeneratedInput", element);

                try (Writer writer = output.openWriter()) {
                    writer.write(
                            "@TraceTag\n"
                            + "public final class GeneratedInput {\n"
                            + "}\n"
                    );
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate source: " + ex.getMessage(),
                        element
                );
            }
        }

        return true;
    }
}
```

Giải thích các chi tiết quan trọng:

- `@SupportedAnnotationTypes("TraceTag")` phù hợp với tên của annotation trong **package mặc định**, chỉ để ví dụ dễ chạy. Trong dự án thật nên dùng package tường minh và tên annotation **đầy đủ**.
- `@SupportedSourceVersion(RELEASE_17)` khai báo source level mà processor hỗ trợ; có thể cập nhật phù hợp khi nâng toolchain.
- `round.getElementsAnnotatedWith(TraceTag.class)` tìm element mang `@TraceTag` ở vòng hiện tại. Processor có thể tham chiếu `TraceTag.class` vì annotation type được biên dịch và có mặt trên processor path.
- `generated` là trạng thái instance để ngăn tạo `GeneratedInput` lần hai. `Filer` không cho tạo trùng cùng source trong một processing run.
- `createSourceFile("GeneratedInput", element)` thông báo nguồn gốc element cho Filer. Source tạo ra là đầu vào cho round kế tiếp, không phải phần tử mới được chèn trực tiếp vào `RoundEnvironment` của lần `process` hiện tại.
- `processingOver()` được kiểm tra trước khi sinh file: final round không mở thêm một vòng annotation processing mới để xử lý file vừa sinh.
- `return true` là **claim** annotation được giao, không phải mã báo thành công của phép ghi file.
- Khi có lỗi I/O, processor báo diagnostic `ERROR` thay vì nuốt exception. Trình biên dịch có thể dừng build theo luồng xử lý lỗi của nó.

Processor **không gọi `System.out.println`**. Nhờ vậy các dòng hiển thị từ hai cờ `-X` sẽ dễ được nhận diện là **diagnostic của javac** chứ không phải output tự in từ ứng dụng.

### File 3 — `Input.java`

```java
@TraceTag
public class Input {
}
```

Class này chỉ là input để processor tìm được marker. Không cần phương thức `main` vì ví dụ kiểm tra **thời gian biên dịch**, không chạy ứng dụng.

### Lệnh chạy trên Linux/macOS hoặc Bash

Mở terminal tại thư mục chứa ba file vừa tạo. Để chạy lại từ đầu, dùng thư mục output mới/trống.

```bash
mkdir -p build generated

javac -encoding UTF-8 -proc:none -d build TraceTag.java TraceProcessor.java

javac -encoding UTF-8 \
    -cp build \
    -processorpath build \
    -processor TraceProcessor \
    -proc:only \
    -s generated \
    -XprintRounds \
    -XprintProcessorInfo \
    Input.java
```

Nếu đang dùng **PowerShell**, có thể tạo thư mục bằng:

```powershell
New-Item -ItemType Directory -Force build, generated | Out-Null
```

Và viết lệnh `javac` thứ hai trên **một dòng** để không phụ thuộc ký tự nối dòng Bash:

```powershell
javac -encoding UTF-8 -cp build -processorpath build -processor TraceProcessor -proc:only -s generated -XprintRounds -XprintProcessorInfo Input.java
```

Lệnh biên dịch đầu sử dụng `-proc:none` để **biên dịch `TraceTag` và `TraceProcessor` thành `.class` trước**, không chạy annotation processor ở bước này. Lệnh thứ hai mới chạy processor tường minh. Cách làm hai bước này loại bỏ nhầm lẫn “vì sao processor chưa tồn tại mà `javac` đã phải gọi nó?”.

Ý nghĩa các option trong lệnh thứ hai:

| Option | Tác dụng |
| --- | --- |
| `-cp build` | Cho compiler nhìn thấy annotation type và những class hỗ trợ đã biên dịch. |
| `-processorpath build` | Chỉ định đường tìm class của annotation processor. |
| `-processor TraceProcessor` | Chọn đúng processor muốn chạy, không phụ thuộc cơ chế service discovery. |
| `-proc:only` | Chạy annotation processing, **không tiếp tục bước biên dịch class ứng dụng**. |
| `-s generated` | Chọn thư mục lưu `.java` do processor phát ra. |
| `-XprintRounds` | In thông tin từng round. |
| `-XprintProcessorInfo` | In thông tin chọn/giao processor. |
| `Input.java` | Source ban đầu chứa `@TraceTag`. |

Sau lệnh thứ hai, trong thư mục `generated` thường có:

```text
generated/
└── GeneratedInput.java
```

Vì dùng `-proc:only`, đừng đòi hỏi lệnh này phải tạo `Input.class` hoặc `GeneratedInput.class`. Nếu muốn tiếp tục biên dịch như ứng dụng thông thường, thay `-proc:only` bằng chế độ processing **và** compilation phù hợp (ví dụ chỉ định processor rõ ràng và bỏ `-proc:only`).

## 6. Đọc kết quả ví dụ theo từng vòng

Với JDK 17 theo thông lệ `javac`, log có thể thể hiện **ba vòng** dưới dạng gần như sau (chỉ minh họa định dạng; không coi là stdout chính xác bất biến):

```text
Round 1:
    input files: {Input}
    annotations: [TraceTag]
    last round: false
Processor TraceProcessor matches [TraceTag] and returns true.
Round 2:
    input files: {GeneratedInput}
    annotations: [TraceTag]
    last round: false
Processor TraceProcessor matches [TraceTag] and returns true.
Round 3:
    input files: {}
    annotations: []
    last round: true
```

Không nên biến các dấu cách, thứ tự dòng hay chính tả biểu diễn `Set` trong đoạn trên thành snapshot test cứng qua nhiều JDK. Hãy **xác minh các bất biến có ý nghĩa**:

1. **Round 1** thấy `Input` mang `@TraceTag`, processor được giao loại annotation đó.
2. Processor tạo `GeneratedInput.java` một lần.
3. **Round 2** thấy `GeneratedInput` có `@TraceTag`, nên đây là dấu hiệu file vừa sinh đã trở thành input round tiếp theo.
4. Ở vòng hai không có source mới, do biến `generated` đã chuyển sang `true`.
5. **Final round** có `last round: true`. Đây là tín hiệu kết thúc vòng đời annotation processing; không được hiểu là một round có thể tùy ý sinh thêm source rồi chờ vòng sau.

Ngoài các dòng do hai option phát ra, `javac` có thể hiển thị thêm warning/error nếu compiler, code nguồn hoặc môi trường có vấn đề. Nếu dùng `-Xlint` hay option khác, số dòng và thứ tự cũng có thể thay đổi.

Muốn so sánh khác biệt, chạy cùng lệnh chỉ bật từng cờ:

```bash
javac -encoding UTF-8 -cp build -processorpath build \
  -processor TraceProcessor -proc:only -s generated -XprintRounds Input.java
```

**Nhớ xóa hoặc đổi thư mục output** `generated` nếu muốn kiểm tra tạo file lại một cách sạch sẽ. Lệnh Filer có thể ghi đè một file từ một compiler invocation trước tùy quy tắc vị trí output, nhưng bên trong một processing run vẫn **không được tạo lặp cùng file**. Để tránh stale source ảnh hưởng chẩn đoán, luôn kiểm tra thư mục output và đầu vào compiler.

So sánh giá trị của hai cờ: `-XprintRounds` cho biết **hành trình dữ liệu qua các vòng**, còn `-XprintProcessorInfo` cho biết **việc giao annotation cho processor**. Khi cần tái hiện lỗi, bật cả hai rồi giữ lại log có version JDK, dòng lệnh, và thông báo lỗi.

## 7. Phân biệt với `-Xprint`, `-proc:only` và `-proc:none`

Các tên khá giống nhau nhưng chức năng khác nhau:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `-XprintRounds` | In thông tin các round annotation processing. |
| `-XprintProcessorInfo` | In thông tin processor được yêu cầu xử lý annotation nào. |
| `-Xprint` | In biểu diễn văn bản của các kiểu theo công cụ, **không thực hiện annotation processing/compilation thông thường**; đây không phải cờ bật trace round. |
| `-proc:only` | Chỉ annotation processing, không thực hiện bước biên dịch tiếp theo; rất tiện khi kiểm chứng processor. |
| `-proc:none` | Tắt annotation processing trong invocation đó. |
| `-processor` | Chỉ định những processor class cần chạy. |
| `-processorpath` | Xác định nơi tìm processor khi sử dụng classpath-style processor loading. |

Một lệnh như:

```bash
javac -proc:none -XprintRounds Input.java
```

không thể dùng để chứng minh processor đang hoạt động, vì `-proc:none` **tắt** annotation processing. Không được kết luận “cờ trace bị lỗi” khi chính invocation đã tắt tính năng cần theo dõi.

Ngược lại:

```bash
javac -processor TraceProcessor \
  -cp build -processorpath build \
  -proc:only -XprintRounds -XprintProcessorInfo Input.java
```

bật processing tường minh và có input phù hợp nên có cơ sở để hiển thị log. Nếu processor được cấu hình không hợp lệ, compiler có thể báo lỗi trước khi tới round.

`-XprintRounds` và `-XprintProcessorInfo` chỉ có tác dụng với **`javac`**; lệnh `java -XprintRounds Input` không chạy annotation processor và không phải cú pháp tương đương.

## 8. Đối chiếu log với `RoundEnvironment`

Hai cờ `-X` cung cấp góc nhìn **bên ngoài processor**. Khi cần xác định điều kiện sinh file hoặc trạng thái phức tạp bên trong, có thể kết hợp với API chuẩn:

```java
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment round) {
    boolean finalRound = round.processingOver();
    boolean priorError = round.errorRaised();

    // ... xử lý theo nhu cầu của processor ...
    return true;
}
```

Đây là đoạn minh họa cần đặt trong class processor, không phải chương trình độc lập. Những API tương ứng:

| Dữ liệu trong log | API/mô hình liên quan |
| --- | --- |
| `last round: true` | `RoundEnvironment.processingOver()` |
| `input files: {...}` | Tập root của round: `RoundEnvironment.getRootElements()` (không phải cam kết chuỗi in giống nhau). |
| `annotations: [...]` | Các annotation xuất hiện trong vòng, cùng quá trình match/giao loại annotation cho processor. |
| Processor nhận loại annotation | Tham số `Set<? extends TypeElement> annotations` trong `process(...)`, theo quy tắc của công cụ chọn processor. |
| Processor `returns true` | Giá trị trả về của `process`: **claim**, không phải exit code của `javac`. |

`RoundEnvironment.errorRaised()` cho biết đã có `ERROR` trong **vòng trước**, không nên sử dụng làm thước đo tức thời cho chính round đang xử lý. `getRootElements()` trả các root của round tương ứng; không được coi là snapshot mọi class trong cả project.

Nếu muốn biết chính xác **tại sao** generator tạo file ở vòng nào, có thể thêm `Messager`:

```java
processingEnv.getMessager().printMessage(
    javax.tools.Diagnostic.Kind.NOTE,
    "Generating source from @TraceTag"
);
```

Đoạn này minh họa code bên trong processor. `Messager` thích hợp cho message gắn với trình biên dịch; log `System.out` của processor và log option `-X` chỉ nên dùng để chẩn đoán khi cần, không làm hợp đồng ứng dụng.

## 9. Những hiện tượng thường gặp khi bật hai cờ

### Chỉ thấy Round 1 và final round

Có thể processor **không sinh source/class mới**, hoặc không có file được xử lý tiếp. Điều đó không tự cho biết processor sai: một processor chỉ kiểm tra annotation thường không cần tạo file.

Nếu dự kiến phải sinh nguồn, kiểm tra điều kiện gọi `Filer`, thông báo `ERROR`, tên output, thư mục `-s`, và việc processor có được giao annotation mong đợi hay không.

### Thấy nhiều round liên tiếp

Nếu mỗi round đều xuất hiện một source file mới, kiểm tra xem processor có đang **tạo đầu ra lặp lại không có điều kiện dừng**. Một lỗi phổ biến là sinh `Generated1`, rồi gặp `Generated1` và sinh `Generated2`, sau đó lại sinh `Generated3` liên tục.

Các cách kiểm soát:
- Giữ set những tên đã xử lý **trong instance processor** cho một compiler invocation.
- Không sinh lại cùng file trong nhiều round.
- Không tạo thêm output nếu generated source đã là kết quả cuối mong muốn.
- Để trace chỉ rõ source mới nào làm phát sinh round kế tiếp.

### Có Round 1 nhưng `-XprintProcessorInfo` không thấy processor mình chờ

Khả năng cần kiểm tra:

1. **Discovery/path**: processor có được biên dịch, có trên processor path và dùng đúng class name không?
2. **Chọn processor**: có `-processor` không? Nếu có, danh sách đúng chưa? Nếu dựa vào service discovery, file `META-INF/services/javax.annotation.processing.Processor` có hợp lệ không?
3. **Supported annotations**: `@SupportedAnnotationTypes` có đúng tên đầy đủ và đúng loại annotation cần xử lý không?
4. **Claim**: một processor trước có thể đã claim annotation đó trong cùng round.
5. **Source level**: `@SupportedSourceVersion` có tương thích với version của mã nguồn/toolchain không?
6. **Input và target**: input có thật sự được annotate tại chỗ `@Target` cho phép không?
7. **Chế độ invocation**: có bị `-proc:none` hoặc cấu hình build tắt processing không?

Không nên cố tìm lỗi ở trong `process(...)` trước khi biết compiler có **chọn và gọi** processor hay không.

### Có `-XprintProcessorInfo` nhưng không có file được sinh

Điều này cũng không chứng minh compiler hoạt động sai. Processor được gọi có thể chỉ làm validation, hoặc điều kiện sinh file không thỏa, hoặc đã phát lỗi. Chỉ số `matches` không phải số file được tạo.

### Log giữa CLI và IDE/build plugin khác nhau

Maven/Gradle/IDE có thể:

- Dùng JDK hoặc compiler khác với terminal.
- Tách processor path/classpath theo cấu hình riêng.
- Chạy incremental compilation nên số root/round khác.
- Lọc, tổng hợp hoặc thay đổi vị trí hiển thị output compiler.
- Dùng compiler implementation không hoàn toàn giống CLI `javac`.

Để cô lập lỗi, ưu tiên một lệnh `javac` trực tiếp với input và processor tối thiểu, bật cả hai option, lưu toàn bộ thông báo compiler rồi mới đưa cấu hình tương đương trở lại công cụ build.

## 10. Làm việc trong Maven, Gradle và CI

Các option thuộc **compiler**, không phải JVM. Khi cấu hình công cụ build cần truyền chúng cho **`javac` invocation** mà công cụ thực sự sử dụng. Cơ chế truyền option có thể khác giữa các phiên bản plugin/build tool, vì vậy không nên coi một đoạn cấu hình của phiên bản cụ thể là cú pháp Java phổ quát.

Các nguyên tắc hữu ích:

1. Xác định toolchain JDK và `javac` version mà build sử dụng.
2. Xác định processor path / processor module path, không chỉ runtime dependencies.
3. Truyền `-XprintRounds` và `-XprintProcessorInfo` vào **compiler arguments** (nơi plugin cho phép), không đưa vào `JAVA_TOOL_OPTIONS` như thể là JVM options.
4. Kiểm tra một clean build khi điều tra số round, tránh output cũ/incremental gây nhiễu.
5. Gắn trace vào phiên debug/CI chẩn đoán thay vì bắt mọi build thông thường in log quá dài.
6. Nếu cần so sánh giữa JDK, ưu tiên sự kiện logic (processor được chọn, generated source hiện diện, có final round) thay vì snapshot cả text.

Chẳng hạn trong một shell, muốn giữ cả stdout và stderr để phân tích:

```bash
javac -cp build -processorpath build -processor TraceProcessor \
  -proc:only -s generated -XprintRounds -XprintProcessorInfo \
  Input.java > processing.log 2>&1
```

`2>&1` là cú pháp chuyển hướng phổ biến trong shell, không phải cờ của `javac`. Sau khi chạy, kiểm tra **exit code** của compiler và đọc log; việc có log rounds không bảo đảm lệnh thoát với mã `0`.

Nếu cần truy vết đúng dữ liệu từng vòng theo cách ổn định hơn định dạng log `-X`, có thể triển khai kiểm tra bằng `RoundEnvironment` và lưu những giá trị cấu trúc do chính processor kiểm soát. Nhưng test cũng cần tránh phụ thuộc số round cố định khi build có nhiều processor tham gia.

## 11. Các hiểu nhầm thường gặp

| Nhầm lẫn | Hiểu đúng |
| --- | --- |
| Hai cờ này phải đặt sau từ khóa `java` | Chúng là tùy chọn **`javac`**, không phải lệnh chạy ứng dụng. |
| `-XprintRounds` in annotation element values | Nó in **thông tin processing round**, không phải giá trị từng `@Annotation(...)`. |
| `-XprintProcessorInfo` in mọi processor có trong classpath | Nó tập trung vào processor **được yêu cầu xử lý annotation**; processor chưa được chọn không nhất thiết xuất hiện. |
| Thấy `returns true` nghĩa là compilation thành công | `true` ở đây là **claim** annotation; build success cần xem lỗi và exit code. |
| Thấy `last round: true` nghĩa là đã chạy xong mọi bước biên dịch class | Final processing round không đồng nghĩa compilation hoàn tất; `-proc:only` còn bỏ bước biên dịch tiếp theo. |
| Tự thêm `@Retention(RUNTIME)` mới đọc annotation trong processor được | `SOURCE` đã đủ cho annotation processing trong lúc biên dịch. |
| `-proc:none -XprintRounds` vẫn phải in round | `-proc:none` **tắt** annotation processing, không còn luồng round cần trace. |
| `-Xprint` chính là dạng rút gọn của `-XprintRounds` | **Không**: hai option có tác dụng khác hẳn nhau. |
| Thấy file generated có nghĩa processor được gọi trong tất cả round | Processor có thể được gọi khác nhau tùy trạng thái selection/claim và input. |
| Log round có text giống nhau trên mọi JDK | Định dạng và các chi tiết cụ thể có thể thay đổi; kiểm tra ngữ nghĩa thay vì raw-string equality. |
| Thấy một lần `process` thì `init` cũng gọi mỗi round | `init` khởi tạo processor trước processing; `process` có thể gọi nhiều round. |
| Nhiều processor luôn có thứ tự và tập annotation y hệt trên mọi build | Phụ thuộc lựa chọn, claim, toolchain và source được tạo qua từng round. |
| `-XprintProcessorInfo` đủ để xác nhận output chính xác | Nó chỉ chứng minh thông tin processor được giao annotation, không chứng minh file sinh đúng nội dung. |

## 12. Bài tập tự kiểm tra

Hãy giả sử compiler báo:

```text
Round 1: Input / @TraceTag / last=false
Round 2: GeneratedInput / @TraceTag / last=false
Round 3: {} / [] / last=true
```

Đây là **cách ghi tắt để suy luận**, không phải format nguyên văn của `javac`.

1. Vì sao có round thứ hai? **Vì có input mới** (`GeneratedInput`) được processor tạo ở round đầu.
2. Cờ nào giúp nhìn thấy chuỗi ba round? **`-XprintRounds`**.
3. Cờ nào cho biết processor đã được giao loại annotation nào? **`-XprintProcessorInfo`**.
4. `last=true` tương ứng phương thức nào? **`RoundEnvironment.processingOver()`**.
5. `returns true` từ `process` có ý nghĩa gì? **Processor claim annotation types được giao**, không chứng minh logic thành công.
6. Một processor chỉ kiểm tra source và không tạo file mới có bắt buộc có ba round như ví dụ? **Không**.
7. `-proc:only` có phát `Input.class` như một build đầy đủ không? **Không**.
8. Nếu muốn debug “không thấy processor trong log”, nên kiểm tra gì trước? **Processor path, tên processor, supported annotation types, mode xử lý và input**.
9. Nếu `@TraceTag` có `RetentionPolicy.SOURCE`, processor có đọc được không? **Có**, vì đang trong thời gian biên dịch.
10. Nếu sau khi có log compiler báo ERROR, có được coi build thành công không? **Không**; phải kiểm tra diagnostic và mã thoát.
11. Vì sao không snapshot toàn bộ output `-XprintRounds` để làm test liên phiên bản JDK? **Vì text là chẩn đoán triển khai, không phải giao thức dữ liệu ổn định**.
12. Tình huống nào cần cả hai cờ? **Khi vừa muốn biết file/annotation vào round nào, vừa muốn biết processor có được giao xử lý annotation đó hay không**.

## 13. Tài liệu tham khảo

- [Oracle Java SE 17 — The `javac` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html), phần Extra Options (`-XprintRounds`, `-XprintProcessorInfo`) và Annotation Processing.
- [Oracle Java SE 21 — The `javac` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html), cùng các option để đối chiếu toolchain JDK mới hơn.
- [Java SE 17 — `javax.annotation.processing.Processor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html), quy tắc processor được giao annotation types, claim, và các vòng xử lý.
- [Java SE 17 — `RoundEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html), đặc biệt `processingOver()`, `getRootElements()` và `errorRaised()`.
- [Java SE 17 — `Filer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html), tạo source mới để compiler xử lý trong các vòng tiếp theo.
