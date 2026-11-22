# Encapsulation của trạng thái cần đồng bộ trong Java

## 1. Tại sao encapsulation là nền tảng của thread safety?

**Encapsulation** (đóng gói) là việc một đối tượng giữ quyền kiểm soát trạng thái của mình và chỉ cho phép bên ngoài tác động thông qua các thao tác có hợp đồng rõ ràng. Trong lập trình đồng thời Java, đóng gói còn là cách bảo đảm **mọi truy cập có khả năng xung đột đều tuân theo cùng một quy tắc đồng bộ**.

Một class có thể đặt trường ở mức `private` nhưng **chưa chắc thread-safe**. Nếu getter trả về chính đối tượng mutable bên trong, caller có thể sửa nó mà không đi qua lock. Nếu có phương thức khóa khi ghi nhưng đọc dữ liệu chung không qua cơ chế đồng bộ phù hợp, class vẫn có thể có data race hoặc đọc trạng thái thiếu nhất quán.

Mục tiêu không đơn thuần là “bọc `synchronized` vào mọi phương thức”. Mục tiêu là:

1. Xác định **bất biến (invariant)** của trạng thái: ví dụ tồn kho không âm; tổng tiền trong hai ví vẫn bảo toàn; danh sách chỉ được sửa qua một API.
2. Xác định **ai sở hữu trạng thái mutable** và ai có thể đọc/ghi nó.
3. Đặt **toàn bộ thao tác liên quan đến cùng bất biến** dưới một giao thức bảo vệ phù hợp: khóa chung, primitive atomic, immutable state thay nguyên tử hoặc thread confinement.
4. Không để tham chiếu mutable hoặc quyền thao tác lên lock thoát ra ngoài theo cách phá vỡ giao thức đó.
5. Công bố kết quả, snapshot hoặc dữ liệu trao đổi với thread khác bằng quan hệ happens-before phù hợp.

Đây là chủ đề Java concurrency nói chung. Các kỹ thuật trong bài dùng Java 17+ và API JDK tiêu chuẩn.

## 2. State, invariant và synchronization policy

Một **state** là tập dữ liệu mà hành vi của đối tượng phụ thuộc vào. State có thể nằm trong các trường primitive, object tham chiếu, collection hoặc các object lồng nhau.

**Invariant** là điều kiện phải luôn đúng ở các điểm mà trạng thái được xem là hợp lệ. Ví dụ:

- `remaining >= 0` đối với kho không cho bán quá số lượng.
- `fromBalance + toBalance == total` trong một lần chuyển tiền nội bộ.
- Một mã định danh chỉ có một bản ghi đang hoạt động.
- Các trường `name` và `version` của một snapshot phải thuộc cùng lần cập nhật.

**Synchronization policy** là quy ước để mọi truy cập liên quan tuân thủ, chẳng hạn “mọi đọc/ghi hai trường tiền phải giữ `lock` của đối tượng”, hoặc “trạng thái được công bố dưới dạng immutable snapshot qua `AtomicReference`”.

Một class muốn thực sự đóng gói tính thread-safe phải kiểm soát được **đường vào trạng thái**. Chỉ một phương thức bỏ qua policy là có thể làm mất bảo đảm của toàn bộ đối tượng.

### Phạm vi bất biến quyết định phạm vi khóa

Nếu `quantity` và `reserved` phải thỏa `quantity >= reserved`, hai phép cập nhật trên hai `AtomicInteger` riêng **chưa** bảo đảm bất biến liên trường ở mọi thời điểm đọc. Nếu cần thay hai trường như một đơn vị logic, có thể:

- Bảo vệ cả hai dưới **cùng một lock** và cung cấp phương thức cập nhật/snapshot đồng bộ.
- Lưu toàn bộ state trong một immutable object rồi thay tham chiếu bằng `AtomicReference.compareAndSet(...)`, tính toán lại khi CAS thất bại.
- Dùng một chủ sở hữu thread duy nhất và gửi thông điệp đến chủ sở hữu, nếu mô hình ứng dụng phù hợp.

