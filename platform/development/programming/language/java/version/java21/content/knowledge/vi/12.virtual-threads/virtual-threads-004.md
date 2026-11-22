# Quan hệ giữa số virtual thread với số luồng hệ điều hành

Virtual thread là một đối tượng `Thread` do JVM quản lý, còn luồng hệ điều hành (OS thread) là luồng được hệ điều hành lập lịch thực thi. Trong Java 21, một số lượng lớn virtual thread có thể được multiplex trên một nhóm nhỏ hơn các platform thread đóng vai trò carrier. Vì vậy, số virtual thread của ứng dụng không cần bằng số OS thread của tiến trình.

Trong phạm vi `JAVA_VERSION_JAVA21` (Java 21), cần phân biệt ba khái niệm: virtual thread, carrier thread và platform thread. Sự phân biệt này giúp hiểu vì sao ứng dụng có thể tạo nhiều tác vụ đồng thời mà không phải tạo một OS thread cho từng tác vụ, đồng thời tránh kỳ vọng rằng virtual thread làm tăng số lõi CPU hoặc loại bỏ giới hạn của cơ sở dữ liệu, socket và dịch vụ bên ngoài.

## Ba loại luồng cần phân biệt

| Khái niệm | Được quản lý bởi | Vai trò |
| --- | --- | --- |
| Virtual thread | JVM | Đại diện cho một tác vụ Java; có thể tồn tại ở số lượng lớn và tạm dừng khi chờ I/O hoặc thao tác blocking được hỗ trợ |
| Platform thread | JVM và hệ điều hành | Luồng Java gắn với một OS thread; có thể thực thi mã ứng dụng hoặc làm carrier cho virtual thread |
| Carrier thread | Platform thread do virtual-thread scheduler quản lý | Thực thi mã của virtual thread trong lúc virtual thread được mount trên carrier |

Carrier thread không phải một loại `Thread` Java riêng. Nó là platform thread đang thực hiện công việc thay cho virtual thread. Khi virtual thread được mount, mã Java của virtual thread chạy trên carrier đó. Khi virtual thread tạm dừng và được unmount, carrier có thể chạy một virtual thread khác.

Ngoài các luồng phục vụ ứng dụng, tiến trình JVM còn có những platform/OS thread nội bộ cho các công việc như garbage collection, JIT compilation và các dịch vụ runtime. Vì vậy, tổng số OS thread của tiến trình cũng bao gồm các luồng không trực tiếp xử lý tác vụ ứng dụng.

## Quan hệ giữa virtual thread và OS thread

Trong mô hình platform thread truyền thống, một Java platform thread thường tương ứng với một OS thread. Nếu ứng dụng tạo một platform thread cho mỗi tác vụ đang chờ I/O, các OS thread đó vẫn tồn tại trong lúc chờ. Số lượng OS thread lớn có thể làm tăng chi phí bộ nhớ, lập lịch và chuyển ngữ cảnh.

Với virtual thread, quan hệ không còn là một-một:

- Một virtual thread được mount trên một carrier platform thread khi đang chạy Java code.
- Một carrier lần lượt có thể thực thi nhiều virtual thread khác nhau theo thời gian.
- Khi virtual thread chờ ở một thao tác blocking được JDK hỗ trợ, JVM thường unmount nó khỏi carrier. Carrier được giải phóng để chạy virtual thread khác.
- Khi điều kiện chờ hoàn tất, virtual thread có thể được mount lại trên một carrier phù hợp; nó không cần quay về đúng carrier trước đó.
- Nhiều virtual thread có thể tồn tại cùng lúc trong khi số carrier và OS thread nhỏ hơn đáng kể.

```text
                JVM
   +----------------------------------+
   | Virtual-thread scheduler         |
   |                                  |
   |  Virtual threads                 |
   |  [V1] [V2] [V3] [V4] [V5] ...     |
   |     \\  |   /     \\              |
   |      \\ |  /       \\             |
   |   Carrier A       Carrier B      |
   +-------|---------------|----------+
           |               |
        OS thread       OS thread
           |               |
        CPU cores / OS scheduler
```

Sơ đồ chỉ mô tả quan hệ multiplex theo thời gian. Không có nghĩa mỗi virtual thread luôn gắn cố định với một carrier, hoặc mỗi carrier luôn bận. Khi virtual thread unmount, carrier có thể chuyển sang tác vụ khác.

## Vì sao số virtual thread có thể lớn hơn số OS thread?

