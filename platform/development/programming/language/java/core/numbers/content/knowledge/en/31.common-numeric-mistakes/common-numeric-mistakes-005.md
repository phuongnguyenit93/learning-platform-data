# Unbox null trong phép toán hoặc toán tử điều kiện của Java

## 1. Vấn đề: một biến Integer có thể chứa null, nhưng int thì không

Trong Java, các kiểu số nguyên thủy như `int`, `long`, `double`, `float`, `short`, `byte` và kiểu logic `boolean` luôn chứa một giá trị primitive khi được sử dụng hợp lệ. Trong khi đó, các lớp wrapper tương ứng (`Integer`, `Long`, `Double`, `Float`, `Short`, `Byte`, `Boolean`, `Character`) là **kiểu tham chiếu**, nên biến có thể chứa `null`.

Java hỗ trợ chuyển đổi tự động:

- **Boxing**: từ primitive sang wrapper, ví dụ `int → Integer`.
- **Unboxing**: từ wrapper sang primitive, ví dụ `Integer → int`.

Với một wrapper khác `null`, unboxing là thao tác thuận tiện. Với wrapper đang bằng `null`, phép chuyển sang primitive gây **`NullPointerException` tại thời điểm chạy**.

~~~java
Integer count = null;

// Lỗi xảy ra tại lệnh gán vì Java cần unbox count thành int:
// int total = count; // NullPointerException

Integer safeToStore = count; // Hợp lệ: chỉ sao chép tham chiếu null.
~~~

Một số lỗi khó nhận ra hơn vì chương trình **không ghi tường minh** `intValue()`, `longValue()` hoặc `booleanValue()`. Toán tử số học, so sánh, và đặc biệt toán tử điều kiện `?:` có thể ngầm đòi primitive. Bài học này giải thích chính xác điểm unboxing xảy ra và cách tránh lỗi mà không tự ý thay đổi ý nghĩa nghiệp vụ của `null`.

## 2. Unboxing thực chất tương đương gọi phương thức lấy giá trị primitive

Ví dụ:

~~~java
Integer number = Integer.valueOf(12);
int a = number;                  // Auto-unboxing
int b = number.intValue();       // Tương đương về giá trị
System.out.println(a == b);      // true
~~~

Nếu `number` là `null`, lời gọi `number.intValue()` không thể thực hiện. Tương tự:

| Wrapper | Primitive đích | Phương thức lấy primitive tương ứng |
|---|---|---|
| `Integer` | `int` | `intValue()` |
| `Long` | `long` | `longValue()` |
| `Double` | `double` | `doubleValue()` |
| `Float` | `float` | `floatValue()` |
| `Short` | `short` | `shortValue()` |
| `Byte` | `byte` | `byteValue()` |
| `Boolean` | `boolean` | `booleanValue()` |
| `Character` | `char` | `charValue()` |

Nhiều trường hợp Java chấp nhận cả wrapper và primitive trong biểu thức, nhưng quá trình biên dịch chèn logic unboxing khi kiểu được yêu cầu là primitive. Do đó, **biểu thức biên dịch thành công không chứng minh dữ liệu `null` sẽ chạy an toàn**.

~~~java
Integer quantity = null;

// Các lệnh dưới đây có thể biên dịch, nhưng khi thực thi sẽ gây NPE:
// int result = quantity + 1;
// boolean positive = quantity > 0;
// int maximum = Math.max(quantity, 0);
~~~

`NullPointerException` là vấn đề runtime, không phải một quy tắc Java buộc compiler phải từ chối các biến wrapper có khả năng `null`.

## 3. Các phép toán số học dễ kích hoạt unboxing

Khi toán hạng là wrapper nhưng toán tử cần primitive, Java sẽ thử unbox. Các trường hợp phổ biến:

| Biểu thức với `Integer n = null` | Tại sao gặp NPE? |
|---|---|
| `int x = n;` | Gán cho `int` yêu cầu `n.intValue()` |
| `int x = n + 1;` | `+` số học yêu cầu giá trị số của `n` |
| `int x = n * 2;` | `*` số học yêu cầu unbox |
| `boolean b = n > 0;` | `>` là toán tử so sánh số, cần `int` |
| `boolean b = n == 0;` | Wrapper so với primitive số, cần quy tắc so sánh số |
| `n++;` | Đọc giá trị primitive, tăng, rồi boxing/gán lại |
| `n += 2;` | Compound assignment vẫn cần đọc và tính từ giá trị cũ |
| `int x = Math.max(n, 0);` | Phương thức `Math.max(int, int)` cần tham số `int` |
| `int x = Math.abs(n);` | Overload số nguyên cần `int` |

