# Kiểm tra suppressed exception và thứ tự đóng tài nguyên trong Java

## 1. Mục tiêu học tập

Khi dùng `try-with-resources`, Java giúp đóng tài nguyên tự động, nhưng một bài kiểm thử đúng không nên chỉ xác nhận tài nguyên đã được đóng. Cần kiểm tra **thứ tự đóng**, **exception nào là lỗi chính**, **exception nào được đưa vào `getSuppressed()`**, và liệu Java có tiếp tục cố đóng các tài nguyên khác sau khi một `close()` thất bại hay không.

Ví dụ đơn giản:

```java
try (Resource a = openA();
     Resource b = openB();
     Resource c = openC()) {
    doWork();
}
```

Đây là **mảnh mã minh họa**, cần tự định nghĩa `Resource` và các phương thức được gọi. Với các tài nguyên đã khởi tạo thành công, thứ tự thông thường là:

```text
Mở:   A → B → C
Thân:  doWork()
Đóng: C → B → A
```

Nếu `doWork()` ném lỗi E và các `close()` cũng ném, Java ưu tiên giữ **E là exception chính**. Lỗi đóng được gắn vào E dưới dạng **suppressed exceptions**, tránh mất dấu lỗi ban đầu trong khi vẫn giữ dữ liệu chẩn đoán các sự cố cleanup.

Nếu thân `try` thành công nhưng `close()` đầu tiên ném lỗi, exception từ `close()` đó trở thành **exception chính**; các lỗi đóng tài nguyên về sau được thêm vào danh sách suppressed của nó.

Bài này sử dụng ví dụ Java 17+ **biên dịch/chạy được**, xác nhận thứ tự event và danh sách suppressed bằng kiểm tra tự động, đồng thời chỉ ra cách viết test JUnit, những trường hợp biên và các lỗi triển khai thường gặp.

## 2. Những khái niệm cần phân biệt

**Primary exception** là Throwable được chọn làm thất bại chính của toàn khối `try-with-resources`. Trong trường hợp thân khối đã ném lỗi, lỗi thân thường là primary. Trong trường hợp thân thành công, lỗi đóng xuất hiện đầu tiên là primary nếu có lỗi đóng.

**Suppressed exception** là Throwable được ghi kèm primary bằng `Throwable.addSuppressed(...)`, thường biểu thị lỗi thứ cấp xảy ra trong khi đóng những tài nguyên còn lại. Có thể lấy ra bằng `Throwable.getSuppressed()`.

**Cause** là quan hệ `getCause()`, thường biểu diễn “lỗi này được gây ra bởi lỗi khác” khi ứng dụng bọc exception với constructor `new Exception(message, cause)`. Suppressed **không phải** cause; cả hai tồn tại độc lập trên cùng Throwable.

**LIFO (Last In, First Out)** trong ngữ cảnh đóng tài nguyên nghĩa là tài nguyên khai báo/khởi tạo sau được đóng trước.

**Cleanup failure** là lỗi từ `close()`, `finally`, rollback hoặc hành động dọn dẹp khác. Không phải cleanup failure nào cũng được Java tự gắn suppressed; hành vi chuẩn được thảo luận ở đây áp dụng cụ thể cho `try-with-resources` và các tình huống dùng `addSuppressed`.

**AutoCloseable** là interface của Java với phương thức `close()`. Kiểu `Closeable` của `java.io` kế thừa `AutoCloseable` và dùng kiểu exception hẹp hơn trong chữ ký `close()`. Tài nguyên phải phù hợp với hợp đồng đóng của nó; không phải mọi `close()` đều chỉ làm tác vụ đơn giản.

## 3. Quy tắc thứ tự của try-with-resources

Java xử lý resource specification theo hai chiều ngược nhau:

1. Các initializer trong header được đánh giá **từ trái sang phải**.
2. Thân `try` chỉ được bắt đầu khi các initializer cần thiết hoàn tất.
3. Khi rời khối, những tài nguyên đã khởi tạo thành công được gọi `close()` **từ phải sang trái**.
4. Java vẫn thử đóng tài nguyên trước đó khi một thao tác đóng ném exception.
5. Các `catch`/`finally` đặt **sau** thân `try-with-resources` được thực thi sau nỗ lực đóng tài nguyên, theo thứ tự ngữ nghĩa của câu lệnh.

Ví dụ:

```java
try (InputStream in = openInput();
     OutputStream out = openOutput()) {
    copy(in, out);
} catch (IOException ex) {
    report(ex);
}
```

Đây là **mảnh code** cần import `java.io.InputStream`, `OutputStream`, `IOException` và các hàm ứng dụng. Nếu cả hai đã được khởi tạo, thứ tự đóng là `out.close()` rồi `in.close()`. Khi vào `catch` ở bên ngoài resource header, nỗ lực đóng của cả hai đã được thực hiện.

