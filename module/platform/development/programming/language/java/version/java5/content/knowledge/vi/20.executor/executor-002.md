# Phân biệt Runnable và Callable

## 1. Hai cách mô tả công việc cần thực hiện

Trong chương Executor, cần tách hai câu hỏi: **công việc làm gì** và **ai tổ chức cho công việc chạy**.

- `Runnable` và `Callable<V>` mô tả một tác vụ.
- `Executor` nhận tác vụ theo hợp đồng của nó và tổ chức thực thi; `ExecutorService` bổ sung quản lý vòng đời và các cách gửi tác vụ có theo dõi.
- `Future<V>` là đối tượng để chờ, nhận kết quả hoặc quan sát việc hủy của tác vụ đã gửi.

Ví dụ, cập nhật bộ nhớ đệm là một hành động không nhất thiết có giá trị trả về; tính tổng tiền đơn hàng cần trả một con số. Sự khác biệt này giúp chọn `Runnable` hoặc `Callable` theo hợp đồng mà nơi gọi cần, trước khi quyết định dùng bao nhiêu luồng.

Cả hai vẫn là API đang được sử dụng trong Java hiện hành. Các ví dụ dưới đây chạy trên Java 17 trở lên; không yêu cầu framework hoặc thư viện ngoài.

## 2. Khác biệt nằm trong chữ ký phương thức

Các chữ ký cốt lõi, lược bỏ phần tài liệu API:

```java
@FunctionalInterface
public interface Runnable {
    void run();
}

@FunctionalInterface
public interface Callable<V> {
    V call() throws Exception;
}
```

Đây là phần trích chữ ký để so sánh, không phải mã cần chép vào chương trình: dùng `java.lang.Runnable` và `java.util.concurrent.Callable` có sẵn.

| Tiêu chí | Runnable | Callable<V> |
|---|---|---|
| Phương thức của tác vụ | `void run()` | `V call() throws Exception` |
| Giá trị trả về trực tiếp | Không có | Có, kiểu `V` |
| Ngoại lệ được kiểm tra lúc biên dịch (checked exception) | Không được truyền ra ngoài `run()` | Được khai báo truyền ra ngoài `call()` |
| Ngoại lệ không được kiểm tra (unchecked exception) | Có thể ném | Có thể ném |
| Gọi qua `Executor.execute(...)` | Được | Không nhận trực tiếp |
| Gửi qua `ExecutorService.submit(...)` | Được | Được |

`V` là tham số kiểu, chẳng hạn `Callable<Integer>`, `Callable<String>` hoặc `Callable<Order>`. Không dùng `Callable<int>` vì generic không nhận kiểu nguyên thủy; dùng `Integer`.

Hai chữ ký và khả năng dùng lambda được mô tả trong [Runnable API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runnable.html) và [Callable API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Callable.html).

### Không trả về giá trị khác với không tạo ra tác động

`Runnable` vẫn có thể ghi tệp, gửi thông báo hoặc thay đổi một đối tượng. `void` chỉ nói rằng người gọi không nhận giá trị qua kết quả của `run()`; nó không bảo đảm tác vụ không thay đổi dữ liệu.

Ngược lại, `Callable` cũng có thể tạo tác động phụ. Việc trả `Integer` không làm tác vụ tự động an toàn khi nhiều luồng cùng truy cập dữ liệu.

Để nhận kết quả tính toán, nên dùng giá trị trả về rõ ràng thay vì tạo biến dùng chung chỉ nhằm lấy kết quả từ `Runnable`.

## 3. Khai báo tác vụ không đồng nghĩa với chạy trên luồng khác

Đoạn mã minh họa:

```java
Runnable announce = () -> System.out.println("Hello");
Callable<Integer> calculate = () -> 20 + 22;
```

Lúc này chỉ mới tạo hai đối tượng tác vụ. Chưa có lời gọi thực thi nào.

Nếu gọi trực tiếp:

```java
announce.run();
int answer = calculate.call();
```

cả hai phương thức chạy như lời gọi phương thức bình thường trên **luồng đang gọi**. Vì `Callable.call()` khai báo `throws Exception`, nơi gọi trực tiếp phải bắt hoặc khai báo ngoại lệ thích hợp, kể cả khi thân lambda cụ thể không ném ngoại lệ.

