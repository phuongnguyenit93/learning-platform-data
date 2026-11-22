# Gắn lỗi, cảnh báo vào phần tử bằng Messager trong annotation processor

Khi xây dựng annotation processor, việc phát hiện annotation không hợp lệ mới chỉ là một nửa công việc. Nửa còn lại là **báo diagnostic đúng mức độ và gắn vào đúng vị trí mã nguồn** để người dùng biết phải sửa annotation, phần tử, hay giá trị thuộc tính nào. Trong Java 17+, API trung tâm cho việc đó là `javax.annotation.processing.Messager`, lấy từ `ProcessingEnvironment.getMessager()`.

Ví dụ: nếu quy ước `@CheckedName("...")` không chấp nhận tên rỗng, người dùng sẽ hiểu vấn đề nhanh hơn khi compiler đánh dấu **chính chuỗi `""`** trên dòng annotation thay vì chỉ in “Invalid name” không có vị trí. Với một giá trị ngắn nhưng vẫn hợp lệ, processor có thể phát `WARNING` để nhắc nhở, không ngăn biên dịch. Việc phân loại diagnostic và vị trí chính xác là phần quan trọng của chất lượng developer experience.

Mục tiêu của bài: hiểu các overload `printMessage`, phân biệt `Diagnostic.Kind`, lấy `Element` / `AnnotationMirror` / `AnnotationValue` đúng cách, tạo processor có thể chạy bằng `javac`, đọc kết quả và exit code, xử lý vòng xử lý (*rounds*), tránh chẩn đoán trùng hoặc sai vị trí, rồi viết kiểm thử cho lỗi và cảnh báo.

## 1. Bối cảnh: processor hoạt động ở giai đoạn biên dịch

Annotation processing là một phần của quá trình build. Khi `javac` chạy processor, nó cung cấp mô hình của chương trình đang biên dịch thông qua `javax.lang.model` và môi trường xử lý thông qua `ProcessingEnvironment`.

Luồng đơn giản:

```text
File nguồn .java
       |
       v
javac phân tích cú pháp / symbol / annotation
       |
       v
Annotation processor (AbstractProcessor.process)
       |
       |-- đọc Element / AnnotationMirror / AnnotationValue
       |-- kiểm tra quy tắc annotation
       |-- gọi processingEnv.getMessager().printMessage(...)
       |
       v
Compiler / IDE / build tool nhận diagnostic
       |
       +-- ERROR: build không thành công
       +-- WARNING: báo rủi ro, build có thể thành công
       +-- NOTE: thông tin bổ sung
       |
       v
Class file có thể được tạo nếu không có lỗi và chế độ biên dịch cho phép
```

`Messager` **không phải** API runtime của ứng dụng Java. Nó không dùng để đưa log lên console khi chương trình của người dùng đang chạy. Đối tượng này phục vụ **báo cáo diagnostic từ processor khi compiler đang xử lý source**.

Nếu processor chỉ gọi `System.out.println("invalid")` hoặc `System.err.println("invalid")`, thông tin thường thiếu mức độ chuẩn hóa và vị trí source. Compiler không coi một dòng chữ in console là một `ERROR` của hệ thống diagnostic. Dùng `Messager` thay vì cố tự dựng “file:line:col” bằng chuỗi.

### Những khái niệm cần biết

| Thành phần | Vai trò |
| --- | --- |
| `AbstractProcessor` | Lớp cơ sở tiện lợi để cài đặt `Processor` |
| `ProcessingEnvironment` | Cung cấp `Messager`, `Elements`, `Types`, `Filer` và options |
| `RoundEnvironment` | Danh sách phần tử trong vòng xử lý hiện tại và trạng thái processing |
| `Element` | Phần tử mô hình của chương trình: class, field, method, parameter... |
| `AnnotationMirror` | Một lần sử dụng annotation trên phần tử trong mô hình Java |
| `AnnotationValue` | Giá trị một thành phần của annotation, ví dụ `"AB"` trong `value = "AB"` |
| `Messager` | API phát diagnostic từ processor |
| `Diagnostic.Kind` | Mức độ của diagnostic (`ERROR`, `WARNING`, `NOTE`...) |

**Lưu ý:** Element và AnnotationMirror là các đối tượng thuộc compiler model; không đồng nghĩa với `java.lang.reflect.AnnotatedElement` và `java.lang.annotation.Annotation` của reflection runtime.

## 2. Bốn cách gọi Messager.printMessage

Java SE 17 định nghĩa bốn overload của `Messager.printMessage`:

```java
void printMessage(Diagnostic.Kind kind, CharSequence msg);

void printMessage(Diagnostic.Kind kind, CharSequence msg, Element e);

void printMessage(Diagnostic.Kind kind, CharSequence msg,
                  Element e, AnnotationMirror a);

void printMessage(Diagnostic.Kind kind, CharSequence msg,
                  Element e, AnnotationMirror a, AnnotationValue v);
```

Các khai báo trên **minh họa chữ ký API**, không phải code cần chép vào class của bạn.

| Lời gọi | Gợi ý vị trí diagnostic | Khi nên dùng |
| --- | --- | --- |
| `printMessage(kind, message)` | Không gắn một phần tử source cụ thể | Chẩn đoán tổng thể về processor hoặc cấu hình |
| `printMessage(kind, message, element)` | Phần tử: lớp, method, field... | Quy tắc áp dụng cho toàn phần tử |
| `printMessage(kind, message, element, mirror)` | Annotation trên phần tử | Quy tắc áp dụng cho chính annotation |
| `printMessage(kind, message, element, mirror, value)` | Một giá trị trong annotation | Lỗi/cảnh báo riêng của thuộc tính annotation |

Sự khác biệt quan trọng nhất: **càng cung cấp ngữ cảnh phù hợp, compiler càng có cơ hội đánh dấu đúng vị trí**. Tuy nhiên, Java API chỉ hứa các đối tượng trên là *location hint*: tùy compiler, IDE, source availability và dạng annotation, vị trí được chọn có thể gần đúng hoặc không xác định. Không nên khẳng định mọi implementation luôn gạch chân từng ký tự giống hệt nhau.

