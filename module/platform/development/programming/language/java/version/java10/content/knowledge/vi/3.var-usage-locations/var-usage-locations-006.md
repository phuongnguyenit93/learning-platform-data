# Giới hạn dùng `var` cho kiểu trả về và tham số phương thức trong Java

## 1. Quy tắc cần nhớ

Từ Java 10, `var` cho phép trình biên dịch **suy luận kiểu của biến cục bộ từ biểu thức khởi tạo**. Khả năng này vẫn được hỗ trợ trong Java hiện đại, nhưng không biến Java thành ngôn ngữ có kiểu động và cũng không áp dụng cho mọi vị trí cần khai báo kiểu.

Đặc biệt:

- **Không được dùng `var` làm kiểu trả về của phương thức**. Ví dụ `public var name()` không hợp lệ, dù thân phương thức luôn `return` một `String`.
- **Không được dùng `var` làm kiểu của tham số phương thức hoặc constructor**. Ví dụ `void print(var value)` và `Person(var name)` không hợp lệ.
- **Được dùng `var` cho biến cục bộ có biểu thức khởi tạo bên trong phương thức**, chẳng hạn `var name = lookupName();`. Phương thức mà biến này gọi vẫn khai báo kiểu trả về tường minh.
- **Ngoại lệ về cú pháp dễ nhầm:** từ Java 11, tham số của *biểu thức lambda* được phép viết `(var x, var y) -> ...` khi thỏa quy tắc lambda. Đây **không phải** tham số trong khai báo một phương thức thông thường.

Nói ngắn gọn: `var` giúp giảm phần khai báo kiểu **trong phần thân xử lý**, trong khi chữ ký (signature) của API phương thức vẫn cần kiểu rõ ràng.

## 2. Vì sao không được suy luận kiểu trả về?

Xét mong muốn viết một phương thức như sau:

~~~java
// KHÔNG HỢP LỆ — chỉ là ví dụ lỗi cú pháp, không phải chương trình chạy.
public var getTitle() {
    return "Java";
}
~~~

Dù biểu thức `"Java"` có kiểu `String`, Java không cho phép `var` ở vị trí khai báo kiểu trả về. Hãy dùng:

~~~java
public String getTitle() {
    return "Java";
}
~~~

Đây là **đoạn phương thức minh họa**, cần đặt trong một lớp để biên dịch; chương trình hoàn chỉnh nằm ở mục 6.

Lý do thiết kế quan trọng:

1. **Kiểu trả về là một phần của hợp đồng API.** Mã gọi, trình biên dịch, Javadoc và thông tin bytecode cần biết kiểu mà phương thức hứa cung cấp, ngay cả khi không xem nội dung triển khai.
2. **Thay đổi cài đặt không nên âm thầm thay đổi hợp đồng.** Nếu kiểu trả về suy luận từ câu lệnh `return`, việc chỉnh một nhánh hoặc đổi phép tính có thể vô tình đổi kiểu mà các nơi gọi phụ thuộc.
3. **Phương thức có thể có nhiều nhánh trả về hoặc gọi lẫn nhau.** Suy luận kiểu ở ranh giới phương thức sẽ làm API khó dự đoán và làm phức tạp phân tích kiểu; quy tắc của Java giữ việc suy luận `var` trong phạm vi cục bộ.
4. **Override và interface cần kiểu được công bố rõ.** Một phương thức triển khai interface hoặc ghi đè phương thức cha vẫn phải dùng kiểu trả về phù hợp với hợp đồng đã khai báo.

Nếu phương thức không trả về giá trị, tiếp tục dùng `void`:

~~~java
public void printTitle(String title) {
    System.out.println(title);
}
~~~

Nếu phương thức có thể trả về nhiều loại object theo hợp đồng, hãy thiết kế kiểu trả về phù hợp bằng interface, class, generic hoặc kiểu bao (wrapper) có ý nghĩa. **Đừng thay bằng `Object` chỉ để né việc khai báo kiểu**, vì người gọi sẽ mất kiểm tra kiểu hữu ích.

### Có thể `return` một biến khai báo bằng `var` không?

**Có.** Giới hạn chỉ nằm ở phần khai báo *kiểu trả về của phương thức*, không cấm biến cục bộ `var` trong thân phương thức:

~~~java
public String createGreeting(String name) {
    var result = "Xin chào, " + name;
    return result;
}
~~~

Ở đây `result` được suy luận là `String`; `return result` hợp lệ vì phù hợp với kiểu trả về `String` đã khai báo. Mã trên là một **phương thức minh họa**, chưa phải file Java hoàn chỉnh.

## 3. Vì sao không được viết `var` ở tham số phương thức?

Đoạn sau **không biên dịch**:

~~~java
// KHÔNG HỢP LỆ — tham số phương thức phải có kiểu công bố.
public void send(var message) {
    System.out.println(message);
}
~~~

Cách đúng:

~~~java
public void send(String message) {
    System.out.println(message);
}
~~~

Điều này đúng với phương thức `static`, phương thức instance, phương thức trong interface, constructor và phương thức có tham số biến thiên (varargs). Hình thức `String... messages` là một kiểu tham số biến thiên **khác hoàn toàn** với từ `var`.

Ví dụ một constructor hợp lệ:

~~~java
public final class Message {
    private final String text;

    public Message(String text) {
        this.text = text;
    }

    public String text() {
        return text;
    }
}
~~~

Đây là một lớp độc lập có thể đặt trong file `Message.java`; tên và kiểu của các tham số/giá trị trả về đều được khai báo rõ ràng.

**Không thể suy luận kiểu tham số từ đối số ở từng lần gọi.** Ví dụ nếu một nơi gọi `send("hello")` còn nơi khác gọi `send(42)`, Java không tự tạo một tham số có kiểu thích nghi theo từng lời gọi. Phương thức có một chữ ký xác định, và trình biên dịch dùng chữ ký đó khi kiểm tra lời gọi và lựa chọn overload.

Khi cần một phương thức xử lý nhiều kiểu dữ liệu theo cách an toàn, hãy xem xét generic thay vì `var`.

## 4. Generic và `var` giải quyết hai bài toán khác nhau

Một phương thức generic có thể khai báo kiểu trừu tượng bằng tham số kiểu `T`:

~~~java
public static <T> T identity(T input) {
    return input;
}
~~~

Trong khai báo này:
- `<T>` xác định tham số kiểu của **phương thức**.
- Kiểu tham số `T input` và kiểu trả về `T` đều là những kiểu hợp lệ, được khai báo tường minh trong chữ ký generic.
- Khi gọi `identity("Java")`, compiler có thể suy luận `T` là `String` theo ngữ cảnh gọi. Đây là **method type inference**, không phải cho phép dùng `var` làm kiểu phương thức.
- Ở phía gọi, có thể viết `var text = identity("Java");`: lúc này `var` chỉ suy luận kiểu cho **biến cục bộ** `text`.

Với API thực tế, lựa chọn kiểu trả về nên diễn tả đúng ý nghĩa. Ví dụ `List<String>` hoặc một interface phù hợp thường tốt hơn dùng kiểu triển khai quá cụ thể; `Optional<T>` có thể hữu ích khi thiết kế API có ý nghĩa “có hoặc không có giá trị”. Chọn theo hợp đồng thực sự, không mặc định dùng `Object` hoặc generic cho mọi trường hợp.

## 5. Ngoại lệ cần phân biệt: `var` trong tham số lambda từ Java 11

Java 11 bổ sung cú pháp `var` cho **tham số lambda** (JEP 323). Đây vẫn là một tính năng được dùng trên JDK hiện đại, nên cần phân biệt với quy tắc của phương thức:

~~~java
// HỢP LỆ từ Java 11 trở lên nếu lambda có kiểu mục tiêu phù hợp:
java.util.function.BiFunction<String, Integer, String> formatter =
        (var text, var count) -> text.repeat(count);
~~~

Các kiểu tham số `text`/`count` được xác định dựa trên **functional interface** `BiFunction<String, Integer, String>`, không phải kiểu được suy luận tự do từ phần thân lambda. Trong ví dụ, `String.repeat(int)` cũng là API có từ Java 11. Đoạn khai báo này là một **đoạn code minh họa trong thân phương thức**; không thể đặt trực tiếp ở đầu file Java ngoài lớp/phương thức.

