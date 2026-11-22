# Điều hướng giữa danh sách, chi tiết và biểu mẫu

Trong module **MODEL_VIEW_CONTROLLER**, luồng tương tác mô tả cách người dùng di chuyển qua các màn hình và gửi yêu cầu để làm việc với dữ liệu. Một luồng web phổ biến bắt đầu từ trang danh sách, mở một bản ghi ở trang chi tiết, rồi chuyển đến biểu mẫu để tạo mới, chỉnh sửa hoặc xác nhận thao tác. Controller tiếp nhận từng request, gọi nghiệp vụ phù hợp và chọn View hoặc response tiếp theo.

Điều hướng tốt giúp người dùng hiểu mình đang ở đâu, có thể làm gì tiếp theo và quay lại ngữ cảnh trước đó. Về mặt kỹ thuật, luồng này cần URL có ý nghĩa, HTTP method phù hợp, dữ liệu trình bày đúng, xử lý lỗi nhất quán và kiểm soát quyền ở server.

## 1. Ba loại màn hình thường gặp

Một chức năng quản lý dữ liệu thường có ba loại màn hình:

| Màn hình | Mục đích | Dữ liệu thường cần |
| --- | --- | --- |
| **Danh sách** | Tìm, lọc, sắp xếp và chọn một bản ghi | Các dòng dữ liệu tóm tắt, bộ lọc, phân trang, trạng thái rỗng |
| **Chi tiết** | Xem đầy đủ thông tin của một bản ghi | Mã định danh, thuộc tính, trạng thái và thao tác được phép |
| **Biểu mẫu** | Nhập dữ liệu để tạo mới hoặc cập nhật | Giá trị ban đầu, trường nhập, lựa chọn, lỗi xác thực và hướng dẫn |

Các màn hình này thường liên kết với nhau bằng URL. Ví dụ với tài nguyên đơn hàng:

| Hành động | URL ví dụ | HTTP method | Kết quả |
| --- | --- | --- | --- |
| Xem danh sách | **GET /orders** | GET | View danh sách |
| Xem trang tiếp theo hoặc lọc | **GET /orders?page=2&status=OPEN** | GET | Danh sách theo query |
| Xem chi tiết | **GET /orders/ORD-42** | GET | View chi tiết |
| Mở form tạo | **GET /orders/new** | GET | Form rỗng |
| Tạo đơn hàng | **POST /orders** | POST | Lỗi form hoặc redirect |
| Mở form sửa | **GET /orders/ORD-42/edit** | GET | Form đã điền dữ liệu |
| Cập nhật đơn hàng | **POST /orders/ORD-42** | POST | Lỗi form hoặc redirect |
| Mở trang xác nhận xóa | **GET /orders/ORD-42/delete** | GET | Trang xác nhận |
| Xóa đơn hàng | **POST /orders/ORD-42/delete** | POST | Redirect về danh sách hoặc chi tiết |

Đây là một quy ước URL có thể dùng với form HTML truyền thống. API REST có thể dùng **PUT**, **PATCH** và **DELETE** cho cập nhật hoặc xóa. HTML form tiêu chuẩn chỉ gửi trực tiếp GET hoặc POST; framework có thể hỗ trợ hidden method field để ánh xạ POST thành phương thức khác.

## 2. Luồng từ danh sách đến chi tiết

Trang danh sách giúp người dùng xác định bản ghi cần xem. Mỗi dòng thường có một liên kết đến trang chi tiết. Liên kết nên là URL có thể mở trực tiếp, sao chép, đánh dấu và chia sẻ theo chính sách quyền truy cập của ứng dụng.

Ví dụ template Thymeleaf:

~~~html
<table>
  <thead>
    <tr>
      <th>Mã đơn</th>
      <th>Trạng thái</th>
      <th>Tổng tiền</th>
      <th></th>
    </tr>
  </thead>
  <tbody>
    <tr th:each="order : ${page.items}">
      <td th:text="${order.orderNumber}">ORD-42</td>
      <td th:text="${order.statusLabel}">Đang xử lý</td>
      <td th:text="${order.totalLabel}">500.000 ₫</td>
      <td>
        <a th:href="@{/orders/{id}(id=${order.id})}">Xem chi tiết</a>
      </td>
    </tr>
  </tbody>
</table>
~~~

Khi người dùng chọn một dòng, trình duyệt gửi GET đến URL chi tiết. Controller lấy dữ liệu theo mã định danh, kiểm tra người dùng có quyền xem tài nguyên đó hay không, rồi cung cấp view model cho View.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant C as OrderController
    participant Q as OrderQuery
    participant V as View
    User->>Browser: Mở danh sách đơn hàng
    Browser->>C: GET /orders
    C->>Q: Tìm đơn hàng theo bộ lọc
    Q-->>C: Trang dữ liệu danh sách
    C->>V: Model danh sách
    V-->>Browser: HTML danh sách và liên kết chi tiết
    User->>Browser: Chọn ORD-42
    Browser->>C: GET /orders/ORD-42
    C->>Q: Lấy chi tiết và kiểm tra quyền
    Q-->>C: Dữ liệu chi tiết
    C->>V: Model chi tiết
    V-->>Browser: HTML trang chi tiết
~~~

Trang chi tiết thường cung cấp các hành động như quay lại danh sách, chỉnh sửa hoặc xóa. Những hành động này nên được hiển thị dựa trên quyền và trạng thái nghiệp vụ đã được xác định. Dù giao diện ẩn một nút, endpoint tương ứng vẫn phải kiểm tra quyền khi nhận request.

## 3. Giữ ngữ cảnh khi quay lại danh sách

Người dùng thường mở một bản ghi từ danh sách đã lọc hoặc đang ở trang thứ ba. Khi quay lại, họ có thể muốn giữ nguyên từ khóa tìm kiếm, bộ lọc, thứ tự sắp xếp và số trang.

Một cách đơn giản là biểu diễn ngữ cảnh danh sách bằng query parameters:

~~~text
/orders?page=3&size=20&sort=createdAt,desc&status=OPEN&keyword=keyboard
~~~

Khi tạo liên kết đến trang chi tiết, có thể giữ lại một phần ngữ cảnh:

~~~html
<a th:href="@{/orders/{id}(
      id=${order.id},
      page=${criteria.page},
      size=${criteria.size},
      sort=${criteria.sort},
      status=${criteria.status},
      keyword=${criteria.keyword}
  )}">Xem chi tiết</a>
~~~

Trang chi tiết có thể tạo liên kết quay lại danh sách với các tham số đã nhận:

~~~html
<a th:href="@{/orders(
      page=${returnContext.page},
      size=${returnContext.size},
      sort=${returnContext.sort},
      status=${returnContext.status},
      keyword=${returnContext.keyword}
  )}">Quay lại danh sách</a>
~~~

Không phải lúc nào cũng cần giữ toàn bộ query. Chỉ giữ những tham số có ý nghĩa với ngữ cảnh người dùng; chuẩn hóa giá trị, giới hạn kích thước và kiểm tra các trường sort/filter hợp lệ. Nếu cần lưu ngữ cảnh phức tạp hơn, có thể dùng session hoặc một mã tham chiếu ngắn, nhưng phải cân nhắc thời hạn sống, nhiều tab và khả năng chia sẻ URL.

Không nên tin một URL quay lại tùy ý do client gửi lên. Nếu hỗ trợ tham số return URL, hãy giới hạn đích đến trong các đường dẫn nội bộ đã cho phép để tránh lỗ hổng open redirect.

## 4. Phân trang, lọc và sắp xếp là một phần của điều hướng

Danh sách có thể có hàng nghìn bản ghi. Phân trang và bộ lọc giúp người dùng tìm dữ liệu mà không phải tải tất cả cùng lúc.