Muốn tách việc tổ chức thực thi khỏi nơi tạo công việc, gửi tác vụ cho executor. Không nên suy luận “dùng Runnable thì chạy luồng phụ”: bản thân giao diện không tạo luồng, và hợp đồng `Executor` không buộc mọi triển khai đều chạy trên một luồng riêng.

`Thread` nhận `Runnable`, không nhận trực tiếp `Callable`. Với bài toán cần kết quả, `ExecutorService.submit(callable)` thường thể hiện ý định rõ hơn việc tự tạo và quản lý luồng.

## 4. Ba overload submit cần phân biệt

Với biến `pool` có kiểu `ExecutorService`:

```java
Runnable action = () -> { /* thực hiện hành động */ };

Future<?> first = pool.submit(action);
Future<String> second = pool.submit(action, "finished");

Callable<Integer> calculation = () -> 42;
Future<Integer> third = pool.submit(calculation);
```

Đây là đoạn minh họa API, chưa phải chương trình độc lập.

Nếu tác vụ hoàn tất thành công:

1. `first.get()` trả `null`. Tuy vậy, `Future<?>` vẫn hữu ích để chờ hoặc phát hiện tác vụ thất bại.
2. `second.get()` trả giá trị `"finished"` đã cung cấp khi gửi. `Runnable.run()` vẫn là `void`; giá trị này không phải kết quả do nó tính ra.
3. `third.get()` trả kết quả do `Callable.call()` trả về.

Giá trị `"finished"` không được trả nếu tác vụ thất bại. `submit` trả `Future` để đại diện cho tác vụ, không đợi hoàn tất rồi trả ngay giá trị nghiệp vụ.

Các overload được quy định trong [ExecutorService API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html).

### execute không trả Future

`pool.execute(runnable)` có kiểu trả về `void`; không có `Future` đi kèm để gọi `get()`.

Không nên hiểu `execute` là “không có lỗi”. Tác vụ vẫn có thể thất bại; cách quan sát lỗi phụ thuộc triển khai và cơ chế xử lý ngoại lệ của môi trường thực thi. Khi cần theo dõi hoàn tất hoặc nhận lỗi qua một đối tượng kết quả, dùng `submit` và thực sự kiểm tra `Future`.

## 5. Ngoại lệ: hợp đồng tác vụ và nơi nhận lỗi

### Runnable không cho checked exception thoát trực tiếp khỏi run

Đoạn sau cố ý **không biên dịch**, vì `Files.readString(...)` có thể ném `IOException`:

```java
Runnable task = () -> {
    String text = java.nio.file.Files.readString(
            java.nio.file.Path.of("input.txt"));
    System.out.println(text);
};
```

Nếu vẫn chọn `Runnable`, phải xử lý ngoại lệ bên trong lambda hoặc chuyển thành ngoại lệ không được kiểm tra có ý nghĩa. Không nên bắt rồi bỏ qua lỗi để làm mã biên dịch.

Nếu mục đích là đọc tệp và trả nội dung cho nơi gọi, `Callable<String>` phù hợp tự nhiên hơn:

```java
Callable<String> task = () -> java.nio.file.Files.readString(
        java.nio.file.Path.of("input.txt"));
```

Đoạn này minh họa việc khai báo tác vụ; kết quả thực tế phụ thuộc tệp. Khi executor thực thi, `IOException` có thể thoát khỏi `call()`.

### Future.get là ranh giới quan sát kết quả

Trong cách dùng `submit` với executor tiêu chuẩn, lỗi do thân tác vụ ném ra được giữ trong kết quả tác vụ. Khi lấy kết quả bằng `get()`:

- Thành công: nhận giá trị của tác vụ, hoặc `null` với `submit(Runnable)`.
- Tác vụ thất bại: nhận `ExecutionException`; dùng `getCause()` để xem nguyên nhân.
- Luồng đang chờ bị ngắt: nhận `InterruptedException`.
- Tác vụ đã bị hủy: nhận `CancellationException`.

