# Đối tượng, trạng thái, hành vi và trách nhiệm trong OOP

Khi học lập trình hướng đối tượng (Object-Oriented Programming – OOP), ta thường nghe: “Một đối tượng có trạng thái và hành vi”. Câu nói đúng nhưng chưa đủ để thiết kế phần mềm. Cần hiểu thêm **đối tượng chịu trách nhiệm về điều gì**, vì chính trách nhiệm quyết định dữ liệu nào thuộc về nó và hành vi nào nên đặt bên trong nó.

Hãy hình dung một đơn hàng đang được tạo: nó có mã đơn, danh sách sản phẩm, trạng thái nháp; người mua có thể thêm sản phẩm rồi xác nhận. Đơn hàng phải tự bảo vệ quy tắc “đã xác nhận thì không được tùy ý sửa danh sách sản phẩm”. Đó là một ví dụ về sự gắn kết giữa **đối tượng → trạng thái → hành vi → trách nhiệm**.

## 1. Bốn khái niệm liên hệ với nhau như thế nào?

| Khái niệm | Câu hỏi cần trả lời | Ví dụ với đơn hàng |
| --- | --- | --- |
| **Đối tượng (object)** | Ai/điều gì đang tham gia vào hệ thống? | Một đơn hàng cụ thể, có mã `orderId` |
| **Trạng thái (state)** | Đối tượng hiện có dữ liệu và đang ở tình huống nào? | Các dòng sản phẩm; `DRAFT`, `CONFIRMED` hoặc `CANCELLED` |
| **Hành vi (behavior)** | Đối tượng có thể thực hiện thao tác có ý nghĩa gì? | `addLine()`, `confirm()`, `cancel()`, `total()` |
| **Trách nhiệm (responsibility)** | Đối tượng phải biết, quyết định và bảo đảm điều gì? | Giữ danh sách sản phẩm hợp lệ và kiểm soát chuyển trạng thái đơn hàng |

Bốn phần không tồn tại độc lập. Nếu một đối tượng có thao tác `confirm()` thì thao tác ấy phải đọc trạng thái hiện tại, kiểm tra điều kiện và cập nhật trạng thái theo trách nhiệm của chính đối tượng.

Ví dụ, việc xác nhận đơn hàng không nên chỉ là gán `status = CONFIRMED`. Nó phải trả lời: *Đơn đã bị hủy chưa? Có ít nhất một sản phẩm chưa? Có cho xác nhận lại không?* Nếu quy tắc nằm rải rác ở nhiều nơi, phần mềm dễ tạo ra đơn hàng ở trạng thái sai.

## 2. Đối tượng là gì? Phân biệt đối tượng và lớp

**Đối tượng** là một thực thể trong chương trình có dữ liệu và cách xử lý liên quan đến dữ liệu đó. Nó có thể biểu diễn một thứ ngoài đời thực (đơn hàng, khách hàng), một khái niệm nghiệp vụ (giỏ hàng, hạn mức tín dụng), hoặc một thành phần kỹ thuật (bộ đệm, bộ đọc tệp). Không phải mọi đối tượng đều phải tương ứng với một vật thể hữu hình.

**Lớp (class)** thường mô tả cấu trúc và hành vi chung; **đối tượng (instance)** là một thể hiện cụ thể được tạo ra từ lớp.

~~~java
Order firstOrder = new Order(UUID.randomUUID());
Order secondOrder = new Order(UUID.randomUUID());

// Cùng kiểu Order nhưng là hai đối tượng riêng.
// Mỗi đối tượng có id, danh sách hàng và trạng thái của riêng nó.
~~~

Hai đơn hàng có thể cùng ở trạng thái `DRAFT` nhưng vẫn là **hai đối tượng khác nhau**. Ngược lại, một đơn hàng chuyển từ `DRAFT` sang `CONFIRMED` vẫn là *cùng đơn hàng ấy*; chỉ có trạng thái của nó thay đổi.

Cần phân biệt hai góc nhìn về danh tính:

- **Danh tính trong bộ nhớ Java:** `firstOrder == secondOrder` so sánh xem hai biến có trỏ đến cùng một object hay không.
- **Danh tính nghiệp vụ:** `orderId` giúp nhận diện một đơn hàng xuyên qua các lần lưu, tải từ database hoặc truyền qua API. Hai instance Java khác nhau có thể biểu diễn cùng một `orderId`. Việc so sánh chúng bằng `equals()` hay bằng ID phụ thuộc thiết kế cụ thể, không tự động suy ra từ tên lớp.

