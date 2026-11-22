# Giữ thống nhất lựa chọn và trạng thái giữa nhiều View

Trong một ứng dụng MVC có nhiều View, cùng một đối tượng hoặc cùng một ngữ cảnh tương tác có thể xuất hiện ở nhiều nơi. Ví dụ, màn hình quản lý sản phẩm có danh sách ở bên trái, thông tin chi tiết ở bên phải và một thanh tóm tắt ở phía trên. Khi người dùng chọn một sản phẩm trong danh sách, cả khung chi tiết và thanh tóm tắt cần phản ánh đúng sản phẩm đó.

Để giữ các View thống nhất, ứng dụng cần xác định trạng thái nào được chia sẻ, thành phần nào có quyền thay đổi trạng thái và cách thông báo thay đổi đến những View liên quan. Nếu mỗi View tự giữ lựa chọn riêng, giao diện dễ rơi vào tình trạng danh sách đánh dấu sản phẩm A nhưng khung chi tiết lại hiển thị sản phẩm B.

## 1. Hiểu trạng thái tương tác được chia sẻ

Một màn hình có thể có nhiều loại trạng thái. Không phải tất cả đều cần chia sẻ giữa các View.

| Loại trạng thái | Ví dụ | Phạm vi phù hợp |
|---|---|---|
| Trạng thái nghiệp vụ | Trạng thái đơn hàng, giá sản phẩm, số lượng tồn kho | Model nghiệp vụ và nguồn lưu trữ có thẩm quyền |
| Trạng thái tương tác được chia sẻ | ID sản phẩm đang chọn, tập mục được chọn, bộ lọc chung, trang hiện tại | Model hoặc store dành cho ngữ cảnh giao diện |
| Trạng thái cục bộ của View | Vị trí con trỏ, trạng thái hover, nội dung đang gõ chưa gửi, trạng thái mở của một tooltip | View đang sở hữu tương tác đó |

Ví dụ, khi chọn sản phẩm có ID 42, ứng dụng có thể lưu selectedProductId = 42 trong một SelectionModel. Danh sách dùng ID này để tô sáng dòng đang chọn; khung chi tiết dùng nó để tải và hiển thị sản phẩm; thanh tóm tắt dùng nó để hiển thị tên và trạng thái.

Lựa chọn đang xem không nhất thiết là thay đổi nghiệp vụ. Chọn một đơn hàng để xem chi tiết không làm thay đổi trạng thái đơn hàng. Vì vậy, nên phân biệt Model nghiệp vụ với trạng thái tương tác của giao diện. Chúng có thể liên kết với nhau, nhưng có vòng đời và quy tắc cập nhật khác nhau.

## 2. Một nguồn có thẩm quyền cho trạng thái được chia sẻ

Nguyên tắc quan trọng là mỗi trạng thái tương tác được chia sẻ cần có một nguồn có thẩm quyền trong phạm vi tương tác đó. Các View đọc cùng trạng thái và gửi ý định thay đổi đến thành phần quản lý trạng thái.

~~~mermaid
flowchart TD
    U[Người dùng chọn sản phẩm] --> V1[View danh sách]
    V1 --> C[Controller]
    C --> S[Selection Model]
    S -->|selectedProductId = 42| E[Thông báo thay đổi]
    E --> V1
    E --> V2[View chi tiết]
    E --> V3[View tóm tắt]
    V1 -->|Đánh dấu dòng 42| R1[Giao diện danh sách]
    V2 -->|Tải chi tiết 42| R2[Giao diện chi tiết]
    V3 -->|Hiển thị sản phẩm 42| R3[Thanh tóm tắt]
~~~

Luồng này có bốn bước:

1. Người dùng thao tác trên một View.
2. View chuyển ý định đến Controller.
3. Controller yêu cầu SelectionModel cập nhật lựa chọn.
4. SelectionModel thông báo trạng thái mới cho các View đã đăng ký.

