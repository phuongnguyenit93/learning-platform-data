# Kiểm thử `finally` không che lỗi và không thay đổi kết quả ngoài ý muốn

Trong Java, `finally` thường dùng để dọn dẹp sau một khối `try`, bất kể khối đó kết thúc bình thường hay bằng một ngoại lệ. Chính vì được thực thi trên nhiều đường thoát, `finally` rất dễ tạo ra lỗi khó phát hiện: **một câu lệnh `return` trong `finally` có thể ghi đè giá trị trả về hoặc nuốt ngoại lệ đang được truyền**, còn **một ngoại lệ phát sinh khi dọn dẹp có thể che mất ngoại lệ gốc**. Ngoài ra, nếu `finally` thay đổi đối tượng hoặc trạng thái chung, giá trị mà caller nhận được có thể khác với ý định ban đầu dù không có ngoại lệ mới.

Mục tiêu của bài này là xây dựng **kiểm thử hành vi** để phát hiện chính những sai sót ấy. Ta sẽ quan sát thứ tự thực thi của `try`–`catch`–`finally`, phân biệt kết quả trả về với trạng thái của đối tượng, kiểm thử lỗi kép (lỗi xử lý chính và lỗi cleanup), viết test kiểm tra bất biến trạng thái và hiểu khi nào nên dùng `try-with-resources`.

## 1. Hợp đồng cơ bản của `finally`

Cấu trúc thường gặp:

```java
try {
    performOperation();
} catch (ExpectedException error) {
    handleExpectedError(error);
} finally {
    releaseOwnedResource();
}
```

Đây là **mã minh họa**, chưa biên dịch độc lập vì các phương thức và kiểu phụ thuộc phải được ứng dụng định nghĩa.

Các điểm cần nhớ:

1. Nếu `try` kết thúc bình thường và không có câu lệnh khác đổi luồng điều khiển, `finally` được thực thi trước khi tiếp tục phía sau.
2. Nếu `try` chuẩn bị `return` hoặc `throw`, Java cũng thực hiện `finally` trước khi trả về hoặc truyền ngoại lệ ra ngoài.
3. Nếu `catch` chuẩn bị `return` hoặc `throw`, `finally` vẫn chạy trên đường thoát đó.
4. Nếu **chính `finally` kết thúc bất thường** bằng `throw`, `return`, `break` hoặc `continue`, việc hoàn tất đang chờ từ `try`/`catch` có thể bị **thay thế**. Đây là nguồn gây che lỗi hoặc thay đổi kết quả.
5. `finally` không được bảo đảm sẽ chạy trong **mọi** tình huống có thể xảy ra: ví dụ JVM bị chấm dứt đột ngột, tiến trình bị kill, hoặc luồng không bao giờ rời khỏi `try`. Không dùng `finally` làm cam kết tuyệt đối đối với sự cố mất điện hay process crash.

Vì vậy, không chỉ kiểm tra rằng cleanup đã được gọi; còn phải kiểm tra **ngoại lệ nào đến caller**, **giá trị nào được trả**, và **trạng thái nghiệp vụ sau khi dọn dẹp**.

## 2. Những rủi ro phải đưa vào bộ kiểm thử

| Tình huống | Hiện tượng cần nhận diện | Khẳng định kiểm thử |
| --- | --- | --- |
| `try` thành công, `finally` bình thường | Cleanup chạy, kết quả gốc được giữ | Giá trị trả về và số lần cleanup đúng |
| `try` ném lỗi, `finally` bình thường | Lỗi gốc đi đến caller | Đúng loại exception, message, cause/identity cần thiết |
| `try` trả giá trị, `finally` cũng `return` | Giá trị từ `finally` **ghi đè** | Test phải phát hiện kết quả sai |
| `try` ném lỗi, `finally` lại `return` | Ngoại lệ gốc bị **nuốt** | Test kỳ vọng exception phải thất bại |
| `try` ném lỗi, `finally` cũng ném lỗi | Lỗi cleanup có thể **che** lỗi chính | Bảo toàn hoặc báo đầy đủ cả hai lỗi |
| `try` trả tham chiếu đối tượng, `finally` sửa đối tượng ấy | Caller có thể thấy đối tượng đã bị biến đổi | Kiểm tra trạng thái thực, không chỉ tham chiếu |
| `try-with-resources` có lỗi ở thân và `close()` | Lỗi thân thường là lỗi chính, `close()` là suppressed | Kiểm tra `getSuppressed()` |
| Cleanup được gọi nhiều lần hoặc không được gọi | Rò rỉ tài nguyên, thay đổi ngoài ý muốn | Kiểm tra số lần cleanup theo từng đường thoát |

**Quy tắc kiểm thử:** có ít nhất một ca cho đường thành công, một ca cho lỗi ở thao tác chính và một ca cho lỗi khi dọn dẹp. Với mã trả dữ liệu hoặc sửa trạng thái, thêm kiểm thử bất biến và giá trị trả về.

## 3. `return` trong `finally` ghi đè `return` trong `try`

Xét đoạn phương thức:

```java
int calculate() {
    try {
        return 10;
    } finally {
        return 20;
    }
}
```

