# Java 7 — Ghi nhật ký rồi ném lại ngoại lệ mà không làm mất nguyên nhân

## 1. Mục tiêu: vừa quan sát được lỗi, vừa giữ đủ thông tin để tầng trên xử lý

Trong Java, một phương thức có thể bắt ngoại lệ (*exception*), bổ sung thông tin chẩn đoán vào nhật ký (*logging*), rồi **ném lại** để tầng gọi quyết định cách xử lý. Với chủ đề “Ném lại ngoại lệ”, yêu cầu quan trọng nhất là: sau khi log, **không biến lỗi gốc thành một thông báo văn bản trơ trọi**, không vô tình xóa stack trace, kiểu ngoại lệ hoặc chuỗi nguyên nhân (*cause chain*).

Có hai trường hợp thông dụng, đều còn phù hợp trên JDK hiện đại:

1. **Giữ nguyên ngoại lệ:** `catch (...) { log(..., ex); throw ex; }`. Lệnh `throw ex;` ném lại **chính đối tượng `Throwable` vừa bắt**, giữ loại ngoại lệ, nguyên nhân đã gắn trước đó, stack trace gốc và danh sách ngoại lệ bị suppressed.
2. **Đổi sang ngoại lệ ở tầng trừu tượng cao hơn:** `throw new ConfigException("...", ex);`. Đây là **đối tượng ngoại lệ mới** có thông điệp ngữ cảnh mới, còn `ex` được lưu làm `cause`. Khi hiển thị stack trace chuẩn, Java có thể thể hiện cả phần `Caused by`.

Trường hợp sai phổ biến là chỉ sao chép message:

```java
catch (java.io.IOException ex) {
    // SAI: mất tham chiếu đến IOException gốc trong chuỗi cause.
    throw new IllegalStateException("Load failed: " + ex.getMessage());
}
```

Đoạn minh họa này vẫn **biên dịch**, nhưng `IllegalStateException.getCause()` là `null`. Thông điệp `getMessage()` không thay thế được kiểu exception, stack trace hay cause chain. Cách đúng nếu thực sự cần đổi loại ngoại lệ:

```java
catch (java.io.IOException ex) {
    throw new IllegalStateException("Load failed", ex);
}
```

Ở đây `getCause()` của `IllegalStateException` trỏ đến chính `IOException` đã bắt. **Không cần wrap nếu giữ nguyên exception đã phù hợp với hợp đồng của phương thức**: lúc đó `throw ex;` đơn giản và giữ bản gốc trực tiếp nhất.

## 2. Ba khái niệm cần tách biệt: message, stack trace và cause

| Thành phần | Java API | Nó cho biết điều gì? |
| --- | --- | --- |
| **Message** | `ex.getMessage()` | Mô tả do người tạo exception cung cấp; có thể trống hoặc `null`. |
| **Kiểu ngoại lệ** | `ex.getClass()` | Phân loại lỗi thực tế, ví dụ `FileNotFoundException` khác `SQLException`. |
| **Stack trace** | `ex.getStackTrace()`, `ex.printStackTrace()` | Vị trí và chuỗi lời gọi được ghi nhận cho đối tượng exception; giúp xác định nguồn phát sinh. |
| **Cause** | `ex.getCause()` | Một `Throwable` khác được đánh dấu là nguyên nhân của exception hiện tại, nếu có. |
| **Suppressed exceptions** | `ex.getSuppressed()` | Các ngoại lệ phụ được lưu kèm, thường phát sinh khi đóng resource bằng try-with-resources. |

Một đối tượng exception **không bắt buộc có cause**: một `new IOException("disk failed")` tạo trực tiếp thường có `getCause() == null`, nhưng bản thân nó vẫn chứa kiểu/message/stack trace hữu ích. Vì vậy “không làm mất nguyên nhân” nghĩa là **bảo toàn đối tượng lỗi gốc khi ném lại**, hoặc **liên kết nó vào ngoại lệ bao ngoài**; không phải mọi lỗi đều vốn có sẵn một tầng `cause`.

Khi wrap:

```text
ConfigException: Cannot initialize application
  └── cause: FileNotFoundException: settings.json
                 └── original stack trace from file-loading operation
```

