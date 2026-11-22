# Vấn đề khi giao diện, xử lý đầu vào và nghiệp vụ trộn lẫn

Hãy hình dung một trang web cho phép khách hàng đặt hàng. Khi người dùng nhấn nút **Đặt hàng**, ứng dụng phải đọc dữ liệu biểu mẫu, kiểm tra dữ liệu, xác định sản phẩm và số lượng còn có thể bán, tính tiền, lưu đơn hàng rồi trả về một trang kết quả. Đây là một luồng nghiệp vụ đơn giản, nhưng nó liên quan đến nhiều loại công việc khác nhau.

Nếu một hàm hoặc một lớp vừa đọc request HTTP, vừa xử lý quy tắc đặt hàng, truy vấn cơ sở dữ liệu, vừa tạo HTML để trả về trình duyệt, các trách nhiệm đó sẽ phụ thuộc chặt chẽ vào nhau. Ban đầu cách viết này có vẻ nhanh vì mọi thứ nằm cùng một chỗ. Khi ứng dụng có thêm biểu mẫu, quy tắc và màn hình, mỗi thay đổi nhỏ lại có thể ảnh hưởng đến nhiều phần không liên quan.

Mô hình **Model–View–Controller (MVC)** giúp tổ chức ứng dụng bằng cách tách trạng thái và nghiệp vụ của ứng dụng khỏi phần trình bày và phần tiếp nhận tương tác. Để hiểu vì sao cách tổ chức này hữu ích, trước hết cần nhận diện những vấn đề xuất hiện khi các trách nhiệm bị trộn lẫn.

## 1. Một request web chứa nhiều loại trách nhiệm

Một request thường đi qua nhiều công việc. Chúng có liên quan với nhau trong cùng một luồng xử lý, nhưng mục đích của chúng khác nhau.

| Trách nhiệm | Câu hỏi cần giải quyết | Ví dụ trong chức năng đặt hàng |
|---|---|---|
| Giao diện và trình bày | Người dùng nhìn thấy và tương tác với thông tin như thế nào? | Hiển thị biểu mẫu, thông báo lỗi, tổng tiền và trang xác nhận |
| Tiếp nhận đầu vào | Request mang dữ liệu gì và dữ liệu đó có đúng định dạng không? | Đọc `productId`, `quantity`, `couponCode`; chuyển số lượng thành số nguyên |
| Nghiệp vụ | Điều kiện nào phải đúng để thao tác được phép xảy ra? | Số lượng phải lớn hơn 0, sản phẩm còn hàng, mã giảm giá còn hiệu lực |
| Lưu trữ | Dữ liệu được đọc và ghi ở đâu, trong giao dịch nào? | Đọc sản phẩm, tạo đơn hàng, cập nhật tồn kho |
| Điều phối request và phản hồi | Ứng dụng phản hồi bằng trang, dữ liệu hay chuyển hướng nào? | Trả lại biểu mẫu có lỗi hoặc chuyển đến trang chi tiết đơn hàng |

Một luồng request cần phối hợp các trách nhiệm này. Vấn đề bắt đầu khi một thành phần phải tự thực hiện tất cả công việc, khiến ranh giới giữa dữ liệu đầu vào, quy tắc nghiệp vụ, lưu trữ và cách hiển thị không còn rõ ràng.

## 2. Ví dụ: một Servlet làm tất cả

Đoạn mã minh họa dưới đây mô phỏng một Servlet xử lý việc tạo đơn hàng. Đây là ví dụ về cách tổ chức dễ gây vấn đề, không phải mẫu kiến trúc nên áp dụng.

