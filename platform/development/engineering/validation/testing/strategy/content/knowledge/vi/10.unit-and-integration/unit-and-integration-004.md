# Chọn mock, stub, fake hoặc thành phần phụ thuộc thật theo mục tiêu

## Mục tiêu bài học

Trong kiểm thử đơn vị và kiểm thử tích hợp, một thành phần thường phụ thuộc vào cơ sở dữ liệu, dịch vụ bên ngoài, đồng hồ hệ thống, hàng đợi, bộ lưu trữ hoặc các thành phần khác. Cách kiểm soát những phụ thuộc này ảnh hưởng trực tiếp đến loại bằng chứng mà bài kiểm thử cung cấp. Dùng mock, stub, fake hay thành phần thật không chỉ là lựa chọn công cụ; đó là quyết định về ranh giới kiểm thử, tính cô lập, độ tin cậy và chi phí vận hành.

Trong chiến lược VALIDATION_TESTING_STRATEGY, lựa chọn phù hợp phải bắt đầu từ câu hỏi cần xác minh. Nếu cần cung cấp một phản hồi xác định để kiểm tra nhánh xử lý, stub có thể phù hợp. Nếu cần xác minh một cộng tác viên nhận đúng lệnh hoặc dữ liệu, mock có thể hữu ích. Nếu cần một triển khai nhẹ nhưng có hành vi thực tế, fake có thể giúp kiểm thử nhanh. Nếu cần bằng chứng rằng ứng dụng tương tác đúng với cơ sở dữ liệu, broker hoặc dịch vụ thật, cần kiểm thử tích hợp với phụ thuộc thật hoặc môi trường tương đương.

Sau bài học, người học có thể:

- Giải thích test double và phân biệt mock, stub, fake với phụ thuộc thật.
- Chọn cách thay thế hoặc giữ phụ thuộc theo mục tiêu kiểm thử.
- Nhận biết lợi ích, giới hạn và rủi ro của từng lựa chọn.
- Thiết kế kiểm thử cô lập mà vẫn bảo vệ được hợp đồng và hành vi tích hợp.
- Tránh over-mocking, kiểm thử giả định của mock và các kiểm thử phụ thuộc môi trường thiếu ổn định.
- Xây dựng chiến lược kết hợp unit test, contract test và integration test.

## 1. Bắt đầu từ mục tiêu và ranh giới kiểm thử

Trước khi chọn mock hay dùng cơ sở dữ liệu thật, hãy xác định chính xác điều cần kiểm tra. Một bài kiểm thử tốt trả lời một câu hỏi có phạm vi rõ ràng, chẳng hạn:

- Hàm tính phí có áp dụng đúng quy tắc cho các trường hợp biên không?
- Dịch vụ có xử lý đúng khi cổng thanh toán trả về timeout không?
- Thành phần đặt hàng có gửi đúng yêu cầu đến dịch vụ kho không?
- Repository có lưu và truy vấn dữ liệu đúng trên hệ quản trị cơ sở dữ liệu đang dùng không?
- Ứng dụng có tương thích với hợp đồng API của dịch vụ bên ngoài không?

Tiếp theo, xác định đối tượng kiểm thử (system under test, SUT), các cộng tác viên trực tiếp và ranh giới cần bảo vệ. Ví dụ, khi kiểm thử dịch vụ đặt hàng, đối tượng kiểm thử có thể là OrderService. Các cộng tác viên là OrderRepository, PaymentGateway, InventoryClient và Clock. Nhóm cần quyết định cộng tác viên nào sẽ được thay thế, cộng tác viên nào cần chạy thật và hành vi nào phải được xác minh ở cấp tích hợp.

Không nên chọn test double chỉ vì nó giúp test chạy nhanh. Cần hỏi liệu bằng chứng tạo ra có phù hợp với câu hỏi hay không. Một mock có thể chứng minh ứng dụng đã gọi một phương thức với tham số nhất định, nhưng không chứng minh dịch vụ bên ngoài thực sự hiểu yêu cầu đó. Một stub có thể giúp kiểm tra nhánh xử lý lỗi, nhưng không chứng minh cơ sở dữ liệu lưu dữ liệu đúng. Một fake có thể cung cấp hành vi nhất quán trong kiểm thử, nhưng không chứng minh fake tương đương hoàn toàn với sản phẩm thật.

