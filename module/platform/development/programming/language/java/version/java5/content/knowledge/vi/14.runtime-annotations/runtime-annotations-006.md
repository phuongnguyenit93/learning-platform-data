# Hợp đồng equals, hashCode và annotationType

## Annotation lúc chạy cũng là một giá trị có kiểu

Sau khi đọc annotation bằng reflection, chương trình có thể cần so sánh hai cấu hình, loại bỏ cấu hình trùng hoặc lưu metadata trong `HashMap` và `HashSet`. Những thao tác này cần biết khi nào hai annotation biểu diễn cùng một giá trị.

Ba phương thức trong giao diện `java.lang.annotation.Annotation` giải quyết ba câu hỏi:

| Phương thức | Câu hỏi |
| --- | --- |
| `annotationType()` | Đây là annotation thuộc kiểu khai báo nào? |
| `equals(Object)` | Hai annotation có cùng kiểu và cùng giá trị các phần tử không? |
| `hashCode()` | Giá trị hash nào phù hợp với quy tắc bình đẳng đó? |

Không dùng danh tính đối tượng hoặc chuỗi hiển thị để thay cho các hợp đồng này. Ví dụ dưới đây dùng Java 17+ và annotation có `RUNTIME` để có thể lấy chúng bằng reflection.

## Ví dụ hoàn chỉnh: mặc định, phần tử mảng và hai kiểu khác nhau

Lưu tệp `AnnotationContractDemo.java`:

```java
import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

public final class AnnotationContractDemo {
    private AnnotationContractDemo() {
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Settings {
        String mode() default "safe";
        int[] ports() default {8080, 8081};
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface OtherSettings {
        String mode() default "safe";
        int[] ports() default {8080, 8081};
    }

    @Settings
    static class Defaults {
    }

    @Settings(mode = "safe", ports = {8080, 8081})
    static class Explicit {
    }

    @Settings(ports = {8081, 8080})
    static class Reordered {
    }

    @OtherSettings
    static class Other {
    }

    public static void main(String[] args) {
        Settings a = Defaults.class.getDeclaredAnnotation(Settings.class);
        Settings b = Explicit.class.getDeclaredAnnotation(Settings.class);
        Settings reordered = Reordered.class.getDeclaredAnnotation(Settings.class);
        OtherSettings other = Other.class.getDeclaredAnnotation(OtherSettings.class);

        System.out.println("type: " + a.annotationType().getSimpleName());
        System.out.println("typeIsSettings: " + (a.annotationType() == Settings.class));
        System.out.println("defaultsEqualExplicit: " + a.equals(b));
        System.out.println("symmetric: " + b.equals(a));
        System.out.println("reorderedEqual: " + a.equals(reordered));
        System.out.println("differentTypeEqual: " + a.equals(other));
        System.out.println("equalMeansSameHash: " + (a.hashCode() == b.hashCode()));

        int expectedHash = (127 * "mode".hashCode() ^ "safe".hashCode())
                + (127 * "ports".hashCode()
                ^ Arrays.hashCode(new int[] {8080, 8081}));
        System.out.println("hashMatchesFormula: " + (a.hashCode() == expectedHash));
        System.out.println("differentTypeSameHash: "
                + (a.hashCode() == other.hashCode()));

        Set<Annotation> unique = new HashSet<>();
        unique.add(a);
        unique.add(b);
        unique.add(reordered);
        unique.add(other);
        System.out.println("uniqueCount: " + unique.size());

        int[] copy = a.ports();
        copy[0] = 9999;
        System.out.println("portsAfterCopyChange: " + Arrays.toString(a.ports()));
        System.out.println("stillEqual: " + a.equals(b));
    }
}
```

