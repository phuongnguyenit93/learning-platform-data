# Capture biến `final` hoặc `effectively final` trong Java Lambda

## 1. Capture là gì và tại sao cần hiểu?

Khi một lambda dùng một biến được khai báo ở phạm vi bao quanh thay vì nhận biến đó qua tham số của chính lambda, ta gọi đó là **capture biến** (bắt giữ biến). Cơ chế này cho phép truyền một hành vi đồng thời mang theo ngữ cảnh cần thiết.

Ví dụ:

~~~java
int minimumScore = 70;
java.util.function.IntPredicate isPassed =
        score -> score >= minimumScore;
~~~

Lambda nhận tham số `score`, nhưng dùng thêm `minimumScore` được khai báo bên ngoài. `minimumScore` là **biến local được capture**; `score` là **tham số lambda**, không phải biến capture.

Capture rất hữu ích khi xây callback, bộ lọc, bộ chuyển đổi, tác vụ trì hoãn hoặc hàm tạo ra một hàm khác. Tuy nhiên, Java đặt quy tắc quan trọng: **biến local hoặc tham số phương thức được lambda capture phải là `final` hoặc `effectively final`.** Quy tắc này có từ Java 8 và tiếp tục áp dụng trong các bản Java hiện đại.

Điều kiện này áp dụng cho **biến local**, bao gồm cả biến local được khai báo bên trong một phương thức hoặc khối, và các tham số. Nó **không cấm lambda đọc/ghi field của đối tượng hoặc static field**. Cũng không có nghĩa mọi đối tượng được capture đều bất biến.

## 2. Phân biệt `final` và `effectively final`

| Khái niệm | Điều kiện | Ví dụ |
| --- | --- | --- |
| `final` | Có từ khóa `final`; biến không được gán giá trị mới sau khi khởi tạo hợp lệ. | `final int limit = 70;` |
| `effectively final` | Không khai báo `final`, nhưng trong thực tế biến không bị gán lại sau khi đã được gán giá trị ban đầu. | `int limit = 70;` và không gán lại `limit` |
| Không effectively final | Biến được gán lại hoặc tăng/giảm trong cùng phạm vi, dù việc gán xảy ra sau vị trí viết lambda. | `limit = 80;`, `limit++;` |

Ví dụ hợp lệ:

~~~java
final int fixedMinimum = 70;
int currentMinimum = 60;

java.util.function.IntPredicate first =
        score -> score >= fixedMinimum;
java.util.function.IntPredicate second =
        score -> score >= currentMinimum;
~~~

`currentMinimum` vẫn được capture dù không có từ khóa `final`, vì nó **effectively final**. Trình biên dịch phân tích những phép gán trong phạm vi của biến để xác định quy tắc này.

Ví dụ **cố ý không biên dịch**:

~~~java
int minimum = 70;
java.util.function.IntPredicate passed = score -> score >= minimum;
minimum = 80; // Lỗi biên dịch: minimum không còn effectively final
~~~

Không thể lập luận rằng “lambda được tạo trước khi đổi biến” để cho phép đoạn trên: điều kiện effectively final áp dụng cho **toàn bộ biến local**. Tương tự, `minimum++`, `minimum += 10` hoặc gán lại một tham số đã được capture đều phá vỡ điều kiện.

Trong quy tắc **definite assignment** của Java, biến local có thể được khai báo trước rồi được gán một lần trước khi dùng trong lambda. Chẳng hạn:

~~~java
int threshold;
threshold = 70; // Gán ban đầu một lần
java.util.function.IntPredicate eligible = value -> value >= threshold;
~~~

Đoạn trên hợp lệ. Điều cốt lõi là biến đã chắc chắn có giá trị khi được dùng và không bị gán lại. Từ khóa `final` thể hiện chủ ý rõ ràng; `effectively final` giảm phần cú pháp lặp mà vẫn đảm bảo cùng ràng buộc cho capture.

### Tham số phương thức cũng phải effectively final

Một phương thức trả về lambda:

~~~java
static java.util.function.IntPredicate greaterThan(int limit) {
    return value -> value > limit;
}
~~~

`limit` là tham số của `greaterThan` và được capture. Khi `greaterThan` trả về, callback vẫn dùng được giá trị `limit` của lần gọi đã tạo nó. Nếu trong thân `greaterThan` có `limit++` hoặc `limit = ...`, capture sẽ không hợp lệ.

## 3. Ví dụ chạy đầy đủ: lọc dữ liệu và trả về lambda đã capture