~~~java
protected void doPost(
        HttpServletRequest request,
        HttpServletResponse response
) throws IOException {
    // 1. Đọc và chuyển đổi dữ liệu từ biểu mẫu.
    String productId = request.getParameter("productId");
    String quantityText = request.getParameter("quantity");
    String couponCode = request.getParameter("couponCode");

    int quantity;
    try {
        quantity = Integer.parseInt(quantityText);
        if (quantity <= 0) {
            response.sendError(400, "Số lượng không hợp lệ");
            return;
        }
    } catch (NumberFormatException ex) {
        response.sendError(400, "Số lượng phải là một số nguyên");
        return;
    }

    // 2. Truy cập dữ liệu và áp dụng quy tắc nghiệp vụ.
    try (Connection connection = dataSource.getConnection()) {
        Product product = loadProduct(connection, productId);
        if (product == null || product.getStock() < quantity) {
            response.sendError(400, "Sản phẩm không khả dụng");
            return;
        }

        BigDecimal total = product.getPrice()
                .multiply(BigDecimal.valueOf(quantity));

        if ("SAVE10".equals(couponCode)) {
            total = total.multiply(new BigDecimal("0.90"));
        }

        // 3. Ghi dữ liệu.
        saveOrder(connection, productId, quantity, total);

        // 4. Tạo nội dung giao diện và gửi phản hồi.
        response.setContentType("text/html;charset=UTF-8");
        response.getWriter().write(
                "<html><body><h1>Đặt hàng thành công</h1>"
                + "<p>Tổng tiền: " + total + "</p></body></html>"
        );
    } catch (SQLException ex) {
        response.sendError(500, "Không thể tạo đơn hàng");
    }
}
~~~

Trong cùng một phương thức có ít nhất bốn nhóm trách nhiệm:

- Đọc tham số HTTP và chuyển kiểu dữ liệu.
- Kiểm tra điều kiện đặt hàng và tính giá.
- Mở kết nối, truy vấn và ghi dữ liệu.
- Quyết định mã phản hồi, tạo HTML và gửi kết quả.

Đoạn mã có thể chạy trong một tình huống nhỏ, nhưng Servlet đang hiểu quá nhiều chi tiết. Nó biết tên tham số của biểu mẫu, cách lưu đơn hàng, quy tắc giảm giá, cấu trúc HTML và cách báo lỗi HTTP. Một thay đổi ở bất kỳ phần nào cũng có thể buộc phải sửa cùng lớp này.

Ví dụ, nếu ứng dụng cần thêm giao diện di động hoặc một API cho phép đặt hàng, quy tắc tính giá và kiểm tra tồn kho vẫn giống nhau. Tuy nhiên, nếu các quy tắc đó nằm trong Servlet và gắn với phản hồi HTML, luồng API mới có thể phải sao chép chúng hoặc gọi lại một thành phần vốn được thiết kế cho trình duyệt.

## 3. Những hệ quả của việc trộn lẫn

### 3.1. Thay đổi giao diện có thể làm ảnh hưởng nghiệp vụ

Giả sử nhóm phát triển muốn thay trang HTML bằng một mẫu giao diện mới. Nếu mã tạo HTML nằm chung với mã tính tiền và lưu đơn hàng, việc chỉnh sửa giao diện có thể vô tình làm thay đổi luồng nghiệp vụ. Ngược lại, khi quy tắc giảm giá thay đổi, người sửa có thể phải thao tác trong một lớp vốn chủ yếu phục vụ HTTP và HTML.

Đây là dấu hiệu của **liên kết chặt**: một thành phần có quá nhiều lý do để thay đổi và phụ thuộc vào nhiều chi tiết thuộc các phần khác nhau.

### 3.2. Nghiệp vụ bị lặp lại giữa các điểm truy cập

Một ứng dụng có thể tạo đơn hàng từ trang web, ứng dụng di động, API đối tác hoặc tác vụ nền. Nếu mỗi điểm truy cập tự kiểm tra tồn kho và tính giảm giá, các phiên bản quy tắc dễ dần khác nhau.

Chẳng hạn, trang web có thể từ chối số lượng vượt tồn kho nhưng API lại quên kiểm tra. Một kênh có thể áp dụng mã giảm giá hết hạn vì quy tắc chưa được cập nhật ở đó. Lỗi không nhất thiết xuất phát từ thuật toán phức tạp; nó thường xuất phát từ việc một quy tắc quan trọng được đặt ở nhiều nơi.

### 3.3. Kiểm thử khó và tốn kém hơn

