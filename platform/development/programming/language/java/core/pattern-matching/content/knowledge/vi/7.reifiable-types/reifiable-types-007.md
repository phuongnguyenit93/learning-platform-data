# Kết hợp generic record với record pattern

**Chủ đề:** Java Core Pattern Matching → Generic và reifiable types  
**Phiên bản thực hành:** Java 21 trở lên. Record patterns là tính năng chính thức từ Java 21 (JEP 440); không cần bật `--enable-preview`.

## 1. Bài toán và ý tưởng chính

Một `record` trong Java là kiểu dữ liệu có các *component* được khai báo rõ. Record cũng có thể mang tham số kiểu (*generic*), chẳng hạn `Box<T>` giữ một giá trị kiểu `T`. **Record pattern** cho phép kiểm tra một đối tượng có phải kiểu record phù hợp hay không và bóc tách các component thành biến cục bộ ngay tại vị trí khớp.

Ví dụ, khi một hàm nhận `Box<String>`, ta có thể viết `box instanceof Box(var text)` để lấy thành phần `text` mà không phải gọi thủ công `box.value()`. Trình biên dịch suy luận kiểu của `text` từ kiểu `Box<String>` đã biết. Đây là kết hợp giữa **generic type inference** tại thời điểm biên dịch và **deconstruction** của record pattern.

Tuy nhiên, `Box<String>` không có thông tin tham số `String` được lưu đầy đủ ở runtime do *type erasure*. Record pattern cũng không “khôi phục” type argument đã bị xóa. Cần phân biệt rõ việc kiểm tra **record object**, kiểm tra **giá trị component**, và việc tin vào **kiểu generic tĩnh** của biểu thức đầu vào.

Mục tiêu sau bài học: viết record pattern có tham số kiểu tường minh hoặc suy luận; hiểu `var` và pattern lồng nhau; nhận ra giới hạn với raw type, wildcard và non-reifiable type; chọn kiểm tra an toàn khi đầu vào có kiểu rộng.

## 2. Khai báo generic record và cú pháp record pattern

Giả sử có ba record:

```java
record Box<T>(T value) {}

record Pair<L, R>(L left, R right) {}

record Envelope<T>(String label, Box<T> box) {}
```

`Box<T>` có một component kiểu `T`; `Pair<L, R>` có hai tham số kiểu riêng; `Envelope<T>` cho thấy một record generic có thể chứa một record generic khác.

Với đối tượng `Box<String> box = new Box<>("Java");`, các cách đọc dữ liệu tương ứng là:

```java
String a = box.value();                   // Truy cập component bằng accessor.
if (box instanceof Box<String>(String b)) {
    System.out.println(b);                // Record pattern có kiểu tường minh.
}
if (box instanceof Box(var c)) {
    System.out.println(c.toUpperCase());  // c được suy luận là String.
}
```

Trong `Box<String>(String b)`:

- `Box<String>` là **kiểu record trong pattern**; ở đây kiểu đầu vào đã biết là `Box<String>`, nên phép đối chiếu không đòi hỏi một cast generic thiếu an toàn.
- `String b` là **pattern của component**. Component được bóc tách và ràng buộc vào `b` khi pattern phù hợp.
- `Box(var c)` bỏ qua việc viết tường minh tham số kiểu và kiểu component. Compiler suy luận kiểu từ ngữ cảnh; với `Box<String>`, `c` có kiểu tĩnh `String`.

Trong `if`, biến pattern chỉ nằm trong các vị trí luồng điều khiển mà Java biết pattern đã khớp. Bản thân `Box(...)` không khớp khi đối tượng record ở cấp ngoài là `null`.

## 3. Suy luận kiểu cho generic record pattern

### 3.1. Đầu vào có generic type xác định

```java
static String upper(Box<String> box) {
    if (box instanceof Box(var text)) {
        return text.toUpperCase(java.util.Locale.ROOT);
    }
    return "NO_BOX";
}
```

Trong nhánh khớp, `text` là `String`, nên gọi `toUpperCase` hợp lệ. Nếu `box == null`, record pattern không khớp, phương thức trả `NO_BOX`. Để bảo vệ component có thể bằng `null`, cần kiểm tra thêm `text == null` trước khi gọi phương thức trên nó.

Với hai tham số kiểu, ý tưởng không thay đổi:

```java
static String pairText(Pair<String, Integer> pair) {
    if (pair instanceof Pair(var label, var count)) {
        return label + ":" + (count + 1);
    }
    return "NO_PAIR";
}
```

Compiler suy luận `label` là `String` và `count` là `Integer`. Phép cộng `count + 1` sử dụng unboxing của `Integer`, nên vẫn có thể ném `NullPointerException` nếu component `count` bằng `null`.

### 3.2. `var` là suy luận kiểu tĩnh, không phải kiểu động

```java
static void inspectUnknown(Object input) {
    if (input instanceof Box(var content)) {
        System.out.println(content);
        // content.toUpperCase(); // Không hợp lệ: content chưa chắc là String.
    }
}
```

Với đầu vào khai báo `Object`, compiler không thể giả định `Box<T>` thực tế là `Box<String>`. Dùng `Box(var content)` vẫn bóc được component, nhưng không cho quyền gọi các phương thức riêng của `String` nếu kiểu tĩnh suy luận của `content` không chứng minh được điều đó.

Đây là điểm khác biệt giữa **thông tin generic ở compile time** và **kiểu runtime của component**. Từ khóa `var` không làm một biến tự đổi kiểu tĩnh theo từng đối tượng đang chạy.

## 4. Khi đầu vào chỉ có kiểu `Object`: kiểm tra component thực sự

Một cách an toàn để xử lý đầu vào không rõ tham số generic là dùng **pattern có kiểm tra kiểu component**:

```java
static String inspect(Object input) {
    if (input instanceof Box(String text)) {
        return "string:" + text;
    } else if (input instanceof Box(Integer number)) {
        return "integer:" + number;
    } else if (input instanceof Box(var other)) {
        return "other:" + other;
    }
    return "not-box";
}
```

Khi đối chiếu `Object input`, Java có thể suy luận record pattern `Box(...)` với thông tin kiểu tổng quát phù hợp và thực hiện kiểm tra các component theo từng pattern:

1. `Box(String text)` chỉ khớp khi đối tượng là `Box` và giá trị component khớp `String` theo ngữ cảnh này.
2. `Box(Integer number)` xử lý component kiểu `Integer`.
3. `Box(var other)` bắt các `Box` còn lại, kể cả Box có component `null`. Nhánh này phải ở sau các nhánh cụ thể nếu muốn phân biệt.
4. Đối tượng không phải `Box`, hoặc bản thân `input == null`, đi tới `not-box`.

**Một điều rất quan trọng:** `Box(String text)` ở đây kiểm tra **giá trị component**, không chứng minh được type argument được khai báo ban đầu của đối tượng là `String`. Do *type erasure*, đối tượng `Box` không mang theo một “nhãn `T = String`” để so sánh trực tiếp tại runtime.

Nếu ứng dụng cần hợp đồng kiểu nghiêm ngặt, hãy thiết kế API truyền `Box<String>` ngay từ đầu, truyền thêm type token như `Class<T>` khi thích hợp, hoặc xác thực giá trị khi nhận dữ liệu đầu vào. Record pattern không thay thế hệ thống kiểm tra dữ liệu.

## 5. Reifiable types, type erasure và giới hạn của pattern có type argument

### 5.1. Reifiable là gì?

Một kiểu *reifiable* có đủ thông tin kiểu để thực hiện một số kiểm tra runtime an toàn sau khi biên dịch. Ví dụ `String`, `Box<?>`, `List<?>` là các kiểu có thể sử dụng cho kiểm tra phù hợp; ngược lại `Box<String>` và `List<String>` không reifiable vì đối số generic cụ thể bị xóa ở runtime.

Từ đối tượng có kiểu rộng:

```java
Object input = new Box<>("Java");
boolean isBox = input instanceof Box<?>; // Hợp lệ: kiểm tra Box ở runtime.
```

Nhưng không được thay bằng kiểm tra parameterized type cụ thể nếu cần unchecked conversion:

```java
// KHÔNG BIÊN DỊCH: kiểm tra Box<String> từ Object không an toàn.
// if (input instanceof Box<String>(var text)) {
//     System.out.println(text);
// }
```

Lý do: từ `Object` sang `Box<String>` không thể bảo đảm an toàn ở runtime khi chỉ biết raw class `Box`. Compiler không cho phép record pattern yêu cầu unchecked conversion như vậy.

### 5.2. Vì sao `Box<String>(String s)` đôi khi lại hợp lệ?

