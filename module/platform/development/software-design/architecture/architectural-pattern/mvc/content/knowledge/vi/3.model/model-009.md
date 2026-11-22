# Thông báo thay đổi Model cho các thành phần quan tâm

Trong kiến trúc Model–View–Controller (MVC), Model quản lý trạng thái và quy tắc nghiệp vụ của ứng dụng. Khi trạng thái đó thay đổi, những thành phần đang phụ thuộc vào nó có thể cần được thông báo để cập nhật cách trình bày, làm mới dữ liệu dẫn xuất hoặc thực hiện một công việc liên quan. Cơ chế phổ biến để tổ chức quan hệ này là Observer (mẫu quan sát): thành phần quan tâm đăng ký nhận thông báo, còn Model phát thông báo sau khi một thay đổi hợp lệ xảy ra.

Thông báo thay đổi giúp các thành phần phối hợp mà không phải liên tục hỏi Model xem dữ liệu đã đổi hay chưa. Tuy nhiên, việc thông báo cần có ranh giới rõ ràng: ai được đăng ký, thông tin nào được gửi, thông báo được gửi đồng bộ hay bất đồng bộ, và điều gì xảy ra khi một bên nhận gặp lỗi. Trong ứng dụng web, cần phân biệt thông báo giữa các đối tượng trong cùng tiến trình với thông báo cập nhật đến trình duyệt qua mạng.

## 1. Vì sao cần thông báo khi Model thay đổi?

Một Model có thể được nhiều thành phần sử dụng. Ví dụ, Model giỏ hàng có thể được quan sát bởi:

- View giỏ hàng để cập nhật danh sách sản phẩm và tổng tiền.
- Biểu tượng giỏ hàng trên thanh điều hướng để cập nhật số lượng mặt hàng.
- Thành phần tính phí vận chuyển để tính lại chi phí khi địa chỉ hoặc số lượng thay đổi.
- Thành phần ghi nhận lịch sử để lưu lại sự kiện nghiệp vụ cần thiết.

Nếu các thành phần này phải tự kiểm tra Model theo chu kỳ, ứng dụng sẽ phát sinh các truy vấn lặp lại, độ trễ và logic kiểm tra khó quản lý. Nếu Controller phải gọi từng View sau mỗi lần thay đổi, Controller sẽ biết quá nhiều về những thành phần đang quan tâm đến Model. Khi thêm một View mới, mã điều phối lại phải thay đổi.

Với cơ chế quan sát, thành phần quan tâm đăng ký với Model hoặc một bộ phát sự kiện. Khi có thay đổi, bên phát thông báo cho các bên đã đăng ký. Mỗi bên nhận tự quyết định cách phản ứng phù hợp với trách nhiệm của mình.

## 2. Observer trong quan hệ Model–View

Observer là mẫu thiết kế hành vi gồm hai vai trò chính:

- **Subject (đối tượng được quan sát):** giữ trạng thái hoặc quản lý danh sách người quan sát; phát thông báo khi có thay đổi cần quan tâm.
- **Observer (đối tượng quan sát):** đăng ký nhận thông báo và triển khai hành vi cập nhật khi thông báo đến.

Trong MVC cổ điển, Model thường đóng vai trò Subject, còn một hoặc nhiều View đóng vai trò Observer. Controller tiếp nhận thao tác của người dùng và yêu cầu Model thay đổi. Khi Model thay đổi thành công, Model thông báo cho các View đang quan sát. View sau đó đọc trạng thái mới hoặc dùng dữ liệu trong thông báo để cập nhật phần trình bày.

~~~mermaid
flowchart TD
    U[Người dùng] --> C[Controller]
    C -->|Yêu cầu thay đổi| M[Model / Subject]
    M -->|Trạng thái thay đổi hợp lệ| N[Thông báo thay đổi]
    N --> V1[View danh sách / Observer]
    N --> V2[View tổng quan / Observer]
    N --> V3[Thành phần quan tâm khác]
    V1 -->|Đọc trạng thái mới| M
    V2 -->|Đọc trạng thái mới| M