Thứ tự đóng có thể quan trọng khi một wrapper phụ thuộc vào tài nguyên bên dưới. Ví dụ một stream được xây trên stream khác thường nên được tạo sau, rồi đóng trước. Tuy nhiên, nhiều wrapper có `close()` **tự đóng cả delegate**: đừng tùy tiện quản lý cùng một tài nguyên hai lần mà không xem hợp đồng idempotency/double close.

## 4. Trường hợp A: thân try lỗi và close cũng lỗi

Giả sử thân `try` ném `IllegalArgumentException("body-failed")`, rồi ba tài nguyên `C`, `B`, `A` đều ném trong `close()`. Java giữ một primary là lỗi thân:

```text
PRIMARY
  IllegalArgumentException("body-failed")
    SUPPRESSED
      IllegalStateException("close-C-failed")
      IllegalStateException("close-B-failed")
      IllegalStateException("close-A-failed")
```

Các sự kiện xảy ra theo thời gian:

```text
open-A
open-B
open-C
body
throw body-failed
close-C  -> throw close-C-failed  -> suppressed
close-B  -> throw close-B-failed  -> suppressed
close-A  -> throw close-A-failed  -> suppressed
propagate body-failed
```

**Điểm kiểm thử:** `getMessage()` của exception chính vẫn là `body-failed`, `getSuppressed().length == 3`, thông điệp của từng phần tử theo thứ tự `C, B, A`. Không được kết luận rằng vì `close-C` thất bại nên `close-B` và `close-A` không chạy.

Lưu ý: danh sách suppressed ghi theo **thứ tự các lỗi được thêm vào** trong quá trình cleanup. Với những `close()` ném trực tiếp trong ví dụ, nó đúng bằng thứ tự đóng ngược. Nếu code tự thêm các suppressed khác hoặc wrapper có cleanup lồng nhau, cần phân tích cấu trúc chính xác, không suy rộng rằng mọi mảng `getSuppressed()` trong mọi chương trình luôn phản ánh duy nhất thứ tự đóng resource header.

## 5. Trường hợp B: thân thành công, nhiều close cùng lỗi

Nếu thân hoàn tất bình thường nhưng `C.close()` thất bại đầu tiên, `C` được xem là exception chính:

```text
PRIMARY
  IllegalStateException("close-C-failed")
    SUPPRESSED
      IllegalStateException("close-B-failed")
      IllegalStateException("close-A-failed")
```

Thứ tự:

```text
open-A
open-B
open-C
body completed normally
close-C  -> failure becomes primary
close-B  -> failure suppressed on close-C failure
close-A  -> failure suppressed on close-C failure
propagate close-C-failed
```

**Bài test phải phân biệt lỗi body và lỗi close.** Không phải mọi exception thoát khỏi `try-with-resources` đều là lỗi trong thân. Nếu tác vụ đọc/ghi hoàn tất rồi `close` gặp lỗi flush/commit, tình trạng dữ liệu cần được xác minh; không nên tự động cho rằng thân chưa thực hiện.

Với `OutputStream` hoặc tài nguyên có buffering, một số lỗi ghi có thể bộc lộ **lúc flush/close**, không phải trong lệnh `write` trước đó. Vì vậy việc assert thân đã chạy không tương đương mọi dữ liệu đã được lưu bền vững.

## 6. Trường hợp C: mở một tài nguyên phía sau thất bại

Giả sử `A` và `B` đã khởi tạo, nhưng việc tạo `C` ném exception. Khi đó:

- Thân `try` **không chạy**.
- `C` chưa được khởi tạo thành công nên **không có tài nguyên C trong header để Java gọi close**.
- Những tài nguyên đã khởi tạo trước đó (`B`, `A`) vẫn được đóng theo thứ tự ngược.
- Exception do khởi tạo `C` tạo ra là **primary**.
- Nếu `B.close()`, `A.close()` cũng thất bại, chúng được gắn suppressed theo thứ tự `B` rồi `A`.

```text
open-A
open-B
attempt to open C -> throw open-C-failed
close-B -> suppressed close-B-failed
close-A -> suppressed close-A-failed
propagate open-C-failed
```

Một constructor có thể cấp phát tài nguyên nội bộ rồi ném trước khi trả object. Trong trường hợp đó, `try-with-resources` **không thể tự gọi `close()` trên object chưa được đăng ký thành công**. Constructor/factory phải quản lý rollback, cleanup các tài nguyên tạm của chính nó. Đây là trường hợp cần test riêng khi xây resource phức tạp.

## 7. Chương trình Java 17+ độc lập, có xác nhận tự động

Ví dụ sau dùng `AutoCloseable` tự tạo, danh sách sự kiện, các exception có message dễ nhận biết và hàm `verify(...)`. Nó kiểm tra **ba trường hợp**: lỗi thân + lỗi close, chỉ lỗi close, và lỗi khởi tạo. Nếu một kết quả không đúng, chương trình ném `AssertionError` thay vì in `TESTS: PASS`.