```java
Box<String> known = new Box<>("ok");

if (known instanceof Box<String>(String text)) {
    System.out.println(text);
}
```

Mẫu này hợp lệ vì **kiểu tĩnh đầu vào đã là `Box<String>`**. Không cần một unchecked conversion để suy ra rằng đối tượng được khai báo theo hợp đồng đó. Khả năng viết type argument trong record pattern **không có nghĩa** là Java kiểm tra được một type argument generic tùy ý ở runtime.

Tương tự, việc nhận `Box raw` rồi viết `raw instanceof Box<String>(var s)` không tạo ra chứng cứ hợp lệ cho `String`. Tránh raw type và unchecked cast; nếu gặp dữ liệu thiếu thông tin kiểu, dùng `Box<?>`, kiểm tra component, rồi chuyển thành API có kiểu rõ ràng.

### 5.3. Generic lồng nhiều tầng

Từ `Object` không thể xác nhận `Box<List<String>>` chỉ bằng tham số kiểu. Nhưng có thể kiểm tra component là một danh sách với phần tử chưa biết:

```java
static int listSize(Object value) {
    if (value instanceof Box(java.util.List<?> list)) {
        return list.size();
    }
    return -1;
}
```

`List<?>` cho phép biết component là `List` và gọi `size()`. Nó **không** chứng minh mọi phần tử là `String`. Muốn dựa trên kiểu từng phần tử, phải kiểm tra hoặc thiết lập hợp đồng dữ liệu riêng; không ép kiểu toàn danh sách một cách mù quáng.

## 6. Record pattern lồng nhau và generic type inference

Giả sử:

```java
Box<Box<String>> nested = new Box<>(new Box<>("inner"));
```

Ta có thể bóc hai tầng:

```java
if (nested instanceof Box(Box(var text))) {
    System.out.println(text); // In "inner"; text được suy luận là String.
}
```

Compiler suy luận type arguments của record pattern dựa trên kiểu đã biết `Box<Box<String>>`, sau đó suy luận tiếp pattern ở component bên trong. Đây là **nested record pattern**, không phải phép kiểm tra `instanceof Box<Box<String>>` trên một `Object` thiếu thông tin.

Với `Envelope<String>`:

```java
Envelope<String> item =
        new Envelope<>("message", new Box<>("hello"));

if (item instanceof Envelope(var label, Box(var text))) {
    System.out.println(label + ":" + text); // message:hello
}
```

Ở đây `label` là `String`, record pattern `Box(var text)` ở tầng hai bóc nội dung `hello`. Nếu component `box` bằng `null`, pattern lồng `Box(...)` không khớp. Nếu bản thân `item` bằng `null`, record pattern ở cấp ngoài cũng không khớp.

**Lưu ý về `null`:** component của một generic record có thể nhận `null` dù type argument là `String`. Một type pattern lồng trực tiếp trong record pattern có thể *null-matching* nếu nó vô điều kiện (*unconditional*) cho kiểu component đã được xác định tĩnh. Chẳng hạn với `Box<String> knownNull = new Box<>(null)`, `knownNull instanceof Box(String s)` có thể khớp và `s == null`. Còn khi cùng object chỉ được nhìn qua `Object unknown`, `unknown instanceof Box(String s)` không mặc nhiên khớp component `null`, vì compiler không biết component có kiểu tĩnh `String`. Luôn bảo vệ biến có thể null trước khi gọi phương thức.

## 7. Kết hợp với `switch` trong Java 21

Record pattern có thể xuất hiện trong `instanceof` và các nhánh `case` của `switch`. Ví dụ một phép mô tả có xử lý cả selector null:

```java
static String describeEnvelope(Envelope<String> input) {
    return switch (input) {
        case null -> "no-envelope";
        case Envelope(var label, Box(var text)) -> label + ":" + text;
        default -> "no-box";
    };
}
```

Thứ tự xử lý:

- `case null` dành riêng cho selector `null`.
- `case Envelope(var label, Box(var text))` bóc component `label` và record `Box` bên trong khi cả hai tầng phù hợp.
- `default` xử lý những giá trị chưa khớp, ví dụ `Envelope<String>` tồn tại nhưng có component `box == null`.

