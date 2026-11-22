# Chi phí tạo `Throwable` và thu thập stack trace trong Java

Ngoại lệ giúp Java báo một sự cố kèm ngữ cảnh chẩn đoán. Khi tạo `new IllegalStateException(...)`, chương trình thường không chỉ cấp phát một đối tượng và lưu chuỗi thông điệp: cơ chế khởi tạo `Throwable` còn **ghi lại thông tin về ngăn xếp lời gọi (stack trace)** của luồng hiện tại. Việc này hữu ích khi một lỗi thật sự cần được điều tra, nhưng có thể trở thành chi phí đáng kể nếu ứng dụng tạo hàng nghìn hoặc hàng triệu ngoại lệ cho những tình huống vốn là một phần hoạt động bình thường.

Cần hiểu chính xác **chi phí phát sinh ở bước nào**, **dữ liệu nào được giữ lại**, và **cách tối ưu mà không đánh đổi khả năng tìm lỗi một cách mù quáng**. Không có một con số nanô giây cố định cho việc tạo ngoại lệ trong mọi JVM: thời gian phụ thuộc vào loại ngoại lệ, độ sâu ngăn xếp, cách chương trình chạy, tối ưu hóa của JVM và hoạt động ghi log.

## 1. `Throwable` là gì và vì sao việc tạo nó có thể tốn chi phí?

`Throwable` là lớp gốc của hai nhánh chính `Exception` và `Error`. Một đối tượng lỗi có thể có:

- **Thông điệp** (`getMessage()`): mô tả ngắn, có thể là `null`.
- **Nguyên nhân** (`getCause()`): đối tượng `Throwable` dẫn tới lỗi hiện tại.
- **Stack trace** (`getStackTrace()`): các khung lời gọi liên quan tới thời điểm thông tin stack được ghi nhận.
- **Suppressed exceptions** (`getSuppressed()`): các lỗi bổ sung, thường gặp khi đóng tài nguyên bằng `try-with-resources`.

Trong trường hợp khởi tạo thông thường, constructor của `Throwable` gọi `fillInStackTrace()` để ghi nhận trạng thái của ngăn xếp luồng. JVM phải làm công việc nhất định để lấy thông tin này; công việc thường tăng khi phải duyệt nhiều khung stack. Tạo chuỗi thông điệp, nguyên nhân, các trường riêng của lớp ngoại lệ và hoạt động cấp phát bộ nhớ cũng góp vào tổng chi phí.

Vì thế, một mã như:

```java
IllegalArgumentException error =
        new IllegalArgumentException("quantity must be positive");
```

là **đoạn minh họa trong một phương thức**, và riêng biểu thức `new` có thể đã thu thập thông tin về stack. Chưa cần có lệnh `throw` hay logger mới phát sinh phần công việc ấy.

**Đừng hiểu rằng `new Throwable` luôn buộc JVM lập ngay toàn bộ mảng `StackTraceElement[]` công khai.** Việc ghi nhận nội bộ khi khởi tạo và việc chuyển dữ liệu thành các đối tượng/mảng để `getStackTrace()` trả về là hai khâu cần phân biệt. Chi tiết lưu trữ, tính lười và các tối ưu hóa là vấn đề của triển khai JVM; lập trình viên nên dựa vào hợp đồng API, không đoán cấu trúc nội bộ.

## 2. Tách riêng bốn nhóm chi phí

| Hoạt động | Ví dụ | Chi phí cần quan sát |
| --- | --- | --- |
| Tạo đối tượng ngoại lệ | `new IllegalStateException("failed")` | Cấp phát, khởi tạo trường, ghi nhận stack tại thời điểm tạo theo cấu hình thường |
| Ném và truyền lỗi | `throw error;`, tìm `catch` phù hợp | Chuyển điều khiển, tháo các khung đang hoạt động, chạy `finally`/dọn tài nguyên liên quan |
| Đọc/biến đổi thông tin stack | `error.getStackTrace()`, `fillInStackTrace()` | Lấy mảng các phần tử stack, sao chép/hiện thực hóa biểu diễn, hoặc ghi lại stack tại thời điểm mới |
| Định dạng và ghi log | `printStackTrace()`, `logger.error("...", error)` | Chuyển stack/cause/suppressed thành nội dung hiển thị; đi qua bộ lọc, formatter, hàng đợi, đầu ra hoặc hệ thống tập trung |

