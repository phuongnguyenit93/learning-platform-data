# Trạng thái dùng chung khó kiểm soát: nhận diện, cô lập và bảo vệ trong Java OOP

> **Chủ đề:** OOP → Lỗi thiết kế → Trạng thái dùng chung khó kiểm soát.  
> **Mục tiêu:** Hiểu *shared mutable state* là gì và vì sao nó làm đối tượng khó dự đoán; phân biệt chia sẻ dữ liệu với chia sẻ quyền sửa dữ liệu; nhận diện rò rỉ tham chiếu, `static` mutable, singleton có trạng thái và race condition; lựa chọn encapsulation, immutable snapshot, stateless service, đồng bộ hoặc transaction đúng phạm vi.

## 1. Vấn đề thực sự: cùng một trạng thái, nhiều nơi có quyền sửa

Giả sử hệ thống bán vé còn **1 chỗ trống**. Hai yêu cầu đặt vé xuất hiện gần như cùng lúc:

1. Yêu cầu A đọc: còn 1 chỗ.
2. Yêu cầu B cũng đọc: còn 1 chỗ.
3. A quyết định đặt thành công.
4. B cũng quyết định đặt thành công.

Hệ thống có thể thông báo **hai lượt đặt thành công cho cùng một chỗ**, dù biến `reserved` cuối cùng chỉ lưu giá trị `1`. Đây không chỉ là lỗi phép cộng; quyết định kinh doanh đã dựa trên **trạng thái dùng chung mà không kiểm soát việc đọc–sửa–ghi**.

Một ví dụ khác không cần nhiều thread: lớp `Team` lưu `List<Member>` do caller truyền vào. Caller sau đó gọi `members.clear()`, khiến số thành viên của `Team` thay đổi **mà không gọi bất kỳ method nghiệp vụ nào của `Team`**. Đây cũng là shared mutable state, nhưng nguyên nhân là **aliasing** (nhiều tham chiếu cùng trỏ đến một object có thể thay đổi).

**Shared mutable state** là trạng thái có thể thay đổi và được nhiều chủ thể truy cập. Chủ thể có thể là nhiều object, nhiều module, nhiều request, nhiều thread hoặc nhiều tiến trình cùng đọc/ghi một bản ghi lưu trữ. Bản thân việc chia sẻ **không luôn xấu**; mùi thiết kế xuất hiện khi **không rõ ai sở hữu, ai được phép sửa, thao tác nào được xem là nguyên tử và các quy tắc nào cần giữ**.

### Phân biệt bốn tình huống

| Dữ liệu | Có chia sẻ? | Có thể đổi? | Nguy cơ chính |
|---|---|---|---|
| Hằng số `static final String APP_NAME` | Có | Không, nếu giá trị immutable | Thấp |
| `List.copyOf(...)` chứa `String` | Có thể | Không qua API của list; phần tử `String` bất biến | Thấp, nếu dữ liệu được phép chia sẻ |
| Một `ArrayList` được nhiều class cùng giữ tham chiếu | Có | Có | Sửa ngoài ý muốn, mất invariant |
| `int remaining` dùng chung cho nhiều thread | Có | Có | Lost update, stale read, check-then-act |
| Hàng tồn kho trong database dùng chung bởi nhiều ứng dụng | Có | Có | Ghi đè cạnh tranh, overselling, transaction không nhất quán |

**Hai câu hỏi then chốt:** *Trạng thái có thể đổi qua những con đường nào?* Và *mọi thay đổi có được kiểm soát theo cùng hợp đồng hay không?*

## 2. Vì sao lỗi này nguy hiểm trong OOP?

OOP cho phép nhiều đối tượng cùng tham chiếu một object:

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> shared = new ArrayList<>(List.of("READ"));

List<String> referenceA = shared;
List<String> referenceB = shared;

referenceA.add("WRITE");
System.out.println(referenceB); // [READ, WRITE]
~~~

`referenceA` và `referenceB` không phải hai danh sách độc lập; chúng là **hai biến trỏ đến cùng một instance**. Không cần sử dụng `static` hay đa luồng mới có tác động từ xa.

Nếu class công bố tham chiếu mutable nội bộ, client sẽ trở thành một người có quyền sửa trạng thái:

~~~java
final class UnsafeGroup {
    private final List<String> members;

    UnsafeGroup(List<String> members) {
        this.members = members; // Giữ alias từ bên ngoài.
    }

    List<String> members() {
        return members; // Lại đưa alias ra ngoài.
    }
}
~~~

Các lệnh sau làm object thay đổi ngoài kiểm soát:

~~~java
List<String> external = new ArrayList<>(List.of("Lan"));
UnsafeGroup group = new UnsafeGroup(external);

