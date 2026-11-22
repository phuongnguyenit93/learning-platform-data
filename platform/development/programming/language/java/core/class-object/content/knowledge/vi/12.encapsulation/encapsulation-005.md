# Ngăn trạng thái dở dang khi thao tác có thể thất bại trong Java

## 1. Vấn đề: một object có thể bị sửa một nửa rồi method ném lỗi

**Đóng gói (encapsulation)** không chỉ là đặt field `private`. Đóng gói còn là việc một class kiểm soát **những trạng thái nào được phép tồn tại** và **đường chuyển từ trạng thái hợp lệ này sang trạng thái hợp lệ khác**. Nếu một method thay đổi nhiều field hoặc nhiều object rồi gặp lỗi giữa chừng, caller có thể nhìn thấy một **trạng thái dở dang** (*partially updated state*): dữ liệu đã bị sửa một phần nhưng thao tác nghiệp vụ chưa hoàn tất.

Ví dụ một tài khoản có:

- `balance`: số dư hiện tại, không âm.
- `reserved`: tiền đang được giữ, không âm và không vượt `balance`.
- `available = balance - reserved`: số tiền có thể chi.

Giả sử method cần chuyển tiền vào phần giữ chỗ nhưng lại sửa trước, kiểm tra sau:

```java
class Account {
    private int balance = 100;
    private int reserved = 20;

    void reserveBadly(int amount) {
        reserved += amount;             // Đã thay state.
        if (reserved > balance) {       // Kiểm tra quá muộn.
            throw new IllegalArgumentException("not enough balance");
        }
    }
}
```

Nếu caller gọi `reserveBadly(90)`, method ném exception vì `reserved` thành 110 lớn hơn `balance` 100. **Nhưng trước khi ném lỗi, field `reserved` đã thành 110**. Object không tự quay về trạng thái cũ chỉ vì có `throw`.

Sơ đồ:

```text
Trước thao tác (hợp lệ)
balance = 100
reserved = 20
available = 80

     reserveBadly(90)
             |
             v
reserved = 110            <-- Đã thay đổi!
             |
             v
if (110 > 100) throw ...
             |
             v
Caller nhận exception, nhưng object:
balance = 100
reserved = 110            <-- Trạng thái sai vẫn còn
available = -10
```

Nếu những method khác vẫn tiếp tục làm việc với object này, lỗi có thể lan sang các thao tác sau. **Ngăn trạng thái dở dang** là thiết kế method sao cho lỗi được phát hiện **trước khi trạng thái bị thay đổi**, hoặc nếu đã thay đổi thì có cơ chế bảo đảm đối tượng vẫn ở trạng thái hợp lệ/được phục hồi theo đúng hợp đồng.

> **Mục tiêu thiết kế:** với các lỗi mà API có chủ đích phát hiện và xử lý, thao tác nên **hoàn tất trọn vẹn** hoặc **để lại trạng thái như trước** khi có thể; ít nhất không được làm hỏng những bất biến (*invariants*) đã cam kết.

## 2. Ba khái niệm phải tách bạch

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Bất biến đối tượng (*invariant*)** | Trạng thái nào phải đúng tại những điểm quan sát hợp lệ? | `0 <= reserved <= balance` |
| **Tính an toàn khi thất bại (*failure/exception safety*)** | Nếu method không hoàn tất, state còn hợp lệ và có giữ nguyên không? | Rút tiền thất bại không được trừ tiền |
| **Tính nguyên tử đồng thời (*concurrency atomicity*)** | Thread khác có thấy các bước trung gian không? | Hai field phải được đọc/ghi dưới cùng cơ chế đồng bộ |

Chúng **liên quan nhưng không đồng nhất**:

- `private` giới hạn quyền truy cập field trong source code, **không tự bảo đảm method cập nhật các field đúng thứ tự**.
- `throw new Exception(...)` **không tự rollback** các phép gán đã thực hiện.
- `try/catch` cho phép xử lý lỗi; bản thân nó **không tạo transaction**.
- `synchronized` giúp phối hợp thread dùng cùng monitor, nhưng **không tự khôi phục state** khi method ném lỗi.
- Ghi đồng thời nhiều field trong một method **không tự biến toàn bộ chuỗi ghi thành một thao tác nguyên tử**.
- Một thao tác thành công trong RAM **không tự bảo đảm dữ liệu đã được commit bền vững** vào file, database hoặc dịch vụ ngoài.

Bài này tập trung vào **thiết kế hướng đối tượng Java**: tránh tạo hoặc để lộ trạng thái sai khi method/constructor có thể thất bại, sau đó chỉ ra ranh giới với concurrency và hệ thống ngoài tiến trình.

## 3. Mức bảo đảm khi thao tác thất bại

Khi thiết kế API, có thể phân biệt một số mức bảo đảm:

| Mức | Ý nghĩa |
| --- | --- |
| **Không có bảo đảm rõ ràng** | Sau lỗi, object có thể ở trạng thái chưa xác định theo contract, kể cả sai invariant |
| **Basic guarantee** | Object vẫn ở trạng thái **hợp lệ theo invariant**, nhưng có thể đã thay đổi một phần |
| **Strong guarantee** | Nếu thao tác thất bại, các trạng thái quan sát được mà contract bao phủ **không thay đổi**; thành công thì cập nhật theo cam kết |
| **No-fail guarantee** | Một thao tác cụ thể được thiết kế **không thất bại** trong các điều kiện đã định |

Đây là các khái niệm về **thiết kế hợp đồng**, không phải mức được Java tự gắn cho mọi method. “Strong guarantee” cần nói rõ **phạm vi**: chỉ field nội bộ, hay cả file, event, log nghiệp vụ, database và dịch vụ khác?

Ví dụ nếu method gửi email rồi mới thất bại khi ghi database, việc hoàn tác field trong RAM **không thu hồi email đã gửi**. Do đó không được tuyên bố “all-or-nothing” cho toàn hệ thống chỉ vì đã sao lưu vài field.

Trong nhiều lớp nghiệp vụ, mục tiêu thực tế là: **input không hợp lệ, exception validation hoặc lỗi tính toán có thể dự đoán được sẽ không làm đổi state nội bộ**. Đây là một hợp đồng hữu ích và kiểm thử được.

## 4. Kỹ thuật đầu tiên: kiểm tra trước khi sửa (*validate before mutate*)

Nếu tất cả điều kiện hợp lệ có thể được kiểm tra từ state hiện tại và input, nên thực hiện validation **trước phép gán gây tác động**.

Phiên bản sửa `reserveBadly`:

```java
class Account {
    private int balance = 100;
    private int reserved = 20;

    void reserve(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        if (amount > balance - reserved) {
            throw new IllegalArgumentException("not enough available balance");
        }
        reserved += amount;
    }

    int available() {
        return balance - reserved;
    }
}
```

Giả sử state đầu hợp lệ, phương thức `reserve(90)` sẽ kiểm tra `90 > 80`, ném exception **trước khi ghi `reserved`**. Field vẫn là `20`.

Điều kiện `amount > balance - reserved` tránh phải tính `reserved + amount` trước kiểm tra và, khi invariant `0 <= reserved <= balance` đúng, tránh một số trường hợp overflow của phép cộng. Nhưng nếu dữ liệu có thể sai ngay từ đầu, method còn cần xử lý **precondition state** và chọn kiểu số đủ miền giá trị.

### Ví dụ hoàn chỉnh với stdout

Lưu vào **`ReserveSafelyDemo.java`**:

```java
class Account {
    private final int balance;
    private int reserved;

    Account(int balance, int reserved) {
        if (balance < 0 || reserved < 0 || reserved > balance) {
            throw new IllegalArgumentException("invalid opening state");
        }
        this.balance = balance;
        this.reserved = reserved;
    }

    void reserve(int amount) {
        if (amount <= 0 || amount > balance - reserved) {
            throw new IllegalArgumentException("cannot reserve " + amount);
        }
        reserved += amount;
    }

    String snapshot() {
        return "balance=" + balance
                + ", reserved=" + reserved
                + ", available=" + (balance - reserved);
    }
}

public class ReserveSafelyDemo {
    public static void main(String[] args) {
        Account account = new Account(100, 20);
        System.out.println("before: " + account.snapshot());

        try {
            account.reserve(90);
        } catch (IllegalArgumentException ex) {
            System.out.println("failed: " + ex.getMessage());
        }

        System.out.println("after failure: " + account.snapshot());
        account.reserve(30);
        System.out.println("after success: " + account.snapshot());
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac ReserveSafelyDemo.java
java ReserveSafelyDemo
```

Output:

```text
before: balance=100, reserved=20, available=80
failed: cannot reserve 90
after failure: balance=100, reserved=20, available=80
after success: balance=100, reserved=50, available=50
```

Bài học từ ví dụ:

1. Constructor xác nhận invariant ngay khi object được tạo.
2. `reserve` xác nhận input và available balance **trước mutation**.
3. Khi validation ném exception, `reserved` giữ nguyên.
4. Khi thành công, chỉ một field cần đổi nên dễ bảo toàn invariant.

**Không nên** dùng validation sau khi sửa rồi “đợi caller bắt exception để sửa lại”. Caller không nhất thiết biết object đã đổi những gì; trách nhiệm giữ invariant nên nằm bên trong lớp sở hữu state.

## 5. Kiểm tra trước chưa đủ nếu chính phép tính có thể thất bại

Một đoạn nhìn có vẻ đã validate vẫn có thể bị lỗi số học:

```java
class BadCounter {
    private int count = Integer.MAX_VALUE;

    void add(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        count += amount; // int có thể overflow.
    }
}
```

Với `count = Integer.MAX_VALUE` và `amount = 1`, phép cộng `int` trong Java **overflow theo quy tắc số nguyên**, cho kết quả âm thay vì tự ném exception. Vì vậy validation “amount không âm” **không bảo vệ** invariant count không âm.

Một cách đúng khi mong muốn từ chối overflow là **tính trước bằng `Math.addExact`**:

```java
class SafeCounter {
    private int count;

    SafeCounter(int initial) {
        if (initial < 0) {
            throw new IllegalArgumentException("negative initial");
        }
        count = initial;
    }

    void add(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        int next = Math.addExact(count, amount);
        count = next;
    }

    int count() {
        return count;
    }
}
```

`Math.addExact` ném `ArithmeticException` nếu kết quả `int` không biểu diễn được. Quan trọng: `next` được tính **trước `count = next`**, nên lỗi số học không làm field bị sửa.

### Ví dụ chạy xác nhận overflow không làm đổi state

Tệp **`OverflowSafetyDemo.java`**:

```java
public class OverflowSafetyDemo {
    private int count;

    OverflowSafetyDemo(int count) {
        this.count = count;
    }

    void add(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("negative");
        }
        int next = Math.addExact(count, amount);
        count = next;
    }

    public static void main(String[] args) {
        OverflowSafetyDemo counter =
                new OverflowSafetyDemo(Integer.MAX_VALUE);

        try {
            counter.add(1);
        } catch (ArithmeticException ex) {
            System.out.println("overflow");
        }

        System.out.println(counter.count);
    }
}
```

```bash
javac OverflowSafetyDemo.java
java OverflowSafetyDemo
```

```text
overflow
2147483647
```

Cần phân biệt **precondition validation** (`amount >= 0`) và **safe computation** (`Math.addExact`). Cả hai đều cần khi muốn trạng thái không vượt miền dữ liệu.

Với tiền tệ, nên cân nhắc đơn vị nguyên nhỏ nhất bằng `long` khi phù hợp hoặc `BigDecimal` với quy tắc precision, scale và rounding rõ ràng; đừng để lỗi biểu diễn số làm invariant bị phá.

## 6. Nhiều field phụ thuộc nhau: tính toàn bộ trạng thái mới trước khi commit

Một object có thể có nhiều field liên quan:

```text
Inventory
- stock    : tổng số hàng
- reserved : số đã đặt
- available = stock - reserved
Bất biến: stock >= 0, reserved >= 0, reserved <= stock
```

Nếu method đổi cả `stock` và `reserved`, code kiểu:

```java
// stock -= amount;
// reserved -= amount;
// kiểm tra điều kiện ở cuối...
```

có nguy cơ gặp lỗi sau một phép gán nhưng trước phép gán còn lại.

**Kỹ thuật nên dùng:** **calculate → validate → commit**:

1. Đọc state hiện tại.
2. Tính **các giá trị dự kiến** vào local variables, không sửa object.
3. Kiểm tra điều kiện, giới hạn số học và invariant của **toàn bộ trạng thái dự kiến**.
4. Chỉ khi tất cả hợp lệ mới gán field theo kế hoạch.

Ví dụ:

```java
class Inventory {
    private int stock;
    private int reserved;

    Inventory(int stock, int reserved) {
        if (stock < 0 || reserved < 0 || reserved > stock) {
            throw new IllegalArgumentException("invalid inventory");
        }
        this.stock = stock;
        this.reserved = reserved;
    }

    void shipReserved(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        int nextStock = Math.subtractExact(stock, amount);
        int nextReserved = Math.subtractExact(reserved, amount);

        if (nextStock < 0 || nextReserved < 0
                || nextReserved > nextStock) {
            throw new IllegalArgumentException("cannot ship " + amount);
        }

        stock = nextStock;
        reserved = nextReserved;
    }

    String summary() {
        return "stock=" + stock + ", reserved=" + reserved;
    }
}
```

Toàn bộ lỗi được dự kiến xử lý (amount không hợp lệ, thiếu reserved hàng, overflow) xảy ra **trước hai assignment**. Sau đó là hai phép gán field đơn giản.

**Giới hạn phải nói rõ:** hai phép gán `stock = ...` và `reserved = ...` **không được Java mặc nhiên gộp thành một thao tác nguyên tử cho các thread khác**. Trong một luồng với dữ liệu hợp lệ và không có can thiệp ngoài, chúng bảo vệ mạnh trước các exception đã kiểm tra. Muốn thread khác không đọc state trung gian, phải dùng cùng chiến lược đồng bộ cho các đường đọc/ghi.

### Chương trình runnable: lỗi không làm hỏng hai field

Tệp **`InventoryCommitDemo.java`**:

```java
class Inventory {
    private int stock;
    private int reserved;

    Inventory(int stock, int reserved) {
        if (stock < 0 || reserved < 0 || reserved > stock) {
            throw new IllegalArgumentException("invalid state");
        }
        this.stock = stock;
        this.reserved = reserved;
    }

    void shipReserved(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("invalid amount");
        }

        int nextStock = Math.subtractExact(stock, amount);
        int nextReserved = Math.subtractExact(reserved, amount);

        if (nextStock < 0 || nextReserved < 0
                || nextReserved > nextStock) {
            throw new IllegalArgumentException("not enough reserved");
        }

        stock = nextStock;
        reserved = nextReserved;
    }

    String snapshot() {
        return stock + "/" + reserved;
    }
}

public class InventoryCommitDemo {
    public static void main(String[] args) {
        Inventory inventory = new Inventory(10, 4);
        System.out.println("before=" + inventory.snapshot());

        try {
            inventory.shipReserved(6);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected");
        }

        System.out.println("after reject=" + inventory.snapshot());
        inventory.shipReserved(3);
        System.out.println("after ship=" + inventory.snapshot());
    }
}
```

