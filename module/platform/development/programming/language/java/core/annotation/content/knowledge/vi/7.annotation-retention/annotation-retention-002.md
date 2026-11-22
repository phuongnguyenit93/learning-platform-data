# RetentionPolicy.SOURCE: siêu dữ liệu annotation chỉ tồn tại ở mã nguồn Java

Khi đọc một annotation như `@Override` hoặc `@SuppressWarnings`, ta thường thấy nó ảnh hưởng đến quá trình **biên dịch** nhưng không xuất hiện khi chương trình đã chạy. Java hỗ trợ cách thiết kế này bằng chính sách **`RetentionPolicy.SOURCE`**: compiler nhìn thấy annotation trong mã nguồn để kiểm tra hoặc xử lý, sau đó **không lưu lần sử dụng annotation đó vào biểu diễn nhị phân của class**.

Khai báo cơ bản:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.SOURCE)
@interface CompileTimeHint {
    String value();
}
```

Với annotation này, `@CompileTimeHint("example")` có thể được gắn vào một khai báo hợp lệ, nhưng sau khi compiler hoàn tất, metadata về **lần gắn annotation** không còn trong `.class` tương ứng. Vì thế Java reflection ở runtime không thể đọc lại lần gắn đó.

Bài học tập trung vào: **SOURCE tồn tại ở giai đoạn nào, biến mất ở đâu, compiler/annotation processor dùng được nó ra sao, cách kiểm chứng với `javac` và `javap`, và khi nào nên chọn SOURCE thay vì CLASS/RUNTIME.**

## 1. Retention là gì?

**Retention policy** quy định mức độ giữ lại một annotation trong chu trình từ mã nguồn Java tới chương trình chạy. Ta đặt nó trên **định nghĩa annotation** bằng meta-annotation `@Retention`:

```java
@Retention(RetentionPolicy.SOURCE)
@interface SourceTag {}
```

`@Retention` là meta-annotation: annotation dùng để mô tả **một annotation khác**. Giá trị `RetentionPolicy.SOURCE` là hằng enum trong `java.lang.annotation.RetentionPolicy`.

Tại một nơi sử dụng:

```java
@SourceTag
class Service {}
```

có hai đối tượng kiến thức khác nhau:

1. **Định nghĩa `SourceTag`**: kiểu annotation được khai báo bằng `@interface SourceTag`. Nó là một kiểu Java có thể được biên dịch riêng thành `SourceTag.class`.
2. **Lần sử dụng `@SourceTag` trên `Service`**: metadata đính vào khai báo `Service`. Chính lần sử dụng này bị compiler loại khỏi `Service.class` khi retention là SOURCE.

Vì thế câu “annotation SOURCE không có trong bytecode” phải hiểu đúng là **lần gắn annotation SOURCE không được ghi vào binary của phần tử được chú thích**. Nó không có nghĩa compiler cấm tạo file `SourceTag.class` cho chính định nghĩa annotation.

## 2. Vòng đời của SOURCE: mã nguồn → compiler → bytecode → runtime

```text
Service.java
  @SourceTag
  class Service {}
        |
        v
Giai đoạn biên dịch:
  - Parser và compiler đọc @SourceTag
  - Kiểm tra tên annotation, vị trí @Target, kiểu element
  - Annotation processor (nếu được cấu hình) có thể đọc SOURCE
        |
        v
Service.class:
  - Có bytecode, class/method/field... theo chương trình
  - KHÔNG lưu lần sử dụng @SourceTag thuộc SOURCE
        |
        v
Runtime:
  - Reflection không thể lấy @SourceTag từ Service.class
  - Framework chỉ quét metadata trong .class cũng không thấy nó
