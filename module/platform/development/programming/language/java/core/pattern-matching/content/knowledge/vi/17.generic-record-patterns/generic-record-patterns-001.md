# Record pattern với generic record trong Java

**Generic record** là `record` có tham số kiểu, ví dụ `Box<T>` hoặc `Pair<K, V>`. **Record pattern** cho phép kiểm tra một đối tượng có thuộc kiểu record phù hợp hay không, đồng thời phân rã các component thành những biến có thể sử dụng ngay. Khi kết hợp hai tính năng, Java vừa bảo toàn kiểm tra kiểu tại thời điểm biên dịch, vừa suy luận được kiểu component dựa trên kiểu generic của record.

Bài này tập trung vào **cách viết record pattern cho generic record**, sự suy luận tham số kiểu, record pattern lồng nhau, xử lý dữ liệu chưa biết kiểu và giới hạn do **type erasure**. Các ví dụ chạy trên **Java 21 trở lên**; record patterns được hoàn thiện trong JEP 440 của Java 21 nên không cần bật preview.

## 1. Generic record và record pattern có vai trò gì?

Khai báo một generic record:

```java
record Box<T>(T value) {}
record Pair<K, V>(K key, V value) {}
```

- `Box<T>` có một component `value`, với kiểu được xác định bởi tham số `T`.
- `Pair<K, V>` có hai component `key` và `value`, lần lượt sử dụng `K` và `V`.
- Trong `Box<String>`, kiểu của component `value` là `String` ở cấp mã nguồn. Trong `Pair<String, Integer>`, kiểu `key` là `String` và kiểu `value` là `Integer`.
- Record vẫn là lớp có kiểu thực; các thành phần của nó được truy cập qua accessor như `value()`, `key()`. Record pattern cung cấp cách lấy các giá trị đó mà không phải gọi accessor trực tiếp trong mỗi nhánh xử lý.

Ví dụ không dùng record pattern:

```java
// Giả sử 'box' đã được khai báo là Box<String>.
if (box != null) {
    String text = box.value();
    System.out.println(text);
}
```

Tương đương về mục đích trích component với record pattern:

```java
// Giả sử 'box' đã được khai báo là Box<String>.
if (box instanceof Box(var text)) {
    System.out.println(text);
}
```

`Box(var text)` có phần `Box` là kiểu record, còn `var text` là component pattern. Nó khai báo biến `text` từ component `value`. Đây là kiểm tra khớp pattern, nên khi `box == null` thì nhánh `if` không chạy.

## 2. Ghi tham số kiểu tường minh trong record pattern

Khi biểu thức cần so khớp đã có kiểu `Box<String>`, có thể viết đầy đủ:

```java
// 'box' có kiểu tĩnh Box<String>.
if (box instanceof Box<String>(String text)) {
    System.out.println(text.toUpperCase());
}
```

Trong `Box<String>(String text)`:

1. `Box<String>` xác định generic record với tham số kiểu `String`.
2. `String text` là component pattern, kiểm tra giá trị component theo kiểu `String` và ràng buộc biến `text`.
3. Sau khi khớp, compiler biết `text` có kiểu `String` nên gọi `toUpperCase()` hợp lệ.

Cú pháp khai báo generic record **khác** cú pháp record pattern: `new Box<>("Java")` là tạo đối tượng, còn `Box<String>(String text)` là kiểm tra và phân rã đối tượng đã có.

Lưu ý về component `null`: một component pattern kiểu `String text` không khớp giá trị `null`. Nếu muốn nhận cả `null`, có thể dùng `var text`, sau đó tự xử lý khả năng `text == null`.

## 3. Suy luận tham số kiểu: `Box(var text)`

Java 21 cho phép compiler **suy luận tham số kiểu của generic record pattern** từ kiểu tĩnh của biểu thức đang được khớp.

```java
// Trích đoạn minh họa; 'box' có kiểu Box<String>.
if (box instanceof Box(var text)) {
    // Compiler suy ra text là String.
    System.out.println(text.toUpperCase());
}
```

Ở đây `Box(var text)` có tác dụng tương đương `Box<String>(String text)` trong ngữ cảnh này. Không cần lặp lại `<String>` trong pattern; compiler đã biết kiểu từ `Box<String>`.

Với `Pair<K, V>` cũng tương tự:

```java
// 'pair' có kiểu Pair<String, Integer>.
if (pair instanceof Pair(var key, var count)) {
    String label = key;   // Hợp lệ: key được suy ra là String.
    Integer total = count; // Hợp lệ: count được suy ra là Integer.
    System.out.println(label + ": " + total);
}
```

