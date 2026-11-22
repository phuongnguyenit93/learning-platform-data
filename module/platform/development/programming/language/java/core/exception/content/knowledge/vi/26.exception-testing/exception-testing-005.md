# Kiểm tra trạng thái đối tượng sau khi phương thức thất bại

Một bài kiểm thử exception không nên chỉ hỏi **“phương thức đã ném đúng exception chưa?”**. Câu hỏi quan trọng không kém là: **“sau khi ném, đối tượng còn ở trạng thái nào?”** Nếu phương thức đã trừ số dư, thêm một phần tử, đổi trạng thái đơn hàng hoặc giữ tài nguyên rồi mới phát hiện lỗi, caller có thể nhận exception đúng loại trong khi đối tượng đã bị thay đổi một phần và không còn hợp lệ.

Ví dụ: `reserve(10)` ném `InsufficientStockException` nhưng kho đã bị trừ 10; `transfer()` ném `IOException` khi gửi thông báo nhưng số tiền ở tài khoản nguồn đã bị trừ; `registerListener()` ném giữa chừng nhưng listener vẫn ở trong danh sách đăng ký. Những lỗi này **không được phát hiện** nếu test chỉ dùng `assertThrows`.

Chủ đề này thuộc **Kiểm thử** trong Java Core – Exception. Mục tiêu là biết cách định nghĩa bảo đảm an toàn khi có exception, chụp trạng thái trước/sau, kiểm tra invariant và side effect, mô phỏng lỗi ở các mốc thực thi, và viết test Java 17 tin cậy.

## 1. Exception đúng loại chưa bảo đảm object đúng trạng thái

Đoạn code sau chỉ **minh họa anti-pattern**, chưa phải chương trình độc lập:

```java
class Inventory {
    private int stock = 5;

    void reserve(int quantity) {
        stock -= quantity;  // Đổi trạng thái trước.
        if (stock < 0) {
            throw new IllegalStateException("not enough stock");
        }
    }
}
```

Nếu caller gọi `reserve(10)`, phương thức ném `IllegalStateException` như mong đợi, nhưng `stock` đã thành `-5`. Một test chỉ kiểm tra exception sẽ **PASS dù đối tượng sai**.

```java
assertThrows(IllegalStateException.class,
        () -> inventory.reserve(10)); // Chưa đủ.
```

Đây là snippet dùng JUnit 5, cần dự án đã cài thư viện JUnit và biến `inventory`. Sau khi ném, test còn phải kiểm tra stock, danh sách giữ chỗ, các cờ trạng thái và tài nguyên liên quan theo hợp đồng.

Một test đầy đủ về logic có dạng:

```text
Given: trạng thái ban đầu hợp lệ S0
When:  gọi phương thức với lỗi được chủ động kích hoạt
Then:  exception đúng loại/nguyên nhân
And:   trạng thái sau lỗi thỏa mức bảo đảm đã công bố
And:   các invariant vẫn đúng
And:   tài nguyên và side effect không rò rỉ
```

Không phải phương thức nào cũng phải giữ nguyên trạng thái sau mọi lỗi. Điều cần kiểm tra là **mức bảo đảm mà API hứa**: giữ nguyên hoàn toàn, giữ trạng thái hợp lệ nhưng có thay đổi một phần, hay chỉ cleanup một số tài nguyên.

## 2. Ba mức bảo đảm an toàn khi có exception

Một cách phân loại hữu ích là các mức *exception safety guarantee*. Chúng mô tả **trạng thái quan sát được sau thất bại**, không chỉ loại exception được ném.

| Mức bảo đảm | Điều được bảo đảm khi lỗi | Ví dụ |
| --- | --- | --- |
| **No-throw guarantee** | Thao tác theo contract không ném exception, thường là cleanup rất đơn giản; cần xác định rõ phạm vi bảo đảm | `close()` của một handle in-memory được thiết kế không ném. |
| **Strong exception guarantee** | Nếu thao tác thất bại thì trạng thái quan sát được không thay đổi so với trước thao tác; “commit hoặc không đổi” | Tạo state mới rồi chỉ gán sau khi mọi bước có thể lỗi thành công. |
| **Basic exception guarantee** | Dù thất bại, các invariant của đối tượng vẫn đúng và không rò rỉ tài nguyên, nhưng có thể đã thay đổi một phần được phép | Import xử lý thành công 7 bản ghi rồi lỗi ở bản ghi thứ 8; 7 bản ghi vẫn có hiệu lực theo contract. |

Các thuật ngữ này hữu ích để thiết kế/test Java, nhưng **không phải ba annotation hay ba loại exception chuẩn trong ngôn ngữ Java**. API phải tự công bố mức bảo đảm thích hợp.

### Strong guarantee có phạm vi

“Không đổi” phải được định nghĩa theo **trạng thái quan sát được qua contract**. Một method có thể tăng internal telemetry counter khi thất bại mà không làm thay đổi state nghiệp vụ, nhưng nếu counter là một phần của API quan sát được thì test phải xét nó. Tương tự, cache, listener, file tạm, event và database có thể nằm ngoài field của object nhưng vẫn là side effect quan trọng.

Không nên hứa “mọi thứ rollback” nếu API chỉ bảo đảm object in-memory. Với DB, network và bên thứ ba, việc hoàn tác có ranh giới giao dịch/đối soát riêng.

### Basic guarantee vẫn phải bảo toàn invariant

Basic không có nghĩa được để object bị hỏng tùy ý. Nếu kho không cho phép tồn âm, `stock >= 0` phải đúng **ngay cả sau lỗi**, dù một phần các item trước đó đã được giữ chỗ thành công. Không được gọi “partial progress” để hợp thức hóa trạng thái bất khả thi.

### No-throw không phải miễn kiểm thử

Một method cleanup được thiết kế không ném vẫn cần test idempotency, thay đổi state, listener removal, release permit và ứng xử khi gọi hai lần. Không tự tuyên bố mọi `AutoCloseable.close()` đều no-throw: `AutoCloseable.close()` có thể khai báo `throws Exception`, và implementation có thể thất bại.

## 3. Định nghĩa invariant trước khi viết test

*Invariant* là điều kiện phải đúng ở các điểm quan sát trạng thái hợp lệ của object, đặc biệt sau khi constructor hoặc một method public hoàn thành — thành công hoặc thất bại, tùy contract.

Ví dụ đối tượng giỏ hàng:

