# Thiết kế API giữ trạng thái hợp lệ khi có lỗi

Một API Java không được xem là đúng chỉ vì nó ném ra exception có tên phù hợp. Sau khi một phương thức thất bại, đối tượng mà phương thức đang sửa có thể vẫn tồn tại, được gọi lại và được quan sát bởi những thành phần khác. Nếu ngoại lệ xuất hiện sau một phần thao tác cập nhật, API có nguy cơ để lại **trạng thái nửa chừng**, phá vỡ invariant, rò rỉ tài nguyên hoặc báo cho caller một kết quả không phản ánh điều đã xảy ra.

**Mục tiêu của thiết kế exception-safe API** là xác định và thực thi một hợp đồng rõ ràng: khi phương thức trả về hoặc ném exception, đối tượng còn ở những trạng thái hợp lệ nào; phần thay đổi nào đã được commit; tài nguyên nào đã được giải phóng; caller có thể thử lại, đọc tiếp hay buộc phải tạo đối tượng mới?

Ví dụ, một API quản lý tồn kho phải tránh trạng thái `availableStock = -3` nếu business invariant yêu cầu không âm. API chuyển tiền phải tránh trạng thái nguồn đã trừ tiền nhưng đích chưa cộng tiền **khi hợp đồng hứa tính nguyên tử**. Một service có thể thất bại khi gửi thông báo sau khi ghi dữ liệu: lúc đó việc ghi có thể đã thành công, nên không được tùy tiện nói rằng toàn bộ nghiệp vụ đã rollback.

Bài thực hành này dùng Java 17+ để thiết kế và kiểm tra ranh giới *validate → prepare → commit*, mức bảo đảm exception, quản lý tài nguyên, cập nhật nhiều bước, publication và concurrency. Các ví dụ độc lập có lệnh biên dịch/chạy và stdout xác định; các đoạn cần framework/database ngoài JDK được đánh dấu là minh họa.

## 1. Trạng thái hợp lệ là một hợp đồng, không chỉ là vài field

Trước khi viết method, hãy ghi rõ **invariant**: điều kiện phải đúng tại các thời điểm mà caller được phép quan sát đối tượng.

Ví dụ với kho đơn giản:

- `available >= 0`.
- Mỗi reservation có định danh không rỗng và số lượng dương.
- Một reservation ID không được tạo trùng nếu contract yêu cầu duy nhất.
- Tất cả reservation đã commit nhất quán với số lượng hàng còn lại.
- Khi gọi method thất bại theo strong guarantee, snapshot trạng thái sau phải bằng snapshot trước.
- Khi kết thúc thao tác, resource được method sở hữu không còn bị bỏ quên.
- Nếu object ở trạng thái `CLOSED`, các thao tác đòi `OPEN` phải bị từ chối rõ ràng.

Các invariant là **giả định thiết kế của API cụ thể**. Một hệ thống cho phép backorder có thể cho tồn kho âm có kiểm soát; khi đó yêu cầu `available >= 0` sẽ không còn đúng. Đừng copy invariant từ ví dụ rồi áp đặt lên một domain khác.

Đặt câu hỏi cho mỗi phương thức public:

| Câu hỏi | Ví dụ quyết định hợp đồng |
| --- | --- |
| Precondition là gì? | `quantity > 0`, `orderId` không blank, object chưa closed. |
| State nào được thay đổi? | Tồn kho, danh sách reservation, version và event pending. |
| Khi nào commit? | Sau khi validate và dựng candidate hoàn chỉnh. |
| Nếu validate lỗi? | Ném `IllegalArgumentException`, state không đổi. |
| Nếu thiếu tồn kho? | Ném domain exception, state không đổi. |
| Nếu tạo candidate lỗi? | Không publish candidate; state cũ giữ nguyên. |
| Nếu dependency bên ngoài lỗi? | Theo transaction/operation ID; có thể phải báo UNKNOWN. |
| Ai sở hữu resource? | Scope tạo resource đóng đúng resource đó. |
| Caller làm gì sau lỗi? | Có thể dùng object tiếp, retry có điều kiện hoặc chuyển sang FAILED. |

Nếu những câu hỏi này chưa có câu trả lời, thêm `catch` để “xử lý exception” thường chỉ che giấu vấn đề.

## 2. Ba mức exception safety cần phân biệt

Những khái niệm sau rất hữu ích khi mô tả hợp đồng API, dù Java không cung cấp annotation chuẩn để tự động thực thi chúng.

| Mức | Điều phải đúng sau exception | Ví dụ |
| --- | --- | --- |
| **Strong guarantee** | Thất bại không làm thay đổi trạng thái quan sát được trong phạm vi đã cam kết. | `reserve` từ chối yêu cầu vượt tồn kho mà không thêm reservation và không trừ stock. |
| **Basic guarantee** | Invariant vẫn đúng, tài nguyên không rò rỉ, nhưng trạng thái có thể đã có tiến độ một phần được cho phép. | `importBatch` giữ 7 record thành công, lỗi ở record thứ 8, và báo checkpoint để tiếp tục. |
| **No-throw guarantee** | Một thao tác được thiết kế không ném trong phạm vi hợp đồng; thường áp dụng cho bước cleanup đơn giản, đáng tin cậy. | Cập nhật cờ `closed` in-memory không làm I/O và không ném. |

### Strong không có nghĩa mọi thứ trên thế giới đều rollback

Nếu API chỉ cam kết trạng thái **in-memory của object**, một file/HTTP request đã gửi trước lỗi không tự được thu hồi. Cần ghi ranh giới của strong guarantee rõ ràng: object state, một transaction DB, hay cả một workflow có cơ chế bù.

### Basic không có nghĩa object được phép hỏng

Một batch import có thể giữ record đã ghi thành công, nhưng index/counter/list phải nhất quán. Caller cần biết phần đã hoàn thành và phần chưa hoàn thành. Trạng thái nửa khởi tạo, số lượng âm sai invariant hoặc resource leak không phải là “basic guarantee”.

### No-throw phải dựa trên implementation thật

`AutoCloseable.close()` có thể ném exception. Một thao tác ghi file, flush buffer hoặc đóng network connection không tự động là no-throw. Chỉ công bố mức không ném khi có cơ sở và đã xét những tình huống cần xử lý lỗi tài nguyên.

## 3. Anti-pattern: thay đổi trạng thái trước khi xác minh

Một lỗi cơ bản:

```java
void reserve(int quantity) {
    available -= quantity;
    if (available < 0) {
        throw new IllegalStateException("insufficient stock");
    }
}
```

