# Đọc `Caused by`, `Suppressed` và các frame được rút gọn trong Java stack trace

Khi một chương trình Java báo lỗi, stack trace thường chứa nhiều tầng ngoài dòng ngoại lệ đầu tiên: `Caused by`, `Suppressed` và dấu `... N more`. Đọc nhầm các thành phần này dễ dẫn đến sửa sai vị trí, bỏ qua lỗi gốc hoặc hiểu nhầm rằng log đã bị cắt. Bài học thuộc nhóm **Java Core – Exception / Chẩn đoán và ghi log**, sử dụng Java 17+.

Mục tiêu: đọc được cấu trúc của stack trace chuẩn do `Throwable.printStackTrace(...)` tạo ra, lần theo **chuỗi nguyên nhân**, hiểu **ngoại lệ bị suppressed** (đặc biệt trong `try-with-resources`), khôi phục ý nghĩa các **frame chung đã rút gọn**, rồi áp dụng một quy trình chẩn đoán và ghi log hữu ích.

## 1. Nhìn một stack trace như một đồ thị lỗi có ngữ cảnh

Một exception trong Java lưu nhiều thông tin khác nhau:

- **Loại ngoại lệ**: chẳng hạn `java.lang.IllegalStateException`.
- **Thông điệp**: đoạn mô tả sau dấu `:`; có thể là `null`.
- **Stack trace**: chuỗi các `StackTraceElement`, biểu thị ngăn xếp tại thời điểm stack trace được ghi nhận; thường có tên lớp, phương thức, tệp và dòng.
- **Cause**: nguyên nhân được nối bằng `Throwable.getCause()`, thông thường là một ngoại lệ bên dưới được bọc thành ngoại lệ có ngữ cảnh cao hơn.
- **Suppressed exceptions**: tập các ngoại lệ phụ lấy bằng `Throwable.getSuppressed()`. Chúng không thay thế cause và thường xuất hiện khi dọn dẹp tài nguyên lại thất bại.

Một bản in điển hình có cấu trúc sau. Đây là **stack trace minh họa**, tên file/số dòng phục vụ giải thích, không phải output được cam kết từ một chương trình cụ thể:

```text
java.lang.IllegalStateException: Không thể xử lý yêu cầu
    at app.OrderService.placeOrder(OrderService.java:52)
    at app.OrderController.submit(OrderController.java:31)
    Suppressed: java.io.IOException: Lỗi đóng bộ ghi
        at app.AuditWriter.close(AuditWriter.java:18)
        at app.OrderService.placeOrder(OrderService.java:52)
        ... 1 more
Caused by: java.lang.IllegalArgumentException: Mã đơn hàng rỗng
    at app.OrderParser.parse(OrderParser.java:14)
    at app.OrderService.placeOrder(OrderService.java:49)
    ... 1 more
```

Đọc theo các lớp ý nghĩa:

1. Dòng đầu cho biết **ngoại lệ đang được in**: `IllegalStateException` với thông điệp “Không thể xử lý yêu cầu”.
2. Các dòng `at ...` ngay sau đó là **stack frame của ngoại lệ ấy**. Trong ví dụ, luồng xử lý đi qua `OrderController.submit` rồi `OrderService.placeOrder`.
3. Nhánh thụt vào `Suppressed:` ghi một **lỗi phụ** trong quá trình đóng bộ ghi. Lỗi này không nhất thiết giải thích nguyên nhân chính của yêu cầu thất bại.
4. `Caused by:` nối tới **ngoại lệ nguyên nhân**: `IllegalArgumentException` về mã đơn hàng. Đây thường là nơi bắt đầu truy tìm điều kiện đầu vào sai.
5. `... 1 more` cho biết **một frame ở cuối stack của ngoại lệ con trùng với phần cuối stack của ngoại lệ bao ngoài trong cùng nhánh in** và đã được rút gọn; đây không phải “một lỗi nữa”.

Không nên mặc định rằng dòng ngoại lệ đầu tiên là **root cause**. Ngoại lệ ngoài cùng thường biểu diễn thao tác ứng dụng đang thất bại, còn các tầng nguyên nhân cho biết vì sao thao tác không thể hoàn tất.

## 2. Một stack frame chứa gì?

Một frame thường có dạng:

```text
at package.ClassName.methodName(FileName.java:123)
```

Ý nghĩa các phần:

| Thành phần | Vai trò |
|---|---|
| `package.ClassName` | Tên lớp có phương thức nằm trong stack |
| `methodName` | Phương thức của frame; có thể là `lambda$...` hoặc tên được sinh bởi compiler |
| `FileName.java` | Tên tệp nguồn nếu có thông tin debug tương ứng |
| `:123` | Dòng nguồn tương ứng nếu JVM có metadata dòng |
| Thứ tự các dòng `at` | Frame trên cùng gần vị trí ghi nhận stack nhất, các frame dưới là ngữ cảnh gọi phía ngoài |

Ví dụ:

```text
at com.example.repo.UserRepository.find(UserRepository.java:88)
at com.example.service.UserService.load(UserService.java:41)
at com.example.web.UserController.show(UserController.java:27)
```

Hướng đọc từ **trên xuống** là từ nơi ghi nhận lỗi ra phía các caller; đường gọi thực tế trước lỗi thường theo hướng ngược lại: `UserController.show` → `UserService.load` → `UserRepository.find`.

Một số dạng đặc biệt:

- `(Native Method)`: frame của phương thức native, thường không có số dòng Java.
- `(Unknown Source)`: không có tệp/dòng nguồn phù hợp để in.
- `lambda$...`, `invoke`, `run`, `execute`: các frame có thể do lambda, reflection, proxy hoặc framework tạo ra. Không phải tất cả đều là vị trí nên sửa.
- Một stack frame chỉ cho thấy **nơi điều khiển đi qua**, không chứng minh chính phương thức đó là nguyên nhân nghiệp vụ.
- Số dòng phụ thuộc phiên bản mã, tối ưu hóa, thông tin debug và stack được in; đừng áp số dòng từ một bản build lên phiên bản triển khai khác.

`Throwable.getStackTrace()` trả một mảng `StackTraceElement[]`. Mỗi phần tử có các phương thức như `getClassName()`, `getMethodName()`, `getFileName()`, `getLineNumber()` và `isNativeMethod()`. Tên module/class loader có thể được bổ sung ở bản in stack trace hiện đại; cấu trúc hiển thị có thể khác đôi chút theo phiên bản JDK và cơ chế logging.

### Ví dụ chạy độc lập: đọc frame bằng API, không phụ thuộc số dòng

Tạo tệp `TraceFramesDemo.java`:

```java
public class TraceFramesDemo {
    static void leaf() {
        throw new IllegalStateException("dữ liệu hỏng");
    }

    static void middle() {
        leaf();
    }

    public static void main(String[] args) {
        try {
            middle();
        } catch (IllegalStateException e) {
            System.out.println("type = "
                    + e.getClass().getSimpleName());
            System.out.println("message = " + e.getMessage());

            StackTraceElement[] frames = e.getStackTrace();
            for (int i = 0; i < Math.min(3, frames.length); i++) {
                System.out.println("frame " + i + " = "
                        + frames[i].getMethodName());
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac TraceFramesDemo.java
java TraceFramesDemo
```

Kết quả:

```text
type = IllegalStateException
message = dữ liệu hỏng
frame 0 = leaf
frame 1 = middle
frame 2 = main
```

Đầu ra được viết theo tên phương thức vì số dòng nguồn trong stack trace có thể thay đổi khi sửa ví dụ. `frames[0]` là frame gần nhất với vị trí exception được tạo trong `leaf`. Một `Throwable` được **tạo trước rồi ném lại sau** có thể giữ stack trace ở thời điểm khởi tạo thay vì vị trí ném lại; nếu cần ghi lại tại vị trí khác có API `fillInStackTrace()`, nhưng việc sửa stack trace làm thay đổi thông tin chẩn đoán và không nên làm tùy tiện.

## 3. `Caused by`: một ngoại lệ bọc ngữ cảnh cho ngoại lệ trước đó

Khi một tầng thấp ném lỗi, tầng cao có thể bọc nó vào loại exception có ý nghĩa với tầng đó:

```java
try {
    repository.load();
} catch (java.io.IOException cause) {
    throw new IllegalStateException("Không đọc được hồ sơ", cause);
}
```

Đây là **mảnh mã minh họa**: giả định `repository.load()` có thể ném `IOException`. Constructor có đối số `cause` tạo liên hệ tới lỗi ban đầu. Người đọc có thể lần theo:

```text
IllegalStateException: Không đọc được hồ sơ
Caused by: IOException: ...
```

`Caused by` là **quan hệ nguyên nhân được tác giả mã hoặc thư viện ghi nhận**, không phải JVM tự suy luận quan hệ logic giữa mọi lỗi. Nếu tầng trên tạo ngoại lệ mới mà **không truyền cause**, chuỗi có thể bị đứt dù trên thực tế có lỗi trước đó.

### Ví dụ độc lập: tạo và lần theo ba tầng `Caused by`

Tệp `CauseChainDemo.java`:

```java
public class CauseChainDemo {
    static void parse() {
        throw new IllegalArgumentException("id phải dương");
    }

    static void service() {
        try {
            parse();
        } catch (IllegalArgumentException e) {
            throw new IllegalStateException(
                    "không tải được người dùng", e);
        }
    }

    static void controller() {
        try {
            service();
        } catch (IllegalStateException e) {
            throw new RuntimeException(
                    "request thất bại", e);
        }
    }

    public static void main(String[] args) {
        try {
            controller();
        } catch (RuntimeException e) {
            int level = 0;
            for (Throwable current = e;
                    current != null;
                    current = current.getCause()) {
                System.out.println("level " + level + ": "
                        + current.getClass().getSimpleName()
                        + ": " + current.getMessage());
                level++;
            }
        }
    }
}
```

Chạy:

```bash
javac CauseChainDemo.java
java CauseChainDemo
```

Kết quả:

```text
level 0: RuntimeException: request thất bại
level 1: IllegalStateException: không tải được người dùng
level 2: IllegalArgumentException: id phải dương
```

Từ API, `e.getCause()` đi **một cấp** vào trong; lặp đến `null` tìm ngoại lệ sâu nhất trong *chuỗi cause*. `printStackTrace()` sẽ in cùng quan hệ bằng nhiều nhánh `Caused by:` và thường rút gọn các frame chung.

Không nhầm “ngoại lệ sâu nhất” với “vị trí duy nhất cần sửa” trong mọi hệ thống. Một `SocketTimeoutException` ở tầng sâu có thể là triệu chứng của sự cố mạng, thiếu tài nguyên hoặc deadline quá ngắn; phải xem cả ngữ cảnh request, thời gian chờ, các lần retry và log phụ cận. Tương tự, lỗi validate đầu vào có thể được phát hiện ở tầng thấp nhưng cần sửa dữ liệu gửi vào từ tầng cao.