Điểm cốt lõi: **danh tính trả lời “đây là ai/cái gì?”, trạng thái trả lời “hiện tại nó ra sao?”**.

## 3. Trạng thái: những gì đối tượng đang nắm giữ

Trạng thái là tập hợp giá trị liên quan đến một đối tượng tại một thời điểm. Với đơn hàng, ta có:

- **Không đổi theo vòng đời nghiệp vụ:** mã đơn hàng `id`.
- **Có thể đổi qua hành vi hợp lệ:** các dòng sản phẩm khi đơn còn ở trạng thái nháp; `status` sau khi xác nhận hoặc hủy.
- **Có thể tính từ trạng thái khác:** `total()` được tính từ số lượng và đơn giá của các dòng sản phẩm. Không nhất thiết phải lưu thêm biến `total` rồi lo đồng bộ mỗi khi thêm hàng.

Ví dụ ba thời điểm của cùng một đơn hàng:

| Thời điểm | Danh sách hàng | Trạng thái | Tổng tiền |
| --- | --- | --- | --- |
| Mới tạo | Rỗng | `DRAFT` | 0 |
| Thêm 2 cuốn sách × 125.000 | 1 dòng hàng, số lượng 2 | `DRAFT` | 250.000 |
| Xác nhận thành công | Giữ nguyên | `CONFIRMED` | 250.000 |

Một trạng thái **hợp lệ** phải tuân theo các quy tắc nghiệp vụ (invariant). Trong ví dụ này:

1. Số lượng mỗi dòng hàng phải lớn hơn 0; đơn giá không âm.
2. Đơn đã xác nhận hoặc đã hủy không được thêm dòng hàng bằng `addLine()`.
3. Một đơn chỉ được `confirm()` khi đang `DRAFT` và có ít nhất một dòng hàng.
4. ID không tự thay đổi chỉ vì đơn chuyển trạng thái.

Không phải tất cả trạng thái đều phải có thể thay đổi. Một đối tượng bất biến (immutable object) vẫn có trạng thái, chỉ là trạng thái được cố định sau khi tạo. Và trường `private` không tự bảo đảm dữ liệu hợp lệ: vẫn cần kiểm soát những phương thức có thể thay đổi dữ liệu.

## 4. Hành vi: việc đối tượng biết làm

**Hành vi** là hoạt động mà đối tượng cung cấp cho phần còn lại của chương trình. Trong Java, hành vi thường được thể hiện bằng method. Một hành vi có thể:

- **Thay đổi trạng thái:** `addLine()`, `confirm()`, `cancel()`.
- **Trả về thông tin mà không thay đổi trạng thái:** `total()`, `status()`.
- **Từ chối thao tác không hợp lệ:** `confirm()` khi đơn rỗng sẽ báo lỗi và giữ nguyên `DRAFT`.

Tên phương thức nên diễn đạt ý định của miền bài toán. So sánh:

~~~java
// Khó kiểm soát: mã gọi bên ngoài tự quyết định trạng thái.
order.setStatus(OrderStatus.CONFIRMED);

// Thể hiện ý nghĩa nghiệp vụ: Order tự kiểm tra điều kiện.
order.confirm();
~~~

`confirm()` tốt hơn trong ví dụ này vì người gọi yêu cầu **“hãy xác nhận đơn”**, còn **đối tượng quyết định liệu yêu cầu có hợp lệ hay không**. Không nên hiểu rằng mọi setter đều xấu: các đối tượng truyền dữ liệu (DTO), cấu hình hoặc bean đơn giản có mục đích riêng. Điều cần tránh là bỏ qua quy tắc quan trọng đối với một đối tượng có vòng đời nghiệp vụ.

Hành vi phải có **đầu vào, điều kiện trước, kết quả và điều kiện sau** rõ ràng. Nếu thao tác thất bại, đừng để dữ liệu ở tình trạng thay đổi dở dang ngoài ý muốn.

## 5. Trách nhiệm: đối tượng nên giữ quy tắc nào?

Trách nhiệm là những điều một đối tượng cần biết hoặc bảo đảm để thực hiện đúng vai trò. Đây là nền tảng để quyết định **đặt dữ liệu và phương thức ở đâu**.

