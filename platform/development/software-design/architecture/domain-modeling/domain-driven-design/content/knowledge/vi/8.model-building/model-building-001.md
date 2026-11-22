# Chọn khái niệm phục vụ quyết định nghiệp vụ thay vì mô phỏng toàn bộ thực tế

Trong Domain-Driven Design (DDD), mô hình miền không phải bản sao thu nhỏ của thế giới thực. Nó là cách diễn đạt có chọn lọc về một phần nghiệp vụ, được tạo ra để giúp các bên hiểu vấn đề, thảo luận quy tắc và đưa ra quyết định nhất quán.

Một doanh nghiệp có vô số thông tin về khách hàng, sản phẩm, nhân viên, giao dịch, thiết bị, địa điểm và lịch sử tương tác. Phần mềm không cần lưu giữ hoặc mô tả tất cả những điều đó trong cùng một mô hình. Nó chỉ cần những khái niệm, thuộc tính, hành vi và mối quan hệ có ý nghĩa đối với trách nhiệm của Bounded Context đang xét.

Vì vậy, câu hỏi quan trọng khi xây dựng mô hình không phải là “Ngoài đời có những thứ gì?” mà là:

**“Đội nghiệp vụ cần đưa ra quyết định nào, và cần hiểu những khái niệm nào để đưa ra quyết định đó đúng đắn?”**

Tư duy này giúp mô hình giữ được trọng tâm, phản ánh đúng ngôn ngữ nghiệp vụ và tránh việc hệ thống trở thành một kho dữ liệu khổng lồ nhưng không diễn đạt rõ quy tắc kinh doanh.

## 1. Mô hình miền là sự trừu tượng có mục đích

### 1.1. Mô hình không phải bản sao của thực tế

Một mô hình là cách con người chọn ra một số khía cạnh của thực tế để mô tả, giải thích hoặc dự đoán một vấn đề. Mỗi mô hình đều có:

- **Mục đích:** mô hình được tạo ra để giải quyết câu hỏi hoặc hỗ trợ quyết định nào?
- **Phạm vi:** phần thực tế nào được xem xét?
- **Khái niệm:** những đối tượng, sự kiện, vai trò, quy tắc và quan hệ nào quan trọng?
- **Mức chi tiết:** cần biểu diễn sâu đến đâu để sử dụng được?
- **Giới hạn:** những gì mô hình không cố gắng giải thích?

Ví dụ, bản đồ giao thông thành phố tập trung vào đường, nút giao và hướng di chuyển. Nó không cần thể hiện màu sơn của mọi ngôi nhà, vị trí từng chiếc ghế trong công viên hay lịch sinh hoạt của cư dân. Những thông tin đó có thể đúng với thế giới thực nhưng không phục vụ mục đích tìm đường.

Mô hình miền cũng vậy. Một mô hình đặt hàng cần giải thích việc xác nhận đơn, tính giá, giữ hàng và hủy đơn. Nó không nhất thiết cần biết màu giao diện mà khách hàng đã nhìn thấy hoặc số lần khách di chuyển chuột trước khi bấm nút đặt hàng.

### 1.2. Mô hình tốt làm rõ quyết định

Một mô hình hữu ích giúp người sử dụng trả lời các câu hỏi nghiệp vụ một cách nhất quán:

- Đơn hàng có đủ điều kiện xác nhận không?
- Giá nào được áp dụng cho giao dịch tại thời điểm này?
- Sản phẩm có thể được giữ chỗ trong bao lâu?
- Ai có quyền chấp nhận một ngoại lệ?
- Khi một sự kiện xảy ra, trạng thái nghiệp vụ phải thay đổi thế nào?
- Nếu hai quy tắc xung đột, quy tắc nào có ưu tiên?

Nếu một khái niệm không giúp giải thích quyết định, hành vi, ràng buộc hoặc sự kiện nào trong phạm vi đang mô hình hóa, cần xem xét liệu nó có thực sự thuộc mô hình hay không.

Điều này không có nghĩa thông tin không được chọn là vô ích. Nó có thể cần cho báo cáo, phân tích, giao diện, vận hành hoặc một Bounded Context khác. Vấn đề là không nên đưa mọi nhu cầu đó vào cùng một mô hình miền chỉ vì dữ liệu có sẵn.

### 1.3. Mô hình luôn gắn với ngữ cảnh

Một khái niệm có thể được biểu diễn khác nhau trong các Bounded Context vì mỗi context giải quyết một vấn đề riêng.

Ví dụ, một người mua hàng có thể xuất hiện dưới nhiều góc nhìn:

| Context | Khái niệm được quan tâm | Thông tin có ý nghĩa |
|---|---|---|
| Customer Support | Người cần hỗ trợ | Lịch sử liên hệ, yêu cầu hỗ trợ, mức độ ưu tiên |
| Ordering | Người đặt đơn | Thông tin đặt hàng, điều kiện mua, địa chỉ nhận tại thời điểm đặt |
| Billing | Bên chịu trách nhiệm thanh toán | Thông tin xuất hóa đơn, mã số thuế, điều khoản thanh toán |
| Marketing | Đối tượng nhận chiến dịch | Sự đồng ý nhận tin, phân khúc, sở thích và hành vi tương tác |