## 2. Test double là gì?

**Test double** là một đối tượng hoặc thành phần được sử dụng thay cho phụ thuộc thật trong một bài kiểm thử. Tên gọi này được dùng như thuật ngữ chung cho các dạng thay thế như dummy, stub, spy, mock và fake. Mỗi dạng phục vụ mục đích khác nhau; trong bài học này, trọng tâm là stub, mock và fake.

Test double có thể giúp:

- Cô lập đối tượng đang kiểm thử khỏi phụ thuộc chậm, khó khởi tạo hoặc khó kiểm soát.
- Tạo tình huống hiếm gặp như timeout, lỗi mạng, dữ liệu bất thường hoặc phản hồi thất bại.
- Kiểm soát đầu vào và kết quả để kiểm thử lặp lại được.
- Xác minh cách thành phần phối hợp với cộng tác viên.
- Giảm chi phí chạy kiểm thử và hạn chế phụ thuộc vào dịch vụ bên ngoài.

Tuy nhiên, test double cũng có thể tạo ra rủi ro:

- Hành vi thay thế khác với phụ thuộc thật.
- Bài kiểm thử chỉ xác minh cách cài đặt hiện tại thay vì hành vi mong đợi.
- Mock quá sâu khiến thay đổi cấu trúc nội bộ làm hỏng nhiều test dù chức năng vẫn đúng.
- Fake không được kiểm tra tương thích nên có thể che giấu sai lệch.
- Bộ kiểm thử không chạy với phụ thuộc thật nên bỏ sót lỗi cấu hình, giao thức, truy vấn hoặc serialization.

Cần xem test double là công cụ có mục tiêu, không phải cách thay thế mọi phụ thuộc trong mọi loại kiểm thử.

## 3. Stub: cung cấp câu trả lời đã định trước

**Stub** là một test double cung cấp dữ liệu hoặc phản hồi được định trước khi đối tượng kiểm thử gọi đến nó. Stub thường dùng để kiểm soát đầu vào gián tiếp của SUT và đưa SUT vào một trạng thái hoặc nhánh xử lý cụ thể.

Ví dụ, OrderService cần kiểm tra cách xử lý khi dịch vụ kho báo hết hàng. Stub InventoryClient có thể trả về trạng thái OUT_OF_STOCK mà không cần kết nối đến hệ thống kho thật.

~~~java
interface InventoryClient {
    InventoryStatus check(String sku, int quantity);
}

enum InventoryStatus {
    AVAILABLE, OUT_OF_STOCK
}

class OrderService {
    private final InventoryClient inventory;

    OrderService(InventoryClient inventory) {
        this.inventory = inventory;
    }

    boolean canPlaceOrder(String sku, int quantity) {
        return inventory.check(sku, quantity) == InventoryStatus.AVAILABLE;
    }
}

// Stub đơn giản trả về kết quả được cấu hình trước.
class OutOfStockStub implements InventoryClient {
    @Override
    public InventoryStatus check(String sku, int quantity) {
        return InventoryStatus.OUT_OF_STOCK;
    }
}
~~~

Bài kiểm thử có thể tạo OrderService với OutOfStockStub và xác minh canPlaceOrder trả về false. Mục tiêu là kiểm tra SUT xử lý đúng phản hồi hết hàng. Test không cần chứng minh rằng InventoryClient gửi HTTP request đúng; đó là câu hỏi của kiểm thử tích hợp hoặc contract test.

### 3.1. Khi nào nên dùng stub?

- Cần cung cấp dữ liệu đầu vào gián tiếp để kiểm tra một nhánh xử lý.
- Cần mô phỏng phản hồi thành công, thất bại hoặc giá trị biên.
- Phụ thuộc thật chậm, không ổn định hoặc khó tạo trạng thái mong muốn.
- Cần kiểm thử timeout, lỗi mạng, dịch vụ không sẵn sàng hoặc hạn mức bị vượt.
- Muốn xác minh kết quả của SUT mà không cần xác minh tương tác với phụ thuộc.

