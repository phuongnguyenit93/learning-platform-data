# Chọn interface riêng hay dùng Runnable, Callable và java.util.function

Khi cần truyền một hành vi vào method khác, Java thường cho phép dùng lambda hoặc method reference. Câu hỏi quan trọng là kiểu interface nào mô tả đúng hợp đồng của hành vi đó. Hãy ưu tiên kiểu mà API đang yêu cầu; nếu tự thiết kế API, chọn kiểu chuẩn khi ý nghĩa đã khớp và tạo interface riêng khi hợp đồng nghiệp vụ cần tên gọi hoặc quy tắc riêng.

## 1. Phân biệt interface thông thường và functional interface

**Functional interface** là interface có đúng một phương thức trừu tượng cần triển khai. Có thể đánh dấu bằng @FunctionalInterface để trình biên dịch kiểm tra điều kiện này. Interface vẫn có thể có các phương thức default và static.

~~~java
@FunctionalInterface
interface DiscountPolicy {
    long finalPrice(long originalPrice);
}
~~~

Vì chỉ có một thao tác trừu tượng, ta có thể truyền lambda như `price -> price * 90 / 100`. Tên interface như DiscountPolicy cho người đọc biết lambda đang biểu diễn chính sách giảm giá nào.

Interface thông thường có thể có nhiều phương thức trừu tượng và biểu diễn một hợp đồng gồm nhiều thao tác. Lambda không thể tự triển khai một interface có nhiều phương thức trừu tượng; trường hợp đó thường cần một lớp triển khai hoặc anonymous class.

## 2. Khi nào dùng các kiểu chuẩn?

| Nhu cầu | Kiểu phù hợp | Hợp đồng |
| --- | --- | --- |
| Một tác vụ không nhận đầu vào, không trả kết quả | Runnable | `void run()` |
| Một tác vụ có kết quả và có thể ném checked exception | Callable&lt;T&gt; | `T call() throws Exception` |
| Biến đổi một giá trị T thành R | Function&lt;T, R&gt; | `R apply(T value)` |
| Kiểm tra một giá trị và trả về đúng/sai | Predicate&lt;T&gt; | `boolean test(T value)` |
| Nhận một giá trị và thực hiện hành động | Consumer&lt;T&gt; | `void accept(T value)` |
| Cung cấp giá trị mà không cần đầu vào | Supplier&lt;T&gt; | `T get()` |
| Biến đổi một giá trị thành cùng kiểu | UnaryOperator&lt;T&gt; | Là dạng chuyên biệt của Function&lt;T, T&gt; |
| Kết hợp hai giá trị cùng kiểu thành một giá trị cùng kiểu | BinaryOperator&lt;T&gt; | Là dạng chuyên biệt của BiFunction&lt;T, T, T&gt; |

Các kiểu trong bảng thuộc những API chuẩn của Java; Runnable nằm trong java.lang, Callable trong java.util.concurrent, còn Function, Predicate, Consumer, Supplier và các biến thể nằm trong java.util.function. Chúng phù hợp khi hợp đồng của bạn thực sự giống với ý nghĩa và chữ ký của kiểu đó.

### Ví dụ: dùng java.util.function

Tệp `StandardFunctionsDemo.java`:

~~~java
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;

public class StandardFunctionsDemo {
    public static void main(String[] args) {
        Function<String, Integer> length = String::length;
        Predicate<Integer> isPositive = n -> n > 0;
        Supplier<String> greeting = () -> "Xin chao";
        Consumer<String> print = System.out::println;

        System.out.println(length.apply("Java"));
        System.out.println(isPositive.test(3));
        System.out.println(greeting.get());
        print.accept("Hello");
    }
}
~~~

Chạy bằng Java 17 trở lên:

~~~bash
javac StandardFunctionsDemo.java
java StandardFunctionsDemo
~~~

Kết quả:

~~~text
4
true
Xin chao
Hello
~~~

Trong ví dụ này, Function biến chuỗi thành độ dài, Predicate kiểm tra số dương, Supplier tạo lời chào và Consumer in một chuỗi. Không cần tự định nghĩa interface mới vì ý nghĩa đã được các kiểu chuẩn diễn đạt rõ.

## 3. Khi nào nên tạo functional interface riêng?

