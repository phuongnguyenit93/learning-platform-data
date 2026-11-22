# Functional interface: phương thức default, static và các phương thức của Object

Functional interface là interface mô tả **một hợp đồng hành vi trừu tượng duy nhất** để Java có thể sử dụng lambda hoặc method reference làm phần triển khai. Một điều dễ gây nhầm lẫn là functional interface **vẫn được khai báo nhiều phương thức**: có thể chứa các phương thức `default`, `static` và những khai báo khớp với các phương thức `public` của `Object` mà vẫn là functional interface.

Điểm quyết định không phải tổng số dòng khai báo phương thức, mà là **có đúng một hợp đồng phương thức trừu tượng sau khi áp dụng các quy tắc của Java Language Specification (JLS)**. Nội dung dưới đây tập trung vào cách Java xác định hợp đồng đó và cách thiết kế interface đúng trên các JDK hiện đại.

## 1. Quy tắc nhận diện một functional interface

Một interface hợp lệ làm target của lambda nếu nó có **một phương thức trừu tượng chức năng** (*single abstract method*, thường gọi là SAM). Theo JLS, các phương thức có chữ ký tương ứng với phương thức **instance public** của `java.lang.Object` được loại khỏi tập phương thức trừu tượng dùng để xác định SAM. Ngoài ra, các phương thức `default` và `static` đã có phần triển khai nên không trở thành những hợp đồng trừu tượng mới.

Trong thực tế, hãy phân loại từng khai báo:

| Dạng phương thức | Có tính là phương thức trừu tượng mới của SAM? | Ghi chú |
| --- | --- | --- |
| `void execute();` | **Có** | Trừ khi nó tương đương một khai báo trừu tượng khác theo quy tắc override |
| `default void log() { ... }` | Không | Là phương thức instance có phần triển khai |
| `static Handler noop() { ... }` | Không | Là phương thức thuộc chính interface |
| `boolean equals(Object other);` | Không | Trùng chữ ký phương thức instance `public` của `Object` |
| `int hashCode();`, `String toString();` | Không | Cũng là những chữ ký `Object` tương ứng |
| `void extra();`, cùng với `void execute();` | **Có thêm** | Hai phương thức trừu tượng độc lập thường làm interface không còn functional |

Các quy tắc chính xác có ngoại lệ về kế thừa những phương thức trừu tượng *override-equivalent* và khả năng thay thế kiểu kết quả. Tuy nhiên, mô hình đơn giản nhất để thiết kế mới là **một phương thức trừu tượng có tên rõ ràng**, các khả năng bổ trợ ở phương thức `default` hoặc `static`, và tránh khai báo lại `Object` nếu không có nhu cầu diễn đạt hợp đồng.

```java
@FunctionalInterface
interface TextRule {
    boolean test(String text);                  // SAM duy nhất
    default boolean reject(String text) {       // Không tính vào SAM
        return !test(text);
    }
    static TextRule nonEmpty() {                // Không tính vào SAM
        return text -> text != null && !text.isEmpty();
    }
    boolean equals(Object other);              // Không tính vào SAM
}
```

Đây là **định nghĩa interface minh họa**, có thể đặt trong tệp Java phù hợp; chưa có phương thức `main` để chạy độc lập. Lambda `TextRule rule = s -> s.length() >= 3;` có thể dùng làm phần triển khai của `test`. `@FunctionalInterface` yêu cầu trình biên dịch kiểm tra rằng interface vẫn thỏa điều kiện; annotation không phải điều kiện bắt buộc để một interface được sử dụng với lambda.

**Phân biệt:** một interface chỉ có `default`, `static` hoặc khai báo các phương thức `Object` nhưng **không có SAM thực sự** thì không phải functional interface. Không thể gắn `@FunctionalInterface` lên một interface như vậy.

## 2. Phương thức default: hành vi bổ trợ của từng instance

