# Kiểm thử đường thành công và đường thất bại theo hợp đồng trong Java

Một phương thức Java không chỉ có *đường thành công* (*happy path*); hợp đồng của nó còn quy định điều gì xảy ra khi đầu vào không hợp lệ, tài nguyên thiếu, I/O lỗi hoặc thao tác bất đồng bộ thất bại. Nếu test chỉ kiểm tra “gọi được và trả kết quả đúng”, những lỗi như ném sai loại exception, mất `cause`, vô tình nuốt lỗi hoặc để trạng thái dở dang rất dễ lọt vào production.

Bài thuộc **Java Core – Exception / Kiểm thử**, dành cho **Java 17+**. Mục tiêu là viết test xác minh **đúng hợp đồng** ở cả hai đường: kết quả trả về và side effect khi thành công; loại lỗi, nội dung quan trọng, cause/suppressed và trạng thái sau lỗi khi thất bại. Các chương trình Java thuần bên dưới biên dịch/chạy trực tiếp bằng `javac`/`java`; phần JUnit 5 được ghi rõ là ví dụ sử dụng thư viện kiểm thử.

## 1. Hợp đồng của phương thức không chỉ là kiểu trả về

Hãy xem API:

```java
int calculateTotal(int unitPrice, int quantity)
```

Một chữ ký như vậy chưa nói hết hợp đồng. Ứng dụng cần quyết định:

- **Điều kiện đầu vào hợp lệ:** ví dụ `unitPrice >= 0`, `quantity > 0`.
- **Kết quả thành công:** tổng tiền được tính thế nào; có giới hạn tràn số không?
- **Điều kiện thất bại:** đầu vào sai; kết quả vượt giới hạn; dependency lỗi.
- **Loại lỗi:** `IllegalArgumentException`, `ArithmeticException`, `IOException`, exception nghiệp vụ...
- **Thông tin lỗi:** message hoặc mã lỗi nào là phần ổn định của API?
- **Trạng thái sau lỗi:** có cập nhật dở dữ liệu, giữ khóa, để mở tài nguyên, đã gửi request ngoài chưa?
- **Tín hiệu đặc biệt:** cancellation, interrupt hoặc timeout nếu API có hỗ trợ.
- **Thứ tự và phạm vi side effect:** điều kiện nào phải được kiểm tra *trước khi* tác động lên trạng thái?

Một test đúng không phải test khiến code đang có “xanh” bằng mọi giá. Nó phải đối chiếu code với **hợp đồng mong muốn** đã được xác định độc lập.

Đối chiếu minh họa:

| Tình huống | Đầu vào/thiết lập | Điều cần xác minh |
|---|---|---|
| Thành công điển hình | `unitPrice=100`, `quantity=2` | Trả `200`, không ném |
| Thành công ở biên hợp lệ | `unitPrice=0`, `quantity=1` | Trả `0` nếu hợp đồng cho phép |
| Thất bại do số lượng | `quantity=0` | Ném `IllegalArgumentException` |
| Thất bại do giá | `unitPrice=-1` | Ném loại lỗi được quy định |
| Tràn số | `unitPrice=Integer.MAX_VALUE`, `quantity=2` | Không âm thầm trả giá trị sai; báo lỗi đúng chính sách |
| Dependency gặp lỗi | Kho dữ liệu giả ném `IOException` | Giữ/biến đổi exception đúng hợp đồng, không báo thành công |
| Cleanup gặp lỗi | Thân công việc và `close()` cùng ném | Lỗi chính được bảo toàn, lỗi đóng nằm ở `Suppressed` nếu dùng TWR |

**Test cả hai đường không nhất thiết nghĩa là số lượng case 50/50.** Số test phải theo **các nhánh và cam kết của API**, đặc biệt các ranh giới có rủi ro cao.

## 2. Đường thành công: cần khẳng định điều gì?

Test happy path phải **khẳng định kết quả**, không chỉ “không xảy ra exception”. Tùy phương thức, hãy kiểm tra:

1. Giá trị trả về hoặc dữ liệu được tạo ra.
2. Trạng thái đối tượng sau thao tác.
3. Side effect cần xảy ra: lưu dữ liệu, tăng counter, gọi dependency.
4. Side effect **không được xảy ra**: không ghi trùng, không gọi fallback khi không cần.
5. Tính bất biến của đối tượng/đầu vào nếu hợp đồng quy định.
6. Tài nguyên được đóng hoặc chuyển quyền sở hữu đúng ranh giới.

Ví dụ test quá yếu:

```java
service.createOrder(validRequest);
```

Đây chỉ là mảnh code minh họa. Nó không chứng minh đơn hàng đã được tạo đúng số tiền hay đã được lưu. Test cần đọc kết quả hoặc kiểm tra trạng thái quan sát được:

```java
Order order = service.createOrder(validRequest);
assertEquals(expectedTotal, order.total());
```

