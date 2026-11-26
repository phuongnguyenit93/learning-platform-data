# Tổ chức mức trừu tượng, hợp đồng công khai và chi tiết nội bộ

Trong chương **Ranh giới và quy tắc phân tầng**, bài học này tập trung vào cách một tầng trình bày năng lực của mình cho tầng khác sử dụng. Với module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, mục tiêu là tổ chức phần mềm theo kiến trúc phân tầng: mỗi tầng xử lý một loại trách nhiệm, cung cấp một bề mặt sử dụng có chủ đích và giữ các quyết định triển khai bên trong ranh giới của nó.

Một kiến trúc có nhiều package hoặc nhiều lớp Java chưa chắc đã có ranh giới tốt. Ranh giới chỉ rõ khi người gọi biết mình được phép yêu cầu điều gì, hiểu kết quả và cam kết đi kèm, nhưng không phải biết tầng được gọi lưu dữ liệu ra sao, chọn thuật toán nào hay chia nhỏ công việc nội bộ như thế nào. Đó là mối quan hệ giữa **mức trừu tượng**, **hợp đồng công khai** và **chi tiết nội bộ**.

Sau bài học, bạn có thể:

- Nhận ra khi một API đang bộc lộ đúng mức trừu tượng hoặc làm rò rỉ chi tiết của tầng bên dưới.
- Xác định nội dung nào thuộc hợp đồng giữa hai tầng và nội dung nào nên được đóng gói bên trong.
- Thiết kế ví dụ luồng xử lý trong ứng dụng Java/Spring sao cho các tầng giao tiếp qua những kiểu dữ liệu và thao tác có ý nghĩa.
- Đánh giá thay đổi hợp đồng, cách kiểm thử ranh giới và chi phí của việc tạo quá nhiều lớp trừu tượng.

## 1. Mức trừu tượng là gì?

Mức trừu tượng mô tả một thành phần bằng **mục đích và trách nhiệm của nó**, thay vì bằng các bước kỹ thuật chi tiết để thực hiện mục đích đó. Trong ứng dụng phân tầng, cùng một yêu cầu được diễn đạt khác nhau ở các tầng:

| Vị trí | Câu hỏi mà tầng cần giải quyết | Ví dụ cách diễn đạt |
|---|---|---|
| Trình bày (presentation) | Người dùng hoặc hệ thống bên ngoài gửi yêu cầu theo cách nào? | Nhận HTTP POST `/orders`, đọc JSON và trả HTTP 201. |
| Điều phối ứng dụng (application) | Ca sử dụng cần phối hợp những việc gì? | Đặt hàng, kiểm tra điều kiện, lưu đơn và trả kết quả. |
| Nghiệp vụ (domain/business) | Quy tắc nào quyết định trạng thái hợp lệ? | Đơn hàng chỉ được xác nhận khi các điều kiện đặt hàng được đáp ứng. |
| Truy cập dữ liệu (data access) | Dữ liệu được đọc và ghi qua cơ chế nào? | Chuyển đối tượng thành bản ghi và thực hiện thao tác với cơ sở dữ liệu. |

Đây là các vai trò thường gặp, không phải quy định rằng mọi hệ thống phải có đúng bốn tầng hoặc phải đặt mỗi vai trò trong một tiến trình riêng. Một ứng dụng nhỏ có thể gộp một số trách nhiệm trong cùng module; một hệ thống lớn có thể chia nhỏ chúng hơn. Điều cần giữ là mỗi ranh giới có mục đích rõ ràng và không khiến tầng gọi phải hiểu cách tầng được gọi triển khai.

Một phương thức ở tầng ứng dụng nên mô tả ca sử dụng, chẳng hạn `placeOrder(command)`. Nếu phương thức này buộc tầng trình bày phải tự mở kết nối JDBC, chọn bảng, tạo câu SQL rồi gọi từng bước nghiệp vụ, thì mức trừu tượng đã bị kéo xuống quá thấp. Ngược lại, một adapter truy cập dữ liệu không nên nhận một yêu cầu HTTP hay tự quyết định mã trạng thái HTTP; đó là khái niệm thuộc tầng trình bày.

### Giữ một mức trừu tượng nhất quán

Trong cùng một API, các thao tác nên nói về cùng một loại ý định. Ví dụ, một giao diện đặt hàng có thể cung cấp thao tác `execute(PlaceOrderCommand)`. Nếu cùng giao diện đó còn cung cấp `openEntityManager()`, `buildInsertSql()` hoặc `setHttpStatus()`, nó đã trộn lẫn ca sử dụng với cơ chế lưu trữ và giao thức trình bày.

