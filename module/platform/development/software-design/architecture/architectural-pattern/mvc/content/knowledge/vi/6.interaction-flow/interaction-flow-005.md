# Đồng bộ nhiều View cùng phản ánh một Model

Trong kiến trúc Model–View–Controller (MVC), một Model có thể được trình bày bởi nhiều View. Ví dụ, cùng một giỏ hàng có thể xuất hiện ở trang chi tiết giỏ hàng, biểu tượng số lượng trên thanh điều hướng và phần tóm tắt đơn hàng. Khi người dùng thêm hoặc xóa sản phẩm, các View cần phản ánh cùng một trạng thái nghiệp vụ để không hiển thị những kết quả mâu thuẫn.

Đồng bộ nhiều View không có nghĩa là mọi View phải có cùng bố cục hoặc cùng một cấu trúc dữ liệu. Mỗi View có thể chọn một phần thông tin và trình bày theo mục đích riêng. Điều cần thống nhất là nguồn trạng thái có thẩm quyền, thời điểm các View nhận biết thay đổi và cách xử lý khi thông báo bị chậm hoặc thất bại.

## 1. Vấn đề khi nhiều View cùng hiển thị một Model

Hãy xem một ứng dụng bán hàng có ba khu vực:

- Trang giỏ hàng hiển thị từng sản phẩm, số lượng và tổng tiền.
- Biểu tượng giỏ hàng trên thanh điều hướng hiển thị tổng số mặt hàng.
- Khung tóm tắt thanh toán hiển thị tạm tính và phí giao hàng.

Ba khu vực này cùng phản ánh một giỏ hàng. Khi người dùng tăng số lượng một sản phẩm từ một lên hai, cả ba khu vực có thể cần cập nhật. Nếu mỗi View giữ một bản sao trạng thái riêng, chúng có thể lệch nhau:

- Trang giỏ hàng hiển thị hai sản phẩm nhưng biểu tượng vẫn hiển thị một.
- Tổng tiền đã được tính lại nhưng khung thanh toán vẫn dùng giá cũ.
- Một View đã xóa sản phẩm trong khi View khác vẫn cho phép thanh toán sản phẩm đó.

Nguyên nhân thường gặp là mỗi View tự quản lý dữ liệu nghiệp vụ hoặc tự thực hiện phép tính giống nhau. Khi có nhiều bản sao có thể chỉnh sửa, mỗi lần cập nhật đều phải đồng bộ tất cả bản sao. Càng nhiều View, nguy cơ sai khác càng tăng.

Thiết kế MVC nên giữ một nguồn trạng thái nghiệp vụ có thẩm quyền. Các View nhận dữ liệu từ Model hoặc từ những projection được tạo ra từ Model đó.

## 2. Phân biệt Model, trạng thái hiển thị và View

Ba khái niệm sau cần được phân biệt:

| Thành phần | Trách nhiệm | Ví dụ trong giỏ hàng |
|---|---|---|
| Model nghiệp vụ | Giữ trạng thái và bảo vệ quy tắc nghiệp vụ | Các dòng hàng, số lượng hợp lệ, cách tính tổng |
| ViewModel hoặc projection | Chọn và định dạng dữ liệu cho một mục đích hiển thị | Số lượng trên biểu tượng; danh sách dòng hàng; tổng tiền |
| View | Trình bày dữ liệu và tiếp nhận tương tác | Trang giỏ hàng, thanh điều hướng, khung thanh toán |

Một Model có thể cung cấp dữ liệu cho nhiều projection. View biểu tượng chỉ cần tổng số lượng; View chi tiết cần danh sách dòng hàng; View thanh toán cần các khoản tiền. Những projection này có thể khác nhau nhưng phải được tính từ cùng một trạng thái hợp lệ.

Không nên biến ViewModel thành một bản sao có quyền sửa độc lập trạng thái nghiệp vụ. ViewModel có thể được tạo mới sau mỗi lần cập nhật hoặc giữ như cache trình bày, nhưng phải có cách làm mới rõ ràng khi nguồn dữ liệu thay đổi.

