# Constructor hỗ trợ `message` và `cause` khi thiết kế ngoại lệ tùy chỉnh trong Java

Khi tạo một lớp ngoại lệ tùy chỉnh (*custom exception*), việc kế thừa `Exception` hay `RuntimeException` chỉ là bước đầu. Muốn người gọi hiểu **điều gì thất bại** và người vận hành truy được **nguyên nhân kỹ thuật ban đầu**, ngoại lệ nên có constructor nhận **message** và **cause**:

```java
public DataLoadException(String message, Throwable cause) {
    super(message, cause);
}
```

Hai tham số có nhiệm vụ khác nhau: `message` giải thích lỗi trong ngữ cảnh của **lớp đang báo lỗi**, còn `cause` tham chiếu đến **đối tượng `Throwable` đã khiến thao tác thất bại**. Khi giữ cả hai, chương trình có thể tạo thêm thông tin ở mỗi tầng mà không mất stack trace, loại ngoại lệ và suppressed exceptions của lỗi gốc.

Bài viết tập trung vào cách thiết kế constructor cho ngoại lệ tùy chỉnh trong Java 17+, các overload thường dùng, cách truyền `super(...)`, sự khác biệt giữa `message` và `cause`, checked/unchecked exception, `null`, `initCause()`, cách bảo toàn chẩn đoán qua nhiều tầng và các lỗi triển khai phổ biến.

## 1. `message` và `cause` không phải cùng một thứ

`Throwable` cung cấp hai thuộc tính chẩn đoán cơ bản:

| Thuộc tính | API đọc | Ý nghĩa | Ví dụ |
| --- | --- | --- | --- |
| *Detail message* | `getMessage()` | Mô tả lỗi của **đối tượng ngoại lệ hiện tại** | `Cannot load customer profile` |
| *Cause* | `getCause()` | Đối tượng ngoại lệ trước đó, trực tiếp góp phần gây ra ngoại lệ hiện tại | `IOException("disk unavailable")` |
| Stack trace | `getStackTrace()` / `printStackTrace()` | Dấu vết nơi thông tin lỗi được ghi lại | Frame ở repository/service |
| Suppressed exceptions | `getSuppressed()` | Lỗi phụ được giữ lại, thường xảy ra khi đóng tài nguyên | `IOException("close failed")` |

Ví dụ giả lập chuỗi lỗi:

```text
DataLoadException("Cannot load customer profile")   ← message tầng service
    |
    +-- cause: IOException("disk unavailable")      ← nguyên nhân ở tầng I/O
                     |
                     +-- stack trace: thao tác đọc tệp
```

Lỗi `IOException` vẫn là **một đối tượng riêng**: nó không biến thành `DataLoadException`. Constructor nhận `cause` chỉ tạo **mối liên kết nguyên nhân**, để người dùng `getCause()` và công cụ in stack trace có thể đi từ lỗi nghiệp vụ về lỗi hạ tầng.

**Thông điệp không tự động thay thế nguyên nhân.** Viết `super("Cannot load: " + ex.getMessage())` có thể giúp người đọc thấy một câu mô tả, nhưng `getCause()` của ngoại lệ mới vẫn bằng `null` và mối liên kết đến đối tượng `ex` bị mất.

## 2. Chọn lớp cha: checked hay unchecked?

Một custom exception thường kế thừa một trong hai lớp:

- **`Exception`** (không kế thừa `RuntimeException`): checked exception. Nếu phương thức có khả năng để lỗi ấy thoát ra, Java thường buộc bên gọi xử lý bằng `catch` hoặc khai báo `throws` phù hợp.
- **`RuntimeException`**: unchecked exception. Không bắt buộc khai báo `throws` để biên dịch, nhưng vẫn có thể và thường nên dùng `cause` để bảo toàn lỗi gốc.

Ví dụ chữ ký:

```java
class DataLoadException extends Exception {
    DataLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}

class ServiceFailureException extends RuntimeException {
    ServiceFailureException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Đây là hai lớp minh họa hợp lệ, không có `main` độc lập. Hai kiểu có cùng constructor nhưng **hợp đồng với bên gọi** khác nhau. Không chọn checked hay unchecked chỉ vì muốn viết ít mã `try-catch` hơn; hãy dựa vào khả năng phục hồi, hợp đồng API và quy tắc thiết kế của module.

Không nên tạo một ngoại lệ nghiệp vụ bình thường bằng `extends Error`. Nhánh `Error` biểu diễn các trường hợp mà ứng dụng thường không được kỳ vọng phục hồi theo cách thông thường.

## 3. Bốn constructor phổ biến của custom exception

Một ngoại lệ có thể cung cấp bốn overload, tương ứng các cách tạo đối tượng phổ biến trong Java:

```java
public class DataLoadException extends Exception {
    public DataLoadException() {
        super();
    }