Đây là đoạn minh họa, giả định `available` là field. Nếu có 5 sản phẩm và caller đặt 7, method ném đúng exception nhưng để `available=-2`.

Một lỗi tinh vi hơn:

```java
void reserve(String id, int quantity) {
    reservations.add(id);
    validateQuantity(quantity);
    available -= quantity;
}
```

Đây là snippet chưa độc lập. Nếu `validateQuantity` ném, danh sách reservation đã bị sửa. Nếu `available -= quantity` thực thi sau nhiều lời gọi phụ có thể lỗi, trạng thái càng khó đối soát.

**Quy tắc thực hành:** kiểm tra tất cả precondition và trạng thái nghiệp vụ có thể kiểm tra trước khi mutate; chuẩn bị dữ liệu mới ngoài state chính; chỉ commit sau khi chuẩn bị thành công. Nhưng cũng phải xét exception đến từ **bước sau commit**: logging, callback, persistence hoặc event publication có thể phá giả định “nếu ném thì không đổi”.

## 4. Khuôn thiết kế validate → prepare → commit

Mô hình:

```text
Trạng thái S0
    |
    +--> VALIDATE (đọc, kiểm tra precondition/invariant)
    |       \-- lỗi: throw, S0 không đổi
    |
    +--> PREPARE (tạo các cấu trúc/value object mới)
    |       \-- lỗi: bỏ candidate, S0 không đổi
    |
    +--> COMMIT (publish state mới trong điểm được kiểm soát)
    |       \-- đã commit: caller phải biết semantics sau commit
    |
    +--> AFTER-COMMIT (outbox/notification theo contract)
            \-- lỗi: không tùy tiện tuyên bố transaction rollback
```

Khi giữ toàn bộ mutable state trong một immutable value object, commit có thể là **một lần thay reference**. Với state cập nhật đồng thời, thao tác commit còn cần lock/CAS/transaction phù hợp. Một reference assignment tự nó không xử lý race khi nhiều thread cùng đọc S0.

Một ví dụ sketch:

```java
State original = state;
validate(input, original);
State candidate = calculateNewState(original, input);
state = candidate; // Commit sau khi prepare thành công.
```

Đây là đoạn minh họa; `State`, `input`, `validate` và `calculateNewState` được định nghĩa ở nơi khác. Nếu `calculateNewState` chỉ dựng dữ liệu local và không tác động bên ngoài, thất bại trước gán giữ state gốc. Nếu hàm prepare lại tự gọi HTTP để thực hiện thanh toán, nó **không còn side-effect-free**, và strong guarantee của cả workflow không còn được bảo đảm chỉ bằng câu lệnh gán cuối.

## 5. Ví dụ Java 17 hoàn chỉnh: thiết kế Inventory exception-safe

Chương trình sau dùng `record` bất biến làm state, danh sách reservation không chỉnh sửa được và `synchronized` để serialize lời gọi vào cùng Inventory. Nó mô phỏng ba trường hợp: không đủ hàng, lỗi được chèn **trước commit**, và thao tác thành công. Mọi exception xảy ra **trước commit** giữ snapshot cũ.

Tạo file `ExceptionSafeInventoryDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ExceptionSafeInventoryDemo {

    private record State(int available, List<String> reservations) {
        State {
            if (available < 0) {
                throw new IllegalArgumentException("negative stock");
            }
            reservations = List.copyOf(reservations);
        }
    }

    private static final class Inventory {
        private State state = new State(5, List.of());

        synchronized State snapshot() {
            return state;
        }

        synchronized void reserve(
                String orderId, int quantity, boolean failBeforeCommit) {
            Objects.requireNonNull(orderId, "orderId");

            if (orderId.isBlank() || quantity <= 0) {
                throw new IllegalArgumentException("invalid reservation");
            }

            State old = state;
            if (quantity > old.available()) {
                throw new IllegalStateException("insufficient stock");
            }

            List<String> candidateReservations =
                    new ArrayList<>(old.reservations());
            candidateReservations.add(orderId + ":" + quantity);

            State candidate = new State(
                    old.available() - quantity, candidateReservations);

            if (failBeforeCommit) {
                throw new IllegalStateException("injected before commit");
            }

            state = candidate;
        }
    }

    public static void main(String[] args) {
        Inventory inventory = new Inventory();
        State initial = inventory.snapshot();

        try {
            inventory.reserve("order-A", 7, false);
        } catch (IllegalStateException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
        System.out.println("unchanged after rejection: "
                + initial.equals(inventory.snapshot()));

        try {
            inventory.reserve("order-B", 2, true);
        } catch (IllegalStateException ex) {
            System.out.println("injected: " + ex.getMessage());
        }
        System.out.println("unchanged after injection: "
                + initial.equals(inventory.snapshot()));

        inventory.reserve("order-C", 2, false);
        System.out.println("after success: " + inventory.snapshot());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 ExceptionSafeInventoryDemo.java
java ExceptionSafeInventoryDemo
```

Stdout xác định:

```text
rejected: insufficient stock
unchanged after rejection: true
injected: injected before commit
unchanged after injection: true
after success: State[available=3, reservations=[order-C:2]]
```

**Vì sao ví dụ giữ state đúng?**

1. Kiểm tra `orderId`, số lượng và tồn kho diễn ra **trước** khi gán `state`.
2. `candidateReservations` là danh sách mới, không phải list nội bộ đang dùng.
3. Constructor của `State` bảo đảm invariant tồn kho không âm và copy danh sách; lỗi trong bước dựng candidate chưa thay đổi state hiện tại.
4. Nhánh `failBeforeCommit` cố ý ném sau prepare và trước gán. Do đó snapshot không đổi.
5. Gán `state = candidate` là điểm commit in-memory. Sau đó method kết thúc ngay, không gọi một callback có thể ném làm mơ hồ nghĩa exception.
6. `synchronized` trên `reserve` và `snapshot` tránh hai lời gọi của **cùng object** đọc và ghi state đè nhau theo đoạn mã ví dụ.

**Giới hạn:** ví dụ chưa kiểm tra duplicate order ID, chưa có DB, event hoặc retry. Nếu domain yêu cầu ID duy nhất, phải kiểm tra hoặc mã hóa invariant ấy trước commit. `List.copyOf` chỉ copy nông, nhưng phần tử ở đây là `String` bất biến. Với nested mutable objects, cần snapshot sâu/value type thích hợp.

`synchronized` bảo vệ các method đang đồng bộ trên cùng monitor của Inventory; nó không tạo transaction xuyên nhiều JVM và không bảo vệ bất cứ biến shared nào nằm ngoài lock.

