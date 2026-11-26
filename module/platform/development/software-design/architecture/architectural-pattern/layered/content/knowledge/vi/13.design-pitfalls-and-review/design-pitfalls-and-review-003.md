# Phân biệt mô hình miền thiếu hành vi với mô hình đơn giản có chủ đích

Bài học này thuộc module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, trong chương **Sai lầm và đánh giá thiết kế**. Module hướng tới cách tổ chức phần mềm theo kiến trúc phân tầng: presentation tiếp nhận yêu cầu, application điều phối ca sử dụng, business/domain biểu diễn quy tắc và data access/infrastructure làm việc với nơi lưu trữ hoặc hệ thống bên ngoài. Trọng tâm ở đây là đánh giá một mô hình miền đang thiếu hành vi hay đang được giữ đơn giản một cách hợp lý.

Một mô hình miền thiếu hành vi (anemic domain model) thường chỉ chứa dữ liệu và getter/setter; các quy tắc nghiệp vụ lại nằm rải rác trong các service hoặc lớp điều phối. Tuy nhiên, mô hình dữ liệu đơn giản không tự động là thiết kế kém. Với ứng dụng CRUD ít quy tắc, một entity đơn giản cùng application service có thể là lựa chọn rõ ràng và tiết kiệm. Cần đánh giá dựa trên độ phức tạp nghiệp vụ, bất biến cần bảo vệ và chi phí thay đổi, không dựa trên số lượng phương thức hay việc có áp dụng đầy đủ DDD hay không.

## 1. Hai tình huống dễ bị nhầm lẫn

### 1.1. Mô hình miền thiếu hành vi

Trong mô hình thiếu hành vi, đối tượng nghiệp vụ chủ yếu là nơi chứa dữ liệu. Nó cho phép bên ngoài đọc, thay đổi trường và tự quyết định trạng thái. Các quy tắc quan trọng được thực hiện ở service khác, đôi khi lặp lại ở nhiều nơi.

Ví dụ, `Order` chỉ có các thuộc tính và setter:

```java
public class Order {
    private OrderStatus status;
    private BigDecimal total;

    public OrderStatus getStatus() {
        return status;
    }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }
}
```

Một service bên ngoài tự tính tổng, tự kiểm tra trạng thái và tự gán kết quả:

```java
public void confirm(Order order) {
    if (order.getStatus() != OrderStatus.DRAFT) {
        throw new IllegalStateException("Đơn hàng không ở trạng thái nháp");
    }

    BigDecimal total = calculateTotal(order);
    if (total.signum() <= 0) {
        throw new IllegalArgumentException("Tổng tiền không hợp lệ");
    }

    order.setTotal(total);
    order.setStatus(OrderStatus.CONFIRMED);
}
```

Nếu có nhiều service cùng thay đổi đơn hàng, mỗi service có thể tự viết một phần kiểm tra. Một luồng quên kiểm tra trạng thái, luồng khác tính tổng theo cách khác. Đối tượng không tự bảo vệ được các điều kiện mà nó phải luôn thỏa mãn.

### 1.2. Mô hình đơn giản có chủ đích

Trong một ứng dụng quản lý danh mục nội bộ, một bản ghi có thể chỉ gồm mã, tên hiển thị và thời điểm cập nhật. Không có quy tắc chuyển trạng thái phức tạp, không có phép tính nghiệp vụ hoặc bất biến liên quan nhiều trường. Application service có thể thực hiện CRUD và repository lưu entity đơn giản.

Ví dụ:

```java
@Entity
class CategoryEntity {
    @Id
    private UUID id;

    private String name;

    private boolean active;
}
```

Nếu ca sử dụng chỉ tạo, đổi tên, bật hoặc tắt danh mục theo quyền truy cập đã được application kiểm tra, việc thêm aggregate, factory, domain service và nhiều lớp mapper có thể không đem lại lợi ích tương xứng.

