# Giới hạn logic điều kiện và vòng lặp trong View

## Mục tiêu

View có nhiệm vụ trình bày dữ liệu và phản hồi trạng thái của ứng dụng cho người dùng. Để làm việc đó, template hoặc thành phần giao diện thường cần điều kiện và vòng lặp: chỉ hiển thị một vùng khi dữ liệu có mặt, đổi nhãn theo trạng thái, hoặc tạo một dòng giao diện cho mỗi phần tử trong danh sách.

Những cấu trúc này là cần thiết, nhưng View sẽ khó bảo trì nếu phải tự quyết định quy tắc nghiệp vụ, truy vấn dữ liệu, tính toán phức tạp hoặc điều phối quy trình. Bài học này giúp xác định logic nào phù hợp với View, logic nào cần được chuẩn bị ở Controller hoặc lớp ứng dụng, và logic nào phải thuộc Model/domain.

Sau khi học, người học có thể:

- Phân biệt logic trình bày với logic nghiệp vụ và logic điều phối.
- Viết điều kiện và vòng lặp đơn giản, dễ đọc trong template.
- Chuẩn bị dữ liệu hiển thị qua một hợp đồng rõ ràng.
- Xử lý trạng thái rỗng, thiếu dữ liệu, lỗi và quyền hiển thị một cách an toàn.
- Nhận diện template đang chứa quá nhiều logic và biết cách refactor.
- Kiểm thử nội dung được render mà không biến template thành nơi thực thi nghiệp vụ.

## 1. Vai trò của View trong MVC

Trong MVC, View chịu trách nhiệm tạo ra phần biểu diễn mà người dùng nhìn thấy. Với ứng dụng web kết xuất phía máy chủ, View thường là template HTML được kết hợp với dữ liệu do Controller cung cấp. Với ứng dụng đơn trang, View là các component giao diện được render từ trạng thái phía frontend.

Một View thường cần thực hiện những việc sau:

- Hiển thị tiêu đề, mô tả, ngày tháng, số tiền và trạng thái.
- Lặp qua danh sách để tạo bảng, thẻ hoặc mục điều hướng.
- Ẩn hoặc hiện một phần giao diện theo trạng thái trình bày.
- Hiển thị thông báo khi danh sách rỗng hoặc khi có lỗi nhập liệu.
- Chọn cách định dạng dữ liệu và gắn lớp CSS phù hợp.

Ví dụ, trang chi tiết đơn hàng có thể hiển thị mã đơn, ngày tạo, danh sách mặt hàng, tổng tiền và trạng thái. View có thể lặp qua danh sách mặt hàng để tạo các dòng HTML. View cũng có thể hiển thị nhãn “Đã thanh toán” khi trạng thái được truyền vào là PAID.

View không nên tự quyết định những vấn đề như:

- Người dùng có đủ điều kiện mua sản phẩm hay không.
- Đơn hàng có thể chuyển từ DRAFT sang CONFIRMED hay không.
- Mức giảm giá được áp dụng theo chính sách nào.
- Tồn kho còn đủ để đáp ứng đơn hàng hay không.
- Phí vận chuyển phải tính theo quy tắc nghiệp vụ nào.
- Dữ liệu cần lấy từ bảng hoặc dịch vụ nào.

Những quyết định đó thuộc Model/domain hoặc lớp ứng dụng. Controller tiếp nhận request và điều phối việc lấy dữ liệu, sau đó đưa kết quả phù hợp cho View.

## 2. Phân biệt ba loại logic

Không phải mọi biểu thức điều kiện trong template đều xấu. Điều quan trọng là mục đích của điều kiện và nơi sở hữu quy tắc.

| Loại logic | Ví dụ | Nơi phù hợp |
|---|---|---|
| Logic trình bày | Có hiển thị ảnh đại diện không? Danh sách có phần tử để render không? Nhãn trạng thái có màu nào? | View |
| Logic nghiệp vụ | Đơn hàng có đủ điều kiện hủy không? Khách hàng được giảm giá bao nhiêu? | Model/domain hoặc domain service |
| Logic điều phối | Tải đơn hàng, gọi ca sử dụng, lấy dữ liệu từ repository, phối hợp transaction | Controller/application service |

