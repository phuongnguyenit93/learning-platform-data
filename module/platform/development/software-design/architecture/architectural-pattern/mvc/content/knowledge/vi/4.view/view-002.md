# Nhận dữ liệu trình bày và tạo đầu ra giao diện

Trong module **MODEL_VIEW_CONTROLLER**, View đảm nhiệm phần trình bày của ứng dụng web. View nhận dữ liệu đã được chuẩn bị, tổ chức dữ liệu thành nội dung dễ hiểu và tạo đầu ra giao diện mà người dùng có thể đọc hoặc tương tác. Đầu ra thường là HTML được gửi đến trình duyệt; với giao diện chạy phía client, đó có thể là cây component được dựng thành giao diện trên màn hình.

Để View làm tốt công việc này, dữ liệu đầu vào cần có hợp đồng rõ ràng. View cần biết tên đơn hàng, nhãn trạng thái, tổng tiền đã định dạng và danh sách dòng hàng; View không cần biết dữ liệu được truy vấn từ bảng nào hoặc quy tắc tính tổng được thực hiện ra sao. Sự phân chia này giúp phần trình bày dễ thay đổi, dễ kiểm thử và ít phụ thuộc vào nghiệp vụ.

## 1. View nhận dữ liệu gì?

View nhận những thông tin cần thiết để thể hiện một màn hình hoặc một vùng giao diện. Trong ứng dụng MVC phía máy chủ, Controller thường đưa dữ liệu vào model của request rồi chọn template tương ứng. Trong ứng dụng có frontend riêng, API trả dữ liệu theo hợp đồng và component giao diện nhận dữ liệu đó qua props hoặc state.

Ví dụ, trang chi tiết đơn hàng có thể cần:

- Mã đơn hàng và thời điểm đặt hàng.
- Nhãn trạng thái thân thiện với người dùng.
- Danh sách sản phẩm, số lượng và thành tiền từng dòng.
- Tổng tiền đã định dạng theo tiền tệ.
- Thông báo hoặc lỗi cần hiển thị.
- Những thông tin cần thiết để tạo liên kết hoặc biểu mẫu tiếp theo.

View thường nhận một **view model** (mô hình dữ liệu trình bày) hoặc một DTO dành cho response. Đối tượng này chứa dữ liệu đã được chọn và chuyển sang hình thức phù hợp với giao diện.

~~~java
public record OrderDetailViewModel(
        String orderNumber,
        String placedAtLabel,
        String statusLabel,
        List<OrderLineViewModel> lines,
        String totalLabel
) {}

public record OrderLineViewModel(
        String productName,
        String quantityLabel,
        String subtotalLabel
) {}
~~~

Các trường như **statusLabel** và **totalLabel** đã thể hiện cách trình bày. Template không phải tự suy luận ý nghĩa của mã trạng thái hoặc tự tính tiền từ các entity. Tùy dự án, việc định dạng có thể nằm trong mapper, presenter hoặc dịch vụ trình bày; điều quan trọng là View có hợp đồng đầu vào ổn định và dễ hiểu.

## 2. Phân biệt dữ liệu nghiệp vụ và dữ liệu trình bày

Model nghiệp vụ biểu diễn khái niệm và quy tắc của ứng dụng. View model biểu diễn những gì một màn hình cần hiển thị. Hai cấu trúc có thể chứa một số thông tin giống nhau, nhưng mục đích của chúng khác nhau.

| Dữ liệu nghiệp vụ | Dữ liệu trình bày |
| --- | --- |
| **OrderStatus.CONFIRMED** | **statusLabel = "Đã xác nhận"** |
| Giá trị tiền có số tiền và đơn vị tiền tệ | **totalLabel = "1.250.000 ₫"** |
| Thời điểm đặt hàng dạng **Instant** | **placedAtLabel = "19/11/2026 14:30"** theo múi giờ đã chọn |
| Mã khách hàng | Tên khách hàng được phép hiển thị |
| Danh sách **OrderLine** | Các dòng gồm tên sản phẩm, số lượng và thành tiền cần trình bày |

