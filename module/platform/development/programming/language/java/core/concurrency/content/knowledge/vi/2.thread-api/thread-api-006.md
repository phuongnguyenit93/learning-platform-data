# Daemon thread và user thread khi JVM kết thúc

Trong Java, một luồng (`Thread`) có thể là **user thread** (luồng thông thường, không phải daemon) hoặc **daemon thread** (luồng nền). Sự khác biệt quan trọng nhất là **JVM có chờ luồng đó trước khi tự kết thúc hay không**. Đây là quy tắc về vòng đời tiến trình Java, không phải cách phân loại mức độ ưu tiên CPU hay độ quan trọng của công việc.

## 1. Quy tắc JVM kết thúc

Trong trường hợp chương trình kết thúc bình thường, JVM bắt đầu quá trình shutdown khi **không còn luồng non-daemon nào đang sống**. JVM không cần đợi các daemon thread hoàn thành. Có thể hình dung:

| Trạng thái | JVM có thể tự kết thúc? | Giải thích |
|---|---|---|
| `main` đã trả về, còn một user thread đang chạy/chờ | Chưa | User thread vẫn giữ JVM sống. |
| `main` đã trả về, chỉ còn daemon thread | Có | Daemon không giữ JVM sống; có thể bị dừng giữa chừng. |
| Tất cả user thread đều đã kết thúc | Có | JVM bắt đầu shutdown thông thường. |
| Có lời gọi `System.exit(status)` | Có, bắt đầu shutdown | Lời gọi này chủ động khởi động shutdown ngay cả khi vẫn có user thread. |
| Có lời gọi `Runtime.getRuntime().halt(status)` | Kết thúc cưỡng bức | Bỏ qua quá trình shutdown thông thường, kể cả shutdown hooks. |

**Phân biệt hai thời điểm:** phương thức `main()` kết thúc **không đồng nghĩa** tiến trình JVM kết thúc. `main` thường chạy trên một user thread. Khi `main` trả về, các user thread khác vẫn có thể tiếp tục chạy; khi chỉ còn daemon, JVM có thể đóng tiến trình mà không chờ chúng.

Quy tắc trên nói về điều kiện JVM duy trì sự sống của tiến trình; nó **không** bảo đảm mọi công việc trên user thread hoàn thành trong mọi hoàn cảnh. `System.exit`, `halt`, lỗi nghiêm trọng của tiến trình hay việc hệ điều hành chấm dứt tiến trình có thể khiến công việc chưa xong.

## 2. Daemon được tạo và kiểm tra như thế nào?

Với **platform thread** thông thường của Java:

- `thread.isDaemon()` trả về trạng thái daemon của một luồng. `Thread.currentThread().isDaemon()` kiểm tra luồng đang thực thi.
- `new Thread(...)` mặc định **kế thừa trạng thái daemon của luồng tạo nó**, trừ khi gọi `setDaemon(...)` để đổi trước khi chạy. Vì `main` thông thường là user thread, luồng được tạo trực tiếp từ `main` thường cũng là user thread.
- `thread.setDaemon(true)` đánh dấu luồng là daemon; `thread.setDaemon(false)` đánh dấu là user thread. Phải thiết lập **trước `start()`**; đổi trên một luồng đang chạy có thể ném `IllegalThreadStateException`.
- `thread.start()` tạo hoạt động chạy bất đồng bộ; gọi trực tiếp `thread.run()` chỉ chạy phương thức như một lời gọi bình thường trên luồng hiện tại.
- `isAlive()` phản ánh luồng đã bắt đầu và chưa kết thúc, **độc lập** với `isDaemon()`. Daemon vẫn có thể ở trạng thái `RUNNABLE`, `WAITING` hoặc `TIMED_WAITING`.

Tên gọi *daemon* **không** có nghĩa JVM ưu tiên chạy nó ít hơn, tự ngắt (interrupt) nó, hoặc gọi `finally` để dọn dẹp trước khi thoát. Daemon vẫn chạy theo cơ chế lập lịch luồng thông thường khi tiến trình còn sống.

> Phạm vi phiên bản: các ví dụ bên dưới dùng Java 17+ với platform threads. Từ **Java 21**, virtual threads luôn là daemon và không giữ JVM sống; API tạo virtual thread không có trong Java 17.

## 3. Ví dụ 1 — User thread có thể giữ JVM sống sau `main`

Tạo tệp `UserThreadExample.java`:

```java
import java.util.concurrent.CountDownLatch;

public class UserThreadExample {
    public static void main(String[] args) {
        CountDownLatch release = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                release.await();
                System.out.println("User worker finished");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "user-worker");

        System.out.println("worker.isDaemon() = " + worker.isDaemon());
        worker.start();
        System.out.println("Main is finishing");
        release.countDown();
    }
}
```

Biên dịch và chạy:

```bash
javac UserThreadExample.java
java UserThreadExample
```

Kết quả:

```text
worker.isDaemon() = false
Main is finishing
User worker finished
```

