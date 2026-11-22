# Messager và Diagnostic.Kind: báo lỗi, cảnh báo và thông tin trong Java annotation processing

Khi một **annotation processor** kiểm tra cấu hình trong source code, kết quả hữu ích nhất không phải là ném một exception rồi dừng đột ngột, mà là **phát chẩn đoán biên dịch (diagnostic)**: thông báo có mức độ rõ ràng, mô tả vi phạm và, nếu có thể, trỏ về đúng khai báo trong tệp nguồn. Java cung cấp hai API nền tảng:

- `javax.annotation.processing.Messager` — giao diện mà processor sử dụng để **gửi diagnostic** đến môi trường xử lý/compilation.
- `javax.tools.Diagnostic.Kind` — enum mô tả **mức độ hoặc loại diagnostic**, đặc biệt `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE` và `OTHER`.

Một ví dụ ngắn nằm **bên trong annotation processor**:

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "required field must have type String",
        fieldElement);
```

Ở đây, `fieldElement` là một `javax.lang.model.element.Element` biểu diễn khai báo field đang bị kiểm tra. `Messager` giúp đưa lỗi vào hệ thống compiler và trỏ thông báo tới phần tử có liên quan. **`ERROR` có ý nghĩa làm quá trình biên dịch thất bại**; `WARNING`/`NOTE` nói chung chỉ báo thông tin mà không mặc nhiên khiến compile thất bại.

Bài học tập trung vào ngữ nghĩa chuẩn của từng mức thông báo, cách lấy `Messager` từ processor, các overload của `printMessage`, cách gắn source location, ảnh hưởng tới build/CI, những lỗi phổ biến và một ví dụ Java 17 có thể biên dịch để nhìn thấy sự khác biệt thật.

## 1. Diagnostic là gì và liên quan thế nào đến annotation processor?

**Diagnostic** là một thông báo được công cụ biên dịch phát ra nhằm cho người lập trình biết tình trạng của source: lỗi, cảnh báo hoặc thông tin. `javac` tự phát diagnostic của Java Core (sai kiểu, cú pháp, thành viên không tìm thấy...). Annotation processor cũng có thể bổ sung diagnostic **theo quy tắc riêng của ứng dụng hoặc thư viện**.

Ví dụ, annotation:

```java
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.FIELD)
@interface CheckedField {
    boolean required() default false;
}
```

không tự khiến `javac` đòi một field có kiểu `String`. Nếu muốn áp quy tắc “field `@CheckedField(required=true)` phải có kiểu `String`”, processor cần:

1. Tìm những field đang gắn annotation tương ứng trong processing round.
2. Đọc metadata, kiểm tra kiểu field.
3. Nếu không hợp lệ, gửi `Diagnostic.Kind.ERROR` qua `Messager` để compilation thất bại.
4. Nếu không nghiêm trọng, có thể gửi `WARNING`; nếu chỉ cần ghi nhận tiến trình, có thể gửi `NOTE`.

**Chỉ khai báo annotation không tự tạo quy tắc**. `Messager` là công cụ *phát thông báo*; logic quyết định “lúc nào báo, báo loại gì” do code processor hoặc công cụ khác xây dựng.

## 2. Lấy Messager đúng cách

Trong `AbstractProcessor`, trường được kế thừa `processingEnv` có kiểu `ProcessingEnvironment`. Nó cung cấp `Messager`:

```java
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.lang.model.element.TypeElement;
import java.util.Set;

public class ExampleProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {

        var messager = processingEnv.getMessager();
        // messager.printMessage(...)
        return true;
    }
}
```

Đây là **khung minh họa**, chưa phải processor hoạt động đầy đủ: để chạy bằng `javac` cần khai báo supported annotation types/source version, cấu hình processor trên command line hoặc build tool và có input liên quan. Ví dụ hoàn chỉnh ở phần 5.

Các thành phần thường đi cùng:

| Thành phần | Vai trò |
|---|---|
| `AbstractProcessor` | Cung cấp lifecycle và `processingEnv` |
| `ProcessingEnvironment.getMessager()` | Lấy đối tượng phát diagnostic |
| `RoundEnvironment.getElementsAnnotatedWith(...)` | Tìm khai báo được gắn annotation trong round |
| `Element` | Mô hình vị trí khai báo như class, method, field, parameter |
| `AnnotationMirror` | Mô hình một annotation có mặt trên element |
| `AnnotationValue` | Mô hình giá trị của một element thuộc annotation |
| `Diagnostic.Kind` | Phân loại ERROR/WARNING/NOTE... |
| `Messager.printMessage(...)` | Phát thông báo cùng ngữ cảnh, có thể kèm vị trí nguồn |

`Messager` không phải `java.util.logging.Logger`, và cũng không phải `System.out.println`. Nó được thiết kế cho **kênh chẩn đoán biên dịch** mà compiler, IDE hoặc build tool có thể tiếp nhận. Kết quả trình bày cụ thể (màu sắc, đường dẫn, dòng/cột, đếm lỗi...) có thể thay đổi theo công cụ.

## 3. Diagnostic.Kind: các mức độ có nghĩa gì?

Java SE 17 có các hằng enum sau:

| `Diagnostic.Kind` | Ý nghĩa cơ bản | Hậu quả phổ biến với `javac` |
|---|---|---|
| `ERROR` | **Lỗi** khiến kết quả compilation không thể coi là thành công | Compiler báo `error:`, exit code khác 0 |
| `WARNING` | Cảnh báo về vấn đề cần lưu ý nhưng không nhất thiết là lỗi Java | Thường báo `warning:`; compile vẫn có thể thành công |
| `MANDATORY_WARNING` | Cảnh báo thuộc nhóm **bắt buộc phải được báo**, theo hợp đồng diagnostic | Có thể hiển thị là `warning:`, không nhất thiết khác WARNING về mặt chuỗi |
| `NOTE` | Thông tin hoặc lời nhắn hướng dẫn, không phải lỗi/cảnh báo | Thường báo `Note:` |
| `OTHER` | Diagnostic không thuộc những loại trên | Phân loại chung; không nên dựa vào một cách trình bày cố định |

### ERROR — từ chối input sai

```java
messager.printMessage(
        Diagnostic.Kind.ERROR,
        "Field is not a String",
        field);
