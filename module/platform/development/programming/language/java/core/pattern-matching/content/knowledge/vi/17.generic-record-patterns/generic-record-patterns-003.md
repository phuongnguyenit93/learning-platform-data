# Generic record patterns: pattern type argument và target type trong Java 21

## 1. Mục tiêu và bối cảnh

**Generic record pattern** là record pattern dùng với một `record` có type parameter, ví dụ `record Box<T>(T value) {}`. Khi khớp pattern, Java vừa kiểm tra cấu trúc record, vừa cho phép truy cập component qua các pattern con. Vấn đề quan trọng là: **kiểu của component và kiểu của pattern variable được quyết định từ đâu?**

Có hai khái niệm phải phân biệt:

- **Pattern type argument**: đối số kiểu viết sau tên record trong pattern, chẳng hạn phần `<String>` của `Box<String>(var text)`. Có thể ghi rõ hoặc để compiler suy luận bằng `Box(var text)`.
- **Target type (kiểu đích của phép khớp pattern)**: kiểu tĩnh mà compiler biết về giá trị đang được đem so với pattern, chẳng hạn `Box<String>`, `Box<? extends CharSequence>` hoặc `Object`. Với record pattern lồng nhau, kiểu của **component tương ứng trong record ngoài** là ngữ cảnh kiểu dùng để suy luận cho pattern trong.

Record patterns được chuẩn hóa ở **Java 21 (JEP 440)** và có thể dùng với `instanceof` hoặc pattern matching trong `switch`. Các ví dụ trong bài biên dịch bằng Java 21+ mà không cần bật preview.

> Cốt lõi: generic type arguments được suy luận chủ yếu từ **kiểu đã được biết tại thời điểm biên dịch**. Java không thể đọc lại `T` của một `Box<T>` bất kỳ tại runtime để chứng minh đối tượng là `Box<String>`, vì thông tin generic phần lớn bị xóa (type erasure).

## 2. Type argument ghi tường minh và suy luận từ target type

Định nghĩa:

```java
record Box<T>(T value) {}

Box<String> box = new Box<>("java");
```

Hai cách dưới đây có ý nghĩa tương ứng trong ngữ cảnh `box` có kiểu tĩnh `Box<String>`:

```java
// Ghi rõ type argument của record pattern:
if (box instanceof Box<String>(var text)) {
    System.out.println(text.toUpperCase());
}

// Để compiler suy luận từ target type Box<String>:
if (box instanceof Box(var text)) {
    System.out.println(text.toUpperCase());
}
```

Cả hai đều in `JAVA`. Ở cách thứ nhất, `<String>` là **pattern type argument** và `var text` nhận kiểu `String`. Ở cách thứ hai, `Box(var text)` được suy luận theo ngữ cảnh `Box<String>`, nên compiler cũng biết `text` có kiểu `String`. Vì thế gọi `text.toUpperCase()` hợp lệ mà không cần ép kiểu.

Có thể viết `Box<String>(String text)` để ghi rõ cả type argument và type pattern của component. Nhưng hai vị trí đó có nhiệm vụ khác nhau: `Box<String>` nói về **kiểu record được kiểm tra theo quy tắc type system**, còn `String text` kiểm tra/ràng buộc **component bên trong**. Khi component đã được bảo đảm là `String` bởi target type, dùng `var` thường gọn và dễ duy trì.

Cú pháp `new Box<>("java")` dùng diamond `<>` để suy luận type arguments khi **tạo đối tượng**. Ngược lại, `Box(var text)` là cú pháp **khớp và phân rã record**. Cả hai có suy luận kiểu nhưng là hai cơ chế được dùng ở hai ngữ cảnh khác nhau.

## 3. Target type làm thay đổi những gì compiler có thể biết

Xem hai lời gọi với cùng một đối tượng runtime:

```java
Box<String> typed = new Box<>("hello");
Object unknown = typed;
```

