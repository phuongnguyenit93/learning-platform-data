# Java 7 — try-with-resources: Quan hệ với catch, finally và return

## 1. Bản chất của try-with-resources

**Try-with-resources** (TWR), được giới thiệu từ Java 7 và tiếp tục được sử dụng trong Java hiện đại, là cú pháp `try` giúp quản lý vòng đời của những đối tượng thực thi `AutoCloseable`. Điểm quan trọng không chỉ là “tự động gọi `close()`”, mà là **việc đóng tài nguyên diễn ra ở thời điểm xác định trong luồng điều khiển**, kể cả khi thân `try` ném ngoại lệ hoặc thực hiện `return`.

Cú pháp đầy đủ có thể có `catch` và `finally`:

```java
try (ResourceType resource = acquire()) {
    use(resource);
} catch (SomeException ex) {
    handle(ex);
} finally {
    finishUnrelatedWork();
}
```

Đây là **mã minh họa**, không phải chương trình có thể biên dịch độc lập vì các tên `ResourceType`, `acquire`, `use`, `SomeException`, `handle` và `finishUnrelatedWork` đại diện cho API của một dự án. Trong mã thực tế, `ResourceType` phải là subtype của `AutoCloseable`, và các ngoại lệ checked từ khởi tạo/thân `try`/`close()` phải được bắt hoặc khai báo qua `throws`.

**Quy tắc cần nhớ:** Với cùng một câu lệnh TWR, quá trình thực hiện về mặt khái niệm là:

1. Khởi tạo resource trong ngoặc `try (...)`.
2. Thực hiện thân `try { ... }`.
3. **Tự động đóng** các resource đã khởi tạo, dù thân chạy bình thường hay đang thoát vì `return`/exception.
4. Nếu có ngoại lệ cần bắt, đi tới `catch` tương ứng **sau khi đã cố đóng resource**.
5. Chạy `finally` nếu được khai báo, sau thân `try` và/hoặc `catch`.
6. Hoàn thành hành vi đang chờ: trả giá trị, tiếp tục ném ngoại lệ hoặc đi tiếp.

Một lược đồ đơn giản:

```text
Khởi tạo tài nguyên
       │
       ▼
     Thân try ─── bình thường / return / throw
       │
       ▼
Đóng tài nguyên tự động (ngược thứ tự mở)
       │
       ├── Có ngoại lệ còn cần xử lý ──► catch phù hợp (nếu có)
       │                                       │
       └───────────────────────────────────────┘
                                               │
                                               ▼
                                           finally
                                               │
                                               ▼
                                 Đi tiếp / return / propagate
```

*Lưu ý:* Đây là **sơ đồ khái niệm**. Nếu việc khởi tạo resource thứ hai thất bại, các resource đã khởi tạo trước đó vẫn được đóng; lỗi từ khởi tạo và đóng cũng tham gia cơ chế exception/suppression.

### 1.1. Vì sao `finally` không còn phải đảm nhiệm việc đóng tài nguyên?

Trước khi có TWR, lập trình viên thường phải tự đặt `close()` trong `finally` và xử lý thêm lỗi có thể xuất hiện trong chính `close()`. Với resource thực thi `AutoCloseable`, hãy để TWR đảm nhận việc đóng. `finally`, nếu cần, dành cho hành vi **khác** như ghi nhận trạng thái, giải phóng một điều kiện không nằm trong `AutoCloseable`, hoặc cập nhật số liệu giám sát.

Không phải mọi chương trình cần đủ ba khối: một TWR không có `catch` và `finally` là hoàn toàn hợp lệ nếu phương thức để exception truyền lên cho caller.

## 2. Thứ tự: thân try → close → catch → finally

Xét ví dụ ngắn:

```java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    return reader.readLine();
} catch (java.io.IOException ex) {
    reportReadFailure(ex);
    return null;
} finally {
    recordFinishedAttempt();
}
```

Đây là **mã minh họa trong một phương thức**; `path`, `reportReadFailure`, `recordFinishedAttempt` phải được khai báo. `var` yêu cầu Java 10+, nên không phải cú pháp sẵn có trên JDK 7; nhưng TWR và quy tắc đóng trước catch/finally vẫn từ Java 7 và còn áp dụng. Trong mã chạy hoàn chỉnh ở phần sau, bài dùng kiểu resource tường minh để tránh nhầm lẫn.

Nếu `reader.readLine()` thành công và `reader.close()` cũng thành công, giá trị trả về được xác định, resource đóng, `finally` thực hiện, rồi phương thức mới hoàn tất `return`. Khối `catch` không chạy.