Tạo file **`SuppressedCloseOrderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class SuppressedCloseOrderDemo {
    private static final List<String> EVENTS = new ArrayList<>();

    static final class NamedResource implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;

        NamedResource(String name, boolean failOnClose) {
            this.name = name;
            this.failOnClose = failOnClose;
            EVENTS.add("open-" + name);
        }

        @Override
        public void close() {
            EVENTS.add("close-" + name);
            if (failOnClose) {
                throw new IllegalStateException("close-" + name + "-failed");
            }
        }
    }

    static NamedResource failToOpen(String name) {
        EVENTS.add("open-attempt-" + name);
        throw new IllegalArgumentException("open-" + name + "-failed");
    }

    static Throwable runBodyCase(boolean failBody) {
        EVENTS.clear();
        try (NamedResource a = new NamedResource("A", true);
             NamedResource b = new NamedResource("B", true);
             NamedResource c = new NamedResource("C", true)) {
            EVENTS.add("body");
            if (failBody) {
                throw new IllegalArgumentException("body-failed");
            }
        } catch (Exception ex) {
            return ex;
        }
        throw new AssertionError("Expected a failure");
    }

    static Throwable runInitCase() {
        EVENTS.clear();
        try (NamedResource a = new NamedResource("A", true);
             NamedResource b = new NamedResource("B", true);
             NamedResource c = failToOpen("C")) {
            EVENTS.add("body");
        } catch (Exception ex) {
            return ex;
        }
        throw new AssertionError("Expected initialization failure");
    }

    static String suppressed(Throwable error) {
        return Arrays.stream(error.getSuppressed())
                .map(Throwable::getMessage)
                .collect(Collectors.joining(","));
    }

    static void verify(String actual, String expected) {
        if (!expected.equals(actual)) {
            throw new AssertionError("Expected: " + expected + ", actual: " + actual);
        }
    }

    public static void main(String[] args) {
        Throwable bodyError = runBodyCase(true);
        String bodyEvents = String.join(",", EVENTS);
        verify(bodyEvents, "open-A,open-B,open-C,body,close-C,close-B,close-A");
        verify(bodyError.getMessage(), "body-failed");
        verify(suppressed(bodyError),
                "close-C-failed,close-B-failed,close-A-failed");
        System.out.println("BODY_EVENTS: " + bodyEvents);
        System.out.println("BODY_PRIMARY: " + bodyError.getMessage());
        System.out.println("BODY_SUPPRESSED: " + suppressed(bodyError));

        Throwable closeError = runBodyCase(false);
        String closeEvents = String.join(",", EVENTS);
        verify(closeEvents, "open-A,open-B,open-C,body,close-C,close-B,close-A");
        verify(closeError.getMessage(), "close-C-failed");
        verify(suppressed(closeError), "close-B-failed,close-A-failed");
        System.out.println("CLOSE_EVENTS: " + closeEvents);
        System.out.println("CLOSE_PRIMARY: " + closeError.getMessage());
        System.out.println("CLOSE_SUPPRESSED: " + suppressed(closeError));

        Throwable initError = runInitCase();
        String initEvents = String.join(",", EVENTS);
        verify(initEvents, "open-A,open-B,open-attempt-C,close-B,close-A");
        verify(initError.getMessage(), "open-C-failed");
        verify(suppressed(initError), "close-B-failed,close-A-failed");
        System.out.println("INIT_EVENTS: " + initEvents);
        System.out.println("INIT_PRIMARY: " + initError.getMessage());
        System.out.println("INIT_SUPPRESSED: " + suppressed(initError));
        System.out.println("TESTS: PASS");
    }
}
```

Biên dịch và chạy từ thư mục chứa file, sử dụng JDK 17 trở lên:

```bash
javac -encoding UTF-8 SuppressedCloseOrderDemo.java
java SuppressedCloseOrderDemo
```

**Standard output đã kiểm chứng bằng `javac` và `java`:**

```text
BODY_EVENTS: open-A,open-B,open-C,body,close-C,close-B,close-A
BODY_PRIMARY: body-failed
BODY_SUPPRESSED: close-C-failed,close-B-failed,close-A-failed
CLOSE_EVENTS: open-A,open-B,open-C,body,close-C,close-B,close-A
CLOSE_PRIMARY: close-C-failed
CLOSE_SUPPRESSED: close-B-failed,close-A-failed
INIT_EVENTS: open-A,open-B,open-attempt-C,close-B,close-A
INIT_PRIMARY: open-C-failed
INIT_SUPPRESSED: close-B-failed,close-A-failed
TESTS: PASS
```

### Đọc kết quả kiểm chứng

