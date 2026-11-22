# Selector expression của pattern switch trong Java 21+

## 1. Selector expression là gì?

Trong câu lệnh hoặc biểu thức `switch`, **selector expression** là biểu thức nằm trong cặp ngoặc ngay sau từ khóa `switch`:

```java
Object value = "Java";

String result = switch (value) {
    case String text -> "text:" + text;
    case Integer number -> "number:" + number;
    default -> "other";
};
```

Ở ví dụ này, **`value` là selector expression**; đối tượng mà nó trả về là **selector value**. Các nhánh `case` ở phía dưới là các **case label**. Pattern switch sử dụng selector value để thử khớp các pattern, chẳng hạn `String text` hoặc `Integer number`, rồi thực hiện nhánh phù hợp.

Ba thành phần không nên nhầm lẫn:

- **Selector expression**: phần được tính một lần để lấy giá trị đưa vào `switch`, ví dụ `value`, `loadInput()` hoặc `request.payload()`.
- **Selector type**: kiểu tĩnh của chính biểu thức đó tại thời điểm biên dịch, ví dụ `Object`, `Shape`, `String`.
- **Case label/pattern**: điều kiện lựa chọn nhánh, ví dụ `case String text`, `case null`, `case Circle(double r)` hoặc `default`.

Với code trên, `value` có kiểu tĩnh `Object`, nhưng giá trị runtime là một `String`. Pattern `String text` khớp; biến `text` được compiler xem là `String` trong nhánh đó. Biểu thức `switch` trả về `"text:Java"`.

**Yêu cầu phiên bản:** pattern matching cho `switch` được chuẩn hóa trong **Java 21 (JEP 441)**, không cần `--enable-preview`. Các chương trình minh họa bên dưới dùng Java 21+. `switch` kiểu truyền thống có từ Java cũ, nhưng `switch` với type/record pattern có quy tắc mới hơn về kiểu selector, `null` và tính bao phủ.

## 2. Selector có thể là những loại biểu thức nào?

Selector có thể là biến, kết quả gọi phương thức, truy cập thuộc tính, kết quả của một biểu thức điều kiện hoặc một biểu thức Java khác có **kiểu hợp lệ** cho `switch`. Không bắt buộc selector phải là tên biến.

```java
Object input = "Java";

String a = switch (input) {
    case String s -> s;
    default -> "?";
};

String b = switch (getInput()) {
    case String s -> s;
    default -> "?";
};

String c = switch (condition ? valueA : valueB) {
    case Integer n -> "int:" + n;
    case String s -> "str:" + s;
    default -> "other";
};
```

Đoạn này là **cú pháp minh họa**: cần có khai báo `getInput()`, `condition`, `valueA` và `valueB` thích hợp trong ngữ cảnh thực tế.

Các quy tắc quan trọng:

1. Java đánh giá **toàn bộ selector expression một lần** khi bắt đầu thực thi `switch`, rồi lấy kết quả để lựa chọn nhánh. Nó không gọi lại biểu thức mỗi khi thử một `case`.
2. Nếu selector chứa lời gọi phương thức có tác dụng phụ, tác dụng phụ đó diễn ra khi đánh giá selector. Thứ tự tính toán vẫn tuân theo quy tắc đánh giá biểu thức thông thường của Java.
3. Nếu việc đánh giá selector ném ngoại lệ, quá trình lựa chọn `case` không diễn ra; ngoại lệ được truyền theo cơ chế Java.
4. Sau khi lấy được selector value, Java so khớp các nhãn phù hợp theo thứ tự và quy tắc của `switch`, gồm điều kiện `when` nếu có.

Nên ưu tiên selector dễ đọc, ít tác dụng phụ. Khi một phép tính phức tạp cần dùng nhiều nơi, có thể lưu nó vào biến trước rồi `switch` trên biến đó; điều này giúp đọc code và debug dễ hơn.

## 3. Kiểu tĩnh của selector quyết định pattern nào hợp lệ

Giá trị runtime quyết định **nhánh nào khớp**, còn kiểu tĩnh của selector giúp compiler quyết định **nhãn `case` nào có thể áp dụng** và **các nhánh có bao phủ đủ trường hợp không**.

