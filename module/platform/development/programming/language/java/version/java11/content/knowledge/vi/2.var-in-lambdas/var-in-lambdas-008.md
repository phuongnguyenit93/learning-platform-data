# Capture, effectively final và phạm vi từ vựng trong lambda (Java 11+)

**Ngữ cảnh:** Bài này thuộc chủ đề `var trong lambda`. Lambda có từ Java 8; Java 11 bổ sung cú pháp `var` cho *tham số lambda* (JEP 323). Các quy tắc capture, `effectively final` và phạm vi từ vựng vẫn được áp dụng trong Java hiện đại. Mọi ví dụ chạy được dưới đây dùng cú pháp tương thích Java 11.

## 1. Cần phân biệt ba loại biến

- **Tham số lambda**: biến nhận đối số mỗi lần gọi, chẳng hạn `n` trong `(var n) -> n + 1`. Kiểu của `n` được suy ra từ *target type* (thường là functional interface).
- **Biến cục bộ ở phạm vi bên ngoài được capture**: biến khai báo trong phương thức/khối bao quanh và được thân lambda tham chiếu, chẳng hạn `offset` trong `(var n) -> n + offset`. Biến loại này phải là `final` hoặc `effectively final`.
- **Field của đối tượng/lớp**: chẳng hạn `this.prefix` hoặc một `static` field. Lambda có thể truy cập field theo quy tắc truy cập thông thường; quy tắc `effectively final` dành cho biến cục bộ được capture không áp lên bản thân field.

Ví dụ ngắn:

```java
int offset = 3;
java.util.function.IntUnaryOperator add = (var n) -> n + offset;
System.out.println(add.applyAsInt(7)); // 10
```

`n` là **tham số lambda** kiểu `int`; `offset` là **biến cục bộ được capture**. `var` không tạo kiểu dữ liệu động: kiểu vẫn được kiểm tra tại thời điểm biên dịch.

## 2. Capture thực chất là gì?

*Capture* (hay *lexical closure*) xảy ra khi lambda dùng tên một biến nằm ngoài phần khai báo và thân của chính nó. Lambda có thể tiếp tục được gọi sau khi phương thức tạo lambda đã kết thúc, vì vậy Java ràng buộc việc sử dụng các biến cục bộ bên ngoài theo quy tắc xác định và ổn định.

Đối với biến cục bộ có kiểu nguyên thủy, lambda sử dụng giá trị được capture. Đối với biến cục bộ chứa tham chiếu đối tượng, giá trị tham chiếu được capture: lambda và mã bên ngoài có thể cùng tham chiếu đến **một đối tượng**, chứ Java không tự tạo bản sao sâu đối tượng đó.

### Ví dụ hoàn chỉnh: `CaptureDemo.java`

```java
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.IntUnaryOperator;

public class CaptureDemo {
    public static void main(String[] args) {
        int discount = 2;
        IntUnaryOperator minusDiscount = (var price) -> price - discount;
        System.out.println(minusDiscount.applyAsInt(12));

        var prefix = "ID-";
        Function<Integer, String> makeId = (var id) -> prefix + id;
        System.out.println(makeId.apply(42));

        StringBuilder builder = new StringBuilder("Java");
        Runnable appendVersion = () -> builder.append(" 11");
        appendVersion.run();
        System.out.println(builder);

        BiFunction<String, String, String> join =
                (final var a, final var b) -> a + ":" + b;
        System.out.println(join.apply("A", "B"));
    }
}
```

Biên dịch và chạy bằng JDK 11 hoặc mới hơn:

```bash
javac --release 11 CaptureDemo.java
java CaptureDemo
```

Kết quả chính xác:

```text
10
ID-42
Java 11
A:B
```

Giải thích:

1. `discount` và `prefix` không bị gán lại sau khi khởi tạo nên đều *effectively final* và được capture hợp lệ.
2. `builder` cũng *effectively final*: biến này vẫn trỏ đến cùng `StringBuilder`. Lệnh `append` **thay đổi trạng thái đối tượng**, không gán lại biến `builder`. Nếu thay bằng `builder = new StringBuilder(...)` thì quy tắc capture sẽ bị vi phạm.
3. `price`, `id`, `a` và `b` là tham số của lambda, không phải các biến được capture từ phương thức `main`.
4. `final var a` và `final var b` là cú pháp hợp lệ trên tham số lambda từ Java 11; `final` ngăn gán lại chính những tham số này bên trong lambda.

## 3. `final` và `effectively final`

- **`final` tường minh:** người viết khai báo `final int base = 10;`; biến chỉ có thể được gán một lần theo quy tắc của Java.
- **`effectively final`:** không viết `final`, nhưng trong mã biến không bị gán lại sau giá trị gán hợp lệ ban đầu và không bị tăng/giảm bằng `++` hoặc `--`. Thêm `final` vào khai báo một biến *effectively final* sẽ không làm chương trình hợp lệ trở thành lỗi.
- **Definite assignment:** biến còn phải chắc chắn có giá trị trước khi được dùng trong lambda.

Ví dụ hợp lệ (đặt trong một phương thức):

```java
int base;
base = 10; // Gán lần đầu và duy nhất
java.util.function.IntUnaryOperator addBase = (var n) -> n + base;
System.out.println(addBase.applyAsInt(5)); // 15
```

Không cần đặt `final` một cách máy móc lên từng biến được capture. Tuy vậy, nếu biến mang ý nghĩa hằng số nghiệp vụ, khai báo `final` tường minh giúp người đọc hiểu ý định.

### Hai lỗi biên dịch thường gặp

**Lỗi 1 — sửa biến trước hoặc sau khi tạo lambda.** Đoạn sau minh họa lỗi, **không biên dịch được**:

```java
int bonus = 5;
java.util.function.IntUnaryOperator addBonus = (var n) -> n + bonus;
bonus++; // bonus không còn effectively final
```

Ngay cả khi `bonus++` nằm **sau** dòng tạo lambda, bộ biên dịch vẫn xét toàn bộ phạm vi liên quan để xác định tính *effectively final*. Không có chuyện lambda tự cho phép dùng một phiên bản cũ trong khi biến cục bộ tiếp tục bị gán lại.

**Lỗi 2 — gán lại biến trong lambda.** Đoạn sau cũng **không biên dịch được**:

```java
int total = 0;
Runnable update = () -> total++; // total là biến cục bộ bên ngoài
```

Cách xử lý nên ưu tiên: truyền giá trị như tham số, trả về kết quả mới, hoặc sử dụng phép tổng hợp như `map`/`reduce` trong xử lý collection. Nếu thật sự cần trạng thái chia sẻ, phải lựa chọn đối tượng giữ trạng thái với quy tắc đồng bộ phù hợp; xem mục 8.

**Lưu ý với `var`:** khai báo biến cục bộ kiểu `var` phải có initializer để suy luận kiểu, nên `var base;` không hợp lệ. Điều này khác với `int base; base = 10;` ở trên.

## 4. Phạm vi từ vựng (*lexical scope*) của lambda

Lambda sử dụng phạm vi tên của vị trí nó được viết. Nó **không tạo một `this`/`super` mới** như một lớp ẩn danh có thể làm:

- Trong phương thức instance, `this` bên trong lambda là đối tượng của lớp bao quanh.
- Lambda nhìn thấy local/parameter/field đang nằm trong phạm vi truy cập hợp lệ tại vị trí khai báo, với điều kiện capture đối với local/parameter bên ngoài.
- Tham số và biến cục bộ khai báo bên trong lambda chỉ tồn tại trong phạm vi của chúng; không thể dùng tên đó ở ngoài lambda.
- Lambda không được khai báo lại tên của một biến cục bộ hoặc tham số ở phạm vi phương thức bao quanh khi tên đó còn trong scope. Không có một tầng tên riêng cho phép che khuất local bên ngoài.

