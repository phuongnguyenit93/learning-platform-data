# Ném ngoại lệ mới nhưng làm mất `cause` trong Java

Khi xử lý lỗi, lập trình viên thường muốn chuyển một ngoại lệ kỹ thuật thành ngoại lệ có ý nghĩa hơn với tầng gọi. Ví dụ, `IOException("configuration file missing")` có thể được chuyển thành `IllegalStateException("Cannot start application")`. Đây là kỹ thuật **exception translation / exception wrapping** hợp lệ. Sai lầm xuất hiện khi tạo ngoại lệ mới **chỉ từ thông điệp** mà không gắn ngoại lệ gốc làm `cause`:

```java
catch (IOException error) {
    throw new IllegalStateException("Startup failed: " + error.getMessage());
}
```

Đoạn trên là mã minh họa trong một phương thức có thể ném `IOException`. Nó tạo một `IllegalStateException` với stack trace riêng, nhưng `getCause()` trả `null`. Người điều tra có thể biết việc khởi động thất bại mà không còn thấy chuỗi nguyên nhân, loại `IOException` gốc, stack trace tại nơi lỗi phát sinh hoặc các suppressed exceptions gắn với lỗi đó.

Cách bọc thường phù hợp hơn là:

```java
catch (IOException error) {
    throw new IllegalStateException("Startup failed", error);
}
```

Constructor nhận `Throwable cause` giữ **tham chiếu tới ngoại lệ gốc**. Stack trace của wrapper mô tả nơi chuyển đổi lỗi, còn `Caused by:` cho phép lần lại nơi ngoại lệ bên dưới xuất hiện. Bài này giải thích hậu quả của việc làm mất `cause`, những trường hợp nên bọc hoặc truyền tiếp ngoại lệ, và cách giữ chuỗi lỗi qua API, logger, tài nguyên và công việc bất đồng bộ.

## 1. Phân biệt thông điệp, cause và stack trace

Một đối tượng `Throwable` thường có những thông tin quan trọng sau:

| Thông tin | API | Tác dụng |
| --- | --- | --- |
| Loại ngoại lệ | `error.getClass()` | Cho biết đây là `IOException`, `SQLException`, `IllegalArgumentException`... |
| Thông điệp | `error.getMessage()` | Chuỗi ngắn mô tả lỗi; có thể là `null` |
| Stack trace | `error.getStackTrace()` | Thông tin lời gọi nơi stack được ghi nhận |
| Nguyên nhân | `error.getCause()` | Ngoại lệ bên dưới được liên kết khi tạo hoặc khởi tạo nguyên nhân |
| Lỗi phụ | `error.getSuppressed()` | Các ngoại lệ bổ sung, ví dụ lỗi `close()` trong `try-with-resources` |

`getMessage()` là **một chuỗi**, không phải bản sao của cả `Throwable`. Tạo `new IllegalStateException(error.getMessage())` không bảo toàn `getCause()`, stack trace của `error` hay suppressed exceptions của nó.

Một chuỗi nguyên nhân đúng có thể trông như:

```text
IllegalStateException: Cannot start application
  Caused by: IOException: configuration file missing
      at ConfigRepository.read(...)
      at StartupService.initialize(...)
```

Đây là dạng minh họa, không phải stdout bảo đảm về số dòng hoặc tên phương thức của mọi ứng dụng. Wrapper mang ngữ cảnh nghiệp vụ, còn cause giữ dấu vết kỹ thuật.

Khi cause bị bỏ:

```text
IllegalStateException: Cannot start application: configuration file missing
  at StartupService.initialize(...)
```

Thông điệp vẫn nhắc tới việc thiếu file, nhưng loại `IOException`, vị trí khởi phát chính xác và các nguyên nhân sâu hơn có thể đã biến mất khỏi đối tượng ngoại lệ mới. Một logger ở tầng cao **không thể tự suy ra lại** dữ liệu đã không được chuyển tiếp.

## 2. Bảng so sánh các cách ném lại

Giả sử đang ở trong `catch (IOException error)`:

| Mã | Đối tượng ném ra | Giữ được cause gốc? | Ý nghĩa |
| --- | --- | --- | --- |
| `throw error;` | Chính `IOException` đã bắt | Không tạo wrapper; giữ nguyên đối tượng và chuỗi cause sẵn có | Truyền nguyên lỗi khi hợp đồng cho phép |
| `throw new IllegalStateException("Cannot load");` | Wrapper mới | **Không** | Thay loại lỗi và mất nguyên nhân |
| `throw new IllegalStateException(error.getMessage());` | Wrapper mới | **Không** | Sao chép message nhưng mất thông tin ngoại lệ gốc |
| `throw new IllegalStateException("Cannot load", error);` | Wrapper mới | **Có** | Thêm ngữ cảnh và giữ `IOException` |
| `throw new RuntimeException(error);` | Wrapper mới | **Có** | Giữ cause; thông điệp mặc định thường suy từ `error.toString()` |
| `throw new IllegalStateException("Cannot load", error.getCause());` | Wrapper mới | Không giữ **đối tượng `error`** | Có thể vô tình bỏ một tầng lỗi hữu ích |
| `throw new IllegalStateException(error.toString());` | Wrapper mới | **Không** | Chỉ sao chép biểu diễn chuỗi, không giữ exception |

Các đoạn trong bảng là câu lệnh minh họa, không phải các chương trình hoàn chỉnh. Việc dùng `throw error;` phụ thuộc vào chữ ký `throws` và cơ chế kiểm tra checked exceptions. Java không cho tự do ném `IOException` ra khỏi một phương thức không được phép khai báo hoặc truyền ngoại lệ này.

**Quy tắc:** nếu phải tạo wrapper để thay đổi tầng trừu tượng, hãy ưu tiên constructor nhận cả **thông điệp có ngữ cảnh** và **`Throwable cause`**.

## 3. Ví dụ Java 17+: thấy trực tiếp dữ liệu bị mất

Tạo tệp **`LostCauseDemo.java`**:

```java
import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;

public class LostCauseDemo {
    static void readConfiguration() throws IOException {
        throw new IOException("configuration file missing");
    }

    static void startWrong() {
        try {
            readConfiguration();
        } catch (IOException original) {
            throw new IllegalStateException(
                    "startup failed: " + original.getMessage());
        }
    }

    static void startCorrect() {
        try {
            readConfiguration();
        } catch (IOException original) {
            throw new IllegalStateException("startup failed", original);
        }
    }

    static void inspect(String label, Runnable action) {
        try {
            action.run();
        } catch (IllegalStateException error) {
            StringWriter buffer = new StringWriter();
            error.printStackTrace(new PrintWriter(buffer));
            boolean hasOriginalTrace = buffer.toString().contains(
                    "Caused by: java.io.IOException: configuration file missing");
            String causeType = error.getCause() == null
                    ? "null"
                    : error.getCause().getClass().getSimpleName();

            System.out.println(label + ".type="
                    + error.getClass().getSimpleName());
            System.out.println(label + ".cause=" + causeType);
            System.out.println(label + ".originalTrace="
                    + hasOriginalTrace);
        }
    }

    public static void main(String[] args) {
        inspect("wrong", LostCauseDemo::startWrong);
        inspect("correct", LostCauseDemo::startCorrect);
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac --release 17 LostCauseDemo.java
java LostCauseDemo
```

Đầu ra:

```text
wrong.type=IllegalStateException
wrong.cause=null
wrong.originalTrace=false
correct.type=IllegalStateException
correct.cause=IOException
correct.originalTrace=true
```

**Giải thích từng bước:**

1. `readConfiguration()` tạo và ném `IOException("configuration file missing")`.
2. `startWrong()` bắt lỗi nhưng chỉ chuyển nội dung thông điệp thành chuỗi mới. `IllegalStateException` của nó không giữ đối tượng `IOException`, nên `getCause() == null`.
3. `startCorrect()` tạo `IllegalStateException` với tham số thứ hai là **ngoại lệ gốc**. Vì vậy `getCause()` là `IOException`.
4. `printStackTrace(...)` trên wrapper đúng trình bày thêm khối `Caused by: ...`, cho phép thấy lỗi bên dưới. Chương trình kiểm tra bằng một đoạn chuỗi ổn định thay vì in toàn bộ stack có số dòng khác nhau theo môi trường.

Ví dụ chỉ cho thấy **mất nguyên nhân do cách tạo wrapper**; nó không đo hiệu năng, không chứng minh rằng mọi logger đều tự in stack trace, và không yêu cầu ứng dụng dùng `IllegalStateException` cho tất cả loại lỗi. Trong dự án thật, chọn loại exception theo hợp đồng API.

## 4. Tại sao mất cause là lỗi nghiêm trọng khi chẩn đoán?

### 4.1. Mất vị trí phát sinh lỗi thật

Wrapper được khởi tạo trong `catch`, nên stack trace mới thường bắt đầu tại nơi `new IllegalStateException(...)`. Nếu mất `cause`, phần stack gắn với `IOException` ban đầu không còn được tham chiếu để ghi ra cùng sự cố.

