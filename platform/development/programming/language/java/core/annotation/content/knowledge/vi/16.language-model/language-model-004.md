# AnnotationMirror và AnnotationValue trong mô hình ngôn ngữ Java

Trong **annotation processing** theo chuẩn JSR 269, compiler cho phép chương trình phân tích cấu trúc Java **ngay khi biên dịch**: lớp, phương thức, trường, tham số, kiểu và các annotation gắn trên chúng. Hai API nền tảng để làm việc với metadata annotation là:

- **`javax.lang.model.element.AnnotationMirror`**: biểu diễn **một lần sử dụng annotation** trong mô hình ngôn ngữ của compiler, bao gồm kiểu annotation và ánh xạ từ các phần tử của annotation tới giá trị.
- **`javax.lang.model.element.AnnotationValue`**: biểu diễn **một giá trị của phần tử annotation**, chẳng hạn `3`, `"checkout"`, `String.class`, enum constant, annotation lồng hoặc mảng các annotation values.

Chúng không phải hai kiểu dùng để đọc metadata bằng Java Reflection khi chương trình nghiệp vụ chạy. `AnnotationMirror` và `AnnotationValue` phục vụ **mô hình ngôn ngữ compile-time**, thường được xử lý trong `AbstractProcessor.process(...)` bằng những đối tượng `Element`, `TypeMirror`, `Elements` và `RoundEnvironment`.

Điểm phân biệt then chốt: với annotation có giá trị mặc định, `AnnotationMirror.getElementValues()` chỉ trả những phần tử **được ghi tường minh tại nơi gắn annotation**; muốn nhận đủ cả mặc định, dùng **`Elements.getElementValuesWithDefaults(mirror)`**.

## 1. Vì sao compiler cần một mô hình thay cho Reflection?

Giả sử đang biên dịch:

```java
@Review(value = "checkout", retries = 3)
class CheckoutService {}
```

Một annotation processor có thể cần biết:

- `CheckoutService` có annotation `Review` nào?
- `Review` là **loại annotation** nào trong mã đang biên dịch?
- Tại lần sử dụng này, phần tử `value` được đặt thành gì?
- `retries` có giá trị gì? Nó được viết tường minh hay dùng default?
- Nếu một phần tử trả về `Class<?>` nhưng kiểu Java đang biên dịch chưa thể tải bằng `ClassLoader`, làm sao phân tích nó?
- Nếu annotation chứa enum, annotation lồng hoặc mảng, compiler biểu diễn các giá trị đó ra sao?

Reflection chủ yếu làm việc trên những lớp đã được biên dịch/nạp vào JVM, với những annotation có retention `RUNTIME`. Annotation processor, ngược lại, cần phân tích cả **mã nguồn đang được compiler xử lý**, kể cả annotation có retention `SOURCE`.

Đó là lý do API `javax.lang.model` dùng một hệ thống **mô hình ngôn ngữ** thay vì cố lấy các `Class<?>`, `Method` hay proxy annotation runtime từ lớp nghiệp vụ chưa hoàn thành biên dịch.

| Nhu cầu | API phù hợp |
| --- | --- |
| Phân tích annotation khi javac đang biên dịch | `Element.getAnnotationMirrors()`, `AnnotationMirror`, `AnnotationValue` |
| Đọc giá trị mặc định trong mô hình compiler | `Elements.getElementValuesWithDefaults(...)` |
| Kiểm tra kiểu trong source hiện tại | `TypeMirror`, `Types`, `TypeElement` |
| Đọc annotation của class đã nạp khi chương trình chạy | Java Reflection như `Class.getAnnotation(...)` |
| Đọc annotation có retention `CLASS` từ `.class` sau compile | Trình đọc class file/bytecode, không phải Java Reflection chuẩn |

Một annotation processor không “chạy mã của annotation”; nó đọc metadata và thực hiện logic riêng như xác thực quy ước, in lỗi compiler hoặc sinh file.

## 2. AnnotationMirror đại diện cho cái gì?

Ví dụ khai báo và sử dụng:

```java
@interface Review {
    String value();
    int retries() default 2;
}

@Review("checkout")
class CheckoutService {}
```

Trong compiler, đối tượng `TypeElement` của `CheckoutService` có thể cung cấp:

```java
List<? extends AnnotationMirror> mirrors =
        checkoutElement.getAnnotationMirrors();
```

Đây là snippet nằm trong annotation processor, giả sử biến `checkoutElement` là một `Element` thích hợp và đã import `java.util.List` cùng `javax.lang.model.element.AnnotationMirror`.

Mỗi `AnnotationMirror` mô tả **một annotation trên một phần tử theo mô hình compiler**. API quan trọng:

```java
DeclaredType annotationType = mirror.getAnnotationType();

Map<? extends ExecutableElement, ? extends AnnotationValue> explicit =
        mirror.getElementValues();
```

- `getAnnotationType()` trả `DeclaredType` biểu diễn **kiểu annotation** được sử dụng. Có thể dùng `annotationType.asElement()` để lấy `TypeElement` của annotation type.
- `getElementValues()` trả một `Map` mà **key** là `ExecutableElement` đại diện cho phương thức phần tử như `value()` hoặc `retries()`, **value** là `AnnotationValue` tương ứng.
- Với `@Review("checkout")`, map này chỉ có khóa cho `value`; phần tử `retries` **không xuất hiện** vì nơi dùng annotation không viết nó.