- `availableStock >= 0`.
- `reservedQuantity >= 0`.
- `reservedQuantity <= initialStock` trong phạm vi tồn kho giả định không replenishment.
- Tổng số lượng phân bổ nhất quán với số còn lại.
- Không có record giữ chỗ mồ côi khi thao tác được bảo đảm atomic.
- Không còn tài nguyên mở bị bỏ quên nếu method kết thúc và phạm vi sở hữu đã kết thúc.

Một invariant phải có **nghĩa nghiệp vụ rõ ràng**. Nếu hệ thống cho phép tồn âm để biểu diễn backorder, test `stock >= 0` lại là sai contract. Tránh đưa implementation detail không được bảo đảm vào test và làm test vỡ khi refactor vô hại.

Khi định nghĩa state để so sánh, không chỉ nhìn một trường như `status`. Một trạng thái có thể sai ở collection, balance, version, resource handle, cache, subscription hoặc external side effect dù enum `status` vẫn như cũ.

## 4. Đừng chỉ dùng assertThrows

Trong JUnit 5, `assertThrows` kiểm tra rằng đoạn code ném một exception thuộc kiểu yêu cầu hoặc subtype. Nó **không kiểm tra** trạng thái object:

```java
IllegalStateException thrown =
        assertThrows(IllegalStateException.class,
                () -> inventory.reserve(10));

assertEquals("not enough stock", thrown.getMessage());
assertEquals(5, inventory.availableStock());
assertEquals(List.of(), inventory.reservations());
```

Đây là **snippet JUnit 5** yêu cầu import/static import JUnit, class `Inventory` và các method theo API thực; không thể chạy chỉ bằng `javac` trần. Kiểm tra message hữu ích khi message là contract; nếu message là text chẩn đoán có thể đổi, thường nên kiểm tra loại, mã lỗi và cause ổn định thay vì khóa test vào đúng câu chữ.

Các assertion sau exception cần kiểm tra:

1. **Loại lỗi:** checked/unchecked, subtype, mã domain, cause.
2. **State giữ nguyên hay thay đổi phần nào:** theo mức bảo đảm.
3. **Invariant:** tính hợp lệ của mọi field/quan hệ quan trọng.
4. **Side effect:** persistence, event, email, queue, file, log nếu contract yêu cầu.
5. **Resource lifecycle:** đóng handle, trả permit, unlock, hủy registration.
6. **Khả năng dùng tiếp:** object có thể tiếp tục hoạt động hợp lệ sau lỗi không?
7. **Concurrency:** trạng thái có nhất quán với thread khác theo contract không?

**Một test đúng exception nhưng sai trạng thái phải FAIL.** Đó là giá trị chính của bài học.

## 5. Snapshot trước/sau: phép so sánh rõ ràng nhất

Để kiểm tra strong guarantee, nên chụp một **snapshot độc lập** của trạng thái quan sát được trước lời gọi, rồi so sánh với snapshot sau khi exception đã được bắt.

Mẫu tư duy:

```java
State before = object.snapshot();

assertThrows(ExpectedException.class,
        () -> object.perform(invalidInput));

State after = object.snapshot();
assertEquals(before, after);
```

Đây là snippet minh họa dùng JUnit, với `State` và `ExpectedException` của ứng dụng. Snapshot phải phản ánh đầy đủ phần trạng thái contract yêu cầu; một snapshot chỉ gồm `status` chưa chắc đủ.

### Snapshot phải thực sự độc lập

Nếu snapshot giữ reference tới một `ArrayList` mutable của object, thay đổi sau đó cũng có thể làm snapshot “thay đổi theo”, khiến so sánh trước/sau **false pass**.

Ví dụ sai:

```java
List<String> before = inventory.getReservations();
inventory.reserve(...);
assertEquals(before, inventory.getReservations());
```

Nếu `getReservations()` trả chính list nội bộ, `before` và giá trị sau là **cùng một object**; cả hai cùng thấy mutation. Cách sửa: copy:

```java
List<String> before = List.copyOf(inventory.getReservations());
```

`List.copyOf` tạo danh sách không cho chỉnh sửa; nhưng đây chỉ là **shallow copy**: nếu phần tử là object mutable, việc sửa field của phần tử vẫn xuất hiện trong snapshot. Với object graph có nested mutable state, cần **deep snapshot** theo contract, sử dụng DTO/record bất biến hoặc serialize/copy có kiểm soát.

Lưu ý `List.copyOf` không nhận phần tử `null`. Nếu domain cho phép null, chọn representation/copy phù hợp, đừng vô tình làm test lỗi ngay lúc snapshot.

## 6. Ví dụ Java 17 hoàn chỉnh: phát hiện state bị hỏng và sửa bằng staged commit

Ví dụ sau có hai cách cập nhật cùng một kiểu `Inventory`:

- `reserveUnsafe` đổi state trước rồi mới kiểm tra điều kiện tồn kho.
- `reserveSafe` xác minh trước, tạo candidate state **trong biến local**, sau đó commit bằng **một lần gán reference**; nếu validation hoặc việc dựng candidate thất bại trước commit thì state cũ được giữ.

Tạo file `InventoryExceptionStateDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class InventoryExceptionStateDemo {

    private record State(int available, List<String> reservations) {
        State {
            reservations = List.copyOf(reservations);
        }
    }

    private static final class Inventory {
        private State state = new State(5, List.of());

        State snapshot() {
            return state;
        }

        void reserveUnsafe(String item, int quantity) {
            Objects.requireNonNull(item, "item");
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity <= 0");
            }

            State old = state;
            List<String> next = new ArrayList<>(old.reservations());
            next.add(item + ":" + quantity);

            // Sai: commit trước khi kiểm tra điều kiện thất bại.
            state = new State(old.available() - quantity, next);

            if (state.available() < 0) {
                throw new IllegalStateException("insufficient stock");
            }
        }

        void reserveSafe(String item, int quantity) {
            Objects.requireNonNull(item, "item");
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity <= 0");
            }

            State old = state;
            if (quantity > old.available()) {
                throw new IllegalStateException("insufficient stock");
            }

            List<String> next = new ArrayList<>(old.reservations());
            next.add(item + ":" + quantity);
            State candidate =
                    new State(old.available() - quantity, next);

            // Commit sau khi tất cả validation/preparation thành công.
            state = candidate;
        }
    }

    public static void main(String[] args) {
        Inventory unsafe = new Inventory();
        State beforeUnsafe = unsafe.snapshot();

        try {
            unsafe.reserveUnsafe("book", 7);
        } catch (IllegalStateException ex) {
            System.out.println("unsafe exception: " + ex.getMessage());
        }
        System.out.println("unsafe unchanged: "
                + beforeUnsafe.equals(unsafe.snapshot()));
        System.out.println("unsafe state: " + unsafe.snapshot());

        Inventory safe = new Inventory();
        State beforeSafe = safe.snapshot();

        try {
            safe.reserveSafe("book", 7);
        } catch (IllegalStateException ex) {
            System.out.println("safe exception: " + ex.getMessage());
        }
        System.out.println("safe unchanged: "
                + beforeSafe.equals(safe.snapshot()));
        System.out.println("safe state: " + safe.snapshot());

        safe.reserveSafe("book", 2);
        System.out.println("safe success: " + safe.snapshot());
    }
}
```

