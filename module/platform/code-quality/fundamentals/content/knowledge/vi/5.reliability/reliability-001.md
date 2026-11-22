# Lỗi đầu vào, lỗi nghiệp vụ và lỗi hạ tầng

Một hệ thống đáng tin cậy không phải là hệ thống không bao giờ gặp lỗi. Điều quan trọng là hệ thống **nhận diện đúng nguyên nhân, phản hồi đúng cho từng trường hợp và bảo vệ trạng thái nhất quán** khi hoạt động không diễn ra như mong muốn.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta học những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không. Với chủ đề **Độ tin cậy**, phân biệt **lỗi đầu vào**, **lỗi nghiệp vụ** và **lỗi hạ tầng** giúp lập trình viên thiết kế xác thực, xử lý, kiểm thử, giám sát và phục hồi phù hợp. Nếu gom mọi vấn đề vào một nhóm “có lỗi”, hệ thống dễ trả lời sai, thử lại vô ích hoặc che giấu sự cố thực sự.

## 1. Ba nhóm lỗi khác nhau ở điểm nào?

Giả sử khách hàng yêu cầu mua 3 sản phẩm. Ba tình huống không thành công có ý nghĩa khác nhau:

1. Yêu cầu gửi thiếu mã sản phẩm hoặc số lượng bằng -3.
2. Yêu cầu hợp lệ, nhưng kho hiện chỉ còn 2 sản phẩm.
3. Yêu cầu hợp lệ, song dịch vụ kho không phản hồi đúng thời hạn.

Cả ba đều khiến việc mua hàng chưa hoàn tất, nhưng **điều cần làm tiếp theo** khác nhau.

| Nhóm lỗi | Bản chất | Ví dụ | Hướng xử lý thường phù hợp |
| --- | --- | --- | --- |
| **Lỗi đầu vào (input/validation error)** | Yêu cầu không đáp ứng hợp đồng dữ liệu: thiếu trường bắt buộc, sai định dạng, giá trị không hợp lệ. | Số lượng bằng 0, mã sản phẩm rỗng, ngày sai định dạng. | Từ chối sớm, chỉ rõ trường cần sửa; thường không thử lại nguyên yêu cầu. |
| **Lỗi nghiệp vụ (business rule violation/conflict)** | Dữ liệu hợp lệ về hình dạng, nhưng thao tác không được phép theo trạng thái hoặc chính sách hiện hành. | Hết hàng, đơn đã hủy, vượt hạn mức mua, khuyến mãi hết hiệu lực. | Giải thích điều kiện bị vi phạm, giữ bất biến nghiệp vụ và hướng dẫn hành động tiếp theo. |
| **Lỗi hạ tầng (infrastructure/dependency failure)** | Thành phần kỹ thuật không cho phép xử lý hoặc xác nhận kết quả đáng tin cậy. | Timeout dịch vụ kho, CSDL mất kết nối, hàng đợi không sẵn sàng. | Giới hạn tác động, ghi nhận sự cố, phục hồi hoặc retry có kiểm soát nếu an toàn. |

Cách phân loại dựa vào **ý nghĩa và nguyên nhân của thất bại**, không dựa hoàn toàn vào lớp Java ném ngoại lệ. Cùng một phương thức có thể vừa kiểm tra đầu vào, vừa thực thi quy tắc nghiệp vụ và vừa gọi phụ thuộc bên ngoài.

### Ranh giới có thể phụ thuộc hợp đồng

Giá trị “số lượng lớn hơn 10” có thể là **lỗi đầu vào** nếu hợp đồng API định nghĩa miền hợp lệ từ 1 đến 10. Nó cũng có thể là **từ chối nghiệp vụ** nếu số lượng là dữ liệu hợp lệ nhưng chính sách mỗi đơn hiện chỉ cho mua 10 món. Cần định nghĩa rành mạch ở hợp đồng và giữ hành vi nhất quán.

Một câu hỏi định hướng hữu ích là: **“Điều gì cần thay đổi để yêu cầu có thể thành công?”**

