# Đóng tài nguyên thủ công thiếu nhánh thất bại

## 1. Vấn đề: đường thành công có close, đường thất bại lại không

Một phương thức Java có thể sử dụng file, stream, socket, kết nối cơ sở dữ liệu, khóa hoặc một tài nguyên có vòng đời riêng. Khi công việc kết thúc, tài nguyên phải được thu hồi theo hợp đồng. **Sai lầm thường gặp** là chỉ gọi phương thức dọn dẹp ở **đường thành công**, quên rằng phần mở tài nguyên, thao tác chính, bước kiểm tra, câu lệnh return hoặc chính thao tác dọn dẹp đều có thể gặp lỗi.

Ví dụ:

~~~java
// Phản mẫu minh họa; openReader() trả về java.io.BufferedReader.
BufferedReader reader = openReader();
String firstLine = reader.readLine();  // Có thể ném IOException.
reader.close();                        // Không chạy nếu readLine() ném lỗi.
return firstLine;
~~~

Trong trường hợp bình thường, close được gọi. Nhưng nếu readLine() ném IOException, điều khiển thoát khỏi phương thức và **dòng close không được thực thi**. Tài nguyên có thể tiếp tục giữ file descriptor, buffer hoặc những dữ liệu nội bộ cần thu hồi. Nếu một phương thức tương tự được gọi nhiều lần, việc bỏ sót nhánh thất bại có thể tích lũy tài nguyên và khiến lỗi chỉ bộc lộ sau một thời gian vận hành.

Một cách sửa sơ sài khác là đưa close vào finally, nhưng **không xét close cũng có thể ném exception**. Khi phần thân và cleanup cùng lỗi, exception từ finally có thể che exception công việc chính, khiến log chỉ còn “close failed”, mất dấu “read failed”.

**Mục tiêu của bài:** bảo đảm những tài nguyên đã được mở thành công sẽ được thử đóng đúng lúc trên mọi đường rời phạm vi sở hữu; đồng thời giữ đầy đủ lỗi công việc và lỗi cleanup. Cách ưu tiên trong Java 17+ cho tài nguyên **AutoCloseable** là **try-with-resources**; cleanup thủ công chỉ nên dùng khi vòng đời tài nguyên hoặc hợp đồng API đòi hỏi logic đặc biệt.

## 2. Những nhánh phải xét khi đọc mã có tài nguyên

Đừng chỉ hỏi “có close không?”. Hãy lập danh sách **điểm phương thức có thể rời khỏi** và **trạng thái tài nguyên tại điểm đó**:

| Điểm xảy ra | Rủi ro nếu cleanup được viết thủ công sơ sài | Cách xét |
| --- | --- | --- |
| Mở tài nguyên đầu tiên thất bại | Không có tài nguyên hợp lệ để đóng; cố đóng biến null hoặc tài nguyên chưa sở hữu | Chỉ đóng những tài nguyên thực sự đã mở thành công |
| Mở tài nguyên thứ hai thất bại | Tài nguyên thứ nhất đã mở nhưng bị bỏ quên | Đóng tài nguyên đã mở trước |
| Thao tác chính ném checked exception | Chạy nhảy qua dòng close nằm sau thao tác | Đảm bảo cleanup ở mọi đường ném |
| Thao tác chính ném RuntimeException hoặc Error | Catch một loại checked exception không đủ | Ưu tiên cơ chế cleanup không phụ thuộc loại lỗi |
| Return sớm khi đã có tài nguyên | Bỏ qua close đặt cuối phương thức | Đóng trước khi return hoàn tất |
| Break/continue/nhánh điều kiện | Bỏ qua một hoặc nhiều bước cleanup | Gắn quyền sở hữu với phạm vi phù hợp |
| Cleanup cũng ném exception | Lỗi cleanup che mất lỗi công việc hoặc ngăn cleanup còn lại | Giữ primary, thu thập lỗi phụ |
| Hủy/interrupt tác vụ | Luồng rời thao tác chờ khi tài nguyên vẫn đang giữ | Cleanup và chính sách interruption cần nhất quán |
| Nhiều tài nguyên cùng dùng | Thứ tự đóng sai, chỉ đóng được một tài nguyên | Đóng theo thứ tự phù hợp và vẫn thử phần còn lại |
| Thao tác hoàn tất nhưng close/flush lỗi | Caller nhận “thành công” dù bước hoàn tất thất bại | Truyền lỗi cleanup theo hợp đồng |

Cốt lõi là **quyền sở hữu tài nguyên**: phương thức hay đối tượng nào có trách nhiệm đóng, tại thời điểm nào, và sau khi chuyển quyền sở hữu thì ai tiếp tục chịu trách nhiệm. Tên biến hoặc việc một object còn reachable không tự xác lập quyền sở hữu; phải đọc hợp đồng API.

## 3. Phản mẫu: close ở cuối không bảo vệ đường exception

Xét phương thức giả định:

~~~java
// Mã minh họa theo ngữ cảnh; không phải chương trình độc lập.
static byte[] readAll(Path path) throws IOException {
    InputStream input = Files.newInputStream(path);
    byte[] bytes = input.readAllBytes();
    input.close();
    return bytes;
}
~~~

Nếu **readAllBytes()** ném IOException hoặc OutOfMemoryError, **input.close()** không được gọi. Dù caller catch lỗi, trách nhiệm giải phóng tài nguyên bên trong phương thức đã bị bỏ sót.

Cách sửa bằng try-with-resources:

~~~java
// Minh họa phương thức Java 17+, với imports thích hợp.
static byte[] readAll(Path path) throws IOException {
    try (InputStream input = Files.newInputStream(path)) {
        return input.readAllBytes();
    }
}
~~~

Với **InputStream implements Closeable** (và qua đó implements AutoCloseable), Java gọi **close()** khi rời khối try, kể cả khi readAllBytes ném lỗi hoặc thân try đi qua return.

Nếu phần thân thất bại và close cũng thất bại, lỗi phần thân được giữ là **primary exception**; lỗi close được gắn vào danh sách **suppressed** trên primary. Việc đóng file có thể báo lỗi: người gọi cần biết cả kết quả công việc và việc thu hồi tài nguyên có thành công hay không.

Đây không phải bảo đảm rằng bytes chưa được đọc trước khi lỗi sẽ “được hoàn tác”; nó chỉ bảo đảm **vòng đời close được xử lý** và exception được báo theo hợp đồng.

## 4. Vì sao finally chưa đủ khi cleanup cũng có thể thất bại?

Một cách sửa cũ thường là:

~~~java
// Phản mẫu minh họa.
InputStream input = Files.newInputStream(path);
try {
    return input.readAllBytes();
} finally {
    input.close();
}
~~~

