# Tách truy vấn khỏi thao tác thay đổi trạng thái trong thiết kế lớp (Command–Query Separation)

**Mục tiêu:** Biết phân biệt phương thức chỉ đọc trạng thái (*query*) với phương thức chủ động thay đổi trạng thái (*command*), thiết kế API Java dễ hiểu và dễ kiểm thử, xử lý ngoại lệ thực tế mà không nhầm với kiến trúc CQRS.

## 1. Vấn đề: một câu hỏi lại âm thầm gây thay đổi

Xét một lớp quản lý hàng tồn kho:

~~~java
class Inventory {
    private int quantity = 10;

    // Nghe như truy vấn số lượng còn lại nhưng đồng thời trừ kho.
    int getAvailableQuantity(int requested) {
        if (requested > quantity) {
            throw new IllegalArgumentException("Not enough stock");
        }
        quantity -= requested;
        return quantity;
    }
}
~~~

Tên `getAvailableQuantity` khiến người gọi kỳ vọng một câu hỏi đọc dữ liệu. Nhưng một lần gọi lại thay đổi số lượng trong kho. Ví dụ UI gọi lại để cập nhật màn hình, logging gọi để ghi thông tin, hoặc test gọi để kiểm tra trạng thái đều có thể vô tình làm mất hàng tồn.

**Command–Query Separation (CQS)** là nguyên tắc thiết kế phương thức thường gắn với Bertrand Meyer: một thao tác nên là **truy vấn cung cấp thông tin** hoặc **lệnh tạo thay đổi**, với hợp đồng rõ ràng về tác động của nó.

- **Query (truy vấn):** Trả về dữ liệu hoặc kết quả tính toán; không làm thay đổi **trạng thái quan sát được của miền nghiệp vụ**. Ví dụ: `availableQuantity()`, `canReserve(int)`, `balance()`.
- **Command (lệnh):** Thực hiện thay đổi trạng thái hoặc hành vi có tác dụng phụ như ghi DB, gửi yêu cầu thanh toán, phát sự kiện. Ví dụ: `reserve(int)`, `deposit(amount)`, `submitOrder()`.
- **Hợp đồng API phải làm rõ điều gì có thể xảy ra:** method có được gọi lặp hay không, có tính idempotent không, có thể ném ngoại lệ nào và trạng thái sau thất bại là gì.

Điều cốt lõi không phải tên `get...` hay kiểu trả về `void`, mà là **ý nghĩa hành vi**. Một method `void calculate()` vẫn có thể là query được thiết kế kém nếu không làm gì ngoài tính toán rồi bỏ kết quả. Ngược lại, `createOrder()` thường cần trả về mã đơn được tạo, dù nó là command. CQS là **hướng dẫn thiết kế**, không phải quy tắc cú pháp cưỡng bức.

## 2. Thiết kế lại một ví dụ nhỏ

Thiết kế ban đầu gộp đọc và thay đổi:

~~~java
final class BadStock {
    private int available = 10;

    int checkAndReserve(int units) {
        if (units <= 0 || units > available) {
            throw new IllegalArgumentException("Invalid quantity");
        }
        available -= units;
        return available;
    }
}
~~~

Có hai ý định nghiệp vụ khác nhau: **kiểm tra khả năng cấp hàng** và **thực sự giữ hàng**. Tách chúng:

~~~java
final class Stock {
    private int available = 10;

    // Query: không làm thay đổi số lượng.
    int availableUnits() {
        return available;
    }

    // Query: có thể hỏi nhiều lần, không tự giữ hàng.
    boolean canReserve(int units) {
        return units > 0 && units <= available;
    }

    // Command: giữ hàng nếu thỏa điều kiện tại thời điểm thực thi.
    void reserve(int units) {
        if (!canReserve(units)) {
            throw new IllegalArgumentException("Not enough stock or invalid units");
        }
        available -= units;
    }
}
~~~

Cách sử dụng:

~~~java
Stock stock = new Stock();

System.out.println(stock.canReserve(4));   // true
System.out.println(stock.availableUnits()); // 10
stock.reserve(4);                           // Command
System.out.println(stock.availableUnits()); // 6
~~~

