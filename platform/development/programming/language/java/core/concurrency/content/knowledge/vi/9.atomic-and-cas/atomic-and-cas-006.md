# Atomic compound reference qua immutable state

Trong lập trình Java concurrency, một thao tác thường phải thay đổi **nhiều trường cùng lúc** để giữ một bất biến nghiệp vụ. Ví dụ: giảm số suất còn trống và tăng số suất đã đặt; chuyển tiền giữa hai số dư; hoặc cập nhật danh sách cấu hình cùng phiên bản. Hai phép ghi độc lập vẫn tạo ra **khoảng thời gian ở giữa** để thread khác quan sát trạng thái dở dang, dù mỗi trường sử dụng `AtomicInteger`, `volatile` hay getter thread-safe.

**Atomic compound reference qua immutable state** là kỹ thuật gói toàn bộ những trường cần nhất quán vào **một object immutable**, rồi quản lý **một tham chiếu duy nhất** bằng `AtomicReference<State>`. Writer đọc snapshot hiện hành, tạo snapshot mới và dùng `compareAndSet(old, next)` để **thay một tham chiếu nguyên tử**. Reader chỉ cần lấy một snapshot bằng `get()` và đọc mọi component từ chính snapshot đó.

Mục tiêu là bảo đảm:
- **Reader không thấy trạng thái cập nhật một nửa** trong nhóm trường được gói cùng một snapshot.
- **Writer không làm mất cập nhật** của writer khác nếu kiểm tra điều kiện, tính trạng thái mới và commit bằng vòng CAS đúng cách.
- **Đối tượng cũ không bị sửa**, nên những thread còn đang cầm snapshot cũ vẫn đọc một phiên bản nhất quán.

Tất cả cơ chế trong bài là Java core (`java.util.concurrent.atomic` và Java Memory Model), không phụ thuộc framework.

## 1. Vì sao nhiều atomic field vẫn có race ở cấp invariant?

Giả sử lớp Inventory quản lý hai số:

```text
available >= 0
reserved >= 0
available + reserved == totalCapacity
```

Cập nhật này **không nguyên tử theo cặp**:

```java
// Mã minh họa: hai biến là AtomicInteger.
available.decrementAndGet();
reserved.incrementAndGet();
```

`decrementAndGet()` và `incrementAndGet()` an toàn **riêng lẻ**, nhưng một reader có thể chạy sau phép giảm và trước phép tăng, thấy tổng tạm thời sai. `volatile` không giải quyết được vì nó không biến hai phép ghi thành một transaction.

### Ví dụ 1 — Tái hiện ảnh chụp không nhất quán

Tạo file **`SplitAtomicState.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class SplitAtomicState {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger available = new AtomicInteger(1);
        AtomicInteger reserved = new AtomicInteger(0);

        CountDownLatch firstWriteDone = new CountDownLatch(1);
        CountDownLatch allowSecondWrite = new CountDownLatch(1);

        Thread writer = new Thread(() -> {
            available.decrementAndGet();
            firstWriteDone.countDown();

            try {
                allowSecondWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            reserved.incrementAndGet();
        }, "writer");

        writer.start();
        firstWriteDone.await();

        System.out.println("Intermediate: available="
                + available.get() + ", reserved=" + reserved.get());
        System.out.println("Intermediate total: "
                + (available.get() + reserved.get()));

        allowSecondWrite.countDown();
        writer.join();

        System.out.println("Final total: "
                + (available.get() + reserved.get()));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac SplitAtomicState.java
java SplitAtomicState
```

Kết quả trong lần chạy bình thường, không có interrupt bên ngoài:

```text
Intermediate: available=0, reserved=0
Intermediate total: 0
Final total: 1
```

