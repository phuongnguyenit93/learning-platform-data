# Những ràng buộc phải được kiểm tra ngay trong dịch vụ sở hữu

## 1. Bối cảnh: kiểm tra ở đâu mới có hiệu lực?

Trong hệ thống microservices, mỗi năng lực nghiệp vụ có thể có API, cơ sở dữ liệu và đội phụ trách riêng. Khi người dùng thực hiện hành động như giữ vé, trừ tồn kho, hoàn tiền hay kích hoạt tài khoản, nhiều lớp có thể kiểm tra đầu vào:

- Giao diện người dùng kiểm tra dữ liệu để hướng dẫn và phản hồi nhanh.
- API gateway kiểm tra danh tính, định tuyến và giới hạn truy cập chung.
- Service gọi có thể kiểm tra điều kiện trước khi gửi yêu cầu.
- Service sở hữu năng lực nghiệp vụ quyết định có được phép thực hiện hành động hay không.
- Cơ sở dữ liệu có thể cưỡng chế một số ràng buộc ở mức lưu trữ.

Các kiểm tra ở lớp trước giúp giảm lỗi và nâng cao trải nghiệm, nhưng **không thay thế được kiểm tra tại dịch vụ có thẩm quyền**. Giá trị quan sát có thể cũ, quy tắc có thể thay đổi, client có thể bỏ qua màn hình, thông điệp có thể gửi trùng và hai yêu cầu có thể đến cùng lúc.

**Nguyên tắc cốt lõi:** Nếu một service có quyền xác nhận một hành động nghiệp vụ, service đó phải bảo vệ những ràng buộc mà hành động có thể vi phạm, ngay tại thời điểm quyết định và trong cơ chế cập nhật có khả năng chịu cạnh tranh đồng thời.

Ví dụ: Giao diện hiển thị “còn một vé”. Hai khách nhấn mua cùng lúc. Nếu cả hai chỉ dựa trên kết quả GET trước đó, hệ thống có thể bán hai vé. Service Reservation cần tự kiểm tra quyền cấp vé và thực hiện phép ghi có điều kiện hoặc giao dịch phù hợp.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt kiểm tra định dạng đầu vào, phân quyền, điều kiện tiên quyết và **bất biến nghiệp vụ**.
2. Xác định dịch vụ nào phải chịu trách nhiệm kiểm tra một ràng buộc trong hệ thống nhiều service.
3. Thiết kế đường ghi để kiểm tra và thay đổi trạng thái có tính nguyên tử theo phạm vi cần thiết.
4. Xử lý đồng thời, yêu cầu lặp, dữ liệu cũ, sự kiện đến trễ và lỗi mạng mà vẫn giữ bất biến.
5. Nhận biết ràng buộc nào cần kiểm tra tức thời, ràng buộc nào phù hợp với quy trình bất đồng bộ và đối soát.
6. Viết API contract, kiểm thử cạnh tranh và tiêu chí vận hành thể hiện đúng quyền sở hữu.

## 2. Những loại ràng buộc không nên đánh đồng

Từ “validation” thường bị dùng để gọi tất cả các phép kiểm tra. Trong thiết kế service, nên phân loại để biết ai chịu trách nhiệm và thời điểm nào phải kiểm tra.

| Loại | Ví dụ | Nơi thực thi chính |
|---|---|---|
| **Định dạng và cú pháp** | Số lượng là số nguyên dương; email có hình thức hợp lệ | Client kiểm tra sớm, API/service kiểm tra lại |
| **Quyền truy cập** | Người dùng được phép hủy đơn của chính mình | Service có thẩm quyền, dựa trên danh tính đã xác minh và chính sách |
| **Điều kiện tiên quyết nghiệp vụ** | Chỉ hủy đơn khi đơn chưa giao; chỉ giữ vé khi suất còn mở | Service sở hữu trạng thái/quyết định |
| **Bất biến trạng thái** | Số vé đã cấp không vượt sức chứa; số tiền hoàn không vượt số tiền được hoàn | Service sở hữu + transaction/ghi có điều kiện |
| **Tính duy nhất** | Một mã đặt chỗ chỉ được tạo một lần trong phạm vi quy định | Service sở hữu, thường có unique constraint ở datastore |
| **Tính nhất quán tham chiếu** | Đơn tham chiếu sản phẩm/khách hàng hợp lệ theo chính sách | Service quyết định ở ranh giới của mình và hợp đồng với owner liên quan |
| **Quy tắc liên service** | Hoàn tất đơn phải có kết quả giữ hàng và thanh toán phù hợp | Service sở hữu quy trình kết hợp với kết quả có thẩm quyền từ từng service |
| **Quy tắc hiển thị** | Cảnh báo khi dữ liệu chưa đồng bộ; nút hành động bị vô hiệu | UI/BFF, nhưng không phải nơi cưỡng chế cuối cùng |

**Điểm quan trọng:** Ràng buộc cú pháp có thể được kiểm tra ở nhiều nơi để phản hồi sớm. Bất biến bảo vệ tiền, quyền lợi, số lượng hay chuyển trạng thái phải được cưỡng chế tại nơi có quyền quyết định, thường cùng với thao tác ghi.

## 3. Dịch vụ sở hữu là ai?

Một service được xem là sở hữu một quyết định khi nó kiểm soát ý nghĩa của quyết định, dữ liệu chuẩn và cách thực hiện thay đổi hợp lệ.

Ví dụ trong hệ thống thương mại điện tử:

| Năng lực | Quyết định thuộc chủ sở hữu | Ràng buộc cần bảo vệ |
|---|---|---|
| Inventory | Có thể giữ hoặc giải phóng hàng hay không | Không giữ vượt lượng có thể cấp; reservation không giải phóng hai lần có tác động |
| Order | Có thể xác nhận, hủy hay chuyển trạng thái đơn không | Không xác nhận đơn đã hủy; không hoàn tất khi điều kiện nghiệp vụ chưa đủ |
| Payment | Có được thu hoặc hoàn tiền không | Không thu hai lần cùng yêu cầu; không hoàn vượt mức được phép |
| Pricing | Báo giá có hợp lệ theo chính sách không | Giá, phí, khuyến mãi và thời hạn áp dụng được xác định nhất quán |
| Enrollment | Học viên có thể ghi danh không | Không vượt số chỗ; không ghi danh trùng ngoài chính sách |
| Identity/Account | Danh tính và trạng thái tài khoản có hiệu lực không | Quyền, trạng thái khóa và giới hạn bảo mật theo chính sách |

Không nên suy từ tên controller hay bảng dữ liệu ra chủ sở hữu. Hỏi: **Ai có đủ thông tin và trách nhiệm để trả lời “được phép hay bị từ chối?”; ai có thể giải thích khi xảy ra sự cố?**

Nếu hai service cùng ghi một dữ liệu hoặc cùng có quyền kết luận một bất biến, ranh giới đang mơ hồ. Có thể cần đưa quyết định về một owner, hoặc phân rã thành hai bất biến độc lập với các hợp đồng rõ ràng.

### 3.1. Quyền sở hữu khác quyền đọc

Order có thể đọc số lượng tồn kho để hiển thị hoặc tối ưu trải nghiệm. Nhưng quyền đọc không cấp cho Order quyền khẳng định có thể giữ số lượng đó. Inventory mới là nơi có thẩm quyền xử lý yêu cầu giữ hàng tại thời điểm thực thi.

