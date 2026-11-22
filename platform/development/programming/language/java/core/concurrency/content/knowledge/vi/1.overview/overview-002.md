# Process, platform thread, virtual thread và task trong Java

## 1. Bức tranh tổng thể: chương trình chạy bằng những gì?

Khi đọc một ứng dụng Java có nhiều công việc diễn ra đồng thời, cần tách bốn khái niệm:

- **Process (tiến trình)**: một lần thực thi chương trình do hệ điều hành quản lý, có không gian địa chỉ và tài nguyên riêng theo cơ chế cách ly của hệ điều hành. Một lần chạy lệnh `java Main` thông thường tạo một tiến trình chứa JVM.
- **Platform thread (luồng nền tảng)**: một `java.lang.Thread` được JVM gắn với luồng hệ điều hành (OS thread). Hệ điều hành lập lịch cho luồng đó chạy trên các lõi CPU.
- **Virtual thread (luồng ảo)**: `java.lang.Thread` nhẹ, được JVM quản lý và lập lịch lên các platform thread dùng làm **carrier** (luồng mang). Virtual thread là tính năng chính thức từ Java 21; API `Thread.ofVirtual()` và `Executors.newVirtualThreadPerTaskExecutor()` đã ổn định.
- **Task (tác vụ)**: đơn vị công việc cần thực hiện, chẳng hạn “đọc dữ liệu”, “xử lý một yêu cầu” hoặc “tính kết quả”. Task là **công việc**, còn thread là **ngữ cảnh thực thi công việc**. Một `Runnable` hoặc `Callable` mô tả task nhưng không tự chạy khi chỉ mới tạo đối tượng.

Quan hệ thường gặp:

```text
Hệ điều hành
  ├── Process A: JVM
  │     ├── platform thread "main" ──────────> chạy mã Java
  │     ├── platform thread trong thread pool -> chạy lần lượt nhiều task
  │     └── carrier platform threads
  │           ├── virtual thread A ──────────> task A (khi được lập lịch)
  │           ├── virtual thread B ──────────> task B (khi được lập lịch)
  │           └── virtual thread C ──────────> task C (khi được lập lịch)
  └── Process B: chương trình khác
```

Sơ đồ biểu diễn quan hệ logic, không hàm ý mỗi virtual thread có một carrier riêng cố định. Một carrier có thể chạy nhiều virtual thread **lần lượt**; khi đang chạy, một virtual thread được gắn (mounted) lên một carrier.

### So sánh nhanh

| Tiêu chí | Process | Platform thread | Virtual thread | Task |
| --- | --- | --- | --- | --- |
| Bản chất | Đơn vị tiến trình của hệ điều hành | Luồng Java gắn với OS thread | Luồng Java do JVM lập lịch trên carrier | Một công việc hoặc phép tính |
| Ai lập lịch thực thi? | Hệ điều hành quản lý tiến trình/các OS thread | Hệ điều hành lập lịch OS thread | JVM lập lịch virtual thread lên carrier; OS lập lịch carrier | Do người gọi, executor hoặc cơ chế điều phối lựa chọn |
| Bộ nhớ/trạng thái | Không gian địa chỉ và tài nguyên tiến trình, thường được cách ly khỏi tiến trình khác | Stack và trạng thái luồng; chia sẻ heap của process | Stack/trạng thái logic của luồng; chia sẻ heap của process | Dữ liệu đầu vào, trạng thái và kết quả tùy thiết kế |
| Chi phí khi tạo nhiều | Tương đối cao | Stack và tài nguyên OS thread đáng kể | Thường thấp hơn nhiều cho số lượng tác vụ chờ I/O lớn | Phụ thuộc bản thân công việc và dữ liệu |
| Đối tượng/API Java tiêu biểu | `Process`, `ProcessBuilder` để quản lý tiến trình con | `Thread.ofPlatform()` | `Thread.ofVirtual()` | `Runnable`, `Callable`, `Future` |

**Ghi nhớ:** một JVM thường có nhiều thread; nhiều thread trong cùng JVM có thể truy cập chung đối tượng trên heap. Hai process thông thường không thể truy cập trực tiếp cùng heap Java; muốn trao đổi cần cơ chế như socket, pipe, tệp hoặc bộ nhớ chia sẻ được cấu hình riêng. Cách ly process không bảo đảm task bên trong process tự an toàn trước tranh chấp dữ liệu.

