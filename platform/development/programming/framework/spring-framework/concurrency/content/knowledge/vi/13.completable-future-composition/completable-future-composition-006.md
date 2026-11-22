# Biến thể Async và lựa chọn bộ thực thi tường minh trong CompletableFuture

**CompletableFuture** cho phép nối nhiều giai đoạn bất đồng bộ thành một pipeline: tạo dữ liệu, chuyển đổi kết quả, gọi thêm dịch vụ, kết hợp nhiều nhánh, xử lý lỗi và trả kết quả cuối. Điểm quan trọng trong **Spring Framework - concurrency** không chỉ là viết một phương thức có đuôi **Async**, mà còn phải trả lời: **giai đoạn nào chạy ở đâu, executor nào nhận việc, trường hợp nào chạy ngay trên thread hiện tại và việc lựa chọn đó tác động thế nào tới tài nguyên của ứng dụng?**

Bài học nằm trong nhóm **Kết hợp CompletableFuture**, với đề tài **Biến thể Async và lựa chọn bộ thực thi tường minh**. Trọng tâm là so sánh các biến thể không có Async và có Async, chỉ định Executor cho từng bước, hiểu cơ chế mặc định của JDK, phối hợp với Spring **@Async** và **ThreadPoolTaskExecutor**, tránh nghẽn pool, xử lý lỗi quá tải và xây dựng kiểm thử Java 17 có đầu ra xác định.

Các nguyên tắc đầu tiên:

- **thenApply** không có Async: tác vụ phụ thuộc có thể chạy ngay trên thread hoàn tất stage trước hoặc trong một ngữ cảnh gọi completion thích hợp; không có cam kết một worker riêng.
- **thenApplyAsync(fn)**: đăng ký một bước được thực thi bất đồng bộ bằng **default asynchronous execution facility** của CompletableFuture; với CompletableFuture chuẩn, thường là **ForkJoinPool.commonPool()**, không mặc nhiên là executor Spring.
- **thenApplyAsync(fn, executor)**: yêu cầu executor **được cung cấp tường minh** thực thi bước callback đó.
- **thenComposeAsync(fn, executor)**: executor được dùng để chạy **hàm fn tạo ra CompletionStage tiếp theo**, không mặc nhiên áp đặt executor cho toàn bộ những giai đoạn nằm bên trong stage mà fn trả về.
- **@Async("beanName")** của Spring và **CompletableFuture.*Async(..., executor)** của JDK là **hai cơ chế chọn executor riêng biệt**. Cấu hình một bên không tự gán executor mặc định cho mọi bước ở bên kia.

## 1. CompletableFuture có ba kiểu lựa chọn thực thi thường gặp

Tưởng tượng công việc gồm: tải dữ liệu từ hệ thống bên ngoài, chuẩn hóa kết quả rồi tính điểm.

~~~text
Request thread
    |
    +-- supplyAsync(load, ioExecutor)
                  |
                  | hoàn tất dữ liệu
                  v
         thenApplyAsync(transform, cpuExecutor)
                  |
                  v
         thenComposeAsync(nextStageFactory, cpuExecutor)
                  |
                  +-- hàm nextStageFactory trả về một CompletionStage
                      của thao tác ở executor khác nếu được chỉ định
                  |
                  v
              kết quả cuối
~~~

Với cùng một tác vụ chuyển đổi, ba lời gọi dưới đây có ý nghĩa khác nhau:

~~~java
CompletableFuture<Integer> source = /* một future hợp lệ */;

CompletableFuture<Integer> a =
        source.thenApply(n -> n * 2);

CompletableFuture<Integer> b =
        source.thenApplyAsync(n -> n * 2);

CompletableFuture<Integer> c =
        source.thenApplyAsync(n -> n * 2, cpuExecutor);
~~~

Đây là **đoạn mã minh họa trong một phương thức có source và cpuExecutor**, không phải chương trình Java độc lập.

| Cách viết | Vị trí callback được thực thi | Điều không được tự suy ra |
| --- | --- | --- |
| **thenApply(fn)** | Theo cơ chế non-async của CompletionStage: có thể là thread hoàn tất stage trước, hoặc caller tham gia hoàn tất/đăng ký trong trường hợp phù hợp | Không chắc chạy trong một executor mới |
| **thenApplyAsync(fn)** | Default async facility của CompletableFuture; thường là commonPool đối với CompletableFuture chuẩn | Không chắc chạy trong ThreadPoolTaskExecutor của Spring |
| **thenApplyAsync(fn, executor)** | Executor truyền vào nhận việc thực thi fn | Không chắc là một thread mới khác caller trong mọi custom Executor |

Phần cuối đặc biệt quan trọng: từ **Async** có nghĩa là callback được **giao cho cơ chế thực thi bất đồng bộ đã chọn**. Nếu bạn chủ động truyền một **Executor chạy trực tiếp** (Runnable::run) hoặc dùng một rejection policy kiểu **CallerRunsPolicy** khi pool đầy, callback vẫn có thể thực hiện ngay trên luồng submit. Do đó, **Async không phải một lời hứa rằng callback luôn chạy trên một OS thread khác** trong mọi cấu hình executor.

## 2. Non-async: tối ưu một bước nhỏ nhưng phải biết nó có thể chạy ở đâu

Các biến thể không có hậu tố Async, như **thenApply**, **thenAccept**, **thenRun**, **thenCompose**, **thenCombine**, **whenComplete** và **handle**, không tự yêu cầu một executor riêng cho callback.

Theo hợp đồng của CompletableFuture, hành động thuộc dependent completion ở biến thể non-async **có thể được thực thi bởi thread hoàn tất future hiện tại hoặc bởi một caller khác đang thực hiện một phương thức completion**.

Hai tình huống thường gặp:

**Trường hợp A — stage đã hoàn thành khi đăng ký callback:**

~~~java
Thread caller = Thread.currentThread();

boolean onCaller = CompletableFuture.completedFuture(10)
        .thenApply(n -> Thread.currentThread() == caller)
        .join();

System.out.println(onCaller);
~~~

Đây là **đoạn thân phương thức Java 17**. Với future đã hoàn tất và thenApply chuẩn trong ví dụ này, callback được chạy trực tiếp trong luồng đang đăng ký, nên in **true**. Không nên dựa vào hiện tượng này để coi **mọi** thenApply đều chạy trên caller.

**Trường hợp B — stage chưa hoàn thành:** callback được đăng ký trước, rồi một worker làm stage nguồn hoàn tất. Callback non-async thường có thể chạy trên thread làm nguồn hoàn tất. Nếu callback này làm I/O chặn lâu hoặc xử lý CPU nặng, nó có thể kéo dài thời gian một worker đang được dùng cho nhiệm vụ trước.

Quy tắc chọn:

- Biến đổi **rất nhẹ, không chặn, không giữ lock lâu**, như đổi trường DTO hoặc kiểm tra điều kiện đơn giản: non-async thường hợp lý.
- Tác vụ **CPU nặng, có blocking I/O, cần cô lập loại workload hoặc cần phân định tài nguyên**: xem xét Async với Executor tường minh.
- Nếu kết quả phải chạy trên một thread có affinity đặc biệt (UI/event loop), **không dựa vào thenApply non-async** để bảo đảm affinity; dùng cơ chế dispatch phù hợp với framework.

**Non-async không phải synchronous toàn bộ pipeline.** Nếu stage nguồn hoàn tất sau một phút, thenApply vẫn chỉ kích hoạt sau khi nguồn xong. Từ non-async ở đây mô tả **cách chạy callback phụ thuộc**, không nói rằng mọi nguồn chạy trong caller.

## 3. Async không chỉ là dùng ForkJoinPool.commonPool một cách vô thức

Khi dùng **CompletableFuture.supplyAsync(supplier)** hoặc **thenApplyAsync(fn)** mà **không truyền Executor**, CompletableFuture chuẩn dùng cơ chế async mặc định, thường là **ForkJoinPool.commonPool()**. Theo Javadoc Java 17, nếu commonPool không hỗ trợ mức song song tối thiểu là hai thì mặc định có thể dùng **thread mới cho từng task** thay thế. Có thể có subclass CompletableFuture tùy biến **defaultExecutor()** cho các phương thức instance.

