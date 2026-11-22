# Nhận diện mã trộn giao diện và nghiệp vụ

Trong module **MODEL_VIEW_CONTROLLER**, ứng dụng được tổ chức để tách phần trình bày, tiếp nhận tương tác và trạng thái hoặc quy tắc nghiệp vụ. Một vấn đề thường gặp là mã giao diện bắt đầu chứa các quyết định nghiệp vụ, hoặc tầng xử lý request phải biết quá nhiều chi tiết về cách hiển thị. Ví dụ, template tự tính giá đơn hàng, JavaScript quyết định người dùng có được hoàn tiền hay không, hoặc Controller vừa truy vấn database vừa tạo HTML bằng cách nối chuỗi.

Hiện tượng này được gọi là **trộn logic giao diện và logic nghiệp vụ**. Nó khiến cùng một quy tắc có thể được triển khai khác nhau ở nhiều nơi, khó kiểm thử ngoài trình duyệt và dễ bị bỏ qua khi một chức năng được gọi qua API hoặc tác vụ nền. Cách cải thiện là xác định rõ loại logic, đặt quy tắc nghiệp vụ trong Model hoặc use case, đặt logic trình bày trong View và dùng Controller làm adapter cho request/response.

## 1. Phân biệt logic giao diện và logic nghiệp vụ

Hai loại logic có liên quan nhưng phục vụ mục đích khác nhau:

**Logic giao diện (presentation logic)** quyết định cách thông tin được trình bày và cách màn hình phản hồi với tương tác. Ví dụ:

- Định dạng ngày, tiền tệ, số lượng và văn bản theo ngôn ngữ hiện tại.
- Chọn màu sắc, biểu tượng hoặc kiểu hiển thị cho trạng thái.
- Hiển thị hoặc ẩn một vùng giao diện theo trạng thái đã được cung cấp.
- Bật/tắt trạng thái loading, mở hộp thoại hoặc chuyển tab.
- Chọn thông báo thân thiện tương ứng với một mã lỗi đã biết.
- Sắp xếp hoặc nhóm dữ liệu chỉ nhằm giúp người dùng đọc dễ hơn, nếu không làm thay đổi ý nghĩa nghiệp vụ.

**Logic nghiệp vụ (business logic)** quyết định điều gì được phép xảy ra trong hệ thống và dữ liệu phải thay đổi như thế nào. Ví dụ:

- Một đơn hàng có đủ điều kiện được xác nhận, hủy hoặc hoàn tiền hay không.
- Giá cuối cùng, thuế, chiết khấu hoặc phí giao hàng được tính theo chính sách nào.
- Người dùng có đủ hạn mức hoặc điều kiện để thực hiện giao dịch không.
- Tồn kho được giữ, trừ hoặc hoàn lại theo quy tắc nào.
- Trạng thái nào được phép chuyển sang trạng thái nào.
- Quyền sở hữu hoặc tenant nào được phép đọc và thay đổi tài nguyên.

Một cách kiểm tra nhanh là đặt câu hỏi: **nếu đổi giao diện web sang mobile app, API hoặc tác vụ nền, quyết định này có còn phải được áp dụng không?** Nếu có, nhiều khả năng đó là quy tắc nghiệp vụ và cần được bảo vệ ở phía server. Nếu quyết định chỉ thay đổi cách hiển thị, nó thường thuộc presentation layer.

## 2. Những dấu hiệu cho thấy hai loại logic đang bị trộn

Hãy chú ý các dấu hiệu sau khi review template, JavaScript và Controller:

- Template chứa công thức tính tổng tiền, chiết khấu, thuế hoặc phí thay vì chỉ hiển thị kết quả server cung cấp.
- JavaScript tự quyết định một thao tác có hợp lệ theo chính sách nghiệp vụ hay không rồi gửi request mà server không kiểm tra lại.
- View truy cập repository, gọi database hoặc gọi dịch vụ nghiệp vụ trực tiếp.
- Controller tạo HTML bằng cách nối chuỗi hoặc chứa nhiều câu lệnh định dạng giao diện.
- Cùng một quy tắc được viết lại trong template, JavaScript và service.
- Form chỉ ẩn nút thao tác theo trạng thái, nhưng endpoint server không kiểm tra trạng thái đó.
- View phải biết cấu trúc entity hoặc quan hệ persistence để lấy dữ liệu.
- Unit test cho quy tắc giá, quyền hoặc chuyển trạng thái phải chạy browser mới xác minh được.
- Thay đổi chính sách nghiệp vụ buộc phải sửa nhiều template hoặc file JavaScript.
- Một API khác không thể dùng lại hành vi vì quyết định chỉ nằm trong mã của trang web.

Không phải mọi biểu thức điều kiện trong View đều là sai. View cần điều kiện để chọn cách trình bày, chẳng hạn hiển thị nhãn “Đã giao” khi status là DELIVERED. Vấn đề xuất hiện khi View tự quyết định trạng thái nào được phép chuyển, có được hoàn tiền hay không hoặc phải tính giá cuối cùng ra sao.

## 3. Ví dụ trộn nghiệp vụ trong template

Giả sử trang chi tiết đơn hàng tự tính tổng tiền và quyết định đơn có được hủy:

~~~html
<div th:object="${page}">
  <p>Đơn hàng: <span th:text="*{code}">ORD-001</span></p>
  <p th:text="*{unitPrice * quantity}">0</p>

  <div th:if="*{status == 'PENDING' and paymentStatus != 'PAID'}">
    <form method="post" action="/orders/cancel">
      <input type="hidden" name="orderId" value="1">
      <button type="submit">Hủy đơn</button>
    </form>
  </div>
</div>
~~~

Ví dụ này có hai vấn đề khác nhau:

1. Template tự tính tiền từ giá và số lượng. Nếu chính sách tính tổng còn gồm thuế, giảm giá, phí vận chuyển hoặc quy tắc làm tròn, biểu thức trong View sẽ nhanh chóng sai lệch so với server.
2. Template tự diễn giải điều kiện hủy đơn. Dù nút bị ẩn, người dùng vẫn có thể gửi request trực tiếp. Server phải kiểm tra lại quyền và trạng thái trước khi hủy.

View có thể nhận canCancel và formattedTotal từ server để quyết định cách trình bày. Giá trị canCancel chỉ phục vụ trải nghiệm; use case hủy đơn vẫn phải xác minh điều kiện nghiệp vụ tại thời điểm thực thi.

## 4. Đưa quyết định nghiệp vụ về Model hoặc use case

Một use case có thể tính toán kết quả và trả về dữ liệu đã sẵn sàng cho màn hình:

~~~java
public record OrderDetailView(
        long id,
        String code,
        String statusLabel,
        String formattedTotal,
        boolean canCancel
) {}
~~~

Query service chuẩn bị dữ liệu:

~~~java
public class GetOrderDetail {
    private final OrderRepository orders;
    private final OrderPolicy orderPolicy;
    private final MoneyFormatter moneyFormatter;

    public OrderDetailView execute(OrderId orderId, UserId viewerId) {
        Order order = orders.findByIdAndViewer(orderId, viewerId)
                .orElseThrow(OrderNotFoundException::new);

        boolean canCancel = orderPolicy.canCancel(order, viewerId);

        return new OrderDetailView(
                order.id().value(),
                order.code(),
                order.status().displayName(),
                moneyFormatter.format(order.total()),
                canCancel
        );
    }
}
~~~

Ở đây, OrderPolicy chịu trách nhiệm quyết định nghiệp vụ; MoneyFormatter xử lý định dạng phục vụ trình bày; query service điều phối việc lấy dữ liệu và chuẩn bị view model. Tùy kiến trúc, formatter có thể nằm trong presentation adapter thay vì application layer. Điều quan trọng là phép tính giá trị đơn hàng phải được thực hiện bởi domain/application logic, còn việc thêm dấu phân cách hàng nghìn hoặc ký hiệu tiền tệ là định dạng hiển thị.