Ví dụ toán tử tăng không làm wrapper biến thành đối tượng có thể thay đổi. `Integer` vẫn bất biến; `n++` thường được hiểu như lấy giá trị cũ, thực hiện phép cộng primitive rồi gán wrapper mới. Nếu giá trị cũ là `null`, bước unbox thất bại trước khi có kết quả.

~~~java
Integer attempts = Integer.valueOf(2);
attempts++; // Thành Integer chứa 3, không sửa đối tượng Integer(2) cũ.
~~~

Các phép số học được đánh giá theo thứ tự và quy tắc kiểu Java; toán hạng nào được thực sự đánh giá và cần unbox thì null ở vị trí đó gây lỗi. Không nên giải thích NPE này bằng "Java cộng null như số 0": Java **không có quy tắc coi null là 0**.

### Phân biệt nối chuỗi với phép cộng số học

Dấu `+` cũng dùng để nối chuỗi:

~~~java
Integer n = null;
System.out.println("n=" + n); // n=null

// int total = n + 1;          // NullPointerException
~~~

Trong nối chuỗi, Java có thể chuyển tham chiếu `null` thành chuỗi `"null"`; điều này khác hẳn `+` số học. Đừng suy luận rằng vì in `n` không lỗi nên phép cộng số với `n` cũng an toàn.

## 4. Toán tử điều kiện ?: gây unboxing ngay cả khi biến nhận là Integer

Toán tử điều kiện có cú pháp:

~~~java
condition ? expressionIfTrue : expressionIfFalse
~~~

Java **chỉ đánh giá một trong hai nhánh kết quả** tùy điều kiện. Tuy nhiên, kiểu của toàn bộ biểu thức `?:` được xác định tại thời điểm biên dịch từ các toán hạng và quy tắc ngôn ngữ. Điều này tạo ra trường hợp bất ngờ:

~~~java
Integer nullable = null;
boolean chooseFirst = true;

// Biên dịch được, nhưng chạy NPE:
Integer result = chooseFirst ? nullable : 7;
~~~

Ở đây một nhánh là `Integer` và nhánh kia là primitive `int`. Theo quy tắc của **numeric conditional expression**, kết quả điều kiện có kiểu primitive `int` trong trường hợp này. Nếu nhánh `nullable` được chọn, Java phải unbox `nullable` để tạo kết quả `int`. Vì nó là `null`, chương trình ném `NullPointerException`.

**Đặc biệt:** biến nhận kết quả có kiểu `Integer` **không bảo vệ** đoạn mã trên. Java trước hết phải tính giá trị biểu thức `?:` (kiểu `int`), sau đó mới boxing để gán vào `Integer`. Lỗi đã xảy ra ở bước unbox trước đó.

Tương tự:

~~~java
Integer nullable = null;
boolean yes = true;

// CŨNG NPE dù biến nhận kiểu Object:
Object value = yes ? nullable : 7;
~~~

Không thể dùng kiểu biến nhận `Object` làm "lá chắn" cho unboxing đã được quyết định bên trong biểu thức điều kiện.

### 4.1. Cách tránh: giữ cả hai nhánh là Integer nếu cần cho phép null

~~~java
Integer nullable = null;
boolean yes = true;

// Hai nhánh đều là Integer: kết quả tham chiếu có thể là null.
Integer result = yes ? nullable : Integer.valueOf(7);
System.out.println(result); // null
~~~

Cần hiểu đúng: đoạn này **không thay null thành giá trị mặc định**. Nó chủ ý giữ `null` ở kết quả nếu nhánh tương ứng được chọn. Điều này phù hợp khi `null` có ý nghĩa "không có dữ liệu" hoặc "chưa được xác định".

Sau đó nếu muốn lấy primitive, vẫn phải kiểm tra:

~~~java
int safeValue = result == null ? 0 : result;
~~~

Lời giải trên chỉ phù hợp nếu hợp đồng nói `null` có thể được thay bằng 0. Nếu thiếu dữ liệu là lỗi, cần báo lỗi thay vì âm thầm gán mặc định.

### 4.2. Bảng so sánh các nhánh của ?:

Giả sử `Integer missing = null; boolean chooseFirst = true;`.

