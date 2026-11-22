# Giới hạn thực thi `finally` khi JVM dừng, tiến trình bị kết thúc hoặc mã không thoát

Trong Java, `finally` là cơ chế thực thi công việc cuối cùng khi luồng điều khiển **rời khỏi một cấu trúc `try`**. Nó hữu ích để dọn dẹp, giải phóng khóa hoặc ghi nhận trạng thái khi thao tác hoàn thành, ném ngoại lệ, hay thoát sớm bằng `return`, `break` hoặc `continue`.

Tuy nhiên, **`finally` không phải lời hứa rằng mã dọn dẹp sẽ luôn được thực thi trong mọi tình huống**. Nó không thể bảo đảm chạy khi JVM bị chấm dứt ngay, tiến trình bị hệ điều hành kết thúc cưỡng bức, thiết bị mất nguồn hoặc đoạn mã không bao giờ rời khỏi `try`. Ngay cả khi `finally` bắt đầu chạy, nó vẫn có thể bị ngắt giữa chừng bởi lỗi mới hoặc kết thúc tiến trình.

Bài này phân biệt những tình huống thường bị gộp nhầm dưới câu hỏi “Tại sao `finally` không chạy?”, từ đó lựa chọn cách quản lý tài nguyên và tính nhất quán dữ liệu phù hợp.

## 1. Điều kiện để `finally` được thực thi

Cấu trúc cơ bản:

~~~java
try {
    // Công việc chính.
} catch (SomeException e) {
    // Xử lý lỗi phù hợp.
} finally {
    // Công việc cuối cùng.
}
~~~

Đây là **đoạn cú pháp minh họa**, trong đó `SomeException` là một loại ngoại lệ có thật trong chương trình và khối `try` phải phù hợp với nhánh `catch`.

Đối với **luồng điều khiển Java thông thường**, `finally` được thực thi khi quá trình rời `try` hoặc `catch` liên quan bắt đầu, bao gồm:

- Thân `try` chạy tới cuối mà không có lỗi.
- `return` yêu cầu trả về từ phương thức.
- `break` hoặc `continue` rời phạm vi `try` tương ứng.
- Ngoại lệ xuất hiện; nó có thể được `catch` trong cùng cấu trúc xử lý hoặc lan truyền ra vùng bao ngoài.

Ví dụ:

~~~java
static int normalReturn() {
    try {
        System.out.println("try");
        return 7;
    } finally {
        System.out.println("finally");
    }
}
~~~

Khi gọi `normalReturn()`, Java in `try` rồi `finally` trước khi caller nhận giá trị `7`. Lệnh `return` không bỏ qua `finally`.

**Nhưng tất cả những trường hợp trên cùng có một tiền đề quan trọng:** luồng thực thi còn vận hành theo cơ chế điều khiển của Java và đang **rời** phạm vi cần dọn dẹp. Nếu chương trình ngừng đột ngột mà không trải qua bước rời phạm vi đó, hoặc đứng mãi trong `try`, không thể suy ra `finally` sẽ được chạy.

## 2. Bảng phân loại các tình huống

| Tình huống | `finally` có chạy không? | Bản chất |
| --- | --- | --- |
| `try` kết thúc bình thường | Có, theo luồng thông thường | Rời cấu trúc có kiểm soát |
| `return`/`break`/`continue` rời `try` | Có, thông thường | Thoát phạm vi theo luật ngôn ngữ |
| Ngoại lệ Java thông thường thoát `try` | Có, khi rời phạm vi | Tháo dần stack và tìm handler |
| `InterruptedException` được ném khỏi thao tác chờ | Có, khi luồng rời `try` | Ngắt thao tác theo cơ chế ngoại lệ |
| `System.exit(status)` thực sự kết thúc JVM | **Không được bảo đảm**, thông thường `finally` của stack đang chạy bị bỏ qua | Khởi động quá trình shutdown của JVM, không phải `return` |
| `Runtime.getRuntime().halt(status)` | **Không được bảo đảm**, thông thường không chạy | Chấm dứt VM ngay, không thực hiện shutdown thông thường |
| Hệ điều hành kill cưỡng bức, tiến trình bị crash, mất điện | **Không được bảo đảm** | Không còn cơ hội thực thi bytecode Java |
| Luồng kẹt mãi trong vòng lặp hoặc chờ không kết thúc | **Chưa chạy** nếu vẫn ở trong `try` | Không xảy ra bước rời phạm vi |
| JVM tự kết thúc vì không còn luồng non-daemon | Không thể dựa vào `finally` của daemon thread còn hoạt động | Shutdown VM có thể cắt ngang công việc daemon |
| Một `finally` khác tự ném lỗi | Khối hiện tại có thể bắt đầu nhưng không hoàn thành | Quá trình dọn dẹp có thể thất bại |

**Lưu ý cách diễn đạt:** `finally` không chạy trong một ví dụ cụ thể **không** đồng nghĩa Java đã “bỏ quy tắc `finally`”. Có thể nguyên nhân là không xảy ra bước rời `try` theo ngữ nghĩa thông thường, JVM shutdown không tháo stack như `return`, hoặc quá trình thực thi đã bị chấm dứt.

## 3. `System.exit(status)` khác `return` ở đâu?

`System.exit(int status)` yêu cầu chấm dứt JVM và tương đương về ý nghĩa với lời gọi `Runtime.getRuntime().exit(status)`. Nó **không phải** lệnh `return` khỏi phương thức `main` và không khởi tạo quá trình tháo mọi khung gọi để chạy `finally`.

