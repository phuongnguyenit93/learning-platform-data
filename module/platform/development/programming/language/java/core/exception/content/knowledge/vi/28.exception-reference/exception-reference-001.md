# Bảng phân biệt `throw`, `throws`, `catch` và `finally` trong Java

> **Chủ đề:** Java Core — Exception
> 
> **Mục đích:** tài liệu tra cứu độc lập về cú pháp, ý nghĩa, vị trí, cách phối hợp và các lỗi thường gặp khi sử dụng bốn từ khóa `throw`, `throws`, `catch`, `finally`. Ví dụ chính dùng Java 17+ và có thể biên dịch/chạy trực tiếp.

## 1. Bảng so sánh nhanh

| Đặc điểm | `throw` | `throws` | `catch` | `finally` |
| --- | --- | --- | --- | --- |
| Bản chất | **Câu lệnh** ném một đối tượng `Throwable` | **Mệnh đề khai báo** trong chữ ký method/constructor | **Mệnh đề xử lý** exception sau `try` | **Mệnh đề dọn dẹp/kết thúc** sau `try` hoặc `catch` |
| Mục tiêu | Chủ động báo một lỗi **ngay tại điểm thực thi** | Công bố các **checked exception** có thể thoát ra khỏi method/constructor | Tiếp nhận và xử lý một exception có kiểu phù hợp | Chạy đoạn code khi rời cấu trúc `try` theo cơ chế thông thường |
| Cú pháp đại diện | `throw new IOException("failed");` | `void load() throws IOException` | `catch (IOException ex) { ... }` | `finally { closeResources(); }` |
| Vị trí | Trong thân method, constructor, initializer, lambda/block thích hợp | Sau danh sách tham số, trước thân method/constructor | Sau khối `try`, trước `finally` nếu có | Sau khối `try` và các `catch` nếu có |
| Dấu kết thúc | `;` sau biểu thức | Không có dấu `;` riêng trong header; kết thúc theo chữ ký/phần thân | Block `{ ... }` | Block `{ ... }` |
| Đối số | Một **biểu thức có kiểu `Throwable`** | Danh sách **kiểu exception**, phân cách bằng dấu phẩy | Một parameter có kiểu exception hoặc multi-catch | Không có parameter |
| Có tạo/ném exception? | **Có**: chuyển điều khiển bằng việc ném | **Không**: tự nó không ném hoặc tạo đối tượng | **Không**: nhận exception đã xảy ra; trong thân có thể `throw` tiếp | **Không mặc định**: thân `finally` vẫn có thể chủ động ném |
| Xử lý checked exception | Việc ném checked exception phải được bắt hoặc khai báo theo luật Java | Cho phép caller biết và xử lý/khai báo checked exception | Có thể thỏa yêu cầu bắt checked exception | Không thay thế `catch`/`throws` cho checked exception |
| Quan hệ với call stack | Bắt đầu lan truyền exception qua stack | Mô tả một phần contract compile time của method | Dừng việc lan truyền **nếu** nhận và xử lý; có thể rethrow | Được chạy trong lúc rời khối, kể cả khi đang unwind trong trường hợp thông thường |
| Có thể đứng riêng? | Có thể dùng trong một block hợp lệ | Chỉ dùng trong khai báo method/constructor | Không: phải đi cùng `try` | Không: phải đi cùng `try` |
| Rủi ro nổi bật | Ném sai loại lỗi, mất cause, đưa secret vào message | Khai báo quá rộng `throws Exception`, hiểu nhầm là sẽ luôn ném | Bắt quá rộng/nuốt lỗi, che bug và ngắt luồng | `return` hoặc `throw` trong `finally` che kết quả/lỗi ban đầu |

**Một câu ghi nhớ:** `throw` là **hành động ném**, `throws` là **lời khai báo**, `catch` là **nơi bắt**, `finally` là **nơi thực hiện phần kết thúc/dọn dẹp**.

Một phương thức hoàn toàn có thể dùng **cả bốn**. Ví dụ:

```java
static String load(boolean offline) throws IOException {
    try {
        if (offline) {
            throw new IOException("source unavailable");
        }
        return "DATA";
    } catch (IllegalArgumentException ex) {
        return "INVALID";
    } finally {
        System.out.println("finished");
    }
}
```

Đây là **mảnh code** cần import `java.io.IOException` và đặt trong một class. `throws IOException` khai báo checked exception có thể thoát; `throw` ném thật khi `offline`; `catch` ở đây chỉ nhận `IllegalArgumentException`, **không** nhận `IOException`; `finally` in thông báo khi khối rời đi. Không nên tưởng bất kỳ `catch` nào cũng bắt được mọi exception.

## 2. Nhìn vào thứ tự điều khiển trước khi học cú pháp

Một đường đi đơn giản:

```text
Caller gọi method
       |
       v
  Vào khối try
       |
       +-- Chạy bình thường ---------> bỏ qua catch
       |                                     |
       +-- Ném exception E                   |
               |                             |
               +--> catch đầu tiên hợp E?    |
                         |                   |
                         +-- có -> xử lý     |
                         |                   |
                         +-- không -> lan truyền
                                             |
                                             v
                                      finally (nếu có)
                                             |
                              kết quả / tiếp tục ném / rẽ nhánh
```

Đây là mô hình khái niệm. `finally` được thực thi trước khi câu lệnh `try` hoàn tất theo các đường rời thông thường. Tuy nhiên **không phải lời bảo đảm tuyệt đối cho mọi trường hợp của JVM**: process bị dừng cưỡng bức, `System.exit` kết thúc VM, JVM crash, luồng kẹt vĩnh viễn hoặc những tình huống không đạt tới điểm rời có thể khiến `finally` không chạy.

**Thứ tự quan trọng:** nếu `catch` xử lý xong và không ném tiếp, `finally` chạy trước khi code sau toàn bộ `try/catch/finally` tiếp tục. Nếu exception không được catch, `finally` vẫn được thử chạy trước khi exception lan ra caller.