Chạy với Java 17+:

```bash
javac -encoding UTF-8 InventoryExceptionStateDemo.java
java InventoryExceptionStateDemo
```

Stdout:

```text
unsafe exception: insufficient stock
unsafe unchanged: false
unsafe state: State[available=-2, reservations=[book:7]]
safe exception: insufficient stock
safe unchanged: true
safe state: State[available=5, reservations=[]]
safe success: State[available=3, reservations=[book:2]]
```

Phân tích:

1. `beforeUnsafe` và `beforeSafe` là các `record State` bất biến đối với các phần tử `String` của ví dụ; list được copy ở constructor. Do đó snapshot trước không biến đổi theo state hiện tại.
2. `reserveUnsafe("book", 7)` đã gán state mới với `available=-2` và reservation `book:7` trước khi ném. Exception đúng nhưng invariant **tồn không âm** sai.
3. `reserveSafe("book", 7)` kiểm tra lỗi **trước mọi commit**. Khi ném, `state` vẫn tham chiếu tới record trước đó; `equals` trả `true`.
4. Gọi `reserveSafe("book", 2)` thành công tạo `State[available=3, reservations=[book:2]]`.
5. Phương thức an toàn chuẩn bị state mới trước gán. Đây là cách đạt strong guarantee **ở phạm vi state in-memory của ví dụ, khi một thread thực thi độc quyền**.

**Giới hạn quan trọng:** `Inventory` không có synchronization, vì thế **không thread-safe**; hai thread cùng đọc một `State` và ghi đè nhau có thể gây lost update. Bảo đảm exception safety không thay thế thread safety. `List.copyOf` là shallow copy; ở ví dụ các phần tử là `String` bất biến. Với DB/network, cần transaction hoặc idempotency/đối soát riêng chứ không thể chỉ gán một field Java để rollback side effect ngoài tiến trình.

## 7. Cách test mạnh hơn: tự viết assertion Java 17, không cần JUnit

Để người học thấy rõ test phải kiểm tra cả exception lẫn state, ví dụ sau **chạy độc lập bằng JDK** và dùng `AssertionError` do code chủ động tạo thay vì phụ thuộc cờ `-ea`.

Tạo file `ExceptionStateAssertionsDemo.java`:

```java
import java.util.List;
import java.util.Objects;

public class ExceptionStateAssertionsDemo {

    private static final class Account {
        private int balance = 100;
        private List<String> history = List.of();

        int balance() {
            return balance;
        }

        List<String> history() {
            return history;
        }

        void withdraw(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            if (amount > balance) {
                throw new IllegalStateException("insufficient funds");
            }

            List<String> nextHistory =
                    new java.util.ArrayList<>(history);
            nextHistory.add("withdraw:" + amount);

            // Mọi bước có thể phát hiện lỗi đã hoàn tất.
            history = List.copyOf(nextHistory);
            balance -= amount;
        }
    }

    private static <T extends Throwable> T expectThrows(
            Class<T> type, Runnable action) {
        try {
            action.run();
        } catch (Throwable error) {
            if (type.isInstance(error)) {
                return type.cast(error);
            }
            throw new AssertionError("wrong exception type", error);
        }
        throw new AssertionError("expected " + type.getSimpleName());
    }

    private static void check(boolean condition, String explanation) {
        if (!condition) {
            throw new AssertionError(explanation);
        }
    }

    public static void main(String[] args) {
        Account account = new Account();
        int balanceBefore = account.balance();
        List<String> historyBefore = List.copyOf(account.history());

        IllegalStateException ex = expectThrows(
                IllegalStateException.class,
                () -> account.withdraw(120));

        check(Objects.equals(ex.getMessage(), "insufficient funds"),
                "wrong message");
        check(account.balance() == balanceBefore,
                "balance changed after failure");
        check(account.history().equals(historyBefore),
                "history changed after failure");
        check(account.balance() >= 0, "negative balance");

        System.out.println("exception checked");
        System.out.println("state unchanged: true");
        System.out.println("invariants checked");

        account.withdraw(40);
        check(account.balance() == 60, "success balance wrong");
        check(account.history().equals(List.of("withdraw:40")),
                "success history wrong");
        System.out.println("success after failure: " + account.balance());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 ExceptionStateAssertionsDemo.java
java ExceptionStateAssertionsDemo
```

Stdout:

```text
exception checked
state unchanged: true
invariants checked
success after failure: 60
```

Điểm đáng học là kiểm tra **khả năng sử dụng tiếp** sau một lần thất bại. `withdraw(120)` phải bị từ chối và giữ state; sau đó `withdraw(40)` phải vẫn hoạt động bình thường. Nếu object đã hỏng ngầm sau failure, test thành công tiếp theo có thể phát hiện vấn đề mà so sánh một field chưa thấy.

Trong demo, `expectThrows` bắt `Throwable` chỉ để trình diễn một bộ assert xác định; **đây không phải chiến lược xử lý lỗi nghiệp vụ production**. Test thực nên dùng JUnit 5 `assertThrows` hoặc `assertThrowsExactly` với semantics phù hợp và tránh tự viết utility nếu framework đã có.

## 8. Kiểm tra exception guarantee từ bên ngoài, không buộc test vào field private

Nếu object có API public:

```java
int availableStock();
List<ReservationView> reservations();
InventoryStatus status();
```

thì test nên ưu tiên kiểm tra các **quan sát có trong hợp đồng** này. Không cần đọc field private bằng reflection trừ khi thật sự phải kiểm tra invariant không được biểu lộ và test được thiết kế cho implementation.

Cấu trúc kiểm thử nên có:

```text
Given:
  - tạo đối tượng ở state hợp lệ xác định
  - lấy snapshot qua public/read-only API
When:
  - gọi method và buộc một đường lỗi cụ thể
Then:
  - assert loại/mã lỗi/cause
  - assert state theo strong hoặc basic guarantee
  - assert bất biến giữa các field
  - assert không có side effect ngoài phạm vi
  - assert có thể dùng tiếp hoặc chuyển sang state FAILED đúng contract
```