Mẫu này tốt hơn việc close ở cuối vì **close được thử khi phần thân lỗi hoặc return**. Tuy nhiên, nếu readAllBytes ném một IOException rồi close ném IOException khác, ngoại lệ phát sinh trong finally có thể **thay thế lỗi đọc ban đầu**. Người gọi chỉ thấy lỗi đóng tài nguyên mà không thấy đường lỗi khiến thao tác chính thất bại.

Nếu trong finally còn có **return**, nó có thể che cả exception đang chờ và kết quả đang chờ:

~~~java
// Phản mẫu minh họa; tuyệt đối không dùng như giải pháp cleanup.
try {
    performOperation();
} finally {
    return; // Có thể làm biến mất exception từ try.
}
~~~

**Không dùng return trong finally để “đảm bảo cleanup”**. Và đừng nghĩ rằng catch cleanup rồi bỏ qua là an toàn:

~~~java
// Phản mẫu minh họa.
try {
    resource.close();
} catch (Exception ignored) {
    // Lỗi cleanup bị nuốt, trạng thái thu hồi không rõ.
}
~~~

Khi việc close gặp lỗi, caller có thể cần biết tài nguyên có còn hợp lệ, dữ liệu có flush đủ hay không hoặc có nên retry. Giấu tất cả lỗi trong catch làm giảm khả năng phát hiện những trường hợp này.

## 5. Cơ chế chuẩn Java: try-with-resources

**Try-with-resources** được giới thiệu từ Java 7 và dùng được trong Java 17+. Mỗi tài nguyên khai báo trong dấu ngoặc phải là **AutoCloseable**:

~~~java
// Minh họa; openResource() trả về một AutoCloseable thích hợp.
try (var resource = openResource()) {
    performOperation(resource);
}
~~~

Java tự quản lý lời gọi **resource.close()** ở cuối phạm vi try. Những bảo đảm có liên quan tới bài này:

1. Nếu phần thân chạy thành công, close vẫn được gọi.
2. Nếu phần thân ném exception, close vẫn được thử.
3. Nếu phần thân đi qua return, close được thực hiện **trước khi phương thức hoàn tất return**.
4. Nếu có nhiều tài nguyên, chúng được đóng theo **thứ tự ngược khi khai báo**.
5. Nếu đang mở tài nguyên sau mà thất bại, những tài nguyên đã mở trước vẫn được đóng.
6. Nếu phần thân đã lỗi và close tiếp tục lỗi, lỗi close được ghi là **suppressed exception**, không che primary theo cơ chế chuẩn.
7. Nếu phần thân thành công nhưng close thất bại, lỗi close có thể được ném như exception chính của lời gọi.

Đây là cách giảm số lượng nhánh phải tự viết, đặc biệt khi một API có nhiều loại checked và unchecked exceptions. Cấu trúc cú pháp làm **quyền sở hữu và phạm vi đóng** rõ ràng hơn.

Cần hiểu rằng **AutoCloseable** khai báo **close() throws Exception**; **java.io.Closeable** có chữ ký **close() throws IOException**. Việc khai báo/bắt checked exception phụ thuộc **kiểu tĩnh** của tài nguyên và API mà phương thức gọi, không phải try-with-resources tự loại bỏ checked exceptions.

## 6. Ví dụ Java 17+ hoàn chỉnh: sáu đường rời và lỗi cleanup

Chương trình dưới đây sử dụng một loại tài nguyên giả để quan sát hành vi rõ ràng, không phụ thuộc file, database hoặc mạng thật. **DemoResource** in tên khi mở/đóng và có thể được cấu hình ném IOException trong close.

Sáu nhóm kịch bản được chạy tuần tự:

- **Không có finally**: công việc lỗi trước close, tài nguyên không được thử đóng.
- **Finally sai**: cleanup ném lỗi và che lỗi công việc.
- **Try-with-resources đúng**: giữ lỗi công việc làm primary và lỗi đóng làm suppressed.
- **Hai tài nguyên**: đóng ngược thứ tự và giữ mọi lỗi phụ.
- **Mở tài nguyên thứ hai thất bại**: vẫn đóng tài nguyên mở trước đó.
- **Return nhưng close lỗi**: không trả kết quả như thể thành công khi close thất bại.

Lưu file **CleanupBranchesDemo.java**:

~~~java
import java.io.IOException;

public class CleanupBranchesDemo {
    static final class DemoResource implements AutoCloseable {
        private final String name;
        private final boolean closeFails;

        DemoResource(String name, boolean closeFails) {
            this.name = name;
            this.closeFails = closeFails;
            System.out.println("open " + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            if (closeFails) {
                throw new IOException("close " + name + " failed");
            }
        }
    }

    static DemoResource openSecondAndFail() throws IOException {
        System.out.println("opening second failed");
        throw new IOException("second open failed");
    }

    static void wrongWithoutFinally() throws IOException {
        DemoResource resource = new DemoResource("leaky", false);
        throw new IOException("work failed");
    }

    static void wrongWithFinally() throws IOException {
        DemoResource resource = new DemoResource("masked", true);
        try {
            throw new IOException("work failed");
        } finally {
            resource.close();
        }
    }

    static void correctWorkAndCloseFailure() throws IOException {
        try (DemoResource resource = new DemoResource("safe", true)) {
            throw new IOException("work failed");
        }
    }

    static void correctSeveralResources() throws IOException {
        try (DemoResource first = new DemoResource("first", true);
             DemoResource second = new DemoResource("second", true)) {
            throw new IOException("work failed");
        }
    }

    static void correctInitializationFailure() throws IOException {
        try (DemoResource first = new DemoResource("opened", true);
             DemoResource second = openSecondAndFail()) {
            System.out.println("unreachable");
        }
    }

    static String returnAfterClose() throws IOException {
        try (DemoResource resource = new DemoResource("return", true)) {
            return "done";
        }
    }

    static void show(IOException failure) {
        System.out.println("primary: " + failure.getMessage());
        for (Throwable secondary : failure.getSuppressed()) {
            System.out.println("suppressed: " + secondary.getMessage());
        }
    }