### Cách giữ cause khi chuyển loại lỗi

Nên dùng constructor chấp nhận cause:

```java
throw new IllegalStateException("Không hoàn tất nghiệp vụ", original);
```

Thay vì:

```java
throw new IllegalStateException("Không hoàn tất nghiệp vụ");
```

Trong ví dụ, `original` là một `Throwable` đã bắt trong `catch`. Cách thứ hai làm mất liên kết nguyên nhân. Nếu thư viện cung cấp loại exception riêng, chọn constructor hoặc factory có khả năng bảo toàn cause. Các lệnh chỉ làm `throw original;` trong phạm vi thích hợp có thể giữ stack trace đang có, nhưng không thêm ngữ cảnh cao hơn.

Nếu dùng `initCause(...)`, chỉ có thể đặt cause trong trường hợp hợp lệ khi cause chưa được khởi tạo; thường nên ưu tiên constructor tường minh để tránh lỗi thiết lập hai lần.

## 4. `Suppressed`: những ngoại lệ phụ không làm mất lỗi chính

Một `Throwable` có thể chứa nhiều ngoại lệ **suppressed**, truy cập qua `getSuppressed()`. Quan hệ này khác `getCause()`:

- **Cause**: mô tả vì sao ngoại lệ hiện tại xảy ra; thông thường là chuỗi nguyên nhân.
- **Suppressed**: các lỗi bổ sung xảy ra trong khi đang xử lý, dọn dẹp hoặc đóng tài nguyên; chúng được gắn vào một exception hiện có để **bảo toàn cả lỗi chính lẫn lỗi phụ**.
- Một exception có thể đồng thời có **một cause** và **nhiều suppressed**.
- Các suppressed exception cũng có thể có cause/suppressed riêng; thông tin lỗi vì vậy là một **đồ thị có nhánh**, không chỉ danh sách tuyến tính.

Trường hợp phổ biến nhất là `try-with-resources`. Khi thân `try` đã ném exception, một hay nhiều lời gọi `close()` có thể cũng thất bại. Java giữ ngoại lệ của **thân `try` là primary exception** và đính kèm ngoại lệ từ `close()` vào mảng suppressed của primary.

### Ví dụ chạy độc lập: đóng hai tài nguyên đều thất bại

Tạo tệp `SuppressedResourcesDemo.java`:

```java
import java.io.IOException;

public class SuppressedResourcesDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            throw new IOException("đóng " + name + " thất bại");
        }
    }

    static void execute() throws Exception {
        try (Resource first = new Resource("first");
             Resource second = new Resource("second")) {
            throw new IllegalStateException("xử lý thất bại");
        }
    }

    public static void main(String[] args) {
        try {
            execute();
        } catch (Exception e) {
            System.out.println("primary = "
                    + e.getClass().getSimpleName()
                    + ": " + e.getMessage());

            for (Throwable suppressed : e.getSuppressed()) {
                System.out.println("suppressed = "
                        + suppressed.getClass().getSimpleName()
                        + ": " + suppressed.getMessage());
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac SuppressedResourcesDemo.java
java SuppressedResourcesDemo
```

Kết quả chính xác:

```text
primary = IllegalStateException: xử lý thất bại
suppressed = IOException: đóng second thất bại
suppressed = IOException: đóng first thất bại
```

Giải thích:

1. `try` khai báo `first` rồi `second`.
2. Thân `try` ném `IllegalStateException`; đây là primary exception.
3. Các tài nguyên được đóng **theo thứ tự ngược với thứ tự khai báo**: `second` trước, `first` sau.
4. Cả hai lần `close()` ném `IOException`, nhưng exception chính được giữ; lỗi đóng lần lượt được gắn bằng suppressed.
5. `getSuppressed()` trả về mảng theo thứ tự được thêm vào, nên output trong ví dụ thể hiện `second` trước `first`.

Điều này rất quan trọng trong xử lý I/O, JDBC, file/stream và các loại `AutoCloseable` khác. Nếu chỉ nhìn dòng đầu “xử lý thất bại” và bỏ toàn bộ `Suppressed`, có thể bỏ sót việc đóng tài nguyên không thành công. Ngược lại, nếu chỉ chăm chú vào suppressed, có thể bỏ qua lỗi thân `try` là nguyên nhân chính.

### Khi `close()` mới là lỗi đầu tiên

Nếu thân `try` **hoàn thành bình thường**, nhưng `close()` ném exception, lỗi từ thao tác đóng đầu tiên theo thứ tự đóng ngược có thể trở thành **primary**. Nếu các lần đóng tiếp theo cũng lỗi, chúng có thể bị suppressed vào primary này. Vì thế không thể suy rằng mọi `Suppressed` đều có ngoại lệ từ thân `try`; hãy xem thứ tự thực thi và ngoại lệ ngoài cùng.

Ví dụ minh họa:

```java
try (Resource first = new Resource("first");
     Resource second = new Resource("second")) {
    System.out.println("thân try thành công");
}
```

Giả sử `Resource` giống class trong ví dụ trên, hai lần `close()` đều ném `IOException`. Thứ tự đóng là `second` rồi `first`; lỗi `close()` của `second` trở thành primary, còn lỗi `close()` của `first` thành suppressed. Đây là **mảnh mã sử dụng lại Resource**, không phải chương trình độc lập.

