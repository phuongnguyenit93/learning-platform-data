# Công bố dữ liệu và các quan hệ đồng bộ cần thiết khi thiết kế dữ liệu chỉ đọc (Java 10+)

## 1. Hai bài toán phải giải quyết cùng lúc

Một ứng dụng Java thường xây dựng danh sách, tập hợp hoặc map trong một luồng rồi cho nhiều luồng khác **đọc**. Ví dụ, luồng cập nhật cấu hình tạo danh sách quyền truy cập mới, còn nhiều luồng xử lý yêu cầu cần quan sát danh sách đó.

Để thiết kế đúng, cần phân biệt **hai yêu cầu độc lập**:

1. **Ngăn người đọc sửa cấu trúc dữ liệu:** dùng các tập hợp không sửa được như `List.copyOf`, `Set.copyOf`, `Map.copyOf` (có từ Java 10), hoặc xây dựng loại đối tượng bất biến phù hợp.
2. **Công bố dữ liệu an toàn giữa các luồng:** bảo đảm các luồng đọc nhìn thấy một phiên bản đã được khởi tạo đúng, theo các quy tắc bộ nhớ Java (*Java Memory Model*, JMM), đặc biệt là quan hệ **happens-before**.

**Một collection không sửa được không tự tạo quan hệ đồng bộ giữa luồng xuất bản và luồng đọc.** Tương tự, đặt một tham chiếu `volatile` **không tự làm các đối tượng mà nó tham chiếu trở nên bất biến**.

Mẫu đơn giản, hiệu quả cho trường hợp **đọc nhiều, cập nhật ít** là: xây dữ liệu độc lập → tạo snapshot không sửa được → công bố **một tham chiếu** bằng `volatile` hoặc `AtomicReference` → độc giả đọc tham chiếu và chỉ sử dụng snapshot đó.

## 2. Thuật ngữ: không sửa được, snapshot, công bố và happens-before

### Dữ liệu không sửa được (*unmodifiable*)

~~~java
var source = new java.util.ArrayList<>(
        java.util.List.of("READ", "WRITE"));

var snapshot = java.util.List.copyOf(source);

// snapshot.add("ADMIN"); // Ném UnsupportedOperationException nếu chạy.
~~~

`List.copyOf` trả về một `List` không cho thêm, xóa hoặc thay phần tử trực tiếp. Nếu nguồn là collection mutable, các thay đổi cấu trúc sau khi copy không ảnh hưởng snapshot:

~~~java
source.add("ADMIN");

System.out.println(source);   // [READ, WRITE, ADMIN]
System.out.println(snapshot); // [READ, WRITE]
~~~

*Đây là đoạn minh họa trong một phương thức.* Snapshot **không phản ánh thay đổi cấu trúc về sau** của nguồn, nhưng vẫn là **sao chép nông**: nếu phần tử có trạng thái mutable, nó vẫn có thể bị thay đổi từ nơi khác.

### Công bố (*publication*)

Công bố là đưa **tham chiếu tới một đối tượng** từ nơi tạo nó đến nơi khác, ví dụ gán vào trường dùng chung để các luồng đọc. Câu hỏi không chỉ là “luồng khác có thấy tham chiếu không?”, mà còn là “khi thấy tham chiếu, luồng đó có được bảo đảm thấy các giá trị khởi tạo của đối tượng và dữ liệu liên quan không?”.

### Happens-before

`happens-before` là quan hệ thứ tự/khả kiến của JMM. Khi hành động A **happens-before** hành động B, các tác dụng bộ nhớ của A được bảo đảm quan sát theo các quy tắc của JMM tại B. Quan hệ được xây dựng từ **thứ tự chương trình trong một luồng** và các cạnh **synchronizes-with** giữa các luồng.

Những cạnh thường dùng:

| Cơ chế | Quan hệ đồng bộ quan trọng |
| --- | --- |
| `volatile` | Ghi vào biến `volatile` **happens-before** các lần đọc tiếp sau của chính biến đó theo thứ tự đồng bộ |
| `synchronized` | Mở khóa một monitor **happens-before** lần khóa tiếp sau trên **cùng monitor** |
| `Thread.start()` | Lời gọi `start()` **happens-before** các hành động trong luồng được khởi chạy |
| `Thread.join()` | Các hành động của luồng hoàn tất **happens-before** luồng khác trở về thành công từ `join()` |
| `AtomicReference` | `get`/`set` và các phép atomic update phù hợp có ngữ nghĩa bộ nhớ quy định bởi API và `VarHandle` |
| Trường `final` | Có bảo đảm khởi tạo đặc biệt khi constructor hoàn tất đúng cách và `this` không thoát ra trong lúc xây dựng |

**Điều quan trọng:** không cần tạo mọi loại đồng bộ cùng lúc. Hãy chọn một giao thức công bố rõ ràng và bảo đảm cả người ghi lẫn người đọc đều tuân thủ nó.

## 3. Công bố snapshot bằng `volatile`

