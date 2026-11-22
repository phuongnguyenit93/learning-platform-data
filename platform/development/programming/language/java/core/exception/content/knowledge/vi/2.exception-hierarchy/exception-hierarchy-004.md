# Checked exception trong Java: quy tắc bắt hoặc khai báo

Checked exception là ngoại lệ mà trình biên dịch Java yêu cầu mã nguồn **xử lý bằng `catch` hoặc khai báo bằng `throws`** khi một lời gọi, biểu thức hay câu lệnh có khả năng phát sinh nó. Quy tắc này thường được gọi là **catch-or-declare** (hoặc catch-or-specify). Nó giúp hợp đồng của phương thức cho người gọi biết những tình huống thất bại cần cân nhắc, chẳng hạn đọc tệp, truy cập dữ liệu hoặc chờ một luồng.

Sau bài này, bạn cần biết cách nhận diện checked exception từ cây kế thừa, giải thích lỗi biên dịch `unreported exception`, chọn đúng giữa xử lý tại chỗ và chuyển trách nhiệm lên tầng gọi, đồng thời áp dụng quy tắc cho phương thức, constructor, overriding và lambda.

## 1. Vị trí trong phân cấp ngoại lệ

~~~text
java.lang.Throwable
├── java.lang.Error                         (unchecked)
│   └── ...                                 (unchecked)
└── java.lang.Exception                     (checked)
    ├── java.io.IOException                 (checked)
    │   ├── java.io.FileNotFoundException   (checked)
    │   └── ...
    ├── java.sql.SQLException               (checked)
    ├── java.lang.InterruptedException      (checked)
    └── java.lang.RuntimeException          (unchecked)
        ├── NullPointerException            (unchecked)
        ├── IllegalArgumentException        (unchecked)
        └── ...
~~~

- **Checked:** những lớp con của `Throwable` mà **không** thuộc nhánh `RuntimeException` hay `Error`. Vì vậy chính `Exception` (ngoại trừ nhánh runtime), `IOException`, `SQLException`, `ClassNotFoundException` và `InterruptedException` đều có cơ chế kiểm tra ở thời điểm biên dịch.
- **Unchecked:** `RuntimeException`, `Error` và các lớp con của chúng. Có thể bắt hoặc khai báo, nhưng trình biên dịch không bắt buộc làm vậy.
- Cả checked và unchecked đều chỉ **thực sự phát sinh khi chương trình chạy**; sự khác biệt là Java có yêu cầu tĩnh về `catch`/`throws` đối với checked exception.

Ví dụ API: `Files.readString(path)` khai báo `IOException`; `Thread.sleep(millis)` khai báo `InterruptedException`; `Integer.parseInt(text)` có thể ném `NumberFormatException` (unchecked). Đừng suy đoán loại ngoại lệ qua tên thao tác: đọc chữ ký phương thức và Javadoc.

## 2. Quy tắc catch-or-declare hoạt động ra sao?

Giả sử một phương thức có thể ném `IOException`:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

// Đoạn minh họa đặt bên trong một lớp.
static String read(Path file) throws IOException {
    return Files.readString(file);
}
~~~

Mọi phương thức gọi `read(file)` phải chọn một trong hai cách:

1. **Bắt (`catch`):** đặt lời gọi trong `try` và cung cấp `catch (IOException ex)` hoặc một kiểu cha phù hợp. Lúc đó trách nhiệm xử lý đã được giải quyết tại đây, trừ khi bạn chủ động ném tiếp.
2. **Khai báo (`throws`):** thêm `throws IOException` (hoặc kiểu cha thích hợp, chẳng hạn `Exception`) vào chữ ký phương thức gọi. Ngoại lệ nếu phát sinh sẽ tiếp tục truyền đến người gọi của phương thức đó; tầng tiếp theo lại phải bắt hoặc khai báo.

Hai cách có thể cùng tồn tại: một phương thức bắt `FileNotFoundException`, nhưng vẫn khai báo `IOException` cho những lỗi I/O còn lại. Compiler theo dõi **kiểu ngoại lệ có thể phát sinh theo mã nguồn**; có `throws` không có nghĩa phương thức luôn ném ngoại lệ.

### Ví dụ không hợp lệ

~~~java
// Minh họa lỗi biên dịch; không phải một chương trình Java độc lập.
static String invalidRead(Path file) {
    return Files.readString(file);
}
~~~

