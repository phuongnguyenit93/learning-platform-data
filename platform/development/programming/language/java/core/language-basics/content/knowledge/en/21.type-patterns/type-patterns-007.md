# Mẫu bao phủ, nhãn không thể được chọn và yêu cầu đầy đủ trong Java

> **Java core — language-basics / Mẫu kiểm tra kiểu**  
> **Mục tiêu:** Hiểu quan hệ giữa các type pattern, vì sao nhãn `case` phía sau có thể bị che khuất (*dominated*), và cách một `switch` sử dụng pattern bao phủ mọi giá trị có thể có (*exhaustive*).  
> **Phiên bản:** `instanceof T x` là tính năng chính thức ở Java 17. **Pattern matching for `switch` còn là preview ở JDK 17 (JEP 406)**; ví dụ chương trình bên dưới sử dụng đúng cờ preview. Từ Java 21, pattern matching for switch đã thành tính năng chính thức.

## 1. Phân biệt ba khái niệm

| Khái niệm | Câu hỏi cần trả lời | Minh họa |
| --- | --- | --- |
| Pattern khớp | Giá trị runtime có thuộc kiểu được thử không? | Một `String` khớp `String` và `CharSequence` |
| Nhãn bị che khuất (*dominated*) | Nhãn trước có bắt hết các giá trị mà nhãn sau định bắt không? | `case CharSequence` trước `case String` |
| Tính đầy đủ (*exhaustiveness*) | Mọi giá trị selector hợp lệ có đường xử lý không? | `case String` và `default` trên `Object` |

Với nhiều nhãn `case`, thứ tự **có thể rất quan trọng**. Không giống một chuỗi `if` tự do để kiểm tra cùng giá trị nhiều lần, pattern switch được trình biên dịch kiểm tra để tránh nhãn không thể được chọn.

Một `switch expression` phải có nhánh phù hợp cho tất cả các giá trị selector mà Java yêu cầu bao phủ. Nếu thiếu, chương trình lỗi ở **thời điểm biên dịch**, không phải đợi người dùng nhập một giá trị chưa xử lý.

## 2. Nhãn bị che khuất: kiểu rộng đặt trước kiểu hẹp

`String` thực thi giao diện `CharSequence`. Vì vậy mọi đối tượng `String` đều khớp `CharSequence`, nhưng một `StringBuilder` cũng khớp `CharSequence` mà không phải `String`.

~~~java
Object value = "Java";
System.out.println(value instanceof CharSequence); // true
System.out.println(value instanceof String);       // true
~~~

Trong một pattern switch, cách sắp xếp sau **không hợp lệ**:

~~~java
// KHÔNG BIÊN DỊCH (Java 17 preview / Java 21+):
// return switch (value) {
//     case CharSequence seq -> "SEQUENCE";
//     case String text -> "TEXT"; // Bị case CharSequence che khuất.
//     default -> "OTHER";
// };
~~~

Khi đầu vào là `String`, nhánh `CharSequence` ở trước đã bắt được nó. Vì thế `case String` phía sau **không thể được chọn** (*dominated case label*).

**Sửa bằng thứ tự cụ thể → tổng quát:**

~~~java
static String label(Object value) {
    return switch (value) {
        case String text -> "STRING:" + text.length();
        case CharSequence seq -> "SEQUENCE:" + seq.length();
        default -> "OTHER";
    };
}
~~~

Với đầu vào `"Java"`, kết quả `"STRING:4"`; với `new StringBuilder("abc")`, kết quả `"SEQUENCE:3"`; với `Integer.valueOf(7)`, kết quả `"OTHER"`.

Thứ tự từ kiểu con tới kiểu cha chỉ là cách nhớ thường dùng. Điều kiện cốt lõi là **một nhãn trước không được bao phủ hoàn toàn một nhãn sau**. Nếu cần kết hợp điều kiện phức tạp, phải xét cả kiểu lẫn điều kiện của pattern theo phiên bản Java được sử dụng.