Không nên đưa toàn bộ entity lưu trữ vào template chỉ vì nó đang có sẵn. Entity có thể chứa khóa ngoại, cờ nội bộ, dữ liệu nhạy cảm hoặc quan hệ lười tải. View model giúp giới hạn trường dữ liệu được phép hiển thị, tránh để cấu trúc cơ sở dữ liệu quyết định cấu trúc giao diện.

Không phải mọi màn hình đều cần một lớp view model riêng. Với trang đơn giản, một DTO có thể đã đủ. Hãy tạo cấu trúc riêng khi nó làm rõ hợp đồng, loại bỏ dữ liệu thừa hoặc tách được giao diện khỏi thay đổi ở Model.

## 3. Luồng dữ liệu từ request đến giao diện

Khi người dùng mở trang chi tiết đơn hàng, luồng phổ biến trong server-side MVC diễn ra như sau:

1. Trình duyệt gửi request **GET /orders/{id}**.
2. Controller tiếp nhận request, kiểm tra tham số và gọi use case hoặc dịch vụ truy vấn phù hợp.
3. Tầng ứng dụng lấy dữ liệu nghiệp vụ và chuyển thành view model dành cho trang chi tiết.
4. Controller đưa view model vào model của request và chọn template **orders/detail**.
5. View đọc các trường đã được cung cấp, tạo HTML theo cấu trúc giao diện.
6. Framework gửi HTML về trình duyệt; trình duyệt phân tích HTML, áp dụng CSS và thực thi JavaScript cần thiết để hiển thị trang.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant C as Controller
    participant A as Dịch vụ ứng dụng
    participant M as Model / nguồn dữ liệu
    participant V as View template
    User->>Browser: Mở trang chi tiết đơn hàng
    Browser->>C: GET /orders/{id}
    C->>A: Yêu cầu dữ liệu trình bày
    A->>M: Lấy dữ liệu đơn hàng
    M-->>A: Dữ liệu nghiệp vụ
    A-->>C: OrderDetailViewModel
    C->>V: Chọn template và truyền dữ liệu
    V-->>Browser: HTML đã render
    Browser-->>User: Hiển thị trang
~~~

Đây là một cách tổ chức phổ biến. Tùy framework, việc chuyển đổi sang view model có thể nằm trong Controller, application service hoặc presenter. Dù đặt ở đâu, View nên nhận đúng dữ liệu cần để trình bày và không tự đi truy vấn các nguồn dữ liệu tùy ý.

## 4. View tạo đầu ra như thế nào?

View dùng dữ liệu đầu vào để dựng cấu trúc giao diện. Trong server-side MVC, template engine kết hợp mẫu HTML với dữ liệu request để tạo HTML hoàn chỉnh. Trong frontend component, framework kết hợp props và state để tạo cây giao diện rồi cập nhật DOM.

Ví dụ Controller trong Spring MVC:

~~~java
@Controller
@RequestMapping("/orders")
public class OrderPageController {
    private final OrderPageQuery orderPageQuery;

    public OrderPageController(OrderPageQuery orderPageQuery) {
        this.orderPageQuery = orderPageQuery;
    }

    @GetMapping("/{id}")
    public String detail(@PathVariable String id, Model model) {
        OrderDetailViewModel page = orderPageQuery.getDetail(id);
        model.addAttribute("page", page);
        return "orders/detail";
    }
}
~~~

Controller cung cấp thuộc tính **page** và chọn tên template. Template Thymeleaf sử dụng dữ liệu đó để tạo HTML:

