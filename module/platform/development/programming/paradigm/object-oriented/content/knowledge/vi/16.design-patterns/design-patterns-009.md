# State Pattern: tổ chức hành vi theo trạng thái của đối tượng

**Chủ đề:** OOP → Mẫu thiết kế → **State và hành vi theo trạng thái**.

**Mục tiêu:** hiểu vì sao cùng một lời gọi có thể có kết quả khác nhau tùy trạng thái hiện tại; viết được State Pattern bằng Java, thiết kế quy tắc chuyển trạng thái hợp lệ, kiểm thử luồng và nhận biết khi nào chỉ cần enum hoặc switch đơn giản.

## 1. Vì sao trạng thái lại ảnh hưởng đến hành vi?

Hãy xét một đơn hàng trực tuyến. Hệ thống cho phép người dùng hoặc nhân viên thực hiện các thao tác:

- **Xác nhận thanh toán** khi đơn mới tạo.
- **Đánh dấu đã bàn giao vận chuyển** sau khi thanh toán được xác nhận.
- **Hủy đơn** khi đơn vẫn đang chờ thanh toán.

Cùng một yêu cầu **cancel()** có ý nghĩa khác nhau: đơn mới tạo thì được hủy, còn đơn đã giao vận chuyển thì không thể dùng cùng quy trình đó để hủy. Tương tự, một đơn đã thanh toán không nên xác nhận thanh toán lần thứ hai như thể chưa thu tiền.

Nói cách khác, **hành vi hợp lệ phụ thuộc vào trạng thái**. Nếu code bỏ qua trạng thái, hệ thống có thể nhận các thao tác không có nghĩa hoặc thực hiện quy trình sai.

Ở phiên bản nhỏ, ta có thể kiểm tra trực tiếp:

~~~java
void confirmPayment() {
    if (status != OrderStatus.CREATED) {
        throw new IllegalStateException(
                "Chỉ đơn mới tạo mới được xác nhận thanh toán");
    }
    status = OrderStatus.PAID;
}
~~~

Đoạn code này hoàn toàn hợp lý khi chỉ có vài trạng thái và quy tắc ngắn. Nhưng khi thêm nhiều thao tác và biến thể, các điều kiện **if/switch** có thể xuất hiện rải rác trong các phương thức như **confirmPayment()**, **markShipped()**, **cancel()**, **allowedActions()**, **nextStep()**. Mỗi lần thêm trạng thái mới, ta phải tìm và sửa nhiều nơi; các nhánh dễ mâu thuẫn với nhau.

**State Pattern** là một cách tổ chức những hành vi đó: đặt logic của từng trạng thái vào một đối tượng riêng, rồi để đối tượng nghiệp vụ ủy quyền cho đối tượng trạng thái hiện tại.

## 2. State Pattern là gì?

State là một **mẫu thiết kế hành vi** (*behavioral design pattern*) cho phép một đối tượng thay đổi cách phản hồi với thao tác khi **trạng thái nội bộ** của nó thay đổi. Với người gọi, dường như đối tượng thay đổi hành vi, trong khi API công khai có thể giữ nguyên.

Bốn vai trò thường gặp:

| Vai trò | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Context** | Đối tượng mà client sử dụng; giữ trạng thái hiện tại và ủy quyền hành vi | **Order** |
| **State** | Hợp đồng cho các thao tác thay đổi theo trạng thái | **OrderState** |
| **Concrete State** | Cài đặt hành vi cụ thể của một trạng thái | **CreatedState**, **PaidState**, **ShippedState**, **CancelledState** |
| **Client** | Gọi API của Context, không cần điều khiển trực tiếp lớp trạng thái | Controller, service hoặc mã trong **main** |

Mối quan hệ tổng quát:

~~~mermaid
classDiagram
    class Order {
        -state: OrderState
        +confirmPayment()
        +markShipped()
        +cancel()
        +status() OrderStatus
        +allowedActions() Set~Action~
    }
    class OrderState {
        <<interface>>
        +status() OrderStatus
        +allowedActions() Set~Action~
        +confirmPayment(order)
        +markShipped(order)
        +cancel(order)
    }
    class CreatedState
    class PaidState
    class ShippedState
    class CancelledState
    Order o--> OrderState : trạng thái hiện tại
    OrderState <|.. CreatedState
    OrderState <|.. PaidState
    OrderState <|.. ShippedState
    OrderState <|.. CancelledState