### Khi selector có kiểu `Object`

```java
Object input = 42;

String description = switch (input) {
    case String s -> "string:" + s;
    case Integer n -> "integer:" + n;
    case Number n -> "number:" + n;
    default -> "other";
};
```

Đây là ví dụ hợp lệ trên Java 21: `Object` đủ rộng để tham chiếu đến `String`, `Integer` hoặc `Number`. Giá trị `42` được autobox thành `Integer` khi gán vào `Object`, nên nhánh `Integer n` khớp và biểu thức trả về `"integer:42"`.

Đặt `case Integer n` **trước** `case Number n`, bởi `Integer extends Number`. Nếu đặt `case Number n` lên trước, pattern `Number` sẽ bao trùm mọi `Integer` và nhánh `Integer` sau đó không thể được chọn; compiler phát hiện lỗi dominance.

### Khi selector đã có kiểu hẹp

```java
String input = "abc";

String result = switch (input) {
    case String text -> text.toUpperCase();
};
```

Trong trường hợp này, mọi giá trị `String` khác `null` đều khớp pattern `String text`. Compiler có thể coi pattern đó là đủ bao phủ các giá trị khác `null` của selector. Nếu `input == null` mà không có nhánh `case null`, vẫn có thể xảy ra `NullPointerException`.

Không thể tùy ý ghép `case Integer n` vào switch trên `String`: quan hệ kiểu của selector và pattern phải cho phép việc match. Tương tự, selector là một kiểu `sealed` có thể khiến compiler tính được các subtype cần bao phủ (xem mục 8).

Điểm mấu chốt: **selector type tạo nên phạm vi lựa chọn khả thi tại compile time; selector value xác định nhánh chạy tại runtime.** Pattern variable như `text` hay `n` có kiểu tĩnh do pattern khai báo, không làm thay đổi kiểu khai báo của biến selector ban đầu.

## 4. Kiểu selector được Java 21 hỗ trợ

Với `switch` truyền thống, các kiểu selector đã quen thuộc là `byte`, `short`, `char`, `int` (và wrapper tương ứng), `String`, `enum`. Pattern switch của Java 21 mở rộng khả năng dùng **các kiểu tham chiếu** như `Object`, interface, record, class, array hoặc một kiểu `sealed` làm selector.

Ví dụ một interface tự định nghĩa có thể làm selector:

```java
sealed interface Message permits TextMessage, ErrorMessage {}

record TextMessage(String text) implements Message {}
record ErrorMessage(int code) implements Message {}

static String describeMessage(Message msg) {
    return switch (msg) {
        case TextMessage(String text) -> text;
        case ErrorMessage(int code) -> "error:" + code;
    };
}
```

Đây là một **đoạn minh họa**, cần đặt trong lớp hay ngữ cảnh chứa khai báo hợp lệ. Nhờ `Message` là `sealed`, hai pattern trên bao phủ các implementation được phép (với giá trị selector khác `null`), nên không bắt buộc có `default`.

**Giới hạn phiên bản:** trong Java 21 chuẩn, `long`, `float`, `double` và `boolean` không phải các kiểu selector primitive được hỗ trợ như `int`. Các cải tiến switch cho primitive xuất hiện trong những phiên bản/preview mới hơn; không đưa chúng vào bài thực hành Java 21 ổn định. Nếu cần xử lý `long` bằng pattern switch Java 21, có thể đặt đối tượng `Long` vào một selector kiểu `Object` và match `case Long n`, nhưng đó là switch trên **tham chiếu**, không phải switch trực tiếp trên primitive `long`.

Ví dụ:

```java
Object amount = 12L;
String kind = switch (amount) {
    case Long n -> "long:" + n;
    default -> "other";
};
```

Ở đây kết quả là `"long:12"`; selector `amount` có kiểu **`Object`**, giá trị runtime là **`Long`**. Cần phân biệt `switch (amount)` với `switch (primitiveLong)` khi đọc quy tắc theo phiên bản.