Nếu `readLine()` ném `IOException`, việc đóng resource được thử trước; sau đó `catch (IOException)` xử lý lỗi và `finally` vẫn chạy. Nếu `close()` tiếp tục ném lỗi, ngoại lệ đóng sẽ là **suppressed** của ngoại lệ đọc chính.

Nếu `readLine()` thành công nhưng `close()` ném `IOException`, **khối catch vẫn có thể nhận lỗi từ `close()`**. Điều này đặc biệt quan trọng khi thân `try` có `return`: có thể tưởng phương thức đã trả về, nhưng trên thực tế quá trình đóng vẫn phải hoàn tất.

### 2.1. Một catch có thể nhận lỗi từ ba vị trí

Với TWR:

```java
try (var resource = open()) {
    perform(resource);
} catch (java.io.IOException ex) {
    handle(ex);
}
```

Đây là ví dụ cấu trúc, trong một phương thức có các API thích hợp. `IOException` mà catch nhận được có thể đến từ:

- **Lúc khởi tạo:** `open()` thất bại; nếu có resource đã tạo trước đó, Java sẽ đóng chúng.
- **Lúc xử lý:** `perform(resource)` ném lỗi.
- **Lúc đóng:** `resource.close()` ném lỗi, khi không có ngoại lệ chính từ quá trình đang thực hiện trước đó.

Đừng mặc định mọi `IOException` trong catch đều đến từ thao tác “đọc” ở thân try. Khi cần nhận diện chính xác nguồn lỗi, giữ exception và stack trace, bổ sung ngữ cảnh có kiểm soát, hoặc tách pha xử lý theo hợp đồng nghiệp vụ.

### 2.2. Resource có được sử dụng trực tiếp trong catch/finally không?

Resource **khai báo ngay trong ngoặc** `try (Type r = ...)` có phạm vi trong resource specification và thân `try`, không thể đơn giản tham chiếu tên `r` từ `catch` hoặc `finally` nằm ngoài. Ví dụ này cố ý sai:

```java
try (java.io.BufferedReader reader =
         java.nio.file.Files.newBufferedReader(path)) {
    reader.readLine();
} finally {
    // Sai phạm vi biến: reader không truy cập được bằng tên tại đây.
    System.out.println(reader);
}
```

Thông thường không cần giữ tham chiếu trong `finally` vì TWR đã lo đóng. Từ Java 9, có thể đưa một biến **đã khai báo trước và final/effectively final** vào resource specification với dạng `try (existingReader)`. Điều đó không làm thay đổi thứ tự đóng/catch/finally và không có nghĩa được phép đọc tiếp resource sau khi nó đã đóng.

## 3. `return` bên trong try: giá trị đang chờ, không bỏ qua close

Quy tắc gây nhầm lẫn nhiều nhất: **`return` trong thân TWR không nhảy ra khỏi phương thức ngay lập tức**. Java tính biểu thức trả về, sau đó đóng resource và chạy `finally` trước khi việc trả về hoàn thành, trừ khi quá trình thoát bị thay bằng một ngoại lệ hoặc hành vi khác.

Ví dụ đơn giản với resource đóng thành công:

```java
static String firstLine(java.nio.file.Path file) throws java.io.IOException {
    try (java.io.BufferedReader reader =
             java.nio.file.Files.newBufferedReader(file)) {
        return reader.readLine();
    }
}
```

Đây là **phương thức hoàn chỉnh để đặt trong một lớp**, không phải chương trình tự chạy vì không có `main`. Khi đọc thành công, Java vẫn gọi `reader.close()` trước khi trả về chuỗi đã đọc. Nếu đọc hoặc đóng ném `IOException`, method có thể ném lỗi theo khai báo `throws IOException` thay vì trả chuỗi.

Không cần viết:

```java
try (java.io.BufferedReader reader =
         java.nio.file.Files.newBufferedReader(file)) {
    String line = reader.readLine();
    reader.close(); // Không nên đóng tay: TWR vẫn sẽ tự close.
    return line;
}
```

Đoạn này cũng chỉ là mã minh họa; **tránh gọi `close()` thủ công trong thân TWR** nếu không có chủ đích đặc biệt. Tự đóng trước thời điểm quản lý tự động có thể gây double-close hoặc làm các thao tác về sau trên resource thất bại, và không bảo đảm mọi implementation của `AutoCloseable` đều hỗ trợ đóng lặp an toàn.

### 3.1. Hai nhánh cần phân biệt