Mức trừu tượng không có nghĩa là mọi phương thức phải thật lớn hoặc chỉ có một câu lệnh. Nó có nghĩa là người gọi được làm việc với khái niệm phù hợp với trách nhiệm của họ. Một tầng có thể dùng nhiều lớp và nhiều hàm trợ giúp nội bộ để thực hiện hợp đồng đơn giản bên ngoài.

## 2. Hợp đồng công khai của một tầng

Hợp đồng công khai là phần bề mặt mà một thành phần chủ động cho thành phần khác sử dụng. Hợp đồng trả lời ít nhất bốn câu hỏi:

1. **Có thể yêu cầu điều gì?** Tên thao tác, mục đích và điều kiện đầu vào.
2. **Cần cung cấp gì?** Kiểu dữ liệu, trường bắt buộc, quy tắc hợp lệ và ý nghĩa của các giá trị.
3. **Nhận lại điều gì?** Kết quả thành công, kết quả không thành công hoặc các lỗi mà bên gọi có thể xử lý.
4. **Cam kết nào đi kèm?** Các tác dụng phụ, tính nguyên tử, tính nhất quán, giới hạn thời gian hoặc quy tắc tương thích nếu chúng có ý nghĩa với bên gọi.

Một hợp đồng tốt mô tả hành vi quan sát được. Chỉ ghi chữ ký phương thức là chưa đủ nếu bên gọi vẫn phải đoán xem thao tác có lưu dữ liệu hay không, có thể trả về giá trị rỗng không, lỗi nào có thể xảy ra hoặc gọi lặp lại có tạo ra hai đơn hàng không.

Ví dụ, tầng ứng dụng có thể công bố một ca sử dụng đặt hàng:

~~~java
import java.math.BigDecimal;
import java.util.List;

public interface PlaceOrder {
    OrderReceipt execute(PlaceOrderCommand command);
}

public record PlaceOrderCommand(
        String customerId,
        List<OrderLine> lines
) {
    public record OrderLine(String productId, int quantity) {}
}

public record OrderReceipt(
        String orderId,
        BigDecimal total
) {}
~~~

Trong thiết kế này, bên gọi biết rằng nó cần cung cấp thông tin đặt hàng và sẽ nhận mã đơn cùng tổng tiền. Hợp đồng thực tế cần quy định thêm các điều kiện nghiệp vụ, cách biểu diễn lỗi và những cam kết liên quan đến việc tạo đơn. Các kiểu dữ liệu trên là ví dụ minh họa; dự án có thể dùng lớp DTO, kiểu kết quả hoặc cơ chế lỗi khác phù hợp với quy ước của mình.

Hợp đồng không nhất thiết phải là một Java `interface`. Nó có thể là một API REST, một lớp public được module cho phép sử dụng, một sự kiện, hoặc một tập thao tác được tài liệu hóa. Interface hữu ích khi cần tách người gọi khỏi lớp triển khai hoặc thay thế triển khai trong kiểm thử. Tuy nhiên, tạo interface cho mọi lớp mà không có nhu cầu về ranh giới sẽ làm tăng số kiểu phải đọc và bảo trì.

### Hợp đồng kiến trúc không đồng nghĩa với từ khóa `public`

Trong Java, `public` là quy tắc truy cập của ngôn ngữ. Hợp đồng kiến trúc là quyết định về việc thành phần nào được phép phụ thuộc vào phần nào và phần nào được cam kết duy trì. Một lớp `public` có thể chỉ là chi tiết nội bộ do quy ước package, module hoặc tài liệu dự án quy định. Ngược lại, một API HTTP hoặc thông điệp sự kiện có thể là hợp đồng công khai giữa các hệ thống dù không có interface Java nào.

Vì vậy, khi xác định bề mặt công khai, cần xem xét cả cấu trúc package/module, cấu hình xuất package nếu dùng Java Platform Module System, các quy tắc truy cập trong mã nguồn, tài liệu API và cách các module khác được phép tham chiếu. Không nên suy ra rằng mọi thành viên có thể truy cập về mặt cú pháp đều là API ổn định.

## 3. Chi tiết nội bộ cần được đóng gói

