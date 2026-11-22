# Vì sao không pool virtual threads?

**Câu trả lời:** Với Java 21 trở lên, hãy tạo **một virtual thread cho mỗi tác vụ đồng thời** thay vì duy trì một nhóm virtual thread để tái sử dụng. Thread pool truyền thống giải quyết sự khan hiếm và chi phí tạo **platform thread** (luồng gắn với luồng hệ điều hành). Virtual thread nhẹ hơn nhiều, được JVM quản lý để có thể tạo, chạy, chờ rồi kết thúc theo vòng đời của từng tác vụ. Pool chúng thường áp đặt một giới hạn giả tạo, tăng hàng đợi và làm mất lợi ích mô hình *thread-per-task*.

Điều này **không có nghĩa là cho phép mọi thao tác truy cập tài nguyên không giới hạn**: vẫn cần giới hạn kết nối, truy vấn, request, bộ nhớ và lượng công việc đang chờ bằng cơ chế đúng mục đích như `Semaphore`, connection pool và backpressure. Phạm vi bài này là **concurrency của Java nói chung**, không đi vào cấu hình hay cơ chế của Spring.

## 1. Pool platform threads ra đời để làm gì?

Với `java.lang.Thread` kiểu **platform thread**, một luồng Java thường gắn với một luồng hệ điều hành trong suốt vòng đời của nó. Việc có quá nhiều luồng như vậy gây tốn tài nguyên hệ thống: stack, bộ nhớ liên quan, chi phí tạo/hủy và điều phối. Bởi vậy, thay vì tạo một platform thread mới cho mỗi tác vụ, ta thường dùng `Executors.newFixedThreadPool(n)`:

1. Hệ thống giữ một số hữu hạn platform thread, ví dụ 16.
2. Tác vụ đến được đưa vào hàng đợi.
3. Mỗi worker lấy một tác vụ, chạy xong rồi tái sử dụng cùng platform thread để chạy tác vụ khác.

Đây là lựa chọn hợp lý khi ta cần quản lý số lượng **platform thread** hoặc số tác vụ CPU đang chạy. Nhưng nếu 16 platform thread đều gọi I/O chặn trong 500 ms, các tác vụ khác phải chờ trong hàng đợi, dù CPU có thể đang rảnh. Tăng pool liên tục để che độ trễ I/O lại tiêu tốn thêm OS threads.

## 2. Virtual thread đổi điều gì?

Virtual thread là một đối tượng `Thread` thực sự trong Java API nhưng **không giữ riêng một OS thread trong toàn bộ thời gian sống**. Virtual thread được thực thi trên **carrier thread** (platform thread dùng bởi bộ lập lịch của JVM). Khi virtual thread gặp một thao tác blocking được JDK hỗ trợ như `Thread.sleep` hoặc nhiều thao tác socket I/O, JVM có thể *unmount* (tách) virtual thread khỏi carrier, để carrier chạy tác vụ khác; khi thao tác sẵn sàng, virtual thread có thể được chạy tiếp trên một carrier thích hợp.

Hình dung:

```text
Platform-thread pool:
Task A ─── blocking I/O ─── hoàn thành ──> worker #1
Task B ─── blocking I/O ─── hoàn thành ──> worker #2
Task C ─── đợi worker rảnh ──────────────> worker #1

Virtual threads:
Task A / virtual thread A ── I/O chờ ────> hoàn thành
Task B / virtual thread B ── I/O chờ ────> hoàn thành
Task C / virtual thread C ── I/O chờ ────> hoàn thành
       Các carrier thread được JVM chia sẻ trong thời gian thực thi.
```

Vì vậy, virtual thread phù hợp với lượng lớn công việc *độc lập, thường xuyên chờ I/O*. Nó giữ mô hình viết mã tuần tự dễ hiểu (`read`, `sleep`, `get`, gọi dịch vụ...), trong khi giảm số platform thread phải nằm chờ.

**Điểm chính:** Một virtual thread thường đại diện **một tác vụ**, chứ không đại diện một worker tồn tại lâu dài để lấy hết tác vụ này đến tác vụ khác. Virtual thread kết thúc khi tác vụ kết thúc. Chính JVM đã quản lý việc dùng lại **carrier thread** ở lớp thấp hơn; ứng dụng không cần tự xây thêm pool virtual threads.

## 3. Tại sao pool virtual threads không có lợi?