Tương tự, Shipping có thể nhận sự kiện đơn đã được thanh toán. Shipping không được tự kết luận giao dịch thành công chỉ từ một dòng “Đã thanh toán” trong projection có thể chậm.

### 3.2. Quyền sở hữu không nhất thiết đồng nghĩa một tiến trình riêng

Trong modular monolith, module Inventory có thể sở hữu cùng bất biến mà một inventory-service độc lập sẽ sở hữu sau này. Điều quan trọng đầu tiên là **đường ghi có một chủ sở hữu và một nơi cưỡng chế quy tắc**. Tách triển khai vật lý là quyết định kiến trúc khác, dựa vào nhu cầu vận hành và phát hành.

## 4. Vì sao kiểm tra trước ở client hoặc service gọi là chưa đủ?

### 4.1. Lỗi thời điểm kiểm tra và thời điểm sử dụng (TOCTOU)

Giả sử tồn kho còn một sản phẩm:

    10:00:00.000  Client A: GET /inventory/SKU-7  -> available=1
    10:00:00.010  Client B: GET /inventory/SKU-7  -> available=1
    10:00:00.020  Client A: POST /reserve qty=1
    10:00:00.030  Client B: POST /reserve qty=1

Hai lần đọc đều đúng ở thời điểm đọc. Nhưng hai lệnh giữ hàng không thể cùng thành công nếu chính sách cấm bán vượt. Kiểm tra GET rồi ghi bằng một UPDATE không có điều kiện tạo ra một khoảng đua (race condition).

Giải pháp không phải “làm cho GET nhanh hơn”, mà là **kiểm tra điều kiện trong cùng cơ chế quyết định nguyên tử với việc thay đổi trạng thái**: conditional update, lock, serializable transaction, atomic compare-and-set hoặc một chủ sở hữu xử lý lệnh tuần tự tùy khả năng hạ tầng.

### 4.2. Client không phải ranh giới tin cậy

Một ứng dụng web có thể ẩn nút “Hoàn tiền” khi người dùng không có quyền. Nhưng người dùng, ứng dụng tự động hoặc kẻ tấn công vẫn có thể gửi thẳng request. Do đó service xử lý Refund phải xác thực danh tính, ngữ cảnh tenant và quyền với **đúng đối tượng giao dịch**, cùng với các điều kiện nghiệp vụ.

Không nên dùng biến “isAdmin=true” do client gửi lên làm bằng chứng quyền; service phải dựa trên credential/token đã được xác thực và nguồn chính sách đáng tin cậy. Các lớp bảo mật phía trước giúp chặn sớm, nhưng owner phải giữ quyền quyết định với thao tác nhạy cảm.

### 4.3. Kết quả đọc có thể cũ

Một read model cập nhật từ sự kiện có thể trễ vài giây. Điều này chấp nhận được đối với lịch sử đơn, trang tìm kiếm hoặc dashboard theo hợp đồng. Nhưng khi chốt đơn, cấp chỗ hay hoàn tiền, service cần tham chiếu **trạng thái có thẩm quyền** phù hợp.

Không thể biến projection thành nguồn quyết định chỉ vì độ trễ quan sát thường rất nhỏ. Vấn đề là tính đúng đắn trong trường hợp xấu nhất được cam kết, không chỉ tốc độ trung bình.

### 4.4. Một số yêu cầu sẽ được gửi lặp

Mạng bị timeout có thể khiến client thử lại cùng lệnh. Queue có thể phát lại sự kiện sau khi consumer crash. Nếu service tạo effect một lần cho mỗi lần nhận message, nó có thể thu tiền hoặc cấp chỗ nhiều lần.

Service sở hữu phải xác định **idempotency** và trạng thái thực thi để xử lý yêu cầu lặp. Đây là ràng buộc nghiệp vụ về *cùng một ý định* chứ không chỉ là cấu hình retry ở gateway.

## 5. Thiết kế một command có quyền quyết định

Một API dạng command nên diễn đạt **ý định nghiệp vụ**, không mở cổng sửa tùy ý trường trạng thái.

Thay vì để Order gọi:

~~~http
PATCH /inventory/SKU-7
Content-Type: application/json

{ "available": 0 }
~~~

hãy xem xét:

~~~http
POST /inventory/reservations
Idempotency-Key: order-123-reserve-v1
Content-Type: application/json

{
  "orderId": "ord-123",
  "sku": "SKU-7",
  "quantity": 1
}
~~~

Inventory phải tự thực hiện các bước tương ứng:
1. Xác thực caller, tenant và quyền thực hiện lệnh.
2. Kiểm tra cấu trúc, loại dữ liệu, giới hạn và giá trị quantity.
3. Kiểm tra trạng thái SKU, chính sách giữ hàng, giới hạn của khách nếu có.
4. Kiểm tra yêu cầu đã được xử lý theo idempotency key chưa.
5. Thực hiện kiểm tra tồn kho và thay đổi dữ liệu trong một transaction hoặc một thao tác nguyên tử phù hợp.
6. Lưu kết quả reservation cùng thông tin phục vụ retry/audit.
7. Trả trạng thái với ngữ nghĩa đã công bố, ví dụ RESERVED, REJECTED hoặc PENDING theo hợp đồng.

**Thứ tự khái niệm không thay thế cơ chế đồng thời.** Hai request vẫn có thể đi qua bước 3 cùng lúc, nên bước 5 phải bảo vệ bất biến tại thời điểm ghi. Một bản ghi kiểm tra idempotency cũng cần cơ chế duy nhất/khóa để hai request song song không cùng tạo effect.

### 5.1. Trạng thái phản hồi có ý nghĩa

Hợp đồng có thể mô tả:
- **RESERVED:** Reservation có hiệu lực đã được ghi thành công.
- **INSUFFICIENT_STOCK:** Nguồn có thẩm quyền từ chối do thiếu số lượng.
- **INVALID_REQUEST:** Dữ liệu đầu vào không hợp lệ.
- **FORBIDDEN:** Caller không có quyền với phạm vi yêu cầu.
- **CONFLICT:** Dữ liệu thay đổi đồng thời hoặc một khóa idempotency được tái sử dụng sai.
- **PENDING:** Yêu cầu đã được nhận bền vững, nhưng quyết định cuối cùng còn chờ.
- **UNAVAILABLE / UNKNOWN:** Chưa thể xác định kết quả; client không được tự suy thành thành công hoặc thất bại.

Mã HTTP chỉ phản ánh một phần ngữ nghĩa. Ví dụ 202 Accepted cho biết yêu cầu được tiếp nhận theo hợp đồng, chưa đồng nghĩa reservation đã có hiệu lực.

## 6. Cưỡng chế bất biến trong database

### 6.1. Atomic conditional update

Ví dụ giữ hàng khi available là số lượng chưa phân bổ:

~~~sql
UPDATE inventory_stock
SET available = available - :quantity,
    reserved = reserved + :quantity,
    version = version + 1
WHERE tenant_id = :tenantId
  AND sku = :sku
  AND available >= :quantity;
~~~

Cần:
- Kiểm tra quantity > 0 và giới hạn số lượng trước khi chạy.
- Kiểm tra **số dòng cập nhật**: thành công đúng một dòng là một phần điều kiện chấp nhận; 0 dòng nghĩa là không thể giữ theo điều kiện hiện tại.
- Chạy trong transaction cùng việc tạo reservation và bản ghi outbox nếu những dữ liệu đó phải đồng bộ.
- Có unique constraint hoặc cơ chế tương đương để một intent không được tạo nhiều reservation.
- Xử lý tình huống rollback, deadlock, timeout và retry theo ngữ nghĩa của datastore.

