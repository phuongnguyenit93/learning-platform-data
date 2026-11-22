# Biểu diễn command bằng record trong thiết kế domain model (Java 21+)

## 1. Command là gì và vì sao dùng record?

Trong thiết kế domain model, **command** là thông điệp diễn đạt một *ý định/yêu cầu thực hiện hành động*: tạo đơn hàng, thêm sản phẩm, xác nhận đơn hay hủy đơn. Command có thể được chấp nhận hoặc bị từ chối sau khi kiểm tra quy tắc nghiệp vụ.

Ví dụ:

- `CreateOrder(orderId, customerId)`: yêu cầu tạo một đơn hàng mới.
- `AddItem(orderId, sku, quantity)`: yêu cầu thêm số lượng sản phẩm vào đơn.
- `SubmitOrder(orderId)`: yêu cầu xác nhận/gửi đơn.
- `CancelOrder(orderId, reason)`: yêu cầu hủy đơn với lý do.

**Java record** là lựa chọn phù hợp cho một command mang dữ liệu vì record tập trung vào **các thành phần dữ liệu**, tự cung cấp constructor, accessor, `equals()`, `hashCode()` và `toString()` theo các component. Record mặc định không cho kế thừa class khác và các field lưu component là `final`; nhờ vậy dễ mô tả một thông điệp có dữ liệu ổn định.

Ví dụ tối giản:

~~~java
record CreateOrder(String orderId, String customerId) {}

CreateOrder command = new CreateOrder("ORD-1", "C-7");
System.out.println(command.orderId());   // ORD-1
System.out.println(command.customerId()); // C-7
~~~

Không có `setOrderId()` hay `setCustomerId()`. Command thường nên mang dữ liệu bất biến sau khi tạo, để handler có thể xử lý đúng một yêu cầu rõ ràng.

**Phân biệt ba khái niệm:**

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Command** | Yêu cầu làm điều gì đó; có thể bị từ chối | `SubmitOrder("ORD-1")` |
| **Event** | Sự kiện đã xảy ra, diễn đạt sự thật quá khứ | `OrderSubmitted("ORD-1")` |
| **Domain state / entity** | Trạng thái nghiệp vụ hiện tại cần được bảo vệ bằng quy tắc | Đơn hàng `ORD-1` đang `DRAFT` |

Record có thể dùng cho nhiều loại thông điệp và value object, nhưng **command không đồng nghĩa với event**. Chỉ vì tạo được một record `SubmitOrder` không có nghĩa đơn hàng đã gửi thành công.

## 2. Từ record rời rạc đến mô hình command có kiểu chung

Một ứng dụng có nhiều loại command thường cần một kiểu chung để router/handler nhận vào. Java hỗ trợ `sealed interface`, giúp công bố **tập command được phép**:

~~~java
sealed interface OrderCommand
        permits CreateOrder, AddItem, SubmitOrder, CancelOrder {}

record CreateOrder(String orderId, String customerId)
        implements OrderCommand {}

record AddItem(String orderId, String sku, int quantity)
        implements OrderCommand {}

record SubmitOrder(String orderId)
        implements OrderCommand {}

record CancelOrder(String orderId, String reason)
        implements OrderCommand {}
~~~

Ví dụ trên minh họa cấu trúc và nên được đặt trong một file/class thích hợp khi dùng thực tế. Các record thuộc tập `permits` đều là những kiểu con hợp lệ của `OrderCommand`, và record vốn là `final` nên không thể có lớp con tự ý kế thừa các record này.

**Ưu điểm của sealed hierarchy:**

1. Mã nguồn biểu diễn rõ các loại command hợp lệ mà module hỗ trợ.
2. Compiler có thể kiểm tra tính **exhaustive** khi dùng pattern matching trong `switch` trên `OrderCommand`.
3. Khi bổ sung loại command mới, chỗ dispatch không xử lý đầy đủ có thể phát sinh lỗi biên dịch, giúp phát hiện thiếu logic khi thay đổi domain model.
4. Mỗi record có đúng dữ liệu cần cho một ý định; tránh một “command tổng” chứa nhiều field nullable tùy thuộc một chuỗi `type`.

**Giới hạn:** sealed hierarchy chỉ khép kín trong phạm vi kiểu Java được biên dịch, không tự xác thực JSON, quyền của người gửi, tính hợp lệ nghiệp vụ hoặc command đến từ bên ngoài. Nếu ứng dụng cần plugin mở rộng động bởi bên thứ ba, sealed có thể không phù hợp với yêu cầu mở rộng.