~~~

Luồng này có một số đặc điểm:

1. Controller chỉ cần yêu cầu Model thực hiện hành động nghiệp vụ; Controller không cần liệt kê mọi View đang quan sát.
2. Model phát thông báo sau khi thay đổi đã được chấp nhận theo quy tắc nghiệp vụ.
3. Mỗi Observer quyết định có cần đọc lại Model, tính toán dữ liệu dẫn xuất hay cập nhật giao diện hay không.
4. Có thể thêm hoặc gỡ Observer trong vòng đời ứng dụng mà không phải sửa logic nghiệp vụ của Model.

Thông báo không có nghĩa là View được phép sửa trực tiếp trạng thái nội bộ của Model. Nếu View phát sinh hành động mới, hành động đó vẫn cần đi qua Controller hoặc use case thích hợp.

## 3. Phân biệt thông báo thay đổi với việc truy vấn trạng thái

Hai cách tiếp cận thường được kết hợp:

| Cách tiếp cận | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Truy vấn (pull) | Trạng thái hiện tại là gì? | View gọi model.getTotal() sau khi nhận thông báo |
| Thông báo mang dữ liệu (push) | Điều gì vừa thay đổi? | Event chứa số lượng cũ và mới |

Với kiểu pull, thông báo chỉ cho biết có thay đổi. Observer đọc trạng thái mới từ Model. Cách này tránh gửi nhiều dữ liệu và phù hợp khi View cần trạng thái tổng thể mới nhất.

Với kiểu push, thông báo chứa thông tin thay đổi như tên thuộc tính, giá trị cũ, giá trị mới hoặc một sự kiện nghiệp vụ. Observer có thể cập nhật phần liên quan mà không cần truy vấn lại toàn bộ Model. Tuy nhiên, thông báo cần chứa đủ dữ liệu để người nhận xử lý và không nên làm lộ những trường mà người nhận không có quyền xem.

Ví dụ, khi số lượng trong giỏ hàng thay đổi, một View nhỏ chỉ cần nhận tổng số lượng mới để cập nhật biểu tượng. Một View chi tiết có thể đọc lại toàn bộ giỏ hàng để dựng lại danh sách. Lựa chọn pull hay push phụ thuộc vào chi phí truy vấn, kích thước thông báo và yêu cầu nhất quán.

## 4. Cài đặt Observer đơn giản trong Java

Java cung cấp PropertyChangeSupport để hỗ trợ thông báo khi thuộc tính của một đối tượng thay đổi. Ví dụ dưới đây minh họa Model sản phẩm thông báo khi giá thay đổi.

### 4.1. Model phát thông báo

~~~java
import java.beans.PropertyChangeListener;
import java.beans.PropertyChangeSupport;
import java.math.BigDecimal;
import java.util.Objects;

public final class ProductModel {
    private final PropertyChangeSupport changes =
            new PropertyChangeSupport(this);

    private BigDecimal price;