Với `typed instanceof Box(var x)`, ngữ cảnh đã biết `Box<String>` và `x` có kiểu `String`. Với `unknown instanceof Box(var x)`, biểu thức bên trái chỉ có kiểu tĩnh `Object`. Compiler có thể kiểm tra runtime rằng `unknown` là một `Box` và lấy component; nhưng **không thể suy ra `String` chỉ từ generic type argument đã bị xóa**. Biến `x` trong trường hợp này được xử lý như `Object`, nên `x.toUpperCase()` không biên dịch.

Muốn phân biệt kiểu **thực tế của component** khi đầu vào là `Object`, dùng type pattern cho component:

```java
Object unknown = new Box<>("hello");

if (unknown instanceof Box(String text)) {
    System.out.println(text.toUpperCase()); // HELLO
}
```

`Box(String text)` kiểm tra rằng đối tượng là `Box` **và** component của nó là một `String`. Nếu bên trong là `Integer`, pattern không khớp. Đây là kiểm tra runtime hợp lệ đối với component, khác với việc yêu cầu kiểm tra generic parameter `Box<String>` tại runtime.

**Đoạn sau không biên dịch:**

```java
Object unknown = new Box<>("hello");

// LỖI: Object cannot be safely cast to Box<String>.
if (unknown instanceof Box<String>(var text)) {
    System.out.println(text);
}
```

Dù ví dụ tạo `unknown` từ chuỗi, **kiểu tĩnh** của nó là `Object`. Java không cho phép record pattern `Box<String>(...)` trong tình huống cần unchecked conversion. Bài toán không được giải quyết bằng việc cố ép generic type argument vào pattern.

Quy tắc thực dụng: khi dữ liệu đã có kiểu chính xác như `Box<String>`, có thể viết tường minh `Box<String>(...)` hoặc để compiler suy luận `Box(...)`; khi đầu vào quá tổng quát như `Object`, hãy dùng `Box(var x)` rồi kiểm tra component hoặc `Box(String x)` nếu thật sự cần một `String`.

## 4. Suy luận đệ quy từ target type của record ngoài

Các record generic có thể lồng nhau nhiều cấp:

```java
record Box<T>(T value) {}
record Pair<A, B>(A first, B second) {}
record Envelope<T>(String tag, Box<Pair<String, T>> data) {}
```

Giả sử phương thức nhận `Envelope<Integer> env`:

```java
if (env instanceof Envelope(var tag, Box(Pair(var name, var count)))) {
    System.out.println(tag + ": " + name.toUpperCase() + " -> " + (count + 1));
}
```

Compiler suy luận theo từng bước:

1. **Cấp ngoài:** từ `env` có kiểu tĩnh `Envelope<Integer>`, biết `T = Integer`. Pattern `Envelope(...)` phù hợp với record này.
2. **Component `tag`:** `Envelope.tag` là `String`, nên `var tag` có kiểu `String`.
3. **Component `data`:** khi thay `T` bằng `Integer`, nó có kiểu `Box<Pair<String, Integer>>`. Đó là **target type** cho pattern `Box(...)` bên trong.
4. **Component `Box.value`:** có kiểu `Pair<String, Integer>`. Đó lại là **target type** cho `Pair(...)`.
5. **Hai component cuối:** `name` có kiểu `String`; `count` có kiểu `Integer`. Vì vậy gọi `name.toUpperCase()` và tính `count + 1` đều hợp lệ. Phép `+ 1` thực hiện unboxing `Integer` nên component `count == null` có thể gây `NullPointerException` khi tính toán; suy luận kiểu không tự thay cho kiểm tra null của component.

Ta có thể viết tường minh các type arguments (khi cần làm rõ sơ đồ kiểu):

```java
if (env instanceof Envelope<Integer>(
        var tag,
        Box<Pair<String, Integer>>(
            Pair<String, Integer>(var name, var count)))) {
    System.out.println(name + ": " + count);
}
```

