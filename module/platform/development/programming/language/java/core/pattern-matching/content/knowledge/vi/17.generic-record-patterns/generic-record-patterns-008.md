# Generic record patterns: Compiler inference và trường hợp cần type rõ ràng

## 1. Mục tiêu và bối cảnh Java

Khi record có tham số kiểu, ví dụ `record Box<T>(T value) {}`, **record pattern** cho phép vừa kiểm tra record vừa tách thành phần. **Compiler inference** là cơ chế trình biên dịch suy luận tham số kiểu của record pattern và kiểu của biến pattern từ **kiểu tĩnh của biểu thức được khớp** và khai báo các component. Ta không phải luôn viết lại `Box<String>` và `String`.

```java
record Box<T>(T value) {}

static void print(Box<String> box) {
    if (box instanceof Box(var text)) {
        // Compiler biết text có kiểu String.
        System.out.println(text.toUpperCase());
    }
}
```

Ở đây `Box(var text)` được suy luận tương đương về mặt kiểu với `Box<String>(String text)` trong ngữ cảnh tham số `box` có kiểu `Box<String>`. Không có lời gọi constructor nào trong pattern. `var` là suy luận **kiểu tĩnh**, không phải kiểu động.

**Phiên bản:** Record (bao gồm generic record) chính thức từ Java 16. Record patterns (JEP 440) chính thức từ **Java 21**; không dùng được cú pháp này với Java 17, và với JDK 21+ không cần `--enable-preview`.

## 2. Hai lớp suy luận: type argument và component variable

Xét khai báo:

```java
record Box<T>(T value) {}
record Pair<A, B>(A first, B second) {}
```

Trong `Box(var x)` có hai việc riêng biệt:

1. **Suy luận type argument `T` của record pattern `Box<T>`** khi `Box` không ghi `<...>`. Kiểu của đối tượng ở vị trí khớp (compile-time target) cung cấp ràng buộc cho `T`.
2. **Suy luận kiểu biến `x`** từ kiểu component `value` sau khi các tham số của record pattern đã được xác định. Nếu `T` là `String`, `x` có kiểu `String`; nếu `T` được suy luận đến `Object`, `x` chỉ có kiểu `Object`.

Cơ chế này áp dụng với `instanceof`, các nhánh `switch` và record patterns lồng nhau. Trong `Pair(var a, var b)`, `A` và `B` có thể được suy luận độc lập từ kiểu của `Pair` đang khớp.

So sánh các ngữ cảnh:

| Kiểu tĩnh của giá trị đầu vào | Record pattern | Kiểu có thể dùng an toàn cho biến |
| --- | --- | --- |
| `Box<String>` | `Box(var x)` | `String` |
| `Box<? extends Number>` | `Box(var x)` | Có thể dùng `x` như `Number` |
| `Pair<String, Integer>` | `Pair(var a, var b)` | `a`: `String`, `b`: `Integer` |
| `Box<Box<String>>` | `Box(Box(var s))` | `s`: `String` |
| `Object` chứa một `Box<String>` lúc chạy | `Box(var x)` | Chỉ bảo đảm `Object`, không tự suy ra `String` |

**Điểm quan trọng:** Compiler nhìn **kiểu tĩnh tại điểm khớp**. Nó không đoán type argument theo nội dung thực tế bên trong đối tượng ở runtime. Ví dụ, khai báo `Object unknown = new Box<>("hello");` không khiến `Box(var x)` suy luận `x` thành `String`. Cần bổ sung một pattern kiểm tra kiểu thành phần nếu muốn xử lý chuỗi an toàn.

## 3. Ví dụ chạy đầy đủ: inferred, explicit, wildcard, nested và switch

Lưu mã thành **`GenericRecordInferenceDemo.java`**:

```java
public class GenericRecordInferenceDemo {
    record Box<T>(T value) {}
    record Pair<A, B>(A first, B second) {}

    static void run() {
        Box<String> textBox = new Box<>("Java");

        // 1. Compiler suy luận Box<String> và text: String.
        if (textBox instanceof Box(var text)) {
            String typed = text; // Không cần cast.
            System.out.println("Inferred: " + typed.toUpperCase());
        }

        // 2. Ghi tường minh type argument và kiểu component.
        if (textBox instanceof Box<String>(String text)) {
            System.out.println("Explicit: " + text.length());
        }

        // 3. Wildcard có upper bound.
        Box<? extends Number> numberBox = new Box<>(42);
        if (numberBox instanceof Box(var number)) {
            Number numeric = number;
            System.out.println("Bounded: " + numeric.intValue());
        }

        // 4. Nested generic record pattern: suy luận qua hai lớp Box.
        Box<Box<String>> nested = new Box<>(new Box<>("inside"));
        if (nested instanceof Box(Box(var innerText))) {
            String typed = innerText;
            System.out.println("Nested: " + typed);
        }

        // 5. Hai tham số kiểu được suy luận riêng.
        Pair<String, Integer> pair = new Pair<>("ok", 3);
        if (pair instanceof Pair(var left, var right)) {
            String label = left;
            Integer count = right;
            System.out.println("Pair: " + label + "/" + count);
        }

        // 6. Khi biểu thức chỉ có kiểu Object, var không tự thành String.
        Object unknown = new Box<>("dynamic");
        if (unknown instanceof Box(var value)) {
            Object general = value;
            System.out.println("General: " + general);
        }

        // 7. Kiểu component tường minh kiểm tra ở runtime.
        if (unknown instanceof Box(String actualString)) {
            System.out.println("Checked: " + actualString.toUpperCase());
        }

        // 8. Record patterns trong switch cũng suy luận kiểu.
        Object mixed = new Box<>(7);
        String kind = switch (mixed) {
            case Box(String s) -> "text=" + s;
            case Box(Integer n) -> "integer=" + n;
            case Box(var any) -> "other=" + any;
            case null -> "null";
            default -> "not-box";
        };
        System.out.println("Switch: " + kind);
    }

    public static void main(String[] args) {
        run();
    }
}
```

Dùng JDK 21 trở lên:

```bash
javac --release 21 GenericRecordInferenceDemo.java
java GenericRecordInferenceDemo
```

Stdout:

```text
Inferred: JAVA
Explicit: 4
Bounded: 42
Nested: inside
Pair: ok/3
General: dynamic
Checked: DYNAMIC
Switch: integer=7
```

Tại phần 6, biến `value` được xử lý như `Object`, mặc dù giá trị thực tế là chuỗi. Phần 7 chuyển sang **kiểm tra component**: `Box(String actualString)` chỉ khớp nếu đối tượng là record `Box` có component tương ứng khớp kiểu `String`; vì thế gọi `toUpperCase()` an toàn trong nhánh đó. Trong `switch`, nhánh `Box(var any)` đặt **sau** các nhánh cụ thể để tránh che khuất chúng. `case null` xử lý selector null, còn `default` xử lý đối tượng không phải `Box`.

## 4. Khi nào nên dựa vào inference?

### Nguồn có generic type rõ ràng

Với `Box<String>`, viết ngắn:

```java
if (textBox instanceof Box(var s)) {
    String text = s;
}
```

Thường đủ rõ và không lặp lại thông tin đã được compiler biết. `String text = s` biên dịch vì `s` là `String`. Khi record có nhiều type arguments, `Pair(var first, var second)` cũng có lợi ích tương tự.

### Generic type lồng nhau

Với `Box<Box<String>>`, hai tầng pattern vẫn có thể suy luận:

```java
if (nested instanceof Box(Box(var s))) {
    String text = s;
}
```

Compiler kết hợp khai báo component `Box<T>` với kiểu tĩnh của `nested` để suy ra component ở tầng trong. Không cần viết dài `Box<Box<String>>(Box<String>(String s))` trong ngữ cảnh đã có đầy đủ thông tin kiểu.

### Wildcard và upper bound

Với `Box<? extends Number>`, chỉ có thể dựa vào các thao tác an toàn theo giới hạn trên:

```java
if (numberBox instanceof Box(var number)) {
    Number n = number;
    System.out.println(n.doubleValue());
}
```

Không được tự mặc định `number` là `Integer` chỉ vì dữ liệu hiện tại dùng `new Box<>(42)`. Một phiên bản khác của chương trình có thể cung cấp `Double` hoặc kiểu con khác của `Number`. Nếu API cần hành vi của `Integer`, phải kiểm tra hẹp hơn.

### Dữ liệu không còn thông tin generic ở kiểu tĩnh

Khi đối tượng được truyền qua tham số `Object`, collection kiểu rộng, hoặc API trả về `Box<?>`, inference không thể khôi phục `String` chỉ từ chuyện đối tượng *thực tế* được tạo bằng `new Box<>("text")`. Hãy giữ generic type trong chữ ký phương thức nếu có thể; nếu cần phân nhánh runtime, kiểm tra kiểu component bằng pattern rõ ràng.

## 5. Khi nào cần viết type rõ ràng?

**“Type rõ ràng” gồm hai quyết định khác nhau:** type argument của record (`Box<String>`) và pattern của component (`String s`). Chúng không có cùng tác dụng.

### Trường hợp A — Tường minh để làm rõ hợp đồng kiểu đã biết

