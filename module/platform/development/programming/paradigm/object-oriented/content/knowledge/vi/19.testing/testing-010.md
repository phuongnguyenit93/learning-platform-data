# Kiểm thử tương tác giữa nhiều đối tượng trong Java OOP

## 1. Vì sao phải kiểm thử sự phối hợp?

Một phương thức hướng đối tượng thường không tự làm mọi việc. Nó nhận yêu cầu, gọi nhiều đối tượng cộng tác, xử lý kết quả rồi quyết định bước tiếp theo. Trong ứng dụng bán hàng, dịch vụ checkout có thể phối hợp:

1. **Inventory** để giữ hàng.
2. **PaymentGateway** để thu tiền.
3. **ReceiptSender** để gửi biên nhận.

Từng lớp có thể hoạt động đúng khi kiểm thử riêng, nhưng cả quy trình vẫn sai: gửi biên nhận trước khi thanh toán, thu tiền khi không đủ hàng, quên trả lại hàng khi bị từ chối, hoặc gọi thu tiền hai lần. Đây là các lỗi **tương tác giữa đối tượng**.

**Kiểm thử tương tác (interaction testing)** xem các đối tượng có gọi cộng tác viên đúng điều kiện, đúng tham số, đúng số lần và đúng thứ tự cần thiết hay không. **Kiểm thử trạng thái/kết quả (state-based testing)** quan sát dữ liệu và kết quả cuối. Hai cách thường bổ sung cho nhau; không nên chỉ đếm lời gọi mà bỏ qua hành vi nghiệp vụ.

Sau bài này, bạn có thể:
- Nhận ra ranh giới đối tượng cần kiểm thử.
- Viết các test cho nhánh thành công, từ chối và lỗi.
- Dùng Mockito verify, never, verifyNoInteractions và InOrder.
- Viết một kiểm thử phối hợp bằng các đối tượng thật trong bộ nhớ.
- Hiểu lúc nào thứ tự gọi là yêu cầu nghiệp vụ, lúc nào nó chỉ là chi tiết hiện thực.

## 2. Đặt hợp đồng nghiệp vụ trước

Ta xây dựng CheckoutService. Mỗi đơn hàng có mã, mã sản phẩm, số lượng và tổng tiền VND dương. Các quy tắc:

| Tình huống | Các lời gọi phải xảy ra | Kết quả |
| --- | --- | --- |
| Không đủ hàng | inventory.reserve trả false; **không** gọi payment hoặc sender | OUT_OF_STOCK |
| Giữ hàng thành công, thanh toán thành công | reserve → charge → send, mỗi bước đúng một lần | PAID |
| Cổng thanh toán từ chối | reserve → charge → release; không gửi biên nhận | DECLINED |
| Cổng thanh toán ném RuntimeException | reserve → charge → release; không gửi; truyền lỗi lên | Exception |
| Đơn hàng null | Không gọi bất kỳ cộng tác viên nào | NullPointerException |
| Gửi biên nhận thất bại sau khi thu tiền | Exception được truyền lên; không tự thu tiền lại, không tự release | Exception (cần cơ chế gửi lại trong hệ thống thật) |

Điều kiện quan trọng: **không gọi charge nếu reserve thất bại**; **không gửi biên nhận nếu charge chưa được xác nhận thành công**.

Một mô tả trình tự:

~~~mermaid
sequenceDiagram
    actor Client
    participant C as CheckoutService
    participant I as Inventory
    participant P as PaymentGateway
    participant R as ReceiptSender
    Client->>C: checkout(order)
    C->>I: reserve(sku, quantity)
    alt Hết hàng
        I-->>C: false
        C-->>Client: OUT_OF_STOCK
    else Đã giữ hàng
        I-->>C: true
        C->>P: charge(orderId, amountVnd)
        alt Thanh toán bị từ chối
            P-->>C: false
            C->>I: release(sku, quantity)
            C-->>Client: DECLINED
        else Thanh toán thành công
            P-->>C: true
            C->>R: send(orderId)
            C-->>Client: PAID
        end
    end
~~~

Sơ đồ diễn tả luồng bình thường. Trường hợp ngoại lệ cần kiểm thử riêng vì mỗi phụ thuộc có thể thất bại theo cách khác.

## 3. Dự án Java 17 + Maven + JUnit 5 + Mockito

Dự án dùng Java 17 để có record, JUnit Jupiter để viết test, Mockito để xác minh lời gọi. Không cần Spring.