- **Page và size:** xác định vị trí và số dòng trên một trang. Server cần giới hạn size tối đa.
- **Keyword:** từ khóa tìm kiếm. Cần quy định rõ trường nào được tìm và cách xử lý chuỗi rỗng.
- **Filter:** trạng thái, ngày tạo hoặc nhóm dữ liệu. Giá trị không hợp lệ cần được xử lý theo quy ước rõ ràng.
- **Sort:** chỉ cho phép sắp xếp theo các trường được hỗ trợ; không ghép trực tiếp tên cột tùy ý từ request vào câu SQL.

Ví dụ một Controller:

~~~java
@GetMapping
public String list(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size,
        @RequestParam(required = false) String status,
        @RequestParam(required = false) String keyword,
        Model model) {

    int safePage = Math.max(page, 0);
    int safeSize = Math.min(Math.max(size, 1), 100);
    OrderSearchCriteria criteria =
            new OrderSearchCriteria(safePage, safeSize, status, keyword);

    model.addAttribute("page", orderQuery.search(criteria));
    model.addAttribute("criteria", criteria);
    return "orders/list";
}
~~~

Trong ứng dụng thực tế, cần xác thực giá trị status và sort theo danh sách cho phép, xử lý từ khóa theo quy tắc tìm kiếm và giữ bộ lọc khi người dùng chuyển trang. Tránh để tham số tùy ý làm thay đổi truy vấn hoặc truy cập dữ liệu ngoài phạm vi người dùng.

## 5. Từ chi tiết đến biểu mẫu tạo mới

Từ trang danh sách hoặc thanh điều hướng, người dùng có thể chọn **Tạo đơn hàng**. Request GET mở form rỗng và có thể tải các dữ liệu hỗ trợ như danh sách sản phẩm, phương thức giao hàng hoặc địa chỉ đã lưu.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant B as Trình duyệt
    participant C as Controller
    participant A as Use case / dịch vụ
    participant V as View form
    User->>B: Chọn Tạo đơn hàng
    B->>C: GET /orders/new
    C->>A: Lấy dữ liệu hỗ trợ form
    A-->>C: Danh mục và lựa chọn
    C->>V: Form rỗng và dữ liệu hỗ trợ
    V-->>B: HTML form
    User->>B: Nhập dữ liệu và gửi
    B->>C: POST /orders
    C->>A: Tạo đơn hàng
    A-->>C: Kết quả xử lý
    C-->>B: Redirect hoặc render lại form
~~~

Ví dụ Controller mở form:

~~~java
@GetMapping("/new")
public String newForm(Model model) {
    model.addAttribute("form", new OrderForm());
    model.addAttribute("products", productQuery.listAvailable());
    return "orders/new";
}
~~~

View dùng dữ liệu form để dựng các trường nhập. Dữ liệu hỗ trợ như danh sách sản phẩm cũng cần được cung cấp lại khi render form có lỗi; nếu thiếu, người dùng có thể mất các lựa chọn cần thiết để sửa dữ liệu.

## 6. Gửi biểu mẫu và xử lý validation

Khi người dùng gửi form, Controller nhận request, binding dữ liệu và kiểm tra định dạng ở ranh giới web. Những điều kiện nghiệp vụ như sản phẩm còn bán hay đơn hàng có thể được tạo ở trạng thái hiện tại cần được kiểm tra trong use case hoặc Model.

Ví dụ:

~~~java
@PostMapping
public String create(
        @Valid @ModelAttribute("form") OrderForm form,
        BindingResult errors,
        Model model,
        RedirectAttributes redirectAttributes) {

    if (errors.hasErrors()) {
        model.addAttribute("products", productQuery.listAvailable());
        return "orders/new";
    }

    OrderId id = placeOrder.execute(form.toCommand());
    redirectAttributes.addFlashAttribute(
            "notice", "Đơn hàng đã được tạo.");
    return "redirect:/orders/" + id.value();
}
~~~