Tạo tệp **CaptureBasicsDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class CaptureBasicsDemo {
    static final class Student {
        private final String name;
        private final int score;

        Student(String name, int score) {
            this.name = name;
            this.score = score;
        }

        String getName() {
            return name;
        }

        int getScore() {
            return score;
        }
    }

    static Predicate<Student> passingAtLeast(int threshold) {
        return student -> student.getScore() >= threshold;
    }

    public static void main(String[] args) {
        int minimumScore = 70; // effectively final
        final String label = "Pass: "; // explicitly final

        List<Student> students = Arrays.asList(
                new Student("An", 85),
                new Student("Binh", 60),
                new Student("Chi", 70)
        );

        List<String> passed = students.stream()
                .filter(student -> student.getScore() >= minimumScore)
                .map(student -> label + student.getName())
                .collect(Collectors.toList());

        System.out.println(passed);

        Predicate<Student> higherThreshold = passingAtLeast(80);
        System.out.println(
                higherThreshold.test(new Student("Dung", 82))
        );
    }
}
~~~

Biên dịch và chạy bằng JDK 17+; toàn bộ tính năng dùng trong ví dụ đã có từ Java 8:

~~~bash
javac CaptureBasicsDemo.java
java CaptureBasicsDemo
~~~

Kết quả:

~~~text
[Pass: An, Pass: Chi]
true
~~~

Phân tích chi tiết:

1. `minimumScore` được dùng bên trong lambda truyền cho `filter`; biến không bị gán lại nên là effectively final. `label` được dùng trong lambda truyền cho `map`; nó được khai báo `final` một cách tường minh.
2. Hai lambda nhận đối số riêng là `student`. Chỉ `minimumScore` và `label` là biến từ phạm vi ngoài được capture.
3. `passingAtLeast(80)` trả về một `Predicate<Student>` đã capture tham số `threshold`. Callback vẫn chạy sau khi lời gọi `passingAtLeast` hoàn tất.
4. `filter` và `map` là các phép toán trung gian của Stream; chúng thực thi khi terminal operation `collect` tiêu thụ pipeline. Bản thân việc tạo lambda không kích hoạt phép lọc.

**Vì sao sau khi phương thức `passingAtLeast` trả về, lambda vẫn dùng được `threshold`?** Giá trị local cần thiết được mang theo bởi đối tượng hành vi. Nó không phụ thuộc vào việc một ô biến local trên stack của phương thức cũ vẫn còn tồn tại. Không nên xây logic dựa trên lớp hoặc định danh đối tượng lambda do JVM tạo ra; phần cần tin cậy là hợp đồng kiểu và hành vi của lambda.

## 4. Capture giá trị của biến khác với bất biến của đối tượng

Đây là điểm rất dễ nhầm.

- Với **primitive** như `int`, capture sử dụng giá trị của biến local tại ngữ cảnh tạo hành vi. Biến local không thể bị gán lại nếu đã được capture.
- Với **reference** như `List<String>`, `StringBuilder` hay đối tượng do bạn tự tạo, reference local phải final/effectively final. Tuy vậy **trạng thái bên trong đối tượng được tham chiếu vẫn có thể thay đổi** nếu đối tượng mutable.
- `final` trên biến reference cấm đổi reference sang đối tượng khác, chứ không tự biến đối tượng được trỏ tới thành immutable.

Ví dụ minh họa:

~~~java
final java.util.List<String> messages =
        new java.util.ArrayList<>();

Runnable addMessage = () -> messages.add("done");
addMessage.run();

System.out.println(messages); // [done]
~~~

Đoạn này hợp lệ. `messages` không bị gán lại; chỉ **nội dung ArrayList** thay đổi. Việc lambda truy cập cùng đối tượng có thể nhìn thấy thay đổi về sau, nhưng không có bảo đảm tự động về thread safety nếu chạy đồng thời.

Ngược lại, ví dụ **cố ý không biên dịch**:

~~~java
java.util.List<String> messages = new java.util.ArrayList<>();
Runnable addMessage = () -> messages.add("done");
messages = new java.util.ArrayList<>(); // Gán reference mới: không hợp lệ
~~~

Với field, quy tắc khác:

~~~java
class RequestCounter {
    private int requests;

    Runnable incrementAction() {
        return () -> requests++;
    }
}
~~~

Đây là **mảnh mã minh họa**, không chứa `main`. Lambda truy cập field `requests` qua đối tượng hiện tại; field không chịu ràng buộc effectively final như biến local. Nhưng `requests++` không phải thao tác atomic trong môi trường nhiều luồng, nên cần phối hợp đồng bộ hoặc dùng cấu trúc dữ liệu đồng thời phù hợp khi có truy cập cạnh tranh.