| Biểu thức | Kiểu/hiệu ứng quan trọng | Khi nhánh đầu được chọn |
|---|---|---|
| `chooseFirst ? missing : 7` | Một nhánh `Integer`, một nhánh `int` → unboxing để thành số | **NPE** |
| `chooseFirst ? missing : Integer.valueOf(7)` | Hai nhánh `Integer` | Trả tham chiếu `null`, chưa NPE |
| `chooseFirst ? missing : "fallback"` | Hai nhánh tham chiếu không phải numeric conditional | Trả `null`, chưa NPE |
| `chooseFirst ? null : Integer.valueOf(7)` | Nhánh `null` và tham chiếu `Integer` | Có thể trả `null` an toàn khi nơi nhận chấp nhận tham chiếu |
| `chooseFirst ? null : 7` rồi gán cho `int` | Nhánh `null` được chọn, phép gán cần unbox kết quả nullable | **NPE** |
| `chooseFirst ? missing : 7` rồi gán cho `Object` | Biểu thức numeric conditional vẫn cần `int` trước khi boxing | **NPE** |

Điểm quan trọng: hãy phân biệt **NPE xảy ra khi tính toán biểu thức** và **NPE xảy ra sau đó khi ép kết quả tham chiếu sang primitive**. Chúng có thể có stack trace khác nhau, nhưng đều bắt nguồn từ việc cần primitive khi giá trị tham chiếu là `null`.

### 4.3. Điều kiện false thì nhánh null không nhất thiết gây lỗi

~~~java
Integer missing = null;
boolean chooseFirst = false;

int value = chooseFirst ? missing : 7; // 7, không NPE
~~~

Vì điều kiện false nên nhánh `missing` không được đánh giá. Tuy vậy biểu thức này **không an toàn với mọi dữ liệu**: nếu đổi điều kiện sang true, NPE xuất hiện. Đây là nguyên nhân các lỗi sản xuất đôi khi chỉ xảy ra trên một đường nhánh hiếm gặp.

## 5. Boolean null ngay tại phần điều kiện

Không chỉ nhánh kết quả; **điều kiện của `if`, `while`, `for` và `?:` cần boolean primitive**. Khi truyền `Boolean`, Java có thể unbox nó:

~~~java
Boolean approved = null;

// Các biểu thức sau biên dịch nhưng có thể ném NullPointerException:
// if (approved) { ... }
// String label = approved ? "yes" : "no";
// while (approved) { ... }
~~~

Toán tử logic `&&` và `||` cũng yêu cầu giá trị boolean ở những toán hạng thực sự được đánh giá:

~~~java
Boolean enabled = null;

// boolean wrong = enabled && true; // NPE
boolean safe = enabled != null && enabled; // false
~~~

Trong biểu thức an toàn, toán tử `&&` đánh giá từ trái sang phải và **short-circuit**: khi `enabled != null` false, Java không đánh giá `enabled` ở vế phải nên không unbox.

Một cách rõ ràng hơn khi muốn coi `null` là false:

~~~java
Boolean enabled = null;
boolean enabledOnlyIfTrue = Boolean.TRUE.equals(enabled); // false
~~~

`Boolean.TRUE.equals(enabled)` không gọi phương thức trên đối tượng có thể null; receiver là hằng `Boolean.TRUE` không null. Nó trả false cho cả `Boolean.FALSE` và `null`.

**Cẩn thận với ba trạng thái:** nếu `null` là trạng thái "chưa trả lời", khác với false ("từ chối"), đừng gộp cả hai thành false mà không có yêu cầu nghiệp vụ. Có thể kiểm tra rõ:

~~~java
if (enabled == null) {
    // Thiếu dữ liệu hoặc trạng thái chưa xác định.
} else if (enabled) {
    // true
} else {
    // false
}
~~~

Ở đây điều kiện `enabled` chỉ được đánh giá sau khi đã biết wrapper khác null.

### Sự khác biệt giữa && và &

`&&` short-circuit; `&` trên boolean luôn đánh giá cả hai vế:

~~~java
Boolean enabled = null;

boolean safe = enabled != null && enabled; // false
// boolean unsafe = enabled != null & enabled; // NPE: vế phải vẫn chạy.
~~~

Quy tắc tương tự với `||` (short-circuit) và `|` (không short-circuit) khi dùng cho boolean. Đây là lỗi thường xảy ra khi thay nhầm một ký tự toán tử logic.

## 6. So sánh ==, equals và < khi tham gia wrapper