Ngoại lệ mới có stack trace riêng tại vị trí wrap; ngoại lệ gốc vẫn giữ stack trace của nó và có thể được duyệt bằng `getCause()`. Nếu rethrow chính ngoại lệ gốc, cùng một đối tượng đi lên stack và **không tự tạo thêm một `cause`**.

## 3. Cách 1 — Ghi log kèm `Throwable` rồi `throw ex;`

Với API chuẩn `java.util.logging`, dùng overload nhận **`Throwable`**:

```java
private static final java.util.logging.Logger LOG =
        java.util.logging.Logger.getLogger(ConfigService.class.getName());

static void loadConfiguration() throws java.io.IOException {
    try {
        readConfiguration();
    } catch (java.io.IOException ex) {
        LOG.log(java.util.logging.Level.WARNING,
                "Cannot load application configuration", ex);
        throw ex;
    }
}
```

Đây là **đoạn minh họa** trong một lớp `ConfigService` có phương thức `readConfiguration()` có thể ném `IOException`; không phải chương trình độc lập. Chọn mức log theo chính sách hệ thống, không mặc định mọi I/O exception đều cần `SEVERE`.

Điểm quan trọng là lời gọi `LOG.log(Level.WARNING, message, ex)`: tham số thứ ba ở đây có kiểu `Throwable`. Theo hợp đồng `Logger`, exception được lưu ở trường **`LogRecord.thrown`**, để handler/formatter xử lý đặc biệt (thường in stack trace), thay vì chỉ chuyển thành một tham số định dạng.

Ngược lại:

```java
LOG.warning("Load failed: " + ex.getMessage());
```

chỉ chuyển nội dung message sang log record; **logger không nhận được chính đối tượng `Throwable`** ở lời gọi này. Dòng log có thể thiếu stack trace, kiểu lỗi gốc và cause chain. Khi framework logging khác được dùng trong dự án, hãy chọn overload có tham số throwable tương đương theo hợp đồng của framework.

**Tại sao `throw ex;` bảo toàn thông tin?**

- `ex` vẫn trỏ tới cùng exception đã được ném trong `try`.
- `throw ex;` không gọi constructor mới, không làm mất cause/suppressed đã có.
- Stack trace của exception gốc vẫn gắn với đối tượng đó. Đừng gọi `fillInStackTrace()` để “làm mới” theo phản xạ: việc này thay đổi thông tin vị trí gốc và thường làm chẩn đoán khó hơn.
- Chữ ký `throws IOException` cho tầng gọi biết lỗi checked nào cần được bắt hoặc tiếp tục khai báo.

**Giới hạn cần hiểu:** log thành công không đồng nghĩa lỗi đã được xử lý hoặc hệ thống đã phục hồi; `throw ex;` tiếp tục chuyển luồng điều khiển qua exception. Và việc ném lại không bảo đảm tất cả log handler đều ghi ra đĩa thành công: chuyện lưu log là trách nhiệm khác của logging infrastructure.

## 4. Cách 2 — Đổi loại lỗi có chủ đích, truyền exception gốc làm `cause`

Ở ranh giới giữa tầng hạ tầng và tầng nghiệp vụ, có thể không muốn công khai `IOException` hoặc `SQLException` trong API ứng dụng. Hãy tạo loại lỗi có ý nghĩa nghiệp vụ và **truyền cause vào constructor**.

```java
final class ConfigurationException extends Exception {
    ConfigurationException(String message, Throwable cause) {
        super(message, cause);
    }
}

static void initializeConfiguration() throws ConfigurationException {
    try {
        loadConfiguration();
    } catch (java.io.IOException ex) {
        throw new ConfigurationException("Cannot initialize configuration", ex);
    }
}
```

Các khai báo trên là **minh họa cần đặt trong lớp/tệp phù hợp**; `loadConfiguration()` là phương thức do ứng dụng cung cấp. Ở tầng gọi:

```java
try {
    initializeConfiguration();
} catch (ConfigurationException ex) {
    Throwable original = ex.getCause();
    // Ở đây original tham chiếu IOException đã được giữ lại.
}
```

Lợi ích: tầng nghiệp vụ nhận `ConfigurationException` đúng abstraction, còn logs/debug vẫn truy theo `getCause()` tới lỗi hạ tầng gốc.

