# Multi-catch trong Java: Giữ nguyên nguyên nhân và thông tin chẩn đoán

## 1. Mục tiêu: bắt lỗi nhưng vẫn biết vì sao lỗi xảy ra

Khi một thao tác thất bại, việc ứng dụng chỉ thông báo "Có lỗi" chưa đủ để chẩn đoán. Ta cần biết **loại lỗi gốc**, **thông điệp**, **vị trí phát sinh**, **chuỗi nguyên nhân** và, khi có, **các lỗi phụ lúc dọn dẹp tài nguyên**.

Từ Java 7, cú pháp **multi-catch** cho phép gom một số exception type vào một `catch` khi chúng dùng chung hành động xử lý:

```java
try {
    performOperation();
} catch (IOException | ParseException e) {
    // Cùng chính sách xử lý cho lỗi đọc dữ liệu và lỗi phân tích dữ liệu.
}
```

Trong ngữ cảnh trên, giả sử `performOperation()` có khai báo `throws IOException, ParseException`. `e` là **chính đối tượng exception đã được ném ra**, dù nhánh bắt liệt kê hai kiểu. Multi-catch **không tạo một exception mới**, không tự xoá thông tin, và không biến một `ParseException` thành `IOException`.

**Quy tắc quan trọng nhất:** Nếu cần truyền lỗi lên tầng trên dưới dạng exception khác, phải **gắn exception gốc làm `cause`**; nếu giữ nguyên loại lỗi thì có thể `throw e;`. Đừng chỉ lấy `e.getMessage()` rồi tạo exception mới mà bỏ đối tượng gốc.

Các API và cú pháp trình bày ở đây vẫn được hỗ trợ trong Java hiện đại, bao gồm Java 17+.

## 2. Những thông tin có trong một `Throwable`

Hầu hết exception ở Java kế thừa `java.lang.Throwable`. Một exception mang những thông tin độc lập, mỗi loại phục vụ việc phân tích lỗi khác nhau:

| Thành phần | API thường dùng | Ý nghĩa |
| --- | --- | --- |
| Loại exception thực tế | `e.getClass()` | Phân biệt `IOException`, `ParseException`, exception nghiệp vụ... |
| Thông điệp | `e.getMessage()` | Mô tả ngắn; có thể là `null` |
| Stack trace | `e.getStackTrace()` hoặc logger nhận `Throwable` | Dấu vết lời gọi lúc stack trace của exception được tạo/ghi |
| Nguyên nhân | `e.getCause()` | Exception đã gây ra exception hiện tại; có thể là `null` |
| Lỗi bị ẩn để ưu tiên lỗi chính | `e.getSuppressed()` | Thường là lỗi xảy ra khi đóng tài nguyên bằng `try-with-resources` |
| Thông tin riêng theo loại exception | Ví dụ `ParseException.getErrorOffset()` | Chi tiết chuyên biệt giúp định vị lỗi |

**Thông điệp không thay thế stack trace hay cause.** Hai lỗi cùng nội dung `"read failed"` có thể phát sinh tại hai vị trí khác nhau, và một lỗi cấp cao có thể cần thêm ngữ cảnh nghiệp vụ mà lỗi cấp thấp không biết.

Một chuỗi nguyên nhân thường có dạng:

```text
ServiceException("Cannot process job")
  └── cause: IOException("disk unavailable")
         └── stack trace: nơi lỗi đọc dữ liệu được tạo
```

Trong thực tế, cause cũng có thể có cause riêng, tạo thành một **exception chain**. Khi đưa cả đối tượng `Throwable` cho công cụ ghi log, công cụ phù hợp sẽ thể hiện loại lỗi, thông điệp, stack trace và chuỗi cause; nếu chỉ đưa chuỗi `e.getMessage()` thì thông tin này không tự xuất hiện.

## 3. Multi-catch giữ lại exception gốc như thế nào?

### 3.1. Một biến `e` cho nhiều loại lỗi

