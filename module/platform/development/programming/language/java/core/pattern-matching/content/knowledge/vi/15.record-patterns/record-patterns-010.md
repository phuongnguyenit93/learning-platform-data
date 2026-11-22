# Pattern variable của record component trong Java 21+

## 1. Khái niệm và mục đích

`record` mô tả một kiểu dữ liệu bằng các **record component** khai báo trong phần đầu của record. Ví dụ:

~~~java
record Point(int x, int y) {}
~~~

`x` và `y` là hai record component kiểu `int`. Trình biên dịch cung cấp các accessor `x()` và `y()` để đọc giá trị từ một đối tượng `Point`.

**Record pattern** cho phép kiểm tra kiểu record rồi tách trực tiếp giá trị các component. **Pattern variable của record component** là biến cục bộ được khai báo bởi *component pattern* bên trong record pattern; biến chỉ được gán khi quá trình so khớp thành công.

~~~java
Object value = new Point(3, 5);

if (value instanceof Point(int first, int second)) {
    System.out.println(first + second); // 8
}
~~~

Trong `Point(int first, int second)`:

- `Point(...)` là **record pattern**, kiểm tra đối tượng có dạng `Point` và so khớp các component theo đúng thứ tự khai báo.
- `int first` và `int second` là **type pattern** áp dụng cho hai component, lần lượt khai báo pattern variable `first` và `second`.
- `first` nhận `3`, `second` nhận `5`; tên biến do người viết pattern chọn, không bắt buộc trùng `x` hoặc `y` trong khai báo record.
- Biến có phạm vi phụ thuộc vào nhánh mà trình biên dịch biết chắc pattern đã khớp; chúng không trở thành field hay component mới của `Point`.

Tính năng record patterns được chuẩn hóa từ **Java 21 (JEP 440)**, không cần `--enable-preview`. Java 19/20 chỉ có các bản preview; Java 17 không biên dịch được cú pháp record pattern của bài này.

## 2. Pattern variable khác gì record component và biến giữ cả record?

| Cấu trúc | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Record component | `x` trong `record Point(int x, int y)` | Thành phần dữ liệu thuộc định nghĩa kiểu record |
| Accessor | `p.x()` | Phương thức đọc component của đối tượng `p` |
| Type pattern giữ cả đối tượng | `value instanceof Point p` | Biến `p` giữ tham chiếu tới toàn bộ `Point`; truy cập bằng `p.x()` |
| Record pattern tách component | `value instanceof Point(int a, int b)` | Pattern variable `a` và `b` nhận giá trị hai component sau khi khớp |

Hai cách dùng tương đương về dữ liệu được đọc:

~~~java
if (value instanceof Point p) {
    System.out.println(p.x() + p.y());
}

if (value instanceof Point(int a, int b)) {
    System.out.println(a + b);
}
~~~

Record pattern **không trực tiếp khai báo biến đại diện cho toàn bộ record**. Những biến được ràng buộc do các pattern lồng ở từng vị trí component khai báo. Trong `Point(int a, int b)`, các tên `a`, `b` độc lập với tên component `x`, `y`.

## 3. Cơ chế khớp và kiểu của biến

Với một giá trị được kiểm tra bằng `Point(int a, int b)`, Java thực hiện về mặt ngữ nghĩa:

1. Giá trị phải khác `null` và phù hợp kiểu record `Point`.
2. Java lấy giá trị từng record component theo thứ tự khai báo bằng accessor tương ứng (`x()`, `y()`).
3. Mỗi component phải khớp với pattern tương ứng. Chỉ khi **toàn bộ** pattern khớp, các pattern variable mới được xem là đã khởi tạo và có thể sử dụng.

Số vị trí trong record pattern phải **bằng đúng số component**. Ví dụ `Point` có hai component nên `Point(int a)` thiếu vị trí và không biên dịch. Kiểu pattern cũng phải phù hợp với kiểu component: `Point(String a, int b)` không hợp lệ vì component đầu có kiểu `int`.

