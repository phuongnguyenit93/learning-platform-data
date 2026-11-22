# Suy luận type argument trong record pattern (Java 21+)

## 1. Vấn đề: record có tham số kiểu thì phân rã như thế nào?

Trong Java, một `record` có thể khai báo tham số kiểu (type parameter), giống lớp generic thông thường:

```java
record Box<T>(T value) {}
record Pair<L, R>(L left, R right) {}
```

`Box<String>` chứa một thành phần có **kiểu khai báo là `String`**, còn `Box<Integer>` chứa một thành phần có kiểu khai báo là `Integer`. Khi đọc nội dung qua `box.value()`, trình biên dịch dùng tham số kiểu của biến `box` để xác định kiểu kết quả.

Từ Java 21, **record pattern** cho phép kiểm tra và lấy các thành phần record trực tiếp trong `instanceof` hoặc `switch`. Với generic record pattern, Java còn có khả năng **suy luận type argument**: nếu kiểu tĩnh của biểu thức đủ thông tin, người viết có thể bỏ danh sách `<...>` ở tên record trong mẫu và để trình biên dịch xác định tham số kiểu phù hợp.

```java
Box<String> box = new Box<>("hello");

if (box instanceof Box(var text)) {
    // Trình biên dịch biết text có kiểu String.
    String upper = text.toUpperCase();
    System.out.println(upper);
}
```

Kết quả:

```text
HELLO
```

Trong mẫu `Box(var text)`, dấu ngoặc tròn là **danh sách mẫu thành phần của record**. `var text` là mẫu khai báo biến có kiểu được suy luận. Tên `Box` không có `<String>` nhưng kiểu của `text` vẫn là `String` vì kiểu đầu vào đã được biết là `Box<String>`.

Đây là hai thao tác suy luận có liên quan nhưng khác nhau:

1. **Suy luận type argument của record pattern:** từ `Box<String>`, xác định tham số `T` của `Box<T>` tương ứng với `String`.
2. **Suy luận kiểu của biến `var`:** từ thành phần `T value` của record sau khi xác định `T`, xác định biến `text` là `String`.

**Phiên bản:** Record patterns, bao gồm suy luận tham số kiểu và mẫu lồng nhau, được chuẩn hóa trong **Java 21 (JEP 440)**. Những ví dụ trong bài dùng Java 21+, không cần bật preview.

## 2. Cơ chế suy luận tại thời điểm biên dịch

Giả sử:

```java
record Box<T>(T value) {}

Box<String> textBox = new Box<>("Java");
```

Khi trình biên dịch gặp:

```java
if (textBox instanceof Box(var text)) {
    String copy = text;
}
```

Nó có hai nguồn thông tin: (a) kiểu tĩnh của `textBox` là `Box<String>`, và (b) thành phần record `Box<T>` có kiểu `T`. Trong ngữ cảnh này, trình biên dịch xác định kiểu generic tương ứng và kiểm tra mẫu thành phần theo kiểu đó; `text` được coi là `String`.

Để thấy rõ cú pháp, trường hợp đã biết kiểu cũng có thể viết tường minh:

```java
if (textBox instanceof Box<String>(var text)) {
    String copy = text;
}
```

Hai ví dụ trên cùng dùng dữ liệu đầu vào `Box<String>`, cùng cho `text` kiểu `String`. Cách rút gọn `Box(var text)` giúp giảm lặp lại tham số kiểu khi ngữ cảnh đã cung cấp đủ thông tin.

**Lưu ý về cú pháp:** `Box(var text)` là cách bỏ type argument của *record pattern*. **`Box<>(var text)` không phải cú pháp record pattern hợp lệ trong Java 21**. Dấu kim cương `<>` thường xuất hiện ở biểu thức tạo đối tượng như `new Box<>("hello")`, không đặt ở đây.

### Bảng suy luận theo kiểu đầu vào