    public ProductModel(BigDecimal initialPrice) {
        this.price = Objects.requireNonNull(initialPrice);
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void addPropertyChangeListener(
            String property,
            PropertyChangeListener listener
    ) {
        changes.addPropertyChangeListener(property, listener);
    }

    public void removePropertyChangeListener(
            String property,
            PropertyChangeListener listener
    ) {
        changes.removePropertyChangeListener(property, listener);
    }

    public void changePrice(BigDecimal newPrice) {
        Objects.requireNonNull(newPrice, "newPrice");
        if (newPrice.signum() < 0) {
            throw new IllegalArgumentException("Giá không hợp lệ");
        }

        BigDecimal oldPrice = this.price;
        if (oldPrice.compareTo(newPrice) == 0) {
            return;
        }

        this.price = newPrice;
        changes.firePropertyChange("price", oldPrice, newPrice);
    }
}
~~~

Phương thức changePrice kiểm tra dữ liệu đầu vào, cập nhật giá rồi phát thông báo price. Nếu giá mới bằng giá hiện tại theo phép so sánh số học, Model không phát thông báo thừa. Phương thức firePropertyChange gửi sự kiện đến các listener đã đăng ký cho thuộc tính đó và các listener đăng ký chung.

Ví dụ này giả định việc thay đổi Model được tuần tự hóa trong một luồng xử lý. PropertyChangeSupport hỗ trợ quản lý danh sách listener an toàn khi đăng ký và gỡ đăng ký đồng thời, nhưng điều đó không tự làm cho mọi trường dữ liệu của ProductModel an toàn khi nhiều luồng cùng đọc và ghi. Ứng dụng đa luồng cần thiết kế đồng bộ trạng thái và thứ tự phát sự kiện một cách riêng biệt.

### 4.2. View đăng ký và gỡ đăng ký

Một View có thể đăng ký lắng nghe thuộc tính price:

~~~java
import java.beans.PropertyChangeEvent;
import java.beans.PropertyChangeListener;
import java.math.BigDecimal;

public final class ProductPriceView
        implements PropertyChangeListener, AutoCloseable {

    private final ProductModel model;

    public ProductPriceView(ProductModel model) {
        this.model = model;
        model.addPropertyChangeListener("price", this);
        render(model.getPrice());
    }

    @Override
    public void propertyChange(PropertyChangeEvent event) {
        BigDecimal newPrice = (BigDecimal) event.getNewValue();
        render(newPrice);
    }

    private void render(BigDecimal price) {
        System.out.println("Giá hiện tại: " + price);
    }

    @Override
    public void close() {
        model.removePropertyChangeListener("price", this);
    }
}
~~~

Khi tạo View, listener được đăng ký và View hiển thị trạng thái hiện tại. Khi Model phát thông báo, phương thức propertyChange được gọi để cập nhật phần trình bày. Khi View không còn được sử dụng, close gỡ listener để Model không tiếp tục giữ tham chiếu đến View.

Có thể sử dụng như sau:

~~~java
import java.math.BigDecimal;

public class ObserverExample {
    public static void main(String[] args) {
        ProductModel product =
                new ProductModel(new BigDecimal("100000"));

        try (ProductPriceView view = new ProductPriceView(product)) {
            product.changePrice(new BigDecimal("120000"));
        }
    }
}
~~~

Kết quả gồm giá ban đầu được hiển thị khi View khởi tạo và giá mới được hiển thị sau khi Model phát thông báo. Khi khối try kết thúc, View tự gỡ đăng ký.

## 5. Trình tự xử lý và thời điểm phát thông báo

Một thông báo đáng tin cậy cần phản ánh thay đổi đã được chấp nhận. Trình tự khái quát nên là:

1. Controller hoặc use case nhận yêu cầu thay đổi.
2. Tầng nghiệp vụ kiểm tra quyền, dữ liệu đầu vào và các bất biến.
3. Model áp dụng thay đổi hợp lệ.
4. Hệ thống phát thông báo mô tả thay đổi.
5. Observer nhận thông báo và cập nhật phần việc của mình.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant C as Controller
    participant M as Model
    participant O1 as View quan sát 1
    participant O2 as View quan sát 2
    User->>C: Yêu cầu đổi giá
    C->>M: changePrice(120000)
    M->>M: Kiểm tra và cập nhật trạng thái
    M-->>O1: Thông báo price changed
    M-->>O2: Thông báo price changed
    O1->>M: Đọc trạng thái cần hiển thị
    O2->>M: Đọc trạng thái cần hiển thị
    C-->>User: Trả kết quả request
~~~

Trong ví dụ đơn giản, thông báo được phát ngay sau khi cập nhật bộ nhớ. Với ứng dụng có lưu trữ giao dịch, cần phân biệt thay đổi trong bộ nhớ với thay đổi đã commit vào cơ sở dữ liệu. Nếu listener gửi email, gọi dịch vụ bên ngoài hoặc cập nhật một hệ thống khác trước khi giao dịch commit, tác dụng phụ có thể xảy ra dù giao dịch sau đó bị rollback.

Với sự kiện gắn với giao dịch, có thể phát hoặc xử lý sự kiện sau khi commit. Trong Spring, TransactionalEventListener với TransactionPhase.AFTER_COMMIT cho phép listener chỉ xử lý sau khi giao dịch thành công. Với yêu cầu không được mất sự kiện khi tiến trình dừng giữa lúc commit và lúc gửi thông báo, cần cân nhắc Transactional Outbox hoặc cơ chế lưu sự kiện bền vững tương đương.

## 6. Thông báo đồng bộ và bất đồng bộ

### 6.1. Đồng bộ

Với thông báo đồng bộ, bên phát gọi listener ngay trong luồng xử lý hiện tại. Khi phương thức phát thông báo kết thúc, các listener đã được gọi xong (hoặc một lỗi chưa được xử lý đã truyền ngược lên).

Ưu điểm:

- Luồng thực thi dễ theo dõi và kiểm thử.
- Observer có thể cập nhật trạng thái ngay trong cùng request.
- Không cần hàng đợi hoặc cơ chế điều phối nền.

Hạn chế:

- Một listener chậm có thể làm chậm toàn bộ request.
- Lỗi từ listener có thể ảnh hưởng đến bên phát nếu không được cô lập.
- Listener gọi ngược Model hoặc kích hoạt thêm thay đổi có thể tạo chuỗi gọi lồng nhau khó kiểm soát.

Thông báo đồng bộ phù hợp với các cập nhật nhỏ, nội bộ và cần hoàn thành trước khi trả kết quả cho người dùng.

### 6.2. Bất đồng bộ

Với thông báo bất đồng bộ, bên phát gửi sự kiện đến executor, hàng đợi hoặc message broker; người nhận xử lý sau trong một luồng hoặc tiến trình khác.

Ưu điểm:

- Bên phát không phải chờ toàn bộ công việc phụ hoàn thành.
- Có thể mở rộng số lượng consumer độc lập.
- Hệ thống có thể đệm công việc khi tải tăng, nếu hạ tầng hỗ trợ.

Hạn chế:

- Người dùng có thể chưa thấy dữ liệu mới ngay lập tức.
- Cần xử lý sự kiện trùng lặp, sai thứ tự, retry và lỗi lâu dài.
- Việc gỡ lỗi và theo dõi luồng xử lý phức tạp hơn.

Không nên chọn bất đồng bộ chỉ để làm cho kiến trúc có vẻ linh hoạt. Hãy dùng nó khi có nhu cầu thực tế về độ trễ, khả năng mở rộng hoặc tách biệt tiến trình. Nếu View cần dữ liệu mới để render ngay trong request hiện tại, View nên đọc trạng thái đã cập nhật trực tiếp; một thông báo nền không bảo đảm cập nhật kịp thời cho phản hồi đó.

## 7. Observer trong ứng dụng Spring và ứng dụng web

### 7.1. Spring application event

Spring cung cấp ApplicationEventPublisher và các listener để các thành phần trong cùng ApplicationContext trao đổi sự kiện mà không cần giữ tham chiếu trực tiếp đến nhau.

Định nghĩa sự kiện có kiểu dữ liệu rõ ràng:

~~~java
import java.math.BigDecimal;

public record ProductPriceChanged(
        long productId,
        BigDecimal oldPrice,
        BigDecimal newPrice
) {
}
~~~

Application service phát sự kiện sau khi cập nhật Model:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductApplicationService {
    private final ProductRepository repository;
    private final ApplicationEventPublisher events;

    public ProductApplicationService(
            ProductRepository repository,
            ApplicationEventPublisher events
    ) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public void changePrice(long productId, BigDecimal newPrice) {
        Product product = repository.findById(productId)
                .orElseThrow();

        BigDecimal oldPrice = product.getPrice();
        product.changePrice(newPrice);
        repository.save(product);

        events.publishEvent(new ProductPriceChanged(
                productId,
                oldPrice,
                product.getPrice()
        ));
    }
}
~~~

Listener có thể phản ứng sau khi giao dịch commit:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class ProductPriceAuditListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(ProductPriceChanged event) {
        System.out.printf(
                "Sản phẩm %d đổi giá từ %s sang %s%n",
                event.productId(),
                event.oldPrice(),
                event.newPrice()
        );
    }
}
~~~