Đó có thể là cùng một con người ngoài đời, nhưng mô hình nghiệp vụ không nhất thiết dùng chung một đối tượng Customer với tất cả thuộc tính và quy tắc. Nếu ép các context dùng một mô hình thống nhất, các yêu cầu riêng dễ xung đột và làm mờ trách nhiệm.

## 2. Bắt đầu từ quyết định và câu hỏi nghiệp vụ

### 2.1. Xác định quyết định trước khi liệt kê khái niệm

Một cách hiệu quả để chọn khái niệm là bắt đầu bằng các quyết định mà nghiệp vụ cần đưa ra.

Ví dụ trong quy trình xác nhận đơn hàng:

1. Đơn có thể được tiếp nhận không?
2. Giá cuối cùng của từng dòng hàng là bao nhiêu?
3. Hàng có thể được giữ chỗ không?
4. Thanh toán đã đạt điều kiện để xác nhận đơn chưa?
5. Đơn có cần chuyển sang xử lý thủ công không?

Với từng quyết định, hãy hỏi:

- Ai hoặc thành phần nào có trách nhiệm quyết định?
- Thời điểm quyết định là khi nào?
- Đầu vào nào ảnh hưởng đến kết quả?
- Quy tắc nào phải được áp dụng?
- Kết quả được biểu diễn ra sao?
- Quyết định có thể bị thay đổi hoặc xem xét lại không?
- Những trường hợp ngoại lệ nào cần xử lý?

Những câu hỏi này tạo ra một đường đi từ nhu cầu nghiệp vụ đến khái niệm. Thay vì bắt đầu bằng một danh sách dài các danh từ như Customer, Product, Address, Payment, Promotion, Device và Employee, đội có thể biết chính xác thông tin nào cần thiết cho từng quyết định.

### 2.2. Dùng kịch bản cụ thể để kiểm chứng

Không nên chỉ hỏi chuyên gia “Nghiệp vụ cần những dữ liệu nào?”. Câu hỏi này thường dẫn đến danh sách trường dữ liệu theo thói quen hoặc theo màn hình hiện có.

Hãy yêu cầu chuyên gia kể lại một trường hợp:

- Một đơn hàng thông thường vừa được xác nhận.
- Một đơn hàng bị từ chối vì hết hàng.
- Một đơn có giá thay đổi giữa lúc khách thêm vào giỏ và lúc thanh toán.
- Một khoản thanh toán bị treo hoặc được gửi kết quả nhiều lần.
- Một đơn cần nhân viên phê duyệt ngoại lệ.

Theo dấu từng trường hợp từ lúc bắt đầu đến khi kết thúc. Ghi lại quyết định, dữ kiện được sử dụng, quy tắc áp dụng và kết quả. Một kịch bản cụ thể thường làm lộ ra những khái niệm quan trọng mà cuộc thảo luận trừu tượng bỏ sót.

### 2.3. Phân biệt câu hỏi nghiệp vụ với yêu cầu giao diện

Các câu hỏi như “Màn hình cần hiển thị cột nào?”, “Nút nằm ở đâu?” hoặc “Có cần lưu bộ lọc gần nhất không?” thường là câu hỏi về trải nghiệm hoặc cách triển khai.

Chúng có thể quan trọng, nhưng chưa đủ để xác định mô hình miền. Hãy hỏi tiếp:

- Người dùng cần hiểu hoặc quyết định điều gì từ thông tin đó?
- Thông tin này có làm thay đổi quy tắc nghiệp vụ không?
- Nó có cần được bảo toàn để giải thích một quyết định sau này không?
- Nó thuộc trách nhiệm của context nào?

Ví dụ, màu đỏ của một nhãn trạng thái trên giao diện có thể chỉ là quy ước hiển thị. Nhưng ý nghĩa của trạng thái “Quá hạn thanh toán” và quy tắc chuyển đơn sang trạng thái đó là nội dung nghiệp vụ.

## 3. Chọn khái niệm theo vai trò trong nghiệp vụ

Không phải mọi danh từ trong cuộc trò chuyện đều cần trở thành một lớp hoặc một entity. Một khái niệm có thể là entity, value object, domain event, policy, service, vai trò hoặc chỉ là dữ liệu mô tả.

### 3.1. Entity: khái niệm cần giữ danh tính

Entity là đối tượng có danh tính liên tục trong vòng đời, ngay cả khi một số thuộc tính thay đổi.

Ví dụ:

- Order cần giữ danh tính khi địa chỉ giao hàng, trạng thái hoặc dòng hàng thay đổi.
- Customer Account cần giữ danh tính khi thông tin liên hệ hoặc thiết lập tài khoản thay đổi.
- Shipment cần giữ danh tính khi kiện hàng được bàn giao qua nhiều trạng thái.