### Logic trình bày

Logic trình bày quyết định cách thể hiện dữ liệu đã được chuẩn bị. Ví dụ:

- Nếu người dùng chưa có ảnh đại diện, hiển thị ảnh mặc định.
- Nếu danh sách kết quả rỗng, hiển thị thông báo “Chưa có kết quả”.
- Nếu trạng thái là PAID, hiển thị nhãn “Đã thanh toán”.
- Nếu một trường ghi chú không có nội dung, bỏ qua vùng ghi chú.
- Với mỗi dòng hàng, hiển thị tên, số lượng và thành tiền.

Những điều kiện này không làm thay đổi ý nghĩa nghiệp vụ của dữ liệu. Chúng chỉ chọn cách biểu diễn phù hợp.

### Logic nghiệp vụ

Logic nghiệp vụ quyết định điều gì được phép xảy ra và kết quả nào là hợp lệ. Ví dụ, điều kiện hủy đơn hàng có thể phụ thuộc vào trạng thái thanh toán, thời điểm giao hàng, chính sách hoàn tiền và quyền của người mua.

Không nên viết quy tắc đó thành một biểu thức dài trong template:

    <button th:if="${order.status == 'DRAFT'
        or (order.status == 'CONFIRMED' and order.paymentStatus == 'UNPAID'
        and order.shipmentStatus == 'NOT_SHIPPED')}">
        Hủy đơn hàng
    </button>

Biểu thức này khiến View phải biết chi tiết chính sách hủy. Khi chính sách thay đổi, template và các nơi thực hiện cùng quy tắc có thể lệch nhau.

Một cách rõ ràng hơn là để lớp ứng dụng hoặc chính sách nghiệp vụ đánh giá khả năng hủy và đưa ra dữ liệu hiển thị:

    public record OrderDetailsView(
            UUID id,
            String orderNumber,
            String statusLabel,
            boolean cancelActionVisible,
            List<OrderLineView> lines) {
    }

    public record OrderLineView(
            String productName,
            int quantity,
            String subtotalText) {
    }

Controller hoặc query service chuẩn bị đối tượng này sau khi áp dụng các quy tắc cần thiết. View chỉ đọc cancelActionVisible để quyết định có render nút hay không.

Việc ẩn nút không thay thế kiểm tra quyền và điều kiện ở endpoint. Khi người dùng gửi request trực tiếp, application service/domain vẫn phải kiểm tra thao tác có hợp lệ hay không.

### Logic điều phối

View không nên gọi repository, service nghiệp vụ hoặc API bên ngoài để tự lấy dữ liệu. Những lời gọi đó khiến việc render phụ thuộc vào hạ tầng và làm phát sinh truy vấn khó nhận biết.

Controller hoặc application service thực hiện việc điều phối, sau đó truyền dữ liệu đã sẵn sàng cho View. Nhờ đó, template có thể được đọc như một bản mô tả cách trình bày.

## 3. Dùng điều kiện cho những lựa chọn hiển thị đơn giản

Điều kiện trong View phù hợp khi biểu thức dễ hiểu, dựa trên dữ liệu đã có và chỉ ảnh hưởng đến phần trình bày.

### Hiển thị trường tùy chọn

Một trang hồ sơ có thể chỉ hiển thị phần giới thiệu khi người dùng đã nhập nội dung:

    <section th:if="${profile.bio != null and !#strings.isEmpty(profile.bio)}">
        <h2>Giới thiệu</h2>
        <p th:text="${profile.bio}">Nội dung giới thiệu</p>
    </section>

Đây là quyết định trình bày: trường rỗng thì không cần tạo phần giới thiệu. Nếu ứng dụng có quy tắc chuẩn hóa hoặc xác thực nội dung giới thiệu, các quy tắc đó phải được xử lý trước khi dữ liệu đến View.