## 5. Thứ tự xử lý pattern: so khớp kiểu, guard, rồi chọn nhánh

Giả sử selector có kiểu `Object`:

```java
static String classify(Object input) {
    return switch (input) {
        case null -> "missing";
        case String text when text.isBlank() -> "blank";
        case String text -> "text:" + text;
        case Integer n -> "int:" + n;
        default -> "other";
    };
}
```

Đây là một phương thức minh họa chạy trong Java 21+.

- Đầu tiên, Java lấy kết quả của selector `input`.
- Nếu kết quả là `null`, nhánh `case null` được xử lý.
- Với giá trị `String`, compiler và runtime cho phép `String text` khớp, rồi đánh giá guard `text.isBlank()` trong nhánh có `when`.
- Nếu chuỗi không blank, guard đầu trả `false`; Java tiếp tục kiểm tra nhánh `case String text` không có guard.
- Với giá trị `Integer`, nhánh `case Integer n` khớp.
- Với kiểu còn lại, dùng `default`.

Biến `text` có kiểu `String` và chỉ có hiệu lực ở những vị trí được bảo đảm pattern tương ứng đã match. Guard `when` **không thay đổi giá trị selector** và không đánh giá lại selector expression. Nó chỉ thêm điều kiện cho một nhánh đã khớp pattern.

**Dominance:** nhánh quá tổng quát đặt trước có thể che khuất nhánh cụ thể và gây lỗi biên dịch. Chẳng hạn:

```java
// Sai: pattern Number bao phủ cả Integer, nên Integer sau đó bị che.
// return switch (input) {
//     case Number n -> "number";
//     case Integer i -> "integer"; // dominated
//     default -> "other";
// };
```

Nếu cần ưu tiên `Integer`, hãy đặt case đó trước `Number`. Khi có `when`, thứ tự còn phụ thuộc điều kiện guard. Luôn để những nhánh chuyên biệt có chủ đích xuất hiện ở vị trí phù hợp.

## 6. Chương trình đầy đủ: selector, pattern, guard và null

Lưu mã sau vào **SelectorExpressionDemo.java**. Chương trình hoạt động trên **JDK 21 trở lên** theo cú pháp Java 21 ổn định.

```java
public class SelectorExpressionDemo {
    sealed interface Shape permits Circle, Rectangle {}
    record Circle(double radius) implements Shape {}
    record Rectangle(int width, int height) implements Shape {}

    static int selectorCalls;

    static Object readOnce() {
        selectorCalls++;
        return " Java ";
    }

    static String fromSelectorExpression() {
        return switch (readOnce()) {
            case String text -> "text:" + text.trim();
            default -> "other";
        };
    }

    static String describe(Object selector) {
        return switch (selector) {
            case null -> "null";
            case String text when text.isBlank() -> "blank";
            case String text -> "text:" + text.trim();
            case Integer count -> "int:" + count;
            case Circle(double radius) -> "circle:" + radius;
            case Rectangle(int width, int height) ->
                    "rectangle:" + width + "x" + height;
            default -> "other";
        };
    }

    static String describeShape(Shape shape) {
        return switch (shape) {
            case Circle(double r) -> "circle";
            case Rectangle(int w, int h) -> "rectangle";
        };
    }

    static String noNullCase(Object value) {
        return switch (value) {
            case String text -> "string";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(fromSelectorExpression());
        System.out.println("selectorCalls:" + selectorCalls);
        System.out.println(describe("   "));
        System.out.println(describe(5));
        System.out.println(describe(new Rectangle(3, 4)));
        System.out.println(describe(new Circle(2.5)));
        System.out.println(describe(null));
        System.out.println(describe(new Object()));
        System.out.println(describeShape(new Circle(1)));

        try {
            noNullCase(null);
        } catch (NullPointerException expected) {
            System.out.println("nullWithoutCase:NPE");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac SelectorExpressionDemo.java
java SelectorExpressionDemo
```

Đầu ra chính xác:

```text
text:Java
selectorCalls:1
blank
int:5
rectangle:3x4
circle:2.5
null
other
circle
nullWithoutCase:NPE
```