Cách này không dựa trên một lần SELECT rồi UPDATE mù. Mệnh đề WHERE và UPDATE được thực hiện như một thao tác có điều kiện theo bảo đảm transaction/atomicity của cơ sở dữ liệu.

### 6.2. Unique constraint không chỉ là lớp tối ưu

Giả sử một học viên chỉ được ghi danh một lần vào mỗi khóa học khi còn hiệu lực. Nếu chỉ viết:

~~~text
if (!existsEnrollment(studentId, courseId)) {
    insertEnrollment(studentId, courseId);
}
~~~

hai transaction đồng thời có thể cùng thấy “chưa tồn tại”. Một unique constraint ở phạm vi phù hợp sẽ ngăn ghi trùng:

~~~sql
CREATE UNIQUE INDEX uq_enrollment_student_course
ON enrollment(tenant_id, student_id, course_id);
~~~

Ví dụ này phù hợp nếu chính sách chỉ cho **một dòng trên mỗi cặp học viên-khóa học**. Nếu nghiệp vụ cho phép nhiều đợt đăng ký trong lịch sử nhưng chỉ một đăng ký active, thiết kế cần chỉ mục có điều kiện, khóa nghiệp vụ hoặc mô hình khác theo khả năng của datastore. Không sao chép constraint khi chưa hiểu phạm vi duy nhất.

Service phải chuyển lỗi unique violation thành kết quả nghiệp vụ có thể hiểu, không chỉ phơi lỗi SQL thô ra client.

### 6.3. Check constraint và khóa ngoại

Trong phạm vi một cơ sở dữ liệu do một service sở hữu, các ràng buộc như NOT NULL, CHECK, FOREIGN KEY, UNIQUE là lớp bảo vệ mạnh đối với tính toàn vẹn lưu trữ.

Ví dụ:

~~~sql
CREATE TABLE wallet (
    wallet_id VARCHAR(64) PRIMARY KEY,
    balance_minor BIGINT NOT NULL,
    CHECK (balance_minor >= 0)
);
~~~

Nếu ví có thể thấu chi theo chính sách, CHECK balance >= 0 sẽ sai về nghiệp vụ. Schema phải phản ánh chính xác bất biến, không áp dụng nguyên tắc một cách máy móc.

**Cẩn trọng:** Constraint ở database không thay thế kiểm tra quyền hay toàn bộ ngữ nghĩa chuyển trạng thái. Database có thể không biết rằng một khoản hoàn tiền cần được đối soát trước hoặc rằng một khách không được đặt quá ba vé theo loại sự kiện.

### 6.4. Khi bất biến liên quan nhiều dòng

Ví dụ “số ghế đã giữ tại sự kiện không vượt tổng số ghế” có thể cần tính tổng từ nhiều bản ghi. SELECT SUM rồi INSERT trong transaction ở isolation thấp có thể tạo write skew hoặc phantom, tùy cơ sở dữ liệu.

Các phương án:
- Một hàng counter/aggregate sở hữu giới hạn và cập nhật có điều kiện.
- Lock phù hợp lên aggregate và phạm vi dữ liệu quyết định.
- Serializable transaction với khả năng retry khi serialization failure.
- Phân bổ trước quota hoặc chỗ cụ thể có unique key.
- Một tiến trình xử lý lệnh tuần tự theo key, nếu độ sẵn sàng và throughput cho phép.

Phương án nào đúng còn tùy engine, isolation, truy cập đọc/ghi và khả năng crash. **Đừng xem việc đặt @Transactional là tự động loại bỏ mọi race condition.**

## 7. Transaction, isolation và phạm vi aggregate

### 7.1. Một ràng buộc nên được bảo vệ ở phạm vi nhỏ nhất đủ đúng

Trong thiết kế hướng miền, **aggregate** là phạm vi của những bất biến cần được kiểm soát cùng một giao dịch. Ví dụ Reservation có thể bảo vệ vòng đời giữ chỗ; InventoryStock bảo vệ số lượng khả dụng. Không nên chọn aggregate chỉ vì quan hệ khóa ngoại, mà dựa vào điều kiện cần đúng ngay.

Không có quy tắc “mỗi service là một transaction cho mọi dữ liệu” hoặc “mỗi aggregate bắt buộc là một bảng”. Một service có thể có nhiều aggregate và nhiều transaction cục bộ.

### 7.2. Các mức isolation giải quyết những hiện tượng khác nhau

- **Read committed:** Ngăn đọc dữ liệu chưa commit; không tự ngăn mọi lost update hoặc tình huống kiểm tra trước khi ghi sau.
- **Repeatable read:** Có thể giữ snapshot ổn định cho một transaction theo cơ chế datastore; không nên suy rằng mọi loại write skew đều bị loại bỏ.
- **Serializable:** Các transaction cam kết tương đương một lịch tuần tự hợp lệ; có thể hủy một giao dịch cạnh tranh và yêu cầu thử lại.

Hành vi cụ thể của repeatable read, row lock và serialization failure khác nhau giữa PostgreSQL, MySQL/InnoDB và các hệ dữ liệu khác. Hãy xác minh theo datastore thực tế thay vì chỉ chọn một enum isolation trong annotation.

### 7.3. Optimistic locking

Khi đối tượng ít xung đột, có thể giữ một version:

~~~sql
UPDATE orders
SET status = :newStatus,
    version = version + 1
WHERE order_id = :orderId
  AND version = :expectedVersion
  AND status = :expectedStatus;
~~~

Nếu update 0 dòng, caller không được giả vờ đã chuyển trạng thái. Service có thể đọc lại, giải thích conflict hoặc đánh giá một lệnh retry tùy nghiệp vụ.

Optimistic locking kiểm soát việc dữ liệu thay đổi ngoài dự kiến giữa đọc và ghi. Nó không thay thế việc định nghĩa những **chuyển trạng thái hợp lệ**.

### 7.4. Pessimistic locking

Khóa dòng hoặc phạm vi dữ liệu có thể thích hợp khi xung đột nhiều và phạm vi quyết định nhỏ. Đổi lại là thời gian chờ, deadlock và giảm thông lượng. Giữ transaction ngắn, tránh gọi mạng hoặc đợi người dùng trong khi giữ khóa database.

Các thao tác thu tiền với provider bên ngoài thường không nên đặt trong transaction database đang giữ khóa, vì mạng có thể chậm hoặc trả kết quả không xác định.

## 8. Ví dụ Java/Spring: kiểm tra ở đúng nơi

Giả sử Inventory là service sở hữu số lượng có thể giữ. Đường xử lý có thể gồm controller → application service → repository/domain → transaction.

### 8.1. Kiểm tra ở API boundary

~~~java
public record ReserveStockRequest(
    @NotBlank String orderId,
    @NotBlank String sku,
    @Positive int quantity
) {}
~~~

Bean Validation kiểm tra hình thức và những điều kiện số học đơn giản. Nó không biết lượng tồn kho còn bao nhiêu, đơn có được phép giữ hàng không hoặc request đã xử lý trước đó chưa.

### 8.2. Application service bảo vệ ý định và điều kiện

Mã dưới đây là **giả mã Java có cấu trúc Spring** để thể hiện trách nhiệm, không phải ứng dụng hoàn chỉnh có thể chạy ngay:

~~~java
@Service
public class InventoryReservationService {

    private final StockRepository stockRepository;
    private final ReservationRepository reservationRepository;
    private final OutboxRepository outboxRepository;