Nếu implementation đổi từ mutable collection sang immutable record nhưng public state không đổi, test contract vẫn nên PASS. Test quá phụ thuộc vào số lần gọi setter hoặc thứ tự field assignment có thể bị vỡ vô ích khi refactor.

Tuy nhiên, khi phải bảo đảm **không gọi hệ thống bên ngoài nếu validation thất bại**, việc dùng fake/mock adapter để xác nhận “không gọi” là phù hợp, vì đây là side effect thuộc contract chứ không phải chi tiết triển khai ngẫu nhiên.

## 9. Khi chỉ có basic guarantee: kiểm tra phần tiến độ được cho phép

Một API xử lý batch có thể không hứa atomic cho cả danh sách. Ví dụ:

```java
void importRows(List<Row> rows) throws ImportException;
```

Đây là chữ ký minh họa; `Row` và `ImportException` của ứng dụng chưa được định nghĩa. Nếu contract nói “các record hoàn thành trước record lỗi vẫn giữ nguyên”, test phải **không khẳng định toàn batch không đổi**.

Giả sử row 1 và row 2 ghi thành công, row 3 không hợp lệ. Test basic guarantee có thể kiểm tra:

- Row 1, row 2 vẫn tồn tại chính xác một lần.
- Row 3 không được ghi dưới dạng record sai hoặc nửa record.
- Counter/sequence không hỏng.
- Index/cache giữ invariant.
- Không có resource/transaction handle bị rò rỉ.
- Có checkpoint hoặc con trỏ resume đúng theo contract.
- Việc gọi lại với cơ chế retry/resume không gây ghi trùng các record đã thành công.

Nếu hệ thống **hứa atomic batch**, kết quả đó lại là lỗi — test phải xác nhận rollback toàn bộ. Vì vậy **viết guarantee trước, viết assertion sau**. Không dùng một bộ assertion “unchanged” chung cho mọi API.

## 10. Phát hiện mutation một phần khi validation ở quá muộn

Một lỗi rất thường gặp:

```java
void updateProfile(UserProfile profile, String newEmail) {
    profile.setEmail(newEmail);
    if (!isValidEmail(newEmail)) {
        throw new IllegalArgumentException("invalid email");
    }
    notifyObservers(profile);
}
```

Đây là snippet minh họa, giả định `UserProfile`, `isValidEmail` và `notifyObservers`. Test chỉ kiểm tra exception sẽ bỏ sót `profile.email` đã đổi thành giá trị sai.

Cách cải thiện thường là **validate first**:

```java
void updateProfile(UserProfile profile, String newEmail) {
    if (!isValidEmail(newEmail)) {
        throw new IllegalArgumentException("invalid email");
    }
    profile.setEmail(newEmail);
    notifyObservers(profile);
}
```

Tuy nhiên, cách sửa này chỉ xử lý lỗi validation xảy ra trước mutation. Nếu `notifyObservers` ném exception sau `setEmail` thì profile **vẫn đã đổi**. Do đó validate-first **chưa đủ cho strong guarantee nếu các bước sau commit có thể thất bại**.

Có thể thiết kế:
- Prepare dữ liệu và tất cả validation trước commit.
- Commit state in-memory bằng một điểm gán nguyên tử ở ranh giới object.
- Thực hiện notification sau commit như tác động riêng với contract rõ: nếu notify thất bại, profile update có rollback hay đã commit?
- Nếu API yêu cầu atomic cùng notification, cần cơ chế phối hợp/transaction/outbox, không thể chỉ đảo lại thứ tự hai dòng đơn giản.

Test phải kích lỗi tại **mỗi bước có thể thất bại**, không chỉ input invalid.

## 11. Kiểm thử failure injection tại những mốc thực thi

Một input sai chỉ chạm một đường lỗi. Muốn biết method có strong/basic guarantee không, cần kích lỗi ở nhiều điểm:

| Mốc phát lỗi | Cần kiểm tra sau lỗi |
| --- | --- |
| Validation đầu vào | Không có mutation; không gọi dependency. |
| Sau khi tạo candidate state | Candidate bị bỏ; state cũ giữ nguyên. |
| Khi cấp phát tài nguyên thứ hai | Tài nguyên thứ nhất được đóng nếu owner đã acquire. |
| Sau mutation đầu tiên nhưng trước mutation thứ hai | Invariant và rollback theo contract. |
| Khi lưu vào database | Transaction rollback hoặc trạng thái pending/unknown đúng. |
| Khi phát event/notification | Ghi nhận trạng thái business commit riêng với event delivery. |
| Khi cleanup/close ném exception | Lỗi chính/các suppressed exceptions không bị mất; resource state có thể quan sát. |
| Khi callback/retry bị interrupt | Dừng theo policy; không để object ở trạng thái nửa đóng sai. |

**Failure injection** có thể dùng fake adapter để chủ động ném exception ở lần gọi thứ N, hoặc một fault injector trong integration test. Đừng phụ thuộc vào network thật tự nhiên thất bại đúng chỗ — test đó khó lặp và thường bỏ qua các điểm nguy hiểm nhất.

Trong Java, interface nhỏ giúp test dễ hơn:

```java
interface Store {
    void save(Order order) throws IOException;
}
```

Snippet này chỉ mô tả contract; `Order` và import cần được định nghĩa. Test dùng một `Store` giả lập có thể ném `IOException` trước/sau thao tác ghi để xác nhận service xử lý state đúng theo từng tình huống.

**Quan trọng:** giả lập “throw trước khi ghi” và “throw sau khi ghi” phải là **hai kịch bản khác nhau**. Nếu một timeout đến sau server commit, rollback bộ nhớ của client không làm mất giao dịch đã commit phía server. Kết quả này có thể là *unknown/pending*, không phải “không có side effect”.

## 12. Ví dụ Java 17: một điểm commit duy nhất

Đối với state in-memory, thiết kế dạng “tính toán trước rồi gán” giúp đạt strong guarantee nếu không có side effect quan sát được trước commit.

Tạo file `AtomicStateCommitDemo.java`:

```java
import java.util.Objects;

public class AtomicStateCommitDemo {

    private record Balance(int alice, int bob) {}

    private static final class Ledger {
        private Balance balance = new Balance(100, 50);

        Balance snapshot() {
            return balance;
        }

        void transfer(int amount, boolean failBeforeCommit) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount <= 0");
            }

            Balance old = balance;
            if (amount > old.alice()) {
                throw new IllegalStateException("insufficient funds");
            }

            Balance candidate =
                    new Balance(old.alice() - amount, old.bob() + amount);

            if (failBeforeCommit) {
                throw new IllegalStateException("injected failure");
            }

            // Chỉ một lần thay reference state.
            balance = candidate;
        }
    }

    public static void main(String[] args) {
        Ledger ledger = new Ledger();
        Balance before = ledger.snapshot();

        try {
            ledger.transfer(30, true);
        } catch (IllegalStateException ex) {
            System.out.println("failure: " + ex.getMessage());
        }
        System.out.println("unchanged: " + before.equals(ledger.snapshot()));
        System.out.println("after failure: " + ledger.snapshot());

        ledger.transfer(30, false);
        System.out.println("after success: " + ledger.snapshot());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 AtomicStateCommitDemo.java
java AtomicStateCommitDemo
```

Stdout:

```text
failure: injected failure
unchanged: true
after failure: Balance[alice=100, bob=50]
after success: Balance[alice=70, bob=80]
```

Đây là một điểm commit cho hai số dư **trong cùng object in-memory**. Nếu exception được kích trước điểm gán, state giữ nguyên. Nhưng điều đó **không phải transaction tiền thật**: một ledger production còn có concurrency, persistence, audit, điều kiện isolation và external side effect.

Ngay cả với một reference field, nếu nhiều thread cùng đọc/ghi, cần dùng cơ chế đồng bộ thích hợp như lock hoặc atomic CAS với invariant; test một thread không chứng minh linearizability/concurrency safety. Khi `Balance` nằm trong record immutable, một lần thay reference không tạo ra trạng thái “alice mới, bob cũ” trong cùng record, nhưng vẫn cần publication/visibility đúng.

## 13. Kiểm thử nhiều field và object graph

Đối tượng thực tế có quan hệ phức tạp:

```text
Order
 ├── status
 ├── total
 ├── List<OrderLine>
 │    ├── quantity
 │    └── price
 └── paymentReference
```

Một snapshot nông chỉ copy reference `OrderLine` có thể không phát hiện mutation ở `quantity`. Nếu strong guarantee áp dụng cho toàn bộ `Order` quan sát được, test phải đọc/copy đủ các trường của nested object:

- Tạo immutable view/DTO cho từng line.
- So sánh danh sách theo **giá trị**, không chỉ kích thước.
- Kiểm tra tổng tiền và quantity nhất quán.
- Kiểm tra không có event/record ở kho phụ bị thêm sau khi test gọi method.
- Khi object cung cấp collection view, kiểm tra không thể mutate nội bộ trái hợp đồng.

Một chiến lược là biến state nghiệp vụ thành immutable record/value object rồi object chủ quản thay toàn state bằng reference mới. Đừng nhầm immutable outer record với deep immutability nếu field của record vẫn là mutable `List` hoặc entity.

Trường hợp có identity có chủ đích (ví dụ bảo đảm trả lại chính object cũ), test `assertSame` có thể phù hợp. Nếu chỉ cần giá trị state không đổi, `assertEquals` hoặc semantic comparator phù hợp hơn và ít buộc implementation.

## 14. Trạng thái bên ngoài object: database, file, event và email

Nếu phương thức thất bại sau khi tác động bên ngoài, chỉ kiểm tra field Java là **chưa đủ**.

| Side effect | Quan sát sau lỗi cần kiểm tra |
| --- | --- |
| Database | Record đã commit chưa? Transaction rollback thật chưa? Unique key có bị tiêu thụ không? |
| File | File mới/đã ghi một phần có tồn tại không? Tệp tạm có được cleanup không? |
| Queue/message | Event đã enqueue hay publish chưa? Gửi lặp có bị dedup không? |
| HTTP tới dịch vụ khác | Response mất có phải outcome không rõ? Có operation ID đối soát không? |
| Email/notification | Đã gửi trước khi ném chưa? Retry có gửi hai lần không? |
| Cache/index | Cache invalidation có nhất quán với nguồn dữ liệu không? |
| Metrics/log | Nếu là hợp đồng quan sát, số đếm/outcome có đúng không? |

Một thất bại sau bước commit có thể được tài liệu hóa là **“operation đã thành công, nhưng thông báo kết quả gặp lỗi”** hoặc **“outcome unknown”**; khi ấy yêu cầu object/DB không đổi là sai thực tế. API nên dùng transaction/operation ID hoặc kết quả có trạng thái để người gọi không retry bừa.

Mục tiêu của test không phải khiến mọi exception biến side effect về 0 bằng phép màu; nó là **phát hiện đúng điều đã xảy ra và xác nhận contract**.

## 15. Cleanup và quyền sở hữu cũng là trạng thái cần kiểm thử

Một method có thể mở stream, acquire permit, lock hoặc subscribe listener. Khi nó ném exception, **cleanup đúng** là một phần bảo toàn trạng thái.

Ví dụ:

```java
try (InputStream in = Files.newInputStream(path)) {
    parse(in);
}
```

Đây là snippet minh họa; `path`, `parse` và các import phù hợp chưa được khai báo. Khi `parse` ném exception, try-with-resources vẫn đóng `in`. Một test bằng fake resource có thể đếm số lần `close()` và xác nhận **đúng owner đã đóng đúng phạm vi**.

Những trường hợp cần test:

1. Tài nguyên thứ nhất mở thành công, mở tài nguyên thứ hai thất bại: thứ nhất được đóng.
2. Body ném exception, `close()` thành công: lỗi chính giữ nguyên và resource được đóng.
3. Body và `close()` cùng ném: exception từ close được đưa vào `getSuppressed()`, trừ những cấu trúc xử lý khác của implementation.
4. Một borrowed resource được truyền vào method: method **không tự đóng** nếu hợp đồng không chuyển ownership.
5. Đã đăng ký listener rồi lỗi giữa startup: handle đăng ký trước đó được hủy nếu chưa chuyển quyền sở hữu.
6. Lỗi trong `Semaphore.acquire()` hoặc `Lock.lockInterruptibly()`: không release/unlock khi chưa acquire.
7. Cancellation/interruption: lifecycle trả về trạng thái có thể quan sát; không giả định `cancel(true)` chứng minh cleanup hoàn tất.

Đóng tài nguyên chưa chắc rollback business state. Một `FileOutputStream.close()` không làm mất dữ liệu đã ghi; `unsubscribe` không rút lại những callback đã chạy. Vì vậy test cần tách **lifecycle cleanup** khỏi **business rollback**.

## 16. Ví dụ Java 17: body ném và close cũng lỗi

Ví dụ này minh họa cách kiểm tra object state sau khi có **hai exception liên quan**: lỗi body là primary; lỗi `close()` là suppressed; cờ resource đã đóng được kiểm tra độc lập.

