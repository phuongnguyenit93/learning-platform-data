# Record pattern là gì trong Java?

## 1. Khái niệm

**Record pattern** là một dạng *pattern matching* trong Java cho phép **kiểm tra một giá trị có thuộc kiểu `record` cần tìm hay không và, nếu khớp, tách (deconstruct) các thành phần của record thành những biến có tên** ngay tại vị trí kiểm tra. Record pattern cũng có thể lồng nhau để lấy dữ liệu nằm sâu trong nhiều record.

Ví dụ, với record biểu diễn điểm hai chiều:

```java
record Point(int x, int y) {}
```

Ta có thể viết:

```java
Object value = new Point(2, 5);

if (value instanceof Point(int x, int y)) {
    System.out.println(x + y); // 7
}
```

Ở đây, `Point(int x, int y)` là **record pattern**, không phải lời gọi constructor. Phần `Point` kiểm tra kiểu record; `(int x, int y)` mô tả cách khớp và ràng buộc hai thành phần tương ứng với `x()`, `y()`. Khi khớp thành công, biến `x` nhận `2` và `y` nhận `5`; chúng có thể dùng trong nhánh `if`.

**Phiên bản:** `record` trở thành tính năng chính thức từ **Java 16**; **record patterns** được thử nghiệm (preview) ở Java 19–20 và trở thành tính năng chính thức trong **Java 21** (JEP 440). Các ví dụ dưới đây dùng Java 21 trở lên, không cần `--enable-preview`. Java 17 có thể khai báo record nhưng chưa dùng được cú pháp record pattern.

## 2. Record pattern hoạt động như thế nào?

Với khai báo `record Point(int x, int y) {}`, Java cung cấp các phương thức truy cập thành phần `x()` và `y()`. Để hiểu lợi ích của record pattern, hãy so sánh:

**Chỉ kiểm tra kiểu bằng type pattern:**

```java
if (value instanceof Point p) {
    int x = p.x();
    int y = p.y();
    System.out.println(x + y);
}
```

**Kiểm tra kiểu và tách thành phần bằng record pattern:**

```java
if (value instanceof Point(int x, int y)) {
    System.out.println(x + y);
}
```

Cả hai ví dụ lấy dữ liệu từ một `Point`, nhưng record pattern diễn đạt trực tiếp cả cấu trúc dữ liệu cần khớp. Java thực hiện phép kiểm tra kiểu và sử dụng accessor của record để lấy các giá trị thành phần; lập trình viên không cần tự gọi từng accessor trong thân nhánh.

Một record pattern có cấu trúc khái quát:

```text
TênRecord(patternThànhPhần1, patternThànhPhần2, ...)
```

- **TênRecord** phải là một kiểu `record` phù hợp.
- Số lượng và thứ tự pattern thành phần phải tương ứng với khai báo record; việc khớp **theo vị trí**, không dựa vào tên biến. Ví dụ `Point(int y, int x)` vẫn là cú pháp hợp lệ nhưng đặt tên biến theo thứ tự dễ gây hiểu nhầm.
- Mỗi pattern con có thể ràng buộc biến như `int x`, dùng kiểu suy luận `var x` hoặc tiếp tục là một record pattern lồng nhau.
- Biến pattern chỉ được sử dụng trong phạm vi mà trình biên dịch xác định việc khớp đã thành công, ví dụ thân `if` khi điều kiện đúng hoặc nhánh `case` tương ứng.

Có thể thay kiểu tường minh bằng `var`:

```java
if (value instanceof Point(var x, var y)) {
    // Với Point(int x, int y), Java suy luận x và y là int.
    System.out.println(x + ", " + y);
}
```

`var` trong ví dụ này **không có nghĩa là kiểu động**; trình biên dịch suy luận kiểu tĩnh của từng thành phần record.

## 3. Ví dụ chạy đầy đủ: instanceof, switch và record pattern lồng nhau

Lưu mã sau thành **`RecordPatternDemo.java`**:

```java
public class RecordPatternDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}

    static String describe(Object value) {
        if (value instanceof Point(int x, int y)) {
            return "Điểm: (" + x + ", " + y + ")";
        }
        return "Không phải Point";
    }

    static String classify(Object value) {
        return switch (value) {
            case Point(int x, int y) when x == 0 && y == 0 ->
                    "Gốc tọa độ";

            case Point(int x, int y) ->
                    "Điểm (" + x + ", " + y + ")";

            case Segment(Point(int x1, int y1), Point(int x2, int y2)) ->
                    "Đoạn (" + x1 + ", " + y1 + ") -> ("
                            + x2 + ", " + y2 + ")";

            case null -> "Giá trị null";
            default -> "Loại khác";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(2, 5)));
        System.out.println(describe("text"));
        System.out.println(describe(null));

        System.out.println(classify(new Point(0, 0)));
        System.out.println(classify(
                new Segment(new Point(1, 2), new Point(3, 4))));
        System.out.println(classify(null));
    }
}
```

Biên dịch và chạy bằng **JDK 21+**:

```bash
javac --release 21 RecordPatternDemo.java
java RecordPatternDemo
```

Kết quả:

```text
Điểm: (2, 5)
Không phải Point
Không phải Point
Gốc tọa độ
Đoạn (1, 2) -> (3, 4)
Giá trị null
```

Giải thích:

1. Trong `describe`, `Point(int x, int y)` chỉ khớp khi `value` là một `Point` không null; vì vậy chuỗi `"text"` và `null` đi vào nhánh còn lại.
2. Trong `switch`, điều kiện `when x == 0 && y == 0` lọc riêng điểm gốc tọa độ. Nhánh có điều kiện đứng **trước** nhánh `Point` tổng quát để không bị nhánh tổng quát bao phủ.
3. `Segment(Point(int x1, int y1), Point(int x2, int y2))` là **record pattern lồng nhau**: Java khớp `Segment`, tiếp tục khớp hai `Point` ở `start` và `end`, rồi ràng buộc bốn tọa độ.
4. `case null` xử lý null tường minh. Với `switch` dùng pattern matching, chỉ có `default` không đồng nghĩa với việc xử lý được null: nếu không có nhánh xử lý null phù hợp, giá trị selector null có thể gây `NullPointerException`.

## 4. Các quy tắc và trường hợp dễ nhầm

### Record pattern không phải constructor hay phép tạo bản sao

`new Point(2, 5)` tạo một đối tượng mới; `Point(int x, int y)` trong `instanceof` hoặc `case` là mô tả **giá trị đầu vào cần khớp**. Pattern chỉ lấy dữ liệu từ đối tượng hiện có; nó không tạo `Point` mới và không sửa các thành phần của record.

### Record pattern chỉ deconstruct record

Không thể dùng trực tiếp cú pháp `SomeClass(...)` làm record pattern cho một lớp thông thường không khai báo bằng `record`. Với đối tượng thông thường, có thể dùng type pattern (`instanceof SomeClass s`) rồi gọi phương thức truy cập thích hợp.

### Vị trí và kiểu thành phần phải đúng

Với `record Point(int x, int y) {}`, pattern `Point(int x, int y)` khớp hai thành phần `int` theo đúng thứ tự. `Point(int x)` thiếu thành phần; `Point(String x, String y)` không tương thích kiểu và không biên dịch. Tên `x`, `y` trong pattern là **tên biến mới**, không phải khóa tra cứu thành phần theo tên.

### Cần phân biệt record null và thành phần null

Giá trị `null` không khớp bất kỳ record pattern nào; `null instanceof Point(int x, int y)` cho kết quả `false`.

Với pattern lồng nhau, ví dụ `Segment(Point(var a, var b), Point(var c, var d))`, nếu `start` hoặc `end` là `null` thì pattern `Point(...)` tương ứng **không khớp**. Điều đó không có nghĩa mọi record chứa một thành phần null đều không thể khớp: kết quả phụ thuộc pattern con dùng để khớp thành phần ấy.

### Khi accessor có hành vi bất thường

Record pattern truy cập các thành phần thông qua accessor của record. Nếu accessor bị tùy biến và ném ngoại lệ, phép khớp có thể kết thúc bằng ngoại lệ thay vì chỉ trả về `false`. Vì thế nên thiết kế accessor theo đúng ý nghĩa dữ liệu của record, tránh side effect gây bất ngờ.

### Không nhầm với type pattern và kiểm tra điều kiện

- `value instanceof Point p`: khớp kiểu và ràng buộc **toàn bộ đối tượng** vào `p`.
- `value instanceof Point(int x, int y)`: khớp kiểu và ràng buộc **các thành phần** vào `x` và `y`.
- `case Point(int x, int y) when x > 0 -> ...`: ngoài khớp record còn có điều kiện `when` của nhánh `switch`. `when` không phải một phần của bản thân cú pháp record pattern.

## 5. Khi nào nên dùng?

Record pattern hữu ích khi dữ liệu được mô hình hóa bằng record và đoạn xử lý chủ yếu quan tâm tới **cấu trúc cùng các thành phần** của dữ liệu: phân loại giá trị trong `switch`, xử lý nhiều lớp record lồng nhau, hoặc viết logic theo từng trường hợp mà không phải gọi accessor thủ công nhiều lần.

Với cấu trúc lồng nhau quá sâu, một pattern dài có thể khó đọc; hãy cân nhắc tách thành những bước nhỏ hoặc dùng type pattern nếu đoạn code thực sự cần cả đối tượng. Record pattern hỗ trợ cách viết hướng dữ liệu, nhưng không thay thế việc kiểm tra nghiệp vụ, kiểm soát null và xử lý ngoại lệ.

**Ghi nhớ:** `record` định nghĩa **hình dạng dữ liệu**; `record pattern` mô tả **hình dạng cần khớp** và lấy các thành phần trong cùng một phép kiểm tra.

### Tài liệu tham khảo

- Oracle Java 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- JEP 440 — Record Patterns: https://openjdk.org/jeps/440
