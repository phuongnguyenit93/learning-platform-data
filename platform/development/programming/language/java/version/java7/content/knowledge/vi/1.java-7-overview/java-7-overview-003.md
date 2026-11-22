# Kiến thức cần có về generics, ngoại lệ, I/O và đa luồng

**Bối cảnh:** Java 7 và nền tảng vẫn được sử dụng trong Java hiện đại. Các ví dụ bên dưới chạy trên **JDK 17+**; những tính năng liên quan đến Java 7 được ghi rõ. Trọng tâm là hiểu đúng kiểu dữ liệu, kiểm soát lỗi, quản lý tài nguyên và phối hợp tác vụ an toàn, thay vì học những cách dùng đã lỗi thời.

## 1. Bốn nhóm kiến thức liên hệ với nhau như thế nào?

Trong một ứng dụng thực tế, một hàm có thể nhận **danh sách đường dẫn tệp** bằng generics, đọc dữ liệu từ tệp bằng I/O, xử lý ngoại lệ khi tệp không tồn tại hoặc thiếu quyền truy cập, rồi dùng executor để xử lý nhiều tệp song song. Mỗi nhóm kiến thức giải quyết một vấn đề khác nhau:

| Nhóm | Câu hỏi cốt lõi | Kết quả mong đợi |
| --- | --- | --- |
| **Generics** | Chương trình biết và kiểm tra kiểu dữ liệu từ lúc nào? | Hạn chế ép kiểu và lỗi kiểu dữ liệu tại runtime. |
| **Ngoại lệ** | Khi một thao tác thất bại, ai chịu trách nhiệm xử lý? | Lỗi được mô tả, chuyển tiếp hoặc phục hồi đúng chỗ. |
| **I/O** | Chương trình đọc/ghi byte và ký tự ở đâu, với encoding nào? | Dữ liệu chính xác, tài nguyên được đóng và lỗi I/O được quản lý. |
| **Đa luồng** | Nhiều tác vụ chạy đồng thời có nhìn thấy và sửa dữ liệu chung an toàn không? | Kết quả đúng bất kể thứ tự chạy, có chính sách hủy và giải phóng tài nguyên. |

**Các mốc Java 7 cần nhận diện:** toán tử diamond `<>` giúp suy luận tham số kiểu khi khởi tạo; **multi-catch** bắt nhiều loại ngoại lệ không có quan hệ kế thừa trong cùng một `catch`; **try-with-resources** tự đóng tài nguyên; **NIO.2** cung cấp `Path`, `Files` và các API hệ thống tệp. `ExecutorService`, `Future` và các lớp đồng bộ trong `java.util.concurrent` xuất hiện trước Java 7 nhưng vẫn là kiến thức cốt lõi. Lambda trong ví dụ đa luồng là cú pháp từ Java 8, được dùng rộng rãi với JDK hiện hành.

## 2. Generics: an toàn kiểu ở thời điểm biên dịch

### 2.1. Khai báo và lý do sử dụng

Generics cho phép lớp, interface và phương thức biểu diễn **kiểu dữ liệu như một tham số**. Ví dụ `List<String>` chỉ nhận các phần tử kiểu `String` theo kiểm tra biên dịch thông thường; trình biên dịch phát hiện lỗi khi cố thêm một `Integer`. Khi lấy phần tử ra, không cần ép kiểu thủ công. Cú pháp `new ArrayList<>()` dùng toán tử diamond, để trình biên dịch suy luận kiểu từ vế trái.

- **Kiểu tham số hóa:** `List<String>`, `Map<String, Integer>`, `Optional<User>`.
- **Lớp generic:** `class Box<T> { private T value; }`, trong đó `T` là tham số kiểu.
- **Phương thức generic:** `static <T> T first(List<T> items)`; `<T>` nằm trước kiểu trả về và chỉ có hiệu lực trong phương thức đó.
- **Giới hạn kiểu:** `<T extends Number>` chỉ chấp nhận `Number` hoặc lớp con, cho phép gọi các phương thức của `Number`.
- **Raw type:** bỏ tham số kiểu của một lớp generic sẽ làm mất phần lớn kiểm tra kiểu, nên khai báo tham số kiểu đầy đủ.

### 2.2. Bất biến và wildcard

`List<Integer>` **không phải** là một `List<Number>` dù `Integer extends Number`. Nếu cho phép gán trực tiếp, chương trình có thể thêm `Double` vào danh sách vốn chỉ chứa `Integer`. Quan hệ này gọi là **invariance**.