## 3. Thiết kế dữ liệu command: mang ý định, không ôm hành vi xử lý

Một command nên trả lời câu hỏi **“ai yêu cầu làm gì, đối tượng nào, với dữ liệu nào?”** chứ không nên tự quyết định cách đọc/ghi database. Ví dụ:

~~~java
record AddItem(String orderId, String sku, int quantity) {}
~~~

Component có vai trò rõ ràng:

- `orderId`: định danh aggregate/entity được tác động.
- `sku`: định danh sản phẩm cần thêm.
- `quantity`: số lượng được yêu cầu.
- **Không có** field `EntityManager`, `Connection`, `Repository` hay `HttpClient` vì chúng là dependency hành vi, không phải dữ liệu của ý định nghiệp vụ.

Với command, tên thường dùng **động từ mệnh lệnh**: `CreateOrder`, `AddItem`, `CancelOrder`. Tránh dùng một record tên `Order` để vừa làm entity có vòng đời, vừa làm tất cả yêu cầu thay đổi entity đó; hai vai trò có invariants và vòng đời khác nhau.

Một command cũng có thể chứa `actorId`, `requestId`, thời điểm hoặc metadata truy vết **nếu** chúng thuộc hợp đồng nghiệp vụ. Nhưng không nên tự động tin giá trị `actorId` do client gửi để cấp quyền: xác thực và phân quyền vẫn phải dựa trên nguồn danh tính đáng tin trong application layer.

## 4. Validate command ngay trong compact constructor

Record không ngăn tạo command sai chỉ vì field là `final`. Ta cần bảo vệ những **điều kiện đúng với mọi instance**, ví dụ ID không null/rỗng và số lượng phải dương.

Java record hỗ trợ **compact canonical constructor**:

~~~java
record AddItem(String orderId, String sku, int quantity) {
    public AddItem {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId không được trống");
        }
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku không được trống");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải > 0");
        }
        orderId = orderId.strip();
        sku = sku.strip();
    }
}
~~~

Trong compact constructor, Java tự động gán các **tham số constructor đã được kiểm tra/chuẩn hóa** vào các field component sau phần thân constructor. Không cần `this.orderId = orderId;` hoặc tự gán field component trong dạng compact constructor.

Phân biệt hai lớp kiểm tra:

- **Kiểm tra dữ liệu command**: thiếu ID, chuỗi rỗng, số lượng không dương; có thể kiểm tra ngay khi khởi tạo record.
- **Kiểm tra trạng thái nghiệp vụ**: đơn có tồn tại không, đã được xác nhận chưa, người yêu cầu có quyền hay không, kho còn hàng không; cần context, entity/repository và thường do application/domain service xử lý.

Không nên buộc command constructor kết nối database để quyết định đơn có đang `DRAFT`. Việc đó làm command khó tạo, khó test và phụ thuộc hạ tầng.

## 5. Record là bất biến nông, không bảo đảm bất biến sâu

Các field component của record là `final` nhưng **đối tượng mà field tham chiếu đến** vẫn có thể thay đổi nếu là đối tượng mutable. Ví dụ một record chứa `List` chưa chắc bất biến an toàn:

~~~java
import java.util.ArrayList;
import java.util.List;

record UnsafeBatch(List<String> items) {}

List<String> list = new ArrayList<>();
list.add("A");
UnsafeBatch batch = new UnsafeBatch(list);
list.add("B");

// batch.items() nay cũng quan sát được phần tử "B".
~~~

Dữ liệu bên ngoài đã thay đổi nội dung của record mà không tạo instance mới. Có thể dùng **defensive copy**:

~~~java
record Batch(List<String> items) {
    public Batch {
        items = List.copyOf(items);
    }
}

List<String> source = new ArrayList<>();
source.add("A");
Batch batch = new Batch(source);
source.add("B");

System.out.println(batch.items()); // [A]
~~~

`List.copyOf` tạo snapshot unmodifiable của cấu trúc danh sách và từ chối null list hoặc null element. Nhưng đây chỉ là **bản sao nông**: nếu element là đối tượng mutable, trạng thái element vẫn có thể đổi. Với command chứa danh sách các record/value object thật sự bất biến, mô hình an toàn hơn.

