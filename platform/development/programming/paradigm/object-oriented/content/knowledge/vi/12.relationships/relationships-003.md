# Tập hợp (Aggregation) và hợp thành (Composition) trong OOP Java

**Chủ đề:** Hai cách biểu diễn quan hệ toàn thể – bộ phận (*whole–part relationship*) giữa các đối tượng: **tập hợp (aggregation)** và **hợp thành (composition)**. Bài học tập trung vào cách chọn đúng quan hệ, nhận biết quyền sở hữu (*ownership*), thiết kế vòng đời đối tượng và thể hiện quan hệ bằng Java/UML.

> **Phân biệt thuật ngữ:** “Tập hợp” ở đây là **aggregation trong mô hình đối tượng/UML**, không đồng nghĩa với kiểu `Collection`, `List` hay `Set` của Java Collections Framework. Một trường kiểu `List<T>` tự nó chưa nói lên quan hệ đang là aggregation hay composition.

## 1. Nền tảng: quan hệ “có/chứa” chưa đủ để kết luận

Giả sử một `Team` có nhiều `Employee`, một `Order` có nhiều `OrderLine`. Cả hai đều có thể biểu diễn bằng trường tham chiếu hay danh sách Java:

~~~java
class Team {
    private java.util.List<Employee> employees;
}

class Order {
    private java.util.List<OrderLine> lines;
}
~~~

Cú pháp trên **không chứng minh** bất kỳ quan hệ nào là hợp thành. Muốn chọn mô hình, cần hỏi:

1. **Bộ phận có danh tính và ý nghĩa riêng ngoài toàn thể không?** Nhân viên vẫn là nhân viên khi rời đội; một dòng đơn hàng thường chỉ có ý nghĩa trong chính đơn hàng đó.
2. **Ai sở hữu và quyết định việc tạo, gắn, gỡ và hủy bộ phận?** Đơn hàng thường quản lý các dòng của mình; đội chỉ tập hợp nhân viên đang tham gia.
3. **Một bộ phận có thể thuộc nhiều toàn thể cùng lúc không?** Một nhân viên có thể tham gia hai đội nếu nghiệp vụ cho phép; một dòng đơn hàng cụ thể không nên đồng thời thuộc hai đơn hàng.
4. **Nếu xóa toàn thể, điều gì xảy ra theo quy tắc nghiệp vụ?** Giải tán đội không có nghĩa nhân viên bị xóa khỏi hệ thống; xóa một đơn nháp có thể xóa các dòng của đơn đó.

Đó là các quy tắc nghiệp vụ, không phải đặc điểm tự động của `List`, `new`, `final` hay cơ chế thu gom rác.

## 2. Ba quan hệ dễ nhầm lẫn

| Quan hệ UML | Ý nghĩa cơ bản | Ví dụ | Ký hiệu đầu toàn thể |
|---|---|---|---|
| **Association** (liên kết) | Các đối tượng biết hoặc tương tác với nhau; không mặc định quan hệ toàn thể–bộ phận | `Doctor` khám `Patient` | Đường nối thường |
| **Aggregation** (tập hợp/chia sẻ) | Một đối tượng nhóm/có các đối tượng khác; phần tử có thể tồn tại độc lập | `Team` gồm các `Employee` | Hình thoi **rỗng** |
| **Composition** (hợp thành) | Quan hệ toàn thể–bộ phận với **quyền sở hữu mạnh**, bộ phận thuộc tối đa một toàn thể tại một thời điểm | `Order` sở hữu `OrderLine` | Hình thoi **đặc** |

**Điểm cần chính xác:** UML định nghĩa *shared aggregation* (hình thoi rỗng) khá lỏng, không gán sẵn một quy tắc vòng đời cụ thể. Vì thế trong tài liệu thiết kế nghiêm túc, nếu chỉ cần “đội có tham chiếu tới nhân viên”, một **association** thông thường cũng có thể rõ ràng hơn hình thoi rỗng. **Composition** có ngữ nghĩa mạnh hơn: phần tử nằm dưới quyền sở hữu của một composite tại một thời điểm; khi toàn thể bị hủy trong mô hình, các phần thuộc nó cũng bị hủy theo quy tắc sở hữu.

~~~mermaid
classDiagram
    class Team
    class Employee
    class PurchaseOrder
    class OrderLine
    Team "1" o-- "0..*" Employee : tập hợp / tham gia
    PurchaseOrder "1" *-- "0..*" OrderLine : sở hữu
