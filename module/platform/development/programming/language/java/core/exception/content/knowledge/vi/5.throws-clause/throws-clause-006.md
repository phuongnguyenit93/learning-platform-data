# Khi nào nên `catch` và khi nào nên tiếp tục `throws` trong Java?

Trong Java, khi một phương thức có thể phát sinh ngoại lệ, lập trình viên thường đứng trước hai lựa chọn: **bắt bằng `catch` ở tầng hiện tại** hoặc **để ngoại lệ tiếp tục lan truyền tới bên gọi**, khai báo `throws` khi cần. Đây là một quyết định về *trách nhiệm xử lý lỗi*, không chỉ là cách làm cho trình biên dịch chấp nhận chương trình.

Nguyên tắc nền tảng: **hãy `catch` tại nơi thực sự có thể xử lý có ý nghĩa; nếu tầng hiện tại không thể khắc phục hay quyết định phản hồi phù hợp, hãy để lỗi lan truyền theo hợp đồng**. Một `catch` không phục hồi được mà chỉ trả giá trị giả hoặc bỏ qua ngoại lệ thường nguy hiểm hơn việc để tầng cao hơn nhìn thấy sự cố.

Cũng cần tách biệt ba việc:

1. **Phát hiện và ném lỗi**: thao tác bên trong ném đối tượng ngoại lệ bằng `throw`, hoặc API/JVM tự phát sinh.
2. **Khai báo khả năng lan truyền**: mệnh đề `throws` trong chữ ký phương thức mô tả các *checked exception* có thể thoát ra; nó không tự xử lý hay tự ném lỗi.
3. **Bắt và xử lý**: `try/catch` chuyển luồng thực thi sang một handler tương thích khi exception được ném.

Một phương thức có thể kết hợp: bắt một loại ngoại lệ để phục hồi, ném lại loại khác, và vẫn khai báo `throws` cho những lỗi chưa xử lý được.

## 1. Ví dụ trực quan: cùng một sự cố, hai tầng chịu trách nhiệm khác nhau

Giả sử ứng dụng cần nạp cấu hình từ tệp. Hàm đọc tệp biết *đọc thất bại* nhưng không biết ứng dụng có được phép dùng cấu hình mặc định không. Trong khi đó, tầng khởi động ứng dụng nắm chính sách: nếu thiếu cấu hình bắt buộc thì dừng khởi động; nếu chỉ thiếu thông tin tùy chọn thì dùng giá trị dự phòng.

Một phương thức đọc ở tầng thấp có thể viết:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class SettingsReader {
    static String read(Path file) throws IOException {
        return Files.readString(file);
    }
}
```

Đây là **lớp minh họa không có `main`**, việc đọc có thành công hay không phụ thuộc tệp trên máy. `Files.readString` có thể ném `IOException`, là checked exception. `SettingsReader.read` không có chính sách sử dụng giá trị dự phòng, nên khai báo `throws IOException` để bên gọi quyết định.

Nếu tầng khởi động có phương án dự phòng hợp lệ:

```java
static String resolveOptionalSetting(Path path) {
    try {
        return SettingsReader.read(path);
    } catch (IOException e) {
        return "default";
    }
}
```

Đây là **phương thức minh họa**, giả sử `SettingsReader` đã được khai báo. Nó chỉ đúng nếu yêu cầu nghiệp vụ *cho phép dùng "default" với mọi `IOException` từ thao tác đó*. Nếu chỉ được phép dùng mặc định khi tệp không tồn tại, không nên bắt toàn bộ `IOException` rồi che luôn lỗi quyền truy cập, thiết bị hoặc dữ liệu hỏng. Khi đó phải phân loại cụ thể hơn, chẳng hạn `NoSuchFileException`, và để các tình huống khác lan truyền.

Nếu cấu hình là bắt buộc, tầng khởi động có thể bắt lỗi ở ranh giới cuối để in thông báo phù hợp và quyết định không tiếp tục. Sự khác biệt nằm ở **hợp đồng của từng tầng**, không nằm ở việc exception đã “có thể catch được” hay chưa.

## 2. `catch` giải quyết điều gì, `throws` giải quyết điều gì?

| Góc nhìn | `catch` | `throws` |
| --- | --- | --- |
| Vị trí | Khối xử lý đi kèm `try` | Chữ ký phương thức |
| Công việc | Chọn một hành động khi gặp exception phù hợp | Công bố khả năng exception lan ra caller |
| Có tự ngăn lỗi lan truyền? | Có, **nếu handler xử lý xong bình thường** | Không |
| Có bắt buộc với checked exception? | Một lựa chọn để đáp ứng `catch-or-declare` | Lựa chọn còn lại để đáp ứng `catch-or-declare` |
| Có tự làm thao tác thành công? | Không; handler phải thực sự khôi phục hoặc chuyển sang kết quả được phép | Không |
| Có thể cùng tồn tại? | Có: bắt một loại, rồi ném tiếp loại khác | Có: khai báo loại checked vẫn thoát ra |
| Có cần với unchecked exception? | Không bắt buộc, nhưng có thể chủ động bắt | Không bắt buộc, nhưng có thể khai báo để tài liệu hóa |

Quy tắc **catch-or-declare** áp dụng cho checked exception: nếu từ thân phương thức có thể thoát ra một checked exception, phương thức phải **bắt hoặc khai báo** nó (hay kiểu cha phù hợp) theo các quy tắc phân tích ngoại lệ của Java. `RuntimeException`, `Error` và lớp con là unchecked; bên gọi không bị trình biên dịch buộc bắt hoặc khai báo chúng.

Ví dụ:

```java
import java.io.IOException;