Nếu biến đầu vào chắc chắn có kiểu `Box<String>`, hai cách sau hợp lệ và cho cùng kiểu biến:

```java
if (textBox instanceof Box(var s)) {
    System.out.println(s.length());
}

if (textBox instanceof Box<String>(String s)) {
    System.out.println(s.length());
}
```

Cách tường minh hữu ích khi cần đọc code mà không phải dò ngược kiểu biến đầu vào, hoặc khi tài liệu đang giải thích mối quan hệ giữa type argument và component. Nó **không** tạo thêm kiểm tra runtime rằng generic argument thực sự là `String`: generic type arguments thông thường bị **type erasure**.

### Trường hợp B — Cần kiểm tra kiểu component lúc chạy

Khi tham số là `Object`:

```java
static void process(Object input) {
    if (input instanceof Box(String s)) {
        System.out.println(s.toUpperCase());
    }
}
```

`Box(String s)` cung cấp điều kiện runtime rõ ràng: thành phần record khớp `String` thì mới vào nhánh. Trái lại, `Box(var s)` tại ngữ cảnh `Object` chỉ cho phép xử lý `s` dưới kiểu `Object`.

Tương tự có thể dùng `Box(Integer n)`, `Box(java.util.List<?> list)` hoặc một record pattern lồng nhau có cấu trúc rõ ràng. Các kiểu này kiểm tra **kiểu thực tế của component**; không chứng minh toàn bộ generic type argument của `Box` ở runtime.

### Trường hợp C — Explicit type argument không phải cách ép compiler tin một generic type đã bị xóa

Đoạn sau là **ví dụ lỗi biên dịch**, không phải mã để chạy:

```java
record Box<T>(T value) {}

static void invalid(Object source) {
    // LỖI: Object không thể safely cast sang Box<String>
    // bằng phép kiểm tra không cần unchecked conversion.
    if (source instanceof Box<String>(var s)) {
        System.out.println(s);
    }
}
```

Việc đưa `<String>` vào record pattern không thay thế việc kiểm tra generic type runtime. `source` có thể chứa `Box<Integer>`; JVM không mang đủ type argument để phân biệt hai `Box` bằng `instanceof`. Java vì vậy từ chối pattern generic cần **unchecked conversion**. Lỗi tương tự xảy ra với một biến `Box` dạng raw mà ta thử khớp như `Box<String>(...)`.

Nếu `source` có kiểu tĩnh `Box<String>`, pattern `Box<String>(var s)` hợp lệ; nếu chỉ là `Object` hoặc raw `Box`, thường phải dùng `Box(var s)` hoặc kiểm tra component (`Box(String s)`) thay vì gắn type argument không thể kiểm chứng.

### Trường hợp D — Generic bên trong generic: đừng suy ra kiểu phần tử của collection

Giả sử nhận một `Object` chứa `Box<List<String>>`. Mẫu `Box(java.util.List<?> values)` có thể kiểm tra component là `List` và cho phép duyệt như `List<?>`. Nhưng `List<String>` không thể được bảo đảm chỉ bằng kiểu generic bị xóa. Nếu cần phần tử chuỗi, kiểm tra từng phần tử hoặc giữ chữ ký đầu vào có kiểu `Box<List<String>>` từ đầu.

```java
static void inspectList(Object source) {
    if (source instanceof Box(java.util.List<?> items)) {
        for (Object item : items) {
            if (item instanceof String text) {
                System.out.println(text.toUpperCase());
            }
        }
    }
}
```

Đây là phép kiểm tra `List<?>` và từng phần tử. Code không giả định mọi phần tử đều là `String` chỉ vì một instance cụ thể đang chứa chuỗi.

## 6. Inference, null và phạm vi biến pattern

Suy luận kiểu **không** loại bỏ trách nhiệm xử lý null:

- Giá trị đầu vào `null` không khớp `Box(...)`, vì đối tượng record bên ngoài phải tồn tại.
- Thành phần bên trong record có thể là `null`. `Box(var x)` sử dụng một pattern component không điều kiện với kiểu khai báo tương ứng, nên vẫn có thể khớp record có component null và gán `x = null`.
- Với `Object input` và `Box(String s)`, nếu component đang null thì `String s` không khớp, vì `String` không bao phủ mọi giá trị kiểu `Object`.
- Khi kiểu tĩnh của component vốn đã là `String`, pattern con `String s` có thể là *unconditional* cho component và khớp cả component null. Vì vậy không nên suy luận rằng mọi `String s` trong record pattern đều loại trừ null; hãy xem kiểu tĩnh ở vị trí component.