Các hoạt động có thể xuất hiện riêng hoặc cùng nhau. Ví dụ **tạo một ngoại lệ rồi không bao giờ ném** vẫn có thể tốn chi phí thu thập stack. Ngược lại, **ném lại chính đối tượng đã tồn tại** không mặc nhiên ghi lại toàn bộ stack mới, dù việc chuyển điều khiển và xử lý nhánh lỗi vẫn có chi phí.

`getMessage()` chỉ lấy thông điệp; nó không thay thế stack trace khi cần tìm lỗi. Nhưng gọi `getStackTrace()` hoặc định dạng nguyên stack trong mọi lần kiểm tra trạng thái cũng có thể tạo nhiều phân bổ và công việc thừa. Nên thu thập/hiển thị chi tiết vào nơi thật sự phục vụ chẩn đoán.

## 3. Stack trace thường được ghi nhận khi tạo, không phải khi bắt

Một hiểu lầm phổ biến là `catch` hoặc `throw` sẽ tự chụp lại stack mới. Với đối tượng ngoại lệ được tạo theo cách thông thường, stack trace được ghi nhận khi khởi tạo, hoặc khi mã chủ động gọi `fillInStackTrace()` để cập nhật nó.

Ví dụ sau có thể chạy bằng Java 17 trở lên.

Tạo tệp **`ThrowableCaptureDemo.java`**:

```java
public class ThrowableCaptureDemo {
    static IllegalArgumentException createFailure() {
        return new IllegalArgumentException("invalid input");
    }

    static void throwExisting(IllegalArgumentException error) {
        throw error;
    }

    public static void main(String[] args) {
        IllegalArgumentException failure = createFailure();
        System.out.println("createdAt="
                + failure.getStackTrace()[0].getMethodName());

        try {
            throwExisting(failure);
        } catch (IllegalArgumentException caught) {
            System.out.println("sameObject=" + (caught == failure));
            System.out.println("topAfterThrow="
                    + caught.getStackTrace()[0].getMethodName());
        }

        StackTraceElement[] first = failure.getStackTrace();
        StackTraceElement[] second = failure.getStackTrace();
        System.out.println("returnedArraysDistinct=" + (first != second));

        failure.fillInStackTrace();
        System.out.println("topAfterRefresh="
                + failure.getStackTrace()[0].getMethodName());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ThrowableCaptureDemo.java
java ThrowableCaptureDemo
```

Đầu ra:

```text
createdAt=createFailure
sameObject=true
topAfterThrow=createFailure
returnedArraysDistinct=true
topAfterRefresh=main
```

Giải thích:

1. `createFailure()` là nơi đối tượng được tạo, nên phần tử stack đầu tiên mô tả phương thức đó.
2. `throwExisting()` ném lại **chính đối tượng** đã có; `sameObject=true`. Thông tin stack đầu tiên vẫn là `createFailure`, vì Java không tự điền stack mới mỗi khi cùng đối tượng được ném lại.
3. Hai lời gọi `getStackTrace()` trả về những mảng riêng để mã nhận có thể làm việc với mảng mà không trực tiếp thay đổi phần lưu trữ stack nội bộ của ngoại lệ. **Việc gọi nhiều lần không miễn phí** trong triển khai thông thường.
4. `fillInStackTrace()` được gọi từ `main`, nên vị trí đứng đầu của stack sau đó là `main`: phương thức này **cập nhật** thông tin stack gắn với đối tượng. Đây là hành vi chủ động, không phải điều xảy ra khi ném lại mặc định.

Chương trình này kiểm tra **ngữ nghĩa**, không đo thời gian chạy. Việc gọi `getStackTrace()[0]` giả định một ngoại lệ có stack được phép ghi và có khung gọi như ví dụ trên. Nếu stack bị vô hiệu hóa, bị rút gọn hoặc ngoại lệ đặc biệt không có các khung, mảng có thể rỗng; không nên truy cập `[0]` trong mã xử lý lỗi tổng quát nếu chưa kiểm tra độ dài.

## 4. Độ sâu ngăn xếp và số lượng ngoại lệ ảnh hưởng thế nào?

Hãy tưởng tượng hai tuyến gọi:

```text
main -> parse                -> new IllegalArgumentException(...)
main -> service -> workflow -> repository -> parser -> new IllegalArgumentException(...)
```

Ở trường hợp thứ hai, đường đi có nhiều khung hơn. Việc tạo stack trace có thể cần duyệt/ghi nhận nhiều thông tin hơn. Tuy vậy, kết quả đo không nhất thiết tăng tuyến tính hoàn hảo theo số khung, bởi JVM có thể tối ưu, giới hạn độ sâu hoặc dùng biểu diễn nội bộ khác nhau.