```

Dùng khi nguồn được xử lý **vi phạm hợp đồng bắt buộc**: ví dụ annotation được gắn vào khai báo không được framework hỗ trợ, tên giá trị trùng làm không thể sinh mã, hoặc một tham số annotation thiếu điều kiện cần thiết. Dù compiler có thể tiếp tục gọi processor trong một số bước để hoàn tất việc xử lý, **kết quả compilation không thành công** vì đã báo error.

`ERROR` không đồng nghĩa lập tức `throw` exception trong method `process`. Nó là diagnostic được compiler ghi nhận. Vì vậy đừng trông chờ việc gọi `printMessage(ERROR, ...)` sẽ tự động thoát khỏi phần còn lại của `process`; nếu dữ liệu không hợp lệ, code phải chủ động bỏ qua những bước không an toàn.

### WARNING — vấn đề nên sửa nhưng có thể tiếp tục

```java
messager.printMessage(
        Diagnostic.Kind.WARNING,
        "Provide a reason for this annotation",
        field);
```

Hợp lý khi vi phạm không làm cấu hình vô nghĩa, nhưng có thể dẫn tới code khó bảo trì, dùng API lỗi thời hoặc cấu hình thiếu minh bạch. Một compile có warning vẫn có thể ra exit code 0. Tuy nhiên nếu dự án bật `-Werror`, warning có thể khiến compilation thất bại dù processor không gửi `ERROR` trực tiếp.

### MANDATORY_WARNING — cảnh báo bắt buộc

```java
messager.printMessage(
        Diagnostic.Kind.MANDATORY_WARNING,
        "Legacy declaration requires migration",
        field);
```

Loại này là **mandatory warning**, không phải “một mức ưu tiên thấp hơn ERROR nhưng cao hơn WARNING” theo một thứ tự số học nào đó. Nó có yêu cầu riêng về việc thông báo cảnh báo; output của `javac` trong ví dụ thực tế vẫn hiển thị `warning:`. Để phân biệt ý nghĩa, phải nhìn loại diagnostic đã truyền, không chỉ đọc một dòng console.

Không phải mọi cảnh báo nghiệp vụ đều cần thành mandatory. Hãy chọn nó có chủ đích; một cảnh báo tùy nghi từ processor có thể dùng `WARNING` thông thường.

### NOTE — tiến trình, thông tin bổ sung

```java
messager.printMessage(
        Diagnostic.Kind.NOTE,
        "Generated configuration source successfully",
        element);
```

Hữu ích khi muốn người dùng biết processor đã đọc bao nhiêu khai báo hoặc tạo ra artifact nào. Tránh phát một NOTE cho mọi chi tiết không quan trọng trên project lớn: log có thể quá dài và che khuất diagnostic thực sự cần hành động. NOTE không có nghĩa “compilation đã chắc chắn thành công”; đó chỉ là thông tin tại thời điểm được phát.

### OTHER — không thuộc bốn nhóm thông thường

`OTHER` tồn tại trong `Diagnostic.Kind` để biểu diễn diagnostic không thuộc ERROR/WARNING/MANDATORY_WARNING/NOTE. Với bài toán báo lỗi hoặc thông báo của processor thông thường, bốn nhóm đầu là những lựa chọn dễ hiểu nhất. Không nên giả định một IDE hoặc compiler sẽ tô màu hoặc đếm `OTHER` giống `NOTE`; công cụ tiêu thụ diagnostic quyết định cách trình bày của nhóm không chuyên biệt này.

## 4. Bốn overload của Messager.printMessage

`Messager` định nghĩa những dạng gọi sau:

```java
printMessage(Diagnostic.Kind kind, CharSequence msg)

printMessage(Diagnostic.Kind kind, CharSequence msg,
             Element e)

printMessage(Diagnostic.Kind kind, CharSequence msg,
             Element e, AnnotationMirror a)

printMessage(Diagnostic.Kind kind, CharSequence msg,
             Element e, AnnotationMirror a, AnnotationValue v)
```

**1. Chỉ kind + message**

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.NOTE,
        "Analyzing configuration...");
```

Không gắn rõ nguồn nào; log có thể thiếu đường dẫn/file/dòng cụ thể. Thích hợp cho thông báo toàn bộ processor hoặc kết quả tổng hợp.

**2. Thêm Element**

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Unsupported field type",
        fieldElement);
```

Cố gắng gắn thông báo với **khai báo** được biểu diễn bởi `Element`, ví dụ tên field. Đây là overload rất hữu ích khi muốn người lập trình bấm vào lỗi trong IDE và đến gần chỗ cần sửa.

**3. Thêm AnnotationMirror**

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Unsupported annotation",
        fieldElement,
        annotationMirror);
```