## 3. `throw`: chủ động ném một exception ngay bây giờ

Cú pháp chuẩn:

```java
throw expression;
```

`expression` phải có kiểu phù hợp với `Throwable` theo luật ngôn ngữ Java, ví dụ:

```java
throw new IllegalArgumentException("quantity must be positive");
```

Đây là mảnh code trong method. Khi câu lệnh được thực thi, các lệnh bình thường **phía sau trong cùng đường đi** không tiếp tục, trừ khi exception được bắt tại một khối bao quanh phù hợp.

Một ví dụ validation:

```java
static int requirePositive(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be positive");
    }
    return quantity;
}
```

Đây là method có thể đặt trong class. `IllegalArgumentException` là `RuntimeException`, vì vậy method không bắt buộc khai báo `throws IllegalArgumentException`. Dù không bắt buộc, API có thể tài liệu hóa `@throws` và điều kiện đầu vào.

### `throw` không phải `return`

- `return` kết thúc method bằng một giá trị (hoặc không có giá trị đối với `void`).
- `throw` kết thúc **đường điều khiển hiện tại** bằng một exception.
- Caller nhận giá trị chỉ khi đường điều khiển hoàn tất bình thường; nếu exception lan ra, caller không nhận giá trị thông thường của lời gọi đó.

### `throw` có thể ném lại exception đã bắt

```java
try {
    read();
} catch (IOException ex) {
    recordFailure();
    throw ex;
}
```

Đây là mảnh code trong method khai báo `throws IOException` (hoặc có handler bao ngoài), cần import `IOException` và định nghĩa `read`/`recordFailure`. `throw ex;` giữ chính **đối tượng Throwable** đã bắt, bao gồm stack/cause/suppressed sẵn có; không tạo wrapper mới.

### `throw null` thì sao?

Một biểu thức throw có thể đánh giá thành `null`; khi thực thi `throw null;`, JVM phát sinh `NullPointerException` thay vì ném một exception hữu ích. Không làm vậy để biểu thị thiếu dữ liệu. Dùng loại exception có nghĩa với thông điệp phù hợp.

## 4. `throws`: khai báo khả năng lan truyền, không tự ném lỗi

Cú pháp:

```java
ReturnType methodName(Parameters...) throws ExceptionType1, ExceptionType2 {
    // method body
}
```

Đây là mẫu chữ ký, không phải code độc lập. Một ví dụ thật:

```java
static String readFile(Path path) throws IOException {
    return Files.readString(path);
}
```

Đây là method cần import `java.nio.file.Path`, `java.nio.file.Files`, `java.io.IOException`. Lời khai báo cho biết caller phải xử lý hoặc truyền tiếp khả năng `IOException` (checked exception). Nhưng **một lần gọi thành công sẽ không ném exception chỉ vì header có `throws`**.

Ví dụ với nhiều loại checked exception:

```java
static void load(Path file)
        throws IOException, java.text.ParseException {
    String raw = Files.readString(file);
    parseRequiredData(raw);
}
```

Đây là mảnh code có `parseRequiredData` do ứng dụng định nghĩa và các import liên quan. Khi thực hiện, phải đảm bảo `parseRequiredData` thật sự có hợp đồng có thể ném `ParseException`; đây chỉ là mẫu cho danh sách `throws`. Không nên khai báo một tập lỗi không liên quan chỉ để “dự phòng”.

### Checked và unchecked

| Nhóm | Ví dụ | Luật compile time |
| --- | --- | --- |
| Checked exception | `IOException`, `SQLException`, `ParseException` | Khi có thể thoát khỏi method, phải **catch hoặc declare (`throws`)**, với các ngoại lệ quy tắc ngôn ngữ liên quan |
| Unchecked exception | `IllegalArgumentException`, `NullPointerException`, `IllegalStateException` | Không bắt buộc catch/declare |
| `Error` | `OutOfMemoryError`, `StackOverflowError` | Không bắt buộc catch/declare; thường không nên phục hồi chung |

`throws` có thể khai báo cả unchecked exception nhằm tài liệu hóa, nhưng không tạo một nghĩa vụ compile-time mới cho caller như checked exception.

### `throws Exception` có phải lựa chọn tốt?

`throws Exception` có thể được dùng trong bài demo, test entrypoint hoặc adapter của thư viện legacy, nhưng API công khai nên ưu tiên nhóm checked exception **có ý nghĩa với người gọi**. Nếu mọi method chỉ `throws Exception`, caller khó biết cần phục hồi trường hợp nào và có xu hướng `catch (Exception)` quá rộng.

Không nên tuyên bố rằng một method `throws IOException` **chỉ có thể** ném `IOException`. Nó vẫn có thể ném unchecked exceptions như `NullPointerException`; `throws` không phải hệ thống kiểu kết quả loại trừ mọi lỗi khác.

## 5. `throw` và `throws` đặt cạnh nhau

Ví dụ:

```java
static String fetch(boolean available) throws IOException {
    if (!available) {
        throw new IOException("dependency offline");
    }
    return "OK";
}
```

Đây là method cần import `IOException`.

| Câu hỏi | `throw new IOException(...)` | `throws IOException` |
| --- | --- | --- |
| Xảy ra ở thời điểm nào? | Khi chạy đến câu lệnh trong body | Khi compiler phân tích chữ ký |
| Có tạo đối tượng exception? | Có: biểu thức `new IOException` | Không |
| Có khiến caller nhận exception ngay? | Khi nhánh được thực thi và không bị xử lý | Không, chỉ công bố khả năng |
| Có thể liệt kê nhiều loại bằng dấu phẩy? | Không: một câu lệnh throw ném một Throwable | Có: `throws IOException, ParseException` |
| Có cần dấu chấm phẩy? | Có, sau câu `throw` | Không có `;` riêng trước method body |
| Có thể dùng trong constructor? | Có, trong body | Có, ở chữ ký constructor |
| Có thể dùng ở một method call site? | Có nếu nằm trong block hợp lệ | Không: `throws` chỉ nằm ở declaration |

