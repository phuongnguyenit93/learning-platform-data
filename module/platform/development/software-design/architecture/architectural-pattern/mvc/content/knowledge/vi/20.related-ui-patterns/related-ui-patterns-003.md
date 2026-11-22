# So sánh MVC và MVVM theo trạng thái trình bày và liên kết dữ liệu

MVC và MVVM đều giúp tách giao diện khỏi nghiệp vụ, nhưng chúng tổ chức phần tương tác và trạng thái trình bày theo cách khác nhau. Trong MVC, Controller tiếp nhận thao tác, điều phối xử lý và quyết định phản hồi hoặc View tiếp theo. Trong MVVM, ViewModel giữ trạng thái trình bày và cung cấp các hành động để View liên kết dữ liệu vào; cơ chế data binding đồng bộ trạng thái giữa View và ViewModel.

Sự khác biệt này đặc biệt rõ khi giao diện có nhiều trạng thái cục bộ: biểu mẫu đang chỉnh sửa, bộ lọc, lựa chọn tab, trạng thái tải, lỗi theo trường, nút bị vô hiệu hóa hoặc dữ liệu cập nhật bất đồng bộ. MVC thường làm rõ luồng request và phản hồi ở Controller; MVVM thường làm rõ trạng thái giao diện và mối liên hệ giữa trạng thái đó với các thành phần View.

Trong ứng dụng web theo Model–View–Controller, Controller thường nằm ở ranh giới HTTP và gọi application service. MVVM thường xuất hiện ở phía client hoặc trong framework giao diện có data binding. Hai cách có thể cùng tồn tại: backend dùng MVC để cung cấp HTML/API, còn frontend dùng ViewModel để quản lý trạng thái tương tác của màn hình.

## 1. Nhắc lại MVC và MVVM

### 1.1. MVC: Model–View–Controller

MVC phân chia giao diện thành ba vai trò:

- **Model:** dữ liệu và trạng thái mà ứng dụng cần biểu diễn. Tùy biến thể MVC, Model có thể là domain model, application model hoặc dữ liệu được chuẩn bị cho View.
- **View:** trình bày dữ liệu và cung cấp các điểm tương tác như nút, biểu mẫu, liên kết.
- **Controller:** nhận thao tác hoặc request, gọi xử lý, cập nhật Model hoặc chuẩn bị dữ liệu, rồi chọn View hay response phù hợp.

Trong web MVC phía máy chủ, luồng thường là:

1. Trình duyệt gửi HTTP request.
2. Controller bind và validate dữ liệu đầu vào.
3. Controller gọi application service.
4. Kết quả được chuyển thành Model/ViewModel.
5. Controller chọn tên View hoặc response DTO.
6. ViewResolver và template engine tạo HTML, hoặc framework serialize JSON.
7. Trình duyệt nhận response.

Controller là nơi điều phối tương tác ở ranh giới giao thức. Nó không nên chứa toàn bộ quy tắc nghiệp vụ hoặc truy vấn persistence trực tiếp.

### 1.2. MVVM: Model–View–ViewModel

MVVM giữ Model và View nhưng thay Controller bằng ViewModel:

- **Model:** dữ liệu và quy tắc của ứng dụng, thường đến từ domain/application service hoặc API.
- **View:** giao diện khai báo cách hiển thị trạng thái và cách chuyển thao tác của người dùng đến ViewModel.
- **ViewModel:** mô hình trạng thái dành riêng cho View. Nó cung cấp dữ liệu có thể quan sát, thuộc tính dẫn xuất, trạng thái tải/lỗi và các hành động (command) mà View có thể gọi.

ViewModel không phải Entity và cũng không nhất thiết là DTO của API. Nó là lớp thích nghi giữa dữ liệu ứng dụng và nhu cầu tương tác của màn hình.

Ví dụ một ViewModel trang chi tiết đơn hàng có thể cung cấp:

- orderNumber, statusLabel, totalText.
- isLoading, loadError, saveError.
- canCancel, được tính từ trạng thái và quyền đã biết.
- cancelCommand, hành động yêu cầu hủy đơn.
- refreshCommand, hành động tải lại dữ liệu.

View bind vào các thuộc tính và command này. Khi ViewModel đổi trạng thái, binding cập nhật phần giao diện liên quan.

### 1.3. Khác biệt cốt lõi

MVC đặt trọng tâm vào **điều phối thao tác và lựa chọn phản hồi**. MVVM đặt trọng tâm vào **mô hình trạng thái trình bày và liên kết dữ liệu**.

