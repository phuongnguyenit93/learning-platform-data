# Đặt hành vi cạnh dữ liệu mà hành vi đó quản lý

## Mục tiêu

Trong MVC, Model biểu diễn dữ liệu và các quy tắc nghiệp vụ mà ứng dụng cần bảo vệ. Một cách tổ chức quan trọng của Model là đặt hành vi gần dữ liệu chịu sự chi phối của hành vi đó. Thay vì để nhiều thành phần đọc rồi sửa trạng thái thông qua các thuộc tính công khai, đối tượng sở hữu trạng thái cung cấp những thao tác có ý nghĩa để tự kiểm tra điều kiện và duy trì tính hợp lệ.

Bài học này giải thích cách đóng gói trạng thái cùng hành vi, cách nhận diện nơi phù hợp cho một quy tắc nghiệp vụ, và cách phối hợp Model với Controller, View, application service và tầng lưu trữ trong ứng dụng web.

Sau khi học, người học có thể:

- Giải thích vì sao dữ liệu và hành vi liên quan nên nằm gần nhau.
- Phân biệt một đối tượng chỉ chứa dữ liệu với một domain model có hành vi.
- Thiết kế phương thức bảo vệ bất biến và chuyển trạng thái hợp lệ.
- Quyết định khi nào hành vi thuộc entity, value object, domain service hoặc application service.
- Kiểm thử quy tắc nghiệp vụ mà không phụ thuộc vào giao diện web.

## 1. Nguyên tắc: dữ liệu có chủ sở hữu và chủ sở hữu bảo vệ dữ liệu

Một đối tượng thường có trách nhiệm quản lý một phần trạng thái. Nếu trạng thái đó có các điều kiện phải luôn đúng, đối tượng nên cung cấp hành vi để thay đổi nó theo những điều kiện ấy.

Ví dụ, một đơn hàng có danh sách mặt hàng và trạng thái xử lý. Những quy tắc có thể gồm:

- Đơn hàng nháp mới được thêm mặt hàng.
- Số lượng của mỗi mặt hàng phải lớn hơn không.
- Không thể xác nhận đơn hàng chưa có mặt hàng.
- Đơn hàng đã thanh toán không thể bị hủy bằng thao tác hủy thông thường.

Nếu Order chỉ công khai các thuộc tính có thể sửa tùy ý, bất kỳ controller, service hay đoạn mã nào cũng có thể đưa đơn hàng vào trạng thái không hợp lệ. Nếu Order cung cấp các thao tác như addItem(), confirm() và cancel(), chính đối tượng có thể kiểm tra điều kiện trước khi thay đổi trạng thái.

Đó là ý nghĩa của việc đặt hành vi cạnh dữ liệu mà hành vi quản lý: mã thực thi quy tắc nằm gần nơi sở hữu trạng thái chịu tác động của quy tắc.

### Đóng gói không chỉ là che giấu thuộc tính

Đóng gói thường được giới thiệu bằng cách khai báo thuộc tính private và cung cấp getter/setter. Cách làm đó có thể che giấu cách lưu trữ, nhưng chưa chắc bảo vệ được quy tắc nghiệp vụ.

Ví dụ:

    public class Order {
        private OrderStatus status;

        public OrderStatus getStatus() {
            return status;
        }

        public void setStatus(OrderStatus status) {
            this.status = status;
        }
    }

Thuộc tính đã là private, nhưng mọi nơi vẫn có thể gọi setStatus() để chuyển đơn hàng từ DRAFT sang PAID, kể cả khi chưa có bước xác nhận hay thanh toán.

Một API giàu ý nghĩa nghiệp vụ giới hạn cách thay đổi:

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Chỉ đơn hàng nháp mới được xác nhận");
        }
        if (items.isEmpty()) {
            throw new IllegalStateException("Đơn hàng phải có ít nhất một mặt hàng");
        }
        status = OrderStatus.CONFIRMED;
    }

