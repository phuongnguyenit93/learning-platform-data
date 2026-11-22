# Phân biệt lỗi nghiệp vụ, xung đột và lỗi hạ tầng

Khi khách đặt hàng, hệ thống có thể từ chối vì kho không còn đủ số lượng, phát hiện đơn đã được một request khác cập nhật, hoặc không thể kết nối database. Cả ba tình huống đều khiến use case không hoàn thành theo cách mong muốn, nhưng ý nghĩa và cách xử lý hoàn toàn khác nhau.

Nếu gom tất cả thành một lỗi chung như `REQUEST_FAILED`, giao diện không biết nên yêu cầu khách thay đổi số lượng, tải lại dữ liệu hay thử lại sau. Nếu retry mọi lỗi, hệ thống có thể lặp lại một lệnh nghiệp vụ vốn đã bị từ chối hoặc thực hiện một tác dụng phụ hai lần. Nếu trả thông báo kỹ thuật cho người dùng, hệ thống có thể làm lộ chi tiết nội bộ và khiến người dùng không biết phải làm gì tiếp theo.

Trong Domain-Driven Design (DDD), Use Case/Application Service là nơi điều phối hành động của người dùng hoặc hệ thống. Nó cần phân biệt kết quả nghiệp vụ dự kiến, xung đột với trạng thái hiện tại và sự cố kỹ thuật để trả về kết quả phù hợp. Domain model quyết định quy tắc nghiệp vụ; persistence và integration adapter phát hiện lỗi hạ tầng; application layer chuyển các kết quả đó thành contract mà caller có thể hiểu.

Sau bài học này, bạn có thể:

- Phân biệt business rejection, state conflict, concurrency conflict và infrastructure failure.
- Xác định lỗi thuộc domain, application hay infrastructure layer.
- Thiết kế kiểu kết quả và mã lỗi ổn định cho một use case.
- Chọn khi nào trả kết quả từ chối, khi nào ném exception và khi nào retry.
- Xử lý optimistic locking, unique constraint, timeout và kết quả không xác định từ hệ thống ngoài.
- Ánh xạ lỗi sang HTTP/API mà không làm domain phụ thuộc giao thức.
- Kiểm thử các nhánh lỗi và khả năng phục hồi của use case.

## 1. Không phải mọi lần use case không thành công đều là cùng một loại lỗi

Xét use case `PlaceOrder`:

| Tình huống | Điều đã xảy ra | Ý nghĩa |
|---|---|---|
| Số lượng yêu cầu lớn hơn hàng khả dụng | Inventory không thể đáp ứng yêu cầu | Từ chối theo quy tắc nghiệp vụ |
| Order đã được giao nên không thể hủy | Trạng thái hiện tại không cho phép hành động | Xung đột trạng thái nghiệp vụ |
| Hai nhân viên cùng sửa một Order; request thứ hai dùng version cũ | Dữ liệu đã đổi sau lần đọc | Xung đột đồng thời |
| Database tạm thời không kết nối được | Ứng dụng không thể hoàn tất thao tác lưu | Lỗi hạ tầng |
| Payment provider timeout sau khi nhận lệnh capture | Chưa biết provider đã xử lý hay chưa | Kết quả bên ngoài chưa xác định |

Điểm khác nhau quan trọng là: **lỗi nghiệp vụ cho biết yêu cầu không được phép hoặc không thể đáp ứng theo quy tắc; xung đột cho biết giả định về trạng thái không còn đúng; lỗi hạ tầng cho biết hệ thống không thể thực hiện hoặc xác nhận thao tác vì một phụ thuộc kỹ thuật.**

Một use case có thể gặp nhiều loại lỗi liên tiếp. Ví dụ, request ban đầu gặp optimistic locking conflict; sau khi tải lại, hệ thống phát hiện hàng đã hết và trả business rejection. Không nên giữ nguyên nhãn `CONCURRENT_UPDATE` sau khi đã đánh giá lại trạng thái và xác định nguyên nhân cuối cùng là thiếu hàng.

## 2. Ba nhóm kết quả chính

### 2.1. Lỗi hoặc từ chối nghiệp vụ (business rejection)

Business rejection xảy ra khi hệ thống hiểu yêu cầu, có đủ dữ liệu để đánh giá, nhưng domain rule không cho phép hành động hoặc điều kiện nghiệp vụ chưa được đáp ứng.

Ví dụ:

- Không đủ hàng để đặt.
- Tài khoản không đủ số dư theo policy.
- Đơn đã giao nên không thể hủy.
- Khách hàng không đủ điều kiện mua chịu.
- Thuê bao đã hết thời gian cho phép gia hạn.
- Số lượng đặt vượt giới hạn tối đa của chương trình.

Đây thường là kết quả có thể dự đoán trong hoạt động bình thường của hệ thống. Người dùng có thể thay đổi yêu cầu, chọn phương án khác hoặc thực hiện hành động khác. Vì vậy, không phải lúc nào business rejection cũng nên được biểu diễn bằng exception.

Ví dụ, `InsufficientStock` có thể là kết quả thường gặp khi khách đặt hàng. Use case có thể trả `Rejected(INSUFFICIENT_STOCK)` để giao diện hiển thị số lượng còn lại hoặc gợi ý giảm số lượng.

### 2.2. Xung đột (conflict)

Conflict xảy ra khi hành động được thực hiện dựa trên một giả định về trạng thái hoặc phiên bản, nhưng giả định đó không còn đúng khi hệ thống xử lý.

Có hai dạng thường gặp:

- **State conflict:** trạng thái hiện tại không còn phù hợp với thao tác, chẳng hạn một Order đã được giao khi người dùng yêu cầu hủy.
- **Concurrency conflict:** một thao tác khác đã thay đổi dữ liệu sau khi request hiện tại đọc nó, chẳng hạn optimistic locking phát hiện version mismatch.