### Chụp ảnh trạng thái (snapshot) hay đọc trạng thái mới nhất?

Giả sử `Config` là một đối tượng có field `timeout` đang thay đổi:

~~~java
int snapshot = config.timeout;
Runnable a = () -> useTimeout(snapshot);
Runnable b = () -> useTimeout(config.timeout);
~~~

Đoạn trên là **mã minh họa cần đặt trong ngữ cảnh đã có `config` và `useTimeout`**, không phải chương trình độc lập.

- `a` dùng giá trị `snapshot` tại thời điểm gán biến local.
- `b` đọc trạng thái `timeout` của đối tượng khi callback chạy.
- Cả hai đều hợp lệ nếu reference local `config` không bị gán lại.

Đây là quyết định thiết kế quan trọng: callback cần một bản chụp ổn định hay cần đọc trạng thái mới nhất? Nếu nhiều luồng tham gia, việc đọc giá trị mới nhất còn phụ thuộc quy tắc visibility và đồng bộ của Java Memory Model.

## 5. Vòng lặp: vì sao biến `for` thường không capture được?

Với `for` truyền thống, biến chỉ số `i` thường bị tăng ở mỗi vòng lặp. Vì `i++` làm nó không effectively final, đoạn sau **cố ý không biên dịch**:

~~~java
java.util.List<Runnable> actions = new java.util.ArrayList<>();
for (int i = 0; i < 3; i++) {
    actions.add(() -> System.out.println(i)); // Không hợp lệ
}
~~~

Cách sửa: tạo **biến local mới trong mỗi lần lặp** và không gán lại biến đó:

~~~java
java.util.List<Runnable> actions = new java.util.ArrayList<>();
for (int i = 0; i < 3; i++) {
    final int index = i;
    actions.add(() -> System.out.println(index));
}
~~~

Mỗi lần lặp tạo một `index` riêng; ba callback lưu giá trị 0, 1, 2. Có thể bỏ từ khóa `final` nếu không gán lại `index`, vì khi đó nó effectively final.

Trong vòng lặp **enhanced for**, biến vòng lặp được coi là một biến riêng cho mỗi lượt lặp trong ngữ cảnh capture. Có thể viết:

~~~java
java.util.List<java.util.function.Supplier<String>> actions =
        new java.util.ArrayList<>();
for (String name : new String[]{"An", "Binh"}) {
    actions.add(() -> name);
}
~~~

Nếu gọi lần lượt hai supplier, kết quả là `An` và `Binh`. Dù vòng lặp có nhiều lượt, biến `name` của từng lượt không bị gán lại nên hợp lệ.

### Ví dụ chạy đầy đủ: callback chạy sau vòng lặp và đối tượng mutable

Tạo tệp **CaptureLoopDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.IntSupplier;
import java.util.function.Supplier;

public class CaptureLoopDemo {
    static final class Counter {
        int value;
    }

    public static void main(String[] args) {
        int offset = 10;
        List<IntSupplier> calculations = new ArrayList<>();

        for (int i = 0; i < 3; i++) {
            int index = i; // effectively final cho từng lượt
            calculations.add(() -> offset + index);
        }

        List<Integer> results = new ArrayList<>();
        for (IntSupplier calculation : calculations) {
            results.add(calculation.getAsInt());
        }
        System.out.println(results);

        List<Supplier<String>> deferredNames = new ArrayList<>();
        for (String name : new String[]{"An", "Binh"}) {
            deferredNames.add(() -> name);
        }
        System.out.println(
                deferredNames.get(0).get()
                + " / " + deferredNames.get(1).get()
        );

        final Counter counter = new Counter();
        Runnable increment = () -> counter.value++;
        increment.run();
        increment.run();
        System.out.println(counter.value);
    }
}
~~~

Chạy với JDK 17+ (ví dụ dùng các API đã có trong Java 8):

~~~bash
javac CaptureLoopDemo.java
java CaptureLoopDemo
~~~

Kết quả chính xác:

~~~text
[10, 11, 12]
An / Binh
2
~~~

Ở phần đầu, `offset` và mỗi `index` là effectively final; tuy vòng lặp đã kết thúc, các `IntSupplier` vẫn trả kết quả dựa trên giá trị đã capture. Phần tiếp theo minh họa enhanced for. Phần cuối minh họa rằng `counter` là **final reference**, nhưng field `value` vẫn thay đổi sau mỗi lần `increment.run()`. Ví dụ chỉ chạy tuần tự; không suy ra rằng việc tăng `value` là an toàn nếu nhiều luồng cùng chạy.

