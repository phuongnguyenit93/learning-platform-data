# Đọc giá trị phần tử và giá trị mặc định của annotation

## 1. Hai câu hỏi khác nhau

Giả sử annotation quy định số lần thử lại. Một nơi sử dụng bỏ qua thuộc tính đó để dùng mặc định; nơi khác chỉ định giá trị riêng. Khi đọc lúc chạy, cần phân biệt:

- **Giá trị của annotation cụ thể:** lần sử dụng này có số lần thử lại là bao nhiêu?
- **Mặc định của kiểu annotation:** nếu bỏ qua phần tử này, quy tắc khai báo cung cấp giá trị nào?

Java biểu diễn phần tử annotation bằng phương thức không tham số. Gọi phương thức trên annotation trả giá trị của lần sử dụng; gọi `Method.getDefaultValue()` trên phương thức khai báo phần tử trả mặc định. Hai thao tác không thay thế nhau. [API Method.getDefaultValue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html#getDefaultValue())

Bài dùng Java 17 trở lên và annotation có retention `RUNTIME` để đọc các lần sử dụng bằng reflection.

## 2. Phần tử bắt buộc, phần tử có mặc định

Đoạn khai báo minh họa:

```java
@interface RetryRule {
    String value();
    int attempts() default 3;
}
```

`value` không có mặc định, nên một lần sử dụng phải cung cấp nó. `attempts` có mặc định 3, nên được bỏ qua. Cú pháp `@RetryRule("payment")` là cách viết ngắn cho `@RetryRule(value = "payment")`; cú pháp viết ngắn không tự làm `value` trở thành tùy chọn.

Giá trị phần tử không được là `null`. Các kiểu hợp lệ gồm kiểu nguyên thủy, `String`, `Class`, enum, annotation và mảng một chiều của các kiểu đó; không dùng `List<String>` hay mảng hai chiều làm kiểu phần tử. [JLS §9.6.1 và §9.7.1](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.1)

Từ khóa `default` trong khai báo phần tử annotation quy định một giá trị, không tạo phương thức interface có thân mặc định.

## 3. Đọc giá trị bằng API đã định kiểu

Lưu toàn bộ chương trình sau vào **AnnotationValuesDemo.java**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

public class AnnotationValuesDemo {
    public enum Mode {
        SAFE, FAST
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target({})
    public @interface Window {
        int seconds();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    public @interface Pipeline {
        String value();
        int retries() default 3;
        Mode mode() default Mode.SAFE;
        String[] labels() default {"general"};
        Class<?> handler() default String.class;
        Window window() default @Window(seconds = 30);
    }

    @Pipeline("basic")
    static class Basic {
    }

    @Pipeline(
        value = "detailed",
        retries = 5,
        mode = Mode.FAST,
        labels = {"orders", "daily"},
        handler = Integer.class,
        window = @Window(seconds = 10)
    )
    static class Detailed {
    }

    @Pipeline(value = "explicit", retries = 3)
    static class ExplicitDefault {
    }

    static class Unmarked {
    }

    public static void main(String[] args) {
        show(Basic.class);
        show(Detailed.class);
        show(ExplicitDefault.class);
        show(Unmarked.class);

        Pipeline basic =
                Basic.class.getDeclaredAnnotation(Pipeline.class);
        Pipeline explicit =
                ExplicitDefault.class.getDeclaredAnnotation(
                        Pipeline.class);
        System.out.println("sameRetries="
                + (basic.retries() == explicit.retries()));
    }

    private static void show(Class<?> type) {
        Pipeline pipeline =
                type.getDeclaredAnnotation(Pipeline.class);

        if (pipeline == null) {
            System.out.println(type.getSimpleName() + ": no-annotation");
            return;
        }

        System.out.println(type.getSimpleName()
                + ": value=" + pipeline.value()
                + ", retries=" + pipeline.retries()
                + ", mode=" + pipeline.mode().name()
                + ", labels=" + Arrays.toString(pipeline.labels())
                + ", handler=" + pipeline.handler().getSimpleName()
                + ", seconds=" + pipeline.window().seconds());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 AnnotationValuesDemo.java
java AnnotationValuesDemo
```

Kết quả:

```text
Basic: value=basic, retries=3, mode=SAFE, labels=[general], handler=String, seconds=30
Detailed: value=detailed, retries=5, mode=FAST, labels=[orders, daily], handler=Integer, seconds=10
ExplicitDefault: value=explicit, retries=3, mode=SAFE, labels=[general], handler=String, seconds=30
Unmarked: no-annotation
sameRetries=true
```

Các cách đọc trong ví dụ:

| Phần tử | Kiểu trả về | Cách sử dụng |
| --- | --- | --- |
| `value()` | `String` | Đọc trực tiếp chuỗi |
| `retries()` | `int` | Đọc trực tiếp số |
| `mode()` | `Mode` | Làm việc với enum, không phân tích chuỗi annotation |
| `labels()` | `String[]` | Duyệt mảng hoặc dùng `Arrays.toString` để trình bày |
| `handler()` | `Class<?>` | Nhận đối tượng mô tả lớp |
| `window()` | `Window` | Đọc tiếp phần tử của annotation lồng |

`Basic` bỏ qua các phần tử có mặc định. `Detailed` chỉ định giá trị riêng. `ExplicitDefault` viết `retries = 3` nhưng có cùng giá trị đọc được với `Basic`.

`Unmarked` không có annotation: `getDeclaredAnnotation` trả `null`, chứ không tạo một annotation mới chỉ vì kiểu `Pipeline` có các giá trị mặc định. [API AnnotatedElement](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)

### Annotation mặc định không tự thực thi nghiệp vụ

`retries=3` chỉ là dữ liệu. Nó không tự làm chương trình thử lại ba lần; tương tự, `handler=String.class` không tự tạo đối tượng `String`. Mã xử lý phải đọc thông tin rồi thực hiện hành vi tương ứng.

## 4. Đọc mặc định từ khai báo phần tử

Để hỏi mặc định của `retries`, cần lấy phương thức trên **kiểu annotation**, không phải tìm một phương thức cùng tên trên lớp được gắn annotation:

```java
Method element =
        AnnotationValuesDemo.Pipeline.class.getDeclaredMethod("retries");
Object defaultValue = element.getDefaultValue();
```

Đoạn này cần `import java.lang.reflect.Method;` và tệp chương trình trước; đây chưa phải một chương trình độc lập.

`getDefaultValue()` trả `Object`. Với phần tử nguyên thủy, kết quả được đóng gói bằng kiểu bao tương ứng: `int` thành `Integer`. Nếu phần tử không có mặc định, kết quả là `null`; gọi trên phương thức thông thường không phải phần tử annotation cũng trả `null`. [Hợp đồng getDefaultValue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html#getDefaultValue())

### Chương trình đối chiếu giá trị sử dụng và mặc định

Tạo **AnnotationDefaultInspector.java** cạnh `AnnotationValuesDemo.java`:

```java
import java.lang.annotation.Annotation;
import java.lang.reflect.Array;
import java.lang.reflect.Method;
import java.util.StringJoiner;

public class AnnotationDefaultInspector {
    public static void main(String[] args) throws Exception {
        Annotation annotation =
                AnnotationValuesDemo.Detailed.class
                    .getDeclaredAnnotation(
                        AnnotationValuesDemo.Pipeline.class);

        if (annotation == null) {
            throw new IllegalStateException("Pipeline is required");
        }

        Class<? extends Annotation> annotationType =
                annotation.annotationType();

        String[] names = {
            "value", "retries", "mode", "labels", "handler"
        };

        for (String name : names) {
            Method element = annotationType.getDeclaredMethod(name);
            Object actual = element.invoke(annotation);
            Object declaredDefault = element.getDefaultValue();

            System.out.println(name
                    + ": actual=" + format(actual)
                    + ", default=" + format(declaredDefault));
        }

        Object retriesDefault =
                annotationType.getDeclaredMethod("retries")
                    .getDefaultValue();
        System.out.println("retriesDefaultType="
                + retriesDefault.getClass().getSimpleName());
    }

    private static String format(Object value) {
        if (value == null) {
            return "<no-default>";
        }

        if (value instanceof Class<?> type) {
            return type.getTypeName();
        }

        if (value instanceof Enum<?> constant) {
            return constant.name();
        }

        if (value.getClass().isArray()) {
            StringJoiner items = new StringJoiner(", ", "[", "]");
            for (int i = 0; i < Array.getLength(value); i++) {
                items.add(format(Array.get(value, i)));
            }
            return items.toString();
        }

        return String.valueOf(value);
    }
}
```

Chạy:

```shell
javac --release 17 -encoding UTF-8 AnnotationValuesDemo.java AnnotationDefaultInspector.java
java AnnotationDefaultInspector
```

Kết quả:

```text
value: actual=detailed, default=<no-default>
retries: actual=5, default=3
mode: actual=FAST, default=SAFE
labels: actual=[orders, daily], default=[general]
handler: actual=java.lang.Integer, default=java.lang.String
retriesDefaultType=Integer
```

Ở đây:

- `element.invoke(annotation)` đọc giá trị trên annotation của lớp `Detailed`.
- `element.getDefaultValue()` đọc giá trị mặc định của phần tử trong `Pipeline`.
- `value` bắt buộc nên không có mặc định, dù annotation cụ thể có giá trị `"detailed"`.
- Phần tử `window` được đọc theo kiểu xác định trong chương trình đầu; ví dụ kiểm tra tổng quát thứ hai chủ động chỉ xét năm phần tử trong mảng `names`.

Dùng `annotation.annotationType()` để lấy đúng kiểu annotation. `annotation.getClass()` có thể là một lớp triển khai phụ thuộc môi trường, không phải kiểu khai báo `Pipeline`. [API Annotation.annotationType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Annotation.html#annotationType())

Hàm `format` dùng `Array.getLength/get` nên xử lý được cả mảng kiểu tham chiếu và mảng nguyên thủy. Không ép mọi mảng thành `Object[]`: một `int[]` không phải `Object[]`. [API Array](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Array.html)

## 5. Ba trường hợp dễ bị nhầm

| Tình huống | Kết quả |
| --- | --- |
| Lớp không có annotation cần tìm | API tìm annotation có thể trả `null` |
| Annotation có phần tử không khai báo mặc định | `Method.getDefaultValue()` của phần tử trả `null` |
| Annotation có mặc định nhưng lần sử dụng chỉ định giá trị riêng | Đọc annotation trả giá trị riêng; đọc mặc định vẫn trả mặc định khai báo |

Hai giá trị `null` ở hai dòng đầu thuộc **hai câu hỏi khác nhau**. Phải kiểm tra annotation có tồn tại trước khi gọi các phương thức của nó. Với phần tử đã biết có mặc định, vẫn nên xác thực kiểu trước khi ép kiểu trong mã công cụ tổng quát.

### Có biết người viết đã bỏ qua phần tử không?

Không thể kết luận chỉ bằng cách so sánh giá trị đọc được với mặc định. Trong ví dụ, `Basic` bỏ qua `retries`, còn `ExplicitDefault` viết rõ `retries = 3`; cả hai đều đọc ra 3.

API reflection đọc giá trị phần tử không cung cấp cờ “đã viết rõ trong mã nguồn”. Nếu một công cụ thực sự cần phân biệt xuất xứ giá trị, nó phải dùng nguồn thông tin khác phù hợp; đừng gán nhãn “người dùng đã bỏ qua” chỉ vì hai giá trị bằng nhau.

Với phần tử mảng, cũng không dùng `==` để so nội dung. `Arrays.equals` với overload phù hợp so các phần tử; `==` chỉ so hai tham chiếu mảng. Các annotation trả về qua reflection là bất biến: việc sửa mảng nhận được không phải cách cập nhật annotation đang gắn trên lớp. [Hợp đồng AnnotatedElement](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)

## 6. Đổi mặc định có thể làm thay đổi hành vi của bên sử dụng

Mặc định được áp dụng khi annotation được đọc; nó không được sao chép vào từng lần sử dụng không chỉ định phần tử ấy. Vì vậy, thay mặc định có thể ảnh hưởng cả lớp đã được biên dịch trước đó nếu lớp đó bỏ qua phần tử tương ứng. [JLS §9.6.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.2)

Ví dụ với một bản phát hành mới thay `retries` từ 3 thành 4:

- Lần sử dụng bỏ qua `retries` có thể đọc ra 4 khi chạy với định nghĩa annotation mới.
- Lần sử dụng đã ghi rõ `retries = 3` vẫn cung cấp 3.
- `getDefaultValue()` trên định nghĩa annotation mới trả 4.

Đây là tác động tương thích hành vi, dù mã ứng dụng không sửa. Khi chọn mặc định cho annotation cấu hình, hãy xem nó như một phần hợp đồng của API; khi thay đổi, cần kiểm thử những bên tiêu thụ phụ thuộc giá trị đó. Không suy luận rằng chương trình đang chạy tự nạp lại một tệp class vừa sửa; ví dụ nói về việc chạy với phiên bản định nghĩa annotation mới.

## 7. Cách viết mã đọc đáng tin

Nếu đã biết kiểu annotation, ưu tiên lời gọi đã định kiểu như `pipeline.retries()`: dễ đọc và được trình biên dịch kiểm tra. Chỉ dùng `Method.invoke` khi cần một công cụ tổng quát.

Khi viết bộ đọc tổng quát:

1. Xác nhận lấy được annotation.
2. Lấy kiểu bằng `annotationType()`.
3. Lấy phương thức khai báo phần tử, rồi đọc giá trị thực và mặc định theo hai đường riêng.
4. Xử lý kiểu trả về, nhất là mảng, enum, `Class` và annotation lồng.
5. Nếu tự duyệt `getDeclaredMethods()`, đặt quy tắc thứ tự rõ ràng để đầu ra ổn định; chương trình trong bài dùng mảng tên cố định.
6. Giữ thông tin lớp, kiểu annotation và tên phần tử khi báo lỗi.

Các thuộc tính kiểu `Class` hoặc enum còn phụ thuộc kiểu/hằng tồn tại lúc chạy. Nếu môi trường thư viện không tương thích, việc đọc phần tử có thể gặp lỗi như `TypeNotPresentException`, `EnumConstantNotPresentException` hoặc `IncompleteAnnotationException`; không coi mọi lỗi đọc là “annotation không tồn tại”. Khi gọi qua `Method.invoke`, lỗi do phương thức được gọi ném ra có thể được bọc trong `InvocationTargetException`. [API AnnotatedElement](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedElement.html), [API Method.invoke](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...))

Đừng phân tích `annotation.toString()` để lấy cấu hình: cách trình bày phụ thuộc triển khai. Hãy sử dụng phương thức phần tử và kiểu dữ liệu đã khai báo. [API Annotation](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Annotation.html)

### Tự thực hành

1. Bỏ `value = "detailed"` khỏi annotation trên `Detailed`. Vì sao chương trình không biên dịch, dù các phần tử khác đều có mặc định?
2. Đổi mặc định `retries` thành 4 rồi biên dịch lại hai chương trình. Dòng của `Basic`, `ExplicitDefault` và kết quả `getDefaultValue()` khác nhau thế nào?
3. Đặt `labels = {}` cho `Detailed`. Phân biệt mảng rỗng được chỉ định với việc bỏ qua `labels` để nhận `{"general"}`.
4. Thêm phần tử `int[] priorities() default {1, 2};`, đưa `"priorities"` vào mảng `names` của bộ đọc. Vì sao hàm trình bày hiện tại vẫn đọc được mà không ép sang `Object[]`?
5. Thử thay `getDefaultValue()` bằng `invoke(annotation)` trong cột mặc định. Vì sao kết quả đó không còn trả lời đúng câu hỏi về mặc định khai báo?