Conflict có thể cần người dùng tải lại và xác nhận. Với một số command có ý nghĩa tương đối như `IncreaseQuantityBy(2)`, hệ thống có thể tải lại và áp dụng lại nếu domain vẫn cho phép. Với command tuyệt đối như `SetQuantityTo(5)`, tự động retry có thể ghi đè ý định của người khác.

### 2.3. Lỗi hạ tầng (infrastructure failure)

Infrastructure failure xảy ra khi một phụ thuộc kỹ thuật không hoạt động như mong đợi hoặc ứng dụng không thể hoàn tất thao tác kỹ thuật.

Ví dụ:

- Database không khả dụng.
- Kết nối đến message broker bị gián đoạn.
- Dịch vụ ngoài trả lỗi tạm thời hoặc timeout.
- Connection pool cạn.
- Lỗi serialization hoặc cấu hình adapter.
- Disk hoặc tài nguyên lưu trữ không còn khả dụng.

Một số lỗi hạ tầng có thể tạm thời và retry được; một số lỗi là cấu hình hoặc dữ liệu không hợp lệ và không nên retry. Không được gắn nhãn `RETRYABLE` chỉ vì lỗi đến từ infrastructure layer.

## 3. Phân biệt business validation và business rejection

Validation thường kiểm tra hình dạng và tính hợp lệ cơ bản của dữ liệu đầu vào. Business rejection kiểm tra một yêu cầu hợp lệ về cấu trúc nhưng không đáp ứng quy tắc domain tại thời điểm thực hiện.

| Trường hợp | Nhóm | Ví dụ |
|---|---|---|
| Thiếu `orderId` | Input validation | Request thiếu trường bắt buộc |
| `quantity = 0` | Validation hoặc invariant của command | Số lượng phải lớn hơn 0 |
| SKU không tồn tại | Domain/application lookup result | Không tìm thấy sản phẩm trong phạm vi context |
| Kho chỉ còn 2 nhưng khách đặt 5 | Business rejection | Không đủ hàng |
| Khách bị khóa mua hàng | Business rejection | Policy không cho phép đặt đơn |
| JSON không parse được | Protocol/input parsing | Payload sai cú pháp |

Ranh giới giữa validation và domain rule phụ thuộc vào ý nghĩa của trường. `quantity > 0` có thể là điều kiện hợp lệ của Value Object `Quantity`; `quantity <= availableStock` là quy tắc nghiệp vụ cần trạng thái Inventory. Không nên đưa mọi kiểm tra vào controller chỉ vì chúng diễn ra trước khi gọi domain model.

Một nguyên tắc hữu ích:

- Kiểm tra cú pháp, kiểu dữ liệu và trường bắt buộc ở ranh giới đầu vào.
- Kiểm tra bất biến của giá trị trong Value Object hoặc constructor phù hợp.
- Kiểm tra điều kiện phụ thuộc trạng thái và chính sách trong Entity/Aggregate hoặc Domain Service.
- Để application layer chuyển kết quả thành response của use case.

## 4. Phân biệt conflict nghiệp vụ với concurrency conflict

Hai tình huống này dễ bị gộp chung vì cả hai đều có thể trả HTTP `409 Conflict`, nhưng cách phục hồi có thể khác nhau.

**State conflict:** người dùng yêu cầu hủy một Order đã ở trạng thái `Shipped`. Ngay cả khi không có request đồng thời nào, domain vẫn từ chối hành động. Tải lại Order không làm thay đổi quy tắc: trạng thái đã giao không cho phép hủy theo policy hiện tại.

**Concurrency conflict:** người dùng mở Order ở version 7. Trong lúc họ chỉnh sửa, một người khác cập nhật Order thành version 8. Request đầu tiên gửi `If-Match` hoặc expected version 7. Hệ thống từ chối vì dữ liệu đã thay đổi sau lần đọc. Sau khi tải lại version 8, người dùng có thể xem xét và gửi một command mới.

| Tiêu chí | State conflict | Concurrency conflict |
|---|---|---|
| Nguyên nhân | Trạng thái domain hiện tại không cho phép hành động | Trạng thái đã đổi sau khi caller đọc |
| Cần version mismatch? | Không | Thường có |
| Tải lại có giúp không? | Thường không, trừ khi trạng thái thay đổi về sau | Có thể giúp caller đánh giá lại |
| Retry tự động | Thường không | Chỉ khi command an toàn và được đánh giá lại |
| Ví dụ | Hủy đơn đã giao | Cập nhật Order với version cũ |

State conflict thường cũng là một dạng business rejection: domain từ chối hành động vì trạng thái hiện tại không đáp ứng điều kiện. Bài học tách nó thành nhóm riêng để nhấn mạnh cách phục hồi khác với concurrency conflict. Với state conflict, tải lại thường chỉ giúp người dùng hiểu trạng thái; với concurrency conflict, tải lại là bước cần thiết để đánh giá lại command trên phiên bản mới.

Một concurrency conflict sau khi tải lại có thể chuyển thành business rejection. Ví dụ, hai người cùng giữ lượng hàng cuối; request thứ hai gặp version mismatch, tải lại và nhận ra không còn hàng. Kết quả cuối cùng cần phản ánh quy tắc thiếu hàng.

## 5. Lỗi thuộc layer nào?

DDD không yêu cầu mọi lỗi phải là một class exception. Nhưng việc xác định nơi phát sinh và nơi chuyển đổi lỗi giúp tránh phụ thuộc ngược giữa các layer.