Giải thích từng phần:

- `switch (readOnce())` là ví dụ selector **gọi phương thức**. Hàm `readOnce()` tăng biến đếm và trả chuỗi. Hai dòng đầu xác nhận selector được đánh giá một lần trong lượt gọi này.
- `describe("   ")` gặp `String` và thỏa guard `isBlank()`, nên trả `"blank"`; chuỗi khác blank mới vào case `String text` phía sau.
- `describe(5)` truyền đối tượng boxed `Integer` qua tham số `Object` và khớp `case Integer count`.
- `Rectangle(int width, int height)` và `Circle(double radius)` là **record patterns**: lấy component của giá trị selector khi record khớp.
- `describe(null)` chạy nhánh `case null`; `describe(new Object())` chạy `default`.
- `describeShape(new Circle(1))` làm việc với selector kiểu tĩnh `Shape` và không cần `default` vì danh sách subtype của sealed interface đã được bao phủ.
- `noNullCase(null)` minh họa rằng không có `case null` thì `default` **không** tự bắt `null`; `NullPointerException` được bắt ở caller nên chương trình tiếp tục chạy.

## 7. Null là trường hợp riêng của selector

Với pattern switch Java 21, xử lý `null` cần được hiểu ngay tại selector:

```java
static String format(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s -> s.toUpperCase();
        default -> value.toString();
    };
}
```

- `case null` là nhãn khớp selector value bằng `null`.
- Các type/record patterns thông thường như `String s` hoặc `Point(int x, int y)` không thay thế việc xử lý `null` ở mức selector.
- **`default` không bắt `null`** theo quy tắc `switch` trên kiểu tham chiếu ở Java 21. Nếu thiếu `case null` và selector trả `null`, `switch` ném `NullPointerException` trước khi xử lý nhánh `default`.
- Dù switch có pattern đủ bao phủ mọi giá trị **khác `null`**, điều đó không đồng nghĩa đã xử lý `null`.
- Có thể dùng nhãn kết hợp đặc biệt `case null, default -> ...` trong tình huống phù hợp để xử lý cả hai nhóm; nhưng cách tách riêng `case null` thường dễ đọc hơn khi cần phân biệt dữ liệu thiếu.

Nếu selector có thể là `null` do một phương thức trả về, hãy quyết định rõ nghiệp vụ muốn **xử lý `null` bằng nhánh riêng** hay coi đó là lỗi. Không tự thêm `default` rồi cho rằng đã loại bỏ nguy cơ NullPointerException.

Một record pattern lồng nhau cần phân biệt thêm: selector có thể là record khác `null` nhưng một component bên trong lại `null`. Khi component đó được match bằng record pattern con, match có thể thất bại và chuyển sang nhánh sau; đây là tình huống khác với selector **tự nó** bằng `null`.

## 8. Sealed selector và tính bao phủ (exhaustiveness)

Kiểu tĩnh của selector đặc biệt quan trọng với `sealed interface`/`sealed class`.

```java
sealed interface Result permits Success, Failure {}
record Success(String data) implements Result {}
record Failure(int code) implements Result {}

static String display(Result input) {
    return switch (input) {
        case Success(String data) -> data;
        case Failure(int code) -> "error:" + code;
    };
}
```

Trong đoạn minh họa này, `Result` chỉ cho phép `Success` và `Failure` trực tiếp thực thi; cả hai pattern được viết nên compiler chứng minh được tính bao phủ của switch trên các giá trị không `null` của kiểu `Result`. Không cần `default` để một **switch expression** biên dịch.

Nếu thêm một subtype hợp lệ mới của sealed interface mà các nhánh switch chưa bao phủ, code có thể yêu cầu cập nhật thêm nhánh tại lúc biên dịch. Đây là ưu điểm khi mô hình hóa một tập trường hợp hữu hạn bằng sealed hierarchy.

**Cần nhớ hai điều:**

1. Việc compiler kiểm tra exhaustiveness dựa trên kiểu tĩnh selector, các pattern và các nhánh có thể bao phủ; không chạy thử mọi đối tượng để suy đoán.
2. Tính bao phủ về kiểu **không tự bao gồm `null`**: gọi `display(null)` vẫn gây `NullPointerException` nếu không có `case null`.

