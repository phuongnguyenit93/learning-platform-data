# Lambda expression như một cách cung cấp triển khai

Lambda expression (biểu thức lambda) là cú pháp được Java giới thiệu từ Java 8 để truyền một đoạn hành vi vào nơi cần một đối tượng có kiểu **functional interface**. Lambda thường là cách ngắn gọn để cung cấp phần thân cho phương thức trừu tượng duy nhất của interface đó.

Lambda không tự tạo ra một kiểu dữ liệu độc lập. Trình biên dịch xác định kiểu đích từ ngữ cảnh, chẳng hạn biến được gán, tham số phương thức hoặc phép ép kiểu. Vì vậy, một lambda chỉ hợp lệ khi ngữ cảnh xác định được functional interface tương ứng.

## 1. Functional interface là nền tảng của lambda

Functional interface là interface có đúng một phương thức trừu tượng theo quy tắc của Java. Phương thức này còn được gọi là **SAM** (*Single Abstract Method*). Lambda cung cấp phần triển khai cho phương thức đó.

~~~java
@FunctionalInterface
interface Greeter {
    String greet(String name);
}
~~~

Có thể cung cấp cách triển khai bằng lambda:

~~~java
Greeter greeter = name -> "Xin chào, " + name;
System.out.println(greeter.greet("An"));
~~~

Kết quả:

~~~text
Xin chào, An
~~~

Chú thích **@FunctionalInterface** không bắt buộc để dùng lambda, nhưng nên dùng vì trình biên dịch sẽ báo lỗi nếu interface không còn đáp ứng quy tắc functional interface. Interface vẫn có thể khai báo phương thức **default** và **static**; chúng không làm tăng số phương thức trừu tượng. Các phương thức trừu tượng kế thừa có cùng chữ ký cũng có thể được xem là một phương thức duy nhất. Những phương thức tương ứng với phương thức public của **Object**, chẳng hạn **equals(Object)**, không làm tăng số phương thức SAM.

Interface có hai phương thức trừu tượng độc lập không thể được triển khai bằng một lambda đơn lẻ:

~~~java
interface InvalidHandler {
    void start();
    void stop();
}

// Không hợp lệ:
// InvalidHandler handler = () -> System.out.println("run");
~~~

Nếu cần cả hai hành vi, hãy thiết kế lại interface hoặc dùng một lớp triển khai đầy đủ.

## 2. Cú pháp và cách đọc lambda

Các dạng phổ biến:

~~~java
() -> doSomething()
value -> value * 2
(left, right) -> left + right
(String value) -> value.trim()
(value) -> {
    String normalized = value.trim();
    return normalized.toUpperCase();
}
~~~

Quy tắc đọc:

- Phần bên trái **->** là danh sách tham số; phần bên phải là biểu thức hoặc khối lệnh.
- Không có tham số thì dùng **()**.
- Với một tham số có kiểu được suy luận, có thể bỏ cặp ngoặc đơn: **value -> ...**.
- Có nhiều tham số thì đặt trong ngoặc đơn và phân tách bằng dấu phẩy.
- Có thể ghi rõ kiểu tham số, nhưng nếu ghi kiểu thì phải ghi nhất quán cho các tham số trong cùng danh sách.
- Thân lambda là một biểu thức thì giá trị biểu thức được trả về khi phương thức có kiểu trả về. Với thân dạng khối **{ ... }**, phải dùng **return** khi phương thức cần trả về giá trị; khối của phương thức **void** không trả về giá trị.
- Kiểu tham số thường được suy luận từ kiểu đích, vì vậy không cần lặp lại kiểu nếu không giúp mã rõ hơn.

Ví dụ, hai cách sau có thể tương đương khi kiểu đích đã là **Function&lt;Integer, Integer&gt;**:

~~~java
Function<Integer, Integer> doubled = value -> value * 2;
Function<Integer, Integer> alsoDoubled = (Integer value) -> value * 2;
~~~

Trình biên dịch không thể suy luận kiểu đích nếu chỉ viết một lambda đứng riêng. Chẳng hạn, **var f = value -> value + 1;** không hợp lệ vì không có kiểu đích để suy ra kiểu của lambda. Hãy khai báo kiểu functional interface rõ ràng hoặc cung cấp lambda trong một ngữ cảnh đã xác định kiểu.