Khi muốn kiểm tra quy tắc “không được đặt số lượng lớn hơn tồn kho”, người viết test có thể phải tạo request HTTP, dựng Servlet, cấu hình kết nối cơ sở dữ liệu và kiểm tra cả nội dung phản hồi. Một kiểm thử như vậy bao gồm nhiều yếu tố hơn điều kiện nghiệp vụ cần xác minh.

Nếu quy tắc được đặt trong một thành phần nghiệp vụ riêng, có thể kiểm tra nó bằng dữ liệu đầu vào và kết quả mong đợi. Các kiểm thử HTTP vẫn cần thiết, nhưng chỉ tập trung vào việc request được tiếp nhận và phản hồi được tạo đúng cách.

### 3.4. Xử lý lỗi trở nên không nhất quán

Một phương thức lớn thường xử lý lỗi theo nhiều cách: lỗi định dạng trả mã 400, lỗi nghiệp vụ trả một chuỗi HTML, lỗi cơ sở dữ liệu trả mã 500. Khi các nhánh lỗi tăng lên, rất dễ có trường hợp cùng một lỗi nhưng mỗi màn hình lại hiển thị khác nhau.

Ngoài ra, lỗi kỹ thuật như mất kết nối cơ sở dữ liệu có thể bị trộn với lỗi người dùng như nhập số lượng không hợp lệ. Hai loại lỗi này cần cách xử lý khác nhau: lỗi đầu vào cần hướng dẫn người dùng sửa biểu mẫu; lỗi kỹ thuật cần được ghi log và trả thông báo an toàn.

### 3.5. Ranh giới bảo mật khó được kiểm soát

Dữ liệu từ trình duyệt luôn cần được xem là dữ liệu không đáng tin cậy. Nếu cùng một đoạn mã vừa nhận dữ liệu, vừa truy vấn, vừa tạo HTML, người phát triển dễ bỏ sót một bước bảo vệ:

- Ghép trực tiếp dữ liệu đầu vào vào câu SQL có thể tạo lỗ hổng SQL injection. Truy vấn có tham số giúp giảm rủi ro này.
- Đưa dữ liệu người dùng vào HTML mà không escape phù hợp có thể tạo lỗ hổng cross-site scripting (XSS).
- Tin vào giá, vai trò, trạng thái hoặc mã người dùng do trình duyệt gửi lên có thể cho phép người dùng sửa dữ liệu để vượt qua quy tắc.
- Chỉ ẩn nút trên giao diện không thay thế được việc kiểm tra quyền truy cập ở phía máy chủ.

Khi trách nhiệm được phân định, nhóm phát triển dễ xác định nơi kiểm tra dữ liệu, nơi áp dụng quyền nghiệp vụ và nơi mã hóa đầu ra. Việc tách lớp không tự động làm ứng dụng an toàn; các biện pháp bảo mật vẫn phải được triển khai ở đúng ranh giới.

### 3.6. Giao dịch và trạng thái khó được quản lý

Tạo đơn hàng có thể bao gồm nhiều thao tác liên quan: kiểm tra tồn kho, giữ hàng, lưu đơn hàng và ghi nhận thanh toán. Nếu các thao tác được rải trong mã xử lý request, khó nhìn ra đâu là một đơn vị công việc cần được thực hiện nhất quán.

Ví dụ, đơn hàng đã được lưu nhưng tồn kho chưa được cập nhật có thể tạo ra trạng thái không hợp lệ. Phần nghiệp vụ hoặc trường hợp sử dụng cần xác định ranh giới giao dịch phù hợp để các thao tác liên quan được xử lý nhất quán.

## 4. MVC phân chia trách nhiệm như thế nào?

MVC tổ chức ứng dụng quanh ba vai trò chính. Tên gọi của chúng mô tả trách nhiệm, không bắt buộc mỗi vai trò chỉ được triển khai bằng đúng một lớp.

