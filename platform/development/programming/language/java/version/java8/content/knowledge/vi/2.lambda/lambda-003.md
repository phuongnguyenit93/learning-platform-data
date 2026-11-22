# Lambda không tham số, một tham số và nhiều tham số trong Java

## Mục tiêu

Trong Java 8, biểu thức lambda giúp viết ngắn gọn phần triển khai của **giao diện hàm (functional interface)**. Sau bài này, bạn có thể đọc, viết và lựa chọn đúng dạng lambda có **0, 1 hoặc nhiều tham số**; biết khi nào được bỏ dấu ngoặc tròn, khi nào cần khai báo kiểu; sử dụng lambda trong các API Java thông dụng; và tránh những lỗi biên dịch liên quan đến kiểu, số lượng tham số, khối lệnh và biến được truy cập từ bên ngoài lambda.

Các cú pháp chính trong bài vẫn được dùng trên các phiên bản Java hiện đại. Những ví dụ hoàn chỉnh bên dưới chỉ dùng API và cú pháp có từ Java 8, vì vậy có thể chạy bằng JDK 8 trở lên, kể cả JDK 17 và 21.

## 1. Lambda diễn tả điều gì?

Lambda diễn tả **hành vi** mà ta truyền cho một chỗ đang cần giao diện hàm. Một giao diện hàm có đúng **một phương thức trừu tượng** cần triển khai (single abstract method, viết tắt SAM). Lambda cung cấp phần thân cho phương thức ấy. Giao diện vẫn có thể có phương thức default hoặc static; chúng không làm tăng số phương thức trừu tượng cần triển khai.

Hai dạng tổng quát:

~~~java
(thamSo) -> bieuThuc

(thamSo) -> {
    // Các câu lệnh
}
~~~

Đoạn trên là **sơ đồ cú pháp**, không phải chương trình chạy độc lập. Phía trái dấu **->** xác định danh sách tham số; phía phải là biểu thức hoặc khối lệnh sẽ chạy khi phương thức chức năng được gọi. Nếu kết quả cần được trả về, dạng biểu thức thường trả về giá trị ngầm định; dạng khối cần dùng lệnh **return** phù hợp.

Ví dụ, giao diện **Function<String, Integer>** có phương thức trừu tượng **Integer apply(String value)**; vì vậy lambda **text -> text.length()** nhận một chuỗi và trả về độ dài. Lambda không mang một kiểu hàm độc lập: **kiểu đích (target type)** như Function, Runnable hoặc BiFunction quyết định kiểu tham số và kiểu kết quả.

Điều kiện quan trọng: lambda phải được đặt trong ngữ cảnh có thể suy ra một giao diện hàm, chẳng hạn gán cho biến kiểu giao diện hàm, truyền cho phương thức nhận giao diện hàm hoặc ép kiểu rõ ràng đến giao diện hàm.

## 2. Lambda không tham số: dấu ngoặc rỗng ()

Khi phương thức trừu tượng không nhận đối số, phải viết **()** trước mũi tên:

~~~java
Runnable task = () -> System.out.println("Đang chạy");
Supplier<String> message = () -> "Sẵn sàng";
~~~

Hai dòng trên là các đoạn minh họa sử dụng Runnable và java.util.function.Supplier; để biên dịch riêng cần import Supplier và đặt trong một phương thức/lớp phù hợp.

- **Runnable.run()** không nhận tham số và trả về **void**. Biểu thức bên phải ở ví dụ là một lời gọi in ra màn hình.
- **Supplier<T>.get()** không nhận tham số nhưng trả về một giá trị kiểu T. Ví dụ trả về chuỗi "Sẵn sàng".
- Cả hai đều **không tự chạy khi khởi tạo lambda**. Phần thân chỉ chạy khi gọi **task.run()** hoặc **message.get()**, hoặc khi một API gọi hộ chúng.
- Không thể thay **() ->** bằng **->** vì Java yêu cầu biểu diễn danh sách tham số rỗng bằng cặp ngoặc tròn.

Có thể sử dụng khối lệnh khi có nhiều câu lệnh:

~~~java
Supplier<String> greeting = () -> {
    String text = "Xin chào";
    return text.toUpperCase();
};
~~~

Dạng khối của Supplier phải trả về String trên mọi đường đi hợp lệ. Với Runnable, phần thân thường chỉ thực hiện hành động:

~~~java
Runnable log = () -> {
    System.out.println("Bắt đầu");
    System.out.println("Kết thúc");
};
~~~

Phân biệt **không có tham số** với **không có kết quả**: đó là hai đặc điểm độc lập. Runnable và Supplier cùng không nhận tham số nhưng khác kiểu trả về.

## 3. Lambda một tham số: có thể bỏ ngoặc tròn

Với đúng **một tham số** và để Java tự suy luận kiểu, có hai cách viết tương đương:

~~~java
Function<String, Integer> first = text -> text.length();
Function<String, Integer> second = (text) -> text.length();
~~~

Đây là các đoạn minh họa, cần **import java.util.function.Function** khi sử dụng riêng.

Nếu muốn ghi rõ kiểu tham số, phải đặt cả kiểu và tên trong ngoặc:

~~~java
Function<String, Integer> third = (String text) -> text.length();
~~~

**Không hợp lệ:** dạng **String text -> text.length()**, vì khi khai báo kiểu tường minh, cặp ngoặc tròn là bắt buộc.

Một số giao diện chuẩn thường gặp có đúng một tham số:

| Giao diện | Phương thức chức năng | Ý nghĩa thường dùng | Ví dụ lambda |
| --- | --- | --- | --- |
| Consumer<T> | void accept(T value) | Nhận giá trị để thực hiện hành động | name -> System.out.println(name) |
| Function<T,R> | R apply(T value) | Chuyển giá trị T thành R | text -> text.length() |
| Predicate<T> | boolean test(T value) | Kiểm tra điều kiện | n -> n > 0 |
| UnaryOperator<T> | T apply(T value) | Biến đổi giá trị nhưng giữ nguyên kiểu | text -> text.trim() |

Tên tham số là do người viết chọn; không bắt buộc đặt là x hoặc value. Nên đặt tên thể hiện vai trò, ví dụ **name**, **order** hoặc **request**.

Java suy luận kiểu tham số từ kiểu đích. Nếu khai báo **Predicate<Integer> isPositive = n -> n > 0**, tham số n có kiểu Integer; khi viết phép so sánh **n > 0**, Java thực hiện mở hộp giá trị cần thiết. Nếu làm việc nhiều với dữ liệu nguyên thủy, những giao diện như **IntPredicate** hoặc **IntUnaryOperator** có thể tránh boxing không cần thiết.

## 4. Lambda nhiều tham số: bắt buộc ngoặc tròn

Khi có từ hai tham số trở lên, **phải** bao danh sách trong ngoặc tròn và ngăn cách các tham số bằng dấu phẩy:

~~~java
BiFunction<Integer, Integer, Integer> add = (a, b) -> a + b;
BiPredicate<String, String> same = (a, b) -> a.equals(b);
~~~

Đây là các đoạn minh họa; các giao diện BiFunction và BiPredicate nằm trong **java.util.function**. Không được viết **a, b -> a + b**.

Có thể ghi rõ kiểu cho **tất cả** tham số:

~~~java
BiFunction<Integer, Integer, Integer> add =
    (Integer a, Integer b) -> a + b;
~~~

Không được trộn một tham số có kiểu tường minh với một tham số suy luận kiểu trong cùng danh sách, ví dụ **(Integer a, b) -> a + b** là không hợp lệ. Quy tắc này giúp cách khai báo nhất quán. Nếu khai báo kiểu tham số tường minh thì tất cả tham số cần khai báo kiểu; nếu suy luận thì tất cả đều dùng dạng tên.

Java cung cấp sẵn các giao diện hai tham số như **BiFunction<T,U,R>**, **BiConsumer<T,U>**, **BiPredicate<T,U>** và **BinaryOperator<T>**. Với phép toán nguyên thủy, **IntBinaryOperator** dùng hai đối số int và trả về int, tránh boxing.