Cung cấp ngữ cảnh của **chính lần sử dụng annotation** trên một phần tử. Phù hợp khi một element có nhiều annotation và chỉ một annotation gây vấn đề. Cần lấy `AnnotationMirror` thực sự liên quan đến `fieldElement`.

**4. Thêm AnnotationValue**

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "This value must not be blank",
        fieldElement,
        annotationMirror,
        annotationValue);
```

Thêm ngữ cảnh của **một giá trị annotation cụ thể**, ví dụ chuỗi `reason = ""`. Nếu compiler có vị trí tương ứng, nó có thể chỉ ra chính vùng giá trị gây lỗi.

Điều quan trọng: các overload có `Element`/`AnnotationMirror`/`AnnotationValue` cung cấp thông tin để **công cụ cố gắng** gắn đúng vị trí nguồn. Javadoc không hứa rằng tất cả compiler, IDE hoặc mọi loại element đều in cùng vị trí cột; với synthetic elements, metadata từ binary hoặc giá trị default, tọa độ có thể kém chính xác. Do đó nên kiểm thử trên toolchain thực tế.

### Cách tìm AnnotationMirror và AnnotationValue

Một processor có thể duyệt metadata:

```java
for (AnnotationMirror mirror : field.getAnnotationMirrors()) {
    if (!mirror.getAnnotationType().toString()
            .equals("org.example.CheckedField")) {
        continue;
    }
    for (var entry : mirror.getElementValues().entrySet()) {
        if (entry.getKey().getSimpleName().contentEquals("reason")) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Reason is invalid",
                    field,
                    mirror,
                    entry.getValue());
        }
    }
}
```

Đây là **đoạn minh họa bên trong processor**: `field` là `Element` của khai báo có annotation, `org.example.CheckedField` là tên đầy đủ giả định của annotation trong dự án. `getElementValues()` chỉ bao gồm những element được viết tường minh, không tự liệt kê mọi giá trị `default`. Nếu muốn tra cả default, có thể dùng `processingEnv.getElementUtils().getElementValuesWithDefaults(mirror)`.

Nếu người viết bỏ `reason` và dùng giá trị mặc định rỗng, bạn có thể **đọc được giá trị mặc định** nhưng không có vị trí source ứng với một cặp `reason = ...` do người dùng không hề viết. Trong trường hợp đó hãy gắn lỗi ở `AnnotationMirror` hoặc `Element` thay vì giả định luôn chỉ được chính xác một `AnnotationValue` trong source.

## 5. Chương trình Java 17+ hoàn chỉnh: NOTE, WARNING, MANDATORY_WARNING và ERROR

Thí nghiệm tạo một annotation và processor tự kiểm tra ba điều kiện. Ta biên dịch một input hợp lệ và một input không hợp lệ để quan sát cả **diagnostic** lẫn **exit code**.

Đặt bốn file bên dưới trong **cùng một thư mục trống**. Ví dụ cố tình dùng default package để lệnh `javac` ngắn; dự án thực tế nên sử dụng package có tên.

### File 1 — CheckedField.java

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.FIELD)
public @interface CheckedField {
    String reason() default "";
    boolean required() default false;
}
```

- `SOURCE` đủ để annotation processor đọc khi biên dịch file Java đang được xử lý.
- `FIELD` chỉ cho phép gắn annotation lên khai báo field.
- `reason()` là chuỗi giải thích; `required()` biểu thị yêu cầu nghiệp vụ trong ví dụ.

Bản thân định nghĩa `@CheckedField` **không buộc field phải có String**, cũng không bắt buộc nhập `reason` vì hai element đều có giá trị default. Những quy tắc được phát triển ở processor phía dưới.

### File 2 — FieldCheckProcessor.java

```java
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("CheckedField")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class FieldCheckProcessor extends AbstractProcessor {
    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        for (Element field :
                round.getElementsAnnotatedWith(CheckedField.class)) {

            CheckedField config = field.getAnnotation(CheckedField.class);

            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.NOTE,
                    "checking field " + field.getSimpleName(),
                    field);

            if (config.reason().isBlank()) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.WARNING,
                        "document the reason",
                        field);
            }

            if (field.getSimpleName().toString().startsWith("legacy")) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.MANDATORY_WARNING,
                        "legacy field needs migration",
                        field);
            }

            if (config.required()
                    && !field.asType().toString()
                            .equals("java.lang.String")) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "required field must have type String",
                        field);
            }
        }
        return true;
    }
}
```

Các bước:

1. `@SupportedAnnotationTypes("CheckedField")` thông báo processor hỗ trợ annotation này. Vì ví dụ dùng default package, tên đơn giản `CheckedField` là tên type đúng; khi chuyển sang package, dùng **fully qualified name** tương ứng.
2. `@SupportedSourceVersion(RELEASE_17)` cho biết mức source version processor hỗ trợ.
3. `getElementsAnnotatedWith(CheckedField.class)` lấy những element gắn `@CheckedField` nằm trong round hiện tại. `@Target(FIELD)` bảo đảm ví dụ của chúng ta chỉ dùng annotation ở field.
4. `config.reason().isBlank()` phát `WARNING` khi chưa giải thích; đây là lựa chọn của processor, không phải quy tắc Java Core.
5. Tên field bắt đầu bằng `legacy` phát `MANDATORY_WARNING`; đây cũng chỉ là luật minh họa.
6. Field đánh dấu `required=true` nhưng có kiểu khác `java.lang.String` phát `ERROR`. Demo kiểm tra tên kiểu thông qua `TypeMirror.toString()` cho dễ hiểu. **Trong processor sản xuất**, nên dùng `Types.isSameType` và `Elements.getTypeElement(...)` để so sánh kiểu thay vì so sánh chuỗi, vì generic, alias, declared/error types và các cấu hình phức tạp không được xử lý đúng chỉ bằng `toString()`.
7. `return true` nghĩa là processor tuyên bố đã xử lý (*claim*) annotation types được giao cho nó trong round. Nó **không** làm compiler thành công nếu có `ERROR` và cũng không thay cho việc dừng xử lý nhánh lỗi.