| Điều xảy ra khi thân try gặp `return value;` | Kết quả |
| --- | --- |
| Mọi resource đóng thành công; `finally` hoàn tất bình thường | Phương thức trả `value` đã được tính. |
| `close()` ném ngoại lệ và không có lỗi chính trước đó | Việc `return` đang chờ **bị hủy**; ngoại lệ đóng có thể được catch xử lý hoặc truyền ra ngoài. |
| `close()` ném ngoại lệ; một `catch` tương ứng xử lý và `return fallback;` | Return ban đầu không còn hiệu lực; khi finally hoàn tất bình thường, trả kết quả từ catch. |
| `finally` ném exception mới | Exception mới có thể **ghi đè** return hoặc exception đang chờ; phải tránh nếu không chủ đích. |
| `finally` có `return other;` | Giá trị từ finally có thể **ghi đè** cả return cũ và ngoại lệ; không nên thiết kế như vậy. |

Bởi vậy “có `return` trong try thì chắc chắn trả giá trị” là **sai**. Hoàn thành việc đóng tài nguyên là một phần của quá trình kết thúc TWR.

### 3.2. Biểu thức return được tính lúc nào?

Trong:

```java
int result = 7;
try (MyResource resource = openResource()) {
    return result;
}
```

Đây là đoạn minh họa trong một phương thức trả `int`, với lớp/method resource do ứng dụng định nghĩa. Biểu thức `result` được tính khi gặp `return`, sau đó Java mới đóng resource. Thay đổi giá trị của biến cục bộ trong một thao tác khác không làm “tính lại” biểu thức return đã tính. Nhưng nếu `close` ném lỗi, hành vi return có thể không hoàn tất.

Với return của **tham chiếu đối tượng**, đối tượng đó vẫn có thể là mutable; việc đã tính xong tham chiếu không có nghĩa đối tượng được đóng băng hoặc không thể bị sửa. Đây là vấn đề aliasing/mutability riêng với try-with-resources.

## 4. `catch` chạy sau auto-close, kể cả khi lỗi đến từ close

Xét tài nguyên tự định nghĩa:

```java
static final class TestResource implements AutoCloseable {
    @Override public void close() throws java.io.IOException {
        throw new java.io.IOException("close failed");
    }
}
```

Đây là **khai báo lớp để đặt trong một lớp chứa**, nhằm mô phỏng tình huống đóng thất bại.

```java
static String attempt() {
    try (TestResource resource = new TestResource()) {
        return "ready";
    } catch (java.io.IOException ex) {
        return "fallback";
    }
}
```

Đây là **phương thức đặt trong cùng lớp đã khai báo TestResource**. Kết quả là `"fallback"`, **không** phải `"ready"`: khi Java cố đóng tài nguyên, `close()` ném IOException, hủy return đang chờ; catch bắt lỗi và quyết định giá trị khác.

Một catch có thể có `return` hoặc `throw` riêng, nhưng `finally` của cùng câu lệnh TWR vẫn thực hiện sau catch khi JVM tiếp tục thực thi bình thường. Do đó đừng dựa vào `return` trong catch để “bỏ qua” logic finally.

## 5. Quan hệ với finally: vẫn thực thi sau auto-close và catch

Thân TWR có thể có `finally`:

```java
try (java.io.BufferedReader reader =
         java.nio.file.Files.newBufferedReader(path)) {
    process(reader);
} catch (java.io.IOException ex) {
    report(ex);
} finally {
    reportAttemptFinished();
}
```

Đây là cấu trúc minh họa trong một phương thức. Thứ tự chính là:

- Đọc/xử lý trong try.
- Đóng `reader` theo cơ chế TWR.
- Nếu lỗi được ném ra, chọn `catch` phù hợp.
- Thực hiện `reportAttemptFinished()` trong `finally`.
- Sau đó tiếp tục hoặc hoàn tất phương thức.

Ngay cả khi try hoặc catch có `return`, `finally` vẫn được thực hiện trước khi return hoàn thành trong luồng thực thi Java thông thường. Nếu `finally` hoàn tất bình thường, nó **không thay thế** kết quả return/exception đang chờ.

**Ngoại lệ cần ghi nhớ:** `finally` không phải cam kết chạy khi toàn bộ JVM bị chấm dứt bất thường, ví dụ tiến trình bị cưỡng bức kết thúc. Đừng dùng finally như cơ chế đảm bảo lưu trữ dữ liệu tuyệt đối khi hệ thống mất điện hoặc bị kill.

### 5.1. Đừng `return` trong finally

Ví dụ **cố ý sai về thiết kế**:

```java
static int dangerous() {
    try {
        throw new IllegalStateException("original failure");
    } finally {
        return 0; // Che mất ngoại lệ gốc.
    }
}
```