Người gọi yêu cầu một hành động có ý nghĩa (confirm) thay vì tự gán một giá trị trạng thái. Đối tượng chịu trách nhiệm quyết định hành động đó có hợp lệ hay không.

## 2. Vì sao nên đặt hành vi gần dữ liệu?

### Bảo vệ bất biến nghiệp vụ

Bất biến là điều kiện phải luôn đúng đối với một đối tượng hoặc một nhóm đối tượng trong suốt vòng đời hợp lệ của chúng. Chẳng hạn, số lượng dòng hàng phải dương, số dư tài khoản không được âm nếu nghiệp vụ cấm thấu chi, hoặc lịch đặt phòng không được có thời điểm kết thúc trước thời điểm bắt đầu.

Nếu quy tắc chỉ nằm trong controller, một đường gọi khác như tác vụ nền, API nội bộ hoặc kiểm thử có thể bỏ qua nó. Khi quy tắc được bảo vệ tại nơi sở hữu trạng thái, mọi luồng gọi hành vi đó đều phải tuân theo cùng điều kiện.

### Tăng tính gắn kết

Một lớp có tính gắn kết cao khi dữ liệu và các thao tác của nó cùng phục vụ một trách nhiệm rõ ràng. Order quản lý các dòng hàng và trạng thái đơn hàng; những thao tác thêm mặt hàng, tính tổng và xác nhận đều liên quan trực tiếp đến trách nhiệm ấy.

Ngược lại, nếu dữ liệu nằm trong Order nhưng quy tắc thêm mặt hàng nằm ở OrderController, quy tắc tính tổng nằm ở CheckoutService, còn quy tắc chuyển trạng thái nằm ở một helper khác, người đọc phải lần theo nhiều nơi để hiểu một khái niệm nghiệp vụ.

### Giảm phụ thuộc vào cấu trúc bên trong

Khi bên ngoài chỉ gọi order.confirm(), lớp có thể thay đổi cách lưu danh sách mặt hàng hoặc cách kiểm tra điều kiện mà không bắt buộc tất cả nơi gọi phải sửa theo. API thể hiện ý định nghiệp vụ thay vì chi tiết thuộc tính.

### Dễ kiểm thử

Quy tắc trong Model có thể được kiểm thử trực tiếp bằng unit test. Không cần dựng HTTP request, template hay cơ sở dữ liệu chỉ để xác nhận rằng một đơn hàng rỗng không thể được xác nhận.

## 3. Từ mô hình chỉ chứa dữ liệu đến domain model có hành vi

Một mô hình chỉ chứa dữ liệu (thường được gọi là anemic domain model) giữ thuộc tính trong các lớp entity, còn hầu hết quy tắc được đặt trong các service thao tác lên những thuộc tính đó.

Ví dụ, cách viết sau để service trực tiếp đọc và thay đổi trạng thái:

    public class Order {
        private OrderStatus status;
        private List<OrderItem> items;

        public OrderStatus getStatus() { return status; }
        public void setStatus(OrderStatus status) { this.status = status; }
        public List<OrderItem> getItems() { return items; }
    }

    public class OrderService {
        public void confirm(Order order) {
            if (order.getStatus() != OrderStatus.DRAFT) {
                throw new IllegalStateException();
            }
            if (order.getItems().isEmpty()) {
                throw new IllegalStateException();
            }
            order.setStatus(OrderStatus.CONFIRMED);
        }
    }

Vấn đề không phải là có một OrderService. Vấn đề là service phải biết cấu trúc nội bộ và tự thực hiện những thay đổi mà chính Order cần bảo vệ. Nếu một service khác cũng muốn xác nhận đơn hàng, quy tắc có thể bị sao chép hoặc thực hiện không nhất quán.

