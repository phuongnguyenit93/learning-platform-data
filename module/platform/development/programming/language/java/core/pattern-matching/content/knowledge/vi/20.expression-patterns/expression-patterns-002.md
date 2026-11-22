# Pattern trong `switch expression` của Java

Một **`switch expression`** chọn nhánh dựa trên giá trị đầu vào **và tạo ra một giá trị kết quả**. Khi kết hợp với **pattern matching**, mỗi nhánh `case` có thể kiểm tra **kiểu**, **cấu trúc của record** và **điều kiện bổ sung** thay vì chỉ so sánh với các hằng số. Cách viết này phù hợp với các bài toán chuyển đổi dữ liệu, phân loại kết quả, dựng thông điệp, tính toán giá trị và xử lý những kiểu đối tượng khác nhau.

Bài này dùng cú pháp ổn định từ **Java 21**: **pattern matching for `switch`** (JEP 441) và **record patterns** (JEP 440). Các ví dụ chính biên dịch với `javac` trên JDK 21 trở lên, không cần `--enable-preview`.

## 1. Vì sao dùng pattern trong `switch expression`?

Trước Java 21, khi một biến có kiểu `Object` chứa nhiều kiểu giá trị, cách xử lý phổ biến là `if/else` kết hợp `instanceof`:

```java
// Trích đoạn minh họa, 'input' đã được khai báo là Object.
String result;
if (input instanceof String text) {
    result = "Văn bản: " + text;
} else if (input instanceof Integer number) {
    result = "Số: " + number;
} else {
    result = "Kiểu khác";
}
```

Với Java 21+, có thể viết trực tiếp một biểu thức:

```java
// Trích đoạn minh họa, 'input' đã được khai báo là Object.
String result = switch (input) {
    case String text -> "Văn bản: " + text;
    case Integer number -> "Số: " + number;
    case null -> "Không có dữ liệu";
    default -> "Kiểu khác";
};
```

Mỗi nhánh `case String text` hoặc `case Integer number` vừa **kiểm tra kiểu thực tế** của đối tượng, vừa **tạo pattern variable** (`text`, `number`) để dùng ngay trong kết quả. Kết quả của `switch` là một `String`, nên có thể gán vào `result` hoặc viết `return switch (...)` trong phương thức.

### Cấu trúc tổng quát

```java
// Mẫu cú pháp, không phải chương trình độc lập.
ResultType result = switch (selector) {
    case SomeType value when condition -> resultExpression;
    case AnotherType value -> otherResultExpression;
    case null -> nullResultExpression;
    default -> fallbackExpression;
};
```

Ý nghĩa:

- `selector`: biểu thức đầu vào được đánh giá trước khi lựa chọn nhánh.
- `case SomeType value`: **type pattern**; kiểm tra đối tượng có kiểu phù hợp và tạo biến `value`.
- `when condition`: **guard**; kiểm tra thêm điều kiện Boolean khi pattern đã khớp.
- `-> resultExpression`: biểu thức tạo giá trị cho nhánh; **không cần `break`**.
- `case null`: xử lý tường minh selector `null`, nếu nghiệp vụ cho phép.
- `default`: xử lý các giá trị còn lại khi các nhánh trên không bao phủ hết.

Dấu **`;` cuối cùng** kết thúc toàn bộ `switch expression` trong câu lệnh gán; không kết thúc từng nhánh `case ... ->` bằng dấu chấm phẩy riêng.

## 2. Type pattern trong `case`

Type pattern có dạng `case Type variableName -> ...`. Với `Object input`, ví dụ:

```java
// Trích đoạn minh họa.
String category = switch (input) {
    case String s -> "String dài " + s.length();
    case Integer n -> n >= 0 ? "Số không âm" : "Số âm";
    case Boolean flag -> flag ? "Đúng" : "Sai";
    case null -> "Không có giá trị";
    default -> "Đối tượng khác";
};
```

`String s`, `Integer n` và `Boolean flag` là các pattern khác nhau. Bên trong nhánh `String s`, Java đã xác nhận `input` khớp `String`, vì thế dùng `s.length()` mà không cần cast.

Điểm quan trọng về kiểu:

- Selector `Object` có thể chứa chuỗi, đối tượng `Integer`, `Boolean`, record hoặc bất kỳ đối tượng tham chiếu nào.
- `case Integer n` là pattern cho **kiểu bao `Integer`**. Với ví dụ Java 21 này, không thay bằng `case int n` cho selector kiểu `Object`; các đề xuất mở rộng primitive patterns thuộc phiên bản/tính năng khác.
- Type pattern `case String s` không khớp selector `null`. Nếu cần nhận `null`, dùng `case null`.
- Khi selector là `Object`, chỉ có vài nhánh `case` cụ thể thì `switch expression` thường cần `default` để bảo đảm có kết quả cho mọi kiểu khác.

### Kiểu của kết quả

Kiểu kết quả của các nhánh cần tương thích với ngữ cảnh sử dụng. Ví dụ:

```java
// Trích đoạn: trả về int, các nhánh đều tạo giá trị int.
int length = switch (input) {
    case String text -> text.length();
    case java.util.Collection<?> items -> items.size();
    case null -> 0;
    default -> -1;
};
```

Một nhánh trả về `String` trong biểu thức được dùng như `int` sẽ gây lỗi biên dịch. Không nên lẫn lộn **kiểu dữ liệu của selector** với **kiểu giá trị mà `switch expression` tạo ra**.

## 3. Guard `when`: phân biệt các trường hợp cùng kiểu

Một type pattern chỉ cho biết kiểu. Khi cần phân loại sâu hơn, gắn điều kiện Boolean bằng `when`:

```java
// Trích đoạn minh họa, 'input' có kiểu Object.
String answer = switch (input) {
    case Integer n when n > 0 -> "Dương";
    case Integer n when n < 0 -> "Âm";
    case Integer n -> "Bằng 0";
    case null -> "Thiếu số";
    default -> "Không phải Integer";
};
```

Quy trình cho `input = Integer.valueOf(-4)`:

1. Pattern `Integer n` ở nhánh đầu khớp về kiểu, nhưng guard `n > 0` là `false`, nên chưa chọn nhánh.
2. Nhánh thứ hai cũng khớp về kiểu và guard `n < 0` là `true`, nên kết quả là `"Âm"`.
3. Các nhánh sau không được chọn.

Khi `input = 0`, hai guard đầu đều sai và nhánh `case Integer n` cuối xử lý số 0. Vì thế, đặt nhánh **cụ thể/có điều kiện trước nhánh rộng** là một nguyên tắc quan trọng.

**Cú pháp chính thức trong Java 21 là `when`**, ví dụ `case String s when s.isBlank() -> ...`. Không viết guard bằng cú pháp cũ của những bản preview khi muốn chương trình chạy nhất quán trên Java 21+.

Pattern variable được tạo bởi `case` có thể dùng trong guard và trong biểu thức kết quả của chính nhánh đó. Guard không biến một pattern variable thành biến chung giữa các nhánh.

## 4. Record pattern trong `switch expression`

Record pattern kiểm tra đối tượng record và **phân rã từng component**. Với hai record:

```java
record Point(int x, int y) {}
record Move(String name, Point target) {}
```

Ví dụ phân loại một `Object` có thể viết:

```java
// Trích đoạn minh họa; 'input' là Object.
String label = switch (input) {
    case Point(var x, var y) when x == 0 && y == 0 ->
            "Gốc tọa độ";
    case Point(var x, var y) ->
            "Điểm (" + x + ", " + y + ")";
    case Move(var name, Point(var x, var y)) ->
            name + " tới (" + x + ", " + y + ")";
    case Move(var name, var target) ->
            name + ": không có điểm đích";
    case null -> "Không có dữ liệu";
    default -> "Đối tượng khác";
};
```

Đọc `case Point(var x, var y)`: selector phải là một `Point` khác `null`; component `x` và `y` được ràng buộc vào hai biến cùng tên, có kiểu `int`. Tên pattern variable được chọn theo vị trí component, không phải theo phương thức accessor, và có thể khác tên được khai báo trong record.

Đọc `case Move(var name, Point(var x, var y))`: trước hết selector phải là `Move`; component `target` tiếp tục phải là `Point` khác `null`; lúc đó lấy được `name`, `x`, `y`. Nếu `target == null`, nhánh lồng nhau này không khớp và chuyển sang nhánh `Move(var name, var target)`.