Dùng cách chi tiết nhất có ý nghĩa. Nếu lỗi nằm ở giá trị `timeout = -1`, gắn vào `AnnotationValue` của `timeout` sẽ hữu ích hơn gắn vào một class có hàng trăm dòng.

## 3. Diagnostic.Kind: khi nào lỗi, khi nào cảnh báo?

`javax.tools.Diagnostic.Kind` có các giá trị liên quan:

- `ERROR`: quy tắc bắt buộc bị vi phạm; việc báo lỗi khiến compilation không thành công.
- `WARNING`: hành vi đáng nghi hoặc cần xử lý nhưng vẫn được phép; biên dịch bình thường có thể tiếp tục.
- `MANDATORY_WARNING`: loại cảnh báo bắt buộc theo hệ thống diagnostic, dành cho tình huống thích hợp; đừng dùng chỉ để ép mọi cảnh báo thành lỗi.
- `NOTE`: thông tin bổ sung giúp người dùng theo dõi; không nên lạm dụng vì làm log dài.
- `OTHER`: diagnostic không phân vào những loại trên; hiếm cần dùng cho validation thông thường.

### Quy tắc thực hành

| Tình huống | Loại gợi ý | Lý do |
| --- | --- | --- |
| Annotation có giá trị trống nhưng hợp đồng yêu cầu không rỗng | `ERROR` | Không thể chấp nhận source theo quy tắc processor |
| Phần tử mang annotation sai `ElementKind` theo quy tắc tùy chỉnh | `ERROR` | Source không hợp lệ đối với processor |
| Giá trị vẫn hợp lệ nhưng không tuân theo quy ước đặt tên khuyến nghị | `WARNING` | Để người dùng quyết định hoặc sửa dần |
| Dùng API cũ có lộ trình thay thế | `WARNING` | Cần nhắc nhưng chưa nhất thiết chặn build |
| Báo một thông tin tổng kết không ảnh hưởng tính đúng | `NOTE` | Trợ giúp chẩn đoán; nên ít và rõ |
| Quy tắc ngôn ngữ hoặc công cụ đòi cảnh báo bắt buộc | `MANDATORY_WARNING` khi thật sự phù hợp | Không thay cho chính sách `-Werror` |

Đối với hầu hết validation annotation thông thường, chọn `ERROR` cho **vi phạm yêu cầu bắt buộc**, `WARNING` cho **đề xuất hoặc vấn đề cần xem xét**, và `NOTE` cho thông tin có ích. Không biến mọi thứ thành `ERROR` vì sẽ khiến processor khó dùng trong dự án legacy hoặc các lần migration.

**`ERROR` khác Java exception.** Gọi `messager.printMessage(Diagnostic.Kind.ERROR, ...)` là báo diagnostic cho compiler; không phải `throw new RuntimeException(...)`. Thông thường processor vẫn có thể hoàn tất logic vòng xử lý hiện tại, và compiler tổng hợp lỗi để trả kết quả thất bại. Không cần cố ném exception để “đảm bảo” lỗi được nhìn thấy.

## 4. Bài lab Java 17+: chuẩn bị annotation và processor

Ta xây dựng bộ kiểm tra `@CheckedName`:

- Tên **rỗng**: `ERROR` `[NAME001]` tại **giá trị annotation**.
- Tên **dưới 3 ký tự**: `WARNING` `[NAME002]` tại **giá trị annotation**.
- Tên **từ 3 ký tự trở lên**: `NOTE` `[NAME000]` tại **annotation** (chỉ để bài học dễ quan sát).
- Processor không tự tạo class, chỉ kiểm tra nguồn.

Cấu trúc một thư mục thực hành độc lập:

```text
messager-lab/
  src/
    diagnostics/
      CheckedName.java
      NameProcessor.java
  examples/
    Cases.java
    Good.java
    Warning.java
  out/
    processor/    (được javac tạo)
    classes/      (được javac tạo)
```

Các ví dụ không cần Maven, Gradle hoặc file `module-info.java`, bởi ở đây ta tập trung vào **annotation processor chạy trên classpath** để giảm yếu tố ngoài chủ đề.

### 4.1. File src/diagnostics/CheckedName.java

```java
package diagnostics;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface CheckedName {
    String value();
}
```

Giải thích:

1. `@Target(ElementType.TYPE)` cho phép annotation được đặt lên khai báo kiểu (class, interface... theo các quy tắc target tương ứng).
2. `@Retention(RetentionPolicy.SOURCE)` cho biết annotation chỉ cần trong nguồn/giai đoạn biên dịch; không cần giữ trong class file ở runtime.
3. `String value();` là thành phần bắt buộc của annotation, không có giá trị mặc định, giúp dễ lấy đúng `AnnotationValue` xuất hiện trong source.

`RetentionPolicy.SOURCE` **không ngăn annotation processor đọc annotation**; ngược lại, source-retention annotations rất phù hợp cho những quy tắc biên dịch, code generation và static validation.

### 4.2. File src/diagnostics/NameProcessor.java

```java
package diagnostics;

import java.util.Map;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.AnnotationMirror;
import javax.lang.model.element.AnnotationValue;
import javax.lang.model.element.Element;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("diagnostics.CheckedName")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class NameProcessor extends AbstractProcessor {
    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        for (TypeElement annotationType : annotations) {
            for (Element element :
                    roundEnv.getElementsAnnotatedWith(annotationType)) {
                AnnotationMirror mirror =
                        findMirror(element, annotationType);
                if (mirror == null) {
                    continue;
                }

                for (Map.Entry<? extends ExecutableElement,
                        ? extends AnnotationValue> entry :
                        mirror.getElementValues().entrySet()) {
                    if (!entry.getKey().getSimpleName()
                            .contentEquals("value")) {
                        continue;
                    }

                    String value = (String) entry.getValue().getValue();
                    if (value.isBlank()) {
                        processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "[NAME001] Ten khong duoc de trong",
                            element, mirror, entry.getValue());
                    } else if (value.length() < 3) {
                        processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.WARNING,
                            "[NAME002] Ten nen co tu 3 ky tu",
                            element, mirror, entry.getValue());
                    } else {
                        processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.NOTE,
                            "[NAME000] Ten hop le: " + value,
                            element, mirror);
                    }
                }
            }
        }
        return true;
    }

    private AnnotationMirror findMirror(
            Element element, TypeElement annotationType) {
        for (AnnotationMirror mirror : element.getAnnotationMirrors()) {
            if (processingEnv.getTypeUtils().isSameType(
                    mirror.getAnnotationType(), annotationType.asType())) {
                return mirror;
            }
        }
        return null;
    }
}
```