Các `when` guard có điều kiện không được xem là luôn đúng cho tất cả giá trị của kiểu; nếu chỉ có những nhánh guarded mà bỏ qua phần còn lại, switch có thể không đủ bao phủ.

## 9. Selector trong switch expression và switch statement

Hai dạng đều có selector expression, nhưng mục đích sử dụng khác nhau:

**Switch expression** tạo ra giá trị:

```java
Object input = 10;
String result = switch (input) {
    case Integer n -> "int:" + n;
    default -> "other";
};
```

**Switch statement** thực thi hành động:

```java
static void printKind(Object input) {
    switch (input) {
        case String s -> System.out.println(s);
        case Number n -> System.out.println(n);
        default -> System.out.println("other");
    }
}
```

Với switch expression, tất cả đường đi hợp lệ phải đưa ra giá trị (hoặc hoàn thành bất thường, như ném ngoại lệ); compiler yêu cầu **exhaustiveness**. Với switch statement có pattern (enhanced switch statement trong Java 21), compiler cũng yêu cầu bao phủ đầy đủ các giá trị selector không `null`. Ví dụ chỉ có `case String s` mà selector kiểu `Object`, không có nhánh khác, sẽ bị từ chối vì chưa bao phủ mọi trường hợp.

Các nhánh dạng `->` tránh rơi tiếp (fall-through) sang nhánh tiếp theo. Dạng `case ...:` cổ điển vẫn tồn tại, nhưng có hạn chế riêng khi kết hợp pattern variables để tránh các đường điều khiển dùng biến chưa khớp. Đối với bài tập pattern switch, `->` là cách viết dễ theo dõi hơn.

Điểm chung là **selector expression được đánh giá trước**, sau đó mới chọn một nhánh phù hợp. Việc chọn statement hay expression không thay đổi ý nghĩa của selector.

## 10. Lỗi thường gặp khi viết selector expression

| Nhầm lẫn | Cách hiểu và sửa đúng |
| --- | --- |
| Nghĩ `case String s` là selector. | Selector là biểu thức sau `switch`; `case String s` là nhãn pattern so khớp với selector value. |
| Tưởng selector được tính lại cho từng `case`. | Selector expression được đánh giá một lần mỗi lượt thực thi switch; guard có thể chạy sau đó nhưng không tự gọi lại selector. |
| Nghĩ `Object value` không thể làm selector. | Java 21 pattern switch hỗ trợ selector kiểu tham chiếu `Object`, nên nhiều type patterns có thể được thử. |
| Nghĩ giá trị runtime thay đổi kiểu tĩnh của selector. | Kiểu tĩnh dùng để kiểm tra nhãn lúc biên dịch; giá trị runtime quyết định pattern nào khớp. |
| Đặt `case Number n` trước `case Integer i`. | Nhánh Number tổng quát bao phủ Integer, gây dominance cho nhánh sau; đặt nhánh chuyên biệt trước. |
| Tin rằng `default` sẽ nhận selector `null`. | `default` không thay `case null` trong pattern switch Java 21; có thể phát sinh NPE. |
| Chỉ viết `case String s` cho selector kiểu `Object`. | Enhanced switch còn trường hợp giá trị không phải String; cần bổ sung case khác hoặc default để exhaustiveness. |
| Dùng selector primitive `long`/`boolean` như `int` trong Java 21. | Java 21 ổn định không hỗ trợ các selector primitive này như dạng switch phổ biến; các phiên bản preview mới có mở rộng riêng. |
| Gọi phương thức có tác dụng phụ trong selector rồi mong nó chạy tại từng nhánh. | Tác dụng phụ của selector chỉ xảy ra khi tính biểu thức ban đầu; không nên phụ thuộc vào đánh giá lặp lại. |
| Nhầm pattern match với so sánh bằng `==`. | Type/record patterns kiểm tra kiểu, cấu trúc và điều kiện guard; không đơn thuần so sánh đối tượng với hằng số. |