## 6. Khi nào một lần thay reference là đủ?

Với state in-memory hoàn toàn bất biến và mọi computation trước commit không có side effect, thay reference tại một điểm rõ có thể giúp thực hiện strong guarantee **đối với failure trước commit**.

Tuy nhiên, phải phân biệt ba loại atomicity:

- **Atomic reference publication:** caller đồng bộ nhìn state trước hoặc sau thay reference, không nhìn bản ghi nửa cập nhật.
- **Atomic read-modify-write:** hai lời gọi đồng thời không ghi đè cập nhật của nhau; cần lock, CAS loop hoặc cơ chế tương đương.
- **Atomic persistence/side effects:** database, cache, queue và dịch vụ bên ngoài nhất quán theo một transaction/hợp đồng. Không thể đạt bằng gán field Java.

Nếu API cho phép đọc từ thread khác mà không đồng bộ, chỉ gán một reference bình thường chưa đủ bảo đảm **visibility** theo Java Memory Model. Có thể dùng `synchronized`, `volatile` hoặc `AtomicReference` thích hợp, nhưng phải lựa chọn sao cho cả logic đọc-sửa-ghi đúng.

Đối với nhiều object cùng tham gia một operation, đôi khi lock chung, transaction hoặc coordinator là điều kiện cần. Đừng nhầm một immutable state đẹp với bảo đảm toàn workflow không thể thấy trạng thái tạm.

## 7. Thiết kế trước commit và sau commit tách biệt

Một phản mẫu:

```java
void createOrder(Order order) {
    database.insert(order);
    emailService.sendConfirmation(order); // Có thể ném IOException.
}
```

Đây là đoạn minh họa với các dependency giả định. Khi gửi email ném, database có thể đã lưu đơn. Nếu caller nhận exception rồi gọi lại `createOrder`, đơn hàng/email có thể trùng.

Giải pháp phải dựa trên **hợp đồng nghiệp vụ**:

- Nếu muốn **đơn hàng và nhiệm vụ gửi email** được ghi nguyên tử, có thể đưa **outbox event** vào cùng transaction DB với đơn hàng.
- Worker khác xử lý outbox, retry phát event với idempotency/dedup; việc gửi email thực tế là một lifecycle riêng.
- Nếu API trả về ngay sau commit DB, nó nên nêu rõ thông báo có thể đang **pending**, không biến lỗi gửi mail thành “đơn chưa được tạo” sai sự thật.
- Nếu dependency có thể commit rồi mất response, cần operation ID và đối soát; không suy ra “không đổi” từ `IOException` của caller.

Với transaction DB thật, trạng thái được commit khi database xác nhận theo contract. Một JVM crash giữa các bước không được giải quyết bằng `finally` hay by-value record in-memory.

### Side effect nên được thực hiện lúc nào?

Không có quy tắc chung rằng mọi side effect phải đặt sau commit. Ví dụ cần authorization trước commit; một số bước read-only gọi dependency phải hoàn thành trước quyết định. Điều quan trọng là biết **bước nào có side effect, bước nào có thể lỗi và điểm commit nào là ranh giới của hợp đồng**.

Với event publication sau commit, test phải kiểm tra “đơn đã commit nhưng event còn pending” theo design; không ép rollback vô điều kiện chỉ vì callback downstream ném.

## 8. Ví dụ Java 17 hoàn chỉnh: ghi business state và outbox cùng một snapshot

Ví dụ in-memory sau biểu diễn nguyên lý *outbox*: một lần commit đưa cả order và event vào cùng immutable state. Lỗi chèn trước commit giữ nguyên cả hai; sau commit, event ở trạng thái chờ gửi, không phải đã được giao cho broker.

Tạo file `OrderOutboxStateDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class OrderOutboxStateDemo {

    private record State(List<String> orders, List<String> pendingEvents) {
        State {
            orders = List.copyOf(orders);
            pendingEvents = List.copyOf(pendingEvents);
        }
    }

    private static final class OrderService {
        private State state = new State(List.of(), List.of());

        synchronized State snapshot() {
            return state;
        }

        synchronized void create(String orderId, boolean failBeforeCommit) {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("invalid orderId");
            }

            State old = state;
            if (old.orders().contains(orderId)) {
                throw new IllegalStateException("duplicate order");
            }

            List<String> nextOrders = new ArrayList<>(old.orders());
            nextOrders.add(orderId);

            List<String> nextEvents =
                    new ArrayList<>(old.pendingEvents());
            nextEvents.add("OrderCreated:" + orderId);

            State candidate = new State(nextOrders, nextEvents);

            if (failBeforeCommit) {
                throw new IllegalStateException("injected before commit");
            }

            state = candidate;
        }
    }

    public static void main(String[] args) {
        OrderService service = new OrderService();
        State before = service.snapshot();

        try {
            service.create("A", true);
        } catch (IllegalStateException ex) {
            System.out.println("failed: " + ex.getMessage());
        }

        System.out.println("unchanged: " + before.equals(service.snapshot()));

        service.create("A", false);
        System.out.println("orders: " + service.snapshot().orders());
        System.out.println("outbox: " + service.snapshot().pendingEvents());

        try {
            service.create("A", false);
        } catch (IllegalStateException ex) {
            System.out.println("duplicate: " + ex.getMessage());
        }
        System.out.println("still one order: "
                + service.snapshot().orders().size());
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 OrderOutboxStateDemo.java
java OrderOutboxStateDemo
```

Stdout:

```text
failed: injected before commit
unchanged: true
orders: [A]
outbox: [OrderCreated:A]
duplicate: duplicate order
still one order: 1
```

Trong chương trình:

- Trạng thái ban đầu không có order/event.
- Failure trước commit không publish `candidate`, vì thế order/event đều giữ nguyên.
- Lần tạo thành công đưa `A` và event `OrderCreated:A` vào **cùng snapshot**.
- Một lần tạo trùng bị từ chối trước commit, không nhân đôi order.
- Event còn trong `pendingEvents`, **chưa giả vờ đã gửi**.

**Hạn chế rất quan trọng:** đây là ví dụ minh họa ranh giới commit **trong một JVM và một object**; không có DB transaction, crash safety, nhiều node, worker gửi event, persistence hoặc acknowledgment. Production transactional outbox cần ghi order và outbox row **trong cùng giao dịch bền vững**, worker phát event theo cơ chế ít nhất một lần khi thích hợp, và consumer/delivery phải xử lý duplicate.

Không dùng `List<String>` in-memory này làm “outbox bảo đảm dữ liệu” cho nghiệp vụ tiền thật.

