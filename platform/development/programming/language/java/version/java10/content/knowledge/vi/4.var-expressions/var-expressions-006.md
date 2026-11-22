# Java 10 — Lambda và tham chiếu phương thức khi không có kiểu đích với `var`

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích vì sao `var action = x -> x + 1;` và `var action = String::trim;` **không biên dịch được**, dù lambda và method reference là cú pháp Java hợp lệ.
- Nhận ra **kiểu đích (target type)** trong phép gán, lời gọi phương thức, câu lệnh `return`, phép ép kiểu; từ đó chọn functional interface thích hợp.
- Dùng `var` đúng với các kết quả **đã có kiểu tĩnh**, chẳng hạn giá trị trả về của factory hoặc phương thức nhận lambda làm đối số.
- Phân biệt `var` cho biến cục bộ (Java 10) với `var` viết trong danh sách tham số lambda (Java 11), tránh suy luận sai rằng thay đổi sau đã loại bỏ nhu cầu về kiểu đích.
- Đọc lỗi biên dịch và sửa code mà không phải dùng `Object` hoặc ép kiểu tùy tiện.

**Phạm vi:** các quy tắc ngôn ngữ Java chính thức vẫn áp dụng ở các JDK hiện đại, cùng thư viện `java.util.function`. Lambda và method reference được giới thiệu ở Java 8; **tương tác với `var` là phần cần hiểu khi học Java 10**.

## 1. Ba khái niệm then chốt

### 1.1. Functional interface và chữ ký hàm (SAM)

Lambda và method reference được gán cho **functional interface**: interface có đúng một phương thức trừu tượng theo quy tắc của Java. Các phương thức tương ứng với `Object` không làm tăng số lượng phương thức trừu tượng cần triển khai. Annotation `@FunctionalInterface` giúp trình biên dịch kiểm tra ý định, nhưng không bắt buộc để một interface đủ điều kiện.

Các kiểu thường dùng:

| Functional interface | Phương thức trừu tượng | Ví dụ chức năng |
|---|---|---|
| `Function<T, R>` | `R apply(T value)` | Chuyển `String` thành `Integer` |
| `UnaryOperator<T>` | `T apply(T value)` | Biến đổi giá trị giữ nguyên kiểu |
| `Predicate<T>` | `boolean test(T value)` | Kiểm tra điều kiện |
| `Consumer<T>` | `void accept(T value)` | Xử lý giá trị nhưng không trả kết quả |
| `Supplier<T>` | `T get()` | Tạo/cung cấp giá trị, không nhận đối số |
| `Runnable` | `void run()` | Thực hiện tác vụ không nhận đối số |
| `IntUnaryOperator` | `int applyAsInt(int value)` | Biến đổi `int` không cần boxing |

Ví dụ, khai báo `Function<String, Integer> length = s -> s.length();` cho trình biên dịch biết đầu vào của `s` là `String` và kết quả cần tương thích `Integer` (giá trị `int` từ `length()` được boxing). Kiểu đích quyết định cách kiểm tra lambda.

### 1.2. Lambda và method reference là *poly expression*

Hai biểu thức này được ngôn ngữ Java phân loại là **poly expression**: để xác định chúng có hợp lệ hay không và chúng tương ứng với kiểu nào, trình biên dịch cần ngữ cảnh cung cấp **target type**.

```java
Function<String, String> clean = text -> text.trim();
Function<String, String> cleanAgain = String::trim;
```

Đây là **hai mảnh mã minh họa**, cần `import java.util.function.Function;` và đặt trong phạm vi khai báo hợp lệ. Trong cả hai:

1. Vế trái cung cấp `Function<String, String>`.
2. Phương thức trừu tượng là `String apply(String)`.
3. Lambda `text -> text.trim()` được kiểm tra với `text` có kiểu `String`.
4. `String::trim` được ánh xạ thành thao tác nhận một `String` rồi gọi `trim()` trên đối tượng đó.

**Bản thân `text -> text.trim()` không có một “kiểu lambda chung” độc lập để trình biên dịch tự đặt tên.** Tương tự, `String::trim` là cú pháp mô tả cách gọi phương thức, không tự trở thành `Function<String, String>` nếu không có đích phù hợp.

### 1.3. `var` cần kiểu suy ra được từ initializer