Điều này không có nghĩa MVC không có trạng thái hoặc MVVM không có điều phối. MVC vẫn có thể dùng presentation model/ViewModel và data binding; MVVM vẫn cần xử lý sự kiện và gọi dịch vụ. Khác biệt nằm ở vai trò trung tâm mà mỗi mẫu dùng để tổ chức sự tương tác.

## 2. Sơ đồ luồng tương tác

### 2.1. Luồng MVC

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant V as View
    participant C as Controller
    participant A as Application Service
    participant M as Model / View Data

    U->>V: Nhấn nút Hủy đơn
    V->>C: POST /orders/42/cancel
    C->>C: Bind và validate request
    C->>A: CancelOrderCommand
    A->>M: Kiểm tra và cập nhật nghiệp vụ
    M-->>A: Kết quả
    A-->>C: CancelResult
    C->>C: Chọn View hoặc redirect
    C-->>V: 303 Redirect / response
~~~

Với server-side MVC, thao tác thường đi qua một HTTP request mới. Controller nhận request, gọi use case và quyết định response. Nếu dùng Post/Redirect/Get, trình duyệt sau đó gửi GET để lấy trang đã cập nhật.

### 2.2. Luồng MVVM

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant V as View
    participant VM as ViewModel
    participant A as Application API / Service
    participant M as Model

    VM->>A: Tải chi tiết đơn hàng
    A->>M: Đọc dữ liệu
    M-->>A: Order detail
    A-->>VM: DTO
    VM->>VM: Cập nhật observable state
    VM-->>V: Binding cập nhật nội dung

    U->>V: Nhấn nút Hủy đơn
    V->>VM: cancelCommand()
    VM->>VM: Kiểm tra trạng thái giao diện
    VM->>A: Gửi yêu cầu hủy
    A->>M: Thực thi quy tắc nghiệp vụ
    M-->>A: Kết quả
    A-->>VM: Success / Error
    VM->>VM: Cập nhật state
    VM-->>V: Binding cập nhật nút, nhãn và thông báo
~~~

MVVM thường giữ trang hiện tại và cập nhật một phần giao diện khi observable state thay đổi. Nhưng request đến backend vẫn phải được xác thực và kiểm tra quy tắc ở máy chủ. ViewModel chỉ điều phối trạng thái client, không phải nguồn có thẩm quyền cho nghiệp vụ.

## 3. So sánh theo trách nhiệm và trạng thái trình bày

| Khía cạnh | MVC | MVVM |
|---|---|---|
| Thành phần điều phối chính | Controller | ViewModel |
| Vai trò View | Hiển thị Model và gửi thao tác đến Controller | Bind vào state/command của ViewModel |
| Trạng thái giao diện | Có thể ở Model, form object, session hoặc JavaScript tùy kiến trúc | Thường tập trung trong ViewModel |
| Cập nhật giao diện | Controller trả View/response; có thể render lại trang hoặc cập nhật client | Binding quan sát thay đổi và cập nhật View |
| Liên kết dữ liệu | Có thể dùng form binding hoặc template binding | Là cơ chế trọng tâm, thường có observable state |
| Hành động người dùng | Event/request được Controller tiếp nhận | Command hoặc method trên ViewModel |
| Kiểm thử | Controller, Model mapping, View selection, HTTP response | State transition, command, computed property, binding |
| Phù hợp | Server-rendered page, request/response rõ ràng, form truyền thống | Giao diện tương tác nhiều, trạng thái cục bộ phong phú |
| Rủi ro | Controller phình to hoặc View chứa logic | ViewModel phình to, binding hai chiều khó theo dõi |

Không nên chọn chỉ dựa vào số lượng class. Một ứng dụng MVC có thể dùng ViewModel và reactive binding; một ứng dụng MVVM vẫn cần controller/router hoặc backend MVC. Chọn mẫu theo cách trạng thái và tương tác thực sự được quản lý.

## 4. Trạng thái trình bày gồm những gì?

Trạng thái trình bày (presentation state) là thông tin cần để View biết nên hiển thị gì và cho phép người dùng làm gì tại thời điểm hiện tại.

Ví dụ với màn hình chi tiết đơn hàng:

| Nhóm trạng thái | Ví dụ | Nơi có thẩm quyền |
|---|---|---|
| Dữ liệu nghiệp vụ | Mã đơn, trạng thái, tổng tiền | Backend/domain |
| Trạng thái tải | Đang tải, đã tải, tải thất bại | ViewModel hoặc state của trang |
| Trạng thái biểu mẫu | Giá trị đang nhập, lỗi theo trường | Client form state / ViewModel |
| Trạng thái điều hướng | Tab đang chọn, bộ lọc, trang hiện tại | UI state |
| Trạng thái thao tác | Đang gửi yêu cầu hủy, thao tác thành công | ViewModel; kết quả cuối do server xác nhận |
| Quyền hiển thị | Có nên hiện nút hủy | Server cung cấp dữ liệu quyền; server vẫn kiểm tra khi thực thi |

