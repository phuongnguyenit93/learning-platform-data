# Đọc stack trace từ loại lỗi và điểm phát sinh trong Java

## 1. Stack trace trả lời những câu hỏi nào?

Khi một ứng dụng Java gặp exception, thông báo “xảy ra lỗi” thường chưa đủ để sửa được nguyên nhân. Stack trace (dấu vết ngăn xếp lời gọi) cho biết **đối tượng lỗi nào được báo**, **những phương thức nào xuất hiện trong dấu vết của lỗi**, **vị trí mã nguồn tương ứng** và, nếu có, **chuỗi nguyên nhân (cause)** hoặc **lỗi phụ (suppressed exceptions)**.

Trong phạm vi chẩn đoán Java Core, đọc stack trace là quá trình nối bốn loại thông tin:

1. **Loại exception**: NullPointerException, IllegalArgumentException, IOException, SQLException, CompletionException, ...
2. **Thông báo lỗi (message)**: đầu vào, điều kiện bất biến hoặc thao tác cụ thể bị thất bại, nếu exception có message.
3. **Các frame**: class, method, file, số dòng và thứ tự lời gọi ghi nhận trong stack trace.
4. **Cây lỗi**: exception ngoài cùng, các nguyên nhân **Caused by**, và những lỗi cleanup **Suppressed**.

Một lỗi có thể được phát hiện ở thư viện JDK nhưng được kích hoạt bởi dữ liệu sai hoặc logic sai trong mã ứng dụng. Vì vậy, không nên chỉ đọc dòng đầu tiên rồi kết luận “JDK bị lỗi”. Ngược lại, cũng không nên chỉ tìm một dòng có tên package dự án rồi bỏ qua thông tin ở các frame thư viện.

**Mục tiêu:** Từ stack trace, xác định *điểm có bằng chứng lỗi xuất hiện*, *đường gọi dẫn đến điểm đó*, và *nguyên nhân gốc phù hợp nhất để điều tra*. Đây là cách ưu tiên giả thuyết sửa lỗi, **không phải bằng chứng tuyệt đối rằng một dòng mã duy nhất là lỗi thiết kế**.

## 2. Cấu trúc chung của một Java stack trace

Một đoạn stack trace điển hình có hình thức:

~~~text
java.lang.IllegalArgumentException: invalid input
    at com.example.app.ProfileService.parse(ProfileService.java:42)
    at com.example.app.ProfileService.load(ProfileService.java:28)
    at com.example.app.Main.main(Main.java:11)
Caused by: java.lang.NumberFormatException: For input string: "abc"
    at java.base/java.lang.NumberFormatException.forInputString(NumberFormatException.java:...)
    at java.base/java.lang.Integer.parseInt(Integer.java:...)
    at com.example.app.ProfileService.parse(ProfileService.java:40)
    ... 2 more
~~~

Đây là **stack trace minh họa**, không phải đầu ra chính xác của chương trình ở mục 6. Tên package, số dòng, prefix module và số frame được rút gọn để làm rõ cấu trúc; dấu **...** trong ví dụ không mang nghĩa số dòng cố định.

Có thể chia thành các phần:

| Phần nhìn thấy | Ý nghĩa chính |
| --- | --- |
| **java.lang.IllegalArgumentException: invalid input** | Kiểu exception đang được in và message của nó |
| **at com.example...parse(ProfileService.java:42)** | Một frame: class/method và thông tin vị trí nguồn |
| Các dòng **at** tiếp theo | Những lời gọi ở cấp trên trong stack được chụp khi Throwable thu nhận trace |
| **Caused by: ...** | Throwable khác được khai báo là nguyên nhân của Throwable đang in |
| **Suppressed: ...** | Throwable phụ được lưu trên một Throwable, thường từ cleanup |
| **... N more** | Một số frame cuối trùng với trace bao ngoài được lược in, không có nghĩa phần đó bị mất trong đối tượng Throwable |

Một stack trace chuẩn của **Throwable.printStackTrace()** có thể hiển thị thêm các lớp lồng, phần bị lược, hoặc cấu trúc riêng của logger. Dù định dạng và mức chi tiết thay đổi theo môi trường, ý tưởng đọc **loại lỗi → frame → cause → suppressed** vẫn hữu ích.

## 3. Bắt đầu bằng loại exception và thông điệp

Dòng đầu tiên thường có dạng:

~~~text
package.ExceptionType: message
~~~

Ví dụ:

~~~text
java.lang.NumberFormatException: For input string: "abc"
java.lang.NullPointerException: Cannot invoke ... because ... is null
java.io.FileNotFoundException: config.txt (The system cannot find the file specified)
java.lang.IllegalStateException: order is already closed
~~~

Đây là **những dạng thông báo minh họa**; chính tả, nội dung chi tiết và mức giải thích của JVM/JDK có thể khác nhau.

**Loại exception** cho biết cơ chế nhận diện lỗi:

- **NumberFormatException**: một chuỗi được chuyển thành giá trị số theo cú pháp không hợp lệ.
- **NullPointerException**: mã cố thao tác trên reference null trong một tình huống mà Java không cho phép.
- **IndexOutOfBoundsException**: truy cập vị trí không hợp lệ trong cấu trúc có chỉ số.
- **ClassCastException**: phép ép kiểu reference không tương thích.
- **IllegalArgumentException**: API từ chối một đối số vì vi phạm hợp đồng.
- **IllegalStateException**: thao tác không được phép với trạng thái hiện thời của đối tượng.
- **IOException**: lỗi ở tầng thao tác nhập/xuất.
- **CompletionException** hoặc **ExecutionException**: có thể là wrapper cho một lỗi nằm ở **cause**.

**Message** bổ sung ngữ cảnh, không phải danh tính của lỗi. Message có thể bằng **null**, có thể do lập trình viên viết, và có thể khác giữa các phiên bản JDK. Không nên xây logic nghiệp vụ dựa trên so sánh nguyên văn message của JDK.

Ví dụ nếu nhận **NumberFormatException: For input string: "abc"**, việc cần điều tra không chỉ là nơi Java ném NumberFormatException, mà còn là nơi ứng dụng cung cấp chuỗi **"abc"**, cách kiểm tra dữ liệu và quy tắc cho phép những định dạng nào.

