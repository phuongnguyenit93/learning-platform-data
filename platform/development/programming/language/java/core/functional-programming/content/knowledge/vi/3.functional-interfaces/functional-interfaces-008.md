# Nhận diện Runnable, Callable và Comparator trong Java

## 1. Mục tiêu

**Runnable**, **Callable** và **Comparator** là ba functional interface quen thuộc của Java. Chúng đều có thể được triển khai bằng **lambda expression** hoặc **method reference** khi tương thích, nhưng giải quyết ba vấn đề rất khác nhau:

- **Runnable** mô tả một hành động không trả kết quả.
- **Callable<V>** mô tả một công việc trả giá trị kiểu **V**, đồng thời có thể khai báo checked exception.
- **Comparator<T>** mô tả quy tắc so sánh hai giá trị kiểu **T** để xác định thứ tự.

Sau bài này, bạn có thể đọc chữ ký phương thức trừu tượng duy nhất (**SAM — Single Abstract Method**) để nhận diện từng interface; chọn đúng loại theo mục đích; viết ví dụ Java 17 dùng lambda, method reference và ExecutorService; giải thích hợp đồng so sánh; tránh các lỗi về thứ tự, tác vụ bất đồng bộ và xử lý ngoại lệ.

## 2. Nhắc lại: vì sao ba interface này là functional interface?

Một **functional interface** có đúng một phương thức trừu tượng được tính theo quy tắc của Java. Giao diện có thể còn có phương thức **default**, **static**, **private** và những khai báo tương ứng với phương thức public của **Object** mà vẫn đáp ứng điều kiện functional interface.

**@FunctionalInterface** là annotation khuyến khích dùng để trình biên dịch kiểm tra hợp đồng “một SAM”, nhưng một interface hợp lệ vẫn là functional interface khi không viết annotation đó.

Ví dụ:

~~~java
@FunctionalInterface
interface Action {
    void execute();

    default void describe() {
        System.out.println("Action");
    }
}
~~~

**Action** có một SAM là **execute()**; phương thức **default** không trở thành SAM thứ hai. Vì vậy có thể tạo đối tượng bằng **Action action = () -> System.out.println("Done");**.

Lambda triển khai **phần thân của SAM**, còn kiểu của lambda được suy ra từ ngữ cảnh kiểu đích (**target typing**). Không có kiểu SAM phù hợp, một lambda đứng riêng không mang kiểu chức năng để khởi tạo biến thông thường.

## 3. Bảng nhận diện nhanh

| Interface | Package | Phương thức trừu tượng chính | Tham số | Kết quả | Checked exception |
| --- | --- | --- | --- | --- | --- |
| **Runnable** | **java.lang** | **void run()** | Không | Không trả giá trị | **run** không khai báo **throws** |
| **Callable<V>** | **java.util.concurrent** | **V call() throws Exception** | Không | Trả **V** | **call** được phép ném checked exception |
| **Comparator<T>** | **java.util** | **int compare(T a, T b)** | Hai giá trị **T** | Số âm, 0 hoặc số dương | **compare** không khai báo checked exception |

Quy tắc chọn nhanh:

1. Có **công việc để chạy**, không cần giá trị trả về: nghĩ đến **Runnable**.
2. Có **công việc để chạy**, cần **nhận kết quả** hoặc muốn khai báo checked exception: nghĩ đến **Callable<V>**.
3. Cần **định nghĩa thứ tự giữa hai đối tượng**, phục vụ sort, tập có thứ tự hoặc map có thứ tự: nghĩ đến **Comparator<T>**.

**Comparator** không đại diện cho một tác vụ chạy nền. Dù cũng là functional interface, nó trả lời câu hỏi “**a đứng trước, ngang hay sau b?**”, không phải “**chạy công việc gì?**”.

## 4. Runnable: một hành động không có giá trị trả về

### 4.1. Chữ ký và lambda

~~~java
@FunctionalInterface
public interface Runnable {
    void run();
}
~~~

Đây là bản rút gọn minh họa chữ ký SAM của **java.lang.Runnable**, không phải yêu cầu khai báo lại interface có sẵn.

Ví dụ sử dụng:

~~~java
Runnable printMessage = () -> System.out.println("Hello");
printMessage.run();
~~~

**Runnable** không nhận tham số ở **run()**, không trả giá trị và không khai báo checked exception. Lambda trên là một triển khai hợp lệ vì phần thân thực hiện hành động mà không trả về giá trị.

**Không nhận tham số** không đồng nghĩa với “không truy cập dữ liệu”. Lambda có thể capture biến cục bộ **final** hoặc **effectively final**, hoặc truy cập trạng thái đối tượng; những thứ ấy cần được cân nhắc khi chạy đa luồng.

### 4.2. Runnable tự nó không tạo thread mới

~~~java
Runnable job = () -> System.out.println(
        Thread.currentThread().getName());

job.run();                 // Gọi trực tiếp ở thread hiện tại.
new Thread(job).start();   // Lên lịch chạy ở thread mới.
~~~

**job.run()** chỉ là một lời gọi phương thức thông thường. **new Thread(job).start()** mới yêu cầu JVM tạo luồng thực thi để chạy logic **run**. Khi dùng executor, chính executor đảm nhiệm lịch chạy.

Không nên dùng ví dụ in tên thread để khẳng định một thứ tự output cố định, bởi lịch chạy các thread không có thứ tự được bảo đảm nếu thiếu phối hợp.

### 4.3. Checked exception trong Runnable

Vì **run()** không khai báo checked exception, phần thân lambda triển khai **Runnable** không thể để checked exception lan ra trực tiếp:

~~~java
// Không biên dịch nếu giữ nguyên lambda này:
// Runnable invalid = () -> Thread.sleep(100);
~~~

**Thread.sleep(...)** khai báo **InterruptedException**, nên cần bắt hoặc xử lý trong lambda:

~~~java
Runnable pause = () -> {
    try {
        Thread.sleep(100);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
    }
};
~~~

Đặt lại cờ interrupted thường là cách hợp lý khi không thể truyền checked exception ra chữ ký **run** và muốn mã ở tầng ngoài có cơ hội nhận biết yêu cầu dừng. Chiến lược xử lý ngắt cụ thể phụ thuộc vòng đời tác vụ.

**Runnable** vẫn có thể ném unchecked exception như **IllegalArgumentException** hoặc **RuntimeException**; “không khai báo checked exception” không có nghĩa mọi lỗi được hệ thống tự nuốt hoặc tự xử lý.

## 5. Callable<V>: tác vụ có kết quả

### 5.1. Chữ ký và kiểu generic

~~~java
@FunctionalInterface
public interface Callable<V> {
    V call() throws Exception;
}
~~~

Đây là bản rút gọn để minh họa chữ ký SAM của **java.util.concurrent.Callable**.

Ví dụ:

~~~java
Callable<Integer> calculate = () -> 6 * 7;
Integer answer = calculate.call(); // 42
~~~

Ở đây **call()** trả **Integer**. Vì khai báo phương thức có **throws Exception**, nơi gọi trực tiếp phải xử lý hoặc khai báo ngoại lệ thích hợp, kể cả khi lambda cụ thể chỉ tính toán đơn giản.

Có thể viết **Callable<String>**, **Callable<List<Order>>** hoặc **Callable<Report>** tùy kết quả. Khi công việc không có giá trị ý nghĩa nhưng vẫn muốn dùng **Callable<Void>**, lambda phải trả **null**, vì **Void** không có giá trị thông thường để tạo ra. Với nhiệm vụ đơn thuần không trả gì, **Runnable** thường diễn đạt ý định rõ hơn.

### 5.2. Callable không tự chạy bất đồng bộ

Tương tự Runnable, **calculate.call()** là lời gọi trực tiếp và chạy trên thread gọi nó. Muốn được lập lịch bởi executor, sử dụng **ExecutorService.submit(Callable<V>)** và nhận **Future<V>**.

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();
try {
    Callable<Integer> calculate = () -> 21 * 2;
    Future<Integer> future = executor.submit(calculate);
    Integer result = future.get(); // Chờ hoàn tất, rồi nhận 42.
} finally {
    executor.shutdown();
}
~~~