- **Phía gửi sửa nội dung yêu cầu:** thường là lỗi đầu vào.
- **Trạng thái hoặc chính sách nghiệp vụ thay đổi:** thường là lỗi nghiệp vụ.
- **Hệ thống hoặc phụ thuộc phục hồi:** thường là lỗi hạ tầng.

Đây là tiêu chí thực dụng, không thay thế việc kiểm tra yêu cầu và bằng chứng. Một sự cố thực tế có thể liên quan nhiều nguyên nhân.

## 2. Phân loại sai có thể khiến hệ thống kém tin cậy hơn

| Phân loại sai | Hậu quả |
| --- | --- |
| Coi **hết hàng** là **lỗi máy chủ** | Sinh cảnh báo vận hành giả; người dùng có thể hiểu lầm rằng thử lại ngay sẽ hết lỗi. |
| Coi **CSDL không phản hồi** là **hết hàng** | Trả thông tin nghiệp vụ không có căn cứ, che giấu sự cố kỹ thuật. |
| Coi **đầu vào sai** là lỗi tạm thời | Retry yêu cầu không thể thành công, tăng tải cho hệ thống. |
| Coi **timeout** là bằng chứng thao tác chưa diễn ra | Có thể tạo đơn hoặc ghi tiền hai lần khi retry một tác vụ có tác dụng phụ. |
| Trả **stack trace hoặc chi tiết kết nối** cho người dùng | Có thể làm lộ thông tin nội bộ và dữ liệu nhạy cảm. |

Độ tin cậy không chỉ là trả kết quả đúng ở luồng thành công. Hệ thống còn cần **từ chối đúng khi yêu cầu không thể thực hiện**, **không biến sự cố kỹ thuật thành kết luận nghiệp vụ** và **không làm hỏng trạng thái khi có lỗi**.

## 3. Lỗi đầu vào: kiểm tra hợp đồng tại ranh giới tin cậy

Đầu vào có thể đi qua HTTP API, message queue, file, tác vụ nền hoặc các dịch vụ nội bộ. Không nên giả định đầu vào đúng chỉ vì nó đến từ một giao diện do chính đội ngũ xây dựng.

Những lỗi thường gặp:

- **Thiếu bắt buộc:** mã sản phẩm null, mã người dùng trống.
- **Sai kiểu hoặc cú pháp:** chuỗi “abc” ở trường số; JSON hỏng; ngày không thể phân tích.
- **Ngoài miền giá trị:** số lượng âm; chuỗi dài quá giới hạn; giá trị enum không hỗ trợ.
- **Sai tương quan:** ngày kết thúc trước ngày bắt đầu, dù hai ngày riêng lẻ có định dạng đúng.
- **Vượt giới hạn tài nguyên:** payload quá lớn, danh sách quá dài so với hợp đồng.

Ví dụ Java:

~~~java
static void validate(String productCode, int quantity) {
    if (productCode == null || productCode.isBlank()) {
        throw new IllegalArgumentException("Product code is required");
    }
    if (quantity <= 0) {
        throw new IllegalArgumentException("Quantity must be positive");
    }
}
~~~

Cần chú ý ba điều:

1. **Kiểm tra đủ sớm** để từ chối yêu cầu sai trước khi gọi CSDL hoặc dịch vụ ngoài nếu không cần thiết.
2. **Bảo vệ bất biến ở lớp thích hợp** khi cùng logic có thể được gọi từ nhiều điểm nhập. Kiểm tra phía giao diện không thay thế kiểm tra phía máy chủ.
3. **Không tự sửa đầu vào một cách âm thầm** nếu làm thay đổi ý nghĩa. Ví dụ đổi số lượng -2 thành 2 bằng giá trị tuyệt đối có thể biến lỗi nhập liệu thành giao dịch không mong muốn.

Ở biên HTTP, lỗi phân tích JSON có thể được xử lý bởi framework trước khi vào service. Bên trong Java, có thể dùng validation annotations hoặc logic tường minh. Cách triển khai khác nhau nhưng hợp đồng và phản hồi cần rõ ràng.