Trong một luồng xử lý bình thường, vài ngoại lệ thực sự xảy ra thường không phải vấn đề. Rủi ro xuất hiện khi hệ thống biến **luồng điều khiển thông thường** thành việc liên tục tạo ngoại lệ:

```java
try {
    return Integer.parseInt(raw);
} catch (NumberFormatException error) {
    return DEFAULT_VALUE;
}
```

Đây là đoạn minh họa trong một phương thức có biến `raw` và hằng `DEFAULT_VALUE`. Nếu đầu vào không hợp lệ là tình huống phổ biến trong một đường xử lý tần suất cao, nhiều `NumberFormatException` sẽ được tạo. Cần cân nhắc một API kiểm tra/parse trả kết quả có cấu trúc, nếu hợp đồng nghiệp vụ coi thất bại parse là nhánh thông thường. Tuy nhiên, **đừng tự xây parser mới chỉ để tránh exception** khi điều đó làm mất tính đúng đắn hoặc khiến mã khó bảo trì; hãy đo tải thật trước.

Một số ngoại lệ như lỗi truy cập mạng, ghi dữ liệu hay vi phạm bất biến là tình huống bất thường đúng nghĩa. Với chúng, giữ stack trace thường có giá trị chẩn đoán lớn hơn khoản tiết kiệm nhỏ khi bỏ nó.

## 5. Gọi `getStackTrace()` và `printStackTrace()` thêm chi phí gì?

`Throwable.getStackTrace()` trả một **mảng `StackTraceElement[]`** chứa các vị trí lời gọi. Mã dùng API có thể đọc, lọc, sắp xếp thông tin này. Việc tạo/copy mảng và hiện thực hóa các phần tử stack trong triển khai JVM có thể tạo cấp phát bổ sung; lập trình viên không nên giả định rằng đọc stack bằng API này là thao tác đơn giản như đọc một trường `boolean`.

Ví dụ:

```java
for (StackTraceElement frame : error.getStackTrace()) {
    if (frame.getClassName().startsWith("com.example.")) {
        System.out.println(frame);
    }
}
```

Đây là đoạn minh họa bên trong phương thức đã có `Throwable error`, không phải chương trình hoàn chỉnh. Nếu đặt đoạn mã vào một vòng xử lý lỗi lặp lại, việc liên tục biến toàn bộ stack thành mảng để chọn một vài khung có thể phát sinh chi phí không cần thiết.

`printStackTrace()` còn phải dựng bản trình bày dễ đọc gồm tên ngoại lệ, thông điệp, các khung stack và thông tin `Caused by:`/`Suppressed:`. Việc in ra console, file, socket hoặc bộ thu thập log có thể tốn thời gian và gây tranh chấp tài nguyên hơn cả thao tác tạo ngoại lệ — tùy nền tảng và cấu hình.

Nếu chỉ cần vị trí gọi hiện tại và **không muốn tạo một ngoại lệ chỉ để lấy stack**, Java 9+ cung cấp `StackWalker`:

```java
String caller = StackWalker.getInstance().walk(stream ->
        stream.findFirst()
                .map(frame -> frame.getClassName()
                        + "#" + frame.getMethodName())
                .orElse("unknown"));
```

Đoạn này minh họa bên trong một phương thức. `StackWalker` cho phép duyệt khung stack của luồng hiện tại theo nhu cầu, nhưng bản thân thao tác đi qua stack **vẫn có chi phí** và không thay thế `Throwable` khi cần lưu nguyên nhân của lỗi đã xảy ra. Khi cần stack của **ngoại lệ được tạo trước đó**, không thể chỉ đi qua stack hiện tại để tái dựng chính xác ngăn xếp của thời điểm lỗi.

## 6. Giảm chi phí bằng ngoại lệ tùy biến không ghi stack

Java có một constructor `protected` của `Throwable` và những lớp con như `RuntimeException`:

```java
RuntimeException(
        String message,
        Throwable cause,
        boolean enableSuppression,
        boolean writableStackTrace);
```

Chữ ký trên là **mô tả API**, không phải lời gọi constructor hợp lệ từ mã bên ngoài `RuntimeException`. Một lớp ngoại lệ tùy biến có thể gọi `super(message, cause, enableSuppression, writableStackTrace)` để quyết định có ghi nhận stack và có cho phép suppressed exceptions hay không.