Đây là **đoạn minh họa** đặt trong phương thức có xử lý/khai báo checked exception và có import các lớp của **java.util.concurrent**, không phải chương trình độc lập. Chương trình chạy hoàn chỉnh sẽ xuất hiện ở phần 8.

**Future.get()** có thể chặn thread đang đợi cho đến khi tác vụ hoàn thành, hoặc kết thúc vì ngắt/hủy/thất bại. Nếu tác vụ ném ngoại lệ trong executor, **get()** thường báo **ExecutionException** và nguyên nhân gốc nằm ở **getCause()**. **get()** còn có thể ném **InterruptedException** khi thread đang đợi bị ngắt và **CancellationException** (unchecked) nếu future đã bị hủy.

**shutdown()** ngăn executor nhận nhiệm vụ mới và khởi động quá trình kết thúc sau các tác vụ đã được nhận; bản thân nó không bảo đảm đợi tất cả hoàn tất. Nếu cần chờ có thời hạn, dùng **awaitTermination(...)** hoặc chờ các **Future** phù hợp với hợp đồng ứng dụng.

### 5.3. Chọn Runnable hay Callable khi submit?

**ExecutorService** có cả overload nhận **Runnable** và **Callable**:

~~~java
Runnable save = () -> System.out.println("Saved");
Callable<Integer> count = () -> 3;

Future<?> saveFuture = executor.submit(save);
Future<Integer> countFuture = executor.submit(count);
~~~

Với **submit(Runnable)**, **Future.get()** sau khi thành công trả **null**, vì chính tác vụ không có kết quả. Với **submit(Callable<Integer>)**, **Future.get()** trả **Integer** do **call()** tạo ra. Có overload **submit(Runnable task, T result)** cho phép gắn một kết quả được cung cấp trước với Runnable khi hoàn tất; vì thế không nên suy luận mọi future xuất phát từ Runnable luôn trả null nếu sử dụng overload khác.

**execute(Runnable)** không trả Future; **submit(...)** trả Future. Chọn API dựa trên nhu cầu nhận biết kết thúc và xử lý thất bại, không chỉ vì cùng có thể chạy mã.

## 6. Comparator<T>: định nghĩa thứ tự giữa hai phần tử

### 6.1. Chữ ký và giá trị trả về

~~~java
@FunctionalInterface
public interface Comparator<T> {
    int compare(T a, T b);
    // Các default/static method và khai báo equals(Object) được lược bỏ.
}
~~~

Đây là mô tả rút gọn, không phải định nghĩa đầy đủ của JDK. **Comparator** vẫn là functional interface dù API có nhiều phương thức **default/static** và khai báo **equals(Object)**: phương thức tương ứng với **Object.equals** không làm tăng số SAM cần triển khai.

Ý nghĩa của **compare(a, b)**:

- Giá trị **âm**: **a** đứng trước **b**.
- Giá trị **0**: **a** và **b** được xem là tương đương theo thứ tự so sánh.
- Giá trị **dương**: **a** đứng sau **b**.

Không bắt buộc trả đúng -1, 0 hoặc 1. Phải quan tâm **dấu** của số, đồng thời duy trì các quy tắc nhất quán của comparator.

~~~java
Comparator<Integer> ascending = Integer::compare;

System.out.println(ascending.compare(2, 5) < 0); // true
System.out.println(ascending.compare(5, 5) == 0); // true
System.out.println(ascending.compare(7, 5) > 0); // true
~~~

Method reference **Integer::compare** tương thích với hai tham số **int** và trả **int**; khi dùng **Comparator<Integer>**, Java có thể unbox các **Integer** không null. Nếu tham số là null, cần chính sách riêng.

### 6.2. Không dùng phép trừ làm comparator một cách tùy tiện

~~~java
// Nguy hiểm khi phép trừ bị tràn int:
Comparator<Integer> broken = (a, b) -> a - b;

// Đúng hơn với int:
Comparator<Integer> safe = Integer::compare;
~~~

Ví dụ **a = Integer.MAX_VALUE**, **b = -1**, phép **a - b** tràn số và có thể trả giá trị âm, khiến thứ tự bị đảo sai. **Integer.compare** xử lý thứ tự nguyên theo ý nghĩa so sánh, không phụ thuộc kết quả phép trừ bị tràn.