Stub thường không cần ghi nhận hoặc xác minh mọi lời gọi. Nó chủ yếu trả lời câu hỏi “nếu phụ thuộc trả về kết quả này thì SUT xử lý thế nào?”. Nếu bài kiểm thử cần khẳng định SUT đã gửi đúng lệnh hoặc không gửi lệnh trong một tình huống, mock hoặc spy có thể phù hợp hơn.

### 3.2. Stub có thể mô phỏng lỗi như thế nào?

Ví dụ, một stub có thể ném exception để kiểm tra việc xử lý khi dịch vụ ngoài không phản hồi:

~~~java
class PaymentTimeoutStub implements PaymentGateway {
    @Override
    public PaymentResult charge(PaymentRequest request) {
        throw new GatewayTimeoutException("Payment provider timed out");
    }
}
~~~

SUT có thể được kiểm tra xem có chuyển trạng thái đơn hàng sang PENDING, ghi nhận mã giao dịch để đối soát và tránh gửi yêu cầu thanh toán trùng hay không. Những hành vi này cần được xác định theo yêu cầu nghiệp vụ; không nên giả định rằng mọi timeout đều có nghĩa giao dịch thất bại, vì nhà cung cấp có thể đã xử lý giao dịch nhưng phản hồi bị mất.

## 4. Mock: xác minh tương tác với cộng tác viên

**Mock** là test double được cấu hình để ghi nhận hoặc xác minh cách SUT tương tác với nó. Nhóm thường dùng mock khi tương tác là một phần quan trọng của hợp đồng cần kiểm tra, chẳng hạn gửi thông báo, gọi dịch vụ thanh toán, phát sự kiện hoặc không gọi một thao tác khi điều kiện chưa đạt.

Ví dụ, sau khi tạo đơn hàng thành công, OrderService cần yêu cầu NotificationSender gửi thông báo xác nhận. Mock có thể xác minh thông điệp được gửi đúng một lần với mã đơn hàng tương ứng.

~~~java
interface NotificationSender {
    void sendOrderConfirmation(String orderId);
}

// Minh họa phong cách kiểm tra bằng mock của một thư viện mocking.
@Test
void sendsConfirmationAfterOrderIsCreated() {
    NotificationSender sender = mock(NotificationSender.class);
    OrderService service = new OrderService(repositoryStub, inventoryStub, sender);

    service.placeOrder(validOrder);

    verify(sender).sendOrderConfirmation("ORD-42");
}
~~~

Trong ví dụ, điểm cần xác minh là tương tác gửi thông báo. Nếu mục tiêu chỉ là kiểm tra giá trị trả về của OrderService, việc xác minh từng lời gọi nội bộ có thể không cần thiết. Mock hữu ích khi lời gọi có ý nghĩa quan sát được hoặc là một phần của hợp đồng cộng tác.

### 4.1. Khi nào nên dùng mock?

- Cần xác minh một lệnh quan trọng đã được gửi đến cộng tác viên.
- Cần xác minh số lần gọi, thứ tự gọi hoặc tham số của một tương tác có ý nghĩa.
- Cần đảm bảo không thực hiện tác động ngoài ý muốn, ví dụ không gửi thanh toán khi dữ liệu không hợp lệ.
- Cần kiểm tra ứng dụng phát sự kiện hoặc gửi thông điệp khi điều kiện nghiệp vụ được đáp ứng.
- Cần mô phỏng một phụ thuộc mà hành vi tương tác của nó là nội dung chính cần xác minh.

### 4.2. Cẩn trọng với kiểm thử dựa quá nhiều vào tương tác

Mock có thể làm test gắn chặt với cấu trúc nội bộ. Ví dụ, một test xác minh OrderService gọi đúng ba phương thức repository theo đúng thứ tự có thể thất bại sau khi nhóm tối ưu truy vấn, dù trạng thái đơn hàng cuối cùng vẫn chính xác.

Nên ưu tiên xác minh tương tác khi nó có ý nghĩa nghiệp vụ hoặc là hợp đồng cần bảo vệ. Tránh kiểm tra các lời gọi nội bộ không ảnh hưởng đến kết quả quan sát được. Một số nguyên tắc:

- Xác minh các tác động có ý nghĩa như gửi thanh toán, phát sự kiện hoặc gửi thông báo.
- Không mock các đối tượng giá trị đơn giản hoặc logic thuần không có phụ thuộc bên ngoài.
- Hạn chế xác minh thứ tự gọi trừ khi thứ tự đó thực sự quan trọng.
- Tránh dùng mock để tái tạo toàn bộ thuật toán hoặc luồng nội bộ của SUT.
- Khi cần kiểm tra kết quả cuối cùng, ưu tiên trạng thái hoặc đầu ra quan sát được thay vì chi tiết triển khai.

## 5. Fake: triển khai nhẹ nhưng có hành vi thực tế

**Fake** là một triển khai thay thế có thể hoạt động thực sự nhưng đơn giản hơn hoặc không phù hợp để dùng trong production. Fake không chỉ trả về một giá trị cố định; nó thực hiện một phần hành vi của phụ thuộc.

Ví dụ, FakeOrderRepository có thể lưu đối tượng trong bộ nhớ và hỗ trợ tìm kiếm theo ID. Nó cho phép kiểm thử dịch vụ nghiệp vụ mà không cần khởi động cơ sở dữ liệu.

~~~java
interface OrderRepository {
    void save(Order order);
    Optional<Order> findById(String id);
}

class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public void save(Order order) {
        orders.put(order.id(), order);
    }

    @Override
    public Optional<Order> findById(String id) {
        return Optional.ofNullable(orders.get(id));
    }
}
~~~

Fake này thực hiện thao tác lưu và đọc trong bộ nhớ. Nó phù hợp để kiểm thử logic của dịch vụ sử dụng repository, nhưng không chứng minh rằng câu SQL, transaction, index, ràng buộc hoặc cấu hình cơ sở dữ liệu thật hoạt động đúng.

### 5.1. Khi nào nên dùng fake?

- Cần một phụ thuộc có hành vi thực tế hơn stub nhưng nhẹ hơn hệ thống thật.
- Nhiều bài kiểm thử cần dùng cùng một triển khai thay thế.
- Muốn kiểm thử logic nghiệp vụ với trạng thái có thể tạo và truy vấn.
- Phụ thuộc thật tốn kém hoặc khó chạy trong mỗi bài unit test.
- Có thể duy trì fake đơn giản và xác minh nó phù hợp với hợp đồng của phụ thuộc thật.

### 5.2. Giới hạn của fake

Fake có nguy cơ trở thành một hệ thống thứ hai mà nhóm phải bảo trì. Nếu fake ngày càng phức tạp, mô phỏng transaction, khóa, phân trang, isolation hoặc quy tắc của cơ sở dữ liệu, nó có thể tạo ra hành vi khác với hệ thống thật.

Để kiểm soát:

- Chỉ triển khai phần hợp đồng cần cho các bài kiểm thử.
- Không tự thêm hành vi không tồn tại trong phụ thuộc thật.
- Dùng cùng bộ kiểm tra hợp đồng cho fake và triển khai thật khi có thể.
- Có kiểm thử tích hợp riêng cho các đặc tính mà fake không mô phỏng.
- Xem xét loại bỏ fake nếu chi phí bảo trì cao hơn lợi ích.

## 6. Dùng phụ thuộc thật: kiểm tra hành vi tích hợp

Dùng **phụ thuộc thật (real dependency)** nghĩa là bài kiểm thử tương tác với triển khai thực tế hoặc một phiên bản tương đương về hành vi của phụ thuộc, thay vì thay thế nó bằng stub, mock hoặc fake.

Ví dụ, kiểm thử repository có thể chạy với PostgreSQL trong một môi trường kiểm thử tạm thời. Bài kiểm thử xác minh truy vấn, ràng buộc, transaction, migration và hành vi thực tế của hệ quản trị cơ sở dữ liệu.

Phụ thuộc thật phù hợp khi câu hỏi kiểm thử liên quan đến chính sự tích hợp:

- Câu SQL có hoạt động trên hệ quản trị cơ sở dữ liệu đang sử dụng không?
- Transaction có rollback đúng khi một thao tác thất bại không?
- Serialization và deserialization có tương thích với API không?
- Broker có giữ đúng thứ tự hoặc cơ chế xác nhận thông điệp theo cấu hình không?
- Cấu hình TLS, xác thực, timeout và retry có hoạt động đúng không?
- Ứng dụng có tương thích với phiên bản dịch vụ hoặc thư viện đang triển khai không?

### 6.1. Ưu điểm