| Kiểu tĩnh của biểu thức | Ví dụ mẫu | Kiểu có thể sử dụng của biến thành phần | Điều cần nhớ |
| --- | --- | --- | --- |
| `Box<String>` | `Box(var value)` | `String` | Gọi được `value.toUpperCase()` sau khi xét `null` |
| `Box<Integer>` | `Box(var value)` | `Integer` | Có thể gán cho `Integer` hoặc tự mở hộp sang `int` nếu khác `null` |
| `Box<? extends Number>` | `Box(var value)` | Một kiểu bị chặn trên bởi `Number` | Có thể gán cho `Number`; không tự suy ra `Integer` |
| `Box<?>` | `Box(var value)` | Không bảo đảm kiểu cụ thể hơn `Object` | Không được mặc định gán sang `String` |
| `Object` (bên trong có một `Box`) | `Box(var value)` | Không bảo đảm kiểu cụ thể hơn `Object` | Kiểu generic thực tế không được “khám phá” từ đối tượng lúc chạy |

Bảng nói về **bảo đảm của trình biên dịch**, không dự đoán lớp thực tế của một giá trị riêng lẻ tại runtime. Ví dụ, một biến khai báo `Box<? extends Number>` có thể chứa `Integer`, `Long` hoặc một kiểu con khác của `Number`; ta chỉ nên viết mã theo giới hạn kiểu đã được bảo đảm.

## 3. Ví dụ đầy đủ, có thể biên dịch và chạy

Lưu toàn bộ chương trình sau vào tệp **`GenericRecordPatternDemo.java`**:

```java
public class GenericRecordPatternDemo {
    record Box<T>(T value) {}
    record Pair<L, R>(L left, R right) {}
    record Parcel<T>(String id, Box<T> content) {}

    // Box<String> giúp suy ra biến text có kiểu String.
    static String upper(Box<String> box) {
        if (box instanceof Box(var text)) {
            String typed = text; // Hợp lệ: typed là String.
            return typed == null ? "Null content" : typed.toUpperCase();
        }
        return "Not a Box";
    }

    // Hai tham số kiểu L và R được suy ra độc lập.
    static String showPair(Pair<String, Integer> pair) {
        if (pair instanceof Pair(var name, var quantity)) {
            String label = name;       // String
            Integer amount = quantity; // Integer
            return label + ": " + amount;
        }
        return "Not a Pair";
    }

    // Từ Parcel<String> suy ra Box<String>, rồi suy ra text là String.
    static String showParcel(Parcel<String> parcel) {
        if (parcel instanceof Parcel(var id, Box(var text))) {
            String content = text;
            return id + " -> " + content;
        }
        return "Missing parcel content";
    }

    // Kiểu Object không bảo đảm Box mang tham số kiểu String.
    static String inspect(Object obj) {
        if (obj instanceof Box(String text)) {
            return "Text: " + text;
        }
        if (obj instanceof Box(var value)) {
            Object untyped = value;
            return "Box value: " + untyped;
        }
        return "Not a Box";
    }

    // Wildcard có giới hạn trên: giá trị sử dụng được như Number.
    static String showNumber(Box<? extends Number> box) {
        if (box instanceof Box(var value)) {
            Number number = value;
            return "Number: " + number.intValue();
        }
        return "Not a Box";
    }

    // Khi kiểu tĩnh tương thích, có thể viết type argument tường minh.
    static String explicit(Box<String> box) {
        if (box instanceof Box<String>(var text)) {
            return "Explicit: " + text;
        }
        return "Not a Box";
    }

    public static void main(String[] args) {
        System.out.println(upper(new Box<>("hello")));
        System.out.println(showPair(new Pair<>("items", 3)));
        System.out.println(showParcel(
                new Parcel<>("PK-01", new Box<>("book"))));
        System.out.println(inspect(new Box<>(42)));
        System.out.println(showNumber(new Box<>(7)));
        System.out.println(explicit(new Box<>("world")));
        System.out.println(upper(new Box<>(null)));
    }
}
```

Biên dịch với JDK 21 trở lên:

```bash
javac --release 21 GenericRecordPatternDemo.java
java GenericRecordPatternDemo
```

Kết quả:

```text
HELLO
items: 3
PK-01 -> book
Box value: 42
Number: 7
Explicit: world
Null content
```

Chương trình minh họa sáu trường hợp suy luận: từ một record một tham số; từ record có hai tham số kiểu; từ record generic lồng nhau; từ dữ liệu chỉ được khai báo là `Object`; từ wildcard có giới hạn; và cách chỉ rõ `Box<String>` trong mẫu.