Nếu validation thất bại, Controller render lại form cùng lỗi và dữ liệu đã nhập. Nếu xử lý thành công, Controller redirect đến trang chi tiết. Mẫu **Post/Redirect/Get (PRG)** giúp thao tác refresh trang kết quả không tự gửi lại POST trước đó.

Không nên chỉ dựa vào validation phía trình duyệt. Request có thể được gửi trực tiếp hoặc bị chỉnh sửa, vì vậy server phải kiểm tra lại dữ liệu và quyền thực hiện. Form thay đổi trạng thái cần được bảo vệ CSRF theo cơ chế của framework.

## 7. Từ chi tiết đến biểu mẫu chỉnh sửa

Form chỉnh sửa cần được điền bằng dữ liệu hiện tại của bản ghi. Khi người dùng mở **Chỉnh sửa**, Controller tải bản ghi, kiểm tra quyền và trạng thái có cho phép sửa hay không, sau đó chuyển dữ liệu phù hợp sang form object.

~~~java
@GetMapping("/{id}/edit")
public String editForm(@PathVariable String id, Model model) {
    OrderEditData data = orderQuery.getEditableData(id);
    model.addAttribute("form", OrderForm.from(data));
    model.addAttribute("products", productQuery.listAvailable());
    return "orders/edit";
}
~~~

Khi gửi form, Controller gọi use case cập nhật:

~~~java
@PostMapping("/{id}")
public String update(
        @PathVariable String id,
        @Valid @ModelAttribute("form") OrderForm form,
        BindingResult errors,
        Model model,
        RedirectAttributes redirectAttributes) {

    if (errors.hasErrors()) {
        model.addAttribute("products", productQuery.listAvailable());
        return "orders/edit";
    }

    updateOrder.execute(id, form.toCommand());
    redirectAttributes.addFlashAttribute(
            "notice", "Đơn hàng đã được cập nhật.");
    return "redirect:/orders/" + id;
}
~~~

Nếu bản ghi đã bị người khác thay đổi hoặc trạng thái không còn cho phép sửa, use case cần phát hiện xung đột và Controller chuyển kết quả thành thông báo hoặc response phù hợp. Có thể dùng optimistic locking/version để tránh ghi đè thay đổi mới hơn.

## 8. Xóa và xác nhận thao tác

Xóa thường là thao tác khó hoàn tác. Một luồng rõ ràng có thể gồm:

1. Người dùng chọn Xóa ở trang chi tiết.
2. GET mở trang xác nhận, hiển thị đúng bản ghi sẽ bị xóa.
3. Người dùng xác nhận bằng một form POST.
4. Controller gọi use case xóa, kiểm tra quyền và quy tắc nghiệp vụ.
5. Nếu thành công, Controller redirect về danh sách hoặc trang đích hợp lý.

Không dùng GET để thực hiện xóa hoặc thao tác làm thay đổi trạng thái. GET có thể bị trình duyệt, crawler hoặc hệ thống trung gian truy cập tự động. Việc thay đổi trạng thái cần dùng method phù hợp và có bảo vệ CSRF.

Ví dụ form xác nhận:

~~~html
<h1>Xác nhận xóa đơn hàng</h1>
<p>Bạn có chắc muốn xóa đơn <span th:text="${page.orderNumber}">ORD-42</span>?</p>
<form th:action="@{/orders/{id}/delete(id=${page.id})}" method="post">
  <button type="submit">Xác nhận xóa</button>
  <a th:href="@{/orders/{id}(id=${page.id})}">Hủy</a>
</form>
~~~

Với Spring Security, token CSRF thường được thêm tự động khi dùng tích hợp Thymeleaf/Spring Security phù hợp; nếu tự xây dựng form hoặc dùng cơ chế khác, phải bảo đảm token được gửi theo yêu cầu cấu hình. Ẩn nút xóa trong View không thay thế kiểm tra quyền trong use case hoặc endpoint.

## 9. Tổng quan luồng điều hướng