Một domain model có hành vi chuyển trách nhiệm bảo vệ trạng thái vào đối tượng:

    public class Order {
        private OrderStatus status = OrderStatus.DRAFT;
        private final List<OrderItem> items = new ArrayList<>();

        public void confirm() {
            if (status != OrderStatus.DRAFT) {
                throw new IllegalStateException("Đơn hàng không ở trạng thái nháp");
            }
            if (items.isEmpty()) {
                throw new IllegalStateException("Không thể xác nhận đơn hàng rỗng");
            }
            status = OrderStatus.CONFIRMED;
        }

        public OrderStatus status() {
            return status;
        }

        public List<OrderItem> items() {
            return List.copyOf(items);
        }
    }

Trong ví dụ này, Order giữ quyền kiểm soát việc chuyển trạng thái. Danh sách trả về là bản sao không thể sửa, nên bên ngoài không thể bỏ qua API của đối tượng để thêm hoặc xóa dòng hàng. Các phương thức thêm và xóa mặt hàng cũng nên được định nghĩa trên Order với những điều kiện phù hợp.

Không phải mọi ứng dụng đều cần một domain model phức tạp. Với màn hình CRUD đơn giản, một lớp dữ liệu và service thủ tục có thể đủ rõ ràng. Khi quy tắc nghiệp vụ tăng lên, có nhiều trạng thái và nhiều luồng cập nhật, việc đưa hành vi vào nơi sở hữu dữ liệu giúp bảo vệ tính nhất quán tốt hơn.

## 4. Ví dụ: đơn hàng tự quản lý các chuyển đổi hợp lệ

Giả sử một cửa hàng trực tuyến có đơn hàng gồm nhiều dòng hàng. Khi thêm sản phẩm, đơn hàng phải kiểm tra trạng thái, số lượng và khả năng bán của sản phẩm. Giá tại thời điểm thêm hàng được ghi nhận vào dòng hàng để tổng tiền không tự thay đổi khi giá niêm yết của sản phẩm đổi sau đó.

Ví dụ dưới đây lược giản phần tiền tệ, kho hàng và lưu trữ để tập trung vào trách nhiệm của Model.

    public enum OrderStatus {
        DRAFT,
        CONFIRMED,
        PAID,
        CANCELLED
    }

    public interface Product {
        String id();
        boolean isAvailableForSale();
        BigDecimal currentPrice();
    }

    public record OrderLine(
            String productId,
            BigDecimal unitPrice,
            int quantity) {

        public OrderLine {
            Objects.requireNonNull(productId);
            Objects.requireNonNull(unitPrice);

            if (quantity <= 0) {
                throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
            }
            if (unitPrice.signum() < 0) {
                throw new IllegalArgumentException("Giá không được âm");
            }
        }

        public OrderLine increaseBy(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("Số lượng tăng phải lớn hơn 0");
            }
            return new OrderLine(
                    productId,
                    unitPrice,
                    Math.addExact(quantity, amount));
        }

        public BigDecimal subtotal() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    public final class Order {
        private final Map<String, OrderLine> lines = new LinkedHashMap<>();
        private OrderStatus status = OrderStatus.DRAFT;

        public void addItem(Product product, int quantity) {
            ensureDraft();
            Objects.requireNonNull(product);

            if (quantity <= 0) {
                throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
            }
            if (!product.isAvailableForSale()) {
                throw new IllegalArgumentException("Sản phẩm hiện không được bán");
            }

            OrderLine current = lines.get(product.id());
            OrderLine updated = current == null
                    ? new OrderLine(product.id(), product.currentPrice(), quantity)
                    : current.increaseBy(quantity);

            lines.put(product.id(), updated);
        }

        public BigDecimal total() {
            return lines.values().stream()
                    .map(OrderLine::subtotal)
                    .reduce(BigDecimal.ZERO, BigDecimal::add);
        }

        public void confirm() {
            ensureDraft();
            if (lines.isEmpty()) {
                throw new IllegalStateException("Không thể xác nhận đơn hàng rỗng");
            }
            status = OrderStatus.CONFIRMED;
        }

        public void markPaid() {
            if (status != OrderStatus.CONFIRMED) {
                throw new IllegalStateException(
                        "Chỉ đơn hàng đã xác nhận mới được đánh dấu đã thanh toán");
            }
            status = OrderStatus.PAID;
        }

        public void cancel() {
            if (status != OrderStatus.DRAFT && status != OrderStatus.CONFIRMED) {
                throw new IllegalStateException(
                        "Không thể hủy đơn hàng ở trạng thái hiện tại");
            }
            status = OrderStatus.CANCELLED;
        }

        public OrderStatus status() {
            return status;
        }

        public List<OrderLine> lines() {
            return List.copyOf(lines.values());
        }

        private void ensureDraft() {
            if (status != OrderStatus.DRAFT) {
                throw new IllegalStateException(
                        "Chỉ có thể sửa đơn hàng ở trạng thái nháp");
            }
        }
    }

