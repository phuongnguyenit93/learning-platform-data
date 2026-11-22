# Ngoại lệ là gì và vấn đề cần giải quyết trong Java

Trong Java, **ngoại lệ (exception)** là đối tượng biểu diễn một tình huống bất thường xảy ra trong lúc chương trình thực thi, khiến thao tác hiện tại không thể tiếp tục theo đường đi bình thường. Thay vì âm thầm trả kết quả sai hoặc bắt mọi hàm tự kiểm tra một “mã lỗi”, Java cho phép nơi phát hiện vấn đề **ném (throw)** một đối tượng exception; hệ thống thực thi sẽ tìm một nơi **bắt (catch)** phù hợp trong chuỗi lời gọi để xử lý.

Ví dụ: chương trình đọc cấu hình để kết nối dịch vụ, nhưng tệp cấu hình không tồn tại. Không thể giả vờ rằng đã đọc được dữ liệu. Mã đọc tệp có thể báo `IOException`; mã gọi nó quyết định nên thử đường dẫn khác, trả lỗi cho người dùng, hủy thao tác hay chuyển lỗi lên tầng cao hơn.

Bài học này giải thích **exception là gì, vì sao Java cần cơ chế exception và cách cơ chế ấy vận hành**. Mục tiêu không phải biến mọi tình huống không như mong muốn thành exception, mà là giữ rõ ranh giới giữa **luồng xử lý bình thường** và **sự cố phải được xử lý có chủ đích**.

## 1. Vấn đề ban đầu: thao tác có thể không hoàn tất

Hãy xét một hàm nạp thông tin người dùng. Trong trường hợp thuận lợi, hàm nhận ID, tìm dữ liệu và trả về người dùng. Nhưng điều gì xảy ra nếu:

- Cơ sở dữ liệu tạm thời không thể truy cập?
- Dữ liệu đầu vào vi phạm tiền điều kiện API?
- Mã cố truy cập một tham chiếu `null`?
- Một phần công việc đã hoàn tất nhưng phần còn lại thất bại?
- Tài nguyên như tệp hoặc kết nối đã mở cần được đóng khi có lỗi?

Nếu chỉ có kiểu kết quả dành cho **thành công**, hàm khó thể hiện nguyên nhân thất bại. Nếu mọi hàm đều trả về một giá trị đặc biệt như `-1`, `null` hoặc chuỗi `"ERROR"`, bên gọi phải nhớ kiểm tra từng bước và giá trị đặc biệt dễ bị hiểu nhầm là dữ liệu hợp lệ.

Ví dụ về cách báo lỗi qua giá trị đặc biệt:

```java
// Minh họa ý tưởng; không phải API hoàn chỉnh.
int readScore(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException e) {
        return -1; // -1 là "không parse được" hay một giá trị đầu vào thực?
    }
}
```

Ở đây không thể phân biệt “người dùng nhập `-1`” với “không chuyển được chuỗi sang số”. Bên gọi còn có thể quên kiểm tra `-1` và dùng nó để tính toán.

Exception giải quyết một phần khó khăn này bằng cách tạo **đường truyền tín hiệu thất bại riêng khỏi giá trị trả về thông thường**. Khi exception được ném, phép tính hiện tại bị gián đoạn; Java tìm nơi xử lý phù hợp, và đối tượng exception có thể mang loại lỗi, thông điệp, nguyên nhân gốc và stack trace.

Điều đó không có nghĩa mọi thất bại đều nên dùng exception. Một kết quả dự kiến như “hết hàng” hoặc “không tìm thấy trong truy vấn tìm kiếm” có thể phù hợp hơn với giá trị trả về có kiểu rõ ràng. Chính **hợp đồng của thao tác** quyết định sự kiện nào là nhánh bình thường, sự kiện nào là bất thường.

## 2. Khái niệm exception theo nghĩa chính xác

**Exception là một đối tượng thuộc lớp `Throwable`, thường là một lớp con của `Exception`, được ném bởi câu lệnh `throw` hoặc phát sinh trong quá trình JVM thực thi.** Khi nói “một exception xảy ra”, thông thường ta đang nói đến việc một đối tượng exception được ném.

Hãy tách ba điều:

1. **Sự kiện/điều kiện gây vấn đề:** ví dụ chuỗi không phải số, tệp mất quyền truy cập hoặc tham chiếu `null`.
2. **Tín hiệu Java:** một đối tượng như `NumberFormatException` hoặc `IOException` biểu diễn vấn đề đó.
3. **Chính sách xử lý:** bắt exception để yêu cầu nhập lại, ghi nhận lỗi, thử phương án khác, hoặc để nó lan truyền tới tầng biết xử lý.

