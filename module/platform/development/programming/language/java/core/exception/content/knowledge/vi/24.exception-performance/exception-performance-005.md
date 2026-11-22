# Stack trace bị lược bỏ và tối ưu phụ thuộc JVM trong Java

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **stack trace được rút gọn khi hiển thị** với **stack trace thật sự trống hoặc không được ghi nhận**.
- Giải thích ý nghĩa dòng `... N more` trong `Throwable.printStackTrace()` khi có cause hoặc suppressed exception.
- Hiểu cơ chế chi phí của việc tạo, ghi nhận và hiển thị stack trace, đặc biệt ở đường lỗi xuất hiện thường xuyên.
- Nhận diện tối ưu thường gọi là **FastThrow** trong HotSpot, liên quan tùy chọn `-XX:+OmitStackTraceInFastThrow`, và hiểu vì sao không nên xem hành vi này là bảo đảm chung cho mọi JVM.
- Phân biệt tối ưu nội bộ JVM với việc **chủ động tắt writable stack trace** trong một lớp `Throwable` tùy biến.
- Chẩn đoán trường hợp log chỉ có tên lỗi hoặc stack trace thiếu frame: kiểm tra API `getStackTrace()`, cách log, cấu hình JVM và điều kiện tái hiện.
- Cân bằng hiệu năng và khả năng quan sát: không dùng exception cho luồng điều khiển thường xuyên, không tự ý xóa trace của lỗi quan trọng.
- Viết và chạy các ví dụ Java 17+ có kết quả xác định mà không dựa vào việc JIT có kích hoạt FastThrow hay không.

**Phạm vi:** Java Core Exception, khía cạnh hiệu năng và chẩn đoán. Các tùy chọn `-XX` được nhắc tới là tùy chọn của **HotSpot/OpenJDK tương thích**, không phải một phần cú pháp hay hợp đồng Java SE dùng chung cho mọi JVM.

## 2. Stack trace là gì, được tạo vào lúc nào?

`Throwable` trong Java lưu thông tin liên quan đến vị trí thực thi khi ngoại lệ được tạo hoặc khi phương thức `fillInStackTrace()` được gọi trong cơ chế thông thường. Khi ném một `Throwable` đã được tạo từ trước, JVM không mặc nhiên chụp lại trace mới ở mỗi lần `throw`.

Ví dụ:

~~~java
IllegalStateException failure = new IllegalStateException("invalid");
throw failure;
~~~

Đây là **đoạn mã minh họa** ở trong một phương thức có quyền ném `IllegalStateException`. Stack trace của `failure` bình thường phản ánh **nơi đối tượng ngoại lệ được khởi tạo**, không nhất thiết là dòng `throw failure` nếu hai vị trí khác nhau.

Mỗi phần tử `StackTraceElement` có thể chứa tên class, tên phương thức, tên file, số dòng và thông tin liên quan tới module/class loader trong các bản Java hỗ trợ. Tuy nhiên, một frame có thể không có số dòng hoặc thông tin file nguồn nếu runtime không cung cấp đủ dữ liệu.

Các thao tác thường gặp:

| API | Ý nghĩa |
| --- | --- |
| `new IllegalStateException("...")` | Tạo exception; trong trường hợp thông thường ghi nhận dấu vết thực thi |
| `throw exception` | Ném đối tượng; không có bảo đảm tự chụp lại trace mới khi tái ném |
| `exception.getStackTrace()` | Lấy mảng `StackTraceElement[]` mà exception hiện cung cấp |
| `exception.printStackTrace()` | In exception, các frame, chuỗi cause và suppressed theo cách hiển thị của JDK |
| `exception.getCause()` | Truy nguyên nhân được nối bằng cause |
| `exception.getSuppressed()` | Lấy các ngoại lệ phụ được giữ lại, chẳng hạn lỗi đóng tài nguyên |
| `exception.fillInStackTrace()` | Ghi lại stack trace theo điểm gọi hiện tại khi writable, thay đổi dấu vết được lưu |
| `exception.setStackTrace(elements)` | Thay thế các phần tử stack trace được công bố nếu cho phép ghi |

**Không đồng nhất** mảng frame trong `getStackTrace()` với văn bản được in bởi `printStackTrace()`. Văn bản in có thể áp dụng quy tắc rút gọn hoặc bị cắt bởi hệ thống thu thập log.

## 3. Ba hiện tượng “không thấy đầy đủ stack trace”

Cùng nhìn thấy một log ít dòng, ta có thể gặp những nguyên nhân rất khác nhau.

| Hiện tượng | Bản chất | Cách kiểm tra |
| --- | --- | --- |
| Log xuất hiện `... N more` | `printStackTrace` rút gọn **các frame chung** giữa exception và cause/suppressed | Đọc cause, so sánh mảng `getStackTrace()`, kiểm tra phần trước của log |
| `getStackTrace().length == 0` | Exception có thể không ghi frame: thiết kế custom Throwable, tối ưu JVM cho một số lỗi, hoặc cấu hình/điều chỉnh khác | Kiểm tra class exception, cách tạo, runtime, flags và khả năng tái hiện |
| Log chỉ ghi `exception.getMessage()` hoặc bị cắt | Hệ thống logging/collector chưa hiển thị toàn bộ đối tượng `Throwable` | So sánh log với `getStackTrace()`, kiểm tra cấu hình logger/formatter và giới hạn kích thước |

