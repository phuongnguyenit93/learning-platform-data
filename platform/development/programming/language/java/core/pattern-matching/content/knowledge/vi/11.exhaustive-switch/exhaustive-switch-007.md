# Compiler kiểm tra nhánh còn thiếu trong exhaustive `switch` (Java Pattern Matching)

## 1. Exhaustive `switch` là gì?

Một `switch` được gọi là **exhaustive** khi tập hợp các nhãn `case` đủ để xử lý **mọi giá trị đầu vào mà hệ thống kiểu cho phép** theo quy tắc bao phủ của Java. Nếu một dạng `switch` bắt buộc phải exhaustive mà trình biên dịch không chứng minh được tính đầy đủ này, mã sẽ **không biên dịch**.

Ví dụ, với một `enum` có ba hằng:

```java
enum Light { RED, YELLOW, GREEN }

static String action(Light light) {
    return switch (light) {
        case RED -> "STOP";
        case YELLOW -> "WAIT";
        // Thiếu GREEN: switch expression không biên dịch.
    };
}
```

Đây là **mã minh họa lỗi**, không phải chương trình có thể biên dịch. Vì biểu thức `switch` phải tạo ra một kết quả cho mọi giá trị hợp lệ của `Light`, compiler xác định còn thiếu `GREEN` và từ chối.

Ngược lại, phiên bản đầy đủ sau **hợp lệ trên Java 21**:

```java
static String action(Light light) {
    return switch (light) {
        case RED -> "STOP";
        case YELLOW -> "WAIT";
        case GREEN -> "GO";
    };
}
```

Khi mọi giá trị của một `enum` đã được liệt kê, `switch` expression không bắt buộc phải có `default`. Điều này đặc biệt hữu ích: nếu sau này thêm một hằng `BLUE` và biên dịch lại mã sử dụng `switch`, compiler có thể chỉ ra nơi cần cập nhật logic.

**Điểm cốt lõi:** tính exhaustiveness được quyết định **lúc biên dịch** dựa trên kiểu selector và các nhãn `case`; không phải bằng cách chạy thử vài dữ liệu rồi suy ra “không còn nhánh nào khác”.

## 2. Compiler kiểm tra những dạng `switch` nào?

Không phải mọi `switch` statement đều có cùng yêu cầu.

| Cấu trúc | Có bắt buộc exhaustive? | Ví dụ |
| --- | --- | --- |
| **`switch` expression** (dùng giá trị kết quả) | **Có** | `String x = switch (value) { ... };` |
| **Enhanced `switch` statement** (Java 21: có nhãn pattern, `case null` hoặc các dạng được phân loại enhanced) | **Có** | `switch (obj) { case String s -> ...; }` |
| **Traditional `switch` statement** với nhãn hằng theo cú pháp truyền thống | **Không nhất thiết** | `switch (light) { case RED: ...; break; }` |

**`switch` expression:** nếu không có nhãn tổng quát và vẫn còn kiểu/hằng chưa được bao phủ, compiler báo lỗi. Chương trình không thể tính một biểu thức mà có đường đi không tạo giá trị.

**Enhanced `switch` statement:** Java 21 yêu cầu exhaustive ngay cả khi không trả về giá trị. Vì pattern có thể dùng cho selector kiểu `Object` hay phân cấp `sealed`, compiler cần bảo đảm tập nhãn bao phủ các giá trị không `null` phù hợp, theo quy tắc ngôn ngữ.

**Traditional `switch` statement:** có thể bỏ nhánh. Nếu không có nhãn nào khớp thì statement chỉ hoàn thành mà không chạy một nhánh `case`, hoặc chạy logic quanh nó như lập trình viên đã viết. Đây là hành vi được phép theo cú pháp truyền thống, không phải bảo đảm mọi trường hợp đã được xử lý.

Ví dụ minh họa statement truyền thống hợp lệ:

```java
static void showRed(Light light) {
    switch (light) {
        case RED:
            System.out.println("RED");
            break;
    }
}
```

Khi `light` bằng `GREEN` hoặc `YELLOW`, ví dụ này không in gì. Không có lỗi compile-time về thiếu nhánh vì đây là traditional `switch` statement.

Trong bài này, các ví dụ có pattern được viết theo **Java 21**, khi pattern matching cho `switch` đã là tính năng chính thức (JEP 441). Không cần bật preview cho các cú pháp Java 21 được trình bày.

## 3. Compiler suy luận tính đầy đủ như thế nào?