**Lưu ý:** `var target` có thể nhận `null` từ component tham chiếu; `Point(var x, var y)` thì không khớp `null` tại vị trí `target`. Đây là lý do có thể cần thêm nhánh xử lý dữ liệu không đầy đủ.

### Pattern variables được giới hạn theo nhánh

Trong `case Point(var x, var y) -> ...`, `x` và `y` chỉ có ý nghĩa trong nhánh mà pattern khớp (bao gồm guard nếu có). Những nhánh `case Point(var x, var y)` khác có thể khai báo lại tên `x`, `y` vì chúng có phạm vi độc lập. Không thể dùng `x` của một nhánh bất kỳ ở bên ngoài `switch` nếu không khai báo biến riêng và không truyền nó qua giá trị kết quả.

## 5. `switch expression` trả về kết quả bằng `->` và `yield`

Khi một nhánh chỉ cần một biểu thức, viết trực tiếp sau `->`:

```java
// Trích đoạn minh họa.
int score = switch (input) {
    case Integer n when n > 0 -> n * 2;
    case Integer n -> 0;
    case null -> 0;
    default -> -1;
};
```

Khi cần nhiều câu lệnh (tính tạm, log, kiểm tra), dùng **block** và `yield`:

```java
// Trích đoạn minh họa.
int score = switch (input) {
    case Integer n when n > 0 -> {
        int doubled = n * 2;
        yield doubled;
    }
    case Integer n -> 0;
    case null -> 0;
    default -> -1;
};
```

`yield doubled;` cung cấp **giá trị của nhánh** cho toàn bộ `switch expression`. `break` trong switch statement truyền thống chỉ thoát khỏi câu lệnh switch, không thay thế `yield` để trả về giá trị. Với cú pháp `case ... -> expression`, không cần viết `yield` vì biểu thức bên phải đã chính là kết quả nhánh.

| Khía cạnh | `switch statement` | `switch expression` |
| --- | --- | --- |
| Mục đích chính | Thực hiện lệnh theo nhánh | Tính một giá trị theo nhánh |
| Đưa kết quả ra ngoài | Thường gán vào biến, gọi phương thức hoặc `return` từ phương thức | Gán trực tiếp, `return switch (...)` hoặc lồng vào biểu thức khác |
| Block sau `->` | Chứa các câu lệnh | Phải cung cấp giá trị bằng `yield` nếu hoàn tất bình thường |
| Exhaustiveness | Không bắt buộc với mọi statement truyền thống | **Bắt buộc** để mọi giá trị có nhánh kết quả |
| `case ... ->` | Không fall-through | Không fall-through |

Trong `switch expression`, có thể có nhánh ném ngoại lệ thay vì tạo giá trị, ví dụ `default -> throw new IllegalArgumentException("Unsupported");`. Ngoại lệ đó làm biểu thức hoàn tất bất thường, không phải kết quả trả về.

## 6. Ví dụ Java 21+ hoàn chỉnh

Tạo tệp **`SwitchPatternExpressionDemo.java`**:

```java
public class SwitchPatternExpressionDemo {
    record Order(String customer, int itemCount, boolean paid) {}

    static String describe(Object value) {
        return switch (value) {
            case Order(var customer, var count, var paid)
                    when paid && count >= 3 ->
                    "Đơn lớn đã thanh toán: " + customer + " (" + count + ")";
            case Order(var customer, var count, var paid)
                    when !paid ->
                    "Đơn chưa thanh toán: " + customer;
            case Order(var customer, var count, var paid) ->
                    "Đơn đã thanh toán: " + customer + " (" + count + ")";
            case String text when text.isBlank() -> "Chuỗi trắng";
            case String text -> "Văn bản: " + text.trim();
            case Integer number when number > 0 -> "Số dương: " + number;
            case Integer number -> "Số khác: " + number;
            case null -> "Không có dữ liệu";
            default -> "Kiểu khác: " + value.getClass().getSimpleName();
        };
    }

    static int calculatePoints(Object value) {
        return switch (value) {
            case Order(var customer, var itemCount, var paid) -> {
                int validCount = Math.max(itemCount, 0);
                yield paid ? validCount * 10 : 0;
            }
            case Integer number -> number;
            case null -> 0;
            default -> -1;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Order("Mai", 3, true)));
        System.out.println(describe(new Order("Nam", 2, false)));
        System.out.println(describe(new Order("An", 1, true)));
        System.out.println(describe("   "));
        System.out.println(describe("  java  "));
        System.out.println(describe(5));
        System.out.println(describe(-2));
        System.out.println(describe(null));
        System.out.println(describe(3.14));

        System.out.println("Điểm: " + calculatePoints(new Order("Mai", 3, true)));
        System.out.println("Điểm: " + calculatePoints(new Order("Nam", 2, false)));
        System.out.println("Điểm: " + calculatePoints(4));
        System.out.println("Điểm: " + calculatePoints("abc"));
        System.out.println("Điểm: " + calculatePoints(null));
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac -encoding UTF-8 SwitchPatternExpressionDemo.java
java SwitchPatternExpressionDemo
```