Cách tường minh dài hơn; khi target type rõ ràng, chuỗi `Envelope(var tag, Box(Pair(var name, var count)))` thường dễ đọc hơn. Điều đáng nhớ là type argument của **pattern con** không suy luận ngẫu nhiên từ giá trị runtime, mà từ **kiểu component do pattern cha cung cấp**.

Nếu component `data` bằng `null`, `Box(...)` bên trong không khớp vì không có đối tượng Box để phân rã. Tương tự, nếu `Pair` bên trong là `null`, `Pair(...)` không khớp. Tuy nhiên, một `var` component đơn thuần có thể nhận `null`; cần phân biệt “record con bị null” với “một component bên trong record có giá trị null”.

## 5. Wildcard target type và giới hạn của suy luận

Xem target type:

```java
Box<? extends CharSequence> box = new Box<>("hello");

if (box instanceof Box(var text)) {
    System.out.println(text.length()); // 5
}
```

`text` được sử dụng qua giao diện `CharSequence` — giới hạn kiểu trên của wildcard `? extends CharSequence`. Phép gọi `length()` hợp lệ, nhưng `text.toUpperCase()` không hợp lệ vì `CharSequence` không khai báo phương thức đó. Dù đối tượng hiện tại đang chứa `String`, type system không coi mọi `CharSequence` đều là `String`.

Muốn gọi API chỉ có ở `String` thì phải kiểm tra thêm:

```java
if (box instanceof Box(var text) && text instanceof String s) {
    System.out.println(s.toUpperCase()); // HELLO
}
```

Đừng dùng `Box<String>(var s)` để thay thế kiểm tra component: kiểu tĩnh `Box<? extends CharSequence>` không cho phép khẳng định an toàn rằng type argument chính xác là `String`.

Với `Box<?>`, compiler không thể tự kết luận component là `String`; có thể dùng `Box(String s)` để kiểm tra component tại runtime. Với `Box<Integer>`, `var n` có kiểu `Integer`; với `Box<Number>`, `var n` có kiểu `Number`. **Generic invariant**: `Box<Integer>` không phải là subtype của `Box<Number>`, dù `Integer` là subtype của `Number`.

## 6. Ví dụ hoàn chỉnh: explicit, inferred, nested, wildcard và switch

Tạo tệp `GenericRecordPatternDemo.java`:

```java
public class GenericRecordPatternDemo {
    record Box<T>(T value) {}
    record Pair<A, B>(A first, B second) {}
    record Envelope<T>(String tag, Box<Pair<String, T>> data) {}

    static String explicit(Box<String> box) {
        if (box instanceof Box<String>(var text)) return text.toUpperCase();
        return "no match";
    }

    static String inferred(Box<String> box) {
        if (box instanceof Box(var text)) return text.toUpperCase();
        return "no match";
    }

    static String fromObject(Object obj) {
        if (obj instanceof Box(var element)) {
            return element == null ? "Box(null)" : "Box(" + element.getClass().getSimpleName() + ")";
        }
        return "not a Box";
    }

    static int wildcard(Box<? extends CharSequence> box) {
        if (box instanceof Box(var text)) return text.length();
        return -1;
    }

    static String nested(Envelope<Integer> env) {
        if (env instanceof Envelope(var tag, Box(Pair(var name, var count)))) {
            return tag + ": " + name.toUpperCase() + " -> " + (count + 1);
        }
        return "incomplete";
    }

    static String classify(Object value) {
        return switch (value) {
            case null -> "null";
            case Box(var item) when item instanceof String s -> "string " + s;
            case Box(var item) -> "box " + (item == null ? "null" : item.getClass().getSimpleName());
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Box<String> textBox = new Box<>("java");
        Envelope<Integer> order = new Envelope<>("E1",
                new Box<>(new Pair<>("items", 4)));

        System.out.println(explicit(textBox));
        System.out.println(inferred(textBox));
        System.out.println(fromObject(new Box<>(123)));
        System.out.println(wildcard(new Box<>("hello")));
        System.out.println(nested(order));
        System.out.println(nested(new Envelope<>("E2", null)));
        System.out.println(classify(new Box<>("ok")));
        System.out.println(classify(new Box<>(27)));
        System.out.println(classify(new Box<>(null)));
        System.out.println(classify(null));
    }
}
```