~~~text
oop-collaboration-tests/
├── pom.xml
└── src/
    ├── main/java/vn/example/
    │   ├── Inventory.java
    │   ├── PaymentGateway.java
    │   ├── ReceiptSender.java
    │   └── CheckoutService.java
    └── test/java/vn/example/
        ├── CheckoutServiceTest.java
        └── CheckoutCollaborationTest.java
~~~

### 3.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>oop-collaboration-tests</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.mockito</groupId>
            <artifactId>mockito-junit-jupiter</artifactId>
            <version>5.14.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 3.2. Ba giao diện của các cộng tác viên

**src/main/java/vn/example/Inventory.java**

~~~java
package vn.example;

public interface Inventory {
    /** true nếu giữ đủ số lượng; false nếu không thể giữ. */
    boolean reserve(String sku, int quantity);

    /** Hoàn lại đúng số lượng đã giữ. */
    void release(String sku, int quantity);
}
~~~

**src/main/java/vn/example/PaymentGateway.java**

~~~java
package vn.example;

public interface PaymentGateway {
    /** true: chấp nhận thanh toán; false: từ chối. */
    boolean charge(String orderId, long amountVnd);
}
~~~

**src/main/java/vn/example/ReceiptSender.java**

~~~java
package vn.example;

public interface ReceiptSender {
    void send(String orderId);
}
~~~

Bộ interface này chỉ thể hiện các khả năng CheckoutService cần. Lớp sử dụng không cần biết kho hàng nằm ở SQL hay bộ nhớ, cổng thanh toán dùng HTTP hay hệ thống giả, sender dùng SMTP hay hàng đợi.

### 3.3. Lớp điều phối thật

**src/main/java/vn/example/CheckoutService.java**

~~~java
package vn.example;

import java.util.Objects;

public final class CheckoutService {
    private final Inventory inventory;
    private final PaymentGateway gateway;
    private final ReceiptSender sender;

    public CheckoutService(
            Inventory inventory,
            PaymentGateway gateway,
            ReceiptSender sender) {
        this.inventory = Objects.requireNonNull(inventory, "inventory");
        this.gateway = Objects.requireNonNull(gateway, "gateway");
        this.sender = Objects.requireNonNull(sender, "sender");
    }

    public record Order(
            String orderId,
            String sku,
            int quantity,
            long amountVnd) {

        public Order {
            if (orderId == null || orderId.isBlank()
                    || sku == null || sku.isBlank()
                    || quantity <= 0 || amountVnd <= 0) {
                throw new IllegalArgumentException("Invalid order");
            }
        }
    }

    public enum Outcome {
        OUT_OF_STOCK, DECLINED, PAID
    }

    public Outcome checkout(Order order) {
        Objects.requireNonNull(order, "order");

        if (!inventory.reserve(order.sku(), order.quantity())) {
            return Outcome.OUT_OF_STOCK;
        }

        final boolean accepted;
        try {
            accepted = gateway.charge(
                    order.orderId(), order.amountVnd());
        } catch (RuntimeException failure) {
            inventory.release(order.sku(), order.quantity());
            throw failure;
        }

        if (!accepted) {
            inventory.release(order.sku(), order.quantity());
            return Outcome.DECLINED;
        }

        sender.send(order.orderId());
        return Outcome.PAID;
    }
}
~~~

Các điểm cần chú ý:

- **CheckoutService là đối tượng thật cần kiểm thử**. Nó chỉ được tiêm ba cộng tác viên qua constructor.
- Đối tượng Order tự bảo vệ bất biến dữ liệu của mình; test không thể đưa số lượng âm vào một Order hợp lệ.
- Nếu hết hàng, trả kết quả ngay, nên PaymentGateway và ReceiptSender tuyệt đối không được gọi.
- Khi gateway từ chối, release xảy ra **sau** charge. Khi gateway ném RuntimeException, release cũng xảy ra rồi lỗi được truyền ra.
- Khối try chỉ bao quanh charge. Vì thế một exception từ release không bị bắt lại để release lần thứ hai.
- Một lỗi từ sender sau khi charge thành công được truyền ra; dịch vụ **không** cố hoàn tác thanh toán. Đây là sự giới hạn có chủ đích để bài tập làm rõ tính nhất quán giữa các hệ thống.

