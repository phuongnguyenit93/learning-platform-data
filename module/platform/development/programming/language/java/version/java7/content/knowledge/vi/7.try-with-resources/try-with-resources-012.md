# Kiểm thử cả đường đi thành công và đường đi thất bại của `try-with-resources` trong Java

## 1. Mục tiêu bài học

`try-with-resources` (có từ Java 7, vẫn được sử dụng trong Java 17+) tự động đóng những tài nguyên triển khai `AutoCloseable` khi thoát khối `try`. Cú pháp đúng **chưa đủ**: kiểm thử phải chứng minh rằng tài nguyên được đóng đúng cả khi công việc thành công lẫn khi có ngoại lệ ở bất kỳ giai đoạn nào.

Những điều cần chứng minh:

1. **Đường đi thành công:** mở tài nguyên, sử dụng, đóng **đúng một lần theo đường thực thi đang kiểm thử** và trả kết quả bình thường.
2. **Lỗi trong thân `try`:** vẫn thực hiện đóng tài nguyên, không nuốt exception chính.
3. **Lỗi trong `close()`:** exception từ thao tác đóng không bị bỏ qua một cách âm thầm.
4. **Cả thân `try` lẫn `close()` đều lỗi:** exception từ thân `try` là lỗi chính; lỗi từ `close()` được giữ trong `getSuppressed()`.
5. **Nhiều tài nguyên:** được đóng **theo thứ tự ngược** với thứ tự khai báo/khởi tạo thành công, kể cả nếu một `close()` ném lỗi.
6. **Lỗi khi khởi tạo tài nguyên:** các tài nguyên đã mở thành công trước đó vẫn được đóng; thân `try` không chạy.
7. **Các cách thoát khác:** `return`, tài nguyên `null` và thời điểm `catch`/`finally` cũng cần kiểm thử theo rủi ro của mã nguồn.
8. **Kiểm tra cả trạng thái lẫn exception:** không chỉ hỏi "có ném lỗi hay không", mà còn kiểm tra thứ tự sự kiện, đối tượng exception chính và suppressed exception.

Bài này trình bày ma trận kiểm thử và một **chương trình Java 17+ chạy độc lập, không cần JUnit hay thư viện ngoài**. Khi triển khai dự án thực tế, có thể chuyển các phép kiểm tra sang framework như JUnit Jupiter.

## 2. Nắm đúng cơ chế trước khi viết test

Cú pháp cơ bản:

```java
try (Resource resource = openResource()) {
    use(resource);
}
```

Đây là **mã minh họa**; `Resource` phải có kiểu phù hợp với `AutoCloseable`, còn `openResource()` và `use(...)` là những phương thức do ứng dụng định nghĩa.

Tóm tắt thứ tự:

1. **Khởi tạo** các tài nguyên từ trái sang phải.
2. **Chạy thân `try`** nếu mọi initializer cần thiết kết thúc bình thường.
3. **Đóng** những tài nguyên đã khởi tạo, từ phải sang trái.
4. Nếu `try-with-resources` có `catch`/`finally`, các handler đó chạy **sau khi** cơ chế đóng tài nguyên của khối đã hoàn tất.
5. Truyền kết quả bình thường, giá trị `return` hoặc exception theo quy tắc của ngôn ngữ.

Có hai đặc điểm hay bị kiểm thử thiếu:

- **Lỗi chính và lỗi phụ:** khi thân `try` đã ném exception A và `close()` ném exception B, A tiếp tục được ném và B nằm trong `A.getSuppressed()`. Không kiểm tra suppressed exceptions có thể bỏ sót lỗi dọn dẹp.
- **Thứ tự đóng và trạng thái:** với `try (A a = ...; B b = ...)`, `b.close()` xảy ra trước `a.close()`. Nếu việc khởi tạo `b` thất bại, `a` vẫn cần được đóng; không được giả định rằng thân `try` đã chạy.

`try-with-resources` không đảm bảo mọi implementer đều có `close()` idempotent. Việc gọi `close()` thủ công trong thân `try` rồi để cơ chế tự đóng thêm lần nữa có thể gây lỗi. Những kiểm thử dưới đây dùng tài nguyên giả để thấy chính xác lời gọi đóng do cơ chế `try-with-resources` thực hiện.

## 3. Thiết kế ma trận kiểm thử