Mô hình đơn giản có chủ đích vẫn cần các quy tắc cần thiết. Ví dụ, tên danh mục không được để trống hoặc mã phải duy nhất. Những điều kiện này có thể được bảo vệ bằng validation, application service và ràng buộc database ở mức phù hợp. Không nhất thiết phải tạo một mô hình domain giàu hành vi cho mọi bảng.

Điểm phân biệt cốt lõi là: mô hình thiếu hành vi làm các quy tắc quan trọng bị phân tán và khó bảo vệ; mô hình đơn giản có chủ đích phản ánh đúng một miền ít quy tắc, với trách nhiệm được đặt rõ ở nơi phù hợp.

## 2. Dấu hiệu mô hình miền đang thiếu hành vi

Không nên kết luận chỉ vì một class có nhiều getter/setter. Hãy xem xét cách hệ thống thực hiện các quy tắc.

### 2.1. Quy tắc cùng một khái niệm bị lặp ở nhiều nơi

Ví dụ, nhiều service đều tự kiểm tra `status == DRAFT` trước khi xác nhận đơn hàng. Khi quy tắc thay đổi để cho phép một trạng thái khác, nhóm phải tìm và sửa nhiều nơi. Một luồng có thể bị bỏ sót.

### 2.2. Đối tượng có thể đi vào trạng thái không hợp lệ

Nếu bất kỳ caller nào cũng có thể gọi `setStatus(CONFIRMED)`, hệ thống có thể xác nhận một đơn hàng rỗng, chưa tính tiền hoặc đã bị hủy. Nếu đối tượng phải luôn thỏa mãn một số điều kiện, constructor và phương thức thay đổi trạng thái nên bảo vệ các điều kiện đó.

### 2.3. Service chứa quá nhiều quyết định nghiệp vụ

Một application service có thể điều phối nhiều bước, nhưng nếu nó tự tính giá, áp dụng chiết khấu, quyết định chuyển trạng thái, kiểm tra giới hạn và thay đổi từng trường của nhiều đối tượng, phần nghiệp vụ đang bị kéo ra khỏi mô hình.

Tên như `OrderManager`, `OrderHelper` hoặc `OrderService` không nói rõ trách nhiệm. Điều đáng xem là service đang điều phối ca sử dụng hay đang trở thành nơi chứa toàn bộ quy tắc của domain.

### 2.4. Cùng một quy tắc cho kết quả khác nhau giữa các luồng

Nếu API, tác vụ nền và message consumer đều có cách tính phí riêng, kết quả có thể không nhất quán. Một quy tắc dùng chung nên được đặt tại mô hình hoặc chính sách nghiệp vụ mà các luồng có thể gọi.

### 2.5. Kiểm thử quy tắc phải khởi động quá nhiều hạ tầng

Nếu muốn kiểm tra “đơn hàng không được xác nhận khi thiếu dòng hàng” mà phải khởi động Spring, mock nhiều repository và tạo database, có thể quy tắc đang bị gắn vào application/infrastructure quá chặt. Một bất biến thuần nghiệp vụ thường có thể được kiểm thử trực tiếp trên đối tượng domain.

Các dấu hiệu này nên được xem xét cùng nhau. Một service dài có thể là dấu hiệu trách nhiệm chưa rõ, nhưng không phải bằng chứng duy nhất. Một ứng dụng CRUD có service điều phối đơn giản không nhất thiết cần tái cấu trúc.

## 3. Ví dụ chuyển quy tắc về mô hình miền

Giả sử hệ thống bán hàng có các quy tắc:

- Đơn hàng phải có ít nhất một dòng hợp lệ.
- Số lượng mỗi dòng phải lớn hơn không.
- Chỉ đơn hàng ở trạng thái nháp mới được xác nhận.
- Tổng tiền được tính từ các dòng hàng và không được sửa tùy ý từ bên ngoài.

Thay vì để service tự sửa từng trường, có thể để domain model sở hữu hành vi:

```java
public final class Order {
    private final OrderId id;
    private final List<OrderLine> lines;
    private OrderStatus status;

    private Order(OrderId id, List<OrderLine> lines) {
        if (lines == null || lines.isEmpty()) {
            throw new InvalidOrderException(
                    "Đơn hàng phải có ít nhất một dòng");
        }
        this.id = id;
        this.lines = new ArrayList<>(lines);
        this.status = OrderStatus.DRAFT;
    }

    public static Order draft(
            OrderId id,
            List<OrderLine> lines) {
        return new Order(id, lines);
    }

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new InvalidOrderStateException(
                    "Chỉ đơn hàng nháp mới được xác nhận");
        }
        status = OrderStatus.CONFIRMED;
    }

    public OrderId id() {
        return id;
    }

    public OrderStatus status() {
        return status;
    }

    public Money total() {
        return lines.stream()
                .map(OrderLine::subtotal)
                .reduce(Money.zero(), Money::add);
    }
}
```

`OrderLine` có thể tự bảo vệ số lượng và tính thành tiền:

```java
public record OrderLine(
        ProductId productId,
        int quantity,
        Money unitPrice) {

    public OrderLine {
        Objects.requireNonNull(productId);
        Objects.requireNonNull(unitPrice);

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Số lượng phải lớn hơn không");
        }
    }

    public Money subtotal() {
        return unitPrice.multiply(quantity);
    }
}
```

Application service vẫn tồn tại và vẫn có vai trò quan trọng. Nó tải dữ liệu cần thiết, gọi domain, lưu kết quả và xác định ranh giới giao dịch:

```java
@Service
class ConfirmOrderService {
    private final OrderRepository orderRepository;

    ConfirmOrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void confirm(OrderId id) {
        Order order = orderRepository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));

        order.confirm();

        orderRepository.save(order);
    }
}
```

Trong thiết kế này:

- Domain bảo vệ trạng thái và quy tắc của đơn hàng.
- Application service điều phối việc tải, gọi hành vi và lưu.
- Repository chịu trách nhiệm truy cập dữ liệu.
- Controller chuyển giao thức HTTP thành lời gọi ca sử dụng.

Mô hình domain không cần biết Spring MVC, JSON, tên bảng hoặc annotation ORM nếu nhóm muốn cô lập các chi tiết đó. Tuy vậy, có thể dùng JPA entity trực tiếp làm mô hình nghiệp vụ trong một ứng dụng đơn giản nếu các yêu cầu và vòng đời dữ liệu phù hợp. Việc tách entity và domain object là quyết định dựa trên lợi ích thực tế, không phải điều kiện để có hành vi nghiệp vụ.

## 4. Không biến mọi logic thành phương thức của entity

Chuyển quy tắc về domain không có nghĩa mọi dòng code đều phải nằm trong một entity. Cần phân biệt một số trách nhiệm:

| Loại trách nhiệm | Vị trí thường phù hợp | Ví dụ |
|---|---|---|
| Bất biến của một đối tượng | Entity hoặc value object | Số lượng dòng hàng phải dương |
| Quy tắc chuyển trạng thái | Entity/aggregate | Chỉ đơn nháp mới được xác nhận |
| Quy tắc dùng dữ liệu của nhiều đối tượng | Domain service hoặc chính sách domain | Tính điều kiện đủ tư cách thành viên |
| Điều phối ca sử dụng | Application service | Tải đơn, kiểm tra quyền, lưu và phát lệnh |
| Truy cập hệ thống bên ngoài | Adapter/infrastructure | Đọc database, gọi dịch vụ vận chuyển |
| Chuyển đổi hợp đồng | Mapper tại biên | Request DTO thành command |

Ví dụ, chính sách chiết khấu có thể cần loại khách hàng, tổng tiền và chương trình khuyến mại. Nếu quy tắc không tự nhiên thuộc về một `Order` hoặc `Customer` cụ thể, một domain service hoặc đối tượng policy có tên rõ ràng có thể phù hợp.

Không nên để entity tự gọi repository, gửi email hoặc gọi HTTP. Những thao tác đó là I/O và thường thuộc application/infrastructure. Domain có thể trả về domain event hoặc kết quả để application xử lý sau khi lưu.

