# Kết hợp deconstruction với switch

## 1. Vì sao kết hợp hai tính năng?

Giả sử chương trình nhận nhiều dạng dữ liệu: một điểm (`Point`), một đoạn thẳng (`Segment`) hoặc một hình tròn (`Circle`). Nếu cần kiểm tra kiểu rồi lấy các tọa độ của từng record để xử lý, cách viết thông thường là dùng `switch` với **type pattern**, sau đó gọi accessor của record:

```java
record Point(int x, int y) {}

static String show(Object value) {
    return switch (value) {
        case Point p -> "Điểm (" + p.x() + ", " + p.y() + ")";
        case null -> "Không có dữ liệu";
        default -> "Kiểu khác";
    };
}
```

Từ **Java 21**, có thể đặt **record pattern** trực tiếp sau `case` để kiểm tra kiểu và trích xuất component ngay khi chọn nhánh:

```java
static String show(Object value) {
    return switch (value) {
        case Point(int x, int y) -> "Điểm (" + x + ", " + y + ")";
        case null -> "Không có dữ liệu";
        default -> "Kiểu khác";
    };
}
```

Hai ví dụ trên là các phương thức minh họa, giả định `Point` được khai báo trong cùng phạm vi. Khi giá trị là `new Point(2, 5)`, cả hai phương thức đều trả về `"Điểm (2, 5)"`.

**Deconstruction (phân rã record)** là việc khớp cấu trúc của record và lấy các component thành biến. `switch` đảm nhiệm chọn nhánh phù hợp; record pattern nằm trong `case` mô tả cấu trúc dữ liệu phải khớp. Sự kết hợp này đặc biệt hữu ích khi mỗi dạng record cần một cách xử lý khác nhau.

## 2. Cách đọc cú pháp case với record pattern

Với record:

```java
record Point(int x, int y) {}
```

Nhánh:

```java
case Point(int x, int y) -> "Tọa độ: " + x + ", " + y;
```

có nghĩa:

1. Kiểm tra selector của `switch` có khớp với record kiểu `Point` hay không.
2. Trích xuất component thứ nhất vào biến `x`, component thứ hai vào biến `y` theo thứ tự khai báo trong record.
3. Nếu các component pattern đều khớp, tính biểu thức ở bên phải `->` và dùng nó làm kết quả nhánh.

`Point(int x, int y)` là **mẫu**, không phải lời gọi constructor. Các biến `x` và `y` chỉ có hiệu lực trong phạm vi cho phép của nhánh `case` đó, không tự trở thành biến dùng chung cho những nhánh khác.

Có thể viết `case Point(var x, var y)`: trình biên dịch suy luận kiểu `int` từ khai báo component. Tên biến trong mẫu do người viết đặt, nhưng **thứ tự component vẫn cố định**. Ví dụ `Point(int y, int x)` vẫn nhận component đầu vào biến `y`, component sau vào biến `x`; chương trình có thể biên dịch nhưng sai ý nghĩa nếu ta tưởng tên biến quyết định vị trí.

## 3. Kết hợp deconstruction lồng nhau và when

Record có thể chứa record khác:

```java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}
```

Nếu chỉ dùng type pattern `case Segment segment`, ta cần gọi `segment.start()` và `segment.end()` để lấy hai đầu mút. Với **nested record pattern**, ta lấy bốn tọa độ ngay trong nhánh:

```java
case Segment(Point(int x1, int y1), Point(int x2, int y2)) ->
        "Từ (" + x1 + ", " + y1 + ") đến (" + x2 + ", " + y2 + ")";
```

Mẫu bên ngoài xác nhận `Segment`. Hai mẫu `Point(...)` bên trong tiếp tục kiểm tra và phân rã các component `start`, `end`. Nếu một đầu mút là `null`, mẫu `Point(...)` tương ứng không khớp, vì vậy cả nhánh lồng không được chọn. Có thể đặt một nhánh `case Segment segment` phía sau để xử lý dữ liệu thiếu.