```java
import java.io.IOException;
import java.text.ParseException;

static void runStep() throws IOException, ParseException {
    // Ví dụ: có thể thất bại khi đọc hoặc khi phân tích dữ liệu.
}

static void execute() throws IOException, ParseException {
    try {
        runStep();
    } catch (IOException | ParseException e) {
        throw e; // ném lại chính đối tượng đã bắt
    }
}
```

Đây là đoạn **minh họa đặt trong một lớp** (không phải tệp Java độc lập): khi `e` thực tế là `IOException`, `throw e;` ném lại đúng đối tượng đó; khi là `ParseException`, kết quả tương tự.

- Multi-catch dùng dấu `|` để liệt kê **những kiểu exception thay thế**.
- Các kiểu trong một multi-catch không được có quan hệ kiểu con/kiểu cha trực tiếp. Ví dụ `catch (FileNotFoundException | IOException e)` là lỗi biên dịch vì `FileNotFoundException extends IOException`.
- Biến exception của multi-catch **ngầm là `final`**: không thể gán `e = new IOException();`.
- Kiểu khai báo của `e` được suy ra từ kiểu chung thích hợp của các nhánh. Vì vậy, trong thân `catch`, hãy dùng các API chung có trên `Throwable`/`Exception` hoặc kiểm tra subtype khi thật sự cần.
- Java hỗ trợ **precise rethrow** trong tình huống này: khi `throw e;`, trình biên dịch có thể phân tích các checked exception thực sự có thể được ném từ `try`, thay vì buộc ta khai báo một kiểu tổng quát không cần thiết.

Nếu hai loại lỗi cần cách xử lý khác nhau, có thể tách thành nhiều `catch` hoặc kiểm tra subtype có chủ đích. Đừng gom chúng chỉ để tiết kiệm dòng code.

### 3.2. Giữ nguyên đối tượng bằng `throw e;`

```java
try {
    loadRecord();
} catch (IOException | ParseException e) {
    throw e;
}
```

Đoạn này là **minh họa trong phương thức** mà `loadRecord()` có thể ném hai exception nói trên; phương thức bao ngoài cần khai báo hoặc xử lý các checked exception tương ứng.

**Ưu điểm:** giữ **chính exception ban đầu**, bao gồm class cụ thể, message, stack trace và cause đã có. Việc rethrow không tự biến lỗi thành một đối tượng khác. Phù hợp khi tầng hiện tại chưa có trách nhiệm chuyển đổi exception sang khái niệm của tầng khác.

**Giới hạn:** tầng gọi tiếp theo phải hiểu và xử lý những kiểu exception đó nếu chúng là checked exception. Đừng để API nghiệp vụ lộ quá nhiều chi tiết hạ tầng khi thực sự cần một ranh giới trừu tượng rõ ràng.

### 3.3. Bọc lỗi có ngữ cảnh nhưng giữ `cause`

```java
final class ImportException extends RuntimeException {
    ImportException(String message, Throwable cause) {
        super(message, cause);
    }
}

// Bên trong phương thức import của ứng dụng:
try {
    readAndParse();
} catch (IOException | ParseException e) {
    throw new ImportException("Failed to import batch 17", e);
}
```

Đây là hai **đoạn minh họa trong cấu trúc lớp/phương thức tương ứng**. Điểm quyết định là đối số thứ hai `e` được truyền cho constructor `super(message, cause)`.

Lỗi mới có:

- Message riêng của tầng nghiệp vụ, ví dụ ID lô xử lý hoặc tên thao tác **không chứa dữ liệu nhạy cảm**.
- **Cause chính là exception gốc**: `wrapped.getCause() == e` là `true`.
- Stack trace của lỗi mới ở vị trí chuyển đổi exception, và stack trace **riêng của cause** ở vị trí xảy ra lỗi ban đầu.
- Những thông tin chuyên biệt của `IOException` hoặc `ParseException` vẫn có thể truy cập qua cause nếu tầng xử lý cần.

**Không làm như sau:**

```java
// Sai nếu mục tiêu là giữ nguyên nguyên nhân:
throw new ImportException(e.getMessage(), null);
```