Có thể ghi kiểu tường minh hoặc dùng `var` để trình biên dịch suy luận:

~~~java
// Đều phù hợp với record Point(int x, int y).
if (value instanceof Point(int a, int b)) {
    System.out.println(a + b);
}

if (value instanceof Point(var a, var b)) {
    System.out.println(a + b);
}
~~~

Ở đây cả `a` lẫn `b` của mẫu `var` được suy luận là `int`. `var` nằm trong danh sách component của record pattern, không có nghĩa là biến có kiểu động; kiểu của chúng được xác định lúc biên dịch. Không thể dùng `value instanceof var v` như một top-level type pattern thay cho `Point(var a, var b)`.

**Lưu ý về accessor:** Khi destructure, record pattern sử dụng accessor của component. Nếu record tự định nghĩa accessor với logic riêng, việc khớp sẽ dùng logic đó; một exception phát sinh từ accessor khi so khớp record pattern được Java 21 bọc thành `MatchException` với cause là exception gốc. Vì vậy tránh đặt tác dụng phụ khó dự đoán trong accessor.

## 4. Phạm vi (flow scoping) và điều kiện

Pattern variable không phải biến có thể đọc ở mọi chỗ sau một câu lệnh `if`. Java chỉ cho dùng ở nơi luồng điều khiển bảo đảm pattern đã khớp.

~~~java
Object input = new Point(2, 4);

// Đúng: khi kiểm tra x > 0 thì Point đã khớp, x đã được ràng buộc.
if (input instanceof Point(var x, var y) && x > 0) {
    System.out.println("y = " + y); // y = 4
}
~~~

Ở vế phải của `&&` và trong thân `if`, `x` và `y` đã tồn tại nếu vế trái đúng. Trái lại, không thể dùng chúng tùy tiện ở nhánh `else`, sau `if` hoặc ở vế phải `||` khi nhánh đó có thể chạy do mẫu **không khớp**.

~~~java
// Các đoạn sau minh họa lỗi biên dịch, không thuộc chương trình chạy đầy đủ.

// Sai: x có thể chưa được khởi tạo ở vế phải ||.
// if (input instanceof Point(var x, var y) || x > 0) { ... }

// Sai: x không còn trong phạm vi được bảo đảm sau if.
// if (input instanceof Point(var x, var y)) { System.out.println(x); }
// System.out.println(x);
~~~

Một `switch` dùng record pattern cũng giới hạn biến trong guard `when` và nhánh `case` tương ứng; tên ở các nhánh khác không tự dùng chung. Tránh khai báo trùng tên pattern variable trong cùng một record pattern (ví dụ `Point(int x, int x)`).

## 5. Pattern lồng nhau: biến của component ở nhiều cấp

Khi một component chứa record khác, có thể destructure nhiều cấp trong một lần kiểm tra:

~~~java
record Point(int x, int y) {}
record LabeledPoint(String label, Point point) {}

Object candidate = new LabeledPoint("A", new Point(4, 7));
if (candidate instanceof LabeledPoint(String name, Point(var px, var py))) {
    System.out.println(name + ": " + px + ", " + py); // A: 4, 7
}
~~~

Trong mẫu `LabeledPoint(String name, Point(var px, var py))`:

- `name` lấy component `label` của record ngoài.
- `Point(var px, var py)` là một **record pattern lồng bên trong** áp dụng cho component `point`; `px` và `py` lấy `x` và `y` của record trong.
- Nếu `point` bằng `null` thì pattern `Point(...)` không khớp, nên nhánh `if` không chạy và không biến nào ở mẫu này được ràng buộc thành công.

Cách viết này phù hợp khi cần nhiều component của cấu trúc dữ liệu lồng nhau. Nếu chỉ cần giữ nguyên record trong, hãy dùng `LabeledPoint(var name, var point)` để ràng buộc component `point` thành một biến kiểu `Point`.

## 6. `null`: phân biệt đối tượng record và giá trị component