| Thành phần | Trách nhiệm chính | Ví dụ trong chức năng đặt hàng |
|---|---|---|
| **Model** | Đại diện trạng thái và quy tắc của ứng dụng; thực hiện hoặc hỗ trợ các thao tác nghiệp vụ | Sản phẩm, đơn hàng, quy tắc tồn kho, dịch vụ tạo đơn, thành phần lưu trữ |
| **View** | Trình bày dữ liệu cho người dùng và cung cấp cách tương tác | Biểu mẫu đặt hàng, trang xác nhận, thông báo lỗi |
| **Controller** | Tiếp nhận tương tác, chuyển dữ liệu request thành đầu vào phù hợp, gọi nghiệp vụ và chọn phản hồi | Nhận `POST /orders`, gọi chức năng tạo đơn, trả biểu mẫu có lỗi hoặc chuyển hướng |

### Model: dữ liệu và quy tắc của ứng dụng

Model không chỉ có nghĩa là một lớp chứa các thuộc tính hoặc một bản ghi cơ sở dữ liệu. Trong kiến trúc MVC, Model đại diện cho trạng thái và hành vi nghiệp vụ mà ứng dụng cần bảo vệ.

Với chức năng đặt hàng, Model có thể bao gồm:

- Đối tượng `Product` biểu diễn sản phẩm và các điều kiện liên quan đến tồn kho.
- Đối tượng `Order` biểu diễn đơn hàng và trạng thái của đơn hàng.
- Dịch vụ hoặc trường hợp sử dụng tạo đơn hàng, tính giá và áp dụng chính sách giảm giá.
- Thành phần repository hỗ trợ đọc và lưu trạng thái.

Model cần giữ các quy tắc quan trọng để mọi kênh truy cập đều áp dụng nhất quán. Ví dụ, dù request đến từ trang web hay API, số lượng đặt hàng vẫn phải thỏa mãn quy tắc của ứng dụng.

### View: tập trung vào cách trình bày

View nhận dữ liệu cần hiển thị và chuyển chúng thành giao diện. View có thể hiển thị tên sản phẩm, tổng tiền, lỗi theo trường và hướng dẫn người dùng sửa biểu mẫu.

View không nên tự quyết định một đơn hàng có được phép tạo hay không, cũng không nên tự truy vấn cơ sở dữ liệu để tìm giá. Những quyết định đó thuộc về Model hoặc các thành phần nghiệp vụ được Model sử dụng. View cũng cần escape dữ liệu khi đưa nội dung động vào HTML.

### Controller: điều phối tương tác

Controller là điểm tiếp nhận request hoặc sự kiện từ người dùng. Controller đọc dữ liệu request, phối hợp việc chuyển đổi và kiểm tra định dạng, gọi chức năng nghiệp vụ, sau đó quyết định phản hồi phù hợp.

Controller nên giữ vai trò điều phối. Nếu Controller tự tính giá, áp dụng chính sách giảm giá, cập nhật tồn kho và tạo câu SQL, nó đang hấp thụ trách nhiệm của Model và lớp lưu trữ.

> Trong một số framework web, từ `Model` còn được dùng cho đối tượng chứa thuộc tính được đưa từ Controller sang View. Đối tượng truyền dữ liệu cho View này không đồng nghĩa với toàn bộ Model nghiệp vụ của kiến trúc MVC. Cần phân biệt hai cách dùng thuật ngữ theo ngữ cảnh.

## 5. Luồng request khi các trách nhiệm được tách rõ

Với biểu mẫu đặt hàng, luồng xử lý có thể diễn ra như sau:

1. Trình duyệt gửi `GET /orders/new`. Controller chọn View để hiển thị biểu mẫu.
2. Người dùng nhập mã sản phẩm, số lượng và mã giảm giá rồi gửi `POST /orders`.
3. Controller tiếp nhận request và chuyển dữ liệu sang một đối tượng đầu vào có cấu trúc rõ ràng.
4. Ứng dụng kiểm tra định dạng và các ràng buộc đầu vào cơ bản, chẳng hạn số lượng phải là số nguyên dương.
5. Controller gọi chức năng tạo đơn hàng trong Model.
6. Model kiểm tra các quy tắc nghiệp vụ, thực hiện thao tác cần thiết và lưu trạng thái.
7. Controller nhận kết quả. Nếu có lỗi đầu vào hoặc lỗi nghiệp vụ có thể khắc phục, Controller đưa lỗi trở lại View; nếu thành công, Controller chuyển hướng đến trang chi tiết đơn hàng.
8. View trình bày kết quả cho người dùng.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant C as Controller
    participant M as Model / nghiệp vụ
    participant DB as Kho dữ liệu
    participant V as View

    User->>Browser: Gửi biểu mẫu đặt hàng
    Browser->>C: POST /orders
    C->>C: Đọc và kiểm tra định dạng đầu vào
    C->>M: createOrder(command)
    M->>DB: Đọc sản phẩm và lưu đơn hàng
    DB-->>M: Dữ liệu và kết quả lưu
    M-->>C: Kết quả nghiệp vụ
    C->>V: Chọn dữ liệu cho trang phản hồi
    V-->>Browser: HTML
    Browser-->>User: Hiển thị kết quả