### File 3 — ValidData.java

```java
class ValidData {
    @CheckedField(reason = "identifier", required = true)
    String id;

    @CheckedField
    int count;

    @CheckedField(reason = "backward compatibility")
    String legacyCode;
}
```

`id` hợp lệ, có reason và đúng String khi required. `count` không có reason nên chỉ tạo warning. `legacyCode` tạo mandatory warning vì quy tắc tên field.

### File 4 — InvalidData.java

```java
class InvalidData {
    @CheckedField(required = true)
    int id;
}
```

Field `id` có `required=true` nhưng kiểu `int`, nên processor gửi `ERROR`. Đồng thời nó cũng thiếu `reason`, do vậy có warning.

### Lệnh biên dịch và quan sát

Ở thư mục chứa bốn file, trước tiên compile annotation và processor:

```bash
javac --release 17 CheckedField.java FieldCheckProcessor.java
```

Sau đó biên dịch từng input, tránh ghép chúng làm một để dễ đọc mức độ chẩn đoán:

```bash
javac --release 17 -cp . -processorpath . -processor FieldCheckProcessor ValidData.java

javac --release 17 -cp . -processorpath . -processor FieldCheckProcessor InvalidData.java
```

**Kết quả với ValidData.java:** exit code **0** (thành công), dù có hai warning. Trích phần diagnostic có ý nghĩa từ lần chạy Java 17:

```text
ValidData.java:3: Note: checking field id
ValidData.java:6: Note: checking field count
ValidData.java:6: warning: document the reason
ValidData.java:9: Note: checking field legacyCode
ValidData.java:9: warning: legacy field needs migration
2 warnings
```

Trong console thực tế, compiler còn in thêm dòng khai báo field và dấu `^` chỉ vị trí; thứ tự và chi tiết dòng/cột có thể khác giữa IDE, JDK và processor khác. Output trên là **phần chẩn đoán tóm lược**, không phải toàn bộ byte-for-byte của console.

**Kết quả với InvalidData.java:** exit code **khác 0** (thất bại). Trích phần diagnostic từ Java 17:

```text
InvalidData.java:3: Note: checking field id
InvalidData.java:3: warning: document the reason
InvalidData.java:3: error: required field must have type String
1 error
1 warning
```

**Điều thí nghiệm chứng minh:** một processor có thể sinh ra warning và note mà vẫn biên dịch thành công. Khi nó gửi `Diagnostic.Kind.ERROR`, compilation thất bại. Dù `MANDATORY_WARNING` là một enum khác `WARNING`, phần console trong ví dụ đều hiển thị là `warning:`.

Đây là chương trình chạy *trong compiler*, không phải ứng dụng có `public static void main` để gọi `java FieldCheckProcessor`. Annotation processor được `javac` nạp và gọi thông qua `-processor`.

## 6. Gắn thông báo vào đúng vị trí nguồn: vì sao nên truyền Element?

So sánh:

```java
// Thông báo chung, thường không có vị trí field.
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Invalid field");

// Thông báo gắn với khai báo field.
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Invalid field",
        field);
```

Với overload có `field`, `javac` có thể hiển thị tên tệp, dòng khai báo, dấu `^` bên dưới tên trường. Chức năng này quan trọng với hàng trăm field: thay vì “Invalid field” chung chung, người lập trình biết **phải sửa đâu**.

Khi cấu hình nằm trong một phần tử của annotation:

```java
@Constraint(min = -1, max = 10)
int quantity;
```

Một diagnostic tốt có thể gắn vào **`AnnotationValue` của `min`** nếu ta có `Element`, `AnnotationMirror` và `AnnotationValue` phù hợp. Tuy nhiên lỗi liên quan tới **hai giá trị** (ví dụ min lớn hơn max) có thể phù hợp hơn nếu gắn vào annotation hoặc cả declaration, kèm giải thích rõ quan hệ cần sửa. Tránh cung cấp một vị trí “rất chính xác” nhưng lại là vị trí sai về ngữ nghĩa.

Mẹo chất lượng:

- Dùng thông điệp có **động từ và điều kiện rõ**: `"required field must have type String"` tốt hơn `"invalid"`.
- Nêu **giá trị quan sát được** và **giá trị kỳ vọng** khi cần: `"expected String, found int"`.
- Gắn `Element` tương ứng; dùng overload sâu hơn khi có annotation mirror/value thực.
- Đặt mã thông báo/hậu tố dễ tìm kiếm nếu tổ chức có quy ước, nhưng không làm message khó đọc.
- Không bắt người dùng phải mở source của processor mới hiểu cách sửa.

## 7. printMessage(ERROR) khác throw Exception

Một trong những nhầm lẫn lớn nhất là xem:

```java
messager.printMessage(Diagnostic.Kind.ERROR, "Invalid", element);
```

như `throw new IllegalStateException(...)`.

**Chúng khác nhau:**