| Layer | Trách nhiệm | Ví dụ kết quả/lỗi |
|---|---|---|
| Domain | Quy tắc và trạng thái nghiệp vụ | `InsufficientStock`, `OrderAlreadyShipped`, `InvalidTransfer` |
| Application | Điều phối use case và chuyển đổi kết quả | `OrderNotFound`, `ConcurrentModification`, `OperationTemporarilyUnavailable` |
| Infrastructure | Database, broker, HTTP client, filesystem | `SQLTransientConnectionException`, timeout, broker unavailable |
| API/Presentation | Giao thức và cách trình bày lỗi | HTTP status, error code, message, field errors |

Domain layer không nên ném `ResponseStatusException`, `HttpException`, `SQLException` hoặc exception của ORM. Domain chỉ biết quy tắc của nó. Application layer có thể nhận diện các lỗi từ repository/adapter và chuyển chúng thành kết quả use case. API adapter ánh xạ kết quả đó thành HTTP hoặc giao thức khác.

## 6. Khi nào dùng exception và khi nào dùng kết quả có kiểu?

Exception phù hợp để báo một tình huống bất thường làm gián đoạn luồng xử lý hiện tại, hoặc khi framework/persistence API đã dùng exception để thông báo lỗi. Nhưng một business rejection thường gặp có thể được biểu diễn như kết quả có kiểu để caller xử lý tường minh.

Ví dụ, một use case đặt hàng có thể trả về:

```text
Placed(orderId)
Rejected(INSUFFICIENT_STOCK)
Rejected(CUSTOMER_NOT_ELIGIBLE)
Conflict(VERSION_MISMATCH)
TemporarilyUnavailable(RETRY_LATER)
```

Caller phải phân biệt các nhánh. Điều này có thể rõ ràng hơn việc ném exception cho mọi kết quả không thành công.

### Dùng exception khi

- Một invariant bị vi phạm ở nơi code kỳ vọng dữ liệu hợp lệ.
- Một domain operation được gọi trong điều kiện mà contract của nó yêu cầu phải thành công, nhưng precondition không còn đúng.
- Một phụ thuộc hạ tầng ném exception và application cần chuyển đổi nó.
- Transaction cần rollback do lỗi không thể tiếp tục.
- Framework dùng exception để báo optimistic locking, constraint violation hoặc timeout.
- Một lỗi lập trình bất ngờ xảy ra và cần được ghi nhận như lỗi hệ thống.

### Dùng kết quả có kiểu khi

- Từ chối là kết quả bình thường của use case.
- Caller cần lựa chọn nhánh tiếp theo theo mã lỗi.
- API cần trả danh sách lý do validation hoặc điều kiện không đạt.
- Không muốn dùng exception làm luồng điều khiển cho các trường hợp dự kiến.

Hai cách có thể cùng tồn tại. Domain method có thể ném `InsufficientFundsException`, còn Application Service bắt và chuyển thành `Rejected(INSUFFICIENT_FUNDS)`. Hoặc domain policy có thể trả `EligibilityResult`. Hãy thống nhất cách dùng trong một codebase và tránh bắt rồi bỏ qua exception.

## 7. Thiết kế mã lỗi ổn định

Mã lỗi là contract giữa use case và caller. Nó nên diễn đạt ý nghĩa ổn định, không phụ thuộc vào tên exception của thư viện hoặc câu chữ của database.

Ví dụ:

| Mã | Ý nghĩa | Có thể thử lại? | Hướng xử lý |
|---|---|---|---|
| `INSUFFICIENT_STOCK` | Hàng khả dụng không đủ | Không với cùng số lượng và cùng trạng thái | Giảm số lượng hoặc chọn mặt hàng khác |
| `CUSTOMER_NOT_ELIGIBLE` | Khách không đáp ứng policy | Không nếu dữ kiện không đổi | Xem điều kiện hoặc liên hệ hỗ trợ |
| `ORDER_STATE_CONFLICT` | Trạng thái Order không cho phép hành động | Không tự động | Tải trạng thái và chọn hành động hợp lệ |
| `VERSION_CONFLICT` | Dữ liệu đã thay đổi kể từ lần đọc | Có điều kiện | Tải lại và đánh giá lại command |
| `DEPENDENCY_UNAVAILABLE` | Phụ thuộc tạm thời không sẵn sàng | Có thể, có giới hạn | Thử lại sau hoặc chuyển sang xử lý chờ |
| `DEPENDENCY_OUTCOME_UNKNOWN` | Không xác định được hệ thống ngoài đã xử lý hay chưa | Không gửi lại mù quáng | Tra cứu bằng idempotency/reference và đối soát |
| `UNEXPECTED_ERROR` | Lỗi không dự kiến | Tùy nguyên nhân | Ghi nhận và xử lý theo incident policy |

Không nên dùng thông điệp exception thô làm error code. Ví dụ `duplicate key value violates unique constraint ...` là chi tiết database, không phải contract domain.

Mã lỗi cần được quản lý khi API thay đổi. Nếu đổi tên exception nội bộ, client không nên phải cập nhật nếu ý nghĩa contract không đổi.

## 8. Biểu diễn kết quả use case bằng Java

Java 17 có thể dùng sealed interface và record để mô tả các kết quả có kiểu. Ví dụ giản lược:

```java
public sealed interface PlaceOrderOutcome
        permits OrderPlacementSucceeded, OrderRejected, OrderConflict,
                OrderTemporarilyUnavailable {
}

public record OrderPlacementSucceeded(OrderId orderId)
        implements PlaceOrderOutcome {
}

public record OrderRejected(String code, String message)
        implements PlaceOrderOutcome {
}

public record OrderConflict(String code, String message)
        implements PlaceOrderOutcome {
}

public record OrderTemporarilyUnavailable(String code)
        implements PlaceOrderOutcome {
}
```

Application Service có thể trả kết quả này cho controller hoặc message consumer. Trong code production, nên dùng enum hoặc type riêng cho error code thay vì chuỗi tự do, và không đưa thông điệp nhạy cảm từ exception vào response.

Một cách dùng:

```java
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.dao.TransientDataAccessException;

public PlaceOrderOutcome execute(PlaceOrderCommand command) {
    try {
        return transactionRunner.execute(() -> placeWithinTransaction(command));
    } catch (OptimisticLockingFailureException ex) {
        return new OrderConflict(
            "VERSION_CONFLICT",
            "Đơn hàng đã được cập nhật. Hãy tải lại trước khi tiếp tục."
        );
    } catch (TransientDataAccessException ex) {
        return new OrderTemporarilyUnavailable("DEPENDENCY_UNAVAILABLE");
    }
}
```

Đoạn code là phương thức bên trong một Application Service; phần khai báo class và dependency được lược bỏ. Đây là ví dụ theo Spring và cần đặt `try/catch` bên ngoài transaction boundary để bắt lỗi có thể chỉ xuất hiện khi flush/commit. Với JPA trực tiếp, adapter có thể nhận `jakarta.persistence.OptimisticLockException` trước khi chuyển đổi sang exception của Spring. Không nên bắt tất cả `RuntimeException` rồi chuyển thành `DEPENDENCY_UNAVAILABLE`; lỗi lập trình hoặc business rule bị vi phạm có thể bị che giấu.

## 9. Domain rule nên được thể hiện như thế nào?

Domain model phải bảo vệ invariant bất kể caller đến từ REST API, message consumer, batch job hay giao diện quản trị.

Ví dụ:

```java
public class StockItem {
    private int availableQuantity;

    public void reserve(int requested) {
        if (requested <= 0) {
            throw new InvalidQuantityException();
        }
        if (availableQuantity < requested) {
            throw new InsufficientStockException();
        }
        availableQuantity -= requested;
    }
}
```

`InvalidQuantityException` và `InsufficientStockException` là lỗi có ý nghĩa domain. Domain không cần biết API sẽ trả 400, 409 hay 422.

Nếu thiếu hàng là kết quả thường gặp, application có thể chuyển exception thành `OrderRejected`. Nếu codebase thích kiểu kết quả, `reserve()` cũng có thể trả `ReservationDecision`. Điều quan trọng là không để caller sửa `availableQuantity` trực tiếp và bỏ qua invariant.

### Phân biệt lỗi đầu vào với invariant

Một request có thể được kiểm tra `quantity > 0` ở Value Object `Quantity`. Nhưng nếu domain model có thể được gọi từ nhiều đường vào, Aggregate vẫn cần bảo vệ invariant quan trọng của nó. Không dựa vào controller để giữ trạng thái domain hợp lệ.

## 10. Xử lý optimistic locking conflict

Optimistic locking phát hiện một request đang ghi trên version cũ. Với JPA, `@Version` thường khiến provider ném `OptimisticLockException` hoặc exception được framework chuyển đổi khi flush/commit.

Luồng xử lý phù hợp:

1. Transaction hiện tại thất bại và rollback.
2. Application layer nhận diện lỗi version conflict.
3. Nếu contract yêu cầu, trả `VERSION_CONFLICT` để client tải lại.
4. Nếu có thể retry tự động, bắt đầu transaction mới và tải Aggregate mới.
5. Áp dụng lại command theo trạng thái mới, chạy lại domain rule.
6. Nếu rule không còn cho phép, trả business rejection thay vì tiếp tục retry.

Không được tiếp tục dùng Aggregate cũ hoặc persistence context đã thất bại. Retry phải có giới hạn và cần đảm bảo command có semantics phù hợp.

Ví dụ:

```text
Request A và B cùng đọc StockItem version 4, available = 10

A reserve 7 -> commit thành công, version = 5, available = 3
B reserve 6 -> version mismatch
B rollback và tải lại version 5
B chạy lại reserve(6) -> InsufficientStock

Kết quả cuối: A thành công, B bị từ chối theo nghiệp vụ
```

Conflict là tín hiệu kỹ thuật về stale state; kết quả sau khi đánh giá lại là quyết định nghiệp vụ.

## 11. Xử lý unique constraint và duplicate request

Unique constraint có thể bảo vệ invariant như một khách không được tạo hai reservation cùng mã yêu cầu, hoặc một Order chỉ có một Invoice đang phát hành theo quy tắc cụ thể.

Khi insert vi phạm unique constraint, database báo lỗi persistence. Application cần biết constraint đó đại diện cho điều gì:

- Nếu nó biểu diễn một quy tắc domain đã biết, có thể chuyển thành business conflict như `DUPLICATE_RESERVATION`.
- Nếu duplicate xuất phát từ request retry có cùng idempotency key, có thể trả lại kết quả đã lưu.
- Nếu vi phạm constraint là bất ngờ do bug hoặc dữ liệu sai, cần ghi nhận như lỗi hệ thống và điều tra.

Không nên phân loại mọi `DataIntegrityViolationException` thành `DUPLICATE_REQUEST`. Nó có thể là foreign key violation, not-null violation, check constraint hoặc lỗi dữ liệu khác. Adapter cần nhận diện constraint cụ thể và application mapping phải có chủ đích.

### Idempotency key

Client có thể gửi một idempotency key cho command tạo giao dịch. Server lưu key cùng kết quả xử lý. Khi nhận lại cùng key:

- Nếu command đã hoàn tất, trả lại kết quả trước đó.
- Nếu command đang xử lý, trả trạng thái đang xử lý hoặc hướng dẫn retry theo contract.
- Nếu key được dùng với payload khác, từ chối theo policy.

Idempotency đặc biệt quan trọng khi client timeout và không biết server đã commit hay chưa. Gửi lại request với key mới có thể tạo giao dịch thứ hai.

## 12. Lỗi hạ tầng: transient, permanent và unknown outcome

Không phải mọi lỗi hạ tầng đều giống nhau. Cần phân loại theo khả năng phục hồi và mức độ chắc chắn về kết quả.

### Transient failure

