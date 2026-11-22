# Kết hợp type pattern và record pattern (Java 21)

## Mục tiêu

Trong Java, **type pattern** xác nhận một giá trị thuộc kiểu nào và ràng buộc giá trị đó vào biến, còn **record pattern** bóc tách các component của record. Khi kết hợp chúng, ta có thể khớp kiểu và duyệt cấu trúc dữ liệu nhiều tầng ngay trong `instanceof` hoặc `switch`, thay vì viết nhiều phép ép kiểu và gọi accessor thủ công.

Bài này thuộc nhóm **Nested record patterns**. Người học cần nắm được:
- Cách đọc type pattern `String text` và record pattern `Point(int x, int y)`.
- Cách đặt type pattern bên trong record pattern, rồi lồng nhiều record pattern.
- Cách áp dụng với `instanceof`, `switch` và guard `when`.
- Cách xử lý `null`, biến pattern, thứ tự các nhánh và tính đầy đủ của `switch`.

**Phiên bản:** Record patterns (JEP 440) và pattern matching cho `switch` (JEP 441) là tính năng chính thức từ **Java 21**. Ví dụ dưới đây dùng JDK 21 trở lên, không cần `--enable-preview`. Type pattern trong `instanceof` đã chính thức từ Java 16.

## 1. Từ type pattern đến nested record pattern

**Type pattern** kiểm tra kiểu và khai báo biến:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Ở đây, `String text` xác nhận `value` là một `String` và cung cấp biến `text`; nó không bóc tách các trường của đối tượng.

**Record pattern** kiểm tra record và lần lượt khớp các component:

```java
record Point(int x, int y) {}

// Minh họa trong một phương thức:
if (value instanceof Point(int x, int y)) {
    System.out.println(x + y);
}
```

`Point(int x, int y)` ràng buộc trực tiếp hai tọa độ. Với type pattern `Point point` thông thường, bạn phải gọi `point.x()` và `point.y()` để lấy chúng.

Xét các kiểu:

```java
record Point(int x, int y) {}
record Box(Point topLeft, Point bottomRight) {}
record Packet(String id, Object payload, Box region) {}
```

Có thể kết hợp tất cả trong một pattern:

```java
Packet(
    String id,
    String text,
    Box(
        Point(int left, int top),
        Point(int right, int bottom)
    )
)
```

Đọc từ ngoài vào trong:
1. Giá trị phải là một `Packet`.
2. `String id` ràng buộc component `id`, vốn được khai báo là `String`.
3. `String text` kiểm tra component `payload` có kiểu tĩnh `Object`, yêu cầu giá trị thực tế phải là `String`. Giá trị `Integer` hoặc `null` không khớp ở đây.
4. `Box(...)` yêu cầu `region` là một `Box` khác `null` và bóc tách tiếp hai `Point`.
5. Mỗi `Point(int ..., int ...)` bóc tách hai component `int` để lấy bốn tọa độ.

Vì **mỗi component trong record pattern lại nhận một pattern con**, bạn có thể thay một type pattern bằng record pattern khác khi muốn đi sâu vào cấu trúc. Đây là hình thức kết hợp type pattern và nested record pattern.

## 2. Chương trình hoàn chỉnh: phân loại Packet

Tạo file **`CombinedPatternDemo.java`**:

```java
public class CombinedPatternDemo {
    record Point(int x, int y) {}

    record Box(Point topLeft, Point bottomRight) {}

    record Packet(String id, Object payload, Box region) {}

    static int areaOfTextPacket(Object value) {
        if (value instanceof Packet(
                String id,
                String text,
                Box(Point(int left, int top), Point(int right, int bottom)))
                && right > left && bottom > top) {
            return (right - left) * (bottom - top);
        }
        return 0;
    }

    static String describe(Object value) {
        return switch (value) {
            case Packet(
                    String id,
                    String text,
                    Box(Point(int left, int top), Point(int right, int bottom)))
                    when right > left && bottom > top ->
                id + ": text=" + text
                    + ", area=" + ((right - left) * (bottom - top));

            case Packet(
                    String id,
                    Integer count,
                    Box(Point(var left, var top), Point(var right, var bottom)))
                    when count > 0 ->
                id + ": count=" + count
                    + ", start=(" + left + "," + top + ")";

            case Packet(var id, var payload, var region) ->
                id + ": other=" + payload;

            case null -> "null input";

            default -> "unsupported input";
        };
    }

    public static void main(String[] args) {
        Box box = new Box(new Point(1, 2), new Point(5, 7));

        System.out.println("area="
            + areaOfTextPacket(new Packet("P-1", "hello", box)));
        System.out.println(describe(new Packet("P-1", "hello", box)));
        System.out.println(describe(new Packet("P-2", 3, box)));
        System.out.println(describe(new Packet("P-3", -2, box)));
        System.out.println(describe(new Packet("P-4", "hello", null)));
        System.out.println(describe(null));
        System.out.println(describe("other"));
    }
}
```