Hai `CountDownLatch` điều khiển lịch xen kẽ để main đọc chính xác lúc phép ghi đầu đã hoàn tất còn phép ghi thứ hai chưa chạy. Đây là **race condition của invariant**, không phải lỗi của từng lớp `AtomicInteger`. Việc sau cùng tổng trở về 1 **không làm hợp lệ** ảnh chụp tạm thời bằng 0 mà client có thể nhìn thấy.

Nếu client cần đọc `available` và `reserved` như một đơn vị thì phải có giao thức bảo vệ cả hai, chẳng hạn một monitor chung hoặc một immutable state snapshot được công bố nguyên tử.

## 2. Thiết kế State immutable: một phiên bản, nhiều trường

Ta dùng record Java 17 cho value object:

```java
record Inventory(int available, int reserved) {
}
```

Đây là trích đoạn định nghĩa kiểu, chưa phải chương trình độc lập. Record chỉ chứa hai `int` không có đường sửa field sau khi tạo, do đó mỗi instance là một **ảnh chụp bất biến**. Khi muốn thay đổi, tạo object mới:

```java
Inventory old = new Inventory(2, 0);
Inventory next = new Inventory(1, 1);
// old vẫn là (2, 0), next là (1, 1).
```

Dùng một tham chiếu trung tâm:

```java
AtomicReference<Inventory> state =
        new AtomicReference<>(new Inventory(2, 0));
```

Đoạn trên cần import `java.util.concurrent.atomic.AtomicReference`. Một reader đọc đúng cách:

```java
Inventory snapshot = state.get();
int total = snapshot.available() + snapshot.reserved();
```

Lưu ý **lấy `get()` một lần**. Nếu viết `int a = state.get().available(); int b = state.get().reserved();`, hai lần `get()` có thể nhận **hai snapshot khác nhau** khi writer cập nhật ở giữa, tái tạo lỗi trộn phiên bản dù bản thân mỗi snapshot đều nhất quán.

Tính đúng đắn đến từ **hai thành phần kết hợp**:

1. **Snapshot immutable:** sau khi công bố object không bị sửa thông qua alias nào.
2. **AtomicReference:** `get()` đọc một tham chiếu nguyên tử; CAS commit một tham chiếu nguyên tử, đồng thời dùng hiệu ứng bộ nhớ thích hợp của Java Memory Model.

Chỉ đặt `AtomicReference<MutableState>` rồi gọi `state.get().setX(...)` **không làm các mutation bên trong an toàn**. CAS chỉ bảo vệ việc thay tham chiếu chứ không bọc mọi setter của object mà nó trỏ tới.

## 3. CAS loop: đọc snapshot, tính mới, commit hoặc retry

Khung thuật toán:

```java
while (true) {
    State oldState = state.get();
    State newState = transform(oldState);
    if (state.compareAndSet(oldState, newState)) {
        break; // Commit thành công.
    }
    // Thread khác đã đổi state; phải đọc và tính lại.
}
```

Đây là trích đoạn minh họa với `State`, `state` và `transform` được giả định đã định nghĩa. `compareAndSet(expected, update)` thành công khi tham chiếu hiện tại **chính là reference expected (`==`)**, và thay bằng reference update trong một bước nguyên tử. Nó so sánh **identity**, không gọi `equals()` trên hai record có component giống nhau.

Ví dụ hai writer đồng thời:

```text
current = S0

Thread A: get S0 -> tạo S1
Thread B: get S0 -> tạo S2

A: CAS(S0, S1) = true   -> current = S1
B: CAS(S0, S2) = false  -> không ghi đè S1
B: get S1 -> tính lại S3 từ S1
B: CAS(S1, S3) = true   -> current = S3
```

Nếu B dùng `state.set(S2)` thay vì retry, bản cập nhật của A có thể bị ghi đè. **Phép gán tham chiếu nguyên tử** khác với **cập nhật đọc–tính–ghi nguyên tử**. CAS loop tạo một điểm commit có thể tuyến tính hóa (*linearization point*) tại phép CAS thành công.