class ChoiceExample {
    static void checkedOperation() throws IOException {
        throw new IOException("Mất kết nối");
    }

    static void propagate() throws IOException {
        checkedOperation(); // Để IOException đi lên caller.
    }

    static void handleLocally() {
        try {
            checkedOperation();
        } catch (IOException e) {
            System.out.println("Đã ghi nhận: " + e.getMessage());
        }
    }
}
```

Đây là lớp hợp lệ không có `main`. `propagate()` buộc khai báo `throws IOException`, còn `handleLocally()` không cần khai báo vì đã bắt lỗi. Tuy nhiên, `handleLocally()` chỉ minh họa cú pháp: in message rồi kết thúc không tự bảo đảm công việc ban đầu đã thành công. Ứng dụng thật phải xác định có được tiếp tục sau thất bại hay không.

## 3. Những dấu hiệu cho thấy nên `catch` ngay tại đây

### 3.1. Tầng hiện tại có phương án khôi phục an toàn

Nếu một phương án thay thế đã được hợp đồng chấp nhận và bạn biết chắc trạng thái vẫn hợp lệ, `catch` là hợp lý. Ví dụ một cấu hình tùy chọn có thể dùng mặc định khi tệp *không tồn tại*.

Quan trọng là nhận diện đủ hẹp để **không che những lỗi khác**. Phải xác định fallback có an toàn, có được phép, và liệu việc mất dữ liệu vừa xảy ra có dẫn đến hành vi sai tiếp theo hay không.

### 3.2. Có thể yêu cầu người dùng điều chỉnh đầu vào

Nếu người dùng nhập `"abc"` vào trường số lượng, `Integer.parseInt` có thể ném `NumberFormatException`. Tầng nhận dữ liệu có thể bắt lỗi và trả thông báo xác thực, vì đây là nơi biết giao diện và hướng xử lý.

```java
static String validateQuantity(String input) {
    try {
        int quantity = Integer.parseInt(input);
        return quantity > 0 ? "Hợp lệ" : "Phải lớn hơn 0";
    } catch (NumberFormatException e) {
        return "Phải nhập số nguyên";
    }
}
```

Đây là **phương thức minh họa**, không có `main`. Việc bắt ở ranh giới nhập liệu phù hợp vì kết quả hợp lệ hoặc lý do từ chối đều là một phần bình thường của hợp đồng. Không nên để lỗi nhập liệu thô tự động đi qua nhiều tầng rồi biến thành “sự cố máy chủ” nếu ranh giới đã đủ thông tin để diễn giải.

### 3.3. Ranh giới ứng dụng phải chuyển lỗi thành phản hồi

Ở một CLI, ranh giới cuối có thể in thông báo và kết thúc với mã thoát phù hợp. Với HTTP, tầng giao tiếp có thể chuyển exception/kết quả ứng dụng thành phản hồi theo hợp đồng API. Với một job nền, tầng điều phối có thể đánh dấu job thất bại và áp dụng chính sách thử lại đã được định nghĩa.

Đây thường là **nơi biết phản ứng cuối**. Ví dụ `400 Bad Request` hoặc `500 Internal Server Error` là lựa chọn giao thức HTTP, không phải hai loại ngoại lệ Java. Không ánh xạ tất cả `IllegalArgumentException` thành 400, vì đôi khi nó biểu thị bug ở dữ liệu nội bộ; phải xét nguồn lỗi và hợp đồng.

### 3.4. Phải thực hiện một hành động có ý nghĩa rồi quyết định lại

Một handler có thể ghi nhận một bước thất bại, hoàn tác thay đổi cục bộ hoặc bổ sung bối cảnh. Sau đó có thể ném lại bằng `throw e` nếu tầng hiện tại chưa khôi phục được. Như vậy, **bắt lỗi không nhất thiết đồng nghĩa nuốt lỗi**.

```java
try {
    operation();
} catch (IOException e) {
    recordFailedAttempt(e);
    throw e;
}
```

Đây là **khung mã minh họa**, giả sử các phương thức phụ trợ đã được định nghĩa và phương thức chứa đoạn mã cho phép lan truyền `IOException`. Công việc của `recordFailedAttempt` phải bản thân nó an toàn, không được âm thầm thay lỗi gốc; nếu nó ném exception mới, caller có thể thấy lỗi mới thay vì lỗi ban đầu.

## 4. Những dấu hiệu cho thấy nên tiếp tục `throws`

### 4.1. Không có thông tin để quyết định cách phục hồi

Thư viện lưu trữ dữ liệu không biết nên hiển thị hộp thoại, chuyển sang tệp dự phòng, trả mã HTTP hay kết thúc chương trình. Nếu không có cách xử lý bảo toàn đúng hợp đồng, hãy để `IOException` hoặc ngoại lệ thích hợp lan ra caller.

Không nên làm việc này:

```java
// Phản ví dụ: trả dữ liệu giả khi đọc thất bại.
static String unsafeRead(Path path) {
    try {
        return Files.readString(path);
    } catch (IOException e) {
        return ""; // Không phân biệt được tệp rỗng với lỗi đọc.
    }
}
```

Đây là phương thức minh họa, cần các import `Files`, `Path` và `IOException`. Chuỗi rỗng chỉ phù hợp nếu nó thực sự được định nghĩa là fallback an toàn trong mọi trường hợp. Nếu không, cách viết này khiến tầng gọi hiểu lầm rằng thao tác đã thành công.

### 4.2. Hợp đồng API vốn đã công bố checked exception

Một phương thức `readFile() throws IOException` có thể giữ nguyên hợp đồng ở các tầng chuyển tiếp. Tầng caller cao hơn biết cách xử lý lỗi I/O, ví dụ đóng phiên làm việc, đổi tệp hoặc hủy chức năng.

Lưu ý `throws` không *thay đổi* exception hay bắt nó. Nó chỉ làm rõ hợp đồng mà Java kiểm tra lúc biên dịch cho checked exception. Nếu exception không có handler phù hợp ở toàn bộ call stack, nó vẫn có thể thoát khỏi luồng đang chạy và làm thao tác thất bại.

### 4.3. Lỗi phát sinh từ bất biến hoặc tiền điều kiện mà tầng hiện tại không thể khắc phục

Nếu một API phát hiện tham số lập trình viên truyền sai, `IllegalArgumentException` có thể phù hợp hơn một fallback giả. Đây là unchecked exception: **không cần viết `throws IllegalArgumentException`**; chỉ để nó lan truyền đã đủ về mặt ngôn ngữ.

Ví dụ `Objects.requireNonNull(value)` có thể ném `NullPointerException` khi đối số là `null`. Tầng nhận giá trị nên bảo đảm hợp đồng; tầng trung gian không nên bắt rồi “tiếp tục như không có gì” khi thiếu dữ liệu bắt buộc.

### 4.4. Có thể bị hỏng trạng thái, cần cấp trên hủy toàn bộ thao tác

Giả sử chức năng lưu đơn đã ghi một phần nhưng bước tiếp theo thất bại. Tầng thấp không được tự tuyên bố “đơn đã tạo thành công”. Có thể cần lan truyền lỗi để tầng quản lý giao dịch quyết định rollback hoặc đánh dấu không nhất quán, tùy cơ chế giao dịch thật sự được triển khai.

**Không suy luận rằng `throws` tự rollback**. Java exceptions không tự hoàn tác thay đổi tệp, dữ liệu hay gọi mạng. Rollback là cơ chế giao dịch hoặc mã bù trừ được hệ thống xây dựng thêm.

## 5. Sơ đồ quyết định nhanh

Với một exception cụ thể, trả lời theo thứ tự:

1. **Đây có phải nhánh nghiệp vụ dự kiến không?** Nếu là “hết hàng” hoặc “không tìm thấy” thường lệ, cân nhắc trả về kiểu kết quả rõ ràng; không nhất thiết dùng exception để điều khiển luồng.
2. **Tầng hiện tại có phương án khôi phục có thể kiểm chứng không?** Nếu có, `catch` đúng loại và thực hiện phương án.
3. **Tầng này có đủ trách nhiệm tạo phản hồi cho người dùng/hệ thống gọi không?** Nếu có, bắt và chuyển sang phản hồi hoặc trạng thái thất bại phù hợp.
4. **Tầng này chỉ biết bổ sung ngữ cảnh, không phục hồi được?** Có thể bắt để log/cleanup rồi `throw e`, hoặc wrap kèm cause nếu hợp đồng tầng mới yêu cầu.
5. **Không làm được gì có ích?** Không tạo `catch` dư thừa; cho exception lan lên caller và khai báo checked exception nếu cần.
6. **Exception thuộc nhánh `Error` nghiêm trọng?** Mã nghiệp vụ thông thường không nên nuốt lỗi để cố vận hành bình thường; ưu tiên điều tra nguyên nhân môi trường/JVM và chính sách vận hành.

Nói ngắn gọn theo ngữ cảnh thiết kế: **catch để quyết định một hành động hợp lệ; throws để giữ nguyên trách nhiệm xử lý cho bên gọi**. Chọn theo khả năng xử lý, không chọn chỉ để hết gạch đỏ trong IDE.

## 6. Chương trình chạy được: `catch` khi có fallback, `throws` khi chưa có

Để không phụ thuộc hệ thống tệp bên ngoài, ví dụ sau mô phỏng một thao tác I/O bằng `IOException`. Lưu toàn bộ thành **`CatchOrThrowsDemo.java`**:

```java
import java.io.IOException;