Đây là ví dụ minh họa cấu trúc sự kiện; Product, ProductRepository và cấu hình giao dịch cần được cung cấp bởi ứng dụng. Listener giao dịch mặc định chỉ chạy khi có giao dịch phù hợp. Nếu cần xử lý bất đồng bộ, có thể kết hợp cấu hình executor và Async, đồng thời thiết kế cơ chế xử lý lỗi, retry và quan sát tác vụ nền.

Application event giúp các thành phần trong cùng ứng dụng ít phụ thuộc trực tiếp hơn. Nó không tự động trở thành message broker bền vững và không bảo đảm sự kiện được chuyển đến hệ thống khác sau khi tiến trình bị dừng.

### 7.2. View của ứng dụng web request–response

Trong ứng dụng Spring MVC dùng template phía máy chủ, mỗi HTTP request thường tạo một luồng xử lý: Controller gọi service, lấy dữ liệu mới, đưa dữ liệu vào Model của Spring MVC rồi render View. Vì vậy, View thường không cần đăng ký listener sống lâu với domain Model. Request tiếp theo chỉ cần truy vấn trạng thái mới từ service.

Cần phân biệt:

- Model nghiệp vụ: giữ dữ liệu và quy tắc của miền ứng dụng.
- org.springframework.ui.Model: vùng chứa thuộc tính mà Controller chuyển cho template trong request hiện tại.
- View: template hoặc thành phần trình bày kết quả.

