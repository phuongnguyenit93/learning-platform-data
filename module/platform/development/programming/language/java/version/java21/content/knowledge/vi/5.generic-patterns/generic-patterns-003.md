# Suy luận type argument từ kiểu của selector hoặc biểu thức instanceof

Java 21 hoàn thiện Record Patterns qua JEP 440. Một tiện ích quan trọng là compiler có thể suy luận type argument khi ta viết record pattern cho một record generic mà bỏ phần `<...>`. Kiểu tĩnh của biểu thức đang được xét cung cấp thông tin để xác định kiểu component bên trong pattern.

Điều này giúp pattern ngắn gọn hơn mà vẫn giữ được kiểu dữ liệu cụ thể khi compiler có đủ thông tin. Cần phân biệt đây là suy luận kiểu tại thời điểm biên dịch; JVM không kiểm tra type argument generic thực tế của object lúc chạy.

## 1. Record generic và record pattern

Giả sử khai báo một record generic:

```java
record Box<T>(T value) {}
```

`Box<T>` có một component `value` mang kiểu `T`. Khi viết record pattern, ta có thể chỉ rõ type argument:

```java
case Box<String>(var value) -> ...
```

Hoặc bỏ type argument để compiler suy luận:

```java
case Box(var value) -> ...
```

Khi type argument được suy luận là `String`, biến pattern `value` cũng có kiểu `String`. Ta có thể gọi trực tiếp các phương thức của `String` mà không cần ép kiểu.

## 2. Suy luận từ kiểu của switch selector

Với pattern trong `switch`, compiler dùng kiểu tĩnh của selector để suy luận type argument cho record pattern. Ví dụ:

```java
record Box<T>(T value) {}

static void printBox(Box<String> box) {
    switch (box) {
        case Box(var value) -> {
            // value có kiểu String
            System.out.println(value.toUpperCase());
        }
    }
}
```

Selector `box` có kiểu tĩnh `Box<String>`, vì vậy `Box(var value)` được hiểu với type argument `String`. Component pattern `var value` nhận kiểu component sau khi thay `T` bằng `String`.

Có thể viết đầy đủ `Box<String>(var value)` để thể hiện tường minh, nhưng thường không cần thiết khi kiểu selector đã cung cấp đủ thông tin.

## 3. Suy luận từ biểu thức instanceof

Record pattern cũng có thể xuất hiện trong biểu thức `instanceof`. Khi bỏ type argument, compiler suy luận từ kiểu tĩnh của biểu thức ở bên trái `instanceof`.

```java
record Box<T>(T value) {}

static void inspect(Object candidate) {
    if (candidate instanceof Box(var value)) {
        // candidate có kiểu tĩnh Object nên value có kiểu Object
        Object data = value;
        System.out.println(data);
    }
}
```

Trong ví dụ này, biến `candidate` chỉ được khai báo với kiểu `Object`. Compiler không biết rằng object thực tế có thể được tạo từ `new Box<String>(...)`, vì vậy component pattern chỉ có thể sử dụng kiểu tổng quát `Object`.

Khi biểu thức có kiểu generic cụ thể hơn, thông tin đó được dùng trong quá trình suy luận. Ví dụ dưới đây kiểm tra component có phải `Integer` hay không:

```java
record Box<T>(T value) {}

static void inspectNumber(Box<Number> candidate) {
    if (candidate instanceof Box(Integer value)) {
        // Type argument của Box được suy luận là Number.
        // Component pattern Integer chỉ khớp khi value là Integer.
        System.out.println(value.intValue());
    }
}
```

Kiểu tĩnh của `candidate` là `Box<Number>`, nên type argument của record pattern được suy luận là `Number`. Pattern thành phần `Integer value` là một điều kiện hẹp hơn: nó chỉ khớp khi giá trị component thực tế là một `Integer`. Nếu component là một kiểu `Number` khác, chẳng hạn `Double`, điều kiện không khớp.

## 4. Suy luận trong record pattern lồng nhau

Compiler có thể truyền thông tin kiểu qua nhiều cấp record pattern. Khi type argument của record bên ngoài được suy luận, kiểu component của nó cũng được xác định; record pattern bên trong tiếp tục suy luận từ kiểu component đó.

```java
record Box<T>(T value) {}
record Envelope<T>(Box<T> payload) {}

static void inspect(Envelope<String> envelope) {
    switch (envelope) {
        case Envelope(Box(var text)) -> {
            // envelope được suy luận là Envelope<String>
            // payload được suy luận là Box<String>
            // text có kiểu String
            System.out.println(text.toUpperCase());
        }
    }
}
```

Không cần viết `Envelope<String>(Box<String>(var text))`. Kiểu tĩnh của selector `Envelope<String>` cung cấp thông tin để suy luận lần lượt cho cả pattern ngoài và pattern trong.

## 5. Kiểu tĩnh quyết định mức độ suy luận

Suy luận dựa trên kiểu mà compiler nhìn thấy trong mã nguồn, không dựa trên kiểu generic mà lập trình viên biết object đã được tạo ra lúc chạy.

| Kiểu tĩnh của biểu thức | Kiểu component có thể suy luận |
|---|---|
| `Box<String>` | `String` |
| `Box<Number>` | `Number` |
| `Box<?>` | Kiểu capture của wildcard; không thể mặc định coi là `String` |
| `Box` raw type | Thông tin generic đã mất; component thường được xử lý như `Object` |
| `Object` | `Object` theo giới hạn thông tin của selector |

