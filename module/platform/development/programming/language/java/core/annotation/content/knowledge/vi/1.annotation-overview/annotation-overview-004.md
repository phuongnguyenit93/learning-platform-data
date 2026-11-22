# Ba cách khai thác annotation trong Java: trình biên dịch, công cụ và chương trình lúc chạy

Annotation là **metadata (siêu dữ liệu)** gắn lên một thành phần Java như lớp, phương thức hoặc trường. Nó mô tả thêm thông tin về thành phần đó để **một bên khác đọc và xử lý**. Bản thân dấu `@...` không tự chạy logic, không tự kiểm tra nghiệp vụ và không tự tạo hành vi cho đối tượng.

Một annotation có thể được khai thác theo ba hướng:

1. **Trình biên dịch (compiler)** hiểu annotation và thực hiện các kiểm tra/cảnh báo theo quy tắc của ngôn ngữ.
2. **Công cụ (tooling)** đọc annotation để phân tích, kiểm tra, tạo mã hoặc tạo tài liệu; annotation processor là ví dụ quan trọng.
3. **Chương trình lúc chạy (runtime)** đọc annotation còn tồn tại trên class file, thường qua Reflection, rồi quyết định thực hiện hành vi.

Ba hướng này có thể xuất hiện trong cùng một dự án nhưng **ai đọc, đọc ở giai đoạn nào, và kết quả là gì** phải được phân biệt.

## 1. Bản đồ ba cách khai thác

| Góc nhìn | Khi nào? | Ai đọc? | Tác dụng điển hình | Ví dụ |
| --- | --- | --- | --- | --- |
| Compiler | Khi `javac` biên dịch mã | Trình biên dịch Java | Kiểm tra khai báo, phát cảnh báo hoặc bỏ qua một nhóm cảnh báo | `@Override`, `@Deprecated`, `@SuppressWarnings` |
| Tooling | Thường trong build hoặc tác vụ phân tích riêng | Annotation processor, IDE, công cụ sinh mã/tài liệu, công cụ đọc bytecode | Kiểm tra quy ước, phát diagnostic, tạo mã/tệp, lập chỉ mục | Processor đọc `@ToolHint` |
| Runtime | Sau khi chương trình đã chạy | Mã ứng dụng/thư viện/framework | Đọc metadata để đăng ký, định tuyến, gọi xử lý hoặc thay đổi cấu hình | `Class.getAnnotation(...)`, framework quét annotation |

Luồng hình dung:

```text
Mã nguồn .java có annotation
        |
        +--> javac: quy tắc của compiler (@Override, @Deprecated, ...)
        |
        +--> processor/tool: phân tích, kiểm tra, sinh mã (khi được cấu hình)
        |
        v
      Class file .class
        |
        +--> metadata SOURCE: không lưu vào .class
        +--> metadata CLASS: lưu vào .class, không hiện qua Reflection chuẩn
        +--> metadata RUNTIME: lưu vào .class, có thể được Reflection đọc
        |
        v
Chương trình chạy: code chủ động truy vấn và xử lý annotation
```

Một annotation có thể phục vụ **nhiều consumer**. Ví dụ `@Deprecated` được compiler dùng để cảnh báo khi gọi API cũ và cũng có thể được công cụ phân tích đọc. Việc annotation tồn tại trong class file không đồng nghĩa chương trình tự động sử dụng nó.

## 2. Cách thứ nhất: compiler khai thác annotation

Đây là các annotation mà `javac` biết cách xử lý theo quy định của Java:

- `@Override`: xác nhận phương thức thực sự ghi đè hoặc triển khai một phương thức hợp lệ từ supertype. Gõ sai tên/chữ ký sẽ bị báo lỗi biên dịch thay vì âm thầm tạo một phương thức mới.
- `@Deprecated`: đánh dấu API không còn được khuyến nghị; compiler có thể cảnh báo ở nơi dùng API đó, tùy ngữ cảnh và tùy chọn cảnh báo. Thuộc tính `since` và `forRemoval` cung cấp thêm thông tin.
- `@SuppressWarnings("deprecation")`: yêu cầu compiler bỏ qua nhóm cảnh báo deprecation trong phạm vi khai báo được gắn annotation. Nó không xóa API cũ, không bỏ qua lỗi biên dịch khác và không thay đổi hành vi runtime.

