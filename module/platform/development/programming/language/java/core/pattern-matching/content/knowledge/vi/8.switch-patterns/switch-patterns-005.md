# Record pattern trong nhãn `case` của `switch` (Java 21)

## 1. Record pattern trong `case` giải quyết việc gì?

Một `record` gom các thành phần dữ liệu có tên và kiểu xác định. Ví dụ, `record Point(int x, int y) {}` biểu diễn một điểm với hai thành phần `x` và `y`.

Khi xử lý một đối tượng trong `switch`, có hai cách tiếp cận:

```java
// Type pattern: lấy cả đối tượng, rồi gọi accessor.
case Point p -> "x=" + p.x() + ", y=" + p.y();

// Record pattern: kiểm tra Point và tách các thành phần ngay tại case.
case Point(int x, int y) -> "x=" + x + ", y=" + y;
```

Hai dòng là **hai nhánh minh họa riêng lẻ**, không đặt cùng nhau trong một `switch` vì nhánh tổng quát đứng trước có thể che khuất nhánh sau.

Với **record pattern** `Point(int x, int y)`, Java:

1. Kiểm tra giá trị đang xét có khớp kiểu record `Point` hay không.
2. Lấy các thành phần record thông qua accessor tương ứng (`x()`, `y()`).
3. Khớp từng thành phần với pattern con được khai báo.
4. Nếu tất cả khớp, gắn biến pattern `x`, `y` và thực thi nhánh `case` tương ứng.

Vì thế, record pattern giúp viết trực tiếp **cấu trúc dữ liệu cần nhận** trong nhãn `case`, thay vì nhận cả record rồi tự lấy các trường bằng nhiều câu lệnh.

**Phiên bản:** Record patterns (JEP 440) và pattern matching cho `switch` (JEP 441) đều được chuẩn hóa trong **Java 21**. Các ví dụ `case Point(...)` trong bài yêu cầu mức ngôn ngữ Java 21 trở lên và không cần `--enable-preview` khi biên dịch với `--release 21`. Java 17 có record và pattern matching cho `instanceof`, nhưng chưa hỗ trợ ổn định cú pháp record pattern trong `case`.

## 2. Cú pháp và các thành phần của nhãn `case`

Xét record:

```java
record Point(int x, int y) {}
```

Một nhánh `switch` dùng record pattern:

```java
case Point(int x, int y) -> System.out.println(x + y);
```

Cú pháp tổng quát:

```text
case RecordType(componentPattern1, componentPattern2, ...)
    [when booleanCondition] -> expression-or-statement
```

Trong đó:

- `RecordType` phải chỉ một **kiểu record**, ví dụ `Point`; Java không cho dùng cú pháp deconstruction này cho một lớp Java thông thường chỉ có getter.
- Danh sách component pattern nằm trong `(...)` và phải có **đúng số thành phần, đúng thứ tự** tương ứng với khai báo record; record không có component dùng pattern `Empty()`.
- `int x`, `int y` là các **pattern con**: khi khớp, chúng tạo biến `x`, `y` cho nhánh được chọn.
- `when booleanCondition` là **guard** tùy chọn, đánh giá sau khi record pattern khớp; guard có thể sử dụng những biến vừa được gắn.
- `->` xác định phần được thực thi/trả về khi nhánh được chọn. Trong `switch` expression, nhánh có thể cho ra giá trị; trong `switch` statement, nhánh có thể thực thi statement hoặc block.

Ví dụ guard đúng vị trí:

```java
case Point(int x, int y) when x == y -> "Điểm nằm trên đường y=x";
```

Không đặt `when` giữa các pattern con hoặc trước phần `Point(...)`. Cú pháp đúng là **`case <pattern> when <điều kiện> ->`**.

### Dùng `var` để suy luận kiểu thành phần

Với `record Point(int x, int y) {}`, có thể viết:

```java
case Point(var x, var y) -> "Point: " + x + "," + y;
```

Ở đây `x` và `y` được suy luận kiểu `int` từ thành phần tương ứng của `Point`. `var` **không làm các biến thành `Object`**; trình biên dịch biết kiểu từ khai báo record.

Sử dụng `var` khi không cần lặp lại tên kiểu đã rõ. Viết kiểu tường minh khi nó giúp người đọc hiểu cấu trúc hoặc làm ví dụ giảng dạy rõ ràng hơn.

## 3. Ví dụ Java 21 chạy độc lập: `case`, `when` và record lồng nhau