Mỗi View chỉ trình bày phần dữ liệu liên quan. View danh sách không cần gọi trực tiếp View chi tiết để yêu cầu đổi nội dung. View chi tiết cũng không cần biết người dùng đã nhấp vào nút nào trong danh sách.

Nếu nhiều View cùng tự ghi vào các biến selectedId riêng, ứng dụng sẽ có nhiều nguồn sự thật. Một SelectionModel hoặc store chung giúp tập trung việc thay đổi và giảm nguy cơ các View tự mâu thuẫn.

## 3. Thiết kế trạng thái lựa chọn

Trước khi triển khai, cần xác định rõ ngữ nghĩa của lựa chọn.

### 3.1. Lựa chọn đơn

Lựa chọn đơn lưu một ID hoặc giá trị null khi chưa có mục nào được chọn:

~~~java
Long selectedProductId;
~~~

Đây là cách phù hợp với màn hình master–detail, nơi người dùng chọn một hàng để xem thông tin chi tiết.

### 3.2. Lựa chọn nhiều mục

Lựa chọn nhiều mục lưu một tập ID:

~~~java
Set<Long> selectedProductIds;
~~~

Tập hợp giúp tránh ID trùng lặp. Nếu thứ tự chọn có ý nghĩa, chẳng hạn thứ tự ưu tiên hoặc thứ tự thao tác, hãy dùng cấu trúc có thứ tự thay vì một Set không cam kết thứ tự.

### 3.3. Phạm vi của lựa chọn

Một lựa chọn cần gắn với ngữ cảnh phù hợp. Ví dụ, selectedProductId trong một cửa sổ quản lý kho không nhất thiết phải đồng nhất với selectedProductId trong cửa sổ bán hàng. Hãy xác định lựa chọn được chia sẻ trong:

- Một màn hình hoặc một nhóm View cùng phục vụ một use case.
- Một tab hoặc một cửa sổ.
- Một phiên người dùng.
- Nhiều thiết bị hoặc nhiều người dùng cùng theo dõi một tài nguyên.

Không nên dùng một biến toàn cục duy nhất cho tất cả người dùng web. Trạng thái lựa chọn của từng người dùng hoặc từng phiên phải được cô lập theo đúng phạm vi.

### 3.4. Lựa chọn và bộ lọc

Nếu người dùng chọn sản phẩm 42 rồi thay đổi bộ lọc khiến sản phẩm 42 không còn trong danh sách, ứng dụng cần có chính sách rõ ràng:

- Xóa lựa chọn nếu chỉ cho phép chọn mục đang hiển thị.
- Giữ lựa chọn nếu khung chi tiết vẫn cần hiển thị sản phẩm hiện tại dù danh sách đã lọc.
- Chuyển sang mục đầu tiên còn hợp lệ nếu quy tắc trải nghiệm yêu cầu luôn có một mục được chọn.

Không nên để mỗi View tự suy luận chính sách này. Controller hoặc thành phần quản lý trạng thái cần áp dụng một quy tắc nhất quán.

## 4. Java: SelectionModel thông báo lựa chọn mới

Ví dụ dưới đây dùng Java PropertyChangeSupport để phát thông báo khi ID được chọn thay đổi. Ví dụ giả định các thao tác được thực hiện tuần tự trên cùng một luồng giao diện.

~~~java
import java.beans.PropertyChangeListener;
import java.beans.PropertyChangeSupport;
import java.util.Objects;

public final class SelectionModel {
    private final PropertyChangeSupport changes =
            new PropertyChangeSupport(this);

    private Long selectedProductId;

    public Long getSelectedProductId() {
        return selectedProductId;
    }

    public void addSelectionListener(PropertyChangeListener listener) {
        changes.addPropertyChangeListener("selectedProductId", listener);
    }

    public void removeSelectionListener(PropertyChangeListener listener) {
        changes.removePropertyChangeListener("selectedProductId", listener);
    }

    public void select(Long productId) {
        Long previous = selectedProductId;
        if (Objects.equals(previous, productId)) {
            return;
        }

        selectedProductId = productId;
        changes.firePropertyChange(
                "selectedProductId",
                previous,
                productId
        );
    }
}
~~~