Đối với **ba hoặc nhiều hơn ba tham số**, Java không có sẵn một họ giao diện chuẩn kiểu TriFunction trong java.util.function. Ta có thể tự khai báo giao diện hàm phù hợp:

~~~java
@FunctionalInterface
interface TriFunction<A, B, C, R> {
    R apply(A first, B second, C third);
}
~~~

Đây là phần khai báo kiểu; cần đặt ở phạm vi cho phép khai báo interface. Khi có kiểu đích này, lambda ba tham số hợp lệ:

~~~java
TriFunction<Integer, Integer, Integer, Integer> sumThree =
    (a, b, c) -> a + b + c;
~~~

Vì tên phương thức trừu tượng do giao diện quyết định, cần gọi **sumThree.apply(1, 2, 3)**, không gọi trực tiếp **sumThree(1, 2, 3)**.

**Số tham số của lambda phải bằng số tham số của phương thức trừu tượng trong giao diện đích.** Một giao diện có một tham số không thể nhận lambda hai tham số chỉ vì hai giá trị có cùng kiểu dữ liệu.

## 5. Ví dụ Java hoàn chỉnh cho cả ba dạng

Chương trình sau sử dụng từ 0 đến 3 tham số và minh họa cả dạng biểu thức lẫn khối lệnh. Các kết quả đều xác định, không phụ thuộc thứ tự chạy đa luồng.

Tạo tệp **LambdaParametersDemo.java**:

~~~java
import java.util.function.BiFunction;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;

public class LambdaParametersDemo {

    @FunctionalInterface
    interface TriFunction<A, B, C, R> {
        R apply(A first, B second, C third);
    }

    public static void main(String[] args) {
        // 0 tham số, không trả về kết quả
        Runnable task = () -> System.out.println("Tác vụ đã chạy");

        // 0 tham số, có trả về kết quả
        Supplier<String> message = () -> "Sẵn sàng";

        // 1 tham số, chỉ thực hiện hành động
        Consumer<String> welcome =
            name -> System.out.println("Chào " + name);

        // 1 tham số, khai báo tường minh kiểu String
        Function<String, Integer> length =
            (String text) -> text.length();

        // 1 tham số, trả về boolean
        Predicate<Integer> isEven = n -> n % 2 == 0;

        // 2 tham số, trả về tổng
        BiFunction<Integer, Integer, Integer> add =
            (a, b) -> a + b;

        // 3 tham số, dùng khối lệnh và return
        TriFunction<Integer, Integer, Integer, Integer> addThree =
            (a, b, c) -> {
                int result = a + b + c;
                return result;
            };

        task.run();
        System.out.println(message.get());
        welcome.accept("An");
        System.out.println("Độ dài Java: " + length.apply("Java"));
        System.out.println("6 là số chẵn: " + isEven.test(6));
        System.out.println("2 + 3 = " + add.apply(2, 3));
        System.out.println("2 + 3 + 4 = " + addThree.apply(2, 3, 4));
    }
}
~~~

Biên dịch và chạy (JDK 8+):

~~~bash
javac -encoding UTF-8 LambdaParametersDemo.java
java LambdaParametersDemo
~~~

Kết quả chuẩn:

~~~text
Tác vụ đã chạy
Sẵn sàng
Chào An
Độ dài Java: 4
6 là số chẵn: true
2 + 3 = 5
2 + 3 + 4 = 9
~~~

Hãy quan sát cách gọi tương ứng:

| Lambda | Giao diện đích | Cách kích hoạt |
| --- | --- | --- |
| () -> ... | Runnable | task.run() |
| () -> "Sẵn sàng" | Supplier<String> | message.get() |
| name -> ... | Consumer<String> | welcome.accept("An") |
| (String text) -> ... | Function<String,Integer> | length.apply("Java") |
| n -> ... | Predicate<Integer> | isEven.test(6) |
| (a,b) -> ... | BiFunction<Integer,Integer,Integer> | add.apply(2,3) |
| (a,b,c) -> {...} | TriFunction tự định nghĩa | addThree.apply(2,3,4) |

