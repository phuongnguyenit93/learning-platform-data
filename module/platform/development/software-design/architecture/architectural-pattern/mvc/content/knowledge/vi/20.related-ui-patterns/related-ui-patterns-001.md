# So sánh MVC và MVP theo trách nhiệm điều phối trình bày

Trong module **MODEL_VIEW_CONTROLLER**, ứng dụng được tổ chức để phân tách trạng thái và quy tắc nghiệp vụ, phần trình bày, cùng cách tiếp nhận tương tác. MVC là một mẫu kiến trúc giao diện phổ biến cho ứng dụng web: Controller nhận request hoặc sự kiện, điều phối xử lý và chọn cách trả kết quả qua View. Một mẫu liên quan là **Model–View–Presenter (MVP)**, trong đó Presenter đứng giữa View và Model để điều phối hành vi của màn hình.

MVC và MVP đều hướng đến việc giảm sự phụ thuộc trực tiếp giữa giao diện và nghiệp vụ. Khác biệt nổi bật nằm ở nơi đặt logic điều phối trình bày và cách View giao tiếp với phần điều phối đó. Trong MVC, Controller thường tiếp nhận input và quyết định response hoặc View cần hiển thị. Trong MVP, View thường chuyển sự kiện cho Presenter; Presenter gọi Model/service rồi cập nhật View thông qua một interface.

Không có một định nghĩa MVC duy nhất áp dụng cho mọi framework. Một số biến thể cho phép View quan sát Model; một số biến thể để Controller điều phối hầu hết tương tác. MVP cũng có các biến thể như Passive View và Supervising Controller. Vì vậy, khi so sánh cần xác định biến thể đang nói đến, thay vì chỉ dựa vào tên mẫu.

## 1. Ba thành phần nền tảng

Cả MVC và MVP đều có ba khái niệm chính:

- **Model:** trạng thái, dữ liệu và quy tắc nghiệp vụ mà ứng dụng cần bảo vệ. Trong ứng dụng web, Model có thể gồm domain object, application service, repository và các hợp đồng liên quan. Model không đồng nghĩa với một bảng database hoặc một JPA entity.
- **View:** phần trình bày mà người dùng nhìn thấy và tương tác, chẳng hạn trang HTML, form, màn hình desktop hoặc thành phần giao diện trên thiết bị di động.
- **Thành phần điều phối trình bày:** nhận tương tác từ View, gọi Model/service cần thiết và quyết định View cần hiển thị trạng thái nào. Thành phần này là Controller trong MVC và Presenter trong MVP.

Mục tiêu là để quy tắc nghiệp vụ không phụ thuộc vào chi tiết của giao diện. Ví dụ, quy tắc một đơn hàng không thể bị hủy sau khi đã giao phải được bảo vệ trong Model hoặc use case, dù thao tác được khởi tạo từ trang web MVC, ứng dụng MVP hay API.

## 2. MVC điều phối tương tác như thế nào?

Trong MVC truyền thống, Controller nhận input, diễn giải hành động, gọi Model hoặc tầng ứng dụng và chọn View/response. View trình bày dữ liệu được cung cấp. Tùy biến thể, View có thể đọc Model hoặc chỉ nhận một view model do Controller chuẩn bị.

Luồng khái quát:

~~~mermaid
flowchart LR
    U[Người dùng] --> V[View]
    V -->|Sự kiện hoặc request| C[Controller]
    C -->|Gọi use case| M[Model]
    M -->|Kết quả| C
    C -->|View model / response| V
    V --> U
~~~

Với ứng dụng web server-side MVC, trình duyệt gửi HTTP request đến Controller. Controller gọi service, đặt dữ liệu vào model dành cho View rồi trả tên template hoặc response body. View engine render HTML từ dữ liệu đó.

Ví dụ với Spring MVC:

~~~java
@Controller
@RequestMapping("/products")
public class ProductController {
    private final ProductQuery productQuery;

    public ProductController(ProductQuery productQuery) {
        this.productQuery = productQuery;
    }

    @GetMapping("/{id}")
    public String detail(@PathVariable long id, Model model) {
        ProductDetailView page = productQuery.getDetail(id);
        model.addAttribute("page", page);
        return "products/detail";
    }
}
~~~