Xét:

~~~java
static void exitExample() {
    try {
        System.out.println("Trước System.exit");
        System.out.flush();
        System.exit(0);
    } finally {
        System.out.println("finally sau System.exit");
    }
}
~~~

Đây là **phương thức minh họa**. Nếu `System.exit(0)` thực sự làm JVM bắt đầu và hoàn tất shutdown, bạn **không được dựa vào** dòng `finally sau System.exit` sẽ được in. Trong cách chạy thông thường, nó sẽ không xuất hiện vì JVM kết thúc thay vì cho phương thức này rời `try` theo đường `return`.

Một vài chi tiết quan trọng:

- `status = 0` thường biểu thị kết thúc thành công theo quy ước hệ điều hành; trạng thái khác `0` thường chỉ kết thúc không thành công. **Giá trị status không quyết định có chạy `finally` hay không**.
- `System.exit` thực hiện quá trình shutdown có tổ chức của JVM, trong đó có **shutdown hooks** đã đăng ký, nhưng không bảo đảm các phương thức đang chạy được quay lại để thực thi `finally`.
- Nếu việc gọi `System.exit` không thật sự chấm dứt JVM (chẳng hạn bị một cơ chế an ninh trong môi trường cũ chặn bằng ngoại lệ), các quy tắc điều khiển Java tương ứng lại được áp dụng. Không nên dùng ngoại lệ hiếm gặp này để thiết kế việc dọn dẹp.
- Gọi `System.out.flush()` có thể hỗ trợ đẩy dữ liệu đang đệm trước khi kết thúc, nhưng **không** biến công việc trong `finally` thành được bảo đảm.

### Vì sao `return` khỏi `main` khác `System.exit`?

~~~java
public static void main(String[] args) {
    try {
        System.out.println("main đang chạy");
        return;
    } finally {
        System.out.println("main finally");
    }
}
~~~

Đây là đoạn **phương thức `main` minh họa**, cần đặt trong một lớp. `return` khiến `main` thoát theo luật Java nên `finally` chạy. Tuy nhiên, sau khi `main` trả về, JVM có thể tiếp tục nếu còn các luồng non-daemon khác đang chạy.

Ngược lại, `System.exit(...)` yêu cầu shutdown của **cả JVM** thay vì chỉ chấm dứt lời gọi phương thức hiện tại. Cần tách biệt hai khái niệm: **kết thúc một phương thức** và **chấm dứt tiến trình JVM**.

## 4. `Runtime.halt(status)`: kết thúc đột ngột hơn `System.exit`

`Runtime.getRuntime().halt(int status)` là cơ chế chấm dứt JVM một cách cưỡng bức. Nó **không thực hiện chu trình shutdown thông thường** và không chạy các shutdown hook còn chờ.

~~~java
static void haltExample() {
    try {
        System.out.println("Trước halt");
        System.out.flush();
        Runtime.getRuntime().halt(1);
    } finally {
        System.out.println("finally sau halt");
    }
}
~~~

Trong lần chạy mà `halt(1)` thật sự chấm dứt VM, chương trình không thể dựa vào `finally` này hoặc các shutdown hook để dọn dẹp. Dòng sau `halt` trong ví dụ thường không xuất hiện.

| Đặc điểm | `System.exit(status)` | `Runtime.halt(status)` |
| --- | --- | --- |
| Mục tiêu | Shutdown JVM theo quy trình thông thường | Dừng VM ngay |
| Shutdown hooks | Thông thường được JVM khởi chạy theo cơ chế shutdown | Không được chạy như một bước shutdown |
| Chờ hook hoàn tất | Theo cơ chế JVM shutdown, trừ khi bị ngắt/bị halt | Không |
| Tháo stack để chạy mọi `finally` | Không bảo đảm | Không bảo đảm |
| Phù hợp với dọn dẹp dữ liệu bình thường | Không nên dùng thay cơ chế đóng tài nguyên có kiểm soát | Không nên dùng |

`Runtime.halt` có thể hữu ích ở một số tình huống vận hành rất đặc biệt, nhưng không phải cách phù hợp để thoát một phương thức, hủy một tác vụ hay xử lý ngoại lệ thông thường.

## 5. Shutdown hook không thay thế `finally`

Có thể đăng ký hook bằng:

~~~java
Runtime.getRuntime().addShutdownHook(new Thread(() -> {
    System.out.println("shutdown hook");
}));
~~~

Đoạn trên cần đặt trong một phương thức và được thực hiện trước khi shutdown bắt đầu. Một shutdown hook là một luồng Java đã đăng ký để JVM **khởi chạy trong giai đoạn shutdown có tổ chức**, chẳng hạn khi `System.exit` hoặc một số tín hiệu kết thúc được xử lý theo quy trình shutdown của JVM.

Điều này tạo ra hai cơ chế khác nhau:

- **`finally`:** gắn với việc **rời một phạm vi `try`** trong luồng điều khiển Java.
- **Shutdown hook:** gắn với **giai đoạn JVM shutdown**, chạy theo cơ chế riêng.

Vì vậy có tình huống shutdown hook chạy nhưng khối `finally` trong phương thức đang gọi `System.exit` không chạy.

### Những giới hạn của shutdown hooks