**Không phải trường hợp nào cũng nên wrap.** Nếu hợp đồng của phương thức đã khai báo `throws IOException` và tầng trên biết cách xử lý, giữ nguyên `throw ex;` tránh tạo thêm lớp lỗi không cần thiết. Khi wrap, cần chắc chắn lỗi mới có ý nghĩa tại ranh giới hiện tại và message bổ sung ngữ cảnh hữu ích; hạn chế những lớp `RuntimeException` chung chung lồng vào nhau liên tiếp.

### 4.1. Ba kiểu viết dễ nhầm

| Câu lệnh sau khi bắt `ex` | Giữ được lỗi gốc? | Ý nghĩa |
| --- | --- | --- |
| `throw ex;` | **Có, cùng đối tượng.** | Ném lại nguyên lỗi, giữ type/stack/cause/suppressed đã có. |
| `throw new ConfigurationException("Cannot load config", ex);` | **Có, qua `cause`.** | Đổi abstraction với ngữ cảnh mới; giữ lỗi gốc trong chuỗi cause. |
| `throw new ConfigurationException(ex.getMessage(), ex);` | **Có, qua `cause`.** | Vẫn giữ lỗi gốc, nhưng message thường thiếu ngữ cảnh mới. |
| `throw new ConfigurationException("Cannot load config", null);` | **Không.** | Cố tình không liên kết lỗi gốc, dù có thể vẫn biết thông điệp. |
| `throw new IllegalStateException("Cannot load: " + ex.getMessage());` | **Không.** | Có thể in ra text giống lỗi, nhưng `getCause() == null`. |
| `return false;` / `return null;` khi chưa có quy ước | **Không chuyển lỗi lên.** | Nuốt ngoại lệ; tầng gọi có thể tưởng thao tác thành công hoặc không hiểu vì sao thất bại. |

Khi API không có constructor `(String, Throwable)`, hãy kiểm tra các overload `(Throwable)` hoặc thiết kế exception có constructor truyền cause. `Throwable.initCause(...)` tồn tại nhưng với lớp do chính dự án định nghĩa, **ưu tiên truyền cause ngay khi khởi tạo** để code rõ ràng và nhất quán. Không gắn nhiều lần `initCause` lên cùng object.

## 5. Ví dụ chạy được trên Java 17+: log rồi rethrow, sau đó wrap với cause

Ví dụ dưới đây dùng toàn API có sẵn trong JDK, không cần thư viện logging bên ngoài. Handler riêng chỉ tồn tại để **stdout ổn định khi học**; trong ứng dụng thực tế, hệ thống logging sẽ tự định dạng, lọc, lưu và có thể in đầy đủ stack trace của `Throwable`.

Tạo tệp **`RethrowLoggingDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class RethrowLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(RethrowLoggingDemo.class.getName());

    static {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Handler teachingHandler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }
                Throwable error = record.getThrown();
                System.out.println("LOG: " + record.getMessage()
                        + " | type=" + (error == null
                        ? "none" : error.getClass().getSimpleName()));
            }

            @Override public void flush() { }
            @Override public void close() { }
        };
        teachingHandler.setLevel(Level.ALL);
        LOG.addHandler(teachingHandler);
    }

    static class ConfigException extends Exception {
        ConfigException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void readConfig() throws IOException {
        throw new FileNotFoundException("settings.json");
    }

    static void loadConfig() throws IOException {
        try {
            readConfig();
        } catch (IOException ex) {
            LOG.log(Level.WARNING, "Cannot read config", ex);
            throw ex;
        }
    }

    static void initialize() throws ConfigException {
        try {
            loadConfig();
        } catch (IOException ex) {
            throw new ConfigException("Initialization failed", ex);
        }
    }

    public static void main(String[] args) {
        try {
            initialize();
        } catch (ConfigException ex) {
            System.out.println("ERROR: " + ex.getMessage());
            Throwable cause = ex.getCause();
            System.out.println("CAUSE: "
                    + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }
    }
}
```

Biên dịch/chạy với JDK 17 hoặc cao hơn:

```bash
javac --release 17 RethrowLoggingDemo.java
java RethrowLoggingDemo
```

**Stdout chính xác:**

```text
LOG: Cannot read config | type=FileNotFoundException
ERROR: Initialization failed
CAUSE: FileNotFoundException: settings.json
```

Phân tích:

1. `readConfig()` ném `FileNotFoundException`, là subclass của `IOException`. Không có thao tác file thực tế nên output luôn tái hiện được.
2. `loadConfig()` bắt bằng kiểu cha `IOException`. `LOG.log(..., ex)` chuyển **chính đối tượng lỗi** cho logger. Handler demo đọc `record.getThrown()`, chứng minh tham chiếu exception gốc vẫn có mặt.
3. `throw ex;` chuyển tiếp **cùng đối tượng** `FileNotFoundException` lên `initialize()`. Kiểu thực tế không bị đổi thành `IOException` chỉ vì catch khai báo kiểu cha.
4. `initialize()` tạo một `ConfigException` mới, truyền `ex` làm cause. `ConfigException.getCause()` vẫn là `FileNotFoundException` ban đầu.
5. `main()` in hai tầng thông tin. Dòng `CAUSE` chứng minh lỗi gốc vẫn được liên kết, dù tầng gọi chỉ bắt `ConfigException`.

**Tại sao handler không in cả stack trace?** Đây là lựa chọn cho bài học có stdout ngắn và ổn định. Trong triển khai thật, nên dùng handler/formatter chuẩn hoặc hệ thống log tập trung phù hợp, ghi đầy đủ exception khi cần. Đừng sao chép cấu hình teaching handler vào dịch vụ thật chỉ để ẩn stack trace.

## 6. Liên hệ Java 7: precise rethrow và kiểu checked exception

Java 7 cải tiến khả năng phân tích exception **chính xác hơn khi ném lại biến catch** (thường gọi *precise rethrow*). Điều này vẫn được áp dụng với compiler của Java 17+.

Xem ví dụ minh họa:

```java
import java.io.IOException;
import java.sql.SQLException;

class PreciseRethrowDemo {
    static void process(boolean file) throws IOException, SQLException {
        if (file) {
            throw new IOException("disk");
        }
        throw new SQLException("database");
    }

    static void forward(boolean file) throws IOException, SQLException {
        try {
            process(file);
        } catch (Exception ex) {
            throw ex;
        }
    }
}
```

Đây là lớp hoàn chỉnh **không có phương thức `main`**, chỉ dùng để minh họa biên dịch. Mặc dù kiểu khai báo của `ex` là `Exception`, `javac` có thể suy ra trong khối `try` chỉ có `IOException` và `SQLException` checked được ném, rồi chấp nhận chữ ký `throws IOException, SQLException`. Điều kiện then chốt là biến catch **`final` hoặc effectively final**: ở đây nó không bị gán lại.

Nếu trong `catch` có thao tác gán `ex = new Exception("replacement");` trước khi `throw ex;`, compiler không còn áp dụng precise rethrow cho biến đó theo cách này; chữ ký `throws IOException, SQLException` sẽ không còn đủ trong ví dụ.

**Đừng hiểu nhầm precise rethrow là thao tác “phục hồi” stack trace.** Đây là **phân tích kiểu ngoại lệ ở compile-time**, không phải một phương thức chỉnh sửa `Throwable` khi runtime. Kỹ thuật giữ nguyên cause vẫn dựa trên `throw ex;` hoặc tạo wrapper với `cause`.

### 6.1. Multi-catch và `final` ngầm định

```java
try {
    process(true);
} catch (IOException | SQLException ex) {
    LOG.log(Level.WARNING, "Operation failed", ex);
    throw ex;
}
```

Đây là **đoạn mã minh họa trong phương thức** có chữ ký `throws IOException, SQLException`, có `LOG` và `process` thích hợp. Trong multi-catch, biến `ex` **final ngầm định**, nên không thể gán lại. Cả `IOException` và `SQLException` không có quan hệ subclass với nhau, vì thế tổ hợp hợp lệ. Nếu từng loại lỗi cần chính sách khác, hãy dùng các `catch` riêng.

Ví dụ **cố ý sai, không biên dịch**:

```java
catch (IOException | SQLException ex) {
    ex = new IOException("other"); // Lỗi: ex là final ngầm định.
    throw ex;
}
```

Với lỗi checked, không nên đổi sang bắt `Exception` thật rộng chỉ để khỏi khai báo `throws`. Loại exception, ranh giới layer và hợp đồng gọi hàm vẫn cần được chọn theo nghĩa nghiệp vụ.

## 7. Log một lần ở tầng có ngữ cảnh phù hợp: tránh duplicate logs