~~~html
<main>
  <h1>Đơn hàng <span th:text="${page.orderNumber}">ORD-001</span></h1>
  <p>
    Trạng thái:
    <span th:text="${page.statusLabel}">Đang xử lý</span>
  </p>

  <ul>
    <li th:each="line : ${page.lines}">
      <span th:text="${line.productName}">Tên sản phẩm</span>
      <span th:text="${line.quantityLabel}">2</span>
      <span th:text="${line.subtotalLabel}">100.000 ₫</span>
    </li>
  </ul>

  <p>
    Tổng cộng:
    <strong th:text="${page.totalLabel}">100.000 ₫</strong>
  </p>
</main>
~~~

Các biểu thức **th:text** đưa giá trị vào nội dung văn bản và Thymeleaf thực hiện escape HTML theo mặc định. Khi dùng template engine khác, hãy hiểu rõ cơ chế escape của nó. Không nối chuỗi dữ liệu không tin cậy trực tiếp vào HTML.

## 5. View xử lý các trạng thái hiển thị

Một giao diện tốt cần thể hiện được nhiều trạng thái của cùng một chức năng. View không chỉ trình bày trường hợp có dữ liệu đầy đủ.

| Trạng thái | Điều người dùng cần thấy | Ví dụ |
| --- | --- | --- |
| Có dữ liệu | Nội dung chính và thao tác hợp lệ | Trang chi tiết đơn hàng có các dòng sản phẩm |
| Rỗng | Giải thích vì sao chưa có nội dung và gợi ý bước tiếp theo | “Bạn chưa có đơn hàng nào” cùng liên kết mua sắm |
| Đang tải | Cho biết thao tác đang được xử lý | Vòng chỉ báo hoặc thông báo đang tải trong giao diện client |
| Lỗi | Thông báo có thể hành động, không lộ chi tiết nội bộ | “Không thể tải đơn hàng. Vui lòng thử lại.” |
| Không có quyền hoặc không tồn tại | Thể hiện kết quả phù hợp với response từ server | Trang không tìm thấy hoặc thông báo không có quyền truy cập |

Với server-side rendering, Controller thường chọn response hoặc template tương ứng với kết quả xử lý. View trình bày trạng thái đã được cung cấp. Với giao diện client, component có thể nhận trạng thái tải và lỗi từ state của client rồi dựng giao diện phù hợp.

Ví dụ template có thể hiển thị danh sách rỗng:

~~~html
<section th:if="${#lists.isEmpty(page.lines)}">
  <p>Đơn hàng chưa có sản phẩm.</p>
</section>
<ul th:unless="${#lists.isEmpty(page.lines)}">
  <li th:each="line : ${page.lines}"
      th:text="${line.productName}"></li>
</ul>
~~~

Các điều kiện trong View nên tập trung vào trạng thái trình bày như rỗng, có dữ liệu hoặc hiện thông báo. Những điều kiện quyết định đơn hàng có hợp lệ, người dùng có quyền thực hiện hành động hay không vẫn phải được kiểm tra ở phía server và tầng nghiệp vụ phù hợp.

## 6. View và biểu mẫu

Biểu mẫu là nơi View trình bày dữ liệu đầu vào và giúp người dùng tạo request tiếp theo. Một form tốt cần có nhãn trường rõ ràng, chỉ dẫn định dạng, thông báo lỗi gắn với trường và giữ lại dữ liệu hợp lệ khi server trả về lỗi xác thực.

Ví dụ một phần template:

~~~html
<form th:action="@{/orders}" th:object="${orderForm}" method="post">
  <label for="customerNote">Ghi chú đơn hàng</label>
  <textarea id="customerNote" th:field="*{customerNote}"></textarea>
  <p th:if="${#fields.hasErrors('customerNote')}"
     th:errors="*{customerNote}"></p>
  <button type="submit">Tạo đơn hàng</button>
</form>
~~~

Controller nhận dữ liệu, thực hiện binding và validation ở biên request. Nếu có lỗi, Controller trả lại form cùng dữ liệu và lỗi để View trình bày. Nếu hợp lệ, Controller gọi use case xử lý và chọn response tiếp theo.

