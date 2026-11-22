# Đánh giá chi phí StackWalker so với việc tạo toàn bộ stack trace

**StackWalker** được bổ sung từ Java 9 để duyệt stack frame theo nhu cầu. Điểm mạnh về hiệu năng của API này thể hiện rõ nhất khi chương trình chỉ cần tìm một caller, kiểm tra một điều kiện hoặc lấy vài frame đầu tiên. Khi cần toàn bộ stack, phải duyệt mọi frame nên lợi thế giảm lượng công việc có thể không còn rõ rệt.

Không nên kết luận StackWalker luôn nhanh hơn Thread.getStackTrace() hoặc Throwable.getStackTrace(). Chi phí thực tế phụ thuộc độ sâu stack, vị trí frame cần tìm, số frame được tiêu thụ, thông tin cần lấy, phiên bản JVM và cách JIT tối ưu mã.

## 1. Ba cách lấy thông tin stack phổ biến

Java hiện có ba cách chính thường được dùng khi cần đọc stack của luồng đang chạy:

| API | Dữ liệu nhận được | Thời điểm lấy stack | Trường hợp phù hợp |
|---|---|---|---|
| StackWalker.walk() | Stream<StackFrame> để duyệt theo nhu cầu | Trong lúc callback walk() thực thi | Tìm caller, kiểm tra điều kiện, lấy một số frame |
| Thread.currentThread().getStackTrace() | Mảng StackTraceElement[] của thread | Khi gọi getStackTrace() | Cần snapshot toàn bộ stack của thread |
| new Throwable().getStackTrace() | Mảng StackTraceElement[] của Throwable | Khi tạo Throwable và ghi nhận stack | Cần giữ lại stack tại một điểm cụ thể để chẩn đoán |

StackWalker chỉ duyệt stack của thread gọi walk(). Thread.getStackTrace() cũng có thể được gọi trên một đối tượng Thread khác để lấy snapshot stack của thread đó, nếu thread và môi trường JVM cung cấp thông tin.

Throwable lưu snapshot stack tại thời điểm đối tượng được tạo. Constructor thông thường gọi fillInStackTrace(); không cần thực sự throw Throwable thì mới ghi nhận stack. Khi gọi getStackTrace() sau đó, chương trình đọc snapshot đã lưu, không phải stack mới tại thời điểm gọi.

## 2. StackWalker giảm công việc bằng cách duyệt lười

StackWalker cung cấp Stream<StackFrame> cho callback của walk():

~~~java
Optional<String> caller = StackWalker.getInstance().walk(frames ->
        frames
                .filter(frame -> frame.getClassName().startsWith("com.example."))
                .map(StackWalker.StackFrame::getMethodName)
                .findFirst());
~~~

Pipeline này tìm frame đầu tiên thuộc package com.example rồi dừng. Nếu frame phù hợp xuất hiện gần đỉnh stack, các frame phía dưới không cần được duyệt.

Một số terminal operation có khả năng dừng sớm:

- findFirst() dừng khi tìm được phần tử đầu tiên.
- anyMatch() dừng khi tìm thấy phần tử thỏa điều kiện.
- noneMatch() dừng khi tìm thấy phần tử không phù hợp với điều kiện “không có”.
- limit(n) giới hạn số phần tử mà pipeline tiêu thụ.

Ví dụ chỉ lấy ba frame đầu tiên:

~~~java
List<StackWalker.StackFrame> topFrames = StackWalker.getInstance().walk(
        frames -> frames.limit(3).collect(Collectors.toList()));
~~~

Điều này giúp tránh tạo một mảng StackTraceElement[] chứa toàn bộ stack chỉ để đọc vài frame. StackWalker vẫn phải thiết lập quá trình walk và thực hiện các phép lọc; lợi ích đến từ việc không cần đi sâu hơn khi kết quả đã đủ.

Stream chỉ hợp lệ bên trong callback walk(). StackWalker đóng stream khi callback kết thúc, vì vậy hãy trả về kết quả đã thu được như Optional, String, boolean hoặc List; không giữ Stream để sử dụng sau đó.

## 3. Chi phí của Thread.getStackTrace()