- `BODY_EVENTS` chứng minh mở `A,B,C` từ trái sang phải, thực hiện body, sau đó đóng `C,B,A` theo LIFO.
- `BODY_PRIMARY` là lỗi body; thứ tự suppressed đúng `C,B,A`.
- `CLOSE_PRIMARY` là lỗi ở `C.close()` vì thân không lỗi; `B` và `A` vẫn được gọi.
- `INIT_EVENTS` cho thấy **không có `body` và không có `close-C`**, do khởi tạo C chưa thành công; B/A vẫn đóng.
- Hàm `verify` kiểm tra giá trị chính xác. Nếu đổi thứ tự event hoặc mất một suppressed, phép kiểm tra ném `AssertionError` và không in `TESTS: PASS`.
- Mỗi case xóa `EVENTS` trước khi chạy; các tài nguyên luôn chạy tuần tự trên main thread nên demo **không** dựa vào thứ tự scheduling bất định.
- Các exception từ `close()` là `IllegalStateException` (unchecked), vì vậy phương thức override `close()` không cần khai báo `throws Exception`. Một tài nguyên thật có thể dùng checked exception và cần xử lý theo chữ ký thích hợp.

Dùng bộ test này để học **quy tắc Java**, không sử dụng `NamedResource` giả làm tài nguyên production. Các thao tác real-world như DB connection, stream flush, socket close có thể có side effects, timeout hoặc semantics riêng.

## 8. Viết JUnit 5 test: assert thứ tự và suppressed

Khi chuyển ví dụ thành test thực tế, có thể dùng **JUnit Jupiter (JUnit 5)**. Đoạn sau là *phương thức kiểm thử minh họa*, cần đặt trong một test class, thêm thư viện JUnit 5 và import phù hợp. Nó không phải chương trình Java SE độc lập:

```java
@Test
void bodyFailureKeepsCloseErrorsSuppressed() {
    List<String> events = new ArrayList<>();

    class R implements AutoCloseable {
        final String name;
        R(String name) {
            this.name = name;
            events.add("open-" + name);
        }
        @Override
        public void close() {
            events.add("close-" + name);
            throw new IllegalStateException("close-" + name);
        }
    }

    IllegalArgumentException thrown = assertThrows(
            IllegalArgumentException.class, () -> {
                try (R a = new R("A");
                     R b = new R("B");
                     R c = new R("C")) {
                    events.add("body");
                    throw new IllegalArgumentException("body");
                }
            });

    assertEquals("body", thrown.getMessage());
    assertEquals(List.of(
            "open-A", "open-B", "open-C", "body",
            "close-C", "close-B", "close-A"), events);
    assertEquals(List.of("close-C", "close-B", "close-A"),
            Arrays.stream(thrown.getSuppressed())
                  .map(Throwable::getMessage)
                  .toList());
}
```

Các import cần thiết (không phải phần của method ở trên):

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
```

Trong JUnit test này, kiểm tra ba yếu tố độc lập:

1. **Loại và message primary:** `assertThrows(IllegalArgumentException.class, ...)` và `getMessage()`.
2. **Thứ tự lifecycle:** danh sách event phải khớp đầy đủ từ open đến close.
3. **Thứ tự suppressed:** `getSuppressed()` là các lỗi từ C, B, A.

Nếu chỉ assert `thrown.getSuppressed().length == 3` thì vẫn có thể bỏ lọt bug gọi `close()` sai thứ tự. Nếu chỉ assert event, có thể bỏ lọt bug **không bảo toàn lỗi**. Kết hợp cả hai tạo một phép thử hữu ích hơn.

Dùng `assertThrowsExactly` khi cần phân biệt loại lỗi chính xác và phiên bản JUnit hỗ trợ; còn `assertThrows` chấp nhận cả subtype của kiểu kỳ vọng. Không cần assert toàn bộ stack trace text vì các tên frame và dòng source có thể thay đổi theo compiler/runtime.

## 9. Ma trận kiểm thử nên bao phủ

| Tình huống | Primary mong đợi | Suppressed | Thứ tự close |
| --- | --- | --- | --- |
| Thân thành công, mọi close thành công | Không có exception | Rỗng | C → B → A |
| Thân lỗi, mọi close thành công | Lỗi body | Rỗng | C → B → A |
| Thân lỗi, chỉ C close lỗi | Lỗi body | C | C → B → A |
| Thân lỗi, C và A close lỗi | Lỗi body | C rồi A | C → B → A |
| Thân lỗi, cả ba close lỗi | Lỗi body | C rồi B rồi A | C → B → A |
| Thân thành công, C close lỗi | Lỗi close-C | Rỗng | C → B → A |
| Thân thành công, C/B/A close lỗi | Lỗi close-C | B rồi A | C → B → A |
| Khởi tạo C lỗi, B/A close thành công | Lỗi khởi tạo C | Rỗng | B → A |
| Khởi tạo C lỗi, B/A close lỗi | Lỗi khởi tạo C | B rồi A | B → A |
| Khởi tạo A lỗi | Lỗi khởi tạo A | Thường rỗng, nếu constructor tự thêm lỗi thì tùy thiết kế | Không có resource header đã khởi tạo để đóng |
| Header có resource tham chiếu null | Tùy body và các resource khác | Không có lỗi close của resource null | Resource null bị bỏ qua |

Đây là **ma trận để thiết kế test**, không phải mọi hệ thống đều cần viết đủ một test riêng cho từng dòng nếu đã được bao phủ bởi parameterized tests hoặc component contract. Với thư viện quản lý tài nguyên, các ca lỗi khởi tạo và lỗi khi đóng là quan trọng nhất vì bug có thể chỉ xuất hiện trong đường thất bại hiếm gặp.

Một chiến lược tốt là tạo `FakeResource` hỗ trợ ba lựa chọn: không lỗi, lỗi khởi tạo, lỗi đóng, rồi chạy các tổ hợp cần thiết. Mỗi test phải xác định rõ **primary**, **getSuppressed()** và **event order** thay vì chỉ nhìn một Boolean “closed”.

## 10. Suppressed exception khác cause như thế nào?

Hai API của `Throwable`:

```java
Throwable cause = error.getCause();
Throwable[] cleanupFailures = error.getSuppressed();
```

Đây là mảnh code bên trong phương thức có `Throwable error`.

- `getCause()` chỉ một liên hệ nguyên nhân khi exception được bọc hoặc gán cause.
- `getSuppressed()` trả **mảng** các Throwable được gắn bằng `addSuppressed`, ví dụ những lỗi xảy ra trong khi đóng các resource còn lại.
- Có thể tồn tại **cả cause và suppressed trên cùng Throwable**.
- Một suppressed exception cũng có thể có **cause** và **suppressed riêng**, tạo cấu trúc lỗi nhiều tầng.

Ví dụ:

```text
OrderProcessingException (primary)
  Caused by: SQLException
  Suppressed: IOException("close output")
  Suppressed: IOException("close input")