Từ khóa `default` cho phép interface định nghĩa phương thức **instance có body**. Lớp triển khai hoặc đối tượng lambda có thể sử dụng hành vi đó mà không phải tự cung cấp phần triển khai; lớp có thể override khi cần.

```java
@FunctionalInterface
interface Normalizer {
    String normalize(String text);

    default String normalizeOrEmpty(String text) {
        return text == null ? "" : normalize(text);
    }
}
```

Đây là **đoạn định nghĩa minh họa**. `normalize` là SAM. `normalizeOrEmpty` là phương thức `default`, gọi lại SAM và xác định xử lý trường hợp `null`. Ví dụ nơi dùng:

```java
Normalizer trim = String::trim;
System.out.println(trim.normalizeOrEmpty("  Java  ")); // "Java"
System.out.println(trim.normalizeOrEmpty(null));       // ""
```

Đoạn gọi này cần có định nghĩa `Normalizer` ở trên; kết quả bình luận biểu diễn chuỗi trả về, còn màn hình in ra lần lượt `Java` và một dòng trống. Phương thức `default` **không** làm tăng số lượng abstract method.

### Default method rất hợp với phép kết hợp hành vi

Một ví dụ thường gặp trong thư viện chuẩn là `Predicate.and`, `Predicate.or`, `Predicate.negate`: chúng tạo ra hành vi kết hợp từ phương thức SAM `test`. Một interface tự định nghĩa cũng có thể cung cấp thao tác kết hợp:

```java
@FunctionalInterface
interface Rule<T> {
    boolean matches(T value);

    default Rule<T> and(Rule<T> other) {
        java.util.Objects.requireNonNull(other, "other");
        return value -> matches(value) && other.matches(value);
    }
}
```

Đây là **định nghĩa minh họa**. `and` trả về một `Rule<T>` mới dựa trên hai phép kiểm tra; toán tử `&&` có short-circuit, nên `other.matches` không chạy khi điều kiện đầu `false`. Nhờ `default`, người gọi có thể viết `adult.and(active)` trong khi chỉ cần cung cấp triển khai `matches`. Chỉ nên thêm default method khi nó phù hợp với ý nghĩa của hợp đồng và không gây nhập nhằng cho người sử dụng.

### Điều cần ghi nhớ khi kế thừa và override

- Một lớp có thể override phương thức `default` bằng phương thức instance tương ứng.
- Nếu một phương thức của superclass có chữ ký phù hợp thì **phương thức của lớp được ưu tiên hơn default method của interface**.
- Nếu nhiều interface cung cấp các default method xung đột mà không có phương thức ưu tiên giải quyết, lớp triển khai phải override và chọn hành vi.
- Trong lớp triển khai, có thể gọi một default method cụ thể qua `InterfaceName.super.method()` khi ngữ cảnh cho phép.
- Một interface con có thể override default method của interface cha hoặc làm nó trở lại abstract theo quy tắc khai báo hợp lệ.

Đừng dùng default method chỉ để đẩy logic nghiệp vụ phức tạp vào interface. Nó phù hợp với hành vi chung, nhỏ, ổn định và có thể giải thích từ hợp đồng của SAM. Thêm default method vào API công khai giúp giảm số lớp phải triển khai phương thức mới, nhưng vẫn cần xem xét xung đột kế thừa ở những hệ phân cấp interface đang tồn tại.

## 3. Phương thức static: factory và tiện ích thuộc về interface

Phương thức `static` trong interface là thành viên của **kiểu interface**, không gắn với một đối tượng lambda cụ thể. Gọi bằng `InterfaceName.method()`.

```java
@FunctionalInterface
interface Filter {
    boolean test(String value);

    static Filter startsWith(String prefix) {
        java.util.Objects.requireNonNull(prefix, "prefix");
        return value -> value != null && value.startsWith(prefix);
    }

    default Filter negate() {
        return value -> !test(value);
    }
}
```

Đây là **định nghĩa minh họa**. Trong ví dụ:

```java
Filter javaNames = Filter.startsWith("Java");
System.out.println(javaNames.test("Java 17"));       // true
System.out.println(javaNames.negate().test("Kotlin")); // true
```

Phương thức `startsWith` là factory tạo ra một thực thể `Filter` bằng lambda; `negate` là default method dùng SAM của instance nhận được. Cặp `static`/`default` cho phép API dễ khám phá mà **SAM vẫn chỉ có `test`**.

**Quy tắc gọi quan trọng:** `Filter.startsWith("J")` đúng; `javaNames.startsWith("J")` không đúng vì `startsWith` là static method của interface. Static method trong interface **không được kế thừa** như instance default method; không gọi nó thông qua lớp triển khai hoặc interface con như một phương thức được kế thừa. Tham chiếu tĩnh nên được đặt rõ theo tên interface khai báo để tránh nhầm với method của đối tượng.

Phương thức static không truy cập `this` hoặc trực tiếp sử dụng trạng thái instance không được truyền vào; nó có thể nhận tham số, trả đối tượng hoặc lambda, thực hiện tính toán và xử lý dữ liệu như static method thông thường. Factory tạo sẵn lambda là một use case rõ ràng; ví dụ tiêu chuẩn `Comparator.comparing`, `Comparator.naturalOrder` là các phương thức static của `Comparator`.

## 4. Các phương thức public của Object có gì đặc biệt?

Các phương thức như:

- `boolean equals(Object obj)`
- `int hashCode()`
- `String toString()`

là những phương thức **public instance** của `Object`. Khi interface khai báo lại chính xác những chữ ký này theo quy tắc hợp lệ, chúng **không trở thành SAM bổ sung**. Mọi lớp Java đều kế thừa cơ sở các phương thức từ `Object`, vì vậy việc khai báo chúng lại không tạo thêm một hành vi trừu tượng hoàn toàn mới mà lambda phải thực hiện.

Ví dụ:

```java
@FunctionalInterface
interface KeySelector<T> {
    String key(T value);

    boolean equals(Object other);
    int hashCode();
    String toString();
}
```

Đây là **định nghĩa minh họa**. Functional method vẫn là `key(T)`. Một lambda như `KeySelector<String> selector = s -> s.trim();` là hợp lệ: các phương thức `equals`/`hashCode`/`toString` không bắt lambda phải viết thêm ba body.

**Không suy diễn quá rộng từ “phương thức của Object”:** JLS loại khỏi phép đếm SAM các chữ ký tương ứng với **public instance methods** của `Object`, không phải mọi phương thức có tên nghe giống `Object`. Chẳng hạn `clone()` trong `Object` là `protected`, nên khai báo `public Object clone();` trong interface không được loại khỏi bộ đếm theo cùng quy tắc; nó còn kéo theo yêu cầu hiện thực khác. Không dùng `clone` như mẹo thiết kế functional interface.

### Không được viết default equals/hashCode/toString

Các khai báo sau là **SAI** và không được đưa vào chương trình chạy:

```java
interface Invalid {
    default String toString() { return "Invalid"; }  // SAI
    default int hashCode() { return 1; }              // SAI
    default boolean equals(Object o) { return true; } // SAI
}
```

JLS cấm một interface khai báo default method có chữ ký *override-equivalent* với phương thức không private của `Object`. Nếu muốn chính sách so sánh, hash hoặc hiển thị, hãy định nghĩa phương thức **có tên riêng** (ví dụ `displayText()`) hoặc triển khai `equals`/`hashCode`/`toString` trực tiếp trên **class** phù hợp.

Không được giả định hai lambda khác nhau bằng nhau vì chúng có cùng body. So sánh identity hoặc triển khai `Object` của đối tượng lambda không phải một phần “hành vi tính toán” mà SAM mô tả. Nếu cần key có equality xác định, hãy tạo kiểu dữ liệu/domain object có hợp đồng `equals`/`hashCode` rõ ràng.

## 5. Comparator là ví dụ thực tế có equals nhưng vẫn functional