Chạy tại thư mục chứa tệp, với JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror AnnotationContractDemo.java
java AnnotationContractDemo
```

Stdout chính xác:

```text
type: Settings
typeIsSettings: true
defaultsEqualExplicit: true
symmetric: true
reorderedEqual: false
differentTypeEqual: false
equalMeansSameHash: true
hashMatchesFormula: true
differentTypeSameHash: true
uniqueCount: 3
portsAfterCopyChange: [8080, 8081]
stillEqual: true
```

## `annotationType()`: kiểu hợp đồng thay vì lớp triển khai

`a.annotationType()` trả về `Settings.class`. `a.getClass()` trả về lớp triển khai của đối tượng annotation, phụ thuộc môi trường. Vì vậy hãy dùng `annotationType()` để phân loại annotation, không kiểm tra tên lớp proxy hoặc tên lớp nội bộ. Xem [hợp đồng của `Annotation`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Annotation.html).

Trong ví dụ, `a` có kiểu tĩnh `Settings`, nhưng một bộ đọc metadata tổng quát có thể giữ nó dưới dạng `Annotation`. Khi đó vẫn có thể gọi `annotationType()` để xác định kiểu khai báo.

Không dùng `a.annotationType().getSimpleName()` làm khóa duy nhất trong ứng dụng: hai kiểu ở các package khác nhau có thể cùng tên ngắn. Bài chỉ dùng tên ngắn để stdout dễ đọc; việc so sánh kiểu dùng trực tiếp `Settings.class`.

## `equals`: so sánh cùng kiểu và cùng giá trị

Ở ví dụ, `Defaults` không viết các giá trị nhưng vẫn sử dụng `mode = "safe"` và `ports = {8080, 8081}` từ mặc định. `Explicit` viết rõ chính các giá trị đó. Vì vậy `a.equals(b)` và `b.equals(a)` cùng là `true`.

Nơi gắn annotation không phải một phần giá trị annotation: `a` đến từ `Defaults`, `b` đến từ `Explicit`, nhưng chúng vẫn bằng nhau. Việc viết tường minh hay dùng giá trị mặc định cũng không tạo ra hai giá trị khác nhau.

`Reordered` dùng mảng `{8081, 8080}`, nên không bằng cấu hình ban đầu. Mảng trong ví dụ được đối chiếu theo phần tử **và thứ tự**, không chỉ theo tập các số cổng. `Arrays.equals` cho mảng `int` cũng phân biệt hai thứ tự này. Xem [`Arrays.equals`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html#equals(int%5B%5D,int%5B%5D)).

`OtherSettings` có cùng tên phần tử và cùng giá trị mặc định nhưng là kiểu annotation khác, nên `a.equals(other)` là `false`. Tên và dữ liệu giống nhau không biến hai kiểu khai báo thành cùng một kiểu.

Không dùng `a == b` để kiểm tra ý nghĩa cấu hình. `==` so sánh cùng một đối tượng; API không yêu cầu mọi lần lấy annotation hoặc mọi annotation cùng giá trị phải dùng chung một instance. Cũng không dùng `a.toString().equals(b.toString())`: dạng chuỗi phục vụ hiển thị có thể phụ thuộc cách triển khai.

## `hashCode`: công thức dành riêng cho annotation

Hash của annotation được tính bằng tổng hash của các phần tử, kể cả phần tử dùng giá trị mặc định. Với một phần tử có tên `name` và giá trị `value`, đóng góp của nó là:

```text
(127 * name.hashCode()) XOR hash(value)
```

Trong Java, XOR là toán tử `^`. Với phần tử mảng, dùng `Arrays.hashCode` theo đúng kiểu mảng; với giá trị nguyên thủy, dùng hash của kiểu bao tương ứng; với chuỗi, enum, `Class` hoặc annotation lồng, dùng `hashCode()` của giá trị. Công thức này được quy định trong [`Annotation.hashCode()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Annotation.html#hashCode()).

`expectedHash` trong ví dụ tính lại chính hai đóng góp của `mode` và `ports`, rồi cộng chúng. Các phép tính dùng `int` của Java; không chuyển tùy ý sang công thức `Objects.hash(...)`, hash danh tính mảng hoặc số học với độ rộng khác.

Không cần tự cài đặt công thức mỗi khi đọc annotation. Phần tính tay ở đây dùng để kiểm chứng hợp đồng; mã ứng dụng thông thường gọi `a.hashCode()`.