Nếu mỗi lần cập nhật bạn **thay toàn bộ** danh sách đã công bố, `volatile` là một cách rõ ràng để bảo đảm khả kiến.

~~~java
import java.util.List;

public final class PermissionStore {
    private volatile List<String> current = List.of();

    public void publish(List<String> stableInput) {
        var next = List.copyOf(stableInput);
        current = next; // volatile write: công bố sau khi copy xong.
    }

    public List<String> snapshot() {
        return current; // volatile read: lấy một snapshot đã công bố.
    }
}
~~~

Đây là **một lớp độc lập**, không có `main`. Tham số `stableInput` có nghĩa là nguồn được phép đọc an toàn trong lúc thực hiện `copyOf`; nếu luồng khác đang sửa nguồn đồng thời, cần bảo vệ thao tác copy riêng (phần 9).

### Giải thích happens-before theo từng bước

Luồng xuất bản:

1. Chuẩn bị dữ liệu, bảo đảm các phần tử hợp lệ.
2. Gọi `List.copyOf(stableInput)` để tạo `next` không sửa được.
3. Gán `current = next` — đây là một **volatile write**.

Luồng đọc:

1. Lấy `List<String> local = current` — đây là **volatile read**.
2. Dùng `local` để duyệt hoặc tra cứu; không sửa nó.

Nếu thao tác đọc `volatile` diễn ra sau thao tác ghi theo thứ tự đồng bộ và nhận phiên bản đã xuất bản, các ghi xảy ra trước `volatile write` được đặt trong chuỗi `happens-before` tới các hành động của luồng đọc. Bởi vậy, không phải chỉ “may mắn nhìn thấy tham chiếu”: việc xuất bản có bảo đảm bộ nhớ phù hợp.

**Không đồng nhất `volatile` với “mọi độc giả lập tức thấy phiên bản mới theo một hạn chót thời gian”.** Nó thiết lập tính khả kiến/thứ tự theo JMM, nhưng không tạo một lời hứa tiến độ hay lịch chạy cụ thể cho từng luồng.

### Đọc tham chiếu một lần cho một thao tác logic

~~~java
public void handle(PermissionStore store) {
    List<String> local = store.snapshot();
    int count = local.size();
    boolean canWrite = local.contains("WRITE");

    System.out.println(count + ":" + canWrite);
}
~~~

Đây là **phương thức minh họa** đặt trong lớp khác. Mỗi lần gọi `snapshot()` có thể quan sát một phiên bản khác nếu luồng khác đang xuất bản. Vì vậy, khi các phép đọc phải nhất quán **trong cùng một thao tác**, hãy giữ **một tham chiếu cục bộ** rồi dùng nó.

Việc đọc từ cùng một `local` không làm thay đổi cấu trúc snapshot. Đây là lý do mẫu **immutable snapshot + volatile reference** rất phù hợp với hệ thống đọc thường xuyên.

## 4. `final` và bảo đảm khởi tạo đối tượng

Trường `final` mang ý nghĩa khác `volatile`:

~~~java
import java.util.List;

public final class Catalog {
    private final List<String> codes;

    public Catalog(List<String> input) {
        codes = List.copyOf(input);
    }

    public List<String> codes() {
        return codes;
    }
}
~~~