external.clear();           // Thay đổi từ đầu vào đã truyền.
group.members().add("Nam"); // Thay đổi qua getter.
~~~

Dù field `members` là `private final`, **nội dung của List vẫn sửa được**. `final` chỉ ngăn gán lại tham chiếu field, không biến đối tượng mà nó trỏ tới thành immutable.

### Các hậu quả thường gặp

- **Invariant bị phá vỡ:** `reserved > capacity`, số dư âm, collection thiếu dữ liệu bắt buộc.
- **Hành vi phụ thuộc thứ tự gọi:** kết quả thay đổi khi một method vô tình được gọi sớm hơn.
- **Bug khó tái hiện:** race chỉ xảy ra ở một lịch thực thi, khi tải cao.
- **Test ảnh hưởng nhau:** singleton/static state bị giữ từ test trước.
- **Rò rỉ giữa request hoặc người dùng:** field của service giữ thông tin request A rồi bị request B ghi đè.
- **Khó quan sát nguyên nhân:** nhiều nơi có khả năng ghi, không biết ai gây ra trạng thái bất hợp lệ.
- **Khó mở rộng nhiều node:** khóa trong một JVM không bảo vệ bản ghi được chia sẻ qua database.

Chỉ tăng số lượng unit test không giải quyết hết vấn đề nếu thiết kế vẫn cho phép sửa state từ mọi nơi.

## 3. Quy tắc sở hữu trạng thái và ranh giới thay đổi

Một đối tượng hoặc module nên có **chủ sở hữu trạng thái rõ ràng**. Bên ngoài yêu cầu một thao tác nghiệp vụ, còn chủ sở hữu quyết định xem thay đổi có hợp lệ:

~~~mermaid
flowchart LR
    C1["Client A"] -->|"reserve(1)"| Owner["SeatInventory: chủ sở hữu"]
    C2["Client B"] -->|"reserve(1)"| Owner
    Owner --> Rule{"capacity còn đủ?"}
    Rule -->|Có| Commit["Cập nhật có kiểm soát"]
    Rule -->|Không| Reject["Từ chối, không đổi state"]
    Owner --> Snapshot["Snapshot chỉ đọc"]
    Snapshot --> C1
    Snapshot --> C2
~~~

Đừng biến quy tắc “chỉ một nơi có quyền sửa” thành cấm mọi class khác **sử dụng** trạng thái. Client vẫn cần đọc một số thông tin, nhưng có thể đọc dưới dạng **snapshot bất biến**, getter có hợp đồng hoặc những query method phù hợp.

Một thiết kế tốt cho trạng thái quan trọng thường có:

1. **Representation private**: client không gán trực tiếp vào field nội bộ.
2. **Thao tác theo nghiệp vụ**: `reserve(1)` thay cho `setReserved(7)`.
3. **Hợp đồng và invariant rõ**: ví dụ `0 ≤ reserved ≤ capacity`.
4. **Tính nguyên tử đúng phạm vi**: check và update phải đi cùng nhau khi có truy cập đồng thời.
5. **Không rò rỉ alias mutable**: kiểm tra cả đường constructor, getter và phần tử lồng nhau.
6. **Kiểm thử đường từ chối**: khi thao tác không hợp lệ, state không được cập nhật một nửa.

## 4. Race condition: ví dụ Java 17 chạy độc lập và có thể tái hiện

Thay vì phụ thuộc may rủi của scheduler, ví dụ dùng `CountDownLatch` để **cố ý ép hai thread đọc cùng một state trước khi ghi**. Như vậy người học có thể nhìn thấy lỗi *lost update* rõ ràng.

### 4.1. Một implementation cố ý sai

Một chỗ trống, hai người cùng đặt. Ở thiết kế sai, cả hai thread cùng đọc `reserved = 0`, rồi mỗi thread ghi lại `observed + 1`:

~~~java
import java.util.concurrent.CountDownLatch;

final class UnsafeSeatGate {
    private final int capacity = 1;
    private int reserved;

    private final CountDownLatch bothRead = new CountDownLatch(2);
    private final CountDownLatch mayWrite = new CountDownLatch(1);

    boolean reserveOne() throws InterruptedException {
        int observed = reserved;

        if (observed >= capacity) {
            return false;
        }

        // Cố ý buộc cả hai request qua bước kiểm tra trước khi ghi.
        bothRead.countDown();
        mayWrite.await();

        reserved = observed + 1; // Ghi từ snapshot cũ.
        return true;
    }

    void letBothWrite() throws InterruptedException {
        bothRead.await();
        mayWrite.countDown();
    }

    int reserved() {
        return reserved;
    }
}
~~~

Đây là class **mô phỏng lỗi**, không dùng trong production. `CountDownLatch` không gây lỗi; nó chỉ cho ta tái hiện đúng lịch thực thi nguy hiểm.

