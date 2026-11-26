# Chọn đơn vị công việc ở tầng dịch vụ

Một thao tác nghiệp vụ thường cần nhiều lần đọc và ghi dữ liệu. Khi đặt hàng, ứng dụng có thể phải kiểm tra sản phẩm, giữ tồn kho và tạo đơn hàng. Nếu mỗi lần gọi repository được coi là một công việc độc lập, lỗi ở bước cuối có thể để lại dữ liệu đã thay đổi ở bước trước.

Trong chương **Ranh giới giao dịch** của module **SPRING_DATA_COMMONS**, bài học này giải thích cách chọn một đơn vị công việc ở tầng dịch vụ: xác định dữ liệu nào phải nhất quán cùng nhau, đặt transaction quanh phần xử lý tương ứng và nhận biết giới hạn của store đang sử dụng. Các abstraction Repository, CRUD, truy vấn, projection hay auditing giúp thao tác dữ liệu; chúng không tự quyết định ranh giới hoàn thành của một yêu cầu nghiệp vụ.

## 1. Đơn vị công việc bắt đầu từ kết quả nghiệp vụ

**Đơn vị công việc** trong bài này là tập hợp những thay đổi mà nghiệp vụ muốn xác nhận thành công cùng nhau hoặc hủy bỏ cùng nhau trong phạm vi tài nguyên có thể tham gia transaction đó.

Nó không mặc định bằng:

- Một câu SQL.
- Một lần gọi `save()`.
- Một repository.
- Một HTTP request.
- Toàn bộ vòng đời của một quy trình kéo dài nhiều phút.

Ví dụ, yêu cầu “tạo đơn hàng chờ thanh toán và giữ đủ hàng cho đơn” có thể có bất biến:

> Khi thao tác đặt hàng được commit thành công, đơn hàng chờ thanh toán tồn tại và lượng tồn khả dụng đã giảm đúng số lượng của đơn. Khi thao tác thất bại trước khi commit, không giữ lại riêng một trong hai thay đổi đó.

Từ bất biến này, ta xác định một transaction cục bộ gồm việc kiểm tra trạng thái liên quan, giữ hàng và lưu đơn. Việc người mua thanh toán vào ngày hôm sau là một bước nghiệp vụ khác, không phải lý do để giữ transaction cơ sở dữ liệu mở qua đêm.

### 1.1. Phân biệt đơn vị công việc nghiệp vụ và persistence context

Trong JPA, persistence context theo dõi entity và thay đổi của chúng; khái niệm Unit of Work cũng thường được dùng để nói về cơ chế theo dõi, đồng bộ thay đổi này. Tuy nhiên, sự tồn tại của persistence context không tự chứng minh toàn bộ use case đã nằm trong một transaction đúng nghĩa.

Khi thiết kế tầng dịch vụ, cần trả lời riêng hai câu hỏi:

1. Những thay đổi nào phải thành công cùng nhau theo nghiệp vụ?
2. Những thay đổi đó thực sự được transaction manager và tài nguyên bên dưới phối hợp như thế nào?

Không dùng việc “entity vẫn còn truy cập được” làm bằng chứng rằng transaction ghi vẫn đang mở.

## 2. Vì sao tầng dịch vụ phù hợp để đặt ranh giới?

Repository diễn đạt thao tác với tập đối tượng lưu trữ: tìm theo ID, lưu, xóa hoặc thực hiện truy vấn được store hỗ trợ. Tầng dịch vụ thường nhìn thấy đủ ngữ cảnh để phối hợp các thao tác đó thành một ca sử dụng.

```text
Controller hoặc adapter nhận yêu cầu
                |
                v
Dịch vụ ứng dụng: placeOrder
    +--------------------------------------+
    | Bắt đầu transaction                  |
    | Đọc sản phẩm                         |
    | Kiểm tra và giữ tồn kho              |
    | Lưu sản phẩm                         |
    | Lưu đơn hàng chờ thanh toán          |
    | Commit nếu toàn bộ phần việc hợp lệ  |
    +--------------------------------------+
                |
                v
Trả kết quả cho bên gọi
```

Nếu hai lần `save()` nằm trong hai transaction độc lập, việc mỗi lần ghi đều có transaction không bảo đảm tính nguyên tử của toàn bộ use case.