Phương thức select là điểm thay đổi trạng thái lựa chọn. Khi ID mới giống ID hiện tại, Model không phát thông báo thừa. Khi ID thay đổi, Model cập nhật trạng thái rồi gửi giá trị cũ và mới đến các listener.

Giá trị null biểu thị chưa chọn mục nào. View cần xử lý trường hợp này để xóa phần chi tiết cũ hoặc hiển thị trạng thái hướng dẫn chọn một mục.

## 5. Nhiều View cùng quan sát một lựa chọn

### 5.1. View danh sách phản ánh lựa chọn

View danh sách đăng ký listener để biết ID nào cần được đánh dấu:

~~~java
import java.beans.PropertyChangeEvent;
import java.beans.PropertyChangeListener;

public final class ProductListView
        implements PropertyChangeListener, AutoCloseable {
    private final SelectionModel selection;
    private final ProductSelectionController controller;

    public ProductListView(
            SelectionModel selection,
            ProductSelectionController controller
    ) {
        this.selection = selection;
        this.controller = controller;
        selection.addSelectionListener(this);
        highlight(selection.getSelectedProductId());
    }

    public void userSelectedProduct(long productId) {
        controller.selectProduct(productId);
    }

    @Override
    public void propertyChange(PropertyChangeEvent event) {
        highlight((Long) event.getNewValue());
    }

    private void highlight(Long productId) {
        System.out.println("Đánh dấu sản phẩm: " + productId);
    }

    @Override
    public void close() {
        selection.removeSelectionListener(this);
    }
}
~~~

View nhận cả SelectionModel để quan sát thay đổi và Controller để gửi ý định do người dùng tạo ra. Nhờ vậy, chiều cập nhật và chiều tương tác có trách nhiệm riêng: Controller thay đổi trạng thái, còn listener chỉ phản ánh trạng thái đã được công bố.

### 5.2. View chi tiết phản ánh cùng lựa chọn

View chi tiết cũng đăng ký với cùng SelectionModel:

~~~java
import java.beans.PropertyChangeEvent;
import java.beans.PropertyChangeListener;

public final class ProductDetailView
        implements PropertyChangeListener, AutoCloseable {
    private final SelectionModel selection;
    private final ProductQueryService products;

    public ProductDetailView(
            SelectionModel selection,
            ProductQueryService products
    ) {
        this.selection = selection;
        this.products = products;
        selection.addSelectionListener(this);
        showProduct(selection.getSelectedProductId());
    }

    @Override
    public void propertyChange(PropertyChangeEvent event) {
        showProduct((Long) event.getNewValue());
    }

    private void showProduct(Long productId) {
        if (productId == null) {
            System.out.println("Hãy chọn một sản phẩm");
            return;
        }

        ProductDetails product = products.findDetails(productId);
        System.out.println("Chi tiết: " + product.name());
    }

    @Override
    public void close() {
        selection.removeSelectionListener(this);
    }
}
~~~

ProductQueryService và ProductDetails là kiểu dữ liệu minh họa cần được định nghĩa trong ứng dụng. Khi lựa chọn thay đổi, View chi tiết tải dữ liệu tương ứng và trình bày. Trong ứng dụng thực tế, việc tải dữ liệu có thể bất đồng bộ; phần xử lý kết quả cần tránh áp dụng phản hồi cũ sau khi người dùng đã chọn một sản phẩm khác.

### 5.3. Controller thay đổi lựa chọn

Controller nhận ID từ tương tác và chuyển yêu cầu đến SelectionModel:

~~~java
public final class ProductSelectionController {
    private final SelectionModel selection;

    public ProductSelectionController(SelectionModel selection) {
        this.selection = selection;
    }

    public void selectProduct(long productId) {
        // Có thể kiểm tra mục có thuộc phạm vi danh sách hiện tại hay không.
        selection.select(productId);
    }

