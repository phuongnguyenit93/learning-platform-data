# Ngoại lệ, trạng thái lỗi và hợp đồng phương thức trong Java

**Chủ đề:** OOP → Cơ chế ngôn ngữ

Một phương thức Java có thể **hoàn thành và trả kết quả**, **từ chối một yêu cầu nghiệp vụ**, hoặc **không thể hoàn thành do lỗi**. Việc chọn trả về `boolean`, `Optional`, một kiểu kết quả có cấu trúc hay ném exception sẽ quyết định cách những người gọi API phải xử lý tình huống đó.

Bài này giúp bạn hiểu cơ chế exception trong Java, cách biểu diễn trạng thái lỗi và cách thiết kế **method contract**: ai được phép gọi phương thức với đầu vào nào, kết quả thành công được bảo đảm ra sao, điều gì xảy ra khi thất bại, và trạng thái đối tượng còn hợp lệ hay không.

## 1. Bắt đầu bằng tình huống thực tế

Một cửa hàng cho khách đặt giữ sách. Hiện kho còn 2 cuốn, khách yêu cầu giữ 3 cuốn.

- **Hết hàng** là tình huống dự kiến trong kinh doanh. Giao diện cần biết lý do để hiển thị “Chỉ còn 2 cuốn”.
- **Số lượng yêu cầu bằng -3** là đầu vào vi phạm quy tắc phương thức. Client không nên dùng API như vậy.
- **Không truy cập được database** là sự cố kỹ thuật. Nếu chuyển thành “hết hàng”, hệ thống đang nói dối về tồn kho.
- **Giữ hàng thành công** phải làm giảm tồn kho chính xác; giữ không thành công không được trừ hàng.

Bốn trường hợp có ý nghĩa khác nhau:

| Tình huống | Điều caller cần biết | Một cách biểu diễn hợp lý |
| --- | --- | --- |
| Đã giữ được sách | Số lượng giữ và tồn còn lại | `Reserved` |
| Không đủ hàng | Lý do từ chối và số lượng hiện có | `Rejected(OUT_OF_STOCK)` |
| Tham số vi phạm hợp đồng | Vị trí sử dụng sai API | `IllegalArgumentException` |
| Cơ sở dữ liệu mất kết nối | Có sự cố để phục hồi, thử lại có điều kiện hoặc báo lỗi | Exception hạ tầng có nguyên nhân rõ ràng |

Nguyên tắc thực dụng: **đừng dùng một tín hiệu duy nhất để mô tả mọi loại thất bại**. Đặc biệt, `null` hoặc `false` có thể quá mơ hồ khi caller phải quyết định hành động khác nhau.

## 2. Hợp đồng phương thức gồm những gì?

Một method contract mô tả những điều mà **bên gọi** và **bên cài đặt** thống nhất:

| Thành phần | Câu hỏi | Ví dụ của `reserve` |
| --- | --- | --- |
| **Precondition** — tiền điều kiện | Trước khi gọi phải đúng điều gì? | SKU không rỗng, số lượng là số nguyên dương |
| **Postcondition** — hậu điều kiện | Khi thành công bảo đảm điều gì? | Số lượng trong kho giảm đúng số đã giữ |
| **Invariant** — bất biến | Điều gì luôn phải đúng với đối tượng? | Tồn kho không âm |
| **Failure contract** | Nếu không thành công, điều gì được trả/ném? | `Rejected` nếu thiếu hàng, exception nếu tham số sai |
| **Side effect** | Phương thức thay đổi gì bên ngoài? | Thay đổi tồn kho; chưa gửi email/thu tiền |
| **Atomicity** | Khi thất bại, có thể bị cập nhật dở không? | Việc từ chối phải giữ nguyên tồn kho |
| **Concurrency** | Hai yêu cầu đồng thời có thể làm sai state không? | Kiểm tra và giảm hàng phải cùng một thao tác được bảo vệ |

Chữ ký `int reserve(String sku, int amount)` chỉ mô tả kiểu dữ liệu, chưa nói được kết quả `-1` nghĩa là không tìm thấy, hết hàng hay lỗi hệ thống.

Có thể làm hợp đồng rõ hơn bằng **kiểu trả về đặt tên tốt**, Javadoc và test:

~~~java
/**
 * Giữ một số lượng sản phẩm trong kho.
 *
 * @param sku mã sản phẩm khác null và không rỗng
 * @param quantity số lượng cần giữ, phải > 0
 * @return Reserved nếu giữ thành công;
 *         Rejected nếu sản phẩm không có hoặc không đủ hàng
 * @throws IllegalArgumentException nếu đầu vào sai hợp đồng
 *
 * Khi trả Rejected, tồn kho không thay đổi.
 * Khi trả Reserved, tồn kho còn lại không âm.
 */
ReserveResult reserve(String sku, int quantity);
~~~

Javadoc là **lời cam kết**, nhưng chỉ code, các ràng buộc dữ liệu và kiểm thử phù hợp mới chứng minh lời cam kết được giữ.

## 3. Exception là gì? Checked và unchecked khác nhau thế nào?

Java dùng `Throwable` làm gốc của hệ thống ngoại lệ. Hai nhánh chính là `Exception` và `Error`; `RuntimeException` kế thừa `Exception`.

~~~mermaid
classDiagram
    Throwable <|-- Exception
    Throwable <|-- Error
    Exception <|-- IOException
    Exception <|-- RuntimeException
    RuntimeException <|-- IllegalArgumentException
    RuntimeException <|-- IllegalStateException
    RuntimeException <|-- NullPointerException
~~~

**Checked exception** là subclass của `Throwable` nhưng không nằm dưới `RuntimeException` hoặc `Error`. Khi một checked exception có thể thoát khỏi phương thức, Java buộc code gọi phải **bắt** hoặc **khai báo `throws`**. Ví dụ: `IOException`, `SQLException`.

**Unchecked exception** gồm `RuntimeException` và các subclass; compiler không buộc caller bắt hoặc khai báo. Thường dùng cho vi phạm hợp đồng, lỗi trạng thái hoặc những failure mà API lựa chọn cách báo này.

**`Error`** như `OutOfMemoryError`, `LinkageError` thường liên quan môi trường chạy nghiêm trọng. Phần lớn code nghiệp vụ không nên `catch (Throwable)` rồi tiếp tục như không có lỗi.

| Loại | Ví dụ | Compiler có bắt khai báo/xử lý không? | Ghi nhớ |
| --- | --- | --- | --- |
| Checked | `IOException` | Có | Có thể bắt hoặc truyền tiếp |
| Unchecked | `IllegalArgumentException` | Không | Vẫn cần ghi rõ điều kiện ném trong hợp đồng |
| Error | `OutOfMemoryError` | Không | Không biến thành lỗi nghiệp vụ thông thường |

**Không suy diễn** “checked = chắc chắn khôi phục được” hoặc “unchecked = chắc chắn bug”. Thư viện HTTP có thể báo lỗi mạng bằng unchecked exception; ngược lại một checked exception vẫn có thể không xử lý được ở tầng hiện tại.

## 4. `throw`, `throws`, `try` và `catch`

`throw` thực sự ném một exception object:

~~~java
static void requirePositive(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException(
                "quantity phải lớn hơn 0");
    }
}
~~~

`throws` **khai báo** ngoại lệ mà phương thức có thể để thoát ra ngoài:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static String readSettings(Path file) throws IOException {
    return Files.readString(file);
}
~~~

Nếu caller có cách xử lý hữu ích, nó bắt exception:

~~~java
try {
    String data = readSettings(Path.of("app.conf"));
    System.out.println(data);
} catch (IOException failure) {
    System.err.println("Không đọc được cấu hình: "
            + failure.getMessage());
}
~~~

Các đoạn trên là các **snippet phương thức/lời gọi** đặt trong class thích hợp. Một caller khác có thể khai báo `throws IOException` để tầng trên quyết định. Không cần bắt và log ở mọi tầng.

**Khi ném exception**, Java ngắt đường chạy bình thường và tìm `catch` phù hợp dọc call stack. Nếu không có handler, exception truyền tới ranh giới thread/framework quản lý. Phần code sau lệnh ném trong cùng đường chạy sẽ không được thực thi bình thường.

### Bắt lỗi cụ thể trước lỗi tổng quát

~~~java
try {
    // ... xử lý ...
} catch (IllegalArgumentException badInput) {
    // Xử lý đầu vào sai nếu tầng này có trách nhiệm.
} catch (RuntimeException unexpected) {
    // Chính sách riêng cho RuntimeException còn lại.
}
~~~