Điểm cần chú ý:

- Order sở hữu danh sách dòng hàng và trạng thái của đơn hàng.
- addItem() bảo đảm chỉ đơn hàng nháp mới được sửa, số lượng hợp lệ và sản phẩm có thể bán.
- OrderLine bảo vệ quy tắc về số lượng và giá, đồng thời tự tính thành tiền của dòng hàng.
- confirm(), markPaid() và cancel() biểu diễn các chuyển đổi trạng thái có ý nghĩa nghiệp vụ.
- lines() không trao quyền sửa danh sách nội bộ cho bên gọi.
- Giá được chụp lại tại thời điểm thêm sản phẩm. Nếu nghiệp vụ yêu cầu kiểm tra lại giá khi xác nhận, quy tắc đó cần được bổ sung vào ca sử dụng tương ứng.

Trong hệ thống thực tế, tiền thường nên được biểu diễn bằng một value object như Money có cả số tiền và đơn vị tiền tệ, thay vì dùng BigDecimal rời rạc. Ví dụ cũng cần được bổ sung chính sách thuế, chiết khấu, làm tròn, tồn kho và xử lý đồng thời tùy yêu cầu sản phẩm.

## 5. Xác định hành vi thuộc entity, value object hay service

Đặt hành vi cạnh dữ liệu không có nghĩa mọi quy tắc đều phải nằm trong một entity. Hãy tìm đối tượng có đủ thông tin và có trách nhiệm sở hữu quy tắc đó.

### Entity: hành vi làm thay đổi trạng thái có định danh

Entity là đối tượng có định danh xuyên suốt vòng đời. Một Order vẫn là cùng một đơn hàng dù trạng thái chuyển từ DRAFT sang CONFIRMED rồi PAID.

Những hành vi thay đổi trạng thái đơn hàng nên thuộc Order, ví dụ:

- Thêm hoặc xóa dòng hàng khi đơn hàng còn nháp.
- Xác nhận đơn hàng.
- Ghi nhận trạng thái thanh toán.
- Hủy đơn hàng khi điều kiện cho phép.

Nếu một quy tắc liên quan đến nhiều entity nằm trong cùng một ranh giới nhất quán, aggregate root thường là nơi cung cấp thao tác công khai để bảo vệ quy tắc đó. Trong ví dụ trên, bên ngoài thay đổi dòng hàng thông qua Order, không sửa trực tiếp danh sách nội bộ.

### Value object: hành vi dựa trên giá trị

Value object không có định danh riêng; hai đối tượng có cùng giá trị được xem là tương đương theo định nghĩa miền nghiệp vụ. Ví dụ: Money, DateRange, EmailAddress hoặc Quantity.

Value object thường bất biến. Nó có thể chứa hành vi như:

- Money.add(other) kiểm tra hai khoản tiền có cùng đơn vị tiền tệ.
- DateRange.overlaps(other) xác định hai khoảng thời gian có giao nhau.
- EmailAddress chuẩn hóa và kiểm tra cấu trúc địa chỉ.

Đặt hành vi trên value object giúp tránh lặp lại các phép tính và điều kiện ở nhiều nơi.

### Domain service: quy tắc nghiệp vụ không có một chủ sở hữu tự nhiên