Mặc dù cú pháp “log rồi rethrow” đúng, nếu **mỗi tầng đều bắt, ghi toàn bộ stack trace và tiếp tục ném**, một sự cố có thể tạo ra nhiều bản log gần như giống hệt nhau. Ví dụ chuỗi:

```text
Repository: log ERROR + throw SQLException
       ↓
Service: log ERROR + throw DomainException(cause=SQLException)
       ↓
Controller: log ERROR + return HTTP 500
```

Hậu quả: cùng một lỗi bị đếm ba lần, tăng dung lượng log và làm khó theo dõi sự cố.

Quy tắc thực hành:

- **Log rồi rethrow chỉ khi tầng đó có ngữ cảnh chẩn đoán cần thiết**, chẳng hạn tên thao tác đã được chuẩn hóa, mã tác vụ không nhạy cảm hoặc quyết định retry. Nếu không thêm thông tin gì, để ngoại lệ đi lên rồi log ở một ranh giới chịu trách nhiệm thường rõ hơn.
- **Log tập trung tại ranh giới xử lý** (ví dụ bộ xử lý request/worker/job) khi đó là nơi sự cố được giải quyết và tạo phản hồi. Nếu đã log đầy đủ ở nơi thấp hơn, tầng trên nên cân nhắc không log lặp cùng stack trace.
- **Nếu chỉ chuyển kiểu lỗi**, thường có thể wrap với cause và **không log tại chỗ**: `throw new DomainException("...", ex);`. Tầng bao ngoài sẽ log cả chuỗi.
- **Nếu sẽ retry**, mức độ log tùy trường hợp: không mặc định log mỗi lần thử thất bại với mức ERROR rồi thêm một ERROR khi thất bại cuối; kiểm tra chính sách observability của hệ thống.
- **Nếu xử lý và phục hồi được** tại tầng hiện tại (ví dụ fallback hợp lệ), có thể log ở mức phù hợp rồi không rethrow. Khi đó code phải rõ rằng lỗi đã được xử lý theo hợp đồng, không giả vờ thành công.

Ví dụ kiểm soát log ở biên:

```java
static void handleRequest() {
    try {
        serviceCall();
    } catch (ConfigurationException ex) {
        LOG.log(Level.SEVERE, "Request failed during initialization", ex);
        // Chuyển thành kết quả/lỗi HTTP thích hợp tại biên này.
    }
}
```

Đây là **đoạn mã minh họa**, không phải chương trình chạy riêng; `serviceCall()` và `ConfigurationException` phải do ứng dụng định nghĩa. Ý chính: log kèm `Throwable` ở nơi chịu trách nhiệm chuyển lỗi thành phản hồi, trong khi các tầng dưới có thể chỉ wrap/rethrow mà không log lặp.

## 8. Ghi gì trong log để truy được nguyên nhân?

Một log hữu ích thường có:

1. **Hành động đang thất bại:** “Read config”, “Fetch invoice”, “Commit transaction”, “Publish event”.
2. **Ngữ cảnh liên kết an toàn:** request ID, correlation ID, mã tác vụ nội bộ hoặc tên thành phần cho phép tiết lộ.
3. **Thông tin exception gốc:** logger nhận `Throwable`, để hệ thống log lưu kiểu, message, stack trace, cause và suppressed.
4. **Mức log theo tác động:** ví dụ WARNING cho tình huống có thể được xử lý/lặp lại; SEVERE/ERROR cho lỗi cần can thiệp. Không chọn mức chỉ theo loại exception.
5. **Phân biệt expected failure và bug:** ngoại lệ như input sai, tài nguyên không tìm thấy, timeout được kỳ vọng trong một số luồng có thể cần cách log khác với lỗi code nghiêm trọng.

**Không đưa bí mật vào log:** tránh mật khẩu, token, key API, dữ liệu cá nhân không cần thiết, nội dung file nhạy cảm hoặc SQL có chứa tham số bí mật. Dù exception message đôi khi chứa đường dẫn/URL/chi tiết truy vấn, chỉ thêm context đã được kiểm soát; áp dụng bộ lọc/redaction theo hệ thống. Không ghi toàn bộ request body một cách vô điều kiện.

Với hệ thống phân tán, correlation ID thường hữu dụng hơn việc copy cùng stack trace qua mọi tầng. Khả năng tìm được “sự cố nào thuộc request nào” và “cause gốc là gì” có giá trị hơn số lượng dòng log.

## 9. Những điều làm mất hoặc làm méo nguyên nhân