### 4.1. Phân biệt domain state và UI state

Domain state là trạng thái có ý nghĩa nghiệp vụ: đơn hàng đang chờ thanh toán, đã thanh toán, đã giao hoặc đã hủy. UI state là trạng thái phục vụ tương tác: tab đang mở, dialog đang hiện, form đang dirty hay trang đang tải.

Không nên đưa UI state vào domain chỉ vì nó cần tồn tại trong một object. Ví dụ isDialogOpen không phải thuộc tính của đơn hàng; nó thuộc ViewModel hoặc component state.

Ngược lại, không nên chỉ lưu domain state ở client rồi xem đó là nguồn có thẩm quyền. Khi người dùng gửi thao tác hủy, server phải tải hoặc kiểm tra trạng thái hiện tại của đơn hàng và quyết định có cho phép hủy hay không.

### 4.2. Ai sở hữu trạng thái?

Một quy tắc hữu ích:

- Backend sở hữu dữ liệu và quy tắc nghiệp vụ.
- ViewModel sở hữu trạng thái trình bày của màn hình.
- View sở hữu cấu trúc và cách hiển thị.
- Controller MVC điều phối request/response ở ranh giới web.
- Form có thể giữ bản nháp người dùng nhập, nhưng bản nháp đó chưa trở thành dữ liệu nghiệp vụ cho đến khi server chấp nhận.

Khi cùng một giá trị được sao chép vào nhiều nơi, cần quy định nguồn nào có thẩm quyền và cách đồng bộ. Nếu không, giao diện có thể hiển thị dữ liệu cũ hoặc ghi đè thay đổi mới.

## 5. Data binding trong MVVM

Data binding kết nối thuộc tính của View với dữ liệu hoặc hành động của ViewModel. Binding có thể cập nhật giao diện khi state thay đổi và chuyển thao tác người dùng về ViewModel.

### 5.1. One-way binding

One-way binding truyền dữ liệu từ ViewModel sang View:

~~~text
ViewModel.statusLabel  --->  View.statusText
~~~

Khi statusLabel thay đổi, View hiển thị nhãn mới. Người dùng không sửa trực tiếp nhãn này qua input.

Phù hợp với:

- Nhãn trạng thái.
- Tổng tiền đã định dạng.
- Thông báo thành công/lỗi.
- Trạng thái nút có thể thực hiện.
- Dữ liệu chỉ đọc.

### 5.2. Two-way binding

Two-way binding đồng bộ giá trị theo cả hai hướng:

~~~text
ViewModel.searchText  <---->  View.searchInput
~~~

Khi người dùng nhập, ViewModel nhận giá trị mới; khi ViewModel thay đổi giá trị, input được cập nhật.

Phù hợp với một số trường nhập liệu như từ khóa tìm kiếm, lựa chọn hoặc giá trị form. Tuy nhiên, binding hai chiều không có nghĩa client được phép cập nhật trực tiếp domain object. Giá trị nhập vẫn là bản nháp và cần validation, xác nhận, rồi gửi command đến backend.

### 5.3. Event/command binding

View có thể liên kết thao tác với command của ViewModel:

~~~text
View.cancelButton  --->  ViewModel.cancelCommand
~~~

Command có thể có trạng thái canExecute hoặc thuộc tính tương tự để View biết có nên bật nút. Trạng thái này chỉ hỗ trợ trải nghiệm; server vẫn phải xác minh quyền và trạng thái nghiệp vụ.

### 5.4. Binding không thay thế quy tắc nghiệp vụ

Không nên đặt quy tắc “đơn đã giao không thể hủy” chỉ trong biểu thức binding. ViewModel có thể tính canCancel để ẩn hoặc disable nút, nhưng application service/domain phải kiểm tra lại khi nhận command.

Binding mô tả cách đồng bộ dữ liệu và giao diện. Nó không phải cơ chế phân quyền, transaction hoặc bảo vệ dữ liệu.

## 6. Ví dụ MVC server-side với Spring MVC

Trong MVC phía máy chủ, Controller nhận request, gọi use case, đưa ViewModel vào Model và chọn template. Biểu mẫu thường submit một HTTP request mới.

### 6.1. ViewModel dành cho trang

~~~java
public record OrderPageView(
    UUID id,
    String orderNumber,
    String statusLabel,
    String totalText,
    boolean canCancel
) {}
~~~

Đây là dữ liệu trình bày cho trang, không phải Entity JPA. Nó có thể được tạo bởi mapper từ application result.