Một người đọc có thể thấy `throws IOException` trên chữ ký nhưng **không thấy `throw new IOException` trong method**: IOException có thể được phát sinh từ lời gọi sâu hơn như `Files.readString()`. Điều này hợp lệ vì ngoại lệ checked lan truyền qua call stack khi chưa được catch.

## 6. `catch`: nhận exception theo loại tương thích

Cú pháp:

```java
try {
    mayFail();
} catch (IOException ex) {
    handleIoError(ex);
}
```

Đây là mảnh code với import và các hàm ứng dụng. Khi code trong `try` ném một Throwable, Java chọn khối `catch` đầu tiên có kiểu parameter tương thích với kiểu exception thực tế.

Một `catch` có thể:

- **Phục hồi** với fallback hợp lệ theo nghiệp vụ.
- **Dịch lỗi** sang exception domain, giữ `cause`.
- **Ghi nhận trạng thái FAILED/CANCELLED** ở nơi sở hữu workflow.
- **Cleanup chuyên biệt** nếu `finally`/`try-with-resources` không phù hợp cho phần đó.
- **Ném lại** bằng `throw ex;` khi không thể xử lý tại tầng này.

Đừng nghĩ `catch` mặc định có nghĩa “lỗi đã được giải quyết”. Nếu handler chỉ in message rồi trả kết quả giả, trạng thái hệ thống có thể vẫn sai. Nếu `catch` ném exception mới, caller sẽ nhận exception đó, và `finally` (nếu có) vẫn được chạy theo quy tắc.

### Catch order: từ cụ thể đến tổng quát

```java
try {
    load();
} catch (FileNotFoundException ex) {
    handleMissing(ex);
} catch (IOException ex) {
    handleOtherIo(ex);
}
```

Đây là mảnh code có `load`/handlers và imports phù hợp. `FileNotFoundException` là subclass của `IOException`; phải đặt nó trước nếu cần handler riêng.

Thứ tự ngược sau **không biên dịch**:

```java
try {
    load();
} catch (IOException ex) {
    handleIo(ex);
} catch (FileNotFoundException ex) {
    handleMissing(ex); // Unreachable catch: đã bị IOException bắt.
}
```

Đây là **ví dụ cố tình sai**. Đừng chạy nó như một chương trình hoàn chỉnh.

## 7. Multi-catch và quy tắc không gộp cha–con

Từ Java 7, một handler có thể bắt nhiều loại exception không nằm trong quan hệ subtype với nhau:

```java
try {
    networkOperation();
} catch (SocketTimeoutException | ConnectException ex) {
    markTemporarilyUnavailable(ex);
}
```

Đây là mảnh code cần import `java.net.SocketTimeoutException`, `java.net.ConnectException` và các hàm ứng dụng. Hai loại được xử lý **giống nhau** nên multi-catch hợp lý.

Một ví dụ **không hợp lệ**:

```java
catch (Exception | IOException ex) {
    // Không biên dịch: IOException là subtype của Exception.
}
```

Trong multi-catch, parameter được xem là **implicitly final**; không thể gán lại biến `ex`. Java chọn handler dựa trên loại Throwable được ném, không chạy nhiều nhánh catch cho cùng một exception.

Multi-catch phù hợp khi **chính sách xử lý trùng nhau**, không chỉ vì muốn viết ít dòng. Nếu timeout có retry còn authentication failure không retry, nên tách xử lý.

## 8. `finally`: chạy khi rời try theo đường điều khiển thông thường

Cú pháp phổ biến:

```java
try {
    work();
} finally {
    cleanup();
}
```

Đây là mảnh code cần định nghĩa `work`/`cleanup`. `finally` có thể đi cùng `try` dù **không có `catch`**. Nó hữu ích để nhả lock hoặc thiết lập lại trạng thái nội bộ khi việc rời block xảy ra qua các đường thông thường.

Một ví dụ:

```java
lock.lock();
try {
    updateState();
} finally {
    lock.unlock();
}
```

Đây là mảnh code cần biến `lock` thuộc `java.util.concurrent.locks.Lock` và hàm `updateState`. `finally` bảo đảm nỗ lực `unlock()` trong quá trình rời block, nhưng **không tự rollback** các cập nhật đã thực hiện trước đó.

### Những tình huống thông thường mà finally được chạy

- Thân `try` chạy xong bình thường.
- Một `catch` xử lý lỗi và chạy xong.
- Thân `try` hoặc `catch` thực hiện `return`.
- Thân có `break` hoặc `continue` khiến control rời phạm vi `try`.
- Một exception không được bắt lan ra khỏi `try`.
- Một exception mới được ném từ `catch` trước khi thoát ra.

### Những giới hạn cần nhớ

Không được khẳng định “finally **luôn luôn** chạy dù bất cứ điều gì xảy ra”. Các trường hợp VM/process kết thúc đột ngột, bị kill, crash hoặc không bao giờ rời được khối (kẹt blocking vô hạn) có thể khiến `finally` không chạy. Ngoài ra, nếu **chính `finally` ném exception hoặc return**, nó có thể thay thế kết quả/lỗi đang được truyền đi.

## 9. `return` trong `try` và thứ tự chạy `finally`

Xem:

```java
static int getValue() {
    try {
        return 42;
    } finally {
        System.out.println("cleanup");
    }
}
```

Đây là method có thể đặt trong một class. Khi gọi `getValue()`, runtime chuẩn bị hoàn tất return nhưng thực thi `finally` trước. Vì vậy output `cleanup` xuất hiện trước khi caller nhận `42`.

Ví dụ cần phân biệt:

```java
static int snapshot() {
    int result = 1;
    try {
        return result;
    } finally {
        result = 2;
    }
}
```