Điểm bắt buộc: điều kiện nghiệp vụ cũng phải được kiểm tra **trên snapshot mới nhất của mỗi vòng lặp**. Không được đọc “còn hai suất” trước vòng lặp rồi cứ cố ghi nếu các writer khác đã lấy hết suất.

## 4. Ví dụ 2 — AtomicInventory: cập nhật nhiều trường cùng nhau

Tạo file **`AtomicInventory.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class AtomicInventory {
    record Inventory(int available, int reserved) {
    }

    static final class Store {
        private final AtomicReference<Inventory> state =
                new AtomicReference<>(new Inventory(2, 0));

        boolean reserveOne() {
            while (true) {
                Inventory old = state.get();

                if (old.available() <= 0) {
                    return false;
                }

                Inventory next = new Inventory(
                        old.available() - 1,
                        old.reserved() + 1
                );

                if (state.compareAndSet(old, next)) {
                    return true;
                }
                // Thử lại với snapshot mới và kiểm tra lại số suất.
            }
        }

        Inventory snapshot() {
            return state.get();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Store store = new Store();
        AtomicInteger accepted = new AtomicInteger();

        Runnable request = () -> {
            if (store.reserveOne()) {
                accepted.incrementAndGet();
            }
        };

        Thread a = new Thread(request, "A");
        Thread b = new Thread(request, "B");
        Thread c = new Thread(request, "C");

        a.start();
        b.start();
        c.start();
        a.join();
        b.join();
        c.join();

        Inventory s = store.snapshot();
        System.out.println("Accepted: " + accepted.get());
        System.out.println("Available: " + s.available());
        System.out.println("Reserved: " + s.reserved());
        System.out.println("Total: " + (s.available() + s.reserved()));
    }
}
```

```bash
javac AtomicInventory.java
java AtomicInventory
```

Kết quả:

```text
Accepted: 2
Available: 0
Reserved: 2
Total: 2
```

**Diễn giải:**

- Ban đầu chỉ có object `Inventory(2, 0)`.
- Mỗi thread cùng gọi `reserveOne()` và có thể đọc snapshot giống nhau. Nhưng **chỉ một CAS** với cùng expected object thắng khi current vẫn là object đó.
- Thread CAS thất bại **không sửa state**. Nó phải lấy snapshot mới, kiểm tra lại `available` và tính lại.
- Cuối cùng hai lượt đặt thành công, trạng thái `Inventory(0, 2)`. Thread thứ ba sẽ thấy đã hết suất ở một vòng lặp nào đó và trả về `false`.
- Không xác định **thread nào thắng**, nhưng invariant `available + reserved == 2` đúng với **mọi snapshot được công bố**.
- `accepted` là biến đo trong chương trình demo, không phải thành phần dùng để bảo vệ invariant của Store. `join()` chờ tất cả worker trước khi main in trạng thái cuối.

Reader có thể gọi `store.snapshot()` khi writer đang chạy. Snapshot trả về không bị mutate, nên dù người khác commit bản tiếp theo, reader vẫn thấy **một phiên bản nhất quán**. Tuy nhiên, nó có thể là bản đã cũ vào thời điểm reader ra quyết định; các quyết định cần commit phải quay lại CAS/lock, không chỉ dựa vào snapshot đã đọc trước đó.

## 5. Trả kết quả sau CAS và thiết kế API hợp thành

Một yêu cầu thực tế không chỉ cần biết có đặt thành công hay không mà còn muốn số suất **sau chính lượt đặt đó**. Trong CAS loop, có thể trả `next` **sau khi CAS thành công**, vì đó là snapshot đã commit của lời gọi.

```java
// Trích đoạn trong Store; định nghĩa Inventory/state như Ví dụ 2.
Inventory reserveAndReturn() {
    while (true) {
        Inventory old = state.get();
        if (old.available() == 0) {
            return old; // Ví dụ tối giản: nhánh không đặt được.
        }
        Inventory next = new Inventory(
                old.available() - 1,
                old.reserved() + 1
        );
        if (state.compareAndSet(old, next)) {
            return next;
        }
    }
}
```

