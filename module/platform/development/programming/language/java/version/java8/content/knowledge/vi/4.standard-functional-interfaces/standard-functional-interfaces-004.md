# Supplier và cung cấp giá trị theo nhu cầu trong Java

## Mục tiêu học tập

Trong Java, có lúc ta đã biết **cách tạo một giá trị**, nhưng chưa chắc **khi nào giá trị đó thực sự cần dùng**. Ví dụ: tính một giá trị dự phòng tốn tài nguyên, tạo một mã mới khi được yêu cầu, dựng thông báo lỗi chỉ khi xảy ra lỗi, hoặc sinh từng phần tử cho một luồng dữ liệu.

**Supplier<T>** thuộc gói **java.util.function** là một giao diện hàm cho tình huống này: nó đại diện cho **một phép cung cấp giá trị không nhận đối số**. Thay vì truyền ngay giá trị đã được tính, ta có thể truyền cách tạo giá trị và để bên nhận quyết định thời điểm gọi.

Sau bài học, bạn sẽ hiểu chữ ký và cách viết Supplier, phân biệt **trì hoãn thực hiện (lazy evaluation)** với **ghi nhớ kết quả (memoization)**, sử dụng Supplier với Optional, Stream và API báo lỗi, nhận diện giới hạn về ngoại lệ, dữ liệu thay đổi và an toàn luồng. Những nội dung này vẫn áp dụng trên JDK hiện đại; ví dụ đầy đủ dùng cú pháp và API có từ Java 8, chạy được với JDK 8 trở lên.

## 1. Supplier là gì?

Giao diện chuẩn được khai báo về ý nghĩa như sau:

~~~java
@FunctionalInterface
public interface Supplier<T> {
    T get();
}
~~~

Đây là **mô tả chữ ký** của giao diện chuẩn, không phải một tệp cần tự tạo trong ứng dụng. Khi viết chương trình, import **java.util.function.Supplier**.

Có ba đặc điểm cốt lõi:

1. **Không nhận đối số:** phương thức chức năng là **get()**, do đó lambda có dạng **() -> ...**.
2. **Trả về T:** T là kiểu giá trị mà lời gọi get() trả về, ví dụ **Supplier<String>**, **Supplier<Integer>**, **Supplier<List<String>>**.
3. **Không bảo đảm lưu kết quả:** mỗi lần gọi get() có thể tạo giá trị mới, trả lại cùng giá trị, đọc trạng thái hiện tại hoặc gây tác dụng phụ. Hợp đồng Supplier không tự quyết định điều đó.

Ví dụ:

~~~java
Supplier<String> greeting = () -> "Xin chào";
Supplier<Integer> answer = () -> 42;
Supplier<StringBuilder> freshBuilder = () -> new StringBuilder();
~~~

Đây là các **đoạn minh họa** cần import Supplier và đặt trong một phương thức hoặc lớp thích hợp. Supplier đầu luôn trả một chuỗi cùng nội dung; Supplier thứ hai trả số 42 (được boxing sang Integer); Supplier cuối tạo một đối tượng StringBuilder mới trong mỗi lần gọi.

**Tạo lambda không gọi phần thân của nó.** Chỉ khi thực thi **greeting.get()**, **answer.get()**, **freshBuilder.get()**, hoặc khi API nhận Supplier chủ động gọi get(), công việc mới diễn ra.

### Mô hình thời gian

~~~text
Tạo Supplier          Gửi Supplier cho nơi sử dụng          Nơi sử dụng gọi get()
     |                           |                                    |
     v                           v                                    v
  () -> tạoGiáTrị       giữ cách tạo, chưa cần giá trị         thực thi tạoGiáTrị()
                                                                  |
                                                                  v
                                                             nhận kết quả T
~~~

Đường thời gian này giải thích **khả năng trì hoãn**, không hứa rằng Java sẽ tự tối ưu thời điểm gọi. Quyền quyết định gọi hay không gọi, gọi bao nhiêu lần thuộc về **mã bên sử dụng**.