### 6.2. Controller chọn View

~~~java
@Controller
@RequestMapping("/orders")
public class OrderPageController {

    private final GetOrderDetailUseCase getOrderDetail;
    private final CancelOrderUseCase cancelOrder;
    private final OrderPageMapper mapper;

    public OrderPageController(
            GetOrderDetailUseCase getOrderDetail,
            CancelOrderUseCase cancelOrder,
            OrderPageMapper mapper) {
        this.getOrderDetail = getOrderDetail;
        this.cancelOrder = cancelOrder;
        this.mapper = mapper;
    }

    @GetMapping("/{id}")
    public String detail(@PathVariable UUID id, Model model) {
        OrderDetail result = getOrderDetail.handle(new OrderId(id));
        model.addAttribute("order", mapper.toView(result));
        return "orders/detail";
    }

    @PostMapping("/{id}/cancel")
    public String cancel(
            @PathVariable UUID id,
            RedirectAttributes redirectAttributes) {
        cancelOrder.handle(new CancelOrderCommand(new OrderId(id)));
        redirectAttributes.addFlashAttribute(
            "notice", "Đã gửi yêu cầu hủy đơn."
        );
        return "redirect:/orders/" + id;
    }
}
~~~

Controller thể hiện rõ route, use case được gọi và View/redirect được chọn. Trong ứng dụng thật, danh tính người dùng cần được lấy từ security context và truyền vào command; đoạn ví dụ lược bớt phần đó để tập trung vào mẫu MVC.

### 6.3. View render dữ liệu

Template có thể bind các thuộc tính của đối tượng order vào phần tử HTML, ví dụ hiển thị orderNumber, statusLabel và totalText. Một form hủy đơn chỉ được render khi canCancel là true. Với Spring Security và Thymeleaf integration, CSRF token có thể được thêm vào form theo cấu hình tương ứng.

Template hiển thị ViewModel. Nó không tự quyết định quy tắc hủy đơn; nó chỉ trình bày khả năng đã được backend cung cấp.

### 6.4. Đặc điểm của trạng thái trong MVC truyền thống

Trong server-side MVC, mỗi lần submit form thường tạo request mới và server render lại trang hoặc redirect. Form object có thể giữ dữ liệu nhập và BindingResult giữ lỗi validation. Trạng thái như tab đang chọn hoặc dialog đang mở có thể do JavaScript quản lý ở client.

Cách này phù hợp khi tương tác chủ yếu theo request/response, điều hướng giữa các trang rõ ràng và phần lớn trạng thái được tải lại từ server. Nó cũng đơn giản hóa việc tạo URL có thể bookmark hoặc chia sẻ.

## 7. Ví dụ MVVM phía client

Với giao diện tương tác nhiều, ViewModel có thể quản lý state cục bộ và gọi API. Ví dụ sau dùng TypeScript theo phong cách reactive; nó minh họa vai trò MVVM, không phụ thuộc vào một framework binding cụ thể.

### 7.1. ViewModel quản lý state và command

~~~typescript
type OrderStatus = "PENDING" | "PAID" | "SHIPPED" | "CANCELLED";

type OrderDetail = {
  id: string;
  orderNumber: string;
  status: OrderStatus;
  totalText: string;
  canCancel: boolean;
};

type OrderApi = {
  getOrder(id: string): Promise<OrderDetail>;
  cancelOrder(id: string): Promise<void>;
};

class OrderDetailViewModel {
  order: OrderDetail | null = null;
  isLoading = false;
  isCancelling = false;
  loadError: string | null = null;
  actionError: string | null = null;
  notice: string | null = null;

  constructor(
    private readonly api: OrderApi,
    private readonly orderId: string
  ) {}

  get canCancel(): boolean {
    return this.order?.canCancel === true
      && !this.isLoading
      && !this.isCancelling;
  }

  async load(): Promise<void> {
    this.isLoading = true;
    this.loadError = null;

    try {
      this.order = await this.api.getOrder(this.orderId);
    } catch {
      this.loadError = "Không thể tải thông tin đơn hàng.";
    } finally {
      this.isLoading = false;
    }
  }

  async cancelCommand(): Promise<void> {
    if (!this.canCancel) return;

    this.isCancelling = true;
    this.actionError = null;
    this.notice = null;

    try {
      await this.api.cancelOrder(this.orderId);
      this.notice = "Yêu cầu hủy đơn đã được tiếp nhận.";
      await this.load();
    } catch {
      this.actionError = "Không thể hủy đơn ở trạng thái hiện tại.";
    } finally {
      this.isCancelling = false;
    }
  }
}
~~~