Các kiểm tra phía trình duyệt như **required**, **maxlength** hoặc định dạng input giúp người dùng sửa lỗi sớm. Chúng không thay thế validation ở server vì client có thể bị sửa hoặc bỏ qua. Với framework có hỗ trợ CSRF, form gửi dữ liệu thay đổi trạng thái cần có token theo cơ chế của framework.

## 7. An toàn khi tạo đầu ra

View thường hiển thị dữ liệu do người dùng nhập hoặc lấy từ hệ thống bên ngoài. Nếu dữ liệu đó được chèn vào HTML không an toàn, kẻ tấn công có thể tạo nội dung thực thi script trong trình duyệt của người khác (cross-site scripting, XSS).

Các nguyên tắc cần áp dụng:

- **Escape theo ngữ cảnh.** Dùng cơ chế escape mặc định của template engine cho văn bản và thuộc tính HTML. HTML, JavaScript, CSS và URL có quy tắc mã hóa khác nhau.
- **Hạn chế HTML tùy ý.** Không dùng tính năng render HTML thô cho dữ liệu không tin cậy. Nếu sản phẩm cần nội dung HTML do người dùng tạo, phải có bước lọc bằng thư viện chuyên dụng và chính sách cho phép rõ ràng.
- **Không đưa bí mật vào view model.** Không gửi mật khẩu, token phiên, khóa nội bộ hoặc dữ liệu cá nhân không cần thiết đến trình duyệt.
- **Không dựa vào việc ẩn giao diện để bảo vệ quyền.** Ẩn nút “Hủy đơn hàng” chỉ là điều chỉnh trải nghiệm. Endpoint xử lý thao tác vẫn phải xác thực và kiểm tra quyền ở server.
- **Dùng URL và tài nguyên an toàn.** Kiểm tra cách tạo liên kết, đường dẫn tải tệp và nội dung được nhúng; tránh đưa dữ liệu không tin cậy vào thuộc tính hoặc URL nguy hiểm.

View góp phần tạo đầu ra an toàn, nhưng bảo mật là trách nhiệm xuyên suốt. Controller, tầng xác thực/phân quyền và Model/use case vẫn phải bảo vệ request và trạng thái nghiệp vụ.

## 8. Khả năng truy cập và bản địa hóa

Đầu ra giao diện cần dễ sử dụng với nhiều người và phù hợp ngôn ngữ, định dạng của họ.

- Dùng phần tử HTML có ngữ nghĩa như **main**, **nav**, **header**, **button**, **label** và các tiêu đề theo thứ bậc.
- Mỗi trường biểu mẫu cần có nhãn liên kết đúng với input; lỗi nên được diễn đạt bằng văn bản và gắn với trường tương ứng.
- Các thao tác quan trọng cần sử dụng được bằng bàn phím; không truyền đạt trạng thái chỉ bằng màu sắc.
- Văn bản, định dạng ngày giờ, số và tiền tệ nên theo locale và múi giờ phù hợp. Tránh ghép chuỗi ngày hoặc tiền tệ theo một định dạng cố định trong template.
- Hình ảnh có ý nghĩa cần văn bản thay thế; nội dung trang nên có tiêu đề và cấu trúc rõ ràng.

Các quy tắc trình bày có thể được hỗ trợ bởi CSS và JavaScript, nhưng cấu trúc HTML vẫn cần có ý nghĩa ngay cả khi style hoặc script không hoạt động.

## 9. Giữ View tập trung vào trình bày

View có thể có điều kiện đơn giản để quyết định phần tử nào cần hiển thị, lặp qua danh sách hoặc định dạng dữ liệu đã chuẩn bị. Tuy nhiên, một số việc nên nằm ở thành phần khác:

| Công việc | Nơi phù hợp |
| --- | --- |
| Tính giá đơn hàng và kiểm tra điều kiện xác nhận | Model hoặc use case |
| Lấy dữ liệu cần cho trang | Dịch vụ truy vấn hoặc tầng ứng dụng |
| Kiểm tra quyền thực hiện thao tác | Tầng bảo mật và use case/server |
| Nhận request, binding, validation đầu vào và chọn response | Controller và tầng web |
| Chuyển dữ liệu nghiệp vụ thành nhãn, định dạng và cấu trúc dành cho màn hình | Mapper, presenter hoặc dịch vụ trình bày |
| Tạo HTML, bố cục, nhãn, thông báo và trạng thái giao diện | View |

Nếu template phải tự gọi cơ sở dữ liệu, thực hiện nhiều quy tắc nghiệp vụ hoặc chứa các phép tính phức tạp, View đang gánh trách nhiệm ngoài phần trình bày. Hãy chuyển phần xử lý đó ra ngoài và cung cấp dữ liệu đã được chuẩn bị.

## 10. Kiểm thử View

Kiểm thử View tập trung vào việc đầu ra có phản ánh đúng dữ liệu và trạng thái được cung cấp hay không:

- Với dữ liệu đầy đủ, trang hiển thị đúng tiêu đề, nhãn, danh sách và tổng tiền.
- Với danh sách rỗng, giao diện hiển thị nội dung rỗng phù hợp và không tạo cấu trúc lỗi.
- Với dữ liệu có ký tự đặc biệt hoặc nội dung không tin cậy, đầu ra được escape đúng.
- Với form có lỗi, thông báo xuất hiện đúng trường và dữ liệu người dùng đã nhập được giữ lại theo yêu cầu.
- Với trạng thái không có quyền hoặc không tìm thấy, giao diện hiển thị thông tin phù hợp mà không tiết lộ dữ liệu nội bộ.
- Với các locale khác nhau, ngày giờ và số tiền được trình bày theo định dạng đã chọn.

Có thể kiểm thử template bằng dữ liệu mẫu mà không cần kết nối cơ sở dữ liệu thật. Kiểm thử tích hợp bổ sung xác nhận Controller truyền đúng thuộc tính và framework render đúng template.

## 11. Quy trình thiết kế một View

Khi tạo màn hình mới, hãy đi theo trình tự:

1. Xác định mục đích của màn hình và những câu hỏi người dùng cần được trả lời.
2. Liệt kê dữ liệu tối thiểu cần hiển thị, thao tác người dùng có thể thực hiện và các trạng thái cần hỗ trợ.
3. Thiết kế view model hoặc DTO với tên trường có ý nghĩa trình bày; không đưa dữ liệu nội bộ không cần thiết vào.
4. Xác định Controller hoặc tầng ứng dụng cung cấp dữ liệu và chọn View tương ứng.
5. Dựng cấu trúc giao diện bằng template hoặc component, sử dụng phần tử có ngữ nghĩa và cơ chế escape phù hợp.
6. Bổ sung trạng thái rỗng, lỗi, tải và lỗi biểu mẫu theo luồng thực tế.
7. Kiểm thử đầu ra với dữ liệu bình thường, biên, rỗng và dữ liệu không tin cậy.

Ví dụ trang danh sách đơn hàng cần một view model có danh sách đơn, thông tin phân trang và trạng thái rỗng. View chỉ lặp qua danh sách, trình bày các trường và tạo liên kết đến trang chi tiết. Việc lọc đơn theo người dùng hiện tại, phân quyền truy cập và truy vấn dữ liệu được xử lý trước khi View nhận dữ liệu.

## Kết luận

View nhận một hợp đồng dữ liệu trình bày rõ ràng, sau đó dùng template hoặc component để tạo đầu ra giao diện. View cần thể hiện nội dung, trạng thái và thao tác một cách dễ hiểu, an toàn và có khả năng truy cập. Khi dữ liệu được chuẩn bị đúng chỗ và View tập trung vào trình bày, phần giao diện có thể thay đổi độc lập hơn với quy tắc nghiệp vụ và chi tiết lưu trữ của ứng dụng MVC.