```bash
javac InventoryCommitDemo.java
java InventoryCommitDemo
```

```text
before=10/4
rejected
after reject=10/4
after ship=7/1
```

Khi `shipReserved(6)` tính `nextReserved=-2`, validation ném lỗi trước khi sửa field. `shipReserved(3)` tính `nextStock=7`, `nextReserved=1`, cả hai hợp lệ và được gán trong pha commit.

## 7. Một field immutable state: thay cả snapshot thay vì sửa nhiều field rời

Nếu trạng thái liên quan có thể gói thành **một value object bất biến**, có thể xây state mới rồi **thay một tham chiếu duy nhất**. Kỹ thuật này thường đơn giản hóa việc bảo đảm object không lộ **một nửa trạng thái cũ, một nửa trạng thái mới**.

Trong Java 17+, `record` là một cách tạo kiểu dữ liệu bất biến ở mức field references (nhưng vẫn phải cẩn thận nếu component trỏ mutable object).

Ví dụ:

```java
record BalanceState(int balance, int reserved) {
    BalanceState {
        if (balance < 0 || reserved < 0 || reserved > balance) {
            throw new IllegalArgumentException("invalid balance state");
        }
    }
}
```

Một lớp sở hữu state:

```java
class Account {
    private BalanceState state = new BalanceState(100, 20);

    void reserve(int amount) {
        if (amount <= 0 || amount > state.balance() - state.reserved()) {
            throw new IllegalArgumentException("invalid reserve");
        }

        BalanceState next = new BalanceState(
                state.balance(),
                Math.addExact(state.reserved(), amount)
        );
        state = next;
    }

    BalanceState snapshot() {
        return state;
    }
}
```

Trong ví dụ **mã lớp hợp lệ nhưng không có main**, constructor `BalanceState` kiểm tra invariant. Nếu tạo `next` thất bại, field `state` vẫn trỏ snapshot cũ. Chỉ sau khi tạo giá trị mới hợp lệ, `state = next` mới diễn ra.

**Đây là “build new state, then replace”**, rất hữu ích khi state gồm nhiều thuộc tính liên quan. Tuy nhiên với concurrent access, phải có chiến lược visibility/atomic update phù hợp (ví dụ đồng bộ hóa hoặc CAS). Chỉ dùng field tham chiếu và record **không tự ngăn lost updates khi nhiều thread cùng thay state**.

### Ví dụ chạy độc lập với record

Tạo **`SnapshotStateDemo.java`**:

```java
record State(int stock, int reserved) {
    State {
        if (stock < 0 || reserved < 0 || reserved > stock) {
            throw new IllegalArgumentException("invalid state");
        }
    }

    @Override
    public String toString() {
        return stock + "/" + reserved;
    }
}

class Warehouse {
    private State state = new State(8, 3);

    void ship(int amount) {
        State current = state;

        State next = new State(
                Math.subtractExact(current.stock(), amount),
                Math.subtractExact(current.reserved(), amount)
        );

        state = next;
    }

    String snapshot() {
        return state.toString();
    }
}

public class SnapshotStateDemo {
    public static void main(String[] args) {
        Warehouse warehouse = new Warehouse();
        System.out.println("before=" + warehouse.snapshot());

        try {
            warehouse.ship(5);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected");
        }

        System.out.println("after failure=" + warehouse.snapshot());
        warehouse.ship(2);
        System.out.println("after success=" + warehouse.snapshot());
    }
}
```

```bash
javac SnapshotStateDemo.java
java SnapshotStateDemo
```

```text
before=8/3
rejected
after failure=8/3
after success=6/1
```

- `warehouse.ship(5)` tính `State(3,-2)`, bị compact constructor của `State` từ chối **trước `state = next`**.
- `ship(2)` tạo `State(6,1)` hợp lệ rồi thay state.
- `State` là record với primitive components, nên giữ một snapshot có trạng thái logic ổn định và không lộ setter cho caller.

Ở ví dụ này, `ship` chưa kiểm `amount > 0`, nên nếu muốn sản phẩm thật phải bổ sung precondition ấy. Để chương trình chủ động từ chối giá trị âm/0 trước phép tính, có thể thêm `if (amount <= 0) throw ...`. Đây là **giới hạn hợp đồng minh họa**, không nên nhầm rằng `State` tự kiểm được ngữ nghĩa “số lượng giao hàng phải dương”.

## 8. Cập nhật collection: sai lầm “add trước, validate sau”

Một lỗi rất thường gặp là thêm phần tử rồi mới kiểm tra giới hạn:

```java
class Team {
    private final java.util.List<String> members =
            new java.util.ArrayList<>();

    void addBadly(String name) {
        members.add(name);
        if (members.size() > 3) {
            throw new IllegalStateException("team is full");
        }
    }
}
```

Nếu đã có ba người, lời gọi `addBadly("D")` thêm người thứ tư rồi ném exception. Team vẫn giữ bốn người, vi phạm quy tắc tối đa ba.

**Cách sửa cơ bản:**

```java
void addSafely(String name) {
    if (name == null || name.isBlank()) {
        throw new IllegalArgumentException("blank name");
    }
    if (members.size() >= 3) {
        throw new IllegalStateException("team is full");
    }
    members.add(name);
}
```

Method ở trên là **mảnh code cần đặt trong lớp `Team` có field `members`**. Nó kiểm tra điều kiện trước `add`.

Nhưng còn một vấn đề: một collection tùy chỉnh hoặc dependency ngoài có thể ném lỗi **trong lúc mutation**, hoặc nhiều thread cùng gọi method. Vì thế *validate-before-mutate* là giải pháp tốt khi ta kiểm soát object và failure modes, **không bảo đảm mạnh một cách tự động cho mọi collection/API**.

## 9. Copy → sửa bản sao → kiểm tra → công bố

Với một collection mà việc cập nhật có nhiều bước có thể thất bại, cách an toàn thường là **làm việc trên bản sao tạm** rồi chỉ thay tham chiếu gốc khi kết quả hoàn chỉnh.

Tạo tệp **`CopyThenCommitDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

class Roster {
    private List<String> members = List.of("An");

    void addBatch(List<String> incoming) {
        if (incoming == null) {
            throw new IllegalArgumentException("incoming required");
        }

        List<String> candidate = new ArrayList<>(members);

        for (String name : incoming) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("invalid member");
            }
            if (candidate.contains(name)) {
                throw new IllegalArgumentException("duplicate: " + name);
            }
            candidate.add(name);
        }

        if (candidate.size() > 3) {
            throw new IllegalStateException("too many members");
        }

        members = List.copyOf(candidate);
    }

    List<String> members() {
        return members;
    }
}

public class CopyThenCommitDemo {
    public static void main(String[] args) {
        Roster roster = new Roster();
        System.out.println("before=" + roster.members());

        try {
            roster.addBatch(List.of("Binh", "Binh"));
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }

        System.out.println("after failure=" + roster.members());
        roster.addBatch(List.of("Binh", "Chi"));
        System.out.println("after success=" + roster.members());
    }
}
```

```bash
javac CopyThenCommitDemo.java
java CopyThenCommitDemo
```

```text
before=[An]
rejected: duplicate: Binh
after failure=[An]
after success=[An, Binh, Chi]
```

Giải thích:

1. `members` ban đầu là immutable list `["An"]`.
2. `candidate = new ArrayList<>(members)` tạo **list structure mới**.
3. Với batch `["Binh","Binh"]`, candidate đã được thêm một Binh, nhưng lần gặp thứ hai bị từ chối. **Chỉ candidate bị thay đổi**, field `members` vẫn tham chiếu list gốc.
4. Với batch hợp lệ, tạo `List.copyOf(candidate)` trước, rồi **thay một field `members`** ở cuối.
5. Getter trả list unmodifiable; caller không thể thay structure qua `members().add(...)` thông thường.

**Lưu ý về bản sao nông:** `new ArrayList<>(members)` và `List.copyOf` sao chép references tới element objects, không deep-copy mọi object. Ở đây phần tử là `String` immutable nên phù hợp. Với `List<Person>` chứa `Person` mutable, nếu bạn gọi `person.rename(...)` trong lúc chuẩn bị candidate, các mutation ấy vẫn có thể lộ sang list cũ. Muốn mạnh hơn phải **không mutate shared elements**, hoặc deep-copy theo hợp đồng.

**Lưu ý concurrency:** một thread khác có thể cũng gọi `addBatch` giữa lúc đọc `members` và commit. Nếu không có đồng bộ, hai lần thay state có thể làm mất cập nhật; giải pháp snapshot chỉ tập trung vào **failure safety một luồng**, chưa giải quyết tranh chấp concurrent writes.

## 10. Một thao tác có nhiều object: chuyển giá trị giữa hai tài khoản

Với giao dịch chuyển tiền, hai object phải đổi trạng thái theo cùng một ý nghĩa nghiệp vụ:

```text
Trước: source = 100; destination = 20
Chuyển 30
Sau : source = 70;  destination = 50
```

Lỗi thiết kế đơn giản:

```java
// source.withdraw(30);         // Đã trừ source.
// destination.deposit(30);     // Có thể thất bại.
// => source đã giảm nhưng destination chưa tăng.
```

Nếu bước thứ hai ném exception vì overflow, validation riêng hoặc lỗi dịch vụ, chuyển tiền trở thành **nửa giao dịch**.

### Phương án cho state RAM: tính cả hai kết quả trước khi thay

Trong trường hợp hai tài khoản chỉ có primitive balance trong cùng tiến trình và tất cả đường truy cập đều tuân thủ chung cơ chế khóa, ta có thể tính trước kết quả rồi commit các field dưới khóa.

Tệp **`SafeTransferDemo.java`**:

```java
final class Account {
    private static final Object LOCK = new Object();
    private int balance;

    Account(int balance) {
        if (balance < 0) {
            throw new IllegalArgumentException("negative opening balance");
        }
        this.balance = balance;
    }

    static void transfer(Account from, Account to, int amount) {
        if (from == null || to == null) {
            throw new IllegalArgumentException("account required");
        }
        if (from == to) {
            throw new IllegalArgumentException("same account");
        }
        if (amount <= 0) {
            throw new IllegalArgumentException("positive amount required");
        }

        synchronized (LOCK) {
            if (amount > from.balance) {
                throw new IllegalArgumentException("insufficient funds");
            }

            int nextFrom = Math.subtractExact(from.balance, amount);
            int nextTo = Math.addExact(to.balance, amount);

            from.balance = nextFrom;
            to.balance = nextTo;
        }
    }

    int balance() {
        synchronized (LOCK) {
            return balance;
        }
    }
}

public class SafeTransferDemo {
    public static void main(String[] args) {
        Account from = new Account(100);
        Account to = new Account(20);

        try {
            Account.transfer(from, to, 150);
        } catch (IllegalArgumentException ex) {
            System.out.println("transfer rejected");
        }

        System.out.println("after rejection="
                + from.balance() + "/" + to.balance());

        Account.transfer(from, to, 30);
        System.out.println("after transfer="
                + from.balance() + "/" + to.balance());
    }
}
```

```bash
javac SafeTransferDemo.java
java SafeTransferDemo
```

```text
transfer rejected
after rejection=100/20
after transfer=70/50
```

Ở đây:

- Cả hai tài khoản được kiểm tra trong cùng đoạn `synchronized(LOCK)`.
- `nextFrom` và `nextTo` được tính **trước** các assignment.
- Khi lỗi thiếu tiền hoặc overflow xảy ra, hai field vẫn nguyên.
- Khi không có lỗi, hai phép gán diễn ra trong đoạn khóa. Các đường đọc `balance()` cũng dùng **cùng LOCK**, nên một reader đơn lẻ không đọc được field trong lúc transfer đang giữ lock.

**Hạn chế cần hiểu rõ:**

- Đây là demo **in-memory**, không phải giao dịch database hay dịch vụ thanh toán.
- Khóa static toàn cục đơn giản nhưng làm mọi Account tranh chấp cùng monitor; hệ thống lớn cần thiết kế concurrency khác (khóa theo tài khoản có thứ tự cố định, transactional store, v.v.).
- Nếu caller đọc lần lượt `from.balance()` rồi `to.balance()` trong **hai lời gọi tách biệt**, một giao dịch chuyển tiền khác vẫn có thể xen giữa hai lần đọc. Muốn snapshot cặp số dư nhất quán, hãy đọc **cả hai trong một critical section** hoặc qua API snapshot chung.
- Ví dụ bảo đảm tính nhất quán ở các method tuân thủ `LOCK`, không phải atomicity trước mọi cơ chế quan sát ngoài JVM hay khi tiến trình bị crash.
- Không nên thực hiện I/O, callback hay gọi code không kiểm soát trong lúc đang giữ khóa nếu có thể tránh, vì có thể gây deadlock, chậm hoặc exception khó phục hồi.

## 11. “Validate trước” có thể sai trong môi trường đa luồng: TOCTOU

**Time-of-check to time-of-use** (TOCTOU) là khoảng cách giữa lúc kiểm tra điều kiện và lúc sử dụng kết quả ấy.

Mã đơn giản:

```java
if (account.balance() >= amount) {
    account.withdraw(amount);
}
```

Nếu nhiều thread cùng thao tác trên cùng tài khoản, cả hai có thể đều thấy đủ tiền trước khi một trong hai trừ số dư. Điều kiện từng kiểm tra **không còn chắc đúng** ở thời điểm cập nhật.

**Thiết kế đúng hơn:** đặt **kiểm tra và thay đổi** trong một API của object sở hữu state và dùng cơ chế đồng bộ phù hợp:

```java
class LockedAccount {
    private int balance;

    LockedAccount(int balance) {
        this.balance = balance;
    }

    synchronized boolean tryWithdraw(int amount) {
        if (amount <= 0 || amount > balance) {
            return false;
        }
        balance -= amount;
        return true;
    }

    synchronized int balance() {
        return balance;
    }
}
```

Đây là **khai báo lớp minh họa không có `main`**. Method `tryWithdraw` kiểm tra và trừ số dư dưới cùng monitor của receiver, trong khi getter cũng đồng bộ trên cùng monitor.

Đừng chỉ viết `volatile int balance` rồi giả định `if (balance >= amount) balance -= amount` trở thành một thao tác nguyên tử: `volatile` cho visibility/order phù hợp nhưng **không tự gộp check-and-update thành một transaction**.

Khi state là immutable snapshot, có thể dùng `AtomicReference<State>` với vòng CAS để bảo đảm cập nhật dựa trên state mà không bị ghi đè bởi thread khác. Nhưng callback tính state mới trong vòng CAS **có thể được chạy nhiều lần**, nên không được có side effect bên ngoài trong bước tính ấy.

