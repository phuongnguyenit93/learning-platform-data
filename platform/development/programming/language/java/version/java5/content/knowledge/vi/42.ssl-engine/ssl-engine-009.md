# Xử lý tác vụ được giao qua getDelegatedTask và phối hợp I/O không chặn

## 1. Vì sao engine TLS còn cần tác vụ bên ngoài?

`SSLEngine` tách xử lý TLS khỏi việc đọc/ghi mạng. Tuy nhiên, một bước bắt tay có thể cần công việc mất thời gian, chẳng hạn kiểm tra chuỗi chứng chỉ, truy cập dịch vụ xác minh hoặc tính toán mật mã. Nếu mọi công việc ấy chạy ngay trên luồng xử lý hàng nghìn kết nối, một kết nối chậm có thể làm các kết nối khác bị chậm theo.

Khi cần kết quả công việc được giao, engine báo `HandshakeStatus.NEED_TASK`. Ứng dụng lấy các `Runnable` bằng `getDelegatedTask()` và thực thi chúng. Phương thức này trả từng tác vụ đang chờ đúng một lần, rồi trả `null` khi không còn tác vụ có thể lấy tại thời điểm đó. Tác vụ đã lấy vẫn cần được chạy; `null` không chứng minh rằng những tác vụ đã giao cho luồng khác đều hoàn thành. Xem [SSLEngine.getDelegatedTask](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngine.html#getDelegatedTask()).

Phân biệt hai việc:

- **Lấy tác vụ**: chuyển trách nhiệm thực thi một đối tượng `Runnable` sang ứng dụng.
- **Hoàn thành tác vụ**: `run()` đã trả về, kết quả đã được chuyển về nơi điều phối để tiếp tục TLS.

Một `Future` được tạo thành công hoặc `executor.execute()` trả về chỉ xác nhận công việc được tiếp nhận; chưa xác nhận bắt tay đã tiếp tục được.

## 2. Hiểu đúng NEED_TASK trong máy trạng thái

`HandshakeStatus` trả lời engine đang cần gì để tiến triển; nó khác với `Status` như `OK`, `CLOSED`, `BUFFER_UNDERFLOW` hoặc `BUFFER_OVERFLOW`.

| Trạng thái bắt tay | Hướng điều phối |
| --- | --- |
| `NEED_TASK` | Lấy tác vụ đang chờ, thực thi, đợi tín hiệu hoàn thành rồi đánh giá lại |
| `NEED_WRAP` | Cho engine tạo dữ liệu TLS gửi đi; nguồn ứng dụng có thể rỗng |
| `NEED_UNWRAP` | Dùng dữ liệu mạng đã có hoặc đợi đọc thêm khi thiếu |
| `FINISHED` | Một kết quả `wrap()`/`unwrap()` vừa hoàn tất bắt tay |
| `NOT_HANDSHAKING` | Hiện không ở trong quá trình bắt tay; vẫn phải quản lý I/O và đóng kết nối |

`FINISHED` xuất hiện trong kết quả thao tác, không phải giá trị lấy từ `engine.getHandshakeStatus()`. Không viết vòng kiểm tra phương thức đó để chờ `FINISHED`. Trên API hiện đại còn có `NEED_UNWRAP_AGAIN` dành cho DTLS; không gom tất cả trạng thái còn lại thành “chờ socket đọc”. Xem [SSLEngineResult.HandshakeStatus](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngineResult.HandshakeStatus.html).

Bài này tập trung vào mô hình TLS trên TCP với một vòng lặp sự kiện; không đưa giao thức hay cơ chế bảo mật cũ vào ví dụ.

## 3. Mô hình dễ kiểm soát: một luồng sở hữu kết nối

Một thiết kế thực tế là giao mỗi kết nối cho một luồng điều phối (owner thread), thường chính là luồng vòng lặp sự kiện.

```text
Luồng điều phối                        Nhóm luồng tác vụ
----------------                      ------------------
wrap/unwrap nhận NEED_TASK
lấy hết tác vụ hiện có
đánh dấu tasksInFlight = true
gửi một đợt tác vụ ------------------> chạy từng Runnable
trả về phục vụ kết nối khác            ghi thông báo hoàn thành
                                      đánh thức vòng lặp
nhận thông báo <----------------------
tasksInFlight = false
đọc trạng thái engine mới nhất
tiếp tục máy trạng thái TLS
```

Luồng điều phối sở hữu các bộ đệm mạng/ứng dụng, hàng đợi gửi, trạng thái đóng, `SelectionKey` và biến `tasksInFlight`. Luồng tác vụ chỉ chạy các `Runnable` đã được lấy, rồi gửi thông báo hoàn thành. Nó không tự gọi `wrap()`, không đổi `interestOps` và không ghi trực tiếp vào bộ đệm của ứng dụng.

Trong thiết kế này, khi một đợt tác vụ của kết nối đang chạy, tạm dừng các thao tác engine của chính kết nối đó. Đây là cách tuần tự hóa được chọn để dễ chứng minh tính đúng đắn, không phải tuyên bố rằng mọi thao tác của SSLEngine đều chỉ có thể chạy trên cùng một luồng. Các kết nối khác vẫn tiếp tục hoạt động.

Có thể vẫn gửi phần dữ liệu TLS đã được tạo và đang chờ trong `netOut`, vì thao tác ghi socket không cần gọi lại engine. Có thể nhận thêm dữ liệu mạng vào vùng trống đã quản lý, nhưng phải có giới hạn; không để dữ liệu tích lũy vô hạn trong lúc chờ tác vụ.

## 4. Một lượt NEED_TASK cần làm đủ những bước nào?

### 4.1. Lấy hết tác vụ hiện có

Phần lấy tác vụ có thể được viết như sau; đây là đoạn tích hợp cần một engine đã được cấu hình và một máy trạng thái kết nối bao quanh:

```java
List<Runnable> batch = new ArrayList<>();
Runnable task;
while ((task = engine.getDelegatedTask()) != null) {
    batch.add(task);
}
```

Không chỉ lấy một tác vụ rồi quên các tác vụ còn lại. Cũng không lưu tác vụ để chạy lại sau khi nó đã hoàn thành: mỗi đối tượng đã lấy chỉ được giao thực thi một lần.

Nếu đang có `tasksInFlight`, không gọi lại nhánh này để gửi một đợt thứ hai cho cùng kết nối. Nếu chưa có đợt nào đang chạy, engine vẫn báo `NEED_TASK` nhưng không lấy được tác vụ nào, hãy kiểm tra lại trạng thái và quy tắc sở hữu; nếu không có cách tiến triển, ghi lỗi nhất quán và kết thúc kết nối theo chính sách thay vì lặp bận.

### 4.2. Đánh dấu trước khi gửi đi

Thứ tự cần giữ là:

1. Lấy đợt tác vụ trên luồng sở hữu.
2. Đánh dấu đợt đó đang chạy, kèm mã nhận diện kết nối/đợt nếu có.
3. Gửi công việc tới executor.
4. Trả về vòng lặp sự kiện ngay.
5. Khi thông báo hoàn thành được xử lý trên luồng sở hữu, mới bỏ cờ và tiếp tục.

Đặt cờ sau khi gửi có thể tạo khe hở: tác vụ ngắn hoàn tất và phát thông báo trước khi trạng thái kết nối được cập nhật.

Nếu executor từ chối tiếp nhận, phải chuyển kết nối sang nhánh thất bại một cách nhất quán. Không để `tasksInFlight=true` vĩnh viễn; cũng không bỏ cờ rồi tiếp tục dùng engine như thể tác vụ đã chạy.

### 4.3. Đợi bằng sự kiện, không chặn luồng điều phối

Trên luồng vòng lặp sự kiện, tránh:

```java
future.get();
future.join();
latch.await();
```

Các dòng trên là ví dụ về cách **không nên chờ tại vị trí này**, không phải đoạn mã để chèn vào bộ điều phối. Chúng làm cả luồng dừng lại cho đến khi công việc xong.

Thay vào đó, luồng tác vụ đưa kết quả vào hàng đợi an toàn giữa các luồng, sau đó gọi cơ chế đánh thức vòng lặp. Với Java NIO, thường dùng `selector.wakeup()`. Hàng đợi chứa thông báo cần xử lý; wakeup chỉ làm luồng thoát khỏi/chưa bước vào trạng thái chọn đang chặn, không tự chạy thông báo và không tự thay đổi trạng thái TLS. Xem [Selector.wakeup](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html#wakeup()).

Thứ tự phải là **đưa thông báo vào hàng đợi trước, đánh thức sau**. Vòng lặp lấy thông báo cả trước và sau bước chờ I/O để không phụ thuộc việc có socket mới sẵn sàng.

## 5. Ví dụ chạy được: giao việc và tiếp tục trên đúng luồng

Chương trình dưới đây minh họa riêng việc giao một đợt công việc, truyền kết quả và quay lại luồng sở hữu. Hai công việc mẫu chỉ ghi dấu vết; chúng **không phải tác vụ TLS thật và không chứng minh một lần bắt tay đã thành công**.

Hàm `collectTasks()` cho thấy cách lấy tác vụ từ engine thật khi tích hợp, nhưng không được gọi trong phần chạy mẫu. Mẫu dùng `LockSupport` làm cơ chế chờ/đánh thức đơn giản để không cần mở socket; ứng dụng NIO thay phần đó bằng selector và xử lý thêm các key sẵn sàng.

Lưu thành `DelegatedTaskDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Queue;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.LockSupport;
import javax.net.ssl.SSLEngine;

public class DelegatedTaskDemo {
    record Completion(Throwable failure) {}

    // Chi goi tren luong so huu engine, khi chua co dot tac vu dang chay.
    static List<Runnable> collectTasks(SSLEngine engine) {
        List<Runnable> tasks = new ArrayList<>();
        Runnable task;
        while ((task = engine.getDelegatedTask()) != null) {
            tasks.add(task);
        }
        return tasks;
    }

    static void submitBatch(List<Runnable> tasks, ThreadPoolExecutor workers,
                            Queue<Completion> completed, Runnable wakeup) {
        List<Runnable> batch = List.copyOf(tasks);
        workers.execute(() -> {
            Throwable failure = null;
            try {
                for (Runnable task : batch) {
                    task.run();
                }
            } catch (Throwable ex) {
                failure = ex;
            } finally {
                completed.add(new Completion(failure));
                wakeup.run();
            }
        });
    }

    public static void main(String[] args) throws Exception {
        Thread owner = Thread.currentThread();
        Queue<Completion> completed = new ConcurrentLinkedQueue<>();
        List<String> trace = new ArrayList<>();
        ThreadPoolExecutor workers = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(8),
                new ThreadPoolExecutor.AbortPolicy());

        try {
            // Hai cong viec mau, khong phai tac vu TLS that.
            List<Runnable> tasks = List.of(
                    () -> trace.add("first"),
                    () -> trace.add("second"));
            System.out.println("submitted=" + tasks.size());
            submitBatch(tasks, workers, completed,
                    () -> LockSupport.unpark(owner));
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);

            boolean done = false;
            while (!done) {
                Completion result;
                while ((result = completed.poll()) != null) {
                    if (result.failure() != null) {
                        throw new IllegalStateException(
                                "Delegated batch failed", result.failure());
                    }
                    System.out.println("trace=" + trace);
                    System.out.println("resumedOnOwner="
                            + (Thread.currentThread() == owner));
                    done = true;
                }
                if (!done) {
                    if (System.nanoTime() >= deadline) {
                        throw new IllegalStateException("Demo timed out");
                    }
                    LockSupport.parkNanos(TimeUnit.MILLISECONDS.toNanos(100));
                }
            }
        } finally {
            workers.shutdown();
            // Cho ket thuc chuong trinh mau; khong dat lenh nay trong event loop.
            if (!workers.awaitTermination(5, TimeUnit.SECONDS)) {
                workers.shutdownNow();
            }
        }
    }
}
```

Chạy bằng JDK 17+:

```shell
javac --release 17 -encoding UTF-8 DelegatedTaskDemo.java
java DelegatedTaskDemo
```

Hoặc chạy tệp nguồn trực tiếp:

```shell
java DelegatedTaskDemo.java
```

Kết quả:

```text
submitted=2
trace=[first, second]
resumedOnOwner=true
```

Điểm cần đọc trong ví dụ:

- Nhóm luồng có một luồng và hàng đợi hữu hạn. Một đợt chạy tuần tự giúp việc đếm hoàn thành đơn giản; nhiều kết nối trong hệ thống thực tế có thể dùng chung một nhóm luồng phù hợp.
- Danh sách `trace` được luồng tác vụ ghi, sau đó luồng sở hữu đọc **sau khi lấy thông báo từ hàng đợi**. Không có hai luồng đồng thời sửa danh sách này.
- `ConcurrentLinkedQueue` bảo đảm quan hệ công bố bộ nhớ từ thao tác trước khi đưa thông báo vào hàng đợi tới thao tác sau khi luồng khác lấy thông báo đó. Chỉ có wakeup mà không có cơ chế truyền dữ liệu đồng bộ thì chưa đủ. Xem [ConcurrentLinkedQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html).
- `parkNanos()` có thể trở về dù chưa có thông báo; vòng lặp luôn kiểm tra lại hàng đợi. Tương tự, ứng dụng không được coi một lần selector thức dậy là bằng chứng tác vụ đã xong.
- `finally` trong công việc gửi thông báo cả khi tác vụ ném lỗi. Ở hệ thống thật, phân loại lỗi nghiêm trọng của JVM theo chính sách vận hành; không bắt `Throwable` để âm thầm tiếp tục sử dụng một engine đã thất bại.
- `awaitTermination()` chỉ nằm ở bước kết thúc chương trình mẫu; không đặt nó vào vòng lặp phục vụ kết nối.
- Bộ đếm thời gian 5 giây là giới hạn của ví dụ điều phối, không phải giá trị timeout bắt tay TLS áp dụng cho mọi hệ thống.

## 6. Sau thông báo hoàn thành, phải đánh giá lại I/O

Khi nhận kết quả thành công, không khôi phục nguyên trạng thái `NEED_TASK` cũ. Đọc trạng thái mới của engine trên luồng sở hữu, rồi điều phối:

- Nếu `NEED_WRAP`, thử tạo dữ liệu TLS dù hàng đợi ứng dụng chưa có dữ liệu; nếu tạo được byte, đưa chúng vào đường gửi.
- Nếu `NEED_UNWRAP`, dùng byte đang có trước; chỉ chờ đọc mạng khi thực sự cần thêm byte.
- Nếu lại `NEED_TASK`, lấy đợt mới theo cùng quy tắc.
- Nếu không còn bắt tay, tiếp tục I/O ứng dụng hoặc quy trình đóng tùy trạng thái kết nối.

`interestOps` mô tả điều kiện mạng cần theo dõi, không trực tiếp biểu diễn mọi trạng thái TLS:

| Điều kiện của kết nối | Quan tâm sự kiện nào? |
| --- | --- |
| `netOut` còn byte chưa gửi được | Theo dõi `OP_WRITE` để gửi tiếp |
| Đã gửi hết `netOut` | Bỏ `OP_WRITE` nếu không có nhu cầu ghi khác |
| Cần dữ liệu mạng và còn chỗ chứa | Theo dõi `OP_READ` |
| Đang chờ tác vụ, vùng nhận đã đầy | Tạm ngừng quan tâm đọc; tiếp tục khi giải phóng được chỗ |
| Chỉ chờ tác vụ hoàn thành, chưa có nhu cầu mạng | Chờ hàng đợi hoàn thành/wakeup; không tự quay vòng gọi engine |

Không bật `OP_WRITE` thường trực chỉ vì đang bắt tay: socket thường xuyên sẵn sàng ghi sẽ làm vòng lặp thức liên tục dù không có byte để gửi. Cũng không đợi `OP_READ` sau mọi lần hoàn thành tác vụ: nếu trạng thái mới là `NEED_WRAP`, phía đối tác có thể đang chờ chính thông điệp cần được tạo đó.

Sau `wrap()`/`unwrap()`, vẫn xử lý số byte đã tiêu thụ/sinh ra và các trạng thái bộ đệm. Tác vụ hoàn thành không tự giải quyết tình trạng đầu vào thiếu byte hay đầu ra thiếu chỗ.

## 7. Nhóm luồng, lỗi và vòng đời kết nối

### Hạn chế tài nguyên

Dùng executor có giới hạn và chính sách từ chối rõ ràng. Hàng đợi không giới hạn có thể biến nhiều lần bắt tay thành lượng công việc tồn đọng lớn.

Không chọn `CallerRunsPolicy` một cách vô thức cho executor được gọi từ vòng lặp sự kiện: khi quá tải, nó chạy công việc ngay trên luồng điều phối, làm mất mục tiêu tách công việc chậm. Không dùng chính sách loại bỏ công việc âm thầm, vì engine có thể chờ một kết quả không bao giờ tới.

Đo riêng thời gian đợi trong hàng đợi và thời gian thực thi. Một nhóm luồng quá nhỏ hoặc dịch vụ kiểm tra chứng chỉ chậm có thể làm timeout tăng dù socket không có vấn đề.

API cho phép nhiều delegated task chạy song song. Nếu chọn cách đó, cần đếm tất cả tác vụ trong đợt và chỉ tiếp tục engine khi đợt đã hoàn tất; không tiếp tục sau tác vụ đầu tiên. Chạy tuần tự theo đợt là lựa chọn đơn giản trong bài, không phải yêu cầu của API.

### Đưa thất bại về nơi sở hữu kết nối

Đừng chỉ `submit()` rồi bỏ qua `Future`: lỗi có thể bị giữ trong future trong khi kết nối vẫn chờ. Cần có đường báo lỗi về vòng lặp.

Một tác vụ trả về bình thường cũng không có nghĩa chứng chỉ đã được chấp nhận hoặc bắt tay đã thành công. Tiếp tục máy trạng thái và xử lý `SSLException` nếu engine báo lỗi ở thao tác tiếp theo. Không tắt kiểm tra chứng chỉ để làm nhánh lỗi biến mất.

### Timeout và kết nối đã đóng

Mỗi thông báo nên mang định danh kết nối và thế hệ/đợt công việc. Nếu kết nối đã hết hạn hoặc đối tượng quản lý đã được tái sử dụng cho kết nối khác, bỏ qua thông báo cũ; không để nó đánh thức hoặc đổi cờ của kết nối mới.

Trong khi tác vụ còn chạy, yêu cầu đóng cần được tuần tự hóa. Có thể dừng tiếp nhận dữ liệu, đánh dấu đóng và đóng transport theo chính sách; không đồng thời dùng engine cho một luồng xử lý mới. Nếu cần gọi các thao tác đóng của engine, điều phối chúng khi không còn đợt tác vụ đang hoạt động.

`Future.cancel(true)` chỉ là yêu cầu ngắt; nó không bảo đảm mã của provider hoặc lời gọi bên ngoài dừng ngay. Đặt deadline là quyết định dừng chờ/phục vụ kết nối, không phải bằng chứng tác vụ nền đã chấm dứt. Không tái sử dụng engine hoặc bộ nhớ đang được tác vụ tham chiếu chỉ vì đã hủy future.

## 8. Tình huống kiểm chứng và lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp |
| --- | --- |
| Mọi kết nối cùng khựng khi một lần bắt tay chậm | Chạy tác vụ trực tiếp hoặc chờ future trên vòng lặp sự kiện |
| Tác vụ chạy xong nhưng kết nối đứng yên | Thiếu thông báo hoàn thành, thiếu wakeup hoặc không gọi lại máy trạng thái |
| CPU cao khi đang chờ tác vụ | Lặp trên NEED_TASK hoặc bật OP_WRITE khi không có dữ liệu |
| Gửi trùng một công việc | Không có cờ/định danh cho đợt đang chạy |
| Kết nối chờ mãi khi executor quá tải | Công việc bị bỏ hoặc từ chối nhưng không cập nhật trạng thái thất bại |
| Engine bị gọi từ hai nơi ngoài dự kiến | Luồng tác vụ tự tiếp tục wrap/unwrap thay vì gửi thông báo về owner |
| Kết nối mới bị đổi trạng thái bởi callback cũ | Không kiểm tra định danh/thế hệ khi nhận hoàn thành |

Ca kiểm tra nên có:

1. Tác vụ hoàn thành ngay trước khi vòng lặp bước vào chờ; thông báo vẫn phải được xử lý.
2. Tác vụ hoàn thành khi vòng lặp đang ngủ; wakeup phải làm kết nối tiếp tục mà không cần thêm gói mạng.
3. Executor từ chối công việc; kết nối phải thất bại hữu hạn, không kẹt cờ.
4. Tác vụ ném lỗi; nhánh hoàn thành thất bại phải chạy đúng một lần.
5. Kết nối đóng trước khi tác vụ hoàn tất; callback cũ không được phục hồi kết nối.
6. Có dữ liệu TLS chưa gửi trong lúc tác vụ chạy; vẫn giữ thứ tự byte và không tạo vòng lặp ghi rỗng.

Nhật ký phục vụ chẩn đoán nên ghi định danh kết nối, mã đợt, số tác vụ, thời gian đợi/chạy, trạng thái trước–sau và lý do thất bại. Những thông tin này giúp phân biệt nghẽn mạng, nghẽn nhóm luồng và lỗi phối hợp mà không cần ghi dữ liệu nhạy cảm của phiên TLS.
