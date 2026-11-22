# Vai trò của công cụ kiểm tra kiểu: annotation trên kiểu không tự áp đặt ràng buộc

Trong Java, bạn có thể viết annotation lên **vị trí sử dụng kiểu** (*type use*) như `@NonNull String`, `List<@NonNull String>` hoặc `String @NonNull []`. Cú pháp này giúp chương trình và công cụ lưu hoặc đọc thông tin bổ sung về cách sử dụng kiểu. Tuy nhiên, **chỉ định nghĩa và gắn `@NonNull` không khiến `javac` mặc định cấm gán `null`**.

Ví dụ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@interface NonNull {}

class Example {
    @NonNull String name = null; // Java 17 javac vẫn chấp nhận
}
```

Annotation `@NonNull` ở đây có đúng `@Target(TYPE_USE)`, nên vị trí ghi là hợp lệ. Nhưng Java Core **chưa được cung cấp một quy tắc phân tích nullness nào cho annotation tự tạo này**. Tên `NonNull` và kiểu chữ trong tên annotation không tự tạo ra luật ràng buộc. Muốn compiler hoặc quy trình build cảnh báo/từ chối kiểu gán này, bạn phải dùng **type checker hoặc công cụ phân tích tĩnh hiểu rõ annotation đó**, được cài đặt/cấu hình để chạy; hoặc tự viết quy tắc kiểm tra phù hợp.

Bài học này làm rõ trách nhiệm của ngôn ngữ Java, annotation, type checker, annotation processor, reflection và kiểm tra runtime, đồng thời hướng dẫn cách quan sát bằng Java 17.

## 1. Java kiểm tra kiểu sẵn có, nhưng không tự hiểu mọi qualifier

Java là ngôn ngữ có kiểm tra kiểu tĩnh. `javac` vốn đã phân tích tính hợp lệ của phép gán, tham số, kiểu generic, override và nhiều quy tắc khác:

```java
int count = 10;     // Hợp lệ
// int wrong = "10"; // Lỗi compile time: String không gán được cho int
```

Cơ chế này dựa trên **hệ thống kiểu và luật gán của ngôn ngữ Java**. Annotation tùy chỉnh bổ sung *metadata* vào mã, chứ bản thân nó không trở thành một loại kiểu Java có luật gán mới.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@interface Trusted {}

class UserInput {
    @Trusted String value = "data";
}

class OtherInput {
    String value = "data";
}
```

Ở mức kiểu Java thông thường, cả hai field đều có kiểu `String`. `@Trusted` không tự sinh ra một subclass của `String`, một kiểu runtime mới hay quy tắc “chỉ String đã xác thực mới được gán”. Nếu một checker biết `Trusted` và luật tin cậy dữ liệu thì nó có thể **diễn giải** metadata thành điều kiện phân tích riêng.

Vì thế cần tách biệt:

1. **Luật kiểu gốc của Java**: compiler luôn thực hiện; annotation tùy chỉnh không thể bỏ qua các lỗi kiểu gốc.
2. **Luật sử dụng annotation**: compiler kiểm tra annotation tồn tại, vị trí dùng có phù hợp `@Target`, giá trị element có đúng kiểu hay không.
3. **Luật ngữ nghĩa tăng cường**: ví dụ “không gán null cho `@NonNull`”, “input đã được sanitize mới đi vào SQL”, “đơn vị mét không trộn với giây”. Các luật này cần công cụ hiểu qualifier và triển khai phân tích tương ứng.

### Annotation là lời mô tả, checker là nơi thực thi quy tắc

`@NonNull` có thể có ý nghĩa mô tả rất rõ với người đọc, nhưng **Java SE không chuẩn hóa ý nghĩa tổng quát của annotation tùy chỉnh có tên `NonNull`**. Một checker cụ thể có thể quy ước cách hiểu của nó; checker khác có thể dùng bộ annotation/độ nghiêm ngặt khác. Không nên suy ra rằng cứ thấy `@NonNull` là build đã được bảo vệ.

## 2. TYPE_USE là gì? Khác gì với annotation trên khai báo?

Java 8 giới thiệu khả năng gắn annotation tại các **vị trí sử dụng kiểu**, được định nghĩa trong JLS (`4.11 và `9.7.4). Meta-annotation `@Target(ElementType.TYPE_USE)` xác nhận annotation có thể đặt ở những vị trí đó.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;

@Target(ElementType.TYPE_USE)
@interface NonNull {}

class TypeUseExamples {
    @NonNull String title;
    List<@NonNull String> labels;
    @NonNull String[] elementsAnnotated;
    String @NonNull [] arrayAnnotated;

