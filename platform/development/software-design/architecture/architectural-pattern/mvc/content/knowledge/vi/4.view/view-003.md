# Phân biệt định dạng hiển thị và tính toán nghiệp vụ

Trong mô hình **Model–View–Controller (MVC)**, View chịu trách nhiệm trình bày dữ liệu để người dùng hiểu và tương tác với ứng dụng. View có thể định dạng ngày giờ, số tiền, số lượng, phần trăm, văn bản và trạng thái hiển thị. Tuy nhiên, View không nên tự quyết định giá bán, mức giảm giá, thuế phải thu, quyền được mua hàng hoặc điều kiện chuyển trạng thái của đơn hàng. Những quyết định đó thuộc về Model và các thành phần nghiệp vụ mà Model sử dụng.

Hai loại công việc đôi khi trông khá giống nhau vì cả hai đều có thể dùng phép toán hoặc biến đổi dữ liệu. Ví dụ, định dạng một số thành chuỗi có dấu phân cách hàng nghìn là công việc trình bày; tính số tiền khách phải trả sau khi áp dụng chính sách giảm giá là công việc nghiệp vụ. Phân biệt đúng giúp nhiều màn hình và nhiều kênh truy cập sử dụng cùng một kết quả, đồng thời tránh để giao diện trở thành nơi thực thi quy tắc quan trọng.

## 1. Định dạng hiển thị và tính toán nghiệp vụ khác nhau ở đâu?

**Định dạng hiển thị** chuyển một giá trị đã có thành cách biểu diễn phù hợp với người xem hoặc kênh giao tiếp. Nó trả lời câu hỏi: *Nên trình bày giá trị này như thế nào?*

Ví dụ:

- Hiển thị `1234567.5` thành `1.234.567,50 ₫` theo quy ước tiếng Việt.
- Hiển thị một thời điểm thành `19/11/2026 14:30` theo múi giờ và ngôn ngữ của người dùng.
- Hiển thị trạng thái nội bộ `PENDING_PAYMENT` thành nhãn “Chờ thanh toán”.
- Hiển thị một tỷ lệ đã được tính là `0,15` thành `15%`.
- Cắt ngắn một tiêu đề dài để vừa chiều rộng thẻ giao diện.

**Tính toán nghiệp vụ** xác định kết quả theo quy tắc của ứng dụng. Nó trả lời câu hỏi: *Điều gì phải xảy ra hoặc giá trị nghiệp vụ đúng là bao nhiêu?*

Ví dụ:

- Tính giá phải trả sau khi áp dụng mã giảm giá hợp lệ.
- Xác định thuế, phí vận chuyển hoặc hoa hồng theo chính sách.
- Kiểm tra số lượng đặt hàng có vượt tồn kho hay không.
- Xác định người dùng có đủ điều kiện nhận ưu đãi.
- Xác định một đơn hàng có được chuyển từ trạng thái chờ thanh toán sang đã xác nhận hay không.

| Tiêu chí | Định dạng hiển thị | Tính toán nghiệp vụ |
|---|---|---|
| Mục tiêu | Giúp người dùng đọc và hiểu dữ liệu | Xác định kết quả hoặc quyết định của ứng dụng |
| Phụ thuộc chính | Locale, múi giờ hiển thị, kiểu thiết bị, quy cách trình bày | Chính sách, trạng thái, dữ liệu miền nghiệp vụ |
| Kết quả thường là | Chuỗi, nhãn, cấu trúc hiển thị | Giá trị nghiệp vụ, kết quả, quyết định hoặc lỗi nghiệp vụ |
| Nơi phù hợp | View, formatter, presenter hoặc lớp chuẩn bị dữ liệu trình bày | Model, domain object, domain service hoặc application service |
| Khi thay đổi | Thường do yêu cầu giao diện hoặc ngôn ngữ | Có thể ảnh hưởng đến giá, quyền lợi, trạng thái hoặc dữ liệu được lưu |