Lỗi có thể tạm thời, chẳng hạn database failover, broker ngắt kết nối ngắn hoặc dịch vụ ngoài trả 503. Retry có thể thành công sau một khoảng chờ.

### Permanent/configuration failure

Ví dụ thiếu credential, URL sai, schema không tương thích hoặc permission bị từ chối. Retry liên tục không giải quyết được nguyên nhân. Cần sửa cấu hình hoặc quyền truy cập.

### Unknown outcome

Request đã được gửi đến hệ thống ngoài nhưng client timeout trước khi nhận response. Có thể provider đã xử lý thành công, nhưng ứng dụng không biết. Đây không phải lỗi có thể retry mù quáng.

Ví dụ, payment provider đã capture tiền nhưng response bị mất. Gửi lại lệnh capture với một request mới có thể thu tiền hai lần. Hãy dùng idempotency key, truy vấn trạng thái theo reference hoặc thực hiện reconciliation trước khi quyết định.

| Loại lỗi | Ví dụ | Retry? | Hành động |
|---|---|---|---|
| Transient | Connection reset, 503 tạm thời | Có điều kiện | Retry có giới hạn, backoff và jitter |
| Permanent | Credential sai, schema mismatch | Không | Sửa cấu hình hoặc contract |
| Unknown outcome | Timeout sau khi gửi lệnh thanh toán | Không gửi lại mù quáng | Tra cứu trạng thái/đối soát bằng idempotency key |
| Business rejection | Không đủ hàng | Không với cùng điều kiện | Thay đổi yêu cầu hoặc chờ trạng thái mới |
| Concurrency conflict | Version mismatch | Có điều kiện | Transaction mới, tải lại và đánh giá lại |

## 13. Retry cần có điều kiện

Retry là một chính sách, không phải phản xạ mặc định khi bắt exception.

Trước khi retry, hãy hỏi:

- Lỗi có khả năng tạm thời không?
- Thao tác có idempotent không?
- Kết quả lần trước có chắc chắn chưa được commit không?
- Command có thể được đánh giá lại trên trạng thái mới không?
- Có giới hạn số lần và tổng thời gian retry không?
- Có backoff/jitter để giảm việc nhiều client cùng retry không?
- Khi hết retry, hệ thống trả kết quả nào và có cần cảnh báo không?

### Không retry business rejection

Nếu số lượng hàng không đủ, retry ngay cùng số lượng và cùng trạng thái sẽ tiếp tục bị từ chối. Retry chỉ có ý nghĩa khi trạng thái thay đổi hoặc yêu cầu được điều chỉnh. Có thể đặt lịch thử lại khi có hàng mới, nhưng đó là một quy trình chờ sự kiện, không phải retry vòng lặp liên tục.

### Retry concurrency conflict

Có thể retry một số command sau khi tải lại Aggregate. Nhưng cần phân biệt command tương đối và tuyệt đối:

- `IncreaseQuantityBy(2)`: có thể áp dụng lại nếu invariant vẫn đúng.
- `SetQuantityTo(5)`: cần biết người dùng có còn muốn ghi đè giá trị mới hay không.
- `CancelOrder`: phải đánh giá lại trạng thái Order sau khi tải mới.

### Retry transient infrastructure failure

Có thể retry nếu thao tác an toàn hoặc có idempotency. Dùng exponential backoff và giới hạn thời gian. Không giữ transaction mở trong khi chờ retry; mỗi lần thử cần transaction/connection phù hợp và tải dữ liệu mới nếu trạng thái có thể thay đổi.

## 14. Transaction rollback và thời điểm bắt lỗi

Một lỗi có thể chỉ xuất hiện khi ORM flush hoặc transaction commit, không nhất thiết tại dòng gọi `save()`. Vì vậy, bắt exception quanh một lời gọi repository có thể chưa đủ.

Ví dụ theo Spring:

```java
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.transaction.support.TransactionTemplate;

public PlaceOrderOutcome execute(PlaceOrderCommand command) {
    try {
        return transactionTemplate.execute(status -> {
            Order order = orders.findById(command.orderId())
                .orElseThrow(OrderNotFoundException::new);

            order.place(command.quantity());
            orders.save(order);
            return new OrderPlacementSucceeded(order.id());
        });
    } catch (OptimisticLockingFailureException ex) {
        return new OrderConflict(
            "VERSION_CONFLICT",
            "Đơn hàng đã thay đổi. Hãy tải lại trước khi tiếp tục."
        );
    } catch (TransientDataAccessException ex) {
        return new OrderTemporarilyUnavailable("DEPENDENCY_UNAVAILABLE");
    }
}
```

Đoạn code đặt `try/catch` bên ngoài `transactionTemplate.execute()` để bao gồm lỗi có thể xuất hiện trong lúc transaction hoàn tất. Tùy cấu hình, `TransactionTemplate` sẽ rollback khi callback ném runtime exception. Nếu dùng `@Transactional`, cần chú ý exception có thể xuất hiện ở proxy boundary khi method trả về và commit được thực hiện.

Ví dụ ánh xạ `TransientDataAccessException` sang unavailable chỉ phù hợp khi adapter xác định thao tác chưa commit và có thể thử lại an toàn. Nếu kết nối bị mất đúng lúc gửi lệnh `COMMIT` và ứng dụng không biết database đã commit hay chưa, hãy biểu diễn `OUTCOME_UNKNOWN` và đối soát theo idempotency key/reference. Không được mặc định mọi lỗi kết nối ở commit đều có nghĩa transaction đã rollback.

Không bắt lỗi rồi tiếp tục dùng transaction đã bị đánh dấu rollback-only. Khi cần retry, bắt đầu transaction mới.

### Không nuốt lỗi

Code như sau rất nguy hiểm:

```java
try {
    orders.save(order);
} catch (Exception ignored) {
    // tiếp tục trả thành công
}
```