Phương thức **trả `20`**, không phải `10`. Đây là đoạn Java minh họa có thể đặt trong một lớp, nhưng không phải chương trình độc lập. Tại điểm `return 10`, Java đã quyết định một kết quả đang chờ. Tuy nhiên, câu lệnh `return 20` trong `finally` kết thúc phương thức bằng kết quả mới và thay thế kết quả cũ.

Điều tương tự còn xảy ra với ngoại lệ:

```java
int hideFailure() {
    try {
        throw new IllegalStateException("original failed");
    } finally {
        return 20;
    }
}
```

Trong trường hợp này, caller nhận **`20` như một kết quả bình thường**, còn `IllegalStateException("original failed")` không được truyền ra. Lỗi lập trình nghiêm trọng có thể bị biến thành thành công giả.

**Không đặt `return` trong `finally`.** Nếu một đoạn code sử dụng `finally` chỉ để cleanup, hãy thiết kế cleanup không tham gia quyết định thành công/thất bại của thao tác chính. Test cần khẳng định rằng một lỗi ở `try` vẫn xuất hiện ở caller.

## 4. Ngoại lệ trong `finally` có thể che ngoại lệ gốc

Đoạn sau ném lỗi từ cả hai nơi:

```java
void perform() {
    try {
        throw new IllegalArgumentException("business failed");
    } finally {
        throw new IllegalStateException("cleanup failed");
    }
}
```

Caller thường chỉ bắt được `IllegalStateException("cleanup failed")`. Ngoại lệ `IllegalArgumentException("business failed")` bị thay thế bởi cách `finally` kết thúc bất thường. Java **không tự động đưa lỗi chính vào `getSuppressed()`** trong `try/finally` viết thủ công như trên.

Đây là lý do một phép kiểm thử chỉ dùng `assertThrows(IllegalStateException.class, ...)` có thể **xanh sai**: nó thấy một ngoại lệ nhưng không phát hiện lỗi chính đã bị che. Cần kiểm tra loại lỗi **được hợp đồng mong đợi**, thông điệp hoặc cause/suppressed, và trạng thái sau thao tác.

Nếu cleanup cũng có thể thất bại, cần xác định chính sách:

- Lỗi xử lý chính phải được ưu tiên? Khi đó giữ lỗi chính, đính kèm lỗi cleanup như suppressed nếu thích hợp.
- Chỉ có lỗi cleanup, không có lỗi xử lý? Khi đó lỗi cleanup có thể là lỗi chính cần ném ra.
- Cleanup thất bại nhưng không ảnh hưởng tới hợp đồng của thao tác? Chỉ nên tiếp tục nếu việc bỏ qua lỗi là **được thiết kế rõ**; một lỗi đóng tài nguyên có thể là sự cố mất dữ liệu nên không thể mặc nhiên bỏ qua.
- Khi dùng `AutoCloseable`, ưu tiên `try-with-resources` để Java thực thi quy tắc ưu tiên ngoại lệ cho tình huống thân `try` và `close()` cùng ném lỗi.

## 5. Ví dụ Java 17+ chạy được: phân biệt các đường `return` và `throw`

Tạo tệp **`FinallyControlFlowDemo.java`**:

```java
public class FinallyControlFlowDemo {
    static int safeReturn() {
        try {
            return 10;
        } finally {
            System.out.println("cleanup ran");
        }
    }

    static int overrideReturn() {
        try {
            return 10;
        } finally {
            return 20; // Phản ví dụ: ghi đè kết quả.
        }
    }

    static int swallowFailure() {
        try {
            throw new IllegalArgumentException("original failed");
        } finally {
            return 30; // Phản ví dụ: nuốt ngoại lệ.
        }
    }

    static void maskFailure() {
        try {
            throw new IllegalArgumentException("original failed");
        } finally {
            throw new IllegalStateException("cleanup failed");
        }
    }

    static void preserveFailure() {
        try {
            throw new IllegalArgumentException("original failed");
        } finally {
            System.out.println("cleanup completed");
        }
    }

    static StringBuilder mutableReturn() {
        StringBuilder result = new StringBuilder("initial");
        try {
            return result;
        } finally {
            result.append("-changed");
        }
    }

    public static void main(String[] args) {
        System.out.println("safeReturn=" + safeReturn());
        System.out.println("overrideReturn=" + overrideReturn());
        System.out.println("swallowFailure=" + swallowFailure());

        try {
            maskFailure();
        } catch (RuntimeException error) {
            System.out.println("maskedType="
                    + error.getClass().getSimpleName());
            System.out.println("maskedMessage=" + error.getMessage());
            System.out.println("maskedCause=" + error.getCause());
            System.out.println("maskedSuppressed="
                    + error.getSuppressed().length);
        }

        try {
            preserveFailure();
        } catch (IllegalArgumentException error) {
            System.out.println("preservedMessage=" + error.getMessage());
        }

        System.out.println("mutableReturn=" + mutableReturn());
    }
}
```

Biên dịch, chạy với Java 17:

```bash
javac --release 17 FinallyControlFlowDemo.java
java FinallyControlFlowDemo
```

Đầu ra dự kiến:

```text
cleanup ran
safeReturn=10
overrideReturn=20
swallowFailure=30
maskedType=IllegalStateException
maskedMessage=cleanup failed
maskedCause=null
maskedSuppressed=0
cleanup completed
preservedMessage=original failed
mutableReturn=initial-changed
```

**Những điều ví dụ chứng minh:**

- `safeReturn()` để `finally` dọn dẹp rồi trả **giá trị ban đầu 10**.
- `overrideReturn()` trả **20** dù nhánh `try` định trả 10.
- `swallowFailure()` trả **30** và làm mất hoàn toàn tín hiệu lỗi `original failed` ở ranh giới gọi.
- `maskFailure()` chỉ phơi ra lỗi cleanup và **không tự** đặt lỗi gốc làm cause hoặc suppressed.
- `preserveFailure()` cho lỗi gốc tiếp tục tới caller sau một `finally` kết thúc bình thường.
- `mutableReturn()` cho thấy **tham chiếu đã chọn để trả về** vẫn chỉ vào đối tượng `StringBuilder` mà `finally` vừa sửa. Đừng nhầm việc Java đã chọn giá trị `return` với việc đối tượng mutable được “đóng băng”.

Một khác biệt tinh tế: nếu `try` trả **giá trị nguyên thủy** hoặc một `String` đã được tính xong, việc sửa biến cục bộ trong `finally` thông thường không thay thế giá trị trả về đã đánh giá. Nhưng nếu giá trị trả về là **tham chiếu tới object mutable**, nội dung object có thể thay đổi trước khi caller nhận. Hai trường hợp nên được kiểm tra riêng khi API trả về collection, DTO hay đối tượng mang trạng thái.

## 6. Khi `finally` sửa state, kiểm thử những gì?

Ngoại lệ không phải nguy cơ duy nhất. Một `finally` có thể thực hiện lệnh ghi thông tin, cập nhật bộ đếm, đóng tài nguyên hoặc phát sự kiện. Những thao tác này có thể làm kết quả thực tế khác trạng thái mà nhánh `try` đã chuẩn bị.

Ví dụ phản ví dụ:

```java
OrderResult execute(OrderResult result) {
    try {
        result.markCompleted();
        return result;
    } finally {
        result.markCancelled(); // Làm thay đổi object đã được return.
    }
}
```

Đây là **mã minh họa**, cần khai báo `OrderResult` cùng hai phương thức tương ứng, không phải chương trình độc lập. Caller nhận chính object `result`, nhưng sau khi `finally` chạy, cờ trạng thái có thể là `CANCELLED` thay vì `COMPLETED`. Việc kiểm thử chỉ dùng `assertSame(result, returned)` không phát hiện lỗi; cần kiểm tra **giá trị trạng thái bên trong**.

Với đối tượng chia sẻ giữa nhiều luồng, `finally` còn có thể thay đổi dữ liệu trong khi công việc khác đang truy cập. Cần cơ chế đồng bộ và ranh giới sở hữu rõ, không xem `finally` như phép toán nguyên tử.

Bộ kiểm thử nên xác nhận:

1. Trường nghiệp vụ giữ đúng trạng thái sau `return`.
2. Cleanup chỉ dọn dẹp **tài nguyên thuộc quyền sở hữu**, không vô tình sửa dữ liệu người gọi cần sử dụng.
3. Không có callback, sự kiện hay ghi DB đánh dấu thành công trong `finally` khi `try` thất bại.
4. Trạng thái sau ngoại lệ phù hợp với chính sách rollback hoặc thất bại đã được thiết kế.
5. Việc đóng tài nguyên không làm đối tượng trả về trở nên không thể dùng nếu hợp đồng yêu cầu caller sử dụng nó sau đó.

Một mẫu thường sai:

```java
try {
    persistChanges();
} catch (Exception error) {
    logFailure(error);
} finally {
    publishSuccessEvent();
}
```

Đây là mảnh mã minh họa, cần các phương thức phụ thuộc. `publishSuccessEvent()` chạy cả khi `persistChanges()` thất bại, tạo “thành công giả”. Sự kiện thành công nên được phát sau khi thao tác thực sự commit thành công, không phải vô điều kiện trong `finally`.

## 7. `try-with-resources` giữ lỗi gốc bằng suppressed exceptions

Một rủi ro thường gặp là cả xử lý chính và đóng tài nguyên đều thất bại. Với `try-with-resources`, Java định nghĩa rõ việc xử lý hai lỗi này:

- Nếu thân `try` ném lỗi A và `close()` ném lỗi B, A thường vẫn là **ngoại lệ chính**, B được thêm vào `A.getSuppressed()`.
- Nếu thân `try` thành công nhưng `close()` ném lỗi B, B là ngoại lệ được truyền ra.
- Nếu nhiều tài nguyên đóng thất bại, có thể có nhiều suppressed exceptions. Tài nguyên trong `try-with-resources` được đóng **theo thứ tự ngược lại** với lúc khai báo.
- Suppression là cơ chế báo lỗi phụ, **không phải** phép rollback cho các thay đổi nghiệp vụ.
- Nếu một exception được tạo với suppression bị tắt thì cách lưu lỗi phụ có thể khác; không nên giả định mọi `Throwable` tùy biến luôn chứa suppressed errors.

Một ví dụ rút gọn:

```java
try (SomeResource resource = openResource()) {
    performBody(resource);
}
```

Đây là mã minh họa chưa độc lập vì cần kiểu `SomeResource` (triển khai `AutoCloseable`) và các phương thức `openResource()`, `performBody(...)`.

So sánh với một khối `finally` thủ công:

```java
try {
    performBody();
} finally {
    resource.close();
}
```

Đây cũng chỉ là mã minh họa. Nếu cả `performBody()` và `resource.close()` đều ném ngoại lệ, lời gọi `close()` trong `finally` có thể **che** lỗi của `performBody()`. Không có quy tắc tự động chuyển lỗi cleanup vào suppressed như trong `try-with-resources`. Cần thay đổi thiết kế để bảo toàn lỗi chính.

## 8. Ví dụ Java 17+ chạy được: một bộ kiểm thử tự chứa cho cleanup

Ví dụ sau dùng các hàm assertion nhỏ trong `main`, không yêu cầu JUnit hay thư viện bên ngoài. Nó kiểm tra bốn đường đi của `try-with-resources`: thành công, chỉ lỗi thân `try`, chỉ lỗi đóng tài nguyên, và **cả hai cùng lỗi**. Nó cũng xác nhận tài nguyên đã được đóng và số lần đóng.

Tạo tệp **`FinallyCleanupContractDemo.java`**:

```java
import java.io.IOException;
import java.util.concurrent.atomic.AtomicReference;

public class FinallyCleanupContractDemo {
    static final class Resource implements AutoCloseable {
        final boolean failOnClose;
        int closeCount;

        Resource(boolean failOnClose) {
            this.failOnClose = failOnClose;
        }

        @Override
        public void close() throws IOException {
            closeCount++;
            if (failOnClose) {
                throw new IOException("close failed");
            }
        }
    }

    static void execute(
            boolean failBody,
            boolean failClose,
            AtomicReference<Resource> reference) throws IOException {
        Resource resource = new Resource(failClose);
        reference.set(resource);

        try (resource) {
            if (failBody) {
                throw new IOException("body failed");
            }
        }
    }

    static void require(boolean condition, String explanation) {
        if (!condition) {
            throw new AssertionError(explanation);
        }
    }

    static void verify(
            boolean failBody, boolean failClose,
            String expectedPrimary, int expectedSuppressed) {
        AtomicReference<Resource> reference = new AtomicReference<>();
        IOException caught = null;

        try {
            execute(failBody, failClose, reference);
        } catch (IOException error) {
            caught = error;
        }

        Resource resource = reference.get();
        require(resource != null, "resource was not created");
        require(resource.closeCount == 1, "close must execute exactly once");

        if (expectedPrimary == null) {
            require(caught == null, "unexpected IOException");
        } else {
            require(caught != null, "expected IOException");
            require(expectedPrimary.equals(caught.getMessage()),
                    "wrong primary exception");
            require(caught.getSuppressed().length == expectedSuppressed,
                    "wrong suppressed count");
            if (expectedSuppressed == 1) {
                require("close failed".equals(
                        caught.getSuppressed()[0].getMessage()),
                        "wrong suppressed exception");
            }
        }
    }

    public static void main(String[] args) {
        verify(false, false, null, 0);
        System.out.println("success: PASS");

        verify(true, false, "body failed", 0);
        System.out.println("body failure: PASS");

        verify(false, true, "close failed", 0);
        System.out.println("close failure: PASS");

        verify(true, true, "body failed", 1);
        System.out.println("dual failure preserves body: PASS");
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 FinallyCleanupContractDemo.java
java FinallyCleanupContractDemo
```

Đầu ra khi tất cả điều kiện đều đúng:

```text
success: PASS
body failure: PASS
close failure: PASS
dual failure preserves body: PASS
```

Nếu một điều kiện vi phạm, chương trình ném `AssertionError` và không in dòng `PASS` tương ứng.

**Điểm đáng học từ cấu trúc test:**

- `AtomicReference<Resource>` cho phép test kiểm tra `Resource` được tạo bên trong hàm `execute`. Ở ví dụ tuần tự này nó chủ yếu là một cách chuyển tham chiếu ra ngoài để kiểm tra, **không chứng minh tính nguyên tử cho một nghiệp vụ nhiều luồng**.
- `closeCount == 1` kiểm tra cleanup được thực hiện đúng số lần ở cả đường thành công và đường lỗi.
- `expectedPrimary` kiểm tra **thông điệp của lỗi chính**, không chỉ kiểm tra “có lỗi”.
- Khi `failBody && failClose`, test bắt buộc `body failed` là lỗi chính và `close failed` nằm trong `getSuppressed()` của chính lỗi đó.
- Khi chỉ `close()` thất bại, test cho phép lỗi cleanup trở thành **lỗi chính** vì không có lỗi thân `try` cần được ưu tiên.

Kiểm thử kiểu này hữu ích hơn `try { execute(); } catch (Exception ignored) {}`: nó làm rõ hợp đồng lỗi và sẽ thất bại nếu một refactor của cleanup vô tình che ngoại lệ gốc.

## 9. Nếu bắt buộc phải dùng `finally` thủ công, bảo toàn lỗi chính thế nào?