## 2. Concurrency khác parallelism

**Concurrency (đồng thời)** nói rằng nhiều công việc cùng tiến triển trong một khoảng thời gian. Chúng có thể thay phiên nhau trên một lõi CPU. **Parallelism (song song)** nói rằng hai hay nhiều công việc thực sự chạy cùng một thời điểm trên các lõi hoặc đơn vị xử lý khác nhau.

Ví dụ, trong khi task A chờ phản hồi mạng, CPU có thể xử lý task B. Đây là concurrency ngay cả khi chỉ có một lõi xử lý mã Java tại một thời điểm. Hai tác vụ tính toán nặng chạy đồng thời trên hai lõi là parallelism.

Thread loại nào cũng cần CPU để chạy mã. Virtual thread **không tạo thêm lõi CPU** và không biến thuật toán tính toán nặng thành nhanh hơn chỉ bằng cách tăng số lượng thread. Điểm mạnh chính của virtual thread là giúp duy trì rất nhiều tác vụ có thời gian chờ I/O theo phong cách lập trình tuần tự mà không cần dành riêng một OS thread cho mỗi tác vụ chờ.

## 3. Process trong ứng dụng Java

Khi chạy `java MyApp`, hệ điều hành khởi tạo tiến trình JVM; bên trong JVM có `main` thread và các thread phục vụ runtime. Mỗi process có PID, tập tài nguyên (ví dụ các file descriptor, socket) và vòng đời riêng. JVM có thể khởi tạo process con bằng `ProcessBuilder`, nhưng **process con khác với một thread mới**: nó có không gian địa chỉ, cơ chế dừng/chờ và giao tiếp riêng.

Ví dụ thực tế:

- Hai lệnh `java MyApp` chạy riêng là hai tiến trình JVM, dù dùng cùng tệp `.class`.
- Trong một JVM, một task đọc socket và task khác tính toán có thể cùng dùng một đối tượng cache; đồng bộ truy cập cache là vấn đề của thread.
- Để một JVM truyền dữ liệu cho JVM khác, cần một kênh IPC hoặc giao thức trao đổi; đặt biến `static` không khiến hai JVM chia sẻ biến.

Process thích hợp khi cần ranh giới cách ly, quyền và vòng đời độc lập. Thread thích hợp khi nhiều công việc thuộc **cùng ứng dụng** cần phối hợp và dùng chung dữ liệu. Đây là hai quyết định kiến trúc ở hai tầng khác nhau.

## 4. Platform thread: ánh xạ tới OS thread

`Thread.ofPlatform().start(runnable)` tạo và khởi chạy một platform thread. Một platform thread gắn với OS thread trong suốt vòng đời; hệ điều hành chịu trách nhiệm phân phối thời gian CPU. Mỗi platform thread cần tài nguyên hệ điều hành và stack, vì vậy tạo hàng chục nghìn platform thread đang tồn tại thường tốn kém hơn nhiều so với tạo cùng số lượng virtual thread.

