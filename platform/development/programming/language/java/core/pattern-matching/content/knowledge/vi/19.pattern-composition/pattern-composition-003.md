# Kết hợp pattern với guard trong Java 21+

## 1. Guard bổ sung điều kiện cho pattern như thế nào?

**Pattern** trả lời câu hỏi “giá trị có đúng kiểu/cấu trúc cần tìm không, và có thể lấy dữ liệu nào từ đó?”. **Guard** thêm một điều kiện Boolean chỉ được xét **sau khi pattern khớp thành công**. Hai bước này cho phép viết logic phân nhánh vừa dựa trên cấu trúc dữ liệu, vừa dựa trên ràng buộc nghiệp vụ.

Ví dụ một record biểu diễn tọa độ:

```java
record Point(int x, int y) {}
```

Để phân loại một điểm thuộc góc phần tư thứ nhất, phải kiểm tra cả **kiểu/cấu trúc** lẫn **giá trị tọa độ**:

```java
String result = switch (value) {
    case Point(int x, int y) when x > 0 && y > 0 -> "Quadrant I";
    case Point(int x, int y) -> "Other point";
    case null -> "Missing";
    default -> "Unknown";
};
```

- `Point(int x, int y)` là **record pattern**: nhận một `Point` và lấy hai component `x`, `y`.
- `when x > 0 && y > 0` là **guard**: chỉ khi pattern khớp mới kiểm tra tọa độ.
- Khi guard không đúng, `switch` tiếp tục xét các nhánh phía sau, chẳng hạn nhánh `Point(...)` tổng quát.
- `case null` và `default` có vai trò khác nhau: nhánh null xử lý selector null, còn default xử lý những giá trị còn lại.

Tính năng *pattern matching for switch* và cú pháp `when` chính thức từ **Java 21** (JEP 441). Record patterns cũng chính thức từ **Java 21** (JEP 440). Các ví dụ dùng JDK 21+, không cần `--enable-preview`. Java 17 không hỗ trợ các cú pháp `switch` pattern/record pattern chính thức này.

## 2. Hai cách kết hợp pattern với điều kiện

### 2.1. `when` trong `switch`

Cú pháp cơ bản:

```java
switch (selector) {
    case SomeType variable when booleanCondition -> ...;
    case SomeType variable -> ...;
    default -> ...;
}
```

Với record pattern:

```java
switch (value) {
    case Point(int x, int y) when x == 0 && y == 0 -> "Origin";
    case Point(int x, int y) when x > 0 && y > 0 -> "Quadrant I";
    case Point(int x, int y) -> "Another point";
    default -> "Other";
}
```

`when` nằm sau pattern trong nhãn `case`, trước `->` (hoặc `:` nếu dùng dạng statement truyền thống). Biểu thức theo sau `when` phải có kiểu `boolean` và có thể truy cập các biến pattern `x`, `y` đã được ràng buộc.

Nếu pattern không khớp, guard **không được đánh giá**. Nếu pattern khớp nhưng guard trả `false`, nhánh không được chọn và `switch` xét nhãn kế tiếp. Nếu guard ném ngoại lệ, ngoại lệ được truyền ra; Java không coi đó là một lần khớp thất bại bình thường.

**Không viết `when` vào cú pháp `instanceof`.** `when` là cú pháp guard dành cho nhãn pattern trong `switch`.

### 2.2. `&&` khi dùng `instanceof`

Đối với `if`, ghép pattern matching với toán tử AND ngắn mạch:

```java
static boolean inQuadrantI(Object value) {
    return value instanceof Point(int x, int y)
            && x > 0
            && y > 0;
}
```

Phần bên phải `&&` chỉ được xét nếu `instanceof Point(...)` thành công. Java biết `x`, `y` đã được gán trong phần còn lại của điều kiện, nên các biến này nằm trong scope hợp lệ.

Có thể thêm nhiều điều kiện liên tiếp:

```java
if (value instanceof Point(int x, int y)
        && x >= 0
        && y >= 0
        && x + y <= 100) {
    System.out.println("Point inside allowed region");
}
```