Trong API production, nên định nghĩa kiểu kết quả thể hiện rõ **đặt thành công hay thất bại**; không buộc caller suy luận từ `Inventory` trả về. Snapshot `next` phản ánh chính trạng thái đã commit, nhưng **thread khác có thể thay nó ngay sau khi CAS thắng**. Nó không phải cam kết “đây sẽ là state mới nhất cho tới khi caller xử lý xong”.

Cần tránh thiết kế API gồm `getAvailable()` rồi `reserve()` và bảo caller tự thực hiện check-then-act. Chỉ nên công bố thao tác hợp thành `reserveOne()`/ `tryReserve()` để bảo đảm invariant ở cấp quyết định.

## 6. Ví dụ 3 — Chuyển tiền giữa hai số dư trong cùng snapshot

Một ứng dụng khác là chuyển giá trị từ `checking` sang `savings`. Bất biến: hai số dư không âm và **tổng không đổi**. Ta gói hai số dư vào một record để mọi lần commit thay hai giá trị như một đơn vị.

Tạo file **`AtomicAccounts.java`**:

```java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicAccounts {
    record Balances(long checking, long savings) {
    }

    static final class Ledger {
        private final AtomicReference<Balances> state =
                new AtomicReference<>(new Balances(100, 0));

        boolean moveToSavings(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }

            while (true) {
                Balances old = state.get();
                if (old.checking() < amount) {
                    return false;
                }
                Balances next = new Balances(
                        old.checking() - amount,
                        old.savings() + amount
                );
                if (state.compareAndSet(old, next)) {
                    return true;
                }
            }
        }

        Balances snapshot() {
            return state.get();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Ledger ledger = new Ledger();

        Thread a = new Thread(() -> ledger.moveToSavings(30));
        Thread b = new Thread(() -> ledger.moveToSavings(40));

        a.start();
        b.start();
        a.join();
        b.join();

        Balances s = ledger.snapshot();
        System.out.println("Checking: " + s.checking());
        System.out.println("Savings: " + s.savings());
        System.out.println("Total: " + (s.checking() + s.savings()));
    }
}
```

```bash
javac AtomicAccounts.java
java AtomicAccounts
```

Kết quả:

```text
Checking: 30
Savings: 70
Total: 100
```

Hai lời chuyển lần lượt 30 và 40 đều có thể thực hiện từ số dư 100; thứ tự CAS nào cũng dẫn đến 30/70. Mỗi snapshot đã commit duy trì tổng 100. **Đây chỉ là ví dụ sổ cái trong bộ nhớ một JVM**: không bảo đảm lưu bền, phục hồi, kiểm toán hay giao dịch giữa database/tiến trình. Đối với tiền thật cần thiết kế số học (đơn vị tiền nguyên nhỏ nhất hoặc `BigDecimal` theo quy tắc phù hợp), transaction và cơ chế tránh thực hiện hai lần ở hệ thống bên ngoài. CAS **không** thay thế transaction của hệ thống sở hữu dữ liệu.

## 7. Immutable nghĩa là không có mutable alias: record chưa đủ trong mọi trường hợp

Record có primitive và String tương đối đơn giản để chia sẻ. Nhưng record chứa list vẫn có thể **chỉ immutable ở mức tham chiếu**:

```java
record UnsafeCatalog(java.util.List<String> items) {
    // Caller giữ List mutable được truyền vào vẫn có thể sửa nó.
}
```

Đây là trích đoạn kiểu dữ liệu. `final List` không ngăn một `ArrayList` bên ngoài sửa nội dung. Bảo vệ bằng defensive copy:

```java
record Catalog(java.util.List<String> items) {
    Catalog {
        items = java.util.List.copyOf(items);
    }
}
```