**Lưu ý nghiệp vụ thật:** sự cố mạng tại gateway không cho biết chắc chắn tiền đã bị trừ hay chưa. Quy tắc release khi gateway ném lỗi ở ví dụ là giả định đơn giản cho bài học, không phải quy trình thanh toán an toàn cho production. Hệ thống thực cần mã giao dịch idempotent, tra cứu trạng thái, xử lý bù và phối hợp trạng thái đơn hàng một cách đáng tin cậy.

## 4. Unit test tương tác bằng Mockito

Mockito tạo các cộng tác viên có thể điều khiển phản hồi và ghi nhận lời gọi. Test sẽ khởi tạo **CheckoutService thật**; không mock chính CheckoutService.

**src/test/java/vn/example/CheckoutServiceTest.java**

~~~java
package vn.example;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InOrder;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CheckoutServiceTest {
    private static final CheckoutService.Order ORDER =
            new CheckoutService.Order("O-1", "SKU-1", 2, 100_000);

    @Mock Inventory inventory;
    @Mock PaymentGateway gateway;
    @Mock ReceiptSender sender;

    private CheckoutService service;

    @BeforeEach
    void setUp() {
        service = new CheckoutService(inventory, gateway, sender);
    }

    @Test
    void successCallsCollaboratorsInBusinessOrder() {
        when(inventory.reserve("SKU-1", 2)).thenReturn(true);
        when(gateway.charge("O-1", 100_000)).thenReturn(true);

        CheckoutService.Outcome result = service.checkout(ORDER);

        assertEquals(CheckoutService.Outcome.PAID, result);
        InOrder calls = inOrder(inventory, gateway, sender);
        calls.verify(inventory).reserve("SKU-1", 2);
        calls.verify(gateway).charge("O-1", 100_000);
        calls.verify(sender).send("O-1");
        calls.verifyNoMoreInteractions();
    }

    @Test
    void outOfStockStopsBeforePaymentAndReceipt() {
        when(inventory.reserve("SKU-1", 2)).thenReturn(false);

        CheckoutService.Outcome result = service.checkout(ORDER);

        assertEquals(CheckoutService.Outcome.OUT_OF_STOCK, result);
        verify(inventory).reserve("SKU-1", 2);
        verifyNoMoreInteractions(inventory);
        verifyNoInteractions(gateway, sender);
    }

    @Test
    void declinedPaymentReleasesInventoryWithoutReceipt() {
        when(inventory.reserve("SKU-1", 2)).thenReturn(true);
        when(gateway.charge("O-1", 100_000)).thenReturn(false);

        CheckoutService.Outcome result = service.checkout(ORDER);

        assertEquals(CheckoutService.Outcome.DECLINED, result);
        InOrder calls = inOrder(inventory, gateway);
        calls.verify(inventory).reserve("SKU-1", 2);
        calls.verify(gateway).charge("O-1", 100_000);
        calls.verify(inventory).release("SKU-1", 2);
        calls.verifyNoMoreInteractions();
        verifyNoInteractions(sender);
    }

    @Test
    void gatewayFailureReleasesInventoryAndPropagatesError() {
        when(inventory.reserve("SKU-1", 2)).thenReturn(true);
        IllegalStateException failure =
                new IllegalStateException("Gateway unavailable");
        when(gateway.charge("O-1", 100_000)).thenThrow(failure);

        IllegalStateException actual = assertThrows(
                IllegalStateException.class,
                () -> service.checkout(ORDER));

        assertSame(failure, actual);
        InOrder calls = inOrder(inventory, gateway);
        calls.verify(inventory).reserve("SKU-1", 2);
        calls.verify(gateway).charge("O-1", 100_000);
        calls.verify(inventory).release("SKU-1", 2);
        calls.verifyNoMoreInteractions();
        verifyNoInteractions(sender);
    }

    @Test
    void receiptFailureIsNotTreatedAsPaymentFailure() {
        when(inventory.reserve("SKU-1", 2)).thenReturn(true);
        when(gateway.charge("O-1", 100_000)).thenReturn(true);
        doThrow(new IllegalStateException("Mail unavailable"))
                .when(sender).send("O-1");

        assertThrows(IllegalStateException.class,
                () -> service.checkout(ORDER));

        InOrder calls = inOrder(inventory, gateway, sender);
        calls.verify(inventory).reserve("SKU-1", 2);
        calls.verify(gateway).charge("O-1", 100_000);
        calls.verify(sender).send("O-1");
        calls.verifyNoMoreInteractions();
        verify(inventory, never()).release(anyString(), anyInt());
    }

    @Test
    void nullOrderDoesNotTouchCollaborators() {
        assertThrows(NullPointerException.class,
                () -> service.checkout(null));
        verifyNoInteractions(inventory, gateway, sender);
    }

    @Test
    void constructorRequiresAllCollaborators() {
        assertThrows(NullPointerException.class,
                () -> new CheckoutService(null, gateway, sender));
        assertThrows(NullPointerException.class,
                () -> new CheckoutService(inventory, null, sender));
        assertThrows(NullPointerException.class,
                () -> new CheckoutService(inventory, gateway, null));

        verifyNoInteractions(inventory, gateway, sender);
    }
}
~~~