## 4. Suy luận trong record pattern lồng nhau

Xét hai kiểu:

```java
record Box<T>(T value) {}
record Parcel<T>(String id, Box<T> content) {}
```

Một `Parcel<String>` có thành phần `content` kiểu `Box<String>`. Khi viết:

```java
Parcel<String> parcel =
        new Parcel<>("PK-01", new Box<>("book"));

if (parcel instanceof Parcel(var id, Box(var text))) {
    String message = text;
    System.out.println(id + " -> " + message);
}
```

Kết quả:

```text
PK-01 -> book
```

Luồng suy luận theo cấu trúc khai báo:

```text
parcel: Parcel<String>
  │
  ├── Parcel<T>  =>  T tương ứng với String
  │
  ├── thành phần id: String  =>  id có kiểu String
  │
  └── thành phần content: Box<T>  =>  Box<String>
        │
        └── mẫu Box(var text)  =>  text có kiểu String
```

Ở tầng trong, người viết không phải nhắc lại `<String>`. Điều đó không có nghĩa Java đọc tham số kiểu từ bộ nhớ đối tượng lúc chạy; trình biên dịch đã có quan hệ `Parcel<T>` chứa `Box<T>` trong **khai báo kiểu**.

Nếu `parcel.content()` bằng `null` thì `Box(var text)` không khớp vì không có đối tượng `Box` để phân rã. Nếu `content` là một `Box<String>` nhưng `content.value()` bằng `null` thì mẫu `Box(var text)` vẫn có thể khớp và `text` có giá trị `null`. Hãy phân biệt record con vắng mặt với thành phần bên trong record là `null`.

## 5. Suy luận và xóa kiểu generic (type erasure) không mâu thuẫn

Generic type argument chủ yếu được trình biên dịch dùng để kiểm tra kiểu. Java áp dụng **type erasure**: đối tượng `new Box<>("abc")` không lưu một dấu runtime đáng tin cậy cho biết nó đã được tạo bằng `Box<String>`. Vì vậy:

```java
Object unknown = new Box<>("abc");

if (unknown instanceof Box(var value)) {
    Object anyValue = value; // An toàn.
    System.out.println(anyValue);
}
```

Mã in `abc`, nhưng từ **kiểu tĩnh `Object`**, Java không thể bảo đảm `value` là `String`. Cũng trong ngữ cảnh này, viết phép thử sau là **lỗi biên dịch**:

```java
Object unknown = new Box<>("abc");

// SAI: không thể kiểm tra an toàn tham số kiểu String từ Object.
if (unknown instanceof Box<String>(var value)) {
    System.out.println(value);
}
```

Thông báo điển hình là `Object cannot be safely cast to Box<String>`. **Cú pháp record pattern generic không xóa bỏ quy tắc an toàn kiểu của `instanceof`**.

Nếu muốn kiểm tra rằng **thành phần** của `Box` thực sự là một chuỗi, có thể dùng **mẫu kiểu thành phần**:

```java
Object unknown = new Box<>("abc");

if (unknown instanceof Box(String value)) {
    System.out.println(value.toUpperCase());
}
```

Kết quả là `ABC`. Ở đây, `String value` là mẫu kiểm tra kiểu của **giá trị thành phần**, không phải một phép kiểm tra “đối tượng `Box` có type argument runtime là `String`”. Với `new Box<>(42)`, mẫu `Box(String value)` không khớp.

**Phân biệt quan trọng:**
- `Box(var value)`: khai báo biến với kiểu suy ra từ ngữ cảnh record; không yêu cầu thành phần đang có lớp runtime `String`.
- `Box(String value)`: dùng mẫu thành phần kiểu `String`; khi kiểu thành phần chưa được chứng minh là `String`, cần kiểm tra kiểu của giá trị thành phần lúc chạy.
- `Box<String>(var value)`: chỉ rõ type argument của record pattern; chỉ hợp lệ khi quy tắc kiểm tra kiểu tổng thể cho phép.

### Lưu ý nâng cao: ảnh hưởng của kiểu tĩnh đối với null