### Hiển thị nhãn theo trạng thái đã được xác định

    <span th:if="${order.status == 'PAID'}"
          class="badge badge-success">
        Đã thanh toán
    </span>
    <span th:if="${order.status == 'PENDING'}"
          class="badge badge-warning">
        Đang chờ thanh toán
    </span>
    <span th:if="${order.status == 'CANCELLED'}"
          class="badge badge-secondary">
        Đã hủy
    </span>

View đang ánh xạ một giá trị trạng thái đã có sang cách trình bày. Nếu có nhiều trạng thái hoặc nhiều giao diện cần cùng nhãn, màu và thứ tự ưu tiên, hãy cân nhắc chuẩn bị statusLabel và statusCssClass trong view model để tránh lặp lại ánh xạ ở nhiều template.

### Hiển thị hành động theo cờ trình bày

    <div class="order-actions">
        <form th:if="${page.cancelActionVisible}"
              th:action="@{/orders/{id}/cancel(id=${page.id})}"
              method="post">
            <button type="submit">Hủy đơn hàng</button>
        </form>
    </div>

Cờ này cho biết giao diện nên trình bày hành động. Endpoint vẫn phải xác thực người dùng, kiểm tra quyền truy cập đối tượng và áp dụng quy tắc hủy khi nhận request.

### Tránh điều kiện lồng nhau quá sâu

Một template có nhiều tầng if/else làm người đọc khó hiểu phần nào được render trong từng trường hợp. Nếu điều kiện bắt đầu mô tả nhiều trạng thái nghiệp vụ, hãy chuyển phần quyết định sang lớp ứng dụng và đưa vào View một trạng thái hiển thị đơn giản.

Có thể dùng một giá trị phân loại như pageState với các giá trị rõ ràng: READY, EMPTY hoặc ERROR. View chỉ cần chọn vùng giao diện tương ứng.

## 4. Dùng vòng lặp để lặp dữ liệu hiển thị

Vòng lặp là cấu trúc tự nhiên của View khi một danh sách cần được biểu diễn thành nhiều phần tử giao diện.

Ví dụ, template Thymeleaf hiển thị các dòng hàng:

    <table>
        <thead>
            <tr>
                <th>Sản phẩm</th>
                <th>Số lượng</th>
                <th>Thành tiền</th>
            </tr>
        </thead>
        <tbody>
            <tr th:each="line : ${page.lines}">
                <td th:text="${line.productName}">Tên sản phẩm</td>
                <td th:text="${line.quantity}">1</td>
                <td th:text="${line.subtotalText}">100.000 đ</td>
            </tr>
        </tbody>
    </table>

Template không cần biết mỗi dòng hàng được truy vấn từ bảng nào hoặc tổng tiền được tính theo chính sách nào. Nó chỉ nhận một danh sách đã được chuẩn bị và render từng phần tử.

### Giữ vòng lặp đơn giản

Trong vòng lặp, nên ưu tiên các thao tác trực tiếp:

- Đọc thuộc tính đã có.
- Định dạng hoặc hiển thị một giá trị.
- Gắn class theo một trạng thái đơn giản.
- Tạo liên kết từ ID hoặc route đã xác định.
- Hiển thị nội dung tùy chọn.

Tránh đặt trong mỗi vòng lặp các thao tác như:

- Gọi repository hoặc service để lấy thêm dữ liệu.
- Tính lại tổng tiền hoặc áp dụng chính sách giảm giá.
- Kiểm tra nhiều điều kiện nghiệp vụ phức tạp.
- Thay đổi trạng thái đối tượng.
- Gửi request hoặc thực hiện tác dụng phụ.

Ví dụ sau là dấu hiệu thiết kế không tốt:

    <tr th:each="line : ${order.lines}">
        <td th:text="${productService.findById(line.productId).name}"></td>
        <td th:text="${pricingService.calculate(line)}"></td>
    </tr>

Template đang thực hiện truy cập dữ liệu và gọi nghiệp vụ cho từng phần tử. Điều này có thể tạo ra vấn đề N+1 query: một truy vấn lấy danh sách, sau đó thêm một truy vấn cho mỗi dòng. Việc render cũng trở nên khó dự đoán vì phụ thuộc vào service và trạng thái bên ngoài.

