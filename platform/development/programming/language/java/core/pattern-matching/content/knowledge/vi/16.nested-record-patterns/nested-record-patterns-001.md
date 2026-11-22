# Lồng record pattern nhiều cấp (Nested Record Patterns) trong Java

## 1. Mục tiêu và phiên bản Java

Khi một đối tượng chứa các `record` lồng nhau, ta thường phải gọi nhiều accessor như `route.segment().from().x()` và tự kiểm tra kiểu/giá trị `null` trước khi sử dụng. **Nested record pattern** cho phép kiểm tra cấu trúc và lấy các component ở nhiều cấp ngay trong một biểu thức `instanceof` hoặc một nhánh `switch`.

Tính năng **record patterns** được chuẩn hóa trong **Java 21 (JEP 440)**; pattern matching cho `switch` cũng chính thức trong Java 21 (JEP 441). Các ví dụ dưới đây dùng **JDK 21+**, không cần `--enable-preview`. `record` là một kiểu lớp dùng để mô tả dữ liệu; mỗi component có accessor cùng tên, chẳng hạn `point.x()`.

Sau bài học, bạn sẽ biết cách đọc record pattern từ ngoài vào trong, kết hợp hai hoặc nhiều cấp record, lấy biến qua `var`, dùng `when` với `switch` và xử lý các trường hợp không khớp.

## 2. Cấu trúc và cú pháp lồng nhau

Giả sử có ba record:

```java
record Point(int x, int y) {}
record Segment(Point from, Point to) {}
record Route(String name, Segment segment) {}
```

Một `Route` chứa `Segment`, còn `Segment` chứa hai `Point`. Khi `value` là một biến kiểu `Object`, ta có thể viết (đặt đoạn này trong một phương thức có biến `value`):

```java
if (value instanceof Route(
        String name,
        Segment(
            Point(int x1, int y1),
            Point(int x2, int y2)))) {
    System.out.println(name + ": (" + x1 + ", " + y1
            + ") -> (" + x2 + ", " + y2 + ")");
}
```

Đọc pattern theo thứ tự:

1. `Route(...)`: giá trị bên ngoài phải là `Route`, có hai component đúng theo thứ tự khai báo: `name` và `segment`.
2. `String name`: ràng buộc giá trị component đầu vào biến `name` theo type pattern.
3. `Segment(...)`: component thứ hai phải khớp với một record `Segment`.
4. Hai `Point(...)`: `from` và `to` tiếp tục được phân rã; `x1`, `y1`, `x2`, `y2` là các biến `int` được khai báo ngay trong pattern.

Đây là **ba cấp record pattern: `Route → Segment → Point`**. Mỗi record pattern cần có đúng số pattern con tương ứng số component của record và cùng thứ tự khai báo. Trình biên dịch sử dụng các accessor của record để lấy component và thử khớp đệ quy. Điều kiện trong `if` chỉ đúng khi toàn bộ pattern khớp; khi ấy các biến mới được sử dụng ở thân `if`. Cú pháp trên không tạo ra record mới, không tự so sánh hai đối tượng `Point` và cũng không so sánh tọa độ bằng giá trị cố định.

## 3. Ví dụ Java 21 hoàn chỉnh, chạy được

Tạo tệp `NestedRecordPatternsDemo.java`:

```java
public class NestedRecordPatternsDemo {
    record Point(int x, int y) {}
    record Segment(Point from, Point to) {}
    record Route(String name, Segment segment) {}
    record Box<T>(T value) {}

    static String startOf(Object value) {
        if (value instanceof Route(String name,
                Segment(Point(int startX, int startY), Point(var endX, var endY)))) {
            return name + ": start=(" + startX + ", " + startY
                    + "), end=(" + endX + ", " + endY + ")";
        }
        return "No complete route";
    }

    static String classify(Object value) {
        return switch (value) {
            case null -> "Null input";
            case Route(String name,
                    Segment(Point(int x1, int y1), Point(int x2, int y2)))
                    when x1 == x2 && y1 == y2 -> name + ": same point";
            case Route(String name,
                    Segment(Point(var x1, var y1), Point(var x2, var y2)))
                    -> name + ": different points";
            default -> "No matching route";
        };
    }

    static String unwrap(Box<Box<String>> box) {
        if (box instanceof Box(Box(var text))) {
            return text;
        }
        return "No nested string";
    }

    public static void main(String[] args) {
        Object complete = new Route("R1", new Segment(new Point(1, 2), new Point(5, 8)));
        Object zero = new Route("R2", new Segment(new Point(3, 3), new Point(3, 3)));
        Object incomplete = new Route("R3", new Segment(null, new Point(9, 9)));

        System.out.println(startOf(complete));
        System.out.println(classify(complete));
        System.out.println(classify(zero));
        System.out.println(classify(incomplete));
        System.out.println(classify(null));
        System.out.println(unwrap(new Box<>(new Box<>("Java 21"))));
    }
}
```