Đây là mã minh họa về cấu trúc. Trong framework reactive thật, các trường cần được bọc bằng observable/ref/reactive để binding nhận biết thay đổi. Nếu chỉ dùng class JavaScript thuần mà không có cơ chế quan sát, View sẽ không tự cập nhật khi thuộc tính thay đổi.

ViewModel có state và command; nó không tự truy cập database hoặc quyết định nghiệp vụ. API là adapter tới backend. canCancel giúp điều khiển trạng thái nút, còn server vẫn kiểm tra điều kiện hủy đơn khi nhận request.

### 7.2. View bind vào state

Mã giả giao diện:

~~~html
<section>
  <p data-bind="visible: isLoading">Đang tải...</p>
  <p data-bind="text: loadError"></p>

  <h1 data-bind="text: order.orderNumber"></h1>
  <p data-bind="text: order.status"></p>
  <p data-bind="text: order.totalText"></p>

  <button
    data-bind="click: cancelCommand, enable: canCancel">
    Hủy đơn
  </button>

  <p data-bind="text: notice"></p>
  <p data-bind="text: actionError"></p>
</section>
~~~

Cú pháp data-bind chỉ là minh họa kiểu binding, không phải HTML hoạt động độc lập. Framework MVVM cụ thể sẽ định nghĩa cú pháp và cách tạo observable. Điểm cần giữ là View khai báo liên kết; logic trạng thái và hành động nằm trong ViewModel.

### 7.3. Cập nhật một phần giao diện

Sau khi isCancelling chuyển thành true, View có thể disable nút và hiển thị trạng thái đang xử lý. Khi API trả kết quả, ViewModel cập nhật notice, actionError hoặc dữ liệu đơn hàng. Binding chỉ cập nhật những vùng phụ thuộc vào state đó.

Không cần tải lại toàn bộ trang nếu trải nghiệm yêu cầu phản hồi tại chỗ. Tuy nhiên, dữ liệu nghiệp vụ mới nhất vẫn phải được lấy từ server hoặc cập nhật theo response đáng tin cậy.

## 8. Cách xử lý form và validation

MVC và MVVM đều cần phân biệt validation ở giao diện với validation có thẩm quyền ở server.

### 8.1. MVC

Trong Spring MVC:

- Request được bind vào form DTO.
- Bean Validation kiểm tra cấu trúc và giới hạn.
- BindingResult giữ lỗi theo trường.
- Controller trả lại View form nếu có lỗi.
- Service/domain kiểm tra quy tắc nghiệp vụ trước khi ghi.

Ví dụ người dùng nhập số lượng bằng 0. Controller có thể trả lại form với lỗi ở trường quantity mà không gọi use case tạo đơn.

### 8.2. MVVM

ViewModel có thể kiểm tra tức thời khi người dùng nhập:

- Trường bắt buộc có giá trị.
- Email có hình dạng hợp lệ.
- Số lượng nằm trong phạm vi giao diện cho phép.
- Nút submit chỉ bật khi form đủ điều kiện sơ bộ.

Khi submit, ViewModel tạo request DTO và gọi API. Server vẫn chạy validation và quy tắc nghiệp vụ. Nếu server trả lỗi, ViewModel ánh xạ lỗi vào fieldErrors hoặc formError để View hiển thị.

### 8.3. Không coi client validation là bảo mật

Người dùng có thể bỏ qua JavaScript hoặc gửi request trực tiếp. Ẩn nút, disable nút hay đánh dấu form hợp lệ ở ViewModel không bảo đảm dữ liệu an toàn. Server phải kiểm tra mọi request và phân quyền theo danh tính đã xác thực.

## 9. Xử lý bất đồng bộ và vòng đời trạng thái

MVVM thường quản lý nhiều request bất đồng bộ hơn vì View không nhất thiết tải lại toàn bộ trang. Điều này khiến vòng đời state và thứ tự response trở nên quan trọng.

### 9.1. Trạng thái loading, success và error

Một thao tác bất đồng bộ nên có trạng thái rõ ràng:

~~~text
Idle -> Loading -> Success
                 -> Error
~~~

Tránh chỉ dùng một boolean loading chung cho mọi thao tác. Trang có thể đang tải chi tiết trong khi một thao tác khác đang gửi biểu mẫu. Tách isLoadingDetail, isSaving hoặc mô hình state theo từng tác vụ giúp View phản ánh chính xác.

### 9.2. Response đến sai thứ tự

Giả sử người dùng đổi bộ lọc nhanh hai lần:

1. Request A tìm kiếm từ khóa "book".
2. Request B tìm kiếm từ khóa "phone".
3. B trả về trước.
4. A trả về sau và ghi đè kết quả mới hơn.