**Điểm quan trọng:** `canReserve(4)` không bảo đảm `reserve(4)` sẽ luôn thành công sau đó nếu nhiều luồng/giao dịch cùng dùng kho. Command phải **tự kiểm tra lại điều kiện tại thời điểm ghi**. Không tách thành “query kiểm tra rồi command trừ không điều kiện” trong hệ thống đồng thời.

## 3. Java 17: API tài khoản có truy vấn thuần và lệnh an toàn

Ví dụ hoàn chỉnh dùng `BigDecimal` cho tiền và đồng bộ trên một đối tượng để việc kiểm tra–thay đổi số dư là nguyên tử trong **một process**. Mọi loại tiền trong ví dụ được xem là cùng đơn vị; hệ thống tài chính thật phải mô hình hóa currency, scale và chính sách làm tròn.

**Tệp `AccountDemo.java`:**

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record AccountSnapshot(BigDecimal balance, List<String> movements) {
    AccountSnapshot {
        Objects.requireNonNull(balance, "balance");
        movements = List.copyOf(Objects.requireNonNull(movements, "movements"));
    }
}

final class Account {
    private BigDecimal balance = BigDecimal.ZERO;
    private final List<String> movements = new ArrayList<>();

    // Query: trả về giá trị bất biến; không sửa trạng thái.
    synchronized BigDecimal balance() {
        return balance;
    }

    // Query: không lộ danh sách có thể sửa của lớp.
    synchronized AccountSnapshot snapshot() {
        return new AccountSnapshot(balance, movements);
    }

    // Query: không tự động trừ tiền.
    synchronized boolean canWithdraw(BigDecimal amount) {
        return amount != null
                && amount.signum() > 0
                && balance.compareTo(amount) >= 0;
    }

    // Command: ghi nhận khoản tiền vào.
    synchronized void deposit(BigDecimal amount) {
        requirePositive(amount);
        balance = balance.add(amount);
        movements.add("DEPOSIT " + amount.toPlainString());
    }

    // Command: kiểm tra lại điều kiện ngay trong vùng đồng bộ.
    synchronized void withdraw(BigDecimal amount) {
        requirePositive(amount);
        if (balance.compareTo(amount) < 0) {
            throw new IllegalStateException("Insufficient balance");
        }
        balance = balance.subtract(amount);
        movements.add("WITHDRAW " + amount.toPlainString());
    }