Với **long**, dùng **Long.compare** hoặc **Comparator.comparingLong(...)** thay vì ép hiệu thành **int**. Với số thực, cần nắm chính sách so sánh **NaN**, **-0.0** và **+0.0** của **Double.compare** nếu dữ liệu có các trường hợp ấy.

### 6.3. Tạo comparator từ thuộc tính

~~~java
Comparator<String> byLength =
        Comparator.comparingInt(String::length);
Comparator<String> byLengthThenName =
        byLength.thenComparing(Comparator.naturalOrder());

List<String> sorted = List.of("Java", "Go", "Kotlin", "C")
        .stream()
        .sorted(byLengthThenName)
        .toList();
~~~

Kết quả **sorted = [C, Go, Java, Kotlin]**. Đầu tiên so theo độ dài, khi bằng nhau thì so theo thứ tự tự nhiên của **String**. **thenComparing** giúp tạo quy tắc phụ rõ ràng; **reversed()** đảo chiều thứ tự; **comparingInt**, **comparingLong** và **comparingDouble** tránh boxing ở phần lấy khóa so sánh nguyên thủy.

**Comparator.naturalOrder()** dùng thứ tự tự nhiên mà các giá trị **Comparable** cung cấp. Ví dụ **String** có thứ tự tự nhiên riêng, không phải thứ tự ngôn ngữ của mọi locale; nếu cần collation ngôn ngữ tự nhiên, cần một bộ so sánh phù hợp với locale và nghiệp vụ.

### 6.4. Hợp đồng Comparator: không chỉ là trả số

Một comparator đúng phải có các tính chất:

1. **Đối xứng về dấu**: **sign(compare(a,b)) = -sign(compare(b,a))**.
2. **Bắc cầu**: nếu **compare(a,b) > 0** và **compare(b,c) > 0**, thì **compare(a,c) > 0**.
3. **Nhất quán với các trường hợp bằng theo comparator**: nếu **compare(a,b) == 0**, dấu so sánh của **a** và **b** với một đối tượng **z** phải giống nhau theo hợp đồng.
4. Không phụ thuộc trạng thái thay đổi bất ngờ khi cấu trúc đang sử dụng comparator, chẳng hạn dữ liệu làm khóa sort đang bị sửa.

Một comparator dùng trong **TreeSet** hay **TreeMap** xác định **tương đương theo thứ tự** bằng **compare(a,b) == 0**. Điều này quan trọng vì hai phần tử khác nhau theo **equals** vẫn có thể bị coi là cùng một khóa theo comparator.

Ví dụ:

~~~java
Comparator<String> onlyLength =
        Comparator.comparingInt(String::length);
java.util.Set<String> words = new java.util.TreeSet<>(onlyLength);
words.add("Go");
words.add("Hi");
System.out.println(words.size()); // 1
~~~

**"Go"** và **"Hi"** đều dài 2 ký tự; comparator xem chúng tương đương. Với hệ thống cần giữ cả hai giá trị, hãy thêm tiêu chí phụ, chẳng hạn **thenComparing(Comparator.naturalOrder())**. Java không buộc mọi comparator phải nhất quán với **equals**, nhưng nếu không nhất quán thì các tập/map có thứ tự có thể gây bất ngờ so với hợp đồng tổng quát của **Set/Map**.

### 6.5. Xử lý null và thứ tự ổn định

~~~java
Comparator<String> nullSafe =
        Comparator.nullsLast(Comparator.naturalOrder());
~~~

**nullsFirst** hoặc **nullsLast** cho phép xác định cách xếp null khi dữ liệu cho phép null. Không nên mặc định các comparator nhận được null khi không có chính sách đó.

**List.sort(comparator)** sắp lại danh sách có thể sửa được, còn **stream().sorted(comparator).toList()** tạo danh sách kết quả từ stream và không sửa trực tiếp danh sách nguồn. Các nguồn mutable bị thay đổi đồng thời cần cơ chế quản lý riêng.

