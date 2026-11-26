# Dùng mẫu không tên để bỏ qua thành phần của record pattern lồng nhau

Java 22 hoàn thiện Unnamed Variables & Patterns theo JEP 456. Với record pattern, ký tự `_` có thể thay cho một thành phần mà chương trình không cần kiểm tra hoặc sử dụng. Khi record pattern được lồng nhiều cấp, ta có thể chỉ lấy dữ liệu cần thiết ở sâu bên trong và bỏ qua các thành phần còn lại ngay tại vị trí của chúng.

Kỹ thuật này giúp pattern ngắn gọn hơn, tránh tạo biến chỉ để không dùng đến và làm nổi bật dữ liệu mà nhánh xử lý thực sự cần. Đây là tính năng chính thức từ Java 22; mã nguồn sử dụng nó không cần bật preview và vẫn dùng được trong các JDK hiện đại.

## 1. Ôn lại record pattern lồng nhau

Record pattern kiểm tra một giá trị có thuộc kiểu record được chỉ định hay không, sau đó tiếp tục kiểm tra các thành phần của record theo thứ tự khai báo. Nếu một thành phần cũng là record, ta có thể đặt một record pattern khác tại vị trí đó. Quá trình này được gọi là deconstruction đệ quy.

Ví dụ, xét ba record:

```java
record Point(int x, int y) {}
record ColoredPoint(Point point, String color) {}
record CanvasItem(ColoredPoint center, String id, String description) {}
```

`CanvasItem` chứa một `ColoredPoint`; `ColoredPoint` lại chứa một `Point`. Nếu muốn lấy tọa độ `x` ở bên trong, có thể viết pattern:

```java
if (value instanceof CanvasItem(
        ColoredPoint(Point(int x, int y), String color),
        String id,
        String description
)) {
    System.out.println("x = " + x);
}
```

Pattern trên kiểm tra cấu trúc của cả ba record và tạo biến cho tất cả thành phần. Nhưng nếu chương trình chỉ cần `x`, các biến `y`, `color`, `id` và `description` là không cần thiết. Mẫu không tên cho phép bỏ qua trực tiếp những vị trí đó.

## 2. Dùng `_` để bỏ qua thành phần ở từng cấp

Thay các pattern không cần thiết bằng `_`:

```java
if (value instanceof CanvasItem(
        ColoredPoint(Point(int x, _), _),
        _,
        _
)) {
    System.out.println("x = " + x);
}
```

Đọc pattern từ ngoài vào trong:

| Vị trí | Pattern | Ý nghĩa |
| --- | --- | --- |
| `CanvasItem(...)` | Record pattern ngoài cùng | Giá trị phải là một `CanvasItem` không null. |
| `ColoredPoint(...)` | Record pattern lồng thứ nhất | Thành phần `center` phải là một `ColoredPoint` không null. |
| `Point(int x, _)` | Record pattern lồng thứ hai | Thành phần `point` phải là một `Point` không null; lấy `x` và bỏ qua `y`. |
| `_` sau `Point(...)` | Mẫu không tên | Bỏ qua `color` của `ColoredPoint`. |
| Hai `_` cuối | Mẫu không tên | Bỏ qua `id` và `description` của `CanvasItem`. |

Mỗi `_` chiếm đúng vị trí của một thành phần trong khai báo record. Nó không tạo biến, không cần tên riêng và có thể được lặp lại nhiều lần trong cùng một pattern. Số lượng thành phần trong pattern vẫn phải bằng số record component của record tương ứng.

Mẫu không tên cũng không yêu cầu giá trị phải khác null. Vì vậy, các thành phần `color`, `id` hoặc `description` trong ví dụ có thể là `null` mà pattern vẫn khớp. Ta đang bỏ qua các giá trị đó hoàn toàn.

## 3. Ví dụ hoàn chỉnh với instanceof

Tạo file `NestedRecordPatternDemo.java`:

```java
record Point(int x, int y) {}
record ColoredPoint(Point point, String color) {}
record CanvasItem(ColoredPoint center, String id, String description) {}

public class NestedRecordPatternDemo {
    static void printCenterX(Object value) {
        if (value instanceof CanvasItem(
                ColoredPoint(Point(int x, _), _),
                _,
                _
        )) {
            System.out.println("Tọa độ x ở tâm: " + x);
        }
    }

    public static void main(String[] args) {
        CanvasItem item = new CanvasItem(
                new ColoredPoint(new Point(12, 8), null),
                null,
                "Điểm đánh dấu"
        );

        printCenterX(item);
    }
}
```

Kết quả:

```text
Tọa độ x ở tâm: 12
```

Trong ví dụ này, chương trình chỉ cần tọa độ `x`. Giá trị `y`, màu sắc, mã định danh và mô tả không tham gia xử lý. Các thành phần bị bỏ qua vẫn được đọc theo cấu trúc record khi pattern được khớp, nhưng không có biến nào được tạo ra để tham chiếu chúng.

## 4. Phân biệt thành phần bị bỏ qua với record lồng bị null

Có một điểm quan trọng khi kết hợp mẫu không tên và record pattern: `_` luôn khớp với giá trị của thành phần, kể cả `null`, còn một record pattern không khớp với giá trị `null`.

Ví dụ sau vẫn khớp vì `color`, `id` và `description` được bỏ qua bằng `_`:

```java
CanvasItem item = new CanvasItem(
        new ColoredPoint(new Point(12, 8), null),
        null,
        "Điểm đánh dấu"
);

printCenterX(item); // In ra tọa độ x
```

Nhưng nếu `center` là `null`, pattern lồng `ColoredPoint(...)` không khớp:

```java
CanvasItem itemWithoutCenter = new CanvasItem(
        null,
        "shape-02",
        "Không có tâm"
);

printCenterX(itemWithoutCenter); // Không in gì
```

Tương tự, nếu `center` khác null nhưng thành phần `point` là null, pattern `Point(int x, _)` cũng không khớp. Các record pattern lồng nhau đang yêu cầu cấu trúc đó thực sự tồn tại để tiếp tục tách thành phần.

Nếu không cần kiểm tra hoặc tách `center`, có thể thay toàn bộ pattern lồng bằng `_`:

```java
if (value instanceof CanvasItem(_, _, _)) {
    System.out.println("Đây là CanvasItem");
}
```

Pattern này khớp với một `CanvasItem` có `center` null hoặc không null, vì cả ba thành phần đều được bỏ qua. Bản thân giá trị `value` vẫn phải là một đối tượng `CanvasItem` không null.

## 5. Dùng mẫu không tên trong switch

Mẫu không tên cũng có thể xuất hiện trong record pattern của nhãn `case`. Điều này hữu ích khi phân loại nhiều dạng dữ liệu mà mỗi nhánh chỉ quan tâm đến một vài thành phần.

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "Giá trị null";
        case CanvasItem(ColoredPoint(Point(int x, _), _), _, _) ->
                "Tọa độ x ở tâm: " + x;
        case CanvasItem(_, _, _) ->
                "CanvasItem không có tâm Point phù hợp";
        default -> "Kiểu dữ liệu khác";
    };
}
```

Nhánh đầu tiên chỉ khớp khi có đủ cấu trúc `CanvasItem`, `ColoredPoint` và `Point`. Nhánh thứ hai bắt các `CanvasItem` còn lại, kể cả trường hợp thành phần `center` là null. `case null` được viết riêng vì `default` không khớp với giá trị null trong switch.

## 6. Khi nào dùng `_` và khi nào cần giữ kiểm tra kiểu?

Trong danh sách thành phần của record pattern, có thể dùng `_` để bỏ qua hoàn toàn một giá trị. Nếu vẫn cần kiểm tra kiểu của thành phần nhưng không cần sử dụng giá trị, có thể dùng type pattern với biến không tên.

```java
record Envelope(Object payload) {}

static boolean containsString(Object value) {
    return value instanceof Envelope(String _);
}
```

`Envelope(_)` chấp nhận mọi giá trị `payload`, bao gồm null. Trong khi đó, `Envelope(String _)` yêu cầu `payload` khớp với type pattern `String`; nó không tạo biến `String` để dùng trong thân nhánh. Vì component có kiểu khai báo `Object`, giá trị null không khớp với type pattern `String` này.

Hãy chọn theo mục đích:

| Cách viết | Ý nghĩa |
| --- | --- |
| `Envelope(_)` | Không quan tâm kiểu hoặc giá trị của `payload`; null cũng được chấp nhận. |
| `Envelope(String _)` | Chỉ khớp khi `payload` thỏa mãn type pattern `String`, nhưng không giữ lại giá trị trong biến. |
| `Envelope(String payload)` | Kiểm tra kiểu và tạo biến `payload` để sử dụng tiếp. |

## 7. Các lỗi thường gặp

- **Dùng `_` như pattern ở cấp cao nhất:** `value instanceof _` không hợp lệ. Unnamed pattern chỉ được dùng làm thành phần trong danh sách component của record pattern.
- **Tham chiếu đến `_`:** `_` không phải tên biến có thể đọc. Không thể in, trả về hoặc truyền `_` như một giá trị.
- **Thiếu hoặc thừa thành phần:** Record pattern phải có đúng số pattern tương ứng với số record component. Thành phần bị bỏ qua vẫn cần một vị trí `_`.
- **Nhầm `_` với record pattern:** `Point(_, _)` vẫn yêu cầu đối tượng là một `Point` không null. Hai `_` chỉ bỏ qua `x` và `y`; chúng không bỏ qua việc kiểm tra record `Point`.
- **Bỏ qua kiểm tra null ở cấp lồng:** Nếu cần record pattern như `Point(...)`, thành phần tương ứng không được null. Chỉ `_` mới luôn khớp với null.
- **Tạo biến không cần thiết:** Nếu giá trị không được sử dụng, ưu tiên `_` thay vì đặt tên biến rồi để biến không được tham chiếu.

## 8. Biên dịch và chạy

Unnamed Variables & Patterns là tính năng chính thức từ Java 22 theo JEP 456. Với JDK 22 trở lên, biên dịch và chạy ví dụ mà không cần `--enable-preview`:

```bash
javac --release 22 NestedRecordPatternDemo.java
java NestedRecordPatternDemo
```

Khi dùng JDK mới hơn, có thể biên dịch theo phiên bản JDK mục tiêu của dự án. Không cần giữ cờ preview chỉ vì tính năng này từng xuất hiện dưới dạng preview trong Java 21.

## 9. Tài liệu tham khảo

- [JEP 456: Unnamed Variables & Patterns](https://openjdk.org/jeps/456) — mục tiêu và thiết kế của tính năng được hoàn thiện trong Java 22.
- [Java SE 22 — Unnamed Variables and Patterns](https://docs.oracle.com/en/java/javase/22/language/unnamed-variables-and-patterns.html) — cú pháp và cách sử dụng mẫu không tên.
- [Java SE 22 — Record Patterns](https://docs.oracle.com/en/java/javase/22/language/record-patterns.html) — cách tách record và sử dụng record pattern lồng nhau.
- [Java Language Specification, Java SE 22, mục 14.30](https://docs.oracle.com/en/java/javase/22/docs/specs/unnamed-jls.html) — quy tắc chính thức về unnamed pattern, việc khớp null và pattern matching.