Tạo tệp **`RecordPatternCaseDemo.java`**:

```java
public class RecordPatternCaseDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}
    record NamedPoint(Point point, String label) {}

    static String describe(Object value) {
        return switch (value) {
            case null -> "NULL";

            case Point(int x, int y) when x == y ->
                "DIAGONAL " + x;

            case Point(int x, int y) ->
                "POINT " + x + "," + y;

            case Segment(
                    Point(int sx, int sy),
                    Point(int ex, int ey)) ->
                "SEGMENT (" + sx + "," + sy
                    + ")->(" + ex + "," + ey + ")";

            case NamedPoint(Point(int x, int y), String label)
                    when label != null && !label.isBlank() ->
                "NAMED " + label + " @ " + x + "," + y;

            case NamedPoint(var point, var label) ->
                "UNNAMED";

            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        Object[] values = {
            new Point(2, 2),
            new Point(2, 3),
            new Segment(new Point(0, 1), new Point(2, 4)),
            new NamedPoint(new Point(3, 4), "A"),
            new NamedPoint(new Point(3, 4), null),
            new NamedPoint(null, "B"),
            null,
            "hello"
        };

        for (Object value : values) {
            System.out.println(describe(value));
        }
    }
}
```

Biên dịch bằng **JDK 21 trở lên** với mức nguồn Java 21:

```bash
javac --release 21 RecordPatternCaseDemo.java
java RecordPatternCaseDemo
```

Kết quả stdout:

```text
DIAGONAL 2
POINT 2,3
SEGMENT (0,1)->(2,4)
NAMED A @ 3,4
UNNAMED
UNNAMED
NULL
OTHER
```

Vì sao mỗi nhánh được chọn:

1. `Point(2, 2)` khớp `Point(int x, int y)` và guard `x == y` đúng, nên trả `DIAGONAL 2`.
2. `Point(2, 3)` cũng khớp record `Point`, nhưng guard `x == y` sai. Java xét nhánh `case Point(int x, int y)` ngay sau và trả `POINT 2,3`.
3. `Segment(Point(0, 1), Point(2, 4))` khớp **record pattern lồng nhau**, tách bốn biến `sx`, `sy`, `ex`, `ey`.
4. `NamedPoint(Point(3, 4), "A")` khớp record lồng nhau, guard xác nhận nhãn khác `null` và không rỗng/trắng, nên trả `NAMED A @ 3,4`.
5. `NamedPoint(Point(3, 4), null)` không qua guard vì `label == null`; nhánh `NamedPoint(var point, var label)` bắt trường hợp còn lại.
6. `NamedPoint(null, "B")` không khớp pattern lồng `Point(int x, int y)` vì thành phần `point` bằng `null`; nhánh `NamedPoint(var point, var label)` vẫn khớp.
7. Giá trị selector là `null` được xử lý bằng `case null`.
8. Chuỗi `"hello"` không phải `Point`, `Segment` hoặc `NamedPoint`, nên rơi vào `default`.

Ở đây toàn bộ `switch` là **một biểu thức** trả về `String`. Mỗi nhánh `->` cung cấp chuỗi kết quả. Khối `switch` có `default` vì đầu vào `Object` có thể thuộc nhiều kiểu ngoài các record đã khai báo.

## 4. Tách thành phần record: cơ chế khớp và biến pattern

So sánh hai cách cùng kiểm tra một `Point`.

**Type pattern:**

```java
case Point point -> "x=" + point.x() + ", y=" + point.y();
```

**Record pattern:**

```java
case Point(int x, int y) -> "x=" + x + ", y=" + y;
```

Cả hai đều bắt giá trị `Point`, nhưng record pattern còn yêu cầu các **component pattern** khớp và trực tiếp khai báo biến `x`, `y`. Cấu trúc này rất có ích khi record chỉ dùng để mang dữ liệu và bạn muốn xử lý ngay các thành phần.

Một record pattern không phải lời gọi constructor `new Point(...)`: nó **phân rã giá trị đã tồn tại** bằng cách lấy các thành phần tương ứng qua accessor. Nó cũng không tạo một `Point` mới.

Biến pattern có phạm vi tương ứng với case được chọn. Trong biểu thức:

```java
return switch (value) {
    case Point(int x, int y) when x > 0 && y > 0 ->
        "Quadrant I";
    case Point(int x, int y) ->
        "Other point";
    default ->
        "Not a point";
};
```