Tạo interface riêng khi tên kiểu giúp thể hiện ý nghĩa nghiệp vụ, khi hợp đồng cần quy tắc đặc thù, hoặc khi phương thức cần khai báo checked exception mà kiểu chuẩn không hỗ trợ. Ví dụ, DiscountPolicy diễn đạt rõ đây là chính sách tính giá cuối cùng; Function&lt;Long, Long&gt; chỉ cho biết có một phép biến đổi số.

Tệp `DiscountDemo.java`:

~~~java
@FunctionalInterface
interface DiscountPolicy {
    long finalPrice(long originalPrice);
}

public class DiscountDemo {
    public static void main(String[] args) {
        DiscountPolicy memberDiscount = price -> price * 90 / 100;
        System.out.println(memberDiscount.finalPrice(100_000L));
    }
}
~~~

Chạy:

~~~bash
javac DiscountDemo.java
java DiscountDemo
~~~

Kết quả:

~~~text
90000
~~~

Tên DiscountPolicy làm rõ mục đích của tham số mà method nhận vào. Trong API công khai hoặc mã nghiệp vụ, kiểu có tên miền cụ thể thường dễ đọc hơn khi hợp đồng đó thực sự có ý nghĩa riêng.

Một trường hợp khác là checked exception. Các phương thức của Function và phần lớn kiểu trong java.util.function không khai báo checked exception. Nếu hành vi cần ném IOException, có thể xử lý ngoại lệ ngay trong lambda, bọc ngoại lệ thành unchecked exception, hoặc định nghĩa hợp đồng riêng:

~~~java
@FunctionalInterface
interface IOFunction<T, R> {
    R apply(T input) throws java.io.IOException;
}
~~~

Chỉ nên tạo kiểu như IOFunction khi việc truyền checked exception là một phần hữu ích của API. Tránh tạo các interface như MyFunction&lt;T, R&gt; chỉ để lặp lại Function&lt;T, R&gt; mà không bổ sung ý nghĩa hay hành vi nào.

## 4. Runnable và Callable trong tác vụ bất đồng bộ

Runnable và Callable đều mô tả tác vụ, nhưng hợp đồng khác nhau:

- **Runnable** không trả kết quả và phương thức run() không khai báo checked exception. Dùng khi cần thực hiện một hành động, chẳng hạn ghi log hoặc cập nhật trạng thái.
- **Callable&lt;T&gt;** trả về giá trị kiểu T và phương thức call() có thể khai báo Exception. Dùng khi tác vụ cần trả kết quả hoặc truyền checked exception về nơi lấy kết quả.
- Khi nộp tác vụ bằng ExecutorService.submit(...), kết quả là Future. Future.get() chờ tác vụ hoàn tất; với Callable, nó trả kết quả. Với Runnable, Future.get() trả về null khi tác vụ hoàn tất bình thường.
- Future.get() có thể ném InterruptedException hoặc ExecutionException. Mã thực tế nên xử lý hai trường hợp này phù hợp; nếu bắt InterruptedException mà không tiếp tục ném ra, thường cần khôi phục cờ ngắt bằng Thread.currentThread().interrupt().

