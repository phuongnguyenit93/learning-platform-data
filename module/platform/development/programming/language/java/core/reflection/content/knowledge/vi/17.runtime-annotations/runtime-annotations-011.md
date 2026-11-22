# `equals`, `hashCode` và `annotationType` của annotation trong Java

## 1. Ba phương thức trả lời ba câu hỏi khác nhau

Khi Reflection đọc một annotation ở runtime, kết quả không chỉ là vài trường metadata; nó là một **đối tượng thực thi giao diện annotation**. Mọi annotation interface đều ngầm mở rộng `java.lang.annotation.Annotation`, nên đối tượng thu được có ba phương thức trọng tâm:

| Phương thức | Câu hỏi cần trả lời | Ý nghĩa |
| --- | --- | --- |
| `annotationType()` | “Annotation này được khai báo bởi **annotation interface** nào?” | Trả `Class<? extends Annotation>` của loại annotation, chẳng hạn `Info.class` |
| `equals(Object other)` | “Hai annotation có **cùng loại và cùng giá trị các thành viên** không?” | So sánh theo **giá trị ngữ nghĩa**, không theo địa chỉ đối tượng |
| `hashCode()` | “Giá trị băm tương thích với quy tắc `equals` của annotation là gì?” | Được đặc tả bằng công thức trên tất cả thành viên, kể cả thành viên dùng giá trị mặc định |

Ví dụ:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Info {
    String name();
    int level() default 1;
}
~~~

Đây là đoạn khai báo minh họa, cần import `java.lang.annotation.*`. Một annotation `@Info(name = "core")` sẽ có **hai thành viên** trong hợp đồng so sánh: `name = "core"` và `level = 1`. Việc không ghi rõ `level` trong mã nguồn **không xóa thành viên này** khỏi `equals` hoặc `hashCode`.

Tại runtime, thông thường lấy annotation qua các API của `AnnotatedElement`:

~~~java
Info info = SomeClass.class.getAnnotation(Info.class);
if (info != null) {
    System.out.println(info.annotationType() == Info.class);
}
~~~

Đoạn minh họa trên giả định có lớp `SomeClass` và annotation `@Info` giữ lại đến runtime. `getAnnotation` trả `null` nếu không tìm thấy annotation phù hợp; đừng gọi `equals`, `hashCode` hoặc `annotationType` trước khi xử lý trường hợp ấy.

## 2. `annotationType()` khác `getClass()` như thế nào?

Một annotation runtime thường được JDK hiện thực bằng **đối tượng của lớp implementation do runtime tạo**, chứ không phải instance có lớp triển khai trùng với annotation interface.

- `info.annotationType()` trả đúng **`Info.class`**.
- `info.getClass()` trả **lớp implementation runtime**, có thể là lớp proxy/implementation phụ thuộc JDK. Không nên đặt kỳ vọng vào tên package, tên class hoặc định dạng implementation của nó.
- `info.annotationType() == Info.class` là cách kiểm tra annotation interface đang được biểu diễn.
- `info.getClass() == Info.class` không phải phép kiểm tra đúng loại annotation: `Info` là một interface, không phải implementation class của object.

Sử dụng `Class<? extends Annotation>` cho kiểu annotation tổng quát:

~~~java
Annotation any = element.getAnnotation(Info.class);
if (any != null) {
    Class<? extends Annotation> kind = any.annotationType();
    System.out.println(kind == Info.class);
}
~~~

Đây là đoạn minh họa bên trong phương thức có `AnnotatedElement element` và `Info` phù hợp. Không dùng `getClass()` làm khóa định danh loại annotation khi xây framework quét metadata.

**Phân biệt thêm:** `annotationType()` **không** trả lớp nơi annotation được đặt. Nếu `@Info` nằm trên `Service`, `annotationType()` vẫn là `Info.class`, **không** phải `Service.class`. Muốn biết đối tượng được gắn annotation, bạn phải giữ riêng tham chiếu `AnnotatedElement` tương ứng.