    public void clearSelection() {
        selection.select(null);
    }
}
~~~

Trong hệ thống thực tế, truy vấn chi tiết vẫn phải xác thực người dùng và kiểm tra quyền truy cập sản phẩm. Một ID được chọn từ giao diện không chứng minh người dùng có quyền xem hoặc cập nhật tài nguyên đó.

## 6. Tránh vòng lặp cập nhật giữa các View

Một lỗi dễ gặp là View nhận thông báo rồi lại phát một thao tác thay đổi trạng thái, khiến các View liên tục kích hoạt lẫn nhau.

Ví dụ về vòng lặp:

1. View danh sách nhận lựa chọn sản phẩm 42.
2. View danh sách cập nhật widget chọn dòng.
3. Widget phát sự kiện selectionChanged dù thay đổi đến từ chương trình.
4. View gọi Controller để chọn lại sản phẩm 42.
5. SelectionModel phát thông báo lần nữa.

Để tránh vòng lặp:

- Chỉ chuyển thao tác của người dùng thành command; cập nhật giao diện do chương trình thực hiện không được coi là thao tác mới.
- So sánh giá trị cũ và mới, không phát thông báo nếu trạng thái không đổi.
- Khi framework hỗ trợ, dùng cơ chế cập nhật widget không phát sự kiện hoặc tạm ngắt listener trong lúc render.
- Không để Observer vừa trình bày dữ liệu vừa điều phối một thay đổi nghiệp vụ khác nếu không có chủ đích rõ ràng.

~~~mermaid
flowchart TD
    U[Người dùng chọn mục] --> C[Controller]
    C --> S[SelectionModel]
    S --> E[Thông báo lựa chọn]
    E --> V1[View danh sách]
    E --> V2[View chi tiết]
    V1 --> R[Render widget, không phát command mới]
    V2 --> R2[Render dữ liệu, không phát command mới]
~~~

Phân biệt rõ hai chiều:

- **Command:** biểu đạt ý định thay đổi trạng thái do người dùng hoặc hệ thống yêu cầu.
- **Notification:** thông báo rằng trạng thái đã thay đổi để View cập nhật.

View nhận notification nên cập nhật cách hiển thị. Nếu cập nhật widget có thể kích hoạt callback của framework, callback cần nhận biết đây là thay đổi do render và bỏ qua việc phát command tương ứng.

## 7. Đồng bộ lựa chọn nhiều mục

Với giao diện cho phép chọn nhiều sản phẩm, SelectionModel có thể quản lý một tập ID bất biến:

~~~java
import java.beans.PropertyChangeSupport;
import java.util.Set;

public final class MultiSelectionModel {
    private final PropertyChangeSupport changes =
            new PropertyChangeSupport(this);

    private Set<Long> selectedIds = Set.of();

    public Set<Long> getSelectedIds() {
        return selectedIds;
    }

    public void setSelectedIds(Set<Long> ids) {
        Set<Long> next = Set.copyOf(ids);
        Set<Long> previous = selectedIds;

        if (previous.equals(next)) {
            return;
        }

        selectedIds = next;
        changes.firePropertyChange("selectedIds", previous, next);
    }
}
~~~

Trong ví dụ, tập ID được sao chép để bên gọi không thể thay đổi trạng thái nội bộ sau khi gửi. Nếu thứ tự chọn cần được giữ như một phần hợp đồng, hãy dùng một collection bất biến có bảo toàn thứ tự và kiểm thử rõ hành vi đó; Set.copyOf không cam kết thứ tự duyệt.

Các View có thể dùng cùng tập ID để đánh dấu hàng, cập nhật số mục đã chọn và bật hoặc tắt các thao tác hàng loạt. Ví dụ, nút xóa hàng loạt chỉ nên bật khi tập lựa chọn không rỗng. Khi người dùng bỏ chọn một mục, Controller tạo tập mới và gửi đến SelectionModel.

## 8. Khi danh sách hoặc dữ liệu thay đổi