| Kịch bản | Lỗi cần giả lập | Điều phải kiểm tra |
| --- | --- | --- |
| 1. Thành công | Không có | `open → use → close`; không có exception |
| 2. Thân `try` lỗi | Ném một `IOException` xác định trong thân | Vẫn `close`; exception được bắt ở caller **chính là** đối tượng đã ném |
| 3. Chỉ `close()` lỗi | Thân bình thường, `close()` ném `IOException` | Exception chính có message của `close`; không có suppressed do lỗi phụ |
| 4. Thân và `close` đều lỗi | Ném lỗi ở hai nơi | Exception chính vẫn là lỗi thân; đúng một suppressed exception từ `close` |
| 5. Hai tài nguyên thành công | Không có | Mở A rồi B; đóng B rồi A |
| 6. Hai `close` đều lỗi | Cả hai lần đóng ném lỗi | B (đóng trước) là exception chính; lỗi đóng A nằm trong suppressed |
| 7. Lỗi khởi tạo tài nguyên thứ hai | Mở A thành công; mở B ném lỗi; `close(A)` cũng lỗi | Thân không chạy; exception khởi tạo B là chính; lỗi đóng A bị suppressed |
| 8. `return` trong thân `try` | Không có lỗi | `close` xảy ra **trước** khi caller nhận giá trị trả về |
| 9. Một resource là `null` | Resource `null` kèm một resource thật | Thân vẫn chạy; không gọi `close()` cho `null`; resource thật vẫn được đóng |
| 10. Có `catch` và `finally` | Lỗi trong thân `try` | Thứ tự là đóng resource → `catch` → `finally` |

Các test này **kiểm tra trực tiếp những nhánh quan trọng của đặc tả**, không chỉ khẳng định một vài câu lệnh được thực thi. Trong ứng dụng thực tế, hãy bổ sung các nhánh theo hợp đồng của tài nguyên đang dùng: timeout, lỗi mở kết nối, lỗi ghi file, đóng mạng, rollback, tài nguyên nhiều lớp, hay kết quả trả về khi `close` cũng lỗi.

**Không phải mọi API `close()` đều giống nhau:** `AutoCloseable.close()` có thể khai báo `throws Exception`, còn `Closeable.close()` khai báo `throws IOException`. Test phải mô phỏng những loại exception thực sự được API mục tiêu công bố, không tự giả định mọi resource luôn chỉ ném `IOException`.

## 4. Tạo tài nguyên kiểm thử có thể quan sát

Một test double (tài nguyên giả) hữu ích cần có:

- Tên định danh như A, B để kiểm chứng thứ tự.
- Danh sách sự kiện `List<String>`, ghi lại `open`, `use`, `close`.
- Cờ giả lập lỗi khi **mở** và khi **đóng**.
- Phương thức `close()` thực sự ghi sự kiện rồi mới tùy chọn ném exception.
- Trạng thái đóng hoặc hành vi phát hiện sử dụng sau khi đóng, khi bài toán yêu cầu.
- Không phụ thuộc file hệ thống thật, network, thời gian ngủ, thread scheduling hay stdout của logger.

Ý tưởng:

```java
static final class Resource implements AutoCloseable {
    private final String name;
    private final List<String> events;
    private final boolean failOnClose;
    private boolean closed;

    Resource(String name, List<String> events, boolean failOnClose) {
        this.name = name;
        this.events = events;
        this.failOnClose = failOnClose;
    }

    void use() {
        if (closed) {
            throw new IllegalStateException("already closed");
        }
        events.add("use:" + name);
    }

    @Override
    public void close() throws IOException {
        events.add("close:" + name);
        closed = true;
        if (failOnClose) {
            throw new IOException("close:" + name);
        }
    }
}
```

Đây là **thành phần được đặt bên trong lớp kiểm thử đầy đủ ở mục 5**, không phải tệp độc lập. Một factory `open(...)` được thiết kế riêng sẽ ghi sự kiện mở và cho phép ném lỗi trước khi tạo đối tượng, nhằm kiểm thử lỗi **khởi tạo resource**.

**Vì sao phải ghi sự kiện thay vì chỉ kiểm tra cờ `closed`?** Cờ chỉ cho biết trạng thái cuối; nó không chứng minh được **thứ tự** giữa hai lần đóng, không phát hiện việc `close` bị gọi hai lần nếu trạng thái đã là `true`, và không chỉ ra `catch` chạy trước hay sau cleanup. Chuỗi sự kiện là bằng chứng trực tiếp cho các kiểm thử này.

## 5. Chương trình Java 17+ đầy đủ: 10 bài kiểm thử chạy độc lập

Lưu nguyên đoạn sau vào tệp **`TryWithResourcesPathTests.java`**. Mỗi hàm kiểm thử độc lập dùng một danh sách sự kiện mới, vì vậy không bị ảnh hưởng bởi test khác. Chương trình dùng phương thức `check(...)` ném `AssertionError`, **không phụ thuộc tùy chọn JVM `-ea`** (khác với lệnh `assert` nguyên thủy của Java).

