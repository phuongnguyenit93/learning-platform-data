# Kiểm tra kết quả hành vi và tránh ràng buộc quá mức vào tương tác nội bộ

**Dependency Injection (DI)** giúp ta thay một dependency thật bằng fake, stub hoặc mock trong kiểm thử. Tuy nhiên, thay thế được dependency **chưa đủ để có kiểm thử tốt**. Nếu bài test chỉ giám sát xem đối tượng A đã gọi phương thức B bao nhiêu lần, theo đúng thứ tự nào, thì một lần refactor hợp lệ có thể làm test thất bại dù kết quả nghiệp vụ không hề thay đổi.

Trong phần **Kiểm thử** của module **Dependency Injection**, nguyên tắc cốt lõi là: **ưu tiên kiểm tra những kết quả và cam kết mà người dùng hoặc hệ thống bên ngoài có thể quan sát**, chỉ kiểm tra tương tác giữa các đối tượng khi **bản thân tương tác đó là một phần của hợp đồng cần bảo vệ**.

Bài này dùng Java 17 thuần để thực hành **constructor injection**, kiểm thử bằng test double và phân biệt assertion bền vững với assertion gắn cứng vào chi tiết triển khai. Cách tư duy này vẫn đúng khi ứng dụng lớn lên, có composition root, quản lý scope/vòng đời và bắt đầu sử dụng DI container.

## 1. Behavior test và interaction test khác nhau ở đâu?

Giả sử một dịch vụ nhận đơn hàng. Hợp đồng nghiệp vụ có thể quy định:

- Khi đơn hợp lệ và chưa tồn tại, hệ thống **lưu đơn**, trả về biên nhận và **phát thông báo xác nhận**.
- Khi mã đơn đã tồn tại, hệ thống **từ chối tạo lại**, không làm thay đổi đơn cũ và không phát xác nhận mới.
- Khi thao tác lưu thất bại, hệ thống **không thông báo đơn đã được chấp nhận**.

Đây là các **hành vi quan sát được**. Một bài test có thể dùng fake repository để xem trạng thái lưu, recorder để xem thông báo, và kiểm tra giá trị trả về hoặc ngoại lệ.

Ngược lại, những chi tiết như “dịch vụ phải gọi `repository.findById()` đúng một lần” hoặc “phải gọi phương thức private nào trước” thường chỉ là **cách triển khai hiện tại**. Nếu sau này repository bổ sung `existsById()` hoặc dịch vụ tối ưu hóa cache, kết quả nghiệp vụ vẫn đúng nhưng test gắn vào chi tiết đó sẽ hỏng.

| Điều được kiểm tra | Ví dụ assertion | Nhận xét |
| --- | --- | --- |
| **Kết quả trả về** | Biên nhận có đúng mã đơn và nội dung đã cam kết | Thường là behavior test tốt |
| **Trạng thái bền vững** | Sau đặt đơn, repository đọc lại được đơn chính xác | Xác minh kết quả tại ranh giới lưu trữ |
| **Side effect có ý nghĩa** | Thông báo xác nhận được gửi khi đơn lưu thành công | Tương tác ở ranh giới hệ thống, có thể là hợp đồng |
| **Đường lỗi có ý nghĩa** | Lưu thất bại thì không gửi xác nhận thành công | Bảo vệ một cam kết nghiệp vụ quan trọng |
| **Chi tiết thực thi** | `findById` được gọi đúng một lần | Dễ quá ràng buộc nếu không có yêu cầu về số lần đọc |
| **Thứ tự nội bộ tùy ý** | Phải gọi helper A rồi helper B | Dễ vỡ khi refactor mà behavior không đổi |
| **Hình dạng object graph trong unit test** | Service bắt buộc dùng đúng lớp adapter X | Đi ngược mục đích thay thế dependency nếu hợp đồng chỉ cần interface |

**Không nên hiểu “behavior test” là “không bao giờ kiểm tra tương tác”.** Nếu một lời gọi ra hệ thống ngoài **chính là kết quả** cần kiểm chứng — chẳng hạn gửi đúng một email, không trừ tiền hai lần, không ghi audit sau khi thao tác thất bại — test phải quan sát tương tác ở ranh giới đó. Điểm cần tránh là theo dõi **mọi bước nội bộ**, kể cả những bước không thuộc hợp đồng.

## 2. DI tạo điều kiện kiểm thử nhưng không quyết định test nên assert gì