`worker` mặc định không phải daemon do được tạo từ `main`. `CountDownLatch` giữ worker chờ cho tới khi dòng `Main is finishing` được in, vì vậy thứ tự thông báo là xác định trong lần chạy bình thường. Phương thức `main` **không gọi `join()`**; JVM vẫn phải tính đến worker nếu worker còn sống sau khi `main` trả về. Lưu ý: một lịch chạy cụ thể cũng có thể cho worker hoàn thành trước khi `main` thực sự trả về; điều đó không thay đổi quy tắc JVM.

Hãy thử thay `release.countDown();` bằng một thao tác không bao giờ mở khóa latch: worker non-daemon sẽ chờ mãi và tiến trình có thể không tự thoát. Đó là **minh họa để suy luận**, không nên để chương trình treo khi thực hành.

## 4. Ví dụ 2 — Daemon không giữ JVM sống

Tạo tệp `DaemonThreadExample.java`:

```java
import java.util.concurrent.CountDownLatch;

public class DaemonThreadExample {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);

        Thread background = new Thread(() -> {
            System.out.println("Daemon started");
            started.countDown();

            try {
                neverReleased.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                System.out.println("Daemon cleanup");
            }
        }, "background");

        background.setDaemon(true); // Phải trước start().
        background.start();
        started.await();
        System.out.println("Main is finishing");
    }
}
```

```bash
javac DaemonThreadExample.java
java DaemonThreadExample
```

Đầu ra khi chạy bình thường:

```text
Daemon started
Main is finishing
```

Latch `started` giúp bảo đảm daemon đã in dòng đầu trước khi `main` tiếp tục. `neverReleased` không bao giờ được mở, nên daemon vẫn chờ. Khi `main` kết thúc, không còn user thread do ứng dụng tạo giữ JVM sống và JVM có thể đóng tiến trình. Dòng `Daemon cleanup` **không được bảo đảm xuất hiện**: JVM không cần đánh thức daemon và không bảo đảm thực thi `finally` của luồng đang chờ.

Điểm cần nhớ: `setDaemon(true)` giải quyết chuyện **luồng có giữ tiến trình sống hay không**; nó **không phải** cơ chế đóng luồng sạch sẽ. Nếu daemon đang ghi tệp, phát sự kiện, gửi dữ liệu hoặc cập nhật trạng thái, công việc có thể bị bỏ dở.

## 5. Ví dụ 3 — Chủ động dừng luồng rồi đợi hoàn thành

Nếu muốn dọn dẹp chắc chắn theo luồng điều khiển bình thường, ứng dụng phải tự phối hợp dừng và đợi worker hoàn tất. Đây là ví dụ dùng một tín hiệu dừng và `join()`, dù worker được đánh dấu daemon.

Tạo tệp `GracefulDaemonExample.java`:

```java
import java.util.concurrent.CountDownLatch;

public class GracefulDaemonExample {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch stop = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                System.out.println("Worker started");
                started.countDown();
                stop.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                System.out.println("Worker cleaned up");
            }
        }, "cleanup-worker");

        worker.setDaemon(true);
        worker.start();

        started.await();
        System.out.println("Requesting stop");
        stop.countDown();
        worker.join();
        System.out.println("Main finished after join");
    }
}
```

```bash
javac GracefulDaemonExample.java
java GracefulDaemonExample
```

Kết quả:

```text
Worker started
Requesting stop
Worker cleaned up
Main finished after join
```

`stop.countDown()` là tín hiệu để worker thoát chờ; `worker.join()` khiến `main` đợi worker kết thúc, do đó dòng dọn dẹp được in trước thông báo cuối. `join()` dùng được với **cả daemon và user thread**. Trường hợp thực tế cũng cần chiến lược xử lý khi worker không chịu dừng (ví dụ thời hạn chờ bằng `join(timeout)`, ghi log lỗi và quyết định mức độ an toàn của việc thoát).

**Không dùng `Thread.stop()`** để cưỡng ép dừng: API này đã lỗi thời và không an toàn. Với công việc thực tế, dùng cơ chế hủy hợp tác như cờ trạng thái có bảo đảm hiển thị bộ nhớ (`volatile`/`AtomicBoolean`), `interrupt()`, hàng đợi/tín hiệu hoặc API quản lý vòng đời phù hợp. Nếu xử lý `InterruptedException` mà không tiếp tục ném lỗi, thường nên khôi phục cờ interrupt bằng `Thread.currentThread().interrupt()`.

## 6. Những trường hợp dễ nhầm

### `main` trả về nhưng ứng dụng vẫn chạy

Nguyên nhân thường là một user thread đang chờ khóa, chờ I/O hoặc chạy vòng lặp không có điều kiện dừng. Đặt tên thread và quan sát trạng thái bằng thread dump (`jcmd <pid> Thread.print` trên JDK phù hợp), rồi xác định thành phần nào tạo ra luồng đó. Việc đánh dấu toàn bộ luồng thành daemon chỉ để ứng dụng thoát có thể che giấu lỗi quản lý tài nguyên.