```

Ý nghĩa của từng chặng:

- **Trước khi biên dịch:** annotation là một phần của source code, có cú pháp và giá trị element phải đúng quy tắc Java.
- **Trong khi biên dịch:** compiler có thể dùng annotation để kiểm tra mã, và annotation processor có thể thấy nó trong mô hình phần tử nguồn.
- **Khi tạo binary:** theo Java Language Specification, lần gắn annotation có retention SOURCE không được xuất hiện trong biểu diễn nhị phân của nơi được gắn.
- **Khi chạy:** các API như `Class.getAnnotation(...)` và `isAnnotationPresent(...)` không thể khôi phục annotation SOURCE trên class đã biên dịch.

**SOURCE không có nghĩa annotation bị xóa khỏi tệp `.java`.** Source code vẫn giữ nguyên trên ổ đĩa; “bị loại bỏ” ở đây mô tả cách compiler tạo biểu diễn nhị phân.

## 3. So sánh SOURCE, CLASS và RUNTIME

Java hỗ trợ ba mức retention:

| Chính sách | Compiler đọc ở lần biên dịch từ source? | Lưu lần sử dụng annotation trong `.class`? | Reflection runtime đọc được? |
|---|---|---|---|
| `RetentionPolicy.SOURCE` | Có | **Không** | **Không** |
| `RetentionPolicy.CLASS` | Có | Có, đối với trường hợp khai báo được lưu theo JLS | Mặc định **không** qua reflection Java chuẩn |
| `RetentionPolicy.RUNTIME` | Có | Có, đối với trường hợp khai báo được lưu theo JLS | **Có** qua reflection ở vị trí API hỗ trợ |

Ba ví dụ ý định sử dụng:

- **SOURCE:** hỗ trợ compiler hoặc công cụ phân tích mã nguồn; không cần metadata của lần gắn sau biên dịch.
- **CLASS:** lưu metadata để công cụ đọc/biến đổi file class hoặc phân tích binary, dù Java reflection runtime không hiển thị mặc định.
- **RUNTIME:** metadata phải được các API reflection phù hợp nhìn thấy khi chương trình chạy; thường dùng cho framework đọc cấu hình annotation lúc khởi động hoặc xử lý request.

**Điểm rất dễ quên:** nếu **không khai báo `@Retention`**, annotation mặc định có retention **CLASS**, không phải SOURCE cũng không phải RUNTIME:

```java
@interface DefaultRetention {
    String value();
}
```

`DefaultRetention` trên một class sẽ theo retention CLASS theo mặc định. Muốn annotation chỉ phục vụ compile time và bị loại khỏi binary thì phải ghi rõ `@Retention(RetentionPolicy.SOURCE)`.

Ngoài ra, JLS có ngoại lệ liên quan đến annotation trên **khai báo biến cục bộ** hoặc **tham số hình thức của lambda** khi xét sự tồn tại trong class file đối với CLASS/RUNTIME; không nên suy rộng bảng này thành cam kết mọi vị trí dùng CLASS/RUNTIME đều được reflection truy xuất như nhau. Với SOURCE, quy tắc loại bỏ lần sử dụng khỏi binary vẫn rõ ràng.

## 4. Ví dụ Java 17+ chạy được: SOURCE biến mất khỏi runtime

Tạo file duy nhất tên `RetentionSourceDemo.java`:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface SourceHint {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface ClassHint {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RuntimeHint {
    String value();
}

@SourceHint("source-only")
@ClassHint("bytecode")
@RuntimeHint("runtime")
class Sample {}

public class RetentionSourceDemo {
    public static void main(String[] args) {
        System.out.println(
                "SOURCE visible: "
                        + Sample.class.isAnnotationPresent(SourceHint.class)
        );
        System.out.println(
                "CLASS visible: "
                        + Sample.class.isAnnotationPresent(ClassHint.class)
        );
        System.out.println(
                "RUNTIME visible: "
                        + Sample.class.isAnnotationPresent(RuntimeHint.class)
        );
        System.out.println(
                "RUNTIME value: "
                        + Sample.class.getAnnotation(RuntimeHint.class).value()
        );
    }
}
```

Biên dịch và chạy trong thư mục chứa file:

```bash
javac --release 17 RetentionSourceDemo.java
java RetentionSourceDemo
```

Kết quả chính xác:

```text
SOURCE visible: false
CLASS visible: false
RUNTIME visible: true
RUNTIME value: runtime
```

**Tại sao?** `Sample` được gắn cả ba annotation trên cùng một khai báo. Nhưng chính sách retention khác nhau quyết định metadata nào tồn tại lúc chạy. `@SourceHint` bị compiler loại khỏi `Sample.class`, `@ClassHint` được ghi vào class file nhưng không được exposed bởi runtime reflection thông thường, còn `@RuntimeHint` vừa được ghi vừa được phép đọc reflectively.

Có thể kiểm tra sâu hơn bằng công cụ `javap` đi cùng JDK:

```bash
javap -v Sample
```

Trong phần metadata của `Sample.class`:

- Sẽ có dấu vết `ClassHint` dưới dạng annotation lưu trong binary (thường ở `RuntimeInvisibleAnnotations`).
- Sẽ có `RuntimeHint` dưới dạng annotation dành cho runtime (thường ở `RuntimeVisibleAnnotations`).
- **Không có lần sử dụng `SourceHint`** được lưu trong `Sample.class`.

Tên các trường, thứ tự dòng, chỉ số constant pool trong output `javap -v` có thể khác theo JDK; thay vì so sánh toàn bộ output, hãy tìm ba tên annotation tương ứng. Với tệp `Sample.class` trong ví dụ này, `SourceHint` không xuất hiện trong dump. Nếu xem riêng `SourceHint.class`, bạn sẽ thấy đó vẫn là một kiểu annotation đã biên dịch; hai việc này không mâu thuẫn.

## 5. SOURCE vẫn hữu ích khi biên dịch: compiler và annotation processor

Việc không giữ annotation đến runtime **không** khiến nó vô dụng. Có hai nhóm ứng dụng compile time thường gặp:

**Compiler xử lý annotation chuẩn.** Chẳng hạn `@Override` dùng để yêu cầu kiểm tra một method có thực sự override/implement method theo luật Java; `@SuppressWarnings` yêu cầu compiler bỏ một số nhóm warning trong phạm vi hợp lệ. Hai annotation chuẩn này dùng retention SOURCE theo Java SE 17. Không cần reflection runtime để chúng có hiệu lực.

**Annotation processor xử lý annotation tùy biến.** Trong Java, API `javax.annotation.processing` cho phép một processor truy cập thông tin về các source element và annotation trên chúng trong lúc `javac` chạy. Một annotation SOURCE tự định nghĩa thường dùng để:

- kiểm tra quy ước compile time (naming/contract/required elements);
- tạo tệp nguồn Java hoặc tài nguyên build thông qua `Filer`;
- tạo cảnh báo/lỗi biên dịch bằng `Messager` khi cấu hình không hợp lệ;
- thu thập thông tin khai báo để sinh code thay vì phụ thuộc quét annotation ở runtime.

**Cần đăng ký hoặc chỉ định processor** bằng cấu hình build/`javac`. Chỉ tạo `@interface MyAnnotation` có retention SOURCE **không tự phát sinh nghiệp vụ, kiểm tra riêng hay sinh code**. Compiler vẫn kiểm tra cú pháp annotation và các quy tắc ngôn ngữ; phần hành vi tùy biến phải do processor hoặc công cụ khác triển khai.

## 6. Thí nghiệm Java 17: annotation processor đọc SOURCE rồi nó biến mất

Thí nghiệm này chứng minh trực tiếp rằng **annotation SOURCE có thể được xử lý khi compile source nhưng không còn trên class file sau khi biên dịch**.

Tạo ba tệp cùng một thư mục. Ví dụ dùng default package để đơn giản hóa các lệnh `javac`; trong dự án thực tế nên tổ chức package riêng.