~~~

Ở đây **Order** không tự hỏi “trạng thái hiện tại là gì?” trong mọi thao tác. Nó gọi **state.confirmPayment(this)** hoặc **state.cancel(this)**. Mỗi state quyết định xử lý hợp lệ ra sao và chuyển sang state nào.

**Điểm quan trọng:** State Pattern không làm quy tắc nghiệp vụ biến mất. Nó đặt quy tắc vào các đơn vị dễ tìm, dễ kiểm tra, dễ mở rộng hơn khi sự khác biệt theo trạng thái đủ lớn.

## 3. Xác định máy trạng thái trước khi viết lớp

Trước khi viết Java, hãy liệt kê rõ các trạng thái và sự kiện chuyển đổi. Với ví dụ này, quy trình được đơn giản hóa thành bốn trạng thái:

| Trạng thái hiện tại | Xác nhận thanh toán | Đánh dấu đã gửi | Hủy |
| --- | --- | --- | --- |
| **CREATED** — mới tạo | Chuyển **PAID** | Từ chối | Chuyển **CANCELLED** |
| **PAID** — đã xác nhận tiền | Từ chối | Chuyển **SHIPPED** | Từ chối |
| **SHIPPED** — đã bàn giao vận chuyển | Từ chối | Từ chối | Từ chối |
| **CANCELLED** — đã hủy | Từ chối | Từ chối | Từ chối |

**Giả định nghiệp vụ của ví dụ:** không hủy sau khi thanh toán vì trường hợp này cần quy trình hoàn tiền riêng. Hệ thống thật có thể cho phép yêu cầu hủy, hoàn tiền, trả hàng hoặc nhiều trạng thái trung gian hơn. Không nên sao chép bảng này thành chính sách thương mại chung cho mọi ứng dụng.

Sơ đồ chuyển trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> PAID: confirmPayment()
    CREATED --> CANCELLED: cancel()
    PAID --> SHIPPED: markShipped()
    SHIPPED --> [*]
    CANCELLED --> [*]
~~~

Trong sơ đồ, **SHIPPED** và **CANCELLED** không có chuyển tiếp trong *phạm vi mô hình minh họa*. Điều đó không có nghĩa đơn đã vận chuyển không thể tiếp tục sang **DELIVERED**, **RETURNED** hoặc trạng thái khác khi phát triển quy trình thực tế.

### Phân biệt trạng thái, sự kiện và hành vi

- **Trạng thái:** đơn hiện đang ở đâu trong vòng đời, chẳng hạn **PAID**.
- **Sự kiện/lệnh:** có yêu cầu thực hiện điều gì, chẳng hạn **markShipped()**.
- **Guard/điều kiện:** điều kiện nào phải đúng để chấp nhận lệnh, chẳng hạn đơn phải ở **PAID** và thông tin bàn giao đã được xác nhận.
- **Chuyển trạng thái:** kết quả thay đổi từ **PAID** sang **SHIPPED**.
- **Tác dụng phụ:** gửi email, gọi cổng thanh toán hoặc ghi database. Những việc này cần thiết kế riêng để tránh tác dụng phụ bị thực hiện hai lần.

State Pattern chủ yếu giúp tổ chức **hành vi và chuyển trạng thái**, chứ tự nó không bảo đảm giao dịch, xác thực, đồng bộ hay hiệu lực của sự kiện bên ngoài.

## 4. Ví dụ Java 17+ hoàn chỉnh

Tạo file **OrderStateDemo.java**. Mã dưới đây độc lập, không cần Spring và không cần thư viện ngoài.

**Thiết kế được chọn:**

1. **Order** là Context, giữ **OrderState** hiện tại trong field **private**.
2. **OrderState** định nghĩa các thao tác mà state có thể xử lý; mặc định từ chối chuyển trạng thái không hợp lệ.
3. Mỗi concrete state chỉ override những hành vi được cho phép.
4. Các đối tượng state được dùng chung dưới dạng singleton **vì chúng không có dữ liệu mutable riêng**.
5. **allowedActions()** cung cấp thông tin giao diện về thao tác hợp lệ; kiểm tra thật vẫn được thực hiện ở phía domain.