**Đây là một processor chạy được**, không phải pseudocode. Trong bài lab, thông điệp diagnostic dùng tiếng Việt không dấu để log console nhất quán trên nhiều môi trường. Trong dự án thật, có thể chọn thông điệp tiếng Việt UTF-8 hoặc tiếng Anh và chuẩn hóa localization.

Giải thích cơ chế:

1. `@SupportedAnnotationTypes("diagnostics.CheckedName")` khai báo loại annotation processor hỗ trợ. Tên là **fully qualified name**, khớp package của annotation.
2. `@SupportedSourceVersion(SourceVersion.RELEASE_17)` khai báo mức source được processor hỗ trợ. Lệnh demo dùng `--release 17` để tránh cảnh báo về phiên bản source mới hơn.
3. `process(annotations, roundEnv)` nhận tập annotation type tương ứng của vòng hiện tại và môi trường để tìm các phần tử đã được đánh dấu.
4. `roundEnv.getElementsAnnotatedWith(annotationType)` lấy `Element`. Dùng overload nhận `TypeElement` để không phụ thuộc việc nạp một annotation class qua reflection vào processor.
5. `findMirror` tìm đúng `AnnotationMirror` trên element bằng cách so `TypeMirror` qua `Types.isSameType`.
6. `mirror.getElementValues()` chứa cặp `ExecutableElement -> AnnotationValue` cho các thành phần annotation **được khai báo tường minh** trong lần dùng đó.
7. Với thành phần có tên `value`, ta đọc dữ liệu và phát diagnostic với đủ ba đối tượng `element, mirror, entry.getValue()` khi lỗi thuộc một giá trị.
8. `return true` báo rằng processor đã *claim* các loại annotation nó xử lý, ảnh hưởng việc các processor sau có thể xử lý cùng annotation; **không có nghĩa build thành công**. Kết quả thành công/thất bại do diagnostics và compiler quyết định.

`entry.getValue().getValue()` trả về một giá trị dạng `Object`, nhưng annotation đã định nghĩa `String value()` nên cast `(String)` đúng với **định nghĩa annotation cụ thể này**. Nếu bạn hỗ trợ nhiều kiểu thành phần (primitive, enum, class literal, nested annotation, array), phải xử lý theo loại giá trị và API tương ứng, không cast mọi `AnnotationValue` sang `String`.

## 5. Biên dịch processor trước, rồi mới chạy nó

Tại thư mục `messager-lab`, thực hiện:

```bash
javac --release 17 -d out/processor src/diagnostics/CheckedName.java src/diagnostics/NameProcessor.java
```

Lệnh này biên dịch cả annotation interface và processor. Khi thành công, bạn có:

```text
out/processor/diagnostics/CheckedName.class
out/processor/diagnostics/NameProcessor.class
```

Sau đó compiler của ứng dụng cần **hai góc nhìn**:

- `-cp out/processor`: cho phép mã nguồn mẫu import `diagnostics.CheckedName`.
- `-processorpath out/processor`: cho phép trình biên dịch nạp class `diagnostics.NameProcessor` để chạy annotation processing.
- `-processor diagnostics.NameProcessor`: chọn chính processor mong muốn, **không phụ thuộc tự động discovery**.
- `-proc:only`: **chỉ chạy annotation processing, không sinh class file cho nguồn ứng dụng**; hữu ích khi kiểm tra diagnostic.
- `-d out/classes`: chỉ định thư mục output nếu trình biên dịch có tạo file; lệnh `-proc:only` không sinh `.class` của các lớp input.

Lưu ý: trong một dự án thực tế, annotation artifact có thể nằm trong compile classpath hoặc module path, còn processor artifact trong processor path. Không trộn lẫn khái niệm “mã người dùng import annotation” và “compiler nạp code processor” chỉ vì bài lab đặt chúng vào cùng thư mục để dễ thao tác.

**Đã kiểm chứng bằng JDK 24 với `--release 17`:** lệnh biên dịch hai file trong `src/diagnostics` thành công với exit code `0`. Mã không dùng API mới hơn Java 17.

## 6. Kiểm chứng ERROR, WARNING và NOTE ở đúng vị trí

### 6.1. File examples/Cases.java

```java
import diagnostics.CheckedName;

@CheckedName("")
class MissingName {}

@CheckedName("AB")
class ShortName {}

@CheckedName("Customer")
class GoodName {}
```

Không có class `public`, vì vậy một file nguồn `Cases.java` có thể chứa cả ba khai báo class trên.

Chạy:

```bash
javac --release 17 -cp out/processor -processorpath out/processor -processor diagnostics.NameProcessor -proc:only -d out/classes examples/Cases.java
```

Trích yếu diagnostic thực tế đã kiểm chứng:

```text
examples/Cases.java:3: error: [NAME001] Ten khong duoc de trong
@CheckedName("")
             ^
examples/Cases.java:6: warning: [NAME002] Ten nen co tu 3 ky tu
@CheckedName("AB")
             ^
examples/Cases.java:9: Note: [NAME000] Ten hop le: Customer
@CheckedName("Customer")
^
1 error
1 warning
```

Ý nghĩa:

- **`[NAME001]` — ERROR:** vị trí gạch chân nằm ở **giá trị `""`**, không phải dòng class `MissingName`, vì gọi overload `printMessage(ERROR, ..., element, mirror, value)`.
- **`[NAME002]` — WARNING:** vị trí nằm ở **giá trị `"AB"`**, vẫn được compiler xem là source hợp lệ nếu không có lỗi khác.
- **`[NAME000]` — NOTE:** vị trí nằm ở **annotation `@CheckedName`**, vì gọi overload chỉ truyền `element, mirror`.
- Vì có `ERROR`, **`javac` trả exit code khác 0** (kiểm thử cụ thể: `1`). Không nên dựa vào số dòng `"1 error"` như API máy đọc duy nhất; hãy kiểm tra exit code của compiler.

Số dòng trên khớp source chính xác trong mục 6.1. Wording của diagnostic là chuỗi do processor quy định, còn định dạng đường dẫn, column indicator, ký hiệu caret và chi tiết thêm có thể khác giữa shell, IDE và các implementation `javac`.

### 6.2. File examples/Good.java: thành công chỉ với NOTE

```java
import diagnostics.CheckedName;

@CheckedName("Customer")
class Customer {}
```

Chạy:

```bash
javac --release 17 -cp out/processor -processorpath out/processor -processor diagnostics.NameProcessor -proc:only -d out/classes examples/Good.java
```

Diagnostic trích yếu:

```text
examples/Good.java:3: Note: [NAME000] Ten hop le: Customer
@CheckedName("Customer")
^
```

**Exit code `0`** trong thí nghiệm đã kiểm chứng. `NOTE` không phải `ERROR` hay `WARNING` và không tự làm compilation thất bại. Chế độ `-proc:only` vẫn không tạo `Customer.class`, kể cả khi exit code bằng `0`.

Trong processor dùng để phát hành thật, không nhất thiết báo `NOTE` trên từng annotation hợp lệ: việc này có thể làm nhiễu log của dự án lớn. Ta thêm `NOTE` chỉ để làm rõ vị trí gắn vào annotation và phân biệt mức diagnostic.

### 6.3. File examples/Warning.java: warning không ngăn build bình thường

```java
import diagnostics.CheckedName;

@CheckedName("AB")
class ShortName {}
```

Chạy:

```bash
javac --release 17 -cp out/processor -processorpath out/processor -processor diagnostics.NameProcessor -proc:only -d out/classes examples/Warning.java
```

Trích yếu:

```text
examples/Warning.java:3: warning: [NAME002] Ten nen co tu 3 ky tu
@CheckedName("AB")
             ^
1 warning
```

Trong thí nghiệm này, compiler **trả exit code `0`**. Nếu muốn nhóm build từ chối warning, có thể chạy:

```bash
javac --release 17 -cp out/processor -processorpath out/processor -processor diagnostics.NameProcessor -proc:only -Werror -d out/classes examples/Warning.java
```

Diagnostic bổ sung có dạng:

```text
error: warnings found and -Werror specified
1 error
1 warning
```

Lúc này compiler **trả exit code khác `0`** (thử nghiệm: `1`), nhưng processor **vẫn phát một `WARNING`**, không tự đổi `Diagnostic.Kind.WARNING` thành `ERROR`. `-Werror` là **chính sách của javac/build**, không phải loại severity mà processor bắt buộc dùng cho mọi cảnh báo.

## 7. Vị trí gắn diagnostic: Element, mirror và value

Hãy xem ba cách chẩn đoán cùng một annotation:

```java
Messager messager = processingEnv.getMessager();

// Toàn phần tử; compiler gợi ý vị trí khai báo class/field/method.
messager.printMessage(
    Diagnostic.Kind.ERROR,
    "[RULE100] Phan tu khong hop le",
    element);

// Annotation cụ thể trên phần tử.
messager.printMessage(
    Diagnostic.Kind.WARNING,
    "[RULE101] Annotation can xem lai",
    element, mirror);

// Một thành phần có giá trị cụ thể trong annotation.
messager.printMessage(
    Diagnostic.Kind.ERROR,
    "[RULE102] Gia tri khong hop le",
    element, mirror, annotationValue);
```

Đoạn này **chỉ minh họa cách gọi API** bên trong processor, giả sử biến `element`, `mirror` và `annotationValue` đã được lấy đúng; không phải file Java độc lập. Bộ khung hoàn chỉnh chạy được nằm ở `NameProcessor.java` phía trên.

**Quy tắc gắn vị trí:**

1. Lỗi thuộc **toàn class** (ví dụ “class annotated phải là public”): dùng `Element` của class.
2. Lỗi thuộc **chính việc dùng annotation** (ví dụ “annotation này không nên được dùng ở đây”): dùng `Element + AnnotationMirror`.
3. Lỗi thuộc **một tham số annotation** (ví dụ `@Check(min = -5)`): dùng `Element + AnnotationMirror + AnnotationValue` của `min`.
4. Lỗi thuộc **cấu hình chung** (ví dụ processor option sai và không có phần tử cụ thể): dùng overload không gắn `Element`, cung cấp thông điệp đủ rõ.

Không lấy `Element` của class cha rồi kết hợp bừa một `AnnotationMirror` thuộc field con. Bộ ba phải mô tả **cùng một lần sử dụng annotation trên đúng phần tử**; nếu không, gợi ý vị trí có thể sai hoặc không sử dụng được.

### Cách tìm AnnotationMirror theo kiểu thực sự

`Element.getAnnotationMirrors()` có thể chứa nhiều annotation khác nhau. Không nên chọn `get(0)` và giả định luôn đúng loại. Trong processor đã dùng:

```java
processingEnv.getTypeUtils().isSameType(
    mirror.getAnnotationType(),
    annotationType.asType())
```

`TypeMirror` của annotation mirror được đối chiếu với `TypeElement` mà compiler đưa vào. Điều này an toàn hơn việc chỉ so chuỗi tên ngắn `"CheckedName"`, vì có thể có các annotation khác package cùng simple name.