## 6. Phạm vi tên biến và `this` bên trong lambda

Lambda sử dụng **lexical scope** của mã bao quanh. Nó không tạo một scope để bạn có thể tùy ý đặt lại tên trùng với biến local đang ở phạm vi ngoài, khác với một số trực giác khi chuyển từ anonymous inner class.

Ví dụ **cố ý không biên dịch**:

~~~java
int value = 5;
Runnable action = () -> {
    int value = 6; // Không được khai báo lại tên biến local bao quanh
    System.out.println(value);
};
~~~

Thay bằng tên khác, hoặc dùng biến ngoài trực tiếp nếu phù hợp.

Trong **instance method**, `this` ở trong lambda tham chiếu đến đối tượng bao quanh, chứ không phải một đối tượng callback riêng. Ví dụ:

~~~java
class LabelPrinter {
    private String label = "ready";

    Runnable printer() {
        return () -> System.out.println(this.label);
    }
}
~~~

Đây là mảnh mã minh họa không có `main`. Nếu thay đổi `label` trước khi gọi callback, biểu thức `this.label` sẽ đọc field của đối tượng tại lúc gọi. Điều này khác việc capture một local `final String snapshot = label;` rồi dùng `snapshot`. Không thể dùng `this` trong static context vì không có đối tượng bao quanh.

`return` trong thân lambda dạng khối chỉ trả về từ lambda; nó không làm phương thức chứa lời khai báo lambda trả về sớm. Nhờ hiểu scope, ta tránh được lỗi tưởng callback có thể điều khiển trực tiếp luồng thực thi của caller.

## 7. Capture khi callback chạy trễ hoặc trên luồng khác

Capture xuất hiện thường xuyên trong API nhận `Runnable`, `Supplier<T>`, `Predicate<T>`, `Function<T,R>` và `Consumer<T>`. Ví dụ:

~~~java
String requestId = "req-42";
Runnable audit = () -> System.out.println("Audit " + requestId);
// Mới tạo hành vi. Callback chưa chạy.
audit.run(); // Audit req-42
~~~

Nếu gửi `audit` cho executor, thời điểm và luồng gọi phụ thuộc executor. Quy tắc effectively final giúp local không đổi binding sau khi lambda tạo, **nhưng không bảo đảm đối tượng mutable bên trong reference an toàn cho nhiều luồng**.

Các điểm cần kiểm tra:

1. **Thread safety của đối tượng được capture**: nếu nhiều callback sửa cùng `ArrayList`, `HashMap` hoặc field thường, có thể có data race và kết quả không nhất quán.
2. **Visibility**: nếu một luồng cập nhật trạng thái và luồng khác đọc, cần cơ chế giao tiếp/đồng bộ phù hợp, như giao tác qua executor, `volatile` ở đúng chỗ, lock, hoặc cấu trúc concurrent. `final` của reference local không tự đồng bộ field mutable.
3. **Atomicity**: phép `count++` gồm nhiều bước; `volatile` đơn lẻ không làm thao tác tăng này thành atomic. Khi cần bộ đếm độc lập nhiều luồng, `AtomicInteger.incrementAndGet()` là một lựa chọn; với bất biến nhiều field, cần thiết kế đồng bộ rộng hơn.
4. **Vòng đời**: callback lưu trong hàng đợi hoặc listener có thể giữ reference tới object lớn hoặc tài nguyên đã hết vòng đời. Chọn dữ liệu capture tối thiểu, quản lý hủy đăng ký listener và đóng tài nguyên theo đúng vòng đời.
5. **Ý nghĩa của giá trị**: nếu muốn xử lý theo một cấu hình cố định của yêu cầu, capture snapshot bất biến; nếu thực sự cần giá trị cập nhật theo thời gian, thiết kế đường đọc trạng thái được đồng bộ hóa rõ ràng.

Không nên dùng `int[] counter = {0}`, `AtomicInteger` hay một mutable holder **chỉ để lách giới hạn effectively final** cho thuật toán tuần tự. Với bài toán tính toán đơn giản, thường có thể dùng `map`, `reduce`, collector hoặc một phương thức thường; khi có đồng thời thật sự, hãy chọn kiểu trạng thái và cơ chế đồng bộ vì lý do nghiệp vụ, không chỉ vì lambda biên dịch.