## 12. Rollback bằng `try/catch`: khi nào cần, khi nào nguy hiểm?

Đôi khi thao tác **bắt buộc** có các bước mutation trước khi tất cả rủi ro được biết. Khi đó có thể cân nhắc **rollback có kiểm soát**:

1. Ghi lại state cần phục hồi.
2. Thực hiện những bước có thể thất bại.
3. Nếu một bước thất bại, khôi phục state.
4. Ném lại exception hoặc chuyển thành kết quả lỗi theo hợp đồng.

Ví dụ minh họa ý tưởng:

```java
int oldCount = count;
try {
    count += amount;
    operationThatMayFail();
} catch (RuntimeException ex) {
    count = oldCount;
    throw ex;
}
```

Đây là **mảnh mã không độc lập**. Nó chỉ có thể bảo đảm `count` được phục hồi đối với các `RuntimeException` bắt được **và** khi code hồi phục hoạt động như dự kiến.

**Các bẫy lớn của rollback thủ công:**

- Có nhiều field/object cùng bị sửa nhưng chỉ lưu `oldCount` thì **không rollback toàn bộ state**.
- Nếu đã gửi email, ghi file, kích hoạt callback hoặc gọi dịch vụ ngoài, gán lại field không thể hoàn tác side effect ấy.
- Nếu callback đã giữ một reference tới object phụ đã mutate, rollback field ở object chính chưa chắc phục hồi state object phụ.
- Nếu exception xảy ra **trong chính quá trình rollback**, việc phục hồi cũng có thể thất bại.
- Trong nhiều thread, rollback bằng cách gán lại giá trị cũ có thể **ghi đè thay đổi hợp lệ của thread khác** nếu không có cơ chế cô lập.
- Không nên bắt tất cả `Throwable` rồi coi mọi trường hợp như lỗi nghiệp vụ phục hồi được; `Error`, tình huống tài nguyên hệ thống và lỗi nghiêm trọng có ràng buộc khác.

Vì vậy **ưu tiên tính trước rồi commit** khi khả thi. Dùng rollback thủ công khi thực sự hiểu mọi side effect và có contract bảo đảm phục hồi; với thao tác nhiều tài nguyên, cần hệ thống transaction hoặc thiết kế bù trừ thích hợp.

## 13. `finally` và try-with-resources: giải phóng tài nguyên khác rollback dữ liệu

Java cung cấp `finally` và **try-with-resources** để giúp **đóng tài nguyên** khi khối code kết thúc bình thường hoặc do exception. Nhưng **đóng tài nguyên không đồng nghĩa khôi phục mọi trạng thái nghiệp vụ**.

Ví dụ với tài nguyên quản lý bằng `AutoCloseable`:

```java
class Resource implements AutoCloseable {
    void use() {
        System.out.println("using resource");
        throw new IllegalStateException("operation failed");
    }

    @Override
    public void close() {
        System.out.println("resource closed");
    }
}

public class ResourceCleanupDemo {
    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            resource.use();
        } catch (IllegalStateException ex) {
            System.out.println("caught: " + ex.getMessage());
        }
    }
}
```

Lưu toàn bộ vào **`ResourceCleanupDemo.java`**, biên dịch/chạy:

```bash
javac ResourceCleanupDemo.java
java ResourceCleanupDemo
```

```text
using resource
resource closed
caught: operation failed
```

`close()` được gọi bởi try-with-resources khi `use()` ném exception. Điều này bảo đảm một cơ chế **cleanup** trong trường hợp minh họa, nhưng không nói rằng mọi thay đổi trong `use()` đã được rollback.

**Phân biệt rõ:**

- **Cleanup:** đóng file, release lock/resource, hủy session tạm.
- **Rollback:** khôi phục trạng thái nghiệp vụ về trước thao tác.
- **Commit:** xác nhận trạng thái mới sau khi hoàn tất các bước cần thiết.

Từng việc cần API và contract riêng. Với JDBC, `Connection.rollback()` chỉ thực sự rollback thay đổi theo quy tắc transaction của connection và cơ sở dữ liệu khi đã tổ chức transaction phù hợp; không phải `try-with-resources` nào cũng tự rollback nghiệp vụ.

## 14. Database transaction: khi thay đổi thuộc về nhiều bản ghi

Một transfer giữa hai tài khoản lưu trong database cần nhìn như **một giao dịch nhiều bước**, không phải hai câu lệnh cập nhật độc lập.

Khung JDBC minh họa:

```java
import java.sql.Connection;
import java.sql.SQLException;

class TransferService {
    static void transfer(Connection connection) throws SQLException {
        boolean originalAutoCommit = connection.getAutoCommit();
        connection.setAutoCommit(false);

        try {
            // Thực thi các PreparedStatement cập nhật hai bản ghi.
            // Kiểm tra số dòng thay đổi và điều kiện nghiệp vụ.
            // Không có SQL thực thi trong mảnh minh họa này.

            connection.commit();
        } catch (SQLException | RuntimeException ex) {
            try {
                connection.rollback();
            } catch (SQLException rollbackFailure) {
                ex.addSuppressed(rollbackFailure);
            }
            throw ex;
        } finally {
            connection.setAutoCommit(originalAutoCommit);
        }
    }
}
```

Đây là **mẫu cấu trúc minh họa**, chưa phải một ứng dụng độc lập hay một transaction hoàn chỉnh; phải dùng schema, SQL, isolation level và datasource cụ thể. Trong hệ thống dùng connection pool, việc sở hữu transaction, tự quản `autoCommit` và trả connection cho pool còn tùy framework/hợp đồng thư viện.

**Điều cần hiểu:**

- `setAutoCommit(false)` khởi đầu mô hình điều khiển transaction trên connection khi phù hợp.
- Chỉ `commit()` sau khi mọi bước/validation hoàn tất.
- Khi lỗi, cố `rollback()` để bỏ các thay đổi chưa commit trong phạm vi database transaction.
- Một lỗi rollback/connection có thể khiến kết quả transaction **không rõ ràng**, cần báo cáo/điều tra hoặc cơ chế recovery; không khẳng định thành công/hoàn tác tuyệt đối khi database trả trạng thái bất định.
- Giao dịch database không tự thu hồi email đã gửi hoặc HTTP request đã xử lý tại hệ thống ngoài.

**Đóng gói trách nhiệm:** nếu `AccountRepository` quản lý lưu trữ, nên tập trung transaction ở service/repository boundary phù hợp, thay vì mỗi entity Java tự mở/commit một connection độc lập gây nửa giao dịch.

## 15. Gọi dịch vụ ngoài: side effect không thể hoàn tác bằng gán field

Giả sử xử lý đơn hàng gồm:

1. Đánh dấu order là đã thanh toán.
2. Trừ tồn kho.
3. Gửi email xác nhận.

Nếu bước 3 lỗi sau khi 1–2 thành công, không nên đơn giản `throw` và tuyên bố “order chưa xử lý”. Thực tế đã có state thay đổi.

Một số chiến lược kiến trúc:

- **Transaction trong cùng database:** cập nhật order và stock trong một transaction nếu thực sự cùng phạm vi transaction.
- **Transactional outbox:** ghi dữ liệu nghiệp vụ và “cần gửi sự kiện” trong cùng DB transaction, rồi hệ thống khác gửi email/event và có cơ chế retry.
- **Idempotency key:** giúp việc retry request/event không tạo thêm hiệu ứng trùng ngoài ý muốn.
- **Saga/compensating action:** khi nhiều dịch vụ không chia sẻ transaction, tổ chức các bước và hành động bù trừ có thể áp dụng — nhưng hành động bù trừ **không phải lúc nào khôi phục hoàn toàn**.
- **Trạng thái nghiệp vụ rõ ràng:** `PENDING`, `PAID`, `FULFILLED`, `FAILED` với quy tắc chuyển trạng thái, thay vì một cờ boolean được đổi trước khi toàn bộ tác vụ hoàn tất.