Ví dụ kiểm chứng sự khác biệt:

```java
Box<String> known = new Box<>(null);
Object unknown = new Box<String>(null);

// true: kiểu component String đã được biết từ Box<String>.
System.out.println(known instanceof Box<String>(String s));

// false: component ở vị trí này được xét từ Object; String là kiểu hẹp hơn.
System.out.println(unknown instanceof Box(String s));

// true: var ở component bao phủ kiểu tương ứng, kể cả null.
System.out.println(unknown instanceof Box(var s));
```

Biến pattern chỉ dùng được tại những vị trí mà compiler chứng minh phép khớp thành công: thân `if` khi điều kiện đúng, nhánh `case` phù hợp và những biểu thức theo luật scope của pattern matching. Không dùng biến `s` bên ngoài phạm vi đó hoặc cố suy ra runtime type khác với static type compiler đã gán.

## 7. Các lỗi thường gặp

1. **Hiểu `var` là kiểu động.** `var` là suy luận kiểu tại compile time. `Object o = new Box<>("abc")` không khiến `Box(var x)` có biến `x` kiểu `String`.
2. **Nhầm type argument và component pattern.** `Box<String>(var x)` dựa vào tính an toàn của phép chuyển kiểu sang `Box<String>`; `Box(String x)` có thể kiểm tra trực tiếp runtime component `String` từ một `Object`.
3. **Dùng parameterized record pattern trong ngữ cảnh cần unchecked cast.** Java cấm ví dụ `Object` hoặc raw `Box` đi với `Box<String>(...)` vì type argument không kiểm chứng được.
4. **Cho rằng generic inference kiểm tra phần tử collection.** `List<String>` là tham số kiểu tĩnh; muốn xác nhận từng phần tử trong dữ liệu không tin cậy, hãy kiểm tra phần tử đó.
5. **Làm mất kiểu quá sớm.** Trả về `Object` thay cho `Box<T>` hoặc `Box<?>` khi không cần thiết khiến các pattern về sau ít thông tin để suy luận hơn.
6. **Quên kiểu biên trên của wildcard.** Với `Box<? extends Number>`, thao tác dựa trên `Number` an toàn; gọi phương thức đặc thù của `Integer` mà chưa kiểm tra sẽ không được bảo đảm.
7. **Đặt nhánh tổng quát trước nhánh cụ thể.** Trong `switch`, `case Box(var any)` nên đứng sau `case Box(String s)`, `case Box(Integer n)` để không chặn các nhánh cần phân loại.
8. **Lẫn generic record pattern với constructor có diamond.** `new Box<>("x")` là tạo đối tượng với diamond inference; `Box(var x)` là khớp và tách đối tượng, inference chịu ràng buộc của vị trí pattern.

## 8. Checklist khi thiết kế pattern

Khi chọn giữa inference và kiểu tường minh, tự kiểm tra:

1. **Kiểu tĩnh của selector/biểu thức là gì?** Nếu đã là `Box<String>` hoặc `Box<Box<String>>`, hãy bắt đầu bằng `Box(var x)` / `Box(Box(var x))`.
2. **Phương thức cần kiểu nào để xử lý?** Nếu cần `String` nhưng compiler chỉ biết `Object`, thêm pattern component `String s` hoặc kiểm tra `instanceof String`.
3. **Có unchecked conversion không?** Đừng thêm `<String>` vào generic record pattern trên đối tượng chưa được chứng minh generic type bằng hệ kiểu.
4. **Có wildcard, null hay nhiều nhánh `switch` không?** Chỉ dùng khả năng mà kiểu tĩnh bảo đảm, xử lý null theo từng tầng và đặt nhánh cụ thể trước nhánh tổng quát.
5. **Có thể giữ generic information từ API upstream không?** Chữ ký `Box<T>` rõ ràng thường giúp code pattern phía sau an toàn và dễ đọc hơn nhiều so với ép kiểu thủ công.

**Kết luận:** Với generic record patterns, compiler thường suy ra cả type arguments và các biến thành phần dựa trên **kiểu tĩnh ở vị trí khớp**. Hãy tận dụng `var` khi thông tin kiểu đã đủ; dùng pattern component tường minh để thu hẹp kiểu runtime, và chỉ ghi type arguments tường minh khi phép kiểm tra vẫn hợp lệ, không cần unchecked conversion.

### Tài liệu tham khảo

- Oracle Java 21 — Record Patterns (Generic Records, Type Inference, Nested Record Patterns): https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- JEP 440 — Record Patterns (final in JDK 21): https://openjdk.org/jeps/440
- Java Language Specification — Record Pattern Type Inference (`18.5.5): https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html