**Lưu ý về trạng thái:** `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, `TERMINATED` là các giá trị `Thread.State` quan sát được qua API, không phải cam kết về chính xác lúc nào CPU đang chạy thread. `RUNNABLE` có thể bao gồm thời gian sẵn sàng chạy. Thread bị chờ khóa monitor, `join` hoặc `sleep` cũng không làm cho task khác tự trở nên an toàn.

Đối với tập công việc nhỏ, tồn tại lâu dài, hoặc tác vụ dùng native API có yêu cầu thread cụ thể, platform thread có thể phù hợp. Khi rất nhiều request đồng thời đều chờ mạng, dùng một platform thread cho mỗi request dễ chạm giới hạn tài nguyên OS thread; vì thế các ứng dụng truyền thống thường dùng **pool** platform thread với số luồng hữu hạn và hàng đợi task.

## 5. Virtual thread: thread Java nhẹ được JVM lập lịch

Virtual thread cũng là `Thread`: có danh tính, có thể gọi `start`, `join`, `interrupt`, quan sát bằng `Thread.currentThread()` và `isVirtual()`. Khác biệt là virtual thread **không sở hữu riêng một OS thread trong toàn bộ vòng đời**.

Trong Java 21, JVM gắn virtual thread lên một carrier platform thread khi nó sẵn sàng chạy. Với nhiều thao tác blocking I/O được JDK hỗ trợ, JVM có thể tháo (unmount) virtual thread khỏi carrier trong lúc chờ, cho carrier chạy virtual thread khác. Khi kết quả I/O sẵn sàng, virtual thread được lên lịch tiếp tục. Cơ chế này giúp mã trông như tuần tự, chẳng hạn `read()` rồi xử lý kết quả, vẫn có thể phục vụ nhiều kết nối đang đợi.

Không phải mọi lời gọi chặn đều giải phóng carrier: có khác biệt giữa phiên bản JDK, thư viện native và loại thao tác. Trong **Java 21**, virtual thread có thể bị **pinning** khi thực hiện thao tác chặn trong vùng `synchronized` hoặc khi chạy mã native/foreign; carrier lúc đó có thể bị giữ lại. Java 24 cải thiện trường hợp monitor pinning theo JEP 491, nhưng vẫn cần xét phiên bản JDK và thư viện cụ thể. Pinning không có nghĩa chương trình luôn sai; nó có thể làm giảm khả năng mở rộng khi xảy ra nhiều thao tác chờ.

Virtual thread đặc biệt thích hợp với tác vụ **I/O-bound** như chờ dữ liệu từ mạng, tệp hoặc hệ thống bên ngoài. Tác vụ **CPU-bound** vẫn cần CPU và nên được giới hạn song song theo tài nguyên xử lý thực có.

### Ví dụ 1 — hai loại thread, cùng thực hiện một kiểu công việc

Tạo tệp `ThreadKindsDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class ThreadKindsDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger platformResult = new AtomicInteger();
        AtomicInteger virtualResult = new AtomicInteger();

        Thread platform = Thread.ofPlatform()
                .name("platform-demo")
                .start(() -> platformResult.set(10));

        Thread virtual = Thread.ofVirtual()
                .name("virtual-demo")
                .start(() -> virtualResult.set(20));

        platform.join();
        virtual.join();

        System.out.println("platform: value=" + platformResult.get()
                + ", virtual=" + platform.isVirtual());
        System.out.println("virtual: value=" + virtualResult.get()
                + ", virtual=" + virtual.isVirtual());
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên**:

```bash
javac ThreadKindsDemo.java
java ThreadKindsDemo
```

Kết quả:

```text
platform: value=10, virtual=false
virtual: value=20, virtual=true
```

Hai thread được tạo và có thể chạy theo thứ tự bất kỳ. Tuy nhiên, `join()` buộc `main` chờ cả hai hoàn tất trước khi in, nên thứ tự hai dòng kết quả như trên là xác định. `AtomicInteger` cung cấp thao tác cập nhật/đọc an toàn; đồng thời, khi `join` trả về bình thường, các hành động của thread đã kết thúc có quan hệ *happens-before* với các hành động sau `join` của thread đợi. `isVirtual()` phân biệt loại luồng, không suy ra số lượng lõi hoặc mức độ song song thực tế.

**Quan trọng về vòng đời:** virtual thread trong Java 21 là daemon thread và tự nó không giữ JVM sống. Nếu `main` kết thúc mà không có thread không-daemon khác, JVM có thể dừng trước khi virtual thread làm xong. Dùng `join`, `Future.get`, đóng executor đúng cách hoặc cơ chế quản lý vòng đời tương ứng để chờ công việc cần thiết.

## 6. Task là công việc; thread là nơi chạy công việc

Xét hai cách viết:

- `Runnable` mô tả công việc không trả kết quả: `() -> saveRecord()`.
- `Callable<T>` mô tả công việc có kết quả `T` hoặc có thể ném exception: `() -> calculateValue()`.

Việc tạo `Runnable` hay `Callable` **không khởi tạo thread và không tự thực thi**. Người gọi có thể chạy đồng bộ bằng `run()`, tạo một thread để chạy, hoặc gửi vào `ExecutorService`. `Thread.start()` tạo hoạt động đồng thời, còn gọi trực tiếp `runnable.run()` chỉ là lời gọi phương thức thông thường trên thread hiện tại.