`List.copyOf` tạo hoặc tái sử dụng một danh sách **không sửa được** với các phần tử đã cho theo hợp đồng. Nếu phần tử là `String` immutable, state được chia sẻ an toàn. Nếu là `MutableOrder` có setter, copy list **không deep-copy** từng item; tham chiếu mutable bên trong vẫn có thể bị sửa. Khi đó cần component immutable, sao chép sâu hoặc kiểm soát ownership.

Không nhầm `Collections.unmodifiableList(original)` (một view không cho sửa trực tiếp, nhưng `original` có thể bị nơi khác thay đổi) với snapshot độc lập.

## 8. Ví dụ 4 — Cập nhật Catalog bằng copy-on-write và updateAndGet

Tạo file **`AtomicCatalog.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

public class AtomicCatalog {
    record Catalog(List<String> items) {
        Catalog {
            items = List.copyOf(items);
        }
    }

    static final class Store {
        private final AtomicReference<Catalog> catalog =
                new AtomicReference<>(new Catalog(List.of()));

        void add(String item) {
            catalog.updateAndGet(old -> {
                List<String> next = new ArrayList<>(old.items());
                next.add(item);
                return new Catalog(next);
            });
        }

        Catalog snapshot() {
            return catalog.get();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Store store = new Store();

        Thread a = new Thread(() -> store.add("A"));
        Thread b = new Thread(() -> store.add("B"));
        a.start();
        b.start();
        a.join();
        b.join();

        List<String> printed = new ArrayList<>(store.snapshot().items());
        Collections.sort(printed);
        System.out.println("Items: " + printed);
        System.out.println("Count: " + printed.size());
    }
}
```

```bash
javac AtomicCatalog.java
java AtomicCatalog
```

Kết quả:

```text
Items: [A, B]
Count: 2
```

`AtomicReference.updateAndGet` cập nhật atomically theo hợp đồng, và **hàm cập nhật có thể được đánh giá lại** trong trường hợp CAS bị tranh chấp. Vì thế lambda chỉ tạo list **local**, không sửa snapshot cũ và không gây side effect bên ngoài. Khi hai thread cùng thêm A và B, kết quả đã commit bao gồm cả hai phần tử. Thứ tự thêm phụ thuộc lịch chạy; chương trình sắp xếp **một bản sao để in ra kết quả ổn định**, không sắp xếp snapshot đã công bố.

Nếu danh sách rất lớn và số lượt cập nhật nhiều, copy-on-write có chi phí cấp phát và sao chép O(n) cho mỗi lần thêm. Khi đó một concurrent collection phù hợp hoặc khóa bảo vệ cấu trúc mutable có thể hiệu quả hơn.

**Không làm thế này:**

```java
// Trích đoạn PHẢN VÍ DỤ: lambda có side effect bên ngoài.
state.updateAndGet(old -> {
    sendEmail(); // Có thể thực thi lại nếu có retry.
    return transform(old);
});
```

Đoạn trên giả định `state`, `sendEmail`, `transform` tồn tại. Vì lambda có thể chạy lại, gửi email trong nó có thể bị lặp dù chỉ một cập nhật thắng CAS. Để tránh, tính snapshot mới bằng hàm thuần, commit trước, rồi thiết kế side effect với idempotency, transaction hoặc cơ chế phục hồi riêng. Chuyển side effect ra sau CAS **không tự bảo đảm** atomicity của side effect với commit JVM khi process có thể lỗi.

## 9. Hiệu ứng bộ nhớ và safe publication theo JMM

`AtomicReference.get()` có hiệu ứng bộ nhớ như một lần **đọc volatile**; `set()` như một lần **ghi volatile**; `compareAndSet()` thành công có hiệu ứng đọc/ghi volatile theo hợp đồng API. Khi writer xây dựng `new State(...)` hoàn chỉnh rồi công bố qua thao tác atomic, reader nhận tham chiếu với `get()` có thể dựa trên quan hệ đồng bộ hóa **happens-before** tương ứng để thấy các trường đã được tạo đúng cách.

