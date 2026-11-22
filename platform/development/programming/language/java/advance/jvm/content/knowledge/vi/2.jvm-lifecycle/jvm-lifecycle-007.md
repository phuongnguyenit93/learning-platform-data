# Shutdown hook, System.exit và Runtime.halt trong quá trình kết thúc JVM

## Mục tiêu bài học

Khi kết thúc một tiến trình Java, điều quan trọng không chỉ là *khi nào* JVM dừng mà còn là *có thời gian dọn dẹp tài nguyên hay không*. Bài này giúp bạn:
- Giải thích những sự kiện kích hoạt quá trình shutdown của JVM, kể cả khi `main()` đã kết thúc.
- Hiểu cơ chế đăng ký, bắt đầu và hoàn tất **shutdown hook**, tính đồng thời và các giới hạn của nó.
- Phân biệt **kết thúc tự nhiên**, **`System.exit(int)` / `Runtime.exit(int)`** và **`Runtime.halt(int)`**.
- Viết, chạy và giải thích chương trình Java 17+ minh họa; nhận diện những trường hợp `finally` hoặc shutdown hook không được thực thi.
- Xây dựng chiến lược **graceful shutdown** có giới hạn thời gian cho ứng dụng nhiều luồng.

## 1. JVM bắt đầu shutdown vào lúc nào?

Một ứng dụng Java không nhất thiết dừng ngay khi phương thức `main()` trả về. Phương thức `main()` chạy trên một luồng; nếu còn những **non-daemon thread** đang sống, JVM thông thường vẫn tiếp tục hoạt động. JVM có thể bắt đầu trình tự shutdown khi:

1. **Không còn non-daemon thread sống**: các công việc nền không phải daemon đã hoàn thành và không còn luồng giữ JVM hoạt động.
2. **Có yêu cầu thoát chủ động**: chương trình gọi `System.exit(status)` hoặc `Runtime.getRuntime().exit(status)`.
3. **Có sự kiện bên ngoài được JVM nhận diện là yêu cầu kết thúc**: ví dụ một số tín hiệu từ hệ điều hành hoặc thao tác ngắt ứng dụng mà JVM hỗ trợ.

Ba loại trên có thể kích hoạt **shutdown sequence**. Trái lại, một số tình huống cưỡng bức kết thúc như **SIGKILL** trên Unix, **TerminateProcess** trên Windows, mất điện, lỗi native nghiêm trọng hoặc trình quản lý tiến trình cưỡng bức kết thúc có thể làm JVM dừng mà không cho hook chạy. Không được xem shutdown hook là cơ chế bảo đảm thực thi trong *mọi* trường hợp chết tiến trình.

### Non-daemon và daemon thread

- **Non-daemon** còn sống thường giữ JVM tồn tại sau khi `main()` kết thúc, cho đến khi shutdown được yêu cầu.
- **Daemon thread** không ngăn JVM bắt đầu shutdown chỉ vì nó còn sống.
- Khi shutdown đã bắt đầu, các hook chạy **đồng thời với những thread đang sống**, kể cả daemon và non-daemon. Vì vậy thread khác có thể vẫn đang thao tác trên tài nguyên mà hook định đóng.

Điều kiện “không còn non-daemon thread” là quy tắc quan trọng trong ứng dụng Java thông thường; nếu JVM được nhúng và điều khiển qua JNI Invocation API, chi tiết vòng đời còn liên quan đến mã native điều khiển JVM.

## 2. Shutdown hook là gì?

**Shutdown hook** là một đối tượng `Thread` đã được tạo nhưng **chưa được `start()`**, được đăng ký với runtime để JVM chủ động bắt đầu chạy khi đi vào shutdown sequence.

API chính:

~~~java
Runtime runtime = Runtime.getRuntime();

Thread hook = new Thread(() -> {
    // Dọn dẹp ngắn gọn, có kiểm soát.
}, "cleanup-hook");

runtime.addShutdownHook(hook);
~~~

