# Bắt giữ biến cục bộ final và effectively final trong Java

Một **lambda expression** có thể đọc các biến trong phạm vi nơi nó được khai báo, kể cả biến cục bộ của phương thức bao quanh. Khi lambda sử dụng một biến cục bộ như vậy, ta gọi đó là **bắt giữ biến (variable capture)**. Java quy định rằng biến cục bộ được bắt giữ phải là **`final` hoặc effectively final**: sau khi được gán giá trị hợp lệ, biến không bị gán lại.

Điểm cốt lõi là phân biệt **biến cục bộ** với **đối tượng mà biến tham chiếu**. Không gán lại một biến tham chiếu không có nghĩa là đối tượng nó trỏ tới bất biến. Quy tắc này cũng khác với việc truy cập các **field** của một đối tượng.

Bài học tập trung vào lambda trong Java 17+, nhưng nguyên tắc bắt giữ tương tự cũng áp dụng khi anonymous class sử dụng biến cục bộ ở phạm vi bao quanh.

Sau bài này, bạn sẽ:
- Xác định đúng biến local nào được lambda phép sử dụng và ý nghĩa của `final` so với *effectively final*.
- Dự đoán lỗi biên dịch khi gán lại, tăng biến đếm, hoặc dùng local chưa được gán chắc chắn.
- Phân biệt việc capture tham chiếu với việc thay đổi trạng thái đối tượng, và phân biệt local với instance/static field.
- Viết callback, `Supplier`, `Runnable`, lambda trong vòng lặp với giá trị cần nhớ rõ ràng.
- Hiểu rủi ro của trạng thái mutable và concurrency khi lambda chạy ở thời điểm khác hoặc trên thread khác.

## 1. Scope và variable capture

**Scope (phạm vi)** là vùng mã nơi tên biến có thể được truy cập hợp lệ. Một lambda có thể dùng tham số của chính nó, biến local được khai báo trong lambda, các local ở phạm vi bao quanh, cũng như field có thể truy cập của class.

Ví dụ minh họa:

```java
String prefix = "Order-"; // local ở phương thức bao quanh
java.util.function.Function<Integer, String> label =
        id -> prefix + id; // id là tham số lambda; prefix được capture
String result = label.apply(7); // "Order-7"
```

Các dòng trên là **mảnh mã đặt trong một phương thức**, không phải một chương trình độc lập. `prefix` được tạo ở ngoài, nhưng lambda có thể đọc nó vì nằm trong phạm vi hợp lệ. Ngược lại, `id` chỉ là tham số của lambda, không tồn tại bên ngoài thân lambda.

**Capture không đồng nghĩa thực thi ngay:** gán lambda cho `label` tạo một đối tượng hành vi có thể dùng sau. Phép nối chuỗi bên trong chỉ diễn ra khi `apply(7)` được gọi.

Trong Java, local variables tồn tại theo phạm vi thực thi của phương thức/khối chứa chúng, còn lambda có thể tồn tại và được gọi sau khi phương thức bao quanh đã trở về. Ràng buộc final/effectively final góp phần tránh những tình huống khó hiểu nếu người viết kỳ vọng lambda và phương thức cùng thay đổi một biến cục bộ.

## 2. final và effectively final có nghĩa gì?

### 2.1. final tường minh

Một biến local được khai báo `final` không được gán giá trị mới sau lần gán hợp lệ:

```java
final int base = 10;
java.util.function.IntUnaryOperator addBase = x -> x + base;
int result = addBase.applyAsInt(3); // 13
```

Dùng `final` để compiler ngăn việc gán lại tên biến. Điều này giúp thể hiện cam kết trong mã nguồn, đặc biệt khi biến có vai trò hằng giá trị của một tác vụ.

### 2.2. Effectively final (final theo thực tế sử dụng)

Một biến không khai báo `final` vẫn được coi là *effectively final* nếu theo quy tắc ngôn ngữ nó không bị gán lại sau lần gán hợp lệ. Đây là cách viết rất phổ biến:

```java
int base = 10; // không ghi final
java.util.function.IntUnaryOperator addBase = x -> x + base;
int result = addBase.applyAsInt(3); // 13
```

Vì `base` không hề được gán lại, compiler cho phép lambda bắt giữ. Việc thêm từ khóa `final` vào biến này không làm thay đổi kết quả ví dụ.