public class CatchOrThrowsDemo {
    static String loadPrimary(boolean available) throws IOException {
        if (!available) {
            throw new IOException("Nguồn chính không sẵn sàng");
        }
        return "primary-config";
    }

    // Không biết chính sách: giữ IOException cho caller.
    static String loadRequired(boolean available) throws IOException {
        return loadPrimary(available);
    }

    // Biết fallback đã được phép: bắt và dùng dữ liệu dự phòng.
    static String loadOptional(boolean available) {
        try {
            return loadPrimary(available);
        } catch (IOException e) {
            return "default-config";
        }
    }

    public static void main(String[] args) {
        System.out.println("Tùy chọn: " + loadOptional(false));
        System.out.println("Bắt buộc: " + loadOptional(true));

        try {
            System.out.println(loadRequired(false));
        } catch (IOException e) {
            System.out.println("Không thể khởi động: " + e.getMessage());
        }

        System.out.println("Main đã xử lý xong");
    }
}
```

Biên dịch/chạy trên Java 17+:

```bash
javac -encoding UTF-8 --release 17 CatchOrThrowsDemo.java
java CatchOrThrowsDemo
```

**Stdout chính xác** khi hiển thị UTF-8:

```text
Tùy chọn: default-config
Bắt buộc: primary-config
Không thể khởi động: Nguồn chính không sẵn sàng
Main đã xử lý xong
```

Ở `loadOptional(false)`, phương án dự phòng là một phần hợp đồng nên tầng hiện tại chủ động `catch` và trả `"default-config"`. Ở `loadRequired(false)`, tầng trung gian chỉ có nhiệm vụ nạp dữ liệu, nên `throws IOException` và caller tại `main` xử lý.

Tên hai dòng đầu chỉ nhằm minh họa kết quả in: dòng “Bắt buộc: primary-config” dùng lệnh `loadOptional(true)` để thể hiện đường đọc thành công có thể so sánh với fallback. Quyết định thực sự về cấu hình bắt buộc nằm ở lời gọi `loadRequired(false)` sau đó.

Việc mô phỏng bằng `IOException` phục vụ bài học về luồng điều khiển; chương trình không chạm vào tệp hay kết nối thật nên đầu ra có thể kiểm tra chính xác.

## 7. `catch` hẹp để không che các sự cố khác

Một API có thể ném nhiều ngoại lệ trong cùng họ. Ví dụ đọc tệp với `Files.readString` có thể ném `NoSuchFileException` khi tệp không tồn tại, hoặc những `IOException` khác khi thao tác thất bại vì quyền truy cập hay thiết bị.

Nếu chỉ **tệp không tồn tại** được phép chuyển sang fallback, cần xử lý hẹp:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

class OptionalFileConfig {
    static String read(Path path) throws IOException {
        try {
            return Files.readString(path);
        } catch (NoSuchFileException e) {
            return "default";
        }
    }
}
```