Wildcard mô tả quyền dùng dữ liệu:

- `? extends Number`: **đọc** các giá trị như `Number`; không được tự ý thêm một `Integer` hay `Double` vì kiểu phần tử cụ thể có thể khác. Đây là hướng *producer*.
- `? super Integer`: có thể **thêm** `Integer`; khi lấy ra chỉ chắc chắn là `Object`. Đây là hướng *consumer*.
- `<?>`: chấp nhận danh sách có kiểu phần tử chưa biết, hữu ích khi chỉ cần đếm, kiểm tra rỗng hoặc duyệt dưới dạng `Object`.

Quy tắc nhớ là **PECS**: *Producer Extends, Consumer Super*. Hãy dùng `List<T>` khi cần vừa đọc vừa ghi đúng một kiểu xác định.

### 2.3. Ví dụ chạy được

Lưu thành `GenericsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class GenericsDemo {
    static double sum(List<? extends Number> values) {
        double total = 0;
        for (Number value : values) {
            total += value.doubleValue();
        }
        return total;
    }

    static void addSamples(List<? super Integer> target) {
        target.add(10);
        target.add(20);
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>();
        addSamples(integers);

        System.out.println(integers);
        System.out.println(sum(integers));

        List<Number> numbers = new ArrayList<>();
        addSamples(numbers);
        System.out.println(numbers);
    }
}
```

Chạy:

```bash
javac GenericsDemo.java
java GenericsDemo
```

Kết quả chính xác:

```text
[10, 20]
30.0
[10, 20]
```

`sum` chấp nhận `List<Integer>` và cả `List<Double>` vì danh sách là nguồn cung cấp giá trị `Number`. `addSamples` chấp nhận `List<Integer>` hoặc `List<Number>` vì danh sách là nơi tiếp nhận `Integer`.

### 2.4. Giới hạn quan trọng của generics

Java dùng **type erasure**: phần lớn tham số kiểu không còn được biểu diễn như kiểu cụ thể tại runtime. Vì vậy, không thể kiểm tra `instanceof List<String>`, không thể trực tiếp `new T()` hoặc tạo mảng `new List<String>[10]`. Có thể dùng `instanceof List<?>` để kiểm tra hình dạng generic chưa biết; khi cần tạo đối tượng theo kiểu động, nên truyền constructor/factory hoặc `Class<T>` một cách tường minh.

Type erasure không làm generics trở nên vô ích: lợi ích chính là kiểm tra tại **compile time**. Khi đọc JSON, dữ liệu qua reflection hoặc API không bảo đảm kiểu, vẫn cần kiểm chứng kiểu và cấu trúc dữ liệu ở ranh giới ngoài. Tránh ép kiểu không kiểm soát và tránh trả về một `Object` khi hợp đồng API có thể diễn đạt bằng generics.

## 3. Ngoại lệ: mô tả và xử lý thất bại có chủ đích

### 3.1. Checked, unchecked và Error

- **Checked exception:** ngoại lệ thuộc `Exception` nhưng không thuộc `RuntimeException`, ví dụ `IOException`. Phương thức phải bắt hoặc khai báo `throws`; điều này báo cho bên gọi biết có một tình huống thất bại cần cân nhắc.
- **Unchecked exception:** `RuntimeException` và các lớp con, như `IllegalArgumentException`, `NumberFormatException`, `IllegalStateException`. Thường biểu thị đầu vào sai hợp đồng hoặc trạng thái không hợp lệ; trình biên dịch không bắt buộc khai báo.
- **`Error`:** nhóm sự cố nghiêm trọng của JVM hoặc môi trường; mã ứng dụng thông thường không dùng `catch (Error)` để tiếp tục như không có gì xảy ra.

**Không nên phân loại chỉ bằng “có thể phục hồi hay không”:** checked và unchecked là một phần của thiết kế API, còn khả năng phục hồi phụ thuộc ngữ cảnh. Ví dụ `IOException` có thể được báo lên tầng giao diện, thử lại với điều kiện phù hợp hoặc kết thúc thao tác; không phải mọi lỗi I/O đều nên thử lại.

### 3.2. `try`, `catch`, `finally`, `throws` và try-with-resources