## 4. Lỗi nghiệp vụ: đầu vào hợp lệ nhưng hành động bị từ chối

Quy tắc nghiệp vụ trả lời câu hỏi: **“Trong trạng thái hiện tại, có được phép thực hiện hành động này không?”**

Ví dụ:

- Đơn đã thanh toán mới được hoàn tiền; đơn chưa thanh toán phải bị từ chối.
- Số lượng mua là số nguyên dương nhưng lớn hơn lượng tồn.
- Mã ưu đãi có định dạng đúng nhưng đã hết hạn.
- Khách hàng được mua tối đa 10 món mỗi đơn.
- Đơn hàng đã hủy nên không thể giao tiếp.

Nhiều kết quả như “hết hàng” là **một phần hoạt động bình thường** của sản phẩm. Không nên tạo cảnh báo vận hành khẩn cấp cho mỗi lần một người chọn số lượng vượt tồn kho.

Điều quan trọng là giữ **bất biến nghiệp vụ**. Ví dụ, “tồn kho không được âm” và “một đơn chỉ có một trạng thái cuối cùng hợp lệ”. Nếu hai yêu cầu đồng thời cùng kiểm tra một sản phẩm còn đúng 1 chiếc, cả hai có thể cùng đọc thấy còn hàng. Vì vậy, một phép kiểm tra bằng lệnh if dựa trên dữ liệu đọc trước **không đủ để giữ tồn kho chính xác**. Khi thật sự giữ hoặc trừ tồn, phải bảo vệ ở thao tác cập nhật nguyên tử, giao dịch hoặc cơ chế đồng bộ phù hợp.

Với trường hợp từ chối dự kiến, có thể biểu diễn bằng enum, kết quả có kiểu (Result) hoặc ngoại lệ nghiệp vụ. Lựa chọn nào cũng cần làm rõ để phía gọi không nhầm với lỗi kỹ thuật.

## 5. Lỗi hạ tầng: không đủ khả năng thực hiện hoặc xác nhận kết quả

Lỗi hạ tầng bắt nguồn từ khả năng hoạt động của CSDL, mạng, hệ thống tệp, dịch vụ ngoài, bộ nhớ, hàng đợi, DNS hoặc hạ tầng triển khai.

Giả sử yêu cầu mua 3 món hợp lệ nhưng dịch vụ kho timeout. Hệ thống **không có bằng chứng** rằng kho chỉ còn 2, hay còn 10. Nếu mặc định trả “hết hàng”, hệ thống đang đưa ra kết luận nghiệp vụ không dựa trên dữ liệu đáng tin cậy.

### Timeout không đồng nghĩa thao tác chưa xảy ra

Với thao tác chỉ đọc, timeout thường có nghĩa chưa nhận được kết quả đủ tin cậy. Với thao tác **có tác dụng phụ** như tạo đơn, trừ tồn hoặc gửi thanh toán, timeout có thể xảy ra sau khi phía nhận đã thực hiện thành công nhưng phản hồi chưa đến được phía gọi.

Sau một timeout, có thể là:

- Thao tác chưa được thực hiện.
- Thao tác đã hoàn tất nhưng phản hồi bị thất lạc.
- Thao tác vẫn đang xử lý hoặc trạng thái cuối chưa được xác nhận.

Vì vậy, không mặc định retry một lệnh tạo đơn hoặc chuyển tiền chỉ dựa vào việc phía gọi chưa nhận được phản hồi. Có thể cần **khóa idempotency**, ràng buộc định danh duy nhất, API kiểm tra trạng thái hoặc đối soát giao dịch trước khi thực hiện lại.

### Biện pháp xử lý lỗi kỹ thuật