    @Transactional
    public ReserveResult reserve(
            AuthenticatedCaller caller,
            ReserveCommand command) {

        // Kiểm tra caller có quyền với tenant/order/scope phù hợp.
        authorization.requireCanReserve(caller, command);

        // Kiểm tra lệnh trùng bằng khóa nghiệp vụ hoặc idempotency key.
        // Ràng buộc UNIQUE ở datastore vẫn cần để bảo vệ request đồng thời.
        Optional<Reservation> prior =
            reservationRepository.findByRequestKey(command.requestKey());

        if (prior.isPresent()) {
            return ReserveResult.from(prior.get());
        }

        int updated = stockRepository.reserveIfAvailable(
            caller.tenantId(),
            command.sku(),
            command.quantity()
        );

        if (updated != 1) {
            throw new InsufficientStockException(command.sku());
        }

        Reservation reservation = reservationRepository.insert(
            caller.tenantId(),
            command.orderId(),
            command.sku(),
            command.quantity(),
            command.requestKey()
        );

        outboxRepository.append(
            InventoryReservedEvent.from(reservation)
        );

        return ReserveResult.from(reservation);
    }
}
~~~

Mã giả minh họa luồng, nhưng để triển khai an toàn cần bổ sung:
- Repository cập nhật tồn kho có điều kiện bằng **một lệnh SQL nguyên tử** hoặc cách tương đương.
- UNIQUE constraint theo đúng phạm vi requestKey/tenant để giải quyết hai request chạy song song.
- Phân biệt trường hợp unique conflict do **cùng ý định** với requestKey trùng nhưng payload khác; không tự trả thành công cho hai ý định khác nhau.
- Khi insert reservation lỗi trong transaction, thay đổi stock cũng rollback.
- Các trường hợp database serialization failure, timeout và retry được xử lý có giới hạn ở phía phù hợp.
- Việc phát event ra broker diễn ra sau thông qua outbox; không gọi broker như một thao tác độc lập được cho là nguyên tử với commit.
- Tránh thực hiện lời gọi mạng tới Payment/Order bên trong transaction Inventory đang giữ khóa.

### 8.3. Một ràng buộc đơn giản, hai yêu cầu đồng thời

Giả sử available = 1 và hai lệnh có requestKey khác nhau, mỗi lệnh giữ 1:
- Cả hai bắt đầu gần như đồng thời.
- Thao tác có điều kiện tại database cho phép tối đa một lệnh giảm available từ 1 xuống 0.
- Lệnh còn lại nhận 0 updated rows hoặc conflict theo cơ chế datastore.
- Kết quả kinh doanh: một reservation được xác nhận, một lệnh bị từ chối hoặc yêu cầu thử lại với chính sách đã công bố.

Chỉ có một điều quan trọng: **bất biến vẫn đúng khi lệnh đến đồng thời**. Đảm bảo này phải được kiểm chứng trong điều kiện cạnh tranh thực tế, không suy ra từ việc chạy tuần tự trong unit test.

## 9. State machine: ràng buộc về chuyển trạng thái

Không phải mọi bất biến đều diễn đạt bằng số học. Nhiều năng lực cần giới hạn chuyển trạng thái.

Ví dụ Order:

    DRAFT  ------submit------> PENDING
    PENDING ----confirm-----> CONFIRMED
    PENDING ----cancel------> CANCELLED
    CONFIRMED --ship-------> SHIPPED
    CONFIRMED --cancel?----> Theo chính sách nghiệp vụ riêng
    CANCELLED --confirm----> BỊ TỪ CHỐI

Không dùng một PATCH status tổng quát cho mọi consumer. Service sở hữu Order cần xác định command, điều kiện chuyển và tác động của từng bước.

Một ví dụ câu lệnh:

~~~sql
UPDATE orders
SET status = 'CONFIRMED',
    version = version + 1
WHERE order_id = :orderId
  AND status = 'PENDING'
  AND version = :expectedVersion;
~~~

Nếu sự kiện PaymentSucceeded đến sau khi đơn đã chuyển sang CANCELLED, Order không thể cập nhật mù sang CONFIRMED. Nó phải xử lý theo policy: từ chối chuyển, tạo yêu cầu hoàn tiền hoặc mở quy trình điều tra.

### 9.1. Trạng thái terminal và sự kiện đến trễ

Một service có thể nhận các thông điệp:
1. PaymentSucceeded cho attempt A.
2. OrderCancelled do hết hạn.
3. PaymentSucceeded bị phát lại hoặc đến trễ.

Trạng thái cuối cùng phải được quyết định bởi **state machine của Order**, liên hệ đúng paymentAttempt, version và chính sách nghiệp vụ. Không thể chỉ lấy sự kiện đến cuối cùng làm trạng thái chuẩn.

### 9.2. Thời gian cũng là dữ liệu nghiệp vụ

Quy tắc “chỉ được hủy trong 15 phút” cần nói rõ:
- 15 phút tính từ thời điểm nào?
- Dùng thời gian đáng tin do server xác định hay thời gian client?
- Nếu request được gửi trước hạn nhưng xử lý sau hạn, chính sách xét thời điểm nào?
- Khi transaction kéo dài, quy tắc được kiểm tra tại thời điểm ra quyết định nào?
- Thời gian lệch giữa các service được xử lý ra sao?

Dịch vụ sở hữu phải định nghĩa và cưỡng chế quy tắc thời gian, không tin timestamp do client gửi làm điều kiện duy nhất.

## 10. Phân quyền cũng cần kiểm tra tại nơi có thẩm quyền

### 10.1. Xác thực caller không đồng nghĩa được phép thao tác

Gateway có thể xác nhận một token JWT hợp lệ. Nhưng token hợp lệ chưa chứng minh người dùng được hoàn tiền cho paymentId bất kỳ hoặc xem đơn của tenant khác.

Payment vẫn cần xác minh:
- Caller/actor có vai trò và scope phù hợp.
- Tài nguyên thuộc tenant/đối tượng được phép.
- Trạng thái giao dịch cho phép hành động.
- Số tiền, lý do và ngưỡng hoàn tiền hợp lệ.
- Các phê duyệt nghiệp vụ bắt buộc đã tồn tại nếu chính sách yêu cầu.

### 10.2. Ngăn nhầm phạm vi tenant

Mọi lookup và write quan trọng nên sử dụng phạm vi tenant đã xác minh, không chỉ dựa trên ID tài nguyên:

~~~sql
SELECT status, amount_minor
FROM payments
WHERE tenant_id = :authenticatedTenantId
  AND payment_id = :paymentId;
~~~

Và khi UPDATE, cũng nên đưa điều kiện tenant/owner vào điều kiện ghi. Nếu truy vấn theo paymentId đơn thuần rồi giả định tenantId đã đúng ở API layer, một đường nội bộ khác có thể tạo lỗ hổng.

Không tin tenantId được cung cấp tùy ý trong request nếu hệ thống lấy tenant từ credential hoặc ngữ cảnh được xác thực. Kiểm tra phạm vi đối tượng cần xảy ra **trong cùng decision path** với thao tác.

### 10.3. Quyền của service gọi

Khi Order gọi Payment, Payment cần xác minh service identity và quyền thực hiện lệnh. Nếu hệ thống hỗ trợ hành động thay người dùng, cần chính sách truyền danh tính người dùng và chứng cứ ủy quyền rõ ràng. Việc Order là service nội bộ không làm mọi lệnh thanh toán tự động hợp lệ.