~~~

Trong class diagram, **hình thoi luôn đặt ở phía đối tượng toàn thể**: phía `Team` hay `PurchaseOrder`, không đặt tại phía đối tượng bộ phận. Bội số `0..*` là lựa chọn theo ví dụ: đội có thể chưa có thành viên, đơn nháp có thể chưa có dòng. Nếu quy tắc yêu cầu một đơn đã xác nhận phải có ít nhất một dòng, hãy biểu diễn và kiểm tra ràng buộc đó ở trạng thái phù hợp.

## 3. Aggregation: đội tập hợp nhân viên độc lập

Giả sử nhân viên có thể tham gia nhiều nhóm công việc. `Team` giữ các tham chiếu đến `Employee`, nhưng `Employee` được tạo và quản lý độc lập. Khi bỏ nhân viên khỏi nhóm, đối tượng nhân viên vẫn tồn tại để tham gia nhóm khác.

**Tệp `AggregationDemo.java` — Java 17+:**

~~~java
import java.util.LinkedHashSet;
import java.util.Objects;
import java.util.Set;

record Employee(String id, String name) {
    Employee {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(name, "name");
        if (id.isBlank() || name.isBlank()) {
            throw new IllegalArgumentException("Employee id/name must not be blank");
        }
    }
}

final class Team {
    private final String name;
    private final Set<Employee> members = new LinkedHashSet<>();

    Team(String name) {
        this.name = Objects.requireNonNull(name, "name");
    }

    void addMember(Employee employee) {
        members.add(Objects.requireNonNull(employee, "employee"));
    }

    boolean removeMember(Employee employee) {
        return members.remove(employee);
    }

    Set<Employee> members() {
        return Set.copyOf(members); // Trả về bản xem không sửa được.
    }

    String name() {
        return name;
    }
}

public class AggregationDemo {
    public static void main(String[] args) {
        Employee lan = new Employee("E01", "Lan"); // Tồn tại độc lập
        Team backend = new Team("Backend");
        Team mentoring = new Team("Mentoring");

        backend.addMember(lan);
        mentoring.addMember(lan); // Cùng một Employee ở hai Team

        backend.removeMember(lan);

        System.out.println(backend.members().contains(lan));  // false
        System.out.println(mentoring.members().contains(lan)); // true
        System.out.println(lan.name());                        // Lan
    }
}
~~~

Biên dịch và chạy: `javac AggregationDemo.java`, sau đó `java AggregationDemo`.

**Điểm thiết kế quan trọng:**

- `Employee` được tạo **trước và độc lập với** `Team`. Việc rời một nhóm không làm mất thực thể nhân viên.
- Theo nghiệp vụ giả định, cùng một nhân viên được phép tham gia nhiều nhóm. Nếu hệ thống quy định mỗi nhân viên chỉ có một nhóm, phải thêm ràng buộc cho miền nghiệp vụ; UML aggregation không tự áp đặt hay kiểm tra ràng buộc đó.
- `Set.copyOf(members)` tạo một tập hợp không thể sửa qua tham chiếu trả về, tránh người gọi `team.members().clear()` để làm hỏng trạng thái bên trong. Trong ví dụ, `Employee` là `record` bất biến; nếu phần tử có thể đổi trạng thái thì chỉ trả về `Set.copyOf` **không** làm các phần tử trở thành bất biến.
- `Set` nhận biết phần tử trùng bằng `equals()/hashCode()`. Với `record Employee`, cả `id` và `name` tham gia so sánh; ở hệ thống thực tế có thể muốn quản lý duy nhất theo mã nhân viên thay vì hai trường này.

**Không diễn giải sai vòng đời:** Xóa một biến `Team` hoặc gọi `removeMember` không kích hoạt thao tác “xóa đối tượng Employee” trong JVM. Java không có phép `delete object` thủ công kiểu C++; một đối tượng chỉ đủ điều kiện được GC khi không còn đường tham chiếu mạnh giữ nó sống, và thời điểm GC không được bảo đảm.

## 4. Composition: đơn hàng sở hữu các dòng hàng

Một `OrderLine` mô tả số lượng và đơn giá của một mặt hàng **trong một đơn hàng cụ thể**. Trong mô hình này, dòng hàng được sinh ra qua `Order`, không được chia sẻ giữa hai đơn và không được quản lý như một thực thể độc lập.

