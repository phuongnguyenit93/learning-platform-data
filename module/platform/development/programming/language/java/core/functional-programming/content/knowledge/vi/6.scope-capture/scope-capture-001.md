# Phạm vi tên của tham số và biến cục bộ trong lambda (Java)

## 1. Mục tiêu bài học

Khi viết lambda, ta có thể khai báo tham số ngay trước dấu `->` và khai báo biến cục bộ bên trong thân dạng block. Đồng thời, lambda có thể tham chiếu các tên đã tồn tại ở lớp hoặc phương thức bao quanh. Để hiểu một cái tên chỉ đến biến nào và có được phép khai báo trùng hay không, cần phân biệt **phạm vi tên (scope)**, **che khuất tên (shadowing)** và **bắt giữ biến từ bên ngoài (capture)**.

Trong Java, lambda **không mở thêm một cấp phạm vi tên giống như khai báo một class mới**. Nó vẫn tạo phạm vi cho các tham số và các biến cục bộ riêng của mình, nhưng **không được dùng những tên này để khai báo đè lên biến cục bộ hoặc tham số đang nằm trong phạm vi bao quanh**. Đây là khác biệt quan trọng với anonymous class.

Sau bài này, bạn có thể:
- Xác định phạm vi của tham số lambda, biến khai báo trong block và biến nằm ở block ngoài.
- Nhận ra các lỗi trùng tên tại thời điểm biên dịch.
- Phân biệt khai báo tên mới trong lambda với việc đọc/capture một biến bên ngoài.
- Hiểu tại sao `this` trong lambda trỏ tới đối tượng bao quanh, trong khi `this` trong anonymous class trỏ tới đối tượng anonymous class.
- Viết lambda lồng nhau mà mỗi tham số có tên rõ ràng, không xung đột.

## 2. Phạm vi của một khai báo được hiểu thế nào?

**Scope** là vùng chương trình trong đó một tên đã khai báo có thể được tham chiếu theo quy tắc của Java. Scope được quyết định chủ yếu bởi vị trí khai báo trong mã nguồn, không phải việc lambda được thực thi vào lúc nào.

Ví dụ (đoạn minh họa đặt bên trong một phương thức):

~~~java
java.util.function.Function<String, String> normalize = value -> {
    String cleaned = value.trim();
    return cleaned.toUpperCase(java.util.Locale.ROOT);
};
~~~

Ở đây:

| Tên | Được khai báo tại đâu? | Phạm vi sử dụng hợp lệ |
| --- | --- | --- |
| `normalize` | Biến cục bộ của phương thức chứa lambda | Phần tiếp theo của block phương thức, từ vị trí khai báo theo quy tắc Java |
| `value` | Tham số của lambda | Thân của lambda đó |
| `cleaned` | Biến cục bộ trong block của lambda | Từ khai báo đến hết block tương ứng |
| `String`, `Locale` | Tên kiểu | Theo quy tắc tên kiểu/import, khác phạm vi biến cục bộ |

Ví dụ, sau khi kết thúc thân `{ ... }` của lambda, mã bên ngoài không thể truy cập tên `cleaned`. Mỗi lần phương thức chức năng được gọi, tham số và biến cục bộ của lần thực thi đó có giá trị riêng theo quy tắc thực thi.

### 2.1. Tham số lambda chỉ có phạm vi trong thân lambda

Có ba cách phổ biến viết tham số của một lambda nhận một giá trị:

~~~java
java.util.function.Function<String, Integer> a = text -> text.length();
java.util.function.Function<String, Integer> b = (text) -> text.length();
java.util.function.Function<String, Integer> c = (String text) -> text.length();
~~~

Ba khai báo độc lập trong đoạn minh họa trên đều hợp lệ và cùng biểu diễn phép lấy độ dài. Tên `text` được dùng lại vì **mỗi tham số thuộc một lambda khác nhau** và các phạm vi tham số không lồng vào nhau.

Ở một lambda nhiều tham số, hai tên trong cùng danh sách phải khác nhau:

~~~java
java.util.function.BiFunction<Integer, Integer, Integer> add =
        (left, right) -> left + right;
~~~

Đoạn sau **cố ý sai cú pháp**, không đưa vào chương trình cần chạy:

~~~java
// LỖI: hai tham số trong cùng lambda không thể trùng tên.
// BiFunction<Integer, Integer, Integer> wrong = (x, x) -> x;
~~~

### 2.2. Biến cục bộ trong thân lambda dạng block

Thân lambda có thể là một biểu thức đơn hoặc một block:

~~~java
java.util.function.Function<String, String> simple =
        input -> input.trim();

java.util.function.Function<String, String> detailed = input -> {
    String trimmed = input.trim();
    String upper = trimmed.toUpperCase(java.util.Locale.ROOT);
    return upper;
};
~~~

Với block, các quy tắc thông thường về biến cục bộ của Java tiếp tục áp dụng: mỗi tên trong cùng phạm vi phải được khai báo hợp lệ, biến phải được gán giá trị trước khi đọc, và `return` phải phù hợp kiểu kết quả của functional interface.

Biến `trimmed` và `upper` chỉ nằm trong thân block của `detailed`; không thể truy cập từ bên ngoài bằng cách viết `detailed.trimmed`. Lambda không tạo một đối tượng với các trường công khai tương ứng với những biến này.

## 3. Quy tắc quan trọng nhất: không khai báo trùng tên biến cục bộ đang ở phạm vi bao quanh

Khi biến cục bộ hoặc tham số của phương thức đã nằm trong phạm vi tại vị trí lambda, không thể đặt cùng tên đó cho tham số lambda:

~~~java
// Minh họa có lỗi biên dịch:
void example(String name) {
    // LỖI: name là tham số phương thức đang trong phạm vi.
    // java.util.function.Function<String, String> bad =
    //         name -> name.trim();
}
~~~

Cách sửa: chọn tên tham số khác, chẳng hạn `value`:

~~~java
void example(String name) {
    java.util.function.Function<String, String> good =
            value -> name + ":" + value.trim();
}
~~~

Đây là phương thức **minh họa đặt trong một class**, không phải chương trình độc lập. Phương thức `good` (biến kiểu Function) sử dụng `value` là tham số lambda và tham chiếu `name` từ phương thức bao quanh.

Cùng quy tắc áp dụng cho biến cục bộ khai báo **bên trong** lambda. Không thể tái khai báo biến ngoài cùng tên trong thân lambda dù có thêm một cặp ngoặc nhọn:

~~~java
void count() {
    int total = 10;

    // LỖI: total cục bộ đã nằm trong phạm vi bao quanh.
    // Runnable bad = () -> {
    //     int total = 20;
    //     System.out.println(total);
    // };

    Runnable good = () -> {
        int increment = 2;
        System.out.println(total + increment);
    };
    good.run();
}
~~~

Phương thức `count()` đặt trong một class sẽ hợp lệ nếu bỏ những dòng ví dụ lỗi đang comment. Lambda `good` tham chiếu giá trị `total` và dùng một biến mới là `increment`, nên không có xung đột tên.

**Điểm dễ nhầm:** thêm block `{ }` không luôn cho phép đặt lại tên một biến cục bộ đang trong phạm vi. Java cũng cấm một biến cục bộ ở block con khai báo trùng tên với biến cục bộ trong block cha đang có scope phủ lên đó.

### 3.1. Vì sao một tên có thể dùng lại ở hai lambda ngang hàng?

Hai lambda được khai báo cạnh nhau có phạm vi tham số riêng, không phải cùng một phạm vi tham số:

~~~java
java.util.function.Function<String, String> first = text -> {
    String result = text.trim();
    return result;
};

java.util.function.Function<String, String> second = text -> {
    String result = text.toUpperCase(java.util.Locale.ROOT);
    return result;
};
~~~

Cả hai lambda đều có tham số `text` và biến cục bộ `result`, nhưng các khai báo đó thuộc **hai thân lambda khác nhau, không bao nhau**. Vì vậy mã hợp lệ.