Một phép biến đổi có dùng toán học chưa chắc là tính toán nghiệp vụ. Chia một số cho 100 để hiển thị phần trăm có thể chỉ là định dạng. Ngược lại, một câu lệnh `if` ngắn quyết định khách hàng có được miễn phí vận chuyển hay không vẫn là quy tắc nghiệp vụ.

## 2. Vì sao View không nên tự tính toán nghiệp vụ?

View thường nằm gần dữ liệu hiển thị nên có vẻ thuận tiện khi đặt thêm công thức vào template hoặc component. Nhưng cách làm đó tạo ra một số vấn đề.

### 2.1. Cùng một quy tắc có thể cho kết quả khác nhau

Một ứng dụng bán hàng có thể hiển thị tổng tiền ở trang giỏ hàng, trang xác nhận, email hóa đơn và API di động. Nếu mỗi View tự tính giảm giá hoặc phí vận chuyển, các công thức có thể khác nhau sau một vài lần sửa.

Ví dụ, trang giỏ hàng áp dụng mã giảm giá trước phí vận chuyển, còn trang xác nhận lại trừ giảm giá sau khi cộng phí. Người dùng nhìn thấy hai tổng tiền khác nhau cho cùng một đơn hàng. Nguyên nhân là quy tắc đã bị sao chép vào nhiều nơi trình bày.

### 2.2. Quy tắc khó được dùng lại ngoài giao diện hiện tại

Nghiệp vụ có thể được gọi từ nhiều điểm vào:

- Trang web truyền thống.
- API cho ứng dụng di động.
- Tác vụ nền xử lý đơn hàng.
- Công cụ nội bộ cho nhân viên.
- Một tiến trình nhập dữ liệu hoặc tích hợp đối tác.

Nếu phép tính chỉ nằm trong template HTML, các kênh khác không thể gọi lại một cách tự nhiên. Nhóm phát triển có thể phải sao chép công thức hoặc tạo một luồng đặc biệt, khiến kết quả không còn nhất quán.

### 2.3. Kiểm thử nghiệp vụ trở nên khó hơn

Muốn kiểm tra chính sách giảm giá nhưng công thức nằm trong View, người viết test có thể phải khởi tạo template engine, tạo model hiển thị và kiểm tra chuỗi HTML. Kiểm thử khi đó bị phụ thuộc vào cấu trúc giao diện.

Nếu phép tính nằm trong một thành phần nghiệp vụ, có thể truyền dữ liệu đầu vào và xác minh kết quả trực tiếp. View chỉ cần được kiểm tra rằng nó trình bày kết quả được cung cấp đúng cách.

### 2.4. Giao diện có thể trở thành nguồn quyết định không đáng tin cậy

Trình duyệt và dữ liệu hiển thị không phải nơi bảo vệ quy tắc. Người dùng có thể sửa HTML, JavaScript hoặc gửi request trực tiếp. Việc ẩn nút mua hàng, vô hiệu hóa trường nhập hoặc tính một mức giá trong JavaScript không ngăn được request giả mạo.

Máy chủ phải xác định lại giá, quyền, trạng thái và điều kiện nghiệp vụ khi xử lý thao tác. View chỉ hỗ trợ người dùng hiểu kết quả và thao tác thuận tiện.

### 2.5. Thay đổi giao diện có thể vô tình thay đổi kết quả nghiệp vụ

Khi công thức nằm trong template, một người chỉ định chỉnh sửa bố cục có thể vô tình thay đổi thứ tự phép tính, điều kiện hoặc cách làm tròn. Điều này khiến việc thay theme, chuyển từ HTML sang JSON hoặc bổ sung ngôn ngữ mới trở nên rủi ro hơn.

## 3. Nhận diện những phép biến đổi thuộc về View

Một phép biến đổi thường thuộc về trình bày nếu nó chỉ thay đổi cách biểu diễn của một kết quả đã được xác định, không làm thay đổi ý nghĩa nghiệp vụ hoặc trạng thái ứng dụng.