1. **Không có thứ tự chạy mặc định giữa các hook.** Nhiều hook có thể được khởi chạy đồng thời; không nên suy ra thứ tự từ lúc đăng ký.
2. **Không có bảo đảm hook sẽ chạy xong.** Hook có thể treo, ném lỗi hoặc bị quá trình chấm dứt cưỡng bức ngắt giữa chừng.
3. **`Runtime.halt` và kill cưỡng bức bỏ qua shutdown thông thường.** Vì vậy hook không thay thế được thiết kế phục hồi sau crash.
4. **Không được dựa vào trạng thái các luồng khác đang thay đổi trong lúc shutdown.** Các luồng khác có thể vẫn đang hoạt động; shutdown hook nên có phạm vi trách nhiệm nhỏ, an toàn, có thời hạn.
5. **Ghi log không đồng nghĩa dữ liệu đã bền vững.** Nội dung có thể còn trong bộ đệm ứng dụng, runtime, hệ điều hành hoặc thiết bị lưu trữ.

Nên dùng shutdown hook cho những hành động **best-effort** phù hợp với giai đoạn dừng dịch vụ, không dùng như cơ chế duy nhất bảo đảm mọi giao dịch đều hoàn tất.

## 6. Tiến trình bị hệ điều hành kết thúc hoặc gặp sự cố

JVM là một tiến trình của hệ điều hành. Nếu tiến trình bị kết thúc theo cách không cho code Java tiếp tục thực thi, các khối `finally` không có cơ hội chạy.

Những ví dụ cần phân biệt:

- **Kill cưỡng bức:** trên hệ Unix-like, `SIGKILL` (ví dụ qua `kill -9`) không thể được tiến trình bắt để thực hiện dọn dẹp Java trước khi kết thúc. Trên Windows, cơ chế kết thúc tiến trình cưỡng bức cũng không cung cấp bảo đảm tháo stack Java.
- **Tín hiệu kết thúc có thể xử lý:** một yêu cầu kết thúc “mềm” như `SIGTERM` có thể đưa JVM vào quá trình shutdown và chạy hook tùy nền tảng/runtime, nhưng **không nên cam kết mọi `finally` của mọi luồng được thực thi**.
- **Crash JVM/native code:** lỗi nghiêm trọng khiến tiến trình không còn chạy bình thường có thể ngăn hoàn toàn việc thực thi mã Java tiếp theo.
- **Mất điện, lỗi phần cứng, hết tài nguyên nghiêm trọng:** không thể giả định tiến trình còn đủ khả năng để chạy hoặc hoàn tất mã dọn dẹp.

Không nên dạy một quy tắc đơn giản như “mọi tín hiệu từ hệ điều hành đều cho JVM chạy `finally`” hoặc “mọi tín hiệu đều không thể chạy shutdown hook”. Hành vi phụ thuộc loại kết thúc, nền tảng và cơ chế JVM, nhưng **thiết kế an toàn phải giả định có thể không có cơ hội dọn dẹp**.

### So sánh kết thúc có kiểm soát và kết thúc cưỡng bức

~~~text
Ứng dụng hoạt động
       |
       +-- Đường kết thúc tác vụ bình thường
       |      |
       |      +-- rời try -> finally -> trả kết quả / dừng tác vụ
       |
       +-- JVM bắt đầu shutdown
       |      |
       |      +-- shutdown hooks có thể chạy
       |      +-- không có bảo đảm tháo các try của mọi luồng
       |
       +-- Tiến trình bị kill cưỡng bức / crash
              |
              +-- Không thể trông chờ finally hoặc hook
~~~

Sơ đồ diễn tả phạm vi trách nhiệm và giới hạn bảo đảm, không mô tả thứ tự chính xác của mọi sự kiện shutdown trên tất cả JVM.

## 7. Mã không bao giờ thoát khỏi `try`

Đôi khi không có `System.exit`, `halt` hay kill từ bên ngoài. `finally` **vẫn chưa chạy** vì chương trình chưa rời khối `try`.

Ví dụ:

~~~java
static void neverLeavesTry() {
    try {
        while (true) {
            // Vòng lặp không có đường thoát.
            Thread.onSpinWait();
        }
    } finally {
        System.out.println("Không tới đây khi còn lặp vô hạn");
    }
}
~~~

Đây là phương thức minh họa, **không nên gọi trực tiếp khi học** vì vòng lặp không kết thúc và có thể tiêu thụ CPU. Khối `finally` không được thực thi chừng nào luồng vẫn ở trong `try`; Java không tự ném ngoại lệ chỉ vì bạn đã chờ lâu.

Một trường hợp thực tế hơn là luồng chờ mãi cho dữ liệu từ socket, lock, hàng đợi hoặc điều kiện đồng bộ. Nếu thao tác chờ không hoàn tất, không bị hủy và không ném ngoại lệ, luồng chưa rời `try`. `finally` chỉ là phần dọn dẹp **khi ra khỏi vùng**, không phải bộ hẹn giờ buộc vùng đó phải kết thúc.

### Ví dụ chờ có thể bị gián đoạn

~~~java
static void waitForSignal() throws InterruptedException {
    java.util.concurrent.CountDownLatch latch =
            new java.util.concurrent.CountDownLatch(1);
    try {
        latch.await();
        System.out.println("Nhận tín hiệu");
    } finally {
        System.out.println("Đã rời vùng chờ");
    }
}
~~~

Đây là phương thức minh họa. Nếu không có luồng nào gọi `countDown()` và không có yêu cầu gián đoạn, `await()` có thể chờ vô hạn; `finally` chưa chạy. Nếu luồng bị interrupt trong khi chờ, `await()` ném `InterruptedException`; lúc đó luồng **rời `try`**, và `finally` thường chạy trước khi ngoại lệ truyền ra bên gọi.