Compiler không cần “đoán” tất cả đối tượng runtime. Nó dùng **kiểu tĩnh** của biểu thức trong `switch (...)` và các quy tắc về tập giá trị có thể khớp:

1. **`default`** có thể bao phủ các giá trị **khác `null`** chưa khớp nhãn trước. Đây là giải pháp tổng quát khi selector là kiểu mở như `Object`.
2. **Toàn bộ hằng của `enum`** tạo thành tập đóng. Nếu đã có case cho mọi hằng, một `switch` expression có thể exhaustive mà không cần `default`.
3. **Các subtype của `sealed` type** được khai báo trong danh sách `permits` tạo thành tập loại triển khai bị kiểm soát. Các pattern phù hợp bao phủ tất cả các subtype được phép có thể làm `switch` exhaustive.
4. **Pattern đủ tổng quát** có thể bao phủ mọi giá trị không `null` của kiểu selector. Ví dụ `case Object obj -> ...` với selector tham chiếu thích hợp.
5. **Record patterns** có thể đóng góp vào phân tích bao phủ khi cấu trúc record và các component patterns là phù hợp; trong bài này dùng `case Literal(int n)` và `case Add(var left, var right)` để minh họa.
6. **Guards `when`** với điều kiện tùy ý **không được giả định luôn đúng**. Một case guarded không tự chứng minh đã xử lý toàn bộ giá trị của kiểu pattern đó.

Nếu compiler chưa có đủ bằng chứng, nó báo rằng `switch` không bao phủ tất cả giá trị có thể có. Nội dung chính xác của thông báo và vị trí đánh dấu tùy JDK/IDE; quan trọng là **lỗi được phát hiện trước khi chạy**.

**Exhaustive không có nghĩa mọi giá trị đều chạy một nhánh:** một selector tham chiếu bằng `null` vẫn cần được xử lý riêng nếu bạn muốn nhận nó. Một `switch` exhaustive về các giá trị khác `null` có thể ném `NullPointerException` khi selector là `null`; `default` thường **không** bắt selector `null`.

## 4. Chương trình Java 21 hoàn chỉnh: compiler chấp nhận tập nhánh đủ

Tạo tệp **`CompilerExhaustiveSwitch.java`**:

```java
public class CompilerExhaustiveSwitch {
    sealed interface Expr permits Literal, Add, Negate {}

    record Literal(int value) implements Expr {}
    record Add(Expr left, Expr right) implements Expr {}
    record Negate(Expr inner) implements Expr {}

    enum Light { RED, YELLOW, GREEN }

    static int evaluate(Expr expr) {
        return switch (expr) {
            case Literal(int n) -> n;
            case Add(var left, var right) ->
                evaluate(left) + evaluate(right);
            case Negate(var inner) -> -evaluate(inner);
        };
    }

    static String action(Light light) {
        return switch (light) {
            case RED -> "STOP";
            case YELLOW -> "WAIT";
            case GREEN -> "GO";
        };
    }

    static String describe(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String text when text.length() >= 4 ->
                "LONG:" + text;
            case String text -> "SHORT:" + text;
            case Integer number -> "INT:" + number;
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        Expr formula = new Add(
            new Literal(2),
            new Negate(new Literal(5))
        );

        System.out.println(evaluate(formula));
        System.out.println(evaluate(new Literal(8)));
        System.out.println(action(Light.GREEN));

        Object[] values = {
            "java", "hi", Integer.valueOf(7), null, 2.5
        };
        for (Object value : values) {
            System.out.println(describe(value));
        }

        try {
            evaluate(null);
        } catch (NullPointerException e) {
            System.out.println("NULL_EXPR");
        }
    }
}
```

Biên dịch/chạy bằng **JDK 21 trở lên**, dùng mức ngôn ngữ Java 21:

```bash
javac --release 21 CompilerExhaustiveSwitch.java
java CompilerExhaustiveSwitch
```

Stdout chính xác:

```text
-3
8
GO
LONG:java
SHORT:hi
INT:7
NULL
OTHER
NULL_EXPR
```

### Vì sao chương trình biên dịch?

