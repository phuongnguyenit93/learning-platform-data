# Record pattern trong `switch` (Java 21+)

## 1. Mục tiêu và điều kiện sử dụng

**Record pattern trong `switch`** cho phép vừa chọn nhánh theo kiểu của đối tượng, vừa **tách trực tiếp các thành phần (components) của một `record`** thành biến để xử lý. Cú pháp này phù hợp khi chương trình nhận nhiều kiểu dữ liệu có cấu trúc, chẳng hạn các loại hình học, sự kiện, thông điệp hoặc kết quả nghiệp vụ.

Hai tính năng liên quan — **Record Patterns (JEP 440)** và **Pattern Matching for `switch` (JEP 441)** — đều trở thành tính năng chính thức ở **Java 21**. Các ví dụ dưới đây yêu cầu JDK 21 trở lên, **không cần `--enable-preview`**. Java 17 có `record` và một số dạng `switch`, nhưng chưa hỗ trợ ổn định cú pháp record pattern trong `switch`.

Sau bài này, bạn có thể:
- Nhận diện cú pháp `case RecordType(pattern1, pattern2, ...)` và cách ràng buộc biến.
- Dùng `when`, record pattern lồng nhau và `switch` expression/statement.
- Kiểm soát thứ tự nhánh, `null`, tính bao phủ (exhaustiveness) và lỗi biên dịch thường gặp.
- Kết hợp `record` với `sealed` để xử lý các kiểu dữ liệu có tập biến thể xác định.

## 2. Cú pháp và cơ chế hoạt động

Cho một record:

```java
record Point(int x, int y) {}
```

Khi đầu vào có kiểu `Object`, một nhánh `switch` có thể viết:

```java
case Point(int x, int y) -> "x=" + x + ", y=" + y
```

Ý nghĩa của `Point(int x, int y)`:

1. Kiểm tra giá trị đầu vào là một đối tượng `Point` phù hợp; `null` không khớp record pattern.
2. Lấy hai component của `Point`, theo **đúng thứ tự khai báo** `x` rồi `y`, thông qua các accessor tương ứng.
3. So khớp từng component với pattern con: ở đây `int x` và `int y` khai báo hai biến kiểu `int`.
4. Nếu mọi pattern đều khớp, chạy nhánh bên phải `->`; biến `x`, `y` dùng được trong nhánh đó.

Có thể dùng `var` để suy luận kiểu từ khai báo record:

```java
case Point(var x, var y) -> "x=" + x + ", y=" + y
```

Với `record Point(int x, int y)`, cả hai biến vẫn có kiểu `int`. `var` ở đây **không biến chúng thành `Object`**. Phân biệt ba cách viết:

| Dạng | Kiểm tra / giá trị nhận được |
| --- | --- |
| `case Point p` | Type pattern: nhận cả đối tượng `Point` qua biến `p`; muốn lấy tọa độ thì gọi `p.x()`, `p.y()`. |
| `case Point(int x, int y)` | Record pattern: tách ngay hai thành phần vào `x`, `y`. |
| `case Point(var x, var y)` | Cùng cơ chế tách, để trình biên dịch suy luận kiểu từng component. |

Record pattern không tạo bản sao record, không tự thay đổi dữ liệu và không gọi constructor mới. Nó thực hiện kiểm tra kiểu và đọc các component đã có. **Số pattern con phải bằng số component**, và từng pattern phải hợp lệ với kiểu component tương ứng.

## 3. Ví dụ hoàn chỉnh: record pattern, `when` và nested pattern

Tạo tệp **`RecordSwitchDemo.java`**:

```java
public class RecordSwitchDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}

    static String describe(Object input) {
        return switch (input) {
            case null -> "Không có dữ liệu";

            case Point(int x, int y) when x == 0 && y == 0 ->
                "Gốc tọa độ";

            case Point(var x, var y) ->
                "Điểm(" + x + ", " + y + ")";

            case Segment(
                    Point(var x1, var y1),
                    Point(var x2, var y2)) ->
                "Đoạn: (" + x1 + ", " + y1 + ") -> ("
                    + x2 + ", " + y2 + ")";

            case Segment s -> "Đoạn thiếu điểm đầu hoặc cuối";

            default -> "Không hỗ trợ: "
                + input.getClass().getSimpleName();
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(0, 0)));
        System.out.println(describe(new Point(3, -2)));
        System.out.println(describe(
            new Segment(new Point(1, 2), new Point(4, 6))));
        System.out.println(describe(
            new Segment(null, new Point(4, 6))));
        System.out.println(describe("abc"));
        System.out.println(describe(null));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp bằng **JDK 21+**:

```bash
javac --release 21 -encoding UTF-8 RecordSwitchDemo.java
java RecordSwitchDemo
```

Đầu ra:

```text
Gốc tọa độ
Điểm(3, -2)
Đoạn: (1, 2) -> (4, 6)
Đoạn thiếu điểm đầu hoặc cuối
Không hỗ trợ: String
Không có dữ liệu
```

Đọc từng nhánh:

- `case null` xử lý khi chính `input` là `null`. Vì vậy nhánh `default` có thể gọi `input.getClass()` an toàn.
- `case Point(int x, int y) when x == 0 && y == 0` chỉ chạy nếu là `Point` **và** cả hai tọa độ bằng 0.
- `case Point(var x, var y)` xử lý các `Point` còn lại; hai biến được suy luận là `int`.
- `case Segment(Point(...), Point(...))` là **nested record pattern**: tách hai `Point` nằm bên trong `Segment`, rồi tách tiếp bốn tọa độ. Mỗi tầng phải khớp.
- Nếu một đầu mút của `Segment` là `null`, nested `Point(...)` ở vị trí đó không khớp. Nhánh `case Segment s` tiếp theo vẫn nhận đối tượng `Segment` và xử lý tình huống thiếu dữ liệu.
- `default` bao phủ các kiểu khác như `String`.

Ví dụ dùng một `switch` **expression**, nên toàn bộ `switch` trả về một `String` cho phương thức `describe`; không cần gán vào biến phụ hay thêm `break`. Đây cũng là một cách phân phối xử lý theo cấu trúc dữ liệu mà không cần chuỗi ép kiểu thủ công.

## 4. Guard `when` và thứ tự nhánh

`when` bổ sung điều kiện Boolean **sau khi** pattern khớp. Những biến vừa tách ra được phép dùng ngay trong guard:

```java
case Point(var x, var y) when x == y -> "Nằm trên đường x = y"
case Point(var x, var y) when x > 0 -> "Phía bên phải trục Oy"
case Point(var x, var y) -> "Điểm còn lại"
```

Ba nhánh này được xét **theo thứ tự xuất hiện**. Ví dụ `Point(2, 2)` khớp nhánh đầu và không đi tiếp; `Point(3, 1)` khớp nhánh thứ hai. Vì guard có thể trả `false`, nhánh record pattern tổng quát ở cuối vẫn cần thiết để bao phủ những trường hợp còn lại.

**Quy tắc dominance:** nếu một nhánh trước đã khớp mọi giá trị mà nhánh sau có thể khớp, nhánh sau bị xem là không thể tới được và mã **không biên dịch**. Ví dụ *cố ý sai*:

```java
// Ví dụ KHÔNG biên dịch: type pattern bao phủ record pattern sau.
return switch (input) {
    case Point p -> "Mọi Point";
    case Point(var x, var y) -> "Không thể tới"; // dominated
    default -> "Khác";
};
```

Đặt các pattern cụ thể/guard trước, rồi pattern tổng quát sau. Không đặt `case Object o` ở đầu khi phía dưới còn muốn nhận `Point` hay `Segment`: `Object o` bao phủ các đối tượng không-null khác. Trong ví dụ đầy đủ, `case Point(...) when ...` được đặt trước `case Point(var x, var y)` và nested `Segment(...)` được đặt trước `case Segment s`.

Guard là điều kiện kiểm tra lúc chạy; đừng nhầm nó với việc Java phải suy luận mọi biểu thức guard bất kỳ để sắp xếp nhánh giúp bạn. Hãy viết thứ tự case minh bạch, nhất là khi hai guard có thể cùng đúng.

## 5. `null`: phân biệt selector và component bên trong record

Có **hai mức `null`** phải phân biệt:

1. **Selector `null`**: `switch (input)` với `input == null` sẽ ném `NullPointerException` nếu không có nhánh `case null` thích hợp, kể cả khi đã có `default`. Khi muốn nhận `null` như một trường hợp nghiệp vụ, ghi `case null -> ...` tường minh.
2. **Component `null`**: record có thể chứa giá trị tham chiếu null nếu constructor không cấm. Pattern con như `Point(var x, var y)` không khớp một component là `null`. Vì vậy `Segment(Point(...), Point(...))` không khớp `new Segment(null, p)`, dù bản thân `Segment` là đối tượng hợp lệ.

Có thể kết hợp một nhánh tách sâu và một nhánh type pattern dự phòng:

```java
case Segment(Point(var ax, var ay), Point(var bx, var by)) ->
    "Hai đầu mút đầy đủ";