Khi chỉ có `TypeElement` của annotation cần tìm, một cách khác là lấy tên đầy đủ từ `Elements`/`TypeElement.getQualifiedName()` và đối chiếu có chủ đích. Cách dùng `Types.isSameType` ở lab phù hợp với cùng mô hình kiểu trong vòng xử lý hiện tại.

### Cách tìm AnnotationValue của thuộc tính cần báo lỗi

`mirror.getElementValues()` trả một map có key kiểu `ExecutableElement` đại diện cho thành phần annotation (ví dụ `String value();`), và value kiểu `AnnotationValue` tương ứng.

Trong lab:

```java
if (entry.getKey().getSimpleName().contentEquals("value")) {
    String value = (String) entry.getValue().getValue();
    // entry.getValue() chính là AnnotationValue để gắn vào vị trí.
}
```

Với annotation nhiều thuộc tính, nên tìm đúng key theo tên hoặc element model, thay vì lấy entry đầu tiên. Map không phải hợp đồng để suy ra vị trí source của “thuộc tính số 1”; lấy key đúng mới quan trọng.

## 8. Giá trị mặc định của annotation là một bẫy thường gặp

Nếu annotation khai báo:

```java
public @interface Threshold {
    int min() default 0;
}
```

Và người dùng viết:

```java
@Threshold
class Example {}
```

Thì trong lần sử dụng `@Threshold` **không có giá trị `min` được ghi tường minh trong source**. Theo API model:

- `AnnotationMirror.getElementValues()` lấy các thành phần **được chỉ định tường minh** trong annotation use.
- `processingEnv.getElementUtils().getElementValuesWithDefaults(mirror)` trả map bao gồm cả giá trị mặc định hợp lệ.

Đây là các khai báo **minh họa riêng**, không nằm trong project `@CheckedName` của lab. Khi kiểm tra quy tắc “`min` phải lớn hơn 0”, nếu thuộc tính bị bỏ trống trong annotation use thì giá trị thực tế vẫn là default `0`; phải lấy qua API có defaults để không bỏ sót.

Nhưng một **giá trị mặc định không có vị trí nguồn tại lần dùng annotation**. Nếu báo lỗi `min=0` được kế thừa từ default, việc cố gắn `AnnotationValue` ấy vào phần source không hề viết `min` có thể cho vị trí gần đúng hoặc không hiển thị như mong muốn. Khi đó diagnostic gắn vào **AnnotationMirror** hoặc **Element** có thể có ý nghĩa hơn, kèm thông điệp “đã dùng giá trị mặc định 0”.

Điểm phân biệt: **lấy đúng giá trị logic** và **định vị ký tự nguồn** là hai vấn đề riêng. Không được hứa luôn có caret cho giá trị mặc định mà người dùng không nhập.

## 9. Processor có nhiều rounds: tránh báo lặp

Annotation processing có thể diễn ra qua nhiều **rounds**, đặc biệt khi một processor hoặc công cụ khác tạo source mới qua `Filer`. Compiler có thể đưa những file/element vừa sinh vào vòng tiếp theo.

Hai phương thức của `RoundEnvironment` cần biết:

```java
roundEnv.processingOver();
roundEnv.errorRaised();
```

- `processingOver()` cho biết round này là round cuối liên quan tới việc xử lý annotation; thường dùng để làm công việc tổng kết có chủ đích, không phát sinh source mới.
- `errorRaised()` phản ánh thông tin lỗi ở round trước theo hợp đồng API; **không thay cho việc tự lưu trạng thái validation** hay quyết định thành công cuối cùng của build.

`RoundEnvironment.getElementsAnnotatedWith(...)` lấy các phần tử **đang thuộc phạm vi round hiện tại**. Bài lab chỉ xử lý phần tử nhận được ở round hiện tại, không quét lại toàn bộ source/classpath theo đường thủ công, nên không tự nhân đôi diagnostic của cùng source chỉ vì compiler gọi `process` nhiều lần.

Để xem hoạt động của processor qua các round khi debug:

```bash
javac --release 17 -XprintRounds -XprintProcessorInfo -cp out/processor -processorpath out/processor -processor diagnostics.NameProcessor -proc:only examples/Good.java
```

Các flag `-XprintRounds`, `-XprintProcessorInfo` là tùy chọn chẩn đoán của `javac`, output chi tiết thay đổi theo JDK và tập annotation được tìm thấy. Chúng giúp xác định processor được gọi khi nào, xử lý annotation nào, và có nhiều round hay không. Không nên đưa toàn bộ log đó vào stdout của ứng dụng.

**Không tạo trùng lỗi theo round:** nếu processor tích lũy danh sách `Element` qua nhiều vòng rồi báo lại cùng lỗi ở vòng cuối, người dùng có thể nhận diagnostic trùng. Hãy chọn vòng xử lý hợp lý, nhận diện phần tử ổn định và chỉ phát một diagnostic cho một vi phạm có chủ đích.

### return true và return false

`process(...)` trả `true` nghĩa là processor **claim** các annotation types được giao; processor khác có thể không còn được yêu cầu xử lý cùng các annotation này theo cơ chế phân phối annotations. `false` nghĩa là chưa claim chúng.

Giá trị trả về **không** có nghĩa:

- `true` = annotation hợp lệ.
- `false` = compilation thất bại.
- `false` = compiler sẽ tự chuyển warning thành error.

Hãy phát `Diagnostic.Kind.ERROR` khi có lỗi thực sự. Việc claim annotation types và việc báo validation failures là hai quyết định độc lập.

## 10. Không dùng exception để thay Messager

Có sự khác nhau rõ giữa:

```java
processingEnv.getMessager().printMessage(
    Diagnostic.Kind.ERROR,
    "[NAME001] Ten khong duoc de trong",
    element, mirror, value);
```

và:

```java
throw new IllegalArgumentException("Ten khong duoc de trong");
```

Đây là hai mảnh **minh họa** trong một method đã có `element/mirror/value`. Khi ném exception từ processor, compiler/build tool có thể in stack trace về lỗi implementation của processor thay vì gạch chân chỗ người dùng cần sửa. Exception nên dành cho tình huống bất thường khi **processor tự gặp lỗi nội bộ**; với **source không tuân theo quy tắc**, báo `ERROR` tại vị trí tương ứng là trải nghiệm tốt hơn.

