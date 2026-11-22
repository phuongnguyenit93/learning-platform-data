# Sử dụng record pattern trong nhãn case của switch

Trong Java 21, có thể đặt record pattern trực tiếp trong nhãn `case` của `switch` để kiểm tra kiểu record và lấy các component của nó trong cùng một nhánh xử lý. Cách viết này giúp xử lý dữ liệu theo cấu trúc: chương trình kiểm tra record, phân rã các component và có thể tiếp tục phân rã record lồng nhau mà không cần gọi accessor thủ công.

Record patterns và pattern matching for `switch` đều đã là tính năng chính thức trong Java 21. Không cần bật preview hoặc dùng tùy chọn `--enable-preview` để biên dịch các ví dụ trong bài.

## 1. Đặt record pattern trong nhãn case

Một record pattern có dạng tên kiểu record theo sau là danh sách pattern component. Số lượng và thứ tự component phải tương ứng với khai báo record.

```java
record Point(int x, int y) {}

static String describe(Object value) {
    return switch (value) {
        case Point(int x, int y) -> "Point(" + x + ", " + y + ")";
        case null -> "No point was supplied";
        default -> "A different value";
    };
}
```

Khi thực thi, `switch` đánh giá biểu thức selector `value`, sau đó xét các nhãn `case` theo thứ tự xuất hiện. Với nhãn `case Point(int x, int y)`, Java thực hiện các bước sau:

1. Kiểm tra giá trị không phải `null` và có thể khớp với kiểu record `Point`.
2. Gọi accessor tương ứng để lấy hai component `x` và `y`.
3. Kiểm tra từng giá trị component với pattern tương ứng. Ở ví dụ này, `int x` và `int y` nhận giá trị component theo đúng kiểu khai báo.
4. Nếu tất cả component pattern đều khớp, các pattern variable `x` và `y` được khởi tạo và nhánh `case` được chọn.

Nếu kiểu record không khớp hoặc một component pattern không khớp, Java tiếp tục xét nhãn tiếp theo. Nếu accessor của record kết thúc bất thường, quá trình matching kết thúc bằng `MatchException` với nguyên nhân gốc được đặt trong `cause`; đây là lỗi thực thi, không được xem như một trường hợp pattern đơn giản là không khớp.

### Phân biệt type pattern và record pattern

Hai cách viết dưới đây đều kiểm tra một giá trị có phải `Point`, nhưng cung cấp mức truy cập dữ liệu khác nhau:

```java
static void useTypePattern(Object value) {
    switch (value) {
        case Point point ->
            System.out.println(point.x() + ", " + point.y());
        default ->
            System.out.println("Not a point");
    }
}

static void useRecordPattern(Object value) {
    switch (value) {
        case Point(int x, int y) ->
            System.out.println(x + ", " + y);
        default ->
            System.out.println("Not a point");
    }
}
```

`Point point` là type pattern: nhánh nhận toàn bộ đối tượng qua biến `point`. `Point(int x, int y)` là record pattern: nhánh nhận trực tiếp các giá trị component qua biến `x` và `y`. Không đặt `case Point point` trước `case Point(int x, int y)` trong cùng một switch, vì type pattern đầu tiên đã bao phủ mọi giá trị `Point` và làm record pattern phía sau bị dominated. Hãy chọn một trong hai cách hoặc đặt pattern cụ thể trước pattern tổng quát khi chúng có điều kiện phù hợp.

## 2. Phân rã record lồng nhau trong switch

Record pattern có thể chứa các record pattern khác. Nhờ đó, một nhãn `case` có thể kiểm tra cấu trúc dữ liệu nhiều tầng và đưa các component ở tầng sâu vào cùng một nhánh xử lý.

```java
record Address(String city, String postalCode) {}
record Customer(String name, Address address) {}

static String describeCustomer(Object value) {
    return switch (value) {
        case Customer(
                var name,
                Address(var city, var postalCode)) ->
            name + " lives in " + city + " (" + postalCode + ")";
        case Customer(var name, Address address) when address == null ->
            name + " has no address";
        case Customer(var name, Address address) ->
            name + " has an address that does not match the first pattern";
        case null -> "No customer was supplied";
        default -> "Not a customer";
    };
}
```

Ở nhánh đầu, pattern ngoài `Customer(...)` lấy `name` và component `address`. Pattern lồng `Address(var city, var postalCode)` tiếp tục kiểm tra và phân rã địa chỉ. Nếu component `address` là `null`, record pattern `Address(...)` không khớp; Java thử nhãn tiếp theo.