Dù message nghe giống nhau, cause đã bị bỏ. Tương tự, `throw new RuntimeException("Import failed");` sẽ cắt mất mối liên hệ với exception gốc nếu không truyền `e`.

## 4. Chương trình Java 17+ đầy đủ: giữ cause và thông tin chẩn đoán

Chương trình sau dùng hai checked exception khác nhau trong cùng một multi-catch, bọc lỗi vào `ServiceException` có ngữ cảnh, rồi truy vấn cause, message, vị trí phát sinh. Phần cuối còn mô phỏng lỗi đóng tài nguyên để giải thích `getSuppressed()`.

Lưu đúng tên tệp **`MultiCatchDiagnosticsDemo.java`**:

```java
import java.io.IOException;
import java.text.ParseException;

public final class MultiCatchDiagnosticsDemo {

    static final class ServiceException extends RuntimeException {
        ServiceException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void load(String kind) throws IOException, ParseException {
        if ("io".equals(kind)) {
            throw new IOException("disk unavailable");
        }
        if ("parse".equals(kind)) {
            throw new ParseException("invalid field", 2);
        }
    }

    static void process(String kind) {
        try {
            load(kind);
        } catch (IOException | ParseException e) {
            throw new ServiceException("job=" + kind + " failed", e);
        }
    }

    static void report(String kind) {
        try {
            process(kind);
        } catch (ServiceException e) {
            Throwable root = e.getCause();
            System.out.println(kind + ": "
                    + root.getClass().getSimpleName());
            System.out.println("context=" + e.getMessage());
            System.out.println("cause=" + root.getMessage());
            System.out.println("origin="
                    + root.getStackTrace()[0].getMethodName());
        }
    }

    static final class ClosingFailure implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static void demonstrateSuppressed() {
        try (ClosingFailure ignored = new ClosingFailure()) {
            throw new IOException("body failed");
        } catch (IOException e) {
            System.out.println("primary=" + e.getMessage());
            System.out.println("suppressed=" + e.getSuppressed().length);
            System.out.println("suppressedMessage="
                    + e.getSuppressed()[0].getMessage());
        }
    }

    public static void main(String[] args) {
        report("io");
        report("parse");
        demonstrateSuppressed();
    }
}
```

Biên dịch và chạy với JDK 17 hoặc phiên bản Java hiện đại tương thích:

```bash
javac MultiCatchDiagnosticsDemo.java
java MultiCatchDiagnosticsDemo
```

**Stdout của chương trình:**

```text
io: IOException
context=job=io failed
cause=disk unavailable
origin=load
parse: ParseException
context=job=parse failed
cause=invalid field
origin=load
primary=body failed
suppressed=1
suppressedMessage=close failed
```

**Phân tích:**

1. `load("io")` ném `IOException` và `load("parse")` ném `ParseException`. Hai trường hợp đều vào cùng `catch (IOException | ParseException e)`.
2. Tầng `process` tạo `ServiceException` nhưng **truyền `e` làm cause**; do đó `getCause()` trả đúng loại lỗi đã phát sinh.
3. `context` mô tả thao tác cấp cao; `cause` mô tả lỗi cấp thấp. Cả hai đều hữu ích, không nên chọn một và bỏ cái kia.
4. `root.getStackTrace()[0].getMethodName()` là `load` trong chương trình này vì exception chuẩn được tạo tại đó. Trong ứng dụng tổng quát, đừng giả định stack trace luôn có phần tử: một exception có thể được cấu hình không ghi stack trace; khi cần ghi log hãy chuyển **toàn bộ đối tượng exception** cho logger.
5. `demonstrateSuppressed()` có lỗi chính ở thân `try` là `"body failed"`. Khi `close()` tiếp tục thất bại, lỗi `"close failed"` được giữ trong `getSuppressed()`, thay vì che mất lỗi chính.

Đây là chương trình **hoàn chỉnh**, không cần thư viện bên ngoài. Các ví dụ minh họa rời ở những mục khác chỉ nhằm giải thích quy tắc và cần đặt vào lớp/phương thức phù hợp nếu muốn biên dịch.