Có ba hình thức lambda tương đương về kiểu khi ngữ cảnh kiểu đã rõ:

~~~java
// Các biểu thức minh họa, đặt ở nơi có kiểu đích BiFunction<Integer, Integer, Integer>.
(a, b) -> a + b
(var a, var b) -> a + b
(Integer a, Integer b) -> a + b
~~~

Đừng trộn cách khai báo giữa các tham số trong **cùng một lambda**:

~~~java
// KHÔNG HỢP LỆ — chỉ minh họa những cú pháp bị cấm.
(var a, b) -> a + b
(var a, Integer b) -> a + b
(Integer a, var b) -> a + b
~~~

Nếu chọn `var` thì **mọi tham số của lambda** đều dùng `var`. Nếu chọn kiểu tường minh thì viết kiểu cho mọi tham số; nếu chọn tên đơn giản thì để mọi tham số suy luận không có `var`. Lambda với tham số khai báo `var` phải viết trong cặp ngoặc tròn, ví dụ `(var x) -> x.trim()`.

`var` trong lambda chủ yếu hữu ích khi cần cú pháp nhất quán với các biến cục bộ hoặc cần gắn một annotation hay modifier `final` phù hợp vào tham số; không tự giúp lambda xử lý thêm kiểu mà functional interface không cho phép.

Một giới hạn nữa: bản thân lambda cần **kiểu mục tiêu** từ interface phù hợp. Không thể viết:

~~~java
// KHÔNG HỢP LỆ — lambda không có kiểu mục tiêu để suy luận.
var formatter = (var text) -> text.trim();
~~~

Cách đúng là khai báo kiểu functional interface:

~~~java
java.util.function.UnaryOperator<String> formatter =
        (var text) -> text.trim();
~~~

**Phân biệt về version:** `var` cho biến cục bộ có từ Java 10; riêng `var` trên tham số lambda có từ Java 11. Trên JDK 17+ cả hai dạng hợp lệ vẫn hoạt động. Tuy nhiên, ở **chữ ký phương thức và constructor** vẫn phải khai báo kiểu như trước, kể cả khi sử dụng JDK mới nhất.

## 6. Chương trình hoàn chỉnh chạy trên Java 17+

Ví dụ sau minh họa đồng thời bốn vị trí: kiểu trả về tường minh, tham số phương thức tường minh, `var` cho biến cục bộ và `var` cho tham số lambda có kiểu mục tiêu. Lưu đúng tên file **`VarMethodDemo.java`**:

~~~java
import java.util.function.BiFunction;

public class VarMethodDemo {

    public static String repeatText(String text, int times) {
        var builder = new StringBuilder();

        for (var i = 0; i < times; i++) {
            builder.append(text);
        }

        return builder.toString();
    }

    public static <T> T identity(T value) {
        return value;
    }

    public static void main(String[] args) {
        var greeting = repeatText("Hi", 2);

        BiFunction<String, Integer, String> operation =
                (var text, var count) -> repeatText(text, count);

        var repeated = operation.apply("Java", 2);
        var label = identity("OK");

        System.out.println(greeting);
        System.out.println(repeated);
        System.out.println(label);
    }
}
~~~

Biên dịch bằng JDK 17 trở lên có hỗ trợ `--release 17`:

~~~bash
javac --release 17 VarMethodDemo.java
java VarMethodDemo
~~~

**Stdout chính xác:**

~~~text
HiHi
JavaJava
OK
~~~

Giải thích từng vị trí:

| Vị trí | Khai báo trong ví dụ | Vì sao đúng? |
| --- | --- | --- |
| Kiểu trả về phương thức | `String repeatText(...)` | Công bố kiểu `String` cho người gọi. |
| Tham số phương thức | `String text, int times` | Chữ ký phương thức có kiểu cụ thể. |
| Biến cục bộ trong phương thức | `var builder = new StringBuilder()` và `var i = 0` | Có biểu thức khởi tạo để suy luận kiểu `StringBuilder` và `int`. |
| Biến cục bộ nhận kết quả phương thức | `var greeting = repeatText(...)` | Kiểu suy luận là `String`, dựa trên kiểu trả về công bố của phương thức. |
| Tham số của biểu thức lambda | `(var text, var count) -> ...` | Có kiểu mục tiêu `BiFunction<String, Integer, String>`; cú pháp này hợp lệ từ Java 11. |
| Phương thức generic | `<T> T identity(T value)` | Cơ chế generic cung cấp kiểu của tham số và kiểu trả về; caller có thể dùng `var` cho kết quả cục bộ. |