**Effectively final là điều kiện tại thời điểm biên dịch**, không phải một phép kiểm tra trạng thái động khi chương trình đang chạy. Chỉ vì hiện tại biến chưa bị gán lại ở một nhánh thực thi cụ thể không có nghĩa là nó được phép capture nếu mã nguồn có phép gán lại không phù hợp.

| Khai báo local | Lambda có thể capture? | Lý do |
| --- | --- | --- |
| `final int threshold = 5;` | Có | Final tường minh và đã được gán. |
| `int threshold = 5;` rồi không gán lại | Có | Effectively final. |
| `int threshold = 5; threshold = 6;` | Không | Có phép gán lại. |
| `int count = 0; count++;` | Không | `++` sửa giá trị của biến. |
| `int count = 0; count += 1;` | Không | Phép gán kết hợp cũng thay đổi biến. |
| `final StringBuilder buffer = new StringBuilder(); buffer.append("x");` | Có | Biến tham chiếu không bị gán lại, dù đối tượng có thay đổi. |

Một biến local chưa có initializer vẫn có thể được gán một lần theo những đường thực thi được compiler chấp nhận, nhưng phải thỏa **definite assignment** (đã được gán chắc chắn trước khi lambda capture) và quy tắc effectively final. Khi muốn mã rõ ràng, hãy khởi tạo giá trị trước khi tạo lambda.

## 3. Ví dụ hoàn chỉnh: final và effectively final

Lưu thành **`LocalCaptureDemo.java`**:

```java
import java.util.function.Function;
import java.util.function.IntUnaryOperator;
import java.util.function.Supplier;

public class LocalCaptureDemo {
    public static void main(String[] args) {
        // Không khai báo final, nhưng không bao giờ gán lại.
        String prefix = "ID-";
        int maxLength = 5;

        Function<String, String> formatter = text ->
                prefix + text.substring(0, Math.min(text.length(), maxLength));

        // final tường minh.
        final int multiplier = 3;
        IntUnaryOperator triple = value -> value * multiplier;

        Supplier<String> greeting = () -> "Xin chào Java";

        System.out.println(formatter.apply("functional"));
        System.out.println("6 x 3 = " + triple.applyAsInt(6));
        System.out.println(greeting.get());
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 LocalCaptureDemo.java
java LocalCaptureDemo
```

**Stdout chính xác:**

```text
ID-funct
6 x 3 = 18
Xin chào Java
```

`prefix` và `maxLength` là effectively final; `multiplier` là final tường minh. Cả ba đều được phép capture. Kết quả `"functional"` lấy năm ký tự đầu là `"funct"`; kết hợp với `"ID-"` được `"ID-funct"`. `greeting` không cần capture biến local nào nhưng vẫn là lambda không tham số hợp lệ.

Vì `substring` yêu cầu đầu vào khác null, đoạn này giả định `formatter.apply` nhận chuỗi không null. Capture không tự bảo vệ khỏi `NullPointerException` hay các lỗi dữ liệu khác.

## 4. Những trường hợp gán lại gây lỗi biên dịch

Những mảnh mã sau **cố ý không biên dịch được**. Đừng trộn chúng vào chương trình chạy được ở phần trước.

### 4.1. Gán lại sau khi tạo lambda

```java
int bonus = 5;
java.util.function.IntUnaryOperator add = x -> x + bonus;
bonus = 10; // lỗi: bonus không effectively final
```

Quy tắc áp dụng cho **toàn bộ khai báo biến** trong phạm vi liên quan, không phải chỉ xét xem `bonus` đã đổi giá trị trước hay sau lần gọi `add.applyAsInt(...)`.

### 4.2. Gán lại trước khi tạo lambda

```java
int bonus = 5;
bonus = 10;
java.util.function.IntUnaryOperator add = x -> x + bonus; // lỗi
```

Lỗi vẫn xảy ra vì `bonus` đã được gán lại. Đặt lambda phía sau phép gán lại không tự biến biến đó thành effectively final.

### 4.3. Toán tử ++ và phép gán kết hợp

```java
int count = 0;
Runnable print = () -> System.out.println(count);
count++; // lỗi khi count được capture
```