```text
Transaction A: giảm tồn kho -> COMMIT
Transaction B: tạo đơn hàng -> lỗi -> ROLLBACK

Kết quả: đã giữ hàng nhưng không có đơn tương ứng.
```

Với một transaction chung, nếu cả hai thao tác thực sự tham gia cùng transaction và lỗi dẫn tới rollback, cả phần giảm tồn lẫn tạo đơn đều được hủy.

Điều này không yêu cầu đưa mọi logic vào một lớp dịch vụ lớn. Có thể tách logic tính toán và quy tắc domain thành nhiều đối tượng; phương thức dịch vụ vẫn điều phối ranh giới hoàn thành của use case.

## 3. Xác định ranh giới bằng năm câu hỏi

Trước khi đặt `@Transactional`, hãy viết rõ hợp đồng của thao tác.

| Câu hỏi | Ví dụ cho `placeOrder` | Ảnh hưởng tới ranh giới |
| --- | --- | --- |
| Khi nào được coi là thành công? | Có đơn chờ thanh toán và đã giữ đủ hàng | Cần xác nhận hai thay đổi cùng nhau |
| Trạng thái trung gian nào không được phép tồn tại sau lỗi? | Giảm tồn mà không có đơn | Không tách hai lần ghi thành transaction độc lập |
| Quyết định phụ thuộc dữ liệu nào? | Số lượng tồn và trạng thái sản phẩm | Đọc và kiểm tra dữ liệu liên quan phải gắn với chiến lược cạnh tranh phù hợp |
| Tài nguyên nào tham gia? | Hai bảng trong cùng cơ sở dữ liệu quan hệ | Có thể dùng một transaction cục bộ nếu cấu hình phù hợp |
| Có chờ người dùng hoặc hệ thống ngoài không? | Thanh toán và email | Tách thành các bước có trạng thái, retry và cơ chế phối hợp riêng |

### 3.1. Bắt đầu đủ sớm

Đọc tồn kho ngoài transaction rồi mở transaction chỉ để lưu không loại bỏ được việc dữ liệu đã thay đổi giữa hai thời điểm.

```text
Đọc tồn = 5
      |
      | Một yêu cầu khác đã giữ 4 sản phẩm
      v
Mở transaction, quyết định vẫn dựa trên tồn = 5
```

Đặt bước đọc liên quan trong transaction giúp tổ chức một đơn vị công việc nhất quán hơn, nhưng vẫn phải chọn thêm cơ chế xử lý cạnh tranh. Chỉ thêm transaction không làm mọi mức isolation trở thành serializable.

Những kiểm tra chỉ dựa vào đầu vào, chẳng hạn số lượng phải dương, có thể thực hiện trước khi truy cập kho dữ liệu. Những kiểm tra phụ thuộc trạng thái đang thay đổi cần được bảo vệ bằng cơ chế phù hợp với store.

### 3.2. Kết thúc đủ sớm

Transaction chỉ nên bao quanh phần cần xác nhận cùng nhau. Tránh giữ kết nối và khóa trong lúc:

- Chờ phản hồi HTTP từ cổng thanh toán.
- Gửi email hoặc tải tệp lên dịch vụ bên ngoài.
- Chờ người dùng xác nhận.
- Xử lý một tập dữ liệu quá lớn mà không có yêu cầu nguyên tử cho toàn bộ tập.

Một ranh giới tốt vừa bảo vệ bất biến, vừa hạn chế thời gian chiếm tài nguyên và nguy cơ xung đột.

## 4. Ví dụ: tạo đơn và giữ tồn trong một transaction

### 4.1. Giả định của ví dụ

Ví dụ dưới đây chọn **Spring Data JPA với cơ sở dữ liệu quan hệ có hỗ trợ transaction**. Hai repository dùng cùng persistence unit và cùng tài nguyên do transaction manager `shopTransactionManager` quản lý. Bean transaction manager này và hạ tầng xử lý `@Transactional` đã được cấu hình trong ứng dụng.

Đây là giả định của ví dụ JPA, không phải bảo đảm rằng mọi module kế thừa abstraction của Spring Data Commons đều có cùng khả năng giao dịch.

Domain minh họa gồm:

- `Product`: có ID, tồn khả dụng và version để kiểm soát cập nhật cạnh tranh.
- `PurchaseOrder`: lưu sản phẩm, số lượng và trạng thái `PENDING_PAYMENT`.
- `Product.reserve(quantity)`: kiểm tra số lượng, từ chối nếu thiếu hàng rồi giảm tồn khả dụng.
- `PurchaseOrder.pending(productId, quantity)`: tạo đơn mới ở trạng thái chờ thanh toán.

Các lớp entity và cấu hình kết nối không được triển khai đầy đủ ở đây; các đoạn code tập trung vào hợp đồng dịch vụ và vị trí đặt transaction.

### 4.2. Repository giữ vai trò truy cập dữ liệu

```java
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository extends CrudRepository<Product, Long> {
}
```

```java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
```

Không cần tạo một repository chung chứa mọi bước đặt hàng chỉ để có transaction. Tầng dịch vụ có thể phối hợp nhiều repository, miễn các thao tác tham gia đúng cùng transaction.

### 4.3. Dịch vụ định nghĩa đơn vị công việc

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderService {

    private final ProductRepository products;
    private final PurchaseOrderRepository orders;

    public PlaceOrderService(
            ProductRepository products,
            PurchaseOrderRepository orders) {
        this.products = products;
        this.orders = orders;
    }

    @Transactional(transactionManager = "shopTransactionManager")
    public OrderReceipt placeOrder(PlaceOrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException(
                    "Số lượng đặt hàng phải lớn hơn 0");
        }

        Product product = products.findById(command.productId())
                .orElseThrow(() -> new IllegalArgumentException(
                        "Không tìm thấy sản phẩm"));

        product.reserve(command.quantity());
        products.save(product);

        PurchaseOrder order = PurchaseOrder.pending(
                product.getId(), command.quantity());
        PurchaseOrder savedOrder = orders.save(order);

        return new OrderReceipt(
                savedOrder.getId(), "PENDING_PAYMENT");
    }

    public record PlaceOrderCommand(long productId, int quantity) {
    }

    public record OrderReceipt(Long orderId, String status) {
    }
}
```

Phương thức này có một mục tiêu nghiệp vụ rõ ràng: tạo đơn chờ thanh toán cùng việc giữ hàng. Nó không thu tiền, gửi email hay xử lý cả quá trình giao hàng.

Trong JPA, thay đổi trên entity đang được quản lý có thể được đồng bộ nhờ dirty checking. Lời gọi `save(product)` trong ví dụ làm rõ ý định qua API repository; không được suy ra rằng mọi store đều có dirty checking như JPA.

Với cách gọi thông qua transaction proxy và không có transaction bên ngoài, transaction interceptor bắt đầu transaction trước khi chạy thân phương thức, rồi commit sau khi thân phương thức trả về bình thường. Nếu commit thất bại, bên gọi vẫn nhận lỗi. Nếu phương thức tham gia một transaction sẵn có, việc commit cuối cùng thuộc về ranh giới bên ngoài đó.

Do đó, tạo được `OrderReceipt` trong thân phương thức hoặc có ID của đơn chưa đủ để kết luận dữ liệu đã commit thành công.

## 5. Transaction và kiểm soát cạnh tranh giải quyết hai vấn đề liên quan

Một transaction chung bảo đảm các thay đổi của nó được commit hoặc rollback cùng nhau theo khả năng của kho dữ liệu. Nó không tự bảo đảm rằng hai yêu cầu đồng thời không cùng bán phần hàng cuối cùng.

Giả sử tồn khả dụng là 3:

```text
Yêu cầu A đọc tồn = 3, muốn mua 2
Yêu cầu B đọc tồn = 3, muốn mua 2
A tính tồn mới = 1
B cũng tính tồn mới = 1
```

Nếu không có cơ chế kiểm soát cạnh tranh, cả hai đơn có thể được chấp nhận trong khi tổng lượng cần giữ vượt tồn ban đầu.

### 5.1. Một lựa chọn cho ví dụ JPA: optimistic locking

Trong entity JPA `Product`, có thể dùng trường version. Đoạn sau chỉ minh họa phần liên quan bên trong entity:

```java
import jakarta.persistence.Version;

// Các trường và phương thức bên trong entity Product:

@Version
private Long version;

private int available;