Một service có thể có quyền yêu cầu “thu tiền theo orderId”, nhưng không có quyền gọi “hoàn tiền tùy ý” chỉ vì cùng nằm trong mạng nội bộ.

## 11. Idempotency: cùng ý định chỉ tạo effect phù hợp

### 11.1. Khi một request bị timeout

Client gửi ChargePayment rồi không nhận phản hồi. Không thể kết luận khoản thu chưa được thực hiện; provider có thể đã chấp nhận nhưng phản hồi bị mất.

Nếu client gửi request mới với một key mới, Payment có nguy cơ tạo khoản thu thứ hai. Quyền sở hữu Payment bao gồm việc định danh **cùng ý định nghiệp vụ** và hỗ trợ client tra cứu kết quả.

Hợp đồng thường cần:
- Idempotency key có phạm vi rõ (caller, tenant, command type, resource).
- Cùng key, cùng request hợp lệ trả kết quả đã ghi hoặc trạng thái đang xử lý.
- Cùng key, payload khác cần phản hồi conflict theo chính sách.
- Thời hạn lưu key và cách truy vấn lại sau thời hạn.
- Unique constraint cho request key và cách xử lý hai request cạnh tranh.
- Định danh phù hợp được truyền tới provider bên ngoài nếu provider hỗ trợ.

### 11.2. Idempotent không có nghĩa mọi retry đều an toàn

Một API GET idempotent về thay đổi dữ liệu nhưng vẫn có thể phản hồi dữ liệu mới. Một command ReserveStock có thể trở nên idempotent khi dùng requestKey. Nhưng retry với **khóa khác** vẫn có thể tạo reservation mới.

Nếu một worker nhận lại OrderConfirmed, nó cần tránh gửi cùng email vô số lần theo policy và công cụ của nhà cung cấp. Phần gửi email ngoài transaction cục bộ có thể có giới hạn chống trùng khác với cập nhật database.

### 11.3. Event consumer cần chịu được at-least-once

Một mẫu xử lý trong transaction consumer:

~~~text
receive(event)
begin transaction
  if processed_events.contains(event.eventId):
      commit
      ack
      return

  validate event and business transition
  update local projection/state
  insert processed_events(event.eventId)
commit
ack
~~~

Cần UNIQUE constraint để hai consumer không thể đồng thời áp dụng effect rồi cùng ghi nhận eventId. Với event có version, còn cần chính sách xử lý sai thứ tự và missing versions.

Đánh dấu xử lý và cập nhật dữ liệu nên cùng transaction cục bộ khi có thể. Nếu effect là gọi một API bên ngoài, cần thêm idempotency key và đối soát với hệ ngoài vì transaction cục bộ không bao trùm lời gọi đó.

## 12. Ràng buộc liên service: không có transaction chung mặc định

Một quy trình thanh toán đơn hàng cần nhiều năng lực:
- Inventory giữ hàng.
- Payment thu tiền.
- Order xác nhận đơn.
- Notification gửi kết quả.

Mỗi service sở hữu dữ liệu và các ràng buộc cục bộ. Một command từ Order không cấp quyền cho Payment bỏ qua quy tắc thu tiền hay cho Inventory tự giảm lượng tồn quá giới hạn.

### 12.1. Tách bất biến cục bộ khỏi điều kiện hoàn thành quy trình

**Bất biến cục bộ:** “Inventory không cấp quá lượng hàng khả dụng”. Điều này phải được bảo vệ tại Inventory khi thực thi ReserveStock.

**Điều kiện hoàn thành quy trình:** “Chỉ xác nhận Order khi đã giữ hàng và Payment có kết quả hợp lệ”. Order có thể sở hữu state machine của quy trình; nó dựa trên chứng cứ có thẩm quyền từ Inventory và Payment, không trực tiếp sửa bảng của họ.

Sơ đồ:

    Order: PENDING_STOCK
        |
        | ReserveStock command
        v
    Inventory: kiểm tra + commit reservation
        |
        | InventoryReserved event/result
        v
    Order: PENDING_PAYMENT
        |
        | ChargePayment command
        v
    Payment: kiểm tra + commit payment state
        |
        | PaymentCaptured event/result
        v
    Order: CONFIRMED

Đây là luồng minh họa. Trong hệ thống thực tế còn có giao dịch không chắc chắn, hết hạn giữ hàng, đơn bị hủy đồng thời và nghĩa vụ hoàn tiền.

### 12.2. Kết quả chậm không cho phép bỏ ràng buộc

Order có thể chờ PaymentSucceeded trong vài giây. Chậm không có nghĩa Payment thất bại; timeout chỉ nói chưa có kết quả trong thời gian quan sát. Order nên chuyển trạng thái PENDING_VERIFICATION hoặc tương đương, truy vấn trạng thái và xử lý theo timeout chính sách.

Nếu Order hết hạn trước khi Payment xác nhận, cần quy tắc rõ ràng về việc gia hạn, hủy, hoàn tiền hoặc xử lý thủ công. Không service nào nên tự đặt quy tắc thay chủ sở hữu còn lại.

### 12.3. Saga và bù trừ

Một saga kết hợp nhiều transaction cục bộ, có thể xử lý bằng orchestration hoặc choreography. Nếu Payment thất bại sau khi Inventory giữ hàng, Order yêu cầu Inventory giải phóng reservation.

**Giải phóng** phải là command có kiểm tra tại Inventory:
- Reservation có thuộc đúng Order không?
- Trạng thái hiện tại cho phép release không?
- Nếu đã release, cùng request có làm tăng tồn thêm lần nữa không?
- Nếu reservation đã hết hạn hoặc đã được tiêu thụ, hành động được phép là gì?

Inventory không chỉ “cộng lại số lượng” khi nhận một event ReleaseRequested bất kỳ. Mọi chuyển trạng thái có tác động đều phải bảo vệ bất biến cục bộ.

### 12.4. Khi bất biến thật sự xuyên nhiều miền

Không phải quy tắc nào cũng có thể đặt gọn ở một service. Ví dụ “Không giao hàng nếu chưa đủ điều kiện thanh toán và chưa vượt hạn mức tín dụng” có thể cần chứng cứ từ Payment, Credit và Shipping.

Các lựa chọn:
1. **Xác định một chủ sở hữu quyết định** phát lệnh giao hàng dựa trên những xác nhận có thẩm quyền.
2. **Thiết kế reservation/authorization token** có thời hạn, phạm vi và khả năng xác minh.
3. **Gom những dữ liệu luôn cần transaction nguyên tử** vào cùng ranh giới nếu có cơ sở nghiệp vụ.
4. **Chấp nhận trạng thái chờ và bù trừ** khi không thể bảo đảm mọi bước tức thời.

Điều quan trọng là mô tả giới hạn rõ: ai có quyền xác nhận “đủ điều kiện”, bằng chứng có hiệu lực đến lúc nào, và chuyện gì xảy ra nếu bằng chứng hết hạn. Đừng giả định có transaction ACID xuyên mọi service chỉ vì quy trình gọi API tuần tự.

## 13. Outbox và các ràng buộc liên quan đến sự kiện

Một lỗi phổ biến:

~~~text
1. Commit status = CONFIRMED trong Order DB
2. Publish OrderConfirmed lên broker
~~~

Nếu ứng dụng chết giữa hai bước, đơn đã xác nhận nhưng consumer không nhận được sự kiện. Đảo thứ tự thành publish trước commit lại có nguy cơ thông báo cho một trạng thái cuối cùng rollback.