Lựa chọn có thể trở nên không hợp lệ khi dữ liệu nguồn thay đổi. Ví dụ:

- Sản phẩm đang chọn bị xóa.
- Người dùng đổi bộ lọc và mục không còn thuộc tập kết quả.
- Quyền truy cập bị thu hồi.
- Trang hiện tại thay đổi do phân trang.
- Một lựa chọn nhiều mục chứa ID không còn tồn tại.

SelectionModel hoặc lớp điều phối cần nhận biết những thay đổi này và áp dụng chính sách đã định nghĩa. Một số lựa chọn phổ biến:

| Tình huống | Chính sách có thể áp dụng |
|---|---|
| Mục bị xóa | Xóa ID khỏi lựa chọn; hiển thị trạng thái không có mục được chọn |
| Mục bị ẩn bởi bộ lọc | Giữ lựa chọn và tiếp tục hiển thị chi tiết, hoặc xóa theo quy tắc màn hình |
| Người dùng mất quyền | Xóa lựa chọn và không tải dữ liệu chi tiết nữa |
| Trang kết quả thay đổi | Giữ lựa chọn toàn cục hoặc chỉ giữ lựa chọn thuộc trang hiện tại |
| Một mục trong tập nhiều lựa chọn bị xóa | Loại ID không hợp lệ khỏi tập và thông báo trạng thái mới |

Không nên để một View tiếp tục hiển thị dữ liệu đã mất quyền truy cập chỉ vì ID vẫn còn trong SelectionModel. Khi nhận thông báo lỗi truy cập, View cần xóa nội dung nhạy cảm và trạng thái lựa chọn tương ứng.

## 9. Tải dữ liệu bất đồng bộ và phản hồi đến sai thứ tự

Khi View chi tiết tải dữ liệu qua mạng, người dùng có thể chọn sản phẩm 42 rồi nhanh chóng chọn sản phẩm 57. Request cho sản phẩm 42 có thể hoàn tất sau request cho sản phẩm 57. Nếu View áp dụng mọi phản hồi theo thứ tự hoàn tất, nó có thể hiển thị chi tiết 42 dù lựa chọn hiện tại là 57.

Có thể xử lý bằng cách gắn ID lựa chọn hoặc số phiên bản vào mỗi lần tải:

1. Khi bắt đầu tải chi tiết, ghi lại selectedProductId hiện tại.
2. Khi response đến, so sánh ID trong response với lựa chọn hiện tại.
3. Chỉ áp dụng response nếu nó vẫn tương ứng với lựa chọn mới nhất.
4. Bỏ qua response cũ hoặc hủy request cũ nếu công cụ mạng hỗ trợ.

~~~java
import java.util.concurrent.atomic.AtomicLong;

// Các thành viên sau nằm bên trong View chi tiết.
private final AtomicLong requestSequence = new AtomicLong();

private void loadDetails(Long requestedId) {
    long requestId = requestSequence.incrementAndGet();
    if (requestedId == null) {
        renderEmpty();
        return;
    }

    productApi.fetchDetails(requestedId).thenAccept(details -> {
        uiExecutor.execute(() -> {
            if (requestId == requestSequence.get()
                    && requestedId.equals(selection.getSelectedProductId())) {
                render(details);
            }
        });
    });
}
~~~

Đoạn mã giả định có ProductApi trả về CompletionStage hoặc một kiểu future tương đương, cùng uiExecutor để đưa thao tác render về UI thread của framework. requestSequence ngăn phản hồi của một lần tải cũ ghi đè kết quả của lần tải mới, kể cả khi người dùng chọn lại cùng một ID.

## 10. Giữ lựa chọn trong ứng dụng web

Trong ứng dụng web, cách lưu trạng thái phụ thuộc vào phạm vi cần chia sẻ.

### 10.1. URL cho lựa chọn có thể chia sẻ

Nếu lựa chọn là một phần của ngữ cảnh điều hướng, có thể biểu diễn nó trong URL:

~~~http
GET /products?selected=42
~~~

