# Trạng thái công khai và mất điều kiện bất biến trong OOP

> **Chủ đề:** OOP → Lỗi thiết kế → Trạng thái công khai và mất điều kiện bất biến.  
> **Mục tiêu:** Nhận diện các đường dữ liệu bên ngoài có thể phá hỏng trạng thái đối tượng; hiểu invariant khác với kiểm tra đầu vào; dùng encapsulation, thao tác nghiệp vụ, defensive copy và kiểm thử để bảo vệ đối tượng trong Java.

## 1. Vấn đề: đối tượng có thể “tự mâu thuẫn” dù khởi tạo hợp lệ

Giả sử hệ thống bán vé có một kho chỗ ngồi: **sức chứa 10**, đã đặt **4**, còn **6**. Các con số đó phải tuân thủ quy tắc:

\[
0 \le \text{reserved} \le \text{capacity}
\]

và \(\text{available}=\text{capacity}-\text{reserved}\).

Đây là **điều kiện bất biến của đối tượng (object invariant)**: một điều kiện phải đúng tại những thời điểm trạng thái của đối tượng được phép quan sát từ bên ngoài, đặc biệt **sau khi khởi tạo thành công** và **sau mỗi thao tác công khai hoàn tất**.

Một thiết kế có thể khởi tạo trạng thái đúng nhưng cho phép code bên ngoài làm sai:

~~~java
// Ví dụ CỐ Ý SAI để thấy lỗi thiết kế.
class BrokenSeatInventory {
    public int capacity;
    public int reserved;

    BrokenSeatInventory(int capacity) {
        this.capacity = capacity;
        this.reserved = 0;
    }

    int available() {
        return capacity - reserved;
    }
}

BrokenSeatInventory inventory = new BrokenSeatInventory(10);
inventory.reserved = 12; // Java cho phép: trường public.
System.out.println(inventory.available()); // -2
~~~

Chỉ một phép gán hợp lệ về mặt **kiểu `int`** đã phá quy tắc nghiệp vụ. Trình biên dịch không thể suy ra “`reserved` không được vượt `capacity`” từ hai trường `int`.

**Lỗi không chỉ là “để field ở `public`”**. Vấn đề sâu hơn là đối tượng **không kiểm soát được mọi con đường thay đổi trạng thái của chính nó**. Trạng thái có thể bị thay trực tiếp qua field, qua getter trả về collection mutable, qua một object được truyền vào constructor rồi bị sửa bên ngoài, hoặc qua setter cho phép các field liên quan biến đổi độc lập.

## 2. Invariant là gì và khác validation như thế nào?

Ba khái niệm thường đi cùng nhưng giải quyết ba câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Ví dụ với kho chỗ |
|---|---|---|
| **Tiền điều kiện (precondition)** | Người gọi phải truyền gì để thao tác hợp lệ? | `reserve(seats)` yêu cầu `seats > 0` |
| **Hậu điều kiện (postcondition)** | Nếu thao tác thành công, kết quả phải thế nào? | Đặt 3 chỗ thành công thì số chỗ đã đặt tăng đúng 3 |
| **Bất biến (invariant)** | Quy tắc nào luôn phải được bảo toàn ở ranh giới quan sát trạng thái? | `0 ≤ reserved ≤ capacity` |

Một invariant có thể liên quan **nhiều trường**:

- Tài khoản: `balance >= 0` nếu nghiệp vụ không cho thấu chi.
- Kho hàng: `0 <= reserved <= stock`.
- Khoảng thời gian: `start.isBefore(end)`.
- Đơn hàng: `status == PAID` chỉ khi một số điều kiện thanh toán đã đạt.
- Nhóm người dùng: quyền sở hữu và thành viên phải nhất quán theo quy tắc hệ thống.

Không phải mọi đối tượng đều có invariant phức tạp. Ví dụ một DTO đọc dữ liệu chưa kiểm chứng có thể cố ý chứa trạng thái chưa hợp lệ để trả lỗi validation. Ngược lại, **domain object** được kỳ vọng biểu diễn trạng thái hợp lệ thì cần giữ quy tắc của nó trong các thao tác công khai.

### “Luôn đúng” có nghĩa đến mức nào?

Một method có thể thay đổi nhiều field qua các bước nội bộ; một trạng thái trung gian **không được lộ ra** có thể chưa thỏa invariant tạm thời. Thiết kế tốt vẫn cố gắng cập nhật theo một bước nhất quán và chỉ công bố trạng thái hợp lệ. Trong chương trình nhiều luồng, điều này còn đòi hỏi đồng bộ hóa nếu các thread cùng đọc/ghi.