### 3.1. Định dạng số và tiền tệ

Cùng một giá trị có thể được trình bày theo nhiều locale:

| Giá trị số | Locale hoặc quy ước | Cách hiển thị minh họa |
|---:|---|---|
| 1234567.5 | Việt Nam | 1.234.567,50 |
| 1234567.5 | Hoa Kỳ | 1,234,567.50 |
| 1234567.5 | Đức | 1.234.567,50 |

View có thể chọn dấu thập phân, dấu phân nhóm, ký hiệu tiền tệ và số chữ số hiển thị dựa trên locale. Nó không nên tự xác định giá trị phải thu bằng cách áp dụng giảm giá hoặc thuế.

### 3.2. Định dạng ngày giờ

Một thời điểm có thể được lưu dưới dạng `Instant` và hiển thị theo múi giờ của người dùng. Ví dụ, cùng một thời điểm có thể được trình bày thành giờ Việt Nam hoặc giờ UTC.

Việc chuyển một thời điểm sang định dạng “19/11/2026 21:30” là công việc hiển thị. Nhưng quyết định một giao dịch có đến hạn hay không cần dựa trên quy tắc thời gian của nghiệp vụ, múi giờ quy định cho nghiệp vụ và thời điểm hiện tại đáng tin cậy ở máy chủ.

### 3.3. Nhãn, văn bản và trạng thái dễ đọc

Model có thể trả về mã trạng thái `PENDING_PAYMENT`. View ánh xạ mã đó thành “Chờ thanh toán” hoặc một nhãn đã dịch theo ngôn ngữ hiện tại.

View cũng có thể chọn biểu tượng, màu sắc hoặc cách trình bày tương ứng với trạng thái. Màu xanh không làm cho đơn hàng trở thành hợp lệ; đó chỉ là cách thể hiện trạng thái đã được nghiệp vụ xác định.

### 3.4. Bố cục và biến đổi phục vụ trải nghiệm

Các thao tác sau thường thuộc View:

- Cắt ngắn văn bản dài và hiển thị dấu ba chấm.
- Chia danh sách thành các nhóm hoặc trang để người dùng dễ theo dõi.
- Hiển thị ngày tương đối như “3 giờ trước” từ thời điểm đã có.
- Chọn thứ tự trình bày các cột trong bảng.
- Hiển thị hoặc ẩn phần trợ giúp dựa trên dữ liệu và quyền đã được máy chủ cung cấp.

Tuy nhiên, cần xem mục đích của thao tác. Phân trang một danh sách để trình bày thường thuộc giao diện. Chọn 10 hồ sơ đủ điều kiện theo một chính sách ưu tiên để cấp quyền lợi lại là nghiệp vụ. Hai thao tác có thể đều dùng sắp xếp và giới hạn số phần tử, nhưng ý nghĩa của chúng khác nhau.

## 4. Nhận diện những phép tính thuộc về nghiệp vụ

Một phép tính thuộc về nghiệp vụ nếu kết quả của nó ảnh hưởng đến quyết định, quyền lợi, nghĩa vụ, trạng thái hoặc dữ liệu mà ứng dụng quản lý.

### 4.1. Giá, giảm giá, thuế và phí

Ví dụ, tổng tiền một đơn hàng có thể được xác định từ giá từng mặt hàng, số lượng, chính sách giảm giá, thuế và phí vận chuyển. Đây là kết quả có ý nghĩa tài chính và phải được tính nhất quán ở máy chủ.

View có thể hiển thị bảng phân rã:

| Khoản mục | Giá trị do nghiệp vụ cung cấp |
|---|---:|
| Tiền hàng | 500.000 ₫ |
| Giảm giá | -50.000 ₫ |
| Phí vận chuyển | 20.000 ₫ |
| Thuế | 0 ₫ |
| **Tổng phải trả** | **470.000 ₫** |

