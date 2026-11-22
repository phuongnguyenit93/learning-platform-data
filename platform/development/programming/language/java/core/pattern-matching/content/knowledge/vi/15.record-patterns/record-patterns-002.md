# Match record và lấy component cùng lúc

## 1. Vấn đề cần giải quyết

Một `record` gom nhiều dữ liệu có liên quan vào một kiểu dữ liệu rõ ràng. Ví dụ, `record Point(int x, int y)` biểu diễn một điểm gồm hai tọa độ. Khi nhận một giá trị có kiểu tổng quát như `Object`, chương trình thường phải thực hiện hai việc: kiểm tra xem đó có phải `Point` hay không, rồi lấy các thành phần `x` và `y` để xử lý.

Trước khi có record patterns, ta có thể dùng *type pattern* với `instanceof` rồi gọi các phương thức truy cập:

```java
record Point(int x, int y) {}

static void printSum(Object candidate) {
    if (candidate instanceof Point p) {
        int x = p.x();
        int y = p.y();
        System.out.println(x + y);
    }
}
```

**Record pattern** kết hợp việc kiểm tra kiểu và trích xuất các component ngay tại vị trí khớp mẫu:

```java
static void printSum(Object candidate) {
    if (candidate instanceof Point(int x, int y)) {
        System.out.println(x + y);
    }
}
```

Hai đoạn minh họa trên giả định có khai báo `Point` trong cùng phạm vi. Ở ví dụ thứ hai, `x` và `y` là **biến cục bộ mới được ràng buộc khi mẫu khớp**, không phải trường được khai báo mới trong `Point`.

## 2. Record pattern hoạt động như thế nào?

Với khai báo:

```java
record Point(int x, int y) {}
```

Mẫu `Point(int a, int b)` diễn đạt ba yêu cầu:

1. Giá trị đang xét phải tương thích với kiểu record `Point`.
2. Component thứ nhất, kiểu `int`, được lấy và ràng buộc vào biến `a`; component thứ hai được ràng buộc vào `b`.
3. Các mẫu thành phần cũng phải khớp. Với `int a` và `int b`, các giá trị nguyên tương ứng sẽ được ràng buộc trực tiếp.

Tên `a`, `b` do người viết mẫu chọn; chúng **không bắt buộc** trùng tên component `x`, `y`. Thứ tự mới là điều quyết định: `Point(int first, int second)` lấy component thứ nhất rồi thứ hai, theo thứ tự khai báo của record. Mẫu có thể dùng `var` để Java suy luận kiểu component, ví dụ `Point(var x, var y)`.

Cú pháp mẫu là `Point(int x, int y)`, **không** viết `new Point(...)` hay `record Point(...)`. Record pattern không tạo một `Point` mới, không thay đổi giá trị gốc và không phải cú pháp gán phân rã độc lập. Nó kiểm tra và phân rã record trong ngữ cảnh hỗ trợ pattern matching, chẳng hạn `instanceof` hoặc nhánh `case` của `switch`.

**Phân biệt hai mẫu dễ nhầm:**

| Mẫu | Khi khớp, ta có gì? |
| --- | --- |
| `candidate instanceof Point p` | Một biến `p` tham chiếu đến toàn bộ record; cần gọi `p.x()`, `p.y()` để lấy component. |
| `candidate instanceof Point(int x, int y)` | Hai biến `x`, `y` đã chứa các component tương ứng; không cần gọi accessor trong thân `if`. |

## 3. Ví dụ Java 21 chạy hoàn chỉnh

Tạo tệp `RecordPatternDemo.java` với nội dung:

```java
public class RecordPatternDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}

    static String describe(Object value) {
        return switch (value) {
            case Point(int x, int y) ->
                    "Point(" + x + ", " + y + ")";
            case Segment(Point(int x1, int y1), Point(int x2, int y2)) ->
                    "Segment[(" + x1 + ", " + y1 + ") -> ("
                            + x2 + ", " + y2 + ")]";
            case null -> "null";
            default -> "Không phải Point hoặc Segment";
        };
    }

    public static void main(String[] args) {
        Object candidate = new Point(3, 5);

        if (candidate instanceof Point(int x, int y)) {
            System.out.println("Tổng tọa độ: " + (x + y));
        }

        System.out.println(describe(candidate));
        System.out.println(describe(
                new Segment(new Point(1, 2), new Point(4, 6))));
        System.out.println(describe("khác"));
        System.out.println(describe(null));
    }
}
```

Dùng **JDK 21 trở lên** và chạy:

```bash
javac RecordPatternDemo.java
java RecordPatternDemo
```

Kết quả:

```text
Tổng tọa độ: 8
Point(3, 5)
Segment[(1, 2) -> (4, 6)]
Không phải Point hoặc Segment
null
```

Giải thích lần lượt:

- `candidate` đang chứa một `Point(3, 5)`, nên `instanceof Point(int x, int y)` khớp và ràng buộc `x = 3`, `y = 5`. Biểu thức `x + y` cho ra `8`.
- Trong `switch`, nhánh `case Point(int x, int y)` vừa chọn đúng kiểu record, vừa lấy hai tọa độ để xây dựng chuỗi.
- `Segment` có hai component mang kiểu `Point`. Mẫu `Segment(Point(int x1, int y1), Point(int x2, int y2))` khớp từ ngoài vào trong: nhận diện `Segment`, phân rã `start` và `end`, rồi tiếp tục phân rã hai `Point`. Vì vậy ta truy cập trực tiếp bốn tọa độ.
- Chuỗi `"khác"` không khớp các record pattern, nên rơi vào `default`.
- `case null` xử lý riêng giá trị `null` của biểu thức `switch`.

## 4. Phạm vi biến và điều kiện khớp

Các biến được khai báo trong pattern chỉ dùng được ở nơi trình biên dịch đã biết mẫu khớp:

```java
Object candidate = new Point(2, 7);
if (candidate instanceof Point(int x, int y)) {
    System.out.println(x * y); // 14
}
// System.out.println(x); // Lỗi biên dịch: x không nằm trong phạm vi ở đây.
```

Tương tự, `x` và `y` trong một nhánh `case` thuộc phạm vi nhánh đó. Không dùng biến của nhánh `Point` ở nhánh `Segment` hoặc bên ngoài `switch`. Khi mẫu không khớp, Java không ràng buộc các biến ấy.

Với `instanceof`, giá trị `null` làm phép kiểm tra trả về `false`; thân `if` không chạy. Với `switch` trên kiểu tham chiếu, nếu đầu vào có thể là `null` thì nên xử lý rõ ràng bằng `case null` như ví dụ; nếu không có nhánh phù hợp để xử lý `null`, `switch` có thể ném `NullPointerException`.

Mẫu lồng nhau cũng phải khớp **ở mọi cấp**. Chẳng hạn, mẫu `Segment(Point(int x1, int y1), Point(int x2, int y2))` đòi hỏi cả `start` và `end` chứa các `Point` không null. Nếu một component chứa `null`, mẫu lồng tương ứng không khớp; hãy chuẩn bị nhánh khác khi dữ liệu cho phép trường hợp đó.

## 5. Khi nào nên dùng và những lỗi thường gặp

Record patterns đặc biệt hữu ích khi xử lý dữ liệu có cấu trúc trong `if` hoặc `switch`: tọa độ, khoảng giá trị, sự kiện có các trường rõ ràng, hoặc record chứa record. Chúng giúp bỏ các lời gọi accessor lặp lại và để cấu trúc dữ liệu cần dùng hiện rõ ngay tại điều kiện hoặc nhánh xử lý. Nếu chỉ cần một component hoặc cần giữ toàn bộ record để truyền tiếp, mẫu kiểu `Point p` đôi khi dễ đọc hơn.

Các lỗi nên tránh:

- **Dùng sai phiên bản Java.** `record` là tính năng chính thức từ Java 16, nhưng **record patterns được chính thức hóa trong Java 21**. Bài này sử dụng cú pháp Java 21 và chạy không cần `--enable-preview` trên JDK 21. Không thể biên dịch mẫu `Point(int x, int y)` bằng Java 17 thông thường.
- **Nhầm thứ tự component.** Biến đặt tên tùy ý nhưng giá trị luôn đi theo thứ tự component của record. Với `record Range(int min, int max)`, mẫu `Range(int max, int min)` vẫn ràng buộc biến `max` vào component **thứ nhất**, gây sai nghĩa rất dễ bỏ sót.
- **Dùng với class thường.** Chỉ record mới hỗ trợ dạng mẫu phân rã record này; một class có các getter `getX()`, `getY()` không tự trở thành record pattern.
- **Dùng biến ngoài phạm vi.** `x`, `y` chỉ tồn tại khi phần mẫu liên quan đã khớp và trong phạm vi Java cho phép.
- **Quên xử lý trường hợp khác kiểu hoặc null.** Với `switch` có selector kiểu `Object`, cần bao phủ các kiểu khác (chẳng hạn `default`) và xét `null` nếu giá trị đầu vào có thể null.

## 6. Tự kiểm tra

Giả sử có `record Size(int width, int height) {}` và giá trị `Object value = new Size(4, 6);`:

```java
if (value instanceof Size(int width, int height)) {
    System.out.println(width * height);
}
```

Kết quả là `24`. Mẫu vừa xác nhận `value` là `Size`, vừa ràng buộc `width` và `height` theo đúng thứ tự component. Nếu đổi hai tên biến thành `height`, `width` trong mẫu, chương trình vẫn có thể biên dịch vì cả hai cùng kiểu `int`, nhưng ý nghĩa của từng giá trị sẽ bị đảo. Đây là lý do phải đọc **thứ tự khai báo record**, không suy luận dựa vào tên biến trong mẫu.

**Ghi nhớ:** `Point(int x, int y)` là một record pattern: nó thực hiện kiểm tra kiểu và lấy các component trong cùng biểu thức khớp mẫu. Khi record có cấu trúc lồng nhau, ta có thể lồng record patterns để lấy dữ liệu ở nhiều cấp, đồng thời vẫn phải chú ý phiên bản Java, phạm vi biến, thứ tự component và giá trị `null`.
