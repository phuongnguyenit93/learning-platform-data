# Component pattern trong record pattern (Java 21+)

## 1. Component pattern là gì?

Một `record` mô tả dữ liệu bằng các **record component** trong phần khai báo. Ví dụ, `record Point(int x, int y) {}` có hai component `x`, `y`, đồng thời có các phương thức truy cập `x()` và `y()`.

**Record pattern** cho phép kiểm tra một giá trị có phù hợp với record hay không, rồi lấy các component ra thông qua việc so khớp mẫu (pattern matching). **Component pattern** là *mẫu nằm tại một vị trí component* bên trong dấu ngoặc của record pattern; nó quyết định giá trị ở vị trí đó phải thỏa điều kiện gì và có được gán cho biến mẫu hay không.

Ví dụ:

~~~java
record Point(int x, int y) {}

Object value = new Point(3, 5);
if (value instanceof Point(int horizontal, int vertical)) {
    System.out.println(horizontal + vertical); // 8
}
~~~

Trong `Point(int horizontal, int vertical)`, hai mẫu `int horizontal` và `int vertical` chính là hai component pattern. Chúng lần lượt nhận giá trị từ component `x` và `y`. Tên biến mẫu không cần trùng tên component đã khai báo; **vị trí và thứ tự** mới quyết định sự tương ứng.

Khả năng dùng record pattern trong `instanceof` và `switch` trở thành tính năng chính thức ở **Java 21**. Khai báo `record` đã có từ các phiên bản trước, nhưng cú pháp phân rã record bằng mẫu như trên yêu cầu Java 21+.

## 2. Đọc cú pháp từ ngoài vào trong

Xét hai record lồng nhau:

~~~java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}
~~~

Mẫu:

~~~java
Segment(Point(int sx, int sy), Point(var ex, var ey))
~~~

có các tầng sau:

1. `Segment(...)` là record pattern ngoài cùng, có **hai component pattern** tương ứng với `start` và `end`.
2. `Point(int sx, int sy)` là một **record pattern lồng nhau** tại vị trí `start`. Bên trong nó, `int sx` và `int sy` lần lượt khớp `x`, `y` của `Point`.
3. `Point(var ex, var ey)` là record pattern lồng nhau tại vị trí `end`. Kiểu của `ex`, `ey` được suy ra là `int` vì `Point` khai báo hai component kiểu `int`.

Nói cách khác, một component pattern có thể là mẫu với **kiểu tường minh** (như `int sx` hoặc `String text`), mẫu `var` (như `var ex`), hay **một record pattern khác** (như `Point(int sx, int sy)`). Việc lồng mẫu cho phép đi qua nhiều lớp record mà không cần chuỗi lời gọi `segment.start().x()`.

Mẫu phải có số vị trí tương ứng với số record component được khai báo. `Point(int x)` không hợp lệ đối với `record Point(int x, int y)` vì thiếu một vị trí.

## 3. Điều kiện để component pattern khớp

Khi đánh giá `value instanceof Segment(Point(int sx, int sy), Point(var ex, var ey))`, Java thực hiện về mặt ngữ nghĩa:

- Giá trị ngoài cùng phải khác `null` và phù hợp với kiểu record `Segment`.
- Hai giá trị component được lấy theo **thứ tự khai báo record**, tức `start` trước rồi `end`; mỗi giá trị phải khớp component pattern tương ứng.
- Với mẫu lồng `Point(...)`, giá trị component phải khác `null` và phù hợp với kiểu `Point`, sau đó các component `x`, `y` tiếp tục được so khớp.
- **Chỉ khi tất cả mẫu con khớp**, record pattern ngoài cùng mới khớp; các biến `sx`, `sy`, `ex`, `ey` được sử dụng trong nhánh đúng.

