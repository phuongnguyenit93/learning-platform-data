# Serializable, tham chiếu transient và dữ liệu cần khôi phục

Trong chương **Dữ liệu và scope**, bài này giải thích cách chuẩn bị dữ liệu để một flow Spring Web Flow có thể được lưu snapshot, tiếp tục ở request sau hoặc được khôi phục sau khi phiên làm việc bị gián đoạn. Với module **SPRING_WEB_FLOW**, việc mô hình hóa hành trình nhiều bước bằng state, event, transition và subflow chỉ đáng tin cậy khi dữ liệu đi cùng flow có vòng đời rõ ràng. Form binding, validation và các scope giúp tổ chức dữ liệu; khả năng tuần tự hóa và cơ chế khôi phục quyết định dữ liệu nào còn dùng được khi execution được phục hồi.

Vấn đề thường xuất hiện khi flow giữ một đối tượng nghiệp vụ quá lớn hoặc chứa tham chiếu tới service, proxy ORM, stream hay tài nguyên chỉ tồn tại trong request hiện tại. Đối tượng có thể hoạt động bình thường khi flow đang chạy trong bộ nhớ, nhưng lỗi khi repository cần tạo snapshot hoặc khi session được passivate, replicate hay khôi phục ở một tiến trình khác.

## Vì sao flow cần dữ liệu có thể khôi phục?

Một hành trình nhiều bước thường trải qua nhiều HTTP request. Sau khi render một view, ứng dụng cần giữ lại thông tin như mã giỏ hàng, địa chỉ đã chọn, lựa chọn giao hàng và bước nghiệp vụ đang chờ. Ở request tiếp theo, Web Flow tiếp tục execution tương ứng và dùng dữ liệu đã lưu để xử lý event mới.

Tùy cấu hình, repository của flow có thể lưu trạng thái thực thi bằng snapshot trong session hoặc một cơ chế lưu trữ khác. Một số môi trường còn cần tuần tự hóa dữ liệu khi session passivation, sao chép session giữa các node hoặc chuyển dữ liệu qua ranh giới tiến trình. Vì vậy, yêu cầu chính xác phụ thuộc repository, snapshot implementation, session store và cấu hình triển khai của ứng dụng.

Không nên kết luận rằng mọi đối tượng trong mọi scope luôn được serialize theo cùng một cách. Hãy xác định cơ chế lưu execution thực tế đang dùng. Tuy nhiên, nếu đường đi lưu trữ có tuần tự hóa object graph, mọi đối tượng cần lưu trong graph phải đáp ứng quy tắc của cơ chế đó.

~~~mermaid
flowchart TD
    A["Request xử lý flow"] --> B["FlowExecution và dữ liệu trong scope"]
    B --> C["Repository tạo snapshot / lưu execution"]
    C --> D{"Cơ chế lưu trữ có serialize?"}
    D -->|"Có"| E["Serialize object graph"]
    D -->|"Không"| F["Lưu theo cơ chế repository tương ứng"]
    E --> G["Lưu snapshot / session"]
    F --> G
    G --> H["Request tiếp theo hoặc phiên được khôi phục"]
    H --> I["Repository tìm execution"]
    I --> J["Khôi phục trạng thái và dữ liệu"]
    J --> K["Flow xử lý event tiếp theo"]
    K --> L["Khôi phục dữ liệu dẫn xuất khi cần"]
~~~

Cần phân biệt ba việc:

- **Giữ dữ liệu giữa các request:** flow scope hoặc conversation scope có thể giữ dữ liệu trong vòng đời flow theo cơ chế Web Flow.
- **Lưu snapshot:** repository ghi nhận trạng thái execution theo cấu hình.
- **Khôi phục dữ liệu nghiệp vụ:** ứng dụng nạp lại hoặc tính lại thông tin từ nguồn dữ liệu có thẩm quyền, chẳng hạn cơ sở dữ liệu hoặc dịch vụ nghiệp vụ.

Một snapshot không thay thế cơ sở dữ liệu nghiệp vụ và cũng không tự bảo đảm rằng một đơn hàng, khoản thanh toán hay quyền truy cập vẫn hợp lệ ở thời điểm tiếp tục.