ViewModel cần hủy request cũ nếu có thể, hoặc gắn sequence/request ID để chỉ chấp nhận response tương ứng với lựa chọn mới nhất. Không nên để response cũ thay thế state mới.

### 9.3. Hủy thao tác khi View rời màn hình

Khi người dùng điều hướng khỏi trang, request có thể không còn cần thiết. Framework có thể cung cấp AbortController hoặc cancellation token. ViewModel nên quản lý vòng đời subscription/request và giải phóng listener khi View bị hủy để tránh cập nhật component đã unmount hoặc rò rỉ bộ nhớ.

### 9.4. Tránh state trùng lặp

Nếu ViewModel giữ order.status, isCancelled, canCancel và statusLabel như bốn giá trị độc lập, chúng có thể mâu thuẫn sau một lần cập nhật.

Ưu tiên giữ dữ liệu nguồn tối thiểu rồi tính các thuộc tính dẫn xuất:

~~~typescript
get isCancelled(): boolean {
  return this.order?.status === "CANCELLED";
}

get canCancel(): boolean {
  return this.order?.canCancel === true
    && !this.isCancelling;
}
~~~

Trong framework reactive, dùng computed/derived state để tự tính lại khi dữ liệu nguồn thay đổi.

## 10. Data binding và rủi ro vòng lặp cập nhật

Binding hai chiều tiện lợi nhưng có thể gây khó khăn nếu nhiều thành phần cùng ghi vào một giá trị hoặc các watcher cập nhật lẫn nhau.

Ví dụ:

- Input thay đổi searchText.
- Watcher tự chuẩn hóa searchText.
- Một watcher khác cập nhật query parameter.
- Navigation cập nhật query parameter ngược lại searchText.
- Hai watcher liên tục kích hoạt nhau.

Để tránh:

- Xác định một nguồn state có thẩm quyền.
- Phân biệt giá trị gốc, giá trị đã chuẩn hóa và giá trị gửi lên API.
- Dùng computed state cho dữ liệu dẫn xuất.
- Chỉ thực hiện side effect trong command hoặc handler rõ ràng.
- Tránh watcher thay đổi ngược chính giá trị mà nó theo dõi mà không có điều kiện dừng.
- Debounce thao tác tìm kiếm nếu mỗi lần gõ không cần gọi API ngay.

### 10.1. Binding không phải lúc nào cũng cần hai chiều

Dùng one-way binding cho dữ liệu chỉ đọc và hai chiều cho input có chỉnh sửa. Với những thao tác có ý nghĩa nghiệp vụ, command tường minh thường dễ kiểm soát hơn việc bind trực tiếp vào object lớn.

Ví dụ, không bind order.status hai chiều rồi cho người dùng tự đổi trạng thái bằng select nếu việc chuyển trạng thái cần kiểm tra quyền, lý do và trạng thái hiện tại. Hãy dùng command requestCancellation hoặc approveOrder để thể hiện ý định.

## 11. Kiểm thử MVC và MVVM

Cách tổ chức state khác nhau nên trọng tâm kiểm thử cũng khác nhau.

| Mục tiêu | MVC | MVVM |
|---|---|---|
| Ánh xạ request | Controller binding/validation test | API client/request mapper test |
| Quyết định phản hồi | View name, Model, status, redirect | ViewModel state sau command |
| Trạng thái tải | HTTP response/PRG hoặc client state | Loading/success/error transitions |
| Validation | BindingResult và server validation | Client validation + server error mapping |
| Binding | Template render/form binding | Observable/computed/two-way binding |
| Quy tắc nghiệp vụ | Application/domain test | Vẫn kiểm thử ở backend application/domain |
| Giao diện | Template integration/E2E | Component/binding/E2E |
| Bất đồng bộ | Request/response và timeout | Response ordering, cancellation, race |

### 11.1. Kiểm thử Controller trong MVC

Kiểm tra:

- Route gọi đúng use case.
- Request DTO được bind và validate.
- View được chọn đúng.
- Model chứa đúng ViewModel.
- Redirect, status và flash message đúng.
- Lỗi được ánh xạ theo hợp đồng.

MockMvc phù hợp cho controller test; integration test với ViewResolver và template engine thật xác nhận template render thành công.

### 11.2. Kiểm thử ViewModel trong MVVM

Kiểm tra state transition và command:

~~~typescript
it("does not send cancellation when the command is unavailable", async () => {
  const vm = new OrderDetailViewModel(api, "order-42");
  vm.order = {
    id: "order-42",
    orderNumber: "ORD-42",
    status: "SHIPPED",
    totalText: "500.000 ₫",
    canCancel: false
  };

  await vm.cancelCommand();

  expect(vm.actionError).toBeNull();
  expect(api.cancelOrder).not.toHaveBeenCalled();
});
~~~