Tại sao key không phải `String`? Vì compiler lưu quan hệ trực tiếp tới **khai báo method element** trong annotation type. Muốn hiển thị tên có thể gọi `entry.getKey().getSimpleName()`, còn muốn kiểm tra chính xác method element có thể làm việc với API của `ExecutableElement`.

`AnnotationMirror` không tương đương đối tượng proxy của `@Review` lúc chạy. Gọi `getAnnotationType()` không trả Java `Class<Review>`, và `getElementValues()` không phải `Map<String,Object>`.

## 3. AnnotationValue đại diện cho kiểu dữ liệu nào?

`AnnotationValue` mô tả từng giá trị hợp lệ của một phần tử annotation, nhưng không ép mọi giá trị vào một kiểu Java runtime đơn giản. Nó có:

```java
Object raw = annotationValue.getValue();
```

`getValue()` trả `Object` bởi các giá trị có nhiều dạng. Cần xem **kiểu thực tế của đối tượng theo hợp đồng của `javax.lang.model`**:

| Loại phần tử annotation | Dạng của `AnnotationValue.getValue()` trong language model | Cách hiểu |
| --- | --- | --- |
| Primitive `boolean`, `byte`, `short`, `int`, `long`, `float`, `double`, `char` | Wrapper tương ứng như `Boolean`, `Integer`, `Character` | Giá trị hằng đã được biểu diễn |
| `String` | `String` | Chuỗi giá trị |
| `Class` hoặc `Class<?>` | **`TypeMirror`** | Mô hình kiểu Java, **không phải `Class<?>`** |
| Enum | **`VariableElement`** | Phần tử enum constant, không phải runtime enum instance |
| Annotation lồng | **`AnnotationMirror`** | Một annotation value chứa metadata annotation khác |
| Mảng một chiều | **`List<? extends AnnotationValue>`** | Danh sách các phần tử annotation value, không phải Java array bình thường |

**Hai lỗi dễ gặp nhất:**

1. Ép phần tử `Class<?> handler()` thành `Class<?>` bằng `((Class<?>) annotationValue.getValue())` là sai: đối tượng mà model trả về là **`TypeMirror`**.
2. Với `String[] labels()`, `getValue()` **không** trả `String[]`, mà trả `List` các `AnnotationValue`; phải truy cập từng element value.

Các giá trị kiểu `enum` cũng không phải enum object đã được load. Compiler dùng `VariableElement` để tham chiếu **enum constant trong mô hình source/type**.

### 3.1. Dữ liệu lồng nhau

Ví dụ:

```java
@interface Tag {
    String value();
}

@interface Review {
    Tag tag();
    String[] labels();
}
```

Khi dùng:

```java
@Review(tag = @Tag("public"), labels = {"api", "payment"})
class Endpoint {}
```

thì:

- `Review` được biểu diễn bằng một `AnnotationMirror`.
- Giá trị của `tag` là một `AnnotationValue` có `getValue()` là **`AnnotationMirror`** của `@Tag("public")`.
- Giá trị của `labels` là một `AnnotationValue` có `getValue()` là **danh sách hai `AnnotationValue`**, mỗi giá trị con bọc một `String`.

Muốn đọc giá trị sâu bên trong annotation lồng, cần đọc **mirror của annotation lồng** tiếp, không ép nó thành instance `Tag` để gọi `tag.value()`.

## 4. Lấy giá trị được ghi tường minh và giá trị mặc định

Xét:

```java
@interface Review {
    String value();
    int retries() default 2;
    String[] labels() default {"core"};
}

@Review("checkout")
class CheckoutService {}
```

Tại đây:

```java
Map<? extends ExecutableElement, ? extends AnnotationValue> explicit =
        mirror.getElementValues();
```

chỉ gồm phần tử `value` với `"checkout"`. Phần tử `retries` và `labels` có default, nhưng tại chỗ sử dụng annotation chúng **không được viết ra**.

Khi cần **giá trị cuối cùng theo khai báo annotation**, gọi:

```java
Map<? extends ExecutableElement, ? extends AnnotationValue> all =
        processingEnv.getElementUtils()
                     .getElementValuesWithDefaults(mirror);
```

Lúc này map có các phần tử:

| Phần tử | `getElementValues()` | `getElementValuesWithDefaults()` |
| --- | --- | --- |
| `value` | `"checkout"` | `"checkout"` |
| `retries` | Không có entry | `2` |
| `labels` | Không có entry | `{"core"}` biểu diễn theo model |

Hãy phân biệt **vắng entry** và **giá trị null**. Annotation element không nhận `null` làm giá trị hợp lệ; vắng entry trong `getElementValues()` thường có nghĩa tại nơi dùng annotation không ghi một giá trị tường minh cho element đó. Không nên coi nó là “đã được ghi `null`”.

Nếu muốn biết giá trị mặc định trên **chính định nghĩa** của một element, `ExecutableElement` còn có:

```java
AnnotationValue defaultValue = methodElement.getDefaultValue();
```

Giá trị này có thể là `null` nếu khai báo annotation element **không có default**. Đây là `null` từ **API biểu thị thiếu default**, không phải giá trị annotation `null` do người dùng ghi.