Controller nhận path parameter, gọi query service, đưa **ProductDetailView** vào model của Spring và chọn template. Template trình bày các trường được cung cấp:

~~~html
<h1 th:text="${page.name}">Tên sản phẩm</h1>
<p th:text="${page.description}">Mô tả sản phẩm</p>
<p th:text="${page.price}">Giá sản phẩm</p>
~~~

Controller không cần tự tạo từng thẻ HTML. View cũng không cần tự truy vấn database hoặc quyết định quy tắc giá. Đây là một cách triển khai MVC thường gặp trong ứng dụng web.

## 3. MVP điều phối tương tác như thế nào?

Trong MVP, View thường triển khai một interface mà Presenter có thể gọi. View nhận thao tác của người dùng rồi chuyển sự kiện cho Presenter. Presenter điều phối Model/service và yêu cầu View cập nhật bằng các phương thức của interface.

Luồng khái quát:

~~~mermaid
flowchart LR
    U[Người dùng] --> V[View]
    V -->|Gọi sự kiện| P[Presenter]
    P -->|Gọi use case| M[Model]
    M -->|Kết quả| P
    P -->|Gọi phương thức hiển thị| V
    V --> U
~~~

Ví dụ, màn hình chi tiết sản phẩm có thể định nghĩa interface:

~~~java
public interface ProductView {
    void showLoading();
    void showProduct(String name, String description, String price);
    void showError(String message);
    void hideLoading();
}
~~~

Presenter điều phối việc tải dữ liệu:

~~~java
public final class ProductPresenter {
    private final ProductView view;
    private final ProductQuery productQuery;

    public ProductPresenter(ProductView view, ProductQuery productQuery) {
        this.view = view;
        this.productQuery = productQuery;
    }

    public void load(long productId) {
        view.showLoading();
        try {
            ProductDetail product = productQuery.getDetail(productId);
            view.showProduct(
                    product.name(),
                    product.description(),
                    product.formattedPrice()
            );
        } catch (ProductNotFoundException exception) {
            view.showError("Không tìm thấy sản phẩm.");
        } finally {
            view.hideLoading();
        }
    }
}
~~~

View triển khai interface bằng framework giao diện cụ thể:

~~~java
public final class ProductScreen implements ProductView {
    private final ProductPresenter presenter;

    public ProductScreen(ProductQuery productQuery) {
        this.presenter = new ProductPresenter(this, productQuery);
    }

    public void onScreenOpened(long productId) {
        presenter.load(productId);
    }

    @Override
    public void showLoading() {
        // Hiển thị chỉ báo đang tải
    }

    @Override
    public void showProduct(String name, String description, String price) {
        // Cập nhật các thành phần giao diện
    }

    @Override
    public void showError(String message) {
        // Hiển thị thông báo lỗi
    }

    @Override
    public void hideLoading() {
        // Ẩn chỉ báo đang tải
    }
}
~~~

Presenter không cần biết View được xây bằng JavaFX, Android View hay một thư viện UI khác. Nó chỉ biết interface **ProductView**. Trong dự án thực tế, cách tạo Presenter và gắn View có thể do dependency injection hoặc lifecycle của framework quản lý; ví dụ trên tập trung vào quan hệ điều phối.

## 4. Khác biệt chính: ai sở hữu logic điều phối trình bày?

Điểm khác biệt trọng tâm không phải Model có dữ liệu gì, mà là phần nào chịu trách nhiệm phản ứng với sự kiện và cập nhật giao diện.

| Trách nhiệm | MVC | MVP |
| --- | --- | --- |
| Nhận input | Controller nhận request hoặc sự kiện từ View/framework | View nhận thao tác rồi gọi Presenter |
| Điều phối màn hình | Controller điều phối request, hành động và response | Presenter điều phối luồng tương tác của màn hình |
| Gọi Model/service | Thường do Controller hoặc tầng ứng dụng được Controller gọi | Thường do Presenter gọi use case/service |
| Cập nhật giao diện | Controller cung cấp model/view model hoặc response; View render | Presenter gọi các phương thức trên View interface |
| Phụ thuộc của phần điều phối | Controller thường phụ thuộc framework web và hợp đồng request/response | Presenter có thể phụ thuộc vào interface View, không cần phụ thuộc UI toolkit |
| Kiểm thử logic trình bày | Kiểm thử Controller và luồng request/response | Kiểm thử Presenter bằng fake/mock View |