Method trên trả **1**, vì giá trị return của primitive đã được xác định trước khi `finally` thay đổi biến local. Đây không phải lời hứa rằng mọi đối tượng được return là bất biến: nếu `finally` **mutate object** đã được tham chiếu, caller có thể quan sát object đã bị sửa.

### Không return từ finally

```java
static int misleading() {
    try {
        throw new IllegalStateException("failure");
    } finally {
        return 10;
    }
}
```

Đây là **mảnh anti-pattern**: nó có thể biên dịch nhưng return trong `finally` **che exception gốc**, khiến caller thấy số 10 dù công việc thất bại.

Tương tự, `finally` ném một exception mới có thể che exception đang được lan truyền. Chỉ để việc cleanup được thực hiện; khi cleanup cũng thất bại, cần bảo toàn lỗi gốc theo contract thay vì tự động thay thế.

## 10. `finally` khác `catch` ở điểm nào?

| Câu hỏi | `catch` | `finally` |
| --- | --- | --- |
| Có chọn loại exception không? | Có, dựa trên parameter type | Không |
| Có nhận Throwable như biến `ex`? | Có | Không |
| Chạy khi `try` hoàn tất bình thường? | Không | Có, nếu có `finally` và control rời bình thường |
| Có thể xử lý/nuốt lỗi gốc không? | Có | Không tự động, nhưng `return`/`throw` trong thân có thể che lỗi |
| Thường dùng cho | Recovery, translation, error mapping, reporting | Cleanup, release lock, cập nhật cờ/lifecycle |
| Có cần `catch` để tồn tại? | Cần `try`, không cần finally | Cần `try`, không cần catch |
| Nếu `catch` ném lại lỗi? | Handler ném lại | `finally` vẫn được thử chạy trước khi exception thoát |
| Có thay thế try-with-resources được không? | Không | Có thể dùng thủ công, nhưng dễ sai khi `close()` cũng ném |

`catch` và `finally` **không thay thế lẫn nhau**. Không bắt exception chỉ vì cần release resource, và không thêm `finally` chỉ để nuốt lỗi bằng `return`.

## 11. Bốn từ khóa phối hợp trong một luồng thực tế

Một mẫu phổ biến ở tầng xử lý I/O:

```java
static String readOrFallback(String path) {
    try {
        return readFile(path); // readFile có thể throws IOException.
    } catch (IOException ex) {
        return "DEFAULT";
    } finally {
        recordAttemptFinished();
    }
}
```

Đây là mảnh code cần các hàm `readFile`/`recordAttemptFinished` và import `IOException`. Nếu `readFile` chạy bình thường, `catch` bị bỏ qua, `finally` chạy rồi caller nhận nội dung. Nếu IOException xảy ra, handler trả fallback, `finally` chạy trước khi caller nhận `DEFAULT`.

**Điều kiện quan trọng:** fallback chỉ hợp lệ khi yêu cầu nghiệp vụ cho phép. Ví dụ cấu hình phụ có default là bình thường; lỗi đọc số dư tài khoản mà trả `0` là sai nghiêm trọng.

Với lỗi đầu vào như `IllegalArgumentException` không được handler `IOException` bắt, `finally` vẫn chạy, sau đó lỗi input lan tới caller. Điều này được xác nhận trong chương trình chạy độc lập ở phần 12.

## 12. Chương trình Java 17+ hoàn chỉnh và output được kiểm chứng

Ví dụ tích hợp sau chứng minh:

1. `throw` tạo `IllegalArgumentException` khi key sai.
2. `throws IOException` trên `read(...)` cho phép một checked exception thoát ra khi dependency giả lập offline.
3. `catch (IOException)` chuyển lỗi I/O thành fallback riêng, không nuốt lỗi validation.
4. `finally` tăng bộ đếm **cả khi thành công, khi bắt IOException và khi một unchecked exception lan ra**.
5. `try-with-resources` đóng tài nguyên theo thứ tự ngược và lưu lỗi đóng ở `getSuppressed()` khi thân cũng đã lỗi.
6. Nếu thân thành công nhưng resource close ném, lỗi close đầu tiên trở thành primary.

Tạo file **`ThrowThrowsCatchFinallyDemo.java`**:

```java
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public class ThrowThrowsCatchFinallyDemo {
    private static int finallyCount;
    private static final List<String> EVENTS = new ArrayList<>();

    static String read(String key) throws IOException {
        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException("key must not be blank");
        }
        if ("offline".equals(key)) {
            throw new IOException("source unavailable");
        }
        return "VALUE:" + key;
    }

    static String request(String key) {
        try {
            return read(key);
        } catch (IOException ex) {
            return "FALLBACK:" + ex.getClass().getSimpleName();
        } finally {
            finallyCount++;
        }
    }

    static final class Resource implements AutoCloseable {
        private final String name;
        Resource(String name) {
            this.name = name;
            EVENTS.add("open-" + name);
        }
        @Override
        public void close() throws IOException {
            EVENTS.add("close-" + name);
            throw new IOException("close-" + name + "-failed");
        }
    }

    static void bodyAndCloseFailure() throws IOException {
        try (Resource a = new Resource("A");
             Resource b = new Resource("B")) {
            EVENTS.add("body-failed");
            throw new IOException("body-failed");
        }
    }

    static void onlyCloseFailure() throws IOException {
        try (Resource a = new Resource("A");
             Resource b = new Resource("B")) {
            EVENTS.add("body-ok");
        }
    }

    static String suppressedMessages(Throwable ex) {
        List<String> messages = new ArrayList<>();
        for (Throwable suppressed : ex.getSuppressed()) {
            messages.add(suppressed.getMessage());
        }
        return String.join(",", messages);
    }

    static void check(boolean condition, String reason) {
        if (!condition) throw new AssertionError(reason);
    }

    public static void main(String[] args) {
        String success = request("A");
        String fallback = request("offline");
        check("VALUE:A".equals(success), "success");
        check("FALLBACK:IOException".equals(fallback), "fallback");
        System.out.println("RETURN: " + success);
        System.out.println("CATCH: " + fallback);

        try {
            request("");
            throw new AssertionError("expected validation exception");
        } catch (IllegalArgumentException ex) {
            check("key must not be blank".equals(ex.getMessage()), "validation");
            System.out.println("THROW_UNCHECKED: " + ex.getMessage());
        }
        check(finallyCount == 3, "finally must run three times");
        System.out.println("FINALLY_COUNT: " + finallyCount);

        EVENTS.clear();
        try {
            bodyAndCloseFailure();
            throw new AssertionError("expected body failure");
        } catch (IOException ex) {
            check("body-failed".equals(ex.getMessage()), "body primary");
            check("close-B-failed,close-A-failed".equals(suppressedMessages(ex)),
                    "body suppressed");
            System.out.println("BODY_PRIMARY: " + ex.getMessage());
            System.out.println("BODY_SUPPRESSED: " + suppressedMessages(ex));
            System.out.println("BODY_EVENTS: " + String.join(",", EVENTS));
        }

        EVENTS.clear();
        try {
            onlyCloseFailure();
            throw new AssertionError("expected close failure");
        } catch (IOException ex) {
            check("close-B-failed".equals(ex.getMessage()), "close primary");
            check("close-A-failed".equals(suppressedMessages(ex)),
                    "close suppressed");
            System.out.println("CLOSE_PRIMARY: " + ex.getMessage());
            System.out.println("CLOSE_SUPPRESSED: " + suppressedMessages(ex));
            System.out.println("CLOSE_EVENTS: " + String.join(",", EVENTS));
        }
        System.out.println("CHECKS: PASS");
    }
}
```

