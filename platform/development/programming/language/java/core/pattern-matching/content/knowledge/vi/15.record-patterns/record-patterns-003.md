# Cú pháp record pattern cơ bản trong Java

**Record pattern** là cú pháp dùng để kiểm tra một giá trị có thuộc một kiểu `record` hay không, đồng thời *tách* (deconstruct) các thành phần của record thành những biến có tên. Tính năng được chuẩn hóa từ **Java 21 (JEP 440)**; Java 19 và 20 chỉ cung cấp phiên bản preview. Các ví dụ dưới đây dùng Java 21+, không cần bật `--enable-preview`.

## 1. Nhìn nhanh vào cú pháp

Giả sử định nghĩa record:

```java
record Point(int x, int y) {}
```

Record có hai thành phần, theo thứ tự khai báo là `x` (kiểu `int`) và `y` (kiểu `int`). Đoạn sau minh họa record pattern ở bên phải `instanceof` (đặt bên trong một phương thức):

```java
Object value = new Point(3, 5);

if (value instanceof Point(int x, int y)) {
    System.out.println(x + y); // 8
}
```

Trong biểu thức `value instanceof Point(int x, int y)`:

1. `value` là giá trị cần kiểm tra.
2. `Point` là kiểu record mà ta muốn khớp.
3. `(int x, int y)` là danh sách **component patterns**, tương ứng từng thành phần của record theo **vị trí**.
4. Khi khớp thành công, Java gán giá trị thành phần thứ nhất vào `x`, thành phần thứ hai vào `y`; các biến này chỉ dùng được ở nơi trình biên dịch biết phép khớp đã thành công.

Khuôn dạng chung:

```text
RecordType(ComponentPattern1, ComponentPattern2, ...)
```

Đây là **pattern**, không phải lời gọi constructor. `new Point(3, 5)` tạo đối tượng; `Point(int x, int y)` mô tả cách kiểm tra và tách đối tượng sẵn có. Java sử dụng các accessor của record, chẳng hạn `x()` và `y()`, để truy xuất thành phần; pattern không sửa đổi record.

## 2. Ghi kiểu tường minh hoặc dùng var

Hai cách dưới đây tương đương khi `Point` khai báo `int x, int y`:

```java
if (value instanceof Point(int x, int y)) {
    System.out.println(x + y);
}

if (value instanceof Point(var a, var b)) {
    System.out.println(a + b);
}
```

- `int x` là **type pattern**: nêu rõ kiểu của thành phần và khai báo biến `x`.
- `var a` cho phép trình biên dịch suy ra kiểu từ khai báo record; `a` và `b` đều có kiểu `int`, không phải kiểu động.
- Tên biến (`x`, `y`, `a`, `b`) do người viết tự đặt. **Thứ tự** thành phần mới quyết định dữ liệu được lấy ra; tên không cần trùng tên thành phần trong record.
- Số component patterns phải bằng số thành phần record. Với `Point(int x, int y)`, pattern `Point(int x)` sai cú pháp về số lượng thành phần và không biên dịch được.
- Kiểu pattern phải tương thích với kiểu thành phần tương ứng. `Point(String x, int y)` không hợp lệ vì thành phần đầu tiên có kiểu `int`.

Có thể gặp record không có thành phần, chẳng hạn `record Marker() {}`; pattern tương ứng là `Marker()`.

## 3. Điều kiện khớp và phạm vi biến

`instanceof` với record pattern thực hiện hai việc: xác nhận kiểu record phù hợp và kiểm tra các pattern thành phần. Nếu phép khớp thất bại, nhánh `if` không chạy; các biến được khai báo trong pattern không thể sử dụng tùy ý bên ngoài.

```java
Object input = new Point(4, 7);

if (input instanceof Point(var x, var y) && x >= 0) {
    System.out.println("x=" + x + ", y=" + y);
}
// Không sử dụng x hoặc y ở đây: ngoài phạm vi khớp đã được đảm bảo.
```

Trong toán tử `&&`, vế phải chỉ được đánh giá khi vế trái đúng, nên `x` có thể xuất hiện trong `x >= 0`. Sau điều kiện, các biến chỉ tồn tại tại những vị trí mà trình biên dịch xác định pattern chắc chắn đã khớp.

**Giá trị `null` không khớp với bất kỳ record pattern nào.** Ví dụ, `null instanceof Point(var x, var y)` cho kết quả `false`. Nếu một record chứa record khác, pattern lồng nhau cũng cần thành phần tương ứng có giá trị phù hợp để tiếp tục tách; xem ví dụ `Segment` bên dưới.

## 4. Record pattern lồng nhau

Record có thể chứa một record khác:

```java
record Segment(Point start, Point end) {}
```

Ta có thể kiểm tra và tách nhiều lớp ngay trong một pattern:

```java
Object shape = new Segment(new Point(1, 2), new Point(4, 6));

if (shape instanceof Segment(Point(var x, var y), var end)) {
    System.out.println("Start: (" + x + ", " + y + ")");
    System.out.println("End: " + end);
}
```

Ở đây, `Segment(...)` khớp record ngoài; `Point(var x, var y)` tách record `start` thành hai tọa độ; `var end` giữ nguyên thành phần `end` (kiểu suy ra là `Point`). Nếu `start` bằng `null`, pattern `Point(var x, var y)` không khớp, nên toàn bộ pattern `Segment(...)` thất bại. Đây là cách phối hợp kiểm tra kiểu và cấu trúc dữ liệu mà không cần tự gọi một chuỗi accessor trong nhánh thành công.

## 5. Dùng trong switch

Từ Java 21, `switch` cũng hỗ trợ pattern matching chính thức (JEP 441). Có thể đặt record pattern ngay sau `case`:

```java
String kind = switch (value) {
    case Point(var x, var y) -> x == 0 && y == 0 ? "Origin" : "Other point";
    case null -> "null";
    default -> "Other type";
};
```

- Nhánh `case Point(var x, var y)` vừa nhận diện `Point` vừa cấp các biến `x`, `y` cho biểu thức bên phải `->`.
- `case null` xử lý rõ giá trị `null`; nếu không có nhánh phù hợp cho `null`, `switch` này có thể ném `NullPointerException` khi nhận `null`.
- `default` xử lý những giá trị khác `Point`. Khi nhiều case có thể khớp, cần chú ý thứ tự và quy tắc dominance của `switch`; ví dụ cơ bản này chỉ dùng một record pattern.

## 6. Chương trình đầy đủ, chạy được

Lưu toàn bộ mã dưới đây vào tệp **`RecordPatternBasics.java`**:

```java
public class RecordPatternBasics {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}

    static String describe(Object value) {
        if (value instanceof Point(int x, int y)) {
            return "Point: x=" + x + ", y=" + y;
        }
        return "Not a Point";
    }

    static String startInfo(Object value) {
        if (value instanceof Segment(Point(var x, var y), var end)) {
            return "Start: (" + x + ", " + y + "), end=" + end;
        }
        return "No valid start point";
    }

    static String classify(Object value) {
        return switch (value) {
            case Point(var x, var y) -> x == 0 && y == 0 ? "Origin" : "Other point";
            case null -> "null";
            default -> "Other type";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(3, 5)));
        System.out.println(describe("hello"));
        System.out.println(startInfo(new Segment(new Point(1, 2), new Point(4, 6))));
        System.out.println(startInfo(new Segment(null, new Point(4, 6))));
        System.out.println(classify(new Point(0, 0)));
        System.out.println(classify(new Point(3, 5)));
        System.out.println(classify(null));
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac -encoding UTF-8 --release 21 RecordPatternBasics.java
java RecordPatternBasics
```

**Kết quả chuẩn:**

```text
Point: x=3, y=5
Not a Point
Start: (1, 2), end=Point[x=4, y=6]
No valid start point
Origin
Other point
null
```

Giải thích: lời gọi đầu tiên tách `Point(3, 5)` thành `x=3` và `y=5`. Chuỗi `"hello"` không phải `Point` nên đi vào nhánh còn lại. `Segment` đầu tiên có `start` hợp lệ; giá trị `end` được in qua phương thức `toString()` do record cung cấp, cho ra `Point[x=4, y=6]`. `Segment` thứ hai có `start=null` nên không khớp pattern lồng nhau. Ba lần gọi `classify` lần lượt phân biệt điểm gốc, điểm khác và `null`.

## 7. Phân biệt với type pattern và các lỗi thường gặp

| Cú pháp | Ý nghĩa |
| --- | --- |
| `value instanceof Point p` | Type pattern: kiểm tra kiểu, lấy cả record vào biến `p`; đọc thành phần bằng `p.x()`, `p.y()`. |
| `value instanceof Point(int x, int y)` | Record pattern: kiểm tra kiểu và tách hai thành phần ngay thành `x`, `y`. |
| `value instanceof Point(var x, var y)` | Record pattern với suy luận kiểu thành phần. |
| `value instanceof Segment(Point(var x, var y), var end)` | Record pattern lồng nhau: tách `Segment` rồi tách tiếp `Point`. |

Những lỗi cần tránh:

1. **Viết `Point(x, y)` mà không khai báo kiểu hoặc `var`.** `x` và `y` ở đây không phải những biểu thức để so sánh giá trị; cần viết `Point(var x, var y)` hoặc `Point(int x, int y)`.
2. **Sai số lượng hoặc thứ tự thành phần.** Pattern tách theo cấu trúc và thứ tự khai báo trong record, không ánh xạ theo tên biến. Hãy xem định nghĩa `record` trước khi viết pattern.
3. **Dùng biến pattern ngoài phạm vi đã khớp.** Hãy sử dụng chúng trong nhánh thành công hoặc điều kiện mà compiler chứng minh đã khớp.
4. **Giả định đối tượng `null` sẽ được tách.** Record pattern không khớp `null`; xử lý rõ trường hợp này khi cần, nhất là với `switch`.
5. **Dùng cú pháp tách thành phần cho class thông thường.** Record pattern yêu cầu kiểu `record`. Với class bình thường, có thể dùng type pattern `obj instanceof SomeClass c`, sau đó gọi các phương thức truy cập phù hợp.
6. **Nhầm cú pháp preview với cú pháp chuẩn Java 21.** Record patterns đã ổn định trong Java 21, nhưng một số cú pháp pattern khác, như dùng `_` cho unnamed pattern, chưa phải tính năng chính thức của Java 21; không thêm chúng vào mã cần chạy bằng `--release 21`.

## 8. Tự kiểm tra

Với `record Point(int x, int y) {}`:

- Nếu `Object v = new Point(8, 9);` và biểu thức `v instanceof Point(var a, var b)` thành công, `a + b` bằng **17**.
- Với `Segment(null, new Point(4, 6))`, pattern `Segment(Point(var x, var y), var end)` **không khớp** vì không thể tách `start=null` bằng pattern `Point(...)`.
- Nếu chỉ cần giữ cả đối tượng `Point` để gọi nhiều phương thức, type pattern `Point p` có thể dễ đọc hơn; nếu cần ngay các thành phần, chọn record pattern.

**Tham khảo chính thức:** [Oracle Java 21 – Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [JEP 440 – Record Patterns](https://openjdk.org/jeps/440), [JEP 441 – Pattern Matching for switch](https://openjdk.org/jeps/441).