Tạo tệp **`StackTraceOptionsDemo.java`**:

```java
public class StackTraceOptionsDemo {
    static final class NormalFailure extends RuntimeException {
        NormalFailure(String message) {
            super(message);
        }
    }

    static final class LightweightSignal extends RuntimeException {
        LightweightSignal(String message) {
            super(message, null, false, false);
        }
    }

    public static void main(String[] args) {
        RuntimeException normal = new NormalFailure("expected");
        RuntimeException lightweight = new LightweightSignal("expected");

        normal.addSuppressed(new IllegalStateException("cleanup"));
        lightweight.addSuppressed(new IllegalStateException("cleanup"));

        System.out.println("normalHasStack="
                + (normal.getStackTrace().length > 0));
        System.out.println("lightweightStackLength="
                + lightweight.getStackTrace().length);
        System.out.println("normalSuppressed="
                + normal.getSuppressed().length);
        System.out.println("lightweightSuppressed="
                + lightweight.getSuppressed().length);

        lightweight.fillInStackTrace();
        System.out.println("lightweightAfterFill="
                + lightweight.getStackTrace().length);
        System.out.println("lightweightMessage="
                + lightweight.getMessage());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 StackTraceOptionsDemo.java
java StackTraceOptionsDemo
```

Đầu ra:

```text
normalHasStack=true
lightweightStackLength=0
normalSuppressed=1
lightweightSuppressed=0
lightweightAfterFill=0
lightweightMessage=expected
```

Lớp `LightweightSignal` đã tắt **cả** khả năng ghi stack và suppression bằng hai đối số `false`. Vì vậy, `getStackTrace()` trả mảng rỗng, `fillInStackTrace()` không ghi stack, và `addSuppressed(...)` không lưu ngoại lệ kèm theo. Thông điệp `"expected"` vẫn có.

Hai cờ này **độc lập về ý nghĩa**: nếu chỉ muốn tắt stack trace nhưng vẫn giữ suppressed exceptions, constructor có thể dùng `super(message, cause, true, false)`. Ví dụ trên cố tình tắt cả hai để cho thấy quyết định giảm dữ liệu chẩn đoán cần được cân nhắc rõ.

**Đánh đổi quan trọng:** một đối tượng không có stack trace sẽ khó điều tra nơi được tạo. Đừng dùng `writableStackTrace=false` rộng khắp cho ngoại lệ bất ngờ, lỗi lập trình, hỏng dữ liệu hoặc lỗi cần phân tích sau sự cố. Chỉ cân nhắc cho một **tín hiệu được định nghĩa rõ, xảy ra thường xuyên và có thể chẩn đoán bằng thông tin khác**. Khi dùng lớp này, phải ghi nhận lý do và bảo đảm người bảo trì không nhầm nó với lỗi nghiêm trọng.

## 7. Có nên ghi đè `fillInStackTrace()` để trả về `this`?

Một kỹ thuật từng được dùng là ghi đè:

```java
@Override
public synchronized Throwable fillInStackTrace() {
    return this;
}
```

Đây là đoạn **minh họa một phương thức override trong lớp con của `Throwable`**, không phải chương trình độc lập. Trong các trường hợp phù hợp, nó ngăn bước ghi stack do `fillInStackTrace()` thực hiện. Tuy nhiên, kết quả phụ thuộc vào cách lớp được khởi tạo, hợp đồng kế thừa và nhu cầu chẩn đoán. Java đã có constructor cho phép tắt `writableStackTrace`; ưu tiên cách diễn đạt trực tiếp bằng constructor khi lớp ngoại lệ của bạn hỗ trợ.

Đặc biệt, không ghi đè chỉ để “tăng tốc” mọi ngoại lệ trước khi chứng minh đây là đường nóng. Việc thiếu vị trí lỗi có thể làm thời gian điều tra sự cố tăng mạnh. Cũng không nên dùng một **singleton `Throwable`** rồi ném lại từ nhiều luồng chỉ để tiết kiệm cấp phát: stack gắn với nơi tạo ban đầu dễ gây hiểu lầm, một số trạng thái ngoại lệ có thể thay đổi, và đối tượng dùng chung làm mất ngữ cảnh riêng của từng lần xảy ra lỗi.

## 8. `throw` không mặc nhiên chụp lại stack, nhưng xử lý ngoại lệ vẫn tốn công