Chỉ nhìn vào wrapper có thể khiến người vận hành sửa nhầm tầng service, trong khi lỗi thực tế nằm ở thao tác đọc file, xử lý SQL hoặc gọi HTTP.

### 4.2. Mất loại ngoại lệ để phân loại và phục hồi

`IOException`, `SQLException`, `TimeoutException` hoặc một exception do SDK cung cấp có thể yêu cầu cách xử lý khác nhau. Nếu chỉ còn message trong wrapper, logic ở tầng cao không thể kiểm tra `getCause()` để nhận đúng loại, ví dụ phân biệt lỗi tạm thời có thể thử lại với lỗi dữ liệu không hợp lệ không nên thử lại.

Tuy nhiên, **không nên chỉ dùng tên lớp exception để quyết định retry**. Cần kiểm tra nguyên nhân, trạng thái, tính idempotent và chính sách hệ thống. Cause là thông tin hỗ trợ phân loại, không phải quyết định nghiệp vụ tự động.

### 4.3. Mất các nguyên nhân bên dưới và lỗi phụ

Một `IOException` có thể có cause riêng, ví dụ lỗi hệ thống tệp. Nó cũng có thể mang `getSuppressed()` do `try-with-resources`. Khi giữ toàn bộ đối tượng `IOException` làm cause, các quan hệ đó vẫn có thể được truy theo; khi chỉ sao chép message, chúng bị bỏ khỏi chuỗi ngoại lệ của wrapper mới.

### 4.4. Làm log và hệ thống giám sát thiếu bằng chứng

Các logger như JUL, SLF4J/Logback thường có cơ chế nhận đối tượng `Throwable` và định dạng stack, cause, suppressed. Nhưng chúng chỉ có thể hiển thị dữ liệu mà exception hiện tại còn giữ. Nếu cause đã bị cắt từ một tầng trung gian, log ở controller hoặc ở bộ xử lý lỗi toàn cục không thể khôi phục nó.

### 4.5. Khó kiểm thử và duy trì hợp đồng lỗi

Test có thể kiểm tra cả loại wrapper **và cause gốc**. Nếu chỉ kiểm tra message, một refactor có thể vô tình làm mất chuỗi nguyên nhân mà test vẫn xanh. Hợp đồng “lỗi tầng dữ liệu được chuyển thành lỗi tầng nghiệp vụ nhưng vẫn giữ nguyên nhân” nên là một điều kiện có thể kiểm chứng.

## 5. Truyền lỗi nguyên vẹn hay bọc bằng lỗi mới?

Không phải lúc nào cũng nên tạo wrapper. Có hai chiến lược chính:

**Truyền tiếp:** khi phương thức có thể khai báo `throws IOException` và tầng gọi đã có trách nhiệm xử lý.

```java
void load() throws java.io.IOException {
    repository.read();
}
```

Đoạn minh họa cần `repository` được khai báo và có phương thức `read()` phù hợp. Ở đây không tạo exception mới. Nếu tầng này không có ngữ cảnh mới và không muốn đổi loại ngoại lệ, việc bắt rồi ném lại đôi khi chỉ làm mã dài hơn.

**Dịch ngoại lệ:** khi muốn mô tả thất bại bằng thuật ngữ của tầng trừu tượng hiện tại, hoặc vì hợp đồng phương thức không cho checked exception lan ra.

```java
void initialize() {
    try {
        repository.read();
    } catch (java.io.IOException cause) {
        throw new IllegalStateException(
                "Cannot initialize configuration", cause);
    }
}
```

Đây là đoạn minh họa cần `repository`. Wrapper cung cấp loại lỗi và thông điệp phù hợp với tầng khởi tạo, trong khi nguyên nhân `IOException` vẫn được giữ.

Hãy dùng wrapper khi **mang thêm ý nghĩa**, không phải cứ đi qua một tầng là tạo một `RuntimeException("failed", previous)`. Nhiều tầng bọc vô ích tăng chi phí tạo stack và khiến trace khó đọc.

Không nên dựa vào thông điệp lỗi kỹ thuật để xây thông điệp hiển thị cho người dùng cuối. Thông điệp HTTP/UI nên an toàn và ổn định, có thể khác thông điệp trong log hoặc trong exception.

## 6. Các constructor giữ nguyên nhân

Trong Java, các lớp exception thường cung cấp một số constructor, ví dụ `IllegalStateException`:

```java
new IllegalStateException("operation failed", cause);
new IllegalStateException(cause);
```