Hãy chuẩn bị danh sách dữ liệu hiển thị trước khi render:

    public record OrderLineView(
            String productName,
            int quantity,
            String subtotalText) {
    }

    public record OrderDetailsView(
            String orderNumber,
            List<OrderLineView> lines) {
    }

Query service có thể tải dữ liệu cần thiết theo cách hiệu quả, áp dụng phép tính nghiệp vụ và chuyển thành OrderDetailsView. Template chỉ lặp qua page.lines.

### Không lạm dụng vòng lặp lồng nhau

Vòng lặp lồng nhau có thể phù hợp với cấu trúc phân cấp, ví dụ danh mục và danh sách sản phẩm trong từng danh mục. Nhưng nếu template phải tìm kiếm phần tử liên quan trong một danh sách khác, nhóm dữ liệu hoặc tính tổng cho từng nhóm, đó thường là dấu hiệu dữ liệu chưa được chuẩn bị đúng.

Thay vì để template ghép hai danh sách bằng nhiều vòng lặp, hãy tạo cấu trúc dữ liệu đã nhóm theo đúng hình thức cần hiển thị:

    public record CategoryView(
            String name,
            List<ProductCardView> products) {
    }

View chỉ cần lặp qua categories, sau đó lặp qua products của từng category. Việc nhóm dữ liệu nên được thực hiện ở query/application layer hoặc một bước chuẩn bị presentation model.

### Sắp xếp dữ liệu

Sắp xếp đơn giản chỉ nhằm trình bày, chẳng hạn tên tăng dần trong một bảng nhỏ, có thể được thực hiện trước khi render hoặc bằng tính năng sắp xếp của giao diện. Tuy nhiên, nếu thứ tự phản ánh ưu tiên nghiệp vụ, xếp hạng, thời hạn xử lý hoặc chính sách phân bổ, hãy để domain/application layer xác định thứ tự đó.

Với danh sách lớn, phân trang và sắp xếp nên được thực hiện ở tầng truy vấn để tránh tải toàn bộ dữ liệu vào bộ nhớ chỉ để render.

## 5. Chuẩn bị dữ liệu hiển thị qua hợp đồng rõ ràng

Một View dễ bảo trì khi nó nhận dữ liệu có cấu trúc phù hợp với màn hình. Hợp đồng này thường được gọi là view model hoặc presentation model.

Ví dụ, trang chi tiết đơn hàng cần:

- Mã đơn và ngày tạo đã định dạng.
- Nhãn trạng thái để hiển thị.
- Các dòng hàng với tên, số lượng và thành tiền.
- Tổng tiền đã định dạng theo đơn vị tiền tệ.
- Các cờ cho biết hành động nào nên xuất hiện.
- Thông báo hoặc trạng thái trang nếu dữ liệu chưa sẵn sàng.

Một đối tượng trình bày có thể như sau:

    public record OrderDetailsPage(
            UUID id,
            String orderNumber,
            String createdAtText,
            String statusLabel,
            String statusCssClass,
            List<OrderLineView> lines,
            String totalText,
            boolean cancelActionVisible) {
    }

Controller phối hợp với query/application service:

    @GetMapping("/{id}")
    public String detail(@PathVariable UUID id, Model model) {
        OrderDetailsPage page = orderQueryService.getDetailsPage(id);
        model.addAttribute("page", page);
        return "orders/detail";
    }

Template đọc hợp đồng đó:

    <h1 th:text="'Đơn hàng ' + ${page.orderNumber}">Đơn hàng</h1>

    <span th:text="${page.statusLabel}"
          th:classappend="${page.statusCssClass}">
        Trạng thái
    </span>

    <p th:text="${page.createdAtText}">Ngày tạo</p>

    <table>
        <tbody>
            <tr th:each="line : ${page.lines}">
                <td th:text="${line.productName}">Sản phẩm</td>
                <td th:text="${line.quantity}">1</td>
                <td th:text="${line.subtotalText}">100.000 đ</td>
            </tr>
        </tbody>
    </table>

    <strong th:text="${page.totalText}">Tổng tiền</strong>