| Thành phần | Trách nhiệm phù hợp | Không nên ôm luôn |
| --- | --- | --- |
| **`Order`** | Quản lý dòng hàng, tính tổng, kiểm tra chuyển trạng thái đơn hàng | Gửi HTTP request tới cổng thanh toán, xây SQL, gửi email |
| **`PaymentService`** | Điều phối quy trình thanh toán, gọi hệ thống thanh toán và xử lý kết quả | Tự sửa trực tiếp danh sách hàng bên trong `Order` |
| **`OrderRepository`** | Lưu và tải đơn hàng từ nơi lưu trữ | Quyết định đơn rỗng có được xác nhận hay không |
| **`NotificationService`** | Gửi thông báo liên quan đến đơn hàng | Tự thay đổi `Order.status` |

Cách phân chia này không tuyệt đối cho mọi hệ thống. Điều quan trọng là quy tắc **“đơn hàng có được xác nhận không?”** có một nơi chịu trách nhiệm rõ ràng, thay vì bị lặp ở controller, service và repository với những điều kiện khác nhau.

**Trách nhiệm khác hành vi:** “Bảo đảm đơn hàng chuyển trạng thái hợp lệ” là một *trách nhiệm*; `confirm()` và `cancel()` là các *hành vi* thực hiện trách nhiệm đó. Một đối tượng có thể có nhiều method để phục vụ cùng một trách nhiệm.

Trách nhiệm tốt thường có **tính gắn kết (cohesion)**: dữ liệu và hành vi cùng phục vụ một mục đích. Nếu lớp `Order` vừa quản lý đơn, vừa xác thực JWT, vừa mở kết nối database, vừa gửi email, các lý do khiến lớp phải thay đổi không còn cùng một nhóm.

## 6. Ví dụ Java hoàn chỉnh: một Order bảo vệ trạng thái của nó

Ví dụ sau dùng Java 17 trở lên (có `record`), có thể lưu trong `Main.java` để chạy. Nó minh họa quy tắc trong bộ nhớ, chưa bàn đến việc lưu database hay xử lý nhiều yêu cầu đồng thời.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

enum OrderStatus {
    DRAFT, CONFIRMED, CANCELLED
}

// Một dòng hàng là value object: chứa dữ liệu hợp lệ và bất biến.
record OrderLine(String sku, int quantity, BigDecimal unitPrice) {
    OrderLine {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (sku.isBlank() || quantity <= 0 || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid order line");
        }
    }

    BigDecimal subtotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}

final class Order {
    private final UUID id;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;

    Order(UUID id) {
        this.id = Objects.requireNonNull(id, "id");
    }

    UUID id() {
        return id;
    }

    OrderStatus status() {
        return status;
    }

    List<OrderLine> lines() {
        return List.copyOf(lines); // Không lộ List mutable bên trong.
    }

    BigDecimal total() {
        return lines.stream()
                .map(OrderLine::subtotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    void addLine(String sku, int quantity, BigDecimal unitPrice) {
        requireDraft();
        lines.add(new OrderLine(sku, quantity, unitPrice));
    }

    void confirm() {
        requireDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException("Empty order cannot be confirmed");
        }
        status = OrderStatus.CONFIRMED;
    }

    void cancel() {
        requireDraft();
        status = OrderStatus.CANCELLED;
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                    "Order must be DRAFT, actual: " + status);
        }
    }
}

public class Main {
    public static void main(String[] args) {
        Order order = new Order(UUID.randomUUID());

        System.out.println(order.status()); // DRAFT
        System.out.println(order.total());  // 0

        order.addLine("BOOK-01", 2, new BigDecimal("125000"));
        System.out.println(order.total());  // 250000

        order.confirm();
        System.out.println(order.status()); // CONFIRMED

        try {
            order.addLine("PEN-01", 1, new BigDecimal("5000"));
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage()); // Order must be DRAFT...
        }

        System.out.println(order.total()); // Vẫn 250000

        // Nhánh thất bại độc lập, không dùng lại đơn đã xác nhận.
        Order emptyOrder = new Order(UUID.randomUUID());
        try {
            emptyOrder.confirm();
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage()); // Empty order...
        }
        System.out.println(emptyOrder.status()); // Vẫn DRAFT

        Order cancelledOrder = new Order(UUID.randomUUID());
        cancelledOrder.cancel();
        System.out.println(cancelledOrder.status()); // CANCELLED
    }
}
~~~

**Đọc ví dụ theo bốn góc nhìn:**