Một `switch` expression phải bảo đảm đầy đủ nhánh. Nếu bỏ `default` mà các pattern còn lại chưa bao phủ được mọi giá trị có thể xảy ra, trình biên dịch có thể báo thiếu tính toàn diện (*exhaustiveness*). Không dùng `case Box<String>(...)` trên `Object` như cách kiểm tra type argument runtime.

## 8. Chương trình Java 21 hoàn chỉnh

Chương trình dưới đây gom các trường hợp: generic type đã biết, đối tượng chưa biết type argument, nested record, `switch`, `List<?>` và `null`.

Tạo tệp **`GenericRecordPatternDemo.java`**:

```java
public class GenericRecordPatternDemo {
    record Box<T>(T value) {}

    record Envelope<T>(String label, Box<T> box) {}

    static String known(Box<String> box) {
        if (box instanceof Box(var text)) {
            return "known:" + text.toUpperCase(java.util.Locale.ROOT);
        }
        return "missing";
    }

    static String inspect(Object input) {
        if (input instanceof Box(String text)) {
            return "string:" + text;
        } else if (input instanceof Box(Integer number)) {
            return "integer:" + number;
        } else if (input instanceof Box(var other)) {
            return "other:" + other;
        }
        return "not-box";
    }

    static String nested(Box<Box<String>> value) {
        if (value instanceof Box(Box(var text))) {
            return "nested:" + text;
        }
        return "nested-unmatched";
    }

    static String describeEnvelope(Envelope<String> input) {
        return switch (input) {
            case null -> "no-envelope";
            case Envelope(var label, Box(var text)) -> label + ":" + text;
            default -> "no-box";
        };
    }

    static int listSize(Object input) {
        if (input instanceof Box(java.util.List<?> list)) {
            return list.size();
        }
        return -1;
    }

    public static void main(String[] args) {
        System.out.println(known(new Box<>("Java")));
        System.out.println(known(null));

        System.out.println(inspect(new Box<>("hello")));
        System.out.println(inspect(new Box<>(42)));
        System.out.println(inspect(new Box<>(3.5)));
        System.out.println(inspect("plain"));
        System.out.println(inspect(new Box<String>(null)));

        System.out.println(nested(new Box<>(new Box<>("inner"))));
        System.out.println(nested(new Box<Box<String>>(null)));

        System.out.println(
                describeEnvelope(new Envelope<>("msg", new Box<>("OK"))));
        System.out.println(
                describeEnvelope(new Envelope<String>("missing", null)));
        System.out.println(describeEnvelope(null));

        System.out.println(
                "size=" + listSize(new Box<>(java.util.List.of("a", "b"))));
        System.out.println("size=" + listSize(new Box<>(42)));
    }
}
```

Biên dịch và chạy bằng JDK 21 hoặc mới hơn:

```bash
javac --release 21 GenericRecordPatternDemo.java
java GenericRecordPatternDemo
```

Kết quả:

```text
known:JAVA
missing
string:hello
integer:42
other:3.5
not-box
other:null
nested:inner
nested-unmatched
msg:OK
no-box
no-envelope
size=2
size=-1
```

Giải thích các phần quan trọng:

1. `known(new Box<>("Java"))` nhận `Box<String>` theo kiểu tĩnh; `Box(var text)` suy luận `text` là `String`, nên trả `known:JAVA`. `known(null)` không khớp record pattern, trả `missing`.
2. `inspect` nhận `Object`. Pattern `Box(String text)` phát hiện component `"hello"`; pattern `Box(Integer number)` phát hiện `42`; `3.5` vào nhánh tổng quát; `"plain"` không phải Box.
3. `new Box<String>(null)` được truyền vào phương thức `inspect(Object)`. Trong ngữ cảnh `Object`, `Box(String text)` không khớp component null; `Box(var other)` có thể nhận null nên in `other:null`.
4. `Box(Box(var text))` chỉ khớp khi record ngoài và record component bên trong đều tồn tại. `new Box<Box<String>>(null)` cho `nested-unmatched`.
5. `describeEnvelope` cho `msg:OK` khi lồng nhau đầy đủ; dùng `default` khi component Box null; dùng `case null` cho selector null.
6. `listSize` chấp nhận một component là `List<?>` và đọc kích thước; với `42`, pattern `List<?>` không khớp nên trả `-1`.

Các type pattern `String`, `Integer`, `List<?>` trong `inspect` và `listSize` kiểm tra **component runtime**; chúng không chứng nhận type argument gốc của record.

## 9. Sai lầm thường gặp và cách tránh