Không nên coi lời hứa “chỉ gọi setter theo đúng thứ tự” là bảo vệ invariant. Người dùng API, lớp con, serializer, framework hay một lần refactor có thể gọi theo thứ tự khác.

## 3. Vì sao `private` là cần nhưng chưa đủ?

**Encapsulation (đóng gói)** không chỉ là thay `public` thành `private`. Nó là việc đối tượng **giữ quyền kiểm soát trạng thái và bảo đảm các quy tắc hợp lệ** khi nhận yêu cầu thay đổi.

Một thiết kế tốt thường có ba tầng bảo vệ:

1. **Ẩn cách lưu trạng thái:** không cho client ghi thẳng các field quan trọng.
2. **Đặt thao tác theo ngôn ngữ nghiệp vụ:** `reserve(3)`, `cancel(2)` thay vì `setReserved(7)`.
3. **Bảo vệ mọi đường tham chiếu mutable:** constructor, getter, setter, collection, array, object lồng nhau và luồng truy cập đồng thời.

Bảng sau tóm tắt những sai lầm phổ biến:

| Cách viết | Rủi ro | Hướng sửa |
|---|---|---|
| `public int reserved` | Mọi client gán giá trị tùy ý | `private` + method `reserve`/`cancel` có điều kiện |
| `setReserved(x)`, `setCapacity(y)` riêng biệt | Có thể gây tổ hợp trạng thái không hợp lệ | Thao tác nghiệp vụ hoặc cập nhật một bộ dữ liệu nguyên tử |
| `getItems() { return items; }` | Trả tham chiếu tới collection mutable nội bộ | Trả snapshot/read-only view phù hợp |
| `this.items = items` nhận `List` từ ngoài | Caller còn giữ alias và sửa dữ liệu về sau | Copy dữ liệu đầu vào theo chính sách |
| `private final List<X> items` | `final` chỉ cố định tham chiếu, không ngăn `add/remove` | Kiểm soát mutation và không rò rỉ tham chiếu |
| `record User(List<Role> roles)` | Record không tự tạo deep copy của component | Chuẩn hóa/copy trong compact constructor |
| Kiểm tra lúc tạo nhưng không ở lúc sửa | Đối tượng hợp lệ ban đầu, sau đó không hợp lệ | Xác nhận invariant trên mọi mutator |

## 4. Ví dụ Java 17 hoàn chỉnh: kho chỗ ngồi bảo toàn invariant

Thay vì công khai `capacity` và `reserved`, ta tạo một đối tượng có trạng thái đóng kín:

- Sức chứa được đặt một lần trong constructor và không thay đổi.
- Đặt chỗ chỉ có thể thông qua `reserve(int seats)`.
- Hủy chỗ chỉ có thể thông qua `cancel(int seats)`.
- Không có API nào cho phép tự ý gán số chỗ đã đặt.
- Khi không đủ chỗ, `reserve` trả `false` và **không thay đổi trạng thái**.
- Số chỗ hợp lệ của thao tác phải dương; `cancel` không được hủy vượt số đã đặt.

