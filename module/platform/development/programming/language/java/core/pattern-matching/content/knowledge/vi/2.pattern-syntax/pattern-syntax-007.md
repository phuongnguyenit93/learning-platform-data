# Pattern resolution theo kiểu của expression trong Java

## 1. Mục tiêu: vì sao cùng một pattern có lúc hợp lệ, có lúc lỗi?

Trong Java, pattern matching không chỉ là phép kiểm tra một đối tượng ở lúc chạy. **Trước khi chạy, trình biên dịch phải xác định pattern có thể áp dụng cho kiểu của biểu thức đang được kiểm tra hay không.** Quá trình này thường được giải thích là *pattern applicability / resolution theo kiểu của expression*: lấy **kiểu tĩnh** (*compile-time type*) của expression để kiểm tra tính tương thích với pattern, xác định kiểu của biến được gắn, và trong một số trường hợp suy luận đối số kiểu của record pattern.

Ví dụ, biểu thức `value` có thể chứa đối tượng `String` ở runtime nhưng có **kiểu tĩnh** là `Object`, `CharSequence` hoặc `String` tùy nơi khai báo. Quy tắc biên dịch áp dụng cho kiểu tĩnh đó, không đoán theo đối tượng thực tế sẽ được truyền vào sau này.

Sau bài này, bạn có thể:

- Phân biệt **kiểu tĩnh của expression**, **kiểu được yêu cầu bởi pattern** và **lớp thực tế của giá trị lúc chạy**.
- Dự đoán một type pattern trong `instanceof` có hợp lệ về cú pháp/kiểu hay bị lỗi biên dịch.
- Giải thích vì sao pattern variable có kiểu xác định và vì sao `var` có thể làm thay đổi cách phân tích pattern.
- Hiểu cách kiểu của expression hỗ trợ suy luận kiểu trong generic record pattern (Java 21+).
- Phân tích các nhánh `switch` theo kiểu selector, tính áp dụng của `case`, thứ tự, dominance và xử lý `null`.
- Nhận biết khác biệt quan trọng giữa Java 17 và Java 21 đối với *unconditional patterns* trong `instanceof`.

## 2. Hai giai đoạn không được nhầm với nhau

Giả sử có một biểu thức `expression` với kiểu tĩnh `T` và một type pattern `U variable`.

**Giai đoạn biên dịch:**

1. Java xác định kiểu tĩnh `T` từ biểu thức ở bên trái `instanceof`, hoặc từ selector của `switch`.
2. Java kiểm tra pattern có **applicable at T** (áp dụng được tại kiểu `T`) không. Đối với type pattern kiểu tham chiếu `U` trong Java 21, điều kiện cốt lõi là `T` có phép chuyển đổi ép kiểu được kiểm tra (*checked cast conversion*) đến `U` theo ngôn ngữ Java. Nếu không, chương trình có lỗi biên dịch.
3. Nếu là record pattern, trình biên dịch còn xét kiểu record, các component pattern và có thể suy luận đối số kiểu của generic record từ kiểu `T`.
4. Kiểu của pattern variable được xác định từ pattern và quy tắc suy luận tĩnh. Nó không tự chuyển thành lớp cụ thể hơn chỉ vì giá trị runtime có lớp đó.

**Giai đoạn chạy:**

1. Expression được tính ra một giá trị.
2. Java thử khớp giá trị với pattern (loại đối tượng, cấu trúc record, các component pattern và điều kiện `when` khi có).
3. Nếu khớp, pattern variable được khởi tạo và có thể sử dụng tại phạm vi mà luồng điều khiển đảm bảo mẫu đã khớp.
4. Với `instanceof`, giá trị `null` làm kết quả pattern matching là `false`, dù pattern có được coi là *unconditional* theo kiểu tĩnh.

Điểm mấu chốt: **applicable** chỉ có nghĩa “mẫu hợp lệ để thử”; nó **không bảo đảm** mọi giá trị runtime sẽ khớp.