Đoạn trên **minh họa API**, chưa phải lớp chương trình Java độc lập. Runtime sẽ tự gọi `start()` cho hook ở thời điểm shutdown; người viết **không được tự `hook.start()`** để “chạy thử” cùng đối tượng đã đăng ký. Việc khởi động hook thủ công trước shutdown có thể đưa trình tự shutdown vào trạng thái hành vi không được đặc tả.

Các API có liên quan:

| API | Tác dụng |
| --- | --- |
| `Runtime.getRuntime()` | Lấy đối tượng runtime hiện hành của ứng dụng. |
| `addShutdownHook(Thread hook)` | Đăng ký một `Thread` chưa được khởi động để chạy lúc shutdown. |
| `removeShutdownHook(Thread hook)` | Bỏ đăng ký hook; trả về `true` nếu hook đã đăng ký và được xóa. |
| `System.exit(int status)` | Cách gọi thông dụng để yêu cầu JVM bắt đầu shutdown với mã trạng thái. |
| `Runtime.exit(int status)` | API nền mà `System.exit` sử dụng. |
| `Runtime.halt(int status)` | Chấm dứt JVM ngay, bỏ qua chờ các hook và không khởi tạo shutdown sequence. |

**Chỉ có thể thêm/bỏ đăng ký khi shutdown chưa bắt đầu.** Sau khi trình tự shutdown bắt đầu, `addShutdownHook` và `removeShutdownHook` sẽ ném `IllegalStateException`. Đăng ký cùng một đối tượng hook lần nữa, hoặc một `Thread` đã chạy, không hợp lệ và có thể ném `IllegalArgumentException`. Trong một số môi trường Java 17 có SecurityManager, kiểm tra quyền liên quan cũng có thể từ chối thao tác.

## 3. JVM chạy các shutdown hook như thế nào?

Mô hình khái niệm:

~~~text
Ứng dụng đang chạy
      |
      | hết non-daemon thread / System.exit / sự kiện JVM nhận diện
      v
BẮT ĐẦU SHUTDOWN SEQUENCE
      |
      +--> JVM start hook A ----------------------+
      |                                          |
      +--> JVM start hook B ----------------------+--> Tất cả hook kết thúc
      |                                          |          |
      +--> JVM start hook C ----------------------+          v
      |                                             JVM kết thúc
      +--> Các thread đang chạy vẫn có thể chạy
           đồng thời trong giai đoạn shutdown
~~~

Những điều bắt buộc phải nhớ:

1. **Thứ tự gọi `start()` và thứ tự hoàn thành các hook không được bảo đảm**. Đăng ký A trước B **không có nghĩa A sẽ chạy trước B**.
2. **Các hook chạy đồng thời**; mỗi hook là một thread riêng. Dữ liệu chung phải bảo đảm thread safety, việc đóng cùng một tài nguyên cần có kiểm soát.
3. **JVM đợi tất cả hook kết thúc** trong shutdown sequence bình thường. Một hook bị kẹt vô hạn có thể làm tiến trình treo ở shutdown.
4. Hook có thể chạy cùng các thread ứng dụng khác; không nên mặc định “toàn bộ ứng dụng đã dừng”.
5. Hook ném ngoại lệ không được bắt sẽ được xử lý như ngoại lệ của thread thông thường; hook đó kết thúc, còn các hook khác có thể tiếp tục. Không nên dùng exception để làm phương thức “chặn toàn JVM”.
6. Việc **tạo và khởi động thread khác** trong shutdown sequence có thể xảy ra, nhưng phải điều phối cẩn thận: trình tự kết thúc được xác định bởi việc *các hook* đã hoàn tất, không phải mọi công việc được tạo thêm.

Do đó, hai hook phụ thuộc chặt vào nhau (ví dụ “đóng database” và “flush các hàng đợi ghi database”) rất dễ gặp lỗi thứ tự. Giải pháp thường là **gom các bước cần đúng thứ tự vào cùng một hook** hoặc một thành phần quản lý lifecycle, thay vì trông chờ thứ tự đăng ký.