**Biên dịch/chạy với JDK 17 trở lên** (không cần thư viện ngoài):

```bash
javac -encoding UTF-8 ThrowThrowsCatchFinallyDemo.java
java ThrowThrowsCatchFinallyDemo
```

**Standard output đã kiểm chứng:**

```text
RETURN: VALUE:A
CATCH: FALLBACK:IOException
THROW_UNCHECKED: key must not be blank
FINALLY_COUNT: 3
BODY_PRIMARY: body-failed
BODY_SUPPRESSED: close-B-failed,close-A-failed
BODY_EVENTS: open-A,open-B,body-failed,close-B,close-A
CLOSE_PRIMARY: close-B-failed
CLOSE_SUPPRESSED: close-A-failed
CLOSE_EVENTS: open-A,open-B,body-ok,close-B,close-A
CHECKS: PASS
```

Output này đến từ chương trình đã biên dịch/chạy bằng `javac`/`java` trên JDK hiện đại và chỉ sử dụng cú pháp/API hợp lệ của Java 17. Các hàm `check` ném `AssertionError` nếu một điều kiện trái kỳ vọng; vì vậy dòng `CHECKS: PASS` chỉ xuất hiện sau khi các nhánh kiểm tra trong demo hoàn tất.

### Phân tích kết quả

- `RETURN: VALUE:A`: không có exception; `read("A")` trả dữ liệu bình thường, `catch` không chạy.
- `CATCH: FALLBACK:IOException`: `read("offline")` **thực sự `throw new IOException`**; `request` bắt đúng checked exception và trả fallback theo contract của bài demo.
- `THROW_UNCHECKED`: key rỗng làm `IllegalArgumentException` lan qua `request` vì ở đó chỉ có `catch(IOException)`; caller ngoài nhận và kiểm tra.
- `FINALLY_COUNT: 3`: ba lần gọi `request` đều đi qua `finally` mặc dù đường trả kết quả/lỗi khác nhau.
- `BODY_PRIMARY` và `BODY_SUPPRESSED`: exception của thân được giữ là primary; lỗi đóng B, A nằm trong suppressed theo thứ tự ngược khi đóng.
- `CLOSE_PRIMARY` và `CLOSE_SUPPRESSED`: thân thành công, B đóng trước và thất bại nên nó trở thành primary; lỗi đóng A là suppressed.
- `BODY_EVENTS` / `CLOSE_EVENTS`: mở A rồi B, đóng B rồi A (LIFO). Những phép đóng vẫn được cố thực hiện sau lỗi đóng đầu tiên.

Ví dụ này dùng `Resource.close()` luôn ném để minh họa. Không nên làm vậy trong một resource production: lỗi đóng chỉ nên được ném khi cleanup thật sự không hoàn tất theo contract của tài nguyên.

## 13. Tại sao try-with-resources thường tốt hơn tự viết finally để close?

Mẫu thủ công thường thấy:

```java
InputStream input = Files.newInputStream(path);
try {
    process(input);
} finally {
    input.close();
}
```

Đây là mảnh code trong method phù hợp với `IOException`, đã có `Path path` và `process` cùng imports. Nếu `process(input)` ném một exception, rồi `input.close()` cũng ném, exception close có thể **che lỗi body**, khiến nguyên nhân ban đầu khó nhận ra.

Cú pháp được khuyến nghị khi tài nguyên triển khai `AutoCloseable`:

```java
try (InputStream input = Files.newInputStream(path)) {
    process(input);
}
```

Mảnh code tương ứng cần imports và contract method giống ví dụ trên. Với `try-with-resources`:

- Resource được khởi tạo từ trái sang phải.
- Khi rời scope, resource đã khởi tạo được đóng từ phải sang trái.
- Nếu body đã ném Throwable, lỗi đóng thứ cấp thường nằm trong `Throwable.getSuppressed()` của primary.
- Nếu body thành công nhưng close đầu tiên ném, lỗi close đó có thể là primary.
- Nếu initializer của resource sau thất bại, những resource trước đã khởi tạo vẫn được thử đóng.
- Resource reference null (hợp lệ về ngữ nghĩa trong một số trường hợp) không bị gọi `close()`.

`try-with-resources` không thay thế transaction/rollback nghiệp vụ. Đóng connection không đồng nghĩa mọi ghi trước đó đã được hoàn tác; semantics của transaction và driver phải được kiểm tra riêng.