Một service tự tạo dependency:

~~~java
// Minh họa thiết kế gắn chặt; các kiểu adapter chỉ là giả định.
final class OrderService {
    private final OrderStore store = new SqlOrderStore();
    private final ReceiptSender sender = new EmailReceiptSender();
}
~~~

Cách này khiến unit test khó kiểm soát lưu trữ và việc gửi email. Cũng khó tạo ra lỗi lưu có chủ đích mà không cần hạ tầng thật.

Với **constructor injection**:

~~~java
final class OrderService {
    private final OrderStore store;
    private final ReceiptSender sender;

    OrderService(OrderStore store, ReceiptSender sender) {
        this.store = java.util.Objects.requireNonNull(store, "store");
        this.sender = java.util.Objects.requireNonNull(sender, "sender");
    }
}
~~~

Composition root quyết định adapter cho production; test có thể truyền một `InMemoryOrderStore` và `RecordingReceiptSender`. **Inversion of Control (IoC)** nằm ở việc service nhận cộng tác viên từ bên ngoài, không tự chọn và tạo chúng.

~~~mermaid
flowchart TD
    Production["Composition root production"] --> ServiceA["OrderService"]
    StoreA["SQL OrderStore"] --> ServiceA
    SenderA["Email ReceiptSender"] --> ServiceA
    TestRoot["Điểm lắp ghép test"] --> ServiceB["OrderService"]
    Fake["InMemoryOrderStore"] --> ServiceB
    Recorder["RecordingReceiptSender"] --> ServiceB
~~~

**DI giúp ta kiểm soát bối cảnh**, còn **hợp đồng nghiệp vụ** phải quyết định assertion. Nếu thay mọi dependency bằng mock rồi yêu cầu đúng mọi lời gọi nội bộ, test vẫn có thể giòn, dù đã sử dụng DI rất đúng kỹ thuật.

## 3. Viết hợp đồng hành vi trước khi chọn test double

Trước khi viết test, trả lời bốn câu hỏi:

1. **Input và điều kiện tiền đề là gì?** Ví dụ đơn hàng có mã hợp lệ, số lượng dương và mã chưa tồn tại.
2. **Kết quả công khai là gì?** Biên nhận trả về, đơn được lưu hoặc ngoại lệ được công bố.
3. **Side effect nào là hợp đồng?** Phát xác nhận khi thành công; không phát khi lưu thất bại.
4. **Chi tiết nào được tự do thay đổi?** Cách kiểm tra trùng lặp, số lần gọi helper, tên implementation, cache hoặc cách chia lớp nội bộ.

Nếu test không thể chỉ ra lý do nghiệp vụ hoặc hợp đồng API cho một assertion, hãy xem assertion đó có đang ràng buộc **chi tiết triển khai** hay không.

Một mẫu diễn đạt:

> **Given** kho chưa có đơn O-1 và dịch vụ được tiêm cộng tác viên giả; **when** đặt đơn O-1; **then** nhận được biên nhận đúng, đọc lại được đơn và ghi nhận một xác nhận tương ứng.

Mẫu này không yêu cầu service có bao nhiêu phương thức private, gọi `findById` mấy lần hoặc dùng cấu trúc dữ liệu nào ở bên trong.

## 4. Ví dụ Java 17 chạy độc lập: kiểm tra kết quả thay vì kịch bản lời gọi

Ví dụ dưới đây cố ý nhỏ để tập trung vào **mức trừu tượng của assertion**. Service nhận hai hợp đồng:

- `OrderStore`: tra cứu và lưu đơn.
- `ReceiptSender`: phát xác nhận đã chấp nhận đơn.

Trong test, `InMemoryOrderStore` giữ trạng thái trong bộ nhớ, còn `RecordingReceiptSender` ghi lại các biên nhận đã phát. Chúng là **test double do test sở hữu**, không đòi hỏi Mockito, JUnit hay DI container. Các bài test dùng một phương thức `check` đơn giản để có thể chạy bằng JDK 17.

Lưu toàn bộ đoạn sau vào `Main.java`:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

record Order(String id, String sku, int quantity) {
    Order {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(sku, "sku");
        if (id.isBlank() || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }
    }
}

record Receipt(String orderId, String description) {
    Receipt {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(description, "description");
    }
}

interface OrderStore {
    Optional<Order> findById(String id);

    void save(Order order);
}