Vì vậy, câu “mọi phương thức Async mặc định đều luôn chạy trên commonPool” là cách nói quá tuyệt đối. Đối với mã ứng dụng phổ thông, hãy hiểu **commonPool là mặc định thường gặp**, nhưng kiểm tra cấu hình/runtime nếu hành vi khác có ý nghĩa vận hành.

**Tại sao cần chú ý commonPool?**

- Đây là tài nguyên **chia sẻ của tiến trình Java**, không phải pool riêng của một Spring service.
- Một pipeline chạy nhiều blocking I/O trong commonPool có thể cạnh tranh với những tác vụ khác trong cùng JVM.
- Kích thước và chính sách của commonPool không tự động khớp với **CPU-bound**, **I/O-bound**, connection pool hay mục tiêu latency của ứng dụng.
- Việc một phương thức Spring dùng **@Async("myExecutor")** không tự động khiến những **thenApplyAsync() không tham số executor** bên trong cũng chạy trên myExecutor.
- Dùng Async không truyền executor làm khó việc phân loại workload và tracing nếu có nhiều subsystem cùng sử dụng commonPool.

**Không cần cấm commonPool tuyệt đối.** Nó có thể hữu ích cho tác vụ nhỏ, CPU-bound, dùng có chủ đích. Nhưng với backend có yêu cầu vận hành rõ, **chọn Executor tường minh** ở các giai đoạn cần kiểm soát thường giúp reasoning và đo đạc dễ hơn.

## 4. Nhóm API: những biến thể Async cần nhận diện

### 4.1 Tạo tác vụ gốc

| Phương thức | Mục đích | Biến thể truyền Executor |
| --- | --- | --- |
| **CompletableFuture.supplyAsync(supplier)** | Thực thi Supplier để tạo giá trị kết quả | **supplyAsync(supplier, executor)** |
| **CompletableFuture.runAsync(runnable)** | Chạy Runnable, future trả kiểu Void | **runAsync(runnable, executor)** |
| **future.completeAsync(supplier)** | Thử hoàn tất future bằng kết quả Supplier bất đồng bộ | **completeAsync(supplier, executor)** |

**runAsync** là lựa chọn khi task **không trả giá trị**, nhưng nó vẫn tạo CompletableFuture<Void> để theo dõi hoàn thành và lỗi. **supplyAsync** phù hợp khi task trả giá trị. **completeAsync** hoạt động trên một future có thể đã tồn tại và có cạnh tranh về việc ai hoàn tất nó; không phải cách thay thế máy móc cho supplyAsync.

### 4.2 Một stage nguồn, xử lý giá trị thành công

| Non-async | Async mặc định | Async với Executor | Ý nghĩa |
| --- | --- | --- | --- |
| **thenApply(fn)** | **thenApplyAsync(fn)** | **thenApplyAsync(fn, ex)** | T → U, trả một giá trị |
| **thenAccept(consumer)** | **thenAcceptAsync(consumer)** | **thenAcceptAsync(consumer, ex)** | Dùng T, không tạo giá trị mới |
| **thenRun(runnable)** | **thenRunAsync(runnable)** | **thenRunAsync(runnable, ex)** | Chạy sau thành công, không nhận T |
| **thenCompose(fn)** | **thenComposeAsync(fn)** | **thenComposeAsync(fn, ex)** | T → CompletionStage<U>, ghép phẳng kết quả |

**thenApply** biến T thành U. Nếu fn **trả CompletableFuture<U>**, kết quả trở thành **CompletableFuture<CompletableFuture<U>>**; khi đó thường cần **thenCompose** để tránh tương lai lồng nhau.

### 4.3 Kết hợp hai stage

| Non-async | Async với Executor | Khi nào kích hoạt |
| --- | --- | --- |
| **thenCombine(other, fn)** | **thenCombineAsync(other, fn, ex)** | Cả hai stage hoàn thành bình thường, lấy hai giá trị để tính U |
| **thenAcceptBoth(other, consumer)** | **thenAcceptBothAsync(other, consumer, ex)** | Cả hai hoàn thành bình thường, dùng hai kết quả |
| **runAfterBoth(other, action)** | **runAfterBothAsync(other, action, ex)** | Cả hai hoàn thành bình thường, chạy không cần giá trị |
| **applyToEither(other, fn)** | **applyToEitherAsync(other, fn, ex)** | Khi một stage hoàn thành bình thường đủ điều kiện |
| **acceptEither(other, consumer)** | **acceptEitherAsync(other, consumer, ex)** | Dùng kết quả thành công từ một stage |
| **runAfterEither(other, action)** | **runAfterEitherAsync(other, action, ex)** | Chạy sau một stage thành công theo hợp đồng |

Những API trên cũng có biến thể **Async không truyền Executor**; bảng chỉ hiển thị dạng ba tham số ở những phương thức kết hợp hai nguồn để nhấn mạnh lựa chọn executor.

Khi hai nhánh có thứ tự hoàn tất phụ thuộc scheduler, **không suy ra nhánh nào luôn thắng**. Với các phương thức **Either**, phải xem semantics hoàn thành bình thường/ngoại lệ theo Javadoc cụ thể, không coi chúng tự động là cơ chế lấy “kết quả thành công nhanh nhất” trong mọi trường hợp lỗi.

### 4.4 Xử lý kết quả và lỗi

| Non-async | Async với Executor | Công dụng |
| --- | --- | --- |
| **whenComplete(action)** | **whenCompleteAsync(action, ex)** | Quan sát cả thành công/lỗi; thông thường không đổi kết quả gốc |
| **handle(fn)** | **handleAsync(fn, ex)** | Có thể biến thành công hoặc lỗi thành kết quả U |
| **exceptionally(fn)** | **exceptionallyAsync(fn, ex)** | Phục hồi từ ngoại lệ bằng giá trị T |
| **exceptionallyCompose(fn)** | **exceptionallyComposeAsync(fn, ex)** | Phục hồi bằng một CompletionStage<T> khác |

Các biến thể **exceptionallyAsync** và **exceptionallyComposeAsync** có sẵn trên **Java 17**. Không nhầm chúng với **handleAsync**: handle nhận cả giá trị lẫn lỗi, trong khi exceptionally chỉ chạy khi stage phía trước hoàn thành ngoại lệ.

**Lưu ý:** khiComplete không phải cơ chế recover mặc định; nếu stage nguồn đã lỗi, khiComplete thường giữ trạng thái lỗi sau khi callback quan sát, trừ các trường hợp đặc biệt theo hợp đồng lỗi callback. Khi cần phục hồi, chọn handle/exceptionally phù hợp.

## 5. Executor được chọn ở mức nào trong một pipeline?

Quan sát chuỗi:

~~~java
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(this::load, ioExecutor)
            .thenApplyAsync(this::normalize, cpuExecutor)
            .thenComposeAsync(this::enrichAsync, cpuExecutor)
            .thenApply(this::format);
~~~

Đây là **đoạn minh họa trong một class có load/normalize/enrichAsync/format, ioExecutor và cpuExecutor**; không phải chương trình có thể biên dịch độc lập.

Thứ tự phân định:

1. **supplyAsync(..., ioExecutor)**: tác vụ **load** chạy qua ioExecutor.
2. **thenApplyAsync(..., cpuExecutor)**: callback **normalize** chạy qua cpuExecutor.
3. **thenComposeAsync(..., cpuExecutor)**: callback **enrichAsync** được dispatch qua cpuExecutor. Nếu enrichAsync tự trả một future tạo bằng **supplyAsync(..., networkExecutor)**, phần việc của future đó chạy tại **networkExecutor**.
4. **thenApply(this::format)**: không chọn executor riêng. Callback format có thể chạy trên thread hoàn tất giai đoạn trước, hoặc caller khác theo semantics non-async.