Điểm khác biệt nằm ở thời gian chờ. Một tác vụ gửi yêu cầu HTTP hoặc truy vấn cơ sở dữ liệu có thể dành phần lớn thời gian chờ phản hồi. Nếu tác vụ đó chạy trên platform thread, OS thread thường bị giữ trong lúc chờ. Nếu chạy trên virtual thread và thao tác blocking được JDK hỗ trợ, virtual thread có thể tạm dừng mà không giữ carrier trong suốt thời gian chờ.

Ví dụ, ứng dụng cần gọi nhiều dịch vụ độc lập. Mỗi tác vụ có thể được biểu diễn bằng một virtual thread:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadExample {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            Future<String> first = executor.submit(() -> callService("A"));
            Future<String> second = executor.submit(() -> callService("B"));
            Future<String> third = executor.submit(() -> callService("C"));

            System.out.println(first.get());
            System.out.println(second.get());
            System.out.println(third.get());
        }
    }

    private static String callService(String name) throws InterruptedException {
        Thread.sleep(500); // Minh họa một khoảng chờ
        return "Hoàn tất dịch vụ " + name
                + "; virtual=" + Thread.currentThread().isVirtual();
    }
}
```

`newVirtualThreadPerTaskExecutor()` tạo một virtual thread cho mỗi tác vụ được submit. `Thread.sleep()` là thao tác blocking có thể nhường carrier trong trường hợp virtual thread. Trong lúc một tác vụ đang ngủ, carrier có thể thực thi tác vụ khác. `Thread.currentThread().isVirtual()` cho biết thread hiện tại có phải virtual thread hay không.

Ví dụ dùng `Thread.sleep()` để minh họa cơ chế chờ, không mô phỏng đầy đủ hành vi mạng. Trong ứng dụng thực tế, các API I/O của JDK có hỗ trợ virtual thread có thể cho phép virtual thread unmount trong lúc chờ. Một thư viện native hoặc thao tác blocking không được hỗ trợ có thể giữ carrier bị chiếm dụng.

## Scheduler và số carrier thread trong Java 21

Virtual-thread scheduler quyết định virtual thread nào được chạy trên carrier. Trong triển khai JDK 21, scheduler sử dụng một `ForkJoinPool` ở chế độ lập lịch phù hợp cho virtual thread. Các giá trị mặc định triển khai của JDK 21 gồm:

- Parallelism mặc định bằng số bộ xử lý khả dụng mà JVM nhìn thấy, có thể xem qua `Runtime.getRuntime().availableProcessors()`.
- Maximum pool size mặc định là 256 carrier thread.
- Các thuộc tính hệ thống `jdk.virtualThreadScheduler.parallelism` và `jdk.virtualThreadScheduler.maxPoolSize` có thể thay đổi các giới hạn scheduler của triển khai JDK.

Đây là chi tiết triển khai của JDK 21, không phải cam kết rằng mọi JVM hoặc mọi phiên bản Java phải sử dụng cùng thuật toán và con số. Thông thường, không cần tự điều chỉnh các thuộc tính scheduler ngay từ đầu. Hãy đo tải thực tế và xác định nguyên nhân nghẽn trước khi thay đổi cấu hình.

Số carrier không được tạo bằng cách nhân số virtual thread. Scheduler có thể dùng một nhóm carrier để chạy nhiều virtual thread theo thời gian. Một virtual thread đang chờ và đã unmount không cần một carrier riêng để tiếp tục tồn tại.

## Số virtual thread không đồng nghĩa với mức song song của CPU

Virtual thread giúp quản lý nhiều tác vụ đồng thời, đặc biệt khi các tác vụ thường xuyên chờ I/O. Chúng không tạo thêm lõi CPU và không làm một phép tính nặng chạy nhanh hơn chỉ vì phép tính được đặt trong virtual thread.

| Loại công việc | Tác động của virtual thread |
| --- | --- |
| Nhiều lời gọi HTTP đồng thời, phần lớn thời gian chờ phản hồi | Có thể tăng khả năng xử lý đồng thời với chi phí thread thấp hơn |
| Nhiều truy vấn DB đang chờ kết quả | Có thể biểu diễn mỗi tác vụ bằng một virtual thread, nhưng vẫn phải tuân theo giới hạn connection pool và DB |
| Tính toán CPU-bound kéo dài | Không tăng năng lực CPU; mức song song vẫn bị giới hạn bởi số lõi và scheduler |
| Tác vụ chờ trên API native hoặc vùng code bị pinning | Carrier có thể bị giữ trong lúc chờ, làm giảm khả năng mở rộng |

Nếu ứng dụng chủ yếu thực hiện tính toán CPU-bound, hãy chọn mức song song phù hợp với số lõi và đo thông lượng. Tạo số lượng virtual thread rất lớn cho các phép tính CPU nặng không làm tăng năng lực xử lý và có thể làm tăng chi phí lập lịch hoặc bộ nhớ.

## Virtual thread không loại bỏ giới hạn của tài nguyên bên ngoài

Việc tạo virtual thread rẻ hơn nhiều so với việc tạo một lượng lớn platform thread, nhưng không có nghĩa có thể mở vô hạn kết nối hoặc gửi vô hạn yêu cầu tới dịch vụ khác. Mỗi tác vụ vẫn có thể giữ dữ liệu, buffer, request context, socket hoặc một tài nguyên ứng dụng khác.

Ví dụ, một ứng dụng có thể tạo 20.000 virtual thread để gọi một dịch vụ, nhưng connection pool chỉ có 100 kết nối. Tại một thời điểm, nhiều tác vụ vẫn phải chờ lượt sử dụng kết nối. Nếu gửi quá nhiều yêu cầu đồng thời, cơ sở dữ liệu hoặc dịch vụ bên ngoài có thể quá tải.

Hãy giới hạn tại tài nguyên thực sự cần bảo vệ:

- Dùng connection pool để kiểm soát số kết nối DB.
- Dùng `Semaphore` để giới hạn số thao tác đồng thời tới một dịch vụ khi cần.
- Dùng timeout, rate limiter và retry policy phù hợp để tránh tích tụ tác vụ chờ quá lâu.
- Theo dõi bộ nhớ, socket, file descriptor và hàng đợi công việc; virtual thread vẫn có chi phí lưu trạng thái và dữ liệu tác vụ.

Ví dụ dùng semaphore để giới hạn số yêu cầu cùng lúc:

```java
import java.util.concurrent.Semaphore;