Một vấn đề có thể được phát hiện ở tầng thấp nhưng chỉ được giải quyết ở tầng cao. Ví dụ, thư viện đọc tệp biết *không đọc được*, còn ứng dụng biết *có được phép dùng cấu hình mặc định hay phải dừng khởi động*. Cơ chế exception cho phép hai tầng giữ đúng trách nhiệm.

**Các thuộc tính đáng chú ý** của đối tượng ngoại lệ:

- **Loại (type):** ví dụ `IOException` hay `IllegalArgumentException`; người gọi có thể bắt theo loại.
- **Thông điệp (message):** lấy qua `getMessage()`, mô tả bối cảnh; có thể bằng `null`.
- **Nguyên nhân (cause):** lấy qua `getCause()`, liên kết lỗi cấp cao với lỗi gốc khi chuyển đổi exception.
- **Stack trace:** các khung lời gọi giúp lần theo vị trí và đường dẫn thực thi; lấy qua `getStackTrace()` hoặc in qua `printStackTrace()`.
- **Suppressed exceptions:** các lỗi phụ được đính kèm, thường gặp khi đóng tài nguyên trong `try-with-resources`; lấy qua `getSuppressed()`.

Thông điệp không phải một mã lỗi chuẩn hóa và có thể thay đổi; đừng để nghiệp vụ phụ thuộc vào việc so sánh nguyên văn `getMessage()`.

## 3. Exception thay đổi luồng thực thi như thế nào?

Câu lệnh bình thường chạy từ trên xuống dưới. Khi ném exception, Java **dừng đường đi bình thường trong đoạn đang thực thi**. Nó tìm `catch` phù hợp ở cấu trúc `try` gần nhất; nếu không có, exception tiếp tục lan truyền qua những phương thức đang gọi nhau.

Ví dụ giả định:

```text
main()
  └─ receiveRequest()
       └─ loadConfig()
            └─ readFile()  → ném IOException
```

Nếu `readFile()` không xử lý exception, nó không quay về với giá trị thành công. Exception được chuyển tới `loadConfig()`; nếu không có `catch` phù hợp thì tiếp tục tới `receiveRequest()`, rồi tới `main()`. Quá trình đó thường được gọi là **lan truyền exception (exception propagation)** và **tháo ngăn xếp lời gọi (stack unwinding)**.

Mỗi khi một phương thức kết thúc bất thường, các lệnh còn lại trên đường thực thi đó không tự động tiếp tục. Khi đã tìm thấy `catch` phù hợp, luồng chạy tiếp **sau phần xử lý theo cấu trúc điều khiển**, chứ không nhảy ngược vào chính câu lệnh gây exception.

Ví dụ Java 17+ độc lập, lưu thành `PropagationDemo.java`:

```java
public class PropagationDemo {
    static void readSettings() {
        throw new IllegalStateException("Thiếu cấu hình");
    }

    static void startService() {
        readSettings();
        System.out.println("Dịch vụ đã khởi động"); // Không chạy
    }

    public static void main(String[] args) {
        System.out.println("Bắt đầu");
        try {
            startService();
            System.out.println("Trong try, sau startService"); // Không chạy
        } catch (IllegalStateException e) {
            System.out.println("Đã bắt: " + e.getMessage());
        }
        System.out.println("Chương trình tiếp tục");
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 --release 17 PropagationDemo.java
java PropagationDemo
```

**stdout chính xác** trong môi trường hiển thị UTF-8:

```text
Bắt đầu
Đã bắt: Thiếu cấu hình
Chương trình tiếp tục
```

Những câu lệnh in “Dịch vụ đã khởi động” và “Trong try, sau startService” không chạy. `catch` nằm ở `main` xử lý được exception ném sâu trong `readSettings`; sau `catch`, chương trình tiếp tục theo đường đi hợp lệ.

Nếu không có `catch` phù hợp trên đường lan truyền và exception thoát khỏi `main`, luồng `main` kết thúc bất thường; JVM thường in loại exception, message và stack trace ra **stderr**. Trong ứng dụng máy chủ hay đa luồng, một exception không được bắt thường làm kết thúc luồng tương ứng; không nên mặc định toàn bộ tiến trình JVM luôn dừng trong mọi ngữ cảnh.

## 4. Exception giải quyết những vấn đề gì?

### 4.1. Báo thất bại mà không giả tạo một kết quả thành công