### 9.1. Chỉ log message thay vì throwable

```java
catch (IOException ex) {
    LOG.warning("Read failed: " + ex.getMessage()); // Thiếu Throwable.
    throw ex;                                       // Rethrow vẫn giữ gốc.
}
```

Lưu ý phân biệt: **lệnh `throw ex;` ở đây vẫn bảo toàn exception**. Phần không đầy đủ là **log record**, vì logger không được cung cấp tham chiếu `Throwable`. Không nên kết luận cứ log sai là rethrow sai; chúng là hai trách nhiệm khác nhau.

### 9.2. Wrap nhưng bỏ cause

```java
catch (IOException ex) {
    // SAI: người bắt IllegalStateException không thể duyệt về IOException.
    throw new IllegalStateException("Cannot read configuration");
}
```

Cách đúng:

```java
catch (IOException ex) {
    throw new IllegalStateException("Cannot read configuration", ex);
}
```

### 9.3. Ném exception mới chỉ có message gốc

```java
catch (IOException ex) {
    // SAI: giữ text nhưng đánh mất exception gốc trong chuỗi cause.
    throw new IOException(ex.getMessage());
}
```

Nếu cần giữ nguyên kiểu và thông tin ban đầu, `throw ex;`. Nếu cần ngữ cảnh mới ở một IOException mới, dùng `new IOException("Reading config failed", ex)`.

### 9.4. Ghi và nuốt lỗi

```java
catch (IOException ex) {
    LOG.log(Level.WARNING, "Read failed", ex);
    return null; // Chỉ đúng nếu API quy định null là kết quả hợp lệ cho failure.
}
```

Đây là **đoạn minh họa lỗi thiết kế thường gặp**: nếu caller không có quy ước rõ, nó có thể coi `null` là giá trị bình thường hoặc xảy ra `NullPointerException` ở chỗ khác, xa nguyên nhân gốc. Với luồng thật có fallback, hãy diễn tả failure bằng kiểu kết quả hoặc lỗi nghiệp vụ phù hợp.

### 9.5. Chỉnh sửa stack trace một cách không cần thiết

`Throwable.fillInStackTrace()` cập nhật stack trace của đối tượng, có thể làm mất vị trí nơi lỗi bắt đầu. Không gọi nó chỉ vì muốn “ném lại đẹp hơn”. Cũng không nên dựng một exception mới với cùng message để làm mới stack trace, vì sẽ mất nguồn gốc nếu không gắn cause. Đối tượng Throwable còn có thông tin suppressed; sao chép message đơn thuần không giữ được danh sách đó.

### 9.6. Che lỗi ban đầu bằng lỗi trong logger hoặc cleanup

Nếu trong khối `catch` còn chạy code phức tạp có thể ném exception khác trước `throw ex;`, lỗi mới có thể thay thế luồng lỗi đang xử lý. Ưu tiên logging API thông thường, kiểm soát side effect và dọn tài nguyên bằng try-with-resources. Không thực hiện thêm thao tác business không cần thiết trong `catch` chỉ để ghi log.

## 10. Ngoại lệ `suppressed` và try-with-resources

Từ Java 7, try-with-resources giúp đóng tài nguyên theo vòng đời rõ ràng. Nếu **thân `try`** và **`close()`** cùng ném exception, lỗi từ `close()` thường được gắn vào lỗi chính dưới dạng **suppressed exception**, truy được bằng `getSuppressed()`.

```java
try (java.io.BufferedReader reader =
             java.nio.file.Files.newBufferedReader(path)) {
    process(reader);
} catch (java.io.IOException ex) {
    LOG.log(java.util.logging.Level.WARNING, "File processing failed", ex);
    throw ex;
}
```

Đây là **đoạn minh họa trong phương thức** có `path`, `process(...)`, `LOG` và `throws IOException` phù hợp. `throw ex;` không loại bỏ suppressed exceptions, vì đang giữ nguyên đối tượng. Nếu wrap theo `new FileProcessingException("...", ex)`, suppressed của lỗi gốc vẫn còn trên cause, có thể truy qua `getCause().getSuppressed()`.

**Không tự tạo exception mới chỉ chứa `getMessage()`**, vì lúc đó vừa mất thông tin gốc vừa mất suppressed đi kèm. Cũng không dùng `getSuppressed()` thay cho `getCause()`: cause và suppressed phục vụ hai quan hệ khác nhau.