Một câu lệnh `throw` của đối tượng đã tồn tại thường không thực hiện hành động giống `new Throwable()` lần nữa. Nó chuyển luồng điều khiển đến bộ xử lý thích hợp, có thể phải rời nhiều khung, chạy `finally`, giải phóng tài nguyên trong `try-with-resources` và thực thi những nhánh xử lý lỗi.

Vì vậy hãy tránh hai kết luận quá mức:

- “Nếu chỉ `throw` lại thì hoàn toàn miễn phí.” **Sai**: vẫn có chi phí chuyển điều khiển, chạy code xử lý và các tác dụng phụ liên quan.
- “Mọi `try/catch` đều chậm ngay cả khi không có lỗi.” **Không nên khẳng định như vậy**. Chi phí chính thường nằm ở đường ném và xử lý ngoại lệ, không phải sự tồn tại của cú pháp `try` quanh một luồng thành công. JVM có thể tối ưu các đường bình thường rất tốt; hãy đo thay vì loại bỏ cấu trúc xử lý lỗi cần thiết.

Hành vi còn phụ thuộc vào loại lỗi: có các ngoại lệ do JVM tạo tự động (chẳng hạn một số lỗi thao tác bytecode) và các đối tượng ngoại lệ do mã ứng dụng `new`. HotSpot có những tối ưu hóa đặc biệt cho một số lỗi JVM phát sinh lặp lại tại cùng vị trí, trong vài điều kiện có thể bỏ thông tin stack. Đây là **chi tiết triển khai, không phải cam kết chung của ngôn ngữ Java**; không nên dựa vào nó để thiết kế logging hoặc dự đoán stack trace sẽ luôn có/không có. Nếu cần kiểm tra, phải xem đúng phiên bản JVM và cấu hình hiện hành.

## 9. Đo hiệu năng đúng cách thay vì gán một con số cố định

Một microbenchmark kém thiết kế rất dễ dẫn đến nhận định sai rằng `Throwable` “tốn đúng X ns” hay “tắt stack luôn nhanh hơn Y lần”. Phép đo chịu ảnh hưởng bởi:

- **Warm-up/JIT**: các lời gọi đầu tiên khác những lần sau khi mã đã được biên dịch tối ưu.
- **Dead-code elimination / escape analysis**: kết quả không được sử dụng có thể bị tối ưu hóa, khiến bạn tưởng đang đo việc tạo đối tượng nhưng thật ra không đo điều đó.
- **Độ sâu stack**: tạo ngoại lệ ở độ sâu 2, 20, 100 có thể cho kết quả khác nhau.
- **Lớp ngoại lệ**: constructor và trường dữ liệu riêng có thể thay đổi khối lượng công việc.
- **Có gọi `getStackTrace()` không**: chỉ tạo `Throwable` khác việc lấy mảng stack.
- **Có định dạng/log ra thiết bị thật không**: chi phí formatter, đồng bộ, buffer, I/O, chính sách drop/sampling có thể lấn át thao tác còn lại.
- **Môi trường JVM**: bản JDK, GC, CPU, cờ VM, công việc khác trên máy và profile tải.

Với nghiên cứu nghiêm túc, dùng **JMH (Java Microbenchmark Harness)** hoặc công cụ profiler có phương pháp rõ ràng, báo cả các phân vị/độ phân tán khi phù hợp và lượng cấp phát (ví dụ byte/op) nếu công cụ hỗ trợ. Không dùng một vòng lặp `System.nanoTime()` quá ngắn rồi kết luận kết quả mang tính phổ quát.

Có thể chia thí nghiệm thành các nhánh độc lập:

| Phép thử | Mục tiêu | Điều cần kiểm soát |
| --- | --- | --- |
| `new NormalFailure(...)` | Chi phí tạo ngoại lệ có stack | Giữ cùng độ sâu gọi, tiêu thụ đối tượng |
| `new LightweightSignal(...)` | Chi phí tạo ngoại lệ không có stack | Cùng loại công việc và dữ liệu, nêu rõ đã hy sinh stack |
| `failure.getStackTrace()` | Chi phí đọc mảng stack | Tách khỏi thời gian tạo đối tượng |
| `failure.printStackTrace(writer)` | Chi phí tạo biểu diễn văn bản | Dùng writer phù hợp, loại trừ/báo riêng I/O |
| Ghi logger có Throwable | Chi phí toàn tuyến logging | Cấu hình backend, mức log, sink và sampling rõ ràng |

Nếu cần dùng JMH, benchmark tối thiểu thường tổ chức như sau (đây là **phác thảo**, cần thêm JMH dependency/import, state và cấu hình, không phải lớp chạy độc lập):