## 3. Luồng đồng bộ trong MVC

Trong mô hình MVC có Model sống trong cùng tiến trình, Controller tiếp nhận hành động của người dùng và yêu cầu Model thay đổi. Khi thay đổi hoàn tất, Model thông báo cho các View đang quan sát. Mỗi View đọc trạng thái mới hoặc nhận một snapshot để cập nhật phần trình bày.

~~~mermaid
flowchart TD
    U[Người dùng thay đổi số lượng] --> C[Controller]
    C -->|Command tăng số lượng| M[Cart Model]
    M -->|Cập nhật trạng thái hợp lệ| S[Snapshot mới]
    S --> E[Thông báo thay đổi]
    E --> V1[View danh sách giỏ hàng]
    E --> V2[View biểu tượng giỏ hàng]
    E --> V3[View tóm tắt thanh toán]
    V1 -->|Render danh sách| U1[Phần giao diện 1]
    V2 -->|Render số lượng| U2[Phần giao diện 2]
    V3 -->|Render tổng tiền| U3[Phần giao diện 3]
~~~

Trình tự điển hình:

1. Người dùng thao tác trên một View.
2. View gửi ý định đến Controller, chẳng hạn tăng số lượng sản phẩm.
3. Controller chuyển ý định thành lời gọi hoặc command cho Model/use case.
4. Model kiểm tra quy tắc và áp dụng thay đổi.
5. Model công bố trạng thái mới hoặc thông báo thay đổi.
6. Các View đang quan tâm cập nhật dữ liệu hiển thị.

Controller không cần biết tất cả View đang quan sát. Khi thêm một View mới, View đó đăng ký nhận thông báo hoặc lấy snapshot hiện tại từ Model. Logic nghiệp vụ không cần được nhân bản cho View mới.

## 4. Hai cách để View nhận trạng thái mới: Pull và Push

Khi Model thay đổi, View có thể nhận biết theo hai cách phổ biến.

| Cách | Cơ chế | Phù hợp khi |
|---|---|---|
| Pull | Model báo có thay đổi; View đọc snapshot mới từ Model | View cần trạng thái đầy đủ hoặc chỉ một tín hiệu làm mới |
| Push | Model gửi dữ liệu thay đổi hoặc snapshot mới đến View | View có thể cập nhật trực tiếp từ payload nhỏ, rõ ràng |

### 4.1. Pull: View đọc lại Model

Thông báo chỉ cho biết trạng thái đã thay đổi. Khi nhận thông báo, View gọi một phương thức đọc như getSnapshot() rồi dựng lại phần hiển thị.

Ưu điểm:

- View luôn lấy dữ liệu từ nguồn có thẩm quyền.
- Thông báo đơn giản, ít phụ thuộc vào cấu trúc dữ liệu.
- Dễ làm mới toàn bộ View khi có nhiều thuộc tính liên quan.

Hạn chế:

- Nhiều View có thể cùng đọc lại dữ liệu sau một thay đổi.
- Nếu việc đọc tốn kém, có thể phát sinh truy vấn hoặc tính toán lặp lại.
- Nếu Model đã đổi lần nữa trước khi View đọc, View nhận trạng thái mới nhất chứ không nhất thiết biết từng thay đổi trung gian.

### 4.2. Push: Model gửi snapshot hoặc dữ liệu thay đổi

Model có thể gửi snapshot mới hoặc một sự kiện có dữ liệu như số lượng cũ và mới. View cập nhật dựa trên dữ liệu nhận được mà không cần truy vấn lại toàn bộ Model.

Ưu điểm:

- Giảm thao tác đọc lại khi payload đã chứa đủ dữ liệu.
- Có thể cập nhật đúng phần giao diện bị ảnh hưởng.
- Hữu ích khi cần thể hiện thay đổi cụ thể, ví dụ mặt hàng nào vừa được thêm.

Hạn chế:

- Payload trở thành hợp đồng giữa Model và Observer.
- View có thể xử lý sai nếu bỏ lỡ một sự kiện hoặc nhận sự kiện sai thứ tự.
- Gửi quá nhiều dữ liệu làm tăng phụ thuộc và có thể tiết lộ trường không cần thiết.

Trong nhiều ứng dụng, cách kết hợp phù hợp là gửi một snapshot bất biến cho View cần cập nhật ngay, đồng thời cung cấp thao tác đọc lại để khôi phục khi View mất đồng bộ.

## 5. Cập nhật trạng thái theo một đơn vị nhất quán

Một thay đổi nghiệp vụ thường ảnh hưởng nhiều thuộc tính. Ví dụ, thêm một mặt hàng có thể làm thay đổi danh sách dòng hàng, số lượng tổng, tạm tính và phí giao hàng. Nếu Model phát thông báo sau từng phép gán riêng lẻ, View có thể quan sát trạng thái trung gian:

1. Danh sách đã có mặt hàng mới.
2. Tổng số lượng chưa được cập nhật.
3. Tổng tiền chưa được tính lại.

Trong khoảng thời gian đó, các View có thể hiển thị một trạng thái không nhất quán.

Một cách thiết kế tốt là tính toán trạng thái mới hoàn chỉnh, thay thế trạng thái hiện tại bằng một snapshot nhất quán rồi mới phát một thông báo. Những View nhận cùng snapshot sẽ cùng phản ánh một phiên bản dữ liệu.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant C as Controller
    participant M as Model
    participant V1 as View danh sách
    participant V2 as View biểu tượng
    participant V3 as View thanh toán
    User->>C: Tăng số lượng sản phẩm
    C->>M: changeQuantity(productId, 2)
    M->>M: Kiểm tra quy tắc và tính snapshot mới
    M->>M: Thay thế trạng thái hiện tại
    M-->>V1: Snapshot phiên bản 8
    M-->>V2: Snapshot phiên bản 8
    M-->>V3: Snapshot phiên bản 8
    V1->>V1: Cập nhật dòng hàng
    V2->>V2: Cập nhật tổng số lượng
    V3->>V3: Cập nhật tạm tính
    C-->>User: Trả kết quả thao tác
~~~

Snapshot có thể là một đối tượng bất biến chứa các giá trị đã được tính toán. Bất biến giúp Observer không vô tình sửa dữ liệu dùng chung. Nếu View cần dữ liệu trình bày khác nhau, mỗi View có thể ánh xạ snapshot thành projection riêng.

## 6. Ví dụ Java: một Cart Model, nhiều View

Ví dụ sau minh họa một Model giỏ hàng phát thông báo khi snapshot thay đổi. Mã được rút gọn để tập trung vào quan hệ giữa Model và nhiều View; ví dụ giả định các thao tác diễn ra trên cùng một luồng giao diện.

Trong dự án Java, đặt mỗi kiểu public trong một file tương ứng; các đoạn mã dưới đây được tách theo vai trò để dễ theo dõi.

### 6.1. Định nghĩa snapshot bất biến

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

public record CartLine(
        String productName,
        int quantity,
        BigDecimal unitPrice
) {
    public CartLine {
        if (quantity < 1) {
            throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
        }
        Objects.requireNonNull(unitPrice, "unitPrice");
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Đơn giá không hợp lệ");
        }
    }

    public BigDecimal lineTotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}

public record CartSnapshot(List<CartLine> lines) {
    public CartSnapshot {
        lines = List.copyOf(lines);
    }

    public int itemCount() {
        return lines.stream().mapToInt(CartLine::quantity).sum();
    }

    public BigDecimal total() {
        return lines.stream()
                .map(CartLine::lineTotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }
}
~~~

CartSnapshot chứa một danh sách bất biến. Tổng số lượng và tổng tiền được suy ra từ cùng danh sách, nhờ đó không phải lưu thêm các bản sao có thể bị cập nhật lệch nhau.

### 6.2. Model quản lý trạng thái và phát thông báo

~~~java
import java.beans.PropertyChangeListener;
import java.beans.PropertyChangeSupport;
import java.util.ArrayList;
import java.util.List;

public final class CartModel {
    private final PropertyChangeSupport changes =
            new PropertyChangeSupport(this);