org.springframework.ui.Model không phải cơ chế quan sát thay đổi tự động. Gọi addAttribute chỉ chuẩn bị dữ liệu cho lần render hiện tại; nó không khiến một trình duyệt đang mở tự cập nhật khi dữ liệu ở máy chủ đổi.

### 7.3. Cập nhật giao diện đang mở bằng WebSocket hoặc Server-Sent Events

Nếu yêu cầu sản phẩm là nhiều trình duyệt đang mở cùng nhận cập nhật gần thời gian thực, máy chủ cần một kênh truyền dữ liệu đến client. Hai lựa chọn phổ biến:

- **Server-Sent Events (SSE):** máy chủ gửi luồng sự kiện một chiều đến trình duyệt qua kết nối HTTP; phù hợp khi client chủ yếu nhận cập nhật.
- **WebSocket:** tạo kết nối hai chiều giữa client và máy chủ; phù hợp khi hai phía đều cần trao đổi thường xuyên.

Luồng điển hình là: Model hoặc application service tạo sự kiện nghiệp vụ; thành phần xử lý sự kiện xác định những người dùng được phép nhận; máy chủ gửi thông báo qua SSE hoặc WebSocket; client cập nhật phần giao diện liên quan hoặc tải lại dữ liệu mới.

~~~mermaid
flowchart LR
    U[Thao tác người dùng] --> C[Controller / Use case]
    C --> M[Model và lưu trữ]
    M --> E[Sự kiện nghiệp vụ]
    E --> B[Thành phần phân phối]
    B --> S[SSE hoặc WebSocket]
    S --> V1[Trình duyệt A]
    S --> V2[Trình duyệt B]
~~~

Kênh truyền chỉ thông báo rằng có thay đổi hoặc mang dữ liệu đã được phép công bố. Máy chủ vẫn phải xác thực người dùng, kiểm tra quyền theo từng chủ đề hoặc tài nguyên, và tránh gửi trường nội bộ. Khi client nhận sự kiện nhưng đã mất đồng bộ, cách an toàn thường là tải lại trạng thái hiện tại từ API.