| Phương pháp | Ý nghĩa | Tác động chính |
|---|---|---|
| `printMessage(ERROR, ..., e)` | Chẩn đoán lỗi nguồn theo hợp đồng xử lý | Compiler đánh dấu có error, nguồn người dùng được chỉ ra |
| `throw new RuntimeException(...)` | Processor gặp ngoại lệ chưa được xử lý | Có thể khiến chính processor/compiler task thất bại với stack trace, thông tin lỗi người dùng kém thân thiện |
| `printMessage(WARNING, ..., e)` | Cảnh báo khuyến nghị | Compiler có thể tiếp tục thành công tùy flags |
| `System.out.println(...)` | In ra output thông thường | Không được tự coi là diagnostic và không tự làm compile fail |

Nên phát `ERROR` cho **source input không hợp lệ**, sau đó chủ động tránh sinh code sai. Chỉ ném exception cho lỗi nội bộ thật sự không thể xử lý một cách có kiểm soát (ví dụ bất biến trong implementation của processor bị phá), và khi thích hợp chuyển thành diagnostic dễ hiểu.

Chẳng hạn:

```java
if (!isValid(element)) {
    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.ERROR,
            "Invalid declaration for code generation",
            element);
    continue; // Bỏ qua element không hợp lệ.
}
generateSource(element); // Chỉ chạy cho element hợp lệ.
```

Đoạn này là **pseudocode Java trong vòng lặp processor**, cần có `isValid` và `generateSource` tương ứng trong chương trình thực tế. Ý chính: `printMessage(ERROR)` không tự dừng thực thi các dòng code phía sau.

## 8. -Werror, -nowarn và cờ của compiler

Mức độ diagnostic còn liên quan đến cấu hình build. Với `javac`:

**`-Werror`:** xem warning là nguyên nhân để compilation thất bại. Với cùng `ValidData.java` ở ví dụ trên, chạy:

```bash
javac --release 17 -Werror -cp . -processorpath . \
    -processor FieldCheckProcessor ValidData.java
```

Đây là cú pháp xuống dòng dành cho shell hỗ trợ backslash continuation; trong PowerShell/cmd trên Windows, hãy dùng một dòng duy nhất hoặc cú pháp nối dòng đúng của shell:

```bash
javac --release 17 -Werror -cp . -processorpath . -processor FieldCheckProcessor ValidData.java
```

Vì processor đưa warning, compilation có thể thất bại dưới `-Werror` dù mọi field đều không vi phạm điều kiện `ERROR` của processor. Khi chẩn đoán build thất bại, hãy kiểm tra **các compiler flags**, không chỉ source Java.

**`-nowarn` / `-Xlint:none`:** có thể điều khiển việc hiển thị một số cảnh báo do compiler phát, nhưng **đừng coi chúng là bộ lọc có thể vô hiệu hóa mọi diagnostic từ mọi processor và mọi mandatory warning**. Hành vi có thể khác giữa mức loại diagnostic và implementation. Nếu một quy tắc nghiệp vụ phải chặn build, dùng `ERROR`; không trông chờ vào policy hiển thị warning bên ngoài.

**`-Xmaxerrs N` / `-Xmaxwarns N`:** giới hạn số lượng diagnostics được trình bày bởi `javac` trong các loại tương ứng. Một build nhiều lỗi có thể chỉ hiển thị một phần nếu giới hạn thấp.

**`-Xlint`:** cho phép bật/tắt những nhóm cảnh báo `javac` biết đến. Không phải vì `-Xlint:all` được bật mà annotation processor tùy chỉnh sẽ tự động tồn tại hoặc mọi rule sẽ tự chạy.

Một nguyên tắc vận hành tốt: cấu hình **processor discovery**, processor path và warning-as-error tại build/CI; đừng dựa vào việc “máy tôi build xanh” nếu IDE không chạy processor.

## 9. Kết hợp với RoundEnvironment và processing rounds

Processor được gọi qua nhiều round nếu trong quá trình xử lý có source/class được tạo. Với mỗi lần `process`:

```java
boolean over = roundEnv.processingOver();
boolean raisedBefore = roundEnv.errorRaised();
```

- `processingOver()` cho biết vòng hiện tại là vòng kết thúc của annotation processing; source được tạo trong vòng kết thúc sẽ không được đem xử lý ở vòng tiếp theo.
- `errorRaised()` cho biết **có lỗi phát sinh trong vòng trước**; không nên suy từ `false` ra kết quả cuối compilation sẽ thành công.