Tuy nhiên, **`var` không tự kiểm tra rằng giá trị là `String` hay `Integer`** nếu đầu vào chỉ có kiểu `Object`. `var` lấy kiểu mà compiler suy ra từ ngữ cảnh. Kiểu của biểu thức đầu vào càng ít thông tin generic, kiểu suy ra cho component càng tổng quát; không thể gọi phương thức dành riêng cho `String` nếu compiler chỉ biết biến là `Object`.

## 4. Record pattern lồng nhau với generic record

Một generic record có thể chứa một generic record khác:

```java
record Box<T>(T value) {}
record Envelope<T>(String label, Box<T> box) {}
```

Khi có `Envelope<String>`, compiler biết component `box` có kiểu `Box<String>`. Ta có thể phân rã hai cấp bằng:

```java
// 'envelope' có kiểu Envelope<String>.
if (envelope instanceof Envelope(var label, Box(var message))) {
    // Compiler suy luận label là String và message là String.
    System.out.println(label + ": " + message.toUpperCase());
}
```

Đọc từ ngoài vào trong:

- `Envelope(var label, ...)` lấy component `label`.
- `Box(var message)` kiểm tra component `box` có phải là một đối tượng `Box` phù hợp không và lấy `value`.
- Vì kiểu tĩnh đầu vào là `Envelope<String>`, hai cấp suy luận dẫn đến `message` có kiểu `String`.
- Nếu `envelope` là `null`, hoặc `envelope.box()` là `null`, toàn bộ record pattern lồng nhau không khớp. Một `Box` tồn tại nhưng có `value == null` vẫn có thể khớp `Box(var message)`, khi đó `message == null` và cần kiểm tra trước khi gọi phương thức trên nó.

Record pattern có thể kết hợp với `instanceof`, `switch` statement và `switch` expression. Dù lồng bao nhiêu cấp, số lượng component pattern ở mỗi cấp phải khớp số component được khai báo trong record tại cấp đó.

## 5. Khi dữ liệu đầu vào là `Object`: wildcard và kiểm tra component

**Generics trong Java dùng type erasure**: tham số `T` trong `Box<T>` không được lưu như một nhãn kiểu có thể kiểm tra trực tiếp cho từng đối tượng tại runtime. Vì vậy, với biến có kiểu tĩnh `Object`, không được tùy tiện viết:

```java
// MÃ KHÔNG BIÊN DỊCH — ví dụ về kiểu chuyển đổi không an toàn.
Object input = new Box<>("Hello");
if (input instanceof Box<String>(var text)) {
    System.out.println(text);
}
```

Nguyên nhân: kiểm tra `Box<String>` từ một `Object` sẽ cần **unchecked conversion**; runtime không thể xác thực riêng tham số `<String>` của `Box`.

Cách an toàn là khớp record với wildcard `<?>` và kiểm tra trực tiếp **giá trị component**:

```java
// Trích đoạn hợp lệ trong Java 21+.
Object input = new Box<>("Hello");

if (input instanceof Box<?>(String text)) {
    System.out.println(text.toUpperCase());
}
```

`Box<?>(String text)` kiểm tra record `Box` rồi kiểm tra giá trị component có phải `String` khác `null` không. Đây **không phải bằng chứng** đối tượng ban đầu có tham số kiểu được khai báo chính xác là `Box<String>`. Chẳng hạn một `Box<CharSequence>` chứa đối tượng `String` cũng có thể khớp pattern này.

Nếu muốn đọc component mà chưa biết kiểu:

```java
// Trích đoạn hợp lệ trong Java 21+.
if (input instanceof Box<?>(var value)) {
    System.out.println(value);
}
```

Ở đây không nên giả định `value` là `String`. Có thể kiểm tra tiếp bằng `value instanceof String s` hoặc dùng nhánh pattern cụ thể.

Bảng so sánh:

| Biểu thức đầu vào (kiểu tĩnh) | Pattern | Đánh giá |
| --- | --- | --- |
| `Box<String>` | `Box<String>(String s)` | Hợp lệ; tham số kiểu đã biết ở compile time |
| `Box<String>` | `Box(var s)` | Hợp lệ; suy luận `s` là `String` |
| `Pair<String, Integer>` | `Pair(var key, var n)` | Hợp lệ; suy luận `String` và `Integer` |
| `Object` | `Box<String>(var s)` | Không hợp lệ do yêu cầu unchecked conversion |
| `Object` | `Box<?>(String s)` | Hợp lệ; kiểm tra giá trị component là `String` |
| `Object` | `Box<?>(var v)` | Hợp lệ; `v` được xử lý theo kiểu an toàn mà compiler suy ra |