Không nên tạo entity chỉ vì một danh từ xuất hiện trong tài liệu. Hãy hỏi:

- Nghiệp vụ có cần nhận diện cùng một đối tượng qua nhiều thời điểm không?
- Đối tượng có vòng đời và hành vi riêng không?
- Có quy tắc nào kiểm soát cách đối tượng thay đổi không?
- Những bên khác có cần tham chiếu đến đúng đối tượng này không?

Nếu câu trả lời chủ yếu là không, khái niệm đó có thể chỉ là thuộc tính hoặc value object.

### 3.2. Value Object: khái niệm được xác định bằng giá trị

Value Object mô tả một đặc điểm hoặc giá trị nghiệp vụ, thường được so sánh bằng nội dung thay vì danh tính. Nó có thể bất biến để tránh thay đổi ngoài ý muốn.

Ví dụ:

- Money gồm số tiền và loại tiền.
- DateRange gồm ngày bắt đầu và ngày kết thúc.
- ShippingAddress mô tả địa chỉ dùng cho một lần giao hàng.
- Percentage biểu diễn tỷ lệ với quy tắc giới hạn phù hợp.

Một địa chỉ giao hàng có thể được lưu như ảnh chụp tại thời điểm đặt hàng. Nếu khách thay đổi địa chỉ trong hồ sơ sau đó, địa chỉ của đơn cũ vẫn phải giữ nguyên theo quyết định đã xác nhận. Điều quan trọng là ý nghĩa của địa chỉ trong Ordering Context, không phải việc ngoài đời địa chỉ đó có thể thay đổi.

### 3.3. Domain Event: điều gì đã xảy ra?

Domain Event diễn đạt một sự kiện nghiệp vụ đã xảy ra và có ý nghĩa đối với miền.

Ví dụ:

- OrderSubmitted: khách đã gửi đơn hàng.
- OrderConfirmed: đơn hàng đã được xác nhận theo các điều kiện nghiệp vụ.
- InventoryReserved: hàng đã được giữ chỗ.
- PaymentCaptured: khoản thanh toán đã được ghi nhận.

Sự kiện giúp mô tả tiến trình và phối hợp giữa các context. Không nên tạo event cho mọi thao tác kỹ thuật như mở modal, tải lại trang hoặc ghi log, trừ khi hành động đó có ý nghĩa nghiệp vụ thực sự.

### 3.4. Policy và quy tắc nghiệp vụ

Policy diễn đạt định hướng hoặc quy tắc chi phối quyết định. Quy tắc có thể được biểu diễn bằng điều kiện, hành vi của entity/aggregate hoặc một thành phần miền phù hợp.

Ví dụ:

- Không xác nhận đơn nếu chưa giữ được hàng.
- Chỉ áp dụng mã khuyến mãi khi đơn thỏa điều kiện của chiến dịch.
- Giao dịch vượt ngưỡng cần người có thẩm quyền phê duyệt.

Khi tìm thấy một quy tắc, đừng vội biến nó thành một lớp riêng. Trước tiên cần biết ai sở hữu quy tắc, phạm vi áp dụng và những khái niệm nào cần cộng tác để thực thi nó.

### 3.5. Role và khái niệm theo vai trò

Một người hoặc tổ chức có thể đóng nhiều vai trò khác nhau tùy giao dịch.

Ví dụ, trong một đơn hàng:

- Người đặt đơn là Buyer.
- Người nhận hàng là Recipient.
- Bên thanh toán là Payer.
- Bên xuất hóa đơn là Invoice Recipient.

Các vai trò này có thể là cùng một người hoặc nhiều người khác nhau. Nếu mô hình chỉ có một trường Customer và giả định người mua luôn là người nhận, nó sẽ không thể diễn tả các trường hợp mua tặng hoặc công ty đặt hàng cho nhân viên.

Hãy tạo khái niệm vai trò khi sự khác biệt đó ảnh hưởng đến quyết định hoặc trách nhiệm. Không cần tách một lớp cho mọi danh xưng nếu nghiệp vụ không có hành vi hay quy tắc riêng.

## 4. Chọn thuộc tính và quan hệ có ý nghĩa

Sau khi xác định khái niệm, hãy chọn thuộc tính và mối quan hệ phục vụ các câu hỏi đã nêu.

### 4.1. Thuộc tính cần có lý do nghiệp vụ

Với mỗi thuộc tính, hãy hỏi:

- Quyết định nào sử dụng thuộc tính này?
- Nó được xác định tại thời điểm nào?
- Ai là nguồn đáng tin cậy của giá trị?
- Giá trị có thể thay đổi không?
- Nếu thay đổi, có cần lưu lịch sử không?
- Có cần phân biệt giá trị chưa biết, không áp dụng và giá trị rỗng không?
- Thuộc tính này có thuộc context đang xét không?