public void reserve(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("Số lượng phải dương");
    }
    if (available < quantity) {
        throw new IllegalStateException("Không đủ tồn kho");
    }
    available -= quantity;
}
```

Khi hai transaction cùng sửa một phiên bản sản phẩm, optimistic locking có thể làm một lần cập nhật thất bại. Khi đó, cả việc giữ hàng và tạo đơn của transaction thất bại phải được rollback. Xung đột có thể chỉ xuất hiện khi flush hoặc commit, không nhất thiết ngay tại `reserve()` hay `save()`.

Nếu thực hiện retry, phải chạy lại toàn bộ đơn vị công việc trong một transaction mới: đọc lại tồn, kiểm tra lại điều kiện rồi mới ghi. Không tái sử dụng quyết định đã tính từ dữ liệu cũ hoặc tiếp tục ghi trong transaction đã thất bại.

### 5.2. Những lựa chọn khác phụ thuộc store

Có thể cân nhắc pessimistic locking, cập nhật có điều kiện rồi kiểm tra số bản ghi bị tác động, hoặc mức isolation phù hợp. Ví dụ ý tưởng cập nhật có điều kiện:

```sql
UPDATE product
SET available = available - :quantity
WHERE id = :productId
  AND available >= :quantity;
```

Trong cách tiếp cận này, chỉ khi cập nhật đúng một bản ghi mới được coi là giữ hàng thành công; sau đó vẫn cần tạo đơn trong cùng transaction. Cách khai báo, thực thi và ánh xạ số bản ghi tác động phụ thuộc module truy cập dữ liệu.

Không ghép tùy tiện một cập nhật SQL trực tiếp với entity JPA đã tải mà bỏ qua việc đồng bộ persistence context và version. Đây là lựa chọn thiết kế thay thế cần được triển khai nhất quán.

## 6. Chọn hành vi khi một bước thất bại

Một đơn vị công việc chỉ có ý nghĩa khi hợp đồng thất bại rõ ràng.

| Tình huống | Kết quả mong muốn trong ví dụ |
| --- | --- |
| Sản phẩm không tồn tại | Từ chối; không tạo đơn, không thay đổi tồn |
| Không đủ hàng | Từ chối; không giữ riêng thay đổi nào |
| Lưu đơn lỗi sau khi đã thay đổi sản phẩm | Rollback cả hai thay đổi |
| Xung đột version khi flush hoặc commit | Rollback; quyết định retry ở bên ngoài transaction đã lỗi |
| Commit thành công nhưng gửi email sau đó lỗi | Đơn vẫn tồn tại; xử lý gửi lại theo cơ chế riêng |

### 6.1. Không nuốt lỗi rồi trả thành công

Một kiểu xử lý nguy hiểm:

```java
try {
    orders.save(order);
} catch (RuntimeException ex) {
    log.warn("Không lưu được đơn", ex);
}