    @NonNull String describe(@NonNull String input) {
        @NonNull String local = input;
        return local;
    }
}
```

Đoạn trên là ví dụ cú pháp; các field chưa khởi tạo có giá trị mặc định nếu là instance field theo luật Java bình thường. `TYPE_USE` cho phép đặt qualifier ở:

- Một kiểu khi khai báo biến, field, tham số, kiểu trả về hoặc biến cục bộ.
- Type argument trong generic, như `List<@NonNull String>`.
- Kiểu thành phần và các chiều mảng; vị trí annotation quan trọng vì `@NonNull String[]` và `String @NonNull []` nhắm tới những phần khác nhau của kiểu mảng.
- Một số dạng cast, type argument, wildcard/bound, `implements`/`extends` và những vị trí dùng kiểu hợp lệ khác theo ngữ pháp Java.

**Sự khác biệt quan trọng:** `@NonNull String[]` có thể mô tả **kiểu phần tử String**, còn `String @NonNull []` gắn annotation ở **chiều mảng**. Một type checker có thể xem “mảng không null” và “phần tử không null” là hai ràng buộc riêng. `javac` không mặc định thi hành cả hai chỉ vì annotation xuất hiện.

Khi viết annotation cho **khai báo type parameter** (ví dụ tham số generic `T`), `ElementType.TYPE_PARAMETER` là mục tiêu được thiết kế cho vị trí khai báo đó; còn `TYPE_USE` nói về nơi dùng kiểu. Một annotation có thể cho phép cả hai:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({ElementType.TYPE_USE, ElementType.TYPE_PARAMETER})
@interface Marked {}

class Box<@Marked T> {
    @Marked T value;
}
```

Với annotation khai báo chỉ `@Target(ElementType.METHOD)`, không được tự đặt vào type argument như `List<@OnlyMethod String>`; compiler sẽ báo annotation không áp dụng được vào vị trí đó. **Đây là lỗi vị trí/cú pháp do Java trực tiếp kiểm tra**, hoàn toàn khác với việc kiểm tra nullness/taint của một qualifier hợp lệ.

## 3. Ví dụ chạy được: Java chấp nhận null dù kiểu có @NonNull

Tạo file duy nhất `TypeUseCheckerDemo.java`. Chương trình dùng annotation có `@Retention(RUNTIME)` để chúng ta còn đọc được vị trí sử dụng kiểu bằng reflection.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonNull {}

class Submission {
    public @NonNull String title = null;
    public List<@NonNull String> tags = new ArrayList<>();

    void populate() {
        tags.add(null);
    }
}

public class TypeUseCheckerDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        Submission submission = new Submission();
        submission.populate();

        Field titleField = Submission.class.getDeclaredField("title");
        Field tagsField = Submission.class.getDeclaredField("tags");
        AnnotatedType titleType = titleField.getAnnotatedType();
        AnnotatedParameterizedType tagsType =
                (AnnotatedParameterizedType) tagsField.getAnnotatedType();
        AnnotatedType elementType = tagsType.getAnnotatedActualTypeArguments()[0];

        System.out.println("title type annotated: "
                + titleType.isAnnotationPresent(NonNull.class));
        System.out.println("tag type annotated: "
                + elementType.isAnnotationPresent(NonNull.class));
        System.out.println("field declaration annotated: "
                + titleField.isAnnotationPresent(NonNull.class));
        System.out.println("null title accepted: " + (submission.title == null));
        System.out.println("null tag accepted: " + (submission.tags.get(0) == null));

        try {
            Objects.requireNonNull(submission.title, "title");
        } catch (NullPointerException e) {
            System.out.println("runtime guard: " + e.getMessage());
        }
    }
}
```

Biên dịch và chạy bằng Java 17:

```bash
javac --release 17 -Xlint:all TypeUseCheckerDemo.java
java TypeUseCheckerDemo
```

Kết quả chính xác:

```text
title type annotated: true
tag type annotated: true
field declaration annotated: false
null title accepted: true
null tag accepted: true
runtime guard: title
```

Điều thí nghiệm chứng minh:

1. Cả kiểu của field `title` lẫn kiểu đối số generic trong `tags` đều có annotation `@NonNull` và vẫn đọc được bằng `AnnotatedType`/`AnnotatedParameterizedType`.
2. `Field.isAnnotationPresent(NonNull.class)` trả về `false` trong ví dụ này, vì `@NonNull` chỉ đặt trên **type use**, không phải annotation được khai báo trên **field** với target `FIELD`. Đọc annotation trên kiểu cần API `Field.getAnnotatedType()`.
3. `@NonNull String title = null` vẫn **biên dịch**. `tags.add(null)` cũng **biên dịch và chạy** với `javac` Java 17 thông thường.
4. `Objects.requireNonNull(...)` mới là phép kiểm tra runtime trong ví dụ; nó ném `NullPointerException` khi gặp `null`. Annotation ở phía trên không tự gọi phương thức này.

**Kết luận về thí nghiệm:** tên annotation, target TYPE_USE và retention RUNTIME chỉ xác định nó được sử dụng/lưu trữ như thế nào. Tự thân các đặc điểm này không tạo ra quy tắc từ chối null cho Java compiler, cũng không tự chèn validation vào bytecode.

## 4. “Công cụ kiểm tra kiểu” (type checker) phải làm gì?

Một công cụ phân tích tĩnh hiểu annotation có thể **mở rộng phân tích kiểu thông thường** bằng khái niệm *qualifier* (thuộc tính gắn với kiểu). Ví dụ trong mô hình nullness:

```text
@NonNull String  : tham chiếu phải khác null theo hợp đồng checker
@Nullable String : tham chiếu có thể null theo hợp đồng checker
```

Tùy bộ quy tắc, công cụ có thể thiết lập một quan hệ gán như:

```text
Giá trị đảm bảo @NonNull
       |
       v