Đây là lớp ví dụ đầy đủ nhưng không có `main`. Constructor tạo snapshot rồi gán cho trường `final`. Theo JLS `17.5, sau khi constructor hoàn tất, **final-field semantics** cung cấp bảo đảm đặc biệt cho các giá trị được khởi tạo qua trường `final`, với điều kiện đối tượng được xây dựng đúng cách, đặc biệt là **không để `this` thoát ra trước khi constructor hoàn tất**.

Điều đó hữu ích khi tạo một đối tượng **có trạng thái không đổi sau construction**.

Tuy nhiên:

- `final List<String> codes` chỉ ngăn **gán lại tham chiếu trường `codes`**; nó không tự làm một `ArrayList` trở nên unmodifiable. Ở đây `List.copyOf` chịu trách nhiệm về phần cấu trúc.
- `final` không tự bảo vệ trạng thái mutable bên trong các phần tử, cũng không bảo đảm an toàn cho những sửa đổi diễn ra **sau constructor**.
- Nếu cùng một thành phần cần **công bố nhiều phiên bản mới theo thời gian**, một trường `final` không thể được thay thế bằng phiên bản khác; hãy dùng một holder có `volatile`/`AtomicReference` hoặc đồng bộ trên trạng thái thay đổi.
- Không gọi callback, đăng ký object vào nơi chia sẻ, khởi tạo luồng dùng `this` hoặc lưu `this` vào cấu trúc chung **ngay trong constructor** khi điều đó cho phép luồng khác quan sát đối tượng chưa xây xong.

Có thể coi `final` là nền tảng tốt cho **một phiên bản trạng thái được xây dựng hoàn chỉnh**. Khi xuất bản một đối tượng phức hợp chứa cả trường `final` và dữ liệu ngoài nó, vẫn nên dùng cơ chế công bố rõ ràng nếu tính đúng đắn phụ thuộc nhiều trạng thái.

## 5. Công bố nhiều trường cùng lúc bằng một đối tượng snapshot

Giả sử hệ thống cần công bố **cùng một phiên bản** của `version` và `tags`. Dùng hai trường `volatile` độc lập **không bảo đảm** độc giả thấy một cặp cùng phiên bản:

~~~java
// Thiết kế không phù hợp nếu version và tags phải đồng bộ logic:
private volatile int version;
private volatile java.util.List<String> tags = java.util.List.of();

// Một người ghi có thể gán version rồi tags.
// Người đọc có thể thấy version mới với tags cũ (hoặc ngược lại).
~~~

Cả hai volatile read/write đều có quy tắc khả kiến, nhưng **không biến hai trường thành một thao tác đọc/ghi nguyên tử chung**.

Giải pháp là bọc dữ liệu vào một **snapshot object** hoàn chỉnh, rồi xuất bản **một tham chiếu**:

~~~java
import java.util.List;

final class ConfigSnapshot {
    final int version;
    final List<String> tags;

    ConfigSnapshot(int version, List<String> tags) {
        this.version = version;
        this.tags = List.copyOf(tags);
    }
}

final class ConfigService {
    private volatile ConfigSnapshot state =
            new ConfigSnapshot(0, List.of());

    void publish(int version, List<String> stableInput) {
        var next = new ConfigSnapshot(version, stableInput);
        state = next;
    }

    ConfigSnapshot current() {
        return state;
    }
}
~~~

Đoạn này là **hai lớp package-private**, có thể đặt trong cùng tệp hoặc tệp riêng; không có `main`. Độc giả:

~~~java
var snapshot = service.current(); // service giả định là ConfigService đã tạo
int version = snapshot.version;
List<String> tags = snapshot.tags;
~~~

Ở đây cả `version` và `tags` lấy từ **cùng object snapshot**. Không xảy ra việc trộn cặp trường từ hai phiên bản chỉ vì publisher đang thay thế tham chiếu.

Đối tượng snapshot không bắt buộc dùng `record`; ví dụ trên dùng lớp `final` để tương thích từ Java 10. Trong code Java 17+, `record` cũng là lựa chọn phù hợp, miễn là các thành phần collection vẫn được sao chép phòng vệ và bất biến theo hợp đồng.

## 6. `synchronized`: bảo vệ cả giai đoạn xây dựng và công bố

Một nguồn mutable có thể được nhiều luồng cập nhật. Trong trường hợp đó, **chỉ có `volatile` ở biến snapshot chưa đủ**, vì còn phải bảo vệ việc truy cập dữ liệu nguồn và quyết định cập nhật nào hợp lệ.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class LockedCatalog {
    private final Object lock = new Object();
    private final List<String> draft = new ArrayList<>();
    private volatile List<String> published = List.of();

    public void add(String value) {
        synchronized (lock) {
            draft.add(Objects.requireNonNull(value));
            published = List.copyOf(draft);
        }
    }

    public List<String> snapshot() {
        return published;
    }
}
~~~

Đây là một lớp độc lập, không có `main`.

Vai trò của hai cơ chế:

- **`synchronized(lock)` ở phía ghi:** các luồng gọi `add` không sửa `draft` đồng thời và không copy nguồn lúc một luồng khác đang cập nhật nó. Mỗi lần mở khóa cùng `lock` có quan hệ đồng bộ với những lần khóa tiếp sau cùng monitor.
- **`volatile published`:** khi writer hoàn thành snapshot và gán tham chiếu, các luồng chỉ đọc `snapshot()` có thể nhận phiên bản hoàn chỉnh mà **không phải khóa `draft`**.
- **`List.copyOf(draft)`:** đối tượng công bố không cho độc giả tự ý thêm/xóa/thay phần tử.

**Giao thức khóa chỉ đúng nếu tất cả người sửa `draft` đều sử dụng cùng khóa.** Nếu lộ tham chiếu `draft` ra ngoài rồi có người sửa nó không khóa, bảo đảm bị phá vỡ.

Không sử dụng `synchronized(published)` để khóa trên kết quả `List.copyOf`: các collection do factory tạo có tính chất **value-based**, không phù hợp làm khóa đồng bộ đáng tin cậy. Nên dùng một object khóa riêng, ổn định, như `new Object()`.

Một lựa chọn khác là bảo vệ **cả đọc và ghi trạng thái mutable** bằng cùng monitor; nhưng nếu đã công bố snapshot không sửa được qua volatile, người đọc thường không cần giữ khóa chỉ để duyệt snapshot của mình.

## 7. Nhiều người ghi: `volatile` không thay được atomic read–modify–write

Mẫu sau trông đơn giản nhưng **có thể làm mất cập nhật** nếu hai luồng gọi đồng thời:

~~~java
private volatile java.util.List<String> snapshot =
        java.util.List.of();

// Mã minh họa: KHÔNG đủ để bảo toàn hai cập nhật đồng thời.
void addUnsafe(String item) {
    var next = new java.util.ArrayList<>(snapshot);
    next.add(item);
    snapshot = java.util.List.copyOf(next);
}
~~~

Cả hai writer có thể đọc **cùng phiên bản cũ**, mỗi writer tự thêm một phần tử khác nhau rồi cùng ghi vào trường `volatile`. Lần ghi cuối làm phiên bản còn lại không được lưu lại: **lost update**.

`volatile` bảo đảm khả kiến cho phép đọc/ghi một tham chiếu, **không biến chuỗi thao tác đọc → copy → thêm → ghi thành một giao dịch nguyên tử**.

### `AtomicReference.updateAndGet`

Khi cần nhiều writer cập nhật trên nền snapshot cũ, có thể dùng `AtomicReference<List<T>>`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

public final class AtomicCatalog {
    private final AtomicReference<List<String>> snapshot =
            new AtomicReference<>(List.of());

    public void add(String item) {
        snapshot.updateAndGet(previous -> {
            var next = new ArrayList<>(previous);
            next.add(item);
            return List.copyOf(next);
        });
    }

    public List<String> snapshot() {
        return snapshot.get();
    }
}
~~~

Đây là một lớp độc lập, không có `main`.

`updateAndGet` áp dụng phép cập nhật nguyên tử bằng cơ chế compare-and-set. Nếu một writer khác đã thay snapshot trong lúc tính toán, hàm cập nhật có thể được **thực hiện lại** dựa trên trạng thái mới. Hai lời gọi đồng thời thêm `"X"` và `"Y"` sẽ không làm mất một trong hai chỉ vì cùng đọc trạng thái cũ, miễn là hàm cập nhật thực hiện đúng và hoàn tất.

**Điều kiện cực kỳ quan trọng:** lambda truyền vào `updateAndGet` nên **không có tác dụng phụ ngoài**. Nó có thể bị gọi nhiều lần khi có tranh chấp. Tạo `ArrayList` cục bộ và trả về snapshot mới là phù hợp; gọi API thanh toán, gửi email, cập nhật database hoặc tăng bộ đếm bên ngoài **trong lambda** là sai thiết kế vì tác dụng phụ có thể lặp.

Nếu chỉ có **một writer** thay toàn bộ phiên bản theo thứ tự, `volatile` có thể đã đủ. Nếu có **nhiều writer cần cập nhật dựa trên phiên bản hiện tại**, dùng khóa chung hoặc cơ chế atomic thích hợp.

## 8. `Thread.start`, `join` và công cụ đồng bộ cấp cao

JMM còn đưa ra các quan hệ dễ sử dụng:

- Các hành động của luồng gọi trước khi `thread.start()` **happens-before** các hành động trong luồng mới.
- Các hành động trong luồng được chạy **happens-before** luồng khác trở về thành công từ `thread.join()`.
- Các cấu trúc như `CountDownLatch`, `BlockingQueue` và các lớp trong `java.util.concurrent` có hợp đồng đồng bộ riêng; hãy dùng theo đúng tài liệu của chúng.

Ví dụ:

~~~java
var config = java.util.List.copyOf(
        java.util.List.of("A", "B"));

Thread worker = new Thread(() ->
        System.out.println(config.size()));

worker.start();
worker.join(); // Nếu đặt trong phương thức throws InterruptedException.
~~~

Đoạn trên minh họa trong một phương thức (không phải chương trình riêng). Khi gọi `start()` sau khi tạo `config`, các hành động trước `start()` có quan hệ `happens-before` với luồng worker. `join()` thành công cho bên gọi biết luồng worker đã hoàn tất và tạo thêm cạnh `happens-before` theo chiều trở lại.

**Không được dùng `Thread.sleep(...)` làm biện pháp công bố dữ liệu.** Chờ một khoảng thời gian không tự tạo quan hệ `happens-before` cần thiết. Tương tự, việc một chương trình “chạy đúng 100 lần” khi không có đồng bộ cũng không chứng minh nó đúng theo JMM.

Trong chương trình kiểm chứng ở phần 12, `join()` được dùng **để kết quả đầu ra xác định**, không phải để chứng minh rằng `volatile` chỉ có tác dụng khi có `join()`. `volatile` có bảo đảm bộ nhớ riêng, độc lập với thử nghiệm này.

## 9. Nguy cơ sửa nguồn trong lúc `copyOf` đang chạy

Một hiểu nhầm nguy hiểm: “Vì `List.copyOf` tạo snapshot nên nó chắc chắn có thể đọc an toàn một `ArrayList` đang bị nhiều luồng khác sửa.”

**Không đúng.** `List.copyOf`, `Set.copyOf` hay `Map.copyOf` **không tự đồng bộ với các thao tác sửa một nguồn mutable không được bảo vệ**.

~~~java
// KHÔNG an toàn nếu một luồng khác sửa source đồng thời mà không có lock.
var published = java.util.List.copyOf(source);
~~~

Nếu luồng A đang copy `source` còn luồng B đang `add`, `remove` hoặc `set` trên nguồn không có giao thức đồng bộ, **không có bảo đảm chung về snapshot nguyên tử/nhất quán**. Tùy collection và lịch chạy có thể quan sát dữ liệu không như mong muốn hoặc gặp ngoại lệ; đừng dựa vào một kiểu ngoại lệ cụ thể để phát hiện mọi race.

### Cách làm đúng khi nguồn được bảo vệ bởi một khóa

~~~java
final Object sourceLock = new Object();
final java.util.List<String> source = new java.util.ArrayList<>();

// Tất cả writer cũng phải sử dụng sourceLock.
void add(String value) {
    synchronized (sourceLock) {
        source.add(value);
    }
}

java.util.List<String> copyStable() {
    synchronized (sourceLock) {
        return java.util.List.copyOf(source);
    }
}
~~~

Đây là **hai phương thức và hai trường minh họa trong cùng lớp**, không phải toàn bộ chương trình độc lập. Mọi nơi thay đổi `source` đều phải tuân thủ cùng `sourceLock`, và thao tác sao chép cần giữ khóa trong suốt quá trình đọc nguồn.

Đừng dùng `synchronized(source)` tùy ý nếu các writer đang dùng một khóa khác. Quan hệ monitor chỉ có hiệu lực khi dùng **chính cùng đối tượng khóa**.

### Nguồn là immutable snapshot thì sao?

Nếu nguồn đã là một tập hợp không sửa được, có các phần tử bất biến, được xây dựng và truyền đến an toàn, `copyOf` có thể không cần tạo bản sao vật lý mới. API cho phép sử dụng lại instance phù hợp. **Đừng dựa vào phép so sánh `==` để kết luận hành vi copy.**

## 10. Vì sao `Collections.unmodifiableList` có thể không phù hợp để công bố?

Xét:

~~~java
var draft = new java.util.ArrayList<>(
        java.util.List.of("A", "B"));

var view = java.util.Collections.unmodifiableList(draft);
var snapshot = java.util.List.copyOf(draft);

draft.add("C");

System.out.println(view);     // [A, B, C]
System.out.println(snapshot); // [A, B]
~~~

`Collections.unmodifiableList(draft)` tạo **view không cho sửa trực tiếp qua tham chiếu view**, nhưng vẫn phản ánh thay đổi của `draft`. Nếu `draft` bị sửa đồng thời trong lúc luồng khác duyệt view, nguy cơ race/vấn đề iterator vẫn có thể xảy ra. “Unmodifiable” không có nghĩa “thread-safe”.

Ngược lại, `List.copyOf(draft)` tạo snapshot độc lập về **cấu trúc** khi nguồn mutable; thay đổi danh sách nguồn sau khi copy không thay đổi các phần tử và vị trí trong snapshot.

Cả hai API đều còn được dùng trong Java hiện đại. Chọn theo hợp đồng:

| Nhu cầu | Phương án |
| --- | --- |
| Bản chụp cấu trúc không theo nguồn sau khi công bố | `List.copyOf`/`Set.copyOf`/`Map.copyOf` |
| View đọc được nhưng phản ánh các thay đổi nguồn do người khác thực hiện | `Collections.unmodifiableList`/... với đồng bộ nguồn thích hợp |
| Map chia sẻ và cập nhật liên tục bởi nhiều writer | Xem xét `ConcurrentHashMap` hoặc khóa phù hợp; không thay bằng `Map.copyOf` |
| Nhiều độc giả, cập nhật toàn phiên bản tương đối ít | Snapshot bất biến + `volatile`/`AtomicReference` |
| Nhiều người ghi cần cập nhật dựa trên phiên bản hiện tại | `synchronized`/lock hoặc `AtomicReference.updateAndGet` |

`ConcurrentHashMap` cung cấp thao tác concurrent trên map mutable, **khác** với hợp đồng “độc giả xem một snapshot toàn phiên bản không đổi”. Đừng coi thay thế một API bằng API khác là tương đương nếu mục tiêu tính nhất quán khác nhau.

## 11. Sao chép nông và an toàn khi phần tử mutable

`List.copyOf` không sao chép sâu các đối tượng được giữ trong danh sách. Ví dụ:

~~~java
var text = new StringBuilder("v1");
var snapshot = java.util.List.copyOf(
        java.util.List.of(text));

text.append("!");
System.out.println(snapshot.get(0)); // v1!
~~~

Kết quả là `v1!` vì snapshot và nơi khác vẫn giữ **cùng tham chiếu `StringBuilder`**. `snapshot.add(...)` sẽ bị từ chối, nhưng `text.append(...)` vẫn sửa được **đối tượng phần tử**.

**Điều này quan trọng trong nhiều luồng:** nếu một luồng đọc `StringBuilder` còn luồng khác sửa nó mà không đồng bộ, vẫn có thể xảy ra data race, dù `List` bao ngoài là unmodifiable và tham chiếu của nó được công bố bằng `volatile`.

Các hướng giải quyết:

- Ưu tiên phần tử thực sự bất biến như `String`, các lớp giá trị bất biến hoặc cấu trúc được thiết kế đúng hợp đồng.
- Nếu phần tử là mutable, sao chép phòng vệ từng phần tử sang loại bất biến trước khi công bố, hoặc sử dụng đồng bộ đầy đủ cho trạng thái bên trong.
- Với dữ liệu lồng nhau, một lần `List.copyOf(outerList)` **chỉ bảo vệ cấu trúc cấp ngoài**. Các `List` con mutable cần có snapshot riêng nếu muốn đọc ổn định.
- Với `Map.copyOf`, cả **khóa** và **giá trị** đều có thể là đối tượng mutable. Đặc biệt nguy hiểm nếu sửa trường ảnh hưởng `equals/hashCode` của khóa sau khi đưa vào map.

**Không nhầm ba tính chất:** “không sửa được qua API collection”, “bất biến sâu của toàn bộ đồ thị đối tượng” và “được công bố an toàn giữa các luồng” là ba bảo đảm khác nhau. Để có một hệ thống đọc ổn định, có thể cần cả ba.

## 12. Chương trình Java hoàn chỉnh với đầu ra xác định

Lưu tệp **`PublicationSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