### Ví dụ hoàn chỉnh: `LexicalScopeDemo.java`

```java
import java.util.function.Function;

public class LexicalScopeDemo {
    private String prefix = "old-";

    void demonstrate() {
        String suffix = "!";
        Function<Integer, String> render =
                (var value) -> this.prefix + value + suffix;

        System.out.println(render.apply(7));
        this.prefix = "new-";
        System.out.println(render.apply(7));
    }

    public static void main(String[] args) {
        new LexicalScopeDemo().demonstrate();
    }
}
```

```bash
javac --release 11 LexicalScopeDemo.java
java LexicalScopeDemo
```

```text
old-7!
new-7!
```

`suffix` là local được capture nên vẫn mang giá trị `"!"`; `this.prefix` là field được đọc khi chạy lambda và có thể thay đổi theo thời gian. `this` ở đây chính là instance `LexicalScopeDemo`. Trong một phương thức `static` không có `this` của instance để sử dụng.

Ví dụ **không biên dịch được** vì trùng tên local:

```java
int count = 10;
java.util.function.IntUnaryOperator f = (var count) -> count + 1;
// Tham số lambda không được khai báo trùng local count bên ngoài
```

Ngược lại, nếu lớp có field `count`, một tham số lambda cũng tên `count` có thể che khuất **field** đó; có thể dùng `this.count` để gọi rõ field của instance. Cần phân biệt quy tắc tên của local/parameter với tên field.

## 5. `var` trong tham số lambda có tác dụng gì ở Java 11?

Java 11 cho phép các dạng sau khi đã biết functional interface đích:

```java
java.util.function.IntUnaryOperator a = n -> n + 1;
java.util.function.IntUnaryOperator b = (var n) -> n + 1;
java.util.function.IntUnaryOperator c = (int n) -> n + 1;
```

Cả ba có cùng kiểu tham số `int` và cùng kết quả. `var` ở đây chỉ làm gọn cú pháp khai báo tham số và cho phép bổ sung annotation/modifier; **không thay đổi** luật capture, vòng đời biến, hay kiểu trả về của lambda.

Quy tắc cú pháp cần nhớ:

| Cú pháp | Kết quả | Vì sao |
| --- | --- | --- |
| `n -> n + 1` | Hợp lệ | Một tham số suy luận kiểu, có thể bỏ ngoặc |
| `(var n) -> n + 1` | Hợp lệ | Dùng `var` phải có ngoặc |
| `(var a, var b) -> a + b` | Hợp lệ khi có target type phù hợp | Cả hai tham số cùng dùng `var` |
| `(var a, b) -> a + b` | Lỗi | Không trộn `var` với tham số bỏ kiểu |
| `(var a, int b) -> a + b` | Lỗi | Không trộn `var` với kiểu tường minh |
| `var n -> n + 1` | Lỗi | Thiếu ngoặc quanh `var n` |

Các đoạn trong bảng là **biểu thức** lambda minh họa; để biên dịch, đặt chúng trong ngữ cảnh functional interface tương thích. Chẳng hạn `BiFunction<Integer, Integer, Integer> sum = (var a, var b) -> a + b;` là một khai báo hợp lệ.

`var` **không tự cấp target type** cho lambda. Vì vậy khai báo dưới đây **không hợp lệ**:

```java
var function = (var n) -> n + 1; // Không có target type để suy ra lambda
```

Hãy dùng một functional interface, ví dụ `IntUnaryOperator function = (var n) -> n + 1;`. Đây là cùng nguyên tắc kiểm tra kiểu khi dùng method reference và lambda ở Java hiện đại.

### Annotation trên tham số `var`

Lợi ích thực tế của JEP 323 là cho phép khai báo annotation hoặc `final` trên tham số lambda mà vẫn suy luận kiểu. Ví dụ độc lập sau tạo một annotation đánh dấu và dùng nó cho hai tham số.

