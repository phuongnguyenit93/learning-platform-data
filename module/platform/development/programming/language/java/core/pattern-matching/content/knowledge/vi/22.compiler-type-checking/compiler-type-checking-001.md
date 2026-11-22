# Compiler phân tích pattern như thế nào

## 1. Phân biệt compiler kiểm tra gì và runtime quyết định gì

Pattern matching trong Java không chỉ rút gọn thao tác ép kiểu. Một pattern đặt ra **hợp đồng về kiểu và cấu trúc dữ liệu**. Trình biên dịch (`javac`) phải xác định rằng cách viết pattern hợp lệ, các biến được ràng buộc có kiểu phù hợp và mọi nhánh `switch` đáp ứng quy tắc của ngôn ngữ.

Ví dụ:

```java
Object input = "Java";

if (input instanceof String text && text.length() >= 4) {
    System.out.println(text.toUpperCase());
}
```

Khi **biên dịch**, Java kiểm tra các điều sau:

1. Kiểu tĩnh của `input` là `Object` và phép thử `instanceof String` có ý nghĩa về mặt kiểu.
2. `text` là một biến pattern có kiểu tĩnh `String`.
3. Sau toán tử `&&`, `text` chỉ được sử dụng nếu pattern bên trái đã khớp; lệnh `text.length()` và `text.toUpperCase()` đều hợp lệ về kiểu.
4. Toàn bộ điều kiện `if` có kiểu `boolean` và phần thân dùng các biến trong phạm vi cho phép.

Khi **chạy**, chương trình mới xét đối tượng thật có phải `String` hay không, độ dài có đạt `4` hay không, rồi in `JAVA`. Compiler không chạy trước các biểu thức trên mọi dữ liệu có thể xuất hiện trong tương lai.

Có thể hình dung công việc của compiler theo các lớp kiểm tra: **cú pháp pattern → tính phù hợp về kiểu → kiểu và phạm vi biến → khả năng tiếp cận nhánh → tính đầy đủ của switch**. Đây là mô hình tư duy để học ngôn ngữ, không phải cam kết rằng mọi compiler phải thực thi các bước nội bộ theo đúng thứ tự này.

## 2. Kiểm tra tính phù hợp của kiểu (type compatibility)

Một pattern phải có ý nghĩa đối với **kiểu tĩnh của biểu thức đang được kiểm tra**. Compiler không chờ đến runtime để chấp nhận một phép thử kiểu chắc chắn không thể đúng theo các quy tắc chuyển kiểu được Java cho phép.

Ví dụ hợp lệ:

```java
Object input = 42;
if (input instanceof Integer number) {
    System.out.println(number + 1);
}
```

`input` có kiểu tĩnh `Object`, có thể đang trỏ tới `Integer`. Khi khớp, `number` có kiểu tĩnh `Integer`, nên ví dụ in `43` nhờ cơ chế unboxing.

Ví dụ không hợp lệ:

```java
String text = "abc";

// KHÔNG BIÊN DỊCH: String và Integer là các kiểu cuối
// không thể chuyển đổi theo phép kiểm tra kiểu này.
// if (text instanceof Integer number) {
//     System.out.println(number);
// }
```

Không có một phép thử `instanceof` hợp lệ từ `String` sang `Integer` trong trường hợp này: compiler phát hiện **kiểu không tương thích**, thay vì để chương trình luôn trả về `false` lúc chạy.

Điểm cần phân biệt: compiler dựa trên **khai báo kiểu tĩnh** và các quy tắc chuyển đổi của ngôn ngữ. Nó không đoán rằng biến `Object` sẽ chỉ mang `String` vì những lần gán quan sát được ở một đoạn ví dụ.

### Pattern không giống ép kiểu thủ công

Trước pattern matching, cách viết thường là:

```java
if (input instanceof String) {
    String text = (String) input;
    System.out.println(text.length());
}
```

Với type pattern:

```java
if (input instanceof String text) {
    System.out.println(text.length());
}
```

Compiler vừa kiểm tra khả năng khớp của phép thử, vừa xác định `text` mang kiểu `String` ở nhánh đã khớp. Phần thân không cần một phép ép kiểu `(String) input` riêng.