### 4.2. Class bảo vệ invariant

Phần đúng phải biến “kiểm tra rồi cập nhật” thành **một thao tác không bị xen ngang bởi thread khác**:

~~~java
record SeatSnapshot(int capacity, int reserved) {
    SeatSnapshot {
        if (capacity <= 0 || reserved < 0 || reserved > capacity) {
            throw new IllegalArgumentException("Invalid snapshot");
        }
    }

    int available() {
        return capacity - reserved;
    }
}

final class SeatInventory {
    private final int capacity;
    private int reserved;

    SeatInventory(int capacity) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be > 0");
        }
        this.capacity = capacity;
    }

    // Cả phần kiểm tra và cập nhật đều nằm trong cùng monitor.
    synchronized boolean reserveOne() {
        if (reserved >= capacity) {
            return false;
        }
        reserved++;
        return true;
    }

    synchronized SeatSnapshot snapshot() {
        return new SeatSnapshot(capacity, reserved);
    }
}
~~~

Ở đây `SeatInventory` giữ `reserved` là `private`, không công bố setter và trả về **`SeatSnapshot` immutable**. `synchronized` trên cả `reserveOne()` và `snapshot()` giúp việc đọc/ghi nhất quán với monitor của chính instance đó.

### 4.3. Chương trình hoàn chỉnh để chạy

Gộp **cả ba đoạn dưới đây** vào **một tệp `SharedStateDemo.java`** theo thứ tự: import, hai class `UnsafeSeatGate`/`SeatInventory` cùng `SeatSnapshot` ở trên, rồi class `SharedStateDemo` bên dưới. Mỗi tệp Java chỉ có một class `public` mang tên tệp:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SharedStateDemo {
    public static void main(String[] args) throws Exception {
        var unsafe = new UnsafeSeatGate();
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<Boolean> a = pool.submit(unsafe::reserveOne);
            Future<Boolean> b = pool.submit(unsafe::reserveOne);

            // Chỉ nhả barrier sau khi cả hai đã đọc reserved = 0.
            unsafe.letBothWrite();

            int accepted = (a.get() ? 1 : 0) + (b.get() ? 1 : 0);

            System.out.println("Unsafe accepted = " + accepted);
            System.out.println("Unsafe reserved = " + unsafe.reserved());

            var safe = new SeatInventory(1);
            Future<Boolean> c = pool.submit(safe::reserveOne);
            Future<Boolean> d = pool.submit(safe::reserveOne);

            int safeAccepted = (c.get() ? 1 : 0) + (d.get() ? 1 : 0);
            System.out.println("Safe accepted = " + safeAccepted);
            System.out.println("Safe reserved = " + safe.snapshot().reserved());
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

**Khi tạo file thực**, đặt tất cả dòng `import` ở **đầu tệp** (không đặt import giữa các class). Vì các snippet trên chia theo khái niệm, phần `import java.util.concurrent.CountDownLatch;` và ba import trong `SharedStateDemo` cần được gom lên đầu tệp:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
~~~

Sau đó là `UnsafeSeatGate`, `SeatSnapshot`, `SeatInventory` và `public class SharedStateDemo`, **không lặp import ở giữa**.

Biên dịch và chạy:

~~~bash
javac SharedStateDemo.java
java SharedStateDemo
~~~

Kết quả có chủ đích:

~~~text
Unsafe accepted = 2
Unsafe reserved = 1
Safe accepted = 1
Safe reserved = 1
~~~

**Điều đáng chú ý:** Kết quả sai **không nhất thiết biểu hiện bằng `reserved > capacity`**. Ở đây `reserved` vẫn là `1`, nhưng hai yêu cầu đều nhận **thành công**. Bản ghi trạng thái không còn tương ứng với các quyết định nghiệp vụ đã công bố: lỗi *lost update*.

Với bản đúng, cùng một lúc chỉ một thread có thể chạy bên trong `reserveOne()` của **cùng instance `SeatInventory`**, nên request còn lại nhìn thấy `reserved = 1` và bị từ chối. `SeatSnapshot` cho phép đọc cặp `capacity/reserved` từ một thời điểm dưới khóa.

## 5. `volatile`, `synchronized` và atomic: khác nhau ở đâu?

Một hiểu lầm nguy hiểm là “thêm `volatile` vào `int` sẽ làm `count++` an toàn”.

~~~java
class WrongCounter {
    private volatile int count;

    void increment() {
        count++; // Đọc -> cộng -> ghi: KHÔNG nguyên tử.
    }

    int get() {
        return count;
    }
}
~~~

`volatile` trong Java tạo những bảo đảm về **visibility và ordering** theo Java Memory Model cho việc truy cập biến được đánh dấu; nó không biến chuỗi thao tác **đọc–sửa–ghi** thành một hành động nguyên tử. Hai thread vẫn có thể cùng đọc một giá trị cũ rồi ghi đè kết quả của nhau.

So sánh:

| Công cụ | Bảo đảm chính | Phù hợp | Chưa đủ cho |
|---|---|---|---|
| `private` | Hạn chế đường truy cập state ở mức ngôn ngữ | Encapsulation | Tự động thread-safe |
| `final` | Không gán lại field; có quy tắc công bố field đặc biệt trong JMM | Thiết kế state ổn định | Làm mutable object thành immutable |
| `volatile` | Visibility/order cho một biến; đọc/ghi của biến được truy cập volatile theo quy tắc JMM | Cờ dừng, trạng thái đơn giản | `count++`, check-then-act nhiều bước |
| `synchronized` | Mutual exclusion và happens-before qua cùng monitor | Bảo vệ một tập state và invariant có quan hệ | Nhiều JVM/DB hoặc hệ thống phân tán |
| `AtomicInteger` | Các thao tác nguyên tử như `incrementAndGet`, `compareAndSet` trên **một** giá trị | Bộ đếm, single-value state, CAS | Tự động giữ invariant qua nhiều object/bản ghi |
| `ReentrantLock` | Lock tường minh, `tryLock`, điều kiện chờ | Quy trình cần tính năng khóa nâng cao | Mọi bất biến nếu có đường truy cập không dùng cùng lock |
| Transaction/constraint DB | Kiểm soát nhất quán của dữ liệu lưu trữ theo DB/isolation | Nhiều request/node cùng sửa bản ghi | Tự bảo đảm mọi side effect ở hệ thống ngoài DB |

### AtomicInteger: đúng cho counter, chưa chắc đúng cho mọi điều kiện

~~~java
import java.util.concurrent.atomic.AtomicInteger;

final class RequestCounter {
    private final AtomicInteger count = new AtomicInteger();

    int markRequest() {
        return count.incrementAndGet();
    }

    int current() {
        return count.get();
    }
}
~~~

Đây là một bộ đếm đơn giản an toàn cho phép tăng nguyên tử, không cần tạo một lock riêng. Nhưng nếu có quy tắc “số vé đã đặt không vượt sức chứa”, làm:

~~~java
// KHÔNG AN TOÀN: check và increment là hai thao tác tách rời.
if (reserved.get() < capacity) {
    reserved.incrementAndGet();
}
~~~

vẫn có race condition. Có thể dùng **CAS loop** kiểm tra và cập nhật như một thao tác compare-and-set:

~~~java
final class AtomicSeatInventory {
    private final int capacity;
    private final java.util.concurrent.atomic.AtomicInteger reserved =
            new java.util.concurrent.atomic.AtomicInteger();

    AtomicSeatInventory(int capacity) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be > 0");
        }
        this.capacity = capacity;
    }

    boolean reserveOne() {
        while (true) {
            int current = reserved.get();
            if (current >= capacity) {
                return false;
            }
            if (reserved.compareAndSet(current, current + 1)) {
                return true;
            }
            // Thread khác vừa ghi; đọc lại trạng thái mới và thử lại.
        }
    }

    int reserved() {
        return reserved.get();
    }
}
~~~