| Biện pháp | Mục đích | Lưu ý |
| --- | --- | --- |
| **Timeout/deadline** | Giới hạn thời gian chờ để tránh treo tài nguyên. | Phù hợp với ngân sách thời gian toàn luồng và kỳ vọng người dùng. |
| **Retry giới hạn** | Vượt qua lỗi thoáng qua, ví dụ mất kết nối ngắn. | Chỉ retry khi an toàn; có giới hạn số lần, backoff và jitter. |
| **Circuit breaker** | Giảm yêu cầu tới một phụ thuộc liên tục lỗi. | Cần quy tắc phục hồi và theo dõi trạng thái. |
| **Bulkhead/giới hạn đồng thời** | Tránh một phụ thuộc chậm làm cạn tài nguyên chung. | Điều chỉnh theo tải và tài nguyên thực tế. |
| **Fallback** | Cung cấp phương án thay thế khi phù hợp. | Không dùng dữ liệu cũ nếu nó có thể khiến quyết định tiền hoặc quyền truy cập bị sai. |
| **Logging, metrics, tracing** | Giúp xác định nguồn gốc, tần suất và phạm vi lỗi. | Bảo vệ thông tin nhạy cảm; gắn correlation/request ID. |

Một dịch vụ đang quá tải có thể bị retry ồ ạt làm quá tải nặng hơn. Biện pháp phục hồi phải dựa trên **tính chất thao tác** và **kiểu lỗi**, không theo quy tắc “hễ lỗi thì gọi lại ba lần”.

## 6. Ví dụ Java: tách lỗi đầu vào, nghiệp vụ và phụ thuộc

Xét dịch vụ **kiểm tra điều kiện mua hàng** với quy tắc:

- Mã sản phẩm không được null hoặc trống; số lượng phải dương.
- Chính sách cho mua tối đa 10 món trong một yêu cầu.
- Sản phẩm phải được bán và tồn kho quan sát được không thấp hơn số lượng muốn mua.
- Nếu hệ thống kho không trả được thông tin tin cậy, báo lỗi phụ thuộc; **không kết luận là hết hàng**.

Ví dụ Java 17:

~~~java
public final class StockCheckService {
    public record StockInfo(boolean saleable, int availableQuantity) {}

    public interface InventoryGateway {
        // null nghĩa là không tìm thấy sản phẩm.
        // Lỗi kỹ thuật phải được ném thành InventoryUnavailableException.
        StockInfo loadStock(String productCode);
    }

    public static final class InvalidInputException extends RuntimeException {
        public InvalidInputException(String message) {
            super(message);
        }
    }

    public static final class BusinessRejectedException extends RuntimeException {
        public BusinessRejectedException(String message) {
            super(message);
        }
    }

    public static final class InventoryUnavailableException extends RuntimeException {
        public InventoryUnavailableException(String message) {
            super(message);
        }
    }

    public static final class DependencyFailureException extends RuntimeException {
        public DependencyFailureException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    private final InventoryGateway inventory;

    public StockCheckService(InventoryGateway inventory) {
        this.inventory = java.util.Objects.requireNonNull(inventory);
    }