Không phải mọi toán tử `==` liên quan đến wrapper đều bắt buộc unbox. Kiểu tĩnh của **cả hai toán hạng** quyết định so sánh tham chiếu hay so sánh số.

~~~java
Integer a = null;
Integer b = Integer.valueOf(7);

System.out.println(a == b);      // false: hai tham chiếu Integer
System.out.println(a == null);   // true: kiểm tra tham chiếu
System.out.println(java.util.Objects.equals(a, b)); // false

// boolean numerical = a == 7; // NPE: Integer so với primitive int
// boolean less = a < 7;       // NPE: phép < đòi giá trị số
~~~

Hai `Integer` dùng `==` là **so sánh nhận dạng tham chiếu**, không phải so sánh giá trị số. Điều này có thể dẫn đến một loại bug khác ngay cả khi không null:

~~~java
Integer x = new Integer(1000); // Ví dụ minh họa API cũ; constructor bị deprecated.
Integer y = new Integer(1000);

// x == y có thể false dù cùng giá trị; đừng dùng == để so giá trị wrapper.
~~~

Trong mã mới, không cần tạo wrapper bằng constructor. Dùng `Integer.valueOf(...)` hoặc autoboxing và **`Objects.equals(x, y)`** cho so sánh giá trị có thể null, hoặc sau khi kiểm tra null dùng `x.intValue() == y.intValue()` nếu thực sự cần primitive.

So sánh giá trị khi null có thể có ý nghĩa riêng. Ví dụ:

~~~java
Integer score = null;
boolean isZero = java.util.Objects.equals(score, 0); // false, không NPE
~~~

`Objects.equals` an toàn với null nhưng **không** coi null là 0; nó coi một bên null và bên kia không null là không bằng nhau.

Riêng `score.equals(0)` vẫn ném NPE nếu `score == null`, bởi receiver của lời gọi phương thức là null:

~~~java
// score.equals(0); // NullPointerException
boolean zero = Integer.valueOf(0).equals(score); // false
~~~

Khi so sánh `Integer` với `Long`, `Objects.equals` xét cả kiểu đối tượng, nên `Integer.valueOf(5)` không bằng `Long.valueOf(5L)` theo `equals`. Nếu nghiệp vụ muốn so giá trị giữa các kiểu số, hãy chuyển đổi **có kiểm soát và kiểm tra null**; không mặc định mọi wrapper số đều tương đương chỉ vì cùng trị số.

## 7. Chương trình Java 17+ hoàn chỉnh: tái hiện NPE và các cách an toàn

Tạo tệp `NullUnboxingDemo.java`. Chương trình bắt `NullPointerException` theo từng ví dụ để toàn bộ chương trình có thể chạy đến cuối, đồng thời giữ đầu ra ổn định và dễ kiểm tra:

~~~java
import java.util.Objects;
import java.util.Optional;

public class NullUnboxingDemo {
    private static void check(String name, Runnable action) {
        try {
            action.run();
        } catch (NullPointerException ex) {
            System.out.println(name + ": NullPointerException");
        }
    }

    public static void main(String[] args) {
        Integer missing = null;
        Boolean unknown = null;
        boolean chooseFirst = true;

        check("arithmetic", () -> {
            int value = missing + 1;
            System.out.println(value);
        });

        check("mixed-ternary", () -> {
            Integer value = chooseFirst ? missing : 7;
            System.out.println(value);
        });

        Integer kept = chooseFirst
                ? missing
                : Integer.valueOf(7);
        System.out.println("both-boxed: " + kept);

        check("Object-target", () -> {
            Object result = chooseFirst ? missing : 7;
            System.out.println(result);
        });

        Object reference = chooseFirst ? missing : "fallback";
        System.out.println("reference-ternary: " + reference);

        check("condition", () -> {
            String answer = unknown ? "yes" : "no";
            System.out.println(answer);
        });

        check("compare-with-int", () -> {
            boolean equalsZero = missing == 0;
            System.out.println(equalsZero);
        });

        System.out.println("Objects.equals: "
                + Objects.equals(missing, 0));
        System.out.println("safe-Boolean: "
                + Boolean.TRUE.equals(unknown));

        int fallback = missing == null ? 0 : missing;
        System.out.println("checked-fallback: " + fallback);

        int optionalFallback = Optional.ofNullable(missing).orElse(0);
        System.out.println("optional-fallback: " + optionalFallback);
    }
}
~~~

Chạy với JDK 17 hoặc mới hơn:

~~~bash
javac NullUnboxingDemo.java
java NullUnboxingDemo
~~~