Một hàm tuyên bố trả về `User` nên trả về người dùng khi thành công. Nếu gặp lỗi không thể hoàn tất, hàm có thể ném exception thay vì trả về một đối tượng rỗng hoặc dữ liệu giả. Điều này giúp bên gọi phân biệt “có dữ liệu hợp lệ” với “không hoàn thành thao tác”.

Cần phân biệt: **không có kết quả nhưng vẫn hợp lệ** (ví dụ tìm một phần tử không tồn tại) có thể dùng `Optional<User>` hoặc loại kết quả riêng; exception không thay thế thiết kế API.

### 4.2. Không bắt tầng thấp tự quyết định cách ứng dụng phản ứng

Mã thao tác tệp biết nó thất bại, nhưng không biết nên hiển thị hộp thoại hay chuyển sang cấu hình dự phòng. Khi ném exception, tầng đó truyền thông tin cho tầng có đủ ngữ cảnh quyết định.

Lợi ích là tách biệt **phát hiện lỗi** và **chính sách xử lý lỗi**. Đổi lại, người viết chương trình phải đọc hợp đồng phương thức và có chiến lược xử lý rõ ràng ở ranh giới phù hợp.

### 4.3. Không bắt mọi lời gọi kiểm tra mã lỗi thủ công

Khi thao tác A gọi B, B gọi C, C gọi D, mã lỗi thủ công buộc nhiều tầng truyền giá trị báo lỗi dù không tầng nào xử lý được nó. Exception có thể đi qua các tầng đó tới `catch` phù hợp.

Đây là công cụ làm mã sáng rõ hơn, **không miễn trách nhiệm thiết kế hợp đồng và kiểm thử nhánh lỗi**. Một exception bị bỏ quên vẫn có thể khiến luồng yêu cầu thất bại bất ngờ.

### 4.4. Giữ bối cảnh chẩn đoán

Loại exception và stack trace cho biết mã đi qua những lời gọi nào; message giải thích điều kiện, `cause` giúp liên kết lỗi cấp cao với lỗi gốc. Khi “không thể tạo báo cáo” bắt nguồn từ “không đọc được tệp cấu hình”, chuỗi nguyên nhân giúp chẩn đoán đúng nơi.

### 4.5. Hỗ trợ cleanup khi đường đi bình thường bị gián đoạn

Khi đang dùng tệp, socket hoặc tài nguyên khác, một exception có thể xuất hiện trước lệnh đóng tài nguyên. `finally` và `try-with-resources` giúp lập trình viên đặt việc dọn dẹp vào vị trí được thực hiện khi rời phạm vi, kể cả trong các đường đi có exception. Tuy nhiên, không có cơ chế cleanup nào bảo đảm chạy trong mọi trường hợp như JVM bị chấm dứt cưỡng bức.

## 5. Hệ phân cấp cơ bản: `Throwable`, `Exception` và `Error`

Sơ đồ rút gọn:

```text
java.lang.Object
  └─ java.lang.Throwable
       ├─ java.lang.Error
       │    ├─ OutOfMemoryError
       │    └─ StackOverflowError
       └─ java.lang.Exception
            ├─ IOException
            ├─ ReflectiveOperationException
            └─ RuntimeException
                 ├─ IllegalArgumentException
                 │    └─ NumberFormatException
                 ├─ IllegalStateException
                 ├─ NullPointerException
                 └─ IndexOutOfBoundsException
```

Các lớp trên chỉ là **một phần** của hệ phân cấp Java.

- `Throwable` là kiểu gốc cho các đối tượng có thể `throw` và `catch`.
- `Exception` thường biểu diễn tình huống ứng dụng có thể xử lý hoặc truyền cho phía gọi.
- `RuntimeException` là lớp con của `Exception`, dùng cho các exception **unchecked** như `IllegalArgumentException` và `NullPointerException`.
- `Error` biểu thị những vấn đề nghiêm trọng của JVM/môi trường hay liên kết lớp; mã nghiệp vụ thông thường **không nên** bắt rộng nhóm này để giả vờ tiếp tục an toàn.

**Checked exception** là lớp con của `Throwable` không thuộc `RuntimeException` hoặc `Error`, thường thấy ở các lớp con của `Exception` như `IOException`. Trình biên dịch yêu cầu mã gọi phải bắt hoặc khai báo checked exception có thể được ném. **Unchecked exception** gồm `RuntimeException` cùng lớp con và `Error` cùng lớp con; trình biên dịch không buộc bên gọi khai báo/bắt chúng.