public final class PublicationSnapshotDemo {
    // Một tham chiếu snapshot được công bố cho người đọc.
    private static volatile List<String> published = List.of();

    private static void publish(List<String> stableInput) {
        published = List.copyOf(stableInput);
    }

    private static List<String> readSnapshot() {
        return published;
    }

    private static void atomicAdd(
            AtomicReference<List<String>> reference, String item) {
        reference.updateAndGet(previous -> {
            var next = new ArrayList<>(previous);
            next.add(item);
            return List.copyOf(next);
        });
    }

    public static void main(String[] args) throws InterruptedException {
        var source = new ArrayList<>(List.of("A", "B"));

        publish(source);
        var first = readSnapshot();

        // Thay đổi source sau khi đã tạo snapshot đầu tiên.
        source.add("C");

        System.out.println("first=" + first);
        System.out.println("source=" + source);

        // Writer công bố phiên bản mới; join giúp test có output cố định.
        Thread updater = new Thread(() -> publish(source));
        updater.start();
        updater.join();

        var latest = readSnapshot();

        System.out.println("latest=" + latest);
        System.out.println("firstStill=" + first);

        try {
            latest.add("D");
        } catch (UnsupportedOperationException ex) {
            System.out.println("directUpdate=blocked");
        }

        // Nhiều writer cập nhật dựa trên phiên bản đang được công bố.
        var atomic = new AtomicReference<List<String>>(List.of());

        Thread firstWriter = new Thread(
                () -> atomicAdd(atomic, "X"));
        Thread secondWriter = new Thread(
                () -> atomicAdd(atomic, "Y"));

        firstWriter.start();
        secondWriter.start();

        firstWriter.join();
        secondWriter.join();

        var both = atomic.get();

        // Thứ tự X/Y không phụ thuộc vào lịch chạy, nhưng cả hai tồn tại.
        System.out.println("atomicSize=" + both.size());
        System.out.println("atomicHasX=" + both.contains("X"));
        System.out.println("atomicHasY=" + both.contains("Y"));

        // Shallow copy: cấu trúc List không sửa được,
        // trạng thái của phần tử mutable vẫn có thể đổi.
        var mutable = new StringBuilder("v1");
        var copy = List.copyOf(List.of(mutable));

        mutable.append("!");
        System.out.println("shallow=" + copy.get(0));
    }
}
~~~