## 4. Đọc từng stack frame để tìm đường gọi

Một frame thường được hiển thị như:

~~~text
at package.ClassName.methodName(FileName.java:lineNumber)
~~~

Các thành phần:

- **package.ClassName**: class chứa phương thức theo thông tin stack.
- **methodName**: phương thức đang nằm trên call stack khi trace được ghi nhận.
- **FileName.java**: tên file nguồn nếu metadata tương ứng khả dụng.
- **lineNumber**: dòng nguồn nếu JDK và class file có thông tin dòng phù hợp.

Thông thường, **frame đầu tiên** của một Throwable phản ánh vị trí gần nhất với nơi trace của Throwable được chụp (thường lúc nó được tạo ra). Các frame phía dưới phản ánh những caller tại thời điểm đó. Có thể đọc theo chiều từ **trên xuống dưới** để biết đường lỗi được ghi nhận:

~~~text
at app.Parser.parse(Parser.java:18)        <- nơi lỗi được ghi nhận gần nhất trong ứng dụng
at app.Repository.load(Repository.java:35) <- hàm gọi Parser.parse
at app.Service.handle(Service.java:64)    <- hàm gọi Repository.load
at app.Main.main(Main.java:10)            <- entry point
~~~

Đây là **chuỗi minh họa**. Thứ tự frame là thông tin rất quan trọng: một frame nằm phía dưới thường gọi vào frame phía trên, không phải ngược lại.

**Cẩn thận:** Trong một stack trace có wrapper, frame đầu của **wrapper** và frame đầu của **cause** có thể là hai vị trí khác nhau. Frame đầu của wrapper chỉ ra nơi mã tạo/ghi nhận wrapper; nó chưa chắc là nơi lỗi nghiệp vụ ban đầu xảy ra. Vì vậy phải xem cả **Caused by** trước khi chốt vị trí điều tra.

Ngoài ra, stack trace cho thấy đường thực thi đã được thu thập, nhưng không bảo đảm mọi bước của ứng dụng đều nằm trong một trace duy nhất. Bất đồng bộ, callback, remote calls và thread boundaries có thể tách một luồng nghiệp vụ thành nhiều trace khác nhau.

## 5. “Điểm phát sinh” không phải lúc nào cũng là dòng đầu tiên

Khi Java tự tạo exception trong thư viện, các frame đầu có thể thuộc **java.base**, **java.util** hoặc một framework. Ví dụ với **Integer.parseInt("abc")**, những frame trên cùng có thể là phương thức nội bộ của NumberFormatException/Integer, trong khi frame đầu tiên thuộc ứng dụng là nơi gọi parseInt.

Điều tra đúng thường gồm hai câu hỏi tách biệt:

1. **Throwable này ghi nhận lỗi ở đâu?** Xem những frame đầu của chính Throwable.
2. **Ứng dụng đã đưa điều kiện nào dẫn đến lỗi ấy?** Xem frame ứng dụng có liên quan và dữ liệu truyền vào.

Ví dụ một lỗi **IndexOutOfBoundsException** ném bởi **ArrayList.get** không có nghĩa bản thân ArrayList hỏng. Caller có thể đã tính chỉ số sai. Tương tự, **NullPointerException** ở một thao tác JDK có thể được kích hoạt bởi input null do ứng dụng truyền vào.

Một frame đầu tiên thuộc package dự án cũng không tự động là bug. Có thể nó chỉ là nơi **throw new IllegalArgumentException(...)** để báo một input từ client không hợp lệ theo thiết kế. Cần đối chiếu hợp đồng API, request, dữ liệu thực tế, thao tác trước đó và log cùng correlation ID.

**Quy tắc thực hành:** Đọc nguyên nhân sâu hơn trước, tìm frame ứng dụng liên quan đến nguyên nhân đó, rồi đi ngược đường gọi để tìm nguồn dữ liệu hoặc quyết định nghiệp vụ gây ra tình trạng lỗi.

## 6. Ví dụ Java 17+: loại lỗi, vị trí ứng dụng, cause và suppressed

Ví dụ hoàn chỉnh sau tạo một đường gọi:

**main → service → repository → parseAge → Integer.parseInt**.

Chuỗi đầu vào không thể chuyển thành int. Một tài nguyên trong **try-with-resources** cũng ném IOException khi đóng, nên Java giữ lỗi parse là primary và gắn lỗi close thành suppressed. **service** chủ động bọc lỗi parse bằng một IllegalArgumentException mang thông điệp nghiệp vụ.

Ví dụ tự duyệt **StackTraceElement** để in các trường quan trọng theo cách ổn định, tránh phụ thuộc số dòng nội bộ của thư viện giữa các bản JDK.

Lưu thành file **StackTraceReadingDemo.java**:

~~~java
import java.io.IOException;

public class StackTraceReadingDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static int parseAge(String value) {
        return Integer.parseInt(value);
    }

    static int repository(String value) {
        return parseAge(value);
    }

    static void service(String value) throws IOException {
        try (FailingResource resource = new FailingResource()) {
            repository(value);
        } catch (NumberFormatException original) {
            throw new IllegalArgumentException("invalid age input", original);
        }
    }

    static StackTraceElement firstApplicationFrame(Throwable error) {
        for (StackTraceElement frame : error.getStackTrace()) {
            if (frame.getClassName().equals(StackTraceReadingDemo.class.getName())) {
                return frame;
            }
        }
        throw new IllegalStateException("No application frame");
    }

    static String applicationChain(Throwable error) {
        StringBuilder result = new StringBuilder();
        for (StackTraceElement frame : error.getStackTrace()) {
            if (frame.getClassName().equals(StackTraceReadingDemo.class.getName())) {
                if (result.length() != 0) {
                    result.append(" -> ");
                }
                result.append(frame.getMethodName());
            }
        }
        return result.toString();
    }

    public static void main(String[] args) throws IOException {
        try {
            service("not-a-number");
        } catch (IllegalArgumentException wrapper) {
            Throwable cause = wrapper.getCause();
            StackTraceElement origin = firstApplicationFrame(cause);
            System.out.println("outer type=" + wrapper.getClass().getSimpleName());
            System.out.println("outer message=" + wrapper.getMessage());
            System.out.println("outer application frame="
                    + firstApplicationFrame(wrapper).getMethodName());
            System.out.println("cause type=" + cause.getClass().getSimpleName());
            System.out.println("cause first application frame=" + origin.getMethodName());
            System.out.println("cause application chain=" + applicationChain(cause));
            System.out.println("cause file=" + origin.getFileName());
            System.out.println("cause line available=" + (origin.getLineNumber() > 0));
            System.out.println("cause suppressed count=" + cause.getSuppressed().length);
            System.out.println("suppressed type="
                    + cause.getSuppressed()[0].getClass().getSimpleName());
            System.out.println("suppressed message=" + cause.getSuppressed()[0].getMessage());
        }
    }
}
~~~