Ví dụ, Ordering có thể cần:

| Thuộc tính | Lý do nghiệp vụ |
|---|---|
| OrderId | Nhận diện đơn trong suốt vòng đời |
| BuyerId | Xác định bên đặt đơn |
| RecipientAddress | Xác định nơi giao hàng đã được chốt |
| Currency | Diễn giải các giá trị tiền |
| UnitPrice | Bảo toàn đơn giá đã áp dụng khi đặt |
| Quantity | Tính số lượng và tổng giá trị dòng hàng |
| SubmittedAt | Xác định thời điểm gửi đơn |
| Status | Theo dõi tiến trình và quyết định tiếp theo |

Các thông tin như màu ảnh đại diện, trình duyệt khách dùng hoặc số lần cuộn trang có thể cần cho Analytics hoặc UX, nhưng không nhất thiết thuộc mô hình miền Ordering.

### 4.2. Quan hệ phải diễn đạt được ý nghĩa

Một quan hệ không nên được tạo chỉ vì hai bảng có khóa ngoại hoặc hai đối tượng cùng xuất hiện trong một màn hình.

Hãy diễn đạt quan hệ bằng câu nghiệp vụ:

- Một Order gồm một hoặc nhiều Order Line.
- Một Order được đặt bởi một Buyer.
- Một Shipment có thể vận chuyển hàng từ một hoặc nhiều đơn, tùy chính sách giao nhận.
- Một Payment Transaction được thực hiện để thanh toán cho một nghĩa vụ cụ thể.

Sau đó kiểm tra:

- Quan hệ có đúng trong mọi trường hợp không?
- Có quan hệ một-nhiều hoặc nhiều-nhiều không?
- Quan hệ có thay đổi theo thời gian không?
- Có cần lưu ảnh chụp hoặc lịch sử không?
- Ai sở hữu vòng đời của mỗi bên?

### 4.3. Không mặc định mọi dữ liệu liên quan phải nằm trong một aggregate

Một mô hình khái niệm có thể có nhiều quan hệ, nhưng điều đó không có nghĩa mọi đối tượng phải được tải, lưu hoặc thay đổi trong một transaction duy nhất.

Ví dụ, Order có thể tham chiếu BuyerId và ProductId, nhưng không nhất thiết chứa toàn bộ hồ sơ khách hàng và danh mục sản phẩm. Ordering chỉ cần dữ liệu hoặc ảnh chụp cần thiết để thực thi quy tắc đặt hàng.

Ranh giới aggregate và cách tham chiếu là quyết định thiết kế chiến thuật tiếp theo, dựa trên invariant và vòng đời. Hãy tránh để sơ đồ khái niệm biến thành một đồ thị đối tượng khổng lồ.

## 5. Ví dụ xuyên suốt: mô hình hóa quyết định xác nhận đơn hàng

Giả sử một cửa hàng trực tuyến muốn xác định khi nào một đơn hàng có thể được xác nhận.

### 5.1. Mô tả quyết định

Đơn hàng chỉ được xác nhận khi:

- Thông tin dòng hàng hợp lệ.
- Giá được chấp nhận tại thời điểm gửi đơn.
- Hàng đã được giữ chỗ thành công.
- Điều kiện thanh toán của đơn được đáp ứng.
- Không có quy tắc chặn hoặc yêu cầu phê duyệt chưa hoàn tất.

Đây là phạm vi nghiệp vụ cần mô hình hóa. Nhóm không bắt đầu bằng việc đưa tất cả thông tin có thể thu thập về người mua và sản phẩm vào một lớp lớn.

### 5.2. Chọn khái niệm

| Khái niệm | Vai trò trong quyết định | Có thuộc mô hình Ordering? |
|---|---|---|
| Order | Đối tượng có vòng đời cần xác nhận hoặc từ chối | Có |
| Order Line | Dòng hàng với sản phẩm, số lượng và giá đã chốt | Có |
| Money | Giá trị tiền có số tiền và loại tiền | Có |
| Buyer Reference | Tham chiếu đến người đặt đơn | Có, ở mức thông tin cần thiết |
| Recipient Address | Địa chỉ giao đã chọn cho đơn | Có |
| Inventory Reservation | Kết quả giữ chỗ do Inventory sở hữu | Có thể biểu diễn bằng tham chiếu/kết quả; không sở hữu toàn bộ tồn kho |
| Payment Authorization | Kết quả thanh toán liên quan đến điều kiện xác nhận | Có thể tham chiếu kết quả từ Payment Context |
| Avatar URL | Ảnh đại diện người mua | Không cần cho quyết định xác nhận đơn |
| Browser Theme | Chủ đề giao diện khách sử dụng | Không cần cho quyết định xác nhận đơn |
| Warehouse Bin Layout | Cách sắp xếp vị trí trong kho | Thuộc Inventory/Warehouse, không thuộc Ordering |