`count += 1` hay `count = count + 1` cũng làm mất effectively final. Việc compiler có đánh dấu lỗi tại dòng lambda hay tại phép sửa biến có thể khác theo thông báo cụ thể, nhưng cặp hành vi capture và gán lại này không hợp lệ.

### 4.4. Local chưa được gán chắc chắn

```java
String message;
Runnable print = () -> System.out.println(message); // lỗi: chưa definitely assigned
message = "ready";
```

Ngoài effectively final, Java còn yêu cầu biến local được **gán chắc chắn** trước khi lambda sử dụng theo quy tắc definite assignment. Để tránh lỗi, hãy gán `message` trước khi tạo lambda.

### 4.5. Vì sao không dùng “hộp” mutable chỉ để vượt compiler?

Có thể đưa một giá trị vào mảng một phần tử hoặc object holder rồi capture tham chiếu final. Điều đó biên dịch, nhưng đưa trạng thái mutable vào luồng thực thi và có thể gây lỗi đồng bộ khi dùng đa luồng. Đừng mặc định coi `int[] count = {0};` là cách giải quyết tốt cho mọi trường hợp; trước tiên hãy cân nhắc phép biến đổi trả kết quả, vòng lặp thông thường hoặc cơ chế tổng hợp dữ liệu đúng mục tiêu.

## 5. final của tham chiếu khác với immutable của đối tượng

Một local giữ tham chiếu có thể là final hoặc effectively final trong khi **nội dung đối tượng vẫn thay đổi**. Ví dụ đầy đủ:

Lưu thành **`MutableReferenceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

public class MutableReferenceDemo {
    public static void main(String[] args) {
        final StringBuilder buffer = new StringBuilder("A");
        Supplier<String> view = () -> buffer.toString();

        System.out.println("Trước: " + view.get());
        buffer.append("B");
        System.out.println("Sau: " + view.get());

        List<String> messages = new ArrayList<>();
        Runnable add = () -> messages.add("done");
        add.run();
        System.out.println("Danh sách: " + messages);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MutableReferenceDemo.java
java MutableReferenceDemo
```

**Stdout chính xác:**

```text
Trước: A
Sau: AB
Danh sách: [done]
```

`buffer` là final nên không thể viết `buffer = new StringBuilder("C");`. Nhưng `buffer.append("B")` sửa nội dung đối tượng đã được tham chiếu; hoàn toàn không phải phép gán lại biến `buffer`. Tương tự, `messages` không bị gán lại nên lambda có thể gọi `messages.add(...)`.

Về mặt ngữ nghĩa, lambda giữ khả năng truy cập **cùng đối tượng**, vì thế lần gọi `view.get()` sau thấy nội dung đã sửa. Đây là khác biệt giữa **bất biến của tên biến local** và **bất biến của trạng thái đối tượng**.

Đổi trạng thái đối tượng thông qua lambda có thể là hợp lệ, nhưng cần suy nghĩ về side effect. Nếu lambda chạy trong Stream, callback bất đồng bộ hoặc nhiều thread, danh sách `ArrayList` và `StringBuilder` ở ví dụ trên **không tự bảo đảm an toàn luồng**. `final` chỉ ngăn việc gán lại biến tham chiếu, không tự tạo cơ chế khóa hoặc bảo đảm tính nhất quán của các thao tác trên object.

## 6. Field không chịu cùng hạn chế capture local

**Biến cục bộ** và **instance/static field** có hợp đồng khác nhau. Quy tắc final/effectively final ở đây áp dụng cho local variables, formal parameters hoặc exception parameters được dùng từ phạm vi bao quanh; **không bắt buộc instance field hoặc static field phải final** để lambda đọc hoặc sửa.

Ví dụ hoàn chỉnh lưu thành **`FieldCaptureDemo.java`**:

```java
public class FieldCaptureDemo {
    private int counter;
    private static int total;

    void runExample() {
        Runnable increment = () -> {
            counter++;
            total++;
        };

        increment.run();
        increment.run();

        System.out.println("instance=" + counter);
        System.out.println("static=" + total);
    }

    public static void main(String[] args) {
        new FieldCaptureDemo().runExample();
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 FieldCaptureDemo.java
java FieldCaptureDemo
```

**Stdout chính xác:**

```text
instance=2
static=2
```