Thread.currentThread().getStackTrace() trả về một mảng StackTraceElement[] đại diện cho stack của thread tại thời điểm gọi:

~~~java
StackTraceElement[] trace =
        Thread.currentThread().getStackTrace();

Optional<String> caller = Arrays.stream(trace)
        .filter(frame -> frame.getClassName().startsWith("com.example."))
        .map(StackTraceElement::getMethodName)
        .findFirst();
~~~

Mặc dù pipeline Arrays.stream() dùng findFirst(), phần stack đã được lấy thành mảng trước khi lọc. Vì vậy, việc dừng sớm trong Stream chỉ dừng xử lý mảng; nó không hoàn tác chi phí lấy snapshot stack ban đầu.

Những chi phí cần tính đến:

- JVM phải lấy snapshot stack và cung cấp mảng StackTraceElement[].
- Mảng chứa các frame của stack, kể cả những frame mà ứng dụng có thể không cần.
- Nếu sau đó chương trình lọc hoặc tìm caller, các phép xử lý đó diễn ra sau khi snapshot đã được lấy.

Thread.getStackTrace() vẫn là lựa chọn phù hợp khi cần toàn bộ stack hoặc cần kiểm tra stack của một thread khác. Tài liệu API cũng quy định mảng có thể rỗng nếu thread chưa chạy, chưa được lập lịch hoặc đã kết thúc; JVM có thể bỏ qua một số frame trong những tình huống nhất định.

## 4. Chi phí của Throwable.getStackTrace()

Có thể tạo snapshot stack tại vị trí hiện tại bằng Throwable:

~~~java
Throwable snapshot = new Throwable("diagnostic snapshot");
StackTraceElement[] trace = snapshot.getStackTrace();
~~~

Constructor Throwable thông thường gọi fillInStackTrace() để ghi lại trạng thái stack của thread tại thời điểm tạo đối tượng. Sau đó getStackTrace() trả về mảng StackTraceElement[] đại diện cho snapshot đó.

Khi chỉ muốn tìm caller, cách này thường thực hiện nhiều công việc hơn mức cần thiết:

1. Tạo một đối tượng Throwable.
2. Ghi nhận stack tại thời điểm khởi tạo thông qua fillInStackTrace().
3. Lấy mảng StackTraceElement[].
4. Duyệt mảng để tìm frame cần thiết.

Throwable có giá trị khi ứng dụng thật sự cần một snapshot gắn với một lỗi hoặc một sự kiện chẩn đoán. Ví dụ, exception được ném ra có thể mang stack trace cùng message và cause để log hoặc truyền lên tầng gọi.

Không nên tạo Throwable mới chỉ để dùng như một công cụ tìm caller thường xuyên trong luồng xử lý bình thường. Nếu chỉ cần một vài frame của thread hiện tại, StackWalker thể hiện đúng nhu cầu hơn.

## 5. Mô hình chi phí: tìm một frame và lấy toàn bộ stack

Bảng dưới đây mô tả lượng công việc ở mức khái niệm. Đây không phải cam kết về số lần cấp phát hay thời gian chạy của mọi JVM.

| Tình huống | StackWalker | Thread.getStackTrace() | new Throwable().getStackTrace() |
|---|---|---|---|
| Tìm frame gần đỉnh stack | Có thể dừng ngay khi tìm thấy | Lấy mảng stack trước, sau đó mới tìm | Tạo Throwable và snapshot trước, sau đó mới tìm |
| Tìm frame gần đáy stack | Phải duyệt gần hết stack | Đã lấy toàn bộ mảng; tìm trên mảng | Đã ghi snapshot; tìm trên mảng |
| Lấy toàn bộ frame | Phải duyệt hết; nếu lưu kết quả còn cần collection | Lấy trực tiếp mảng snapshot | Tạo snapshot và lấy mảng |
| Giữ snapshot để đọc về sau | Cần tự materialize kết quả trong callback | Có thể giữ mảng đã nhận | Throwable giữ snapshot tại thời điểm tạo |