Lưu ý: tổng `x + y` là phép cộng `int` có thể tràn số với giá trị cực lớn. Khi làm điều kiện giới hạn số học nhạy cảm, cân nhắc ép lên `long`: `(long) x + y <= 100`.

**Khác biệt cú pháp:** với `switch` dùng `case Point(...) when condition`; với `if` dùng `if (value instanceof Point(...) && condition)`.

## 3. Ví dụ Java hoàn chỉnh: type pattern, record pattern, nested pattern và sealed hierarchy

Ví dụ dưới đây minh họa ba mức kết hợp: kiểm tra dữ liệu tọa độ, kiểm tra **record pattern lồng nhau** cho hình chữ nhật, và phân nhánh theo một **sealed interface**. Lưu vào file **`GuardedPatternDemo.java`**.

```java
public class GuardedPatternDemo {
    record Point(int x, int y) {}

    record Rectangle(Point start, Point end) {}

    sealed interface Action permits Transfer, Cancel {}

    record Transfer(String account, int amount) implements Action {}

    record Cancel(String account) implements Action {}

    static String describe(Object value) {
        return switch (value) {
            case Point(int x, int y) when x == 0 && y == 0 ->
                    "Origin";

            case Point(int x, int y) when x > 0 && y > 0 ->
                    "Quadrant I";

            // Sau các nhánh có guard là nhánh Point bao phủ còn lại.
            case Point(int x, int y) ->
                    "Other point: " + x + "," + y;

            // Hai record Point lồng trong Rectangle.
            case Rectangle(
                    Point(int x1, int y1),
                    Point(int x2, int y2))
                    when x2 > x1 && y2 > y1 ->
                    "Area: " + ((x2 - x1) * (y2 - y1));

            // Bao phủ Rectangle không thỏa pattern/guard phía trên.
            case Rectangle(var from, var to) ->
                    "Invalid rectangle";

            case null -> "Missing";
            default -> "Unknown";
        };
    }

    static String handle(Action action) {
        return switch (action) {
            case Transfer(String account, int amount)
                    when amount >= 100 ->
                    "Large transfer: " + account;

            case Transfer(String account, int amount)
                    when amount > 0 ->
                    "Small transfer: " + account;

            // Cần nhánh không guard để xử lý Transfer còn lại.
            case Transfer(String account, int amount) ->
                    "Rejected transfer: " + account;

            case Cancel(String account) ->
                    "Cancel: " + account;

            case null -> "No action";
        };
    }

    static boolean inQuadrantI(Object value) {
        return value instanceof Point(int x, int y)
                && x > 0 && y > 0;
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(0, 0)));
        System.out.println(describe(new Point(3, 4)));
        System.out.println(describe(new Point(-1, 4)));

        System.out.println(describe(new Rectangle(
                new Point(0, 0), new Point(5, 4))));

        System.out.println(describe(new Rectangle(
                null, new Point(5, 4))));

        System.out.println(describe(null));
        System.out.println(describe("hello"));

        System.out.println(handle(new Transfer("A", 150)));
        System.out.println(handle(new Transfer("B", 30)));
        System.out.println(handle(new Transfer("C", 0)));
        System.out.println(handle(new Cancel("D")));
        System.out.println(handle(null));

        System.out.println(inQuadrantI(new Point(2, 3)));
        System.out.println(inQuadrantI("bad"));
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac --release 21 GuardedPatternDemo.java
java GuardedPatternDemo
```

Kết quả stdout:

```text
Origin
Quadrant I
Other point: -1,4
Area: 20
Invalid rectangle
Missing
Unknown
Large transfer: A
Small transfer: B
Rejected transfer: C
Cancel: D
No action
true
false
```

**Diễn giải điểm đáng chú ý:**