**Hai nhu cầu khác nhau:**

- `getElementValuesWithDefaults(mirror)`: đọc **lần sử dụng annotation cụ thể**, bao gồm mặc định mà nó thừa hưởng.
- `ExecutableElement.getDefaultValue()`: đọc **định nghĩa annotation element**, có hoặc không có default.

Mọi cách đọc phải xét đúng annotation mirror, nhất là khi processor xử lý nhiều annotation type.

## 5. Duyệt giá trị bằng AnnotationValueVisitor

Bạn có thể dùng `instanceof` sau `getValue()`, nhưng khi cần code mở rộng hoặc hỗ trợ đủ kiểu giá trị, Java cung cấp:

```java
<R, P> R AnnotationValue.accept(AnnotationValueVisitor<R, P> visitor, P p)
```

Visitor có các thao tác chuyên biệt:

- `visitBoolean`, `visitByte`, `visitShort`, `visitInt`, `visitLong`, `visitChar`, `visitFloat`, `visitDouble`;
- `visitString`;
- `visitType(TypeMirror, ...)` cho class literals;
- `visitEnumConstant(VariableElement, ...)` cho enum;
- `visitAnnotation(AnnotationMirror, ...)` cho nested annotation;
- `visitArray(List<? extends AnnotationValue>, ...)` cho mảng.

Một visitor tránh việc phân tán những phép ép kiểu dễ sai khắp code. Lớp hỗ trợ `SimpleAnnotationValueVisitor9<R,P>` (Java 9+) cho phép ghi đè các nhánh cần thiết và kế thừa cách xử lý mặc định cho phần còn lại. Java 17 dùng được class này.

**Lưu ý tên phương thức `visitType`:** nó trả dữ liệu về **`TypeMirror`**, không yêu cầu `Class<?>` tương ứng phải load được ở JVM đang chạy processor. Đây là khác biệt thiết yếu khi phân tích source code.

Đoạn dưới là một nhánh minh họa, dùng bên trong lớp visitor:

```java
@Override
public String visitType(TypeMirror type, Void unused) {
    return "type:" + type;
}
```

Muốn giải quyết các kiểu phức tạp hơn (generic, array, error type…), có thể dùng thêm `Types`, `TypeKind` và các subtype của `TypeMirror` theo nhu cầu, thay vì tin rằng `toString()` luôn là định danh ổn định để so sánh.

## 6. Ví dụ Java 17+: một annotation processor thực sự đọc Mirror và Value

Phần này tạo **bốn file** ở cùng thư mục, không dùng framework ngoài JDK:

```text
Review.java
ReviewProcessor.java
CheckoutService.java
DefaultService.java
```

Ví dụ chạy trong hai bước: biên dịch annotation type và processor, sau đó dùng processor đó để biên dịch các lớp được đánh dấu.

### 6.1. Review.java — định nghĩa metadata nhiều loại giá trị

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface Review {
    String value();
    int retries() default 2;
    Class<?> handler() default Runnable.class;
    Priority priority() default Priority.NORMAL;
    Tag tag() default @Tag("stable");
    String[] labels() default {"core"};
}

enum Priority {
    NORMAL, HIGH
}

@interface Tag {
    String value();
}
```

Trong `Review`, compiler có thể gặp:

- `String` (`value`);
- `int` (`retries`);
- `Class<?>` (`handler`);
- `enum` (`priority`);
- nested annotation `Tag` (`tag`);
- mảng `String[]` (`labels`).

`@Retention(SOURCE)` cố ý minh họa rằng annotation processor vẫn nhìn thấy annotation trên source khi compile, dù Java Reflection runtime không thể đọc lần sử dụng này. Retention không buộc phải là `RUNTIME` để annotation processing hoạt động.

`Tag` có default retention `CLASS` vì không khai báo riêng; trong ví dụ này nó được dùng như annotation value lồng. Điều quyết định để processor làm việc là annotation value có sẵn trong **mô hình compile-time** của `Review`.

### 6.2. ReviewProcessor.java — lấy AnnotationMirror và đọc AnnotationValue

```java
import java.util.*;
import javax.annotation.processing.*;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.*;
import javax.lang.model.type.TypeMirror;
import javax.lang.model.util.SimpleAnnotationValueVisitor9;

