# Đóng gói trường dữ liệu và cấu trúc nội bộ trong Java OOP

> **Phạm vi:** Tái cấu trúc — *Encapsulate Field*, *Encapsulate Collection* và *Hide Representation*. Mục tiêu là để mỗi đối tượng tự bảo vệ trạng thái hợp lệ và cho phép bên ngoài làm việc qua một API ổn định.

## 1. Vấn đề thực tế: field `private` chưa đủ

Trong lập trình hướng đối tượng, **đóng gói (encapsulation)** có nghĩa là đối tượng kiểm soát cách trạng thái của nó được đọc hoặc thay đổi. Client cần biết **đối tượng có thể làm gì**, thay vì biết **nó lưu dữ liệu như thế nào**.

Hai tình huống làm mất đóng gói:

~~~java
class Order {
    public final List<OrderLine> lines = new ArrayList<>();
}
~~~

`final` chỉ ngăn gán lại **tham chiếu** `lines`; nó **không** ngăn `order.lines.clear()`, `add()` hay sửa phần tử nằm trong danh sách.

~~~java
class Order {
    private final List<OrderLine> lines = new ArrayList<>();

    public List<OrderLine> getLines() {
        return lines; // Vẫn rò rỉ tham chiếu nội bộ!
    }
}
~~~

Dù field đã `private`, client vẫn sửa danh sách trực tiếp qua getter:

~~~java
order.getLines().clear();
~~~

Vấn đề này được gọi là **representation exposure**: cấu trúc dữ liệu dùng để biểu diễn trạng thái nội bộ bị lộ ra, cho phép mã khác thay đổi nó mà không đi qua quy tắc của đối tượng.

### Kết quả cần đạt

Sau bài này, bạn có thể:

- Nhận biết field bị lộ, mutable collection, mutable element và tham chiếu alias gây rò rỉ trạng thái.
- Áp dụng `Encapsulate Field` bằng việc giữ field `private` và cung cấp thao tác có ý nghĩa, thay vì tự động tạo getter/setter cho mọi field.
- Giấu `ArrayList`, `HashMap` hoặc mảng đằng sau một **hợp đồng hành vi** không phụ thuộc loại cấu trúc lưu trữ.
- Phân biệt **bản chụp bất biến**, **view không sửa được** và **deep copy**.
- Viết kiểm thử chứng minh client không sửa được trạng thái nội bộ qua tham chiếu được trả về.
- Tái cấu trúc có kiểm soát, giữ hành vi công khai đã cam kết và xử lý điểm tương thích API khi cần.

## 2. Tại sao cần đóng gói cấu trúc nội bộ?

Giả sử `ShoppingCart` có các quy tắc:

1. Mỗi SKU xuất hiện tối đa một lần.
2. SKU phải khác `null`, không phải chuỗi trống hay chỉ có khoảng trắng.
3. Đơn giá (cent) không âm, số lượng luôn dương khi dòng hàng tồn tại.
4. Thay đổi số lượng về `0` có nghĩa là xóa dòng hàng, không lưu dòng có số lượng `0`.
5. Tổng tiền bằng tổng `unitPriceCents × quantity` của các dòng; không được trả số âm hoặc kết quả sai vì tràn `long`.

Nếu client được `cart.lines.add(...)` hoặc `cart.lines.get(0).quantity = -5`, mọi quy tắc này có thể bị phá mà `ShoppingCart` không biết.

**Bất biến (invariant)** là điều kiện phải đúng với mọi trạng thái có thể quan sát được của đối tượng sau một thao tác công khai thành công. API của giỏ hàng nên cho phép `putLine`, `changeQuantity`, `removeLine` và `totalCents`, thay vì cho phép client tùy ý sửa `Map`/`List`.