### Giải thích các lời xác minh

| API kiểm thử | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| when(...).thenReturn(...) | Cho mock phản hồi theo kịch bản | Kho còn/hết hàng; thanh toán chấp nhận/từ chối |
| when(...).thenThrow(...) | Giả lập exception từ cộng tác viên | Dịch vụ thanh toán gặp sự cố |
| doThrow(...).when(sender).send(...) | Giả lập lỗi từ phương thức trả void | Gửi thông báo thất bại |
| verify(mock).method(args) | Mặc định yêu cầu lời gọi khớp đúng một lần | Tham số truyền sang kho và gateway |
| verify(mock, never()).method(...) | Xác minh lời gọi nhất định không xuất hiện | Không release khi đã thu tiền và chỉ lỗi gửi email |
| verifyNoInteractions(mock) | Không có lời gọi nào với mock | Nhánh thiếu hàng không chạm gateway/sender |
| inOrder(a, b, c) | Xác minh thứ tự những lời gọi nghiệp vụ cần thiết | Phải giữ hàng trước khi thu tiền, thu tiền trước khi gửi |
| assertEquals / assertThrows | Kiểm tra kết quả và ngoại lệ công khai | Tránh test chỉ có verify mà quên nghiệp vụ |

**Chú ý:** Mockito trả false mặc định cho boolean chưa stub. Vì vậy case kho hết hàng cũng sẽ xảy ra nếu quên stub Inventory, khiến test dễ xanh do vô tình. Hãy khai báo rõ phản hồi cần thiết của từng nhánh như trong ví dụ.

**Thứ tự xác minh là một quyết định thiết kế.** Nếu hai thao tác độc lập và không có hợp đồng về thứ tự, dùng verify thông thường thay vì InOrder. Chỉ ghim thứ tự cho các bước mà đổi thứ tự sẽ phá vỡ quy tắc nghiệp vụ.

## 5. Kiểm thử phối hợp với các đối tượng thật trong bộ nhớ

Mock có thể chứng minh CheckoutService **đã gọi** release, nhưng không chứng minh hàng tồn kho thật sự được hoàn lại. Để kiểm tra cả trạng thái sau một chuỗi lời gọi, ta có thể kết hợp các đối tượng thật và implementation bộ nhớ có hành vi rõ ràng.

**src/test/java/vn/example/CheckoutCollaborationTest.java**

~~~java
package vn.example;

import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;

class CheckoutCollaborationTest {

    private static final CheckoutService.Order ORDER =
            new CheckoutService.Order("O-1", "SKU-1", 2, 100_000);

    @Test
    void successfulWorkflowUpdatesRealInMemoryState() {
        InMemoryInventory inventory = new InMemoryInventory();
        RecordingSender sender = new RecordingSender();

        // Hàm lambda này là implementation của PaymentGateway.
        PaymentGateway gateway = (orderId, amountVnd) -> true;
        CheckoutService service =
                new CheckoutService(inventory, gateway, sender);

        assertEquals(CheckoutService.Outcome.PAID,
                service.checkout(ORDER));
        assertEquals(3, inventory.available("SKU-1"));
        assertEquals(List.of("O-1"), sender.sent);
    }

    @Test
    void rejectedPaymentRestoresStockWithoutNotification() {
        InMemoryInventory inventory = new InMemoryInventory();
        RecordingSender sender = new RecordingSender();
        PaymentGateway gateway = (orderId, amountVnd) -> false;
        CheckoutService service =
                new CheckoutService(inventory, gateway, sender);

        assertEquals(CheckoutService.Outcome.DECLINED,
                service.checkout(ORDER));
        assertEquals(5, inventory.available("SKU-1"));
        assertTrue(sender.sent.isEmpty());
    }

    private static final class InMemoryInventory implements Inventory {
        private final Map<String, Integer> stock = new HashMap<>();