return successResult;
```

Nếu lỗi bị nuốt, tầng gọi có thể nhận thông tin thành công không đúng. Tùy lỗi và hạ tầng persistence, transaction có thể còn được commit hoặc đã bị đánh dấu rollback-only và sẽ thất bại khi kết thúc. Cả hai khả năng đều cần được xử lý theo hợp đồng rõ ràng, không dựa vào việc đã chạy đến câu lệnh `return`.

Thông thường, để lỗi cần rollback thoát ra khỏi ranh giới transactional, rồi chuyển thành phản hồi thích hợp ở tầng ngoài. Chỉ bắt lỗi bên trong khi có lý do cụ thể và hiểu trạng thái transaction sau lỗi.

### 6.2. Khai báo rollback phù hợp với kiểu lỗi

Theo mặc định thông thường của `@Transactional` trong Spring, lỗi `RuntimeException` và `Error` dẫn tới rollback, còn checked exception không tự có cùng quy tắc đó. Ứng dụng cũng có thể cấu hình lại quy tắc, nên cần đọc đúng cấu hình đang dùng.

Nếu dịch vụ dùng một checked exception để báo thao tác nghiệp vụ thất bại và cần rollback, có thể khai báo rõ:

```java
@Transactional(
    transactionManager = "shopTransactionManager",
    rollbackFor = OrderPlacementException.class
)
public OrderReceipt placeOrder(PlaceOrderCommand command)
        throws OrderPlacementException {
    // Đọc, kiểm tra và ghi trong cùng đơn vị công việc.
    // Ném OrderPlacementException khi cần hủy toàn bộ thao tác.
    throw new OrderPlacementException("Ví dụ lỗi nghiệp vụ");
}
```

Đây là minh họa cách khai báo quy tắc; không phải phần thay thế hoàn chỉnh cho phương thức đặt hàng ở trên. `OrderPlacementException` trong ví dụ này là một checked exception do ứng dụng định nghĩa.

## 7. Bảo đảm lời gọi thực sự đi qua ranh giới transactional

### 7.1. Gọi qua Spring bean

Trong chế độ proxy thường dùng, `@Transactional` có tác dụng khi lời gọi được transaction interceptor xử lý. Cách thiết kế dễ theo dõi là đặt annotation trên phương thức public của một Spring-managed service và gọi service đó qua bean được inject.

Các trường hợp cần chú ý:

- Tự tạo đối tượng bằng `new PlaceOrderService(...)` không tự nhận transaction proxy của Spring.
- Một phương thức trong cùng đối tượng gọi `this.placeOrder(...)` thường không đi qua proxy trong chế độ proxy.
- Gắn annotation lên phương thức private không tạo ra ranh giới proxy theo cách trên.
- Chuyển phần ghi sang một luồng khác không tự mang theo transaction imperative đang gắn với luồng hiện tại.

Nếu cần một ranh giới riêng, có thể tách phương thức đó sang bean khác hoặc dùng API transaction theo chương trình phù hợp. Không dùng self-invocation như một cách mặc định để mở transaction mới.

### 7.2. Nhiều service vẫn có thể cùng một đơn vị công việc

Service A có thể gọi service B qua bean. Khi cả hai dùng propagation `REQUIRED`, cùng transaction manager và có transaction tương thích đang hoạt động, B thường tham gia transaction hiện tại. Không phải cứ có hai annotation thì sẽ có hai lần commit độc lập.

Ngược lại, `REQUIRES_NEW` mở một transaction độc lập trong điều kiện hạ tầng hỗ trợ. Nếu B đã commit ở transaction riêng, việc A rollback sau đó không tự hủy commit của B.

Vì vậy, không đặt `REQUIRES_NEW` tùy tiện lên thao tác giữ hàng hoặc tạo đơn nếu bất biến yêu cầu chúng thành công cùng nhau.

## 8. Phân biệt transaction cục bộ với quy trình nhiều hệ thống

Giả sử ứng dụng dùng:

```text
Cơ sở dữ liệu đơn hàng
Cơ sở dữ liệu tồn kho riêng
Cổng thanh toán HTTP
Hệ thống email
```

Một annotation ở service không tự biến bốn tài nguyên này thành một transaction nguyên tử. Transaction manager phải thực sự quản lý được tài nguyên tham gia; một transaction manager cục bộ không tự điều phối mọi cơ sở dữ liệu và API bên ngoài.

Với quy trình phân tán, cần xác định các bước có trạng thái và cơ chế phục hồi riêng, chẳng hạn:

1. Tạo đơn và giữ hàng trong phạm vi giao dịch có thể bảo đảm.
2. Ghi nhận yêu cầu xử lý tiếp theo.
3. Thực hiện thanh toán bằng giao thức của hệ thống ngoài.
4. Cập nhật đơn thành đã thanh toán hoặc hủy, trả hàng theo kết quả.

Nếu cần phát sự kiện đáng tin cậy sau khi tạo đơn, có thể ghi một bản ghi outbox cùng transaction với đơn, rồi để tiến trình khác gửi sự kiện và retry. Outbox phải nằm trong cùng phạm vi transaction được bảo đảm; một outbox ở tài nguyên độc lập không tự có tính nguyên tử với đơn hàng.

Gửi email sau commit tránh gửi thông báo cho một đơn bị rollback, nhưng bản thân callback sau commit không phải cơ chế lưu bền để bảo đảm gửi thành công. Khi cần độ tin cậy, phải có dữ liệu lưu bền, cơ chế retry và xử lý lặp phù hợp.

## 9. Chọn ranh giới cho các loại thao tác thường gặp

| Loại thao tác | Ranh giới thường phù hợp | Điểm cần quyết định thêm |
| --- | --- | --- |
| Tạo hoặc cập nhật một aggregate | Một transaction cho thao tác nghiệp vụ với aggregate | Version, ràng buộc và quyền sửa |
| Phối hợp nhiều repository cùng tài nguyên | Một transaction ở service nếu cần nguyên tử | Tất cả phải tham gia đúng transaction |
| Lấy dữ liệu hiển thị đơn giản | Phạm vi đọc cần thiết, có thể dùng read-only khi phù hợp | Khả năng store, mapping và nhu cầu nhất quán |
| Đọc nhiều trang dữ liệu | Thường kết thúc từng lần đọc thay vì giữ transaction qua tương tác người dùng | Các trang có thể thấy dữ liệu ở những thời điểm khác nhau |
| Import hàng triệu bản ghi | Chia lô nếu nghiệp vụ chấp nhận commit từng phần | Checkpoint, retry, idempotency và thông báo tiến độ |
| Chờ thanh toán hoặc phê duyệt | Nhiều bước ngắn với trạng thái lưu bền | Timeout, bù trừ và xử lý thông điệp lặp |

`readOnly = true` có thể diễn đạt ý định đọc và cho phép một số tối ưu tùy hạ tầng. Không coi đó là cơ chế phân quyền cấm ghi tuyệt đối hoặc lời hứa rằng mọi lần đọc đều thấy cùng một snapshot.

Projection có thể giúp lấy đúng dữ liệu cần dùng và tránh mang entity ra ngoài phạm vi persistence không phù hợp. Tuy nhiên, projection, derived query, phân trang và sắp xếp không tự thay đổi bảo đảm transaction của store. Auditing ghi nhận metadata như người sửa và thời điểm sửa; nó cũng không thay thế việc thiết kế ranh giới commit.

Với API reactive, transaction cần được áp dụng vào chuỗi thực thi bằng hạ tầng reactive tương ứng; với coroutine, cần kiểm tra khả năng tích hợp của store và transaction manager đang dùng. Không áp nguyên xi giả định transaction imperative gắn với một luồng cho mọi repository bất đồng bộ.

## 10. Đánh giá một thiết kế ranh giới bằng các tình huống cụ thể

Trước khi chấp nhận một thiết kế, hãy mô tả kết quả mong đợi của các tình huống sau:

1. Thao tác ghi thứ hai lỗi sau khi thao tác thứ nhất đã thực thi: dữ liệu nào được giữ lại?
2. Lỗi chỉ phát sinh tại commit: tầng gọi có nhận thành công nhầm không?
3. Hai yêu cầu cùng dùng phần tồn cuối: cơ chế nào ngăn chấp nhận vượt khả năng cung cấp?
4. Bên gọi gửi lại yêu cầu sau khi mất kết nối: làm sao xác định yêu cầu trước đã commit hay chưa?
5. Hệ thống email hoặc thanh toán không phản hồi: có đang giữ transaction cơ sở dữ liệu không?
6. Một repository được đổi sang kho dữ liệu khác: bảo đảm nguyên tử ban đầu còn đúng không?

Với yêu cầu lặp, có thể cần mã idempotency hoặc ràng buộc duy nhất theo định danh yêu cầu. Transaction giúp phối hợp thay đổi trong một lần thực thi; nó không tự nhận biết hai HTTP request là cùng một yêu cầu nghiệp vụ.

Một hợp đồng ranh giới có thể viết ngắn gọn như sau:

```text
Use case: đặt hàng chờ thanh toán

Thành công cục bộ:
- Đơn chờ thanh toán được lưu.
- Tồn khả dụng được giảm đúng số lượng.

Thất bại trước commit:
- Không giữ riêng một trong hai thay đổi trên.

Tài nguyên:
- Cùng cơ sở dữ liệu và transaction manager của cửa hàng.

Cạnh tranh:
- Kiểm soát bằng version hoặc cơ chế cập nhật được chọn cho store.

Ngoài transaction này:
- Thu tiền, gửi email và chờ người dùng.

Lặp yêu cầu:
- Có chiến lược nhận diện yêu cầu nếu nghiệp vụ cần chống tạo đơn trùng.
```

Chọn đơn vị công việc ở tầng dịch vụ là đưa hợp đồng này vào cấu trúc chương trình: một phương thức điều phối mục tiêu nghiệp vụ, một ranh giới transaction phù hợp tài nguyên, và một cách xử lý lỗi thể hiện đúng điều mà hệ thống đã hoặc chưa commit.
