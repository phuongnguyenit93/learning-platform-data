# Pattern không thể xảy ra: compiler và type checking trong Java 21+

## 1. “Pattern không thể xảy ra” nghĩa là gì?

Pattern matching trong Java dùng một mẫu (*pattern*) để kiểm tra một giá trị có hình dạng hoặc kiểu phù hợp rồi, khi khớp, tạo các **biến mẫu** (*pattern variables*). Với type pattern, ta viết `value instanceof Integer number`; với record pattern (Java 21+), ta có thể phân rã các component: `value instanceof Point(int x, int y)`.

Không phải mọi pattern đều có khả năng khớp với kiểu dữ liệu đang xét. Đặc biệt, cần phân biệt **ba hiện tượng**:

1. **Bất khả thi theo kiểu tĩnh (*statically inapplicable*)**: compiler biết từ các kiểu đã khai báo rằng giá trị không thể khớp mẫu. Đây là **lỗi biên dịch**.
2. **Bị che khuất (*dominated*) trong `switch`**: một nhánh `case` trước đã bao phủ trường hợp mà nhánh sau có thể nhận. Nhánh sau không thể được chọn và bị compiler từ chối. Đây là lỗi về **thứ tự/khả năng đến được nhánh**, không nhất thiết vì kiểu của mẫu vốn bất khả thi.
3. **Hợp lệ khi biên dịch nhưng không khớp lúc chạy**: kiểu tĩnh vẫn cho phép một giá trị phù hợp, chỉ có **giá trị thực tế** hiện tại là không phù hợp. Java không báo lỗi biên dịch; biểu thức `instanceof` trả về `false`.

Ngoài ra còn có **ràng buộc nghiệp vụ** (ví dụ một giá trị luôn dương theo quy ước ứng dụng) mà compiler không nhất thiết biết. Không nên gọi mọi điều kiện thất bại là “pattern không thể xảy ra” theo nghĩa kiểm tra kiểu của Java.

Bài này dùng cú pháp **Java 21+**, trong đó type pattern với `instanceof` và `switch`, record pattern và `sealed` hierarchy đều có thể sử dụng mà không bật preview.

## 2. Compiler phát hiện kiểu pattern không thể tương thích

### 2.1. Hai kiểu lớp không thể chuyển đổi

~~~java
String known = "abc";

// CỐ Ý KHÔNG BIÊN DỊCH:
if (known instanceof Integer number) {
    System.out.println(number);
}
~~~

Kiểu tĩnh của `known` là `String`. `String` và `Integer` là hai lớp không có quan hệ kế thừa phù hợp để giá trị kiểu `String` có thể là một `Integer`. Vì vậy compiler từ chối biểu thức `instanceof Integer number` trước khi chương trình được chạy.

Đây **không** phải là một phép so khớp hợp lệ luôn trả về `false`: bản thân mã đã không thể biên dịch.

Ngược lại:

~~~java
Object unknown = "abc";
System.out.println(unknown instanceof Integer number); // false
~~~

Đoạn này **biên dịch và chạy được**. Kiểu tĩnh `Object` có thể chứa một `Integer`, dù giá trị thực tế đang được lưu là `String`. Compiler chỉ nhìn thấy khả năng chuyển đổi hợp lệ theo kiểu tĩnh; việc không khớp được xác định **ở runtime**.

So sánh:

| Kiểu tĩnh của biểu thức | Mẫu | Kết quả |
| --- | --- | --- |
| `String` | `Integer n` | Lỗi biên dịch: kiểu không tương thích |
| `Object` | `Integer n` | Hợp lệ; khớp hoặc không tùy giá trị runtime |
| `Number` | `Integer n` | Hợp lệ vì `Integer` là kiểu con của `Number` |
| `Object` có giá trị `null` | `String s` | Hợp lệ khi biên dịch; `instanceof` trả `false` |
| `Object` có giá trị `"abc"` | `String s` | Hợp lệ, khớp và `s` nhận `"abc"` |

Điều quan trọng: **compiler không cần chạy mã để loại bỏ một mẫu có kiểu tĩnh không tương thích**. Nhưng một mẫu có thể hợp lệ về kiểu mà vẫn không khớp trong dữ liệu thực tế.