Một số quy tắc liên quan đến nhiều entity hoặc nhiều khái niệm mà không đối tượng nào phù hợp để sở hữu. Khi đó, domain service có thể biểu diễn hành vi ấy.

Ví dụ, việc tính phí vận chuyển có thể phụ thuộc vào địa chỉ giao hàng, tổng khối lượng đơn hàng, vùng phục vụ và chính sách vận chuyển. Không nhất thiết ép toàn bộ quy tắc vào Order hoặc Address; một ShippingFeePolicy có thể nhận các thông tin cần thiết và tính kết quả.

Domain service nên thể hiện một quy tắc nghiệp vụ rõ ràng. Nếu nó chỉ tải dữ liệu, gọi repository, gửi email rồi điều phối nhiều bước kỹ thuật, nó có thể đang làm nhiệm vụ của application service.

### Application service: điều phối ca sử dụng

Application service tổ chức một thao tác hoàn chỉnh: tải aggregate, gọi hành vi domain, lưu thay đổi và phối hợp cổng tích hợp khi cần. Nó thường xác định ranh giới giao dịch.

Ví dụ:

    @Service
    public class ConfirmOrderService {
        private final OrderRepository orders;

        public ConfirmOrderService(OrderRepository orders) {
            this.orders = orders;
        }

        @Transactional
        public void confirm(UUID orderId) {
            Order order = orders.findById(orderId)
                    .orElseThrow(OrderNotFoundException::new);

            order.confirm();

            orders.save(order);
        }
    }

Application service điều phối việc tải và lưu Order. Quy tắc “đơn hàng nào được xác nhận” vẫn thuộc Order.confirm(). Nhờ đó, cùng hành vi có thể được gọi từ web controller, tác vụ nền hoặc một luồng xử lý khác.

## 6. Kết nối Model với Controller và View trong MVC

Trong ứng dụng web, Controller tiếp nhận request, kiểm tra dữ liệu đầu vào ở ranh giới giao thức, gọi application service hoặc hành vi phù hợp, rồi chuẩn bị phản hồi. Controller không nên trực tiếp sửa từng thuộc tính của Model để tự thực thi toàn bộ quy tắc nghiệp vụ.

Ví dụ, controller có thể tiếp nhận yêu cầu xác nhận đơn hàng:

    @PostMapping("/{id}/confirm")
    public String confirm(@PathVariable UUID id) {
        confirmOrderService.confirm(id);
        return "redirect:/orders/" + id;
    }

Controller không cần biết Order lưu dòng hàng bằng Map hay List, cũng không cần tự kiểm tra mọi điều kiện chuyển trạng thái. Nó chỉ điều phối request đến ca sử dụng.

View nhận dữ liệu đã được chuẩn bị để trình bày. Nó có thể hiển thị trạng thái đơn hàng, danh sách dòng hàng và thông báo phù hợp, nhưng không nên quyết định đơn hàng có được xác nhận hay không. Việc ẩn nút “Xác nhận” trên giao diện chỉ hỗ trợ trải nghiệm người dùng; Model vẫn phải kiểm tra điều kiện vì request có thể được gửi trực tiếp.

Cần phân biệt các loại kiểm tra:

| Loại kiểm tra | Ví dụ | Vị trí phù hợp |
|---|---|---|
| Cấu trúc đầu vào | Trường quantity có phải số nguyên? orderId có đúng định dạng? | Binding, DTO, validation ở ranh giới Controller |
| Quy tắc bất biến | Số lượng phải dương; đơn hàng rỗng không thể xác nhận | Model hoặc value object sở hữu dữ liệu |
| Quy tắc của ca sử dụng | Người dùng hiện tại có quyền xác nhận đơn hàng này? | Application service hoặc chính sách quyền truy cập |
| Quy tắc liên hệ thống | Gửi thông báo sau khi xác nhận; đồng bộ trạng thái với cổng thanh toán | Application service và adapter tích hợp |