**`AnnotatedVarDemo.java`**

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.function.BiFunction;

@Target(ElementType.PARAMETER)
@interface Marked {}

public class AnnotatedVarDemo {
    public static void main(String[] args) {
        BiFunction<String, String, String> join =
                (@Marked var left, @Marked var right) -> left + ":" + right;
        System.out.println(join.apply("L", "R"));
    }
}
```

```bash
javac --release 11 AnnotatedVarDemo.java
java AnnotatedVarDemo
```

```text
L:R
```

`@Marked` trong ví dụ chỉ là metadata/đánh dấu. Java không tự kiểm tra nghiệp vụ hay ràng buộc `null` chỉ vì một annotation được đặt trên tham số; tác dụng cụ thể phụ thuộc annotation và công cụ/framework sử dụng nó.

## 6. Capture trong vòng lặp

Một biến điều khiển vòng `for` thông thường bị tăng/giảm qua các lần lặp, vì vậy không *effectively final*:

```java
for (int i = 0; i < 3; i++) {
    // tasks.add(() -> System.out.println(i)); // Lỗi biên dịch
}
```

Cách thông dụng là tạo một bản sao cục bộ cho **từng** lần lặp. Biến trong enhanced `for` cũng được xem là biến riêng ở mỗi lần lặp, nên có thể capture nếu nó không bị gán lại.

### Ví dụ hoàn chỉnh: `LoopCaptureDemo.java`

```java
import java.util.ArrayList;
import java.util.List;