Kết quả stdout:

~~~text
arithmetic: NullPointerException
mixed-ternary: NullPointerException
both-boxed: null
Object-target: NullPointerException
reference-ternary: null
condition: NullPointerException
compare-with-int: NullPointerException
Objects.equals: false
safe-Boolean: false
checked-fallback: 0
optional-fallback: 0
~~~

Đọc kết quả theo từng nhóm:

- `arithmetic`: Java cần `int` để thực hiện phép cộng.
- `mixed-ternary` và `Object-target`: biểu thức điều kiện có nhánh `Integer`/`int` nên unbox trước khi trả kết quả, bất kể biến nhận là `Integer` hay `Object`.
- `both-boxed`: hai nhánh đều là `Integer`, nên kết quả có thể là tham chiếu null.
- `reference-ternary`: hai nhánh `Integer` và `String` tạo biểu thức tham chiếu, nhánh `missing` có thể trả null mà không unbox.
- `condition`: `Boolean` null bị unbox khi chọn nhánh.
- `compare-with-int`: phép so sánh wrapper với primitive cần xử lý giá trị số.
- `Objects.equals` và `Boolean.TRUE.equals`: không dùng unboxing của đối tượng nullable; kết quả false.
- `checked-fallback` và `optional-fallback`: lựa chọn mặc định 0 có chủ đích, không NPE.

**Không phụ thuộc vào văn bản chi tiết của thông báo NPE** trong test: "helpful NullPointerExceptions" của các bản JDK có thể tạo thông báo khác nhau tùy cách biên dịch. Chương trình in tên ngoại lệ cố định để giúp hiểu hiện tượng, không in `ex.getMessage()`.

## 8. Các mẫu sửa lỗi: chọn theo ý nghĩa của null

Lỗi unboxing không nên được "sửa" bằng cách đổi mọi null thành 0. Cần quyết định ý nghĩa nghiệp vụ của null trước.

### 8.1. Null nghĩa là giá trị mặc định

~~~java
Integer quantity = null;
int value = quantity != null ? quantity : 0;
~~~

Toán tử `?:` trong ví dụ vẫn có kiểu primitive `int` nhưng **chỉ chọn nhánh có thể null khi đã biết quantity khác null**. Phép unboxing vì thế an toàn.

Có thể viết ngắn hơn:

~~~java
int value = quantity == null ? 0 : quantity;
~~~

Hoặc khi dữ liệu đầu vào được thiết kế theo kiểu nullable:

~~~java
int value = java.util.Optional.ofNullable(quantity).orElse(0);
~~~

`Optional.ofNullable` nhận null và cho một `Optional` rỗng; `orElse(0)` trả một `Integer` không null, sau đó Java unbox an toàn thành `int`. Cách này không cần thiết cho mọi đường tính toán; kiểm tra null trực tiếp thường rõ ràng và nhẹ hơn.

### 8.2. Null là lỗi dữ liệu, phải từ chối

~~~java
import java.util.Objects;

Integer amount = null;

// Khi gọi và amount null, lỗi xảy ra sớm với thông báo có chủ đích:
int required = Objects.requireNonNull(amount, "amount must not be null");
~~~

`requireNonNull` ném `NullPointerException` với thông điệp chỉ định khi giá trị null. Nếu ứng dụng muốn một loại ngoại lệ khác, có thể kiểm tra và ném `IllegalArgumentException` hoặc exception miền nghiệp vụ ở đúng ranh giới dữ liệu.

Điều quan trọng là **phát hiện null sớm**, thay vì để exception xuất hiện sâu trong phép cộng hoặc một biểu thức `?:` phức tạp rồi khó lần ra nguồn.

### 8.3. Null là trạng thái có nghĩa, phải giữ lại

~~~java
Integer measured = null;

Integer selected = measured == null
        ? null
        : Integer.valueOf(measured + 1);

// selected là null; không ép thành 0.
~~~

Nếu API trả `Integer` nullable, giữ nguyên khả năng trả null thay vì ép sang `int`. Với kết quả cuối chỉ có thể là số hoặc không có số, một `OptionalInt` cũng có thể diễn đạt ý nghĩa vắng mặt một cách rõ ràng:

~~~java
java.util.OptionalInt maybeValue = measured == null
        ? java.util.OptionalInt.empty()
        : java.util.OptionalInt.of(measured);
~~~