## 8. Quản lý vòng đời đăng ký

Một lỗi phổ biến của Observer là đăng ký listener nhưng không gỡ đăng ký khi thành phần kết thúc vòng đời. Subject giữ tham chiếu đến listener; listener vì thế không thể được thu hồi bộ nhớ và vẫn có thể nhận thông báo ngoài thời gian mong muốn.

Hãy xác định rõ:

- Khi nào Observer đăng ký: lúc khởi tạo, lúc màn hình xuất hiện hoặc khi bắt đầu theo dõi một tài nguyên.
- Khi nào Observer gỡ đăng ký: lúc đóng màn hình, hủy tác vụ hoặc kết thúc phiên làm việc.
- Ai sở hữu đăng ký: chính Observer, đối tượng điều phối hay một đối tượng subscription có thể đóng.
- Nếu đăng ký nhiều lần, hệ thống có ngăn listener bị gọi lặp hay không.

Với Java, có thể dùng AutoCloseable như ví dụ ProductPriceView để việc gỡ đăng ký gắn với vòng đời tài nguyên. Với UI framework, hãy dùng lifecycle hook hoặc cơ chế binding/unsubscribe mà framework cung cấp.

## 9. Những vấn đề cần kiểm soát

| Vấn đề | Rủi ro | Cách xử lý |
|---|---|---|
| Listener không được gỡ | Rò rỉ bộ nhớ, nhận sự kiện sau khi đã đóng | Quản lý đăng ký theo vòng đời và unsubscribe |
| Listener thực hiện quá nhiều việc | Request bị chậm hoặc nghẽn | Giữ handler ngắn; chuyển tác vụ phù hợp sang nền |
| Listener ném exception | Các listener sau có thể không được gọi; bên phát có thể thất bại | Quy định chính sách cô lập lỗi, ghi log và retry |
| Thông báo được phát trước khi giao dịch commit | Bên nhận thực hiện tác dụng phụ cho dữ liệu sẽ rollback | Dùng sự kiện sau commit hoặc Transactional Outbox |
| Sự kiện bị gửi lặp | Cập nhật, gửi email hoặc tính tiền nhiều lần | Thiết kế consumer idempotent và khóa định danh sự kiện |
| Sự kiện đến sai thứ tự | Trạng thái dẫn xuất bị lùi về dữ liệu cũ | Dùng phiên bản, sequence hoặc kiểm tra thời điểm cập nhật |
| Thông báo chứa quá nhiều dữ liệu | Tăng phụ thuộc và nguy cơ lộ thông tin | Gửi payload tối thiểu, kiểm tra quyền trước khi phân phối |
| Observer sửa Model ngay trong callback | Tạo chuỗi thay đổi lồng nhau hoặc vòng lặp | Tách lệnh thay đổi khỏi callback, giới hạn luồng phản ứng |
| Phát sự kiện quá rộng | Thành phần không liên quan nhận nhiều thông báo | Dùng loại sự kiện và phạm vi đăng ký cụ thể |

Một listener lỗi không nên âm thầm làm mất dấu sự cố. Tùy yêu cầu, ứng dụng có thể ghi nhận lỗi, tiếp tục gọi listener khác, retry hoặc chuyển thông điệp vào dead-letter queue. Chính sách cần phù hợp với mức quan trọng của sự kiện; thông báo cập nhật một nhãn giao diện có thể được xử lý khác với sự kiện ghi nhận thanh toán.

## 10. Thiết kế sự kiện có ý nghĩa

Một sự kiện tốt mô tả điều đã xảy ra, thường dùng tên ở thì quá khứ, chẳng hạn ProductPriceChanged, OrderPlaced hoặc InventoryReserved. Sự kiện nên mang định danh đối tượng, thời điểm hoặc phiên bản khi cần, cùng dữ liệu tối thiểu giúp người nhận xử lý.

Phân biệt sự kiện với lệnh:

- **Command:** yêu cầu một thành phần thực hiện hành động, ví dụ ChangeProductPrice.
- **Event:** thông tin một việc đã xảy ra, ví dụ ProductPriceChanged.

Command có thể bị từ chối vì dữ liệu không hợp lệ hoặc người dùng không có quyền. Event chỉ nên được phát sau khi điều kiện phát sinh sự kiện đã được thỏa mãn. Người nhận sự kiện không nên hiểu event là yêu cầu tùy ý thay đổi lại Model gốc.

Không nên phát một sự kiện chung chung như ModelChanged cho mọi thay đổi nếu các bên nhận cần hành vi khác nhau. Sự kiện quá chung buộc Observer kiểm tra nhiều thuộc tính và tạo phụ thuộc vào cấu trúc nội bộ của Model. Sự kiện có ý nghĩa nghiệp vụ giúp hợp đồng giữa bên phát và bên nhận rõ ràng hơn.

## 11. Kiểm thử cơ chế thông báo

Có thể kiểm thử theo các tình huống sau:

1. **Thay đổi hợp lệ:** khi giá đổi, listener nhận đúng loại sự kiện và giá trị cũ/mới.
2. **Không có thay đổi:** gán lại cùng giá trị không tạo thông báo thừa nếu đó là chính sách đã chọn.
3. **Dữ liệu không hợp lệ:** giá âm bị từ chối và không phát sự kiện thay đổi thành công.
4. **Đăng ký và gỡ đăng ký:** listener đã gỡ không còn nhận thông báo ở lần thay đổi tiếp theo.
5. **Nhiều Observer:** tất cả Observer còn đăng ký đều nhận được thông báo theo hợp đồng.
6. **Lỗi listener:** xác nhận chính sách lỗi đã chọn, chẳng hạn listener độc lập tiếp theo vẫn được gọi hoặc sự kiện được retry.
7. **Giao dịch:** khi giao dịch rollback, listener yêu cầu AFTER_COMMIT không thực hiện tác dụng phụ.
8. **Thông báo qua mạng:** kiểm tra quyền nhận sự kiện, khả năng kết nối lại và hành vi tải lại dữ liệu khi client mất đồng bộ.

Nên kiểm thử cả kết quả nghiệp vụ lẫn tác dụng phụ. Một bài kiểm thử chỉ xác nhận phương thức listener được gọi chưa đủ để chứng minh View hiển thị đúng trạng thái hoặc hệ thống không gửi dữ liệu cho người dùng sai quyền.

## 12. Checklist lựa chọn cơ chế

Trước khi triển khai thông báo thay đổi Model, hãy trả lời:

- Thành phần nào thực sự cần biết về thay đổi?
- Chúng cần trạng thái mới nhất hay cần biết chính xác điều gì vừa xảy ra?
- Thông báo chỉ tồn tại trong một tiến trình hay cần truyền đến trình duyệt/dịch vụ khác?
- Người dùng có cần thấy kết quả ngay trong request hiện tại không?
- Listener chạy đồng bộ hay bất đồng bộ, và ai chịu trách nhiệm khi listener lỗi?
- Sự kiện có cần chờ giao dịch commit hoặc cần lưu bền vững không?
- Ai quản lý đăng ký và gỡ đăng ký theo vòng đời?
- Payload có tối thiểu và an toàn với quyền của người nhận không?
- Hệ thống có kiểm thử trường hợp trùng lặp, sai thứ tự và mất kết nối không?

Observer giúp Model thông báo thay đổi cho những thành phần quan tâm mà không buộc Model phải biết chi tiết cách từng thành phần phản ứng. Trong MVC, điều này hỗ trợ nhiều View cùng phản ánh trạng thái nghiệp vụ. Khi chuyển sang ứng dụng web và hệ thống phân tán, cần chọn thêm cơ chế sự kiện, giao dịch và truyền dữ liệu phù hợp để bảo đảm thông báo đúng thời điểm, đúng người nhận và có thể vận hành đáng tin cậy.