## 3. Compiler xác định kiểu của biến pattern

Với:

```java
record Point(int x, int y) {}
```

Record pattern:

```java
if (input instanceof Point(int x, int y)) {
    System.out.println(x + y);
}
```

yêu cầu compiler đối chiếu với khai báo record. `Point` có đúng hai component kiểu `int` và `int`; vì vậy `x` và `y` là các biến `int` trong phần chương trình mà mẫu đã khớp.

Java 21 cũng cho phép suy luận kiểu component:

```java
if (input instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

Ở đây, `var` không có nghĩa là biến không có kiểu. Compiler suy luận mỗi biến là `int` từ component tương ứng của `Point`.

Ví dụ lỗi cú pháp/kiểu khi khớp record:

```java
// KHÔNG BIÊN DỊCH: Point có hai component, không phải một.
// if (input instanceof Point(int x)) { }

// KHÔNG BIÊN DỊCH: component của Point là int, không phải String.
// if (input instanceof Point(String x, String y)) { }
```

Record pattern phải khớp đúng **số lượng component** và dùng các pattern phù hợp với kiểu từng component. Tên biến trong pattern không thay thế cho thứ tự khai báo. Ví dụ `Point(int y, int x)` có thể hợp lệ nhưng `y` lại nhận component thứ nhất — một lỗi ý nghĩa mà compiler không biết người viết có chủ đích hay không.

### Pattern lồng nhau

Giả sử:

```java
record Segment(Point start, Point end) {}
```

Mẫu:

```java
if (input instanceof Segment(
        Point(int x1, int y1),
        Point(int x2, int y2))) {
    System.out.println(x2 - x1);
}
```

khi biên dịch được phân tích dựa trên cấu trúc khai báo `Segment`: có hai component kiểu `Point`; mỗi `Point` tiếp tục có hai component kiểu `int`. Compiler kiểm tra tính phù hợp và xác định các biến `x1`, `y1`, `x2`, `y2`.

**Lúc chạy**, việc khớp toàn bộ mẫu còn phụ thuộc giá trị từng component. Nếu `start` hoặc `end` là `null`, mẫu `Point(...)` ở vị trí đó không khớp; cả mẫu `Segment(...)` lồng nhau không khớp. Record pattern không tự gọi constructor, tạo đối tượng mới hoặc biến tất cả component thành giá trị khác `null`.

## 4. Phạm vi biến pattern: flow scoping và definite match

Một điểm đặc biệt quan trọng là compiler không chỉ xét vị trí dấu ngoặc nhọn. Nó còn phân tích **đường đi điều khiển** để biết ở đâu biến pattern chắc chắn đã được ràng buộc (*flow scoping*).

### Trường hợp hợp lệ với &&

```java
if (input instanceof String text && !text.isBlank()) {
    System.out.println(text.length());
}
```

`&&` đánh giá ngắn mạch: vế phải chỉ được xét khi vế trái đúng. Vì vậy, khi đánh giá `text.isBlank()`, compiler có thể chứng minh `text` đã được tạo ra bởi pattern. Trong thân `if`, điều kiện tổng cũng đã đúng nên biến vẫn dùng được.

### Trường hợp sai với ||

```java
// KHÔNG BIÊN DỊCH:
// Vế phải của || chạy khi pattern bên trái KHÔNG khớp,
// nên biến text chưa chắc đã tồn tại.
// if (input instanceof String text || text.isBlank()) {
//     System.out.println(text);
// }
```

`||` cũng ngắn mạch, nhưng điều kiện kích hoạt vế phải **ngược với `&&`**: vế phải được đánh giá khi vế trái sai. Do đó không thể dùng `text` tại vị trí đó. Không nên sửa bằng cách đổi sang `|` hoặc `&`; hai toán tử boolean này đánh giá cả hai vế.

### Guard clause giúp biến hợp lệ ở phần tiếp theo

```java
static int lengthOrZero(Object input) {
    if (!(input instanceof String text)) {
        return 0;
    }
    return text.length();
}
```

Nhánh phủ định kết thúc bằng `return`. Mọi đường thực thi tiếp tục đến dòng `return text.length()` đều đã vượt qua phép thử `instanceof` thành công; compiler cho phép dùng `text`.

Ngược lại:

```java
// KHÔNG BIÊN DỊCH nếu cố dùng text sau if:
// if (!(input instanceof String text)) {
//     System.out.println("Không phải chuỗi");
// }
// System.out.println(text.length());
```

Ở đây nhánh mẫu **không khớp** vẫn có thể đi tiếp sau `if`. Compiler không thể bảo đảm `text` đã được ràng buộc ở câu lệnh bên dưới. Điều này liên quan đến phân tích luồng, không chỉ là phạm vi theo dấu `{}`.

### Phạm vi giữa các nhánh switch

```java
return switch (input) {
    case String text -> "Chuỗi: " + text.length();
    case Integer number -> "Số: " + number;
    case null -> "Không có dữ liệu";
    default -> "Loại khác";
};
```

Ở đây `text` chỉ dùng trong nhánh `String`, `number` trong nhánh `Integer`. Không thể mang `text` sang nhánh `Integer` rồi mong compiler biết giá trị đó có kiểu `String`. Mẫu nào khớp thì biến của mẫu đó mới có nghĩa.

## 5. Compiler phân tích case, guard và dominance trong switch

Pattern matching for `switch` ở Java 21 cho phép mỗi nhánh diễn đạt một loại dữ liệu hoặc cấu trúc record. Compiler kiểm tra **kiểu của selector**, **tính hợp lệ của từng nhánh** và liệu nhánh sau có bị nhánh trước bao phủ hoàn toàn hay không (*dominance*).

Ví dụ sai vì thứ tự nhánh:

```java
// KHÔNG BIÊN DỊCH: nhánh tổng quát đứng trước nhánh cụ thể.
// return switch (input) {
//     case Object any -> "Bất kỳ object không null";
//     case String text -> "Chuỗi: " + text;
//     case null -> "null";
// };
```

`case Object any` nhận mọi đối tượng không `null`, gồm cả `String`. Vì thế nhánh `case String text` phía sau không thể được chọn, và compiler phát hiện nhánh bị bao phủ.

Cách sắp xếp phù hợp:

```java
return switch (input) {
    case String text -> "Chuỗi: " + text;
    case Integer number -> "Số: " + number;
    case null -> "Không có dữ liệu";
    default -> "Loại khác";
};
```

Một **guard `when`** bổ sung điều kiện sau khi pattern khớp:

```java
return switch (input) {
    case Integer number when number > 0 -> "Số dương";
    case Integer number -> "Số nguyên không dương";
    case null -> "Không có dữ liệu";
    default -> "Loại khác";
};
```

Trình biên dịch biết `number` trong `when number > 0` có kiểu `Integer` do pattern ràng buộc. Còn việc `number > 0` thực sự đúng hay sai được xác định lúc chạy.

**Đặt nhánh cụ thể có `when` trước nhánh `Integer` không guard.** Nếu đặt `case Integer number` không guard trước, nhánh cùng loại đứng sau có thể bị **dominated**. Không nên giả định compiler hiểu mọi quan hệ logic toán học giữa hai biểu thức `when` tùy ý. Quy tắc dominance của ngôn ngữ dựa trên những gì compiler được định nghĩa phải chứng minh, không phải một trình giải mọi mệnh đề nghiệp vụ.

### Guard không có nghĩa là pattern đầy đủ

```java
// Chỉ có nhánh số dương thì switch expression không đầy đủ:
// return switch (input) {
//     case Integer n when n > 0 -> "Dương";
// };
```

Vì `input` có thể không phải `Integer`, hoặc có thể là một số nguyên không dương, biểu thức này chưa bao phủ hết trường hợp. Đặt `default` hoặc các nhánh còn lại thích hợp sẽ giải quyết vấn đề.

## 6. Exhaustiveness: compiler chứng minh switch expression có đủ nhánh

Một **switch expression** cần bao phủ mọi giá trị selector mà quy tắc ngôn ngữ yêu cầu. Với `Object` chứa nhiều loại dữ liệu không giới hạn, `default` thường cần thiết.

Với **sealed type**, compiler có thêm thông tin về các subtype được phép, nhờ đó có thể kiểm tra tính đầy đủ mà không cần một `default` chung cho các giá trị không `null`:

```java
sealed interface Shape permits Circle, Rectangle {}
record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
```

Một ví dụ đầy đủ:

```java
static String shapeKind(Shape shape) {
    return switch (shape) {
        case Circle(double radius) -> "Tròn: " + radius;
        case Rectangle(double width, double height) ->
                "Chữ nhật: " + width + " x " + height;
        case null -> "Không có hình";
    };
}
```

Compiler có thể xác định các dạng không `null` của `Shape` từ khai báo `sealed` và hai kiểu record được cho phép. `case null` xử lý trường hợp selector `null` một cách tường minh. Trong ví dụ này, không cần `default`.

Khi dùng guard, cần thêm nhánh để xử lý các giá trị **không thỏa guard**:

```java
return switch (shape) {
    case Circle(double radius) when radius > 0 -> "Tròn hợp lệ";
    case Circle(double radius) -> "Tròn bán kính không dương";
    case Rectangle(double width, double height) ->
            "Chữ nhật";
    case null -> "Không có hình";
};
```

Nhánh `case Circle(double radius)` thứ hai bao phủ các giá trị `Circle` không khớp guard đầu. Nếu chỉ có nhánh `Circle(...) when radius > 0`, các hình tròn bán kính `0` hay âm không được xử lý; không thể xem nhánh có guard tùy ý là bao phủ toàn bộ loại `Circle`.

**Lưu ý:** `default` không nên được hiểu là nhánh tự động bắt selector `null` trong pattern matching for switch. Nếu selector có thể là `null` và muốn trả về kết quả riêng, hãy dùng `case null`. Nếu không có nhánh xử lý `null` phù hợp, `switch` có thể ném `NullPointerException` tại runtime dù phần bao phủ kiểu không `null` đã đầy đủ.

## 7. Generic record pattern và giới hạn của type erasure

Compiler cũng phải hiểu kiểu generic của record:

```java
record Box<T>(T value) {}