Không có “tính kế thừa executor vĩnh viễn” từ stage đầu. Dùng **supplyAsync(..., ioExecutor)** không có nghĩa mọi **thenApplyAsync(...)** phía sau mặc định dùng ioExecutor. Muốn bảo đảm từng bước quan trọng chạy trong pool nào thì **truyền Executor ở chính lời gọi của bước đó**.

### Dấu hiệu sai khi review

~~~java
CompletableFuture.supplyAsync(() -> fetch(), ioExecutor)
        .thenApplyAsync(data -> heavyCompute(data));
~~~

**heavyCompute** không mặc nhiên chạy trong ioExecutor; callback Async không có đối số Executor dùng default facility. Với workload CPU được cô lập, sửa thành:

~~~java
CompletableFuture.supplyAsync(() -> fetch(), ioExecutor)
        .thenApplyAsync(data -> heavyCompute(data), cpuExecutor);
~~~

Hai đoạn code là **minh họa**, giả sử fetch/heavyCompute và executor đã được khai báo. Điểm sửa không phải là “thêm Async”, mà là **đưa đúng executor vào đúng ranh giới**.

## 6. Java 17 chạy độc lập: mỗi biến thể dùng đúng executor

Ví dụ này **không phụ thuộc Spring**. Nó tạo hai executor một luồng có tên rõ ràng, rồi lần lượt thực thi **supplyAsync**, **thenApplyAsync**, **thenComposeAsync** và một nhánh nested future. Nó không khẳng định rằng Async luôn tạo thread mới; ở đây **chúng ta chủ động chọn hai ExecutorService** có worker riêng.

Tạo tệp **AsyncVariantsDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class AsyncVariantsDemo {
    private static ExecutorService namedSingleThread(String name) {
        return Executors.newSingleThreadExecutor(
                task -> new Thread(task, name));
    }

    public static void main(String[] args) throws Exception {
        Thread caller = Thread.currentThread();

        ExecutorService io = namedSingleThread("io-worker");
        ExecutorService cpu = namedSingleThread("cpu-worker");

        AtomicReference<String> sourceThread = new AtomicReference<>();
        AtomicReference<String> mapThread = new AtomicReference<>();
        AtomicReference<String> composeThread = new AtomicReference<>();
        AtomicReference<String> nestedThread = new AtomicReference<>();
        AtomicReference<String> finalThread = new AtomicReference<>();

        try {
            CompletableFuture<Integer> source =
                    CompletableFuture.supplyAsync(() -> {
                        sourceThread.set(Thread.currentThread().getName());
                        return 10;
                    }, io);

            CompletableFuture<String> pipeline = source
                    .thenApplyAsync(value -> {
                        mapThread.set(Thread.currentThread().getName());
                        return value * 2;
                    }, cpu)
                    .thenComposeAsync(value -> {
                        composeThread.set(Thread.currentThread().getName());
                        return CompletableFuture.supplyAsync(() -> {
                            nestedThread.set(
                                    Thread.currentThread().getName());
                            return value + 5;
                        }, io);
                    }, cpu)
                    .thenApplyAsync(value -> {
                        finalThread.set(Thread.currentThread().getName());
                        return "value=" + value;
                    }, cpu);

            String result = pipeline.get(5, TimeUnit.SECONDS);

            boolean nonAsyncOnCaller =
                    CompletableFuture.completedFuture(7)
                            .thenApply(x -> Thread.currentThread() == caller)
                            .join();

            System.out.println("Non-async trên caller: "
                    + nonAsyncOnCaller);
            System.out.println("supplyAsync: " + sourceThread.get());
            System.out.println("thenApplyAsync: " + mapThread.get());
            System.out.println("thenComposeAsync: " + composeThread.get());
            System.out.println("nested supplyAsync: " + nestedThread.get());
            System.out.println("final thenApplyAsync: " + finalThread.get());
            System.out.println("result: " + result);
        } finally {
            io.shutdown();
            cpu.shutdown();
            if (!io.awaitTermination(5, TimeUnit.SECONDS)) {
                io.shutdownNow();
            }
            if (!cpu.awaitTermination(5, TimeUnit.SECONDS)) {
                cpu.shutdownNow();
            }
        }
    }
}
~~~

Lệnh biên dịch và chạy (JDK 17+):

~~~bash
javac -encoding UTF-8 AsyncVariantsDemo.java
java AsyncVariantsDemo
~~~

**Stdout của chương trình**, nếu hai executor bình thường và task hoàn tất trong thời hạn test:

~~~text
Non-async trên caller: true
supplyAsync: io-worker
thenApplyAsync: cpu-worker
thenComposeAsync: cpu-worker
nested supplyAsync: io-worker
final thenApplyAsync: cpu-worker
result: value=25
~~~

Phân tích từng kết quả:

- **sourceThread** là io-worker vì supplier gốc được giao **io**.
- **mapThread** là cpu-worker vì biến thể **thenApplyAsync** chỉ định **cpu**.
- **composeThread** là cpu-worker vì chính **hàm tạo CompletionStage** được dispatch tới **cpu**.
- **nestedThread** quay lại io-worker vì **hàm trả về một CompletableFuture mới** thông qua **supplyAsync(..., io)**. Executor của thenComposeAsync **không điều khiển công việc bên trong nested future**.
- **finalThread** là cpu-worker do last thenApplyAsync chỉ định cpu.
- **result** bằng value=25 vì 10 × 2 + 5.
- Phép thử **completedFuture(7).thenApply(...)** chạy callback ngay khi đăng ký trên caller của ví dụ, cho kết quả **true**. Điều đó không phải một cam kết cho mọi future chưa hoàn tất.

Chương trình chỉ in sau khi đã **get(timeout)** kết quả cuối nên không phụ thuộc thứ tự log giữa worker. Những tên worker được **ThreadFactory** cấu hình tường minh. Các AtomicReference được đọc sau khi future hoàn tất, bảo đảm có thể thấy giá trị đã được ghi trong những stage tương ứng.

**Giới hạn đo lường:** ví dụ chứng minh **giai đoạn nào được chuyển sang executor nào trong cấu hình cụ thể**, không phải benchmark throughput. Executor single-thread trong ví dụ nhằm dễ giải thích và kiểm chứng; không nên bê nguyên giới hạn 1 worker vào production mà không đánh giá workload.

## 7. thenApplyAsync khác thenComposeAsync thế nào?

Xét một hàm gọi dịch vụ trả về một future:

~~~java
CompletableFuture<User> loadUserAsync(String id) {
    return CompletableFuture.supplyAsync(
            () -> queryUser(id), ioExecutor);
}
~~~

Đây là **đoạn method minh họa** với User, queryUser và ioExecutor được định nghĩa ở ứng dụng. Khi muốn load user sau khi đã lấy id:

~~~java
CompletableFuture<String> idFuture = /* stage nguồn */;

// Tạo một future lồng trong future:
CompletableFuture<CompletableFuture<User>> nested =
        idFuture.thenApplyAsync(
                id -> loadUserAsync(id),
                cpuExecutor);

// Ghép phẳng để nhận một future của User:
CompletableFuture<User> flat =
        idFuture.thenComposeAsync(
                id -> loadUserAsync(id),
                cpuExecutor);
~~~

**thenApplyAsync** chấp nhận hàm **T → U**. Nếu U là CompletableFuture<User>, kết quả là **CompletableFuture<CompletableFuture<User>>**.

**thenComposeAsync** chấp nhận hàm **T → CompletionStage<U>**, rồi tạo một stage phụ thuộc phản ánh **kết quả eventual** của stage được hàm trả về. Nhờ vậy ta nhận **CompletableFuture<User>** thay vì tương lai lồng nhau.

Trong mã này **cpuExecutor chạy hàm gọi loadUserAsync**. Nhưng chính loadUserAsync bên trong tạo tác vụ qua **supplyAsync(..., ioExecutor)** nên queryUser được thực thi trên **ioExecutor**. Đây là nơi nhiều người nhầm giữa **executor của callback tạo future** và **executor của công việc mà future mô tả**.

Một cách viết khác có thể hợp lý nếu hàm tạo future chỉ thực hiện thao tác rất nhẹ:

~~~java
CompletableFuture<User> flat =
        idFuture.thenCompose(id -> loadUserAsync(id));
~~~

Ở đây việc tạo/đăng ký future không được dispatch riêng, nhưng queryUser **vẫn có thể chạy ở ioExecutor** vì loadUserAsync tự dùng supplyAsync với ioExecutor. Nếu hàm thenCompose chỉ khởi tạo future và không blocking, cách này có thể tránh thêm một lần chuyển thread không cần thiết.

**Tóm lại:** chọn **thenApply(Async)** khi biến đổi giá trị, chọn **thenCompose(Async)** khi hàm trả về một **CompletionStage**. Quyết định **Async hay non-async** cho phần hàm callback là một quyết định khác với **Apply hay Compose**.

## 8. thenCombineAsync: kết hợp hai công việc độc lập

Giả sử cần tính một mức giá từ hai nguồn độc lập:

~~~java
CompletableFuture<Integer> baseFuture =
        CompletableFuture.supplyAsync(
                () -> loadBasePrice(), ioExecutor);

CompletableFuture<Integer> feeFuture =
        CompletableFuture.supplyAsync(
                () -> loadFee(), ioExecutor);

CompletableFuture<Integer> totalFuture =
        baseFuture.thenCombineAsync(
                feeFuture,
                (base, fee) -> base + fee,
                cpuExecutor);
~~~

Đây là **đoạn minh họa trong ứng dụng** đã định nghĩa loadBasePrice/loadFee và executors. Hai future nguồn có thể cùng tiến triển, phụ thuộc khả năng executor và tài nguyên downstream. Hàm cộng chỉ được thực thi sau khi cả hai stage hoàn thành bình thường, trên **cpuExecutor**.

Nếu chỉ cần cộng hai số, callback thực tế rất nhẹ; **thenCombine** không Async cũng có thể đủ. Chỉ định executor sẽ có giá trị khi phần kết hợp thực sự **tốn CPU**, yêu cầu **thread affinity** hoặc cần tách workload.

### allOf và anyOf không phải các overload Async với Executor

**CompletableFuture.allOf(f1, f2, ...)** tạo một future tổng hợp hoàn tất khi các future đầu vào đã hoàn tất; nó **không trả danh sách các giá trị**. Bạn vẫn đọc từng result từ những future gốc sau khi điều kiện hoàn tất được bảo đảm.

~~~java
CompletableFuture<Void> all =
        CompletableFuture.allOf(baseFuture, feeFuture);

CompletableFuture<Integer> total = all.thenApplyAsync(
        ignored -> baseFuture.join() + feeFuture.join(),
        cpuExecutor);
~~~

Đây là **đoạn minh họa** với hai future trả Integer. Khi all hoàn tất **bình thường**, các future thành viên đã hoàn tất bình thường nên join trong callback không phải đợi chúng tiếp tục chạy. Nếu một future đầu vào lỗi, all cũng có thể hoàn tất ngoại lệ và thenApplyAsync không chạy; caller phải xử lý nhánh lỗi riêng.

**allOf** bản thân **không có tham số Executor**. Nếu muốn chạy bước hậu xử lý ở pool cụ thể, chọn **thenApplyAsync/thenRunAsync/... với Executor** trên future tổng hợp. **anyOf** trả một tương lai có kiểu giá trị **Object** và hoàn tất theo future thành viên hoàn tất trước; nó cũng không phải cú pháp để cấu hình executor chạy mọi nhánh đầu vào.

Đừng nghĩ rằng **allOf** tự mở một pool hoặc tự chạy lại các tác vụ. Nó chỉ **kết hợp completion** của những future đã có.

## 9. Biến thể Async của bước cuối và xử lý lỗi

### thenAcceptAsync và thenRunAsync

~~~java
CompletableFuture<Order> orderFuture = /* future hợp lệ */;

CompletableFuture<Void> audit =
        orderFuture.thenAcceptAsync(
                order -> auditOrder(order),
                auditExecutor);

CompletableFuture<Void> cleanup =
        audit.thenRunAsync(
                () -> markAuditComplete(),
                auditExecutor);
~~~

**thenAcceptAsync** nhận Order và trả stage Void. **thenRunAsync** không nhận Order/result đầu vào, chỉ chạy sau khi upstream thành công. Hai bước được yêu cầu chạy qua **auditExecutor**, với điều kiện executor nhận việc.

**Lưu ý:** một hành động side effect như audit phải có quy tắc idempotency và lỗi rõ ràng. Nếu audit có tính bắt buộc, đừng coi một callback in-memory đã đăng ký là xác nhận công việc được lưu bền vững.

### whenCompleteAsync và handleAsync

~~~java
CompletableFuture<String> observed =
        sourceFuture.whenCompleteAsync(
                (value, error) -> logOutcome(value, error),
                logExecutor);

CompletableFuture<String> recovered =
        sourceFuture.handleAsync(
                (value, error) -> error == null
                        ? value
                        : "fallback",
                recoveryExecutor);
~~~

Đây là **đoạn minh họa** với sourceFuture, logOutcome và executors đã tồn tại. **whenCompleteAsync** phù hợp để quan sát/log và thường giữ kết quả hoặc lỗi gốc; **handleAsync** trả một giá trị mới nên có thể chuyển một exceptional completion thành kết quả bình thường, nếu logic cho phép.

### exceptionallyAsync và exceptionallyComposeAsync

Java 17 có các API:

~~~java
CompletableFuture<String> recoveredValue =
        sourceFuture.exceptionallyAsync(
                error -> "fallback",
                recoveryExecutor);

CompletableFuture<String> recoveredStage =
        sourceFuture.exceptionallyComposeAsync(
                error -> fetchFromBackupAsync(),
                recoveryExecutor);
~~~

**exceptionallyAsync** tạo giá trị phục hồi khi có lỗi. **exceptionallyComposeAsync** gọi hàm sinh một **CompletionStage<String>** khác và ghép kết quả của stage đó. Trong ví dụ thứ hai, **recoveryExecutor** được dùng để chạy hàm tạo stage backup; future được hàm **fetchFromBackupAsync()** trả về vẫn tuân theo executor/cơ chế riêng của nó.

Đừng dùng fallback chung để che mọi lỗi nghiệp vụ. Ví dụ, lỗi phân quyền hoặc request không hợp lệ thường không nên biến thành một dữ liệu hợp lệ giả. Phân loại exception/cause trước khi quyết định phục hồi hoặc retry.

**Phân biệt lỗi scheduler và lỗi task:** một task có thể được executor **từ chối trước khi chạy**; hoặc đã chạy rồi gặp exception. Cách lỗi xuất hiện với CompletableFuture phụ thuộc chính API và **thời điểm** bị reject; cần xử lý cả đường submit/đăng ký và future exceptional completion, không mặc định mọi lỗi đều đợi được bằng exceptionally.

## 10. Chọn Executor nào? Phân biệt CPU-bound, I/O-bound và downstream

Một ứng dụng có thể chọn nhiều executor, thay vì dồn mọi giai đoạn vào một pool:

| Workload | Ví dụ | Hướng chọn executor |
| --- | --- | --- |
| CPU-bound | tính điểm lớn, chuyển đổi dữ liệu nặng, nén | Worker pool hữu hạn theo khả năng CPU; tránh oversubscribe quá mạnh |
| Blocking I/O | HTTP client đồng bộ, driver DB blocking, file access | Worker riêng có giới hạn đồng thời phù hợp connection pool và timeout |
| Log/metrics nhẹ | thống kê, ghi log không chặn quá lâu | Thường không cần chuyển executor cho từng phép toán; chọn hệ thống telemetry phù hợp |
| Tác vụ bắt buộc lưu/đảm bảo | job thanh toán, gửi email quan trọng | Durable queue/job store hoặc outbox, không tin chỉ Future trong RAM |
| Logic phối hợp future | nối stage, ghép kết quả, chọn fallback | Non-async nếu thật sự nhẹ; Async có executor nếu cần cô lập/affinity |

