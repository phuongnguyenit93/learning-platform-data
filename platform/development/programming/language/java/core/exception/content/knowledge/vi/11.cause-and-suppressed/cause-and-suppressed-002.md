# Giữ nguyên nguyên nhân khi bọc ngoại lệ trong Java

## 1. Mục tiêu học tập

Khi một phương thức bắt được ngoại lệ ở tầng thấp rồi cần thông báo thất bại bằng một loại ngoại lệ phù hợp hơn với tầng trên, nó có thể **bọc ngoại lệ** (*exception wrapping*). Cách bọc đúng phải giữ được **nguyên nhân gốc** để lập trình viên không mất thông tin quan trọng về vị trí và bản chất sự cố.

Ví dụ: thư viện đọc tệp ném `IOException`, lớp nhập dữ liệu muốn báo `ImportException`. Nếu chỉ tạo `new ImportException("Import failed")`, stack trace của lỗi đọc có thể mất khỏi thông tin ngoại lệ được truyền lên. Nếu tạo `new ImportException("Import failed", original)`, lỗi mới thêm ngữ cảnh nghiệp vụ nhưng vẫn truy vết về `IOException` gốc qua `getCause()`.

Bài học giúp bạn:

- Phân biệt **ngoại lệ bao ngoài** (*wrapper*) với **nguyên nhân** (*cause*) và **ngoại lệ suppressed**.
- Sử dụng constructor `Throwable(String, Throwable)` hoặc constructor tương ứng của `Exception`/`RuntimeException` và các lớp con.
- Thiết kế custom exception hỗ trợ nguyên nhân, giữ nguyên đối tượng `Throwable` ở chuỗi lỗi.
- Dùng `initCause(Throwable)` trong các trường hợp cần tương thích API cũ, đồng thời hiểu giới hạn của nó.
- Tìm nguyên nhân gốc qua nhiều tầng mà không đánh mất thông tin các tầng trung gian.
- Quyết định khi nào nên **ném lại nguyên ngoại lệ**, khi nào nên **bọc**, và khi nào nên **xử lý tại chỗ**.
- Tránh anti-pattern chỉ sao chép `getMessage()`, log lặp, che mất cause hoặc chuyển sai loại checked/unchecked.
- Đọc `printStackTrace()` và phân biệt `Caused by:` với `Suppressed:` trong chẩn đoán.

Các chương trình chạy độc lập dùng Java 17 trở lên, có lệnh `javac`/`java` và `stdout` dự kiến.

## 2. Vì sao mất `cause` là một lỗi thiết kế?

Giả sử lớp dưới có phương thức:

```java
static int parse(String text) {
    return Integer.parseInt(text);
}
```

Nếu `text` không chứa số nguyên hợp lệ, `Integer.parseInt` ném `NumberFormatException`. Một tầng ứng dụng có thể bắt lỗi và chuyển thành ngoại lệ có ngữ nghĩa nghiệp vụ:

```java
try {
    return parse(text);
} catch (NumberFormatException original) {
    throw new IllegalStateException("Invalid configuration");
}
```

Hai đoạn trên là **mảnh minh họa** trong một lớp/phương thức có biến `text` thích hợp. Cách viết cuối có vấn đề: ngoại lệ bao ngoài vẫn có stack trace của nơi **bọc lỗi**, nhưng mối liên hệ chính thức đến đối tượng `NumberFormatException` ban đầu không được lưu. Người đọc chỉ thấy “Invalid configuration”, không còn trực tiếp xem được lỗi parse, lời gọi gây lỗi và những thông tin gắn với đối tượng cũ qua chuỗi `cause`.

Cách đúng:

```java
try {
    return parse(text);
} catch (NumberFormatException original) {
    throw new IllegalStateException(
            "Invalid configuration: expected an integer", original);
}
```

Ở đây:

- `original` là chính đối tượng `NumberFormatException` đã được bắt.
- `IllegalStateException` mới đại diện cho thất bại ở tầng cấu hình.
- Constructor có đối số thứ hai lưu `original` làm **cause**.
- `getCause()` trên wrapper trả tham chiếu tới `original`, không phải một ngoại lệ mới tái tạo từ message.
- Khi xem stack trace đầy đủ, Java có thể biểu diễn cả hai tầng và nơi lỗi gốc phát sinh.

**Nguyên tắc:** bọc lỗi phải thêm thông tin hữu ích **mà vẫn giữ lỗi gốc**, không được chỉ thay tên lỗi rồi đánh mất đường truy vết.

## 3. Mô hình `Throwable`: message, cause, stack trace và suppressed

Một đối tượng `Throwable` có nhiều thông tin khác nhau:

| Thành phần | API chính | Ý nghĩa |
| --- | --- | --- |
| Loại exception | `getClass()` | Tầng/nguyên nhân thất bại được biểu diễn bằng kiểu Java |
| Thông điệp | `getMessage()` | Mô tả ngắn, có thể là `null` |
| Chuỗi nguyên nhân | `getCause()` | Ngoại lệ khiến lỗi hiện tại xuất hiện hoặc được bọc lại |
| Vị trí thực thi | `getStackTrace()`, `printStackTrace()` | Các frame liên quan khi stack trace được ghi nhận |
| Lỗi phụ | `getSuppressed()` | Những lỗi bổ sung được gắn vào cùng Throwable, thường khi cleanup |

Sơ đồ quan hệ:

```text
ImportException: "Cannot import orders"       <-- wrapper
    |
    +-- getCause()
            |
            v
      IOException: "Cannot read orders.csv"    <-- cause
            |
            +-- getCause() == null

Mỗi Throwable trong sơ đồ có thể có stack trace
và danh sách getSuppressed() riêng.
```

Đừng coi `getCause()` và `getSuppressed()` là hai tên của cùng một cơ chế. `cause` giải thích quan hệ **gây ra/bị bọc bởi**; suppressed giữ những lỗi **bổ sung** (ví dụ đóng resource thất bại sau khi đọc tệp lỗi).

Một wrapper thường có stack trace được tạo tại **vị trí bọc**; cause giữ stack trace ở **vị trí gốc**. Giữ cả hai giúp biết không chỉ *lỗi nào xảy ra* mà còn *tầng nào đã chuyển đổi lỗi*.

## 4. Constructor nhận nguyên nhân: cách thông dụng nhất

Nhiều lớp exception Java có constructor:

```java
new RuntimeException("context", cause);
new IllegalStateException("context", cause);
new java.io.IOException("context", cause);
```

Đây là các biểu thức minh họa, cần biến `cause` kiểu `Throwable` được khai báo. Các lớp custom nên cung cấp constructor tương tự khi có nhu cầu bọc.

Ví dụ định nghĩa:

```java
class ImportException extends Exception {
    ImportException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Đây là lớp Java hợp lệ. Gọi `super(message, cause)` để lớp cha `Exception` lưu nguyên nhân trong cơ chế của `Throwable`. Không cần tự tạo một field `Throwable rootCause` nếu chỉ muốn dùng chức năng tiêu chuẩn.

### Vì sao tham số nguyên nhân dùng `Throwable`?

`Throwable` là kiểu cha của `Exception` và `Error`. Constructor nhận `Throwable` cho phép bảo toàn chính xác đối tượng lỗi nguồn mà không buộc nó phải cùng phân cấp với wrapper.

Tuy vậy, khả năng **truyền được một `Error`** không có nghĩa ứng dụng nên bắt mọi `Error` rồi chuyển thành ngoại lệ có thể phục hồi. Nhiều `Error` biểu thị sự cố nghiêm trọng của JVM hoặc môi trường chạy; hãy giữ phạm vi bắt và bọc phù hợp với hợp đồng.

### Dùng constructor có cause, không dựng lại ngoại lệ từ chuỗi

Nếu đã có `IOException original`, tránh:

```java
throw new IOException(original.getMessage());
```

Mảnh mã này có thể tạo một `IOException` mới, nhưng không lưu `original` làm cause. Thông điệp có thể giống nhau mà quan hệ nguyên nhân vẫn bị mất.

Nên viết:

```java
throw new IOException("Unable to read configuration", original);
```

Trong hai mảnh minh họa, `original` giả định đã được bắt hoặc khai báo. Dạng thứ hai giữ nguyên đối tượng lỗi gốc. Việc thêm ngữ cảnh vẫn nên ngắn gọn và mô tả được **thao tác nào đã thất bại**.

## 5. Ví dụ hoàn chỉnh: bọc `NumberFormatException` thành lỗi cấu hình

Tạo file **`PreservedCauseDemo.java`**:

```java
public class PreservedCauseDemo {
    static class ConfigurationException extends Exception {
        ConfigurationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static int readPort(String text) throws ConfigurationException {
        try {
            return Integer.parseInt(text);
        } catch (NumberFormatException original) {
            throw new ConfigurationException(
                    "Port must be an integer", original);
        }
    }