Các trường hợp cần chú ý gồm `List`, `Map`, `Set`, array, `Date` (mutable) và đối tượng domain mutable. Với array, cần sao chép cả khi đưa vào **và** khi trả ra nếu muốn tránh lộ dữ liệu nội bộ. Không mặc định `record` đồng nghĩa “deeply immutable”.

## 6. Dispatch command bằng pattern matching trong switch

Từ Java 21, có thể dùng **record patterns** trong `switch` để tách trực tiếp component:

~~~java
static String describe(OrderCommand command) {
    return switch (command) {
        case CreateOrder(var id, var customerId) ->
            "Tạo đơn " + id + " cho " + customerId;

        case AddItem(var id, var sku, var quantity) ->
            "Thêm " + quantity + " " + sku + " vào " + id;

        case SubmitOrder(var id) ->
            "Gửi đơn " + id;

        case CancelOrder(var id, var reason) ->
            "Hủy đơn " + id + ": " + reason;
    };
}
~~~

Ở mỗi `case`:

1. Compiler xác định command có kiểu record phù hợp hay không.
2. Record pattern trích component theo **đúng thứ tự khai báo**.
3. Các pattern variable khai báo qua `var` được suy luận từ kiểu component, ví dụ `id` và `sku` là `String`, `quantity` là `int`.
4. Nhánh phù hợp tạo kết quả của `switch expression`.

Không cần cast thủ công như `(AddItem) command` rồi gọi từng accessor. Vì `OrderCommand` là sealed và switch xử lý toàn bộ subtype được permit, ví dụ trên không cần `default`. Khi thêm subtype mới vào hierarchy, compiler có thể báo chỗ switch chưa exhaustive — một lợi ích thiết kế đáng kể.

**Với null:** `switch (command)` trên reference selector không tự đưa null vào `default`; nên xác định chính sách rõ. Trong ví dụ handler hoàn chỉnh bên dưới, `Objects.requireNonNull(command)` từ chối null trước switch. Nếu muốn xử lý null thành một kết quả, thêm `case null -> ...`.

Các case trên là ví dụ dispatch thuần giá trị; một **handler thực tế** còn cần thực thi use case, kiểm tra state và lưu kết quả.

## 7. Đặt command bên cạnh state và handler: luồng xử lý

Mô hình đơn giản của một lần xử lý:

~~~text
Command record
     |
     v
Application handler
     |
     +--> kiểm tra dữ liệu cấu trúc (đã được constructor bảo vệ)
     +--> tải domain state / aggregate
     +--> áp dụng quy tắc nghiệp vụ
     +--> tạo state mới / ghi giao dịch
     +--> trả kết quả hoặc báo lỗi
~~~

Ví dụ với `AddItem("ORD-1", "SACH", 2)`:

- Command record chỉ đại diện yêu cầu “thêm hai sản phẩm mã SACH vào ORD-1”.
- Handler tìm đơn `ORD-1`.
- Domain rule chỉ cho phép thêm sản phẩm nếu đơn còn `DRAFT`.
- Nếu hợp lệ, tạo snapshot/trạng thái mới rồi lưu.
- Nếu đơn đã `SUBMITTED`, handler **từ chối**; command không “tự sửa” entity.

**Lưu ý kiến trúc:** command record không phải **event**. Chỉ sau khi thực thi thành công, hệ thống mới có cơ sở phát ra một sự kiện như `ItemAdded` hoặc `OrderSubmitted` (nếu ứng dụng cần event). Trong ví dụ chạy bên dưới, handler chỉ trả thông điệp và cập nhật map trong bộ nhớ, **không** xây dựng hệ thống event sourcing.

## 8. Chương trình end-to-end: record command + sealed interface + handler

Lưu toàn bộ mã vào **`CommandRecordDemo.java`** và chạy với Java 21+:

~~~java
import java.util.*;

public class CommandRecordDemo {
    sealed interface Command
            permits CreateOrder, AddItem, SubmitOrder, CancelOrder {}

    record CreateOrder(String orderId, String customerId)
            implements Command {
        public CreateOrder {
            orderId = requireText(orderId, "orderId");
            customerId = requireText(customerId, "customerId");
        }
    }