## 8. Những nhầm lẫn phổ biến

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “Muốn capture thì phải viết `final`.” | Không bắt buộc ghi từ khóa; effectively final là đủ. |
| “Đã tạo lambda rồi mới gán lại biến thì được.” | Vẫn không được: trình biên dịch kiểm tra biến local trong phạm vi của nó. |
| “Không gán lại reference tức là object bất biến.” | Object vẫn có thể mutable; `list.add`, `builder.append`, gán field vẫn có thể hợp lệ. |
| “Capture `int` nghĩa là lambda đọc một ô local đang sống trên stack.” | Callback mang theo giá trị cần thiết; có thể được gọi sau khi phương thức tạo callback trả về. |
| “Biến `i` trong `for (int i...; i++)` luôn capture được.” | Không được nếu `i` thay đổi; tạo một local snapshot trong mỗi vòng lặp. |
| “`final` tự làm mọi thao tác trong lambda an toàn luồng.” | Không; cần xem xét dữ liệu mutable, visibility và atomicity. |
| “Lambda tự chạy ngay khi khai báo.” | Nó chỉ chạy khi callback được API gọi hoặc lời gọi SAM diễn ra. |
| “Đổi một field là lỗi effectively final.” | Quy tắc này dành cho local/parameter được capture; field có thể thay đổi, nhưng phải xét an toàn và hợp đồng. |

Các dấu hiệu nên sửa ngay: một lambda rất dài chỉ để thay đổi các field ở bên ngoài; bộ đếm mutable dùng trong `Stream.forEach` để thu thập kết quả; một `Runnable` lưu lâu vô tình giữ cả đối tượng lớn; hoặc một callback nhận tham số nhưng không có hợp đồng thời điểm/số lần gọi rõ ràng.

## 9. Bài tập vận dụng

**Bài 1 — Dự đoán biên dịch.** Với từng đoạn sau, hãy giải thích biến nào là captured local, biến nào chỉ là tham số lambda, và đoạn nào không biên dịch:

~~~java
// A
int base = 5;
java.util.function.IntUnaryOperator f = x -> x + base;

// B (đặt độc lập với A)
int base = 5;
java.util.function.IntUnaryOperator f = x -> x + base;
base = 6;

// C (đặt độc lập với A và B)
final java.util.List<String> words = new java.util.ArrayList<>();
Runnable r = () -> words.add("A");
~~~

Gợi ý kiểm tra: A hợp lệ; B không hợp lệ do gán lại `base`; C hợp lệ vì chỉ sửa nội dung object. Mỗi đoạn là mảnh mã minh họa trong một phương thức riêng, không đặt nối tiếp nguyên văn với những tên local trùng nhau.

**Bài 2 — Chụp giá trị từng lượt.** Tạo năm `IntSupplier` trong `for (int i = 0; i < 5; i++)` sao cho khi gọi sau khi vòng lặp kết thúc, chúng lần lượt trả `0, 1, 4, 9, 16`. Giải thích vì sao phải dùng biến local riêng của từng lượt.

**Bài 3 — Tạo predicate bằng factory.** Viết `static IntPredicate betweenInclusive(int low, int high)` trả lambda kiểm tra `low <= value && value <= high`. Thử dùng predicate sau khi `betweenInclusive` đã trả về; mô tả hai tham số `low` và `high` được capture thế nào.

**Bài 4 — Snapshot so với state hiện hành.** Một object `Settings` có field `maxRetries` thay đổi theo thời gian. Đề xuất một callback dùng giá trị chụp tại lúc tạo và một callback đọc field khi chạy. Nêu hành vi mong muốn và yêu cầu đồng bộ nếu callback chạy trên luồng khác.

## 10. Ghi nhớ

- Một lambda **capture** biến local/parameter ngoài danh sách tham số của chính nó khi lambda dùng những biến đó trong thân.
- Java yêu cầu biến local/parameter được capture là `final` hoặc **effectively final**; khai báo `final` tường minh là tùy chọn nếu biến thực tế không bị gán lại.
- **Không gán lại biến reference** khác với **không sửa trạng thái object**. `final`/effectively final không làm object mutable trở thành bất biến và không tự tạo thread safety.
- Callback có thể tồn tại lâu hơn phương thức tạo nó. Với vòng lặp truyền thống, cần snapshot local theo mỗi lần lặp nếu chỉ số thay đổi; enhanced for có biến vòng lặp riêng ở mỗi lượt.
- Trong callback chạy trễ/đồng thời, hãy cân nhắc snapshot, vòng đời, visibility, atomicity và hợp đồng thực thi. Đây là các vấn đề thực tế của Java hiện đại, độc lập với việc mã dùng Java 8 hay JDK mới.