Ví dụ, nếu một giá trị `Box<String>` được gán vào biến `Object`, thông tin `String` không còn nằm trong kiểu tĩnh của biến đó:

```java
Box<String> typed = new Box<>("Java");
Object unknown = typed;

if (unknown instanceof Box(var value)) {
    // value có kiểu Object, không phải String
    System.out.println(value);
}
```

Nếu chương trình cần thao tác với một kiểu cụ thể, hãy giữ thông tin kiểu ở biến hoặc API đầu vào, hoặc kiểm tra kiểu của component bằng một pattern thành phần phù hợp. Không giả định compiler có thể khôi phục type argument đã mất khi biểu thức chỉ còn kiểu `Object` hoặc raw type.

## 6. Suy luận kiểu không phải kiểm tra generic ở runtime

Java sử dụng type erasure cho generics. Khi chạy, `Box<String>` và `Box<Integer>` đều có class runtime là `Box`; JVM không lưu type argument `String` hoặc `Integer` để `instanceof` kiểm tra.

Record pattern với type argument được suy luận vẫn tuân theo giới hạn đó:

- Compiler suy luận kiểu component dựa trên kiểu tĩnh và kiểm tra tính tương thích của pattern tại thời điểm biên dịch.
- Khi chạy, pattern nhận diện record class và lấy component thông qua accessor được sinh cho record.
- Không thể dùng record pattern để xác nhận một object thực sự chứa `String` chỉ vì viết hoặc suy luận được `Box<String>` ở mã nguồn.
- Nếu dữ liệu đi vào từ raw type, reflection, serialization hoặc code có heap pollution, cần xác thực component theo kiểu thực tế trước khi sử dụng như dữ liệu tin cậy.

Ví dụ với selector kiểu `Object`, có thể kiểm tra kiểu component trực tiếp:

```java
record Box<T>(T value) {}

static void printText(Object candidate) {
    if (candidate instanceof Box(String text)) {
        // Chỉ vào nhánh này nếu component là String.
        System.out.println(text.toUpperCase());
    }
}
```

Ở đây pattern thành phần `String text` thực hiện kiểm tra kiểu của giá trị component. Điều kiện đó khác với việc JVM kiểm tra type argument generic của `Box`.

## 7. Các điểm cần chú ý

- **Dùng `var` khi kiểu component đã rõ:** trong `Box<String>` hoặc `Envelope<String>`, `var` nhận kiểu đã được suy luận và giúp pattern gọn hơn.
- **Dùng type pattern cụ thể khi cần lọc dữ liệu:** `Box(Integer value)` kiểm tra component là `Integer`, kể cả khi type argument suy luận của record là `Number` hoặc một kiểu tham chiếu rộng hơn tương thích.
- **Đừng nhầm kiểu tĩnh với kiểu object lúc chạy:** biến khai báo là `Object` không mang theo thông tin `Box<String>` chỉ vì object được tạo từ kiểu đó.
- **Cẩn thận với wildcard và raw type:** wildcard có thể tạo kiểu capture; raw type làm mất thông tin generic. Không tự ép các trường hợp này thành một kiểu component cụ thể.
- **Xử lý `null` đúng ngữ cảnh:** `instanceof` trả về `false` khi biểu thức bên trái là `null`. Với `switch`, selector `null` không khớp record pattern và sẽ gây `NullPointerException` nếu không có nhánh `case null` phù hợp.
- **Không thêm `--enable-preview`:** Record Patterns đã là tính năng hoàn thiện trong Java 21 qua JEP 440.

## 8. Khi nào nên sử dụng?

Kiểu suy luận này đặc biệt hữu ích khi mô hình dữ liệu dùng record generic như `Box<T>`, `Result<T>`, `Page<T>`, `Envelope<T>` hoặc các record lồng nhau. Nó giảm phần type argument lặp lại mà vẫn giữ kiểu component trong phạm vi pattern.

| Tình huống | Cách viết phù hợp |
|---|---|
| Selector có kiểu `Box<String>` | `case Box(var value)` để `value` là `String` |
| Selector có kiểu `Envelope<String>` và component là `Box<String>` | `case Envelope(Box(var value))` để `value` là `String` |
| Biểu thức `instanceof` có kiểu `Object` | `instanceof Box(var value)`; xử lý `value` như `Object` |
| Component có thể là một trong nhiều kiểu con | Dùng pattern thành phần như `Box(Integer value)` để lọc kiểu cụ thể |

## 9. Biên dịch với Java 21

Record Patterns và type argument inference cho record patterns đã được hoàn thiện trong Java 21. Có thể biên dịch mã nguồn với release 21 mà không bật Preview:

```bash
javac --release 21 -d out src/GenericRecordPatternDemo.java
java -cp out GenericRecordPatternDemo
```

Không dùng `--enable-preview` cho các ví dụ trong bài. Nếu dự án dùng Maven hoặc Gradle, cấu hình compiler release/toolchain là 21 để bảo đảm cú pháp và API được kiểm tra theo đúng phiên bản.

## 10. Tài liệu tham khảo

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Java Language Specification, Java SE 21 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Java Language Specification, Java SE 21 — Type Inference](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html)
- [Oracle — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Java SE 21 API — java.lang.Record](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Record.html)