Một pattern phòng ngừa:

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {

    if (roundEnv.processingOver()) {
        return true;
    }

    for (Element e :
            roundEnv.getElementsAnnotatedWith(CheckedField.class)) {
        validateAndReport(e);
    }
    return true;
}
```

Đây là skeleton minh họa: `validateAndReport` cần được định nghĩa trong processor và dùng `Messager`. Nếu tác vụ cần in báo cáo tổng kết ở final round, nó có thể làm điều đó, nhưng đừng tự động **lặp lại toàn bộ lỗi của các vòng trước** chỉ vì bước tổng kết chạy thêm một lần.

### Tránh báo trùng trên cùng input

Nếu processor quét `RoundEnvironment` theo round và lưu trạng thái, cần xác định element nào đã được xử lý. Ví dụ một generator có thể tạo thêm source, mở một round mới; nếu thiết kế scan sai và quét lại mọi type cũ, cùng một lỗi có thể được in nhiều lần. Nên giới hạn theo các element hiện diện trong round hoặc sử dụng định danh/cơ chế deduplication rõ ràng.

Không mặc định một classpath scan tùy ý có thứ tự ổn định. Tập `Set<? extends Element>` không hứa thứ tự iteration, nên nếu diagnostic cần thứ tự deterministic, hãy sắp xếp theo một khóa phù hợp. Đừng gắn logic “dòng warning đầu tiên là quan trọng nhất” vào thứ tự ngẫu nhiên.

### ERROR và source generation

Nếu một annotation không hợp lệ khiến code generation không thể tạo ra output đúng, tốt hơn là:

1. Phát diagnostic `ERROR` tại nguồn vi phạm.
2. Đánh dấu input bị lỗi và bỏ qua việc tạo output cho input đó.
3. Cho compiler xử lý failure theo lifecycle của annotation processing.

Tránh vừa phát `ERROR` vừa tạo source không hợp lệ, khiến người dùng nhận thêm hàng chục error phụ khó xác định nguyên nhân gốc.

## 10. NOTE và các thông báo tiến trình cần sử dụng hợp lý

Diagnostic `NOTE` không vô hại tuyệt đối về mặt trải nghiệm: processor của một dự án lớn có thể chạy trên hàng nghìn phần tử. Nếu mọi phần tử phát ba NOTE, console/CI log trở nên ồn và che khuất cảnh báo quan trọng.

Lựa chọn thực tế:

- NOTE ít và có ý nghĩa ở mốc bắt đầu/kết thúc hoặc khi sinh artifact quan trọng.
- WARNING khi có rủi ro thật sự và người dùng có thể hành động.
- ERROR khi input không đáp ứng hợp đồng bắt buộc.
- MANDATORY_WARNING chỉ khi thật sự cần semantic cảnh báo bắt buộc.
- Hạn chế lặp diagnostic qua các rounds hoặc nhiều processor.

Nếu cần debug chi tiết, cân nhắc tùy chọn processor (ví dụ `-AmyProcessorDebug=true`) và chỉ phát NOTE chi tiết khi debug được bật. Khi dùng annotation processor option dạng `-Akey=value`, code cần khai báo supported options hoặc xử lý sao cho compiler/build biết nó là tùy chọn được hỗ trợ; không tự nhận bất kỳ key nào như một cờ Java chuẩn.

**Không có quy định rằng NOTE phải đứng trước WARNING hoặc ERROR.** Các compiler/IDE có thể nhóm/sắp xếp diagnostics theo cách khác nhau. Đối với integration test, nên xác minh mức độ và nội dung trọng tâm thay vì phụ thuộc toàn bộ output byte-for-byte và thứ tự nếu toolchain không cố định.

## 11. Vấn đề @SuppressWarnings và diagnostic tùy chỉnh

`@SuppressWarnings` là annotation chuẩn để các compiler/tool bỏ qua một số cảnh báo có khóa nhất định. Nhưng:

**Việc processor tự gọi `Messager.printMessage(WARNING, ...)` không tự tạo một `-Xlint` warning category hay quy tắc suppression cho `@SuppressWarnings("custom-key")`.**

Nếu muốn người dùng tắt một cảnh báo tùy chỉnh của processor ở một phạm vi nhất định, cần:

1. Định nghĩa khóa suppression và các loại diagnostic nào được phép suppress.
2. Trước khi phát warning, processor đọc `@SuppressWarnings` hoặc annotation cấu hình riêng theo quy tắc đã công bố.
3. Chỉ bỏ qua warning phù hợp, không làm mất error bắt buộc.
4. Kiểm thử scope (class, method, field) và precedence một cách nhất quán.

Đừng kỳ vọng `@SuppressWarnings("unchecked")` mặc định xóa cảnh báo `"document the reason"` trong ví dụ. Hai cảnh báo thuộc hai cơ chế độc lập.

Nếu warning thực sự là vấn đề nghiêm trọng ảnh hưởng tính đúng đắn, hãy chọn `ERROR` thay vì dựa vào một cảnh báo dễ bị bỏ qua. Ngược lại, không nên lạm dụng ERROR cho mọi vấn đề về style hoặc gợi ý cải thiện.

## 12. Tại sao thông báo từ IDE và javac có thể khác nhau?

Java định nghĩa mô hình `Messager`/`Diagnostic.Kind`, nhưng các công cụ tiêu thụ diagnostic có thể khác:

- **javac CLI** thường in nguồn, dòng, `^`, message và số lượng errors/warnings.
- **IDE** có thể trình bày marker/gutter, Problems view, quick navigation, hoặc chỉ chạy processor khi annotation processing được bật.
- **Build tool** như Maven/Gradle có thể gom diagnostic, thêm prefix, lọc log, chạy incremental compilation, hoặc bọc output của compiler.
- **Compiler API** có thể cho client nhận diagnostic qua `DiagnosticListener` tùy cách tích hợp.

Do đó hãy viết thông báo có đủ nội dung tự giải thích, ngay cả khi IDE không gắn chính xác vào tên element. Thông báo kiểu `"invalid value"` không có ngữ cảnh khó xử lý hơn `"@CheckedField(required=true) requires java.lang.String, found int"`.

Trong test tự động, kiểm tra:

- Input hợp lệ có exit code thành công.
- Input vi phạm ERROR có exit code thất bại.
- WARNING và NOTE xuất hiện theo rule đã kích hoạt.
- Tệp/dòng hoặc element hợp lý được báo nếu toolchain hỗ trợ.
- Không có diagnostic trùng lặp không chủ ý sau các rounds.
- Tool chạy trên JDK/compiler version mà dự án thật sử dụng.

Nếu toolchain thay đổi format hiển thị, các phép kiểm tra ngữ nghĩa vẫn có thể đứng vững.

## 13. Một số lỗi dùng Messager thường gặp

### Lỗi 1 — In System.out rồi cho rằng build sẽ thất bại

```java
System.out.println("ERROR: invalid annotation");
```

Đây là chuỗi trên console, không phải `Diagnostic.Kind.ERROR`. Muốn compiler biết có lỗi, dùng `processingEnv.getMessager().printMessage(ERROR, ..., element)`.

### Lỗi 2 — Gọi ERROR rồi tiếp tục generate code từ dữ liệu sai

`printMessage(ERROR)` không tự chặn các dòng Java còn lại trong `process`. Cần `continue`, `return` hoặc nhánh điều khiển hợp lý để không sinh source lỗi.

### Lỗi 3 — Báo lỗi chung không có Element

`printMessage(ERROR, "Invalid")` có thể thiếu vị trí sửa; nên truyền `Element` đúng. Khi muốn chỉ ra một cặp annotation cụ thể, cân nhắc thêm `AnnotationMirror` và `AnnotationValue`.

### Lỗi 4 — Cho rằng WARNING luôn không làm hỏng build

Bật `-Werror` có thể khiến compile fail. Nếu CI yêu cầu không warning, build có thể thất bại dù code processor chỉ phát WARNING.

### Lỗi 5 — Dùng MANDATORY_WARNING như ERROR

`MANDATORY_WARNING` vẫn là **warning kind**, không phải lỗi bắt buộc làm compile thất bại trong mọi cấu hình. Nếu cần ràng buộc buộc compilation thất bại, dùng ERROR.

### Lỗi 6 — Nhầm NOTE với log debug tùy ý

NOTE có thể xuất hiện với số lượng lớn và làm log khó đọc. Một processor chạy trên nhiều module nên tránh gửi NOTE cho từng field trừ khi đang debug.

### Lỗi 7 — Tin rằng -Xlint:all tự kích hoạt processor

`-Xlint:all` chỉ liên quan tới nhóm cảnh báo javac hỗ trợ. Annotation processor cần được discover/cấu hình; các API `Messager` không tự được gọi nếu processor không chạy.

### Lỗi 8 — Dùng Element/AnnotationValue không tương ứng

Nếu truyền `AnnotationMirror` không gắn trên `Element` đang nói tới, hoặc `AnnotationValue` không thuộc mirror đó, vị trí source có thể không hữu ích. Luôn lấy metadata từ chính declaration đã kiểm tra.

### Lỗi 9 — Báo trùng giữa các rounds

Quét lại tất cả source và gửi cùng warning/error ở mỗi round gây rối và có thể làm test không ổn định. Tổ chức processing theo round, đồng thời chỉ xử lý mỗi khai báo cần thiết một cách nhất quán.

### Lỗi 10 — So kiểu Java bằng toString trong code production

Trong ví dụ `required=true`, `field.asType().toString().equals("java.lang.String")` được dùng cho minh họa. Đối với type checking thực tế, nên dùng `Types.isSameType`, `Types.isAssignable` hoặc thao tác tương thích với `TypeMirror` để không phụ thuộc biểu diễn chuỗi.

### Lỗi 11 — Xem default value như source element được ghi rõ

Một annotation element không xuất hiện tường minh có thể có default. Diagnostic vẫn cần báo được vi phạm, nhưng không có cặp literal nguồn để gắn chính xác. Hãy báo ở annotation hoặc khai báo chứa annotation.

### Lỗi 12 — Dùng throw cho lỗi input bình thường

Exception chưa được xử lý của processor có thể sinh stack trace làm người dùng khó biết cách sửa input. Nên phát diagnostic rõ với Messager cho lỗi hợp đồng source; dành exception cho lỗi nội bộ không thể tiếp tục.

## 14. Quy trình chọn Diagnostic.Kind

Khi phát hiện một vấn đề trong processor, hãy trả lời lần lượt:

1. **Đây có phải input không hợp lệ theo hợp đồng bắt buộc không?** Nếu đúng, gửi `ERROR` tại đúng `Element`/annotation value, rồi tránh generate code từ input sai.
2. **Đây có phải vi phạm khuyến nghị nhưng kết quả vẫn hữu dụng không?** Dùng `WARNING`. Ghi rõ cách sửa và hậu quả nếu không sửa.
3. **Đây có phải một cảnh báo bắt buộc theo semantics của công cụ không?** Cân nhắc `MANDATORY_WARNING`, nhưng không thay thế ERROR khi thực sự cần fail.
4. **Chỉ là thông tin cho người dùng?** Dùng `NOTE`, giới hạn số lượng.
5. **Có cần trỏ chính xác đến khai báo/giá trị không?** Chọn overload `printMessage` với context sâu nhất có thể và đúng thực tế.
6. **Có thể bị lặp khi source generation mở vòng mới không?** Xây dựng xử lý idempotent hoặc lưu khóa deduplicate hợp lý.
7. **Có hiệu lực trong CI không?** Test input đúng/sai và flag `-Werror`; xác minh build thực sự chạy processor.

Một sơ đồ lựa chọn:

```text
Phát hiện sự kiện trong processor
        |
        +-- Vi phạm hợp đồng bắt buộc? --> ERROR (+ bỏ qua generate sai)
        |
        +-- Có rủi ro cần người dùng sửa? --> WARNING
        |                                   (hoặc MANDATORY_WARNING có chủ đích)
        |
        +-- Chỉ cần cập nhật trạng thái? --> NOTE