View định dạng từng giá trị. Nó không tự suy ra giảm giá 10% hoặc quyết định phí vận chuyển bằng 0. Các con số trong bảng là kết quả ví dụ; ứng dụng phải lấy chúng từ chính sách và dữ liệu thật.

### 4.2. Điều kiện và quyền lợi

Các câu hỏi sau đều cần câu trả lời từ nghiệp vụ:

- Khách hàng có đủ điều kiện dùng mã giảm giá không?
- Sản phẩm có được bán ở khu vực này không?
- Người dùng có thể hủy đơn ở trạng thái hiện tại không?
- Khách hàng có được miễn phí vận chuyển không?
- Giao dịch có vượt giới hạn tín dụng không?

View có thể hiển thị kết quả `eligible = false` thành thông báo dễ hiểu. Nó không nên tự quyết định điều kiện đủ tư cách bằng cách đọc các trường rồi tạo ra quy tắc riêng.

### 4.3. Chuyển trạng thái và tính toán ảnh hưởng dữ liệu

Nếu một thao tác làm thay đổi trạng thái đơn hàng, số lượng tồn kho, điểm thưởng hoặc số dư tài khoản, quyết định phải nằm ở phía nghiệp vụ. View chỉ gửi ý định thao tác và hiển thị kết quả.

### 4.4. Tính toán có tác động đến báo cáo hoặc cam kết

Một chỉ số được hiển thị trên dashboard có thể là phép tính nghiệp vụ nếu nó được dùng làm cơ sở cho thưởng, hạn mức, cảnh báo hoặc quyết định quản lý. Không nên đưa công thức đó vào template chỉ vì kết quả đang được hiển thị ở một biểu đồ.

## 5. Ranh giới tinh tế: làm tròn và chuyển đổi đơn vị

Một số trường hợp dễ nhầm vì vừa liên quan đến con số vừa liên quan đến cách trình bày. Cần xét xem quy tắc đó có ảnh hưởng đến ý nghĩa và kết quả nghiệp vụ hay không.

### 5.1. Làm tròn tiền

Có hai việc khác nhau:

- **Làm tròn theo chính sách tài chính:** Ví dụ, quy định thuế được tính và làm tròn đến hai chữ số thập phân ở từng dòng hàng hay trên tổng hóa đơn. Đây là quy tắc nghiệp vụ, vì nó ảnh hưởng số tiền phải trả hoặc số tiền được ghi nhận.
- **Giới hạn chữ số khi trình bày:** Ví dụ, một chỉ số thống kê có nhiều chữ số thập phân được hiển thị với hai chữ số để dễ đọc. Đây có thể là định dạng hiển thị nếu giá trị gốc và ý nghĩa nghiệp vụ không bị thay đổi.

Không nên dùng `double` cho phép tính tiền cần độ chính xác thập phân. Trong Java, `BigDecimal` thường phù hợp hơn, với scale và rounding mode được chọn theo chính sách nghiệp vụ. View nhận kết quả đã được tính chính xác rồi định dạng nó.

### 5.2. Chuyển đổi đơn vị

Chuyển 1.500 mét thành “1,5 km” chỉ để trình bày thường thuộc View. Nhưng nếu ứng dụng tính phí giao hàng theo kilomet, xác định giới hạn vận chuyển hoặc áp dụng quy định an toàn theo đơn vị đo, việc chuyển đổi và làm tròn có thể là một phần của nghiệp vụ.

### 5.3. Múi giờ và thời hạn

Định dạng một `Instant` theo múi giờ hiển thị của người dùng thuộc View. Tính thời điểm hết hạn của phiếu giảm giá lại thuộc nghiệp vụ và cần tuân theo múi giờ hoặc quy ước thời gian đã xác định cho chính sách đó.

### 5.4. Phần trăm

Nhân tỷ lệ `0.15` với 100 để hiển thị “15%” thường là định dạng. Nhưng quyết định một khách hàng được giảm 15% hay không, và tính số tiền giảm tương ứng, là nghiệp vụ.