Mã trên có thể biên dịch, nhưng `finally` hoàn thành bằng `return 0`, khiến caller **không nhìn thấy IllegalStateException**. Trong code thực tế, tránh `return`/`break`/`continue` và exception không chủ đích từ finally vì chúng có thể ghi đè lý do thoát ban đầu. TWR giúp loại bỏ phần lớn nhu cầu đóng resource trực tiếp trong finally, giảm rủi ro này.

### 5.2. finally vẫn có ích ở đâu?

- Ghi nhận thời điểm kết thúc một attempt, khi cách ghi nhận không làm hỏng luồng lỗi đang chờ.
- Kết thúc một trạng thái/điều kiện không được biểu diễn bằng `AutoCloseable`, nếu thật sự cần.
- Bổ sung telemetry đơn giản đã được kiểm soát lỗi.

Với cleanup của resource **có thể triển khai `AutoCloseable`**, ưu tiên TWR. Nếu cleanup của finally tự có nguy cơ ném ngoại lệ, thiết kế để không vô tình che mất lỗi gốc; trong nhiều trường hợp, chuyển cleanup thành resource có quản lý vòng đời sẽ an toàn và dễ đọc hơn.

## 6. Khi thân try và close cùng ném lỗi: primary và suppressed

Một đặc điểm quan trọng của TWR từ Java 7 là bảo toàn **ngoại lệ chính** (*primary exception*) và lưu **lỗi đóng tài nguyên** như *suppressed exceptions* khi có ngoại lệ trước đó.

Giả sử:

```java
try (FailingClose resource = new FailingClose()) {
    throw new IllegalStateException("body failed");
} catch (IllegalStateException ex) {
    System.out.println(ex.getMessage()); // "body failed"
    for (Throwable extra : ex.getSuppressed()) {
        System.out.println(extra.getMessage());
    }
}
```

Đây là đoạn minh họa trong một phương thức có lớp `FailingClose` thực thi `AutoCloseable` và ném lỗi trong `close()`. Khi try ném `IllegalStateException` rồi close ném lỗi, **lỗi ở thân try được giữ làm primary**, còn lỗi đóng được gắn vào `ex.getSuppressed()`. Nhờ vậy chương trình không đánh mất nguyên nhân ban đầu như một khối finally tự đóng resource có thể gây ra.

Cần phân biệt:

- **`ex.getCause()`:** mối liên hệ ngoại lệ nguyên nhân do code/API thiết lập.
- **`ex.getSuppressed()`:** các ngoại lệ phụ gắn kèm một lỗi chính, thường từ việc tự động đóng resource.

Một Throwable có thể có cả cause và suppressed. Nếu log bằng API nhận nguyên `Throwable`, hệ thống logging thích hợp có thể in cả cause và suppressed; chỉ log `getMessage()` là không đủ để chẩn đoán.

### 6.1. Khi không có lỗi ở thân try nhưng nhiều close bị lỗi

Nếu có hai tài nguyên `A`, `B` khởi tạo theo thứ tự đó, Java sẽ đóng **B trước, A sau**. Nếu thân try hoàn thành bình thường nhưng cả hai lần đóng đều ném lỗi, lỗi đóng của **B** thường trở thành primary exception; lỗi đóng của **A** được đính kèm như suppressed.

Ngược lại, nếu thân try đã ném lỗi, ngoại lệ từ thân là primary; lỗi close B và A lần lượt nằm trong danh sách suppressed. Các tài nguyên vẫn được cố đóng theo thứ tự dù `close()` của B gặp lỗi.

## 7. Chương trình Java 17+ hoàn chỉnh minh họa cả ba luồng

Ví dụ này cố tình mô phỏng resource tự đóng, có/không ném ngoại lệ, để stdout **không phụ thuộc file hệ thống, database, mạng hoặc thời gian thực**.

Tạo tệp **`ResourceFlowDemo.java`**:

```java
import java.io.IOException;

public class ResourceFlowDemo {
    static final class NamedResource implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;

        NamedResource(String name, boolean failOnClose) {
            this.name = name;
            this.failOnClose = failOnClose;
            System.out.println("open " + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            if (failOnClose) {
                throw new IOException("closing " + name);
            }
        }
    }

    static String normalReturn() {
        try (NamedResource resource = new NamedResource("normal", false)) {
            System.out.println("body normal");
            return "ok";
        } catch (IOException ex) {
            return "not expected";
        } finally {
            System.out.println("finally normal");
        }
    }

    static String failedClose() {
        try (NamedResource resource = new NamedResource("failed", true)) {
            System.out.println("body return pending");
            return "will be cancelled";
        } catch (IOException ex) {
            System.out.println("catch " + ex.getMessage());
            return "fallback";
        } finally {
            System.out.println("finally failed");
        }
    }

    static void bodyAndCloseFail() throws IOException {
        try (NamedResource first = new NamedResource("A", true);
             NamedResource second = new NamedResource("B", true)) {
            System.out.println("body throws");
            throw new IllegalStateException("body error");
        } catch (IllegalStateException ex) {
            System.out.println("catch " + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed " + suppressed.getMessage());
            }
        } finally {
            System.out.println("finally both");
        }
    }

    public static void main(String[] args) throws IOException {
        System.out.println("result normal = " + normalReturn());
        System.out.println("result failed = " + failedClose());
        bodyAndCloseFail();
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ResourceFlowDemo.java
java ResourceFlowDemo
```