## 5. Cause và suppressed exception không phải một

### 5.1. Cause: lỗi gốc dẫn đến lỗi ở tầng khác

Giả sử xử lý đơn hàng gọi tầng lưu trữ. Khi tầng lưu trữ ném `IOException`, dịch vụ có thể bọc nó bằng `OrderProcessingException`:

```java
throw new OrderProcessingException(
        "Cannot complete order update", ioException);
```

Constructor của `OrderProcessingException` cần gọi `super(message, cause)`. Đây là **quan hệ nguyên nhân**: một exception ở tầng dưới dẫn tới exception mới ở tầng trên.

### 5.2. Suppressed: lỗi khác được giữ lại khi lỗi chính được ưu tiên

Ngược lại, ở `try-with-resources`, một lỗi trong thân `try` và một lỗi khi `close()` đều có thể xảy ra trong cùng lượt thực thi:

```java
try (Resource resource = openResource()) {
    updateResource(resource); // có thể ném lỗi chính
}
// Trình biên dịch đảm bảo gọi close() theo quy tắc AutoCloseable.
```

Nếu thân `try` đã ném lỗi rồi `close()` lại lỗi, **lỗi từ thân `try` vẫn được truyền ra**, còn lỗi đóng tài nguyên được **suppressed** và có thể đọc qua `getSuppressed()`.

| Thuộc tính | Cause | Suppressed |
| --- | --- | --- |
| Ý nghĩa | Lỗi nào gây ra lỗi hiện tại? | Những lỗi khác nào cũng xảy ra nhưng nhường ưu tiên cho lỗi chính? |
| API truy cập | `getCause()` | `getSuppressed()` |
| Dạng dữ liệu | Một `Throwable` hoặc `null` | Mảng `Throwable[]`, có thể rỗng |
| Nguồn thường gặp | `new HigherLevelException(message, cause)` | `try-with-resources` tự lưu lỗi lúc `close()` |
| Có thể tồn tại đồng thời? | Có | Có |

**Đừng nhầm `getCause() == null` với “không còn thông tin lỗi khác”**: exception vẫn có stack trace, message và có thể có suppressed exceptions. Ngược lại, cause cũng có cause và suppressed của chính nó.

### 5.3. Khi nào dùng `addSuppressed`?

Thông thường **không cần gọi tay**: `try-with-resources` tự quản lý suppressed exceptions. Khi có nhiều lỗi độc lập mà ứng dụng phải chọn một lỗi chính để ném, có thể gắn các lỗi phụ vào exception chính qua `primary.addSuppressed(secondary)`.

```java
IOException primary = new IOException("write failed");
IOException cleanup = new IOException("cleanup failed");
primary.addSuppressed(cleanup);
throw primary;
```

Đây là minh họa trong một phương thức có `throws IOException` hoặc có handler thích hợp. Chỉ dùng `addSuppressed` khi **đúng quan hệ lỗi chính/lỗi phụ**; không thay cause bằng suppressed cho một lỗi thực sự tạo nên lỗi tầng trên. Không gắn một exception làm suppressed của chính nó.

## 6. Tránh mất chẩn đoán khi ghi log

Đối tượng exception là nguồn dữ liệu chính để quan sát. Logger phải nhận **`Throwable`**, không chỉ nhận message. Ví dụ dùng **`System.Logger`** (API có từ Java 9, dùng tốt với Java 17+):

```java
private static final System.Logger LOG =
        System.getLogger("application.import");

static void handleFailure(Exception e, String operation) {
    LOG.log(System.Logger.Level.ERROR,
            "Operation " + operation + " failed", e);
}
```

Đây là đoạn **đặt trong một lớp**, dùng logger của ứng dụng. Tùy hệ thống logging được cấu hình, bản ghi có thể bao gồm cause chain và suppressed exceptions. Bản thân việc in `e.getMessage()` **không có đủ** những thông tin ấy.

Với `java.util.logging`, cách truyền exception cũng rõ ràng:

```java
logger.log(java.util.logging.Level.SEVERE,
        "Import operation failed", e);
```