Lưu ý: không phải mọi thao tác chờ đều hỗ trợ ngắt bằng `Thread.interrupt()`. Có API chờ phản ứng với interrupt, có API yêu cầu đóng tài nguyên hoặc một cơ chế hủy khác.

## 8. `Thread.interrupt()` không đồng nghĩa kill luồng

Một hiểu nhầm phổ biến là “ngắt luồng thì `finally` sẽ không chạy”. `Thread.interrupt()` chủ yếu **đặt trạng thái interrupt** và làm một số thao tác chờ có khả năng gián đoạn ném `InterruptedException`. Nó không tương đương kill tiến trình hay buộc mọi câu lệnh đang chạy dừng ngay.

Ví dụ:

~~~java
static void interruptible() {
    try {
        try {
            System.out.println("Trước sleep");
            Thread.currentThread().interrupt();
            Thread.sleep(100);
        } finally {
            System.out.println("finally sau interrupt");
        }
    } catch (InterruptedException e) {
        System.out.println("Đã bắt InterruptedException");
        Thread.currentThread().interrupt();
    }
}
~~~

Khi gọi trong một luồng bình thường chưa bị ngắt trước đó, stdout:

~~~text
Trước sleep
finally sau interrupt
Đã bắt InterruptedException
~~~

Ở đây `Thread.sleep` phát hiện trạng thái interrupt và ném `InterruptedException`. Khối `finally` của `try` trong chạy khi ngoại lệ rời khối; sau đó `catch` ngoài nhận lỗi.

**Chính quá trình ném và lan truyền `InterruptedException` khiến `finally` chạy**, không phải hành vi “interrupt luôn gọi `finally`” theo một cơ chế đặc biệt.

Nếu đoạn mã lặp liên tục, phớt lờ interrupt và không rời `try`, `finally` có thể tiếp tục không chạy. Khi thiết kế tác vụ dài hạn, nên có điều kiện dừng, xử lý interrupt theo hợp đồng và giải phóng tài nguyên ở đường thoát thích hợp.

## 9. Luồng daemon và thời điểm JVM kết thúc

JVM thông thường còn tiếp tục chạy khi vẫn có luồng **non-daemon** đang sống, dù phương thức `main` đã kết thúc. Ngược lại, khi tất cả luồng non-daemon kết thúc, JVM có thể bắt đầu shutdown trong lúc một số daemon thread vẫn đang hoạt động.

Do đó không nên giả định:

> “Nếu một daemon thread còn ở trong `try`, JVM chắc chắn sẽ cho nó chạy hết `finally` trước khi thoát.”

Điều đó **không được bảo đảm**. Daemon thread thường phục vụ công việc nền và không giữ JVM sống chỉ để hoàn thành phần việc của nó. Nếu cần hoàn tất thao tác quan trọng, hãy quản lý lifecycle rõ ràng: tín hiệu dừng, chờ luồng/tác vụ hoàn thành có giới hạn và đóng tài nguyên trước khi dừng ứng dụng.

Một số nguyên tắc:

- Không dựa vào daemon thread để flush dữ liệu quan trọng sau khi các luồng nghiệp vụ kết thúc.
- Với `ExecutorService`, chủ động yêu cầu `shutdown()`, chờ `awaitTermination(...)` khi hợp đồng cho phép, và xác định chính sách hủy phần việc còn lại.
- Không xem `shutdownNow()` là bảo đảm mọi tác vụ đã bị dừng; nó thường cố gắng ngắt các tác vụ nhưng tác vụ có thể không phản hồi.
- Hãy phân biệt dừng **một nhiệm vụ** và dừng **cả JVM**.

`finally` vẫn có giá trị trong một daemon thread **nếu thread đó thực sự rời phạm vi `try` theo luồng Java bình thường**. Vấn đề là vòng đời JVM có thể kết thúc trước lúc ấy.

## 10. Ví dụ Java 17+ chạy độc lập, không tự treo ở chế độ mặc định

Chương trình có các chế độ riêng. Mặc định chỉ chạy trường hợp an toàn `normal`; các chế độ `exit`, `halt` và `wait` **phải chạy trong tiến trình Java riêng** nếu muốn thử. Chúng không phải phần của luồng mặc định.