## 4. Kết thúc tự nhiên khác `System.exit` ra sao?

**Kết thúc tự nhiên:** khi luồng cuối cùng không phải daemon hoàn thành, JVM bắt đầu shutdown. Hook đã đăng ký chạy rồi JVM kết thúc.

**`System.exit(status)`:** yêu cầu kết thúc chủ động, **kể cả khi còn non-daemon thread**. Đây là lời gọi có tác động đến *toàn tiến trình JVM*, không đơn thuần dừng luồng đang gọi. `System.exit(status)` là cách thuận tiện để gọi `Runtime.getRuntime().exit(status)`.

- Quy ước phổ biến: **`status = 0`** biểu thị thành công; **nonzero** biểu thị lỗi hoặc kết thúc bất thường. Ý nghĩa cụ thể của mã thoát thuộc về ứng dụng và môi trường gọi.
- Khi exit được chấp nhận, shutdown sequence được kích hoạt; các hook được chạy và JVM kết thúc sau khi chúng hoàn thành.
- Lời gọi `exit` không quay về bình thường; các dòng mã phía sau nó trong cùng luồng sẽ không chạy.
- Không được giả định các thread đang chạy sẽ tự hoàn thành tác vụ trước khi JVM kết thúc: nếu chưa được phối hợp, chúng có thể bị dừng khi toàn bộ hook kết thúc.

### Ví dụ 1 — `System.exit` vẫn chạy shutdown hook

Tạo tệp **`ExitDemo.java`**:

~~~java
public class ExitDemo {
    public static void main(String[] args) {
        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> System.out.println("hook: cleanup"), "cleanup"));

        System.out.println("main: request exit");
        System.exit(7);

        System.out.println("main: unreachable");
    }
}
~~~

Biên dịch và chạy trên **JDK 17+**:

~~~bash
javac ExitDemo.java
java ExitDemo
~~~

**Stdout chính xác** trong lần chạy độc lập thông thường:

~~~text
main: request exit
hook: cleanup
~~~

Lời gọi `System.exit(7)` kích hoạt hook rồi JVM kết thúc với **exit status 7**. Dòng `main: unreachable` không được in. Trong ví dụ này chỉ có một hook và không có công việc ứng dụng khác, nên thứ tự hai dòng là rõ ràng; với **nhiều hook** hoặc thread chạy song song, thứ tự đầu ra có thể không cố định.

### Khi nào nên gọi `System.exit`?

Trong chương trình dòng lệnh, `System.exit` phù hợp nếu cần trả mã thoát cụ thể cho shell/CI hoặc buộc cả ứng dụng kết thúc. Trong thư viện, request handler hoặc ứng dụng do framework quản lý, gọi `System.exit` từ mã nghiệp vụ thường không phù hợp vì nó dừng **toàn bộ JVM**. Thường nên trả lỗi/exception cho nơi điều phối và để vòng đời ứng dụng được quản lý tập trung.

## 5. `Runtime.halt`: chấm dứt cưỡng bức ngay lập tức

**`Runtime.getRuntime().halt(status)`** buộc JVM dừng ngay. Khác với `exit`, nó:
- **Không bắt đầu shutdown sequence** nếu sequence chưa bắt đầu.
- **Không đợi** các shutdown hook đang chạy nếu sequence đã bắt đầu.
- Có thể bỏ qua công việc dọn dẹp, flush, hoàn tất phương thức, `finally`, `try-with-resources` và xử lý exception còn dang dở.
- Có thể dẫn đến mất dữ liệu, file/transaction ở trạng thái chưa hoàn chỉnh, log chưa ghi đủ hoặc hệ thống khác chưa nhận tín hiệu kết thúc sạch.

Khi `halt` được gọi trong lúc một `exit` đang chờ hook, mã trạng thái truyền cho `halt` có thể **ghi đè exit status** dự kiến của `exit`. `halt` là biện pháp cuối cùng khi cần dừng JVM một cách cưỡng bức, không phải cách mặc định để xử lý lỗi ứng dụng.