## 9. Nguyên tắc validate trước khi mutate có giới hạn

Đối với input không hợp lệ, **validate first** thường giúp state không đổi:

```java
void setQuantity(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity <= 0");
    }
    this.quantity = quantity;
}
```

Đây là snippet trong một class giả định; `quantity` là field. Với update chỉ một primitive và không có side effect nào sau đó, đây là cấu trúc đơn giản.

Nhưng nếu method có thêm:

```java
this.quantity = quantity;
notifyListeners(); // Có thể ném exception.
```

thì exception ở `notifyListeners` xảy ra **sau mutation**. Nếu API vẫn hứa strong guarantee, phải thiết kế lại ranh giới:

- Callback có thể được chuẩn bị/kiểm tra trước mà không side effect không?
- Có thể tách update và notification thành hai operation/hợp đồng riêng không?
- Có thể ghi durable event/outbox thay vì gọi callback trực tiếp dưới transaction không?
- Có thể rollback mutation và cả tác động callback đã xảy ra không? Nếu không, không nên hứa rollback toàn bộ.
- Caller có thể phân biệt “update thành công, notification chưa được giao” qua result/status không?

**Đặt validation trước mutation là cần thiết nhưng chưa đủ** cho method có nhiều bước có thể ném.

## 10. Hợp đồng method khi lỗi: throw, return hay trạng thái miền ứng dụng?

Một API có thể chọn cách báo lỗi:

**Throw exception** khi precondition sai, invariant bị vi phạm hoặc lỗi bất ngờ theo hợp đồng.

```java
void reserve(String orderId, int quantity);
```

Nếu dùng `IllegalStateException` khi thiếu hàng, cần tài liệu hóa: sau khi ném, tồn kho và reservation có giữ nguyên không? Caller có thể thử lại khi bổ sung hàng không?

**Trả một result type** khi “không thực hiện được” là kết quả thường gặp và caller cần phân biệt nhiều trường hợp có kiểm soát.

```java
sealed interface ReserveResult
        permits Reserved, Rejected, Pending {}

record Reserved(String reservationId) implements ReserveResult {}
record Rejected(String reasonCode) implements ReserveResult {}
record Pending(String operationId) implements ReserveResult {}
```

Đây là snippet minh họa dùng sealed interface/record hợp lệ về mặt cú pháp Java 17; cần đặt các declaration trong file hoặc class thích hợp. `Pending` biểu diễn trường hợp chưa hoàn tất/chưa chắc kết quả, không phải một exception được nuốt để biến thành thành công.

**Không biến mọi exception thành `true`/`false` hoặc `null`** nếu caller cần nguyên nhân, trạng thái giao dịch và hướng phục hồi. Một result type chỉ tốt khi semantics, invariant và các trạng thái trả về được định nghĩa rõ.

### Checked và unchecked không tự nói trạng thái đã rollback

`IOException`, `SQLException` và `RuntimeException` thuộc các nhóm khác nhau ở compile time, nhưng **không loại nào tự bảo đảm object không đổi**. Tài liệu contract cần chỉ ra điều gì xảy ra trên mỗi loại lỗi.

## 11. Chọn đúng ranh giới transaction hoặc unit of work

Nếu method sửa hai tài khoản:

```java
from.debit(amount);
to.credit(amount);
```

đây là đoạn minh họa nguy hiểm nếu `to.credit` có thể ném sau khi `from.debit` đã thành công. Nếu contract hứa một giao dịch nguyên tử, cần:

- Xác minh số dư/điều kiện trước khi commit.
- Dựng candidate cho **cả hai account**.
- Commit dưới một lock/transaction bao trùm đúng các đối tượng.
- Hoặc giao toàn bộ thao tác cho database transaction thực với isolation/constraints.
- Khi có ngoại tác mạng, sử dụng operation ID và giao thức phối hợp thích hợp.

Nếu domain cho phép tiến độ một phần, phải báo explicit trạng thái thay vì giả vờ transfer nguyên tử. Với luồng tiền thật, không chỉ dựa vào `synchronized` trên hai object Java: nhiều process/node/database transaction và sự cố mất response đều phải được xét.

### Đừng chỉ rollback field thứ nhất trong catch

Phản mẫu:

```java
try {
    from.debit(amount);
    to.credit(amount);
} catch (Exception ex) {
    from.credit(amount);
    throw ex;
}
```

Đây là snippet minh họa anti-pattern. Lệnh rollback cũng có thể ném hoặc tạo side effect mới; `to.credit` có thể đã thành công trước khi ném; đồng thời code có thể đang chạy cạnh tranh với thread khác. Cách này không tự trở thành transaction an toàn.

Với in-memory state nhỏ, staged immutable state là lựa chọn tốt. Với DB, transaction là boundary. Với nhiều hệ thống, có thể cần workflow/Saga/compensation và trạng thái trung gian rõ ràng.

## 12. Cleanup thuộc cùng hợp đồng trạng thái sau thất bại

Một API có thể **giữ nguyên dữ liệu nghiệp vụ** sau lỗi nhưng vẫn để rò rỉ connection, semaphore permit hoặc listener. Như vậy, lời hứa “state hợp lệ sau exception” chưa đủ nếu hợp đồng còn quy định lifecycle tài nguyên.

Khi một method acquire resource A rồi B, hãy ghi rõ: A đã được cấp thành công thì phải được giải phóng nếu bước B thất bại. Với resource do chính phạm vi sở hữu, dùng:

~~~java
try (Resource first = acquireFirst();
     Resource second = acquireSecond(first)) {
    performWork(first, second);
}
~~~

Đây là snippet minh họa, với `Resource extends AutoCloseable` và các factory tự định nghĩa. Nếu `acquireSecond` thất bại, Java cố đóng `first`. Nếu cả hai thành công, chúng được đóng **ngược thứ tự**. Trong test, đừng chỉ assert loại exception: hãy đo `closeCalls` và trạng thái object sau failure.

**Ownership phải chính xác:** không đóng stream mà API chỉ mượn từ caller; không shutdown cả executor dùng chung chỉ vì một job lỗi. Với `Semaphore.acquire()`, `Lock.lockInterruptibly()` hoặc một token đăng ký có thể thất bại trước khi acquire, chỉ release/unlock/unsubscribe khi đã sở hữu thực sự. Lỗi cleanup cũng không tự hoàn tác những dữ liệu đã commit.

Phần kế tiếp dùng fake resource để kiểm chứng rõ **lỗi khi acquire B, A vẫn được đóng**, thay vì phụ thuộc vào file hay connection thật.