Nơi chấp nhận @Nullable         (thường hợp lệ)

Giá trị có thể @Nullable
       |
       x
Nơi yêu cầu @NonNull            (checker có thể báo lỗi)
```

Dấu `?` hay annotation cụ thể dùng để diễn đạt nullness phụ thuộc library và checker. Hai dòng trên mô tả **một hợp đồng thường gặp của nullness checker**, không phải quy tắc có sẵn của `javac` cho mọi annotation tên `NonNull` hoặc `Nullable`.

Để phát hiện vi phạm đáng tin cậy, công cụ thường cần:

- **Đọc qualifier ở đúng vị trí type use:** ví dụ annotation gắn vào phần tử của `List<...>` khác annotation gắn trên chính biến danh sách.
- **Kiểm tra phép gán và lời gọi phương thức:** một giá trị có thể null không được truyền tới tham số yêu cầu non-null nếu chưa kiểm tra.
- **Phân tích luồng dữ liệu (data-flow/flow-sensitive analysis):** sau `if (x != null)` hoặc `Objects.requireNonNull(x)`, checker có thể thu hẹp trạng thái nullness của `x` trong phạm vi mà nó chứng minh được.
- **Kiểm tra method contract:** annotation trên kiểu trả về, tham số, field và quan hệ override/implementation.
- **Phân tích generic, array, wildcard:** chẳng hạn `List<@NonNull String>` khác `@NonNull List<@Nullable String>`.
- **Chính sách mặc định và metadata từ thư viện:** xác định kiểu không gắn annotation được hiểu là “unknown”, “nullable”, “nonnull by default” hay một trạng thái khác.

Một công cụ **không tự nhiên làm được mọi mục trên chỉ nhờ việc annotation khai báo TYPE_USE**. Nó phải có mô hình kiểm tra, các rule, các API tích hợp với compiler/AST và cách phát cảnh báo/lỗi riêng.

## 5. Nhìn một đoạn code theo ba góc độ

Xét đoạn minh họa dưới đây, giả sử đã có khai báo `@NonNull` và `@Nullable` dùng được trên type use:

```java
class GreetingService {
    @Nullable String findName(boolean exists) {
        return exists ? "Alice" : null;
    }

    void greet(@NonNull String name) {
        System.out.println(name.toUpperCase());
    }