### Ví dụ 2 — `halt` bỏ qua shutdown hook

Tạo tệp **`HaltDemo.java`**:

~~~java
public class HaltDemo {
    public static void main(String[] args) {
        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> System.out.println("hook: should not run")));

        System.out.println("main: before halt");
        System.out.flush();

        Runtime.getRuntime().halt(9);

        System.out.println("main: unreachable");
    }
}
~~~

Chạy trong một **tiến trình riêng** để không làm dừng chương trình khác:

~~~bash
javac HaltDemo.java
java HaltDemo
~~~

**Stdout của chương trình**:

~~~text
main: before halt
~~~

Hook không chạy; dòng `main: unreachable` không xuất hiện. Tiến trình kết thúc với **status 9** khi lời gọi `halt(9)` được thực hiện. `System.out.flush()` giúp đảm bảo thông điệp trước khi halt được đẩy ra stream; không nên suy diễn rằng `halt` có thể flush mọi buffer I/O hoặc bảo đảm dữ liệu ghi bền vững.

> **Cảnh báo về thí nghiệm:** các ví dụ `System.exit`/`Runtime.halt` làm **kết thúc JVM đang chạy chúng**. Hãy thử bằng lệnh `java TênLớp` trong tiến trình riêng, tránh gọi trực tiếp trong IDE console/plugin host hoặc máy chủ chứa tác vụ đang phục vụ người dùng.

## 6. `finally`, try-with-resources và shutdown hook: phạm vi bảo đảm khác nhau

`finally` và **try-with-resources** giúp dọn tài nguyên trong **luồng điều khiển Java bình thường** hoặc khi exception khiến stack unwind. Chúng *không* phải một cơ chế hook toàn JVM.

Ví dụ:

~~~java
public class ExitFinallyDemo {
    public static void main(String[] args) {
        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> System.out.println("hook: executed")));

        try {
            System.out.println("try: before exit");
            System.exit(5);
        } finally {
            System.out.println("finally: not executed");
        }
    }
}
~~~

Lệnh:

~~~bash
javac ExitFinallyDemo.java
java ExitFinallyDemo
~~~

**Stdout:**

~~~text
try: before exit
hook: executed
~~~

Đoạn `finally` của luồng gọi exit **không được thực hiện**, vì `System.exit` không trả về và không unwind stack như một exception thông thường. Hook chạy do JVM bước vào shutdown sequence. Nếu đổi `System.exit(5)` thành `throw new IllegalStateException("failed");`, `finally` sẽ chạy khi stack unwind; đó là cơ chế hoàn toàn khác.

So sánh:

| Cơ chế | Khi nào sử dụng | Điều gì cần lưu ý |
| --- | --- | --- |
| `try-with-resources`, `finally` | Đóng kết nối/tệp/lock ở cuối phạm vi công việc, kể cả khi ném exception | Dọn dẹp có tính cục bộ, dễ kiểm soát; không được bảo đảm khi JVM bị halt/kill hoặc gọi exit trước khi unwind. |
| Shutdown hook | Dọn dẹp lúc JVM bắt đầu **shutdown sequence** | Chạy best effort, đồng thời, không bảo đảm với forced termination. |
| `System.exit` / `Runtime.exit` | Bắt đầu shutdown chủ động và cung cấp exit status | Gọi ở cấp tiến trình; hook có cơ hội chạy; có thể ảnh hưởng thread đang hoạt động. |
| `Runtime.halt` | Cưỡng bức kết thúc toàn JVM ngay | Bỏ qua hoặc cắt ngang cleanup và hook; nguy cơ mất dữ liệu. |

**Nguyên tắc thiết kế:** sử dụng **try-with-resources cho tài nguyên có phạm vi rõ ràng**, quản lý vòng đời chính thức cho thành phần dịch vụ, và dùng shutdown hook làm “lưới an toàn” cho những tài nguyên sống đến cuối tiến trình. Không dồn tất cả việc dọn dẹp của ứng dụng vào hook.