Một trường hợp thứ tư là **stack trace có một số frame nhưng ít hơn mong đợi**. Nguyên nhân có thể nằm ở thời điểm đối tượng được tạo, cách tái ném, các phương thức viết lại trace hoặc giới hạn ghi nhận/hiển thị. Không nên tự động quy mọi trace ngắn về JIT.

Nếu muốn biết có thật sự mất frame hay chỉ không được hiển thị, bước đầu hợp lý là kiểm tra `getStackTrace().length` trên **chính đối tượng exception** trước khi kết luận.

## 4. Dòng `... N more`: rút gọn khi in, không nhất thiết mất dữ liệu

Khi một exception bọc một exception khác, phần cuối stack trace của cả hai thường trùng nhau vì chúng cùng đi qua những lời gọi ở phía ngoài.

Ví dụ minh họa cấu trúc:

~~~text
java.lang.RuntimeException: Không thể xử lý
    at Example.service(Example.java:20)
    at Example.main(Example.java:30)
Caused by: java.lang.IllegalStateException: Hỏng dữ liệu
    at Example.repository(Example.java:10)
    at Example.service(Example.java:18)
    ... 1 more
~~~

Đây là **ví dụ hình thức trình bày**, không phải stdout chính xác của một chương trình. Trong cách in truyền thống của JDK, `... 1 more` có nghĩa **một frame cuối của cause trùng với phần cuối của stack trace bao ngoài đang được in**, nên không cần lặp lại nguyên frame đó.

Cơ chế:

1. `printStackTrace` in thông tin exception bên ngoài.
2. Khi in cause, nó tìm các phần tử cuối của cause trùng phần cuối stack trace ở cấp bao gần nhất.
3. Các frame trùng ở cuối có thể được thay bằng dòng `... N more`.
4. Mảng `getStackTrace()` của cause có thể vẫn chứa đầy đủ những phần tử đó.

Nếu cause lại có cause, mỗi cấp có thể được rút gọn so với trace đang bao nó. Các suppressed exceptions cũng có thể được hiển thị có thụt dòng và rút gọn frame chung.

**`... N more` không phải bằng chứng FastThrow hoặc mất stack trace tại JVM.** Nó là cách hiển thị giảm lặp. Nếu cần kiểm tra số frame nguyên bản, đọc trực tiếp `getStackTrace()` của ngoại lệ ở cấp tương ứng.

### Khi nào không có `... N more`?

Nếu không có phần đuôi frame chung, có thể không có dòng rút gọn. Nếu logger dùng định dạng riêng, nó cũng có thể chọn cách hiển thị khác với `printStackTrace`. Do đó không nên coi việc có/không có dòng này là điều kiện bắt buộc của mọi hệ thống ghi log.

## 5. Ví dụ Java 17 độc lập: phần in rút gọn nhưng cause vẫn còn frame

Lưu tệp **CommonFramesDemo.java**:

~~~java
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.regex.Pattern;

public class CommonFramesDemo {

    static void repository() {
        throw new IllegalStateException("bad data");
    }

    static void service() {
        try {
            repository();
        } catch (IllegalStateException original) {
            throw new RuntimeException("service failure", original);
        }
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (RuntimeException outer) {
            Throwable cause = outer.getCause();
            int frameCountBefore = cause.getStackTrace().length;

            StringWriter buffer = new StringWriter();
            outer.printStackTrace(new PrintWriter(buffer));
            String rendered = buffer.toString();

            boolean abbreviated = Pattern
                    .compile("\\.\\.\\. \\d+ more")
                    .matcher(rendered)
                    .find();

            System.out.println("Outer has frames: "
                    + (outer.getStackTrace().length > 0));
            System.out.println("Cause has frames: "
                    + (frameCountBefore > 0));
            System.out.println("Print has Caused by: "
                    + rendered.contains("Caused by: "));
            System.out.println("Print abbreviates common frames: "
                    + abbreviated);
            System.out.println("Cause frames still available: "
                    + (cause.getStackTrace().length == frameCountBefore));
        }
    }
}
~~~

Biên dịch và chạy trên Java 17:

~~~bash
javac -encoding UTF-8 CommonFramesDemo.java
java CommonFramesDemo
~~~

**Stdout kỳ vọng trong cách in chuẩn của Java 17:**

~~~text
Outer has frames: true
Cause has frames: true
Print has Caused by: true
Print abbreviates common frames: true
Cause frames still available: true
~~~

Lý giải:

- `repository()` tạo `IllegalStateException`; `service()` bắt nó và tạo `RuntimeException` với `original` làm cause.
- Stack trace của wrapper và cause có phần đuôi lời gọi chung, nên cách in chuẩn rút gọn những frame trùng.
- Việc dựng chuỗi qua `StringWriter` không sửa mảng stack trace của cause.
- Chương trình **không cần JIT** và không thử kích hoạt bất kỳ tối ưu HotSpot đặc biệt nào.
- Dòng kiểm tra cuối cho thấy rút gọn trong văn bản không làm mảng `getStackTrace()` của cause bị xóa.

**Lưu ý về tính di động:** ký hiệu `... N more` là cách trình bày quen thuộc của `Throwable.printStackTrace` trên JDK chuẩn; các hệ thống logging bên ngoài có thể render theo định dạng khác. Ví dụ nhắm tới Java 17 với cách in chuẩn, không phải một giao thức văn bản giữa các JVM/logger bất kỳ.

## 6. Khi stack trace thật sự trống: chủ động tạo exception không ghi trace