Biên dịch/chạy bằng JDK 21 trở lên:

```bash
javac --release 21 NestedRecordPatternsDemo.java
java NestedRecordPatternsDemo
```

Kết quả:

```text
R1: start=(1, 2), end=(5, 8)
R1: different points
R2: same point
No matching route
Null input
Java 21
```

Giải thích từng trường hợp:

- `startOf(complete)` khớp toàn bộ ba cấp, gán bốn tọa độ và trả về mô tả điểm đầu/cuối.
- `classify(complete)` không qua nhánh `when` vì hai điểm khác nhau; nhánh record pattern tổng quát phía dưới được chọn.
- `classify(zero)` qua nhánh có `when x1 == x2 && y1 == y2` vì điểm đầu và điểm cuối trùng nhau.
- `incomplete` có `Segment.from() == null`, nên pattern `Point(...)` ở vị trí đó **không khớp**. `switch` đi đến `default` thay vì truy cập `null.x()`.
- `classify(null)` được xử lý bằng `case null`; nếu thiếu nhánh này thì `switch` trên giá trị `null` thông thường ném `NullPointerException`.
- `unwrap` cho thấy khả năng suy luận kiểu khi lồng record generic: từ tham số `Box<Box<String>>`, trình biên dịch suy ra `text` có kiểu `String`.

## 4. Những quy tắc cần nhớ khi lồng nhiều cấp

### Dùng `var` và type pattern đúng chỗ

Trong `Point(int x, int y)`, ta ghi rõ kiểu của từng component. Với `Point(var x, var y)`, trình biên dịch tự suy ra cả `x` và `y` là `int` từ khai báo `record Point(int x, int y)`. `var` bên trong record pattern là biến có **kiểu xác định tại thời điểm biên dịch**; nó không biến Java thành ngôn ngữ có kiểu động. `var` kiểu này là pattern component, không phải toán tử bỏ qua dữ liệu.

Bạn có thể trộn nhiều mức: `Route(String name, Segment(Point(var x, var y), var to))`. Trong ví dụ đó, `to` vẫn có kiểu `Point` vì component `Segment.to` là `Point`, nhưng chưa phân rã tọa độ của `to`. Chỉ phân rã tới mức thật sự cần dùng để code dễ đọc hơn.

### Kết hợp `switch` và điều kiện `when`

`when` được đánh giá **sau khi** pattern ở nhánh `case` khớp, và có thể sử dụng các biến được khai báo trong chính pattern đó. Nhánh hẹp, có `when`, nên đặt trước nhánh bao quát hơn. Nếu một nhánh tổng quát đã bao phủ hết một nhánh cụ thể ở dưới, Java có thể báo lỗi **dominated case label** khi biên dịch.

Biểu thức `switch` phải bao phủ mọi đầu vào hợp lệ; với đầu vào kiểu `Object` như ví dụ, `default` đảm bảo tính đầy đủ. `case null` là một trường hợp riêng, không mặc nhiên được bao phủ bởi record pattern.

### Phân biệt `null` ở từng mức

Một **record pattern** như `Point(var x, var y)` không khớp với giá trị `null`. Do đó, nếu một cấp trung gian mà ta định phân rã thành record bị `null`, toàn bộ nested pattern không khớp. Riêng các type pattern dùng cho component (đặc biệt `var`/kiểu bao trùm component) có quy tắc khớp `null` riêng; đừng suy luận rằng mọi component `null` đều làm hỏng mọi pattern. Hãy xác định chính xác **cấp nào đang dùng record pattern**.

Nếu cần phân biệt “sai kiểu”, “thiếu record con” và “tọa độ không hợp lệ”, nên đặt các kiểm tra rõ ràng hoặc tách phương thức thay vì gộp tất cả vào một `default`.

### Phạm vi biến và accessor

Các biến như `x1`, `y1` chỉ có hiệu lực ở những vị trí mà compiler biết pattern đã khớp: thân `if`, phần bên phải phù hợp của `&&`, `when` và phần xử lý tương ứng của `case`. Không thể dùng chúng tùy ý sau `if` nếu nhánh không khớp. Pattern matching truy cập các component qua accessor theo cơ chế ngôn ngữ; đây không phải việc đọc field bằng reflection và không cần ép kiểu thủ công.