Đầu ra đúng:

```text
Đơn lớn đã thanh toán: Mai (3)
Đơn chưa thanh toán: Nam
Đơn đã thanh toán: An (1)
Chuỗi trắng
Văn bản: java
Số dương: 5
Số khác: -2
Không có dữ liệu
Kiểu khác: Double
Điểm: 30
Điểm: 0
Điểm: 4
Điểm: -1
Điểm: 0
```

### Phân tích từng phần

**Hàm `describe`:**

1. Khi `value` là `Order("Mai", 3, true)`, record pattern khớp, guard `paid && count >= 3` là đúng, nên chọn nhánh đầu.
2. `Order("Nam", 2, false)` không qua guard đầu, nhưng nhánh `when !paid` đúng. `Order("An", 1, true)` không qua hai guard đầu, rơi vào nhánh `Order(...)` thứ ba.
3. Chuỗi chứa toàn khoảng trắng khớp `String text` và `text.isBlank()`. Chuỗi `"  java  "` không rỗng/trắng nên khớp nhánh `String text` còn lại và được `trim()`.
4. Số `5` và `-2` là `Integer` khi truyền cho tham số `Object` (autoboxing), vì thế khớp hai nhánh `Integer` khác nhau.
5. `null` được xử lý bởi `case null`. Số thực `3.14` là `Double` khi truyền vào `Object`, nên đi tới `default`.

**Hàm `calculatePoints`:**

- Nhánh `Order(...)` sử dụng block `-> { ... yield ...; }` để giới hạn số sản phẩm tối thiểu về 0 rồi tính điểm khi đã thanh toán.
- Nhánh `Integer` trả chính số đầu vào làm điểm.
- `case null` trả `0`; các kiểu còn lại trả `-1`.
- Biến `customer` trong nhánh record được đặt tên để minh họa cách phân rã toàn bộ record; trong tính điểm chỉ cần `itemCount` và `paid`. Nếu chạy Java 22+, có thể dùng unnamed pattern `_` thay cho component không cần sử dụng. Code trên vẫn tương thích Java 21 vì không dùng cú pháp `_`.

Về mặt thiết kế, hãy chọn kết quả có cùng ý nghĩa giữa các nhánh. Ví dụ `-1` được dùng như tín hiệu “không hỗ trợ” trong chương trình minh họa; hệ thống thực tế có thể chọn một kiểu kết quả như enum hoặc record để diễn đạt lỗi rõ hơn.

## 7. Tính đầy đủ (exhaustiveness) và `sealed` types

Compiler yêu cầu một `switch expression` phải **bao phủ mọi trường hợp** theo những kiểu có thể xảy ra. Với selector `Object`, các nhánh `String`, `Integer`, `Order` chưa bao phủ tất cả kiểu; thường phải có `default`.

Với **sealed interface**, compiler biết tập các lớp con trực tiếp được phép, vì thế có thể kiểm tra tính đầy đủ mà không cần `default`:

```java
// Ví dụ độc lập: các khai báo đặt cùng tệp trong cùng phạm vi phù hợp.
sealed interface Shape permits Circle, Rectangle {}
record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}

static double area(Shape value) {
    return switch (value) {
        case Circle(var radius) -> Math.PI * radius * radius;
        case Rectangle(var width, var height) -> width * height;
        case null -> 0.0;
    };
}
```