- `Expr` là một `sealed interface` cho phép đúng ba record: `Literal`, `Add`, `Negate`. Ba record patterns trong `evaluate` bao phủ các dạng của `Expr`. **Không cần `default`.**
- Với `Add(var left, var right)`, `var` suy luận kiểu thành phần là `Expr`. Phương thức `evaluate` gọi đệ quy cho hai vế; `Negate` đổi dấu.
- `Light` có ba hằng và `action` liệt kê đầy đủ ba hằng. **Không cần `default`.**
- `describe(Object)` làm việc với kiểu mở `Object`, nên có `default` cho giá trị khác `null` không phải `String` hay `Integer`. Nhánh `case null` nhận selector `null`.
- Hai nhánh `String` trong `describe` có guard và fallback không guard. Nhánh `String text` thứ hai nhận mọi chuỗi không được nhánh đầu chọn.
- `evaluate(null)` có `switch` exhaustive trên các subtype `Expr` nhưng không có `case null`, nên vẫn ném `NullPointerException`; `catch` ở `main` in `NULL_EXPR`.

Đây là minh họa quan trọng: **compiler chứng minh bao phủ các dạng kiểu; compiler không tự bảo đảm rằng bạn đã thiết kế chính sách xử lý `null` hoặc dữ liệu nghiệp vụ hợp lệ.**

## 5. Trường hợp compiler phát hiện nhánh còn thiếu

### A. `enum`: bỏ sót một hằng

Đoạn mã sau **cố ý lỗi trên Java 21**:

```java
enum Status { NEW, RUNNING, DONE }

static String label(Status status) {
    return switch (status) {
        case NEW -> "New";
        case RUNNING -> "Running";
        // Thiếu DONE và không có default.
    };
}
```

Với kiểu `Status`, compiler biết còn hằng `DONE` chưa được bao phủ. Cách sửa đúng khi mỗi hằng cần xử lý riêng là bổ sung:

```java
case DONE -> "Done";
```

Dòng trên là **phần nhãn được thêm vào `switch`**, không phải chương trình độc lập.

Có thể thêm `default -> "Other"` để đạt exhaustiveness, nhưng lúc đó thay đổi enum trong tương lai có thể được nhánh dự phòng bắt mà compiler không buộc bạn xem lại logic. Với nghiệp vụ yêu cầu phân biệt từng enum hằng, liệt kê đầy đủ thường an toàn hơn.

### B. `sealed` hierarchy: bỏ một permitted subtype

Giả sử:

```java
sealed interface Shape permits Circle, Square {}
record Circle(int radius) implements Shape {}
record Square(int side) implements Shape {}
```

Biểu thức này **không đầy đủ**:

```java
static int size(Shape shape) {
    return switch (shape) {
        case Circle(int radius) -> radius * radius;
        // Thiếu Square.
    };
}
```

Compiler biết `Square` là subtype được cho phép của `Shape`, nên báo `switch` thiếu nhánh. Cách sửa là thêm `case Square(int side) -> side * side;` hoặc tổ chức lại các case để bao phủ `Square`.

**Sealed không có nghĩa mọi dữ liệu đều có dạng chỉ định trước ở runtime nếu bạn biên dịch/ràng buộc nhiều module khác nhau:** cần xét lớp được phép qua phân cấp type tương ứng. Tuy vậy, sealed giúp compiler biết các subtype hợp lệ **trong kiểu tại thời điểm biên dịch** và chỉ rõ thiếu nhánh khi sửa hệ phân cấp rồi biên dịch lại.

### C. Selector kiểu mở: thiếu `default` hoặc pattern tổng quát

Với selector `Object value`:

```java
static String textOnly(Object value) {
    return switch (value) {
        case String text -> "S:" + text;
        case Integer number -> "I:" + number;
        // Có thể là Double, Boolean, Object khác...
    };
}
```

Đoạn mã trên **cố ý không biên dịch**. Kiểu `Object` có vô số loại giá trị khác; compiler không thể kết luận `String` và `Integer` đã bao phủ tất cả. Sửa bằng:

```java
static String textOnly(Object value) {
    return switch (value) {
        case String text -> "S:" + text;
        case Integer number -> "I:" + number;
        default -> "Other";
    };
}
```

Cách này exhaustive với các đối tượng khác `null`. Nếu muốn trả `"Null"` khi selector bằng `null`, thêm `case null -> "Null";` hoặc gộp `case null, default -> "Other";` theo nhu cầu.

### D. Enhanced `switch` statement: thiếu nhánh dù không trả giá trị

Ví dụ **cố ý lỗi trong Java 21**:

```java
static void print(Object value) {
    switch (value) {
        case String text -> System.out.println(text);
        // Thiếu mọi đối tượng không phải String.
    }
}
```