## 2. Khác nhau giữa truyền giá trị và truyền cách tạo giá trị

Xem hai kiểu phương thức:

~~~java
String direct = buildDefault();
String lazy = useDefaultIfNeeded(input, () -> buildDefault());
~~~

Đây là sơ đồ sử dụng: **buildDefault()** và **useDefaultIfNeeded(...)** cần được định nghĩa ở ngữ cảnh đầy đủ. Trong dòng đầu, buildDefault() chạy ngay để tạo biến direct. Trong dòng hai, phần **() -> buildDefault()** mô tả cách tạo giá trị; buildDefault() sẽ chạy khi và chỉ khi **useDefaultIfNeeded** gọi phương thức get() của Supplier được truyền vào.

Ví dụ triển khai một API nhỏ:

~~~java
static String useDefaultIfNeeded(
        String input,
        java.util.function.Supplier<String> fallback) {
    return input != null ? input : fallback.get();
}
~~~

Đoạn này chỉ là **phương thức minh họa** cần đặt trong một lớp. Nếu input không null, nhánh có fallback.get() không chạy, vì vậy có thể tránh việc tính giá trị dự phòng. Nếu input null, phương thức yêu cầu Supplier cung cấp một chuỗi.

**Phân biệt hai ý:**

- **Trì hoãn (lazy):** lùi thời điểm thực thi phép tính cho đến khi có nhu cầu.
- **Lưu nhớ (memoized/cached):** sau khi thực thi một lần, lưu kết quả để những lần yêu cầu sau dùng lại.

Một Supplier có thể lazy nhưng **không** memoized: mỗi lần get() lại tính. Nếu muốn chỉ tính tối đa một lần, phải thêm cơ chế lưu kết quả hoặc dùng một API có hợp đồng rõ ràng về lưu nhớ. Không được suy ra “Supplier = khởi tạo một lần”.

## 3. Ví dụ hoàn chỉnh: Supplier chạy khi được gọi và có thể chạy nhiều lần