Test này xác nhận command không gửi request khi ViewModel biết thao tác hiện không khả dụng. Cần thêm test cho trường hợp server từ chối dù client cho phép, để xác nhận lỗi API được ánh xạ đúng. Đoạn test dùng API mock theo kiểu minh họa.

### 11.3. Kiểm thử binding

Component test nên xác nhận:

- State thay đổi làm nội dung View thay đổi.
- Input cập nhật đúng ViewModel property.
- Command được gọi khi người dùng thao tác.
- Nút disable khi canExecute false.
- Lỗi và loading state được trình bày.
- Component hủy subscription khi unmount nếu có đăng ký listener.

Không nên chỉ kiểm tra method ViewModel bằng unit test rồi giả định binding trong template đã nối đúng. Cần ít nhất một số component/integration test kiểm tra View và ViewModel hoạt động cùng nhau.

## 12. Khi nào chọn MVC?

MVC thường phù hợp khi:

- Ứng dụng chủ yếu là server-rendered web page.
- Luồng tương tác xoay quanh request/response.
- Form submit và redirect là trải nghiệm chính.
- Điều hướng URL và khả năng bookmark/chia sẻ quan trọng.
- Trạng thái cục bộ của màn hình tương đối đơn giản.
- Muốn tận dụng template engine và cơ chế HTTP của framework.

Ưu điểm là luồng xử lý dễ theo dõi qua route, Controller và response. Các vấn đề thường gặp là Controller phình to, Model chứa quá nhiều dữ liệu trình bày hoặc logic giao diện bị đẩy vào template.

MVC vẫn có thể hỗ trợ tương tác phong phú bằng JavaScript và API. Khi phần client trở nên phức tạp, có thể tổ chức riêng state của client theo một mẫu như MVVM mà không phải thay toàn bộ backend MVC.

## 13. Khi nào chọn MVVM?

MVVM thường phù hợp khi:

- Giao diện có nhiều trạng thái tương tác cục bộ.
- Nhiều vùng UI cần phản ứng với cùng một dữ liệu.
- Có lọc, tìm kiếm, tab, dialog, wizard hoặc cập nhật bất đồng bộ.
- Muốn kiểm thử state transition mà không cần render toàn bộ giao diện.
- Framework hỗ trợ observable state, computed property và binding tốt.

MVVM có thể giảm logic điều kiện trong template và giúp trạng thái giao diện tập trung. Tuy nhiên, ViewModel có thể trở nên quá lớn nếu gom cả điều hướng, gọi API, validation, cache, analytics và quy tắc nghiệp vụ vào một class. Hãy chia theo màn hình hoặc use case và giữ domain rule ở backend/domain.

## 14. Có thể kết hợp MVC và MVVM không?

Có. Một kiến trúc web phổ biến có thể dùng:

- Spring MVC ở backend để tiếp nhận HTTP, gọi application service và trả HTML/JSON.
- MVVM hoặc một mô hình reactive tương tự ở frontend để quản lý state của trang.
- API DTO làm hợp đồng giữa frontend và backend.
- Domain/application service làm nguồn có thẩm quyền cho quy tắc nghiệp vụ.

~~~mermaid
flowchart TB
    subgraph Browser[Trình duyệt]
        View[View / Components]
        VM[ViewModel / UI State]
        View <--> VM
    end

    subgraph Backend[Backend Service]
        Controller[MVC Controller]
        App[Application Service]
        Domain[Domain Model]
        Repo[Repository Adapter]
        Controller --> App
        App --> Domain
        App --> Repo
    end

    VM <-->|HTTP API / DTO| Controller
~~~

Trong mô hình này, backend MVC và frontend MVVM giải quyết hai ranh giới khác nhau. Backend điều phối request và bảo vệ nghiệp vụ; frontend quản lý trạng thái tương tác và binding. Không nên gọi toàn bộ hệ thống là “MVVM” chỉ vì frontend có ViewModel, cũng không nên nghĩ MVC backend loại trừ việc dùng reactive UI.

## 15. Những nhầm lẫn thường gặp

### Xem ViewModel là domain model

ViewModel phục vụ màn hình và có thể chứa nhãn đã dịch, chuỗi định dạng hoặc cờ hiển thị. Domain model chứa trạng thái và quy tắc nghiệp vụ. Hai loại có thể cùng biểu diễn một đơn hàng nhưng không có cùng trách nhiệm.

### Cho rằng MVC không có data binding