Khi chỉ cần một frame đầu tiên, StackWalker có thể giảm số frame cần kiểm tra và tránh việc lấy toàn bộ mảng trước khi lọc. Khi frame mục tiêu nằm sâu hoặc ứng dụng cần toàn bộ stack, StackWalker phải duyệt nhiều frame và lợi thế đó giảm đi.

Nếu chương trình chuyển mọi StackFrame thành StackTraceElement hoặc collect toàn bộ frame, lượng dữ liệu được tạo ra cũng tăng. Không nên dùng StackWalker với mục tiêu lấy toàn bộ stack rồi mặc định rằng nó sẽ ít tốn chi phí hơn API trả về mảng.

## 6. Những yếu tố làm thay đổi chi phí

Không có một con số cố định cho chi phí lấy stack. Các yếu tố sau có thể làm kết quả khác nhau:

- **Độ sâu stack:** stack càng sâu thì việc lấy hoặc duyệt toàn bộ stack thường càng nhiều việc.
- **Vị trí frame cần tìm:** tìm caller gần đỉnh có thể dừng sớm; tìm frame ở gần đáy thường cần duyệt phần lớn stack.
- **Số frame cần giữ:** findFirst() và anyMatch() thường tiêu thụ ít frame hơn collect() hoặc forEach().
- **Thông tin cần đọc:** chỉ lấy method name có thể ít công việc hơn khi cần thêm Class reference hoặc chuyển frame sang StackTraceElement.
- **Tùy chọn StackWalker:** RETAIN_CLASS_REFERENCE cho phép lấy Class object qua getDeclaringClass(); chỉ bật khi thật sự cần.
- **JVM và JIT:** phiên bản JDK, nhà cung cấp JVM, chế độ biên dịch, deoptimization và cấu trúc call stack đều có thể ảnh hưởng kết quả.
- **Mục đích snapshot:** Thread.getStackTrace() và Throwable.getStackTrace() cung cấp mảng có thể giữ lại; StackWalker tập trung vào thao tác duyệt trong callback.

StackWalker.getInstance(options, estimateDepth) nhận estimateDepth làm gợi ý về số frame dự kiến để implementation có thể chọn kích thước buffer ban đầu. Đây là giá trị ước lượng, không phải giới hạn độ sâu stack và cũng không làm cho các frame vượt quá con số đó bị bỏ qua.

Mặc định StackWalker ẩn một số frame nội bộ và không giữ Class reference. Vì vậy, số frame hoặc kết quả lọc giữa StackWalker và hai API mảng không nhất thiết giống tuyệt đối nếu không chuẩn hóa điều kiện so sánh.

## 7. Ví dụ hoàn chỉnh: cùng tìm một caller bằng ba API

Lưu chương trình dưới tên **StackWalkCostDemo.java**. Cả ba cách đều tìm caller gần nhất thuộc lớp ví dụ. Chương trình cũng lấy ba frame ứng dụng đầu tiên bằng StackWalker để minh họa việc giới hạn lượng dữ liệu cần đọc.

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

public class StackWalkCostDemo {
    private static final String APP_CLASS = StackWalkCostDemo.class.getName();
    private static final StackWalker WALKER = StackWalker.getInstance();

    public static void main(String[] args) {
        entry();
    }

    private static void entry() {
        service();
    }

    private static void service() {
        inspect();
    }