| Cách thiết kế | Có bảo vệ bất biến? | Điểm cần nhớ |
|---|---|---|
| `public List<Line> lines` | Không | Client thay đổi trực tiếp collection |
| `private List<Line> lines` + getter trả tham chiếu gốc | Không | Chỉ thay cú pháp, chưa ẩn representation |
| Getter trả `Collections.unmodifiableList(lines)` | Chỉ chặn sửa qua view | View **sống**, vẫn phản ánh thay đổi từ nguồn; element mutable vẫn sửa được |
| Getter trả `List.copyOf(lines)` | Chặn sửa cấu trúc snapshot | Sao chép **nông**: element mutable vẫn có thể bị sửa |
| Snapshot của các **value object bất biến** | Thường phù hợp cho đọc an toàn | Client không thể sửa list hoặc phần tử qua reference được trả |
| API mutation có kiểm tra quy tắc | Có thể bảo vệ invariant | Mọi thay đổi hợp lệ đi qua phương thức kiểm soát |

**Encapsulation không đồng nghĩa bất biến tuyệt đối:** một giỏ hàng vẫn có thể thay đổi trạng thái thông qua các phương thức công khai **được phép**. Điều quan trọng là không có đường tắt vượt qua validation và business rules.

## 3. Ví dụ Java 17 chạy được: từ giỏ hàng rò rỉ dữ liệu sang API an toàn

Tạo tệp duy nhất `EncapsulationDemo.java`, dùng JDK 17 trở lên. Ví dụ có cả phiên bản **cố ý không an toàn** để minh họa hậu quả và phiên bản đã cải thiện để kiểm thử.

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;

public class EncapsulationDemo {

    // BEFORE: client có thể sửa cả danh sách lẫn đối tượng nằm trong đó.
    static final class MutableLine {
        public String sku;
        public long unitPriceCents;
        public int quantity;

        MutableLine(String sku, long unitPriceCents, int quantity) {
            this.sku = sku;
            this.unitPriceCents = unitPriceCents;
            this.quantity = quantity;
        }
    }

    static final class LeakyCart {
        public final List<MutableLine> lines = new ArrayList<>();

        long totalCents() {
            long sum = 0;
            for (MutableLine line : lines) {
                sum += line.unitPriceCents * line.quantity;
            }
            return sum;
        }
    }