Đây là **lớp minh họa không có `main`**. Khi đúng một `NoSuchFileException` phát sinh, tầng này dùng fallback; những `IOException` khác tiếp tục được khai báo bằng `throws IOException`. Điều đó phân biệt nhánh dự kiến với những lỗi kỹ thuật mà mã không đủ thông tin khắc phục.

Lưu ý: một file đang tồn tại vẫn có thể mất giữa thời điểm kiểm tra và đọc; dùng `Files.exists(path)` trước rồi đọc không thay thế xử lý ngoại lệ tại thao tác thực tế. Tránh giả định rằng kiểm tra trước đã loại bỏ mọi lỗi I/O.

### Thứ tự các nhánh `catch`

Khi nhiều handler có quan hệ kế thừa, nhánh cụ thể phải đứng trước:

```java
try {
    readSomething();
} catch (NoSuchFileException e) {
    useFallback();
} catch (IOException e) {
    reportIoFailure(e);
}
```

Đây là khung minh họa. Nếu đảo `IOException` lên trước thì `NoSuchFileException` phía sau sẽ là handler không thể tới vì lớp cha đã bắt mọi instance của lớp con. Java phát hiện điều này tại biên dịch.

## 8. Bắt rồi ném lại: `catch` và `throws` có thể cùng xuất hiện

Một phương thức có thể cần log/ngữ cảnh tại tầng hiện tại nhưng vẫn phải lan truyền checked exception. Ví dụ độc lập, lưu thành **`RethrowDecisionDemo.java`**:

```java
import java.io.IOException;

public class RethrowDecisionDemo {
    static void read() throws IOException {
        throw new IOException("Không đọc được");
    }

    static void service() throws IOException {
        try {
            read();
        } catch (IOException e) {
            System.out.println("Service ghi nhận lỗi");
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (IOException e) {
            System.out.println("Main xử lý: " + e.getMessage());
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 RethrowDecisionDemo.java
java RethrowDecisionDemo
```

**Stdout chính xác:**

```text
Service ghi nhận lỗi
Main xử lý: Không đọc được
```

`service()` có `catch` để ghi nhận lỗi và `throw e` để **ném lại chính đối tượng ngoại lệ**, vì tầng này không phục hồi. Nó phải khai báo `throws IOException` do lỗi checked tiếp tục thoát ra. `main()` là nơi handler cuối có thể quyết định phản hồi.

Nếu `service()` không cần ghi nhận gì, có thể viết ngắn hơn:

```java
static void service() throws IOException {
    read();
}
```

Đây là **phương thức thay thế minh họa**, thuộc cùng lớp với `read()`, không phải đoạn cần nối thêm vào chương trình có sẵn. Bỏ handler vô ích giúp mã rõ hơn.

## 9. Khi nào nên wrap thay vì `throw e`?

Đôi khi API ở một tầng khác không nên công bố các chi tiết của tầng thấp. Ví dụ tầng repository phát sinh `IOException` nhưng tầng dịch vụ muốn công bố “không thể nạp thông tin thanh toán” bằng một loại ngoại lệ ứng dụng rõ ràng. Khi đó có thể **bọc ngoại lệ gốc** trong một exception mới và giữ `cause`.

Ví dụ minh họa:

```java
import java.io.IOException;

class PaymentConfigurationException extends RuntimeException {
    PaymentConfigurationException(String message, Throwable cause) {
        super(message, cause);
    }
}

class PaymentConfigurationService {
    static String load() {
        try {
            return readFromSource();
        } catch (IOException e) {
            throw new PaymentConfigurationException(
                    "Không thể nạp cấu hình thanh toán", e);
        }
    }

    static String readFromSource() throws IOException {
        throw new IOException("Nguồn cấu hình không truy cập được");
    }
}
```

Đây là lớp hợp lệ **không có `main`**. `load()` không khai báo `throws IOException` vì bắt và chuyển nó thành một unchecked exception mới. Caller nhận `PaymentConfigurationException`, còn `getCause()` là `IOException` ban đầu.

Việc wrapping là **thay đổi hợp đồng**, không phải chỉ là “tắt checked exception”. Chỉ dùng nếu tầng hiện tại có lý do giữ trừu tượng và bên gọi có chính sách xử lý phù hợp. Nếu vẫn cần caller xử lý riêng `IOException`, tiếp tục `throws IOException` hoặc một loại checked exception mới có thể thích hợp hơn.