        InMemoryInventory() {
            stock.put("SKU-1", 5);
        }

        @Override
        public boolean reserve(String sku, int quantity) {
            int current = stock.getOrDefault(sku, 0);
            if (current < quantity) {
                return false;
            }
            stock.put(sku, current - quantity);
            return true;
        }

        @Override
        public void release(String sku, int quantity) {
            stock.merge(sku, quantity, Integer::sum);
        }

        int available(String sku) {
            return stock.getOrDefault(sku, 0);
        }
    }

    private static final class RecordingSender implements ReceiptSender {
        final List<String> sent = new ArrayList<>();

        @Override
        public void send(String orderId) {
            sent.add(orderId);
        }
    }
}
~~~

Ở ví dụ này, InMemoryInventory là một fake có hành vi lưu trữ; RecordingSender là spy ghi nhận tác dụng phụ. Không cần Mockito cho hai test này: state của kho và danh sách gửi là bằng chứng cuối cùng về sự phối hợp. Các test này vẫn không kết nối kho hàng thật hoặc cổng thanh toán thật, nên chưa phải integration test đầy đủ với hạ tầng production.

### 5.1. Chạy toàn bộ bài học

Trong thư mục chứa pom.xml, dùng JDK 17 hoặc mới hơn tương thích Maven:

~~~bash
mvn test
~~~

Hai lớp test gồm **9 phương thức @Test**: 7 kiểm thử tương tác mock và 2 kiểm thử phối hợp trong bộ nhớ. Khi nhập mã chính xác như trên và có các dependency Maven tương ứng, kỳ vọng 9 test qua, không failures/errors. Mỗi test được tạo với fixture riêng để không phụ thuộc vào thứ tự chạy.

## 6. Những mức kiểm thử cần phân biệt

| Cấp độ | Đối tượng được chạy thật | Phụ thuộc thay thế | Bảo đảm chính |
| --- | --- | --- | --- |
| Unit + interaction test | CheckoutService | Mock Inventory, Gateway, Sender | Điều kiện gọi, tham số, thứ tự, số lần, ngoại lệ |
| Unit/collaboration test | CheckoutService, InMemoryInventory, RecordingSender | Gateway trả kết quả cố định | Thay đổi trạng thái qua nhiều đối tượng trong bộ nhớ |
| Integration test | Adapter JDBC/API và dịch vụ test | Chỉ một số hệ thống ngoài | Mapping, transaction, cấu hình, hợp đồng với hạ tầng |
| End-to-end test | Luồng ứng dụng gần môi trường thật | Có thể dùng sandbox để tránh thu tiền thật | Các thành phần phối hợp từ đầu vào tới kết quả cuối |

Lưu ý: cách đặt tên cấp độ có thể khác nhau giữa các nhóm. Điều quan trọng hơn nhãn gọi là nói rõ test đã chạy thành phần nào thật, đã giả lập thành phần nào và không kiểm chứng được điều gì.

Trong sản phẩm thật, bạn còn phải kiểm thử adapter kho hàng trước cạnh tranh cập nhật, thanh toán khi timeout và hệ thống gửi thông báo khi hàng đợi chậm hoặc trùng. Mockito không thể tự chứng minh các hệ thống thật tuân theo hợp đồng.

## 7. Lỗi phổ biến khi kiểm thử nhiều đối tượng

### 7.1. Chỉ kiểm tra gọi phương thức, không kiểm tra kết quả

~~~java
// Chưa đủ: chỉ biết charge đã được gọi.
verify(gateway).charge("O-1", 100_000);
~~~

Cần kết hợp assertion của kết quả (PAID/DECLINED) và trạng thái còn lại (ví dụ tồn kho). Một lời gọi đúng tham số có thể vẫn dẫn đến kết quả sai nếu lớp điều phối bỏ qua giá trị trả về.

### 7.2. Mock cả đối tượng đang kiểm thử

Nếu mock CheckoutService rồi tự quy định checkout trả PAID, test sẽ kiểm chứng Mockito làm theo cấu hình, chứ không thực thi nhánh xử lý nghiệp vụ. Hãy tạo CheckoutService thật và thay thế các cộng tác viên bên ngoài ranh giới cần cô lập.

### 7.3. Xác minh mọi chi tiết nội bộ