Đây là **ví dụ tích hợp JUnit**, giả định các kiểu `service`, `Order`, `validRequest`, `expectedTotal` đã được định nghĩa và có `assertEquals` từ JUnit. Trong test thực, cần kiểm tra trạng thái quan trọng thay vì lặp lại chính thuật toán trong expected value; nếu viết cùng một công thức sai cả trong production lẫn test, test vẫn có thể xanh.

Một nguyên tắc hữu ích: **mỗi assertion phải trả lời một cam kết của hợp đồng**. Đừng assert mọi chi tiết nội bộ của implementation, vì refactor đúng vẫn phải giữ nguyên hợp đồng công khai.

## 3. Đường thất bại: kiểm tra nhiều hơn việc có exception

Trên failure path, các lớp kiểm tra thường gồm:

- **Exception type:** API phải ném loại đã hứa, không ném một `NullPointerException` tình cờ vì bug.
- **Message hoặc mã lỗi:** chỉ kiểm tra phần ổn định, có ý nghĩa đối với caller.
- **Cause:** khi tầng cao bọc exception, lỗi gốc còn nằm trong `getCause()` không?
- **Suppressed:** nếu cleanup cũng thất bại, có giữ được lỗi thứ cấp không?
- **Không có kết quả thành công giả:** không trả giá trị mặc định khiến caller tưởng thao tác đã hoàn tất.
- **Không có side effect cấm:** validation sai không làm trừ tiền, ghi dở dữ liệu hoặc đổi state sai.
- **Tài nguyên được giải phóng:** `close`, `unlock`, rollback hoặc release theo hợp đồng.
- **Lỗi chỉ xuất hiện trong đúng phạm vi:** không để một exception từ dependency khác tình cờ làm test “đạt”.

Ví dụ test yếu:

```java
assertThrows(Exception.class, () -> repository.load("bad-id"));
```

Mảnh này là cú pháp JUnit 5, không phải chương trình chạy độc lập. Nó có thể chấp nhận rất nhiều lỗi không mong muốn. Nếu hợp đồng chỉ cho `IllegalArgumentException` khi mã đầu vào không hợp lệ, hãy dùng:

```java
IllegalArgumentException error = assertThrows(
        IllegalArgumentException.class,
        () -> repository.load("bad-id"));
```

Sau đó kiểm tra message/mã lỗi quan trọng và nếu có state, kiểm tra state không bị thay đổi.

`assertThrows(Expected.class, executable)` của JUnit 5 chấp nhận cả **subclass của loại expected**. Khi hợp đồng thực sự yêu cầu đúng class cụ thể, hãy xem xét `assertThrowsExactly` (nếu phiên bản JUnit hỗ trợ) hoặc so sánh `error.getClass()`.

## 4. Ví dụ Java 17 độc lập: kiểm thử hợp đồng đầu vào và kết quả

Tạo tệp `PriceContractTest.java`. Đây là một bộ test thuần JDK với `main`, không cần JUnit.

```java
public class PriceContractTest {
    static int total(int price, int quantity) {
        if (price < 0) {
            throw new IllegalArgumentException("price must be >= 0");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be > 0");
        }
        return Math.multiplyExact(price, quantity);
    }

    static void check(boolean condition, String description) {
        if (!condition) {
            throw new AssertionError(description);
        }
    }

    static void expectIllegalArgument(
            Runnable action, String expectedMessage) {
        try {
            action.run();
            throw new AssertionError("Expected IllegalArgumentException");
        } catch (IllegalArgumentException e) {
            check(expectedMessage.equals(e.getMessage()),
                    "Wrong message: " + e.getMessage());
        }
    }

    public static void main(String[] args) {
        check(total(100, 2) == 200, "Wrong normal total");
        System.out.println("success: normal");

        check(total(0, 1) == 0, "Wrong boundary total");
        System.out.println("success: boundary");

        expectIllegalArgument(() -> total(-1, 2),
                "price must be >= 0");
        System.out.println("failure: negative price");

        expectIllegalArgument(() -> total(10, 0),
                "quantity must be > 0");
        System.out.println("failure: invalid quantity");

        try {
            total(Integer.MAX_VALUE, 2);
            throw new AssertionError("Expected ArithmeticException");
        } catch (ArithmeticException expected) {
            System.out.println("failure: overflow");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac PriceContractTest.java
java PriceContractTest
```

Đầu ra:

```text
success: normal
success: boundary
failure: negative price
failure: invalid quantity
failure: overflow
```

Cách test hoạt động:

- Hai trường hợp thành công kiểm tra **kết quả cụ thể**.
- Hai trường hợp invalid input kiểm tra đúng **loại lỗi** và message do chính API quy định.
- `Math.multiplyExact` phát hiện overflow, cho phép test xác nhận lỗi thay vì âm thầm nhận một số sai.
- `check` ném `AssertionError` nếu invariant bị vi phạm. Đây là bộ test **chủ động kiểm tra**, không phụ thuộc việc chạy JVM với cờ `-ea`.
- Trong `expectIllegalArgument`, nếu phương thức không ném, chương trình ném `AssertionError`; nó **không bị bắt nhầm** bởi `catch (IllegalArgumentException)`.