## 11. Kiểm thử hành vi giữ nguyên ngoại lệ và cause

Đừng chỉ kiểm thử thông điệp text; hãy kiểm tra **kiểu, object identity, cause chain** và đường xử lý phù hợp.

### 11.1. Kiểm tra cùng đối tượng khi rethrow

```java
java.io.IOException original = new java.io.IOException("disk unavailable");
try {
    try {
        throw original;
    } catch (java.io.IOException ex) {
        throw ex;
    }
} catch (java.io.IOException caught) {
    System.out.println(caught == original); // true
}
```

Đoạn này đặt trong một phương thức, không phải chương trình chạy độc lập. Output `true` cho thấy `throw ex;` không tạo exception mới.

### 11.2. Kiểm tra cause khi wrap

```java
java.io.IOException original = new java.io.IOException("disk unavailable");
IllegalStateException wrapped =
        new IllegalStateException("Cannot start", original);

System.out.println(wrapped.getCause() == original); // true
System.out.println(wrapped.getCause().getMessage()); // disk unavailable
```

Đoạn này cũng là mã đặt trong phương thức. Test tích hợp có thể kiểm tra log event nhận đúng `Throwable` bằng in-memory handler/appender tương ứng, đồng thời xác minh tầng trên nhận exception đúng loại. Đừng viết test chỉ khớp toàn bộ stack trace dưới dạng chuỗi dài: số dòng và tên frame có thể đổi theo compiler/JDK.

### 11.3. Với logging framework

Trong unit test, thay vì dựa vào console hoặc file log, có thể gắn một handler/appender test để kiểm tra:

- message có ngữ cảnh và mức log dự kiến;
- trường throwable được truyền vào log event là chính lỗi đã bắt;
- phương thức tiếp tục ném đúng exception hoặc wrapper có đúng cause;
- số event không bị nhân lên bất ngờ qua nhiều tầng.

Đối với phương thức có `throws IOException`, test cũng phải quan tâm việc caller sẽ xử lý hay tiếp tục ném ngoại lệ checked đúng hợp đồng.

## 12. Quy trình thực hành ở dự án

Khi cần “ghi nhật ký rồi ném lại mà không mất nguyên nhân”, áp dụng lần lượt:

1. **Xác định tầng chịu trách nhiệm lỗi:** tầng hiện tại chỉ biết I/O chi tiết, hay tầng hiện tại có thể đổi sang lỗi nghiệp vụ hữu ích?
2. **Xác định có cần log tại tầng này không:** nếu không bổ sung ngữ cảnh, để lỗi đi lên, log ở ranh giới chịu trách nhiệm nhằm tránh duplicate.
3. **Nếu log, truyền `Throwable`:** `LOG.log(Level.WARNING, "context", ex)` thay vì chỉ ghép `ex.getMessage()`.
4. **Nếu giữ loại lỗi:** `throw ex;` và khai báo/điều chỉnh `throws` phù hợp.
5. **Nếu đổi loại lỗi:** tạo wrapper có message mới và cause: `new DomainException("context", ex)`.
6. **Không làm thay đổi đối tượng Throwable gốc:** tránh `fillInStackTrace()`, không tự tạo lỗi mới bỏ cause, không nuốt lỗi bằng return thiếu hợp đồng.
7. **Kiểm thử đường đi exception:** xác nhận kiểu, nguyên nhân, suppressed nếu liên quan, và khả năng caller phản hồi đúng.
8. **Đảm bảo log hữu dụng, không lộ dữ liệu nhạy cảm:** thêm correlation ID phù hợp, không lặp log nhiều tầng, loại bỏ bí mật khỏi context.
9. **Phân biệt cú pháp Java 7 với lựa chọn triển khai hiện đại:** rethrow/precise rethrow và try-with-resources vẫn hữu dụng, nhưng chương trình nên biên dịch/chạy trên JDK đang được hỗ trợ trong môi trường của dự án.

### Những hiểu lầm thường gặp

**“Ghi `ex.getMessage()` vào log là đã log đủ lỗi.”** Không: logging API sẽ không tự có nguyên đối tượng `Throwable`, type và cause nếu bạn chỉ truyền message.