`counter` thuộc đối tượng `FieldCaptureDemo`; `total` thuộc class. Lambda trong instance method có thể truy cập và sửa chúng, nên cả hai đều tăng hai lần. Tuy nhiên, **biên dịch được không có nghĩa là an toàn khi nhiều thread cùng tăng**: `counter++` và `total++` không phải phép tăng atomic. Nếu có chạy đồng thời, cần chọn cơ chế đồng bộ phù hợp với yêu cầu.

### this trong lambda và anonymous class

Trong lambda được khai báo ở instance context, `this` trỏ tới **instance bao quanh**, không phải một đối tượng “lambda” có `this` riêng. Có thể viết `() -> this.counter++` tương đương truy cập field ở ví dụ trên.

Trái lại, trong một **anonymous class** triển khai `Runnable`, `this` bên trong phần triển khai chỉ tới instance của anonymous class đó. Đây là một khác biệt quan trọng khi chuyển anonymous class thành lambda.

## 7. Capture trong vòng lặp: giữ snapshot hợp lệ

Biến điều khiển của vòng `for` cổ điển thường được cập nhật ở mỗi vòng lặp, vì vậy không effectively final:

```java
for (int i = 0; i < 3; i++) {
    // SAI: i được tăng trong điều kiện cập nhật của for.
    // tasks.add(() -> System.out.println(i));
}
```

Muốn mỗi callback nhớ một giá trị của vòng lặp, tạo **biến local mới không bị gán lại** bên trong thân vòng lặp.

Lưu thành **`LoopCaptureDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class LoopCaptureDemo {
    public static void main(String[] args) {
        List<Runnable> actions = new ArrayList<>();

        for (int i = 0; i < 3; i++) {
            final int snapshot = i;
            actions.add(() -> System.out.println("index=" + snapshot));
        }

        actions.forEach(Runnable::run);

        List<Runnable> names = new ArrayList<>();
        for (String item : List.of("A", "B")) {
            names.add(() -> System.out.println("item=" + item));
        }

        names.forEach(Runnable::run);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 LoopCaptureDemo.java
java LoopCaptureDemo
```

**Stdout chính xác:**

```text
index=0
index=1
index=2
item=A
item=B
```

Giải thích:
1. `i` trong `for (int i = 0; i < 3; i++)` thay đổi nên không thể capture trực tiếp.
2. Mỗi lần thực hiện thân vòng lặp tạo một `snapshot` riêng, được gán một lần và không đổi. Mỗi lambda capture giá trị `snapshot` tương ứng.
3. Với **enhanced for** (`for (String item : ...)`), biến `item` của mỗi lượt lặp được coi là biến riêng cho lượt đó. Nếu không gán lại `item`, lambda có thể capture trực tiếp.
4. `actions.forEach(Runnable::run)` chạy các callback lần lượt theo thứ tự danh sách, nên stdout có thể dự đoán chính xác như trên. Nếu thay bằng tác vụ bất đồng bộ, không được suy luận các dòng log sẽ luôn xuất hiện cùng thứ tự.

Ví dụ này cũng cho thấy callback có thể được **tạo trong vòng lặp nhưng chạy sau khi vòng lặp kết thúc**. Capture giúp mỗi callback giữ đúng dữ liệu của lượt tạo ra nó.

## 8. Các lưu ý về thời điểm thực thi và trạng thái

### 8.1. Lambda có thể chạy sau khi phương thức khai báo kết thúc

```java
static java.util.function.Supplier<String> makeSupplier(String prefix) {
    return () -> prefix + "Java";
}
```

Đoạn minh họa này có thể đặt trong một class. Sau khi `makeSupplier("Hello ")` trả về, caller vẫn có thể gọi `supplier.get()` và nhận `"Hello Java"`. Tham số `prefix` là effectively final nếu không bị gán lại trong phương thức.

Không nên hiểu rằng Java giữ nguyên toàn bộ stack frame của phương thức cho lambda. Điều quan trọng là lambda có thể tiếp tục sử dụng **giá trị hoặc tham chiếu đã capture** theo ngữ nghĩa được bảo đảm bởi ngôn ngữ; chi tiết bytecode và tối ưu hóa do compiler/runtime quyết định.

### 8.2. Capture tham chiếu không tạo bản sao sâu