**Tệp `SourceTag.java` — annotation chỉ giữ ở source:**

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface SourceTag {
    String value();
}
```

**Tệp `PrintSourceTagProcessor.java` — processor đọc annotation ở compile time:**

```java
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("SourceTag")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class PrintSourceTagProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        for (Element element
                : roundEnv.getElementsAnnotatedWith(SourceTag.class)) {
            SourceTag tag = element.getAnnotation(SourceTag.class);
            System.out.println("processing: "
                    + element.getSimpleName()
                    + " -> " + tag.value());
        }
        return true;
    }
}
```

**Tệp `AnnotatedTask.java` — khai báo được gắn SOURCE:**

```java
@SourceTag("validate-me")
class AnnotatedTask {}
```

Đứng trong thư mục chứa cả ba tệp, biên dịch annotation và processor trước:

```bash
javac --release 17 SourceTag.java PrintSourceTagProcessor.java
```

Sau đó biên dịch **mã nguồn** `AnnotatedTask.java` với processor được chỉ định rõ ràng:

```bash
javac --release 17 -cp . -processorpath . -processor PrintSourceTagProcessor AnnotatedTask.java
```

Output do processor chủ động in ra:

```text
processing: AnnotatedTask -> validate-me
```

Cuối cùng, kiểm tra class được tạo:

```bash
javap -v AnnotatedTask
```

Output đầy đủ của `javap` gồm nhiều chi tiết về class file; **không có lần gắn `@SourceTag("validate-me")`** trong metadata `AnnotatedTask.class`.

Trong quá trình biên dịch, `roundEnv.getElementsAnnotatedWith(SourceTag.class)` tìm thấy `AnnotatedTask`, và `element.getAnnotation(SourceTag.class)` lấy giá trị `"validate-me"` từ mô hình annotation ở giai đoạn processing. Khi compiler phát sinh class file, lần gắn SOURCE bị loại. Vì vậy hai kết quả không mâu thuẫn.

Ví dụ processor chỉ **in thông tin** để quan sát; nó chưa phát sinh mã, cũng chưa ép điều kiện validate nào. Muốn báo lỗi biên dịch, processor có thể dùng `processingEnv.getMessager().printMessage(Diagnostic.Kind.ERROR, ..., element)`; muốn tạo file, dùng `processingEnv.getFiler()`. Việc tạo file/đọc tài nguyên không phải chức năng tự có của retention SOURCE.

## 7. Những gì SOURCE làm được và những gì không làm được

| Nhu cầu | SOURCE có phù hợp? | Giải thích |
|---|---|---|
| Yêu cầu compiler xác minh method override | Có | Ví dụ `@Override`, hành vi được compiler định nghĩa |
| Bỏ một số cảnh báo compiler | Có | Ví dụ `@SuppressWarnings("unchecked")` |
| Processor tạo code từ khai báo nguồn | Có | Processor được gọi trong build và thấy SOURCE |
| Kiểm tra quy ước khi tác giả biên dịch các source liên quan | Có | Nếu processor/tool được cấu hình, annotation hiện diện trong lượt compile đó |
| Framework dùng reflection đọc annotation lúc startup | **Không** | Metadata SOURCE không ở class file |
| Runtime DI quét `@SourceTag` trên bean | **Không** | Scanner/runtime không thể đọc lần gắn đã mất |
| Công cụ đọc bytecode của thư viện đã build để tìm `@SourceTag` | **Không** | Binary không lưu lần gắn SOURCE |
| Lưu cấu hình để runtime quyết định behavior | **Không** | Cần lựa chọn lưu khác, thường là RUNTIME hoặc dữ liệu sinh ra |
| Một lần compile thư viện, consumer muốn xử lý lại SOURCE khi chỉ có JAR | **Không theo cách đọc annotation gốc** | JAR không mang lần gắn SOURCE để processor phục hồi |

Cần phân biệt **processor đọc SOURCE ở lúc compile source** với **processor đọc annotation trên một class đã được biên dịch trước đó**. Khi input chỉ còn bytecode, dữ liệu SOURCE ở nơi sử dụng đã bị loại; annotation processor không thể tự tái dựng những gì không được lưu.

## 8. SOURCE không giống @Target, và không bảo đảm hành vi nghiệp vụ

Hai meta-annotation trả lời hai câu hỏi khác nhau:

- `@Target`: annotation **được phép đặt ở đâu** (class, method, field, parameter, type use, v.v.).
- `@Retention`: annotation **được giữ tới giai đoạn nào** (SOURCE, CLASS, RUNTIME).

Ví dụ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.SOURCE)
@interface Reviewed {
    String reviewer();
}

class Checkout {
    @Reviewed(reviewer = "team")
    void pay() {}
}
```

`@Reviewed` hợp lệ ở method và compiler sẽ kiểm tra giá trị element đúng kiểu. Nhưng **không có luật Java mặc định** nào tự xác minh người review, tạo audit log hay ngăn deploy. Muốn có quy tắc như “reviewer không được rỗng”, phải viết processor hoặc công cụ phân tích riêng. `@Target(METHOD)` không ảnh hưởng chính sách SOURCE, và `@Retention(SOURCE)` không cho phép đặt annotation vào các vị trí ngoài `@Target`.

Có thể gắn `@Documented` hoặc các meta-annotation khác khi phù hợp nhu cầu tài liệu; chúng không tự nâng retention từ SOURCE lên RUNTIME.

## 9. Vì sao SOURCE thường hữu ích cho thiết kế build-time?

Có những thông tin chỉ cần ở lúc xây dựng phần mềm. Lưu chúng vào binary có thể không cần thiết:

1. **Compiler cần ngay khi kiểm tra source**, chẳng hạn cảnh báo hoặc override.
2. **Processor có thể chuyển annotation thành artifact khác** như Java source, metadata file, hay diagnostics. Artifact được tạo (nếu có) tồn tại theo cơ chế tạo của processor; bản thân lần gắn SOURCE vẫn không nằm trong class file.
3. **Runtime ít bị phụ thuộc hơn** vào việc đọc annotation gốc. Code runtime nên tiêu thụ artifact đã sinh hoặc cấu hình runtime theo thiết kế của ứng dụng.

Ví dụ một framework build-time có `@GenerateAdapter` retention SOURCE. Annotation processor có thể tạo class adapter từ source được đánh dấu. Khi chương trình chạy, adapter đã được compile như class bình thường và hoạt động dù `@GenerateAdapter` không còn trong bytecode. Đây là **thiết kế có processor sinh code**, không phải hành vi mặc định của mọi SOURCE annotation.

Ngược lại, nếu framework runtime dùng `SomeClass.class.getAnnotation(...)` để quyết định đăng ký handler, chuyển annotation sang SOURCE sẽ làm runtime không đọc được nó. Lúc này `@Retention(RUNTIME)` thường là lựa chọn phù hợp hơn.

## 10. Các lỗi hiểu nhầm phổ biến

### Lỗi 1: Quên @Retention rồi nghĩ annotation mặc định là SOURCE

```java
@interface ConfigMarker {}

@ConfigMarker
class Component {}
```

Annotation `ConfigMarker` có retention mặc định **CLASS**. Muốn SOURCE cần:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.SOURCE)
@interface SourceOnlyMarker {}
```

### Lỗi 2: Dùng getAnnotation để đọc SOURCE lúc chạy

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.SOURCE)
@interface SourceAudit {}

@SourceAudit
class AuditJob {}

class AuditReader {
    static boolean check() {
        return AuditJob.class.isAnnotationPresent(SourceAudit.class);
    }
}
```

`check()` trả về `false`. Nó không chứng minh mã nguồn chưa từng chứa `@SourceAudit`; nó chứng minh reflection không nhìn thấy annotation SOURCE trên class đã compile.

### Lỗi 3: Nghĩ annotation SOURCE sẽ tự kích hoạt một processor

```java
@Retention(RetentionPolicy.SOURCE)
@interface Validate {}
```

Định nghĩa này mới chỉ chọn retention. Cần có processor/kiểm tra compiler tương ứng và cấu hình để công cụ đó chạy. Nếu không có, `@Validate` thường chỉ được Java kiểm tra theo các quy tắc chung của annotation (tên, element, `@Target`,...).

### Lỗi 4: Nghĩ SOURCE có nghĩa tệp định nghĩa annotation không được biên dịch

`SourceTag.java` vẫn là một khai báo kiểu, và `javac` vẫn có thể tạo `SourceTag.class`. Chính metadata **trên lớp được đánh dấu**, chẳng hạn `@SourceTag` trên `AnnotatedTask`, bị loại khỏi `AnnotatedTask.class`.

### Lỗi 5: Mong processor xử lý SOURCE từ JAR đã build sẵn

Nếu một JAR chứa `AnnotatedTask.class` được tạo từ nguồn có `@SourceTag`, lần gắn đó không còn trong binary. Processor chạy ở một project khác, chỉ thấy class đã build, không thể khám phá lại metadata SOURCE ban đầu. Nếu cần cơ chế tiêu thụ xuyên project, hãy thiết kế artifact metadata được sinh và đóng gói, hoặc chọn retention khác phù hợp.

### Lỗi 6: Đổi retention để chữa lỗi thiếu processor

Nếu processor không chạy do cấu hình build, chuyển `SOURCE` sang `RUNTIME` **không tự làm processor được gọi**. Cần kiểm tra `-processor`, `-processorpath`, dependency processor và build configuration. Retention quyết định giữ metadata, còn cơ chế kích hoạt processor là câu chuyện riêng.

### Lỗi 7: Nghĩ SOURCE loại bỏ mọi tác động đến quá trình build

Annotation SOURCE có thể dẫn đến diagnostic từ compiler, diagnostic hoặc file do processor sinh ra. Nó biến mất khỏi bytecode của nơi được gắn, nhưng **những quyết định và artifact được tạo trong quá trình biên dịch vẫn có thể ảnh hưởng chương trình cuối cùng**. Điều này giải thích vì sao SOURCE vừa không hiện diện ở runtime vừa hữu ích trong hệ thống sinh code.