Đây là các biểu thức minh họa với biến `cause` kiểu `Throwable`. Constructor hai tham số thường rõ ràng nhất vì vừa có ngữ cảnh nghiệp vụ vừa giữ nguyên nhân.

Một lớp exception tùy biến nên cân nhắc constructor cho phép chuyển cause:

```java
public final class ConfigurationLoadException extends RuntimeException {
    public ConfigurationLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Đây là **khai báo lớp hoàn chỉnh ở mức đoạn mã**, nhưng khi đặt vào một tệp Java độc lập tên lớp public phải khớp tên tệp (`ConfigurationLoadException.java`). Có thể bỏ `public` trong ví dụ nhúng vào lớp khác. Để sử dụng:

```java
try {
    configRepository.read();
} catch (java.io.IOException cause) {
    throw new ConfigurationLoadException("Cannot load application config", cause);
}
```

Đoạn sử dụng yêu cầu đối tượng `configRepository` và lớp `ConfigurationLoadException` tương ứng.

Nếu dùng constructor chỉ có message, ví dụ `new ConfigurationLoadException(cause.getMessage())`, lớp phải có constructor đó thì mới biên dịch; quan trọng hơn, cách đó vẫn **không tự gắn cause**.

Một số thư viện có hệ thống exception riêng (mã lỗi, trạng thái HTTP, retryability). Hãy sử dụng constructor/builder có trường nguyên nhân đúng theo API, thay vì phỏng đoán rằng đặt một trường `message` là tương đương.

## 7. `initCause()` không phải giải pháp ưu tiên và không phải setter

`Throwable.initCause(Throwable)` có thể gắn nguyên nhân sau khi tạo một throwable mà cause **chưa được khởi tạo**. Điều này hữu ích cho những lớp cũ thiếu constructor nhận `Throwable`, nhưng có các giới hạn quan trọng:

- Chỉ được khởi tạo cause **một lần**. Gọi `initCause` lần nữa ném `IllegalStateException`.
- `initCause(this)` không hợp lệ: một throwable không được làm nguyên nhân trực tiếp của chính mình.
- Nếu constructor đã khởi tạo cause, kể cả về `null`, việc gọi `initCause(...)` sau đó có thể bị từ chối.
- Không nên gọi `initCause` trên exception đã chia sẻ giữa request hoặc nhiều luồng để cố thay nguyên nhân.

Ví dụ **đoạn mã độc lập ở mức phương thức**:

```java
Exception error = new Exception("load failed");
error.initCause(new java.io.IOException("file missing"));

System.out.println(error.getCause().getClass().getSimpleName());
```

Đầu ra:

```text
IOException
```

Ưu tiên constructor có `cause` ngay khi tạo nếu lớp hỗ trợ. Điều đó làm quan hệ lỗi rõ ràng và tránh một khoảng thời gian object tồn tại mà chưa có nguyên nhân.

## 8. Cause không đồng nghĩa suppressed exception

Có hai kiểu quan hệ ngoại lệ khác nhau:

- **Cause:** lỗi A dẫn đến việc tạo báo cáo lỗi B. Ví dụ `IOException` khi đọc dữ liệu là cause của `IllegalStateException("startup failed")`.
- **Suppressed:** một lỗi phụ xảy ra trong quá trình xử lý/đóng tài nguyên trong khi một lỗi chính đã xuất hiện. Ví dụ `close()` thất bại sau khi đọc file đã ném lỗi.

Đừng thay quan hệ nhân-quả bằng `addSuppressed(error)` chỉ để “lưu cho có”. `getCause()` và `getSuppressed()` mang nghĩa khác nhau; các hệ thống xử lý và người đọc log cũng diễn giải chúng khác nhau.

### Ví dụ Java 17+: cause giữ cả suppressed exceptions

Tạo tệp **`CauseAndSuppressedDemo.java`**:

```java
import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;

public class CauseAndSuppressedDemo {
    static final class BrokenResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static void readData() throws IOException {
        try (BrokenResource resource = new BrokenResource()) {
            throw new IOException("read failed");
        }
    }

    static void process() {
        try {
            readData();
        } catch (IOException original) {
            throw new IllegalStateException("import failed", original);
        }
    }