Hai nhãn sau sử dụng type pattern `Address address` trực tiếp ở vị trí component. Vì pattern này là unconditional đối với kiểu component `Address`, nó có thể nhận cả giá trị `null` trong ngữ cảnh component của record pattern. Guard `when address == null` vì thế có thể xử lý riêng trường hợp địa chỉ rỗng. Nhãn kế tiếp xử lý các địa chỉ còn lại. Record pattern ở selector ngoài cùng vẫn không khớp với `null`, nên `case null` riêng biệt được dùng để xử lý selector null.

`var` giúp trình biên dịch suy luận kiểu của pattern variable từ kiểu component. Ví dụ, `var city` có kiểu `String` và `var postalCode` cũng có kiểu `String`; không cần lặp lại kiểu khi cấu trúc record đã xác định chúng.

## 3. Kết hợp record pattern với guard `when`

Đôi khi kiểu record và cấu trúc component chưa đủ để quyết định nhánh. Java 21 cho phép thêm guard `when` sau pattern để kiểm tra điều kiện Boolean trên các pattern variable vừa được tạo.

```java
record Point(int x, int y) {}

static String classify(Point point) {
    return switch (point) {
        case Point(int x, int y) when x == y -> "On the diagonal";
        case Point(int x, int y) when x == 0 || y == 0 -> "On an axis";
        case Point(int x, int y) -> "An ordinary point";
        case null -> "No point";
    };
}
```

Guard chỉ được đánh giá sau khi record pattern tương ứng đã khớp. Nếu pattern không khớp, guard không được đánh giá. Nếu pattern khớp nhưng guard trả về `false`, Java tiếp tục xét nhãn `case` tiếp theo. Vì vậy, nhánh cuối có thể xử lý các điểm không thỏa hai điều kiện trước.

Các biến được khai báo trong pattern có thể dùng trong guard và phần thân của chính nhãn đó. Chúng không có phạm vi sử dụng bên ngoài nhánh `case` tương ứng.

Không dùng cú pháp guard của các bản preview cũ. Trong Java 21, guard được viết bằng từ khóa `when`:

```java
case Point(int x, int y) when x == y -> "Diagonal";
```

## 4. Dùng record pattern trong switch expression và switch statement

Record pattern có thể xuất hiện trong cả switch expression lẫn switch statement.

### Switch expression trả về kết quả

Switch expression trả về một giá trị, nên mỗi đường thực thi phải tạo ra kết quả. Nếu một nhánh cần nhiều câu lệnh, dùng block và `yield` để trả về kết quả của nhánh đó:

```java
record Rectangle(double width, double height) {}

static double area(Object value) {
    return switch (value) {
        case Rectangle(double width, double height) -> {
            double result = width * height;
            yield result;
        }
        case null -> 0.0;
        default -> throw new IllegalArgumentException("Not a rectangle");
    };
}
```

Ở đây, record pattern lấy `width` và `height` trước khi tính diện tích. `yield` kết thúc block của switch rule và cung cấp giá trị cho switch expression. Có thể dùng biểu thức ngắn trực tiếp sau `->` nếu nhánh chỉ cần một phép tính.

### Switch statement thực hiện hành động

Switch statement thường được dùng khi mỗi nhánh cần thực hiện một hoặc nhiều thao tác mà không trả về một giá trị:

```java
record Point(int x, int y) {}

static void print(Object value) {
    switch (value) {
        case Point(int x, int y) ->
            System.out.println("Coordinates: " + x + ", " + y);
        case null ->
            System.out.println("Point is null");
        default ->
            System.out.println("Unsupported value");
    }
}
```

Nên ưu tiên switch rule với `->` để mỗi nhánh là một đơn vị độc lập. Java 21 vẫn hỗ trợ nhóm nhãn `case` với dấu `:`, nhưng pattern variable chỉ có phạm vi trong nhóm statement tương ứng và trình biên dịch cấm đường thực thi có thể rơi xuyên qua nhãn khiến pattern variable chưa được khởi tạo.

## 5. Xử lý null ở selector và component

Null cần được xem xét ở hai vị trí riêng: giá trị selector của `switch` và giá trị component bên trong một record.

### Selector của switch là null