Đặt subclass ở nhánh `catch` trước class cha. Java từ chối các `catch` không thể tới được; không thể bắt `RuntimeException` rồi sau đó mới bắt `IllegalArgumentException` riêng.

Có thể dùng **multi-catch** nếu các loại lỗi có cùng chính sách:

~~~java
catch (IllegalArgumentException | IllegalStateException failure) {
    // Quy tắc xử lý chung.
}
~~~

Các lựa chọn trong một multi-catch không được có quan hệ subclass/superclass với nhau. Trong code thật, không tự động gom mọi exception chỉ để tránh viết thêm dòng.

## 5. Chọn kết quả nghiệp vụ hay exception?

Ba API giả định đều có thể hợp lệ nhưng phục vụ hợp đồng khác nhau:

~~~java
// Không cần phân biệt nguyên nhân, ví dụ một thao tác thử đơn giản.
boolean tryReserve(String sku, int quantity);

// Không có giá trị trả về là tình huống bình thường.
java.util.Optional<Book> findByIsbn(String isbn);

// Cần phân biệt thành công với các lý do từ chối.
ReserveResult reserve(String sku, int quantity);
~~~

Với `Optional.empty()`, caller hiểu “không có sách” nếu hợp đồng `findByIsbn` nói vậy. Khi DB mất kết nối, **không nên** bí mật trả empty: caller sẽ tưởng sản phẩm không tồn tại.

Một số hệ thống chọn ném **domain exception** cho yêu cầu hết hàng; cách đó cũng có thể đúng nếu API/UX/handler thống nhất theo quy ước ấy. Nhưng khi từ chối là một nhánh được dự kiến và caller thường xuyên phải phân biệt, **kiểu Result có cấu trúc** thường khiến luồng xử lý rõ ràng.

## 6. Ví dụ Java 17 hoàn chỉnh: kết quả thành công/từ chối và lỗi hợp đồng