## 3. Nhãn bao phủ toàn bộ và `default`

Trên selector kiểu `Object`, nhãn `case Object any` là một *total type pattern*: nó bao phủ mọi kiểu đối tượng có thể dùng làm giá trị của selector này.

~~~java
static String broad(Object value) {
    return switch (value) {
        case String s -> "STRING";
        case Object any -> "OBJECT";
    };
}
~~~

Không cần thêm `default` vì nhãn `Object` ở cuối đã bao phủ những loại còn lại. Không đặt `case Object any` **trước** `case String s`: như vậy String bị che khuất.

Đồng thời, **không** đặt cả một total pattern và `default` trong cùng switch: chúng là hai nhãn bắt phần còn lại (*match-all*) và xung đột trong quy tắc switch.

~~~java
// KHÔNG BIÊN DỊCH:
// return switch (value) {
//     case Object any -> "ANY";
//     default -> "OTHER"; // Hai nhãn match-all.
// };
~~~

Cách dễ hiểu hơn cho người mới là dùng `default` khi không cần ràng buộc biến:

~~~java
static String fallback(Object value) {
    return switch (value) {
        case String s -> "STRING:" + s;
        case Integer n -> "INT:" + n;
        default -> "OTHER";
    };
}
~~~

**Chú ý null và phiên bản:** Pattern switch thay đổi chi tiết xử lý `null` qua các bản preview. Để chương trình rõ nghĩa trên Java 17 và 21, nếu muốn phân loại null thành một kết quả riêng, hãy viết `case null -> ...` tường minh (xem mục 6). `default` thông thường **không nên được hiểu** là nhãn riêng cho null.

## 4. Tính đầy đủ của `switch expression`

Ví dụ không bao phủ toàn bộ selector `Object`:

~~~java
// KHÔNG BIÊN DỊCH: thiếu đường cho Integer, Double, v.v.
// String result = switch (value) {
//     case String s -> "TEXT";
//     case Integer i -> "INTEGER";
// };
~~~

Dù code chỉ dự kiến truyền String và Integer, kiểu tĩnh của `value` vẫn là `Object`. Trình biên dịch phải xét các loại có thể xuất hiện khác nữa. Có thể sửa bằng `default` hoặc một total pattern phù hợp:

~~~java
String result = switch (value) {
    case String s -> "TEXT";
    case Integer i -> "INTEGER";
    default -> "OTHER";
};
~~~

Bao phủ đầy đủ **không có nghĩa tất cả nhánh đều thực thi**: tại một lần đánh giá, switch chọn một nhánh phù hợp. Cũng không có nghĩa nhánh nào cũng trả giá trị thành công — một nhánh có thể chủ động `throw`.

Với switch expression dạng `case ... ->`, các nhánh block cần `yield expression;` để cung cấp kết quả khi hoàn thành bình thường; dùng `throw` khi trường hợp đó phải bị từ chối.

## 5. Bao phủ toàn bộ phân cấp `sealed` mà không cần `default`

Java 17 đã hỗ trợ `sealed class/interface` chính thức. Khi kiểu selector là sealed interface, compiler biết các kiểu triển khai trực tiếp được phép và có thể kiểm tra các pattern đã bao phủ hết hay chưa.

~~~java
sealed interface Job permits PrintJob, SaveJob {}
record PrintJob(String message) implements Job {}
record SaveJob(int id) implements Job {}

static String describe(Job job) {
    return switch (job) {
        case PrintJob p -> "PRINT:" + p.message();
        case SaveJob s -> "SAVE:" + s.id();
    };
}
~~~

`Job` chỉ có hai kiểu triển khai trực tiếp được cho phép trong ví dụ; cả hai nhãn `case` đã có nên switch expression **exhaustive mà không cần `default`**.

Nếu thêm một kiểu triển khai được phép, chẳng hạn `SendJob`, rồi biên dịch lại, trình biên dịch sẽ yêu cầu cập nhật phần bao phủ hoặc bổ sung nhãn phù hợp. Đây là lợi ích bảo trì đáng kể so với việc đặt một `default` che giấu mọi trường hợp mới.