Tạo file `CleanupAfterFailureDemo.java`:

```java
import java.io.IOException;
import java.util.concurrent.atomic.AtomicBoolean;

public class CleanupAfterFailureDemo {

    private static final class Resource implements AutoCloseable {
        private final AtomicBoolean closed;

        Resource(AtomicBoolean closed) {
            this.closed = closed;
        }

        @Override
        public void close() throws IOException {
            closed.set(true);
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        AtomicBoolean closed = new AtomicBoolean(false);

        try (Resource resource = new Resource(closed)) {
            throw new IllegalStateException("work failed");
        } catch (IllegalStateException ex) {
            System.out.println("primary: " + ex.getMessage());
            System.out.println("suppressed: " + ex.getSuppressed().length);
            System.out.println(
                    "cleanup error: " + ex.getSuppressed()[0].getMessage());
        } catch (IOException ex) {
            System.out.println("unexpected close-only: " + ex.getMessage());
        }

        System.out.println("close invoked: " + closed.get());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 CleanupAfterFailureDemo.java
java CleanupAfterFailureDemo
```

Stdout:

```text
primary: work failed
suppressed: 1
cleanup error: close failed
close invoked: true
```

**Diễn giải chính xác:** cờ `closed=true` trong ví dụ chỉ có nghĩa **code `close()` đã chạy đến bước ghi cờ**. Vì `close()` vẫn ném `IOException`, không được kết luận mọi tài nguyên production đã được giải phóng thành công. Với file, socket, connection hoặc flush buffer thật, việc cleanup hoàn tất cần được đánh giá theo contract và trạng thái của API đó.

Test đầy đủ kiểm tra primary exception, suppressed exception, trạng thái ghi nhận cleanup và khả năng object/ứng dụng đi tiếp sau lỗi theo hợp đồng.

## 17. Kiểm tra trạng thái khi lỗi được bọc hoặc đổi nghĩa

Một method có thể bắt lỗi tầng thấp rồi ném loại lỗi ổn định hơn:

```java
try {
    repository.save(entity);
} catch (SQLException ex) {
    throw new RepositoryException("save failed", ex);
}
```

Đây là mảnh minh họa, `repository`, `entity`, `RepositoryException` và import chưa được định nghĩa. Test không nên dừng ở `RepositoryException`:

- `getCause()` có phải lỗi SQL gốc không?
- Repository transaction đã rollback hay commit chưa?
- Entity in-memory có bị đánh dấu `SAVED` sai không?
- Cache có bị cập nhật một phần không?
- Nếu operation có thể đã commit nhưng response mất, có trạng thái **pending/unknown** và cơ chế đối soát không?

Nếu method catch rồi **swallow exception**, test cần xác nhận fallback/result domain rõ ràng; không được để lỗi biến thành thành công giả mà state thiếu nhất quán.

### Bắt lỗi ở đúng boundary

Nếu test ở tầng service, inject lỗi repository vào fake; assert state service và các lệnh gọi dependency. Nếu test ở tầng repository, dùng transaction/test database thật để xác nhận rollback/constraints. **Không cố dùng một unit test giả lập để chứng minh toàn bộ ACID guarantee của database production**.

## 18. JUnit 5: mẫu test exception và state bằng snapshot

Với một class có method và snapshot public thích hợp, test JUnit 5 có thể dùng:

```java
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class InventoryTest {

    @Test
    void reserveFailureLeavesStateUnchanged() {
        Inventory inventory = new Inventory(5);
        InventorySnapshot before = inventory.snapshot();

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> inventory.reserve("book", 7));

        InventorySnapshot after = inventory.snapshot();

        assertAll(
                () -> assertEquals("insufficient stock", error.getMessage()),
                () -> assertEquals(before, after),
                () -> assertEquals(5, after.available()),
                () -> assertEquals(0, after.reservations().size())
        );
    }
}
```

**Đây là template JUnit, không phải file tự chạy bằng JDK:** `Inventory`/`InventorySnapshot` là các kiểu ứng dụng cần được triển khai, JUnit 5 là dependency ngoài JDK. Đoạn test thể hiện cách kiểm tra cả exception và state; không bịa rằng JUnit có sẵn trong Java 17.

`assertAll` cho phép chạy một nhóm assertion và thu thập nhiều thất bại, giúp chẩn đoán state phức tạp. Tuy nhiên, nếu `after` là null hoặc getter ném exception, một assertion có thể cần được sắp xếp lại để tránh che nguyên nhân kiểm thử.

Nếu muốn chấp nhận subtype, `assertThrows(ExpectedException.class, ...)` phù hợp. Nếu contract đòi **đúng kiểu, không chấp nhận subtype**, JUnit 5 có `assertThrowsExactly` ở những phiên bản hỗ trợ; dùng khi thật sự có yêu cầu đó, không chỉ để làm test quá chặt.

## 19. Test sự phục hồi sau khi object đã thất bại một lần

Một object có thể qua được test “state không đổi” nhưng vẫn không thể sử dụng tiếp vì flag `busy`, lock, queue hoặc resource bị mắc kẹt.

Trình tự kiểm thử hữu ích:

1. Tạo object hợp lệ.
2. Gọi phương thức với input gây lỗi.
3. Khẳng định loại exception, trạng thái và invariant sau lỗi.
4. Gọi **một operation hợp lệ**.
5. Xác nhận operation hợp lệ thành công và state mới đúng.
6. Nếu object phải chuyển sang trạng thái không thể dùng tiếp (`FAILED`/`CLOSED`), xác nhận lời gọi tiếp theo bị từ chối bằng exception theo contract.

Ví dụ `Account` ở mục 7 bị từ chối rút `120` nhưng vẫn rút được `40` sau đó. Đây là kiểm tra rất hữu ích với service/resource object có lifecycle.

Đối với object bị đánh dấu `FAILED`, test đừng đòi nó hoạt động bình thường nếu contract yêu cầu discard/recreate. Bảo đảm đúng là **không giả vờ usable khi state không an toàn**.

## 20. State machine và tính hợp lệ của chuyển trạng thái

Với một lifecycle:

```text
NEW → OPEN → ACTIVE → CLOSED
             |
             +→ FAILED
```

Nếu `activate()` ném giữa chừng, đối tượng phải nằm ở trạng thái được thiết kế: vẫn `OPEN` (strong guarantee), hoặc `FAILED` (basic guarantee) nếu không thể rollback. Không được để một đối tượng vừa có `state=ACTIVE` vừa thiếu các resource cần thiết để thật sự hoạt động.