`ExecutorService` nhận task, quyết định cách thực thi dựa vào implementation, và thường trả `Future` để quan sát kết quả. Một **pool platform thread** có thể tái sử dụng một số thread cho nhiều task lần lượt. Ngược lại, `newVirtualThreadPerTaskExecutor()` tạo **một virtual thread mới cho mỗi task**, không phải một pool virtual thread dùng lại. Tên “per task” mô tả chính sách thực thi, không có nghĩa task và thread là cùng một khái niệm.

### Ví dụ 2 — thực thi task bằng virtual-thread-per-task executor

Tạo tệp `TaskExecutorDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class TaskExecutorDemo {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            Future<Integer> calculation = executor.submit(() -> {
                Thread.sleep(50);
                return 6 * 7;
            });
            Future<Boolean> typeCheck = executor.submit(
                    () -> Thread.currentThread().isVirtual());

            System.out.println("result=" + calculation.get());
            System.out.println("runsOnVirtualThread=" + typeCheck.get());
        }
    }
}
```

Chạy với JDK 21 trở lên:

```bash
javac TaskExecutorDemo.java
java TaskExecutorDemo
```

Kết quả:

```text
result=42
runsOnVirtualThread=true
```

Hai `submit` gửi hai task độc lập; mỗi task chạy trong virtual thread riêng. `Thread.sleep(50)` mô phỏng thời gian chờ, không chứng minh tăng tốc hiệu năng và không bảo đảm thứ tự các task thực sự bắt đầu. `Future.get()` chờ kết quả (hoặc ném exception nếu task thất bại). `try`-with-resources đóng executor theo vòng đời của `ExecutorService`, chờ các task hoàn tất. Chương trình in theo thứ tự cố định vì gọi `get` rồi in theo thứ tự xác định.

**Không suy rộng:** `CompletableFuture.supplyAsync(...)` không có đối số executor mặc định dùng `ForkJoinPool.commonPool()` (theo cấu hình thông thường), **không mặc nhiên dùng virtual thread**. Muốn task chạy trên virtual thread bằng API đó, phải truyền executor phù hợp.

## 7. Những gì xảy ra khi task chờ, chạy nặng hoặc bị hủy

### 7.1. Blocking I/O và carrier

Một tác vụ mạng kiểu tuần tự có thể thực hiện: gửi yêu cầu → chờ phản hồi → phân tích kết quả. Với platform thread, trong thời gian thao tác chặn, OS thread đó thường đang đợi và chưa thể thực thi task khác trong cùng thread. Với virtual thread trên JDK và thao tác I/O hỗ trợ unmount, JVM có thể trả carrier về bộ lập lịch trong lúc virtual thread chờ.

Chính khả năng tận dụng carrier trong thời gian chờ tạo lợi ích mở rộng số lượng tác vụ I/O đồng thời. Nếu bản thân tác vụ chạy vòng lặp CPU liên tục thì virtual thread vẫn chiếm carrier khi thực thi; nó không tự “nhẹ CPU” hơn platform thread.

### 7.2. Chờ hoàn thành khác với hủy công việc

- `thread.join()` chờ thread kết thúc; `future.get()` chờ task hoàn thành hoặc thất bại.
- `future.get(timeout, unit)` chỉ đặt giới hạn thời gian **chờ kết quả** cho bên gọi. Khi bị `TimeoutException`, task không tự bị hủy.
- `future.cancel(true)` yêu cầu hủy task và thường phát tín hiệu ngắt tới thread đang chạy, nhưng **không bảo đảm task dừng tức thì**.
- `thread.interrupt()` là tín hiệu hợp tác. Mã đang chờ bằng nhiều API như `sleep`/`join` có thể nhận `InterruptedException`; mã chạy lâu cần chủ động kiểm tra trạng thái ngắt và thoát an toàn.

Khi bắt `InterruptedException` mà không thể ném tiếp, cách xử lý thường là khôi phục cờ ngắt qua `Thread.currentThread().interrupt()` rồi kết thúc phần việc hoặc chuyển tín hiệu lên tầng điều phối. Đừng nuốt exception rồi tiếp tục như thể không có yêu cầu dừng.

### 7.3. Vòng đời và tài nguyên ngoài thread

Mỗi task có thể giữ socket, transaction, kết nối, file descriptor hoặc bộ đệm. Dù virtual thread rẻ hơn, **các tài nguyên này không tự rẻ hơn**. Nếu tạo 100.000 virtual thread cùng gọi một cơ sở dữ liệu chỉ hỗ trợ 50 kết nối, nút thắt vẫn nằm ở giới hạn kết nối, khả năng xử lý của hệ thống đích và chính sách timeout.