### 2.2. Không nên xem “không cần thiết” là “bất khả thi”

Một mẫu có thể dư thừa về mặt ý nghĩa nhưng vẫn hợp lệ. Chẳng hạn:

~~~java
String text = "hello";

if (text instanceof String sameText) {
    System.out.println(sameText.toUpperCase());
}
~~~

Đoạn trên vẫn hợp lệ: `text` có thể là `null` ở trường hợp tổng quát, nên `instanceof` còn kiểm tra việc giá trị khác `null`. Đừng suy đoán rằng compiler sẽ từ chối mọi pattern “hiển nhiên sẽ khớp”.

## 3. Record pattern: kiểm tra từng component ở thời điểm biên dịch

Record pattern giúp phân rã dữ liệu:

~~~java
record Fixed(String value) {}
record Flexible(Object value) {}
~~~

Khi compiler nhìn thấy:

~~~java
Object input = new Fixed("abc");

// CỐ Ý KHÔNG BIÊN DỊCH:
if (input instanceof Fixed(Integer number)) {
    System.out.println(number);
}
~~~

Kiểu của component `value` trong `Fixed` đã được khai báo là `String`. Pattern con `Integer number` không phù hợp với `String`, nên toàn bộ `Fixed(Integer number)` bị từ chối **ngay lúc biên dịch**, dù biểu thức đầu vào có kiểu `Object`.

So sánh với record có component `Object`:

~~~java
Object first = new Flexible("abc");
Object second = new Flexible(42);

System.out.println(first instanceof Flexible(Integer n));  // false
System.out.println(second instanceof Flexible(Integer n)); // true
~~~

Trong `Flexible`, compiler chỉ biết component là `Object`; giá trị thực tế có thể là `Integer` nên pattern con `Integer n` là hợp lệ. Sau đó, Java mới kiểm tra component ở runtime.

**Quy tắc cần nhớ:** Với record pattern, phải xét **kiểu được khai báo cho từng component** sau khi suy luận kiểu generic (nếu có), không chỉ xét kiểu của biến đầu vào. Một mẫu ngoài có vẻ hợp lệ vẫn có thể sai vì **mẫu con bất khả thi**.

### Pattern lồng nhau và khả năng khớp

~~~java
record Item(String name) {}
record Parcel(Item item) {}

Object input = new Parcel(new Item("book"));

if (input instanceof Parcel(Item(String name))) {
    System.out.println(name); // book
}
~~~

Đây là **đoạn minh họa**, giả sử các khai báo record ở phạm vi phù hợp. Mỗi tầng của mẫu phải được kiểm tra về kiểu và khả năng khớp. Nếu một component khai báo `String` mà mẫu con lại đòi `Integer`, compiler phát hiện lỗi tại tầng đó. Nếu kiểu cho phép khớp nhưng dữ liệu thực tế không phù hợp, pattern thất bại lúc chạy.

## 4. Phân cấp sealed giúp giới hạn những kiểu có thể xuất hiện

Giả sử có một phân cấp đóng:

~~~java
sealed interface Signal permits TextSignal, CodeSignal {}

record TextSignal(String text) implements Signal {}
record CodeSignal(int code) implements Signal {}
~~~

Cả `TextSignal` và `CodeSignal` đều triển khai `Signal`. Chúng là các kiểu được khai báo trong `permits` của phân cấp này. Vì `String` không phải kiểu được phép thuộc phân cấp `Signal`, đoạn sau bị compiler từ chối:

~~~java
Signal signal = new TextSignal("ok");

// CỐ Ý KHÔNG BIÊN DỊCH:
if (signal instanceof String s) {
    System.out.println(s);
}
~~~

Lỗi này xuất phát từ **quan hệ kiểu không tương thích**, không phải vì ở runtime `signal` đang chứa `TextSignal`. Từ kiểu tĩnh `Signal` và các ràng buộc của phân cấp, compiler có thể kết luận một `String` không phải là một `Signal` hợp lệ.

Phân cấp `sealed` còn giúp `switch` kiểm tra tính bao phủ:

~~~java
static String label(Signal value) {
    return switch (value) {
        case TextSignal t -> "text:" + t.text();
        case CodeSignal c -> "code:" + c.code();
        case null -> "null";
    };
}
~~~

