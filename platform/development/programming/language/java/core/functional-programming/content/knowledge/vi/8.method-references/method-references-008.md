# Chọn phương thức nạp chồng theo kiểu đích trong method reference Java

Một **method reference** là biểu thức tham chiếu đến một phương thức đã có, dùng cú pháp `::` để cung cấp phần triển khai cho **functional interface**. Khi tên phương thức được **nạp chồng (overload)**, Java phải xác định phiên bản nào tương thích với **kiểu đích (target type)** ở ngữ cảnh sử dụng.

Ví dụ, nếu có hai phương thức `render(String)` và `render(int)`, biểu thức `Codec::render` chưa tự xác định sẽ chọn phương thức nào. Kiểu đích như `Function<String, String>` hay `IntFunction<String>` cung cấp chữ ký functional method để compiler kiểm tra và chọn overload phù hợp.

**Điểm mấu chốt:** lựa chọn overload của method reference được thực hiện **khi biên dịch**, dựa trên kiểu đích, kiểu đối số, dạng tham chiếu và các quy tắc chọn phương thức của Java. Nó không chọn lại tùy ý theo kiểu runtime của từng đối số khi gọi functional method.

Bài học này giúp bạn:
- Giải thích vì sao cùng `Type::method` có thể trỏ đến các overload khác nhau trong những target types khác nhau.
- Phân biệt tham chiếu phương thức `ClassName::staticMethod`, `receiver::instanceMethod`, `ClassName::instanceMethod` và `ClassName::new`.
- Đọc đúng chữ ký SAM để dự đoán overload được chọn.
- Nhận diện lỗi *ambiguous method reference*, *ambiguous method call* và tham chiếu thiếu target type.
- Sử dụng biến có kiểu rõ ràng, cast có mục đích hoặc lambda tường minh để giải quyết mơ hồ.

## 1. Kiểu đích xác định hợp đồng mà method reference phải đáp ứng

Xét functional interface `Function<T,R>` trong `java.util.function`. Nó có một phương thức trừu tượng:

```java
R apply(T input);
```

Đây là **chữ ký minh họa**, không phải một chương trình Java độc lập. Khi khai báo:

```java
java.util.function.Function<String, String> f = Codec::render;
```

compiler hiểu target type là `Function<String,String>`, tương đương một hợp đồng nhận `String` và trả `String`. Nó cần tìm một phương thức tên `render` trên `Codec` mà kiểu đầu vào và đầu ra phù hợp với target type ấy. Nếu `Codec` có overload `render(String)` và `render(int)`, overload `render(String)` được chọn.

Ngược lại:

```java
java.util.function.IntFunction<String> g = Codec::render;
```

`IntFunction<String>` có functional method `String apply(int value)`, nên overload `render(int)` phù hợp.

Hai dòng trên là mảnh mã minh họa với class `Codec` được định nghĩa ở ví dụ hoàn chỉnh tiếp theo.

**Method reference là poly expression:** nó thường cần một functional interface làm target type từ phép gán, tham số phương thức, câu lệnh `return` hoặc cast. Tên phương thức ở phía phải `::` chưa đủ để quyết định toàn bộ kiểu biểu thức.

## 2. Ví dụ Java 17: cùng method reference, hai overload được chọn

Lưu vào tệp **`StaticOverloadReferenceDemo.java`**:

```java
import java.util.function.Function;
import java.util.function.IntFunction;

class Codec {
    static String render(String text) {
        return "String:" + text;
    }

    static String render(int number) {
        return "int:" + number;
    }
}

public class StaticOverloadReferenceDemo {
    public static void main(String[] args) {
        Function<String, String> textRenderer = Codec::render;
        IntFunction<String> numberRenderer = Codec::render;

        System.out.println(textRenderer.apply("Java"));
        System.out.println(numberRenderer.apply(7));

        // Lambda tường minh cho cùng lựa chọn ở trường hợp String.
        Function<String, String> explicit = text -> Codec.render(text);
        System.out.println(explicit.apply("Lambda"));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 StaticOverloadReferenceDemo.java
java StaticOverloadReferenceDemo
```

**Stdout chính xác:**

```text
String:Java
int:7
String:Lambda
```

Giải thích từng dòng:

1. `textRenderer` có target type `Function<String,String>`; functional method nhận `String`, nên chọn `Codec.render(String)`.
2. `numberRenderer` có target type `IntFunction<String>`; functional method nhận `int`, nên chọn `Codec.render(int)`.
3. Lambda `text -> Codec.render(text)` có `text` suy luận là `String`, do đó lời gọi `render(text)` cũng chọn overload nhận `String`.

Dù mã dùng chung cú pháp `Codec::render`, hai phép gán tạo ra các đối tượng chức năng với hợp đồng khác nhau. Thực tế việc gọi `apply` sau này tuân thủ functional method của từng interface.

## 3. Đọc đúng chữ ký của functional method

Để quyết định overload, trước tiên hãy viết ra chữ ký SAM của kiểu đích, không suy luận theo tên biến:

| Target type | Chữ ký functional method | Hình thức đầu vào mà phương thức được tham chiếu phải phù hợp |
| --- | --- | --- |
| `Function<String,String>` | `String apply(String x)` | Một `String`, kết quả chuyển được sang `String`. |
| `IntFunction<String>` | `String apply(int x)` | Một `int`, trả `String`. |
| `BiFunction<String,Integer,String>` | `String apply(String x,Integer y)` | Hai tham số phù hợp sau khi xét quy tắc chuyển đổi kiểu. |
| `Supplier<String>` | `String get()` | Không tham số, trả `String`. |
| `Consumer<String>` | `void accept(String x)` | Một tham số; phép tham chiếu phải phù hợp với hợp đồng trả `void`. |

Các chữ ký được viết đơn giản hóa để dễ đọc. Functional method của generic interface thực tế trải qua thay thế tham số kiểu và quy tắc tương thích theo Java Language Specification.

**Không lựa chọn chỉ dựa trên số lượng tham số.** Nếu có `render(String)` và `render(int)`, cả hai đều nhận một tham số, nhưng target type phân biệt chúng nhờ kiểu đối số. Nếu có nhiều phương thức cùng phù hợp, Java tiếp tục áp dụng quy tắc tìm phương thức áp dụng được và chọn phương thức cụ thể nhất (*most specific*), có xét chuyển đổi kiểu, generic và các điều kiện tương thích liên quan.

Giá trị trả về cũng phải phù hợp với functional method; checked exceptions không được phép cũng có thể làm phép tham chiếu không hợp lệ. Tuy nhiên, **Java không cho nạp chồng hai phương thức chỉ khác kiểu trả về** với cùng danh sách tham số. Return type không phải một cơ chế để khai báo overload chỉ theo kết quả.

## 4. Bốn dạng method reference và vai trò tham số receiver

| Cú pháp | Ý nghĩa | Cách đối chiếu với SAM |
| --- | --- | --- |
| `Type::staticMethod` | Tham chiếu static method | Đối số của SAM cung cấp đối số của static method. |
| `receiver::instanceMethod` | Tham chiếu tới instance method trên một receiver đã xác định | Receiver đã được cố định; đối số SAM cung cấp các đối số còn lại. |
| `Type::instanceMethod` | Tham chiếu instance method không gắn receiver | Thường đối số đầu tiên của SAM là receiver; các đối số sau truyền cho method. |
| `Type::new` | Constructor reference | Chọn constructor phù hợp với chữ ký SAM. |

Đây là sơ đồ tư duy dành cho những trường hợp thông dụng. Với `Type::name`, Java còn phải xem dạng tìm kiếm static hoặc instance theo quy tắc JLS; nếu phương thức nạp chồng và có khả năng khớp nhiều dạng, cần kiểm tra chính xác kiểu đích và kết quả biên dịch. Đừng luôn giả định `Type::name` chỉ có thể là static.

Đặc biệt, `receiver::method` giữ receiver do bạn cung cấp khi **tạo method reference**; còn `Type::instanceMethod` không có receiver cố định và cần nhận nó qua lời gọi functional method.

## 5. Ví dụ Java 17: overload trên instance method

Lưu thành **`InstanceOverloadReferenceDemo.java`**:

```java
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.IntFunction;

class Labeler {
    String mark(String text) {
        return "Text:" + text;
    }

    String mark(int number) {
        return "Number:" + number;
    }
}

public class InstanceOverloadReferenceDemo {
    public static void main(String[] args) {
        Labeler labeler = new Labeler();

        // Bound reference: receiver labeler đã cố định.
        Function<String, String> text = labeler::mark;
        IntFunction<String> number = labeler::mark;

        // Unbound reference: Labeler là tham số đầu tiên của SAM.
        BiFunction<Labeler, String, String> unbound = Labeler::mark;

        System.out.println(text.apply("Hello"));
        System.out.println(number.apply(12));
        System.out.println(unbound.apply(labeler, "Java"));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 InstanceOverloadReferenceDemo.java
java InstanceOverloadReferenceDemo
```

**Stdout chính xác:**

```text
Text:Hello
Number:12
Text:Java
```

Với `labeler::mark`, target `Function<String,String>` chọn `mark(String)`, target `IntFunction<String>` chọn `mark(int)`. Với `Labeler::mark`, functional method của `BiFunction<Labeler,String,String>` có hai đối số: `Labeler` làm receiver và `String` làm đối số cho `mark(String)`.

Nếu viết `BiFunction<Labeler,Integer,String> intUnbound = Labeler::mark;`, compiler có thể sử dụng unboxing `Integer` thành `int` để khớp overload `mark(int)`; đây là ví dụ về vai trò của quy tắc chuyển đổi kiểu khi so khớp, dù hai chữ ký không giống nhau từng ký tự.

## 6. Constructor reference cũng chọn overload theo target type

Constructor của một class có thể được nạp chồng. `ClassName::new` sử dụng chữ ký functional method để chọn constructor có danh sách tham số phù hợp.

Ví dụ đầy đủ, lưu thành **`ConstructorOverloadReferenceDemo.java`**:

```java
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.Supplier;

record Entry(String name, int score) {
    Entry() {
        this("unknown", 0);
    }

    Entry(String name) {
        this(name, 0);
    }
}

public class ConstructorOverloadReferenceDemo {
    public static void main(String[] args) {
        Supplier<Entry> noArgs = Entry::new;
        Function<String, Entry> oneArg = Entry::new;
        BiFunction<String, Integer, Entry> twoArgs = Entry::new;

        Entry a = noArgs.get();
        Entry b = oneArg.apply("Lan");
        Entry c = twoArgs.apply("Mai", 9);

        System.out.println(a.name() + ":" + a.score());
        System.out.println(b.name() + ":" + b.score());
        System.out.println(c.name() + ":" + c.score());
    }
}
```

Biên dịch/chạy trên Java 17:

```bash
javac -encoding UTF-8 ConstructorOverloadReferenceDemo.java
java ConstructorOverloadReferenceDemo
```

**Stdout chính xác:**

```text
unknown:0
Lan:0
Mai:9
```

- `Supplier<Entry>` có `get()` không đối số, chọn constructor `Entry()`.
- `Function<String,Entry>` có `apply(String)`, chọn `Entry(String)`.
- `BiFunction<String,Integer,Entry>` có `apply(String,Integer)`; tham số thứ hai được unbox thành `int` để gọi constructor canonical `Entry(String,int)`.

Ví dụ dùng `record`, chính thức được hỗ trợ từ Java 16. `Entry` là record package-private trong cùng tệp nguồn với public class demo.

## 7. Khi overload của phương thức nhận method reference làm lời gọi bị mơ hồ

Có **hai tầng overload** cần phân biệt:

1. **Overload của phương thức được tham chiếu**, ví dụ `Renderer.show(String)` và `Renderer.show(int)`.
2. **Overload của phương thức nhận đối số functional interface**, ví dụ `accept(Function<String,String>)` và `accept(IntFunction<String>)`.

Ngay cả khi mỗi target type riêng rẽ chọn được overload `show` rất rõ, compiler vẫn có thể không chọn được overload `accept` khi đối số chỉ là `Renderer::show` mà không có ngữ cảnh đủ để phân biệt hai overload nhận.

Ví dụ **cố ý không biên dịch**, chỉ để thấy vấn đề:

```java
// Giả sử Renderer có static show(String) và show(int).
// Giả sử accept được overload cho Function<String,String> và IntFunction<String>.
accept(Renderer::show); // có thể lỗi: ambiguous method call
```

Không nên dùng cách “đợi đến runtime biết giá trị” để giải quyết: tại thời điểm biên dịch, đối số method reference có thể phù hợp nhiều chữ ký và compiler phải chọn lời gọi `accept` theo quy tắc overload resolution.

