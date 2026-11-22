# Arrow expression và hiệu ứng phụ khi kết hợp patterns (Java 21+)

## 1. Arrow rule trong pattern matching là gì?

Trong Java, nhãn `case Pattern -> ...` là một **switch rule** dùng ký hiệu mũi tên `->`. Khi kết hợp với **switch expression**, mỗi nhánh được chọn tạo ra giá trị (hoặc ném ngoại lệ). Khi kết hợp với **switch statement**, nhánh được chọn thực thi hành động mà không cần tạo giá trị trả về cho toàn bộ `switch`.

Ví dụ có pattern và guard:

```java
record Order(String category, int amount) {}

static String classify(Object value) {
    return switch (value) {
        case Order(var category, int amount) when amount >= 100 ->
                "Large: " + category;
        case Order(var category, int amount) ->
                "Normal: " + category;
        case String s -> "Text: " + s;
        case null -> "Missing";
        default -> "Other";
    };
}
```

Trong ví dụ:

- `Order(var category, int amount)` là **record pattern**: kiểm tra record và trích xuất hai thành phần.
- `when amount >= 100` là **guard**: kiểm tra điều kiện phụ sau khi record pattern khớp.
- `->` mở phần thân của switch rule. Nhánh đầu trả chuỗi bắt đầu bằng `Large`, nhánh hai trả chuỗi `Normal`.
- `case null` xử lý null của selector; `default` xử lý những giá trị còn lại.

Ký hiệu `->` ở đây **khác lambda** (`x -> x + 1`). Hai cú pháp có biểu tượng giống nhau nhưng thuộc hai cơ chế ngôn ngữ khác nhau.

**Hiệu ứng phụ (side effect)** là thay đổi trạng thái có thể quan sát ngoài giá trị biểu thức, chẳng hạn ghi log, thay đổi biến hoặc collection, cập nhật cơ sở dữ liệu, gửi sự kiện, gọi I/O. Trong `switch` dùng pattern, side effect có thể xuất hiện khi đánh giá **selector**, gọi **record accessor**, xét **guard** hoặc thực thi **thân nhánh arrow**. Bài học tập trung vào thứ tự thực thi và cách hạn chế các tác động ngoài ý muốn.

**Phiên bản:** Switch expressions đã chính thức từ Java 14. Pattern matching for `switch` (JEP 441) và record patterns (JEP 440) được chuẩn hóa trong **Java 21**; tất cả ví dụ tích hợp `when`/record patterns dưới đây dùng JDK 21+ và không cần `--enable-preview`.

## 2. Thứ tự đánh giá selector, pattern, guard, arrow

Xét một switch expression:

```java
String result = switch (source()) {
    case Order(String name, int amount)
            when eligible(name, amount) ->
            processLarge(name);

    case Order(String name, int amount) ->
            processRegular(name);

    default -> "Other";
};
```

Mô tả luồng xử lý (các hàm `source`, `eligible` và `processLarge`/`processRegular` là minh họa giả định):

1. Java đánh giá **selector `source()` đúng một lần** cho một lần chạy của `switch`. Nếu `source()` tăng biến đếm hoặc ghi log, tác động này xảy ra trước khi tìm nhánh.
2. Các nhãn pattern được kiểm tra để tìm nhánh phù hợp. Record patterns có thể gọi accessor của record để trích xuất component. Phần này không đồng nghĩa toàn bộ quá trình khớp là không có side effect.
3. Nếu pattern của một nhánh có `when` khớp, Java đánh giá guard. Guard trả `false` sẽ khiến nhánh đó không được chọn và việc tìm nhánh phù hợp tiếp tục. **Side effect đã xảy ra trong guard không được tự hoàn tác.**
4. Chỉ phần thân `->` của nhánh được chọn mới chạy. Không có **fall-through** từ nhánh arrow này sang nhánh arrow khác.
5. Với switch expression, kết quả được lấy từ biểu thức ở nhánh, `yield` của block, hoặc quá trình kết thúc bằng ngoại lệ.

Lưu ý quan trọng: **“selector được đánh giá một lần” không có nghĩa mọi accessor/guard được gọi đúng một lần**. Trong quá trình thử nhiều pattern, accessor record tùy biến có thể được gọi trong các phép khớp khác nhau. Không viết nghiệp vụ phụ thuộc số lần accessor được gọi.

## 3. Chương trình chạy được: ghi dấu thứ tự side effects