## 13. Ví dụ Java 17 hoàn chỉnh: cleanup khi acquire thất bại

Ví dụ dùng một `AutoCloseable` mô phỏng resource, ghi thứ tự các bước vào danh sách. Tình huống thứ hai không mở được resource B, vì vậy A phải được đóng trước khi exception tới caller.

Tạo file `PartialAcquisitionDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class PartialAcquisitionDemo {

    private static final class Lease implements AutoCloseable {
        private final String name;
        private final List<String> events;

        Lease(String name, List<String> events) {
            this.name = name;
            this.events = events;
            events.add("open " + name);
        }

        @Override
        public void close() {
            events.add("close " + name);
        }
    }

    private static Lease acquireSecond(
            List<String> events, boolean fail) {
        if (fail) {
            throw new IllegalStateException("second unavailable");
        }
        return new Lease("B", events);
    }

    private static void execute(List<String> events, boolean failSecond) {
        try (Lease first = new Lease("A", events);
             Lease second = acquireSecond(events, failSecond)) {
            events.add("work");
        }
    }

    public static void main(String[] args) {
        List<String> failed = new ArrayList<>();
        try {
            execute(failed, true);
        } catch (IllegalStateException ex) {
            failed.add("caught " + ex.getMessage());
        }
        failed.forEach(System.out::println);

        System.out.println("---");

        List<String> success = new ArrayList<>();
        execute(success, false);
        success.forEach(System.out::println);
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 PartialAcquisitionDemo.java
java PartialAcquisitionDemo
```

Stdout:

```text
open A
close A
caught second unavailable
---
open A
open B
work
close B
close A
```

Quan sát:

- Lỗi `acquireSecond` xảy ra **trước** khi B được tạo; không có `close B`.
- Vì A được tạo thành công, try-with-resources đóng A khi thoát do exception.
- Với đường thành công, B đóng trước A do thứ tự ngược khai báo.
- `Lease.close()` trong demo không ném và chỉ ghi sự kiện. Resource thực có thể cần cleanup khác hoặc close failure, phải có test riêng.

Tránh làm cleanup phụ thuộc vào việc “sau khi catch rồi sẽ tự nhớ đóng”: đặt resource scope gần nơi acquire là cách bền vững hơn.

## 14. Cleanup lỗi kép: kiểm tra thêm bất biến sau thất bại

Nếu phần thân đã ném ngoại lệ A và `close()` lại ném B, `try-with-resources` giữ A là **primary**, B ở `A.getSuppressed()` khi suppression được bật. Đây là cơ chế bảo toàn thông tin lỗi, **không phải cơ chế rollback dữ liệu**.

Đối với API exception-safe, kết quả kiểm thử cần ghép **hai nhóm assertion**:

| Thông tin lỗi | Trạng thái sau lỗi |
| --- | --- |
| Cause / primary vẫn mô tả đúng thất bại của operation | Snapshot business data còn đúng invariant; nếu hứa strong guarantee thì không đổi |
| `getSuppressed()` giữ thông tin lỗi close | Resource sở hữu đã được *thử* close đúng cách, dù close có thể thất bại |
| Lỗi close-only được báo khi thân try thành công | Caller không nhầm kết quả trước close là thành công hoàn tất |
| Nếu cleanup/undo bị lỗi tiếp | Lifecycle có thể là `FAILED`/không thể tái sử dụng; không thông báo rollback đã thành công |

Ví dụ chương trình `PartialAcquisitionDemo` ở mục 13 chỉ ghi nhận close thành công; khi mở rộng fake để close ném exception, hãy assert primary/suppressed **và** state machine của resource. Các kịch bản ba resource và kiểm thử thứ tự suppressed chuyên sâu thuộc bài riêng về nhiều suppressed exceptions; ở đây trọng tâm là **hợp đồng hậu điều kiện của API**.

## 15. Phân biệt lỗi trước commit, trong commit và sau commit

Một failure có thể xảy ra ở ba giai đoạn khác nhau:

| Thời điểm | Ví dụ | Kết luận hợp lý |
| --- | --- | --- |
| **Trước commit** | Validation fail; candidate state không dựng được | Nếu prepare không side effect, state đã publish có thể giữ nguyên. |
| **Trong commit** | DB commit trả lỗi kết nối; driver không biết kết quả | Có thể là outcome unknown; cần kiểm tra contract và đối soát. |
| **Sau commit** | Gửi email/event hay log callback thất bại | Business state có thể đã commit; không tuyên bố rollback nếu không có cơ chế. |

Trên JVM in-memory, một phép gán field không ném checked exception và được JVM thực hiện theo semantics của nó; nhưng việc **chỉ có một phép gán** không giải quyết side effect bên ngoài, visibility hoặc race. API phải chia phase đúng ranh giới quan sát.

Một thiết kế tốt thường không cố catch bất cứ exception nào rồi gọi `rollback()` vô điều kiện. Nó ghi trạng thái đã commit, trạng thái cần retry/compensate và định danh operation để trả caller kết quả thật.

## 16. Không để callback làm hỏng tính nguyên tử của state

Giả sử method gọi observer trong khi state đang dở:

```java
state = new State(...);
listener.onChanged(state); // callback ngoài quyền kiểm soát
commitOtherPart();
```

Đây là snippet minh họa. Listener có thể ném hoặc reenter API; trong lúc đó những thành phần khác đã nhìn thấy một phần state mới. Đặc biệt không nên gọi callback không tin cậy khi đang giữ lock nếu có nguy cơ deadlock hoặc lộ trạng thái giữa chừng.

Hướng cải thiện:

1. Validate và dựng snapshot mới.
2. Commit toàn bộ state thuộc một invariant một cách có kiểm soát.
3. Ghi nhận event hoặc callback trong **giai đoạn sau commit** với semantics riêng.
4. Nếu callback fail, có policy retry/durable event hoặc trạng thái notification failed; không biến thành “state chưa đổi”.
5. Bảo đảm listener không có quyền mutate trực tiếp collection nội bộ.

Nếu cần notification **cùng transaction** với business update, dùng cơ chế outbox/transaction; một callback in-memory không thể thay thế transaction phân tán.

## 17. API có vòng đời: OPEN, FAILED, CLOSED

Không phải lỗi nào cũng cho phép object hoạt động như cũ. Nếu một connection/session bị phá đến mức không thể phục hồi an toàn, object có thể phải chuyển sang `FAILED` để từ chối thao tác tiếp theo.

```text
NEW → OPEN → CLOSED
        |
        +→ FAILED → CLOSED
```