    public void check(String productCode, int quantity) {
        if (productCode == null || productCode.isBlank() || quantity <= 0) {
            throw new InvalidInputException(
                    "Product code required; quantity must be positive");
        }

        if (quantity > 10) {
            throw new BusinessRejectedException(
                    "Maximum quantity per order is 10");
        }

        StockInfo stock;
        try {
            stock = inventory.loadStock(productCode);
        } catch (InventoryUnavailableException cause) {
            throw new DependencyFailureException(
                    "Inventory service unavailable", cause);
        }

        if (stock == null || !stock.saleable()) {
            throw new BusinessRejectedException(
                    "Product is not available for sale");
        }

        if (stock.availableQuantity() < quantity) {
            throw new BusinessRejectedException("Insufficient stock");
        }
    }
}
~~~

Bảng đường đi:

| Tình huống | Kết quả | Ý nghĩa |
| --- | --- | --- |
| Mã rỗng hoặc số lượng = 0 | InvalidInputException | Phía gửi cần sửa yêu cầu. |
| Số lượng = 11 | BusinessRejectedException | Vi phạm chính sách. |
| Còn 2, yêu cầu 3 | BusinessRejectedException | Tồn kho không đáp ứng, theo dữ liệu hiện có. |
| Gateway timeout, ném InventoryUnavailableException | DependencyFailureException (giữ cause) | Không thể xác nhận tồn kho; sự cố kỹ thuật. |
| Còn 5, yêu cầu 3 | Trả về bình thường | Kiểm tra điều kiện thành công. |

**Giới hạn của ví dụ:** Đây chỉ là kiểm tra thông tin tại một thời điểm, **chưa phải thao tác giữ hàng**. Khi có cập nhật tồn kho, cần bảo đảm tính nguyên tử, xử lý đồng thời và khôi phục các bước thất bại. Ngoài ra, gateway phải phân biệt rõ “không tìm thấy sản phẩm” với “không đọc được dữ liệu”; hợp đồng trả null ở đây nhằm rút gọn ví dụ.

### Một lỗi thiết kế rất dễ mắc

~~~java
// SAI: che giấu lỗi kỹ thuật bằng kết quả nghiệp vụ.
boolean canBuy(String productCode, int quantity) {
    try {
        var stock = inventory.loadStock(productCode);
        return stock != null
                && stock.saleable()
                && stock.availableQuantity() >= quantity;
    } catch (RuntimeException ignored) {
        return false;
    }
}
~~~

Giá trị false có thể có nghĩa là **hết hàng**, **sản phẩm không bán** hoặc **dịch vụ kho đang hỏng**. Phía gọi không biết nên sửa yêu cầu, thông báo hết hàng hay báo sự cố tạm thời. Cách bắt RuntimeException còn có thể che lỗi lập trình ngoài dự kiến.

Nếu có fallback, phải làm rõ ý nghĩa của dữ liệu dự phòng. Ví dụ hiển thị “chưa xác định được tồn kho” có thể phù hợp hơn là âm thầm hiển thị “hết hàng”.

## 7. Thiết kế phản hồi API nhất quán

Lớp HTTP/API chuyển kết quả nội bộ thành hợp đồng bên ngoài. Một số mã trạng thái thường được chọn:

| Tình huống | HTTP status tham khảo | Phản hồi cần có |
| --- | --- | --- |
| Thiếu trường, sai kiểu, giá trị ngoài miền | **400 Bad Request** | Trường và điều kiện cần sửa. |
| Dữ liệu có cú pháp đúng nhưng không thể xử lý theo quy tắc | **422 Unprocessable Content** | Mã lỗi và lý do nghiệp vụ. |
| Xung đột với trạng thái hiện tại, ví dụ giữ hàng khi hết | **409 Conflict** | Giải thích xung đột và bước tiếp theo. |
| Không tìm thấy tài nguyên theo định danh | **404 Not Found** | Mô tả theo hợp đồng API. |
| Dịch vụ tạm thời không sẵn sàng | **503 Service Unavailable** | Thông báo tạm thời, request ID; Retry-After nếu có căn cứ. |
| Gateway/proxy quá hạn chờ upstream | **504 Gateway Timeout** | Thông tin timeout phù hợp vai trò HTTP. |
| Lỗi lập trình hoặc lỗi chưa xử lý | **500 Internal Server Error** | Thông báo chung; chi tiết chỉ trong log nội bộ. |

Bảng chỉ là **khuyến nghị thiết kế**, không phải phép ánh xạ bắt buộc một-một. Một API kiểm tra hàng có thể trả HTTP 200 với kết quả không có hàng; API tạo đơn có thể dùng 409. Quan trọng là hành vi nhất quán, được tài liệu hóa và đủ rõ cho phía gọi.

Ví dụ JSON lỗi bên ngoài:

~~~json
{
  "code": "INVENTORY_UNAVAILABLE",
  "message": "Chưa thể kiểm tra tồn kho. Vui lòng thử lại sau.",
  "requestId": "req-8f1a"
}
~~~

Trường code là mã máy ổn định, message là thông báo dễ hiểu, requestId hỗ trợ đối chiếu log. Không trả stack trace, câu lệnh SQL, thông tin kết nối hay dữ liệu cá nhân trong lỗi công khai.

Các lỗi xác thực/phân quyền có yêu cầu bảo mật riêng: thường gặp 401 khi chưa xác thực hợp lệ và 403 khi đã xác thực nhưng không đủ quyền. Không gộp chúng thành lỗi đầu vào chung rồi vô tình tiết lộ thông tin nhạy cảm.

## 8. Kiểm thử đúng hành vi thất bại

Một bộ kiểm thử tốt cần xác nhận **đúng loại lỗi**, **không tạo tác dụng phụ không cần thiết** và **giữ được nguyên nhân kỹ thuật** để điều tra.

Ví dụ JUnit 5 cho lớp StockCheckService:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class StockCheckServiceTest {
    @Test
    void invalidInputStopsBeforeCallingInventory() {
        AtomicInteger calls = new AtomicInteger();
        StockCheckService.InventoryGateway gateway = code -> {
            calls.incrementAndGet();
            return new StockCheckService.StockInfo(true, 5);
        };

        StockCheckService service = new StockCheckService(gateway);

        assertThrows(StockCheckService.InvalidInputException.class,
                () -> service.check("", 2));
        assertEquals(0, calls.get());
    }

    @Test
    void insufficientStockIsBusinessRejection() {
        StockCheckService service = new StockCheckService(
                code -> new StockCheckService.StockInfo(true, 2));

        assertThrows(StockCheckService.BusinessRejectedException.class,
                () -> service.check("SKU-1", 3));
    }

    @Test
    void infrastructureFailureKeepsItsCause() {
        StockCheckService service = new StockCheckService(code -> {
            throw new StockCheckService.InventoryUnavailableException("timeout");
        });

        var failure = assertThrows(
                StockCheckService.DependencyFailureException.class,
                () -> service.check("SKU-1", 3));

        assertInstanceOf(
                StockCheckService.InventoryUnavailableException.class,
                failure.getCause());
    }

    @Test
    void availableStockAllowsCheckToComplete() {
        StockCheckService service = new StockCheckService(
                code -> new StockCheckService.StockInfo(true, 5));

        assertDoesNotThrow(() -> service.check("SKU-1", 3));
    }
}
~~~

Bốn ca trên **minh họa** các nhóm kết quả. Cần bổ sung các giá trị biên, mã null, số lượng vượt 10, sản phẩm không bán, sản phẩm không tồn tại và những lỗi phụ thuộc khác theo hợp đồng.

Nếu hệ thống có thao tác **ghi**, cần kiểm thử tích hợp với các tình huống: hai yêu cầu đồng thời, timeout sau khi phía nhận đã ghi, retry cùng idempotency key, transaction thất bại giữa chừng và cơ chế khôi phục. Mock ném ngoại lệ đơn thuần chưa đủ chứng minh các tính chất này.

## 9. Logging và giám sát theo đúng nguyên nhân

Khi quan sát hệ thống, cần phân biệt lỗi do client, nghiệp vụ và hạ tầng để đội ngũ vận hành phản ứng chính xác.

| Tín hiệu | Công dụng |
| --- | --- |
| Tỷ lệ lỗi đầu vào theo endpoint/trường | Phát hiện client sai hợp đồng hoặc API khó sử dụng. |
| Số lượt từ chối nghiệp vụ theo lý do | Hiểu tình trạng hết hàng, giới hạn giao dịch, khuyến mãi. |
| Timeout, lỗi kết nối, latency và error rate phụ thuộc | Nhận diện sự cố hạ tầng và mức ảnh hưởng. |
| Exception không dự kiến, lỗi 5xx và lỗi bất biến | Điều tra lỗi chương trình hoặc tương tác thành phần bất thường. |

Ví dụ log có cấu trúc:

~~~text
level=ERROR
event=inventory_lookup_failed
requestId=req-8f1a
dependency=inventory
errorType=TIMEOUT
attempt=1
elapsedMs=1200
~~~

Không log dữ liệu thanh toán hay dữ liệu cá nhân một cách tùy tiện. Một lỗi đầu vào thông thường có thể là sự kiện cần thống kê nhưng không cần cảnh báo khẩn cấp; một lỗi hạ tầng cần được nhìn thấy kể cả khi cơ chế fallback khiến người dùng chưa cảm nhận ảnh hưởng.

Khi có cơ chế retry, cần ghi nhận **tổng số lần thử** và **kết quả cuối**, tránh đếm mỗi lần thử thất bại như một yêu cầu người dùng thất bại độc lập.

## 10. Quy trình xử lý khi thao tác không thành công

1. **Đối chiếu hợp đồng:** Đầu vào nào hợp lệ? Quy tắc nào phải được giữ? Phụ thuộc nào cần hoạt động?
2. **Thu thập bằng chứng:** Kiểm tra dữ liệu đầu vào, trạng thái liên quan, exception cause, request ID, log và metric.
3. **Phân loại:** Phía gửi cần sửa, quy tắc nghiệp vụ từ chối, hay hệ thống chưa thể đưa ra kết quả tin cậy?
4. **Giữ bất biến:** Không ghi dữ liệu nửa chừng; không tạo tác dụng phụ lặp; không tự động cho phép thao tác quan trọng khi mất dữ liệu xác thực.
5. **Phản hồi phù hợp:** Lỗi validation rõ ràng, lý do nghiệp vụ cụ thể, hoặc thông báo lỗi phụ thuộc có thể theo dõi.
6. **Phục hồi có điều kiện:** Giới hạn timeout; chỉ retry nếu an toàn; giữ dấu vết giao dịch; có phương án đối soát khi kết quả chưa xác định.
7. **Kiểm tra lại:** Thử các ca lỗi có chủ đích và xác nhận hệ thống giữ trạng thái đúng sau thất bại.

Đặc biệt với giao dịch có tác dụng phụ, hãy luôn hỏi: **“Nếu phản hồi bị mất sau khi phía nhận đã xử lý thành công, làm thế nào biết có nên thực hiện lại?”**. Nếu chưa có câu trả lời, retry có thể chưa an toàn.

## 11. Tình huống tự luyện

**Tình huống A.** Client gửi số lượng bằng 0, service trả “Service temporarily unavailable”.

**Phân tích:** Đây là đầu vào không hợp lệ. Phản hồi nên chỉ rõ số lượng phải dương, thay vì quy trách nhiệm cho hạ tầng.

**Tình huống B.** Client yêu cầu 3 món. Kho đáng tin cậy cho biết chỉ còn 1.

**Phân tích:** Đây là từ chối theo trạng thái nghiệp vụ. Có thể hướng dẫn giảm số lượng hoặc chọn sản phẩm khác.

**Tình huống C.** Client yêu cầu 3 món. Dịch vụ kho timeout, service trả “Out of stock”.

**Phân tích:** Kết luận thiếu căn cứ. Cần báo tình trạng chưa xác định được do phụ thuộc và giữ riêng tín hiệu kỹ thuật.

**Tình huống D.** API tạo đơn timeout. Phía gọi gửi lại với định danh mới, và hệ thống tạo hai đơn.

**Phân tích:** Timeout không chứng minh thao tác đầu tiên chưa xảy ra. Cần thiết kế idempotency, định danh giao dịch và kiểm tra trạng thái trước khi xử lý lặp.

**Tình huống E.** Khi CSDL lỗi, một phương thức quyết định có được giao dịch không bắt exception rồi trả true để “trải nghiệm mượt hơn”.

**Phân tích:** Mặc định cho phép khi không đủ căn cứ có thể vi phạm giới hạn nghiệp vụ. Cần xác định chính sách an toàn khi dữ liệu không khả dụng, thường là tạm từ chối hoặc báo chưa thể xác nhận.

---

**Ghi nhớ:** Với **lỗi đầu vào**, giúp phía gửi sửa yêu cầu. Với **lỗi nghiệp vụ**, từ chối theo đúng quy tắc và bảo vệ trạng thái hợp lệ. Với **lỗi hạ tầng**, không suy diễn dữ liệu chưa biết thành kết luận chắc chắn; hãy quan sát, giới hạn tác động và phục hồi có kiểm soát. Phân biệt ba nhóm lỗi giúp mã đáng tin cậy, dễ kiểm thử và dễ thay đổi hơn.