## 3. Hợp đồng `equals`: bằng nhau khi nào?

Javadoc `java.lang.annotation.Annotation` quy định hai annotation bằng nhau nếu và chỉ nếu:

1. Đối tượng đem so sánh biểu diễn **cùng một annotation interface**.
2. **Tất cả các thành viên tương ứng đều có giá trị bằng nhau** theo quy tắc dành cho từng kiểu.

Không yêu cầu hai annotation phải nằm trên cùng class, cùng field hoặc cùng method. Không yêu cầu hai giá trị được viết giống hệt nhau trong mã nguồn nếu chúng mang cùng giá trị sau khi áp dụng default.

### 3.1. Giá trị mặc định cũng tham gia so sánh

~~~java
@Info(name = "core")
class A { }

@Info(name = "core", level = 1)
class B { }
~~~

Giả sử `Info.level()` có `default 1` như ở mục 1. Annotation của `A` và `B` **bằng nhau** theo `equals` vì giá trị tất cả thành viên giống nhau. Khi gọi `level()` từ annotation của `A`, API trả 1.

Điều này khác với việc so sánh nguyên văn source code: `@Info(name = "core")` và `@Info(name = "core", level = 1)` không giống hệt về cách viết, nhưng có **giá trị annotation tương đương**.

### 3.2. So sánh từng kiểu thành viên

| Kiểu thành viên | Quy tắc `equals` của annotation |
| --- | --- |
| Primitive `boolean`, `byte`, `short`, `char`, `int`, `long` | So theo giá trị bằng toán tử `==` |
| `float`, `double` | Theo `Float.valueOf(x).equals(Float.valueOf(y))` hoặc `Double.valueOf(x).equals(Double.valueOf(y))` |
| `String`, `Class`, enum | Dùng `equals` của giá trị tương ứng |
| Annotation lồng trong annotation | So sánh `equals` **đệ quy** |
| Mảng một chiều của các kiểu được phép | Dùng overload thích hợp của `Arrays.equals` |

Cần chú ý **điểm đặc biệt của số thực**: theo hợp đồng annotation, `NaN` được coi là bằng chính nó, còn `+0.0` và `-0.0` được phân biệt khi so sánh thành viên kiểu `float`/`double`. Quy tắc này khác với cách dùng toán tử số học `==` thông thường trong Java.

### 3.3. Array member so **nội dung**, không so identity

Nếu annotation có thành viên:

~~~java
int[] ids() default {1, 2};
~~~

thì `ids = {1, 2}` bằng `ids = {1, 2}` dù các mảng được tạo ở những lần truy cập khác nhau. Nhưng `{1, 2}` **không bằng** `{2, 1}`, vì `Arrays.equals` so sánh **theo thứ tự phần tử**.

Không dùng `array1 == array2` hay `array1.equals(array2)` để tự mô phỏng hợp đồng annotation: cả hai cách ấy chỉ so tham chiếu mảng. Với `int[]`, nên dùng `Arrays.equals(int[], int[])`; với mảng reference hợp lệ, dùng overload `Arrays.equals(Object[], Object[])`. Hợp đồng annotation chọn overload tương ứng tự động.

Đặc biệt, annotation member **không thể là một array nhiều chiều**; tập kiểu hợp lệ được giới hạn trong primitive, `String`, `Class`, enum, annotation interface và mảng một chiều của các kiểu ấy. Giá trị member không thể là `null`.

### 3.4. Cùng tên các thành viên chưa đủ

Hai annotation interfaces khác nhau:

~~~java
@interface Alpha { String value(); }
@interface Beta  { String value(); }
~~~

dù đều được sử dụng dưới dạng `@Alpha("x")` và `@Beta("x")`, **không bằng nhau**. `annotationType()` khác nhau, nên điều kiện thứ nhất của `equals` thất bại. Tên member hay nội dung giống hệt cũng không biến hai loại annotation khác nhau thành một.