Trong MVC web, Controller thường gắn với giao thức HTTP: route, path variable, form binding, session, status code và điều hướng. Presenter trong MVP thường gắn với vòng đời và hành vi của một màn hình: tải dữ liệu, phản hồi nút bấm, bật/tắt trạng thái loading và hiển thị lỗi.

Sự phân biệt này mang tính điển hình. Một MVC client-side có thể có Controller rất giàu logic UI; một MVP có thể để View xử lý một số binding đơn giản. Điều cần xem là hợp đồng và trách nhiệm thực tế của từng thành phần.

## 5. Hai biến thể phổ biến của MVP

### Passive View

Trong **Passive View**, View càng ít logic càng tốt. View chủ yếu hiển thị dữ liệu và chuyển sự kiện. Presenter quyết định nội dung, trạng thái loading, thông báo lỗi, trạng thái enable/disable và thứ tự các bước tương tác.

Ưu điểm là Presenter có thể được kiểm thử gần như hoàn toàn bằng unit test mà không cần khởi tạo UI framework. Nhược điểm là interface View có thể có nhiều phương thức và Presenter có thể trở nên lớn nếu một màn hình chứa quá nhiều chức năng.

### Supervising Controller

Trong **Supervising Controller**, View có thể đảm nhận một số việc đơn giản như binding dữ liệu hoặc hiển thị thuộc tính trực tiếp. Presenter tập trung vào logic trình bày phức tạp, phối hợp nhiều dữ liệu hoặc xử lý tương tác cần quyết định.

Biến thể này giảm số phương thức cần khai báo trong View interface, nhưng một phần logic hiển thị nằm trong View nên cần kiểm thử UI bổ sung. Nó là cách dung hòa giữa View hoàn toàn thụ động và View tự xử lý quá nhiều nghiệp vụ.

## 6. MVC cũng có nhiều cách tổ chức View và Model

Không nên hiểu MVC như một sơ đồ duy nhất. Một số cách triển khai thường gặp:

- **Server-side MVC:** Controller xử lý HTTP request, chuẩn bị model cho template và trả HTML. Spring MVC là ví dụ tiêu biểu.
- **Client-side MVC:** Controller điều phối sự kiện trong ứng dụng chạy trên trình duyệt; View và Model có thể được quản lý bởi thư viện phía client.
- **Model-observing View:** View đăng ký lắng nghe thay đổi của Model và tự cập nhật khi dữ liệu đổi.
- **Controller-mediated View:** Controller chủ động lấy dữ liệu và cung cấp một cấu trúc trình bày cho View.

Trong ứng dụng web hiện đại, View thường nhận **ViewModel/DTO** được chuẩn bị riêng thay vì truy cập trực tiếp domain entity. Điều này giúp kiểm soát dữ liệu trả về, tránh lộ trường nội bộ và giảm phụ thuộc giữa template với cấu trúc lưu trữ.

Vì thế, khi nhóm nói “đang dùng MVC”, nên làm rõ Controller có trách nhiệm gì, View có được đọc Model hay không và logic trình bày đang nằm ở đâu. Tên mẫu một mình chưa đủ để mô tả ranh giới mã nguồn.

## 7. Ví dụ cùng một thao tác trong MVC và MVP

Giả sử người dùng nhấn nút **Thêm vào giỏ hàng**. Hệ thống cần kiểm tra sản phẩm còn được bán, thêm sản phẩm vào giỏ và cập nhật số lượng hiển thị.

### Cách tổ chức theo MVC

1. Người dùng gửi form hoặc request đến route thêm sản phẩm.
2. Controller nhận product ID và số lượng, kiểm tra binding/validation.
3. Controller gọi use case AddToCart.
4. Use case kiểm tra quy tắc nghiệp vụ và cập nhật giỏ.
5. Controller chọn redirect hoặc response DTO.
6. View render trạng thái giỏ hàng mới.

~~~java
@PostMapping("/cart/items")
public String addToCart(
        @Valid @ModelAttribute("form") AddCartItemForm form,
        BindingResult result,
        @AuthenticationPrincipal AppPrincipal principal,
        RedirectAttributes redirectAttributes) {

    if (result.hasErrors()) {
        return "cart/edit";
    }

    cartService.addItem(
            principal.userId(),
            form.productId(),
            form.quantity()
    );
    redirectAttributes.addFlashAttribute("message", "Đã thêm vào giỏ hàng.");
    return "redirect:/cart";
}
~~~