```java
@Benchmark
public void constructThrowable(org.openjdk.jmh.infra.Blackhole sink) {
    sink.consume(new IllegalStateException("expected"));
}

@Benchmark
public void materializeStack(org.openjdk.jmh.infra.Blackhole sink) {
    sink.consume(existingThrowable.getStackTrace());
}
```

Ở nhánh thứ hai, `existingThrowable` phải là state được tạo ở ngoài phép đo để đo việc đọc stack thay vì vô tình đo cả khởi tạo. Cần thiết kế state hợp lý với số luồng và tránh chia sẻ trạng thái mutable không có kiểm soát. JMH là thư viện ngoài JDK, không tự có chỉ vì dùng Java 17.

Trong ứng dụng thật, kết hợp microbenchmark với profiler và metrics: tỷ lệ exception trên mỗi request, chi phí CPU của `Throwable.fillInStackTrace`, tổng byte cấp phát, tần suất GC, thời gian xử lý request và lượng log. Một tối ưu làm microbenchmark nhanh hơn chưa chắc cải thiện độ trễ hệ thống nếu chi phí thực nằm ở I/O hoặc khóa.

## 10. Kỹ thuật giảm overhead mà vẫn giữ chẩn đoán

**(1) Đừng dùng exception để thay thế nhánh kết quả dự kiến.** Ví dụ kiểm tra điều kiện nghiệp vụ bình thường và trả kết quả có cấu trúc (`Optional`, enum trạng thái, kiểu kết quả riêng) thay vì ném ngoại lệ cho mỗi lần tra cứu không tìm thấy, nếu quy ước API coi “không tìm thấy” là kết quả thường. Với sai lệch bất ngờ, exception vẫn là cơ chế phù hợp.

**(2) Không tạo exception chỉ để lấy tên caller khi đã có API thích hợp.** Nếu mục tiêu là stack hiện tại hoặc một caller cụ thể, xem `StackWalker` hoặc cơ chế metadata/trace của framework. Việc đi qua stack vẫn có giá; đo và chỉ làm ở nơi cần thiết.

**(3) Giữ đối tượng `Throwable` khi log lỗi quan trọng.** Với SLF4J, một lời gọi minh họa trong ứng dụng có logger là:

```java
logger.error("Failed to process order {}", orderId, exception);
```

Đoạn này yêu cầu SLF4J, `logger`, `orderId`, `exception`. Nó mang cả exception cho backend để có thể ghi stack/cause; gọi `exception.getMessage()` rồi bỏ `exception` sẽ mất dữ liệu chẩn đoán. Nếu log volume cao, kiểm soát mức log, rate limit, sampling hoặc gom nhóm tại ranh giới xử lý. Đừng tắt stack trace của lỗi nghiêm trọng chỉ để giảm số byte log.

**(4) Chọn đúng điểm log.** Một lỗi qua repository → service → API có thể bị log ba lần; thường nên log một lần ở nơi có đầy đủ ngữ cảnh và trách nhiệm xử lý, rồi truyền trạng thái lỗi qua các tầng khác. Nếu một tầng xử lý được lỗi và trả fallback, log ở đó có thể hữu ích hơn.

**(5) Đừng bắt rồi ném lại ngoại lệ mới mà mất cause.** Nếu cần bọc lỗi, dùng constructor lưu nguyên nhân, ví dụ `new IllegalStateException("Could not save order", cause)`. Nếu mỗi tầng lại `new ...` một cách vô ích, chương trình vừa thêm chi phí tạo stack mới, vừa làm chuỗi nguyên nhân khó đọc.

**(6) Hạn chế truy xuất stack nhiều lần.** Nếu cần đọc stack để phân loại một lỗi cụ thể, đọc một lần vào biến rồi xử lý khi cần; tránh gọi `getStackTrace()` nhiều lần trong vòng lặp tìm một phần tử. Đừng lấy stack đầy đủ chỉ để quyết định mức log nếu có tín hiệu nghiệp vụ chính xác hơn.

**(7) Chỉ chọn ngoại lệ không có stack sau khi đánh giá ngữ nghĩa.** Một `LightweightSignal` có thể hợp lý cho cơ chế hủy/điều khiển nội bộ có hợp đồng riêng. Nhưng nếu caller bên ngoài có thể coi nó là lỗi cần điều tra, mất stack có thể gây tổn thất lớn.