### Ví dụ Java 17 hoàn chỉnh: thêm target type để giải quyết mơ hồ

Lưu thành **`OverloadedReceiverDemo.java`**:

```java
import java.util.function.Function;
import java.util.function.IntFunction;

class Renderer {
    static String show(String text) {
        return "S:" + text;
    }

    static String show(int value) {
        return "N:" + value;
    }
}

public class OverloadedReceiverDemo {
    static void accept(Function<String, String> handler) {
        System.out.println("string -> " + handler.apply("Java"));
    }

    static void accept(IntFunction<String> handler) {
        System.out.println("int -> " + handler.apply(5));
    }

    public static void main(String[] args) {
        // accept(Renderer::show); // CỐ Ý KHÔNG BIÊN DỊCH: ambiguous

        // Cast tạo target type cho method reference và chọn overload accept.
        accept((Function<String, String>) Renderer::show);
        accept((IntFunction<String>) Renderer::show);

        // Hoặc đặt trong biến với kiểu được khai báo rõ ràng.
        Function<String, String> selected = Renderer::show;
        accept(selected);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 OverloadedReceiverDemo.java
java OverloadedReceiverDemo
```

**Stdout chính xác:**

```text
string -> S:Java
int -> N:5
string -> S:Java
```

Dòng `accept(Renderer::show)` được **để dưới dạng comment** để chương trình hoàn chỉnh vẫn chạy được. Dòng đó gây mơ hồ vì cả hai overload `accept` đều là ứng viên thích hợp: một nhận chức năng `String -> String`, một nhận `int -> String`.

Cast hoặc biến có kiểu rõ ràng giải quyết ở hai cấp: chọn target type cho `Renderer::show`, đồng thời chọn overload `accept` tương ứng. Cách này cũng giúp người đọc hiểu chính xác ý định API.

## 8. Method reference cần target type, không tự tạo kiểu bằng var

Không thể yêu cầu `var` tự suy luận functional interface từ method reference đứng riêng:

```java
// CỐ Ý SAI: method reference không có target type.
var f = Renderer::show;

// CỐ Ý SAI: Object không phải functional interface.
Object f2 = Renderer::show;
```

`var` cần biểu thức khởi tạo đã có kiểu xác định; method reference thường là poly expression cần target type. Kiểu `Object` không khai báo functional method, nên nó cũng không phải target type phù hợp.

Các cách hợp lệ:

```java
java.util.function.Function<String, String> f = Renderer::show;
var inferred = f;
var explicitlyTyped = (java.util.function.IntFunction<String>) Renderer::show;
```

Đây là **mảnh mã minh họa**, `Renderer` cần có khai báo phương thức như ở chương trình đầy đủ bên trên. `inferred` nhận kiểu của biến `f`, còn cast làm rõ target type cho `explicitlyTyped`. Cả hai cách đều có nguồn thông tin kiểu hợp lệ.

## 9. Trường hợp một target type vẫn chưa đủ: nhiều overload cùng áp dụng được

Không phải cứ có target type là mọi method reference đều hợp lệ. Nếu nhiều overload của chính phương thức được tham chiếu cùng áp dụng được mà quy tắc chọn phương thức cụ thể nhất không phân biệt được, **method reference vẫn mơ hồ**.

Ví dụ **cố ý không biên dịch**:

```java
class Ambiguous {
    static String choose(CharSequence value) {
        return "text";
    }

    static String choose(java.io.Serializable value) {
        return "serializable";
    }
}

// String đồng thời implements CharSequence và Serializable.
java.util.function.Function<String, String> f = Ambiguous::choose;
// Lỗi: không có overload rõ ràng cụ thể hơn giữa hai tham số trên.
```

Trong ví dụ này, target type cho biết đầu vào của SAM là `String`. Nhưng `String` có thể chuyển sang cả `CharSequence` và `Serializable`; hai kiểu này không có quan hệ subtype trực tiếp quyết định một overload cụ thể hơn, nên phép tham chiếu không chọn duy nhất được.

Nếu nghiệp vụ cần một trong hai overload, có thể viết lambda với cast **ở đối số lời gọi method**:

```java
java.util.function.Function<String, String> chooseText =
        value -> Ambiguous.choose((CharSequence) value);
```

Ở đây lời gọi bên trong lambda nhận đối số kiểu `CharSequence`, nên compiler chọn `choose(CharSequence)`. Khác với việc chỉ cast **bản thân method reference** sang `Function<String,String>`: target type khi đó vẫn nhận `String`, nên có thể vẫn mơ hồ.

**Điểm cần phân biệt:** trong phần 7, *overload của phương thức nhận callback* gây mơ hồ, dù mỗi target riêng có thể chọn method được tham chiếu. Ở phần này, chỉ có **một** target type, nhưng *overload của phương thức được tham chiếu* tự nó mơ hồ.

## 10. Chuyển đổi kiểu, generic và giá trị trả về

Java không chỉ so sánh chữ ký một cách máy móc theo tên kiểu. Khi kiểm tra method reference, compiler còn xét các quy tắc liên quan đến:

- **Widening primitive** trong những ngữ cảnh áp dụng được, chẳng hạn `int` sang `long`.
- **Boxing/unboxing**, chẳng hạn `Integer` với `int`.
- **Widening reference**, ví dụ `String` sang `CharSequence`.
- **Generic methods** và type inference, nếu phương thức được tham chiếu có type parameters.
- **Varargs** và các giai đoạn tìm phương thức áp dụng được.
- **Return compatibility** với functional method, cùng giới hạn checked exceptions.

Trong các trường hợp phức tạp, không nên dùng khẩu quyết “luôn ưu tiên kiểu nguyên thủy” hoặc “luôn ưu tiên exact match” thay cho quy tắc chính thức. Quá trình overload resolution của Java có thứ tự các giai đoạn áp dụng và khái niệm *most specific*; lựa chọn thực tế phụ thuộc đầy đủ chữ ký và ngữ cảnh target.

Ví dụ dùng generics:

```java
java.util.function.UnaryOperator<String> trim = String::trim;
java.util.function.Function<String, Integer> length = String::length;
```

Hai method references này hợp lệ vì target types cung cấp kiểu receiver và kết quả cần thiết. Đoạn minh họa chỉ nhằm giải thích target typing, không phải hai overload của cùng một tên.

**Giá trị trả về không phải lúc nào cũng được yêu cầu theo cách giống nhau.** Các functional methods trả `void` có quy tắc tương thích riêng, vì vậy đừng kết luận một method reference không hợp lệ chỉ vì phương thức bên dưới có kiểu trả về giá trị; cần kiểm tra quy tắc thích ứng return đối với loại target ấy.

## 11. Quy trình đọc lỗi và chọn overload đúng

Khi một tham chiếu như `Service::convert` không biên dịch, làm lần lượt:

1. **Viết kiểu đích rõ ràng:** ví dụ `Function<String,Integer>`, không để `var` hoặc overload của caller che khuất ngữ cảnh.
2. **Ghi chữ ký functional method:** số tham số, kiểu tham số, kiểu trả về và checked exceptions.
3. **Xác định dạng reference:** static, bound instance, unbound instance hoặc constructor; với unbound instance, chú ý tham số receiver đầu tiên của SAM.
4. **Liệt kê các overload phù hợp của tên phương thức** trong đúng class (và phương thức được kế thừa có thể áp dụng).
5. **Xét chuyển đổi kiểu và most-specific:** phân biệt overload không áp dụng, một overload duy nhất áp dụng, hay nhiều overload mơ hồ.
6. **Xem caller có nạp chồng hay không:** hai overload của phương thức nhận callback có thể cùng phù hợp với method reference.
7. **Làm rõ ý định:** dùng biến functional interface có kiểu tường minh, cast đến functional interface hoặc lambda gọi trực tiếp một overload qua đối số được cast khi cần.
8. **Biên dịch lại** và kiểm tra unit test đại diện cho nhánh `String`, `int` hoặc loại thực sự cần.

Nếu lambda tường minh làm code dễ đọc hơn, dùng nó là hợp lý. Method reference không bắt buộc phải được sử dụng trong mọi hoàn cảnh; mục tiêu là giữ rõ hợp đồng kiểu và tính đúng đắn.

## 12. Những ngộ nhận phổ biến

