# Record pattern và danh sách component pattern (Java 21+)

## 1. Record pattern giải quyết vấn đề gì?

`record` là kiểu dữ liệu gọn để biểu diễn một nhóm thành phần có tên, chẳng hạn `record Point(int x, int y) {}`. Khi cần kiểm tra một đối tượng có phải `Point` và lấy ngay hai tọa độ, cách truyền thống dùng type pattern rồi gọi accessor:

```java
record Point(int x, int y) {}

static void printPoint(Object value) {
    if (value instanceof Point point) {
        System.out.println(point.x() + ", " + point.y());
    }
}
```

Từ Java 21, **record pattern** kết hợp hai thao tác trong một cấu trúc: kiểm tra kiểu record và phân rã (deconstruct) các component thành biến:

```java
static void printPointWithPattern(Object value) {
    if (value instanceof Point(int x, int y)) {
        System.out.println(x + ", " + y);
    }
}
```

Với `new Point(3, 5)`, nhánh `if` chạy và in `3, 5`. Với một đối tượng không phải `Point`, nhánh không chạy. Các tên `x`, `y` trong pattern là **biến mới được khai báo khi so khớp**, không phải lời gọi hàm hoặc đối số để tạo record.

**Yêu cầu phiên bản:** record pattern được chuẩn hóa trong **Java 21 (JEP 440)**; dùng JDK 21 trở lên không cần `--enable-preview`. Java 17 hỗ trợ type pattern trong `instanceof` nhưng chưa có record pattern ổn định.

## 2. Cấu trúc của một record pattern

Dạng khái quát:

```text
RecordType(componentPattern1, componentPattern2, ..., componentPatternN)
```

- `RecordType` phải là một kiểu `record`, ví dụ `Point`.
- Dấu ngoặc chứa **danh sách component pattern** có thứ tự, gồm một pattern cho **mỗi component** đã khai báo trong record.
- Mỗi pattern con có thể khai báo biến với kiểu cụ thể (`int x`, `String name`), dùng `var` để suy luận kiểu, hoặc là một record pattern khác.
- Số lượng và thứ tự pattern con bám đúng vào danh sách component của record, **không phụ thuộc tên biến** người viết đặt.

Ví dụ:

```java
record Person(String name, int age) {}

// Person(String fullName, int years) tương ứng:
// component thứ nhất: name -> biến fullName
// component thứ hai: age  -> biến years
static void show(Object value) {
    if (value instanceof Person(String fullName, int years)) {
        System.out.println(fullName + " - " + years);
    }
}
```

Trong `Person(String fullName, int years)`, hai biến `fullName` và `years` nhận giá trị qua các accessor `name()`, `age()` sau khi match thành công. Việc đổi tên biến không làm thay đổi component được đọc.

| Thành phần trong pattern | Vai trò | Ví dụ |
| --- | --- | --- |
| `int x` | Pattern có kiểu nguyên thủy, khai báo biến `x` | `Point(int x, int y)` |
| `var x` | Suy luận kiểu biến từ component tương ứng | `Point(var x, var y)` |
| `String name` | Type pattern cho component tham chiếu | `Person(String name, int age)` |
| `Point(int x, int y)` | Record pattern lồng nhau, tiếp tục phân rã | `Segment(Point(int x, int y), var end)` |

**“Danh sách component pattern” không phải `java.util.List`.** Đây là danh sách các pattern *trong cú pháp* của một record pattern, được phân cách bằng dấu phẩy.

Một record không có component vẫn có record pattern rỗng: `record Marker() {}` có thể được kiểm tra bằng `value instanceof Marker()`.

## 3. Quy trình so khớp và phạm vi biến

Với `value instanceof Point(int px, int py)`, có thể hiểu các bước theo thứ tự:

1. Kiểm tra `value` khác `null` và có thể so khớp kiểu record `Point`.
2. Lấy các component tương ứng bằng accessor của record (`x()` và `y()`).
3. So khớp từng component với pattern ở **cùng vị trí** trong danh sách.
4. Chỉ khi **toàn bộ component pattern** đều khớp, record pattern mới khớp và các biến `px`, `py` mới được dùng trong nhánh thành công.

