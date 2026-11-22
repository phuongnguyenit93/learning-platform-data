# Thread.getStackTrace và Thread.getAllStackTraces

## 1. Lấy ảnh chụp đường gọi mà không cần có ngoại lệ

Một stack trace là danh sách các khung lời gọi (stack frame) thể hiện đường đi đến điểm đang thực thi của một luồng tại lúc lấy thông tin. Nó giúp trả lời “luồng đang ở đâu và đi đến đây qua những phương thức nào”. Không cần phải xảy ra lỗi hoặc ném ngoại lệ mới có stack trace.

`Thread.getStackTrace()` lấy thông tin của một đối tượng luồng cụ thể. `Thread.getAllStackTraces()` lấy một bản đồ stack trace của các **platform thread đang sống**; trên Java hiện hành, bản đồ này không bao gồm virtual thread. Hai API phục vụ quan sát và chẩn đoán, không dùng để thay thế cơ chế đồng bộ hoặc suy ra trạng thái nghiệp vụ chắc chắn. [API Thread](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#getAllStackTraces())

Ví dụ: khi một worker không hoàn tất, thay vì tạo ngoại lệ giả để in ngăn xếp của luồng đang xử lý yêu cầu chẩn đoán, ta có thể lấy stack trace trực tiếp từ `Thread` của worker đó. Nếu cần tìm các nhóm worker đang cùng chờ một đường gọi, ảnh chụp nhiều platform thread giúp có góc nhìn rộng hơn.

## 2. So sánh hai API

| Điểm so sánh | `thread.getStackTrace()` | `Thread.getAllStackTraces()` |
| --- | --- | --- |
| Kiểu phương thức | Phương thức của một đối tượng `Thread` | Phương thức `static` |
| Kết quả | `StackTraceElement[]` | `Map<Thread, StackTraceElement[]>` |
| Phạm vi | Luồng mà biến `thread` trỏ tới | Các platform thread đang sống tại quá trình thu thập |
| Cách chọn mục tiêu | Có sẵn tham chiếu đến luồng | Lọc các entry trong bản đồ sau khi thu thập |
| Giới hạn thường gặp | Luồng có thể đổi vị trí ngay sau khi chụp; có thể không có frame | Các luồng không được bảo đảm chụp đúng cùng một thời điểm; không có virtual thread |
| Nhu cầu điển hình | Xem một worker đã biết hoặc luồng hiện tại | Quan sát nhiều platform thread để tìm mẫu chung |

Lệnh `Thread.currentThread().getStackTrace()` chụp luồng đang thực hiện lời gọi ấy. Nếu chạy lệnh trong một luồng quản trị, kết quả là stack của luồng quản trị, không tự chuyển sang luồng yêu cầu đang bị chậm. Muốn xem luồng khác, cần gọi trên đúng đối tượng `Thread` đó.

## 3. Thứ tự frame và cách đọc StackTraceElement

Nếu mảng khác rỗng, phần tử đầu là đỉnh stack: điểm gần hoạt động hiện tại nhất. Các phần tử tiếp theo đi dần về phía những bên gọi trước đó; phần tử cuối là đáy của đường gọi được trả về. [Thứ tự getStackTrace](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#getStackTrace())

Ví dụ khái niệm:

```text
readBody
loadDocument
handleRequest
run
```

Đọc từ trên xuống: luồng đang trong `readBody`, được `loadDocument` gọi, đi từ `handleRequest`, rồi từ `run`. Muốn hiểu tính năng nghiệp vụ nào dẫn tới thao tác chờ, thường cần tìm frame thuộc mã ứng dụng sau các frame thư viện ở phía trên, không dừng lại ở frame đầu tiên.

Mỗi `StackTraceElement` có thể cung cấp:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getClassName()` | Tên lớp chứa điểm thực thi |
| `getMethodName()` | Tên phương thức của frame |
| `getFileName()` | Tên tệp nguồn nếu có thông tin |
| `getLineNumber()` | Số dòng nguồn nếu xác định được |
| `isNativeMethod()` | Có phải phương thức native không |
| `getModuleName()`, `getModuleVersion()` | Thông tin module khi có |

Tên tệp có thể là `null`, số dòng có thể âm khi không có thông tin phù hợp. Phương thức native có cách biểu diễn riêng; không coi mọi số âm là một dòng Java có thể mở trong trình soạn thảo. Tên tệp trong trace cũng không phải lúc nào là đường dẫn tuyệt đối trên máy. [StackTraceElement](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StackTraceElement.html)

Đọc dữ liệu qua các getter khi cần lọc/phân loại. Không tách chuỗi `toString()` bằng dấu chấm hoặc dấu hai chấm rồi coi định dạng hiển thị là một giao thức dữ liệu ổn định, đặc biệt khi có module và frame native.

## 4. Vì sao trace có thể rỗng?

`getStackTrace()` có thể trả mảng độ dài `0` khi luồng chưa bắt đầu, chưa được hệ thống cho thực thi sau khi bắt đầu, hoặc đã kết thúc. JVM còn được phép bỏ qua một số frame; trong trường hợp không có thông tin stack, có thể trả mảng rỗng. [Các trường hợp rỗng của getStackTrace](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#getStackTrace())

Hệ quả khi viết mã chẩn đoán:

- Kiểm tra độ dài trước khi đọc phần tử đầu; không dùng `trace[0]` vô điều kiện.
- Không hiểu mảng rỗng là luồng đang rảnh hoặc không có vấn đề.
- Không coi thiếu một frame là bằng chứng phương thức ấy chưa từng chạy.
- Khi tìm entry trong bản đồ, xử lý cả trường hợp không có entry và trường hợp có entry nhưng mảng rỗng; hai tình huống khác nhau.

Trace không phải lịch sử thực thi. Một hàm đã chạy xong trước lúc chụp sẽ không hiện như một frame đang hoạt động. Nếu tác vụ được chuyển qua executor hoặc một bước bất đồng bộ, stack của worker thường thể hiện đường gọi đang chạy trên worker; nó không tự chứa toàn bộ lịch sử luồng đã gửi việc.

## 5. Chương trình hoàn chỉnh: một luồng, nhiều luồng và vòng đời

Lưu mã thành `StackTraceApiDemo.java`. Chương trình dùng Java 17 trở lên và tạo một platform thread bằng `new Thread`. Worker có một cổng chờ để nó chưa rời phương thức cần quan sát trong lúc luồng chính lấy trace.

```java
import java.util.Arrays;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.stream.Collectors;

public class StackTraceApiDemo {
    private static void first() {
        second();
    }

    private static void second() {
        String methods = Arrays.stream(Thread.currentThread().getStackTrace())
                .filter(frame -> frame.getClassName()
                        .equals(StackTraceApiDemo.class.getName()))
                .map(StackTraceElement::getMethodName)
                .collect(Collectors.joining(" <- "));
        System.out.println("self=" + methods);
    }

    private static void awaitSignal(
            CountDownLatch entered, CountDownLatch release) {
        entered.countDown();
        try {
            release.await();
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        }
    }

    private static boolean hasMethod(StackTraceElement[] trace, String method) {
        return Arrays.stream(trace).anyMatch(frame ->
                frame.getClassName().equals(StackTraceApiDemo.class.getName())
                        && frame.getMethodName().equals(method));
    }

    public static void main(String[] args) throws InterruptedException {
        first();

        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        Thread worker = new Thread(
                () -> awaitSignal(entered, release), "diagnostic-worker");

        System.out.println("new-empty=" + (worker.getStackTrace().length == 0));
        worker.start();
        entered.await();
        try {
            StackTraceElement[] single = worker.getStackTrace();
            System.out.println("single-has-awaitSignal="
                    + hasMethod(single, "awaitSignal"));

            Map<Thread, StackTraceElement[]> all = Thread.getAllStackTraces();
            System.out.println("all-contains-worker=" + all.containsKey(worker));
            StackTraceElement[] workerTrace = all.get(worker);
            System.out.println("all-has-awaitSignal="
                    + (workerTrace != null
                    && hasMethod(workerTrace, "awaitSignal")));
        } finally {
            release.countDown();
            worker.join();
        }

        System.out.println("terminated-empty="
                + (worker.getStackTrace().length == 0));
    }
}
```

Biên dịch và chạy:

```shell
javac StackTraceApiDemo.java
java StackTraceApiDemo
```

Stdout đã kiểm tra trên JDK 24:

```text
self=second <- first <- main
new-empty=true
single-has-awaitSignal=true
all-contains-worker=true
all-has-awaitSignal=true
terminated-empty=true
```

### Phần lấy stack của chính mình

`main` gọi `first`, `first` gọi `second`, và `second` chụp stack. Bộ lọc chỉ giữ frame có tên lớp đúng bằng lớp ví dụ, nên kết quả còn `second <- first <- main`. Nó loại các frame của API/JVM mà không phụ thuộc vào việc chúng nằm ở chỉ số nào.

Không áp dụng quy tắc “caller luôn ở trace[2]”. Wrapper, đường gọi và mức thông tin JVM cung cấp có thể khác. Khi cần tìm một frame ứng dụng, dùng tiêu chí rõ ràng như tên lớp/phương thức; khi cần phân tích bên gọi của luồng hiện tại với chính sách lọc chuyên biệt, có thể xem xét `StackWalker`.

### Phần lấy stack của worker

`entered.countDown()` cho luồng chính biết worker đã vào `awaitSignal`. `release` còn đóng nên worker chưa thể hoàn thành phương thức đó. Luồng chính lấy cả `worker.getStackTrace()` và entry tương ứng trong `Thread.getAllStackTraces()`, rồi tìm frame `awaitSignal`.

Bộ lọc kiểm tra cả tên lớp và tên phương thức: chỉ tìm chuỗi `await` trong văn bản hiển thị sẽ dễ trộn lẫn nhiều hàm không liên quan. Các frame thư viện ở đỉnh có thể thay đổi giữa các JDK, vì vậy chương trình không in chúng như một stdout cố định.

Khối `finally` mở cổng và `join` worker để chương trình kết thúc sạch. Sau khi `join` hoàn tất, worker đã kết thúc nên lần gọi stack tiếp theo rỗng. Trước `start`, mảng cũng rỗng nhưng nguyên nhân vòng đời khác.

JVM được phép thiếu thông tin frame trong những tình huống đặc biệt, nên không coi các phép tìm frame của chương trình là bảo đảm tuyệt đối cho mọi máy ảo. Chúng là kết quả thực nghiệm trên môi trường đã nêu. Bảo đảm về phối hợp worker trong ví dụ đến từ latch và join, không đến từ việc tìm thấy một tên phương thức trong trace.

## 6. Bản đồ nhiều luồng không phải ảnh chụp nguyên tử toàn hệ thống

Các luồng có thể vẫn thực thi trong khi `getAllStackTraces()` thu thập. Stack của từng luồng là ảnh chụp và có thể được lấy ở các thời điểm khác nhau. Một luồng trong bản đồ có thể đã kết thúc khi mã của bạn bắt đầu duyệt entry. [Ngữ nghĩa ảnh chụp getAllStackTraces](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#getAllStackTraces())

Vì thế, không dùng hai stack trong một bản đồ để khẳng định chắc chắn hai luồng cùng giữ/chờ một trạng thái nghiệp vụ tại đúng một nanô giây. Nếu gọi thêm `getState()` sau khi có bản đồ, trạng thái đó lại là một quan sát khác; nó không tự đồng bộ thời điểm với mảng frame đã thu thập.

Kết quả cũng không phải một màn hình tự cập nhật. Giữ mảng rồi in lại sau đó chỉ in dữ liệu đã lấy; muốn quan sát diễn biến phải lấy mẫu mới. Khi so sánh các mẫu, ghi thời điểm thu thập và định danh phù hợp, thay vì chỉ nhìn chuỗi frame.

Tên luồng hữu ích cho người đọc nhưng không bắt buộc duy nhất. Trong cùng một ảnh chụp, dùng chính khóa `Thread` để chọn đúng đối tượng nếu đã có tham chiếu, như `all.get(worker)` trong ví dụ. Khi ghi định danh số trên Java hiện hành, có thể dùng `threadId()` từ Java 19 trở lên; ví dụ nền Java 17 cố ý không cần API đó.

## 7. Lọc và trình bày kết quả có chủ đích

Đoạn sau là hàm tiện ích đặt bên trong một lớp Java, không phải chương trình độc lập. Nó giữ các luồng theo tiền tố tên để hiển thị, sắp tên cho dễ đọc và giới hạn số frame **in ra** mỗi luồng:

```java
static void printPlatformThreads(String prefix, int maxFrames) {
    if (prefix == null || maxFrames < 0) {
        throw new IllegalArgumentException();
    }
    Map<Thread, StackTraceElement[]> snapshot = Thread.getAllStackTraces();
    snapshot.entrySet().stream()
            .filter(entry -> entry.getKey().getName().startsWith(prefix))
            .sorted(java.util.Comparator.comparing(
                    entry -> entry.getKey().getName()))
            .forEach(entry -> {
                System.out.println(entry.getKey().getName());
                StackTraceElement[] trace = entry.getValue();
                if (trace.length == 0) {
                    System.out.println("  <no stack information>");
                }
                for (int i = 0; i < Math.min(maxFrames, trace.length); i++) {
                    System.out.println("  at " + trace[i]);
                }
                if (trace.length > maxFrames) {
                    System.out.println("  <remaining frames omitted>");
                }
            });
}
```

Hàm cần import `java.util.Map`. Đầu ra thực tế phụ thuộc các luồng đang sống, nên không có danh sách cố định để so sánh như chương trình chính. Các tên giống nhau vẫn có thể xuất hiện nhiều lần; việc sắp theo tên chỉ phục vụ hiển thị, không đặt ra thứ tự thực thi.

Giới hạn `maxFrames` ở đây chỉ giảm lượng hiển thị sau khi đã thu thập. Tương tự, lọc tên sau `getAllStackTraces()` không biến nó thành thao tác chỉ chụp các luồng khớp. Nếu đã biết đúng một luồng cần xem, dùng API một luồng sẽ bám sát phạm vi chẩn đoán hơn.

## 8. Từ stack đến giả thuyết, rồi tìm bằng chứng tiếp

Ví dụ các mẫu quan sát và hướng suy luận:

| Frame/đường gọi quan sát được | Câu hỏi tiếp theo |
| --- | --- |
| Đường vào vùng synchronized của mã ứng dụng | Luồng đang chờ monitor nào, ai giữ và giữ để làm gì? |
| `LockSupport.park` bên dưới AQS | Đang chờ khóa, giấy phép, điều kiện hay công cụ nào? |
| Đường lấy phần tử từ hàng đợi | Có công việc cần xử lý không, nguồn cấp việc còn hoạt động không? |
| Frame I/O và hàm ứng dụng gọi nó | Đang tương tác tài nguyên nào, có thời hạn và số liệu độ trễ liên quan không? |
| Một phương thức ứng dụng lặp lại trong nhiều mẫu | Có tiến triển thực tế không, hay đang xử lý lâu/vòng lặp? |

Một stack không tự chứa biến cục bộ, đối số, giá trị dữ liệu hoặc mọi thông tin về chủ sở hữu khóa. Nó cũng không tự cho biết phần trăm CPU. Muốn điều tra deadlock hoặc cạnh tranh monitor/khóa, cần thông tin bổ sung về các đối tượng đồng bộ và quan hệ sở hữu, chẳng hạn từ công cụ dump hoặc API quản lý phù hợp.

`ThreadInfo` có thể cung cấp thông tin stack cùng các đối tượng/khóa liên quan trên phạm vi công cụ hỗ trợ. Khi dùng thêm nó, vẫn phải tôn trọng tính ảnh chụp và khả năng thay đổi giữa các lần quan sát. [ThreadInfo](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadInfo.html)

Không dừng hoặc ngắt luồng chỉ để “giữ nguyên stack” rồi chụp; điều đó đổi hành vi của hệ thống đang cần chẩn đoán. Phối hợp có kiểm soát như ví dụ phù hợp trong thực nghiệm; trong hệ thống đang chạy, thu thập bằng cơ chế quan sát được hỗ trợ và phân tích nhiều nguồn bằng chứng.

## 9. Virtual thread: chữ All không có nghĩa mọi loại luồng

Trên Java hiện hành, `Thread.getAllStackTraces()` chỉ trả các **live platform thread** và không liệt kê virtual thread. Bỏ qua giới hạn này có thể khiến một hệ thống dùng nhiều virtual thread trông như có rất ít công việc đang hoạt động. [Phạm vi chính thức getAllStackTraces](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#getAllStackTraces())

Nếu đang giữ tham chiếu đến một virtual thread cụ thể, API lấy stack của một `Thread` là câu hỏi riêng với API liệt kê tất cả. Khi cần ảnh chụp nhiều virtual thread, chọn công cụ chẩn đoán có hỗ trợ trên JDK đích; không suy rằng đổi cách lọc bản đồ platform thread sẽ làm các virtual thread xuất hiện.

Cũng không lấy stack carrier thread rồi coi đó tự động là toàn bộ stack logic của một virtual thread bạn đang quan tâm. Cần xác định đúng loại luồng và công cụ trước khi diễn giải dữ liệu.

## 10. Chọn công cụ gần nhất với câu hỏi

| Câu hỏi | Điểm bắt đầu |
| --- | --- |
| Luồng hiện tại đang đi qua các phương thức nào? | `Thread.currentThread().getStackTrace()` |
| Worker cụ thể đang ở đâu? | `worker.getStackTrace()` |
| Các platform thread đang có mẫu chờ gì? | `Thread.getAllStackTraces()` cùng thông tin liên quan |
| Cần duyệt/lọc stack của luồng hiện tại theo chính sách có kiểm soát | `StackWalker` |
| Cần biết ngoại lệ được tạo/ném ở đường gọi nào theo cơ chế ngoại lệ | Stack trace của `Throwable` tương ứng |
| Cần quan sát JVM từ ngoài tiến trình hoặc thêm thông tin khóa | Công cụ chẩn đoán JDK phù hợp, kiểm tra khả năng trên JVM đích |

`StackWalker` duyệt stack **luồng hiện tại** theo API stream trong phạm vi callback `walk`; nó không thay `getAllStackTraces` để duyệt các luồng khác. Nó cho phép chọn cách lọc/thông tin cần lấy, nhưng không nên tuyên bố mọi trường hợp đều nhanh hơn mà không đo. [StackWalker](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StackWalker.html)

Stack của một `Throwable` thường gắn với thời điểm thu thập thông tin cho ngoại lệ ấy; nó không phải màn hình trực tiếp của một worker hiện tại. Đừng nhầm chẩn đoán “luồng đang ở đâu” với lịch sử một lỗi đã được ghi nhận.

## 11. Chi phí và vòng đời của dữ liệu chẩn đoán

Việc thu thập stack và tạo các mảng/frame có chi phí. Chụp toàn bộ platform thread trên mỗi yêu cầu hoặc trong vòng lặp dày có thể làm nặng hệ thống và sinh lượng log lớn. Thiết kế tần suất, phạm vi và số mẫu theo câu hỏi cần giải đáp; số thread và độ sâu stack có thể thay đổi nhiều theo tải.

Bản đồ chứa tham chiếu đến đối tượng `Thread` và các mảng trace. Không giữ vô hạn nhiều bản đồ thô trong bộ nhớ chỉ để làm lịch sử; chuyển thành thông tin báo cáo cần thiết rồi giải phóng dữ liệu theo vòng đời thu thập. Nếu cần lưu mẫu dài hạn, đặt giới hạn rõ ràng.

Stack thường không chứa trực tiếp toàn bộ giá trị biến, nhưng vẫn có thể lộ cấu trúc lớp, tính năng và thông tin triển khai. Trong một chức năng chẩn đoán của sản phẩm, chọn nơi lưu/hiển thị phù hợp và tránh đưa dump hàng loạt vào phản hồi thông thường của người dùng cuối.

## 12. Lỗi phổ biến và bài tập

| Lỗi | Cách sửa |
| --- | --- |
| Cứ lấy `trace[2]` để xác định caller | Dùng tiêu chí frame rõ ràng hoặc API duyệt stack phù hợp |
| Thấy trace rỗng rồi kết luận worker không có lỗi | Kiểm tra vòng đời và khả năng thiếu thông tin |
| Lọc theo tên rồi cho rằng chỉ các luồng ấy được chụp | Nhớ bước thu thập toàn bộ đã diễn ra trước lọc |
| Coi các entry là cùng một thời điểm tuyệt đối | Ghi nhận ngữ nghĩa ảnh chụp và đối chiếu nhiều mẫu |
| Dùng getAllStackTraces để đếm cả virtual thread | Chọn công cụ hỗ trợ loại luồng cần quan sát |
| Dùng trace làm cơ chế đồng bộ | Dựa vào khóa/latch/công cụ giao tiếp đúng hợp đồng |

1. **Vì sao `Thread.currentThread().getStackTrace()` ở endpoint quản trị không tự cho stack của worker đang treo?** Vì nó chụp luồng đang thực thi endpoint; phải chọn đúng đối tượng worker hoặc công cụ quan sát nhiều luồng.
2. **Bản đồ có entry worker nhưng mảng rỗng có nghĩa gì?** Entry xác định luồng được thu thập; JVM không cung cấp frame cho ảnh chụp đó. Không được suy từ mảng rỗng rằng worker chưa từng chạy phương thức nào.
3. **Vì sao chương trình mẫu cần latch dù đã có API lấy trace?** Latch giữ vòng đời thực nghiệm ổn định; trace chỉ là bằng chứng quan sát, không giữ worker ở một điểm hay bảo đảm nó chờ.
4. **Cùng một frame xuất hiện trong ba ảnh chụp có chắc là vòng lặp vô hạn không?** Chưa. Nó có thể là thao tác chờ hoặc xử lý lâu; cần ghép thời gian, CPU, dữ liệu tiến triển và ngữ cảnh công việc.
5. **Giới hạn in năm frame có làm chi phí capture thành đúng năm frame không?** Không. Giới hạn hiển thị sau thu thập không thay đổi phạm vi lời gọi API đã thực hiện.