Tạo tệp **`InvariantDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

// Một thiết kế lỗi để quan sát tác hại của public state.
final class BrokenSeatInventory {
    public int capacity;
    public int reserved;

    BrokenSeatInventory(int capacity) {
        this.capacity = capacity;
        this.reserved = 0;
    }

    int available() {
        return capacity - reserved;
    }
}

// Thiết kế có encapsulation và thao tác nghiệp vụ.
final class SeatInventory {
    private final int capacity;
    private int reserved;

    SeatInventory(int capacity) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be positive");
        }
        this.capacity = capacity;
        this.reserved = 0;
    }

    // synchronized làm cho toàn bộ kiểm tra + cập nhật là một critical section.
    synchronized boolean reserve(int seats) {
        requirePositive(seats);

        // Tránh reserved + seats gây overflow số nguyên.
        if (seats > capacity - reserved) {
            return false;
        }
        reserved += seats;
        return true;
    }

    synchronized void cancel(int seats) {
        requirePositive(seats);
        if (seats > reserved) {
            throw new IllegalArgumentException(
                    "cannot cancel more than reserved");
        }
        reserved -= seats;
    }

    synchronized int reserved() {
        return reserved;
    }

    synchronized int available() {
        return capacity - reserved;
    }

    int capacity() {
        return capacity;
    }

    private static void requirePositive(int seats) {
        if (seats <= 0) {
            throw new IllegalArgumentException("seats must be positive");
        }
    }
}

// Bảo vệ cả constructor và getter khỏi tham chiếu Set mutable bên ngoài.
final class PermissionSet {
    private final Set<String> permissions;

    PermissionSet(Set<String> input) {
        Objects.requireNonNull(input, "input");
        this.permissions = Set.copyOf(input);
    }

    Set<String> permissions() {
        return permissions; // Không sửa trực tiếp được.
    }

    boolean allows(String permission) {
        return permissions.contains(permission);
    }
}

public class InvariantDemo {
    public static void main(String[] args) {
        var broken = new BrokenSeatInventory(10);
        broken.reserved = 12;
        System.out.println("Broken available = " + broken.available());

        var seats = new SeatInventory(10);
        System.out.println("Reserve 4 = " + seats.reserve(4));
        System.out.println("Reserve 7 = " + seats.reserve(7));
        System.out.println("Available = " + seats.available());

        seats.cancel(2);
        System.out.println("Available after cancel = " + seats.available());

        Set<String> external = new HashSet<>(Set.of("READ"));
        PermissionSet policy = new PermissionSet(external);
        external.add("ADMIN"); // Thay đổi tập nguồn sau constructor.

        System.out.println("Policy has ADMIN = " + policy.allows("ADMIN"));

        try {
            policy.permissions().add("ADMIN");
        } catch (UnsupportedOperationException expected) {
            System.out.println("Permissions cannot be mutated externally");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac InvariantDemo.java
java InvariantDemo
~~~

Kết quả dự kiến:

~~~text
Broken available = -2
Reserve 4 = true
Reserve 7 = false
Available = 6
Available after cancel = 8
Policy has ADMIN = false
Permissions cannot be mutated externally
~~~

### Phân tích trạng thái từng bước

| Bước | Thao tác | `reserved` | `available` | Invariant |
|---|---|---:|---:|---|
| Khởi tạo | `new SeatInventory(10)` | 0 | 10 | Đúng |
| Đặt 4 | `reserve(4)` trả `true` | 4 | 6 | Đúng |
| Đặt thêm 7 | `reserve(7)` trả `false` | 4 | 6 | Đúng, trạng thái giữ nguyên |
| Hủy 2 | `cancel(2)` | 2 | 8 | Đúng |
| Hủy 5 | `cancel(5)` ném exception | 2 | 8 | Đúng, trạng thái giữ nguyên |

**Điểm quan trọng:** `SeatInventory` không có setter dạng `setReserved`; nó chỉ có những hành vi gắn với **ý nghĩa nghiệp vụ**. Constructor đảm bảo trạng thái ban đầu hợp lệ, còn mọi public mutator hợp lệ đều giữ được:

\[
0 \le \text{reserved} \le \text{capacity}
\]

Đây là một lập luận theo kiểu **quy nạp**:

1. **Cơ sở:** sau constructor, `reserved = 0` và `capacity > 0`.
2. **Bước đặt chỗ:** chỉ cộng khi `seats > 0` và `seats <= capacity - reserved`; vì vậy không vượt capacity.
3. **Bước hủy:** chỉ trừ khi `0 < seats <= reserved`; vì vậy không âm.
4. **Bảo toàn:** nếu trạng thái trước thao tác hợp lệ, trạng thái sau thao tác thành công vẫn hợp lệ. Đường lỗi không sửa state.

Lập luận đúng trong phạm vi các method được định nghĩa, với giả định không có code nào dùng reflection/native access để sửa field bất hợp lệ và không bỏ qua cơ chế đồng bộ của các method. Trong Java bình thường, quyền truy cập private giúp chặn các phép gán trực tiếp từ client.

### Vì sao lại có `synchronized`?

Nếu hai thread cùng đọc `reserved = 4` và cùng muốn đặt 4 chỗ, thao tác “kiểm tra rồi cộng” phải được xem như **một đơn vị**. Nếu thiếu đồng bộ, hai thread có thể đều thấy đủ chỗ, trả `true`, nhưng kết quả lưu lại và số booking thực tế có thể không nhất quán.

`synchronized` trên `reserve`, `cancel` và các phép đọc khiến chúng cùng dùng một monitor cho object, tạo quan hệ happens-before thích hợp trong phạm vi class. Đây là một minh họa quản lý concurrency **trong bộ nhớ một JVM**; nếu kho chỗ được lưu trong database và có nhiều instance ứng dụng, vẫn cần transaction/optimistic lock hoặc điều kiện cập nhật nguyên tử ở tầng lưu trữ. Không thể chỉ thêm `synchronized` ở một service instance rồi bảo đảm hết vấn đề race giữa nhiều node.

## 5. Lỗi khó thấy: field private nhưng trả về collection gốc

Xét một giỏ hàng:

~~~java
import java.util.ArrayList;
import java.util.List;

class LeakyCart {
    private final List<String> items = new ArrayList<>();

    LeakyCart() {
        items.add("SKU-1");
    }

    public List<String> getItems() {
        return items; // RÒ RỈ live mutable reference.
    }
}

LeakyCart cart = new LeakyCart();
cart.getItems().clear(); // Xóa trạng thái nội bộ từ ngoài class!
~~~

Đổi `items` thành `private final` **không giải quyết được** vì `final` chỉ ngăn đổi đối tượng `List` đang được tham chiếu, không ngăn việc sửa nội dung của nó.

Một cách sửa với phần tử `String` bất biến:

~~~java
final class SafeCart {
    private final List<String> items = new ArrayList<>();

    SafeCart() {
        items.add("SKU-1");
    }

    void addItem(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("Invalid SKU");
        }
        items.add(sku);
    }

    List<String> itemsSnapshot() {
        return List.copyOf(items);
    }
}
~~~

Giờ các đoạn sau sẽ không thể sửa giỏ hàng thông qua snapshot:

~~~java
SafeCart cart = new SafeCart();
List<String> readOnly = cart.itemsSnapshot();

// readOnly.add("SKU-2"); // Biên dịch được, nhưng runtime
// ném UnsupportedOperationException vì snapshot không sửa được.

cart.addItem("SKU-2");
System.out.println(readOnly);          // Vẫn chỉ [SKU-1].
System.out.println(cart.itemsSnapshot()); // [SKU-1, SKU-2].
~~~

Một snapshot cũng giúp phân biệt rõ **ảnh chụp tại thời điểm gọi** với **view có thể thay đổi theo dữ liệu gốc**. Nếu API thực sự cần live view, phải nêu rõ hợp đồng về thời điểm và concurrency, chứ không trả ngẫu nhiên một reference mutable.

## 6. Defensive copy trong constructor: chặn sửa thông qua alias

Một lớp có thể không lộ getter mà vẫn bị thay đổi thông qua object bên ngoài đã truyền vào:

~~~java
import java.util.List;

class BrokenTeam {
    private final List<String> members;

    BrokenTeam(List<String> members) {
        this.members = members; // Giữ alias do client sở hữu.
    }

    int size() {
        return members.size();
    }
}
~~~

Client còn giữ reference:

~~~java
List<String> external = new java.util.ArrayList<>(
        List.of("Lan", "Minh"));

BrokenTeam team = new BrokenTeam(external);
external.clear();

System.out.println(team.size()); // 0, dù Team không có mutator.
~~~

Nếu invariant là “nhóm phải có ít nhất một thành viên”, việc kiểm tra `!members.isEmpty()` trong constructor **không bảo đảm điều đó về sau**. Ta cần sao chép cấu trúc đầu vào và chỉ giữ một representation không sửa được:

~~~java
final class Team {
    private final List<String> members;

    Team(List<String> members) {
        java.util.Objects.requireNonNull(members);
        if (members.isEmpty()) {
            throw new IllegalArgumentException("Team must be nonempty");
        }

        // List.copyOf từ chối phần tử null và snapshot cấu trúc danh sách.
        this.members = List.copyOf(members);

        for (String name : this.members) {
            if (name.isBlank()) {
                throw new IllegalArgumentException("Blank member");
            }
        }
    }

    List<String> members() {
        return members; // Danh sách không thể sửa; String là immutable.
    }

    int size() {
        return members.size();
    }
}
~~~

Trong `Team` này, cả constructor lẫn getter đã bảo vệ được invariant dựa trên **cấu trúc danh sách và giá trị String bất biến**. Nếu phần tử là object mutable thì `List.copyOf` **không phải deep copy**: các object bên trong vẫn có thể bị sửa qua alias khác.

### Bẫy `Collections.unmodifiableList`

~~~java
List<String> external = new java.util.ArrayList<>(List.of("A"));
List<String> view = java.util.Collections.unmodifiableList(external);

external.add("B");
System.out.println(view); // [A, B]
~~~

`unmodifiableList` chỉ ngăn sửa **thông qua view**, không ngăn chủ sở hữu của list gốc sửa nó. Ngược lại, `List.copyOf(external)` tạo snapshot cấu trúc (nếu collection phù hợp), nên các thao tác `add/remove` về sau trên `external` không đổi snapshot.

| Cách bảo vệ | Chặn sửa qua giá trị trả về? | Tách khỏi thay đổi của collection gốc? | Chặn sửa object phần tử mutable? |
|---|---|---|---|
| Trả trực tiếp `items` | Không | Không | Không |
| `Collections.unmodifiableList(items)` | Có | Không, đây là view | Không |
| `List.copyOf(items)` | Có | Có, với thay đổi cấu trúc của source | Không |
| Copy sâu có kiểm soát | Tùy API | Có | Có, nếu mọi phần tử mutable liên quan được copy đúng |

**Vì vậy:** `private + final + getter` chưa đủ để kết luận object được đóng gói an toàn. Hãy vẽ **đồ thị tham chiếu**, xem ai còn có thể sửa vật thể nào.

## 7. Lớp con, record và getter/setter có thể phá invariant theo cách khác

### 7.1. Setter độc lập làm hỏng quy tắc liên quan nhiều field

Xét cửa sổ đặt lịch với `start < end`:

~~~java
import java.time.Instant;

class MutableWindow {
    private Instant start;
    private Instant end;

    MutableWindow(Instant start, Instant end) {
        setStart(start);
        setEnd(end);
    }

    void setStart(Instant start) {
        this.start = start;
    }

    void setEnd(Instant end) {
        this.end = end;
    }
}
~~~

Constructor gọi setter nhưng không kiểm tra quan hệ. Dù ta thêm validation ở mỗi setter, thay đổi một khoảng hợp lệ từ `10:00–11:00` sang `12:00–13:00` bằng `setStart(12:00)` trước có thể tạo trạng thái trung gian vô hiệu. Nếu kiểm tra chặt và ném exception, đôi khi client **không thể đổi theo thứ tự mong muốn**, dù trạng thái đích hợp lệ.

Thay vì hai setter, hãy chọn thao tác cập nhật cả hai trường cùng lúc, với kiểm tra trước khi ghi:

~~~java
import java.time.Instant;
import java.util.Objects;

final class BookingWindow {
    private Instant start;
    private Instant end;

    BookingWindow(Instant start, Instant end) {
        replace(start, end);
    }

    synchronized void replace(Instant nextStart, Instant nextEnd) {
        Objects.requireNonNull(nextStart, "start");
        Objects.requireNonNull(nextEnd, "end");

        if (!nextStart.isBefore(nextEnd)) {
            throw new IllegalArgumentException("start must be before end");
        }

        // Chỉ sửa state sau khi đã kiểm tra cặp giá trị mới.
        this.start = nextStart;
        this.end = nextEnd;
    }

    synchronized boolean contains(Instant point) {
        Objects.requireNonNull(point);
        return !point.isBefore(start) && point.isBefore(end);
    }
}
~~~

`BookingWindow` trong demo giữ hai field mutable để dạy về method cập nhật cặp. Đối với một value object không cần thay đổi sau tạo, thiết kế **immutable** còn đơn giản hơn:

~~~java
import java.time.Instant;
import java.util.Objects;

record ImmutableWindow(Instant start, Instant end) {
    ImmutableWindow {
        Objects.requireNonNull(start);
        Objects.requireNonNull(end);
        if (!start.isBefore(end)) {
            throw new IllegalArgumentException("Invalid interval");
        }
    }
}

// Thay đổi => tạo một ImmutableWindow mới hợp lệ.
~~~

### 7.2. Record không tự bảo đảm deep immutability

~~~java
record AccountRoles(java.util.List<String> roles) {}

var external = new java.util.ArrayList<>(java.util.List.of("READ"));
var roles = new AccountRoles(external);
external.add("ADMIN");

System.out.println(roles.roles()); // [READ, ADMIN]
~~~

`record` sinh constructor, accessor, `equals` và `toString` dựa trên các component, nhưng không tự copy một `List` mutable. Nếu muốn giữ snapshot:

~~~java
record SafeAccountRoles(java.util.List<String> roles) {
    SafeAccountRoles {
        roles = java.util.List.copyOf(
                java.util.Objects.requireNonNull(roles));
    }
}
~~~

Trong compact constructor, phép gán `roles = ...` thay đổi tham số dùng để khởi tạo field record; với list chứa `String` immutable, đây là cách bảo vệ hợp lý.

### 7.3. Kế thừa mở thêm đường thay đổi

Nếu lớp cha có field `protected` mutable:

~~~java
class InventoryBase {
    protected int reserved; // Lớp con có thể sửa mà không qua validation.
}
~~~

Một subclass có thể trực tiếp tăng/giảm và phá invariant của lớp cha. Nếu một lớp sở hữu invariant chặt, có thể dùng `private` state, các method kiểm soát thay đổi, và cân nhắc `final class` hoặc API kế thừa có hợp đồng rõ ràng. **`protected` không đồng nghĩa “chỉ dùng nội bộ trong chính lớp này”**.

Một override của method được gọi trong quá trình khởi tạo cũng có thể quan sát trạng thái subclass chưa hoàn tất. Tránh gọi method có thể override từ constructor khi invariant của lớp con chưa được thiết lập.

## 8. Sơ đồ luồng kiểm soát trạng thái

~~~mermaid
flowchart TD
    Client["Client"] --> Request["reserve(3)"]
    Request --> Preconditions{"seats > 0?"}
    Preconditions -->|Không| Reject["Ném IllegalArgumentException<br/>Không đổi state"]
    Preconditions -->|Có| Capacity{"seats <= capacity - reserved?"}
    Capacity -->|Không| NoChange["Trả false<br/>Giữ nguyên state"]
    Capacity -->|Có| Mutate["reserved += seats"]
    Mutate --> Done["Trả true<br/>Invariant được bảo toàn"]
~~~

Sơ đồ thể hiện đúng ranh giới: **Client gửi yêu cầu**, không trực tiếp ghi `reserved`. Chỉ đối tượng sở hữu trạng thái mới quyết định có được thay đổi hay không.

Khi một thao tác liên quan nhiều aggregate hoặc database, invariant cần được phân thành hai mức:

- **Invariant trong một object/aggregate:** có thể giữ bằng API, state riêng và đồng bộ thích hợp.
- **Invariant liên quan nhiều bản ghi hoặc nhiều hệ thống:** thường cần transaction, optimistic locking, unique constraint, outbox, idempotency hoặc những cơ chế nhất quán khác.

Encapsulation trong Java không thay thế database constraint. Ví dụ “không bán quá số vé” phải được bảo vệ cả khi hai node ứng dụng cùng đặt vé trên một database.

## 9. Kiểm thử invariant: phải thử cả đường thất bại và đường đi vòng

Nếu test chỉ kiểm tra `reserve(4)` trả `true`, ta chưa chứng minh được object an toàn. Cần kiểm tra **trạng thái không đổi sau yêu cầu bị từ chối**, đường mutation gián tiếp và các điều kiện biên.

Các test sau dùng JUnit Jupiter (JUnit 5), đặt cùng package với **`InvariantDemo.java`**:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;

class InvariantDemoTest {
    @Test
    void reservationCannotExceedCapacity() {
        SeatInventory inventory = new SeatInventory(10);

        assertTrue(inventory.reserve(4));
        assertFalse(inventory.reserve(7));

        assertEquals(4, inventory.reserved());
        assertEquals(6, inventory.available());
    }

    @Test
    void invalidCancelDoesNotChangeState() {
        SeatInventory inventory = new SeatInventory(10);
        assertTrue(inventory.reserve(3));

        assertThrows(IllegalArgumentException.class,
                () -> inventory.cancel(4));

        assertEquals(3, inventory.reserved());
        assertEquals(7, inventory.available());
    }

    @Test
    void invalidInitialAndOperationArgumentsAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> new SeatInventory(0));

        SeatInventory inventory = new SeatInventory(2);
        assertThrows(IllegalArgumentException.class,
                () -> inventory.reserve(0));
        assertThrows(IllegalArgumentException.class,
                () -> inventory.cancel(-1));

        assertEquals(2, inventory.available());
    }

    @Test
    void originalCollectionCannotMutatePermissionSnapshot() {
        Set<String> source = new HashSet<>(Set.of("READ"));
        PermissionSet policy = new PermissionSet(source);

        source.add("ADMIN");
        assertFalse(policy.allows("ADMIN"));

        assertThrows(UnsupportedOperationException.class,
                () -> policy.permissions().add("ADMIN"));
        assertFalse(policy.allows("ADMIN"));
    }
}
~~~

Đối với generic collection, nên bổ sung test khi phần tử là **object mutable**, không chỉ String. Đối với `BookingWindow`, hãy thử cập nhật một khoảng hợp lệ mới, cập nhật sai thứ tự và xác nhận trường cũ vẫn giữ nguyên sau exception.

**Cần test cả ranh giới concurrency khi có yêu cầu:** nhiều thread cùng đặt chỗ, nhưng không chỉ dựa vào một vài lần chạy để “chứng minh thread-safe”. Có thể dùng test đồng bộ với latch, stress test, kiểm tra race bằng công cụ chuyên dụng và xác minh transaction ở tầng lưu trữ.

### Một test chuyên biệt cho atomic update

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class BookingWindowTest {
    @Test
    void invalidReplacementLeavesPreviousIntervalIntact() {
        Instant ten = Instant.parse("2026-10-15T10:00:00Z");
        Instant eleven = Instant.parse("2026-10-15T11:00:00Z");
        Instant twelve = Instant.parse("2026-10-15T12:00:00Z");

        BookingWindow window = new BookingWindow(ten, eleven);

        assertThrows(IllegalArgumentException.class,
                () -> window.replace(twelve, eleven));

        assertTrue(window.contains(ten));
        assertFalse(window.contains(twelve));
    }
}
~~~

Test này xác minh cả **hậu điều kiện của đường lỗi**: một lệnh cập nhật bị từ chối không được để lại trạng thái một nửa. Lưu ý `Instant` không mang múi giờ địa phương, còn chuỗi `Z` là UTC; giá trị ngày giờ ở đây chỉ dùng làm dữ liệu ví dụ.

## 10. Phân biệt invariant, immutability và thread safety

Ba thuộc tính hỗ trợ nhau nhưng **không đồng nghĩa**:

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| **Invariant** | Quy tắc trạng thái phải đúng | `0 <= reserved <= capacity` |
| **Encapsulation** | Kiểm soát ai được đọc/ghi và qua API nào | `reserved` là private, thay đổi qua `reserve` |
| **Immutability** | Trạng thái quan sát được không đổi sau khởi tạo | `ImmutableWindow` với hai `Instant` |
| **Thread safety** | Hành vi đúng khi nhiều thread cùng sử dụng theo hợp đồng | `SeatInventory` bảo vệ cả check và update bằng `synchronized` |

Một object mutable vẫn có thể luôn giữ invariant; `SeatInventory` chính là ví dụ. Một object immutable được tạo với dữ liệu sai vẫn **có thể vi phạm invariant mãi mãi** nếu constructor không validation. Và một class có các method kiểm tra invariant đúng khi gọi tuần tự vẫn có thể gặp race condition nếu gọi đồng thời mà không có bảo vệ.

`private` là công cụ **ẩn dữ liệu khỏi mã bên ngoài**, không phải cơ chế đồng bộ bộ nhớ. `final` trên reference là một phần của thiết kế bất biến, nhưng không biến collection mutable thành immutable.

## 11. Khi nào cần getter/setter, khi nào nên dùng hành vi nghiệp vụ?

Không phải setter nào cũng xấu. Với DTO, JavaBeans, form binding hay cấu hình, getter/setter có thể là lựa chọn thực dụng. Nhưng khi object **sở hữu invariant hoặc hành vi nghiệp vụ**, setter “đưa gì cũng nhận” thường là dấu hiệu nên xem xét lại API.

| Mô hình | API thường hợp lý | Ghi chú |
|---|---|---|
| DTO nhập liệu chưa xác thực | Field/bean properties theo framework | Validation thực hiện tại boundary trước khi tạo domain object |
| Domain entity có quy tắc trạng thái | `pay()`, `cancel()`, `reserve(n)` | Thao tác diễn đạt nghiệp vụ, giữ invariant |
| Value object | Constructor/factory validation, không có mutator | Giá trị mới thường tạo object mới |
| Collection nội bộ | `addItem`, `removeItem`, snapshot | Không rò rỉ mutable collection gốc |
| Cặp field phải cập nhật cùng nhau | `replaceWindow(start,end)` | Kiểm tra tổ hợp trước khi công bố state |

Trước khi thêm `setStatus(String status)` vào một entity, hãy hỏi **những chuyển trạng thái nào thực sự hợp lệ?** Chẳng hạn đơn hàng từ `PAID` không thể tùy ý trở lại `CREATED` chỉ vì một setter nhận chuỗi đó.

## 12. Checklist review mã nguồn: tìm mọi đường phá invariant

Khi đánh giá một class có state, hãy lần lượt kiểm tra:

1. **Viết invariant thành câu hoặc biểu thức cụ thể.** Nếu chưa nói được “trạng thái hợp lệ” là gì, rất khó bảo vệ.
2. **Constructor/factory:** Có từ chối giá trị sai? Có copy những object mutable do caller truyền vào?
3. **Field:** Có mutable field `public`/`protected`? `final` chỉ áp dụng cho tham chiếu hay cho toàn bộ giá trị?
4. **Getter:** Có trả collection, array, `Date` hoặc mutable object nội bộ không?
5. **Setter/mutator:** Có thể sửa một field làm mâu thuẫn với field khác? Có kiểm tra *trước* khi ghi?
6. **Method override:** Subclass có thể bỏ qua validation hoặc truy cập state bằng một con đường khác không?
7. **Serialization/ORM/framework:** Framework có thể tạo và khôi phục đối tượng qua reflection hay persistence mapping không? Nếu có, validation phải được áp dụng ở boundary/hook thích hợp mà không phá hợp đồng framework.
8. **Concurrency:** Có thể nhiều thread truy cập cùng instance? Nếu có, kiểm tra check-then-act, memory visibility và atomicity.
9. **Đa hệ thống:** Invariant có phụ thuộc DB, cache hoặc một service khác không? Thiết kế constraint và cơ chế nhất quán ở đúng tầng.
10. **Test:** Có kiểm tra đường lỗi giữ nguyên state, mutation thông qua alias, phần tử mutable và các trạng thái biên chưa?

### Đừng “sửa” bằng cách khóa mọi trường thành private rồi bỏ hết hành vi

Nếu chỉ thay field public bằng setter/getter bọc quanh field:

~~~java
class WeakInventory {
    private int reserved;

    void setReserved(int value) {
        this.reserved = value; // Không có quy tắc nào được bảo vệ.
    }

    int getReserved() {
        return reserved;
    }
}
~~~

thiết kế vẫn cho phép truyền `-50` hay `1_000_000`. Tốt hơn là xác định **trạng thái hợp lệ** và **những thao tác được phép**. Đóng gói không có nghĩa “mỗi field đều có getter/setter”; nó là **giữ quyền quyết định về invariant trong chính object**.

## 13. Bài tập thực hành: số lượng tồn kho và đặt hàng

Hãy thiết kế một lớp `StockItem` có:

- `sku` là chuỗi ID không rỗng, không thay đổi sau khởi tạo.
- `onHand` là số lượng hàng hiện có, không âm.
- `reserved` là số lượng đang giữ cho đơn, không âm và không vượt `onHand`.
- Không công khai các field mutable.
- Có `reserve(n)`, `release(n)`, `receive(n)` và `shipReserved(n)`.

**Yêu cầu về trạng thái:**

\[
0 \le \text{reserved} \le \text{onHand}
\]

`shipReserved(n)` cần giảm **cả** `reserved` và `onHand` sau khi xác minh yêu cầu hợp lệ; không được giảm một trường rồi thất bại ở trường kia. `receive(n)` tăng số hàng hiện có và cần xử lý tràn số nguyên nếu dùng `int` (có thể dùng `Math.addExact` hoặc kiểm tra trước). `reserve(n)` không được giữ vượt hàng khả dụng `onHand - reserved`.

Viết unit tests cho ít nhất:

- Khởi tạo với `onHand < 0` bị từ chối.
- Đặt số lượng lớn hơn khả dụng bị từ chối, state không đổi.
- Xuất hàng từ lượng reserved cập nhật cả hai số đúng.
- Xuất vượt reserved không làm thay đổi bất kỳ field nào.
- Hai lệnh đặt đồng thời không được cùng tiêu thụ một đơn vị cuối cùng trong một kho chung.
- Nếu lưu kho trên DB, mô tả cách bảo vệ invariant khi nhiều ứng dụng chạy ở các node khác nhau.

### Câu hỏi tự kiểm tra

1. Vì sao việc `inventory.reserved = 12` biên dịch được chưa chứng minh trạng thái hợp lệ?
2. Khác nhau giữa tiền điều kiện `seats > 0` và invariant `reserved <= capacity`?
3. Vì sao `private final List<?>` vẫn có thể bị sửa từ bên ngoài?
4. `Collections.unmodifiableList(source)` khác `List.copyOf(source)` ở điểm nào?
5. Nếu `List.copyOf` chứa phần tử là object mutable, object có được deep immutable không?
6. Vì sao hai setter `setStart` và `setEnd` có thể gây trạng thái trung gian sai?
7. Khi nào record vẫn để rò rỉ reference mutable?
8. `synchronized` trên một object Java có bảo đảm kho vé trên nhiều JVM không?
9. Với một entity nghiệp vụ, khi nào `reserve(n)` tốt hơn `setReserved(n)`?

**Kết luận:** **Invariant là lời cam kết rằng đối tượng không bị đẩy vào trạng thái mâu thuẫn qua những API được công bố.** Để giữ lời cam kết ấy, không chỉ giấu field mà còn phải kiểm soát **mọi đường thay đổi và mọi tham chiếu mutable**: constructor, getter, mutator, subclass và concurrency. Hãy thiết kế thao tác theo nghiệp vụ, xác thực trước khi cập nhật, bảo vệ alias và kiểm thử rằng cả thành công lẫn thất bại đều để đối tượng trong trạng thái hợp lệ.