Code trên bảo vệ một ràng buộc đơn giản trên **một giá trị `reserved`** với `capacity` bất biến. Nếu còn phải cập nhật `reserved`, `revenue` và lịch sử booking cùng lúc, không thể chỉ dùng ba AtomicInteger rồi mặc định chúng tạo một transaction nguyên tử. Cần xem **đơn vị nhất quán** thực sự gồm bao nhiêu trường/đối tượng.

## 6. Aliasing cũng là shared mutable state, ngay cả khi chỉ có một thread

Hai biến có thể trỏ đến **cùng một collection**, khiến một nơi thay đổi dữ liệu mà nơi khác không hề gọi phương thức nghiệp vụ. Bài này tập trung vào *quyền sở hữu của state dùng chung*; phân tích chi tiết các đường rò rỉ getter/constructor và defensive copy đã có ở bài *Trạng thái công khai và mất điều kiện bất biến*.

Xét một tập quyền của nhóm, dữ liệu được truyền từ caller:

~~~java
// Sai: nhóm giữ cùng List mà caller còn được sửa.
List<String> external = new ArrayList<>(List.of("READ"));

final class PermissionGroup {
    private final List<String> permissions;

    PermissionGroup(List<String> input) {
        this.permissions = input;
    }

    boolean has(String permission) {
        return permissions.contains(permission);
    }
}