    public static void main(String[] args) {
        System.out.println("== No finally ==");
        try {
            wrongWithoutFinally();
        } catch (IOException failure) {
            show(failure);
        }
        System.out.println("== Incorrect finally ==");
        try {
            wrongWithFinally();
        } catch (IOException failure) {
            show(failure);
        }
        System.out.println("== Try-with-resources ==");
        try {
            correctWorkAndCloseFailure();
        } catch (IOException failure) {
            show(failure);
        }
        System.out.println("== Two resources ==");
        try {
            correctSeveralResources();
        } catch (IOException failure) {
            show(failure);
        }
        System.out.println("== Initialization failure ==");
        try {
            correctInitializationFailure();
        } catch (IOException failure) {
            show(failure);
        }
        System.out.println("== Return then close failure ==");
        try {
            System.out.println("result: " + returnAfterClose());
        } catch (IOException failure) {
            show(failure);
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 CleanupBranchesDemo.java
java CleanupBranchesDemo
~~~

Stdout đã được kiểm tra trực tiếp:

~~~text
== No finally ==
open leaky
primary: work failed
== Incorrect finally ==
open masked
close masked
primary: close masked failed
== Try-with-resources ==
open safe
close safe
primary: work failed
suppressed: close safe failed
== Two resources ==
open first
open second
close second
close first
primary: work failed
suppressed: close second failed
suppressed: close first failed
== Initialization failure ==
open opened
opening second failed
close opened
primary: second open failed
suppressed: close opened failed
== Return then close failure ==
open return
close return
primary: close return failed
~~~

### Đọc kết quả: No finally

Tài nguyên **leaky** được mở và chương trình ném **work failed**. Không có dòng **close leaky**. Đây là phản mẫu minh họa **thiếu nhánh đóng khi công việc lỗi**. Tài nguyên giả chỉ in log; trong hệ thống thật, một stream/socket/connection tương tự có thể giữ tài nguyên hạ tầng cho tới khi được giải phóng bằng cách khác, và không được dựa vào garbage collector để đảm bảo close đúng thời điểm.

### Đọc kết quả: Incorrect finally

Phần thân ném **work failed**, rồi finally gọi close trên **masked** và close ném **close masked failed**. Exception thoát ra là lỗi cleanup, khiến **work failed** bị che. Không có suppressed exception tự động trong mẫu finally này.

### Đọc kết quả: Try-with-resources

Tài nguyên **safe** được đóng khi thân try thất bại. **work failed** vẫn là primary; **close safe failed** nằm trong danh sách suppressed. Chương trình cho thấy cả hai thông tin cùng được giữ mà không phải tự viết catch/finally phức tạp.

### Đọc kết quả: Two resources

Java đóng **second** rồi **first**. Khi hai lần đóng đều ném IOException, phần thân **work failed** vẫn là primary, còn lỗi đóng second và first lần lượt được thêm vào suppressed. Đây là đường rất dễ bỏ sót nếu viết các lệnh close nối tiếp trong finally mà không có chiến lược bắt từng lỗi.

### Đọc kết quả: Initialization failure

Tài nguyên **opened** đã được tạo thành công. Mở tài nguyên tiếp theo bằng **openSecondAndFail()** ném **second open failed** trước khi có resource thứ hai. Try-with-resources vẫn gọi close trên **opened**. Nếu close của opened cũng lỗi, lỗi đó được suppressed lên exception khi mở thứ hai. Đó là cách tránh rò tài nguyên **đã mở trước khi quá trình khởi tạo đầy đủ hoàn thành**.

### Đọc kết quả: Return then close failure

Lệnh return **"done"** được đánh giá trong thân try, nhưng Java cần đóng resource trước khi phương thức thực sự hoàn tất. Close ném IOException, nên caller không nhận được **"done"**; thay vào đó catch in **close return failed**. Điều này quan trọng với các stream có thể flush/hoàn tất dữ liệu lúc đóng: đến được lệnh return không đồng nghĩa toàn bộ lời gọi thành công.

## 7. Lỗi khi mở tài nguyên thứ hai: nhánh thường bị quên

Một phản mẫu khởi tạo nhiều tài nguyên:

~~~java
// Minh họa theo ngữ cảnh; cả a và b cần được đóng.
Resource a = openA();
Resource b = openB(); // Có thể ném exception.
try {
    use(a, b);
} finally {
    b.close();
    a.close();
}
~~~

Nếu **openB()** ném exception, **khối try/finally chưa bắt đầu**, nên a không được đóng. Đây là lý do “có finally” vẫn chưa đủ nếu **phạm vi finally bắt đầu sau quá trình cấp phát có thể thất bại**.

Sửa bằng try-with-resources:

~~~java
// Minh họa: Resource implements AutoCloseable.
try (Resource a = openA();
     Resource b = openB()) {
    use(a, b);
}
~~~

Nếu a mở thành công rồi b không mở được, Java đóng a trên đường xử lý thất bại. Nếu close của a cũng ném lỗi, lỗi khởi tạo b vẫn được giữ là primary khi suppression hoạt động.

Nếu nhà cung cấp tài nguyên có factory với tác dụng phụ **trước khi trả về object**, nhưng factory thất bại và tự làm thất thoát tài nguyên nội bộ, try-with-resources bên ngoài **không thể đóng một object chưa được trả về**. Chính factory phải có cleanup khi nó cấp phát dở dang:

~~~java
// Minh họa logic bên trong factory; không phải chương trình độc lập.
ResourcePartial partial = openPartial();
try {
    finishInitialization(partial);
    return partial;
} catch (Exception failure) {
    // Cần cleanup partial theo cơ chế bảo toàn primary phù hợp.
    throw failure;
}
~~~

Không sao chép đoạn này như một factory hoàn chỉnh: comment đại diện cho bước cleanup còn cần được triển khai, và ví dụ chỉ minh họa **ranh giới trách nhiệm khi khởi tạo**. Trong code thật, ưu tiên thiết kế constructor/factory có bảo đảm exception safety rõ ràng hoặc sử dụng try-with-resources ngay bên trong factory khi có thể.

## 8. Lỗi thân try và lỗi close: primary khác suppressed

`try-with-resources` thường giữ **lỗi thân `try` A làm primary** khi `close()` ném thêm B. Người gọi xem `A.getSuppressed()` để thấy B. Nếu service bọc A thành C thì B vẫn nằm ở `C.getCause().getSuppressed()`, không tự động chuyển sang suppressed của C.

~~~text
body: throw A      -> primary A
close(): throw B   -> A.getSuppressed() chứa B
wrap A thành C     -> C.getCause() là A
~~~

Khi chỉ `close()` thất bại, chính lỗi close là primary. Nếu nhiều tài nguyên cùng đóng thất bại, lỗi close **đầu tiên theo thứ tự đóng ngược** có thể trở thành primary, các lỗi đóng sau được giữ như suppressed; Java vẫn thử đóng những tài nguyên còn lại.

Trong bài cleanup, **không được xem lỗi close luôn vô hại**: tùy API, thao tác đóng có thể flush/finalize hoặc xác nhận hoàn tất dữ liệu. Đọc hợp đồng resource và test hậu điều kiện của thao tác, không chỉ đếm exception.

## 9. Đóng nhiều tài nguyên: còn phải thử close tiếp theo

Phản mẫu:

~~~java
// Phản mẫu minh họa, khi đã giữ cả a và b.
finally {
    b.close(); // Nếu ném, a.close() không được chạy.
    a.close();
}
~~~

Một lệnh close ném exception sẽ bỏ qua lệnh kế tiếp trong cùng finally, trừ khi bạn chủ động bắt xử lý. Tài nguyên a có thể bị bỏ quên chỉ vì b close lỗi.

Với try-with-resources:

~~~java
// Minh họa tài nguyên triển khai AutoCloseable.
try (Resource a = openA();
     Resource b = openB()) {
    use(a, b);
}
~~~

Java đóng b trước, rồi a. Các close được xử lý theo cơ chế bảo toàn lỗi; lỗi từ close đầu không ngăn toàn bộ cơ chế tiếp tục thử đóng những tài nguyên đã mở còn lại.

**Lưu ý về thứ tự:** Đóng ngược khai báo thường phù hợp với phụ thuộc vòng đời. Ví dụ stream bọc một stream khác thường phải đóng wrapper trước hoặc để wrapper sở hữu close của stream dưới; **không nên đóng cùng tài nguyên hai lần** chỉ vì hai biến khác nhau tham chiếu vào nó. Một số wrapper close luôn tài nguyên nền; hãy đọc hợp đồng ownership.

### Thứ tự đóng không phải hình thức

Nếu B phụ thuộc vào A khi close, đặt **A trước B** trong khai báo để B đóng trước A:

~~~java
// Minh họa theo ngữ cảnh.
try (Resource connection = openConnection();
     Resource statement = openStatement(connection)) {
    use(statement);
}
~~~

Nếu A có nhiệm vụ sở hữu/đóng B tự động, khai báo cả A và B làm tài nguyên độc lập cần được cân nhắc để tránh đóng trùng không có chủ đích. **AutoCloseable** không mặc định cam kết close idempotent cho mọi loại tài nguyên.

## 10. Trường hợp biến null, factory thất bại và scope

Một cách viết cleanup thủ công thường dùng:

~~~java
// Minh họa theo ngữ cảnh.
Resource resource = null;
try {
    resource = openResource();
    work(resource);
} finally {
    resource.close(); // Nếu openResource thất bại, resource == null.
}
~~~

Nếu openResource ném lỗi trước khi gán biến, finally tiếp tục dereference null và có thể ném NullPointerException, che khuất lỗi mở tài nguyên.

Có thể phòng null:

~~~java
// Minh họa một nhánh cleanup thủ công.
finally {
    if (resource != null) {
        resource.close();
    }
}
~~~

Nhưng cách này vẫn chưa tự giải quyết vấn đề **close cũng ném lỗi**, và phải xét những exception của phần thân. Nếu tài nguyên là AutoCloseable, **try-with-resources** thường rõ hơn. Java sẽ **không gọi close nếu giá trị tài nguyên trong resource specification là null**; tuy nhiên thiết kế factory nên ưu tiên trả object hợp lệ hoặc ném lỗi rõ ràng để code không phải dựa vào null.

Nếu một thư viện chỉ trả handle đặc biệt và không triển khai AutoCloseable, cần bọc handle trong adapter quản lý ownership hoặc thiết kế cleanup thủ công có đầy đủ nhánh.

## 11. Cleanup thủ công khi API không có AutoCloseable

Không phải API nào cũng cung cấp AutoCloseable. Đôi khi phải dùng phương thức như **release()**, **unlock()**, **rollback()** hoặc một lệnh hủy riêng. Khi đó code cần xác định:

- **Khi nào quyền sở hữu bắt đầu?** Sau khi mở/lock thành công.
- **Khi nào quyền sở hữu kết thúc?** Sau khi cleanup thành công hoặc chuyển giao.
- **Loại lỗi nào có thể phát sinh?** Checked, unchecked, Error, interruption.
- **Lỗi nào là primary nếu nhiều bước thất bại?**
- **Có tiếp tục cleanup các tài nguyên khác được không?**
- **Nếu cleanup lỗi, trạng thái hệ thống còn tin cậy không?**

Một ví dụ an toàn tương đối với **Lock**:

~~~java
// Minh họa: lock là java.util.concurrent.locks.Lock.
lock.lock();
try {
    performOperation();
} finally {
    lock.unlock();
}
~~~

Khóa chỉ được đưa vào phạm vi finally **sau khi lock() thành công**. Nhưng nếu **unlock()** ném lỗi trong lúc thân try cũng lỗi, vấn đề che primary vẫn có thể phát sinh. Các Lock tiêu chuẩn thông thường không dùng checked exception cho unlock, nhưng có thể ném unchecked exception nếu sử dụng sai hợp đồng.

Với API interruptible:

~~~java
// Minh họa: java.util.concurrent.locks.Lock.
lock.lockInterruptibly();
try {
    performOperation();
} finally {
    lock.unlock();
}
~~~

Đặt **lockInterruptibly() trước try** để nếu nó ném InterruptedException trước khi lấy khóa, code không gọi unlock trên lock mình chưa sở hữu. Đây là một lỗi scope cleanup đặc biệt khó phát hiện nếu chỉ nhìn thấy có finally.

### Có thể dùng adapter AutoCloseable

Với một resource có **release()** nhưng không implements AutoCloseable, có thể tạo một adapter:

~~~java
// Minh họa trong phương thức, giả định handle đã acquire thành công.
try (AutoCloseable scope = () -> handle.release()) {
    use(handle);
}
~~~

Cần lưu ý **AutoCloseable.close()** có thể ném Exception, nên phương thức chứa code phải khai báo/bắt exception phù hợp. Nếu kiểu handle cần cleanup chính xác một lần hoặc có thể thất bại một phần, adapter phải tuân thủ contract đó; biểu thức lambda trên chỉ là minh họa ngắn cho mô hình.

## 12. Cleanup khi catch một kiểu lỗi nhưng bỏ sót kiểu khác

Một mẫu thủ công dễ thất bại:

~~~java
// Phản mẫu minh họa theo ngữ cảnh.
try {
    performOperation();
} catch (IOException failure) {
    resource.close();
    throw failure;
}
resource.close();
~~~

Code có thể xử lý IOException, nhưng nếu **performOperation() ném RuntimeException hoặc Error**, đường cleanup đó bị bỏ sót. Chỉ catch những loại đã nghĩ tới không chứng minh cleanup bao phủ mọi đường thất bại.

Kể cả đổi thành **catch(Exception)**, kiểu Error không bị bắt. Việc cố **catch(Throwable)** để tiếp tục chạy cũng rủi ro vì Error có thể đại diện tình trạng JVM nghiêm trọng, không phải điều kiện phục hồi bình thường.

**Try-with-resources** giải quyết việc đóng tài nguyên theo đường rời khối mà không phải viết từng catch riêng cho IOException, RuntimeException, Error hoặc return.

Nếu vẫn cần cleanup thủ công, hãy thiết kế theo *hợp đồng sở hữu tài nguyên* và tất cả điểm thoát có thể xảy ra; tránh tin rằng một catch đủ rộng là thay thế cho finally hoặc AutoCloseable.

## 13. Sửa bằng finally bảo toàn lỗi khi thực sự bắt buộc

Nếu API cleanup không phù hợp với AutoCloseable hoặc có ràng buộc đặc biệt, cần giữ lỗi công việc chính và đính kèm lỗi cleanup. Một mẫu **chỉ minh họa logic**, không phải trình thay thế tổng quát cho try-with-resources:

~~~java
// Minh họa phạm vi: resource implements AutoCloseable;
// work(resource) có thể ném IOException, còn close() ném IOException.
IOException primary = null;
try {
    work(resource);
} catch (IOException original) {
    primary = original;
    throw original;
} finally {
    try {
        resource.close();
    } catch (IOException cleanup) {
        if (primary != null && primary != cleanup) {
            primary.addSuppressed(cleanup);
        } else {
            throw cleanup;
        }
    }
}
~~~

Ở đây **primary** là chính object IOException đã bị bắt, không phải một bản copy chỉ chứa message. Khi cleanup ném IOException, **addSuppressed()** giữ lỗi phụ trên primary, rồi rethrow original từ catch tiếp tục có hiệu lực.

**Giới hạn nghiêm trọng của mẫu này:** Code chỉ catch IOException. Nếu work ném RuntimeException hoặc Error và close ném IOException, finally có thể che khuất lỗi work. Nếu tài nguyên có close() throws Exception rộng hơn, chữ ký đoạn này cũng chưa đủ. Vì vậy không nên copy mẫu này cho mọi tài nguyên rồi coi đã giải quyết xong mọi đường lỗi.

Nếu cần một quy tắc ưu tiên thực sự bao quát, có thể tổ chức code theo Throwable nhưng phải giữ đúng loại lỗi và tránh nuốt Error. Với close thuần AutoCloseable, **try-with-resources** vẫn là lựa chọn đơn giản và chính xác hơn.

### Tránh self-suppression

**Throwable.addSuppressed()** không cho phép thêm chính Throwable đó làm suppressed của nó. Nếu **primary == cleanup**, lệnh addSuppressed sẽ ném IllegalArgumentException. Đây là trường hợp hiếm nhưng phải được xét nếu cleanup và công việc có thể dùng chung một instance Throwable (ví dụ lỗi được tái sử dụng). Tài liệu Java cũng không bảo đảm suppression được bật trên mọi Throwable tùy chỉnh; nếu suppression bị vô hiệu hóa, addSuppressed không giữ lỗi phụ.

Không cố lưu mọi lỗi cleanup dưới dạng **cause** của primary: cause mô tả quan hệ nguyên nhân, còn suppressed mô tả lỗi phụ phát sinh trong quá trình xử lý/thu hồi. Dùng hai quan hệ đúng nghĩa giúp log dễ chẩn đoán hơn.

## 14. Đóng tài nguyên và giao dịch: đừng nhầm cleanup với rollback

Vấn đề “đủ nhánh cleanup” thường bị trộn với câu hỏi “dữ liệu có được khôi phục khi thất bại hay không?”. Đây là hai đảm bảo khác nhau.

**Đóng một stream** không xóa các byte đã ghi trước đó. **Đóng connection** không đồng nghĩa commit hay rollback thành công theo mọi hợp đồng JDBC/pool. **Release lock** không làm object tự quay về trạng thái trước khi sửa. **Hủy Future** không đảo ngược request mạng đã gửi.

Ví dụ với giao dịch JDBC thủ công, nếu connection thuộc quyền sở hữu của phạm vi này:

~~~java
// Mã minh họa theo ngữ cảnh; DataSource và SQLException đã import.
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        doSqlWork(connection);
        connection.commit();
    } catch (SQLException workFailure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            workFailure.addSuppressed(rollbackFailure);
        }
        throw workFailure;
    }
}
~~~

Đây là ví dụ phục vụ phân tích đường lỗi **SQLException**, chưa phải class độc lập; **doSqlWork** là logic ứng dụng. Try-with-resources đảm bảo thử close connection trên các đường rời. Nhánh catch chủ động thử rollback nếu doSqlWork/commit ném SQLException; lỗi rollback được suppressed thay vì che lỗi chính. Nếu close còn lỗi, try-with-resources tiếp tục thêm lỗi close vào exception chính khi cơ chế suppression hoạt động.

**Những giới hạn phải nhớ:**

- Nếu doSqlWork có thể ném RuntimeException/Error, catch(SQLException) không thực hiện rollback cho những đường đó; cần thiết kế transaction boundary bao quát đúng hợp đồng ứng dụng.
- Nếu **setAutoCommit(false)** thất bại trước khi vào inner try, nhánh rollback ở trên không chạy; connection vẫn được thử close, nhưng phải phân tích trạng thái transaction riêng.
- Rollback có thể không thành công; việc gắn exception rollback vào suppressed **không bảo đảm transaction đã phục hồi**.
- Có framework quản lý transaction tự động; tự commit/rollback ngoài phạm vi sở hữu có thể phá hợp đồng framework.
- Sau lỗi transaction, connection có thể cần được đánh dấu không đáng tin hoặc loại khỏi pool theo cơ chế của datasource, không tiếp tục sử dụng như thể an toàn.

Với dữ liệu bên ngoài, **exception safety** và **state recovery** đòi hỏi chính sách transaction, idempotency hoặc compensation riêng. Try-with-resources chỉ quản lý vòng đời AutoCloseable và exception của close, không biến mọi tác động thành giao dịch nguyên tử.

## 15. Trả kết quả sớm, vòng lặp và chuyển quyền sở hữu

Các nhánh không ném exception cũng dễ bị quên:

~~~java
// Phản mẫu minh họa.
Resource resource = openResource();
if (skip(resource)) {
    return; // Bỏ qua close nếu viết nó ở cuối phương thức.
}
use(resource);
resource.close();
~~~

Với try-with-resources:

~~~java
// Minh họa cùng ngữ cảnh.
try (Resource resource = openResource()) {
    if (skip(resource)) {
        return;
    }
    use(resource);
}
~~~

Java vẫn đóng resource khi gặp return. Tương tự, rời khỏi phạm vi try qua break hoặc continue trong cấu trúc vòng lặp được sắp xếp phù hợp vẫn thực hiện cleanup.

**Nhưng đừng trả về chính tài nguyên rồi đóng nó trước khi caller dùng:**

~~~java
// Phản mẫu minh họa.
Resource openAndReturn() throws Exception {
    try (Resource resource = openResource()) {
        return resource; // Resource đã bị close trước khi caller nhận.
    }
}
~~~

Nếu nhiệm vụ phương thức là **chuyển quyền sở hữu resource cho caller**, nó không được tự đóng trước khi giao. Hợp đồng phải quy định caller chịu trách nhiệm đóng, ví dụ trả về một InputStream còn mở rồi caller đặt nó trong try-with-resources ở phía mình. Không áp dụng TWR một cách máy móc khi ownership thực sự cần chuyển giao.

Một trường hợp tương tự là trả về **Stream** từ API lazy: stream có thể còn cần đọc datasource sau khi phương thức trả về. Nếu datasource đã đóng trong phương thức, operation về sau có thể thất bại. Tài liệu API nên nói rõ quyền sở hữu và trách nhiệm close của caller.

## 16. Đóng khi task bị ngắt hoặc hủy

Trong concurrency, một tác vụ có thể rời một lệnh blocking qua **InterruptedException**. Nếu tài nguyên đang mở, cleanup vẫn phải chạy. Đặt resource trong try-with-resources giúp xử lý nhánh ném checked exception này cùng những nhánh lỗi khác.

~~~java
// Minh họa: resource implements AutoCloseable;
// waitForWork có thể ném InterruptedException.
try (Resource resource = openResource()) {
    waitForWork(resource);
}
~~~

Tuy nhiên, có hai mối quan tâm riêng:

1. **Bảo toàn thông tin InterruptedException:** Nếu method cho phép, để InterruptedException lan truyền; nếu không, boundary có thể cần khôi phục **Thread.currentThread().interrupt()** và kết thúc theo hợp đồng.
2. **Cleanup không tự cancel side effect:** Đóng resource không có nghĩa một request phía ngoài chắc chắn dừng hoặc rollback.

Cẩn thận nếu trong cleanup còn gọi API blocking có thể bị interrupt. Khi thread có interrupt flag, cleanup có thể thất bại ngay. Cần thiết kế timeout và chính sách xử lý lỗi cleanup, tránh đổi một đường yêu cầu dừng thành chờ vô hạn hoặc che lỗi gốc.

Nếu một Future bị **cancel(true)**, việc Future ở trạng thái canceled không chứng minh worker đã thôi sử dụng tài nguyên. Quy tắc sở hữu phải tính tới lúc worker thực sự kết thúc và lúc phạm vi cleanup chạy.

## 17. Khi nào close thất bại cần retry?

Không nên mặc định close có thể gọi lặp an toàn. **AutoCloseable** không bảo đảm mọi implementation **idempotent**; có loại close nhiều lần được phép, có loại dẫn đến lỗi hoặc tác dụng phụ khác.

Khi close ném exception:

- Đọc hợp đồng tài nguyên xem trạng thái sau thất bại có được xác định không.
- Không gọi close lần hai ngay lập tức chỉ vì muốn “chắc đã đóng”, nếu không hiểu hậu quả.
- Một số thao tác finish/flush/commit không phải cleanup thuần; retry có thể gây ghi trùng hoặc lỗi trạng thái.
- Nếu API cho phép và việc retry được thiết kế rõ, giới hạn số lần, backoff và log kết quả.
- Nếu tài nguyên còn khả năng sử dụng nguy hiểm, đánh dấu không đáng tin và chuyển cho tầng sở hữu cao hơn quyết định.

Với tài nguyên pool, đôi khi close trả kết nối về pool thay vì thật sự đóng socket. Close lỗi có thể yêu cầu pool loại bỏ handle. Điều này thuộc hợp đồng cụ thể của implementation; không tự suy ra mọi Connection.close đều xử lý như nhau.

## 18. Các đoạn cleanup có thể tự gây tác dụng phụ

Đừng xem cleanup là đoạn code “không có logic”:

- Một **Writer.close()** có thể flush buffer.
- Một **ZipOutputStream.close()** có thể cần hoàn tất cấu trúc dữ liệu nén.
- Một session hoặc transaction API có thể yêu cầu commit/rollback riêng.
- Một handler release khóa có thể ảnh hưởng quyền truy cập của thread khác.
- Một callback cleanup có thể ghi log, gửi metrics hoặc hủy lịch công việc.

Nếu close/cleanup thất bại, trạng thái cuối có thể không rõ ràng. Một ứng dụng ghi file có thể đã ghi được một phần dữ liệu; một request gửi xa có thể đã được xử lý. Không ghi kết quả **SUCCESS** chỉ vì xử lý chính đi tới cuối, nếu hợp đồng vẫn yêu cầu cleanup/finalization thành công.

Tương tự, không đánh dấu mọi lỗi cleanup là **FATAL**. Mức nghiêm trọng phụ thuộc loại tài nguyên, giai đoạn sử dụng, hệ quả trên dữ liệu và tính khả năng phục hồi. Tốt nhất là có hợp đồng rõ ràng về thế nào là một thao tác “hoàn thành”.

## 19. Ghi log lỗi chính và lỗi dọn dẹp

Một ứng dụng thường mắc hai lỗi đối lập:

**Chỉ ghi lỗi đầu:**

~~~java
// Phản mẫu minh họa.
logger.error("Operation failed: " + failure.getMessage());
~~~

Cách này có thể bỏ qua suppressed từ close, cause và stack trace. Trong Java logging framework hỗ trợ throwable, nên truyền đối tượng lỗi đầy đủ:

~~~java
// Minh họa với logger có API error(String, Throwable).
logger.error("Operation failed", failure);
~~~

Đoạn logger phụ thuộc framework tương ứng, không phải class Java SE độc lập. Trong production, xác minh formatter thực sự hiển thị **getCause()**, **getSuppressed()** và stack trace; pipeline JSON có thể cần cấu hình riêng.

**Ghi log mọi catch rồi throw lại:** Cùng một lỗi có thể bị log ở nhiều tầng, dẫn tới đếm trùng sự cố. Thường nên giữ cause/suppressed khi truyền lỗi và log một lần ở boundary phù hợp, bổ sung correlation ID, resource identifier và operation name theo chính sách bảo mật.

Nếu suppressed nằm trên cause của một wrapper, chỉ nhìn **wrapper.getSuppressed()** có thể không thấy nó. Hãy đọc toàn bộ cây exception, không chỉ một cấp.

## 20. Kiểm thử từng nhánh thay vì chỉ kiểm tra happy path

Một unit test cleanup chỉ gọi phương thức trên đường thành công không chứng minh exception safety. Cần có tài nguyên giả cho phép điều khiển **open**, **work**, **close** để tái hiện rõ từng đường lỗi.

Ma trận kiểm thử tối thiểu:

| Mở tài nguyên | Công việc | Close | Kỳ vọng |
| --- | --- | --- | --- |
| Thành công | Thành công | Thành công | Kết quả bình thường, close được gọi |
| Thành công | Thất bại A | Thành công | A được ném, close đã thử |
| Thành công | Thành công | Thất bại B | B được ném; không công bố thành công giả |
| Thành công | Thất bại A | Thất bại B | A primary, B suppressed |
| A mở thành công; B mở lỗi C | Không chạy | A đóng thành công | C là lỗi chính, A đã được đóng |
| A mở thành công; B mở lỗi C | Không chạy | A đóng lỗi D | C primary, D suppressed |
| A và B mở thành công | Thất bại C | B và A đóng lỗi D/E | C primary, suppressed D rồi E |
| Thành công | Return sớm | Đóng lỗi B | Không return bình thường nếu close bắt buộc báo lỗi |
| Thành công | RuntimeException | Close thành công | RuntimeException còn được ném, resource được đóng |
| Thành công | Error | Close có thể lỗi | TWR vẫn theo nguyên tắc cleanup và suppressed; không dùng catch(Throwable) để nuốt Error |

Với unit test dùng JUnit, tốt nhất dùng **assertSame** (identity) để kiểm tra primary là đúng exception instance từ work, và **assertArrayEquals** hoặc so identity từng suppressed để kiểm tra thứ tự. Nếu chỉ kiểm tra **assertThrows(IOException.class)**, test có thể PASS ngay cả khi lỗi **work failed** bị thay bằng **close failed**.

Chương trình chạy ở mục 6 đã trình bày sáu đường lỗi có đầu ra dễ theo dõi. Test thực tế nên thêm những tình huống không lỗi, lỗi unchecked, interrupted caller và trạng thái tài nguyên theo hợp đồng.

### Kiểm tra cleanup được gọi đúng lần

Một tài nguyên test có thể đếm số lần close:

~~~java
// Mã minh họa theo ngữ cảnh.
final class CountingResource implements AutoCloseable {
    int closes;