Biên dịch bằng JDK 17+ và chạy:

~~~bash
javac --release 17 StackTraceReadingDemo.java
java StackTraceReadingDemo
~~~

Stdout đã được kiểm chứng bằng biên dịch và chạy:

~~~text
outer type=IllegalArgumentException
outer message=invalid age input
outer application frame=service
cause type=NumberFormatException
cause first application frame=parseAge
cause application chain=parseAge -> repository -> service -> main
cause file=StackTraceReadingDemo.java
cause line available=true
cause suppressed count=1
suppressed type=IOException
suppressed message=close failed
~~~

Chương trình này biên dịch với cấu hình mặc định của **javac --release 17**, nên metadata dòng nguồn có sẵn. Nếu build dùng cấu hình bỏ debug line information, số dòng có thể không khả dụng; kết quả **cause line available** khi đó có thể khác. Ví dụ không in số dòng cụ thể vì số dòng phụ thuộc bố cục file nguồn.

### Đọc output theo từng lớp

- **outer type = IllegalArgumentException:** exception ứng dụng công bố ra bên ngoài được tạo tại **service**.
- **outer message = invalid age input:** service cung cấp ngữ cảnh nghiệp vụ, không thay thế kiểu lỗi thấp.
- **outer application frame = service:** stack trace của wrapper được ghi nhận khi tạo wrapper trong service.
- **cause type = NumberFormatException:** lỗi parse thực sự vẫn tồn tại và truy cập qua **getCause()**.
- **cause first application frame = parseAge:** dù một số frame nội bộ JDK đứng trên, **parseAge** là frame đầu tiên thuộc class ứng dụng ở cause.
- **cause application chain = parseAge → repository → service → main:** các phương thức gọi nhau tại thời điểm NumberFormatException được tạo.
- **cause suppressed count = 1:** close của FailingResource ném IOException trong lúc thân try đã thất bại. Try-with-resources giữ nó như một lỗi phụ **trên NumberFormatException**, không phải tự động chuyển nó sang danh sách suppressed của IllegalArgumentException wrapper.
- **suppressed message = close failed:** có thêm thông tin cleanup thất bại; chỉ đọc outer message sẽ bỏ lỡ chi tiết quan trọng này.

Trong ví dụ, **service() throws IOException** vì FailingResource.close() có khai báo checked IOException và một đường thực thi khác có thể khiến lỗi đóng là primary. Việc parse lỗi ở lần chạy này làm NumberFormatException trở thành primary và lỗi đóng thành suppressed, nên catch(NumberFormatException) xử lý và wrap nó. Không nên xóa khai báo IOException một cách tùy ý chỉ vì đường chạy thử không ném nó trực tiếp.

## 7. Đọc Caused by để không sửa nhầm wrapper

Khi một tầng thêm ngữ cảnh bằng exception mới:

~~~java
// Mã minh họa bên trong một catch hợp lệ.
catch (java.io.IOException original) {
    throw new IllegalStateException("Cannot initialize configuration", original);
}
~~~

Throwable mới là một **wrapper**, còn **original** được đặt trong **cause**. Trong log, lỗi wrapper thường xuất hiện ở dòng đầu tiên và có stack frames trỏ tới nơi thực hiện **throw new**. Dưới phần **Caused by** là Throwable thấp hơn và các frame tương ứng.

Ví dụ khái niệm:

~~~text
java.lang.IllegalStateException: Cannot initialize configuration
    at app.ConfigurationService.start(ConfigurationService.java:58)
Caused by: java.io.FileNotFoundException: config.properties
    at app.ConfigReader.read(ConfigReader.java:21)
    at app.ConfigurationService.start(ConfigurationService.java:54)
    ... 1 more
~~~

Đây là ví dụ mô phỏng, không phải stdout từ code phần 6.

Cách đọc hợp lý:

1. Ghi nhận **mục đích mà wrapper muốn diễn đạt**: không thể khởi tạo cấu hình.
2. Theo **Caused by** đến FileNotFoundException.
3. Tìm frame ứng dụng trong cause: ConfigReader.read.
4. Kiểm tra path cấu hình, thư mục làm việc, quyền truy cập, cách lấy đường dẫn và cấu hình môi trường.
5. Từ **ConfigurationService.start** xác định ai yêu cầu load cấu hình và ứng dụng nên phản ứng thế nào.

Không phải lúc nào cause sâu nhất cũng là nguyên nhân nghiệp vụ đủ để sửa lỗi. Một **ConnectException** sâu nhất cho biết không kết nối được, nhưng vấn đề thực sự có thể là endpoint sai, DNS, credential hoặc dịch vụ chưa sẵn sàng. Stack trace là bằng chứng về *đường lỗi*, không thay thế quan sát hệ thống bên ngoài.

### getCause() và các tầng lồng

**Throwable.getCause()** có thể trả về null. Nhiều framework có thể wrap lỗi qua nhiều tầng; phải duyệt có kiểm soát:

~~~java
// Mã minh họa trong một phương thức nhận Throwable.
Throwable current = failure;
while (current.getCause() != null) {
    current = current.getCause();
}
// current là cause sâu nhất theo chuỗi getCause() này.
~~~

Không viết cố định **failure.getCause().getCause()** khi chưa kiểm tra null. Hơn nữa, chọn duy nhất cause cuối có thể làm mất thông tin ngữ cảnh của các wrapper phía trên. Trong báo cáo chẩn đoán, tốt hơn giữ cả **cây lỗi** rồi tập trung vào tầng phù hợp cho hành động sửa.

## 8. Đọc Suppressed để nhận ra lỗi cleanup không che lỗi gốc