`Runnable` cũng có thể thất bại bằng `RuntimeException`; khi gửi bằng `submit`, vẫn có thể quan sát lỗi ấy qua `Future.get()`. Vì vậy, không được kết luận “chỉ Callable mới báo lỗi”.

Cần phân biệt lỗi **khi gửi tác vụ** như `RejectedExecutionException` với lỗi **trong thân tác vụ** được quan sát sau đó. Chẳng hạn executor đã đóng có thể từ chối ngay tại `submit`.

Nếu bắt `InterruptedException` ở nơi không thể truyền tiếp, thông thường cần phục hồi cờ ngắt bằng `Thread.currentThread().interrupt()` và dừng hoặc chuyển hướng xử lý phù hợp. Không coi ngắt là một lỗi nghiệp vụ thông thường rồi tiếp tục chờ vô hạn.

## 6. Chương trình hoàn chỉnh: hành động, kết quả và thất bại

Lưu thành **`RunnableCallableDemo.java`**:

```java
import java.io.IOException;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class RunnableCallableDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Runnable action = () -> {
                // Hanh dong nay khong tra gia tri.
            };
            Callable<Integer> calculation = () -> 6 * 7;
            Callable<String> failing = () -> {
                throw new IOException("read failed");
            };

            Future<?> actionFuture = pool.submit(action);
            Future<Integer> resultFuture = pool.submit(calculation);
            Future<String> failedFuture = pool.submit(failing);

            System.out.println("Runnable result: " + actionFuture.get());
            System.out.println("Callable result: " + resultFuture.get());

            try {
                failedFuture.get();
            } catch (ExecutionException e) {
                Throwable cause = e.getCause();
                System.out.println(
                        "Task failure: " + cause.getClass().getSimpleName()
                        + ": " + cause.getMessage());
            }
        } finally {
            pool.shutdown();
            try {
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                }
            } catch (InterruptedException e) {
                pool.shutdownNow();
                Thread.currentThread().interrupt();
                throw e;
            }
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 RunnableCallableDemo.java
java RunnableCallableDemo
```

Stdout chính xác:

```text
Runnable result: null
Callable result: 42
Task failure: IOException: read failed
```

Ba tác vụ được gửi trước khi bắt đầu chờ kết quả. Việc chúng hoàn tất theo thứ tự nào không quyết định thứ tự các dòng trên: chỉ luồng `main` in ra, theo thứ tự các câu lệnh của nó.

Tác vụ đầu hoàn tất nhưng không có giá trị trả về; tác vụ thứ hai tạo ra `42`; tác vụ cuối ném checked exception hợp lệ từ `call()`, rồi `get()` báo lỗi qua `ExecutionException`.

`main` khai báo `throws Exception` để giữ ví dụ tập trung. Trong ứng dụng thực, nơi gọi cần quyết định rõ cách phản hồi thất bại, timeout và ngắt. Khối `finally` quản lý tài nguyên executor: `shutdown()` không đợi tác vụ kết thúc; `awaitTermination(...)` dành một khoảng chờ; `shutdownNow()` chỉ cố gắng ngắt công việc còn chạy, không bảo đảm dừng cưỡng bức.

Cách đóng tường minh trên tương thích Java 17+. Nếu dùng `ExecutorService` với try-with-resources, cần Java 19 trở lên, vì khả năng `AutoCloseable` của giao diện này không có trên Java 17.

## 7. Chọn kiểu tác vụ theo nhu cầu của nơi gọi

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Chỉ thực hiện hành động | `Runnable` | Hợp đồng `void` diễn đạt đúng ý định |
| Chờ một hành động hoàn tất và nhận biết lỗi | `Runnable` + `submit` + `Future<?>` | Không cần giá trị nghiệp vụ nhưng vẫn cần theo dõi |
| Tính rồi trả dữ liệu | `Callable<V>` | Kết quả có kiểu, nhận qua `Future<V>` |
| Công việc cần truyền checked exception | `Callable<V>` | `call()` có hợp đồng `throws Exception` |

`Callable<Void>` cũng hợp lệ cho công việc không cần dữ liệu nhưng muốn truyền checked exception; khi thành công phải trả `null`. Đây là kiểu `java.lang.Void`, không phải từ khóa `void`.