Record pattern có thể chứa một *mẫu thành phần khớp vô điều kiện* khi trình biên dịch đã biết thành phần mang đúng kiểu. Ví dụ sau minh họa việc kiểu tĩnh cũng tác động đến điều kiện khớp mẫu thành phần:

```java
record Box<T>(T value) {}

Box<String> typed = new Box<>(null);
Object unknownView = typed;

System.out.println(typed instanceof Box(String text));       // true
System.out.println(unknownView instanceof Box(String text)); // false
```

Khi biến có kiểu `Box<String>`, thành phần `value` được biết là `String` nên `String text` là mẫu khớp vô điều kiện cho thành phần đó, kể cả `null`. Khi nhìn cùng đối tượng qua `Object`, Java phải kiểm tra kiểu của thành phần tại runtime, và mẫu kiểu có điều kiện không khớp `null`. Cả hai trường hợp đều không kiểm tra type argument runtime của `Box`; sự khác biệt đến từ **thông tin kiểu có sẵn lúc biên dịch**.

Quy tắc thực hành: không dựa vào việc pattern khớp để khẳng định mọi trường khác `null`. Kiểm tra điều kiện nghiệp vụ ngay sau khi phân rã.

## 6. Nhiều type argument, wildcard và giới hạn kiểu

### 6.1. Hai tham số generic độc lập

```java
record Pair<L, R>(L left, R right) {}

Pair<String, Integer> pair = new Pair<>("score", 10);

if (pair instanceof Pair(var label, var points)) {
    String name = label;
    Integer count = points;
    System.out.println(name + ": " + count);
}
```

Kết quả: `score: 10`. Kiểu `L` tương ứng với `String`, kiểu `R` tương ứng với `Integer`. Việc cả hai mẫu đều dùng `var` không có nghĩa cả hai biến cùng kiểu; mỗi vị trí lấy kiểu từ thành phần tương ứng của record.

### 6.2. Giới hạn trên `? extends Number`

```java
Box<? extends Number> numeric = new Box<>(37);

if (numeric instanceof Box(var value)) {
    Number n = value;
    System.out.println(n.intValue());
}
```

Kết quả: `37`. Trình biên dịch biết `value` là một kiểu phù hợp với giới hạn `Number`, vì vậy có thể gán cho `Number`; không được mặc định gán sang `Integer` vì record có thể chứa một kiểu con khác của `Number`.

### 6.3. Wildcard `?` và raw type

Với `Box<?>`, type argument chưa được xác định cụ thể. `Box(var value)` vẫn có thể phân rã record, nhưng không bảo đảm `value` là `String` hay `Integer`. Mọi xử lý đòi hỏi kiểu hẹp hơn phải có kiểm tra thích hợp.

Tránh dùng raw type `Box` khi có thể viết `Box<String>`, `Box<Number>` hoặc `Box<?>`. Raw type làm mất thông tin kiểm tra kiểu, thường kéo theo cảnh báo unchecked và không giúp cơ chế suy luận record pattern mạnh hơn.

## 7. Các lỗi dễ mắc

1. **Cho rằng `var` đọc kiểu generic tại runtime.** Nó sử dụng các ràng buộc kiểu do trình biên dịch biết. Cùng một đối tượng có thể được tham chiếu bằng `Box<String>` hoặc `Object` và mang mức thông tin kiểu khác nhau.
2. **Viết `Box<>(var x)` trong mẫu.** Dấu `<>` dùng với `new Box<>(...)`, còn cú pháp suy luận record pattern là `Box(var x)`.
3. **Ép `Box<String>` lên dữ liệu `Object` chỉ vì giá trị thử nghiệm là chuỗi.** Type erasure ngăn kiểm tra tham số generic theo cách này. Dùng `Box(String x)` nếu mục tiêu là kiểm tra giá trị thành phần kiểu `String`.
4. **Nhầm tính bất biến của generic.** `Box<Integer>` không phải kiểu con của `Box<Number>`. Nếu chỉ cần đọc số ở nhiều kiểu con, cân nhắc `Box<? extends Number>`.
5. **Lẫn kiểu record với kiểu thành phần.** `Box(String x)` có thể kiểm tra thành phần là `String`, nhưng không biến mọi `Box<?>` thành `Box<String>`.
6. **Quên kiểm tra `null`.** Mẫu `Box(var value)` có thể ràng buộc `value == null`. Với mẫu lồng nhau, một thành phần record ở tầng ngoài bằng `null` khiến mẫu record tầng trong không khớp.
7. **Suy luận quá mạnh từ wildcard.** `Box<? extends Number>` chỉ cho phép dùng giá trị như `Number`; giá trị cụ thể có thể là nhiều kiểu con.
8. **Dùng JDK trước Java 21 mà không xét preview.** Các ví dụ trong bài sử dụng cú pháp chuẩn Java 21, nên hãy kiểm tra `javac -version` và `java -version`.

