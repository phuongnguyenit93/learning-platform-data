# Hoàn tất CompletableFuture bất đồng bộ bằng completeAsync và lựa chọn Executor

## Mục tiêu

Sau bài học này, bạn có thể:

- Dùng hai overload \`CompletableFuture.completeAsync\` được bổ sung trong Java 9.
- Phân biệt hoàn tất một future đã tồn tại với việc tạo future mới bằng \`supplyAsync\`.
- Chọn executor phù hợp với công việc CPU-bound, I/O blocking và yêu cầu cô lập tài nguyên.
- Hiểu cách supplier trả về giá trị, ném exception hoặc cạnh tranh với một thao tác hoàn tất khác.
- Xử lý executor bị từ chối nhận task và quản lý vòng đời của executor.
- Tránh giả định các stage nối tiếp tự động chạy trên cùng executor.

## 1. completeAsync dùng để làm gì?

Thông thường, một \`CompletableFuture<T>\` được hoàn tất bằng một trong các cách:

- \`complete(value)\`: đặt giá trị trực tiếp.
- \`completeExceptionally(error)\`: hoàn tất bằng lỗi.
- \`completeAsync(supplier)\`: tính giá trị trong một task được gửi đến executor rồi dùng kết quả để hoàn tất future.

Java 9 bổ sung hai overload:

~~~java
CompletableFuture<T> completeAsync(
        Supplier<? extends T> supplier);

CompletableFuture<T> completeAsync(
        Supplier<? extends T> supplier,
        Executor executor);
~~~

Ví dụ:

~~~java
CompletableFuture<String> result = new CompletableFuture<>();

result.completeAsync(() -> loadConfiguration(), executor);
~~~

Điểm quan trọng là \`completeAsync\` làm việc trên future đã tồn tại và trả về chính future đó. Supplier được gọi trong task do executor thực thi. Khi supplier trả về giá trị, future được hoàn tất bằng giá trị ấy; nếu supplier ném exception, future được hoàn tất exceptional.

Method không trả về một future mới đại diện cho supplier. Nó trả về object \`CompletableFuture\` ban đầu để caller tiếp tục nối các stage hoặc chờ kết quả.

## 2. Phân biệt completeAsync và supplyAsync

Hai method có mục đích gần nhau nhưng khác điểm bắt đầu:

~~~java
CompletableFuture<String> existing = new CompletableFuture<>();

// Hoàn tất object đã có.
existing.completeAsync(() -> loadConfiguration(), executor);

// Tạo một CompletableFuture mới từ Supplier.
CompletableFuture<String> created =
        CompletableFuture.supplyAsync(
                () -> loadConfiguration(), executor);
~~~

| Method | Future đầu vào | Kết quả trả về |
|---|---|---|
| \`existing.completeAsync(supplier, executor)\` | Một future đã tồn tại | Chính future đó |
| \`CompletableFuture.supplyAsync(supplier, executor)\` | Không cần future có sẵn | Một future mới |

Dùng \`completeAsync\` khi một API hoặc object đã tạo future và một thành phần khác chịu trách nhiệm cung cấp kết quả sau đó. Dùng \`supplyAsync\` khi muốn tạo future mới trực tiếp từ một tác vụ có kết quả.

Nếu tác vụ không trả về giá trị, \`runAsync\` thường phù hợp hơn:

~~~java
CompletableFuture<Void> saved =
        CompletableFuture.runAsync(
                () -> saveData(), executor);
~~~

## 3. Lựa chọn executor

Overload không truyền executor:

~~~java
future.completeAsync(() -> calculate());
~~~

sử dụng default async execution facility của \`CompletableFuture\`. Thông thường đó là \`ForkJoinPool.commonPool()\`. Nếu common pool không hỗ trợ mức parallelism tối thiểu là hai, implementation có thể tạo một thread mới cho từng task. Không dựa vào tên thread hoặc số lượng thread cụ thể của default facility.

Overload truyền executor:

~~~java
future.completeAsync(() -> loadData(), executor);
~~~

cho phép ứng dụng kiểm soát nơi task được thực thi. Có thể dùng một thread pool dùng chung, một pool chuyên cho I/O hoặc executor có chính sách giới hạn riêng.

### 3.1. Công việc CPU-bound

Với phép tính CPU ngắn, không blocking, common pool thường là lựa chọn phù hợp nếu workload của ứng dụng cho phép chia sẻ tài nguyên:

~~~java
CompletableFuture<Long> total = new CompletableFuture<>();

total.completeAsync(() -> calculateChecksum(data));
~~~

Không nên mặc định mọi tác vụ đều phù hợp với common pool. Một lượng lớn tác vụ blocking có thể chiếm worker thread và làm chậm những công việc khác đang dùng chung pool.

### 3.2. Công việc I/O blocking

Đọc file, gọi hệ thống bên ngoài hoặc chờ network có thể block trong thời gian dài. Hãy cân nhắc executor riêng để cô lập những tác vụ này:

~~~java
ExecutorService ioExecutor =
        Executors.newFixedThreadPool(8);

CompletableFuture<String> response =
        new CompletableFuture<>();

response.completeAsync(
        () -> callRemoteService(),
        ioExecutor);
~~~

Kích thước pool phải dựa trên tải, giới hạn kết nối, bộ nhớ và thời gian chờ thực tế. Pool quá lớn có thể làm cạn thread hoặc tài nguyên hệ thống; pool quá nhỏ có thể tạo hàng đợi dài.

### 3.3. Executor quyết định chính sách chạy

\`Executor\` chỉ định cách nhận và thực thi task. Interface này không bảo đảm task luôn chạy trên một thread khác. Ví dụ executor trực tiếp:

~~~java
Executor directExecutor = Runnable::run;

future.completeAsync(() -> "done", directExecutor);
~~~

thực thi \`Runnable\` ngay trong lời gọi \`execute\`, vì vậy supplier có thể chạy ngay trên thread gọi \`completeAsync\`. Nếu cần ranh giới bất đồng bộ thực sự, hãy truyền executor có cơ chế lập lịch phù hợp, chẳng hạn \`ExecutorService\`.

## 4. Điều gì xảy ra khi supplier chạy?

Có ba kết quả thường gặp:

1. **Supplier trả về giá trị:** future được hoàn tất bình thường bằng giá trị đó.
2. **Supplier ném exception:** future được hoàn tất exceptional; khi gọi \`join()\`, caller thường nhận \`CompletionException\` với nguyên nhân là exception của supplier.
3. **Một thao tác khác hoàn tất future trước:** kết quả đã được đặt không bị ghi đè bởi lần hoàn tất sau. \`CompletableFuture\` dùng quy tắc first-completion-wins cho các thao tác hoàn tất thông thường.

Ví dụ supplier lỗi:

~~~java
CompletableFuture<String> failed = new CompletableFuture<>();

failed.completeAsync(() -> {
    throw new IllegalStateException("service unavailable");
}, executor);

try {
    failed.join();
} catch (CompletionException ex) {
    Throwable cause = ex.getCause();
    System.out.println(cause.getClass().getSimpleName());
}
~~~

Output:

~~~text
IllegalStateException
~~~

Không dùng supplier như nơi thực hiện side effect không thể lặp lại hoặc không thể bỏ qua. Nếu \`complete\`, \`completeExceptionally\` hoặc \`cancel\` cạnh tranh với task, supplier có thể đã bắt đầu chạy nhưng kết quả của nó không còn thắng được lần hoàn tất trước. Hãy để supplier tập trung tạo kết quả; quản lý side effect bằng cơ chế có tính nhất quán riêng.

## 5. Xử lý executor bị từ chối task

Executor có thể từ chối task, chẳng hạn thread pool đã shutdown hoặc hàng đợi có giới hạn đã đầy. Khi việc gọi \`execute\` ném \`RejectedExecutionException\`, lời gọi \`completeAsync\` có thể ném exception ngay tại chỗ và task không được lập lịch.

~~~java
Executor rejectingExecutor = command -> {
    throw new RejectedExecutionException("executor is closed");
};

CompletableFuture<String> pending = new CompletableFuture<>();

try {
    pending.completeAsync(() -> "value", rejectingExecutor);
} catch (RejectedExecutionException ex) {
    // Chưa có task nào được nhận để hoàn tất future.
    System.out.println("task rejected");
}
~~~

Trong trường hợp executor từ chối đồng bộ như ví dụ trên, future vẫn chưa hoàn tất. Caller cần quyết định retry, chuyển sang executor khác hoặc hoàn tất future bằng lỗi:

~~~java
pending.completeExceptionally(
        new IllegalStateException("No executor available"));
~~~

Không nên retry vô hạn khi executor đã shutdown hoặc hệ thống đang quá tải. Hãy có chính sách giới hạn retry, backoff và xử lý lỗi phù hợp với ứng dụng.

## 6. Ví dụ hoàn chỉnh với Executor riêng

Tạo file **CompleteAsyncDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class CompleteAsyncDemo {

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "complete-demo"));

        try {
            CompletableFuture<String> target = new CompletableFuture<>();
            AtomicReference<String> supplierThread = new AtomicReference<>();

            CompletableFuture<String> returned = target.completeAsync(() -> {
                supplierThread.set(Thread.currentThread().getName());
                return "ready";
            }, executor);

            String value = target.get(5, TimeUnit.SECONDS);

            System.out.println("same future = " + (returned == target));
            System.out.println("value = " + value);
            System.out.println("supplier thread = " + supplierThread.get());

            CompletableFuture<String> failed = new CompletableFuture<>();
            failed.completeAsync(() -> {
                throw new IllegalStateException("boom");
            }, executor);

            try {
                failed.join();
                throw new AssertionError("Expected exceptional completion");
            } catch (CompletionException ex) {
                System.out.println("supplier failure = "
                        + ex.getCause().getClass().getSimpleName());
            }

            Executor rejectingExecutor = task -> {
                throw new RejectedExecutionException("closed");
            };

            CompletableFuture<String> rejected = new CompletableFuture<>();
            boolean rejectedSynchronously = false;

            try {
                rejected.completeAsync(
                        () -> "never scheduled", rejectingExecutor);
            } catch (RejectedExecutionException expected) {
                rejectedSynchronously = true;
            }

            System.out.println("executor rejection thrown = "
                    + rejectedSynchronously);
            System.out.println("rejected future still pending = "
                    + !rejected.isDone());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 -Xlint:all -d out CompleteAsyncDemo.java
java -cp out CompleteAsyncDemo
~~~

Output chính xác:

~~~text
same future = true
value = ready
supplier thread = complete-demo
supplier failure = IllegalStateException
executor rejection thrown = true
rejected future still pending = true
~~~

Ví dụ cho thấy:

- Method trả về đúng object future đã tạo.
- Supplier chạy trên thread do executor riêng quản lý.
- Exception từ supplier được lưu trong future và xuất hiện dưới dạng nguyên nhân của \`CompletionException\`.
- Executor từ chối task có thể làm lời gọi \`completeAsync\` ném \`RejectedExecutionException\` đồng bộ; future chưa được task đó hoàn tất.
- Executor được shutdown sau khi tác vụ đã hoàn tất.

## 7. Nối các stage và chọn executor cho từng bước

Executor dùng để chạy supplier của \`completeAsync\` không tự động trở thành executor mặc định cho mọi stage nối tiếp.

Ví dụ:

~~~java
CompletableFuture<String> result = new CompletableFuture<>();

result.completeAsync(() -> loadUser(), ioExecutor)
      .thenApply(user -> formatUser(user))
      .thenApplyAsync(user -> enrichUser(user), cpuExecutor);
~~~

Cần phân biệt:

- \`thenApply\` là stage không có hậu tố \`Async\`; action có thể chạy trên thread hoàn tất stage trước đó hoặc thread gọi đăng ký stage nếu future đã hoàn tất.
- \`thenApplyAsync\` lập lịch action bất đồng bộ bằng default async facility nếu không truyền executor.
- \`thenApplyAsync(action, executor)\` dùng executor được chỉ định cho stage đó.

Nếu bước tiếp theo cũng cần chạy trên một pool cụ thể, hãy truyền executor ở chính stage đó. Không suy luận rằng toàn bộ pipeline sẽ chạy trên \`ioExecutor\` chỉ vì supplier đầu tiên được gửi vào executor này.

## 8. Quản lý vòng đời executor

Executor có thể là tài nguyên dùng chung của ứng dụng. Cần xác định rõ ai sở hữu và ai có quyền shutdown:

- Nếu method tạo \`ExecutorService\` riêng, method hoặc thành phần sở hữu nó phải shutdown khi không còn cần dùng.
- Nếu executor được inject từ bên ngoài hoặc dùng chung toàn ứng dụng, không shutdown nó sau một tác vụ đơn lẻ.
- \`shutdown()\` ngừng nhận task mới nhưng cho task đã nhận cơ hội hoàn tất.
- \`shutdownNow()\` yêu cầu dừng task đang chạy và trả về task đang chờ; việc dừng thực tế phụ thuộc vào khả năng phản hồi interrupt của tác vụ.
- Luôn xử lý trường hợp task bị từ chối sau khi executor đã shutdown.

Không tạo một thread pool mới cho từng request nếu không có chính sách vòng đời và giới hạn rõ ràng. Việc tạo quá nhiều pool làm tăng chi phí thread, khó giám sát và có thể khiến ứng dụng quá tải.

## 9. Lỗi thường gặp

### Dùng completeAsync khi cần tạo future mới

\`completeAsync\` hoàn tất future đã có. Dùng \`supplyAsync\` nếu cần tạo future mới từ supplier.

### Nghĩ rằng completeAsync luôn chạy trên thread khác

Executor trực tiếp có thể thực thi task ngay trong thread gọi. Chọn executor có cơ chế lập lịch nếu cần tách luồng.

### Đưa tác vụ blocking lớn vào common pool

Các worker của common pool có thể bị chiếm bởi I/O blocking. Cân nhắc pool chuyên dụng và giới hạn concurrency.

### Nghĩ supplier lỗi sẽ ném trực tiếp tại nơi gọi join

Exception của supplier được lưu trong future. \`join()\` ném \`CompletionException\`; kiểm tra \`getCause()\` để tìm lỗi gốc.

### Bỏ qua RejectedExecutionException

Executor có thể từ chối task ngay khi gọi \`completeAsync\`. Xử lý rejection tại ranh giới gửi task và quyết định cách hoàn tất hoặc retry future.

### Giả định future chưa hoàn tất thì supplier chắc chắn sẽ thắng

Một thao tác khác có thể hoàn tất hoặc cancel future trước khi supplier chạy xong. Thiết kế pipeline theo quy tắc first-completion-wins và tránh side effect không an toàn khi có race.

### Nghĩ các stage nối tiếp dùng cùng executor

Executor của một stage không tự động áp dụng cho stage sau. Chỉ định executor riêng ở từng stage \`Async\` khi cần kiểm soát.

### Shutdown executor dùng chung

Chỉ thành phần sở hữu executor mới nên quản lý shutdown. Không gọi \`shutdown()\` trên pool được chia sẻ bởi các thành phần khác.

## 10. Checklist

- [ ] Đã xác định future cần hoàn tất đã tồn tại hay cần tạo mới.
- [ ] Đã chọn \`completeAsync\` hoặc \`supplyAsync\` đúng mục đích.
- [ ] Đã hiểu overload không truyền executor dùng default async facility.
- [ ] Đã chọn executor phù hợp với CPU-bound hoặc I/O blocking.
- [ ] Đã kiểm tra supplier trả về giá trị và xử lý exception.
- [ ] Đã tính đến race giữa supplier, complete, completeExceptionally và cancel.
- [ ] Đã xử lý \`RejectedExecutionException\` khi executor từ chối task.
- [ ] Đã chỉ định executor ở từng stage \`Async\` cần kiểm soát.
- [ ] Đã xác định ai sở hữu và shutdown ExecutorService.
- [ ] Đã biên dịch và chạy ví dụ với JDK 17.