    record AddItem(String orderId, String sku, int quantity)
            implements Command {
        public AddItem {
            orderId = requireText(orderId, "orderId");
            sku = requireText(sku, "sku");
            if (quantity <= 0)
                throw new IllegalArgumentException("quantity phải > 0");
        }
    }

    record SubmitOrder(String orderId) implements Command {
        public SubmitOrder {
            orderId = requireText(orderId, "orderId");
        }
    }

    record CancelOrder(String orderId, String reason)
            implements Command {
        public CancelOrder {
            orderId = requireText(orderId, "orderId");
            reason = requireText(reason, "reason");
        }
    }

    static String requireText(String value, String name) {
        if (value == null || value.isBlank())
            throw new IllegalArgumentException(name + " không được trống");
        return value.strip();
    }

    enum Status { DRAFT, SUBMITTED, CANCELLED }
    record Line(String sku, int quantity) {}

    record Order(String id, String customerId,
                 List<Line> lines, Status status) {
        public Order {
            Objects.requireNonNull(id);
            Objects.requireNonNull(customerId);
            lines = List.copyOf(lines);
            Objects.requireNonNull(status);
        }
    }

    static final class Handler {
        private final Map<String, Order> orders = new LinkedHashMap<>();

        String handle(Command command) {
            Objects.requireNonNull(command, "command");

            return switch (command) {
                case CreateOrder(var id, var customerId) -> {
                    if (orders.containsKey(id))
                        yield "Đơn đã tồn tại: " + id;

                    orders.put(id, new Order(
                            id, customerId, List.of(), Status.DRAFT));
                    yield "Tạo đơn " + id;
                }

                case AddItem(var id, var sku, var quantity) -> {
                    Order order = requireOrder(id);
                    requireDraft(order);

                    List<Line> next = new ArrayList<>(order.lines());
                    next.add(new Line(sku, quantity));
                    orders.put(id, new Order(
                            order.id(), order.customerId(),
                            next, order.status()));

                    yield "Thêm " + quantity + " " + sku
                            + " vào " + id;
                }

                case SubmitOrder(var id) -> {
                    Order order = requireOrder(id);
                    requireDraft(order);
                    if (order.lines().isEmpty())
                        throw new IllegalStateException("Đơn trống");

                    orders.put(id, new Order(
                            order.id(), order.customerId(),
                            order.lines(), Status.SUBMITTED));
                    yield "Gửi đơn " + id;
                }

                case CancelOrder(var id, var reason) -> {
                    Order order = requireOrder(id);
                    requireDraft(order);

                    orders.put(id, new Order(
                            order.id(), order.customerId(),
                            order.lines(), Status.CANCELLED));
                    yield "Hủy đơn " + id + ": " + reason;
                }
            };
        }

        private Order requireOrder(String id) {
            Order order = orders.get(id);
            if (order == null)
                throw new IllegalStateException(
                        "Không tìm thấy đơn: " + id);
            return order;
        }

        private static void requireDraft(Order order) {
            if (order.status() != Status.DRAFT)
                throw new IllegalStateException(
                        "Đơn không ở DRAFT");
        }

        Order find(String id) {
            return requireOrder(id);
        }
    }