| Thuộc tính | Được xác định khi nào? | Ví dụ |
| --- | --- | --- |
| Kiểu tĩnh của expression (`T`) | Biên dịch | `Object input` thì `input` có kiểu tĩnh `Object` |
| Kiểu của type pattern (`U`) | Biên dịch | `String text` yêu cầu kiểu `String` |
| Pattern có applicable tại `T` không | Biên dịch | `Object` có thể kiểm tra với `String` |
| Giá trị runtime có khớp không | Chạy | `input` thực tế là `Integer` thì `String text` không khớp |
| Kiểu của pattern variable | Biên dịch | `text` có kiểu `String` sau nhánh khớp |

## 3. Ví dụ Java 17: một đối tượng, nhiều góc nhìn kiểu tĩnh

Đoạn sau là **chương trình đầy đủ** chạy được trên Java 17+. Lưu với tên `StaticTypeResolutionDemo.java`.

~~~java
public class StaticTypeResolutionDemo {
    static String describe(Object expression) {
        if (expression instanceof String text && !text.isBlank()) {
            return "String:" + text.toUpperCase();
        }
        if (expression instanceof Number number) {
            return "Number:" + number.intValue();
        }
        return "Other";
    }

    static String charSequence(CharSequence expression) {
        if (expression instanceof String text) {
            return "String length=" + text.length();
        }
        return "Other CharSequence";
    }

    public static void main(String[] args) {
        Object wide = "Java";
        CharSequence interfaceView = "hi";
        System.out.println(describe(wide));
        System.out.println(describe(12));
        System.out.println(describe(null));
        System.out.println(charSequence(interfaceView));
        System.out.println(charSequence(new StringBuilder("ok")));
        var inferred = "Java";
        Object widened = inferred;
        System.out.println(describe(widened));
    }
}
~~~

~~~bash
javac --release 17 StaticTypeResolutionDemo.java
java StaticTypeResolutionDemo
~~~

Kết quả:

~~~text
String:JAVA
Number:12
Other
String length=2
Other CharSequence
String:JAVA
~~~

Phân tích:

- `Object wide = "Java";`: biến `wide` có **kiểu tĩnh** `Object`, trong khi giá trị runtime là `String`. Pattern `String text` applicable tại `Object` và khớp tại runtime.
- Trong `describe(12)`, đối số số nguyên được boxing thành `Integer` để truyền vào tham số `Object`. Pattern `String` không khớp; pattern `Number` có khớp, vì `Integer` là con của `Number`.
- Với `null`, cả hai type pattern trong `instanceof` đều không khớp nên trả về `Other`.
- `CharSequence interfaceView = "hi";` vẫn chứa `String`. Pattern `String text` applicable tại `CharSequence`: một đối tượng `String` có thể được nhìn qua interface `CharSequence`.
- `new StringBuilder("ok")` cũng là `CharSequence` nhưng không phải `String`, nên cùng pattern không khớp khi chạy.
- `var inferred = "Java";` khiến Java suy luận **kiểu tĩnh** của `inferred` là `String`. Phép gán `Object widened = inferred;` tạo một biểu thức ở kiểu rộng hơn; lời gọi `describe(widened)` vẫn sử dụng cùng giá trị `String` lúc chạy.

Trong mẫu `expression instanceof String text`, `text` có kiểu `String`. Nếu mẫu là `expression instanceof Number number`, biến `number` có kiểu `Number`, dù đối tượng lúc chạy có thể là `Integer` hoặc `Double`. Không thể gọi phương thức riêng của `Integer` trên `number` mà không có kiểm tra/ép kiểu phù hợp.

## 4. Tính tương thích được quyết định bằng kiểu expression

Đọc từng ví dụ theo thứ tự: **kiểu của biểu thức → pattern muốn thử → trình biên dịch cho phép hay không → kết quả nếu chạy**.

| Kiểu tĩnh của expression | Pattern | Java 17/21 | Giải thích |
| --- | --- | --- | --- |
| `Object` | `String s` | Hợp lệ | Có đối tượng `Object` tại runtime đồng thời là `String` |
| `CharSequence` | `String s` | Hợp lệ | `String` triển khai `CharSequence` |
| `Number` | `Integer n` | Hợp lệ | `Integer` là lớp con của `Number` |
| `Integer` | `String s` | Lỗi biên dịch | Hai lớp không tương thích theo phép checked cast |
| `String` | `String s` | Java 17: lỗi; Java 21: hợp lệ | Khác biệt phiên bản về *unconditional patterns* trong `instanceof` |
| `Object` | `Number n` | Hợp lệ | Có thể khớp với giá trị kiểu `Integer`, `Double`, ... |