Use case có thể báo thành công dù dữ liệu chưa được lưu. Nếu lỗi là kết quả dự kiến, hãy chuyển thành một outcome rõ ràng; nếu là lỗi kỹ thuật, hãy để transaction rollback và xử lý ở boundary phù hợp.

## 15. Ánh xạ lỗi sang HTTP/API

Domain và application layer không nên biết HTTP status code. Controller/API adapter chuyển outcome của use case thành response theo contract.

Một bảng ánh xạ tham khảo:

| Kết quả use case | HTTP có thể dùng | Ý nghĩa với client |
|---|---:|---|
| Request sai cú pháp/kiểu | `400 Bad Request` | Sửa request |
| Không xác thực/không có quyền | `401` / `403` | Đăng nhập hoặc kiểm tra quyền |
| Không tìm thấy tài nguyên | `404 Not Found` | Kiểm tra ID hoặc phạm vi truy cập |
| Business validation không đạt | `422 Unprocessable Content` hoặc `400` theo contract | Sửa dữ liệu/điều kiện |
| State/concurrency conflict | `409 Conflict` | Tải lại hoặc chọn hành động khác |
| `If-Match` không còn đúng | `412 Precondition Failed` | Đọc representation mới rồi quyết định |
| Phụ thuộc tạm thời không khả dụng | `503 Service Unavailable` | Thử lại sau nếu request an toàn |
| Gateway chờ hệ thống ngoài quá lâu | `504 Gateway Timeout` | Kết quả có thể cần tra cứu nếu side effect đã được gửi |
| Lỗi không dự kiến | `500 Internal Server Error` | Không thể tự khắc phục từ request hiện tại |

Đây là hướng dẫn tham khảo; contract API của hệ thống cần nhất quán. Một business rejection không nhất thiết luôn là 422, và không phải mọi conflict đều phải trả 409. Ví dụ, điều kiện `If-Match` không thỏa có ngữ nghĩa HTTP riêng là 412.

### Error response nên có gì?

Một response lỗi có thể chứa:

```json
{
  "code": "VERSION_CONFLICT",
  "message": "Đơn hàng đã được cập nhật. Hãy tải lại trước khi tiếp tục.",
  "correlationId": "c7a2f8...",
  "retryable": false
}
```

Với validation có thể trả thêm danh sách field errors. Với lỗi tạm thời, có thể có `Retry-After` nếu phù hợp. Không trả stack trace, SQL, tên bảng, credential, địa chỉ nội bộ hoặc thông điệp exception thô cho client.

## 16. Lỗi nghiệp vụ không nên làm lộ dữ liệu nhạy cảm

Thông báo cần giúp người dùng hiểu hành động tiếp theo, nhưng không nên tiết lộ thông tin mà họ không có quyền biết.

Ví dụ, khi khách nhập mã khách hàng không tồn tại, việc trả “khách hàng này đã bị khóa vì nợ quá hạn” có thể tiết lộ thông tin tài khoản. Tùy use case, response có thể chỉ nói “Không thể thực hiện yêu cầu với thông tin đã cung cấp”.

Domain vẫn cần mã lý do nội bộ để audit và xử lý. API adapter quyết định mức chi tiết được phép công khai theo quyền và chính sách bảo mật.

## 17. Xử lý lỗi khi dùng Domain Event và Outbox

Một use case có thể commit Order và outbox record thành công, nhưng publisher hoặc consumer gặp lỗi sau đó. Không nên đổi kết quả của command ban đầu thành thất bại nếu Order đã commit thành công.

Ví dụ:

```text
PlaceOrder
  -> Order + Outbox record commit thành công
  -> API trả OrderPlaced

Outbox Publisher
  -> gửi Integration Event
  -> broker tạm thời unavailable
  -> retry theo policy
```

Command `PlaceOrder` đã thành công; việc giao event là một tiến trình riêng cần theo dõi. Nếu consumer không xử lý được, message có thể retry hoặc chuyển dead-letter. Process Manager có thể giữ trạng thái Order đang chờ Inventory nếu giữ hàng là bước bắt buộc trước fulfillment.

Hãy phân biệt:

- **Command đã commit:** sự thật thuộc context nguồn đã được ghi nhận.
- **Message đã publish:** broker đã nhận message theo contract của publisher.
- **Consumer đã xử lý:** context đích đã hoàn thành phản ứng của nó.

Ba mốc này không đồng nghĩa. Một API không nên nói “đã giữ hàng” chỉ vì message `ReserveStock` đã được publish; cần chờ kết quả `StockReserved` nếu đó là điều kiện nghiệp vụ.

## 18. Lỗi từ hệ thống ngoài và kết quả chưa xác định

Timeout là tình huống đặc biệt. Client không nhận được response không chứng minh rằng server hoặc provider chưa xử lý request.

Ví dụ thanh toán:

1. Payment Context gửi lệnh capture với idempotency key `PAY-ORDER-123`.
2. Provider nhận và capture thành công.
3. Response bị mất trên đường truyền.
4. Payment Context nhận timeout.

Không được tự động tạo một payment attempt mới với key khác. Hãy truy vấn provider bằng reference/key cũ hoặc gửi lại cùng key nếu provider bảo đảm idempotency. Nếu không thể xác định kết quả, giữ giao dịch ở trạng thái `OutcomeUnknown`/`PendingReconciliation` và thực hiện đối soát.

Trạng thái chưa xác định là một trạng thái vận hành có ý nghĩa. Nó giúp hệ thống tránh kết luận sai rằng thanh toán thất bại hoặc thành công khi chưa có bằng chứng.

## 19. Quan sát, log và correlation

Khi một use case thất bại, cần đủ thông tin để xác định nguyên nhân mà không ghi lộ dữ liệu nhạy cảm.

Các trường hữu ích:

| Trường | Mục đích |
|---|---|
| `correlationId` / `traceId` | Theo dõi request qua nhiều service |
| `useCase` | Xác định thao tác đang chạy |
| `errorCode` | Phân loại lỗi theo contract nội bộ |
| `aggregateId` | Xác định Aggregate liên quan, nếu được phép log |
| `expectedVersion` / `actualVersion` | Điều tra concurrency conflict |
| `dependency` | Nhận diện database, broker hoặc provider gặp sự cố |
| `attempt` | Theo dõi số lần retry |
| `duration` | Phát hiện timeout hoặc latency tăng |
| `idempotencyKey` | Đối chiếu request lặp mà không log payload nhạy cảm |

Metric có thể theo dõi tỷ lệ business rejection, version conflict, transient failure, timeout chưa xác định, số lần retry, outbox backlog và dead-letter count. Nếu business rejection tăng đột biến, đó có thể là dấu hiệu thay đổi chính sách hoặc vấn đề dữ liệu, không nhất thiết là sự cố hạ tầng.

## 20. Kiểm thử từng loại lỗi

Một use case cần test các kết quả thành công lẫn các nhánh lỗi có ý nghĩa. Đừng chỉ kiểm tra rằng một exception bất kỳ được ném ra.

| Nhóm | Test cần có |
|---|---|
| Input validation | Thiếu field, sai format, số lượng âm hoặc bằng zero |
| Business rejection | Không đủ hàng, khách không đủ điều kiện, trạng thái không cho phép |
| State conflict | Hủy Order đã giao, sửa đối tượng đã đóng |
| Concurrency conflict | Hai transaction cùng đọc một version; một transaction bị từ chối khi commit |
| Infrastructure transient | Database/broker tạm thời không khả dụng; retry có giới hạn |
| Permanent infrastructure | Credential/configuration sai; không retry vô hạn |
| Unknown outcome | Timeout sau khi gửi payment command; tra cứu bằng idempotency key |
| Duplicate request/event | Cùng key hoặc event ID không tạo tác dụng nghiệp vụ hai lần |
| Transaction rollback | Lỗi ở bước cuối làm rollback tất cả thay đổi cần atomicity |
| Error mapping | Domain outcome được ánh xạ đúng status/code mà không lộ nội bộ |

### Ví dụ test business rejection

```java
@Test
void rejectsOrderWhenStockIsInsufficient() {
    StockItem stock = new StockItem(2);

    assertThrows(InsufficientStockException.class,
        () -> stock.reserve(3));

    assertEquals(2, stock.availableQuantity());
}
```

Test xác nhận domain rule và trạng thái không bị thay đổi khi hành động bị từ chối.

### Ví dụ test concurrency

Integration test cần hai transaction hoặc persistence context độc lập:

```text
Given StockItem has quantity 10 and version 4
And transaction A and B both load version 4
When A reserves 7 and commits
And B attempts to reserve 6 and commits
Then B receives a concurrency conflict
And latest available quantity remains 3
```

Không thể chứng minh optimistic locking chỉ bằng unit test trên một object trong bộ nhớ.

### Ví dụ test retry và idempotency

```text
Given Payment provider has accepted capture for key K
And the response was lost
When the application retries with the same key K
Then provider returns the existing outcome
And only one capture exists
```

Test này xác nhận ứng dụng không tạo một payment attempt mới khi kết quả trước chưa rõ.

## 21. Những sai lầm thường gặp

**Gộp mọi lỗi thành `500`.** Caller không thể phân biệt cần sửa request, tải lại dữ liệu hay thử lại sau.

**Dùng exception cho mọi business rejection.** Các kết quả dự kiến bị biến thành luồng điều khiển khó đọc và dễ bị log như lỗi hệ thống. Có thể dùng typed outcome cho các nhánh bình thường.

**Trả lỗi kỹ thuật từ domain.** Domain không nên phụ thuộc HTTP, SQL hoặc ORM exception. Chuyển đổi ở application/adapter boundary.

**Retry mọi exception.** Business rejection, lỗi cấu hình và unknown outcome không thể được xử lý bằng retry mù quáng.

**Coi mọi unique constraint violation là duplicate request.** Phải nhận diện constraint cụ thể và hiểu invariant mà nó bảo vệ.

**Bắt exception trong transaction rồi tiếp tục.** Transaction có thể đã rollback-only hoặc persistence context không còn an toàn.

**Dùng Aggregate cũ sau optimistic conflict.** Phải rollback, tải lại trong transaction mới và đánh giá lại command.

**Coi timeout là thất bại chắc chắn.** Hệ thống ngoài có thể đã xử lý. Dùng idempotency và reconciliation.

**Để API trả stack trace hoặc SQL.** Điều đó làm lộ chi tiết nội bộ và tạo contract không ổn định.

**Dùng message lỗi làm logic.** Client không nên phân tích chuỗi tiếng Việt hoặc exception message để quyết định hành vi. Hãy dùng error code ổn định.

## 22. Quy trình phân loại và xử lý lỗi cho một use case

Khi thiết kế use case, hãy đi theo các bước sau:

**Bước 1: Liệt kê kết quả nghiệp vụ.** Thành công có những dạng nào? Những lý do từ chối nào là bình thường?

**Bước 2: Xác định state conflict.** Có hành động nào chỉ hợp lệ ở một số trạng thái? Khi trạng thái không còn phù hợp, caller cần làm gì?

**Bước 3: Xác định concurrency point.** Aggregate nào có version? Có unique constraint hoặc điều kiện ghi nguyên tử nào bảo vệ invariant?

**Bước 4: Liệt kê phụ thuộc hạ tầng.** Database, broker, API provider hoặc file store có thể thất bại ra sao?

**Bước 5: Phân loại retryability.** Transient, permanent hay unknown outcome? Command có idempotent không?