PermissionGroup unsafe = new PermissionGroup(external);
external.add("ADMIN");
System.out.println(unsafe.has("ADMIN")); // true ngoài ý muốn
~~~

Ở đây không cần race condition: **alias đã mở một đường sửa state ngoài chủ sở hữu**. Sửa thiết kế bằng snapshot không sửa được khi nhận dữ liệu:

~~~java
final class SafePermissionGroup {
    private final java.util.List<String> permissions;

    SafePermissionGroup(java.util.List<String> input) {
        java.util.Objects.requireNonNull(input, "input");
        this.permissions = java.util.List.copyOf(input);
    }

    boolean has(String permission) {
        return permissions.contains(permission);
    }

    java.util.List<String> snapshot() {
        return permissions;
    }
}
~~~

`List.copyOf` bảo vệ **cấu trúc List** khỏi caller và ngăn sửa thông qua kết quả `snapshot()`; do phần tử là `String` bất biến nên đủ cho demo. Nếu phần tử mutable, snapshot này vẫn nông, phải xem lại ownership của từng phần tử. Shared immutable object hoặc snapshot an toàn không phải lỗi thiết kế: cái cần kiểm soát là **những ai còn quyền mutate cùng dữ liệu**.

## 7. `static` và Singleton: phạm vi chia sẻ rộng hơn ý muốn

Trong Java, field `static` thuộc về **class tương ứng trong phạm vi class loader**, không thuộc riêng từng instance. Nếu field đó mutable, nhiều đối tượng sử dụng class có thể cùng thấy và sửa nó:

~~~java
final class GlobalFlags {
    static boolean maintenanceMode = false;
}

// Một phần chương trình:
GlobalFlags.maintenanceMode = true;
// Phần khác đọc cùng biến trong cùng class-loader context.
~~~

Trong ứng dụng nhiều thread, field ở ví dụ trên còn thiếu bảo đảm visibility khi ghi/đọc không đồng bộ. Nếu chỉ là một cờ bật/tắt cần visibility giữa thread, có thể cân nhắc `volatile` hoặc `AtomicBoolean`, nhưng còn phải xác định quyền sửa và phạm vi tồn tại của cờ. Với cấu hình dùng chung bất biến, `static final` thường đơn giản hơn.

**`static` không đồng nghĩa “có một bản trên toàn bộ cluster”**. Nhiều JVM, nhiều class loader hoặc nhiều tiến trình có trạng thái tách biệt.

### Một singleton không tự động thread-safe

Singleton chỉ nói về cách quản lý instance trong một phạm vi, **không tự đồng bộ hóa field bên trong**.

~~~java
final class SessionTracker {
    // Một singleton toàn chương trình (minh họa ý tưởng).
    static final SessionTracker INSTANCE = new SessionTracker();

    private String lastUserId;

    private SessionTracker() {}

    void record(String userId) {
        lastUserId = userId;
    }

    String lastUserId() {
        return lastUserId;
    }
}
~~~

Nếu nhiều request gọi `record` đồng thời, giá trị `lastUserId` liên tục bị ghi đè và không thuộc về request nào cụ thể. `volatile` có thể giúp nhìn thấy cập nhật mới, nhưng không làm dữ liệu “thuộc đúng user” — **đây trước hết là lỗi mô hình sở hữu**.

Thay vì dùng singleton mutable để giữ thông tin request, hãy truyền `userId` như tham số hoặc tạo **request-scoped state** có vòng đời đúng.

## 8. Spring singleton service và rò rỉ trạng thái giữa request

Trong Spring, bean `@Service` thường có scope **singleton theo mặc định trong mỗi application context**. Nhiều HTTP request có thể gọi vào **cùng một instance** từ các thread khác nhau.

Ví dụ có vấn đề:

~~~java
// Ví dụ minh họa cho ứng dụng Spring, không thuộc JDK trần.
@org.springframework.stereotype.Service
class UnsafeCheckoutService {
    private String currentOrderId; // Request state nằm trên singleton!

    String prepare(String orderId) {
        currentOrderId = orderId;

        // Giữa các bước này request khác có thể ghi field.
        return "Processing " + currentOrderId;
    }
}
~~~

Hai request A/B có thể xen kẽ làm A đọc `orderId` của B. Đây là lỗi ngay cả khi field `currentOrderId` là `volatile` hoặc getter/setter được synchronized riêng, vì vấn đề là **nhiều request dùng chung một slot trạng thái**.

Thiết kế stateless đơn giản hơn:

~~~java
@org.springframework.stereotype.Service
class CheckoutService {
    String prepare(String orderId) {
        // Dữ liệu riêng của lời gọi nằm trong biến local.
        String validated = java.util.Objects.requireNonNull(orderId);
        if (validated.isBlank()) {
            throw new IllegalArgumentException("orderId is blank");
        }
        return "Processing " + validated;
    }
}
~~~