Ở mỗi trường hợp, **kiểu đích** quy định số lượng đối số và kiểu trả về. Java kiểm tra tính tương thích khi biên dịch; không dựa vào số tên biến xuất hiện trong phần thân.

## 6. Phần thân biểu thức và phần thân khối lệnh

Dù lambda có bao nhiêu tham số, có thể chọn một biểu thức ngắn hoặc khối nhiều câu lệnh. Cần phân biệt cách trả về kết quả:

~~~java
Function<Integer, Integer> square = n -> n * n;

Function<Integer, Integer> squareBlock = n -> {
    int result = n * n;
    return result;
};
~~~

Hai lambda trên tương đương về kết quả. Với phần thân là **biểu thức** trả về giá trị, không viết thêm từ khóa return ở phía trước. Với phần thân là **khối**, phải dùng return để trả về giá trị khi SAM yêu cầu.

Ví dụ dạng void:

~~~java
Consumer<String> print = text -> System.out.println(text);

Consumer<String> printBlock = text -> {
    System.out.println(text);
};
~~~

Biểu thức lời gọi phương thức cũng có thể tương thích với kết quả void khi đáp ứng quy tắc biểu thức câu lệnh của Java. Không nên kết luận mọi biểu thức trả về giá trị đều tự động dùng được ở vị trí void; hãy dựa vào chữ ký SAM và quy tắc tương thích của trình biên dịch.

**Dấu chấm phẩy:** khi gán lambda cho một biến, toàn bộ câu lệnh gán kết thúc bằng dấu **;**. Các câu lệnh bên trong khối cũng dùng dấu chấm phẩy theo quy tắc Java. Không đặt dấu chấm phẩy sau dấu ngoặc đóng của danh sách tham số.

## 7. Truy cập biến bên ngoài lambda

Lambda có thể đọc biến cục bộ bên ngoài nếu biến đó là **final** hoặc **effectively final** (được gán một lần, không bị thay đổi sau đó). Quy tắc này vẫn có hiệu lực trong Java hiện đại và giúp tránh các tình huống nhập nhằng khi giữ lại biến cục bộ sau khi phạm vi ban đầu kết thúc.

Chương trình độc lập **LambdaCaptureDemo.java**:

~~~java
import java.util.function.Function;
import java.util.function.IntBinaryOperator;