Use case thực hiện hành động hủy phải kiểm tra lại:

~~~java
public class CancelOrder {
    private final OrderRepository orders;
    private final OrderPolicy policy;

    @Transactional
    public void execute(OrderId orderId, UserId actorId) {
        Order order = orders.findByIdAndOwner(orderId, actorId)
                .orElseThrow(OrderNotFoundException::new);

        policy.ensureCanCancel(order, actorId);
        order.cancel();
        orders.save(order);
    }
}
~~~

Không dùng giá trị canCancel từ trình duyệt làm bằng chứng quyền. Client có thể thay đổi HTML hoặc tự tạo request. Quy tắc được xác minh trong use case/domain tại thời điểm thao tác.

## 5. Controller làm cầu nối giữa HTTP và use case

Controller không cần biết công thức tính tiền hay toàn bộ cấu trúc giao diện. Nó tiếp nhận request, lấy danh tính đã xác thực, gọi query/use case và trả View:

~~~java
@Controller
@RequestMapping("/orders")
public class OrderController {
    private final GetOrderDetail getOrderDetail;
    private final CancelOrder cancelOrder;

    public OrderController(
            GetOrderDetail getOrderDetail,
            CancelOrder cancelOrder) {
        this.getOrderDetail = getOrderDetail;
        this.cancelOrder = cancelOrder;
    }

    @GetMapping("/{id}")
    public String detail(
            @PathVariable long id,
            @AuthenticationPrincipal AppPrincipal principal,
            Model model) {
        model.addAttribute(
                "page",
                getOrderDetail.execute(new OrderId(id), principal.userId())
        );
        return "orders/detail";
    }

    @PostMapping("/{id}/cancel")
    public String cancel(
            @PathVariable long id,
            @AuthenticationPrincipal AppPrincipal principal,
            RedirectAttributes flash) {
        cancelOrder.execute(new OrderId(id), principal.userId());
        flash.addFlashAttribute("message", "Đơn hàng đã được hủy.");
        return "redirect:/orders/" + id;
    }
}
~~~

Controller xử lý route, principal, model và redirect. Query/use case xử lý dữ liệu nghiệp vụ. Template chỉ trình bày view model. Nếu cùng hành động hủy được gọi từ REST API hoặc worker, quy tắc vẫn được áp dụng trong use case.

## 6. View được phép quyết định điều gì?

View không cần trở thành một tệp HTML tĩnh. Nó vẫn có thể chứa logic trình bày hợp lý:

~~~html
<section th:object="${page}">
  <h1 th:text="*{code}">ORD-001</h1>
  <p th:text="*{statusLabel}">Đang chờ</p>
  <p th:text="*{formattedTotal}">0 đ</p>

  <form th:if="*{canCancel}"
        th:action="@{/orders/{id}/cancel(id=*{id})}"
        method="post">
    <button type="submit">Hủy đơn</button>
  </form>
</section>
~~~

Trong ví dụ, View chọn hiển thị nút dựa trên canCancel, một giá trị đã được server cung cấp. Điều này cải thiện trải nghiệm vì người dùng không thấy thao tác không phù hợp. Tuy nhiên, endpoint cancel vẫn phải kiểm tra quyền và trạng thái.

Các quyết định trình bày thường phù hợp trong View:

- Chọn nhãn, icon hoặc class CSS theo một trạng thái đã xác định.
- Hiển thị vùng nội dung khi một dữ liệu tùy chọn có mặt.
- Lặp qua danh sách và tạo hàng trong bảng.
- Định dạng ngày/giờ hoặc tiền tệ theo locale.
- Hiển thị lỗi validation cạnh trường tương ứng.
- Chọn layout cho màn hình nhỏ hoặc lớn.

Các quyết định nên nằm ở nghiệp vụ:

- Trạng thái nào hợp lệ để chuyển đổi.
- Giá trị cuối cùng phải thu bao nhiêu.
- Có được áp dụng ưu đãi hoặc hoàn tiền không.
- Ai có quyền thao tác trên tài nguyên.
- Hạn mức, tồn kho hoặc điều kiện tín dụng có được đáp ứng không.
- Hành động nào phải ghi nhận audit hoặc phát sự kiện.

## 7. Phân biệt định dạng và tính toán nghiệp vụ

Đôi khi cùng một phép tính nhìn giống logic trình bày nhưng thực chất là nghiệp vụ. Hãy phân biệt bằng ý nghĩa của kết quả:

| Công việc | Loại logic | Nơi phù hợp |
| --- | --- | --- |
| Hiển thị 1.250.000 ₫ theo locale | Định dạng | Presentation/formatter |
| Tính tổng dòng từ đơn giá và số lượng theo chính sách bán hàng | Nghiệp vụ | Domain/application |
| Tính thuế theo quy định và địa điểm giao hàng | Nghiệp vụ | Domain policy/use case |
| Chọn màu xanh cho trạng thái đã thanh toán | Trình bày | View/CSS |
| Quyết định thanh toán có được xem là hoàn tất | Nghiệp vụ | Domain/application |
| Chuyển timestamp sang múi giờ hiển thị của người dùng | Định dạng | Presentation |
| Xác định thời hạn thanh toán và tiền phạt quá hạn | Nghiệp vụ | Domain/application |
| Ẩn cột không được hiển thị theo cấu hình giao diện | Trình bày | View |
| Ngăn người dùng xem dữ liệu không thuộc tenant | Bảo mật/nghiệp vụ | Server-side authorization/query |

Nếu kết quả ảnh hưởng đến tiền, quyền, trạng thái, nghĩa vụ hoặc tính nhất quán dữ liệu, hãy coi đó là quyết định nghiệp vụ. Việc trình bày kết quả đã tính mới thuộc giao diện.

## 8. JavaScript phía trình duyệt không phải nơi bảo vệ quy tắc

JavaScript có thể hỗ trợ UX bằng cách kiểm tra dữ liệu sớm, tính toán tạm thời hoặc bật/tắt nút. Ví dụ, khi người dùng thay đổi số lượng, giao diện có thể hiển thị ước tính tổng tiền. Nhưng server vẫn phải tính lại giá trị cuối cùng từ dữ liệu đáng tin cậy và chính sách hiện hành.

Ví dụ không an toàn nếu server tin tổng tiền client gửi:

~~~javascript
const total = Number(unitPriceInput.value) * Number(quantityInput.value);
formData.append("total", String(total));
~~~

Người dùng có thể sửa unitPrice, total hoặc request trước khi gửi. Server không được dùng những giá trị này làm nguồn sự thật cho giao dịch.

Thiết kế tốt hơn là chỉ gửi dữ liệu đầu vào được phép:

~~~javascript
const payload = {
  productId: Number(productIdInput.value),
  quantity: Number(quantityInput.value)
};

await fetch("/api/orders", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload)
});
~~~

Server tải sản phẩm, lấy giá hiện hành, kiểm tra tồn kho, tính tổng và lưu đơn. JavaScript có thể hiển thị ước tính, nhưng response cuối cùng phải đến từ server.

## 9. Không để View truy cập trực tiếp database hoặc entity graph

Một template gọi trực tiếp repository hoặc truy cập quan hệ lazy của JPA entity có thể tạo ra nhiều vấn đề:

- View phụ thuộc vào persistence model và tên thuộc tính database.
- Vòng lặp render có thể kích hoạt N+1 query.
- Logic truy vấn bị giấu trong template, khó quan sát và kiểm thử.
- View có thể vô tình hiển thị trường nội bộ hoặc dữ liệu nhạy cảm.
- Khó tái sử dụng cùng dữ liệu cho API hoặc giao diện khác.