~~~

Sơ đồ mô tả một luồng thành công ở mức khái quát. Trong thực tế, khi kiểm tra đầu vào hoặc nghiệp vụ thất bại, Controller có thể trả lại biểu mẫu cùng thông báo lỗi. Khi tạo đơn thành công, ứng dụng web thường dùng mẫu **Post/Redirect/Get**: phản hồi POST bằng chuyển hướng, sau đó trình duyệt gửi GET để tải trang kết quả. Cách này giúp việc tải lại trang kết quả không vô tình gửi lại biểu mẫu POST.

## 6. Phác thảo cách phân chia trong Java

Có thể tổ chức chức năng tạo đơn hàng thành các thành phần có hợp đồng rõ ràng. Ví dụ sau dùng cú pháp gần với Spring MVC để minh họa vai trò; tên lớp và phương thức có thể khác tùy framework.

### Đối tượng tiếp nhận dữ liệu biểu mẫu

Không nên mặc định gắn trực tiếp dữ liệu trình duyệt vào đối tượng nghiệp vụ hoặc đối tượng lưu trữ. Một lớp đầu vào riêng giúp xác định rõ những trường mà request được phép gửi.

~~~java
public class CreateOrderForm {
    @NotBlank
    private String productId;

    @NotNull
    @Positive
    private Integer quantity;

    private String couponCode;

    // Getter và setter
}
~~~

Đối tượng này là hợp đồng dữ liệu của biểu mẫu. Các ràng buộc như trường bắt buộc, kiểu dữ liệu hoặc số lượng dương có thể được kiểm tra trong quá trình binding và validation. Khi chuyển sang nghiệp vụ, ứng dụng có thể ánh xạ nó thành một command phù hợp.

### Controller tiếp nhận và điều phối

~~~java
@Controller
@RequestMapping("/orders")
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public String create(
            @Valid @ModelAttribute("form") CreateOrderForm form,
            BindingResult errors
    ) {
        if (errors.hasErrors()) {
            return "orders/new";
        }

        try {
            CreateOrderCommand command = new CreateOrderCommand(
                    form.getProductId(),
                    form.getQuantity(),
                    form.getCouponCode()
            );
            OrderReceipt receipt = orderService.create(command);
            return "redirect:/orders/" + receipt.id();
        } catch (OrderRuleViolation ex) {
            errors.reject(ex.getCode(), ex.getMessage());
            return "orders/new";
        }
    }
}
~~~

Controller thực hiện các việc thuộc ranh giới web: nhận biểu mẫu, kiểm tra lỗi binding, chuyển dữ liệu thành command, gọi dịch vụ nghiệp vụ và chọn tên View hoặc URL chuyển hướng. Controller không tự tính tổng tiền hay cập nhật tồn kho.

Trong một ứng dụng thực tế, cần đặt đối tượng `BindingResult` ngay sau tham số được kiểm tra theo quy ước của framework. Cách ánh xạ lỗi nghiệp vụ thành lỗi toàn biểu mẫu hoặc lỗi theo trường cũng cần được thiết kế nhất quán để View có thể hiển thị đúng vị trí.

### Model thực hiện quy tắc nghiệp vụ

~~~java
public class OrderService {
    private final ProductRepository products;
    private final OrderRepository orders;
    private final PricingPolicy pricingPolicy;