Đừng hiểu “checked” là chắc chắn phục hồi được, hay “unchecked” là chắc chắn bug. Một `IOException` có thể không thể khắc phục tại chỗ; một `IllegalArgumentException` có thể bắt nguồn từ dữ liệu nhập vào cần được báo lại cho người dùng. Tình huống thực tế và hợp đồng API mới quyết định hành động.

## 6. Các cấu trúc Java liên quan trực tiếp đến exception

| Cấu trúc | Vai trò |
| --- | --- |
| `throw exceptionObject;` | Ném **một đối tượng** thuộc `Throwable`, làm gián đoạn luồng bình thường |
| `throws SomeException` | Khai báo ở chữ ký phương thức rằng nó có thể truyền exception tương ứng ra ngoài; **không tự ném** |
| `try { ... }` | Bao đoạn mã cần đặt dưới cơ chế bắt/dọn dẹp |
| `catch (Type e) { ... }` | Chạy khi có exception khớp kiểu đang được lan truyền từ `try` tương ứng |
| `finally { ... }` | Dành cho dọn dẹp/cuối thao tác, thường chạy khi rời `try/catch` |
| `try (resource) { ... }` | Tự đóng tài nguyên `AutoCloseable` theo thứ tự ngược khi rời `try` |

### `throw` và `throws` là hai việc khác nhau

```java
import java.io.IOException;

class ConfigurationService {
    static String load(boolean reachable) throws IOException {
        if (!reachable) {
            throw new IOException("Không thể truy cập cấu hình");
        }
        return "ready";
    }
}
```

Đây là **đoạn khai báo lớp minh họa**, không có `main` để chạy độc lập. `throw new IOException(...)` thực sự tạo và ném đối tượng; `throws IOException` thông báo cho bên gọi về khả năng này. Nếu bên gọi viết `ConfigurationService.load(false)`, nó phải bắt hoặc khai báo `IOException` thì mã mới biên dịch được, vì đó là checked exception.

`throws` không làm tệp/dịch vụ hoạt động lại, cũng không thay cho `catch`. Bên gọi muốn bỏ qua vấn đề bằng cách ghi `throws IOException` suốt chuỗi tầng thì tầng cao nhất vẫn cần xác định điều gì xảy ra nếu exception thoát ra.

### `catch` lựa chọn theo quan hệ kiểu

`catch` bắt exception có kiểu tương thích với kiểu khai báo của tham số, kể cả lớp con. Các nhánh `catch` phải được sắp từ **cụ thể tới tổng quát**. Ví dụ `NumberFormatException` là lớp con của `IllegalArgumentException`; bắt `IllegalArgumentException` trước sẽ khiến nhánh `NumberFormatException` phía sau trở thành mã không thể tới, nên Java báo lỗi biên dịch.

```java
try {
    int value = Integer.parseInt(text);
    System.out.println(value);
} catch (NumberFormatException e) {
    System.out.println("Dữ liệu không phải số nguyên");
} catch (IllegalArgumentException e) {
    System.out.println("Đối số không hợp lệ");
}
```

Đây là **đoạn trong một phương thức**, giả sử biến `text` đã được khai báo. Phân nhánh thứ hai sẽ bắt một số `IllegalArgumentException` khác phát sinh bên trong `try`; với riêng `Integer.parseInt` và một chuỗi đầu vào, nhánh `NumberFormatException` là nhánh lỗi chuyển đổi đáng quan tâm.

### `finally` và `try-with-resources`

`finally` thường chạy khi thoát `try`, dù thành công, có exception được bắt, exception chưa được bắt hoặc có `return`; nhưng không thể bảo đảm nếu tiến trình bị dừng cưỡng bức, JVM sập hoặc xảy ra các tình huống đặc biệt. Tránh `return` hoặc `throw` mới trong `finally` vì có thể **che khuất exception hoặc giá trị trả về đang có**.