Controller chịu trách nhiệm cho ranh giới HTTP, binding và điều hướng. Use case chịu trách nhiệm quy tắc thêm hàng. View hiển thị thông báo và giỏ hàng.

### Cách tổ chức theo MVP

1. View nhận sự kiện nhấn nút và gọi Presenter.
2. Presenter đặt trạng thái loading và gọi use case AddToCart.
3. Use case kiểm tra quy tắc nghiệp vụ và cập nhật giỏ.
4. Presenter yêu cầu View hiển thị thành công hoặc lỗi.
5. View cập nhật số lượng và thông báo.

~~~java
public interface CartView {
    void setAdding(boolean adding);
    void showCartCount(int count);
    void showMessage(String message);
    void showError(String message);
}

public final class CartPresenter {
    private final CartView view;
    private final AddToCartUseCase addToCart;
    private final CartQuery cartQuery;
    private final UserId currentUser;

    public CartPresenter(
            CartView view,
            AddToCartUseCase addToCart,
            CartQuery cartQuery,
            UserId currentUser) {
        this.view = view;
        this.addToCart = addToCart;
        this.cartQuery = cartQuery;
        this.currentUser = currentUser;
    }

    public void addItem(ProductId productId, int quantity) {
        view.setAdding(true);
        try {
            addToCart.execute(currentUser, productId, quantity);
            int count = cartQuery.getItemCount(currentUser);
            view.showCartCount(count);
            view.showMessage("Đã thêm vào giỏ hàng.");
        } catch (ProductUnavailableException exception) {
            view.showError("Sản phẩm hiện không thể thêm vào giỏ.");
        } finally {
            view.setAdding(false);
        }
    }
}
~~~

Ví dụ MVP mô tả một màn hình tương tác trực tiếp, không phải cách thay thế HTTP authorization. Trong ứng dụng có backend, server vẫn phải xác thực danh tính và kiểm tra quyền; không tin currentUser do client tự gửi. Presenter điều phối giao diện, còn use case/server bảo vệ quy tắc nghiệp vụ.

## 8. So sánh khả năng kiểm thử

### Kiểm thử MVC

Trong ứng dụng web MVC, có thể kiểm thử ở nhiều cấp:

- Unit test cho service/use case để xác minh quy tắc nghiệp vụ.
- Unit test cho mapper hoặc thành phần chuẩn bị ViewModel.
- Web/controller test để kiểm tra route, binding, validation, status, redirect và dữ liệu đưa vào View.
- Integration test để xác minh luồng qua repository và database.

Ví dụ Spring MockMvc có thể kiểm tra Controller trả đúng View và model attribute, nhưng không nên đặt mọi quy tắc nghiệp vụ vào Controller chỉ để test dễ hơn. Quy tắc cần được kiểm thử ở tầng sở hữu chúng.

### Kiểm thử MVP

Presenter thường dễ unit test vì có thể truyền một fake View:

~~~java
final class FakeCartView implements CartView {
    int cartCount;
    boolean adding;
    String message;
    String error;

    public void setAdding(boolean adding) {
        this.adding = adding;
    }

    public void showCartCount(int count) {
        this.cartCount = count;
    }

    public void showMessage(String message) {
        this.message = message;
    }

    public void showError(String message) {
        this.error = message;
    }
}
~~~

Test có thể gọi Presenter và xác nhận các phương thức của View được gọi với kết quả mong đợi. Ví dụ, khi sản phẩm không còn bán, Presenter phải yêu cầu View hiển thị lỗi và kết thúc trạng thái loading.

MVP không loại bỏ nhu cầu kiểm thử giao diện thật. Cần có test UI/integration để xác minh View nối đúng sự kiện, render đúng trạng thái và quản lý vòng đời đúng cách.

## 9. So sánh coupling và khả năng thay đổi