## 11. Chọn SOURCE hay retention khác?

Hãy hỏi **ai cần đọc annotation** và **đọc vào thời điểm nào**:

| Câu hỏi thiết kế | Hướng chọn |
|---|---|
| Chỉ compiler hoặc processor khi biên dịch source cần thông tin? | `SOURCE` |
| Công cụ xử lý file `.class` sau khi build cần đọc metadata? | Cân nhắc `CLASS` hoặc `RUNTIME` tùy công cụ |
| Application/framework đọc annotation bằng reflection khi chạy? | `RUNTIME` |
| Không khai báo retention có chấp nhận được? | Chỉ khi muốn hành vi mặc định `CLASS` |
| Muốn kiểm soát nơi được gắn (class, method, field...)? | Khai báo `@Target` **độc lập** với retention |

**Quy tắc thiết kế:** chọn retention ngắn nhất vẫn đáp ứng đúng người tiêu thụ metadata. Nếu toàn bộ quyết định được hoàn tất ở compile time, SOURCE thường thể hiện intent rõ và không đưa lần gắn annotation vào binary. Nếu runtime phụ thuộc metadata gốc, SOURCE sẽ không đáp ứng được.

## 12. Bài tập tự kiểm tra

**Bài 1.** Khai báo:

```java
@Retention(RetentionPolicy.SOURCE)
@interface CheckName {}

@CheckName
class Customer {}
```

Sau khi biên dịch, `Customer.class.getAnnotation(CheckName.class)` có trả về đối tượng annotation không?

**Đáp án:** không; nó trả về `null` vì `@CheckName` trên `Customer` có retention SOURCE và không được lưu vào binary.

**Bài 2.** Một annotation không có `@Retention` sẽ thuộc chính sách nào?

**Đáp án:** `RetentionPolicy.CLASS`. Đừng giả định SOURCE chỉ vì một annotation được dùng lúc viết source.

**Bài 3.** Nếu một processor được gọi trong lúc `javac` biên dịch file `Customer.java`, nó có thể nhận biết `@CheckName` không?

**Đáp án:** có, nếu processor được cấu hình và xử lý đúng loại annotation. Quy tắc SOURCE không ngăn compile-time processor truy cập metadata từ source đang biên dịch.

**Bài 4.** Nếu processor chỉ được chạy sau đó trong một project tiêu thụ `Customer.class` từ JAR và không có mã nguồn `Customer.java`, nó có còn nhìn thấy `@CheckName` không?

**Đáp án:** không. Lần gắn SOURCE đã bị loại khỏi binary nên processor không thể khôi phục nó chỉ từ JAR.

**Bài 5.** Một framework dùng reflection để quét annotation trên class khi khởi động. Chọn SOURCE hay RUNTIME?

**Đáp án:** `RUNTIME` vì framework cần đọc annotation ở runtime. Có thể dùng SOURCE nếu kiến trúc thay đổi để compile-time processor tạo metadata/artifact riêng mà runtime tiêu thụ, nhưng khi đó framework **không còn đọc annotation SOURCE trực tiếp qua reflection**.

**Bài 6.** Tại sao `javap -v Sample` có thể hiển thị `ClassHint` nhưng `Sample.class.isAnnotationPresent(ClassHint.class)` lại trả `false`?

**Đáp án:** CLASS lưu lần gắn annotation trong file class nhưng reflection Java chuẩn không công bố annotation đó ở runtime; đó là sự khác biệt giữa việc metadata **có mặt trong binary** và việc **được phản chiếu tại runtime**.

## Tài liệu tham khảo

- [Java SE 17 — RetentionPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html): SOURCE, CLASS, RUNTIME và ý nghĩa mỗi mức.
- [Java SE 17 — @Retention](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html): meta-annotation khai báo retention và mặc định CLASS.
- [JLS Java SE 17 `9.6.4.2 — Retention](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.2): quy tắc bắt buộc khi compiler tạo binary, các trường hợp ngoại lệ.
- [Java SE 17 — Annotation Processing](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/package-summary.html): các API processor và xử lý compile time.
- [Java SE 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): công cụ compiler và tùy chọn processor.