## 7. Thiết kế shutdown hook an toàn cho ứng dụng nhiều luồng

Một shutdown hook tốt cần **nhanh, có giới hạn thời gian, idempotent khi phù hợp và an toàn khi chạy đồng thời**. Các bước graceful shutdown thường là:

1. **Ngừng nhận công việc mới** (server/listener/job scheduler).
2. **Báo cho công việc đang chạy dừng có trật tự**; nếu có thể, chờ trong một khoảng thời gian hữu hạn.
3. **Flush/commit dữ liệu cần thiết**, rồi đóng queue, pool, kết nối, file và telemetry/logging theo thứ tự phụ thuộc.
4. **Trả quyền điều khiển khỏi hook** để JVM có thể hoàn tất shutdown sequence; nếu quá hạn, cân nhắc interrupt/cancel đúng giao thức của thành phần.
5. **Đặt thứ tự trong cùng một hook hoặc lifecycle coordinator**, thay vì hy vọng các hook độc lập chạy theo thứ tự đăng ký.

### Ví dụ 3 — Shutdown executor có timeout

Tạo **`GracefulPoolDemo.java`**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class GracefulPoolDemo {
    public static void main(String[] args) {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            System.out.println("hook: stopping executor");
            pool.shutdown(); // Không nhận task mới.
            try {
                if (!pool.awaitTermination(2, TimeUnit.SECONDS)) {
                    pool.shutdownNow(); // Yêu cầu interrupt các task còn chạy.
                }
            } catch (InterruptedException ex) {
                pool.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }, "executor-shutdown"));

        pool.submit(() -> System.out.println("task: completed"));
        System.out.println("main: request exit");
        System.exit(0);
    }
}
~~~

Lệnh:

~~~bash
javac GracefulPoolDemo.java
java GracefulPoolDemo
~~~

**Các dòng có thể xuất hiện:**

~~~text
task: completed
main: request exit
hook: stopping executor
~~~

Đây là **một đầu ra hợp lệ, không phải thứ tự được bảo đảm**. Tác vụ của executor có thể chạy trước hoặc sau dòng `main: request exit`; hook cũng chạy đồng thời với worker. Trong ví dụ đơn giản, hook gọi `shutdown()`, chờ task hoàn tất (tối đa hai giây) rồi kết thúc. Nếu task không tự dừng khi nhận interrupt, `shutdownNow()` chỉ là **yêu cầu ngắt**, không phải cơ chế cưỡng ép task chắc chắn hoàn thành. Khi hook đã kết thúc, JVM vẫn có thể dừng dù còn công việc khác.

Với ứng dụng thực tế, nên **bắt và ghi nhận lỗi dọn dẹp từng tài nguyên** để một lần đóng thất bại không vô tình bỏ qua các bước đóng tiếp theo. Nếu tài nguyên có thể được đóng từ luồng khác nữa, dùng cơ chế đồng bộ/trạng thái để tránh đóng đôi nguy hiểm. Không nên block mãi trong `join()`, `awaitTermination()`, khóa chéo hay lời gọi mạng không có timeout.

## 8. Những điều tuyệt đối tránh trong shutdown hook

### Gọi `System.exit` từ chính hook

Đây là một lỗi nghiêm trọng: khi JVM đang chờ tất cả hook kết thúc, lời gọi `System.exit`/`Runtime.exit` bên trong hook có thể bị **chặn vô thời hạn** và khiến quá trình shutdown không hoàn thành. Muốn thông báo lỗi cleanup, **ghi nhận/log** rồi cho hook kết thúc; đừng tự gọi `exit` lần nữa.

### Đợi hook khác hoặc phụ thuộc tài nguyên hook khác đang đóng