@SupportedAnnotationTypes("Review")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class ReviewProcessor extends AbstractProcessor {
    static class ValueText
            extends SimpleAnnotationValueVisitor9<String, Void> {

        @Override
        public String visitString(String s, Void ignored) {
            return "string:" + s;
        }

        @Override
        public String visitInt(int n, Void ignored) {
            return "int:" + n;
        }

        @Override
        public String visitType(TypeMirror type, Void ignored) {
            return "type:" + type;
        }

        @Override
        public String visitEnumConstant(VariableElement constant, Void ignored) {
            return "enum:" + constant.getSimpleName();
        }

        @Override
        public String visitAnnotation(AnnotationMirror a, Void ignored) {
            return "annotation:" + a.getAnnotationType();
        }

        @Override
        public String visitArray(
                List<? extends AnnotationValue> values, Void ignored) {
            List<String> rendered = new ArrayList<>();
            for (AnnotationValue value : values) {
                rendered.add(value.accept(this, null));
            }
            return "array:" + rendered;
        }
    }

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return false;
        }

        TypeElement review =
                processingEnv.getElementUtils().getTypeElement("Review");
        if (review == null) {
            return false;
        }

        for (Element element : roundEnv.getElementsAnnotatedWith(review)) {
            for (AnnotationMirror mirror : element.getAnnotationMirrors()) {
                if (!mirror.getAnnotationType().asElement().equals(review)) {
                    continue;
                }

                System.out.println("element=" + element.getSimpleName());
                System.out.println("annotationType="
                        + mirror.getAnnotationType());
                System.out.println("explicit=" + names(mirror.getElementValues()));

                Map<? extends ExecutableElement,
                    ? extends AnnotationValue> all =
                    processingEnv.getElementUtils()
                                 .getElementValuesWithDefaults(mirror);

                ValueText visitor = new ValueText();
                all.entrySet().stream()
                    .sorted(Comparator.comparing(
                        e -> e.getKey().getSimpleName().toString()))
                    .forEach(e -> System.out.println(
                        e.getKey().getSimpleName() + "="
                        + e.getValue().accept(visitor, null)));
            }
        }
        return false;
    }

    private static String names(
            Map<? extends ExecutableElement,
                ? extends AnnotationValue> values) {

        return values.keySet().stream()
                .map(e -> e.getSimpleName().toString())
                .sorted()
                .toList()
                .toString();
    }
}
```

Điểm chính trong processor:

1. `@SupportedAnnotationTypes("Review")` yêu cầu xử lý annotation type có tên `Review`. Ví dụ sử dụng **package mặc định** để dễ biên dịch bằng lệnh ở bên dưới; trong dự án thật nên đặt annotation vào package có tên và dùng tên fully qualified tương ứng.
2. `@SupportedSourceVersion(SourceVersion.RELEASE_17)` tuyên bố phiên bản source mà processor hỗ trợ trong ví dụ. Các lệnh biên dịch dùng `--release 17` để tương thích.
3. `roundEnv.getElementsAnnotatedWith(review)` tìm các `Element` được đánh `@Review` trong vòng xử lý hiện tại.
4. `element.getAnnotationMirrors()` trả metadata annotation của phần tử. Mã lọc bằng `mirror.getAnnotationType().asElement()` để chọn **đúng loại `Review`**, tránh trộn các annotation khác.
5. `mirror.getElementValues()` dùng để hiển thị **tên những element được viết tường minh**.
6. `getElementValuesWithDefaults(mirror)` dùng để có đủ các giá trị kể cả những element không xuất hiện trong source nơi sử dụng.
7. `ValueText` giải mã các kiểu `String`, `int`, `Class` (`TypeMirror`), enum (`VariableElement`), annotation lồng (`AnnotationMirror`) và array (`List<AnnotationValue>`).
8. Mã sắp xếp theo tên element trước khi in để output có thứ tự xác định. **Thứ tự `Map` trả về không nên được dùng làm hợp đồng hiển thị**.

Lớp `ValueText` chỉ là một visitor trình bày để phục vụ bài học. Khi viết processor production, bạn thường muốn **trả dữ liệu có kiểu rõ ràng** và dùng `Messager.printMessage(Diagnostic.Kind.ERROR, ..., element)` để báo lỗi compiler thay vì `System.out.println`. `System.out` ở đây nhằm làm ví dụ dễ tái lập và so stdout.

Giá trị `Tag` lồng được visitor trình bày thành `annotation:Tag`; ví dụ này **chưa in ra `Tag.value()`**, nhưng có thể đi sâu vào `AnnotationMirror` lồng để làm việc đó bằng cùng cơ chế `getElementValuesWithDefaults`.

### 6.3. CheckoutService.java — ghi tất cả giá trị

```java
@Review(
    value = "checkout",
    retries = 3,
    handler = String.class,
    priority = Priority.HIGH,
    tag = @Tag("public"),
    labels = {"api", "payment"}
)
class CheckoutService {}
```

Ở lần sử dụng này, **sáu phần tử** đều có giá trị tường minh: `value`, `retries`, `handler`, `priority`, `tag` và `labels`.

### 6.4. DefaultService.java — chỉ ghi giá trị bắt buộc

```java
@Review("default")
class DefaultService {}
```

Ở đây chỉ có `value` được ghi tường minh. Các phần tử khác lấy default từ định nghĩa annotation type.

### 6.5. Lệnh biên dịch và chạy processor

Từ thư mục chứa bốn file, tạo thư mục output:

```bash
mkdir out
```

**Bước 1.** Biên dịch annotation type và processor:

```bash
javac --release 17 -d out Review.java ReviewProcessor.java
```

**Bước 2.** Biên dịch hai lớp có `@Review` và **chỉ định processor tường minh**:

```bash
javac --release 17 -cp out -processorpath out -processor ReviewProcessor -d out CheckoutService.java DefaultService.java
```

Ở bước 2:

- `-cp out` giúp compiler tìm `Review`, `Priority` và `Tag` đã biên dịch.
- `-processorpath out` làm `ReviewProcessor` có thể được tìm thấy tại đường dẫn processor.
- `-processor ReviewProcessor` chỉ định processor cần chạy. Ví dụ **không** dựa vào tự phát hiện processor qua `META-INF/services`.
- `-d out` chỉ định nơi lưu các file `.class` sinh ra.
- Không cần chạy `java CheckoutService`: chúng là lớp được phân tích trong lúc **javac** chạy, không phải ứng dụng có `main`.

**Output của bước 2:**

```text
element=CheckoutService
annotationType=Review
explicit=[handler, labels, priority, retries, tag, value]
handler=type:java.lang.String
labels=array:[string:api, string:payment]
priority=enum:HIGH
retries=int:3
tag=annotation:Tag
value=string:checkout
element=DefaultService
annotationType=Review
explicit=[value]
handler=type:java.lang.Runnable
labels=array:[string:core]
priority=enum:NORMAL
retries=int:2
tag=annotation:Tag
value=string:default
```

Ví dụ đã được thử bằng `javac --release 17` trên JDK mới hơn, qua **hai bước biên dịch** tương ứng, và kết quả in trùng khớp khối output trên.

**Đừng nhầm:** đây là console output do `System.out.println` trong `ReviewProcessor.process` phát ra **khi javac đang biên dịch**. Nó không phải stdout của `CheckoutService` khi chạy, cũng không chứng minh annotation được giữ ở runtime. `@Retention(SOURCE)` phù hợp với ví dụ.

## 7. Phân tích từng AnnotationValue từ kết quả

### 7.1. String và primitive

```text
value=string:checkout
retries=int:3
```

`value` là giá trị `String`. `retries` là `int` bọc bởi `AnnotationValue`; `visitInt` nhận `int`. Với các primitive khác, visitor có phương thức riêng tương ứng, ví dụ `visitBoolean`, `visitChar`, `visitLong`.

Một annotation element kiểu `int` có thể nhận một constant expression như `1 + 2`; mô hình giá trị hiển thị **giá trị tính được** chứ không nhất thiết giữ nguyên cú pháp source ban đầu. Đừng sử dụng `AnnotationValue.toString()` để khôi phục nguyên vẹn mã người dùng viết.

### 7.2. Class literal trở thành TypeMirror

```text
handler=type:java.lang.String
```

Trong source có `handler = String.class`. Compiler trả `TypeMirror` khi visitor xử lý `handler`, chứ không trả `String.class` dưới dạng `java.lang.Class`.

Tương tự, default `Runnable.class` cho output `type:java.lang.Runnable`. `TypeMirror` cho phép phân tích **kiểu đang được biên dịch**, kể cả kiểu dự án và kiểu phức tạp, mà không phải nạp Java class thực tế.

Trong công cụ production, khi cần so kiểu, nên dùng `Types.isSameType(...)`, `Types.isSubtype(...)` hoặc truy cập `TypeElement` thích hợp, thay vì chỉ so chuỗi `type.toString()`.

### 7.3. Enum constant trở thành VariableElement

```text
priority=enum:HIGH
```

Trong source có `Priority.HIGH`. Visitor nhận `VariableElement` đại diện cho enum constant và lấy `getSimpleName()` để hiển thị `HIGH`.

Nếu trong processor cần biết enum type, có thể xem enclosing element hoặc mô hình kiểu của constant; không được giả định `AnnotationValue.getValue()` là một object `Priority.HIGH` trong runtime processor.

### 7.4. Annotation lồng trở thành AnnotationMirror

```text
tag=annotation:Tag
```

Tại source có `tag = @Tag("public")`. Visitor nhìn thấy **`AnnotationMirror`** cho `Tag`.

Nếu cần `"public"`, duyệt giá trị của mirror lồng:

```java
@Override
public String visitAnnotation(AnnotationMirror nested, Void ignored) {
    Map<? extends ExecutableElement, ? extends AnnotationValue> entries =
            processingEnv.getElementUtils()
                         .getElementValuesWithDefaults(nested);

    for (var entry : entries.entrySet()) {
        if (entry.getKey().getSimpleName().contentEquals("value")) {
            return "tag:" + entry.getValue().getValue();
        }
    }
    return "tag:(missing)";
}
```

Đây là snippet **để thay thế nhánh `visitAnnotation` trong processor**, không phải một chương trình hoàn chỉnh độc lập. Mã chỉ minh họa một annotation `Tag` cụ thể; code tổng quát nên có cách xử lý mọi element của nested annotation, kiểu dữ liệu và diagnostics nếu cấu trúc không như mong đợi.

### 7.5. Mảng trở thành List các AnnotationValue

```text
labels=array:[string:api, string:payment]
```

`labels` được khai báo `String[]`. Visitor `visitArray` nhận `List<? extends AnnotationValue>` và dùng `value.accept(this, null)` để xử lý **từng giá trị thành phần**, giữ thứ tự.

Đối với `Class<?>[]`, mỗi phần tử con sẽ được xử lý bởi `visitType`; đối với mảng annotation lồng, mỗi phần tử con đi qua `visitAnnotation`. Không ép cả `getValue()` thành `String[]`, `Class<?>[]` hoặc `Tag[]`.

## 8. Nên dùng getValue(), toString() hay visitor?

Ba cách xử lý thường gặp:

**Cách 1 — `getValue()` rồi phân nhánh theo kiểu:** phù hợp logic nhỏ, biết trước phần tử đang đọc, và có kiểm tra đầy đủ trường hợp `TypeMirror`/`VariableElement`/`AnnotationMirror`/`List`.

**Cách 2 — `AnnotationValue.toString()`:** tiện cho hiển thị nhanh khi debug, nhưng **không phải hợp đồng phục hồi source code hoặc serialize dữ liệu ổn định**. Biểu diễn văn bản có thể chứa dấu nháy, dạng tên kiểu và thông tin tùy trường hợp. Không nên dùng chuỗi `toString()` làm chuẩn kiểm tra kiểu.

**Cách 3 — `AnnotationValue.accept(visitor, p)`:** thường dễ mở rộng hơn nếu phải xử lý nhiều loại phần tử; visitor có phương thức riêng cho từng dạng giá trị và hỗ trợ nhánh mảng/nested annotation.

Ví dụ mã xử lý `Class` đúng:

```java
Object raw = value.getValue();
if (raw instanceof TypeMirror typeMirror) {
    // typeMirror thuộc hệ thống mô hình kiểu, không phải Class<?>.
    System.out.println(typeMirror);
}
```

Đoạn này là snippet trong processor với biến `value` kiểu `AnnotationValue`, cần import `TypeMirror`.

Không viết:

```java
// Sai với annotation value chứa Class literal:
Class<?> clazz = (Class<?>) value.getValue();
```

Lý do: trong language model, class literal dùng `TypeMirror`. Đây là khác biệt bản chất với trường hợp một annotation runtime proxy có phương thức kiểu `Class<?>`.

## 9. AnnotationMirror và TypeMirror khác gì nhau?

Tên giống nhau nhưng đối tượng mô tả khác nhau.

| Loại | Biểu diễn | Ví dụ |
| --- | --- | --- |
| `Element` | Một phần tử Java được khai báo: class, method, field, parameter… | `TypeElement` cho `CheckoutService` |
| `TypeMirror` | **Một kiểu Java** theo mô hình compiler | kiểu `java.lang.String`, `List<String>` |
| `AnnotationMirror` | **Một lần sử dụng annotation** | `@Review(value = "checkout", ...)` |
| `AnnotationValue` | **Giá trị của một element annotation** | `"checkout"`, `3`, `String.class` theo dạng model |
| `ExecutableElement` | Một phần tử thực thi/khai báo phương thức trong model | `Review.retries()` |

`AnnotationMirror.getAnnotationType()` trả **`DeclaredType`**, một dạng của `TypeMirror` biểu diễn **kiểu annotation**. Nhưng cả `AnnotationMirror` không phải `TypeMirror`: một bên là **lần dùng metadata**, một bên là **kiểu**.

Với class literal trong annotation, chính **`AnnotationValue.getValue()` trả `TypeMirror`**. Với nested annotation, **`AnnotationValue.getValue()` trả `AnnotationMirror`**. Hai trường hợp này cần phân biệt khi viết visitor tổng quát.

## 10. Annotation processing theo vòng (round) và nguồn nào được đọc?

Một `AbstractProcessor` tham gia các processing rounds của javac. Trong mỗi round, compiler cung cấp `RoundEnvironment` và tập annotation types mà processor có thể xử lý.

Ví dụ:

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {

    if (roundEnv.processingOver()) {
        return false;
    }

    // Đọc các phần tử được gắn annotation trong round hiện tại.
    return false;
}
```