Nhưng hãy phân biệt:

- **Hiển thị/publish:** reader thấy các field đã được khởi tạo trong snapshot.
- **Không có mutation tiếp theo:** snapshot immutable bảo vệ reader khỏi thay đổi sâu.
- **Không mất cập nhật:** writer dùng CAS loop thay vì `get()` rồi `set()` đơn thuần.

Nếu thiếu một trong ba, kết quả có thể sai. Việc thấy các field của `State` là `final` giúp bảo đảm khởi tạo đúng cách theo JMM, **không** làm các object mutable trỏ tới trở nên bất biến. Không để `this` hoặc tham chiếu tới state đang khởi tạo thoát khỏi constructor trước khi hoàn tất.

Có thể dùng `volatile State current` để reader lấy **một snapshot** bằng phép đọc volatile nếu chỉ có một writer hoặc writer được phối hợp ngoài. Nhưng khi nhiều writer đều làm `newState = f(current); current = newState`, hai phép tính có thể cùng dựa trên state cũ rồi overwrite nhau. CAS hoặc khóa là cần thiết khi muốn cập nhật hợp thành không mất thay đổi.

## 10. set(), getAndSet(), compareAndSet() và updateAndGet() khác gì?

| API | Hợp đồng chính | Khi nào phù hợp |
|---|---|---|
| `get()` | Lấy tham chiếu hiện hành với hiệu ứng đọc volatile. | Reader lấy **một** immutable snapshot để đọc nhiều field. |
| `set(next)` | Ghi một tham chiếu atomically với hiệu ứng ghi volatile. | Công bố một giá trị đã định; không tự bảo vệ tính toán từ current của nhiều writer. |
| `getAndSet(next)` | Thay tham chiếu và trả tham chiếu cũ như một thao tác nguyên tử. | Swap một tham chiếu giá trị đã chuẩn bị sẵn. |
| `compareAndSet(old, next)` | Chỉ thay nếu current **cùng reference** với old; trả boolean. | Check-then-act trên immutable snapshot với CAS loop. |
| `updateAndGet(fn)` | Biến đổi và commit state mới nguyên tử, trả giá trị mới. | Cập nhật thuần, lambda chịu được retry. |
| `getAndUpdate(fn)` | Tương tự nhưng trả state trước khi cập nhật. | Cần biết snapshot cũ của commit; lambda vẫn phải thuần. |

**Identity vs equality:** `AtomicReference.compareAndSet` so sánh object reference, không phải `equals()`. Nếu tự tạo một object `new State(...)` có cùng giá trị với state hiện tại rồi dùng làm expected, CAS có thể thất bại vì khác instance. Hãy truyền chính tham chiếu `old = state.get()` làm expected.

## 11. ABA: giá trị có thể quay lại mà CAS không biết lịch sử

**ABA problem**: Thread T1 đọc tham chiếu A; thread T2 đổi A → B → **trở lại chính tham chiếu A**; T1 gọi CAS(expected A, next) vẫn có thể thắng vì current lúc đó lại cùng A, mặc dù có thay đổi trung gian.

Điểm quan trọng: **cùng nội dung chưa phải cùng reference**. Nếu T2 tạo một instance A mới có component giống object A cũ nhưng identity khác, CAS với reference cũ không thắng. Một thiết kế **luôn tạo snapshot mới, không bao giờ tái công bố instance cũ** hạn chế kiểu ABA trên identity; tuy nhiên thuật toán nào cần phát hiện “đã có bất cứ update nào kể từ lúc đọc” thì vẫn cần thiết kế version rõ ràng.

Có thể thêm `version` tăng cùng mỗi snapshot, hoặc cân nhắc `AtomicStampedReference` nếu yêu cầu phát hiện thay đổi trung gian. Khi dùng version phải tính đến overflow và chính sách tái sử dụng. Không mặc định rằng CAS nguyên thủy có chức năng ghi nhớ lịch sử state.