- Cung cấp bằng chứng gần với điều kiện vận hành thực tế.
- Phát hiện sai lệch mà test double không thể mô phỏng, chẳng hạn truy vấn sai, schema không tương thích hoặc cấu hình sai.
- Giảm nguy cơ kiểm thử chỉ xác minh giả định do chính test double tạo ra.
- Hữu ích cho kiểm thử contract, integration, migration và hành vi phụ thuộc nền tảng.

### 6.2. Chi phí và rủi ro

- Cần khởi tạo, cấu hình và dọn dẹp môi trường.
- Có thể chậm hơn và dễ bị ảnh hưởng bởi tài nguyên dùng chung.
- Dữ liệu hoặc trạng thái tồn tại giữa các lần chạy có thể làm test không xác định.
- Phụ thuộc bên ngoài có thể giới hạn tần suất chạy hoặc tạo chi phí.
- Nếu dùng dịch vụ thật có tác động bên ngoài, test có thể gửi email, tạo giao dịch hoặc thay đổi dữ liệu không mong muốn.

Nên dùng môi trường kiểm thử riêng, container, sandbox hoặc dịch vụ thử nghiệm do nhà cung cấp cung cấp. Tránh để test tự động ghi dữ liệu vào hệ thống production hoặc tạo tác động thật ngoài phạm vi kiểm soát.

## 7. So sánh mock, stub, fake và phụ thuộc thật

| Lựa chọn | Vai trò chính | Phù hợp khi | Giới hạn chính |
|---|---|---|---|
| Stub | Trả dữ liệu hoặc lỗi được định trước. | Cần điều khiển phản hồi để kiểm tra nhánh xử lý của SUT. | Không chứng minh tương tác hoặc hành vi thật của phụ thuộc. |
| Mock | Ghi nhận và xác minh tương tác. | Cần kiểm tra lệnh, tham số, số lần gọi hoặc tác động có ý nghĩa. | Có thể làm test phụ thuộc chi tiết triển khai. |
| Fake | Cung cấp triển khai thay thế đơn giản nhưng có hành vi. | Cần trạng thái và hành vi thực tế ở mức nhẹ, lặp lại được. | Có thể lệch với triển khai thật và cần bảo trì. |
| Phụ thuộc thật | Chạy triển khai thực tế hoặc tương đương. | Cần xác minh tích hợp, giao thức, truy vấn, cấu hình hoặc hành vi nền tảng. | Tốn thời gian, tài nguyên và yêu cầu môi trường/dữ liệu. |

Một thư viện mocking có thể gọi chung nhiều chức năng là “mock”, “stub” hoặc “spy” theo cách riêng. Cách gọi trong công cụ có thể khác với định nghĩa khái niệm. Khi viết chiến lược, hãy mô tả hành vi cần có: trả phản hồi cố định, ghi nhận tương tác, triển khai hành vi nhẹ hay kết nối phụ thuộc thật.

## 8. Chọn theo mục tiêu kiểm thử

| Mục tiêu | Lựa chọn thường phù hợp | Vì sao |
|---|---|---|
| Kiểm tra một nhánh xử lý khi dịch vụ trả về timeout | Stub | Dễ tạo phản hồi timeout lặp lại và kiểm soát. |
| Xác minh không gọi cổng thanh toán khi giỏ hàng không hợp lệ | Mock | Tương tác không được phép là điều cần xác minh. |
| Kiểm tra logic nghiệp vụ dùng repository có trạng thái | Fake | Có thể lưu và truy vấn dữ liệu nhẹ trong bộ nhớ. |
| Xác minh câu truy vấn và transaction trên PostgreSQL | Phụ thuộc thật | Cần hành vi của hệ quản trị cơ sở dữ liệu thực tế. |
| Xác minh cấu trúc yêu cầu gửi đến dịch vụ bên ngoài | Contract test, có thể dùng mock server hoặc môi trường thử nghiệm | Cần kiểm tra hợp đồng giao tiếp, không chỉ lời gọi nội bộ. |
| Kiểm tra xử lý lỗi khi nhà cung cấp không phản hồi | Stub hoặc mock ở unit test; môi trường mô phỏng ở integration test | Unit test cần tình huống xác định; kiểm thử tích hợp cần xác minh timeout và cấu hình mạng thực tế. |
| Xác minh thông điệp được gửi vào broker và consumer xử lý đúng | Phụ thuộc thật hoặc container ở integration test | Cần kiểm tra serialization, routing, acknowledgement và cấu hình broker. |