| Tiêu chí | MVC | MVP |
| --- | --- | --- |
| Ranh giới giao diện | View thường gắn với route, template hoặc response contract của framework | View được trừu tượng hóa qua interface |
| Thay UI framework | Có thể cần thay Controller/View adapter và template | Có thể giữ Presenter nếu interface View và use case ổn định |
| Lượng mã kết nối | Thường ít interface riêng cho từng View | Có thể nhiều interface và phương thức View |
| Logic trình bày phức tạp | Có nguy cơ dồn nhiều logic vào Controller | Có nơi tập trung rõ ở Presenter |
| Test logic màn hình | Phụ thuộc mức tách Controller khỏi framework | Presenter thường dễ test độc lập |
| Phù hợp với HTTP | Rất tự nhiên vì Controller xử lý request/response | Có thể dùng, nhưng cần thêm adapter HTTP nếu chọn MVP cho UI web |
| Quản lý vòng đời | Framework web thường quản lý request và Controller | Cần quản lý Presenter/View attach, detach và callback |

MVP có thể giảm coupling giữa logic trình bày và UI toolkit, nhưng interface View cũng là một hợp đồng cần duy trì. Nếu màn hình có hàng chục phương thức nhỏ và nhiều trạng thái, Presenter có thể trở thành một lớp điều phối quá lớn. Nên chia màn hình hoặc use case khi trách nhiệm đã vượt quá phạm vi dễ hiểu.

MVC thường đơn giản hơn cho luồng web request/response. Tuy nhiên, Controller vẫn có thể trở thành “God Controller” nếu chứa validation nghiệp vụ, truy vấn, điều phối nhiều dịch vụ và định dạng response trong cùng một phương thức. Giải pháp là giữ Controller mỏng, chuyển nghiệp vụ sang use case và dùng DTO/ViewModel rõ ràng.

## 10. Xử lý form, validation và lỗi

Với MVC server-side, Controller thường là điểm tiếp nhận form:

- Binding chuyển dữ liệu request vào form object.
- Validation kiểm tra định dạng và ràng buộc đầu vào.
- Controller trả lại View cùng lỗi theo trường hoặc lỗi chung.
- Use case kiểm tra quy tắc nghiệp vụ sau khi dữ liệu qua validation.
- Kết quả nghiệp vụ được ánh xạ thành thông báo hoặc response.

Với MVP, View chuyển dữ liệu người dùng nhập cho Presenter. Presenter có thể phối hợp kiểm tra hiển thị như trường bắt buộc, trạng thái nút hoặc thông báo. Quy tắc nghiệp vụ vẫn phải được kiểm tra ở use case/Model để mọi client đều tuân thủ.

Không nên hiểu MVP có nghĩa Presenter phải chứa toàn bộ validation. Có thể chia:

| Loại kiểm tra | Vị trí phù hợp |
| --- | --- |
| Định dạng đầu vào cơ bản, độ dài, trường bắt buộc | Form DTO/validator hoặc lớp tiếp nhận |
| Phản hồi tức thời của giao diện | View/Presenter theo nhu cầu UX |
| Quy tắc nghiệp vụ và tính nhất quán | Use case/Model |
| Quyền truy cập tài nguyên | Server-side authorization |
| Ánh xạ lỗi sang giao diện | Controller trong MVC hoặc Presenter trong MVP |

Thông báo lỗi cần rõ ràng và không tiết lộ stack trace, SQL hoặc chi tiết nội bộ. Với API, trả error DTO ổn định; với HTML form, hiển thị lỗi tại trường phù hợp và giữ lại dữ liệu không nhạy cảm.

## 11. Trạng thái và vòng đời giao diện

MVC web thường tận dụng vòng đời request: dữ liệu tạm được chuẩn bị trong request model, View render response rồi request kết thúc. Trạng thái cần tồn tại qua nhiều request được lưu trong session, database hoặc một cơ chế lưu trữ có phạm vi rõ ràng.

MVP thường có Presenter gắn với vòng đời một View hoặc màn hình. Với ứng dụng desktop/mobile, cần quản lý:

- Khi View được tạo, Presenter được gắn với View như thế nào.
- Khi View bị hủy hoặc rời màn hình, Presenter có được detach hay không.
- Callback bất đồng bộ có thể cập nhật View đã bị hủy hay không.
- Dữ liệu màn hình nào cần được giữ lại khi xoay thiết bị hoặc khôi phục trạng thái.
- Tác vụ đang chạy có thể hủy hoặc bỏ qua kết quả khi người dùng rời màn hình không.