**Bước 6: Định nghĩa outcome/error code.** Caller cần biết mã nào, thông tin nào và hành động tiếp theo nào?

**Bước 7: Đặt chuyển đổi đúng layer.** Domain phát biểu quy tắc; application điều phối và phân loại; adapter ánh xạ sang HTTP/message contract.

**Bước 8: Xác định transaction behavior.** Lỗi nào phải rollback? Exception xuất hiện ở flush/commit hay ngay tại lời gọi repository?

**Bước 9: Thiết kế retry và idempotency.** Retry có giới hạn, transaction mới, cùng idempotency key và reconciliation khi cần.

**Bước 10: Kiểm thử và quan sát.** Test từng loại lỗi, metric, correlation và cảnh báo cho tình huống không tự phục hồi.

## 23. Checklist đánh giá xử lý lỗi

- [ ] Business rejection được phân biệt với lỗi kỹ thuật.
- [ ] State conflict được phân biệt với concurrency conflict.
- [ ] Validation được đặt ở đúng boundary và không thay thế domain invariant.
- [ ] Domain không phụ thuộc HTTP, SQL, ORM hoặc broker exception.
- [ ] Use case có outcome/error code ổn định.
- [ ] Caller có hướng xử lý rõ cho từng loại kết quả.
- [ ] Chỉ retry lỗi có khả năng phục hồi và thao tác an toàn.
- [ ] Retry có giới hạn, backoff và transaction boundary phù hợp.
- [ ] Sau version conflict, Aggregate được tải lại trong transaction mới.
- [ ] Unique constraint được ánh xạ theo ý nghĩa constraint cụ thể.
- [ ] Unknown outcome được xử lý bằng idempotency hoặc reconciliation.
- [ ] Lỗi persistence ở flush/commit được bắt tại transaction boundary.
- [ ] Transaction rollback khi một thay đổi bắt buộc thất bại.
- [ ] API không để lộ stack trace, SQL hoặc thông tin nhạy cảm.
- [ ] Log/metric có correlation và error code hữu ích.
- [ ] Có test business rejection, conflict, transient failure, duplicate và rollback.

## 24. Bài tập tự kiểm tra

Một use case `ConfirmBooking` cần giữ một phòng trong một khoảng thời gian và thu tiền đặt cọc. Hệ thống có các tình huống:

1. Người dùng gửi thời gian trả phòng sớm hơn thời gian nhận phòng.
2. Phòng đã được người khác đặt trong lúc người dùng đang điền form.
3. Optimistic locking phát hiện version của RoomAvailability đã đổi.
4. Database mất kết nối khi commit.
5. Payment provider timeout sau khi nhận lệnh thu tiền.
6. Client gửi lại cùng request vì không nhận được response.
7. Email xác nhận thất bại sau khi Booking đã được commit.

Hãy phân loại từng tình huống và trả lời:

- Tình huống nào là validation, business rejection, state/concurrency conflict hay infrastructure failure?
- Tình huống nào có thể retry tự động?
- Tình huống nào cần tải lại và đánh giá lại domain rule?
- Tình huống nào cần idempotency key hoặc reconciliation?
- Khi email thất bại, Booking có nên bị rollback không?
- API nên trả mã lỗi hoặc trạng thái nào để client biết bước tiếp theo?

Gợi ý:

| Tình huống | Phân loại | Cách xử lý phù hợp |
|---|---|---|
| Thời gian trả phòng trước nhận phòng | Validation/domain value rule | Từ chối request và yêu cầu sửa thời gian |
| Phòng đã được đặt | Business rejection hoặc state conflict theo mô hình | Không xác nhận booking; gợi ý thời gian khác |
| Version RoomAvailability đã đổi | Concurrency conflict | Rollback, tải lại và đánh giá lại khả năng giữ phòng |
| Database mất kết nối khi commit | Infrastructure failure; kết quả commit có thể cần xác minh | Không khẳng định thất bại nếu commit outcome chưa rõ; kiểm tra theo booking/idempotency reference |
| Payment provider timeout | Unknown outcome | Tra cứu/retry cùng idempotency key, đối soát trước khi tạo lệnh mới |
| Client gửi lại request | Duplicate command | Trả lại kết quả theo idempotency key đã lưu |
| Email thất bại sau commit | Side-effect delivery failure | Retry qua outbox; Booking vẫn đã được xác nhận nếu email không phải invariant bắt buộc |

HTTP status cụ thể phụ thuộc API contract. Ví dụ, `If-Match` không còn đúng có thể trả 412; state conflict có thể trả 409; validation có thể trả 400 hoặc 422; lỗi phụ thuộc tạm thời có thể trả 503. Với kết quả thanh toán chưa xác định, response cần thể hiện trạng thái đang xác minh thay vì khẳng định thanh toán thất bại.

## Kết luận

Business rejection, conflict và infrastructure failure là những kết quả khác nhau và cần cách xử lý khác nhau. Business rejection phản ánh quy tắc domain; state conflict phản ánh hành động không phù hợp với trạng thái hiện tại; concurrency conflict cho biết dữ liệu đã thay đổi sau lần đọc; infrastructure failure phản ánh sự cố của phụ thuộc kỹ thuật. Timeout từ hệ thống ngoài còn có thể tạo ra kết quả chưa xác định, cần idempotency và đối soát.

Hãy để domain model bảo vệ quy tắc, application layer điều phối và chuyển đổi kết quả use case, còn adapter ánh xạ sang HTTP hoặc message contract. Chỉ retry khi lỗi có khả năng phục hồi và thao tác an toàn; sau concurrency conflict phải tải lại và đánh giá lại command. Mã lỗi ổn định, transaction rollback đúng, idempotency và kiểm thử từng nhánh giúp caller biết phải làm gì và giúp hệ thống giữ được tính đúng đắn khi có sự cố.