## 4. Hợp đồng `hashCode` của annotation

`Annotation.hashCode()` **không phải** mã băm identity của đối tượng proxy. Nó được định nghĩa theo tổng giá trị băm của **mọi thành viên annotation**, bao gồm member dùng default.

Với thành viên tên `n` và giá trị `v`:

~~~text
memberHash = (127 * n.hashCode()) XOR valueHash(v)

annotationHash = tổng memberHash trên tất cả thành viên
~~~

- `n.hashCode()` là `String.hashCode()` của **tên member**, ví dụ `"name"`, không phải tên annotation interface.
- Với primitive, `valueHash(v)` là `hashCode()` của wrapper tương ứng: `Integer`, `Boolean`, `Float`, `Double`, ...
- Với `String`, `Class`, enum, hoặc annotation lồng, dùng `v.hashCode()` (annotation lồng lại tính theo cùng hợp đồng).
- Với array member, dùng overload tương ứng của `Arrays.hashCode`; **không dùng `Object.hashCode` của mảng**.
- Tổng số học trong Java dùng số nguyên `int`; overflow được phép theo quy tắc số nguyên Java.

Ví dụ annotation:

~~~java
@interface Info {
    String name();
    int[] ids() default {1, 2};
}
~~~

Với `@Info(name = "core")`, công thức băm tương ứng là:

~~~java
int expectedHash =
        (127 * "name".hashCode() ^ "core".hashCode()) +
        (127 * "ids".hashCode() ^ Arrays.hashCode(new int[]{1, 2}));
~~~

Đây là đoạn minh họa trong phương thức có import `java.util.Arrays`, không phải ứng dụng riêng. Toán tử XOR `^` áp dụng cho từng member, sau đó **cộng** hai memberHash. Giá trị `ids` mặc định `{1, 2}` **vẫn tham gia** vào `hashCode`.

**Hệ quả bắt buộc:** nếu `a.equals(b)` là `true`, thì `a.hashCode() == b.hashCode()` phải là `true`. Chiều ngược lại **không được bảo đảm**, bởi hai giá trị khác nhau vẫn có thể trùng hash. Không dùng một hashCode đơn độc làm bằng chứng rằng hai annotation bằng nhau.

Không nên hardcode một mã băm số nguyên cụ thể khi xây logic nghiệp vụ; dùng `equals`, và nếu cần tự tính để học thì áp dụng đúng công thức của Javadoc.

## 5. Ví dụ hoàn chỉnh Java 17+: equality, defaults, arrays và HashMap

Tạo file **`AnnotationIdentityDemo.java`**:

~~~java
import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;

public class AnnotationIdentityDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Info {
        String name();
        int[] ids() default {1, 2};
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface OtherInfo {
        String name();
        int[] ids() default {1, 2};
    }

    @Info(name = "core")
    static class DefaultValues { }

    @Info(name = "core", ids = {1, 2})
    static class ExplicitValues { }

    @Info(name = "core", ids = {2, 1})
    static class Reordered { }

    @Info(name = "other")
    static class DifferentName { }

    @OtherInfo(name = "core")
    static class DifferentType { }

