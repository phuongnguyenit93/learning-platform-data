# Biến effectively final và dữ liệu được giữ bởi lambda trong Java

Lambda expression cho phép code Java tham chiếu các tên khai báo bên ngoài thân lambda, chẳng hạn biến cục bộ và tham số của method bao quanh. Nhưng để **capture biến cục bộ**, compiler yêu cầu biến đó là **final** hoặc **effectively final**. Quy tắc này khác hoàn toàn với việc đối tượng được tham chiếu có mutable hay không, và càng khác với thread safety.

Bài học phân biệt rõ: (1) compiler chấp nhận những biến local nào, (2) giá trị nào được giữ khi lambda được tạo, (3) state nào được đọc vào lúc callback chạy, và (4) điều gì thay đổi khi lambda sống lâu hơn method hoặc được chạy ở thread khác.

## 1. Ví dụ đầu tiên: một lambda capture local variables

Tạo tệp `FirstCapture.java`:

~~~java
import java.util.function.IntFunction;

public final class FirstCapture {
    public static void main(String[] args) {
        int multiplier = 3;
        String prefix = "result=";

        IntFunction<String> format = value -> prefix + value * multiplier;
        System.out.println(format.apply(4));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 --release 17 FirstCapture.java
java FirstCapture
~~~

Stdout chính xác:

~~~text
result=12
~~~

Phân tích:

- `value` là **tham số của lambda**, được nhận khi gọi `format.apply(4)`.
- `multiplier` và `prefix` là **local variables của method `main`**, được lambda tham chiếu từ lexical scope bên ngoài.
- Hai local variables này không được gán lại sau khi khởi tạo, nên là **effectively final**, không cần từ khóa `final`.
- Lambda giữ **giá trị** cần dùng: số nguyên `3` của `multiplier`, và giá trị tham chiếu tới đối tượng `String` của `prefix`.
- Phép nhân và nối chuỗi trong thân lambda được thực hiện **khi `apply` được gọi**, chứ không chạy ngay chỉ vì dòng khai báo lambda đã được thực thi.

`IntFunction<String>` là một *functional interface* (một abstract method `apply(int)`); lambda được kiểm tra kiểu theo target type này. Lambda không phải một method tự do có thể chạy khi không có functional interface tương ứng.

## 2. Quy tắc final và effectively final

**Final local variable:** có khai báo `final`, chỉ được gán một lần theo các quy tắc definite assignment.

~~~java
final int limit = 10;
// limit = 11; // Lỗi biên dịch
~~~

**Effectively final local variable:** không khai báo `final`, nhưng toàn bộ quá trình gán biến thỏa quy tắc có thể xem nó như biến final. Đối với biến khởi tạo ngay ở khai báo, mọi phép gán lại đều phá tính effectively final.

~~~java
int limit = 10;
Runnable print = () -> System.out.println(limit);
print.run(); // In 10
~~~

Cách viết không có `final` vẫn hợp lệ vì không có lần gán khác cho `limit`. Compiler áp dụng quy tắc này cho các biến local/parameters được lambda sử dụng, dù lambda chạy trước hay sau thời điểm có một câu lệnh gán lại.

| Tình huống (mỗi dòng là ví dụ độc lập) | Effectively final? | Vì sao |
| --- | --- | --- |
| `int x = 1;` và chỉ đọc `x` | Có | Một initializer, không gán lại |
| `int x = 1; x = 1;` | Không | Gán thêm lần nữa dù giá trị không đổi |
| `int x = 1; x++;` | Không | Tăng biến là sửa biến |
| `int x = 1; x += 0;` | Không | Phép gán kết hợp vẫn ghi vào biến |
| `int x; x = 1;` | Có nếu không có lần gán khác và đáp ứng definite assignment | Biến chưa khởi tạo được gán một lần |
| `int x; if (flag) x = 1; else x = 2;` | Có nếu không có lần gán khác | Mỗi đường chạy gán đúng một lần |
| `List<String> xs = new ArrayList<>(); xs.add("a");` | Có | Biến tham chiếu không được gán lại |
| `int[] a = {0}; a[0]++;` | Có | Sửa phần tử mảng, không gán lại biến `a` |
| `List<String> xs = new ArrayList<>(); xs = new ArrayList<>();` | Không | Thay giá trị tham chiếu của biến |

Bản chất của **effectively final** là hạn chế **assignment đối với biến**, không phải so sánh hai giá trị bằng `equals` hay kiểm tra đối tượng có bất biến không.

### Gán sau khai báo: definite assignment

Đoạn sau hoàn toàn hợp lệ và runnable:

~~~java
// File: OneAssignment.java
import java.util.function.IntSupplier;

public final class OneAssignment {
    static int choose(boolean flag) {
        int result;
        if (flag) {
            result = 7;
        } else {
            result = 11;
        }
        IntSupplier supplier = () -> result;
        return supplier.getAsInt();
    }

    public static void main(String[] args) {
        System.out.println(choose(true));
        System.out.println(choose(false));
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 OneAssignment.java
java OneAssignment
~~~

Stdout:

~~~text
7
11
~~~

`result` được gán một lần trên mỗi đường chạy. Compiler còn kiểm tra **definite assignment**: biến phải chắc chắn đã có giá trị trước lúc được đọc. `final`/effectively final và definite assignment là hai kiểm tra liên quan nhưng không đồng nhất.

## 3. Những trường hợp capture không được compiler chấp nhận

Những đoạn trong phần này **cố ý sai** để nhận diện compile-time errors.

### Gán lại sau khi tạo lambda

~~~java
int count = 0;
Runnable task = () -> System.out.println(count);
count++;
~~~

Compiler báo lỗi thường có nội dung:

~~~text
local variables referenced from a lambda expression must be final or effectively final
~~~

Không thể biện hộ rằng lambda sẽ chạy *trước khi* `count++`: cả biến local được xét, và `count++` làm nó mất tính effectively final.

### Gán lại trước khi tạo lambda

~~~java
int count = 0;
count = 5;
Runnable task = () -> System.out.println(count);
~~~

Cũng không hợp lệ. Lần gán thứ hai đã xảy ra trước dòng tạo lambda nhưng vẫn tồn tại trên biến `count`.

### Gán lại ngay trong lambda

~~~java
int count = 0;
Runnable task = () -> count++; // Lỗi
~~~

Biến local được capture không thể trở thành đích gán trong thân lambda theo cách này. Viết `count += 1` hay `count = count + 1` vẫn sai.

### Không definitely assigned

~~~java
int count;
Runnable task = () -> System.out.println(count); // Lỗi
~~~

`count` có thể được xem xét là effectively final, nhưng chưa chắc chắn có giá trị trước lúc được lambda tham chiếu. Cần gán hợp lệ trước rồi mới dùng.

### Method parameter cũng chịu quy tắc

~~~java
static Runnable bad(int number) {
    number = number + 1;
    return () -> System.out.println(number); // Lỗi
}
~~~

Tham số `number` được gán lại, nên không effectively final. Cách sửa là dùng local snapshot mới:

~~~java
static Runnable good(int number) {
    int adjusted = number + 1;
    return () -> System.out.println(adjusted);
}
~~~

`adjusted` được tính một lần khi gọi `good` và không bị gán lại.

## 4. Capture primitive và capture reference

Java phân biệt **giá trị primitive** và **giá trị tham chiếu**:

- Với `int amount = 10`, giá trị giữ cho lambda là `10`.
- Với `StringBuilder text = new StringBuilder("a")`, giá trị giữ là **tham chiếu tới đối tượng `StringBuilder`**, không phải bản sao nội dung hiện tại của đối tượng đó.
- Khi lambda được gọi, nó có thể đọc **trạng thái mới của đối tượng cùng được tham chiếu**. Điều này không vi phạm effectively final vì biến `text` chưa bị gán lại.

Tạo tệp `MutableCapture.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

public final class MutableCapture {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        Supplier<Integer> size = () -> words.size();
        words.add("A");
        words.add("B");
        System.out.println(size.get());

        StringBuilder builder = new StringBuilder("hello");
        Supplier<String> current = () -> builder.toString();
        String snapshot = builder.toString();
        Supplier<String> frozen = () -> snapshot;

        builder.append("-java");
        System.out.println(current.get());
        System.out.println(frozen.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 MutableCapture.java
java MutableCapture
~~~

Stdout:

~~~text
2
hello-java
hello
~~~

`size` và `current` giữ tham chiếu tới các đối tượng mutable rồi **gọi method trên đối tượng khi callback chạy**. Còn `frozen` giữ giá trị tham chiếu tới `String` được tạo sẵn bởi `builder.toString()`, nên trả về `"hello"` dù `builder` đã được sửa.

Đây là khác biệt giữa:

~~~java
// Các đoạn minh họa bên trong method có builder tương ứng
Supplier<String> live = () -> builder.toString(); // Đọc state khi gọi get()
String saved = builder.toString();
Supplier<String> once = () -> saved;               // Giữ kết quả đã tính
~~~

Nếu cần snapshot bất biến của cả một collection, việc giữ tham chiếu không đủ: cân nhắc tạo **bản sao phù hợp**, chẳng hạn `List.copyOf(source)` với những điều kiện về phần tử null và tính immutable của các đối tượng bên trong. Bản sao collection cũng không tự deep-copy mutable elements.

## 5. Lambda có thể sống lâu hơn method tạo ra nó

~~~java
// File: EscapingCapture.java
import java.util.function.IntSupplier;

public final class EscapingCapture {
    static IntSupplier make(int seed) {
        int doubled = seed * 2;
        return () -> doubled + 1;
    }

    public static void main(String[] args) {
        IntSupplier result = make(5);
        System.out.println(result.getAsInt());
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 EscapingCapture.java
java EscapingCapture
~~~

Stdout:

~~~text
11
~~~

Method `make(5)` đã return khi `getAsInt()` được gọi, nhưng lambda vẫn sử dụng `doubled = 10`. Không nên hình dung lambda liên tục đọc lại **stack slot của method đã kết thúc**. Compiler/runtime phải cung cấp giá trị capture để callback dùng đúng về sau; implementation cụ thể không nhất thiết tạo một class file cho từng lambda.

Không phải tất cả thân lambda được chạy khi lambda **được tạo**. Ví dụ:

~~~java
int base = 10;
java.util.function.IntSupplier s = () -> base + expensive();
~~~

`base` được giữ; `expensive()` vẫn chạy **mỗi lần `s.getAsInt()`** nếu body được thực thi. Đây chỉ là minh họa trong class có method `expensive()` phù hợp, không phải chương trình hoàn chỉnh. Nếu muốn tính một lần:

~~~java
int computed = expensive();
java.util.function.IntSupplier s = () -> computed;
~~~

Hai cách có hành vi khác nhau khi `expensive()` có side effects, tốn thời gian hoặc trả các giá trị thay đổi.

## 6. Capture trong vòng lặp

### 6.1. Basic `for`: không capture trực tiếp biến `i` bị tăng

~~~java
for (int i = 0; i < 3; i++) {
    Runnable task = () -> System.out.println(i); // Lỗi biên dịch
}
~~~

`i++` khiến biến `i` không effectively final. Java **không mặc định tạo bản sao `i`** riêng cho mỗi lambda theo cú pháp này.

Tạo local snapshot trong mỗi vòng:

~~~java
// File: LoopCapture.java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

public final class LoopCapture {
    public static void main(String[] args) {
        List<Runnable> tasks = new ArrayList<>();

        for (int i = 0; i < 3; i++) {
            int step = i;
            tasks.add(() -> System.out.println(step));
        }

        for (Runnable task : tasks) {
            task.run();
        }

        List<Supplier<String>> letters = new ArrayList<>();
        for (String letter : List.of("A", "B")) {
            letters.add(() -> letter);
        }
        System.out.println(letters.get(0).get() + letters.get(1).get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 LoopCapture.java
java LoopCapture
~~~

Stdout:

~~~text
0
1
2
AB
~~~

`step` là local mới của **mỗi lần thực thi thân vòng**, được khởi tạo bằng giá trị `i` của lần lặp đó. Từng biến `step` đều effectively final.

### 6.2. Enhanced `for` có iteration variable riêng

Với `for (String letter : List.of("A", "B"))`, biến `letter` theo ngữ nghĩa là biến iteration mới trên mỗi lần lặp. Nó có thể được capture nếu không gán lại bên trong body. Do đó hai `Supplier` ở trên trả `"A"` và `"B"` theo đúng thứ tự được đưa vào list.

Nếu bên trong enhanced-for vừa viết `letter = "changed";` vừa capture `letter`, compiler vẫn từ chối vì biến đó không còn effectively final. Đừng đánh đồng enhanced-for variable với basic-for counter `i`.

## 7. Instance/static fields không bị ràng buộc như local variables

Tính effectively final của local/parameter **không có nghĩa mọi field mà lambda đọc đều phải final**.

~~~java
// File: FieldCapture.java
import java.util.function.IntSupplier;

public final class FieldCapture {
    private int value = 1;

    IntSupplier reader() {
        return () -> value;
    }

    public static void main(String[] args) {
        FieldCapture owner = new FieldCapture();
        IntSupplier read = owner.reader();
        owner.value = 7;
        System.out.println(read.getAsInt());
        owner.value = 9;
        System.out.println(read.getAsInt());
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 FieldCapture.java
java FieldCapture
~~~

Stdout:

~~~text
7
9
~~~

Lambda bên trong `reader()` đọc instance field `value` của **enclosing `this`** khi `getAsInt()` được gọi. Field có thể được gán lại, do đó kết quả khác nhau giữa hai lần gọi.

Các **static fields** cũng có thể được lambda đọc, nhưng không vì thế trở thành snapshot. Cả instance fields lẫn static fields đều cần đồng bộ phù hợp nếu được nhiều thread đọc/ghi.

### Muốn snapshot field thì dùng local riêng

~~~java
// Minh họa bên trong instance method của một class có field value
int atCreation = this.value;
IntSupplier frozen = () -> atCreation;
IntSupplier live = () -> this.value;
~~~

`frozen` giữ **giá trị của local** khi tạo lambda; `live` đọc **state hiện tại của field** lúc gọi. Đây là cách chủ động lựa chọn giữa snapshot và live access.

### `this` của lambda và anonymous class

Lambda sử dụng `this` theo **lexical scope**. Trong instance method, `this` bên trong lambda chỉ instance của class đang chứa method; lambda không cung cấp một `this` độc lập để gọi như anonymous inner class.

~~~java
// Minh họa trong instance method
Runnable a = () -> System.out.println(this.toString());

Runnable b = new Runnable() {
    @Override
    public void run() {
        System.out.println(this.toString());
    }
};
~~~

Trong `a`, `this` là enclosing instance. Trong `b`, `this` là instance anonymous class. Cùng sử dụng local variables từ enclosing scope, anonymous class cũng phải tuân theo ràng buộc final/effectively final; tuy nhiên hai loại expression khác nhau về identity/scope và cách biểu diễn.

## 8. Method reference và dữ liệu được giữ

Bound method reference có thể giữ **receiver object**:

~~~java
// Minh họa trong method
StringBuilder builder = new StringBuilder("A");
java.util.function.Supplier<String> read = builder::toString;
builder.append("B");
// read.get() trả "AB"
~~~

Biểu thức receiver `builder` của `builder::toString` được đánh giá khi method reference được tạo. Method `toString()` được gọi sau, khi `get()` chạy. Vì vậy giá trị tham chiếu receiver có thể được giữ trong khi state của receiver vẫn thay đổi.

Đừng đồng nhất `builder::toString` với `builder.toString()`: thứ nhất tạo functional object để gọi method sau; thứ hai **gọi method ngay** và trả một `String`.

Method reference như `Type::staticMethod`, `Type::instanceMethod` và `Type::new` còn có quy tắc target type riêng. Không nên kết luận mọi method reference đều capture local theo cùng một hình thức.

## 9. Lambda chạy đa luồng: effectively final không bảo đảm thread safety

### 9.1. “Mảng một phần tử” có thể compile nhưng vẫn có data race

~~~java
int[] count = {0};
Runnable increment = () -> count[0]++;
increment.run();
System.out.println(count[0]); // 1 nếu chạy tuần tự một lần
~~~

Biến local `count` không bị gán lại, nên effectively final. Phần tử `count[0]` được sửa. Nhưng `count[0]++` gồm đọc, cộng, ghi, **không atomic** khi hai thread cùng thực hiện. Dùng mảng chỉ để “vượt” quy tắc capture sẽ giấu shared mutable state và khiến code khó hiểu.

Các holder objects, `ArrayList`, `StringBuilder`... cũng có thể được capture dưới dạng tham chiếu. Final reference không tự biến operations trên các đối tượng thành thread-safe.

### 9.2. Dùng atomic primitive khi cần shared counter

~~~java
// File: AtomicCapture.java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

public final class AtomicCapture {
    public static void main(String[] args) {
        AtomicInteger counter = new AtomicInteger();

        IntStream.range(0, 1_000)
                .parallel()
                .forEach(i -> counter.incrementAndGet());

        System.out.println(counter.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 AtomicCapture.java
java AtomicCapture
~~~

Stdout:

~~~text
1000
~~~

Tham chiếu `counter` effectively final. Từng `incrementAndGet()` là atomic; sau khi terminal operation `forEach` hoàn tất, tổng đúng là 1000. **Thứ tự xử lý các phần tử trong parallel stream không được bảo đảm**; không dựa vào thứ tự print/update phụ để suy ra tính đúng.

Với mục đích chỉ tính tổng/đếm trong stream, thường đơn giản hơn nếu tránh shared mutable state:

~~~java
long total = java.util.stream.IntStream.range(0, 1_000).parallel().count();
// total là 1000
~~~

Đó là reduction do stream API quản lý, thay vì cập nhật một shared counter từ từng callback.

### 9.3. Visibility và happens-before vẫn là trách nhiệm riêng

Nếu lambda được chạy bởi thread khác, tính effectively final chỉ ràng buộc **local variable binding**. Với một đối tượng mutable được capture, những lần sửa state từ thread này có thể cần `synchronized`, `volatile`, atomic classes hoặc các cơ chế concurrent thích hợp để thread khác nhìn thấy dữ liệu đúng.

`Thread.start()` và `Thread.join()` có những quy tắc *happens-before* liên quan, nhưng không thay thế việc thiết kế đồng bộ các lần đọc/ghi **đang diễn ra đồng thời**. API nhận lambda có thể chạy callback 0 lần, 1 lần hoặc nhiều lần, đồng bộ hoặc bất đồng bộ; cần đọc hợp đồng API, không suy diễn từ cú pháp lambda.

## 10. Compiler biểu diễn capture như thế nào?

Ví dụ:

~~~java
// Minh họa trong method
int offset = 10;
java.util.function.IntUnaryOperator add = x -> x + offset;
~~~

Cần một cách để body của lambda dùng `offset = 10` ngay cả khi method chứa khai báo đã kết thúc. `javac` trong các JDK hiện đại thường biên dịch lambda qua `invokedynamic`, `LambdaMetafactory`, bootstrap metadata và các method tổng hợp kiểu `lambda$...`; captured values có thể được truyền vào khi tạo functional object.

Nhưng **JLS bảo đảm hành vi, không bảo đảm một layout fields/classes/bytecode duy nhất**. Không mặc định:

- Mỗi lambda được tạo thành `Outer$1.class` riêng như anonymous class.
- Mỗi lần đánh giá lambda đều tạo object mới (các lambda không capture có thể được tái sử dụng).
- Tên method tổng hợp hay thứ tự arguments của `invokedynamic` giống nhau trên mọi phiên bản `javac`.
- Lambda capture “con trỏ tới stack local” còn có thể thay đổi sau khi method kết thúc.

Để quan sát bản build thực tế:

~~~bash
javap -c -p FirstCapture
javap -v -p FirstCapture
~~~

`-c` in bytecode instructions, `-p` hiện private/synthetic members và `-v` mở rộng constant pool/bootstrap metadata. Hãy tìm `invokedynamic` và captured arguments, nhưng xem đây là bằng chứng **của compiler/JDK đang dùng**, không phải một mẫu bytecode bắt buộc.

## 11. Chương trình đối chiếu snapshot với state hiện tại

Tệp `CaptureComparison.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.IntSupplier;
import java.util.function.Supplier;

public final class CaptureComparison {
    private int field = 1;

    IntSupplier readField() {
        return () -> field;
    }

    public static void main(String[] args) {
        int local = 7;
        IntSupplier localReader = () -> local;

        CaptureComparison owner = new CaptureComparison();
        IntSupplier liveField = owner.readField();
        int snapshot = owner.field;
        IntSupplier frozenField = () -> snapshot;

        List<String> words = new ArrayList<>();
        Supplier<Integer> size = words::size;

        owner.field = 9;
        words.add("one");
        words.add("two");

        System.out.println(localReader.getAsInt());
        System.out.println(liveField.getAsInt());
        System.out.println(frozenField.getAsInt());
        System.out.println(size.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 CaptureComparison.java
java CaptureComparison
~~~

Stdout:

~~~text
7
9
1
2
~~~

| Biểu thức | Giá trị giữ/đọc | Kết quả |
| --- | --- | --- |
| `() -> local` | Capture primitive local `7` | `7` |
| `() -> field` trong `readField()` | Lambda dùng enclosing instance, đọc field khi gọi | `9` |
| `() -> snapshot` | Capture local `snapshot = 1` | `1` |
| `words::size` | Giữ receiver `words`, gọi `size()` khi dùng | `2` |

Ví dụ chạy tuần tự nên kết quả không yêu cầu bảo đảm visibility giữa các thread. Nếu dùng kiểu đọc/ghi mutable field tương tự trong nhiều thread, cần thiết kế cơ chế đồng bộ.

## 12. Lỗi thường gặp và hướng sửa

| Lỗi/nhầm lẫn | Nguyên nhân | Cách giải quyết |
| --- | --- | --- |
| `local variables referenced from a lambda expression must be final or effectively final` | Local/parameter bị gán lại | Giữ local ổn định hoặc tạo snapshot local mới |
| Biến trong lambda chưa khởi tạo | Vi phạm definite assignment | Gán hợp lệ trên mọi đường chạy trước khi capture |
| Mong lambda thấy giá trị mới của local sau `x = ...` | Local capture giữ giá trị; gán lại còn gây lỗi compile | Nếu cần state sống, dùng field/holder có ownership rõ |
| Mong `final List` bất biến | Final chỉ chặn gán lại tham chiếu | Dùng immutable data hoặc snapshot nếu cần |
| Basic-for `i++` bị báo lỗi capture | `i` không effectively final | `int step = i` trong body mỗi iteration |
| Dùng `int[1]` để chia sẻ counter giữa threads | Phép tăng không atomic | Dùng reduction/AtomicInteger hoặc đồng bộ phù hợp |
| Lambda chạy sau khi method return, nghĩ local biến mất | Đã capture giá trị cần dùng | Không cần giữ stack frame của method |
| Nhầm `this` trong lambda với anonymous class | Lexical `this` khác | Viết `Outer.this`/receiver tường minh khi cần |
| Gọi lambda là tính sẵn body | Tạo lambda khác gọi functional method | Phân biệt thời điểm tạo và thời điểm gọi |
| Nghĩ `javap` phải hiện `Outer$1.class` | Implementation lambda không bắt buộc tạo class file | Dùng `javap -v`, xem call site thực tế |

## 13. Checklist và tự kiểm tra

Trước khi viết callback, lần lượt xác định: tên nào là local/parameter phải effectively final; tên nào là field có thể đọc động; đang cần snapshot hay state mới; callback có thể chạy sau method hay ở thread khác không; callback có được gọi nhiều lần/đồng thời không; và có thể dùng reduction/immutable input thay shared mutation hay không.

**Câu 1.** `int a = 2; Runnable r = () -> System.out.println(a);` hợp lệ không?  
**Có**, nếu `a` không bị gán lại; nó effectively final dù không ghi `final`.

**Câu 2.** `int a = 2; a = 2;` còn effectively final không?  
**Không.** Gán lại bằng cùng giá trị vẫn là lần gán thứ hai.

**Câu 3.** Lambda capture `List` rồi gọi `list.add(...)` có lỗi không?  
**Không nếu biến tham chiếu không bị gán lại**. Nhưng list mutable và có thể đòi hỏi đồng bộ khi dùng đa luồng.

**Câu 4.** Vì sao lambda tạo ở method đã return vẫn hoạt động?  
Giá trị local cần capture được giữ để thực thi callback về sau; không dựa vào việc stack frame ban đầu còn sống.

**Câu 5.** Vì sao basic `for` không capture trực tiếp `i`?  
`i++` thay đổi `i`; cần local `step = i` riêng trong mỗi vòng.

**Câu 6.** `final int[] count = {0}` và lambda `() -> count[0]++` có thread-safe?  
**Không mặc nhiên.** Final reference không làm phép tăng phần tử atomic.

**Câu 7.** Lambda đọc instance field thay đổi sau khi tạo có thể thấy giá trị mới?  
**Có trong chương trình tuần tự**, vì đọc field được thực hiện khi gọi callback. Trong đa luồng cần thêm quy tắc visibility.

**Câu 8.** `this` của lambda trong instance method là gì?  
Là enclosing instance theo lexical context, khác `this` của anonymous class.

**Câu 9.** Cần giá trị field tại thời điểm tạo lambda?  
Đọc field vào local `int snapshot = this.field;` rồi capture local không gán lại.

**Câu 10.** Lambda không capture có bắt buộc tạo một instance mới mỗi lần không?  
**Không có bảo đảm như vậy.** Không dựa vào object identity của lambda.

### Tài liệu chuẩn

- [Java Language Specification §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): effectively final và definite assignment.
- [Java Language Specification §15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): phạm vi và ngữ nghĩa lambda.
- [Java Language Specification §15.13 — Method Reference Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.13): bound receiver và method references.
- [Java Language Specification §17.4 — Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4): visibility, happens-before và đa luồng.

**Ghi nhớ:** effectively final là quy tắc **không gán lại biến local/parameter**. Lambda có thể giữ **giá trị primitive hoặc giá trị tham chiếu** đã capture; nó không tự đóng băng đối tượng mutable. Nếu callback chạy bất đồng bộ, thread safety là một trách nhiệm riêng cần thiết kế rõ ràng.