**(8) Theo dõi việc ghi log bất đồng bộ.** Backend logging có thể hoãn định dạng hoặc đẩy sự kiện vào hàng đợi, giảm thời gian chặn luồng gọi trong một số cấu hình; việc đó không xóa chi phí tạo ngoại lệ, không loại bỏ tổng công việc formatter/I/O và có thể tạo áp lực bộ nhớ hoặc mất sự kiện theo chính sách hàng đợi. Phải đo toàn hệ thống.

## 11. Chi phí và tính đầy đủ của stack trace trong thực tế

Có những trường hợp không nên tin rằng mọi `Throwable` đều có stack trace chi tiết:

1. **Tắt writable stack trace**: constructor bốn tham số với `writableStackTrace=false` cho phép không điền stack; `getStackTrace()` trả mảng rỗng.
2. **Code chủ động thay đổi stack**: `fillInStackTrace()` ghi lại tại vị trí hiện tại, `setStackTrace(...)` có thể thay đổi cách stack được trả về cho đối tượng có stack ghi được. Không nên sửa stack để làm đẹp log nếu không có lý do kỹ thuật rõ ràng.
3. **Giới hạn/đặc điểm JVM**: stack có thể bị giới hạn, rút gọn hoặc vắng mặt trong các trường hợp đặc biệt do VM; một số tối ưu cho ngoại lệ do JVM tạo không nhất thiết áp dụng với ngoại lệ người dùng `new`.
4. **Lỗi nghiêm trọng**: khi JVM thiếu bộ nhớ hoặc stack quá sâu, hệ thống có thể không còn tài nguyên để tạo và in log như bình thường. Không thể coi stack trace đầy đủ là bảo đảm tuyệt đối trong mọi tình huống.
5. **Ranh giới tác vụ bất đồng bộ**: stack của exception ở worker thể hiện ngữ cảnh worker; khi `CompletableFuture.join()` hoặc `Future.get()` báo lỗi cho thread khác, lớp bọc và cause có thể mang những stack khác nhau. Cần giữ cause và mã tương quan để nối các ngữ cảnh.

Khi phân tích performance, số khung trong một trace không phải luôn bằng toàn bộ lịch sử nghiệp vụ của request. Stack mô tả trạng thái của **một luồng ở thời điểm ghi stack**, chứ không tự ghép được đường đi của một request qua nhiều thread hay message queue. Distributed tracing và correlation ID bổ sung thông tin đó, nhưng chúng cũng có chi phí riêng.

## 12. Sai lầm phổ biến

| Sai lầm | Vì sao chưa đúng | Cách hiểu/thực hành tốt |
| --- | --- | --- |
| “`throw` mới là lúc Java tạo stack trace.” | Khởi tạo `Throwable` thường đã ghi stack | Phân biệt tạo ngoại lệ với ném một đối tượng có sẵn |
| “`catch` luôn thêm nơi bắt vào stack.” | Bắt lỗi không tự điền lại stack | Dùng cause và trace sẵn có, chỉ gọi `fillInStackTrace()` nếu chủ đích muốn cập nhật |
| “`getMessage()` là đủ, rẻ hơn nên luôn chỉ log nó.” | Mất loại lỗi, stack, cause và suppressed | Với lỗi cần chẩn đoán, chuyển cả `Throwable` cho logger |
| “`new Exception()` và `new Object()` có cùng chi phí.” | Exception thường có bước ghi nhận stack và dữ liệu phụ | Đo chi phí tạo `Throwable` riêng |
| “Gọi `getStackTrace()` không cấp phát gì thêm.” | API trả mảng và có thể cần chuyển biểu diễn nội bộ | Tránh lặp lại vô ích; đo JVM đang dùng |
| “Tắt stack trace cho mọi lỗi là tối ưu chắc chắn.” | Mất vị trí phát sinh lỗi và giảm giá trị chẩn đoán | Chỉ cân nhắc cho tín hiệu dự kiến có hợp đồng riêng |
| “`Throwable` không stack thì không thể có message/cause.” | Cờ writable stack và các dữ liệu khác có ý nghĩa khác nhau | Kiểm tra constructor và dữ liệu được giữ |
| “Một microbenchmark ngắn là đủ định lượng chi phí production.” | JIT, GC, độ sâu stack, tải I/O, logger đều có thể làm kết quả khác | Kết hợp JMH, profiler và số liệu production |
| “Tái sử dụng một ngoại lệ singleton luôn an toàn.” | Ngữ cảnh mỗi lần ném khác nhau và đối tượng có trạng thái | Tránh chia sẻ lỗi mutable khi cần truy vết từng lần |
| “Thao tác log chỉ tốn tiền nếu mức ERROR bật.” | Đối tượng Throwable có thể đã được tạo từ trước dù log bị lọc | Tránh tạo ngoại lệ chỉ để phục vụ thông điệp log không cần thiết |