Lưu ý: `assert` của ngôn ngữ Java có thể bị tắt mặc định nếu không dùng `-ea`. Với một bộ test thuần `main` như trên, `if (!condition) throw new AssertionError(...)` đảm bảo test vẫn thực hiện assertion. Khi dùng JUnit, assertions của JUnit không phụ thuộc cờ `-ea`.

## 5. Chọn bộ giá trị đại diện: bình thường, biên và không hợp lệ

Test thành công/thất bại nên thiết kế theo **phân vùng tương đương** (*equivalence partitioning*) và **giá trị biên** (*boundary value analysis*).

Với quy tắc `quantity > 0`:

| Nhóm | Input ví dụ | Kỳ vọng |
|---|---:|---|
| Giá trị hợp lệ nhỏ nhất | `1` | Thành công |
| Giá trị hợp lệ phổ biến | `5` | Thành công |
| Biên ngay bên ngoài hợp lệ | `0` | `IllegalArgumentException` |
| Giá trị âm | `-1` | `IllegalArgumentException` |
| Giá trị dương rất lớn | `Integer.MAX_VALUE` | Theo giới hạn và khả năng overflow của phép tính |

Với `String` không được `null` và không được blank, nên phân biệt:

- `null`: lỗi null theo hợp đồng.
- `""`: chuỗi rỗng.
- `"   "`: chỉ chứa khoảng trắng.
- `"A"`: hợp lệ tối thiểu.
- `" A "`: có trim/normalize hay không tùy hợp đồng.
- Ký tự Unicode: xử lý theo yêu cầu thực tế, không giả định chỉ có ASCII.

Đừng tự đặt kỳ vọng mà chưa xác định policy. Một số API cho phép chuỗi rỗng nhưng cấm `null`, một số cho phép số `0`, một số xem “không tìm thấy” là `Optional.empty()` thay vì exception. Test phải **phản ánh cam kết được công bố**, không áp một loại lỗi chung cho mọi API.

## 6. Với JUnit 5: viết test success và failure rõ ràng

JUnit Jupiter là công cụ phổ biến để tổ chức unit test Java. Các ví dụ trong mục này **cần dependency JUnit Jupiter phù hợp và test runner của Maven/Gradle/IDE**; không phải các tệp có thể chạy chỉ với `javac` thuần.

Giả sử tệp production `PricePolicy.java`:

```java
public final class PricePolicy {
    public int total(int price, int quantity) {
        if (price < 0) {
            throw new IllegalArgumentException("price must be >= 0");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be > 0");
        }
        return Math.multiplyExact(price, quantity);
    }
}
```

Tệp kiểm thử `PricePolicyTest.java`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class PricePolicyTest {
    private final PricePolicy policy = new PricePolicy();

    @Test
    void returnsTotalForValidInput() {
        int result = assertDoesNotThrow(() -> policy.total(100, 2));
        assertEquals(200, result);
    }

    @Test
    void acceptsMinimumValidQuantity() {
        assertEquals(0, policy.total(0, 1));
    }

    @Test
    void rejectsNegativePrice() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> policy.total(-1, 2));

        assertEquals("price must be >= 0", error.getMessage());
    }

    @Test
    void rejectsZeroQuantity() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> policy.total(10, 0));

        assertEquals("quantity must be > 0", error.getMessage());
    }

    @Test
    void detectsOverflow() {
        assertThrows(ArithmeticException.class,
                () -> policy.total(Integer.MAX_VALUE, 2));
    }
}
```

Phân tích:

- `assertDoesNotThrow(...)` làm rõ mong muốn không có exception; **vẫn phải assert giá trị** trả về. Chỉ “không ném lỗi” chưa đủ để chứng minh hợp đồng tính toán.
- `assertThrows` chỉ đạt nếu executable **thực sự ném exception phù hợp**.
- Test nhận chính đối tượng `error`, nhờ đó có thể kiểm tra message/cause/suppressed hoặc error code.
- Mỗi test có tên thể hiện tình huống và kỳ vọng. Nếu một test thất bại, tên phương thức giúp tìm nhanh cam kết bị vi phạm.

Thực thi trong dự án Maven thường dùng `mvn test`; trong dự án Gradle được cấu hình JUnit Platform là `gradle test` hoặc `./gradlew test`. Những lệnh này yêu cầu dự án có build file, dependency JUnit và cấu hình test thích hợp. Không nên chạy tệp JUnit bằng `java PricePolicyTest` như ví dụ có `main`.

**Không cần thêm `assertDoesNotThrow` ở mọi test happy path**: một lời gọi ném ngoại lệ bất ngờ thường cũng khiến test JUnit thất bại. Hãy dùng khi nó làm hợp đồng rõ hơn hoặc cần lấy kết quả trong lambda.

## 7. Exception type: khi nào kiểm tra subtype, khi nào kiểm tra chính xác?

Giả sử hợp đồng ghi “ném `IllegalArgumentException` nếu input không hợp lệ”. `assertThrows(IllegalArgumentException.class, ...)` có thể chấp nhận subclass, phù hợp nếu hợp đồng cho phép phân lớp riêng.

Nếu contract ghi rõ **đúng một loại lỗi**, có thể dùng:

```java
IllegalArgumentException error = assertThrowsExactly(
        IllegalArgumentException.class,
        () -> policy.total(-1, 1));