## 12. Chi phí và bảo đảm tiến triển

CAS loop không giữ monitor chặn writer khác trong lúc tính snapshot; nó là kỹ thuật **optimistic concurrency**. Điều này hữu ích khi số lượt đọc cao, snapshot nhỏ, cập nhật ít hoặc tranh chấp vừa phải. Nhưng phải cân nhắc:

- **Retry:** dưới contention, một thread có thể CAS thất bại nhiều lần, tốn CPU.
- **Allocation/GC:** mỗi lần thử có thể tạo object mới; bản thất bại trở thành rác.
- **Copy-on-write:** snapshot chứa collection lớn có thể cần O(n) công việc và bộ nhớ cho mỗi update.
- **Fairness:** CAS không bảo đảm mỗi thread riêng lẻ hoàn thành trong một giới hạn thời gian.
- **Side effects:** các thao tác phải được thiết kế để retry an toàn, vì phép tính có thể chạy lại.

Dùng atomic reference không tự làm **toàn bộ thuật toán wait-free** hoặc bảo đảm liveness không giới hạn. Nếu state phức tạp hoặc phải gọi mã bên ngoài dài, một `synchronized`/`ReentrantLock` bao trùm invariant có thể đơn giản và dễ chứng minh đúng hơn. Chỉ tối ưu sau khi đo contention, latency và throughput thực tế.

## 13. Giới hạn atomicity: một reference không phải mọi tài nguyên

Gói hai field vào một immutable State chỉ làm nguyên tử **bộ giá trị mà reference đó trỏ đến**. Nó **không** tạo transaction cho:

- Hai `AtomicReference` **khác nhau** khi cập nhật lần lượt.
- Object mutable ở nơi khác không được đưa vào snapshot.
- Database, file, mạng hoặc tiến trình JVM khác.
- Tác dụng phụ của một lời gọi HTTP, gửi message, ghi audit log.

Nếu nghiệp vụ cần atomicity xuyên nhiều hệ thống, phải dựa trên transaction/constraint/idempotency/outbox hoặc giao thức nhất quán do hệ thống lưu trữ/tích hợp hỗ trợ. Một lock hoặc CAS trong JVM đơn lẻ không bảo đảm nhiều tiến trình khác tuân theo.

Ví dụ `AtomicAccounts` là một **sổ cái minh họa trong bộ nhớ**, không phải giao dịch ngân hàng thực. Việc ghép những yêu cầu khác nhau (ghi bền, rollback, retry yêu cầu khách hàng) đòi hỏi kiến trúc ngoài phạm vi `AtomicReference`.

## 14. So sánh các lựa chọn

| Tình huống | Công cụ phù hợp | Điều kiện/giới hạn |
|---|---|---|
| Tăng một bộ đếm | `AtomicInteger.incrementAndGet()` | Một phép cập nhật nguyên tử trên một biến. |
| Quota còn/đã dùng là một invariant nhiều field | `AtomicReference<ImmutableState>` + CAS hoặc monitor | Phải bảo vệ cả các phép đọc snapshot và mọi đường cập nhật. |
| Reader nhiều, writer ít, state nhỏ | Immutable snapshot + atomic reference | Đọc dễ và nhất quán, trả giá bằng allocation khi ghi. |
| Update nhiều field và có nhánh dài/phức tạp | `synchronized` hoặc `ReentrantLock` | Mọi đường truy cập cùng invariant cần dùng cùng khóa. |
| Map có các key độc lập | `ConcurrentHashMap` | Atomicity theo hợp đồng từng thao tác, không tự giao dịch nhiều key. |
| Chia sẻ danh sách đọc nhiều/ghi ít | Copy-on-write hoặc snapshot immutable | Tránh nếu danh sách rất lớn và writer cực nhiều. |
| State chia sẻ xuyên nhiều JVM | Transaction/conditional write của backend dữ liệu | CAS trong một JVM không bảo đảm toàn cục. |