Sơ đồ dưới đây mô tả các màn hình và những thao tác chính của một chức năng quản lý đơn hàng:

~~~mermaid
flowchart TD
    L["Danh sách đơn hàng"] -->|Chọn một dòng| D["Chi tiết đơn hàng"]
    L -->|Tạo mới| N["Form tạo đơn hàng"]
    D -->|Chỉnh sửa| E["Form chỉnh sửa"]
    D -->|Xóa| X["Xác nhận xóa"]
    N -->|POST hợp lệ| S["Tạo thành công"]
    N -->|Validation lỗi| N
    E -->|POST hợp lệ| U["Cập nhật thành công"]
    E -->|Validation lỗi| E
    X -->|POST xác nhận| R["Xóa thành công"]
    S --> D
    U --> D
    R --> L
    D -->|Quay lại, giữ bộ lọc| L
~~~

Các mũi tên biểu diễn hành động điều hướng và kết quả thường gặp. Trong ứng dụng thật, mỗi request vẫn cần kiểm tra dữ liệu, quyền truy cập và trạng thái tài nguyên. Người dùng cũng có thể truy cập trực tiếp một URL mà không đi qua trang danh sách trước đó.

## 10. URL, trạng thái và lịch sử trình duyệt

URL nên mô tả tài nguyên hoặc màn hình hiện tại đủ rõ để người dùng có thể tải lại trang, mở trong tab mới hoặc chia sẻ khi được phép.

- Dùng path variable cho định danh tài nguyên, ví dụ **/orders/ORD-42**.
- Dùng query parameter cho trạng thái có thể chia sẻ như bộ lọc, phân trang và sắp xếp.
- Không đưa mật khẩu, token bí mật hoặc dữ liệu cá nhân nhạy cảm vào URL.
- Khi redirect sau POST, chuyển đến URL GET có thể tải lại an toàn.
- Nút quay lại của trình duyệt là một phần của lịch sử điều hướng; trang cần xử lý hợp lý khi được tải lại hoặc truy cập trực tiếp.

Không nên giả định người dùng luôn đi theo đúng chuỗi màn hình. Một người có thể lưu URL chi tiết và mở trực tiếp vào ngày khác, hoặc mở hai bản ghi ở hai tab. Vì vậy, mỗi request cần tự tải dữ liệu cần thiết và kiểm tra quyền độc lập, thay vì dựa vào trạng thái chỉ được thiết lập ở request trước.

## 11. Bảo mật trong luồng điều hướng

Điều hướng giữa danh sách, chi tiết và form tạo ra nhiều điểm cần kiểm soát:

- **Xác thực và phân quyền theo tài nguyên:** khi nhận mã đơn, server phải xác minh người dùng được phép xem, sửa hoặc xóa đúng đơn đó. Biết một ID không có nghĩa là có quyền truy cập.
- **Chống IDOR:** không chỉ kiểm tra người dùng đã đăng nhập; cần kiểm tra quan hệ sở hữu hoặc quyền truy cập đối với từng bản ghi. Có thể trả 404 thay vì 403 trong một số chính sách nhằm tránh tiết lộ sự tồn tại của tài nguyên.
- **CSRF:** các request thay đổi trạng thái cần token hoặc cơ chế bảo vệ tương đương.
- **Không thực hiện thay đổi bằng GET:** link xem chi tiết có thể dùng GET; form xóa hoặc cập nhật phải gửi request thay đổi trạng thái.
- **Kiểm tra redirect:** nếu có tham số return URL, chỉ cho phép đích đến đã được xác minh.
- **Kiểm tra dữ liệu form ở server:** không tin giá, trạng thái, quyền hoặc ID tham chiếu chỉ vì chúng đến từ một trường ẩn trong HTML.

Những kiểm tra này phải nằm ở server và tầng nghiệp vụ phù hợp. View chỉ hỗ trợ trải nghiệm bằng cách trình bày đúng những hành động mà người dùng có thể thực hiện.