Giới hạn truy cập tài nguyên bằng connection pool, `Semaphore` hoặc cơ chế backpressure phù hợp. Không “pool virtual thread” chỉ để hạn chế tải: giới hạn ở đúng tài nguyên đang khan hiếm. Luôn quy định thời gian chờ, hủy, retry có kiểm soát và đóng tài nguyên trong `try`-with-resources khi có thể.

## 8. Dùng chung dữ liệu: virtual thread không tự giải quyết race condition

Các thread trong một JVM thường thấy cùng heap. Hai task đồng thời sửa một biến chung mà không có quan hệ đồng bộ hợp lệ có thể gây **data race**, lost update hoặc đọc giá trị không được bảo đảm nhìn thấy theo Java Memory Model. Điều đó xảy ra với cả platform thread lẫn virtual thread.

Ví dụ `counter++` gồm nhiều bước đọc, cộng, ghi; hai thread cùng tăng có thể mất một lần cập nhật. Thay bằng `AtomicInteger.incrementAndGet()` khi chỉ cần bộ đếm đơn giản, hoặc dùng khóa, collection concurrent và thiết kế bất biến/chuyển thông điệp tùy yêu cầu.

Các quan hệ *happens-before* hữu ích gồm việc hoàn tất `Thread.start()` trước các hành động trong thread mới, hành động của thread trước khi một `join` tương ứng trả về, và các bảo đảm của `synchronized`, `volatile`, atomic classes, `Future` theo hợp đồng API. Đừng đánh đồng “đã nhìn thấy giá trị đúng ở một lần chạy” với “chương trình luôn đúng”.

**ThreadLocal:** dữ liệu lưu theo từng thread, kể cả virtual thread. Tạo số lượng virtual thread rất lớn rồi đặt nhiều đối tượng nặng trong `ThreadLocal` vẫn có thể tốn nhiều bộ nhớ và kéo dài vòng đời tài nguyên. Không giả định trạng thái `ThreadLocal` từ task trước sẽ tồn tại ở task tiếp theo trong `newVirtualThreadPerTaskExecutor`: mỗi task nhận một virtual thread mới.

## 9. Chọn đơn vị thực thi cho tình huống thực tế

| Tình huống | Lựa chọn khởi đầu hợp lý | Lý do và điều kiện |
| --- | --- | --- |
| Cần chạy chương trình tách biệt, cách ly tài nguyên/quyền | Process mới | Ranh giới hệ điều hành; phải chủ động giao tiếp, xử lý lỗi và thu hồi tiến trình |
| Vài tác vụ nền tồn tại lâu hoặc có ràng buộc với native OS thread | Platform thread | Phù hợp khi số lượng luồng hạn chế và đặc tính native cần thread riêng |
| Lượng lớn request độc lập, phần lớn thời gian chờ I/O | Virtual thread cho mỗi task | Mã đồng bộ dễ theo dõi, ít OS thread bị giữ khi chờ I/O có hỗ trợ |
| Hàng loạt phép tính CPU-bound | Executor giới hạn concurrency theo CPU | Virtual thread không tăng năng lực CPU; cần chia nhỏ và đo hiệu năng |
| Gọi dịch vụ/DB có quota hay connection pool cố định | Task + giới hạn truy cập tài nguyên | Số virtual thread lớn không thay thế quota, timeout và backpressure |
| Nhiều task cần trả kết quả, phát lỗi hoặc hủy có kiểm soát | `ExecutorService` + `Future` | Tách mô tả task khỏi điều phối và theo dõi vòng đời |

Đừng chọn theo số lượng thread tối đa trong một bản demo. Hãy đo thời gian chờ, CPU, bộ nhớ, số connection, contention, latency và throughput với tải thực tế. Mục tiêu là để nhiều **công việc hữu ích** tiến triển an toàn, chứ không phải tạo nhiều thread nhất.

## 10. Những nhầm lẫn cần loại bỏ