## 8. Cách chọn mẫu khi thiết kế mã

| Nhu cầu | Cách diễn đạt | Lý do |
| --- | --- | --- |
| Biến đã khai báo `Box<String>` và cần lấy chuỗi | `Box(var text)` | Suy luận được kiểu từ ngữ cảnh, ít lặp lại |
| Muốn type argument của pattern hiển thị rõ | `Box<String>(var text)` khi hợp lệ | Giữ thông tin generic trong mã nguồn |
| Biến là `Object`; cần kiểm tra thành phần chuỗi | `Box(String text)` | Kiểm tra thành phần thay vì thử đoán generic runtime |
| Muốn xử lý mọi loại `Box` | `Box(var value)`, thao tác như `Object` | Không đưa ra giả định kiểu hẹp hơn |
| Record generic lồng nhau | `Parcel(var id, Box(var text))` | Kiểu suy luận truyền qua khai báo các thành phần |
| Chỉ biết thành phần là một kiểu số | `Box(var number)` với `Box<? extends Number>` | Bảo toàn giới hạn kiểu do API khai báo |

## 9. Bài tập thực hành và câu hỏi tự kiểm tra

**Bài 1 — Dự đoán kiểu.** Với `Pair<String, Long> pair`, viết `pair instanceof Pair(var label, var count)`. Kiểu của `label` là gì? Kiểu của `count` là gì? Đáp án: `String` và `Long`.

**Bài 2 — Suy luận xuyên hai tầng.** Với `Parcel<Integer> parcel` và khai báo `record Parcel<T>(String id, Box<T> content)`, biến `payload` trong `Parcel(var id, Box(var payload))` có thể được gán cho kiểu nào? Đáp án: `Integer`, miễn là mẫu lồng nhau khớp; nếu `content == null` thì không vào nhánh.

**Bài 3 — Nhận biết lỗi.** Tại sao đoạn `Object value = new Box<>("hello"); if (value instanceof Box<String>(var text)) { ... }` không được chấp nhận? Đáp án: không có phép kiểm tra runtime an toàn cho type argument `String` trên đối tượng chỉ được khai báo là `Object`. Thay bằng `Box(String text)` nếu mục tiêu là kiểm tra kiểu thành phần.

**Bài 4 — Dữ liệu thiếu.** Với `Box<String> box = new Box<>(null)`, `box instanceof Box(var text)` có khớp không? Đáp án: **có**; `text` được suy ra kiểu `String` nhưng giá trị có thể là `null`. Hãy thêm `text != null` trước khi gọi phương thức trên chuỗi.

**Bài 5 — Giới hạn kiểu.** Vì sao `Box<? extends Number>` dùng được `Number n = value` trong mẫu `Box(var value)` nhưng không thể luôn viết `Integer n = value`? Đáp án: wildcard chỉ bảo đảm kiểu con của `Number`, không bảo đảm chính xác `Integer`.

**Ghi nhớ:** Suy luận type argument trong generic record pattern là **cơ chế của trình biên dịch** dựa trên kiểu tĩnh của biểu thức và khai báo các thành phần record. Nó kết hợp tự nhiên với `var` và nested record patterns để giảm phần kiểu lặp lại, trong khi vẫn phải tuân theo type erasure, giới hạn wildcard và quy tắc khớp `null`.

**Tài liệu chính thức:** [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [Java Language Specification 21 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