Biến local thuộc lần gọi method, không phải field mutable dùng chung của service. Một Spring singleton **có thể an toàn khi giữ các dependency thread-safe hoặc immutable**; không phải cứ singleton thì sai. Nếu service dùng shared cache, repository hoặc scheduler có state, tính đúng đắn vẫn phụ thuộc vào hợp đồng concurrency của chính các đối tượng cộng tác đó.

**Lưu ý về `ThreadLocal`:** Nó có thể giữ context theo thread nhưng không phải lựa chọn mặc định cho dữ liệu request. Thread pool tái sử dụng thread; nếu không dọn `remove()` ở đúng vòng đời, context có thể rò rỉ giữa tác vụ. Với xử lý bất đồng bộ, reactive hoặc virtual threads, cách truyền context cần phù hợp framework. Khi có thể, truyền context tường minh sẽ dễ kiểm soát hơn.

## 9. `ConcurrentHashMap` không tự biến mọi nghiệp vụ thành nguyên tử

Một collection concurrent bảo vệ một số thao tác, nhưng không bảo đảm một chuỗi thao tác của caller là nguyên tử.

~~~java
import java.util.concurrent.ConcurrentHashMap;

var counts = new ConcurrentHashMap<String, Integer>();

// Không an toàn để tăng đồng thời:
int oldValue = counts.getOrDefault("ORD-1", 0);
counts.put("ORD-1", oldValue + 1);
~~~

Hai thread có thể cùng đọc cùng `oldValue` và một update bị mất. Nếu thao tác chỉ cần cập nhật **một key** dựa trên giá trị hiện tại:

~~~java
counts.merge("ORD-1", 1, Integer::sum);
~~~

`ConcurrentHashMap.merge` thực hiện cập nhật nguyên tử cho mapping của key theo hợp đồng của collection. Nhưng không có nghĩa một phép cập nhật **nhiều key** hay cả database và email được thực hiện như một transaction.

Đồng thời, nếu value của map là `ArrayList` mutable, việc map thread-safe **không biến nội dung ArrayList thành thread-safe**. Rủi ro aliasing còn nguyên:

~~~java
// Một ConcurrentHashMap<String, List<String>> có thể
// được truy cập concurrent, nhưng các List bên trong vẫn
// cần hợp đồng cập nhật riêng hoặc thay bằng giá trị bất biến.
~~~

Đừng chỉ hỏi “dùng collection concurrent chưa?”; hãy hỏi “**đơn vị thay đổi cần giữ invariant** là một key, nhiều key hay nhiều resource?”.

## 10. Phạm vi một JVM và phạm vi database/cluster khác nhau

Giả sử mỗi instance ứng dụng có:

~~~java
private final SeatInventory inventory = new SeatInventory(100);
~~~

Nếu hai node ứng dụng được triển khai độc lập, mỗi node có **SeatInventory riêng**. Các lock của node A không khóa node B. Nếu sức chứa thật là một tài nguyên chung lưu ở database, bộ đếm local chỉ là cache/ước lượng nếu không có cơ chế đồng bộ với nguồn sự thật.

Một hướng xử lý ở database là cập nhật có điều kiện và kiểm tra số bản ghi ảnh hưởng:

~~~sql
-- Pseudocode SQL, cú pháp điều chỉnh theo cơ sở dữ liệu.
UPDATE inventory
SET reserved = reserved + :quantity
WHERE id = :inventory_id
  AND :quantity > 0
  AND reserved <= capacity - :quantity;
~~~

Nếu lệnh update ảnh hưởng **một** bản ghi, đặt chỗ thành công; nếu ảnh hưởng **không** bản ghi nào, có thể là không tồn tại hàng, thiếu sức chứa hoặc điều kiện không thỏa. Caller phải phân biệt các trường hợp theo hợp đồng. Cần constraint cho `0 <= reserved <= capacity` và lưu ý overflow/kiểu số, isolation level, retry và idempotency theo môi trường thực tế.

Khi nhiều bản ghi phải thay đổi cùng nhau (giữ vé, tạo booking, trừ ví...), cần **transaction** với isolation phù hợp hoặc cơ chế phối hợp khác. Khi có hệ thống ngoài như email, transaction của database thường không bao trùm việc gửi thành công: có thể cần transactional outbox, idempotent consumer hoặc chính sách bù trừ.

**Giới hạn phạm vi** là một phần của thiết kế. `synchronized` bảo vệ trạng thái trên **một Java object trong một JVM**, không phải bằng chứng rằng cả cụm hệ thống đã tránh overselling.

## 11. Phân tích nguyên nhân với mô hình “ai giữ tham chiếu?”