**Giá trị `null` không bao giờ khớp với chính một record pattern.** Do đó `value instanceof Point(var x, var y)` trả về `false` nếu `value == null`; `Point(...)` lồng nhau cũng thất bại khi giá trị record ở vị trí đó là `null`.

Tuy nhiên, component mang kiểu tham chiếu **có thể bằng `null`**. Một component type pattern với `var` (hoặc kiểu tường minh phù hợp vô điều kiện) có khả năng nhận `null` ở vị trí ấy:

~~~java
record Note(String text) {}

Object value = new Note(null);
if (value instanceof Note(var message)) {
    System.out.println(message == null); // true
}
~~~

Vì vậy cần phân biệt:

- `new Note(null) instanceof Note(var text)`: **khớp**, `text` được gán `null`.
- `new LabeledPoint("B", null) instanceof LabeledPoint(var label, Point(var x, var y))`: **không khớp**, vì record pattern `Point(...)` không nhận `null`.
- `new LabeledPoint("B", null) instanceof LabeledPoint(var label, var point)`: **khớp**, `point == null`.

Không dựa vào việc “record đã khớp” để kết luận mọi component tham chiếu đều khác `null`. Với `switch` trên giá trị có thể `null`, xử lý tường minh bằng `case null` hoặc theo hợp đồng đầu vào.

## 7. Dùng pattern variable trong `switch`

Kể từ Java 21, `switch` hỗ trợ record pattern và guard `when`. Pattern variable được dùng ngay trong guard và nhánh của chính pattern đó:

~~~java
static String classify(Object value) {
    return switch (value) {
        case Point(int x, int y) when x == y -> "Đường chéo: " + x;
        case Point(var x, var y) -> "Điểm: " + x + ", " + y;
        case null -> "null";
        default -> "Kiểu khác";
    };
}
~~~

- Nhánh đầu bắt `Point` có `x == y`; guard `when` sử dụng được `x` và `y` đã khớp.
- Nhánh tiếp theo bắt những `Point` còn lại.
- `case null` xử lý giá trị đầu vào `null`, còn `default` dành cho các kiểu khác.
- **Thứ tự nhánh quan trọng:** một pattern tổng quát đứng trước có thể *dominate* pattern hẹp hơn, khiến nhánh sau lỗi biên dịch. Đặt nhánh có guard cụ thể trước nhánh `Point(var x, var y)` tổng quát.

## 8. Generic record và suy luận kiểu

Với record generic, trình biên dịch có thể suy luận kiểu tham số và kiểu component variable từ ngữ cảnh:

~~~java
record Box<T>(T value) {}

Box<String> box = new Box<>("Java");
if (box instanceof Box(var text)) {
    System.out.println(text.toUpperCase()); // JAVA
}
~~~

Trong ví dụ này `text` có kiểu `String`, suy luận từ `Box<String>`. Record pattern không xóa bỏ quy tắc *type erasure* của Java: không nên coi việc destructure là phép kiểm chứng tự động kiểu generic của mọi đối tượng ở runtime. Các mẫu sử dụng kiểu generic tường minh vẫn phải thỏa điều kiện chuyển kiểu an toàn của trình biên dịch.

## 9. Ví dụ hoàn chỉnh chạy được trên Java 21+

Lưu thành **`RecordComponentPatternsDemo.java`**:

~~~java
public class RecordComponentPatternsDemo {
    record Point(int x, int y) {}
    record LabeledPoint(String label, Point point) {}
    record Box<T>(T value) {}

    static String format(Object value) {
        if (value instanceof LabeledPoint(String label, Point(var x, var y))) {
            return label + ": (" + x + ", " + y + ")";
        }
        return "Không khớp";
    }

    static String classify(Object value) {
        return switch (value) {
            case Point(int x, int y) when x == y -> "Đường chéo: " + x;
            case Point(var x, var y) -> "Điểm: " + x + ", " + y;
            case null -> "null";
            default -> "Kiểu khác";
        };
    }