Thay vào đó, query/use case nên chuẩn bị một ViewModel/DTO chỉ chứa trường cần thiết:

~~~java
public record CustomerSummaryView(
        String displayName,
        String maskedEmail,
        int activeOrderCount
) {}
~~~

Query service truy vấn và ánh xạ dữ liệu:

~~~java
public CustomerSummaryView getSummary(UserId userId) {
    Customer customer = customers.findById(userId)
            .orElseThrow(CustomerNotFoundException::new);
    int activeOrders = orders.countActiveByCustomer(userId);

    return new CustomerSummaryView(
            customer.displayName(),
            emailMasker.mask(customer.email()),
            activeOrders
    );
}
~~~

View nhận dữ liệu đã được chọn lọc. Nếu cần nhiều phép định dạng phụ thuộc locale, có thể thực hiện ở presentation mapper hoặc template formatter, nhưng không để template tự truy vấn persistence.

## 10. Xử lý validation và lỗi ở đúng tầng

Validation cũng có thể bị trộn nếu mọi quy tắc được viết trong JavaScript hoặc template:

- HTML required, min và max hỗ trợ phản hồi nhanh.
- JavaScript có thể kiểm tra định dạng hoặc mối liên hệ giữa trường để cải thiện UX.
- Request DTO/Bean Validation kiểm tra cấu trúc và định dạng ở server.
- Use case/Model kiểm tra quy tắc nghiệp vụ cần dữ liệu hiện tại và bảo vệ tính nhất quán.

Ví dụ quantity phải lớn hơn 0 có thể được kiểm tra ở DTO, nhưng số lượng có còn trong kho hay không phải được kiểm tra lại trong use case khi đặt hàng. Client có thể đã mở form từ lâu hoặc có người khác vừa mua hết sản phẩm.

View nên hiển thị lỗi đã được ánh xạ thành mã hoặc thông báo an toàn. Không để template tự phân tích stack trace hoặc tự quyết định cách xử lý mọi loại exception. Controller advice hoặc adapter web có thể chuyển lỗi nghiệp vụ sang status/response phù hợp.

## 11. Phân quyền và hiển thị nút thao tác

Ẩn nút “Xóa”, “Sửa” hoặc “Hoàn tiền” chỉ là logic trình bày. Người dùng có thể gọi endpoint bằng curl, browser devtools hoặc một client khác.

Một luồng an toàn gồm:

1. Server xác thực người gửi.
2. Controller lấy danh tính từ principal/security context.
3. Use case kiểm tra quyền trên tài nguyên cụ thể.
4. Domain Model kiểm tra trạng thái có cho phép hành động hay không.
5. Server cập nhật dữ liệu và trả kết quả.
6. View dùng thông tin quyền đã được server cung cấp để hiển thị hoặc ẩn nút tương ứng.

Quyền truy cập cần được kiểm tra ở server mỗi lần thao tác, kể cả khi giao diện đã ẩn nút. Không đưa danh sách quyền hoặc cờ isAdmin do client tự khai báo vào làm căn cứ cho quyết định.

## 12. Kiểm thử khi đã tách logic

Khi logic giao diện và nghiệp vụ bị trộn, kiểm thử thường phải đi qua toàn bộ browser để xác nhận một quy tắc. Sau khi tách, có thể kiểm thử mỗi loại logic ở nơi phù hợp:

| Loại kiểm thử | Điều cần xác minh |
| --- | --- |
| Unit test domain | Giá cuối cùng, điều kiện hủy, chuyển trạng thái, giới hạn nghiệp vụ |
| Unit test use case | Dữ liệu được tải đúng, quyền và chính sách được áp dụng, thay đổi được lưu |
| Controller test | Route, principal, binding, status, redirect và ViewModel |
| Template/UI test | Nhãn, định dạng, vùng hiển thị và thông báo được render đúng |
| Integration test | Truy vấn, transaction và cập nhật trạng thái thực tế |
| End-to-end test | Người dùng hoàn thành luồng qua giao diện mà không gặp lỗi |