Những biến `x`, `y` ở nhánh đầu và nhánh thứ hai là **hai nhóm biến pattern khác nhau**, được phép dùng lại tên vì phạm vi các rule không chồng lấn. Guard của nhánh đầu có thể dùng `x`, `y`. Ở nhánh `default`, không có những biến này.

**Lưu ý:** đoạn trên là một **minh họa phần thân của phương thức trả về `String`** có tham số hoặc biến `value`; không phải chương trình Java độc lập.

## 5. Nested record pattern: khớp cấu trúc nhiều tầng

Record có thể chứa record khác:

```java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}
```

Nếu chỉ viết type pattern:

```java
case Segment segment ->
    segment.start().x() + "," + segment.end().y();
```

Bạn nhận cả `segment` và tự gọi accessor.

Với nested record pattern:

```java
case Segment(Point(int sx, int sy), Point(int ex, int ey)) ->
    sx + "," + sy + " -> " + ex + "," + ey;
```

Java kiểm tra `Segment`, lấy `start` và `end` rồi tiếp tục khớp chúng như `Point`. Chỉ khi **các pattern con đều khớp**, nhánh mới được chọn và các biến thành phần mới được sử dụng trong thân nhánh.

Nếu `start` hoặc `end` là `null`, pattern con `Point(int ..., int ...)` **không khớp**. Nhánh `case Segment(...)` này bị bỏ qua và chương trình tìm nhánh `case` khác phù hợp, chẳng hạn `case Segment(var start, var end)` hoặc `default`. Điều này không đồng nghĩa Java tự động gọi `start.x()` trên giá trị `null`.

Tách cấu trúc hai hoặc ba tầng là hợp lý nếu giúp bộc lộ ý nghĩa của dữ liệu. Với record rất sâu, một số tên tạm hoặc phương thức xử lý riêng có thể dễ đọc hơn một pattern lồng quá nhiều dấu ngoặc.

## 6. Guard `when` lọc sau khi pattern đã khớp

Record pattern mô tả **hình dạng và kiểu dữ liệu**. Guard `when` đặt thêm một điều kiện logic trên các thành phần đã tách:

```java
return switch (value) {
    case Point(int x, int y) when x == 0 && y == 0 ->
        "Origin";
    case Point(int x, int y) when x >= 0 && y >= 0 ->
        "Nonnegative quadrant";
    case Point(int x, int y) ->
        "Other point";
    default ->
        "Not a point";
};
```

Ví dụ:
- `Point(0, 0)` trả `Origin`.
- `Point(2, 3)` trả `Nonnegative quadrant`.
- `Point(-1, 3)` trả `Other point`.

Đây là ba nhánh mẫu cùng kiểu record với các điều kiện từ cụ thể đến tổng quát. Guard **không thay đổi định nghĩa record**, không ép kiểu và không tự sửa thành phần. Nó chỉ quyết định có chấp nhận nhãn `case` hiện tại hay cần xét nhánh tiếp.

Với `when x > 0 && y > 0`, điều kiện được đánh giá theo quy tắc Java bình thường; nếu guard gọi phương thức có side effect thì lời gọi cũng có thể thực sự chạy. Việc khớp record có thể gọi accessor của record. Vì thế không nên giả định mọi biểu thức liên quan đến pattern đều “không thực thi mã”.

**Thứ tự nhánh đặc biệt quan trọng.** Nếu đặt một pattern không có guard, đủ tổng quát để khớp mọi `Point`, **trước** một nhánh `Point` có guard, nhánh sau có thể bị compiler bác bỏ vì bị nhánh trước bao phủ (*dominated case label*).

## 7. `null`: selector và thành phần record không có cùng quy tắc

Đây là điểm dễ nhầm trong record patterns của Java 21.

### Selector `null`

Bản thân `null` **không khớp một record pattern**:

```java
switch (value) {
    case null -> System.out.println("No value");
    case Point(int x, int y) -> System.out.println(x + y);
    default -> System.out.println("Other");
}
```

Đây là đoạn minh họa trong phương thức với `value`. Nếu `value == null`, chỉ nhánh `case null` được chọn. Nếu bỏ xử lý `null`, một pattern `switch` thông thường với selector `null` có thể ném `NullPointerException` **trước khi** đến `default`; `default` không tự thay thế `case null`.

### Thành phần record có thể bằng `null`

Giả sử:

```java
record NamedPoint(Point point, String label) {}
```

Khi viết:

```java
case NamedPoint(Point(int x, int y), String label)
        when label != null && !label.isBlank() -> ...
```

Có **hai kiểu pattern con** khác nhau:

- `Point(int x, int y)` là **record pattern lồng nhau**. Nó **không khớp `null`** ở thành phần `point`.
- `String label` là **type pattern trực tiếp cho thành phần `String`**. Trong Java 21, vì nó là pattern *unconditional* đối với kiểu khai báo `String` của thành phần, nó thuộc trường hợp **null-matching component pattern**: nó **có thể gắn `label = null`**. Vì vậy guard phải kiểm tra `label != null` trước khi gọi `label.isBlank()`.

Điểm này khác với `object instanceof String s` ở cấp ngoài, nơi `object == null` luôn làm phép `instanceof` trả `false`. Không nên lấy quy tắc `instanceof` với selector `null` rồi áp đặt cho mọi **component pattern** bên trong record.

Một fallback dùng `var` có thể nhận cả những giá trị thành phần bằng `null` khi nó là type pattern unconditional theo kiểu thành phần:

```java
case NamedPoint(var point, var label) -> "Incomplete";
```

Trong ví dụ chạy độc lập phía trên, nhánh này xử lý cả record có nhãn `null` và record có vị trí `null`. Nếu không muốn cho phép các thành phần rỗng, nên kiểm tra giá trị trong constructor của record hoặc xử lý rõ trong nhánh `case`.

## 8. Tính bao phủ của `switch` và record pattern

### `switch` expression phải đầy đủ các trường hợp

Một `switch` expression phải **exhaustive**: trình biên dịch cần thấy có cách xử lý những giá trị selector có thể xảy ra. Với selector kiểu `Object`, thường dùng `default`:

```java
return switch (value) {
    case Point(int x, int y) -> "Point";
    default -> "Something else";
};
```

Đoạn này xử lý các kiểu không phải `Point` thông qua `default`, nhưng nếu `value` là `null` thì vẫn cần cân nhắc `case null` như đã giải thích.

### Có thể exhaustive mà không cần `default` khi dùng `sealed`

Ví dụ nâng cao Java 21, đặt các khai báo sau trong cùng một tệp (mỗi record là một lớp được phép của giao diện sealed):

```java
sealed interface Expr permits Literal, Sum {}
record Literal(int value) implements Expr {}
record Sum(Expr left, Expr right) implements Expr {}

static int evaluate(Expr expr) {
    return switch (expr) {
        case Literal(int value) -> value;
        case Sum(var left, var right) ->
            evaluate(left) + evaluate(right);
    };
}
```

Phương thức `evaluate` cần được **đặt trong một lớp chứa**, còn các type declarations tương ứng ở phạm vi được Java cho phép; đây là mã minh họa mối quan hệ sealed và record patterns, không phải một tệp độc lập như chương trình tại mục 3.

Với các lớp hiện được `Expr` cho phép, compiler có thể chứng minh các case record bao phủ mọi kiểu triển khai hợp lệ **khác `null`**. Nếu gọi `evaluate(null)` thì selector `null` vẫn có thể dẫn đến `NullPointerException`; nếu một thành phần `left/right` là `null`, lời gọi đệ quy cũng cần được xử lý theo hợp đồng dữ liệu. Đừng nhầm “exhaustive về kiểu” với “không cần quan tâm null trong dữ liệu”.

## 9. Các lỗi thường gặp khi viết record pattern trong `case`