```

Đây là cấu trúc minh họa, không phải output bắt buộc của một runtime. `cause` nói về nguồn thất bại nghiệp vụ, còn suppressed ghi những lỗi cleanup **không nên thay thế nguyên nhân chính**.

Nếu dùng `logger.error("failed", error)`, nhiều logging framework in cả suppressed lẫn cause. Khi điều tra, đừng bỏ qua các dòng `Suppressed: ...` của stack trace. Cũng không nên nhầm “suppressed” là “đã được xử lý an toàn và có thể bỏ qua”: việc close thất bại có thể liên quan đến mất dữ liệu, khóa, transaction hoặc tài nguyên không được giải phóng.

## 11. Cơ chế gần tương đương do compiler sinh

`try-with-resources` không đơn giản là:

```java
try {
    body();
} finally {
    resource.close();
}
```

Mẫu `finally` thủ công này **có thể làm exception của `close()` che exception từ `body()`**, nên không giữ đúng hành vi suppressed của try-with-resources.

Về ý tưởng, với một resource, compiler cần một Throwable primary và xử lý lỗi close theo hướng:

```java
Throwable primary = null;
try {
    body();
} catch (Throwable thrown) {
    primary = thrown;
    throw thrown;
} finally {
    if (resource != null) {
        if (primary != null) {
            try {
                resource.close();
            } catch (Throwable closeFailure) {
                primary.addSuppressed(closeFailure);
            }
        } else {
            resource.close();
        }
    }
}
```

Đây là **mã giả gần cấu trúc**, không phải chương trình độc lập; `resource` và `body()` đã giả định tồn tại. Nó giúp hiểu tại sao lỗi body vẫn được ưu tiên và lỗi close thứ cấp được thêm vào primary. Không nên tự sao chép đoạn này để thay thế cú pháp Java: code sinh thật phải xử lý nhiều resource, scopes, khởi tạo, loại exception và các chi tiết ngôn ngữ khác.

Khi nhiều tài nguyên được khai báo, có thể xem về mặt khái niệm như nhiều lớp `try-with-resources` lồng nhau, đảm bảo **thứ tự close ngược**. Cần nhớ resource đã đóng trước khi chạy catch/finally bên ngoài.

Tại sao code generated có thể bắt `Throwable`? Vì nó phải bảo toàn primary bất kể body ném loại Throwable nào, **khác với lời khuyên viết `catch (Throwable)` trong business layer rồi nuốt mọi lỗi**. Đây là chi tiết của cơ chế compiler, không phải chính sách “phục hồi mọi Error”.

## 12. Kiểm thử close khi tài nguyên khởi tạo thất bại

Không chỉ thân try mà **initializer** cũng có thể ném exception:

```java
try (Connection con = openConnection();
     PreparedStatement ps = con.prepareStatement(sql);
     ResultSet rs = ps.executeQuery()) {
    consume(rs);
}
```

Đây là **mảnh code minh họa JDBC**, cần import `java.sql.Connection`, `PreparedStatement`, `ResultSet`, và các phương thức/biến `openConnection`, `sql`, `consume`. Nếu `ps.executeQuery()` ném lỗi khi khởi tạo `rs`:

- `rs` chưa được nhận như resource đã khởi tạo thành công nên không được close bằng header.
- `ps` được đóng.
- `con` được đóng.
- Nếu `ps.close()` và `con.close()` ném, chúng có thể xuất hiện trong suppressed của exception từ `executeQuery()`.

Test unit có thể dùng fake JDBC hoặc mock có kiểm soát, nhưng integration test với driver thật còn cần kiểm tra **semantics transaction, rollback, connection pooling**. Đừng mặc định `Connection.close()` tương đương transaction rollback trong mọi tình huống; nó tùy driver và transaction configuration.

Nếu constructor/factory của một resource ném sau khi mở file descriptor nội bộ, nó phải tự dọn dẹp phần đã cấp phát; TWR không thể gọi close cho biến chưa được gán thành công.

## 13. Thứ tự close với resource lồng nhau và wrapper

Hai cú pháp có thể tương đương về thứ tự nếu không có side effects khác:

```java
try (A a = createA();
     B b = createB(a)) {
    use(b);
}
```

và một cấu trúc lồng:

```java
try (A a = createA()) {
    try (B b = createB(a)) {
        use(b);
    }
}
```

Đều là **mảnh code cần định nghĩa các kiểu/hàm ứng dụng**; `b` đóng trước `a` khi cả hai đã tạo được.

Nhưng một wrapper `B` có thể tự động đóng `A` khi gọi `B.close()`. Khi đó nếu cả hai cũng nằm trong header, `A.close()` có thể được gọi thêm lần nữa. Với những resource có close idempotent, điều này có thể không ảnh hưởng. Với resource khác, double close có thể lỗi hoặc gây side effect. Kiểm thử phải căn cứ **hợp đồng thật của wrapper/delegate**, không chỉ quy tắc ngôn ngữ.

### External resource từ Java 9

Java 9+ cho phép dùng một biến resource đã khai báo trước nếu biến final hoặc effectively final:

```java
InputStream in = Files.newInputStream(path);
try (in) {
    use(in);
}
```

Đây là **mảnh code**, cần import `java.io.InputStream`, `java.nio.file.Files`, và `Path` tương ứng; phương thức bên ngoài phải xử lý `IOException`. Khi ra khỏi `try`, `in` đã được đóng, dù biến vẫn tồn tại. Không tiếp tục sử dụng stream đó như còn mở và không bọc thêm một `try` thứ hai để đóng lại nếu loại resource không cho phép.

Trong mọi trường hợp, thứ tự close vẫn dựa trên **resource specification của từng try**, cùng cấu trúc lồng nhau.

## 14. Resource tham chiếu null, close không idempotent và những trường hợp biên

TWR có thể có một resource reference là `null`:

```java
AutoCloseable maybeResource = null;
try (maybeResource) {
    perform();
}
```

Đây là mảnh code Java 9+ với `perform()` do ứng dụng định nghĩa; nếu `maybeResource` không được gán lại, nó effectively final. Java **không gọi `close()`** trên resource reference null, vì vậy không có `NullPointerException` tự phát sinh chỉ do bước close của tham chiếu ấy.

Tuy nhiên, **không nên coi null resource là API design lý tưởng**. Nếu sự tồn tại resource là điều kiện bắt buộc, kiểm tra sớm bằng `Objects.requireNonNull` hoặc thiết kế factory trả giá trị rõ nghĩa.

Một số tình huống biên cần kiểm thử theo yêu cầu hệ thống:

- `close()` không idempotent: gọi hai lần có thể ném lỗi hoặc làm thay đổi trạng thái.
- `close()` có thứ tự phụ thuộc: wrapper/delegate, transaction/session, stream/filter.
- `close()` block lâu hoặc không trả về: TWR chỉ bảo đảm **cố gọi**, không có deadline mặc định.
- `close()` ném `Error` thay vì checked exception: cơ chế suppression có thể liên quan Throwable loại Error; đừng tự catch rồi tiếp tục.
- `close()` làm thay đổi dữ liệu hoặc flush: thất bại khi close có thể nghiêm trọng dù body thành công.
- Cleanup tự gắn suppressed vào exception qua `addSuppressed`; kiểm tra nội dung thay vì chỉ đếm số lượng.
- Một resource được chia sẻ cho nhiều owner: không để hai owner cùng nghĩ mình chịu trách nhiệm đóng.

Các tình huống lỗi lạ nên được kiểm thử bằng fake resource, còn semantics của driver/native resource cần integration test.

## 15. Các lưu ý về Throwable.addSuppressed

`Throwable.addSuppressed(Throwable exception)` thêm một Throwable thứ cấp vào đối tượng hiện tại. Một số điểm đáng nhớ:

- `getSuppressed()` trả mảng các exception được gắn; không phải `getCause()`.
- `addSuppressed(null)` gây `NullPointerException`.
- Không được tự suppress chính đối tượng Throwable lên nó (*self-suppression*); thao tác có thể ném `IllegalArgumentException`.
- Một số subclass có thể dùng constructor `Throwable` đặc biệt để **tắt cơ chế suppression**; khi đó `getSuppressed()` không giữ các lỗi thêm vào theo cách thông thường.
- Trong code ứng dụng tự quản lý cleanup thủ công, phải cẩn thận giữ exception chính đúng ý nghĩa. Mặc định TWR đã giải quyết trường hợp tiêu chuẩn này tốt hơn.

**Trường hợp cực đoan self-suppression** có thể xảy ra nếu resource `close()` cố tình ném lại **chính instance Throwable** đã được ném từ body. Đây không phải hợp đồng close bình thường. Đừng giả định mọi resource độc hại hoặc sai hợp đồng đều tuân theo mô hình lỗi đơn giản; có thể phát sinh lỗi khác từ thao tác thêm suppressed.

Nói cách khác, tài nguyên nên có exception mới/đúng bản chất khi fail close, không tái sử dụng cùng đối tượng Throwable đang là primary.

## 16. finally và catch ngoài try-with-resources

Xét:

```java
try (Resource r = open()) {
    work();
} catch (Exception ex) {
    inspect(ex.getSuppressed());
} finally {
    recordCompletion();
}
```

Đây là mảnh code có kiểu `Resource`, các hàm `open`, `work`, `inspect`, `recordCompletion`. Khi `catch` nhận exception, Java đã thực hiện nỗ lực `r.close()`. Nếu body lỗi và close cũng lỗi, `catch` có thể đọc suppressed trực tiếp tại thời điểm đó.

**Cảnh báo:** nếu `catch` hoặc `finally` của bạn **tự ném exception mới**, hoặc `recordCompletion()` ném, lỗi được quan sát cuối cùng có thể khác và che nguyên nhân ban đầu nếu không được bảo toàn. `try-with-resources` quản lý lỗi từ **resource close trong header**, không tự bảo toàn mọi exception phát sinh từ mọi `finally` bạn tự viết.

Ví dụ sai:

```java
try (Resource r = open()) {
    work();
} finally {
    throw new IllegalStateException("reporting failed");
}
```

Đây là mảnh **không khuyến nghị**. Nó cố tình ném ở `finally` và có thể làm lỗi primary từ body/close không còn là exception được lan truyền. Khi viết code quan sát/metric/cleanup bổ sung, đảm bảo không vô tình thay thế lỗi quan trọng hoặc làm log trở nên không đáng tin.

## 17. Đọc stack trace và cấu trúc suppressed

Java `Throwable.printStackTrace()` thường hiển thị các suppressed exception với nhãn `Suppressed:`, ví dụ minh họa:

```text
java.lang.IllegalArgumentException: body-failed
    at Demo.work(Demo.java:10)
    Suppressed: java.lang.IllegalStateException: close-C-failed
        at Demo$Resource.close(Demo.java:25)
    Suppressed: java.lang.IllegalStateException: close-B-failed
        at Demo$Resource.close(Demo.java:25)
    Suppressed: java.lang.IllegalStateException: close-A-failed
        at Demo$Resource.close(Demo.java:25)