`var` của Java 10 là **suy luận kiểu biến cục bộ** tại thời điểm biên dịch (JEP 286). Với `var value = expression;`, trình biên dịch lấy kiểu từ biểu thức khởi tạo rồi gán kiểu tĩnh đó cho biến. Nó không chọn ngẫu nhiên một functional interface phù hợp với lambda và cũng không dùng các phép gán ở dòng sau để đoán lại kiểu.

```java
var count = 5;                             // int
var title = "Java";                        // String
var numbers = java.util.List.of(1, 2, 3); // List<Integer>
```

Những initializer này tự cung cấp kiểu có thể suy ra. Ngược lại, một lambda hoặc method reference **đứng trực tiếp ở vế phải của `var`** thiếu ngữ cảnh để có kiểu đích.

## 2. Các lỗi đúng trọng tâm: lambda/method reference không có target type

Những đoạn dưới đây là **ví dụ lỗi biên dịch có chủ đích; không gộp chúng vào chương trình chạy được**:

```java
// Sai: trình biên dịch không thể suy ra functional interface cho lambda.
var doubleValue = n -> n * 2;

// Sai: viết rõ kiểu tham số cũng không xác định target interface.
var clean = (String s) -> s.trim();

// Sai: method reference cần functional interface đích.
var trim = String::trim;

// Sai: thêm var vào THAM SỐ lambda không tạo target type cho cả lambda.
var cleanAgain = (var s) -> s.trim();

// Sai: Object không phải một functional interface.
Object any = String::trim;
```

Thông báo thường gặp của `javac`/JShell có ý nghĩa tương đương:

```text
cannot infer type for local variable ...
  (lambda expression needs an explicit target-type)

cannot infer type for local variable ...
  (method reference needs an explicit target-type)
```

Nội dung chính xác, số dòng và vị trí dấu mũ của chẩn đoán có thể thay đổi theo JDK/IDE; **quy tắc bị vi phạm là không có kiểu đích của functional interface**.

Vì sao `(String s) -> s.trim()` vẫn sai với `var`? Dù đầu vào đã rõ là `String` và thân lambda trả `String`, vẫn còn nhiều functional interface có thể tương thích, chẳng hạn `Function<String, String>`, `UnaryOperator<String>` hoặc interface tự định nghĩa. Trình biên dịch không tự chọn thay người viết.

Thêm ngoặc đơn như `var fn = (String::trim);`, hay đặt lambda vào một phép gán cho `Object`, không tạo ra target type phù hợp. Muốn dùng lambda hoặc method reference, hãy **cung cấp functional interface ở một ngữ cảnh được Java hỗ trợ**.

## 3. Nguồn của kiểu đích: các ngữ cảnh hợp lệ

| Ngữ cảnh | Ví dụ hợp lệ | Kiểu đích đến từ đâu? |
|---|---|---|
| Khai báo biến tường minh | `UnaryOperator<String> op = String::trim;` | Kiểu biến `UnaryOperator<String>` |
| Gán cho biến đã khai báo | `op = s -> s.strip();` | Kiểu đã có của `op`; giả sử `op` là `UnaryOperator<String>` |
| Đối số phương thức | `applyText(" Hi ", String::trim);` | Kiểu tham số nhận hàm của `applyText` |
| Trả về từ phương thức | `return String::trim;` | Kiểu trả về được khai báo là một functional interface |
| Ép kiểu tường minh | `(UnaryOperator<String>) String::trim` | Target type trong phép cast |
| Toán tử điều kiện có ngữ cảnh | `UnaryOperator<String> op = flag ? String::trim : String::toUpperCase;` | Kiểu của biến bên trái truyền vào các nhánh |
| Biểu thức truyền qua hàm | `var result = applyText(" Hi ", String::trim);` | Lambda/ref lấy kiểu từ tham số phương thức; `var` lấy **kiểu trả về** |

Các mẫu chứa `op`, `flag` hay `applyText` là mảnh minh họa phải được khai báo phù hợp ở chương trình sử dụng.

Điểm đáng nhớ ở hàng cuối: **`var` có thể đứng ở vế trái của một lời gọi chứa lambda** vì lời gọi đã có kiểu trả về rõ ràng. Điều không hợp lệ là dùng bare lambda/method reference làm initializer trực tiếp mà không có target.

## 4. Cách sửa lỗi và lựa chọn phù hợp

### Cách 1 — Khai báo functional interface tường minh (thường rõ ràng nhất)

```java
IntUnaryOperator doubleValue = n -> n * 2;
UnaryOperator<String> clean = String::trim;
Predicate<String> nonBlank = s -> !s.isBlank();
Supplier<StringBuilder> create = StringBuilder::new;
```