Một lỗi thiết kế đáng chú ý là cố đưa mọi nghiệp vụ vào selector quá phức tạp:

```java
// Cú pháp minh họa; các hàm cần được khai báo trong chương trình thực tế.
return switch (load().transform().getValue()) {
    case String s -> s;
    default -> "other";
};
```

Nếu có nhiều bước có thể ném lỗi hoặc tạo tác dụng phụ, hãy cân nhắc tách chúng:

```java
// Cú pháp minh họa; kiểu của input phải là kiểu reference phù hợp.
Object input = loadValue();
return switch (input) {
    case String s -> s;
    default -> "other";
};
```

Việc tách biến giúp đặt breakpoint, ghi log có kiểm soát và phân biệt lỗi đánh giá selector với lỗi xử lý nhánh.

## 11. Bài tập tự kiểm tra

### Bài 1 — Selector nào được tính?

```java
static int calls;
static Object next() {
    calls++;
    return 7;
}

static String classify() {
    return switch (next()) {
        case String s -> "text";
        case Integer n -> "number:" + n;
        default -> "other";
    };
}
```

Nếu ban đầu `calls = 0`, gọi `classify()` một lần sẽ trả gì và `calls` bằng bao nhiêu?

**Đáp án:** trả `"number:7"`; `calls == 1`. Toàn bộ selector `next()` được tính một lần. Phần nhánh `Integer n` khớp vì `next()` trả một `Integer` được autobox từ số `7`.

### Bài 2 — Xử lý null

```java
static String format(Object data) {
    return switch (data) {
        case String s -> s;
        default -> "other";
    };
}
```

Gọi `format(null)` có trả `"other"` không?

**Đáp án:** không. Theo Java 21, selector `null` ở switch này gây `NullPointerException`. Nếu muốn trả `"missing"`, thêm nhánh `case null -> "missing";`.

### Bài 3 — Kiểu tĩnh ảnh hưởng đến các case

Tại sao switch trên `Object` có thể có `case String s` và `case Integer n`, nhưng không thể tùy ý đặt `case Integer n` trong một switch có selector kiểu tĩnh `String`?

**Đáp án:** selector kiểu `Object` có thể tham chiếu nhiều class khác nhau; kiểu tĩnh `String` không thể là `Integer` theo quan hệ kiểu Java. Compiler kiểm tra tương thích ở thời điểm biên dịch, trước khi có giá trị runtime.

### Bài 4 — Exhaustiveness với sealed hierarchy

Cho:

```java
sealed interface Action permits Create, Delete {}
record Create(String id) implements Action {}
record Delete(String id) implements Action {}
```

Hãy viết switch expression nhận `Action action` và trả chuỗi `"create:<id>"` hoặc `"delete:<id>"`.

**Lời giải** (trong ngữ cảnh có các khai báo record):

```java
static String describeAction(Action action) {
    return switch (action) {
        case Create(String id) -> "create:" + id;
        case Delete(String id) -> "delete:" + id;
    };
}
```

Hai record patterns bao phủ toàn bộ subtype trực tiếp được sealed interface cho phép. Với `action == null`, switch vẫn ném `NullPointerException` nếu không bổ sung `case null`.

## 12. Ghi nhớ

**Selector expression là biểu thức nằm trong `switch (...)`; nó được đánh giá một lần để lấy giá trị lựa chọn nhánh.** Kiểu tĩnh của selector xác định những pattern phù hợp và ảnh hưởng đến kiểm tra exhaustiveness lúc biên dịch; giá trị runtime cùng các guard xác định nhánh thực thi.

Ở Java 21, pattern switch hỗ trợ selector là các kiểu tham chiếu rộng như `Object`, interface, record và sealed hierarchy. Cần xử lý `null` có chủ đích bằng `case null` nếu nghiệp vụ cho phép. Đặt các pattern cụ thể đúng thứ tự để tránh dominance, và bảo đảm các nhánh bao phủ đủ giá trị của selector.

Tài liệu đối chiếu:
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java SE 21 Language Specification — Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 Language Specification — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