### 8.1. Cây quyết định đơn giản

~~~mermaid
flowchart TD
    A[Đã xác định câu hỏi kiểm thử?] --> B{Cần kiểm tra hành vi tích hợp thật?}
    B -->|Có| C[Dùng phụ thuộc thật hoặc môi trường tương đương]
    B -->|Không| D{Cần một triển khai nhẹ có trạng thái?}
    D -->|Có| E[Dùng Fake]
    D -->|Không| F{Cần xác minh tương tác/lệnh?}
    F -->|Có| G[Dùng Mock]
    F -->|Không| H{Cần điều khiển phản hồi đầu vào?}
    H -->|Có| I[Dùng Stub]
    H -->|Không| J[Xem xét dùng giá trị thật hoặc đơn giản hóa ranh giới]
~~~

Cây quyết định chỉ là gợi ý. Một bài kiểm thử có thể kết hợp nhiều cách: dùng stub cho cổng thanh toán, fake cho repository và mock cho bộ gửi thông báo. Điều quan trọng là mỗi test double có mục đích riêng và không làm mờ đối tượng đang được kiểm thử.

## 9. Ví dụ thiết kế kiểm thử cho dịch vụ đặt hàng

Giả sử OrderService thực hiện các bước: xác minh giỏ hàng, kiểm tra tồn kho, tính tổng tiền, lưu đơn hàng, yêu cầu thanh toán và gửi thông báo. Các phụ thuộc gồm:

- InventoryClient: dịch vụ kiểm tra tồn kho.
- PricingService: thành phần tính giá.
- OrderRepository: lưu và truy vấn đơn hàng.
- PaymentGateway: cổng thanh toán.
- NotificationSender: gửi xác nhận.
- Clock: cung cấp thời điểm hiện tại.

Nhóm có thể chọn như sau:

| Phụ thuộc | Cách dùng trong unit test | Cách kiểm tra tích hợp |
|---|---|---|
| InventoryClient | Stub để trả về còn hàng, hết hàng hoặc lỗi. | Sandbox hoặc dịch vụ kiểm thử để xác minh giao thức và timeout. |
| PricingService | Dùng triển khai thật nếu logic thuần và nhẹ; stub khi chỉ cần một kết quả cố định. | Kiểm tra khi quy tắc phụ thuộc dữ liệu hoặc dịch vụ khác. |
| OrderRepository | Fake để kiểm tra luồng nghiệp vụ hoặc mock khi cần xác minh một lệnh quan trọng. | Cơ sở dữ liệu thật trong container để kiểm tra query, transaction và migration. |
| PaymentGateway | Stub kết quả thành công, từ chối hoặc timeout; mock nếu cần xác minh không gọi charge. | Sandbox của nhà cung cấp hoặc môi trường mô phỏng giao thức. |
| NotificationSender | Mock để xác minh sự kiện gửi thông báo sau khi tạo đơn. | Broker/email sandbox để kiểm tra tích hợp và xử lý thông điệp. |
| Clock | Dùng Clock cố định hoặc fake để kiểm tra thời hạn, ngày và giờ. | Kiểm tra cấu hình múi giờ và đồng bộ thời gian trong môi trường phù hợp. |

Không nhất thiết mọi test đều dùng cùng cách. Ví dụ:

- Test tính tổng tiền có thể dùng PricingService thật nếu nó là logic thuần và đã được kiểm thử độc lập.
- Test xử lý timeout của thanh toán dùng stub để tạo phản hồi xác định.
- Test không được gửi thông báo khi tạo đơn thất bại dùng mock để xác minh không có tương tác gửi.
- Test lưu đơn hàng và transaction dùng PostgreSQL thật trong môi trường tích hợp.
- Test toàn bộ hành trình mua hàng dùng các dịch vụ sandbox và một số phụ thuộc thật đã kiểm soát.

## 10. Kiểm thử hợp đồng để kiểm soát sai lệch giữa fake và thật