`roundEnv.getElementsAnnotatedWith(type)` tìm các phần tử được gắn annotation theo các quy tắc của annotation processing trong round đó. Khi processor sinh thêm source, compiler có thể xử lý những source mới ở round tiếp theo.

Vì thế:

- Không nên giả định `process` chỉ được gọi **một lần**.
- Không nên sinh cùng một file nhiều lần mà không quản lý trạng thái và các vòng xử lý.
- Trong processor production, dùng `processingEnv.getMessager().printMessage(...)` để phát diagnostic có vị trí gắn với `Element` hoặc `AnnotationMirror` khi cần.
- Chỉ định `@SupportedAnnotationTypes` và `@SupportedSourceVersion` đúng với annotation/module/source level được hỗ trợ.
- Giá trị trả về `true` của `process` có ý nghĩa **claim** các annotation types được xử lý; không có nghĩa giá trị annotation là boolean hay processor chạy thành công/thất bại. Ví dụ trả `false` để không claim chúng.

**Một lưu ý về Retention:** annotation có retention `SOURCE` vẫn có thể được đọc khi processor làm việc với source. Nhưng compiler không giữ nó vào `.class` để Reflection runtime tìm thấy. Không chọn retention `RUNTIME` chỉ vì nghĩ rằng annotation processor bắt buộc phải dùng Reflection.