`java.util.Comparator<T>` là ví dụ quan trọng của JDK:

- `int compare(T a, T b)` là phương thức trừu tượng chức năng.
- `boolean equals(Object other)` là khai báo tương ứng với `Object.equals`, nên không làm tăng số SAM.
- `reversed()`, `thenComparing(...)` là ví dụ về các default method kết hợp hành vi.
- `comparing(...)`, `comparingInt(...)`, `naturalOrder()` là các static factory/helper method.

```java
Comparator<String> byLength = (a, b) ->
        Integer.compare(a.length(), b.length());

Comparator<String> byLengthThenName =
        byLength.thenComparing(Comparator.naturalOrder());
```

Đây là **đoạn minh họa**, cần `import java.util.Comparator;`. `byLength` được tạo bằng lambda dù `Comparator` có nhiều phương thức công khai; `thenComparing` dùng default behavior để tạo một comparator mới khi có phần tử cùng độ dài. Nếu cần so sánh theo thuộc tính, `Comparator.comparingInt(String::length)` thường diễn đạt ý định ngắn hơn là tự viết phép trừ giữa hai độ dài.

Không nên dùng `a.length() - b.length()` cho mọi phép so sánh số nguyên vì phép trừ có thể overflow với dữ liệu số lớn; các utility như `Integer.compare` hoặc `Comparator.comparingInt` diễn đạt đúng mục đích. Đồng thời, comparator phải có quan hệ thứ tự nhất quán theo hợp đồng của nó để collection sắp xếp đúng.

## 6. Khi default methods xung đột: quy tắc giải quyết

Một chức năng phổ biến của default method là mở rộng hợp đồng khi không bắt buộc mọi lớp hiện có tự viết method mới. Tuy nhiên, Java không tùy ý “chọn đại” giữa hai default methods trùng chữ ký.

Giả sử:

```java
interface EnglishLabel {
    default String label() { return "EN"; }
}
interface VietnameseLabel {
    default String label() { return "VI"; }
}

// ĐÚNG: lớp chủ động giải quyết xung đột.
class LabelService implements EnglishLabel, VietnameseLabel {
    @Override
    public String label() {
        return EnglishLabel.super.label() + "/" +
               VietnameseLabel.super.label();
    }
}
```

Đây là **đoạn minh họa** có thể biên dịch khi đặt trong tệp Java hợp lệ; chưa có `main`. Nếu bỏ phần override của `LabelService`, lớp sẽ bị lỗi vì nhận hai default methods xung đột. Một phương thức instance cụ thể tương ứng được kế thừa từ superclass, nếu có, có thể giải quyết tình huống theo quy tắc “class wins”; interface chuyên biệt hơn cũng có thể được ưu tiên trong phân cấp interface. Khi có xung đột khó hiểu, override tường minh thường là cách dễ bảo trì nhất.

Không nên thêm default method vào public API mà bỏ qua việc nó có thể tạo xung đột với những interface khác trong các lớp triển khai. Đánh giá tương thích nguồn và hợp đồng khi mở rộng thư viện.

## 7. Ví dụ tổng hợp chạy được với Java 17+

Ví dụ sau minh họa cùng lúc: một SAM, default method có thể ghép hành vi, static factory tạo lambda, khai báo ba phương thức `Object` không phá functional status, và giải quyết xung đột của hai default methods từ hai interface.

Lưu toàn bộ thành tệp **FunctionalInterfaceMethodsDemo.java**:

```java
import java.util.Locale;
import java.util.Objects;

public class FunctionalInterfaceMethodsDemo {

    @FunctionalInterface
    interface TextTransform {
        String apply(String text); // SAM

        default TextTransform andThen(TextTransform next) {
            Objects.requireNonNull(next, "next");
            return input -> next.apply(apply(input));
        }

        static TextTransform trim() {
            return String::trim;
        }

        // Khớp với các public instance methods của Object.
        boolean equals(Object other);
        int hashCode();
        String toString();
    }

    interface EnglishLabel {
        default String label() {
            return "EN";
        }
    }

    interface VietnameseLabel {
        default String label() {
            return "VI";
        }
    }

    static class LabelService
            implements EnglishLabel, VietnameseLabel {
        @Override
        public String label() {
            return EnglishLabel.super.label()
                    + "/" + VietnameseLabel.super.label();
        }
    }

    public static void main(String[] args) {
        TextTransform uppercase =
                text -> text.toUpperCase(Locale.ROOT);

        TextTransform pipeline =
                TextTransform.trim().andThen(uppercase);

        System.out.println(pipeline.apply("  java  "));
        System.out.println(pipeline.equals(pipeline));
        System.out.println(new LabelService().label());
    }
}
```

Chạy trên JDK 17 trở lên:

```bash
javac FunctionalInterfaceMethodsDemo.java
java FunctionalInterfaceMethodsDemo
```

**Stdout chính xác:**

```text
JAVA
true
EN/VI
```

Giải thích:

1. `@FunctionalInterface` trên `TextTransform` hợp lệ vì chỉ `apply` là SAM. `andThen` là instance default method, `trim` là static factory; ba chữ ký `Object` được loại khỏi phép đếm.
2. `TextTransform.trim()` trả một lambda dùng method reference `String::trim`. `andThen(uppercase)` trả lambda mới thực hiện cắt khoảng trắng rồi chuyển thành chữ hoa với `Locale.ROOT`. Vì thế `"  java  "` thành `"JAVA"`.
3. `pipeline.equals(pipeline)` là `true` vì một đối tượng bằng chính nó theo hợp đồng phản xạ của `equals`; điều đó **không** cho phép suy ra equality cho hai lambda được tạo riêng.
4. `LabelService` phải override `label()` do có hai default methods xung đột. `EnglishLabel.super.label()` và `VietnameseLabel.super.label()` gọi từng triển khai được chỉ định, nên tạo `"EN/VI"`.

## 8. Lỗi thường gặp

### Lỗi 1: Tưởng default/static làm mất SAM

```java
// HỢP LỆ: chỉ có một abstract method.
@FunctionalInterface
interface Operation {
    int apply(int n);
    default int twice(int n) { return apply(n) * 2; }
    static Operation identity() { return n -> n; }
}
```

Đây là **định nghĩa minh họa**. `default` và `static` có phần triển khai riêng, không bổ sung abstract method. `Operation op = n -> n + 1;` vẫn biên dịch.

### Lỗi 2: Hai abstract methods độc lập

```java
// SAI: không thể dùng @FunctionalInterface, không làm target lambda.
@FunctionalInterface
interface InvalidOperation {
    int calculate(int n);
    int validate(int n);
}
```

Bỏ annotation cũng không biến interface này thành functional interface; chỉ bỏ đi bước kiểm tra tĩnh của annotation. Cần thiết kế lại thành một SAM hoặc dùng một lớp triển khai hai phương thức nếu cả hai đều cần.

### Lỗi 3: Interface chỉ có Object methods

```java
// SAI: không có abstract method chức năng ngoài Object.
@FunctionalInterface
interface ObjectOnly {
    boolean equals(Object other);
    String toString();
}
```

Các chữ ký `Object` không trở thành SAM; interface thiếu phương thức trừu tượng mới cần thiết cho lambda.

### Lỗi 4: Đặt default lên phương thức Object

```java
// SAI: không được default override Object.toString().
interface InvalidToString {
    default String toString() {
        return "label";
    }
}
```

Hãy override `toString` trên class nếu đó là trách nhiệm của class, hoặc đặt một default method có tên riêng như `displayLabel()`.

### Lỗi 5: Gọi static method qua instance hoặc lớp triển khai

```java
// Giả sử TextTransform là interface trong ví dụ tổng hợp.
// ĐÚNG:
TextTransform trim = TextTransform.trim();

// SAI: static method của interface không gọi qua object.
// trim.trim();
```

