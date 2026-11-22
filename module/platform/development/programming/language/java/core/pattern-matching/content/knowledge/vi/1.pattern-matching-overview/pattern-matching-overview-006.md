# Vai trò của `instanceof`, `switch` và `record` trong Java Pattern Matching

## 1. Bức tranh chung: nhận diện, phân nhánh và khai thác dữ liệu

Trong Java, **pattern matching (so khớp mẫu)** là cách kiểm tra một giá trị có phù hợp với một hình dạng/kiểu dữ liệu mong đợi hay không, đồng thời khai báo biến để sử dụng phần dữ liệu đã khớp. Nhờ đó, chương trình tránh lặp lại thao tác kiểm tra kiểu rồi ép kiểu thủ công.

Giả sử một phương thức nhận `Object`: giá trị thực tế có thể là `String`, `Integer`, một đối tượng miền nghiệp vụ, hoặc `null`. Để xử lý, ta thường phải trả lời ba câu hỏi:

1. **Đây là đối tượng thuộc kiểu nào?** `instanceof` cùng type pattern giúp kiểm tra một khả năng và lấy đối tượng đã được gán kiểu.
2. **Có nhiều khả năng khác nhau thì chọn nhánh nào?** `switch` với pattern giúp diễn đạt một phép phân loại nhiều nhánh, rõ ràng và được trình biên dịch kiểm tra.
3. **Dữ liệu có cấu trúc nào, gồm những thành phần nào?** `record` khai báo một kiểu dữ liệu mang giá trị; **record pattern** (Java 21+) cho phép khớp và tách trực tiếp các thành phần của một `record`.

Một phân biệt quan trọng: **`record` tự nó không phải phép so khớp mẫu**. Nó là cách định nghĩa lớp dữ liệu. Cú pháp `Point(int x, int y)` trong ngữ cảnh `instanceof` hoặc `case` mới là *record pattern*.

| Công cụ | Vai trò chính | Phiên bản ổn định |
| --- | --- | --- |
| `obj instanceof T value` | Kiểm tra một type pattern và tạo biến đã có kiểu `T` | Java 16 |
| `record Point(int x, int y) {}` | Định nghĩa kiểu dữ liệu với các thành phần được công khai qua accessor | Java 16 |
| `switch` expression với nhãn hằng | Chọn kết quả theo `int`, `String`, `enum`… | Java 14 |
| `switch` với `case T value` và `when` | So khớp nhiều kiểu/điều kiện theo thứ tự | Java 21 |
| `Point(int x, int y)` dưới dạng record pattern | Kiểm tra `Point` và tách các thành phần | Java 21 |
| `sealed` interface/class | Giới hạn các kiểu con được phép, hỗ trợ `switch` bao phủ đủ các trường hợp | Java 17 |

Ở Java 17, `instanceof` pattern và `record` đã dùng được bình thường; pattern matching cho `switch` mới ở giai đoạn *preview*, không thể dùng như cú pháp ổn định của Java 17. Các ví dụ `switch` theo kiểu và record pattern dưới đây yêu cầu **JDK 21 trở lên**.

## 2. `instanceof`: nhận diện một kiểu và loại bỏ ép kiểu lặp lại

### Trước và sau khi có type pattern

Cách truyền thống kiểm tra kiểu trước, rồi ép kiểu trong nhánh đã xác nhận:

```java
static int length(Object input) {
    if (input instanceof String) {
        String text = (String) input;
        return text.length();
    }
    return 0;
}
```

Với type pattern, `text` chỉ được gán khi `input` thực sự là `String`:

```java
static int length(Object input) {
    if (input instanceof String text) {
        return text.length();
    }
    return 0;
}
```

Tại đây, `String text` vừa là **kiểm tra kiểu**, vừa là **biến gắn với giá trị khớp**. Kiểu của `text` đã được trình biên dịch xác định, nên không cần ép kiểu. Khi `input == null`, `instanceof String text` trả về `false`.

### Phạm vi biến phụ thuộc vào luồng điều khiển

Java chỉ cho dùng biến pattern tại nơi trình biên dịch chứng minh rằng phép khớp đã thành công. Vì `&&` đánh giá vế phải khi vế trái đúng, đoạn này hợp lệ:

```java
if (input instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
```

Ngược lại, biểu thức sau **không biên dịch**, vì ở vế phải của `||`, `text` có thể chưa được gán:

```java
// KHÔNG HỢP LỆ:
// if (input instanceof String text || text.isBlank()) { ... }
```

Một nhánh thoát sớm cũng có thể giúp biến còn hiệu lực ở phía sau:

```java
static String normalized(Object input) {
    if (!(input instanceof String text)) {
        return "Không phải chuỗi";
    }
    return text.strip();
}
```