**“`throw ex;` làm mất stack trace nên luôn phải wrap.”** Không: `throw ex;` giữ cùng đối tượng và stack trace đã có. Wrap chỉ khi cần đổi abstraction hoặc bổ sung ngữ cảnh ở một exception mới.

**“Nếu có `Caused by` thì mọi vấn đề đã được xử lý.”** Không: cause chain hỗ trợ chẩn đoán; logic phục hồi, rollback, phản hồi, retry vẫn là quyết định khác.

**“Chỉ cần đưa `ex.getMessage()` vào constructor của wrapper là giữ được cause.”** Không: cần truyền `ex` vào constructor nhận `Throwable`, hoặc một cách thiết lập cause hợp lệ tương ứng.

**“Log rồi rethrow tại mọi tầng luôn tốt.”** Không: nhiều event cho cùng một sự cố có thể làm nhiễu cảnh báo và tốn chi phí. Ghi log tại nơi có ngữ cảnh hoặc ở ranh giới xử lý cuối, theo chính sách chung.

**“`catch (Exception ex) { throw ex; }` luôn buộc `throws Exception` rộng.”** Không luôn: với điều kiện *effectively final* và exception analysis phù hợp, Java 7+ có precise rethrow cho các checked exception thực sự có thể phát sinh.

**“Ngoại lệ bị suppressed là cause.”** Không: suppressed và cause có mục đích khác nhau; giữ object hoặc wrap bằng cause sẽ tránh mất cả hai dạng thông tin.

## 13. Câu hỏi tự kiểm tra

**1.** Khi bắt `IOException ex`, lệnh nào giữ chính đối tượng lỗi gốc? — `throw ex;`. Kèm log đúng thì `LOG.log(Level.WARNING, "context", ex); throw ex;`.

**2.** `throw new IllegalStateException(ex.getMessage())` có giúp tầng trên truy `IOException` cũ bằng `getCause()` không? — **Không**; cần `new IllegalStateException("context", ex)`.

**3.** Việc log bằng `LOG.warning(ex.getMessage())` có làm `throw ex;` mất stack trace không? — **Không**. Rethrow vẫn giữ exception, nhưng bản ghi log được tạo bằng cách đó thiếu tham chiếu `Throwable`.

**4.** Tại sao không log ERROR đầy đủ ở cả repository, service và controller cho một lần lỗi? — Vì dễ nhân bản cùng sự cố và gây nhiễu; nên chọn nơi có ngữ cảnh hoặc ranh giới xử lý.

**5.** Có thể có `ConfigException.getCause() == originalIOException` dù tầng gọi chỉ nhìn thấy `ConfigException` không? — **Có**, nếu constructor của wrapper được gọi với `originalIOException` làm cause.

**6.** Vì sao `catch (Exception ex) { throw ex; }` có thể khai báo chỉ `throws IOException, SQLException` trong một ví dụ Java 7+? — Vì compiler suy luận chính xác các checked exceptions mà `try` có thể ném khi biến catch là final/effectively final.

**7.** Nếu `close()` của tài nguyên ném lỗi khi thân `try` đã ném lỗi, có phải chỉ lưu message thì vẫn giữ đủ chẩn đoán? — **Không**. Cần giữ object hoặc wrap với cause để bảo toàn cả suppressed exceptions.

**8.** Khi ghi log tại một lỗi liên quan thanh toán, có nên thêm toàn bộ thông tin thẻ/credential vào context? — **Không**. Chỉ thêm mã tham chiếu an toàn và dữ liệu được phép, áp dụng redaction.

## Tài liệu chính thức còn áp dụng

- [Java Language Specification 17, §11.2.2 — Exception Analysis of Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2.2): điều kiện precise rethrow với biến catch final/effectively final.
- [Java Language Specification 17, §14.20 — The `try` statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): try/catch, multi-catch, try-with-resources.
- [Java SE 17 API — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): overload `log(Level, String, Throwable)` và `LogRecord.thrown`.
- [Java SE 17 API — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, `getStackTrace()`, `getSuppressed()` và `fillInStackTrace()`.

**Ghi nhớ:** **Log đủ ngữ cảnh và truyền `Throwable`; `throw ex;` nếu giữ loại lỗi; `throw new MeaningfulException("context", ex);` nếu đổi loại lỗi; tránh lặp log nhiều tầng.** Nhờ đó lỗi vẫn có thể truy về nguồn gốc mà chương trình giữ được hợp đồng exception rõ ràng.