    private static void requirePositive(BigDecimal amount) {
        Objects.requireNonNull(amount, "amount");
        if (amount.signum() <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
    }
}

public class AccountDemo {
    public static void main(String[] args) {
        Account account = new Account();

        account.deposit(new BigDecimal("100.00"));
        System.out.println(account.canWithdraw(new BigDecimal("40.00"))); // true
        System.out.println(account.balance()); // 100.00

        account.withdraw(new BigDecimal("40.00"));
        AccountSnapshot result = account.snapshot();
        System.out.println(result.balance()); // 60.00
        System.out.println(result.movements());
        // [DEPOSIT 100.00, WITHDRAW 40.00]
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AccountDemo.java
java AccountDemo
~~~

**Vì sao đây là một thiết kế có CQS rõ ràng?**

| Phương thức | Vai trò | Giá trị trả về | Có thay đổi trạng thái nghiệp vụ? |
|---|---|---|---|
| `balance()` | Query | `BigDecimal` | Không |
| `snapshot()` | Query | `AccountSnapshot` bất biến | Không |
| `canWithdraw(amount)` | Query | `boolean` | Không |
| `deposit(amount)` | Command | `void` | Có: số dư và lịch sử |
| `withdraw(amount)` | Command | `void` | Có: số dư và lịch sử |
| `requirePositive(amount)` | Hàm kiểm tra nội bộ | `void` hoặc exception | Không |

`AccountSnapshot` dùng `List.copyOf` để giữ bản sao không thể sửa bằng API collection. `BigDecimal` và `String` cũng là kiểu bất biến. Nếu snapshot chứa đối tượng lồng có thể sửa thì `List.copyOf` **không** tự biến các đối tượng lồng thành bất biến.

`synchronized` giúp phối hợp thao tác trên **cùng một đối tượng Account trong một JVM**. Đây không phải giải pháp cho nhiều instance dịch vụ cùng cập nhật một tài khoản trong DB; ứng dụng thực cần transaction, khóa hoặc optimistic locking và kiểm soát concurrency tại nơi lưu trữ.

## 4. Trực quan hóa luồng đọc và ghi

~~~mermaid
flowchart TD
    Client[Ứng dụng/UI] --> Q[Query: snapshot / balance]
    Q --> S[(Trạng thái hiện tại)]
    S --> R[Trả dữ liệu, không sửa trạng thái]
    Client --> C[Command: deposit / withdraw]
    C --> V{Điều kiện hợp lệ?}
    V -->|Không| E[Trả lỗi, không thay đổi số dư]
    V -->|Có| U[Cập nhật số dư và lịch sử]
    U --> S
~~~

Bộ phận giao diện có thể gọi query để hiển thị bao nhiêu lần tùy ý mà không làm thay đổi tài khoản. Command phản ánh **một ý định thực hiện hành động** của người dùng hoặc use case. Nếu UI gọi command hai lần do retry, điều đó không tự động an toàn: cần xem xét idempotency.

## 5. CQS và CQRS: liên quan nhưng không giống nhau

**CQS** là nguyên tắc **thiết kế phương thức/API**, thường áp dụng ngay bên trong một lớp OOP. **CQRS** (*Command Query Responsibility Segregation*) là một cách **tổ chức kiến trúc** tách đường xử lý lệnh và truy vấn, đôi khi dùng mô hình dữ liệu hoặc nơi lưu trữ riêng.

| Khía cạnh | CQS | CQRS |
|---|---|---|
| Cấp độ | Phương thức, lớp, interface, API | Application / hệ thống / kiến trúc |
| Câu hỏi | Method này đọc hay làm thay đổi trạng thái? | Đường đọc và ghi cần xử lý bằng mô hình/thành phần riêng hay không? |
| Bắt buộc tách database? | Không | Cũng không bắt buộc; có thể tách handler nhưng dùng cùng DB |
| Mục tiêu | Tính dễ đoán, dễ dùng và kiểm thử của API | Mô hình đọc/ghi độc lập theo nhu cầu nghiệp vụ, mở rộng và hiệu năng |
| Ví dụ | `account.balance()` / `account.withdraw(x)` | `WithdrawCommandHandler` / `AccountBalanceQueryHandler` |
| Chi phí | Thường thấp | Có thể cao: thêm mapping, synchronization, eventual consistency |

Một ứng dụng có CQS tốt **không cần** áp dụng CQRS. Nếu CQRS có read model được cập nhật bất đồng bộ, dữ liệu đọc có thể **trễ** sau command thành công; phải định nghĩa yêu cầu nhất quán. CQS trong một đối tượng không tự tạo độ trễ đó.

~~~mermaid
flowchart LR
    UI[Client] --> Query[Query API]
    UI --> Command[Command API]
    Query --> Read[(Read model)]
    Command --> Write[(Write model)]
    Write -. cập nhật/projection .-> Read
~~~

Sơ đồ chỉ minh họa **một kiến trúc CQRS có mô hình đọc và ghi riêng**; không phải điều kiện cần để tuân thủ CQS.

## 6. Ranh giới của “không thay đổi trạng thái”

Một query lý tưởng không có **tác dụng phụ quan sát được** đối với domain. Cần phân biệt:

1. **Thay đổi dữ liệu nghiệp vụ:** `getBalance()` tự tăng phí, `findOrder()` tự đánh dấu đơn đã giao → trái kỳ vọng query; nên tách thành command có tên rõ.
2. **Ghi log, metrics, tracing:** hệ thống quan sát có thể tạo dữ liệu kỹ thuật, nhưng đó không nên làm kết quả nghiệp vụ thay đổi. Nên minh bạch, đặc biệt với audit log và quyền riêng tư.
3. **Cache/memoization:** một getter lần đầu tính rồi lưu cache là thay đổi trạng thái nội bộ vì tối ưu. Về mặt CQS thực dụng, có thể chấp nhận nếu **giữ nguyên hành vi quan sát được**, không ảnh hưởng luồng xử lý, concurrency hay idempotency; tuyệt đối không dùng cache để che giấu một command nghiệp vụ.
4. **Lazy loading ORM:** đọc getter của JPA entity có thể kích hoạt SQL SELECT, network và exception nếu session đóng. Dù không chủ động cập nhật dữ liệu, phương thức không còn “thuần” theo nghĩa không I/O. Cần biết ranh giới persistence, tránh giả định mọi getter rẻ hoặc an toàn sau transaction.
5. **Truy vấn tăng bộ đếm đọc hoặc ghi `lastSeen`:** nếu đó là thay đổi domain, nên thiết kế như một command riêng hoặc một use case được đặt tên phản ánh cả đọc và ghi; không che dấu trong `get...`.
6. **Đọc file hay gọi API:** là query về mặt intent nếu chỉ thu thập thông tin, nhưng có thể timeout/thất bại. “Không thay đổi trạng thái domain” không đồng nghĩa “không bao giờ phát sinh I/O”.

Một query được gọi nhiều lần với cùng dữ liệu và không có sửa đổi xen giữa nên cho kết quả nhất quán theo hợp đồng. Không nhất thiết trả về **cùng object identity**, đặc biệt khi tạo snapshot mới.

## 7. Command có bắt buộc trả về void?

Không. Phân loại theo **tác dụng** chứ không chỉ kiểu trả về.

Ví dụ `createOrder(request)` ghi đơn mới và trả về `OrderId`. Đây vẫn là **command**:

~~~java
record OrderId(String value) {}

interface OrderCommands {
    OrderId createOrder(CreateOrderRequest request); // Có hiệu ứng ghi
}

interface OrderQueries {
    OrderView findById(OrderId id);     // Chỉ trả dữ liệu
}
~~~

Trả `OrderId`, trạng thái thành công hoặc phiên bản mới là cách hợp lý để xác định kết quả command. Tuy nhiên, cần tránh việc một method vừa âm thầm ghi rồi trả nguyên một danh sách phức tạp để giả làm query. Nếu nghiệp vụ cần một giá trị tổng hợp mới sau khi ghi, cân nhắc command trả ID/version và query riêng khi thực sự có lợi. Đừng tách thêm API chỉ để đạt “void tuyệt đối” nếu khiến caller phải gọi thừa không cần thiết.

Một quy ước tiện dụng:

- `get`, `find`, `list`, `calculate`, `can` → ưu tiên query rõ ràng.
- `create`, `update`, `reserve`, `pay`, `withdraw`, `cancel` → thể hiện command rõ ràng.
- `getAndReset`, `readAndMarkSeen`, `checkAndReserve` → cần xem xét tách trách nhiệm hoặc đổi tên/hợp đồng để làm lộ hiệu ứng.

Tên chỉ là tín hiệu. Các quy tắc nghiệp vụ, transaction, error handling và quyền hạn quyết định nội dung thực sự.

## 8. Tránh điều kiện kiểm tra rồi thực hiện không nguyên tử (TOCTOU)

Tách query và command rất hữu ích, nhưng có thể tạo lỗi nếu caller tưởng kết quả query “khóa” trạng thái:

~~~java
if (inventory.canReserve(2)) {
    inventory.reserve(2); // Một caller khác có thể đã giữ hàng trước đó.
}
~~~

Đây là **time-of-check to time-of-use (TOCTOU)**. Cách xử lý:

- Query `canReserve` chỉ giúp UI hiển thị khả năng **tạm thời**, không bảo đảm thành công.
- Command `reserve` phải kiểm tra lại **trong cùng vùng bảo vệ thay đổi**.
- Với cùng một JVM, có thể dùng `synchronized` hay lock phù hợp để gộp kiểm tra–ghi.
- Với database, nên thực hiện update có điều kiện trong transaction hoặc dùng version/optimistic locking. Ví dụ điều kiện `WHERE available >= :qty` và kiểm tra số hàng cập nhật. Không dựa vào `SELECT` trước đó làm bằng chứng chắc chắn.
- Với nhiều service, phải xác định ranh giới nhất quán ở nơi thật sự sở hữu tồn kho, thay vì chỉ khóa object ở một instance ứng dụng.

CQS tách **ý định đọc** và **ý định thay đổi**; tính nguyên tử là một yêu cầu khác cần đảm bảo ở command.

## 9. Idempotency của command và an toàn khi retry

**Query không có side effect nghiệp vụ**, nhưng command có thể tạo tác dụng phụ. Một command không mặc định idempotent:

- `setStatus("PAID")` thường idempotent nếu thực hiện lại không tạo thêm hiệu ứng.
- `deposit(100)` thực hiện hai lần tăng số dư hai lần: **không idempotent**.
- `sendEmail()` gọi lại có thể gửi thêm email dù dữ liệu không đổi.

Khi client retry do timeout, cần một **idempotency key** gắn với ý định giao dịch. Ví dụ API nhận `requestId` duy nhất rồi ghi nhận yêu cầu đã hoàn thành để lần gửi lại không chạy hiệu ứng lần nữa.

~~~text
POST /payments
Idempotency-Key: pay-req-8f9...
Body: {"orderId":"O-101","amountCents":50000}
~~~

Để thực hiện đúng trên nhiều instance, việc kiểm tra/chèn khóa và cập nhật dữ liệu cần atomic trong cơ chế lưu trữ thích hợp; một `HashSet<String>` trong RAM đơn lẻ không bảo đảm an toàn đa process hoặc restart.

## 10. Test nguyên tắc CQS bằng hành vi quan sát được

Với tệp `AccountDemo.java` ở mục 3, có thể tạo **`AccountTest.java`** dùng JUnit Jupiter 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class AccountTest {
    @Test
    void queriesDoNotChangeBalanceOrMovements() {
        Account account = new Account();
        account.deposit(new BigDecimal("100.00"));

        AccountSnapshot before = account.snapshot();

        assertTrue(account.canWithdraw(new BigDecimal("40.00")));
        assertEquals(0, new BigDecimal("100.00").compareTo(account.balance()));
        assertEquals(before, account.snapshot()); // Cùng giá trị quan sát được
    }

    @Test
    void commandsChangeStateAndPreserveInvariant() {
        Account account = new Account();
        account.deposit(new BigDecimal("100.00"));
        account.withdraw(new BigDecimal("40.00"));

        assertEquals(0, new BigDecimal("60.00").compareTo(account.balance()));
        assertEquals(2, account.snapshot().movements().size());

        AccountSnapshot beforeError = account.snapshot();
        assertThrows(IllegalStateException.class,
                () -> account.withdraw(new BigDecimal("100.00")));
        assertEquals(beforeError, account.snapshot());
    }

    @Test
    void snapshotCannotBeMutatedFromOutside() {
        Account account = new Account();
        account.deposit(BigDecimal.ONE);

        assertThrows(UnsupportedOperationException.class,
                () -> account.snapshot().movements().clear());
        assertEquals(1, account.snapshot().movements().size());
    }
}
~~~

Các test trên xác nhận query không thay đổi trạng thái nghiệp vụ, command giữ invariant khi thành công và thất bại, snapshot không lộ collection mutable. Chúng **không** kiểm thử độ bền dữ liệu database, bảo đảm phân tán hoặc hiệu ứng thanh toán thật. Những khía cạnh đó cần integration tests phù hợp.

Không cần test dựa vào reflection để đếm số method có prefix `get` hay xem kiểu trả về có phải `void`; điều đó không chứng minh hợp đồng đọc/ghi.

## 11. Quy trình refactor method đang trộn query và command

~~~mermaid
flowchart TD
    A[Nhận diện method vừa đọc vừa thay đổi] --> B[Liệt kê kết quả và side effect]
    B --> C[Thiết kế query không thay đổi domain]
    C --> D[Thiết kế command thể hiện ý định ghi]
    D --> E[Cập nhật callers và hợp đồng lỗi]
    E --> F[Đảm bảo validation và ghi atomic]
    F --> G[Kiểm thử kết quả, rollback và retry]
~~~

Thực hiện theo thứ tự:

1. **Tìm đúng các method khả nghi:** `getAndDelete`, `fetchAndMarkRead`, `calculateAndSave`, `checkAndReserve`, getter có setter ẩn hoặc query phát thông báo.
2. **Xác định side effect cần giữ:** thay đổi field, DB, cache nghiệp vụ, event, email, transaction; đồng thời liệt kê giá trị trả về và ngoại lệ hiện hành.
3. **Làm rõ use case:** người dùng đang hỏi tình trạng hay đang yêu cầu thay đổi? Cùng một thao tác có thể cần hai API nếu cả hai nhu cầu đều hợp lệ.
4. **Tạo query có hợp đồng đọc:** trả snapshot/DTO/value object khi cần ngăn sửa trạng thái qua object tham chiếu.
5. **Tạo command có tên phản ánh thay đổi:** tự validation và đảm bảo invariant tại thời điểm ghi; quyết định return value thiết thực.
6. **Di chuyển caller:** thay code đang dựa vào side effect của getter; lưu ý API public có thể cần deprecation/migration.
7. **Kiểm tra transaction/concurrency/retry:** tránh tình trạng check trước, ghi sau thiếu khóa; bổ sung idempotency khi hành vi cần.
8. **Kiểm thử:** query không tạo tác động ngoài mong đợi, command xử lý thành công/thất bại nhất quán, integration test xác nhận tác động thật.

**Ví dụ quyết định refactor:** `MessageService.fetchAndMarkRead(id)` có thể tách thành `findById(id)` và `markRead(id)` nếu UI vừa cần xem trước mà không đánh dấu đã đọc, vừa cần đánh dấu chủ động. Nếu nghiệp vụ quy định “xem tin nhắn đồng nghĩa đánh dấu đã đọc” thì có thể giữ một **use case command** `openMessage(id)` trả nội dung và nêu rõ hiệu ứng trong hợp đồng; không che hành vi đó sau tên `getMessage`.

## 12. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Getter tự ghi dữ liệu nghiệp vụ | Refresh UI có thể tạo thay đổi ngoài ý muốn | Tách query khỏi command hoặc đặt tên/hợp đồng thể hiện side effect |
| Nghĩ command bắt buộc `void` | Tạo API bất tiện, truy vấn thừa để lấy ID/version | Cho command trả metadata cần thiết, vẫn gọi đúng là command |
| Nghĩ CQS chính là CQRS | Áp dụng architecture phức tạp cho bài toán đơn giản | Phân biệt mức method với mức kiến trúc |
| Query trả thẳng `List` mutable bên trong | Caller sửa state không qua command | Trả snapshot/immutable view phù hợp |
| Chỉ kiểm tra trước bằng query | TOCTOU/race condition | Command kiểm tra–ghi nguyên tử tại owner của dữ liệu |
| Coi cache nội bộ giống thay đổi nghiệp vụ | Tối ưu vô hại cũng bị cấm máy móc | Xác định rõ trạng thái quan sát được và giới hạn side effect |
| Retry command không idempotent | Thanh toán/ghi dữ liệu bị lặp | Sử dụng idempotency key và transaction phù hợp |
| Tách mọi API một cách cực đoan | Tăng call round-trip, tăng complexity | Chọn ranh giới có lợi ích thực tế |

## 13. Bài tập vận dụng

Một hệ thống thư viện có:

~~~java
BookView borrowAndGetBook(String bookId, String memberId);
~~~

Method vừa trừ số sách còn lại, tạo phiếu mượn, vừa trả nội dung hiển thị sách.

Hãy xác định các nhu cầu thực tế và thiết kế lại:

- `BookView findBook(String bookId)` chỉ đọc metadata/số lượng tại thời điểm truy vấn.
- `BorrowReceipt borrowBook(String bookId, String memberId, String requestId)` là command kiểm tra quyền mượn, điều kiện tồn kho và ghi phiếu mượn trong transaction. Nó có thể trả phiếu biên nhận để dùng ngay.
- Nếu UI cần trạng thái mới nhất sau khi mượn, có thể query lại; nếu hệ thống dùng optimistic update thì kiểm tra trường hợp mượn thất bại do cạnh tranh.
- Nếu client retry, bảo đảm `requestId` không tạo hai phiếu mượn.

**Câu hỏi tự kiểm tra:** Người gọi có thể nhận ra method nào làm thay đổi hệ thống không? Query có an toàn khi được gọi lặp không? Command có bảo vệ invariant tại lúc ghi không? API có nêu rõ trạng thái lỗi và các hiệu ứng ngoài hệ thống không?

---

**Ghi nhớ:** Hãy thiết kế phương thức để một câu hỏi **không bí mật làm thay đổi trạng thái nghiệp vụ**, còn lệnh **thể hiện rõ ý định thay đổi**. Phân tách đúng làm API dễ dự đoán, nhưng vẫn phải bảo vệ tính nguyên tử, tính nhất quán và khả năng retry của những command có side effect.