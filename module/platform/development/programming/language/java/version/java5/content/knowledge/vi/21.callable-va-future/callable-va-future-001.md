# Callable<V>, giá trị trả về và ngoại lệ của tác vụ

## 1. Callable giải quyết vấn đề gì?

Một công việc chạy độc lập thường cần cho nơi gọi biết **kết quả là gì** hoặc **vì sao không tạo được kết quả**. Chẳng hạn, tác vụ đọc cấu hình phải trả nội dung đã đọc; tác vụ tính tổng phải trả một con số. Chỉ giao một khối lệnh không trả dữ liệu sẽ khiến chương trình phải tự tạo thêm cách trao đổi kết quả và lỗi.

`Callable<V>` biểu diễn công việc có thể trả một kết quả kiểu `V` và có thể ném ngoại lệ. Nó là một giao diện hàm (functional interface), nên có thể được cài đặt bằng lớp, lambda hoặc tham chiếu phương thức.

Hợp đồng cốt lõi:

```java
V call() throws Exception;
```

`V` là kiểu của **kết quả**, không phải kiểu luồng hay kiểu ngoại lệ. `call()` không có tham số; dữ liệu đầu vào có thể được truyền qua hàm tạo của lớp cài đặt hoặc được lambda giữ từ phạm vi bao quanh. [Hợp đồng Callable](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Callable.html).

Ba thành phần cần phân biệt trong chương này:

```text
Callable<V>       mô tả công việc tạo ra V
ExecutorService   tiếp nhận và tổ chức thực thi công việc
Future<V>         đại diện cho việc hoàn thành/kết quả của một lần giao việc
```

Callable tự nó không tạo luồng. Gọi `task.call()` là lời gọi phương thức thông thường trên chính luồng gọi. Muốn giao việc cho executor, thường dùng `submit(task)` rồi nhận Future. Đây đều là API còn áp dụng trong Java hiện nay; ví dụ chính tương thích Java 17 trở lên.

## 2. Kiểu kết quả V và quy tắc trả giá trị

Các khai báo sau minh họa bên trong một phương thức đã import `java.util.concurrent.Callable`:

```java
Callable<Integer> total = () -> 6 * 7;
Callable<String> title = () -> "Java concurrency";
Callable<Boolean> valid = () -> true;
Callable<Void> noData = () -> {
    return null;
};
```

- `Callable<Integer>` trả `Integer`; biểu thức số nguyên được đóng gói tự động khi cần.
- Không viết `Callable<int>` vì tham số kiểu generic là kiểu tham chiếu, không phải kiểu nguyên thủy.
- `Callable<Void>` biểu diễn tác vụ không có dữ liệu kết quả hữu ích. Khác `void`, `Void` là một kiểu tham chiếu; cách trả thông thường là `null`.
- Kết quả có thể là một đối tượng miền nghiệp vụ, danh sách hoặc một cấu trúc bất biến, không chỉ là số/chuỗi.

Nếu `call()` kết thúc bình thường, nó phải đáp ứng hợp đồng trả về. Với lambda có khối lệnh, các nhánh có thể hoàn thành bình thường phải trả giá trị phù hợp; một nhánh ném ngoại lệ không cần trả thêm giá trị.

### null có nghĩa là lỗi không?

Không. Một Callable có thể hoàn thành bình thường với kết quả `null`. Khi đó Future tương ứng cũng có thể trả `null` từ `get()`.

Nếu `null` không được phép trong hợp đồng nghiệp vụ, cần xác định điều đó ở thiết kế tác vụ, kiểm tra đầu ra hoặc dùng một mô hình kết quả rõ nghĩa. Không mặc định diễn giải `null` vừa là “không tìm thấy”, vừa là “thất bại”, vừa là “không có dữ liệu”. Những ý nghĩa lẫn nhau làm nơi gọi khó xử lý chính xác.

Cũng cần tránh mở hộp một kết quả có thể null:

```java
Callable<Integer> maybeNull = () -> null;
Integer result = maybeNull.call();
// int primitive = result; // sẽ ném NullPointerException nếu thực hiện
```

Đoạn trên cần phương thức bao quanh xử lý/khai báo `Exception`; dòng gây lỗi được giữ dưới dạng chú thích để không vô tình chạy.

## 3. Callable so với Runnable

| Tiêu chí | `Runnable` | `Callable<V>` |
|---|---|---|
| Phương thức chức năng | `void run()` | `V call() throws Exception` |
| Trả dữ liệu từ tác vụ | Không qua `run()` | Có, theo kiểu `V` |
| Ném ngoại lệ được kiểm tra ra ngoài | Không được khai báo thêm vào hợp đồng `run()` | Được phép theo hợp đồng `call()` |
| Dùng trực tiếp với `Thread` | `Thread` nhận Runnable | Không có hàm tạo Thread nhận Callable trực tiếp |
| Giao cho ExecutorService | `submit(Runnable)` | `submit(Callable<V>)` |

Runnable vẫn có thể ném ngoại lệ không được kiểm tra như `IllegalArgumentException`. Câu “Runnable không ném được ngoại lệ” là không chính xác; điểm khác biệt là hợp đồng không khai báo ngoại lệ được kiểm tra (checked exception).

Ngược lại, chọn Callable không có nghĩa tác vụ nhất thiết phải thất bại hoặc luôn phải khai báo một ngoại lệ ở mọi lớp cài đặt. Phương thức cài đặt có thể khai báo phạm vi ngoại lệ hẹp hơn, hoặc không khai báo ngoại lệ được kiểm tra nào.

## 4. Dữ liệu đầu vào khi call() không nhận tham số

Một lớp có thể lưu dữ liệu cần tính toán trong trường bất biến:

```java
final class SumTask implements Callable<Integer> {
    private final int left;
    private final int right;

    SumTask(int left, int right) {
        this.left = left;
        this.right = right;
    }

    @Override
    public Integer call() {
        return Math.addExact(left, right);
    }
}
```

Đây là lớp minh họa cần import `Callable`; không có `main`. `Math.addExact` báo `ArithmeticException` nếu cộng vượt miền giá trị của `int`, thay vì âm thầm cho kết quả tràn số. `call()` ở lớp này không cần khai báo `throws Exception` vì không phát sinh ngoại lệ được kiểm tra.

Với lambda, có thể giữ các biến cục bộ là `final` hoặc không bị gán lại (effectively final):

```java
int left = 20;
int right = 22;
Callable<Integer> task = () -> Math.addExact(left, right);
```

Giữ một tham chiếu không làm đối tượng được tham chiếu trở thành bất biến. Nếu lambda giữ một danh sách rồi luồng khác sửa danh sách đó khi tác vụ chạy, vẫn phải thiết kế đồng bộ hoặc tạo bản sao đầu vào phù hợp. Tránh coi việc “đã đưa vào Callable” là một cơ chế sao chép dữ liệu tự động.

## 5. Hai cách gọi có hai đường đi ngoại lệ

### 5.1. Gọi trực tiếp call()

```java
Callable<String> task = () -> {
    throw new java.io.IOException("data unavailable");
};
String text = task.call();
```

Đây là đoạn minh họa cần xử lý/khai báo `Exception` ở phương thức bao quanh. Nó chạy ngay trên luồng gọi. Nếu tác vụ ném `IOException`, ngoại lệ truyền trực tiếp qua lời gọi `call()`, không tự được bọc thành `ExecutionException`.

Khi biến có kiểu `Callable<String>`, hợp đồng tĩnh của `call()` vẫn là `throws Exception`, kể cả lambda cụ thể chỉ ném `IOException`. Cần bắt hoặc khai báo đủ phạm vi theo kiểu được dùng tại nơi gọi; không dựa vào việc nhìn nội dung lambda để bỏ qua kiểm tra của trình biên dịch.