## 5. Khi mô hình dữ liệu đơn giản là lựa chọn đúng

Mô hình đơn giản có chủ đích thường phù hợp khi:

- Dữ liệu chủ yếu được tạo, đọc, cập nhật và xóa.
- Quy tắc nghiệp vụ ít, rõ và không thay đổi thường xuyên.
- Không có nhiều trạng thái hoặc chuyển đổi phức tạp.
- Các thao tác không cần phối hợp nhiều đối tượng để giữ bất biến.
- Một application service ngắn có thể diễn đạt đầy đủ ca sử dụng.
- Mô hình API, mô hình lưu trữ và khái niệm nội bộ có vòng đời gần giống nhau.
- Chi phí thêm abstraction, mapper và lớp domain lớn hơn lợi ích nhận được.

Ví dụ quản lý danh sách tỉnh/thành, danh mục màu sắc hoặc cấu hình hiển thị có thể không cần aggregate phức tạp. Một service với các thao tác CRUD, validation và repository là đủ rõ ràng.

Cũng có thể giữ entity JPA đơn giản nếu dữ liệu không mang nhiều hành vi. Ràng buộc database vẫn cần thiết để bảo vệ tính duy nhất, khóa ngoại và tính toàn vẹn dữ liệu. Validation ở application vẫn cần kiểm tra quyền và điều kiện của ca sử dụng. “Đơn giản” không có nghĩa là bỏ qua kiểm tra.

## 6. Khi nào nên tăng hành vi cho mô hình miền?

Việc chuyển từ mô hình đơn giản sang mô hình có hành vi thường đáng giá khi xuất hiện một hoặc nhiều dấu hiệu:

- Nhiều quy tắc phải luôn đúng với cùng một đối tượng.
- Có nhiều trạng thái và các chuyển đổi trạng thái bị ràng buộc.
- Quy tắc tính toán hoặc chính sách được dùng bởi nhiều ca sử dụng.
- Các luồng API, tác vụ nền và message consumer cần cùng một hành vi.
- Một service bắt đầu chứa nhiều nhánh nghiệp vụ và thao tác sửa trực tiếp trường của entity.
- Bug thường xuất hiện do một đường gọi quên kiểm tra hoặc áp dụng quy tắc.
- Nhóm cần kiểm thử nghiệp vụ độc lập với framework và database.
- Các khái niệm miền có ngôn ngữ và ý nghĩa ổn định cần được thể hiện bằng kiểu dữ liệu rõ ràng.

Không nhất thiết phải tái cấu trúc toàn bộ module. Có thể bắt đầu bằng một bất biến đang bị lặp, chuyển nó vào một phương thức domain, thêm test, rồi tiếp tục khi có bằng chứng về lợi ích.

## 7. DDD không phải tiêu chí duy nhất để đánh giá

Domain-Driven Design cung cấp các kỹ thuật hữu ích như entity, value object, aggregate, domain service, repository và ubiquitous language. Những kỹ thuật này có thể hỗ trợ miền phức tạp, nhưng không phải mọi ứng dụng đều cần áp dụng đầy đủ.

Có thể chọn mức độ phù hợp:

| Độ phức tạp | Thiết kế có thể phù hợp |
|---|---|
| CRUD đơn giản | DTO/entity và application service ngắn |
| Có một số quy tắc dùng chung | Đối tượng domain nhỏ hoặc policy thuần Java |
| Nhiều bất biến và trạng thái | Entity/aggregate có hành vi rõ, value object |
| Quy tắc phối hợp nhiều khái niệm | Domain service hoặc policy có tên rõ |
| Nhiều miền nghiệp vụ và nhóm độc lập | Cân nhắc bounded context và ranh giới module |

Không nên tạo aggregate cho mọi bảng, repository cho mọi entity hoặc interface cho mọi service chỉ để mô phỏng một kiến trúc lý tưởng. Ngược lại, không nên dùng lý do “ứng dụng CRUD” để bỏ qua một quy tắc quan trọng đã bắt đầu xuất hiện.