1. `new Point(0, 0)` khớp record pattern đầu tiên, sau đó guard `x == 0 && y == 0` đúng; nhánh `Origin` được chọn.
2. `new Point(3, 4)` không qua guard đầu tiên nhưng qua guard `x > 0 && y > 0`; kết quả `Quadrant I`.
3. `new Point(-1, 4)` thất bại ở cả hai guard nhưng vẫn khớp `Point(...)` không guard; kết quả `Other point: -1,4`.
4. `Rectangle(Point(...), Point(...))` deconstruct các component ở hai tầng. Guard sử dụng bốn biến tọa độ để kiểm tra hình chữ nhật hợp lệ theo giả định `start` là góc trên-trái và `end` có cả hai tọa độ lớn hơn.
5. `Rectangle(null, new Point(5, 4))` không khớp pattern `Rectangle(Point(...), Point(...))` vì `start` là null. Nhánh `Rectangle(var from, var to)` rộng hơn tiếp nhận đối tượng này và in `Invalid rectangle`.
6. `Action` là sealed interface chỉ cho phép `Transfer` và `Cancel`. `handle` xử lý hết hai biến thể (bao gồm các `Transfer` không qua guard) và trường hợp null; không cần `default`.
7. `inQuadrantI` cho thấy pattern variables có thể dùng ngay trong biểu thức Boolean với `&&`.

Ví dụ tính diện tích với `int` để tập trung vào pattern matching. Trong ứng dụng thực, cần kiểm soát miền giá trị và phép nhân/trừ có thể tràn số; cân nhắc `long` hoặc kiểm tra giới hạn trước.

## 4. Thứ tự nhánh, domination và nhánh dự phòng

### 4.1. Pattern cụ thể/guard nên đứng trước nhánh tổng quát

Xét thứ tự hợp lệ:

```java
return switch (value) {
    case Point(int x, int y) when x == 0 && y == 0 -> "Origin";
    case Point(int x, int y) when x > 0 && y > 0 -> "Quadrant I";
    case Point(int x, int y) -> "Other point";
    default -> "Other";
};
```

Nếu đặt `case Point(int x, int y)` **không guard** lên đầu thì các nhánh `Point(...) when ...` phía sau đều bị nó bao phủ, tạo trường hợp **dominated case label** mà compiler sẽ từ chối. Một nhánh có guard không hằng đúng như `x > 0` chỉ bao phủ một phần của không gian giá trị, nên các nhánh khác có thể tiếp tục xử lý.

Tương tự, với type pattern:

```java
case String s when s.isBlank() -> "Blank string";
case String s -> "Non-blank string";
```

Nhánh `String s` không guard nên đặt sau nhánh kiểm tra chuỗi trống. Nếu `s` rỗng, nhánh trước được chọn; nếu không, nhánh sau được chọn.

### 4.2. Guard không tự làm cho `switch` exhaustive

Khi chỉ viết:

```java
// Ý tưởng chưa đủ cho mọi Point:
// case Point(int x, int y) when x > 0 -> ...
```

nhánh này không xử lý `Point(0, y)` hoặc các điểm có `x < 0`. Với một `switch` expression, compiler đòi hỏi các nhánh phải bao phủ đầy đủ phạm vi thích hợp. Hãy thêm nhánh tổng quát cho `Point`, hoặc nhánh `default`/các nhánh khác phù hợp kiểu đầu vào.

Với **sealed hierarchy** trong ví dụ, các nhánh `Transfer` có guard **không thay thế** nhánh `Transfer` không guard vì `amount` có thể bằng 0 hoặc âm. Khi thêm `case Transfer(...)` không guard và `case Cancel(...)`, compiler có thể nhận ra mọi biến thể được sealed interface cho phép đã được xử lý.

### 4.3. Guard `false` khác với `break` hoặc rơi xuyên nhánh

Nếu pattern khớp mà `when` là `false`, **không có lệnh nào trong thân nhánh ấy được thực thi**; quá trình tìm nhánh khớp tiếp tục. Đây không phải `fall-through` của `switch` dạng colon cũ. Với `case ... ->`, mỗi nhánh biểu diễn một kết quả riêng.

## 5. Scope của biến pattern và short-circuit

Biến pattern chỉ có thể được sử dụng khi compiler chứng minh pattern tương ứng đã khớp:

```java
if (candidate instanceof Point(int x, int y)
        && x > 0
        && y > 0) {
    System.out.println("Accepted: " + x + "," + y);
}
```

Nếu `candidate` là chuỗi hoặc null, `instanceof` trả `false`; vế phải `&&` không chạy. Biến `x`, `y` được phép xuất hiện trong điều kiện sau `&&` và trong thân `if` đúng.