```

Sơ đồ này là một **quy trình thiết kế**, không phải hành vi tự động do Java suy ra từ tên annotation.

## 15. Bài tập tự kiểm tra

### Bài 1 — Chọn mức diagnostic

Processor yêu cầu `@Entity` chỉ đặt trên class không abstract để có thể sinh factory. Một class abstract được gắn `@Entity`. Nên báo gì?

**Đáp án:** thường là `ERROR` nếu không thể sinh factory đúng theo hợp đồng. Nên gắn diagnostic vào `TypeElement` của class sai.

### Bài 2 — Cảnh báo và exit code

`ValidData.java` của ví dụ báo NOTE, WARNING và MANDATORY_WARNING nhưng không ERROR. Kết quả javac mặc định?

**Đáp án:** vẫn có thể thành công (thí nghiệm có exit code 0); warning được in để người dùng cân nhắc. Nếu thêm `-Werror`, build có thể thất bại do warning.

### Bài 3 — printMessage không có Element

Hai lệnh:

```java
messager.printMessage(Diagnostic.Kind.ERROR, "Wrong field");
messager.printMessage(Diagnostic.Kind.ERROR, "Wrong field", field);
```

Lệnh nào hữu ích hơn khi cần chỉ đúng dòng field vi phạm?

**Đáp án:** lệnh thứ hai, vì truyền `Element` cho compiler gắn source location khi có thể.

### Bài 4 — MANDATORY_WARNING có tương đương ERROR?

**Đáp án:** không. Đây vẫn là warning kind. `ERROR` mới thể hiện vi phạm bắt buộc làm compilation thất bại; compiler flags như `-Werror` có thể thay đổi hậu quả của warning.

### Bài 5 — Lỗi bị in nhiều lần

Một processor in cùng error ở ba processing rounds. Có phải RoundEnvironment tự khử trùng mọi lỗi?

**Đáp án:** không. Processor phải tổ chức quét đúng scope round và/hoặc deduplicate theo identity thích hợp; `Messager` không tự cung cấp chính sách loại diagnostic lặp theo quy tắc nghiệp vụ.

### Bài 6 — Giá trị mặc định

Annotation định nghĩa `String reason() default "";`, người dùng chỉ ghi `@CheckedField`. Muốn báo `"reason must be provided"` tại nguồn, có chắc lấy được `AnnotationValue` của literal `reason=""` không?

**Đáp án:** không. Người dùng không viết cặp đó, nên nên báo lỗi ở annotation mirror hoặc element; nếu cần lấy giá trị default cho phân tích, dùng API `Elements.getElementValuesWithDefaults`.

### Bài 7 — System.out khác Messager như thế nào?

**Đáp án:** `System.out.println` tạo output text thông thường, không tự được compiler nhận thành diagnostic. `Messager.printMessage` truyền phân loại `Diagnostic.Kind` và có thể gắn context nguồn.

### Bài 8 — WARNING có mặc định được @SuppressWarnings("custom") bỏ qua không?

**Đáp án:** không. Processor tùy chỉnh muốn hỗ trợ suppression phải tự có cơ chế hiểu khóa, phạm vi và quyết định không phát warning tương ứng.

### Bài 9 — Vị trí nguồn chính xác hơn

Khi annotation có `@Limit(max = -1)` và lỗi nằm ở giá trị `max`, overload nào có thể cung cấp source context cụ thể nhất?

**Đáp án:** overload nhận `Diagnostic.Kind`, message, `Element`, `AnnotationMirror` và `AnnotationValue`, với mirror/value liên quan đúng tới `max`. Tuy nhiên mức độ chính xác khi hiển thị vẫn phụ thuộc compiler/IDE.

### Bài 10 — NOTE có bảo đảm build thành công?

**Đáp án:** không. NOTE chỉ báo thông tin; build có thể thất bại ở chỗ khác do error của compiler hoặc processor khác.

## 16. Tổng kết

**Messager** là kênh báo diagnostic cho annotation processor; **Diagnostic.Kind** phân biệt mức độ. `ERROR` dành cho input không được chấp nhận; `WARNING` nêu rủi ro không nhất thiết gây lỗi; `MANDATORY_WARNING` cho cảnh báo bắt buộc; `NOTE` cho thông tin; `OTHER` cho loại diagnostic ngoài những nhóm trên.

Để bộ xử lý hữu ích cho người lập trình, hãy phát thông báo **đúng mức độ, rõ nội dung, đúng phần tử nguồn và không lặp ngoài ý muốn**. Cơ chế kết hợp giữa `RoundEnvironment`, `Messager`, `Element`/`AnnotationMirror`/`AnnotationValue` giúp một annotation processor trở thành một công cụ kiểm tra thực sự trong lúc biên dịch. Một lời nhắn tốt chỉ ra **điều kiện đã vi phạm và cách khắc phục**, không chỉ nói “invalid annotation”.

### Tài liệu Java SE 17 chính thức

- [Messager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Messager.html): bốn overload của `printMessage` và quy tắc gắn diagnostic với source.
- [Diagnostic.Kind](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.Kind.html): các loại `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE` và `OTHER`.
- [Diagnostic](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html): mô hình diagnostic mà Java compiler API cung cấp.
- [ProcessingEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html): `getMessager()` và tài nguyên của processor.
- [RoundEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): `getElementsAnnotatedWith` và trạng thái các vòng.
- [Elements](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html): `getElementValuesWithDefaults` và các tiện ích mô hình khai báo.
- [javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `-processor`, `-processorpath`, `-Werror`, `-Xlint` và tùy chọn hiển thị diagnostic.