**Transactional outbox** ghi thay đổi trạng thái và bản ghi cần phát trong cùng transaction cục bộ:

~~~text
begin transaction
  kiểm tra trạng thái Order và bằng chứng nghiệp vụ
  UPDATE Order sang CONFIRMED nếu hợp lệ
  INSERT Outbox(eventId, type=OrderConfirmed, payload, version)
commit

publisher: đọc Outbox -> publish broker -> đánh dấu đã gửi
~~~

Phát lại có thể xảy ra nếu publisher crash sau broker ACK và trước lúc đánh dấu đã gửi. Vì vậy consumer vẫn cần idempotency, version guard và cơ chế replay phù hợp.

Outbox bảo vệ quan hệ giữa **trạng thái cục bộ và ý định phát sự kiện**; nó không làm tất cả consumer áp dụng trong một transaction và không bảo đảm thời gian hội tụ cố định.

### 13.1. Trạng thái dựa trên sự kiện phải có nguồn thẩm quyền

Service Notification nhận OrderConfirmed có thể gửi email. Nó không được tự tạo sự kiện OrderConfirmed chỉ vì email đã được gửi. Tương tự, consumer báo cáo không được tự sửa Payment thành CAPTURED vì nhận được một snapshot có trường paid=true.

Sự kiện nên mô tả sự thật đã được chủ sở hữu quyết định và công bố. Nơi tiêu thụ chỉ áp dụng tác động **trong phạm vi trách nhiệm của mình**.

## 14. Tham chiếu, bản sao và dữ liệu cũ

### 14.1. Dữ liệu phụ thuộc bên ngoài có thể đổi

Order có thể tham chiếu customerId, skuId và priceQuoteId. Tại thời điểm tạo đơn, Order cần biết những tham chiếu ấy có được phép theo nghiệp vụ. Nhưng dữ liệu nguồn có thể đổi ngay sau khi kiểm tra.

Để bảo vệ kết quả:
- Dùng quote hoặc reservation có ID, version và thời hạn hợp lệ.
- Lưu snapshot những thông tin phải giữ theo lịch sử, chẳng hạn đơn giá tại lúc chốt.
- Thiết kế điều kiện tại nguồn có thẩm quyền thay vì dùng một bản GET cũ để quyết định.
- Nếu có quyền thay đổi xuyên hai miền, xác định cách hết hạn/thu hồi bằng hợp đồng và state machine.

### 14.2. Snapshot khác dữ liệu hiện tại

Một đơn chốt với đơn giá 100.000 đồng. Sau đó Pricing đổi giá hiện tại thành 110.000 đồng. Order vẫn có thể giữ snapshot 100.000 vì đó là sự thật của đơn đã chốt; Pricing vẫn sở hữu chính sách giá đang áp dụng cho lần mua mới.

Không nên dùng snapshot 100.000 của Order để báo giá cho đơn khác, cũng không tự cập nhật mọi hóa đơn cũ khi giá hiện tại thay đổi.

### 14.3. Projection phục vụ đọc không ra quyết định

Trang “còn 2 chỗ” có thể là dữ liệu từ cache cập nhật vài giây một lần. Nó phù hợp để hiển thị cùng thông báo “số chỗ có thể thay đổi”. Nhưng ReserveSeat vẫn phải kiểm tra và ghi tại Reservation/Inventory với cơ chế nguyên tử.

**Quy tắc:** Nếu dữ liệu có thể cũ hoặc được sao chép, chỉ dùng nó làm cơ sở ra quyết định khi rủi ro và hợp đồng nghiệp vụ cho phép. Với bất biến cứng, dùng authority hoặc một quyền phân bổ đã được cấp rõ ràng.

## 15. Phân biệt ràng buộc cứng, ràng buộc mềm và kiểm tra sau

Không phải mọi điều kiện đều cần dừng request ngay.

### 15.1. Ràng buộc cứng

Là điều không thể cho phép vi phạm tại thời điểm chấp nhận hành động, ví dụ:
- Không cấp cùng một seatId cho hai reservation đang hiệu lực.
- Không ghi nhận hoàn tiền vượt số tiền được phép hoàn.
- Không cho tài khoản bị khóa tự chuyển trạng thái sang ACTIVE bằng một API không có thẩm quyền.
- Không xác nhận lệnh có chữ ký hoặc quyền truy cập không hợp lệ.

Cần bảo vệ tại service sở hữu và nguồn ghi tương ứng.

### 15.2. Ràng buộc mềm hoặc mục tiêu vận hành

Ví dụ:
- Gửi email xác nhận trong một phút sau khi đặt hàng.
- Cập nhật dashboard trong vòng vài giây.
- Tính điểm thưởng sau khi nhận sự kiện thanh toán.
- Gợi ý sản phẩm cần phản ánh danh mục gần đây.

Những điều này có thể được xử lý bất đồng bộ, theo SLO, retry và cơ chế bù trừ. Service vẫn cần chịu trách nhiệm, đo mức trễ và khôi phục khi quy trình kẹt.

### 15.3. Kiểm tra sau không sửa được mọi lỗi

Một báo cáo phát hiện bán vượt 100 vé sau khi khách đã thanh toán không thể thay thế quy tắc giữ chỗ tại điểm cấp vé. Đối soát hữu ích để phát hiện sự cố và khôi phục, nhưng không thích hợp làm **cơ chế duy nhất** cho bất biến không thể chấp nhận vi phạm.

Ngược lại, thống kê truy cập được cộng dồn trễ 10 giây có thể chấp nhận được nếu nghiệp vụ không dùng số liệu đó để cấp quyền hoặc thu tiền.

## 16. Mã lỗi và cách phản hồi có trách nhiệm

Service sở hữu phải phân biệt **từ chối theo quy tắc** với **lỗi kỹ thuật**.

| Kết quả | Ví dụ | Hành động caller |
|---|---|---|
| Validation error | Quantity = -1 | Sửa dữ liệu đầu vào |
| Authorization denied | Không được hủy đơn của người khác | Không retry tự động, xử lý quyền |
| Business rejection | Hết hàng, vượt hạn mức | Thông báo kết quả hợp lệ của nghiệp vụ |
| Optimistic conflict | Version đã đổi | Đọc lại và quyết định retry phù hợp |
| Duplicate accepted | Request key đã xử lý với cùng payload | Nhận lại kết quả cũ/trạng thái |
| Duplicate conflict | Cùng key nhưng payload khác | Xử lý lỗi dùng sai khóa |
| Temporary unavailable | DB/broker không sẵn sàng | Retry có backoff khi an toàn |
| Outcome unknown | Payment timeout sau khi provider có thể đã xử lý | Tra trạng thái, đối soát, tránh tạo yêu cầu mới |

Nếu trả lỗi “Internal Server Error” cho mọi loại, caller khó xử lý đúng và có thể lặp lại lệnh nguy hiểm. Ngược lại, phơi chi tiết constraint SQL hoặc tên bảng nội bộ không hữu ích cho contract và có thể làm lộ cấu trúc hệ thống.

### 16.1. Không coi lỗi timeout là phủ định của thành công

Một lệnh mạng có thể hoàn tất bên phía provider dù caller không nhận phản hồi. Chính vì vậy Payment hoặc Reservation cần ID tra cứu, idempotency và trạng thái trung gian. Kết quả “chưa biết” là trạng thái hợp lệ trong hệ thống phân tán, không được tự biến thành thất bại để thử một lệnh mới không kiểm soát.

## 17. Kiểm thử chứng minh ràng buộc được cưỡng chế