Ưu điểm là người dùng có thể tải lại trang, đánh dấu trang hoặc chia sẻ liên kết và vẫn mở đúng sản phẩm. Controller đọc query parameter, kiểm tra định dạng, gọi service xác minh quyền truy cập rồi dựng View tương ứng.

Không nên đưa dữ liệu nhạy cảm hoặc quyền hạn vào URL. ID trên URL vẫn là đầu vào không đáng tin và phải được kiểm tra ở máy chủ.

### 10.2. Session cho trạng thái riêng của người dùng

Nếu lựa chọn cần tồn tại qua nhiều request nhưng không cần chia sẻ bằng liên kết, ứng dụng có thể lưu nó trong session hoặc một store phía máy chủ gắn với người dùng. Cần giới hạn dữ liệu lưu, thời gian sống và phạm vi session. Không dùng một biến singleton mutable để giữ lựa chọn cho tất cả người dùng.

### 10.3. SPA dùng store phía client

Trong SPA, một store chung có thể giữ selectedProductId. Các component đăng ký theo dõi phần state liên quan và render lại khi giá trị thay đổi. Nếu lựa chọn cần được khôi phục sau khi refresh, có thể đồng bộ store với URL hoặc cơ chế lưu trạng thái phù hợp.

### 10.4. Nhiều tab hoặc nhiều trình duyệt

Trạng thái trong bộ nhớ của một tab không tự đồng bộ sang tab khác. Nếu cần đồng bộ nhiều tab trên cùng trình duyệt, có thể dùng URL, storage event hoặc BroadcastChannel. Nếu cần đồng bộ nhiều thiết bị hoặc người dùng, cần một dịch vụ phía máy chủ và kênh thông báo có xác thực, phân quyền.

Hãy xác định rõ liệu các tab có thực sự cần cùng một lựa chọn hay mỗi tab nên giữ ngữ cảnh riêng. Chia sẻ mọi lựa chọn giữa các tab có thể khiến thao tác ở một tab làm thay đổi bất ngờ màn hình đang làm việc ở tab khác.

## 11. Phân quyền và quyền riêng tư của trạng thái lựa chọn

Lựa chọn là dữ liệu đầu vào, không phải bằng chứng về quyền. Người dùng có thể sửa URL, gửi ID khác trong request hoặc tự tạo thông báo client. Vì vậy:

- Xác thực người dùng trước khi tải dữ liệu chi tiết.
- Kiểm tra quyền trên từng tài nguyên, không chỉ kiểm tra quyền truy cập màn hình.
- Không gửi dữ liệu nhạy cảm đến View chỉ vì ID đã được chọn.
- Khi quyền bị thu hồi, làm sạch dữ liệu đang hiển thị và cache có liên quan.
- Với lựa chọn nhiều mục, kiểm tra quyền cho từng mục trước khi thực hiện thao tác hàng loạt.

Nếu hai người dùng cùng làm việc trên một tài nguyên, lựa chọn của người này thường không nên tự động thay đổi lựa chọn của người kia. Chỉ chia sẻ lựa chọn khi đó là một tính năng cộng tác có chủ đích và có quy tắc hiển thị rõ ràng.

## 12. Kiểm thử sự thống nhất giữa nhiều View

Kiểm thử nên tập trung vào trạng thái được chia sẻ và cách mỗi View phản ánh nó.

1. **Lựa chọn đơn:** chọn một ID và xác nhận danh sách, chi tiết và tóm tắt cùng phản ánh ID đó.
2. **Bỏ chọn:** đặt lựa chọn về null và xác nhận View chi tiết xóa dữ liệu cũ.
3. **Không thay đổi:** chọn lại cùng ID không phát thông báo thừa.
4. **Lựa chọn nhiều mục:** thêm, bỏ và thay tập ID; xác nhận mọi View dùng cùng tập hợp.
5. **Vòng lặp sự kiện:** cập nhật widget từ notification không tạo command mới ngoài ý muốn.
6. **Vòng đời:** View đã đóng không còn nhận thông báo.
7. **Dữ liệu không còn hợp lệ:** xóa mục hoặc thu hồi quyền thì lựa chọn được làm sạch theo chính sách.
8. **Phản hồi bất đồng bộ:** response của lựa chọn cũ không ghi đè chi tiết của lựa chọn mới.
9. **Phạm vi người dùng:** lựa chọn của một session không xuất hiện trong session khác.
10. **Điều hướng:** nếu URL là nguồn khôi phục lựa chọn, tải lại hoặc mở liên kết phải khôi phục đúng ngữ cảnh.