Không nên chọn số lượng khóa hoặc số lượng trường atomic chỉ theo số trường dữ liệu. Hãy bắt đầu từ bất biến cần được bảo vệ.

## 3. Những dạng “rò rỉ trạng thái” thường gặp

### 3.1. Getter trả về tham chiếu mutable nội bộ

Tạo tệp `EscapedList.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class EscapedList {
    private final List<String> items = new ArrayList<>();

    public synchronized void add(String item) {
        items.add(item);
    }

    public synchronized int size() {
        return items.size();
    }

    // Lỗi thiết kế: trả ra chính list mutable đang được bảo vệ.
    public synchronized List<String> items() {
        return items;
    }

    public static void main(String[] args) {
        EscapedList store = new EscapedList();
        store.add("A");

        List<String> leaked = store.items();
        leaked.clear(); // Bỏ qua mọi phương thức đồng bộ của store.

        System.out.println("Store size: " + store.size());
    }
}
```

Chạy trên Java 17+:

```bash
javac EscapedList.java
java EscapedList
```

Đầu ra:

```text
Store size: 0
```

Đoạn mã chạy tuần tự đã đủ chứng minh lỗi **mất quyền kiểm soát state**: caller xóa dữ liệu mà không qua API `add` hoặc một chính sách chỉnh sửa nào của store. Khi có nhiều thread, hành động `leaked.clear()` có thể xảy ra song song với `add()`/`size()`. Việc `items()` có khóa chỉ bảo vệ **thời điểm trả tham chiếu**; sau khi phương thức kết thúc, tham chiếu vẫn trỏ tới chính list nội bộ.

**Sửa:** giữ list private và chỉ trả về một bản sao phù hợp; cung cấp các thao tác đọc/ghi có đồng bộ trên đối tượng sở hữu state.

### 3.2. Getter trả về mảng, map hoặc object mutable

Các mẫu nguy hiểm về mặt thiết kế:

```java
// Ví dụ minh họa, các trường được giả sử đã khai báo.
public byte[] buffer() { return internalBuffer; }
public Map<String, String> entries() { return mutableMap; }
public MutableConfig config() { return internalConfig; }
```

Trả về tham chiếu cho phép caller viết vào object nội bộ mà class không quan sát hay đồng bộ đúng. `private final byte[] internalBuffer` cũng **không bảo vệ nội dung mảng**: `final` chỉ ngăn gán lại tham chiếu trường, không làm mảng bất biến.

Nếu cần trao đổi dữ liệu mutable, cân nhắc sao chép khi **nhận vào** và **trả ra**, sử dụng value object bất biến, hoặc chuyển quyền sở hữu một cách rõ ràng. Kể cả constructor nhận `List` từ caller, lưu thẳng tham chiếu đó có thể khiến caller vẫn có quyền sửa state về sau.

### 3.3. Unmodifiable view không phải immutable snapshot

`Collections.unmodifiableList(backingList)` tạo một view không cho sửa qua view, nhưng **backing list vẫn thay đổi được** nếu chủ sở hữu hoặc tham chiếu khác sửa nó. Vì vậy, view này có thể phản ánh các thay đổi tương lai và không thay thế việc chụp snapshot trong một lock.

`List.copyOf(source)` tạo danh sách không chỉnh sửa được và không phản ánh thêm/xóa phần tử sau đó từ source. Nhưng nó là **shallow copy**: nếu phần tử là các object mutable, caller vẫn có thể sửa nội dung object đó. Ngoài ra, `List.copyOf` không chấp nhận phần tử null.

Đối với `List<String>`, chuỗi bất biến giúp ví dụ snapshot trở nên đơn giản. Với object mutable phức tạp, hãy chuyển sang DTO/value object bất biến hoặc sao chép sâu theo ngữ nghĩa miền dữ liệu khi cần.

## 4. Java 17+: encapsulation bằng API giữ nguyên invariant