| Sai lầm | Hậu quả | Cách hiểu/khắc phục |
| --- | --- | --- |
| Cho rằng `Box<String>` còn giữ `String` như type token ở runtime | Viết phép kiểm tra generic mà JVM không thể xác nhận | Phân biệt type erasure với kiểm tra component; dùng `Box<?>` hoặc pattern component |
| Viết `obj instanceof Box<String>(var x)` khi `obj` là `Object` | Lỗi biên dịch do cần unchecked conversion | Dùng `Box(String x)` để kiểm tra giá trị component hoặc thiết kế API nhận `Box<String>` |
| Dùng raw type rồi ép `Box<String>` không kiểm tra | Có thể gặp `ClassCastException` khi dùng dữ liệu sai kiểu | Tránh raw type; xử lý bằng wildcard và kiểm tra component |
| Nghĩ `Box(var x)` luôn làm `x` thành `String` | Không thể gọi phương thức đặc trưng String nếu ngữ cảnh không chứng minh kiểu | Xem kiểu tĩnh của biểu thức đầu vào; nếu cần dùng `Box(String x)` |
| Cho rằng `List<?>` cũng chứng minh `List<String>` | Có thể ép/call nhầm kiểu từng phần tử | Duyệt và kiểm tra phần tử hoặc dùng nguồn dữ liệu có hợp đồng kiểu |
| Cho rằng generic record chứa null không thể match | Bỏ sót trường hợp component null hoặc gây `NullPointerException` | Phân biệt record ngoài null với component null; kiểm tra component trước khi dùng |
| Đặt nhánh Box tổng quát trước các pattern cụ thể | Các nhánh cụ thể có thể không bao giờ tới được | Đặt pattern cụ thể trước, tổng quát sau; tuân theo quy tắc dominance của `switch` |
| Dùng `Box<String>` như thể là `Box<Object>` | Generics Java bất biến (*invariant*) | Dùng `Box<?>` khi chỉ cần đọc mà không biết T |
| Sao chép record pattern vào compiler Java 17 | Không biên dịch vì record pattern chưa là tính năng chính thức ở JDK 17 | Dùng JDK 21+; kiểm tra cả JDK của IDE, Gradle/Maven và lệnh `javac` |

## 10. Bài tập và tiêu chí tự kiểm tra

1. Khai báo `record Pair<L, R>(L left, R right) {}` và hàm nhận `Pair<String, Integer>`. Dùng `Pair(var label, var count)` để trả `label + ":" + count`; giải thích compiler suy luận hai kiểu nào.
2. Với `Object data = new Box<>(42);`, thử `data instanceof Box(Integer n)` và `data instanceof Box(String s)`; giải thích điều kiện nào khớp và điều này nói gì về **component**, không phải type argument.
3. Thử biên dịch `data instanceof Box<String>(var s)` khi `data` có kiểu `Object`. Ghi lại lỗi unchecked conversion và thay bằng cách kiểm tra component phù hợp.
4. Tạo `Box<Box<String>>` có hai tầng thật và một trường hợp component Box bên trong bằng `null`. Dùng `Box(Box(var text))` để phân biệt; tránh giả định mọi component đều không null.
5. Viết `switch` cho `Envelope<String>` có `case null`, record pattern lồng và `default`. Xử lý rõ ràng cả record null và component null.
6. Thử `Box<List<String>>` và `Box<List<Integer>>` trong hàm nhận `Object`; dùng `Box(List<?> list)` để đọc `size()`, sau đó giải thích vì sao chưa đủ để kết luận từng phần tử là `String`.
7. Tạo `Box<String> known = new Box<>(null);` và kiểm tra `known instanceof Box(String text)`. So sánh với `Object opaque = known; opaque instanceof Box(String text)` để giải thích khi nào type pattern lồng là null-matching theo ngữ cảnh tĩnh.

**Đạt bài học khi:** đọc được generic record pattern có `var`, type argument tường minh và nesting; nói đúng sự khác biệt giữa suy luận compile time với kiểm tra runtime; nhận diện được non-reifiable type, unchecked conversion, `null`, và xử lý các trường hợp biên bằng chương trình Java 21 chạy được.

**Tài liệu đối chiếu:**

- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
- [Java Language Specification 21, §18.5.5 — Record Pattern Type Inference](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html#jls-18.5.5).
- [Java Language Specification 21, §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