## Serializable trong Java có ý nghĩa gì?

Trong Java, một lớp có thể tham gia cơ chế tuần tự hóa mặc định khi triển khai giao diện đánh dấu **Serializable**. Khi serialize một đối tượng, Java ghi trạng thái của đối tượng cùng các tham chiếu không bị loại khỏi quá trình tuần tự hóa. Quá trình này đi theo object graph: các trường tham chiếu tới đối tượng khác cũng phải tuần tự hóa được, trừ trường hợp được xử lý riêng.

Ví dụ một DTO nhỏ có thể dùng làm dữ liệu lưu trong flow:

~~~java
import java.io.Serializable;
import java.time.Instant;

public final class CheckoutSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;

    private String orderId;
    private String customerId;
    private String shippingAddressId;
    private String paymentAttemptId;
    private Instant lastUpdatedAt;

    public CheckoutSnapshot(
            String orderId,
            String customerId,
            String shippingAddressId,
            String paymentAttemptId,
            Instant lastUpdatedAt) {
        this.orderId = orderId;
        this.customerId = customerId;
        this.shippingAddressId = shippingAddressId;
        this.paymentAttemptId = paymentAttemptId;
        this.lastUpdatedAt = lastUpdatedAt;
    }

    public String getOrderId() {
        return orderId;
    }

    public String getCustomerId() {
        return customerId;
    }

    public String getShippingAddressId() {
        return shippingAddressId;
    }

    public String getPaymentAttemptId() {
        return paymentAttemptId;
    }

    public Instant getLastUpdatedAt() {
        return lastUpdatedAt;
    }
}
~~~

DTO này chỉ giữ các định danh và dữ liệu nhỏ cần để tiếp tục hành trình. Các trường như **String** và **Instant** đều có thể tuần tự hóa. Nếu thêm một trường **List**, **Map** hoặc một lớp tự định nghĩa, cần kiểm tra cả các phần tử, khóa và giá trị bên trong collection; việc kiểu khai báo là collection không làm cho toàn bộ object graph tự động an toàn.

**serialVersionUID** định danh phiên bản cấu trúc tuần tự hóa của lớp. Khai báo giá trị tường minh giúp ứng dụng kiểm soát tương thích khi class thay đổi. Nếu snapshot cũ được đọc bởi phiên bản class mới nhưng cấu trúc không tương thích, quá trình khôi phục có thể thất bại với lỗi như **InvalidClassException**. Một giá trị UID cố định không tự làm cho mọi thay đổi tương thích; nhóm vẫn phải quản lý thay đổi field và chiến lược triển khai phiên bản.

### Kiểm tra toàn bộ object graph

Giả sử đối tượng flow giữ một **CheckoutSnapshot**, trong đó có danh sách mặt hàng. Để snapshot có thể serialize, các phần tử trong danh sách cũng phải tuần tự hóa được. Nếu một phần tử giữ một **EntityManager**, **InputStream** hoặc một proxy không hỗ trợ serialization, toàn bộ thao tác có thể thất bại.

| Dữ liệu trong graph | Cần kiểm tra |
|---|---|
| Trường nguyên thủy và wrapper | Có giá trị phù hợp và không chứa dữ liệu ngoài ý muốn |
| String, enum, kiểu ngày giờ chuẩn | Kiểm tra kiểu cụ thể và phiên bản Java đang dùng |
| Collection và Map | Cả collection, khóa, giá trị và từng phần tử có serialize được không |
| DTO tự định nghĩa | Triển khai Serializable, có UID phù hợp và quản lý thay đổi cấu trúc |
| Entity hoặc proxy ORM | Có thể mang lazy proxy, quan hệ vòng hoặc tham chiếu persistence context |
| Service, repository, client kết nối | Là thành phần của Spring container, không phải dữ liệu phiên |
| Request, response, stream, socket | Thường gắn với tài nguyên hoặc vòng đời request, không phù hợp để lưu trong flow |

Không nên chỉ thêm **implements Serializable** vào lớp ngoài cùng rồi coi như xong. Cần kiểm tra mọi trường tham chiếu, kể cả những trường ít được sử dụng trong màn hình hiện tại.