Quy tắc thực hành: dùng `instanceof` khi chỉ cần xử lý **một kiểu đặc biệt**, hoặc khi một điều kiện ngắn tự nhiên hơn nhiều nhánh `switch`.

## 3. `record`: mô hình hóa dữ liệu để việc so khớp dễ hiểu

Một `record` là dạng lớp dùng để biểu diễn dữ liệu có cấu trúc cố định, ví dụ tọa độ:

```java
record Point(int x, int y) {}
```

Khai báo trên tự tạo constructor tương ứng, các accessor `x()` và `y()`, cùng `equals()`, `hashCode()`, `toString()`. Các trường thành phần là `private final`; đối tượng `Point` không có setter tự sinh. Cách truy cập là `point.x()`, không phải `point.getX()`.

`record` giúp người đọc nhìn ngay thấy một giá trị gồm những thành phần nào. Tuy nhiên, nó **không tự đảm bảo bất biến sâu**: nếu một thành phần chứa `List` có thể sửa đổi, nội dung danh sách vẫn có thể thay đổi. `record` cũng không tự cấm `null`; có thể bổ sung kiểm tra trong constructor khi miền dữ liệu cần điều đó.

```java
record User(String name, int age) {
    User {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
        if (age < 0) {
            throw new IllegalArgumentException("age must be non-negative");
        }
    }
}
```

Đây là *compact constructor*: Java gán các tham số thành phần cho trường của record sau phần thân constructor. Một record vẫn là lớp (ngầm `final`, kế thừa `java.lang.Record`), có thể triển khai interface, nhưng không được kế thừa một lớp tùy ý.

### Ví dụ hoàn chỉnh cho Java 17

Tệp **`Instanceof17Demo.java`** kết hợp `record` và type pattern; hoàn toàn không cần tính năng preview:

```java
public class Instanceof17Demo {
    record Point(int x, int y) {}

    static String describe(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "Text: " + text.strip();
        }
        if (value instanceof Point point) {
            return "Point: " + point.x() + "," + point.y();
        }
        return "Other";
    }

    public static void main(String[] args) {
        System.out.println(describe("  Hello  "));
        System.out.println(describe(new Point(2, 3)));
        System.out.println(describe(null));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac Instanceof17Demo.java
java Instanceof17Demo
```

Kết quả:

```text
Text: Hello
Point: 2,3
Other
```

Ở đây `record Point` định nghĩa **hình dạng dữ liệu**; `instanceof Point point` chỉ xác nhận đúng kiểu rồi cho truy cập qua `point.x()` và `point.y()`. Nó **chưa** tách hai thành phần trực tiếp thành biến `x`, `y` — đó là vai trò của record pattern trong Java 21.

## 4. `switch`: lựa chọn giữa nhiều mẫu

### `switch` truyền thống và `switch` có pattern khác nhau thế nào?

`switch` truyền thống chọn nhánh theo một **giá trị hằng** (chẳng hạn `case "DONE"` hoặc `case 1`). `switch` expression kiểu này đã ổn định trước Java 17:

```java
static String label(String status) {
    return switch (status) {
        case "NEW" -> "Mới";
        case "DONE" -> "Hoàn tất";
        default -> "Khác";
    };
}
```

Từ Java 21, `switch` còn có thể chọn nhánh theo **kiểu và điều kiện** của giá trị:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "Không có giá trị";
        case Integer n -> "Số nguyên: " + n;
        case String text when text.isBlank() -> "Chuỗi trống";
        case String text -> "Chuỗi: " + text;
        default -> "Kiểu khác";
    };
}
```

`case String text` kiểm tra kiểu và tạo biến `text`. `when text.isBlank()` là điều kiện bổ sung (*guard*), chỉ được đánh giá sau khi pattern khớp. Nhánh `String` có guard phải đứng trước nhánh `String` tổng quát.

### Thứ tự, tính bao phủ và `null`

- **Thứ tự có ý nghĩa.** Nếu `case CharSequence chars` đứng trước `case String text`, nhánh `String` bị che khuất (*dominated*) vì mọi `String` đều là `CharSequence`; Java báo lỗi biên dịch. Đặt trường hợp cụ thể trước trường hợp rộng hơn.
- **Tính đầy đủ (*exhaustiveness*).** `switch` expression phải bao phủ mọi trường hợp có thể xảy ra. Khi xét kiểu `Object`, thường cần `default`. Với một hệ kiểu `sealed`, trình biên dịch có thể kiểm tra đã liệt kê đủ các kiểu con hợp lệ, nên không cần `default`.
- **`null` phải được xét riêng.** Pattern kiểu thông thường không khớp `null`; nếu `switch` gặp `null` mà không có `case null`, nó có thể ném `NullPointerException`. Một `default` thông thường không thay thế cho việc xử lý `null`.
- **Biến pattern có phạm vi trong nhánh tương ứng.** Biến từ `case Integer n` không tồn tại ở nhánh `case String text` hoặc sau toàn bộ `switch`.

Dùng `switch` khi nhiều kiểu đầu vào tương ứng với những hành động rõ ràng, nhất là khi cần trình biên dịch cảnh báo trường hợp còn thiếu.

## 5. Record pattern: kiểm tra kiểu và tách dữ liệu ngay trong mẫu (Java 21+)

Type pattern `Point point` chỉ gắn tên cho **toàn bộ** đối tượng. Record pattern `Point(int x, int y)` đi thêm một bước: kiểm tra đối tượng là `Point`, rồi khớp lần lượt các thành phần để đưa `x`, `y` vào phạm vi sử dụng.

Đoạn minh họa sau đặt trong một lớp Java 21 có khai báo `record Point(int x, int y) {}`:

```java
Object candidate = new Point(2, 3);