```java
Object value = new Point(4, 9);

if (value instanceof Point(int left, int right)) {
    int sum = left + right;     // left = 4, right = 9
    System.out.println(sum);    // 13
}
// left và right không thuộc phạm vi sử dụng ở đây.
```

Record pattern kiểm tra **cấu trúc và kiểu**, không tự so sánh nội dung với một giá trị cố định. `Point(int x, int y)` vẫn khớp khi `x != y`; muốn áp dụng điều kiện như `x == y` thì kiểm tra trong thân `if` hoặc dùng `when` ở nhánh `switch`.

Lưu ý accessor có thể được định nghĩa lại trong record. Pattern dùng kết quả accessor để lấy component; không nên giả định việc deconstruct luôn là thao tác đọc trường thuần túy không thể phát sinh lỗi.

## 4. Record pattern lồng nhau

Các record có thể chứa record khác:

```java
record Point(int x, int y) {}
record Segment(Point from, Point to) {}
```

Cách lấy tọa độ bằng accessor:

```java
static void printSegmentOld(Object value) {
    if (value instanceof Segment segment) {
        Point from = segment.from();
        Point to = segment.to();
        if (from != null && to != null) {
            System.out.println(from.x() + "," + from.y()
                    + " -> " + to.x() + "," + to.y());
        }
    }
}
```

Record pattern lồng nhau thể hiện cùng cấu trúc ngay tại chỗ so khớp:

```java
static void printSegment(Object value) {
    if (value instanceof Segment(
            Point(int fromX, int fromY),
            Point(int toX, int toY))) {
        System.out.println(fromX + "," + fromY
                + " -> " + toX + "," + toY);
    }
}
```

Pattern ngoài yêu cầu `Segment`; mỗi component `from` và `to` lại phải khớp với `Point(int, int)`. Với `new Segment(new Point(0, 0), new Point(3, 4))`, kết quả là `0,0 -> 3,4`. Nếu một đầu mút bằng `null`, **record pattern lồng nhau `Point(...)` không khớp**, nên nhánh `if` không chạy.

Có thể phối hợp mức phân rã khác nhau. `Segment(Point(int x, int y), var end)` chỉ tách `from` thành hai tọa độ, còn `end` nhận toàn bộ component `to`. Đây là một ưu điểm của danh sách component pattern: mỗi vị trí có thể chứa pattern phù hợp nhu cầu xử lý.

## 5. Ví dụ đầy đủ: `instanceof`, `switch`, `when` và `null`

Lưu tệp sau với tên **RecordPatternDemo.java**. Đây là một chương trình hoàn chỉnh chạy bằng Java 21+:

```java
public class RecordPatternDemo {
    record Point(int x, int y) {}
    record Segment(Point from, Point to) {}

    static String describe(Object input) {
        return switch (input) {
            case null -> "null";
            case Point(int x, int y) when x == y ->
                    "diagonal:" + x;
            case Point(int x, int y) ->
                    "point:" + x + "," + y;
            case Segment(
                    Point(int x1, int y1),
                    Point(int x2, int y2)) ->
                    "segment:" + x1 + "," + y1
                    + " -> " + x2 + "," + y2;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(2, 2)));
        System.out.println(describe(new Point(2, 5)));
        System.out.println(describe(
                new Segment(new Point(0, 0), new Point(3, 4))));
        System.out.println(describe(null));
        System.out.println(describe(
                new Segment(null, new Point(3, 4))));
    }
}
```

Biên dịch và chạy:

```bash
javac RecordPatternDemo.java
java RecordPatternDemo
```

Kết quả chính xác:

```text
diagonal:2
point:2,5
segment:0,0 -> 3,4
null
other
```

Diễn giải:

- `case Point(int x, int y) when x == y` chỉ chạy khi vừa khớp `Point`, vừa thỏa điều kiện `x == y`. Biến từ component pattern được dùng ngay trong `when`.
- `case Point(int x, int y)` xử lý các `Point` còn lại. Đặt nhánh có điều kiện **trước** nhánh tổng quát để tránh nhánh tổng quát che mất nhánh chuyên biệt.
- `case Segment(Point(...), Point(...))` chỉ khớp nếu hai đầu mút đều là `Point` có thể deconstruct.
- `case null` xử lý riêng `input == null`. Trong `switch` Java 21, không nên trông đợi `default` tự xử lý `null`.
- `default` xử lý giá trị còn lại, gồm cả `Segment` có component `null` khiến pattern lồng nhau không khớp.

Trong `switch` với pattern, thứ tự nhánh còn chịu quy tắc **dominance** của Java: nhánh tổng quát có thể khiến một nhánh cụ thể đặt phía sau trở nên không hợp lệ ngay khi biên dịch.

## 6. `var` và type inference trong component pattern

Không cần lặp lại kiểu component khi compiler suy luận được:

```java
record Point(int x, int y) {}

static void print(Object input) {
    if (input instanceof Point(var x, var y)) {
        // Compiler suy luận x và y đều là int.
        System.out.println(x + y);
    }
}
```

Với generic record, thông tin kiểu tĩnh cũng giúp suy luận:

```java
record Box<T>(T value) {}

static void showUppercase(Box<String> box) {
    if (box instanceof Box(var text)) {
        // text được suy luận là String trong ngữ cảnh Box<String>.
        System.out.println(text.toUpperCase());
    }
}
```

Ví dụ trên giả định `value` khác `null` khi gọi `toUpperCase()`. `var` **không tự kiểm tra non-null** cho mọi component. Khi muốn bảo đảm component là `String` từ một record khai báo `Object`, có thể dùng type pattern rõ ràng, chẳng hạn `Entry(String text)` với `record Entry(Object value) {}`.

Với generic record, cách ghi tham số kiểu tường minh (ví dụ `Box<String>(String text)`) còn chịu quy tắc chuyển kiểu an toàn tại thời điểm biên dịch. Không thể tùy ý dùng một `Box` raw rồi ép pattern thành `Box<String>` nếu việc đó đòi hỏi unchecked conversion.

## 7. Cẩn thận với `null` trong danh sách component pattern

Cần phân biệt **giá trị đem so khớp với record pattern** và **giá trị của một component**:

- Bản thân `null` **không khớp** với `Point(int x, int y)` hoặc bất kỳ record pattern nào.
- Nếu component là `null` và pattern ở vị trí đó cũng là **record pattern lồng nhau** (như `Point(int x, int y)`), nhánh này không khớp.
- Một **type pattern ở vị trí component** có thể khớp `null` khi nó là pattern vô điều kiện đối với kiểu khai báo của component. Vì vậy không thể kết luận rằng *mọi component null đều làm record pattern thất bại*.

Ví dụ minh họa khác biệt:

```java
record Entry(Object value) {}

static void checkNullComponents() {
    Entry item = new Entry(null);
    System.out.println(item instanceof Entry(var anyValue)); // true
    System.out.println(item instanceof Entry(String text));   // false
}
```

`Entry(var anyValue)` lấy component có kiểu tĩnh `Object` và có thể khớp giá trị `null`; `Entry(String text)` đòi component khớp kiểu `String` nên không khớp `null` trong trường hợp này. Cả hai vẫn yêu cầu **đối tượng `Entry` bên ngoài khác `null`**.

Khi xử lý dữ liệu có thể thiếu, hãy thể hiện chính sách `null` rõ ràng trong logic nghiệp vụ. Với `switch`, bổ sung `case null` cho selector khi có khả năng nhận `null`.

## 8. Các lỗi cú pháp và tư duy thường gặp

**Sai số component:** record pattern phải có đủ pattern cho từng component. Với `record Point(int x, int y) {}`, cách viết `Point(int x)` hoặc `Point(int x, int y, int z)` là lỗi biên dịch, vì `Point` có đúng hai component.