    @Override
    public void close() {
        closes++;
    }
}
~~~

Ở nơi sở hữu đúng tài nguyên, assert **closes == 1** sau đường thành công hoặc lỗi. Nhưng đừng khẳng định mọi API thực tế đều phải close đúng một lần theo logic nội bộ của wrapper; một wrapper có thể đóng tài nguyên bên dưới hoặc tổ chức vòng đời riêng. Test cần mô phỏng hợp đồng đang được dùng, không chỉ đếm lệnh gọi.

## 21. Checklist review code có tài nguyên

Khi xem một pull request chứa file, stream, connection, lock, session hoặc handle, hãy hỏi:

1. **Ai sở hữu tài nguyên?** Phương thức hiện tại, đối tượng dài hạn hay caller?
2. **Tài nguyên được mở ở đâu?** Có thể phát sinh lỗi giữa những lần mở không?
3. **Nếu thao tác chính ném exception**, close có được thử không?
4. **Nếu xảy ra return/break/continue**, close có chạy trước khi thoát phạm vi không?
5. **Nếu close ném exception**, lỗi chính có bị che mất không?
6. **Nếu có nhiều tài nguyên**, close đầu thất bại có ngăn các lần close sau không?
7. **Thứ tự đóng có đúng không**, có đóng trùng một resource thông qua wrapper và biến nền không?
8. **Nếu một resource chưa mở xong**, code có tránh gọi close/unlock trên handle chưa sở hữu không?
9. **Có cần rollback/compensation riêng không**, hay tác giả đang nhầm close với khôi phục dữ liệu?
10. **Nếu cleanup lỗi**, trạng thái resource còn tin cậy không, có cần đánh dấu hoặc loại bỏ nó không?
11. **Nếu bị interrupt/cancel**, cleanup và trạng thái thread có được xử lý đúng không?
12. **Logger có giữ cause/suppressed không**, hay chỉ ghi message?
13. **Unit test có bơm lỗi vào open/work/close** và xác minh primary/suppressed, trạng thái trước/sau không?

**Ưu tiên sửa:** Với tài nguyên AutoCloseable thuộc quyền sở hữu phạm vi, thay các đoạn open/use/close thủ công bằng **try-with-resources**. Chỉ dùng finally thủ công cho API hoặc semantics thật sự khác, kèm đầy đủ xử lý lỗi và test.

## 22. Những sai lầm nối tiếp thường bị bỏ qua

**Sai lầm 1 — đưa close xuống cuối cùng rồi tin là đủ.** Exception/return trước đó sẽ bỏ qua close. Gắn close với phạm vi bằng TWR hoặc finally đúng hợp đồng.

**Sai lầm 2 — có finally nhưng phạm vi bắt đầu quá muộn.** Nếu tài nguyên thứ hai mở lỗi trước khi vào try, tài nguyên thứ nhất rò. Khai báo nhiều resource trong TWR hoặc quản lý từng acquisition ngay khi thành công.

**Sai lầm 3 — finally đóng nhiều tài nguyên bằng lệnh nối tiếp.** Lỗi ở lần close đầu có thể bỏ qua close sau. Dùng nhiều resource TWR với thứ tự khai báo hợp lý.

**Sai lầm 4 — close exception che exception công việc.** Có thể làm nhóm debug sửa sai lỗi. TWR giữ primary/suppressed theo cơ chế chuẩn.

**Sai lầm 5 — catch cleanup rồi bỏ qua.** Không biết kết quả thu hồi, flush hoặc transaction. Phải có lý do nếu bỏ qua một lỗi cụ thể.

**Sai lầm 6 — chỉ catch IOException quanh work.** RuntimeException/Error vẫn làm code nhảy khỏi đường cleanup thủ công. TWR không cần dự đoán mọi class lỗi.

**Sai lầm 7 — close cả handle chưa sở hữu.** Với lockInterruptibly, unlock sau khi acquisition thất bại có thể ném IllegalMonitorStateException. Xác lập ownership trước khi đưa unlock vào finally.

**Sai lầm 8 — trả về một tài nguyên đã đóng.** TWR sẽ đóng trước return; chỉ dùng nếu trả về dữ liệu đã đọc, không phải handle caller còn cần dùng.

**Sai lầm 9 — coi close là rollback.** Dữ liệu bị sửa dở có thể còn đó. Cần transaction, idempotency hoặc compensation khi có side effect.

**Sai lầm 10 — quên lỗi close ở cuối thao tác thành công.** Nếu close báo lỗi, không tự ghi nhận SUCCESS khi hợp đồng yêu cầu đóng/flush hoàn tất.

**Sai lầm 11 — retry close vô điều kiện.** Không phải AutoCloseable nào cũng idempotent. Xem contract tài nguyên.

**Sai lầm 12 — thiếu test lỗi kép.** Assert loại exception không đủ nếu work và close cùng ném IOException; phải kiểm tra primary và suppressed cụ thể.

## 23. Quy trình cải tiến một đoạn cleanup thủ công

Một cách refactor có kiểm soát:

**Bước 1: Liệt kê resources và ownership.** Nếu wrapper đã sở hữu resource nền, tránh tạo hai đường đóng có thể trùng. Xác định API nào implements AutoCloseable hoặc Closeable.

**Bước 2: Vẽ các điểm acquisition.** Với mỗi resource, ghi rõ thời điểm mở thành công và tất cả đường có thể ném trong quá trình mở tiếp.

**Bước 3: Thống kê exit paths.** Exception checked/unchecked, early return, loop control, timeout, interruption và nhánh bình thường.

**Bước 4: Chọn phạm vi TWR.** Đưa việc acquisition vào dấu ngoặc try nếu phù hợp để Java bảo đảm cleanup cho những resource đã mở thành công.

**Bước 5: Thiết lập thứ tự khai báo.** Nếu tài nguyên B phụ thuộc A, khai báo A trước B để B đóng trước A; kiểm tra contract thật của wrapper.

**Bước 6: Xác định exception contract.** Caller sẽ nhận primary, suppressed và checked exceptions từ close thế nào? Khi thành công về work nhưng close lỗi, có coi lời gọi là thất bại không?

**Bước 7: Xử lý state recovery riêng.** Với transaction hoặc thao tác có side effect, quyết định rollback/commit/compensation và lỗi của chính các bước đó.

**Bước 8: Tạo test tiêm lỗi.** Bao gồm work fail, close fail, acquisition fail và nhiều close fail. Verify exact identity, order và close attempts.

**Bước 9: Quan sát môi trường thật.** Đảm bảo logs hiển thị cause/suppressed, theo dõi tài nguyên mở lâu, file descriptor, connection pool và timeout.

**Bước 10: Dọn mã cũ.** Loại bỏ close thủ công dư thừa khi TWR đã sở hữu tài nguyên; không để hai cơ chế đóng cùng một object mà không có hợp đồng.

## 24. Câu hỏi tự kiểm tra

**Nếu return nằm trong try-with-resources, có thể bỏ qua close không?**

Không. Close chạy trước khi phương thức hoàn tất return. Nếu close ném lỗi, kết quả return dự kiến có thể bị thay bởi exception, đúng như ví dụ runnable.

**Nếu openB() lỗi khi openA() đã thành công, try-with-resources có đóng A không?**

Có. Tài nguyên mở thành công trước đó được đóng trên đường thất bại khởi tạo tài nguyên kế tiếp. Nếu close A cũng lỗi, lỗi close có thể suppressed vào lỗi khởi tạo.

**Nếu cả work và close cùng ném IOException, catch bên ngoài nhận lỗi nào?**

Với TWR và suppression hoạt động, lỗi work là primary, còn lỗi close nằm trong **getSuppressed()**. Với finally thủ công không bảo toàn lỗi, close có thể che work.

**Nếu close lỗi mà work thành công, có thể return thành công không?**

Còn tùy cách tổ chức API và hợp đồng, nhưng TWR sẽ truyền close exception thay vì hoàn tất return bình thường khi close báo lỗi. Đừng bỏ lỗi chỉ để báo success.

**Nếu có hai resource, tại sao phải đóng ngược thứ tự?**

Vì resource mở sau thường phụ thuộc resource mở trước; TWR đóng từ phải sang trái. Đây là quy tắc của cú pháp Java, nhưng thiết kế vẫn phải xác định ownership và tránh close trùng.

**Nếu finally có null check, đã xử lý đủ chưa?**

Chưa. Null check chỉ tránh dereference handle chưa được gán; không giải quyết close failure, lỗi kép, thứ tự nhiều tài nguyên hoặc side effect cần rollback.

**Dùng try-with-resources có tự rollback transaction không?**

Không. Nó gọi close theo vòng đời AutoCloseable. Transaction state/commit/rollback phụ thuộc API và cơ chế quản lý giao dịch. Cần chính sách riêng.

**Có cần catch(Throwable) để đảm bảo cleanup không?**

Không cần nếu tài nguyên phù hợp AutoCloseable và dùng TWR. Catch(Throwable) tùy tiện có thể nuốt Error nghiêm trọng. Nếu phải quản lý thủ công, cần xác định rõ propagation và không giấu exception.

## 25. Tóm tắt quyết định kỹ thuật

**Đóng tài nguyên thủ công thiếu nhánh thất bại** là bug khi mã chỉ đóng trên happy path hoặc chỉ xử lý một vài loại lỗi. Việc thêm finally có thể sửa rò tài nguyên, nhưng chưa chắc giữ được **lỗi chính** khi cleanup cũng lỗi. Một lần mở tài nguyên sau thất bại, một close trong chuỗi thất bại hoặc return sớm đều là những nhánh cần được kiểm thử.

Đối với tài nguyên **AutoCloseable**, **try-with-resources** là lựa chọn chuẩn vì nó xử lý những nhánh này ngay trong cấu trúc ngôn ngữ: đóng những tài nguyên đã mở thành công, đóng theo thứ tự ngược, không bỏ qua cleanup khi thân try lỗi/return, giữ exception công việc làm primary và các lỗi close phụ dưới dạng suppressed.

Với API cần **unlock, rollback, cancel, release** theo semantics riêng, vẫn cần cleanup thủ công có chủ đích. Khi đó đừng chỉ kiểm tra “finally có chạy không”; phải kiểm tra **trách nhiệm sở hữu, mọi đường thoát, lỗi trong cleanup, trạng thái dữ liệu sau thất bại và khả năng quan sát**. Kiểm thử lỗi kép và đường khởi tạo thất bại thường phát hiện những sai sót mà happy-path test không thể nhìn thấy.