### Lưu ý về `throws` của `AutoCloseable.close()`

`AutoCloseable.close()` được khai báo `throws Exception`, còn `Closeable.close()` (trong `java.io`) khai báo hẹp hơn với `IOException`. Khi viết method dùng một resource có checked exception từ `close()`, compiler cần thấy lỗi đó được catch hoặc declare.

Không nên tuyên bố chỉ vì body không ném mà method không thể ném: `close()` vẫn có thể ném.

## 14. `throw new`, `throw ex` và bọc exception có cause

Ba hình thức dễ nhầm:

```java
throw new IllegalArgumentException("bad parameter");
```

Đây là mảnh code: **tạo và ném instance mới**.

```java
catch (IOException ex) {
    throw ex;
}
```

Mảnh code nằm trong cấu trúc `try/catch` và chữ ký phù hợp: **ném lại đúng instance đã bắt**.

```java
catch (IOException ex) {
    throw new RepositoryUnavailableException("repository unavailable", ex);
}
```

Đây là mảnh code cần định nghĩa `RepositoryUnavailableException` có constructor nhận `Throwable cause`. Nó **dịch lỗi** sang loại có ý nghĩa ở boundary, đồng thời giữ lỗi nguồn thông qua `getCause()`.

Đừng làm:

```java
catch (IOException ex) {
    throw new RuntimeException("operation failed");
}
```

mà không có lý do, vì nó làm mất cause và đường đi của lỗi gốc. Đồng thời, dù đã giữ cause, **không tự in toàn bộ message/cause ra API response**: exception của dependency có thể chứa URL, token, credential hoặc dữ liệu cá nhân.

Với exception translation, chọn loại lỗi có ý nghĩa nghiệp vụ chứ không bọc mọi thứ thành `RuntimeException` chung.

## 15. Một `try` có bắt buộc phải có cả catch và finally không?

**Không.** Những cấu trúc sau đều hợp lệ:

**Chỉ try/catch:**

```java
try {
    work();
} catch (KnownFailure ex) {
    recover(ex);
}
```

**Chỉ try/finally:**

```java
try {
    work();
} finally {
    cleanup();
}
```

**Try/catch/finally:**

```java
try {
    work();
} catch (KnownFailure ex) {
    recover(ex);
} finally {
    cleanup();
}
```

**Try-with-resources:**

```java
try (Resource resource = openResource()) {
    workWith(resource);
}
```

Tất cả đều là mảnh code khái niệm, cần định nghĩa loại `KnownFailure`, `Resource` và các phương thức tương ứng. Với kiểu `try` truyền thống, phải có ít nhất **một `catch` hoặc một `finally`**. Với `try-with-resources` có resource specification, không bắt buộc có catch/finally tường minh.

Vị trí `finally` nếu có luôn **sau** các `catch` của cùng câu lệnh. Không đặt `catch` sau `finally`. Một khối `try` có thể có nhiều `catch`, nhưng chỉ một `finally` gắn trực tiếp với nó; muốn cleanup nhiều cấp thì dùng nhiều scope hoặc helper.

## 16. Checked exception từ method gọi sâu: không cần ném lại thủ công

```java
static void copy(Path source, Path destination) throws IOException {
    Files.copy(source, destination);
}
```

Đây là method cần imports từ `java.nio.file` và `java.io`. `Files.copy` có thể ném checked exception, nên `copy` có thể đơn giản khai báo `throws IOException` để caller quyết định xử lý. Không cần:

```java
static void copy(Path source, Path destination) throws IOException {
    try {
        Files.copy(source, destination);
    } catch (IOException ex) {
        throw ex;
    }
}
```

vì khối catch này **không làm thêm gì** so với để lỗi lan truyền. Catch chỉ hữu ích khi có xử lý như rollback thuộc quyền sở hữu, thêm context an toàn, chuyển loại exception hoặc ghi trạng thái có ý nghĩa.

Điểm quan trọng: `throws` **không chủ động chuyển checked thành unchecked**, cũng không bảo đảm một lỗi sẽ được bắt. Nó chỉ tham gia hợp đồng compile time và cho exception tiếp tục lan truyền nếu xảy ra.

## 17. Rethrow và precise rethrow

Java cho phép ném lại parameter của catch:

```java
try {
    mayThrowFileOrSql();
} catch (Exception ex) {
    record(ex);
    throw ex;
}
```

Đây là mảnh code với method `mayThrowFileOrSql` có hợp đồng checked exception và `record` tự định nghĩa. Với Java 7+, compiler có thể dùng **phân tích precise rethrow** để suy ra tập kiểu exception checked mà statement có thể ném nếu biến catch parameter effectively final (không bị gán lại), thay vì luôn bắt buộc `throws Exception`.

Ví dụ nếu `mayThrowFileOrSql()` chỉ có thể ném `IOException` và `SQLException`, method bao ngoài có thể khai báo hai loại đó khi điều kiện precise rethrow thỏa mãn. Ngược lại, nếu gán lại `ex`, phân tích có thể không còn đủ chính xác theo quy tắc ngôn ngữ.

Đây là đặc điểm **compile-time**. Ở runtime `throw ex` vẫn ném đúng object. Tuy nhiên một `catch(Exception)` chỉ để rethrow không có hành động thêm thường vẫn không cần thiết; đừng thêm khối catch chỉ để thử compiler feature.

## 18. `catch(Exception)` và `catch(Throwable)` khác nhau

| Handler | Bao gồm | Nguy cơ nếu dùng đại trà |
| --- | --- | --- |
| `catch (Exception ex)` | Checked exceptions và `RuntimeException` | Nuốt bug, che `InterruptedException`, biến lỗi thành kết quả giả |
| `catch (Throwable t)` | Toàn bộ `Exception` **và `Error` | Có thể che `OutOfMemoryError`/`StackOverflowError` và để ứng dụng chạy trong trạng thái không đáng tin |
| `catch (IOException ex)` | Nhóm I/O | Thường hẹp hơn, nhưng vẫn cần chính sách hợp lệ |
| `catch (InterruptedException ex)` | Tín hiệu ngắt blocking operation | Cần truyền tiếp hoặc restore flag/rời task theo contract |