**Kiểm chứng trực tiếp:** đoạn `StringBuilder` ban đầu rỗng, vòng lặp nối `"Hi"` hai lần thành `"HiHi"`; lambda gọi `repeatText("Java", 2)` cho `"JavaJava"`; `identity("OK")` trả lại `"OK"`. Không có mã deprecated hay API nội bộ.

## 7. Bảng phân biệt nhanh vị trí được phép và bị cấm

| Vị trí | Dùng `var`? | Ví dụ / cách đúng |
| --- | --- | --- |
| Biến cục bộ có giá trị khởi tạo trong method | **Có** (Java 10+) | `var result = service.load();` |
| Biến điều khiển vòng `for` | **Có** (Java 10+) | `for (var i = 0; i < 3; i++)` |
| Biến trong enhanced `for` | **Có** (Java 10+) | `for (var item : items)` |
| Biến resource trong `try-with-resources` | **Có**, khi có initializer hợp lệ | `try (var reader = Files.newBufferedReader(path)) { ... }` |
| Kiểu trả về method | **Không** | `String getName()`, `void print()` hoặc kiểu generic hợp lệ |
| Tham số phương thức | **Không** | `void print(String name)` |
| Tham số constructor | **Không** | `Person(String name)` |
| Thuộc tính/field của class | **Không** | `private final String name;` |
| Tham số lambda | **Có** (Java 11+) | `(var x, var y) -> x + y`, có kiểu mục tiêu phù hợp và dùng đồng nhất |
| Tham số khai báo của abstract method trong functional interface | **Không** | `String apply(String input);` |
| Khai báo generic method | **Không thay `T` bằng `var`** | `static <T> T identity(T x)` |

Lưu ý: Với biến cục bộ, bản thân `var` cần đủ thông tin để suy luận kiểu. Vì thế `var value;` hoặc `var value = null;` không hợp lệ. Đây là yêu cầu riêng của suy luận kiểu biến cục bộ; nó không tạo ngoại lệ cho chữ ký phương thức.

## 8. Những nhầm lẫn thường gặp và cách sửa

### Nhầm 1: “Compiler biết method trả `String` nên tôi viết `var` để nó tự hiểu”

**Sai**. Compiler không sử dụng `return` để suy luận kiểu trả về trong chữ ký của phương thức Java. Đổi `public var name()` thành `public String name()` (hoặc kiểu phù hợp với hợp đồng).

### Nhầm 2: “Java 11 cho dùng `var` ở tham số, vậy method cũng dùng được”

**Sai**. Java 11 chỉ mở rộng cho **tham số của biểu thức lambda**. Chữ ký một phương thức như `void log(var text)` vẫn không hợp lệ ở Java 17, 21, 25, 27 và các JDK hiện đại. Viết `void log(String text)`.

### Nhầm 3: “Dùng `var` thì kiểu sẽ thay đổi khi gán giá trị khác”

**Sai**. Một biến `var x = "Java";` có kiểu tĩnh là `String`. Gán `x = 123;` không hợp lệ vì `int` không phải `String`. Phương thức trả về `String` vẫn trả kiểu tường minh, bất kể biến cục bộ dùng `var`.

### Nhầm 4: “Generic `<T> T` chính là `var` cho kiểu trả về”

**Sai**. `T` là một **type parameter** được khai báo trong API của phương thức. Java kiểm tra mối liên hệ giữa các vị trí `T` theo quy tắc generic; điều đó khác với suy luận kiểu của biến cục bộ.

### Nhầm 5: “Lambda có `var` thì tự đoán được toàn bộ kiểu mà không cần functional interface”

**Sai**. Lambda nhận kiểu mục tiêu từ phép gán, tham số lời gọi phương thức hoặc ngữ cảnh tương ứng. Cần một functional interface như `Function<String, String>`, `UnaryOperator<String>` hay `BiFunction<A, B, R>`. Sử dụng `var` cho biến nhận chính lambda mà không có ngữ cảnh kiểu mục tiêu sẽ không biên dịch.