Không có quy tắc “I/O pool luôn phải có N thread” đúng cho mọi hệ thống. Nếu database chỉ cho 10 connection đồng thời, cho 1.000 blocking DB tasks chạy trên 1.000 platform threads có thể làm tăng chờ và bộ nhớ mà không tăng throughput. **CPU pool cũng không tự tăng năng lực tính toán bằng cách tăng vô hạn số worker**.

### ThreadPoolTaskExecutor của Spring

**ThreadPoolTaskExecutor** có thể được dùng như một **Executor** chuẩn để truyền vào **CompletableFuture.*Async(..., executor)**. Nó có các thông số:

- **corePoolSize**: số worker cốt lõi.
- **maxPoolSize**: số worker tối đa.
- **queueCapacity**: dung lượng lưu task chờ; **0** chọn SynchronousQueue / handoff trực tiếp.
- **threadNamePrefix**: tên worker cho logging/debug.
- **RejectedExecutionHandler**: xử lý khi không thể nhận thêm tác vụ.
- Các tùy chọn **shutdown/lifecycle** cần phù hợp yêu cầu của ứng dụng.

Một queue quá lớn có thể tích tụ backlog và khiến maxPoolSize ít khi có cơ hội tăng. Một queue bằng 0 có thể làm pool mở rộng nhanh hơn đến max nhưng cũng reject sớm hơn. Chọn thông số theo lượng tải, SLA, deadline và resource downstream; không lấy giá trị ví dụ trong bài làm cấu hình production mặc định.

## 11. Spring @Async và CompletableFuture: hai tầng dispatch khác nhau

Spring **@Async** cho phép **Spring AOP/interceptor** chuyển việc thực thi method vào một executor. Một phương thức có **@Async("ioExecutor")** dùng executor theo tên bean/qualifier được chỉ định để chạy **phần thân method** qua cơ chế Spring. Điều đó **không thay đổi mặc định của CompletableFuture.thenApplyAsync(...)** ở các giai đoạn downstream.

Sơ đồ:

~~~text
Caller thread
   |
   +-- Spring proxy: @Async("ioExecutor")
   |          |
   |          +-- ioExecutor chạy body of service.load()
   |                       |
   |                       +-- trả kết quả CompletableFuture
   |
   +-- nhận CompletableFuture từ proxy
              |
              +-- thenApplyAsync(fn, cpuExecutor)
              |          |
              |          +-- CPU executor chạy fn
              |
              +-- thenApplyAsync(fn)  [không truyền executor]
                         |
                         +-- default async facility của CF
                             (thường là commonPool, không phải ioExecutor)
~~~

Với **@Async** chuẩn, một method cần return type hỗ trợ như **void**, **Future** hoặc **CompletableFuture** theo hợp đồng Spring. Nếu trong body method đã được Spring dispatch tới ioExecutor và tính toán đã xong, có thể trả **CompletableFuture.completedFuture(value)**. Caller sẽ nhận future do Spring proxy cung cấp để theo dõi phần thực thi bất đồng bộ.

**Không nhất thiết gọi supplyAsync thêm bên trong @Async method.** Nếu viết @Async("ioExecutor") rồi trong body lại **supplyAsync(..., cpuExecutor)** mà không có chủ đích, bạn tạo thêm một tầng scheduling, có thể làm khó việc truyền context, tính thời gian, quan sát lỗi và shutdown.

### Cấu hình hai executor Spring, chọn tường minh cho từng công đoạn

Ví dụ ứng dụng Spring dưới đây dùng:

- Bean **ioExecutor** cho body của **@Async**.
- Bean **cpuExecutor** làm tham số của **thenApplyAsync**.
- Hai pool chỉ có một worker để kiểm chứng đường chạy, **không phải kích cỡ nên dùng ở production**.

Cấu trúc thư mục Maven:

~~~text
spring-explicit-executor/
├── pom.xml
└── src/main/java/example/SpringAsyncSelectionDemo.java
~~~

**pom.xml** (Spring Framework 6.2.12 và Java 17):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-explicit-executor</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.SpringAsyncSelectionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/example/SpringAsyncSelectionDemo.java**:

~~~java
package example;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class SpringAsyncSelectionDemo {
    private static final AtomicReference<String> ioThread =
            new AtomicReference<>();
    private static final AtomicReference<String> cpuThread =
            new AtomicReference<>();

    @Configuration
    @EnableAsync
    public static class Config {
        @Bean("ioExecutor")
        public ThreadPoolTaskExecutor ioExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(10);
            pool.setThreadNamePrefix("io-");
            return pool;
        }

        @Bean("cpuExecutor")
        public ThreadPoolTaskExecutor cpuExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(10);
            pool.setThreadNamePrefix("cpu-");
            return pool;
        }

        @Bean
        public ReportWorker reportWorker() {
            return new ReportWorker();
        }

        @Bean
        public ReportPipeline reportPipeline(
                ReportWorker worker,
                @Qualifier("cpuExecutor") Executor cpuExecutor) {
            return new ReportPipeline(worker, cpuExecutor);
        }
    }

    public static class ReportWorker {
        @Async("ioExecutor")
        public CompletableFuture<Integer> load(int value) {
            ioThread.set(Thread.currentThread().getName());
            return CompletableFuture.completedFuture(value + 1);
        }
    }

    public static class ReportPipeline {
        private final ReportWorker worker;
        private final Executor cpuExecutor;

        public ReportPipeline(ReportWorker worker, Executor cpuExecutor) {
            this.worker = worker;
            this.cpuExecutor = cpuExecutor;
        }

        public CompletableFuture<Integer> run(int value) {
            return worker.load(value)
                    .thenApplyAsync(loaded -> {
                        cpuThread.set(Thread.currentThread().getName());
                        return loaded * 2;
                    }, cpuExecutor);
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            int result = context.getBean(ReportPipeline.class)
                    .run(10)
                    .get(5, TimeUnit.SECONDS);

            System.out.println("ioExecutor đúng: "
                    + ioThread.get().startsWith("io-"));
            System.out.println("cpuExecutor đúng: "
                    + cpuThread.get().startsWith("cpu-"));
            System.out.println("Kết quả: " + result);
        }
    }
}
~~~

Chạy:

~~~bash
mvn -q compile exec:java
~~~

**Stdout của chương trình** (không tính log của Maven/Spring, phụ thuộc môi trường):

~~~text
ioExecutor đúng: true
cpuExecutor đúng: true
Kết quả: 22
~~~

Giải thích:

1. **@EnableAsync** bật việc phát hiện **@Async**. Bean ReportWorker do Spring quản lý, method load là **public**, không final và được **ReportPipeline** (bean khác) gọi qua dependency Spring inject, cho phép async proxy hoạt động.
2. **@Async("ioExecutor")** yêu cầu Spring đưa **body của load** lên pool ioExecutor. Body ghi lại tên worker, tính 10 + 1 = 11 rồi trả **completedFuture(11)**; interceptor tạo future phù hợp cho caller.
3. ReportPipeline đăng ký **thenApplyAsync(..., cpuExecutor)**, nên phép nhân 11 × 2 được xử lý qua pool cpuExecutor.
4. **get(timeout)** được gọi ở main để chờ hoàn tất, sau đó mới in; vì vậy log kết quả không phụ thuộc thứ tự thực thi worker.
5. Hai tên thread đều xuất phát từ **setThreadNamePrefix**, và code kiểm tra tiền tố thay vì đoán số thứ tự worker.
6. Các bean ThreadPoolTaskExecutor được Spring quản lý và khởi tạo trong context; khi context đóng, vòng đời executor được container điều phối. Trong chương trình thuần Java phải đóng ExecutorService chủ động.

Đây là **ví dụ kỹ thuật tự chứa trong một dự án Maven có dependencies phù hợp**. Nó minh họa hai tầng chọn executor độc lập, không phải bộ khung production hoàn chỉnh về bảo mật, timeout, metrics và xử lý lỗi.

## 12. Chọn executor qua @Async, qualifier và AsyncConfigurer

Có nhiều mức lựa chọn trong Spring:

**A. Chỉ định trực tiếp ở method:**

~~~java
@Async("ioExecutor")
public CompletableFuture<Data> read() {
    return CompletableFuture.completedFuture(loadData());
}
~~~

Đây là **đoạn minh họa method** trong bean Spring. Chuỗi **ioExecutor** phải khớp bean name hoặc qualifier mà Spring có thể resolve thành một Executor/TaskExecutor.

**B. Chỉ định ở class:**

~~~java
@Async("ioExecutor")
public class ExternalApiWorker {
    public CompletableFuture<String> call() {
        return CompletableFuture.completedFuture("ok");
    }
}
~~~

Đây là **đoạn minh họa class** (còn cần đăng ký bean), không phải full application. Method-level **@Async("otherExecutor")** có thể **ghi đè qualifier ở class-level** theo cơ chế Spring.

**C. Cấu hình mặc định của async support:**

Có thể dùng **AsyncConfigurer** trong Spring để cung cấp executor mặc định cho những method **@Async không có qualifier**, hoặc để cấu hình xử lý ngoại lệ cho async void. Tên bean tự chọn theo quy tắc framework cũng có thể ảnh hưởng lựa chọn nếu không định rõ. Không nên trộn các cách này rồi suy ra executor thực tế chỉ từ tên annotation.

**D. Chỉ định ở từng callback CompletableFuture:**

~~~java
return worker.load()
        .thenApplyAsync(this::transform, cpuExecutor)
        .thenComposeAsync(this::saveAsync, ioExecutor);
~~~

Đây là **đoạn minh họa method có các dependency**; chính đối số Executor cho từng Async callback mới quyết định nơi callback tương ứng được dispatch. Qualifier **@Async("ioExecutor")** trên worker.load **không thay thế** hai đối số đó.

**Kết luận tổ chức:** chọn executor của method Spring bằng **@Async("...")**, chọn executor của callback CompletionStage bằng **biến thể Async có đối số Executor**, và kiểm tra bean names/qualifiers bằng integration test.

## 13. Executor tường minh không tự truyền ThreadLocal, MDC và security context

Nhiều dữ liệu trong Spring gắn với thread đang xử lý request, ví dụ:

- **MDC** dùng trong logging.
- **SecurityContext** theo chiến lược giữ context hiện tại.
- **RequestContextHolder** và request attributes.
- **Transaction/persistence context** liên kết với transaction của thread.
- Các ThreadLocal ứng dụng tự viết.

Khi chuyển từ **request thread** sang **ioExecutor** rồi tiếp tục sang **cpuExecutor**, ngữ cảnh đó **không mặc nhiên đi theo mọi bước**. Việc dùng tên executor chính xác giúp kiểm soát tài nguyên, nhưng không phải tự động kích hoạt context propagation.

Ví dụ lỗi dễ gặp:

~~~java
CompletableFuture<String> future = CompletableFuture
        .supplyAsync(() -> callRemote(), ioExecutor)
        .thenApplyAsync(value -> {
            // Đừng tự giả định MDC, Principal hay transaction
            // từ HTTP request thread hiện có ở đây.
            return process(value);
        }, cpuExecutor);
~~~

Đây là **đoạn minh họa**, không phải đoạn chạy độc lập.

Thiết kế phù hợp:

1. **Dữ liệu nghiệp vụ**: tạo immutable snapshot từ input cần thiết trước khi gửi task.
2. **Logging/tracing**: sử dụng cơ chế context propagation chính thức của stack Spring/Micrometer hoặc **TaskDecorator** được cấu hình đúng; phải làm sạch/khôi phục context sau callback khi worker được tái sử dụng.
3. **Bảo mật**: cân nhắc các wrapper/delegating executor của Spring Security hoặc xác thực/ủy quyền lại tại nơi thực hiện thao tác quan trọng. Không chia sẻ bừa toàn bộ principal/token.
4. **Transaction**: transaction ở request thread không tự mở rộng qua Async stage. Mở transaction phù hợp với thao tác ở worker, thường qua service bean giao dịch đúng proxy.
5. **Đổi executor nhiều lần**: nếu pipeline có nhiều ranh giới io → cpu → io, phải xét propagation và cleanup ở **từng ranh giới**, không chỉ stage đầu.

**Không dùng field mutable của singleton bean để giả lập request context xuyên luồng.** Điều đó khiến nhiều request có thể ghi đè thông tin của nhau.

## 14. Quá tải và rejection ở các giai đoạn Async

Khi gọi Async với Executor tường minh, stage phụ thuộc có thể **không được lên lịch** nếu executor đã shutdown hoặc bão hòa. Ví dụ **ThreadPoolTaskExecutor** có hàng đợi hữu hạn và worker giới hạn có thể ném **TaskRejectedException** theo hợp đồng Spring; JDK **ThreadPoolExecutor** thường biểu hiện từ chối qua **RejectedExecutionException**.

Phân biệt:

| Vấn đề | Xảy ra ở đâu | Cách xử lý |
| --- | --- | --- |
| Không chấp nhận task | Lúc submit/schedule một stage | Bắt lỗi có thể xảy ra ở đường gọi; quan sát exceptional completion khi API đó báo qua future; xác định retry/overload |
| Lỗi trong supplier/function | Sau khi stage được nhận và chạy | Future tương ứng hoàn tất exceptional; dùng handle/exceptionally/whenComplete |
| Task bị chờ lâu trong queue | Sau khi được nhận nhưng chưa chạy | Deadline/timeout, metric queue wait, giới hạn backlog |
| Bị block do join/get | Thread gọi join/get | Tránh blocking trong worker có năng lực hữu hạn; thiết kế compose |
| Callback bị chạy ở caller | Direct Executor hoặc CallerRunsPolicy | Không được giả định Async luôn giữ caller rảnh |

**Một điểm rất dễ nhầm:** nếu gọi **thenApplyAsync(fn, executor)** khi stage nguồn **đã hoàn tất**, implementation có thể cố schedule callback **ngay trong lời gọi đăng ký**. Nếu executor không tiếp nhận, kết quả có thể xuất hiện khác với trường hợp stage nguồn **chỉ hoàn tất sau đó** và lời từ chối xảy ra khi future đang kích hoạt dependent action. Không nên khẳng định mọi rejection đều luôn xảy ra trong một Future hay luôn ném ngay tại cùng một dòng trong mọi implementation. Viết test cho executor và API thực tế, xử lý cả submit boundary lẫn exceptional completion.

**Với @Async**, việc Spring proxy gửi method vào executor còn là một ranh giới riêng; **TaskRejectedException** có thể được caller nhận **trước khi một CompletableFuture được trả về**. Nếu task đã được nhận nhưng body lỗi, future là nơi theo dõi exceptional completion.

### Rejection policy không phải cách “để hết lỗi”

- **AbortPolicy**: từ chối bằng ngoại lệ, giúp quan sát saturation.
- **CallerRunsPolicy**: khi chưa shutdown, có thể chạy task trên thread gửi, làm các hàm Async thực thi ở caller trong trường hợp quá tải.
- **DiscardPolicy/DiscardOldestPolicy**: có nguy cơ mất công việc hoặc tạo Future không bao giờ hoàn tất nếu không quản lý trạng thái task bị bỏ.

Một backend cần xác định rõ liệu task có được phép mất hay không. Nếu không được mất, executor nội bộ trong RAM **không thay thế durable job queue/outbox**; phải có trạng thái tiếp nhận bền vững và retry/idempotency phù hợp.

## 15. Tránh deadlock và starvation khi dùng cùng một pool

Một lỗi phổ biến: gửi một task vào **executor chỉ có một worker**, rồi **ngay bên trong task đó** lại gửi task phụ vào **cùng executor** và **join()** để đợi:

~~~java
ExecutorService oneWorker = Executors.newSingleThreadExecutor();

CompletableFuture<Integer> result =
        CompletableFuture.supplyAsync(() -> {
            CompletableFuture<Integer> nested =
                    CompletableFuture.supplyAsync(() -> 42, oneWorker);
            return nested.join(); // Rủi ro deadlock!
        }, oneWorker);