`OptionalInt` không chứa null bên trong, nhưng người gọi phải xử lý trạng thái không có giá trị qua `isPresent()`, `orElse(...)`, `orElseThrow()`... Không coi `OptionalInt.empty()` tương đương số 0 nếu nghiệp vụ không nói vậy.

### 8.4. Boolean ba trạng thái

~~~java
Boolean answer = null;

if (answer == null) {
    System.out.println("unknown");
} else if (answer) {
    System.out.println("yes");
} else {
    System.out.println("no");
}
~~~

Chỉ sau khi kiểm tra khác null mới được unbox trong `else if`. Nếu nghiệp vụ cho phép null được xem là false, `Boolean.TRUE.equals(answer)` là một thành ngữ gọn. Nếu nghiệp vụ phân biệt chưa trả lời và từ chối, dùng ba nhánh như ví dụ.

## 9. Chú ý ranh giới dữ liệu: List, Map, Stream và Optional

Unboxing null không chỉ xuất hiện trong các biểu thức nhìn thấy ngay ở một dòng mã. Nó còn thường xảy ra khi dữ liệu được đưa vào API yêu cầu primitive.

### 9.1. List<Integer> và Stream

~~~java
import java.util.Arrays;
import java.util.List;

List<Integer> values = Arrays.asList(1, null, 3);

// NullPointerException khi terminal operation thực sự duyệt tới phần tử null:
// int sum = values.stream().mapToInt(Integer::intValue).sum();