Nếu processor có thể tiếp tục phân tích an toàn, có thể báo **nhiều lỗi độc lập** trong một lượt để người dùng sửa cùng lúc. Nhưng đừng phát các lỗi dây chuyền vô nghĩa vì một giá trị đã sai khiến mọi kiểm tra phụ thuộc thất bại.

### Không lạm dụng stdout/stderr

`Messager` là API trừu tượng; implementation có thể hiển thị diagnostic trong terminal, cửa sổ IDE hoặc giao diện build tool. Oracle API nói rõ thông điệp **không nhất thiết xuất hiện như văn bản trên `System.out` hoặc `System.err`**. Vì vậy:

- Đừng viết test chỉ dựa vào `System.out` của compiler.
- Đừng gọi `System.err.println` như cách chính để chặn compilation.
- Với unit/integration test, kiểm tra **compiler diagnostics và kết quả compilation**.
- Nếu viết custom Java Compiler API test, có thể dùng `DiagnosticCollector<JavaFileObject>` hoặc listener phù hợp với implementation; đây là cách có cấu trúc hơn việc parse toàn bộ console log.

## 11. Tùy chọn javac liên quan đến annotation processing

| Flag | Vai trò | Khi dùng |
| --- | --- | --- |
| `-processor diagnostics.NameProcessor` | Chọn class processor trực tiếp | Bài lab, test tái lập, tránh phụ thuộc auto-discovery |
| `-processorpath out/processor` | Đường tìm processor | Processor và dependency riêng |
| `-cp out/processor` | Đường tìm annotation/API sử dụng trong source | Để source import annotation |
| `-proc:only` | Chạy annotation processing nhưng không sinh class của source được compile | Test validation và generated sources |
| `-proc:none` | Không chạy annotation processing | Khoanh vùng lỗi do processor |
| `-XprintRounds` | In thông tin rounds | Debug vòng xử lý |
| `-XprintProcessorInfo` | In thông tin processor/annotation types | Debug phát hiện processor |
| `-Werror` | Coi warnings là nguyên nhân fail build | Quy tắc CI chất lượng |
| `-Xmaxerrs N`, `-Xmaxwarns N` | Giới hạn số diagnostic được in chi tiết | Kiểm soát log dài |
| `--release 17` | Source/API/target tương ứng Java 17 | Giữ ví dụ tương thích Java 17 |

**`-processorpath` khác `-cp`**, dù ở lab chúng cùng trỏ tới `out/processor` vì chúng ta đặt annotation interface và processor class trong một thư mục. Ở dự án thực, có thể tách riêng hai artifact để tránh vô tình mang compiler implementation vào runtime.

### Tự động phát hiện processor

Bạn có thể đăng ký processor qua file service provider trong JAR processor:

```text
META-INF/services/javax.annotation.processing.Processor
```

Nội dung file là fully qualified name của processor:

```text
diagnostics.NameProcessor
```

Đây là **mô tả cơ chế đăng ký**, không phải một lệnh tạo JAR hoàn chỉnh trong lab. Khi đóng gói đầy đủ, cần đặt service file đúng vị trí trong artifact và cấu hình đường tìm processor. Hành vi mặc định về phát hiện/tự khởi chạy annotation processing đã thay đổi giữa các bản JDK; để ví dụ đáng tin trên toolchain hiện đại, bài thực hành dùng `-processor diagnostics.NameProcessor` **tường minh**.

### Có cần @SupportedSourceVersion không?

Có, hoặc override `getSupportedSourceVersion()` tương ứng. Nếu processor báo chỉ hỗ trợ source version cũ hơn source đang dùng, `javac` có thể phát warning về supported source version. Đó là diagnostic của công cụ liên quan đến processor configuration, **không phải lỗi annotation của user**.

Trong bài lab, `SourceVersion.RELEASE_17` ghép với `--release 17` để có một môi trường nhất quán. Khi nâng dự án lên Java mới, đánh giá API và source version mà processor thực sự hỗ trợ, không tự thay chuỗi số mà bỏ qua khả năng tương thích.

## 12. Phân biệt lỗi định dạng source và lỗi do processor

Giả sử người dùng viết:

```java
@CheckedName(
class Broken {}
```

Đây là mã **cố ý sai cú pháp Java**. Parser không tạo được annotation use hợp lệ như bài lab, nên compiler có thể báo lỗi cú pháp trước khi processor chạy. Bạn không nên mong `Messager` chẩn đoán một `AnnotationValue` không tồn tại trong mô hình Java hợp lệ.

Ngược lại:

```java
@CheckedName("")
class MissingName {}
```

Đây là **cú pháp annotation hợp lệ**, nhưng **quy tắc tùy chỉnh của processor** từ chối tên rỗng. Lúc này việc gắn `ERROR` vào value qua `Messager` là đúng mục đích.

Hai nhóm lỗi khác nhau:

- **Cú pháp/kiểu/hợp đồng ngôn ngữ:** thường do `javac` xử lý trực tiếp.
- **Ràng buộc miền nghiệp vụ của annotation:** do processor thực thi và báo qua `Messager`.

Không nên cố viết processor để thay thế parser, type checker hoặc các quy tắc ngôn ngữ đã được Java đảm bảo.