case Segment s -> "Một hoặc cả hai đầu mút có thể bị null";
```

Nhánh `case Segment s` không tự tách `Point` nên vẫn nhận `Segment` có component null. Nếu muốn chặn dữ liệu thiếu ngay khi tạo đối tượng, có thể kiểm tra ở compact constructor của record:

```java
record NonNullSegment(Point start, Point end) {
    NonNullSegment {
        java.util.Objects.requireNonNull(start, "start");
        java.util.Objects.requireNonNull(end, "end");
    }
}
```

Khi đó, dữ liệu thiếu bị từ chối ngay tại thời điểm tạo `NonNullSegment`. Đừng coi record pattern là cơ chế xác thực toàn bộ nghiệp vụ: nó chỉ kiểm tra kiểu và cấu trúc theo pattern đã mô tả.

## 6. `sealed` + record patterns: bao phủ đầy đủ không cần `default`

Khi dữ liệu có một tập biến thể đóng, `sealed interface` cho trình biên dịch biết các kiểu con hợp lệ. Record pattern cho phép tách thông tin khác nhau ở từng biến thể.

Tạo tệp **`ShapeSwitchDemo.java`**:

```java
public class ShapeSwitchDemo {
    sealed interface Figure permits Square, Rect {}

    record Square(int edge) implements Figure {}
    record Rect(int width, int height) implements Figure {}

    static int area(Figure figure) {
        return switch (figure) {
            case null -> throw new IllegalArgumentException("figure is null");
            case Square(var edge) -> edge * edge;
            case Rect(var width, var height) -> width * height;
        };
    }