Một cách hiệu quả để review là vẽ sơ đồ chủ sở hữu và các đường mutate:

~~~mermaid
flowchart TD
    Input["Caller List mutable"] -->|"truyền reference"| C["Order / Group"]
    Input -.->|"vẫn có thể sửa"| Data["Cùng List object"]
    C -->|"giữ alias"| Data
    Getter["Getter trả List"] -->|"trao alias cho"| Other["Client khác"]
    Other -.->|"add/remove"| Data
    Fix["Defensive copy + controlled methods"] --> Safe["Snapshot bất biến"]
~~~

Ở thiết kế sai, caller có thể thay đổi state qua đường constructor hoặc getter, không cần gọi mutator của class sở hữu. Ở thiết kế đúng, class **chuyển quyền sở hữu bằng cách copy** hoặc chia sẻ các giá trị immutable theo hợp đồng.

Các câu hỏi review cụ thể:

- Object được tạo từ đâu? Ai còn giữ tham chiếu mutable?
- Có phương thức nào trả về collection/array hoặc object con mutable?
- `final` chỉ khóa field reference hay còn khóa nội dung?
- Một singleton có giữ dữ liệu riêng của request/user/tenant không?
- Những bước nào phải được xem như một thay đổi nguyên tử?
- Những thread hoặc node nào có thể đọc/ghi cùng dữ liệu?
- Khi update thất bại, state có bị thay đổi một nửa không?
- Có cách nào từ bỏ shared mutable state mà vẫn đáp ứng nghiệp vụ không?

## 12. Kiểm thử concurrency mà không dựa vào may rủi

Một bài test ngủ `Thread.sleep(100)` rồi kỳ vọng race xảy ra là **không ổn định**. Thay vào đó, dùng `CountDownLatch` hoặc các primitive đồng bộ để điều khiển điểm bắt đầu/điểm dừng và dùng `Future.get()` hoặc `Thread.join()` để quan sát kết quả.