Cấu trúc này làm cho nhu cầu của màn hình được thể hiện rõ. Khi đổi cách lưu trữ hoặc cách truy vấn, template không cần biết chi tiết thay đổi nếu hợp đồng trình bày vẫn giữ nguyên.

Không nhất thiết tạo một DTO riêng cho mọi màn hình nhỏ. Với trang đơn giản, Controller có thể truyền một vài thuộc tính riêng lẻ. Hãy tạo view model khi màn hình có nhiều dữ liệu liên quan, nhiều trạng thái trình bày hoặc cần tách khỏi entity lưu trữ.

## 6. Xử lý trạng thái rỗng, tải dữ liệu và lỗi

Một View tốt cần trình bày được các trạng thái mà người dùng có thể gặp, không chỉ trường hợp có dữ liệu đầy đủ.

### Danh sách rỗng

Vòng lặp trên danh sách rỗng thường không tạo phần tử nào. Nếu không có vùng thay thế, người dùng có thể tưởng rằng trang bị lỗi.

    <table th:if="${!#lists.isEmpty(page.lines)}">
        <tbody>
            <tr th:each="line : ${page.lines}">
                <td th:text="${line.productName}">Sản phẩm</td>
                <td th:text="${line.quantity}">1</td>
            </tr>
        </tbody>
    </table>

    <p th:if="${#lists.isEmpty(page.lines)}">
        Đơn hàng chưa có mặt hàng.
    </p>

Nếu page.lines có thể null, hãy thống nhất hợp đồng để Controller/query service luôn cung cấp danh sách rỗng thay vì null. Điều này giúp template đơn giản hơn và giảm nguy cơ lỗi khi render.

### Đang tải dữ liệu

Với server-side rendering, request thường được xử lý trước khi trả HTML, nên trạng thái loading thường do trình duyệt hoặc cơ chế tải bất đồng bộ hiển thị. Với ứng dụng đơn trang, View có thể render theo trạng thái đã được frontend quản lý:

    if (state.loading) {
        return <LoadingIndicator />;
    }

    if (state.error) {
        return <ErrorMessage message={state.error.message} />;
    }

    return <OrderList items={state.orders} />;

Đây là logic trình bày dựa trên trạng thái tải đã được xác định. Việc gọi API, retry hoặc xử lý dữ liệu trả về thuộc lớp quản lý dữ liệu hoặc application layer của frontend.

### Lỗi biểu mẫu

View có thể trình bày lỗi validation đã được Controller đưa vào model:

    <form th:action="@{/registrations}" th:object="${registrationForm}" method="post">
        <label for="email">Email</label>
        <input id="email" type="email" th:field="*{email}">

        <p th:if="${#fields.hasErrors('email')}"
           th:errors="*{email}">
            Email không hợp lệ
        </p>

        <button type="submit">Đăng ký</button>
    </form>

Template hiển thị lỗi đã có. Nó không nên tự gửi biểu mẫu, truy vấn tài khoản để kiểm tra email đã đăng ký hay quyết định người dùng có được tạo tài khoản hay không.

## 7. Bảo mật khi render điều kiện và danh sách

View là nơi dữ liệu được đưa vào HTML, nên cách render có ảnh hưởng trực tiếp đến bảo mật.

### Escape dữ liệu đầu ra

Khi hiển thị dữ liệu do người dùng nhập, cần dùng cơ chế escape phù hợp với ngữ cảnh. Trong Thymeleaf, th:text sẽ escape nội dung HTML:

    <p th:text="${comment.content}">Nội dung bình luận</p>

Không dùng th:utext cho nội dung không đáng tin cậy nếu chưa có quy trình làm sạch HTML phù hợp. Render HTML thô có thể tạo lỗ hổng cross-site scripting (XSS).

### Ẩn giao diện không phải là kiểm soát truy cập

Một điều kiện như sau chỉ quyết định có hiển thị nút hay không:

    <button th:if="${page.editActionVisible}">Chỉnh sửa</button>

