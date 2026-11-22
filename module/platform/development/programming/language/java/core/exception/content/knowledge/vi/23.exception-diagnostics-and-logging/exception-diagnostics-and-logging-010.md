# Dùng debugger với exception breakpoint cho lỗi đã bắt hoặc chưa bắt

## 1. Vì sao exception breakpoint hữu ích hơn chỉ đọc log?

Trong ứng dụng Java, lỗi có thể xuất hiện ở một phương thức cấp thấp, được **catch** tại tầng trung gian, rồi được chuyển thành kết quả dự phòng hoặc một exception khác. Nếu debugger chỉ dừng khi chương trình kết thúc bất thường, bạn có thể bỏ lỡ lỗi đã được bắt từ sớm. Ngược lại, nếu chỉ đọc thông điệp ở một catch block, bạn có thể chưa biết chính xác trạng thái biến và chuỗi lời gọi tại thời điểm exception đầu tiên phát sinh.

**Exception breakpoint** (điểm dừng theo exception) cho debugger cơ hội tạm dừng khi JVM thông báo một exception phù hợp được **ném** trong quá trình chạy. Sau khi tạm dừng, bạn có thể kiểm tra frame, giá trị biến, thread, stack và điều kiện dẫn đến lỗi. Tùy debugger, breakpoint có thể được cấu hình theo **exception được bắt (caught)**, **exception chưa có handler phù hợp (uncaught)**, hoặc cả hai.

Điểm phân biệt chính:

- **Line breakpoint:** dừng khi luồng thực thi tới một dòng mã nguồn hoặc vị trí bytecode tương ứng, bất kể có lỗi hay không.
- **Exception breakpoint:** dừng khi có sự kiện ném exception thuộc loại được chọn và thỏa điều kiện caught/uncaught mà debugger hỗ trợ.
- **Dừng ở catch block:** dừng khi logic bắt lỗi bắt đầu chạy; đây không nhất thiết là nơi exception đầu tiên được tạo ra.
- **Dừng khi process chết vì exception:** chỉ quan sát một nhóm trường hợp lỗi không được xử lý; không đủ để phân tích những exception đã bị catch, wrap hoặc chuyển thành fallback.

**Mục tiêu học:** dùng exception breakpoint để tìm *đúng nơi ném lỗi*, phân biệt *lỗi đã được bắt* và *lỗi chưa được bắt*, đọc dữ liệu ở thời điểm xảy ra, rồi đi theo đường exception để hiểu tác động nghiệp vụ. Debugger là công cụ chẩn đoán, không tự sửa lỗi hoặc thay thế kiểm thử.

## 2. “Caught” và “uncaught” nghĩa là gì?

**Caught exception** thường chỉ một sự kiện ném exception mà có một handler phù hợp trong đường thực thi Java. Ví dụ:

~~~java
// Mã minh họa; parse(...) được định nghĩa trong cùng class/ngữ cảnh.
try {
    int value = Integer.parseInt("abc");
} catch (NumberFormatException failure) {
    System.out.println("Input is invalid");
}
~~~

**NumberFormatException** được ném bởi quá trình chuyển chuỗi sang số; catch block xử lý nó. Khi chạy bình thường, chương trình có thể tiếp tục và không in stack trace ra stderr. Nhưng nếu bật breakpoint cho **caught NumberFormatException**, debugger có thể dừng **ngay tại sự kiện ném** — trước khi mã catch làm thay đổi trạng thái.

**Uncaught exception** thường chỉ sự kiện exception không có handler phù hợp trong đường xử lý hiện tại của JVM, cuối cùng có thể đi tới uncaught exception handler của thread. Ví dụ:

~~~java
// Mã minh họa bên trong main hoặc phương thức đang gọi.
int port = Integer.parseInt("abc");
// Không có catch phù hợp trong đường gọi.
~~~

Với một ứng dụng console đơn giản, lỗi này thường khiến thread **main** kết thúc và JVM in stack trace lên stderr. Tuy nhiên, việc cả process có kết thúc hay không còn tùy những thread không phải daemon khác, uncaught exception handler và môi trường chạy.

**Cần hiểu giới hạn của nhãn caught/uncaught:** Trình gỡ lỗi và cơ chế JVM debug xác định sự kiện theo khả năng tìm handler tại điểm ném trong stack phù hợp, không phải theo dự đoán nghiệp vụ kiểu “sau đó sẽ có ai log lỗi này hay không”. Một framework, thư viện executor, proxy hoặc mã do compiler sinh có thể bắt exception rồi báo lại qua một kết quả khác. Tùy IDE/debugger, nhãn hiển thị và cách phân loại sự kiện có thể khác nhau ở những ranh giới như vậy.

Đặc biệt, một exception đã bị **catch rồi throw lại** có thể tạo thêm sự kiện ném. Một exception **được bọc thành exception mới** tạo ra ít nhất hai đối tượng lỗi liên quan: original và wrapper. Debugger có thể dừng nhiều lần trong cùng một chuỗi sự cố, và đó không nhất thiết là nhiều bug độc lập.

## 3. Exception breakpoint dừng tại thời điểm nào?

Hình dung một chuỗi gọi:

~~~text
Main.main()
  -> OrderService.create()
     -> Validator.parse()
        -> Integer.parseInt("bad")
           [ném NumberFormatException]
     -> catch(NumberFormatException)
        -> ghi log / trả kết quả lỗi / throw wrapper
~~~

Nếu đặt line breakpoint trong catch, bạn chỉ bắt đầu quan sát khi JVM đã chuyển điều khiển vào catch. Exception breakpoint cho **NumberFormatException** có thể dừng ở nơi **Integer.parseInt** thực sự ném lỗi, với stack chứa các frame dẫn ngược về phương thức **Validator.parse** của ứng dụng. Bạn có thể xem input thực tế là **"bad"**, trạng thái object, điều kiện rẽ nhánh và những frame trước khi catch thay đổi dữ liệu.