Test nên xác định:

- Những state nào hợp lệ?
- Chuyển nào được phép?
- Exception ở mỗi transition khiến state cuối là gì?
- Resource có được cleanup khi sang `FAILED` hoặc `CLOSED` không?
- Gọi lặp `close`/`activate` có idempotent hoặc ném rõ ràng không?
- Object có thể recover hay phải tạo lại?
- Có event callback nào còn chạy sau khi unregister không?

Nếu enum state đã đổi nhưng phần resource tương ứng chưa đổi, invariant có thể bị phá. Cần kiểm tra **state machine và các phụ thuộc**, không chỉ enum.

## 21. Concurrency: state đúng sau exception cần thêm thread safety

Các test một thread chỉ kiểm tra một phần. Một phương thức có thể bảo toàn state trong đường exception nhưng vẫn có race:

```java
State old = state;
State next = compute(old);
state = next;
```

Đây là snippet minh họa. Nếu hai thread cùng tính từ `old` và gán, một thay đổi có thể bị mất. Strong exception guarantee **không đồng nghĩa** linearizability, atomicity giữa các thread hay safe publication.

Một số hướng kiểm thử:

- Dùng `CountDownLatch`/`CyclicBarrier` để tạo interleaving có kiểm soát ở trước commit.
- Inject lỗi ở một thread khi thread kia đang đọc hoặc cập nhật.
- Xác nhận invariant không bị phá và kết quả quan sát theo synchronization contract.
- Nếu dùng `synchronized`/lock/CAS, kiểm tra không deadlock/lost update.
- Nếu callback cleanup xảy ra ở background thread, cần **đợi tín hiệu hoàn tất rõ ràng**, không dùng `Thread.sleep(50)` để phỏng đoán.
- Với `Future.cancel(true)`, trạng thái canceled của future không chứng minh worker đã cleanup hoàn tất; dùng acknowledgement/`CountDownLatch` khi contract yêu cầu.

**Đừng kiểm tra state ngay sau khi chỉ gửi yêu cầu cancel rồi tuyên bố code cleanup sai** nếu API cho phép cleanup hoàn tất bất đồng bộ. Hãy phân biệt mốc “yêu cầu dừng” với mốc “đã dừng”.

## 22. Property-based và fault-injection testing

Một vài ví dụ đơn lẻ chưa đủ chứng minh invariant tổng quát. Có thể kiểm tra bằng nhiều input và điểm lỗi:

- Sinh quantity âm, zero, nhỏ hơn tồn, bằng tồn, lớn hơn tồn; check invariant và guarantee từng nhánh.
- Sinh chuỗi thao tác hợp lệ/lỗi đan xen; object vẫn hợp lệ sau mỗi bước.
- Inject lỗi sau bước chuẩn bị A, B, C và trước commit, xem state có được giữ nguyên nếu API hứa strong.
- Inject lỗi cleanup để kiểm tra suppressed exceptions.
- Với nhiều tài nguyên, tạo lỗi khi resource thứ N được mở; các resource trước đó được đóng.
- Với retry, ném lỗi transient sau khi side effect đã xảy ra để phát hiện duplicate.
- Với transaction, mô phỏng lost response sau commit và xác nhận logic đánh dấu UNKNOWN/idempotency.
- Với concurrent API, chủ động thay đổi thứ tự hai thread và check invariant dưới contention.

Có thể dùng property-based testing framework ngoài JDK (ví dụ jqwik) hoặc viết vòng lặp data-driven. Không nên dựa vào random input không seed rồi test lúc pass lúc fail không tái lập. Lưu seed và scenario khi một phép thử thất bại để debug.

### Những property hữu ích

```text
Nếu reserve(q) thất bại dưới strong guarantee:
    snapshotAfter == snapshotBefore

Ở mọi trạng thái hợp lệ của inventory:
    available >= 0
    all reservation quantities > 0

Nếu transfer(a→b,q) thành công trong ledger không phí:
    balanceA + balanceB không đổi

Nếu transfer thất bại trước commit:
    cả balanceA và balanceB không đổi

Nếu close/cleanup hoàn tất theo contract:
    owner không còn giữ resource đang mở
```

Đây là các property **minh họa có điều kiện**. Ví dụ tổng balance chỉ bất biến khi không có phí/chuyển tiền ra ngoài ledger; đừng áp dụng ngoài giả định.

## 23. Phân biệt test unit, integration và end-to-end

| Cấp độ | Có thể xác minh tốt | Giới hạn |
| --- | --- | --- |
| **Unit** với fake/mocks | State Java, snapshot, số lần gọi, mốc injected exception, basic/strong logic | Không tự chứng minh transaction thật hoặc mạng đã commit. |
| **Integration** với DB/filesystem/message broker kiểm thử | Rollback, constraint, file cleanup, transaction boundary, side effect tương tác | Có thể chưa bao quát mọi race hoặc sự cố hạ tầng. |
| **End-to-end** với hệ thống nhiều service | Operation ID, retry/idempotency, trạng thái UNKNOWN, recovery sau incident | Tốn kém và khó fault-inject chính xác mọi điểm; cần đo ổn định. |

Tầng nào cũng cần kiểm tra exception **và state** theo boundary đó. Một fake DB ném `IOException` trước khi ghi giúp unit test service, nhưng không chứng minh DB thật không commit khi kết nối mất ngay sau câu lệnh COMMIT.

## 24. Những lỗi kiểm thử thường gặp

**Chỉ assert exception type.** Bỏ sót mutation và invariant hỏng. Luôn bổ sung state/side effect theo contract.

**Chụp snapshot bằng reference tới mutable list.** Trạng thái trước/sau cùng thay đổi khiến test false pass. Tạo snapshot độc lập.

**So sánh sai mức guarantee.** API chỉ hứa basic nhưng test yêu cầu mọi state không đổi, hoặc API hứa strong mà test chỉ kiểm tra một field.

**Chỉ inject lỗi ở bước đầu.** Không tìm ra lỗi xảy ra sau mutation hoặc trong cleanup. Dùng fault injection ở các mốc quan trọng.

**Chỉ kiểm tra một field như `status`.** Bỏ sót balance, collection, version, resource, event và DB.

**Assert exception message không ổn định.** Test vỡ khi thay câu chữ, dù contract không đổi. Ưu tiên type/code/cause ổn định.

**Bỏ qua nested mutable object.** Shallow snapshot có thể không phát hiện thay đổi trong phần tử.

**Dùng mock gọi `save` làm bằng chứng DB rollback.** Mock chỉ xác nhận invocation, không chứng minh semantics của transaction thật.