Biên dịch và chạy với **JDK 17+** (toàn bộ cú pháp/API trong mã đã được hỗ trợ từ Java 10):

~~~bash
javac PublicationSnapshotDemo.java
java PublicationSnapshotDemo
~~~

**`stdout` được kiểm chứng trên JDK 24:**

~~~text
first=[A, B]
source=[A, B, C]
latest=[A, B, C]
firstStill=[A, B]
directUpdate=blocked
atomicSize=2
atomicHasX=true
atomicHasY=true
shallow=v1!
~~~

Đầu ra được thiết kế **không phụ thuộc lịch chạy**:

1. `first=[A, B]`: snapshot cũ không đổi dù `source` thêm phần tử.
2. `latest=[A, B, C]`: writer tạo và công bố phiên bản sau khi nguồn đã cập nhật; `join()` khiến main chỉ đọc sau khi writer hoàn tất.
3. `directUpdate=blocked`: kết quả `List.copyOf` không cho sửa cấu trúc.
4. `atomicSize=2` và hai dòng `atomicHas...=true`: cả hai phép thêm bằng `AtomicReference.updateAndGet` được phản ánh. **Không in trực tiếp danh sách `both`** vì `X`/`Y` có thể xuất hiện theo thứ tự khác nhau.
5. `shallow=v1!`: snapshot list vẫn quan sát được thay đổi của một `StringBuilder` được chia sẻ.