Biên dịch và chạy với JDK 21 trở lên:

```bash
javac --release 21 CombinedPatternDemo.java
java CombinedPatternDemo
```

Stdout:

```text
area=20
P-1: text=hello, area=20
P-2: count=3, start=(1,2)
P-3: other=-2
P-4: other=hello
null input
unsupported input
```

**Giải thích từng trường hợp:**

- Với `P-1`, `payload` là `String` và `region` chứa hai `Point(1,2)`, `Point(5,7)`. Điều kiện tọa độ hợp lệ, diện tích = (5 − 1) × (7 − 2) = 20. Cả `instanceof` và `switch` đều khớp các type pattern bên trong hai cấp record pattern.
- Với `P-2`, `payload` là `Integer(3)` nên nhánh `String text` không khớp. Nhánh `Integer count` khớp, guard `count > 0` đúng, và biến `left`/`top` có giá trị 1/2.
- Với `P-3`, `count = -2` nên guard `count > 0` sai; `switch` chuyển sang nhánh fallback `Packet(var id, var payload, var region)`.
- Với `P-4`, `region = null` nên `Box(Point(...), Point(...))` không khớp. Fallback dạng `Packet(var ...)` vẫn xử lý được record chứa component `null`.
- Selector `null` khớp `case null`; giá trị chuỗi `"other"` khớp `default`.

Ví dụ dùng `int` để minh họa đơn giản. Nếu tọa độ đủ lớn, phép trừ hoặc phép nhân có thể tràn số nguyên. Trong hệ thống thực tế cần kiểm tra miền dữ liệu và dùng `long` phù hợp.

## 3. Khi nào dùng instanceof, khi nào dùng switch?

**`instanceof`** phù hợp với một kiểm tra chuyên biệt. Bạn có thể nối `&&` sau pattern: các biến pattern chỉ được dùng khi việc khớp thành công.

```java
if (value instanceof Packet(
        String id, String text,
        Box(Point(int left, int top), Point(int right, int bottom)))
        && right > left && bottom > top) {
    // text, left, top, right, bottom có phạm vi hợp lệ ở đây.
}
```

Nếu giá trị ngoài cùng sai kiểu, payload không phải `String` hoặc region thiếu cấu trúc cần thiết, nhánh `if` không chạy.

**`switch`** phù hợp khi cần phân loại nhiều biến thể. Một nhánh có thể vừa kiểm tra kiểu, bóc tách record, vừa thêm guard `when`:

```java
case Packet(
        String id, Integer count,
        Box(Point(var left, var top), Point(var right, var bottom)))
        when count > 0 ->
    id + ": count=" + count
        + ", start=(" + left + "," + top + ")";
```

Đây là trích đoạn `case` trong chương trình hoàn chỉnh, không phải chương trình độc lập. `when` chỉ được kiểm tra sau khi pattern khớp. Khi guard sai, các case tiếp theo vẫn có thể được xét.

Trong `Point(var left, var top)`, `var` là type pattern suy ra kiểu từ component; ở đây cả hai biến mang kiểu `int`. Nó tránh lặp lại kiểu đã rõ, không phải phép kiểm tra runtime tùy ý.

## 4. Quy tắc, giới hạn và lỗi thường gặp

### 4.1. Pattern ở từng component phải tương thích với kiểu tĩnh

`Packet` khai báo `payload` là `Object`, do đó `String text` hoặc `Integer count` là các phép lọc kiểu hợp lệ tại vị trí này.

Trái lại, dùng `String text` ở vị trí `region` (kiểu tĩnh `Box`) hoặc ở vị trí tọa độ `int` là không tương thích kiểu. Trình biên dịch kiểm tra tính hợp lệ của từng pattern con, kể cả khi nó được lồng rất sâu.

Record pattern chỉ bóc tách **record class**. Với class thông thường, dùng type pattern như `SomeClass obj` và các accessor/method của class đó; không tự áp dụng cú pháp `SomeClass(component1, component2)`.

### 4.2. Phân biệt null của selector, record và component