Có những tài nguyên không triển khai `AutoCloseable`, hoặc ứng dụng phải thực hiện cleanup đặc biệt. Khi đó không nên chỉ thêm `finally { close(); }` rồi cho rằng tình huống lỗi kép đã được xử lý.

Một phương án về mặt khái niệm là:

1. Ghi nhận lỗi chính khi nó được ném.
2. Khi cleanup thất bại, nếu **đã có lỗi chính**, gắn lỗi cleanup vào nó bằng `addSuppressed(...)` (khi phù hợp).
3. Nếu **không có lỗi chính**, để lỗi cleanup được truyền ra theo hợp đồng.
4. Không dùng `return` trong `finally` và không tạo ngoại lệ mới chỉ từ `getMessage()` làm mất cause.

Đoạn Java minh họa bên trong một phương thức được phép truyền `Exception`:

```java
Exception primary = null;
try {
    doWork();
} catch (Exception failure) {
    primary = failure;
    throw failure;
} finally {
    try {
        cleanup();
    } catch (Exception cleanupFailure) {
        if (primary != null) {
            primary.addSuppressed(cleanupFailure);
        } else {
            throw cleanupFailure;
        }
    }
}
```

Đoạn trên **không phải chương trình độc lập** vì cần `doWork()` và `cleanup()` được ứng dụng khai báo; chữ ký phương thức bao quanh phải phù hợp với các checked exception. Đây là mẫu đơn giản cho các trường hợp lỗi thuộc `Exception`.

**Giới hạn quan trọng:** nếu `doWork()` ném `Error` chứ không phải `Exception`, nhánh `catch (Exception ...)` không giữ nó vào `primary`; một `Exception` từ cleanup trong `finally` khi đó có thể che `Error`. Không nên tự mở rộng thành `catch (Throwable)` tùy tiện nếu không thực sự hiểu hợp đồng và chính sách xử lý `Error`. Khi tài nguyên thích hợp, **`try-with-resources` thường là lựa chọn an toàn, rõ ràng hơn**.

Tránh thêm suppressed exception trùng hoặc tự thêm chính throwable vào chính nó. `addSuppressed(this)` bị từ chối. Cũng đừng biến lỗi cleanup thành “chỉ log và bỏ qua” trong mọi trường hợp: đôi khi cleanup lỗi là dấu hiệu dữ liệu chưa được ghi/đóng an toàn.

## 10. Kiểm thử `finally` với JUnit 5

Trong dự án có JUnit 5, các assertion giúp biểu đạt trực tiếp yêu cầu. Ví dụ sau là **mảnh test minh họa**, cần dependency JUnit 5, import `org.junit.jupiter.api.Test` và các assertion từ `org.junit.jupiter.api.Assertions`, đồng thời cần các phương thức/kiểu `service` tương ứng. Nó **không phải** chương trình Java chạy độc lập chỉ với JDK:

```java
@Test
void cleanupDoesNotMaskOriginalFailure() {
    IllegalArgumentException failure = assertThrows(
            IllegalArgumentException.class,
            () -> service.executeWithCleanupFailure());

    assertEquals("operation failed", failure.getMessage());
    assertEquals(1, failure.getSuppressed().length);
    assertEquals("cleanup failed",
            failure.getSuppressed()[0].getMessage());
}
```

Ca này phát hiện được lỗi **ngoại lệ gốc bị che**. Nếu `finally` ném `IllegalStateException` thay vì giữ lỗi chính, `assertThrows(IllegalArgumentException.class, ...)` sẽ thất bại.

Kiểm thử kết quả trả về:

```java
@Test
void cleanupDoesNotReplaceReturnValue() {
    int value = service.computeAndClose();
    assertEquals(10, value);
}
```

Ca này bắt được việc một người sau đó thêm `return 20` vào `finally`.

Kiểm thử trạng thái đối tượng mutable:

```java
@Test
void returnedResultIsNotMutatedByCleanup() {
    Result result = service.process();
    assertEquals(Status.COMPLETED, result.status());
    assertFalse(result.isClosedUnexpectedly());
}
```

Ca này yêu cầu các lớp `Result`, `Status` và service cụ thể. Nó giúp bắt lỗi mà `assertSame(...)` hoặc kiểm tra non-null đơn giản không phát hiện.

Kiểm thử cleanup đúng một lần:

```java
@Test
void cleanupRunsOnFailure() {
    assertThrows(IllegalArgumentException.class,
            () -> service.failAfterOpeningResource());

    verify(resource).close();
}
```

Ví dụ cuối **giả định** có Mockito hoặc cơ chế spy tương tự để cung cấp `verify(resource).close()`; Mockito không có sẵn trong JDK/JUnit. Nếu không dùng mock framework, một fake resource với bộ đếm như `FinallyCleanupContractDemo` sẽ minh bạch và tránh thêm dependency.

**Không kiểm thử bằng cách chỉ nhìn stdout** nếu hệ thống có state hoặc side effect quan trọng. `assertThrows`, số lần `close`, trạng thái sau lỗi, giá trị trả về và cause/suppressed nên được khẳng định trực tiếp.

## 11. Ma trận kiểm thử đầy đủ cho một tác vụ có cleanup