Một thiết kế tốt có thể đơn giản ở phần lớn hệ thống và có mô hình domain giàu hành vi ở một số khu vực nghiệp vụ phức tạp. Không cần mọi package có cùng mức độ trừu tượng.

## 8. Những sai lầm khi tái cấu trúc mô hình miền

### 8.1. Chuyển toàn bộ code từ service vào entity

Một entity khổng lồ biết cách truy cập database, gửi email, gọi dịch vụ ngoài và điều phối toàn bộ quy trình sẽ khó kiểm thử và khó thay đổi. Chỉ chuyển các quy tắc và hành vi thuộc khái niệm domain vào mô hình. Application vẫn điều phối; adapter vẫn xử lý I/O.

### 8.2. Tạo phương thức chỉ để bọc setter

Một phương thức như `changeName(String name)` chỉ gọi `this.name = name` mà không bảo vệ quy tắc hoặc thể hiện ý nghĩa có thể không mang lại nhiều giá trị. Phương thức nên diễn đạt hành vi hoặc bảo vệ một điều kiện có ý nghĩa.

### 8.3. Giữ service khổng lồ nhưng đổi tên thành domain service

Đổi tên class không làm thay đổi trách nhiệm. Nếu lớp vẫn điều phối HTTP, transaction, repository, gửi email và quy tắc, cần phân tách theo trách nhiệm thực tế.

### 8.4. Tạo abstraction trước khi có nhu cầu

Thêm interface và nhiều implementation dự phòng làm tăng chi phí đọc và điều hướng. Hãy tạo abstraction khi có ranh giới thay thế, kiểm thử hoặc phụ thuộc cần bảo vệ.

### 8.5. Dùng entity JPA làm nơi chứa mọi quyết định chỉ vì nó đã có dữ liệu

Entity ORM có thể là một lựa chọn thực dụng, nhưng cần chú ý lifecycle, lazy loading và việc framework có thể tạo object ở trạng thái chưa đầy đủ. Nếu constructor hoặc factory không bảo vệ được bất biến, cần thiết kế cách tạo và khôi phục trạng thái phù hợp.

### 8.6. Để validation ở controller thay cho bảo vệ domain

Validation HTTP giúp phản hồi đầu vào sai sớm. Nhưng một message consumer hoặc tác vụ nền có thể gọi application mà không đi qua controller. Bất biến nghiệp vụ cần được bảo vệ ở domain hoặc nơi thực thi ca sử dụng để mọi đường gọi đều tuân thủ.

## 9. Kiểm thử để xác nhận mô hình có trách nhiệm phù hợp

Khi quy tắc nằm trong domain, có thể kiểm thử trực tiếp hành vi:

```java
class OrderConfirmationTest {
    @Test
    void cannotConfirmCancelledOrder() {
        Order order = Order.draft(
                new OrderId("O-100"),
                List.of(new OrderLine(
                        new ProductId("P-10"),
                        1,
                        Money.of("100000", "VND"))));

        order.cancel();

        assertThrows(
                InvalidOrderStateException.class,
                order::confirm);
    }
}
```

Test này không cần Spring hoặc database. Nó bảo vệ một quy tắc chuyển trạng thái. Application service vẫn cần test riêng để xác minh tải đơn, gọi hành vi và lưu kết quả. Repository cần integration test khi cần kiểm tra mapping hoặc transaction.

Nếu mô hình đơn giản có chủ đích, kiểm thử có thể tập trung vào application service, validation và repository contract. Không cần tạo unit test cho từng getter/setter nếu không có hành vi cần bảo vệ.

Hãy đánh giá test theo điều nó chứng minh:

- Unit test domain chứng minh quy tắc ở đối tượng hoạt động đúng với dữ liệu đầu vào.
- Application test chứng minh các bước điều phối và xử lý lỗi.
- Repository integration test chứng minh truy vấn, mapping và ràng buộc lưu trữ.
- Web/contract test chứng minh hợp đồng với caller.
- E2E test chọn lọc chứng minh luồng quan trọng qua nhiều tầng.