Khi method thất bại, contract nên xác định:

- Lỗi validation thông thường: object vẫn `OPEN` và có thể dùng tiếp.
- Lỗi giao thức nghiêm trọng làm mất đồng bộ: object `FAILED` và các lệnh tiếp theo bị từ chối.
- Lỗi trong `close()`: object có thể ở `CLOSING`/`CLOSED_WITH_ERRORS` hoặc trạng thái khác được định nghĩa; không tự báo `CLOSED` sạch nếu resource chưa giải phóng.
- Lệnh `close()` gọi lại: có idempotent không, có ném không?
- Caller nên dùng `reset()`, tạo object mới, hay đóng bỏ?

Đừng viết API khiến state `ACTIVE` xuất hiện khi các resource cần thiết cho ACTIVE chưa tạo xong. Cũng đừng bắt mọi lỗi rồi lặng lẽ đặt `OPEN` dù invariant có thể đã bị phá.

Nếu object được chia sẻ, lifecycle transition phải đồng bộ với thread đang xử lý, không chỉ cập nhật enum thiếu memory visibility.

## 18. Khi method có partial progress được phép

Strong guarantee không phải lúc nào cũng rẻ hoặc khả thi. Một API batch có thể công khai **basic guarantee**:

```java
BatchResult importRecords(List<Record> records);
```

Đây là chữ ký minh họa, `BatchResult` và `Record` cần được định nghĩa. Hợp đồng có thể cho phép xử lý thành công N record, rồi dừng khi record tiếp theo lỗi. Khi đó:

- N record đã commit phải nhất quán, không trùng.
- Vị trí resume/checkpoint phải chính xác.
- Record lỗi không được để lại nửa cấu trúc sai.
- Tài nguyên owned phải cleanup.
- Caller nhận số lượng thành công, danh sách lỗi hoặc trạng thái cho phép phục hồi.
- Retry/resume không lặp side effect của các record đã ghi.

Nếu contract là “atomic batch”, giữ lại 7/10 record sau exception lại **vi phạm** hợp đồng. Hãy chọn guarantee theo nhu cầu domain, tài liệu hóa và kiểm thử cụ thể.

Một result type báo “PARTIAL_SUCCESS” có thể rõ hơn ném một exception chung rồi buộc caller tự suy đoán bao nhiêu item đã được ghi.

## 19. Cách dùng try/catch cho rollback có giới hạn

Một số code thực sự cần thao tác bù khi failed:

```java
boolean registered = false;
try {
    registerListener(listener);
    registered = true;
    activate();
} catch (RuntimeException failure) {
    if (registered) {
        try {
            unregisterListener(listener);
        } catch (RuntimeException cleanupFailure) {
            failure.addSuppressed(cleanupFailure);
        }
    }
    throw failure;
}
```

Đây là snippet minh họa; `registerListener`, `activate`, `unregisterListener`, `listener` chưa được định nghĩa. Nó cho thấy **chỉ cleanup cái đã acquire thành công**, và không để lỗi cleanup che lỗi chính.

Nhưng có hai vấn đề API phải tự xử lý:

- `registerListener` có thể đã đăng ký thành công rồi **ném sau khi side effect xảy ra**, nên `registered=false` không chắc đồng nghĩa không cần cleanup. Tốt nhất registration trả một handle có contract rõ, hoặc thao tác có idempotency/trạng thái đối soát.
- `activate` có thể tác động ngoài đăng ký listener. Cleanup listener không rollback side effect khác, vì vậy không được vội hứa strong guarantee toàn workflow.

Tốt hơn, thiết kế các bước acquire/registration để chúng hoặc trả handle rõ ràng, hoặc có cơ chế an toàn xác định nếu lỗi xảy ra giữa chừng.

## 20. Thiết kế contract lỗi dễ hiểu cho caller

Javadoc hoặc mô tả API nên nêu:

**Precondition:** input và lifecycle yêu cầu gì?

**Failure types:** lỗi validation, thiếu tài nguyên, lỗi dependency, cancellation và illegal state được biểu diễn như thế nào?

**State guarantee:** phần nào không đổi khi thất bại? Có partial commit không?

**Resource ownership:** API tự đóng cái gì, cái gì caller phải đóng?

**Retry semantics:** lỗi nào có thể retry, thao tác có idempotent không, có operation ID không?

**Concurrency:** method thread-safe không, snapshot nhất quán đến mức nào?

**Unknown outcome:** nếu mất response lúc commit, caller tra cứu bằng cách nào?

Ví dụ Javadoc minh họa:

```java
/**
 * Giữ chỗ số lượng hàng cho một order.
 *
 * @throws IllegalArgumentException nếu id blank hoặc quantity không dương
 * @throws IllegalStateException nếu không đủ hàng
 *
 * Exception safety: nếu validation hoặc kiểm tra tồn kho thất bại,
 * trạng thái inventory giữ nguyên. Phương thức thread-safe trong
 * phạm vi một Inventory instance.
 */
void reserve(String orderId, int quantity);
```

Đây là chữ ký/tài liệu minh họa, chưa định nghĩa body. `@throws` mô tả điều kiện xảy ra lỗi; phần “Exception safety” mô tả hậu quả đối với object. Hai phần bổ trợ nhau.

Không dùng `throws Exception` rộng chỉ vì API có nhiều bước. Kiểu lỗi rõ có ích, nhưng ngay cả nhiều kiểu exception cụ thể cũng không thay cho mô tả state guarantee.

## 21. Kiểm thử: sau exception state còn hợp lệ không?

Một bộ test chỉ có:

```java
assertThrows(IllegalStateException.class, () -> inventory.reserve("x", 99));
```

là chưa đủ. Đây là snippet JUnit 5 cần dependency ngoài JDK. Nó chứng minh một exception thuộc họ `IllegalStateException` được ném, không chứng minh state còn đúng.

Một test tốt nên:

1. Chuẩn bị object ở state hợp lệ.
2. Lấy snapshot độc lập trước lời gọi.
3. Gây một lỗi xác định.
4. Assert exception type/code/cause khi contract yêu cầu.
5. Assert snapshot sau bằng trước cho strong guarantee, hoặc thỏa basic guarantee đã mô tả.
6. Assert invariant của object.
7. Assert không có side effect ngoài phạm vi hoặc trạng thái unknown đúng như hợp đồng.
8. Assert resource đã cleanup.
9. Thử một thao tác **thành công sau khi lỗi** nếu object được hứa vẫn usable.
10. Với concurrency, kiểm tra trạng thái và thứ tự commit dưới interleaving được kiểm soát.