## Tham chiếu transient và giới hạn của nó

Từ khóa **transient** yêu cầu cơ chế tuần tự hóa mặc định bỏ qua trường instance đó. Khi đối tượng được deserialize, trường transient thường nhận giá trị mặc định của kiểu: **null** với tham chiếu, **false** với boolean và **0** với kiểu số nguyên thủy.

Ví dụ:

~~~java
import java.io.Serializable;

public class LegacyCheckoutData implements Serializable {
    private static final long serialVersionUID = 1L;

    private String orderId;

    private transient OrderService orderService;

    public String getOrderId() {
        return orderId;
    }

    public OrderService getOrderService() {
        return orderService;
    }
}
~~~

Sau khi đối tượng được khôi phục từ snapshot, **orderService** không tự động được Spring inject trở lại. Đoạn code gọi **getOrderService()** có thể gặp **NullPointerException**. **transient** chỉ loại tham chiếu khỏi trạng thái được serialize; nó không phải cơ chế dependency injection, không tự tìm lại bean và cũng không tái tạo tài nguyên.

Vì vậy, không nên đặt service hoặc repository trong đối tượng dữ liệu của flow rồi dựa vào **transient** để làm cho object graph hợp lệ. Service nên do Spring quản lý và được gọi từ action hoặc component quản lý bởi application context. Đối tượng nằm trong scope chỉ giữ dữ liệu cần thiết để service xử lý.

Một trường transient có thể phù hợp với cache có thể tính lại, dữ liệu dẫn xuất hoặc tham chiếu kỹ thuật có cách tái tạo rõ ràng. Nếu thật sự cần khôi phục trường đó, ứng dụng phải có bước khởi tạo lại sau khi deserialize, chẳng hạn dùng custom serialization hook hoặc một bước rehydration được quản lý rõ ràng. Custom **readObject** có thể khôi phục trạng thái nội bộ của lớp, nhưng không nên dùng nó để tự tìm Spring bean qua static application context hoặc tạo kết nối ngoài ngoài vòng đời quản lý.

## Chọn dữ liệu nào cần lưu, dữ liệu nào cần nạp lại?

Mục tiêu là lưu đủ để tiếp tục đúng nghiệp vụ, nhưng giữ object graph nhỏ và ổn định. Có thể chia dữ liệu thành ba nhóm:

| Nhóm | Ví dụ | Cách xử lý |
|---|---|---|
| Dữ liệu người dùng đã nhập và cần giữ | Địa chỉ giao hàng, lựa chọn gói dịch vụ, nội dung biểu mẫu chưa gửi | Lưu DTO hoặc giá trị đơn giản trong scope phù hợp để người dùng không phải nhập lại |
| Định danh của dữ liệu nghiệp vụ | **orderId**, **customerId**, **paymentAttemptId** | Lưu ID; truy vấn lại đối tượng mới nhất từ dịch vụ khi tiếp tục |
| Dữ liệu dẫn xuất hoặc tạm thời | Tổng tiền hiển thị, phí ước tính, danh sách gợi ý, cache | Tính lại từ nguồn dữ liệu có thẩm quyền khi cần |
| Tài nguyên và thành phần runtime | Service, repository, EntityManager, socket, stream | Không lưu trong flow data; lấy từ Spring bean hoặc mở lại trong đúng vòng đời |
| Trạng thái nghiệp vụ có tính quyết định | Đơn đã xác nhận, thanh toán đã được chấp thuận | Đọc trạng thái mới nhất từ hệ thống nghiệp vụ; không tin snapshot cũ như nguồn chân lý |

Ví dụ, flow đặt hàng có thể lưu mã đơn và mã địa chỉ đã chọn. Khi người dùng quay lại sau một khoảng thời gian, ứng dụng tải đơn hiện tại, kiểm tra địa chỉ còn hợp lệ và tính lại phí giao hàng. Nếu giá hoặc tồn kho đã thay đổi, flow phải áp dụng quy tắc nghiệp vụ tương ứng thay vì sử dụng kết quả tính toán cũ một cách mù quáng.

### Chọn scope theo vòng đời