**Suppressed exception** là Throwable phụ gắn vào một Throwable khác bằng **addSuppressed()**. Try-with-resources sử dụng cơ chế này khi thân try đang ném exception và lệnh close của tài nguyên cũng ném lỗi.

Ví dụ dạng log:

~~~text
java.lang.NumberFormatException: For input string: "not-a-number"
    at java.base/java.lang.Integer.parseInt(Integer.java:...)
    at app.StackTraceReadingDemo.parseAge(StackTraceReadingDemo.java:...)
    Suppressed: java.io.IOException: close failed
        at app.StackTraceReadingDemo$FailingResource.close(StackTraceReadingDemo.java:...)
        ... 3 more
~~~

Đây là cấu trúc minh họa, có rút gọn số dòng và frame. **Suppressed** không có nghĩa lỗi close gây ra NumberFormatException. Quan hệ là: khi exception chính đã xảy ra, một lỗi thứ hai cũng xuất hiện lúc dọn dẹp. Nếu đảo quan hệ nhân quả, ta có thể sửa nhầm close thay vì dữ liệu parse.

Với chương trình ở mục 6, wrapper IllegalArgumentException có **cause là NumberFormatException**; chính NumberFormatException mới mang **suppressed IOException**. Do đó, khi log chỉ hiển thị exception wrapper hoặc khi helper chỉ hỏi **wrapper.getSuppressed()**, lỗi close có thể không xuất hiện. Cần duyệt cause và suppressed đúng vị trí.

Phân biệt nhanh:

| Quan hệ | API | Câu hỏi cần hỏi |
| --- | --- | --- |
| **Cause** | **getCause()** | Lỗi nào dẫn đến exception này theo cách mã đã wrap? |
| **Suppressed** | **getSuppressed()** | Khi xử lý/đóng tài nguyên có lỗi phụ nào được giữ lại? |
| **Stack frame** | **getStackTrace()** | Tại thời điểm trace được ghi nhận, những phương thức nào đang trên call stack? |

Nếu **close()** thất bại khi thân try **không lỗi**, lỗi close có thể là exception chính được ném ra. Không mặc định rằng mọi IOException từ close chỉ là lỗi phụ.

## 9. Ý nghĩa của dòng ... N more

Khi Throwable.printStackTrace in một exception có cause hoặc suppressed, nó có thể rút gọn những frame cuối **giống nhau** giữa trace hiện tại và trace của exception bao quanh. Khi thấy:

~~~text
Caused by: java.io.IOException: read failed
    at app.Reader.read(Reader.java:17)
    ... 3 more
~~~

Điều đó không có nghĩa Java mất ba frame vì exception bị “cắt ngắn” ngẫu nhiên. **... 3 more** thường biểu thị ba frame cuối trùng với các frame của trace đang bao ngoài và không cần in lại.

Khi đọc:

1. Xem frame riêng của cause nằm ngay trên **... N more**.
2. Đối chiếu những frame tương ứng ở trace bên ngoài để khôi phục đường caller chung.
3. Tập trung frame riêng có giá trị chẩn đoán: thường là điểm exception sâu hơn phát sinh.
4. Đừng nhầm số **N** với số exception, số retry, số lần lỗi xuất hiện hoặc số dòng mã bị bỏ qua.

Nếu sử dụng **getStackTrace()** trên object Throwable trong chương trình, bạn nhận một mảng **StackTraceElement** của chính Throwable; dấu **... N more** là **cách in rút gọn**, không phải phần tử đặc biệt nằm trong mảng.

## 10. Wrapper, throw e, throw new và thời điểm thu thập trace

Một vấn đề dễ hiểu nhầm là stack trace không nhất thiết phản ánh nơi một Throwable **được ném gần đây nhất**. **Throwable** thường thu nhận stack trace khi nó được khởi tạo (hoặc khi **fillInStackTrace()** được gọi theo thiết kế của class).

Ví dụ:

~~~java
// Mã minh họa, bên trong một phương thức có khai báo phù hợp.
try {
    riskyOperation();
} catch (IllegalArgumentException original) {
    throw original; // Giữ cùng đối tượng Throwable.
}
~~~

Thông thường **throw original** không tạo một đối tượng lỗi mới và không tự thay toàn bộ stack trace bằng địa điểm rethrow. Khi điều tra, điều này giúp giữ lại nơi exception ban đầu được ghi nhận.

Ngược lại:

~~~java
// Mã minh họa.
try {
    riskyOperation();
} catch (IllegalArgumentException original) {
    throw new IllegalStateException("Processing failed", original);
}
~~~

**new IllegalStateException(...)** tạo wrapper với stack trace riêng tại chỗ tạo; lỗi cũ tồn tại qua **getCause()**. Nếu chỉ xem phần trace ngoài cùng, bạn có thể thấy dòng tại chỗ wrap mà không thấy điểm lỗi thấp hơn.

Mã như sau làm mất dấu gốc:

~~~java
// Phản mẫu minh họa.
catch (IllegalArgumentException original) {
    throw new IllegalStateException(original.getMessage());
}
~~~

Lỗi mới không giữ original làm cause. Dù message giống nhau, stack trace gốc và các suppressed exceptions nằm trên original đã bị tách khỏi wrapper; hệ thống logging chỉ nhận wrapper khó truy vết nguyên nhân.

Cũng cần tránh **tái sử dụng một instance exception** cho các lần thất bại ở thời điểm khác nhau: trace của instance cũ có thể không phản ánh lần gọi mới. Các API như **setStackTrace()**, **fillInStackTrace()**, **Throwable** tùy biến vô hiệu hóa writable stack trace, hoặc một số tối ưu JVM đều có thể làm dấu vết khác cấu trúc thông thường.

**Kết luận:** Frame đầu ghi nhận nơi trace của **Throwable cụ thể** được xây dựng/thu thập, không phải chứng cứ phổ quát rằng mọi lần throw của cùng object đều diễn ra đúng tại dòng đó.

## 11. Các frame thư viện và frame ứng dụng

Một stack trace có thể chứa những frame thuộc nhiều lớp hệ thống:

- **java.base/java.lang...**, **java.base/java.util...**: phương thức của JDK.
- **org.springframework...**, **org.hibernate...**, **com.fasterxml...** hoặc package framework khác: những tầng framework/library.
- **com.example...**: mã ứng dụng của bạn.
- Những tên chứa **lambda$...**, **$$Lambda**, proxy hoặc reflection: các cách JVM/framework triển khai callback và gọi động.

Đọc stack trace không nên chỉ lọc mọi frame thư viện rồi bỏ đi. Ví dụ:

- **Integer.parseInt** giúp biết lỗi là chuyển chuỗi sang số.
- **Objects.requireNonNull** giúp biết có validation không-null.
- **ArrayList.get** giúp biết thao tác truy cập theo chỉ số.
- **CompletableFuture** hoặc **FutureTask** giúp biết lỗi đi qua boundary bất đồng bộ.
- **Method.invoke** giúp nhận biết lời gọi reflection.

Sau đó tìm frame ứng dụng **gần vùng lỗi nhất và phù hợp nhất**, chứ không mặc định frame ứng dụng đầu tiên là bug. Nếu lỗi do framework gọi ngược vào mã của bạn qua callback, frame ứng dụng quan trọng có thể nằm ở nhiều vị trí.

### Những cách hiển thị vị trí khác

Có thể gặp:

~~~text
at java.base/java.util.ArrayList.get(ArrayList.java:427)
at app.NativeBridge.nativeMethod(Native Method)
at app.GeneratedProxy.call(Unknown Source)
at app.Main.lambda$main$0(Main.java:23)
~~~