Không nên coi vị trí hiển thị của IDE là tuyệt đối giống nhau trên mọi bản JDK. Exception có thể được ném trong mã thư viện, trong native code hoặc lớp proxy; IDE có thể tự chuyển hướng tới frame nguồn hiện có hoặc bỏ qua frame thư viện theo bộ lọc **Just My Code / step filters**. Vì vậy, cần phân biệt **vị trí debugger đưa lên màn hình** với **vị trí sự kiện ném thực tế** trong call stack.

### Exception breakpoint không tương đương “break ở lệnh throw”

Một exception có thể được tạo/ngầm ném bởi JVM hoặc thư viện mà không có lệnh **throw** ngay tại mã ứng dụng của bạn:

- **Integer.parseInt** ném NumberFormatException khi dữ liệu sai.
- Truy cập reference null có thể gây NullPointerException.
- Truy cập mảng sai chỉ số có thể gây ArrayIndexOutOfBoundsException.
- Phép ép kiểu không hợp lệ có thể gây ClassCastException.
- Gọi **Future.get()** có thể ném ExecutionException hoặc CancellationException.

Đặt exception breakpoint đúng loại giúp quan sát các lỗi này kể cả khi mã ứng dụng không chứa câu lệnh **throw new** tương ứng.

## 4. Điều kiện chuẩn bị để debug Java 17+

Một workflow học tập dễ tái hiện:

1. Cài JDK 17 hoặc mới hơn, cấu hình IDE sử dụng đúng JDK với project.
2. Biên dịch bằng chế độ có metadata dòng nguồn phù hợp. **javac** thông thường sinh thông tin line number; build bị tắt debug metadata có thể chỉ hiển thị **Unknown Source**.
3. Chạy bằng chế độ **Debug** thay vì chỉ **Run**, bảo đảm debugger đã attach vào JVM đúng process.
4. Mở cấu hình **Breakpoints** hoặc **Exception Breakpoints** trong IDE.
5. Thêm loại exception muốn quan sát, chẳng hạn **java.lang.NumberFormatException**.
6. Chọn bắt **caught**, **uncaught** hoặc cả hai tùy mục tiêu.
7. Dùng trường hợp lỗi nhỏ, có thể lặp lại, để xác nhận debugger thật sự dừng.
8. Khi dừng, xem **Threads**, **Frames/Call Stack**, **Variables** và **Evaluate Expression** nếu công cụ hỗ trợ.

Tên menu và bố cục trong IntelliJ IDEA, Eclipse, VS Code Java extensions có thể thay đổi theo phiên bản. Hãy tìm những lựa chọn tương ứng với **exception breakpoint**, **caught/uncaught**, **break on thrown exceptions**, **exception type/class filters**. Không giả định mọi IDE đều có cùng tên checkbox hoặc cùng mức hỗ trợ các bộ lọc.

**Lưu ý về quyền quan sát:** Code đang chạy dưới debugger có thể chứa token, password hoặc dữ liệu nhạy cảm trong memory và biến cục bộ. Chỉ debug môi trường và dữ liệu bạn được phép truy cập; cân nhắc hậu quả của **Evaluate Expression** vì gọi một method có side effect có thể làm thay đổi chương trình đang dừng.

## 5. Ví dụ Java 17+ độc lập: năm đường exception

Chương trình sau cố ý tạo năm tình huống để thử breakpoint:

1. **caught:** NumberFormatException được bắt tại cùng luồng.
2. **wrapped:** NumberFormatException được bắt rồi chuyển thành IllegalArgumentException có cause.
3. **suppressed:** lỗi parse là primary; IOException từ **close()** được đính kèm như suppressed.
4. **async:** NumberFormatException xảy ra trong tác vụ CompletableFuture; khi **join()**, caller nhận CompletionException.
5. **uncaught:** NumberFormatException thoát khỏi **main** mà không có catch phù hợp.

Lưu file **ExceptionBreakpointLab.java**:

~~~java
import java.io.IOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class ExceptionBreakpointLab {
    static final class FaultyResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static int parsePort(String text) {
        return Integer.parseInt(text);
    }

    static void caughtCase() {
        try {
            parsePort("not-a-number");
        } catch (NumberFormatException problem) {
            System.out.println("caught: " + problem.getClass().getSimpleName());
        }
    }

    static void wrappedCase() {
        try {
            parsePort("bad-port");
        } catch (NumberFormatException original) {
            throw new IllegalArgumentException("invalid port", original);
        }
    }

    static void suppressedCase() throws IOException {
        try (FaultyResource resource = new FaultyResource()) {
            parsePort("bad");
        } catch (NumberFormatException original) {
            System.out.println("suppressed primary: "
                    + original.getClass().getSimpleName());
            System.out.println("suppressed close: "
                    + original.getSuppressed()[0].getClass().getSimpleName());
        }
    }

    static void asyncCase() {
        CompletableFuture<Integer> stage =
                CompletableFuture.supplyAsync(() -> parsePort("bad-async"));
        try {
            stage.join();
        } catch (CompletionException wrapper) {
            System.out.println("async wrapper: "
                    + wrapper.getClass().getSimpleName());
            System.out.println("async cause: "
                    + wrapper.getCause().getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws IOException {
        String mode = args.length == 0 ? "caught" : args[0];
        switch (mode) {
            case "caught" -> caughtCase();
            case "wrapped" -> {
                try {
                    wrappedCase();
                } catch (IllegalArgumentException wrapper) {
                    System.out.println("wrapped outer: "
                            + wrapper.getClass().getSimpleName());
                    System.out.println("wrapped cause: "
                            + wrapper.getCause().getClass().getSimpleName());
                }
            }
            case "suppressed" -> suppressedCase();
            case "async" -> asyncCase();
            case "uncaught" -> {
                System.out.println("about to throw uncaught");
                System.out.flush();
                parsePort("bad-uncaught");
            }
            default -> System.out.println("unknown mode");
        }
    }
}
~~~

Biên dịch bằng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 ExceptionBreakpointLab.java
~~~

Chạy riêng từng mode:

~~~bash
java ExceptionBreakpointLab caught
java ExceptionBreakpointLab wrapped
java ExceptionBreakpointLab suppressed
java ExceptionBreakpointLab async
java ExceptionBreakpointLab uncaught
~~~

Đầu ra **stdout chính xác** đã kiểm chứng cho bốn mode kết thúc bình thường:

**caught**

~~~text
caught: NumberFormatException
~~~

**wrapped**

~~~text
wrapped outer: IllegalArgumentException
wrapped cause: NumberFormatException
~~~

**suppressed**

~~~text
suppressed primary: NumberFormatException
suppressed close: IOException
~~~

**async**

~~~text
async wrapper: CompletionException
async cause: NumberFormatException
~~~

Với mode **uncaught**, chương trình in một dòng stdout trước khi ném lỗi:

~~~text
about to throw uncaught
~~~

Sau đó JVM thông thường in **stack trace của NumberFormatException ra stderr** và tiến trình Java kết thúc với mã lỗi khác 0. Stack trace stderr chứa tên file/dòng, frame nội bộ JDK và đường gọi **parsePort → main**; số dòng chính xác phụ thuộc bố cục mã nguồn và build. Không dùng một mẫu stack trace có số dòng cố định làm stdout của ví dụ.

**Vì sao suppressedCase khai báo throws IOException?** **FaultyResource.close()** có chữ ký throws IOException. Compiler phải xét khả năng thân try hoàn tất bình thường rồi close ném IOException làm primary. Trong đường chạy đang minh họa, parse ném NumberFormatException trước; close lỗi trở thành suppressed của NumberFormatException và được đọc trong catch tương ứng.

**Vì sao asyncCase bắt CompletionException?** **join()** báo exceptional completion thông thường dưới dạng CompletionException. Cause trong ví dụ là NumberFormatException do supplier tạo. Đây là hai thời điểm/đối tượng cần xem khi debug: lỗi gốc ở luồng chạy supplier và wrapper được quan sát tại consumer.

## 6. Thực hành breakpoint cho exception đã được bắt

Bắt đầu bằng lệnh:

~~~bash
java ExceptionBreakpointLab caught
~~~

Để debugger chạy được từ IDE, cấu hình **program arguments = caught** rồi chọn **Debug**.

Tạo exception breakpoint cho **java.lang.NumberFormatException** và bật tùy chọn **caught** nếu debugger hỗ trợ. Khi tiếp tục chạy:

1. JVM bắt đầu thực thi **caughtCase()**.
2. **parsePort("not-a-number")** gọi **Integer.parseInt**.
3. JDK tạo và ném NumberFormatException.
4. Breakpoint có thể tạm dừng tại sự kiện exception **trước** khi catch trong caughtCase thực thi.
5. Mở call stack để tìm **ExceptionBreakpointLab.parsePort** và **caughtCase**.
6. Chọn frame **parsePort** để xem biến **text = "not-a-number"**.
7. Continue/resume; catch sẽ in **caught: NumberFormatException**.

Nếu breakpoint chỉ bật **uncaught**, tình huống này thường không làm debugger dừng trên NumberFormatException theo tiêu chí uncaught, vì có catch phù hợp xử lý nó. Một số debugger có định nghĩa tùy chọn hoặc cơ chế filtering khác nhau; kiểm tra cấu hình thật và Java debugger đang dùng trước khi kết luận breakpoint lỗi.

**Điều học được:** Một exception bị bắt có thể là hoạt động bình thường của logic (ví dụ parse thử rồi trả lỗi nhập liệu), hoặc dấu hiệu bug đang bị che. Việc debugger tạm dừng ở caught exception không tự chứng minh rằng process đã thất bại. Cần hiểu catch làm gì sau đó.

### Nếu dừng trong frame thư viện

Khi breakpoint tạm dừng tại một phương thức của **java.lang.Integer**, mở **Call Stack** và chọn frame ứng dụng **parsePort**. Tại đây bạn kiểm tra input, dữ liệu truyền từ caller và quyết định gọi parse. Không nhất thiết phải **Step Into** sâu vào thư viện JDK, nhất là khi mã thư viện đã được kiểm thử và vấn đề thực tế nằm ở đối số ứng dụng cung cấp.

## 7. Thực hành breakpoint cho exception chưa được bắt

Chạy mode:

~~~bash
java ExceptionBreakpointLab uncaught
~~~

Bật breakpoint **NumberFormatException** với tiêu chí **uncaught**. Trong mode này, **parsePort("bad-uncaught")** được gọi từ main và không có catch NumberFormatException hoặc superclass phù hợp trong đường gọi ứng dụng này. Theo execution path của chương trình nhỏ, lỗi thoát khỏi main, nên debugger hỗ trợ uncaught exception breakpoints có cơ hội dừng khi exception xuất hiện.

Khi dừng:

1. Ghi nhận **thread hiện tại**: ở đây là main.
2. Xác nhận **exception type** và message chứa giá trị đầu vào không parse được.
3. Tìm **parsePort** trong Call Stack và chọn frame của ứng dụng.
4. Xem biến text và dòng gọi parseInt.
5. Xem frame **main** để hiểu caller đưa chuỗi từ đâu.
6. Resume để quan sát cơ chế uncaught exception handler và stack trace trên stderr.

**Chưa được bắt không đồng nghĩa “không có ai từng catch ở cả hệ thống”.** Một lỗi có thể không được bắt ở thread hiện tại nhưng thread uncaught handler, runtime, framework hoặc process supervisor vẫn thu thập/ghi nhận nó ở một cơ chế khác. Đừng suy ra một exception breakpoint không dừng nghĩa là không có lỗi; cấu hình debugger, attach sai process, class filter, handler của framework hoặc tối ưu runtime có thể ảnh hưởng sự kiện bạn quan sát.

### Nếu ứng dụng tiếp tục chạy sau uncaught exception

Ở chương trình nhiều thread, một worker có uncaught exception có thể kết thúc nhưng các thread khác tiếp tục chạy. Việc thread main kết thúc bất thường cũng không nhất thiết tắt một process còn thread non-daemon. Cần phân biệt **uncaught của thread** với **process termination** và lỗi được framework chuyển thành trạng thái của job.

## 8. Vì sao lỗi wrapped có thể dừng nhiều lần?

Chạy mode **wrapped** và thử hai exception breakpoints: **NumberFormatException** và **IllegalArgumentException**.

Trong **wrappedCase()**:

~~~java
// Đoạn trích từ chương trình đầy đủ.
try {
    parsePort("bad-port");
} catch (NumberFormatException original) {
    throw new IllegalArgumentException("invalid port", original);
}
~~~

Trình tự logic:

1. **Integer.parseInt** ném NumberFormatException.
2. **wrappedCase** bắt NumberFormatException.
3. Catch tạo một **IllegalArgumentException** mới với message **invalid port** và cause là original.
4. Lệnh **throw new ...** ném wrapper.
5. **main** bắt wrapper và in loại outer/cause.

Vì NumberFormatException **kế thừa IllegalArgumentException**, một breakpoint đặt trên **IllegalArgumentException** có thể khớp cả **NumberFormatException** lẫn wrapper, tùy debugger có áp dụng bộ lọc **bao gồm subclass** hay chỉ khớp chính xác class. Đây là lý do phổ biến dẫn đến số lần dừng nhiều hơn dự tính.

Đừng kết luận đã có ba sự cố riêng chỉ vì debugger dừng nhiều lần. Cần xem:

- **Exception object identity** (nếu debugger có thể hiển thị và so sánh).
- **Exception type thực tế** tại mỗi lần dừng.
- **Cause** của wrapper có phải original vừa bắt hay không.
- **Thread** và **stack frame** ở từng sự kiện.
- Việc một đoạn catch **throw lại cùng object** khác với **tạo wrapper object mới**.

Trong ví dụ, outer được bắt ở main nên nếu bật loại break khi **caught**, debugger có thể dừng ở sự kiện wrapper dù chương trình cuối cùng vẫn in kết quả và kết thúc bình thường.

## 9. Debug try-with-resources và lỗi suppressed

Chạy mode **suppressed**. Đặt exception breakpoints cho:

- **NumberFormatException** — lỗi chính từ **parsePort("bad")**.
- **IOException** — lỗi từ **FaultyResource.close()**.

Trình tự:

1. Phần thân try ném NumberFormatException.
2. JVM bắt đầu cleanup resource theo cơ chế try-with-resources.
3. **close()** ném IOException.
4. Cơ chế tự động giữ NumberFormatException là **primary** và gắn IOException vào **primary.getSuppressed()**.
5. Catch NumberFormatException đọc suppressed và in hai dòng kết quả.

Nếu debugger dừng ở IOException từ close, **điều đó không có nghĩa IOException là nguyên nhân gây ra lỗi parse**. Nó là lỗi phụ xảy ra trong khi đang thu hồi tài nguyên. Người điều tra cần đọc cả primary và suppressed, đồng thời hỏi liệu cleanup thất bại có làm tài nguyên hoặc trạng thái hệ thống không đáng tin không.

**Một bẫy trong debugger:** Khi pause ngay tại lệnh **throw new IOException(...)** trong close, bước gắn IOException vào danh sách suppressed của NumberFormatException **chưa chắc đã thực hiện xong**. Muốn xác minh mảng suppressed cuối cùng, hãy tiếp tục đến catch hoặc breakpoint sau điểm cleanup, rồi kiểm tra **original.getSuppressed()**. Trạng thái object tại điểm throw và sau khi cleanup hoàn tất là hai thời điểm khác nhau.

Nếu dùng **finally** thủ công với **close()** có thể ném exception, lỗi cleanup còn có thể che mất primary. Try-with-resources là cách chuẩn của Java để lưu các lỗi phụ mà vẫn giữ nguyên lỗi chính trong trường hợp này.

## 10. Debug exception bên trong CompletableFuture

Chạy mode **async** và đặt exception breakpoint cho NumberFormatException. Supplier:

~~~java
// Đoạn trích từ chương trình đầy đủ.
CompletableFuture<Integer> stage =
        CompletableFuture.supplyAsync(() -> parsePort("bad-async"));
~~~

được thực thi bởi executor mặc định của CompletableFuture trong ví dụ này. **NumberFormatException** ném trong thread thực thi supplier, không phải tại dòng **stage.join()** trên main. CompletableFuture thu thập lỗi để hoàn tất stage một cách bất thường; khi main gọi join, nó nhận **CompletionException** có cause là NumberFormatException.

Để debug hiệu quả:

1. Chạy bằng debugger có hỗ trợ debug thread khác main.
2. Bật break **NumberFormatException** (bao gồm caught nếu cần).
3. Khi dừng, xem **Threads** để xác định thread đang thực thi supplier.
4. Kiểm tra frame ứng dụng **parsePort** và tham số **text = "bad-async"**.
5. Resume rồi có thể quan sát **CompletionException** tại **join()** nếu đặt breakpoint cho loại này.
6. Xem **getCause()** của CompletionException để nối lỗi consumer nhận với lỗi worker tạo.
7. Không dùng mỗi frame **main** ở join để kết luận lỗi nằm trong join; điểm gây lỗi thực sự có thể ở lambda của supplier.

**Chú ý:** Lỗi trong CompletableFuture thường được framework **bắt** và chuyển thành exceptional completion. Vì vậy một exception mà bạn nghĩ “task bị hỏng” có thể được debugger phân loại theo **caught** ở thời điểm ném. Chỉ bật **uncaught** có thể không nhìn thấy lỗi gốc. Hãy chọn cả caught/uncaught khi đang điều tra, rồi thu hẹp sau khi tìm được vị trí.

Một số trình gỡ lỗi hỗ trợ **async stack traces** hoặc hiển thị liên kết giữa các stage; tính năng và độ đầy đủ tùy môi trường. Stack trace tiêu chuẩn của một Throwable không thể bảo đảm tái tạo toàn bộ hành trình request xuyên thread, executor và service. Dùng task ID, request ID hoặc correlation ID nếu cần nối sự kiện bên ngoài call stack của một thread.

## 11. Caught, uncaught và checked/unchecked là hai phân loại khác nhau

Một nhầm lẫn rất phổ biến là cho rằng:

- **Checked exception** đồng nghĩa lỗi sẽ được bắt.
- **Unchecked exception** đồng nghĩa lỗi sẽ không được bắt.

Hai phát biểu đều **sai**.

**Checked/unchecked** là quy tắc **kiểm tra tại compile time**:

- **IOException** là checked: phương thức gọi code có thể ném nó phải bắt hoặc khai báo throws theo luật Java.
- **NumberFormatException** và **IllegalArgumentException** là unchecked: compiler không buộc khai báo/catch.

Trong khi đó, **caught/uncaught** phản ánh **đường xử lý của exception lúc chạy**. Một RuntimeException hoàn toàn có thể được catch. Một checked exception có thể được khai báo throws qua nhiều tầng và cuối cùng không được một handler phù hợp bắt trong thread đang thực thi.

Ví dụ **main(String[] args) throws IOException** trong chương trình chính cho phép close() ném checked IOException đi ra ngoài nếu đường chạy không có catch phù hợp. Điều này không biến IOException thành unchecked; compiler chấp nhận vì chữ ký main đã khai báo loại lỗi.

Chọn exception breakpoint theo **đường cần quan sát**, không theo việc exception có bắt buộc ghi **throws** trong mã nguồn hay không.

## 12. Thêm breakpoint theo exception cụ thể hay Throwable chung?

Cấu hình breakpoint quá rộng có thể khiến debugger dừng liên tục ở hàng nghìn exception mà framework cố ý dùng làm tín hiệu điều khiển. Trong một ứng dụng lớn, nhiều thư viện thử parse, bắt lỗi rồi fallback, kiểm tra classpath, truy cập tài nguyên không tồn tại theo dự kiến hoặc dùng exception để triển khai cơ chế nội bộ.

Có ba chiến lược:

| Chiến lược | Khi nên dùng | Rủi ro |
| --- | --- | --- |
| **Một loại cụ thể** như NumberFormatException | Đã biết lỗi chính qua stack trace/log | Có thể bỏ qua wrapper hoặc loại lỗi khác |
| **Nhóm superclass** như IOException hoặc RuntimeException | Đang khoanh vùng một nhóm có quy luật | Có thể khớp nhiều subclass và gây dừng nhiều |
| **Throwable / All exceptions** | Điều tra ngắn khi chưa biết loại hoặc tìm lỗi bị nuốt | Rất nhiều sự kiện, chậm và khó tập trung |

**Khuyến nghị thực hành:** Bắt đầu từ exception type đã biết trên log hoặc từ hành vi quan sát. Bật caught khi nghi lỗi bị catch/nuốt; bật uncaught khi process hoặc thread kết thúc bất thường. Dùng filter theo package/class/thread/method khi IDE hỗ trợ. Sau khi xác định loại và vị trí, giảm phạm vi breakpoint để tránh nhiễu.

Cần hiểu inheritance khi đặt breakpoint superclass: NumberFormatException extends IllegalArgumentException, IllegalArgumentException extends RuntimeException, RuntimeException extends Exception. Không mặc định tính năng **subclass inclusion** được bật hoặc tắt giống nhau ở mọi debugger; hãy kiểm tra setting.

## 13. Bộ lọc class, package, thread và điều kiện

Một số IDE/debugger cho phép:

- Chỉ dừng khi exception phát sinh trong class hoặc package phù hợp.
- Bỏ qua thư viện JDK hoặc framework theo class filters.
- Chỉ quan sát một thread nhất định, nếu debugger hỗ trợ.
- Tạm ngắt tất cả thread hoặc chỉ thread chứa sự kiện.
- Dùng điều kiện biểu thức nếu có hỗ trợ.
- Chọn chỉ caught, chỉ uncaught, hoặc cả hai.

Các bộ lọc giảm nhiễu nhưng cũng có thể làm biến mất sự kiện cần xem. Ví dụ lỗi thực sự được ném bên trong **Integer.parseInt** thuộc package **java.lang**; nếu lọc chỉ cho dừng ở những exception ném trong package ứng dụng, debugger có thể không dừng dù một frame ứng dụng **parsePort** nằm trong stack.

Không nhầm **throwing class filter** với việc tìm **frame ứng dụng**. Một exception được ném bởi JDK có thể liên quan trực tiếp đến input sai từ ứng dụng.

Khi đặt điều kiện, cũng cần thận trọng:

- Điều kiện đánh giá tại breakpoint có thể chạy nhiều lần.
- Một số biểu thức tham chiếu biến chỉ có sẵn ở frame nhất định.
- Việc evaluate method có thể làm thay đổi trạng thái ứng dụng.
- Điều kiện phức tạp có thể làm debugger chậm và khó tái hiện.
- Nếu breakpoint không dừng, hãy thử bỏ bộ lọc trước khi kết luận exception không xuất hiện.

Một chiến lược gọn là **loại exception cụ thể → caught/uncaught đúng nhu cầu → loại bỏ filter quá chặt → kiểm tra thread/frame → thêm filter dần**.

## 14. Dùng Call Stack để đọc trạng thái ngay trước catch

Khi exception breakpoint kích hoạt, ưu tiên quy trình:

1. Xem **loại Throwable đang ném**, message và các thuộc tính liên quan nếu debugger hiện.
2. Xem **thread** đang dừng.
3. Xác định **frame đầu** trong debugger: có thể là thư viện Java.
4. Chuyển sang **frame đầu thuộc ứng dụng có liên quan**.
5. Đọc biến cục bộ, parameter, field của this và các object liên quan.
6. Đi xuống frame caller để tìm nguồn input và đường đi của dữ liệu.
7. So sánh với **điều kiện hợp lệ theo hợp đồng**, không chỉ đoán từ message.
8. Step/Resume để xem exception được catch ở đâu hoặc thoát ra ngoài.
9. Khi tới catch, kiểm tra logic quyết định retry, fallback, wrap, rollback hoặc logging.
10. Nếu kết quả cuối không khớp kỳ vọng, đặt thêm line breakpoint sau catch để xác minh trạng thái đã thay đổi.

**Step Into, Step Over và Step Out** điều khiển bước thực thi theo frame; chúng không tự động đưa bạn tới frame gốc của cause nếu bạn đang dừng ở wrapper. Hãy dùng cả Call Stack và đối tượng **Throwable.getCause()**.

Tại một breakpoint trong debugger, **stack trace của Throwable** và **call stack đang chạy** không nhất thiết giống hệt: Throwable thường giữ dấu vết lúc nó được tạo/thu nhận, trong khi debugger hiển thị stack của thread tại thời điểm pause. Đặc biệt với catch/rethrow, async và các wrapper mới, hai loại stack có thể khác nhau mà không mâu thuẫn.

## 15. Trường hợp exception được catch rồi nuốt

Một lỗi bị bỏ qua có thể khiến ứng dụng tiếp tục chạy nhưng tạo sai dữ liệu:

~~~java
// Phản mẫu minh họa, không phải chương trình độc lập.
try {
    updateDatabase();
} catch (Exception ignored) {
    // Không log, không trả lỗi và tiếp tục.
}
markOrderCompleted();
~~~

Nếu updateDatabase thất bại, dòng **markOrderCompleted()** vẫn có thể được gọi. Cách điều tra:

1. Nghi ngờ một loại exception theo nghiệp vụ hoặc log của dependency.
2. Bật exception breakpoint **caught** cho loại phù hợp.
3. Chạy lại tình huống lỗi.
4. Khi breakpoint kích hoạt, xác định call stack và thông điệp lỗi.
5. Continue đến catch hoặc đặt line breakpoint trong catch.
6. Kiểm tra phần catch có nuốt lỗi, thay exception, trả fallback hay tiếp tục sai hay không.
7. Sửa hợp đồng lỗi và logic cập nhật trạng thái, không chỉ thêm log nếu dữ liệu vẫn sai.

Với đoạn code trên, biến tên **ignored** không biến exception thành vô hại. Người viết API phải quyết định có được phép bỏ qua lỗi cụ thể nào trong ngữ cảnh đó. Nếu một thao tác là optional và lỗi thuộc tập có thể chấp nhận, cách xử lý nên có thông điệp, metrics hoặc fallback có lý do rõ ràng.

**Exception breakpoint caught** đặc biệt có ích ở đây vì “không thấy exception trên terminal” không có nghĩa exception không từng được ném.

## 16. Khi exception là điều khiển luồng hợp lệ

Không phải exception nào bị catch cũng là bug. Một số thao tác cố ý:

- Thử parse input và báo lỗi validation.
- Tìm optional file rồi fallback sang default có kiểm soát.
- Kiểm tra token/credentials rồi từ chối yêu cầu sai.
- Nhận CancellationException khi Future bị hủy theo yêu cầu.
- Nhận InterruptedException rồi truyền tín hiệu dừng lên tầng sở hữu tác vụ.
- Retry theo chính sách hữu hạn với backoff khi dependency tạm thời thất bại.

Nếu bật breakpoint cho mọi **caught exception**, debugger có thể dừng ở tất cả các tình huống được thiết kế này, gây hiệu ứng “first-chance exception noise”. Đừng sửa mã chỉ vì exception breakpoint đã dừng. Cần so sánh hành vi với hợp đồng, tần suất, bối cảnh và kết quả nghiệp vụ.

Cũng đừng gọi mọi exception caught là “handled successfully”: catch có thể rethrow, wrap, retry rồi thất bại, hoặc swallow sai. Hãy theo dõi từ **throw point** đến **boundary nhận kết quả cuối**.

## 17. Debugger và exception qua reflection, proxy, callback

Trong ứng dụng Java thực tế, lỗi có thể đi qua reflection hoặc proxy:

- **Method.invoke()** có thể bọc exception do method được gọi ném vào **InvocationTargetException**.
- Một proxy/framework có thể chuyển exception thấp thành loại exception riêng.
- Callback được framework gọi có thể bị catch bởi event loop hoặc scheduler.
- **Future.get()** có thể truyền lỗi tác vụ thông qua **ExecutionException**.
- **CompletableFuture.join()** thường truyền exceptional completion bằng **CompletionException**.

Trong những trường hợp này, một exception “nguyên bản” có thể được debugger xem là caught tại framework, dù request nghiệp vụ cuối cùng thất bại. Cần quan sát cả **throw point**, **wrapper creation**, và **boundary trả lỗi**.

Gợi ý cách đặt breakpoint:

1. Bắt đầu từ wrapper trong log, ví dụ CompletionException.
2. Xem **getCause()** để tìm exception gốc.
3. Đặt exception breakpoint cho loại cause, bật caught nếu framework có thể bắt nó.
4. Dùng class/thread filters để thu hẹp sau khi đã thấy điểm ném.
5. Đặt thêm line breakpoint ở nơi framework hoặc service chuyển lỗi nếu cần phân tích quá trình mapping.

Không kết luận **framework đã nuốt exception** chỉ vì nó catch để tạo Future đã hoàn tất bất thường. Cơ chế này có thể chính là hợp đồng báo lỗi của API bất đồng bộ.

## 18. Điều tra exception liên quan interruption và cancellation

Exception breakpoint cho **InterruptedException** có thể dừng ở một API blocking đang bị interrupt. Nhưng cần biết:

- **InterruptedException** biểu diễn thao tác chờ của **thread đó** đã nhận tín hiệu ngắt.
- **CancellationException** biểu diễn một Future/kết quả đã canceled, không nhất thiết đồng nghĩa worker đã ngừng.
- **TimeoutException** từ **Future.get(timeout)** biểu diễn lượt chờ quá hạn, không tự cancel task.
- **ExecutionException** của **Future.get()** có thể chứa cause là lỗi từ **worker**.

Các exception này có thể được catch rất thường xuyên trong executor, thread pool hoặc ứng dụng có timeout. Bật caught exception breakpoint cho **InterruptedException** trên toàn JVM có thể khiến debugger dừng tại các đường shutdown hoàn toàn hợp lệ.

Nên kiểm tra:

1. Thread nào bị interrupt và do ai yêu cầu?
2. Catch có **throw e** lên trên nếu hợp đồng cho phép không?
3. Nếu không thể truyền checked exception, catch có khôi phục **Thread.currentThread().interrupt()** và kết thúc phù hợp không?
4. Công việc đã thay đổi trạng thái trước khi dừng chưa?
5. Một Future canceled có tiếp tục có side effect không?
6. Các lần timeout có làm mã retry vô hạn hoặc tạo duplicate request không?

Debugger giúp nhìn trạng thái tại điểm lỗi, nhưng không tự bảo đảm rollback. Khi đang pause các thread, việc quan sát các race và timeout cũng có thể thay đổi vì **thời gian dừng dưới debugger** không giống thời gian thực thi bình thường.

## 19. Breakpoint làm thay đổi timing của ứng dụng nhiều luồng

Đặt exception breakpoint trong một hệ thống đồng thời có thể thay đổi hành vi bạn đang điều tra:

- Nếu debugger tạm dừng **all threads**, một worker đang giữ lock khiến các thread khác cùng dừng hoặc bị chặn.
- Nếu chỉ dừng **event thread**, các worker khác có thể tiếp tục sửa object và làm trạng thái biến đổi trước khi bạn xem xong.
- Pause có thể khiến các deadline của service bên ngoài hết hạn, vì hệ bên ngoài không bị debugger của bạn làm dừng.
- Một race rất hiếm khi chạy bình thường có thể biến mất hoặc xảy ra thường xuyên hơn khi có breakpoint.
- Method evaluation có side effect có thể gây deadlock nếu gọi hàm cần lock đang được một thread bị suspend giữ.

Do đó:

1. Xác định debugger tạm dừng **thread hiện tại** hay **toàn process**.
2. Ghi lại timestamp, thread name và correlation ID.
3. Không dựa vào một lần chạy dưới debugger như bằng chứng duy nhất của race.
4. Với lỗi timing, kết hợp logging có cấu trúc, metrics, thread dump, unit/concurrency tests.
5. Nếu lỗi biến mất khi debug, đừng vội loại trừ race hoặc visibility issue.

Trong môi trường production, attach debugger và suspend thread có thể ảnh hưởng SLA, request timeout và tính toàn vẹn hệ thống. Chỉ làm khi có quyền, quy trình vận hành và môi trường phù hợp; ưu tiên tái hiện trên staging/test.

## 20. Ghi nhận kết quả sau khi debug

Sau khi tìm được điểm phát sinh, tài liệu hóa ngắn gọn:

- **Loại exception gốc:** ví dụ NumberFormatException.
- **Nơi ném:** ví dụ Integer.parseInt được gọi bởi ExceptionBreakpointLab.parsePort.
- **Đầu vào/tình trạng:** chuỗi không thể chuyển thành số, biến text trong frame.
- **Đường bắt hoặc truyền lỗi:** caught, wrapped, suppressed, async hay uncaught.
- **Cause/suppressed:** lớp wrapper nào nhận lỗi, lỗi cleanup nào phụ.
- **Tác động:** request bị từ chối, task hoàn tất bất thường, dữ liệu có thay đổi hay không.
- **Giải pháp:** validation, hợp đồng API, trạng thái hoặc cơ chế cleanup nào cần sửa.
- **Cách tái hiện/test:** mode, input và assertion cần thiết.

Đừng chỉ chụp một ảnh màn hình debugger rồi bỏ qua thông tin có thể kiểm chứng bằng test. Việc sửa bug cần được chứng minh bằng test đúng trạng thái và loại exception, kể cả đường thành công.

### Tránh log trùng

Không nhất thiết thêm **printStackTrace()** ở mọi tầng. Nếu catch chỉ wrap/rethrow, một lỗi có thể xuất hiện thành nhiều bản log. Thường nên giữ **Throwable cause/suppressed** khi chuyển tầng và ghi log một lần ở ranh giới xử lý có trách nhiệm. Mục tiêu của exception breakpoint là **tìm nguồn**, không phải thêm noise vào production logs.

## 21. Kiểm thử để xác nhận nguyên nhân, không chỉ bắt đúng exception

Một test tốt cho chuỗi caught/wrapped/suppressed cần khẳng định:

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Caught | Đã đi vào catch đúng loại, không có side effect không mong muốn |
| Uncaught | Exception thoát khỏi phạm vi thử nghiệm như dự kiến; với process con có thể kiểm tra exit code và stderr |
| Wrapped | Wrapper giữ cause đúng instance gốc, không chỉ trùng message |
| Suppressed | Primary giữ nguyên, close failure trong getSuppressed đúng thứ tự |
| Async | Consumer nhìn wrapper phù hợp, cause chỉ về lỗi supplier |
| Retry/fallback | Chỉ xử lý loại lỗi được cho phép; không biến lỗi nguy hiểm thành thành công |
| Multi-thread | Thread và trạng thái sau lỗi phù hợp với hợp đồng hủy/đồng bộ |

Một **exception breakpoint không phải unit test**. Nó chỉ cho phép dừng tại một sự kiện trong một lần chạy. Bạn vẫn cần test để xác nhận logic đúng ở nhiều input, thời điểm và môi trường. Với code ở mục 5, có thể dùng các mode chạy độc lập để xác minh loại exception và cause; riêng mode uncaught nên chạy như process con nếu muốn test exit code, tránh làm hỏng chính tiến trình test.

Nếu unit test dùng framework có assertThrows, nên assert loại exception và **getCause()**, **getSuppressed()**, trạng thái trước/sau, không dừng ở việc một exception bất kỳ xuất hiện.

## 22. Những lỗi cấu hình và lỗi sử dụng thường gặp

**Chỉ bật uncaught rồi không tìm thấy lỗi đã catch.** Bật caught exception breakpoint cho loại đúng, nhất là khi nghi lỗi bị framework bắt hoặc chuyển thành fallback.

**Bật Throwable + caught trên toàn JVM quá lâu.** Có thể tạo hàng nghìn lần dừng ở lỗi được xử lý hợp lệ. Thu hẹp type, class, package, thread hoặc condition có chủ đích.

**Tưởng debugger dừng nghĩa là bug chắc chắn.** Một exception được catch có thể là đường xử lý input sai hoàn toàn đúng. Phải kiểm tra hợp đồng nghiệp vụ.

**Nhầm frame đầu JDK với bug JDK.** Đọc frame ứng dụng đã gọi phương thức thư viện và đầu vào đã truyền.

**Quên subclass matching.** Breakpoint trên IllegalArgumentException có thể khớp NumberFormatException nếu cấu hình tính cả lớp con; số lần dừng lớn hơn dự tính.

**Không nhận ra wrapper.** Chỉ dừng tại CompletionException ở join rồi sửa consumer, bỏ qua NumberFormatException trong supplier. Phải xem cause.

**Quên lỗi cleanup.** IOException ở close có thể là suppressed, không phải primary. Xem Throwable tree trước khi kết luận.

**Cho rằng uncaught = cả process chắc chắn chết.** Một worker thread có thể kết thúc trong khi process vẫn chạy; framework có thể bắt và chuyển lỗi thành trạng thái job.

**Không kiểm tra debugger đang attach đúng JVM.** Có thể nhầm bản build, server instance, test fork hoặc process dùng port khác.

**Lấy biến ở frame sai.** Khi đang ở Integer.parseInt, biến local của parsePort có thể chưa hiển thị ở frame hiện tại; chuyển frame ứng dụng.

**Đánh giá biểu thức có side effect.** Method evaluation có thể mutate state, gọi I/O, lock hoặc ném exception mới, làm điều tra sai lệch.

**Cố định số dòng từ stack trace để so với source khác bản.** Xác nhận code và build đang chạy trước khi sửa.

**Để breakpoints nhạy cảm tồn tại trong môi trường cần ổn định.** Xóa/tắt các exception breakpoints quá rộng sau khi debug, giữ cấu hình tối thiểu cho lần tái hiện tiếp theo.

## 23. Checklist áp dụng từng bước

Trước khi kết thúc một phiên debug, hãy kiểm tra:

1. **Đúng JVM?** Debugger đang attach đúng process, classpath và phiên bản mã?
2. **Đúng exception type?** Breakpoint theo loại thực tế, không chỉ theo wrapper ở log?
3. **Caught/uncaught?** Chọn chế độ đúng với đường xử lý đang nghi ngờ?
4. **Inheritance?** Class breakpoint có match subclasses và tạo lần dừng phụ không?
5. **Filters?** Có loại trừ vị trí ném trong thư viện hoặc thread đang cần xem không?
6. **Throw point?** Đã xem frame của nơi Throwable được ném và frame ứng dụng liên quan chưa?
7. **Variables?** Đã ghi nhận đầu vào, trạng thái object và điều kiện dẫn đến lỗi chưa?
8. **Catch path?** Đã theo dõi exception đến catch, wrapper, retry, fallback hoặc uncaught handler chưa?
9. **Cause/suppressed?** Đã phân biệt lỗi chính, lỗi được wrap và lỗi cleanup chưa?
10. **Concurrency?** Đã xác định suspend policy và ảnh hưởng của việc pause tới thread/race/timeout chưa?
11. **Kết quả?** Đã xác minh tác động trạng thái và tạo test tái hiện chưa?
12. **Thu dọn?** Đã tắt breakpoint quá rộng, bảo vệ thông tin nhạy cảm và giữ log/test cần thiết chưa?

**Kết luận:** Exception breakpoint cho **caught exceptions** giúp tìm lỗi đã được bắt hoặc bị framework chuyển đổi mà console không thể hiện trực tiếp. Exception breakpoint cho **uncaught exceptions** giúp xác định đường lỗi không có handler phù hợp trong thread đang chạy. Cả hai đều có ích nhất khi kết hợp với **Call Stack**, biến cục bộ, **cause**, **suppressed** và hiểu biết về thread/async. Hãy dùng debugger để tìm chính xác *nơi exception được ném* và *nó được xử lý ở đâu*, rồi xác nhận nguyên nhân và cách sửa bằng kiểm thử.