    public static void main(String[] args) {
        System.out.println(area(new Square(4)));
        System.out.println(area(new Rect(3, 5)));
    }
}
```

Chạy:

```bash
javac --release 21 -encoding UTF-8 ShapeSwitchDemo.java
java ShapeSwitchDemo
```

Đầu ra:

```text
16
15
```

`Figure` chỉ cho phép `Square` và `Rect`, và các record pattern tương ứng bao phủ giá trị không-null của hai kiểu này. Vì vậy `switch` expression **đủ nhánh mà không cần `default`**. Nhánh `case null` thể hiện chính sách báo lỗi rõ ràng khi đầu vào thiếu. Nếu thêm một kiểu con được phép mới vào `Figure` rồi biên dịch lại, trình biên dịch có thể yêu cầu bổ sung nhánh tương ứng — một lợi ích của việc không che các biến thể bằng `default`.

Một `switch` expression phải có khả năng tạo kết quả hoặc ném ngoại lệ trên mọi đường đi. Một `switch` statement dùng pattern cũng phải bao phủ các trường hợp của kiểu selector theo quy tắc enhanced switch; vì vậy khi selector là `Object`, hãy dùng `default` hoặc một nhánh đủ tổng quát.

**Lưu ý khi chạy:** giả định về tính bao phủ được kiểm tra lúc biên dịch. Nếu một hệ phân cấp `sealed` đã thay đổi giữa các thành phần biên dịch/chạy mà mã `switch` cũ không được biên dịch lại, có thể xảy ra `MatchException` ở runtime. Trường hợp record pattern lồng nhau gặp dữ liệu null không được bao phủ cũng là tình huống cần phòng tránh, như phần trước đã minh họa.

## 7. `switch` expression, `switch` statement và phạm vi biến

Record pattern dùng được trong cả hai dạng.

- **Expression** trả về một giá trị: `String result = switch (value) { ... };`. Nếu nhánh có nhiều câu lệnh, dùng khối `{ ... yield result; }`; `yield` trả kết quả của nhánh.
- **Statement** thực hiện hành động, ví dụ ghi log, không cần trả giá trị. Cú pháp mũi tên `->` không rơi xuyên (fall-through) sang nhánh sau.

Ví dụ statement với `Point` đã khai báo ở trên:

```java
static void printPoint(Object value) {
    switch (value) {
        case null -> System.out.println("null");
        case Point(var x, var y) ->
            System.out.println("x=" + x + ", y=" + y);
        default -> System.out.println("Không phải Point");
    }
}
```

Đây là **đoạn bổ sung vào lớp có record `Point`**, không phải một tệp chạy độc lập. Đối với expression, có thể dùng khối:

```java
static String horizontalSide(Point point) {
    return switch (point) {
        case Point(var x, var y) -> {
            String side = x < 0 ? "trái" : (x > 0 ? "phải" : "trên trục Oy");
            yield side + ", y=" + y;
        }
    };
}
```

Các biến `x`, `y` do mỗi `case` khai báo chỉ có phạm vi trong guard và phần thân nhánh tương ứng. Không thể dùng chúng sau khi ra khỏi `switch`. Bạn có thể dùng lại tên biến ở những nhánh khác khi không xung đột về phạm vi.

## 8. Các lỗi hay gặp và cách sửa

| Vấn đề | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `javac` báo cú pháp `case Point(var x, var y)` không hợp lệ | Dùng Java cũ hoặc nhầm preview với tính năng chính thức | Dùng JDK 21+ và kiểm tra `javac -version`; không cần preview với Java 21. |
| Không khớp record có đủ kiểu nhưng một component là `null` | Record pattern lồng nhau cần từng pattern con khớp, trong khi pattern tham chiếu không khớp null | Thêm nhánh type pattern dự phòng, kiểm tra/chuẩn hóa dữ liệu, hoặc chặn null ngay ở constructor. |
| Nhánh ở dưới bị lỗi `dominated case label` | Nhánh tổng quát đặt trước nhánh chuyên biệt | Đưa guard/record pattern chuyên biệt lên trước; nhánh type pattern rộng đặt sau. |
| `switch` expression báo không exhaustive | Thiếu trường hợp kiểu dữ liệu, guard không bao phủ mọi giá trị hoặc thiếu `default` ở selector mở | Bao phủ tất cả biến thể `sealed`, thêm pattern dự phòng hoặc `default` có chủ đích. |
| Sai số lượng/thứ tự component | Record pattern phải theo **thứ tự khai báo** record, không theo tên hiển thị | Đối chiếu khai báo `record`; dùng `var` khi muốn để trình biên dịch suy luận kiểu. |
| Muốn tách một POJO hoặc `List` bằng `Type(...)` | Cú pháp record pattern áp dụng cho **record class**, không phải mọi lớp/collection | Dùng type pattern và API của lớp, hoặc biểu diễn dữ liệu bằng record khi phù hợp. |
| Cố phân biệt `Box<String>` và `Box<Integer>` tại runtime | Generic type argument bị xóa kiểu (type erasure); không thể dựa vào record pattern để kiểm tra mọi tham số generic | Thiết kế nhánh theo kiểu có thể kiểm tra ở runtime hoặc kiểm tra giá trị bên trong riêng. |
| Dùng `_` để bỏ qua component và không biên dịch trên Java 21 thông thường | Unnamed patterns/variables là **preview ở Java 21**, không thuộc cú pháp ổn định dùng trong bài | Dùng biến có tên trên Java 21 hoặc chủ động chọn phiên bản/cấu hình hỗ trợ `_`. |

Một điểm cần nhớ: record pattern chỉ tách thành phần theo khai báo `record`; nó không tự kiểm tra giá trị như “tọa độ phải dương” hay “tên không được rỗng”. Muốn ràng buộc thêm điều kiện khi chọn nhánh, dùng `when`; muốn bảo toàn invariant dữ liệu, kiểm tra trong constructor/logic nghiệp vụ.

Ngoài ra, việc tách component gọi các **accessor** của record. Nếu accessor do lập trình viên tùy biến ném ngoại lệ, pattern matching có thể kết thúc bất thường bằng `MatchException` với nguyên nhân gốc. Vì vậy nên giữ record/accessor đơn giản, không có tác dụng phụ bất ngờ.

## 9. Khi nào nên chọn record pattern trong `switch`?

Nên dùng khi dữ liệu đến từ nhiều **record** hoặc các record lồng nhau và mỗi dạng cần một nhánh xử lý khác nhau. Với `sealed`, compiler còn giúp đảm bảo có đủ nhánh. Nếu chỉ có một đối tượng cố định và muốn đọc một trường, gọi accessor trực tiếp (ví dụ `point.x()`) thường rõ hơn. Nếu cấu trúc quá sâu khiến một `case` dài và khó đọc, có thể tách thành phương thức nhỏ hoặc chuyển phần xác thực sang nơi tạo dữ liệu.

Để tự luyện tập, thử:
1. Thêm một nhánh `Point(var x, var y) when x == y` vào `describe` và quyết định đúng vị trí để nhánh gốc tọa độ vẫn có ưu tiên mong muốn.
2. Sửa `Segment` thành record không chấp nhận component null rồi quan sát khác biệt giữa **validation khi tạo đối tượng** và **matching lúc xử lý**.
3. Thêm `record Triangle(int base, int height) implements Figure` vào ví dụ `sealed`, cập nhật `permits` và xem trình biên dịch yêu cầu xử lý nhánh mới ra sao.

**Ghi nhớ:** `case RecordType(...)` đồng thời kiểm tra kiểu và tách dữ liệu; `when` lọc theo điều kiện; thứ tự nhánh quyết định ưu tiên; `case null` xử lý selector null; `sealed` giúp kiểm tra tính bao phủ.

## Tài liệu chính thức

- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Java Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