## 11. Annotation được lặp (repeatable) và AnnotationMirror

Với:

```java
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@interface Tags {
    Tag[] value();
}

@Tag("a")
@Tag("b")
class Sample {}
```

Compiler có quy tắc biểu diễn các annotation lặp qua **container annotation**. Khi dùng mô hình compile-time:

- `Element.getAnnotationMirrors()` trả danh sách annotation mirrors theo hợp đồng của language model. Với repeated annotations, cách các annotation hiện diện trong mirror list liên quan tới quy tắc **container**; không tự giả định luôn có hai `AnnotationMirror` top-level riêng biệt cho hai `@Tag`.
- Một `AnnotationMirror` cho container `Tags` có phần tử `value()` với `AnnotationValue` chứa **danh sách `AnnotationValue`**, mỗi phần tử có thể chứa một `AnnotationMirror` cho từng `@Tag`.
- Một công cụ tổng quát muốn đọc mọi `Tag` phải xem xét cả annotation trực tiếp và annotation container thích hợp, hoặc dùng API theo loại phù hợp khi được hỗ trợ và khi ngữ nghĩa đáp ứng yêu cầu.

Không đơn giản ép kết quả `getAnnotationMirrors()` sang mảng các annotation runtime proxy, và đừng giả định `getValue()` cho mảng container là `Tag[]` Java runtime.