Đây là một **enhanced switch statement**, bởi có pattern label. Java 21 yêu cầu exhaustive nên compiler từ chối. Thêm `default -> {}` để có nhánh không làm gì, hoặc xử lý từng loại cần thiết. Khi đầu vào có thể bằng `null`, xét thêm `case null` nếu không muốn ném `NullPointerException`.

Đừng nhầm với ví dụ traditional `switch` statement chỉ có một nhánh enum tại mục 2: một trường hợp không yêu cầu exhaustive; trường hợp còn lại có yêu cầu.

## 6. Guard `when` không tự bao phủ toàn bộ một kiểu

Xét một `sealed` hierarchy có `Circle` và `Square` như mục trước:

```java
static String describe(Shape shape) {
    return switch (shape) {
        case Circle(int radius) when radius > 0 ->
            "Positive circle";
        case Square(int side) -> "Square";
    };
}
```

Đoạn này **không biên dịch** vì một `Circle(0)` hoặc `Circle(-2)` vẫn có thể được tạo ra với record định nghĩa ở trên. Pattern `Circle(int radius)` khớp, nhưng guard `radius > 0` sai. Như vậy vẫn thiếu đường xử lý cho `Circle`.

Một bản exhaustive là:

```java
static String describe(Shape shape) {
    return switch (shape) {
        case Circle(int radius) when radius > 0 ->
            "Positive circle";
        case Circle(int radius) ->
            "Non-positive circle";
        case Square(int side) -> "Square";
    };
}
```

Nhánh `Circle` không guard đứng sau bảo đảm các giá trị `Circle` còn lại vẫn được nhận. Có thể dùng `default` khi phù hợp, nhưng case rõ ràng giúp trình bày đủ các dạng.

### Guard và thứ tự nhánh

Compiler còn kiểm tra **dominance** (nhánh trước bao phủ nhánh sau). Ví dụ:

```java
// Cố ý lỗi: nhánh sau bị bao phủ.
return switch (shape) {
    case Circle(int radius) -> "Any circle";
    case Circle(int radius) when radius > 0 ->
        "Positive circle";
    case Square(int side) -> "Square";
};
```

Dù tập kiểu đã được bao phủ, nhánh guard phía sau không bao giờ có cơ hội được chọn vì nhánh `Circle` không guard đứng trước nhận mọi giá trị `Circle`. Sửa bằng cách đặt **case cụ thể có guard trước**, rồi đến case không guard.

**Hai phép kiểm tra khác nhau:**
- *Exhaustiveness* hỏi: có giá trị nào chưa được xử lý?
- *Dominance* hỏi: có nhãn nào bị nhãn đứng trước che khuất khiến nó không thể được chọn?

Một `switch` có thể đủ bao phủ nhưng vẫn lỗi biên dịch vì dominance.

## 7. Record patterns và khả năng bao phủ

Record pattern khai báo trực tiếp cấu trúc dữ liệu cần khớp. Trong chương trình hoàn chỉnh ở mục 4:

```java
case Literal(int n) -> n;
case Add(var left, var right) -> evaluate(left) + evaluate(right);
case Negate(var inner) -> -evaluate(inner);
```

Ba pattern này lần lượt bao phủ ba record được phép của `Expr`. Các component pattern `int n` và `var left/right/inner` có kiểu phù hợp với khai báo record, nên không tạo ra một dạng `Literal`, `Add` hay `Negate` chưa được nhận chỉ vì giá trị thành phần thông thường.

Tuy nhiên, **không phải mọi record pattern lồng nhau đều tự động bao phủ tất cả giá trị của record ngoài**. Ví dụ với:

```java
record Point(int x, int y) {}
record Container(Point point) {}
```

Nếu viết:

```java
case Container(Point(int x, int y)) -> "Has point";
```

nhãn này chỉ khớp khi thành phần `point` bên trong khớp record pattern `Point(...)`. Nếu `point` bằng `null`, nested record pattern không khớp. Có thể cần case bổ sung, một component pattern phù hợp hơn, hoặc `default` tùy kiểu selector và yêu cầu nghiệp vụ.

**Lưu ý về giá trị `null` bên trong record:** pattern `var p` (một dạng unconditional component type pattern) có thể nhận thành phần `null` của record trong Java 21, trong khi record pattern lồng `Point(...)` không khớp `null`. Đừng suy diễn rằng mọi component pattern có cùng khả năng khớp rỗng.

Ngoài ra, **exhaustiveness chỉ là kiểm tra cấu trúc tĩnh**. Nếu `Add.left()` trả `null`, nhánh `Add(var left, var right)` vẫn có thể được chọn nhưng lệnh `evaluate(left)` có thể ném `NullPointerException`. Đó là vấn đề hợp đồng dữ liệu và runtime, không đồng nghĩa thiếu một subtype ở `switch`.