**Ví dụ 1 — kiểm tra compiler và đọc metadata runtime trong cùng chương trình.** Tạo tệp `AnnotationConsumersDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RuntimeLabel {
    String value();
}

@RuntimeLabel("catalog")
class Catalog {
    @Deprecated(since = "17")
    static String legacyName() {
        return "legacy";
    }
}

public class AnnotationConsumersDemo {
    @SuppressWarnings("deprecation")
    public static void main(String[] args) {
        RuntimeLabel label = Catalog.class.getAnnotation(RuntimeLabel.class);
        System.out.println(label == null ? "<không tìm thấy>" : label.value());
        System.out.println(Catalog.legacyName());
    }

    @Override
    public String toString() {
        return "demo";
    }
}
```

Trong thư mục chứa tệp, dùng **JDK 17 trở lên**:

```bash
mkdir out
javac --release 17 -d out AnnotationConsumersDemo.java
java -cp out AnnotationConsumersDemo
```

Stdout chính xác:

```text
catalog
legacy
```

**Phân tích theo consumer:**

1. Compiler kiểm tra `toString()` thực sự override `Object.toString()` nhờ `@Override`. Thử đổi chữ ký thành `toString(int n)` nhưng giữ `@Override`: biên dịch không thành công.
2. Compiler biết `Catalog.legacyName()` đã bị `@Deprecated`. `@SuppressWarnings("deprecation")` trên `main` chặn cảnh báo deprecation tại lời gọi trong phương thức này; có thể xem cảnh báo khi xóa annotation suppress và biên dịch với `-Xlint:deprecation`.
3. Runtime không “thực thi `@RuntimeLabel`”. Chính lệnh `Catalog.class.getAnnotation(RuntimeLabel.class)` **chủ động đọc** metadata, sau đó mã của chúng ta in `value()` ra màn hình.
4. Lệnh gọi `Catalog.legacyName()` vẫn trả `"legacy"`. `@Deprecated` không vô hiệu hóa phương thức.

`--release 17` ở đây giữ ví dụ tương thích ngôn ngữ/API Java 17 khi sử dụng JDK mới hơn. Tên tệp phải là `AnnotationConsumersDemo.java` vì có `public class AnnotationConsumersDemo`.

### Compiler không tự hiểu mọi annotation tự định nghĩa

Nếu tạo `@Audit` hoặc `@CheckAccess` do bạn định nghĩa, `javac` chỉ kiểm tra **cách sử dụng hợp lệ** của annotation (kiểu phần tử, `@Target`, giá trị bắt buộc...). Compiler không tự đoán ý nghĩa nghiệp vụ như “ghi log khi gọi hàm” hoặc “chặn người dùng chưa đăng nhập”. Muốn có tác dụng đó phải có processor, công cụ hay mã runtime thực sự xử lý annotation.

## 3. Cách thứ hai: công cụ khai thác annotation

**Tooling** là nhóm rộng hơn annotation processor. IDE có thể phân tích source, bộ sinh tài liệu có thể đọc chú thích, công cụ build có thể quét class file và thư viện có thể sinh mã dựa trên annotation. Trong Java, cách phổ biến nhất để học cơ chế này là **annotation processing API** (`javax.annotation.processing`, JSR 269).

Một processor chạy **trong quá trình biên dịch khi được kích hoạt**, nhưng có trách nhiệm riêng với các kiểm tra nội tại của `javac`. Nó nhận mô hình các phần tử chương trình, tìm những phần tử được đánh annotation rồi phát diagnostic hoặc tạo thêm tệp bằng API được cung cấp. Processor không cần chạy chương trình ứng dụng.

**Ví dụ 2 — processor đọc một annotation chỉ tồn tại ở source.** Tạo ba tệp cùng thư mục, không khai báo `package` để tập trung vào cơ chế.

Tệp `ToolHint.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface ToolHint {
    String value();
}
```

Tệp `ToolHintProcessor.java`:

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