    public DataLoadException(String message) {
        super(message);
    }

    public DataLoadException(String message, Throwable cause) {
        super(message, cause);
    }

    public DataLoadException(Throwable cause) {
        super(cause);
    }
}
```

Đây là **tệp lớp hợp lệ** nếu lưu thành `DataLoadException.java`; nó không chứa `main()`. Các overload có vai trò riêng:

| Constructor | Cách dùng điển hình | `getMessage()` | `getCause()` |
| --- | --- | --- | --- |
| `DataLoadException()` | Lỗi đơn giản không có ngữ cảnh chi tiết | `null` | `null` |
| `DataLoadException(String message)` | Báo lỗi mới độc lập | Chuỗi `message` | `null` |
| `DataLoadException(String message, Throwable cause)` | Dịch ngoại lệ tại ranh giới tầng, thêm bối cảnh | Chính chuỗi `message` được truyền | Chính đối tượng `cause` |
| `DataLoadException(Throwable cause)` | Wrapper gần như chỉ bao nguyên nhân | `cause == null ? null : cause.toString()` | Chính đối tượng `cause` |

Có thể không cần đủ bốn overload nếu API chỉ có một hoặc hai nhu cầu tạo lỗi rõ ràng. Tuy nhiên, khi xuất bản một thư viện cho nhiều bên dùng, cung cấp các overload có ý nghĩa giúp người gọi không phải gắn `cause` muộn hoặc tự xây message vụng về.

**Lưu ý:** Constructor `DataLoadException(Throwable cause)` không tạo một message nghiệp vụ mới. Theo hợp đồng `Exception(Throwable cause)`, message được dẫn xuất từ `cause.toString()`. Nếu cần hiển thị ngữ cảnh có ý nghĩa, thường ưu tiên overload `(String, Throwable)`.

## 4. Chương trình Java 17+: kiểm tra chính xác từng overload

Lưu thành `ConstructorOverloadsDemo.java`:

```java
import java.io.IOException;

public class ConstructorOverloadsDemo {
    static class DomainException extends Exception {
        DomainException() {
            super();
        }

        DomainException(String message) {
            super(message);
        }

        DomainException(String message, Throwable cause) {
            super(message, cause);
        }

        DomainException(Throwable cause) {
            super(cause);
        }
    }