Record pattern không khớp với giá trị `null`. Nếu selector là `null` và switch block không có nhãn `case null`, Java ném `NullPointerException`. Nhãn `default` đơn lẻ không xử lý `null`.

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "null value";
        case Point(int x, int y) -> "point: " + x + ", " + y;
        default -> "other value";
    };
}
```

Java 21 cũng cho phép kết hợp `null` với `default` trong cùng một nhãn:

```java
return switch (value) {
    case Point(int x, int y) -> "point";
    case null, default -> "null or another type";
};
```

`case null` chỉ được kết hợp với `default`, không được ghép cùng một pattern hoặc một hằng số case khác. Nếu cần xử lý `null` riêng, hãy dùng nhãn `case null` độc lập.

### Component bên trong record là null

Record pattern lồng nhau như `Address(var city, var postalCode)` không khớp khi component `address` là `null`. Nếu cần nhận biết trường hợp này, có thể dùng một type pattern unconditional cho đúng kiểu component, sau đó kiểm tra giá trị bằng guard `when`, như ví dụ `Customer` ở phần trước.

Điểm khác biệt cần nhớ:

- Record pattern ở selector ngoài cùng luôn không khớp với `null`.
- Record pattern lồng nhau cũng không khớp khi giá trị component tương ứng là `null`.
- Type pattern unconditional xuất hiện trực tiếp ở vị trí component có thể là null-matching theo quy tắc record pattern của Java 21; nhờ vậy có thể gán component null vào pattern variable và kiểm tra trong guard.

## 6. Thứ tự nhãn case và lỗi dominance

Java xét nhãn theo thứ tự từ trên xuống. Nếu một nhãn trước đã bao phủ toàn bộ giá trị mà nhãn sau có thể nhận, nhãn sau bị *dominated* và chương trình không biên dịch.

Ví dụ sau không hợp lệ:

```java
static String classify(Object value) {
    return switch (value) {
        case Point(var x, var y) -> "Any point";
        case Point(int x, int y) when x == y -> "Diagonal point"; // compile-time error
        default -> "Other";
    };
}
```

`Point(var x, var y)` có thể khớp mọi `Point`, nên nhánh thứ hai không bao giờ được chọn. Cần đặt pattern cụ thể hoặc guarded pattern trước pattern tổng quát:

```java
static String classify(Object value) {
    return switch (value) {
        case Point(int x, int y) when x == y -> "Diagonal point";
        case Point(int x, int y) -> "Any other point";
        default -> "Other";
    };
}
```

Một type pattern rộng cũng có thể làm record pattern phía sau bị dominated. Ví dụ, nếu `case Shape shape` xuất hiện trước `case Circle(double radius)`, nhãn `Circle(...)` không thể được chọn vì mọi `Circle` cũng là `Shape`.

Guarded pattern thường không được dùng để kết luận dominance vì trình biên dịch không thể tổng quát xác định giá trị của mọi biểu thức guard. Dù vậy, nên đặt các nhánh có điều kiện cụ thể trước nhánh không có guard, sau đó mới đặt pattern tổng quát. Đặt `default` ở cuối để thứ tự dễ đọc và tránh che khuất nhánh cụ thể.

## 7. Bảo đảm switch đầy đủ các trường hợp

Switch expression luôn phải exhaustive: switch block phải bao phủ các giá trị không-null có thể có theo kiểu selector. Switch statement có sử dụng pattern label hoặc nhãn `null` cũng phải exhaustive trong Java 21. Exhaustiveness là kiểm tra độ bao phủ kiểu ở thời điểm biên dịch; nó không tự xử lý selector `null`. Nếu selector có thể là `null`, cần thêm `case null` hoặc dùng `case null, default` để tránh `NullPointerException`.

Có thể bảo đảm exhaustiveness theo một trong các cách sau:

- Thêm `default` để xử lý các giá trị chưa được liệt kê.
- Dùng `case null, default` nếu muốn xử lý cả `null` và mọi giá trị còn lại trong một nhánh.
- Nếu selector có kiểu sealed, liệt kê đầy đủ các kiểu con được phép và các pattern tương ứng để compiler chứng minh switch đã bao phủ toàn bộ hierarchy.

Ví dụ với sealed hierarchy:

```java
sealed interface Shape permits Circle, Rectangle {}
record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}