Với tài nguyên triển khai `AutoCloseable` (như `BufferedReader`), ưu tiên `try-with-resources`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class FileReaderExample {
    static String readFirstLine(Path path) throws IOException {
        try (BufferedReader reader = Files.newBufferedReader(path)) {
            return reader.readLine();
        }
    }
}
```

Đoạn này là **lớp minh họa không có `main`**; hành vi phụ thuộc đường dẫn và nội dung tệp thực tế. Dù `readLine` thành công, trả về `null` khi đã hết dữ liệu, hay ném exception, Java đều cố đóng `reader` khi rời khối `try`. Nếu cả phần xử lý lẫn `close()` đều ném exception, ngoại lệ khi đóng thường được lưu trong danh sách **suppressed** của exception chính, để giữ dấu vết lỗi gốc. Nếu không có lỗi phần xử lý nhưng việc đóng lỗi, exception từ `close()` có thể được truyền ra ngoài.

`try-with-resources` không tự động rollback giao dịch, hoàn tác mọi side effect, hay bảo đảm tài nguyên xa được đóng thành công; nó quản lý việc gọi `close()` trên các tài nguyên được khai báo.

## 7. Ví dụ hoàn chỉnh: nhận dữ liệu, báo lỗi, xử lý và tiếp tục

Lưu chương trình sau thành `ExceptionBasicsDemo.java` và chạy với **Java 17+**:

```java
public class ExceptionBasicsDemo {
    static int readPositiveInteger(String text) {
        int value = Integer.parseInt(text);
        if (value <= 0) {
            throw new IllegalArgumentException("Giá trị phải lớn hơn 0");
        }
        return value;
    }

    static int calculatePrice(String quantityText) {
        int quantity = readPositiveInteger(quantityText);
        return quantity * 100;
    }

    public static void main(String[] args) {
        String[] inputs = {"3", "0", "abc"};

        for (String text : inputs) {
            try {
                int price = calculatePrice(text);
                System.out.println(text + " -> " + price);
            } catch (NumberFormatException e) {
                System.out.println(text + " -> không phải số nguyên");
            } catch (IllegalArgumentException e) {
                System.out.println(text + " -> số lượng không hợp lệ: "
                        + e.getMessage());
            }
        }

        System.out.println("Đã xử lý tất cả đầu vào");
    }
}
```

Lệnh chạy:

```bash
javac -encoding UTF-8 --release 17 ExceptionBasicsDemo.java
java ExceptionBasicsDemo
```

**stdout chính xác** trong môi trường hiển thị UTF-8:

```text
3 -> 300
0 -> số lượng không hợp lệ: Giá trị phải lớn hơn 0
abc -> không phải số nguyên
Đã xử lý tất cả đầu vào
```

Phân tích từng nhánh:

1. `"3"` chuyển được thành `int 3`, hợp lệ; `calculatePrice` trả về `300` như một giá trị thông thường.
2. `"0"` chuyển được thành số nhưng không thỏa tiền điều kiện của `readPositiveInteger`; câu lệnh `throw new IllegalArgumentException(...)` chấm dứt nhánh bình thường và ném exception đến `catch` tương ứng trong vòng lặp ở `main`.
3. `"abc"` khiến `Integer.parseInt` ném `NumberFormatException` trước khi tới kiểm tra số dương. Vì nhánh `catch (NumberFormatException e)` đứng trước `IllegalArgumentException` nên nó được chọn.
4. Sau khi mỗi exception được xử lý, vòng lặp chuyển sang lần tiếp theo; không có lệnh nào trong phép gọi thất bại tiếp tục chạy tại vị trí đã bị gián đoạn.

Ví dụ dùng giá đơn vị `100` để kết quả dễ theo dõi; ứng dụng thực cần xác thực miền giá trị, chống tràn số và lựa chọn cách xử lý nhập liệu phù hợp. `NumberFormatException` là một exception, nhưng việc nhập sai có thể được chuyển thành **kết quả xác thực dự kiến** tại giao diện; lựa chọn đó phụ thuộc hợp đồng tầng giao tiếp.

## 8. Khi không bắt được exception: điều gì thực sự xảy ra?

Nếu không có `catch` tương thích, exception tiếp tục được truyền lên các caller. Với một ứng dụng console, exception thoát khỏi `main` thường in stack trace và kết thúc luồng chính với trạng thái lỗi. Stack trace hiển thị những vị trí khung lời gọi phục vụ chẩn đoán, ví dụ từ `readPositiveInteger` qua `calculatePrice` tới `main`, cùng tên loại exception.

Trong chương trình đa luồng, nếu một thread có exception không được bắt, thread đó có thể kết thúc; các thread khác có thể vẫn tiếp tục. Trong framework máy chủ, tầng framework thường đặt ranh giới xử lý exception cho từng request, nên một request có thể thất bại mà toàn bộ JVM vẫn sống. Vì vậy câu “cứ ném exception là chương trình sập” là khái quát sai.

Phân biệt **được ném** và **được xử lý hiệu quả**: một `catch` có thể bắt exception nhưng trả về dữ liệu sai, bỏ qua nguyên nhân hoặc ghi log rồi tiếp tục trong trạng thái hỏng. Đó không phải xử lý an toàn.

## 9. Chọn nơi bắt và cách xử lý ngoại lệ

Chỉ bắt exception khi tầng hiện tại **biết làm gì có ý nghĩa**: thử phương án dự phòng, yêu cầu dữ liệu mới, khôi phục trạng thái hợp lệ, bổ sung ngữ cảnh cho lỗi hoặc chuyển thành phản hồi ở ranh giới API.

Các lựa chọn điển hình:

- **Phục hồi:** đường dẫn tệp chính lỗi và ứng dụng có cấu hình dự phòng được phép dùng. Bắt `IOException`, thử đường dẫn dự phòng, báo rõ nếu vẫn không thể nạp.
- **Chuyển thành kết quả rõ ràng:** lớp giao tiếp bắt lỗi chuyển đổi dữ liệu người dùng và trả một lỗi xác thực có cấu trúc.
- **Bổ sung ngữ cảnh rồi ném tiếp:** lớp dịch vụ biết thao tác nào thất bại; bọc `IOException` thành ngoại lệ phù hợp với API, giữ `cause`.
- **Cho phép lan truyền:** tầng hiện tại không có chiến lược an toàn; giữ hợp đồng `throws` cho checked exception hoặc cho exception unchecked đi lên tầng có trách nhiệm.

Ví dụ chuyển lỗi nhưng vẫn giữ nguyên nhân gốc:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class AppSettings {
    static String load(Path path) {
        try {
            return Files.readString(path);
        } catch (IOException cause) {
            throw new IllegalStateException(
                    "Không nạp được cấu hình từ " + path, cause);
        }
    }
}
```