    public static void main(String[] args) {
        Handler handler = new Handler();

        System.out.println(handler.handle(
                new CreateOrder("  ORD-1 ", " C-7 ")));
        System.out.println(handler.handle(
                new AddItem("ORD-1", "SACH", 2)));
        System.out.println(handler.handle(
                new SubmitOrder("ORD-1")));

        System.out.println(handler.find("ORD-1").status());
        System.out.println(handler.find("ORD-1").lines().size());

        System.out.println(handler.handle(
                new CreateOrder("ORD-1", "C-7")));

        try {
            new AddItem("ORD-1", "BUT", 0);
        } catch (IllegalArgumentException e) {
            System.out.println("Lỗi đầu vào: " + e.getMessage());
        }

        try {
            handler.handle(
                    new AddItem("ORD-1", "BUT", 1));
        } catch (IllegalStateException e) {
            System.out.println("Lỗi nghiệp vụ: " + e.getMessage());
        }

        System.out.println(handler.handle(
                new CreateOrder("ORD-2", "C-8")));
        System.out.println(handler.handle(
                new CancelOrder("ORD-2", " Khách đổi ý ")));
        System.out.println(handler.find("ORD-2").status());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 21 CommandRecordDemo.java
java CommandRecordDemo
~~~

Đầu ra chính xác:

~~~text
Tạo đơn ORD-1
Thêm 2 SACH vào ORD-1
Gửi đơn ORD-1
SUBMITTED
1
Đơn đã tồn tại: ORD-1
Lỗi đầu vào: quantity phải > 0
Lỗi nghiệp vụ: Đơn không ở DRAFT
Tạo đơn ORD-2
Hủy đơn ORD-2: Khách đổi ý
CANCELLED
~~~

**Phân tích những điểm chính:**

- `CreateOrder("  ORD-1 ", " C-7 ")` được chuẩn hóa bằng `strip()` trong compact constructor, nên handler nhận `ORD-1` và `C-7`.
- `AddItem` kiểm tra `quantity > 0` ngay lúc tạo record, tránh việc một command sai cấu trúc đi sâu vào handler.
- Handler dùng `switch (command)` và record pattern để nhận đúng loại command, tách các component mà không cần cast.
- `Order` trong ví dụ là một **immutable state snapshot**; `List.copyOf` tạo danh sách unmodifiable từ các `Line` vốn có component `String` và `int`.
- Khi thêm sản phẩm, handler sao chép danh sách, thêm `Line` và tạo `Order` mới; không sửa record state đã tồn tại.
- Khi đơn đã `SUBMITTED`, `AddItem` vẫn là một command **hợp lệ về dữ liệu**, nhưng handler từ chối vì **quy tắc nghiệp vụ** “chỉ được thay đổi đơn DRAFT”.
- Khi gửi command tạo đơn trùng ID, handler trả thông điệp `Đơn đã tồn tại`. Đây chỉ là chính sách minh họa trong bộ nhớ, **không phải bảo đảm idempotency phân tán**.
- `CancelOrder` lưu trạng thái `CANCELLED` và trả thông điệp có lý do; ví dụ không ghi lý do vào lịch sử audit/event store.
- `Handler` dùng `LinkedHashMap` cục bộ, không có kết nối database, giao dịch hay an toàn đa luồng. Không dùng nguyên xi handler demo cho môi trường production.

## 9. Dùng `when` cho một nhánh command cần ưu tiên

Java 21 hỗ trợ guard `when` trong pattern switch. Có thể dùng để chuyên biệt hóa cách xử lý một command:

~~~java
static String category(Command command) {
    return switch (command) {
        case AddItem(var id, var sku, var qty) when qty >= 10 ->
                "Yêu cầu nhập số lượng lớn";
        case AddItem(var id, var sku, var qty) ->
                "Yêu cầu thêm sản phẩm";
        case CreateOrder(var id, var customerId) ->
                "Yêu cầu tạo đơn";
        case SubmitOrder(var id) ->
                "Yêu cầu gửi đơn";
        case CancelOrder(var id, var reason) ->
                "Yêu cầu hủy đơn";
    };
}
~~~

Đặt nhánh `AddItem ... when qty >= 10` **trước** nhánh `AddItem` chung; nhánh chung đặt trước có thể dominate nhánh có guard, dẫn tới lỗi biên dịch. Guard được đánh giá **sau khi** pattern khớp; `qty` đã có kiểu `int` và có thể sử dụng trong biểu thức guard.

Đoạn trên minh họa phân loại. Với quy tắc kiểm tra dữ liệu đầu vào, giữ validation trong constructor và quy tắc cần state trong handler/domain service. Không nên chuyển toàn bộ chính sách domain thành một switch chứa quá nhiều guard khó kiểm thử.

## 10. Một vài lựa chọn thiết kế và giới hạn cần biết

### 10.1. Khi nào record không phù hợp?

Record phù hợp cho **command message, DTO hoặc value object**. Một entity/aggregate có danh tính và vòng đời phức tạp đôi khi phù hợp với class thông thường hơn, đặc biệt khi cần thay đổi trạng thái dưới sự bảo vệ của các phương thức domain.

Không nên dùng record chỉ để tạo “object ngắn hơn” nếu thực thể cần quy tắc identity riêng, lazy loading, proxy của ORM hoặc trạng thái mutable được kiểm soát. `record` bình đẳng theo **giá trị component** (`equals()`), không tự thể hiện khái niệm identity của entity. Trong ví dụ, `Order` chỉ là immutable snapshot nhằm đơn giản hóa; production có thể thay bằng aggregate/entity đúng mô hình.

### 10.2. Kiểu command nhiều tham số

Khi command có quá nhiều tham số cùng kiểu `String`, lời gọi theo vị trí rất dễ nhầm:

~~~java
new CreateOrder("ORD-1", "C-7"); // orderId rồi customerId
~~~

Có thể dùng **value object**:

~~~java
record OrderId(String value) {
    public OrderId {
        if (value == null || value.isBlank())
            throw new IllegalArgumentException("OrderId rỗng");
        value = value.strip();
    }
}

record CustomerId(String value) {
    public CustomerId {
        if (value == null || value.isBlank())
            throw new IllegalArgumentException("CustomerId rỗng");
        value = value.strip();
    }
}

record CreateOrderTyped(OrderId orderId, CustomerId customerId) {}
~~~

Lúc đó compiler ngăn việc truyền nhầm `CustomerId` vào tham số `OrderId`. Quyết định có tách value object riêng hay không phụ thuộc vào độ phức tạp domain và tần suất dùng; không nên tạo nhiều kiểu bọc vô ích khi mô hình đơn giản.

### 10.3. Command record và dữ liệu từ JSON/API

Thông điệp ngoài hệ thống phải trải qua **parse + validation + authorization**, không chỉ được tạo thành record một cách cơ học:

~~~text
HTTP/Queue payload
    -> DTO/parser
    -> kiểm tra kiểu, trường bắt buộc, giới hạn dữ liệu
    -> tạo command record hợp lệ
    -> xác thực/ủy quyền dựa trên context tin cậy
    -> handler/domain
~~~

Nếu dùng thư viện JSON, khả năng ánh xạ record, constructor và sealed hierarchy tùy vào thư viện/phiên bản/cấu hình. Đừng khẳng định mọi serializer tự biết chọn đúng command subtype. Có thể cần trường phân biệt `kind` ở **API boundary**, nhưng vẫn nên chuyển nó thành hierarchy có kiểu chặt chẽ bên trong domain.

Không dùng dữ liệu client tự khai `actorId` làm chứng cứ được phép hủy đơn; quyền xử lý phải được xác minh từ session/token/context đã được xác thực.

### 10.4. Idempotency và xử lý command lặp

Một command có thể được gửi lại do client retry hoặc message broker cung cấp at-least-once delivery. Việc hai record command có cùng `equals()` **không** tự khiến side effect chỉ chạy một lần.

Nếu use case yêu cầu chống lặp, cần chính sách có chủ đích như:

- `requestId`/idempotency key hợp lệ, ổn định cho một yêu cầu logic;
- lưu trạng thái xử lý idempotency cùng giao dịch;
- unique constraint/optimistic locking hoặc xử lý trùng theo nghiệp vụ;
- định nghĩa lại kết quả trả về khi nhận yêu cầu lặp.

`CreateOrder` trong demo chỉ kiểm tra map trùng ID và trả chuỗi. Nó không giải quyết crash/retry, race condition hoặc exactly-once processing.

### 10.5. Concurrency, transaction và bất biến state

`Command` record bất biến **không khiến handler tự động thread-safe**. Hai luồng cùng đọc một đơn `DRAFT`, cùng tạo state mới rồi ghi vào map/database có thể gây lost update.

Trong production, cần lựa chọn thích hợp: transaction, khóa đồng bộ, version number và optimistic concurrency, sequence per aggregate, hoặc actor/message-queue ordering. Dùng immutable command là điểm khởi đầu tốt, không thay cho tính nguyên tử và nhất quán của trạng thái nghiệp vụ.

### 10.6. Evolution của schema

Thêm component mới vào record làm thay đổi canonical constructor, accessors, `equals()`/`hashCode()` và representation. Điều đó có thể ảnh hưởng code gọi, serialization và thông điệp đang nằm trong queue hoặc event log.

Với giao tiếp qua API/messaging, cân nhắc versioning, trường optional có default được validate ở boundary, adapter chuyển dữ liệu cũ sang command mới, và compatibility tests. Không coi việc thêm field vào record là thay đổi hoàn toàn vô hại.

## 11. Các lỗi dễ gặp

| Sai lầm | Vì sao có vấn đề | Cách làm phù hợp |
| --- | --- | --- |
| Command record chứa repository/database connection | Trộn ý định với hạ tầng, khó test | Record chỉ chứa dữ liệu; handler dùng dependency |
| Chỉ tin field `final` là bất biến sâu | List/array và element mutable vẫn có thể đổi | Defensive copy, value object immutable |
| Dùng entity record thay cho command record | Trộn định danh/vòng đời của entity với thông điệp yêu cầu | Tách command và state/aggregate |
| Để command constructor đọc database | Cần context ngoài để kiểm tra trạng thái | Constructor kiểm tra invariant dữ liệu, handler/domain kiểm tra state |
| Dùng switch có `default` cho mọi sealed command | Dễ che việc thêm command mới mà quên xử lý | Ưu tiên exhaustive switch không default khi phù hợp |
| Quên `null` của selector | Switch pattern trên reference thường không tự chấp nhận null | `requireNonNull` hoặc `case null` rõ ràng |
| Cho rằng command được tạo nghĩa là đã thực thi | Command chỉ là yêu cầu | Handler trả kết quả/exception sau khi kiểm tra domain |
| Xem `equals()` là chống duplicate request | Value equality khác dedup có giao dịch | Idempotency key + persistence policy |
| Command bất biến nên handler thread-safe | State/repository vẫn có thể bị race | Transaction và concurrency control |
| Gắn tên command bằng chuỗi và ép kiểu tay | Bỏ kiểm tra exhaustiveness/kiểu tĩnh | Dùng sealed interface và pattern switch |
| Nhét data client vào command rồi bỏ qua phân quyền | Dữ liệu đầu vào có thể không đáng tin | Xác thực/ủy quyền tại application boundary |

## 12. Bài tập và gợi ý

**Bài 1 — Thêm command mới.** Thêm `UpdateDeliveryAddress(orderId, address)` vào sealed interface `Command`. Quan sát lý do switch expression không có `default` yêu cầu bạn xử lý nhánh mới. Validate `address` ở compact constructor, nhưng kiểm tra đơn có được đổi địa chỉ không ở handler.

**Bài 2 — Tách domain rule.** Trong demo, quy tắc nào thuộc constructor `AddItem`, quy tắc nào thuộc `Handler`? Vì sao `quantity > 0` có thể kiểm tra ngay, còn “đơn phải đang DRAFT” thì không?

**Bài 3 — Immutability.** Viết record `BulkAdd(String orderId, List<Line> lines)`, thực hiện `List.copyOf(lines)` trong compact constructor. Vì sao cần thiết? Nếu `Line` chứa một `ArrayList` mutable thì còn thiếu điều gì?

**Bài 4 — Bài kiểm thử.** Viết phép thử cho các đường đi sau của `Handler`: tạo ID mới thành công, tạo ID trùng, gửi đơn rỗng thất bại, gửi đơn có line thành công, thêm line sau khi gửi thất bại, hủy đơn DRAFT thành công, hủy lần thứ hai thất bại.

**Bài 5 — Event so với command.** Khi handler xử lý thành công `SubmitOrder`, vì sao `OrderSubmitted` (nếu được phát ra) nên là một thông điệp khác `SubmitOrder`? Điều gì xảy ra nếu validation của `SubmitOrder` thất bại?

**Đáp án định hướng:**

- Bài 1: thêm subtype vào `permits` và thêm nhánh pattern tương ứng vào switch; nếu không, compile-time exhaustiveness có thể phát hiện thiếu.
- Bài 2: số lượng dương là thuộc tính độc lập của yêu cầu; trạng thái đơn phụ thuộc vào aggregate được tải từ nơi lưu trữ.
- Bài 3: `List.copyOf` cố định cấu trúc danh sách, nhưng không sao chép sâu từng element mutable.
- Bài 4: kiểm tra trạng thái, exception và phản hồi; không chỉ xác nhận một chuỗi output.
- Bài 5: command diễn tả điều **muốn làm**, event diễn tả điều **đã xảy ra**. Khi command bị từ chối, không được phát `OrderSubmitted` như thể thành công.

## Tài liệu tham khảo

- [JEP 395 — Records](https://openjdk.org/jeps/395): record class, mục đích và cơ chế tổng hợp thành viên.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): đóng tập subtype của interface/class.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): destructuring record trong pattern matching (Java 21).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): type/record pattern trong switch và tính exhaustiveness.
- [Oracle Java 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html).
- [Java SE 21 API — List.copyOf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable snapshot, giới hạn null và defensive copy.