    public static void main(String[] args) {
        IOException original = new IOException("disk offline");

        DomainException empty = new DomainException();
        DomainException messageOnly =
                new DomainException("cannot load profile");
        DomainException both =
                new DomainException("cannot load profile", original);
        DomainException causeOnly = new DomainException(original);

        System.out.println("emptyMessage=" + empty.getMessage());
        System.out.println("emptyCause=" + empty.getCause());

        System.out.println("messageOnly=" + messageOnly.getMessage());
        System.out.println("messageOnlyCause=" + messageOnly.getCause());

        System.out.println("bothMessage=" + both.getMessage());
        System.out.println("bothCauseIsOriginal="
                + (both.getCause() == original));

        System.out.println("causeOnlyMessage=" + causeOnly.getMessage());
        System.out.println("causeOnlyIsOriginal="
                + (causeOnly.getCause() == original));
    }
}
```

Biên dịch và chạy từ thư mục có tệp:

```bash
javac -encoding UTF-8 ConstructorOverloadsDemo.java
java ConstructorOverloadsDemo
```

Kết quả xác định:

```text
emptyMessage=null
emptyCause=null
messageOnly=cannot load profile
messageOnlyCause=null
bothMessage=cannot load profile
bothCauseIsOriginal=true
causeOnlyMessage=java.io.IOException: disk offline
causeOnlyIsOriginal=true
```

Ở dạng `(String, Throwable)`, Java **không tự chèn** message từ cause vào message của wrapper. Ta chủ động quyết định câu mô tả có ý nghĩa ở tầng hiện tại. Ở dạng `(Throwable)`, message mặc định được lấy từ `cause.toString()`, bao gồm tên lớp `java.io.IOException` và message của cause trong ví dụ.

Lệnh so sánh `==` chứng minh wrapper giữ tham chiếu đến **chính đối tượng nguyên nhân ban đầu**, không tự tạo bản sao của `IOException`.

## 5. Cách viết `super(message, cause)` đúng

Constructor là nơi khởi tạo đối tượng ngoại lệ và phải gọi constructor của lớp cha theo quy tắc Java. Trong Java 17, lời gọi constructor tường minh `super(...)` hoặc `this(...)` phải là câu lệnh đầu tiên của constructor.

Mẫu chuẩn:

```java
public ConfigLoadException(String message, Throwable cause) {
    super(message, cause);
}
```

Đoạn trên là **constructor minh họa** của một lớp `ConfigLoadException` kế thừa `Exception` hoặc `RuntimeException` có overload tương ứng.

Nếu muốn chuẩn hóa message trước khi chuyển cho lớp cha, có thể dùng biểu thức trong tham số:

```java
public ConfigLoadException(String key, Throwable cause) {
    super("Unable to load config key: " + key, cause);
}
```

Trong thiết kế API thật, cần cân nhắc xem `key` có chứa dữ liệu nhạy cảm không trước khi đưa vào message và log.

**Không viết**:

```java
public ConfigLoadException(String message, Throwable cause) {
    super(message);
    initCause(cause);
}
```

Mã trên có thể hợp lệ trong một lớp kế thừa `Exception` nếu cause chưa được khởi tạo, nhưng đây là cách vòng vèo không cần thiết: khi đã có `super(message, cause)` thì nên dùng trực tiếp nó. Nếu `initCause` bị gọi thêm một lần ở nơi khác, hợp đồng khởi tạo cause một lần sẽ bị vi phạm.

**Đặc biệt không gọi cả `super(message, cause)` và `initCause(cause)`:** cause đã được khởi tạo qua constructor hai tham số; lần gọi thêm ném `IllegalStateException`.

## 6. Trường hợp `null` và trạng thái khởi tạo cause

Đây là một khác biệt tinh tế giữa các constructor:

- `super(message)` tạo đối tượng có cause **chưa được khởi tạo**. Sau đó `initCause(...)` có thể được gọi một lần.
- `super(message, null)` tạo đối tượng có cause **đã được khởi tạo thành `null`**. Sau đó `initCause(...)` **không** được phép gọi lại.
- `super(cause)` nhận `null` hợp lệ, message được suy ra thành `null` nếu cause bằng `null`; cause vẫn được coi là đã khởi tạo.
- `getCause() == null` **không cho biết** cause đã được khởi tạo hay chưa.

| Cách tạo | `getCause()` ban đầu | Có thể `initCause(realCause)` sau đó? |
| --- | --- | --- |
| `new Exception("message")` | `null` | Có, một lần nếu chưa dùng |
| `new Exception("message", null)` | `null` | Không |
| `new Exception((Throwable) null)` | `null` | Không |
| `new Exception("message", original)` | `original` | Không |

Vì cả `String` và `Throwable` đều có overload một tham số, câu lệnh `new Exception(null)` có thể **mơ hồ lúc biên dịch**. Khi thật sự cần truyền `null`, dùng ép kiểu tường minh `(String) null` hoặc `(Throwable) null`, hoặc constructor hai tham số như `new Exception("message", null)` để nói rõ ý định.

### Chương trình Java 17+: `null` không đồng nghĩa “chưa khởi tạo cause”

Lưu thành `NullCauseConstructorDemo.java`:

```java
public class NullCauseConstructorDemo {
    static class SampleException extends Exception {
        SampleException(String message) {
            super(message);
        }