Một rủi ro phổ biến là fake hoặc mock không phản ánh đúng hợp đồng của phụ thuộc thật. Ví dụ, fake repository có thể cho phép lưu hai bản ghi cùng ID, trong khi cơ sở dữ liệu thật có unique constraint. Unit test dùng fake vẫn đạt nhưng integration test thất bại.

**Contract test** giúp kiểm tra rằng các triển khai đáp ứng cùng một hợp đồng quan sát được. Có thể xây dựng một bộ kiểm tra dùng chung cho fake và triển khai thật:

- Lưu một đối tượng rồi truy vấn lại trả về dữ liệu tương đương.
- ID trùng xử lý theo quy tắc đã định.
- Đối tượng không tồn tại trả về kết quả phù hợp.
- Thao tác cập nhật giữ các bất biến cần thiết.
- Dữ liệu đầu vào không hợp lệ được từ chối theo hợp đồng.

Ví dụ khái quát:

~~~java
interface OrderRepositoryContract {
    OrderRepository createRepository();

    default void savesAndFindsOrder() {
        OrderRepository repository = createRepository();
        Order order = new Order("ORD-1", "CUSTOMER-7");

        repository.save(order);

        assertEquals(order, repository.findById("ORD-1").orElseThrow());
    }
}
~~~

Một bộ kiểm tra hợp đồng có thể được thực thi với InMemoryOrderRepository và một triển khai PostgreSQL. Các trường hợp phụ thuộc đặc tính riêng của cơ sở dữ liệu vẫn cần integration test chuyên biệt; contract test không thay thế mọi kiểm tra tích hợp.

## 11. Kiểm soát thời gian, dữ liệu và tính ngẫu nhiên

Một số phụ thuộc không phải dịch vụ bên ngoài nhưng vẫn làm kiểm thử khó lặp lại:

- Đồng hồ hệ thống và múi giờ.
- Số ngẫu nhiên, UUID hoặc thứ tự ngẫu nhiên.
- Hệ thống tệp và đường dẫn.
- Biến môi trường và cấu hình.
- Thread, scheduler và tác vụ bất đồng bộ.
- Dịch vụ gửi email, webhook hoặc thông báo.

Với các phụ thuộc này, có thể đưa chúng qua một interface hoặc adapter để kiểm soát trong unit test. Ví dụ, dùng Clock cố định giúp kiểm tra hạn thanh toán mà không cần chờ thời gian thực. Với hệ thống tệp, có thể dùng thư mục tạm để kiểm thử tích hợp, còn logic xử lý đường dẫn có thể kiểm tra độc lập.

Không nên giả lập thời gian hoặc luồng thực thi nếu mục tiêu chính là kiểm tra hành vi đồng bộ hóa hoặc timeout của môi trường thật. Cần có bài kiểm thử tích hợp hoặc kiểm thử chuyên biệt cho những rủi ro đó.

## 12. Các lỗi thiết kế thường gặp khi dùng test double

### 12.1. Over-mocking

Mock mọi phụ thuộc khiến test phải mô tả quá nhiều chi tiết nội bộ. Test có thể thất bại khi tái cấu trúc mà hành vi công khai không thay đổi. Nên giữ ranh giới kiểm thử ở các cộng tác viên có ý nghĩa và ưu tiên xác minh đầu ra hoặc trạng thái quan sát được.

### 12.2. Mock cả đối tượng đang kiểm thử

Nếu test thay thế chính phần logic cần xác minh, nó không còn cung cấp bằng chứng về hành vi của SUT. Chỉ thay thế cộng tác viên bên ngoài ranh giới kiểm thử, không thay thế phần cần đánh giá.

### 12.3. Stub giả định hành vi mà không có căn cứ

Nếu stub luôn trả về kết quả thành công theo giả định, test có thể bỏ qua lỗi thực tế như timeout, lỗi xác thực hoặc phản hồi không hợp lệ. Cần xác định các trạng thái quan trọng từ hợp đồng và rủi ro, sau đó tạo test tương ứng.

### 12.4. Fake quá phức tạp

Fake mô phỏng nhiều đặc tính của cơ sở dữ liệu hoặc broker có thể trở thành một hệ thống riêng. Nếu fake cần nhiều logic để mô phỏng transaction, khóa, thứ tự thông điệp hoặc retry, hãy cân nhắc chạy phụ thuộc thật trong môi trường tích hợp.