- `throw new IllegalArgumentException("...")` chủ động ném một ngoại lệ; `throws IOException` khai báo checked exception có thể đi tới caller.
- `catch` nên xử lý một lỗi **mà tầng hiện tại hiểu rõ**: báo thông tin có ích, dùng phương án dự phòng an toàn hoặc chuyển tiếp với ngữ cảnh. Không nên bắt `Exception` rộng để in log rồi trả về kết quả giả thành công.
- `finally` phục vụ thao tác dọn dẹp cần chạy khi rời khối `try`. Với tài nguyên triển khai `AutoCloseable`, ưu tiên **try-with-resources** vì nó tự gọi `close()` cả lúc có ngoại lệ.
- Khi phần thân `try` và lúc đóng tài nguyên đều ném ngoại lệ, ngoại lệ đóng thường được giữ trong `getSuppressed()` của ngoại lệ chính. Điều này giúp không đánh mất nguyên nhân ban đầu.
- **Multi-catch:** `catch (IOException | SecurityException ex)` phù hợp khi cách xử lý là giống nhau. Không ghép hai ngoại lệ có quan hệ cha–con trong cùng multi-catch.

Ví dụ một hàm đọc dòng đầu, chuyển trách nhiệm xử lý checked exception cho caller:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FirstLineReader {
    static String firstLine(Path path) throws IOException {
        try (BufferedReader reader =
                     Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            return reader.readLine();
        }
    }
}
```

Đây là **một lớp minh họa API**, chưa có `main` để chạy độc lập. Nếu tệp rỗng, `readLine()` trả về `null`; caller cần định nghĩa hành vi tương ứng. Nếu không mở/đọc được, `IOException` được chuyển tiếp, còn reader được đóng tự động.

### 3.3. Ví dụ đầy đủ về kiểm tra hợp đồng đầu vào

Lưu `ExceptionDemo.java`:

```java
public class ExceptionDemo {
    static int parsePositive(String text) {
        int value = Integer.parseInt(text);
        if (value <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }
        return value;
    }