Chi tiết nội bộ là những quyết định có thể thay đổi mà không buộc bên gọi thay đổi cách sử dụng hợp đồng. Tùy tầng, chúng có thể bao gồm:

- Cách chia một ca sử dụng thành các bước nhỏ, các hàm private và lớp trợ giúp.
- Thuật toán, cấu trúc dữ liệu tạm, cache và cách tối ưu hiệu năng.
- Câu SQL, tên bảng/cột, mapping ORM, entity lưu trữ và cấu hình kết nối.
- Thư viện cụ thể, cách retry, cách ghi log và chi tiết triển khai giao dịch.
- Cách chuyển đổi giữa mô hình nội bộ với DTO hoặc kiểu dữ liệu được công bố.

Đóng gói không có nghĩa là che giấu mọi thông tin. Bên gọi vẫn cần biết những điều ảnh hưởng đến hành vi của nó. Chẳng hạn, nếu thao tác có thể thất bại do hết hàng, lỗi đó phải được thể hiện qua hợp đồng để tầng trình bày hoặc tầng điều phối cao hơn có thể phản hồi phù hợp. Nhưng bên gọi không cần biết hệ thống kiểm tra tồn kho bằng câu SQL nào hoặc dữ liệu nằm ở bảng nào.

### Tránh để lộ mô hình lưu trữ

Giả sử controller trả trực tiếp một đối tượng JPA entity. Khi đó, cấu trúc bảng, quan hệ lazy/eager, trường kỹ thuật và quy tắc mapping có thể vô tình trở thành một phần của API HTTP. Một thay đổi trong cơ sở dữ liệu có thể làm hỏng client dù ý nghĩa nghiệp vụ không thay đổi. Ngoài ra, serialization có thể kích hoạt truy vấn ngoài dự kiến hoặc làm lộ trường không dành cho người dùng.