Người dùng vẫn có thể tự gửi HTTP request đến endpoint. Controller, application service hoặc lớp bảo mật phải kiểm tra danh tính và quyền trên tài nguyên ở phía máy chủ. Model/domain tiếp tục bảo vệ các bất biến nghiệp vụ.

Không dùng điều kiện trong View làm ranh giới bảo mật duy nhất.

### Không đưa dữ liệu nhạy cảm vào View model

Chỉ truyền những trường cần thiết để hiển thị. Không đưa mật khẩu, token bí mật, dữ liệu thanh toán nhạy cảm hoặc thông tin nội bộ không cần thiết vào model của template. Dữ liệu được truyền vào View có thể xuất hiện trong HTML trả về hoặc trong công cụ kiểm tra trang của trình duyệt.

### Dùng URL và thuộc tính theo cơ chế an toàn của framework

Ưu tiên cơ chế tạo URL và binding thuộc tính do template engine cung cấp. Tránh nối chuỗi đầu vào không đáng tin cậy thành HTML hoặc JavaScript. Với dữ liệu cần nhúng vào script, phải dùng cơ chế serialize và escape đúng ngữ cảnh thay vì chèn trực tiếp giá trị vào mã.

## 8. Tách template lớn thành các phần có trách nhiệm rõ ràng

Khi một View chứa quá nhiều điều kiện, vòng lặp và markup lặp lại, hãy chia thành fragment hoặc component nhỏ theo vùng giao diện.

Ví dụ, trang đơn hàng có thể gồm:

- Phần tóm tắt đơn hàng.
- Danh sách dòng hàng.
- Nhãn trạng thái.
- Thanh hành động.
- Khu vực thông báo lỗi hoặc trạng thái rỗng.

Với Thymeleaf, một fragment có thể được định nghĩa như sau:

    <div th:fragment="statusBadge(label, cssClass)">
        <span class="badge"
              th:text="${label}"
              th:classappend="${cssClass}">
            Trạng thái
        </span>
    </div>

Sau đó được tái sử dụng trong template:

    <div th:replace="~{fragments/status :: statusBadge(
            ${page.statusLabel}, ${page.statusCssClass})}">
    </div>

Fragment nên có đầu vào rõ ràng và trách nhiệm trình bày cụ thể. Không nên biến fragment thành một nơi chứa nghiệp vụ dùng chung hoặc một thành phần tự truy cập service.

Nếu một vùng giao diện có nhiều trạng thái, hãy cân nhắc component riêng với API đầu vào rõ ràng. Việc tách nhỏ nên giúp đọc và kiểm thử dễ hơn; không cần tạo fragment cho mọi thẻ HTML đơn lẻ.

## 9. Dấu hiệu View đang chứa quá nhiều logic

Có thể xem xét refactor khi gặp một hoặc nhiều dấu hiệu sau:

- Một biểu thức điều kiện chứa nhiều trạng thái và quy tắc nghiệp vụ.
- Nhiều template lặp lại cùng một điều kiện tính quyền hoặc chính sách.
- Vòng lặp gọi service hoặc truy cập dữ liệu cho từng phần tử.
- Template phải ghép nhiều danh sách, nhóm dữ liệu hoặc tìm kiếm phần tử liên quan.
- Một thay đổi nghiệp vụ buộc phải sửa nhiều file View.
- Template chứa phép tính tiền, phí, điểm, giới hạn hoặc điều kiện chuyển trạng thái.
- Người đọc phải hiểu chi tiết database hay domain mới biết tại sao một phần tử xuất hiện.
- Việc kiểm thử template đòi hỏi phải dựng nhiều service và phụ thuộc hạ tầng.

Quy trình refactor có thể gồm:

1. Ghi rõ kết quả giao diện cần có và dữ liệu nào đang được dùng để quyết định nó.
2. Xác định điều kiện nào chỉ liên quan đến cách hiển thị, điều kiện nào là nghiệp vụ hoặc quyền truy cập.
3. Chuyển quy tắc nghiệp vụ về domain/application layer và kiểm thử tại đó.
4. Chuẩn bị dữ liệu trình bày qua view model hoặc cấu trúc dữ liệu phù hợp.
5. Rút gọn biểu thức trong template thành điều kiện đơn giản và vòng lặp trực tiếp.
6. Render thử các trường hợp có dữ liệu, rỗng, thiếu trường tùy chọn và lỗi.
7. Kiểm tra endpoint độc lập để chắc chắn việc ẩn nút không làm mất kiểm soát truy cập.