~~~

Đây là **đoạn minh họa nguy hiểm**, không phải chương trình nên chạy: nếu worker thứ nhất đang chờ nested.join(), nested task nằm trong hàng đợi và không có worker thứ hai để xử lý. Đừng chạy ví dụ này mà không có cơ chế hủy/timeout bên ngoài; nó có thể treo.

Thay bằng composition **không block trong worker**:

~~~java
CompletableFuture<Integer> result =
        CompletableFuture.supplyAsync(() -> 10, oneWorker)
                .thenComposeAsync(
                        n -> CompletableFuture.supplyAsync(
                                () -> n + 32, oneWorker),
                        oneWorker);
~~~

Đây là **đoạn minh họa**. thenComposeAsync chạy hàm tạo future mới trong executor, nhưng nó **không join đợi future bên trong ngay khi đang giữ worker**; worker có thể nhả quyền chạy để task nested được thực hiện sau. Với một worker, hai task có thể lần lượt hoàn thành mà không tự giữ worker để chờ nhau.

Dù vậy, **không phải cứ thêm thenCompose là mọi hệ thống không thể deadlock**. Vẫn cần xem lock, database connection, transaction, lô task khác, queue và exception. Mấu chốt là **không block một worker trên công việc bắt buộc phải lấy cùng worker đó để tiến triển**.

### Join/get thuộc về tầng nào?

- **get(timeout)** trên thread phối hợp ở biên có thể hữu ích để chờ kết quả có deadline.
- **join()** bên trong task chạy trên pool nhỏ dễ tăng khả năng bão hòa và làm mất lợi ích của pipeline bất đồng bộ.
- **thenCompose** chuyển mối quan hệ “chờ stage phụ” thành **composition** mà không cần worker chủ động đợi trong lời gọi join.
- Nếu bắt buộc block vì API ngoài chỉ đồng bộ, phân bổ pool phù hợp và đặt timeout rõ ràng, không giả vờ nó là nonblocking.

## 16. Timeouts, delayedExecutor và lựa chọn executor

Java 17 có các tiện ích:

- **orTimeout(timeout, unit)**: nếu future chưa hoàn thành trước deadline thì làm future đó hoàn thành ngoại lệ TimeoutException theo hợp đồng.
- **completeOnTimeout(value, timeout, unit)**: làm future hoàn thành bằng giá trị fallback nếu quá hạn.
- **delayedExecutor(delay, unit, executor)**: tạo một Executor adapter trì hoãn thời điểm **giao task cho executor được chỉ định**.
- **CompletableFuture.copy()** và **minimalCompletionStage()**: hỗ trợ kiểm soát cách bên ngoài truy cập/hoàn tất stage trong API thiết kế thư viện; không phải lựa chọn thread cho callback.

**orTimeout** và **completeOnTimeout** không có tham số Executor riêng để chọn nơi chạy code nghiệp vụ; chúng tác động trạng thái completion và không đồng nghĩa việc task nguồn bị interrupt/hủy ngay khi timeout xảy ra.

Ví dụ trì hoãn một tác vụ:

~~~java
Executor delayed = CompletableFuture.delayedExecutor(
        200, TimeUnit.MILLISECONDS, ioExecutor);

CompletableFuture<String> future =
        CompletableFuture.supplyAsync(() -> "ok", delayed);
~~~

Đây là **đoạn code minh họa** với ioExecutor, TimeUnit và Executor đã import. Executor adapter trì hoãn rồi chuyển task tới **ioExecutor**. Nó **không nói rằng callback sau future tự kế thừa ioExecutor**. Nếu sau đó cần transform trong cpuExecutor, viết **thenApplyAsync(fn, cpuExecutor)**.

**Deadline nghiệp vụ** có thể bao gồm thời gian queue wait + execution + retry. Một CompletableFuture timeout sau 2 giây không tự giải phóng DB connection đang bị blocking I/O kéo dài; tài nguyên I/O cần timeout/cancellation riêng.

## 17. Kiểm thử việc chọn executor một cách xác định

Không nên chứng minh Async bằng cách đo **Thread.sleep(50)** rồi nhìn thứ tự in log. Hãy thiết kế test theo điều bạn cần xác minh:

**Kiểm thử phân định pool:**

1. Tạo hai ExecutorService có ThreadFactory đặt tên rõ hoặc lưu **Thread identity** trong AtomicReference.
2. Chạy **supplyAsync(..., ioExecutor)** và **thenApplyAsync(..., cpuExecutor)**.
3. Chờ future cuối với **get(timeout)**.
4. Assert supplier/callback đã chạy trên thread/executor được cấu hình.
5. Đóng pool trong finally để test không rò rỉ worker.

**Kiểm thử non-async:**

1. Tạo completedFuture đã hoàn tất.
2. Gọi thenApply và đối chiếu Thread.currentThread() tại callback với caller.
3. Để kiểm thử khả năng non-async chạy khi stage hoàn tất sau, dùng **CountDownLatch** điều phối, không đoán thứ tự thực thi.
4. Không biến một trường hợp kiểm thử thành “quy luật mọi non-async luôn chạy trên caller”.

**Kiểm thử @Async và proxy:**

1. Dùng **ApplicationContext**, không **new ReportWorker()** trực tiếp.
2. Bật **@EnableAsync**; gọi method **qua Spring proxy từ bean khác**.
3. Tránh self-invocation **this.load()**, method private/final không phù hợp với kiểu proxy.
4. Đo thread chạy body và thread chạy bước **thenApplyAsync(..., cpuExecutor)** tách biệt.
5. Kiểm thử khi executor bão hòa/shutdown, phân biệt **TaskRejectedException tại submit** và future exceptional completion.

**Kiểm thử overload:**

- Cấu hình pool có worker/queue hữu hạn.
- Giữ task đang chạy bằng **CountDownLatch**, chờ xác nhận các worker đã bắt đầu.
- Submit thêm task tới lúc bão hòa, assert hành vi Abort/CallerRuns theo cấu hình.
- Luôn release latch/cleanup trong finally.
- Theo dõi số task rejected, queue wait, pool active và tác động response latency.

## 18. Những lỗi hiểu nhầm thường gặp

**“Async luôn tạo thread mới.”** Sai. CompletableFuture.*Async gọi một Executor; executor có thể tái sử dụng worker, chạy trực tiếp hoặc CallerRuns khi quá tải.

**“thenApply và thenApplyAsync chỉ khác về tên, kết quả như nhau nên không quan trọng.”** Sai. Khác biệt ở lựa chọn thread và tác động latency/saturation/context, dù giá trị cuối có thể giống.

**“supplyAsync(..., ioExecutor) buộc mọi thenApplyAsync sau đó dùng ioExecutor.”** Sai. Mỗi Async callback không truyền executor sử dụng default asynchronous facility; phải truyền executor ở từng ranh giới muốn kiểm soát.

**“thenComposeAsync(..., cpuExecutor) chạy tất cả future mà hàm trả về trong cpuExecutor.”** Sai. cpuExecutor chạy hàm callback tạo CompletionStage, còn future trả về có thể dùng executor riêng.

**“@Async("ioExecutor") khiến CompletableFuture.thenApplyAsync() tự dùng ioExecutor.”** Sai. Spring @Async và JDK CompletableFuture có cơ chế cấu hình khác nhau.

**“thenComposeAsync luôn tốt hơn thenCompose.”** Sai. Nếu hàm tạo future rất nhẹ và không block, thenCompose non-async có thể tránh scheduling bổ sung. Đánh giá nhu cầu thực sự.

**“thenApplyAsync làm phép tính CPU nặng nhanh hơn nếu tăng số thread vô hạn.”** Sai. CPU vẫn có giới hạn core/cache và overhead scheduling; cần đo throughput/latency.

**“allOf sẽ tự chạy mọi input future trên executor truyền vào.”** Sai. allOf chỉ kết hợp completion; các input futures phải được khởi tạo/chạy theo cơ chế riêng.