**Stdout chính xác:**

```text
open normal
body normal
close normal
finally normal
result normal = ok
open failed
body return pending
close failed
catch closing failed
finally failed
result failed = fallback
open A
open B
body throws
close B
close A
catch body error
suppressed closing B
suppressed closing A
finally both
```

### Phân tích từng luồng

**Luồng 1 — `normalReturn()`:**

1. In `open normal` khi khởi tạo.
2. In `body normal` rồi gặp `return "ok"`.
3. Trước khi thực sự trả `"ok"`, TWR gọi `close()` và in `close normal`.
4. Vì đóng thành công, khối catch không chạy; finally in `finally normal`.
5. Chỉ sau đó `main` mới in `result normal = ok`.

**Luồng 2 — `failedClose()`:**

1. In `open failed` và `body return pending`.
2. `return "will be cancelled"` chuẩn bị trả kết quả, nhưng `close()` in `close failed` rồi ném `IOException("closing failed")`.
3. Exception từ close **thay thế luồng return**, được `catch (IOException)` nhận, in `catch closing failed` và chọn `return "fallback"`.
4. finally vẫn in `finally failed`.
5. Cuối cùng `main` nhận và in `result failed = fallback`. Chuỗi `"will be cancelled"` không bao giờ trở thành kết quả trả về của lời gọi này.

**Luồng 3 — `bodyAndCloseFail()`:**

1. Khởi tạo lần lượt A rồi B, vì vậy log là `open A`, `open B`.
2. Thân try in `body throws` và ném `IllegalStateException("body error")`.
3. Auto-close chạy **B rồi A**, cả hai ném `IOException`, nhưng được gắn thành suppressed của lỗi body.
4. `catch (IllegalStateException)` in `catch body error` và hai message suppressed theo thứ tự `closing B`, `closing A`.
5. Sau cùng finally in `finally both`. Phương thức có thể hoàn tất bình thường vì khối catch đã xử lý lỗi chính; khai báo `throws IOException` vẫn là một hợp đồng được phép của phương thức.

**Kết luận từ code:** TWR đóng tài nguyên **trước** khi các `catch`/`finally` cùng cấp thực hiện, không bỏ qua close khi có return, và không làm mất lỗi chính khi đóng resource cũng thất bại.

## 8. Các kịch bản và thứ tự hành vi cần ghi nhớ

| Trạng thái ở thân try | Đóng resource | catch | finally | Kết quả có thể quan sát |
| --- | --- | --- | --- | --- |
| Chạy hết, không có lỗi | Thành công | Không chạy | Chạy nếu có | Đi tiếp sau câu lệnh. |
| Chạy hết, không có lỗi | Ném exception | Catch tương ứng chạy nếu có | Chạy nếu có | Exception đóng là lỗi cần xử lý hoặc truyền lên. |
| `return value` | Thành công | Không chạy | Chạy nếu có | Return `value` (nếu finally không ghi đè). |
| `return value` | Ném exception | Catch tương ứng có thể chạy | Chạy nếu có | Pending return bị thay thế bằng exception; catch có thể quyết định return khác. |
| Body ném exception E | Close thành công | Catch E nếu có | Chạy nếu có | E được xử lý hoặc truyền lên. |
| Body ném E | Close cũng ném F | Catch E nếu có | Chạy nếu có | E thường là primary; F ở `E.getSuppressed()`. |
| Body ném E | Close ném F | Catch chỉ phù hợp F, không phù hợp E | Chạy nếu có | Catch F không xử lý được E; E tiếp tục truyền lên nếu không bị hành vi khác thay thế. |
| Khởi tạo resource sau thất bại | Resource trước đó được đóng | Catch tương ứng với lỗi khởi tạo nếu có | Chạy nếu có | Không vào thân try; không bỏ quên resource đã khởi tạo. |
| Catch có `return result` | Resource đã đóng | Return đang chờ | Finally vẫn chạy | Return từ catch nếu finally hoàn tất bình thường. |