    void run() {
        @Nullable String candidate = findName(false);
        greet(candidate); // Có thể gây NullPointerException
    }
}
```

**Góc độ `javac` Java Core:** nếu các annotation hợp lệ về `@Target` và khai báo, compiler thông thường vẫn xem `candidate` là một tham chiếu có kiểu Java `String`; phép truyền nó vào tham số `String` của `greet` phù hợp hệ thống kiểu gốc. Không phải lỗi kiểu Java tiêu chuẩn.

**Góc độ checker chuyên nullness:** nếu tool hỗ trợ chính bộ qualifier đang dùng, nó có thể xác định `findName` trả về giá trị có khả năng null và báo lỗi khi truyền `candidate` vào tham số `@NonNull`. Công cụ cũng có thể chấp nhận nhánh được kiểm tra rõ ràng:

```java
@Nullable String candidate = findName(false);
if (candidate != null) {
    greet(candidate);
}
```

**Góc độ runtime:** nếu `candidate` thực sự null mà code gọi `name.toUpperCase()` thì `NullPointerException` vẫn xảy ra, bất kể annotation. Một phân tích tĩnh giúp phát hiện sớm trong phạm vi dữ liệu/đường đi mà nó hiểu được; nó không phải bảo đảm tuyệt đối cho reflection, native code, dữ liệu bên ngoài, hoặc những vị trí tool không phân tích.

Hai đoạn ở mục này **chỉ là minh họa quy tắc khi có checker tương thích**; không thể tự biên dịch độc lập nếu chưa định nghĩa `@Nullable` và `@NonNull`. Ví dụ hoàn chỉnh không cần công cụ ngoài đã ở mục 3.

## 6. @Target, @Retention và checker là ba trách nhiệm khác nhau

| Khái niệm | Định nghĩa | Java Core làm sẵn | Những gì không tự có |
|---|---|---|---|
| `@Target(TYPE_USE)` | Cho annotation xuất hiện tại vị trí sử dụng kiểu | Kiểm tra vị trí áp dụng | Không kiểm tra ý nghĩa “nonnull”, “trusted”, “positive” |
| `@Target(TYPE_PARAMETER)` | Cho xuất hiện ở khai báo type parameter | Kiểm tra vị trí khai báo | Không kiểm tra luật generic tăng cường |
| `@Retention(SOURCE)` | Giữ lần sử dụng annotation trong source lúc xử lý compile | Có thể được compiler/processor nhìn thấy khi compile source | Không còn lần sử dụng trong `.class` |
| `@Retention(CLASS)` | Giữ metadata trong binary khi vị trí áp dụng được lưu theo quy tắc JLS | Compiler lưu tương ứng | Java reflection chuẩn không tự nhìn thấy |
| `@Retention(RUNTIME)` | Lưu và cho phép reflection đọc tại vị trí API hỗ trợ | Runtime reflection có thể lấy metadata | Không tự chạy validation/kiểm tra null |
| **Type checker** | Xác định và áp dụng quy tắc trên các kiểu có qualifier | Chỉ tồn tại nếu có công cụ và cấu hình cụ thể | Không do `@interface` tự sinh |

Chọn retention tùy theo **thời điểm tiêu thụ metadata**:

- Nếu công cụ phân tích ngay khi compile source, một annotation SOURCE có thể đủ.
- Nếu tool phải phân tích các thư viện đã được biên dịch thành `.class`/JAR, có thể cần annotation được lưu vào class file (CLASS hoặc RUNTIME, nếu vị trí được giữ).
- Nếu ứng dụng muốn dùng reflection để xem type annotation ở runtime, cần RUNTIME và API `AnnotatedType` phù hợp.

Không phải cứ đặt `RUNTIME` là một checker sẽ tự chạy lúc runtime. Retention chỉ là hợp đồng lưu metadata. Checker hoạt động khi build/tooling được gọi; runtime validation phải có code thực thi riêng.

## 7. Annotation processor và type checker: có liên quan nhưng không đồng nghĩa

**Annotation processor** là một chương trình chạy trong quá trình biên dịch theo API `javax.annotation.processing`. Nó có thể đọc metadata, tạo source file và phát cảnh báo/lỗi bằng `Messager`. Tuy nhiên, một processor đơn giản quét annotation **không tự có khả năng phân tích tất cả phép gán, luồng dữ liệu hay quan hệ kiểu có qualifier**.

**Type checker chuyên dụng** có thể được triển khai qua compiler plugin, framework phân tích kiểu hoặc thành phần tích hợp build/IDE. Nó thường hiểu sâu hơn về biểu thức, kiểu, luồng điều khiển và generic.

Ví dụ một processor chỉ kiểm tra quy tắc khai báo: mọi field có tên kết thúc bằng `Id` phải dùng type annotation `@NotNullType`. Quy tắc này **chỉ kiểm tra sự hiện diện của annotation**, chưa chứng minh giá trị của field thực sự khác null. Thí nghiệm sau giúp thấy rõ trách nhiệm của công cụ.

### Thí nghiệm Java 17: processor tạo lỗi biên dịch theo quy tắc tùy chỉnh

Tạo bốn file trong cùng thư mục.

**File `NotNullType.java`:**

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE_USE)
public @interface NotNullType {}
```

**File `FieldRuleProcessor.java`:**

```java
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

@SupportedAnnotationTypes("*")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class FieldRuleProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations, RoundEnvironment round) {
        for (Element root : round.getRootElements()) {
            for (Element element : root.getEnclosedElements()) {
                if (element.getKind() == ElementKind.FIELD
                        && element.getSimpleName().toString().endsWith("Id")
                        && element.asType().getAnnotation(NotNullType.class) == null) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "Field ending in Id needs @NotNullType", element);
                }
            }
        }
        return false;
    }
}
```