Ví dụ nghiệp vụ: mở resource, tính một kết quả, đóng resource và trả kết quả. Hãy thiết kế các ca sau:

| Thân thao tác | Cleanup | Kết quả kỳ vọng | Điều cần khẳng định |
| --- | --- | --- | --- |
| Thành công | Thành công | Trả kết quả thật | Kết quả không đổi, close đúng một lần |
| Thất bại | Thành công | Ném lỗi thao tác chính | Không có thành công giả, giữ lỗi gốc |
| Thành công | Thất bại | Theo hợp đồng: báo lỗi cleanup | Không âm thầm trả thành công khi cleanup quan trọng |
| Thất bại | Thất bại | Giữ lỗi thao tác chính, đính lỗi cleanup | Primary/cause/suppressed đúng |
| `try` có `return` | `finally` có thay đổi biến cục bộ | Không thay kết quả đã tính nếu không có `return` mới | Giá trị trả về chính xác |
| `try` trả object mutable | Cleanup sửa object | Theo hợp đồng đối tượng vẫn hợp lệ | Trường dữ liệu/state sau lời gọi |
| `try` ném lỗi | `finally` định `return` | Không được nuốt lỗi | Test phải thất bại nếu không ném |
| Cleanup được gọi hai lần | Lỗi đóng tài nguyên có thể xảy ra | Không đóng lặp ngoài ý muốn | Số lần gọi close/rollback |
| Tác vụ bị ngắt | Cleanup chạy rồi truyền ngắt đúng | Tín hiệu hủy không bị che | Chính sách `InterruptedException` và interrupted status |
| Nhiều resource cùng đóng | Một hoặc nhiều `close()` lỗi | Báo đúng lỗi chính và lỗi phụ | Số/loại suppressed, thứ tự đóng theo hợp đồng |

Bảng là **ma trận thiết kế test**; không phải mọi dự án phải có 10 test riêng biệt nếu các ca đã được bao phủ ở tầng thích hợp. Nhưng đường lỗi kép rất quan trọng: chỉ kiểm tra thành công và lỗi đơn lẻ không đủ để phát hiện lỗi bị che bởi cleanup.

## 12. Ngoại lệ phát sinh ở `catch` cũng có thể bị `finally` che

Đôi khi nhánh `catch` chuyển lỗi kỹ thuật thành một ngoại lệ nghiệp vụ:

```java
try {
    repository.load();
} catch (IOException cause) {
    throw new IllegalStateException("Cannot load", cause);
} finally {
    closeConnection();
}
```

Đây là đoạn minh họa không độc lập (`repository` và `closeConnection` do ứng dụng cung cấp). Nếu `closeConnection()` cũng ném, ngoại lệ cleanup có thể **thay thế** cả `IllegalStateException` mà `catch` vừa tạo. Vì vậy test nên đặt lỗi cho `closeConnection()` ngay cả khi nhánh `catch` đã có chính sách chuyển lỗi.

Dùng `try-with-resources` có thể bảo toàn lỗi đang truyền từ thân `try` hoặc `catch` tùy cấu trúc cụ thể. Để biết chính xác ngoại lệ nào là primary và suppressed trong mã thực tế, cần xem **phạm vi cú pháp của tài nguyên và khối `catch`** chứ không giả định mọi lệnh close đều được ưu tiên giống nhau.

Một nguyên tắc hữu ích: khi chuyển lỗi thành wrapper, giữ cause trong constructor, sau đó bảo đảm cleanup không cắt đi wrapper vừa được tạo.

## 13. `finally` và transaction/rollback: kiểm tra hậu điều kiện

Với đơn vị công việc có giao dịch, một cách thiết kế là:

```java
beginTransaction();
try {
    performBusinessChanges();
    commitTransaction();
} catch (Exception original) {
    rollbackTransaction();
    throw original;
} finally {
    closeTransactionResource();
}
```

Đoạn này **chỉ minh họa luồng điều khiển**, không thể biên dịch độc lập nếu không có các hàm và khai báo `throws` tương ứng. Quan trọng hơn: cả `rollbackTransaction()` trong `catch` lẫn `closeTransactionResource()` trong `finally` **đều có thể ném lỗi**, làm thay thế `original`. Chính sách đúng thường cần giữ nguyên lỗi thao tác và báo lỗi cleanup/rollback như thông tin bổ sung khi lỗi kép xảy ra.

Test tích hợp nên kiểm tra **dữ liệu thật** sau thất bại, không chỉ ngoại lệ:

- Nếu bước ghi DB lỗi, transaction không vô tình commit phần còn lại.
- Nếu rollback cũng lỗi, báo được cả lý do thất bại ban đầu và tình trạng rollback chưa chắc thành công.
- Nếu `finally` dọn kết nối, không có lệnh `commit` hoặc công bố thành công ngoài ý muốn.
- Nếu các hệ thống bên ngoài đã nhận tác dụng phụ, cần đối soát/idempotency/compensation; `finally` không tự hoàn tác HTTP request hay message đã gửi.

Một `finally` kết thúc bình thường **không bảo đảm trạng thái nghiệp vụ tự động trở lại như cũ**. Việc khẳng định trạng thái hậu điều kiện trong test là cách phát hiện sự khác nhau giữa “đã dọn resource” và “đã phục hồi dữ liệu”.