Java cung cấp protected constructor của `Throwable` và các lớp con phù hợp với chữ ký:

~~~java
Throwable(String message, Throwable cause,
          boolean enableSuppression,
          boolean writableStackTrace)
~~~

Chữ ký ở trên **minh họa API protected**, không phải lời gọi khởi tạo class `Throwable` trong code hoàn chỉnh.

Trong lớp exception tự định nghĩa có thể dùng:

~~~java
public final class LightweightException extends RuntimeException {
    public LightweightException(String message) {
        super(message, null, true, false);
    }
}
~~~

Đây là **lớp độc lập**, lưu thành `LightweightException.java` nếu sử dụng riêng. Tham số `writableStackTrace=false` yêu cầu không ghi stack trace của đối tượng mới, nên `getStackTrace()` trả mảng rỗng. Các lần gọi `fillInStackTrace()` và `setStackTrace(...)` không khôi phục được frame theo cách thông thường trên đối tượng đã tắt writable stack trace.

**Đây là quyết định thiết kế của lớp exception**, không phải FastThrow. Nó có hiệu lực cả trong trường hợp ngoại lệ được tạo lần đầu; không cần lặp hàng nghìn lần.

### Đánh đổi

Ưu điểm có thể có:

- Giảm công việc và chi phí liên quan đến ghi nhận stack trace cho đối tượng exception.
- Hợp lý trong một số đường điều khiển được biết trước, thường xuyên và đã có đủ ngữ cảnh khác.

Nhược điểm:

- Mất vị trí tạo exception trong stack trace của chính nó.
- Khó truy ngược luồng gọi khi một lỗi bất thường xuất hiện.
- Nếu quyết định này được dùng rộng rãi, log production có thể chỉ còn tên lỗi và message.

**Không tối ưu bằng cách tắt stack trace cho mọi ngoại lệ.** Với lỗi hiếm và có giá trị chẩn đoán cao, chi phí đo đạc có thể nhỏ hơn nhiều so với thời gian khắc phục sự cố do không có trace.

## 7. Ví dụ Java 17 độc lập: writableStackTrace=false

Lưu tệp **DisabledTraceDemo.java**:

~~~java
public class DisabledTraceDemo {

    static final class LightweightFailure extends RuntimeException {
        LightweightFailure(String message) {
            super(message, null, true, false);
        }
    }