### Snapshot không được trỏ vào collection mutable

Sai:

```java
List<Item> before = inventory.items();
```

Nếu `items()` trả list mutable nội bộ, `before` và `inventory.items()` có thể là cùng object; mutation sau thất bại làm snapshot thay đổi theo, test false pass.

Đúng hơn:

```java
List<ItemView> before = snapshotItems(inventory);
```

Đây là snippet minh họa, với `ItemView` bất biến và `snapshotItems` tạo bản sao sâu/semantic phù hợp. `List.copyOf` chỉ tạo shallow copy; nếu phần tử còn mutable, cần bản snapshot an toàn hơn.

## 22. Kiểm thử lỗi ở nhiều mốc

Đừng chỉ test validation failure. Một API gồm acquire, transform, commit và publish có thể lỗi ở bất kỳ bước nào:

| Điểm phát lỗi | Kiểm tra |
| --- | --- |
| Đầu vào null/blank/sai khoảng | Không mutate state, không gọi side effect. |
| Không thỏa invariant nghiệp vụ | Trạng thái giữ nguyên theo contract. |
| Acquire resource A thành công, B lỗi | A được cleanup, B không bị close nếu chưa tồn tại. |
| Tạo candidate collection lỗi | State đang publish không đổi. |
| Trước commit | Candidate không bị publish. |
| Trong DB transaction | Rollback/UNKNOWN theo hợp đồng DB, không đoán. |
| Sau commit khi gửi event lỗi | State đã commit, event pending hoặc failure được ghi có nghĩa. |
| Close cũng lỗi | Primary/cause/suppressed và resource state được bảo toàn. |
| Caller bị interrupt khi đang chờ | Không nhầm với worker thất bại; cleanup thuộc đúng owner. |
| Duplicate operation ID | Không tạo side effect trùng khi domain đòi idempotency. |

Có thể dùng fake adapter có nút “fail at step N” hoặc JUnit mock có hành vi xác định. Nhưng unit test không chứng minh transaction của database thật; cần integration test với hệ thống thật/giả lập phù hợp.

## 23. Kiểm thử lỗi đã làm object hỏng ngầm

Một đối tượng có thể giữ nguyên những field nhìn thấy nhưng bị kẹt vì:

- Cờ `busy=true` không được reset.
- Semaphore permit/lock chưa release.
- Listener còn đăng ký nên nhận callback không mong muốn.
- Stream đã đóng nhưng field vẫn báo `OPEN`.
- Cache version và DB version không đồng nhất.
- Task async vẫn ghi state sau khi API báo canceled.
- Một thread bị interrupt nhưng vòng lặp vẫn tiếp tục tác động.

Ngoài snapshot, nên thực hiện **operation hợp lệ ngay sau failure**. Nếu contract nói object vẫn hoạt động, method tiếp theo phải không bị kẹt do resource/lifecycle bị bỏ sót. Nếu contract nói phải chuyển `FAILED`, lời gọi tiếp theo cần báo rõ `IllegalStateException`/domain error chứ không sử dụng state có thể không an toàn.

Với cleanup async, phải đợi acknowledgement/latch theo contract trước khi assert “đã đóng”; `Future.isCancelled()` không nhất thiết đồng nghĩa `finally` của worker đã hoàn tất.

## 24. Concurrency: exception safety khác thread safety

Đoạn:

```java
State old = state;
State next = compute(old);
state = next;
```

có thể đáp ứng strong guarantee với một thread, nhưng **hai thread cùng đọc `old` và commit riêng có thể mất cập nhật**. Vì vậy một API được chia sẻ phải xét:

- Atomic read-modify-write bằng lock/CAS/transaction.
- Visibility: `volatile` hoặc synchronization cho publication.
- Invariant gồm nhiều field cần được quan sát nhất quán.
- Callback không chạy trên state nửa commit.
- Nếu CAS thất bại, thử tính candidate mới không được lặp side effect vô ý.
- Cancellation xảy ra giữa prepare và commit phải có chính sách rõ.

Nếu dùng CAS loop, `compute(old)` phải không có side effect không idempotent, vì CAS có thể fail và buộc tính lại. Đừng gọi thanh toán, gửi email hoặc tăng counter bên ngoài trước mỗi lần CAS retry.

**Một lần gán reference không tự làm toàn bộ workflow thread-safe.** Nó chỉ là một thành phần kỹ thuật trong thiết kế đồng bộ.

## 25. Exception safety và cancellation/interruption

Một operation có thể nhận `InterruptedException` ở bước blocking. Cách xử lý tùy ranh giới:

- Nếu API có thể truyền `InterruptedException` lên caller, truyền tín hiệu để lifecycle owner quyết định.
- Nếu chuyển sang unchecked exception và dừng, thường khôi phục interrupt flag bằng `Thread.currentThread().interrupt()`.
- Đặt cleanup owned resources trong `finally`/`try-with-resources`.
- Không release lock/permit khi chưa acquire.
- Nếu cancel xảy ra sau side effect, trạng thái chưa chắc rollback.
- Nếu cleanup cần thao tác blocking, cân nhắc khi nào phục hồi flag để cleanup không tự bị ngắt lập tức; đặt deadline hợp lý.

Ví dụ:

```java
try (OwnedHandle handle = acquireOwnedHandle()) {
    performInterruptibleWork(handle);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new OperationInterruptedException("interrupted", ex);
}
```

Đây là snippet minh họa với các kiểu/method do ứng dụng cung cấp. Đặt catch **bên ngoài** try-with-resources nghĩa là handle được đóng trước khi catch khôi phục flag, có thể hữu ích khi cleanup nhạy với interruption. Nếu `close` có checked exception khác, chữ ký/catch thực tế phải xử lý theo đúng loại đó.

Không coi interrupt như lỗi tạm thời để retry vô hạn; nó thường là yêu cầu dừng.

## 26. Những lỗi thiết kế API thường gặp

**1. Ném đúng exception nhưng mutate state trước khi kiểm tra.** Test type vẫn pass trong khi invariant sai. Validate trước và chuẩn bị candidate trước commit.

**2. Trả collection mutable nội bộ ra ngoài.** Caller có thể tự thay đổi state bỏ qua invariant/validation. Trả immutable view hoặc snapshot theo contract.

**3. Chỉ copy reference để snapshot.** Dữ liệu lồng mutable đổi theo bản gốc, tạo test false pass. Dùng immutable value objects hoặc deep snapshot.

**4. Tưởng một gán field là transaction DB.** Nó không rollback filesystem, queue, external API hay state của process khác.