    public static void main(String[] args) {
        Object candidate = new Point(3, 5);
        if (candidate instanceof Point(int x, int y) && x > 0) {
            System.out.println("Tổng tọa độ: " + (x + y));
        }

        System.out.println(format(new LabeledPoint("A", new Point(4, 7))));
        System.out.println(format(new LabeledPoint("B", null)));
        System.out.println(classify(new Point(6, 6)));
        System.out.println(classify(new Point(3, 5)));
        System.out.println(classify(null));

        Box<String> box = new Box<>("Java");
        if (box instanceof Box(var text)) {
            System.out.println("Nhãn: " + text.toUpperCase());
        }

        record Note(String text) {}
        Object note = new Note(null);
        if (note instanceof Note(var text)) {
            System.out.println("Text null? " + (text == null));
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 21 trở lên:

~~~bash
javac --release 21 RecordComponentPatternsDemo.java
java RecordComponentPatternsDemo
~~~

Đầu ra:

~~~text
Tổng tọa độ: 8
A: (4, 7)
Không khớp
Đường chéo: 6
Điểm: 3, 5
null
Nhãn: JAVA
Text null? true
~~~

Chương trình thể hiện: ràng buộc hai component nguyên thủy, record pattern lồng nhau, một lần không khớp do record trong `null`, `switch` có guard, suy luận kiểu generic và trường hợp component tham chiếu `null` vẫn khớp với `var`.

## 10. Lỗi thường gặp và cách tránh

| Lỗi | Nguyên nhân và cách sửa |
| --- | --- |
| Viết `Point(int x)` khi record có hai component | Arity không đúng; cung cấp đủ pattern theo thứ tự khai báo: `Point(int x, int y)`. |
| Dùng `String` pattern cho component `int` | Kiểu không tương thích; dùng `int` hoặc `var`. |
| Dùng `x` sau câu `if` mà không được bảo đảm match | Pattern variable có *flow scope*; dùng trong thân `if` hoặc nhánh được chứng minh pattern đã khớp. |
| Dùng cùng tên `x` cho hai component trong một pattern | Trùng khai báo biến; đặt tên riêng cho từng component. |
| Cho rằng `Point(...)` khớp `null` | Bản thân record pattern không khớp `null`; tách biệt chuyện component tham chiếu có thể `null`. |
| Cho rằng `var` là kiểu runtime linh hoạt | `var` được suy luận kiểu tĩnh tại compile time. |
| Destructure class bình thường như record | Record pattern chỉ áp dụng cho record class type; với class thường dùng type pattern và getter thích hợp. |
| Dùng `_` như unnamed pattern trong bài chạy Java 21 không bật preview | Java 21 không có unnamed pattern ở chế độ chuẩn; dùng biến có tên, ví dụ `var unused`. |
| Đặt nhánh `case Point(var x, var y)` trước nhánh Point hẹp hơn | Nhánh tổng quát có thể che nhánh sau; đặt pattern cụ thể trước. |
| Chạy với JDK 17 hoặc thêm `--enable-preview` theo thói quen | Cú pháp record pattern chuẩn từ JDK 21; dùng JDK 21+ và không cần preview. |

## 11. Tự kiểm tra

1. Với `record Range(int start, int end) {}`, viết `instanceof` để ràng buộc hai component vào `start` và `end` rồi tính `end - start`. Hai tên pattern variable **có thể khác** tên component.
2. Với `record User(String name, Box<String> email) {}`, giải thích vì sao `User(var name, Box(var email))` không khớp nếu component `email` chứa `null`, còn `User(var name, var box)` có thể khớp với `box == null`.
3. Với một `switch` gồm `case Point(var x, var y)` và `case Point(int x, int y) when x == y`, nhánh nào phải đứng trước, và vì sao?

Đáp án định hướng: (1) `if (obj instanceof Range(int a, int b)) { int length = b - a; }`; (2) record pattern `Box(...)` lồng trong không khớp `null` nhưng `var box` ở vị trí component có thể nhận `null`; (3) nhánh có guard `x == y` đứng trước nhánh tổng quát để tránh dominance.

## Tài liệu tham khảo

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [Java Language Specification 21, `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