Nếu `start` là `null`, `Point(int sx, int sy)` không khớp và toàn bộ mẫu `Segment(...)` thất bại. Đây là một điểm khác với việc gọi trực tiếp `segment.start().x()` khi `start()` trả về `null`: lời gọi thủ công có thể ném `NullPointerException`.

Component pattern có kiểu cụ thể còn kiểm tra kiểu tại thời điểm chạy. Với `record Box(Object value) {}`, mẫu `Box(String text)` chỉ khớp khi giá trị của component là một `String` khác `null`. Trong khi đó, `Box(var other)` suy ra kiểu biến `other` là `Object` từ khai báo `Box`; mẫu `var` có thể tiếp nhận cả component có giá trị `null`.

## 4. Chương trình Java 21 chạy được

Lưu chương trình sau vào tệp `ComponentPatternDemo.java`:

~~~java
public class ComponentPatternDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}
    record Box(Object value) {}

    static String describe(Object input) {
        return switch (input) {
            case Box(String text) -> "String: " + text;
            case Box(Integer number) -> "Integer: " + number;
            case Box(var other) -> "Other: " + other;
            case null -> "null";
            default -> "not a Box";
        };
    }

    public static void main(String[] args) {
        Object segment = new Segment(
                new Point(2, 3),
                new Point(8, 13)
        );

        if (segment instanceof Segment(
                Point(int sx, int sy),
                Point(var ex, var ey))) {
            System.out.printf("start=(%d,%d)%n", sx, sy);
            System.out.printf("end=(%d,%d)%n", ex, ey);
            System.out.printf("delta=(%d,%d)%n", ex - sx, ey - sy);
        }

        System.out.println(describe(new Box("hi")));
        System.out.println(describe(new Box(42)));
        System.out.println(describe(new Box(null)));
        System.out.println(describe(null));
    }
}
~~~

Biên dịch và chạy bằng JDK 21 trở lên:

~~~bash
javac --release 21 ComponentPatternDemo.java
java ComponentPatternDemo
~~~

Kết quả:

~~~text
start=(2,3)
end=(8,13)
delta=(6,10)
String: hi
Integer: 42
Other: null
null
~~~

Giải thích:

- Mẫu `Segment(Point(int sx, int sy), Point(var ex, var ey))` phân rã `Segment` qua hai `Point`. Ta nhận `(sx, sy) = (2, 3)`, `(ex, ey) = (8, 13)` nên độ chênh là `(6, 10)`.
- Trong `switch`, `Box(String text)` khớp `Box("hi")`; `Box(Integer number)` khớp `Box(42)`. Đây là ví dụ component pattern vừa kiểm tra kiểu thật của component vừa tạo biến đã được thu hẹp kiểu.
- `Box(var other)` xử lý các `Box` còn lại, kể cả `Box(null)`, vì component pattern `var other` nhận được `null`. `case null` là trường hợp **chính đối tượng đem ra switch** bằng `null`, khác với một `Box` tồn tại nhưng chứa giá trị `null`.
- Đặt mẫu riêng `Box(String text)` và `Box(Integer number)` **trước** mẫu bao quát `Box(var other)`: đảo ngược thứ tự sẽ khiến các nhánh riêng không còn khả năng được chọn.

## 5. So sánh với lấy component bằng accessor

Không dùng record pattern, có thể lấy dữ liệu với những lời gọi tường minh:

~~~java
if (segment instanceof Segment s) {
    Point from = s.start();
    Point to = s.end();

    if (from != null && to != null) {
        int sx = from.x();
        int sy = from.y();
        int ex = to.x();
        int ey = to.y();
        // Sử dụng bốn tọa độ tại đây
    }
}
~~~

Đây là **đoạn minh họa**, giả sử `segment` và hai record `Point`, `Segment` đã được định nghĩa như chương trình ở trên. Record pattern rút gọn việc lấy các giá trị và diễn đạt điều kiện khớp ngay tại chỗ; accessor vẫn hữu ích khi cần xử lý từng component độc lập, tái sử dụng giá trị hoặc giữ điều kiện rẽ nhánh dễ đọc hơn.