### Nhầm 6: “Đổi khai báo method thành `Object` là tương đương `var`”

**Sai**. `Object` là kiểu thật, được công bố trong hợp đồng API; người gọi có thể phải cast hoặc kiểm tra kiểu. Đổi từ `String` sang `Object` làm yếu ràng buộc compile-time. Nếu cần API linh hoạt, thiết kế theo interface hoặc generic cụ thể.

## 9. Cách kiểm tra trên dự án và câu hỏi tự đánh giá

**Quy trình áp dụng:**
1. Xác nhận phiên bản compiler/Java mà dự án nhắm tới với `javac --version` và cấu hình toolchain. Nếu dùng `var` trong lambda, cần source level từ Java 11; dùng `--release 17` khi ứng dụng thực sự nhắm tới Java 17.
2. Khi định viết `var`, hỏi “Tôi đang khai báo **biến cục bộ có initializer** hay một phần **chữ ký method/constructor**?”. Với chữ ký method, phải đặt kiểu tường minh.
3. Nếu đang viết lambda, xác nhận phiên bản Java và functional interface kiểu mục tiêu. Chọn đồng nhất `(x, y)` hoặc `(var x, var y)`; không trộn.
4. Với API công khai, chọn kiểu trả về và kiểu tham số giúp người dùng API hiểu, compile và phát triển mã an toàn. `var` không phải công cụ thiết kế hợp đồng API.
5. Chạy biên dịch trên đúng target; kiểm tra cả khi IDE gợi ý “convert to var”, vì tính năng refactor biến cục bộ không có nghĩa nó áp dụng được cho method signature.

**Tự kiểm tra:**

- `var result = calculate();` nằm trong method và có initializer hợp lệ. **Hợp lệ:** kiểu của `result` suy luận từ `calculate()`.
- `public var calculate() { return 42; }`. **Không hợp lệ:** cần `public int calculate()` hoặc kiểu trả về được khai báo phù hợp.
- `public void print(var item)`. **Không hợp lệ:** cần kiểu tham số tường minh, chẳng hạn `String`.
- `BiFunction<Integer, Integer, Integer> add = (var a, var b) -> a + b;`. **Hợp lệ từ Java 11:** có kiểu mục tiêu và cả hai tham số lambda đều dùng `var`.
- `BiFunction<Integer, Integer, Integer> add = (var a, b) -> a + b;`. **Không hợp lệ:** lambda trộn cú pháp tham số có và không có `var`.
- `public static <T> T first(T item) { return item; }`. **Hợp lệ:** đây là khai báo generic method với kiểu trả về và tham số đã có ràng buộc `T`, không dùng `var` ở chữ ký.

## 10. Tài liệu chính thức để tra khi cần

- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): phạm vi suy luận kiểu biến cục bộ ra mắt Java 10 và lý do không đưa suy luận vào chữ ký API.
- [OpenJDK — Local Variable Type Inference FAQ](https://github.com/openjdk/amber-docs/blob/master/site/guides/lvti-faq.md): mục “Where can `var` be used?” giải thích rõ không được dùng cho field, tham số phương thức hay kiểu trả về phương thức.
- [OpenJDK JEP 323 — Local-Variable Syntax for Lambda Parameters](https://openjdk.org/jeps/323): cú pháp tham số lambda có `var` từ Java 11.
- [Oracle — Java 17 Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html): ví dụ hợp lệ và không hợp lệ của `var` cho biến cục bộ và tham số lambda.
- [Oracle — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html): xác nhận Java 10 bổ sung suy luận kiểu cho biến cục bộ và Java 11 bổ sung cú pháp `var` cho tham số lambda.

**Điểm cốt lõi khi áp dụng hiện nay:** `var` dành cho các vị trí suy luận kiểu được Java cho phép, đặc biệt là biến cục bộ; phương thức và constructor vẫn khai báo tham số, kiểu trả về tường minh. Riêng `var` trong biểu thức lambda từ Java 11 là cú pháp hợp lệ với điều kiện có kiểu mục tiêu và không trộn các kiểu khai báo tham số.