## 6. Ví dụ hoàn chỉnh, chạy được trên Java 21+

Tạo tệp **`GenericRecordPatternsDemo.java`**:

```java
public class GenericRecordPatternsDemo {
    record Box<T>(T value) {}
    record Pair<K, V>(K key, V value) {}
    record Envelope<T>(String label, Box<T> box) {}

    static String knownBox(Box<String> box) {
        if (box instanceof Box(var text)) {
            return text.toUpperCase();
        }
        return "null box";
    }

    static String nested(Envelope<String> envelope) {
        if (envelope instanceof Envelope(var label, Box(var message))) {
            return label + ": " + message.toUpperCase();
        }
        return "no nested box";
    }

    static String inspect(Object obj) {
        if (obj instanceof Box<?>(String text)) {
            return "String: " + text;
        }
        if (obj instanceof Box<?>(var value)) {
            return "Other: " + value;
        }
        return "Not a box";
    }

    static String pair(Pair<String, Integer> pair) {
        return switch (pair) {
            case Pair(var key, var number)
                    when number != null && number > 0 -> key + "=" + number;
            case Pair(var key, var number) ->
                    key + "=nonpositive (" + number + ")";
        };
    }

    public static void main(String[] args) {
        System.out.println(knownBox(new Box<>("java")));
        System.out.println(nested(
                new Envelope<>("email", new Box<>("hello"))));
        System.out.println(nested(
                new Envelope<>("sms", null)));
        System.out.println(inspect(new Box<>("hello")));
        System.out.println(inspect(new Box<>(42)));
        System.out.println(inspect(new Box<>(null)));
        System.out.println(inspect("other"));
        System.out.println(pair(new Pair<>("tasks", 5)));
        System.out.println(pair(new Pair<>("tasks", 0)));
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên**:

```bash
javac GenericRecordPatternsDemo.java
java GenericRecordPatternsDemo
```

Kết quả:

```text
JAVA
email: HELLO
no nested box
String: hello
Other: 42
Other: null
Not a box
tasks=5
tasks=nonpositive (0)
```

Giải thích:

1. `knownBox` nhận `Box<String>` nên `Box(var text)` suy luận đúng kiểu `String`; `toUpperCase()` hoạt động.
2. `nested` phân rã hai generic record qua `Envelope(var label, Box(var message))`. Với `Envelope("sms", null)`, component `box` không khớp record pattern `Box(...)` nên trả về `"no nested box"`.
3. `inspect` nhận `Object`: nhánh `Box<?>(String text)` chỉ nhận component là `String` khác `null`. Nhánh tiếp theo `Box<?>(var value)` nhận `Integer` và cả `null`. Chuỗi `"other"` không phải một `Box`.
4. `pair` dùng record pattern trong `switch` expression. Biến `number` được suy luận là `Integer`, điều kiện `number != null` tránh lỗi tự mở hộp `null` khi so sánh với `0`. Nhánh thứ hai xử lý giá trị không dương hoặc `null`.

Trong chương trình thực tế, nếu `knownBox` hoặc `nested` nhận được component giá trị `null` thì lời gọi `toUpperCase()` có thể gây `NullPointerException`. Record pattern trích được component không mặc nhiên bảo đảm component khác `null`.

## 7. Giới hạn quan trọng: type erasure, `null`, kiểu nguyên thủy và tính đầy đủ của `switch`

### Type erasure không biến mất

`Box<String>` và `Box<Integer>` cùng có raw class `Box` tại runtime. Vì thế:

- Không thể dùng record pattern để phân biệt **tham số generic** `String` với `Integer` bằng một unchecked test từ `Object`.
- Có thể kiểm tra **giá trị component** tại runtime, như `Box<?>(String s)` hoặc `Box<?>(Integer n)`.
- Nếu `T` là kiểu giao diện hay lớp cha, giá trị component có thể thuộc một subtype; một pattern trên subtype có thể khớp mà không chứng minh được tham số generic khi record được tạo.
- Tránh dùng raw type `Box` để né kiểm tra kiểu; raw type khiến mất bảo đảm generic và có thể sinh unchecked warnings. Ưu tiên `Box<?>` khi chưa biết kiểu.

### `null` có hai vị trí khác nhau

- `null` là chính **đối tượng record**: bất kỳ record pattern `Box(...)` nào cũng không khớp.
- `null` là **giá trị component**: `Box<?>(var value)` vẫn khớp nếu đối tượng `Box` tồn tại; `value` bằng `null`. Trong khi đó, `Box<?>(String s)` không khớp component `null` vì không thỏa type pattern `String`.

Đặc biệt, `switch` với selector `null` cần một nhánh `case null` nếu muốn xử lý mà không ném ngoại lệ. `switch` expression còn phải thỏa kiểm tra exhaustiveness của compiler; record pattern lồng nhau có thể không bao phủ component record bị `null` và vì thế có thể cần nhánh bổ sung hoặc `default`.

### `T` là kiểu tham chiếu

Generic type argument phải là kiểu tham chiếu: viết `Box<Integer>` thay cho `Box<int>`. Bản thân record có thể khai báo component nguyên thủy ngoài generic, ví dụ:

```java
record Labeled<T>(T label, int score) {}