- **Đối tượng:** `order`, `emptyOrder` và `cancelledOrder` là ba instance có ID riêng, dù chúng cùng được tạo từ lớp `Order`.
- **Trạng thái:** `id`, `lines` và `status` tạo thành dữ liệu mà `Order` quản lý. `total()` suy ra kết quả từ `lines`.
- **Hành vi:** `addLine()` thay đổi danh sách; `confirm()` và `cancel()` chuyển trạng thái; `total()` chỉ tính toán.
- **Trách nhiệm:** `Order` bảo đảm mọi thao tác công khai ở ví dụ đều giữ trạng thái theo quy tắc. Nó che danh sách mutable bằng `List.copyOf(...)` và không cung cấp `setStatus()` tự do.

Chạy ví dụ:

~~~bash
javac Main.java
java Main
~~~

**Lưu ý về ví dụ:** Chúng ta chủ động định nghĩa chỉ đơn `DRAFT` được hủy. Dự án thực tế có thể cho hủy đơn đã xác nhận, hoàn tiền hoặc có thêm `PAID`/`SHIPPED`; khi đó phải thay đổi quy tắc và kiểm thử đúng theo nghiệp vụ. `BigDecimal` được dùng để tránh sai số số thực nhị phân trong phép tính thập phân, nhưng hệ thống tiền tệ thực tế còn cần quy định đơn vị tiền, làm tròn và thuế/phí.

## 7. Vòng đời đối tượng: trạng thái thay đổi qua hành vi

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT: tạo Order
    DRAFT --> DRAFT: addLine(...) hợp lệ
    DRAFT --> CONFIRMED: confirm() và có hàng
    DRAFT --> CANCELLED: cancel()
    CONFIRMED --> [*]
    CANCELLED --> [*]
~~~

Sơ đồ mô tả **các chuyển trạng thái thành công** trong ví dụ. Những yêu cầu không hợp lệ (xác nhận đơn rỗng, thêm hàng sau xác nhận, hủy lần nữa) bị từ chối; trạng thái được giữ nguyên.

Theo dõi chính xác một luồng:

| Bước | Lệnh | Trước | Sau | Kết quả quan sát được |
| --- | --- | --- | --- | --- |
| 1 | `new Order(id)` | Chưa tồn tại | `DRAFT`, rỗng | Có một đơn mới |
| 2 | `addLine("BOOK-01", 2, 125000)` | `DRAFT`, rỗng | `DRAFT`, 1 dòng | `total() = 250000` |
| 3 | `confirm()` | `DRAFT`, 1 dòng | `CONFIRMED`, 1 dòng | Xác nhận thành công |
| 4 | `addLine("PEN-01", 1, 5000)` | `CONFIRMED`, 1 dòng | **Giữ nguyên** | Ném `IllegalStateException`; tổng vẫn 250000 |

Để thử lỗi “xác nhận đơn rỗng”, dùng **đơn thứ hai**: `new Order(id2)` → `confirm()` thất bại → trạng thái vẫn `DRAFT`. Hai nhánh kiểm thử riêng giúp không nhầm kết quả của đơn trước với đơn sau.

## 8. Khi nhiều đối tượng phối hợp thì sao?

Một đối tượng có trách nhiệm riêng, nhưng hệ thống thường phải phối hợp nhiều đối tượng.

Ví dụ luồng xác nhận đơn trong ứng dụng Spring Boot:

~~~mermaid
sequenceDiagram
    participant C as OrderController
    participant S as OrderService
    participant R as OrderRepository
    participant O as Order
    C->>S: confirmOrder(orderId)
    S->>R: findById(orderId)
    R-->>S: Order
    S->>O: confirm()
    O-->>S: Thành công hoặc exception
    S->>R: save(Order) khi thành công
    S-->>C: Kết quả
~~~

Trong cách tổ chức này, **OrderController** nhận request, **OrderService** điều phối use case, **OrderRepository** lo truy xuất/lưu trữ, còn **Order** kiểm tra điều kiện và chuyển trạng thái. Phân chia ấy cho phép sửa quy tắc “đơn rỗng có được xác nhận không?” tại `Order.confirm()`, đồng thời cho phép thay đổi cách lưu trữ mà không phải đưa SQL vào `Order`.

Đây là **một thiết kế minh họa**, không phải yêu cầu mọi ứng dụng OOP đều phải có các lớp tên `Service`/`Repository`. Ở ứng dụng đơn giản, số lượng lớp có thể ít hơn. Ở hệ thống có thanh toán, kho hàng và giao dịch, trách nhiệm phối hợp sẽ phức tạp hơn.