Trường hợp này cũng không nên bị diễn giải thành “lambda có thể shadow mọi tên bên ngoài”: các tên `text` và `result` của lambda thứ nhất **không** nằm trong phạm vi lambda thứ hai. Chúng không xung đột vì các phạm vi độc lập.

### 3.2. Khi tên bên ngoài chưa nằm trong phạm vi

Trong một block Java, phạm vi biến cục bộ bắt đầu từ khai báo của nó theo quy tắc ngôn ngữ, không bắt đầu từ đầu toàn bộ block. Vì vậy, việc cùng tên nhưng thuộc vùng không giao nhau có thể hợp lệ.

Ví dụ minh họa:

~~~java
Runnable earlier = () -> {
    int later = 1;
    System.out.println(later);
};
int later = 2;
~~~

Khi lambda được viết, khai báo biến cục bộ `later` của block ngoài ở dòng sau chưa nằm trong phạm vi tại vị trí đó. Tuy nhiên, đây là kiểu đặt tên dễ khiến người đọc hiểu sai; tốt hơn vẫn nên dùng tên phản ánh ý nghĩa.

## 4. Lambda lồng nhau: kiểm tra đồng thời nhiều phạm vi

Lambda có thể trả về một lambda khác:

~~~java
java.util.function.Function<Integer,
        java.util.function.IntUnaryOperator> adder =
        outer -> inner -> outer + inner;
~~~

Cách đọc:

- `outer` là tham số của lambda ngoài.
- `inner` là tham số của lambda trong.
- Thân lambda trong nhìn thấy cả `inner` và `outer`, vì thân lambda trong nằm trong phạm vi của tham số lambda ngoài.
- `adder.apply(3).applyAsInt(4)` trả 7.

Không thể sử dụng cùng tên `outer` cho tham số lambda trong:

~~~java
// LỖI: tham số của lambda ngoài đã ở trong phạm vi.
// Function<Integer, IntUnaryOperator> wrong =
//         outer -> outer -> outer + 1;
~~~

Cũng không thể khai báo thêm biến cục bộ `outer` trong block của lambda trong. Khi lồng lambda, nên dùng tên `outerIndex`, `innerIndex`, `item` hoặc tên nghiệp vụ thực tế thay vì các ký hiệu mơ hồ.

## 5. Tên trường (field) khác tên biến cục bộ

Quy tắc cấm khai báo trùng **biến cục bộ hoặc tham số** ở phạm vi bao quanh không đồng nghĩa cấm tham số lambda cùng tên với một **field**.

Ví dụ minh họa đặt trong class:

~~~java
class ScopeWithField {
    private String label = "field";

    void show() {
        java.util.function.Function<String, String> f =
                label -> label.toUpperCase(java.util.Locale.ROOT);
        System.out.println(f.apply("local")); // LOCAL
        System.out.println(this.label);       // field
    }
}
~~~

Tham số `label` của lambda có thể che khuất field `label` khi dùng tên đơn trong thân lambda. Có thể truy cập field của đối tượng bao quanh rõ ràng bằng `this.label` trong ngữ cảnh instance.

Ngược lại, nếu một phương thức có tham số `label` đang trong phạm vi, việc dùng `label` làm tham số lambda bên trong phương thức là lỗi biên dịch. Tức là **cần phân biệt field với local/formal parameter** khi xét xung đột tên.

## 6. `this` và `super`: lambda dùng ngữ cảnh lớp bao quanh

Theo JLS §15.27.2, ý nghĩa của các tên và của `this`, `super` bên trong lambda gần như giữ nguyên ngữ cảnh bao quanh, ngoại trừ các tên do tham số lambda mới khai báo. Lambda không tạo một instance class mới với `this` riêng như anonymous class.

Giả sử trong phương thức instance:

~~~java
Runnable lambda = () -> System.out.println(this.owner);
~~~

`this` là đối tượng đang thực hiện phương thức bao quanh, nên đọc field `owner` của đối tượng đó. Trong anonymous class:

~~~java
Runnable anonymous = new Runnable() {
    private final String owner = "anonymous";

    @Override
    public void run() {
        System.out.println(this.owner);
    }
};
~~~

`this` trong phương thức `run()` là instance của anonymous class, vì đó là ngữ cảnh một class được khai báo mới.

Với `super` trong lambda, việc tra cứu cũng dựa trên ngữ cảnh lexical của class bao quanh khi có lời gọi hợp lệ. Trong ngữ cảnh `static`, không thể sử dụng `this` hoặc `super` như thể có một enclosing instance.

**Lưu ý:** cách Java triển khai object cho lambda trong JVM là chi tiết của runtime; không nên dựa vào danh tính class sinh ra, tên class nội bộ hoặc coi `this` là chính object biểu diễn lambda.

## 7. Phạm vi tên và bắt giữ biến là hai quy tắc riêng

Phạm vi xác định **có thể tham chiếu tên hay không**; capture xác định việc lambda dùng một giá trị từ ngữ cảnh ngoài được phép ra sao.

Java chỉ cho lambda bắt giữ một **biến cục bộ/tham số của phương thức bao quanh** nếu nó là `final` hoặc **effectively final** (sau khi gán theo quy tắc Java, không bị gán lại). Ví dụ:

~~~java
void sample() {
    String prefix = "Hi ";
    java.util.function.Function<String, String> greet =
            name -> prefix + name;
    System.out.println(greet.apply("An")); // Hi An
}
~~~

Ví dụ **không biên dịch** nếu bỏ comment:

~~~java
void invalidCapture() {
    int counter = 0;
    // java.util.function.IntSupplier reader = () -> counter;
    counter++;
    // LỖI nếu khai báo reader ở trên:
    // counter đã bị thay đổi nên không effectively final.
}
~~~

Trường hợp này không phải lỗi trùng tên; lambda đang **đọc** biến ngoài đúng tên nhưng biến ngoài không thỏa ràng buộc capture.

**Phân biệt thêm:**
- Bản thân tham số lambda có thể được gán lại trong body nếu không khai báo `final`, dù cách làm đó thường kém rõ ràng. Điều kiện effectively final nói trên áp dụng cho **biến cục bộ được bắt giữ từ bên ngoài**.
- Một field của class có thể thay đổi và được truy cập trong lambda nếu đúng quy tắc truy cập. Điều này không bị giới hạn bởi effectively final của biến cục bộ, nhưng có thể làm hành vi phụ thuộc trạng thái chia sẻ.
- Tham chiếu local effectively final có thể trỏ đến một đối tượng **mutable**. Cấm gán lại biến tham chiếu không đồng nghĩa cấm thay đổi trạng thái của đối tượng mà nó trỏ đến.

Phạm vi tên, tính bất biến của biến tham chiếu và tính bất biến của đối tượng là **ba vấn đề khác nhau**.

## 8. Dạng khai báo tham số và kiểm tra tên

Java hỗ trợ tham số lambda khai báo kiểu tường minh, suy luận kiểu, hoặc dùng `var` (Java 11+) tùy ngữ cảnh:

~~~java
java.util.function.BiFunction<Integer, Integer, Integer> sum1 =
        (Integer left, Integer right) -> left + right;

java.util.function.BiFunction<Integer, Integer, Integer> sum2 =
        (left, right) -> left + right;

java.util.function.BiFunction<Integer, Integer, Integer> sum3 =
        (var left, var right) -> left + right;
~~~

Cả ba đều hợp lệ trên Java 17. Không được trộn khai báo kiểu tường minh với suy luận kiểu trong cùng danh sách, hoặc trộn `var` với kiểu không khai báo:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH:
// BiFunction<Integer,Integer,Integer> bad1 =
//         (Integer left, right) -> left + right;
// BiFunction<Integer,Integer,Integer> bad2 =
//         (var left, right) -> left + right;
// BiFunction<Integer,Integer,Integer> bad3 =
//         (var left, Integer right) -> left + right;
~~~