### Executor và thread pool

Khi tạo `ExecutorService`, cần quản lý thời điểm không nhận thêm việc và thời điểm dừng worker, ví dụ `shutdown()`, `awaitTermination(...)` và khi thật sự cần thiết mới xem xét `shutdownNow()`. Với các thread factory thường gặp, worker của pool có thể là non-daemon và giữ JVM sống. Không nên dựa vào việc `main` kết thúc để tự dọn pool. `shutdownNow()` chỉ **cố gắng** hủy tác vụ đang chạy, thường thông qua interrupt; tác vụ phớt lờ interrupt có thể tiếp tục.

### Shutdown hook không làm daemon trở nên an toàn tuyệt đối

`Runtime.getRuntime().addShutdownHook(thread)` đăng ký một luồng **chưa được `start()`** để JVM khởi chạy trong quá trình shutdown thông thường. Hook hữu ích để phát tín hiệu ngừng và thu hồi tài nguyên có kiểm soát, nhưng các hook có thể chạy đồng thời, có thể bị treo, và không chạy khi `Runtime.halt()` hoặc khi tiến trình bị kết thúc cưỡng bức. Không giả định daemon sẽ được đợi hay toàn bộ `finally` của daemon sẽ chạy chỉ vì có shutdown hook.

### `System.exit(0)` và `return` là hai việc khác nhau

- `return` trong `main`: chỉ kết thúc lời gọi `main`; JVM tiếp tục nếu còn user thread.
- `System.exit(0)`: yêu cầu JVM bắt đầu quá trình shutdown thông thường dù có user thread đang chạy; các shutdown hook đã đăng ký có cơ hội thực thi.
- `Runtime.getRuntime().halt(0)`: dừng cưỡng bức, bỏ qua shutdown hooks; không dùng như giải pháp quản lý luồng hằng ngày.

### Daemon khác với độ ưu tiên và tính đúng đắn của dữ liệu

`setDaemon(true)` không thay `setPriority(...)`, không bảo đảm chạy theo lịch biểu cụ thể và không bảo đảm hoàn thành task. Một daemon giữ khóa hoặc đang cập nhật dữ liệu vẫn có thể ảnh hưởng các user thread trong lúc JVM còn chạy. Với nhiệm vụ bắt buộc hoàn thành, cần có điểm chờ hoàn tất rõ ràng, cơ chế lưu bền và xử lý lỗi phù hợp.

## 7. Cách chọn trong chương trình Java

| Loại công việc | Lựa chọn thường hợp lý | Điều kiện quan trọng |
|---|---|---|
| Tính toán hoặc ghi dữ liệu bắt buộc hoàn thành trước khi thoát | User thread, hoặc executor được quản lý rõ vòng đời | Dừng nhận việc, chờ hoàn thành, xử lý lỗi. |
| Giám sát nền mang tính phụ trợ, có thể bỏ dở khi tiến trình đóng | Có thể dùng daemon | Không đặt tính đúng đắn của dữ liệu vào việc daemon chạy đến cuối. |
| Nền định kỳ nhưng phải flush dữ liệu/báo cáo | Chọn theo yêu cầu hoàn thành và quản lý shutdown riêng | Có tín hiệu dừng và chờ hoàn thành phần quan trọng. |
| Thread pool xử lý nhiều tác vụ | Quản lý executor tường minh | Gọi shutdown và đợi theo thời hạn; hiểu hành vi thread factory. |

Câu hỏi quyết định là: **“Nếu JVM đóng ngay sau khi tất cả user thread kết thúc, công việc của luồng này có thể bị bỏ dở mà vẫn chấp nhận được không?”** Nếu câu trả lời là không, không được chỉ dựa vào daemon. Ngược lại, một luồng non-daemon cũng cần cơ chế dừng để tránh giữ ứng dụng sống vô hạn.

## 8. Tự kiểm tra kiến thức

1. **Vì sao in xong dòng cuối của `main` mà tiến trình chưa thoát?** Vì vẫn có thể còn user thread đang sống; kiểm tra thread dump và vòng đời executor/worker.
2. **`setDaemon(true)` có khiến `finally` của worker luôn chạy?** Không. JVM không đợi daemon và có thể dừng tiến trình khi daemon đang chờ hoặc đang xử lý.
3. **Đặt `setDaemon(true)` sau `start()` được không?** Không được dùng cách đó; phải cấu hình trước khi start, nếu cố thay khi thread đang sống sẽ gặp `IllegalThreadStateException`.
4. **Có thể dùng `join()` với daemon không?** Có. Daemon mô tả điều kiện giữ JVM sống; `join()` là lời gọi đợi một thread kết thúc.
5. **Tại sao `System.exit(0)` khác `return` ở `main`?** `System.exit` chủ động khởi động shutdown; `return` chỉ trả về từ `main`.

**Ghi nhớ:** user thread có thể giữ JVM sống; daemon thread không giữ JVM sống; **muốn kết thúc công việc an toàn phải điều phối dừng và chờ hoàn thành một cách tường minh**.