    public static void main(String[] args) {
        try {
            process();
        } catch (IllegalStateException wrapper) {
            Throwable cause = wrapper.getCause();

            System.out.println("wrapper=" + wrapper.getMessage());
            System.out.println("cause=" + cause.getMessage());
            System.out.println("suppressedCount="
                    + cause.getSuppressed().length);
            System.out.println("suppressedMessage="
                    + cause.getSuppressed()[0].getMessage());

            StringWriter buffer = new StringWriter();
            wrapper.printStackTrace(new PrintWriter(buffer));
            String trace = buffer.toString();

            System.out.println("causeInTrace="
                    + trace.contains("Caused by: java.io.IOException: read failed"));
            System.out.println("suppressedInTrace="
                    + trace.contains(
                            "Suppressed: java.io.IOException: close failed"));
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 CauseAndSuppressedDemo.java
java CauseAndSuppressedDemo
```

Đầu ra:

```text
wrapper=import failed
cause=read failed
suppressedCount=1
suppressedMessage=close failed
causeInTrace=true
suppressedInTrace=true
```

Vì `readData()` ném `IOException("read failed")` khi thân `try` đang chạy, còn `close()` ném `IOException("close failed")`, Java giữ lỗi đọc làm ngoại lệ chính và gắn lỗi đóng thành suppressed. `process()` tạo wrapper **nhưng giữ chính ngoại lệ đọc làm cause**, nên từ wrapper vẫn truy được cả hai thất bại.

Nếu thay dòng trong `process()` bằng `throw new IllegalStateException(original.getMessage());`, wrapper sẽ mất đường dẫn tới cả `IOException("read failed")` lẫn `getSuppressed()` của nó. Đây là lý do sai lầm “chỉ sao chép thông điệp” đặc biệt có hại khi lỗi gồm nhiều tầng.

## 9. Lần theo chuỗi cause mà không làm mất ngữ cảnh

Khi điều tra lỗi, bắt đầu từ exception ngoài cùng rồi đi theo `getCause()`:

```java
Throwable cursor = failure;
while (cursor != null) {
    System.out.println(cursor.getClass().getName()
            + ": " + cursor.getMessage());
    cursor = cursor.getCause();
}
```

Đây là đoạn minh họa bên trong một phương thức có `Throwable failure`. Đối với một chuỗi nguyên nhân hợp lệ thông thường, cách duyệt giúp xem từng tầng. Tuy nhiên, nếu viết tiện ích phục vụ dữ liệu lỗi từ nguồn bất kỳ, nên có biện pháp chống chuỗi bất thường (ví dụ theo dõi đối tượng đã gặp và giới hạn chiều sâu) thay vì giả định mọi liên kết cause luôn có độ sâu hợp lý.

**Không phải lúc nào cause sâu nhất cũng là thông tin duy nhất quan trọng.** Ngoại lệ tầng trên như `PaymentValidationException` có thể chứa quy tắc nghiệp vụ thất bại, trong khi cause sâu nhất chỉ là `SQLException`. Khi chọn phản hồi hoặc chính sách retry, giữ thông tin từng tầng; khi log, ưu tiên chuyển cả `Throwable` để backend hỗ trợ trình bày toàn bộ chuỗi.

Nếu mã dùng một helper “unwrap” bỏ `CompletionException` hoặc `ExecutionException`, nên phân biệt **bọc kỹ thuật** với **ngoại lệ có ngữ nghĩa nghiệp vụ**. Bỏ mọi wrapper vô điều kiện có thể làm mất thông tin về thao tác đã thất bại.

## 10. Ảnh hưởng trong `CompletableFuture` và `ExecutorService`

Trong tác vụ bất đồng bộ, lỗi có thể được bọc thêm bởi API quan sát kết quả:

- `Future.get()` và `CompletableFuture.get()` thường ném `ExecutionException` khi tác vụ thất bại; `getCause()` liên hệ ngoại lệ từ tác vụ.
- `CompletableFuture.join()` thường ném `CompletionException` khi future hoàn tất thất bại; cause chứa lỗi của pipeline.
- Trong `CompletableFuture.supplyAsync`, nếu supplier muốn chuyển `IOException` checked thành ngoại lệ unchecked để báo lỗi, có thể ném `new CompletionException("loading failed", original)`. Điều này **giữ nguyên nhân**.
- Nếu supplier lại ném `new RuntimeException(original.getMessage())`, nguyên nhân bị mất từ **ngay trong worker**. `join()`/`get()` có bọc thêm bao nhiêu lớp cũng không phục hồi lại `IOException` đã bị bỏ.

Mã minh họa trong lambda của một `CompletableFuture`:

```java
CompletableFuture<String> loaded = CompletableFuture.supplyAsync(() -> {
    try {
        return readText();
    } catch (java.io.IOException original) {
        throw new java.util.concurrent.CompletionException(
                "Cannot read text asynchronously", original);
    }
});
```

Đây là đoạn mã **không chạy độc lập**: yêu cầu import `CompletableFuture` và hàm `readText()` được khai báo với kiểu kết quả `String` và có thể ném `IOException`.

Khi bắt `CompletionException` ở ranh giới gọi `join()`:

```java
try {
    loaded.join();
} catch (java.util.concurrent.CompletionException error) {
    Throwable underlying = error.getCause();
    // Phân loại lỗi nếu cần, đồng thời giữ chuỗi throwable khi log.
    throw error;
}
```

Đoạn minh họa cần `loaded` được khai báo như trên. Tùy pipeline, `getCause()` có thể là một ngoại lệ nghiệp vụ hoặc một wrapper khác. Việc kiểm tra từng tầng là cách đáng tin hơn đoán chiều sâu cause.

Trường hợp hủy (`CancellationException`) hoặc ngắt luồng đang chờ (`InterruptedException`) có ngữ nghĩa riêng; không nên bọc mọi lỗi hủy/ngắt thành một `RuntimeException` chung chỉ để tránh checked exception. Nếu bắt `InterruptedException` nhưng không thể ném tiếp và chủ đích kết thúc việc đang làm, cần cân nhắc khôi phục trạng thái bằng `Thread.currentThread().interrupt()` rồi rời tác vụ theo hợp đồng.

## 11. Ghi log: truyền cả `Throwable`, không chỉ message

Ngay cả khi wrapper đã giữ cause đúng, bạn vẫn có thể làm mất thông tin ở **tầng logging** nếu chỉ ghi chuỗi.

Với SLF4J (đoạn mã minh họa, cần `logger`, `orderId`, `error`):

```java
logger.error("Order {} failed: {}", orderId, error.getMessage());
```

Cách trên không chuyển đối tượng exception đến logger. Thay bằng:

```java
logger.error("Order {} failed", orderId, error);
```

Trong cách dùng SLF4J phổ biến, đối số `Throwable` cuối được nhận diện như ngoại lệ của sự kiện, để backend có thể in stack trace, cause và suppressed. Nếu không cần biến nội dung, có thể dùng `logger.error("Order failed", error)`.

Với `java.util.logging` (JUL):

```java
logger.log(java.util.logging.Level.SEVERE, "Order failed", error);
```

Đây là lời gọi trên một `java.util.logging.Logger logger`; overload có `Throwable` giữ tham chiếu ngoại lệ trong `LogRecord`. Ngược lại, `logger.severe(error.getMessage())` chỉ ghi chuỗi và không đính kèm exception.

Đừng nhầm việc **giữ cause trong đối tượng** với việc **backend chắc chắn hiển thị toàn bộ cause**. Định dạng thực tế còn phụ thuộc formatter, mức log, cấu hình, sampling và điểm đến. Cần xác minh cấu hình môi trường vận hành.

Với một lỗi đi qua nhiều tầng, tránh vừa log nguyên stack ở repository, vừa log thêm ở service, rồi log lại ở controller nếu không có lý do. Thường nên log một lần tại ranh giới xử lý có đủ ngữ cảnh, còn tầng trung gian chỉ chuyển tiếp hoặc thêm cause đúng cách.

## 12. Khi bọc lỗi, chọn thông điệp thế nào?

Một thông điệp tốt của wrapper nên trả lời **thao tác nào không thực hiện được**, thay vì chỉ lặp lại thông điệp kỹ thuật:

```java
throw new IllegalStateException(
        "Cannot initialize tax rules for region " + safeRegionCode,
        original);
```

Đây là đoạn minh họa với biến `safeRegionCode` và `original`. Wrapper thêm ngữ cảnh “khởi tạo luật thuế cho vùng nào” trong khi cause giữ lỗi ở tầng lưu trữ/mạng. Tránh tự xây thông điệp bằng mật khẩu, token, dữ liệu định danh nhạy cảm hoặc toàn bộ yêu cầu người dùng.

Không nhất thiết nối `original.getMessage()` vào message wrapper. Nếu hệ thống logging trình bày cause chain, thông điệp của lỗi gốc đã có trong phần `Caused by:`. Việc lặp message có thể gây dài dòng, khó tìm kiếm và tăng nguy cơ rò rỉ dữ liệu.

**Thông điệp đối với người dùng cuối** nên được tạo riêng theo hợp đồng lỗi: chẳng hạn một mã lỗi không nhạy cảm và hướng dẫn thao tác. Không trả stack trace, cause kỹ thuật hoặc cấu trúc ngoại lệ nội bộ trực tiếp cho API công khai.

## 13. Những ngoại lệ và phản ví dụ đáng lưu ý

### 13.1. Constructor không hỗ trợ cause

Một số lớp exception cũ hoặc của thư viện có thể chỉ hỗ trợ message. Nếu cần giữ nguyên nhân, kiểm tra xem có constructor khác, builder hoặc `initCause` phù hợp hay không. Không tự ý dùng reflection để thay trường cause; nếu cần, tạo wrapper mới có constructor nhận `Throwable` theo đúng hợp đồng của ứng dụng.

### 13.2. Không dùng `initCause` trên exception đã hoàn tất hoặc chia sẻ

Một `Throwable` có thể đã có cause, hoặc được nhiều luồng cùng sử dụng. Việc thử gán nguyên nhân sau khi đã phát hành có thể thất bại hoặc trộn ngữ cảnh. Tạo wrapper mới của **sự cố hiện tại** thường dễ suy luận hơn.

### 13.3. Bắt mọi `Exception` rồi biến thành cùng một lỗi

```java
try {
    performOperation();
} catch (Exception error) {
    throw new IllegalStateException("operation failed", error);
}
```

Đoạn này giữ được cause nhưng **không tự đảm bảo thiết kế tốt**: bắt quá rộng có thể che phân loại lỗi, đổi hợp đồng ngoại lệ, hoặc nuốt tín hiệu ngắt cần được xử lý đặc biệt. Chỉ bắt ở ranh giới mà bạn thật sự có chính sách chuyển đổi; tránh bắt `Throwable` bao gồm cả `Error` một cách tùy tiện.

### 13.4. Biến checked exception thành unchecked không có nghĩa là nguyên nhân biến mất

Nếu một API không muốn công bố `IOException` trong chữ ký, tạo `UncheckedIOException` là một lựa chọn chuyên biệt trong nhiều tình huống I/O:

```java
catch (java.io.IOException original) {
    throw new java.io.UncheckedIOException("Cannot load resource", original);
}
```

Đây là đoạn minh họa đặt trong một `catch`; constructor nhận `IOException` giúp giữ loại nguyên nhân gốc. Chọn loại ngoại lệ nhất quán với tầng trừu tượng của thư viện.

### 13.5. Dùng `throw new Exception(error.toString())` không bảo toàn stack

`Throwable.toString()` thường chứa tên lớp và message, nhưng vẫn chỉ là chuỗi. Nó không thay cho tham chiếu tới object gốc và không cho phép `getCause()` của wrapper truy về lỗi ban đầu.

### 13.6. Nếu muốn thêm stack của tầng gọi, wrapper có ích nhưng không được thay cause

Khi tạo wrapper, Java có thể ghi stack của **vị trí chuyển đổi ngoại lệ**, rất hữu ích để biết request đi qua tầng service nào. Giữ `original` làm cause giúp người điều tra có **cả** vị trí chuyển đổi lẫn vị trí sinh lỗi. Đừng xóa cause để “stack gọn hơn”; có thể định dạng hoặc lọc log ở công cụ quan sát, không cắt quan hệ lỗi tại nguồn.

## 14. Checklist rà soát code và quy trình sửa lỗi

Khi đọc một nhánh `catch`, hãy kiểm tra tuần tự:

1. **Có thật cần bắt ở đây?** Nếu tầng này không xử lý, không thêm ngữ nghĩa và hợp đồng cho phép, cân nhắc truyền nguyên ngoại lệ.
2. **Có cần đổi loại lỗi?** Nếu có, chọn wrapper phản ánh đúng ranh giới nghiệp vụ/kỹ thuật.
3. **Constructor có nhận `Throwable cause`?** Tránh chỉ truyền `error.getMessage()` hoặc `error.toString()`.
4. **Có giữ đúng ngoại lệ đang bắt không?** Đừng vô tình chọn `error.getCause()` rồi bỏ tầng `error` mang ngữ cảnh hữu ích.
5. **Có suppressed exceptions hoặc cause sâu hơn không?** Wrapper đúng phải giữ đường truy cập tới chúng.
6. **Có phục hồi hoặc xử lý đặc biệt cần thiết không?** Ví dụ ngắt luồng, hủy tác vụ, lỗi cần retry hoặc lỗi không nên retry.
7. **Logger có nhận cả throwable không?** Nếu chỉ log chuỗi, dữ liệu vẫn bị mất ở ranh giới ghi log.
8. **Thông điệp bổ sung có an toàn?** Không nhúng bí mật hoặc dữ liệu người dùng không được phép ghi.
9. **Test có khẳng định cause không?** Kiểm tra loại lỗi ngoài cùng, loại cause và thông điệp/cấu trúc cần thiết.
10. **Có log lặp hoặc wrapper vô ích không?** Tránh tạo thêm chuỗi lỗi quá sâu mà không cung cấp thông tin mới.

Một mẫu sửa trong code review:

```diff
 try {
     repository.save(entity);
 } catch (IOException error) {
-    throw new IllegalStateException("Save failed: " + error.getMessage());
+    throw new IllegalStateException("Save failed", error);
 }
```

Đoạn diff là minh họa; nó không phải lệnh được thực thi. Sự khác biệt nhỏ ở constructor tạo ra khác biệt lớn trong khả năng chẩn đoán.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `throw new RuntimeException(error.getMessage());` giữ lại những gì?  
**Đáp án:** Một thông điệp mới. Nó không tự đặt `getCause()` thành `error`, không giữ stack trace của `error` và không nối các suppressed exceptions từ `error`.

**Câu 2.** `throw new IllegalStateException("Cannot load", error);` có bao nhiêu đối tượng ngoại lệ?  
**Đáp án:** Ít nhất có wrapper mới và đối tượng `error` hiện có. `wrapper.getCause()` tham chiếu đến `error`; chúng không phải một đối tượng.

**Câu 3.** Nếu phương thức được phép khai báo `throws IOException` và không cần thêm thông tin, có nhất thiết phải tạo wrapper không?  
**Đáp án:** Không. Có thể truyền tiếp lỗi theo hợp đồng hoặc để ngoại lệ tự lan lên.

**Câu 4.** `Throwable.initCause` có dùng như setter để thay cause mỗi lần ném không?  
**Đáp án:** Không. Cause chỉ được khởi tạo một lần theo hợp đồng API.

**Câu 5.** Vì sao chỉ log `exception.getMessage()` không đủ, ngay cả khi wrapper đã gắn cause?  
**Đáp án:** Logger chỉ nhận chuỗi, nên không có đối tượng throwable để trình bày stack trace, `Caused by:` và suppressed exceptions.

**Câu 6.** Một `IOException` có suppressed `close failed`. Khi tạo `new IllegalStateException("load failed", original)`, liệu còn truy được lỗi đóng tài nguyên không?  
**Đáp án:** Có, qua `wrapper.getCause().getSuppressed()`; ví dụ `CauseAndSuppressedDemo` chứng minh điều đó.

**Câu 7.** Có nên luôn lấy cause sâu nhất rồi bỏ mọi wrapper khi trả lỗi không?  
**Đáp án:** Không. Wrapper có thể chứa ngữ cảnh nghiệp vụ rất quan trọng; cần phân biệt lớp bọc kỹ thuật với tầng lỗi có ý nghĩa.

**Câu 8.** Khi đổi `IOException` sang `UncheckedIOException`, làm sao không mất cause?  
**Đáp án:** Dùng constructor có đối số nguyên nhân, ví dụ `new UncheckedIOException("Cannot read", original)`.

**Câu 9.** Bọc lỗi có cause vẫn có thể sai trong tình huống nào?  
**Đáp án:** Bắt quá rộng, chọn loại wrapper không phù hợp, che `InterruptedException`, log trùng lặp hoặc đưa dữ liệu nhạy cảm vào message đều là lỗi thiết kế cần kiểm soát.

## 16. Tài liệu tham khảo

- [Java 17 — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, `initCause()`, stack trace và suppressed exceptions.
- [Java 17 — `IllegalStateException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalStateException.html): các constructor hỗ trợ thông điệp và cause.
- [Java 17 — `UncheckedIOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/UncheckedIOException.html): cách chuyển `IOException` thành ngoại lệ unchecked mà vẫn giữ nguyên nhân.
- [Java 17 — `CompletionException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html) và [Java 17 — `ExecutionException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html): lớp bọc khi quan sát lỗi bất đồng bộ.

**Ghi nhớ:** tạo ngoại lệ mới chỉ với `error.getMessage()` hoặc `error.toString()` **không bảo toàn nguyên nhân**. Nếu cần bọc lỗi, hãy giữ chính đối tượng `Throwable` đã bắt trong constructor nhận `cause`; nếu không cần bọc, truyền tiếp ngoại lệ đúng hợp đồng. Stack trace của wrapper và chuỗi cause bổ sung cho nhau để người đọc tìm được cả nơi lỗi được chuyển đổi lẫn nơi lỗi thật phát sinh.