## 13. Những lỗi thường gặp khi gắn diagnostic

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Processor báo lỗi nhưng IDE chỉ thấy dòng log, không nhảy đến nguồn | Dùng `println` hoặc overload `printMessage(kind,msg)` không có element | Dùng `Element` hoặc mirror/value khi có vị trí |
| Dấu `^` nằm ở class thay vì giá trị annotation | Chỉ truyền `Element` | Tìm đúng `AnnotationMirror` và `AnnotationValue` |
| Báo lỗi trên annotation khác | Chọn mirror theo thứ tự `get(0)` | Đối chiếu annotation type cụ thể |
| Không tìm thấy thuộc tính có default | Chỉ dùng `getElementValues()` | Cân nhắc `getElementValuesWithDefaults()` |
| Gạch chân giá trị default không thấy đúng ký tự | Default không có vị trí được viết trong annotation use | Báo ở mirror/element và giải thích default |
| Warning vẫn build thành công | `WARNING` không chặn compile mặc định | Chỉ báo `ERROR` nếu vi phạm bắt buộc, hoặc dùng `-Werror` ở CI |
| Processor không chạy | Chưa đưa processor vào path hoặc chưa chỉ định/discover processor | Xem `-processor` và `-processorpath` |
| Processor chạy nhưng không tìm thấy annotation | Sai fully qualified name, sai target, sai source path, vòng xử lý không có phần tử | Xác nhận `@SupportedAnnotationTypes` và mô hình source |
| Mỗi lỗi bị lặp hai hoặc nhiều lần | Xử lý lại phần tử qua nhiều rounds hoặc logic báo trùng | Kiểm soát vòng và deduplicate nếu cần |
| Stack trace thay vì vị trí sửa code | Ném exception thay vì phát diagnostic hợp lệ | Gọi `Messager` cho lỗi của mã người dùng |
| Build tool không hiện cùng output với terminal | Diagnostic UI/log của compiler implementation khác | Kiểm tra compiler result/diagnostics thay vì format text cố định |
| `-Werror` khiến warning fail build | Chính sách compiler, không phải processor tự đổi severity | Xem quality gate và mức độ diagnostic có phù hợp |

## 14. Thiết kế message dễ dùng và dễ kiểm thử

Một diagnostic tốt nên trả lời được **cái gì sai, sai ở đâu, và sửa thế nào**. Ví dụ thay vì:

```text
Invalid annotation
```

nên dùng thông điệp như:

```text
[NAME001] @CheckedName.value must not be blank; provide a non-empty name
```

Trong demo đã dùng chuỗi ngắn có mã ổn định `[NAME001]`, `[NAME002]`, `[NAME000]`. Mã này giúp người dùng tìm tài liệu, viết unit test ít phụ thuộc ngôn ngữ và phân biệt lỗi của processor với lỗi của `javac`.

Khuyến nghị:

1. Mỗi loại validation có **một diagnostic code ổn định** và severity nhất quán.
2. Gắn diagnostic vào vị trí có khả năng **sửa trực tiếp nhất**.
3. Không hiển thị dữ liệu nhạy cảm vô ích trong message, đặc biệt các annotation values chứa cấu hình nội bộ.
4. Phân biệt quy tắc bắt buộc với lời khuyên, tránh dùng `ERROR` cho stylistic preference.
5. Gợi ý hành động cụ thể: “provide non-empty value”, “use supported enum”, “add missing method”, thay vì thông báo chung.
6. Với processor phức tạp, dùng message catalog nếu cần hỗ trợ nhiều ngôn ngữ; Java API `ProcessingEnvironment.getLocale()` có thể hỗ trợ chính sách localization khi môi trường cung cấp.

**Không hứa ổn định line/column hoặc wording của compiler** qua mọi JVM. Thứ có thể ổn định theo thiết kế processor là diagnostic code, điều kiện phát sinh và quan hệ với phần tử/giá trị được kiểm tra.

## 15. Viết test cho vị trí và mức độ diagnostic

Có hai lớp kiểm thử bổ sung cho nhau:

### Integration test với javac (như bài lab)

- **Case lỗi:** `Cases.java` tạo `1 error`, `1 warning` và `1 Note`; exit code khác 0.
- **Case chỉ cảnh báo:** `Warning.java` tạo warning; exit code 0.
- **Case chỉ note:** `Good.java` tạo note; exit code 0.
- **Case warning có `-Werror`:** `Warning.java` lúc này làm build fail.
- **Kiểm tra vị trí:** trên `javac` chuẩn ở thí nghiệm, dấu `^` của lỗi/cảnh báo chỉ ngay vào value, còn note chỉ annotation.

Tại PowerShell, đọc **`$LASTEXITCODE` ngay sau khi chạy `javac`**:

```powershell
javac --release 17 -cp out/processor -processorpath out/processor -processor diagnostics.NameProcessor -proc:only examples/Cases.java
$LASTEXITCODE
```

Ví dụ `Cases.java` trả `1` trong lần kiểm chứng. Ở Bash/zsh, lệnh `echo $?` ngay sau `javac` cung cấp trạng thái. Hãy đọc exit code trước khi chạy thêm lệnh khác để tránh lấy nhầm trạng thái.

**Không tự giả định “warning là lỗi”** khi chưa bật quality gate. Đầu ra có một warning nhưng exit code 0 là hoàn toàn bình thường theo compiler mode mặc định.

### Test theo Java Compiler API

Các công cụ unit test có thể dùng:

```java
javax.tools.DiagnosticCollector<
        javax.tools.JavaFileObject> diagnostics =
        new javax.tools.DiagnosticCollector<>();
```

Đây là một **mảnh mã minh họa việc khai báo collector**, chưa phải chương trình test đầy đủ. `JavaCompiler.getTask(...)` có thể nhận `DiagnosticListener`; sau compilation, test có thể duyệt `diagnostics.getDiagnostics()` để kiểm tra:

- `diagnostic.getKind()` có phải `ERROR`/`WARNING`/`NOTE` đúng kỳ vọng.
- Message chứa code `[NAME001]` hay `[NAME002]`.
- Nguồn và vị trí có được cung cấp khi môi trường hỗ trợ.
- Boolean result của compilation đúng với case.

Nếu processor chạy trong JVM có sẵn bằng Java Compiler API, cách cấu hình processor instance/path có thể khác lệnh `javac` độc lập. Không khẳng định mọi `-processorpath` command-line option đều được truyền theo cùng một đường trong tất cả build tools.

Khi cần kiểm tra position, so sánh **có nguồn và thuộc vùng annotation** thay vì cố đóng đinh số cột đúng mọi phiên bản compiler. Đó là một bài kiểm thử ít giòn hơn.