Lưu thành **`FinallyLimitsDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;

public class FinallyLimitsDemo {
    public static void main(String[] args) {
        String mode = args.length == 0 ? "normal" : args[0];

        switch (mode) {
            case "normal" -> normal();
            case "exception" -> exceptionCase();
            case "interrupt" -> interruptCase();
            case "exit" -> exitCase();
            case "halt" -> haltCase();
            case "wait" -> waitCase();
            default -> System.out.println("Unknown mode");
        }
    }

    static void normal() {
        try {
            System.out.println("try: normal");
            return;
        } finally {
            System.out.println("finally: normal");
        }
    }

    static void exceptionCase() {
        try {
            try {
                System.out.println("try: exception");
                throw new IllegalStateException("boom");
            } finally {
                System.out.println("finally: exception");
            }
        } catch (IllegalStateException e) {
            System.out.println("caught: " + e.getMessage());
        }
    }

    static void interruptCase() {
        try {
            try {
                System.out.println("try: sleep");
                Thread.currentThread().interrupt();
                Thread.sleep(100);
            } finally {
                System.out.println("finally: interrupt");
            }
        } catch (InterruptedException e) {
            System.out.println("caught: interrupted");
            Thread.currentThread().interrupt();
        }
    }

    static void exitCase() {
        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> System.out.println("hook: exit"))
        );

        try {
            System.out.println("try: exit");
            System.out.flush();
            System.exit(0);
        } finally {
            System.out.println("finally: exit");
        }
    }

    static void haltCase() {
        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> System.out.println("hook: halt"))
        );

        try {
            System.out.println("try: halt");
            System.out.flush();
            Runtime.getRuntime().halt(0);
        } finally {
            System.out.println("finally: halt");
        }
    }

    static void waitCase() {
        CountDownLatch neverReleased = new CountDownLatch(1);
        try {
            System.out.println("try: wait");
            System.out.flush();
            neverReleased.await();
        } catch (InterruptedException e) {
            System.out.println("caught: wait interrupted");
            Thread.currentThread().interrupt();
        } finally {
            System.out.println("finally: wait");
        }
    }
}
~~~

Biên dịch:

~~~bash
javac FinallyLimitsDemo.java
~~~

Chạy ba chế độ an toàn **riêng từng lần**, không chấm dứt cưỡng bức tiến trình:

~~~bash
java FinallyLimitsDemo
java FinallyLimitsDemo exception
java FinallyLimitsDemo interrupt
~~~

**Stdout chính xác của `java FinallyLimitsDemo`:**

~~~text
try: normal
finally: normal
~~~

**Stdout chính xác của `java FinallyLimitsDemo exception`:**

~~~text
try: exception
finally: exception
caught: boom
~~~

**Stdout chính xác của `java FinallyLimitsDemo interrupt`:**

~~~text
try: sleep
finally: interrupt
caught: interrupted
~~~

Ba chế độ này làm rõ: `return` và các ngoại lệ thông thường, kể cả `InterruptedException` từ thao tác chờ, không tự động ngăn `finally`.

### Chạy thử `System.exit` trong tiến trình riêng

~~~bash
java FinallyLimitsDemo exit
~~~

Trong môi trường JVM Java 17 thông thường, khi `System.exit(0)` thực sự chấm dứt JVM, có thể quan sát đầu ra tương tự:

~~~text
try: exit
hook: exit
~~~

Đây là **đầu ra thường thấy, không phải cam kết tuyệt đối về mọi môi trường**. Dòng `finally: exit` không được bảo đảm sẽ xuất hiện và thông thường không xuất hiện. Shutdown hook có cơ hội được chạy trong quy trình shutdown, khác với khối `finally` đang nằm trên stack của luồng gọi `System.exit`.

Không diễn giải tình huống này thành “`System.exit` đảm bảo hook in được mọi thứ”: có thể xảy ra chấm dứt cưỡng bức, I/O thất bại hoặc hook không hoàn thành.

### Chạy thử `Runtime.halt` trong tiến trình riêng

~~~bash
java FinallyLimitsDemo halt
~~~

Trong một JVM hoạt động bình thường, có thể chỉ thấy:

~~~text
try: halt
~~~

Đây cũng là **đầu ra minh họa thông thường**, không phải lời hứa rằng mọi thông báo đều ra console trong mọi môi trường. `Runtime.halt(0)` dừng VM mà không thực hiện shutdown hook `hook: halt`; `finally: halt` cũng không được thực thi theo đường thoát bình thường.

### Chế độ `wait` cố ý không hoàn thành

**Không chạy chế độ sau như một phần của bài kiểm tra tự động hoặc trong terminal không thể hủy tác vụ:**

~~~bash
java FinallyLimitsDemo wait
~~~

`CountDownLatch` được khởi tạo với count bằng `1` nhưng trong chương trình không có nơi `countDown()`, nên `await()` sẽ chờ cho tới khi luồng bị ngắt hoặc tiến trình bị kết thúc. Nếu không có sự kiện làm nó thoát, chương trình in `try: wait` rồi cứ chờ; `finally: wait` chưa được thực thi.

Khi cần kiểm tra sự khác nhau giữa ngắt thao tác và kill cưỡng bức, phải sử dụng môi trường thử nghiệm có thể kiểm soát tiến trình. Không dùng lệnh kill nhầm vào JVM dịch vụ hoặc tiến trình của người khác.

## 11. Phân tích: “`finally` chưa chạy” không đồng nghĩa “`finally` bị bỏ qua”

Có ba tình huống cần dùng từ chính xác:

1. **Đã rời `try` và chạy `finally`:** ví dụ `return`, `throw` bình thường; khối dọn dẹp được thực thi.
2. **Chưa rời `try` nên chưa đến `finally`:** ví dụ `await()` không có tín hiệu hoặc vòng lặp vô hạn.
3. **Không còn cơ hội thực thi `finally`:** ví dụ VM bị `halt`, tiến trình bị kill cưỡng bức, thiết bị mất nguồn.

Trong trường hợp (2), nếu sau đó luồng được đánh thức, gặp timeout, nhận interrupt và thực sự thoát phạm vi `try`, `finally` **có thể chạy**. Trong trường hợp (3), code Java không còn cơ hội tiếp tục theo đường bình thường.

Còn một trường hợp thứ tư: **`finally` đã bắt đầu nhưng không hoàn tất**. Ví dụ lệnh đóng tài nguyên trong `finally` ném ngoại lệ, hoặc tiến trình bị chấm dứt giữa quá trình đóng. Vì vậy một dòng log ở đầu `finally` không chứng minh toàn bộ công việc dọn dẹp đã thành công.

## 12. `finally` tự ném lỗi và giới hạn của việc dọn dẹp

Xét:

~~~java
static void cleanupCanFail() {
    try {
        throw new IllegalArgumentException("main failure");
    } finally {
        throw new IllegalStateException("cleanup failure");
    }
}
~~~

Phương thức minh họa này kết thúc bằng ngoại lệ `IllegalStateException("cleanup failure")`. Lỗi ban đầu `IllegalArgumentException` bị thay thế và **không tự được gắn làm cause hoặc suppressed exception** trong cấu trúc `try/finally` thủ công đó.

Ngay cả khi JVM đang chạy bình thường, `finally` vẫn không đồng nghĩa mọi dọn dẹp an toàn hoặc thành công. Lưu ý hai mặt:

- Mã dọn dẹp có thể ném lỗi mới và che lỗi chính.
- Mã dọn dẹp có thể chạy lâu, kẹt lock hoặc gặp trạng thái không còn hợp lệ.

Không nên để một lệnh `return` trong `finally` vô tình nuốt lỗi đang truyền. Tránh viết logic nghiệp vụ dài và phức tạp trong `finally`; ưu tiên cấu trúc xử lý đóng tài nguyên có kiểm soát và bọc nguyên nhân khi cần.

## 13. Try-with-resources cũng có giới hạn khi tiến trình chấm dứt

Try-with-resources là lựa chọn tốt khi thao tác với tài nguyên `AutoCloseable`:

~~~java
static String firstLine(String text) throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 new java.io.BufferedReader(
                         new java.io.StringReader(text))) {
        return reader.readLine();
    }
}
~~~

Đây là một phương thức minh họa hợp lệ trong Java 17+. Khi rời `try` theo đường Java thông thường, tài nguyên được đóng tự động. Nếu thân `try` ném ngoại lệ còn `close()` cũng ném, ngoại lệ khi đóng thường được giữ dưới dạng `suppressed exception` thay vì thay thế lỗi chính như một `finally` thủ công viết sai.

Nhưng **try-with-resources không phải cơ chế dọn dẹp sau crash**. Việc đóng tài nguyên vẫn cần mã Java được thực thi khi rời phạm vi. Nếu JVM bị `Runtime.halt`, kill cưỡng bức hoặc mất nguồn trước thời điểm đó, không thể dựa vào lệnh `close()` tự động đã chạy.

Cần phân biệt:

- **Quản lý scope đúng:** try-with-resources giúp bảo đảm đóng trong các đường thoát thông thường.
- **Chống mất dữ liệu khi crash:** cần thiết kế lưu trữ, transaction, commit/rollback, cơ chế phục hồi và xác nhận độ bền ở tầng hệ thống.

Đóng một `BufferedWriter` đúng cách là quan trọng, nhưng `finally` hoặc try-with-resources **không thay thế** cho chính sách flush, fsync, giao dịch hay các bảo đảm lưu trữ cụ thể khi hệ thống có yêu cầu độ bền cao.

## 14. Thiết kế tác vụ để có cơ hội chạy `finally`

Muốn `finally` thực thi đáng tin cậy **trong các đường vận hành bình thường**, hãy tạo các điều kiện để thao tác có thể kết thúc có kiểm soát.

### Có timeout cho các thao tác chờ

Không nên để mọi lời gọi mạng hoặc chờ lock tồn tại vô hạn khi ứng dụng yêu cầu shutdown đúng hạn. Dùng timeout phù hợp của từng API, chẳng hạn timeout kết nối/đọc dữ liệu hoặc chờ có giới hạn. Timeout có thể khiến thao tác trả trạng thái thất bại hoặc ném ngoại lệ, giúp luồng rời `try` và chạy dọn dẹp.

Timeout phải được xử lý theo hợp đồng: chỉ retry khi an toàn, có giới hạn thời gian và tránh lặp vô hạn gây quá tải.

### Hỗ trợ yêu cầu hủy và interrupt

Ví dụ một vòng xử lý dài nhưng có đường thoát:

~~~java
static void doWork(java.util.concurrent.atomic.AtomicBoolean running) {
    try {
        while (running.get()) {
            if (Thread.currentThread().isInterrupted()) {
                break;
            }
            // Thực hiện một đơn vị công việc nhỏ, hữu hạn.
            doOneStep();
        }
    } finally {
        releaseResources();
    }
}
~~~

Đây là **đoạn minh họa**, `doOneStep()` và `releaseResources()` là các hàm của ứng dụng. Giả định một đơn vị công việc có thể hoàn thành hoặc phản hồi hủy; nếu `doOneStep()` tự chặn vô hạn, chỉ kiểm tra `running` ở đầu vòng vẫn không đủ.

`Thread.interrupt()` là tín hiệu hủy hợp tác, không phải kill tiến trình. Nếu phương thức đang chờ ném `InterruptedException`, hãy tuân thủ hợp đồng của tác vụ, thường là chuyển tiếp hoặc khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` khi không thể chuyển tiếp, rồi kết thúc công việc phù hợp.