Đây là **phương thức minh họa** nằm trong lớp có khai báo `Signal` và hai record ở trên. Hai nhánh pattern bao phủ mọi kiểu triển khai được phép trong phân cấp này; `case null` xử lý selector `null`. Không cần nhánh `default` cho các subtype khác trong phiên bản phân cấp đã khai báo.

Nếu sau này mở rộng `permits` bằng một subtype mới, hãy kiểm tra lại `switch`: trình biên dịch có thể yêu cầu bổ sung nhánh xử lý để biểu thức vẫn bao phủ đủ các trường hợp.

**Giới hạn quan trọng:** compiler kiểm tra **các kiểu mà ngôn ngữ và khai báo cho phép**. Nó không tự chứng minh các giả định nghiệp vụ như “hệ thống sẽ không bao giờ phát sinh loại tín hiệu này” nếu điều đó không được biểu diễn bằng hệ thống kiểu.

## 5. `switch`: nhánh bị dominated không có cơ hội chạy

Một lỗi khác hay bị gọi nhầm là “pattern không thể xảy ra” là nhánh nằm **sau một mẫu bao quát hơn**.

~~~java
Object value = 42;

// CỐ Ý KHÔNG BIÊN DỊCH: case Integer bị case Number che khuất.
String description = switch (value) {
    case Number n -> "number";
    case Integer i -> "integer";
    default -> "other";
};
~~~

Ở đây `Integer` hoàn toàn có thể là một giá trị hợp lệ của `Object`. Tuy nhiên, bất kỳ `Integer` nào cũng là một `Number`; nhánh `case Number n` đứng trước sẽ nhận nó. Vì vậy `case Integer i` không thể được chọn và compiler báo **dominated case label**.

Cách sửa là sắp xếp từ **cụ thể đến tổng quát**:

~~~java
Object value = 42;

String description = switch (value) {
    case Integer i -> "integer";
    case Number n -> "number";
    default -> "other";
};

System.out.println(description); // integer
~~~

Đừng nhầm ba tình huống:

- **`String known instanceof Integer i`**: pattern bị từ chối vì **không tương thích kiểu tĩnh**.
- **`Object value` với `case Number` rồi `case Integer`**: nhánh `Integer` **bị che khuất** vì thứ tự.
- **`Object value = "abc"` với `instanceof Integer i`**: pattern **hợp lệ**, nhưng không khớp giá trị hiện tại.

Nếu `case` có guard `when`, khả năng dominated còn phụ thuộc quy tắc lựa chọn nhánh và guard tương ứng. Không nên suy luận đơn giản rằng cứ trùng kiểu là compiler sẽ báo lỗi; hãy kiểm tra trường hợp cụ thể bằng trình biên dịch.

## 6. `null`: “không thể khớp” phụ thuộc vị trí pattern

Với type pattern tại `instanceof`:

~~~java
String value = null;
System.out.println(value instanceof String text); // false
~~~

Giá trị `null` không khớp phép `instanceof` trực tiếp. Tuy nhiên, **record pattern có một chi tiết khác**: một **component pattern unconditional** (mẫu bao phủ toàn bộ các giá trị thuộc kiểu tĩnh của component) có thể khớp cả component `null`. Vì thế, không được nói rằng **mọi type pattern lồng bên trong record đều từ chối `null`**.

So sánh hai record:

~~~java
record Strict(String value) {}
record Broad(Object value) {}

Object a = new Strict(null);
Object b = new Broad(null);

System.out.println(a instanceof Strict(String text)); // true
System.out.println(b instanceof Broad(String text));  // false
~~~

Tại `Strict(String text)`, component đã có kiểu tĩnh `String`; `String text` là pattern unconditional đối với component ấy và có thể nhận `null`. Với `Broad(Object value)`, mẫu `String text` phải **kiểm tra kiểu của giá trị component** tại runtime; component `null` không khớp mẫu có điều kiện đó.

Đây là điểm dễ dẫn tới `NullPointerException` khi lập trình viên giả định sai:

~~~java
Object input = new Strict(null);

// CÓ THỂ NÉM NPE nếu bỏ kiểm tra text != null.
if (input instanceof Strict(String text) && !text.isBlank()) {
    System.out.println("valid");
}
~~~