Một quy tắc có thể được kiểm tra ở nhiều lớp với mục đích khác nhau. Ví dụ, form validation báo lỗi sớm để người dùng sửa dữ liệu, còn Model vẫn phải bảo vệ bất biến khi hành vi được gọi từ bất kỳ đường đi nào.

## 7. Kiểm thử hành vi của Model

Vì hành vi nghiệp vụ được đặt gần dữ liệu, có thể kiểm thử trực tiếp bằng unit test. Một số trường hợp cho Order:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Thêm sản phẩm vào đơn hàng nháp với số lượng dương | Có dòng hàng và tổng tiền được cập nhật |
| Thêm số lượng bằng 0 hoặc âm | Từ chối thao tác |
| Thêm sản phẩm không được phép bán | Từ chối thao tác |
| Xác nhận đơn hàng rỗng | Từ chối thao tác |
| Xác nhận đơn hàng nháp có mặt hàng | Trạng thái chuyển thành CONFIRMED |
| Thêm mặt hàng sau khi xác nhận | Từ chối thao tác |
| Đánh dấu đã thanh toán khi chưa xác nhận | Từ chối thao tác |
| Hủy đơn hàng đã thanh toán | Từ chối thao tác theo chính sách ví dụ |

Ví dụ kiểm thử bằng JUnit:

    @Test
    void cannotConfirmAnEmptyOrder() {
        Order order = new Order();

        assertThrows(
                IllegalStateException.class,
                order::confirm);

        assertEquals(OrderStatus.DRAFT, order.status());
    }

    @Test
    void confirmingAnOrderWithItemsChangesItsStatus() {
        Order order = new Order();
        Product product = availableProduct("course-101", new BigDecimal("120.00"));

        order.addItem(product, 2);
        order.confirm();

        assertEquals(OrderStatus.CONFIRMED, order.status());
        assertEquals(new BigDecimal("240.00"), order.total());
    }

Unit test nên tập trung vào hành vi quan sát được và điều kiện nghiệp vụ. Không cần kiểm tra thuộc tính private bằng reflection hoặc buộc test phụ thuộc vào cấu trúc lưu trữ nội bộ.

Các loại kiểm thử khác vẫn cần thiết:

- Unit test kiểm tra quy tắc trong entity và value object.
- Integration test kiểm tra việc ánh xạ, lưu và tải aggregate qua repository.
- Application test kiểm tra ranh giới giao dịch và phối hợp các thành phần.
- Controller test kiểm tra binding, mã HTTP, điều hướng và cách phản hồi lỗi.

## 8. Các giới hạn và lỗi thiết kế thường gặp

### Đưa mọi hành vi vào một entity

Một entity có quá nhiều trách nhiệm sẽ trở nên khó hiểu. Order không nên tự gửi email, gọi cổng thanh toán qua HTTP, ghi log hạ tầng hoặc điều khiển quy trình triển khai. Nó nên giữ các quy tắc liên quan đến trạng thái đơn hàng. Application service và adapter phụ trách điều phối và tích hợp.

### Công khai setter cho mọi thuộc tính

Setter tổng quát làm cho trạng thái có thể thay đổi theo mọi thứ tự. Hãy ưu tiên phương thức thể hiện ý định nghiệp vụ như confirm(), cancel() hoặc changeShippingAddress() và chỉ cung cấp những thao tác hợp lệ.

Không phải mọi thuộc tính đều cần setter. Một số thuộc tính chỉ được gán khi tạo đối tượng; một số khác chỉ được thay đổi thông qua một hành vi có điều kiện.

### Đưa truy cập cơ sở dữ liệu và HTTP vào entity

Entity nên tập trung vào quy tắc miền nghiệp vụ. Việc tự gọi repository, gửi HTTP request hoặc phụ thuộc vào framework web khiến Model khó kiểm thử và khó tái sử dụng. Application service phối hợp với repository và adapter, sau đó gọi hành vi của entity.