### 12.5. Chỉ dùng phụ thuộc thật cho mọi unit test

Khởi động cơ sở dữ liệu, mạng và dịch vụ ngoài cho mọi bài test làm tăng thời gian, độ phụ thuộc môi trường và khó chẩn đoán. Giữ unit test nhỏ, nhanh; dành phụ thuộc thật cho câu hỏi thực sự cần bằng chứng tích hợp.

### 12.6. Không làm sạch trạng thái

Dữ liệu còn lại từ lần chạy trước có thể khiến test đạt hoặc trượt không nhất quán. Mỗi test hoặc nhóm test cần kiểm soát dữ liệu, transaction, tài nguyên và quá trình dọn dẹp.

### 12.7. Kiểm tra chi tiết triển khai thay vì hợp đồng

Xác minh một phương thức private được gọi hoặc một chuỗi lệnh nội bộ có thể làm test dễ vỡ. Nên kiểm tra hành vi quan sát được, hợp đồng của cộng tác viên và các tác động có ý nghĩa nghiệp vụ.

## 13. Quy trình lựa chọn có thể áp dụng

1. **Xác định SUT và mục tiêu:** viết rõ hành vi hoặc rủi ro cần xác minh.
2. **Liệt kê phụ thuộc:** ghi các cộng tác viên trực tiếp, tác động bên ngoài và ranh giới hệ thống.
3. **Phân loại bằng chứng:** cần kiểm tra phản hồi, tương tác, trạng thái hay tích hợp thật?
4. **Chọn test double phù hợp:** stub cho phản hồi định trước, mock cho tương tác cần xác minh, fake cho hành vi nhẹ có trạng thái.
5. **Giữ phụ thuộc thật ở nơi cần thiết:** dùng integration test để kiểm tra giao thức, cấu hình, truy vấn, transaction và tương thích.
6. **Đánh giá độ tin cậy:** test double có thể lệch so với triển khai thật ở điểm nào? Có cần contract test không?
7. **Kiểm soát dữ liệu và môi trường:** tạo dữ liệu độc lập, dọn dẹp trạng thái và làm cho kết quả có thể lặp lại.
8. **Rà soát chi phí bảo trì:** loại bỏ mock không có ý nghĩa, fake quá phức tạp và test tích hợp trùng lặp.
9. **Cập nhật khi hợp đồng thay đổi:** khi API, schema hoặc phụ thuộc thay đổi, cập nhật cả test double, contract test và integration test liên quan.

## 14. Checklist trước khi chốt cách dùng phụ thuộc

- [ ] Đã xác định đối tượng kiểm thử và câu hỏi cần trả lời.
- [ ] Đã xác định phụ thuộc nào nằm trong ranh giới cần kiểm tra.
- [ ] Stub chỉ cung cấp phản hồi cần thiết cho nhánh xử lý.
- [ ] Mock chỉ xác minh tương tác có ý nghĩa.
- [ ] Fake có hành vi đủ dùng, đơn giản và không giả vờ mô phỏng mọi chi tiết của hệ thống thật.
- [ ] Các đặc tính của cơ sở dữ liệu, broker, API hoặc cấu hình thật được kiểm tra ở tầng tích hợp phù hợp.
- [ ] Có contract test khi cần bảo vệ sự tương thích giữa nhiều triển khai.
- [ ] Dữ liệu, thời gian, trạng thái và môi trường được kiểm soát.
- [ ] Không có test phụ thuộc chi tiết triển khai mà không tạo thêm bằng chứng.
- [ ] Chi phí chạy và bảo trì phù hợp với tần suất sử dụng của bộ kiểm thử.

## Kết luận

Hãy chọn test double theo câu hỏi cần xác minh: stub điều khiển phản hồi, mock xác minh tương tác, fake cung cấp hành vi thay thế đơn giản và phụ thuộc thật tạo bằng chứng về tích hợp thực tế. Không lựa chọn nào phù hợp cho mọi trường hợp. Kết hợp unit test, contract test và integration test giúp nhóm vừa có phản hồi nhanh, vừa kiểm tra được các ranh giới quan trọng. Mỗi lựa chọn cần được đánh giá theo độ tin cậy của bằng chứng, rủi ro bị lệch so với hệ thống thật và chi phí duy trì.