Kiểm thử nên hướng vào hành vi có thể vi phạm bất biến, không chỉ xác nhận một phương thức gọi helper validation.

### 17.1. Kiểm thử đơn vị của quy tắc miền

Ví dụ:
- Không cho chuyển Order từ CANCELLED sang CONFIRMED.
- Không cho tạo reservation quantity <= 0.
- Không cho hoàn tiền vượt số tiền đã thu sau khi tính đến khoản hoàn trước đó.
- Không cho cùng một idempotency key gắn với hai payload khác nhau theo policy.

Unit test có thể kiểm tra quyết định miền ở nhiều trạng thái, nhưng **không chứng minh** cạnh tranh đồng thời an toàn.

### 17.2. Kiểm thử tích hợp với datastore thật

Tình huống quan trọng cho Inventory: bắt đầu available=1, cho hai transaction đồng thời ReserveStock 1 với hai key khác nhau. Kỳ vọng một lệnh được chấp nhận, một bị từ chối hoặc xử lý lại theo contract; available không âm và reserved tương ứng chính xác.

Cần chạy với **database engine và isolation thực tế**. H2 hoặc mock repository có thể cho hành vi khóa, isolation hoặc unique constraint khác với PostgreSQL/MySQL trong sản xuất.

### 17.3. Kiểm thử replay và crash

- Gửi cùng command hai lần liên tiếp và đồng thời.
- Publisher crash sau commit, trước publish.
- Publisher publish thành công rồi crash trước đánh dấu outbox.
- Consumer apply xong nhưng chưa ACK, sau đó nhận lại message.
- Sự kiện version 8 đến trước version 7.
- User đổi tenant hoặc quyền bị thu hồi giữa lúc hiển thị và khi gửi command.
- Hai lệnh CancelOrder và ConfirmOrder đến cạnh tranh.
- Một yêu cầu hoàn tiền timeout sau khi provider đã thực hiện effect.

Mỗi tình huống có **bất biến có thể đo**. Không đánh giá “đạt” chỉ vì API trả HTTP 200; cần kiểm tra trạng thái nguồn, số tác động bên ngoài, outbox, bản ghi idempotency và các điều kiện nghiệp vụ.

### 17.4. Contract tests

Consumer-driven contract tests có thể chứng minh:
- Provider từ chối ReserveStock khi không đủ hàng theo error contract.
- Command lặp cùng key không tạo reservation mới.
- Response/Event có trường, enum và ngữ nghĩa đã công bố.
- Consumer cũ tiếp tục hoạt động trong giai đoạn triển khai phiên bản mới.

Kiểm thử hợp đồng không thay thế kiểm thử transaction, concurrency, bảo mật tài nguyên hay điều kiện sống của workflow.

## 18. Quan sát và vận hành khi ràng buộc bị từ chối

Một hệ thống có thể từ chối hợp lệ nhiều lệnh vì hết hàng. Không nên xem mọi từ chối nghiệp vụ là lỗi hệ thống. Tuy nhiên tỷ lệ từ chối tăng bất thường có thể báo hiệu vấn đề dữ liệu hoặc trải nghiệm.

Các chỉ số cần cân nhắc:
- Số command được chấp nhận/từ chối theo loại lý do nghiệp vụ.
- Tỷ lệ concurrency conflict, optimistic lock failure và transaction retry.
- Tỷ lệ idempotency hit, key conflict và duplicate event.
- Transaction deadlock/serialization failure, thời gian chờ lock.
- Số đơn ở trạng thái PENDING quá hạn, số yêu cầu cần đối soát.
- Số lần vi phạm bất biến phát hiện bởi kiểm tra toàn vẹn định kỳ (mục tiêu bằng 0 ở phạm vi yêu cầu cứng).
- Độ trễ command, lỗi dependency, backlog outbox và lag consumer.
- Tỷ lệ forbidden/tenant mismatch; phát hiện truy cập trái phép theo chính sách bảo mật.

**Cách đọc chỉ số:** Một đợt tăng lỗi INSUFFICIENT_STOCK khi bán vé hot có thể là kết quả bình thường của số chỗ hạn chế. Nhưng xuất hiện negative inventory hoặc hai reservation cùng giữ seatId là dấu hiệu bất biến không được bảo vệ.

Báo động nên được thiết kế theo **tác động và ngưỡng kỳ vọng**, tránh biến mọi từ chối nghiệp vụ thành cảnh báo khẩn.

## 19. Các lỗi kiến trúc thường gặp

**Lỗi 1 — Chỉ kiểm tra ở frontend.** Người dùng có thể gọi API trực tiếp hoặc giá trị có thể thay đổi sau lần GET. Service sở hữu phải kiểm tra lại tại lúc ghi.

**Lỗi 2 — Gateway thay service quyết định.** Gateway có thể xác thực token nhưng thường không có dữ liệu và quy tắc đủ để quyết định refund, seat allocation hoặc order transition.

**Lỗi 3 — SELECT rồi UPDATE không có điều kiện.** Hai transaction cùng đọc trạng thái cũ và có thể cùng thành công. Dùng atomic update, concurrency control hoặc isolation phù hợp.

**Lỗi 4 — @Transactional được hiểu là “không thể có race”.** Transaction tự động không chỉ ra isolation hay bất biến. Cần xét điều kiện WHERE, khóa, unique constraint và các transaction cạnh tranh.

**Lỗi 5 — Service khác trực tiếp sửa bảng owner.** Order tự UPDATE inventory_stock sẽ bỏ qua policy và làm migration khó kiểm soát. Tương tác phải thông qua command/API/sự kiện có thẩm quyền.

**Lỗi 6 — Chỉ có kiểm tra domain trong code, thiếu ràng buộc lưu trữ.** Trong cạnh tranh đồng thời hoặc khi có job nội bộ khác, có thể ghi trạng thái vi phạm. Dùng UNIQUE/CHECK/FOREIGN KEY/conditional write khi phù hợp và thiết kế chính sách phù hợp.

**Lỗi 7 — Dùng read model để chốt giao dịch.** Projection chậm có thể đưa quyết định dựa trên dữ liệu cũ. Đưa quyết định về nguồn chuẩn hoặc quyền đã được cấp xác thực.

**Lỗi 8 — Nhầm “event được nhận” với “quyết định được phê duyệt”.** Consumer không được tự tạo một trạng thái nghiệp vụ mới vì có sự kiện liên quan đến từ khóa status.

**Lỗi 9 — Retry tự do mọi lỗi.** Một lệnh thanh toán timeout có thể đã thành công. Retry khác key có thể tạo effect lặp. Cần policy theo loại lỗi và idempotency.

**Lỗi 10 — Bù trừ bằng phép ghi ngược đơn giản.** ReleaseStock lặp lại hai lần có thể làm tăng stock gấp đôi; refund lặp có thể hoàn vượt tiền. Hành động bù trừ phải là command do owner kiểm tra.

**Lỗi 11 — Dùng timestamp client làm sự thật.** Client có thể sai đồng hồ hoặc gửi giá trị có chủ ý; quy tắc thời gian cần nguồn và chính sách rõ.

**Lỗi 12 — Một owner cho “bất kỳ dữ liệu nào mang cùng tên”.** “Giá hiện tại” thuộc Pricing, còn “đơn giá đã chốt” thuộc Order. Chúng có thể là hai sự thật khác nhau theo thời điểm, không phải hai nơi cùng ghi cùng một trường.

## 20. Checklist thiết kế cho một command mới