```java
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public final class TryWithResourcesPathTests {

    @FunctionalInterface
    interface Action {
        void run() throws Exception;
    }

    static final class Resource implements AutoCloseable {
        private final String name;
        private final List<String> events;
        private final boolean failOnClose;
        private boolean closed;

        Resource(String name, List<String> events, boolean failOnClose) {
            this.name = name;
            this.events = events;
            this.failOnClose = failOnClose;
        }

        void use() {
            if (closed) {
                throw new IllegalStateException("already closed");
            }
            events.add("use:" + name);
        }

        @Override
        public void close() throws IOException {
            events.add("close:" + name);
            closed = true;
            if (failOnClose) {
                throw new IOException("close:" + name);
            }
        }
    }

    static Resource open(String name, List<String> events,
                         boolean failOnOpen, boolean failOnClose)
            throws IOException {
        events.add("open:" + name);

        if (failOnOpen) {
            throw new IOException("init:" + name);
        }

        return new Resource(name, events, failOnClose);
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void checkEvents(List<String> actual, String... expected) {
        check(actual.equals(List.of(expected)),
                "events " + actual + " != " + List.of(expected));
    }

    static IOException expectIo(Action action) throws Exception {
        try {
            action.run();
        } catch (IOException e) {
            return e;
        }
        throw new AssertionError("Expected IOException");
    }

    // 1. Đường đi thành công: mở, sử dụng, đóng.
    static void success() throws Exception {
        List<String> events = new ArrayList<>();

        try (Resource resource = open("A", events, false, false)) {
            resource.use();
        }

        checkEvents(events, "open:A", "use:A", "close:A");
    }

    // 2. Thân try lỗi: vẫn đóng; lỗi gốc không bị thay thế.
    static void bodyFailure() throws Exception {
        List<String> events = new ArrayList<>();
        IOException original = new IOException("body");

        IOException caught = expectIo(() -> {
            try (Resource resource = open("A", events, false, false)) {
                resource.use();
                throw original;
            }
        });

        check(caught == original, "body exception must stay primary");
        check(caught.getSuppressed().length == 0,
                "unexpected suppressed");
        checkEvents(events, "open:A", "use:A", "close:A");
    }

    // 3. Thân thành công nhưng close lỗi: lỗi close đi ra caller.
    static void closeFailure() throws Exception {
        List<String> events = new ArrayList<>();

        IOException caught = expectIo(() -> {
            try (Resource resource = open("A", events, false, true)) {
                resource.use();
            }
        });

        check(caught.getMessage().equals("close:A"),
                "wrong close failure");
        check(caught.getSuppressed().length == 0,
                "unexpected suppressed");
        checkEvents(events, "open:A", "use:A", "close:A");
    }

    // 4. Cả thân và close lỗi: thân là primary, close là suppressed.
    static void bodyAndCloseFailure() throws Exception {
        List<String> events = new ArrayList<>();
        IOException body = new IOException("body");

        IOException caught = expectIo(() -> {
            try (Resource resource = open("A", events, false, true)) {
                throw body;
            }
        });

        check(caught == body, "body should be primary");
        check(caught.getSuppressed().length == 1,
                "need one suppressed");
        check(caught.getSuppressed()[0].getMessage().equals("close:A"),
                "wrong suppressed close");
        checkEvents(events, "open:A", "close:A");
    }

    // 5. Hai tài nguyên: đóng theo thứ tự ngược.
    static void closeOrder() throws Exception {
        List<String> events = new ArrayList<>();

        try (Resource first = open("A", events, false, false);
             Resource second = open("B", events, false, false)) {
            first.use();
            second.use();
        }

        checkEvents(events,
                "open:A", "open:B", "use:A", "use:B",
                "close:B", "close:A");
    }

    // 6. Hai close lỗi: close B là primary, close A bị suppressed.
    static void multipleCloseFailures() throws Exception {
        List<String> events = new ArrayList<>();

        IOException caught = expectIo(() -> {
            try (Resource first = open("A", events, false, true);
                 Resource second = open("B", events, false, true)) {
                events.add("body");
            }
        });

        check(caught.getMessage().equals("close:B"),
                "B is primary close failure");
        check(caught.getSuppressed().length == 1,
                "need A suppressed");
        check(caught.getSuppressed()[0].getMessage().equals("close:A"),
                "A suppressed");
        checkEvents(events,
                "open:A", "open:B", "body", "close:B", "close:A");
    }

    // 7. Mở B lỗi: không chạy body, vẫn đóng A đã mở thành công.
    static void initializationFailure() throws Exception {
        List<String> events = new ArrayList<>();

        IOException caught = expectIo(() -> {
            try (Resource first = open("A", events, false, true);
                 Resource second = open("B", events, true, false)) {
                events.add("body");
            }
        });

        check(caught.getMessage().equals("init:B"),
                "init failure must be primary");
        check(caught.getSuppressed().length == 1,
                "A close must be suppressed");
        check(caught.getSuppressed()[0].getMessage().equals("close:A"),
                "wrong initialization suppression");
        checkEvents(events, "open:A", "open:B", "close:A");
    }

    // 8. return trong try: close xảy ra trước khi caller nhận kết quả.
    static String earlyReturn(List<String> events) throws IOException {
        try (Resource resource = open("A", events, false, false)) {
            events.add("return");
            return "ok";
        }
    }

    static void earlyReturnTest() throws Exception {
        List<String> events = new ArrayList<>();
        check(earlyReturn(events).equals("ok"), "wrong result");
        checkEvents(events, "open:A", "return", "close:A");
    }

    // 9. Resource null bị bỏ qua khi đóng, resource thật vẫn được đóng.
    static void nullResource() throws Exception {
        List<String> events = new ArrayList<>();

        try (Resource missing = null;
             Resource live = open("A", events, false, false)) {
            check(missing == null, "expected null");
            events.add("body");
            live.use();
        }

        checkEvents(events, "open:A", "body", "use:A", "close:A");
    }

    // 10. Đóng tài nguyên trước catch và finally bên ngoài.
    static void catchFinallyOrder() throws Exception {
        List<String> events = new ArrayList<>();

        try (Resource resource = open("A", events, false, false)) {
            throw new IOException("body");
        } catch (IOException e) {
            events.add("catch");
        } finally {
            events.add("finally");
        }

        checkEvents(events, "open:A", "close:A", "catch", "finally");
    }

    public static void main(String[] args) throws Exception {
        success();
        System.out.println("PASS success");

        bodyFailure();
        System.out.println("PASS body-failure");

        closeFailure();
        System.out.println("PASS close-failure");

        bodyAndCloseFailure();
        System.out.println("PASS body-and-close-failure");

        closeOrder();
        System.out.println("PASS close-order");

        multipleCloseFailures();
        System.out.println("PASS multiple-close-failures");

        initializationFailure();
        System.out.println("PASS initialization-failure");

        earlyReturnTest();
        System.out.println("PASS early-return");

        nullResource();
        System.out.println("PASS null-resource");

        catchFinallyOrder();
        System.out.println("PASS catch-finally-order");

        System.out.println("ALL TESTS PASSED: 10");
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac TryWithResourcesPathTests.java
java TryWithResourcesPathTests
```