Cần import `java.util.function.IntUnaryOperator`, `UnaryOperator`, `Predicate` và `Supplier`; các dòng này dành để đặt trong method/khối lệnh. `String.isBlank()` xuất hiện từ Java 11, vẫn là API phổ biến trên JDK hiện đại.

Lợi điểm: tên interface bộc lộ **ý nghĩa hợp đồng** — trả kết quả, kiểm tra điều kiện, tạo dữ liệu hay sinh tác dụng phụ. Với người đọc, `IntUnaryOperator` rõ hơn ép cả lambda sang `Object` hoặc một kiểu generic quá rộng.

### Cách 2 — Cast đến functional interface rồi mới dùng `var`

```java
var doubleValue = (IntUnaryOperator) (n -> n * 2);
var clean = (UnaryOperator<String>) String::trim;
```

Hai initializer này hợp lệ vì phép cast cung cấp target type cho lambda/method reference. `var` sau đó suy ra kiểu **`IntUnaryOperator`** và **`UnaryOperator<String>`**, không tạo ra “kiểu var” trong runtime.

Đây là giải pháp khi cần giữ `var` vì một lý do cụ thể; trong mã thông thường, khai báo kiểu interface trực tiếp ở cách 1 thường ít dấu ngoặc và dễ hiểu hơn. Cast cũng không biến một lambda không phù hợp chữ ký thành hợp lệ.

### Cách 3 — Truyền lambda vào phương thức biết trước kiểu tham số

```java
static String applyText(String source, UnaryOperator<String> transform) {
    return transform.apply(source);
}

// Bên trong một phương thức khác:
var text = applyText("  Java  ", String::trim);
```

`String::trim` có target type `UnaryOperator<String>` từ tham số thứ hai; `text` được suy ra là `String` từ kiểu trả về của `applyText`.

### Cách 4 — Lấy một functional interface đã được trả về có kiểu

```java
static UnaryOperator<String> selectRule(boolean trim) {
    return trim ? String::trim : String::toUpperCase;
}

// Bên trong một phương thức khác:
var rule = selectRule(true);
```

`return`/các nhánh conditional có target type `UnaryOperator<String>` do kiểu trả về của `selectRule`. Sau đó, `var rule` suy ra đúng kiểu interface từ **lời gọi phương thức**. Không tồn tại lambda “không có kiểu đích” trong ví dụ này.

Cần tránh hiểu sai: `var rule = flag ? String::trim : String::toUpperCase;` **không hợp lệ** chỉ vì hai nhánh đều trông giống hàm. Cả hai vẫn cần một target type, ví dụ `UnaryOperator<String> rule = flag ? String::trim : String::toUpperCase;`.

## 5. Ví dụ Java 17+ hoàn chỉnh, biên dịch và chạy được

Tệp: **`TargetTypingDemo.java`**

```java
import java.util.function.Function;
import java.util.function.IntUnaryOperator;
import java.util.function.Supplier;
import java.util.function.UnaryOperator;

public class TargetTypingDemo {
    // Kiểu trả về cho phép biên dịch cả hai method references.
    static UnaryOperator<String> choose(boolean trim) {
        return trim ? String::trim : String::toUpperCase;
    }

    // Target type cho tham số fn được biết từ khai báo phương thức.
    static String apply(String text, UnaryOperator<String> fn) {
        return fn.apply(text);
    }

    static UnaryOperator<String> identityString() {
        return value -> value;
    }

    public static void main(String[] args) {
        // Các functional interface cung cấp target type.
        IntUnaryOperator doubleIt = n -> n * 2;
        Function<String, String> trim = String::trim;
        Supplier<StringBuilder> factory = StringBuilder::new;

        // Cast cung cấp target type; var suy ra kiểu từ cast.
        var plusThree = (IntUnaryOperator) (n -> n + 3);
        var viaCast = (UnaryOperator<String>) String::toUpperCase;

        // Kết quả lời gọi đã có kiểu tĩnh; var sử dụng được.
        var viaFactory = choose(false);
        var viaCall = apply("  Java  ", String::trim);
        var viaReturn = identityString();

        System.out.println("double=" + doubleIt.applyAsInt(4));
        System.out.println("trim=[" + trim.apply("  Java  ") + "]");
        System.out.println("factory=" + factory.get().length());
        System.out.println("castLambda=" + plusThree.applyAsInt(4));
        System.out.println("castMethod=" + viaCast.apply("java"));
        System.out.println("factoryFunction=" + viaFactory.apply("java"));
        System.out.println("callResult=[" + viaCall + "]");
        System.out.println("returnFunction=" + viaReturn.apply("ok"));
        System.out.println("conditional=[" + choose(true).apply("  Java  ") + "]");
    }
}
```