Nếu cần thứ tự, giữ thứ tự từ các `AnnotationValue` trong mảng container. Nếu cần hỗ trợ kế thừa `@Inherited`, phân biệt ngữ nghĩa tra cứu của model compile-time với các API Reflection runtime và kiểm chứng theo hợp đồng cụ thể.

## 12. Phân biệt API model getAnnotation(...) với Java Reflection

`Element` còn có các phương thức tiện lợi `getAnnotation(Class<A>)` và `getAnnotationsByType(Class<A>)`. Chúng thuộc `AnnotatedConstruct` trong language-model API và **không có nghĩa** annotation processor nên phụ thuộc vào Reflection runtime của lớp đang được biên dịch.

Khi annotation type có element kiểu `Class<?>`, dùng proxy annotation từ các API tiện lợi này có thể dẫn tới **`MirroredTypeException`** (hoặc các ngoại lệ liên quan tới type mirrors). Lý do là đối tượng `Class` của kiểu được nhắc tới trong source có thể chưa được load hoặc không thích hợp để biểu diễn bằng runtime class trong processor.

Trong ví dụ chính:

```java
@Review(handler = String.class, value = "checkout")
class CheckoutService {}
```

Nếu processor định gọi các accessor từ annotation proxy theo cách giống runtime, nó có thể phải xử lý vấn đề class literal được biểu diễn bằng type mirror. Cách làm vững chắc là đọc:

```java
AnnotationMirror mirror = ...;       // Mirror của @Review
AnnotationValue handlerValue = ...;  // Value của element handler()
TypeMirror handlerType =
        (TypeMirror) handlerValue.getValue();
```

Đây là snippet, không phải file độc lập; thực tế cần chọn `handlerValue` từ map element values của mirror, đồng thời kiểm tra đúng kiểu trước khi ép.

**Quy tắc thiết kế:** khi xử lý source hoặc cần so sánh kiểu Java đang biên dịch, ưu tiên dữ liệu `javax.lang.model` (`Element`/`TypeMirror`/`AnnotationMirror`) hơn là buộc lớp nghiệp vụ đã tồn tại dưới dạng runtime `Class<?>`.

## 13. Những lỗi phổ biến

**“`AnnotationMirror` là `java.lang.annotation.Annotation`.”** Sai. Nó là mô hình compile-time của **một lần sử dụng annotation**, không phải instance annotation proxy runtime.

**“`AnnotationValue.getValue()` trả đúng Java value type của element mọi lúc.”** Sai với `Class`, enum, nested annotation và array; các trường hợp này lần lượt dùng `TypeMirror`, `VariableElement`, `AnnotationMirror` và `List<? extends AnnotationValue>`.

**“`mirror.getElementValues()` luôn chứa cả element có default.”** Sai. Nó chỉ chứa các element đã viết tường minh. Dùng `getElementValuesWithDefaults` nếu cần kết quả đầy đủ.

**“Element thiếu trong map nghĩa là default bằng `null`.”** Sai. Trong ngôn ngữ Java, annotation element không có giá trị `null` hợp lệ. Trạng thái thiếu là **không ghi tường minh**; đọc default thông qua API phù hợp.

**“`Class<?>` trong annotation có thể ép trực tiếp từ getValue().”** Sai. Language model dùng `TypeMirror`.

**“Enum constant là runtime enum object.”** Sai. Language model trả `VariableElement`.

**“Mảng trả `String[]` hoặc `AnnotationMirror[]`.”** Sai. `AnnotationValue` của mảng trả danh sách các **`AnnotationValue`**.

**“Processor chỉ chạy nếu annotation được giữ đến `RUNTIME`.”** Sai. Processor có thể xử lý annotation trên source có retention `SOURCE`.

**“`getAnnotationMirrors()` là cách đọc file .class qua Reflection.”** Sai. Nó là API model của compiler; công cụ bytecode reader và Reflection là hai cơ chế khác.

**“AnnotationValue.toString() khôi phục chính xác chuỗi người dùng gõ.”** Sai. Mô hình giá trị có thể làm mất khác biệt giữa `1 + 2` và `3`, hoặc các chi tiết cú pháp/định dạng của source.

**“Process trả false tức processor thất bại.”** Sai. Boolean này liên quan đến việc claim annotation types trong processing pipeline.

## 14. Bài tập tự kiểm tra

### Bài 1 — Hai loại map khác nhau

Cho `@Review("default")` và khai báo `Review` ở mục 6, dự đoán:

- Những key nào có trong `mirror.getElementValues()`?
- Những key nào xuất hiện sau `getElementValuesWithDefaults(mirror)`?