Không cần áp dụng mọi mẫu kiến trúc phức tạp cho một class đơn giản; quan trọng là **định nghĩa chính xác ranh giới của “thành công”, “thất bại” và “đã commit”**.

## 16. Constructor cũng có thể thất bại: không để lộ object đang dựng dở

Constructor thường thiết lập invariant ban đầu. Hãy kiểm tra dữ liệu **trước khi lưu state nhạy cảm hoặc để `this` thoát ra ngoài**.

Ví dụ:

```java
final class Booking {
    private final String code;
    private final int seats;

    Booking(String code, int seats) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code required");
        }
        if (seats <= 0) {
            throw new IllegalArgumentException("positive seats required");
        }

        this.code = code;
        this.seats = seats;
    }

    String summary() {
        return code + ":" + seats;
    }
}
```

Nếu validation ném exception, biểu thức tạo `Booking` không hoàn tất bình thường và caller không nhận object từ lời gọi constructor ấy. Nhưng điều đó **không bảo đảm mọi side effect của constructor tự rollback**. Nếu constructor đã đăng ký `this` vào một static collection, khởi động thread, gửi event hoặc mutate object ngoài, tham chiếu đến object đang dựng dở có thể bị lộ.

### Bẫy “this escapes” trong constructor

```java
// Chỉ minh họa kiểu thiết kế nguy hiểm:
class BadRegistration {
    static final java.util.List<BadRegistration> ALL =
            new java.util.ArrayList<>();

    private String name;

    BadRegistration(String name) {
        ALL.add(this); // this thoát ra ngoài trước khi khởi tạo xong.
        if (name == null) {
            throw new IllegalArgumentException("name required");
        }
        this.name = name;
    }
}
```

Nếu gọi `new BadRegistration(null)`, constructor ném lỗi nhưng danh sách `ALL` có thể đã giữ tham chiếu tới object chưa có `name` hợp lệ. Đây là một ví dụ về **side effect trước validation** và **object escape**.

Cách tiếp cận an toàn:

1. Validate các input/điều kiện có thể kiểm tra trước.
2. Khởi tạo đầy đủ state của object.
3. Tránh công bố `this` (đăng ký vào registry, callback, thread) trong constructor nếu có thể.
4. Khi phải đăng ký, cân nhắc factory/service thực hiện **registration sau khi construction thành công**; vẫn cần tính tới lỗi registration và khả năng retry/rollback.

**Chú ý:** private final fields giúp thiết kế dễ kiểm soát, nhưng không tự ngăn callback hoặc external side effects trong constructor.

## 17. Trả kết quả mới thay vì mutate đầu vào

Một cách giảm nguy cơ trạng thái dở dang là dùng **immutable value objects** và method trả instance mới.

Ví dụ Java 17+:

```java
record Money(long cents) {
    Money {
        if (cents < 0) {
            throw new IllegalArgumentException("negative money");
        }
    }

    Money plus(Money other) {
        return new Money(Math.addExact(cents, other.cents));
    }
}
```

Trong `plus`, object `this` và `other` không bị thay đổi. Nếu overflow xảy ra, `Math.addExact` ném `ArithmeticException` và hai Money cũ vẫn giữ giá trị. Nếu thành công, một instance `Money` mới được trả về.

### Chương trình runnable về value object

Tệp **`ImmutableMoneyDemo.java`**:

```java
record Money(long cents) {
    Money {
        if (cents < 0) {
            throw new IllegalArgumentException("negative");
        }
    }

    Money plus(Money other) {
        return new Money(Math.addExact(cents, other.cents()));
    }
}

public class ImmutableMoneyDemo {
    public static void main(String[] args) {
        Money original = new Money(500);
        Money addition = new Money(125);
        Money result = original.plus(addition);

        System.out.println("original=" + original.cents());
        System.out.println("result=" + result.cents());

        try {
            new Money(Long.MAX_VALUE).plus(new Money(1));
        } catch (ArithmeticException ex) {
            System.out.println("overflow rejected");
        }
    }
}
```

```bash
javac ImmutableMoneyDemo.java
java ImmutableMoneyDemo
```

```text
original=500
result=625
overflow rejected
```

**Lợi ích:** input records không thay đổi do method `plus`. Nhưng immutable object **không loại bỏ** lỗi khi phối hợp nhiều external systems; nó chỉ giúp ranh giới state trong RAM rõ ràng hơn.

Nếu record chứa một mutable `List`, `Map` hoặc array, các component fields có thể là final nhưng **object được tham chiếu vẫn có thể bị mutate**. Cần defensive copy khi muốn bất biến sâu theo contract.

## 18. Bản sao nông, bản sao sâu và object graph

Kỹ thuật copy-then-commit có một giới hạn quan trọng: **một bản sao container chưa chắc là bản sao mọi phần tử**.

```java
class Participant {
    String name;

    Participant(String name) {
        this.name = name;
    }
}
```

Giả sử:

```java
java.util.List<Participant> original =
        new java.util.ArrayList<>();
original.add(new Participant("An"));

java.util.List<Participant> candidate =
        new java.util.ArrayList<>(original);

candidate.get(0).name = "Binh";
```

Dù `candidate` và `original` là **hai list objects**, chúng cùng giữ tham chiếu tới **một Participant object**. Việc sửa `candidate.get(0).name` **đã làm thay đổi participant mà original trỏ tới** trước khi commit list.

Sơ đồ:

```text
original ──> List A [0] ────┐
                            ├──> Participant X {name="Binh"}
candidate ─> List B [0] ────┘
```

Để đảm bảo không mutate đồ thị dữ liệu gốc khi chuẩn bị kết quả, có thể:

- **Không sửa object phần tử** khi đang thao tác candidate; chỉ tạo/thay tham chiếu phù hợp.
- Dùng immutable element types.
- Tạo **copy của từng mutable element** theo constructor/factory/hợp đồng copy.
- Xây một giá trị state mới hoàn chỉnh thay vì đụng vào object graph gốc.

Không có `clone()` tổng quát nào tự bảo đảm deep copy cho mọi Java object graph. Cần xét ownership, chu kỳ tham chiếu, invariant và chi phí.

## 19. Đừng dùng validation có side effect

Một method validation nên **tập trung kiểm tra**, tránh tự ý mutate những state mà chính nó đang xác nhận.

Ví dụ không nên:

```java
boolean validAndRemoveExpired(java.util.List<Item> items) {
    items.removeIf(Item::expired);  // Mutation lẫn trong validation.
    return items.size() <= 10;
}
```

Đây là **mảnh code minh họa** giả định `Item` có `expired()`, không phải runnable độc lập. Nếu phần kiểm tra tiếp theo thất bại hoặc method ném exception, list đã thay đổi dù caller có thể tưởng đây chỉ là câu hỏi yes/no.

Cách rõ hơn là phân tách:

1. `validate(...)` **đọc** và kiểm tra, không mutate.
2. `plan(...)` tạo các thay đổi dự kiến ở local/immutable state.
3. `commit(...)` áp dụng một lần khi tất cả điều kiện đã thỏa.

Tất nhiên có những API cố ý kết hợp kiểm tra và thay đổi, ví dụ `tryWithdraw` hoặc `removeIf`; vấn đề không phải cấm mutation mà là **hợp đồng phải nói rõ** và failure behavior phải được thiết kế.