1. **“Một task luôn là một thread.”** Sai. Một thread trong pool có thể chạy hàng nghìn task qua thời gian; một task có thể tự chia thành nhiều tác vụ con. Chỉ với `newVirtualThreadPerTaskExecutor`, mỗi task được executor gán một virtual thread mới.
2. **“Virtual thread không dùng OS thread.”** Sai. Mã Java của virtual thread vẫn chạy trên carrier platform thread; OS vẫn lập lịch carrier lên CPU.
3. **“Virtual thread làm bài toán tính toán nặng chạy nhanh hơn.”** Không có bảo đảm đó. Tác vụ CPU-bound vẫn tranh cùng các lõi CPU, thậm chí tạo quá nhiều task có thể gây overhead.
4. **“Thread.sleep() nghĩa là nhường CPU một cách công bằng.”** `sleep` yêu cầu chờ tối thiểu theo ngữ nghĩa API, không bảo đảm công bằng, thời điểm được chạy lại hoặc thứ tự xử lý.
5. **“Dùng virtual thread thì không cần khóa.”** Sai. Cả hai loại thread chia sẻ dữ liệu và phải tuân theo Java Memory Model.
6. **“Có Future.get(timeout) thì task đã bị dừng khi hết giờ.”** Sai. Timeout khi đợi không phải hủy; cần chính sách cancel, interrupt và cleanup riêng.
7. **“Càng nhiều virtual thread thì càng nhiều kết nối DB.”** Sai. Connection pool và hệ thống đích vẫn quyết định mức truy cập hữu ích.
8. **“Tất cả blocking operations đều unmount virtual thread.”** Sai. Có các trường hợp pinning/native và khác biệt giữa phiên bản JDK; cần quan sát trên môi trường chạy thật.

## 11. Tự kiểm tra hiểu biết

**Tình huống A:** Chạy hai lần `java MyApp`. Mỗi lần tạo 20 virtual thread. Có bao nhiêu process Java và các virtual thread có mặc định chia sẻ biến `static` giữa hai lần chạy không?

**Đáp án:** Thông thường là hai JVM process; mỗi process có không gian heap riêng. Hai nhóm virtual thread trong hai process không chia sẻ trực tiếp cùng biến `static`.

**Tình huống B:** Một ứng dụng có 5.000 công việc chờ HTTP, mỗi công việc chủ yếu đợi phản hồi mạng. Vì sao virtual thread có thể phù hợp hơn 5.000 platform thread?

**Đáp án:** JVM có thể unmount nhiều virtual thread đang chờ I/O, tái sử dụng tập carrier OS thread nhỏ hơn nhiều để chạy những virtual thread sẵn sàng. Kết quả vẫn phụ thuộc thư viện mạng, giới hạn hệ thống đích, socket, bộ nhớ và cấu hình runtime.

**Tình huống C:** Đổi từ platform thread sang virtual thread nhưng phép tính `counter++` trên biến dùng chung vẫn cho kết quả sai. Vì sao?

**Đáp án:** Race condition nằm ở việc cập nhật nhiều bước không được đồng bộ, không nằm ở loại thread. Cần `AtomicInteger`, đồng bộ hoặc cấu trúc dữ liệu an toàn phù hợp.

**Tình huống D:** Một task gọi `Future.get(100, MILLISECONDS)` rồi timeout. Task đang chạy có chắc chắn đã dừng?

**Đáp án:** Không. Timeout chỉ kết thúc việc đợi kết quả của bên gọi; muốn hủy cần thực hiện `cancel` và thiết kế task phản hồi tín hiệu ngắt, đóng tài nguyên đúng cách.

## 12. Tổng hợp mối quan hệ

**Process** đặt ranh giới thực thi và tài nguyên ở cấp hệ điều hành. Trong một JVM process, **platform thread** cung cấp luồng thực thi gắn OS thread, còn **virtual thread** cung cấp luồng Java nhẹ do JVM gắn lên carrier khi cần chạy. **Task** mô tả công việc cần hoàn tất; executor hoặc mã ứng dụng quyết định đặt task vào thread nào và quản lý kết quả ra sao.

Với Java 21+, cách tiếp cận tự nhiên cho nhiều tác vụ chờ I/O là **mỗi task một virtual thread** cùng quản lý vòng đời, timeout và giới hạn tài nguyên. Với tác vụ CPU-bound hoặc ràng buộc OS/native đặc thù, quyết định dựa trên số lõi, chi phí thật và đo đạc. Dù chọn loại thực thi nào, an toàn dữ liệu và cách hủy task vẫn là trách nhiệm thiết kế của chương trình.