Tạo tệp `SafeInventory.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class SafeInventory {
    private int remaining = 5;

    // Toàn bộ check và decrement nằm trong cùng critical section.
    public synchronized boolean reserveOne() {
        if (remaining <= 0) {
            return false;
        }
        remaining--;
        return true;
    }

    public synchronized int available() {
        return remaining;
    }

    public static void main(String[] args) throws InterruptedException {
        SafeInventory inventory = new SafeInventory();
        AtomicInteger accepted = new AtomicInteger();
        Thread[] workers = new Thread[12];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                if (inventory.reserveOne()) {
                    accepted.incrementAndGet();
                }
            }, "buyer-" + i);
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("Accepted: " + accepted.get());
        System.out.println("Remaining: " + inventory.available());
    }
}
```

Biên dịch và chạy:

```bash
javac SafeInventory.java
java SafeInventory
```

Đầu ra khi các worker hoàn tất bình thường:

```text
Accepted: 5
Remaining: 0
```

**Vì sao kết quả luôn đúng?**

- `remaining` là `private` và không có setter tự do; code bên ngoài chỉ có thể yêu cầu `reserveOne()` hoặc đọc `available()`.
- `reserveOne()` giữ monitor của chính đối tượng `inventory` trong suốt đoạn **kiểm tra còn hàng → trừ hàng**. Không thread nào khác có thể chen vào giữa hai bước này nếu cũng đi qua API của đối tượng.
- `available()` dùng **cùng monitor** để đọc giá trị, vì thế có quan hệ đồng bộ phù hợp với những lần cập nhật.
- Mười hai worker có thể được scheduling theo mọi thứ tự; chỉ năm lần reserve thành công. `AtomicInteger accepted` cho phép ghi nhận số lần chấp nhận từ nhiều thread mà không làm mất lượt.
- `join()` giúp `main` đợi tất cả worker trước khi in kết quả.

Trong class này, bất biến `remaining >= 0` được giữ đúng qua mỗi lần gọi API. **Điều kiện thiết kế** là không có đường khác chỉnh sửa `remaining` không tuân theo policy; một setter riêng lẻ không kiểm tra hoặc việc lộ tham chiếu tới state mutable sẽ phá vỡ bảo đảm.

### Check–then–act phải nằm trong cùng thao tác

Một API kiểu `available()` rồi `reserveOne()` là an toàn nếu caller **không giả định** kết quả `available()` trước đó sẽ vẫn đúng. Chỉ `reserveOne()` mới là điểm quyết định chấp nhận/từ chối. Nếu thay bằng hai phương thức `hasStock()` và `decrement()` không ràng buộc, hai caller có thể đều qua check rồi cùng giảm số lượng. Một khóa riêng cho từng phương thức **không đủ** để biến tổ hợp do caller thực hiện thành nguyên tử.

Cách thiết kế tốt là **đưa thao tác nghiệp vụ cần atomic vào cùng phương thức của đối tượng sở hữu state**.

## 5. Lock nội bộ, policy nhất quán và khả năng giữ kiểm soát

`synchronized` instance method khóa monitor của `this`. Điều này đúng với ví dụ `SafeInventory` nhưng bất kỳ code nào có tham chiếu đến đối tượng cũng có thể viết `synchronized (inventory)`, gây tranh chấp hoặc giữ lock ngoài dự kiến. Khi muốn kiểm soát lock rõ hơn, dùng **private lock object**:

```java
final class Counter {
    private final Object lock = new Object();
    private int value;

    public void increment() {
        synchronized (lock) {
            value++;
        }
    }

    public int get() {
        synchronized (lock) {
            return value;
        }
    }
}
```

Đây là class phụ trợ có thể biên dịch trong một file chứa class không public, không có `main`. `lock` không được trả ra ngoài, không gán lại và không dùng để đồng bộ cho những đối tượng không liên quan. Với cùng lock, mọi lần cập nhật và đọc `value` được bảo vệ, và monitor unlock/lock tạo quan hệ happens-before thích hợp.

Các quy tắc quan trọng:

1. **Ghi rõ state nào lock nào bảo vệ.** Nếu có nhiều lock, phải rõ mỗi invariant phụ thuộc những trường nào; đừng khóa riêng từng trường rồi tưởng có snapshot nhất quán liên trường.
2. **Bảo vệ cả đường đọc và đường ghi.** Đọc không khóa một biến đang bị thread khác ghi có thể tạo data race; getter tuy đơn giản vẫn phải theo policy hoặc dùng dữ liệu đã publish an toàn.
3. **Giữ lock đủ lâu để bảo vệ invariant**, rồi thả càng sớm càng tốt. Không cố tình mở khóa giữa check và update.
4. **Tránh callback không kiểm soát trong critical section.** Callback có thể gọi lại API, chờ I/O, giữ lock khác hoặc tạo chu trình deadlock.
5. **Không xuất bản lock nội bộ.** Trả `lock`, lấy một đối tượng công khai làm monitor hoặc dùng chuỗi literal làm lock làm giảm khả năng kiểm soát tranh chấp.
6. **Tài nguyên bên ngoài cần giao thức riêng.** Monitor trong một JVM không bảo vệ một database, file hay service có thể bị tiến trình/JVM khác thay đổi.

### `volatile` và `AtomicInteger` không thay thế mọi lock

`volatile` tạo một số bảo đảm visibility/ordering, thích hợp với cờ đơn giản theo giao thức rõ ràng, nhưng `count++` trên `volatile int` vẫn không atomic. `AtomicInteger.incrementAndGet()` phù hợp với một bộ đếm độc lập; nhiều biến atomic riêng không tạo một transaction bao phủ invariant giữa chúng.

Ngược lại, việc dùng lock cho mọi trường đơn lẻ cũng chưa chắc cần thiết. Trạng thái bất biến hoặc confined trong một thread không đòi lock ở mọi phép đọc. Chọn cơ chế theo điều kiện chia sẻ và invariant thực sự.

## 6. Encapsulation khi trả snapshot cho caller

Nếu caller muốn xem nội dung collection, đừng trả thẳng mutable backing collection. Có thể tạo snapshot **trong vùng đã khóa** rồi công bố snapshot bất biến ra ngoài.

Tạo tệp `SnapshotStore.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SnapshotStore {
    private final Object lock = new Object();
    private final List<String> items = new ArrayList<>();

    public void add(String value) {
        synchronized (lock) {
            items.add(value);
        }
    }

    public List<String> snapshot() {
        synchronized (lock) {
            return List.copyOf(items);
        }
    }

    public static void main(String[] args) {
        SnapshotStore store = new SnapshotStore();
        store.add("A");

        List<String> oldSnapshot = store.snapshot();
        store.add("B");

        System.out.println("Old: " + oldSnapshot);
        System.out.println("Current: " + store.snapshot());

        try {
            oldSnapshot.add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("Snapshot is read-only");
        }
    }
}
```

Chạy:

```bash
javac SnapshotStore.java
java SnapshotStore
```

Đầu ra:

```text
Old: [A]
Current: [A, B]
Snapshot is read-only
```

**Phân tích:**

- `snapshot()` giữ cùng `lock` mà `add()` dùng, nên bản sao được tạo trong một thời điểm logic nhất quán với các thao tác sửa của store.
- `List.copyOf(items)` trả danh sách không chỉnh sửa được, tách riêng cấu trúc phần tử khỏi những lần thêm/xóa về sau của `items`.
- `oldSnapshot` không tự biến thành `[A, B]` sau khi store thay đổi; caller không thể thực hiện `add()` trên snapshot.
- Phần tử ở đây là `String` bất biến. Nếu mỗi phần tử là `MutableOrder`, `List.copyOf` **không sao chép sâu** các order; vẫn phải thiết kế riêng việc chụp bất biến của từng phần tử.