## 3. Chương trình hoàn chỉnh: tự định nghĩa interface và dùng interface có sẵn

Tạo tệp **LambdaAsImplementationDemo.java**:

~~~java
import java.util.Locale;
import java.util.function.Predicate;

public class LambdaAsImplementationDemo {
    @FunctionalInterface
    interface TextFormatter {
        String format(String value);
    }

    public static void main(String[] args) {
        TextFormatter upper = value -> value.toUpperCase(Locale.ROOT);
        TextFormatter wrapped = value -> "[" + value + "]";

        System.out.println(upper.format("java"));
        System.out.println(wrapped.format("lambda"));

        Predicate<String> nonBlank =
                value -> value != null && !value.isBlank();

        System.out.println(nonBlank.test("hello"));
        System.out.println(nonBlank.test("   "));
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac LambdaAsImplementationDemo.java
java LambdaAsImplementationDemo
~~~

Kết quả stdout chính xác:

~~~text
JAVA
[lambda]
true
false
~~~

Ở ví dụ trên, biến **upper** và **wrapped** có kiểu **TextFormatter**; mỗi lambda cung cấp triển khai cho phương thức **format**. Biến **nonBlank** có kiểu **Predicate&lt;String&gt;**; lambda cung cấp triển khai cho phương thức **test**, trả về **true** hoặc **false**. Điều kiện kiểm tra **value != null** phải đứng trước **value.isBlank()** để tránh gọi phương thức trên giá trị null. **String.isBlank()** có từ Java 11.

## 4. Các functional interface thường gặp trong thư viện Java

| Interface | Phương thức trừu tượng | Ý nghĩa thường dùng |
|---|---|---|
| **Runnable** | **void run()** | Hành động không tham số, không trả kết quả |
| **Supplier&lt;T&gt;** | **T get()** | Cung cấp một giá trị |
| **Consumer&lt;T&gt;** | **void accept(T)** | Nhận và xử lý một giá trị |
| **Function&lt;T, R&gt;** | **R apply(T)** | Chuyển một giá trị kiểu T thành kiểu R |
| **Predicate&lt;T&gt;** | **boolean test(T)** | Kiểm tra một điều kiện |
| **UnaryOperator&lt;T&gt;** | **T apply(T)** | Nhận và trả về cùng kiểu T |
| **BiFunction&lt;T, U, R&gt;** | **R apply(T, U)** | Kết hợp hai đầu vào để tạo kết quả |
| **BinaryOperator&lt;T&gt;** | **T apply(T, T)** | Kết hợp hai giá trị cùng kiểu để tạo giá trị cùng kiểu |
| **Comparator&lt;T&gt;** | **int compare(T, T)** | Xác định thứ tự so sánh hai đối tượng |

Các interface phổ biến trên nằm trong **java.lang** hoặc **java.util.function**; **Comparator** thuộc **java.util**. Những kiểu này cho phép API nhận hành vi dưới dạng tham số thay vì buộc người gọi tạo một lớp riêng cho từng trường hợp.

~~~java
Predicate<String> startsWithJ = text -> text.startsWith("J");
Function<String, Integer> length = text -> text.length();
Consumer<String> print = text -> System.out.println(text);
Supplier<String> defaultName = () -> "Guest";

System.out.println(startsWithJ.test("Java")); // true
System.out.println(length.apply("Java"));     // 4
print.accept(defaultName.get());              // Guest
~~~

Đoạn trên minh họa cú pháp; khi đặt vào một chương trình, cần thêm các import tương ứng cho **Predicate**, **Function**, **Consumer** và **Supplier** từ **java.util.function**.

## 5. Lambda dùng làm callback cho API

Một lợi ích chính của lambda là truyền cách xử lý vào API. Ví dụ, **List.sort** nhận một **Comparator**, còn **forEach** nhận một **Consumer**.

Tạo tệp **LambdaSortDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LambdaSortDemo {
    record Course(String name, int durationHours) {}

    public static void main(String[] args) {
        List<Course> courses = new ArrayList<>(List.of(
                new Course("Streams", 4),
                new Course("Lambda", 2),
                new Course("Generics", 3)
        ));

        courses.sort((left, right) ->
                Integer.compare(left.durationHours(), right.durationHours()));

        courses.forEach(course ->
                System.out.println(course.name() + ": " + course.durationHours()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LambdaSortDemo.java
java LambdaSortDemo
~~~

Kết quả stdout:

~~~text
Lambda: 2
Generics: 3
Streams: 4
~~~

Lambda truyền vào **sort** so sánh thời lượng của hai khóa học; số âm, số 0 hoặc số dương lần lượt biểu thị thứ tự trước, bằng nhau hoặc sau theo hợp đồng của **Comparator**. Lambda truyền vào **forEach** in từng phần tử. Bản thân lambda không tự tạo luồng hay chạy bất đồng bộ; API gọi nó khi và theo cách mà API quy định.

## 6. Thân lambda dạng khối và giá trị trả về

Dùng thân dạng biểu thức khi hành vi ngắn gọn. Dùng thân dạng khối khi cần nhiều bước, biến cục bộ, điều kiện hoặc xử lý lỗi.

~~~java
import java.util.function.IntUnaryOperator;

IntUnaryOperator addTenPercent = price -> {
    int tax = Math.round(price * 0.1f);
    return price + tax;
};

System.out.println(addTenPercent.applyAsInt(100));
~~~

Kết quả là **110**. Đây là đoạn minh họa một biểu thức có thể đặt trong phương thức; nếu muốn chạy độc lập, hãy đặt phần khai báo và câu lệnh in bên trong **main** của một lớp Java.

Với functional interface có kiểu trả về khác **void**, mọi nhánh thực thi của thân khối phải trả về giá trị phù hợp. Không thể bỏ **return** chỉ vì lambda được viết nhiều dòng. Với interface trả về **void**, thân khối có thể chứa nhiều câu lệnh nhưng không được trả về một giá trị.

## 7. Biến cục bộ được lambda sử dụng

Lambda có thể đọc biến cục bộ trong phạm vi bao quanh nếu biến đó là **final** hoặc **effectively final**: biến được gán một lần và không bị gán lại sau đó.

~~~java
int offset = 10;
IntUnaryOperator addOffset = value -> value + offset;
System.out.println(addOffset.applyAsInt(5)); // 15
~~~

Ví dụ sau không hợp lệ vì **offset** bị gán lại sau khi được dùng trong lambda:

~~~java
int offset = 10;
IntUnaryOperator addOffset = value -> value + offset;
offset = 20; // Lỗi biên dịch: offset không còn effectively final
~~~

Quy tắc này áp dụng cho biến cục bộ và tham số phương thức được capture. Lambda vẫn có thể đọc hoặc thay đổi trạng thái của một đối tượng mà biến tham chiếu tới, nếu quyền truy cập cho phép; tuy nhiên, tính bất biến của tham chiếu không đồng nghĩa đối tượng được tham chiếu là bất biến. Cần cẩn thận với trạng thái dùng chung trong xử lý đa luồng.

## 8. Phạm vi của this và tên biến

Trong lambda, **this** tham chiếu tới đối tượng bao quanh nơi lambda được viết. Lambda không tạo một lớp lồng ẩn danh với một đối tượng **this** riêng. Đây là điểm khác biệt quan trọng so với lớp ẩn danh, nơi **this** bên trong phần thân thường tham chiếu tới instance của lớp ẩn danh.

Tham số lambda không được trùng tên với biến cục bộ đã khai báo trong cùng phạm vi bao quanh. Hãy chọn tên tham số rõ nghĩa và tránh che khuất tên biến khiến mã khó đọc.

## 9. Kiểm tra ngoại lệ

Kiểu phương thức SAM quyết định các ngoại lệ checked mà thân lambda được phép ném. Nếu phương thức trừu tượng không khai báo một ngoại lệ checked nào, lambda không thể ném trực tiếp ngoại lệ checked đó mà không xử lý hoặc chuyển đổi nó. Ví dụ, **Runnable.run()** không khai báo ngoại lệ checked, trong khi **Callable.call()** có thể ném **Exception**.

Khi tích hợp API có thể phát sinh ngoại lệ, hãy xử lý ở nơi phù hợp hoặc định nghĩa một functional interface có chữ ký ngoại lệ phù hợp. Không nên bọc mọi ngoại lệ thành ngoại lệ runtime một cách máy móc, vì việc đó làm mất thông tin về cách gọi cần xử lý lỗi.

## 10. Lambda và method reference

Khi lambda chỉ gọi một phương thức với các tham số tương ứng, **method reference** có thể biểu đạt cùng ý định gọn hơn:

~~~java
Function<String, String> trimWithLambda = text -> text.trim();
Function<String, String> trimWithReference = String::trim;
~~~

Một số dạng method reference là **TênLớp::phươngThứcTĩnh**, **đốiTượng::phươngThứcInstance** và **TênLớp::phươngThứcInstance**. Method reference cũng cần một kiểu functional interface làm kiểu đích; đây là cú pháp liên quan và có thể thay thế lambda khi chữ ký tương thích.

## 11. Lambda so với lớp ẩn danh

Lambda phù hợp khi cần cung cấp một hành vi duy nhất cho functional interface. Nó ngắn gọn, giúp thể hiện trực tiếp hành vi được truyền vào API và sử dụng ngữ cảnh **this** của lớp bao quanh.

Lớp ẩn danh vẫn hữu ích khi cần khai báo nhiều phương thức, ghi đè thêm hành vi, hoặc cần một lớp con của lớp trừu tượng thay vì triển khai functional interface. Không thể thay thế mọi lớp ẩn danh bằng lambda vì lambda chỉ nhắm tới functional interface.

Không nên dựa vào việc hai lambda có cùng phần thân thì chắc chắn bằng nhau hoặc là cùng một instance; định danh của đối tượng lambda không được đảm bảo theo cách đó. Nếu cần so sánh kết quả, hãy so sánh đầu ra hoặc dữ liệu miền nghiệp vụ.

## 12. Lỗi thường gặp và cách khắc phục

- **Interface có nhiều phương thức trừu tượng:** chỉ dùng lambda khi kiểu đích là functional interface; rà soát thiết kế và dùng **@FunctionalInterface** để trình biên dịch kiểm tra.
- **Không có kiểu đích:** khai báo biến bằng kiểu functional interface, truyền lambda vào tham số có kiểu rõ ràng hoặc ép kiểu khi thực sự cần.
- **Sai kiểu tham số hoặc kiểu trả về:** so khớp chữ ký lambda với phương thức SAM, kể cả kiểu **void** và kiểu trả về.
- **Thiếu return trong thân khối:** thêm **return** cho mọi nhánh khi phương thức SAM yêu cầu kết quả.
- **Gán lại biến cục bộ đã capture:** giữ biến final/effectively final hoặc thiết kế lại cách truyền dữ liệu.
- **Mơ hồ khi gọi phương thức overload:** nếu nhiều overload nhận các functional interface có hình dạng tương thích, trình biên dịch có thể không chọn được; cung cấp kiểu tham số rõ ràng hoặc ép kiểu về interface đích thích hợp.
- **Giả định lambda tự chạy song song:** lambda chỉ mô tả hành vi; luồng thực thi do đoạn mã gọi lambda quyết định.
- **Đưa quá nhiều xử lý vào một lambda:** tách logic phức tạp thành phương thức có tên để dễ kiểm thử và bảo trì.

## 13. Quy trình chọn và viết lambda

1. Xác định API cần một hành vi nào và tìm kiểu tham số functional interface của API.
2. Xem chữ ký SAM: số lượng tham số, kiểu tham số, kiểu trả về và ngoại lệ được khai báo.
3. Viết lambda khớp chữ ký đó; để trình biên dịch suy luận kiểu khi ngữ cảnh đã rõ.
4. Chọn thân biểu thức cho xử lý đơn giản hoặc thân khối cho nhiều bước.
5. Kiểm tra quy tắc capture, phạm vi tên, ngoại lệ và các overload có thể gây mơ hồ.
6. Chạy ví dụ với đầu vào đại diện, kiểm tra stdout hoặc kết quả thực tế và giữ phần xử lý đủ rõ để bảo trì.

Lambda giúp Java truyền hành vi như một giá trị thông qua functional interface. Khi hiểu kiểu đích và chữ ký SAM, có thể dùng lambda để triển khai callback, lọc, ánh xạ, sắp xếp và nhiều thao tác API khác mà không cần tạo một lớp riêng cho mỗi hành vi nhỏ.