**Nhầm vị trí và tên:** `Point(int y, int x)` vẫn biên dịch vì cả hai component đều là `int`, nhưng biến `y` nhận component thứ nhất (`x()`), biến `x` nhận component thứ hai (`y()`). Tên không định tuyến giá trị; **thứ tự mới quyết định**.

**Dùng record pattern cho class thường:** cú pháp `Customer(String name)` chỉ hợp lệ nếu `Customer` là record tương ứng; record pattern không tự phân rã class bất kỳ có getter.

**Nhầm pattern với constructor:** `Point(int x, int y)` trong `instanceof`/`case` không tạo đối tượng mới. Tạo record cần `new Point(1, 2)`. Pattern chỉ thử khớp và khai báo biến.

**Đặt trùng tên biến:** `Point(int x, int x)` không hợp lệ, vì hai component pattern cùng khai báo biến tên `x`. Muốn kiểm tra hai tọa độ bằng nhau, dùng hai tên riêng và so sánh chúng.

**Dùng biến ngoài phạm vi:** biến từ pattern chỉ sẵn sàng tại các vị trí được bảo đảm match, như nhánh `if` đúng hoặc phần thân nhánh `case` tương ứng. Không sử dụng biến đó ở nhánh không match.

**Sai thứ tự `case`:** nhánh khớp chung có thể bao phủ nhánh cụ thể; nên tổ chức `when` và các case có chủ đích để chương trình biên dịch và xử lý đúng thứ tự.

**Dùng ký hiệu `_` với Java 21 mặc định:** unnamed pattern/variable là tính năng preview trong Java 21; nếu cần bài thực hành Java 21 không bật preview, hãy dùng tên biến thông thường (có thể không sử dụng biến đó).

**Nhầm với record pattern trong enhanced `for`:** Java 21 không hỗ trợ đặt record pattern ở header của enhanced `for`. Hãy dùng `for (var item : items)` rồi match `item` trong thân vòng lặp.

## 9. Bài tập tự kiểm tra

**Bài 1.** Cho `record RGB(int red, int green, int blue) {}`. Viết pattern để lấy ba component và in tổng. Lời giải:

```java
static void printBrightness(Object color) {
    if (color instanceof RGB(int r, int g, int b)) {
        System.out.println(r + g + b);
    }
}
```

Với `new RGB(10, 20, 30)`, kết quả là `60`. Đây là tổng ba giá trị trong ví dụ, không phải công thức độ sáng màu chuẩn.

**Bài 2.** Cho `record Segment(Point from, Point to) {}`. Pattern `Segment(Point(var x, var y), var end)` lấy được thông tin gì?

Đáp án: `x` và `y` là hai tọa độ của `from`; `end` là toàn bộ component `to` (kiểu `Point`). Vì `from` được kiểm tra bằng record pattern lồng nhau, pattern không khớp nếu `from == null`. Nếu không cần tách `to` thành tọa độ, cách viết này đơn giản hơn việc lồng thêm một `Point(...)`.

**Bài 3.** Tại sao `Point(int a, int b)` không tự bảo đảm `a == b`?

Đáp án: danh sách component pattern khớp theo **kiểu và vị trí**; nó khai báo biến `a`, `b` mà không đặt điều kiện quan hệ giữa hai giá trị. Dùng `if (a == b)` trong nhánh đã match hoặc `when a == b` trong `case`.

## 10. Ghi nhớ

Record pattern có dạng **`TênRecord(danh sách component pattern)`**. Nó kiểm tra kiểu record và phân rã các component theo thứ tự khai báo; mỗi vị trí có thể là type pattern, `var` hoặc record pattern lồng nhau. Danh sách phải đúng số lượng component, biến chỉ có hiệu lực khi pattern khớp, và cần xét `null` theo từng mức lồng. Kết hợp với `instanceof` và `switch` giúp biểu đạt việc đọc dữ liệu có cấu trúc ngay tại điểm ra quyết định.

Tài liệu đối chiếu:
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Oracle Java 21 — Java Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