if (candidate instanceof Point(int x, int y)) {
    System.out.println(x + y); // 5
}
```

Record pattern cũng có thể lồng nhau khi mô hình dữ liệu chứa các record khác:

```java
record Address(String city) {}
record Person(String name, Address address) {}

// Giả sử các khai báo record ở cùng phạm vi lớp với đoạn sử dụng:
Object value = new Person("An", new Address("Hà Nội"));
if (value instanceof Person(String name, Address(String city))) {
    System.out.println(name + " ở " + city);
}
```

Khi chạy trong bối cảnh đã nêu, dòng in ra là `An ở Hà Nội`. Các đoạn ở mục này là **minh họa cú pháp**, không phải tệp Java độc lập; ví dụ chạy hoàn chỉnh xuất hiện ngay dưới đây.

Record pattern là công cụ **phân rã có kiểm tra** (*deconstruction*): nó không thay đổi đối tượng gốc, không tự gọi setter và không tạo bản sao. Nếu cấu trúc record lồng nhau có giá trị `null`, một mẫu con yêu cầu kiểu đối tượng cụ thể có thể không khớp; vì vậy cần thiết kế bất biến dữ liệu hoặc xử lý `null` cho phù hợp.

## 6. Kết hợp `sealed`, `record` và `switch` cho dữ liệu có nhiều biến thể

Mỗi công cụ đảm nhận một phần của mô hình:

- `sealed interface Event` xác định **tập các biến thể được phép**.
- `record Moved` và `record Stopped` định nghĩa **dữ liệu của từng biến thể**.
- `switch` với pattern chọn **cách xử lý tương ứng**; record pattern lấy trực tiếp tọa độ từ `Moved`.
- `when` phân biệt trường hợp đặc biệt trong cùng một biến thể.

Tạo tệp **`PatternSwitch21Demo.java`**:

```java
public class PatternSwitch21Demo {
    sealed interface Event permits Moved, Stopped {}

    record Moved(int x, int y) implements Event {}
    record Stopped() implements Event {}