@SupportedAnnotationTypes("ToolHint")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class ToolHintProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        for (Element element : roundEnv.getElementsAnnotatedWith(ToolHint.class)) {
            ToolHint hint = element.getAnnotation(ToolHint.class);
            processingEnv.getMessager().printMessage(
                Diagnostic.Kind.NOTE,
                "ToolHint: " + element.getSimpleName() + " => " + hint.value(),
                element
            );
        }
        return true;
    }
}
```

Tệp `ImportantService.java`:

```java
@ToolHint("review endpoint contract")
public class ImportantService {
}
```

**Thực thi theo thứ tự** (có JDK 17+):

```bash
mkdir out
javac --release 17 -d out ToolHint.java ToolHintProcessor.java
javac --release 17 -cp out -processorpath out -processor ToolHintProcessor -d out ImportantService.java
```

Ở bước hai, `javac` hiển thị diagnostic thuộc loại `NOTE` với phần thông báo chính:

```text
ToolHint: ImportantService => review endpoint contract
```

Thông tin tên tệp, dòng và dấu mũ do compiler hiển thị xung quanh diagnostic có thể khác giữa các phiên bản/công cụ. Đây là **thông báo của processor khi biên dịch**, không phải stdout của chương trình `ImportantService`.

Giải thích các điểm then chốt:

- `@Retention(SOURCE)` cho phép processor thấy `@ToolHint` trên source; annotation **không cần tồn tại trong file `ImportantService.class`**.
- `@Target(TYPE)` giới hạn nơi dùng cho loại như class/interface; không được tùy ý chuyển `@ToolHint` sang một biến local.
- `@SupportedAnnotationTypes("ToolHint")` khai báo annotation processor quan tâm; dùng tên đầy đủ có package khi triển khai thực tế.
- `RoundEnvironment.getElementsAnnotatedWith(ToolHint.class)` tìm phần tử tương ứng ở vòng xử lý hiện tại. Processor có thể được gọi trong nhiều round, đặc biệt khi có mã được sinh; ví dụ chỉ in note cho những phần tử tìm thấy.
- `processingEnv.getMessager()` gửi diagnostic cho compiler. Trong dự án thật, processor còn có thể dùng `Filer` để sinh file nguồn hoặc resource.
- `-cp out` cho compiler thấy kiểu `ToolHint` của ứng dụng; `-processorpath out` chỉ nơi tìm processor; `-processor ToolHintProcessor` yêu cầu chạy processor cụ thể. Có thể đăng ký tự phát hiện processor qua service descriptor trong build thực tế.

Thử bỏ `-processor ToolHintProcessor` trong lệnh biên dịch thứ hai **và bảo đảm không có processor nào được tự đăng ký**: `ImportantService` vẫn là lớp Java hợp lệ nhưng sẽ không có thông báo riêng của `ToolHintProcessor`. Điều này cho thấy khai báo annotation chưa đủ để kích hoạt một công cụ.

**Phân biệt quan trọng:** compiler và processor cùng có thể hoạt động trong lệnh `javac`, nhưng `@Override` là một quy tắc được compiler Java tự kiểm tra, còn `@ToolHint` chỉ được diễn giải theo logic ta viết trong `ToolHintProcessor`.

## 4. Cách thứ ba: chương trình lúc chạy khai thác annotation

Khi dùng `@Retention(RUNTIME)`, thông tin annotation cần thiết được giữ trong class file để chương trình chạy có thể đọc bằng Reflection. Mã ứng dụng hoặc framework quyết định sẽ làm gì với thông tin được đọc.

Trong ví dụ 1:

```java
RuntimeLabel label = Catalog.class.getAnnotation(RuntimeLabel.class);
if (label != null) {
    String name = label.value();
    System.out.println(name);
}
```

`getAnnotation(RuntimeLabel.class)` trả một đối tượng biểu diễn annotation nếu loại annotation đó hiện diện theo quy tắc Reflection; có thể trả `null` nếu không tìm thấy. Vì vậy hãy kiểm tra null trước khi đọc giá trị khi không chắc annotation tồn tại.

Các API thường gặp:

| API | Nơi đọc | Điều cần nhớ |
| --- | --- | --- |
| `Class.getAnnotation(YourAnnotation.class)` | Annotation trên lớp | Có thể xét thừa kế theo quy tắc `@Inherited` |
| `Class.getDeclaredAnnotation(YourAnnotation.class)` | Annotation khai báo trực tiếp trên lớp | Không tìm annotation được thừa kế |
| `Method.getAnnotation(...)` | Annotation của phương thức | Phải lấy đúng đối tượng `Method` trước |
| `Field.getAnnotation(...)` | Annotation của trường | Phải lấy đúng đối tượng `Field` trước |
| `AnnotatedElement.getAnnotationsByType(...)` | Lấy các annotation theo kiểu, kể cả trường hợp lặp hợp lệ | Hữu ích với `@Repeatable` |

Ví dụ trong framework: framework có thể quét class/method để tìm annotation định tuyến, ánh xạ hoặc cấu hình rồi đăng ký handler tương ứng. **Framework chủ động xử lý annotation**; JVM không tự nhìn thấy `@Something` và gọi phương thức nghiệp vụ.

Reflection chỉ cho ta **đọc metadata**, không mặc nhiên áp đặt quy tắc truy cập, dependency injection, transaction hay validation. Muốn hành vi xảy ra phải có thành phần triển khai và được kích hoạt đúng lúc.

## 5. `@Retention` quyết định consumer nào có thể nhìn thấy

Ba chính sách trong `java.lang.annotation.RetentionPolicy`:

| Chính sách | Còn trong `.class`? | Reflection chuẩn đọc được khi chạy? | Tình huống phù hợp |
| --- | --- | --- | --- |
| `SOURCE` | Không | Không | Gợi ý/kiểm tra tại source, annotation processor |
| `CLASS` | Có | Không | Công cụ phân tích hoặc biến đổi bytecode sau biên dịch |
| `RUNTIME` | Có | Có | Logic runtime đọc qua Reflection |

Nếu **không khai báo `@Retention`**, mặc định là `RetentionPolicy.CLASS`.

Thử trong ví dụ 1 đổi:

```java
@Retention(RetentionPolicy.RUNTIME)
```

thành:

```java
@Retention(RetentionPolicy.CLASS)
```

Biên dịch lại rồi chạy: dòng đầu sẽ là `<không tìm thấy>`, dòng hai vẫn `legacy`. Metadata kiểu `RuntimeLabel` không thể được lấy bằng Reflection chuẩn với chính sách `CLASS`, dù annotation đó có thể còn được ghi trong class file.

Cần phân biệt **annotation được lưu trong bytecode** với **annotation được Reflection phơi bày**. Công cụ đọc/biến đổi bytecode vẫn có thể kiểm tra annotation `CLASS`, nhưng `Catalog.class.getAnnotation(RuntimeLabel.class)` không đọc được nó.

`@Target` là câu hỏi khác: annotation **được phép đặt ở đâu**; nó không quyết định runtime có đọc được hay không. Trong các ví dụ, `@Target(TYPE)` cho phép đánh dấu class, còn `@Retention(RUNTIME)` hoặc `SOURCE` quyết định vòng đời lưu giữ.

Một vài lưu ý thêm:

- `@Inherited` chỉ tác động trong những điều kiện riêng đối với annotation trên **class** khi truy vấn theo cơ chế thừa kế; không tự làm annotation trên method hoặc interface được kế thừa như annotation trên class cha.
- Annotation với `RUNTIME` không bảo đảm tool hay framework sẽ quét tới đối tượng đó. Còn phụ thuộc phạm vi scan, class loader, thời điểm khởi tạo và logic xử lý.
- Annotation processor có thể đọc `SOURCE` ở vòng biên dịch; suy luận “processor cũng đọc bằng Reflection runtime trên lớp ứng dụng” là sai về cơ chế trong ví dụ.
- `@SuppressWarnings` không phải công cụ bảo mật; nó chỉ ảnh hưởng cảnh báo biên dịch được hỗ trợ.

## 6. Chọn cách khai thác cho nhu cầu thực tế

| Mục tiêu | Nên bắt đầu từ | Vì sao? |
| --- | --- | --- |
| Bắt lỗi ghi đè phương thức ngay khi viết code | `@Override` với compiler | Phát hiện trước khi chạy, không cần infrastructure |
| Cảnh báo API cũ và chuyển dần API | `@Deprecated` cùng kiểm tra compiler/IDE | Thông báo cho người sử dụng API |
| Bắt quy tắc cấu trúc và sinh mã trong build | Annotation processor/tool | Phân tích ở build-time, có thể fail build hoặc tạo tài nguyên |
| Đăng ký handler, cấu hình hoặc ánh xạ lúc chạy | Annotation có `RUNTIME` + mã quét/xử lý | Quyết định dựa trên metadata khi ứng dụng khởi động hoặc đang chạy |
| Quét metadata đã biên dịch mà không chạy ứng dụng | Công cụ đọc `.class` | Có thể phân tích `CLASS` và `RUNTIME` qua bytecode |

Cần lựa chọn thời điểm xử lý có chủ đích. Nếu lỗi có thể được xác nhận hoàn toàn ở giai đoạn biên dịch, kiểm tra sớm thường cho feedback tốt. Nếu quyết định phụ thuộc trạng thái runtime, phải có thành phần chạy thực tế để xử lý. Có thể phối hợp cả hai khi có lý do.

## 7. Các lỗi hiểu sai thường gặp

**“Có annotation là hành vi tự chạy.”** Sai: khai báo annotation chỉ gắn metadata. Trong ví dụ 2, thông báo có được vì đã cấu hình và chạy `ToolHintProcessor`; trong ví dụ 1, chuỗi `catalog` được in vì mã chủ động gọi `getAnnotation`.

**“Annotation nào cũng có thể đọc bằng Reflection.”** Sai: với `SOURCE` hoặc `CLASS`, chương trình không thể đọc annotation ấy bằng Reflection chuẩn; cần `RUNTIME` cho cách lấy annotation ở runtime trong bài.

**“SOURCE vô dụng vì bị xóa khi compile.”** Sai: processor đã có thể sử dụng annotation đó **trước khi** nó bị loại khỏi class file.

**“Annotation processor và reflection là cùng một việc.”** Sai: processor làm việc với mô hình mã trong giai đoạn xử lý biên dịch; reflection truy vấn thông tin của kiểu/thành viên đã được nạp khi chương trình chạy.

**“`@Deprecated` hoặc `@SuppressWarnings` thay đổi kết quả của phương thức.”** Sai: chúng liên quan chủ yếu đến thông tin/cảnh báo; không tự làm phương thức ngừng hoạt động hoặc được gọi khác đi.

**“Đặt `RUNTIME` là đủ để framework xử lý.”** Sai: framework phải thực sự quét, nhận diện và xử lý annotation ấy; còn phải cấu hình đúng phạm vi quét.

## 8. Tự kiểm tra

1. Giữ `@RuntimeLabel("catalog")` nhưng đổi retention thành `SOURCE` rồi biên dịch/chạy lại ví dụ 1. Dự đoán kết quả của `getAnnotation` và giải thích.
2. Ở ví dụ 2, vì sao `@ToolHint` vẫn được processor đọc dù dùng `SOURCE`? Điều gì xảy ra nếu không kích hoạt processor?
3. Đặt `@ToolHint` lên một biến local. Vì sao compiler từ chối ngay cả khi processor không chạy?
4. Một thư viện muốn đọc annotation từ class đã nạp khi khởi động ứng dụng: cần retention nào và thêm bộ phận xử lý gì?
5. Phân biệt “compiler tự kiểm tra `@Override`” với “processor tự định nghĩa quy tắc cho `@ToolHint`” trong một câu.

**Đáp án định hướng:** (1) `getAnnotation` trả `null`, dòng đầu trong ví dụ sẽ in `<không tìm thấy>`; (2) processor đọc mô hình source trong khi biên dịch, nếu không chạy processor thì không có diagnostic của nó; (3) `@Target(TYPE)` không cho phép `LOCAL_VARIABLE`; (4) `RUNTIME` và mã/framework thực sự đọc, xử lý metadata; (5) quy tắc `@Override` thuộc compiler Java, còn quy tắc `@ToolHint` nằm trong processor do người phát triển cung cấp.

## 9. Ghi nhớ

Khi gặp một annotation mới, hãy hỏi liên tiếp: **Ai là consumer? Đọc ở giai đoạn nào? Metadata có tồn tại đủ lâu cho consumer đó không? Logic xử lý nằm ở đâu?** Bốn câu hỏi này giúp phân biệt chính xác chức năng compiler, tooling và runtime mà không gán nhầm hành vi cho bản thân annotation.