| Vấn đề | Giữ pool virtual threads | Một virtual thread cho mỗi task |
| --- | --- | --- |
| Vòng đời | Virtual thread tồn tại lâu để nhận nhiều task | Virtual thread được tạo cho một task và kết thúc |
| Giới hạn | Số worker cố định khiến task phải xếp hàng | Số virtual thread đang sống tùy theo nhu cầu công việc |
| Chi phí tránh được | Chủ yếu cố tiết kiệm tạo/hủy virtual thread vốn đã nhẹ | Không cần tái sử dụng virtual thread |
| Điều tiết tài nguyên | Lẫn lộn số worker với giới hạn tài nguyên thực | Giới hạn rõ ngay nơi dùng tài nguyên |
| Quan sát/debug | Một worker có thể xử lý nhiều tác vụ kế tiếp | Stack trace và vòng đời gắn trực tiếp với từng tác vụ |

Giả sử cần thực hiện 5.000 lần gọi I/O, mỗi lần mất khá nhiều thời gian để chờ phản hồi. Một pool chỉ có 20 virtual threads sẽ chỉ cho 20 tác vụ đi vào phần xử lý tại một thời điểm và xếp các tác vụ còn lại vào hàng đợi, dù việc cho nhiều virtual threads *đang chờ* thường không đòi hỏi tương ứng chừng ấy carrier threads. Ta đã vô tình tạo lại nút thắt cổ chai tương tự một pool nhỏ.

Ngược lại, nếu hệ thống đích chỉ cho phép **20 request đồng thời**, việc mở 5.000 request cùng lúc là sai. Giới hạn đúng là **số request đến hệ thống đích**, không phải số virtual threads của toàn ứng dụng: các công việc không sử dụng hệ thống đích vẫn có thể tiếp tục độc lập.

Một lỗi thiết kế là:

```java
// KHÔNG NÊN: giữ cố định 20 virtual threads để tái sử dụng như worker.
ExecutorService executor =
        Executors.newFixedThreadPool(20, Thread.ofVirtual().factory());
```

Đoạn trên tạo **pool các worker là virtual threads** và áp trần 20 tác vụ đang chạy trong executor. Đây là API có thể dùng được, nhưng không phải mô hình khuyến nghị để tận dụng virtual threads cho tác vụ I/O độc lập. Ngược lại, `Executors.newVirtualThreadPerTaskExecutor()` **không phải pool virtual threads**: mỗi task được submit sẽ có virtual thread riêng.

## 4. Cách dùng chuẩn: virtual thread per task

Java 21 hỗ trợ trực tiếp `Executors.newVirtualThreadPerTaskExecutor()` và `Thread.ofVirtual()`. Ví dụ sau chạy độc lập bằng Java 21+, không cần thư viện ngoài:

**Tệp `WhyNotPoolVirtualThreads.java`:**

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;

public class WhyNotPoolVirtualThreads {
    private static final int TASK_COUNT = 8;
    private static final Semaphore SERVICE_SLOTS = new Semaphore(2);

    public static void main(String[] args) throws Exception {
        List<Future<String>> results = new ArrayList<>();

        // Mỗi submit() tạo một virtual thread cho một tác vụ.
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 1; i <= TASK_COUNT; i++) {
                final int taskId = i;
                results.add(executor.submit(() -> {
                    // Giới hạn thao tác lên tài nguyên, không giới hạn số virtual threads.
                    SERVICE_SLOTS.acquire();
                    try {
                        Thread.sleep(50); // Giả lập chờ I/O; không phải gọi mạng thật.
                        return "Task " + taskId
                                + ": virtual=" + Thread.currentThread().isVirtual();
                    } finally {
                        SERVICE_SLOTS.release();
                    }
                }));
            }