Cách an toàn:

~~~java
if (input instanceof Strict(String text)
        && text != null
        && !text.isBlank()) {
    System.out.println("valid");
}
~~~

**Kết luận về null:** phải phân biệt phép `instanceof` tại ngoài cùng, mẫu component trong record và kiểu tĩnh của chính component. Kiểm tra giá trị `null` ở nơi cần gọi phương thức, thay vì dựa vào một quy tắc khái quát sai.

## 7. Generic type erasure là ràng buộc khác, không đồng nghĩa pattern bất khả thi

Với các kiểu generic, một cú pháp pattern có thể bị từ chối **vì không thể kiểm tra tham số kiểu một cách an toàn ở runtime**, dù kiểu đối tượng thực sự có thể tồn tại.

~~~java
Object input = java.util.List.of("a", "b");

// CỐ Ý KHÔNG BIÊN DỊCH từ biến Object:
// Runtime không thể kiểm tra an toàn toàn bộ List<String>.
if (input instanceof java.util.List<String> names) {
    System.out.println(names.size());
}
~~~

Cách kiểm tra hình dạng danh sách ở runtime:

~~~java
Object input = java.util.List.of("a", "b");

if (input instanceof java.util.List<?> items) {
    System.out.println(items.size()); // 2
}
~~~

`List<?>` kiểm tra rằng giá trị là một `List`, **không** chứng minh mọi phần tử đều có kiểu `String`. Nếu cần đảm bảo kiểu phần tử, kiểm tra từng giá trị khi duyệt.

Trường hợp này nên được ghi nhận là **hạn chế của kiểm tra generic/reifiability**, không phải kết luận rằng không một `List<String>` nào có thể xuất hiện. Phân biệt nguyên nhân lỗi giúp chọn cách sửa đúng thay vì ép kiểu không an toàn để tắt thông báo compiler.

## 8. Chương trình Java 21 hoàn chỉnh: kiểm thử phân biệt compile-time và runtime

Lưu toàn bộ mã sau thành tệp **`ImpossiblePatternDemo.java`**. Mã sử dụng phân cấp `sealed`, type pattern, record pattern và `switch`. Những đoạn **cố ý không biên dịch** ở các mục trước **không nằm trong chương trình** này.

~~~java
public class ImpossiblePatternDemo {
    sealed interface Signal permits TextSignal, CodeSignal {}
    record TextSignal(String text) implements Signal {}
    record CodeSignal(int code) implements Signal {}
    record Case(String name, Object input, String expected) {}

    static String inspect(Object value) {
        if (value instanceof TextSignal(String text)
                && text != null && !text.isBlank()) {
            return "valid:" + text;
        }
        if (value instanceof CodeSignal(int code)) {
            return "code:" + code;
        }
        return value == null ? "null" : "other";
    }

    static String label(Signal value) {
        return switch (value) {
            case TextSignal t -> "text:" + t.text();
            case CodeSignal c -> "code:" + c.code();
            case null -> "null";
        };
    }

    static void check(String name, String got, String expected) {
        if (!expected.equals(got)) {
            throw new AssertionError(
                    name + ": expected " + expected + ", got " + got);
        }
        System.out.println("PASS " + name + " -> " + got);
    }

    public static void main(String[] args) {
        Case[] cases = {
            new Case("text-ok", new TextSignal("ok"), "valid:ok"),
            new Case("text-blank", new TextSignal("   "), "other"),
            new Case("text-null", new TextSignal(null), "other"),
            new Case("code-record", new CodeSignal(7), "code:7"),
            new Case("plain-integer", 7, "other"),
            new Case("plain-string", "ok", "other"),
            new Case("input-null", null, "null")
        };

        for (Case test : cases) {
            check(test.name(), inspect(test.input()), test.expected());
        }

        check("sealed-text-null",
                label(new TextSignal(null)), "text:null");
        check("sealed-code", label(new CodeSignal(8)), "code:8");
        check("sealed-null", label(null), "null");

        Object uncertain = "hello";
        System.out.println(
                "Object-to-Integer=" + (uncertain instanceof Integer n));

        Object nestedNull = new TextSignal(null);
        if (nestedNull instanceof TextSignal(String text)) {
            System.out.println("nested-null-matched=" + (text == null));
        }

        System.out.println("ALL PASSED: 10");
    }
}
~~~