| Kiểu selector | Ví dụ bao phủ đầy đủ |
| --- | --- |
| `Object` | Các nhãn cụ thể rồi `default` hoặc total pattern phù hợp |
| `String` | Các nhãn chuỗi phù hợp, cùng `default` |
| `enum` | Liệt kê đủ mọi hằng enum, hoặc dùng `default` |
| Sealed interface | Pattern cho đủ các nhánh thuộc phân cấp sealed, hoặc dùng nhãn bao phủ thích hợp |

Đừng nhầm **bao phủ kiểu** với **kiểm tra toàn vẹn dữ liệu**: trường `message` vẫn có thể rỗng/null dù đối tượng là `PrintJob`. Các quy tắc nội dung phải kiểm tra thêm.

## 6. `null` là trường hợp phải thiết kế rõ

Với `instanceof` thông thường, null cho false:

~~~java
Object value = null;
boolean result = value instanceof String; // false
~~~

Nhưng `switch` với pattern không nên được xem như một chuỗi `instanceof` độc lập. Trong Java 17 preview, có thể đưa `null` thành một nhãn tường minh:

~~~java
static String nullable(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s -> "STRING:" + s.toUpperCase(java.util.Locale.ROOT);
        default -> "OTHER";
    };
}
~~~

`nullable(null)` cho `"NULL"`; `nullable("ok")` cho `"STRING:OK"`; một `Integer` rơi vào `"OTHER"`. Trên Java 17 với switch pattern preview, **không có nhãn null hoặc nhãn tổng quát xử lý null**, selector null thường dẫn đến `NullPointerException`. Do đó hãy kiểm thử null riêng, không giả định default là cách diễn đạt chính xác yêu cầu xử lý null.

Nên viết `case null` rõ ràng nếu null là giá trị đầu vào được hỗ trợ; nếu null là lỗi nghiệp vụ, có thể kiểm tra và ném ngoại lệ có thông báo ở trước switch.

## 7. Chương trình Java 17+ chạy độc lập

Tạo file **PatternCoverageDemo.java**:

~~~java
import java.util.Locale;

public final class PatternCoverageDemo {
    sealed interface Job permits PrintJob, SaveJob {}
    record PrintJob(String message) implements Job {}
    record SaveJob(int id) implements Job {}

    private static String label(Object value) {
        return switch (value) {
            case String s -> "STRING:" + s.length();
            case CharSequence seq -> "SEQUENCE:" + seq.length();
            default -> "OTHER";
        };
    }

    private static String broad(Object value) {
        return switch (value) {
            case String s -> "STRING";
            case Object any -> "OBJECT";
        };
    }

    private static String fallback(Object value) {
        return switch (value) {
            case String s -> "TEXT";
            case Integer n -> "INTEGER";
            default -> "OTHER";
        };
    }

    private static String describe(Job job) {
        return switch (job) {
            case PrintJob p -> "PRINT:" + p.message();
            case SaveJob s -> "SAVE:" + s.id();
        };
    }

    private static String nullable(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String s -> "STRING:" + s.toUpperCase(Locale.ROOT);
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println("labelText=" + label("Java"));
        System.out.println("labelBuilder="
                + label(new StringBuilder("abc")));
        System.out.println("labelInteger=" + label(Integer.valueOf(7)));

        System.out.println("broadString=" + broad("x"));
        System.out.println("broadObject=" + broad(new Object()));

        System.out.println("fallbackText=" + fallback("a"));
        System.out.println("fallbackNumber=" + fallback(3));
        System.out.println("fallbackOther=" + fallback(2.5));

        System.out.println("sealedPrint="
                + describe(new PrintJob("HELLO")));
        System.out.println("sealedSave=" + describe(new SaveJob(42)));

        System.out.println("nullableNull=" + nullable(null));
        System.out.println("nullableText=" + nullable("ok"));
        System.out.println("nullableOther=" + nullable(Integer.valueOf(9)));

        Object missing = null;
        System.out.println("instanceofNull="
                + (missing instanceof String));
    }
}
~~~