## 12. Kiểm thử luồng điều hướng

Kiểm thử từng trang riêng lẻ là chưa đủ. Cần kiểm tra các chuyển tiếp giữa trang và phản hồi của từng thao tác:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Mở danh sách và chọn một bản ghi | Link đúng ID, trang chi tiết tải đúng dữ liệu |
| Lọc rồi mở chi tiết và quay lại | Bộ lọc, sắp xếp và phân trang được giữ theo thiết kế |
| Mở form tạo và gửi dữ liệu hợp lệ | Tạo đúng tài nguyên rồi redirect đến URL hợp lý |
| Gửi form không hợp lệ | Render lại form, hiển thị lỗi và giữ dữ liệu |
| Mở form sửa | Form chứa giá trị hiện tại và dữ liệu hỗ trợ |
| Cập nhật khi dữ liệu đã thay đổi | Xử lý xung đột, tránh ghi đè âm thầm |
| Xóa một bản ghi | GET chỉ mở xác nhận; POST mới thực hiện xóa |
| Truy cập ID của người khác | Server từ chối theo chính sách, không lộ dữ liệu |
| Mở URL chi tiết trực tiếp | Request tự tải dữ liệu và kiểm tra quyền |
| Refresh sau khi gửi form thành công | Không gửi lại thao tác POST theo luồng PRG |

Có thể kiểm thử Controller bằng MockMvc hoặc công cụ tương đương để xác minh URL, status, tên View, model attributes và redirect. Kiểm thử tích hợp nên đi qua framework render template và xác nhận dữ liệu xuất hiện đúng trong HTML.

## 13. Quy trình thiết kế luồng cho một chức năng

Khi thiết kế chức năng quản lý dữ liệu mới, hãy làm rõ các điểm sau:

1. Xác định các màn hình cần có: danh sách, chi tiết, tạo mới, chỉnh sửa, xác nhận hoặc kết quả.
2. Đặt URL và HTTP method cho từng hành động; dùng GET cho đọc và method thay đổi trạng thái cho thao tác ghi.
3. Xác định dữ liệu đầu vào, view model và dữ liệu hỗ trợ cần thiết cho mỗi View.
4. Xác định cách giữ ngữ cảnh như bộ lọc, phân trang và sắp xếp khi di chuyển giữa các trang.
5. Quy định kết quả thành công, lỗi validation, không tìm thấy, xung đột và từ chối quyền.
6. Chọn render, redirect hoặc response body phù hợp với loại client.
7. Kiểm tra quyền theo từng tài nguyên và bảo vệ request thay đổi trạng thái.
8. Viết kiểm thử cho cả đường đi bình thường và các nhánh lỗi, bao gồm truy cập URL trực tiếp.

Ví dụ với chức năng quản lý sản phẩm, trang danh sách cung cấp bộ lọc theo danh mục; trang chi tiết hiển thị thông tin và nút chỉnh sửa; form chỉnh sửa được điền bằng dữ liệu hiện tại; khi lưu thành công, Controller redirect về chi tiết. Nếu sản phẩm đã ngừng kinh doanh và không thể sửa một trường nhất định, use case trả kết quả phù hợp và Controller đưa người dùng đến thông báo hoặc form có hướng dẫn.

## Kết luận

Điều hướng giữa danh sách, chi tiết và biểu mẫu là một chuỗi request có mục đích rõ ràng. Danh sách giúp tìm tài nguyên, chi tiết trình bày một tài nguyên, biểu mẫu thu nhận dữ liệu để tạo hoặc thay đổi tài nguyên. Controller điều phối các bước, chọn View hoặc redirect, giữ ngữ cảnh cần thiết và ánh xạ lỗi; server kiểm tra quyền và quy tắc ở từng request. Khi URL, dữ liệu và phản hồi nhất quán, người dùng có thể di chuyển trong ứng dụng MVC một cách dễ dự đoán và an toàn.