**Không xem một lần chạy thành công là chứng minh đầy đủ cho JMM.** Tính đúng đắn của cơ chế công bố phải dựa trên **quan hệ happens-before được đặc tả**, không chỉ dựa trên kết quả test. Chương trình sử dụng `join` cho output xác định, nên bản thân test không tách biệt để đo riêng tác dụng của `volatile`.

## 13. Những lỗi thiết kế thường gặp

### Lỗi 1: trường thường chứa snapshot và kỳ vọng mọi luồng thấy phiên bản mới

~~~java
// Không đủ làm giao thức công bố an toàn nếu writer/reader
// không có một quan hệ happens-before phù hợp.
private List<String> current = List.of();

void publish(List<String> stableInput) {
    current = List.copyOf(stableInput);
}
~~~

`List.copyOf` bảo vệ cấu trúc phần tử, nhưng **không tự tạo happens-before** cho phép ghi/đọc trường `current` giữa hai luồng. Nếu các luồng truy cập cùng trường mà không có quan hệ đồng bộ phù hợp, ứng dụng có thể gặp vấn đề khả kiến/data race.

**Cách sửa:** nếu đây là một trường được thay phiên bản và có nhiều độc giả đồng thời, dùng `volatile`, `AtomicReference` hoặc khóa bảo vệ đúng giao thức.