Đây là **lớp minh họa không có `main`**. Nếu việc đọc thất bại, bên gọi thấy `IllegalStateException` với thông điệp có ngữ cảnh; `getCause()` trả về `IOException` ban đầu. Không lạm dụng việc chuyển checked sang unchecked chỉ để né xử lý; chỉ đổi loại khi phù hợp với hợp đồng API của tầng hiện tại.

Đặt xử lý tại **ranh giới có khả năng quyết định**: ví dụ console UI chọn thông báo và yêu cầu nhập lại, HTTP adapter chuyển lỗi thành mã HTTP đúng theo hợp đồng, scheduler ghi nhận job thất bại và áp dụng chính sách retry hợp lệ. Đừng bắt một lỗi từ cơ sở dữ liệu rồi trả về “không tìm thấy người dùng” nếu hai tình huống có ý nghĩa khác nhau.

## 10. Exception không có nhiệm vụ thay thế mọi nhánh nghiệp vụ

Hãy hỏi: một điều kiện có **thường xuyên và hợp lệ** đối với nghiệp vụ hay không? Nếu “hết hàng” là nhánh phải hiển thị bình thường, kiểu kết quả chứa trạng thái `OUT_OF_STOCK` thường dễ hiểu hơn ném exception qua nhiều tầng. Nếu “kho luôn không âm” là bất biến nội bộ nhưng đột nhiên kho âm, exception có thể biểu diễn việc vi phạm hợp đồng.

Một số hình thức báo kết quả thường gặp:

| Trường hợp | Một thiết kế có thể phù hợp |
| --- | --- |
| Tìm ID có thể không tồn tại như điều bình thường | `Optional<User>` hoặc kết quả có trạng thái `NOT_FOUND` |
| Đặt hàng bị từ chối vì hết hàng | Kết quả kiểu `OrderResult` chứa mã từ chối |
| Dữ liệu người dùng không đạt điều kiện | Danh sách lỗi xác thực; hoặc lỗi chuyển đổi được xử lý tại ranh giới |
| Gọi API với tham số sai hợp đồng của lập trình viên | `IllegalArgumentException` |
| Tệp bắt buộc bị lỗi truy cập | `IOException`, xử lý hoặc lan truyền có ngữ cảnh |
| Hệ thống vi phạm bất biến nội bộ | Exception diễn tả trạng thái không hợp lệ, đi tới tầng chịu trách nhiệm |

Các lựa chọn trên không phải luật cứng. Có API cố ý thiết kế **domain exception** để biểu diễn sự từ chối nghiệp vụ. Khi ấy exception vẫn là cơ chế Java của việc truyền tín hiệu; ý nghĩa là gì do hợp đồng quyết định. Quan trọng nhất là caller biết xử lý thế nào và không coi một lời từ chối dự kiến là sự cố hạ tầng.

## 11. Exception khác gì lỗi biên dịch và lỗi logic?