MVC framework có thể hỗ trợ form binding, model binding hoặc template binding. Khác biệt của MVVM là ViewModel và binding thường trở thành cơ chế trung tâm để quản lý state và tương tác.

### Cho rằng MVVM luôn là client-side và MVC luôn là server-side

Đây là cách triển khai phổ biến trong web, không phải định nghĩa tuyệt đối. MVC và MVVM là mẫu tổ chức trách nhiệm; chúng có thể xuất hiện ở các nền tảng khác nhau.

### Dùng two-way binding cho mọi dữ liệu

Two-way binding không phù hợp với mọi giá trị. Dữ liệu chỉ đọc nên one-way; hành động nghiệp vụ nên là command rõ ràng. Binding hai chiều rộng có thể làm thay đổi state khó truy vết.

### Để ViewModel chứa nghiệp vụ

ViewModel có thể tính trạng thái trình bày như canShowCancelButton, nhưng không nên là nơi quyết định chính sách hủy đơn có hợp lệ hay không. Server/domain phải kiểm tra lại.

### Tin trạng thái client sau khi gửi request

Client có thể bị sửa, request có thể bị gửi lặp hoặc dữ liệu có thể đã thay đổi. Mọi thao tác ghi cần được server xác thực, phân quyền và kiểm tra trạng thái hiện tại.

### Tạo quá nhiều lớp trung gian

Không cần có một DTO, ViewModel, mapper và adapter riêng cho từng trường hợp nếu chúng không bảo vệ ranh giới có ý nghĩa. Tách lớp khi nó làm rõ hợp đồng hoặc vòng đời, không chỉ để tăng số lượng file.

## 16. Bảng chọn nhanh theo đặc điểm giao diện

| Đặc điểm | Hướng phù hợp |
|---|---|
| Trang đọc dữ liệu, điều hướng URL rõ ràng | MVC server-side |
| Form truyền thống với submit/redirect | MVC |
| Dashboard cập nhật nhiều vùng theo thời gian thực | MVVM hoặc reactive UI |
| Wizard nhiều bước, nhiều state cục bộ | MVVM |
| API backend phục vụ nhiều client | MVC/Web adapter ở backend; frontend chọn mẫu riêng |
| Giao diện đơn giản nhưng có vài tương tác động | MVC kết hợp JavaScript/component state |
| Ứng dụng có nhiều biểu mẫu và validation phía client | MVVM có thể giúp tập trung form state; server vẫn validate |

Không có ngưỡng cứng dựa trên số lượng màn hình hay component. Hãy xem trạng thái có thường xuyên thay đổi không, bao nhiêu phần View phụ thuộc vào nó và nhóm phát triển cần kiểm thử hành vi theo cách nào.

## 17. Checklist thiết kế trạng thái và binding

1. Phân biệt domain state, server state, form draft và UI state.
2. Xác định nguồn có thẩm quyền cho từng giá trị.
3. Giữ ViewModel dành cho nhu cầu trình bày, không biến nó thành domain model.
4. Dùng one-way binding cho dữ liệu chỉ đọc.
5. Dùng two-way binding có chọn lọc cho input và bản nháp.
6. Dùng command tường minh cho hành động có ý nghĩa nghiệp vụ.
7. Tính thuộc tính dẫn xuất thay vì lưu nhiều bản sao state dễ lệch nhau.
8. Quản lý loading, success, error và trạng thái đang gửi theo từng thao tác.
9. Xử lý response bất đồng bộ đến sai thứ tự và hủy request khi phù hợp.
10. Kiểm tra validation và authorization ở server dù client đã kiểm tra.
11. Kiểm thử Controller/HTTP contract trong MVC.
12. Kiểm thử state transition và binding trong MVVM.
13. Kiểm thử template/component tích hợp và hành trình E2E quan trọng.
14. Giữ quy tắc nghiệp vụ trong application/domain, không đặt trong binding hoặc template.

## Kết luận

MVC và MVVM cùng tách giao diện khỏi nghiệp vụ nhưng tổ chức phần tương tác theo trọng tâm khác nhau. MVC dùng Controller để tiếp nhận thao tác, điều phối use case và chọn View hoặc response. MVVM dùng ViewModel để giữ trạng thái trình bày, cung cấp command và liên kết dữ liệu với View. Khi trạng thái giao diện đơn giản và luồng request/response rõ, MVC thường dễ triển khai; khi giao diện có nhiều trạng thái cục bộ và cập nhật phản ứng, MVVM có thể làm mối liên hệ giữa state và View rõ hơn. Hai mẫu có thể kết hợp ở hai phía của một dịch vụ: backend MVC bảo vệ hợp đồng và nghiệp vụ, frontend MVVM quản lý trải nghiệm tương tác.