Ngoài cấu trúc record, đôi khi còn cần kiểm tra **điều kiện bổ sung**. Java 21 dùng `when` để gắn biểu thức boolean vào nhánh có pattern:

```java
case Segment(Point(int x1, int y1), Point(int x2, int y2))
        when x1 == x2 && y1 == y2 ->
        "Đoạn suy biến";
```

Điều kiện `when` chỉ được xét khi pattern phía trước khớp và các biến `x1`, `y1`, `x2`, `y2` đã được ràng buộc. Nếu điều kiện trả về `false`, `switch` tiếp tục tìm nhánh tiếp theo phù hợp.

**Thứ tự nhánh có ý nghĩa.** Hãy đặt nhánh có `when` cụ thể trước nhánh record pattern không có guard cho cùng một loại dữ liệu. Nếu đặt nhánh `case Segment segment` tổng quát trước, các nhánh `Segment(...)` đứng sau có thể bị trình biên dịch báo **dominated case** vì không thể được chọn.

## 4. Chương trình Java 21 đầy đủ

Lưu mã sau thành tệp **`SwitchDeconstructionDemo.java`**:

```java
public class SwitchDeconstructionDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}
    record Circle(Point center, int radius) {}

    static String describe(Object value) {
        return switch (value) {
            case Point(int x, int y) ->
                    "Điểm: (" + x + ", " + y + ")";

            case Segment(Point(int x1, int y1), Point(int x2, int y2))
                    when x1 == x2 && y1 == y2 ->
                    "Đoạn suy biến tại (" + x1 + ", " + y1 + ")";

            case Segment(Point(int x1, int y1), Point(int x2, int y2)) ->
                    "Đoạn từ (" + x1 + ", " + y1 + ") đến ("
                            + x2 + ", " + y2 + ")";

            case Segment segment ->
                    "Đoạn thiếu điểm đầu hoặc cuối";

            case Circle(Point(int x, int y), int radius) when radius > 0 ->
                    "Tròn: tâm (" + x + ", " + y + "), r=" + radius;

            case Circle(Point(int x, int y), int radius) ->
                    "Tròn có bán kính không dương: " + radius;

            case Circle circle ->
                    "Tròn thiếu tâm";

            case null ->
                    "Không có dữ liệu";

            default ->
                    "Kiểu không hỗ trợ";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(1, 2)));
        System.out.println(describe(
                new Segment(new Point(0, 0), new Point(0, 0))));
        System.out.println(describe(
                new Segment(new Point(0, 1), new Point(2, 3))));
        System.out.println(describe(
                new Segment(new Point(1, 2), null)));
        System.out.println(describe(
                new Circle(new Point(3, 4), 5)));
        System.out.println(describe(
                new Circle(new Point(5, 6), 0)));
        System.out.println(describe(new Circle(null, 7)));
        System.out.println(describe("khác"));
        System.out.println(describe(null));
    }
}
```

Với **JDK 21 trở lên**, biên dịch và chạy:

```bash
javac SwitchDeconstructionDemo.java
java SwitchDeconstructionDemo
```

Kết quả dự kiến trên standard output:

```text
Điểm: (1, 2)
Đoạn suy biến tại (0, 0)
Đoạn từ (0, 1) đến (2, 3)
Đoạn thiếu điểm đầu hoặc cuối
Tròn: tâm (3, 4), r=5
Tròn có bán kính không dương: 0
Tròn thiếu tâm
Kiểu không hỗ trợ
Không có dữ liệu
```

Giải thích theo thứ tự chạy:

- `new Point(1, 2)` khớp mẫu `Point(int x, int y)` và tạo chuỗi với hai tọa độ.
- `Segment` có hai đầu mút giống nhau khớp cả mẫu lồng và điều kiện `when`, nên chọn nhánh “Đoạn suy biến”.
- `Segment` có hai đầu mút khác nhau không thỏa guard, nhưng khớp nhánh `Segment(Point(...), Point(...))` tiếp theo.
- `Segment` có `end == null` không khớp mẫu `Point(...)` ở component `end`. Nhánh tổng quát `case Segment segment` được chọn.
- `Circle` với bán kính `5` và tâm hợp lệ khớp mẫu lồng có guard `radius > 0`.
- `Circle` với bán kính `0` không thỏa guard, đi vào nhánh `Circle(Point(...), int radius)` không có guard.
- `Circle` có `center == null` không khớp `Point(...)`, nên nhánh `case Circle circle` xử lý.
- Chuỗi `"khác"` không thuộc một kiểu record được xử lý và rơi vào `default`.
- Selector `null` đi vào `case null`.

Chú ý rằng `record Circle(Point center, int radius)` không tự cấm bán kính không dương hay tâm `null`. Trong ứng dụng thực tế, có thể thêm kiểm tra trong constructor để giữ bất biến dữ liệu; ví dụ này cố ý cho phép các trường hợp ấy nhằm minh họa việc chọn nhánh.

## 5. Switch expression và switch statement

Ví dụ chính dùng **switch expression**:

```java
String result = switch (value) {
    case Point(int x, int y) -> x + ", " + y;
    case null -> "null";
    default -> "kiểu khác";
};
```

Đây là ví dụ minh họa với các khai báo `Point` và `value` có sẵn. `switch` trả về một giá trị; các nhánh phải tạo kết quả phù hợp với kiểu suy luận cho biểu thức. Với nhánh nhiều câu lệnh, dùng khối và `yield` để cung cấp kết quả:

```java
String result = switch (value) {
    case Point(int x, int y) -> {
        String location = "(" + x + ", " + y + ")";
        yield "Point " + location;
    }
    case null -> "null";
    default -> "kiểu khác";
};
```

Nếu chỉ muốn thực hiện hành động, có thể dùng **switch statement**:

```java
switch (value) {
    case Point(int x, int y) ->
            System.out.println("x + y = " + (x + y));
    case null ->
            System.out.println("Không có dữ liệu");
    default ->
            System.out.println("Loại khác");
}
```

Các đoạn này là ví dụ độc lập, không phải các biến thể được đặt cùng lúc trong một phương thức. Với nhánh dùng mũi tên `->`, Java không thực hiện **fall-through** sang nhánh kế tiếp. Record pattern và `when` có thể dùng trong cả hai dạng `switch` của Java 21.

## 6. Null, phạm vi biến và tính đầy đủ của các nhánh

### Null ở selector và null ở component khác nhau

- **Selector của switch bằng null:** `case null` xử lý. Nếu không có cách xử lý phù hợp, `switch` có thể ném `NullPointerException` trước khi chọn nhánh thông thường; `default` đơn thuần không thay thế được ý định xử lý null.
- **Một component record bằng null:** record ngoài có thể vẫn khớp về kiểu, nhưng record pattern lồng ở component đó không khớp. Ví dụ `Segment(Point(...), Point(...))` không khớp khi `end == null`; nhánh `case Segment segment` rộng hơn vẫn có thể xử lý.
- **Component tham chiếu được ràng buộc nhưng null:** record pattern không tự xác nhận mọi giá trị tham chiếu khác null. Sau khi ràng buộc dữ liệu, cần xem xét điều kiện null trước khi gọi phương thức hoặc unbox nếu giá trị có thể null.

### Biến chỉ tồn tại trong nhánh đã khớp

`x1`, `y1`, `x2`, `y2` trong nhánh `Segment(...)` có hiệu lực trong guard `when` và phần xử lý của nhánh. Không thể dùng chúng trong nhánh `Circle` hay sau toàn bộ biểu thức `switch`. Mỗi nhánh có các biến pattern riêng, kể cả khi trùng tên với biến ở nhánh khác.