- `value instanceof ...` trả về `false` khi `value == null`; một giá trị `null` không khớp record pattern nào.
- `Box(Point(...), Point(...))` không khớp khi bản thân component `region` là `null`.
- Type pattern lồng bên trong record **có thể khớp null** nếu nó *unconditional* đối với kiểu component được khai báo. Vì vậy `Packet(var id, var payload, var region)` có thể ràng buộc cả `payload == null` và `region == null`.
- `String id` đặt ở component được khai báo `String` là unconditional và có thể nhận `null`. Ngược lại, `String text` ở component kiểu `Object` không khớp `null` vì nó đòi hỏi giá trị thực tế kiểu `String`.
- Với `switch` trên tham chiếu `null`, hãy dùng `case null` nếu muốn xử lý giá trị này. `default` thông thường không thay thế `case null`; nếu thiếu xử lý null, có thể phát sinh `NullPointerException`.

### 4.3. Case cụ thể phải xuất hiện trước case tổng quát

Ví dụ **cố ý sai và không biên dịch** nếu đặt trong một `switch`:

```java
case Packet packet -> "any packet";
case Packet(String id, String text, var region) -> "text packet";
```

`Packet packet` đã nhận mọi `Packet` khác `null` nên nhánh `Packet(String id, String text, ...)` phía sau bị *dominated*. Trình biên dịch phát hiện nhánh không thể được chọn.

Hãy đặt những nhánh kiểm tra `String`/`Integer` và record pattern lồng sâu trước, sau đó mới đặt fallback `Packet(var id, var payload, var region)`. Guard `when` có thể khiến một nhánh không được chọn, nên cần xét cả trường hợp guard sai.

### 4.4. switch expression phải bao phủ hết các trường hợp

`switch` expression là **exhaustive** khi các nhánh bao phủ mọi kiểu mà selector có thể nhận. Trong `describe(Object value)`, các nhánh `Packet` không xử lý `String` hoặc `Long`, vì vậy cần `default`. `case null` xử lý riêng đầu vào null.

Khi selector là một sealed hierarchy hay record với các record pattern bao phủ đầy đủ, trình biên dịch có thể chứng minh tính exhaustive mà không cần `default`. Dù vậy, cần cân nhắc riêng khả năng đầu vào `null`.

### 4.5. Biến pattern có phạm vi theo kết quả khớp

Biến như `text`, `left`, `right` có thể dùng trong thân nhánh đã khớp, trong guard `when` của nhánh đó và ở vế `&&` phù hợp. Chúng không có phạm vi trong nhánh thất bại hay ở vị trí mà trình biên dịch không thể bảo đảm đã được ràng buộc.

Không khai báo hai biến pattern trùng tên trong một nested record pattern. Muốn so sánh hai tọa độ, đặt tên riêng rồi dùng `when left == right` hoặc biểu thức điều kiện tương đương.

### 4.6. Bóc tách không đồng nghĩa tạo hoặc sửa đối tượng

`Point(int x, int y)` lấy giá trị từ các accessor component của record, không tạo `Point` mới. Các field component của record là final; nếu một component giữ tham chiếu đến đối tượng có thể thay đổi, record đó cũng không mặc nhiên bất biến sâu.

## 5. Cách áp dụng và bài tập

Một quy trình thực tế để viết pattern kết hợp:
1. Xác định record ngoài cùng và kiểu của từng component.
2. Chỉ bóc tách những cấp dữ liệu thực sự cần; nếu chỉ cần toàn bộ object, `Packet packet` đơn giản hơn.
3. Đặt type pattern tại component đa hình, ví dụ `String text` và `Integer count` ở `Object payload`.
4. Dùng `&&` hoặc `when` cho các điều kiện nghiệp vụ, thay vì cố biến mọi điều kiện thành kiểm tra kiểu.
5. Sắp xếp case từ cụ thể đến tổng quát và xử lý đầy đủ null/fallback.
6. Tách phương thức khi pattern lồng quá sâu hoặc có guard phức tạp.

**Bài tập:** Thêm một nhánh vào `describe` xử lý `Packet` có `payload` là `Long` lớn hơn 10 và `region` chứa hai `Point`. Đặt `Long amount` ở vị trí payload, dùng nested `Box(Point(...), Point(...))` và guard `when amount > 10`. Thêm nhánh này **trước** fallback `Packet(var ...)`, rồi thử `11L`, `9L` và `null`: chỉ `11L` đi vào nhánh mới; hai trường hợp còn lại đi vào fallback.

**Ghi nhớ:** Type pattern lọc kiểu và ràng buộc biến; record pattern duyệt và ràng buộc cấu trúc record. Kết hợp chúng làm rõ ngay trong cú pháp dữ liệu được chấp nhận, giảm ép kiểu thủ công và giúp xử lý cấu trúc nhiều tầng có kiểm soát.

## Tham khảo chính thức

- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- OpenJDK JEP 440: https://openjdk.org/jeps/440
- OpenJDK JEP 441: https://openjdk.org/jeps/441