1. **“Tên method reference tự quyết định overload.”** Sai. `Codec::render` cần target type để biết hình thức lời gọi phù hợp.
2. **“Overload được chọn theo object runtime.”** Sai trong trường hợp overload resolution thông thường; kiểu compile-time của các đối số và target type quyết định overload. Phân phối động của overridden instance method là một cơ chế khác.
3. **“Một target type thì luôn hết mơ hồ.”** Sai. Nhiều overload cùng áp dụng có thể không có phương thức cụ thể nhất duy nhất.
4. **“Method reference luôn tương đương việc lấy địa chỉ một method cố định, không cần ngữ cảnh.”** Sai. Nó là poly expression trong nhiều ngữ cảnh và cần target type để giải nghĩa.
5. **“String::method luôn là static reference.”** Sai. Nó có thể là tham chiếu instance method không gắn receiver tùy chữ ký và quy tắc phù hợp.
6. **“receiver::method và Type::method nhận số đối số SAM như nhau.”** Sai trong trường hợp unbound instance: SAM còn nhận receiver làm đối số đầu tiên.
7. **“Nạp chồng chỉ dựa vào số tham số.”** Sai. Kiểu tham số, generic và chuyển đổi cũng quan trọng.
8. **“Đổi kiểu trả về là đủ để overload method.”** Sai. Java không cho hai method chỉ khác return type với cùng danh sách tham số.
9. **“Cast tới Function luôn giải quyết được mọi ambiguity.”** Sai. Cast giải quyết thiếu target type hoặc overload caller; nếu method được tham chiếu tự mơ hồ trong target ấy, cần làm rõ lời gọi.
10. **“var f = Type::method sẽ tự đoán interface hợp lý.”** Sai. `var` không tự tạo target type từ method reference.

## 13. Tự kiểm tra

**Câu 1.** `Codec` có `render(String)` và `render(int)`. Dòng nào chọn overload `int`?

```java
java.util.function.Function<String, String> a = Codec::render;
java.util.function.IntFunction<String> b = Codec::render;
```

**Đáp án:** `b`, vì functional method của `IntFunction<String>` nhận `int`.

**Câu 2.** Khi viết `BiFunction<Labeler,String,String> f = Labeler::mark;`, đối số đầu tiên của `f.apply(...)` đóng vai trò gì?

**Đáp án:** Là receiver `Labeler` để gọi instance method `mark`; đối số `String` thứ hai truyền vào method.

**Câu 3.** Vì sao `accept(Renderer::show)` có thể mơ hồ khi `accept` có hai overload nhận `Function<String,String>` và `IntFunction<String>`?

**Đáp án:** Cả hai target types đều có method reference phù hợp, và Java cần chọn duy nhất overload của `accept`. Cast method reference sang interface mong muốn hoặc đưa vào một biến có kiểu tường minh.

**Câu 4.** `Supplier<Entry> f = Entry::new` chọn constructor nào khi `Entry` có 0, 1 và 2 tham số?

**Đáp án:** Constructor không tham số `Entry()`, bởi functional method `get()` không có đối số.

**Câu 5.** Nếu `Ambiguous.choose(CharSequence)` và `Ambiguous.choose(Serializable)` cùng có mặt, tại sao `Function<String,String> f = Ambiguous::choose` có thể bị từ chối?

**Đáp án:** `String` tương thích với cả hai kiểu tham số mà không có overload cụ thể nhất duy nhất. Target type đã rõ, nhưng phương thức bên dưới vẫn mơ hồ.

**Câu 6.** Cách nhanh để phân biệt lỗi từ phương thức được tham chiếu và lỗi overload của caller là gì?

**Đáp án:** Gán method reference cho một biến functional interface có kiểu tường minh. Nếu phép gán đã lỗi, xem chữ ký và overload của method được tham chiếu. Nếu phép gán đúng nhưng truyền trực tiếp vào phương thức overload bị lỗi, xem các overload của caller và cách chọn target type.

**Ghi nhớ:** Với method reference nạp chồng, hãy bắt đầu từ **chữ ký functional method của kiểu đích**, xác định receiver và đối số, sau đó áp dụng quy tắc overload của Java. Kiểu đích làm rõ overload trong nhiều trường hợp, nhưng không loại bỏ mọi ambiguity khi có nhiều ứng viên cùng phù hợp.