    public static void main(String[] args) {
        Info first = DefaultValues.class.getAnnotation(Info.class);
        Info equivalent = ExplicitValues.class.getAnnotation(Info.class);
        Info reordered = Reordered.class.getAnnotation(Info.class);
        Info different = DifferentName.class.getAnnotation(Info.class);
        Annotation other = DifferentType.class.getAnnotation(OtherInfo.class);

        int expectedHash =
                (127 * "name".hashCode() ^ "core".hashCode()) +
                (127 * "ids".hashCode() ^ Arrays.hashCode(new int[]{1, 2}));

        Map<Info, String> index = new HashMap<>();
        index.put(first, "found");

        System.out.println("same annotation type: " +
                (first.annotationType() == Info.class));
        System.out.println("getClass is annotation type: " +
                (first.getClass() == Info.class));
        System.out.println("omitted default equals explicit: " +
                first.equals(equivalent));
        System.out.println("matching hashCode: " +
                (first.hashCode() == equivalent.hashCode()));
        System.out.println("contract hash formula: " +
                (first.hashCode() == expectedHash));
        System.out.println("reversed array: " + first.equals(reordered));
        System.out.println("different member: " + first.equals(different));
        System.out.println("different annotation interface: " +
                first.equals(other));
        System.out.println("map lookup: " + index.get(equivalent));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 AnnotationIdentityDemo.java
java AnnotationIdentityDemo
~~~

Đầu ra:

~~~text
same annotation type: true
getClass is annotation type: false
omitted default equals explicit: true
matching hashCode: true
contract hash formula: true
reversed array: false
different member: false
different annotation interface: false
map lookup: found
~~~

**Giải thích từng phép kiểm tra:**

1. `first.annotationType() == Info.class` là `true`. Ngược lại, `first.getClass() == Info.class` là `false` bởi `getClass()` chỉ lớp implementation của annotation object, không phải chính annotation interface.
2. `@Info(name = "core")` và `@Info(name = "core", ids = {1, 2})` có cùng loại và cùng tất cả member values. `ids` mặc định được đưa vào hợp đồng, nên `equals` là `true`.
3. Hai annotation tương đương có `hashCode` bằng nhau. Công thức `127 * memberName.hashCode() XOR memberValueHash`, cộng qua mọi member, trả đúng hash của `first`.
4. `{2, 1}` và `{1, 2}` chứa cùng tập phần tử nhưng **khác thứ tự**, nên `equals` trả `false`.
5. Thay `name` từ `"core"` sang `"other"` làm khác member value, vì thế `equals` trả `false`.
6. `@OtherInfo(name = "core")` có cùng tên và default member values nhưng là **annotation interface khác**; `equals` vẫn `false`.
7. `HashMap<Info, String>` lưu theo `first` và truy xuất bằng `equivalent` thành công nhờ hợp đồng `equals`/`hashCode`, **không cần cùng identity đối tượng**.

Ví dụ chủ động không in tên lớp proxy hoặc thứ tự `toString()`, bởi đó không phải thuộc tính nên dựa vào khi thiết kế ứng dụng.

## 6. Khác biệt giữa annotation interface và giá trị annotation

Một annotation interface là khai báo kiểu, ví dụ:

~~~java
@interface Security {
    String role();
    boolean enabled() default true;
}
~~~

Mỗi đối tượng annotation runtime chứa các **giá trị thành viên** theo khai báo ấy. `role()` và `enabled()` là các member method không có tham số, không phải Java fields thông thường có thể đặt giá trị tùy ý.

- `Security.class`: token kiểu (annotation interface).
- `someAnnotation.annotationType()`: token kiểu annotation mà object biểu diễn.
- `someAnnotation.role()`: đọc member value từ annotation object.
- `someAnnotation.equals(other)`: so sánh **cả loại và toàn bộ member values**.
- `someAnnotation.hashCode()`: hash từ toàn bộ member values theo công thức chuẩn.

Trên annotation interface, các member method có thể khai báo giá trị `default`. Điều này không giống từ khóa `default` cho Java interface method có body. Annotation member không thực hiện logic nghiệp vụ động như method thông thường.

**Cần `@Retention(RetentionPolicy.RUNTIME)`** khi muốn lấy annotation từ Reflection runtime bằng các API như `Class.getAnnotation`, `Method.getDeclaredAnnotation`, `Field.getAnnotation`. Annotation có retention `SOURCE` hoặc `CLASS` không được hiển thị như annotation runtime bình thường qua các API này.

`@Target` xác định annotation có thể đặt ở đâu. Nó không thay đổi công thức `equals` và `hashCode` cho những annotation cùng loại đã được đọc.

## 7. Dùng `annotationType()`, `equals` và `hashCode` trong framework

### Phân nhóm annotation theo loại

Một framework scan nhiều thành viên có thể dùng:

~~~java
Annotation annotation = element.getAnnotation(Security.class);
if (annotation != null) {
    Class<? extends Annotation> type = annotation.annotationType();
    // type là Security.class.
}
~~~

Đây là đoạn minh họa trong phương thức đã có `AnnotatedElement element`, với `Security` được khai báo trong ví dụ trên và đã giữ tới runtime.

Nếu cần tạo tập các **annotation interfaces có mặt**, dùng `Set<Class<? extends Annotation>>` chứa `annotationType()`, thay vì `getClass()`. Cùng một annotation interface có thể xuất hiện dưới nhiều annotation object khác nhau; kiểu và giá trị là hai chiều dữ liệu riêng.

### Dùng annotation làm khóa

Nhờ hợp đồng so sánh theo giá trị, một annotation runtime có thể được dùng như khóa `Map` hoặc phần tử `Set`, trong phạm vi các dữ liệu annotation phù hợp:

~~~java
Map<Info, String> descriptions = new HashMap<>();
descriptions.put(infoA, "configuration");
String found = descriptions.get(infoB);
~~~

Đoạn này minh họa với `infoA` và `infoB` đã có kiểu `Info`. Nếu chúng `equals`, phép tra cứu có thể tìm cùng entry.

Dù vậy, **không sử dụng `annotation.hashCode()` thay `equals` để quyết định tương đương**: hash có thể va chạm. Nếu tạo implementation tùy chỉnh của annotation interface, hãy tuân thủ đầy đủ hợp đồng `Annotation` (đặc biệt là so sánh mảng, default values, kiểu annotation và công thức hash). Triển khai thiếu chính xác có thể khiến `HashMap` hoặc `HashSet` hoạt động sai.

### Khi chỉ muốn lấy tất cả annotation?

`element.getAnnotations()`, `getDeclaredAnnotations()`, `getAnnotationsByType(...)` phục vụ **tìm annotation** với các quy tắc riêng về khai báo trực tiếp, kế thừa hoặc repeatable annotation. Sau khi có một annotation object, hợp đồng `equals`, `hashCode`, `annotationType` của nó vẫn là hợp đồng trong `java.lang.annotation.Annotation`.

Không nhầm thao tác **lọc nơi đặt annotation** với thao tác **so sánh giá trị annotation**. Hai annotation giống nhau gắn lên các class khác nhau vẫn có thể `equals == true`.

## 8. Những sai lầm dễ gặp

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Dùng `a == b` để xác nhận hai annotation có cùng nội dung | `==` so identity của object | Dùng `a.equals(b)` |
| Dùng `a.getClass()` để xác định loại annotation | Trả implementation class | Dùng `a.annotationType()` |
| Chỉ so member được ghi tường minh | Member dùng default cũng có giá trị | So mọi member theo hợp đồng |
| Dùng `intArray.equals(otherIntArray)` | Mảng không override `Object.equals` để so nội dung | Dùng `Arrays.equals` |
| Xem `ids={1,2}` bằng `ids={2,1}` | Thứ tự trong array member có ý nghĩa | So theo vị trí |
| Dùng `hashCode` bằng nhau để khẳng định annotation bằng nhau | Có thể có hash collision | So bằng `equals` |
| Nhầm `annotationType()` với class được gắn annotation | Một bên là loại annotation, bên kia là annotated element | Giữ riêng `AnnotatedElement` |
| Lệ thuộc kết quả `annotation.toString()` hoặc tên proxy | Javadoc không yêu cầu chuỗi trình bày/implementation cố định | Đọc member values theo API |
| Tự tính hash array bằng `array.hashCode()` | Hash identity không đúng hợp đồng | Dùng `Arrays.hashCode` thích hợp |
| Không kiểm tra `getAnnotation` trả `null` | Khi không có annotation, gọi member sẽ ném NPE | Kiểm tra `null` trước |

### Lưu ý nâng cao: `float` và `double`

Với annotation có member `double threshold()`, không được mô phỏng `equals` bằng cách dùng thuần toán tử `==`. Theo Javadoc của `Annotation.equals`:

- `Double.NaN` so với `Double.NaN` được xem là **bằng** ở member annotation.
- `+0.0` và `-0.0` được xem là **không bằng** ở member annotation.
- `hashCode` cho member số thực dùng `Float.hashCode` / `Double.hashCode` thông qua wrapper, phù hợp với quy tắc `equals`.

Đây là lý do phải dùng hợp đồng `Annotation` thay vì tự viết một bộ so sánh “có vẻ tương đương”.

## 9. Checklist khi làm việc với annotation runtime

1. Xác định annotation có `@Retention(RUNTIME)` và target phù hợp.
2. Lấy annotation bằng đúng Reflection API: `getAnnotation`, `getDeclaredAnnotation` hay `getAnnotationsByType` tùy trường hợp.
3. Kiểm tra kết quả khác `null`.
4. Nếu cần **định danh annotation interface**, dùng `annotationType()`.
5. Nếu cần **so sánh hai annotation**, dùng `equals()`, không dùng identity, không chỉ so `toString()`.
6. Nếu cần làm khóa trong `HashMap`/`HashSet`, tin dùng cặp `equals`/`hashCode` tuân thủ đặc tả; đừng dùng một số hash làm định danh duy nhất.
7. Khi kiểm thử, có ít nhất một trường hợp **giá trị mặc định**, một trường hợp **array member**, một trường hợp **khác annotation interface**.
8. Không viết logic dựa vào class name hoặc cấu trúc implementation nội bộ của annotation proxy.

### Câu hỏi tự kiểm tra

**1.** `@Config(value="x")` với `int level() default 1` có bằng `@Config(value="x", level=1)` không?  
**Có**, nếu là cùng annotation interface và tất cả member values khác cũng giống nhau.

**2.** Hai annotation đặt trên hai class khác nhau có thể `equals` không?  
**Có**, vì nơi đặt annotation không phải member value tham gia so sánh.

**3.** Một annotation có `int[] ids()` trả `{1,2}`, annotation khác trả `{2,1}`. Chúng có bằng nhau không?  
**Không**, vì `Arrays.equals` xét thứ tự các phần tử.

**4.** Khi `a.equals(b)` là `true`, `a.hashCode() == b.hashCode()` có bắt buộc không?  
**Có**. Nhưng cùng hashCode **không** đủ suy ra `equals`.

**5.** Muốn biết annotation được khai báo bằng `@interface Role` hay `@interface Policy`, nên dùng API nào?  
**`annotationType()`**, không phải `getClass()`.

**6.** Mã băm của một member mảng được tính qua `array.hashCode()` hay `Arrays.hashCode(array)`?  
**`Arrays.hashCode(array)`**, dùng overload phù hợp với loại mảng.

**7.** Annotation không có `@Retention(RUNTIME)` thì Reflection chắc chắn nhìn thấy nó ở runtime?  
**Không.** Cần cấu hình retention phù hợp để các API Reflection thông thường trả annotation.

**Ghi nhớ cuối:** `annotationType()` định danh **loại annotation**; `equals()` so **loại và toàn bộ member values** (kể cả default và nội dung mảng); `hashCode()` mã hóa đúng hợp đồng ấy. Cả ba thuộc `java.lang.annotation.Annotation`, không dựa vào identity hoặc tên lớp implementation runtime.

### Tài liệu chính thức

- [Java SE 17 — `java.lang.annotation.Annotation`: `equals`, `hashCode`, `annotationType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html)
- [Java SE 17 — `AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)
- [Java SE 17 — `RetentionPolicy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html)
- [Java Language Specification §9.6 — Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6)