Đây là **trích đoạn minh họa**, không phải một tệp Java độc lập vì `static double area` cần nằm trong một lớp/record hoặc ngữ cảnh khai báo hợp lệ. Mẫu không cần `default` vì `Circle` và `Rectangle` bao phủ các triển khai của `Shape` đã khai báo; `case null` xử lý thêm `null` nếu được truyền vào.

Nếu sau này thiết kế sealed hierarchy thêm một kiểu được phép khác, compiler có thể yêu cầu bổ sung nhánh cho kiểu đó khi biên dịch lại. Đây là lợi ích của việc để compiler kiểm tra những nhánh cần thiết thay vì lập tức viết `default` cho mọi trường hợp.

**Điểm tinh tế:** Exhaustiveness chủ yếu nói về những giá trị không `null` có thể khớp theo hệ thống kiểu; `switch` với selector `null` vẫn cần được xem xét riêng. Nếu không có `case null` (hoặc nhãn xử lý `null` hợp lệ), gọi biểu thức với `null` thường ném `NullPointerException`, kể cả khi có `default`.

## 8. Thứ tự nhánh, dominance và phạm vi biến

### Nhánh rộng có thể che nhánh hẹp

Java kiểm tra **dominance** của các case pattern. Nếu đặt một nhánh tổng quát trước một nhánh hẹp hơn, nhánh hẹp có thể không bao giờ được chọn và **compiler báo lỗi**:

```java
// SAI: trích đoạn không biên dịch.
String output = switch (input) {
    case CharSequence text -> "Chuỗi ký tự";
    case String text -> "String cụ thể"; // bị case CharSequence che.
    case null -> "Null";
    default -> "Khác";
};
```

Cách sửa: ưu tiên nhánh `String` cụ thể trước:

```java
// HỢP LỆ với Object input.
String output = switch (input) {
    case String text -> "String cụ thể";
    case CharSequence text -> "Chuỗi ký tự";
    case null -> "Null";
    default -> "Khác";
};
```

Tương tự, nếu viết `case String s -> ...` trước `case String s when s.isBlank() -> ...`, nhánh có guard trở thành unreachable. Đặt các guard chuyên biệt trước nhánh cùng type nhưng không guard.

### Phạm vi pattern variable

Tên trong `case String text` được dùng ở `when` và phần thân của chính nhánh đó. Có thể đặt cùng tên `text` ở các nhánh khác nếu phạm vi không chồng lấn, nhưng không tham chiếu trực tiếp nó ở ngoài `switch`.

Đặt tên có ý nghĩa hơn `x` hay `obj` khi dữ liệu nhiều tầng: `customer`, `count`, `paid` dễ hiểu hơn trong nghiệp vụ Order. Với record lồng nhau, tên được ràng buộc tại từng component tương ứng; không có phép tự động “lấy mọi field theo tên”.

### Arrow tránh fall-through

`case ... ->` chạy nhánh được chọn, sau đó tạo kết quả. Nó không rơi xuyên xuống nhánh tiếp theo như kiểu viết `case:` của switch statement truyền thống. Với `switch expression`, hãy ưu tiên arrow để người đọc nhìn rõ nhánh nào sinh kết quả nào.

## 9. Các lỗi thường gặp

| Lỗi | Vì sao xảy ra | Cách khắc phục |
| --- | --- | --- |
| Không có `default` khi switch trên `Object` với vài kiểu cụ thể | `switch expression` không exhaustive | Bổ sung `default` hoặc type pattern tổng quát hợp lệ |
| Cho rằng `default` luôn xử lý `null` | Selector `null` có ngữ nghĩa riêng | Viết `case null` nếu đầu vào có thể là `null` |
| Đặt `case String s` trước `case String s when s.isBlank()` | Nhánh có guard bị che (dominated) | Đưa nhánh có guard lên trước |
| Đặt `case CharSequence c` trước `case String s` | Nhánh `String` bị che bởi kiểu cha | Đặt `String` trước `CharSequence` |
| Dùng `break value;` trong block của switch expression | Không phải cú pháp trả về giá trị của switch expression | Dùng `yield value;` |
| Viết `case Point(var x)` khi record có hai component | Thiếu một component pattern | Viết đủ `Point(var x, var y)` |
| Dùng `case String s` rồi cho rằng `s` có thể `null` | Type pattern không khớp `null` | Xử lý selector `null` ở nhánh riêng; component `var` có thể `null` |
| Tham chiếu pattern variable ở bên ngoài case | Biến chỉ có scope trong nhánh đã khớp | Tính giá trị trong nhánh và trả qua `switch expression` |
| Trả về kiểu kết quả không tương thích | Không thể tạo giá trị phù hợp kiểu đích | Thống nhất các kiểu giá trị hoặc thiết kế kiểu kết quả rõ ràng |
| Dùng cú pháp `switch` preview cũ trên Java 21 | Tính năng đã đổi trước khi hoàn thiện | Dùng `case Type v when condition -> ...` |