public class LoopCaptureDemo {
    public static void main(String[] args) {
        List<Runnable> tasks = new ArrayList<>();

        for (int i = 0; i < 3; i++) {
            var snapshot = i;
            tasks.add(() -> System.out.println(snapshot));
        }

        for (var label : List.of("A", "B")) {
            tasks.add(() -> System.out.println(label));
        }

        tasks.forEach(Runnable::run);
    }
}
```

```bash
javac --release 11 LoopCaptureDemo.java
java LoopCaptureDemo
```

```text
0
1
2
A
B
```

`snapshot` được tạo lại ở mỗi lượt, mỗi lần chỉ gán một giá trị rồi capture. Biến `label` của enhanced `for` cũng là một biến riêng cho từng lượt. `var` ở hai khai báo trên là suy luận kiểu **biến cục bộ** (Java 10+), còn `var` trong danh sách tham số lambda là tính năng Java 11.

## 7. Trường hợp tham số lambda bị gán lại

Quy tắc capture **không cấm mọi phép gán trong thân lambda**. Ví dụ này hợp lệ vì `input` là tham số của chính lambda và không được một lambda/lớp lồng bên trong capture:

```java
java.util.function.UnaryOperator<String> trim = (var input) -> {
    input = input.trim();
    return input;
};
System.out.println(trim.apply("  Java  ")); // Java
```

Tuy nhiên, viết thành `(var input) -> input.trim()` thường rõ ràng hơn. Nếu khai báo `(final var input)`, phép gán lại `input` sẽ trở thành lỗi biên dịch. Nếu lambda *con* capture tham số `input`, tham số ấy lại phải `final` hoặc *effectively final*, giống các tham số phương thức được capture từ bên ngoài.

## 8. Capture và dữ liệu thay đổi: chú ý tính an toàn

`effectively final` bảo vệ **ràng buộc của biến cục bộ**; nó không đồng nghĩa với **đối tượng bất biến** hoặc **an toàn khi chạy đa luồng**.

Ví dụ có thể biên dịch:

```java
int[] counter = {0};
Runnable increment = () -> counter[0]++;
increment.run();
System.out.println(counter[0]); // 1
```

Ở đây `counter` không bị trỏ sang mảng khác nhưng phần tử `counter[0]` bị sửa. Đừng coi mẹo mảng một phần tử là cách chuẩn để né *effectively final*: nó dễ gây tác dụng phụ khó theo dõi, đặc biệt nếu lambda chạy đồng thời trên nhiều thread.

- Nếu chỉ cần kết quả tính toán, ưu tiên lambda nhận đầu vào và **trả về giá trị** thay vì cập nhật biến ngoài.
- Nếu thực sự cần bộ đếm chia sẻ giữa thread, có thể dùng `AtomicInteger` cùng thiết kế đồng bộ phù hợp; `AtomicInteger` chỉ bảo đảm các thao tác nguyên tử mà API của nó cung cấp, không tự biến toàn bộ logic phức tạp thành thread-safe.
- Việc field có thể bị sửa không bảo đảm các thread khác nhìn thấy ngay thay đổi. Quy tắc *happens-before*, `volatile` hoặc cơ chế đồng bộ vẫn có thể cần thiết.

## 9. Cách tự kiểm tra nhanh

Khi đọc một lambda, hãy đi theo thứ tự:

1. **Xác định target type.** Functional interface nào quyết định kiểu tham số và kiểu trả về? Nếu dùng `var`, mọi tham số cùng khai báo `var` và có ngoặc chưa?
2. **Phân loại từng tên.** Nó là tham số lambda, local/parameter ở bên ngoài, hay field? Có tên bị khai báo trùng trong phạm vi từ vựng không?
3. **Kiểm tra local bên ngoài.** Mỗi biến được capture đã *definitely assigned* và `final`/*effectively final* chưa? Có phép gán, `++`, `--` ở bất kỳ nơi nào trong phạm vi liên quan không?
4. **Kiểm tra trạng thái đối tượng.** Lambda đang đọc giá trị ổn định, thay đổi đối tượng được tham chiếu, hay truy cập field có thể đổi theo thời gian? Nếu nhiều thread cùng sử dụng, đã xử lý an toàn bộ nhớ và đồng bộ chưa?

### Tình huống tự luyện

**A.** `int x = 4; IntUnaryOperator f = (var n) -> n + x;` rồi thêm `x = 5;` ở dòng sau. Có hợp lệ không?

**B.** `StringBuilder b = new StringBuilder("a"); Runnable r = () -> b.append("b");`. Có hợp lệ không?

**C.** `BiFunction<Integer, Integer, Integer> f = (var x, Integer y) -> x + y;`. Có hợp lệ không?

**Đáp án:** A **không**: `x` mất tính *effectively final* dù phép gán ở sau lambda. B **có**: `b` không bị gán lại, chỉ trạng thái đối tượng thay đổi (với một thread trong ví dụ). C **không**: Java cấm trộn `var` với kiểu tường minh trong cùng danh sách tham số lambda.

## 10. Ghi nhớ trọng tâm

- `var` trên **tham số lambda** là cú pháp được hỗ trợ từ Java 11; kiểu tham số do functional interface quyết định, không phải kiểu động.
- Biến local/parameter **ở ngoài** được lambda capture phải `final` hoặc *effectively final*, đồng thời được gán chắc chắn trước khi sử dụng.
- `final` của một biến tham chiếu không biến đối tượng mà nó trỏ tới thành bất biến.
- Lambda tuân theo **lexical scope**, dùng `this` của lớp bao quanh và không được che khuất một local/parameter bao quanh bằng tên tham số cùng tên.
- Field và đối tượng mutable có thể thay đổi, nhưng hiệu ứng phụ và truy cập đồng thời cần được thiết kế rõ ràng.
- Cú pháp `var` phải nhất quán trong toàn bộ danh sách tham số; annotation/`final` là các tình huống sử dụng quan trọng của JEP 323.

## Tham khảo chính thức

- [OpenJDK JEP 323 — Local-Variable Syntax for Lambda Parameters](https://openjdk.org/jeps/323).
- [Java Language Specification §4.12.4 — `final` và `effectively final`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.12.4).
- [Java Language Specification §6.4 — Shadowing, và §6.5.6.1 — tên biến được capture](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html).
- [Java Language Specification §15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27).