Vì `Files.readString` khai báo `IOException` nhưng phương thức trên không bắt và không khai báo, `javac` sẽ báo lỗi chứa thông điệp tương tự `unreported exception java.io.IOException; must be caught or declared to be thrown`. Việc gọi đến đoạn mã lỗi chưa xảy ra cũng không giúp vượt qua kiểm tra biên dịch.

## 3. Ví dụ hoàn chỉnh: chuyển lên tầng gọi rồi bắt ở ranh giới ứng dụng

Tạo tệp `CatchOrDeclareDemo.java`:

~~~java
import java.io.IOException;

public class CatchOrDeclareDemo {
    static String readConfiguration() throws IOException {
        throw new IOException("thiếu config.properties");
    }

    static String startService() throws IOException {
        return readConfiguration();
    }

    public static void main(String[] args) {
        try {
            System.out.println(startService());
        } catch (IOException ex) {
            System.out.println("Không khởi động: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac CatchOrDeclareDemo.java
java CatchOrDeclareDemo
~~~

Đầu ra chính xác:

~~~text
Không khởi động: thiếu config.properties
~~~

Diễn giải luồng thực thi:

1. `readConfiguration()` thực hiện `throw new IOException(...)`. Từ khóa `throw` **ném một đối tượng ngoại lệ**; `throws IOException` ở chữ ký **khai báo khả năng ném**.
2. `startService()` không bắt nên phải khai báo `throws IOException`. Ngoại lệ đi từ `readConfiguration` qua `startService` lên `main`.
3. `main()` bắt `IOException`, chọn thông báo phù hợp và tiếp tục đến cuối chương trình. Câu lệnh in kết quả bình thường trong khối `try` bị bỏ qua khi ngoại lệ xuất hiện.

Nếu đổi `main` thành `public static void main(String[] args) throws IOException` và gọi trực tiếp `startService()`, mã vẫn **biên dịch**, nhưng vì không có tầng Java nào ở đây bắt ngoại lệ, ứng dụng sẽ kết thúc bất thường và JVM thường in stack trace. Khai báo `throws` không đồng nghĩa với việc lỗi đã được phục hồi.

Trong thực tế, `readConfiguration()` có thể dùng `Files.readString(Path.of("config.properties"))` thay vì ném ngoại lệ cố định. Khi dùng đường dẫn thật, kết quả thành công/thất bại sẽ phụ thuộc vào hệ thống tệp và quyền truy cập.

## 4. Chọn `catch` hay `throws`?

| Tình huống | Thường chọn | Lý do |
| --- | --- | --- |
| Lớp giao tiếp người dùng có thể yêu cầu chọn tệp khác | `catch` | Có phương án phục hồi cụ thể. |
| Hàm tiện ích đọc tệp không biết cách báo lỗi cho người dùng | `throws IOException` | Giữ nguyên thông tin thất bại cho tầng quyết định. |
| Tầng dịch vụ cần bổ sung ngữ cảnh nghiệp vụ | Bắt rồi ném ngoại lệ phù hợp, kèm `cause` | Người gọi hiểu đang thất bại ở thao tác nào. |
| Luồng bị ngắt khi chờ | Khai báo `InterruptedException` hoặc bắt và khôi phục cờ ngắt | Tôn trọng yêu cầu hủy/ngắt công việc. |
| Lỗi lập trình như đối số sai, truy cập `null` | Sửa nguyên nhân; unchecked nếu cần biểu diễn vi phạm hợp đồng | Không cần ép quy trình catch-or-declare. |

Nguyên tắc: **bắt ở nơi có thể quyết định phải làm gì với lỗi**; nếu chưa thể xử lý hợp lý, thường nên khai báo hoặc chuyển thành ngoại lệ có ngữ cảnh và giữ nguyên nguyên nhân. Tránh `catch (Exception ex) { }` vì nó nuốt lỗi, khiến thao tác phía sau tưởng rằng mọi việc thành công. Cũng tránh chỉ `printStackTrace()` rồi trả về dữ liệu giả như thể đọc thành công.

`throws Exception` và `catch (Exception ex)` hợp lệ về mặt ngôn ngữ, nhưng làm mờ loại lỗi mà API muốn công bố và dễ bắt cả lỗi lập trình không mong đợi. Ưu tiên loại checked exception đủ cụ thể, trừ khi API thực sự có hợp đồng rộng.

## 5. Những quy tắc quan trọng về phạm vi và kiểu

### Kiểu cha, kiểu con và nhiều ngoại lệ

- `catch (IOException ex)` cũng xử lý các lớp con như `FileNotFoundException`, `NoSuchFileException` khi chúng phát sinh.
- Khi có nhiều `catch`, đặt kiểu **cụ thể trước, tổng quát sau**. Nếu đặt `catch (IOException)` trước `catch (FileNotFoundException)`, nhánh phía sau không thể được chọn và trình biên dịch báo lỗi.
- Một phương thức có thể khai báo `throws IOException, SQLException`. Người gọi phải bao phủ cả hai bằng các `catch` thích hợp hoặc tiếp tục khai báo.
- Có thể dùng multi-catch `catch (IOException | SQLException ex)` khi các kiểu là những lựa chọn không có quan hệ kế thừa với nhau. Không viết `IOException | FileNotFoundException`: kiểu thứ hai là con của kiểu thứ nhất.
- `catch` không tự động bắt mọi `Throwable`: chỉ các đối tượng tương thích với kiểu đã khai báo mới khớp; một ngoại lệ chưa được bắt sẽ truyền ra ngoài.

Ví dụ bắt cụ thể trước tổng quát (đoạn minh họa đặt trong phương thức có biến `Path file`):

~~~java
try {
    String content = Files.readString(file);
    System.out.println(content);
} catch (java.nio.file.NoSuchFileException ex) {
    System.out.println("Không tìm thấy tệp được yêu cầu.");
} catch (IOException ex) {
    System.out.println("Không thể đọc tệp: " + ex.getMessage());
}
~~~

Trường hợp `IOException` không thể phát sinh từ khối `try` theo phân tích của compiler mà bạn vẫn viết `catch (IOException)`, Java có thể báo lỗi kiểu `exception IOException is never thrown in body of corresponding try statement`. Vì vậy không thêm `catch` chỉ để “cho đủ”, đặc biệt với checked exception.

### `throws` và hợp đồng của phương thức

Đối với checked exception, lời khai báo trong một phương thức/constructor là phần của **hợp đồng API**: những nơi gọi nó phải chuẩn bị xử lý. `throws IOException` cho phép khai báo kiểu cha của `FileNotFoundException` vì người gọi bắt `IOException` cũng bao trùm kiểu con.

Một phương thức có thể khai báo checked exception dù nhánh thực thi hiện tại không thật sự ném nó. Tuy nhiên, đừng khai báo rộng hoặc không liên quan nếu không có lý do về hợp đồng. Trong thiết kế API, loại checked exception cụ thể giúp người dùng xác định cách phục hồi.

### Ghi đè (`override`) và triển khai interface

Phương thức ghi đè **không được thêm checked exception mới hoặc rộng hơn** so với phương thức bị ghi đè; nó có thể không khai báo, hoặc khai báo loại checked hẹp hơn được hợp đồng cha cho phép. Ví dụ sau là hợp lệ:

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;

interface Repository {
    String load() throws IOException;
}

class TextRepository implements Repository {
    @Override
    public String load() throws FileNotFoundException {
        return "demo";
    }
}
~~~

Nếu `TextRepository.load()` khai báo `throws Exception` hoặc `throws SQLException`, mã không hợp lệ vì hợp đồng `Repository.load()` chỉ cho phép `IOException` và các kiểu con của nó. Ngoại lệ unchecked không chịu giới hạn `throws` này. Khi một lớp triển khai nhiều interface có cùng chữ ký, phải thỏa mãn tất cả hợp đồng liên quan.

### Constructor, initializer và lambda

- Constructor chịu nguyên tắc bắt/khai báo giống phương thức. Nếu lời gọi `new FileInputStream(path)` có thể ném `FileNotFoundException`, constructor chứa lời gọi cũng phải xử lý hoặc khai báo.
- Mã khởi tạo đối tượng/khối khởi tạo có quy tắc riêng theo ngữ cảnh; không thể tùy ý ném checked exception ra khỏi static initializer bằng một `throws` gắn lên khối. Đối với instance initializer, phải xét các constructor liên quan.
- Lambda và method reference cũng được compiler kiểm tra theo hợp đồng `throws` của phương thức trừu tượng mà functional interface khai báo. `Runnable.run()` không khai báo checked exception, nên không thể trực tiếp ném `IOException` từ lambda gán cho `Runnable`. Ngược lại, `Callable.call()` khai báo `throws Exception`, vì vậy có thể viết:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.Callable;

// Đoạn minh họa trong một phương thức.
Callable<String> task = () -> Files.readString(Path.of("config.properties"));
~~~

Lambda trên chỉ **tạo tác vụ**, chưa đọc tệp tại thời điểm khai báo. Khi tác vụ được gọi, `Callable.call()` có thể ném checked exception. Tương tự, các hàm trong Stream như `Function.apply` không khai báo checked exception, nên `stream.map(x -> Files.readString(x))` không biên dịch nếu không có xử lý phù hợp.

## 6. Kết hợp try-with-resources với checked exception

Một thao tác I/O có thể lỗi lúc **mở**, **đọc** hoặc **đóng** tài nguyên. `try-with-resources` đảm bảo gọi `close()` khi rời khối `try`, kể cả khi đang xử lý ngoại lệ.

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

// Đoạn minh họa đặt trong một lớp.
static String firstLine(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
~~~

`Files.newBufferedReader`, `reader.readLine` và `reader.close` có thể tạo ra `IOException`; `throws IOException` ở `firstLine` bao phủ trách nhiệm của cả thao tác đọc lẫn đóng. Nếu khối xử lý và lệnh đóng cùng ném lỗi, lỗi từ đóng thường được gắn dưới dạng **suppressed exception** của lỗi chính trong cơ chế try-with-resources; kiểm tra bằng `getSuppressed()` khi cần chẩn đoán. Đừng tự đóng tài nguyên trong `finally` một cách cẩu thả, vì lỗi khi đóng có thể che mất lỗi gốc.

`finally` hữu ích cho dọn dẹp logic không dựa trên `AutoCloseable`, nhưng không thay thế được quy tắc bắt/khai báo checked exception. Hơn nữa, `return` hoặc `throw` trong `finally` có thể che khuất kết quả/ngoại lệ phát sinh trước đó, nên cần tránh.

## 7. Chuyển đổi và bảo toàn nguyên nhân của ngoại lệ

Đôi khi một tầng cần công bố lỗi ở mức khái niệm khác. Bạn có thể tạo một checked exception riêng bằng cách kế thừa `Exception`, rồi truyền ngoại lệ gốc làm `cause`:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class ConfigurationException extends Exception {
    ConfigurationException(String message, Throwable cause) {
        super(message, cause);
    }
}

class ConfigurationLoader {
    static String load(Path path) throws ConfigurationException {
        try {
            return Files.readString(path);
        } catch (IOException ex) {
            throw new ConfigurationException("Không đọc được cấu hình: " + path, ex);
        }
    }
}
~~~

Ở đây `ConfigurationLoader.load` **không cần khai báo `IOException`** vì đã bắt nó; thay vào đó, nó phải khai báo `ConfigurationException` mới được ném. Người gọi `load` lại có trách nhiệm bắt hoặc khai báo ngoại lệ checked mới. `getCause()` giữ `IOException` gốc để phục vụ chẩn đoán.

Nếu bắt buộc thích ứng với API không cho khai báo checked exception (ví dụ một functional interface), có thể chuyển một `IOException` thành `UncheckedIOException` với `cause` đầy đủ, nhưng đó là lựa chọn thiết kế có chủ đích; người gọi lúc này không còn được compiler buộc xử lý. Đừng âm thầm nuốt lỗi hoặc biến tất cả ngoại lệ thành `RuntimeException` chỉ để mã biên dịch.

## 8. Trường hợp đặc biệt: InterruptedException

`Thread.sleep`, `Object.wait` và nhiều thao tác chặn khác có thể ném `InterruptedException` (checked). Cách ưu tiên ở tầng có thể chuyển tiếp là khai báo `throws InterruptedException` để người gọi quyết định hủy tác vụ.

Nếu một phương thức không thể khai báo và phải bắt ngoại lệ này, thông thường cần **khôi phục trạng thái ngắt** để mã ở tầng trên nhận ra tín hiệu:

~~~java
// Đoạn minh họa là phương thức bên trong một lớp.
static void pauseBriefly() {
    try {
        Thread.sleep(100);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return;
    }
}
~~~

`Thread.sleep` sẽ xóa cờ interrupted khi ném `InterruptedException`; gọi lại `interrupt()` phục hồi tín hiệu cho logic kiểm tra sau đó. Trong chương trình có vòng lặp tác vụ, sau khi phục hồi cờ ngắt nên kết thúc hoặc chuyển quyền xử lý, tránh tiếp tục chạy vô hạn. Không dùng lại cách này một cách máy móc với mọi `IOException` vì mục đích ngữ nghĩa khác nhau.

## 9. Lỗi thường gặp và cách sửa

| Sai sót | Hệ quả | Cách sửa |
| --- | --- | --- |
| Gọi phương thức khai báo checked exception mà không có `catch`/`throws` | Lỗi biên dịch `unreported exception` | Bắt đúng kiểu hoặc khai báo ở phương thức chứa lời gọi. |
| Nhầm `throw` và `throws` | Tưởng khai báo là đã xử lý lỗi | `throw` thực hiện ném; `throws` mô tả hợp đồng. |
| Chỉ thêm `throws Exception` ở mọi lớp | API mất thông tin cụ thể, đẩy trách nhiệm mơ hồ | Khai báo ngoại lệ cụ thể hoặc bắt ở nơi xử lý được. |
| Bắt `Exception` rồi để khối bắt rỗng | Mất tín hiệu thất bại, khó truy tìm lỗi | Phục hồi thật sự, chuyển tiếp, hoặc bọc kèm nguyên nhân. |
| Bắt lớp cha trước lớp con | `catch` phía sau không thể tới, mã không biên dịch | Sắp xếp nhánh cụ thể trước nhánh tổng quát. |
| Thêm `throws SQLException` vào override khi interface chỉ cho `IOException` | Vi phạm hợp đồng phương thức | Giữ tập checked exception cùng loại hoặc hẹp hơn cha. |
| Bắt `InterruptedException` nhưng không chuyển tiếp/khôi phục cờ ngắt | Mất tín hiệu hủy công việc | `throws InterruptedException` hoặc `Thread.currentThread().interrupt()` rồi dừng phù hợp. |
| Ném ngoại lệ mới nhưng bỏ `cause` | Mất dấu vết lỗi gốc | Dùng constructor nhận `cause` hoặc `initCause` khi thích hợp. |

## 10. Tự kiểm tra

1. `IOException` khác `NullPointerException` ở yêu cầu biên dịch nào? **Đáp án:** `IOException` là checked, nên phải được bắt hoặc khai báo khi có thể phát sinh; `NullPointerException` là unchecked, không có yêu cầu đó.
2. A khai báo `throws IOException`, B gọi A nhưng không bắt. B phải làm gì? **Đáp án:** B khai báo `throws IOException` hoặc một kiểu cha phù hợp; tiếp tục chuyển trách nhiệm cho nơi gọi B.
3. `catch (Exception ex)` có thể bắt `IOException` không? **Có**, nhưng thường quá rộng; cần cân nhắc bắt chính xác và không nuốt lỗi.
4. Trong override của phương thức cha `throws IOException`, có thể khai báo `throws FileNotFoundException` không? **Có**, vì `FileNotFoundException` là lớp con của `IOException`.
5. Dùng `throws IOException` trong `main` có đảm bảo ứng dụng không dừng khi lỗi I/O xuất hiện? **Không**; nó chỉ chuyển ngoại lệ ra khỏi `main`, không thực hiện phục hồi.

## Tài liệu đối chiếu

- Java Language Specification 17, [§11.1.1 và §11.2 — Exception Types và Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html).
- Oracle Java Tutorials, [The Catch or Specify Requirement](https://docs.oracle.com/javase/tutorial/essential/exceptions/catchOrDeclare.html) (trang giới thiệu cho JDK 8, quy tắc cốt lõi vẫn áp dụng).
- Oracle Java Tutorials, [The try-with-resources Statement](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html).

**Ghi nhớ:** `throws` là một phần của hợp đồng truyền lỗi; `catch` là nơi bạn đưa ra cách xử lý. Chọn điểm xử lý theo khả năng phục hồi thực tế và luôn bảo toàn thông tin cần thiết về nguyên nhân ngoại lệ.