Một lỗi nội dung khác cần tránh là biến `var` trong record pattern có thể nhận **component tham chiếu `null`**. Ví dụ `case Order(var customer, var count, var paid)` có thể tạo `customer == null`; không được gọi `customer.length()` nếu không xử lý khả năng đó.

## 10. Bài tập tự luyện

Cho record:

```java
record Temperature(double celsius, String city) {}
```

**Bài 1.** Với `Object input`, viết một `switch expression` trả về `String`: `"Nóng"` nếu là `Temperature` có `celsius >= 35`, `"Bình thường"` nếu là `Temperature` còn lại, `"Thiếu dữ liệu"` nếu `null`, và `"Không phải nhiệt độ"` với kiểu khác.

**Đáp án:**

```java
// Trích đoạn minh họa.
String result = switch (input) {
    case Temperature(var degrees, var city) when degrees >= 35 -> "Nóng";
    case Temperature(var degrees, var city) -> "Bình thường";
    case null -> "Thiếu dữ liệu";
    default -> "Không phải nhiệt độ";
};
```

**Bài 2.** Viết lại nhánh đầu để dùng block và `yield` với biến tạm `String message`.

**Đáp án:**

```java
case Temperature(var degrees, var city) when degrees >= 35 -> {
    String message = "Nóng";
    yield message;
}
```

Đây là **đoạn nhánh `case`**, phải nằm trong một `switch expression` có các nhánh còn lại tương ứng. `yield` đưa `message` ra làm giá trị của biểu thức.

**Bài 3.** Điều gì xảy ra nếu đặt `case Temperature(var degrees, var city) -> "Bình thường";` trước nhánh `when degrees >= 35`?

**Đáp án:** Nhánh có guard bị che bởi nhánh `Temperature` tổng quát hơn; compiler không cho phép case pattern bị dominated. Hãy đặt guard cụ thể lên trước.

**Bài 4.** Tại sao có thể bỏ `default` trong một `switch expression` phân nhánh hết các lớp con được phép của sealed interface nhưng không thường bỏ được khi selector là `Object`?

**Đáp án:** Với sealed hierarchy, compiler biết danh sách các kiểu con được phép để kiểm tra coverage. Với `Object`, còn rất nhiều kiểu runtime chưa được liệt kê, nên phải có một nhánh bao phủ chúng (thường là `default`). Xử lý `null` vẫn là một quyết định riêng.

## 11. Tổng kết thực hành

- Dùng **`switch expression`** khi cần lấy **một giá trị kết quả** từ việc phân loại dữ liệu.
- `case Type variable` kiểm tra kiểu và cho phép dùng biến trong nhánh; `case Record(var a, var b)` phân rã record components.
- Thêm `when` để phân biệt những điều kiện khác nhau trên cùng kiểu; đặt nhánh có guard và các kiểu hẹp **trước** nhánh tổng quát.
- Dùng `-> expression` cho nhánh ngắn; dùng `-> { ... yield value; }` khi cần nhiều câu lệnh.
- Đảm bảo tất cả trường hợp được bao phủ; thêm `default` cho selector mở như `Object`, dùng sealed types khi muốn compiler kiểm tra tập kiểu rõ ràng.
- Xử lý `null` chủ động và giữ kết quả các nhánh tương thích về kiểu.

**Tài liệu chuẩn:** [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html), [Oracle Java 21 — Switch Expressions](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html).