**Chọn cơ chế dựa trên phạm vi invariant**. Nếu tất cả state liên quan vừa trong một immutable object và cập nhật có thể tính thuần, CAS hợp lý. Nếu state trải nhiều hệ thống hoặc cần thao tác không thể retry, mô hình cần một công cụ khác.

## 15. Checklist thiết kế một compound atomic state

1. **Viết invariant:** liệt kê tất cả field phải nhất quán với nhau.
2. **Đặt vào một State immutable:** record, class final, defensive copy và component immutable.
3. **Ẩn AtomicReference:** dùng `private final AtomicReference<State>`, không để caller tùy tiện `set()`.
4. **Reader chụp một lần:** `State snapshot = state.get()`, đọc mọi field từ cùng snapshot.
5. **Writer đọc–kiểm tra–tính:** tạo object mới từ snapshot đọc được, không sửa object cũ.
6. **CAS commit:** chỉ trả thành công khi `compareAndSet(old, next)` thành công.
7. **Retry đúng:** khi CAS thất bại phải đọc lại và kiểm tra lại điều kiện nghiệp vụ, không ghép state lỗi thời.
8. **Hàm biến đổi thuần:** không I/O, gửi email hoặc ghi vào state khác bên trong retry lambda.
9. **Rõ contract cho snapshot trả về:** snapshot có thể là phiên bản cũ ngay sau `get()`, dù nhất quán.
10. **Đo hiệu năng:** theo dõi retry, thời gian tính, lượng allocation và độ lớn snapshot.
11. **Kiểm thử invariant dưới cạnh tranh:** dùng latch/barrier tạo lịch xen kẽ, `join()` đợi worker, kiểm tra tổng số commit.
12. **Xử lý lỗi ngoài JVM riêng:** không giả định CAS commit đồng thời với database/message/file.

## 16. Câu hỏi tự kiểm tra

1. **Tại sao hai `AtomicInteger` không bảo vệ tổng bất biến hai field?** Mỗi biến atomic riêng, reader có thể thấy khoảng giữa hai cập nhật.
2. **Tại sao reader không nên gọi `state.get()` hai lần rồi ghép hai field?** Hai lần có thể đọc hai snapshot khác phiên bản.
3. **CAS trên `AtomicReference` so sánh `==` hay `equals()`?** So sánh identity reference (`==`).
4. **Nếu CAS thất bại, có thể gọi `state.set(next)` của lần thử cũ không?** Không, vì có thể ghi đè kết quả writer khác.
5. **Vì sao `updateAndGet` nên nhận lambda không side effect?** Lambda có thể được gọi lại do retry.
6. **Có thể sửa `ArrayList` bên trong record có field final mà vẫn coi state immutable không?** Không; cần tránh mutable alias, dùng defensive copy và immutable component.
7. **CAS vừa thắng có nghĩa snapshot luôn mới nhất cho tới khi caller xử lý xong không?** Không; writer khác có thể thay ngay sau đó.
8. **CAS có làm database và JVM thành một transaction không?** Không, cần cơ chế riêng của hệ thống lưu trữ.
9. **ABA nghĩa là gì?** Reference A đổi sang B rồi quay về **chính A**, CAS chỉ dựa identity có thể không nhận ra lịch sử.
10. **Khi nào khóa có thể phù hợp hơn CAS?** State phức tạp, side effect khó retry, snapshot copy tốn kém hoặc contention lớn.

**Ghi nhớ:** nếu nhiều trường thuộc cùng invariant, hãy công bố **một immutable State qua một AtomicReference**, dùng **CAS** để commit các thay đổi hợp thành, và cho reader lấy **một snapshot duy nhất**. Không mutate snapshot cũ; retry phải được thiết kế thuần; đồng bộ trong JVM không tự thay thế transaction bên ngoài.