Lưu đoạn mã sau vào file **`ArrowPatternEffectsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ArrowPatternEffectsDemo {
    record Order(String category, int amount) {}

    static int sourceCalls;

    static Object source(Object input) {
        sourceCalls++;
        return input;
    }

    static boolean premium(
            String category, int amount, List<String> trace) {
        trace.add("guard(" + category + "," + amount + ")");
        return amount >= 100;
    }

    static String arm(String value, List<String> trace) {
        trace.add("arm(" + value + ")");
        return value;
    }

    static String categorize(Object input, List<String> trace) {
        return switch (source(input)) {
            case Order(String category, int amount)
                    when premium(category, amount, trace) ->
                    arm("priority:" + category, trace);

            case Order(String category, int amount) -> {
                trace.add("block(" + category + ")");
                yield "regular:" + category + ":" + amount;
            }

            case String text -> arm("text:" + text, trace);
            case null -> arm("null", trace);
            default -> arm("other", trace);
        };
    }

    static void show(Object input) {
        sourceCalls = 0;
        List<String> trace = new ArrayList<>();
        String result = categorize(input, trace);

        System.out.println(
                result + " | source=" + sourceCalls
                        + " | trace=" + trace);
    }

    static void statement(Object input) {
        List<String> steps = new ArrayList<>();

        // Switch statement: nhánh thực thi hành động.
        switch (input) {
            case Order(var kind, int amount)
                    when amount >= 100 ->
                    steps.add("large:" + kind);

            case Order(var kind, int amount) ->
                    steps.add("small:" + kind);

            case null -> steps.add("missing");
            default -> steps.add("unknown");
        }

        System.out.println("statement: " + steps);
    }

    public static void main(String[] args) {
        show(new Order("book", 150));
        show(new Order("book", 20));
        show("hi");
        show(null);
        show(17);
        statement(new Order("pen", 3));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 ArrowPatternEffectsDemo.java
java ArrowPatternEffectsDemo
```

Stdout:

```text
priority:book | source=1 | trace=[guard(book,150), arm(priority:book)]
regular:book:20 | source=1 | trace=[guard(book,20), block(book)]
text:hi | source=1 | trace=[arm(text:hi)]
null | source=1 | trace=[arm(null)]
other | source=1 | trace=[arm(other)]
statement: [small:pen]
```

Phân tích:

1. Với `new Order("book", 150)`, `source` tăng bộ đếm lên 1; pattern `Order(...)` khớp và guard `premium` chạy, ghi `guard(book,150)`; do guard đúng, `arm` chạy và ghi `arm(priority:book)`. Nhánh `Order` thứ hai không chạy.
2. Với `new Order("book", 20)`, guard vẫn ghi `guard(book,20)` **dù trả false**. Java chuyển sang nhánh `Order` không guard, ghi `block(book)` rồi dùng `yield` tạo giá trị `regular:book:20`.
3. Với `"hi"`, `null` và `17`, pattern `Order` không khớp nên hàm `premium` không được gọi. Mỗi giá trị chọn nhánh `String`, `null` hoặc `default` tương ứng.
4. Trong `statement`, `steps.add(...)` là hành động của switch statement. Chương trình không lấy giá trị từ toàn bộ `switch`; đối tượng `List` thay đổi vì đúng một nhánh chạy.

Biến `sourceCalls` chỉ có mục đích minh họa. Đây là trạng thái `static` dùng chung, không có bảo vệ đồng thời; với mã nhiều luồng, không dùng cách đếm này như một bộ đo thread-safe.

## 4. Ba dạng thân arrow rule quan trọng

### 4.1. Trả giá trị trực tiếp từ switch expression

```java
String description = switch (input) {
    case String s -> s.toUpperCase();
    case Integer n -> "Number: " + n;
    case null -> "Null";
    default -> "Other";
};
```

Biểu thức bên phải `->` của nhánh được chọn được đánh giá và tạo giá trị cho toàn bộ switch expression. Chỉ một nhánh được chọn, nên các biểu thức của những nhánh khác **không** chạy.

Một lời gọi phương thức ở đây có thể có side effect. Ví dụ, `case String s -> logAndFormat(s)` sẽ vừa ghi log vừa trả chuỗi nếu `logAndFormat` được thiết kế làm cả hai việc. Đừng giả định nhánh tạo giá trị là nhánh thuần túy.