Với `String` immutable, giá trị chuỗi đã capture là đơn giản để suy luận. Với `List`, `StringBuilder` hoặc đối tượng nghiệp vụ mutable, lambda vẫn có thể quan sát sửa đổi sau này của **cùng object**. Muốn nội dung không đổi, tạo dữ liệu bất biến hoặc bản sao độc lập có độ sâu phù hợp trước khi capture:

```java
List<String> snapshot = List.copyOf(source);
java.util.function.Supplier<List<String>> reader = () -> snapshot;
```

Đây là mảnh mã minh họa với `source` là `List<String>` đã có. `List.copyOf` tạo danh sách không thể sửa cấu trúc qua API của nó và từ chối phần tử null, nhưng **không tự sao chép sâu** các đối tượng bên trong. Đối với các `String` bất biến, tính chất đó phù hợp; với phần tử là object mutable, cần cân nhắc tạo bản sao các phần tử.

### 8.3. Concurrency và visibility

`final` hoặc effectively final **không tự làm mọi phép truy cập thread-safe**. Nếu lambda giữ tham chiếu đến một object mutable và được gọi từ nhiều thread, vẫn phải xử lý đồng bộ, visibility và race condition theo Java Memory Model.

Ví dụ, `AtomicInteger` có thể phù hợp cho bộ đếm cập nhật đồng thời đơn giản, nhưng không thay thế thiết kế đồng bộ cho nhiều trạng thái liên quan. Với Stream, ưu tiên `map`, `filter`, `reduce` và collector phù hợp thay vì sửa một `ArrayList` chung trong lambda song song.

### 8.4. Tính thuần và kiểm thử

Lambda bắt giữ một giá trị bất biến rồi tính kết quả thuần thường dễ kiểm thử. Lambda phụ thuộc vào object mutable, field toàn cục hoặc I/O có thể cho kết quả khác nhau giữa các lần gọi cùng đối số. Khi thiết kế API, cân nhắc truyền đầu vào trực tiếp hoặc chụp snapshot nếu cần khả năng tái lập.

## 9. Quy tắc về phạm vi tên trong lambda

Lambda trong Java có phạm vi tên gần với khối chứa nó. Nó **không cho phép khai báo lại tên biến local ở phạm vi bao quanh** bằng tên tham số hoặc local trong lambda.

**Ví dụ cố ý sai:**

```java
int value = 7;
java.util.function.IntUnaryOperator f = value -> value * 2;
// Sai: tham số lambda có tên value trùng biến local ở phạm vi bao quanh.
```

Cách sửa:

```java
int value = 7;
java.util.function.IntUnaryOperator f = x -> x + value;
```

Trong ví dụ đúng, `x` là tham số lambda, `value` là local effectively final được capture.

Các quy tắc khác:
- Local khai báo **bên trong thân lambda** có scope riêng của khối đó, nhưng không thể trùng tên với local đang ở phạm vi bao quanh.
- Tham số lambda và biến local của phương thức bao quanh đều có quy tắc truy cập từ scope của chúng; `this` không trở thành một biến local mới của lambda.
- Không thể dùng biến local nằm ngoài phạm vi lexical của lambda. Capture không cho phép vượt qua quy tắc scope thông thường.

## 10. Cách chọn thiết kế thay vì “vượt qua” final

| Nhu cầu thực tế | Thiết kế phù hợp | Điều cần chú ý |
| --- | --- | --- |
| Truyền một cấu hình không đổi vào callback | Capture local final/effectively final | Đơn giản, dễ đọc và dễ kiểm thử. |
| Lưu chỉ số mỗi lượt `for` | Tạo `snapshot` trong thân vòng lặp | Mỗi callback có giá trị riêng. |
| Thực hiện phép tính tích lũy | Dùng `reduce`, `collect` hoặc vòng lặp rõ ràng | Tránh side effect trên biến bao quanh. |
| Đếm với nhiều thread | `AtomicInteger` hoặc cơ chế đồng bộ phù hợp | Atomic một biến không bảo đảm invariant nhiều biến. |
| Đọc một danh sách có thể bị sửa sau | Chụp snapshot trước khi capture | Xem xét shallow/deep copy. |
| Cập nhật state của object | Truy cập field theo hợp đồng object | Cân nhắc đồng bộ và thread ownership. |