Exception là cơ chế **khi thực thi**. Nó không thay thế kiểm tra cú pháp và kiểu của `javac`:

- `int n = "5";` là lỗi kiểu tại **biên dịch**, không thể dùng `try/catch` để “bắt” lỗi đó trong chương trình đã chạy.
- `Integer.parseInt("x")` có thể **biên dịch**, nhưng khi chạy sẽ ném `NumberFormatException`.
- `int sum = Integer.MAX_VALUE + 1;` biên dịch và thực thi phép cộng kiểu `int` với kết quả bị tràn theo quy tắc số nguyên Java; mặc định **không ném exception**. Đây có thể là lỗi logic nếu nghiệp vụ cần kết quả toán học chính xác.
- Một yêu cầu đăng nhập có mật khẩu không đúng có thể trả “từ chối” hoàn toàn bình thường; không nhất thiết có exception.

Đừng chẩn đoán sai bằng quy tắc “không có exception nghĩa là chương trình đúng” hay “có exception nghĩa là chắc chắn lỗi lập trình”. Kiểm thử tính đúng đắn, tính nhất quán dữ liệu và các nhánh nghiệp vụ vẫn cần thực hiện.

## 12. Những lỗi phổ biến khi bắt ngoại lệ

### Bắt rồi bỏ qua

```java
try {
    performOperation();
} catch (Exception ignored) {
    // Không ghi nhận và không có chiến lược khôi phục.
}
```

Đây là **đoạn minh họa**, giả sử `performOperation()` đã được định nghĩa. Cách này làm mất tín hiệu về sự cố. Chỉ bỏ qua một loại exception cụ thể khi hợp đồng cho phép và có lý do rõ ràng.

### Bắt quá rộng hoặc bắt cả `Throwable`

`catch (Exception e)` có thể gom nhiều loại lỗi cần xử lý khác nhau, che giấu bug và đánh mất hành động phù hợp với từng loại. `catch (Throwable t)` còn có thể bắt cả `Error` vốn không nên được tầng nghiệp vụ cố xử lý như lỗi thường. Có các ranh giới framework đặc biệt cần bắt rộng để ghi nhận lỗi cuối cùng, nhưng đó là quyết định kiến trúc có chủ đích.

### Đổi sang lỗi mới mà làm mất `cause`

```java
// Kém: không giữ nguyên nhân ban đầu.
catch (IOException e) {
    throw new IllegalStateException("Không đọc được dữ liệu");
}
```

Nên giữ nguyên nhân nếu chuyển kiểu:

```java
catch (IOException e) {
    throw new IllegalStateException("Không đọc được dữ liệu", e);
}
```

Hai đoạn là **phần của khối try/catch**, không phải chương trình độc lập. Giữ `cause` giúp stack trace phản ánh cả sự cố nền tảng.

### Dùng exception thay vòng điều khiển thông thường

Ném exception cho mỗi bước lặp hoặc mỗi kết quả kiểm tra thông thường khiến mã khó hiểu, buộc người đọc lần theo các nhánh phi tuyến, và có thể gây chi phí không cần thiết khi ném rất thường xuyên. Hãy dùng điều kiện, trạng thái hoặc kiểu kết quả rõ ràng cho những nhánh dự kiến.

### Hiển thị stack trace cho người dùng cuối

Stack trace dành cho người phát triển và vận hành; có thể chứa đường dẫn nội bộ, tên lớp, thông tin nhạy cảm và cấu trúc hệ thống. Ứng dụng nên cung cấp thông điệp phù hợp với người dùng, đồng thời ghi log chẩn đoán cần thiết ở nơi được bảo vệ. Không đặt bí mật vào message của exception.

### Retry mọi exception

Không phải lỗi nào cũng tạm thời, và không phải thao tác nào cũng an toàn khi lặp lại. Retry một yêu cầu tạo đơn hàng có thể tạo đơn trùng nếu lần đầu đã ghi thành công trước khi mất phản hồi. Chỉ retry khi nguyên nhân, chính sách backoff, timeout, tính idempotent và side effect đã được xem xét.

### Quên cleanup hoặc dùng `finally` không an toàn

Một exception có thể bỏ qua lệnh `close()` nằm ở cuối `try`. Hãy ưu tiên `try-with-resources` cho `AutoCloseable`. Đừng `return` trong `finally` để vô tình ghi đè kết quả hoặc che exception đang lan truyền.

## 13. Cách đọc exception khi xử lý lỗi thật

Khi có lỗi runtime, lần lượt:

1. **Tên loại:** `NumberFormatException` nói đến chuyển đổi số, `IOException` liên quan hoạt động I/O; tên loại chỉ là gợi ý, không đủ để kết luận nguyên nhân gốc.
2. **Message:** nêu giá trị/trạng thái liên quan nếu an toàn, nhưng không phụ thuộc vào văn bản message làm logic điều kiện.
3. **Stack trace:** tìm khung lời gọi thuộc mã ứng dụng nơi thao tác lỗi, rồi lần theo caller để biết điều kiện nào dẫn tới đó. Dòng gây ném ở thư viện không nhất thiết là nơi có bug trong ứng dụng.
4. **Cause:** lần xuống chuỗi `getCause()` để xác định lỗi sâu bên dưới khi exception được bọc.
5. **Suppressed:** kiểm tra khi có nhiều lỗi, đặc biệt lúc đóng tài nguyên.
6. **Bối cảnh:** dữ liệu đầu vào, phiên bản JDK, cấu hình, tài nguyên, thời điểm và thao tác trước đó; tránh log dữ liệu bí mật.
7. **Hợp đồng:** xác định nên khôi phục, trả kết quả nghiệp vụ, hay thông báo lỗi kỹ thuật cho tầng cao hơn.

Một exception được **bắt** chưa chắc đã **được giải quyết**. Xử lý đúng nghĩa là giữ hệ thống ở trạng thái hợp lệ, đưa ra tín hiệu phù hợp cho caller và không làm mất thông tin cần điều tra.

## 14. Câu hỏi tự kiểm tra

**Tình huống 1.** Hàm đọc tệp ném `IOException`. Phương thức gọi chỉ có thể hiển thị thông báo và yêu cầu chọn tệp khác. Nên làm gì?  
Có thể `catch` tại tầng giao diện để báo lỗi và cho chọn lại, vì tầng này có chiến lược phục hồi hợp lệ.

**Tình huống 2.** `methodA()` gọi `methodB()`; `methodB()` ném `IllegalStateException` không được bắt. Câu lệnh ngay sau lời gọi `methodB()` trong `methodA()` có tiếp tục không?  
Không, lời gọi kết thúc bất thường và exception tiếp tục lan truyền. Mã có thể chạy tiếp ở một `catch` phù hợp trên call stack.

**Tình huống 3.** Thêm `throws IOException` vào một phương thức có làm lỗi đọc tệp biến mất không?  
Không. Nó chỉ thay đổi hợp đồng khai báo và cho phép exception lan truyền; vẫn phải quyết định chính sách xử lý.

**Tình huống 4.** Người dùng tìm kiếm một bản ghi không tồn tại. Có bắt buộc phải ném exception không?  
Không. Nếu “không tìm thấy” là kết quả được dự kiến, có thể dùng `Optional` hoặc trạng thái nghiệp vụ rõ ràng.

**Tình huống 5.** Vì sao nên dùng `try-with-resources` khi đọc tệp?  
Vì tài nguyên được đóng khi rời khối theo cơ chế có cấu trúc, kể cả khi có exception, và Java giữ được suppressed exception trong tình huống thích hợp.

**Tình huống 6.** Vì sao `catch (NumberFormatException e)` cần đứng trước `catch (IllegalArgumentException e)`?  
Vì `NumberFormatException` là lớp con của `IllegalArgumentException`. Nếu bắt lớp cha trước, nhánh cho lớp con phía sau không thể tới và trình biên dịch từ chối.

## 15. Ghi nhớ để dùng exception đúng mục đích

- **Exception là tín hiệu có kiểu**, được ném trong lúc thực thi để biểu diễn vấn đề khiến đường đi bình thường không thể tiếp tục.
- Khi exception xuất hiện, Java **lan truyền qua call stack** đến `catch` tương thích; các lệnh nằm sau điểm ném trên nhánh đang bị gián đoạn không tự chạy tiếp.
- Exception giúp **tách việc phát hiện vấn đề khỏi quyết định xử lý**, giữ thông tin chẩn đoán và hỗ trợ dọn dẹp tài nguyên khi thoát đường đi bất thường.
- `throw` dùng để ném; `throws` khai báo khả năng ném; `catch` chỉ có ích khi tầng đó thật sự biết cách xử lý; `try-with-resources` quản lý tài nguyên `AutoCloseable`.
- **Không phải mọi kết quả không như mong muốn đều cần exception.** Chọn giữa kết quả bình thường và exception theo hợp đồng, bản chất sự kiện và trách nhiệm của bên gọi.