Ví dụ JUnit Jupiter 5 kiểm tra implementation **đúng** `SeatInventory`; đặt trong `SeatInventoryTest.java` cùng package với các class Java ở phần 4:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class SeatInventoryTest {
    @Test
    void twoConcurrentRequestsCannotBothReserveTheLastSeat()
            throws Exception {
        SeatInventory inventory = new SeatInventory(1);

        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<Boolean> a = pool.submit(() -> {
                start.await();
                return inventory.reserveOne();
            });
            Future<Boolean> b = pool.submit(() -> {
                start.await();
                return inventory.reserveOne();
            });

            start.countDown();

            boolean first = a.get(3, TimeUnit.SECONDS);
            boolean second = b.get(3, TimeUnit.SECONDS);

            assertEquals(1,
                    (first ? 1 : 0) + (second ? 1 : 0));

            SeatSnapshot snapshot = inventory.snapshot();
            assertEquals(1, snapshot.reserved());
            assertEquals(0, snapshot.available());
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void capacityCannotBeZero() {
        assertThrows(IllegalArgumentException.class,
                () -> new SeatInventory(0));
    }

    @Test
    void rejectedBookingDoesNotMutateState() {
        SeatInventory inventory = new SeatInventory(1);

        assertTrue(inventory.reserveOne());
        assertFalse(inventory.reserveOne());

        assertEquals(1, inventory.snapshot().reserved());
    }
}
~~~

Các test cần JUnit Jupiter và test runner tương thích. `start` giúp hai task có cơ hội bắt đầu cùng một thời điểm, nhưng **không bảo đảm một lịch chạy giống nhau**. Test đáng tin nhờ bất biến được kiểm tra sau khi các task đã kết thúc; lỗi race nghiêm trọng có thể cần stress test có hệ thống hoặc mô hình hóa concurrency. Timeout giúp phát hiện treo thay vì làm suite chờ vô hạn.

### Kiểm thử aliasing

Một test rất nhanh có thể chứng minh snapshot không bị sửa từ bên ngoài:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class PermissionGroupTest {
    @Test
    void clientCannotEditPermissionsThroughAliasedList() {
        List<String> external = new ArrayList<>(List.of("READ"));
        SafePermissionGroup group = new SafePermissionGroup(external);

        external.add("ADMIN");

        assertFalse(group.has("ADMIN"));
        assertThrows(UnsupportedOperationException.class,
                () -> group.snapshot().add("ADMIN"));
        assertFalse(group.has("ADMIN"));
    }
}
~~~

Test này kiểm tra cả **đường input** lẫn **đường output**. Với danh sách chứa object mutable, phải bổ sung test rằng bản thân các phần tử không làm lộ state hoặc quyền truy cập ngoài dự kiến.

## 13. Lựa chọn giải pháp theo bản chất shared state

| Tình huống | Hướng tiếp cận | Điểm cần kiểm tra |
|---|---|---|
| Configuration dùng chung, không đổi sau khởi động | Immutable config/`static final` phù hợp | Không chứa nested mutable object bị rò rỉ |
| Dữ liệu riêng từng request | Method parameters, local variables, request context có vòng đời rõ | Không lưu trong field của singleton chung |
| Danh sách do caller truyền vào | Defensive copy + immutable elements | Shallow vs deep copy |
| Một bộ đếm chung | `AtomicInteger`, `LongAdder` tùy nhu cầu | Đếm gần đúng hay cần snapshot/atomic read; reset/aggregate |
| Check-then-act trên một object | `synchronized`/lock/CAS | Check và update cùng vùng bảo vệ |
| Nhiều field phải luôn đồng bộ | Một lock hoặc immutable aggregate thay toàn bộ | Không lộ trạng thái trung gian |
| Mutable collection concurrent | `ConcurrentHashMap`/concurrent collection + hợp đồng thao tác đúng | Compound actions, giá trị bên trong mutable |
| Bản ghi chung nhiều node | DB transaction/conditional update/optimistic lock | Isolation, retry, idempotency |
| Cache dùng chung | Library cache đã kiểm nghiệm + immutable value | TTL, eviction, stale reads, stampede |
| Eventual consistency được phép | Sự kiện, outbox, worker, reconciliation | Định nghĩa rõ trạng thái tạm thời và kết quả cuối |

Không có “một từ khóa chữa mọi shared state”. `volatile`, `synchronized`, atomic và transaction giải quyết **các phạm vi và loại ràng buộc khác nhau**. Biện pháp tốt nhất đôi khi đơn giản là **không chia sẻ trạng thái mutable**.

## 14. Bài tập: quản lý hạn mức sử dụng một mã giảm giá

Một coupon cho phép **tối đa 100 lượt sử dụng**. API xử lý nhiều request đồng thời.

### Yêu cầu

Thiết kế `CouponQuota` với:

- `maxUses` bất biến và lớn hơn 0.
- `used` không âm và không vượt `maxUses`.
- Method `boolean tryUse()` chỉ trả `true` khi ghi nhận **chính xác một** lượt sử dụng.
- Method `snapshot()` trả bộ dữ liệu bất biến về `used`/`remaining`.
- Không public setter và không để caller tự tăng `used`.
- Có test gửi ít nhất 500 yêu cầu `tryUse()` đồng thời, cuối cùng **đúng 100 thành công**, số đã dùng bằng 100.
- Mở rộng sang nhiều node: mô tả cách cập nhật có điều kiện hoặc dùng version/constraint trong database; đừng dựa vào lock của một instance Java.

Có thể triển khai bản đầu bằng `synchronized`, sau đó bản thứ hai bằng `AtomicInteger.compareAndSet`. So sánh độ dễ hiểu, lượng code và phạm vi invariant mà mỗi bản bảo vệ.

### Tự kiểm tra

1. Vì sao có một field `private final List<String>` vẫn chưa đủ bảo vệ trạng thái?
2. Nếu hai biến trỏ đến cùng `ArrayList`, thay đổi qua biến này ảnh hưởng biến kia thế nào?
3. Vì sao `volatile int count; count++` vẫn bị mất cập nhật?
4. Trong ví dụ bán vé, tại sao `reserved == 1` vẫn có thể là **kết quả nghiệp vụ sai** khi hai yêu cầu đều được chấp nhận?
5. Một Spring singleton có field `currentOrderId` gặp nguy cơ gì dưới tải đồng thời?
6. `Collections.unmodifiableList(source)` khác snapshot `List.copyOf(source)` ở điểm nào?
7. Khi nào `AtomicInteger` đủ, khi nào cần một lock bảo vệ nhiều field?
8. Một `ConcurrentHashMap` có làm các value `ArrayList` bên trong thread-safe không?
9. Vì sao `synchronized` của node A không bảo vệ việc bán vé trên node B?
10. Có thể bỏ hẳn mutable shared state ở đâu bằng local variable, immutable snapshot hoặc truyền tham số?

**Kết luận:** “Trạng thái dùng chung khó kiểm soát” không đơn thuần là có nhiều biến toàn cục hay dùng nhiều thread. Đó là tình trạng **quyền sở hữu, quyền thay đổi, thời điểm quan sát và đơn vị nhất quán không được quy định rõ**. Thiết kế OOP bền vững ưu tiên **ẩn state, cung cấp thao tác nghiệp vụ, giới hạn alias mutable, dùng dữ liệu bất biến khi có thể**, và chọn cơ chế đồng bộ/transaction theo đúng phạm vi chia sẻ thực tế.