Không viết `throw new RuntimeException(e.getMessage())` khi cần chẩn đoán nguyên nhân, vì chuỗi message **không chứa** đầy đủ stack trace và cause gốc. Constructor có `cause` như `new RuntimeException("...", e)` giúp giữ dấu vết.

## 10. `throws` không thay thế cleanup

Một phương thức có `throws IOException` vẫn phải bảo vệ tài nguyên đang nắm giữ. Nếu mở file, socket hoặc đối tượng `AutoCloseable` rồi để exception đi lên, tài nguyên không được tự giải phóng chỉ vì có `throws`.

Dùng `try-with-resources` để đóng tài nguyên khi rời phạm vi, cả trên đường hoàn thành bình thường và nhiều đường ném ngoại lệ. Đặc biệt, tài nguyên được đóng theo **thứ tự ngược khai báo**.

Lưu ví dụ độc lập **`ThrowsResourceDemo.java`**:

```java
import java.io.IOException;

public class ThrowsResourceDemo {
    static class Session implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("Đã đóng session");
        }
    }

    static void work() throws IOException {
        try (Session session = new Session()) {
            System.out.println("Đang làm việc");
            throw new IOException("Không hoàn tất");
        }
    }

    public static void main(String[] args) {
        try {
            work();
        } catch (IOException e) {
            System.out.println("Caller: " + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 ThrowsResourceDemo.java
java ThrowsResourceDemo
```

**Stdout chính xác:**

```text
Đang làm việc
Đã đóng session
Caller: Không hoàn tất
```

`work()` không `catch`, nhưng vẫn dọn dẹp bằng `try-with-resources`. Sau khi đóng `session`, exception đi lên caller. Tương tự, nếu `close()` cũng ném exception trong lúc thân `try` đã ném, lỗi khi đóng có thể được đính kèm dạng **suppressed exception** trong exception chính; caller có thể kiểm tra bằng `getSuppressed()`.

`finally` cũng có thể dùng cho việc dọn dẹp, nhưng đừng đặt `return` hoặc ném lỗi mới một cách vô ý bên trong `finally` vì chúng có thể che lỗi chính đang lan truyền. Và không có cleanup nào bảo đảm chạy khi JVM bị chấm dứt cưỡng bức hoặc gặp sự cố nghiêm trọng.

## 11. Checked và unchecked quyết định nghĩa vụ biên dịch, không quyết định khả năng phục hồi

### Checked exception

Ví dụ `IOException` hoặc `SQLException` (khi dùng API có thể ném chúng) là checked exception. Nếu phương thức không xử lý, nó phải khai báo `throws` tương ứng hoặc kiểu cha theo luật Java. Đây là **quy tắc ngôn ngữ**, không phải tuyên bố rằng checked exception luôn có thể phục hồi.

Một `IOException` có thể phát sinh khi tệp cấu hình cốt lõi bị lỗi. Dù đã khai báo `throws IOException`, một ứng dụng không có fallback hợp lệ vẫn phải xem đó là lỗi cần chấm dứt thao tác.

### Unchecked exception

`IllegalArgumentException`, `NullPointerException` và `IllegalStateException` là lớp con của `RuntimeException`, nên caller **không bắt buộc** dùng `catch` hoặc `throws`. Nếu biết cách chuyển một lỗi parse thành thông báo nhập liệu, vẫn có thể `catch (NumberFormatException e)` chủ động. Nếu đó là bug sử dụng API sai, nên sửa nơi gọi hơn là nuốt ngoại lệ.

`Error` và lớp con cũng unchecked, nhưng thường thể hiện sự cố môi trường/JVM hoặc bất biến nghiêm trọng; mã nghiệp vụ thông thường không nên `catch (Throwable e)` chỉ để chặn mọi lỗi rồi tiếp tục.

### Vì sao `throws RuntimeException` hiếm khi cần

Một chữ ký:

```java
static int parse(String text) throws NumberFormatException {
    return Integer.parseInt(text);
}
```

là hợp lệ, nhưng `throws NumberFormatException` **không làm bên gọi phải bắt** loại unchecked này. Nếu muốn tài liệu hóa rõ các tiền điều kiện, có thể dùng JavaDoc `@throws` hoặc mô tả hợp đồng; thêm `throws` vào chữ ký có thể hữu ích để người đọc nhận biết, nhưng không thay quy tắc biên dịch.

Không nên nhầm “không có `throws`” với “không thể có exception”: unchecked exception vẫn có thể xảy ra lúc chạy.

## 12. `throws Exception` và `catch (Exception e)`: vì sao nên cẩn trọng?

Hai cách viết rộng này đều hợp lệ trong một số tình huống, nhưng có thể làm mất ý nghĩa loại lỗi và khiến hệ thống khó xử lý chính xác.

### Khai báo quá rộng

```java
static void loadEverything() throws Exception {
    readConfig();
}
```

Đây là mã minh họa, `readConfig()` cần được định nghĩa. Nếu thực tế chỉ có `IOException` là checked exception thì chữ ký `throws IOException` cho caller thông tin hữu ích hơn. Khi khai báo `throws Exception`, caller phải bắt/khai báo kiểu checked rộng hơn, ngay cả khi thao tác hiện chỉ dùng lỗi I/O.

Trong ứng dụng demo hoặc tại ranh giới `main`, chữ ký rộng đôi khi giúp thử nghiệm nhanh, nhưng API công khai của thư viện nên bộc lộ hợp đồng cụ thể và ổn định.