static void show(Box<String> box) {
    if (box instanceof Box(var text)) {
        System.out.println(text.toUpperCase());
    }
}
```

Trong Java 21, trình biên dịch có thể **suy luận đối số kiểu** cho record pattern khi ngữ cảnh tĩnh đủ rõ. Với `Box<String>` ở ví dụ trên, component `text` được suy luận là `String`. Do vậy, không phải cứ viết `Box(var text)` là dùng raw type.

Tuy nhiên, Java dùng **type erasure** với generic: không được cho rằng một kiểm tra trên đối tượng kiểu `Object` sẽ xác nhận chính xác đối số kiểu `String` của `Box<String>` tại runtime. Nếu đầu vào có kiểu không biết, hãy kiểm tra kiểu component thực tế:

```java
static String readBox(Object input) {
    if (input instanceof Box(var value) && value instanceof String text) {
        return text.toUpperCase();
    }
    return "Không phải Box chứa String";
}
```

Bài học quan trọng là:

- Compiler kiểm tra **tính hợp lệ về kiểu tĩnh và khả năng suy luận kiểu**.
- Runtime kiểm tra đối tượng và component cụ thể có khớp pattern hay không.
- Không dùng raw type hoặc ép kiểu unchecked như một cách bỏ qua hợp đồng generic; chúng có thể tạo cảnh báo và dời rủi ro về thời gian chạy.

## 8. Chương trình Java 21 chạy hoàn chỉnh

Tạo tệp **`CompilerPatternAnalysisDemo.java`**:

```java
public class CompilerPatternAnalysisDemo {
    sealed interface Shape permits Circle, Rectangle {}
    record Circle(double radius) implements Shape {}
    record Rectangle(double width, double height) implements Shape {}