Tệp `ExecutorTasksDemo.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ExecutorTasksDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<?> completed = pool.submit(
                () -> System.out.println("Runnable ran")
            );
            Future<Integer> answer = pool.submit(() -> 40 + 2);

            completed.get();
            System.out.println(answer.get());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Chạy:

~~~bash
javac ExecutorTasksDemo.java
java ExecutorTasksDemo
~~~

Kết quả:

~~~text
Runnable ran
42
~~~

Executor đơn luồng thực hiện hai tác vụ theo thứ tự đã nộp, nên đầu ra trên ổn định. finally bảo đảm gọi shutdown() kể cả khi lấy kết quả gặp lỗi. shutdown() ngừng nhận tác vụ mới và cho các tác vụ đã nộp có cơ hội hoàn tất; nó không tự chờ như awaitTermination().

Đừng nhầm Callable với Supplier&lt;T&gt;. Cả hai đều có thể trả về T, nhưng Supplier&lt;T&gt; là kiểu cung cấp giá trị tổng quát, không khai báo checked exception; Callable&lt;T&gt; được thiết kế cho tác vụ có kết quả trong API concurrency và có thể ném Exception. Hãy dùng đúng kiểu theo API mà bạn đang gọi.

## 5. Những biến thể hữu ích

Khi thao tác với kiểu nguyên thủy thường xuyên, dùng các interface chuyên biệt có thể tránh boxing/unboxing không cần thiết, ví dụ IntPredicate, IntConsumer, IntSupplier, IntUnaryOperator, LongUnaryOperator hoặc ToIntFunction&lt;T&gt;. Khi nhận hai tham số, cân nhắc BiFunction&lt;T, U, R&gt;, BiPredicate&lt;T, U&gt; hoặc BiConsumer&lt;T, U&gt;. Đừng chọn kiểu phức tạp hơn nếu Function, Predicate, Consumer hoặc Supplier đã mô tả đủ hợp đồng.

Một số functional interface chuẩn còn hỗ trợ ghép hành vi: Function có compose() và andThen(), Predicate có and(), or() và negate(), Consumer có andThen(). Những phương thức này hữu ích khi cần kết hợp nhiều bước mà vẫn giữ kiểu dữ liệu rõ ràng.

## 6. Quy trình chọn kiểu

1. **Kiểm tra chữ ký API trước.** Nếu method yêu cầu Runnable, Callable&lt;T&gt; hoặc một kiểu chuẩn khác, hãy cung cấp đúng kiểu đó.
2. **So khớp số lượng tham số và kiểu kết quả.** Không đầu vào/không kết quả thường là Runnable; không đầu vào/có kết quả có thể là Supplier&lt;T&gt; hoặc Callable&lt;T&gt; tùy API và quy tắc ngoại lệ; T thành R là Function&lt;T, R&gt;; T thành boolean là Predicate&lt;T&gt;.
3. **Xem ý nghĩa nghiệp vụ.** Nếu tên kiểu như DiscountPolicy, RetryPolicy hoặc AuthorizationRule làm hợp đồng rõ hơn đáng kể, interface riêng có thể phù hợp.
4. **Xem ngoại lệ và các ràng buộc đặc thù.** Nếu cần khai báo checked exception hoặc API cần hợp đồng riêng, cân nhắc interface tùy chỉnh.
5. **Phân biệt một hành vi với nhiều thao tác.** Một thao tác trừu tượng phù hợp với lambda; nhiều thao tác độc lập thường cần interface thông thường.
6. **Ưu tiên đơn giản và nhất quán.** Đừng tạo nhiều kiểu tương đương chỉ khác tên nếu chúng không diễn đạt khác biệt có ích.

## 7. Lỗi thường gặp

- Chọn Runnable cho công việc cần trả dữ liệu, rồi cố lấy kết quả từ Future của Runnable. Hãy dùng Callable&lt;T&gt; khi submit cần kết quả.
- Dùng Supplier&lt;T&gt; cho tác vụ nộp vào API yêu cầu Callable&lt;T&gt;. Hai kiểu có chữ ký gần nhau nhưng không thay thế tự động cho nhau; hãy dùng lambda phù hợp với kiểu đích mà API yêu cầu.
- Dùng Function&lt;T, Boolean&gt; cho điều kiện đúng/sai. Predicate&lt;T&gt; thể hiện mục đích rõ hơn và cung cấp các phép kết hợp điều kiện.
- Tạo interface riêng trùng hoàn toàn với Function hoặc Consumer mà không có ý nghĩa bổ sung. Việc này làm API có nhiều kiểu phải học và chuyển đổi hơn.
- Quên rằng lambda cần kiểu đích. Khai báo kiểu rõ ràng hoặc truyền lambda vào method có tham số functional interface; không thể suy luận kiểu đích cho một lambda độc lập như một giá trị thông thường.
- Cho nhiều overload chỉ khác nhau bởi các functional interface có chữ ký tương tự. Một số lambda có thể trở nên khó chọn hoặc gây mơ hồ; tên method riêng hoặc kiểu tham số rõ ràng giúp API dễ sử dụng hơn.
- Quên xử lý lỗi khi gọi Future.get(). Lỗi trong tác vụ thường được bọc trong ExecutionException; cần kiểm tra nguyên nhân gốc khi chẩn đoán.

Nguyên tắc thực hành: dùng interface chuẩn khi nó biểu đạt chính xác hợp đồng và phù hợp với API; dùng interface riêng khi tên miền, checked exception hoặc quy tắc đặc thù làm hợp đồng trở nên rõ ràng hơn. Với tác vụ concurrency, phân biệt rõ hành động không kết quả (Runnable) và tác vụ có kết quả (Callable&lt;T&gt;).