```

Đây là **mảnh code JUnit**; cần import `assertThrowsExactly` và biến `policy` đã có. Có thể dùng `assertEquals(IllegalArgumentException.class, error.getClass())` nếu cần kiểm tra chính xác sau `assertThrows`.

Đừng test quá hẹp nếu thư viện công khai cho phép một họ exception. Ví dụ, hợp đồng JDBC hoặc HTTP client có thể hứa checked exception gốc hoặc subclass tùy driver; test ép đúng class implementation có thể hỏng khi nâng dependency mà hành vi công khai vẫn đúng.

Ngược lại, đừng test quá rộng:

```java
assertThrows(RuntimeException.class, () -> parse("not-a-number"));
```

Câu này có thể xanh vì một `NullPointerException` bất ngờ trong implementation. Nếu contract nêu `NumberFormatException` hoặc `IllegalArgumentException`, hãy test tương ứng. Khi đọc một exception lạ, xác định nó là **lỗi được mong đợi** hay bug bị test vô tình chấp nhận.

## 8. Message và error code: điều gì đáng khóa chặt trong test?

Thông điệp exception thường phục vụ con người chẩn đoán. Có những phần nên test:

- Mã lỗi ổn định, ví dụ `E_INVALID_QUANTITY`.
- Tên ràng buộc hoặc trường sai nếu hợp đồng công khai quy định.
- Giá trị an toàn quan trọng giúp caller hiểu lỗi.
- Thông điệp chính xác **nếu nó được công bố là một phần của API**.

Không nên mặc định kiểm tra **từng ký tự** của message do JDK, driver hoặc thư viện bên ngoài tạo. Message có thể đổi do JDK version, locale, driver, định dạng hoặc nâng dependency. Ví dụ test nguyên văn thông điệp `NumberFormatException` của JDK dễ gây brittle test khi API không hứa format đó.

Ví dụ JUnit minh họa:

```java
IllegalArgumentException error = assertThrows(
        IllegalArgumentException.class,
        () -> service.applyQuantity(-1));

assertTrue(error.getMessage().contains("quantity"));
```

Đây là mảnh tích hợp, cần `service` và import `assertTrue`, `assertThrows`. `contains("quantity")` chỉ phù hợp khi contract thực sự yêu cầu thông tin ấy; không phải phép kiểm tra tự động tốt hơn mọi trường hợp.

Nếu ứng dụng cần lỗi có thể xử lý bằng máy, ưu tiên **exception class, enum error code hoặc field riêng** thay vì bắt người gọi parse message. Test mã lỗi ổn định thường bền vững hơn test một câu chữ có thể được dịch.

## 9. Kiểm tra chuỗi nguyên nhân với `getCause()`

Một service có thể bọc lỗi tầng thấp thành exception có nghĩa ở tầng nghiệp vụ:

```java
try {
    return repository.load(id);
} catch (IOException e) {
    throw new IllegalStateException("Không tải được hồ sơ", e);
}
```

Đây là **mảnh mã minh họa** trong phương thức có các biến được định nghĩa. Hợp đồng thất bại có thể yêu cầu:

1. Caller nhận `IllegalStateException`.
2. Message của wrapper diễn đạt ngữ cảnh tải hồ sơ.
3. `getCause()` vẫn là `IOException`, giữ thông tin nguyên nhân.
4. Không trả kết quả thành công giả.
5. Không log lặp ở từng tầng; handler cuối xử lý tùy chính sách.

### Chương trình Java 17 độc lập: kiểm tra cause và trường hợp thành công

Tệp `CauseContractTest.java`:

```java
import java.io.IOException;

public class CauseContractTest {
    @FunctionalInterface
    interface Repository {
        String read() throws IOException;
    }