int safeSum = values.stream()
        .filter(java.util.Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum(); // 4
~~~

`mapToInt(Integer::intValue)` yêu cầu unbox wrapper và xảy ra khi pipeline được thực thi (vì Stream intermediate operations là lazy). Phải quyết định rõ null nghĩa là "bỏ qua", "coi là 0" hay "lỗi đầu vào"; đoạn `filter(Objects::nonNull)` chỉ phù hợp khi việc bỏ qua phần tử rỗng là đúng.

Lưu ý `List.of(1, null, 3)` tự nó đã không cho phép null và ném `NullPointerException` khi tạo list; ví dụ sử dụng `Arrays.asList` để mô tả tình huống một collection thực sự chứa null.

### 9.2. Map.get hoặc getOrDefault

~~~java
import java.util.HashMap;
import java.util.Map;

Map<String, Integer> counts = new HashMap<>();
counts.put("A", null);

// int value = counts.get("A"); // NPE vì unboxing null.
~~~

`Map.getOrDefault(key, defaultValue)` **không phải luôn là biện pháp thay null**: nếu key tồn tại và được gắn với giá trị null, nó có thể trả null (với `HashMap`). Ví dụ:

~~~java
// Map<String, Integer> counts như ở trên.
// int value = counts.getOrDefault("A", 0); // vẫn có thể NPE.
~~~

Nếu ứng dụng cho phép `null` là giá trị có nghĩa, xử lý rõ ràng:

~~~java
Integer count = counts.get("A");
int value = count == null ? 0 : count;
~~~

Nếu cần phân biệt "không có key" và "key có giá trị null", dùng `containsKey` cùng `get` hoặc thiết kế lại cấu trúc dữ liệu cho phù hợp.

### 9.3. Optional không tự bảo đảm unboxing an toàn

~~~java
import java.util.Optional;

Optional<Integer> maybe = Optional.empty();

// int value = maybe.orElse(null); // NPE nếu cố gán null vào int.
int safeValue = maybe.orElse(0);
~~~

`Optional<Integer>` diễn đạt khả năng không có wrapper. Nhưng kết quả của `orElse(null)` vẫn có thể là null; nếu được unbox sau đó, lỗi vẫn xuất hiện. Chọn `OptionalInt` khi API cần biểu diễn trực tiếp "có hoặc không có một giá trị int" mà không cần wrapper ở mỗi bước.

## 10. Trường hợp điều kiện phức tạp và thứ tự đánh giá

Các biểu thức có nhiều nhánh dễ che giấu một phép unbox nằm sâu bên trong:

~~~java
Integer discount = null;
boolean vip = true;
boolean promotion = false;

// Ví dụ cần kiểm tra kiểu và null trước khi viết code phức tạp:
// int applied = vip ? discount : (promotion ? 5 : 0);
~~~

Nếu `vip` là true, nhánh `discount` được chọn; do biểu thức số đòi primitive, null có thể bị unbox. Dù nhánh còn lại không chạy, điều đó không làm biểu thức an toàn.

Thay vào đó, làm rõ chính sách:

~~~java
Integer discount = null;
boolean vip = true;
boolean promotion = false;

int applied;
if (vip) {
    if (discount == null) {
        throw new IllegalStateException("VIP discount is missing");
    }
    applied = discount;
} else {
    applied = promotion ? 5 : 0;
}
~~~

Khi điều kiện nghiệp vụ phức tạp, một khối `if/else` với kiểm tra null tường minh thường dễ hiểu và dễ review hơn lồng nhiều biểu thức `?:`, nhất là khi các nhánh có kiểu wrapper/primitive khác nhau.

### Toán tử short-circuit giúp tránh phép unbox không cần thiết

~~~java
Integer age = null;

boolean adult = age != null && age >= 18; // false, không NPE
boolean missingOrAdult = age == null || age >= 18; // true, không NPE
~~~

Ở ví dụ đầu, vế phải `age >= 18` chỉ chạy khi `age != null`. Ở ví dụ sau, vế phải chỉ chạy khi `age == null` là false. Mẫu kiểm tra này an toàn nhờ quy tắc đánh giá ngắn mạch; thay nhầm `&&` thành `&` hoặc `||` thành `|` có thể làm mất khả năng bảo vệ.

## 11. Quy tắc rà soát mã để phát hiện unboxing null

Khi review đoạn Java có wrapper nullable, hãy lần theo **kiểu tĩnh** của từng toán hạng, không chỉ nhìn kiểu khai báo biến đích.

Một checklist ngắn:

1. **Nguồn nullable:** trường entity/DTO, kết quả `Map.get`, parse dữ liệu thiếu, cột database có null, phương thức trả wrapper có thể null.
2. **Đích primitive:** gán `Integer → int`, truyền vào phương thức `method(int)`, trả về từ hàm khai báo `int`.
3. **Toán tử yêu cầu primitive:** `+`, `-`, `*`, `/`, so sánh `<`/`>`, toán tử tăng/giảm và compound assignment.
4. **Điều kiện logic:** `if(Boolean)`, `while(Boolean)`, `Boolean && ...`, `Boolean ? ... : ...`.
5. **Toán tử `?:`:** khi trộn wrapper số và primitive số, kiểm tra kiểu của **toàn bộ biểu thức**. Việc kết quả được gán cho `Integer`/`Object` không nhất thiết tránh unboxing.
6. **API chuyển đổi:** `Integer::intValue`, `mapToInt`, `Collectors.summingInt`, `Math.max` và các overload yêu cầu primitive.
7. **Kiểm thử cả hai nhánh:** điều kiện true/false và các giá trị null/non-null; lỗi hiếm thường nằm ở nhánh không được chạy trong test đơn giản.

### Kiểm thử bằng ca nhỏ nhất

Để xác nhận một biểu thức có rủi ro, viết test với tất cả tổ hợp có ý nghĩa:

| Điều kiện | Giá trị wrapper | Điều cần kiểm tra |
|---|---|---|
| true | khác null | Kết quả nhánh đầu đúng |
| true | null | Có NPE hoặc null được giữ lại theo hợp đồng? |
| false | khác null | Nhánh thứ hai và kiểu kết quả |
| false | null | Nhánh null có bị bỏ qua thật không? |
| `Boolean` null làm điều kiện | bất kỳ | Có NPE từ phần điều kiện trước khi chọn nhánh? |

Không nên chỉ test "happy path" với `Integer.valueOf(5)`. Phải có test chạy thực sự với `null` và kiểm tra đúng kiểu exception hoặc kết quả mặc định.

## 12. Sai lầm thường gặp và cách thay thế

| Cách viết / suy nghĩ sai | Vấn đề | Hướng xử lý |
|---|---|---|
| `Integer n = flag ? nullable : 0;` chắc chắn không NPE vì kết quả là Integer | Nhánh `Integer`/`int` có thể unbox `nullable` | Kiểm tra null hoặc dùng hai nhánh wrapper nếu muốn giữ null |
| `Object o = flag ? nullable : 0;` chắc chắn giữ được null | Kiểu biểu thức được quyết định trước khi gán vào Object | Xác định kiểu của `?:`, sửa kiểu nhánh |
| `Boolean b = null; if (b) ...` | Điều kiện đòi `boolean` | `Boolean.TRUE.equals(b)` hoặc kiểm tra ba trạng thái |
| `n == 0` an toàn nếu n là Integer | So với primitive làm unbox null | `Objects.equals(n, 0)` hoặc kiểm tra null |
| `n.equals(0)` là null-safe | Gọi phương thức trên null gây NPE | `Objects.equals(n, 0)` |
| `n++` không thể NPE vì chỉ tăng wrapper | Tăng yêu cầu unbox giá trị cũ | Khởi tạo giá trị, kiểm tra null |
| `mapToInt(Integer::intValue)` tự bỏ qua null | Pipeline unbox từng phần tử khi tiêu thụ | Lọc hoặc báo lỗi rõ theo hợp đồng |
| `map.getOrDefault(k, 0)` luôn khác null | Map có key gắn với null vẫn có thể trả null | Đọc vào wrapper, kiểm tra null |
| `Optional.ofNullable(n).orElse(null)` là safe | Có thể trả null rồi bị unbox | Chọn default không null hoặc giữ Optional |
| Thay mọi null thành 0 | Mất ý nghĩa "thiếu" hay "chưa xác định" | Xác lập chính sách xử lý null |
| Dùng `==` để so giá trị hai Integer | Hai wrapper có thể so tham chiếu | `Objects.equals` cho so giá trị null-safe |
| Chỉ test với điều kiện false | Không kiểm tra đường nhánh null được chọn | Test true/false với null và non-null |

## 13. Bài tập tự kiểm tra

**Câu 1.** Điều gì xảy ra?

~~~java
Integer n = null;
int r = n + 10;
~~~

**Đáp án:** `NullPointerException` khi Java unbox `n` để thực hiện phép cộng `int`.

**Câu 2.** Tại sao mã này có thể ném NPE dù kiểu biến nhận là `Integer`?

~~~java
Integer n = null;
boolean flag = true;
Integer r = flag ? n : 5;
~~~

**Đáp án:** hai nhánh có kiểu `Integer` và `int`; biểu thức điều kiện số có kiểu `int`, nên nhánh `n` được unbox khi chọn. `flag` true, `n` null, dẫn đến NPE trước bước boxing kết quả về `Integer`.

**Câu 3.** Đổi `5` thành `Integer.valueOf(5)` trong câu 2 thì sao?

**Đáp án:** Hai nhánh đều kiểu `Integer`, nên kết quả có thể là tham chiếu `null` và phép gán vào `Integer` không NPE. NPE vẫn có thể xuất hiện nếu unbox kết quả sau đó.

**Câu 4.** `Boolean approved = null; boolean ok = approved != null && approved;` trả kết quả nào?

**Đáp án:** `false`, không NPE. Vế phải không chạy vì `approved != null` false.

**Câu 5.** Với `Integer a = null; Integer b = 2;`, so sánh `a == b` và `a == 2` khác nhau thế nào?

**Đáp án:** `a == b` so sánh tham chiếu wrapper, trả false, không cần unbox. `a == 2` so với primitive `int`, unbox `a` và gây NPE. Khi muốn so giá trị, nên dùng `Objects.equals(a, b)` thay vì so nhận dạng wrapper.

**Câu 6.** Vì sao đoạn code `String s = "n=" + nullableInteger;` có thể chạy khi `nullableInteger` null?

**Đáp án:** Toán tử `+` với chuỗi nối chuỗi từ tham chiếu, có thể tạo `"n=null"`; đây không phải phép cộng số học cần unbox.

**Câu 7.** Một DTO chứa `Integer quantity` có thể null. API yêu cầu kết quả là `int`. Nên làm gì?

**Đáp án:** Xác định null mang nghĩa gì: mặc định 0, lỗi dữ liệu hay thiếu thông tin phải chuyển lên tầng gọi. Sau đó kiểm tra null trước khi unbox hoặc thay mô hình dữ liệu/kiểu trả về. Không tự gán 0 nếu nghiệp vụ chưa quy định.

**Câu 8.** `Optional<Integer>` có bảo đảm biểu thức `int x = optional.orElse(null);` chạy an toàn không?

**Đáp án:** Không. Nếu Optional rỗng thì `orElse(null)` trả null và phép gán vào `int` cố unbox null, dẫn đến NPE.

---

**Ghi nhớ:** `null` hợp lệ đối với wrapper nhưng không thể trở thành primitive bằng unboxing. Phép số học, so sánh, điều kiện `Boolean`, API nhận primitive và toán tử `?:` trộn wrapper/primitive đều có thể kích hoạt unboxing ẩn. **Kiểm tra kiểu của biểu thức trước khi gán**, kiểm tra null tại ranh giới và chọn chính sách xử lý null đúng nghiệp vụ thay vì mặc định coi null bằng 0.