**Sai khi dùng `||` để gọi biến pattern ở nhánh có thể chưa khớp:**

```java
// Không biên dịch:
// if (candidate instanceof Point(int x, int y) || x > 0) {
//     System.out.println(y);
// }
```

Khi vế đầu `false`, vế phải `||` sẽ chạy, nhưng `x` và `y` chưa hề được gán. Cần tách điều kiện hoặc dùng `&&` đúng mục tiêu.

Trong `switch`, các biến `x` và `y` của `case Point(int x, int y) when ...` dùng được trong **guard và thân chính nhánh đó**. Biến khai báo bởi nhánh này không thể tự động dùng ở các nhánh `case` khác.

Nếu điều kiện trở nên dài, có thể đặt logic vào phương thức Boolean:

```java
static boolean validPoint(int x, int y) {
    return x >= 0 && y >= 0;
}

// Trong switch:
case Point(int x, int y) when validPoint(x, y) -> "Valid";
```

Cách này giúp đặt tên quy tắc nghiệp vụ và dễ kiểm thử độc lập. Bản thân việc gọi phương thức trong guard **không làm thay đổi quy tắc**: guard chỉ chạy sau khi pattern khớp.

## 6. Guard với nested record patterns và null

Khi nhiều record lồng nhau, mỗi tầng pattern phải khớp trước lúc Java đánh giá guard. Ví dụ:

```java
record Point(int x, int y) {}
record Rectangle(Point start, Point end) {}

// Ý tưởng kiểm tra dựa trên cấu trúc và tọa độ:
case Rectangle(
        Point(int x1, int y1),
        Point(int x2, int y2))
        when x2 > x1 && y2 > y1 ->
        "Valid rectangle";
```

Nếu `start` hoặc `end` là null, `Point(...)` ở tầng trong không khớp. Do đó guard sử dụng `x1`, `y1`, `x2`, `y2` **không được đánh giá**. Nhánh tổng quát `case Rectangle(var start, var end)` có thể xử lý record chứa component null vì `var` ở vị trí component bao phủ kiểu tương ứng.

Có ba trường hợp cần phân biệt:

| Giá trị | Điều gì xảy ra? |
| --- | --- |
| `value == null` | Không khớp `Rectangle(...)` hay `Point(...)`; trong `switch` có thể xử lý bằng `case null`. |
| `new Rectangle(null, new Point(2, 3))` | Pattern lồng `Rectangle(Point(...), Point(...))` không khớp; guard không chạy. |
| `new Rectangle(new Point(0, 0), new Point(2, 3))` | Cả hai `Point(...)` khớp, guard mới kiểm tra thứ tự tọa độ. |

**Không mặc định `default` sẽ xử lý null selector.** Với pattern matching for switch, nếu selector null mà không có nhánh null phù hợp, thường phát sinh `NullPointerException`. Trong ví dụ chạy đầy đủ, `case null` xử lý điều này tường minh.

**Guard có thể tự ném lỗi:** một biểu thức như `when name.length() > 3` có thể ném `NullPointerException` nếu `name` null và pattern trước đó vẫn cho phép component null. Nếu dùng đối tượng/chuỗi nullable trong guard, hãy kiểm tra null:

```java
record Message(String content) {}

// Với component String, biến s có thể nhận null.
case Message(var s) when s != null && !s.isBlank() ->
        "Non-blank message";
case Message(var s) -> "Empty or null message";
```

Guard nên đơn giản, nhanh, ít side effect để việc phân nhánh ổn định và dễ đọc.

## 7. Kết hợp nhiều điều kiện nghiệp vụ

Guards là biểu thức Boolean thông thường; có thể dùng `&&`, `||`, phép so sánh, lời gọi phương thức thuần túy và các biến đã được pattern ràng buộc.

**Ví dụ phân loại số lượng:**

```java
record Order(String customer, int quantity, boolean priority) {}

// Các nhãn sau là minh họa một phần của switch:
case Order(var customer, int quantity, boolean priority)
        when priority && quantity >= 10 ->
        "Large priority order";

case Order(var customer, int quantity, boolean priority)
        when priority ->
        "Priority order";

case Order(var customer, int quantity, boolean priority)
        when quantity > 0 ->
        "Regular order";

case Order(var customer, int quantity, boolean priority) ->
        "Invalid quantity";
```