### Record generic lồng nhau

Từ định nghĩa `record Box<T>(T value) {}` và biến `Box<Box<String>> box`, pattern `Box(Box(var text))` cho phép lấy `String` ở lớp trong. Trình biên dịch phải chứng minh kiểu có thể khớp an toàn; không nên đưa ra kiểm tra kiểu tham số hóa không thể kiểm chứng với raw type rồi trông đợi record pattern vượt qua type erasure.

## 5. Những lỗi thường gặp

| Lỗi | Nguyên nhân và cách sửa |
| --- | --- |
| Viết `Point(int x)` trong khi `Point` có `x, y` | Sai số component. Viết đủ hai pattern, chẳng hạn `Point(int x, int y)`. |
| Đảo `from` và `to` vì tưởng pattern khớp theo tên | Record pattern khớp theo **vị trí khai báo**. Đọc lại định nghĩa `record Segment(Point from, Point to)`. |
| Dùng cú pháp `Point(0, 0)` để kiểm tra điểm gốc | Java 21 không có cú pháp literal record pattern như vậy. Dùng `Point(int x, int y)` rồi kiểm tra `x == 0 && y == 0` bằng `if` hoặc `when`. |
| Dùng một record pattern để “phân rã” lớp thông thường | Cú pháp phân rã này dành cho **record class**. Với class thường, dùng accessor hoặc chuyển cấu trúc dữ liệu khi phù hợp. |
| Truy cập biến pattern sau một `if` không bảo đảm khớp | Biến chưa chắc được gán ở mọi luồng điều khiển. Chuyển xử lý vào thân `if` hoặc nhánh đã được kiểm chứng. |
| Bỏ qua giá trị `null` ở cấp record con hoặc ở selector của `switch` | Thêm nhánh xử lý trường hợp không khớp; dùng `case null` khi selector của `switch` có thể là `null`. |
| Đặt `case` tổng quát trước `case` có `when` | Nhánh sau có thể bị che khuất; đặt nhánh cụ thể trước, nhánh tổng quát sau. |
| Biên dịch bằng Java 17 không bật preview | Record patterns chưa phải tính năng chuẩn trong Java 17. Sử dụng **JDK 21+** cho các ví dụ ở bài này. |

## 6. Khi nào nên dùng và cách luyện tập

Nested record patterns hữu ích với các cấu trúc dữ liệu bất biến, cấu trúc biểu thức cú pháp (AST), sự kiện hoặc kết quả xử lý mà nhiều record lồng nhau. Ưu tiên chúng khi phần code muốn diễn đạt rõ **“dữ liệu có cấu trúc nào?”** và **“cần lấy component nào?”**. Khi số tầng quá sâu hoặc có nhiều điều kiện nghiệp vụ, tách pattern thành nhiều bước hoặc các phương thức nhỏ có thể dễ hiểu, dễ kiểm thử hơn.

Bài tập: Cho ba record sau, viết `instanceof` để lấy `city` của một `Order` chỉ khi khách hàng có `Address` và `city != null`:

```java
record Address(String city, int postalCode) {}
record Customer(String id, Address address) {}
record Order(long orderId, Customer customer) {}
```

Một lời giải (đặt trong phương thức nhận `Object input`):

```java
if (input instanceof Order(
        var orderId,
        Customer(var customerId, Address(var city, var postalCode)))
        && city != null) {
    System.out.println(orderId + " / " + customerId + " / " + city);
} else {
    System.out.println("Missing customer address or city");
}
```

Trong ví dụ này, `Address(...)` buộc cấp địa chỉ phải là một record `Address` khác `null`; phép kiểm tra `city != null` xử lý thêm component chuỗi. Đây là hai điều kiện khác nhau và đều quan trọng.

**Ghi nhớ:** nested record pattern khớp từ record ngoài vào record trong, theo đúng thứ tự component. `var` giúp suy luận kiểu, `when` xử lý điều kiện trên dữ liệu đã ràng buộc, `case null` xử lý selector rỗng, và `default` hoặc `else` giải quyết dữ liệu không khớp. Khi cần truy cập nhiều cấp dữ liệu, cú pháp này thường ngắn và an toàn hơn chuỗi ép kiểu thủ công.

**Tài liệu tham khảo:** [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