Không có một con số cố định về số dòng hoặc số điều kiện mà mọi View phải tuân theo. Hãy đánh giá mức độ dễ đọc, số trách nhiệm và mức độ phụ thuộc của template.

## 10. Kiểm thử View

Kiểm thử View nên xác nhận dữ liệu được biểu diễn đúng và các trạng thái giao diện được xử lý đầy đủ.

Với trang danh sách đơn hàng, có thể kiểm tra:

| Tình huống | Điều cần xác nhận |
|---|---|
| Có nhiều đơn hàng | Mỗi đơn hàng tạo đúng một mục hiển thị |
| Danh sách rỗng | Thông báo rỗng xuất hiện, bảng hoặc danh sách không hiển thị dữ liệu giả |
| Thiếu ghi chú tùy chọn | Vùng ghi chú được ẩn hoặc hiển thị trạng thái phù hợp |
| Trạng thái PAID | Nhãn “Đã thanh toán” và class trình bày đúng |
| Có lỗi biểu mẫu | Lỗi được hiển thị cạnh trường tương ứng |
| Người dùng không có quyền | Hành động nhạy cảm không được trình bày; endpoint cũng phải từ chối request trái phép |
| Dữ liệu có ký tự HTML | Nội dung được escape, không thực thi như markup hoặc script |

Với Spring MVC và Thymeleaf, có thể dùng kiểm thử MVC để xác nhận Controller cung cấp đúng model, đồng thời dùng công cụ kiểm thử template hoặc kiểm thử tích hợp để xác nhận HTML được render. Các quy tắc nghiệp vụ nên có unit test riêng, không cần kiểm tra chúng bằng cách so khớp HTML.

Khi kiểm thử vòng lặp, hãy dùng dữ liệu có số phần tử khác nhau, gồm danh sách rỗng, một phần tử và nhiều phần tử. Điều này giúp phát hiện lỗi ở trường hợp biên như phần tử cuối, tổng số mục và trạng thái rỗng.

## 11. Checklist khi viết View

Trước khi hoàn tất một template, hãy tự kiểm tra:

- Điều kiện chỉ chọn cách trình bày và không chứa chính sách nghiệp vụ.
- Vòng lặp chỉ render dữ liệu đã có, không gọi repository hoặc service.
- Danh sách rỗng và trường tùy chọn có cách trình bày rõ ràng.
- Dữ liệu hiển thị được escape theo đúng ngữ cảnh.
- Không truyền dữ liệu nhạy cảm không cần thiết vào View.
- Việc ẩn hành động không được xem là kiểm soát truy cập.
- Các biểu thức có tên và cấu trúc dễ đọc.
- Những vùng markup lặp lại có thể được tách thành fragment hoặc component.
- Template không phụ thuộc vào cấu trúc lưu trữ nội bộ của Model.

## Kết luận

Điều kiện và vòng lặp là công cụ cần thiết để View trình bày dữ liệu theo trạng thái và cấu trúc của giao diện. Chúng phù hợp khi biểu thức đơn giản, chỉ quyết định phần nào được render và lặp qua dữ liệu đã được chuẩn bị.

Khi template bắt đầu tính toán chính sách, kiểm tra điều kiện nghiệp vụ, truy cập dữ liệu hoặc điều phối quy trình, trách nhiệm đã vượt khỏi vai trò trình bày. Hãy chuyển quyết định về Model/domain hoặc application layer, chuẩn bị một hợp đồng dữ liệu rõ ràng cho View và giữ template tập trung vào HTML, định dạng, điều kiện hiển thị và vòng lặp render. Cách tổ chức này giúp giao diện dễ đọc, dễ kiểm thử và ít bị ảnh hưởng khi nghiệp vụ thay đổi.