**Stdout chính xác của bộ kiểm thử khi toàn bộ kiểm tra đều đạt:**

```text
PASS success
PASS body-failure
PASS close-failure
PASS body-and-close-failure
PASS close-order
PASS multiple-close-failures
PASS initialization-failure
PASS early-return
PASS null-resource
PASS catch-finally-order
ALL TESTS PASSED: 10
```

Mỗi dòng `PASS` chỉ được in **sau khi** hàm kiểm thử liên quan kết thúc thành công. Nếu một kỳ vọng sai, `check` ném `AssertionError` khiến chương trình dừng và **không** in `ALL TESTS PASSED: 10`. Do đó, kết quả này không phải các dòng `PASS` được in vô điều kiện mà không thực hiện kiểm tra.

Tài nguyên `Resource` ở đây chỉ là **test double**: nó không mở file hay socket thật. Chính vì thế, thứ tự sự kiện và exception có thể được xác minh chính xác mà không phụ thuộc hệ thống. Những lớp sản xuất thực tế cần thêm kiểm thử tích hợp về quyền truy cập file, kết nối, hiệu lực giao dịch, timeout và contract của đối tượng thật.

## 6. Giải thích kỹ từng đường đi quan trọng

### 6.1. Đường đi thành công: kiểm tra có đóng, không chỉ kiểm tra kết quả

`success()` phải quan sát đúng:

```text
open:A
use:A
close:A
```

Nếu code sản xuất trả dữ liệu đúng nhưng quên đóng file hoặc socket, test chỉ so sánh dữ liệu đầu ra vẫn có thể **vượt qua sai**. Kiểm tra sự kiện đóng hoặc trạng thái bên trong test double bảo vệ trực tiếp hợp đồng giải phóng tài nguyên.

Không nên đếm số lần `close()` mà bỏ qua cách gọi thủ công trong code: nếu ai đó thêm `resource.close()` vào trong thân `try`, chương trình có thể vô tình gọi `close()` **hai lần**. Danh sách sự kiện giúp nhận ra hành vi này.

### 6.2. Lỗi trong thân: lỗi chính phải giữ nguyên, đóng vẫn chạy

Trong `bodyFailure()`, test tạo trước đối tượng:

```java
IOException original = new IOException("body");
```

Rồi ném chính đối tượng ấy trong thân `try`. Kỳ vọng:

- Caller nhận **cùng object**: `caught == original`.
- Thứ tự vẫn là `open:A → use:A → close:A`.
- Không có suppressed exception khi `close()` hoàn tất bình thường.

Đây là kiểm tra mạnh hơn việc chỉ thấy `IOException` hoặc một message giống nhau. Nó chứng minh cơ chế `try-with-resources` **không tự tạo wrapper hay thay lỗi gốc** khi đóng thành công.

### 6.3. Chỉ lỗi đóng: `close()` có thể là exception chính

Trong `closeFailure()`, thân `try` chạy bình thường nhưng `close()` ném `IOException("close:A")`. Vì trước đó **không có exception nào đang chờ được truyền**, lỗi đóng chính là lỗi đi tới caller.