Không phải `catch(Exception)` luôn sai: ở HTTP boundary hoặc job runner cuối, một fallback chung cho lỗi chưa dự kiến có thể hợp lý sau các handler cụ thể. Điều không nên làm là **sao chép catch rộng tại mọi tầng và nuốt lỗi**.

`catch(Throwable)` có thể tồn tại trong framework hoặc test harness để quan sát thất bại của một đơn vị thực thi, nhưng không nên xem đó là cách “phục hồi mọi Error”. Một VM thiếu tài nguyên có thể không đủ khả năng thực thi logic báo lỗi phức tạp.

## 19. Đừng nuốt InterruptedException trong catch rộng

Ví dụ tác vụ chạy trong thread pool:

```java
while (true) {
    try {
        process(queue.take());
    } catch (Exception ex) {
        logger.warn("retry", ex);
    }
}
```

Đây là **mảnh anti-pattern** có `queue`, `process` và `logger` do ứng dụng định nghĩa. `BlockingQueue.take()` có thể ném `InterruptedException`, mà nó là subclass của `Exception`. Catch chung có thể nuốt tín hiệu hủy, làm worker tiếp tục chạy.

Nếu method có thể khai báo:

```java
void receive(BlockingQueue<Job> queue) throws InterruptedException {
    process(queue.take());
}
```

Đây là mảnh code cần import `BlockingQueue`, định nghĩa `Job`/`process`. Truyền tiếp checked interruption thường rõ.

Trong `Runnable.run()` không được ném checked `InterruptedException`:

```java
@Override
public void run() {
    try {
        process(queue.take());
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return;
    } finally {
        releaseResources();
    }
}
```

Đây là mảnh trong class ứng dụng có queue/cleanup. Khi đã bắt, restore flag và thoát đường thực thi thích hợp; không restore rồi quay lại vòng `while(true)` bất chấp yêu cầu ngắt, vì có thể tạo vòng lặp nóng.

Một tầng sở hữu toàn bộ giao thức interruption có thể xử lý và tiêu thụ tín hiệu có chủ đích, nhưng đó phải là quyết định rõ ràng, không phải side effect của catch quá rộng.

## 20. `finally` không đồng nghĩa rollback và không tự đảm bảo close thành công

Một anti-pattern:

```java
try {
    chargeCustomer(); // Có thể đã commit.
    sendReceipt();    // Có thể lỗi.
    return true;
} finally {
    logFinished();
}
```

Đây là mảnh code có các hàm nghiệp vụ đã định nghĩa. `finally` chỉ gọi `logFinished()` khi rời. Nó **không tự hoàn tác** việc trừ tiền. Nếu `chargeCustomer()` đã thành công và `sendReceipt()` lỗi, caller có thể nhận exception dù tiền đã bị trừ.

Tương tự:

- `lock.unlock()` trong finally nhả lock, không undo state đã mutate.
- `connection.close()` không được mặc định tương đương transaction rollback trên mọi driver/pool.
- `future.cancel(true)` là yêu cầu hủy, không cam kết mọi side effect trước đó đã biến mất.
- `Files.delete(...)` trong finally có thể tự thất bại hoặc xóa sai nếu path không được quản lý cẩn thận.

Nếu cần rollback, xác định transaction owner, điều kiện commit/rollback, trạng thái chưa xác định và cách bảo toàn lỗi rollback. Với nhiều hệ thống, dùng idempotency, transactional outbox hoặc compensation khi phù hợp.

## 21. Bảng quyết định: dùng từ khóa nào?

| Bạn đang cần… | Công cụ thường phù hợp | Ví dụ cách tư duy |
| --- | --- | --- |
| Từ chối tham số sai ngay lập tức | `throw` | `throw new IllegalArgumentException(...)` |
| Báo caller rằng method có thể thất bại vì I/O | `throws` | `readFile(...) throws IOException` |
| Xử lý lỗi I/O bằng fallback hợp lệ | `catch (IOException ex)` | Chỉ dùng fallback có nghĩa theo contract |
| Dịch lỗi adapter sang domain error | `catch` + `throw new ...(..., ex)` | Giữ `cause` |
| Chỉ chuyển tiếp lỗi I/O từ method trung gian | `throws IOException` | Không cần catch rồi rethrow vô nghĩa |
| Giải phóng lock dù thân thất bại | `finally` | `unlock()` trong finally |
| Đóng resource `AutoCloseable`, giữ lỗi close | `try-with-resources` | Tự close, hỗ trợ suppressed |
| Bắt nhiều lỗi với chung cách xử lý | Multi-catch | `catch (A | B ex)` cho hai loại độc lập |
| Báo lỗi bất ngờ ở API boundary | Fallback catch chuyên trách | Trả public error code, không leak stack |
| Tác vụ bị interrupt trong khi chờ | `catch(InterruptedException)` hoặc `throws` | Truyền tiếp hoặc restore và dừng |
| Phục hồi sau partial commit | Không chỉ dùng bốn keyword | Transaction/idempotency/compensation |
| Giữ tất cả lỗi từ try và close | `try-with-resources` + `getSuppressed()` | Body primary, close suppressed khi phù hợp |

Bảng là định hướng, không thay cho hợp đồng của API đang dùng. Lỗi validation, lỗi domain, lỗi phụ thuộc và cancellation có chính sách rất khác nhau, dù tất cả đều có thể biểu diễn bằng Throwable.

## 22. Lỗi cú pháp và lỗi suy luận thường gặp