Biên dịch và chạy bằng JDK 21 trở lên:

~~~bash
javac --release 21 ImpossiblePatternDemo.java
java ImpossiblePatternDemo
~~~

**Kết quả mong đợi:**

~~~text
PASS text-ok -> valid:ok
PASS text-blank -> other
PASS text-null -> other
PASS code-record -> code:7
PASS plain-integer -> other
PASS plain-string -> other
PASS input-null -> null
PASS sealed-text-null -> text:null
PASS sealed-code -> code:8
PASS sealed-null -> null
Object-to-Integer=false
nested-null-matched=true
ALL PASSED: 10
~~~

### Những gì bài kiểm thử chứng minh

1. `TextSignal("ok")` với pattern `TextSignal(String text)` và guard hợp lệ được phân loại `"valid:ok"`.
2. `TextSignal(null)` không được chấp nhận làm dữ liệu văn bản hợp lệ vì **guard `text != null`**, chứ **không** phải vì bản thân component pattern `String text` chắc chắn thất bại.
3. `CodeSignal(7)` khớp record pattern `CodeSignal(int code)`.
4. Giá trị nguyên `7` và chuỗi `"ok"` trực tiếp không khớp hai mẫu record, dù biến tham số `inspect` có kiểu tĩnh `Object` khiến việc kiểm tra là hợp lệ.
5. `label` bao phủ hai subtype được phép của `Signal` và xử lý `null` selector; component `text == null` vẫn là một `TextSignal` hợp lệ cho type pattern `case TextSignal t`.
6. `Object-to-Integer=false` xác minh một mẫu **có thể xảy ra theo kiểu tĩnh** nhưng không khớp giá trị runtime.
7. `nested-null-matched=true` là phép thử cho trường hợp component pattern **unconditional** trong record được phép nhận `null`.

Hàm `check` ném `AssertionError` nếu một kỳ vọng sai. Vì thế, dòng `ALL PASSED: 10` chỉ xuất hiện sau khi cả mười phép kiểm tra kết quả chạy đều đạt. Các dòng kiểm tra bổ sung về `Object` và `null` được in sau đó để nhấn mạnh sự khác biệt với lỗi biên dịch.

## 9. Cách kiểm thử các trường hợp compiler phải từ chối

Một bộ kiểm thử runtime **không** thể kiểm chứng trực tiếp rằng chương trình cố ý sai phải bị compiler từ chối. Hãy tạo các tệp nhỏ **riêng biệt** để thử biên dịch âm (*negative compile tests*), không chèn mã đó vào chương trình chạy được ở mục 8.

Ví dụ tệp `ImpossibleType.java`:

~~~java
public class ImpossibleType {
    public static void main(String[] args) {
        String text = "abc";
        if (text instanceof Integer number) {
            System.out.println(number);
        }
    }
}
~~~

Dùng lệnh:

~~~bash
javac --release 21 ImpossibleType.java
~~~

**Kỳ vọng:** `javac` báo lỗi biên dịch vì `String` không thể chuyển thành `Integer`; tiến trình biên dịch thất bại. Không có stdout của một chương trình Java đã chạy ở ví dụ này.

Có thể thử theo cách tương tự với ba ví dụ lỗi ở trên:

- **Record component không tương thích:** `Fixed(String value)` nhưng dùng `Fixed(Integer n)`.
- **Kiểu bị loại bởi phân cấp:** giá trị có kiểu tĩnh `Signal` nhưng yêu cầu mẫu `String s`.
- **Nhánh `switch` bị che khuất:** `case Number n` xuất hiện trước `case Integer i`.

Hãy kiểm tra **nguyên nhân trong thông báo lỗi**, không chỉ mã thoát khác 0: lỗi cú pháp do chép thiếu dấu ngoặc không chứng minh compiler phát hiện pattern bất khả thi.

Nếu dùng hệ thống build, các ca biên dịch âm nên được chạy bằng một harness chuyên biệt và chấm “thất bại biên dịch đúng kỳ vọng” là **PASS**; không trộn chúng vào các nguồn Java chính của ứng dụng.