### 5.2. Giao Callable cho executor

```java
Future<String> future = pool.submit(task);
String text = future.get();
```

Ở đây `pool` là `ExecutorService` đã tồn tại. `submit` trả `Future<String>`, không trả ngay nội dung chuỗi. Sau khi tác vụ thành công, `get()` trả kết quả; nếu chưa hoàn thành, `get()` có thể chờ. [ExecutorService.submit(Callable)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html#submit(java.util.concurrent.Callable)).

Nếu tác vụ thất bại, Future giữ thông tin thất bại và `get()` báo bằng `ExecutionException`. Lấy `getCause()` để phân biệt nguyên nhân như lỗi dữ liệu, lỗi I/O hay lỗi lập trình. Việc đặt tên một biến là `future` không khiến nơi gọi tự biết lỗi: phải thực sự quan sát kết quả hoặc có đường giám sát rõ ràng khác.

`try/catch` chỉ bọc `pool.submit(task)` không đủ bắt lỗi tính toán xảy ra sau đó ở luồng thực thi. Tuy nhiên, `submit` bản thân vẫn có thể báo lỗi ngay khi giao việc, chẳng hạn executor không nhận tác vụ với chính sách từ chối mặc định. **Lỗi giao việc và lỗi chạy việc xảy ra ở hai thời điểm khác nhau.**

## 6. Chương trình đầy đủ: giá trị thành công và lỗi được kiểm tra

Lưu thành `CallableResultDemo.java`. Bài thử dùng phép tính thuần không có trạng thái thay đổi và một tác vụ ném `IOException` có chủ đích; không phụ thuộc tệp hoặc mạng thực tế.

```java
import java.io.IOException;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CallableResultDemo {
    public static void main(String[] args) throws Exception {
        Callable<Integer> calculation = () -> Math.addExact(20, 22);
        Callable<String> failingRead = () -> {
            throw new IOException("data unavailable");
        };

        System.out.println("direct result: " + calculation.call());
        try {
            failingRead.call();
            throw new AssertionError("Expected IOException");
        } catch (IOException ex) {
            System.out.println("direct exception: "
                    + ex.getClass().getSimpleName());
        }

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> value = pool.submit(calculation);
            Future<String> failure = pool.submit(failingRead);
            System.out.println("future result: "
                    + value.get(10, TimeUnit.SECONDS));

            try {
                failure.get(10, TimeUnit.SECONDS);
                throw new AssertionError("Expected ExecutionException");
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();
                System.out.println("future exception: "
                        + cause.getClass().getSimpleName());
                System.out.println("future cause message: "
                        + cause.getMessage());
            }

            Callable<Void> noData = () -> null;
            Future<Void> completion = pool.submit(noData);
            System.out.println("Void result: "
                    + completion.get(10, TimeUnit.SECONDS));
        } finally {
            shutdown(pool);
        }
    }

    private static void shutdown(ExecutorService pool) {
        pool.shutdown();
        try {
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Executor did not terminate");
                }
            }
        } catch (InterruptedException ex) {
            pool.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 CallableResultDemo.java
java CallableResultDemo
```

Stdout khi chương trình hoàn thành bình thường:

```text
direct result: 42
direct exception: IOException
future result: 42
future exception: IOException
future cause message: data unavailable
Void result: null
```

Đọc kết quả theo hợp đồng:

1. `calculation.call()` tính trên luồng `main` và trả trực tiếp `42`.
2. `failingRead.call()` truyền trực tiếp `IOException` đến khối bắt ngoại lệ ở `main`.
3. `pool.submit(calculation)` tạo một lần thực thi khác, trả Future rồi nhận `42` bằng `get()`.
4. Lỗi của tác vụ đã giao được `get()` báo qua `ExecutionException`; chương trình in **nguyên nhân**, nên dòng tương ứng ghi `IOException`.
5. `Callable<Void>` thành công với `null`; không có ngoại lệ đồng nghĩa kết quả đó là kết quả bình thường theo hợp đồng tác vụ.

Chương trình chủ động dùng lại hai Callable không có trạng thái thay đổi. Mỗi lần gọi/giao việc vẫn thực hiện lại công việc; không có bộ nhớ đệm kết quả tự động. Các dòng kết quả đều do luồng `main` in sau điểm quan sát tương ứng, nên không phụ thuộc thứ tự các luồng thực thi in ra console.

## 7. Phân loại lỗi khi lấy kết quả

| Hiện tượng | Nguồn của trạng thái/lỗi | Cách hiểu |
|---|---|---|
| `get()` trả `V` | Tác vụ kết thúc bình thường | Có kết quả theo hợp đồng, kể cả null nếu được phép |
| `ExecutionException` | Tác vụ ném lỗi | Xem `getCause()` để xử lý nguyên nhân |
| `InterruptedException` | Luồng đang chờ kết quả bị ngắt | Không tự kết luận Callable đã bị ngắt hoặc thất bại |
| `CancellationException` | Future bị hủy | Không có kết quả bình thường để lấy |
| `TimeoutException` ở `get(timeout, unit)` | Nơi gọi chờ quá hạn | Tác vụ có thể vẫn tiếp tục chạy |

`ExecutionException` là lớp bọc tại ranh giới lấy kết quả. Lỗi gốc vẫn có ý nghĩa riêng; nên giữ nguyên chuỗi nguyên nhân khi chuyển thành lỗi của tầng ứng dụng, thay vì chỉ ghi một chuỗi chung rồi làm mất thông tin chẩn đoán. [ExecutionException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutionException.html).

Nếu Callable ném `InterruptedException` vì chính tác vụ bị ngắt và không tự xử lý, đó là **lỗi của lần thực thi tác vụ**, có thể được quan sát dưới nguyên nhân của `ExecutionException` nếu Future không được chuyển sang trạng thái hủy. Nó khác với `InterruptedException` do `get()` ném khi luồng đang chờ bị ngắt. Nếu Future đã bị hủy, quan sát qua `get()` thường là `CancellationException` theo hợp đồng hủy.

Với Callable chạy trong FutureTask thông thường, ngoại lệ không được kiểm tra như `IllegalStateException` cũng có thể được báo qua `ExecutionException` khi lấy kết quả. Không suy luận rằng chỉ ngoại lệ được kiểm tra mới đi qua Future.

## 8. Đừng biến thất bại thành một giá trị thành công mơ hồ

Giả sử tác vụ đọc dữ liệu bắt mọi `Exception` rồi `return ""`. Khi đó Future có thể hoàn thành bình thường với chuỗi rỗng, dù nguyên nhân thực tế là không đọc được dữ liệu. Nơi gọi không còn phân biệt được “nội dung thật sự rỗng” với “đọc thất bại”.

Có ba lựa chọn tùy hợp đồng nghiệp vụ:

- Để ngoại lệ thích hợp truyền ra, cho nơi gọi xử lý qua Future.
- Chuyển thành ngoại lệ miền nghiệp vụ có thông điệp rõ ràng, đồng thời giữ nguyên nguyên nhân.
- Trả một kiểu kết quả có các trạng thái rõ ràng nếu thất bại đó thực sự là kết quả nghiệp vụ dự kiến.

Không chọn giá trị giả như `-1` hoặc `null` chỉ để hết lỗi biên dịch. Nếu một giá trị đặc biệt là một phần hợp đồng, phải mô tả rõ và bảo đảm nơi gọi xử lý nó. Với tác vụ truy cập tài nguyên, dùng cơ chế đóng tài nguyên phù hợp kể cả khi tác vụ ném lỗi.

Bản thân `throws Exception` cũng không có nghĩa nên bắt rộng và bỏ qua mọi lỗi. Nó cho tác vụ khả năng báo thất bại; thiết kế ứng dụng vẫn cần quyết định mức nào chịu trách nhiệm xử lý và mức nào chỉ truyền lỗi tiếp.

## 9. Kết quả không tự trở thành bản sao an toàn

Nếu Callable trả một danh sách có thể thay đổi, `Future.get()` trả tham chiếu kết quả, không tự tạo bản sao sâu. Quan hệ đồng bộ của Future giúp công việc đã thực hiện trước khi hoàn thành được quan sát đúng sau khi nhận kết quả, nhưng không bảo vệ các lần sửa tiếp theo từ nhiều luồng. [Future và tính nhất quán bộ nhớ](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html).

Một cách dễ quản lý là để tác vụ xây dựng kết quả trong dữ liệu riêng, rồi công bố một kết quả bất biến hoặc chuyển quyền sở hữu rõ ràng. Tránh vừa trả một đối tượng cho nơi gọi vừa tiếp tục cho luồng khác sửa nó mà không có hợp đồng đồng bộ.

Tương tự, dùng một đối tượng Callable cho nhiều lần `submit` không tự bảo đảm an toàn luồng. Nếu `call()` tăng một trường đếm không được bảo vệ hoặc sử dụng tài nguyên không cho phép truy cập đồng thời, các lần thực thi có thể tranh chấp. Khi không cần chia sẻ trạng thái, tạo mỗi tác vụ với đầu vào độc lập thường dễ hiểu hơn.

## 10. Lỗi thường gặp và tự kiểm tra

| Lỗi | Cách sửa mô hình hiểu |
|---|---|
| Khai báo Callable rồi cho rằng nó đang chạy nền | Callable chỉ mô tả công việc; chọn cách thực thi riêng |
| Viết `Callable<int>` | Dùng `Callable<Integer>` |
| Tưởng `Callable<Void>` không cần return khi hoàn thành bình thường | Dùng `return null` theo hợp đồng |
| Bắt IOException trực tiếp chỉ quanh `Future.get()` | Bắt ExecutionException rồi kiểm tra nguyên nhân |
| Bỏ Future của tác vụ có thể thất bại | Xác định đường quan sát kết quả/lỗi |
| Cho rằng timeout đồng nghĩa tác vụ đã bị hủy | Timeout giới hạn việc chờ; hủy là thao tác/chính sách riêng |
| Gửi nhiều lần cùng Callable có trạng thái rồi cho rằng tự an toàn | Thiết kế trạng thái, đồng bộ và tài nguyên cho các lần chạy |

Tự kiểm tra:

1. `Callable<String>` trả `null` có tự trở thành thất bại không? **Không**, trừ khi mã tác vụ/hợp đồng ứng dụng chủ động kiểm tra và báo lỗi.
2. `call()` ném `IOException`; gọi trực tiếp và gọi qua `submit` khác nhau ở đâu? **Gọi trực tiếp nhận IOException theo lời gọi phương thức; qua Future, lấy kết quả thất bại bằng get() nhận ExecutionException với nguyên nhân là IOException.**
3. Một Callable luôn trả `42` có cần khai báo `throws Exception` trong phương thức cài đặt không? **Không.** Nhưng nơi gọi qua kiểu Callable vẫn phải tôn trọng chữ ký của giao diện.
4. `Future<Integer>` có phải chính số nguyên kết quả không? **Không.** Nó đại diện cho một lần thực thi và cần được quan sát theo trạng thái/kết quả.

Thực hành: trong chương trình đầy đủ, thay `failingRead` bằng `throw new IllegalArgumentException("invalid input")`. Sửa khối bắt lỗi của lời gọi trực tiếp cho phù hợp, rồi so sánh nguyên nhân lấy từ Future. Sau đó cho tác vụ trả một chuỗi hợp lệ và sửa kiểm tra thành công tương ứng. Dự đoán trước mỗi thay đổi sẽ ảnh hưởng đến đường trả giá trị hay đường ném ngoại lệ.