Nếu Presenter giữ tham chiếu đến Activity, Fragment hoặc View đã bị hủy, ứng dụng có thể gặp memory leak hoặc cập nhật UI sai vòng đời. Có thể dùng interface attach/detach, lifecycle-aware component hoặc cơ chế cancellation phù hợp với framework.

## 12. Điều hướng và nhiều màn hình

Trong MVC web, điều hướng thường được thể hiện bằng route, redirect hoặc response. Controller có thể trả tên View, redirect URL hoặc response API. Điều hướng là một phần của hợp đồng HTTP và trình duyệt.

Trong MVP, Presenter có thể yêu cầu một navigation service hoặc router chuyển sang màn hình khác. Không nên để Presenter tự tạo Activity/Window cụ thể nếu mục tiêu là giữ nó độc lập với UI framework. Thay vào đó, định nghĩa một interface điều hướng hoặc phát ra ý định điều hướng để lớp ngoài thực hiện.

Khi ứng dụng có nhiều màn hình, tránh để Presenter của màn hình A gọi trực tiếp Presenter của màn hình B. Điều hướng nên đi qua một cơ chế chung để quản lý lịch sử, tham số, quyền và vòng đời.

## 13. Khi nào nên chọn MVC?

MVC thường phù hợp khi:

- Ứng dụng chủ yếu xử lý HTTP request/response.
- Framework web đã cung cấp routing, Controller, model binding và view rendering.
- Mỗi request có thể được xử lý như một đơn vị tương đối độc lập.
- View được render phía server hoặc API response là đầu ra chính.
- Logic trình bày không quá phức tạp và có thể giữ Controller mỏng.

Ví dụ phù hợp gồm trang quản trị, hệ thống quản lý dữ liệu, website thương mại điện tử server-rendered và REST API dùng Controller làm adapter HTTP.

## 14. Khi nào nên chọn MVP?

MVP thường phù hợp khi:

- Màn hình có nhiều tương tác và trạng thái thay đổi theo sự kiện.
- Muốn kiểm thử logic điều phối giao diện mà không khởi chạy UI framework.
- Cần tách logic màn hình khỏi Android View, JavaFX hoặc toolkit cụ thể.
- Nhiều thành phần giao diện cần phản hồi theo một luồng tương tác có quy tắc rõ.
- View có thể được biểu diễn bằng interface và triển khai thay thế được.

Ví dụ gồm màn hình nhập liệu nhiều bước, ứng dụng desktop, ứng dụng di động hoặc màn hình có nhiều trạng thái loading/error/empty/success.

MVP không tự động là lựa chọn tốt hơn cho mọi ứng dụng web. Nếu phần lớn công việc chỉ là nhận request, gọi use case và trả response, thêm Presenter cùng View interface cho từng trang có thể tạo nhiều lớp mà không đem lại lợi ích tương xứng.

## 15. Có thể kết hợp MVC và MVP không?

Một hệ thống có thể dùng MVC ở ranh giới HTTP và dùng Presenter trong một thành phần giao diện phức tạp. Ví dụ, Controller phục vụ trang web hoặc endpoint, còn một widget tương tác phía client sử dụng cấu trúc gần MVP để quản lý trạng thái của chính widget đó.

Điều quan trọng là không để hai lớp điều phối cùng sở hữu một quyết định. Nếu Controller và Presenter đều tự quyết định validation, điều hướng và trạng thái, luồng xử lý dễ bị chia đôi và khó kiểm thử.

Một cách chia hợp lý:

- Controller xử lý giao thức HTTP, xác thực request, binding và response.
- Presenter điều phối trạng thái tương tác của một màn hình hoặc widget phía client.
- Use case/Model sở hữu quy tắc nghiệp vụ và tính nhất quán dữ liệu.
- View chỉ trình bày dữ liệu và chuyển tương tác theo hợp đồng đã định.

Nếu Presenter phía client gọi API, backend vẫn phải thực hiện validation và authorization. Không coi logic ở trình duyệt là hàng rào bảo vệ dữ liệu.

## 16. Bảng quyết định nhanh