Các cách thường gây mất dữ liệu:

```java
// Chỉ còn một chuỗi; không còn stack trace/cause đi kèm log.
logger.warning(e.getMessage());

// Ghi bản ghi "lỗi" nhưng bỏ exception cụ thể.
logger.log(java.util.logging.Level.SEVERE, "Import failed");

// Chỉ in thông điệp ở stdout/stderr, không đủ dữ liệu chẩn đoán.
System.err.println(e.getMessage());
```

`e.printStackTrace()` có thể hữu ích khi thử nghiệm cục bộ vì nó in chuỗi cause/suppressed vào stream, nhưng trong dịch vụ thực tế nên dùng logger có cấu hình mức log, định dạng và hệ thống tập trung phù hợp. **Tránh gọi `printStackTrace()` rồi log cùng exception ở cùng tầng**, vì tạo bản ghi trùng.

### 6.1. Thêm ngữ cảnh hữu ích, an toàn

Nội dung cần cho người vận hành thường là:

- **Thao tác**: `"importOrders"`, `"parseConfig"`, `"loadProfile"`.
- **Định danh tương quan**: trace ID / request ID / job ID đã có ở hệ thống.
- **Đối tượng xử lý**: một mã được cho phép ghi log theo chính sách dữ liệu.
- **Kết quả xử lý**: thử lại, trả lỗi cho caller hay dừng xử lý.

Không ghi mật khẩu, access token, secret, dữ liệu cá nhân hoặc toàn bộ request body chỉ để “đầy đủ chẩn đoán”. Message của exception từ thư viện bên dưới cũng có thể chứa thông tin nhạy cảm; cần áp dụng chính sách redaction/ghi log của hệ thống.

**Ghi log ở ranh giới chịu trách nhiệm xử lý lỗi**, thay vì mọi tầng đều log rồi ném lại. Ví dụ tầng repository ném lỗi có cause, tầng service bọc lỗi kèm ngữ cảnh, còn tầng HTTP / job runner log một lần khi thực sự quyết định phản hồi hoặc kết thúc tác vụ.

## 7. Những cách xử lý làm mất nguyên nhân

### 7.1. Chỉ giữ lại message

```java
catch (IOException | ParseException e) {
    throw new IllegalStateException(e.getMessage());
}
```

Lỗi này có thể mang lại một message, nhưng **`getCause() == null`** và stack trace của lỗi gốc không còn trong exception mới.

**Sửa:**

```java
catch (IOException | ParseException e) {
    throw new IllegalStateException("Failed to load document", e);
}
```

### 7.2. Nuốt lỗi rồi trả giá trị có vẻ hợp lệ

```java
catch (IOException | ParseException e) {
    return null; // Nếu null không được hợp đồng định nghĩa là kết quả lỗi
}
```

Điều này có thể khiến code gọi tiếp theo ném `NullPointerException` ở vị trí xa lỗi ban đầu. Nếu nghiệp vụ thực sự cho phép giá trị dự phòng, hãy thiết kế rõ hợp đồng trả về (ví dụ `Optional` hoặc kết quả có trạng thái) và quan sát lỗi theo chính sách. Nếu xử lý không thể tiếp tục, ném lại hoặc chuyển đổi exception với cause.

### 7.3. Bắt quá rộng hoặc bắt sai kiểu

```java
catch (Exception e) {
    throw new RuntimeException("failed", e);
}
```

Đoạn này **không làm mất cause**, nhưng bắt cả các lỗi khác mà người viết có thể chưa muốn xử lý cùng một chính sách, ví dụ lỗi lập trình dạng `NullPointerException`. Multi-catch liệt kê **những tình huống cụ thể thực sự cùng cách xử lý** giúp ý đồ rõ hơn.

Không nên dùng `catch (Throwable e)` chỉ để “giữ mọi thông tin”; cách đó còn bắt cả `Error`, thường không phù hợp với xử lý lỗi nghiệp vụ thông thường.

### 7.4. Thay thế exception trong `finally`