## 20. Thứ tự kiểm tra và thứ tự side effect

Giả sử một method thực hiện:

```text
Kiểm tra input
Ghi log sự kiện thành công
Tính kết quả (có thể overflow)
Gán state
```

Nếu phép tính overflow, log đã ghi “thành công” sai sự thật. Vì vậy không chỉ state field, **thứ tự side effect** cũng cần cân nhắc.

Thứ tự thường hợp lý hơn:

```text
1. Validate input và state hiện tại.
2. Tính kết quả dự kiến (có thể ném lỗi).
3. Chuẩn bị dữ liệu/event sẽ cần.
4. Commit trạng thái tại ranh giới được thiết kế.
5. Phát tín hiệu hoàn tất/log thành công theo contract.
```

Nhưng nếu ghi log hoặc gửi message ở bước 5 thất bại, phải xác định **trạng thái nghiệp vụ đã commit hay chưa**. Không thể cứ ném một exception chung rồi coi như chưa có gì xảy ra. Với nhiều hệ thống ngoài, dùng transactional outbox, retry có idempotency hoặc trạng thái `PENDING_NOTIFICATION` sẽ rõ ràng hơn.

### Vì sao `System.out.println` trong giữa transaction cũng là side effect?

Console output không được rollback khi object state quay về cũ. Trong tutorial, in log đơn giản giúp quan sát thứ tự; trong production, **không dùng output thành công trước commit** để chứng minh nghiệp vụ đã thành công.

## 21. Xử lý exception: giữ nguyên nguyên nhân và hợp đồng lỗi

Khi một method thất bại, caller cần biết:

- Lỗi thuộc loại **invalid input**, **không đủ tài nguyên/trạng thái nghiệp vụ**, hay **lỗi hệ thống**?
- Object sau lỗi **còn hợp lệ không**, có **giữ nguyên state cũ không**?
- Caller có thể **retry** an toàn không?
- Có side effect bên ngoài nào **đã thực hiện thành công** không?

Ví dụ:

```java
void reserve(int amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }
    if (amount > available()) {
        throw new IllegalStateException("not enough available items");
    }
    // Thực hiện mutation theo kế hoạch hợp lệ.
}
```

Đây là mảnh code minh họa cần đặt trong một lớp có method `available()` phù hợp. Phân biệt exception types giúp caller hiểu lỗi, nhưng **loại exception không tự bảo đảm state an toàn**. Điều quyết định vẫn là **thứ tự và cách cập nhật**.

**Không nên** bắt mọi `RuntimeException` rồi trả `false` nếu trạng thái đã thay đổi một phần; như vậy lỗi bị che khuất. Cũng không nên nuốt exception khiến caller tin thao tác thành công. Nếu đổi exception type, nên bảo toàn cause bằng cách constructor thích hợp và mô tả contract.

Với bước cleanup/rollback có thể thất bại, cần tránh làm mất exception gốc; ví dụ dùng `addSuppressed` cho lỗi rollback như khung JDBC ở trên.

## 22. Những lỗi hay gặp khi ngăn trạng thái dở dang

| Sai lầm | Vì sao nguy hiểm | Cách thiết kế tốt hơn |
| --- | --- | --- |
| Sửa field rồi mới validate | Exception để lại field đã đổi | Validate trước mutation |
| Kiểm tra input nhưng bỏ qua overflow | State có thể vượt miền số học | Tính bằng `Math.addExact`/`subtractExact` trước khi gán |
| Cập nhật field A rồi mới tính field B | Tính B thất bại khiến A đã bị sửa | Tính tất cả `next...` trước commit |
| Chỉ dùng `private` và tin object an toàn | Method của chính class vẫn có thể phá invariant | Mỗi mutation path phải giữ invariant |
| Gọi hai setters độc lập để sửa state liên quan | State trung gian có thể sai hoặc lộ | Một domain operation cập nhật cả nhóm |
| Add vào list rồi mới kiểm tra capacity | List đã quá giới hạn nếu throw | Kiểm tra trước hoặc copy-then-commit |
| Clone list nhưng mutate element dùng chung | Shallow copy không cô lập mutable elements | Immutable elements/deep copy có chọn lọc |
| `try/catch` rồi không rollback | Exception không hủy mutation cũ | Thiết kế strong/basic guarantee rõ ràng |
| `finally` được xem là transaction | Cleanup khác rollback | Dùng transaction/rollback đúng phạm vi |
| Save vào DB rồi gửi event trực tiếp, lỗi lại coi như chưa save | External side effect không được đảo ngược | Outbox/idempotency/saga khi phù hợp |
| `synchronized` và nghĩ exception tự rollback | Lock không lưu state cũ | Compute-before-commit và đồng bộ riêng |
| Validate ngoài lock, commit trong lock sau | TOCTOU: state có thể đổi giữa hai bước | Validate+commit cùng critical section |
| Factory/constructor công bố `this` trước khi hoàn tất | Có thể lộ object dở dang | Hoàn tất object rồi mới công bố |
| Bắt mọi lỗi thành `false` | Che state hỏng và che nguyên nhân | Báo lỗi có contract và kiểm tra state |
| Retry thao tác không idempotent vô điều kiện | Có thể nhân đôi tác động đã xảy ra | Idempotency key hoặc kết quả xác định |
| Đổi nhiều field mà không đồng bộ các reader | Thread khác có thể thấy trạng thái giữa chừng | Snapshot/lock/transaction phù hợp |
| Coi all-or-nothing trong RAM là bền vững khi crash | Không có guarantee storage | Dùng cơ chế lưu trữ giao dịch |
| Cho caller mutate mutable state qua getter | Invariant bị phá ngoài method | Defensive copy/unmodifiable API |

## 23. Tự kiểm tra bằng 12 câu hỏi có đáp án

**Câu 1.** Method viết `balance -= amount; if (balance < 0) throw ...;` có bảo toàn state khi rút quá số dư không?

**Đáp án:** Không. Field `balance` đã bị giảm trước khi ném exception. Kiểm tra `amount` và số dư trước khi gán.

**Câu 2.** `throw new IllegalArgumentException(...)` có tự rollback mọi thay đổi field trước nó không?

**Đáp án:** Không. Java exception thay đổi luồng điều khiển, không cung cấp rollback state tổng quát.

**Câu 3.** Tại sao `Math.addExact` nên gọi trước phép gán field?

**Đáp án:** Nếu overflow, nó ném `ArithmeticException` trước mutation; field vẫn giữ giá trị cũ.

**Câu 4.** Đối với hai field liên quan, vì sao tính `nextA` và `nextB` trước có lợi?

**Đáp án:** Validation/tính toán có thể thất bại khi object còn nguyên; chỉ commit khi toàn bộ state dự kiến hợp lệ.

**Câu 5.** Dùng `synchronized` quanh hai phép gán có tự rollback nếu câu lệnh thứ hai ném exception không?

**Đáp án:** Không. Khóa xử lý phối hợp concurrency, không tự phục hồi dữ liệu đã gán.

**Câu 6.** Tạo `new ArrayList<>(original)` rồi mutate field của object ở index 0 có đảm bảo original không đổi không?

**Đáp án:** Không. Bản sao list là shallow copy; hai list có thể cùng trỏ một mutable element object.

**Câu 7.** Một record chứa `List<Person>` với field final có hoàn toàn immutable không?

**Đáp án:** Không chắc. Person hoặc list có thể mutable và được chia sẻ; cần thiết kế copy/immutability phù hợp.