### 4.2. Nhiều lệnh trong block: dùng `yield`

```java
int[] counter = {0};

String label = switch (input) {
    case String s -> {
        counter[0]++;           // Side effect.
        String result = s.strip();
        yield "Text: " + result;
    }
    case null -> "Missing";
    default -> "Other";
};
```

Một nhánh `-> { ... }` của **switch expression** cần `yield expression;` nếu nó hoàn thành bình thường với một kết quả. `yield` tạo ra giá trị cho `switch`, không phải `return` khỏi phương thức chứa `switch`.

Sai về ý tưởng:

```java
// KHÔNG BIÊN DỊCH: block của switch expression hoàn thành
// mà không tạo giá trị.
// String label = switch (input) {
//     case String s -> {
//         counter[0]++;
//     }
//     default -> "Other";
// };
```

Nếu nhánh cần kết thúc bằng ngoại lệ thì dùng `throw` thay vì trả giá trị:

```java
int normalized = switch (input) {
    case Integer n when n >= 0 -> n;
    case Integer n ->
            throw new IllegalArgumentException("Negative: " + n);
    case null -> 0;
    default -> 0;
};
```

Khi nhánh `throw` chạy, switch expression không tạo giá trị `normalized`; ngoại lệ truyền ra ngoài.

### 4.3. Arrow rule trong switch statement

```java
switch (input) {
    case String s -> System.out.println("Text: " + s);
    case Integer n -> System.out.println("Number: " + n);
    case null -> System.out.println("Null");
    default -> System.out.println("Other");
}
```

Ở đây `switch` là **statement**, mục đích chạy lệnh. Những nhánh arrow rule có thể chứa một statement expression, block hoặc `throw`; không cần `yield` để tạo giá trị cho toàn bộ `switch`. Một nhánh chạy xong không rơi tiếp xuống nhánh kế tiếp (khác với lỗi quên `break` ở `case ...:` truyền thống).

## 5. Vì sao guard `when` có side effect dễ gây lỗi?

Guard có thể gọi bất kỳ biểu thức Boolean hợp lệ nào, kể cả phương thức ghi log, tăng counter hoặc sửa trạng thái:

```java
static boolean checked(int amount, List<String> trace) {
    trace.add("checked:" + amount);
    return amount > 0;
}

// Nhãn minh họa của một switch expression:
case Order(var category, int amount)
        when checked(amount, trace) ->
        "Accepted:" + category;
```

Nếu pattern khớp, `checked` chạy. Với `amount == 0`, nó thêm `checked:0` vào trace **trước khi** trả `false`. Nhánh phía sau có thể được chọn, nhưng trace đã thay đổi.

Hai guard khác nhau có thể cùng truy cập một trạng thái biến đổi. Nếu guard đầu tiên thay đổi trạng thái mà guard thứ hai dựa vào, thứ tự và kết quả phân loại trở nên khó đoán. Với ứng dụng nghiệp vụ, nên cố gắng giữ các guard **thuần túy**: chỉ đọc dữ liệu và trả `true/false`. Đưa những thao tác cập nhật trạng thái vào thân nhánh đã được chọn hoặc phương thức nghiệp vụ được gọi từ nhánh đó.

Ví dụ guard an toàn hơn với kiểm tra null:

```java
case Order(var category, int amount)
        when category != null
                && category.startsWith("VIP")
                && amount > 0 ->
        "VIP order";
```

`&&` đánh giá ngắn mạch từ trái sang phải. Nếu `category == null`, `startsWith` không được gọi. Nếu `Order(...)` không khớp, toàn bộ guard không chạy.

**Ngoại lệ trong guard không phải “guard false”.** Nếu phương thức `checked` ném ngoại lệ, Java truyền ngoại lệ ra ngoài, không âm thầm tiếp tục nhánh dự phòng.

## 6. Đặt side effect ở đâu?

Nhánh của switch expression có thể vừa gọi phương thức gây side effect vừa tạo giá trị, nhưng cần xác định rõ tính nhất quán khi có lỗi.

Ví dụ mã **minh họa (không độc lập)**:

```java
case Order(var category, int amount) -> {
    charge(amount);             // Giả sử đã trừ tiền.
    yield createReceipt();      // Giả sử có thể ném lỗi.
}
```