**Chi phí:** snapshot tốn thời gian và bộ nhớ theo số phần tử; nếu dữ liệu lớn, tần suất đọc cao hoặc cần stream nhiều bản ghi, cần cân nhắc pagination, read-only interface có hợp đồng phù hợp, copy-on-write hoặc cách truyền dữ liệu khác. Một snapshot nhất quán có thể đáng giá hơn chi phí sao chép khi nó ngăn việc lộ state.

### Defensive copy cả lúc nhận dữ liệu vào

Một constructor chỉ viết `this.items = input` có thể giữ tham chiếu tới collection mà caller vẫn quản lý. Nếu mục tiêu là sở hữu dữ liệu, có thể tạo `new ArrayList<>(input)` hoặc `List.copyOf(input)` theo nhu cầu mutable/immutable. **Nhớ copy lúc vào và lúc ra** nếu cả hai hướng đều có thể làm state bị sửa ngoài giao thức.

## 7. Invariant gồm nhiều trường: một snapshot phải đồng bộ với cập nhật

Tạo tệp `AccountBookDemo.java`:

```java
public class AccountBookDemo {
    record Balances(int from, int to) {
        int total() {
            return from + to;
        }
    }

    private static final class AccountBook {
        private int from = 100;
        private int to = 0;

        public synchronized boolean transfer(int amount) {
            if (amount <= 0 || amount > from) {
                return false;
            }
            from -= amount;
            to += amount;
            return true;
        }

        public synchronized Balances snapshot() {
            return new Balances(from, to);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AccountBook book = new AccountBook();
        Thread first = new Thread(() -> book.transfer(30));
        Thread second = new Thread(() -> book.transfer(20));

        first.start();
        second.start();
        first.join();
        second.join();

        Balances result = book.snapshot();
        System.out.println(result);
        System.out.println("Total: " + result.total());
    }
}
```

Chạy với Java 17+ (có hỗ trợ `record`):

```bash
javac AccountBookDemo.java
java AccountBookDemo
```

Đầu ra:

```text
Balances[from=50, to=50]
Total: 100
```

Hai thread có thể gọi `transfer` theo thứ tự bất kỳ nhưng **mỗi lần chuyển được thực hiện trong cùng monitor**. Một lần chuyển không để lộ trạng thái trung gian từ khi trừ `from` đến khi cộng `to` cho caller dùng API đồng bộ. Phương thức `snapshot()` giữ monitor đó để sao chép **cùng lúc** hai giá trị vào immutable `record Balances`. Caller không thể sửa trực tiếp `from` và `to`.

Nếu viết hai getter `getFrom()` và `getTo()` đều synchronized nhưng caller gọi tách rời, một transfer có thể diễn ra **giữa hai lời gọi**. Hai kết quả mỗi cái đúng tại thời điểm đọc vẫn có thể không tạo cùng một snapshot. Khi invariant đi qua nhiều trường, nên trả về một snapshot được chụp trong **một** critical section.

Ví dụ sử dụng số nguyên nhỏ để tập trung vào concurrency; khi xử lý tiền thật còn cần kiểu tiền và quy tắc nghiệp vụ phù hợp. Lock trong ví dụ chỉ bảo vệ trạng thái của một đối tượng `AccountBook` trong JVM, không là giao dịch liên hệ thống.

## 8. Safe publication và ownership của object

Ngay cả một class có tất cả phương thức đồng bộ, quá trình **tạo và công bố tham chiếu** cũng cần được xét. Đừng cho `this` “thoát ra” trước khi constructor hoàn tất, ví dụ khởi động thread giữ tham chiếu `this` từ constructor hoặc đăng ký callback vào một đối tượng bên ngoài khi state chưa sẵn sàng.

`final` có quy tắc JMM đặc biệt trong quá trình khởi tạo đúng, nhưng `final List<?>` chỉ giữ cố định **tham chiếu** và không làm các phần tử hoặc nội dung list trở thành bất biến. Một object đã tạo xong có thể được trao qua `Thread.start()`, `BlockingQueue`, `volatile`/`AtomicReference`, `synchronized` hoặc các cơ chế khác có memory-consistency guarantees phù hợp.