Quy tắc thực tế là: nếu việc làm tròn, chuyển đổi hoặc lựa chọn giá trị có thể thay đổi quyền lợi, nghĩa vụ, điều kiện hoặc dữ liệu được lưu, hãy xử lý nó ở nghiệp vụ. Nếu chỉ thay đổi cách biểu diễn của một kết quả đã xác định, hãy để View hoặc formatter đảm nhiệm.

## 6. Ví dụ sai: View tự tính tổng tiền

Giả sử một template Thymeleaf hiển thị đơn hàng bằng cách tự nhân đơn giá với số lượng và tự trừ giảm giá:

~~~html
<table>
    <tr th:each="item : ${order.items}">
        <td th:text="${item.name}">Sản phẩm</td>
        <td th:text="${item.unitPrice}">Đơn giá</td>
        <td th:text="${item.quantity}">Số lượng</td>
        <td th:text="${item.unitPrice * item.quantity}">
            Thành tiền
        </td>
    </tr>
</table>

<p th:text="${order.subtotal * 0.9}">
    Tổng sau giảm giá
</p>
~~~

Template đang tự giả định mọi mặt hàng đều được giảm 10%. Nó cũng không thể hiện rõ chính sách áp dụng cho từng dòng, giới hạn giảm tối đa, mã giảm giá hết hạn, thuế hoặc quy tắc làm tròn. Khi trang xác nhận hoặc API cần cùng kết quả, nhóm phát triển có thể sao chép công thức này.

Một biểu thức nhân đơn giá với số lượng đôi khi chỉ là phép tính hiển thị trong ứng dụng rất đơn giản. Nhưng khi thành tiền được dùng để thanh toán, ghi nhận đơn hàng hoặc áp dụng chính sách giá, nó đã trở thành kết quả nghiệp vụ. Đừng xác định ranh giới chỉ dựa vào việc công thức ngắn hay dài.

## 7. Cách tổ chức phù hợp: nghiệp vụ tính, View định dạng

Model hoặc dịch vụ nghiệp vụ nên cung cấp các giá trị đã được xác định. Controller chuẩn bị dữ liệu cho View, còn View định dạng những giá trị đó theo ngôn ngữ và cách trình bày hiện tại.

### 7.1. Kết quả nghiệp vụ có cấu trúc

Ví dụ sau minh họa các kiểu dữ liệu mà nghiệp vụ có thể trả về:

~~~java
public record Money(BigDecimal amount, Currency currency) {}

public record OrderLineSummary(
        String productName,
        int quantity,
        Money unitPrice,
        Money lineTotal
) {}

public record OrderSummary(
        String orderNumber,
        List<OrderLineSummary> lines,
        Money subtotal,
        Money discount,
        Money shippingFee,
        Money tax,
        Money total,
        Instant createdAt,
        OrderStatus status
) {}
~~~

Các giá trị `lineTotal`, `discount`, `tax` và `total` được xác định trong nghiệp vụ theo chính sách giá. Kết quả trả về giữ kiểu dữ liệu có ý nghĩa, chẳng hạn `Money`, thay vì chỉ trả một chuỗi đã gắn ký hiệu tiền tệ.

### 7.2. Dịch vụ nghiệp vụ tính kết quả

~~~java
public class OrderPricingService {
    private final DiscountPolicy discountPolicy;
    private final TaxPolicy taxPolicy;

    public OrderSummary calculate(Order order) {
        Money subtotal = calculateSubtotal(order);
        Money discount = discountPolicy.calculate(order, subtotal);
        Money taxableAmount = subtotal.subtract(discount);
        Money tax = taxPolicy.calculate(order, taxableAmount);
        Money shippingFee = calculateShippingFee(order);

        Money total = taxableAmount
                .add(tax)
                .add(shippingFee);

        return new OrderSummary(
                order.getNumber(),
                buildLineSummaries(order),
                subtotal,
                discount,
                shippingFee,
                tax,
                total,
                order.getCreatedAt(),
                order.getStatus()
        );
    }
}
~~~