Lưu ý: kiểm tra trong `Order` ở bộ nhớ **chưa giải quyết** các tình huống hai request đồng thời, cập nhật thất bại hoặc rollback database. Những vấn đề ấy cần cơ chế transaction, locking/versioning và xử lý lỗi thích hợp trong tầng lưu trữ/quy trình nghiệp vụ.

## 9. Lỗi thiết kế thường gặp

| Cách nghĩ dễ sai | Hệ quả | Cách suy nghĩ tốt hơn |
| --- | --- | --- |
| “Đối tượng chỉ là một nhóm field.” | Lớp chỉ chứa getter/setter; quy tắc rải ngoài lớp. | Hỏi đối tượng phải bảo vệ điều kiện và thực hiện hành vi gì. |
| “Mỗi method đều là một trách nhiệm khác nhau.” | Phân chia lớp tùy tiện, khó theo dõi. | Nhiều method có thể phục vụ cùng một trách nhiệm nhất quán. |
| “`private` nghĩa là trạng thái luôn an toàn.” | Setter vô điều kiện vẫn phá được quy tắc; collection mutable có thể bị lộ. | Kiểm tra quy tắc ở đường thay đổi trạng thái và giới hạn quyền sửa. |
| “Trạng thái là status enum.” | Bỏ qua danh sách hàng, số lượng, giá trị khác trong object. | State là toàn bộ dữ liệu liên quan tại một thời điểm; status chỉ là một phần. |
| “Cứ biến thứ gì thành class là OOP tốt.” | Tăng lớp vô ích; trách nhiệm không rõ. | Tạo đối tượng khi nó có vai trò, dữ liệu hoặc hành vi cần quản lý. |
| “Đối tượng tự làm được mọi thứ.” | Một lớp ôm API, database, thanh toán, email và nghiệp vụ. | Chọn ranh giới trách nhiệm, cộng tác thông qua method phù hợp. |

Một dấu hiệu nên xem lại: ở nhiều nơi xuất hiện mã dạng `if (order.getStatus() == DRAFT) { ... }` trước khi thay đổi đơn. Có thể quy tắc thuộc về `Order` và nên được đưa vào hành vi của nó. Tuy nhiên, những quy tắc liên quan **nhiều đối tượng, nhiều nguồn dữ liệu** vẫn có thể cần service hoặc thành phần điều phối.

## 10. Tự kiểm tra mức hiểu

**Tình huống 1.** Hai đơn đều có `status = DRAFT` và `total = 0`. Chúng có phải cùng một đối tượng? **Không nhất thiết.** Cần xét danh tính; dữ liệu giống nhau không có nghĩa là cùng instance hoặc cùng đơn nghiệp vụ.

**Tình huống 2.** Một đơn được xác nhận, sau đó `status` đổi thành `CONFIRMED`. Đây có phải một đối tượng mới? **Không.** Danh tính vẫn giữ nguyên, trạng thái thay đổi.

**Tình huống 3.** Có nên cho controller gọi `order.setStatus(CONFIRMED)`? **Trong ví dụ này không nên.** Phương thức `confirm()` giúp Order tự kiểm tra điều kiện trước khi chuyển trạng thái.

**Tình huống 4.** `total()` không sửa dữ liệu. Nó có phải hành vi không? **Có.** Hành vi có thể tính toán/trả lời thông tin mà không thay đổi trạng thái.

**Tình huống 5.** Có nên đặt code gửi email trong `Order.confirm()`? **Thông thường không.** Gửi email là trách nhiệm tích hợp/thông báo, có thể do thành phần khác xử lý sau khi nghiệp vụ xác nhận thành công.

Khi tự thiết kế một lớp OOP, hãy hỏi theo thứ tự:

1. **Đối tượng nào** tồn tại trong bài toán? Điều gì nhận diện một đối tượng cụ thể?
2. **Trạng thái nào** đối tượng phải sở hữu? Phần nào được thay đổi, phần nào chỉ tính ra?
3. **Hành vi nào** có ý nghĩa với người dùng hoặc nghiệp vụ? Mỗi hành vi có điều kiện trước/sau gì?
4. **Quy tắc nào** đối tượng phải luôn bảo vệ? Điều gì xảy ra khi thao tác thất bại?
5. **Trách nhiệm nào** thuộc về đối tượng đó, trách nhiệm nào nên giao cho đối tượng khác?

Nếu trả lời được năm câu hỏi này bằng một ví dụ cụ thể, bạn đã nắm được cách tư duy từ dữ liệu thụ động sang **đối tượng có hành vi và trách nhiệm rõ ràng**, thay vì chỉ nhớ định nghĩa OOP.