Test quá chi tiết có thể gãy sau một lần refactor đúng. Ví dụ, nếu hệ thống thêm bước ghi log, việc yêu cầu mọi lời gọi xảy ra theo danh sách cứng có thể gây false alarm. Chỉ xác minh những tương tác thuộc **hợp đồng nghiệp vụ** hoặc những tương tác tránh hậu quả nguy hiểm như charge hai lần.

### 7.4. Test phụ thuộc dữ liệu dùng chung

Nếu kho fake là singleton chia sẻ trạng thái giữa nhiều test, test đầu sẽ giảm tồn kho của test sau. Khởi tạo fake mới cho từng test; ở integration test dùng database thật thì tách dữ liệu hoặc rollback/cleanup phù hợp.

### 7.5. Xử lý lỗi từ nhiều đối tượng một cách mơ hồ

PaymentGateway ném lỗi chưa chắc giao dịch bị từ chối: đôi khi gateway đã nhận tiền nhưng phản hồi bị mất. Không được suy luận nghiệp vụ từ một exception kỹ thuật nếu hợp đồng chưa định nghĩa rõ trạng thái. Với hệ thống thanh toán thật, cần cơ chế reconciliation, idempotency key, lưu tiến độ và retry an toàn.

Gửi biên nhận thất bại cũng không phải là lý do tự động thu tiền lại. Có thể cần transactional outbox hoặc sự kiện bền vững để gửi lại. Các quyết định đó phải được nêu thành hợp đồng rồi kiểm thử bằng kịch bản tương ứng.

## 8. Cách thiết kế để dễ kiểm thử tương tác

1. **Giao diện nhỏ theo vai trò**: Inventory, PaymentGateway, ReceiptSender chỉ khai báo thao tác mà quy trình cần.
2. **Constructor injection**: truyền cộng tác viên từ bên ngoài thay vì tự new hoặc tìm qua singleton toàn cục.
3. **Tách orchestration khỏi I/O**: CheckoutService quyết định thứ tự, adapter chịu trách nhiệm giao tiếp bên ngoài.
4. **Thiết kế kết quả rõ ràng**: enum Outcome giúp các nhánh thành công, hết hàng, từ chối khác nhau và test không phải đoán từ null.
5. **Phân biệt trả false với exception**: nhánh nghiệp vụ từ chối khác với lỗi kỹ thuật; cách phục hồi có thể khác.
6. **Nhìn vào ranh giới tác dụng phụ**: charge, release và send là các tương tác đặc biệt cần test tỉ mỉ vì thay đổi thế giới bên ngoài.
7. **Có test trạng thái ngoài test thứ tự**: phối hợp nhiều đối tượng chỉ thực sự đúng khi kết quả cuối cũng đúng.
8. **Dùng fake/mocks có chủ đích**: mock phù hợp để đo tương tác; fake hữu ích để mô phỏng thay đổi trạng thái; adapter thật cần integration test riêng.

## 9. Bài tập thực hành

**Bài 1 — Bắt lỗi thứ tự.** Cố tình chuyển dòng sender.send(...) lên trước gateway.charge(...). Chạy lại unit test và xác định ca nào thất bại. Khôi phục vị trí đúng và giải thích vì sao thứ tự này mang ý nghĩa nghiệp vụ.

**Bài 2 — Bắt lỗi số lần gọi.** Cố ý gọi gateway.charge(...) hai lần trên đường thành công. Kiểm tra InOrder/verifyNoMoreInteractions phát hiện lời gọi dư, rồi trả mã về đúng.

**Bài 3 — Thêm nhánh hết hàng trong test trạng thái.** Thêm test vào CheckoutCollaborationTest với đơn yêu cầu 6 sản phẩm khi kho chỉ còn 5. Kỳ vọng OUT_OF_STOCK, số lượng kho giữ nguyên 5 và không có biên nhận.

**Bài 4 — Thêm sự kiện bền vững.** Giả lập EventPublisher và mở rộng quy trình để công bố OrderPaid sau thanh toán thành công. Quy định rõ thứ tự giữa lưu trạng thái thanh toán và phát sự kiện; dùng mock để xác minh thứ tự, sau đó dùng fake repository để xác minh trạng thái cuối.

**Tiêu chí tự đánh giá:** Một test tốt về tương tác nhiều đối tượng chỉ ra được **ai gọi ai, khi nào, với dữ liệu gì, tác dụng phụ nào phải xảy ra hoặc bị cấm**, đồng thời chứng minh kết quả quan sát được từ phía người dùng hoặc trạng thái nghiệp vụ.