Tạo file **ErrorContractDemo.java**. Ví dụ dùng `sealed interface` để giới hạn các nhánh kết quả, `record` để biểu diễn dữ liệu kết quả bất biến, và `synchronized` cho thao tác kiểm tra–cập nhật tồn kho trong **một instance**.

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class ErrorContractDemo {
    enum RejectionReason {
        UNKNOWN_SKU, OUT_OF_STOCK
    }

    sealed interface ReserveResult permits Reserved, Rejected {}

    record Reserved(String sku, int quantity, int remaining)
            implements ReserveResult {
        Reserved {
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank() || quantity <= 0 || remaining < 0) {
                throw new IllegalArgumentException(
                        "Kết quả giữ hàng không hợp lệ");
            }
        }
    }

    record Rejected(RejectionReason reason, String message)
            implements ReserveResult {
        Rejected {
            Objects.requireNonNull(reason, "reason");
            Objects.requireNonNull(message, "message");
        }
    }

    static final class StockService {
        private final Map<String, Integer> stock = new HashMap<>();

        StockService(Map<String, Integer> initialStock) {
            Objects.requireNonNull(initialStock, "initialStock");

            for (var entry : initialStock.entrySet()) {
                String sku = entry.getKey();
                Integer quantity = entry.getValue();

                if (sku == null || sku.isBlank()
                        || quantity == null || quantity < 0) {
                    throw new IllegalArgumentException(
                            "Tồn kho khởi tạo không hợp lệ");
                }
                stock.put(sku, quantity);
            }
        }

        /**
         * Preconditions: sku không rỗng, quantity > 0.
         * Rejected không làm thay đổi tồn kho.
         * Reserved giảm tồn đúng quantity, remaining >= 0.
         */
        synchronized ReserveResult reserve(
                String sku, int quantity) {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException(
                        "SKU không được rỗng");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "Số lượng phải dương");
            }

            Integer available = stock.get(sku);
            if (available == null) {
                return new Rejected(
                        RejectionReason.UNKNOWN_SKU,
                        "Sản phẩm không tồn tại");
            }

            if (available < quantity) {
                return new Rejected(
                        RejectionReason.OUT_OF_STOCK,
                        "Chỉ còn " + available + " sản phẩm");
            }

            int remaining = available - quantity;
            stock.put(sku, remaining);
            return new Reserved(sku, quantity, remaining);
        }

        synchronized int remaining(String sku) {
            Integer quantity = stock.get(sku);
            if (quantity == null) {
                throw new IllegalArgumentException(
                        "Không có SKU: " + sku);
            }
            return quantity;
        }
    }

    public static void main(String[] args) {
        StockService service =
                new StockService(Map.of("JAVA", 3));

        ReserveResult first = service.reserve("JAVA", 2);
        ReserveResult second = service.reserve("JAVA", 2);

        System.out.println(first);
        System.out.println(second);
        System.out.println("Remaining: "
                + service.remaining("JAVA"));

        try {
            service.reserve("JAVA", 0);
        } catch (IllegalArgumentException failure) {
            System.out.println("INPUT_ERROR: "
                    + failure.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ErrorContractDemo.java
java ErrorContractDemo
~~~

Kết quả:

~~~text
Reserved[sku=JAVA, quantity=2, remaining=1]
Rejected[reason=OUT_OF_STOCK, message=Chỉ còn 1 sản phẩm]
Remaining: 1
INPUT_ERROR: Số lượng phải dương
~~~

**Phân tích theo hợp đồng:**

1. Lần giữ đầu tiên trả `Reserved`; tồn kho từ 3 còn 1.
2. Lần giữ thứ hai vượt số lượng hiện có nên trả `Rejected`. Không có dữ liệu nào bị trừ thêm.
3. Yêu cầu với số lượng 0 vi phạm precondition, nên bị từ chối bằng `IllegalArgumentException`.
4. `stock` thuộc quyền sở hữu của `StockService`: dữ liệu từ map đầu vào đã được sao chép, không giữ reference mutable từ bên ngoài.
5. `synchronized` khiến kiểm tra và giảm số lượng cùng được bảo vệ bởi monitor của service instance. Điều này **không thay transaction database** và không bảo vệ khi có nhiều JVM/instance cùng ghi dữ liệu dùng chung.

Nếu muốn client ở package khác dùng các kiểu kết quả, hãy tổ chức chúng thành public API với visibility thích hợp. Các kiểu được để package-private trong ví dụ nhằm cung cấp một file Java chạy độc lập.

## 7. Test cả giá trị trả về và trạng thái sau thất bại

Đặt đoạn sau vào **ErrorContractDemoTest.java**, trong cùng package, và cấu hình **JUnit Jupiter 5**:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Map;
import org.junit.jupiter.api.Test;

class ErrorContractDemoTest {

    @Test
    void reserveThanhCongGiamDungSoLuong() {
        var stock = new ErrorContractDemo.StockService(
                Map.of("JAVA", 3));

        assertEquals(
                new ErrorContractDemo.Reserved("JAVA", 2, 1),
                stock.reserve("JAVA", 2));
        assertEquals(1, stock.remaining("JAVA"));
    }

    @Test
    void reserveKhongDuHangKhongDoiState() {
        var stock = new ErrorContractDemo.StockService(
                Map.of("JAVA", 1));

        var result = stock.reserve("JAVA", 2);
        assertEquals(
                new ErrorContractDemo.Rejected(
                        ErrorContractDemo.RejectionReason.OUT_OF_STOCK,
                        "Chỉ còn 1 sản phẩm"),
                result);
        assertEquals(1, stock.remaining("JAVA"));
    }

    @Test
    void thamSoSaiNemExceptionTruocKhiThayDoi() {
        var stock = new ErrorContractDemo.StockService(
                Map.of("JAVA", 3));

        assertThrows(IllegalArgumentException.class,
                () -> stock.reserve("JAVA", 0));
        assertEquals(3, stock.remaining("JAVA"));
    }

    @Test
    void khongTimThaySkuLaTuChoiNghiepVu() {
        var stock = new ErrorContractDemo.StockService(
                Map.of("JAVA", 3));

        var result = stock.reserve("MISSING", 1);
        assertInstanceOf(ErrorContractDemo.Rejected.class, result);
        var rejected = (ErrorContractDemo.Rejected) result;
        assertEquals(
                ErrorContractDemo.RejectionReason.UNKNOWN_SKU,
                rejected.reason());
    }
}
~~~

Các test này xác minh **cả hậu điều kiện lẫn bất biến**. Không chỉ kiểm tra exception được ném, mà còn xác minh tồn kho không bị sửa trong trường hợp thất bại. Chúng chưa chứng minh khả năng chống race giữa các máy chủ hoặc xử lý transaction với DB thật; cần test tích hợp cho những điều đó.

## 8. Stack trace, propagation và giữ chuỗi nguyên nhân

Khi exception được ném, nó tìm handler trên call stack. Nếu repository đọc file gặp lỗi nhưng application service cần thêm bối cảnh nghiệp vụ, tầng service có thể chuyển đổi exception:

~~~java
final class InventoryUnavailableException
        extends RuntimeException {
    InventoryUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}

static String loadInventoryText(java.nio.file.Path file) {
    try {
        return java.nio.file.Files.readString(file);
    } catch (java.io.IOException cause) {
        throw new InventoryUnavailableException(
                "Không tải được tồn kho: " + file, cause);
    }
}
~~~

Đây là các snippet dùng trong một class hoặc file Java thích hợp. Lỗi mới vẫn giữ **cause** để người điều tra lần được xuống `IOException` gốc. Nếu mọi tầng đều bắt, in stack trace rồi ném exception mới, log sẽ bị nhân bản và rất khó tìm điểm xảy ra lỗi thực sự.

Một nguyên tắc hữu ích là **catch tại tầng có khả năng đưa ra quyết định**:

~~~mermaid
sequenceDiagram
    participant Caller
    participant Service
    participant Repository
    Caller->>Service: load inventory
    Service->>Repository: read file
    Repository--xService: IOException
    Note over Service: Translate + giữ cause nếu cần
    Service--xCaller: InventoryUnavailableException
    Note over Caller: Quyết định phản hồi, log, retry có điều kiện
~~~

Không dùng `new RuntimeException(e.getMessage())` nếu muốn giữ nguyên nhân; truyền `e` làm `cause`.

### `getMessage()` không nên là mã lỗi

Một lỗi có thể được hiển thị bằng tiếng Việt hôm nay, tiếng Anh ngày mai hoặc thêm ngữ cảnh sau khi refactor. Caller nên phân biệt bằng **kiểu exception** hoặc **error code cấu trúc**, thay vì parse nội dung chuỗi `getMessage()`.

## 9. Try-with-resources, `finally` và suppressed exceptions

Khi đọc tệp, ghi stream hoặc dùng connection, cần đóng tài nguyên. `try-with-resources` làm việc đó theo hợp đồng `AutoCloseable`:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static long countLines(Path file) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(file)) {
        long count = 0;
        while (reader.readLine() != null) {
            count++;
        }
        return count;
    }
}
~~~

Nếu cả thân `try` lẫn `close()` đều ném exception, exception ở thân thường là **primary exception**; lỗi từ close được lưu trong `getSuppressed()`. Điều này giúp không làm mất lỗi ban đầu.

`finally` thường dùng để dọn dẹp sau `try`/`catch`, nhưng không nên `return` trong finally: nó có thể che giá trị trả về hoặc exception đang chờ. `finally` cũng không được đảm bảo chạy nếu JVM bị chấm dứt đột ngột hoặc tiến trình bị hủy từ bên ngoài.

**Resource cleanup không phải database rollback.** Nếu code đã gửi email hoặc trừ tiền rồi ném lỗi, việc đóng resource không tự động hoàn tác tác dụng phụ.

## 10. Exception không bảo đảm thao tác nguyên tử

Xét đoạn:

~~~java
balance -= amount;
sendConfirmationEmail(); // Có thể ném exception.
~~~

Nếu gửi email thất bại, `balance` đã bị trừ. Việc bắt exception không tự khôi phục số dư.

Cần xác định tính **failure atomicity**: thao tác thất bại có để lại một phần thay đổi không? Với dữ liệu quan trọng, có thể cần:

- Validate điều kiện độc lập **trước** khi sửa state.
- Dùng transaction cho các thay đổi thuộc cùng một nguồn dữ liệu có khả năng giao dịch.
- Với database và message broker, cân nhắc **transactional outbox** để đồng bộ thay đổi state và việc ghi sự kiện.
- Với lệnh có thể bị lặp sau timeout, dùng **idempotency key** hoặc điều kiện chống thực hiện trùng.
- Dùng optimistic locking, conditional update hoặc locking phù hợp để tránh mất cập nhật khi nhiều yêu cầu cùng sửa tài nguyên.

Một `@Transactional` trong Spring không tự rollback email đã gửi, và kết quả rollback của transaction manager còn phụ thuộc loại exception, cấu hình, điểm đi qua proxy và tài nguyên được quản lý. Phải kiểm thử tình huống lỗi ở chính ranh giới đó.

## 11. Hợp đồng exception khi override và đa hình

Giả sử client sử dụng abstraction:

~~~java
interface AccountStore {
    /** Empty chỉ có nghĩa tài khoản không tồn tại. */
    java.util.Optional<String> findOwner(String accountId);
}
~~~

Một implementation không thể coi lỗi mạng là `Optional.empty()`, vì điều đó phá nghĩa “không tồn tại” mà client đang dựa vào. Chữ ký vẫn đúng nhưng **hợp đồng hành vi đã sai**.

Với **Liskov Substitution Principle (LSP)**, implementation thay thế nên giữ:

- **Precondition:** không buộc caller thỏa thêm yêu cầu bất ngờ so với hợp đồng.
- **Postcondition:** không giảm những bảo đảm khi kết thúc thành công.
- **Invariant:** giữ điều kiện trạng thái mà abstraction đã công bố.
- **Failure semantics:** giữ ý nghĩa của các trường hợp từ chối, lỗi và side effect.

Ở mức cú pháp Java, method override **không thể thêm checked exception mới rộng hơn** checked exception của phương thức được override. Nhưng Java không chặn một implementation tự ném unchecked exception ở runtime; vì vậy cần thiết kế và test hành vi, không chỉ dựa vào compiler.

Ví dụ một `ReadOnlyRepository` triển khai giao diện hứa có `save()` rồi luôn ném `UnsupportedOperationException`: đây là dấu hiệu hợp đồng có thể quá rộng hoặc subtype không phù hợp, nên xem lại phân tách interface.

## 12. Cách ánh xạ lỗi giữa domain và API

| Tầng | Ví dụ | Việc nên đảm nhiệm |
| --- | --- | --- |
| Controller/API | JSON thiếu field, số lượng âm | Xác thực đầu vào, phản hồi có cấu trúc, tránh lộ dữ liệu nội bộ |
| Application service | Yêu cầu giữ hàng hoặc hủy đơn | Phối hợp nghiệp vụ, quyền, transaction và side effect |
| Domain object | Vi phạm bất biến, trạng thái không cho thao tác | Bảo vệ precondition/postcondition, trả kết quả hoặc ném lỗi domain phù hợp |
| Repository/adapter | Database unavailable, timeout | Giữ nguyên nhân và truyền hoặc chuyển lỗi đúng ranh giới |
| Job/queue consumer | Command xử lý thất bại | Xác định retry/backoff, dead-letter và xử lý lặp |
| HTTP boundary | Ngoại lệ chưa được xử lý | Quyết định status/response an toàn, log có ngữ cảnh |

**Mã lỗi nghiệp vụ không nhất thiết trùng mã HTTP.** `OUT_OF_STOCK` có thể là một enum ổn định trong domain; controller lựa chọn HTTP status theo chính sách API. Đừng để domain object phụ thuộc trực tiếp vào một framework web chỉ để biểu diễn tình huống bị từ chối.

### Có nên tạo exception riêng?

Nếu caller cần phân biệt bằng loại exception, có thể tạo:

~~~java
final class OrderAlreadyShippedException
        extends IllegalStateException {
    OrderAlreadyShippedException(String orderId) {
        super("Đơn đã giao không được hủy: " + orderId);
    }
}
~~~

Không nhất thiết tạo một class exception cho mỗi câu thông báo. Chọn loại có ý nghĩa, ổn định; tránh ghi token, thông tin thanh toán hoặc dữ liệu nhạy cảm vào message rồi vô tình đưa vào log.

## 13. Retry, interrupt và lỗi bất đồng bộ

**Không retry tất cả exception.** `IllegalArgumentException` từ số lượng âm sẽ không tự khỏi sau ba lần gọi. Lỗi timeout có thể là tạm thời, nhưng timeout xảy ra **sau khi hệ thống ngoài đã xử lý** thì retry mù có thể thu tiền/gửi tin hai lần.

Với `InterruptedException`, nếu đã bắt nhưng không truyền tiếp, nên khôi phục cờ interrupt:

~~~java
try {
    Thread.sleep(1000);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return; // Trong một phương thức void.
}
~~~

Nếu method có thể khai báo `throws InterruptedException`, việc truyền tiếp thường rõ ràng hơn. Không nuốt interrupt khiến task bỏ qua yêu cầu hủy hoặc shutdown.

`CompletableFuture` có thể kết thúc theo cách **exceptional completion**. Caller nhìn thấy failure ở `join()`/`get()` qua các wrapper exception tương ứng. Hợp đồng cần phân biệt “đã lập lịch”, “đã xử lý xong trong bộ nhớ” và “bên ngoài xác nhận hoàn tất”.

## 14. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Lựa chọn tốt hơn |
| --- | --- | --- |
| `catch (Exception e) { return null; }` | Không phân biệt mất kết nối và không có giá trị | Optional cho “không có”; exception/result riêng cho lỗi |
| `catch (Exception ignored) {}` | Báo thành công giả | Xử lý có chủ đích hoặc truyền tiếp |
| `catch (Throwable t)` trong nghiệp vụ | Nuốt cả Error nghiêm trọng | Bắt loại exception có thể xử lý |
| `throw new RuntimeException(e.getMessage())` | Mất original cause | `new RuntimeException("...", e)` |
| Log toàn bộ stack trace ở mọi tầng | Log trùng và khó tìm boundary | Log tại ranh giới chịu trách nhiệm |
| So sánh `getMessage()` với chuỗi cứng | Dễ vỡ khi đổi ngôn ngữ/thông điệp | Kiểu exception hoặc error code |
| Trả `false` cho mọi failure | Mất ngữ cảnh xử lý | Result có lý do hoặc exception thích hợp |
| Sửa state rồi mới validate | Có thể để lại state không hợp lệ | Validate trước, transaction nếu cần |
| Catch exception và cho rằng đã rollback | Side effect trước đó vẫn tồn tại | Thiết kế atomicity/compensation |
| Retry lệnh có side effect mà không chống trùng | Xử lý hai lần | Idempotency key và kiểm soát cập nhật |
| Coi checked luôn recoverable, unchecked luôn bug | Sai trong nhiều API | Đọc hợp đồng và chính sách phục hồi |

## 15. Bài tập: hợp đồng chuyển tiền giữa hai tài khoản

Thiết kế `transfer(fromId, toId, amountVnd)` với các yêu cầu:

1. ID không rỗng, hai ID khác nhau, số tiền phải dương.
2. Một tài khoản có thể không tồn tại, bị khóa hoặc không đủ số dư.
3. Nếu thành công, nguồn bị trừ đúng số tiền, đích tăng đúng số tiền, tổng số dư hai tài khoản không đổi.
4. Nếu bị từ chối, **không tài khoản nào được thay đổi**.
5. Nếu database lỗi, không được biến lỗi đó thành “không tìm thấy tài khoản”.
6. Nếu số dư dùng `long` VND, phải xử lý overflow bằng `Math.addExact` hoặc cách biểu diễn phù hợp.
7. Nếu có hai lệnh đồng thời hoặc một lệnh được gửi lại qua queue, cần mô tả transaction, version/lock và idempotency key.

Hãy viết hợp đồng bằng bảng **preconditions/postconditions/invariants/failures**, chọn có lý do giữa `TransferResult` và typed domain exception, rồi viết JUnit test cho thành công, thiếu tiền, tài khoản khóa, số tiền âm, overflow và bảo toàn số dư khi thất bại.

**Tự kiểm tra:** caller có phân biệt được từ chối nghiệp vụ với lỗi hạ tầng không? Có trường hợp ném exception sau khi đã sửa một nửa dữ liệu không? Hợp đồng lỗi có đang phụ thuộc vào nội dung message dễ thay đổi không?

**Điều cần nhớ:** trong Java, exception là một cơ chế báo và truyền failure; **hợp đồng phương thức** quyết định failure đó có ý nghĩa gì, caller phải xử lý ra sao và đối tượng phải giữ bất biến nào. Một API tốt làm rõ cả đường thành công lẫn đường thất bại.