Biên dịch bằng JDK 17 trở lên:

```bash
javac --release 17 TargetTypingDemo.java
java TargetTypingDemo
```

**Kết quả stdout:**

```text
double=8
trim=[Java]
factory=0
castLambda=7
castMethod=JAVA
factoryFunction=JAVA
callResult=[Java]
returnFunction=ok
conditional=[Java]
```

**Phân tích theo từng nhóm:**

- `doubleIt` và `trim` có kiểu interface được viết trực tiếp; chúng không dùng `var` để đoán lambda/ref.
- `factory` dùng constructor reference `StringBuilder::new` với đích `Supplier<StringBuilder>`: mỗi lần `get()` có thể tạo một `StringBuilder` mới; builder mới có độ dài bằng 0.
- `plusThree` và `viaCast` hợp lệ vì phép cast cung cấp target type, rồi `var` suy ra kiểu của kết quả cast.
- `viaFactory` có kiểu `UnaryOperator<String>` vì `choose` trả về interface đó; `viaReturn` tương tự.
- `viaCall` có kiểu `String` vì `apply` trả `String`. Method reference trong lời gọi được kiểm tra với tham số `UnaryOperator<String>`.
- `choose(true)` chọn `String::trim`, `choose(false)` chọn `String::toUpperCase`. Hai nhánh được kiểm tra cùng một target type từ kiểu trả về của phương thức.

Tất cả đều là cách dùng API ngôn ngữ ổn định. Không cần preview flag, thư viện bên ngoài, hoặc khai báo module đặc biệt.

## 6. Method reference cần kiểu đích để ghép chữ ký

Method reference không gọi phương thức ngay tại nơi viết; nó mô tả cách gọi sẽ diễn ra khi phương thức trừu tượng của functional interface được gọi. Vì vậy, số lượng và kiểu tham số đầu vào, kiểu trả về, cũng như overload cần chọn phụ thuộc **target functional interface**.

| Dạng | Ví dụ có kiểu đích | Ánh xạ ý nghĩa |
|---|---|---|
| Tham chiếu phương thức static | `Function<String, Integer> parse = Integer::valueOf;` | Nhận `String`, gọi `Integer.valueOf(String)` |
| Tham chiếu method của một đối tượng có sẵn | `Supplier<String> get = "java"::toUpperCase;` | Không nhận đối số, gọi `toUpperCase()` trên chuỗi đã gắn |
| Tham chiếu instance method theo **kiểu** | `Function<String, String> clean = String::trim;` | Tham số `String` trở thành receiver của `trim()` |
| Constructor reference | `Supplier<StringBuilder> make = StringBuilder::new;` | Gọi constructor không đối số |
| Method reference có nhiều overload | `Function<Integer, String> show = String::valueOf;` | Target buộc chữ ký 1 đối số `Integer`, giúp phân giải overload phù hợp |

Ví dụ với `String::trim`, một lập trình viên có thể hình dung tham số ngầm là receiver. Nhưng với các method reference có overload hoặc có constructor nhận tham số, chỉ tên method/constructor không đủ để xác định chữ ký thực sự cần dùng.

**Giới hạn:** Đích phải tương thích về số đối số, kiểu tham số, kiểu trả về và ngoại lệ được khai báo. Nếu chọn functional interface sai, code vẫn lỗi dù đã “bổ sung kiểu đích”.

Ví dụ sai có chủ đích:

```java
Supplier<String> invalid = String::trim; // Không có String receiver
```

`Supplier<String>` có phương thức `get()` không đối số, trong khi `String::trim` dạng unbound instance method cần một `String` làm receiver. Sửa thành `Function<String, String> valid = String::trim;` hoặc, nếu muốn gắn một đối tượng cụ thể, `Supplier<String> valid = " Java "::trim;`.

## 7. Khác biệt quan trọng: `var` ở Java 10 và `var` ở tham số lambda từ Java 11

- **Java 10 / JEP 286:** `var` thay phần khai báo kiểu của **biến cục bộ**, nhưng initializer phải đủ thông tin để có kiểu.
- **Java 11 / JEP 323:** có thể viết `var` ở **tham số của lambda**. Kiểu các tham số lambda vẫn được suy ra từ target functional interface. Việc dùng `var` ở đây **không** tự tạo functional interface cho toàn bộ lambda.