### Bắt quá rộng

```java
try {
    execute();
} catch (Exception e) {
    return fallback();
}
```

Đây là mã minh họa, chỉ đúng khi API thật sự cho phép fallback với **mọi** lớp con của `Exception` có thể phát sinh. `catch (Exception e)` gồm checked exception và `RuntimeException`, có thể che bug mà tầng hiện tại không biết khắc phục. Nó cũng **không** bắt `Error`.

Mức bắt rộng có thể hợp lý tại một ranh giới cuối, ví dụ framework quản lý request/job và phải ghi nhận mọi thất bại để giữ vòng phục vụ hoạt động. Khi đó việc chọn phản hồi, báo lỗi và trạng thái tiếp theo vẫn phải được thiết kế cụ thể, thay vì âm thầm coi mọi ngoại lệ là thành công.

## 13. Precise rethrow: bắt kiểu rộng nhưng vẫn `throws` hẹp

Từ Java 7, khi tham số `catch` là `final` hoặc **effectively final** (không bị gán lại), Java có thể phân tích chính xác hơn các checked exception mà lệnh `throw e` có thể truyền ra. Do đó, không phải cứ `catch (Exception e)` rồi `throw e` là bắt buộc khai báo `throws Exception`.

Ví dụ chạy được, lưu **`PreciseRethrowChoiceDemo.java`**:

```java
import java.io.IOException;

public class PreciseRethrowChoiceDemo {
    static void read() throws IOException {
        throw new IOException("Lỗi khi đọc");
    }

    static void relay() throws IOException {
        try {
            read();
        } catch (Exception e) {
            System.out.println("Relay ghi nhận lỗi");
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            relay();
        } catch (IOException e) {
            System.out.println("Caller: " + e.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 PreciseRethrowChoiceDemo.java
java PreciseRethrowChoiceDemo
```

**Stdout chính xác:**

```text
Relay ghi nhận lỗi
Caller: Lỗi khi đọc
```

Mặc dù handler khai báo `catch (Exception e)`, phương thức `relay` chỉ cần `throws IOException` vì compiler xác định tập checked exception có thể thoát ra từ `try` trong ví dụ và biến `e` không bị gán lại. Nếu gán lại `e` trong handler, việc thu hẹp kiểu theo quy tắc precise rethrow có thể không còn áp dụng, và `throw e` có thể bị kiểm tra theo kiểu khai báo rộng hơn.

Đây là một tính năng phân tích tại **compile time**; đối tượng exception được ném ở runtime vẫn là cùng đối tượng được `catch` nhận. Không nên dùng `catch (Exception e)` ở khắp nơi chỉ vì precise rethrow tồn tại: bắt loại cụ thể thường vẫn dễ hiểu và tránh xử lý sai phạm vi.

## 14. Cẩn trọng với `InterruptedException`

`InterruptedException` là checked exception xuất hiện trong những thao tác có thể chờ hoặc bị ngắt, ví dụ `Thread.sleep`. Nó còn mang ý nghĩa **tín hiệu hợp tác hủy/chấm dứt công việc**; cách xử lý thường khác với lỗi I/O.

Nếu tầng hiện tại có thể khai báo `throws InterruptedException` và hợp đồng cho phép, **truyền tiếp** thường là cách rõ ràng để caller quyết định việc dừng thao tác.

Nếu một ranh giới không thể khai báo checked exception này và phải bắt, thông thường cần **khôi phục trạng thái interrupt** bằng `Thread.currentThread().interrupt()` trước khi kết thúc nhánh xử lý, để tầng cao hơn còn nhận biết tín hiệu. Trong Java, nhiều phương thức chặn khi ném `InterruptedException` sẽ xóa trạng thái interrupt của thread.

Ví dụ phương thức minh họa:

```java
static boolean pause() {
    try {
        Thread.sleep(1000);
        return true;
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return false;
    }
}
```

Đây là **phương thức minh họa không có `main`**. `false` ở đây là một kết quả đã được hợp đồng giả định để biểu diễn thao tác bị hủy; caller phải hiểu và xử lý. Không sử dụng mẫu này ở mọi API một cách máy móc: có trường hợp nên `throws InterruptedException` thay vì chuyển thành boolean, và có ranh giới cần thực hiện thêm cleanup. Không tự động dùng `catch (Exception e)` để vô tình nuốt tín hiệu interrupt.

## 15. Chuyển lỗi tại ranh giới nhưng giữ nguyên nhân

Mã Java thuần không quy định một exception phải trở thành status HTTP cụ thể. Ở ranh giới giao tiếp hoặc module nghiệp vụ, bạn có thể chuyển một lỗi tầng dưới thành loại lỗi có ý nghĩa hơn mà vẫn giữ `cause`, hoặc trả một đối tượng kết quả khi hợp đồng quy định đây là nhánh dự kiến.

Lưu ý khi chuyển lỗi:

- **Giữ ý nghĩa:** sự cố database là lỗi kỹ thuật; không giả vờ là “không tìm thấy” chỉ vì không đọc được dữ liệu.
- **Giữ nguyên nhân:** constructor `new SomeException("...", cause)` giúp bảo toàn dấu vết và stack trace của lỗi gốc trong chuỗi `getCause()`.
- **Không làm lộ chi tiết nội bộ:** stack trace và bí mật cấu hình không nên đưa thẳng vào thông báo người dùng.
- **Tránh log trùng lặp ở mọi tầng:** chọn nơi có đủ ngữ cảnh; mỗi tầng không bắt buộc in cả stack trace trước khi ném tiếp.
- **Chọn chính sách cuối cùng:** hủy request, ghi job thất bại, thử lại có giới hạn hoặc thông báo thiếu dữ liệu là việc của ranh giới biết trạng thái tổng thể.