public class ServiceGate {
    private final Semaphore permits = new Semaphore(100);

    public String callProtectedService() throws InterruptedException {
        permits.acquire();
        try {
            return performRemoteCall();
        } finally {
            permits.release();
        }
    }

    private String performRemoteCall() {
        // Gọi dịch vụ từ xa; thay bằng client thực tế của ứng dụng.
        return "response";
    }
}
```

Semaphore giới hạn số tác vụ đang giữ permit, bất kể tác vụ đó chạy trên platform thread hay virtual thread. Hãy đặt giới hạn dựa trên năng lực dịch vụ và connection pool, không dựa đơn thuần trên số virtual thread có thể tạo.

## Pinning trong Java 21 có thể giữ carrier bị chiếm dụng

Virtual thread chỉ giải phóng carrier khi nó có thể unmount tại điểm blocking được hỗ trợ. Trong Java 21, có hai trường hợp quan trọng có thể pin virtual thread vào carrier:

- Virtual thread thực hiện thao tác blocking trong khi đang giữ intrinsic lock, chẳng hạn bên trong vùng `synchronized`.
- Virtual thread thực hiện thao tác blocking khi đang ở trong native method hoặc gọi native code.

Khi bị pin, virtual thread không thể unmount khỏi carrier trong lúc blocking đó. Carrier bị giữ lại, nên scheduler không thể dùng carrier đó để chạy một virtual thread khác. Trong Java 21, scheduler không tự tăng parallelism để bù cho trường hợp pinning này.

Ví dụ về vùng có nguy cơ pinning nếu lời gọi bên trong chặn lâu:

```java
public synchronized String load() throws InterruptedException {
    return blockingOperation();
}
```

Nếu `blockingOperation()` chờ I/O lâu trong khi monitor vẫn được giữ, virtual thread có thể bị pin trên carrier. Không phải mọi lần vào `synchronized` đều gây pinning; vấn đề xuất hiện khi virtual thread bị block trong lúc đang giữ monitor.

Khi điều tra, có thể dùng Java Flight Recorder và theo dõi sự kiện `jdk.VirtualThreadPinned`. Nếu sự kiện cho thấy một vùng synchronized đang gây pinning kéo dài, hãy cân nhắc thu hẹp vùng giữ lock hoặc chuyển thao tác blocking ra ngoài vùng synchronized nếu vẫn bảo toàn đúng tính đồng bộ của dữ liệu. Không thay toàn bộ `synchronized` chỉ vì ứng dụng dùng virtual thread; cần dựa trên số liệu và tính đúng đắn của đồng bộ hóa.

## Đếm thread trong JVM và đếm OS thread là hai việc khác nhau

Khi quan sát ứng dụng, cần xác định công cụ đang đếm loại thread nào:

- Công cụ của hệ điều hành thường báo số OS thread của tiến trình JVM. Con số này bao gồm carrier/platform thread và các thread nội bộ của JVM.
- Số virtual thread đang tồn tại có thể lớn hơn nhiều số OS thread, vì virtual thread được JVM quản lý và có thể unmount khi chờ.
- `ThreadMXBean` trong Java 21 báo cáo số platform thread; không dùng riêng `getThreadCount()` để suy ra tổng số virtual thread.
- Java Flight Recorder hỗ trợ quan sát hoạt động virtual thread và các sự kiện liên quan, giúp phân biệt thời gian chạy, chờ và pinning.

Do đó, nếu OS cho thấy tiến trình chỉ có một số lượng carrier/platform thread vừa phải, điều đó không chứng minh ứng dụng chỉ có từng ấy tác vụ Java. Ngược lại, số virtual thread rất lớn cũng không chứng minh tất cả đang chạy song song trên CPU.

Khi đo hiệu năng, hãy quan sát đồng thời số tác vụ đang hoạt động, thời gian chờ, thông lượng, độ trễ, mức dùng CPU, số kết nối và các giới hạn tài nguyên. Một con số thread riêng lẻ không đủ để kết luận ứng dụng đang tận dụng virtual thread tốt hay chưa.

## Không dùng virtual thread như một thread pool

Virtual thread được thiết kế theo hướng một thread cho mỗi tác vụ, thay vì tạo pool virtual thread để tái sử dụng. Tạo virtual thread mới có chi phí thấp; việc giới hạn tải nên dựa vào semaphore, connection pool hoặc cơ chế điều tiết phù hợp với tài nguyên.

```java
import java.util.concurrent.Executors;