### `addSuppressed(...)` để bảo toàn lỗi thủ công

Java cho phép gắn ngoại lệ phụ:

```java
try {
    doWork();
} catch (Exception primary) {
    try {
        cleanup();
    } catch (Exception cleanupFailure) {
        primary.addSuppressed(cleanupFailure);
    }
    throw primary;
}
```

Đây là **mảnh mã minh họa** trong một phương thức có `throws Exception`; `doWork()` và `cleanup()` là các hàm đã được ứng dụng định nghĩa. `Throwable.addSuppressed(...)` không cho phép tự suppress chính đối tượng (`self-suppression`) và không nhận `null`. Thông thường, hãy dùng `try-with-resources` thay vì viết lại logic quản lý close phức tạp.

**Đừng chuyển suppressed thành cause một cách máy móc.** Ngoại lệ đóng tài nguyên thường chỉ là **lỗi bổ sung xảy ra trong dọn dẹp**, không phải nguyên nhân của ngoại lệ ban đầu.

## 5. Cách đọc `... N more` chính xác

Trong stack trace do `Throwable.printStackTrace()` in, Java tìm những frame ở **cuối stack trace của một throwable con** (cause hoặc suppressed) giống với phần cuối stack trace của throwable **bao ngoài trực tiếp đang được in**. Thay vì lặp lại các frame giống nhau, trình in ghi:

```text
... 3 more
```

Ý nghĩa chính xác: **ba stack frame ở cuối nhánh con trùng với ba frame cuối của stack cha** và đã được lược bỏ khỏi phần in của nhánh con.

Đây là **rút gọn frame trùng nhau**, không phải:

- Ba ngoại lệ khác nữa.
- Ba dòng log bị mất vì vượt giới hạn.
- Ba vòng retry.
- Ba phần của root cause chưa được tìm thấy.
- Một lời khẳng định rằng exception không còn stack frame nào khác.

### Ví dụ sơ đồ minh họa

Giả sử stack trace của exception ngoài cùng:

```text
java.lang.IllegalStateException: service lỗi
    at demo.Service.load(Service.java:30)
    at demo.Controller.handle(Controller.java:20)
    at demo.Main.main(Main.java:10)
```

Stack đầy đủ của cause bên trong:

```text
java.lang.IllegalArgumentException: id sai
    at demo.Parser.parse(Parser.java:12)
    at demo.Service.load(Service.java:26)
    at demo.Controller.handle(Controller.java:20)
    at demo.Main.main(Main.java:10)
```

Hai frame cuối `Controller.handle(...)` và `Main.main(...)` là **suffix chung**, nên phần cause có thể được in như:

```text
Caused by: java.lang.IllegalArgumentException: id sai
    at demo.Parser.parse(Parser.java:12)
    at demo.Service.load(Service.java:26)
    ... 2 more
```

Để tái tạo **ý nghĩa** của nhánh cause, hãy đọc `... 2 more` bằng cách nối vào hai frame ở cuối stack cha tương ứng. Con số là **độ dài suffix chung** giữa hai stack trace trong cây in, không phải số frame phía trên bị rút tùy ý.

### Suppressed cũng có `... N more`

Dưới `Suppressed:`, quy tắc frame chung tương tự nhưng nhánh suppressed được thụt lề sâu hơn và so với stack enclosing của **nhánh cha đang in**. Đừng luôn so với frame của exception gốc cấp cao nhất nếu suppressed nằm sâu trong một cause.

Ví dụ cấu trúc:

```text
java.lang.IllegalStateException: xử lý lỗi
    at demo.Service.run(Service.java:27)
    at demo.Main.main(Main.java:7)
    Suppressed: java.io.IOException: đóng stream lỗi
        at demo.Stream.close(Stream.java:16)
        at demo.Service.run(Service.java:27)
        ... 1 more
Caused by: java.lang.IllegalArgumentException: đầu vào lỗi
    at demo.Parser.parse(Parser.java:9)
    at demo.Service.run(Service.java:21)
    ... 1 more
```

Ở đây `... 1 more` trong hai nhánh đều ám chỉ phần frame đuôi trùng với stack của exception bao ngoài tương ứng. Mỗi nhánh được rút gọn **độc lập**.

### Rút gọn mặc định khác với log bị truncate

`Throwable.printStackTrace(...)` **có quy tắc rút gọn frame trùng**. Một hệ thống logging có thể thêm cơ chế khác: giới hạn số dòng, chỉ in vài nguyên nhân cuối, che dữ liệu, cấu hình pattern `%ex{short}` hoặc cắt sự kiện log dài. Khi thấy stack trace mất đoạn **không có dạng `... N more` chuẩn**, hãy kiểm tra cấu hình logger/appender, giới hạn ingest, dịch vụ tập trung log và kích thước sự kiện.

Đối với `... N more` chuẩn, các frame ấy có thể suy ra từ stack cha trong **cùng bản in đầy đủ**; nếu bản in cha đã bị hệ thống log cắt, việc suy ra có thể không còn thực hiện được.

## 6. Thứ tự đọc stack trace thực tế

Một quy trình điều tra hiệu quả:

1. **Lấy đủ sự kiện log liên quan**: timestamp, tên dịch vụ, request/correlation ID, thread, phiên bản build, vị trí triển khai. Một stack trace đơn lẻ thường thiếu ngữ cảnh xảy ra lỗi.
2. **Đọc exception ngoài cùng**: thao tác cấp ứng dụng nào báo thất bại? Message mô tả điều kiện gì? Có dấu hiệu bọc lỗi giữa các layer không?
3. **Quét các nhánh `Caused by`**: xác định ngoại lệ ở tầng sâu có thông tin cụ thể nhất như SQL constraint, connection timeout, parse error, validation error hay I/O.
4. **Tìm frame do mình sở hữu** gần vị trí phát sinh lỗi: ưu tiên class/package ứng dụng so với frame wrapper chung trong framework, nhưng vẫn đọc ngữ cảnh gọi.
5. **Kiểm tra `Suppressed`**: có lỗi đóng tài nguyên, cleanup hoặc hoạt động phụ nào thất bại không? Chúng có làm vấn đề trầm trọng hơn không?
6. **Giải nghĩa `... N more`**: frame đuôi của từng nhánh có thể đã in ở stack cha; không bỏ qua các frame chung khi dựng lại đường gọi.
7. **Đối chiếu với mã và build đúng phiên bản**: số dòng trên production phải khớp artifact hoặc commit đang chạy.
8. **Kiểm tra dòng thời gian và tác động**: yêu cầu bị từ chối, tác vụ retry, tài nguyên chưa đóng, transaction rollback, dữ liệu đã ghi một phần hay không.
9. **Xác nhận giả thuyết bằng quan sát hoặc bài test có mục tiêu**: không sửa theo lớp exception duy nhất nếu điều kiện gây lỗi chưa được tái hiện.

Đọc cause sâu nhất trước **là mẹo hữu ích**, không phải quy tắc tuyệt đối. Một lỗi `NullPointerException` sâu có thể là bug cục bộ; một lỗi `IOException` sâu có thể là hệ quả của mất kết nối ở tầng mạng; một lỗi suppressed khác có thể báo dọn dẹp cũng bị lỗi. Cần xét cả cấu trúc lẫn bối cảnh.

## 7. In và duyệt nguyên nhân, suppressed bằng Java

`Throwable` hỗ trợ các API:

| API | Trả về/tác động | Lưu ý |
|---|---|---|
| `getMessage()` | Thông điệp | Có thể `null` |
| `getLocalizedMessage()` | Thông điệp cục bộ hóa nếu lớp triển khai hỗ trợ | Mặc định thường giống `getMessage()` |
| `getCause()` | Throwable nguyên nhân hoặc `null` | Theo chuỗi cause |
| `getSuppressed()` | Mảng các Throwable bị suppressed | Có thể rỗng |
| `getStackTrace()` | Mảng `StackTraceElement` | Là bản sao, có thể rỗng hoặc được thay đổi bằng API |
| `printStackTrace()` | In exception, frames, suppressed và cause | Mặc định dùng `System.err` |
| `printStackTrace(PrintStream)` | In vào stream được chỉ định | Ví dụ dùng `System.out` khi cần trình diễn |
| `addSuppressed(Throwable)` | Gắn lỗi phụ vào exception chính | Không tự gắn chính nó hoặc `null` |
| `setStackTrace(StackTraceElement[])` | Thay mảng stack trace lưu trong throwable | Chỉ khi có lý do đặc biệt, tránh làm mất thông tin thực |

Duyệt cause bằng `for (Throwable t = e; t != null; t = t.getCause())` đủ cho hầu hết exception Java thông thường. Nếu xây một **trình duyệt lỗi tổng quát** đọc các Throwable do plugin hoặc thư viện lạ tạo, nên có tập identity để tránh lặp vô hạn khi đồ thị ngoại lệ bất thường, và phân biệt cause/suppressed.

### Ví dụ độc lập: báo cáo từng nhánh bằng API

Tệp `ThrowableTreeDemo.java`:

```java
import java.io.IOException;

public class ThrowableTreeDemo {
    public static void main(String[] args) {
        IOException root = new IOException("không đọc được tệp");
        IllegalStateException primary =
                new IllegalStateException("không tải được dữ liệu", root);

        primary.addSuppressed(
                new IOException("đóng stream thất bại"));
        primary.addSuppressed(
                new IllegalArgumentException("định dạng log không hợp lệ"));

        System.out.println("primary = "
                + primary.getClass().getSimpleName());

        Throwable cause = primary.getCause();
        System.out.println("cause = "
                + cause.getClass().getSimpleName()
                + ": " + cause.getMessage());

        for (Throwable suppressed : primary.getSuppressed()) {
            System.out.println("suppressed = "
                    + suppressed.getClass().getSimpleName()
                    + ": " + suppressed.getMessage());
        }
    }
}
```

Chạy:

```bash
javac ThrowableTreeDemo.java
java ThrowableTreeDemo
```

Output:

```text
primary = IllegalStateException
cause = IOException: không đọc được tệp
suppressed = IOException: đóng stream thất bại
suppressed = IllegalArgumentException: định dạng log không hợp lệ
```

Ví dụ chứng minh **cause và suppressed cùng tồn tại** trên một exception. Khi in bằng `primary.printStackTrace(System.out)`, Java sẽ hiển thị thông tin chi tiết của cả hai nhánh cùng các frame. Nếu thêm `printStackTrace(...)` vào bài này, số dòng nguồn trong output phụ thuộc vị trí mã; vì vậy ví dụ trên dùng API để có kết quả chính xác và dễ so sánh.