```

Đây chỉ là **stack trace minh họa**, không phải output của `SuppressedCloseOrderDemo.java` và không bảo đảm số dòng/format. Trong hệ thống thật, trình logging có thể cấu hình giới hạn stack trace; collector hoặc APM có thể làm mất các phần suppressed nếu không hỗ trợ hoặc bị truncate.

Khi điều tra một lỗi, hãy hỏi:

1. Exception chính là lỗi body, initializer hay close?
2. Danh sách suppressed có bao nhiêu phần tử và theo thứ tự nào?
3. Mỗi suppressed có cause/suppressed riêng không?
4. Tài nguyên nào đã đóng, tài nguyên nào chưa bao giờ khởi tạo thành công?
5. Nếu close thất bại, có dữ liệu chưa flush hoặc transaction chưa hoàn tất không?

Trong log chứa dữ liệu thật, kiểm tra chính sách bảo vệ **secret và thông tin cá nhân**: cause/suppressed message từ driver có thể chứa URL, SQL, token hoặc payload. Không tự động đưa toàn bộ Throwable ra HTTP response hoặc các sink rộng quyền chỉ vì muốn kiểm tra suppressed.

## 18. Lỗi thường gặp khi kiểm thử

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Chỉ assert có exception được ném | Không biết đó là lỗi thân hay lỗi close | Assert loại, message/cause, suppressed và event order |
| Cho rằng resource đóng theo thứ tự A → B → C | Trái LIFO của header | Kiểm tra C → B → A |
| Nghĩ close-C lỗi thì không gọi close-B/A | TWR vẫn thử đóng tài nguyên còn lại | Fake resource ghi event của mọi close |
| Kiểm tra suppressed bằng `getCause()` | Cause và suppressed là hai quan hệ khác | Dùng `getSuppressed()` |
| Assert số suppressed mà bỏ qua thứ tự | Không bắt được lỗi đóng sai thứ tự | Assert cả mảng message theo thứ tự |
| Coi tất cả lỗi close luôn là suppressed | Nếu body thành công, lỗi close đầu tiên là primary | Test cả case body thành công |
| Bỏ qua lỗi lúc khởi tạo resource giữa header | Tài nguyên trước phải vẫn được đóng | Test init fail ở A/B/C |
| Dùng close thật từ DB/network để ép lỗi theo timing | Test chậm, flaky, khó dự đoán | Unit test với fake, integration test riêng |
| Bọc `catch (Throwable)` rồi swallow tất cả | Có thể che `Error` và sai kết quả | Dựa vào TWR, phân loại lỗi tại boundary |
| Tự viết `finally` và để close che body exception | Mất nguyên nhân chính | Dùng `try-with-resources` |
| Test bằng full text của stack trace | Phụ thuộc version/dòng source | Assert Throwable API và sự kiện |
| Tưởng close thành công là dữ liệu đã commit bền vững | API tài nguyên có semantics riêng | Test transaction/flush/durability riêng |

## 19. Chiến lược unit test và integration test

**Unit test** là nơi tốt nhất để xác nhận cơ chế Java, dùng resource giả có hành vi được điều khiển:

- Thu danh sách event `open-X`, `body`, `close-X`.
- Tạo lỗi ở body/initializer/close theo cờ.
- Assert loại exception chính, message, `getSuppressed()`, thứ tự gọi.
- Không phụ thuộc kết nối mạng, driver, filesystem hoặc đồng hồ.

**Integration test** kiểm tra thêm contract thực tế của tài nguyên:

- `Connection.close()` dưới connection pool có trả handle về pool hay thực sự đóng kết nối vật lý?
- `ResultSet`, `Statement`, `Connection` có quan hệ tự đóng lẫn nhau không?
- `OutputStream.close()` có flush dữ liệu và báo lỗi không?
- Tài nguyên gắn transaction có rollback/commit ra sao khi close lỗi?
- Socket, file, lock và scheduler có timeout/cancellation phù hợp không?

Không dùng fake resource để “chứng minh” JDBC rollback hoặc file durability; fake chỉ kiểm tra logic code của ứng dụng và ngữ nghĩa Java đã lập trình.

Các bài test liên quan luồng nên có timeout và đồng bộ rõ ràng. Tuy nhiên, quy tắc đóng của **một try-with-resources statement đồng bộ** không cần concurrency để test; tạo nhiều thread không cải thiện độ chính xác của thứ tự resource header và chỉ khiến kết quả khó lặp lại.

## 20. Checklist trước khi hoàn tất một bài kiểm thử

1. Xác định thứ tự resource **khởi tạo thành công** và thứ tự close ngược.
2. Có case **thân lỗi**, **thân thành công nhưng close lỗi**, **initializer lỗi**.
3. Assert exception chính đúng nơi phát sinh.
4. Assert từng phần tử `getSuppressed()` đúng số lượng, nội dung, thứ tự.
5. Xác nhận những tài nguyên đã khởi tạo vẫn được thử đóng sau close failure.
6. Xác nhận tài nguyên không khởi tạo thành công không được close bởi header.
7. Với lỗi cleanup, không nhầm suppressed với cause và không tự động nuốt lỗi.
8. Kiểm tra `catch`/`finally` ngoài TWR không thay thế lỗi gốc.
9. Phân biệt code demo/fake với tác dụng phụ của resource thật.
10. Đọc stack trace, cause và suppressed có kiểm soát để tránh rò thông tin nhạy cảm.
11. Không dùng full stack trace text làm assertion chính của unit test.
12. Với hệ thống có DB/file/network, bổ sung integration test cho flush, rollback, close idempotency và trạng thái sau lỗi.

**Ghi nhớ:** tài nguyên trong `try-with-resources` được **khởi tạo từ trái sang phải, đóng từ phải sang trái**. Nếu body hoặc initializer đã lỗi, lỗi đó thường giữ vai trò **primary**, còn lỗi đóng được lưu bằng `getSuppressed()`. Nếu body thành công, lỗi close đầu tiên trở thành primary. Một phép kiểm thử tốt cần xác nhận **cả thứ tự sự kiện lẫn cấu trúc Throwable** để không đánh mất thông tin lỗi và không tưởng rằng cleanup đã thành công khi thực tế chưa.