| Câu hỏi | Gợi ý |
| --- | --- |
| Luồng chính là HTTP request → use case → HTML/JSON? | MVC thường tự nhiên hơn |
| Màn hình có nhiều trạng thái và tương tác cần điều phối? | Cân nhắc MVP |
| Muốn unit test logic màn hình bằng fake View? | MVP Passive View có lợi thế |
| Framework đã cung cấp Controller và binding tốt? | Tận dụng MVC trước |
| Có nhiều lớp Presenter chỉ để chuyển tiếp một lời gọi? | Xem lại việc dùng MVP có tạo thêm giá trị không |
| Controller chứa nhiều quy tắc nghiệp vụ? | Tách use case/Model; không nhất thiết phải chuyển sang MVP |
| Cần thay UI toolkit nhưng giữ logic tương tác? | MVP với View interface có thể phù hợp |

Không chọn mẫu chỉ theo mức độ phổ biến. Hãy xem nơi logic trình bày đang nằm, độ phức tạp tương tác, khả năng kiểm thử và chi phí duy trì các hợp đồng giữa thành phần.

## 17. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| MVC luôn có View đọc trực tiếp Model | Tùy biến thể; server-side MVC thường truyền model/view model cho template |
| MVP chỉ là đổi tên Controller thành Presenter | Presenter thường điều phối View qua interface và có trách nhiệm cụ thể với màn hình |
| Presenter chứa toàn bộ nghiệp vụ | Quy tắc nghiệp vụ vẫn thuộc Model/use case; Presenter điều phối tương tác |
| MVP không cần kiểm thử UI | Vẫn cần test để xác minh View nối sự kiện và render đúng |
| MVC chỉ dùng cho website | MVC cũng được dùng trong nhiều loại ứng dụng có giao diện |
| Dùng MVP thì tự động dễ bảo trì | Interface và Presenter quá lớn cũng tạo coupling và boilerplate |
| Ẩn nút trên View là đủ bảo mật | Server vẫn phải xác thực và kiểm tra quyền |
| Có thể thay MVC bằng MVP để sửa Controller phình to | Trước tiên cần tách nghiệp vụ khỏi Controller và xác định đúng trách nhiệm điều phối |

## 18. Quy trình lựa chọn và tổ chức mã nguồn

Khi thiết kế một màn hình hoặc chức năng, hãy thực hiện theo trình tự:

1. Xác định loại ứng dụng và ranh giới tương tác: HTTP request/response hay màn hình tương tác dài hạn.
2. Liệt kê sự kiện, trạng thái và kết quả mà giao diện cần hỗ trợ.
3. Xác định logic nào là nghiệp vụ, logic nào chỉ điều phối trình bày.
4. Đặt quy tắc nghiệp vụ trong Model/use case, không đặt vào View.
5. Nếu dùng MVC, giữ Controller tập trung vào request, binding, điều phối và response.
6. Nếu dùng MVP, định nghĩa View interface đủ nhỏ và để Presenter điều phối các trạng thái màn hình.
7. Quy định rõ ai sở hữu validation, thông báo lỗi, điều hướng và trạng thái loading.
8. Kiểm thử nghiệp vụ độc lập; kiểm thử Controller hoặc Presenter ở đúng ranh giới.
9. Bổ sung UI/integration test cho luồng người dùng quan trọng.
10. Rà soát trách nhiệm khi Controller, Presenter hoặc View interface trở nên quá lớn.

Với ứng dụng web Spring MVC, thường bắt đầu bằng Controller mỏng, use case rõ và ViewModel riêng. Chỉ cân nhắc MVP cho phần giao diện có tương tác phức tạp cần được điều phối và kiểm thử độc lập. Cách chọn này giữ cho kiến trúc phù hợp với luồng thực tế và tránh tạo thêm lớp không có trách nhiệm rõ.

## Kết luận

MVC và MVP cùng phân tách Model khỏi phần trình bày, nhưng đặt trách nhiệm điều phối ở những nơi khác nhau. MVC dùng Controller để tiếp nhận request/sự kiện và chọn response hoặc View; MVP dùng Presenter để điều phối tương tác của màn hình và cập nhật View qua interface. MVC thường phù hợp với luồng web request/response, còn MVP hữu ích khi logic tương tác của màn hình phức tạp và cần kiểm thử độc lập. Dù chọn mẫu nào, quy tắc nghiệp vụ và kiểm tra quyền vẫn phải nằm ở Model/use case phía server, còn View chỉ trình bày dữ liệu theo hợp đồng rõ ràng.