    public static void main(String[] args) {
        try {
            System.out.println(parsePositive("-5"));
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

```bash
javac ExceptionDemo.java
java ExceptionDemo
```

```text
value must be positive
```

`NumberFormatException` cũng là một `IllegalArgumentException`, nên `catch` ở đây bao phủ cả chuỗi không phải số. Trong chương trình thực tế, hãy phân biệt thông báo “không phải số” và “không dương” nếu giao diện cần phản hồi cụ thể. Khi bọc ngoại lệ để bổ sung ngữ cảnh, truyền nguyên nhân vào constructor, chẳng hạn `new IllegalStateException("Cannot load config", cause)`, để giữ stack trace nguồn.

**Đặc biệt với đa luồng:** khi bắt `InterruptedException` mà không ném tiếp, thường phải gọi `Thread.currentThread().interrupt()` rồi kết thúc hoặc trả quyền điều khiển cho caller; nuốt tín hiệu ngắt có thể khiến hủy tác vụ không hoạt động đúng.

## 4. I/O: đọc ghi dữ liệu và đóng tài nguyên

### 4.1. Byte, ký tự và encoding

- **Byte stream** như `InputStream`/`OutputStream` phù hợp dữ liệu nhị phân (ảnh, ZIP, giao thức byte). Không diễn giải byte thành ký tự nếu chưa biết encoding.
- **Character stream** như `Reader`/`Writer` dùng cho văn bản. Một ký tự có thể chiếm nhiều byte; chọn encoding rõ ràng, ưu tiên `StandardCharsets.UTF_8` cho dữ liệu trao đổi.
- **Buffered I/O** gom thao tác nhỏ để giảm lần gọi hệ điều hành. `BufferedReader` còn có `readLine()`; đọc từng dòng thích hợp cho tệp văn bản lớn.
- **`Path`** biểu diễn đường dẫn; **`Files`** cung cấp thao tác tạo, đọc, ghi, sao chép, di chuyển, xóa và kiểm tra metadata. Đây là API NIO.2 từ Java 7 vẫn hữu ích hiện nay.

Không nhầm `String.length()` với số byte UTF-8. Khi giao tiếp hệ thống bên ngoài, encoding là một phần của hợp đồng. Với đầu vào không đáng tin cậy, cần kiểm tra đường dẫn được phép truy cập, kích thước dữ liệu và khả năng thiếu quyền/tệp biến mất giữa lúc kiểm tra và sử dụng.

### 4.2. Chọn cách đọc phù hợp kích thước dữ liệu

| Trường hợp | API phù hợp | Lưu ý |
| --- | --- | --- |
| Tệp văn bản nhỏ, có thể đưa vào RAM | `Files.readString(path, UTF_8)` (Java 11+) | Đơn giản nhưng đọc toàn bộ nội dung vào bộ nhớ. |
| Tệp văn bản lớn hoặc cần xử lý từng dòng | `Files.newBufferedReader(path, UTF_8)` | Đọc dần; đóng reader bằng try-with-resources. |
| Muốn kết hợp thao tác Stream trên từng dòng | `Files.lines(path, UTF_8)` (Java 8+) | Stream này giữ tài nguyên I/O; đặt trong try-with-resources. |
| Tệp nhị phân | `Files.newInputStream(path)`, `Files.newOutputStream(path)` | Xử lý byte, nên có buffer hợp lý và đóng stream. |
| Sao chép/di chuyển | `Files.copy`, `Files.move` với `StandardCopyOption` thích hợp | Xác định chính sách ghi đè và lỗi khi đích đã tồn tại. |

`Files.exists(path)` chỉ cho biết trạng thái tại thời điểm kiểm tra; một tiến trình khác vẫn có thể sửa/xóa tệp ngay sau đó. Hãy xử lý ngoại lệ của **thao tác thực** thay vì coi kiểm tra trước là bảo đảm tuyệt đối.

### 4.3. Ví dụ I/O có tạo, đọc và dọn tệp tạm

Lưu `IoDemo.java`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class IoDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("io-demo-");
        Path file = directory.resolve("data.txt");

        try {
            Files.write(
                file,
                Arrays.asList("alpha", "beta"),
                StandardCharsets.UTF_8
            );

            try (BufferedReader reader =
                         Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                String line;
                while ((line = reader.readLine()) != null) {
                    System.out.println(line);
                }
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
```

```bash
javac IoDemo.java
java IoDemo
```

```text
alpha
beta
```

Đoạn mã dùng `Path`/`Files`, chỉ định UTF-8, đóng reader tự động và xóa dữ liệu tạm trong `finally`. Nếu thao tác dọn dẹp cũng thất bại, ngoại lệ dọn dẹp có thể thay thế ngoại lệ trước đó trong ví dụ tối giản này; hệ thống thực tế cần chính sách dọn dẹp và ghi nhận lỗi rõ ràng. Với dữ liệu lớn, tránh `readAllBytes`/`readString` không giới hạn; xử lý theo luồng và giới hạn khối lượng đầu vào.

## 5. Đa luồng: phối hợp công việc và bảo vệ trạng thái chung

### 5.1. Thread, executor, Future

**Concurrency** là tổ chức nhiều tác vụ có thời gian thực hiện chồng lấn; **parallelism** là thực thi thực sự đồng thời trên nhiều lõi. Thứ tự hoàn thành không bảo đảm giống thứ tự khởi chạy. Tác vụ **CPU-bound** chịu giới hạn lõi CPU; tác vụ **I/O-bound** thường chờ mạng/đĩa nên có đặc điểm điều phối khác.

Không cần tự tạo một `Thread` cho từng công việc. `ExecutorService` nhận các `Runnable`/`Callable<T>` và quản lý worker. `submit(Callable<T>)` trả về `Future<T>`; `get()` chờ kết quả, có thể ném `InterruptedException` hoặc `ExecutionException` (nguyên nhân từ tác vụ nằm trong `getCause()`). Khi có thời hạn, dùng `get(timeout, unit)` và chính sách hủy `cancel(true)` thích hợp.

**Executor phải có vòng đời rõ ràng:** ngừng nhận việc bằng `shutdown()`, chờ tối đa khi cần bằng `awaitTermination`, cân nhắc `shutdownNow()` khi quá hạn. `shutdownNow()` chỉ yêu cầu ngắt các tác vụ đang chạy; không thể bảo đảm tác vụ bỏ dở nếu nó không hợp tác với ngắt.

### 5.2. Race condition, visibility và các công cụ đồng bộ

Giả sử hai thread cùng chạy `counter++`. Phép tăng gồm nhiều bước đọc–tính–ghi, nên có thể mất cập nhật (**race condition**). Một kết quả “đúng” ở vài lần thử không chứng minh chương trình an toàn.

- `synchronized` bảo vệ **critical section** và cung cấp quan hệ *happens-before* khi unlock/lock cùng monitor. Dùng khi một nhóm thao tác phải nhất quán cùng nhau.
- `volatile` giúp các thread quan sát thay đổi của một biến theo ngữ nghĩa Java Memory Model; **không** biến `counter++` thành phép tăng nguyên tử.
- `AtomicInteger`, `AtomicLong` hỗ trợ các thao tác nguyên tử riêng lẻ như `incrementAndGet()`; với quy tắc nhiều biến, có thể vẫn cần khóa hoặc thiết kế immutable.
- `ConcurrentHashMap` và các cấu trúc trong `java.util.concurrent` phù hợp truy cập đồng thời theo hợp đồng của từng cấu trúc. Một chuỗi thao tác “kiểm tra rồi cập nhật” vẫn cần API nguyên tử như `compute` hoặc cơ chế đồng bộ phù hợp.
- **Immutability** và hạn chế chia sẻ trạng thái thay đổi là cách giảm lỗi đa luồng rất hiệu quả. Không dựa vào `Thread.sleep` để “đợi” sự kiện hoặc sắp thứ tự cập nhật.

Các lỗi cần nhận diện: **race condition** (kết quả phụ thuộc lịch chạy), **deadlock** (các thread chờ nhau), **starvation** (một tác vụ không được cấp cơ hội), rò rỉ thread/executor và tác vụ bị chặn không có timeout. Khi sử dụng nhiều khóa, cần một thứ tự lấy khóa thống nhất để giảm nguy cơ deadlock.

### 5.3. Ví dụ chạy được: một bộ đếm an toàn với 100 tác vụ

Lưu `ConcurrentDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        ExecutorService pool = Executors.newFixedThreadPool(4);
        AtomicInteger counter = new AtomicInteger();

        try {
            List<Future<?>> jobs = new ArrayList<>();
            for (int i = 0; i < 100; i++) {
                jobs.add(pool.submit(() -> {
                    counter.incrementAndGet();
                }));
            }

            for (Future<?> job : jobs) {
                job.get();
            }
            System.out.println(counter.get());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ConcurrentDemo.java
java ConcurrentDemo
```

```text
100
```

Kết quả là **100** dù thứ tự chạy của các tác vụ thay đổi: `AtomicInteger` chống mất cập nhật và vòng lặp `Future.get()` đợi từng tác vụ hoàn tất trước khi in. `shutdown()` bảo đảm executor không nhận tác vụ mới. Ví dụ cho phép `main` chuyển tiếp ngoại lệ để tập trung minh họa; mã ứng dụng cần xử lý ngắt, nguyên nhân thất bại của task, timeout và shutdown theo yêu cầu dịch vụ.

**Cập nhật Java hiện đại:** Java 21+ có **virtual threads**, hữu ích cho rất nhiều tác vụ blocking I/O khi thư viện tương thích. Chúng không làm tính toán CPU-bound tự động nhanh hơn, không loại bỏ race condition và không thay thế việc quản lý tài nguyên. Khi học riêng Java 7, hiểu `ExecutorService`, `Future` và đồng bộ cơ bản trước là đủ để đi tiếp.

## 6. Kết hợp bốn chủ đề trong cùng một bài toán

Xét yêu cầu: nhận một `List<Path>`, đếm số dòng của từng tệp và trả kết quả cho người gọi.

1. **Generics:** kiểu đầu vào `List<Path>` bảo đảm danh sách biểu diễn đường dẫn; có thể trả `Map<Path, Long>` nếu cần ghép đường dẫn với số dòng.
2. **I/O:** mở từng tệp dưới dạng `Files.lines(path, UTF_8)` trong try-with-resources, sau đó `count()`; luôn đóng Stream giữ tài nguyên.
3. **Ngoại lệ:** `IOException` của từng tệp phải có chính sách rõ ràng: thất bại cả lần xử lý, báo lỗi theo từng tệp hoặc thử lại có giới hạn. Không âm thầm trả về số dòng bằng 0 vì như vậy dễ biến lỗi thành dữ liệu hợp lệ.
4. **Đa luồng:** nếu có nhiều tệp độc lập, tạo các `Callable<Long>` và nộp cho executor với số worker hợp lý. Mỗi tác vụ dùng tài nguyên I/O riêng, thu kết quả qua `Future<Long>`; caller xử lý `ExecutionException`, ngắt và timeout trước khi kết hợp kết quả.

Cách phân chia trách nhiệm này giúp dễ kiểm thử: kiểm tra kiểu và hợp đồng đầu vào, kiểm tra tài nguyên được đóng, giả lập lỗi đọc tệp và chạy lặp nhiều lần để phát hiện vấn đề đồng bộ. Việc xử lý song song chỉ nên áp dụng sau khi phiên bản tuần tự đã đúng; số lượng worker tối ưu phụ thuộc loại ổ đĩa, tải hệ thống và đặc tính dữ liệu chứ không phải cứ nhiều thread là nhanh.

## 7. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hiểu đúng |
| --- | --- |
| `List<Integer>` có thể gán cho `List<Number>`. | Generics bất biến; dùng wildcard khi cần quan hệ đọc/ghi linh hoạt. |
| Generics bảo đảm luôn biết `T` cụ thể ở runtime. | Java chủ yếu dùng type erasure; có giới hạn với kiểm tra kiểu/khởi tạo động. |
| Bắt mọi `Exception` là an toàn nhất. | Chỉ bắt lỗi tầng hiện tại xử lý được; chuyển tiếp lỗi không thể xử lý cùng ngữ cảnh. |
| `finally` luôn đủ để đóng stream đúng cách. | Try-with-resources diễn đạt sở hữu tài nguyên trực tiếp và xử lý suppressed exception tốt hơn. |
| Dữ liệu văn bản luôn là “một ký tự bằng một byte”. | Encoding quyết định byte; dùng UTF-8 rõ ràng ở ranh giới dữ liệu. |
| `Files.exists` bảo đảm lần đọc tiếp theo sẽ thành công. | Hệ thống tệp có thể thay đổi; vẫn phải bắt/đẩy `IOException` của thao tác đọc. |
| `volatile int count` làm `count++` an toàn. | Visibility khác atomicity; dùng `AtomicInteger` hoặc khóa cho phép tăng. |
| Gọi `submit` xong là tác vụ đã hoàn tất. | Cần nhận/đợi `Future` hoặc cơ chế phối hợp phù hợp. |
| `shutdown()` hủy ngay các tác vụ đang chạy. | Nó dừng tiếp nhận việc mới; tác vụ đã nhận có thể tiếp tục tới khi xong. |
| Chạy đúng một lần chứng minh code thread-safe. | Lỗi đồng thời phụ thuộc lịch chạy; cần thiết kế đúng và kiểm thử áp lực có mục tiêu. |

## 8. Thực hành kiểm chứng năng lực

**Bài 1 — Generics:** viết `sum(List<? extends Number>)` nhận cả danh sách `Integer` lẫn `Double`. Giải thích vì sao không thể tùy tiện thêm `Integer` vào tham số wildcard này, rồi viết `addDefaults(List<? super Integer>)` để thấy sự khác biệt giữa producer và consumer.

**Bài 2 — Ngoại lệ và I/O:** đọc một tệp UTF-8 từng dòng bằng `BufferedReader` và try-with-resources. Kiểm tra ba tình huống: tệp có dữ liệu, tệp rỗng, đường dẫn không tồn tại. Với từng tình huống, chỉ rõ giá trị trả về, loại lỗi có thể phát sinh và tầng nào quyết định hiển thị thông báo.

**Bài 3 — Đa luồng:** nộp 1.000 tác vụ tăng bộ đếm thông qua `ExecutorService`. Dùng `AtomicInteger`, đợi các `Future` hoàn tất rồi kiểm tra kết quả 1.000. Giải thích vì sao thay bằng một biến `int` dùng `++` có thể không cho kết quả chính xác và vì sao chỉ thêm `volatile` chưa giải quyết lỗi.

**Bài 4 — Tích hợp:** nhận danh sách đường dẫn qua `List<Path>`, đếm số dòng theo từng tệp và tổng hợp thành `Map<Path, Long>`. Bắt đầu từ xử lý tuần tự, sau đó dùng `Callable<Long>`/`Future<Long>` để chạy đồng thời. Giữ nguyên chính sách báo lỗi giữa hai phiên bản, đóng toàn bộ tài nguyên, kiểm tra kết quả bằng tệp nhỏ đã biết số dòng và giới hạn thời gian chờ khi cần.

Sau phần này, người học nên **giải thích được hợp đồng kiểu của API**, nhận diện được **checked/unchecked exception**, chọn cách đọc/ghi phù hợp kích thước tệp, quản lý tài nguyên bằng try-with-resources, và biết khi nào phải dùng **đồng bộ hoặc dữ liệu bất biến** để kết quả không phụ thuộc lịch chạy. Đây là nền tảng còn giá trị trên Java hiện đại, đồng thời nối trực tiếp các tính năng hữu ích được hoàn thiện trong Java 7.