### Lỗi 2: dùng `volatile` nhưng vẫn sửa collection được tham chiếu

~~~java
private volatile List<String> current = new ArrayList<>();

// Không an toàn cho độc giả concurrent chỉ vì current là volatile:
// current.add("A");
~~~

`volatile` chỉ áp dụng cho **việc đọc/ghi tham chiếu `current`**, không khiến thao tác `add` trên `ArrayList` trở thành an toàn đồng thời. Nếu writer và reader truy cập trực tiếp một `ArrayList` mutable, vẫn có thể xảy ra race.

**Cách sửa:** xây bản mới và công bố snapshot không sửa được, hoặc dùng một collection concurrent/cơ chế khóa phù hợp với yêu cầu.

### Lỗi 3: dùng nhiều `volatile` cho một trạng thái logic

Hai trường `volatile` có thể được quan sát ở **hai phiên bản khác nhau**, dù từng trường được đọc hợp lệ.

**Cách sửa:** đóng gói các trường cần nhất quán vào **một snapshot object** và công bố bằng một tham chiếu duy nhất; độc giả đọc tham chiếu một lần.

### Lỗi 4: thay snapshot bằng `volatile` nhưng có nhiều writer cùng sửa dựa trên snapshot cũ

Cặp thao tác `read current → build next → write current` không phải một giao dịch nguyên tử, nên có thể mất cập nhật.

**Cách sửa:** dùng `synchronized` với một khóa chung hoặc `AtomicReference.updateAndGet`/CAS nếu phù hợp. Lambda cho CAS phải tránh side effect do có thể chạy lại.

### Lỗi 5: copy nguồn mutable khi đang bị sửa không đồng bộ

`copyOf` không khóa nguồn thay bạn. Snapshot được xây trong khi nguồn đồng thời sửa có thể không phản ánh trạng thái nhất quán.

**Cách sửa:** xây trên một nguồn thread-confined, hoặc giữ cùng khóa khi vừa cập nhật vừa sao chép, hoặc dùng một cơ chế snapshot được thiết kế riêng.

### Lỗi 6: đồng bộ trên chính collection `List.copyOf`

Các đối tượng từ unmodifiable factory có đặc tính value-based; không sử dụng identity của chúng cho `synchronized`.

**Cách sửa:** chọn monitor ổn định do bạn sở hữu, ví dụ `private final Object lock = new Object();`.

### Lỗi 7: phần tử mutable trong snapshot

Snapshot chỉ sao chép cấu trúc; nếu đối tượng phần tử mutable vẫn bị sửa nơi khác thì dữ liệu quan sát có thể thay đổi và có thể phát sinh race.

**Cách sửa:** thiết kế phần tử bất biến hoặc sao chép phòng vệ sâu đến mức cần thiết; nếu không thể, bắt buộc có đồng bộ cho phần tử.

## 14. Bảng chọn cơ chế đồng bộ

| Tình huống | Hướng tiếp cận | Điều cần nhớ |
| --- | --- | --- |
| Đối tượng cấu hình tạo một lần, mọi trường là bất biến | `final` fields + constructor đúng, công bố rõ ràng | Không cho `this` thoát trong constructor |
| Một writer định kỳ thay nguyên snapshot | `volatile List<T>`/`volatile ConfigSnapshot` | Nguồn phải ổn định khi copy; giữ snapshot là unmodifiable |
| Nhiều writer bổ sung trên phiên bản hiện tại | `AtomicReference.updateAndGet` hoặc khóa chung | Không để side effect trong lambda có thể retry |
| Nhiều trường phải nhất quán cùng phiên bản | Một object snapshot + một tham chiếu công bố | Đọc tham chiếu một lần ở mỗi thao tác |
| Nguồn mutable có nhiều writer | `synchronized`/`Lock` nhất quán | Dùng cùng cơ chế cả khi copy nguồn |
| Phần tử bên trong có thể sửa | Sao chép phần tử hoặc đồng bộ riêng | `List.copyOf` không deep copy |
| Cần map cập nhật liên tục | `ConcurrentHashMap` hoặc cơ chế khóa thích hợp | Không giống với snapshot map bất biến |
| Chỉ muốn hạn chế sửa trực tiếp qua tham chiếu | Unmodifiable view, có giao thức đồng bộ nếu nguồn thay đổi | View có thể phản ánh cập nhật của nguồn |