### Đóng dịch vụ theo nhiều bước

Một quy trình shutdown có kiểm soát có thể gồm:

1. Ngừng nhận công việc mới.
2. Ra tín hiệu yêu cầu những tác vụ hiện tại kết thúc.
3. Chờ trong một thời hạn phù hợp và xử lý các tác vụ không phản hồi.
4. Đóng tài nguyên, hoàn tất hoặc hủy giao dịch đúng cách.
5. Kết thúc JVM sau khi các bước quan trọng đã được xác nhận.

Các bước trên diễn ra **khi ứng dụng còn sống**, thay vì hy vọng `finally` sẽ xử lý mọi thứ sau một lệnh `System.exit` bất ngờ.

## 15. Thiết kế an toàn khi không có `finally`

Với dữ liệu hoặc thao tác có giá trị, hãy giả định tiến trình có thể dừng **ở bất kỳ điểm nào** và có kế hoạch khôi phục.

| Nhu cầu | `finally` giúp gì? | Bảo vệ thêm cần cân nhắc |
| --- | --- | --- |
| Đóng socket/file trong hoạt động bình thường | Chạy mã đóng khi thoát `try` | Timeout, quản lý vòng đời, tài nguyên hệ điều hành |
| Không để giao dịch dở dang | Có thể gọi rollback khi đường lỗi được phát hiện | Transaction/atomic commit của hệ quản trị lưu trữ |
| Ghi dữ liệu quan trọng | Có thể yêu cầu flush/close trên đường bình thường | Cơ chế durable write, commit xác nhận, phục hồi sau crash |
| Tránh xử lý yêu cầu trùng khi khởi động lại | Không giải quyết đầy đủ | Idempotency key, deduplication, trạng thái bền vững |
| Hoàn thành job nền trước shutdown | Hữu ích nếu job thực sự thoát `try` | Graceful shutdown, chờ có giới hạn, quản lý non-daemon/daemon |
| Dọn dẹp sau tiến trình bị kill cưỡng bức | Không được bảo đảm | Lease, TTL, watchdog ngoài tiến trình, quy trình recovery |