Dùng `var` cho tham số lambda **không** nới lỏng quy tắc về tên: mỗi tên tham số vẫn phải độc nhất trong danh sách và không được xung đột với local/parameter đang ở phạm vi bao quanh.

Tên chỉ là **định danh**: có thể đổi từ `text` thành `inputText` mà không đổi bản chất phép tính, miễn các tham chiếu trong body được đổi nhất quán. Tuy nhiên, khi tên đó đã bị sử dụng bởi biến ngoài, phải chọn tên khác để tránh xung đột.

## 9. Ví dụ Java 17 hoàn chỉnh

Tạo file **LambdaScopeLesson.java**. Chương trình cho thấy:
- Capture một local effectively final.
- Khai báo local riêng trong thân lambda dạng block.
- Dùng field trong lambda qua `this`.
- Đặt tên tham số ở lambda lồng nhau.
- Dùng lại tên `result` trong hai lambda ngang hàng.
- So sánh `this` của lambda và anonymous class.

~~~java
import java.util.Locale;
import java.util.function.Function;
import java.util.function.IntUnaryOperator;

public class LambdaScopeLesson {
    private final String owner = "instance";
    private int increment = 5;

    void demonstrate() {
        String prefix = "pre";

        Function<String, String> process = input -> {
            String cleaned = input.trim();
            return prefix + ":" + cleaned;
        };
        IntUnaryOperator add = number -> number + this.increment;
        Function<Integer, IntUnaryOperator> sum =
                outer -> inner -> outer + inner;

        Function<String, String> first = text -> {
            String result = text.trim();
            return result;
        };
        Function<String, String> second = text -> {
            String result = text.toUpperCase(Locale.ROOT);
            return result;
        };

        Runnable lambda = () ->
                System.out.println("lambda this=" + this.owner);
        Runnable anonymous = new Runnable() {
            private final String owner = "anonymous";
            @Override
            public void run() {
                System.out.println("anonymous this=" + this.owner);
            }
        };

        System.out.println(process.apply(" Java "));
        System.out.println(add.applyAsInt(7));
        System.out.println(sum.apply(3).applyAsInt(4));
        System.out.println(first.apply(" Hi "));
        System.out.println(second.apply("Hi"));
        lambda.run();
        anonymous.run();
    }