Ví dụ unit test cho chính sách hủy đơn:

~~~java
@Test
void deliveredOrderCannotBeCancelled() {
    Order delivered = OrderFixture.delivered();

    assertThrows(
            InvalidOrderStateException.class,
            delivered::cancel
    );
}
~~~

Ví dụ test này xác nhận quy tắc ngay trong Model. Không cần khởi chạy template engine hoặc browser để chứng minh một đơn đã giao không thể bị hủy.

Controller test có thể xác nhận canCancel được đưa vào ViewModel, còn UI test xác nhận nút chỉ hiển thị khi giá trị đó là true. Một integration test khác phải gửi request hủy trực tiếp khi điều kiện không còn đúng và xác nhận server từ chối.

## 13. Refactor mã đang trộn giao diện và nghiệp vụ

Không cần viết lại toàn bộ View hoặc Controller cùng lúc. Có thể xử lý theo từng màn hình:

1. **Liệt kê quyết định đang có:** tìm công thức, điều kiện, truy vấn và hành động trong template, JavaScript, Controller.
2. **Phân loại từng đoạn:** xác định đó là định dạng, trạng thái UI, validation cấu trúc, quy tắc nghiệp vụ hay authorization.
3. **Tìm nguồn sự thật:** xác định Model/use case nào phải sở hữu quy tắc và dữ liệu nào được phép làm đầu vào.
4. **Tạo DTO/ViewModel:** cung cấp dữ liệu đã tính và các cờ phục vụ trình bày.
5. **Chuyển quy tắc về server:** đặt bất biến trong entity/domain policy và điều phối use case.
6. **Giữ Controller làm adapter:** nhận request, lấy principal, gọi use case và ánh xạ response.
7. **Giảm logic trong View:** giữ định dạng, lặp danh sách và điều kiện hiển thị; bỏ công thức nghiệp vụ và truy vấn.
8. **Giữ JavaScript ở vai trò UX:** có thể hiển thị ước tính hoặc kiểm tra sớm nhưng không thay thế validation/authorization phía server.
9. **Viết test theo ranh giới:** unit test nghiệp vụ, controller test, template/UI test và kiểm thử endpoint trực tiếp.
10. **Xóa mã trùng:** loại bỏ công thức hoặc điều kiện cũ sau khi xác nhận luồng mới hoạt động đúng.

Trong lần refactor đầu, nên giữ nguyên route và hợp đồng response nếu có thể. Điều này giảm phạm vi thay đổi và giúp phát hiện hồi quy dễ hơn.

## 14. Ví dụ trước và sau khi tách

| Trước khi tách | Sau khi tách |
| --- | --- |
| Template tự tính tổng tiền | Use case/domain tính tiền; View nhận formattedTotal |
| JavaScript tự quyết định có được hoàn tiền | Server kiểm tra quyền và trạng thái; JS chỉ cải thiện tương tác |
| Controller truy vấn nhiều bảng rồi tự tính chính sách | Query/use case điều phối truy vấn và policy |
| View gọi getter entity kích hoạt lazy query | Query service trả ViewModel có trường cần thiết |
| Template tự phân tích exception | Adapter ánh xạ lỗi; View hiển thị thông báo an toàn |
| Nhiều nơi lặp điều kiện chuyển trạng thái | Domain Model bảo vệ một quy tắc thống nhất |

Việc tách không nhằm chuyển mọi biểu thức ra khỏi View. Mục tiêu là để mỗi quyết định có một nơi sở hữu rõ ràng và có thể kiểm thử độc lập.

## 15. Những cách tách sai thường gặp