            // Lấy Future theo thứ tự submit để stdout luôn có thứ tự xác định.
            for (Future<String> result : results) {
                System.out.println(result.get());
            }
        } // close() chờ các tác vụ hoàn tất; executor không giữ pool VT.
    }
}
```

Biên dịch và chạy:

```bash
javac WhyNotPoolVirtualThreads.java
java WhyNotPoolVirtualThreads
```

Kết quả:

```text
Task 1: virtual=true
Task 2: virtual=true
Task 3: virtual=true
Task 4: virtual=true
Task 5: virtual=true
Task 6: virtual=true
Task 7: virtual=true
Task 8: virtual=true
```

**Giải thích chính xác:**

- Có **8 task và 8 virtual threads** được executor tạo ra, nhưng tại một thời điểm chỉ **tối đa 2 task** được vào vùng giả lập gọi dịch vụ, vì `Semaphore(2)`.
- `acquire()` có thể làm một virtual thread chờ; đặt `release()` trong `finally` để trả permit ngay cả khi tác vụ lỗi hoặc bị ngắt sau khi acquire thành công. Nếu bị ngắt ngay khi đang `acquire()`, chương trình chưa lấy permit nên sẽ không chạy `finally` tương ứng.
- `Thread.sleep(50)` mô phỏng khoảng chờ, không chứng minh hiệu năng I/O thật. Kết quả `virtual=true` là xác định; thứ tự **thực thi** các tác vụ và carrier cụ thể không được đảm bảo, chỉ thứ tự **in** được cố định bằng danh sách `Future`.
- `Future.get()` cho phép lấy kết quả và nhận lỗi của tác vụ qua `ExecutionException`; `try-with-resources` đóng executor sau khi dùng xong.

Nếu chỉ cần một virtual thread riêng lẻ, cũng có thể gọi `Thread.ofVirtual().start(runnable)`; phải quản lý việc chờ kết thúc và xử lý lỗi thích hợp. Với nhiều task và `Future`, executor theo từng tác vụ thường dễ tổ chức hơn.

## 5. Giới hạn đúng thứ cần giới hạn

### 5.1. Tài nguyên bên ngoài: `Semaphore` hoặc connection pool

Ví dụ một dịch vụ chỉ xử lý được 10 request đồng thời. Dùng `Semaphore(10)` **quanh thao tác gọi dịch vụ**: request thứ 11 chờ permit; tác vụ khác không đụng tới dịch vụ đó vẫn được chạy. Khi mỗi truy vấn phải lấy kết nối từ một connection pool hữu hạn, chính **connection pool** đã có chức năng chờ/giới hạn số kết nối; thường không cần thêm semaphore trùng mục đích, trừ khi có yêu cầu bảo vệ khác.

Không nên hiểu nhầm rằng vì virtual threads rẻ mà database, socket, file descriptor, băng thông, API quota, bộ nhớ hay transaction cũng trở thành vô hạn.

### 5.2. Áp lực đầu vào: backpressure và giới hạn số công việc đã nhận

`Semaphore` đặt **bên trong** virtual thread bảo vệ phần việc được giới hạn, nhưng nếu tạo hàng triệu virtual threads cùng chờ permit thì vẫn tốn bộ nhớ, task context và công sức quản lý. Khi đầu vào không bị chặn, cần thêm **giới hạn số request đang nhận/xử lý**, hàng đợi có kích thước hữu hạn, từ chối có kiểm soát, hoặc làm chậm phía producer. Đây là **admission control/backpressure**, một quyết định riêng với số carrier threads.

Có thể đặt permit **trước khi submit task** để producer phải chờ khi lượng task đang tồn tại đạt ngưỡng; khi task kết thúc thì trả permit, kể cả khi lỗi. Cần xử lý cả tình huống `submit()` bị từ chối để không làm rò permit. Không dùng giới hạn tùy tiện như "pool 100 virtual threads" để thay thế phân tích yêu cầu tải, độ trễ và tài nguyên thực.

### 5.3. CPU-bound: không có phép màu tăng tốc

Virtual threads cải thiện **khả năng mở rộng khi nhiều task chờ**, chứ không làm CPU có thêm lõi. Với tác vụ chủ yếu tính toán (mã hóa, nén, xử lý số học), thêm virtual threads có thể chỉ làm tăng cạnh tranh CPU và context switching. Số công việc CPU chạy song song thực tế vẫn phụ thuộc số lõi/CPU được cấp, scheduler và cấu hình JVM. Một pool platform threads hữu hạn hoặc cơ chế điều phối riêng cho khối lượng CPU có thể phù hợp hơn. Đừng kết luận "virtual threads luôn nhanh hơn platform threads" chỉ từ số lượng thread.

## 6. Các lỗi hiểu thường gặp

1. **"Virtual threads không dùng pool nào cả."** Chưa chính xác. Ứng dụng không nên pool **virtual threads**; JVM vẫn dùng các **carrier platform threads** và bộ lập lịch nội bộ để thực thi chúng. Đừng cố điều khiển carrier bằng cách tự làm pool virtual threads.
2. **"Dùng `newVirtualThreadPerTaskExecutor()` nghĩa là không giới hạn concurrency nên an toàn."** Sai. Executor tạo một virtual thread cho mỗi task được submit; các hạn mức downstream, bộ nhớ, hàng đợi và áp lực đầu vào vẫn phải được quản lý.
3. **"Semaphore biến virtual threads thành pool."** Sai. Semaphore giới hạn một *đoạn truy cập tài nguyên*, không tái sử dụng một nhóm virtual threads cố định. Các virtual threads vẫn sống theo task của chúng.
4. **"Có 10.000 virtual threads tức 10.000 OS threads."** Sai. Nhiều virtual threads có thể luân phiên dùng một số lượng nhỏ hơn nhiều carrier threads, đặc biệt khi phần lớn đang chờ thao tác blocking được hỗ trợ. Số carrier thực tế do JVM và workload quyết định.
5. **"I/O chặn luôn nhả carrier trong mọi tình huống."** Sai. Một số thao tác native, foreign-function hoặc tình huống runtime đặc biệt có thể giữ carrier (pinning); cần kiểm tra bằng đo đạc trên JDK đang chạy.
6. **"Mỗi virtual thread có thể giữ cache lớn trong `ThreadLocal` vì thread được tái sử dụng."** Sai. `ThreadLocal` vẫn hoạt động, nhưng các virtual threads thường sống ngắn và rất đông; cache nặng theo thread dễ phát sinh cấp phát và áp lực GC. Chỉ giữ dữ liệu ngữ cảnh thật sự cần và đo footprint.
7. **"Có thể bỏ connection pool khi chuyển sang virtual threads."** Sai. Connection pool tồn tại để quản lý **kết nối thật**, vốn hữu hạn và tốn kém, nên vẫn có giá trị.

## 7. Lưu ý theo phiên bản JDK và vận hành

- **Java 21:** Virtual threads là tính năng chính thức (JEP 444). Khi chạy blocking trong `synchronized`, virtual thread có thể bị **pin** vào carrier; nếu xảy ra nhiều và lâu sẽ ảnh hưởng scalability. Cần nhận diện vị trí I/O có thể block kéo dài bên trong monitor; thay đổi sang cơ chế khóa thích hợp chỉ khi cần dựa trên profiling.
- **Java 24+:** JEP 491 cho phép phần lớn tình huống blocking liên quan `synchronized` không còn pin carrier như trước. Vì thế **không được lặp lại một cách máy móc** lời khuyên của JDK 21 rằng mọi `synchronized` đều phải đổi thành `ReentrantLock`. Một số trường hợp native/foreign vẫn có thể pin; phải dựa vào phiên bản JDK và quan sát thực tế.
- **Quan sát:** Đo throughput, p95/p99 latency, số request đang chờ permit, thời gian chờ connection pool, memory/GC, CPU và tình huống pinning. JDK Flight Recorder có sự kiện `jdk.VirtualThreadPinned`; có thể dùng thread dump hỗ trợ virtual threads (`jcmd <pid> Thread.dump_to_file -format=json <file>`) tùy phiên bản/công cụ. Đừng dùng riêng "số lượng thread" làm thước đo tối ưu.
- **Hủy và lỗi:** Task có thể thất bại, bị interrupt hoặc quá hạn. Bảo đảm giải phóng permit, đóng tài nguyên, thu nhận lỗi từ `Future` và quản lý vòng đời executor. Virtual threads giúp chờ hiệu quả hơn; chúng không tự giải quyết timeout, retry hay cancellation.

## 8. Khi nào áp dụng?

**Nên chọn virtual-thread-per-task** khi nhiều công việc độc lập dùng Java blocking API để gọi I/O và cần giữ lối viết tuần tự. **Chọn giới hạn riêng** ở từng tài nguyên có quota hoặc chi phí thực. **Kiểm soát đầu vào** khi lượng task có thể tăng vô hạn. **Đo thực tế** nếu ứng dụng thiên về CPU hoặc có nhiều blocking native/pinning.

Ghi nhớ: **Pool platform threads vì platform threads đắt; không pool virtual threads vì virtual threads được tạo theo task. Giới hạn tài nguyên bằng cơ chế giới hạn tài nguyên.**

## Tài liệu tham khảo

- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): mô hình virtual thread per task, vòng đời và scalability.
- [Oracle Java Virtual Threads Guide](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): không pool virtual threads, semaphore, thread-local và lưu ý trên Java 21.
- [OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): thay đổi pinning từ Java 24.