try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    for (int i = 0; i < 1_000; i++) {
        int taskId = i;
        executor.submit(() -> process(taskId));
    }
}
```

Executor này tạo virtual thread cho mỗi tác vụ. Khi đóng executor trong try-with-resources, chương trình chờ các tác vụ đã submit hoàn tất. Trong ứng dụng thật, cần xử lý kết quả, lỗi, hủy tác vụ và giới hạn số yêu cầu tới tài nguyên bên ngoài. Không cần đặt một fixed-size pool chỉ để tái sử dụng virtual thread.

## Quy trình lựa chọn và kiểm chứng

1. **Xác định công việc chủ yếu chờ hay tính toán.** Virtual thread hữu ích nhất với nhiều tác vụ đồng thời có thời gian chờ I/O đáng kể.
2. **Chọn mô hình một tác vụ một virtual thread.** Dùng `Thread.startVirtualThread`, `Thread.ofVirtual()` hoặc `Executors.newVirtualThreadPerTaskExecutor()` tùy nhu cầu quản lý tác vụ.
3. **Xác định tài nguyên cần giới hạn.** Đặt giới hạn ở connection pool, semaphore, rate limiter hoặc API client thay vì giới hạn số virtual thread một cách tùy tiện.
4. **Kiểm tra điểm blocking và pinning.** Đặc biệt xem xét synchronized giữ lock trong lúc chờ và native call; dùng JFR để tìm điểm nóng.
5. **Quan sát đúng loại thread.** Phân biệt số virtual thread, platform/carrier thread và OS thread; không dùng một số đo thay cho tất cả.
6. **Đo theo tải thực tế.** So sánh throughput, latency, CPU, memory và giới hạn dịch vụ trước và sau thay đổi.
7. **Triển khai với JDK phù hợp.** Virtual Threads là tính năng ổn định từ Java 21; các ví dụ trong bài không cần bật preview.

Số virtual thread có thể lớn hơn số OS thread vì JVM tạm dừng và unmount virtual thread đang chờ, rồi dùng lại carrier để thực thi tác vụ khác. Carrier/platform thread vẫn là những luồng gắn với OS thread, còn virtual thread là đơn vị tác vụ nhẹ được JVM lập lịch. Hiểu đúng quan hệ này giúp tận dụng khả năng đồng thời của Java 21 mà vẫn kiểm soát CPU, bộ nhớ và tài nguyên bên ngoài.