| Cách làm | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| Chuyển mọi biểu thức khỏi template | View trở nên khó đọc và cần nhiều lớp trung gian | Giữ logic trình bày đơn giản trong View |
| Chuyển toàn bộ điều kiện vào một service lớn | Tạo God Service thay cho Fat Controller | Chia theo use case và domain responsibility |
| Để JavaScript tính giá rồi server tin kết quả | Client có thể sửa dữ liệu | Server tự tính lại từ nguồn dữ liệu đáng tin cậy |
| Dùng cờ canEdit để bảo vệ endpoint | Người dùng có thể gọi endpoint trực tiếp | Kiểm tra quyền ở server mỗi lần thao tác |
| Truyền toàn bộ entity cho View | Lộ dữ liệu và gắn View với persistence | Dùng DTO/ViewModel có trường tối thiểu |
| Đưa formatter vào domain entity | Domain bị phụ thuộc locale và cách hiển thị | Tách formatter ở presentation layer |
| Tạo ViewModel chứa quy tắc nghiệp vụ mới | Quy tắc bị giấu trong mapper | ViewModel chỉ mang dữ liệu đã được quyết định |
| Chỉ kiểm thử giao diện | Khó xác định lỗi thuộc nghiệp vụ hay trình bày | Kiểm thử domain, use case và UI ở từng tầng |

## 16. Checklist review một màn hình MVC

Khi review một màn hình hoặc endpoint, hãy tự hỏi:

- Template có tự tính giá, phí, thuế hoặc điều kiện chuyển trạng thái không?
- JavaScript có đang được xem như nơi duy nhất xác thực hoặc phân quyền không?
- Controller có trực tiếp truy vấn nhiều repository và quyết định nghiệp vụ không?
- View có truy cập entity graph hoặc persistence layer không?
- Dữ liệu đưa vào View có qua DTO/ViewModel rõ ràng không?
- Các cờ hiển thị như canCancel có được xem là gợi ý UX thay vì hàng rào bảo mật không?
- Use case có kiểm tra lại điều kiện tại thời điểm thực hiện không?
- Domain Model có bảo vệ bất biến quan trọng không?
- Format tiền/ngày có tách khỏi phép tính nghiệp vụ không?
- Có thể kiểm thử quy tắc nghiệp vụ mà không cần browser không?
- Có cùng một quy tắc bị lặp ở template, JavaScript và server không?

Nếu câu trả lời cho thấy một quyết định quan trọng nằm ở View hoặc chỉ tồn tại ở client, hãy chuyển nó về server trước khi tối ưu cách trình bày.

## 17. Quy trình thiết kế chức năng mới với ranh giới rõ

Khi xây dựng một chức năng MVC mới:

1. Viết rõ hành động nghiệp vụ và điều kiện để hành động hợp lệ.
2. Định nghĩa dữ liệu đầu vào client được phép gửi.
3. Xác thực danh tính và quyền truy cập ở server.
4. Đặt quy tắc và bất biến trong Model/domain policy.
5. Tạo use case để điều phối truy vấn, thay đổi dữ liệu và transaction.
6. Chuẩn bị DTO/ViewModel chỉ chứa dữ liệu cần cho màn hình.
7. Để Controller xử lý request, gọi use case và chọn View/response.
8. Để View định dạng và trình bày dữ liệu; JavaScript hỗ trợ tương tác.
9. Kiểm thử nghiệp vụ, giao thức HTTP và cách render riêng biệt.
10. Kiểm tra lại endpoint bằng request trực tiếp để bảo đảm client không thể bỏ qua quy tắc.

## Kết luận

Mã trộn giao diện và nghiệp vụ xuất hiện khi View hoặc JavaScript tự quyết định giá trị, quyền hay trạng thái nghiệp vụ, hoặc khi Controller phải biết quá nhiều chi tiết trình bày. Hãy để Model/domain policy bảo vệ quy tắc, use case điều phối hành động, Controller làm adapter HTTP và View chỉ định dạng, trình bày cùng phản hồi tương tác. DTO/ViewModel tạo hợp đồng dữ liệu rõ ràng; kiểm thử riêng từng tầng giúp quy tắc được áp dụng nhất quán dù chức năng được gọi từ web, API hay tác vụ nền.