Không loại bỏ integration test chỉ vì domain đã có unit test. Một mô hình giàu hành vi không thể tự chứng minh transaction hoặc SQL đúng.

## 10. Quy trình đánh giá và cải thiện từng bước

Khi review một module, có thể tiến hành theo thứ tự:

1. **Liệt kê quy tắc thực tế:** tìm các điều kiện, phép tính và chuyển trạng thái đang được thực hiện trong service, controller hoặc repository.
2. **Tìm nơi quy tắc bị lặp:** xác định các luồng cùng xử lý một khái niệm nhưng có logic khác nhau.
3. **Xác định bất biến:** hỏi đối tượng nào phải luôn giữ điều kiện nào, kể cả khi được gọi từ API, tác vụ nền hoặc message consumer.
4. **Chọn trách nhiệm phù hợp:** đưa bất biến vào entity/value object, chính sách liên quan vào domain service, còn điều phối giữ ở application.
5. **Giữ mô hình đơn giản khi không có quy tắc:** không tạo class hoặc abstraction chỉ để làm cấu trúc đồng đều.
6. **Thêm test bảo vệ hành vi:** tạo test cho quy tắc trước hoặc cùng lúc với refactor.
7. **Theo dõi chi phí sau thay đổi:** xem số lớp, mapper, độ phức tạp và khả năng hiểu luồng có thực sự cải thiện không.

Có thể dùng bảng review sau:

| Câu hỏi | Nếu câu trả lời là “có” | Hướng xem xét |
|---|---|---|
| Quy tắc của cùng một khái niệm bị lặp ở nhiều service? | Có nguy cơ lệch hành vi | Đưa về domain/policy dùng chung |
| Đối tượng có thể bị sửa thành trạng thái không hợp lệ? | Bất biến chưa được bảo vệ | Giới hạn setter, dùng hành vi có kiểm tra |
| Service chỉ tải, gọi và lưu? | Có thể là application orchestration hợp lý | Giữ service đơn giản |
| Service chứa nhiều nhánh và phép tính nghiệp vụ? | Có thể đang ôm trách nhiệm domain | Tách hành vi hoặc policy theo khái niệm |
| Dữ liệu chỉ CRUD, ít quy tắc? | Domain model giàu hành vi có thể dư thừa | Giữ mô hình đơn giản |
| Một thay đổi framework buộc sửa quy tắc nghiệp vụ? | Phụ thuộc kỹ thuật có thể đã rò rỉ | Cân nhắc adapter và mô hình riêng |
| Tách mô hình làm tăng mapper nhưng không tạo ranh giới? | Chi phí có thể lớn hơn lợi ích | Cân nhắc dùng chung mô hình |

## 11. Ghi nhớ

- Mô hình miền thiếu hành vi thường để quy tắc quan trọng nằm rải rác trong service và cho phép đối tượng đi vào trạng thái không hợp lệ.
- Mô hình dữ liệu đơn giản không tự động là anemic; CRUD ít quy tắc có thể dùng entity đơn giản và application service ngắn.
- Đánh giá dựa trên bất biến, chuyển trạng thái, quy tắc dùng chung, rủi ro thay đổi và khả năng kiểm thử, không dựa trên số phương thức hoặc class.
- Domain nên sở hữu hành vi và quy tắc của khái niệm; application service điều phối; adapter thực hiện I/O.
- Không chuyển toàn bộ điều phối vào entity hoặc tạo phương thức chỉ để bọc setter.
- DDD cung cấp công cụ cho miền phức tạp nhưng không bắt buộc cho mọi module.
- Có thể nâng cấp mô hình từng bước: chọn một quy tắc bị lặp, đưa về đúng nơi và thêm test bảo vệ.
- Unit test domain không thay thế integration test cho repository, transaction hoặc hợp đồng giữa các tầng.
- Giữ mức trừu tượng vừa đủ với rủi ro và độ phức tạp thực tế của từng khu vực phần mềm.