### Switch expression cần đầy đủ trường hợp

Khi selector có kiểu `Object` như ví dụ chính, không thể chứng minh chỉ có `Point`, `Segment`, `Circle`. Vì vậy `default` đảm nhiệm các giá trị kiểu khác. `case null` giải quyết khả năng `null` được truyền vào. Nếu selector là một kiểu phân cấp `sealed`, các nhánh bao phủ mọi subtype được phép có thể giúp biểu thức `switch` đạt tính đầy đủ mà không cần `default` cho các giá trị không null; việc kiểm tra có đầy đủ hay không vẫn do trình biên dịch thực hiện.

## 7. Lỗi thường gặp

| Lỗi | Vì sao sai hoặc nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Viết `case Point p` rồi tưởng `x`, `y` tự có | Type pattern chỉ ràng buộc cả record vào `p`. | Dùng `case Point(int x, int y)` hoặc gọi `p.x()`, `p.y()`. |
| Đặt `case Segment segment` trước `case Segment(Point(...), Point(...))` | Nhánh rộng hơn bao phủ các giá trị mà mẫu cụ thể có thể xử lý, khiến nhánh cụ thể bị **dominated**. | Đặt case đặc thù và case có `when` trước case tổng quát. |
| Cho rằng `when` luôn chạy | Guard chỉ được xét khi pattern liên quan đã khớp. | Đặt kiểm tra điều kiện trong `when` sau pattern và dự kiến nhánh fallback khi guard sai. |
| Quên component có thể null | Mẫu record lồng không khớp nếu record bên trong là null. | Có nhánh dự phòng hoặc quy tắc dữ liệu bảo đảm component hợp lệ. |
| Nhầm thứ tự component | Pattern ràng buộc dữ liệu theo thứ tự khai báo record, không theo tên biến. | Đối chiếu khai báo record và thứ tự các component pattern. |
| Trông chờ `default` xử lý selector null | `null` cần được xử lý theo quy tắc riêng của `switch`. | Dùng `case null` khi giá trị đầu vào có thể null. |
| Dùng biến pattern ngoài nhánh | Phạm vi biến kết thúc theo quy tắc của case/nhánh khớp. | Chỉ dùng biến trong guard và phần xử lý hợp lệ của nhánh. |
| Biên dịch bằng Java 17 thông thường | Record patterns và pattern matching for switch chính thức trong Java 21. | Dùng JDK 21 trở lên; không cần `--enable-preview` trên JDK 21. |

## 8. Bài tập tự kiểm tra

Cho:

```java
record Point(int x, int y) {}
record Rectangle(Point topLeft, Point bottomRight) {}
```

Hãy viết biểu thức `switch` nhận `Object input`, dùng mẫu:

```java
case Rectangle(Point(int x1, int y1), Point(int x2, int y2)) ->
        "Rộng=" + (x2 - x1) + ", Cao=" + (y2 - y1);
```

Bổ sung nhánh `case Rectangle rectangle` để báo “Thiếu tọa độ” khi một đầu mút bằng null, cùng `case null` và `default` để xử lý đầu vào còn lại.

Với `new Rectangle(new Point(1, 2), new Point(6, 8))`, chuỗi trả về là **`Rộng=5, Cao=6`**. Bài tập giả định tọa độ hai góc có thứ tự phù hợp; nếu cần xử lý hình chữ nhật bất kể thứ tự góc, phải chuẩn hóa hoặc tính trị tuyệt đối theo yêu cầu miền dữ liệu.

**Ghi nhớ:** Đặt record pattern trong `case` cho phép `switch` vừa chọn kiểu dữ liệu, vừa phân rã các component để xử lý. Mẫu lồng nhau diễn đạt cấu trúc record bên trong; `when` thêm điều kiện sau khi mẫu khớp; thứ tự case, `null`, phạm vi biến và tính đầy đủ của switch expression quyết định hành vi chính xác của chương trình.