Serializable không thay thế việc chọn scope đúng. Dữ liệu đặt trong scope dài hơn sẽ tồn tại lâu hơn trong hành trình và có thể được đưa vào snapshot nhiều lần tùy cơ chế repository.

| Scope | Phạm vi sử dụng | Gợi ý dữ liệu |
|---|---|---|
| **requestScope** | Một request đang xử lý | Kết quả tạm chỉ dùng trong request hiện tại |
| **viewScope** | Trong một view-state | Dữ liệu phụ trợ riêng cho màn hình |
| **flowScope** | Một flow execution | DTO và ID cần dùng xuyên suốt các state |
| **conversationScope** | Conversation của flow gốc và các subflow liên quan | Dữ liệu thực sự cần chia sẻ trong cùng conversation |

Không đưa mọi dữ liệu vào **conversationScope** chỉ vì muốn giữ chúng lâu hơn. Scope dài hơn có thể làm snapshot lớn, giữ dữ liệu nhạy cảm lâu hơn và khiến dữ liệu cũ khó được làm mới. Chọn scope theo nhu cầu sử dụng thực tế, đồng thời xác định lúc nào dữ liệu phải được xóa hoặc thay thế.

## Mẫu khôi phục dữ liệu bằng Spring bean

Một mẫu dễ bảo trì là lưu snapshot DTO trong flow scope, sau đó gọi một Spring bean để nạp lại dữ liệu nghiệp vụ khi flow cần tiếp tục. Service được inject vào bean do Spring quản lý; nó không nằm trong DTO và không cần serialize.

Ví dụ component khôi phục:

~~~java
import org.springframework.stereotype.Component;

@Component
public class CheckoutRecoveryService {
    private final OrderService orderService;
    private final ShippingService shippingService;

    public CheckoutRecoveryService(
            OrderService orderService,
            ShippingService shippingService) {
        this.orderService = orderService;
        this.shippingService = shippingService;
    }

    public OrderSummary rebuildSummary(CheckoutSnapshot snapshot) {
        Order order = orderService.findCurrent(snapshot.getOrderId());

        ShippingAddress address =
                shippingService.findCurrent(snapshot.getShippingAddressId());

        return OrderSummary.from(order, address);
    }
}
~~~

**CheckoutRecoveryService** là bean do Spring quản lý. Khi gọi **rebuildSummary**, bean truy vấn trạng thái mới nhất và tạo dữ liệu trình bày mới. **OrderSummary** cũng cần phù hợp với cơ chế lưu trữ nếu nó được đặt vào scope và snapshot sau đó; hoặc chỉ giữ nó trong phạm vi ngắn nếu chỉ dùng để render một request.

Flow có thể gọi bean trong một action-state tại điểm khôi phục đã thiết kế:

~~~xml
<action-state id="rebuildOrderSummary">
    <evaluate expression="checkoutRecoveryService.rebuildSummary(flowScope.checkout)"
              result="flowScope.orderSummary" />
    <transition to="reviewOrder" />
</action-state>
~~~

Trong cấu hình này, **flowScope.checkout** là DTO đã được lưu; **checkoutRecoveryService** là bean có trong application context. Hãy thiết kế đường đi để action khôi phục được gọi trước khi view hoặc action sau đó sử dụng dữ liệu dẫn xuất. Việc một snapshot được deserialize không tự động gọi action này. Nếu flow có thể tiếp tục trực tiếp ở nhiều state, cần xác định điểm kiểm tra và khôi phục phù hợp cho từng đường đi, thay vì giả định mọi lần resume đều đi qua một action-state duy nhất.

Phương thức khôi phục cũng cần xử lý trường hợp dữ liệu gốc không còn tồn tại, người dùng mất quyền truy cập, đơn đã bị hủy hoặc trạng thái thanh toán đã thay đổi. Khi đó flow nên phát sinh nhánh nghiệp vụ thích hợp: thông báo, quay lại bước chỉnh sửa, khởi động lại một phần hoặc kết thúc với outcome phù hợp.

## Xử lý dữ liệu cũ và thay đổi phiên bản