**Nhầm timeout với thất bại chắc chắn của remote operation.** Outcome có thể không rõ; test phải diễn tả PENDING/UNKNOWN và đối soát khi phù hợp.

**Bỏ qua cleanup.** Object field đúng nhưng connection hoặc listener rò rỉ. Kiểm tra ownership và lifecycle.

**Đọc state trước khi async cleanup hoàn tất.** Cần đợi tín hiệu completion theo contract.

**Không thử operation thành công sau lần lỗi.** Có thể bỏ sót cờ `busy` hoặc lock bị giữ khiến object không usable.

**Tạo test không xác định bằng `Thread.sleep`.** Dùng latch/barrier/fake clock khi có thể.

**Cho rằng fail-fast ở input đủ mạnh cho mọi exception.** Sau validation còn thể có I/O, allocation, observer callbacks và persistence ném lỗi.

**Dùng reflection để test implementation detail thay cho API contract.** Dễ làm test giòn và cản refactor; chỉ dùng khi thực sự cần.

## 25. Checklist cho test trạng thái sau exception

Trước khi xem một test là hoàn chỉnh, hãy hỏi:

- [ ] Đã nêu guarantee của method là strong/basic/no-throw hay contract cụ thể khác?
- [ ] Đã tạo trạng thái ban đầu hợp lệ và lưu **snapshot độc lập**?
- [ ] Đã kích đúng loại lỗi dự kiến, kiểm tra type/code/cause?
- [ ] Đã so sánh toàn bộ phần state thuộc contract, không chỉ một field?
- [ ] Đã kiểm tra invariant sau thất bại?
- [ ] Đã kiểm tra side effect ngoài object khi operation có DB/file/event/network?
- [ ] Đã kiểm tra resource owner cleanup, không đóng borrowed resource?
- [ ] Đã test lỗi sau partial work và lỗi trong cleanup?
- [ ] Đã phân biệt rollback với unknown outcome khi response có thể bị mất?
- [ ] Đã test object hoạt động tiếp hoặc chuyển đúng lifecycle state?
- [ ] Đã kiểm tra concurrency/synchronization nếu object được chia sẻ?
- [ ] Đã kiểm soát thứ tự với fake/latch thay vì sleep ngẫu nhiên?
- [ ] Đã có test happy path để chắc giải pháp sửa lỗi không làm hỏng thao tác thành công?
- [ ] Đã chạy lại test sau refactor và không khóa test vào chi tiết implementation không cần thiết?

## 26. Bài tập tự kiểm tra

**Câu 1:** `reserve(7)` ném đúng `IllegalStateException` nhưng `available=-2`. Test `assertThrows` có thể pass không? Object có bảo toàn invariant tồn không âm không?

**Đáp án:** `assertThrows` có thể pass, nhưng object đã sai invariant. Test phải khẳng định `available` và các reservation sau exception.

**Câu 2:** Bạn viết `List<Item> before = object.items()`; `items()` trả list nội bộ. Sau khi method thất bại, so sánh `before.equals(object.items())` trả true. Có đủ chứng minh strong guarantee không?

**Đáp án:** Không. Hai reference có thể cùng trỏ tới list đã bị mutate. Cần snapshot độc lập; nếu `Item` mutable, cần copy sâu/phép so sánh semantic thích hợp.

**Câu 3:** Batch import 10 record và lỗi ở record 8; 7 record trước đã commit. Basic guarantee có thể vẫn đúng không?

**Đáp án:** Có, **nếu contract cho phép partial progress**, mọi invariant đúng và không leak tài nguyên. Nếu API hứa atomic batch/strong guarantee thì test phải fail.

**Câu 4:** Đối tượng cập nhật DB thành công nhưng response bị mất. Client nhận timeout. Có thể assert DB không đổi chỉ vì client thấy exception không?

**Đáp án:** Không. Outcome của remote có thể đã commit. Cần kiểm tra trạng thái thật hoặc operation ID/idempotency để đối soát, không suy ra rollback từ exception phía client.

**Câu 5:** `try-with-resources` có body ném `IllegalStateException` và `close` ném `IOException`. Test cần kiểm tra gì?

**Đáp án:** Lỗi body là primary, lỗi close có thể nằm trong `getSuppressed()`, và trạng thái cleanup cần được kiểm tra theo contract của resource. Gọi `close` không tự chứng minh đã giải phóng hoàn toàn.

**Câu 6:** Test dùng `future.cancel(true)`, ngay lập tức assert listener đã unregister nhưng test thường thất bại. Có chắc implementation sai không?

**Đáp án:** Chưa chắc. Cancellation state của Future có thể thay đổi trước khi worker cleanup hoàn tất. Phải đợi acknowledgement hoặc synchronization theo contract nếu test muốn kiểm tra mốc cleanup hoàn thành.

**Câu 7:** Inventory dùng record immutable và một lần gán `state = candidate` nên strong guarantee trong một thread. Điều đó bảo đảm an toàn khi hai thread cùng `reserve` không?

**Đáp án:** Không. Hai thread có thể đọc cùng state cũ rồi gán kết quả khác nhau, mất cập nhật. Cần đồng bộ/CAS hoặc cơ chế concurrency phù hợp.

**Câu 8:** Sau một exception, state nhìn có vẻ đúng nhưng lệnh hợp lệ tiếp theo luôn ném `IllegalStateException("busy")`. Test nào có thể phát hiện?

**Đáp án:** Một test **thao tác thành công sau thất bại**, kiểm tra object còn usable theo contract, sẽ phát hiện cờ busy hoặc lifecycle bị mắc kẹt.

## 27. Kết luận

**Một exception đúng loại chỉ xác nhận đường báo lỗi; trạng thái sau exception mới cho biết đối tượng có còn đúng hợp đồng hay không.** Để kiểm thử đầy đủ, hãy công bố strong/basic/no-throw guarantee hoặc điều kiện tương đương, chụp snapshot độc lập trước lời gọi, kích lỗi ở nhiều mốc, rồi kiểm tra trạng thái, invariant, side effect, cleanup và khả năng sử dụng tiếp.

Thiết kế giảm lỗi thường dựa vào **validate trước mutation**, **prepare candidate trước commit**, **commit tại một ranh giới rõ**, và **transaction/compensation/idempotency** khi side effect vượt ra ngoài bộ nhớ. Kiểm thử nên bám vào những bảo đảm có thể quan sát, không phán đoán rollback chỉ từ exception. Khi làm được vậy, hệ thống vừa báo lỗi đúng, vừa giữ trạng thái đáng tin cậy sau những đường chạy không thành công.