### Ví dụ lỗi vì hai lớp không tương thích

Đây là **đoạn minh họa cố ý không biên dịch**, không ghép vào chương trình chạy ở trên:

~~~java
static boolean invalid(Integer expression) {
    return expression instanceof String text; // COMPILE ERROR
}
~~~

Java biết `Integer` là lớp `final` và không thể là một `String`; không có phép checked cast hợp lệ trong trường hợp này. Lỗi xảy ra khi biên dịch; không đợi chương trình chạy rồi trả về `false`.

Ngược lại, khi viết:

~~~java
Object expression = Integer.valueOf(7);
boolean matched = expression instanceof String text;
~~~

Java cho phép vì kiểu tĩnh là `Object`; biểu thức trả về `false` vì giá trị thực tế là `Integer`. **Cùng một giá trị runtime không đồng nghĩa cùng một kết quả kiểm tra tính hợp lệ ở compile time.**

### Khác biệt Java 17 và Java 21: pattern đã bao trùm kiểu tĩnh

Với Java 17, đoạn sau bị `javac --release 17` từ chối (*unconditional patterns in instanceof are not supported in -source 17*):

~~~java
static boolean test(String expression) {
    return expression instanceof String text;
}
~~~

Từ Java 21, type pattern bao trùm kiểu tĩnh như thế được cho phép. Chương trình sau **chạy được với Java 21+**:

~~~java
public class UnconditionalTypeDemo {
    static String describe(String expression) {
        return expression instanceof String text
            ? "Matched:" + text.length()
            : "No match";
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(null));
    }
}
~~~

~~~bash
javac --release 21 UnconditionalTypeDemo.java
java UnconditionalTypeDemo
~~~

Kết quả:

~~~text
Matched:4
No match
~~~

“Unconditional” là khái niệm về **quan hệ kiểu tĩnh của pattern**. Nó không biến `null` thành một đối tượng `String`; `instanceof` với `null` vẫn trả về `false`. Trong thực tế, nếu đầu vào đã là `String`, thường không cần dùng lại type pattern để xác nhận điều hiển nhiên; chỉ cần xử lý `null` nếu cần.

## 5. Suy luận bằng var không thay đổi quy tắc

Cần phân biệt hai vai trò của `var`:

**Biến cục bộ trong Java 10+:**

~~~java
var expression = "hello";   // expression có kiểu tĩnh String
Object wider = expression;  // wider có kiểu tĩnh Object
~~~

`var` suy luận từ biểu thức khởi tạo, **không** có nghĩa biến thuộc kiểu động hay kiểu `Object`. Vì thế nếu viết `expression instanceof String s` thì Java 17 có thể từ chối dạng unconditional, còn `wider instanceof String s` là hợp lệ. Java 21 cho phép cả hai cách kiểm tra.

**Pattern variable trong type pattern ở vị trí `instanceof`:**

~~~java
if (wider instanceof String text) {
    System.out.println(text.length());
}
~~~

Ở đây dùng tên kiểu `String`, **không viết** `wider instanceof var text` trong Java 17/21. `var` có vai trò khác: nó được hỗ trợ cho component pattern trực tiếp bên trong record pattern (Java 21+), như phần kế tiếp.

## 6. Generic record pattern: kiểu expression giúp suy luận kiểu của component

Một record tổng quát có thể khai báo `record Envelope<T>(T payload) {}`. Với Java 21, record pattern vừa kiểm tra kiểu record vừa tách component. Khi viết `Envelope(var item)`, trình biên dịch có thể dùng **kiểu tĩnh của expression** để suy luận tham số generic của record pattern và kiểu của `item`.

Đây là chương trình đầy đủ lưu tại `RecordTypeResolutionDemo.java`:

~~~java
record Envelope<T>(T payload) {}

public class RecordTypeResolutionDemo {
    static String typed(Envelope<String> expression) {
        if (expression instanceof Envelope(var item)) {
            return "Upper:" + item.toUpperCase();
        }
        return "Not envelope";
    }