~~~java
import java.util.Objects;
import java.util.Set;

public class OrderStateDemo {

    public enum OrderStatus {
        CREATED, PAID, SHIPPED, CANCELLED
    }

    public enum Action {
        CONFIRM_PAYMENT, MARK_SHIPPED, CANCEL
    }

    public static final class Order {
        private static final OrderState CREATED_STATE = new CreatedState();
        private static final OrderState PAID_STATE = new PaidState();
        private static final OrderState SHIPPED_STATE = new ShippedState();
        private static final OrderState CANCELLED_STATE = new CancelledState();

        private final String id;
        private OrderState state = CREATED_STATE;

        public Order(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException(
                        "Mã đơn hàng không được rỗng");
            }
            this.id = id.trim();
        }

        public String id() {
            return id;
        }

        public OrderStatus status() {
            return state.status();
        }

        public Set<Action> allowedActions() {
            return state.allowedActions();
        }

        public String nextStep() {
            return state.nextStep();
        }

        // Client chỉ gọi API nghiệp vụ của Order.
        public void confirmPayment() {
            state.confirmPayment(this);
        }

        public void markShipped() {
            state.markShipped(this);
        }

        public void cancel() {
            state.cancel(this);
        }

        // Chỉ code bên trong Order được chuyển trạng thái trực tiếp.
        private void transitionTo(OrderState next) {
            state = Objects.requireNonNull(next, "next");
        }

        private static IllegalStateException invalid(
                OrderState state, String operation) {
            return new IllegalStateException(
                    operation + " is not allowed in " + state.status());
        }

        private interface OrderState {
            OrderStatus status();

            Set<Action> allowedActions();

            String nextStep();

            default void confirmPayment(Order order) {
                throw invalid(this, "confirmPayment");
            }

            default void markShipped(Order order) {
                throw invalid(this, "markShipped");
            }

            default void cancel(Order order) {
                throw invalid(this, "cancel");
            }
        }

        private static final class CreatedState implements OrderState {
            @Override
            public OrderStatus status() {
                return OrderStatus.CREATED;
            }

            @Override
            public Set<Action> allowedActions() {
                return Set.of(Action.CONFIRM_PAYMENT, Action.CANCEL);
            }

            @Override
            public String nextStep() {
                return "Chờ xác nhận thanh toán";
            }

            @Override
            public void confirmPayment(Order order) {
                order.transitionTo(PAID_STATE);
            }

            @Override
            public void cancel(Order order) {
                order.transitionTo(CANCELLED_STATE);
            }
        }

        private static final class PaidState implements OrderState {
            @Override
            public OrderStatus status() {
                return OrderStatus.PAID;
            }

            @Override
            public Set<Action> allowedActions() {
                return Set.of(Action.MARK_SHIPPED);
            }

            @Override
            public String nextStep() {
                return "Chờ bàn giao vận chuyển";
            }

            @Override
            public void markShipped(Order order) {
                order.transitionTo(SHIPPED_STATE);
            }
        }

        private static final class ShippedState implements OrderState {
            @Override
            public OrderStatus status() {
                return OrderStatus.SHIPPED;
            }

            @Override
            public Set<Action> allowedActions() {
                return Set.of();
            }

            @Override
            public String nextStep() {
                return "Đơn đã bàn giao vận chuyển";
            }
        }

        private static final class CancelledState implements OrderState {
            @Override
            public OrderStatus status() {
                return OrderStatus.CANCELLED;
            }

            @Override
            public Set<Action> allowedActions() {
                return Set.of();
            }