Trong code processor, `element.asType()` cung cấp `TypeMirror` của field; `getAnnotation(NotNullType.class)` kiểm tra annotation **trên kiểu** của field. `Messager` báo lỗi tại khai báo field khi không đạt quy tắc đặt ra. Logic được cố tình giới hạn để học cơ chế; nó chưa phân tích giá trị gán hoặc phương thức.

**File `ValidOrder.java`:**

```java
class ValidOrder {
    @NotNullType String orderId = null;
}
```

**File `InvalidOrder.java`:**

```java
class InvalidOrder {
    String orderId = "123";
}
```

Biên dịch định nghĩa annotation và processor:

```bash
javac --release 17 NotNullType.java FieldRuleProcessor.java
```

Gọi processor có chủ đích cho từng input:

```bash
javac --release 17 -cp . -processorpath . -processor FieldRuleProcessor ValidOrder.java
javac --release 17 -cp . -processorpath . -processor FieldRuleProcessor InvalidOrder.java
```

- Với `ValidOrder.java`: compiler **thành công**, dù `orderId = null`. Processor chỉ xác minh type annotation có mặt, chưa kiểm tra giá trị.
- Với `InvalidOrder.java`: compiler **thất bại** vì processor phát `Diagnostic.Kind.ERROR`. Thông điệp trọng tâm:

```text
InvalidOrder.java:2: error: Field ending in Id needs @NotNullType
    String orderId = "123";
           ^
1 error
```

Chú ý: field của `InvalidOrder` thật sự đang có chuỗi không null, nhưng processor vẫn từ chối vì **quy tắc tên field và annotation** đã được lập trình như vậy. Điều này minh họa rằng loại lỗi bổ sung phụ thuộc chính xác vào những gì tool được viết để kiểm tra.

**Thí nghiệm không thể thay thế một nullness type checker.** Nullness checker thực sự cần kiểm tra các đường gán, giá trị, tham số, return, generic, flow và hợp đồng; chỉ nhìn thấy `@NotNullType` chưa đủ.

Một chi tiết workflow: cần chỉ định `-processor`/`-processorpath` (hoặc cấu hình processor qua build). Chỉ thêm dependency chứa annotation rồi mong tự có cảnh báo là chưa đủ. Những tên class/đường dẫn và cách kích hoạt processor có thể khác với build tool thực tế.

## 8. Kiểm tra TYPE_USE trên generic: ý nghĩa của vị trí annotation

Dùng qualifier trên kiểu của danh sách và phần tử để minh họa:

```java
List<@NonNull String> names;
@NonNull List<String> listReference;
@NonNull List<@NonNull String> both;
```

Đây là ba cấu hình metadata khác nhau:

| Ví dụ | Annotation đang nhắm đến | Điều checker có thể muốn áp đặt |
|---|---|---|
| `List<@NonNull String>` | `String` là type argument | Không phần tử nào trong list được null |
| `@NonNull List<String>` | Tham chiếu danh sách | Biến list không được null |
| `@NonNull List<@NonNull String>` | Cả tham chiếu list và các phần tử | Hai điều kiện trên đồng thời |

Giá trị metadata nằm ở những vị trí dùng kiểu khác nhau; vậy một checker thiết kế nghiêm túc phải biết tìm đúng vị trí. Java có API reflection như `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` để nhìn thấy type annotation trên type argument khi retention phù hợp, nhưng **có thể đọc được không có nghĩa tự ràng buộc được giá trị**.

Với generic method, return type, wildcard hoặc array, bài toán tiếp tục phức tạp: mỗi vị trí có qualifier riêng, suy diễn generic và biến đổi kiểu phải tôn trọng luật qualifier mà checker định nghĩa. Ví dụ nếu cho phép `List<@NonNull String>` chứa null thì hợp đồng đã thất bại ở runtime; nếu checker được cấu hình, nó phải phát hiện `add(null)` hoặc dữ liệu đến từ nguồn có thể null.

## 9. Lỗi thật của Java và lỗi do checker bổ sung: cần phân biệt trong log

Giả sử có ba trường hợp:

**Trường hợp A — lỗi kiểu Java chuẩn:**

```java
// Không biên dịch với Java thông thường:
int number = "forty-two";
```

Không cần annotation hay checker bổ sung để phát hiện.

**Trường hợp B — sai @Target:**

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;

@Target(ElementType.METHOD)
@interface OnlyMethod {}