### Ví dụ: ghi tệp thay thế an toàn hơn

Với một tệp cấu hình quan trọng, chỉ ghi trực tiếp lên tệp đích rồi đóng trong `finally` có thể để lại dữ liệu không hoàn chỉnh nếu crash giữa chừng.

Một chiến lược thường dùng là ghi vào **tệp tạm cùng hệ thống tệp**, đồng bộ dữ liệu khi cần, rồi đổi tên/thay thế tệp đích bằng thao tác nguyên tử **nếu hệ thống tệp và API thực sự hỗ trợ**. Sau crash, quy trình khởi động kiểm tra trạng thái và xử lý tệp tạm còn dư.

Không phải mọi `rename` hay `Files.move(..., ATOMIC_MOVE)` đều được mọi môi trường hỗ trợ, và “atomic rename” không tự bảo đảm dữ liệu đã được ghi bền vững trên thiết bị. Cần kiểm tra yêu cầu về durability và tính năng của hệ thống lưu trữ cụ thể.

Đó là ví dụ cho cách tư duy đúng: **khả năng chống crash đến từ giao thức cập nhật bền vững**, không chỉ từ `finally`.

## 16. Những hiểu lầm thường gặp

**Hiểu lầm 1 — “`finally` luôn chạy, không có ngoại lệ.”**  
Không đúng. `finally` là phần của luồng điều khiển Java, không phải cơ chế bất tử khi VM hoặc hệ điều hành dừng đột ngột.

**Hiểu lầm 2 — “`System.exit` cũng giống `return` trong `main`.”**  
Không. `return` rời phương thức bình thường và kích hoạt các `finally` liên quan. `System.exit` yêu cầu shutdown JVM, không bảo đảm tháo các khung gọi để chạy `finally`.

**Hiểu lầm 3 — “Có shutdown hook thì mọi `finally` cũng phải chạy.”**  
Không. Shutdown hook và `finally` là hai cơ chế khác nhau. Hook có thể được chạy trong shutdown thông thường ngay cả khi một `finally` trên stack của luồng đang gọi `System.exit` không được chạy.

**Hiểu lầm 4 — “`Runtime.halt` sẽ cho hook dọn dẹp trước.”**  
Không. `halt` chấm dứt VM mà không thực hiện shutdown bình thường. Không dùng nó khi cần một quy trình đóng có kiểm soát.

**Hiểu lầm 5 — “Dừng từ hệ điều hành thì Java luôn kịp lưu mọi thứ.”**  
Không. Kill cưỡng bức, crash và mất điện có thể không cho bytecode Java tiếp tục chạy.

**Hiểu lầm 6 — “Vòng lặp vô hạn khiến Java bỏ qua `finally`.”**  
Chưa chính xác. Nếu vòng lặp không thoát, chương trình đơn giản **chưa đi tới bước thực thi `finally`**. Khác với việc VM đã kết thúc và không còn cơ hội chạy.

**Hiểu lầm 7 — “`Thread.interrupt()` luôn bỏ qua `finally`.”**  
Không. Interrupt có thể khiến thao tác chờ ném `InterruptedException`; nếu luồng rời `try` thì `finally` thường chạy. Nếu code phớt lờ tín hiệu và không thoát, `finally` có thể vẫn chưa chạy.

**Hiểu lầm 8 — “Daemon thread sẽ được JVM chờ dọn dẹp hết trước khi thoát.”**  
Không có bảo đảm như vậy. Nếu công việc quan trọng phải hoàn tất, cần quản lý lifecycle và chờ đúng cách từ các luồng còn giữ JVM hoạt động.

**Hiểu lầm 9 — “Try-with-resources đóng tài nguyên kể cả sau SIGKILL.”**  
Không. Nó chỉ chạy logic đóng tài nguyên khi luồng Java có cơ hội rời scope.

**Hiểu lầm 10 — “Đã in log trong `finally` nghĩa là dữ liệu chắc chắn được lưu.”**  
Không. `finally` có thể mới bắt đầu, log có thể đang đệm, lệnh ghi có thể chưa bền vững hoặc hệ thống có thể crash ngay sau đó.