Một flow execution có thể tồn tại lâu hơn một lần deploy ứng dụng. Nếu class của DTO thay đổi giữa lúc snapshot được tạo và lúc nó được đọc lại, ứng dụng cần có chiến lược tương thích.

Các nguyên tắc cần xem xét:

- Duy trì **serialVersionUID** có chủ đích cho các lớp snapshot.
- Thêm field mới với giá trị mặc định hoặc bước migration rõ ràng; không giả định mọi thay đổi đều tương thích.
- Tránh đổi kiểu hoặc đổi ý nghĩa field khi snapshot cũ vẫn có thể tồn tại.
- Nếu không thể hỗ trợ snapshot cũ, có kế hoạch hết hạn execution, thông báo người dùng và khởi động lại hành trình an toàn.
- Khi chạy nhiều phiên bản ứng dụng đồng thời, kiểm tra khả năng đọc snapshot giữa các phiên bản trước khi triển khai rolling update.
- Dùng version field trong DTO nếu nghiệp vụ cần chuyển đổi dữ liệu cũ sang cấu trúc mới.

Ví dụ, snapshot cũ có thể chỉ lưu **shippingAddressId**, trong khi phiên bản mới cần thêm **deliveryMethod**. Khi khôi phục, ứng dụng có thể xác định version và chọn phương án mặc định phù hợp, hoặc yêu cầu người dùng xác nhận lại lựa chọn giao hàng. Không nên tự suy ra lựa chọn mới nếu điều đó có thể làm thay đổi chi phí hoặc cam kết dịch vụ.

## Những lỗi thường gặp khi khôi phục

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| **NotSerializableException** | Một đối tượng trong object graph không serialize được | Xác định lớp được nêu trong exception; thay bằng DTO/ID hoặc loại tham chiếu runtime khỏi graph |
| **InvalidClassException** | UID hoặc cấu trúc class không tương thích với snapshot cũ | Kiểm tra phiên bản class, UID và chiến lược tương thích/migration |
| Trường transient là null sau resume | Trường bị bỏ qua khi serialize và chưa có bước khởi tạo lại | Tái tạo dữ liệu qua Spring bean hoặc bỏ tham chiếu đó khỏi flow data |
| Lazy loading thất bại | Entity/proxy được dùng sau khi persistence context đã đóng | Lưu ID hoặc DTO; truy vấn lại qua service trong transaction phù hợp |
| Dữ liệu hiển thị đã lỗi thời | Snapshot chứa giá trị dẫn xuất cũ | Tính lại từ nguồn dữ liệu hiện tại và kiểm tra điều kiện nghiệp vụ |
| Snapshot quá lớn | Lưu entity graph, file, collection hoặc dữ liệu không cần thiết | Thu nhỏ DTO, chỉ giữ dữ liệu cần tiếp tục và đặt scope ngắn hơn |
| Resume thất bại sau deploy | Snapshot cũ không tương thích với phiên bản mới | Kiểm thử tương thích, version hóa hoặc cho execution hết hạn có kiểm soát |

Khi điều tra, hãy đọc exception gốc và xác định object graph tại thời điểm repository lưu snapshot. Đừng chỉ bắt **NotSerializableException** rồi bỏ qua; việc bỏ qua có thể khiến flow tiếp tục mà thiếu dữ liệu cần thiết.

## Kiểm thử khả năng serialize và khôi phục

Một bài kiểm thử đơn vị có thể kiểm tra DTO bằng cách serialize rồi deserialize trong cùng phiên bản class:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;

import org.junit.jupiter.api.Test;

class CheckoutSnapshotTest {

    @Test
    void snapshotCanBeSerializedAndRestored() throws Exception {
        CheckoutSnapshot original = new CheckoutSnapshot(
                "order-42",
                "customer-7",
                "address-9",
                "payment-attempt-3",
                java.time.Instant.parse("2026-01-10T10:15:30Z"));

        byte[] bytes;
        try (ByteArrayOutputStream buffer = new ByteArrayOutputStream();
             ObjectOutputStream output = new ObjectOutputStream(buffer)) {
            output.writeObject(original);
            output.flush();
            bytes = buffer.toByteArray();
        }

        CheckoutSnapshot restored;
        try (ByteArrayInputStream buffer = new ByteArrayInputStream(bytes);
             ObjectInputStream input = new ObjectInputStream(buffer)) {
            restored = (CheckoutSnapshot) input.readObject();
        }

        assertEquals(original.getOrderId(), restored.getOrderId());
        assertEquals(original.getCustomerId(), restored.getCustomerId());
        assertEquals(
                original.getShippingAddressId(),
                restored.getShippingAddressId());
    }
}
~~~