class WrongPlacement {
    // Không biên dịch: OnlyMethod không dành cho TYPE_USE.
    // List<@OnlyMethod String> values;
}
```

Compiler kiểm tra vị trí áp dụng annotation, dù không hiểu một ngữ nghĩa nghiệp vụ nào của `OnlyMethod`.

**Trường hợp C — vi phạm quy ước được định nghĩa bởi checker:**

```java
class Person {
    @NonNull String nickname = null;
}
```

Nếu `@NonNull` là type-use annotation tự khai báo và chạy `javac` thuần, đây không phải lỗi từ hệ thống kiểu Java chuẩn. Nếu kích hoạt một checker **thực sự hiểu annotation đó** và quy tắc cấm null, nó có thể phát lỗi/warning. Mức độ nghiêm trọng do cấu hình công cụ quyết định: một dự án có thể đặt diagnostics thành lỗi khiến build thất bại, dự án khác xem chúng là cảnh báo.

Đừng xử lý mọi “annotation warning” bằng `@SuppressWarnings` một cách máy móc. Với tool khác nhau, khóa suppress và API điều chỉnh mức nghiêm trọng cũng khác; phải đọc hướng dẫn của checker hoặc build plugin thực tế.

## 10. Kiểm tra tĩnh và kiểm tra runtime bổ sung cho nhau

**Static type checking** tìm lỗi từ source/type information trước khi chạy, giúp giảm lỗi từ sớm. Nó mạnh khi phân tích được kiểu, gán dữ liệu và luồng điều khiển; có giới hạn khi dữ liệu đến từ reflection, hệ thống bên ngoài, dynamic proxy hoặc logic không thể chứng minh tại thời điểm biên dịch.

**Runtime validation** kiểm tra giá trị thật tại một thời điểm cụ thể:

```java
import java.util.Objects;

class AccountService {
    static String normalize(String name) {
        Objects.requireNonNull(name, "name");
        return name.trim();
    }
}
```

Ở đây `Objects.requireNonNull` thực sự kiểm tra `name` và ném exception nếu null. Nó hoạt động độc lập với annotation. Framework validation cũng chỉ chạy khi luồng xử lý **thật sự gọi** bộ validator/hook tương ứng.

Một dự án có thể kết hợp:

1. Qualifier/annotation để khai báo hợp đồng.
2. Type checker để phân tích hợp đồng ở compile time.
3. Guard/validation để bảo vệ biên tin cậy tại runtime.
4. Test để xác minh các trường hợp nghiệp vụ và tích hợp.

Không có lựa chọn nào tự động bảo đảm tuyệt đối cho mọi tình huống; phải hiểu **tool nào thực thi luật nào ở giai đoạn nào**.

## 11. Retention SOURCE, CLASS hay RUNTIME cho type checker?

`@Target(TYPE_USE)` và `@Retention` là hai trục độc lập. Ví dụ:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonNull {}

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE_USE)
@interface CompileTimeChecked {}
```

Annotation SOURCE có thể được compiler/processor quan sát trong lần compile source nhưng không được lưu vào biểu diễn binary. Annotation RUNTIME có thể truy vấn qua các API `AnnotatedType` phù hợp. Annotation CLASS có thể nằm trong class file nhưng không phải annotation visible của reflection runtime thông thường.

Nếu checker cần phân tích **library đã compile**, thiết kế qualifier và build cần cân nhắc khả năng giữ metadata trong binary hoặc cung cấp *stub/annotation specification* ngoài. Nếu checker chỉ chạy khi compile toàn bộ source, SOURCE có thể đủ. Các công cụ có hỗ trợ/đòi hỏi retention và metadata đầu vào khác nhau; hãy kiểm tra hợp đồng của checker cụ thể.

Không phải mọi compiler plugin, annotation processor hoặc static analyzer đều tự đọc được mọi thông tin generic qua reflection; runtime reflection không tương đương Java compiler model (Element/TypeMirror) và không cung cấp mọi chi tiết source/data flow.

## 12. Khi nào sử dụng một checker chuyên dụng?

Dùng checker khi dự án có loại lỗi lặp lại mà luật kiểm tra tĩnh có thể giúp phát hiện trước khi chạy, ví dụ:

- **Nullness:** dữ liệu có thể null truyền vào nơi yêu cầu non-null; điều kiện null-check chưa đủ.
- **Taint/trust:** input chưa được kiểm tra đi đến vị trí nhạy cảm; có thể biểu diễn “trusted/untrusted” bằng qualifier và bộ quy tắc tương ứng.
- **Đơn vị đo:** không dùng lẫn đơn vị hoặc đại lượng khác nhau, nếu hệ thống qualifier và checker được xây dựng đầy đủ.
- **Immutability/ownership:** giới hạn việc thay đổi hoặc chuyển giao dữ liệu theo những luật mà công cụ thực sự hỗ trợ.