    public OrderReceipt create(CreateOrderCommand command) {
        Product product = products.getRequired(command.productId());

        if (!product.canSupply(command.quantity())) {
            throw new OrderRuleViolation("out_of_stock");
        }

        Money total = pricingPolicy.calculate(
                product,
                command.quantity(),
                command.couponCode()
        );

        Order order = Order.create(product, command.quantity(), total);
        orders.save(order);

        return new OrderReceipt(order.getId());
    }
}
~~~

Đây là phác thảo để thể hiện ranh giới trách nhiệm. Trong ứng dụng có cập nhật tồn kho hoặc nhiều thao tác ghi liên quan, dịch vụ cần phối hợp giao dịch phù hợp; ví dụ, việc giữ hàng và lưu đơn phải được thiết kế để tránh tạo trạng thái dở dang. Các repository và chính sách giá cũng cần có hợp đồng rõ ràng.

### View trình bày dữ liệu và lỗi

View có thể hiển thị một biểu mẫu HTML tương ứng với hợp đồng đầu vào:

~~~html
<form method="post" action="/orders">
    <label for="productId">Mã sản phẩm</label>
    <input id="productId" name="productId" type="text">

    <label for="quantity">Số lượng</label>
    <input id="quantity" name="quantity" type="number" min="1">

    <label for="couponCode">Mã giảm giá</label>
    <input id="couponCode" name="couponCode" type="text">

    <button type="submit">Đặt hàng</button>
</form>
~~~

Khi dùng framework có cơ chế bảo vệ CSRF, biểu mẫu phải gửi token theo đúng cấu hình của ứng dụng. View cũng cần hiển thị lại giá trị hợp lệ đã nhập và thông báo lỗi phù hợp, đồng thời escape dữ liệu động theo ngữ cảnh HTML.

## 7. Phân biệt kiểm tra đầu vào và quy tắc nghiệp vụ

Một điểm dễ nhầm khi áp dụng MVC là đưa toàn bộ việc kiểm tra dữ liệu vào Controller. Không phải mọi quy tắc đều là kiểm tra biểu mẫu.

| Loại kiểm tra | Ví dụ | Vị trí phù hợp |
|---|---|---|
| Định dạng và cấu trúc request | Thiếu `productId`, `quantity` không chuyển được thành số, chuỗi vượt giới hạn cho phép | Binding, DTO/form và validation ở ranh giới request |
| Quy tắc nghiệp vụ | Sản phẩm ngừng bán, tồn kho không đủ, mã giảm giá hết hạn, khách hàng không đủ điều kiện mua | Model, domain hoặc dịch vụ nghiệp vụ |
| Quyền truy cập | Người dùng có được xem đơn hàng này hoặc thực hiện thao tác này không? | Cơ chế xác thực và phân quyền của ứng dụng; kiểm tra quyền trên tài nguyên tại phía máy chủ |
| An toàn khi trình bày và lưu trữ | Dữ liệu có được escape khi xuất HTML và truyền vào SQL theo cách an toàn không? | View và lớp truy cập dữ liệu, cùng các cơ chế bảo mật liên quan |

Ví dụ, `quantity` không phải số nguyên là lỗi định dạng request. Nhưng số lượng lớn hơn tồn kho là quy tắc nghiệp vụ vì nó phụ thuộc vào trạng thái hiện tại của sản phẩm. Quy tắc tồn kho phải được thực thi ở phía Model ngay cả khi Controller đã kiểm tra dữ liệu biểu mẫu.

Tương tự, một biểu mẫu có thể không hiển thị trường `price`, nhưng điều đó không có nghĩa máy chủ có thể tin giá do trình duyệt gửi lên. Giá cần được xác định từ nguồn dữ liệu đáng tin cậy và chính sách nghiệp vụ ở phía máy chủ.

## 8. Kiểm thử cũng được phân chia theo trách nhiệm

Khi ranh giới giữa các thành phần rõ ràng, mỗi loại kiểm thử có thể tập trung vào một câu hỏi cụ thể:

- **Kiểm thử Model hoặc dịch vụ nghiệp vụ:** Với sản phẩm có tồn kho là 2, yêu cầu mua 3 sản phẩm phải bị từ chối. Kiểm thử tập trung vào quy tắc và kết quả nghiệp vụ.
- **Kiểm thử Controller:** Khi gửi số lượng không hợp lệ, ứng dụng trả lại biểu mẫu với lỗi phù hợp. Khi dữ liệu hợp lệ, Controller gọi chức năng nghiệp vụ và chuyển hướng đúng.
- **Kiểm thử tích hợp:** Khi tạo đơn hàng thành công, dữ liệu đơn hàng và các thay đổi liên quan được lưu nhất quán.
- **Kiểm thử View:** Biểu mẫu có đúng tên trường, hiển thị lỗi dễ hiểu và trình bày dữ liệu động an toàn.

Không phải mọi ứng dụng đều cần cùng một số lượng lớp hoặc cùng một bộ kiểm thử. Mục tiêu là kiểm tra đúng trách nhiệm ở nơi nó được đặt, nhờ đó lỗi được khoanh vùng dễ hơn.

## 9. Tách trách nhiệm mà không chia lớp máy móc

MVC không yêu cầu tạo thật nhiều lớp chỉ để có đủ ba chữ Model, View và Controller. Một chức năng nhỏ có thể dùng ít thành phần hơn, miễn là ranh giới trách nhiệm vẫn dễ hiểu.

Một số dấu hiệu cho thấy Controller đang làm quá nhiều việc:

- Controller chứa công thức tính giá, chính sách giảm giá hoặc quy tắc chuyển trạng thái.
- Controller trực tiếp điều khiển nhiều câu truy vấn và cập nhật dữ liệu.
- Controller tự tạo chuỗi HTML lớn hoặc quyết định chi tiết bố cục giao diện.
- Nhiều Controller lặp lại cùng một quy tắc nghiệp vụ.
- Muốn kiểm thử một quy tắc nghiệp vụ phải dựng đầy đủ request, response và giao diện.

Khi gặp các dấu hiệu này, hãy xác định phần nào là quy tắc của ứng dụng, phần nào là chi tiết HTTP, phần nào là trình bày, rồi chuyển trách nhiệm về thành phần phù hợp. Không cần tách một phương thức đơn giản thành nhiều lớp nếu việc đó không làm ranh giới rõ hơn.

## 10. Checklist nhận diện vấn đề

Khi xem xét một chức năng web, có thể tự hỏi:

1. Nếu thay HTML bằng JSON, quy tắc nghiệp vụ có phải viết lại không?
2. Nếu một quy tắc nghiệp vụ thay đổi, có phải sửa nhiều Controller hoặc nhiều trang không?
3. Có thể kiểm thử quy tắc chính mà không cần tạo request HTTP và dựng giao diện không?
4. Dữ liệu từ trình duyệt có được kiểm tra và chuyển thành hợp đồng đầu vào rõ ràng không?
5. Giá, quyền và trạng thái quan trọng có được xác định ở phía máy chủ không?
6. Lỗi đầu vào, lỗi nghiệp vụ và lỗi kỹ thuật có cách xử lý phù hợp không?
7. View có tập trung vào trình bày, Controller có tập trung vào điều phối và Model có giữ các quy tắc ứng dụng không?

Nếu nhiều câu trả lời cho thấy các phần đang phụ thuộc trực tiếp vào nhau, đó là dấu hiệu nên xem lại cách tổ chức theo MVC.

## Kết luận

Khi giao diện, xử lý đầu vào và nghiệp vụ trộn lẫn, ứng dụng dễ phát sinh liên kết chặt, lặp quy tắc, khó kiểm thử và khó kiểm soát lỗi cũng như bảo mật. MVC giúp làm rõ ba vai trò: Model giữ trạng thái và quy tắc ứng dụng, View trình bày thông tin, Controller tiếp nhận tương tác và điều phối luồng request. Ranh giới này giúp mỗi phần có thể thay đổi và được kiểm thử với phạm vi rõ ràng hơn, đồng thời giữ cho quy tắc nghiệp vụ nhất quán giữa các cách truy cập ứng dụng.