Một test chỉ bao phủ lỗi ở thân mà không bao phủ lỗi `close()` có thể bỏ qua hoàn toàn lớp lỗi này. Hãy mô phỏng nó chủ động bằng một cờ của test double.

### 6.4. Lỗi thân và lỗi đóng: `suppressed` thay vì mất nguyên nhân

Trong `bodyAndCloseFailure()`:

1. Thân `try` ném `IOException("body")`.
2. JVM vẫn gọi `close()`.
3. `close()` lại ném `IOException("close:A")`.
4. Exception `"body"` tiếp tục là primary; `"close:A"` được thêm vào danh sách suppressed.

Test chứng minh:

```java
check(caught == body, "body should be primary");
check(caught.getSuppressed().length == 1,
        "need one suppressed");
check(caught.getSuppressed()[0].getMessage().equals("close:A"),
        "wrong suppressed close");
```

**Cause và suppressed không phải một.** `getCause()` diễn tả quan hệ nguyên nhân giữa các exception, còn `getSuppressed()` giữ những lỗi phụ bị gác lại để ưu tiên exception chính. Ở ví dụ này, lỗi đóng **không tự động trở thành `getCause()`** của lỗi thân.

### 6.5. Nhiều tài nguyên: phải thử đúng thứ tự đóng

Với:

```java
try (Resource first = open("A", events, false, false);
     Resource second = open("B", events, false, false)) {
    first.use();
    second.use();
}
```

Kỳ vọng:

```text
open:A
open:B
use:A
use:B
close:B
close:A
```

`try-with-resources` quản lý theo nguyên tắc **last-opened, first-closed** đối với những tài nguyên đã khởi tạo thành công. Thứ tự đóng có thể rất quan trọng khi một resource phụ thuộc vào resource khác.

**Không chỉ test rằng cả hai đã đóng**: danh sách `close:A, close:B` có cùng tập tài nguyên được đóng nhưng **sai thứ tự**.

### 6.6. Nhiều lần `close()` đều thất bại

Nếu thân `try` bình thường và cả `B.close()`, `A.close()` đều ném lỗi:

- `B.close()` được gọi trước, lỗi từ B là **primary**.
- `A.close()` vẫn được thử gọi sau đó; lỗi từ A trở thành **suppressed** của lỗi B.
- Test phải chứng minh vẫn có sự kiện `close:A`, bởi việc đóng thất bại ở B **không làm Java bỏ đóng A**.

Đây là một trường hợp dễ bị bỏ qua nếu chỉ giả lập lỗi đóng trên một tài nguyên duy nhất.

### 6.7. Lỗi khởi tạo giữa chừng

Xét:

```java
try (Resource first = open("A", events, false, true);
     Resource second = open("B", events, true, false)) {
    events.add("body");
}
```

Trong ví dụ này:

1. A mở thành công.
2. Hàm `open("B", ...)` ghi sự kiện cố gắng mở B rồi ném `IOException("init:B")` **trước khi trả về** đối tượng B.
3. Thân `try` **không chạy** vì resource specification chưa hoàn tất.
4. Java vẫn gọi `A.close()`. Trong test, `A.close()` cũng ném `IOException("close:A")`.
5. Lỗi mở B **vẫn là primary**, lỗi đóng A là suppressed.

Kỳ vọng:

```text
open:A
open:B
close:A
```

Không có `body` và không có `close:B`, bởi **B chưa từng được khởi tạo thành công thành tài nguyên được đăng ký**.

Ngoài kiểm thử lỗi mở thứ hai, trong ứng dụng có nhiều resource hơn, hãy thử lỗi mở ở vị trí đầu, giữa và cuối. Điều này giúp chứng minh những resource đã mở trước đó được cleanup đúng.

### 6.8. `return` và những cách thoát không phải exception

`return` bên trong `try` **không bỏ qua cleanup**:

```java
static String earlyReturn(List<String> events) throws IOException {
    try (Resource resource = open("A", events, false, false)) {
        events.add("return");
        return "ok";
    }
}
```

Test `earlyReturnTest()` khẳng định thứ tự:

```text
open:A
return
close:A
```

Caller chỉ nhận kết quả `"ok"` khi cơ chế đóng đã hoàn tất thành công. Nếu `close()` ném exception trong lúc thân `try` sắp `return`, exception của `close()` có thể làm lời gọi **không trả về giá trị**. Đây là nhánh bổ sung hữu ích trong API có kết quả trả về sớm.

Tương tự, nếu có `break` hoặc `continue` thoát khỏi phần thân mà làm kết thúc khối `try-with-resources`, resource vẫn được xử lý đóng theo ngữ nghĩa của cấu trúc đó.

### 6.9. Tài nguyên `null` vẫn cho phép thân `try` chạy

Trong `nullResource()`, một resource có giá trị `null` và resource khác là object hợp lệ. Java **bỏ qua `close()` cho resource `null`**, không bỏ qua toàn bộ khối `try`.