| Lỗi hoặc nhầm lẫn | Ví dụ / nguyên nhân | Cách sửa |
| --- | --- | --- |
| Dùng Java 17 như thể đã hỗ trợ chuẩn Java 21 | `case Point(int x, int y) ->` ở mức nguồn Java 17 | Nâng mức ngôn ngữ lên Java 21+ hoặc dùng `case Point p ->` theo hỗ trợ pattern switch phù hợp phiên bản |
| Số component không đúng | `Point(int x)` với `record Point(int x, int y)` | Cung cấp đúng hai component pattern, theo thứ tự khai báo |
| Kiểu component không tương thích | `Point(String x, int y)` khi `x` của record là `int` | Dùng `int x` hoặc `var x` |
| Dùng deconstruction với lớp thường | `case NormalClass(var x) ->` dù `NormalClass` không phải record | Dùng type pattern `case NormalClass obj ->` và accessor của lớp |
| Guard đặt sai vị trí | Đưa `when` vào bên trong `Point(...)` | Đặt `when` sau dấu `)` của record pattern |
| Case tổng quát che case cụ thể | `case Point(var x, var y) ->` đứng trước `case Point(int x, int y) when x == y ->` | Đưa case có guard cụ thể lên trước |
| Trùng tên biến trong cùng record pattern | `Point(int n, int n)` | Dùng hai tên phân biệt, ví dụ `x` và `y` |
| Nhầm `null` ở record lồng nhau với type pattern | `Point(...)` không khớp một component `null`, nhưng type pattern trực tiếp có thể null-matching | Kiểm tra riêng dữ liệu rỗng và xét kiểu pattern con |
| Quên `default` hoặc độ bao phủ | Selector `Object` có thể có nhiều kiểu khác | Thêm nhánh phù hợp hoặc chứng minh exhaustiveness trên một hierarchy sealed |

### Một số ví dụ biên dịch lỗi

Các dòng dưới đây **cố ý không hợp lệ**, chỉ để nhận biết lỗi:

```java
// Point có đúng hai thành phần; thiếu một thành phần.
// case Point(int x) -> "bad";

// Point.x() trả về int, không khớp type pattern String.
// case Point(String x, int y) -> "bad";

// Hai biến trùng tên trong cùng record pattern.
// case Point(int n, int n) -> "bad";
```

Nếu bạn cần xác thực dữ liệu nghiệp vụ như tọa độ dương hoặc một chuỗi không rỗng, dùng `when` và guard tương ứng, hoặc đặt invariant hợp lệ trong constructor của record. Record pattern **không tự biến bất kỳ điều kiện nghiệp vụ nào thành kiểm tra cấu trúc**.

## 10. Khi nào nên dùng `case Record(...)`?

Record pattern trong nhãn `case` phù hợp nhất khi:

1. Đầu vào có thể là nhiều loại record và bạn cần chọn cách xử lý theo **hình dạng dữ liệu**.
2. Nhánh cần trực tiếp các thành phần record, thay vì giữ cả đối tượng và gọi accessor nhiều lần.
3. Cấu trúc có một hoặc hai tầng record lồng nhau, khiến việc deconstruct giúp mã dễ hiểu hơn.
4. Cần guard theo giá trị thành phần, như `case Point(int x, int y) when x == y`.
5. Đang xây dựng một mô hình dữ liệu kiểu sealed + records để xử lý các biến thể rõ ràng.

Nếu bạn chỉ cần truyền nguyên một đối tượng record cho phương thức khác, **type pattern** như `case Point point -> process(point)` có thể ngắn và rõ hơn. Record pattern không bắt buộc cho mọi nhánh `switch`; chọn theo lượng dữ liệu thực sự cần.

## 11. Tự kiểm tra

Với khai báo:

```java
record Point(int x, int y) {}
Object value = new Point(5, 5);
```

Và biểu thức trong một phương thức Java 21:

```java
String result = switch (value) {
    case null -> "null";
    case Point(int x, int y) when x > y -> "greater";
    case Point(int x, int y) when x == y -> "equal";
    case Point(int x, int y) -> "other point";
    default -> "other type";
};
```

**Hỏi:** `result` là gì? **Đáp:** `"equal"`. Cả ba record patterns `Point(...)` đều có cấu trúc phù hợp, nhưng nhánh đầu có guard sai, nhánh thứ hai có guard đúng và được chọn. Nhánh tổng quát đứng sau vẫn có vai trò xử lý các `Point` không thỏa guard nào.

**Thử thay `value = null`:** khi đó `case null` được chọn, không có record pattern nào khớp selector `null`.

**Thử thay `value = new Point(5, 3)`:** guard đầu đúng nên kết quả là `"greater"`; các nhánh tiếp theo không được thực thi.

**Ghi nhớ:** `case RecordType(componentPatterns...)` kết hợp **kiểm tra kiểu record**, **tách các thành phần**, và **gắn biến pattern** trong cùng nhãn `case`. Guard `when` kiểm tra điều kiện bổ sung; thứ tự nhánh quyết định rule phù hợp đầu tiên. Record pattern có thể lồng nhau, nhưng cần phân biệt `null` của selector với `null` của thành phần record và dùng cú pháp Java 21+.

## Tài liệu chính thức

- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21 — §14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
- [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440) và [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).