    static String load(Repository repository) {
        try {
            return repository.read();
        } catch (IOException e) {
            throw new IllegalStateException("load failed", e);
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        check("OK".equals(load(() -> "OK")), "Success path failed");
        System.out.println("success = OK");

        IOException root = new IOException("disk offline");
        try {
            load(() -> {
                throw root;
            });
            throw new AssertionError("Expected IllegalStateException");
        } catch (IllegalStateException e) {
            check("load failed".equals(e.getMessage()),
                    "Wrong wrapper message");
            check(e.getCause() == root, "Original cause lost");
            System.out.println("outer = "
                    + e.getClass().getSimpleName());
            System.out.println("cause = "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac CauseContractTest.java
java CauseContractTest
```

Đầu ra:

```text
success = OK
outer = IllegalStateException
cause = IOException
```

Dependency được thay bằng một **fake** theo interface `Repository` đơn giản, không cần database thật. Đường thành công trả `"OK"`; đường thất bại ném **chính đối tượng `root`** để kiểm tra wrapper giữ đúng identity trong `getCause()`.

Nếu không kiểm tra cause, một refactor sai kiểu:

```java
throw new IllegalStateException("load failed");
```

có thể vẫn qua test loại lỗi và message nhưng **mất nguyên nhân gốc**. Đây là lý do test hợp đồng exception cần có chiều sâu hơn `assertThrows`.

## 10. Kiểm tra trạng thái và side effect sau thất bại

Một API có side effect không chỉ cam kết “ném đúng exception”. Nó còn có thể cam kết:

- Validation chạy **trước** khi ghi dữ liệu.
- Khi dependency thất bại, bộ đếm thành công không tăng.
- Một transaction thất bại phải rollback theo quy tắc.
- Resource được đóng dù thân xử lý có exception.
- Một lần retry không nhân đôi giao dịch đã thành công trước đó.

Ví dụ Java thuần `MutationContractTest.java`:

```java
public class MutationContractTest {
    static final class Wallet {
        private int balance;

        Wallet(int initialBalance) {
            balance = initialBalance;
        }

        int balance() {
            return balance;
        }

        void debit(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("invalid amount");
            }
            if (amount > balance) {
                throw new IllegalStateException("insufficient funds");
            }
            balance -= amount;
        }
    }

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Wallet wallet = new Wallet(100);
        wallet.debit(40);
        check(wallet.balance() == 60, "Successful debit is wrong");
        System.out.println("success balance = " + wallet.balance());

        try {
            wallet.debit(-1);
            throw new AssertionError("Expected invalid amount");
        } catch (IllegalArgumentException expected) {
            check(wallet.balance() == 60,
                    "Balance changed after validation error");
            System.out.println("invalid balance = " + wallet.balance());
        }

        try {
            wallet.debit(70);
            throw new AssertionError("Expected insufficient funds");
        } catch (IllegalStateException expected) {
            check(wallet.balance() == 60,
                    "Balance changed after insufficient funds");
            System.out.println("insufficient balance = " + wallet.balance());
        }
    }
}
```

Chạy:

```bash
javac MutationContractTest.java
java MutationContractTest
```

Kết quả:

```text
success balance = 60
invalid balance = 60
insufficient balance = 60
```

Sau lần debit thành công, số dư còn 60. Hai lần debit thất bại phải **giữ nguyên số dư**. Nếu implementation cập nhật số dư rồi mới ném, test sẽ thất bại ngay cả khi loại exception vẫn đúng.

Đây là ví dụ đồng bộ thuần bộ nhớ; **không** chứng minh cách triển khai ví điện tử thực tế an toàn nhiều luồng hoặc bảo đảm transaction giữa nhiều hệ thống. Với database, cần dùng ranh giới transaction và fixture phù hợp, test cả rollback và commit theo hợp đồng.

## 11. Resource cleanup: kiểm tra cả primary và `Suppressed`

Một trường hợp dễ bị bỏ sót là `try-with-resources`: thân `try` ném lỗi A, còn `close()` ném lỗi B. Theo Java, **A là primary**, B được gắn vào A qua `getSuppressed()`. Nếu code đổi sang `finally` thủ công sai cách, B có thể **che A**.

Tệp Java 17 độc lập `ResourceExceptionContractTest.java`:

```java
import java.io.IOException;

public class ResourceExceptionContractTest {
    static final class Resource implements AutoCloseable {
        private final boolean failOnClose;

        Resource(boolean failOnClose) {
            this.failOnClose = failOnClose;
        }

        @Override
        public void close() throws IOException {
            if (failOnClose) {
                throw new IOException("close failed");
            }
        }
    }

    static String execute(boolean fail) throws Exception {
        try (Resource resource = new Resource(fail)) {
            if (fail) {
                throw new IllegalStateException("body failed");
            }
            return "completed";
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        check("completed".equals(execute(false)),
                "Expected successful result");
        System.out.println("success = completed");

        try {
            execute(true);
            throw new AssertionError("Expected primary exception");
        } catch (IllegalStateException e) {
            check("body failed".equals(e.getMessage()),
                    "Primary exception changed");

            Throwable[] suppressed = e.getSuppressed();
            check(suppressed.length == 1,
                    "Expected exactly one suppressed exception");
            check(suppressed[0] instanceof IOException,
                    "Expected IOException in suppressed");
            check("close failed".equals(suppressed[0].getMessage()),
                    "Wrong cleanup message");

            System.out.println("primary = " + e.getMessage());
            System.out.println("suppressed = "
                    + suppressed[0].getMessage());
        }
    }
}
```

Chạy:

```bash
javac ResourceExceptionContractTest.java
java ResourceExceptionContractTest
```

Output:

```text
success = completed
primary = body failed
suppressed = close failed
```

Khi `fail=false`, thân công việc thành công và `close()` không ném; kết quả là `"completed"`. Khi `fail=true`, cả thân xử lý và close đều thất bại. Test xác minh **exception chính không bị ghi đè**, đồng thời lỗi cleanup không bị mất.

Các trường hợp khác đáng kiểm thử nếu API hứa quản lý nhiều tài nguyên:

1. Thân thành công, `close()` thất bại: exception cleanup trở thành primary.
2. Thân lỗi, nhiều `close()` lỗi: có nhiều suppressed theo thứ tự đóng ngược.
3. Constructor tài nguyên thứ hai lỗi: tài nguyên thứ nhất vẫn phải được đóng.
4. Thân `try` return giá trị nhưng close lỗi: caller nhìn thấy lỗi đóng thay vì kết quả thành công.
5. Hàm cleanup thủ công ném unchecked exception: phải xác định precedence theo hợp đồng.

Test đừng chỉ xác minh `close()` được gọi bằng mock; **nếu hợp đồng cần giữ primary**, kiểm tra cả cause/suppressed mới phát hiện mất dữ liệu chẩn đoán.

## 12. Checked exception, unchecked exception và việc chọn ranh giới test

Hai đường lỗi hay bị trộn lẫn:

- **Checked exception**, ví dụ `IOException`: phương thức phải khai báo `throws` hoặc bắt. Test nên xác nhận `IOException` được propagate/bọc đúng hợp đồng.
- **Unchecked exception**, ví dụ `IllegalArgumentException`, `IllegalStateException`: vẫn cần test khi loại lỗi là một phần của contract, dù compiler không bắt buộc khai báo.

Không nên coi checked exception là “lỗi quan trọng” còn unchecked exception chỉ là bug. Một `IllegalArgumentException` có thể là phản hồi dự kiến của validation; một `IOException` có thể do dependency tạm thời; phân loại dựa theo **ý nghĩa nghiệp vụ**.

Nếu API quy định `IOException` từ repository phải đi xuyên qua service, test kỳ vọng checked exception. Nếu service cố ý chuyển sang exception nghiệp vụ có cause, test cả wrapper và cause. Nhưng test **không nên tự đặt quy tắc bọc lỗi** chỉ vì muốn code nhất quán: nó phải dựa trên contract mà caller thực sự sử dụng.

Với một API `Optional<T>` hoặc kết quả `Result<T>`, trường hợp “không tìm thấy” có thể là **đường bình thường** không ném exception. Khi đó failure test của hệ thống có thể kiểm tra `Optional.empty()` chứ không phải `assertThrows`. Dùng exception cho điều kiện nào phải được quyết định ở API, rồi mới viết test.

## 13. Exception từ `Future` và `CompletableFuture`

Khi một tác vụ bất đồng bộ lỗi, loại exception quan sát ở **caller** có thể khác lỗi ném từ **worker**:

- `Future.get()` thường ném `ExecutionException` nếu task thất bại; lỗi gốc ở `getCause()`.
- `CompletableFuture.join()` thường ném `CompletionException` khi stage hoàn thành ngoại lệ; nguyên nhân ở `getCause()`.
- `CompletableFuture.get()` dùng `ExecutionException` cho exceptional completion thông thường.
- Khi caller đang chờ `get()` và **chính caller bị interrupt**, có thể nhận `InterruptedException`; điều này không tự nói rằng worker đã lỗi/hủy.
- Một Future đã hủy có thể khiến `get()` ném `CancellationException`; trạng thái canceled không bảo đảm worker đã dọn dẹp xong.
- Timeout của `get(timeout, unit)` có thể ném `TimeoutException` nhưng không tự hủy task.

Do đó test cần **nhắm đúng hợp đồng mà caller quan sát**, không nhầm `IOException` bên trong `Callable` với `IOException` được ném trực tiếp từ `get()`.

### Ví dụ Java 17 độc lập: hai đường hoàn thành của `CompletableFuture`

Tệp `AsyncExceptionContractTest.java`:

```java
import java.io.IOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CancellationException;

public class AsyncExceptionContractTest {
    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        CompletableFuture<String> success =
                CompletableFuture.completedFuture("ok")
                        .thenApply(String::toUpperCase);

        check("OK".equals(success.join()),
                "Wrong successful result");
        System.out.println("success = " + success.join());

        IOException root = new IOException("offline");
        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(root);

        try {
            failed.join();
            throw new AssertionError("Expected CompletionException");
        } catch (CompletionException e) {
            check(e.getCause() == root, "Cause was lost");
            System.out.println("cause = "
                    + e.getCause().getClass().getSimpleName());
        }

        CompletableFuture<String> canceled = new CompletableFuture<>();
        check(canceled.cancel(false), "Cancel should succeed");

        try {
            canceled.join();
            throw new AssertionError("Expected CancellationException");
        } catch (CancellationException expected) {
            check(canceled.isCancelled(), "Future must be canceled");
            System.out.println("canceled = true");
        }
    }
}
```

Chạy:

```bash
javac AsyncExceptionContractTest.java
java AsyncExceptionContractTest
```

Kết quả:

```text
success = OK
cause = IOException
canceled = true
```

Test dùng các Future đã hoàn thành hoặc được hủy trực tiếp, nên output ổn định và **không phụ thuộc lịch thực thi các thread**. Nó kiểm tra hợp đồng **quan sát kết quả** của `CompletableFuture`, không thử chứng minh hiệu quả hủy một worker đang chạy.

Nếu cần test worker thật sự nhận interrupt, hãy dùng `CountDownLatch`, `Future` hoặc cơ chế đồng bộ thích hợp; tránh ngủ một thời lượng ngẫu nhiên rồi hi vọng worker đã chạy đến đúng chỗ.

## 14. Test bất đồng bộ mà không tạo race/flaky test

Anti-pattern thường gặp:

```java
executor.submit(() -> updateState());
Thread.sleep(100);
assertEquals("DONE", state.get());
```

Đây là **mảnh mã minh họa JUnit** (chưa độc lập), với `executor`, `updateState`, `state` đã có. `sleep(100)` không bảo đảm task sẽ hoàn thành trong 100 ms trên CI. Test có thể qua trên máy cá nhân nhưng thất bại dưới tải.

Nếu cần đợi kết quả, dùng đồng bộ có deadline:

```java
Future<String> future = executor.submit(() -> "DONE");
String result = future.get(2, TimeUnit.SECONDS);
assertEquals("DONE", result);
```

Đây là **mảnh mã tích hợp**, cần `ExecutorService`, `Future`, `TimeUnit`, JUnit imports và quy tắc shutdown. Deadline giúp test tránh treo vô hạn, nhưng không biến mã bất đồng bộ sai thành đúng.

Đối với scenario phức tạp, dùng `CountDownLatch` để ép thứ tự cần thiết; khi test xong hãy giải phóng latch trong `finally`, đóng executor và xử lý interrupt phù hợp. Không gọi `Thread.stop()` để “dọn” một test bị treo.

**Timeout chỉ là hàng rào chống treo**, không phải bằng chứng correctness. Test vẫn phải assert trạng thái kết quả, exception type và các side effect đã cam kết.

## 15. Không test failure bằng cách tạo lỗi không liên quan

Một test như sau có thể *giả xanh*:

```java
assertThrows(NullPointerException.class,
        () -> service.process(null));
```

Nếu hợp đồng thực tế yêu cầu `IllegalArgumentException`, test trên không đúng kỳ vọng. Hoặc test có thể vô tình ném `NullPointerException` ngay ở bước dựng fixture, không phải trong `service.process(...)`.

Biện pháp:

1. Chuẩn bị fixture **trước** lambda kiểm tra lỗi.
2. Trong lambda, chỉ đặt **hành động mà hợp đồng yêu cầu sẽ thất bại**.
3. Kiểm tra đúng exception type, mã lỗi/cause quan trọng.
4. Xác minh side effect và state sau thất bại.
5. Nếu có nhiều lỗi có thể xảy ra, cô lập precondition để chỉ một điều kiện sai.

Ví dụ JUnit phù hợp hơn:

```java
OrderRequest request = new OrderRequest("A-1", -1);
IllegalArgumentException error = assertThrows(
        IllegalArgumentException.class,
        () -> service.createOrder(request));

assertEquals("INVALID_QUANTITY", error.getMessage());
```

Đây là **mảnh minh họa** với `OrderRequest`/`service` do hệ thống định nghĩa. Hãy đặt `request` trước `assertThrows`, tránh việc khởi tạo fixture bên trong lambda cũng có thể là nơi gây exception. Message chính xác chỉ nên test nếu `INVALID_QUANTITY` là cam kết ổn định.

## 16. Failure path không được tạo thành công giả

Một lỗi nghiêm trọng là code bắt exception rồi trả mặc định:

```java
try {
    return repository.read();
} catch (IOException e) {
    return "";
}
```

Đây là mảnh mã minh họa. Nó chỉ đúng nếu hợp đồng thật sự quy định `""` là kết quả fallback hợp lệ và caller phân biệt được nó với dữ liệu bình thường. Nếu hợp đồng yêu cầu báo lỗi, đây là bug: exception đã bị **nuốt**.

Test phải tìm ra hành vi sai bằng cách:

- Cho fake repository ném `IOException`.
- Xác minh service propagate `IOException` hoặc bọc đúng loại exception.
- Khẳng định **không** có kết quả thành công.
- Kiểm tra cause còn nguyên nếu có chuyển loại lỗi.

Tương tự, `return` trong `finally` có thể che exception đang ném. Một test failure path có kiểm tra chính xác loại lỗi sẽ phát hiện tình huống chương trình trả kết quả bình thường khi lẽ ra phải ném.

## 17. Test exception message/cause sau refactor

Refactor có thể giữ happy path nhưng làm hỏng failure path theo nhiều cách:

- Bỏ `throw`/chuyển sang trả `null`.
- Thay `IOException` bằng `IllegalStateException` mà quên cause.
- Tạo exception mới với message chung chung `"failed"` thay vì mã lỗi ổn định.
- Đổi `try-with-resources` sang `try-finally` khiến close exception che primary.
- Thay `throw e` bằng `throw new RuntimeException(e.getMessage())`, làm mất stack cause.
- Bắt `InterruptedException` rồi bỏ qua, khiến tác vụ vẫn tiếp tục.
- Catch `Exception` quá rộng, chuyển các lỗi lập trình thành fallback thành công.

Vì vậy, khi thay đổi code liên quan exception, hãy chạy lại **ít nhất một test success và các test failure tương ứng từng hợp đồng bị ảnh hưởng**. Phần regression suite nên tập trung vào hành vi có thể quan sát từ caller, không phụ thuộc quá sâu vào vị trí `catch` trong implementation.

## 18. Unit test, integration test và nơi chịu trách nhiệm

Không phải mọi hợp đồng có thể được chứng minh bằng unit test giả lập.

| Loại test | Kiểm tra tốt nhất |
|---|---|
| Unit test | Validation, exception type, message/code ổn định, cause wrapping, lựa chọn fallback, thay đổi state cục bộ |
| Integration test | Transaction rollback thật, tài nguyên được đóng, SQL/HTTP error mapping, adapter giữ cause |
| Contract test giữa service | HTTP status/body ổn định, mã lỗi công khai, retry semantics ở ranh giới |
| End-to-end test | Hành vi từ góc nhìn người dùng; operation thành công/thất bại qua nhiều thành phần |

Ví dụ, mock một `Connection.rollback()` chỉ chứng minh code **đã gọi** rollback trong test cụ thể; chưa chứng minh database thực sự rollback. Ngược lại, integration test với database thật đắt hơn nhưng xác nhận semantics end-to-end của resource/transaction.

Khi cần test exception từ một dependency, fake/stub có thể chủ động ném lỗi xác định để tái lập dễ dàng. Đừng dùng network thật để tạo timeout trong một unit test nếu không bắt buộc; nó khiến test chậm và flaky.

## 19. Phân biệt exception dự kiến với lỗi test hạ tầng

Khi test thất bại, đọc tín hiệu:

- **Assertion failure:** hành vi quan sát khác hợp đồng; xem message của assertion và input.
- **Exception chưa dự kiến:** test/setup hoặc code production ném lỗi khác; đọc stack và cause.
- **Test timeout:** có thể deadlock, chờ quá lâu, môi trường quá tải hoặc fixture không giải phóng latch. Không vội tăng timeout nếu có logic sai.
- **Failure do môi trường:** thiếu file, DB chưa chạy, timezone/locale khác, permission hoặc dependency chưa cấu hình.
- **Flaky test:** kết quả phụ thuộc thread scheduling, thời gian thật, random hoặc shared state.

Một test tốt phải **thất bại khi contract bị vi phạm** và **ổn định khi contract được đáp ứng**. Không nên biến test đỏ thành xanh bằng cách catch quá rộng hoặc bỏ assertion quan trọng.

### Message của JDK/stack trace không nên là oracle cứng

Nếu test in toàn bộ `printStackTrace()` rồi đối chiếu 100% text, nó dễ khác do số dòng, tên file, wrapper hoặc bản JDK. Hãy dùng API như `getCause()`, `getSuppressed()` và kiểm tra loại lỗi. Chỉ lock exact message của code bạn kiểm soát nếu có lý do hợp đồng rõ ràng.

## 20. Checklist trước khi kết luận một exception contract đã được kiểm thử đủ

- **Success:** có input điển hình, biên hợp lệ và assert kết quả/side effect đúng không?
- **Invalid input:** mỗi nhóm điều kiện sai có test exception type phù hợp không?
- **No exception:** test success có vô tình chỉ gọi hàm mà không kiểm tra kết quả không?
- **Exception type:** có bắt quá rộng (`Exception`/`RuntimeException`) khiến bug được chấp nhận không?
- **Message/code:** đang test thông tin hợp đồng ổn định hay chi tiết do JDK/driver tự sinh?
- **Cause:** exception được bọc có giữ đúng nguyên nhân gốc không?
- **Suppressed:** lỗi cleanup có được giữ đúng và không che primary không?
- **State:** sau failure có tránh cập nhật dở hoặc side effect cấm không?
- **Async:** caller thấy `CompletionException`, `ExecutionException`, `CancellationException` hoặc `InterruptedException` đúng bối cảnh không?
- **Determinism:** test dùng fake/latch/deadline thay vì sleep tùy tiện không?
- **Isolation:** mỗi test có fixture sạch, không phụ thuộc thứ tự chạy test khác không?
- **Observability:** test assertion, tên test và failure message có giúp tìm cam kết bị vi phạm không?

**Ghi nhớ:** test exception theo hợp đồng nghĩa là **xác minh cả cách API thành công lẫn cách nó từ chối/thất bại**, kể cả kết quả, loại ngoại lệ, cause, suppressed và trạng thái hệ thống sau lỗi. Một bộ test đủ mạnh không chỉ chứng minh “có exception”, mà chứng minh **đúng exception ở đúng tình huống và không có tác dụng phụ sai**.