    private CartSnapshot state = new CartSnapshot(List.of());

    public CartSnapshot snapshot() {
        return state;
    }

    public void addListener(PropertyChangeListener listener) {
        changes.addPropertyChangeListener("state", listener);
    }

    public void removeListener(PropertyChangeListener listener) {
        changes.removePropertyChangeListener("state", listener);
    }

    public void addLine(CartLine newLine) {
        CartSnapshot previous = state;
        List<CartLine> nextLines = new ArrayList<>(previous.lines());
        nextLines.add(newLine);

        CartSnapshot next = new CartSnapshot(nextLines);
        state = next;
        changes.firePropertyChange("state", previous, next);
    }
}
~~~

Model tạo snapshot mới từ trạng thái trước đó, thay thế trạng thái hiện tại rồi phát một thông báo duy nhất. Mọi Observer nhận được cùng snapshot mới. Ví dụ này không đồng bộ hóa nhiều luồng; nếu nhiều luồng có thể cùng cập nhật Model, cần bảo vệ thao tác đọc–sửa–ghi và bảo đảm thứ tự công bố phiên bản, như trình bày ở phần xử lý đồng thời.

### 6.3. View danh sách và View tóm tắt cùng quan sát Model

View danh sách hiển thị từng mặt hàng:

~~~java
import java.beans.PropertyChangeEvent;
import java.beans.PropertyChangeListener;

public final class CartDetailsView
        implements PropertyChangeListener, AutoCloseable {
    private final CartModel model;

    public CartDetailsView(CartModel model) {
        this.model = model;
        model.addListener(this);
        render(model.snapshot());
    }

    @Override
    public void propertyChange(PropertyChangeEvent event) {
        render((CartSnapshot) event.getNewValue());
    }

    private void render(CartSnapshot snapshot) {
        System.out.println("Danh sách sản phẩm:");
        snapshot.lines().forEach(line ->
                System.out.printf(
                        "%s x %d%n",
                        line.productName(),
                        line.quantity()
                )
        );
    }

    @Override
    public void close() {
        model.removeListener(this);
    }
}
~~~

View tóm tắt chỉ hiển thị số lượng và tổng tiền:

~~~java
import java.beans.PropertyChangeEvent;
import java.beans.PropertyChangeListener;

public final class CartSummaryView
        implements PropertyChangeListener, AutoCloseable {
    private final CartModel model;

    public CartSummaryView(CartModel model) {
        this.model = model;
        model.addListener(this);
        render(model.snapshot());
    }

    @Override
    public void propertyChange(PropertyChangeEvent event) {
        render((CartSnapshot) event.getNewValue());
    }

    private void render(CartSnapshot snapshot) {
        System.out.printf(
                "Có %d sản phẩm, tổng tiền %s%n",
                snapshot.itemCount(),
                snapshot.total()
        );
    }

    @Override
    public void close() {
        model.removeListener(this);
    }
}
~~~

Khởi tạo hai View với cùng một Model:

~~~java
import java.math.BigDecimal;

public class CartScreen {
    public static void main(String[] args) {
        CartModel cart = new CartModel();

        try (
                CartDetailsView details = new CartDetailsView(cart);
                CartSummaryView summary = new CartSummaryView(cart)
        ) {
            cart.addLine(new CartLine(
                    "Bàn phím",
                    2,
                    new BigDecimal("500000")
            ));
        }
    }
}
~~~

Khi addLine được gọi, Model phát một thông báo. Cả CartDetailsView và CartSummaryView nhận cùng snapshot và tự trình bày phần dữ liệu mà chúng cần. View chi tiết hiển thị dòng hàng; View tóm tắt hiển thị số lượng hai và tổng tiền 1.000.000. Không View nào phải tự sửa bản sao giỏ hàng của mình.

## 7. Controller điều phối thay đổi như thế nào?

Trong ví dụ trên, lời gọi trực tiếp cart.addLine đại diện cho thao tác được Controller điều phối. Một Controller thực tế nên nhận dữ liệu từ giao diện, chuyển thành command và gọi phương thức nghiệp vụ phù hợp:

~~~java
public record AddCartItemCommand(
        long productId,
        int quantity
) {
}

public final class CartController {
    private final CartApplicationService cartService;