Ví dụ dùng **đối tượng con riêng tư** và API hành vi thay vì công khai `List<OrderLine>`. Đây là cách thể hiện ownership tốt hơn việc chỉ viết `private final List<...>`.

**Tệp `CompositionDemo.java` — Java 17+:**

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Order {
    private final String orderId;
    private final List<LineItem> lines = new ArrayList<>();
    private boolean submitted;

    // Chỉ Order có thể tạo và truy cập kiểu nội bộ này.
    private static final class LineItem {
        private final String sku;
        private final int quantity;
        private final BigDecimal unitPrice;

        private LineItem(String sku, int quantity, BigDecimal unitPrice) {
            this.sku = sku;
            this.quantity = quantity;
            this.unitPrice = unitPrice;
        }

        private BigDecimal subtotal() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    Order(String orderId) {
        this.orderId = Objects.requireNonNull(orderId, "orderId");
        if (orderId.isBlank()) {
            throw new IllegalArgumentException("Order id must not be blank");
        }
    }

    void addLine(String sku, int quantity, BigDecimal unitPrice) {
        if (submitted) {
            throw new IllegalStateException("Submitted order is locked");
        }
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");
        if (sku.isBlank() || quantity <= 0 || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid order line");
        }

        // LineItem được tạo và giữ hoàn toàn bên trong Order.
        lines.add(new LineItem(sku, quantity, unitPrice));
    }

    BigDecimal total() {
        return lines.stream()
                .map(LineItem::subtotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    int lineCount() {
        return lines.size();
    }

    void submit() {
        if (submitted) {
            throw new IllegalStateException("Already submitted");
        }
        if (lines.isEmpty()) {
            throw new IllegalStateException("Cannot submit an empty order");
        }
        submitted = true;
    }

    String id() {
        return orderId;
    }
}

public class CompositionDemo {
    public static void main(String[] args) {
        Order first = new Order("ORD-100");
        Order second = new Order("ORD-101");

        first.addLine("JAVA-BOOK", 2, new BigDecimal("125000"));
        second.addLine("JAVA-BOOK", 1, new BigDecimal("125000"));

        first.submit();
        System.out.println(first.total());     // 250000
        System.out.println(second.total());    // 125000
        System.out.println(first.lineCount()); // 1
        System.out.println(second.lineCount());// 1
    }
}
~~~

Biên dịch và chạy: `javac CompositionDemo.java`, sau đó `java CompositionDemo`.

Hai đơn có thể cùng tham chiếu **mã sản phẩm** `"JAVA-BOOK"`, nhưng mỗi đơn sở hữu một đối tượng `LineItem` riêng. Đây là khác biệt giữa **chia sẻ thông tin về sản phẩm** và **chia sẻ chính phần tử cấu thành đơn hàng**. Sản phẩm trong catalog có vòng đời riêng; còn `LineItem` biểu diễn giá/số lượng tại một đơn hàng.

Trong ví dụ, `LineItem` là lớp lồng `private`, được tạo bằng `Order.addLine()` và không thoát ra qua API. `BigDecimal` là bất biến; danh sách nội bộ không bị lộ. Điều đó hỗ trợ bất biến nghiệp vụ rằng không thể lấy một dòng từ đơn A rồi gắn trực tiếp sang đơn B. `final` trên tham chiếu danh sách chỉ cấm gán lại biến `lines`; chính việc **đóng gói và kiểm soát API** mới bảo vệ nội dung danh sách.

**Vòng đời ở hai tầng cần phân biệt:**

- **Tầng domain/UML:** nếu đơn bị hủy khỏi mô hình, các dòng thuộc đơn cũng bị hủy theo quyết định nghiệp vụ, không được giữ lại như dòng của một đơn khác.
- **Tầng runtime Java:** JVM không tự xóa đệ quy các đối tượng vào đúng thời điểm bạn “hủy đơn”. GC dựa trên khả năng tiếp cận của tham chiếu; các quan hệ composition cần được thể hiện bằng API và quy tắc domain. Nếu các phần tử đã bị rò rỉ ra ngoài qua tham chiếu khác, chúng vẫn có thể tồn tại trong bộ nhớ.
- **Tầng database:** xóa hàng `orders` không mặc nhiên xóa hàng `order_lines`; cần cơ chế phù hợp, ví dụ transaction, foreign key `ON DELETE CASCADE`, hoặc ánh xạ ORM với cascade/orphan removal đúng trường hợp.

## 5. Cách nhận ra quan hệ từ yêu cầu nghiệp vụ

| Câu hỏi | Nghiêng về aggregation / association | Nghiêng về composition |
|---|---|---|
| Phần tử có ý nghĩa độc lập không? | Có: nhân viên, bác sĩ, tài khoản | Không, hoặc bị ràng buộc chặt với toàn thể: dòng đơn hàng |
| Có thể đồng thời là bộ phận của nhiều toàn thể không? | Có thể, tùy mô hình | **Không** theo ngữ nghĩa UML của composition |
| Ai quản lý việc tạo và xóa phần tử? | Thực thể/dịch vụ độc lập | Toàn thể thường kiểm soát |
| Xóa toàn thể có xóa phần tử trong mô hình không? | Thường không | Có, theo hợp đồng sở hữu |
| Chia sẻ tham chiếu cùng phần tử giữa hai toàn thể? | Có thể hợp lệ | Vi phạm exclusivity khi hai toàn thể cùng sở hữu |
| Cài đặt Java thường gặp | Tham chiếu/collection tới đối tượng bên ngoài | Tạo con qua phương thức của chủ, che giấu API thay đổi hoặc áp ràng buộc owner |

**Cảnh giác với ví dụ kinh điển:** `Car` – `Engine` hay `House` – `Room` không thể được chốt quan hệ chỉ nhờ từ ngữ. Nếu động cơ được tháo và chuyển sang xe khác, hoặc phòng được mô hình hóa độc lập trong hệ thống quản lý bất động sản, yêu cầu nghiệp vụ đã thay đổi. Với composition, có thể chuyển một part từ composite A sang B, nhưng phải **gỡ quyền sở hữu cũ trước khi gắn quyền sở hữu mới**, không được thuộc cả hai cùng thời điểm.

## 6. UML: ký hiệu, hướng, multiplicity, navigability

~~~mermaid
classDiagram
    direction LR
    class Organization {
        +name: String
    }
    class Department {
        +name: String
    }
    class Employee {
        +id: String
    }
    class PurchaseOrder {
        +id: String
        +addLine(...)
        +submit()
    }
    class OrderLine {
        +sku: String
        +quantity: int
    }

    Organization "1" o-- "0..*" Department : nhóm các phòng ban
    Department "0..*" -- "0..*" Employee : phân công
    PurchaseOrder "1" *-- "0..*" OrderLine : các dòng riêng
~~~

- **Hình thoi rỗng (`o--`)** biểu thị shared aggregation; **hình thoi đặc (`*--`)** biểu thị composition. Ký hiệu nằm tại đầu **whole**.
- **Multiplicity** cho biết số lượng liên kết hợp lệ tại mỗi đầu. Ví dụ `PurchaseOrder "1" *-- "0..*" OrderLine`: mỗi `OrderLine` của mô hình gắn đúng một `PurchaseOrder`, còn một đơn nháp có thể có nhiều dòng. Khi hệ thống hỗ trợ xóa/di chuyển dòng, cần định nghĩa các trạng thái chuyển tiếp hợp lệ.
- **Navigability** cho biết từ đối tượng nào có thể điều hướng tới đối tượng khác; không đồng nhất với ownership. Một composition có thể có hoặc không cho phép phần tử đi ngược về đối tượng chủ qua tham chiếu `order`.
- **Aggregation không tự làm rõ chia sẻ hoặc tồn tại lâu dài:** đừng suy luận mọi shared aggregation đều *bắt buộc* cho phép đồng sở hữu. Ràng buộc đó do nghiệp vụ xác định. Nếu không cần ngữ nghĩa toàn thể–bộ phận rõ, dùng association thường đủ.
- Một composition **không yêu cầu mọi trường hợp phải có đối tượng con tại thời điểm khởi tạo**. Đơn nháp chưa có dòng là hợp lệ nếu trạng thái “đã gửi” yêu cầu `lineCount >= 1` và được kiểm tra khi `submit()`.

## 7. Quy tắc triển khai thực tế trong Java

**Để biểu diễn aggregation đúng ý định:**

1. Truyền phần tử được tạo từ ngoài vào constructor hoặc `addMember()` của đối tượng nhóm.
2. Khi gỡ khỏi nhóm, chỉ thay đổi **quan hệ thành viên**, không vô tình xóa phần tử gốc.
3. Trả về collection không cho phép caller sửa trạng thái nội bộ; cân nhắc snapshot/danh sách bất biến tùy nhu cầu.
4. Xác định rõ phần tử được phép chia sẻ giữa nhiều nhóm hay chỉ được tham gia một nhóm; đây là luật domain, không phải tính năng của hình thoi.

**Để biểu diễn composition rõ ràng:**

1. Xác định ai là chủ (*owner*) và part có được tồn tại độc lập không.
2. Cho owner tạo/thêm/sửa/xóa part qua các phương thức có tên theo hành vi nghiệp vụ; ngăn gắn một part vào nhiều owner cùng lúc.
3. Không trả ra collection có thể sửa trực tiếp hoặc một part có thể bị tái gán owner tùy tiện. Nếu phải trả ra part, dùng giá trị bất biến, DTO/snapshot, hoặc kiểm tra owner.
4. Kiểm tra invariants ở ranh giới của aggregate: số lượng dương, giá không âm, đơn đã khóa thì không thể sửa, đơn đã gửi phải có dòng.
5. Quyết định rõ chính sách lưu trữ: khi xóa owner thì xử lý part nào, trong cùng transaction nào; việc đó **không phát sinh tự động** từ quan hệ Java.

Một dạng composition khác thường gặp là constructor khởi tạo part một lần:

~~~java
final class Computer {
    private final Motherboard motherboard;

    Computer() {
        this.motherboard = new Motherboard();
    }
}
~~~

Ví dụ này gợi ý quyền sở hữu, nhưng **chưa chứng minh** mô hình composition nếu `Computer` còn công khai reference part cho bên ngoài thay chủ sở hữu hoặc cho phép chia sẻ. Ngữ nghĩa đến từ luật domain và API được thiết kế, không đến từ vị trí đặt từ khóa `new`.

## 8. Khi làm việc với Spring/JPA

Java object graph, UML và lưu trữ quan hệ là ba lớp khác nhau. Một liên kết `@OneToMany` **không đủ** để bảo đảm composition. Ví dụ có chủ đích `PurchaseOrderEntity` quản lý `OrderLineEntity` có thể dùng:

~~~java
// Minh họa trường ánh xạ trong PurchaseOrderEntity (không phải lớp đầy đủ)
@OneToMany(mappedBy = "order",
           cascade = CascadeType.ALL,
           orphanRemoval = true)
private List<OrderLineEntity> lines = new ArrayList<>();
~~~

Cần thêm trường `@ManyToOne` và `@JoinColumn` phù hợp ở phía `OrderLineEntity`, đồng bộ **cả hai phía** liên kết qua phương thức `addLine/removeLine`, và đặt transaction đúng chỗ. Khi orphan removal bật, loại một dòng khỏi quan hệ được quản lý có thể dẫn tới xóa dòng tại thời điểm flush; hãy chắc chắn đây đúng là nghiệp vụ mong muốn. `CascadeType.ALL` bao gồm cả REMOVE nên nguy hiểm nếu bộ phận thực sự là entity chia sẻ, chẳng hạn `Employee` được nhiều nhóm tham chiếu.

Đối với aggregation `Team` – `Employee`, thường không nên cấu hình cascade REMOVE từ Team sang Employee. Xóa nhóm chỉ cần xóa membership (ví dụ hàng ở bảng liên kết) nếu nhân viên vẫn tồn tại độc lập. Lựa chọn `@ManyToMany`, một entity `Membership`, hoặc bảng join có ràng buộc riêng còn phụ thuộc việc cần lưu ngày gia nhập, vai trò hay lịch sử thay đổi.

## 9. Kiểm thử hành vi thay vì kiểm tra hình dạng mã

Với ví dụ `AggregationDemo`, những trường hợp có giá trị:

- Một `Employee` tham gia hai `Team` theo đúng chính sách đã đặt.
- Xóa khỏi team A không làm mất bản ghi nhân viên và không ảnh hưởng membership ở team B.
- Caller không thể sửa nội bộ `members` qua collection trả về.
- Giá trị rỗng/null bị chặn đúng hợp đồng.

Với `CompositionDemo`:

- Hai `Order` thêm cùng `sku` vẫn giữ **dòng riêng** và tính tổng độc lập.
- Thêm dòng có số lượng bằng 0 hoặc đơn giá âm bị từ chối.
- `submit()` từ chối đơn rỗng và khóa thao tác sửa sau khi thành công.
- API ngoài không thể lấy đối tượng `LineItem` từ đơn A rồi gắn trực tiếp vào đơn B.
- Integration test xác nhận các dòng của một đơn bị xóa theo giao dịch khi xóa đơn thật trong database, nếu đó là policy hệ thống.

Không cần kiểm thử bằng reflection chỉ để chắc chắn có trường `List<LineItem>` hay constructor gọi `new LineItem()`; điều cần bảo vệ là **quy tắc sở hữu và hành vi quan sát được**.

## 10. Sai lầm thường gặp

| Nhầm lẫn | Vì sao sai | Cách sửa |
|---|---|---|
| “Có `List` thì chắc chắn aggregation” | Collection chỉ là cấu trúc lưu tham chiếu | Dựa vào ý nghĩa domain và vòng đời |
| “Có `new` trong constructor thì chắc chắn composition” | Đối tượng con vẫn có thể bị chia sẻ hoặc đổi chủ | Bảo vệ quyền sở hữu bằng API/invariant |
| “Composition có nghĩa Java xóa con ngay khi xóa cha” | GC không phải cơ chế cascade domain | Tách quy tắc domain, tham chiếu và persistence |
| “Aggregation luôn cho phép chia sẻ giữa nhiều whole” | Shared aggregation trong UML không áp luật chia sẻ cố định | Ghi rõ ràng buộc business cụ thể |
| “Hình thoi rỗng có định nghĩa chặt như hình thoi đặc” | UML để nhiều chi tiết shared aggregation cho người mô hình hóa | Dùng association nếu không cần ownership |
| “`final List` không thể bị sửa” | `final` chỉ giữ nguyên tham chiếu | Đóng gói danh sách; trả snapshot/read-only view |
| “`CascadeType.ALL` dùng được cho mọi quan hệ has-a” | REMOVE có thể xóa dữ liệu chia sẻ | Chọn cascade theo ownership thực tế |

## 11. Bài tập vận dụng

**Bối cảnh:** Nền tảng học tập có `Course`, `Student`, `Enrollment`, `Quiz`, `Question`.

Hãy quyết định đâu là association, aggregation hoặc composition dựa trên yêu cầu sau:

1. Một `Student` được ghi danh nhiều `Course`; xóa khóa học không được xóa sinh viên.
2. `Enrollment` lưu sinh viên, khóa học, ngày ghi danh và trạng thái; chỉ tồn tại khi một lượt đăng ký hợp lệ tồn tại, nhưng có yêu cầu lưu lịch sử dù khóa học đã đóng.
3. Mỗi bản `Quiz` có các `Question` riêng; khi hủy bản nháp quiz thì hủy câu hỏi của bản nháp. Ngân hàng câu hỏi gốc (nếu có) vẫn độc lập và có thể được dùng để tạo bản sao cho quiz khác.

**Gợi ý thiết kế:** `Course` – `Student` là quan hệ qua `Enrollment` thay vì trực tiếp dùng composition; `Enrollment` có vòng đời riêng theo quy tắc lưu lịch sử; `Quiz` – các bản `Question` sở hữu riêng có thể là composition, còn `QuestionBankEntry` là thực thể độc lập được tham chiếu hoặc sao chép dữ liệu. Sơ đồ chỉ đúng khi gắn với các ràng buộc vừa nêu.

**Tự kiểm tra:** Bạn có chỉ ra được ai có quyền tạo/xóa part, khi toàn thể bị xóa thì dữ liệu nào cần giữ, và một part có thể thuộc bao nhiêu whole tại một thời điểm không?

---

**Ghi nhớ:** *Aggregation* thể hiện một quan hệ toàn thể–bộ phận lỏng, với bộ phận có thể tồn tại độc lập; *composition* biểu diễn **quyền sở hữu mạnh và độc quyền tại một thời điểm**. Sự khác biệt nằm ở **hợp đồng miền nghiệp vụ** và cách bảo vệ hợp đồng đó, không ở việc Java dùng trường, collection hay dấu `new`.