## 14. `InterruptedException` và cleanup

Tác vụ đang chờ có thể nhận `InterruptedException`. Khi xử lý ngắt, `finally` thường vẫn chạy để giải phóng tài nguyên. Nhưng một lỗi trong cleanup có thể làm mất tín hiệu ngắt hoặc thay ngoại lệ ngắt bằng loại khác, khiến tầng gọi tưởng tác vụ thất bại vì nguyên nhân không liên quan.

Nếu phương thức cho phép `throws InterruptedException`, thường nên truyền tiếp ngắt theo hợp đồng. Nếu không thể truyền, có thể cần khôi phục cờ bằng `Thread.currentThread().interrupt()` rồi rời công việc thích hợp; không được tự ý nuốt tín hiệu hủy chỉ để “tiếp tục bình thường”.

Ví dụ minh họa bên trong một phương thức:

```java
try {
    blockingWork();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
} finally {
    releaseResource();
}
```

Đây là mảnh mã cần `blockingWork()` và `releaseResource()`. Dù `catch` định `return`, `finally` vẫn chạy; nếu cleanup ném ngoại lệ unchecked, nó sẽ làm phương thức không trở về bình thường. Chính sách xử lý có thể cần giữ và ghi nhận cả lỗi cleanup lẫn trạng thái ngắt, thay vì mặc định rằng mọi lệnh dọn dẹp đều thành công.

Khi kiểm thử, phải tạo ngắt bằng công cụ đồng bộ như `CountDownLatch` thay vì dựa vào `Thread.sleep(10)` và timing ngẫu nhiên. Test nên xác nhận thao tác kết thúc, resource được giải phóng và interrupted status được giữ/khôi phục đúng chính sách.

## 15. Tránh những assertion quá yếu

Những bài test sau rất dễ bỏ sót lỗi thật:

```java
assertNotNull(service.process());
```

```java
assertThrows(Exception.class, () -> service.run());
```

```java
try {
    service.run();
} catch (Exception ignored) {
    // Chỉ cần “không crash” là pass?
}
```

Đây là các đoạn minh họa không độc lập, cần JUnit/ứng dụng cụ thể. Các dạng này không xác định rõ **kết quả nào đúng**, **ngoại lệ nào phải tồn tại**, **tài nguyên có đóng đủ**, hoặc **trạng thái có bị thay đổi sai**.

Nên thay bằng:

- Assert kiểu exception chính xác nếu đó là hợp đồng.
- Assert message hoặc mã lỗi có ý nghĩa thay vì chỉ `assertNotNull(error)`.
- Assert `getCause()` và `getSuppressed()` khi có thể phát sinh lỗi kép.
- Assert số lần cleanup, không chỉ việc cleanup đã từng chạy.
- Assert hậu điều kiện của state khi kết thúc bình thường **và** khi có lỗi.
- Assert không phát sinh sự kiện “SUCCESS” trên đường thất bại.
- Dùng test doubles/fakes để gây lỗi có kiểm soát trong `close()`, `rollback()` và các điểm cleanup khác.

Không nên bắt `Throwable` vô điều kiện trong code nghiệp vụ chỉ để “bao phủ mọi thứ” cho test. Trong test, `assertThrows` thường nhận một `Class` cụ thể; không biến `AssertionError` bị ném bởi framework test thành kết quả thành công giả.

## 16. Các lỗi thường gặp khi review code

| Sai lầm | Hệ quả | Cách phòng tránh |
| --- | --- | --- |
| `return` trong `finally` | Ghi đè kết quả hoặc nuốt ngoại lệ | Không `return` trong finally; test đường thành công/lỗi |
| `throw` mới từ `finally` mà không giữ lỗi cũ | Ngoại lệ cleanup che lỗi chính | Dùng `try-with-resources` hoặc xử lý suppressed có chủ đích |
| `finally` cập nhật cờ thành công | Báo thành công dù thao tác thất bại | Chỉ cập nhật trạng thái thành công sau commit thật |
| Sửa object mutable đã được return | Caller thấy object khác ý định | Kiểm tra nội dung object và quyền sở hữu |
| Cleanup không được gọi trên đường lỗi | Rò tài nguyên | Fake resource theo dõi số lần close |
| Cleanup được gọi nhiều lần | Double-close, tác dụng phụ bất ngờ | Kiểm tra số lần và tính idempotent |
| Nuốt ngoại lệ trong test | Test “xanh” dù lỗi xảy ra | Assert loại exception, cause, suppressed |
| `assertThrows(Exception.class, ...)` cho mọi ca | Sai loại lỗi vẫn có thể pass | Assert loại phù hợp và nội dung cần thiết |
| Nhầm `finally` với rollback transaction | Dữ liệu đã sửa vẫn còn | Test cả DB state/side effect |
| Bắt `InterruptedException` rồi cleanup che lỗi | Mất tín hiệu hủy | Test trạng thái ngắt và truyền lỗi đúng |
| Tin `finally` luôn chạy dù JVM bị kill | Không có đảm bảo cleanup khi process chấm dứt đột ngột | Thiết kế phục hồi/timeout ngoài tiến trình khi cần |