Đây là minh họa định dạng, không khẳng định số dòng cố định của phiên bản JDK. **Native Method** và **Unknown Source** cho biết không có vị trí Java source line tương ứng trong frame theo cách hiển thị; **lambda$...** có thể là phương thức tổng hợp cho lambda, tên có thể thay đổi theo compiler. Phần prefix module, ví dụ **java.base/**, không phải một phần tên class trả về từ **StackTraceElement.getClassName()**.

Nếu class được biên dịch không có **LineNumberTable** hoặc mã đang chạy khác bản nguồn mở trong IDE, số dòng có thể không hữu ích. Đừng sửa đúng dòng trong bản nguồn cũ rồi khẳng định đã giải quyết: trước hết xác minh artifact, commit và môi trường chạy tương ứng.

## 12. Java 17: đọc StackTraceElement bằng mã

Một Throwable có thể cung cấp:

~~~java
// Mã minh họa trong phương thức nhận Throwable.
StackTraceElement[] frames = failure.getStackTrace();
for (StackTraceElement frame : frames) {
    String className = frame.getClassName();
    String method = frame.getMethodName();
    String fileName = frame.getFileName();
    int line = frame.getLineNumber();
    // Dùng các giá trị để phân tích hoặc hiển thị.
}
~~~

Các API hữu ích:

| API | Ý nghĩa và giới hạn |
| --- | --- |
| **getClassName()** | Tên nhị phân của class theo frame, không nhất thiết là một file Java mà bạn có thể sửa |
| **getMethodName()** | Tên phương thức hoặc tên synthetic do compiler tạo |
| **getFileName()** | Tên file nguồn nếu biết; có thể null |
| **getLineNumber()** | Số dòng nếu có; giá trị đặc biệt biểu thị không biết hoặc native |
| **isNativeMethod()** | Frame đại diện một phương thức native |
| **toString()** | Biểu diễn frame gần với cú pháp dòng **at ...** |

Đừng giả định **getStackTrace()[0]** luôn tồn tại: Throwable có thể có trace rỗng, đặc biệt khi writable stack trace bị vô hiệu hóa hoặc đối tượng do người viết class cấu hình. Với mã chẩn đoán dùng trong production, hãy kiểm tra độ dài trước khi lấy index.

Ví dụ phần 6 dùng một helper **firstApplicationFrame** lọc theo class của chính ví dụ. Nó **cố tình ném IllegalStateException** nếu không có frame phù hợp để bắt lỗi giả định trong demo. Một tool chẩn đoán tổng quát nên trả Optional hoặc tín hiệu “không tìm thấy” thay vì cho rằng mọi trace đều có frame thuộc package ứng dụng.

Java 9+ còn cung cấp **StackWalker** để duyệt stack của thread đang thực thi. Tuy nhiên, StackWalker chụp **stack hiện tại khi gọi**, còn **Throwable.getStackTrace()** đọc dấu vết đã được lưu trên một Throwable. Chúng không tự thay thế nhau: muốn tìm nơi một exception cũ phát sinh, thường cần trace của exception đó, không phải stack của logger đang chạy.

## 13. Phân biệt trace của main thread với lỗi trong task bất đồng bộ

Với **ExecutorService**, **Future** hoặc **CompletableFuture**, một tác vụ có thể thất bại ở thread worker nhưng kết quả lỗi được đọc ở thread caller. Khi đó dễ xuất hiện hai tầng dấu vết:

1. **Cause của task**: frame từ worker, nơi exception được tạo/phát sinh.
2. **Wrapper khi nhận kết quả**: frame từ caller đang gọi **get()** hoặc **join()**, hoặc frame của cơ chế completion.

Ví dụ khái niệm:

~~~text
java.util.concurrent.ExecutionException: java.lang.IllegalStateException: worker failed
    at java.base/java.util.concurrent.FutureTask.report(FutureTask.java:...)
    at java.base/java.util.concurrent.FutureTask.get(FutureTask.java:...)
    at app.Main.main(Main.java:...)
Caused by: java.lang.IllegalStateException: worker failed
    at app.Worker.compute(Worker.java:...)
    at app.Worker.call(Worker.java:...)
    ... more ...
~~~

Đây là cấu trúc minh họa, không phải stdout chính xác. Phần đầu mô tả nơi **caller thu nhận kết quả lỗi**, còn **Caused by** mô tả nơi **worker tạo lỗi**.

Với **CompletableFuture**, **get()** thường ném checked **ExecutionException** khi Future hoàn tất bất thường vì lỗi tác vụ; **join()** thường ném unchecked **CompletionException**. Hai wrapper này có thể giữ cùng lỗi gốc trong cause. Với Future bị hủy, **CancellationException** có thể ném trực tiếp. **get(timeout)** có thể ném **TimeoutException** vì lần chờ hết hạn, chứ không nhất thiết vì worker tạo một exception.

Khi điều tra, phải phân biệt:

- **InterruptedException ở caller.get()**: chính caller có thể bị interrupt khi chờ.
- **InterruptedException từ Callable worker**: có thể là cause bên trong ExecutionException.
- **TimeoutException trực tiếp từ get(timeout)**: caller chưa thấy kết quả trong thời hạn.
- **TimeoutException là cause sau orTimeout của CompletableFuture**: Future đã được hoàn tất bất thường bởi chính sách timeout.

Nếu chỉ nhìn wrapper của caller rồi tìm bug tại dòng **future.get()**, rất có thể bạn đang bỏ qua lỗi thực sự bên trong task hoặc một chính sách timeout ở tầng khác.

## 14. Đọc trace với try-with-resources, finally và cleanup

Tài nguyên được giải phóng khi rời khối, kể cả khi thân try đã gặp exception. Nhưng **close()** cũng có thể thất bại.

Với **try-with-resources**:

~~~java
// Minh họa với resource có AutoCloseable.close().
try (var resource = openResource()) {
    performOperation(resource);
}
~~~

Nếu **performOperation** ném lỗi A và **resource.close()** ném lỗi B, A được giữ là primary còn B được thêm vào **A.getSuppressed()**. Vì vậy khi đọc log, hãy tìm cả **Suppressed** để biết cleanup có lỗi mà không nhầm B thành nguyên nhân gây A.

Nếu dùng **finally** để cleanup rồi close ném exception mới không được xử lý, B có thể che khuất A. Đây là lỗi lập trình làm mất stack trace của failure ban đầu. Không chỉ so hai thông điệp rồi kết luận “close là lỗi duy nhất”.

Một trường hợp khác: thân try thành công nhưng close thất bại. Lúc ấy không có lỗi A từ thân; B có thể là exception chính được truyền ra. Bởi vậy **suppressed** không đồng nghĩa với **mọi exception phát sinh trong close**.

Nếu lỗi cleanup nằm sâu trong cause của một wrapper như ví dụ chính, tìm **Suppressed** ở chính cause phù hợp. Chỉ in **wrapper.getSuppressed()** có thể trả mảng rỗng dù **wrapper.getCause().getSuppressed()** chứa lỗi rất quan trọng.

## 15. Những nguồn gây hiểu nhầm khi so log với mã nguồn

Một stack trace được lấy từ hệ thống đang chạy phải được đặt cạnh **đúng phiên bản mã nguồn**:

- Đã deploy đúng JAR, classpath, container image hay chưa?
- File **.class** có được biên dịch từ commit đúng không?
- Số dòng có thay đổi vì mã nguồn đã chỉnh nhưng chương trình chưa build/deploy lại không?
- Một exception có bị wrap tại boundary của framework nên frame đầu nhìn khác kỳ vọng không?
- Có lambda, proxy, reflection hoặc generated code khiến tên class/method khó đối chiếu không?
- Nếu xảy ra ở task bất đồng bộ, có đang xem stack trace của thread consumer thay vì lỗi ở producer không?
- Log aggregator có lược bỏ phần **Caused by**, **Suppressed** hoặc giới hạn độ dài stack trace không?

Một log có thông báo **NullPointerException** nhưng không có frame vì cấu hình logger chỉ ghi message không phải bằng chứng JVM không có stack trace. Cần kiểm tra cách Throwable được truyền vào API logging.

Tương tự, một trace chứa **Unknown Source** không có nghĩa lỗi “không thể debug”. Hãy dùng class/method, các frame lân cận, bytecode/artifact phù hợp và các dữ kiện vận hành để khoanh vùng; đồng thời bật metadata line number cho các build cần hỗ trợ chẩn đoán.

## 16. Ghi log sao cho còn thông tin traceback

Java cung cấp **Throwable.printStackTrace()**, phù hợp cho ví dụ hoặc chẩn đoán đơn giản:

~~~java
// Mã minh họa trong catch hợp lệ.
catch (Exception failure) {
    failure.printStackTrace();
}
~~~

Trong ứng dụng production, thường nên dùng logging framework hoặc **java.util.logging** theo chính sách hệ thống. Ví dụ với **java.util.logging.Logger** của JDK:

~~~java
import java.util.logging.Level;
import java.util.logging.Logger;

// Minh họa trong một class có Logger logger và Throwable failure.
logger.log(Level.SEVERE, "Unable to process request", failure);
~~~

Đây là snippet minh họa theo ngữ cảnh, không phải class độc lập; **logger** phải được khởi tạo và **failure** phải tồn tại.

Đối với logger có chữ ký dạng **error(String, Throwable)**:

~~~java
// Minh họa API logger tương ứng, không phải Java SE độc lập.
logger.error("Unable to process request", failure);
~~~

Truyền **Throwable** giúp formatter có cơ hội hiển thị stack trace, cause và suppressed. Ngược lại:

~~~java
// Phản mẫu: thường chỉ ghi thông báo.
logger.error("Unable to process request: " + failure.getMessage());
~~~

có thể đánh mất dấu vết. Cần kiểm tra chữ ký logger và pipeline log cụ thể; đừng giả định mọi hệ logging đều in đầy đủ cây exception chỉ vì đã truyền đối tượng.

### Ghi log một lần ở ranh giới phù hợp

Một lỗi đi qua nhiều tầng service/controller có thể bị log ở mọi catch rồi ném lại. Kết quả là nhiều stack trace giống nhau trong cùng request, dễ bị đếm nhầm là nhiều sự cố. Mẫu thường tốt hơn:

- Tầng thấp **throw/wrap với cause phù hợp** và giữ context cần thiết.
- Tầng sở hữu ranh giới (controller/job scheduler/message consumer) ghi log đầy đủ một lần ở mức phù hợp.
- Dùng request ID/trace ID hoặc correlation ID để nối sự kiện qua thread và dịch vụ.
- Chỉ log lại giữa các tầng nếu có thông tin độc lập thực sự hữu ích.

Khi tạo log ở hệ thống thật, tránh ghi password, token, dữ liệu cá nhân, dữ liệu thẻ hoặc raw request chứa thông tin bí mật vào exception message. Stack trace chẩn đoán nên đầy đủ nhưng vẫn phải tuân thủ chính sách bảo mật và lưu giữ dữ liệu.

## 17. Quy trình đọc một stack trace để tìm bug

Một quy trình thực hành hiệu quả:

### Bước 1: Lấy đủ cây Throwable

Không chỉ chụp dòng exception đầu tiên. Thu thập phần **at**, **Caused by**, **Suppressed**, thông điệp trước/sau của cùng request và metadata về phiên bản ứng dụng. Nếu log bị cắt, tìm bản đầy đủ trước khi suy luận.

### Bước 2: Nhận diện wrapper hay lỗi trực tiếp

Nếu dòng đầu là **CompletionException**, **ExecutionException**, **InvocationTargetException** hoặc exception do framework dùng để thêm ngữ cảnh, truy xuống **getCause()**. Đừng nhầm điểm wrap là điểm lỗi nghiệp vụ ban đầu.

### Bước 3: Đọc loại lỗi sâu phù hợp

Xem lỗi thuộc loại input, trạng thái, parse, quyền truy cập, concurrency, I/O hay hệ ngoài. Chỉ dùng loại exception như dấu hiệu định hướng, không thay thế việc xem logic thực tế.

### Bước 4: Xem frame ứng dụng gần nguyên nhân

Tìm frame code của hệ thống xuất hiện trong trace của Throwable liên quan. Mở chính file và dòng nguồn của artifact đang chạy. Xác định biểu thức có thể thất bại ở dòng đó, không chỉ đọc tên phương thức.

### Bước 5: Đi xuống caller để hiểu dữ liệu đến từ đâu

Các frame ở dưới cho biết chuỗi gọi. Hỏi caller nhận input từ đâu, đã validate ở đâu, có state nào thay đổi, có điều kiện race hay dữ liệu trễ không.

### Bước 6: Xem cause/suppressed bổ sung

Nếu có **Caused by**, xác định quan hệ nguyên nhân. Nếu có **Suppressed**, xem cleanup có hỏng và có gây hệ quả trạng thái nào không. Không gộp hai loại thành “cùng một lỗi”.

### Bước 7: Đối chiếu ngữ cảnh vận hành

Kiểm tra timestamp, dependency status, thread name, endpoint, request ID, phiên bản deploy, feature flag, cấu hình, tải hệ thống và thao tác ngay trước khi lỗi xảy ra. Một stack trace thường là điểm bắt đầu tốt nhưng không phải toàn bộ thông tin.

### Bước 8: Tạo test tái hiện

Tạo unit test hoặc integration test với dữ liệu và điều kiện gây lỗi. Kiểm tra không chỉ “throw đúng exception” mà còn nguyên nhân, thông điệp có ích và bảo toàn trạng thái khi thất bại.

### Bước 9: Sửa nguyên nhân, không chỉ ẩn triệu chứng

Không sửa bằng **catch(Exception) { return null; }** hoặc **try/catch** nuốt lỗi chỉ để log biến mất. Nếu lỗi là input sai, sửa validation/handling; nếu race, sửa synchronization/ownership; nếu resource thiếu, sửa cấu hình/vòng đời tài nguyên.

### Bước 10: Xác minh kết quả và quan sát sau deploy

Test cả đường thành công, lỗi tương tự và lỗi cleanup; sau deploy xác nhận log giảm tương ứng, không có biến dạng trạng thái hoặc lỗi mới do thay đổi.

## 18. Ví dụ phân tích các tình huống phổ biến

### NullPointerException

~~~text
java.lang.NullPointerException
    at app.OrderService.calculate(OrderService.java:81)
    at app.OrderController.create(OrderController.java:33)
~~~

Cần xem dòng **calculate:81** dereference biến nào có thể null, dữ liệu được khởi tạo/validate ở đâu, caller **create** đưa đối tượng nào vào. Đừng tự kết luận mọi NullPointerException phải sửa bằng một **if (x != null)**; có thể hợp đồng yêu cầu đối tượng không được null, nên caller cần được sửa hoặc dữ liệu cần validation rõ ràng hơn.

### NumberFormatException

~~~text
java.lang.NumberFormatException: For input string: "x"
    at java.base/java.lang.Integer.parseInt(Integer.java:...)
    at app.ConfigParser.parsePort(ConfigParser.java:19)
    at app.Bootstrap.start(Bootstrap.java:8)
~~~

**Integer.parseInt** là nơi lỗi được tạo trong JDK, nhưng **parsePort** là frame cần xem dữ liệu cấu hình. Kiểm tra port được đọc từ đâu, có khoảng trắng, định dạng không hợp lệ hay giới hạn phạm vi nào.

### IndexOutOfBoundsException

~~~text
java.lang.IndexOutOfBoundsException: Index 4 out of bounds for length 3
    at java.base/java.util.ArrayList.get(ArrayList.java:...)
    at app.ReportService.column(ReportService.java:47)
~~~

Xem cách ReportService tính index so với kích thước dữ liệu, khả năng collection bị sửa đồng thời, ranh giới vòng lặp hoặc dữ liệu thiếu. Không quy trách nhiệm cho ArrayList khi caller đưa index sai.

### IOException có cause sâu

~~~text
java.io.IOException: failed to load feed
    at app.FeedReader.read(FeedReader.java:56)
Caused by: java.net.ConnectException: Connection refused
    at ... network stack ...
~~~

Lớp ngoài nói công việc load feed thất bại. Cause cho biết kết nối bị từ chối. Cần đối chiếu host/port, service đích, network policy, trạng thái dependency. Stack trace không thể tự khẳng định đó là lỗi firewall hay service down nếu chưa có dữ kiện ngoài.

### CompletionException từ bất đồng bộ

~~~text
java.util.concurrent.CompletionException: java.lang.IllegalStateException: worker failed
    at ... completion machinery ...
Caused by: java.lang.IllegalStateException: worker failed
    at app.Worker.process(Worker.java:72)
~~~

Ưu tiên xem **Worker.process:72** và input task. Dòng consumer gọi **join()** không nhất thiết là nguồn lỗi, dù đó là nơi exception được quan sát.

Các đoạn trên đều là ví dụ minh họa định dạng, không phải kết quả chạy chính xác của chương trình mục 6.

## 19. Kiểm thử hành vi exception và chất lượng trace

Khi tạo class và API có thể lỗi, nên xem chất lượng exception như một phần của hợp đồng:

| Tình huống cần test | Điều cần xác minh |
| --- | --- |
| Input không hợp lệ | Loại exception đúng, message đủ ngữ cảnh nhưng không lộ dữ liệu nhạy cảm |
| Lỗi thấp được wrap | Wrapper có cause là lỗi gốc |
| Throwable ném lại | Không vô ý làm mất object gốc, cause hoặc suppressed |
| Try-with-resources có lỗi chính và lỗi close | Lỗi chính còn nguyên; lỗi close nằm trong suppressed |
| Async task thất bại | Consumer nhìn đúng wrapper; cause phản ánh lỗi task |
| Logger nhận Throwable | Test/integration kiểm tra formatter có giữ stack trace/cause/suppressed |
| Nhiều phiên bản artifact | File/dòng trong trace khớp version đang chạy |
| Lỗi được recovery có chủ đích | Không coi fallback là xử lý thành công nếu business contract yêu cầu báo thất bại |

Có thể assert **same instance** cho cause, thay vì chỉ so sánh message. Ví dụ ở phần 6, nếu tách hàm trả về wrapper để test, nên kiểm tra **wrapper.getCause()** vẫn là chính NumberFormatException đã bắt, và **getSuppressed()** trên cause có IOException từ close.

**Không nên cố định số dòng source trong test thông thường**, trừ khi chính contract của công cụ chẩn đoán đòi hỏi mapping dòng. Số dòng thay đổi theo việc chỉnh mã, còn trace có thể khác giữa build modes. Test có thể kiểm tra tên class/method hoặc đường quan hệ cause/suppressed ổn định hơn.

Nếu dùng JUnit, một test đơn giản có thể assertThrows đúng kiểu rồi kiểm tra cause/suppressed. Tuy nhiên, đoạn test thực tế phải phù hợp phiên bản JUnit và setup dự án; không nhầm mã phụ thuộc framework với mã Java SE có thể biên dịch độc lập.

## 20. Lỗi thường gặp khi đọc hoặc ghi stack trace

**Chỉ đọc dòng đầu tiên.** Dễ bỏ qua cause sâu chứa lỗi thực sự, đặc biệt với CompletionException/ExecutionException hoặc wrapper nghiệp vụ.

**Cho rằng frame đầu của wrapper là nguồn lỗi thấp nhất.** Frame đầu có thể là nơi tạo wrapper; cần xem trace của cause.

**Chỉ tìm frame thuộc package dự án rồi coi đó là bug.** Frame ứng dụng có thể báo lỗi theo hợp đồng và nguyên nhân nằm ở cấu hình, input, dữ liệu từ ngoài hoặc dependency.

**Bỏ qua Suppressed.** Có thể không nhận ra close/rollback thất bại và trạng thái hệ thống chưa được làm sạch.

**Nhầm ... N more với N lỗi mới.** Đó là cách rút gọn frame trùng khi in cây exception.

**Bắt lỗi rồi tạo RuntimeException mới chỉ từ getMessage.** Làm đứt chuỗi cause và mất trace gốc, khiến debug khó hơn.

**Chỉ log getMessage().** Log thiếu class/method/source line, cause và suppressed. Nên truyền Throwable cho logger.

**Bật log ở mọi tầng.** Tạo bản sao cùng một sự cố, nhiễu cảnh báo và tốn tài nguyên. Chọn boundary quan sát có trách nhiệm.

**Tin tuyệt đối vào số dòng khi mã và deploy khác phiên bản.** Có thể đọc nhầm source cũ. Xác minh artifact/hash/commit và thông tin debug lines.

**Dùng exception message làm khóa phân nhánh logic.** Message có thể thay đổi theo JDK hoặc ngữ cảnh; ưu tiên type, cause, mã lỗi cấu trúc hoặc hợp đồng API.

**Coi trace ở caller.get()/join() là toàn bộ lịch sử bất đồng bộ.** Worker có thể có trace riêng trong cause; cần đi theo pipeline và correlation ID.

**Để lộ secrets qua log.** Exception và stack trace vẫn là dữ liệu vận hành có thể chứa tên file, URI, input, cấu hình; áp dụng masking và chính sách truy cập/retention.

## 21. Bảng kiểm đọc stack trace trong thực tế

Trước khi kết luận nguyên nhân, hãy trả lời:

1. **Loại exception ngoài cùng** là gì và message có cung cấp ngữ cảnh nào?
2. Có **Caused by** không? Cause sâu nào thực sự liên quan đến thao tác thất bại?
3. Có **Suppressed** không? Cleanup đã gặp lỗi gì?
4. **Frame đầu của Throwable đang phân tích** nằm ở đâu? Nó có phải frame thư viện, wrapper hoặc frame ứng dụng không?
5. Frame ứng dụng nào gần điểm lỗi nhất, và **dòng đó làm gì** với dữ liệu hiện có?
6. Chuỗi frame phía dưới phản ánh những caller nào và dữ liệu đi qua chúng ra sao?
7. Có tên **lambda/proxy/reflection**, module prefix, Native Method hoặc Unknown Source nào cần giải thích không?
8. Lỗi có xảy ra qua **Future/CompletableFuture** khiến wrapper được tạo ở thread consumer không?
9. Stack trace có tương ứng chính xác với **mã đã deploy** và metadata dòng nguồn của build đang chạy không?
10. Log có đủ Throwable tree, context, trace ID, nhưng không làm lộ dữ liệu nhạy cảm không?
11. Đã tạo được test tái hiện và sửa **nguyên nhân** thay vì chỉ nuốt exception chưa?

**Kết luận:** Đọc stack trace hiệu quả bắt đầu bằng **loại exception và message**, sau đó lần theo **stack frame**, phân biệt **điểm ghi nhận exception** với **nơi ứng dụng tạo điều kiện lỗi**, và luôn xem **Caused by** cùng **Suppressed**. Với wrapper hoặc tác vụ bất đồng bộ, lỗi ngoài cùng không nhất thiết là lỗi nghiệp vụ ban đầu. Giữ nguyên chuỗi Throwable khi ghi log và đối chiếu đúng mã nguồn đang chạy là cơ sở để xác định nguyên nhân một cách đáng tin cậy.