## 8. Khi nào `Caused by` không xuất hiện?

Không phải stack trace nào cũng có `Caused by`:

- Ngoại lệ được tạo mà không có cause.
- Mã bọc exception nhưng quên `cause` trong constructor.
- Framework/logger đã cấu hình chỉ in outer exception hoặc chỉ in root cause.
- Log bị cắt, phân đoạn hoặc chỉ ghi `e.getMessage()`.
- Throwable được tạo/biến đổi khác thường và cause không còn được bảo toàn.
- Một exception chỉ mang suppressed mà không có cause.

Ví dụ ghi log không đủ:

```java
System.err.println(e.getMessage());
```

Dòng này chỉ in thông điệp và **không cung cấp stack trace, cause hay suppressed**. Kể cả khi message diễn giải rất hay, người đọc vẫn khó xác định code path và các nhánh lỗi đi kèm.

Nếu dùng logging framework, truyền **đối tượng Throwable** đúng overload của API để giữ toàn bộ stack. Ví dụ minh họa giả định `logger` có API SLF4J tương thích:

```java
logger.error("Không xử lý được yêu cầu", e);
```

Đây là **mảnh mã tích hợp**, không phải chương trình độc lập vì `logger` và thư viện chưa được khai báo. Tùy API logging, vị trí throwable trong tham số và cấu hình trình in khác nhau; hãy xem tài liệu logger đang dùng. Tránh chỉ ghi `logger.error("{}", e.getMessage())` nếu mục đích là chẩn đoán đầy đủ.

## 9. `printStackTrace()` và framework logging khác nhau ở đâu?

`Throwable.printStackTrace()` cung cấp bản in trực tiếp từ đối tượng ngoại lệ; mặc định là `System.err`. Nó hữu ích khi học, trong ví dụ nhỏ, hoặc khi khắc phục sự cố cục bộ.

Trong dịch vụ thực tế, logger thường cần cung cấp:

- **Ngữ cảnh có cấu trúc**: module, operation, request ID, trace ID, tên component, tình trạng retry, phiên bản triển khai.
- **Thời điểm và mức độ nghiêm trọng**: lỗi do dữ liệu không hợp lệ có thể khác lỗi mất DB nghiêm trọng.
- **Throwable đầy đủ**: cho phép cấu hình in cause, suppressed, frames.
- **Bảo vệ dữ liệu**: không ghi token, mật khẩu, key, thông tin nhạy cảm hay body request không được phép.
- **Giới hạn lặp và thu thập**: không ghi cùng một exception ở mọi layer tạo ra log trùng và làm khó tìm lỗi thực.

Một chiến lược hay dùng: ở tầng thấp, **ném lại với cause** và ngữ cảnh cần thiết; ở ranh giới ứng dụng chịu trách nhiệm xử lý thất bại, **ghi log một lần đủ thông tin**. Nếu tầng thấp thực sự xử lý phục hồi và không đẩy lỗi đi tiếp, có thể ghi log ở tầng đó, nhưng tránh nhân bản những log cùng sự kiện.

Stack trace có thể bộc lộ đường dẫn tệp, tên lớp, SQL, tham số hoặc giá trị trong message. Không xuất toàn bộ trace ra phản hồi công khai cho người dùng cuối; có thể gửi mã lỗi/correlation ID và lưu chi tiết trong hệ thống log được kiểm soát.

## 10. `getStackTrace()` không phải “nguyên nhân” và không thay `getCause()`

Một `StackTraceElement[]` chỉ mô tả một ngăn xếp gọi được ghi nhận. Nó không tự chỉ ra mọi ngoại lệ đã xảy ra. Ví dụ một wrapper được tạo trong `service()` sẽ có frame đầu ở `service()`, còn nguyên nhân được tạo trong `repository()` có frame đầu của riêng nó. Vì thế muốn biết **tại sao** wrapper xuất hiện cần `getCause()` chứ không chỉ frame đầu wrapper.

```text
Outer exception: IllegalStateException
  stack[0] = Service.load(...)
  cause    = IOException
                 stack[0] = Repository.read(...)
```

Khi gặp suppressed, tình huống tương tự:

```text
Primary exception: IllegalStateException
  cause         → IOException("đọc dữ liệu lỗi")
  suppressed[0] → IOException("đóng dữ liệu lỗi")
```

Hai nhánh `cause` và `suppressed` mang **những đường thực thi, thời điểm và trách nhiệm khác nhau**. Chúng có thể dùng chung các frame ở cuối do cùng được gọi từ một luồng xử lý.

Cũng không nên giả định nguyên nhân sâu nhất luôn có nhiều frame nhất. Mỗi Throwable có mảng stack khác nhau; Java có thể rút gọn frame khi in, nhưng đó chỉ là cách trình bày.

## 11. Phân tích stack trace dài có framework, proxy và bất đồng bộ

Stack trace trong ứng dụng Java hiện đại có thể chứa nhiều frame do framework hoặc thư viện:

```text
at java.base/java.util.concurrent.CompletableFuture$AsyncSupply.run(...)
at java.base/java.util.concurrent.ThreadPoolExecutor.runWorker(...)
at java.base/java.util.concurrent.ThreadPoolExecutor$Worker.run(...)
at java.base/java.lang.Thread.run(...)
```

Đây là **đoạn ví dụ dạng frame có thể gặp**, không bảo đảm mọi bản JDK có cùng lớp nội bộ, dòng nguồn hoặc thứ tự. Khi điều tra:

1. Tìm exception message và nguyên nhân cụ thể nhất.
2. Xác định frame đầu thuộc package ứng dụng **trong đúng nhánh Throwable đang đọc**.
3. Nhìn các frame gần đó để hiểu đường đi từ scheduler, executor, HTTP handler hoặc service.
4. Với async, lưu ý stack trace ghi tại thời điểm Throwable được tạo/điền stack, **không thể tự khôi phục đầy đủ chuỗi caller đã submit task trước đó**.
5. Nếu cần lần theo công việc xuyên thread, bổ sung request ID, trace/span ID, context propagation và logging có cấu trúc.

Một `CompletionException` hoặc `ExecutionException` thường là **wrapper** báo rằng một tác vụ bất đồng bộ đã hoàn thành thất bại:

```text
java.util.concurrent.CompletionException: java.io.IOException: ...
Caused by: java.io.IOException: ...
```

Khi `CompletableFuture.join()` gặp exceptional completion thường có `CompletionException` ở phía quan sát; với `Future.get()` hoặc `CompletableFuture.get()`, caller có thể thấy `ExecutionException`. Đừng sửa code chỉ vì thấy wrapper; hãy kiểm tra cause để biết lỗi bên trong worker hoặc pipeline. Các trường hợp cancellation và interrupt ở caller cần phân biệt riêng với lỗi của worker.

Trong async, exception được bọc thêm một tầng không làm mất chuỗi nguyên nhân nếu cause được giữ đúng. Nhưng stack của từng Throwable có thể xuất hiện ở thread khác nhau; không nên ghép tất cả frame thành một lời gọi đồng bộ liên tục.

## 12. Một số tình huống điều tra cụ thể

### Tình huống A: request báo lỗi service, root cause là dữ liệu đầu vào

```text
java.lang.IllegalStateException: Không tạo được hóa đơn
    at app.InvoiceService.create(InvoiceService.java:70)
Caused by: java.lang.NumberFormatException: For input string: "abc"
    at java.base/java.lang.Integer.parseInt(Integer.java:...)
    at app.InvoiceParser.parseId(InvoiceParser.java:24)
    ... 1 more
```

Đây là **log minh họa**, dấu `...` trong số dòng của lớp JDK không phải output literal chuẩn. Nếu lỗi xảy ra khi parse `"abc"` thành số, chỗ sửa có thể là xác thực đầu vào, thông báo lỗi cho caller hoặc quy tắc mapping. Cần đối chiếu `InvoiceParser.parseId` và dữ liệu thực, không suy từ `IllegalStateException` ngoài cùng rằng state của JVM hỏng.

### Tình huống B: thao tác đã lỗi, đóng tài nguyên cũng lỗi

```text
java.lang.IllegalStateException: Ghi báo cáo thất bại
    at app.ReportService.write(ReportService.java:55)
    Suppressed: java.io.IOException: Đóng output thất bại
        at app.ReportFile.close(ReportFile.java:20)
        ... 1 more
Caused by: java.io.IOException: Ghi tệp thất bại
    at app.ReportFile.write(ReportFile.java:15)
    ... 1 more
```

Cần kiểm tra **hai vấn đề**: vì sao ghi thất bại (cause), và liệu cleanup/close thất bại có để lại tài nguyên hoặc dữ liệu dở dang hay không (suppressed). Nếu chỉ sửa `close()`, lỗi ghi ban đầu có thể vẫn xảy ra.

### Tình huống C: `... N more` làm người đọc tưởng thiếu tầng lỗi

```text
Caused by: java.lang.IllegalArgumentException: id rỗng
    at app.Parser.readId(Parser.java:18)
    ... 4 more
```

Trong bản in chuẩn, các frame chung đã có ở **stack cha** của nhánh ấy. Nếu còn đủ bản in, đọc bốn frame cuối của parent để dựng bối cảnh. Nếu hệ thống logging chỉ thu dòng `Caused by` này mà không có parent, cần lấy **sự kiện log đầy đủ**, không thể đoán chắc bốn frame từ riêng dòng rút gọn.

### Tình huống D: logger chỉ in thông điệp

```text
Không xử lý được request: connection refused
```

Không đủ dữ liệu để phân biệt lỗi socket, lỗi wrapper, vị trí gọi và suppressed. Nếu có stack trace gốc, hãy dùng logging API nhận Throwable và bổ sung correlation ID; tránh vội sửa `catch` bằng cách nuốt lỗi.

## 13. Những lỗi phổ biến khi đọc hoặc ghi log

### Chỉ đọc dòng đầu

Dòng đầu có thể là wrapper như `CompletionException` hoặc `IllegalStateException` của service. Nên lần theo `Caused by`, đọc frame của ngoại lệ gốc và ngữ cảnh request. Tuy nhiên root cause sâu nhất chưa chắc là kết luận cuối cùng.

### Đọc `Suppressed` như root cause

Suppressed là **nhánh lỗi phụ**; trong `try-with-resources`, nó thường là lỗi `close()` xảy ra **sau khi** thân `try` thất bại. Cần điều tra cả primary lẫn cleanup, không đảo quan hệ bằng suy đoán.

### Đọc `... 2 more` thành “còn hai lỗi nữa”

Nó nói có **hai frame ở đuôi trùng với frame đuôi của enclosing stack trace**, được rút gọn. Các exception khác chỉ thể hiện bằng những nhánh Throwable như `Caused by` hoặc `Suppressed`.