    record Point(int x, int y) {}
    record LabelledPoint(String label, Point point) {}

    static String inspect(Object value) {
        if (value instanceof LabelledPoint(
                String label, Point(int x, int y))
                && x >= 0 && y >= 0) {
            return "Point " + label + "=(" + x + "," + y + ")";
        }

        if (value instanceof LabelledPoint point) {
            return "LabelledPoint chưa phù hợp";
        }

        return "Không phải LabelledPoint";
    }

    static String kind(Shape shape) {
        return switch (shape) {
            case Circle(double r) when r > 0 ->
                    "Tròn hợp lệ: " + r;
            case Circle(double r) ->
                    "Tròn không hợp lệ: " + r;
            case Rectangle(double w, double h) when w > 0 && h > 0 ->
                    "Chữ nhật hợp lệ: " + (w * h);
            case Rectangle(double w, double h) ->
                    "Chữ nhật không hợp lệ";
            case null ->
                    "Không có hình";
        };
    }

    public static void main(String[] args) {
        System.out.println(inspect(
                new LabelledPoint("A", new Point(2, 3))));
        System.out.println(inspect(new LabelledPoint("B", null)));
        System.out.println(inspect("khác"));

        System.out.println(kind(new Circle(2)));
        System.out.println(kind(new Circle(0)));
        System.out.println(kind(new Rectangle(3, 4)));
        System.out.println(kind(new Rectangle(3, -1)));
        System.out.println(kind(null));
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên**:

```bash
javac CompilerPatternAnalysisDemo.java
java CompilerPatternAnalysisDemo
```

Kết quả trên standard output:

```text
Point A=(2,3)
LabelledPoint chưa phù hợp
Không phải LabelledPoint
Tròn hợp lệ: 2.0
Tròn không hợp lệ: 0.0
Chữ nhật hợp lệ: 12.0
Chữ nhật không hợp lệ
Không có hình
```

Phân tích các điểm compiler cần kiểm tra trong chương trình:

1. `LabelledPoint(String label, Point(int x, int y))` phải phù hợp với cấu trúc record: component đầu kiểu `String`; component thứ hai là `Point` có hai component `int`.
2. Biến `x`, `y` tồn tại ở các toán hạng `&&` sau mẫu đã khớp và trong thân `if`; phép so sánh `>= 0` hợp lệ với `int`.
3. Nhánh `instanceof LabelledPoint point` phía sau là một phép thử khác: giá trị có thể là `LabelledPoint` nhưng thiếu component con, ví dụ `point == null` bên trong record.
4. Selector `switch` có kiểu `Shape`. Compiler thấy `Shape` là `sealed`, chỉ cho phép `Circle` và `Rectangle` trong cấu trúc khai báo đang xét.
5. Các nhánh `case ... when ...` đứng trước nhánh cùng record không guard nên không bị các nhánh rộng hơn che khuất.
6. Các nhánh `Circle` và `Rectangle` không guard bảo đảm mọi trường hợp không `null` trong hai loại hình đều có nhánh; `case null` giải quyết selector `null`.

Phân tích hành vi lúc chạy:

- `LabelledPoint("A", Point(2, 3))` khớp cả mẫu lồng và `x >= 0 && y >= 0` nên trả về `Point A=(2,3)`.
- `LabelledPoint("B", null)` không khớp mẫu `Point(int x, int y)`, nhưng vẫn khớp type pattern tổng quát `LabelledPoint point`.
- `"khác"` không phải `LabelledPoint` nên trả về thông báo cuối cùng.
- `Circle(2)` có bán kính `2.0`, khớp guard `r > 0`; `Circle(0)` trượt guard nhưng vẫn khớp nhánh `Circle` kế tiếp.
- `Rectangle(3, 4)` có hai kích thước dương nên diện tích `12.0`; `Rectangle(3, -1)` trượt guard và chọn nhánh dự phòng.
- `null` được xử lý tường minh bởi `case null`.

Chương trình không phụ thuộc thứ tự liệt kê đối tượng runtime để compiler quyết định kiểu của các biến pattern; các quy tắc kiểm tra và tính đầy đủ được áp dụng ngay từ khai báo kiểu của chương trình.

## 9. Các lỗi compiler thường phát hiện

| Trường hợp | Điều compiler kiểm tra / báo lỗi | Cách khắc phục |
| --- | --- | --- |
| `String text` được thử với `instanceof Integer number` | Phép thử kiểu không tương thích với kiểu tĩnh của giá trị. | Kiểm tra kiểu đúng với miền giá trị đầu vào. |
| `Point(int x)` trong khi `Point` có hai component | Record pattern sai số lượng component. | Đủ hai component pattern theo đúng thứ tự. |
| `Point(String x, String y)` với component `int` | Pattern component không tương thích kiểu. | Dùng `int` hoặc `var` phù hợp. |
| Dùng biến pattern ở vế phải `||` | Mẫu vế trái có thể không khớp khi vế phải được xét. | Dùng `&&` nếu có quan hệ phụ thuộc; hoặc tách guard clause. |
| Dùng biến pattern sau nhánh phủ định không `return` | Không chứng minh được biến đã được ràng buộc trên mọi đường đi. | Chỉ dùng biến ở nơi flow scoping cho phép. |
| Đặt `case Object any` trước `case String text` | Nhánh `String` bị nhánh trước bao phủ hoàn toàn. | Đặt nhánh cụ thể trước nhánh tổng quát. |
| Chỉ có `case Circle(...) when r > 0` cho mọi `Circle` | Guard không bao phủ những bán kính không dương; switch có thể không đầy đủ. | Thêm nhánh `Circle` không guard hoặc nhánh thích hợp. |
| Lấy `String` từ một `Box<?>` mà không kiểm tra | Đối số generic không được chứng minh là `String`. | Giữ kiểu tham số trong API hoặc kiểm tra component. |

Compiler **không** chứng minh được tất cả tính đúng đắn của chương trình: nó không bảo đảm bán kính luôn dương, chuỗi luôn hợp lệ về nghiệp vụ, dữ liệu không bao giờ `null` hoặc mọi phương thức được gọi không ném exception. Những điều này cần kiểm tra ở runtime, hợp đồng dữ liệu, test và code ứng dụng.

## 10. Tự kiểm tra

Cho các khai báo:

```java
record Task(String title, int priority) {}
Object input = new Task("Fix", 3);
```

**Câu hỏi 1:** Compiler có thể xác định kiểu của `title` và `priority` trong mẫu sau không?

```java
if (input instanceof Task(var title, var priority)
        && priority >= 2) {
    System.out.println(title + ": ưu tiên");
}
```

**Đáp án:** Có. `Task` khai báo component `title` là `String`, `priority` là `int` nên `var` được suy luận tương ứng. `priority` được dùng hợp lệ sau `&&`. Với dữ liệu ví dụ, in `Fix: ưu tiên`.

**Câu hỏi 2:** Nếu đổi `&&` thành `||` và vẫn dùng `priority` ở vế phải thì sao?

**Đáp án:** Không biên dịch được do phạm vi biến pattern: vế phải `||` có thể chạy khi record pattern không khớp.

**Câu hỏi 3:** Nếu chuyển `Task` thành một subtype được phép của sealed interface và dùng `switch` để phân loại, chỉ viết `case Task(var title, var priority) when priority > 0` đã đủ cho tất cả `Task` chưa?

**Đáp án:** Chưa. Guard `priority > 0` có thể sai, nên cần nhánh bổ sung cho `Task` còn lại. Ngoài ra, `switch` phải bao phủ những subtype khác được phép nếu có, và có cách xử lý `null` nếu bài toán cần chấp nhận đầu vào ấy.

**Ghi nhớ:** Với pattern matching, compiler kiểm tra **tính hợp lệ của kiểu và cấu trúc, kiểu và phạm vi biến được ràng buộc, dominance và exhaustiveness của switch**. Runtime mới quyết định **một giá trị cụ thể có khớp pattern và guard hay không**. Phân biệt hai tầng kiểm tra giúp đọc thông báo lỗi `javac` chính xác hơn và viết pattern Java 21 an toàn, dễ bảo trì.