## 15. Câu hỏi tự kiểm tra

### Câu 1: `List.copyOf` có đủ để công bố an toàn sang luồng khác không?

**Đáp án:** Không tự đủ trong mọi mô hình chia sẻ. Nó cung cấp danh sách không sửa được và snapshot cấu trúc. Việc **truyền tham chiếu giữa các luồng** còn cần một đường công bố có quan hệ `happens-before` phù hợp (ví dụ `volatile`/`AtomicReference`, cùng monitor hoặc các quan hệ start/join), trừ những bảo đảm khởi tạo đặc biệt áp dụng đúng trường hợp.

### Câu 2: `volatile List<String> current` có làm cho `current.add("X")` an toàn không?

**Đáp án:** Không. `volatile` bảo vệ hành vi đọc/ghi **tham chiếu trường**, không tự đồng bộ các thao tác vào nội dung mutable của collection. Hãy công bố snapshot mới thay vì sửa collection chia sẻ trực tiếp hoặc dùng cấu trúc concurrent/khóa phù hợp.

### Câu 3: nếu hai writer cùng chạy `current = List.copyOf(next)`, có thể mất cập nhật không?

**Đáp án:** Có, nếu `next` được tính từ phiên bản `current` cũ và mỗi writer thực hiện riêng chuỗi **đọc–sửa–ghi**. Dùng `AtomicReference.updateAndGet` hoặc khóa chung để cập nhật trên trạng thái hiện hành một cách nguyên tử.

### Câu 4: khóa khi copy nguồn nhưng writer khác lại không dùng khóa đó có an toàn không?

**Đáp án:** Không. `synchronized` chỉ tạo mutual exclusion khi các bên tham gia cùng khóa. Một writer không khóa vẫn có thể sửa nguồn trong lúc đang copy.

### Câu 5: tại sao nên đọc `var local = published;` một lần?

**Đáp án:** Nếu `published` được thay bằng snapshot mới giữa nhiều lần đọc, mã có thể trộn dữ liệu của các phiên bản khác nhau. Giữ một tham chiếu cục bộ đến object snapshot bất biến giúp cùng thao tác đọc một phiên bản nhất quán.

### Câu 6: nếu một snapshot chứa `StringBuilder` thì có thật sự bất biến sâu không?

**Đáp án:** Không. `StringBuilder` còn mutable và có thể được chia sẻ; sửa đối tượng đó vẫn thay đổi kết quả quan sát qua snapshot. Cần dữ liệu phần tử bất biến hoặc cơ chế bảo vệ/sao chép riêng.

## 16. Kết luận và nguồn chính thức

- **Dữ liệu chỉ đọc và công bố an toàn là hai mục tiêu riêng**: không thể thay `happens-before` bằng `List.copyOf` đơn thuần, cũng không thể thay bất biến nội dung bằng `volatile` đơn thuần.
- Với mô hình **đọc nhiều/cập nhật ít**, xây **snapshot không sửa được trên nguồn ổn định**, rồi công bố qua `volatile` hoặc `AtomicReference` là cách thiết kế rõ ràng.
- **Trường `final`** cung cấp bảo đảm khởi tạo đặc biệt khi constructor không để `this` thoát; nó không làm mọi đối tượng reachable trở thành bất biến sâu.
- **`synchronized`** bảo vệ vùng đọc/sửa nguồn bằng cùng khóa; `AtomicReference.updateAndGet` hỗ trợ cập nhật nguyên tử nhiều writer, nhưng lambda có thể chạy lại.
- Độc giả nên **lấy một tham chiếu snapshot cục bộ** để không trộn nhiều phiên bản trong cùng thao tác.
- **`Thread.start` và `join` cũng tạo quan hệ happens-before**, nhưng `sleep` không phải cách bảo đảm khả kiến.
- Khi snapshot chứa phần tử mutable hoặc nguồn bị sửa trong lúc sao chép, phải thiết kế thêm biện pháp bảo vệ; **không có API copy nào tự động giải quyết mọi race**.

Tài liệu tham khảo chính thức (kiến thức hiện hành):

- [Java Language Specification, `17.4.5 — Happens-before Order (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-17.html#jls-17.4.5)
- [Java Language Specification, `17.5 — final Field Semantics (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-17.html#jls-17.5)
- [Java SE 26 — List.copyOf, Unmodifiable Lists](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))
- [Java SE 26 — AtomicReference.updateAndGet](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html#updateAndGet(java.util.function.UnaryOperator))
- [Oracle — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/26/core/creating-immutable-lists-sets-and-maps.html)