static double area(Shape shape) {
    return switch (shape) {
        case Circle(double radius) -> Math.PI * radius * radius;
        case Rectangle(double width, double height) -> width * height;
    };
}
```

Vì `Shape` chỉ cho phép hai record `Circle` và `Rectangle` triển khai, hai record pattern bao phủ toàn bộ các kiểu con được phép. Do đó không cần `default` để đạt exhaustiveness. Nếu hierarchy được mở rộng về sau, hãy biên dịch lại lớp chứa switch để compiler kiểm tra các kiểu con mới. Nếu hierarchy đã thay đổi nhưng lớp switch cũ chưa được biên dịch lại, một giá trị mới không khớp có thể khiến runtime ném `MatchException`.

Lưu ý: switch statement truyền thống chỉ dùng các hằng số `case` cho kiểu selector cũ không bắt buộc exhaustive. Quy tắc bắt buộc exhaustive áp dụng cho switch expression và enhanced switch statement, tức switch statement có pattern label hoặc nhãn `null` (hoặc selector thuộc nhóm kiểu được mở rộng theo đặc tả).

## 8. Record pattern generic và suy luận kiểu trong switch

Java 21 có thể suy luận tham số kiểu của generic record pattern dựa trên kiểu selector. Điều này giúp tránh lặp lại tham số kiểu khi chúng đã được xác định từ biến đầu vào.

```java
record Box<T>(T value) {}

static String describeBox(Box<String> box) {
    return switch (box) {
        case Box(var value) -> "Box contains: " + value;
        case null -> "No box";
    };
}
```

Vì selector có kiểu `Box<String>`, compiler suy luận `Box(var value)` tương ứng với `Box<String>` và kiểu của `value` là `String`. Record pattern vẫn phải thỏa các quy tắc kiểm tra kiểu an toàn; không thể dùng một tham số kiểu cụ thể nếu việc kiểm tra đòi hỏi unchecked conversion.

## 9. Các lỗi thường gặp khi dùng record pattern trong switch

| Dấu hiệu | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không biên dịch vì sai số component | Pattern không có đúng số component hoặc thứ tự không khớp record header | Đối chiếu record declaration và viết đủ pattern theo đúng thứ tự |
| Không biên dịch vì dominated label | Pattern rộng hơn đã xuất hiện trước và bao phủ nhánh sau | Đưa pattern cụ thể hoặc guarded pattern lên trước |
| `NullPointerException` khi selector null | Không có nhãn `case null`; `default` không bắt null | Thêm `case null` hoặc dùng `case null, default` |
| Switch expression hoặc pattern switch statement không exhaustive | Chưa bao phủ mọi kiểu có thể có | Thêm `default` hoặc liệt kê đủ các kiểu con của sealed hierarchy |
| Nhánh record lồng nhau không được chọn | Component null hoặc không khớp kiểu/pattern lồng | Kiểm tra null và kiểu component; thêm nhánh xử lý riêng nếu cần |
| `MatchException` khi matching | Accessor của record ném lỗi hoặc hierarchy sealed thay đổi sau khi compile | Kiểm tra accessor và cause; biên dịch lại switch sau khi thay đổi hierarchy |

Khi thiết kế switch có nhiều nhánh, hãy kiểm tra cả cấu trúc dữ liệu lẫn thứ tự nhãn. Một pattern đúng về cú pháp vẫn có thể không bao giờ được chọn nếu nó bị một pattern rộng hơn đặt phía trước.

## 10. Quy trình thiết kế một pattern switch

Khi chuyển chuỗi `if/else instanceof` thành switch có record pattern, có thể làm theo trình tự sau:

1. Xác định kiểu selector và các kiểu record mà logic cần xử lý.
2. Chọn record pattern khi nhánh cần trực tiếp các component; dùng type pattern nếu nhánh cần giữ toàn bộ đối tượng.
3. Với dữ liệu lồng nhau, đặt record pattern tương ứng ở vị trí component và quyết định rõ hành vi khi component là `null`.
4. Đưa điều kiện nghiệp vụ vào guard `when`, sử dụng pattern variable được khai báo trong cùng nhãn.
5. Sắp xếp pattern cụ thể và guarded pattern trước pattern tổng quát để tránh dominance.
6. Bảo đảm switch expression hoặc enhanced switch statement exhaustive; xử lý selector null một cách tường minh nếu đầu vào có thể null.
7. Biên dịch và kiểm thử trên Java 21, bao gồm trường hợp không khớp, component null, selector null và các nhánh guard trả về `false`.

## Kết luận

Record pattern trong nhãn `case` giúp switch kiểm tra kiểu record và phân rã component ngay tại nhánh xử lý. Java 21 bổ sung khả năng lồng pattern, kết hợp guard `when`, xử lý null và kiểm tra exhaustiveness cho enhanced switch. Để switch dễ bảo trì, hãy chọn đúng mức pattern, đặt nhánh cụ thể trước nhánh tổng quát, xác định rõ cách xử lý null và bảo đảm mọi giá trị có thể có đều được bao phủ.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 21 — The switch Statement (§14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html)
- [Java Language Specification, Java SE 21 — Patterns (§14.30)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html)
- [Oracle Java SE 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