Do các hook chạy đồng thời không có thứ tự, **hook A đợi B**, trong khi B cần lock do A giữ, sẽ deadlock. Tương tự, chờ một service (logging, AWT event thread, thread pool) vốn đã được hook khác đóng có thể treo. Nếu có chuỗi phụ thuộc A→B→C, hãy cho một lifecycle coordinator chủ động sắp thứ tự, hoặc thiết kế từng bước đóng với hợp đồng rõ ràng.

### Thực hiện giao dịch/phép tính quá dài

Nền tảng như container/orchestrator có thể chỉ cho tiến trình một **grace period** hữu hạn trước khi buộc dừng. Hook có nhiệm vụ kết thúc nhanh; không phải chỗ thích hợp cho backup kéo dài, tương tác người dùng, hoặc khởi chạy luồng công việc nghiệp vụ mới. Vẫn cần lưu/commit định kỳ trong luồng xử lý bình thường.

### Cho rằng hook luôn chạy

Một số lệnh hủy tiến trình, crash native, mất nguồn hoặc `Runtime.halt` có thể khiến hook không chạy. Thiết kế ứng dụng phải chịu được **crash recovery**, ví dụ dựa vào transaction, ghi log bền vững, message acknowledgment hoặc cơ chế retry/idempotency, thay vì dùng hook làm nơi duy nhất lưu trạng thái.

### Dùng hook để “cứu” dữ liệu chưa ghi khi mất tiến trình

Hook là **best-effort cleanup**. Nó không thay thế journal/transaction, write-ahead log, fsync khi cần, cơ chế khôi phục hay quy trình graceful shutdown của framework. Một lệnh `println` lúc kết thúc cũng không chứng minh dữ liệu đã ghi bền vững vào ổ đĩa.

## 9. Nhận biết vấn đề thực tế

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Kết thúc `main()` nhưng tiến trình Java vẫn sống | Còn non-daemon thread, thread pool hoặc timer chưa dừng | Kiểm tra thread dump; đóng executor/service đúng vòng đời. |
| Gọi `System.exit` mà chương trình không thoát | Hook treo, deadlock hoặc chờ I/O vô hạn | Thread dump trong lúc shutdown; thêm timeout và log các bước cleanup. |
| Log của nhiều hook đảo thứ tự giữa các lần chạy | Hook chạy đồng thời, thứ tự không bảo đảm | Gộp các bước phụ thuộc vào một coordinator. |
| Hook không in log khi bị `kill -9` | SIGKILL không cho JVM shutdown sạch | Giám sát/crash recovery, đừng dựa vào hook cho độ bền dữ liệu. |
| Đăng ký hook muộn báo `IllegalStateException` | JVM đã vào shutdown sequence | Đăng ký từ giai đoạn khởi tạo ứng dụng; không đăng ký khi đang dừng. |
| Hook chưa chạy nhưng lập trình viên đã gọi `hook.start()` | Hook được tự khởi động; làm sai hợp đồng đăng ký | Chỉ tạo và `addShutdownHook`, để JVM tự start. |
| Thêm cùng hook lần thứ hai báo `IllegalArgumentException` | Đối tượng `Thread` đã đăng ký hoặc đã chạy | Quản lý một lần đăng ký cho mỗi hook. |
| Máy chủ bị mất request dở dang khi exit | Shutdown sequence không tự bảo đảm thread nghiệp vụ xong | Dừng nhận request, drain, timeout, rồi mới đóng tài nguyên. |
| Dùng `Runtime.halt` khiến log/file dở dang | `halt` bỏ qua cleanup và cắt ngang threads | Dùng `halt` chỉ khi bắt buộc cưỡng bức và có phương án recovery. |

### Góc nhìn trong server/container

Một ứng dụng service thường có **quy trình shutdown do framework điều phối**. Ví dụ, framework có thể đóng HTTP listener, hủy lịch job, đợi request đang xử lý, đóng pool, flush logging. Nếu bạn tự thêm hook, hãy kiểm tra nó có “tranh” tài nguyên với hook của framework hay không. Đối với container/orchestrator, kiểm tra tín hiệu gửi đến tiến trình Java, timeout cho việc dừng và giới hạn tài nguyên. Không giả định rằng tất cả môi trường đều gửi cùng tín hiệu hoặc luôn đủ thời gian.