Đây là phác thảo về phân chia trách nhiệm. Các phương thức `Money.add` và `subtract` trong ứng dụng thực tế cần kiểm tra cùng loại tiền tệ. Chính sách thuế, thứ tự áp dụng giảm giá và cách làm tròn phải được định nghĩa rõ theo nghiệp vụ; không thể suy ra chúng chỉ từ đoạn mã minh họa.

### 7.3. Controller đưa kết quả sang View

~~~java
@GetMapping("/orders/{orderNumber}")
public String detail(
        @PathVariable String orderNumber,
        Model model
) {
    OrderSummary summary = orderQueryService.getSummary(orderNumber);
    model.addAttribute("order", summary);
    return "orders/detail";
}
~~~

Controller nhận dữ liệu từ dịch vụ truy vấn và đưa vào model của framework để View sử dụng. Controller không tự tính lại tổng tiền.

### 7.4. View chỉ định dạng và trình bày

View có thể dùng formatter để hiển thị số tiền theo locale:

~~~java
@Component
public class MoneyFormatter {
    public String format(Money money, Locale locale) {
        NumberFormat format = NumberFormat.getCurrencyInstance(locale);
        format.setCurrency(money.currency());
        format.setMinimumFractionDigits(
                Math.max(0, money.currency().getDefaultFractionDigits())
        );
        format.setMaximumFractionDigits(
                Math.max(0, money.currency().getDefaultFractionDigits())
        );
        return format.format(money.amount());
    }
}
~~~

Formatter này chịu trách nhiệm biểu diễn số tiền. Nó không áp dụng giảm giá, tính thuế hoặc quyết định tổng phải thu. Trong ứng dụng thực tế, quy tắc số chữ số hiển thị cần phù hợp với loại tiền và yêu cầu sản phẩm; cấu hình hiển thị cũng không được thay thế chính sách làm tròn khi tính toán.

View có thể trình bày dữ liệu đã được cung cấp:

~~~html
<h1>Đơn hàng <span th:text="${order.orderNumber}">ORD-001</span></h1>

<table>
    <tr th:each="line : ${order.lines}">
        <td th:text="${line.productName}">Sản phẩm</td>
        <td th:text="${line.quantity}">1</td>
        <td th:text="${@moneyFormatter.format(line.unitPrice, #locale)}">
            Đơn giá
        </td>
        <td th:text="${@moneyFormatter.format(line.lineTotal, #locale)}">
            Thành tiền
        </td>
    </tr>
</table>

<p>
    Tạm tính:
    <span th:text="${@moneyFormatter.format(order.subtotal, #locale)}">
        0
    </span>
</p>
<p>
    Giảm giá:
    <span th:text="${@moneyFormatter.format(order.discount, #locale)}">
        0
    </span>
</p>
<p>
    Tổng phải trả:
    <strong th:text="${@moneyFormatter.format(order.total, #locale)}">
        0
    </strong>
</p>
~~~

Template chỉ chọn trường cần hiển thị và gọi formatter. Dữ liệu động vẫn phải được escape theo ngữ cảnh đầu ra. Nếu dùng template engine có cơ chế escape mặc định, cần giữ đúng chế độ escape thay vì đưa nội dung người dùng vào HTML thô.

## 8. Phân biệt trách nhiệm khi dùng nhiều kênh giao tiếp

Một quy tắc nghiệp vụ có thể được sử dụng bởi nhiều kênh. Mỗi kênh có cách định dạng riêng, nhưng phải dựa trên cùng kết quả nghiệp vụ.

| Kênh | Kết quả nghiệp vụ | Cách trình bày |
|---|---|---|
| Trang web | Tổng tiền, thuế, giảm giá và trạng thái đơn | Chuỗi tiền tệ theo locale, nhãn trạng thái, HTML |
| Ứng dụng di động | Cùng các giá trị và mã trạng thái | JSON, định dạng được API quy định |
| Email xác nhận | Cùng tổng tiền và thông tin đơn hàng | Mẫu email và định dạng tiền tệ phù hợp |
| Tác vụ nền | Cùng quy tắc tính và quyết định | Có thể không cần định dạng giao diện |
| Báo cáo nội bộ | Giá trị đã tính theo nghiệp vụ | Bảng, biểu đồ, định dạng số phù hợp người xem |