Bảng giả định Java tiếp tục thực thi thông thường và chính khối `finally` không tự ném exception mới hay return để thay đổi kết quả. Khi finally hoàn thành đột ngột, quy tắc thay thế luồng điều khiển vẫn áp dụng như với `try/catch/finally` thông thường.

## 9. Nhiều resource: thứ tự mở/đóng và phạm vi catch

TWR cho phép nhiều resource:

```java
try (java.io.InputStream in = java.nio.file.Files.newInputStream(source);
     java.io.OutputStream out = java.nio.file.Files.newOutputStream(target)) {
    in.transferTo(out);
} catch (java.io.IOException ex) {
    handleCopyFailure(ex);
} finally {
    recordCopyFinished();
}
```

Đây là mã minh họa trong một phương thức có `source`, `target`, `handleCopyFailure` và `recordCopyFinished`. `InputStream.transferTo` có từ Java 9 và chạy trên JDK 17+; logic TWR đóng ngược thứ tự đã có từ Java 7.

Trình tự khi mọi khởi tạo thành công:

1. Tạo `in`.
2. Tạo `out`.
3. Chạy `in.transferTo(out)`.
4. Đóng `out`.
5. Đóng `in`.
6. Khi có ngoại lệ chưa xử lý, vào `catch`.
7. Chạy `finally`.

Nếu tạo `out` thất bại, `in` **vẫn được đóng tự động** trước khi catch xử lý lỗi khởi tạo. Nếu đóng `out` thất bại, Java vẫn cố đóng `in`. Nếu lỗi ban đầu phát sinh từ `transferTo`, lỗi đóng trở thành suppressed.

Với code sao chép file thực tế, cần xác định chế độ ghi đè, tính nguyên tử, cleanup của file đích khi sao chép thất bại, và quyền truy cập. **TWR quản lý đóng resource, không bảo đảm thao tác nghiệp vụ là giao dịch nguyên tử hoặc đã hoàn tất thành công.**

## 10. Checked exception từ close: phải tính trong thiết kế hàm

`AutoCloseable.close()` có thể khai báo `throws Exception`; `java.io.Closeable.close()` khai báo `throws IOException`. Một implementation có thể thu hẹp hoặc không khai báo ngoại lệ checked nào. Compiler phân tích kiểu khai báo và thân try để xác định những checked exception cần bắt/khai báo.

Ví dụ:

```java
static String readHeader(java.nio.file.Path path)
        throws java.io.IOException {
    try (java.io.BufferedReader reader =
             java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
```

Phương thức này hợp lệ vì `throws IOException` bao phủ các lỗi đọc và đóng reader. **Không cần có catch** nếu caller chịu trách nhiệm xử lý.

Ngược lại, mã minh họa sau cố ý sai về hợp đồng checked exception:

```java
static String unsafeHeader(java.nio.file.Path path) {
    try (java.io.BufferedReader reader =
             java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
```

Nó không biên dịch vì không bắt hoặc khai báo `IOException` có thể phát sinh từ mở/đọc/đóng. Việc có `return` không loại bỏ trách nhiệm này.

Một điểm thực hành: với resource có `close()` được khai báo ném kiểu `Exception` rất rộng, phương thức có thể phải xử lý cả kiểu đó, dù thân try không ném; cân nhắc triển khai `Closeable` hoặc override `close()` với kiểu ngoại lệ phù hợp nếu domain của resource cho phép.

## 11. Vẫn cần catch riêng để chuyển lỗi sang ý nghĩa nghiệp vụ

TWR chỉ quản lý vòng đời, không quyết định lỗi nào cần hiển thị ở API/UI. Ví dụ phương thức đọc nội dung có thể chọn giữ `IOException` để caller xử lý, hoặc wrap thành lỗi nghiệp vụ có cause:

```java
static String loadRequiredConfig(java.nio.file.Path path) {
    try (java.io.BufferedReader reader =
             java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    } catch (java.io.IOException ex) {
        throw new IllegalStateException(
                "Unable to load required configuration", ex);
    }
}
```

Đây là phương thức có thể đặt trong lớp Java. Nó chủ động đổi IOException thành unchecked exception ở ranh giới yêu cầu cấu hình, đồng thời **giữ nguyên lỗi gốc bằng tham số `cause`**. Trong triển khai thực tế, chỉ dùng unchecked nếu đúng hợp đồng API và policy khởi động của hệ thống.

Điểm quan trọng cho quan hệ với TWR:

- Nếu lỗi xảy ra trong thân try, TWR vẫn đóng reader trước khi catch nhận `IOException`.
- Nếu lỗi xuất hiện từ close, catch cũng có thể bắt và wrap lỗi đó.
- Nếu nhiều lỗi xảy ra, exception chính và suppressed vẫn được giữ trên đối tượng `ex`; wrapper mới chứa `ex` như cause nên không làm mất chẩn đoán.

**Đừng wrap chỉ bằng `ex.getMessage()`**: cách đó làm đứt cause chain và có thể che mất suppressed exceptions. Nếu chỉ muốn log, truyền chính `Throwable` cho logging API thích hợp.

## 12. So sánh với try-catch-finally truyền thống

Ví dụ đóng tay bằng finally sau đây dễ xảy ra lỗi ưu tiên ngoại lệ:

```java
java.io.InputStream in = java.nio.file.Files.newInputStream(path);
try {
    process(in);
} finally {
    in.close();
}
```

Đây là đoạn mã minh họa trong phương thức có `path`, `process` và chữ ký `throws IOException` phù hợp. Nếu `process(in)` ném lỗi E và `in.close()` ném lỗi F, một `finally` đóng tay có thể khiến F **ghi đè E** trong luồng exception truyền ra. Không nên tái tạo logic suppression phức tạp thủ công cho những resource có thể dùng TWR.

Dùng TWR:

```java
try (java.io.InputStream in =
         java.nio.file.Files.newInputStream(path)) {
    process(in);
}
```

Nếu body ném E và `close()` ném F, cơ chế TWR giữ E là primary và F là suppressed. Còn nếu body thành công nhưng close lỗi, F trở thành exception được truyền ra — phù hợp vì đóng tài nguyên có thể là một bước thất bại quan trọng.

**Không nên dùng cả TWR lẫn `finally { resource.close(); }` cho cùng một resource.** Đóng lặp có thể phát sinh lỗi, làm khó xác định ownership và đi ngược mục đích của TWR. Hãy xác định rõ ai sở hữu vòng đời resource.

## 13. Lỗi thường gặp khi kết hợp catch, finally và return

**Lỗi 1 — “Có `return` trong try thì `close()` không chạy.”** Sai. Auto-close chạy trước khi return hoàn tất.

**Lỗi 2 — “`catch` chạy trước khi resource được đóng.”** Sai với các catch của cùng TWR: các resource đã được đóng hoặc đã được cố đóng trước khi catch thực hiện.

**Lỗi 3 — “Nếu thân try không ném lỗi, catch sẽ không bao giờ chạy.”** Sai. Lỗi từ khởi tạo/close cũng có thể khiến catch chạy.

**Lỗi 4 — “finally là nơi phải gọi close() cho resource đã đặt trong try(...).”** Sai. TWR đã quản lý close; finally có thể dùng cho trách nhiệm khác nếu cần.

**Lỗi 5 — “`return` trong finally chỉ giúp code rõ hơn.”** Sai. Nó có thể che ngoại lệ gốc hoặc ghi đè giá trị trả về từ try/catch.

**Lỗi 6 — “Cả body và close ném exception thì close mới là lỗi chính.”** Không đúng với TWR thông thường: lỗi body được giữ làm primary; lỗi close ở suppressed.

**Lỗi 7 — “Chỉ cần kiểm tra `getCause()` để biết mọi lỗi phát sinh khi đóng.”** Không. Lỗi đóng resource thường nằm trong `getSuppressed()` của lỗi chính, không tự động nằm trong cause.

**Lỗi 8 — “catch `IOException` chắc chắn chỉ bắt lỗi trong thân try.”** Sai: nó còn có thể nhận lỗi của resource initializer hoặc close.

**Lỗi 9 — “Sau khi catch được IOException, mọi resource có thể tiếp tục sử dụng.”** Sai. Auto-close đã được thử trước khi catch chạy; resource được khai báo trong ngoặc try cũng không nằm trong phạm vi của catch.

**Lỗi 10 — “TWR bảo đảm chương trình không có lỗi tài nguyên.”** Không. TWR giúp quản lý đóng resource nhưng resource vẫn có thể không mở được, thao tác thất bại, close lỗi hoặc bị chấm dứt do lỗi hạ tầng bên ngoài JVM.

## 14. Checklist áp dụng vào code dự án