**Đáp án:** map thứ nhất chỉ có `value`. Map thứ hai chứa `value`, `retries`, `handler`, `priority`, `tag`, `labels`.

### Bài 2 — Class literal

Với `@Review(handler = String.class, value = "checkout")`, `AnnotationValue.getValue()` của `handler` có thể ép thành `Class<?>` hay không?

**Đáp án:** không. Nó trả `TypeMirror` đại diện cho `java.lang.String` trong mô hình compiler.

### Bài 3 — Enum và annotation lồng

Tại sao visitor dùng `visitEnumConstant(VariableElement, ...)` cho `Priority.HIGH` và `visitAnnotation(AnnotationMirror, ...)` cho `@Tag("public")`?

**Đáp án:** enum constant là một phần tử được khai báo của kiểu enum; annotation lồng là một lần sử dụng annotation riêng, có kiểu và các element values riêng. Cả hai không phải object instance nghiệp vụ được tạo bởi source code.

### Bài 4 — Mảng

Với `labels = {"api", "payment"}`, `AnnotationValue.getValue()` của `labels` trả dạng nào?

**Đáp án:** `List<? extends AnnotationValue>` có hai phần tử; mỗi phần tử con trả chuỗi tương ứng khi `getValue()` hoặc qua `visitString`.

### Bài 5 — SOURCE retention

Tại sao `ReviewProcessor` có thể đọc `@Review` dù `Review` được khai báo `@Retention(SOURCE)`?

**Đáp án:** processor chạy **khi compiler phân tích source**. Retention `SOURCE` chỉ quy định dữ liệu này không cần được giữ trong class file đầu ra, không xóa nó khỏi source model khi đang biên dịch.

### Bài 6 — Nested annotation value

Muốn lấy chuỗi `"public"` bên trong `tag = @Tag("public")`, bạn cần thao tác với `AnnotationMirror` của `Tag` như thế nào?

**Đáp án:** dùng các API đọc element values của nested `AnnotationMirror`, tìm phần tử `value()`, rồi lấy `AnnotationValue` tương ứng và giải mã string.

### Bài 7 — Lỗi khi đọc Class bằng proxy

Tại sao processor không nên viết logic dựa vào việc gọi `Review review = element.getAnnotation(Review.class); Class<?> c = review.handler();` như một runtime Reflection API thông thường?

**Đáp án:** các kiểu được nhắc đến trong source có thể chưa load; language-model proxy accessor của `Class` có thể ném `MirroredTypeException`. Dùng `AnnotationMirror` và `TypeMirror` để xử lý độc lập với class loading.

### Bài 8 — Build thật

Hãy biên dịch bốn file ở mục 6. Vì sao cần `-processorpath out` và `-processor ReviewProcessor` trong lệnh thứ hai?

**Đáp án:** để javac tìm và gọi processor đã biên dịch ở bước 1. Không cần đóng gói `META-INF/services` khi processor được chỉ định tường minh.

## 15. Checklist áp dụng vào annotation processor

1. **Đọc từ compiler model:** đã có đúng `Element` được đánh annotation chưa?
2. **Chọn đúng annotation type:** đã kiểm tra `mirror.getAnnotationType()` chưa?
3. **Phân biệt explicit và default:** muốn chỉ những gì source viết hay muốn kết quả kèm mặc định?
4. **Chọn cách duyệt value:** có cần hỗ trợ đủ primitive, `String`, class literal, enum, nested annotation và array không?
5. **Tránh ép kiểu runtime sai:** dùng `TypeMirror`, `VariableElement`, `AnnotationMirror`, `List<AnnotationValue>` đúng nơi.
6. **Annotation lồng và mảng:** nếu cần dữ liệu sâu, đã duyệt đệ quy và giữ thứ tự chưa?
7. **Không phụ thuộc việc load class nghiệp vụ:** hạn chế dùng `Class<?>` để biểu diễn các kiểu đang được compiler phân tích.
8. **Xử lý rounds:** có kiểm tra `processingOver()` và tránh tạo trùng file không?
9. **Kiểm tra phiên bản source:** processor đã khai báo và được biên dịch với source level phù hợp chưa?
10. **Dùng diagnostic phù hợp:** khi phát hiện cấu hình sai, đã báo lỗi gắn với `Element` thay vì chỉ in console chưa?
11. **Chạy thử đủ ca:** annotation viết đầy đủ, annotation dùng defaults, mảng rỗng, class literal, enum và nested annotation?
12. **Đọc lại output javac:** xác minh đúng thông tin explicit và giá trị default, không suy luận từ `toString()`?

**Kết luận:** `AnnotationMirror` mô tả **một lần dùng annotation trong mô hình biên dịch**, còn `AnnotationValue` mô tả **từng giá trị được gắn vào các phần tử annotation**. `getElementValues()` cho dữ liệu ghi tường minh; `getElementValuesWithDefaults()` bổ sung giá trị mặc định. Nhờ `TypeMirror`, `VariableElement`, nested `AnnotationMirror` và visitor cho `AnnotationValue`, processor có thể phân tích metadata Java một cách đúng kiểu **ngay khi javac đang làm việc**, không cần biến source code chưa hoàn thành thành các class runtime để dùng Reflection.