Việc một khái niệm không nằm trong mô hình Ordering không có nghĩa phải xóa dữ liệu đó khỏi hệ thống. Nó có thể thuộc context khác với trách nhiệm và quy tắc riêng.

### 5.3. Diễn đạt hành vi thay vì chỉ lưu trạng thái

Một mô hình chỉ có các trường như OrderId, Status và TotalAmount sẽ khó giải thích vì sao đơn được xác nhận hoặc bị từ chối. Cần diễn đạt hành vi và điều kiện. Đoạn mã giả theo phong cách Java dưới đây tập trung vào ý nghĩa nghiệp vụ, lược bỏ các kiểu dữ liệu và phần khởi tạo để dễ theo dõi.

~~~text
public final class Order {
    private final OrderId id;
    private final List<OrderLine> lines;
    private final Money total;
    private OrderStatus status;
    private final Address deliveryAddress;

    public void confirm(ConfirmationEvidence evidence) {
        if (status != OrderStatus.SUBMITTED) {
            throw new IllegalStateException(
                "Only submitted orders can be confirmed"
            );
        }
        if (!evidence.inventoryReserved()) {
            throw new IllegalStateException(
                "Inventory must be reserved before confirmation"
            );
        }
        if (!evidence.paymentRequirementSatisfied()) {
            throw new IllegalStateException(
                "Payment requirement is not satisfied"
            );
        }
        status = OrderStatus.CONFIRMED;
    }
}
~~~

Đoạn mã chỉ minh họa rằng mô hình nên thể hiện quyết định và điều kiện nghiệp vụ. Trong hệ thống thực, cách phối hợp với Inventory và Payment, xử lý lỗi, transaction và aggregate boundary cần được thiết kế riêng. Không nên gọi trực tiếp các hệ thống bên ngoài bên trong entity chỉ để làm ví dụ trông đầy đủ.

### 5.4. Nhận diện phần thuộc context khác

Ordering cần kết quả giữ chỗ và kết quả thanh toán, nhưng Inventory mới sở hữu số lượng vật lý, vị trí kho và quy tắc giữ chỗ. Payment Context sở hữu giao dịch, trạng thái ủy quyền và hoàn tiền.

Ordering có thể nhận bằng chứng hoặc tham chiếu từ các context đó, sau đó áp dụng quy tắc xác nhận đơn của mình. Điều này giữ cho mô hình tập trung vào trách nhiệm riêng.

### 5.5. Kiểm tra bằng trường hợp biên

Hãy dùng các tình huống để kiểm tra mô hình:

| Tình huống | Câu hỏi cần mô hình trả lời |
|---|---|
| Đơn có nhiều dòng hàng, một dòng hết hàng | Có cho xác nhận một phần hay từ chối toàn bộ? |
| Giá thay đổi sau khi khách gửi đơn | Giá nào được giữ và ai có quyền thay đổi? |
| Thanh toán được gửi kết quả hai lần | Làm sao tránh xác nhận hoặc ghi nhận thanh toán lặp? |
| Địa chỉ trong hồ sơ khách thay đổi | Đơn đã gửi dùng địa chỉ cũ hay địa chỉ mới? |
| Khách mua tặng người khác | Buyer và Recipient được phân biệt thế nào? |
| Giữ chỗ tồn kho hết hạn trước khi xác nhận | Đơn phải được thử lại, chờ hay từ chối? |

Nếu mô hình không trả lời được, có thể đang thiếu một khái niệm, quy tắc hoặc sự phân biệt quan trọng. Nếu mô hình phải chứa nhiều thông tin không liên quan mới trả lời được, phạm vi có thể đang quá rộng.

## 6. Một quy trình thực tế để chọn khái niệm

### Bước 1: Chốt ngữ cảnh và trách nhiệm

Xác định Bounded Context đang mô hình hóa, mục tiêu nghiệp vụ, người sử dụng mô hình và trách nhiệm context phải đảm nhận. Viết rõ những phần nằm ngoài phạm vi.

### Bước 2: Thu thập quyết định và kịch bản

Liệt kê các quyết định quan trọng, trường hợp bình thường, ngoại lệ và sự kiện làm thay đổi tiến trình. Ưu tiên các tình huống có ảnh hưởng lớn đến khách hàng, tài chính, tuân thủ hoặc vận hành.

### Bước 3: Tìm các khái niệm ứng viên

Đọc lời kể và hồ sơ nghiệp vụ để tìm:

- Đối tượng có danh tính và vòng đời.
- Giá trị hoặc đặc điểm cần được xác định nhất quán.
- Vai trò của người hoặc tổ chức.
- Sự kiện có ý nghĩa nghiệp vụ.
- Quy tắc và chính sách.
- Quan hệ và phụ thuộc giữa các khái niệm.

Đây là danh sách ứng viên, chưa phải danh sách lớp sẽ triển khai.

### Bước 4: Kiểm tra từng khái niệm bằng câu hỏi quyết định