Với Java, có thể kiểm thử SelectionModel độc lập bằng listener giả để xác nhận giá trị cũ/mới và số lần phát sự kiện. Kiểm thử View có thể dùng mock service để xác nhận View chi tiết tải đúng ID. Với Spring MVC, MockMvc có thể kiểm tra query parameter và phản hồi; kiểm thử store phía client cần xác nhận các component cùng render từ một state.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Mỗi View tự lưu selectedId riêng | Các View hiển thị những mục khác nhau | Dùng một SelectionModel hoặc store chung trong đúng phạm vi |
| Dùng trạng thái lựa chọn thay cho trạng thái nghiệp vụ | Nhầm việc đang xem với việc thay đổi dữ liệu | Tách UI state khỏi domain state |
| View cập nhật widget rồi phát lại command | Vòng lặp notification và callback | Phân biệt thao tác người dùng với render |
| Không xử lý lựa chọn null | Chi tiết cũ vẫn hiển thị sau khi bỏ chọn | Định nghĩa trạng thái rỗng cho mọi View |
| Không xử lý mục bị xóa hoặc mất quyền | View tiếp tục hiển thị dữ liệu lỗi thời hoặc nhạy cảm | Làm sạch lựa chọn và dữ liệu theo chính sách |
| Response bất đồng bộ cũ ghi đè response mới | Chi tiết không khớp lựa chọn hiện tại | Kiểm tra ID hoặc version trước khi render |
| Dùng biến singleton cho lựa chọn của mọi người dùng | Rò rỉ hoặc trộn trạng thái session | Phân vùng state theo người dùng và ngữ cảnh |
| Chia sẻ lựa chọn qua mọi tab mà không có yêu cầu | Thao tác ở tab này làm đổi tab khác ngoài dự kiến | Xác định rõ phạm vi chia sẻ |

## 14. Checklist thiết kế

Trước khi hoàn thành một màn hình có nhiều View tương tác, hãy kiểm tra:

- Trạng thái nào là nghiệp vụ, trạng thái nào chỉ phục vụ tương tác?
- Lựa chọn được chia sẻ trong phạm vi nào?
- Có một nguồn có thẩm quyền cho mỗi trạng thái được chia sẻ không?
- Các View có đăng ký và hủy đăng ký đúng vòng đời không?
- Notification có làm View render mà không phát lại command không?
- Trạng thái không có lựa chọn và lựa chọn không còn hợp lệ được xử lý ra sao?
- Phản hồi bất đồng bộ cũ có bị ngăn không cho ghi đè lựa chọn mới?
- ID và dữ liệu chi tiết có được kiểm tra quyền ở máy chủ không?
- URL, session hoặc store có được chọn theo nhu cầu khôi phục trạng thái không?
- Kiểm thử có xác nhận mọi View phản ánh cùng lựa chọn sau mỗi thao tác không?

Giữ thống nhất lựa chọn giữa nhiều View là việc quản lý một trạng thái tương tác dùng chung trong một phạm vi xác định. Khi Controller điều phối thay đổi qua một nguồn có thẩm quyền và các View chỉ phản ánh trạng thái nhận được, giao diện có thể gồm nhiều vùng độc lập mà vẫn trình bày cùng một ngữ cảnh. Việc phân biệt trạng thái giao diện với trạng thái nghiệp vụ, xử lý vòng đời và kiểm tra dữ liệu bất đồng bộ giúp sự thống nhất đó bền vững hơn.