Đối với đầu vào **có encounter order**, thao tác **Stream.sorted()** là **stable**: phần tử được comparator đánh giá bằng nhau giữ thứ tự gặp ban đầu. Với stream **không có thứ tự**, không có bảo đảm stable tương ứng. Nếu hệ thống cần quy tắc phụ rõ ràng, hãy viết comparator có tiêu chí phụ thay vì phụ thuộc hoàn toàn vào tính ổn định.

## 7. So sánh lambda và method reference

Ba functional interface đều hỗ trợ lambda hoặc method reference khi chữ ký phù hợp:

~~~java
Runnable runnable1 = () -> System.out.println("Hello");
Runnable runnable2 = System.out::println;
// runnable2 vẫn cần đối số cho println? Xem giải thích dưới.
~~~

**Chú ý:** dòng **Runnable runnable2 = System.out::println** ở trên **không nên dùng làm ví dụ chuyển đổi mặc định**, vì **PrintStream.println** có nhiều overload; tùy ngữ cảnh compiler có thể chọn overload không tham số. Với API nhiều overload, hãy chọn lời gọi minh bạch **() -> System.out.println()** hoặc method reference tới phương thức tự định nghĩa có chữ ký rõ ràng. Ví dụ chuẩn, dễ đọc hơn:

~~~java
class Messenger {
    void notifyDone() {
        System.out.println("Done");
    }
}

Messenger messenger = new Messenger();
Runnable r = messenger::notifyDone;
Callable<String> c = () -> "Done";
Comparator<String> comparator = String::compareTo;
~~~

Đây là **đoạn minh họa** trong ngữ cảnh Java hợp lệ có các import tương ứng. **String::compareTo** là tham chiếu đến instance method với receiver từ tham số đầu, tương thích với **compare(String a, String b)**. Khi so sánh String có thể null, phương thức này không tự xử lý null.

**Nhận diện bằng chữ ký, không bằng cú pháp:** **() -> "OK"** phù hợp **Callable<String>** nhưng không phù hợp **Runnable** vì phải trả kết quả. **(a, b) -> Integer.compare(a, b)** phù hợp **Comparator<Integer>** vì nhận hai tham số và trả **int**. **() -> doWork()** có thể phù hợp **Runnable** khi kết quả gọi phương thức bị bỏ qua theo quy tắc statement expression; hãy dựa vào kiểu đích và việc compiler giải overload, không dựa riêng vào hình dạng dấu ngoặc.

## 8. Ví dụ Java 17 chạy độc lập: cả ba interface trong một chương trình

Ví dụ dùng **Runnable** để in thông báo, **Callable<Integer>** để tính kết quả, và **Comparator<String>** để sắp xếp danh sách theo độ dài rồi theo tên.