    static String unknown(Object expression) {
        if (expression instanceof Envelope(var item)) {
            return "Payload:" + item;
        }
        return "Not envelope";
    }

    public static void main(String[] args) {
        System.out.println(typed(new Envelope<>("java")));
        System.out.println(unknown(new Envelope<>(42)));
        System.out.println(unknown("hello"));
    }
}
~~~

~~~bash
javac --release 21 RecordTypeResolutionDemo.java
java RecordTypeResolutionDemo
~~~

Kết quả:

~~~text
Upper:JAVA
Payload:42
Not envelope
~~~

**Vì sao hai phương thức khác nhau?**

- `typed(Envelope<String> expression)` biết rõ tham số kiểu là `String`. Với `Envelope(var item)`, Java có đủ dữ liệu tĩnh để suy luận kiểu của `item` là `String`. Lời gọi `item.toUpperCase()` hợp lệ.
- `unknown(Object expression)` chỉ biết kiểu tĩnh là `Object`. Record pattern nhận ra `Envelope` lúc chạy nhưng không thể suy ra `T = String` chỉ nhờ nhìn payload thực tế. Trong trường hợp này, `item` được nhìn như `Object`.
- Nếu thay `return "Payload:" + item;` bằng `return item.toUpperCase();` trong `unknown`, trình biên dịch báo không có `toUpperCase()` trên `Object`.
- Record pattern không “đọc lại generic type argument” đã bị xóa bởi *type erasure* tại runtime. Kiểu suy luận phụ thuộc thông tin đã có ở compile time.

Tính applicable của record pattern không chỉ xét record bên ngoài: các component pattern cũng phải tương thích với kiểu khai báo của từng record component. Ví dụ, ở record `Point(int x, int y)`, mẫu `Point(int x, int y)` gắn hai thành phần kiểu `int`, nhưng không thể tùy ý mô tả thành phần số nguyên này như một đối tượng `String`. Record pattern là tính năng ổn định từ Java 21.

## 7. Generic type pattern: không phải cứ thêm đối số kiểu là kiểm tra được

Trường hợp generic giúp thấy rõ hơn lý do Java kiểm tra **kiểu tĩnh của expression**. Chương trình sau chạy được trên Java 17:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericResolutionDemo {
    static String describe(List<String> words) {
        if (words instanceof ArrayList<String> items) {
            return "ArrayList size=" + items.size();
        }
        return "Other list size=" + words.size();
    }

    public static void main(String[] args) {
        System.out.println(describe(new ArrayList<>(List.of("a", "b"))));
        System.out.println(describe(List.of("a")));
    }
}
~~~

~~~bash
javac --release 17 GenericResolutionDemo.java
java GenericResolutionDemo
~~~

Kết quả:

~~~text
ArrayList size=2
Other list size=1
~~~

Kiểu tĩnh `List<String>` đã mang thông tin tham số kiểu; Java cho phép phép kiểm tra với `ArrayList<String>` vì phép chuyển đổi tương ứng hợp lệ theo quy tắc checked cast. Điều này **không có nghĩa** Java kiểm tra được từng phần tử của generic collection trong lúc chạy.

Trái lại, đoạn sau **cố ý không biên dịch** với Java 17/21:

~~~java
static boolean invalid(Object expression) {
    return expression instanceof java.util.List<String> values;
}
~~~

Từ một `Object` bất kỳ, Java không thể thực hiện phép kiểm tra runtime an toàn để xác nhận đối số kiểu `String` của một `List` do *type erasure*. Compiler báo kiểu `Object` không thể được ép kiểu an toàn thành `List<String>` trong phép kiểm tra này. Nếu chỉ cần biết đó là một `List`, có thể dùng `expression instanceof List<?> values` (với `import java.util.List;`), sau đó kiểm tra/diễn giải từng phần tử theo nhu cầu. Tránh suy diễn rằng `List<?>` là `List<String>`.

## 8. Trong switch, selector expression cũng quyết định case nào hợp lệ

Từ Java 21, `switch` với pattern hoạt động trên các kiểu tham chiếu, với các quy tắc:

1. **Kiểu selector:** Compiler lấy kiểu tĩnh của expression trong `switch (expression)`.
2. **Tương thích của case:** Mỗi case pattern phải applicable tại kiểu selector đó. Ví dụ `case String s` có thể áp dụng khi selector là `Object` hoặc `CharSequence`; `case Integer i` là lỗi khi selector là `CharSequence` trong Java 21.
3. **Thứ tự và dominance:** Các nhánh xét theo thứ tự xuất hiện. Một pattern bao quát đứng trước có thể làm pattern hẹp phía sau không thể tới được, và Java sẽ báo lỗi biên dịch.
4. **Exhaustiveness:** `switch` expression phải bao phủ toàn bộ khả năng; enhanced `switch` statement dùng pattern cũng phải đầy đủ. `default` thường là nhánh dự phòng.
5. **Null:** `case null` xử lý riêng giá trị `null`. Nếu không có nhánh phù hợp, `switch` trên giá trị `null` có thể ném `NullPointerException`.

Chương trình đầy đủ lưu tại `SwitchResolutionDemo.java`:

~~~java
public class SwitchResolutionDemo {
    static String describe(Object expression) {
        return switch (expression) {
            case null -> "Null";
            case String text when text.isBlank() -> "Blank String";
            case String text -> "String:" + text.length();
            case Number number -> "Number:" + number.intValue();
            default -> "Other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(null));
        System.out.println(describe("  "));
        System.out.println(describe("Java"));
        System.out.println(describe(7));
        System.out.println(describe(new Object()));
    }
}
~~~

~~~bash
javac --release 21 SwitchResolutionDemo.java
java SwitchResolutionDemo
~~~

Kết quả:

~~~text
Null
Blank String
String:4
Number:7
Other
~~~

Ở đây kiểu selector là `Object` nên các case `String` và `Number` đều hợp lệ để thử. Giá trị runtime quyết định nhánh nào khớp. Guard `when text.isBlank()` chỉ đánh giá sau khi pattern `String text` đã khớp, nên `text` có kiểu `String` trong guard.

### Trường hợp sai: case không phù hợp với kiểu selector

Đoạn minh họa sau **cố ý không biên dịch**:

~~~java
static int invalid(CharSequence expression) {
    return switch (expression) {
        case Integer number -> 1; // COMPILE ERROR
        default -> 0;
    };
}
~~~

Kiểu tĩnh `CharSequence` không có phép checked cast hợp lệ đến lớp `Integer` (lớp final không triển khai `CharSequence`). Kiểu selector được xác định trước khi Java so khớp các giá trị runtime.

### Trường hợp sai: pattern bao quát che mất pattern hẹp

Đoạn sau cũng **cố ý không biên dịch**:

~~~java
static int invalid(Object expression) {
    return switch (expression) {
        case CharSequence value -> 1;
        case String text -> 2; // COMPILE ERROR: dominated
        default -> 3;
    };
}
~~~

Mọi `String` đều là `CharSequence`, nên nhánh đầu đã bao trùm mọi giá trị mà nhánh thứ hai muốn bắt. Khi cần phân biệt `String` với các `CharSequence` khác, đặt `case String text` **trước** `case CharSequence value`.

Lưu ý: **pattern resolution không có nghĩa Java tự chọn “case cụ thể nhất” bất kể thứ tự** như một bộ giải overload phương thức. Java áp dụng kiểm tra tĩnh về applicability/dominance và dùng thứ tự case hợp lệ khi chạy.

## 9. Những nhầm lẫn quan trọng

1. **“Giá trị thực tế là String thì compiler chắc chắn biết.”** Không đúng: với tham số `Object`, compiler phải xử lý mọi giá trị có thể thuộc kiểu `Object`. Pattern variable được gắn theo mẫu, không dựa trên đoán trước dữ liệu.
2. **“Pattern hợp lệ nghĩa là luôn match.”** Không đúng: `Object expression = 7; expression instanceof String s` là hợp lệ nhưng trả về `false`.
3. **“Bất kỳ hai kiểu tham chiếu nào cũng có thể so bằng pattern.”** Không đúng: các kiểu không có checked cast conversion tương ứng, như `Integer` và `String`, gây lỗi biên dịch.
4. **“var luôn là Object.”** Không đúng: `var expression = "Java"` suy luận kiểu `String`; còn `var` trong generic record component được suy luận từ component và ngữ cảnh kiểu của record.
5. **“Generic parameter được kiểm tra tại runtime.”** Không đúng: `List<?>` chỉ xác định được lớp/quan hệ kiểu thích hợp; nó không xác nhận phần tử là `String`. Java có một số kiểm tra generic pattern hợp lệ khi kiểu tĩnh đủ cụ thể, nhưng không thể bỏ qua type erasure.
6. **“Pattern unconditional luôn match null.”** Không đúng: với `instanceof`, `null` trả về `false`. Ngoài ra, Java 17 và Java 21 khác nhau ở việc chấp nhận unconditional type pattern.
7. **“Trong switch, case nào cụ thể hơn sẽ tự được ưu tiên.”** Không đúng: thứ tự và dominance là một phần của quy tắc hợp lệ.

## 10. Bài tập và đáp án giải thích

**Bài 1 (Java 17+):** Cho `Object expression = "Java";` và `CharSequence expression2 = "Java";`. Cả hai có thể dùng `instanceof String s` không?

**Đáp án:** Có. Ở hai kiểu tĩnh `Object` và `CharSequence` đều tồn tại phép checked cast phù hợp đến `String`. Tại runtime cả hai cùng khớp vì giá trị là `String`.

**Bài 2 (Java 17 và Java 21):** Xét `String expression = "Java";` cùng mẫu `expression instanceof String s`. Có khác nhau về biên dịch không?

**Đáp án:** Có. Với `--release 17`, trường hợp unconditional này bị từ chối; với `--release 21`, nó hợp lệ. Với giá trị `null`, `instanceof` vẫn là `false`.

**Bài 3 (Java 21+):** Cho:

~~~java
record Box<T>(T value) {}

static void inspect(Box<String> known, Object unknown) {
    if (known instanceof Box(var first)) {
        System.out.println(first.toUpperCase());
    }
    if (unknown instanceof Box(var second)) {
        System.out.println(second);
    }
}
~~~

`first` và `second` được compiler nhìn là kiểu gì?

**Đáp án:** `first` là `String` nhờ kiểu tĩnh `Box<String>` của `known`. `second` là `Object` do `unknown` chỉ có kiểu tĩnh `Object`, nên không thể trực tiếp gọi `second.toUpperCase()`. Đây là trích đoạn có thể đặt trong một class và cần Java 21+.

**Bài 4 (Java 21+):** Trong `switch(Object x)`, vì sao `case CharSequence cs` trước `case String s` gây lỗi, còn đổi thứ tự có thể hợp lệ?

**Đáp án:** `CharSequence` bao trùm `String`; đặt trước làm `case String` không thể được chọn. Đặt `String` trước cho phép bắt trường hợp hẹp trước, rồi mới tới `CharSequence`. Đừng quên thêm `default` hoặc các case khác nếu cần tính bao phủ đầy đủ.

## 11. Checklist khi đọc một pattern

Khi gặp mã pattern matching khó hiểu, hãy tự hỏi theo thứ tự:

1. Expression này có **kiểu tĩnh nào** tại vị trí được kiểm tra? Có đang được khai báo bằng `var`, kiểu interface, generic hay có phép ép kiểu tường minh không?
2. Mẫu đang yêu cầu **kiểu nào**? Đây là type pattern hay record pattern có component lồng nhau?
3. Pattern có **applicable** tại kiểu tĩnh đó không? Có vướng generic/checked cast hoặc khác biệt phiên bản Java không?
4. Nếu hợp lệ, **giá trị runtime** có thể khớp không? `null` sẽ xử lý như thế nào?
5. Pattern variable có kiểu gì, dùng được ở vùng luồng điều khiển nào? Với `switch`, có case nào bị *dominated*, và switch đã exhaustive chưa?

Nắm chắc chuỗi **kiểu tĩnh của expression → pattern hợp lệ → đối tượng thực tế khớp → biến pattern được sử dụng** sẽ giúp đọc, viết và sửa mã pattern matching chính xác hơn.

### Đọc thêm trong đặc tả

- Java SE 21 JLS `15.20.2 — `instanceof` và pattern matching: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2
- Java SE 21 JLS `14.30.3 — Applicability, unconditional và dominance: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3
- Java SE 21 JLS `14.11.1 — Quy tắc của `switch` block: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1