**Thread confinement:** nếu toàn bộ state mutable chỉ được truy cập bởi một thread sở hữu, có thể không cần lock cho state đó. Các thread khác gửi thông điệp/tác vụ đến owner thay vì trực tiếp viết state. Điều kiện là không có tham chiếu mutable bị chia sẻ ngoài dự định.

**Immutable state:** nếu object không có mutable state sau khi tạo đúng cách và tham chiếu được công bố an toàn, nhiều reader có thể dùng nó mà không phải khóa cho từng lần đọc. Điều này thường giúp code dễ suy luận hơn.

**Shared mutable state:** nếu nhiều thread được phép thay đổi object, policy đồng bộ phải được chỉ định theo object sở hữu state và thực thi ở mọi API liên quan.

## 9. API “thread-safe” không có nghĩa mọi tổ hợp API đều atomic

Một collection concurrent thường chỉ bảo đảm những thao tác được mô tả trong hợp đồng của nó. Ví dụ dùng `ConcurrentHashMap`:

```java
// Minh họa: map đã là ConcurrentHashMap<String, String>.
if (!map.containsKey("job-1")) {
    map.put("job-1", "running");
}
```

Đây là **snippet không độc lập**. Dù `containsKey` và `put` thread-safe khi gọi riêng, hai thread có thể cùng thấy key chưa tồn tại và cùng quyết định đăng ký. Nếu invariant là “chỉ một người đăng ký”, phải dùng `putIfAbsent` hoặc một thao tác atomic theo key phù hợp.

Tương tự, các phương thức riêng lẻ `size()` và `remove()` của một wrapper synchronized không tự biến chuỗi `if (size() > 0) remove()` thành atomic đối với các thread khác. Nếu cần hành động có điều kiện, hãy **đóng gói cả check và act** vào một API của chủ sở hữu state và bảo vệ trọn đoạn đó.

### Các callback và hàm do caller cung cấp

Một API nhận `Consumer`, `Function` hoặc comparator từ caller có thể gián tiếp chạy mã tùy ý khi đang giữ lock. Callback có thể chặn I/O, gọi lại chính đối tượng, cố lấy lock khác hoặc gây deadlock. Hãy xác định rõ callback được chạy trong hay ngoài critical section và đánh giá tính đúng đắn nếu chạy trên một snapshot ngoài lock.

Ví dụ, “copy snapshot dưới lock rồi áp dụng callback ngoài lock” thường tránh chạy code lạ khi giữ lock; nhưng chỉ đúng khi thao tác thực sự cho phép làm việc trên snapshot cũ. Nếu callback phải cập nhật chính state dựa trên điều kiện vừa đọc, việc thả lock trước khi ghi có thể lại tạo TOCTOU. Không có một lựa chọn mặc định phù hợp mọi invariant.

## 10. Encapsulation giúp bảo đảm đồng bộ ở ranh giới nào?

| Phạm vi | Encapsulation/lock Java có thể bảo vệ? | Ghi chú |
| --- | --- | --- |
| Nhiều thread cùng dùng một instance trong một JVM | Có, khi mọi đường truy cập tuân theo policy | Cùng lock hoặc primitive atomic phù hợp |
| Nhiều instance, mỗi instance có lock riêng | Chỉ state của từng instance | Không bảo vệ shared static state nếu policy khác |
| Nhiều JVM/process truy cập cùng file | Không tự động | Cần cơ chế nguyên tử/lock của hệ thống tệp phù hợp |
| Nhiều ứng dụng cập nhật cùng nơi lưu trữ | Không tự động | Cần transaction/conditional update/unique constraint tại nguồn chân lý |
| Snapshot immutable đã công bố an toàn | Thường không cần khóa khi chỉ đọc | Không được chứa hoặc để lộ mutable element thiếu bảo vệ |

Một biến `static` mutable có thể được tất cả instance cùng chia sẻ. Nếu mỗi instance dùng `synchronized` trên `this` để bảo vệ biến static, các instance có **monitor khác nhau** và không loại trừ lẫn nhau. Khi cần bảo vệ state static chia sẻ, phải chọn một policy chung tương ứng với phạm vi state đó.