## 17. Checklist thiết kế bộ test

Trước khi chấp nhận một thay đổi có `finally`, tự hỏi:

1. Đã kiểm thử **kết quả trả về** của đường thành công chưa?
2. Đã kiểm thử **ngoại lệ chính** của đường thất bại chưa?
3. Nếu cleanup ném, test có chứng minh lỗi chính **không bị che** không?
4. Nếu chỉ cleanup lỗi, lỗi ấy có được báo trung thực không?
5. Nếu `try` trả object, `finally` có sửa/đóng object đó không? Test có quan sát được không?
6. Tài nguyên có luôn được giải phóng **đúng một lần** không?
7. Có bất kỳ lệnh `return`, `break`, `continue`, `throw` hoặc đổi trạng thái nghiệp vụ nào trong `finally` cần đánh giá lại không?
8. Nếu dùng `try-with-resources`, test có kiểm tra `getSuppressed()` khi cả body và `close()` lỗi không?
9. Có kịch bản transaction rollback lỗi hoặc I/O cleanup lỗi khiến việc chẩn đoán bị thay thế không?
10. Bộ test có dùng dữ liệu và bộ đếm độc lập thay vì dựa vào thứ tự thread/timing khó dự đoán không?

## 18. Tự kiểm tra

**Câu 1.** `try { return 1; } finally { return 2; }` trả gì?  
**Trả lời:** `2`. `return` từ `finally` thay kết quả đang chờ ở `try`.

**Câu 2.** `try` ném `IOException` nhưng `finally` ném `IllegalStateException`. Caller thường thấy gì?  
**Trả lời:** Ngoại lệ phát sinh từ `finally`, trừ khi mã chủ động bảo toàn lỗi chính. `try/finally` thủ công không tự gắn lỗi cũ làm suppressed.

**Câu 3.** `try` trả một `ArrayList`, `finally` thêm phần tử vào chính list đó. Caller có thể thấy phần tử mới không?  
**Trả lời:** Có. Caller nhận tham chiếu đến đối tượng đã bị thay đổi.

**Câu 4.** Trong `try-with-resources`, body ném `IOException("read")`, `close()` ném `IOException("close")`. Ngoại lệ chính thường là gì?  
**Trả lời:** Lỗi `read`; lỗi `close` được thêm vào `getSuppressed()` của lỗi chính.

**Câu 5.** Vì sao chỉ kiểm tra `assertThrows(Exception.class, ...)` là yếu?  
**Trả lời:** Vì một exception hoàn toàn khác do cleanup gây ra cũng có thể thỏa assertion, dù lỗi gốc bị che.

**Câu 6.** Cleanup chạy trong `finally` và tất cả resource đã đóng. Có chứng minh transaction thành công không?  
**Trả lời:** Không. Dọn tài nguyên và thành công nghiệp vụ là hai điều khác nhau; phải xác nhận hậu điều kiện hoặc rollback/commit.

**Câu 7.** `finally` có luôn chạy khi JVM bị cưỡng bức chấm dứt không?  
**Trả lời:** Không. Nó hoạt động theo luồng điều khiển Java thông thường, không phải đảm bảo phục hồi ở cấp tiến trình.

**Câu 8.** Khi cả xử lý chính và cleanup đều có thể lỗi, nên thử thiết kế gì trước?  
**Trả lời:** `try-with-resources` nếu tài nguyên triển khai `AutoCloseable`, cùng kiểm thử primary/suppressed, số lần close và trạng thái sau lỗi.

**Câu 9.** `return` đã được tính là một giá trị nguyên thủy, rồi `finally` sửa biến cục bộ; giá trị trả về tự đổi không?  
**Trả lời:** Không, nếu `finally` kết thúc bình thường và không có return/throw thay thế. Ngược lại, đối tượng mutable được trả theo tham chiếu vẫn có thể bị chỉnh sửa.

**Câu 10.** Làm sao phát hiện `finally` đã phát sự kiện `SUCCESS` dù `try` thất bại?  
**Trả lời:** Dùng fake publisher hoặc event collector trong test, gây lỗi có kiểm soát ở body rồi assert không có sự kiện thành công và trạng thái nghiệp vụ được bảo toàn.

## 19. Tham khảo

- [Java Language Specification §14.20 — `try` statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): thứ tự và quy tắc hoàn tất của `try`, `catch`, `finally`, `try-with-resources`.
- [Java SE 17 — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, `getSuppressed()`, `addSuppressed()` và stack trace.
- [Java SE 17 — `AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng `close()` của tài nguyên.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): cách kiểm thử bằng `assertThrows`, assertion và test doubles (cần dependency bên ngoài JDK).

**Ghi nhớ:** `finally` là nơi dọn dẹp, **không phải nơi tự ý quyết định lại kết quả**. Test phải chứng minh được ba điều: kết quả hợp lệ **không bị thay**, lỗi chính **không bị che**, và tài nguyên/trạng thái **được xử lý đúng trên mọi đường thoát**. Đặc biệt cần kiểm thử tình huống body và cleanup cùng thất bại, vì đây là nơi những lỗi khó tìm nhất thường xuất hiện.