Kiểm thử trên chỉ chứng minh DTO và object graph hiện tại có thể đi qua cơ chế Java serialization. Nó không chứng minh repository Web Flow, session store, cluster replication hoặc quy trình khôi phục nghiệp vụ hoạt động đúng.

Ở mức tích hợp, cần kiểm tra thêm:

1. Khởi chạy flow, nhập dữ liệu và lưu những giá trị cần giữ trong scope.
2. Tạo một request tiếp theo để repository thực hiện quy trình lưu execution theo cấu hình.
3. Tiếp tục flow bằng execution key và xác nhận dữ liệu người dùng đã nhập vẫn còn.
4. Kiểm tra trường transient không được giả định là đã tự khôi phục.
5. Chạy action khôi phục và xác nhận dữ liệu dẫn xuất được nạp lại từ service.
6. Thay đổi hoặc xóa dữ liệu nghiệp vụ gốc trước khi resume; xác nhận flow xử lý trạng thái mới đúng quy tắc.
7. Nếu triển khai hỗ trợ session passivation, replication hoặc nhiều phiên bản ứng dụng, kiểm thử các tình huống đó trong môi trường tương ứng.

Với các flow quan trọng, nên kiểm thử cả trường hợp snapshot hỏng, execution hết hạn và người dùng không còn quyền truy cập. Hành trình phải có cách phục hồi rõ ràng, không để dữ liệu cũ khiến thao tác nghiệp vụ được thực hiện hai lần hoặc trái với trạng thái hiện tại.

## Checklist thiết kế dữ liệu có thể khôi phục

Trước khi đưa một đối tượng vào flow scope hoặc conversation scope, hãy rà soát:

- [ ] Đã xác định repository và cơ chế lưu execution thực tế.
- [ ] Đã kiểm tra object graph nếu đường đi lưu trữ có serialization.
- [ ] DTO chỉ chứa dữ liệu cần thiết, không giữ service hoặc tài nguyên runtime.
- [ ] Các collection và phần tử bên trong đều phù hợp với cơ chế lưu trữ.
- [ ] Trường **transient** có kế hoạch khởi tạo lại nếu ứng dụng cần dùng sau resume.
- [ ] ID của dữ liệu nghiệp vụ được dùng để truy vấn trạng thái mới nhất khi cần.
- [ ] Dữ liệu dẫn xuất được tính lại thay vì tin snapshot đã lỗi thời.
- [ ] Có chiến lược tương thích khi class thay đổi hoặc snapshot cũ còn tồn tại.
- [ ] Có kiểm thử serialize/deserialize và kiểm thử tích hợp resume flow.
- [ ] Có xử lý cho execution hết hạn, dữ liệu không còn tồn tại và lỗi khôi phục.

## Ghi nhớ

- **Serializable** là điều kiện tham gia Java serialization; toàn bộ object graph liên quan cũng phải đáp ứng cơ chế lưu trữ đang dùng.
- **transient** bỏ qua một trường trong serialization mặc định. Trường tham chiếu thường trở thành **null** sau khi deserialize và không được Spring tự inject lại.
- Lưu DTO nhỏ cùng ID nghiệp vụ; lấy service từ Spring container và nạp lại dữ liệu có thẩm quyền qua một bước khôi phục rõ ràng.
- Chọn scope theo vòng đời dữ liệu. Scope dài hơn không đồng nghĩa dữ liệu đã bền vững hoặc còn đúng với trạng thái nghiệp vụ hiện tại.
- Kiểm thử cả khả năng serialize, resume execution, khôi phục dữ liệu, tương thích phiên bản và các nhánh lỗi trước khi dựa vào flow snapshot trong môi trường triển khai.