    public static void main(String[] args) {
        new LambdaScopeLesson().demonstrate();
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 LambdaScopeLesson.java
java LambdaScopeLesson
~~~

Stdout đã được kiểm chứng:

~~~text
pre:Java
12
7
Hi
HI
lambda this=instance
anonymous this=anonymous
~~~

Giải thích:
1. `prefix` là local của `demonstrate` và không được gán lại, nên `process` có thể capture. `input` và `cleaned` là tham số/biến của chính lambda.
2. `add` lấy tham số `number` và đọc field `increment` qua `this`: 7 + 5 = 12.
3. `sum` gồm hai lambda lồng nhau; `outer = 3` và `inner = 4`, nên kết quả là 7.
4. Hai lambda `first` và `second` dùng các tên `text`, `result` giống nhau nhưng thuộc các phạm vi độc lập; cả hai hợp lệ.
5. `lambda` đọc field `owner` của `LambdaScopeLesson`, còn anonymous class khai báo một field `owner` riêng; vì vậy hai dòng cuối khác nhau.

Chương trình được biên dịch thật với `javac --release 17` và chạy thành công. Các đoạn ví dụ **cố ý sai** ở các mục trước đã được comment để không lẫn với chương trình chạy độc lập.

## 10. Lỗi phổ biến và cách sửa

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Đặt tên tham số lambda trùng biến local bên ngoài | Tái khai báo trong scope của local | Đổi tên tham số lambda |
| Khai báo local trong lambda trùng tham số phương thức | Tham số phương thức còn trong phạm vi | Dùng tên local khác |
| Hai tham số cùng tên trong một lambda | Không thể có hai formal parameter trùng identifier | Đổi một tên |
| Lambda trong khai báo lại tên tham số lambda ngoài | Scope của tham số ngoài bao phủ lambda trong | Dùng các tên khác nhau |
| Hiểu `this` là lambda object | Lambda không có `this` lexical riêng | Hiểu `this` theo class bao quanh |
| Capture local rồi gán lại local đó | Local không effectively final | Đưa trạng thái vào đối tượng có hợp đồng rõ hoặc thiết kế lại phép xử lý |
| Đặt biến trong thân lambda rồi truy cập từ bên ngoài | Tên chỉ nằm trong block lambda | Trả giá trị từ lambda hoặc lưu kết quả ở nơi gọi |
| Cho rằng hai lambda cạnh nhau không được trùng tên tham số | Nhầm các scope độc lập với scope lồng nhau | Dùng lại tên là hợp lệ, dù nên đặt tên rõ ý nghĩa |

Một cách kiểm tra thực tế là vẽ “vùng nhìn thấy tên” từ khai báo tới điểm kết thúc phạm vi, sau đó xét tại từng khai báo mới xem tên đã có local/parameter ở phạm vi bao quanh hay chưa. Khi lỗi xảy ra, compiler thường báo rằng biến đã được định nghĩa hoặc được khai báo trong một phạm vi bao quanh.

## 11. Tự kiểm tra

**Câu 1.** Tại sao ví dụ sau sai?

~~~java
// void work(int value) {
//     java.util.function.IntUnaryOperator op = value -> value + 1;
// }
~~~

Vì `value` đã là tham số của phương thức bao quanh; tham số lambda không được tái sử dụng tên này trong scope đang hoạt động.

**Câu 2.** Hai lambda ngang hàng có thể cùng dùng tham số `item` không?

**Có.** Mỗi tham số chỉ thuộc scope thân lambda của chính nó; không có xung đột khi hai scope độc lập.

**Câu 3.** Nếu một lambda lồng trong lambda khác cần đọc tham số `outer`, nó có thể đặt tên tham số riêng cũng là `outer` không?

**Không.** Scope của tham số lambda ngoài bao phủ thân lambda trong. Lambda trong có thể **đọc** `outer`, nhưng không được **khai báo lại** tham số cùng tên.

**Câu 4.** Lambda có field `this` của riêng nó không?

**Không.** Trong instance context, `this` biểu thị enclosing instance theo ngữ cảnh lexical. Anonymous class có instance và `this` riêng.

**Câu 5.** Local được capture là effectively final có khiến object mà nó tham chiếu bất biến?

**Không.** Ràng buộc đó cấm gán lại biến local; nếu đối tượng tham chiếu mutable thì nội dung của nó vẫn có thể đổi.

**Câu 6.** Tại sao đổi tên local ngoài thành tên khác giải quyết được một số lỗi lambda?

Vì quy tắc cấm trùng identifier phụ thuộc vào tên khai báo có scope chồng nhau. Đổi tên giải quyết va chạm tên, nhưng phải bảo đảm mọi tham chiếu đến biến đều được cập nhật đúng ý nghĩa.

## 12. Tài liệu đối chiếu

- [Java Language Specification 17, §6.3 – Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3).
- [Java Language Specification 17, §6.4 – Shadowing and Obscuring](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.4).
- [Java Language Specification 17, §15.27.1 – Lambda Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.1).
- [Java Language Specification 17, §15.27.2 – Lambda Body](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.2).
- [Java Language Specification 17, §6.5.6.1 – Simple Expression Names (capture)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.5.6.1).

**Ghi nhớ:** Tham số và local bên trong lambda có scope riêng nhưng không được đặt trùng tên với local/parameter đang hiện diện ở phạm vi bao quanh. Hai lambda độc lập có thể dùng lại tên. Lambda nhìn thấy `this`/`super` theo class bao quanh; việc capture một local từ ngoài còn đòi hỏi biến đó là `final` hoặc effectively final. Hiểu những ranh giới này giúp tránh lỗi biên dịch và làm code dễ đọc hơn.