Với mỗi ứng viên, ghi rõ quyết định nào sử dụng nó, hành vi hoặc quy tắc nào cần nó và điều gì sẽ sai nếu bỏ nó. Nếu không tìm được lý do cụ thể, hãy để nó ở ngoài mô hình hiện tại hoặc đánh dấu cần xác minh.

### Bước 5: Làm rõ ý nghĩa và phân biệt thuật ngữ

Thảo luận với chuyên gia nghiệp vụ để xác định định nghĩa, ví dụ, phản ví dụ, phạm vi và cách dùng thuật ngữ. Nếu hai từ khác nhau có cùng ý nghĩa trong context, cân nhắc thống nhất. Nếu một từ có nhiều nghĩa, cân nhắc dùng tên cụ thể hơn.

### Bước 6: Xác định thuộc tính, hành vi và invariant

Mô tả điều gì có thể thay đổi, điều gì phải luôn đúng, ai có quyền thực hiện hành động và sự kiện nào được phát sinh. Ưu tiên diễn đạt quy tắc thành hành vi nghiệp vụ có tên rõ ràng.

### Bước 7: Kiểm tra ranh giới với context khác

Xác định dữ liệu nào do context khác sở hữu, mô hình nào được trao đổi qua hợp đồng và phần nào cần chuyển đổi. Không sao chép toàn bộ mô hình của upstream chỉ vì downstream cần một vài giá trị.

### Bước 8: Thử mô hình bằng ví dụ và phản ví dụ

Dùng kịch bản thật, trường hợp biên và thay đổi chính sách để xem mô hình có giải thích được quyết định không. Khi có điểm không phù hợp, sửa khái niệm hoặc định nghĩa trước khi thêm các trường dữ liệu mới.

### Bước 9: Giữ mô hình ở mức vừa đủ và lặp lại

Mô hình miền phát triển qua nhiều vòng khám phá và phản hồi. Chỉ bổ sung độ chi tiết khi có nhu cầu nghiệp vụ rõ ràng. Ghi nhận các giả định chưa xác minh và quay lại khi có bằng chứng mới.

~~~mermaid
flowchart TD
    A["Xác định Bounded Context và trách nhiệm"] --> B["Liệt kê quyết định nghiệp vụ"]
    B --> C["Thu thập kịch bản và ngoại lệ"]
    C --> D["Đề xuất khái niệm ứng viên"]
    D --> E["Kiểm tra khái niệm có hỗ trợ quyết định không"]
    E --> F["Định nghĩa ngôn ngữ, thuộc tính, hành vi và quy tắc"]
    F --> G["Kiểm tra ranh giới với context khác"]
    G --> H["Thử bằng ví dụ và phản ví dụ"]
    H --> I{"Mô hình giải thích đúng nghiệp vụ?"}
    I -->|Chưa| D
    I -->|Rồi| J["Ghi nhận mô hình hiện tại và tiếp tục học"]
~~~

## 7. Những gì nên để ngoài mô hình miền

Một số loại thông tin thường bị đưa vào mô hình vì dễ thu thập hoặc đã có sẵn trong cơ sở dữ liệu.

### Chi tiết chỉ phục vụ giao diện

Màu sắc, vị trí nút, trạng thái mở rộng của panel hoặc kích thước ảnh thường thuộc lớp trình bày. Chỉ đưa vào mô hình miền khi có ý nghĩa nghiệp vụ, chẳng hạn lựa chọn ngôn ngữ trong hợp đồng hoặc phương thức liên hệ được khách hàng chấp thuận.

### Chi tiết kỹ thuật và hạ tầng

Tên máy chủ, địa chỉ IP, số lần retry, tên queue hoặc ID trace thường thuộc mô hình kỹ thuật. Chúng có thể được ghi log và theo dõi vận hành mà không trở thành khái niệm miền.

### Dữ liệu phân tích không tham gia quyết định

Một số chỉ số như số lần xem trang, thời gian cuộn hoặc nguồn truy cập có thể rất hữu ích cho Analytics. Nhưng nếu Ordering không dùng chúng để thực thi quy tắc đặt hàng, chúng không cần nằm trong mô hình Ordering.

### Thông tin thuộc trách nhiệm của context khác

Ordering có thể cần kết quả thanh toán, nhưng không cần quản lý toàn bộ vòng đời của thẻ hoặc tài khoản ngân hàng. Customer Support có thể cần mã đơn, nhưng không cần sở hữu quy tắc định giá.

### Dữ liệu dự phòng chưa có mục đích

Trường “miscellaneous”, “extraData” hoặc một túi thuộc tính tự do có thể che giấu việc chưa hiểu rõ nghiệp vụ. Nếu dữ liệu thực sự cần thiết, hãy xác định ý nghĩa, người sở hữu và quy tắc sử dụng. Nếu chưa biết dùng để làm gì, ghi nhận như giả định thay vì đưa nó thành trung tâm của mô hình.