## 8. `null`: exhaustive không đồng nghĩa null-safe

Đây là khác biệt rất quan trọng:

```java
record Box(int number) {}

static String show(Box box) {
    return switch (box) {
        case Box(int number) -> "Box:" + number;
    };
}
```

Biểu thức này có thể được compiler chứng minh exhaustive về kiểu `Box` **khác `null`**; nó không có `case null`. Gọi `show(null)` vẫn có thể ném `NullPointerException`.

Muốn xử lý `null` thành một giá trị cụ thể:

```java
static String show(Box box) {
    return switch (box) {
        case null -> "Missing";
        case Box(int number) -> "Box:" + number;
    };
}
```

Với selector kiểu `Object`:

```java
static String show(Object value) {
    return switch (value) {
        case String text -> "Text:" + text;
        case null, default -> "Other";
    };
}
```

Nhánh `case null, default` xử lý selector `null` **và** những đối tượng không khớp `String`. Nếu không muốn gộp hai loại này, viết `case null` và `default` riêng.

Không nên viết quy tắc “hễ có `default` thì `null` chắc chắn được xử lý”. Đối với pattern `switch` của Java 21, `default` thông thường không tự bắt giá trị `null`.

## 9. Kiểm tra tại compile time khác sự an toàn lúc runtime

Compiler có thể chứng minh `switch` exhaustive **ở thời điểm biên dịch**, nhưng chương trình vẫn có thể gặp ngoại lệ khi chạy:

- **Selector `null`:** nếu thiếu `case null`, chương trình có thể ném `NullPointerException` khi đánh giá `switch`.
- **Dữ liệu bên trong record không hợp lệ:** record pattern khớp nhưng hành động của nhánh có thể lỗi vì số âm, thành phần `null`, chia cho 0, gọi API thất bại...
- **Thay đổi kiểu giữa các bản build:** khi enum/sealed hierarchy được thay đổi và những lớp đã biên dịch trước vẫn chạy với định nghĩa mới mà không được biên dịch lại nhất quán, một `switch` được coi là exhaustive ở bản build cũ có thể gặp giá trị mới chưa có nhánh. Trong Java 21, trường hợp không nhãn nào áp dụng ở runtime có thể dẫn đến `MatchException` (khác với `NullPointerException` dành cho selector rỗng).

Vì vậy, **exhaustiveness không phải là bảo đảm “hàm này không bao giờ ném ngoại lệ”**. Nó là bảo đảm về **độ bao phủ nhãn theo hệ thống kiểu** lúc biên dịch, với các quy tắc runtime bổ sung.

### Khi nào dùng `default`?

Nên cân nhắc:

- Với selector kiểu **mở** như `Object`: `default` thường cần thiết, trừ khi có pattern tổng quát đã bao phủ giá trị còn lại.
- Với **enum/sealed hierarchy có tập trường hợp đóng**: thường **không thêm `default`** khi mục tiêu là để compiler nhắc cập nhật logic nếu thêm trạng thái/kiểu con. Vẫn có ngoại lệ: yêu cầu nghiệp vụ có thể muốn một hành vi fallback chung.
- Với nhãn `when` chỉ nhận một phần giá trị: cần case không guard phù hợp hoặc `default`.
- Với đầu vào có thể `null`: quyết định chính sách riêng cho `null`; đừng dùng `default` như cách thay thế ngầm định.

## 10. Cách kiểm tra và sửa lỗi “switch chưa exhaustive”

Khi gặp thông báo kiểu “switch expression does not cover all possible input values” hoặc “switch statement does not cover all possible input values”, xử lý theo các bước:

1. **Xác định dạng `switch`:** expression, enhanced statement, hay traditional statement?
2. **Đọc kiểu tĩnh của selector:** `enum`, `sealed interface`, record cụ thể, hay kiểu mở như `Object`?
3. **Liệt kê mọi trường hợp có thể:** tất cả enum constants, các permitted subtypes, hoặc các kiểu chưa nhận với selector mở.
4. **Xem mỗi nhãn `case` có thực sự bao phủ cả kiểu không:** nhánh có `when` có thể chỉ nhận một phần; record pattern lồng có thể có thành phần không khớp.
5. **Đảm bảo không có nhánh bị dominance:** nhánh tổng quát không được đặt trước nhánh cụ thể cần chạy.
6. **Bổ sung case có ý nghĩa nghiệp vụ hoặc fallback:** với enum/sealed, nên thêm nhánh còn thiếu; với kiểu mở, cân nhắc `default`.
7. **Kiểm tra riêng `null`:** thêm `case null` nếu cần, không suy ra từ `default`.
8. **Biên dịch với đúng phiên bản dự án:** `javac --release 21` hoặc cấu hình tương đương trong IDE/build tool; tránh nhầm tính năng preview của phiên bản khác.