### Giữ message nhưng quên cause khi bọc exception

Sai:

```java
throw new IllegalStateException("Tải dữ liệu thất bại");
```

Nếu đang bọc một ngoại lệ vừa bắt, hãy dùng constructor có `cause`. Chỉ tạo message mới thường làm đứt nguồn gốc lỗi và khiến log nhìn như exception bắt đầu ở service.

### Ghi log ở mọi `catch` rồi ném lại

Mỗi tầng ghi cùng stack gây log storm, tăng phí thu thập và khó nhóm lỗi. Nên gắn ngữ cảnh, giữ cause và để tầng chịu trách nhiệm xử lý ghi log một lần khi có thể.

### Đổ lỗi cho frame của framework

Stack có thể có nhiều frame của Spring, servlet, executor hoặc reflection. Chúng cho biết ngữ cảnh chạy, không tự động chứng minh framework có bug. Chọn frame ứng dụng phù hợp và đọc nguyên nhân.

### Tin tuyệt đối số dòng khi build đã thay đổi

Dòng trong exception phản ánh class được biên dịch và debug metadata thực tế. Nếu CI/CD thay đổi source, so với sai commit dễ sửa nhầm chỗ. Giữ version/commit ID của artifact trong log.

### Bỏ qua suppressed khi close hoặc rollback thất bại

Cleanup lỗi có thể làm rò tài nguyên hoặc để dữ liệu ở trạng thái không mong muốn. Đừng biến mọi suppressed thành cảnh báo vô hại; đánh giá theo tính chất tài nguyên.

### Tự cắt stack trace bằng xử lý chuỗi

Cắt `stackTraceString` theo số dòng có thể mất cause hoặc suppressed. Dùng logger/appender có cấu hình phù hợp, giữ event đầy đủ ở nơi đủ quyền và chỉ rút gọn có kiểm soát ở bề mặt hiển thị.

### Ghi nguyên stack trace cho người dùng cuối

Stack có thể tiết lộ package nội bộ, tên file, câu truy vấn, endpoint, metadata và dữ liệu trong thông điệp. Tách thông báo công khai ra khỏi chi tiết log nội bộ, dùng mã lỗi để hỗ trợ đối chiếu.

## 14. Bài tập đọc stack trace và đáp án

Xem bản in minh họa:

```text
java.lang.IllegalStateException: Không xuất được CSV
    at export.CsvService.export(CsvService.java:40)
    at export.Main.main(Main.java:10)
    Suppressed: java.io.IOException: Lỗi đóng writer
        at export.CsvWriter.close(CsvWriter.java:21)
        at export.CsvService.export(CsvService.java:40)
        ... 1 more
Caused by: java.lang.IllegalArgumentException: Thiếu tên cột
    at export.CsvValidator.check(CsvValidator.java:15)
    at export.CsvService.export(CsvService.java:36)
    ... 1 more
```

Các câu hỏi và câu trả lời:

1. **Exception ngoài cùng?** `IllegalStateException`, thông điệp “Không xuất được CSV”.
2. **Nguyên nhân được khai báo?** `IllegalArgumentException` về tên cột, được nối bằng `Caused by`.
3. **Lỗi phụ?** `IOException` khi đóng writer, được gắn qua `Suppressed`.
4. **Có mấy tầng cause được in?** Một cause trực tiếp trong ví dụ; không đếm suppressed là cause.
5. **`... 1 more` có nghĩa gì?** Mỗi nhánh con rút gọn một frame đuôi trùng với stack enclosing của nó.
6. **Nên kiểm tra code nào?** `CsvValidator.check`, luồng gọi `CsvService.export`, và `CsvWriter.close`; ngoài ra kiểm tra đầu vào CSV và chính sách đóng writer.
7. **Có chứng cứ lỗi close là nguyên nhân thiếu tên cột?** Không. Hai nhánh thể hiện hai lỗi khác nhau trong luồng xử lý.

## 15. Checklist chẩn đoán và ghi log

Trước khi khép lại một incident Java, kiểm tra:

- Đã đọc **exception type + message** của outer exception và mọi `Caused by` quan trọng chưa?
- Đã tìm **frame ứng dụng** và đối chiếu mã nguồn của đúng bản build chưa?
- Đã đọc `Suppressed` và xác định lỗi cleanup có hậu quả riêng không?
- Đã giải nghĩa `... N more` là **frame chung được rút gọn** chưa?
- Log có đầy đủ Throwable, thời gian, thread, request/trace ID và ngữ cảnh cần thiết không?
- Có thể phân biệt exception trong worker với wrapper `ExecutionException`/`CompletionException` ở caller không?
- Có vô tình mất cause khi chuyển exception, hoặc in log trùng tại nhiều tầng không?
- Có dữ liệu nhạy cảm nào trong message, stack trace hoặc ngữ cảnh log cần che đi không?
- Đã kiểm tra tác động thực tế (giao dịch, tệp, tài nguyên, retry) ngoài thông điệp lỗi chưa?

**Ghi nhớ:** `Caused by` nối **nguyên nhân**, `Suppressed` giữ **những lỗi phụ**, còn `... N more` rút gọn **các stack frame trùng ở đuôi**. Đọc cả ba thành phần trong đúng nhánh Throwable rồi đối chiếu với mã nguồn, bản build và ngữ cảnh sự kiện mới có thể đưa ra kết luận chẩn đoán đáng tin.