API nên cân nhắc trả giá trị có cấu trúc thay vì chuỗi đã định dạng theo locale của một người dùng cụ thể. Ví dụ, trả `amount` và `currency` giúp client hiển thị theo quy ước của nó, đồng thời giữ hợp đồng dữ liệu rõ ràng. Nếu API quy định một chuỗi hiển thị cụ thể, định dạng đó là một phần hợp đồng API và cần được quản lý như vậy.

## 9. Kiểm thử riêng nghiệp vụ và định dạng hiển thị

Khi hai trách nhiệm tách biệt, mỗi loại test có thể kiểm tra đúng điều cần bảo vệ.

### 9.1. Kiểm thử tính toán nghiệp vụ

Kiểm thử dịch vụ giá với các tình huống như:

- Đơn hàng không có giảm giá.
- Mã giảm giá hợp lệ.
- Mã giảm giá hết hạn hoặc không đủ điều kiện.
- Giá trị giảm vượt giới hạn tối đa.
- Thuế được tính theo đúng cơ sở tính thuế.
- Quy tắc làm tròn cho kết quả tài chính.
- Đơn hàng có nhiều mặt hàng với số lượng khác nhau.

Test nên so sánh giá trị `BigDecimal` và tiền tệ theo chính sách đã định. Không nên chỉ so sánh chuỗi hiển thị vì chuỗi còn phụ thuộc locale và formatter.

### 9.2. Kiểm thử formatter và View

Kiểm thử định dạng có thể xác minh:

- Cùng một giá trị được hiển thị đúng với locale Việt Nam và Hoa Kỳ.
- Ngày giờ được chuyển sang múi giờ hiển thị mong muốn.
- Mã trạng thái được ánh xạ thành nhãn đã dịch.
- View hiển thị đúng giá trị được cung cấp.
- Dữ liệu động được escape và không bị diễn giải thành HTML không an toàn.

### 9.3. Kiểm thử tích hợp

Kiểm thử tích hợp xác minh Controller lấy đúng kết quả nghiệp vụ, đưa dữ liệu vào View hoặc response và không tính lại kết quả. Với API, kiểm tra cấu trúc JSON và hợp đồng số tiền.

Một lỗi nghiệp vụ không nên chỉ được phát hiện bằng cách so sánh nội dung HTML. Ngược lại, lỗi định dạng ngày giờ hoặc dấu phân cách số cũng không nên làm cho test nghiệp vụ phải phụ thuộc vào locale.

## 10. Những lỗi thiết kế thường gặp

### Đưa công thức vào template

Template chứa biểu thức tính giá, thuế hoặc quyền lợi. Hãy chuyển phép tính có ý nghĩa nghiệp vụ sang Model hoặc service, sau đó cung cấp kết quả cho View.

### Trả chuỗi đã định dạng từ Model

Model trả `"1.234.500 ₫"` thay vì một giá trị tiền tệ có cấu trúc. Điều này gắn nghiệp vụ với một locale và khiến API hoặc báo cáo khó tái sử dụng giá trị. Hãy giữ kiểu dữ liệu như `Money` và định dạng tại ranh giới trình bày.

Có ngoại lệ khi một chuỗi là nội dung nghiệp vụ đã được xác định, chẳng hạn mã tham chiếu hoặc thông điệp chính thức. Nhưng không nên biến mọi giá trị thành chuỗi chỉ để tiện hiển thị.

### Dùng JavaScript ở trình duyệt làm nguồn tính giá

JavaScript có thể tính tạm tổng tiền để người dùng thấy phản hồi nhanh. Đây là hỗ trợ trải nghiệm. Máy chủ vẫn phải tính lại và xác nhận kết quả trước khi tạo đơn hoặc thu tiền.