**Biên dịch/chạy trên JDK 17** (preview bắt buộc):

~~~bash
javac --enable-preview --release 17 -encoding UTF-8 PatternCoverageDemo.java
java --enable-preview PatternCoverageDemo
~~~

Trình biên dịch JDK 17 có thể in thông báo về preview ra **stderr**, không thuộc stdout của chương trình. Nếu dùng **JDK 21+**, cú pháp trong file này là tính năng chính thức, có thể chạy bằng lệnh thông thường:

~~~bash
javac -encoding UTF-8 PatternCoverageDemo.java
java PatternCoverageDemo
~~~

**Expected stdout chính xác:**

~~~text
labelText=STRING:4
labelBuilder=SEQUENCE:3
labelInteger=OTHER
broadString=STRING
broadObject=OBJECT
fallbackText=TEXT
fallbackNumber=INTEGER
fallbackOther=OTHER
sealedPrint=PRINT:HELLO
sealedSave=SAVE:42
nullableNull=NULL
nullableText=STRING:OK
nullableOther=OTHER
instanceofNull=false
~~~

Chương trình minh họa ba ý: nhãn cụ thể phải đặt trước nhãn rộng hơn; tổng pattern hoặc nhãn mặc định bao phủ trường hợp còn lại; sealed interface được xử lý đủ hai nhánh mà không cần default. Với `null`, chương trình có nhãn tường minh thay vì phụ thuộc vào mặc định.

## 8. Lỗi thường gặp và bài tập

| Hiện tượng | Nguyên nhân / cách sửa |
| --- | --- |
| `case CharSequence` trước `case String` | `case String` bị che khuất; chuyển nhãn String lên trước |
| `case Object` trước mọi nhãn hẹp | Các nhãn hẹp phía sau bị che khuất; đặt total pattern cuối |
| Cả total pattern và `default` | Hai nhãn match-all; chỉ giữ một |
| Switch expression thiếu xử lý đầu vào | Không exhaustive; thêm `default` hoặc pattern bao phủ hợp lệ |
| Sealed type có subtype mới mà switch chưa cập nhật | Mở rộng nhánh tương ứng và biên dịch lại |
| Cho rằng null tự vào `default` như các giá trị khác | Xử lý `case null` hoặc kiểm tra trước switch |
| Viết pattern switch trên JDK 17 không bật preview | Dùng `javac --enable-preview --release 17` và `java --enable-preview` |

**Bài 1.** Đổi thứ tự `case String` và `case CharSequence` trong `label`; dự đoán lỗi biên dịch và giải thích bằng quan hệ kiểu.

**Bài 2.** Bỏ `default` khỏi `fallback`. Trình biên dịch báo lỗi vì giá trị thuộc kiểu nào chưa được bao phủ?

**Bài 3.** Trong `broad`, đưa `case Object` lên trước `case String`. Nhãn nào bị che khuất? Có thể sửa chỉ bằng thêm `break` không?

**Bài 4.** Thêm kiểu mới được phép vào sealed interface `Job` và cập nhật switch expression `describe` cho exhaustive.

**Bài 5.** Kiểm thử `null` với `instanceof String` và `nullable(null)`; giải thích vì sao một phép cho false còn phép còn lại vào nhánh `case null`.

### Ghi nhớ

**Dominance**: pattern rộng đặt trước có thể làm nhãn hẹp không thể chọn, gây lỗi biên dịch. **Exhaustiveness**: switch expression phải bao phủ tất cả khả năng; có thể dùng `default`, total pattern hoặc đủ các nhánh của phân cấp `sealed`. **Null** phải được thiết kế rõ. Khi học với **JDK 17**, pattern switch cần bật **preview**; từ Java 21 đây là tính năng chính thức.