@FunctionalInterface
interface ReceiptSender {
    void send(Receipt receipt);
}

final class OrderService {
    private final OrderStore store;
    private final ReceiptSender sender;

    OrderService(OrderStore store, ReceiptSender sender) {
        this.store = Objects.requireNonNull(store, "store");
        this.sender = Objects.requireNonNull(sender, "sender");
    }

    Receipt place(Order order) {
        Objects.requireNonNull(order, "order");

        if (store.findById(order.id()).isPresent()) {
            throw new IllegalArgumentException("Duplicate order");
        }

        store.save(order);
        Receipt receipt = new Receipt(
                order.id(),
                "Accepted " + order.sku() + " x" + order.quantity());
        sender.send(receipt);
        return receipt;
    }
}

// Fake biểu diễn trạng thái kết quả, không phải script kỳ vọng call.
final class InMemoryOrderStore implements OrderStore {
    private final Map<String, Order> orders = new HashMap<>();
    private boolean failOnSave;

    void setFailOnSave(boolean value) {
        failOnSave = value;
    }

    @Override
    public Optional<Order> findById(String id) {
        return Optional.ofNullable(orders.get(id));
    }

    @Override
    public void save(Order order) {
        if (failOnSave) {
            throw new IllegalStateException("Storage unavailable");
        }
        orders.put(order.id(), order);
    }
}

// Recording fake quan sát side effect qua ranh giới phát xác nhận.
final class RecordingReceiptSender implements ReceiptSender {
    private final List<Receipt> sent = new ArrayList<>();

    @Override
    public void send(Receipt receipt) {
        sent.add(receipt);
    }

    List<Receipt> delivered() {
        return List.copyOf(sent);
    }
}

public class Main {
    public static void main(String[] args) {
        testSuccessfulOrder();
        testDuplicateOrder();
        testStorageFailure();
        testAlternativeCollaborator();
        System.out.println("PASS");
    }

    private static void testSuccessfulOrder() {
        InMemoryOrderStore store = new InMemoryOrderStore();
        RecordingReceiptSender sender = new RecordingReceiptSender();
        OrderService service = new OrderService(store, sender);

        Order order = new Order("O-1", "BOOK-7", 2);
        Receipt actual = service.place(order);
        Receipt expected = new Receipt("O-1", "Accepted BOOK-7 x2");

        check(actual.equals(expected),
                "Kết quả công khai là biên nhận chính xác");
        check(store.findById("O-1").equals(Optional.of(order)),
                "Đơn phải được lưu và đọc lại đúng");
        check(sender.delivered().equals(List.of(expected)),
                "Một đơn thành công phải có đúng một xác nhận");
    }

    private static void testDuplicateOrder() {
        InMemoryOrderStore store = new InMemoryOrderStore();
        RecordingReceiptSender sender = new RecordingReceiptSender();
        OrderService service = new OrderService(store, sender);

        Order original = new Order("O-2", "PEN-1", 1);
        service.place(original);

        boolean rejected = false;
        try {
            service.place(new Order("O-2", "PEN-1", 9));
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }

        check(rejected, "Mã đơn trùng phải bị từ chối");
        check(store.findById("O-2").equals(Optional.of(original)),
                "Đơn cũ phải giữ nguyên");
        check(sender.delivered().size() == 1,
                "Thử lại với mã trùng không được tạo xác nhận mới");
    }

    private static void testStorageFailure() {
        InMemoryOrderStore store = new InMemoryOrderStore();
        store.setFailOnSave(true);
        RecordingReceiptSender sender = new RecordingReceiptSender();
        OrderService service = new OrderService(store, sender);

        boolean failed = false;
        try {
            service.place(new Order("O-3", "ERASER-2", 3));
        } catch (IllegalStateException expected) {
            failed = true;
        }

        check(failed, "Lỗi lưu phải được báo");
        check(store.findById("O-3").isEmpty(),
                "Không được có đơn đã lưu thành công giả");
        check(sender.delivered().isEmpty(),
                "Không được báo đã chấp nhận khi lưu thất bại");
    }