Các nhánh được xếp từ điều kiện cụ thể đến trường hợp còn lại. Việc dùng chung tên biến giữa các nhãn không có nghĩa chúng là cùng một biến; mỗi nhãn khớp và ràng buộc dữ liệu riêng.

**Guard phối hợp với sealed types:** có thể phân loại từng biến thể rồi lọc thêm theo dữ liệu, như `Transfer` trong ví dụ đầy đủ. Nếu thêm một subtype vào `permits`, hãy biên dịch lại các `switch` exhaustive để phát hiện nơi cần xử lý biến thể mới.

## 8. Những lỗi thường gặp

1. **Viết `when` trong `instanceof`.** Sai: `if (o instanceof Point(int x, int y) when x > 0)`. Đúng: `if (o instanceof Point(int x, int y) && x > 0)`.
2. **Đặt nhánh không guard trước nhánh có guard.** Nhánh tổng quát có thể dominate nhánh sau, gây lỗi biên dịch.
3. **Cho rằng guard làm `switch` exhaustive.** `case Point(...) when x > 0` không bao phủ những `Point` còn lại; thêm nhánh không guard hoặc nhánh dự phòng.
4. **Đọc biến pattern ở chỗ chưa chắc đã khớp.** Kết hợp `||` với biến chỉ được khai báo ở vế trái thường vi phạm flow scoping.
5. **Bỏ sót null selector.** `default` không tự thay thế `case null` trong những `switch` pattern matching cần xử lý null.
6. **Nhầm null selector với component null.** `case null` xử lý toàn bộ selector; component lồng nhau null cần pattern dự phòng và/hoặc điều kiện thích hợp.
7. **Đặt guard có side effect.** Gọi cập nhật trạng thái, I/O hoặc thay đổi dữ liệu trong `when` khiến việc lựa chọn nhánh khó dự đoán và kiểm thử. Ưu tiên điều kiện Boolean thuần túy.
8. **Coi guard như phép cast.** Guard được xét sau khi pattern khớp; chỉ pattern mới giới thiệu biến đúng kiểu/cấu trúc. Guard không thể sửa một record pattern sai cú pháp hoặc không tương thích.
9. **Dùng biểu thức guard có thể lỗi.** Ví dụ truy cập `name.length()` khi `name` nullable hoặc dùng phép chia mà mẫu số bằng 0; phải thêm điều kiện bảo vệ.

## 9. Cách lựa chọn trong code thực tế

- Nếu chỉ cần một nhánh kiểm tra kiểu/cấu trúc và một điều kiện đơn giản, dùng `instanceof Pattern && condition` trong `if`.
- Nếu cần **phân loại nhiều trường hợp** dựa trên cùng một selector, dùng `switch` với nhiều nhánh `case Pattern when condition` và nhánh dự phòng.
- Nếu dữ liệu gồm nhiều record lồng nhau, đặt record patterns bên trong nhau rồi dùng guard cho điều kiện liên quan các component đã tách.
- Nếu dùng sealed hierarchy, kiểm tra xem các nhánh không guard đã bao phủ mọi biến thể cho `switch` expression chưa.
- Nếu điều kiện nghiệp vụ phức tạp, đặt logic vào phương thức trả về `boolean` có tên rõ ràng, và kiểm thử cả giá trị biên, null và ngoại lệ.

**Ghi nhớ:** Pattern quyết định **cấu trúc nào khớp**; guard quyết định **giá trị trong cấu trúc ấy có thỏa điều kiện hay không**. Trong `switch`, dùng `when` sau pattern; trong `if`, dùng `&&` sau `instanceof`. Luôn sắp xếp nhánh theo độ cụ thể, xử lý các trường hợp còn lại và kiểm tra null đúng tầng.

### Tài liệu tham khảo

- JEP 441 — Pattern Matching for switch (Java 21): https://openjdk.org/jeps/441
- JEP 440 — Record Patterns (Java 21): https://openjdk.org/jeps/440
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