| Sai lầm | Vấn đề | Sửa theo hướng nào |
| --- | --- | --- |
| Viết `throws new IOException(...)` | `throws` nhận **kiểu**, không nhận instance | Dùng `throw new IOException(...)` trong body |
| Viết `throw IOException;` | `throw` cần **biểu thức Throwable**, không phải tên class | Tạo/nhận instance |
| Viết `throw "error";` | `String` không là `Throwable` | Ném kiểu exception phù hợp |
| Nghĩ `throws` làm exception xuất hiện mỗi lần gọi | Declaration không tự ném | Tìm đường `throw` hoặc lời gọi ném lỗi thật |
| Nghĩ `catch(IOException)` bắt cả `NullPointerException` | Không cùng nhánh | Catch đúng loại cần xử lý, để bug lan ra |
| Đặt `catch(IOException)` sau `catch(Exception)` | Handler subclass không thể tới | Bắt cụ thể trước |
| Dùng `catch(Exception | IOException)` | Multi-catch có quan hệ cha–con | Chỉ gộp các loại độc lập |
| Bỏ `catch`/`finally` khỏi `try` truyền thống | Cú pháp `try { }` đơn lẻ không hợp lệ | Thêm catch/finally hoặc dùng TWR |
| Nghĩ finally chạy ngay **trước** catch | Sai thứ tự | Với exception phù hợp: catch rồi finally |
| Return trong finally để “chắc chắn trả kết quả” | Có thể che exception/return từ try | Không return trong finally |
| Exception mới trong finally che lỗi chính | Mất chẩn đoán primary | Dùng TWR hoặc bảo toàn lỗi gốc |
| Catch IOException rồi trả success giả | Trạng thái nghiệp vụ sai | Fallback chỉ khi hợp đồng cho phép |
| Bọc exception mới mà bỏ cause | Mất lỗi gốc | Truyền `ex` vào constructor nhận cause |
| Catch Exception rồi nuốt interrupt | Task không dừng | Xử lý `InterruptedException` riêng |
| Tin finally luôn chạy kể cả process crash | Không có bảo đảm tuyệt đối | Cleanup theo lifecycle + cơ chế khôi phục ngoài process |
| Tin close đồng nghĩa rollback | Side effect có thể đã commit | Kiểm tra transaction semantics |
| Ghi Throwable message trực tiếp ra client | Có thể lộ secrets/PII | Error code an toàn + log theo policy |

## 23. Bài tập tự luyện và đáp án định hướng

### Câu 1 — Xác định kết quả

```java
static int example() {
    try {
        return 5;
    } finally {
        System.out.println("F");
    }
}
```

Khi gọi `System.out.println(example());`, chương trình in `F` rồi `5`. **Vì sao?** Giá trị return đã chuẩn bị nhưng `finally` được chạy trước khi method hoàn tất.

### Câu 2 — Phân biệt hai lỗi

```java
static void run() throws IOException {
    throw new IOException("io");
}
```

**`throws IOException` có phải nguyên nhân runtime ném lỗi?** Không: nguyên nhân runtime là câu `throw new IOException("io")` được thực thi. `throws` cho compiler/caller biết một checked exception có thể thoát khỏi method.

### Câu 3 — Đổi thứ tự catch

```java
try {
    read();
} catch (Exception ex) {
    handleGeneric(ex);
} catch (IOException ex) {
    handleIo(ex);
}
```

**Có biên dịch không?** Không, vì handler `Exception` trước đã bắt được `IOException`; handler IOException sau unreachable. Sửa bằng cách đặt handler IOException trước hoặc bỏ handler riêng nếu cùng chính sách.

### Câu 4 — Cuối cùng có che lỗi?

```java
static int example() {
    try {
        throw new RuntimeException("failure");
    } finally {
        return 99;
    }
}
```

**Caller nhận gì?** Method trả 99 và exception gốc bị che. Đây là lý do **tránh return trong finally**.

### Câu 5 — Khi thân và close đều ném

Một `try-with-resources` mở A rồi B; thân ném `IOException("body")`; B.close và A.close cùng ném. **Primary là gì?** Lỗi body. **Đóng theo thứ tự nào?** B rồi A. **Lỗi close nằm ở đâu?** Trong `primary.getSuppressed()` theo thứ tự phát sinh.

Các mảnh bài tập được đặt trong ngữ cảnh method/class phù hợp và thêm imports khi cần. Chỉ chương trình ở phần 12 được thiết kế thành một file Java độc lập hoàn chỉnh.

## 24. Checklist tra cứu cuối

- [ ] Phân biệt **`throw` (hành động)** và **`throws` (khai báo)**.
- [ ] Khi dùng checked exception, method có handler phù hợp hoặc `throws` đúng contract.
- [ ] Catch dựa trên loại Throwable thực tế; subclass trước superclass.
- [ ] Không bắt Exception/Throwable quá rộng chỉ để làm biến mất lỗi.
- [ ] Nếu dịch exception, chọn mã/loại đúng và giữ cause khi cần.
- [ ] `finally` chạy trên đường rời thông thường, **không phải bảo đảm tuyệt đối bất chấp JVM/process**.
- [ ] Không `return` trong `finally` và tránh làm exception từ finally che primary.
- [ ] Với `AutoCloseable`, ưu tiên `try-with-resources` và kiểm tra `getSuppressed()` khi có lỗi close.
- [ ] Không đánh đồng exception được ném với “chưa có side effect”.
- [ ] Không log trực tiếp secrets, token, PII vào exception message hoặc phản hồi client.
- [ ] Phân biệt interruption/cancellation với lỗi nghiệp vụ, nhất là trong worker.
- [ ] Kiểm thử cả success, checked failure, unchecked failure, catch mapping, finally, close failure và suppressed errors.

**Tóm lại:** `throw` làm lỗi **xảy ra**, `throws` mô tả lỗi checked **có thể thoát**, `catch` quyết định **có xử lý loại lỗi đó tại tầng này không**, và `finally` đảm nhận **bước hoàn tất/dọn dẹp khi rời khối**. Sử dụng đúng không chỉ là đúng cú pháp, mà còn là giữ nguyên nhân, không che trạng thái thất bại và không tạo thành công giả.