## 13. Tình huống tự kiểm tra

**Tình huống A.** Một hàm tạo `IllegalStateException` tại phương thức `create()`, rồi hàm khác ném lại đối tượng đó. Khung đầu của stack mặc định thường chỉ nơi nào?  
**Trả lời:** Nơi ngoại lệ được tạo/được điền stack gần nhất (`create()`), không nhất thiết là lời gọi `throw` sau này.

**Tình huống B.** Bạn gọi `error.fillInStackTrace()` ở một điểm mới. Điều gì thay đổi?  
**Trả lời:** Với throwable có thể ghi stack, thông tin stack được cập nhật theo trạng thái luồng tại điểm gọi. Làm vậy có thể làm mất dấu vết vị trí tạo gốc nếu không giữ ngữ cảnh trước đó.

**Tình huống C.** Dùng `super(message, null, true, false)` trong constructor ngoại lệ tùy biến. `getStackTrace()` và suppression ra sao?  
**Trả lời:** Stack bị vô hiệu hóa; `getStackTrace()` rỗng. Suppression vẫn được cho phép bởi tham số `true`, nên có thể thêm suppressed exceptions.

**Tình huống D.** Một endpoint trả nhiều lỗi nhập liệu dự kiến mỗi giây. Có nên thay tất cả bằng ngoại lệ không có stack?  
**Trả lời:** Cần đánh giá trước xem lỗi nhập liệu là kết quả thông thường của API và có thể trả kiểu kết quả/trạng thái phù hợp hay không. Nếu phải giữ exception, chỉ tắt stack sau khi đo và chắc chắn không cần thông tin đó cho chẩn đoán.

**Tình huống E.** Mỗi lần lỗi, chương trình gọi `getStackTrace()` trong một vòng lặp để tìm phương thức đầu tiên của ứng dụng. Điều gì đáng xem lại?  
**Trả lời:** Cách đọc nhiều lần có thể phát sinh công việc/cấp phát lặp lại. Có thể lấy mảng một lần rồi duyệt, hoặc dùng API khác phù hợp với mục tiêu.

**Tình huống F.** `logger.error("Bad: {}", new RuntimeException("x"))` nằm trong đường code chỉ nhằm ghi debug cho mỗi request. Dù logger tắt mức này, việc tạo `RuntimeException` có miễn phí không?  
**Trả lời:** Không thể coi là miễn phí: biểu thức tạo exception được đánh giá trước khi gọi logger, trừ khi toàn bộ nhánh được tránh hoặc có tối ưu hóa cụ thể. Không nên tạo throwable chỉ để trang trí thông điệp log thường xuyên.

**Tình huống G.** Tối ưu trong JMH cho thấy bỏ stack giảm phân bổ, nhưng khi production lỗi thì khó điều tra hơn. Quyết định nào đúng?  
**Trả lời:** So sánh lợi ích thực trên workload với mức mất thông tin chẩn đoán. Giữ trace của lỗi bất ngờ; tối ưu bằng thay đổi luồng điều khiển, giới hạn log hoặc chỉ dùng ngoại lệ nhẹ cho tín hiệu thực sự có thể chẩn đoán mà không cần stack.

## 14. Tài liệu tham khảo

- [Java 17 `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `fillInStackTrace`, `getStackTrace`, `printStackTrace`, `getSuppressed` và constructor với `writableStackTrace`.
- [Java 17 `RuntimeException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html): constructor `protected` dùng trong lớp ngoại lệ tùy biến.
- [Java 17 `StackWalker`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackWalker.html): đọc các khung ngăn xếp của luồng hiện tại theo nhu cầu.
- [JMH — Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/): bộ công cụ đo microbenchmark JVM với warm-up và khả năng kiểm soát tối ưu hóa.

Điều cần nhớ: **tạo `Throwable` thường tốn thêm công việc ghi stack; `getStackTrace()` và xuất log có thể cộng thêm chi phí; ném lại cùng đối tượng không tự chụp stack mới.** Hãy giữ dấu vết cho lỗi cần điều tra, đo theo môi trường thực và chỉ giảm hoặc bỏ stack trace trong những trường hợp có hợp đồng rõ ràng.