Tạo file **FunctionalInterfacesDemo.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FunctionalInterfacesDemo {
    public static void main(String[] args) throws Exception {
        Runnable announce =
                () -> System.out.println("Runnable: completed");

        Callable<Integer> calculate = () -> 6 * 7;

        Comparator<String> byLengthThenName =
                Comparator.comparingInt((String s) -> s.length())
                          .thenComparing(Comparator.naturalOrder());

        List<String> languages = List.of("Java", "Go", "Kotlin", "C");
        List<String> sorted = languages.stream()
                .sorted(byLengthThenName)
                .toList();

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<?> announcement = executor.submit(announce);
            Future<Integer> calculation = executor.submit(calculate);

            Object announcementResult = announcement.get();
            Integer value = calculation.get();

            System.out.println("Runnable result: " + announcementResult);
            System.out.println("Callable result: " + value);
            System.out.println("Sorted: " + sorted);
            System.out.println("Source: " + languages);
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac FunctionalInterfacesDemo.java
java FunctionalInterfacesDemo
~~~

Đầu ra:

~~~text
Runnable: completed
Runnable result: null
Callable result: 42
Sorted: [C, Go, Java, Kotlin]
Source: [Java, Go, Kotlin, C]
~~~

**Vì sao đầu ra có thứ tự như trên?**

- **Executors.newSingleThreadExecutor()** cung cấp executor có một worker thread xử lý các tác vụ đã gửi theo thứ tự nộp. **announcement.get()** trong main đợi **Runnable** hoàn thành trước khi main in kết quả của nó, nên dòng đầu tiên của Runnable xuất hiện trước **Runnable result: null**.
- **submit(Runnable)** tạo **Future<?>** mà **get()** trả null khi tác vụ thành công, vì không cung cấp giá trị kết quả.
- **submit(Callable<Integer>)** tạo **Future<Integer>**; phép tính trả 42 và main đọc giá trị qua **get()**. Công việc này chạy trên worker thread, còn các lệnh **System.out.println** sau **get()** chạy trên thread main.
- **byLengthThenName** sắp theo độ dài tăng dần; các chuỗi trong ví dụ có độ dài lần lượt: **C = 1**, **Go = 2**, **Java = 4**, **Kotlin = 6**. Danh sách nguồn **languages** không bị sửa vì sử dụng **stream().sorted(...).toList()**.
- **finally** gọi **shutdown()** để kết thúc vòng đời executor. Hai **Future.get()** đã hoàn thành thành công trước khi in, nên không có công việc đang chạy tiếp trong ví dụ thông thường.

Ở chương trình thực tế, khi thread main bị ngắt hoặc future thất bại, cần quản lý hủy tác vụ, dừng executor và phản hồi lỗi theo chính sách của ứng dụng. Ví dụ này chủ đích đơn giản để làm nổi bật ba chữ ký SAM.

## 9. Lỗi và ngoại lệ khác nhau ra sao?

### 9.1. Runnable không khai báo checked exception

~~~java
Runnable task = () -> {
    // Cần tự xử lý IOException nếu gọi API có throws IOException.
    System.out.println("Running");
};
~~~

Với một tác vụ do **ExecutorService.submit(Runnable)** chạy, unchecked exception phát sinh trong **run()** có thể được lưu vào Future; khi gọi **get()**, nó xuất hiện dưới dạng **ExecutionException**. Nếu chạy bằng **new Thread(task).start()** hoặc gọi **run()** trực tiếp, đường đi của ngoại lệ khác; không được mặc định mọi lỗi Runnable đều xuất hiện qua Future.

### 9.2. Callable cho phép checked exception

~~~java
Callable<String> task = () -> {
    if (true) {
        throw new java.io.IOException("Cannot read input");
    }
    // Nhánh return chỉ để ví dụ có kiểu trả về String.
};
~~~

Đoạn lambda này **không biên dịch** vì mọi đường đi đều ném exception và khối sau điều kiện hằng gây nhánh kiểm tra khó đọc; hãy dùng ví dụ hợp lệ rõ ràng sau:

~~~java
Callable<String> task = () -> {
    String value = System.getProperty("example.value");
    if (value == null) {
        throw new java.io.IOException("Missing example.value");
    }
    return value;
};
~~~

**Callable.call()** khai báo throws Exception, nên checked **IOException** trong lambda là hợp lệ. Khi thực thi bằng executor và gọi **Future.get()**, exception từ tác vụ được bọc trong **ExecutionException**. Phân biệt **exception do tác vụ gây ra** với **InterruptedException của thread đang chờ**.

**Thực hành tốt:** xử lý ngoại lệ đúng tầng sở hữu trách nhiệm, ghi đủ nguyên nhân cần thiết và tránh chuyển mọi exception thành null rồi để pipeline tiếp tục với dữ liệu thiếu.

## 10. Lỗi chọn nhầm interface và hiểu sai SAM

### 10.1. Trả giá trị trong Runnable

~~~java
// Sai: Runnable.run() phải trả void.
// Runnable wrong = () -> { return 42; };

Callable<Integer> correct = () -> 42;
~~~

**Runnable** dùng cho hành động; **Callable<Integer>** dùng khi giá trị 42 là kết quả của nhiệm vụ cần nhận lại.

### 10.2. Comparator thiếu tham số

~~~java
// Sai: Comparator.compare(a,b) cần hai tham số.
// Comparator<String> wrong = () -> 0;

Comparator<String> correct = (a, b) -> a.compareTo(b);
~~~

Không nên cố đưa tác vụ không nhận tham số vào Comparator chỉ vì cả hai có thể dùng lambda. Kiểu chức năng được xác định bởi chữ ký SAM.

### 10.3. Nhầm Callable với Supplier<T>

**Supplier<T>** cũng có SAM không tham số trả **T**, nhưng là **T get()** và không khai báo checked exception. **Callable<V>** có **V call() throws Exception**, gắn nhiều với API công việc và concurrency. Chọn theo hợp đồng và nơi tiêu thụ:

~~~java
java.util.function.Supplier<Integer> supplier = () -> 42;
Callable<Integer> callable = () -> 42;
~~~

Hai lambda có hình dạng tương tự nhưng hai biến thuộc hai interface khác nhau. Không được tự gán **Supplier<Integer>** vào biến **Callable<Integer>**; nếu muốn chuyển, có thể tạo adapter như **Callable<Integer> fromSupplier = supplier::get;**.

### 10.4. Nhầm Comparator với Comparable

**Comparable<T>** thuộc **java.lang**, yêu cầu **compareTo(T other)**: quy tắc tự nhiên do **chính lớp** cung cấp. **Comparator<T>** thuộc **java.util**, yêu cầu **compare(T a, T b)**: quy tắc so sánh **tách khỏi lớp** và có thể có nhiều biến thể (theo tuổi, tên, điểm, ngày tạo...).

Ví dụ **String** đã implements **Comparable<String>**, nhưng bạn vẫn có thể tạo **Comparator<String> byLength** để sắp theo độ dài. **Comparable** không phải interface cần nhận hai tham số như Comparator, và đây là lý do đọc chữ ký SAM trước khi chọn.

## 11. Quy tắc đọc code hiện có

Khi gặp một lambda, hãy nhìn vào **kiểu đích**:

~~~java
Runnable onClose = () -> releaseResources();
Callable<Boolean> check = () -> isReady();
Comparator<User> byAge = (left, right) ->
        Integer.compare(left.age(), right.age());
~~~

Các phương thức **releaseResources()**, **isReady()** và lớp **User** ở đây là tên minh họa, chưa phải chương trình độc lập. Có thể nhanh chóng suy luận:

- **onClose**: chạy hành động, không cần lấy một giá trị từ lời gọi **run()**.
- **check**: tác vụ trả **Boolean**; có thể được thực thi trực tiếp hoặc submit vào executor.
- **byAge**: nhận hai **User**, trả dấu so sánh dựa trên tuổi; dùng với sort hay cấu trúc có thứ tự.

Sau đó kiểm tra thêm: ai gọi lambda, chạy trên thread nào, có lấy Future không, có dữ liệu mutable bị capture không, có checked exception không, comparator có bắc cầu và ổn định không?

Một lambda không tự tạo concurrency, không tự bảo đảm tính thuần và không tự giải quyết lỗi. Những thuộc tính đó phụ thuộc cách interface được sử dụng và hợp đồng cụ thể của chương trình.

## 12. Bài tập tự luyện và đáp án

### Bài 1: Chọn interface

Ghép yêu cầu với interface phù hợp:

1. “Sau khi nhận sự kiện, in trạng thái và không cần giá trị trả về.”
2. “Thực hiện phép tính giá trị hóa đơn trong executor và lấy kết quả sau khi hoàn tất.”
3. “Sắp xếp nhân viên theo tên rồi theo mã nhân viên.”

**Đáp án:** (1) **Runnable**, (2) **Callable<BigDecimal>** hoặc kiểu kết quả nghiệp vụ phù hợp, (3) **Comparator<Employee>** với **thenComparing**. Nếu bài toán (1) cần thông báo thất bại, vẫn phải quyết định cơ chế quan sát exception hoặc Future tùy cách chạy.

### Bài 2: Đọc dấu so sánh

~~~java
Comparator<Integer> descending = (a, b) ->
        Integer.compare(b, a);
~~~

Hỏi: **descending.compare(10, 3)** trả số âm, 0 hay dương?

**Đáp án:** âm, vì **Integer.compare(3, 10) < 0**. Theo comparator giảm dần, 10 đứng trước 3. Đừng suy diễn “số lớn luôn làm compare dương”; dấu phụ thuộc chính **thứ tự mong muốn**.

### Bài 3: Sửa comparator dễ tràn

~~~java
Comparator<Integer> unsafe = (a, b) -> a - b;
~~~

**Đáp án đề xuất:**

~~~java
Comparator<Integer> ascending = Integer::compare;
Comparator<Integer> descending =
        (a, b) -> Integer.compare(b, a);
~~~

Kiểm thử với **Integer.MIN_VALUE**, **Integer.MAX_VALUE**, số âm, số dương, 0, giá trị trùng nhau. Cần cả ba tính chất hợp đồng comparator, không chỉ vài lần gọi thành công.

### Bài 4: Dự đoán kết quả executor

Với:

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();
try {
    Runnable r = () -> { };
    Callable<String> c = () -> "OK";
    System.out.println(executor.submit(r).get());
    System.out.println(executor.submit(c).get());
} finally {
    executor.shutdown();
}
~~~

Đây là đoạn code trong phương thức đã khai báo hoặc xử lý exception và có import tương ứng.

**Đáp án:** chương trình in:

~~~text
null
OK
~~~

**Future** trả null từ **submit(Runnable)** theo overload một đối số; **Callable<String>** trả **"OK"**. **get()** đợi hoàn thành, không phải cứ gọi **submit** thì có ngay giá trị trả về.

### Bài 5: Comparator kết hợp nhiều tiêu chí

Tạo comparator cho chuỗi: **độ dài tăng dần**, khi bằng độ dài thì **thứ tự tự nhiên giảm dần**.

**Gợi ý đáp án:**

~~~java
Comparator<String> comparator =
        Comparator.comparingInt(String::length)
                .thenComparing(Comparator.reverseOrder());
~~~

Đây là đoạn code minh họa đặt trong ngữ cảnh có import **Comparator**. Thử với **["bb", "aa", "c", "ddd"]**: kết quả là **[c, bb, aa, ddd]**. Nếu muốn cho null, thêm chính sách null rõ ràng, ví dụ bọc comparator bằng **Comparator.nullsLast(...)**.

## 13. Kiểm tra kiến thức khi review

Trước khi chấp nhận code dùng ba interface này, tự hỏi:

1. **Kiểu SAM có đúng không?** Runnable không kết quả, Callable có kết quả, Comparator nhận hai đối tượng và trả dấu so sánh.
2. **Tác vụ chạy ở đâu?** Lời gọi **run()** hoặc **call()** trực tiếp không khởi tạo thread mới; **Thread.start()** hoặc executor mới quyết định lập lịch.
3. **Ngoại lệ được xử lý thế nào?** **run()** không khai báo checked exception; **call()** có thể khai báo; **Future.get()** có thể chờ và bọc lỗi của tác vụ.
4. **Có nhận biết hoàn tất và dừng tài nguyên không?** Executor cần được quản lý vòng đời; không nên bỏ quên Future hoặc worker thread.
5. **Comparator có đúng hợp đồng không?** Tránh phép trừ có thể tràn, kiểm tra tính bắc cầu, tiêu chí phụ và null.
6. **Comparator có nhất quán với equals nếu đưa vào TreeSet/TreeMap không?** Giá trị **compare(a,b) == 0** quyết định phần tử tương đương theo thứ tự.
7. **Lambda có truy cập trạng thái mutable chia sẻ không?** Cần cân nhắc an toàn luồng, thời điểm chạy và thứ tự thực thi.

## 14. Ghi nhớ

**Runnable — void run() — hành động không trả kết quả. Callable<V> — V call() throws Exception — tác vụ trả giá trị và có thể khai báo checked exception. Comparator<T> — int compare(T,T) — quy tắc sắp xếp dựa trên dấu của kết quả.**

Điểm chung là đều có đúng một SAM nên sử dụng lambda/method reference được khi kiểu phù hợp. Điểm khác biệt quyết định lựa chọn là **mục đích của lời gọi**, **số tham số**, **kiểu trả về**, **hợp đồng ngoại lệ** và **cách thư viện tiêu thụ đối tượng ấy**. Đọc đúng những yếu tố này sẽ giúp bạn chọn interface chính xác, tránh nhầm concurrency với sorting và viết code Java dễ kiểm thử, bảo trì.