        SampleException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static void main(String[] args) {
        SampleException messageOnly = new SampleException("one");
        messageOnly.initCause(new IllegalStateException("original"));
        System.out.println("firstLinked="
                + (messageOnly.getCause() instanceof IllegalStateException));

        SampleException explicitNull =
                new SampleException("two", null);
        System.out.println("nullCause=" + explicitNull.getCause());

        try {
            explicitNull.initCause(new IllegalStateException("late"));
        } catch (IllegalStateException ex) {
            System.out.println("initAgain="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

```bash
javac -encoding UTF-8 NullCauseConstructorDemo.java
java NullCauseConstructorDemo
```

Kết quả:

```text
firstLinked=true
nullCause=null
initAgain=IllegalStateException
```

Đừng xây ứng dụng dựa trên việc tự do gắn cause sau nhiều tầng. Mẫu dễ hiểu nhất là tạo wrapper với đúng message và cause ngay lúc bắt lỗi:

```java
throw new DataLoadException("Cannot load profile", original);
```

Đây là đoạn minh họa khi `original` là một `Throwable` và `DataLoadException` có constructor `(String, Throwable)`.

## 7. Checked exception qua nhiều tầng: đặt ngữ cảnh vào wrapper

Giả sử tầng repository gặp `IOException`, tầng service muốn cung cấp một ngoại lệ nghiệp vụ kiểm tra được (*checked*). Một lớp custom có constructor `(String, Throwable)` là cách trình bày ý nghĩa lỗi của tầng service mà không bắt bên gọi phụ thuộc vào ngoại lệ hạ tầng.

Lưu thành `CheckedTranslationDemo.java`:

```java
import java.io.IOException;

public class CheckedTranslationDemo {
    static class ProfileLoadException extends Exception {
        ProfileLoadException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String repository() throws IOException {
        throw new IOException("file read failed");
    }

    static String service() throws ProfileLoadException {
        try {
            return repository();
        } catch (IOException ex) {
            throw new ProfileLoadException(
                    "Could not load user profile", ex);
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println(service());
        } catch (ProfileLoadException ex) {
            System.out.println("type=" + ex.getClass().getSimpleName());
            System.out.println("message=" + ex.getMessage());
            System.out.println("causeType="
                    + ex.getCause().getClass().getSimpleName());
            System.out.println("causeMessage=" + ex.getCause().getMessage());
        }
        System.out.println("end");
    }
}
```

```bash
javac -encoding UTF-8 CheckedTranslationDemo.java
java CheckedTranslationDemo
```

Kết quả:

```text
type=ProfileLoadException
message=Could not load user profile
causeType=IOException
causeMessage=file read failed
end
```

Cơ chế:

1. `repository()` tạo/ném `IOException`.
2. `service()` bắt lỗi hạ tầng và **tạo đối tượng mới** `ProfileLoadException` với message nghiệp vụ.
3. Constructor `super(message, cause)` giữ `IOException` thành nguyên nhân của wrapper.
4. Vì `ProfileLoadException extends Exception`, `service()` khai báo `throws ProfileLoadException`. Tầng `main()` bắt loại đó.
5. `main()` có thể tiếp tục sau `catch` vì lỗi đã được xử lý ở ranh giới phù hợp.

**Không phải mọi tầng đều nên bọc ngoại lệ một lần nữa.** Nếu tầng trung gian chưa có ngữ cảnh mới, lan truyền nguyên ngoại lệ có thể tốt hơn tạo nhiều lớp wrapper giống nhau.

## 8. Custom unchecked exception cũng cần constructor nhận cause

Ngoại lệ unchecked không yêu cầu `throws` ở bên gọi, nhưng việc giữ cause vẫn rất quan trọng. Một lỗi về cấu hình hoặc trạng thái dịch vụ có thể cần được biểu diễn bởi kiểu domain-specific unchecked exception thay vì lộ `IOException` tới tầng business.

Lưu thành `UncheckedTranslationDemo.java`:

```java
import java.io.IOException;

public class UncheckedTranslationDemo {
    static class ConfigurationFailure extends RuntimeException {
        ConfigurationFailure(String message) {
            super(message);
        }

        ConfigurationFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String loadConfig() throws IOException {
        throw new IOException("permission denied");
    }

    static String initializeService() {
        try {
            return loadConfig();
        } catch (IOException ex) {
            throw new ConfigurationFailure(
                    "Service configuration unavailable", ex);
        }
    }

    public static void main(String[] args) {
        try {
            initializeService();
        } catch (ConfigurationFailure ex) {
            System.out.println("unchecked="
                    + (ex instanceof RuntimeException));
            System.out.println("message=" + ex.getMessage());
            System.out.println("causeIsIo="
                    + (ex.getCause() instanceof IOException));
        }
    }
}
```

```bash
javac -encoding UTF-8 UncheckedTranslationDemo.java
java UncheckedTranslationDemo
```

Kết quả:

```text
unchecked=true
message=Service configuration unavailable
causeIsIo=true
```

`initializeService()` không cần `throws ConfigurationFailure` vì đó là unchecked exception. Điều này **không đồng nghĩa** ngoại lệ không thể khiến chương trình kết thúc đột ngột. Nếu không có `catch` phù hợp, nó vẫn tiếp tục lan truyền theo cơ chế ngoại lệ Java.

Chỉ nên chọn unchecked nếu hợp đồng module thực sự muốn biểu thị lỗi không bắt buộc xử lý tại mọi nơi; không tự động bọc mọi checked exception thành unchecked để tránh quy tắc của trình biên dịch.

## 9. `cause` là tham chiếu tới đối tượng gốc, không phải một bản sao

Khi gọi:

```java
IOException original = new IOException("disk offline");
DataLoadException wrapper =
        new DataLoadException("Cannot load profile", original);
```

đối tượng `wrapper.getCause()` là **chính `original`**. Java không copy thông điệp, stack trace và suppressed exceptions thành một bản `IOException` khác khi dùng constructor `(String, Throwable)`.

Hệ quả:

- `wrapper.getMessage()` mô tả lỗi ở tầng wrapper; không phải tên lỗi gốc.
- `wrapper.getCause().getMessage()` mô tả lỗi gốc, nếu `getCause()` khác `null`.
- `wrapper.getStackTrace()` thường ghi nơi wrapper được tạo.
- `wrapper.getCause().getStackTrace()` thường ghi nơi đối tượng cause đã được tạo hoặc nơi trace của nó được cập nhật.
- Danh sách suppressed của cause **vẫn gắn với cause**, không tự được chuyển sang wrapper.

### Chương trình Java 17+: giữ cả suppressed khi bọc ngoại lệ

Lưu thành `SuppressedCauseDemo.java`:

```java
import java.io.IOException;

public class SuppressedCauseDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static class DataLoadException extends Exception {
        DataLoadException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void repository() throws IOException {
        try (Resource resource = new Resource()) {
            throw new IOException("read failed");
        }
    }

    static void service() throws DataLoadException {
        try {
            repository();
        } catch (IOException ex) {
            throw new DataLoadException("Data access failed", ex);
        }
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (DataLoadException ex) {
            Throwable cause = ex.getCause();

            System.out.println("wrapper=" + ex.getMessage());
            System.out.println("wrapperSuppressed="
                    + ex.getSuppressed().length);
            System.out.println("cause=" + cause.getMessage());
            System.out.println("causeSuppressed="
                    + cause.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 SuppressedCauseDemo.java
java SuppressedCauseDemo
```

Kết quả:

```text
wrapper=Data access failed
wrapperSuppressed=0
cause=read failed
causeSuppressed=close failed
```

Lỗi từ thân `try` là primary của `IOException`; lỗi `close()` được suppress vào chính đối tượng đó. Khi service tạo `DataLoadException(..., ex)`, wrapper **không tự sao chép** suppressed array của cause. Nhưng vì cause được giữ nguyên, vẫn truy được lỗi phụ từ `ex.getCause().getSuppressed()`.

Khi log, nên chuyển cả đối tượng `Throwable` cho logger để công cụ có thể in message, trace, cause và suppressed, thay vì chỉ ghi `getMessage()` rồi làm mất quan hệ này.

## 10. Tại sao không nên chỉ nhận `String message` rồi tự nối tên lỗi gốc?

Mẫu dễ gặp nhưng thiếu thông tin:

```java
catch (IOException ex) {
    throw new DataLoadException(
            "Unable to load: " + ex.getMessage());
}
```

Đây là đoạn **minh họa**, giả định `DataLoadException(String)` có sẵn. Người đọc thấy văn bản mô tả, nhưng `getCause()` là `null` và không còn liên kết lập trình được tới `ex`.

Cách nên dùng:

```java
catch (IOException ex) {
    throw new DataLoadException(
            "Unable to load customer profile", ex);
}
```

Ngoại lệ gốc vẫn tồn tại như cause; nếu thực sự muốn bổ sung message của `ex` vào phần mô tả cho con người thì có thể làm, nhưng cần cân nhắc lặp thông tin trong log và dữ liệu nhạy cảm.

Một nguyên tắc về message:

- **Mô tả ngữ cảnh ở tầng hiện tại**: thao tác nào thất bại và đối tượng miền nghiệp vụ nào bị ảnh hưởng.
- **Không lộ bí mật**: tránh mật khẩu, token, chuỗi kết nối, thông tin định danh nhạy cảm.
- **Không thay cause bằng message**: cause giữ loại, stack trace và thông tin nguyên nhân gốc.
- **Giữ message ổn định về ý nghĩa** cho việc đọc log, nhưng đừng yêu cầu code nghiệp vụ parse message text để xác định mã lỗi.

Nếu bên gọi phải đưa ra quyết định dựa trên loại lỗi, cung cấp kiểu ngoại lệ, enum mã lỗi hoặc thuộc tính có kiểu thích hợp thay vì cố phân tích một chuỗi `getMessage()`.

## 11. `getMessage()` khác `toString()` và `printStackTrace()`

Đừng nhầm các API chẩn đoán:

| API | Thông tin chính |
| --- | --- |
| `getMessage()` | Chỉ detail message của đối tượng hiện tại, có thể `null` |
| `toString()` | Thông thường tên lớp lỗi và detail message nếu có |
| `getCause()` | Đối tượng cause hoặc `null` |
| `printStackTrace()` | Biểu diễn chẩn đoán gồm đối tượng lỗi, các frame, chuỗi cause và suppressed khi có |
| `getSuppressed()` | Mảng các ngoại lệ phụ của chính đối tượng đó |

Chương trình nhỏ để so sánh, lưu thành `MessageDisplayDemo.java`:

```java
import java.io.IOException;

public class MessageDisplayDemo {
    static class ImportFailure extends Exception {
        ImportFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static void main(String[] args) {
        IOException original = new IOException("invalid bytes");
        ImportFailure wrapper =
                new ImportFailure("Cannot import document", original);

        System.out.println("message=" + wrapper.getMessage());
        System.out.println("simpleType="
                + wrapper.getClass().getSimpleName());
        System.out.println("causeMessage="
                + wrapper.getCause().getMessage());
        System.out.println("causeType="
                + wrapper.getCause().getClass().getSimpleName());
    }
}
```

```bash
javac -encoding UTF-8 MessageDisplayDemo.java
java MessageDisplayDemo
```

Kết quả:

```text
message=Cannot import document
simpleType=ImportFailure
causeMessage=invalid bytes
causeType=IOException
```

Ví dụ tránh so sánh nguyên văn `printStackTrace()` vì số dòng nguồn, tên file và số frame phụ thuộc nơi biên dịch/chạy. Thay vào đó, kiểm tra những thuộc tính xác định mà API cam kết. Nếu cần in trace thực tế, dùng `wrapper.printStackTrace()` ở nơi phù hợp và nhớ rằng overload không tham số ghi vào `System.err`.

## 12. Constructor có trường dữ liệu nghiệp vụ: lưu thêm thông tin mà không bỏ cause

Có khi message không đủ để code xử lý: ví dụ ngoại lệ cần mang `resourceName` hoặc `errorCode`. Có thể thêm trường bất biến, nhưng constructor vẫn nên truyền cause cho lớp cha.

```java
public final class RecordValidationException extends Exception {
    private final String field;

    public RecordValidationException(
            String field, String message, Throwable cause) {
        super(message, cause);
        this.field = field;
    }

    public String getField() {
        return field;
    }
}
```

Đây là **lớp hợp lệ** nếu lưu trong `RecordValidationException.java`; không có `main()`. Bên gọi có thể truy:

```java
RecordValidationException failure =
        new RecordValidationException(
                "email", "Email validation failed", original);

System.out.println(failure.getField());
System.out.println(failure.getCause() == original);
```

Đây là đoạn sử dụng minh họa khi `original` đã được định nghĩa là một `Throwable` trong scope. Cả thuộc tính có kiểu và cause được giữ riêng.

Nếu lỗi đơn giản chỉ vì đầu vào không hợp lệ, có thể không có cause nào; không cần tạo một `Throwable` giả để điền vào. Khi đó truyền `null` vào overload `(String, Throwable)` là hợp lệ, hoặc cung cấp overload `(String)` nếu hợp đồng cần.

**Thông điệp không nên là nguồn dữ liệu duy nhất** cho những quyết định như retry, HTTP status, field bị lỗi hoặc loại khắc phục. Những giá trị dùng trong logic nên được cung cấp qua kiểu dữ liệu ổn định.

## 13. Sai lầm trong constructor chaining

Có thể dùng `this(...)` để giảm trùng mã, nhưng phải hiểu việc nó chọn constructor nào.

Ví dụ:

```java
class ValidationFailure extends Exception {
    ValidationFailure(String message) {
        this(message, null);
    }

    ValidationFailure(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Đây là **mã hợp lệ**. Tuy nhiên, nó **không hoàn toàn giống** constructor `ValidationFailure(String message) { super(message); }` về trạng thái cause:

- Với `this(message, null)`, constructor hai tham số chạy `super(message, null)` và **đã khởi tạo cause thành `null`**.
- Với `super(message)`, cause chưa được khởi tạo và `initCause(...)` có thể được gọi một lần sau đó.

Nếu lớp được thiết kế để mọi cause phải được quyết định ngay khi tạo đối tượng, gọi `this(message, null)` có thể là lựa chọn có chủ đích. Nếu muốn giữ đúng ngữ nghĩa constructor `Exception(String)` tiêu chuẩn, viết `super(message)` trực tiếp.

**Tránh gọi `super(...)` và `this(...)` trong cùng một constructor**: mỗi constructor chỉ được chọn một constructor invocation tường minh tương ứng theo cú pháp. Không thể gọi cả hai như các hàm thông thường.

### Ví dụ lỗi do gọi `initCause` sau khi đã dùng constructor có cause

```java
class WrongFailure extends Exception {
    WrongFailure(String message, Throwable cause) {
        super(message, cause);
        initCause(cause); // Chạy tới đây sẽ ném IllegalStateException.
    }
}
```

Đây là **mã biên dịch được nhưng constructor thất bại lúc chạy**. Lý do: `super(message, cause)` đã khởi tạo cause; `initCause` không cho khởi tạo lần thứ hai. Sửa bằng cách **xóa `initCause(cause)`**.

Nếu viết `super(message)` rồi `initCause(cause)`, mã có thể hoạt động lần đầu nhưng dài và dễ bị thay đổi sai; khi đã có overload hai tham số, không có lợi thế rõ ràng so với `super(message, cause)`.

## 14. Một số giới hạn cần kiểm tra khi triển khai

### 14.1. Cause không thể là chính đối tượng wrapper

Một ngoại lệ không thể dùng chính nó làm cause qua `initCause(this)`. Điều này bị từ chối bằng `IllegalArgumentException`. Khi viết constructor nhận `Throwable cause`, hãy truyền **đối tượng ngoại lệ gốc khác với wrapper đang được tạo**, không cố tự liên kết đối tượng với chính nó để giữ stack trace.

Trong thực tế, một tham số `cause` bình thường truyền từ `catch (Exception ex)` vào constructor `new DomainException(..., ex)` là đối tượng khác, nên hợp lệ.

### 14.2. Cause có thể bằng `null`

`super(message, null)` hợp lệ: nghĩa là chưa có nguyên nhân được biết hoặc không có một ngoại lệ cụ thể gây ra lỗi. Nhưng nó vẫn khởi tạo cause **một lần**. Không dùng `getCause() == null` để kết luận `initCause(...)` có thể gọi lại.

### 14.3. Không tạo vòng cause hoặc chain vô nghĩa

Không nên dùng cause để lưu một ngoại lệ hoàn toàn không liên quan, hoặc tạo chu trình tham chiếu qua nhiều đối tượng. Điều đó có thể làm stack trace khó đọc và phá ý nghĩa “gây ra lỗi này”. Lỗi phụ xảy ra khi cleanup nên được biểu diễn bằng suppressed exceptions trong các ngữ cảnh thích hợp, không ép tất cả thành cause.

### 14.4. Không tự động vô hiệu hóa stack trace

Các lớp `Exception` và `RuntimeException` có constructor protected mở rộng hỗ trợ `enableSuppression` và `writableStackTrace`. Đây là công cụ nâng cao. Tắt stack trace hoặc suppression có thể giảm lượng thông tin chẩn đoán quan trọng; không nên xem đó là mặc định cho mọi custom exception.

### 14.5. `serialVersionUID` là mối quan tâm riêng

Các ngoại lệ Java kế thừa `Throwable` và có khả năng tham gia Java serialization. Nếu một custom exception là phần của hợp đồng serialization lâu dài, cân nhắc `serialVersionUID` và khả năng tương thích phiên bản. Nhưng đây là vấn đề thiết kế serialization, **không phải điều kiện để constructor `(String, Throwable)` hoạt động**.

## 15. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Sửa như thế nào |
| --- | --- | --- |
| Chỉ viết `MyException(String message)` trong khi phải chuyển nguyên nhân gốc. | Mất cause khi chuyển đổi lỗi. | Thêm `MyException(String, Throwable)` và gọi `super(message, cause)`. |
| Bọc lỗi bằng `new MyException(ex.getMessage())`. | Chỉ sao chép text, mất liên kết tới `ex`. | Truyền `ex` làm cause. |
| Viết `super(cause)` dù cần message theo ngữ cảnh tầng hiện tại. | Message chỉ là `cause.toString()`. | Dùng `super("Context...", cause)`. |
| Gọi `initCause()` sau `super(message, cause)`. | `IllegalStateException` lúc chạy. | Không gọi `initCause` nữa. |
| Xem `getCause() == null` như “chưa từng khởi tạo cause”. | Có thể gặp lỗi khi khởi tạo lần hai. | Quyết định cause ngay ở constructor. |
| Dùng `new MyException(null)` khi có overload `String` và `Throwable`. | Mơ hồ lúc biên dịch. | Dùng ép kiểu hoặc overload hai tham số rõ ràng. |
| Ném `new MyException("failure", null)` cho mọi trường hợp kể cả khi có ngoại lệ gốc. | Cause thật bị bỏ qua. | Chỉ dùng `null` khi không có cause thích hợp. |
| Bọc nhiều tầng mà không thêm thông tin mới. | Chain dài, log khó đọc. | Chỉ chuyển loại khi vượt qua ranh giới hợp đồng có ý nghĩa. |
| Đưa token, mật khẩu hoặc thông tin nhạy cảm vào message. | Rủi ro rò rỉ qua log/trace. | Message có ngữ cảnh nhưng không chứa bí mật. |
| Chỉ kiểm tra `getMessage()`, không đọc cause và suppressed. | Bỏ qua nguyên nhân kỹ thuật và lỗi đóng. | Log đối tượng `Throwable` và truy chain khi cần. |
| Dùng checked exception nhưng quên `throws` ở tầng gọi. | Không biên dịch. | Khai báo `throws` phù hợp hoặc xử lý tại `catch`. |
| Dùng unchecked cho mọi lỗi chỉ để bớt khai báo. | Hợp đồng lỗi khó rõ ràng. | Chọn checked/unchecked dựa vào cách bên gọi xử lý. |
| Định nghĩa constructor tên khác tên lớp hoặc thêm kiểu trả về. | Không phải constructor hợp lệ. | Constructor trùng tên lớp, không có kiểu trả về. |

## 16. Quy trình thiết kế một custom exception có message và cause

Khi xây một lớp mới, có thể làm theo các bước sau:

1. **Xác định ý nghĩa lỗi:** lỗi cần đại diện cho sự kiện nào ở module? Đã có ngoại lệ chuẩn nào đủ phù hợp chưa?
2. **Chọn checked/unchecked:** bên gọi có được kỳ vọng phục hồi không, API cần yêu cầu xử lý lúc biên dịch hay không?
3. **Chọn các overload cần thiết:** tối thiểu `(String, Throwable)` nếu có chuyển đổi lỗi; thêm `(String)` nếu có những lỗi độc lập không có cause.
4. **Gọi constructor lớp cha đúng:** `super(message, cause)`, `super(message)` hoặc `super(cause)` tương ứng.
5. **Giữ ngữ cảnh:** tạo message diễn đạt **thao tác ở tầng hiện tại** thay vì chỉ lặp lại message của nguyên nhân.
6. **Giữ object cause:** truyền ngoại lệ bắt được, không tự tạo bản sao hoặc chuỗi thay thế.
7. **Kiểm tra `null`:** có cho phép cause thiếu không? Nếu có, chỉ gắn `null` khi thực sự không có lỗi gốc.
8. **Kiểm tra contract:** checked exception có được `throws` hoặc `catch` đúng không? Trong override/interface có làm rộng thêm checked exceptions không?
9. **Kiểm tra chẩn đoán:** khi in log còn thấy cause chain và suppressed exceptions của lỗi gốc không?
10. **Đánh giá phạm vi thông tin:** message có lộ dữ liệu nhạy cảm hoặc khó dùng cho vận hành không?

Một thiết kế nhỏ, minh bạch thường tốt hơn nhiều constructor với hành vi tùy biến không nhất quán. Chỉ thêm trường nghiệp vụ, mã lỗi hoặc logic xử lý khi có nhu cầu thực sự.

## 17. Tự kiểm tra

**Câu 1.** Vì sao `super(message, cause)` tốt hơn `super(message + cause.getMessage())` khi chuyển đổi ngoại lệ?  
Vì cách đầu **giữ đối tượng cause** cùng stack trace và thông tin phụ; cách sau chỉ ghép chuỗi, có thể mất liên kết và còn có nguy cơ NPE khi cause bằng `null`.

**Câu 2.** Constructor `MyException(Throwable cause) { super(cause); }` tạo message gì?  
Thông thường `cause.toString()`, hoặc `null` nếu cause là `null`, theo hợp đồng của lớp cha.

**Câu 3.** `new Exception("failed", null)` có hợp lệ không?  
**Có.** Cause bằng `null` được phép và được xem là đã khởi tạo.

**Câu 4.** Sau `super(message, null)`, có thể gọi `initCause(realCause)` không?  
**Không.** Cause đã được khởi tạo bằng constructor hai tham số.

**Câu 5.** Hai constructor `MyException(String)` và `MyException(Throwable)` tồn tại; `new MyException(null)` có luôn biên dịch không?  
**Không.** Lời gọi có thể mơ hồ vì `null` phù hợp cả `String` và `Throwable` mà hai kiểu không có quan hệ kế thừa trực tiếp.

**Câu 6.** Custom exception kế thừa `RuntimeException` có được dùng constructor nhận cause không?  
**Có.** Khác biệt checked/unchecked không làm mất cơ chế chaining.

**Câu 7.** Khi wrapper đã có cause, suppressed exceptions của cause có tự được copy lên wrapper không?  
**Không.** Chúng vẫn ở đối tượng cause; có thể đọc qua `wrapper.getCause().getSuppressed()` khi cause không `null`.

**Câu 8.** Tại sao không nên bắt mọi ngoại lệ rồi tạo `new MyException("error")` ở từng tầng?  
Vì có thể mất cause, lặp wrapper vô nghĩa, che giấu ranh giới trách nhiệm và làm chẩn đoán khó hơn.

**Câu 9.** Có bắt buộc custom exception phải cung cấp đủ bốn overload không?  
**Không.** Chỉ cần những overload được hợp đồng sử dụng; `(String, Throwable)` đặc biệt hữu ích khi chuyển đổi lỗi.

**Câu 10.** Ngoại lệ có cause đầy đủ đã là đủ để bảo đảm log an toàn và dễ đọc chưa?  
**Chưa.** Vẫn cần message có ngữ cảnh, kiểm soát thông tin nhạy cảm và trình bày đầy đủ chain ở tầng logging phù hợp.

## Tài liệu tham khảo chuẩn

- [Java SE 21 API — `Throwable`: message, cause, `initCause()` và stack trace](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Throwable.html).
- [Java SE 21 API — `Exception`: các constructor, `Exception(Throwable)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Exception.html).
- [Java SE 21 API — `RuntimeException`: các constructor, checked/unchecked](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/RuntimeException.html).
- [JLS Java SE 21 — §11.1.1: checked và unchecked exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.1.1).
- [JLS Java SE 21 — §11.2: Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2).
- [JLS Java SE 21 — §8.8.7: Constructor Body](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.8.7).

**Ghi nhớ:** Một constructor custom exception tốt không chỉ tạo một dòng message: nó bảo toàn nguyên nhân bằng `super(message, cause)`, giữ thông tin lỗi gốc để truy vấn và giúp mỗi tầng diễn đạt đúng ngữ cảnh của mình. Chọn overload theo hợp đồng API, xử lý `null` rõ ràng và tránh tự làm mất cause bằng cách chỉ sao chép text.