1. **Resource thực thi AutoCloseable?** Dùng TWR khi bạn sở hữu vòng đời của nó và cần đóng khi thoát scope.
2. **Có bao nhiêu resource?** Viết rõ thứ tự khởi tạo, nhớ chúng được đóng ngược thứ tự.
3. **Có `return` bên trong không?** Chấp nhận rằng close và finally chạy trước khi return hoàn tất; code phải tính đến khả năng close thất bại.
4. **Có catch không?** Bắt đúng exception từ khởi tạo, body và close; tránh bắt rộng rồi âm thầm bỏ qua lỗi.
5. **Có finally không?** Chỉ dùng khi có công việc ngoài việc close resource; tránh return/throw ngoài ý muốn làm mất lỗi ban đầu.
6. **Có thể có nhiều lỗi?** Ghi lại Throwable khi cần, kiểm tra suppressed để không bỏ lỡ lỗi từ close.
7. **Có khai báo đủ checked exceptions?** Tính cả `close()`, không chỉ các lời gọi trong thân try.
8. **Có chuyển abstraction?** Nếu wrap, giữ cause: `new DomainException("context", ex)` thay vì chỉ giữ message.
9. **Có test đường close lỗi?** Test cả body lỗi và close lỗi, cũng như return pending bị close exception hủy.
10. **Có tuân theo JDK mục tiêu?** TWR có từ Java 7, cú pháp dùng biến có sẵn trong `try(existingVariable)` bắt đầu ở Java 9, `var` trong resource declaration bắt đầu từ Java 10. Với ứng dụng hiện đại, dùng JDK được hỗ trợ và chọn cú pháp tương ứng với mức `--release`.

## 15. Câu hỏi tự kiểm tra

**1.** Trong `try (R r = ...) { return "ok"; }`, `close()` có được gọi không? — **Có.** Close diễn ra trước khi return hoàn tất. Nếu close ném lỗi, return có thể bị thay thế.

**2.** Khi thân try ném `IllegalStateException`, còn close ném `IOException`, catch nào sẽ nhận ngoại lệ chính? — Catch phù hợp với **`IllegalStateException`**; `IOException` thường nằm trong `getSuppressed()` của lỗi chính.

**3.** `finally` của TWR chạy trước hay sau auto-close? — **Sau** khi các resource được đóng/cố đóng, và sau catch nếu catch tương ứng được thực thi.

**4.** Nếu resource B mở sau A, chúng đóng theo thứ tự nào? — **B rồi A**. Nếu mở B thất bại, A đã khởi tạo vẫn được đóng.

**5.** `return 1;` trong try, `return 2;` trong finally. Giá trị nào được trả? — **2**, nếu finally chạy tới return đó; đây là lỗi thiết kế nên tránh vì ghi đè luồng trước.

**6.** Đọc file thành công rồi `close()` ném `IOException`. Catch của TWR có thể bắt lỗi không? — **Có.** Lỗi từ close có thể làm hủy return đang chờ hoặc khiến câu lệnh thất bại.

**7.** Bản thân TWR có bắt buộc phải có catch không? — **Không.** Chỉ cần xử lý hoặc khai báo checked exceptions theo hợp đồng; TWR tự đóng dù không có catch/finally.

**8.** Ghi lại `ex.getMessage()` có đủ để giữ suppressed exceptions không? — **Không**. Giữ/log chính `Throwable` hoặc truyền nó làm cause khi wrap.

**9.** Có nên đóng cùng resource một lần trong thân try và thêm một lần trong finally không? — **Không nên.** Quản lý vòng đời nhất quán qua TWR để tránh double-close.

**10.** TWR giúp quản lý việc đóng nhưng có đảm bảo ghi file thành công và giao dịch được commit không? — **Không**. Kết quả thao tác nghiệp vụ, commit/rollback và xử lý lỗi vẫn cần thiết kế riêng.

## Tài liệu chính thức

- [Java Language Specification 17, §14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): thứ tự khởi tạo/đóng resource, cơ chế suppressed exception, mối quan hệ với catch/finally.
- [Java Language Specification 17, §14.20.2 — Execution of try-finally](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.2): quy tắc kiểm soát luồng và việc finally có thể thay thế hành vi thoát ban đầu.
- [Java SE 17 API — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng đóng resource và các lưu ý khi `close()` ném ngoại lệ.
- [Java SE 17 API — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()` và `getSuppressed()`.
- [dev.java — Catching and Handling Exceptions](https://dev.java/learn/catching-and-handling-exceptions/): cách tiếp cận hiện đại với try/catch/finally/try-with-resources.

**Ghi nhớ:** Trong TWR, **resource được đóng trước catch/finally**. `return` trong try là kết quả **đang chờ**, có thể bị lỗi close thay thế. Nếu thân try và close cùng thất bại, **lỗi chính được giữ, lỗi đóng được suppressed**. Hãy để TWR quản lý close, dùng catch để xử lý đúng exception và chỉ dùng finally khi thực sự cần công việc khác.