Không chọn `Callable` chỉ vì cho rằng nó chạy nhanh hơn. Hai giao diện thể hiện hợp đồng khác nhau; hiệu năng còn phụ thuộc công việc, executor, mức song song và tài nguyên đang chờ.

## 8. Những điểm dễ hiểu nhầm

### Chờ ngay sau mỗi submit có thể làm mất cơ hội chạy chồng lấp

Nếu gửi tác vụ A rồi gọi `get()` ngay, sau khi A xong mới gửi B, thì A và B chưa từng cùng được gửi để xử lý đồng thời. Khi các công việc độc lập, thường gửi chúng trước rồi mới thu kết quả; vẫn phải giới hạn số tác vụ và tài nguyên trong bài toán thực.

### isDone không đồng nghĩa với thành công

Một `Future` có thể đã xong do hoàn tất bình thường, ném ngoại lệ hoặc bị hủy. Không dùng riêng `isDone()` để tuyên bố công việc thành công. Khi dùng các API tương thích Java 17 trong bài, `get()` là nơi nhận kết quả hoặc phát hiện lỗi.

### Timeout và hủy không phải tính năng riêng của Callable

Cả `Future` của `Runnable` và `Callable` đều có thể dùng `get(timeout, unit)` hoặc `cancel(...)`. Hết thời gian chờ chỉ làm lời gọi `get` ném `TimeoutException`; nó không tự hủy tác vụ. Yêu cầu ngắt cũng cần tác vụ hợp tác xử lý.

Các trạng thái và ngoại lệ của thao tác chờ được quy định trong [Future API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html).

### Lambda phụ thuộc kiểu đích

Để biểu đạt rõ lựa chọn overload, có thể khai báo kiểu trước:

```java
Runnable log = () -> System.out.println("saved");
Callable<Integer> count = () -> 42;
```

Lambda có khối và không trả giá trị phù hợp với `Runnable`; lambda trả dữ liệu phù hợp với `Callable`. Một số biểu thức lời gọi phương thức có thể dùng theo cả hai kiểu đích, vì kết quả có thể bị bỏ đi trong ngữ cảnh `void`. Khi quá trình chọn overload không rõ, đặt kiểu tác vụ tường minh thay vì đoán từ hình thức lambda.

### Tác vụ không tự bảo vệ dữ liệu dùng chung

Cùng một đối tượng `Runnable` hoặc `Callable` có thể được gửi nhiều lần. Nếu nó chứa trường có thể thay đổi và các lần thực thi truy cập đồng thời, vẫn cần thiết kế đồng bộ thích hợp. Ưu tiên dữ liệu đầu vào bất biến và trả kết quả riêng khi có thể.

## 9. Tự kiểm tra

1. Một `Runnable` gửi bằng `submit` có `Future` hay không? Nếu thành công thì `get()` trả gì?
2. `Callable<Integer> task = () -> 42;` đã tạo luồng mới chưa?
3. Một `Callable` ném `IOException`: gọi trực tiếp `call()` khác gọi `get()` sau `submit` thế nào?
4. Tại sao không nên dùng biến `int[]` dùng chung chỉ để đưa kết quả ra khỏi `Runnable`?
5. `isDone() == true` hoặc hết thời gian chờ có đủ để kết luận tác vụ thành công hay đã dừng không?

**Gợi ý đáp án:** (1) Có; trả `null` với overload một đối số. (2) Chưa. (3) Gọi trực tiếp nhận ngoại lệ theo hợp đồng `call()`; qua `Future.get()` nhận `ExecutionException` có nguyên nhân tương ứng. (4) Làm hợp đồng kết quả kém rõ ràng và dễ dẫn đến lỗi chia sẻ dữ liệu. (5) Không; cần phân biệt hoàn tất thành công, thất bại, hủy và việc chỉ dừng chờ.

Điểm cần nhớ: **Runnable mô tả hành động không trả giá trị; Callable mô tả công việc trả kết quả và có thể truyền checked exception. Executor tổ chức việc chạy, còn Future là nơi theo dõi và nhận kết quả khi dùng submit.**