Chạy với JDK 21 trở lên:

```bash
javac --release 21 GenericRecordPatternDemo.java
java GenericRecordPatternDemo
```

Kết quả đúng:

```text
JAVA
JAVA
Box(Integer)
5
E1: ITEMS -> 5
incomplete
string ok
box Integer
box null
null
```

Cách đọc kết quả:

- Hai dòng `JAVA` cho thấy pattern có type argument `<String>` tường minh và pattern để compiler suy luận đều lấy được `String`.
- `Box(Integer)` cho thấy đầu vào tĩnh `Object` vẫn có thể khớp hình dạng record `Box` nhưng không được gán “mặc định là String”.
- `5` là độ dài chuỗi trong `Box<? extends CharSequence>`; kiểu mà code có thể dùng là API chung `CharSequence`.
- `E1: ITEMS -> 5` chứng minh suy luận xuyên ba generic record patterns và unboxing component `Integer`.
- `incomplete` xảy ra vì `Envelope.data == null`: nested `Box(...)` không khớp.
- Hai dòng `string ok` và `box Integer` cho thấy `switch` có thể phân biệt **kiểu thực của component** bằng `when item instanceof String s` ngay cả khi selector được khai báo `Object`.
- `box null` là một record `Box` hợp lệ có component bằng `null`; `null` cuối cùng là bản thân selector của `switch` bằng `null` và được bắt bởi `case null`.

Trong `switch`, đặt nhánh có `when` trước nhánh `case Box(var item)` tổng quát. Đảo thứ tự có thể tạo nhánh bị che khuất và gây lỗi biên dịch do domination.

## 7. Các lỗi biên dịch và ngộ nhận thường gặp

| Tình huống | Vì sao sai hoặc dễ nhầm | Hướng xử lý |
| --- | --- | --- |
| `Object value` rồi `value instanceof Box<String>(var s)` | Không thể xác nhận generic argument `String` qua runtime erasure; phép chuyển kiểu cần unchecked conversion. | Dùng `Box(String s)` để kiểm tra component, hoặc giữ kiểu `Box<String>` ở API đầu vào. |
| `Box raw` rồi `raw instanceof Box<String>(var s)` | Raw type làm mất ràng buộc generic cần thiết. | Tránh raw type; truyền `Box<String>` hoặc dùng `Box(var s)` với kiểm tra bổ sung. |
| `Box<Number>` và pattern `Box<Integer>(var n)` | Generic invariant; không phải cast an toàn từ `Box<Number>` sang `Box<Integer>`. | Kiểm tra kiểu thực của component nếu cần hoặc đổi hợp đồng generic từ đầu. |
| Tưởng `Box(var s)` luôn suy ra `String` từ `new Box<>("abc")` | Suy luận phụ thuộc target type tĩnh tại **vị trí kiểm tra**, không đọc lại biểu thức tạo đối tượng. | Xem kiểu biến/kiểu selector/kiểu component nơi pattern xuất hiện. |
| Tưởng `Box(String s)` và `Box<String>(var s)` giống nhau | Cái đầu kiểm tra component `String` tại runtime; cái sau chỉ hợp lệ khi type argument `String` an toàn theo kiểu tĩnh. | Chọn cú pháp theo mục tiêu kiểm tra. |
| Tưởng `var` tạo kiểu động | `var` vẫn có kiểu do compiler quyết định; không được gọi tùy ý phương thức của subtype. | Kiểm tra hoặc thu hẹp kiểu trước khi gọi API riêng. |
| Quên kiểm tra `null` ở record con hoặc component | Record pattern lồng trong không khớp với record con `null`; nhưng component `var` có thể chứa `null`. | Viết nhánh không khớp, kiểm tra thành phần nullable trước khi gọi phương thức/unboxing. |
| Dùng Java 17 không có hỗ trợ chuẩn | Record patterns chỉ được chuẩn hóa từ Java 21. | Dùng JDK 21+ cho toàn bộ ví dụ. |