Nếu `finally` ném một exception mới, nó có thể làm mất exception đang chờ được truyền ra khỏi `try`. Khi cần đóng tài nguyên, dùng `try-with-resources` để giữ lỗi chính và lưu lỗi dọn dẹp qua suppressed exceptions.

Nếu dùng cleanup phức tạp thủ công, phải thiết kế rõ cách xử lý cả hai lỗi, thay vì để lỗi cleanup âm thầm che lấp lỗi chính.

### 7.5. Đổi exception thành chuỗi trước khi chuyển tầng

```java
// Chỉ còn một String, không phải exception chain.
String errorText = e.toString();
queue.send(errorText);
```

Đối với thông điệp giữa dịch vụ/process, một `Throwable` không thể tự động được truyền nguyên vẹn qua giao thức ngoài JVM. Hãy thiết kế **error contract** riêng (mã lỗi, mô tả an toàn, trace ID, ngữ cảnh được phép công bố), đồng thời giữ exception thật và cause trong quan sát/log của nơi phát sinh. Đừng đưa stack trace hoặc dữ liệu nhạy cảm vào phản hồi công khai chỉ để thuận tiện debug.

## 8. Tái ném chính xác, thay kiểu exception và giữ trách nhiệm từng tầng

| Mục tiêu | Mẫu xử lý | Thông tin được giữ |
| --- | --- | --- |
| Chưa xử lý, chỉ chuyển lỗi lên | `throw e;` | Cùng đối tượng exception, loại cụ thể, message, stack trace, cause, suppressed |
| Chuyển từ lỗi hạ tầng sang lỗi nghiệp vụ | `throw new ServiceException("context", e);` | Context mới + toàn bộ nguyên nhân nằm trong `getCause()` |
| Ghi log ở điểm kết thúc tác vụ | `LOG.log(Level.ERROR, "context", e);` | Logger có thể ghi toàn bộ exception chain |
| Đóng tài nguyên có thể lỗi | `try-with-resources` | Lỗi chính và lỗi `close()` bị suppressed |
| Xử lý từng loại khác nhau | Các `catch` riêng hoặc phân loại có chủ đích | Không xoá sự khác biệt giữa các tình huống lỗi |

Ví dụ **precise rethrow** vẫn áp dụng khi multi-catch có checked exceptions:

```java
static void rethrowPrecisely(String mode)
        throws IOException, ParseException {
    try {
        if ("io".equals(mode)) {
            throw new IOException("read failure");
        }
        if ("parse".equals(mode)) {
            throw new ParseException("parse failure", 0);
        }
    } catch (IOException | ParseException e) {
        throw e;
    }
}
```

Đây là khai báo **phương thức đặt trong lớp** có `import java.io.IOException;` và `import java.text.ParseException;`. Nó không cần `throws Exception` vì compiler có thể phân tích các checked exception tương ứng. Trường hợp này nên rethrow nguyên bản nếu caller có trách nhiệm xử lý hai loại đó; nếu một API cần quy ước exception riêng, wrapping có cause có thể phù hợp hơn.

**Lưu ý về ngắt luồng:** Nếu đang xử lý `InterruptedException`, việc “bắt rồi tiếp tục như chưa có gì” có thể làm mất yêu cầu ngắt. Thông thường nên truyền lại exception hoặc khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` khi không thể truyền checked exception lên trên. Không gộp `InterruptedException` vô điều kiện vào chính sách retry/log chung của các lỗi I/O hoặc parse.

## 9. Kiểm tra một exception có thật sự giữ cause không?

Không cần so sánh toàn bộ stack trace bằng chuỗi, vì số dòng và tên file có thể thay đổi theo trình biên dịch hoặc cách chạy. Với code kiểm thử, có thể kiểm tra **quan hệ đối tượng**, **kiểu** và **message**:

```java
IOException original = new IOException("disk unavailable");
ServiceException wrapped =
        new ServiceException("job failed", original);