**“join/get bên trong worker pool chỉ là cách viết gọn, không ảnh hưởng concurrency.”** Sai. Blocking có thể gây starvation/deadlock, nhất là khi task phụ cần cùng một pool.

**“@Async luôn trả về ngay mà caller không bao giờ chặn.”** Không chắc. CallerRunsPolicy hoặc lỗi ở submit có thể ảnh hưởng; sau đó caller cũng có thể tự gọi join/get để chờ.

**“Exception trong pipeline và rejection ở submit có thể xử lý bằng đúng một exceptionally.”** Không nên giả định. Rejection có thể xảy ra trước khi một future được tạo/trả về hoặc khi scheduling dependent callback; phải kiểm tra API thực tế.

**“orTimeout tự hủy task gốc và giải phóng mọi I/O resource.”** Sai. Nó thay đổi completion semantics của future; việc ngắt/cancel/timeout operation cần thiết kế riêng.

**“Executor tường minh có nghĩa MDC, SecurityContext và transaction luôn đi theo.”** Sai. Context propagation là vấn đề khác, phải có cơ chế chuyên dụng và cleanup.

**“Future trả về 202 Accepted nghĩa là job đã lưu bền vững.”** Sai. CompletableFuture không phải durable queue và không bảo đảm sống qua restart.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Gọi **thenApplyAsync(fn)** không truyền Executor trong một CompletableFuture chuẩn. Có chắc dùng ThreadPoolTaskExecutor của Spring không?

**Đáp án:** Không. Nó dùng default asynchronous execution facility của CompletableFuture, thường là ForkJoinPool.commonPool().

**Câu 2.** Gọi **thenApplyAsync(fn, cpuExecutor)** sau **supplyAsync(supplier, ioExecutor)**. Supplier và fn có bắt buộc dùng cùng executor không?

**Đáp án:** Không. Supplier được gửi tới ioExecutor; fn được gửi tới cpuExecutor.

**Câu 3.** Một **thenApply(fn)** non-async đứng sau future chưa hoàn tất. Có chắc fn chạy trên caller tạo chuỗi không?

**Đáp án:** Không. fn có thể chạy trên thread hoàn tất upstream hoặc caller khác liên quan completion; không có thread affinity mặc định.

**Câu 4.** Hàm tạo stage trong **thenComposeAsync(fn, cpuExecutor)** trả về **supplyAsync(..., ioExecutor)**. Công việc nested chạy ở đâu?

**Đáp án:** fn chạy qua cpuExecutor; phần supplier của future được trả về chạy qua ioExecutor.

**Câu 5.** Nếu fn trả về CompletableFuture<User>, nên dùng **thenApply** hay **thenCompose** để có **CompletableFuture<User>**?

**Đáp án:** thenCompose; thenApply sẽ tạo future lồng nhau.

**Câu 6.** Có thể dùng **thenCombineAsync** để tổng hợp hai future độc lập trong một executor riêng không?

**Đáp án:** Có. Truyền (other, function, executor), callback kết hợp được scheduling qua executor khi hai nguồn hoàn tất bình thường.

**Câu 7.** **allOf(f1, f2)** có chấp nhận tham số executor để di chuyển mọi f1/f2 vào pool mới không?

**Đáp án:** Không. allOf chỉ tạo stage tổng hợp; muốn hậu xử lý ở pool nào, nối thêm callback Async với Executor đó.

**Câu 8.** **@Async("ioExecutor")** trên Spring service có tự điều khiển **thenApplyAsync(fn)** ở phía caller không?

**Đáp án:** Không. Caller cần gọi thenApplyAsync(fn, ioExecutor) hoặc một executor khác nếu muốn lựa chọn rõ.

**Câu 9.** Nếu một worker duy nhất gọi nested Future.join() mà nested task cũng nằm chờ trong pool có một worker, nguy cơ là gì?

**Đáp án:** Starvation/deadlock vì worker duy nhất đang chờ công việc cần chính worker đó để chạy.

**Câu 10.** Nếu pipeline chỉ có transform rất nhẹ, không chặn và không cần affinity, có nhất thiết dùng Async ở mọi bước không?

**Đáp án:** Không. Non-async có thể giảm chi phí scheduling, với điều kiện hiểu callback có thể chạy trên thread hoàn tất upstream.

**Câu 11.** **whenCompleteAsync** và **handleAsync** khác nhau ở đâu?

**Đáp án:** whenComplete chủ yếu quan sát outcome và thường giữ outcome cũ, handle có thể tính một kết quả mới từ thành công hoặc ngoại lệ.

**Câu 12.** Nếu **@Async** bị executor từ chối ngay lúc gọi proxy, một handler **exceptionally** gắn vào future có chắc nhận được lỗi không?

**Đáp án:** Không. Có trường hợp lời gọi chưa trả Future để gắn handler; cần xử lý ở boundary submit và ở future nếu đã được trả.

**Câu 13.** **orTimeout** có bảo đảm task đang gọi HTTP client sẽ lập tức dừng không?

**Đáp án:** Không. Timeout ở future không tự đảm bảo cancel/hủy I/O. Cần timeout/cancellation của chính client và policy cleanup.

## 20. Checklist thiết kế pipeline trong ứng dụng Spring

- [ ] Tách rõ **nguồn dữ liệu** và các **dependent stages**.
- [ ] Với mỗi stage, xác định nó **CPU-bound, blocking I/O hay callback rất nhẹ**.
- [ ] Chọn **non-async** cho callback nhẹ không đòi hỏi thread affinity khi phù hợp.
- [ ] Dùng **Async(..., executor)** ở mỗi ranh giới thật sự muốn chọn pool.
- [ ] Không giả định executor của stage nguồn được thừa kế vô hạn.
- [ ] Phân biệt **thenApply** với **thenCompose**, và executor của callback với executor của future mà callback trả về.
- [ ] Khi dùng **@Async("...")**, xác minh bean name/qualifier, **@EnableAsync** và lời gọi đi qua Spring proxy.
- [ ] Xử lý riêng **rejection tại scheduling/submit** và lỗi task qua future.
- [ ] Không gọi **join/get** chờ nested task trong cùng pool hữu hạn nếu có thể dùng composition.
- [ ] Cấu hình **pool, queue, max threads, timeout** theo downstream và SLA.
- [ ] Truyền **immutable snapshot** của dữ liệu request cần thiết; không chia sẻ mutable field singleton giữa các request.
- [ ] Propagate/cleanup **MDC, SecurityContext, tracing** đúng cách ở các ranh giới thread.
- [ ] Test thread identity hoặc tên worker được đặt tường minh, không chỉ kiểm tra giá trị cuối.
- [ ] Dùng get(timeout), release latch và shutdown/awaitTermination để test không bị treo.
- [ ] Nếu công việc không được phép mất khi restart, thiết kế **durable job queue/outbox**, không dựa chỉ vào CompletableFuture.

## Kết luận

**Biến thể Async** của CompletableFuture cho bạn kiểm soát **nơi và cách chạy callback**, còn lựa chọn **Executor tường minh** cho phép phân chia CPU, blocking I/O, giới hạn concurrency và quản lý quá tải một cách có chủ đích. Các phương thức non-async không tự chọn worker riêng; các phương thức Async không truyền executor thường dùng default facility của CompletableFuture, **không mặc nhiên là pool Spring**.

Trong hệ thống Spring, **@Async("executorName")** điều khiển executor của **method body được proxy dispatch**, trong khi **thenApplyAsync/thenComposeAsync/thenCombineAsync(..., executor)** điều khiển executor của **từng dependent callback**. Để tránh “async nhưng chạy sai pool”, hãy **đặt Executor đúng ở từng ranh giới cần kiểm soát**, phân biệt nested stage, tránh blocking làm nghẽn worker, quản lý context và test bằng thread identity hoặc executor được đặt tên tường minh.

**Tài liệu chính thức nên đọc:**

- Java SE 17: [CompletableFuture Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html) và [CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html).
- Java SE 17: [Executor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html), [ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html), [ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html).
- Spring Framework: [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html), [@Async Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/Async.html), [ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html).