            @Override
            public String nextStep() {
                return "Đơn đã hủy";
            }
        }
    }

    public static void main(String[] args) {
        Order first = new Order("ORD-001");

        System.out.println(first.status());
        first.confirmPayment();
        System.out.println(first.status());

        try {
            first.cancel();
        } catch (IllegalStateException error) {
            System.out.println(error.getMessage());
        }

        System.out.println(first.status()); // Thao tác lỗi không đổi state.
        first.markShipped();
        System.out.println(first.status());

        Order second = new Order("ORD-002");
        second.cancel();
        System.out.println(second.status());
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac OrderStateDemo.java
java OrderStateDemo
~~~

Kết quả:

~~~text
CREATED
PAID
cancel is not allowed in PAID
PAID
SHIPPED
CANCELLED
~~~

### Giải thích luồng hoạt động

- **new Order("ORD-001")** tạo Context ở **CREATED_STATE**.
- Gọi **confirmPayment()**: **Order** ủy quyền cho **CreatedState**, state đó chuyển Order sang **PAID_STATE**.
- Gọi **cancel()** từ **PAID_STATE**: không có override hợp lệ nên **OrderState.cancel()** ném **IllegalStateException**. Trạng thái vẫn **PAID**.
- Gọi **markShipped()**: **PaidState** cho phép chuyển sang **SHIPPED_STATE**.
- Một đơn mới khác có thể được hủy ngay ở trạng thái **CREATED** và chuyển sang **CANCELLED_STATE**.

Mã **confirmPayment()** mô phỏng việc ghi nhận rằng thanh toán đã được xác minh. **Không gọi phương thức này chỉ vì client gửi lên thông báo “tôi đã trả tiền”**: khi tích hợp thật, server cần kiểm tra sự kiện/callback đáng tin cậy hoặc trạng thái thanh toán ở hệ thống thanh toán trước khi ghi nhận thay đổi.

### Vì sao dùng private State thay vì public setter?

Nếu có **order.setStatus(OrderStatus.SHIPPED)**, bất kỳ nơi nào cũng có thể nhảy thẳng từ **CREATED** sang **SHIPPED** và bỏ qua quy tắc. Ví dụ dùng các **command method** có ý nghĩa như **confirmPayment()** và **markShipped()**; việc chuyển trạng thái trực tiếp bị đóng bên trong lớp **Order**.

State object được chia sẻ an toàn về **mặt dữ liệu nội bộ của chính các state** vì chúng không giữ state mutable. Tuy nhiên, **Order** vẫn có field mutable **state** nên toàn bộ Order **không mặc nhiên thread-safe**. Điều này sẽ được xử lý ở phần vận hành.

## 5. Cùng API, hành vi khác nhau theo trạng thái

State Pattern không chỉ là “lưu enum dưới dạng class”. Nó đặc biệt có ích khi trạng thái quyết định **nhiều hành vi khác nhau**.

Trong ví dụ:

| Hành vi | CREATED | PAID | SHIPPED | CANCELLED |
| --- | --- | --- | --- | --- |
| **confirmPayment()** | Đổi sang PAID | Báo lỗi | Báo lỗi | Báo lỗi |
| **markShipped()** | Báo lỗi | Đổi sang SHIPPED | Báo lỗi | Báo lỗi |
| **cancel()** | Đổi sang CANCELLED | Báo lỗi | Báo lỗi | Báo lỗi |
| **allowedActions()** | Xác nhận tiền, hủy | Đánh dấu đã gửi | Trống | Trống |
| **nextStep()** | Chờ xác nhận tiền | Chờ bàn giao | Đã bàn giao | Đã hủy |

Client gọi cùng một phương thức **nextStep()** nhưng nhận mô tả khác nhau từ state hiện tại. Nếu xuất hiện các hành vi riêng như **tính chi phí hủy**, **cho phép sửa địa chỉ**, **xác định SLA**, **kiểm tra quyền thao tác** hoặc **quy định sự kiện tiếp theo**, việc tổ chức chúng theo trạng thái có thể rõ hơn một khối lớn switch nằm rải ở nhiều lớp.

Với giao diện người dùng, **allowedActions()** hữu ích để ẩn hoặc vô hiệu nút không liên quan, nhưng **không phải kiểm soát bảo mật**. Server vẫn phải xác thực người dùng, kiểm tra quyền, ràng buộc nghiệp vụ và trạng thái thực tại thời điểm thực hiện lệnh. Dữ liệu trạng thái mà UI hiển thị có thể đã cũ.

## 6. Kiểm thử quy tắc chuyển trạng thái

State Pattern cần test **đường đi hợp lệ** lẫn **thao tác bị từ chối**. Một thay đổi enum hoặc sửa quyền của state rất dễ gây lỗi nếu không kiểm tra cả hai.

Ví dụ với **JUnit 5 (Jupiter)**, đặt trong **OrderStateDemoTest.java** cùng package:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Set;
import org.junit.jupiter.api.Test;

class OrderStateDemoTest {

    @Test
    void dongThanhToanVaBanGiaoDungThuTu() {
        var order = new OrderStateDemo.Order("ORD-001");

        assertEquals(OrderStateDemo.OrderStatus.CREATED,
                order.status());

        order.confirmPayment();
        assertEquals(OrderStateDemo.OrderStatus.PAID,
                order.status());

        order.markShipped();
        assertEquals(OrderStateDemo.OrderStatus.SHIPPED,
                order.status());
    }

    @Test
    void donMoiTaoCoTheHuy() {
        var order = new OrderStateDemo.Order("ORD-002");
        order.cancel();

        assertEquals(OrderStateDemo.OrderStatus.CANCELLED,
                order.status());
        assertEquals(Set.of(), order.allowedActions());
    }

    @Test
    void khongDuocBanGiaoKhiChuaThanhToan() {
        var order = new OrderStateDemo.Order("ORD-003");

        assertThrows(IllegalStateException.class,
                order::markShipped);
        assertEquals(OrderStateDemo.OrderStatus.CREATED,
                order.status());
    }

    @Test
    void khongDuocHuySauKhiXacNhanThanhToan() {
        var order = new OrderStateDemo.Order("ORD-004");
        order.confirmPayment();

        assertThrows(IllegalStateException.class, order::cancel);
        assertEquals(OrderStateDemo.OrderStatus.PAID,
                order.status());
    }

    @Test
    void hanhDongDuocPhepThayDoiTheoState() {
        var order = new OrderStateDemo.Order("ORD-005");

        assertEquals(Set.of(
                OrderStateDemo.Action.CONFIRM_PAYMENT,
                OrderStateDemo.Action.CANCEL),
                order.allowedActions());

        order.confirmPayment();

        assertEquals(Set.of(OrderStateDemo.Action.MARK_SHIPPED),
                order.allowedActions());
    }
}
~~~

Các test này cần JUnit Jupiter trong classpath. **OrderStateDemo.java** tự chạy được mà không cần JUnit. Khi phát triển thật, bổ sung test cho các quy trình hoàn tiền, timeout, xác nhận lặp, khôi phục trạng thái từ database và thao tác đồng thời.

### Test ma trận trạng thái

Với hệ thống có nhiều trạng thái, nên tạo một **ma trận trạng thái × thao tác** và kiểm tra các ô được chấp nhận hoặc từ chối. Chỉ test một “happy path” từ đầu đến cuối sẽ bỏ sót các chuyển trạng thái bất hợp lệ. Khi các quy tắc là đặc tả nghiệp vụ quan trọng, hãy coi bảng chuyển trạng thái như một tài liệu thiết kế cần được review cùng code/test.

## 7. State khác Strategy, enum và State Machine như thế nào?

Các khái niệm này liên quan nhưng không đồng nhất:

| Kỹ thuật | Cơ chế chủ yếu | Khi nào phù hợp |
| --- | --- | --- |
| **Enum + if/switch** | Lưu mã trạng thái; dùng điều kiện để quyết định hành vi | Ít trạng thái, ít thao tác, quy tắc đơn giản và ổn định |
| **State Pattern** | Context ủy quyền cho đối tượng trạng thái; mỗi state quy định hành vi/chuyển tiếp | Nhiều hành vi phụ thuộc trạng thái, nhánh phức tạp hoặc dễ thay đổi |
| **Strategy Pattern** | Client/Context dùng một thuật toán có thể thay thế | Nhiều cách thực hiện cùng một công việc: tính thuế, phí vận chuyển, định dạng xuất |
| **Finite State Machine (FSM)** | Mô hình hình thức gồm trạng thái, sự kiện, điều kiện và chuyển tiếp | Cần đặc tả, xác minh, phát hiện trạng thái bất khả đạt hoặc quy trình phức tạp |
| **Workflow/State Machine Framework** | Máy thực thi chuyển tiếp, guard, event, persistence, action theo cấu hình/code | Quy trình dài, phân nhánh, có nhiều bước bất đồng bộ và yêu cầu vận hành đặc thù |

**State Pattern là một cách cài đặt máy trạng thái**, nhưng không phải mọi FSM đều cần State Pattern. Một bảng chuyển trạng thái và một hàm thuần túy có thể đủ cho quy trình nhỏ. Ngược lại, một thư viện workflow có thể áp dụng FSM bằng bảng dữ liệu hay cấu hình mà không tạo một concrete class cho từng state.

### State và Strategy đều dùng composition/polymorphism; khác mục đích

Giả sử **ShippingFeePolicy** có hai thuật toán **StandardFeePolicy** và **ExpressFeePolicy**. Chọn chính sách nào thường do cấu hình hoặc client quyết định; đó là hướng **Strategy**. Còn việc **Order** chuyển từ **CREATED** sang **PAID** bởi sự kiện xác nhận thanh toán là sự phát triển của **trạng thái vòng đời**; đó là hướng **State**.

Điểm khác thường gặp: **Strategy** có thể được chọn từ bên ngoài mà không tự đổi sau lời gọi; **State** thường quyết định hoặc ảnh hưởng đến state tiếp theo của Context. Đây là khác biệt về **ý định**, không phải giới hạn cú pháp cứng nhắc.

## 8. Ai được quyết định trạng thái tiếp theo?

Trong ví dụ, **concrete state** gọi **order.transitionTo(...)**. Đây là một trong các cách thiết kế.

Có ít nhất ba lựa chọn hợp lý:

1. **State tự yêu cầu chuyển:** concrete state biết trạng thái tiếp theo; code nằm gần hành vi quyết định. Ví dụ Java đã chọn cách này.
2. **Context điều phối chuyển:** concrete state trả về một kết quả/sự kiện, Context áp dụng chuyển tiếp. Phù hợp khi Context phải bảo vệ thêm các bất biến hoặc thực hiện một chuỗi xử lý thống nhất.
3. **Bộ điều phối bên ngoài:** workflow engine hoặc application service xét guard, thực hiện action và lưu state. Phù hợp khi quá trình liên quan transaction, nhiều aggregate, timeout hoặc event bất đồng bộ.

Không cần thêm lớp điều phối chỉ để “đúng mẫu”. Hãy chọn nơi đặt quy tắc khiến người đọc dễ tìm ra câu trả lời: **ở trạng thái nào, thao tác nào được phép, tại sao, và kết quả là gì?**

### Có nên dùng default method để từ chối thao tác?

Trong ví dụ, **OrderState** dùng default method ném lỗi. Điều đó có hai lợi ích: code của một state ngắn và tập trung vào điều được phép; hành vi từ chối nhất quán.

Tuy nhiên, nếu một state bỏ sót override do lỗi lập trình, mặc định ném lỗi cũng có thể che việc triển khai thiếu. Với nghiệp vụ quan trọng, cần test ma trận. Ở một thiết kế khác, có thể dùng interface buộc khai báo mọi hành vi hoặc một bảng chuyển tiếp dữ liệu để dễ audit. **Default method ở đây là lựa chọn minh họa, không phải yêu cầu bắt buộc của State Pattern.**

## 9. Thực tế: database, transaction và xử lý đồng thời

Code trong bộ nhớ ở trên dạy rõ mô hình State, nhưng chưa phải một hệ thống đặt hàng hoàn chỉnh. Có ba ranh giới quan trọng.

### 9.1. Lưu trạng thái bền vững

Nếu khởi động lại ứng dụng, field **state** trong RAM sẽ mất. Ứng dụng thật thường lưu một mã trạng thái như **CREATED**, **PAID** vào database. Khi đọc lại aggregate, hệ thống ánh xạ mã đã lưu thành State object tương ứng.

**Không nhất thiết phải serialize trực tiếp implementation của State**. Việc lưu mã trạng thái tách dữ liệu nghiệp vụ khỏi tên class Java và thuận tiện cho schema migration. Phần phục hồi trạng thái phải là API nội bộ có kiểm soát, không phải public setter cho bất cứ client nào nhảy giữa các trạng thái.

### 9.2. Hai yêu cầu đồng thời có thể phá vỡ kỳ vọng

Giả sử cùng một đơn đang ở **CREATED**. Một request **confirmPayment()**, một request **cancel()** chạy gần như đồng thời. Nếu chúng cùng đọc trạng thái cũ và ghi trạng thái mới mà không có biện pháp điều phối, có thể xảy ra mất cập nhật (*lost update*) hoặc ghi nhận hai sự kiện nghiệp vụ mâu thuẫn.

Các biện pháp tùy kiến trúc bao gồm:

- Transaction và khóa database phù hợp với đặc điểm dữ liệu.
- **Optimistic locking** với cột version; chỉ một update dựa trên version cũ được chấp nhận, request còn lại phải kiểm tra lại.
- **Conditional update** có điều kiện trạng thái, chẳng hạn “chỉ đổi CREATED → PAID nếu trạng thái hiện vẫn là CREATED”.
- Serialization các lệnh theo từng order ID khi kiến trúc thực sự cần.

Ví dụ ý tưởng SQL (cú pháp và transaction thực tế phụ thuộc database):

~~~sql
UPDATE orders
SET status = 'PAID', version = version + 1
WHERE id = :order_id
  AND status = 'CREATED'
  AND version = :expected_version;
~~~

Nếu số dòng được cập nhật là **0**, trạng thái/version không còn đúng hoặc đơn không tồn tại. Application cần phân biệt lý do và phản hồi phù hợp. **State Pattern trong JVM tự nó không cung cấp atomicity xuyên các request/instance.**

### 9.3. Tác dụng phụ phải phù hợp kết quả transaction

Một bước chuyển trạng thái có thể cần gửi email hoặc xuất sự kiện. Không nên mặc định gọi email trước khi commit transaction: nếu commit thất bại, khách có thể nhận email “đã thanh toán” dù trạng thái trong database vẫn chưa đổi.

Tùy hệ thống, có thể dùng **transactional outbox** để lưu event trong cùng transaction với thay đổi trạng thái, sau đó có worker phát event. Consumer cần idempotency/deduplication phù hợp vì việc giao event có thể lặp.

Đối với thanh toán, **confirmPayment** trong ví dụ chỉ minh họa chuyển từ **CREATED** sang **PAID** sau khi đã xác minh. Trong thực tế, phải có định danh giao dịch, chống xử lý callback lặp, xác minh chữ ký/sự kiện, xử lý tiền hoàn trả và các trạng thái thất bại/đang chờ. Các nghĩa vụ đó là thiết kế nghiệp vụ và hạ tầng, không thể được bảo đảm chỉ bằng việc chia thành State class.

## 10. Những lỗi thường gặp khi dùng State Pattern

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Mỗi state chỉ trả về một tên enum, không có hành vi khác biệt | Thêm nhiều lớp mà không giảm độ phức tạp | Giữ **enum + switch** nếu đủ rõ |
| Context có public **setState(...)** | Client vượt qua quy tắc chuyển trạng thái | Giấu state, phơi bày các phương thức nghiệp vụ có ý nghĩa |
| Concrete state vừa xử lý nhiều nghiệp vụ không liên quan vừa gọi DB/email trực tiếp | Coupling lớn, khó test và transaction khó kiểm soát | Đặt side effect và phối hợp hạ tầng ở ranh giới có trách nhiệm rõ |
| State instance dùng chung nhưng chứa dữ liệu mutable theo từng Order | Đơn này ảnh hưởng tới đơn khác, có nguy cơ race | State dùng chung nên stateless; dữ liệu theo đơn nằm trong Order hoặc state instance riêng |
| Kiểm tra trạng thái bằng dữ liệu UI đã tải trước đó | Chấp nhận thao tác dựa trên state cũ | Kiểm tra lại khi xử lý request, cập nhật có điều kiện |
| Cho phép chuyển tiếp tùy ý khi đọc từ DB | Phá bất biến vòng đời | Có cơ chế restore nội bộ riêng; validate dữ liệu và sự kiện |
| Ném exception không nhất quán hoặc nuốt exception | Client không biết chuyển trạng thái thất bại | Định nghĩa kết quả lỗi và giữ nguyên state khi lệnh bị từ chối |
| Quên các đường đi terminal/hoàn tiền/lỗi | Quy trình kẹt hoặc rẽ nhánh sai | Vẽ sơ đồ và review toàn bộ ma trận trạng thái |
| Dùng State Pattern để thay cho xác thực/phân quyền | Người dùng vẫn có thể gọi API trái phép | Kiểm tra authorization tại server theo user + resource + operation |

**Đừng nhầm thay đổi trạng thái với thay đổi loại đối tượng.** Một **Order** vẫn là cùng một đơn hàng, có cùng định danh, nhưng phản hồi khác nhau theo giai đoạn xử lý. Đây không phải việc xóa Order cũ rồi tạo một subtype Order mới mỗi khi thanh toán hoặc giao hàng.

## 11. Khi nào nên áp dụng và khi nào nên dừng ở cách đơn giản?

**State Pattern đáng cân nhắc khi** hành vi thực sự thay đổi theo trạng thái ở nhiều phương thức, logic transition ngày càng rắc rối, các nhóm nghiệp vụ bổ sung trạng thái mới, hoặc trạng thái có các quy tắc riêng đủ lớn để đóng gói độc lập.

**Giữ enum/switch khi** chỉ có 2–3 trạng thái, vài quy tắc dễ đọc, phần lớn hành vi không khác nhau và không có áp lực thay đổi. Tạo bốn lớp chỉ để thay cho một switch ngắn chưa chắc làm code tốt hơn.

Quy trình chọn thiết kế thực dụng:

1. Liệt kê trạng thái và sự kiện; vẽ ma trận chuyển tiếp.
2. Viết implementation đơn giản nhất vẫn đúng các bất biến.
3. Khi nhiều hành vi bắt đầu phụ thuộc vào cùng state và nhánh lặp lại, nhóm logic vào State.
4. Đặt test cho mọi chuyển tiếp quan trọng và trường hợp không hợp lệ.
5. Xác định ranh giới transaction, persistence, quyền thao tác và tích hợp ngoài độc lập với mẫu thiết kế.
6. Đo độ dễ đọc và chi phí sửa đổi của code hiện có; bỏ abstraction không giúp giải quyết vấn đề.

Số lượng state **không phải** tiêu chí duy nhất. Hai state nhưng mỗi state có logic phức tạp có thể cần State Pattern; nhiều state với bảng transition thuần dữ liệu có thể phù hợp hơn với một FSM engine hoặc bảng cấu hình.

## 12. Bài tập: vòng đời phiếu hỗ trợ khách hàng

Một hệ thống hỗ trợ có các trạng thái: **NEW**, **ASSIGNED**, **RESOLVED**, **CLOSED**. Nghiệp vụ yêu cầu:

- Từ **NEW** được **assign(agentId)** sang **ASSIGNED** hoặc **close()** khi phiếu tạo nhầm.
- Từ **ASSIGNED** được **resolve(solution)** sang **RESOLVED**.
- Từ **RESOLVED** được **reopen()** về **ASSIGNED**, hoặc **close()** sang **CLOSED**.
- **CLOSED** không cho thao tác thêm trong mô hình này.

Hãy tự làm:

1. Vẽ **Mermaid stateDiagram-v2** và bảng transition đầy đủ (cả trường hợp bị từ chối).
2. Viết **Ticket** (Context), **TicketState** và các concrete state bằng Java. Giữ **ticketId**, **agentId**, **solution** là dữ liệu nghiệp vụ của Ticket; đừng lưu dữ liệu theo phiếu vào một state singleton dùng chung.
3. Thiết kế **assign**, **resolve**, **reopen**, **close** sao cho client không thể gọi public setter để bỏ qua transition.
4. Viết test đường đi **NEW → ASSIGNED → RESOLVED → CLOSED**, đường **RESOLVED → ASSIGNED** và các lỗi như resolve trước assign, reopen khi CLOSED.
5. Trả lời: nếu người dùng A và B cùng xử lý một phiếu, bạn sẽ bảo vệ transition bằng cách nào khi có database?

**Tiêu chí hoàn thành:** mỗi event chỉ được chấp nhận ở trạng thái phù hợp, các lệnh bị từ chối không làm thay đổi trạng thái, code thể hiện rõ trách nhiệm từng state, và mọi phụ thuộc vào database/quyền người dùng được xử lý ở ranh giới thích hợp.

**Ghi nhớ:** State Pattern tổ chức hành vi biến thiên theo **trạng thái hiện tại của cùng một đối tượng**. Khi dùng đúng, các quy tắc chuyển trạng thái dễ tìm, dễ kiểm thử và tránh những khối điều kiện lan rộng. Giá trị của nó đến từ yêu cầu nghiệp vụ cụ thể; việc kiểm soát persistence, giao dịch và đồng thời vẫn là trách nhiệm thiết kế hệ thống.