    // AFTER: value object bất biến, dùng để trả kết quả đọc.
    // String, long, int ở đây không để lộ mutable component.
    public record LineSnapshot(
            String sku, long unitPriceCents, int quantity) {
        public LineSnapshot {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku must not be blank");
            }
            if (unitPriceCents < 0) {
                throw new IllegalArgumentException("unitPriceCents must be >= 0");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be > 0");
            }
        }
    }

    static final class ShoppingCart {
        // Có thể đổi Map thành cấu trúc khác mà API không đổi.
        // LinkedHashMap giữ thứ tự chèn cho ví dụ.
        private final Map<String, LineSnapshot> lines = new LinkedHashMap<>();

        // Upsert: SKU mới thì thêm; SKU cũ thì thay giá và số lượng.
        public void putLine(String sku, long unitPriceCents, int quantity) {
            LineSnapshot next = new LineSnapshot(sku, unitPriceCents, quantity);
            lines.put(next.sku(), next);
        }

        // Chỉ thay số lượng; quantity = 0 xóa dòng.
        public void changeQuantity(String sku, int quantity) {
            if (quantity < 0) {
                throw new IllegalArgumentException("quantity must be >= 0");
            }
            LineSnapshot current = lines.get(sku);
            if (current == null) {
                throw new NoSuchElementException("Unknown SKU: " + sku);
            }
            if (quantity == 0) {
                lines.remove(sku);
                return;
            }
            lines.put(sku,
                new LineSnapshot(sku, current.unitPriceCents(), quantity));
        }

        public boolean removeLine(String sku) {
            return lines.remove(sku) != null;
        }

        // Snapshot tách khỏi Map nội bộ; các element đều bất biến.
        public List<LineSnapshot> lines() {
            return List.copyOf(lines.values());
        }

        public long totalCents() {
            long result = 0;
            for (LineSnapshot line : lines.values()) {
                long itemTotal = Math.multiplyExact(
                    line.unitPriceCents(), line.quantity());
                result = Math.addExact(result, itemTotal);
            }
            return result;
        }

        public int lineCount() {
            return lines.size();
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void expectUnsupported(Runnable operation) {
        try {
            operation.run();
        } catch (UnsupportedOperationException expected) {
            return;
        }
        throw new AssertionError("Expected UnsupportedOperationException");
    }

    private static void expectIllegalArgument(Runnable operation) {
        try {
            operation.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("Expected IllegalArgumentException");
    }

    public static void main(String[] args) {
        // Chứng minh lỗi: client sửa state mà không qua validation.
        LeakyCart old = new LeakyCart();
        MutableLine leaked = new MutableLine("BOOK", 100, 2);
        old.lines.add(leaked);
        check(old.totalCents() == 200, "initial old total");
        leaked.quantity = -3; // alias ngoài giỏ hàng làm hỏng invariant
        check(old.totalCents() == -300, "expected broken old total");
        System.out.println("LEAK: client changed old cart total to -300");

        ShoppingCart cart = new ShoppingCart();
        cart.putLine("BOOK", 100, 2);
        cart.putLine("PEN", 99, 1);
        check(cart.totalCents() == 299, "initial safe total");
        check(cart.lineCount() == 2, "initial line count");

        List<LineSnapshot> snapshot = cart.lines();
        expectUnsupported(snapshot::clear);
        check(snapshot.get(0).quantity() == 2, "snapshot initial quantity");

        // Thao tác hợp lệ đi qua API có kiểm soát.
        cart.changeQuantity("BOOK", 3);
        check(cart.totalCents() == 399, "safe updated total");
        check(snapshot.get(0).quantity() == 2,
            "old snapshot must not change after cart update");
        check(cart.lines().get(0).quantity() == 3,
            "new snapshot must reflect new state");

        // Input sai bị chặn và không làm thay đổi state.
        expectIllegalArgument(() -> cart.putLine("BAD", -1, 1));
        expectIllegalArgument(() -> cart.putLine("X", 100, 0));
        expectIllegalArgument(() -> cart.putLine("  ", 100, 1));
        expectIllegalArgument(() -> cart.changeQuantity("BOOK", -1));
        check(cart.lineCount() == 2 && cart.totalCents() == 399,
            "invalid operations must not corrupt cart");

        // Đổi số lượng về 0 sẽ xóa dòng, không tạo dòng không hợp lệ.
        cart.changeQuantity("BOOK", 0);
        check(cart.lineCount() == 1, "remove by quantity zero");
        check(cart.totalCents() == 99, "total after removal");

        System.out.println("PASS: cannot modify exposed snapshot");
        System.out.println("PASS: invariants enforced by public methods");
        System.out.println("PASS: old snapshot is independent");
        System.out.println("Final total (cents): " + cart.totalCents());
    }
}
~~~

Biên dịch, chạy:

~~~bash
javac EncapsulationDemo.java
java EncapsulationDemo
~~~

Kết quả mong đợi:

~~~text
LEAK: client changed old cart total to -300
PASS: cannot modify exposed snapshot
PASS: invariants enforced by public methods
PASS: old snapshot is independent
Final total (cents): 99
~~~

**Tại sao phiên bản mới an toàn hơn?**

1. `lines` là `private`: client không thể thêm/xóa dòng bằng truy cập field.
2. `putLine` và `changeQuantity` là **cửa ngõ duy nhất** thay đổi các dòng trong mô hình này. Validation xảy ra **trước** khi cập nhật trạng thái.
3. `LineSnapshot` là record có component `String`, `long` và `int`; không có reference tới object có thể thay đổi. Khi cập nhật số lượng, giỏ tạo record mới.
4. `List.copyOf(lines.values())` tạo danh sách snapshot không sửa được. Snapshot cũ không thay đổi khi `ShoppingCart` cập nhật nội bộ.
5. `Math.multiplyExact` và `Math.addExact` phát hiện tràn số bằng `ArithmeticException`; không để `long` âm đi vì phép toán tràn rồi âm thầm trả số sai.

Ví dụ chưa xử lý **concurrency**: `LinkedHashMap` không thread-safe. Nếu nhiều thread cùng thay đổi giỏ, cần giới hạn ownership theo request/transaction hoặc đồng bộ tại đúng ranh giới; tính bất biến của snapshot không tự khiến toàn bộ `ShoppingCart` thread-safe.

## 4. Ba khái niệm hay bị nhầm: copy, view và immutable element

Xét `List<Person>` mà `Person` có setter:

~~~java
final class Person {
    private String name;
    Person(String name) { this.name = name; }
    String getName() { return name; }
    void setName(String name) { this.name = name; }
}
~~~

| Câu lệnh | Có sửa được cấu trúc danh sách trả về? | Có thấy nguồn thay đổi sau khi lấy? | Có thể sửa `Person` qua reference? |
|---|---|---|---|
| `return people;` | Có | Có, cùng object | Có |
| `return Collections.unmodifiableList(people);` | Không qua view | **Có** (live view) | **Có** |
| `return new ArrayList<>(people);` | Có, nhưng chỉ bản sao list | Không thấy thêm/xóa của nguồn sau copy | **Có** |
| `return List.copyOf(people);` | Không | Thường là snapshot đối với thay đổi cấu trúc khi nguồn mutable | **Có** |
| `return people.stream().map(p -> new ImmutablePerson(p.getName())).toList();` | Không qua danh sách trả về | Không, nếu thành phần immutable | Không |

`List.copyOf` sao chép cấu trúc từ collection mutable, nhưng **không sao chép sâu** các phần tử. Nếu object trong list có thể thay đổi thì cả bản sao và nguồn vẫn nhìn thấy cùng object đó. `Collections.unmodifiableList` chỉ bọc list, còn chủ sở hữu list ban đầu vẫn có thể thay đổi nội dung, nên view có thể đổi theo.

`Stream.toList()` (Java 16+) tạo danh sách không hỗ trợ các thao tác cập nhật, nhưng **cũng không tự deep-copy element**.

### Khi có mutable element, dùng defensive copy thực sự

Nếu buộc giữ class `Person` mutable, có thể tạo bản sao tại **đầu ra**:

~~~java
public List<Person> peopleSnapshot() {
    return people.stream()
        .map(p -> new Person(p.getName()))
        .toList();
}
~~~

Và tạo bản sao tại **đầu vào**:

~~~java
public void addPerson(Person incoming) {
    java.util.Objects.requireNonNull(incoming);
    people.add(new Person(incoming.getName()));
}
~~~

Như vậy, việc caller sửa `incoming` sau `addPerson` hoặc sửa một `Person` nhận về từ `peopleSnapshot` không ảnh hưởng trạng thái lưu bên trong, **với điều kiện** tên là `String` immutable và class chỉ có field đang sao chép. Với object lồng nhau, mảng, collection hay mutable `Date`, cần quyết định sao chép sâu các thành phần sở hữu phù hợp. Không có một hàm clone vạn năng tự đảm bảo an toàn cho mọi object graph.

## 5. Đóng gói trường dữ liệu (Encapsulate Field) đúng cách

Ví dụ field public:

~~~java
class BankAccount {
    public long balanceCents;
}
~~~

Sửa cơ học thành `private` + setter là chưa đủ:

~~~java
class BankAccount {
    private long balanceCents;

    public long getBalanceCents() { return balanceCents; }
    public void setBalanceCents(long balanceCents) {
        this.balanceCents = balanceCents; // vẫn cho phép caller gán âm
    }
}
~~~

Nếu hợp đồng là “số dư không âm”, API nên thể hiện **hành động hợp lệ**:

~~~java
final class BankAccount {
    private long balanceCents;

    BankAccount(long openingBalanceCents) {
        if (openingBalanceCents < 0) {
            throw new IllegalArgumentException("Negative opening balance");
        }
        this.balanceCents = openingBalanceCents;
    }

    long balanceCents() {
        return balanceCents; // primitive: trả theo giá trị, an toàn
    }

    void deposit(long amountCents) {
        if (amountCents <= 0) {
            throw new IllegalArgumentException("Deposit must be positive");
        }
        balanceCents = Math.addExact(balanceCents, amountCents);
    }

    void withdraw(long amountCents) {
        if (amountCents <= 0 || amountCents > balanceCents) {
            throw new IllegalArgumentException("Invalid withdrawal");
        }
        balanceCents -= amountCents;
    }
}
~~~

Ưu điểm là client chỉ có thể tăng/giảm số dư trong điều kiện hợp lệ. Nếu cần chuyển tiền giữa hai tài khoản, phải thiết kế thao tác giao dịch thích hợp; chỉ hai lời gọi `withdraw` rồi `deposit` không tự bảo đảm tính nguyên tử nếu một bước thất bại.

### Chọn API theo bản chất state

- Field cấu hình chỉ đọc: dùng `private final` và getter an toàn hoặc truyền qua constructor.
- Giá trị nghiệp vụ có ràng buộc: ưu tiên `deposit`, `withdraw`, `changeQuantity`, `rename`, `activate`… thay cho `setAnything`.
- Danh sách thuộc quyền sở hữu object: cho xem snapshot; thay đổi qua `add/remove/update` có validation.
- Giá trị tính được: ưu tiên method `totalCents()` thay vì cho caller sửa một field `total` dễ mất đồng bộ.
- DTO chỉ chuyển dữ liệu giữa tầng/API: record hoặc JavaBean có setter có thể là lựa chọn hợp lý; không cần ép mọi DTO thành rich domain model.

**Điểm cốt lõi:** Không phải “càng ít getter/setter càng tốt”. Thiết kế API phải tương ứng với điều người dùng đối tượng được phép làm và những bất biến cần giữ.

## 6. Che giấu cấu trúc dữ liệu là giảm phụ thuộc vào implementation

Hãy so sánh hai API:

~~~java
// Client phụ thuộc vào cấu trúc lưu trữ.
Map<String, LineSnapshot> getInternalMap();

// Client phụ thuộc vào khả năng cần dùng.
void putLine(String sku, long priceCents, int quantity);
void changeQuantity(String sku, int quantity);
List<LineSnapshot> lines();     // snapshot đọc
long totalCents();
~~~

Với thiết kế thứ hai, implementation có thể chuyển từ `LinkedHashMap` sang cấu trúc phù hợp hơn, thêm chỉ mục theo SKU, cache tổng tiền hoặc lưu các bản ghi khác mà caller vẫn dựa vào hợp đồng công khai.

~~~mermaid
classDiagram
    class CartClient {
      +renderCart()
      +updateQuantity()
    }
    class ShoppingCart {
      -Map~String,LineSnapshot~ lines
      +putLine(String,long,int)
      +changeQuantity(String,int)
      +removeLine(String) boolean
      +lines() List~LineSnapshot~
      +totalCents() long
    }
    class LineSnapshot {
      <<record>>
      +sku() String
      +unitPriceCents() long
      +quantity() int
    }
    CartClient --> ShoppingCart : gọi API công khai
    ShoppingCart o--> LineSnapshot : chứa dữ liệu bất biến
~~~

**Che giấu implementation** không có nghĩa client không biết gì về dữ liệu. Client vẫn cần tên SKU, giá, số lượng nếu đó là mục đích nghiệp vụ; điều nó không cần biết là object lưu chúng bằng `ArrayList`, `LinkedHashMap` hay bảng DB.

## 7. Quy trình refactor an toàn trong dự án đang chạy

1. **Xác định ownership của dữ liệu:** Ai được quyền tạo, giữ, thay và hủy collection hoặc object? Tìm mọi đường sửa hiện có: field public, getter, setter, alias từ constructor, callback, serialization.
2. **Ghi hợp đồng trước thay đổi:** Field có cho phép null không, duplicate không, thứ tự có ý nghĩa không, kiểu ngoại lệ nào được công bố, hành động nào phải bảo toàn dữ liệu?
3. **Thêm characterization/regression tests:** Kiểm tra dữ liệu hợp lệ, input sai, giá trị biên và tác dụng phụ mà client thực sự trông đợi.
4. **Đưa thao tác cập nhật vào class sở hữu state:** Ví dụ `addLine`, `removeLine`, `changeQuantity`. Validation trước mutation; giữ trạng thái hợp lệ cả khi exception xảy ra.
5. **Thu hẹp quyền truy cập field:** Chuyển thành `private` khi có thể; thay client bằng API mới một cách có kiểm soát.
6. **Bảo vệ đầu vào/đầu ra:** Copy collection khi nhận vào nếu nhận ownership; trả snapshot hoặc view thích hợp; nếu element mutable cần bản sao an toàn hoặc value object.
7. **Dọn đường tắt cũ:** Ngừng trả tham chiếu mutable, tránh setter tùy ý phá invariant. Với public API đã phát hành, lên kế hoạch deprecation/migration hoặc adapter phù hợp.
8. **Chạy test và review diff:** Xác nhận invariant, concurrency contract nếu có, hiệu năng đối với collection lớn và serialization/API compatibility.

~~~mermaid
flowchart TD
    A["Quan sát alias / field rò rỉ"] --> B["Xác định invariant và contract hiện có"]
    B --> C["Viết test bảo vệ hành vi"]
    C --> D["Tạo API thao tác có kiểm soát"]
    D --> E["Ẩn field và defensive copy"]
    E --> F{"Test regression + bất biến PASS?"}
    F -->|Không| G["Sửa nguyên nhân rồi chạy lại"]
    G --> F
    F -->|Có| H["Đổi client, dọn API cũ, review"]
~~~

### Các điểm tương thích cần cân nhắc

- **API/source compatibility:** Đổi field `public` thành `private` khiến client đang gọi field không biên dịch. Nếu thư viện đã được xuất bản, cần migration plan và versioning.
- **Hợp đồng collection:** Nếu client được cam kết **thứ tự**, việc chuyển `LinkedHashMap` sang `HashMap` rồi trả list có thể làm thay đổi thứ tự quan sát được. Nếu thứ tự không phải hợp đồng, đừng thêm test buộc thứ tự.
- **ORM/JPA/serialization:** Framework có thể cần constructor, access strategy hoặc annotation phù hợp. Bảo đảm dùng được với framework thay vì mở field public chỉ vì tiện.
- **Hiệu năng:** `List.copyOf` tạo snapshot khi cần; trả snapshot của collection rất lớn với tần suất cao có chi phí. Có thể cung cấp truy vấn theo trang, iterator có kiểm soát hoặc immutable data structure thích hợp. Không được hy sinh invariant chỉ vì muốn tránh copy.
- **Thread safety:** Trả snapshot an toàn không tự làm thao tác cập nhật trên collection thread-safe. Cần chiến lược đồng bộ, immutable aggregate hoặc transaction tùy ngữ cảnh.
- **Biểu diễn JSON:** DTO có thể khác mô hình miền. Một adapter/mapper nên chịu trách nhiệm chuyển đổi, tránh lộ cấu trúc lưu trữ của domain ra payload công khai.

## 8. Kiểm thử đóng gói: chứng minh bên ngoài không phá được trạng thái

Các test nên xác nhận **hành vi**, không chỉ kiểm tra rằng field mang từ khóa `private`.

| Ca kiểm thử | Thao tác | Kết quả kỳ vọng |
|---|---|---|
| Không lộ list mutable | Nhận `lines()` rồi gọi `clear()` | Bị chặn; giỏ hàng không đổi |
| Snapshot độc lập | Lấy snapshot A, update giỏ, lấy B | A giữ trạng thái cũ; B phản ánh trạng thái mới |
| Không lộ mutable element | Thử thay đổi element đã nhận | Không có đường sửa trực tiếp; nếu DTO mutable thì phải copy |
| Validate trước ghi | Gọi `putLine("", 100, 1)` | Ném `IllegalArgumentException`; tổng và lineCount giữ nguyên |
| Bất biến số lượng | `changeQuantity("BOOK", 0)` | Xóa dòng BOOK, không lưu quantity = 0 |
| Thao tác sai | `changeQuantity("UNKNOWN", 2)` | Ném `NoSuchElementException`; dữ liệu hiện có giữ nguyên |
| Tràn phép tính | Dữ liệu đủ lớn gây overflow | Không trả tổng đã wrap; có lỗi được phát hiện rõ |
| Tính ổn định hợp đồng | Đổi internal `Map` thành triển khai khác | Các ca client hợp lệ vẫn có kết quả đúng |

Có thể dùng JUnit 5 (JUnit Jupiter), đặt test trong cùng package với `EncapsulationDemo`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;

class ShoppingCartTest {
    @Test
    void returnedCollectionCannotMutateCart() {
        var cart = new EncapsulationDemo.ShoppingCart();
        cart.putLine("BOOK", 100, 2);

        List<EncapsulationDemo.LineSnapshot> before = cart.lines();
        assertThrows(UnsupportedOperationException.class, before::clear);

        cart.changeQuantity("BOOK", 3);
        assertEquals(2, before.get(0).quantity());
        assertEquals(3, cart.lines().get(0).quantity());
        assertEquals(300, cart.totalCents());
    }

    @Test
    void failedValidationDoesNotCorruptState() {
        var cart = new EncapsulationDemo.ShoppingCart();
        cart.putLine("BOOK", 100, 2);

        assertThrows(IllegalArgumentException.class,
            () -> cart.putLine("PEN", -1, 2));
        assertThrows(IllegalArgumentException.class,
            () -> cart.changeQuantity("BOOK", -4));

        assertEquals(1, cart.lineCount());
        assertEquals(200, cart.totalCents());
    }

    @Test
    void removingByZeroKeepsInvariant() {
        var cart = new EncapsulationDemo.ShoppingCart();
        cart.putLine("BOOK", 100, 2);
        cart.changeQuantity("BOOK", 0);

        assertTrue(cart.lines().isEmpty());
        assertEquals(0, cart.totalCents());
    }
}
~~~

Ví dụ test trên dựa vào class demo cùng package (các nested class không khai báo `public`). Dự án thực tế nên đặt mỗi kiểu vào tệp thích hợp và tổ chức access modifier theo API của package/module.

Cũng cần kiểm thử ở **ranh giới đối tượng đầu vào**. Nếu constructor nhận `List<MutableLine>` rồi lưu tham chiếu trực tiếp, người gọi vẫn có thể sửa `MutableLine` hoặc list sau khi constructor trả về, dù getter đã defensive copy.

## 9. Những lỗi refactor dễ mắc

**Lỗi 1 — “Private rồi là xong”.** Getter trả `List`/`Map` gốc vẫn lộ dữ liệu. Cần xem toàn bộ **đường tham chiếu** vào và ra object.

**Lỗi 2 — Tạo setter cho mọi field.** Setter tự do cho `balance`, `items`, `status` có thể cho phép trạng thái bất hợp lệ. Nên chọn những thao tác hợp lệ của miền.

**Lỗi 3 — Nghĩ `final` làm object bất biến.** `private final List<T>` vẫn bị thay đổi nội dung khi lớp sở hữu gọi `add/remove`; điều này hoàn toàn hợp lệ nếu có kiểm soát. Nếu reference bị lộ, bên ngoài cũng có thể thay đổi nó.

**Lỗi 4 — Nhầm unmodifiable view với snapshot.** `Collections.unmodifiableList(source)` không cho sửa qua wrapper nhưng vẫn thấy sửa đổi từ `source`; `List.copyOf(source)` tạo snapshot cấu trúc (nhưng phần tử vẫn được chia sẻ).

**Lỗi 5 — Sao chép list mà quên element.** `new ArrayList<>(people)` không deep-copy `Person`. Sửa `peopleCopy.get(0).setName("X")` có thể sửa dữ liệu nội bộ nếu phần tử cùng tham chiếu.

**Lỗi 6 — Dựa hoàn toàn vào record để khẳng định deep immutable.** Record với `List`, `Date` hoặc mảng chỉ có field cuối cùng; phần tử/đối tượng lồng nhau có thể mutable. Phải defensive copy tại constructor và accessor khi cần.

**Lỗi 7 — Bỏ quên tính nguyên tử khi mutate.** Nếu update state trước rồi mới validate hoặc gọi logic có thể ném lỗi, object có thể bị dở dang. Tính trước, kiểm tra trước, rồi mới commit; với nhiều resource có thể cần transaction.

**Lỗi 8 — Phá giao diện công khai của thư viện mà không có kế hoạch.** Không nên xem thay `public field` thành private là refactor hoàn toàn tương thích ở ranh giới người dùng thư viện. Cần kiểm thử tương thích API và hướng dẫn migration.

## 10. Bài tập áp dụng

**Bài 1 — Chỉ ra lỗ hổng:**

~~~java
class Library {
    private final List<StringBuilder> titles = new ArrayList<>();

    void add(StringBuilder title) { titles.add(title); }
    List<StringBuilder> getTitles() { return List.copyOf(titles); }
}
~~~

Hãy mô tả **hai đường** làm thay đổi tiêu đề nội bộ ngoài ý muốn: sửa `StringBuilder` sau khi truyền vào `add`, và sửa một `StringBuilder` nhận được từ `getTitles`. Thử sửa thiết kế bằng `List<String>` (với `String` immutable) hoặc copy giá trị khi vào/ra.

**Bài 2 — Thay API setter:** Một `Employee` có `setSalaryCents(long)` công khai. Hãy xác định invariant tiền lương và đề xuất method chuyên biệt (`adjustSalary` hoặc `changeSalary` với kiểm tra, xác thực quyền theo ngữ cảnh). Viết test cho số âm và số vượt giới hạn nghiệp vụ.

**Bài 3 — Danh sách đơn hàng:** Đổi `ShoppingCart.lines()` sang trả live unmodifiable view thay vì snapshot. Viết test để phân biệt **A có giữ nguyên sau update hay không**, rồi quyết định hành vi nào phù hợp contract.

**Bài 4 — Đổi cấu trúc bên trong:** Thay `LinkedHashMap` bằng một cấu trúc khác nhưng giữ `putLine`, `changeQuantity`, `removeLine` và `totalCents`. Nếu thứ tự trả về chưa được công bố, không cần buộc client phụ thuộc vào thứ tự nội bộ.

**Bài 5 — Xử lý null, race và overflow:** Mở rộng bộ test với null SKU, SKU không tồn tại, số tiền lớn và gọi đồng thời. Nêu rõ đâu là lỗi validation và đâu là yêu cầu thread-safety cần bổ sung vào hợp đồng.

### Tiêu chí hoàn thành

Bạn có thể nhận ra đường rò rỉ trạng thái qua field, getter, constructor hoặc phần tử mutable; thiết kế API mutation giữ invariant; chọn **snapshot/view/copy** phù hợp; và chứng minh bằng Java test rằng mã client không thể tùy ý làm hỏng cấu trúc nội bộ. Khi refactor thư viện hoặc hệ thống đang chạy, bạn cũng biết kiểm tra tương thích giao diện công khai, framework và concurrency.