## 10. Tự kiểm tra

**Câu 1.** `main()` đã return nhưng một `new Thread(...).start()` không phải daemon vẫn chạy. JVM có bắt buộc shutdown ngay không?

**Đáp án:** Không. Non-daemon thread còn sống thường giữ JVM hoạt động. JVM bắt đầu shutdown tự nhiên khi không còn non-daemon thread.

**Câu 2.** Hai hook A và B đăng ký theo thứ tự A rồi B. B có chắc chạy sau A và được bảo đảm nhìn thấy tài nguyên đã được A dọn không?

**Đáp án:** Không. Các hook được start theo thứ tự không xác định và chạy đồng thời. Phải tự thiết kế thứ tự/phối hợp.

**Câu 3.** `System.exit(4)` có làm code trong `finally` của luồng đang gọi được chạy tự động không? Hook đã đăng ký có được chạy không?

**Đáp án:** `System.exit` không unwind stack của luồng gọi như exception nên không tự chạy `finally` tại vị trí đó. Nếu JVM bắt đầu shutdown sequence thành công thì shutdown hook được chạy, trừ tình huống cưỡng bức hoặc lỗi ngoài khả năng bảo đảm.

**Câu 4.** Một hook chờ vô hạn; mọi hook khác hoàn tất. Khi nào JVM kết thúc bình thường?

**Đáp án:** Khi **mọi hook** kết thúc. Nếu một hook treo vô hạn, shutdown sequence có thể không hoàn thành; `halt` hoặc cưỡng bức từ môi trường có thể cắt ngang nhưng rủi ro mất dữ liệu.

**Câu 5.** Gọi `Runtime.halt(9)` trước khi shutdown bắt đầu. Hook có chạy không và `finally` có bảo đảm chạy không?

**Đáp án:** Không. `halt` không bắt đầu shutdown sequence, kết thúc JVM ngay; hook và `finally` không được bảo đảm thực thi.

**Câu 6.** Khi ứng dụng bị SIGKILL trên Linux, có nên mong đợi hook lưu transaction cuối cùng?

**Đáp án:** Không. SIGKILL không tạo cơ hội cho JVM chạy cleanup. Cần bảo đảm nhất quán bằng cơ chế lưu bền vững, transaction và phục hồi khi khởi động lại.

## 11. Mô hình ghi nhớ

~~~text
Kết thúc tự nhiên / System.exit / sự kiện được JVM xử lý
                        |
                        v
                SHUTDOWN SEQUENCE
                 /      |      \
              hook A  hook B   hook C  (đồng thời, không bảo đảm thứ tự)
                 \      |      /
                     xong tất cả
                        |
                        v
                     JVM dừng

Runtime.halt --------------> JVM dừng ngay, bỏ qua/chặn ngang hooks

SIGKILL/crash --------------> JVM có thể bị dừng, không bảo đảm hooks
~~~

**Điểm cốt lõi:** shutdown hook là **cơ hội dọn dẹp trước khi JVM tắt**, `System.exit` là **yêu cầu bắt đầu kết thúc có thực hiện shutdown sequence**, còn `Runtime.halt` là **cưỡng bức chấm dứt không chờ cleanup**. Với dịch vụ cần độ tin cậy cao, dọn dẹp phải ngắn, có thứ tự, giới hạn thời gian và có cơ chế khôi phục sau khi tiến trình chết đột ngột.

## Tài liệu chuẩn để tra cứu

- [Oracle JDK 17 — `java.lang.Runtime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): `addShutdownHook`, `removeShutdownHook`, `exit`, `halt` và các lưu ý shutdown.
- [Oracle JDK 17 — `java.lang.System`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html): `System.exit`.
- [Java Virtual Machine Specification 21 — §5.7 JVM Termination](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.7): các trường hợp kết thúc JVM.