// Trích đoạn: 'item' có kiểu Labeled<String>.
if (item instanceof Labeled(var name, var score)) {
    System.out.println(name + ": " + score); // name: String; score: int.
}
```

## 8. Lỗi phổ biến khi viết generic record pattern

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Viết `Box<String>(var x)` khi đầu vào có kiểu `Object` | Compile error do unchecked conversion | Dùng `Box<?>(String x)` để kiểm tra component hoặc giữ thông tin kiểu từ sớm |
| Cho rằng `Box(var x)` luôn suy ra `x` là `String` | Không đúng nếu đầu vào thiếu thông tin generic | Kiểm tra kiểu tĩnh của đầu vào; dùng type pattern khi cần |
| Nghĩ `Box<?>(String x)` chứng minh tham số `T` là `String` | Nhầm kiểm tra giá trị runtime với kiểu generic compile time | Chỉ khẳng định component hiện tại là `String` |
| Gọi `x.toUpperCase()` sau `Box(var x)` mà không xử lý `null` | Có thể gây `NullPointerException` | Kiểm tra `x != null` hoặc dùng kiểu component phù hợp |
| Viết `Pair(var key)` cho record có hai component | Số component pattern không khớp | Viết đủ `Pair(var key, var value)` |
| Dùng `Box<int>` | Java generics không nhận kiểu nguyên thủy | Dùng `Box<Integer>` |
| Lạm dụng raw type và unchecked casts | Mất an toàn kiểu và có thể gây lỗi về sau | Dùng type arguments hoặc wildcard có chủ đích |

## 9. Bài tập tự kiểm tra

Cho hai record:

```java
record Result<T>(String status, T payload) {}
record Batch<T>(Result<T> first, Result<T> second) {}
```

**Bài 1.** Biến `Result<Integer> r`, hãy trích `status` và `payload` mà không lặp `<Integer>` trong pattern. Compiler suy ra kiểu gì?

**Đáp án:** `if (r instanceof Result(var status, var payload)) { ... }`. Biến `status` có kiểu `String`, `payload` có kiểu `Integer`.

**Bài 2.** Biến `Batch<String> batch`, hãy trích nội dung của `first.payload` bằng record pattern lồng nhau.

**Đáp án:**

```java
// Trích đoạn minh họa; 'batch' có kiểu Batch<String>.
if (batch instanceof Batch(Result(var status, var payload), var second)) {
    System.out.println(status + ": " + payload);
}
```

`payload` được suy ra là `String`. Nếu `batch` hoặc `first` là `null` thì pattern lồng nhau không khớp. `second` có kiểu `Result<String>` (và có thể `null`).

**Bài 3.** Từ `Object input`, có thể viết `input instanceof Result<String>(var status, var value)` để kiểm tra payload là `String` không?

**Đáp án:** Không; đó là phép kiểm tra tham số generic cần unchecked conversion. Hãy dùng `Result<?>(var status, String value)` để kiểm tra giá trị component `payload` có phải `String` khác `null` hay không.

## 10. Ghi nhớ

- Generic record pattern kết hợp **record deconstruction** với **generic type information**. Ví dụ `Box(var value)` có thể suy luận kiểu component từ `Box<String>`.
- Có thể ghi tường minh tham số kiểu (`Box<String>(String text)`) hoặc bỏ tham số kiểu cho compiler suy luận (`Box(var text)`).
- Với dữ liệu chỉ có kiểu `Object`, sử dụng wildcard và kiểm tra component như `Box<?>(String text)`; không kiểm tra trực tiếp `Box<String>` bằng unchecked pattern.
- Pattern lồng nhau như `Envelope(var label, Box(var message))` vẫn suy luận kiểu qua nhiều cấp và vẫn phải tuân theo quy tắc khớp với `null`.
- Record patterns ổn định từ **Java 21** (JEP 440); pattern matching for `switch` cũng ổn định từ Java 21 (JEP 441).

Tài liệu chính thức: [Oracle — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