Tạo tệp **SupplierBasicsDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class SupplierBasicsDemo {
    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger(0);

        Supplier<String> codeGenerator = () -> {
            int sequence = calls.incrementAndGet();
            System.out.println("Tạo lần " + sequence);
            return "Mã-" + sequence;
        };

        System.out.println("Chưa gọi: " + calls.get());
        System.out.println("Lần 1: " + codeGenerator.get());
        System.out.println("Lần 2: " + codeGenerator.get());
        System.out.println("Đã gọi: " + calls.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 SupplierBasicsDemo.java
java SupplierBasicsDemo
~~~

Kết quả chính xác:

~~~text
Chưa gọi: 0
Tạo lần 1
Lần 1: Mã-1
Tạo lần 2
Lần 2: Mã-2
Đã gọi: 2
~~~

**Điều cần quan sát:** dòng khai báo codeGenerator **không in gì và không tăng calls**. Lần get() thứ nhất mới sinh mã 1, lần thứ hai sinh mã 2. Supplier có thể giữ trạng thái thông qua một đối tượng được lambda bắt giữ; ở đây dùng AtomicInteger để việc tăng biến đếm là nguyên tử nếu sau này có nhiều luồng, nhưng ví dụ hiện tại chỉ gọi tuần tự.

Không phải mọi Supplier đều tạo kết quả khác nhau. Ví dụ **() -> "OK"** thường trả cùng chuỗi nội dung ở mỗi lần gọi; **() -> new Object()** tạo đối tượng mới; **() -> System.currentTimeMillis()** đọc thời gian tại lúc gọi. Hãy nhìn vào **phần thân lambda** và hợp đồng của API chứ không suy đoán từ tên Supplier.

## 4. Supplier, Runnable, Callable và Function khác nhau ở đâu?

Các giao diện hàm này cùng mô tả hành vi, nhưng mục đích và chữ ký khác nhau:

| Giao diện | Phương thức chức năng | Nhận tham số | Kết quả | Cách dùng điển hình |
| --- | --- | --- | --- | --- |
| **Supplier<T>** | T get() | 0 | T | Cung cấp một giá trị khi cần |
| **Runnable** | void run() | 0 | Không có giá trị | Thực hiện một hành động |
| **Callable<V>** | V call() throws Exception | 0 | V | Tác vụ có kết quả và hợp đồng cho checked exception |
| **Function<T,R>** | R apply(T input) | 1 | R | Biến đổi đầu vào thành đầu ra |

**Supplier<T> không phải Runnable:** một lambda **() -> 42** thích hợp Supplier<Integer>, nhưng không thích hợp Runnable vì literal 42 không tạo thân void hợp lệ.

**Supplier<T> không phải Function<T,R>:** Function cần một đối số; Supplier không cần. Nếu cần truyền đầu vào để tạo kết quả, Function thường diễn tả hợp đồng tốt hơn. Ví dụ **name -> "Xin chào " + name** là Function<String,String>, không phải Supplier<String>.

**Supplier<T> không phải Callable<V>:** đều có thể trả giá trị không đối số, nhưng **Callable.call()** khai báo **throws Exception**, còn **Supplier.get()** không khai báo checked exception. Callable thường xuất hiện trong các API tác vụ như ExecutorService.submit(Callable), còn Supplier thường xuất hiện khi API muốn trì hoãn lấy giá trị.

**Supplier không tự tạo luồng và không tự chạy bất đồng bộ.** Lời gọi **get()** trực tiếp thực thi trên luồng đang gọi, giống một phương thức bình thường. Nếu cần thực thi trên executor, phải có một API lên lịch rõ ràng, ví dụ CompletableFuture.supplyAsync(Supplier) dùng Supplier làm nguồn tạo kết quả, đồng thời sử dụng cơ chế thực thi bất đồng bộ do API đó quy định.

## 5. Optional.orElse và Optional.orElseGet: trường hợp điển hình của cung cấp theo nhu cầu

**Optional<T>** biểu diễn khả năng có hoặc không có một giá trị. Hai phương thức rất dễ nhầm:

- **orElse(T other):** nhận một giá trị T đã được tính. Biểu thức truyền làm đối số được đánh giá trước khi orElse được gọi.
- **orElseGet(Supplier<? extends T> supplier):** nhận cách tạo giá trị thay thế và **chỉ gọi supplier.get() khi Optional rỗng**.

Khi giá trị thay thế có chi phí, tác dụng phụ hoặc chỉ hợp lệ lúc thật sự cần, orElseGet thường phù hợp hơn.

Tạo tệp **OptionalFallbackDemo.java**:

~~~java
import java.util.Optional;

public class OptionalFallbackDemo {
    private static String createFallback() {
        System.out.println("Đã tạo giá trị dự phòng");
        return "Khách";
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("An");

        System.out.println(
            "orElse có giá trị: " + present.orElse(createFallback()));

        System.out.println(
            "orElseGet có giá trị: " +
            present.orElseGet(OptionalFallbackDemo::createFallback));

        Optional<String> empty = Optional.empty();

        System.out.println(
            "orElseGet rỗng: " +
            empty.orElseGet(OptionalFallbackDemo::createFallback));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 OptionalFallbackDemo.java
java OptionalFallbackDemo
~~~

Kết quả chính xác:

~~~text
Đã tạo giá trị dự phòng
orElse có giá trị: An
orElseGet có giá trị: An
Đã tạo giá trị dự phòng
orElseGet rỗng: Khách
~~~

Giải thích:

1. Dù present chứa "An", biểu thức **createFallback()** trong **orElse(createFallback())** vẫn được chạy trước, nên thông báo tạo giá trị dự phòng xuất hiện.
2. Với **orElseGet(OptionalFallbackDemo::createFallback)**, Optional đang có giá trị thì Supplier không được gọi.
3. Với Optional.empty(), **orElseGet** gọi Supplier một lần để lấy "Khách".
4. **OptionalFallbackDemo::createFallback** là **method reference** tương thích Supplier<String>: phương thức không nhận đối số, trả String.

**Không nên kết luận orElse luôn sai:** nếu giá trị dự phòng là literal hoặc đã có sẵn, như **optional.orElse("Chưa có")**, cách viết đó rất rõ ràng và không tạo chi phí đáng kể. Lựa chọn dựa trên cách tạo giá trị, không chỉ tên phương thức.

Nếu **orElseGet** được gọi cho Optional rỗng mà Supplier trả về null, kết quả của orElseGet có thể là null; bản thân chữ ký Supplier không cấm null. Điều này khác với một số API khác có hợp đồng không chấp nhận null.

### Optional.orElseThrow với Supplier tạo ngoại lệ

Từ Java 8, Optional còn có overload **orElseThrow(Supplier<? extends X> exceptionSupplier)**, chỉ tạo ngoại lệ khi Optional rỗng. Ví dụ minh họa:

~~~java
String user = optionalUser.orElseThrow(
    () -> new IllegalStateException("Không tìm thấy người dùng"));
~~~

Đây là **đoạn minh họa**, giả sử optionalUser là Optional<String> được khai báo trước. Nếu giá trị tồn tại, lambda không được gọi. Nếu rỗng, Supplier tạo đối tượng ngoại lệ để phương thức ném ra. Cần phân biệt Supplier trả về **đối tượng Throwable** trong ngữ cảnh API này với việc **Supplier.get() tự ném checked exception**, vốn không được chữ ký Supplier thông thường cho phép.

## 6. Stream.generate: sinh phần tử khi luồng dữ liệu cần

**Stream.generate(Supplier<T>)** dùng Supplier để tạo phần tử cho một Stream tuần tự, không có thứ tự gặp được bảo đảm và có khả năng không giới hạn số phần tử. Tạo Stream không nhất thiết đã sinh phần tử: những thao tác trung gian trên Stream có đặc tính lười, và công việc thường được thực hiện khi có thao tác kết thúc (terminal operation).

Ví dụ hoàn chỉnh **StreamSupplierDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StreamSupplierDemo {
    public static void main(String[] args) {
        AtomicInteger sequence = new AtomicInteger(0);

        Supplier<String> nextItem =
            () -> "item-" + sequence.incrementAndGet();

        Stream<String> stream = Stream.generate(nextItem);
        System.out.println("Trước thao tác cuối: " + sequence.get());

        List<String> items = stream
            .limit(3)
            .collect(Collectors.toList());

        System.out.println("Danh sách: " + items);
        System.out.println("Số lần tạo: " + sequence.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StreamSupplierDemo.java
java StreamSupplierDemo
~~~

Kết quả:

~~~text
Trước thao tác cuối: 0
Danh sách: [item-1, item-2, item-3]
Số lần tạo: 3
~~~

Ở đây **Stream.generate(nextItem)** chưa gọi Supplier; sau đó pipeline tuần tự **limit(3).collect(...)** yêu cầu đúng ba phần tử nên Supplier chạy ba lần. Đừng quên rằng Stream.generate có thể tạo nguồn **không giới hạn**; nếu dùng thao tác kết thúc tiêu thụ toàn bộ mà không có điều kiện dừng, chương trình có thể không kết thúc.

Khi xử lý stream song song, thứ tự và số lần gọi hàm nguồn có thể bị ảnh hưởng bởi cách tổ chức thực thi; tuyệt đối không dựa vào tác dụng phụ hay thứ tự đánh số để suy ra tính đúng của pipeline song song. Với ví dụ trên, pipeline được giữ tuần tự để kết quả minh họa là xác định.

**Stream.generate khác Stream.iterate:** generate lấy mỗi phần tử từ Supplier không có tham số; iterate xây phần tử dựa trên phần tử trước. Khi các phần tử độc lập hoặc cần tạo theo yêu cầu, generate có thể phù hợp hơn; khi có quy luật tiến triển từ phần tử trước, iterate diễn tả rõ quan hệ.

## 7. Supplier giúp tạo thông báo lỗi khi cần

Một ứng dụng thực tế thường cần thông báo lỗi có nội dung phải ghép hoặc tính toán tốn chi phí. **Objects.requireNonNull(T obj, Supplier<String> messageSupplier)** có từ Java 8 và chỉ cần thông báo nếu obj là null.

Tạo tệp **LazyErrorMessageDemo.java**:

~~~java
import java.util.Objects;
import java.util.function.Supplier;

public class LazyErrorMessageDemo {
    public static void main(String[] args) {
        Supplier<String> errorMessage = () -> {
            System.out.println("Đang tạo thông báo lỗi");
            return "Tên không được null";
        };

        String name = Objects.requireNonNull("Lan", errorMessage);
        System.out.println("Tên hợp lệ: " + name);

        try {
            Objects.requireNonNull(null, errorMessage);
        } catch (NullPointerException ex) {
            System.out.println("Lỗi: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 LazyErrorMessageDemo.java
java LazyErrorMessageDemo
~~~

Kết quả chính xác:

~~~text
Tên hợp lệ: Lan
Đang tạo thông báo lỗi
Lỗi: Tên không được null
~~~

Supplier không chạy ở lần kiểm tra "Lan" vì đối tượng hợp lệ. Khi kiểm tra null, requireNonNull gọi get() để lấy thông báo, sau đó ném NullPointerException với thông báo vừa được cung cấp. Trong mã ứng dụng, thông báo lỗi nên rõ ràng và không nên làm phát sinh tác dụng phụ không mong muốn, bởi ngoại lệ gốc phải là điều được ưu tiên khi gỡ lỗi.

Một số API logging trên JDK cũng chấp nhận Supplier<String> để trì hoãn tính thông báo; cần xem tài liệu API cụ thể vì không phải mọi overload ghi log đều trì hoãn nội dung. Ví dụ, một biểu thức chuỗi được tính trước khi gọi logger sẽ không tự trở thành lazy chỉ vì sau đó nó được truyền vào một phương thức.

## 8. Cung cấp theo nhu cầu không đồng nghĩa ghi nhớ kết quả

Hãy phân biệt ba chính sách:

| Chính sách | Thời điểm tính | Khi gọi nhiều lần |
| --- | --- | --- |
| Giá trị tính sẵn | Trước khi truyền | Dùng lại kết quả đã có |
| Supplier thông thường | Khi bên sử dụng gọi get() | Có thể tính lại ở **mỗi lần** |
| Supplier có cơ chế memoization | Lần đầu tiên cần giá trị | Thường trả lại kết quả đã lưu sau lần đầu |

Ví dụ **Supplier<String> generator = () -> expensiveCall();** không tự bảo đảm expensiveCall() chỉ chạy một lần. Nếu cần lưu nhớ, API hoặc lập trình viên phải định nghĩa rõ chính sách cache, cách xử lý giá trị null, ngoại lệ và truy cập đồng thời.

### Ví dụ hoàn chỉnh: một Supplier chỉ khởi tạo một lần

Tạo tệp **MemoizedSupplierDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class MemoizedSupplierDemo {
    private static <T> Supplier<T> memoize(Supplier<T> original) {
        return new Supplier<T>() {
            private boolean initialized;
            private T cached;

            @Override
            public synchronized T get() {
                if (!initialized) {
                    cached = original.get();
                    initialized = true;
                }
                return cached;
            }
        };
    }

    public static void main(String[] args) {
        AtomicInteger creations = new AtomicInteger();

        Supplier<String> value = memoize(() -> {
            creations.incrementAndGet();
            System.out.println("Tạo giá trị");
            return "Sẵn sàng";
        });

        System.out.println("Chưa dùng: " + creations.get());
        System.out.println("Lần 1: " + value.get());
        System.out.println("Lần 2: " + value.get());
        System.out.println("Đã tạo: " + creations.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 MemoizedSupplierDemo.java
java MemoizedSupplierDemo
~~~

Kết quả:

~~~text
Chưa dùng: 0
Tạo giá trị
Lần 1: Sẵn sàng
Lần 2: Sẵn sàng
Đã tạo: 1
~~~

Ở ví dụ này, cơ chế memoization nằm trong **lớp ẩn danh** trả về từ phương thức memoize, không nằm trong bản thân interface Supplier. Phương thức get() dùng **synchronized** để không có hai luồng cùng khởi tạo đồng thời và bảo đảm việc nhìn thấy cached sau khi khởi tạo. Biến initialized tách việc “đã tính” khỏi giá trị cached, nên vẫn phân biệt được kết quả null với trạng thái chưa khởi tạo.

Nếu **original.get() ném lỗi** trước khi gán initialized = true, lần gọi sau sẽ thử lại. Đó là một **chính sách cụ thể** của ví dụ, không phải hợp đồng chung của mọi cache. Với hệ thống thực tế, còn cần cân nhắc vòng đời cache, thời điểm làm mới dữ liệu, lỗi, đệ quy trong quá trình khởi tạo và việc giữ tài nguyên.

Ví dụ dùng anonymous class để minh họa việc Supplier chỉ là **kiểu hợp đồng**; cách triển khai có thể là lambda, method reference hoặc một lớp. Không nhất thiết mọi Supplier phải viết dưới dạng lambda.

## 9. Những điểm cần cẩn thận khi thiết kế Supplier

### 9.1. Không bảo đảm hàm thuần hoặc không có tác dụng phụ

Supplier không có tham số nhưng vẫn có thể đọc đồng hồ, trạng thái đối tượng, môi trường, gọi mạng, sinh số ngẫu nhiên hoặc ghi log. Không có tham số đầu vào không đồng nghĩa “luôn trả cùng một giá trị”.

Hãy phân biệt **Supplier mô tả hành vi tạo giá trị** với **giá trị được cung cấp**. Một Supplier đọc thời gian hiện tại có thể cho kết quả khác nhau giữa hai lần gọi; một Supplier bắt giữ biến cục bộ effectively final vẫn có thể đọc đối tượng mutable mà biến đó trỏ tới.

### 9.2. Không tự bảo đảm an toàn luồng

Supplier có thể được nhiều luồng gọi, nhưng giao diện Supplier **không tự đồng bộ**. Nếu phần thân dùng dữ liệu mutable chung, phải bảo vệ theo đúng cách. Ví dụ **AtomicInteger.incrementAndGet()** là nguyên tử; tăng một biến int dùng chung bằng **counter++** không tự trở nên an toàn khi đặt trong lambda.

Lập trình viên cũng cần kiểm tra đối tượng mà Supplier trả về có dùng chung hay không. **() -> new ArrayList<>()** tạo danh sách mới mỗi lần gọi; **() -> sharedList** trả cùng tham chiếu sharedList; hai lựa chọn có khác biệt về quyền sở hữu và an toàn khi sửa.

### 9.3. Không nhận đối số và không có checked exception trong chữ ký

Supplier.get() không khai báo **throws IOException** hay các checked exception khác. Nếu bên trong cần gọi một API ném checked exception, phải xử lý ở trong lambda, hoặc định nghĩa một giao diện hàm khác có hợp đồng ngoại lệ phù hợp. Đừng bọc mọi lỗi vào RuntimeException một cách tùy tiện, làm mất thông tin hoặc khó kiểm soát xử lý lỗi.

Nếu việc tạo giá trị **cần một tham số** từ bên gọi, hãy xem **Function<T,R>**; nếu cần kết quả cùng hợp đồng checked exception, xem **Callable<V>**. Việc chọn đúng interface giúp mã giao tiếp rõ nghĩa.

### 9.4. Kiểm soát giá trị null

Supplier<T> có thể trả null. Tuy nhiên, từng API sử dụng Supplier có thể có quy định riêng về null. Ví dụ Optional.of(...) không nhận null, trong khi Optional.orElseGet(...) có thể trả null nếu Supplier trả null. Không suy diễn từ kiểu T rằng giá trị không bao giờ null.

### 9.5. Không dùng Supplier cho mọi phép tính

Nếu giá trị đã có sẵn hoặc phép tính rất đơn giản, truyền trực tiếp thường dễ hiểu hơn. Supplier chỉ đem lại lợi ích khi **trì hoãn thực thi**, tránh tính toán không cần thiết hoặc mô tả cách cung cấp dữ liệu là một phần của hợp đồng API.

Nếu trì hoãn quá lâu, dữ liệu có thể không còn giống tại thời điểm tạo Supplier. Hãy chủ động quyết định có muốn **giá trị tại thời điểm yêu cầu** hay **bản chụp tại thời điểm cấu hình**.

### 9.6. Không được tự suy luận rằng get() chỉ gọi một lần

Một API nhận Supplier có thể gọi get() **0, 1 hoặc nhiều lần** tùy hợp đồng của API đó. Optional.orElseGet gọi khi thiếu giá trị; Stream.generate có thể gọi nhiều lần; một API do bạn viết có thể gọi hai lần. Nếu logic phụ thuộc số lần gọi hoặc thứ tự tác dụng phụ, phải đọc hợp đồng thực thi cụ thể.

Với Supplier tạo tài nguyên có vòng đời như kết nối, luồng I/O hay file handle, chỉ cung cấp tài nguyên là chưa đủ. Cần xác định rõ ai sở hữu, ai đóng và lúc nào đóng. Không nên tự biến Supplier thành cơ chế quản lý vòng đời tài nguyên mà không có hợp đồng rõ ràng.

## 10. API Java hiện đại có liên quan

Các nguyên lý Supplier không lỗi thời trên JDK mới. Một số API đáng biết:

- **Optional.orElseGet(Supplier<? extends T>)**: Java 8; chỉ tạo fallback khi thiếu giá trị.
- **Optional.orElseThrow(Supplier<? extends X>)**: Java 8; chỉ tạo ngoại lệ khi Optional rỗng.
- **Stream.generate(Supplier<T>)**: Java 8; sinh giá trị cho stream khi pipeline yêu cầu.
- **Objects.requireNonNull(T, Supplier<String>)**: Java 8; chỉ tạo thông báo lỗi khi null.
- **CompletableFuture.supplyAsync(Supplier<U>)**: Java 8; sắp xếp công việc có kết quả để thực hiện bất đồng bộ bằng executor thích hợp; việc chạy bất đồng bộ đến từ **supplyAsync** chứ không đến từ Supplier.
- **Objects.requireNonNullElseGet(T, Supplier<? extends T>)**: có từ Java 9; cung cấp giá trị thay thế khi đối tượng đầu vào null, và theo hợp đồng của API kết quả thay thế không được null. Không dùng phương thức này nếu dự án thật sự phải biên dịch bằng JDK 8.

Mục tiêu của bài là hiểu Supplier như một cơ chế tổng quát, nên khi dùng API hiện đại hãy kiểm tra chính xác **khi nào API gọi get()**, **có chấp nhận null không**, **có dùng executor không** và **có trả lại kết quả đã lưu hay không**. Một interface chung không áp đặt cùng một chính sách cho mọi API.

## 11. Lỗi thường gặp và cách sửa

| Nhận định hoặc mã | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| **Supplier<String> s = "A";** | "A" là giá trị String, không phải hành vi Supplier | **Supplier<String> s = () -> "A";** |
| **Supplier<Integer> s = x -> x + 1;** | Supplier.get() không nhận đối số | Dùng **Function<Integer,Integer>** |
| **Supplier<String> s = () -> { System.out.println("A"); };** | Thiếu String trả về trên đường chạy bình thường | Thêm **return "A";** hoặc dùng Runnable |
| Cho rằng tạo Supplier đã thực hiện phép tính | Lambda chỉ mô tả hành vi | Gọi get() hoặc truyền cho API sẽ gọi |
| Cho rằng get() trả kết quả đã cache | Supplier không có hợp đồng memoization | Cài cơ chế memoization rõ ràng nếu cần |
| Dùng **orElse(expensive())** khi chỉ muốn fallback nếu rỗng | Đối số expensive() được tính trước | Dùng **orElseGet(() -> expensive())** |
| Dùng Stream.generate không có giới hạn rồi collect toàn bộ | Nguồn có thể sinh vô hạn phần tử | Giới hạn hoặc có điều kiện kết thúc rõ ràng |
| Ném thẳng IOException chưa xử lý từ Supplier | get() không khai báo checked exception | Xử lý tại chỗ hoặc chọn giao diện phù hợp |
| Cho rằng Supplier mặc định chạy trên worker | get() trực tiếp chạy trên luồng gọi | Chỉ dùng bất đồng bộ khi API lên lịch rõ ràng |
| Supplier có dữ liệu chung nhưng không đồng bộ | Có thể race condition nếu nhiều luồng cùng gọi | Giảm chia sẻ trạng thái hoặc dùng cơ chế bảo vệ phù hợp |
| Dùng Supplier tạo kết nối rồi quên đóng | Không rõ vòng đời tài nguyên | Xác định trách nhiệm đóng và cách xử lý lỗi |
| Dùng Supplier để che giấu phép tính phụ thuộc thời gian | Kết quả có thể thay đổi giữa các lần gọi | Làm rõ yêu cầu: giá trị mới hay giá trị được chụp/lưu |

## 12. Bài tập thực hành

**Bài 1.** Viết Supplier<String> trả về "Java" và giải thích vì sao phải viết **() -> "Java"** thay vì **x -> "Java"**. Gợi ý: get() có 0 tham số.

**Bài 2.** Cho Optional.of("A") và một hàm expensive() có in log. Dự đoán số lần log khi chạy **orElse(expensive())** và **orElseGet(() -> expensive())**. Đáp án: dòng thứ nhất vẫn gọi expensive() một lần trước khi truyền vào orElse; dòng thứ hai không gọi Supplier vì Optional đã có giá trị.

**Bài 3.** Viết Supplier<Integer> dùng AtomicInteger để trả 1, rồi 2, rồi 3 ở ba lần gọi get(). Giải thích vì sao sự thay đổi nằm ở phần thân lambda chứ không phải do giao diện Supplier định nghĩa.

**Bài 4.** Với **Stream.generate(() -> "x").limit(4).collect(Collectors.toList())**, dự đoán danh sách khi chạy tuần tự. Đáp án: **[x, x, x, x]**. Giải thích tại sao chỉ khai báo Stream chưa tạo danh sách.

**Bài 5.** Muốn lần đầu tính một cấu hình, các lần sau dùng kết quả cũ và nhiều luồng có thể yêu cầu đồng thời, chỉ viết **Supplier<Config> config = () -> loadConfig();** đã đủ chưa? Đáp án: **chưa**; cần cơ chế khởi tạo/lưu nhớ có bảo vệ đúng cách, và cần xác định xử lý lỗi, làm mới và vòng đời.

**Bài 6.** Nếu một API nhận **Supplier<String> fallback**, điều gì bảo đảm fallback không được gọi khi dữ liệu chính đã có? Đáp án: **logic và hợp đồng của API nhận Supplier**. Bản thân Supplier không tự quyết định thời điểm được gọi.

## Ghi nhớ

**Supplier<T> là một giao diện hàm với phương thức T get() không có tham số.** Nó biểu diễn **cách cung cấp giá trị theo yêu cầu**, giúp bên sử dụng trì hoãn tạo giá trị tới lúc cần. Gọi get() thông thường không đồng nghĩa gọi một lần, không tự lưu nhớ, không tự chạy bất đồng bộ và không tự bảo đảm an toàn luồng.

Khi đọc một API nhận Supplier, hãy hỏi: **ai gọi get(), khi nào gọi, gọi bao nhiêu lần, có thể trả null hoặc ném lỗi gì, và kết quả có được lưu lại không?** Những câu hỏi này giúp lựa chọn đúng giữa truyền giá trị trực tiếp, Supplier tính theo nhu cầu và Supplier có cơ chế ghi nhớ.