public class LambdaCaptureDemo {
    public static void main(String[] args) {
        String prefix = "Mã: ";
        int offset = 5;

        Function<String, String> describe =
            code -> prefix + code;

        IntBinaryOperator addWithOffset =
            (a, b) -> a + b + offset;

        System.out.println(describe.apply("A1"));
        System.out.println(addWithOffset.applyAsInt(2, 3));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 LambdaCaptureDemo.java
java LambdaCaptureDemo
~~~

Kết quả:

~~~text
Mã: A1
10
~~~

Ở đây **prefix** và **offset** không được khai báo final nhưng không bị gán lại, nên là effectively final. Nếu thêm lệnh **offset++** trong cùng phương thức, việc lambda tham chiếu đến offset sẽ không còn hợp lệ và trình biên dịch sẽ báo lỗi.

**Điểm cần phân biệt:** final/effectively final ràng buộc **biến cục bộ được bắt giữ** chứ không đóng băng mọi đối tượng mà biến ấy trỏ tới. Nếu lambda truy cập một đối tượng có thể thay đổi, đối tượng đó vẫn có thể bị chỉnh sửa qua tham chiếu khác; khi dùng với nhiều luồng vẫn cần cân nhắc tính an toàn dữ liệu.

Lambda cũng có phạm vi tên gần với vị trí khai báo: không thể khai báo tham số lambda trùng tên với một biến cục bộ đã tồn tại trong phạm vi bao quanh. Từ khóa **this** bên trong lambda chỉ đối tượng bao quanh theo ngữ cảnh lớp; lambda không tạo một đối tượng this riêng theo cách lớp ẩn danh vẫn làm.

## 8. Lambda được dùng ở đâu trong mã ứng dụng?

Các phương thức thư viện thường nhận một giao diện hàm như tham số, nên cú pháp 0/1/nhiều tham số xuất hiện tự nhiên:

- **0 tham số:** truyền một nhiệm vụ vào Executor thông qua Runnable hoặc cung cấp giá trị trì hoãn bằng Supplier.
- **1 tham số:** List.forEach nhận Consumer; Collection.removeIf nhận Predicate; Stream.map nhận Function; Optional.orElseGet nhận Supplier không tham số.
- **2 tham số:** List.sort nhận Comparator<T> có phương thức compare(T a, T b); Map.forEach nhận BiConsumer<K,V>; Stream.reduce có một số dạng nhận BinaryOperator<T>.
- **3 tham số trở lên:** dùng giao diện hàm tự định nghĩa khi API thực sự cần nhiều đối số, hoặc gom những dữ liệu liên quan vào một kiểu dữ liệu có ý nghĩa để làm rõ mô hình.

Ví dụ minh họa (các biến **names** và **scores** phải được khai báo trong ngữ cảnh thích hợp):

~~~java
names.forEach(name -> System.out.println(name));
names.removeIf(name -> name.isEmpty());
names.sort((left, right) -> left.compareToIgnoreCase(right));
scores.forEach((name, score) ->
    System.out.println(name + ": " + score));
~~~

Ba lệnh đầu minh họa lambda một tham số rồi hai tham số khi dùng List; lệnh cuối minh họa hai tham số của Map.forEach. Đây là các **đoạn sử dụng API**, không phải chương trình độc lập; không nên chạy riêng khi chưa có kiểu và dữ liệu của names/scores.

**Phương thức tham chiếu (method reference)** như **System.out::println** là cách viết gọn khác khi đã có một phương thức phù hợp, nhưng không phải lúc nào cũng thay được lambda. Với bài học này, hiểu cách khớp **danh sách tham số của SAM** mới là nền tảng quan trọng nhất.

**Lambda không tự tạo luồng mới hoặc tự chạy bất đồng bộ.** Ví dụ **names.forEach(...)** trên một List thông thường chạy đồng bộ theo lời gọi của người dùng. Khả năng song song hay bất đồng bộ chỉ xuất hiện khi API và cách tổ chức thực thi thực sự hỗ trợ, không đến từ ký hiệu **->**.

## 9. Các lỗi cú pháp và kiểu thường gặp

| Viết sai hoặc hiểu sai | Vì sao sai | Cách đúng |
| --- | --- | --- |
| -> System.out.println("Hi") | Lambda không tham số thiếu ngoặc rỗng | () -> System.out.println("Hi") |
| String s -> s.length() | Khai báo kiểu một tham số phải đặt trong ngoặc | (String s) -> s.length() |
| a, b -> a + b | Từ hai tham số trở lên phải có ngoặc | (a, b) -> a + b |
| (Integer a, b) -> a + b | Trộn kiểu tường minh và kiểu suy luận | (Integer a, Integer b) -> a + b hoặc (a, b) -> a + b |
| (a, b) -> a + b gán cho Function<Integer,Integer> | SAM của Function nhận đúng một tham số | Dùng BiFunction<Integer,Integer,Integer> |
| () -> "Hi" gán cho Runnable | Runnable.run() không nhận đối số và không trả kết quả; biểu thức chuỗi không phù hợp thân void | Dùng Supplier<String> |
| () -> { "Hi"; } | Chuỗi literal đứng riêng không phải câu lệnh hợp lệ và Supplier cần trả kết quả | () -> { return "Hi"; } |
| (a, b) -> { a + b; } gán cho BiFunction | BiFunction cần kết quả; phép cộng trần không phải câu lệnh hợp lệ | (a, b) -> { return a + b; } |
| Cho rằng gọi mới một lambda sẽ chạy phần thân | Khởi tạo lambda chỉ tạo giá trị có thể được gọi | Gọi đúng phương thức SAM hoặc truyền cho API sẽ gọi |
| Tự định nghĩa TriFunction rồi cho rằng đó là lớp có sẵn trong JDK | java.util.function không có TriFunction chuẩn | Tự khai báo @FunctionalInterface khi thực sự cần |

Một lỗi khác là **không đủ thông tin kiểu**. Ví dụ Java không chấp nhận gán lambda trực tiếp cho biến kiểu **Object** như một giá trị không có kiểu đích giao diện hàm; nên khai báo một giao diện hàm cụ thể như Runnable, Function hoặc giao diện tự định nghĩa. Khi một phương thức có nhiều overload nhận các giao diện hàm khác nhau, lambda đôi khi cũng gây mơ hồ; có thể làm rõ bằng kiểu biến trung gian hoặc ép kiểu đúng giao diện.

## 10. Bài tập thực hành và đáp án gợi ý

**Bài 1 — Không tham số.** Viết một lambda trả về số 42 mà không nhận đối số. Chọn giao diện **Supplier<Integer>** và gọi phương thức get() để lấy kết quả.

Gợi ý:

~~~java
Supplier<Integer> answer = () -> 42;
System.out.println(answer.get());
~~~

Đây là đoạn minh họa; cần import Supplier và đặt trong phương thức thích hợp. Kết quả được in là **42**.

**Bài 2 — Một tham số.** Viết một lambda kiểm tra độ dài chuỗi lớn hơn 3. Chọn **Predicate<String>**, đặt tên tham số **text** và gọi test().

~~~java
Predicate<String> longerThanThree = text -> text.length() > 3;
System.out.println(longerThanThree.test("Java"));
~~~

Kết quả **true**; ví dụ giả định **text** không null và cần import Predicate.

**Bài 3 — Hai tham số.** Viết hàm nhận hai số nguyên và trả về số lớn hơn bằng **BinaryOperator<Integer>** hoặc **IntBinaryOperator**. Tránh gọi song song hoặc thay đổi biến dùng chung vì bài chỉ kiểm tra cú pháp lambda.

~~~java
IntBinaryOperator max = (a, b) -> Math.max(a, b);
System.out.println(max.applyAsInt(7, 4));
~~~

Kết quả **7**, cần import IntBinaryOperator.

**Bài 4 — Ba tham số.** Từ TriFunction trong chương trình hoàn chỉnh, thay phần thân lambda **(a, b, c) -> a + b + c** bằng dạng khối có biến trung gian. Gọi apply(2, 3, 4), xác nhận kết quả **9**. Giải thích vì sao Function và BiFunction không có cùng số lượng tham số với giao diện bạn đang dùng.

**Bài 5 — Nhận diện lỗi.** Với **Function<String,Integer> f**, lựa chọn biểu thức phù hợp trong ba mẫu: **s -> s.length()**, **() -> 1**, **(a,b) -> 1**. Chỉ mẫu đầu có đúng một tham số tương thích với phương thức apply(String), và trả về Integer thông qua boxing từ int.

## Ghi nhớ

- **0 tham số:** **() -> ...**; không thể bỏ cặp ngoặc rỗng.
- **1 tham số:** **x -> ...** hoặc **(x) -> ...** nếu suy luận kiểu; ghi kiểu tường minh thì viết **(Type x) -> ...**.
- **Từ 2 tham số trở lên:** **(x, y) -> ...**; luôn cần ngoặc tròn; khi khai báo kiểu tường minh thì khai báo đầy đủ cho mọi tham số.
- **Số tham số và kiểu kết quả** phải phù hợp với phương thức trừu tượng của giao diện hàm đích.
- **Biểu thức** có thể trả giá trị ngầm định; **khối lệnh** cần return khi phương thức chức năng yêu cầu giá trị.
- Lambda có thể tham chiếu biến cục bộ final/effectively final và vẫn tuân theo các quy tắc kiểu, phạm vi tên và an toàn dữ liệu của Java.

Khi đọc một lambda, hãy xác định **giao diện đích**, xem **phương thức trừu tượng nhận bao nhiêu đối số và trả về gì**, rồi đối chiếu với hai phía dấu **->**. Cách đọc này áp dụng nhất quán cho Java 8 và các JDK được dùng hiện nay.