Một dữ liệu bị loại khỏi mô hình miền vẫn có thể được lưu ở nơi khác theo yêu cầu pháp lý, kiểm toán, phân tích hoặc vận hành. Quyết định không đưa nó vào mô hình chỉ giới hạn phạm vi khái niệm và quy tắc của context.

## 8. Những dấu hiệu mô hình đang quá rộng hoặc quá hẹp

### Mô hình quá rộng

- Một entity có hàng chục thuộc tính không phục vụ cùng một quyết định.
- Một lớp cố đại diện cho cùng khái niệm ở nhiều Bounded Context.
- Thay đổi một quy tắc nhỏ buộc nhiều nhóm sửa mô hình không liên quan.
- Mô hình chứa nhiều trạng thái hoặc trường chỉ để phục vụ giao diện và báo cáo.
- Người đọc không thể giải thích trách nhiệm chính của một khái niệm.

Khi gặp những dấu hiệu này, hãy xem lại phạm vi context, phân biệt các vai trò và tách những khái niệm có ngữ nghĩa khác nhau.

### Mô hình quá hẹp

- Quy tắc quan trọng nằm rải rác trong controller hoặc script mà mô hình không thể hiện.
- Các quyết định được thực hiện bằng điều kiện lặp lại ở nhiều nơi.
- Không thể giải thích vì sao một trạng thái được chuyển đổi.
- Các trường hợp ngoại lệ phải dựa vào ghi chú hoặc thao tác thủ công không được mô hình hóa.
- Chuyên gia nghiệp vụ không nhận ra thuật ngữ của họ trong mô hình.

Khi đó, hãy tìm hành vi, invariant, policy hoặc khái niệm đang bị bỏ sót. Đừng chỉ thêm trường dữ liệu; có thể điều còn thiếu là quy tắc hoặc ý nghĩa.

## 9. Mối liên hệ với Tactical Design

Việc chọn khái niệm theo quyết định nghiệp vụ tạo nền tảng cho các lựa chọn tactical design:

- **Entity:** khi nghiệp vụ cần danh tính và vòng đời liên tục.
- **Value Object:** khi giá trị và các thuộc tính của nó xác định ý nghĩa, thường không cần danh tính riêng.
- **Aggregate:** khi cần xác định ranh giới bảo vệ các invariant và điều phối thay đổi nhất quán.
- **Repository:** khi cần truy xuất và lưu aggregate theo ngôn ngữ miền.
- **Domain Event:** khi một sự kiện đã xảy ra có ý nghĩa với nghiệp vụ hoặc các context khác.
- **Domain Service:** khi một hành vi nghiệp vụ có ý nghĩa nhưng không tự nhiên thuộc về một entity hay value object cụ thể.

Không nên bắt đầu bằng việc chọn mẫu thiết kế rồi ép nghiệp vụ vào đó. Trước tiên cần hiểu quyết định, khái niệm và quy tắc. Sau đó mới chọn cách biểu diễn phù hợp.

Ví dụ, nếu một quy tắc yêu cầu tổng giá trị đơn hàng không được vượt quá hạn mức tín dụng, cần xác định:

- Hạn mức được sở hữu bởi context nào?
- Giá trị đơn hàng được tính theo loại tiền và thời điểm nào?
- Quyết định kiểm tra hạn mức thuộc trách nhiệm của aggregate nào hoặc dịch vụ miền nào?
- Có cần giữ chỗ hạn mức hay chỉ kiểm tra tại thời điểm gửi?
- Sự kiện nào được phát ra khi hạn mức được chấp nhận hoặc từ chối?

Chỉ sau khi trả lời các câu hỏi này mới có thể quyết định ranh giới aggregate, cách tham chiếu và cơ chế phối hợp.

## 10. Những sai lầm thường gặp

**Mô hình hóa thế giới thực một cách đầy đủ.** Mọi thông tin được xem là có thể hữu ích nên được thêm vào, khiến mô hình khó hiểu và khó thay đổi. Hãy quay lại quyết định và trách nhiệm của context.

**Biến mọi danh từ thành entity.** Một thuộc tính, vai trò hoặc value object bị biến thành entity sẽ kéo theo danh tính, vòng đời và quan hệ không cần thiết. Hãy xác định nghiệp vụ có thực sự cần theo dõi nó độc lập không.

**Bắt đầu từ schema cơ sở dữ liệu.** Cấu trúc bảng phản ánh cách lưu trữ hiện tại, không nhất thiết phản ánh ngôn ngữ và quy tắc nghiệp vụ. Hãy khám phá quyết định trước rồi mới thiết kế persistence.

**Dùng một mô hình Customer hoặc Product cho mọi nơi.** Cùng tên không có nghĩa cùng trách nhiệm. Hãy giữ mô hình phù hợp với Bounded Context và chuyển đổi qua hợp đồng khi cần.

**Chỉ mô hình hóa dữ liệu mà bỏ qua hành vi.** Một tập hợp trường và quan hệ không giải thích được quyết định. Hãy đưa quy tắc, invariant, hành vi và sự kiện vào mô hình.