    private static void inspect() {
        Optional<String> walkerCaller = WALKER.walk(frames -> frames
                .filter(frame -> frame.getClassName().equals(APP_CLASS))
                .filter(frame -> !frame.getMethodName().equals("inspect"))
                .map(StackWalker.StackFrame::getMethodName)
                .findFirst());

        StackTraceElement[] threadTrace =
                Thread.currentThread().getStackTrace();
        String threadCaller = Arrays.stream(threadTrace)
                .filter(frame -> frame.getClassName().equals(APP_CLASS))
                .filter(frame -> !frame.getMethodName().equals("inspect"))
                .map(StackTraceElement::getMethodName)
                .findFirst()
                .orElse("<none>");

        Throwable snapshot = new Throwable("diagnostic snapshot");
        StackTraceElement[] throwableTrace = snapshot.getStackTrace();
        String throwableCaller = Arrays.stream(throwableTrace)
                .filter(frame -> frame.getClassName().equals(APP_CLASS))
                .filter(frame -> !frame.getMethodName().equals("inspect"))
                .map(StackTraceElement::getMethodName)
                .findFirst()
                .orElse("<none>");

        List<String> topApplicationFrames = WALKER.walk(frames -> frames
                .filter(frame -> frame.getClassName().equals(APP_CLASS))
                .limit(3)
                .map(StackWalker.StackFrame::getMethodName)
                .collect(Collectors.toList()));

        System.out.println("StackWalker caller: " + walkerCaller.orElse("<none>"));
        System.out.println("Thread.getStackTrace caller: " + threadCaller);
        System.out.println("Throwable.getStackTrace caller: " + throwableCaller);
        System.out.println("top application frames: " + topApplicationFrames);
        System.out.println("full thread array available: " + (threadTrace.length > 0));
        System.out.println("full throwable array available: " + (throwableTrace.length > 0));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 9 StackWalkCostDemo.java
java StackWalkCostDemo
~~~

Kết quả stdout:

~~~text
StackWalker caller: service
Thread.getStackTrace caller: service
Throwable.getStackTrace caller: service
top application frames: [inspect, service, entry]
full thread array available: true
full throwable array available: true
~~~

Ba cách đều tìm được caller service. Khác biệt nằm ở cách lấy dữ liệu: StackWalker có thể dừng sau khi tìm thấy frame phù hợp; hai API mảng lấy snapshot stack trước rồi mới lọc. Các dòng boolean chỉ xác nhận hai mảng snapshot có dữ liệu trong lần chạy này, không phải số đo hiệu năng.

## 8. Đo hiệu năng đúng cách bằng JMH

Nếu cần quyết định API nào phù hợp với một ứng dụng cụ thể, hãy đo bằng JMH thay vì chạy một vòng lặp System.nanoTime() đơn giản.

Một phép đo có ý nghĩa nên tách các trường hợp:

1. StackWalker tìm caller bằng filter() và findFirst().
2. Thread.getStackTrace() lấy mảng rồi tìm cùng caller.
3. Tạo Throwable mới, lấy stack trace rồi tìm cùng caller.
4. StackWalker duyệt và collect toàn bộ frame.
5. Thread.getStackTrace() lấy toàn bộ mảng mà không lọc.

Thiết lập benchmark nên có:

- Warmup để JVM và JIT ổn định trước khi ghi số liệu.
- Nhiều measurement iteration và nhiều fork để giảm ảnh hưởng trạng thái JVM trước đó.
- Cùng độ sâu call stack và cùng điều kiện tìm frame cho các cách so sánh.
- Các tình huống tìm thấy frame ở gần đỉnh, gần đáy và không tìm thấy frame.
- Kiểm tra allocation rate, ví dụ dùng profiler GC của JMH, bên cạnh thời gian trung bình.
- Trả về kết quả hoặc dùng Blackhole để tránh benchmark bị loại bỏ vì kết quả không được sử dụng.

Không đo việc tạo Throwable một lần rồi tái sử dụng nếu mục tiêu thực tế là tạo snapshot mới mỗi lần. Cũng không so sánh StackWalker chỉ lấy một frame với Thread.getStackTrace() rồi in toàn bộ mảng; hai trường hợp đang làm lượng công việc khác nhau.

Không có benchmark số liệu trong ví dụ này vì kết quả phụ thuộc môi trường chạy. Hãy đo trên đúng JDK, cấu hình JVM, độ sâu stack và tần suất gọi của ứng dụng sẽ sử dụng API.

## 9. Chọn API theo nhu cầu

| Nhu cầu | Lựa chọn nên cân nhắc | Lý do |
|---|---|---|
| Tìm caller hoặc kiểm tra một frame | StackWalker với findFirst()/anyMatch() | Có thể dừng sớm, không cần lấy toàn bộ mảng |
| Chỉ lấy vài frame đầu | StackWalker với limit(n) | Chỉ duyệt số frame cần thiết |
| Duyệt và phân tích toàn bộ stack hiện tại | StackWalker hoặc Thread.getStackTrace() | Chọn theo kiểu dữ liệu và thao tác xử lý tiếp theo |
| Lưu snapshot stack của một sự kiện | Throwable được tạo tại thời điểm sự kiện | Snapshot gắn với thời điểm tạo Throwable |
| Lấy stack của một thread khác | Thread.getStackTrace() trên Thread tương ứng | StackWalker chỉ walk thread đang gọi |
| Xử lý lỗi và ghi log cause/stack trace | Throwable và printStackTrace()/logger | Giữ ngữ cảnh lỗi, nguyên nhân và stack liên quan |

Trong code chạy thường xuyên như logging helper, caller lookup hoặc framework dispatch, StackWalker thường là lựa chọn tự nhiên vì có thể giới hạn số frame cần đọc. Với xử lý lỗi, hãy giữ Throwable thật và stack trace của lỗi thay vì thay thế nó bằng một lần walk chỉ lấy vài frame.

## 10. Lỗi thường gặp và cách tránh

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Kết luận StackWalker luôn nhanh hơn | Bỏ qua trường hợp phải duyệt toàn bộ stack hoặc pipeline phức tạp | Đánh giá theo số frame cần đọc và benchmark workload thực tế |
| Dùng findFirst() sau khi đã tạo mảng stack | Vẫn phải trả chi phí lấy snapshot toàn bộ trước khi lọc | Dùng StackWalker nếu mục tiêu chỉ là tìm một frame của thread hiện tại |
| Dùng new Throwable() chỉ để tìm caller | Tạo Throwable và ghi nhận snapshot không cần thiết | Dùng StackWalker với filter() và findFirst() |
| Collect toàn bộ StackFrame nhưng kỳ vọng dừng sớm | Pipeline phải tiêu thụ toàn bộ frame cần collect | Dùng findFirst(), anyMatch() hoặc limit(n) khi chỉ cần kết quả giới hạn |
| Giữ Stream ra ngoài callback walk() | Stream đã đóng khi walk() trả về | Materialize kết quả trong callback và chỉ trả dữ liệu cần dùng |
| So sánh hai API với tập frame khác nhau | Kết quả thời gian không tương đương | Chuẩn hóa filter, frame ẩn, độ sâu stack và lượng thông tin |
| Dùng số đo một lần từ System.nanoTime() | Nhiễu do JIT, GC và trạng thái runtime | Dùng JMH với warmup, measurement, forks và allocation profiler |
| Nhầm snapshot Throwable với stack hiện tại | Đọc lại vị trí tạo Throwable thay vì vị trí đang gọi getStackTrace() | Tạo Throwable tại đúng thời điểm muốn ghi nhận stack |

## 11. Ghi nhớ

- StackWalker có từ Java 9 và hỗ trợ truy cập stack frame theo nhu cầu.
- findFirst(), anyMatch() và limit(n) có thể giảm số frame cần duyệt khi kết quả nằm gần đỉnh stack.
- Thread.getStackTrace() trả về mảng snapshot stack của thread; lọc mảng sau đó không tiết kiệm chi phí lấy snapshot ban đầu.
- Constructor Throwable thông thường ghi nhận stack tại thời điểm tạo; getStackTrace() cung cấp snapshot đó dưới dạng mảng.
- StackWalker không mặc định nhanh hơn khi cần toàn bộ stack; kết quả phụ thuộc JVM, độ sâu stack, option và pipeline.
- estimateDepth chỉ là gợi ý kích thước buffer, không phải giới hạn số frame.
- Dùng StackWalker cho caller lookup và short walk; dùng Throwable khi cần lưu ngữ cảnh lỗi; dùng Thread.getStackTrace() khi cần snapshot của một thread.
- Khi cần kết luận hiệu năng, benchmark cùng workload bằng JMH và đo cả thời gian lẫn cấp phát.

## Tài liệu tham khảo

- [JEP 259: Stack-Walking API](https://openjdk.org/jeps/259)
- [StackWalker — Java SE API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/StackWalker.html)
- [Thread.getStackTrace() — Java SE API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.html#getStackTrace())
- [Throwable.getStackTrace() — Java SE API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Throwable.html#getStackTrace())