**5. Catch mọi exception rồi rollback thủ công vô điều kiện.** Rollback cũng có thể lỗi và side effect có thể đã commit; cần transaction/compensation/status rõ.

**6. Xem lỗi ở after-commit callback là bằng chứng chưa commit.** Có thể tạo duplicate khi caller retry. Phân biệt business commit và notification.

**7. Đóng shared resource khi một request lỗi.** Ownership sai gây gián đoạn request khác. Chỉ đóng handle do scope sở hữu.

**8. Release permit hoặc unlock chưa acquire.** Interruption có thể đến trước lúc acquire thành công; kiểm tra đúng điểm sở hữu.

**9. Đặt tất cả exception thành một thông điệp “failed”.** Làm mất cause và trạng thái rollback/unknown cần thiết.

**10. Nuốt cleanup exception.** Có thể mất dữ liệu khi flush/close; giữ cause/suppressed và trạng thái lỗi.

**11. Hứa strong guarantee nhưng cho phép partial progress không được báo.** Phải thống nhất contract và test; nếu basic, expose checkpoint.

**12. Dùng `synchronized` ở một method nhưng đọc state từ method khác không đồng bộ.** Dễ có visibility/race. Bảo vệ toàn bộ contract đọc/ghi.

**13. Gọi observer trong lúc object ở state tạm.** Callback có thể ném hoặc reenter; publish state nhất quán trước và chọn semantics notification.

**14. Chỉ kiểm tra exception class bằng `assertThrows`.** Không kiểm tra state, invariant, cleanup và khả năng object còn usable.

**15. Retry toàn operation sau timeout dù side effect có thể đã xảy ra.** Cần idempotency/operation ID và cơ chế đối soát.

## 27. Bài tập thực hành

**Bài 1 – Kho hàng:** `reserve(7)` từ tồn 5 ném lỗi nhưng thêm một reservation. Hãy mô tả invariant bị vi phạm và thay đổi thứ tự xử lý.

*Gợi ý:* kiểm tra quantity/tồn và duplicate ID trước; chuẩn bị danh sách mới; commit một lần. Test cả state và exception.

**Bài 2 – Account:** `transfer(30)` trừ nguồn rồi lỗi khi cộng đích. Nếu contract hứa atomic, tại sao `catch { source += 30; }` chưa đủ?

*Gợi ý:* rollback cũng có thể thất bại, đích có thể đã cộng trước khi ném, và concurrency có thể xen vào. Cần ranh giới atomic hơn.

**Bài 3 – Listener:** `register` A thành công, B thất bại; A vẫn còn subscribed. Nên cleanup ở đâu?

*Gợi ý:* dùng registration handle thuộc scope hoặc `finally` chỉ hủy registration đã acquire. Test lần khởi tạo lỗi và callback sau cleanup.

**Bài 4 – DB + email:** DB đã commit nhưng gửi email lỗi. Có được khẳng định tạo đơn hàng thất bại hoàn toàn không?

*Gợi ý:* không nếu DB đã commit; dùng pending event/outbox hoặc báo trạng thái thích hợp.

**Bài 5 – Concurrency:** hai thread cùng đọc tồn kho 5, cả hai muốn giữ 4, mỗi thread tự tính `next=1` rồi gán. Invariant `available >= 0` có thể vẫn đúng nhưng đã xảy ra lỗi gì?

*Gợi ý:* lost update/đặt quá số lượng thực tế. Cần đồng bộ/CAS/transaction và invariant bao gồm tổng reservation.

**Bài 6 – Cleanup:** thân `try` ném `IllegalStateException`, `close` ném `IOException`. Test nên kiểm tra gì?

*Gợi ý:* primary exception, suppressed close exception, tài nguyên đã cố đóng, trạng thái cleanup theo contract.

**Bài 7 – Interruption:** một luồng bị ngắt trước khi `Semaphore.acquire()` nhận permit. Tại sao `finally { semaphore.release(); }` luôn chạy là sai?

*Gợi ý:* chưa sở hữu permit nên release làm sai bộ đếm; thiết kế scope theo điểm acquire thành công.

## 28. Checklist trước khi công bố một API exception-safe

- [ ] Mọi public method có precondition, postcondition và invariant rõ.
- [ ] Đã chọn strong/basic/no-throw hoặc mô tả guarantee riêng theo thao tác.
- [ ] Lỗi validation không mutate state đã publish.
- [ ] Candidate dữ liệu được chuẩn bị độc lập, không vô tình sửa collection đang chia sẻ.
- [ ] Commit nằm ở một ranh giới có thể xác định/kiểm soát.
- [ ] Các thao tác có thể lỗi sau commit đã có semantics riêng, không hứa rollback giả.
- [ ] DB/outbox/event/network có transaction, idempotency hoặc đối soát thích hợp.
- [ ] Resource ownership rõ: acquire thành công mới release/close.
- [ ] try-with-resources/finally bao phủ đường lỗi và cleanup failure được xét.
- [ ] Loại exception, cause và trạng thái UNKNOWN/PENDING được công bố đủ.
- [ ] API không lộ mutable state để caller phá invariant bên ngoài.
- [ ] Concurrency/read-write visibility được bảo vệ theo hợp đồng.
- [ ] Có test fault injection trước commit, trong cleanup và after-commit.
- [ ] Có snapshot state độc lập và assertion invariant sau thất bại.
- [ ] Có test operation thành công sau exception hoặc chuyển đúng FAILED lifecycle.
- [ ] Có integration test cho transaction/side effect ngoài JVM khi cần.
- [ ] Không retry bừa khi response mất mà kết quả server có thể đã commit.

## 29. Tổng kết

Thiết kế API giữ trạng thái hợp lệ khi có lỗi đòi hỏi **nêu rõ trạng thái nào được phép sau exception**, không chỉ quyết định sẽ ném exception gì. Với in-memory state, mô hình **validate → prepare → commit** cùng immutable value objects và synchronization thích hợp giúp giảm mutation một phần; với resource, cần ownership và cleanup có cấu trúc; với DB/network/event, cần transaction, outbox, idempotency hoặc đối soát theo ranh giới thực tế.

Một API đáng tin có thể nói chính xác: **lỗi này xảy ra trước commit nên state không đổi; lỗi kia xảy ra sau commit nên business state vẫn thành công nhưng notification còn pending; lỗi nghiêm trọng này khiến object chuyển FAILED và không còn dùng tiếp được.** Khi những hợp đồng ấy được thể hiện trong thiết kế và test, exception không còn là dấu hiệu mơ hồ mà trở thành một phần kiểm soát được của tính đúng đắn hệ thống.