`charge` và `createReceipt` là những phương thức giả định, không nằm trong chương trình demo. Nếu `charge` đã cập nhật hệ thống còn `createReceipt` ném ngoại lệ, Java **không tự rollback** việc trừ tiền chỉ vì toàn bộ `switch` chưa trả kết quả. Arrow rule không tự tạo transaction, idempotency hay cơ chế retry an toàn.

Lựa chọn thực tế:

- **Biểu thức phân loại/biến đổi dữ liệu:** dùng switch expression, ưu tiên thân nhánh tính ra kết quả một cách thuần túy.
- **Các tác vụ có side effect là mục tiêu chính:** dùng switch statement hoặc chuyển thao tác sang phương thức nghiệp vụ riêng như `processOrder(order)`.
- **Vừa xử lý vừa trả kết quả:** có thể dùng block `-> { ... yield result; }`; định nghĩa rõ transaction, rollback/compensation, xử lý ngoại lệ và việc gọi lại có an toàn không.
- **Quan sát/logging:** xác định cần log lúc kiểm tra guard hay chỉ khi nhánh được chọn; hai thời điểm có ý nghĩa khác nhau.

## 7. Phạm vi pattern variable và short-circuit ngoài switch

Trong nhánh:

```java
case Order(String category, int amount)
        when amount >= 100 ->
        category + ":" + amount;
```

`category` và `amount` được ràng buộc khi pattern thành công, nên có thể dùng trong guard và thân nhánh. Chúng không tự động tồn tại ngoài `switch` hoặc trong nhánh `case` khác.

Với `instanceof`, không dùng `when`; thay bằng `&&`:

```java
boolean eligible = input instanceof Order(var category, int amount)
        && category != null
        && amount >= 100;
```

Điều kiện sau `&&` được đánh giá khi các điều kiện trước đã đúng. Compiler biết `category` và `amount` đã được ràng buộc nếu `instanceof` trả true.

Có thể kết hợp pattern với toán tử ba ngôi:

```java
String category = input instanceof Order(var kind, int amount)
        ? kind
        : "unknown";
```

Ở nhánh đúng của `?:`, biến `kind` có phạm vi hợp lệ. Nhánh sai không được phụ thuộc vào biến đó.

Ví dụ sai (mã minh họa không biên dịch):

```java
// if (input instanceof Order(var kind, int amount) || amount > 0) {
//     System.out.println(kind);
// }
```

Khi vế trái của `||` sai thì vế phải được đánh giá nhưng biến pattern chưa được ràng buộc. Vì vậy compiler không cho dùng `amount` ở vị trí ấy.

## 8. Null, record accessor và những tác động ít thấy

### Null của selector và null của component

- Selector `null` không khớp record pattern; xử lý bằng `case null` nếu cần.
- Trong pattern matching switch, `default` không thay thế một nhánh xử lý null một cách tổng quát. Nếu không có nhãn xử lý phù hợp, selector null có thể gây `NullPointerException`.
- Một record có thể chứa component null, ví dụ `new Order(null, 10)`. Với component `String`, pattern con `String category` trong record pattern có thể là *unconditional* cho kiểu thành phần và ràng buộc cả null. Guard gọi `category.length()` vì thế phải kiểm tra null khi cần.
- Với nested record pattern, nếu **chính record con** là null, pattern record con không khớp và guard của nhánh đó không chạy. Cần nhánh bao phủ trường hợp ấy.

### Record accessor có thể được tùy biến

Java cho phép record khai báo accessor rõ ràng:

```java
record Token(String value) {
    @Override
    public String value() {
        System.out.println("accessor invoked");
        return value;
    }
}
```

Khi xử lý `case Token(var text) -> ...`, Java có thể gọi `value()` để trích xuất component trước khi đánh giá guard hay thân arrow. Bởi vậy, **việc kiểm tra pattern không nhất thiết hoàn toàn không có side effect**. Accessor tùy biến có thể ghi log hoặc ném ngoại lệ; khi ngoại lệ phát sinh, đó không đơn thuần là “pattern không khớp”.

Thiết kế tốt là giữ accessor đơn giản, nhất quán với dữ liệu của record và tránh phụ thuộc số lần accessor được gọi trong một phép pattern matching.

## 9. Exhaustiveness, thứ tự nhánh và domination

Một **switch expression** phải bao phủ các trường hợp thích hợp của selector. Với `Object`, thường cần `default`. Với sealed hierarchy, compiler có thể xác định các nhánh đã bao phủ mọi subtype được phép, nhưng một `case Pattern when điềuKiện` thường chỉ xử lý **một phần** giá trị của kiểu đó.