    private static void testAlternativeCollaborator() {
        InMemoryOrderStore store = new InMemoryOrderStore();
        List<String> acceptedIds = new ArrayList<>();

        // Một implementation khác của ReceiptSender.
        ReceiptSender sender = receipt ->
                acceptedIds.add(receipt.orderId());

        OrderService service = new OrderService(store, sender);
        Receipt receipt = service.place(new Order("O-4", "RULER-1", 1));

        check(receipt.orderId().equals("O-4"),
                "Kết quả không phụ thuộc implementation sender");
        check(store.findById("O-4").isPresent(),
                "Store vẫn lưu đúng đơn");
        check(acceptedIds.equals(List.of("O-4")),
                "Adapter khác vẫn đáp ứng hợp đồng phát xác nhận");
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 Main.java
java Main
~~~

Kết quả mong đợi:

~~~text
PASS
~~~

Các bài test **không kiểm tra** số lần gọi `findById`, không quan tâm service có dùng một helper riêng hay không, cũng không buộc thứ tự của các lệnh tra cứu nội bộ ngoài những quan hệ đã được nghiệp vụ công bố. Chúng kiểm tra kết quả trả về, đơn còn hay mất trong kho và việc xác nhận có được phát đúng theo hợp đồng hay không.

**Giới hạn quan trọng:** đây là mô hình **chạy tuần tự, không có transaction hoặc concurrency**. Bước “tìm rồi lưu” có thể bị race condition ở production nếu hai request có cùng mã; ràng buộc unique trong lưu trữ và thao tác nguyên tử cần được thiết kế riêng. Tương tự, việc lưu thành công rồi gửi xác nhận thất bại không được mô hình này xử lý bền vững. Với yêu cầu giao hàng sự kiện đáng tin cậy, có thể cần transactional outbox, retry và idempotency tùy hệ thống. Không xem ví dụ như một giao thức giao dịch hoàn chỉnh.

## 5. Một bài test dễ vỡ sẽ trông như thế nào?

Giả sử test sử dụng mocking framework để xác nhận toàn bộ script gọi dependency:

~~~java
// Pseudocode kiểu Mockito, KHÔNG phải chương trình Java độc lập.
// Không cần chạy đoạn này để hiểu vấn đề.
verify(store, times(1)).findById("O-1");
verify(store, times(1)).save(order);
verify(sender, times(1)).send(receipt);
verifyNoMoreInteractions(store, sender);
~~~

Một số assertion có ý nghĩa, nhưng các ràng buộc **`findById` phải được gọi đúng một lần** và **không có tương tác nào khác** có thể khiến test thất bại khi:

- Service chuyển từ `findById` sang `existsById`.
- Có thêm bước đọc để xác minh dữ liệu nhưng kết quả không thay đổi.
- Logic được tách thành cộng tác viên mới hoặc một adapter được tối ưu hóa.
- Cơ chế cache làm giảm số truy vấn nhưng giữ nguyên hợp đồng công khai.

Nếu test bảo vệ **kết quả đặt đơn**, những thay đổi nội bộ này không nhất thiết phải làm test đỏ. Việc “mock mọi thứ rồi verify mọi phương thức” biến test thành một bản sao của implementation thay vì một cơ chế phát hiện sai lệch nghiệp vụ.

### Vì sao verifyNoMoreInteractions thường gây ràng buộc quá mức?

`verifyNoMoreInteractions` có thể hợp lý khi hợp đồng yêu cầu **tuyệt đối không được có thêm side effect** ở một ranh giới bảo mật hoặc thanh toán. Nhưng dùng nó trên mọi dependency mặc định sẽ khiến mỗi lần thêm log, kiểm tra trạng thái hoặc đường tối ưu hóa thành lý do test thất bại.

Hãy chỉ rõ **đường tương tác nào không được phép xảy ra** và lý do. Ví dụ “không được gửi xác nhận khi lưu thất bại” là cam kết nghiệp vụ; “không được gọi bất kỳ helper nào khác” thì thường không phải.

## 6. Khi nào kiểm tra tương tác là đúng và cần thiết?

Có những hành vi **không quan sát được chỉ qua giá trị trả về**. Đặc biệt là các tác dụng phụ nằm ngoài tiến trình hoặc có tác động không thể đảo ngược.

| Hợp đồng cần bảo vệ | Assertion tương tác phù hợp | Điều nên tránh |
| --- | --- | --- |
| Mỗi đơn được xác nhận một lần khi lưu thành công | Recorder có đúng một thông báo với nội dung mong đợi | Verify mọi method nội bộ dẫn tới phát thông báo |
| Lưu thất bại thì không gửi xác nhận | Recorder rỗng sau lỗi lưu | Buộc đúng một trình tự gọi private helper |
| Một yêu cầu bị từ chối không được trừ tiền | Fake payment gateway không ghi lần charge nào | Kiểm tra cả những phương thức đọc vô hại không thuộc hợp đồng |
| Một lệnh retry không được nhân đôi side effect | Kiểm tra idempotency key hoặc số charge thực tế | Giả định “method được gọi một lần” là đủ để chứng minh hệ thống không thu tiền hai lần |
| Ghi audit bắt buộc | Kiểm tra sự kiện audit có nội dung cần thiết | Chỉ xác minh gọi logger bất kỳ mà không xem ngữ nghĩa |

**Khác biệt tinh tế:** “gửi một thông báo” có thể là yêu cầu nghiệp vụ trực tiếp, còn “gọi `notifier.send()` một lần” là một **cách kiểm chứng** yêu cầu đó qua test double. Test nên mô tả ý nghĩa ở lời assert, không biến tên method nội bộ thành chính hợp đồng nếu không cần.

Nếu API có cam kết thứ tự quan trọng — ví dụ phải kiểm tra quyền trước khi thực hiện thanh toán — có thể kiểm tra **thứ tự của các side effect công khai có ý nghĩa**. Nhưng nếu chỉ một giá trị trả về phụ thuộc vào hai phép tính thuần, việc ép thứ tự gọi hai phép tính thường không tăng giá trị kiểm thử.

## 7. Fake, stub, mock và spy: chọn theo bằng chứng cần quan sát

Các thuật ngữ test double đôi khi được dùng hơi khác giữa tài liệu và framework. Một cách phân biệt hữu ích là:

| Loại double | Mục đích chính | Ví dụ |
| --- | --- | --- |
| **Stub** | Cung cấp câu trả lời định sẵn để đưa test vào trạng thái cần kiểm tra | Repository trả một đơn đã tồn tại hoặc ném lỗi |
| **Fake** | Implementation đơn giản nhưng hoạt động theo một mô hình trạng thái có ích | Repository lưu `Order` trong `HashMap` |
| **Mock** | Đối tượng dùng xác minh những tương tác được kỳ vọng | Xác nhận gateway nhận một yêu cầu charge theo hợp đồng |
| **Spy/recording fake** | Ghi nhận những sự kiện/lời gọi thực tế để test kiểm tra | `RecordingReceiptSender` lưu danh sách biên nhận đã phát |

Trong ví dụ, `InMemoryOrderStore` là fake có trạng thái; `RecordingReceiptSender` là recording fake/spy. Không cần framework để hiểu nguyên tắc.

**Chọn double dựa vào điều gì cần quan sát**, không theo thói quen “mọi interface đều phải mock”. Với logic có trạng thái, một fake thường giúp test diễn đạt hành vi rõ hơn nhiều chuỗi `when(...).thenReturn(...)`. Với gateway có tác dụng phụ, recorder hoặc mock thường phù hợp.

Tuy nhiên, fake cũng có rủi ro: một `HashMap` không mô phỏng đầy đủ SQL transaction, unique constraint, khóa đồng thời hoặc hành vi lỗi mạng. Unit test với fake **không chứng minh adapter thật đúng**. Để tránh niềm tin sai, nên bổ sung **contract test cho adapter** và integration test trên hạ tầng phù hợp.

## 8. Thiết kế test bền trước refactor nhưng nhạy với lỗi thật

Một bài test tốt nên **thất bại khi hợp đồng bị phá**, nhưng **tiếp tục vượt qua khi implementation thay đổi mà hợp đồng vẫn giữ nguyên**.

Hãy xem các thay đổi sau đối với `OrderService`:

| Refactor | Kết quả nghiệp vụ vẫn đúng? | Behavior test nên thế nào? |
| --- | --- | --- |
| Đổi `findById` thành `existsById` trong port | Có thể đúng nếu logic trùng lặp không đổi | Test hành vi vẫn qua sau khi adapter/test double phù hợp được cập nhật |
| Tách phần tạo `Receipt` sang một lớp riêng | Có | Test không cần biết helper mới |
| Đổi `HashMap` thành implementation repository khác | Có nếu cùng hợp đồng | Test hành vi chỉ cần dữ liệu kết quả |
| Làm mất thông báo xác nhận sau khi lưu | Không | Test phải thất bại |
| Gửi thông báo dù lưu thất bại | Không | Test đường lỗi phải thất bại |
| Trả sai mã đơn trong biên nhận | Không | Test giá trị trả về phải thất bại |

Khi port công khai đổi từ `findById` sang `existsById`, test double và mã test cần **biên dịch theo API mới**, nhưng **assertion về behavior** không cần chuyển thành một script tương tác mới. Đó là ý nghĩa của việc giảm coupling giữa test và implementation.

### Một test có quá nhiều mock là dấu hiệu cần xem thiết kế

Một class đòi 12 cộng tác viên khiến mỗi unit test phải tạo 12 mock chỉ để gọi một method có thể đang gánh nhiều trách nhiệm. Đừng vội khắc phục bằng cách ẩn tất cả trong một service locator. Hãy kiểm tra khả năng tách trách nhiệm, gom logic cùng miền hoặc tạo facade phù hợp. **DI làm phụ thuộc lộ rõ**; test phức tạp đôi khi là tín hiệu hữu ích của thiết kế, không phải bất tiện cần giấu.

## 9. Đặc tả đường lỗi và trạng thái quan sát được

Đường thành công thường dễ viết test; đường lỗi mới là nơi hợp đồng cần chính xác. Một số câu hỏi quan trọng:

- Khi dependency lưu trữ ném ngoại lệ, service trả lỗi nào, có thông báo thành công nhầm không?
- Khi dữ liệu đầu vào sai, service có tạo tài nguyên ngoài hay side effect không?
- Khi dependency khác thất bại **sau khi lưu đã thành công**, trạng thái hiện tại là gì? Hệ thống có retry không?
- Có cần bảo đảm idempotency để một request gửi lại không gây thêm charge hoặc notification?
- Có cần đóng kết nối, stream hoặc session dù tác vụ thất bại không?

Ví dụ `testStorageFailure` kiểm tra **kho chưa lưu** và **không phát xác nhận**. Nó không đòi một chuỗi lời gọi cứng; nó bảo vệ hai đầu ra tiêu cực có ý nghĩa.

Không nên mở rộng `testStorageFailure` thành tuyên bố “không bao giờ gửi xác nhận trước khi lưu” cho **mọi implementation** nếu chưa có cơ chế giao dịch bảo đảm. Test hiện tại chỉ chứng minh hành vi của một cấu hình **tuần tự** với fake lưu trữ cụ thể. Nếu production cần tính nhất quán vượt qua lỗi tiến trình hoặc lỗi mạng, phải bổ sung thiết kế và integration test phù hợp.

### Xác minh ngoại lệ mà không phụ thuộc vào thông điệp nội bộ

Nếu API công bố **loại ngoại lệ hoặc mã lỗi**, test nên assert vào hợp đồng đó. Tránh assert toàn bộ chuỗi thông điệp `NullPointerException` hoặc tên class của adapter nếu chúng không nằm trong API công khai. Thông điệp phục vụ chẩn đoán có thể thay đổi hợp lệ mà không làm sai behavior.

Trong `Main.java`, test chỉ bắt loại `IllegalStateException` ở đường lưu thất bại và xác minh các kết quả liên quan. Ứng dụng thực tế có thể định nghĩa một `StorageUnavailableException` thuộc API riêng, giúp báo lỗi chính xác hơn và test ổn định hơn.

## 10. Ranh giới giữa unit test, contract test và integration test

Mục tiêu kiểm thử khác nhau đòi hỏi độ thực tế khác nhau:

| Tầng kiểm thử | Đối tượng thực | Double hoặc hạ tầng | Câu hỏi được trả lời |
| --- | --- | --- | --- |
| **Unit test** | Một service và logic nghiệp vụ | Fake/stub/recorder được inject | Service có giữ hợp đồng hành vi và đường lỗi? |
| **Contract test của port/adapter** | Adapter hoặc implementation của interface | Dữ liệu và môi trường kiểm thử phù hợp | Adapter thật có tuân hợp đồng của port mà fake đang giả định? |
| **Integration/wiring test** | Nhiều service, composition root hoặc DI container | Database/API test hoặc môi trường gần thật | Binding có đúng, vòng đời và side effect có kết nối chính xác? |
| **End-to-end test** | Luồng người dùng qua các ranh giới chính | Hạ tầng phù hợp | Người dùng có nhận kết quả mong đợi trong hệ thống tích hợp? |

Không nên chạy cả DI container chỉ để chứng minh một hàm thuần tính toán trả đúng số. Ngược lại, chỉ dùng unit test với mock cũng không đủ để chứng minh kết nối thật, transaction, serialization, retry hoặc lifecycle resource đúng.

### Contract test bảo vệ sự tương thích giữa fake và adapter thật

Giả sử `OrderStore.save(order)` phải làm cho `findById(order.id())` trả lại đúng đơn, và khi thao tác thất bại thì không được giả vờ lưu thành công. Ta có thể viết **một nhóm hành vi chung** cho các implementation của port; chạy nó với fake và với adapter database test.

Nếu adapter thật khác giả định quan trọng (ví dụ unique constraint hoặc transaction), unit test với fake có thể cho cảm giác an toàn giả. Contract test giúp bảo đảm test double không trở thành **một thế giới tưởng tượng** khác hẳn hệ thống thật.

Nhưng contract test không thể chứng minh mọi đặc điểm production; những trường hợp liên quan đến isolation level, race condition, lỗi mạng hoặc scale vẫn cần test chuyên biệt ở tầng tích hợp.

## 11. Scope, state và cô lập test khi sử dụng DI container

Không ít test thất bại ngẫu nhiên vì state bị chia sẻ giữa các lần chạy:

- Một fake repository singleton-scoped giữ dữ liệu từ test trước.
- Registry/static singleton tích lũy thông báo từ nhiều test.
- Context ứng dụng được cache giữa test nhưng một test lại sửa binding hoặc cấu hình mutable.
- Executor hoặc subscription còn chạy sau khi test kết thúc.

Một unit test đơn giản nên **tự tạo object graph mới** trong mỗi test:

~~~java
// Ví dụ nguyên tắc - dùng các kiểu từ Main.java ở mục 4.
InMemoryOrderStore store = new InMemoryOrderStore();
RecordingReceiptSender sender = new RecordingReceiptSender();
OrderService service = new OrderService(store, sender);
~~~

Điều này giúp mỗi bài test kiểm soát rõ dữ liệu ban đầu. Khi sử dụng DI container thật, có thể xây context riêng cho test hoặc reset đúng các thành phần được phép reset; phải đóng context và resource theo hợp đồng.

**Đừng làm test pass bằng cách cho global state bị xóa ngầm vào những thời điểm không rõ ràng.** Việc cô lập và lifecycle nên là quyết định tường minh của test setup.

Với dependency dùng chung giữa các service, có thể viết một test wiring nhỏ để xác minh **cùng instance cần chia sẻ** hoặc **scope cần tách biệt**, thay vì để tất cả unit test phụ thuộc vào object identity. Đây là một kiểm thử của **cấu hình lắp ghép**, không phải của từng service nghiệp vụ.

## 12. Dấu hiệu cảnh báo kiểm thử đang ràng buộc nội bộ quá mức

Các tình huống nên rà soát:

1. **Refactor đổi tên helper làm hàng chục test đỏ**, dù output và side effect không thay đổi.
2. **Mock từng dependency transitively**: test của service A phải biết cả cấu trúc của B, C và D.
3. **Assertion vào state private** chỉ để chắc một dòng code đã chạy, thay vì kiểm tra kết quả ở API.
4. **Buộc một thứ tự gọi không thuộc hợp đồng**, như gọi formatter trước logger, dù cả hai là thao tác thuần/không quan trọng.
5. **VerifyNoMoreInteractions trên mọi object** dù không có yêu cầu cấm các lời gọi bổ sung.
6. **Mock implementation class thay vì port** trong khi service có thể phụ thuộc vào abstraction nhỏ, rõ.
7. **Test tự tính lại thuật toán bằng cùng các bước** của production; cả code và test có thể cùng sai theo một giả định.
8. **Quá nhiều setup chi tiết** khiến ý nghĩa nghiệp vụ của test bị che lấp.

Cách cải thiện: diễn đạt behavior bằng ngôn ngữ miền nghiệp vụ, quan sát tại output và boundary có ý nghĩa, chỉ giữ những assertions tương tác thật sự bảo vệ hợp đồng.

### Cân bằng: không bỏ sót side effect quan trọng

Một test chỉ assert `receipt.orderId().equals("O-1")` có thể **quá yếu**, vì service vẫn có thể trả đúng biên nhận dù quên lưu đơn. Bởi vậy hãy kiểm tra **đủ kết quả công khai và side effect bắt buộc**, chứ không chọn cực đoan “chỉ assert return value”.

Điểm cân bằng là **ít lệ thuộc vào cơ chế nội bộ nhưng đủ nhạy với lỗi nghiệp vụ**.

## 13. Bài tập thực hành

**Bài 1 — Phân loại assertions.** Với `OrderService`, đánh dấu các kiểm tra sau thuộc hợp đồng hay chi tiết triển khai: trả đúng receipt, lưu đúng order, gọi `findById` đúng một lần, không gửi email sau khi lưu lỗi, gọi helper `buildReceipt` trước `send`, không tạo hai charge cho cùng idempotency key.

**Bài 2 — Refactor test giòn.** Một bài test Mockito dùng `verifyNoMoreInteractions(store, sender)`. Hãy thay bằng assertions vào receipt, trạng thái lưu trữ và nội dung thông báo. Nêu trường hợp nào vẫn cần kiểm tra số lần gửi.

**Bài 3 — Thay double.** Viết thêm một `ReceiptSender` dùng lambda ghi vào `List<String>`. Xác minh service vẫn đáp ứng hợp đồng mà không thay mã của `OrderService`.

**Bài 4 — Contract test.** Định nghĩa hành vi chung cho `OrderStore`: lưu đơn rồi tìm lại được; lưu thất bại phải báo lỗi; trùng khóa xử lý theo hợp đồng công bố. Chỉ rõ phần nào cần test với database thật.

**Bài 5 — Lỗi sau lưu.** Trong `OrderService`, cho `ReceiptSender.send` ném ngoại lệ sau khi `OrderStore.save` thành công. Xác định trạng thái thực tế và những lựa chọn thiết kế như retry, outbox hoặc thay đổi thời điểm xác nhận. Viết test mô tả **hợp đồng đã chọn**, không mặc định mọi thao tác có thể rollback chỉ vì có ngoại lệ.

## 14. Tự kiểm tra mức độ hiểu

**Câu 1.** DI có bảo đảm test tốt không? **Không.** DI cho phép thay dependency và kiểm soát bối cảnh; việc chọn assertions vẫn quyết định test có bền và có ích hay không.

**Câu 2.** Kiểm tra một email được gửi có phải luôn là “kiểm thử nội bộ không nên làm” không? **Không.** Nếu gửi email là side effect thuộc hợp đồng, phải xác minh nó qua boundary phù hợp.

**Câu 3.** Vì sao ép `repository.findById()` đúng một lần thường giòn? **Vì** số lần đọc có thể thay đổi khi tối ưu hóa mà behavior của use case không đổi, trừ khi số lần gọi là yêu cầu riêng về hiệu năng/chi phí.

**Câu 4.** Fake `HashMap` có thể thay hoàn toàn integration test database không? **Không.** Nó không mô phỏng đầy đủ transaction, concurrency, lỗi network và các constraint của database thật.

**Câu 5.** Khi lưu đơn thất bại, nên kiểm tra những gì? **Kiểm tra lỗi được trả**, trạng thái lưu không thay đổi theo hợp đồng và không có thông báo xác nhận thành công.

**Câu 6.** Khi nào nên test object identity hoặc thứ tự lifecycle? **Khi** đang kiểm tra chính sách scope/wiring hoặc một hợp đồng ownership có yêu cầu chia sẻ, cô lập và đóng tài nguyên theo thứ tự.

## Ghi nhớ

- **Ưu tiên kiểm thử hành vi quan sát được**: giá trị trả về, trạng thái bền vững, lỗi công khai và side effect thuộc hợp đồng.
- **Tránh over-specification**: không khóa test vào số lần gọi helper, thứ tự nội bộ hay implementation class nếu những chi tiết đó có thể thay đổi mà behavior không đổi.
- **Tương tác không phải lúc nào cũng là chi tiết nội bộ**: gửi email, ghi audit, trừ tiền hoặc không tạo side effect khi thất bại có thể chính là yêu cầu nghiệp vụ cần kiểm tra.
- **Constructor injection** cho phép đưa fake/stub/recorder vào test bằng Java thuần; test double phải đủ trung thực với hợp đồng port, đồng thời cần contract/integration test cho adapter thật.
- **Tách kiểm thử logic khỏi kiểm thử composition root, scope và lifecycle**. Một bộ test tốt bền trước refactor hợp lệ nhưng vẫn thất bại khi hệ thống phá vỡ cam kết với người dùng hoặc bên ngoài.