### Dùng số dấu phẩy động cho tiền

`float` và `double` có thể biểu diễn một số thập phân gần đúng do đặc tính nhị phân. Với tiền tệ, nên dùng kiểu thập phân chính xác như `BigDecimal` và định nghĩa chính sách scale, rounding rõ ràng.

### Trộn múi giờ hiển thị với quy tắc thời hạn

Nếu View đổi múi giờ hoặc định dạng ngày, kết quả hiển thị có thể thay đổi. Điều đó không được làm thay đổi thời điểm hết hạn mà nghiệp vụ đã xác định. Hãy giữ thời điểm chuẩn và áp dụng múi giờ hiển thị riêng.

### Dùng nhãn hiển thị làm dữ liệu nghiệp vụ

Không nên lưu hoặc so sánh chuỗi “Đang xử lý” để xác định trạng thái đơn hàng. Hãy dùng mã hoặc enum ổn định như `PROCESSING`, rồi ánh xạ sang nhãn theo ngôn ngữ.

## 11. Quy trình quyết định một phép tính đặt ở đâu

Khi gặp một biểu thức trong Controller, template hoặc component giao diện, hãy tự hỏi:

1. Kết quả có ảnh hưởng đến số tiền, quyền lợi, nghĩa vụ, quyền truy cập hoặc trạng thái không?
2. Kết quả có cần giống nhau giữa Web, API, email và tác vụ nền không?
3. Quy tắc có phụ thuộc vào dữ liệu miền nghiệp vụ hoặc chính sách thay đổi theo thời gian không?
4. Nếu thay locale, theme hoặc cách hiển thị, kết quả nghiệp vụ có phải giữ nguyên không?
5. Có thể kiểm thử phép tính mà không dựng giao diện không?

Nếu kết quả ảnh hưởng đến hành vi hoặc trạng thái ứng dụng, đặt nó trong Model hoặc dịch vụ nghiệp vụ. Nếu chỉ biến đổi cách biểu diễn một kết quả đã có, đặt nó trong View hoặc formatter. Với trường hợp hỗn hợp, tách phần quyết định nghiệp vụ khỏi phần định dạng.

## 12. Checklist khi review View

- [ ] View nhận các giá trị đã được nghiệp vụ xác định.
- [ ] View không tự áp dụng chính sách giá, thuế, giảm giá hoặc phí.
- [ ] View không tự quyết định quyền hoặc tính hợp lệ của thao tác.
- [ ] Ngày giờ được định dạng theo locale và múi giờ hiển thị phù hợp.
- [ ] Số và tiền tệ được định dạng mà không làm thay đổi giá trị nghiệp vụ.
- [ ] Quy tắc làm tròn tài chính được thực hiện ở phía nghiệp vụ.
- [ ] Mã trạng thái ổn định được ánh xạ sang nhãn trình bày.
- [ ] Dữ liệu động được escape đúng ngữ cảnh.
- [ ] Nhiều kênh giao tiếp dùng chung kết quả nghiệp vụ.
- [ ] Có kiểm thử riêng cho tính toán nghiệp vụ và định dạng hiển thị.

## Kết luận

Định dạng hiển thị trả lời câu hỏi dữ liệu được trình bày như thế nào; tính toán nghiệp vụ trả lời ứng dụng phải xác định kết quả hoặc quyết định nào. View có thể định dạng tiền tệ, ngày giờ, phần trăm, nhãn trạng thái và bố cục. Model hoặc dịch vụ nghiệp vụ phải sở hữu các phép tính ảnh hưởng đến giá, thuế, quyền lợi, điều kiện và trạng thái. Khi nghiệp vụ cung cấp kết quả có cấu trúc còn View chỉ định dạng kết quả đó, ứng dụng dễ tái sử dụng quy tắc giữa nhiều kênh, kiểm thử rõ ràng và thay đổi giao diện an toàn hơn.