Thứ tự đúng:

```java
return switch (input) {
    case Order(var category, int amount) when amount >= 100 ->
            "large";
    case Order(var category, int amount) ->
            "regular";
    case null -> "null";
    default -> "other";
};
```

Nếu đặt nhánh `Order(...)` **không guard** lên trước, nó sẽ bao phủ các `Order` có amount lớn, khiến nhánh có guard ở phía sau bị **dominated**; compiler có thể từ chối. Nên đặt điều kiện cụ thể trước, nhánh bao phủ còn lại sau.

Mặt khác, một guard `when amount >= 100` không làm cho switch xử lý mọi `Order`, bởi `Order(..., 20)` vẫn có thể xuất hiện. Luôn có nhánh phù hợp cho những trường hợp không qua guard.

## 10. Lỗi thường gặp và cách khắc phục

1. **Nhầm arrow rule với lambda.** `case Pattern -> expression` là nhánh switch, còn `x -> x + 1` là lambda.
2. **Tin rằng chỉ thân arrow mới có side effect.** Selector, record accessor và guard có thể có tác động trước khi chọn nhánh.
3. **Cho rằng guard false sẽ rollback trạng thái.** Side effect trong guard vẫn tồn tại; ưu tiên guard thuần túy.
4. **Thiếu `yield` ở block của switch expression.** Nếu nhánh hoàn thành bình thường và cần cung cấp kết quả, dùng `yield value;`.
5. **Dùng `return`/`break` như `yield`.** Chúng có nghĩa điều khiển khác; không thay thế việc tạo giá trị từ switch expression.
6. **Nhầm switch expression và switch statement.** Dạng expression tạo giá trị; dạng statement chạy hành động. Cả hai dùng arrow rule, nhưng cách tạo kết quả khác nhau.
7. **Giả định fall-through giữa các arrow rules.** Một nhánh `->` được chọn không tự chạy nhánh `->` tiếp theo.
8. **Đặt pattern tổng quát trước pattern chuyên biệt.** Có thể làm nhánh sau bị dominated hoặc không bao giờ đến được.
9. **Không kiểm tra null ở guard.** Component của record có thể null dù pattern đã khớp.
10. **Cho rằng việc trả về một giá trị là transaction.** Nếu một lời gọi trước `yield` đã sửa trạng thái rồi có lỗi, Java không tự hoàn tác thay đổi.
11. **Cho rằng guard được gọi cho mọi input.** Guard chỉ được đánh giá sau khi pattern nhãn `case` tương ứng khớp.
12. **Dùng biến pattern ở ngoài scope.** Biến được ràng buộc trong guard/thân nhánh phù hợp, không mặc định dùng được trong nhánh khác.

## 11. Checklist thiết kế

Khi kết hợp pattern, guard và arrow rules, hãy tự kiểm tra:

- Selector có side effect không, và có cần tách việc lấy dữ liệu ra một biến cục bộ trước `switch` không?
- Guard có chỉ làm kiểm tra Boolean, không sửa trạng thái không? Nếu có side effect, việc guard trả false đã được tính đến chưa?
- Phần thân nhánh có trách nhiệm trả giá trị hay thực hiện hành động? `yield`/`throw` có đúng không?
- Các nhánh đã sắp xếp từ cụ thể đến tổng quát, tránh domination và bảo đảm tính exhaustive chưa?
- Null của selector, null của component và ngoại lệ do accessor/guard có được xử lý phù hợp không?
- Nếu có I/O hoặc cập nhật bên ngoài, việc xử lý lỗi và tính nguyên tử có được bảo đảm ở tầng nghiệp vụ không?

**Ghi nhớ:** Pattern xác định **cấu trúc khớp**; `when` lọc thêm **điều kiện giá trị**; `->` thực thi **thân một nhánh được chọn**. Hiệu ứng phụ có thể xảy ra trong cả ba giai đoạn kiểm tra đầu vào, đánh giá guard và chạy nhánh. Giữ guard và accessor đơn giản, dùng arrow expression cho biến đổi dữ liệu rõ ràng, đặt các cập nhật trạng thái vào nơi có trách nhiệm xử lý lỗi.

### Tài liệu tham khảo

- JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java 21 — Switch Expressions: https://docs.oracle.com/en/java/javase/21/language/switch-expressions.html