    static String describe(Event event) {
        return switch (event) {
            case null -> "No event";
            case Moved(int x, int y) when x == 0 && y == 0 -> "Origin";
            case Moved(int x, int y) -> "Moved(" + x + ", " + y + ")";
            case Stopped ignored -> "Stopped";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Moved(0, 0)));
        System.out.println(describe(new Moved(2, 3)));
        System.out.println(describe(new Stopped()));
        System.out.println(describe(null));
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên, chọn đích ngôn ngữ Java 21:

```bash
javac --release 21 PatternSwitch21Demo.java
java PatternSwitch21Demo
```

Kết quả chính xác:

```text
Origin
Moved(2, 3)
Stopped
No event
```

Không cần `default` vì `Event` là `sealed` và các nhánh không có guard đã bao phủ cả `Moved` lẫn `Stopped`; `case null` xử lý giá trị `null` riêng. Nếu sau này thêm biến thể `record Paused() implements Event` và cập nhật `permits`, trình biên dịch sẽ báo `switch` chưa đủ nhánh khi biên dịch lại đoạn xử lý.

Trái lại, một `switch` trên `Object` khó biết hết kiểu đầu vào nên thường phải có `default`. Với quan hệ miền nghiệp vụ giới hạn được, bộ ba `sealed + record + switch` giúp mô hình hóa một tập lựa chọn hữu hạn một cách rõ ràng.

## 7. Chọn công cụ nào cho từng bài toán?

| Tình huống | Cách tiếp cận phù hợp | Lý do |
| --- | --- | --- |
| Một nhánh xử lý riêng khi đầu vào là `String` | `if (obj instanceof String s)` | Ngắn gọn, không phải ép kiểu |
| Đầu vào có nhiều loại và mỗi loại có quy tắc khác nhau | `switch` với type pattern (Java 21+) | Nhìn thấy các nhánh và thứ tự ngay một chỗ |
| Cần một kiểu dữ liệu nhỏ như tọa độ, khoảng thời gian, kết quả tính toán | `record` | Nêu rõ thành phần, tự có constructor/accessor/value methods |
| Cần trích trực tiếp nhiều thành phần của một record | Record pattern (Java 21+) | Tránh gọi thủ công nhiều accessor trong điều kiện và nhánh |
| Một tập biến thể nghiệp vụ đóng, ví dụ `Success`/`Failure` | `sealed` + các kiểu con + `switch` | Kiểm tra tính bao phủ khi thêm biến thể |
| Dự án phải chạy trên Java 17 và không bật preview | `instanceof` pattern + `record` + `if/else` hoặc `switch` hằng | Không phụ thuộc cú pháp Java 21 |

Không phải mọi `if/else` đều cần đổi thành `switch`: nếu chỉ kiểm tra một trường hợp, `instanceof` rõ ràng hơn. Không phải mọi lớp đều nên thành `record`: đối tượng có danh tính riêng, trạng thái thay đổi hoặc hành vi phức tạp thường cần lớp thường. Và `record` không bắt buộc phải đi với pattern matching; nhiều record được dùng bình thường qua accessor.

## 8. Lỗi phổ biến và cách tự kiểm tra

1. **Nhầm mốc phiên bản.** `record` và `instanceof T t` chạy ổn định trên Java 17; `case T t`, `when` và `Point(int x, int y)` dưới dạng pattern trong ví dụ yêu cầu Java 21+. Dự án nên cấu hình rõ `--release` hoặc language level trong công cụ build/IDE.
2. **Cho rằng `record` tự phân rã dữ liệu.** `record Point(int x, int y)` định nghĩa kiểu; `instanceof Point p` chỉ tạo biến `p`; `instanceof Point(int x, int y)` mới tạo biến thành phần.
3. **Sử dụng biến pattern ngoài phạm vi chắc chắn khớp.** Cần xét kỹ `&&`, `||`, phủ định `!` và nhánh thoát sớm; trình biên dịch dùng phân tích luồng điều khiển để kiểm tra.
4. **Đặt mẫu tổng quát trước mẫu cụ thể trong `switch`.** Ví dụ `CharSequence` che `String`. Với `when`, nhánh có điều kiện nên đứng trước nhánh cùng kiểu không có điều kiện.
5. **Quên `null`.** `instanceof` với `null` là `false`; `switch` pattern có thể cần `case null`; thành phần trong record cũng có thể `null` nếu không được kiểm tra.
6. **Đồng nhất `final` với bất biến sâu.** Record giữ cố định tham chiếu thành phần; đối tượng mà tham chiếu trỏ tới vẫn có thể thay đổi. Khi cần dữ liệu bất biến, hãy dùng kiểu thành phần bất biến hoặc bản sao phòng vệ.
7. **Lạm dụng mẫu tham số hóa không thể kiểm tra ở runtime.** Chẳng hạn `instanceof java.util.List<String> list` không hợp lệ theo cách kiểm tra kiểu thông thường vì generic bị xóa kiểu; thường phải khớp `List<?> list` rồi kiểm tra các phần tử nếu cần.

### Tự thực hành

- Trên Java 17, thêm nhánh `Integer` vào `Instanceof17Demo.describe`. Thử đầu vào `null`, chuỗi trắng và `Point`; giải thích nhánh được chọn.
- Trên Java 21, thêm biến thể `Paused` vào `Event`, cập nhật `permits`, rồi quan sát lỗi biên dịch của `switch` trước khi thêm `case Paused p`.
- Thử đặt nhánh `case Moved(int x, int y)` trước nhánh `case Moved(int x, int y) when x == 0 && y == 0` và giải thích vì sao nhánh có guard bị che.

**Ghi nhớ:** `instanceof` nhận diện **một kiểu**; `switch` tổ chức **nhiều nhánh so khớp**; `record` mô tả **hình dạng dữ liệu**; record pattern khai thác **các thành phần** của dữ liệu đó. Khi dùng đúng chỗ, chúng làm rõ luồng điều khiển và giảm ép kiểu thủ công, nhưng không thay thế việc thiết kế kiểu dữ liệu và xử lý `null` cẩn thận.

## Tài liệu chuẩn để tra cứu

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