Khi đổi checked exception sang unchecked wrapper, bên gọi không còn nghĩa vụ `catch-or-declare` do compiler, nhưng **sự cố vẫn tồn tại** và thiết kế vẫn cần điểm xử lý cuối. Nếu thư viện công bố checked exception như một phần quan trọng của API, thay đổi kiểu ngoại lệ có thể ảnh hưởng caller và kiểm thử; hãy cân nhắc khả năng tương thích.

## 16. Ngoại lệ trong `finally` và lỗi bị che khuất

Một quyết định `catch` hay `throws` tốt vẫn có thể thất bại nếu cleanup tạo lỗi mới và che đi lỗi quan trọng.

Ví dụ khung:

```java
try {
    throw new IllegalArgumentException("Lỗi chính");
} finally {
    throw new IllegalStateException("Lỗi cleanup");
}
```

Nếu đoạn này được đặt trong một phương thức hợp lệ, exception cuối được truyền ra là `IllegalStateException` từ `finally`. Exception chính có thể bị mất khỏi đường chẩn đoán nếu không được lưu riêng. Do đó:

1. Ưu tiên `try-with-resources` với `AutoCloseable`.
2. Đừng viết `return` trong `finally`; nó có thể ghi đè exception hoặc giá trị return đang chờ.
3. Nếu cleanup có thể thất bại, xác định cách giữ nguyên nhân và suppressed exception.
4. Không để lỗi cleanup khiến caller hiểu rằng công việc chính thành công.

Một lựa chọn `throws` chính xác phải đi kèm thực hành quản lý tài nguyên đúng; không thể dùng mệnh đề `throws` để thay cho việc đóng tệp, socket hay trả tài nguyên.

## 17. Kiểm thử cả hai nhánh quyết định

Kiểm thử ngoại lệ không chỉ kiểm tra chương trình “không crash”. Cần xác nhận **hợp đồng thực tế** ở từng tầng.

| Trường hợp cần kiểm tra | Điều mong đợi |
| --- | --- |
| Đường thành công | Phương thức trả dữ liệu đúng, không chạy `catch` |
| Lỗi có fallback được phép | `catch` chọn đúng fallback, dữ liệu/side effect nhất quán |
| Lỗi không có fallback | Checked exception được khai báo và lan tới caller; không có thành công giả |
| Lỗi thuộc loại khác | Handler hẹp không nuốt ngoại lệ ngoài phạm vi |
| Handler chỉ log rồi rethrow | Caller vẫn nhận đúng exception hoặc hợp đồng wrapper có cause |
| Tài nguyên bị lỗi khi đang sử dụng | Tài nguyên được cố đóng; lỗi chính/các suppressed được bảo toàn phù hợp |
| Interrupted operation | Trạng thái interrupt được xử lý đúng hợp đồng |
| Lỗi nghiệp vụ dự kiến | Trả kết quả domain hoặc mã lỗi tương ứng; không nhất thiết ném exception |

Một bài test tốt còn kiểm tra rằng một handler rộng không biến các bug như `NullPointerException` thành giá trị fallback có vẻ hợp lệ. Nếu fallback có thể mất dữ liệu, thay đổi giao dịch hoặc ảnh hưởng bảo mật, cần test các bất biến sau lỗi chứ không chỉ kiểm tra giá trị trả về.

## 18. Các sai lầm thường gặp

**Sai lầm 1: Bắt tất cả rồi bỏ qua.**

```java
try {
    save();
} catch (Exception ignored) {
    // Không làm gì.
}
```

Đây là khung minh họa, `save()` chưa được định nghĩa. Nếu `save()` thất bại, caller có thể tiếp tục như đã lưu thành công. Chỉ bỏ qua exception cụ thể khi hợp đồng bảo đảm việc bỏ qua thật sự an toàn và có lý do rõ ràng.

**Sai lầm 2: Dùng `throws Exception` để khỏi hiểu lỗi.** Chữ ký quá rộng làm caller khó phân biệt I/O, lỗi dữ liệu và các điều kiện khác. Khai báo loại checked phù hợp với hợp đồng khi khả thi.

**Sai lầm 3: Dùng `catch` chỉ để ghi log và ném lại ở mọi tầng.** Các bản ghi trùng nhau khiến hệ thống khó quan sát. Hãy log tại nơi có giá trị chẩn đoán hoặc thêm ngữ cảnh, rồi giữ exception gốc hay wrapper có cause.

**Sai lầm 4: Dùng `catch (Exception e)` làm fallback cho mọi tình huống.** Có thể che những `RuntimeException` do bug; không phải exception nào cũng có thể khôi phục.

**Sai lầm 5: Nghĩ `throws` sẽ tự hiển thị lỗi, retry hay rollback.** `throws` chỉ là khai báo; giao diện, retry và giao dịch cần code/cơ chế riêng.

**Sai lầm 6: Chuyển checked sang unchecked chỉ để compiler không báo lỗi.** Lỗi không biến mất; chỉ nghĩa vụ biên dịch thay đổi. Cần một hợp đồng API thích hợp và giữ `cause`.

**Sai lầm 7: Quên đóng tài nguyên khi để exception lan truyền.** Dùng `try-with-resources` hoặc cleanup phù hợp để tránh rò rỉ tài nguyên.