Ví dụ chạy được với JDK 17+ (cú pháp tham số `var` có từ Java 11):

Tệp: **`LambdaParametersDemo.java`**

```java
import java.util.function.Function;

public class LambdaParametersDemo {
    public static void main(String[] args) {
        Function<String, String> normalize =
                (var text) -> text.strip();

        System.out.println("value=" + normalize.apply("  Java  "));
    }
}
```

```bash
javac --release 17 LambdaParametersDemo.java
java LambdaParametersDemo
```

```text
value=Java
```

Ngữ cảnh `Function<String, String>` vẫn là **phần không thể thiếu**. Cố đổi khai báo thành `var normalize = (var text) -> text.strip();` thì lỗi thiếu target type vẫn tồn tại.

Ngoài ra, khi chọn khai báo tham số lambda bằng `var`, phải dùng `var` nhất quán với mọi tham số của cùng lambda, không trộn kiểu khai báo như `(var a, String b) -> ...`. Thường người học không cần `var` trong tham số lambda nếu không có lý do về nhất quán cú pháp hoặc annotation; `text -> text.strip()` với target type tường minh vẫn dễ đọc.

## 8. `var`, kiểu generic và suy luận có thể rộng hơn mong muốn

Đừng nhầm **suy luận kiểu trả về lời gọi phương thức** với **suy luận functional interface từ bare lambda**.

Ví dụ: `Function.identity()` là phương thức có kiểu trả về đã khai báo, do đó dùng với `var` là **hợp lệ**. Tuy nhiên, nếu không có thông tin bổ sung, tham số kiểu generic có thể được suy luận thành `Object`:

```java
var broad = Function.identity();           // Function<Object, Object>
var precise = Function.<String>identity(); // Function<String, String>

Object a = broad.apply("hello");
String b = precise.apply("hello");
```

Cần `import java.util.function.Function;` và đặt trong một method. Trình biên dịch đã biết kiểu của mỗi lời gọi `identity()`, nhưng độ cụ thể của generic phụ thuộc target type và type witness.

Không nên chuyển một lambda không có kiểu đích thành `Object` để “giữ tính linh hoạt”. Khi muốn biểu diễn tác vụ không tham số, dùng `Runnable`; khi muốn chuyển đổi, dùng `Function`/`UnaryOperator`; khi muốn kiểm tra điều kiện, dùng `Predicate`. Nếu interface chuẩn không biểu đạt hợp đồng mong muốn (ví dụ ngoại lệ checked khác biệt), có thể thiết kế functional interface riêng.

Ví dụ functional interface riêng:

```java
@FunctionalInterface
interface Formatter {
    String format(String source);
}

// Với Formatter được khai báo trong chương trình:
Formatter formatter = value -> "[" + value.strip() + "]";
```

Dạng này vẫn cần target type là `Formatter`, chứ `var formatter = value -> ...` vẫn sai.

## 9. Cách chẩn đoán nhanh và sửa trong dự án

Khi gặp `cannot infer type` với lambda/method reference:

1. **Xác định initializer:** Nếu vế phải của `var` là `->` hoặc `::` trực tiếp, nghi ngờ thiếu target type trước tiên.
2. **Xác định hợp đồng hàm:** Có bao nhiêu tham số? Đầu vào/đầu ra là kiểu gì? Có side effect hoặc checked exception không? Từ đó chọn đúng `Function`, `UnaryOperator`, `Predicate`, `Consumer`, `Supplier`, `Runnable` hoặc interface riêng.
3. **Đặt kiểu tại nơi rõ nghĩa nhất:** Thường là khai báo biến hoặc tham số phương thức. Chỉ dùng cast nếu nó giúp ích cho cách tổ chức mã.
4. **Nếu `var` đứng trước một lời gọi phương thức:** Kiểm tra target type của **lambda tại vị trí đối số**, rồi kiểm tra kiểu trả về của **cả lời gọi** để biết `var` sẽ suy ra gì.
5. **Với method reference:** Kiểm tra static/bound/unbound/constructor reference, số tham số, overload và kiểu trả về. Nếu khó đọc, chuyển tạm thành lambda tương đương đã có target type.
6. **Biên dịch bằng target Java của dự án:** Ví dụ `javac --release 17 ...`; sửa mọi lỗi thực sự thay vì che lỗi bằng cast `Object` hoặc `@SuppressWarnings`.