**Hiểu lầm 11 — “Bắt `Throwable` bảo đảm ứng dụng sẽ sống đủ lâu để chạy `finally`.”**  
Không. Bắt rộng không thể sửa tình huống JVM bị dừng cưỡng bức, mất điện hay code bị kẹt mãi. Bắt `Error` bừa bãi còn có thể khiến hệ thống tiếp tục trong trạng thái không an toàn.

**Hiểu lầm 12 — “Nếu `finally` chạy thì chắc chắn hoàn tất thành công.”**  
Không. Chính mã trong `finally` có thể ném ngoại lệ hoặc bị chặn, và nó có thể bị tiến trình kết thúc giữa chừng.

## 17. Kiểm tra kiến thức

1. `return` từ trong `try` có thông thường làm `finally` chạy trước khi caller nhận kết quả không?
2. Vì sao `System.exit(0)` không thể xem là đồng nghĩa với `return` khỏi `main`?
3. Shutdown hook được khởi chạy trong trường hợp nào, và tại sao không thể dùng nó làm cơ chế duy nhất để chống mất dữ liệu?
4. `Runtime.halt(1)` có chạy shutdown hook theo quy trình shutdown thông thường không?
5. Nếu tiến trình bị `SIGKILL`, có thể bảo đảm `finally` ghi xong dữ liệu không?
6. `while (true)` bên trong `try` không có đường thoát: nên mô tả `finally` “bị bỏ qua” hay “chưa được thực thi”?
7. Khi một luồng đang `CountDownLatch.await()` bị interrupt và `InterruptedException` thoát khỏi `try`, `finally` thường hoạt động thế nào?
8. `Thread.interrupt()` có tương đương với kết thúc cưỡng bức một tiến trình không?
9. Vì sao không nên đặt ghi dữ liệu quan trọng chỉ trong shutdown hook và giả định nó luôn hoàn tất?
10. Nếu daemon thread còn ở giữa `try` nhưng tất cả luồng non-daemon đã kết thúc, liệu JVM có phải chờ daemon thread chạy hết `finally` không?
11. Try-with-resources có đảm bảo đóng tài nguyên sau khi `Runtime.halt` không?
12. Trong `try/finally` thủ công, một `close()` ném ngoại lệ mới có thể gây tác dụng gì với ngoại lệ gốc?
13. Vì sao timeout và hỗ trợ hủy hợp tác giúp tăng cơ hội chạy `finally`?
14. Hãy nêu một cơ chế cần thiết ngoài `finally` để bảo vệ cập nhật dữ liệu khi mất điện.
15. Nếu một dòng log ở đầu `finally` đã được in, ta có thể kết luận toàn bộ mã dọn dẹp phía sau đã thành công không?
16. Nêu sự khác nhau giữa **dừng một tác vụ**, **shutdown JVM thông thường** và **kill cưỡng bức tiến trình**.
17. Với `java FinallyLimitsDemo exit` và `java FinallyLimitsDemo halt`, vì sao các đầu ra được mô tả là đầu ra thường thấy thay vì cam kết tuyệt đối?

### Gợi ý đáp án

1. Có, khi luồng Java rời cấu trúc theo cách bình thường.
2. `System.exit` yêu cầu kết thúc cả JVM, không tháo stack như `return` thông thường.
3. Hook thuộc giai đoạn shutdown có tổ chức; có thể không chạy/hoàn tất khi halt, kill hoặc crash.
4. Không.
5. Không.
6. “Chưa được thực thi” vì chưa xảy ra bước rời `try`.
7. Nó thường chạy trong quá trình lan truyền `InterruptedException`.
8. Không; interrupt là tín hiệu hợp tác và cơ chế của các thao tác chờ hỗ trợ ngắt.
9. Vì hook phụ thuộc việc JVM còn đủ cơ hội shutdown và hoàn thành I/O.
10. Không có bảo đảm.
11. Không.
12. Có thể thay thế/che ngoại lệ gốc; try-with-resources thường lưu lỗi đóng thành suppressed khi thân `try` đã ném lỗi chính.
13. Giúp tác vụ có đường ra khỏi `try` và giải phóng tài nguyên trước shutdown.
14. Ví dụ transaction/atomic commit, đồng bộ dữ liệu bền vững và quy trình khôi phục sau crash.
15. Không; phần còn lại có thể chưa chạy, ném lỗi hoặc bị chấm dứt.
16. Dừng tác vụ có thể đi qua `finally`; JVM shutdown có hook nhưng không tháo mọi stack; kill cưỡng bức có thể dừng tức thời.
17. Vì hành vi ghi console, cơ chế shutdown và môi trường runtime không phải một lời hứa rằng mọi dòng sẽ được xuất ra.

## 18. Ghi nhớ

**`finally` đáng tin cậy trong các đường thoát có kiểm soát của luồng thực thi Java, nhưng không phải bảo đảm tuyệt đối trong trường hợp JVM/tiến trình chấm dứt hoặc khi mã không bao giờ thoát `try`.** `System.exit` không đồng nghĩa với `return`; `Runtime.halt` và kill cưỡng bức còn làm giảm cơ hội dọn dẹp; shutdown hook có phạm vi riêng và cũng không chống được mọi sự cố. Hãy dùng `finally` hoặc try-with-resources để quản lý scope và tài nguyên trong vận hành bình thường, đồng thời xây dựng timeout, hủy hợp tác, shutdown có kiểm soát và cơ chế dữ liệu bền vững để chịu được những trường hợp mà mã Java không còn cơ hội chạy.