Thay vì viết `int count = 0; list.forEach(x -> count++);` (không biên dịch), có thể dùng `long count = list.stream().filter(predicate).count();` khi mục tiêu là đếm phần tử thỏa điều kiện. Đây là chuyển đổi từ side effect sang phép tính kết quả rõ ràng. Nếu nhu cầu chỉ là một vòng lặp tuần tự có nhiều hành động, vòng `for` thường đơn giản hơn việc cố ép logic vào lambda.

## 11. Lỗi phổ biến và cách nhận biết

1. **Hiểu `final` là object bất biến:** final khóa biến tham chiếu, không khóa trạng thái object.
2. **Gán lại local đã được capture:** `x = ...`, `x++`, `x += ...` khiến biến không effectively final.
3. **Cho rằng gán lại trước lambda là hợp lệ:** effectively final xét toàn bộ khai báo biến, không chỉ khoảng thời gian sau khi tạo lambda.
4. **Capture `i` của vòng `for` cổ điển:** `i` bị tăng; tạo `final int snapshot = i` bên trong thân vòng lặp.
5. **Cho rằng enhanced for cũng luôn lỗi:** mỗi lượt enhanced for có biến riêng và có thể capture khi nó không bị gán lại.
6. **Dùng local chưa chắc chắn được khởi tạo:** Java cần definite assignment trước khi sử dụng trong lambda.
7. **Khai báo tên tham số trùng local bao quanh:** lambda không được shadow local đang trong scope.
8. **Nhầm field với local:** field không chịu quy tắc effectively final dành cho capture local, nhưng vẫn có các quy tắc truy cập và concurrency khác.
9. **Cho rằng capture sao chép sâu object:** tham chiếu mutable vẫn trỏ tới object có thể bị thay đổi.
10. **Dùng mảng/holder mutable để “né” compiler rồi chạy parallel:** có thể gây lost updates và race condition.
11. **Cho rằng tạo lambda lập tức chạy code:** thân lambda chạy khi functional method được gọi, trừ các biểu thức ngoài thân được đánh giá khi tạo lambda.
12. **Dựa vào thứ tự thực thi callback bất đồng bộ:** các giá trị được capture có thể đúng, nhưng thứ tự chạy và log không được bảo đảm nếu không có cơ chế phối hợp.

## 12. Tự kiểm tra

**Câu 1.** Vì sao đoạn này hợp lệ?

```java
int offset = 3;
java.util.function.IntUnaryOperator plus = n -> n + offset;
```

Vì `offset` được gán một lần rồi không thay đổi: nó **effectively final** dù không ghi `final`.

**Câu 2.** Nếu thêm `offset++` sau khi tạo `plus`, mã có hợp lệ?

**Không.** `offset` không còn effectively final. Thứ tự “tạo lambda trước, sửa biến sau” không giúp hợp lệ.

**Câu 3.** `final StringBuilder sb = new StringBuilder("A"); Runnable r = () -> sb.append("B");` có hợp lệ?

**Có.** Lambda sửa trạng thái object chứ không gán lại `sb`. Trong ứng dụng đa luồng vẫn cần chú ý an toàn luồng.

**Câu 4.** Vì sao `for (int i=0; i<3; i++) callbacks.add(() -> use(i));` lỗi?

Vì `i` thay đổi trong vòng lặp nên không effectively final. Tạo `final int snapshot = i;` trong thân vòng lặp rồi capture `snapshot`.

**Câu 5.** Field `counter` của class có thể tăng trong lambda không?

**Có.** Chỉ số lần cập nhật đồng thời cần xử lý nếu nhiều thread cùng thay đổi field; đây là vấn đề concurrency, không phải lỗi effectively final.

**Câu 6.** Lambda capture `List<String> items` có thấy thay đổi khi người khác `items.add(...)` không?

**Có thể thấy**, vì nó giữ cùng tham chiếu object. Tuy nhiên khi chạy đồng thời mà không đồng bộ, không được giả định visibility hoặc trạng thái nhất quán. Nếu cần dữ liệu cố định, chụp snapshot và bảo đảm phần tử phù hợp với yêu cầu bất biến.

**Ghi nhớ:** **Local đã được capture phải final hoặc effectively final; field và trạng thái object tuân theo những quy tắc khác.** Phân biệt rõ ba khái niệm này sẽ giúp bạn viết callback an toàn, hiểu lambda chạy muộn và thiết kế xử lý dữ liệu dễ kiểm thử.