**Sai lầm 8: Nuốt `InterruptedException`.** Việc chặn tín hiệu ngắt có thể cản khả năng hủy công việc; truyền tiếp hoặc khôi phục interrupt khi phù hợp.

**Sai lầm 9: Coi “không tìm thấy dữ liệu” luôn là exception.** Nếu đây là kết quả dự kiến, `Optional` hoặc kiểu kết quả domain có thể biểu diễn rõ hơn.

**Sai lầm 10: Cố bắt `Error` nghiêm trọng như một lỗi nghiệp vụ.** Các lỗi ở mức JVM/hệ thống như `OutOfMemoryError` thường không cho phép tầng nghiệp vụ tiếp tục an toàn.

## 19. Câu hỏi tự kiểm tra

**1. Hàm đọc tệp ném `IOException`, tầng hiện tại không biết nên dùng cấu hình nào. Nên `catch` hay `throws`?**  
Nên cho exception lan truyền bằng `throws IOException`, để tầng biết chính sách quyết định.

**2. Tầng giao diện bắt được `NumberFormatException` do người dùng nhập chữ vào ô số. Có cần tiếp tục `throws` không?**  
Không nhất thiết. Nếu tầng giao diện có thể trả lỗi xác thực phù hợp, đó là nơi `catch` có giá trị.

**3. Một phương thức có thể ném `IllegalArgumentException` nhưng không có `throws`. Có sai không?**  
Không. `IllegalArgumentException` là unchecked exception nên không bắt buộc khai báo.

**4. `catch (IOException e) { throw e; }` có nghĩa lỗi đã xử lý xong không?**  
Không. Handler chỉ ném lại lỗi; phương thức chứa handler vẫn có thể thoát bất thường và cần khai báo checked exception.

**5. Khi nào fallback là nguy hiểm?**  
Khi nó che tình huống cần cảnh báo, làm mất dữ liệu hoặc khiến bên gọi tưởng thao tác thành công dù trạng thái không hợp lệ.

**6. Có thể vừa `catch` loại A vừa `throws` loại B trong cùng phương thức không?**  
Có. Bạn có thể xử lý một số lỗi và để những lỗi khác tiếp tục lan theo hợp đồng.

**7. Nếu đang dùng `try-with-resources` mà thân `try` ném ngoại lệ, `throws` có ngăn việc gọi `close()` không?**  
Không. Java cố đóng tài nguyên trước khi exception tiếp tục thoát khỏi cấu trúc.

**8. `throws IOException` có tự retry thao tác I/O không?**  
Không. Retry cần chính sách và code riêng, đặc biệt khi thao tác có side effect.

**9. Nếu muốn chuyển `IOException` thành `PaymentConfigurationException`, làm sao giữ dấu vết gốc?**  
Tạo exception mới với nguyên nhân: `new PaymentConfigurationException("...", e)` và để caller truy `getCause()`.

**10. Catch rộng ở ranh giới cuối có luôn sai không?**  
Không. Một ranh giới điều phối có thể cần bắt rộng để ghi nhận thất bại và giữ vòng phục vụ hoạt động; phải có chính sách an toàn và tránh biến lỗi nội bộ thành thành công giả.

## 20. Checklist ra quyết định khi viết API Java

Trước khi viết `catch` hay `throws`, hãy rà soát:

1. **Ý nghĩa lỗi:** exception này biểu thị tình huống kỹ thuật bất thường, vi phạm hợp đồng hay kết quả nghiệp vụ dự kiến?
2. **Nơi có thông tin:** tầng hiện tại có đủ hiểu biết để khắc phục mà vẫn giữ đúng dữ liệu, bất biến và side effect?
3. **Hợp đồng trả về:** caller cần biết kết quả gì, có loại fallback hợp lệ không, có cần kết quả dạng `Optional` hoặc `Result`?
4. **Kiểu lỗi:** checked exception nào cần khai báo; unchecked exception nào nên để lan truyền hoặc xử lý chủ động?
5. **Phạm vi `catch`:** có thể bắt loại cụ thể hơn để không nuốt các sự cố khác?
6. **Nếu ném lại:** có giữ cùng đối tượng bằng `throw e` hay có lý do wrap với `cause`? Có thêm giá trị thực sự trước khi ném?
7. **Tài nguyên:** file/socket/session có được đóng đúng không, exception cleanup có thể che lỗi gốc không?
8. **Tín hiệu hủy:** có `InterruptedException` cần truyền tiếp hoặc restore interrupt không?
9. **Ranh giới cuối:** ai hiển thị thông báo, đánh dấu job thất bại, quyết định retry hoặc rollback?
10. **Kiểm thử:** cả đường thành công, fallback hợp lệ, lan truyền lỗi, cleanup và lỗi ngoài phạm vi có được kiểm chứng?

## 21. Ghi nhớ

**Nên `catch` khi tầng hiện tại có hành động xử lý cụ thể, hợp lệ và giữ được trạng thái hệ thống; nên tiếp tục `throws` khi bên gọi mới có đủ thông tin hoặc chính sách để xử lý.** Bắt để ghi nhận rồi `throw e` vẫn là **lan truyền lỗi**, còn wrap phải giữ `cause` nếu muốn bảo toàn nguyên nhân.

Checked exception buộc mã tuân thủ `catch-or-declare`; unchecked exception không có nghĩa vụ đó nhưng vẫn cần hợp đồng và trách nhiệm xử lý rõ ràng. `throws` không tự sửa lỗi, retry, rollback hay cleanup. Chính việc hiểu nơi phát hiện, nơi phục hồi và nơi quyết định phản hồi giúp luồng exception trở nên chính xác, dễ kiểm thử và dễ bảo trì.