Một ví dụ lỗi riêng **không được ghép vào tệp runnable**:

```java
record Box<T>(T value) {}

static void invalid(Object obj) {
    // Không biên dịch: không thể kiểm tra an toàn Box<String> từ Object.
    if (obj instanceof Box<String>(var text)) {
        System.out.println(text);
    }
}
```

Cách sửa khi cần chắc chắn component là chuỗi:

```java
static void valid(Object obj) {
    if (obj instanceof Box(String text)) {
        System.out.println(text.toUpperCase());
    }
}
```

Trong trường hợp API đã nhận được `Box<String>`, lại có thể dùng `Box<String>(var text)` hoặc `Box(var text)`. **Bối cảnh kiểu là một phần của việc xác định một pattern có hợp lệ hay không.**

## 8. Áp dụng và bài tập tự kiểm tra

Tình huống thực tế thường là dữ liệu dạng kết quả tổng quát (generic result wrapper), sự kiện chứa payload và cấu trúc lồng của AST. Generic record patterns cho phép lấy dữ liệu đúng kiểu mà ít phải gọi accessor và ép kiểu thủ công. Tuy nhiên, không nên lồng quá nhiều cấp nếu điều đó khiến ranh giới nullable hoặc điều kiện nghiệp vụ khó nhận ra.

**Bài tập:** Cho các record sau:

```java
record Pair<L, R>(L left, R right) {}
record Box<T>(T value) {}
record Response<T>(int status, Box<Pair<String, T>> payload) {}
```

Hãy điền kiểu của `label` và `quantity` ở ví dụ này, xác định target type của `Pair(...)`, và dự đoán khi `payload == null`:

```java
static String display(Response<Long> response) {
    if (response instanceof Response(var status, Box(Pair(var label, var quantity)))) {
        return status + "/" + label + "/" + quantity;
    }
    return "missing payload";
}
```

**Đáp án:** `Response<Long>` có `T = Long`. Component `payload` có kiểu `Box<Pair<String, Long>>`. Vì vậy `Pair(...)` có target type `Pair<String, Long>`; `label` có kiểu `String` và `quantity` có kiểu `Long`. Nếu `payload == null`, pattern `Box(...)` không khớp và phương thức trả về `"missing payload"`. Trái lại, nếu `payload` là `Box` nhưng `Pair` bên trong là `null`, pattern `Pair(...)` cũng không khớp. Nếu `Pair` tồn tại mà `quantity == null`, `var quantity` vẫn có thể được ràng buộc với giá trị `null`; cần kiểm tra trước khi unboxing hoặc gọi phương thức.

## 9. Tổng kết cơ chế

Một generic record pattern dùng hai nguồn thông tin: **type arguments tường minh** khi ta viết `Record<T>(...)`, hoặc **suy luận dựa trên kiểu tĩnh của giá trị được kiểm tra** khi viết `Record(...)`. Ở pattern nhiều cấp, kiểu component của record cha tạo ra target type cho pattern con, vì thế các ràng buộc generic được lan truyền tự nhiên. Type erasure vẫn giới hạn những gì Java có thể xác minh tại runtime; để kiểm tra kiểu nội dung trong dữ liệu tổng quát, sử dụng component type pattern hoặc `instanceof` phù hợp.

**Tài liệu tham khảo:** [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [Oracle Java 21 — Record Patterns (Generic Records, Type Inference, Nested Record Patterns)](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [Java SE 21 Language Specification — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