Không nên “sửa cho qua lỗi” bằng cách thêm `default -> null` hoặc `default -> 0` một cách máy móc. Nếu trường hợp bị thiếu là trạng thái nghiệp vụ quan trọng, một giá trị mặc định tùy tiện có thể làm lỗi âm thầm thay vì được phát hiện sớm.

## 11. Bảng tổng kết

| Selector / thiết kế | Nhánh hiện có | Exhaustive theo Java 21? | Điều cần chú ý |
| --- | --- | --- | --- |
| `enum Light {RED,YELLOW,GREEN}` | Chỉ `RED`, `YELLOW` trong switch expression | Không | Thiếu `GREEN` |
| Cùng enum | Đủ ba hằng, không `default` | Có | Selector `null` vẫn có thể ném NPE |
| `sealed Expr` với ba record | `Literal`, `Add`, `Negate` | Có | Hành động đệ quy vẫn phải xử lý dữ liệu hợp lệ |
| `Object` | Chỉ `String` và `Integer` | Không | Còn nhiều kiểu khác |
| `Object` | `String`, `Integer`, `default` | Có đối với các giá trị khác `null` | `null` cần xử lý riêng nếu muốn không ném NPE |
| `Shape` với `Circle` và `Square` | `Circle` có guard `radius > 0`, `Square` | Không | Các `Circle` không thỏa guard bị bỏ sót |
| Enhanced statement trên `Object` | Chỉ `case String s` | Không | Enhanced switch statement cũng cần exhaustive |
| Traditional statement trên enum | Chỉ `case RED: ... break;` | Không bắt buộc | Với các hằng khác, có thể không làm gì |

## 12. Tự kiểm tra kiến thức

**Bài 1 — Enum thêm trạng thái.** Có `enum Mode { AUTO, MANUAL }` và switch expression với đủ hai nhánh. Sau này thêm `PAUSED` rồi biên dịch lại dự án. Nếu không có `default`, điều gì xảy ra?

**Đáp án:** Compiler thấy `PAUSED` chưa được bao phủ và buộc cập nhật switch expression. Đây là một lợi ích của exhaustive `switch` đối với enum đóng.

**Bài 2 — Guard chưa bao phủ.** Với `sealed interface Shape permits Circle, Square`, tại sao `case Circle(int r) when r > 0` cùng `case Square(int s)` chưa đủ?

**Đáp án:** `Circle(0)` và `Circle(-1)` vẫn hợp lệ theo khai báo. Guard có thể sai, nên cần thêm một nhánh `Circle` không guard hoặc một fallback phù hợp.

**Bài 3 — Null.** Với `Object x = null`, switch expression có `case String s -> ...; default -> ...;` đã exhaustive đối với các giá trị khác `null`. Có chắc chạy vào `default` không?

**Đáp án:** Không. `null` không được `default` thông thường tự động bắt trong Java 21. Muốn xử lý, thêm `case null -> ...` hoặc dùng `case null, default -> ...`.

**Bài 4 — Statement truyền thống.** Vì sao `switch (light) { case RED: ...; break; }` có thể biên dịch mặc dù enum có ba hằng?

**Đáp án:** Đây là traditional switch statement, không bắt buộc exhaustive. Nếu cần compiler kiểm tra đầy đủ, có thể tổ chức logic thành switch expression, hoặc chủ động bao phủ mọi trạng thái một cách rõ ràng.

**Ghi nhớ:** **Exhaustiveness là khả năng compiler chứng minh không còn trường hợp kiểu nào chưa được một nhãn phù hợp bao phủ.** Nó đặc biệt hữu ích với enum và sealed hierarchies, nhưng phải kết hợp hiểu biết về guards, record patterns, nhánh `default`, selector `null` và sự khác biệt giữa switch expression và switch statement.

## Tài liệu tham khảo chính thức

- [Oracle Java 21 — Pattern Matching for `switch`](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21 — §14.11: Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Java Language Specification 21 — §15.28: Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440).