    public CartController(CartApplicationService cartService) {
        this.cartService = cartService;
    }

    public void addItem(AddCartItemCommand command) {
        cartService.addItem(command.productId(), command.quantity());
    }
}
~~~

CartApplicationService chịu trách nhiệm tra cứu sản phẩm, lấy giá có thẩm quyền, kiểm tra tồn kho và điều kiện mua, sau đó cập nhật CartModel bằng một CartLine hợp lệ. Controller không nhận giá do trình duyệt gửi và không tự quyết định quy tắc mua hàng.

Điểm chính là mọi View gửi thao tác qua cùng một luồng điều phối. Việc thay đổi Model được thực hiện ở một nơi có thể kiểm soát, sau đó các View nhận thông báo từ cùng nguồn trạng thái.

## 8. Đồng bộ nhiều View trong ứng dụng web

Trong ứng dụng web, cần phân biệt một Model object sống trong cùng tiến trình với trạng thái được lưu trên máy chủ và các bản hiển thị ở trình duyệt.

### 8.1. Ứng dụng render HTML phía máy chủ

Với Spring MVC dùng template phía máy chủ, mỗi request thường có vòng đời riêng:

1. Trình duyệt gửi request.
2. Controller gọi service để đọc trạng thái hiện tại.
3. Controller đưa dữ liệu vào org.springframework.ui.Model.
4. View template render HTML từ dữ liệu của request.
5. Trình duyệt hiển thị kết quả.

Nếu một request khác cập nhật dữ liệu, trang HTML đã được gửi trước đó không tự thay đổi. Người dùng cần tải lại trang hoặc gửi request mới để nhận trạng thái mới. org.springframework.ui.Model là vùng chứa dữ liệu cho lần render hiện tại, không phải một đối tượng Observer kết nối lâu dài với trình duyệt.

Vì vậy, nhiều URL có thể dùng chung Model nghiệp vụ và đọc cùng nguồn lưu trữ, nhưng mỗi phản hồi HTML là một snapshot tại thời điểm request được xử lý.

### 8.2. Ứng dụng một trang (SPA)

Với SPA, trình duyệt thường giữ một client-side store hoặc state container. Nhiều component đọc các projection từ cùng store. Khi API trả về trạng thái mới, ứng dụng cập nhật store; các component phụ thuộc vào phần state thay đổi được render lại.

~~~mermaid
flowchart TD
    U[Thao tác trên component] --> A[API Request]
    A --> C[Controller]
    C --> S[Application Service]
    S --> M[Model và cơ sở dữ liệu]
    M --> S
    S --> C
    C --> R[API Response]
    R --> ST[Client-side Store]
    ST --> V1[Component danh sách]
    ST --> V2[Component số lượng]
    ST --> V3[Component tổng tiền]
~~~

Client-side store là bản trạng thái phục vụ giao diện, không phải nguồn chân lý của nghiệp vụ. Máy chủ vẫn phải xác thực và kiểm tra mọi command. Nếu client cập nhật giao diện lạc quan trước khi server xác nhận, cần có cách rollback hoặc tải lại trạng thái khi server từ chối.

### 8.3. Cập nhật nhiều trình duyệt đang mở

Nếu nhiều người dùng hoặc nhiều tab cùng mở một dữ liệu và cần nhận thay đổi gần thời gian thực, request–response thông thường chưa đủ. Máy chủ có thể phát sự kiện qua Server-Sent Events (SSE), WebSocket hoặc một kênh thông báo khác.

~~~mermaid
flowchart LR
    U1[Người dùng A] --> C[Controller / Use case]
    C --> M[Model và lưu trữ]
    M --> E[Sự kiện sau cập nhật]
    E --> D[Phân phối thông báo]
    D --> W1[Trình duyệt A]
    D --> W2[Trình duyệt B]
    D --> W3[Trình duyệt C]
    W1 --> S1[Store / View A]
    W2 --> S2[Store / View B]
    W3 --> S3[Store / View C]
~~~

SSE phù hợp khi máy chủ chủ yếu đẩy sự kiện một chiều đến trình duyệt. WebSocket phù hợp khi hai phía cần trao đổi hai chiều liên tục. Dù dùng cơ chế nào, máy chủ phải kiểm tra quyền nhận theo người dùng, tài nguyên hoặc kênh đăng ký. Không phát toàn bộ Model cho mọi client.

Thông báo có thể chỉ chứa định danh tài nguyên và phiên bản mới. Client nhận thông báo rồi gọi API để tải dữ liệu mới. Cách này giảm nguy cơ payload sự kiện chứa thông tin nhạy cảm và cho phép máy chủ tiếp tục áp dụng chính sách truy cập.

## 9. Đảm bảo tính nhất quán khi có nhiều thay đổi

Đồng bộ nhiều View trở nên phức tạp khi nhiều thao tác xảy ra gần nhau hoặc nhiều người dùng cùng sửa một Model.

### 9.1. Tránh trạng thái trung gian

Gom các thay đổi có quan hệ thành một thao tác nghiệp vụ. Tính snapshot mới hoàn chỉnh rồi mới thông báo. Không phát sự kiện sau từng phép gán nếu View cần nhìn thấy một trạng thái nhất quán của toàn bộ đối tượng.

### 9.2. Dùng phiên bản để nhận biết dữ liệu cũ

Có thể gắn số phiên bản tăng dần vào snapshot hoặc event. View chỉ áp dụng dữ liệu có phiên bản mới hơn phiên bản đang hiển thị. Nếu nhận phiên bản 12 sau khi đã áp dụng phiên bản 13, View bỏ qua thông báo cũ hoặc yêu cầu đồng bộ lại theo chính sách.

~~~java
public record VersionedCartSnapshot(
        long version,
        CartSnapshot snapshot
) {
}
~~~

Phiên bản giúp phát hiện sự kiện đến sai thứ tự hoặc trạng thái cũ, nhưng không tự giải quyết xung đột ghi. Việc cập nhật phiên bản cần được bảo vệ ở nơi lưu trạng thái có thẩm quyền.

### 9.3. Kiểm soát cập nhật đồng thời

Nếu hai request cùng đọc phiên bản 5 rồi cùng cập nhật, một request có thể ghi đè thay đổi của request còn lại. Với cơ sở dữ liệu, có thể dùng optimistic locking qua trường version; request cập nhật chỉ thành công nếu phiên bản hiện tại vẫn bằng phiên bản mà nó đã đọc.

Trong HTTP API, ETag kết hợp If-Match có thể giúp client gửi điều kiện phiên bản khi cập nhật. Nếu tài nguyên đã đổi, máy chủ trả lỗi xung đột hoặc tiền điều kiện không thỏa mãn theo hợp đồng, thay vì âm thầm ghi đè dữ liệu mới.

### 9.4. Chọn mức nhất quán phù hợp

| Mức đồng bộ | Đặc điểm | Trường hợp phù hợp |
|---|---|---|
| Đồng bộ trong cùng luồng | View được gọi cập nhật ngay sau thay đổi | Ứng dụng desktop hoặc UI một luồng |
| Đồng bộ trong cùng request | Phản hồi trả về trạng thái sau khi use case hoàn tất | Form hoặc API cần hiển thị kết quả ngay |
| Nhất quán sau khi tải lại | View đọc trạng thái mới ở request tiếp theo | Website render phía máy chủ |
| Nhất quán cuối cùng | Sự kiện được phân phối sau; View có thể tạm thời cũ | Dashboard, thông báo và hệ thống phân tán |

Không phải màn hình nào cũng cần cập nhật theo thời gian thực. Hãy xác định độ trễ tối đa mà người dùng chấp nhận và hậu quả nếu họ nhìn thấy dữ liệu cũ. Màn hình hiển thị số người đang trực tuyến có thể chấp nhận trễ vài giây; màn hình xác nhận tồn kho hoặc thanh toán cần dựa trên trạng thái được kiểm tra ở máy chủ trước khi hoàn tất giao dịch.

## 10. Giao dịch và thông báo sau khi lưu thành công

Với Model được lưu vào cơ sở dữ liệu, cần bảo đảm thông báo phản ánh dữ liệu đã commit. Nếu ứng dụng gửi sự kiện đến View hoặc hệ thống khác trước khi giao dịch commit, người nhận có thể cập nhật theo một thay đổi cuối cùng bị rollback.

Với sự kiện nội bộ trong Spring, @TransactionalEventListener có thể xử lý sau commit. Tuy nhiên, việc chỉ phát event trong bộ nhớ sau commit vẫn có khoảng trống: tiến trình có thể dừng sau khi cơ sở dữ liệu commit nhưng trước khi gửi event. Nếu sự kiện bắt buộc phải được phát, Transactional Outbox giúp ghi thay đổi nghiệp vụ và bản ghi sự kiện trong cùng giao dịch; một tiến trình khác phân phối sự kiện sau đó.

View nhận event nên xử lý idempotent nếu hạ tầng có thể gửi lặp. Nếu sự kiện bị bỏ lỡ hoặc client mất kết nối, client cần có cách tải lại snapshot hiện tại. Không nên dựa vào chuỗi thông báo tạm thời làm nguồn trạng thái duy nhất.

## 11. Hiệu năng khi nhiều View cùng cập nhật

Khi số lượng View tăng, một thay đổi có thể kích hoạt nhiều lần render hoặc truy vấn. Cần cân nhắc:

- Chỉ thông báo cho những View thực sự phụ thuộc vào phần dữ liệu thay đổi.
- Gửi snapshot dùng chung hoặc projection đã tính toán để tránh lặp phép tính tốn kém.
- Tách sự kiện theo loại thay đổi khi các View có nhu cầu khác nhau.
- Gộp nhiều thay đổi nhanh thành một lần render nếu giao diện không cần hiển thị mọi trạng thái trung gian.
- Dùng cache có phiên bản hoặc cơ chế invalidation rõ ràng.
- Tránh để listener thực hiện tác vụ mạng hoặc truy vấn chậm trong luồng giao diện.

Trong ứng dụng desktop, callback cập nhật giao diện cần chạy trên UI thread của framework. Nếu Model đổi từ một luồng nền, hãy đưa thao tác render về UI event queue, chẳng hạn cơ chế dispatch của Swing hoặc JavaFX. Không cập nhật component giao diện trực tiếp từ một luồng không được phép.

Với ứng dụng web nhiều người dùng, tránh lưu một mutable Model dùng chung toàn cục cho tất cả session. Trạng thái theo người dùng phải được phân vùng và truy xuất theo danh tính, quyền và ngữ cảnh. Một singleton chứa giỏ hàng mutable có thể khiến dữ liệu giữa các người dùng rò rỉ hoặc ghi đè lẫn nhau.

## 12. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Mỗi View giữ bản sao Model có thể sửa | Dữ liệu giữa các View bị lệch | Dùng một nguồn trạng thái có thẩm quyền |
| View tự tính lại quy tắc nghiệp vụ | Kết quả khác nhau giữa các màn hình | Đưa quy tắc vào Model hoặc service nghiệp vụ |
| Phát nhiều thông báo cho một thay đổi nguyên tử | View nhìn thấy trạng thái trung gian | Cập nhật snapshot hoàn chỉnh rồi thông báo một lần |
| Không gỡ Observer khi View đóng | Rò rỉ bộ nhớ và callback ngoài vòng đời | Quản lý đăng ký và unsubscribe |
| Callback thực hiện tác vụ nặng | Giao diện hoặc request bị chậm | Giữ callback ngắn, chuyển việc phù hợp sang nền |
| Không có cơ chế khôi phục sau khi mất event | View tiếp tục hiển thị dữ liệu cũ | Tải lại snapshot hoặc đồng bộ theo version |
| Không kiểm soát thứ tự event | View có thể áp dụng dữ liệu cũ sau dữ liệu mới | Dùng version, sequence và idempotency |
| Gửi toàn bộ Model đến mọi client | Rò rỉ dữ liệu và phụ thuộc quá mức | Gửi projection tối thiểu, kiểm tra quyền |
| Dùng chung Model mutable giữa các người dùng web | Trộn dữ liệu giữa các session | Phân vùng trạng thái theo người dùng và phạm vi |

## 13. Kiểm thử đồng bộ nhiều View

Kiểm thử cần xác nhận cả Model lẫn các View phản ánh cùng một phiên bản trạng thái.

1. **Một thay đổi, nhiều View:** thay đổi số lượng giỏ hàng và xác nhận View danh sách, View biểu tượng và View tổng tiền đều nhận trạng thái mới.
2. **Không phát thông báo thừa:** một thao tác không làm thay đổi trạng thái không tạo event nếu hợp đồng quy định như vậy.
3. **Snapshot nhất quán:** tổng số lượng và tổng tiền được tính từ cùng danh sách dòng hàng.
4. **Vòng đời Observer:** View đã gỡ đăng ký không còn nhận callback.
5. **Lỗi callback:** một View lỗi không làm các View độc lập khác bị bỏ cập nhật nếu chính sách yêu cầu cô lập lỗi.
6. **Sự kiện trùng hoặc sai thứ tự:** View không quay lại phiên bản cũ và có thể đồng bộ lại khi phát hiện khoảng trống.
7. **Cập nhật đồng thời:** hai request cùng sửa một tài nguyên không âm thầm ghi đè thay đổi của nhau.
8. **Phân quyền:** client chỉ nhận dữ liệu và event thuộc phạm vi được phép.

Với ứng dụng web, có thể kiểm thử Controller và application service riêng, sau đó có kiểm thử tích hợp xác nhận request cập nhật và request đọc tiếp theo trả về trạng thái nhất quán. Với SSE hoặc WebSocket, cần kiểm tra cả quyền đăng ký, ngắt kết nối, kết nối lại và hành vi tải lại dữ liệu.

## 14. Checklist thiết kế

Trước khi triển khai tính năng có nhiều View cùng phản ánh một Model, hãy xác nhận:

- Model nào là nguồn trạng thái có thẩm quyền?
- Những View nào phụ thuộc vào từng phần dữ liệu?
- View cần pull snapshot, nhận push event hay kết hợp cả hai?
- Một thay đổi nghiệp vụ có được công bố như một snapshot nhất quán không?
- Mỗi View có thể làm mới khi bỏ lỡ thông báo không?
- Phiên bản và thứ tự cập nhật có được kiểm soát khi có nhiều request đồng thời không?
- Mức nhất quán có phù hợp với yêu cầu của từng màn hình không?
- Đăng ký Observer có được gỡ đúng vòng đời không?
- Client có được xác thực và phân quyền trước khi nhận dữ liệu không?
- Kiểm thử có xác nhận nhiều View cùng phản ánh một trạng thái sau cập nhật không?

Nhiều View có thể khác nhau về cách trình bày nhưng phải dựa trên cùng trạng thái nghiệp vụ có thẩm quyền. Khi Model công bố thay đổi theo một hợp đồng rõ ràng, các View có thể cập nhật độc lập mà vẫn nhất quán. Trong ứng dụng web, cần bổ sung cơ chế đọc lại, phiên bản và truyền sự kiện phù hợp với vòng đời request và khả năng mất kết nối của client.