**Câu 8.** Constructor ném exception sau khi đã thêm `this` vào static registry có thể có hậu quả gì?

**Đáp án:** Registry có thể vẫn chứa tham chiếu tới object chưa hoàn tất khởi tạo, dù caller không nhận object qua expression `new` thành công.

**Câu 9.** `try-with-resources` có bảo đảm mọi cập nhật database/field rollback không?

**Đáp án:** Không. Nó quản lý đóng tài nguyên; transaction rollback cần được tổ chức riêng theo contract.

**Câu 10.** Vì sao một method chuyển tiền qua hai service cần cơ chế phức tạp hơn hai assignment trong RAM?

**Đáp án:** Có network, storage và side effect độc lập; không có một Java lock/try-catch nào tự tạo distributed transaction. Cần transaction/outbox/idempotency/saga phù hợp.

**Câu 11.** Nếu hai thread cùng check `balance >= amount` trước khi rút, điều gì có thể xảy ra?

**Đáp án:** Cả hai có thể đều thấy đủ tiền nhưng tổng rút vượt số dư do TOCTOU. Check-and-update cần đồng bộ/CAS/transaction phù hợp.

**Câu 12.** “Method thất bại thì state không đổi” có bao gồm email đã gửi trước đó không?

**Đáp án:** Chỉ khi contract/boundary và cơ chế cụ thể bảo đảm điều ấy. Đối với email đã gửi ra ngoài, thường không thể rollback bằng gán lại Java field.

## 24. Bài thực hành cuối: tìm bug partial mutation và sửa

Đề bài: Một `GiftCard` có `balance` (số tiền) và `spent` (tổng tiền đã dùng). Bất biến:

```text
balance >= 0
spent >= 0
```

Mã sai:

```java
class GiftCard {
    private int balance;
    private int spent;

    GiftCard(int balance) {
        this.balance = balance;
    }

    void payBadly(int amount) {
        balance -= amount;    // Sửa trước.
        spent += amount;      // Có thể overflow.
        if (balance < 0) {
            throw new IllegalArgumentException("not enough");
        }
    }
}
```

**Hãy tự trả lời:** Nếu `amount > balance` hoặc `spent + amount` tràn `int`, class còn giữ đúng invariant không? Có thể sửa để các lỗi đó xảy ra **trước mutation** không?

### Một lời giải theo calculate → validate → commit

Tạo tệp **`GiftCardSafetyDemo.java`**:

```java
class GiftCard {
    private int balance;
    private int spent;

    GiftCard(int initial) {
        if (initial < 0) {
            throw new IllegalArgumentException("negative initial");
        }
        this.balance = initial;
    }

    void pay(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("positive amount required");
        }
        if (amount > balance) {
            throw new IllegalArgumentException("insufficient balance");
        }

        int nextBalance = Math.subtractExact(balance, amount);
        int nextSpent = Math.addExact(spent, amount);

        if (nextBalance < 0 || nextSpent < 0) {
            throw new IllegalArgumentException("invalid resulting state");
        }

        balance = nextBalance;
        spent = nextSpent;
    }

    String snapshot() {
        return "balance=" + balance + ", spent=" + spent;
    }
}

public class GiftCardSafetyDemo {
    public static void main(String[] args) {
        GiftCard card = new GiftCard(50);
        System.out.println("before: " + card.snapshot());

        try {
            card.pay(70);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected");
        }

        System.out.println("after failure: " + card.snapshot());
        card.pay(20);
        System.out.println("after success: " + card.snapshot());
    }
}
```

```bash
javac GiftCardSafetyDemo.java
java GiftCardSafetyDemo
```

```text
before: balance=50, spent=0
rejected
after failure: balance=50, spent=0
after success: balance=30, spent=20
```

**Phân tích lời giải:**

1. Constructor không cho giá trị số dư âm.
2. Method `pay` kiểm tra `amount > 0` và đủ số dư trước mọi mutation.
3. `Math.subtractExact` và `Math.addExact` tính hai kết quả dự kiến. Nếu một phép tính lỗi, hai field còn nguyên.
4. Điều kiện invariant của kết quả được xác minh trước commit.
5. Hai assignment cuối là bước áp dụng state mới. Ví dụ này thảo luận failure safety trong một luồng; nếu nhiều thread truy cập card, cần đồng bộ các đường đọc/ghi hoặc dùng immutable snapshot.

### Tình huống nâng cao

Nếu cần `spent` không vượt một hạn mức, hãy bổ sung giới hạn vào **pha validate kết quả**, không thêm một dòng `if` ném lỗi sau khi đã gán `spent`. Nếu thanh toán phải ghi database và gửi sự kiện, phải mở rộng hợp đồng transaction ngoài state của `GiftCard` chứ không chỉ thêm `try/catch`.

## 25. Checklist code review trước khi công bố một method có thể thất bại

- [ ] Object có **invariant rõ ràng** sau khi tạo và sau mỗi public operation?
- [ ] Mỗi con đường thất bại có định nghĩa **state sau lỗi**?
- [ ] Input và preconditions được kiểm tra **trước mutation** nếu khả thi?
- [ ] Các phép tính overflow/parse/lookup có thể ném lỗi đã được chạy trước commit?
- [ ] Với nhiều field, đã tính **toàn bộ giá trị mới** rồi kiểm tra invariant trước assignment?
- [ ] Có thể dùng **immutable snapshot** thay nhiều field cập nhật riêng không?
- [ ] Với collection, đã cân nhắc **copy → validate → commit**?
- [ ] Bản copy có thật sự cô lập mutable element objects cần được bảo vệ?
- [ ] Getter hoặc constructor có vô tình để lộ alias tới mutable internal state?
- [ ] Có side effect bên ngoài nào xảy ra trước khi nghiệp vụ được coi là commit?
- [ ] Khi rollback, có lưu đủ state và mọi bước rollback đáng tin không?
- [ ] Nếu rollback thất bại, exception gốc có được giữ và trạng thái không rõ có được báo?
- [ ] Có lẫn **cleanup**, **rollback** và **commit** thành một khái niệm không?
- [ ] Constructor/factory có công bố `this` quá sớm không?
- [ ] Với đa luồng, validation và mutation có nằm trong **cùng ranh giới đồng bộ** thích hợp?
- [ ] Các reader có thể nhìn state trung gian qua field riêng hay qua getter không đồng bộ không?
- [ ] Nếu gọi database/dịch vụ ngoài, API có transaction/idempotency/retry contract phù hợp?
- [ ] Unit test có kiểm **state trước/sau các lỗi có dự đoán được**, không chỉ kiểm exception type?
- [ ] Test có bao phủ **giới hạn số học, danh sách đầy, dữ liệu null/trùng, lỗi nhiều bước** không?
- [ ] Documentation có nói rõ trạng thái sau thất bại và khả năng retry?

---

**Ghi nhớ:** Ngăn trạng thái dở dang là **phần cốt lõi của đóng gói**. Field `private` giúp tập trung quyền sửa, nhưng **mỗi method sở hữu state vẫn phải giữ invariant**. Khi thao tác có thể thất bại, ưu tiên **validate trước → tính state mới đầy đủ → commit sau**. Với collections và object graph, có thể **copy → sửa/kiểm tra trên bản sao → công bố state mới**, nhưng phải lưu ý shallow copy. `throw`, `try/catch`, `finally` và `synchronized` **không tự cung cấp rollback tổng quát**. Với concurrency, database và side effect ngoài tiến trình, cần ranh giới transaction/đồng bộ và hợp đồng lỗi riêng để tránh coi một thao tác nửa chừng là đã hoàn tất.