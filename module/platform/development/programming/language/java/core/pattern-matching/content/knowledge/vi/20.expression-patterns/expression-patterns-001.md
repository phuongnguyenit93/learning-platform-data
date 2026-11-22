# Pattern trong `instanceof` expression (Java)

## 1. Bản chất của pattern matching với `instanceof`

`instanceof` là một **biểu thức Boolean** trong Java. Theo cách truyền thống, nó chỉ hỏi một đối tượng có tương thích với kiểu được nêu hay không:

```java
Object value = "Hello";
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length()); // 5
}
```

Ở đây lập trình viên phải viết lại phép ép kiểu `(String) value` dù nhánh `if` đã xác nhận kiểu. **Pattern matching for `instanceof`** gộp việc **kiểm tra kiểu** và **khai báo biến chứa giá trị đã khớp**:

```java
Object value = "Hello";
if (value instanceof String text) {
    System.out.println(text.length()); // 5
}
```

`String text` là **type pattern**: `String` là kiểu cần kiểm tra, `text` là biến pattern được gán khi phép khớp thành công. Nó không tạo một `String` mới, mà cung cấp tham chiếu đến giá trị gốc dưới kiểu đã được kiểm tra.

- Type patterns trong `instanceof` trở thành tính năng chính thức từ **Java 16** (JEP 394).
- **Record patterns** có dạng `Point(var x, var y)`, cho phép tách các component của một `record`, trở thành tính năng chính thức từ **Java 21** (JEP 440).
- Những ví dụ dùng cả hai loại pattern trong bài này yêu cầu **JDK 21 trở lên**; không cần cờ `--enable-preview`.

Nội dung ở đây tập trung vào **pattern trong biểu thức `instanceof`**. Pattern matching trong `switch` có những quy tắc và cách diễn đạt riêng.

## 2. Đọc một biểu thức `instanceof` có pattern

Dạng cơ bản:

```java
expression instanceof ReferenceType variable
```

Ví dụ:

```java
Object input = "Java";
boolean matches = input instanceof String s;
System.out.println(matches); // true
```

Điều kiện để **type pattern** khớp:

1. Giá trị do `expression` tạo ra **khác `null`**.
2. Giá trị đó tương thích runtime với `ReferenceType` trong pattern, theo phép kiểm tra của `instanceof`.
3. Khi khớp, biến pattern được gán giá trị và khả dụng tại các vị trí mà trình biên dịch bảo đảm pattern đã đúng.

Với `input = 42` hoặc `input = null`, `input instanceof String s` là `false`; biến `s` sẽ không khả dụng ở nhánh phụ thuộc vào kết quả không khớp.

**Không nhầm ba dạng sau:**

| Biểu thức | Ý nghĩa |
| --- | --- |
| `input instanceof String` | Kiểm tra runtime type, không tạo biến pattern. |
| `input instanceof String s` | Type pattern: kiểm tra và ràng buộc toàn bộ giá trị vào `s`. |
| `input instanceof Point(var x, var y)` | Record pattern: kiểm tra `Point` và tách hai component thành `x`, `y`; yêu cầu Java 21+. |

Type pattern không phải cú pháp ép kiểu mới; trình biên dịch đã chứng minh kiểu phù hợp nên ta không cần cast lặp lại trong nhánh đã khớp.

## 3. Phạm vi biến pattern theo luồng điều khiển

Biến được khai báo bởi pattern tuân theo **flow scoping**: tên biến có hiệu lực khi luồng thực thi bảo đảm việc khớp đã thành công. Vì thế không thể suy luận phạm vi chỉ dựa vào dấu ngoặc nhọn.

### 3.1. Trong nhánh `if` đúng

```java
static void printUpper(Object input) {
    if (input instanceof String s) {
        System.out.println(s.toUpperCase());
    }
    // Không dùng s ở đây: input có thể không phải String.
}
```

Biến `s` dùng được trong nhánh `if` đúng. Nhánh `else` không được giả định `s` đã gán vì đó là nhánh pattern thất bại.

### 3.2. Kết hợp `&&` để vừa khớp vừa lọc

```java
static boolean hasPrefix(Object input) {
    return input instanceof String s && s.startsWith("J");
}
```

`&&` đánh giá **ngắn mạch**: vế phải chỉ chạy khi vế trái là `true`. Vì vậy `s` chắc chắn đã được gán khi gọi `s.startsWith(...)`. Một `null` ở `input` khiến vế trái là `false` và không gọi phương thức trên `s`.

Ngược lại, mã sau **không hợp lệ**:

```java
// Ví dụ lỗi biên dịch: s không chắc đã được gán ở vế phải ||.
if (input instanceof String s || s.isEmpty()) {
    System.out.println("matched");
}
```

Vế phải của `||` được đánh giá khi vế trái là `false`, chính là lúc `s` chưa có giá trị. Đừng “sửa” lỗi bằng cách chép tên biến ra ngoài phạm vi được bảo đảm.

### 3.3. Phủ định và guard clause

```java
static int lengthOrZero(Object input) {
    if (!(input instanceof String text)) {
        return 0;
    }
    return text.length();
}
```

Nếu điều kiện phủ định đúng, phương thức kết thúc ngay. Do đó **mọi đường đi tới `return text.length()`** đều đi qua một lần khớp thành công. Java cho phép dùng `text` sau `if` trong trường hợp này.

Nếu nhánh phủ định **không kết thúc**, compiler sẽ không thể bảo đảm biến pattern tồn tại ở mọi đường đi.

### 3.4. Biểu thức điều kiện và vòng lặp

```java
static int safeLength(Object value) {
    return value instanceof String text ? text.length() : 0;
}
```

Trong toán tử điều kiện `?:`, nhánh `text.length()` chỉ chạy khi pattern khớp. Với vòng lặp cũng cần để ý điều kiện:

```java
Object value = "abcd";
while (value instanceof String s && !s.isEmpty()) {
    System.out.println(s);
    value = null; // Để ví dụ thoát vòng lặp sau một lượt.
}
```

Trong thân vòng lặp, `s` hợp lệ vì điều kiện có pattern đã khớp. Vòng lặp dừng khi `value` được gán `null`.

## 4. Record pattern trong `instanceof`: kiểm tra và tách cấu trúc

Một record có các thành phần cố định:

```java
record Sensor(int temperature, String location) {}
```

Nếu chỉ cần đối tượng nguyên vẹn, dùng type pattern:

```java
if (value instanceof Sensor sensor) {
    System.out.println(sensor.temperature());
}
```

Nếu cần các component ngay tại chỗ, dùng record pattern:

```java
if (value instanceof Sensor(var temperature, var location)) {
    System.out.println(temperature + " @ " + location);
}
```

Ở đây:

- `Sensor(...)` kiểm tra runtime value có khớp record `Sensor` hay không và thực hiện phép tách component.
- `var temperature` và `var location` là các pattern con; kiểu tĩnh được suy luận lần lượt là `int` và `String`.
- Các pattern con phải tương ứng **đủ số lượng, đúng thứ tự và tương thích kiểu** với các component do record khai báo. `Sensor(var temperature)` là lỗi biên dịch vì thiếu pattern cho `location`.
- Record pattern sử dụng accessor record để lấy giá trị component; nó không gọi constructor để tạo một record mới.
- Một component kiểu tham chiếu được bắt bằng `var` có thể nhận `null`. Bản thân record pattern ở tầng ngoài không khớp nếu đối tượng mang record tại tầng đó là `null`.

Khi record có record con, có thể lồng pattern:

```java
record Coordinates(int x, int y) {}
record Reading(String id, Coordinates coordinates) {}

Object item = new Reading("R-1", new Coordinates(2, 3));

if (item instanceof Reading(var id, Coordinates(var x, var y))) {
    System.out.println(id + " => " + (x + y)); // R-1 => 5
}
```

Nếu `coordinates == null`, pattern con `Coordinates(...)` không khớp, toàn bộ biểu thức trả về `false`. Còn `Reading(var id, var coordinates)` có thể khớp và ràng buộc `coordinates = null`. Phải phân biệt **kiểu pattern con** với điều kiện xác thực dữ liệu nghiệp vụ.

## 5. Ví dụ hoàn chỉnh, chạy và kiểm tra đầu ra

Tạo file **`InstanceofPatternsDemo.java`**:

```java
public class InstanceofPatternsDemo {
    record Sensor(int temperature, String location) {}

    static String classify(Object value) {
        // Type pattern String + điều kiện ngắn mạch.
        if (value instanceof String s && !s.isBlank()) {
            return "text:" + s.toUpperCase();
        }

        // Type pattern Integer + điều kiện số dương.
        if (value instanceof Integer n && n > 0) {
            return "positive:" + n;
        }

        // Record pattern tách hai component; vẫn phải kiểm tra location null.
        if (value instanceof Sensor(var t, var place) && place != null) {
            return "sensor:" + place + ":" + (t >= 30 ? "hot" : "normal");
        }

        return "other";
    }

    static int lengthOrZero(Object value) {
        if (!(value instanceof String s)) {
            return 0;
        }
        return s.length();
    }

    public static void main(String[] args) {
        System.out.println(classify("java"));
        System.out.println(classify(12));
        System.out.println(classify(new Sensor(32, "LAB")));
        System.out.println(classify(new Sensor(20, null)));
        System.out.println(classify(null));
        System.out.println(classify(-2));
        System.out.println(lengthOrZero("pattern"));
        System.out.println(lengthOrZero(99));
    }
}
```