Ví dụ về hệ sinh thái là **Checker Framework**, cung cấp cơ chế và các checker chuyên biệt dựa trên annotation. Điều này là tính năng của **thư viện/công cụ và cấu hình của nó**, không có nghĩa Java Core mặc định hiểu mọi annotation mang tên `NonNull`, `Nullable` hay `Untainted`. Một số IDE và analyzer cũng có kiểm tra nullness riêng. Khi chọn công cụ, cần thống nhất namespace annotation, cách cấu hình compiler và trạng thái của những library chưa được gắn qualifier.

Với ứng dụng nhỏ, có thể bắt đầu bằng kiểm tra null ở biên dữ liệu và giữ kiểu Java rõ ràng. Khi hợp đồng được tái sử dụng khắp dự án, qualifier kèm checker tương thích mới đem lại lợi ích rộng hơn.

## 13. Các lỗi hiểu nhầm thường gặp

**Lỗi 1 — Tự tạo @NonNull rồi nghĩ javac sẽ cấm null.**  
Không. `@interface NonNull` + `@Target(TYPE_USE)` chỉ khai báo metadata hợp lệ. Cần bộ kiểm tra bổ sung để có diagnostic về nullness.

**Lỗi 2 — Nghĩ RUNTIME retention đồng nghĩa validation tự chạy.**  
Không. RUNTIME chỉ giúp lưu/đọc annotation ở vị trí reflection hỗ trợ. Nếu không có code đọc và kiểm tra, không có hành vi validation nào.

**Lỗi 3 — Nhầm annotation trên field với annotation trên type của field.**  
`Field.getAnnotation(...)` hỏi annotation trên **khai báo field**; `Field.getAnnotatedType()` hỏi **type use** của field. Với qualifier chỉ target TYPE_USE, hai đường đọc này có thể cho kết quả khác nhau như ví dụ đầy đủ.

**Lỗi 4 — Nghĩ một processor đơn giản đồng nghĩa type checker toàn diện.**  
Processor trong mục 7 chỉ kiểm tra field được đánh dấu hay chưa. Nó còn chấp nhận `@NotNullType String orderId = null`. Phân tích nullness cần luật và data-flow riêng.

**Lỗi 5 — Chạy javac -Xlint:all rồi cho rằng mọi annotation đều được kiểm tra ngữ nghĩa.**  
`-Xlint:all` bật các nhóm warning mà `javac` hỗ trợ; nó **không tự kích hoạt mọi checker bên ngoài**. Build phải chạy đúng công cụ với cấu hình đúng.

**Lỗi 6 — Ghi @NonNull vào sai vị trí mảng hoặc generic.**  
Qualifier đặt trên phần tử của list khác qualifier của list. Với mảng cũng vậy: vị trí gắn trên kiểu phần tử/chiều mảng ảnh hưởng ý nghĩa theo checker. Hãy viết rõ hợp đồng mong muốn.

**Lỗi 7 — Trộn annotation từ nhiều thư viện.**  
Hai annotation đều tên `NonNull` nhưng ở package khác nhau không đương nhiên có cùng ý nghĩa hay được cùng checker hỗ trợ. Hãy biết chính xác tool đọc loại annotation nào.

**Lỗi 8 — Suppress cảnh báo quá rộng.**  
Suppress ở class lớn có thể che vi phạm mới, trong khi loại warning và suppression key tùy thuộc tool. Nếu có lý do bắt buộc, nên giới hạn phạm vi và ghi lý do, đồng thời giữ runtime guard ở chỗ dữ liệu bên ngoài cần được xác thực.

**Lỗi 9 — Thấy metadata runtime rồi nghĩ giá trị đã được bảo đảm.**  
`AnnotatedType` đọc được `@NonNull` không nói gì về giá trị thực sự đang lưu. Biểu diễn metadata và kiểm chứng dữ liệu là hai thao tác khác nhau.

## 14. Quy trình áp dụng annotation kiểm tra kiểu vào dự án