## 11. Các sai lầm thường gặp

- **“Trường private đồng nghĩa thread-safe.”** Sai khi API vẫn trả tham chiếu mutable, callback lộ state hoặc truy cập khác bỏ qua policy.
- **“Thêm synchronized vào getter list là đủ.”** Sai nếu getter trả backing list; caller tiếp tục sửa ngoài lock.
- **“final làm list hoặc mảng bất biến.”** Sai: final cố định tham chiếu trường; nội dung object vẫn có thể mutable.
- **“unmodifiableList là bản sao không đổi.”** Sai: view không cho sửa qua nó nhưng backing collection có thể thay đổi.
- **“List.copyOf sao chép sâu mọi phần tử.”** Sai: nó sao chép cấu trúc list, không tự sao chép object mutable ở từng phần tử.
- **“Đã synchronized từng getter nên snapshot nhiều trường nhất quán.”** Sai nếu các getter chạy trong hai critical section riêng và có update ở giữa.
- **“Đã dùng volatile/atomic cho từng field nên invariant nhiều field luôn đúng.”** Sai nếu cần nguyên tử tính giữa các trường.
- **“Chỉ khóa writer là đủ.”** Sai nếu reader đọc cùng state không có giao thức visibility/ordering phù hợp.
- **“Một lock private giải quyết được sửa đổi từ service khác.”** Sai: monitor chỉ phối hợp những thread dùng monitor đó trong JVM.
- **“Gọi callback trong synchronized luôn an toàn.”** Không hẳn: callback không kiểm soát có thể kéo dài thời gian giữ lock hoặc tạo vòng chờ.
- **“Đặt Thread.sleep trong critical section giúp thread khác kịp cập nhật.”** Sai: sleep không nhả monitor và không làm thuật toán tự an toàn.

## 12. Checklist thiết kế class thread-safe

1. **Liệt kê state và invariant:** những trường nào liên quan nhau, giá trị hợp lệ là gì, ai được quyền sửa?
2. **Chỉ định chủ sở hữu:** có một đối tượng kiểm soát cập nhật hay state bị chia sẻ ngoài ý muốn?
3. **Định nghĩa synchronization policy:** cùng lock cho mọi truy cập có liên quan, atomic cho phép cập nhật đơn, hoặc immutable/thread-confined state?
4. **Kiểm tra API vào/ra:** constructor có giữ tham chiếu mutable của caller không? Getter có trả object/mảng/map/list nội bộ không?
5. **Đóng gói thao tác nghiệp vụ:** check–then–act hoặc read–modify–write cần atomic nên nằm trong một phương thức được bảo vệ.
6. **Đảm bảo snapshot nhất quán:** khi nhiều trường tạo thành một invariant, sao chép chúng trong cùng critical section thành immutable result.
7. **Xem xét callback và vòng đời:** không để `this` escape khi chưa khởi tạo xong, hạn chế chạy code lạ và chờ I/O trong khi giữ lock.
8. **Kiểm tra khả năng mở rộng:** đo contention, chi phí copy snapshot, độ dài critical section; không đổi đúng đắn lấy hiệu năng dự đoán.
9. **Kiểm thử các lịch xen kẽ:** dùng nhiều worker, `CountDownLatch`, invariant assertions và stress test; việc chạy qua vài lần không chứng minh không có race.
10. **Giữ đúng phạm vi bảo đảm:** lock cục bộ không tự bảo vệ process khác hoặc nguồn dữ liệu bên ngoài.

**Ghi nhớ:** thread safety là thuộc tính của **toàn bộ giao thức truy cập trạng thái**, không phải của từ khóa `private` hay một vài phương thức `synchronized` đứng riêng lẻ. Encapsulation hiệu quả giữ quyền cập nhật bên trong đối tượng, bảo vệ cùng một invariant bằng chính sách đồng bộ nhất quán và chỉ công bố dữ liệu cho bên ngoài qua những API không làm lộ mutable state.