    public static void main(String[] args) {
        LightweightFailure failure = new LightweightFailure("expected");

        System.out.println("Initial frames: "
                + failure.getStackTrace().length);
        System.out.println("Cause: " + failure.getCause());

        StackTraceElement fake = new StackTraceElement(
                "Example", "method", "Example.java", 42);
        failure.setStackTrace(new StackTraceElement[]{fake});

        System.out.println("Frames after setStackTrace: "
                + failure.getStackTrace().length);

        failure.fillInStackTrace();
        System.out.println("Frames after fillInStackTrace: "
                + failure.getStackTrace().length);

        System.out.println("Message is still present: "
                + "expected".equals(failure.getMessage()));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 DisabledTraceDemo.java
java DisabledTraceDemo
~~~

**Stdout chính xác:**

~~~text
Initial frames: 0
Cause: null
Frames after setStackTrace: 0
Frames after fillInStackTrace: 0
Message is still present: true
~~~

Điểm đáng nhớ:

- `super(message, null, true, false)` tắt khả năng ghi stack trace cho **chính đối tượng** `LightweightFailure`.
- `getMessage()` vẫn còn; “không có frame” không có nghĩa Throwable mất tất cả thông tin.
- `getCause()` trả `null` vì ví dụ truyền cause `null`. Một exception tùy biến khác có thể vẫn giữ cause ngay cả khi không lưu trace riêng.
- `setStackTrace` và `fillInStackTrace` không tái tạo frame do writable stack trace đã tắt từ lúc khởi tạo.

Lưu ý: việc khởi tạo custom exception dạng này là lựa chọn chủ động, phải ghi rõ trong thiết kế API. Không sử dụng nó chỉ để làm gọn log một cách tùy tiện.

## 8. FastThrow: tối ưu phụ thuộc HotSpot/JIT

Ngoài trường hợp chủ động tắt writable stack trace, một số bản HotSpot có tối ưu thường gọi là **FastThrow**, gắn với tùy chọn:

~~~bash
-XX:+OmitStackTraceInFastThrow
~~~

Ý tưởng khái quát: khi JIT nhận diện một số **ngoại lệ runtime ngầm định** xảy ra nhiều lần ở cùng vị trí bytecode, runtime có thể dùng đường xử lý nhanh và bỏ việc ghi nhận stack trace chi tiết cho các lần ném lỗi được tối ưu. Mục tiêu là giảm overhead ở đường ngoại lệ lặp lại dày đặc.

Các tình huống hay được thảo luận gồm một số lỗi phát sinh từ phép toán hoặc thao tác bytecode, chẳng hạn:

- `NullPointerException` khi dereference null.
- `ArithmeticException` khi chia nguyên cho 0.
- `ArrayIndexOutOfBoundsException` ở truy cập mảng sai chỉ số.
- `ClassCastException` ở phép ép kiểu sai.

**Không coi danh sách này là quy tắc bảo đảm rằng mọi lần ném của các class đó đều bị rút trace.** Tối ưu phụ thuộc bản JVM, compiler, profile thực thi, ngữ cảnh bytecode, flags và trạng thái warm-up. Không phải tất cả exception thuộc các class trên đều được tạo bằng đường bytecode ngầm định; một exception được tạo tường minh bằng `new` không nhất thiết có cùng hành vi.

### Ví dụ một lỗi ngầm định

~~~java
static int divide(int divisor) {
    return 10 / divisor;
}
~~~

Đây là **mã minh họa**. Gọi `divide(0)` ném `ArithmeticException` do phép chia số nguyên cho 0. Nếu HotSpot tối ưu được đường lỗi lặp lại sau quá trình warm-up, một số lần ném sau có thể khác về chi phí và mức độ stack trace so với những lần đầu.

Không nên kết luận JVM có FastThrow chỉ vì một exception nhất định có trace ngắn trong một lần chạy; cũng không nên kết luận JVM không hỗ trợ FastThrow chỉ vì thử một vòng lặp mà vẫn thấy trace đầy đủ. Điều kiện tối ưu và ngưỡng kích hoạt **không phải API Java SE ổn định**.

## 9. Flag HotSpot và giới hạn tính di động

Trong một môi trường HotSpot/OpenJDK hỗ trợ flag này, có thể kiểm tra khác biệt bằng cách chạy cùng chương trình với:

~~~bash
java -XX:-OmitStackTraceInFastThrow YourMainClass
~~~

Đây là **cú pháp lệnh minh họa**. `YourMainClass` là tên lớp main thực tế cần thay thế khi sử dụng; không phải một chương trình standalone của bài. Dấu `-` trước tên flag vô hiệu hóa tùy chọn trong những HotSpot hỗ trợ. Không mặc định flag này tồn tại trên mọi JVM hoặc mọi bản phân phối Java.

Để biết runtime nào đang chạy:

~~~bash
java -version
~~~

Khi điều tra ở máy cụ thể, cần ghi lại ít nhất:

- Nhà cung cấp JVM và phiên bản JDK.
- Tùy chọn khởi động liên quan đến tối ưu và stack trace.
- Cách chạy ứng dụng (JIT thông thường, kiểm thử, cấu hình container/production).
- Exception type, nơi phát sinh và đặc điểm tần suất lặp lại.
- Đầu ra raw từ `getStackTrace()` so với output của logger.
- Thông tin cho biết có dùng exception class tùy biến tắt writable stack trace hoặc code gọi `setStackTrace` hay không.

**Cẩn trọng:** `-XX:-OmitStackTraceInFastThrow` chỉ giải quyết một nguyên nhân liên quan đến tối ưu của HotSpot. Nó không tự làm xuất hiện stack trace cho exception được thiết kế `writableStackTrace=false`, không sửa trace đã bị ứng dụng thay thế, cũng không khôi phục đoạn log đã bị collector cắt.

### Cờ cấu hình độ sâu và các tối ưu khác

Một số JVM còn có tùy chọn liên quan đến số frame tối đa được ghi nhận hoặc cách hiển thị chẩn đoán. Tên, giá trị mặc định và ý nghĩa cụ thể có thể khác theo implementation/phiên bản. Khi cần thay đổi, hãy đối chiếu tài liệu và thông tin flags của **đúng JVM đang chạy**. Đừng sao chép một bộ tham số `-XX` từ hướng dẫn cũ rồi coi đó là quy định chung của Java.

## 10. Ví dụ thăm dò FastThrow: đầu ra không bảo đảm giống nhau

Nếu muốn thăm dò một bản HotSpot cụ thể, có thể dùng chương trình sau. Đây là **một phép thử quan sát**, không phải kiểm thử khẳng định FastThrow chắc chắn phải được kích hoạt.

Lưu tệp **FastThrowProbe.java**:

~~~java
public class FastThrowProbe {

    static int divideBy(int value) {
        return 100 / value;
    }

    public static void main(String[] args) {
        int total = 0;
        int emptyTraces = 0;

        for (int i = 0; i < 200_000; i++) {
            try {
                divideBy(0);
            } catch (ArithmeticException error) {
                total++;
                if (error.getStackTrace().length == 0) {
                    emptyTraces++;
                }
            }
        }

        System.out.println("Caught: " + total);
        System.out.println("Empty traces range valid: "
                + (emptyTraces >= 0 && emptyTraces <= total));
        System.out.println("Observed empty traces: " + emptyTraces);
    }
}
~~~

Chạy với Java 17+:

~~~bash
javac -encoding UTF-8 FastThrowProbe.java
java FastThrowProbe
java -XX:-OmitStackTraceInFastThrow FastThrowProbe
~~~

Hai dòng đầu của stdout luôn có dạng:

~~~text
Caught: 200000
Empty traces range valid: true
~~~

Dòng thứ ba là **số đo thực tế**, không có một giá trị stdout cố định có thể hứa trước:

~~~text
Observed empty traces: <số đo từ 0 đến 200000>
~~~

Dòng trong khối text trên là **mẫu diễn giải định dạng**, không phải dòng stdout chính xác; chương trình sẽ in một số nguyên. Tùy runtime, mức tối ưu, chế độ thực thi và phiên bản JDK, giá trị có thể bằng 0 hoặc lớn hơn 0.

**Không sử dụng số lần lặp 200.000 làm công thức bảo đảm tái hiện.** JIT có thể không tạo đường ném tối ưu trong môi trường cụ thể. `getStackTrace()` cũng làm phép thử có chi phí và có thể tác động tới cấu hình tối ưu/quan sát. Mục tiêu chỉ là tạo một phép thử có thể đo đạc trên máy thực tế.

Nếu command có `-XX:-OmitStackTraceInFastThrow` bị JVM từ chối, điều đó cho thấy cần dùng tài liệu của runtime hiện có, không phải bằng chứng Java SE “bị lỗi”. Khi so sánh, giữ nguyên nguồn mã, cùng kiểu workload và ghi lại tùy chọn runtime.

## 11. NPE message và những khác biệt về chẩn đoán

Java hiện đại có thể cung cấp message chi tiết hơn cho một số `NullPointerException` phát sinh ngầm định. Message này chịu ảnh hưởng của runtime và cấu hình chẩn đoán. Nếu exception được tạo theo một đường nhanh bỏ stack trace, mức thông tin message có thể không giống một trường hợp ném thông thường.

Điểm cần học **không phải** thuộc lòng một chuỗi message NPE:

- Không dựa vào văn bản `NullPointerException.getMessage()` để xác định hợp đồng nghiệp vụ.
- Không giả định mọi NPE đều có message hữu ích hoặc cùng định dạng.
- Một NPE tạo tường minh bằng `new NullPointerException("...")` khác với NPE do JVM phát hiện ở thao tác dereference.
- Trong hệ thống log, cần giữ loại ngoại lệ, ngữ cảnh thao tác và thông tin tương quan; message có thể thay đổi giữa các phiên bản JDK.
- Nếu thấy NPE thiếu trace ở đường nóng, cần xét cả chính sách logging và khả năng tối ưu HotSpot, chứ không chỉ nghi ngờ lỗi tạo wrapper.

Khi cần chẩn đoán code sai, hãy tìm vị trí phát sinh từ trace có thể tin cậy, tái hiện trong cấu hình có khả năng quan sát đầy đủ và kiểm tra input/trạng thái có liên quan. Không sửa code dựa trên giả định “NPE nào cũng thuộc cùng một dòng”.

## 12. Những lý do khác khiến log không đầy đủ

### 12.1. Chỉ log message

~~~java
logger.warning(error.getMessage());
~~~

Đây là **mã minh họa** với biến `logger` và `error` đã tồn tại. Một lời gọi chỉ truyền message sẽ không tự ghi cause chain hay stack trace. Lỗi trong log thiếu thông tin **không chứng minh exception đã mất stack trace**.

Với `java.util.logging.Logger`, khi chính sách dữ liệu cho phép, có thể truyền cả `Throwable`:

~~~java
logger.log(java.util.logging.Level.SEVERE,
        "operation.failed", error);
~~~

Đây cũng là **mã minh họa**. Logger và formatter sẽ quyết định cách hiển thị; phải kiểm tra cấu hình, vì stack trace hoặc message kỹ thuật có thể chứa thông tin nhạy cảm.

### 12.2. Logger hoặc log collector giới hạn kích thước

Nhiều hệ thống log có thể áp giới hạn số ký tự, số dòng, số frame hoặc kích thước bản ghi; một số giao diện chỉ mở phần trace đầu tiên. Nếu output bị cắt ở tầng hiển thị/thu thập, việc đổi flag JIT không giải quyết được. Cần kiểm tra log raw, cài đặt formatter, giới hạn truyền dữ liệu và giao diện quan sát.

### 12.3. Exception được tạo ở nơi khác

~~~java
static final RuntimeException CACHED =
        new RuntimeException("cached");

static void fail() {
    throw CACHED;
}
~~~

Đây là **mã minh họa**. Stack trace của `CACHED` thường phản ánh nơi nó được khởi tạo trong quá trình khởi tạo lớp, chứ không chỉ ra chính xác vị trí mỗi lần `fail()` ném lại đối tượng đó. Đừng tái sử dụng exception có trace để tối ưu mà không hiểu mất khả năng gắn lỗi với từng lần xảy ra.

### 12.4. Ứng dụng tự thay đổi stack trace

~~~java
error.setStackTrace(new StackTraceElement[0]);
~~~

Đây là **mã minh họa** với `error` có sẵn. Nếu exception cho phép sửa trace, lời gọi này thay mảng được công bố thành rỗng. Đây không phải tối ưu JIT mà là tác động có chủ đích của ứng dụng hoặc thư viện.

### 12.5. Tắt writable stack trace

Lớp Throwable tự định nghĩa có thể dùng constructor bốn tham số với `writableStackTrace=false`. Trường hợp này cần sửa thiết kế class hoặc cách tạo exception nếu muốn có frame; không thể chỉ bật flag HotSpot để khôi phục.

### 12.6. Rút gọn cause/suppressed khi in

Dòng `... N more` chỉ lược phần cuối trùng nhau. Nhiều người nhầm việc này với trace rỗng và làm mất thời gian điều chỉnh cấu hình JVM không liên quan.

## 13. Cách chẩn đoán khi thấy stack trace bị thiếu

Áp dụng quy trình từ ít xâm lấn đến nhiều xâm lấn:

1. **Xác định đối tượng đang quan sát.** Đó là exception gốc, wrapper, cause hay một thông báo đã được chuyển đổi?
2. **Kiểm tra định dạng log.** Có `Caused by`, `Suppressed:`, `... N more` hay dấu hiệu bị cắt vì giới hạn dòng không?
3. **Đo số frame thực tế** bằng `error.getStackTrace().length` ở môi trường có thể chẩn đoán, nếu đang nắm được đối tượng Throwable.
4. **Duyệt cause một cách có kiểm soát.** Một wrapper có frame nhưng cause rỗng, hoặc ngược lại, là hai tình huống khác nhau.
5. **Kiểm tra class exception.** Có constructor tắt writable stack trace, override `fillInStackTrace()`, gọi `setStackTrace()` hoặc cache instance không?
6. **Kiểm tra phương thức log.** Đang truyền `Throwable` hay chỉ `getMessage()`? Logger/collector có giới hạn số frame không?
7. **Ghi lại môi trường JVM** bằng `java -version` và tùy chọn chạy. Có thay đổi JDK hoặc mode JIT gần thời điểm phát hiện vấn đề không?
8. **Nếu nghi HotSpot FastThrow,** tái hiện trên môi trường kiểm soát, so sánh với cấu hình hỗ trợ `-XX:-OmitStackTraceInFastThrow`.
9. **Nếu còn nghi truncation ở JVM,** kiểm tra tài liệu của đúng runtime về giới hạn độ sâu stack trace và các cấu hình liên quan.
10. **Đảm bảo bảo mật log:** không đưa raw stack trace của production có dữ liệu nhạy cảm ra nơi công khai chỉ để kiểm thử.

### Mẫu kiểm tra an toàn

~~~java
Throwable cause = error.getCause();
System.out.println("Top-level type: " + error.getClass().getName());
System.out.println("Top-level frames: " + error.getStackTrace().length);
System.out.println("Has cause: " + (cause != null));
if (cause != null) {
    System.out.println("Cause frames: " + cause.getStackTrace().length);
}
~~~

Đây là **mã minh họa**, giả định `error` đã tồn tại. Mục tiêu là phân biệt trace của wrapper và cause; không in message kỹ thuật nhạy cảm vào output công khai.

Một phép kiểm tra `getStackTrace().length == 0` chỉ mô tả trạng thái hiện tại của đối tượng, không tự chứng minh nguyên nhân. Khi không có quyền truy cập Throwable thật và chỉ có log đã format, cần cẩn trọng với mọi kết luận về hành vi của JVM.

## 14. Mối liên hệ giữa hiệu năng và khả năng chẩn đoán

Việc tạo và xử lý exception có thể tốn tài nguyên:

- Phân bổ đối tượng exception.
- Ghi nhận thông tin stack khi implementation cung cấp writable trace.
- Khởi tạo message và tạo các wrapper.
- Materialize/copy frame khi truy `getStackTrace()`.
- Định dạng, ghi và truyền stack trace qua logger/collector.
- Chi phí I/O và lưu trữ của log rất dài hoặc lặp lại.

Mức chi phí phụ thuộc runtime, JIT, độ sâu call stack, tần suất ném, logger và cách thu thập dữ liệu. Không nên khẳng định một con số cố định như “exception luôn chậm gấp 100 lần” khi chưa đo chính workload.

**Điều cần tối ưu đầu tiên** thường là tránh dùng exception để biểu đạt nhánh thành công/dự kiến xảy ra dày đặc. Ví dụ, nếu dữ liệu có thể thiếu theo nghiệp vụ, cân nhắc API trả `Optional`, một result type có cấu trúc, hoặc kiểm tra điều kiện mà không cần ném exception mỗi lần. Không biến mọi lỗi thật thành giá trị thành công giả chỉ để tăng throughput.

### Khi nào có thể cân nhắc exception nhẹ?

- Đường đi **rất nóng** và trạng thái được mô hình hóa rõ ràng như một tín hiệu nội bộ.
- Đã đo đạc bằng benchmark phù hợp và xác định overhead của stack capture là nút thắt.
- Có cơ chế khác để ghi đủ ngữ cảnh khi phát sinh lỗi thật.
- Người bảo trì chấp nhận được giới hạn chẩn đoán và API công bố rõ cách xử lý.

Ngay cả khi dùng exception nhẹ, cần tránh dùng chúng qua ranh giới dịch vụ cho người dùng mà không có thông tin tương quan, mã lỗi và bối cảnh. Các exception thực sự bất thường nên ưu tiên khả năng chẩn đoán.

### Vì sao cần đo trước khi tắt trace?

Nếu một lỗi xảy ra mỗi vài giờ, chi phí tạo stack trace có thể không đáng kể, còn việc mất call stack làm quá trình điều tra tốn rất nhiều thời gian. Ngược lại, ném hàng triệu exception/giây có thể gây áp lực GC và log; nhưng giải pháp tối ưu tốt hơn đôi khi là thay đổi luồng điều khiển, không phải tắt trace.

Khi benchmark exception, cần tránh sai lầm:

- So sánh hai đoạn code không cùng công việc.
- Không warm up JIT rồi coi số đo là steady state.
- In stack trace ra console trong vòng lặp và cho rằng đang đo riêng chi phí tạo exception.
- Không phân biệt exception ngầm định do JVM ném với exception tạo tường minh bằng `new`.
- Chạy một vòng lặp trên một máy rồi suy ra kết quả cho mọi JVM.
- Không xét GC, allocation rate, latency tail và chất lượng log.

Với benchmark nghiêm túc, có thể dùng JMH trong một dự án cấu hình phù hợp; JMH không phải API có sẵn chỉ bằng `javac` của Java SE. Dù đo bằng công cụ nào, phải ghi version runtime, JIT flags, tải và cách thu thập kết quả.

## 15. Logging: giữ thông tin cần thiết nhưng tránh flood

Khi exception lặp dày đặc, việc ghi full stack trace cho từng lần có thể làm hệ thống logging quá tải. Các biện pháp thích hợp có thể gồm:

- Dùng metric đếm số lỗi theo loại và thành phần, thay vì lưu hàng triệu stack trace giống nhau.
- Dùng sampling hoặc rate limiting có chủ đích tại tầng logging/telemetry; giữ trace của mẫu lỗi cần điều tra.
- Ghi correlation ID, operation, exception type và ngữ cảnh an toàn để ghép lỗi với request.
- Giữ cause chain của mẫu lỗi quan trọng; không chỉ log message nếu cần debug nguồn.
- Không phát tán raw stack trace hoặc thông tin hạ tầng tới người dùng hoặc log công khai.

**Sampling do ứng dụng/logger thực hiện khác với FastThrow của JVM.** Ở sampling, Throwable có thể vẫn giữ trace nhưng không được gửi lên collector ở mọi lần. Ở FastThrow, đường exception tối ưu có thể không lưu trace chi tiết. Hai hiện tượng cần được kiểm tra và giải quyết ở hai tầng riêng.

Nếu hệ thống đang mất thông tin chẩn đoán, thay vì bật full stack trace cho mọi request production vô thời hạn, có thể tái hiện trên môi trường kiểm soát hoặc áp dụng một chế độ ghi log được giới hạn về thời gian, lưu lượng và quyền truy cập.

## 16. Stack trace của cause và suppressed cũng cần được xét

Một wrapper có thể giữ cause:

~~~java
try {
    repositoryCall();
} catch (IllegalStateException original) {
    throw new RuntimeException("Operation failed", original);
}
~~~

Đây là **mã minh họa** với `repositoryCall()` được định nghĩa trong ứng dụng. Wrapper và cause là **hai đối tượng** có trace riêng. Nếu wrapper có trace mà cause bị tối ưu thành rỗng, logger có thể in wrapper với đầy đủ frame nhưng cause rất ngắn.

Ngược lại, nếu wrapper là lightweight exception không writable stack trace nhưng giữ cause bình thường, trace của cause vẫn có thể hữu ích. Bởi vậy khi điều tra, **đừng chỉ xem `getStackTrace()` ở exception ngoài cùng**.

Với `try-with-resources`, ngoại lệ khi đóng tài nguyên có thể được lưu trong `getSuppressed()` của lỗi chính. `printStackTrace` có cách hiển thị suppressed exception riêng và cũng có thể rút gọn các frame chung. Một dòng `... N more` dưới `Suppressed:` không đồng nghĩa lỗi đóng tài nguyên đã biến mất.

Đừng dùng việc thêm suppressed exception thủ công chỉ để “bù” cho mọi trace thiếu. Cause và suppressed thể hiện các quan hệ lỗi khác nhau; quan trọng hơn là giữ đúng đối tượng và ngữ nghĩa của chúng.

## 17. fillInStackTrace và việc tái sử dụng Throwable

`Throwable.fillInStackTrace()` có thể làm trace của exception phản ánh **điểm gọi mới** nếu đối tượng cho phép ghi stack trace. Nó không khôi phục các frame gốc đã bị bỏ qua do FastThrow hoặc do log collector cắt.

Ví dụ minh họa:

~~~java
RuntimeException error = new RuntimeException("cached");
error.fillInStackTrace();
throw error;
~~~

Đây là **đoạn mã** trong một phương thức Java. Việc gọi `fillInStackTrace` có thể làm thay đổi dấu vết đang lưu. Không dùng mẹo này để cố khôi phục chính xác “điểm phát sinh thật” của một lỗi đã xảy ra trước đó; nó chỉ ghi lại stack tại vị trí gọi hiện thời theo implementation.

Nếu một đối tượng exception được tái sử dụng giữa nhiều thread, việc đọc/viết trace hoặc context của nó có thể gây nhầm lẫn trong log; bản thân việc dùng một Throwable chung cũng không có nghĩa mỗi lần `throw` sẽ ghi nhận đầy đủ lịch sử riêng của từng lần lỗi.

Nhìn chung, với lỗi thực sự bất thường, hãy tạo exception phù hợp và giữ cause thay vì tái sử dụng một instance chung chỉ vì muốn giảm allocation. Nếu trạng thái có thể dự kiến và xảy ra thường xuyên, một result type phù hợp sẽ rõ nghĩa hơn.

## 18. Kiểm thử stack trace một cách đáng tin cậy

Nên kiểm thử **thuộc tính cần thiết** thay vì chụp nguyên văn stack trace rồi assert từng số dòng.

| Mục tiêu | Cách kiểm tra |
| --- | --- |
| Exception thường có trace | Kiểm tra `getStackTrace().length > 0` trong điều kiện chạy thông thường |
| Cause được giữ | Kiểm tra `wrapper.getCause() == original` |
| Cause còn frame sau khi in | So sánh `getStackTrace().length` trước và sau `printStackTrace` |
| Lightweight exception không có writable trace | Kiểm tra `getStackTrace().length == 0` |
| Thứ tự lỗi trong ứng dụng | Kiểm tra type/code/cause và bối cảnh đã xác định, không phụ thuộc số dòng stack |
| HotSpot FastThrow | Quan sát/benchmark trên runtime đích, **không** đặt assert rằng một lần lặp cụ thể phải không có trace |
| Logger bị cắt | So sánh dữ liệu Throwable raw và output thật của logger/collector |
| Public response | Kiểm tra không chứa stack trace, path, hostname hoặc secret |

Ví dụ với JUnit 5, đoạn sau là **mã minh họa trong lớp test có JUnit 5 và import phù hợp**:

~~~java
RuntimeException original = new RuntimeException("low-level");
RuntimeException wrapper = new RuntimeException("high-level", original);

assertSame(original, wrapper.getCause());
assertTrue(original.getStackTrace().length > 0);
assertTrue(wrapper.getStackTrace().length > 0);
~~~

Không cần assert một số frame cụ thể như 2 hay 3 nếu mục đích chỉ là bảo toàn cause: compiler, test framework và cách gọi có thể thay đổi số frame.

Không đặt unit test bắt buộc “sau 10.000 lần `ArithmeticException` chắc chắn phải có empty stack trace”. Điều đó biến chi tiết tối ưu của một implementation thành điều kiện đúng sai của code nghiệp vụ và khiến test không ổn định khi nâng cấp JDK.

## 19. Lỗi phổ biến và cách sửa

1. **Thấy `... N more` rồi cho rằng JVM đã xóa các frame:** kiểm tra cause và `getStackTrace()`; thường chỉ là rút gọn khi in.
2. **Thấy trace rỗng rồi chắc chắn đổ lỗi cho FastThrow:** còn nhiều nguyên nhân như custom Throwable hoặc thao tác `setStackTrace`.
3. **Cho rằng FastThrow áp dụng cho mọi exception:** cơ chế phụ thuộc bytecode, JIT, runtime và trường hợp cụ thể.
4. **Mong flag HotSpot hoạt động trên mọi JVM:** `-XX` không phải API Java SE có hợp đồng portable.
5. **Dùng một số vòng lặp cố định để test FastThrow:** quá trình tối ưu không có ngưỡng bảo đảm cho chương trình của bạn.
6. **Chỉ log `e.getMessage()`:** không thấy stack trace vì cách log, không phải vì JVM không lưu trace.
7. **Log full trace không giới hạn cho lỗi hàng triệu lần:** có thể tăng I/O, dung lượng lưu và ảnh hưởng latency.
8. **Tắt writable stack trace để sửa vấn đề log quá lớn:** có thể làm mất dữ liệu điều tra lỗi thật.
9. **Tạo một exception rồi ném lại nhiều lần, mong trace tự đổi:** trace có thể giữ vị trí tạo ban đầu.
10. **Gọi `fillInStackTrace()` sau lỗi và coi đó là trace gốc:** thao tác này có thể thay dấu vết thành điểm gọi mới.
11. **Không xem cause/suppressed:** lỗi gốc có thể ở một cấp khác với wrapper.
12. **Tin rằng logger luôn giữ đủ dữ liệu:** định dạng, sampling và collector có thể rút ngắn đầu ra.
13. **Dùng stack trace như một public API ổn định:** tên lớp, số dòng, định dạng và số frame có thể đổi khi tối ưu hoặc đổi phiên bản.
14. **Đưa raw trace cho người dùng cuối:** có thể lộ đường dẫn và thông tin triển khai; nên trả mã lỗi/thông báo an toàn và correlation ID.
15. **Đo exception bằng benchmark thiếu warm-up và kiểm soát môi trường:** kết quả khó dùng để quyết định kiến trúc.
16. **Tự động bỏ qua exception không có trace:** lỗi vẫn có thể nghiêm trọng; phải phân loại theo ngữ nghĩa và tác động thực tế.
17. **Đồng nhất `getStackTrace().length == 0` với `getCause() == null`:** hai thuộc tính độc lập.
18. **Gắn mọi trace thiếu với lỗi JVM:** kiểm tra trước mã nguồn, cấu hình logging, thời điểm tạo exception và điều kiện môi trường.

## 20. Checklist vận hành

Khi gặp log exception có vẻ thiếu stack trace, hãy hỏi:

- Đây là phần in `... N more` do các frame cuối trùng nhau, hay `getStackTrace()` của object thật rỗng?
- Đang xem wrapper, cause hay suppressed exception?
- Logger có nhận `Throwable` hay chỉ được truyền message?
- Trace có bị cắt do formatter, giao diện hoặc giới hạn ingestion không?
- Exception có constructor tắt writable stack trace, override `fillInStackTrace`, bị gọi `setStackTrace` hoặc được cache dùng lại không?
- Có phải lỗi runtime ngầm định xuất hiện dày đặc trên đường bytecode nóng trong HotSpot không?
- Đã ghi lại phiên bản JVM và flags trước khi so sánh chưa?
- Nếu muốn tắt FastThrow để chẩn đoán, đã xác nhận runtime hỗ trợ flag và dùng một phép thử kiểm soát chưa?
- Có đảm bảo log/traces không tiết lộ secret hoặc dữ liệu nhạy cảm không?
- Việc giảm chi phí exception có căn cứ đo lường và không phá khả năng điều tra lỗi quan trọng không?

**Kết luận:** “Stack trace bị lược bỏ” không mô tả duy nhất một hiện tượng. Dòng `... N more` thường chỉ **rút gọn khi in**; một exception tùy biến có thể **chủ động không ghi trace**; còn HotSpot có thể dùng **tối ưu FastThrow** để giảm chi phí của một số lỗi runtime xuất hiện nhiều lần. Hãy xác định đúng lớp nguyên nhân trước khi điều chỉnh JVM hoặc thiết kế exception. Với lỗi hiếm và quan trọng, khả năng chẩn đoán chính xác thường đáng giá hơn một tối ưu vi mô chưa đo đạc.