Biên dịch và chạy bằng **JDK 21+**:

```bash
javac --release 21 InstanceofPatternsDemo.java
java InstanceofPatternsDemo
```

**Đầu ra chính xác**:

```text
text:JAVA
positive:12
sensor:LAB:hot
other
other
other
7
0
```

Giải thích tám ca:

1. `"java"` khớp `String s`, `!s.isBlank()` đúng nên trả `text:JAVA`.
2. `12` được autobox thành `Integer` khi truyền cho `Object`; `n > 0` đúng nên trả `positive:12`.
3. `new Sensor(32, "LAB")` khớp record pattern, `location` khác `null` và `32 >= 30`, nên trả `sensor:LAB:hot`.
4. `new Sensor(20, null)` **vẫn khớp phần record pattern** `Sensor(var t, var place)`, nhưng guard `place != null` là `false` nên trả `other`.
5. `null` không khớp bất kỳ pattern `instanceof` nào trong ví dụ, trả `other`.
6. `-2` là `Integer` nhưng không thỏa điều kiện `n > 0`, trả `other`.
7. `"pattern"` có 7 ký tự, vượt qua guard clause nên trả `7`.
8. `99` không phải `String`, nhánh phủ định kết thúc sớm và trả `0`.

Ví dụ này thể hiện cả **type pattern**, **record pattern**, **flow scoping**, **`&&` đánh giá ngắn mạch**, **phủ định** và **`null`** trong những biểu thức thường gặp. Kết quả đã được kiểm tra bằng JDK 24 với cú pháp Java 21.

## 6. Các lưu ý về kiểu và generic

### 6.1. Loại kiểu có thể viết trong type pattern

`instanceof` kiểm tra kiểu tham chiếu tương thích, không thể viết pattern kiểu nguyên thủy như `value instanceof int n`. Với dữ liệu đóng hộp, kiểm tra wrapper phù hợp:

```java
Object value = Integer.valueOf(10);
if (value instanceof Integer number) {
    System.out.println(number + 1); // 11
}
```

Compiler cũng kiểm tra tính hợp lệ của chuyển đổi tại **compile time**. Không phải mọi cặp kiểu tham chiếu bất kỳ đều được dùng nếu trình biên dịch biết việc khớp là bất khả thi.

### 6.2. Generic type và type erasure

Không thể dùng `instanceof List<String> texts` để kiểm tra một đối tượng kiểu rộng `Object`, vì tham số `String` của generic `List` không thể kiểm tra đầy đủ ở runtime do **type erasure**. Cách an toàn là kiểm tra wildcard, sau đó kiểm tra phần tử:

```java
Object unknown = java.util.List.of("a", "b");

if (unknown instanceof java.util.List<?> items) {
    for (Object element : items) {
        if (element instanceof String text) {
            System.out.println(text.toUpperCase());
        }
    }
}
```

Đây là **đoạn minh họa trong một phương thức hoặc JShell**, chưa phải class Java độc lập. Với dữ liệu mẫu, đầu ra là `A` và `B` trên hai dòng. `List<?>` chỉ cho biết đây là một danh sách có kiểu phần tử chưa xác định; nó **không xác nhận** mọi phần tử đều là `String`.

### 6.3. Một phép `instanceof` không thay thế validation

`value instanceof String s` xác nhận runtime type; nó không xác nhận `s` không rỗng, phù hợp định dạng email, hợp lệ theo quy tắc nghiệp vụ hay an toàn để đưa vào SQL. Với record pattern, `var` cũng không tự xác thực mọi component. Cần bổ sung guard, như `&& !s.isBlank()`, hoặc logic kiểm tra riêng.

### 6.4. Pattern variable và tên đã khai báo

Pattern variable là một khai báo biến thực sự và phải tuân theo các quy tắc trùng tên trong phạm vi áp dụng. Nếu đã có biến cục bộ tên `text` trong cùng phạm vi, việc khai báo thêm `String text` có thể gây lỗi. Hãy dùng tên phản ánh vai trò mới và chỉ tham chiếu biến trên đường đi pattern đã khớp.

## 7. So sánh code trước và sau khi dùng type pattern

**Trước Java 16**, khi một giá trị khai báo là `Object` cần đọc dưới dạng `String`:

```java
static String labelOld(Object input) {
    if (input instanceof String) {
        String text = (String) input;
        return "name:" + text;
    }
    return "unknown";
}
```

**Với type pattern**:

```java
static String labelNew(Object input) {
    if (input instanceof String text) {
        return "name:" + text;
    }
    return "unknown";
}
```

Hai phương thức minh họa này có cùng ý nghĩa kiểm tra kiểu và tạo chuỗi. Phiên bản mới loại bỏ cast trùng lặp và không cần định nghĩa một biến trung gian tách biệt. Đây là những **phương thức phải đặt bên trong class Java**, không phải chương trình độc lập.

Khi muốn lấy nhiều component của một record, Java 21 còn cho phép bỏ các lời gọi accessor:

```java
// Cách dùng type pattern:
if (value instanceof Sensor sensor) {
    System.out.println(sensor.temperature() + " @ " + sensor.location());
}

// Cách dùng record pattern:
if (value instanceof Sensor(var t, var location)) {
    System.out.println(t + " @ " + location);
}
```

Cả hai cách đều hữu ích: type pattern phù hợp khi muốn giữ cả đối tượng, còn record pattern phù hợp khi cần ngay các component. Nếu sau đó phải tạo DTO mới hoặc chuẩn hóa dữ liệu, bước mapping vẫn phải thực hiện riêng.

## 8. Lỗi thường gặp

| Lỗi | Vì sao sai / cách sửa |
| --- | --- |
| Dùng `value instanceof String s` rồi truy cập `s` ở mọi nơi | Biến `s` chỉ khả dụng khi dòng điều khiển bảo đảm pattern đã khớp. Dùng trong nhánh đúng hoặc sau guard clause kết thúc sớm. |
| Dùng `|| s.someMethod()` sau type pattern ở vế trái | Vế phải `||` có thể chạy khi pattern không khớp. Thường dùng `&&` nếu điều kiện tiếp theo cần biến pattern. |
| Tin rằng `instanceof` sẽ ném `NullPointerException` với `null` | Kiểm tra một giá trị `null` bằng `instanceof` trả `false`. |
| Tưởng `var` trong record pattern từ chối mọi `null` | `var` có thể ràng buộc component tham chiếu `null`; thêm guard khi cần. |
| Dùng `instanceof` với nguyên thủy `int` | Type pattern `instanceof` trong các ví dụ này dùng kiểu tham chiếu; với dữ liệu được đóng hộp, dùng `Integer`. |
| Đòi kiểm tra `List<String>` qua `instanceof` trên một `Object` | Do type erasure, dùng `List<?>` rồi xác nhận phần tử riêng. |
| Dùng `Point(var x, var y)` trên Java 17 | Record patterns được chuẩn hóa từ Java 21; chọn toolchain JDK 21+ và build target tương ứng. |
| Dùng `R(...)` để tách một class thường | Record pattern yêu cầu kiểu record; dùng type pattern + accessor cho class thường. |
| Nhầm pattern matching với ánh xạ dữ liệu | Pattern kiểm tra và ràng buộc giá trị; không tự chuyển đổi hay tạo DTO đích. |

## 9. Tự luyện và đáp án tham khảo

Cho:

```java
record Result(int code, String message) {}
Object response = new Result(200, "OK");
```

**Bài 1.** Viết một biểu thức `instanceof` dùng record pattern để in thông báo nếu `code == 200` và `message` khác `null`.

Đáp án (đặt trong thân phương thức):

```java
if (response instanceof Result(var code, var message)
        && code == 200
        && message != null) {
    System.out.println(message); // OK
}
```

**Bài 2.** Khi `response = new Result(500, null)`, pattern ở vế trái của `&&` có khớp không? Nhánh `if` chạy không?

Đáp án: bản thân `Result(var code, var message)` **vẫn khớp** vì đối tượng là record `Result` hợp lệ và `var message` có thể nhận `null`. Nhưng `code == 200` sai, nên `&&` kết thúc sớm; nhánh `if` không chạy. Không đánh đồng “record pattern khớp” với “toàn bộ biểu thức Boolean được đánh giá là `true`”.

**Bài 3.** Viết một phương thức nhận `Object`, trả `0` nếu đầu vào không phải `String`; ngược lại trả độ dài chuỗi, sử dụng guard clause và biến pattern phía sau guard.

Đáp án:

```java
static int textLength(Object input) {
    if (!(input instanceof String s)) {
        return 0;
    }
    return s.length();
}
```

**Tài liệu chính thức:**
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Java 21 Language Guide — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof.html)
- [Java 21 Language Guide — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