Hai annotation bằng nhau bắt buộc có cùng hash. Chiều ngược lại không đúng: hai giá trị khác nhau có thể trùng hash. Đây cũng là giới hạn chung của `hashCode`; không dùng một số hash làm bằng chứng bình đẳng. Xem [hợp đồng `Object.hashCode()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Object.html#hashCode()).

Ví dụ cố ý tạo trường hợp dễ quan sát: `Settings` và `OtherSettings` có cùng tên phần tử và giá trị nên công thức cho cùng hash, dù `equals` trả `false`. Điều này hợp lệ; kiểu annotation không được cộng như một hạng riêng vào công thức trên.

## Hệ quả khi đưa vào `HashSet` hoặc làm khóa

Ví dụ thêm bốn đối tượng annotation nhưng tập chỉ có ba giá trị phân biệt:

- `a` và `b` là cùng một giá trị cấu hình.
- `reordered` có thứ tự mảng khác.
- `other` có kiểu annotation khác, dù hash trùng với `a`.

`HashSet` vẫn phân biệt được các phần tử khác nhau có cùng hash bằng hợp đồng bình đẳng; không phải cứ trùng hash là mất một phần tử. Bài chỉ in kích thước vì thứ tự duyệt của `HashSet` không được bảo đảm. Xem [`HashSet`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/HashSet.html).

Nếu cần lưu **mọi nơi sử dụng annotation**, không dùng riêng annotation làm khóa. Hai lớp khác nhau có annotation bằng nhau có thể bị gộp như `a` và `b`. Khóa cần thể hiện thêm phần tử nguồn, chẳng hạn lớp hoặc phương thức được đánh dấu.

Ngược lại, nếu mục tiêu là loại bỏ các cấu hình trùng theo đúng nghĩa giá trị annotation, sử dụng `Set<Annotation>` có thể phù hợp. Hãy xác định nhu cầu trước khi chọn khóa cho bộ nhớ đệm.

## Mảng trả về và tính bất biến

Các annotation được reflection trả về là bất biến. Việc đổi `copy[0]` trong ví dụ không sửa cấu hình bên trong `a`: lần gọi `a.ports()` tiếp theo vẫn cho `[8080, 8081]`, và `a.equals(b)` vẫn là `true`. Xem [tính bất biến trong `AnnotatedElement`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedElement.html).

Không lấy mảng trả về rồi sửa nó với kỳ vọng thay đổi metadata của lớp. Nếu ứng dụng cần cấu hình có thể cập nhật, hãy chuyển dữ liệu annotation sang mô hình cấu hình riêng có quy tắc cập nhật rõ ràng.

## Trường hợp `float`, `double` và annotation lồng

Với `float` và `double`, phép đối chiếu giá trị phần tử tuân theo cách so sánh của kiểu bao tương ứng: `NaN` được xem là bằng `NaN`, còn `+0.0` và `-0.0` được phân biệt. Điều này khác phép `==` nguyên thủy trong hai trường hợp đó. Xem [`Double.equals`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Double.html#equals(java.lang.Object)).

Chạy ví dụ riêng sau để quan sát, lưu trong `FloatingAnnotationDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

public final class FloatingAnnotationDemo {
    private FloatingAnnotationDemo() {
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Measure {
        double value();
    }

    @Measure(Double.NaN)
    static class NanA {
    }

    @Measure(Double.NaN)
    static class NanB {
    }

    @Measure(0.0)
    static class PositiveZero {
    }

    @Measure(-0.0)
    static class NegativeZero {
    }

    public static void main(String[] args) {
        Measure a = NanA.class.getDeclaredAnnotation(Measure.class);
        Measure b = NanB.class.getDeclaredAnnotation(Measure.class);
        Measure positive = PositiveZero.class.getDeclaredAnnotation(Measure.class);
        Measure negative = NegativeZero.class.getDeclaredAnnotation(Measure.class);
        System.out.println("NaN annotations equal: " + a.equals(b));
        System.out.println("zero annotations equal: " + positive.equals(negative));
    }
}
```

```shell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror FloatingAnnotationDemo.java
java FloatingAnnotationDemo
```

Stdout chính xác:

```text
NaN annotations equal: true
zero annotations equal: false
```

Với phần tử nguyên thủy `boolean`, `byte`, `short`, `char`, `int` và `long`, hai giá trị tương ứng được so sánh bằng `==`. Riêng hai kiểu dấu phẩy động tuân theo quy tắc vừa minh họa.

Nếu phần tử có kiểu annotation lồng, việc so sánh tiếp tục áp dụng hợp đồng annotation cho giá trị lồng đó. Phần tử `String`, enum hoặc `Class` được đối chiếu theo bình đẳng của chính giá trị tương ứng. Không chuyển các giá trị này sang chuỗi để tạo một thuật toán so sánh khác.

## Kiểm tra và lỗi thường gặp

1. Muốn biết hai cấu hình có giống nhau, gọi `equals`; không dùng `==`, tên lớp triển khai hoặc hash đơn lẻ.
2. Muốn phân loại kiểu annotation, dùng `annotationType`; tên lớp triển khai lúc chạy không phải hợp đồng.
3. Khi có phần tử mảng, giữ nguyên ý nghĩa thứ tự; nếu miền nghiệp vụ muốn coi như tập hợp thì phải xây dựng mô hình so sánh riêng.
4. Khi dùng annotation làm khóa, xác định có cần giữ vị trí nguồn hay chỉ giữ giá trị cấu hình.
5. Khi lấy annotation bằng một bộ quét tổng quát, xử lý `null` trước khi gọi các phương thức này; các ví dụ biết trước annotation có mặt.

Thử đổi thứ tự **các cặp tên–giá trị** trong `@Settings` trên `Explicit`, nhưng giữ nguyên nội dung mảng: nó vẫn bằng `Defaults`. Sau đó đổi thứ tự **phần tử trong mảng**: kết quả bình đẳng thay đổi. Hai phép thử giúp tách cách viết mã nguồn khỏi ý nghĩa dữ liệu mà annotation biểu diễn.