Kiểm thử chứng minh sự kiện sử dụng `live` xảy ra, đồng thời không có sự kiện đóng cho `missing`. Nếu bên trong thân `try` gọi phương thức trên `missing`, lỗi `NullPointerException` vẫn có thể xảy ra: `try-with-resources` chỉ tránh gọi `close()` trên tham chiếu `null` ở phần cleanup, không tự biến `null` thành object hợp lệ.

### 6.10. Cleanup phải xảy ra trước `catch`/`finally`

`catchFinallyOrder()` ném exception trong thân `try`, nhưng kỳ vọng:

```text
open:A
close:A
catch
finally
```

Điều này bảo đảm handler không chạy khi resource còn đang chờ được đóng trong chính cấu trúc `try-with-resources` ấy. Nếu logic của handler cần truy cập dữ liệu trước khi đóng, nên thu thập thông tin cần thiết **bên trong thân `try`** và truyền giá trị độc lập, thay vì cố dùng một resource đã đóng.

## 7. Đưa các kiểm thử vào JUnit Jupiter

Bộ kiểm thử độc lập ở trên không yêu cầu dependency. Trong dự án Java thực tế có JUnit Jupiter, có thể chuyển từng hàm thành một `@Test` riêng, thay `check` và `checkEvents` bằng assertions có thông báo rõ ràng.

Ví dụ **một phương thức kiểm thử đặt trong lớp test**, giả sử lớp `Resource`, hàm `open(...)` đã tồn tại trong fixture và dự án đã cấu hình JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