System.out.println(wrapped.getCause() == original); // true
System.out.println(wrapped.getCause() instanceof IOException); // true
System.out.println(wrapped.getMessage()); // job failed
```

Đoạn này minh họa khi `ServiceException` đã được định nghĩa như phần chương trình đầy đủ ở trên. Với unit test, dùng assertions như `assertSame(original, wrapped.getCause())` (tùy thư viện kiểm thử của dự án).

Có thể kiểm tra tương tự cho suppressed exceptions:

```java
IOException primary = new IOException("primary");
IOException cleanup = new IOException("cleanup");
primary.addSuppressed(cleanup);

System.out.println(primary.getSuppressed().length); // 1
System.out.println(primary.getSuppressed()[0] == cleanup); // true
```

Đừng dùng `getMessage()` làm cách duy nhất xác nhận cause. Một exception có thể có message `null`, hoặc nhiều exception có cùng message nhưng khác nguyên nhân.

## 10. Câu hỏi ôn tập

**Câu 1.** Trong `catch (IOException | ParseException e)`, biến `e` có mất loại exception thực tế không?  
**Đáp án:** Không. Đối tượng vẫn là `IOException` hoặc `ParseException` tương ứng; multi-catch chỉ kết hợp các nhánh xử lý chung.

**Câu 2.** Vì sao `throw new ServiceException("failed", e);` giữ chẩn đoán tốt hơn `throw new ServiceException("failed", null);`?  
**Đáp án:** Cách thứ nhất giữ `e` trong `getCause()` cùng class cụ thể, message và stack trace gốc; cách thứ hai cắt chuỗi nguyên nhân.

**Câu 3.** `e.getMessage()` có luôn là đủ để tái hiện sự cố không?  
**Đáp án:** Không. Nó có thể `null` hoặc thiếu vị trí phát sinh, loại lỗi cụ thể, cause và suppressed exceptions.

**Câu 4.** Vì sao lỗi `close()` trong `try-with-resources` không nhất thiết che lỗi từ thân `try`?  
**Đáp án:** Nếu thân `try` đã ném lỗi chính, lỗi khi đóng tài nguyên được lưu vào `getSuppressed()` của lỗi chính.

**Câu 5.** Khi một tầng muốn giữ nguyên checked exception đã bắt thì dùng gì?  
**Đáp án:** Thường dùng `throw e;` và khai báo/xử lý kiểu exception tương ứng ở API bao ngoài. Khi cần đổi loại lỗi theo hợp đồng tầng, bọc bằng constructor nhận cause.

**Câu 6.** Có nên ghi log cùng exception ở ba tầng và lại ném tiếp cả ba lần?  
**Đáp án:** Thường không. Hãy thêm ngữ cảnh thích hợp trong exception chain, và ghi log đầy đủ một lần ở ranh giới có trách nhiệm xử lý.

## 11. Ghi nhớ

- **Multi-catch giữ nguyên đối tượng exception gốc** trong biến `e`. Biến này ngầm `final`; `throw e;` là cách tái ném nguyên bản khi thích hợp.
- **Wrapping phải có cause:** `new HigherLevelException("context", e)` để kết hợp ngữ cảnh nghiệp vụ với stack trace và loại exception ở tầng dưới.
- **Message, cause, stack trace và suppressed là các thông tin khác nhau**. Bỏ đối tượng exception rồi chỉ giữ message là làm mất dữ liệu chẩn đoán.
- **Try-with-resources bảo tồn lỗi chính** khi đóng tài nguyên cũng lỗi; các lỗi đóng tài nguyên có thể đọc bằng `getSuppressed()`.
- **Logger nên nhận cả đối tượng `Throwable`**, thêm ngữ cảnh an toàn và tránh ghi trùng ở nhiều tầng.

### Tài liệu chính thức còn hiệu lực

- [Java Language Specification — `14.20 `try` Statement, exception handling và multi-catch](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html#jls-14.20).
- [Java SE 26 API — `java.lang.Throwable`: cause, stack trace, suppressed exceptions](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Throwable.html).
- [Java SE 26 API — `java.lang.System.Logger`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.Logger.html).
- [Java SE 26 API — `AutoCloseable`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/AutoCloseable.html).