Đây là minh họa về cú pháp gọi; `TextTransform` trong ví dụ tổng hợp là nested interface, nên câu lệnh phải đặt trong ngữ cảnh có thể truy cập đúng kiểu.

### Lỗi 6: Giả định default method luôn được ưu tiên

Nếu superclass có method instance cụ thể phù hợp, method đó có thể được chọn thay cho default method của interface. Nếu nhận hai default methods xung đột từ các interface ngang hàng, cần override trong lớp để giải quyết. Đừng phụ thuộc vào thứ tự viết `implements A, B` để quyết định chọn method nào; thứ tự này không phải quy tắc phân giải xung đột.

### Lỗi 7: Khai báo lại Object methods mà không có chủ đích

Việc khai báo `equals`, `hashCode`, `toString` trên functional interface **có thể hợp lệ**, nhưng thường không cần thiết. Nó dễ khiến người đọc tưởng rằng SAM phải xử lý cả logic so sánh, hoặc rằng những lambda khác nhau sẽ được so sánh theo nội dung code. Nếu cần equality theo dữ liệu nghiệp vụ, hãy thiết kế domain class/record phù hợp, không trông chờ vào danh tính đối tượng lambda.

## 9. Checklist thiết kế và review API

- **SAM rõ ràng:** Có đúng một hành vi trừu tượng mà người dùng sẽ cung cấp bằng lambda hoặc method reference không?
- **Annotation:** Gắn `@FunctionalInterface` để trình biên dịch bảo vệ ý định nếu interface được thiết kế làm SAM.
- **Default methods:** Mỗi method có giá trị bổ sung trực tiếp từ SAM, hành vi dễ hiểu và không làm rối trách nhiệm interface không?
- **Static methods:** Dùng tên interface để cung cấp factory/helper; đừng kỳ vọng method static được kế thừa hoặc có thể gọi qua instance.
- **Object methods:** Chỉ những khai báo tương ứng với phương thức instance `public` của `Object` mới được bỏ qua khi đếm SAM. Không tạo default `equals`/`hashCode`/`toString`.
- **Xung đột kế thừa:** Nếu mở rộng API với default method, đã xem xét việc lớp triển khai còn implement những interface nào có method cùng chữ ký chưa?
- **Thiết kế hành vi:** Lambda chỉ cần hiện thực SAM; helper default có thể tái sử dụng hành vi đó, còn static factory có thể trả về lambda dựng sẵn.
- **Kiểm chứng:** Có bài test cho kết quả từ SAM, default method, factory và nhánh override khi xung đột không?

### Bài tập tự luyện

1. Viết `@FunctionalInterface interface PriceRule` có SAM `boolean accept(int amount)`, default method `negate()` và static factory `atLeast(int minimum)`. Tạo lambda kiểm tra số tiền từ 100 trở lên. Xác định vì sao interface vẫn functional.
2. Bổ sung `boolean equals(Object other);` vào `PriceRule`. Giải thích tại sao nó không làm tăng SAM và vì sao không được thay bằng `default boolean equals(Object other) { ... }`.
3. Tạo hai interface `Printable` và `Loggable` cùng có `default String label()`. Viết một class implements cả hai và override `label()` để phân giải xung đột. Kiểm tra lớp có thể gọi từng `InterfaceName.super.label()` không.
4. Thử thêm `void audit();` vào `PriceRule` mà không có triển khai. Giải thích vì sao annotation `@FunctionalInterface` và biểu thức lambda hiện có không còn hợp lệ, rồi thiết kế cách bổ sung tác vụ audit phù hợp hơn.

### Tài liệu chính thức

- [JLS `9.8 — Functional Interfaces](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-9.html#jls-9.8)
- [JLS `9.2 — Interface Members](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-9.html#jls-9.2)
- [JLS `9.4 — Interface Method Declarations](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-9.html#jls-9.4)
- [Java SE 26 — Comparator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Comparator.html)
- [Java SE 26 — FunctionalInterface](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/FunctionalInterface.html)