Có thể giữ ranh giới bằng cách chuyển đổi dữ liệu tại tầng phù hợp:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {
    private final PlaceOrder placeOrder;

    OrderController(PlaceOrder placeOrder) {
        this.placeOrder = placeOrder;
    }

    @PostMapping
    ResponseEntity<OrderResponse> create(
            @RequestBody CreateOrderRequest request) {
        var command = new PlaceOrderCommand(
                request.customerId(), request.lines());
        var receipt = placeOrder.execute(command);
        var response = new OrderResponse(
                receipt.orderId(), receipt.total());
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
~~~

Controller hiểu HTTP request/response và chuyển đổi chúng sang hợp đồng của ca sử dụng. Controller không cần biết dịch vụ ứng dụng dùng JPA, JDBC hay một hệ thống lưu trữ khác. `CreateOrderRequest` và `OrderResponse` là kiểu dành cho API trình bày; chúng có thể khác với `PlaceOrderCommand` và `OrderReceipt` của tầng ứng dụng khi nhu cầu của hai ranh giới khác nhau.

Ở phía lưu trữ, một hợp đồng có thể mô tả thao tác theo ngôn ngữ của ứng dụng:

~~~java
public interface OrderStore {
    void save(Order order);
}

@Repository
class JpaOrderStore implements OrderStore {
    private final SpringDataOrderRepository repository;

    JpaOrderStore(SpringDataOrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void save(Order order) {
        repository.save(OrderEntity.from(order));
    }
}
~~~

Ví dụ trên minh họa adapter chuyển mô hình mà ứng dụng sử dụng sang entity mà ORM quản lý. Tầng gọi `OrderStore` không cần biết tên bảng hoặc Spring Data repository. Trong một thiết kế cụ thể, hợp đồng lưu trữ có thể thuộc module ứng dụng/nghiệp vụ và adapter JPA triển khai nó; vị trí chính xác phụ thuộc vào quy tắc phụ thuộc của hệ thống. Không cần áp dụng một mô hình DDD hay một cách đặt interface duy nhất cho mọi dự án.

## 4. Luồng giao tiếp qua hợp đồng

Một luồng đặt hàng trong ứng dụng Spring có thể được tổ chức như sau:

~~~mermaid
flowchart TD
    A[HTTP client] --> B[OrderController]
    B -->|PlaceOrderCommand| C[Hợp đồng PlaceOrder]
    C --> D[DefaultPlaceOrder]
    D -->|OrderStore| H[Hợp đồng OrderStore]
    H --> E[JpaOrderStore]
    E --> F[Spring Data / JPA]
    F --> G[(Database)]
    D -->|OrderReceipt| C
    C -->|OrderReceipt| B
    B -->|OrderResponse / HTTP 201| A
~~~

Mỗi bước giao tiếp cần dùng ngôn ngữ của ranh giới tương ứng:

- Controller chuyển giao thức HTTP thành yêu cầu của ca sử dụng và chuyển kết quả thành phản hồi HTTP.
- Dịch vụ ứng dụng điều phối ca sử dụng và gọi các hợp đồng cần thiết.
- Thành phần nghiệp vụ thực thi quy tắc nghiệp vụ bằng các khái niệm phù hợp với miền bài toán.
- Adapter dữ liệu chuyển đổi giữa mô hình ứng dụng và cơ chế lưu trữ cụ thể.

Trong một ứng dụng phân tầng cổ điển, tầng trên thường gọi bề mặt được công bố của tầng dưới. Khi áp dụng dependency inversion, hợp đồng của một chính sách cấp cao có thể được đặt ở module cấp cao và adapter cấp thấp triển khai hợp đồng đó. Hai cách tổ chức có thể khác nhau về vị trí khai báo interface, nhưng đều cần làm rõ ai sở hữu hợp đồng, ai được phụ thuộc vào nó và chi tiết nào bị giữ bên trong.

Một quy tắc hữu ích là **không đi xuyên qua ranh giới của tầng khác để thao tác trực tiếp với chi tiết nội bộ**. Ví dụ, controller không nên lấy `EntityManager` để cập nhật đơn hàng, hoặc truy cập thẳng repository JPA chỉ vì cần một trường dữ liệu. Nếu ca sử dụng cần thông tin đó, hãy bổ sung một thao tác phù hợp vào hợp đồng mà controller đang sử dụng, rồi để tầng sở hữu trách nhiệm thực hiện.

## 5. Những quy tắc thực tế để giữ ranh giới

### Công bố ý định, không công bố cơ chế

Tên thao tác và kiểu dữ liệu nên phản ánh điều bên gọi muốn đạt được. `findActiveOrders(customerId)` diễn đạt nhu cầu ở mức ứng dụng rõ hơn `selectFromOrderWhereStatusEquals(...)`. Câu SQL là cơ chế của adapter lưu trữ; nó có thể thay đổi mà không làm đổi ý nghĩa của ca sử dụng.

### Giữ kiểu dữ liệu ở đúng ranh giới

Không đưa kiểu chỉ có ý nghĩa trong một framework hoặc tầng vào hợp đồng rộng hơn nếu bên gọi không cần nó. Ví dụ, tránh trả `JpaRepository`, `EntityManager`, `HttpServletRequest` hoặc JPA entity qua hợp đồng tầng ứng dụng. Dùng command, result, DTO hoặc kiểu nghiệp vụ có ý nghĩa ổn định hơn. Cũng không cần tạo một DTO mới cho mọi phương thức nếu kiểu hiện có đã diễn đạt đúng hợp đồng và không làm lộ chi tiết.

### Định nghĩa rõ lỗi và kết quả

Bên gọi cần biết lỗi nào có thể xảy ra và phải phản ứng ra sao. Có thể dùng exception theo ngữ nghĩa nghiệp vụ, kiểu kết quả có trạng thái, hoặc một quy ước khác. Tầng trình bày có thể ánh xạ lỗi nghiệp vụ sang HTTP 4xx; lỗi hạ tầng có thể được xử lý theo chính sách lỗi hệ thống. Không nên buộc controller phân tích thông điệp lỗi SQL hoặc tên exception riêng của ORM.

### Không tạo phụ thuộc vòng

Nếu tầng A cần gọi B và B lại cần gọi trực tiếp A, hợp đồng và trách nhiệm có thể đang đặt sai chỗ. Hãy xem lại luồng điều phối, tách một chính sách dùng chung vào vị trí hợp lý hoặc thay đổi cách trao đổi dữ liệu. Phụ thuộc vòng làm khó kiểm thử, khó khởi tạo và khó thay đổi riêng từng tầng.

### Không truyền chi tiết nội bộ ra ngoài qua tác dụng phụ

Một API có thể có chữ ký gọn nhưng vẫn rò rỉ chi tiết qua việc sửa một đối tượng mutable mà bên gọi giữ tham chiếu, phụ thuộc vào thứ tự gọi, yêu cầu mở transaction trước, hoặc trả về một stream gắn với kết nối đã đóng. Những điều kiện ảnh hưởng đến người gọi phải được loại bỏ hoặc mô tả rõ trong hợp đồng.

### Thay đổi hợp đồng có chủ đích

Khi sửa kiểu đầu vào, kiểu trả về, ý nghĩa lỗi hoặc hành vi của thao tác, hãy kiểm tra tất cả bên gọi. Thêm trường bắt buộc, đổi đơn vị tiền tệ, thay đổi cách phân trang hoặc đổi ý nghĩa của giá trị null đều có thể là thay đổi không tương thích dù chữ ký nhìn qua ít thay đổi. Với API bên ngoài, cân nhắc phiên bản hoặc giai đoạn chuyển tiếp; với module nội bộ, cập nhật các consumer và kiểm thử hợp đồng cùng lúc.

## 6. Kiểm thử ranh giới và hợp đồng

Kiểm thử nên xác nhận hành vi quan sát được qua hợp đồng. Không cần kiểm tra mọi hàm private hoặc buộc test biết cấu trúc nội bộ của lớp triển khai.

| Vị trí kiểm thử | Điều cần xác nhận | Ví dụ |
|---|---|---|
| Controller | Ánh xạ giao thức và dữ liệu đúng | Request hợp lệ tạo command đúng; kết quả ca sử dụng được chuyển thành response và mã HTTP phù hợp. |
| Dịch vụ ứng dụng | Điều phối và quy tắc của ca sử dụng | Khi đặt hàng hợp lệ, lưu đơn và trả receipt; khi vi phạm điều kiện, trả lỗi theo hợp đồng. |
| Adapter dữ liệu | Hợp đồng được thực hiện đúng với công nghệ lưu trữ | Lưu và đọc lại dữ liệu qua JPA trên cơ sở dữ liệu kiểm thử. |
| Kiểm thử tích hợp | Các ranh giới phối hợp đúng trong ứng dụng | Request đi qua controller, dịch vụ và adapter, cho kết quả đúng với dữ liệu được lưu. |

Trong unit test của dịch vụ ứng dụng, có thể thay `OrderStore` bằng fake hoặc mock để kiểm tra hành vi mà không cần khởi động cơ sở dữ liệu. Trong integration test của `JpaOrderStore`, nên dùng cơ sở dữ liệu kiểm thử phù hợp để xác nhận mapping và truy vấn. Nếu nhiều triển khai phải tuân thủ cùng một hợp đồng, có thể dùng một bộ contract test chạy trên từng triển khai.

Một dấu hiệu của ranh giới tốt là có thể thay đổi cách lưu trữ hoặc cách chia nhỏ lớp nội bộ mà phần lớn test của consumer vẫn giữ nguyên. Nếu một thay đổi tên cột khiến hàng loạt test controller thất bại, có thể tầng trình bày đang phụ thuộc quá sâu vào chi tiết lưu trữ.

## 7. Ví dụ về rò rỉ trừu tượng và cách sửa

| Thiết kế gây rò rỉ | Hệ quả | Cách tổ chức lại |
|---|---|---|
| Controller gọi trực tiếp `JpaRepository` để hoàn thành ca sử dụng. | Quy tắc và điều phối bị phân tán; controller biết công nghệ lưu trữ. | Controller gọi hợp đồng ca sử dụng; dịch vụ ứng dụng điều phối thao tác dữ liệu. |
| Tầng ứng dụng trả JPA entity cho client. | Schema lưu trữ và quan hệ ORM trở thành một phần của API. | Chuyển kết quả thành kiểu phản hồi ổn định tại ranh giới trình bày. |
| Hợp đồng yêu cầu bên gọi truyền `HttpServletRequest` xuống tầng nghiệp vụ. | Tầng nghiệp vụ bị gắn với HTTP và khó dùng trong tác vụ nền hoặc giao diện khác. | Chuyển thông tin cần thiết thành command hoặc kiểu dữ liệu độc lập giao thức. |
| Adapter dữ liệu trả lỗi SQL thô cho controller. | Controller phải hiểu chi tiết cơ sở dữ liệu. | Ánh xạ lỗi tại tầng sở hữu ngữ nghĩa và công bố kết quả/lỗi theo hợp đồng. |
| Mỗi lớp nội bộ đều có interface dù chỉ có một consumer và không có nhu cầu thay thế. | Số lượng kiểu tăng nhưng ranh giới không rõ hơn. | Chỉ tạo hợp đồng ở nơi có consumer, nhu cầu kiểm thử, thay thế hoặc ranh giới module thực sự. |

Hãy lưu ý rằng một lớp gọi trực tiếp một lớp khác không tự động là sai. Vấn đề xuất hiện khi lời gọi vượt qua trách nhiệm đã định, khiến consumer phụ thuộc vào chi tiết dễ thay đổi hoặc làm ranh giới không thể diễn đạt bằng một hợp đồng rõ ràng.

## 8. Cân bằng giữa đóng gói và chi phí trừu tượng

Tách hợp đồng và triển khai đem lại khả năng thay đổi nội bộ, kiểm thử độc lập và giới hạn phạm vi ảnh hưởng. Đổi lại, hệ thống có thể phát sinh thêm interface, DTO, mapper, adapter và bước chuyển đổi dữ liệu. Nếu mọi lời gọi đơn giản đều phải đi qua nhiều lớp chỉ để chuyển tiếp tham số, kiến trúc trở nên khó theo dõi.

Nên đầu tư vào một hợp đồng riêng khi có ít nhất một lý do cụ thể: nhiều consumer cần dùng chung năng lực; tầng triển khai có khả năng thay đổi; ranh giới module cần được bảo vệ; cần thay adapter trong kiểm thử; hoặc hợp đồng có ý nghĩa ổn định hơn chi tiết triển khai. Nếu một helper chỉ được dùng bên trong một lớp, phương thức private có thể là lựa chọn đủ tốt. Nếu một module có một API ổn định nhưng chỉ có một triển khai, vẫn có thể cần hợp đồng rõ ràng; số lượng triển khai không phải tiêu chí duy nhất.

Không nên đánh đồng tầng logic với tier triển khai. Các tầng trình bày, ứng dụng, nghiệp vụ và dữ liệu có thể là các package/module chạy trong cùng một ứng dụng Spring. Một hệ thống cũng có thể triển khai nhiều tầng trên các máy chủ khác nhau, nhưng việc tách tiến trình không tự động tạo ra hợp đồng tốt. Hợp đồng cần được thiết kế ở cấp kiến trúc trước khi quyết định ranh giới triển khai.

## 9. Tự rà soát thiết kế

Khi xem một ranh giới giữa hai tầng, hãy thử trả lời các câu hỏi sau:

1. Consumer đang diễn đạt nhu cầu bằng khái niệm thuộc trách nhiệm của nó hay bằng chi tiết của tầng được gọi?
2. Hợp đồng có mô tả đầu vào, kết quả, lỗi và cam kết quan trọng đủ rõ để consumer sử dụng mà không phải đọc mã triển khai không?
3. Nếu thay JPA bằng JDBC, đổi câu SQL hoặc thay thuật toán nội bộ, consumer có phải sửa không? Nếu có, sự phụ thuộc đó có thực sự cần thiết không?
4. Kiểu dữ liệu được trao đổi có mang theo framework, giao thức hoặc cấu trúc lưu trữ mà consumer không cần biết không?
5. Có lời gọi nào đi xuyên qua một tầng, phụ thuộc vòng hoặc truy cập trực tiếp chi tiết nội bộ không?
6. Hợp đồng có đủ giá trị để biện minh cho interface, DTO và mapper bổ sung không?
7. Có thể kiểm thử hành vi qua hợp đồng mà không khóa test vào cấu trúc lớp nội bộ không?

Nếu câu trả lời cho thấy consumer phải hiểu cơ chế của tầng khác, hãy xem lại hợp đồng và nơi đặt trách nhiệm. Nếu hợp đồng quá rộng, chứa nhiều thao tác không cùng mục đích hoặc buộc nhiều consumer phụ thuộc vào những phần chúng không dùng, hãy chia nhỏ bề mặt công khai theo nhóm trách nhiệm thực tế.

## Kết luận

Một tầng được tổ chức tốt cung cấp cho consumer một hợp đồng diễn đạt đúng ý định ở mức trừu tượng phù hợp, đồng thời giữ các quyết định triển khai bên trong ranh giới của mình. Hãy làm rõ hành vi mà hợp đồng cam kết, dùng kiểu dữ liệu phù hợp với ranh giới, ngăn consumer đi xuyên tầng và chỉ tạo thêm lớp trừu tượng khi nó giải quyết một nhu cầu thực tế. Những quy tắc này giúp phần mềm phân tầng dễ hiểu, dễ kiểm thử và có thể thay đổi từng phần mà không kéo theo các tầng không liên quan.