**Đưa chi tiết giao diện vào miền.** Thông tin hiển thị thường thay đổi theo trải nghiệm người dùng và không nên chi phối mô hình nghiệp vụ nếu không có ý nghĩa miền.

**Thiết kế quá sớm khi chưa có ví dụ.** Thuật ngữ có thể nghe hợp lý nhưng không xử lý được ngoại lệ thực tế. Hãy kiểm tra bằng hồ sơ và tình huống cụ thể.

**Coi mô hình là cố định sau khi viết tài liệu.** Hiểu biết nghiệp vụ luôn được bổ sung. Hãy xem mô hình là kết quả hiện tại của quá trình học và điều chỉnh khi có bằng chứng mới.

## 11. Mẫu thực hành chọn khái niệm

Có thể sử dụng mẫu sau trong buổi Event Storming, phỏng vấn chuyên gia hoặc phiên làm rõ mô hình:

~~~text
BOUNDED CONTEXT
- Tên context:
- Mục đích và trách nhiệm:
- Những gì nằm ngoài phạm vi:

QUYẾT ĐỊNH NGHIỆP VỤ
- Quyết định cần đưa ra:
- Ai chịu trách nhiệm:
- Thời điểm quyết định:
- Kết quả hợp lệ:

KỊCH BẢN
- Trường hợp thông thường:
- Trường hợp ngoại lệ:
- Sự kiện làm thay đổi tiến trình:

KHÁI NIỆM ỨNG VIÊN
- Tên khái niệm:
- Định nghĩa trong context:
- Vai trò đối với quyết định:
- Hành vi hoặc quy tắc liên quan:
- Thuộc tính cần thiết:
- Nguồn dữ liệu / context sở hữu:

KIỂM TRA PHẠM VI
- Nếu bỏ khái niệm này, quyết định nào không thể thực hiện đúng?
- Có thông tin nào đang được đưa vào nhưng không phục vụ quyết định?
- Có khái niệm nào thực chất thuộc context khác?
- Có thuật ngữ nào đang bị dùng với nhiều nghĩa?

GIẢ ĐỊNH VÀ VIỆC CẦN XÁC MINH
- Giả định:
- Bằng chứng còn thiếu:
- Người xác nhận:
- Ngày xem xét lại:
~~~

Ví dụ ghi một khái niệm:

| Trường | Nội dung |
|---|---|
| Context | Ordering |
| Quyết định | Đơn có thể được xác nhận không? |
| Khái niệm | Order |
| Định nghĩa | Yêu cầu mua hàng được gửi và quản lý trong suốt tiến trình xác nhận, thực hiện hoặc hủy |
| Vai trò | Giữ các dòng hàng, giá đã chốt, bên đặt, địa chỉ giao và trạng thái nghiệp vụ |
| Hành vi | Submit, Confirm, Reject, Cancel |
| Quy tắc | Chỉ xác nhận khi các điều kiện hàng hóa và thanh toán được đáp ứng |
| Không bao gồm | Vòng đời giao dịch thanh toán và vị trí tồn kho vật lý |

## 12. Tiêu chí tự kiểm tra

Trước khi chuyển mô hình sang thiết kế chiến thuật hoặc triển khai, hãy tự hỏi:

- Mục đích và Bounded Context của mô hình đã rõ chưa?
- Mô hình được bắt đầu từ quyết định và kịch bản nghiệp vụ cụ thể chưa?
- Mỗi khái niệm có định nghĩa rõ trong ngữ cảnh đang xét không?
- Có phân biệt entity, value object, role, event và policy theo ý nghĩa nghiệp vụ không?
- Mỗi thuộc tính có quyết định hoặc quy tắc sử dụng cụ thể không?
- Các quan hệ có diễn đạt đúng trách nhiệm và vòng đời không?
- Những invariant và hành vi quan trọng đã được thể hiện chưa?
- Dữ liệu thuộc context khác có được tham chiếu hoặc chuyển đổi qua ranh giới phù hợp không?
- Có thông tin giao diện, hạ tầng hoặc phân tích đang làm mô hình mất trọng tâm không?
- Mô hình có giải thích được trường hợp thông thường, ngoại lệ và thay đổi chính sách không?
- Chuyên gia nghiệp vụ có hiểu và xác nhận được thuật ngữ, hành vi trong mô hình không?
- Các giả định và điểm chưa chắc chắn có được ghi nhận không?

Một mô hình miền tốt không cố chứa mọi điều đúng về thế giới. Nó chọn đúng những điều cần thiết để diễn đạt nghiệp vụ, bảo vệ quyết định và giúp các bên cộng tác bằng một ngôn ngữ rõ ràng. Khi mỗi khái niệm đều có lý do tồn tại trong Bounded Context, mô hình sẽ dễ hiểu hơn, tập trung hơn và có khả năng thay đổi cùng hiểu biết nghiệp vụ.