## 16. Checklist trước khi công bố annotation processor

- [ ] Quy tắc validation có phân biệt **bắt buộc** và **khuyến nghị**.
- [ ] `ERROR` dùng cho trường hợp source thực sự không hợp lệ theo hợp đồng processor.
- [ ] `WARNING` dùng khi build vẫn có thể tiếp tục; tương tác với `-Werror` đã được kiểm chứng.
- [ ] Mỗi diagnostic mang mã và thông điệp hướng sửa cụ thể.
- [ ] Diagnostic thuộc class/field/method gắn đúng `Element`.
- [ ] Diagnostic thuộc annotation gắn đúng `AnnotationMirror`.
- [ ] Diagnostic thuộc một thuộc tính annotation gắn đúng `AnnotationValue` khi có nguồn thích hợp.
- [ ] Đã kiểm tra cả giá trị **được chỉ định** và giá trị **mặc định** nếu hợp đồng cần.
- [ ] Không tạo diagnostic trùng vô nghĩa qua nhiều processing rounds.
- [ ] Processor khai báo `@SupportedAnnotationTypes` và supported source version đúng.
- [ ] Build/test ghi nhận JDK version, classpath/processor path, mode annotation processing và exit code.
- [ ] Các ví dụ lỗi, warning, thành công đều được test với source độc lập.
- [ ] Không dùng `throw` hoặc `println` làm cách thông báo chính đối với lỗi validation của người dùng.

## 17. Bài tập có đáp án

**Bài 1: Chọn overload cho lỗi giá trị**

Bạn có `@Range(min = -2)` trên một method, và quy tắc yêu cầu `min >= 0`. Nên gắn diagnostic vào đâu?

**Đáp án:** Dùng overload có `Element` của method, `AnnotationMirror` của `@Range` và `AnnotationValue` của `min = -2`. Nếu `min` không được viết mà lấy default không hợp lệ, gắn vào mirror/element có thể hữu ích hơn vì không có vị trí token của giá trị ấy tại annotation use.

**Bài 2: Có thể in console để compiler tự hiểu là lỗi?**

Processor gọi `System.err.println("Error")` nhưng không phát diagnostic. Compiler có mặc nhiên trả exit code thất bại không?

**Đáp án:** Không. Một dòng chữ console không phải `Diagnostic.Kind.ERROR`. Dùng `Messager.printMessage(ERROR, ...)` để compiler nhận lỗi có cấu trúc.

**Bài 3: return true có làm build pass?**

Processor phát một `ERROR` rồi trả `true`. Build có thành công không?

**Đáp án:** Không, `true` chỉ claim annotation types; `ERROR` vẫn khiến compilation thất bại.

**Bài 4: Warning và -Werror**

Processor phát duy nhất `WARNING`. Ở chế độ mặc định, compilation có thể thành công không? Với `-Werror` thì sao?

**Đáp án:** Có thể thành công khi không có lỗi khác. Khi `-Werror` áp dụng, warning làm compiler báo lỗi build theo chính sách này.

**Bài 5: Annotation default**

`@Threshold` bỏ qua `min() default 0`. `getElementValues()` có luôn trả `min=0` không?

**Đáp án:** Không; `getElementValues()` chỉ trả các thành phần được cung cấp tường minh. Dùng `Elements.getElementValuesWithDefaults(...)` để tính cả default.

**Bài 6: Chẩn đoán trùng**

Processor phát lại cùng `ERROR` cho một class ở hai rounds. Việc này giúp compile chắc chắn fail hơn không?

**Đáp án:** Không. Một error đã có hiệu lực; báo lặp gây nhiễu. Nên làm rõ vòng xử lý, tập element và quy tắc deduplication.

**Bài 7: Mức độ và vị trí của NOTE**

Chương trình `Good.java` chỉ tạo `NOTE` ở `@CheckedName("Customer")`. Vì sao không có class file sau khi compile?

**Đáp án:** Vì lệnh test dùng `-proc:only`, không phải do `NOTE`. Bỏ `-proc:only` và compile bình thường nếu muốn phát sinh class file.

## 18. Tổng kết và tài liệu chính thống

`Messager` giúp annotation processor báo **lỗi/cảnh báo/thông tin** thông qua hệ thống diagnostic chính thức của compiler. Những overload nhận `Element`, `AnnotationMirror` và `AnnotationValue` là phương pháp quan trọng để **gắn diagnostic đúng chỗ người dùng cần sửa**, thay vì chỉ báo một dòng log không ngữ cảnh. Mức độ `ERROR`/`WARNING`/`NOTE` quyết định cách compiler và build tool phản hồi; nó **không được điều khiển bởi giá trị trả về của `process(...)`**.

Tài liệu tham khảo:

1. [Java SE 17 — javax.annotation.processing.Messager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Messager.html): bốn overload, vị trí gợi ý, mức lỗi/warning/note.
2. [Java SE 17 — javax.tools.Diagnostic.Kind](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.Kind.html): các loại diagnostic.
3. [Java SE 17 — javax.annotation.processing.RoundEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): elements theo round, `processingOver`, `errorRaised`.
4. [Java SE 17 — javax.lang.model.element.AnnotationMirror](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationMirror.html): đọc annotation model và giá trị được khai báo tường minh.
5. [Java SE 17 — javax.lang.model.util.Elements](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html): `getElementValuesWithDefaults`.
6. [JDK 17 — javac command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `-processor`, `-processorpath`, `-proc:only`, `-Werror` và cấu hình compile.

**Tư duy cần nhớ:** khi phát hiện một vi phạm, xác định **mức độ** trước (`ERROR` hay `WARNING`), xác định **đối tượng bị lỗi** sau (`Element`, annotation hay value), rồi đưa cả hai thông tin cho `Messager`. Một processor chất lượng không chỉ biết mã nguồn sai, mà còn giúp người dùng tìm ra **chính xác cần sửa ở đâu và vì sao**.