Khi thêm một lệnh có tác động, hãy trả lời bằng chứng cụ thể:

1. **Owner:** Service nào có quyền chấp nhận/từ chối? Ai phụ trách sự cố?
2. **Bất biến:** Viết quy tắc thành mệnh đề có thể kiểm thử; phạm vi theo tenant, user, item hay aggregate?
3. **Dữ liệu có thẩm quyền:** Đang ở đâu? Có dùng cache/projection làm điều kiện ra quyết định không?
4. **Phân quyền:** Caller/actor/tenant/resource được xác minh tại đâu? Có đường gọi nội bộ bỏ qua không?
5. **Nguyên tử:** Kiểm tra và ghi nào cần cùng transaction? Isolation/lock/unique constraint nào bảo vệ?
6. **Đồng thời:** Hai command khác nhau đến cùng lúc có thể cùng được chấp nhận sai không?
7. **Lặp:** Cùng command retry có gây effect thêm không? Idempotency key được giữ bao lâu?
8. **Trạng thái:** Những chuyển trạng thái nào hợp lệ? Trường hợp sự kiện đến muộn xử lý ra sao?
9. **Liên service:** Kết quả nào do service khác quyết định? Có timeout, unknown outcome hoặc saga không?
10. **Hợp đồng:** Error code và kết quả có giúp caller phân biệt từ chối nghiệp vụ với lỗi tạm thời không?
11. **Lưu vết:** Có audit và event/outbox nào phải commit cùng cập nhật trạng thái không?
12. **Kiểm chứng:** Test nào chứng minh bất biến vẫn đúng dưới cạnh tranh, retry, crash và thay đổi quyền?

Checklist giúp thiết kế trước khi triển khai. Không phải mục nào cũng cần phức tạp như Payment; độ nghiêm ngặt phụ thuộc tác động của thao tác.

## 21. Bài thực hành: giữ chỗ lớp học có thanh toán

Một nền tảng học trực tuyến bán 30 chỗ cho một lớp. Các thành phần:
- **Enrollment:** Đăng ký và giữ chỗ.
- **Billing:** Tính phí, nhận tiền và hoàn tiền.
- **CourseCatalog:** Hiển thị thông tin lớp, ngày khai giảng và số chỗ dự kiến.
- **Notification:** Gửi email xác nhận.

Dữ liệu minh họa:
- Enrollment hiện ghi 29 chỗ đã có hiệu lực.
- Hai học viên gửi đăng ký gần như cùng thời điểm.
- Catalog cache số chỗ còn lại trong 20 giây.
- Billing provider có thể timeout dù đã thu tiền.
- Queue có thể giao lại sự kiện PaymentCaptured.
- Một yêu cầu hủy có thể đến đồng thời với sự kiện thanh toán thành công.

### Yêu cầu

1. Viết ba bất biến của Enrollment và hai bất biến của Billing. Phân biệt ràng buộc cứng với điều kiện được xử lý sau.
2. Ai có thẩm quyền quyết định “được nhận vào lớp” và “đã thu tiền”? Vì sao Catalog cache không được chốt một suất học?
3. Thiết kế command ReserveSeat với requestId/idempotency key, lớp học, học viên và tenant. Xác định những kiểm tra chủ sở hữu phải tự thực hiện.
4. Nêu một cơ chế database để hai request cạnh tranh không thể cùng chiếm chỗ thứ 30. Xác định số dòng cập nhật/constraint được kiểm tra thế nào.
5. Mô tả state machine tối thiểu PENDING_SEAT, SEAT_RESERVED, PENDING_PAYMENT, ENROLLED, CANCELLED, REVIEW_REQUIRED và những chuyển trạng thái bị cấm.
6. Khi Payment timeout, Enrollment phải trả trạng thái gì và cần thông tin nào để đối soát?
7. Khi cùng sự kiện PaymentCaptured được gửi hai lần, ai chịu trách nhiệm chặn việc xác nhận và gửi thông báo không phù hợp nhiều lần?
8. Viết ba kiểm thử tích hợp: cạnh tranh giữ ghế cuối, retry cùng command và hủy đồng thời với kết quả thanh toán.
9. Nêu ít nhất hai metric và một báo động thể hiện hệ thống đang bảo vệ được ràng buộc.

### Gợi ý tư duy

Một hướng thiết kế là Enrollment sở hữu số chỗ và trạng thái ghi danh; Billing sở hữu hiệu lực khoản thu và khoản hoàn. Enrollment xử lý giữ chỗ bằng cập nhật nguyên tử/unique constraint phù hợp; Billing dùng paymentAttemptId cùng idempotency để chống thu tiền trùng; Enrollment chỉ xác nhận ENROLLED khi thỏa điều kiện giữ chỗ và thanh toán. Catalog là nguồn hiển thị có thể cũ, Notification chỉ chịu trách nhiệm giao thông báo. Nếu kết quả thanh toán chưa rõ, không tự tạo một charge mới hoặc khẳng định học viên đã thất bại; dùng trạng thái đang xác minh và đối soát.

## 22. Mẫu ghi nhận quyết định kiến trúc (ADR)

~~~text
ADR: Ràng buộc bắt buộc tại <service / command>

Ngày, chủ sở hữu và người duyệt:
Mục tiêu nghiệp vụ:
Service quyết định cuối cùng:
Các command liên quan và actor được phép:
Dữ liệu nguồn và phạm vi tenant:
Bất biến cứng (viết thành câu có thể kiểm thử):
Những điều kiện được chấp nhận xử lý bất đồng bộ:
Phần kiểm tra ở client/gateway và lý do:
Cách cưỡng chế tại owner:
  - Transaction và isolation:
  - Lock / conditional update / unique constraint:
  - State machine / version:
  - Authorization:
Idempotency, retry và trường hợp outcome chưa xác định:
Các hợp đồng liên service:
Outbox, event và consumer duplicate handling:
Hành vi khi xung đột, timeout, dependency lỗi:
Bằng chứng kiểm thử đồng thời/crash:
Metric, audit, cảnh báo và đối soát:
Phương án thay thế và chi phí:
Điều kiện đánh giá lại:
~~~

## 23. Ghi nhớ khi thiết kế microservices

- **Nơi sở hữu quyết định phải cưỡng chế ràng buộc liên quan đến quyết định**, kể cả khi client và service khác đã kiểm tra trước.
- **Kiểm tra phải gắn với thao tác cập nhật**, nếu không có thể sai do thời gian, cạnh tranh hoặc dữ liệu cũ.
- **Database constraint, transaction và concurrency control** là các công cụ bảo vệ ràng buộc; mỗi công cụ có phạm vi và giới hạn riêng.
- **Bất biến nghiệp vụ và phân quyền** không được chuyển hoàn toàn sang client, gateway, cache hay consumer.
- **Command có ngữ nghĩa rõ** giúp service kiểm soát hành vi, trạng thái và lỗi; API sửa tùy ý cột dữ liệu dễ làm lộ ranh giới.
- **Retry, duplicate, delayed event và unknown outcome** là tình huống bình thường của hệ phân tán; idempotency và state machine phải được thiết kế ngay từ đầu.
- **Liên service cần phân biệt quyết định cục bộ với quy trình tổng thể**. Chủ quy trình phối hợp kết quả, không được chiếm quyền của owner khác.
- **Bất biến được chứng minh bằng hành vi dưới lỗi và cạnh tranh**, cùng quan sát/đối soát sau triển khai, chứ không chỉ bằng sơ đồ service.