Điểm cần phân biệt:

| Cú pháp | Ý nghĩa |
| --- | --- |
| `record Point(int x, int y) {}` | Khai báo hai record component là `x` và `y`. |
| `Point(int a, int b)` | Record pattern có hai component pattern kiểu `int`, tạo biến mẫu `a`, `b`. |
| `Point(var a, var b)` | Record pattern có hai component pattern `var`, suy ra cả hai biến là `int`. |
| `Box(String text)` | Kiểm tra component kiểu `Object` thực sự chứa `String` và tạo biến `text` kiểu `String`. |
| `Box(var content)` | Tạo biến `content` kiểu `Object` theo kiểu khai báo của component; không tự ép thành `String`. |

## 6. Những lỗi thường gặp

**Nhầm tên biến với tên record component.** Trong `Point(int y, int x)`, biến `y` nhận component *đầu tiên* và biến `x` nhận component *thứ hai*. Java không ghép theo tên; nên đặt tên nhất quán để tránh nhầm tọa độ.

**Thiếu component hoặc dùng sai kiểu.** Với `Point` có hai component, phải cung cấp đúng hai mẫu. Một component pattern cũng phải tương thích về kiểu: chẳng hạn mẫu `Point(String x, int y)` không hợp lệ khi component thứ nhất là kiểu nguyên thủy `int`.

**Cho rằng `var` kiểm tra kiểu runtime như `String`.** Với `Box(var content)`, kiểu tĩnh của `content` là `Object`; không thể gọi `content.length()` như một `String` nếu chưa kiểm tra/ép kiểu phù hợp. Hãy dùng `Box(String content)` khi mục đích là chỉ xử lý dữ liệu chuỗi.

**Không xử lý `null` và mẫu lồng nhau.** Một `Segment` có `start == null` không khớp `Segment(Point(...), ...)`. Mẫu `Box(String text)` không khớp `Box(null)`; cần một mẫu/nhánh khác nếu trường hợp đó hợp lệ trong bài toán.

**Dùng biến mẫu ngoài phạm vi.** Các biến được khai báo bởi component pattern chỉ chắc chắn có giá trị trên đường điều khiển mà pattern đã khớp, ví dụ thân của nhánh `if` hoặc nhánh `case` tương ứng. Không dùng `sx` sau `if` như thể nó luôn được tạo.

**Áp dụng record pattern cho class thông thường.** Cú pháp `Point(...)` là record pattern và cần một kiểu `record` tương ứng. Class có getter giống record không tự trở thành kiểu có thể phân rã bằng record pattern.

**Dùng sai phiên bản Java.** `record` và record pattern là hai tính năng có mốc hỗ trợ khác nhau. Dùng JDK **21+** cho ví dụ này; trên Java 21 không cần bật `--enable-preview` đối với record pattern.

## 7. Khi nào nên dùng?

Component pattern phù hợp khi mô hình dữ liệu dùng record, ta cần đọc nhanh những giá trị thành phần, đặc biệt là các record lồng nhau (`Segment` chứa `Point`) hoặc cần chọn cách xử lý dựa trên kiểu dữ liệu thật của component (`Box(Object)` chứa `String`/`Integer`). Một mẫu lồng quá sâu lại có thể khó đọc; khi logic xử lý dài, hãy tách bước kiểm tra hoặc sử dụng accessor với biến trung gian.

**Ghi nhớ:** Record pattern xác định *hình dạng record* cần khớp; từng **component pattern** xác định *điều kiện khớp của mỗi giá trị thành phần theo đúng thứ tự khai báo*. Mẫu lồng cho phép đi sâu, mẫu `var` suy ra kiểu component, còn mẫu có kiểu cụ thể có thể kiểm tra và thu hẹp kiểu của giá trị.