**Bảng trước/sau:**

| Sai: thiếu kiểu đích | Đúng: có kiểu đích | Vì sao |
|---|---|---|
| `var f = x -> x + 1;` | `IntUnaryOperator f = x -> x + 1;` | Biết hàm nhận/trả `int` |
| `var f = String::trim;` | `UnaryOperator<String> f = String::trim;` | Chọn SAM `String apply(String)` |
| `var f = (String s) -> s.trim();` | `Function<String, String> f = s -> s.trim();` | Nêu interface thay vì chỉ nêu kiểu tham số |
| `var f = (var s) -> s.strip();` | `Function<String, String> f = (var s) -> s.strip();` | `var` trong lambda vẫn cần interface đích |
| `Object f = String::trim;` | `Object f = (Function<String, String>) String::trim;` | Cast cung cấp target trước khi upcast lên `Object` |
| `var f = flag ? String::trim : String::toUpperCase;` | `UnaryOperator<String> f = flag ? String::trim : String::toUpperCase;` | Cả hai nhánh nhận kiểu đích từ phép gán |

Các ô mã trong bảng là **mảnh minh họa**, giả định có import, biến và phạm vi khai báo phù hợp. Bảng so sánh lỗi kiểu; nó không khuyến khích lưu functional interface dưới dạng `Object` nếu không cần thiết.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `var convert = (String s) -> s.toUpperCase();` không biên dịch, dù kiểu tham số và kết quả đều rõ?

> Vì Java cần một functional interface target cho toàn bộ lambda. Chữ ký đầu vào/đầu ra không tự xác định interface cụ thể.

**Câu 2.** `var f = (UnaryOperator<String>) String::trim;` có hợp lệ không? Kiểu tĩnh của `f` là gì?

> Có. Cast cung cấp target type; `f` có kiểu `UnaryOperator<String>`.

**Câu 3.** `var result = applyText("  hi  ", String::trim);` có hợp lệ không nếu `applyText` nhận `UnaryOperator<String>` và trả `String`?

> Có. Method reference có target tại tham số của `applyText`; `result` là `String`.

**Câu 4.** Dùng `(var s) -> s.trim()` theo Java 11 có cho phép viết `var f = (var s) -> s.trim();` không?

> Không. `var` trong tham số lambda chỉ thay cách khai báo tham số; lambda vẫn phải có target functional interface.

**Câu 5.** Vì sao `Supplier<String> f = String::trim;` sai, còn `Function<String, String> f = String::trim;` đúng?

> `String::trim` cần một receiver `String`. `Supplier` không có tham số; `Function` có một tham số phù hợp.

**Câu 6.** `var fn = Function.identity();` có hợp lệ không? Có chắc kiểu là `Function<String, String>` vì về sau gọi với chuỗi?

> Hợp lệ, nhưng khi không có ngữ cảnh generic bổ sung, kiểu suy ra thường là `Function<Object, Object>`; phép gọi sau không quyết định lại kiểu. Dùng `Function<String, String> fn = Function.identity();` hoặc `var fn = Function.<String>identity();` khi cần kiểu cụ thể.

## 11. Nguồn chính thức

- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): nguồn gốc `var` ở Java 10 và các giới hạn initializer.
- [OpenJDK — FAQ cho `var`/JEP 286](https://github.com/openjdk/amber-docs/blob/master/site/guides/lvti-faq.md): giải thích vì sao lambda và method reference không đủ để suy ra kiểu cho `var`.
- [Java Language Specification, Java 17 — Method Reference Expressions (`15.13)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.13): quy tắc target type, cú pháp và phân giải method reference.
- [Java Language Specification, Java 17 — Type of a Lambda Expression (`15.27.3)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.3): kiểu đích và functional interface.
- [OpenJDK JEP 323 — Local-Variable Syntax for Lambda Parameters](https://openjdk.org/jeps/323): phân biệt `var` trong tham số lambda (Java 11) với `var` khai báo biến cục bộ (Java 10).
- [Java SE 17 — `java.util.function`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html): các functional interface thường dùng trong code hiện đại.

**Ghi nhớ cốt lõi:** `var` lấy kiểu từ một initializer **đã có kiểu tĩnh**. Lambda và method reference đứng một mình là những **poly expression cần functional interface target**. Muốn kết hợp chúng, hãy cung cấp target thông qua khai báo interface, tham số/kiểu trả về phương thức hoặc cast rõ ràng. Quy tắc này vẫn áp dụng trong Java hiện đại.