@Test
void bodyExceptionWinsWhenCloseAlsoFails() {
    List<String> events = new ArrayList<>();
    IOException body = new IOException("body");

    IOException caught = assertThrows(IOException.class, () -> {
        try (Resource resource = open("A", events, false, true)) {
            throw body;
        }
    });

    assertSame(body, caught);
    assertEquals(1, caught.getSuppressed().length);
    assertEquals("close:A",
            caught.getSuppressed()[0].getMessage());
    assertEquals(List.of("open:A", "close:A"), events);
}
```

Đây là **đoạn minh họa, không phải tệp Java độc lập**: phần import đặt ở đầu tệp; `@Test` và method đặt trong lớp test; fixture phải khai báo hoặc import `Resource` và `open(...)`. Khi dùng code thực tế, hãy kiểm tra cấu hình dependency, version và test engine của dự án.

Các assertions quan trọng:

- `assertThrows(...)` kiểm tra loại exception đến caller.
- `assertSame(...)` kiểm tra **đúng đối tượng** exception gốc.
- `assertEquals(...)` kiểm tra thông điệp hoặc số lượng suppressed exception.
- `assertIterableEquals(...)` hoặc `assertEquals(List.of(...), events)` kiểm tra **thứ tự** thao tác.
- Có thể dùng `assertDoesNotThrow(...)` cho đường thành công, nhưng vẫn cần assertion riêng xác nhận đã đóng resource.

**Tránh chỉ viết `assertThrows(IOException.class, ...)` cho mọi trường hợp lỗi.** Nó không chứng minh resource đã đóng, thứ tự đóng, exception nào là primary hoặc suppressed nào được giữ.

## 8. Kiểm thử tài nguyên thực và test double: khi nào dùng loại nào?

### 8.1. Unit test: tài nguyên giả cho thứ tự và ngoại lệ

Dùng tài nguyên giả như `Resource` ở mục 5 khi cần kiểm soát chính xác **trường hợp hiếm**:

- Đóng tài nguyên ném exception.
- Nhiều resource cùng ném lỗi trong lúc đóng.
- Một initializer ném lỗi sau khi một resource khác mở thành công.
- Thứ tự đóng và thứ tự handler.
- Tài nguyên null và các đường return sớm.

Các tình huống này khó tái hiện ổn định bằng file hay socket thật. Test double giúp test **nhanh, xác định được, không phụ thuộc môi trường**.

### 8.2. Integration test: kiểm tra hợp đồng API thực

Với `Files.newBufferedReader(path)`, `Files.newOutputStream(path)`, socket hoặc JDBC, cần kiểm thử thêm những gì test double không đảm bảo:

- Đường thành công thực sự đọc/ghi đúng nội dung và đóng đúng tài nguyên.
- Đường thất bại không để connection/stream mở quá phạm vi cho phép.
- Hành vi lỗi đóng và exception của API thực, nếu có thể tái hiện an toàn.
- Thứ tự sở hữu tài nguyên khi wrapper đóng cả underlying stream.
- Cleanup khi thư viện bên ngoài quản lý transaction hoặc connection pool.

Với test file, tạo đường dẫn và thư mục tạm theo cơ chế của framework test (ví dụ `@TempDir` trong JUnit Jupiter), không dùng đường dẫn cố định hoặc file thật của người dùng. Hãy kiểm thử sản phẩm trên tài nguyên thực, nhưng không dùng timing/sleep như bằng chứng duy nhất cho việc đã đóng.

### 8.3. Hành vi cần test theo hợp đồng cụ thể

`AutoCloseable.close()` **không bảo đảm** mọi implementation đều có thể gọi lặp an toàn, và không phải resource nào cũng công bố trạng thái `isClosed()`. Vì vậy một test tích hợp nên quan sát trạng thái qua API được công bố của resource, hoặc qua fake/instrumentation hợp lý, chứ không giả định có thể truy vấn "closed" trên mọi resource.

Nếu wrapper sở hữu underlying stream, test việc đóng wrapper có đóng stream nền như dự kiến hay không; tránh đưa cả wrapper và stream nền vào cùng header khi việc đóng lặp không được đảm bảo an toàn.

## 9. Những lỗi thiết kế test thường gặp

| Cách kiểm thử chưa đủ | Rủi ro | Cách sửa |
| --- | --- | --- |
| Chỉ assert dữ liệu trả về | Không phát hiện resource bị rò rỉ | Ghi sự kiện `close`/đo trạng thái theo hợp đồng |
| Chỉ test đường thành công | Bỏ sót lỗi cleanup trên đường ngoại lệ | Giả lập body failure, close failure và cả hai |
| Chỉ nhìn class của exception | Không biết có giữ đúng lỗi gốc | `assertSame` với exception gốc khi phù hợp |
| Chỉ kiểm tra `getMessage()` | Không phát hiện mất suppressed exception | Assert `getSuppressed()` và loại/message của từng lỗi |
| Assert "A và B đều đóng" nhưng bỏ qua thứ tự | Không phát hiện đóng sai thứ tự | Assert chính xác `close:B → close:A` |
| Không test lỗi initializer thứ hai | Có thể bỏ qua cleanup resource thứ nhất | Giả lập mở B thất bại, kiểm tra A vẫn đóng |
| Test bằng file/network công khai và timing | Flaky, phụ thuộc môi trường, khó tái hiện lỗi đóng | Unit test với test double; integration test biệt lập |
| Dùng `assert` Java nhưng quên bật `-ea` | Các assertions có thể không chạy | Dùng JUnit assertions hoặc `check` ném `AssertionError` |
| `catch (Exception e) { }` trong test | Nuốt exception, làm test "PASS" sai | Assert exception mong đợi; lỗi khác phải làm test thất bại |
| In `PASS` trước khi kiểm tra | Đưa kết quả báo cáo sai | Chỉ in `PASS` **sau** các kiểm tra |
| Test dùng chung một danh sách sự kiện mutable | Test phụ thuộc nhau và khó xác định lỗi | Mỗi test có fixture/sự kiện mới |
| Đòi stack trace có số dòng cố định | Dễ hỏng khi refactor hoặc khác compiler | Test quan hệ cause/suppressed, không so chuỗi toàn bộ stack trace |

**Lưu ý:** `java -ea` có thể bật từ khóa `assert` của Java, nhưng không cần dùng `-ea` để chạy những `check(...)` ở ví dụ hoàn chỉnh. Khi chuyển qua JUnit, các assertion của JUnit được thực thi theo test framework, không phụ thuộc trạng thái `-ea`.

## 10. Kịch bản nâng cao nên bổ sung theo yêu cầu ứng dụng

Bộ kiểm thử 10 trường hợp ở trên bao phủ hành vi nền tảng. Các hệ thống đặc thù có thể cần:

1. **`close()` ném lỗi trong lúc `return`:** test rằng exception đóng được truyền ra; caller không nhận giá trị dự kiến.
2. **Initializer thứ nhất thất bại:** không có resource nào trước đó để đóng; thân `try` không chạy.
3. **Initializer thứ ba thất bại:** A và B đã mở phải đóng theo thứ tự B rồi A; lỗi đóng được suppressed theo quy tắc.
4. **Tài nguyên implement `AutoCloseable` ném checked exception rộng:** kiểm tra chữ ký `throws` hoặc `catch` tương ứng, không ép mọi lỗi về `IOException`.
5. **Có nhiều suppressed exceptions:** kiểm tra danh sách chứa đủ các lỗi đóng được tạo theo thứ tự dọn dẹp.
6. **Body ném exception unchecked:** `RuntimeException` cũng là đường kết thúc bất thường và vẫn phải cleanup.
7. **Ứng dụng chuyển đổi exception sang loại nghiệp vụ:** kiểm tra wrapper có `cause` đúng, đồng thời suppressed của cause không mất.
8. **Tài nguyên đã khai báo trước** (`try (existing)`, Java 9+): kiểm tra tài nguyên vẫn được đóng khi kết thúc; biến vẫn nằm trong phạm vi khai báo bên ngoài nhưng không được mặc định tiếp tục sử dụng object đã đóng.
9. **Hệ thống log:** chỉ ghi exception tại ranh giới phù hợp, bảo đảm logger nhận `Throwable` nếu cần stack trace, cause, suppressed; không log trùng ở mọi tầng.

Các mục này là **ý tưởng mở rộng**; bài kiểm thử chạy độc lập ở mục 5 đã thật sự kiểm tra 10 tình huống nền tảng, không tự khẳng định đã kiểm tra mọi nhánh nâng cao.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Nếu thân `try` ném `IOException A`, và `close()` ném `IOException B`, caller nhận lỗi nào?  
**Đáp án:** A là primary. B nằm trong `A.getSuppressed()`; test nên khẳng định đúng **đối tượng A** và đúng suppressed B.

**Câu 2.** Hai tài nguyên A, B mở thành công, B đóng lỗi trước; Java có cố đóng A nữa không?  
**Đáp án:** Có. Cơ chế đóng vẫn tiến hành với những tài nguyên đã khởi tạo còn lại; nếu A cũng đóng lỗi và không có lỗi thân `try`, lỗi của A có thể bị suppressed vào lỗi đóng của B.

**Câu 3.** Khởi tạo B lỗi khi A đã mở; thân `try` có chạy không?  
**Đáp án:** Không. A được đóng, còn B chưa có resource được đăng ký thành công nên không được đóng từ lần khởi tạo thất bại.

**Câu 4.** Một test chỉ thấy `assertThrows(IOException.class, ...)` thành công đã chứng minh không rò rỉ resource chưa?  
**Đáp án:** Chưa. Cần kiểm tra sự kiện đóng hoặc trạng thái resource, kể cả thứ tự khi có nhiều resource.

**Câu 5.** `return` trong thân `try-with-resources` có làm bỏ qua `close()` không?  
**Đáp án:** Không. Java tiến hành cleanup trước khi caller nhận kết quả; nếu cleanup ném lỗi, việc trả kết quả có thể không diễn ra.

**Câu 6.** Nếu một resource là `null`, Java có bỏ qua toàn bộ thân `try` và các resource khác không?  
**Đáp án:** Không. Nó chỉ không gọi `close()` trên resource `null`. Những initializer khác và thân `try` vẫn chạy nếu không có lỗi khác.

**Câu 7.** Vì sao nên dùng sự kiện `open:A, close:A` thay vì chỉ in `PASS`?  
**Đáp án:** Vì sự kiện xác nhận hành vi cleanup thật, phát hiện thiếu/đóng thừa và thứ tự đóng sai.

## 12. Checklist áp dụng vào dự án

Trước khi coi một hàm dùng `try-with-resources` là đã kiểm thử đủ, hãy tự xác nhận:

- [ ] Đường thành công kiểm tra kết quả **và** đóng tài nguyên.
- [ ] Lỗi trong thân `try` vẫn đóng tài nguyên, lỗi gốc không bị mất.
- [ ] Lỗi `close()` khi thân thành công được truyền/giải quyết đúng.
- [ ] Lỗi thân và lỗi đóng đồng thời: primary và suppressed đúng.
- [ ] Hai hay nhiều tài nguyên được đóng theo thứ tự ngược.
- [ ] Một lần `close()` thất bại không ngăn cleanup các tài nguyên trước đó.
- [ ] Lỗi khởi tạo ở giữa: tài nguyên trước đã mở được cleanup, thân không chạy.
- [ ] `return` hoặc đường thoát sớm không bỏ qua cleanup.
- [ ] Trường hợp `null` được kiểm tra theo hợp đồng đầu vào của ứng dụng.
- [ ] `catch`/`finally` chạy sau cleanup tương ứng.
- [ ] Test độc lập, deterministic, không nuốt exception, không dựa vào timing hay trạng thái shared mutable.
- [ ] Kiểm thử tích hợp bổ sung đúng hành vi của tài nguyên sản xuất.

## 13. Kết luận và tài liệu chính thức

**Kiểm thử `try-with-resources` không phải chỉ là kiểm tra có trả kết quả đúng hoặc có ném exception hay không.** Mục tiêu là chứng minh **resource lifecycle** đúng trong cả đường bình thường lẫn bất thường, và giữ lại đầy đủ các exception phục vụ chẩn đoán. Công cụ hiệu quả nhất ở unit test là **tài nguyên giả có nhật ký sự kiện và chủ động phát sinh lỗi**, kết hợp assertions cho **thứ tự đóng, primary exception, suppressed exception và hành vi của caller**.

Tài liệu tham khảo hiện hành:

- [Java Language Specification 17, `14.20.3 — `try`-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): khởi tạo, đóng ngược thứ tự, lỗi đóng, suppressed exceptions và các kiểu kết thúc khối.
- [Java SE 17 API — `AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng `close()`, kiểu exception và lưu ý idempotence.
- [Java SE 17 API — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getSuppressed()`, `getCause()` và thông tin chẩn đoán.
- [JUnit Jupiter User Guide — Assertions](https://docs.junit.org/current/user-guide/#writing-tests-assertions): cách viết unit test bằng `assertThrows`, `assertEquals`, `assertSame` trong dự án có JUnit.