## 10. Checklist chẩn đoán khi compiler báo lỗi pattern

Khi gặp lỗi kiểu hoặc unreachable branch, làm lần lượt:

1. **Xác định kiểu tĩnh của selector/biểu thức.** Đó là `String`, `Object`, một interface, record generic, hay một kiểu `sealed`?
2. **Kiểm tra khả năng chuyển đổi giữa kiểu tĩnh và kiểu pattern.** Hai lớp final không tương thích thường không có đường khớp hợp lệ. Một biến kiểu `Object` rộng hơn và có thể cần kiểm tra runtime.
3. **Nếu là record pattern, xem từng component.** Kiểu của component khai báo có tương thích với mẫu con không? Với generic record, tham số kiểu được suy luận ra sao?
4. **Nếu là `switch`, đọc các nhánh từ trên xuống.** Nhánh rộng hơn có làm nhánh cụ thể phía sau bị dominated không? Có cần đảo thứ tự hay tách điều kiện `when`?
5. **Nếu liên quan generics, phân biệt lỗi không kiểm tra được type argument với kiểu thật sự bất khả thi.** `List<String>` không thể kiểm chứng tổng quát qua `instanceof` từ `Object` vì type erasure; `List<?>` chỉ kiểm tra kiểu danh sách.
6. **Thử cả `null` ở ngoài cùng và trong component.** Đừng giả định record component pattern unconditional luôn loại `null`.
7. **Viết test runtime cho những đường đi hợp lệ**, và test biên dịch âm cho các trường hợp compiler phải từ chối. Không thể thay thế hai loại test cho nhau.

## 11. Những nhầm lẫn cần tránh

**Nhầm 1 — compiler biết mọi giá trị runtime.** Java không suy ra rằng một `Object` chứa `"abc"` mãi mãi chỉ vì hiện tại nó được gán chuỗi. `instanceof Integer` từ kiểu tĩnh `Object` là biểu thức hợp lệ, thường trả `false` nếu giá trị không phù hợp.

**Nhầm 2 — mọi pattern không khớp đều là lỗi biên dịch.** Giá trị khác kiểu, thiếu dữ liệu, guard sai hoặc `null` có thể làm một pattern hợp lệ không khớp tại runtime. Lỗi biên dịch là khi quy tắc kiểu hoặc thứ tự nhánh không cho phép cách viết đó.

**Nhầm 3 — dominated `case` đồng nghĩa kiểu đích bất khả thi.** `Integer` hoàn toàn có thể xuất hiện; lỗi là `Number` đứng trước đã nhận tất cả `Integer`. Đổi thứ tự từ cụ thể đến tổng quát thường giải quyết được.

**Nhầm 4 — record pattern lúc nào cũng loại mọi component `null`.** Component pattern unconditional có thể nhận `null`; cần kiểm tra null khi thao tác trên biến tham chiếu.

**Nhầm 5 — ép kiểu để “lách” compiler là giải pháp đúng.** Ép kiểu qua `Object` hoặc raw type có thể khiến mã biên dịch được nhưng tăng rủi ro `ClassCastException` và làm mất bảo đảm kiểu. Nên sửa thiết kế kiểu và lựa chọn pattern đúng với dữ liệu.

**Nhầm 6 — compiler kiểm tra thay các quy tắc nghiệp vụ.** Các điều kiện như “số lượng luôn dương” hoặc “trạng thái này không bao giờ đi kèm loại dữ liệu kia” phải được biểu diễn bằng cấu trúc kiểu, validation hoặc test nghiệp vụ nếu muốn có bảo đảm tương ứng.

**Ghi nhớ:** Một pattern thực sự “không thể xảy ra” theo **kiểu tĩnh** thường bị Java từ chối ngay khi biên dịch. Một `case` bị **dominated** bị loại vì không thể được chọn sau nhánh rộng hơn. Còn pattern hợp lệ nhưng **không khớp runtime** chỉ phản ánh giá trị hiện tại. Phân biệt đúng ba hiện tượng này — và thận trọng với `null` trong record component — là nền tảng để viết pattern matching an toàn, có thể bảo trì trong Java 21+.