    public static void main(String[] args) {
        try {
            readPort("abc");
        } catch (ConfigurationException failure) {
            System.out.println("outer="
                    + failure.getClass().getSimpleName());
            System.out.println("message=" + failure.getMessage());
            System.out.println("cause="
                    + failure.getCause().getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy Java 17+:

```bash
javac PreservedCauseDemo.java
java PreservedCauseDemo
```

`stdout` chính xác:

```text
outer=ConfigurationException
message=Port must be an integer
cause=NumberFormatException
```

Giải thích:

1. `Integer.parseInt("abc")` ném `NumberFormatException`.
2. `readPort` bắt đúng ngoại lệ được ném trong phần thân.
3. `new ConfigurationException(..., original)` tạo đối tượng lỗi mới với ngữ cảnh “Port must be an integer”.
4. `main` nhận `ConfigurationException`, có thể xử lý lỗi cấu hình theo hợp đồng ứng dụng.
5. `failure.getCause()` vẫn là `NumberFormatException` gốc; thông điệp và stack trace của lỗi parse không mất khỏi chuỗi nguyên nhân.

Không cần tự gọi `fillInStackTrace()` hay tạo một `NumberFormatException` mới để “phục dựng” cause. Việc giữ **tham chiếu đến lỗi gốc** mới bảo toàn đầy đủ những gì đối tượng ấy đã ghi nhận.

## 6. Chuỗi nguyên nhân qua nhiều tầng

Trong hệ thống phân lớp, lỗi có thể được bọc nhiều lần:

```text
IOException                 lỗi ở API đọc dữ liệu
     |
     | bọc thành
     v
StorageException             lỗi tầng lưu trữ
     |
     | bọc thành
     v
ImportException              lỗi tầng nghiệp vụ
```

Khi đọc theo `getCause()` từ ngoại lệ ngoài cùng:

```text
ImportException
  -> StorageException
      -> IOException
          -> null
```

Đây là chuỗi **cause**, không phải danh sách suppressed. Mỗi tầng nên cung cấp ngữ cảnh có ích chứ không chỉ lặp lại “failed” một cách vô nghĩa.

### Ví dụ chạy được: nguyên nhân qua ba tầng

Tạo file **`CauseChainDemo.java`**:

```java
import java.io.IOException;

public class CauseChainDemo {
    static class StorageException extends Exception {
        StorageException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static class ImportException extends Exception {
        ImportException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String readSource() throws IOException {
        throw new IOException("source unavailable");
    }

    static String load() throws StorageException {
        try {
            return readSource();
        } catch (IOException original) {
            throw new StorageException("cannot load source", original);
        }
    }

    static void importData() throws ImportException {
        try {
            load();
        } catch (StorageException original) {
            throw new ImportException("cannot import records", original);
        }
    }

    public static void main(String[] args) {
        try {
            importData();
        } catch (ImportException failure) {
            Throwable current = failure;
            while (current != null) {
                System.out.println(
                        current.getClass().getSimpleName()
                        + ": " + current.getMessage());
                current = current.getCause();
            }
        }
    }
}
```

```bash
javac CauseChainDemo.java
java CauseChainDemo
```

`stdout`:

```text
ImportException: cannot import records
StorageException: cannot load source
IOException: source unavailable
```

Chuỗi được xây như sau:

- `readSource()` tạo lỗi gốc `IOException`.
- `load()` nhận lỗi đó và bọc trong `StorageException`.
- `importData()` bọc `StorageException` trong `ImportException`.
- `main` lần theo từng liên kết cause, không cần biết chi tiết lỗi I/O ở thời điểm viết mã nghiệp vụ.

Với một throwable đến từ **nguồn bất kỳ** hoặc thư viện tùy biến, code duyệt cause theo ý tưởng nên có cơ chế nhận biết vòng tham chiếu để tránh lặp vô hạn nếu một chuỗi lỗi bị tạo bất thường. Đối với chuỗi tuyến tính do ba lớp của ví dụ tạo, vòng lặp `while` kết thúc khi `getCause() == null`.

### Không tự bọc mọi tầng nếu không thêm thông tin

Nếu `load()` và `importData()` chỉ cùng truyền lỗi I/O mà không bổ sung ý nghĩa gì, việc bọc ở cả hai tầng có thể làm log phức tạp, tạo stack trace dài và che hợp đồng API. Bọc khi có **ranh giới trừu tượng** hoặc nhu cầu bổ sung ngữ cảnh có giá trị.

## 7. `initCause(Throwable)`: khi không có constructor phù hợp

Một số lớp exception cũ không có constructor nhận cause. Khi đó, `Throwable.initCause(cause)` có thể được dùng để liên kết nguyên nhân **sau khi tạo đối tượng**, miễn là nguyên nhân chưa được thiết lập.

Ví dụ:

```java
LegacyException wrapper = new LegacyException("cannot process");
wrapper.initCause(original);
throw wrapper;
```

Đây là mảnh minh họa, giả định `LegacyException` đã tồn tại và `original` là `Throwable`. Tốt nhất vẫn dùng constructor nhận cause nếu API cung cấp.

### Giới hạn của `initCause`

- Chỉ gọi được **một lần** khi trạng thái cause vẫn chưa được khởi tạo.
- Nếu cause đã được khởi tạo (kể cả đã được constructor ghi nhận là `null`), gọi tiếp `initCause` sẽ ném `IllegalStateException`.
- Không được dùng **chính throwable nhận lời gọi** làm cause của nó; self-causation gây `IllegalArgumentException`.
- Truyền `null` có thể là giá trị cause khi trạng thái chưa được khởi tạo; đừng hiểu nó là cách “reset” quan hệ cause.
- `initCause` trả lại chính đối tượng `Throwable` nhận lời gọi, thuận tiện cho một số kiểu viết nhưng không buộc bạn phải dùng chaining.
- Với mã mới do bạn quản lý, constructor `(String, Throwable)` thường rõ ràng và an toàn hơn việc tạo đối tượng rồi nhớ liên kết sau.

### Ví dụ chạy được: thiết lập cause một lần

Tạo file **`InitCauseDemo.java`**:

```java
import java.io.IOException;

public class InitCauseDemo {
    static class LegacyException extends Exception {
        LegacyException(String message) {
            super(message);
        }
    }

    public static void main(String[] args) {
        IOException root = new IOException("disk failed");
        LegacyException wrapper =
                new LegacyException("load operation failed");

        wrapper.initCause(root);
        System.out.println("cause=" + wrapper.getCause().getMessage());

        try {
            wrapper.initCause(new IOException("second cause"));
        } catch (IllegalStateException failure) {
            System.out.println("second init rejected");
        }

        try {
            LegacyException self = new LegacyException("self");
            self.initCause(self);
        } catch (IllegalArgumentException failure) {
            System.out.println("self cause rejected");
        }
    }
}
```

```bash
javac InitCauseDemo.java
java InitCauseDemo
```

`stdout`:

```text
cause=disk failed
second init rejected
self cause rejected
```

`super(message)` trong custom exception giữ trạng thái cause chưa gán theo cơ chế `Throwable(String)`, nên lần `initCause(root)` đầu thành công. Lần tiếp theo bị từ chối. Với self-causation, Java cũng không chấp nhận xây cause trỏ trực tiếp về chính đối tượng.

### Không dùng `initCause` sau constructor đã nhận cause

Mã minh họa:

```java
IOException wrapped = new IOException("cannot read", original);
wrapped.initCause(anotherFailure); // Sai: cause đã được khởi tạo.
```

Đoạn này sẽ ném `IllegalStateException` tại runtime (giả định `original` và `anotherFailure` là các đối tượng `Throwable` hợp lệ), vì constructor đã thiết lập cause. Không dùng `initCause` như cơ chế “đổi nguyên nhân” sau này.

## 8. `cause` không phải `suppressed exception`

Hai loại liên kết có thể cùng tồn tại:

```text
ImportException: cannot import
    |
    +-- cause: IOException("read failed")
    |
    +-- suppressed: IOException("close failed")
```

Một số tình huống điển hình:

- **Bọc lỗi từ tầng dưới:** `new ImportException("...", original)` → dùng `cause`.
- **Đọc file lỗi, đóng file cũng lỗi trong TWR:** lỗi đọc là primary, lỗi đóng thường là `suppressed`.
- **Đóng file lỗi khi phần thân thành công:** lỗi đóng có thể là primary, không nhất thiết là suppressed.
- **Một lỗi nghiệp vụ vừa bị bọc vừa có cleanup failure:** wrapper có cause; suppressed có thể nằm trên chính cause hoặc wrapper tùy tầng/cơ chế quản lý resource thực tế. Không được suy luận rằng suppressed luôn nằm ở tầng ngoài cùng.

### Ví dụ chạy được: có cả nguyên nhân và lỗi phụ

Tạo file **`CauseAndSuppressedDemo.java`**:

```java
import java.io.IOException;

public class CauseAndSuppressedDemo {
    public static void main(String[] args) {
        IOException readFailure =
                new IOException("read failed");
        readFailure.addSuppressed(
                new IOException("reader close failed"));

        IllegalStateException wrapper =
                new IllegalStateException("cannot load report", readFailure);

        System.out.println("outer=" + wrapper.getMessage());
        System.out.println("cause=" + wrapper.getCause().getMessage());
        System.out.println("outer suppressed="
                + wrapper.getSuppressed().length);
        System.out.println("cause suppressed="
                + wrapper.getCause().getSuppressed().length);
        System.out.println("cleanup="
                + wrapper.getCause().getSuppressed()[0].getMessage());
    }
}
```

```bash
javac CauseAndSuppressedDemo.java
java CauseAndSuppressedDemo
```

`stdout`:

```text
outer=cannot load report
cause=read failed
outer suppressed=0
cause suppressed=1
cleanup=reader close failed
```

Giải thích: `readFailure` có một suppressed exception; nó được đưa nguyên vẹn vào cause của wrapper. Constructor nhận cause **không chuyển** danh sách suppressed từ cause sang wrapper. Vì thế `wrapper.getSuppressed().length == 0`, còn suppressed nằm ở `wrapper.getCause()`.

Trong log, `printStackTrace()` của wrapper thường trình bày chuỗi cause và những suppressed của từng throwable theo cấu trúc; không nên chỉ kiểm tra `wrapper.getSuppressed()` rồi kết luận không có lỗi cleanup ở các nguyên nhân sâu hơn.

## 9. `try-with-resources` kết hợp với bọc ngoại lệ

`try-with-resources` tự đóng tài nguyên `AutoCloseable` theo thứ tự ngược. Khi phần thân thất bại và `close()` cũng thất bại, Java giữ lỗi thân làm primary và gắn lỗi đóng làm suppressed. Nếu tầng ngoài bọc primary, **nên bảo toàn chính đối tượng primary cùng suppressed của nó**.

### Ví dụ chạy được: bảo toàn nguyên nhân lẫn suppressed qua wrapper

Tạo file **`WrappedResourceFailureDemo.java`**:

```java
import java.io.IOException;

public class WrappedResourceFailureDemo {
    static class BrokenResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static class OperationException extends Exception {
        OperationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void execute() throws OperationException {
        try (BrokenResource resource = new BrokenResource()) {
            throw new IOException("read failed");
        } catch (IOException original) {
            throw new OperationException("report generation failed", original);
        }
    }

    public static void main(String[] args) {
        try {
            execute();
        } catch (OperationException failure) {
            Throwable cause = failure.getCause();
            System.out.println("outer=" + failure.getMessage());
            System.out.println("cause=" + cause.getMessage());
            System.out.println("suppressed="
                    + cause.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac WrappedResourceFailureDemo.java
java WrappedResourceFailureDemo
```

`stdout`:

```text
outer=report generation failed
cause=read failed
suppressed=close failed
```

Từng bước:

1. `execute()` bắt đầu vùng TWR với `BrokenResource`.
2. Phần thân ném `IOException("read failed")`.
3. `close()` ném `IOException("close failed")`; JVM/TWR đính kèm lỗi này vào `getSuppressed()` của lỗi đọc.
4. Handler `catch (IOException original)` nhận đối tượng primary đã có suppressed.
5. `new OperationException(..., original)` bọc **đúng đối tượng** và giữ liên kết cause.
6. Caller có thể xem cause, rồi truy cập suppressed gắn với cause đó.

Nếu viết `new OperationException(original.getMessage(), null)` hoặc chỉ copy message, quan hệ cause và lỗi close sẽ bị bỏ mất khỏi ngoại lệ được truyền lên. Đây là ví dụ thực tế tại sao giữ nguyên đối tượng lỗi quan trọng hơn việc giữ một chuỗi văn bản.

## 10. Khi nào nên `throw original;` thay vì bọc?

**Không phải mọi ngoại lệ đều cần wrapper.** Nếu tầng gọi hiện tại không thay đổi ý nghĩa hoặc không cần chuyển hợp đồng, việc ném lại nguyên ngoại lệ thường đơn giản và trung thực hơn.

Ví dụ:

```java
static String readLine(java.io.BufferedReader reader)
        throws java.io.IOException {
    try {
        return reader.readLine();
    } catch (java.io.IOException original) {
        // Có thể ghi nhận một ngữ cảnh thực sự hữu ích ở đây.
        throw original;
    }
}
```

Đây là **mảnh phương thức**. `throw original;` truyền **cùng đối tượng IOException**, giữ message, cause, suppressed và stack trace mà đối tượng đã có. Tuy nhiên, đoạn `catch` chỉ để ném lại mà không thêm ý nghĩa thường là dư thừa; có thể để exception tự lan truyền.

Sử dụng wrapper khi:

- Đang đi qua ranh giới trừu tượng: I/O → lưu trữ → nghiệp vụ.
- Tầng trên không nên phụ thuộc một loại lỗi kỹ thuật chi tiết, nhưng vẫn cần truy vết.
- API cần bổ sung thông tin ngữ cảnh như tên thao tác, nguồn dữ liệu hoặc mã giao dịch (không lộ dữ liệu bí mật).
- Chính sách error handling của tầng trên có hợp đồng khác và có lý do rõ ràng.

Giữ nguyên lỗi hoặc bắt xử lý trực tiếp khi:

- API của phương thức đã khai báo loại checked exception phù hợp.
- Không có thêm ngữ nghĩa hữu ích để đưa vào wrapper.
- Bên gọi cần xử lý chính kiểu gốc.
- Đang bắt lỗi chỉ để log rồi ném lên mà không thêm gì: nên để logging ở một ranh giới thích hợp để tránh log lặp.

### Không bọc rồi nuốt ngoại lệ

Anti-pattern:

```java
try {
    save();
} catch (Exception original) {
    new IllegalStateException("Save failed", original);
    // Không throw: ngoại lệ mới bị bỏ đi.
}
```

Đây là **mảnh mã thiết kế sai có chủ ý**, cần định nghĩa `save()`. Chỉ tạo đối tượng wrapper mà không `throw` hay đưa vào cơ chế báo lỗi không làm caller biết thao tác thất bại. Chú ý dùng:

```java
throw new IllegalStateException("Save failed", original);
```

nếu chính sách thực sự là truyền lỗi lên bằng unchecked exception.

## 11. Checked và unchecked exception khi bọc

Bọc có thể đổi **loại ngoại lệ mà bên gọi phải xử lý**; đó là quyết định thiết kế API, không chỉ quyết định log.

Ví dụ một phương thức gọi API checked:

```java
static void load() throws java.io.IOException {
    throw new java.io.IOException("missing file");
}
```

Nếu method gọi bọc thành `IllegalStateException`:

```java
static void initialize() {
    try {
        load();
    } catch (java.io.IOException original) {
        throw new IllegalStateException(
                "Startup configuration could not be loaded", original);
    }
}
```

Đây là **các mảnh phương thức minh họa** cùng lớp; `initialize()` không cần khai báo `throws IOException`, vì nó xử lý IOException bằng việc ném unchecked wrapper. Nhưng điều này **không đồng nghĩa lỗi đã được phục hồi**. Bên gọi có thể vẫn thất bại ở runtime nếu không có handler thích hợp.

Nếu sử dụng checked wrapper:

```java
class StartupException extends Exception {
    StartupException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

thì method ném `StartupException` phải khai báo `throws StartupException` hoặc caller xử lý tương ứng. Cần phân biệt:

| Lựa chọn | Ảnh hưởng tới caller | Lưu nguyên nhân |
| --- | --- | --- |
| Ném lại checked exception gốc | Caller tiếp tục bắt/khai báo kiểu checked đó | Giữ đối tượng gốc |
| Bọc thành checked exception mới | Caller bắt/khai báo kiểu checked mới | Có nếu truyền `original` vào cause |
| Bọc thành unchecked exception | Không bắt buộc catch/throws ở compile time | Có nếu truyền `original` vào cause |
| Chỉ tạo wrapper rồi bỏ qua | Caller có thể tưởng thao tác thành công | Không có báo lỗi hợp lệ |
| Chỉ copy `original.getMessage()` | Có thể đổi hợp đồng, nhưng mất liên kết cause | Không |

Chọn checked/unchecked theo khả năng xử lý của caller, quy ước module và mức độ dự kiến của sự cố. Không dùng unchecked chỉ để “thoát khỏi trình biên dịch” mà không thiết kế phương án xử lý thất bại.

## 12. Lỗi cần tránh khi viết custom exception

### 12.1. Không quên truyền cause lên superclass

Sai lầm:

```java
class BadImportException extends Exception {
    BadImportException(String message, Throwable cause) {
        super(message); // Cause nhận vào nhưng bị bỏ qua.
    }
}
```

Đây là **ví dụ class hợp lệ về cú pháp nhưng sai chức năng** nếu API hứa giữ cause. Tham số `cause` bị bỏ qua; `getCause()` trên wrapper mặc định không trỏ về lỗi gốc.

Sửa:

```java
class GoodImportException extends Exception {
    GoodImportException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

### 12.2. Không lưu riêng cause mà bỏ API chuẩn

Ví dụ không nên chỉ có:

```java
class NonstandardException extends Exception {
    private final Throwable original;

    NonstandardException(Throwable original) {
        this.original = original;
    }
}
```

Đây là class minh họa có thể biên dịch, nhưng `getCause()` của `Throwable` không phản ánh field `original` vừa tạo. Những logger và công cụ chẩn đoán chuẩn sẽ không tự tìm được nguyên nhân qua API chuẩn. Nếu cần thông tin đặc thù, hãy vẫn gọi `super(message, cause)`, rồi thêm field nghiệp vụ **không thay thế** cause.

### 12.3. Không biến cause thành chuỗi

`cause.toString()` có thể cho thông điệp hữu ích, nhưng không thay thế liên kết Throwable. Nếu lưu chỉ chuỗi lỗi, bạn có thể đánh mất kiểu ngoại lệ, stack trace, suppressed exceptions và những trường bổ sung trên lớp con.

### 12.4. Không cập nhật cause hai lần

Nếu constructor đã dùng `super(message, cause)`, `initCause(newCause)` sau đó thường gây `IllegalStateException`. Một throwable không có hợp đồng thay đổi cause liên tục sau khi đã thiết lập.

### 12.5. Không dùng `catch (Throwable)` chỉ để bọc mọi thứ

`Throwable` bao gồm cả `Error`. Bắt và chuyển mọi `Error` thành một `RuntimeException` có vẻ “đồng nhất” nhưng có thể che đi lỗi nghiêm trọng liên quan JVM/tài nguyên mà chương trình không thể xử lý an toàn. Chỉ bắt những kiểu phù hợp với hợp đồng và chiến lược xử lý.

### 12.6. Không đánh mất thời điểm lỗi ban đầu vì tạo lại cause

Đoạn:

```java
catch (java.io.IOException original) {
    throw new IllegalStateException(
            "Cannot read", new java.io.IOException(original.getMessage()));
}
```

Đây là mảnh **sai về bảo toàn chẩn đoán**: “cause” mới là một đối tượng `IOException` khác, stack trace được ghi ở chỗ **tạo mới**, không phải nơi lỗi gốc phát sinh. Hãy truyền trực tiếp `original`.

## 13. In stack trace và đọc chuỗi nguyên nhân

Gọi:

```java
failure.printStackTrace();
```

thường in ngoại lệ vào `System.err`, bao gồm các liên kết `Caused by:` và `Suppressed:` có liên quan. Không nên kỳ vọng stack trace ở một dòng hoặc các số dòng source cố định: thông tin class, file, module, vị trí dòng và cách rút gọn frame có thể thay đổi giữa các bản build/JVM.

Ví dụ khái niệm:

```text
ImportException: cannot import
    at ImportService.importData(...)
Caused by: StorageException: cannot read
    at StorageService.load(...)
Caused by: IOException: access denied
    at FileService.open(...)
```

Đây là **sơ đồ rút gọn**, không phải `stdout` chính xác của chương trình; dấu `...` chỉ các frame mô tả.

Một số logger nhận cả đối tượng Throwable:

```java
logger.error("Import failed", failure);
```

Đây là **mảnh minh họa framework logging**, không phải cú pháp Java SE độc lập vì `logger` cần đến API của thư viện. Mục tiêu: truyền **đối tượng Throwable**, không chỉ `failure.getMessage()`. Kiểu API và cách format phụ thuộc thư viện logger cụ thể.

Đừng log cùng ngoại lệ ở mọi tầng rồi ném tiếp nếu không cần. Một thực hành phổ biến là tầng thấp chỉ thêm ngữ cảnh khi bọc; ranh giới xử lý cuối quyết định log và thông điệp cho người dùng.

### Thông tin bổ sung trong message

Một message wrapper tốt nên nêu thao tác và ngữ cảnh an toàn:

- `"Cannot parse import batch 42"`.
- `"Cannot load application configuration"`.
- `"Could not persist invoice"`.

Tránh message quá chung chung như `"error"`, nhưng cũng không đưa mật khẩu, token, nội dung dữ liệu nhạy cảm, chuỗi kết nối đầy đủ hoặc dữ liệu người dùng không cần thiết vào lỗi/log. Cause có thể tự chứa thông tin nhạy cảm nên chính sách ghi log và hiển thị stack trace vẫn quan trọng.

## 14. Ví dụ hoàn chỉnh: bỏ qua cause so với giữ cause

Tạo file **`CauseLossComparisonDemo.java`**:

```java
import java.io.IOException;

public class CauseLossComparisonDemo {
    static IllegalStateException withoutCause(IOException original) {
        return new IllegalStateException("service failed");
    }

    static IllegalStateException withCause(IOException original) {
        return new IllegalStateException("service failed", original);
    }

    public static void main(String[] args) {
        IOException root = new IOException("database unavailable");

        IllegalStateException lost = withoutCause(root);
        IllegalStateException kept = withCause(root);

        System.out.println("lost cause=" + (lost.getCause() == null));
        System.out.println("kept identity="
                + (kept.getCause() == root));
        System.out.println("root message="
                + kept.getCause().getMessage());
    }
}
```

```bash
javac CauseLossComparisonDemo.java
java CauseLossComparisonDemo
```

`stdout`:

```text
lost cause=true
kept identity=true
root message=database unavailable
```

Mấu chốt là `kept.getCause() == root` trả về `true`: constructor nhận cause giữ **chính đối tượng** `IOException` ban đầu, không tạo bản sao. Ngược lại, `withoutCause` không lưu liên kết; một công cụ chỉ có đối tượng `lost` không thể lần theo cause để tìm `root`.

## 15. Chẩn đoán cause một cách an toàn

Khi cần tìm nguyên nhân gốc ở một hệ thống có nhiều wrapper, bạn có thể đi theo `getCause()`. Tuy vậy, không nên viết một vòng lặp vô hạn nếu đối tượng Throwable từ thư viện tùy biến tạo cấu trúc bất thường.

Ví dụ dùng `IdentityHashMap` để dừng nếu gặp lại cùng một **đối tượng throwable**:

Tạo file **`SafeCauseTraversalDemo.java`**:

```java
import java.io.IOException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public class SafeCauseTraversalDemo {
    static void show(Throwable failure) {
        Set<Throwable> visited =
                Collections.newSetFromMap(new IdentityHashMap<>());

        Throwable current = failure;
        while (current != null && visited.add(current)) {
            System.out.println(
                    current.getClass().getSimpleName()
                    + ": " + current.getMessage());
            current = current.getCause();
        }
    }

    public static void main(String[] args) {
        IOException root = new IOException("read failed");
        IllegalStateException middle =
                new IllegalStateException("load failed", root);
        RuntimeException outer =
                new RuntimeException("request failed", middle);

        show(outer);
    }
}
```

```bash
javac SafeCauseTraversalDemo.java
java SafeCauseTraversalDemo
```

`stdout`:

```text
RuntimeException: request failed
IllegalStateException: load failed
IOException: read failed
```

`IdentityHashMap` sử dụng đồng nhất đối tượng làm cơ sở khóa, phù hợp khi muốn không truy lại cùng một `Throwable`. Vòng lặp chỉ đi theo `getCause()`; nó **không** tự duyệt `getSuppressed()` tại từng tầng. Nếu xây công cụ phân tích ngoại lệ hoàn chỉnh, cần duyệt cả cause và suppressed theo một cấu trúc đồ thị và theo dõi đối tượng đã gặp để tránh lặp.

Trong ứng dụng bình thường, các logger và `printStackTrace()` thường đã trình bày đủ thông tin; đừng tự viết hệ thống duyệt exception tree nếu không có nhu cầu thực tế.

## 16. Bảng quyết định: ném lại, bọc hay xử lý?

| Hoàn cảnh | Cách xử lý thường phù hợp | Lý do |
| --- | --- | --- |
| Cùng loại checked exception vẫn nằm trong hợp đồng phương thức | Để lan truyền hoặc `throw original;` | Giữ đúng kiểu gốc, ít lớp bọc |
| Chuyển tầng I/O sang API nghiệp vụ có hợp đồng lỗi riêng | `throw new DomainException(context, original);` | Thêm ngữ cảnh và giữ nguyên nhân |
| Tầng hiện tại có thể retry/phục hồi an toàn | Xử lý cụ thể ở đây | Không cần ném đến tầng trên nếu đã khắc phục |
| Checked exception trở thành lỗi khởi tạo không thể tiếp tục | Có thể bọc unchecked với cause | Bên gọi cần chính sách dừng/ghi log rõ ràng |
| Lỗi resource close xảy ra khi đã có lỗi thân TWR | Giữ primary, để close thành suppressed | Bảo toàn cả hai lỗi |
| Custom exception chưa có constructor nhận cause | `initCause(original)` một lần, nếu hợp lệ | Duy trì khả năng truy vết ở API cũ |
| Custom exception do bạn thiết kế mới | Constructor `(String, Throwable)` | Công khai hợp đồng và an toàn hơn |
| Tầng trung gian chỉ bắt để in message rồi ném tiếp | Cân nhắc bỏ catch thừa | Tránh log lặp và mất ngữ cảnh |
| Gặp `Error` nghiêm trọng | Không bắt/bọc bừa bãi | Có thể không có điều kiện phục hồi an toàn |

Đây là các nguyên tắc thiết kế, không phải quy tắc tuyệt đối. Quyết định cuối cần theo hợp đồng API, khả năng khôi phục, mức độ quan trọng của dữ liệu và chính sách vận hành.

## 17. Những nhầm lẫn phổ biến

**“Bọc lỗi bằng ngoại lệ mới là đã giữ nguyên nhân.”** Sai. Nếu constructor không nhận `cause`, quan hệ cause có thể không được lưu.

**“Chỉ cần nối `original.getMessage()` vào message của wrapper.”** Sai. Message không thay thế đối tượng Throwable, stack trace hoặc suppressed exceptions.

**“`getCause()` trả lỗi mới do `RuntimeException` tự tạo.”** Sai. Nếu constructor nhận đối tượng `original`, `getCause()` trả chính tham chiếu ấy.

**“`initCause` có thể gọi bao nhiêu lần cũng được.”** Sai. Cause thường chỉ được khởi tạo một lần; những lần đặt lại gây `IllegalStateException`.

**“Có thể đặt cause là chính wrapper.”** Sai. Self-causation trực tiếp bị từ chối.

**“`getCause()` và `getSuppressed()` giống nhau.”** Sai. Cause thể hiện quan hệ nguyên nhân; suppressed ghi lỗi bổ sung.

**“Bọc một lỗi có suppressed sẽ tự chuyển suppressed sang wrapper.”** Sai. Thường suppressed vẫn nằm trên đối tượng cause ban đầu, trừ khi code chủ động thêm vào wrapper.

**“Bọc checked exception thành unchecked nghĩa là lỗi đã được xử lý.”** Sai. Nó chỉ đổi hợp đồng kiểm tra compile-time; runtime vẫn có thể thất bại.

**“Nên bắt `Throwable` để bọc luôn `Error` cho thống nhất.”** Không nên coi đây là mặc định; nhiều `Error` báo tình huống không thể phục hồi.

**“Mỗi lớp nên bọc thêm một lớp ngoại lệ dù không thêm thông tin.”** Không. Chuỗi wrapper quá dày làm phức tạp chẩn đoán.

**“Muốn log nguyên nhân thì chỉ cần `getMessage()`.”** Không đủ trong nhiều trường hợp; message bỏ qua stack trace, cause và suppressed.

**“`printStackTrace()` chỉ hiển thị ngoại lệ ngoài cùng.”** Không đúng: nó được thiết kế để thể hiện chuỗi cause và suppressed có liên quan.

**“Một custom exception tự lưu field `original` là công cụ Java sẽ nhận ra cause.”** Không tự động. Hãy gọi `super(message, cause)` hoặc liên kết chuẩn hợp lệ qua `initCause`.

**“Dùng `new IOException(original.getMessage())` là tương đương giữ IOException cũ.”** Sai. Đây là đối tượng mới, ghi stack trace mới và không tự chứa liên kết với object gốc.

**“Đã có cause thì không cần xem suppressed.”** Sai. Lỗi đóng resource có thể nằm trong suppressed của cause sâu bên dưới.

## 18. Câu hỏi tự kiểm tra

1. **Khi bọc `IOException` thành `ImportException`, làm thế nào giữ nguyên nhân?** Dùng constructor `new ImportException("context", original)` và gọi `super(message, cause)` trong lớp custom.
2. **Chỉ viết `new ImportException(original.getMessage())` có giữ object gốc không?** Không.
3. **`getCause()` trả kiểu gì?** `Throwable` hoặc `null`, tùy trạng thái cause.
4. **`getCause()` có trả chính đối tượng đã truyền vào constructor không?** Có; không tự clone.
5. **Cause khác suppressed ở điểm nào?** Cause nói về nguyên nhân/quan hệ bọc, suppressed ghi lỗi phụ, thường ở cleanup.
6. **`IOException` đọc thất bại có suppressed từ `close()`. Sau khi bọc IOException, suppressed nằm ở đâu?** Trên chính đối tượng IOException cause nếu chưa chủ động chuyển/sửa.
7. **Có nên tạo một exception mới chỉ với message của cause rồi truyền nó như cause không?** Không, vì làm mất đối tượng và stack trace gốc.
8. **`initCause` có thể thay nguyên nhân đã được constructor đặt không?** Không; việc khởi tạo lại gây `IllegalStateException`.
9. **Truyền chính object exception làm cause của nó hợp lệ không?** Không, gây `IllegalArgumentException`.
10. **Khi hợp đồng phương thức vẫn cho phép checked IOException và không có ngữ cảnh mới, cần wrapper không?** Thường không; có thể để ngoại lệ tự lan truyền.
11. **Bọc IOException thành IllegalStateException có tự khắc phục lỗi đọc không?** Không.
12. **Điều gì xảy ra nếu handler tạo wrapper nhưng không `throw`?** Caller có thể không được thông báo lỗi; wrapper chỉ là đối tượng bị bỏ qua.
13. **Nên bắt mọi `Error` để bọc thành exception nghiệp vụ?** Không; nhiều `Error` mang ngữ nghĩa sự cố nghiêm trọng.
14. **Có nên log exception ở mọi tầng rồi ném tiếp không?** Thường không; chọn ranh giới log phù hợp để tránh lặp.
15. **Một chain dài gồm wrapper → cause → cause có mất lỗi gốc không?** Không nếu mỗi tầng giữ nguyên đối tượng cause tương ứng.
16. **Nên duyệt `getCause()` vô hạn mà không kiểm tra khi phân tích đối tượng lỗi tùy biến?** Không. Với công cụ tổng quát có thể theo dõi danh tính đối tượng để ngăn vòng.
17. **Có thể vừa có cause vừa có suppressed trên cùng `Throwable` không?** Có; chúng phục vụ hai mục đích khác nhau.
18. **Khi nào nên dùng `initCause`?** Chủ yếu khi tương thích với exception API cũ không có constructor phù hợp và cause chưa được đặt.

## 19. Tài liệu Java 17

- [Java SE 17 — Throwable constructors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): constructor lưu `message`, `cause`, suppression và stack trace.
- [Java SE 17 — Throwable.getCause](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getCause()): truy cập nguyên nhân được lưu.
- [Java SE 17 — Throwable.initCause](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#initCause(java.lang.Throwable)): gắn nguyên nhân một lần và các giới hạn.
- [Java SE 17 — Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed()): các lỗi bổ sung độc lập với cause.
- [Java SE 17 — RuntimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html): constructor với `(String, Throwable)`.
- [Java SE 17 — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): checked exception có thể nhận cause.
- [Java Language Specification 17 — `11, Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): ném, bắt và kiểm tra ngoại lệ.
- [Java Language Specification 17 — `14.20.3, try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): primary/suppressed trong quá trình đóng resource.

**Ghi nhớ:** Khi cần bọc ngoại lệ, hãy truyền **chính đối tượng ngoại lệ đã bắt** vào constructor nhận `cause`, ví dụ `throw new DomainException("meaningful context", original);`. Việc đó cho phép tầng trên xử lý bằng loại lỗi phù hợp mà vẫn lần theo `getCause()` để đến nguyên nhân gốc cùng stack trace và suppressed exceptions. Chỉ dùng `initCause()` khi cần và hợp lệ; không bao giờ coi việc sao chép message là thay thế cho bảo toàn chuỗi nguyên nhân.