### Lặp lại cùng một quy tắc ở nhiều lớp

Kiểm tra đầu vào ở Controller hữu ích, nhưng không thay thế kiểm tra bất biến trong Model. Ngược lại, Model không cần biết cách hiển thị lỗi cho người dùng. Mỗi lớp kiểm tra điều thuộc trách nhiệm của nó và chuyển lỗi qua hợp đồng rõ ràng.

### Coi mọi ứng dụng đều cần domain model phức tạp

Một danh mục nội dung đơn giản hoặc trang quản trị chỉ thực hiện CRUD có thể không cần nhiều entity giàu hành vi. Hãy chọn mức độ mô hình hóa theo độ phức tạp nghiệp vụ. Khi có nhiều quy tắc, trạng thái và luồng cập nhật, lợi ích của việc đóng gói hành vi sẽ rõ rệt hơn.

### Nhầm lẫn bất biến trong bộ nhớ với tính nhất quán đồng thời

Một phương thức confirm() có thể kiểm tra trạng thái hiện tại của đối tượng, nhưng điều đó không tự giải quyết được hai request đồng thời cùng tải và xác nhận một đơn hàng. Ứng dụng có thể cần transaction, khóa phù hợp, optimistic locking với version, ràng buộc duy nhất hoặc cơ chế idempotency tùy nghiệp vụ.

Quy tắc nghiệp vụ trong Model và cơ chế nhất quán ở tầng lưu trữ cần phối hợp với nhau. Không nên giả định rằng việc đóng gói trong một lớp tự động bảo đảm mọi tình huống cạnh tranh giữa các tiến trình.

## 9. Quy trình thiết kế thực tế

Khi thiết kế một Model có hành vi, có thể đi theo trình tự sau:

1. Xác định khái niệm nghiệp vụ và trạng thái mà nó sở hữu. Ví dụ: đơn hàng có các dòng hàng và trạng thái xử lý.
2. Liệt kê bất biến cần giữ đúng. Ví dụ: đơn hàng đã xác nhận không được thêm mặt hàng.
3. Xác định những hành động hợp lệ làm thay đổi trạng thái. Ví dụ: addItem(), confirm(), markPaid(), cancel().
4. Đặt mỗi hành động vào đối tượng có đủ dữ liệu và trách nhiệm để bảo vệ quy tắc.
5. Dùng value object cho khái niệm được xác định bởi giá trị và có quy tắc riêng.
6. Dùng domain service khi một quy tắc không có chủ sở hữu tự nhiên trong entity hoặc value object.
7. Để application service điều phối tải dữ liệu, giao dịch, lưu trữ và tích hợp.
8. Kiểm thử các chuyển đổi hợp lệ và không hợp lệ trước khi nối vào Controller và View.

Khi rà soát một thiết kế hiện có, hãy tìm các đoạn mã thường xuyên đọc thuộc tính của entity rồi tự quyết định và gán trạng thái. Đó là dấu hiệu quy tắc có thể đang nằm xa dữ liệu mà nó quản lý. Hãy xem xét chuyển quy tắc vào một phương thức có tên thể hiện ý định, sau đó cập nhật các nơi gọi để sử dụng API đó.

## Kết luận

Đặt hành vi cạnh dữ liệu mà hành vi quản lý là cách xây dựng Model có trách nhiệm rõ ràng. Entity bảo vệ trạng thái và các chuyển đổi nghiệp vụ của nó; value object đóng gói quy tắc dựa trên giá trị; domain service xử lý quy tắc không có chủ sở hữu tự nhiên; application service điều phối ca sử dụng và các thành phần bên ngoài.

Trong MVC, cách tổ chức này giúp Controller tập trung vào tiếp nhận và điều phối request, View tập trung vào trình bày, còn Model giữ các quy tắc cần luôn đúng. Kết quả là hành vi nghiệp vụ nhất quán hơn, dễ kiểm thử hơn và ít phụ thuộc vào một đường đi cụ thể của ứng dụng.