1. **Xác định lỗi muốn ngăn:** null dereference, trusted input, đơn vị đo, mutability... Hãy diễn đạt ràng buộc thành ví dụ hợp lệ/không hợp lệ.
2. **Chọn annotation và checker như một cặp:** xác minh checker thật sự hiểu qualifier, vị trí TYPE_USE cần thiết, generic/array và hành vi override.
3. **Tích hợp checker vào build/CI:** chạy trên đúng source set/module, có phiên bản compiler phù hợp; lỗi cần chặn release nên được xử lý ở cấp build.
4. **Quy định default:** kiểu thiếu annotation có ý nghĩa gì; quy tắc nào áp dụng cho code cũ và library bên ngoài.
5. **Viết ví dụ âm tính:** chẳng hạn `@NonNull String s = null` phải tạo diagnostic của checker; nếu build vẫn xanh thì công cụ chưa được kích hoạt hoặc chưa hiểu annotation.
6. **Xem xét runtime boundaries:** dữ liệu JSON, database, reflection, deserialization cần guard/validation phù hợp.
7. **Cập nhật hợp đồng khi thay đổi phiên bản:** JDK, checker, annotation dependency và IDE có thể thay đổi mức hỗ trợ; luôn kiểm thử bằng compiler/build thực tế của dự án.

Mức thành công đo bằng **lỗi cụ thể được phát hiện đúng** và **code hợp lệ vẫn được chấp nhận**, không đo bằng số lượng annotation được thêm.

## 15. Bài tập và câu hỏi kiểm tra

### Bài 1: Quy tắc Java Core

Cho:

```java
@Target(ElementType.TYPE_USE)
@interface NonNull {}

class Data {
    @NonNull String name = null;
}
```

Không thêm checker ngoài, `javac` Java 17 có bắt buộc báo lỗi ở dòng gán null không?

**Đáp án:** không. Annotation tự khai báo được dùng đúng vị trí; ngôn ngữ Java không có quy tắc kiểm tra nullness mặc định cho qualifier này.

### Bài 2: Hiểu đúng các vị trí

So sánh:

```java
List<@NonNull String> a;
@NonNull List<String> b;
```

Qualifier được gắn lên đâu?

**Đáp án:** `a` gắn qualifier lên type argument `String`; `b` gắn lên kiểu tham chiếu `List<String>`. Một checker hỗ trợ nullness có thể diễn giải hai ràng buộc khác nhau.

### Bài 3: Annotation processor đủ chưa?

Processor chỉ kiểm tra các field tên `...Id` phải có `@NotNullType`. Tại sao `@NotNullType String orderId = null` vẫn qua được?

**Đáp án:** processor chỉ kiểm tra *metadata hiện diện*, chưa đánh giá giá trị initializer hay luồng dữ liệu. Cần bổ sung bộ quy tắc phân tích nếu thật sự muốn cấm null.

### Bài 4: Mức retention

Nếu cần đọc type annotation từ `Field.getAnnotatedType()` trong chương trình đang chạy thì retention nào phù hợp?

**Đáp án:** `RUNTIME`. Với SOURCE hoặc CLASS, runtime reflection thông thường không cung cấp lần sử dụng annotation.

### Bài 5: @Target sai

Nếu một annotation chỉ có `@Target(ElementType.METHOD)` mà đem đặt vào `List<@OnlyMethod String>`, javac có được phép báo lỗi không?

**Đáp án:** có, vì vị trí dùng annotation không hợp lệ. Đây là luật vị trí của Java, không cần checker ngữ nghĩa riêng.

### Bài 6: Tiêu chí chứng minh checker hoạt động

Làm thế nào biết kiểm tra nullness đã thực sự được bật trong CI?

**Đáp án:** tạo một kiểm thử build có chủ ý dùng giá trị có thể null ở vị trí `@NonNull`; xác minh bước compiler/checker đưa ra diagnostic được thiết kế và build thất bại nếu vi phạm nghiêm trọng. Một cú pháp annotation hợp lệ và một lần compile xanh chưa đủ bằng chứng.

## Tài liệu tham khảo

- [Java Language Specification 17 `4.11 — Where Types Are Used](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.11): vị trí sử dụng kiểu trong Java.
- [JLS 17 `9.6.4.1 — @Target](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.1): TYPE_USE, TYPE_PARAMETER và giới hạn áp dụng.
- [JLS 17 `9.7.4 — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4): type annotations và annotation trên khai báo.
- [Java SE 17 API — AnnotatedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html): cách đọc metadata type use ở runtime.
- [Java SE 17 API — AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html): đọc annotation ở type argument của generic type.
- [Java SE 17 API — TypeMirror](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html): mô hình kiểu cho compile-time processors.
- [Java SE 17 API — AbstractProcessor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): cơ chế xử lý annotation compile time.
- [Checker Framework](https://checkerframework.org/): ví dụ hệ sinh thái tool hỗ trợ annotation-based type checking với các qualifier/rule do công cụ định nghĩa.
