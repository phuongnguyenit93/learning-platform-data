# Xóa đối tượng theo ngữ nghĩa nghiệp vụ và quan hệ sở hữu

Trong phần mềm, thao tác xóa thường được biểu diễn bằng một nút Delete, một lệnh SQL `DELETE` hoặc một endpoint HTTP `DELETE`. Tuy nhiên, trong Domain-Driven Design (DDD), xóa một đối tượng là quyết định liên quan đến ý nghĩa và vòng đời nghiệp vụ. Một đơn hàng có thể được hủy, một tài khoản có thể bị đóng, một hợp đồng có thể hết hiệu lực, một dòng hàng có thể bị loại khỏi đơn nháp và một hồ sơ có thể được lưu trữ. Những hành động này không nhất thiết có cùng ý nghĩa với việc xóa vĩnh viễn dữ liệu khỏi database.

Trước khi xóa, nhóm cần hiểu đối tượng đang ở trạng thái nào, ai sở hữu vòng đời của nó, những đối tượng nào phụ thuộc vào nó, quy tắc nào phải được bảo vệ và lịch sử nào cần giữ lại. Đặc biệt, trong mô hình aggregate, đối tượng nội bộ thường chỉ được thêm hoặc loại bỏ thông qua aggregate root để bảo đảm các invariant. Với các aggregate hoặc bounded context độc lập, việc xóa cần được phối hợp qua hợp đồng và quy trình phù hợp.

Bài học này trình bày cách lựa chọn ngữ nghĩa xóa, phân biệt xóa với các hành động kết thúc vòng đời khác, xử lý quan hệ sở hữu, áp dụng cascade một cách có kiểm soát và thiết kế việc xóa trong hệ thống phân tán.

## 1. Xóa là một hành vi nghiệp vụ

Một yêu cầu như “xóa khách hàng” chưa đủ để xác định phần mềm phải làm gì. Người yêu cầu có thể muốn:

- Ngăn khách hàng tiếp tục đăng nhập.
- Ngừng quan hệ kinh doanh nhưng giữ lịch sử giao dịch.
- Ẩn hồ sơ khỏi các màn hình vận hành thông thường.
- Xóa một hồ sơ được tạo nhầm và chưa phát sinh giao dịch.
- Xóa dữ liệu cá nhân theo một chính sách đã được xác nhận.
- Xóa hoàn toàn một bản ghi kỹ thuật không còn được tham chiếu.

Những mục tiêu này dẫn đến hành vi và hệ quả khác nhau. Nếu nhóm triển khai tất cả bằng một phương thức `deleteCustomer()`, mã nguồn có thể xóa nhầm dữ liệu cần giữ, không thu hồi đúng quyền truy cập hoặc làm mất lịch sử cần cho đối soát.

Trong DDD, hãy bắt đầu bằng câu hỏi: **nghiệp vụ muốn điều gì xảy ra với đối tượng và các quan hệ của nó?** Sau đó mới quyết định trạng thái miền, sự kiện, thay đổi dữ liệu và cách lưu trữ tương ứng.

### 1.1. Phân biệt hành động với thao tác lưu trữ

Một thao tác lưu trữ có thể là `DELETE FROM customer`, nhưng hành vi nghiệp vụ có thể là `CloseCustomerAccount`, `DeactivateCustomer` hoặc `ErasePersonalData`. Tên hành vi nên thể hiện điều người dùng hoặc tổ chức thực sự yêu cầu.

Ngược lại, không phải mọi hành vi kết thúc vòng đời đều phải xóa bản ghi. Đóng tài khoản có thể chuyển trạng thái sang `CLOSED`; hủy đơn có thể ghi nhận `CANCELLED`; lưu trữ hồ sơ có thể chuyển nó sang vùng lưu trữ riêng. Những bản ghi này vẫn tồn tại để bảo vệ lịch sử và quan hệ nghiệp vụ.

## 2. Phân biệt delete, deactivate, close, cancel, archive và expire

Các từ này thường bị dùng thay thế cho nhau trong giao tiếp, nhưng chúng biểu diễn những kết quả khác nhau. Nhóm cần thống nhất ý nghĩa trong bounded context tương ứng.

| Hành động | Ý nghĩa thường gặp | Dữ liệu có thể còn tồn tại? | Ví dụ |
| --- | --- | --- | --- |
| Delete (xóa) | Loại bỏ một đối tượng hoặc dữ liệu theo chính sách | Có thể bị xóa vật lý hoặc đánh dấu xóa | Xóa một dòng nháp được tạo nhầm |
| Deactivate (vô hiệu hóa) | Ngừng cho phép đối tượng được sử dụng | Thường còn tồn tại | Vô hiệu hóa người dùng đã nghỉ việc |
| Close (đóng) | Kết thúc hoạt động hoặc quan hệ đang mở | Thường còn tồn tại để tra cứu lịch sử | Đóng tài khoản hoặc hồ sơ |
| Cancel (hủy) | Hủy một cam kết hoặc quy trình chưa/đang thực hiện theo chính sách | Thường giữ lịch sử và lý do | Hủy đơn hàng |
| Archive (lưu trữ) | Chuyển khỏi luồng vận hành thường ngày nhưng giữ để tra cứu | Có | Lưu trữ hợp đồng đã kết thúc |
| Expire (hết hạn) | Đối tượng mất hiệu lực do thời hạn hoặc điều kiện | Thường còn tồn tại | Phiếu giảm giá hết hạn |
| Revoke (thu hồi) | Rút lại quyền, giấy phép hoặc sự chấp thuận đã cấp | Thường giữ bằng chứng và thời điểm | Thu hồi quyền truy cập hoặc ủy quyền |
| Erase (xóa dữ liệu) | Xóa dữ liệu cụ thể theo chính sách dữ liệu | Tùy phạm vi và yêu cầu | Xóa thông tin cá nhân được phép xóa |

Đây là cách phân biệt khái quát. Mỗi tổ chức cần định nghĩa chính xác các thuật ngữ theo nghiệp vụ, hợp đồng và chính sách áp dụng. Chẳng hạn, “hủy hợp đồng” có thể khác “thu hồi hợp đồng” về thẩm quyền và hiệu lực pháp lý.

### 2.1. Hủy đơn hàng không đồng nghĩa xóa đơn hàng

Khi khách hàng hủy một đơn đã được xác nhận, doanh nghiệp có thể cần giữ lại:

- Mã đơn và thông tin người đặt.
- Thời điểm tạo, xác nhận và hủy.
- Người hoặc quy trình yêu cầu hủy.
- Lý do và kết quả phê duyệt.
- Trạng thái thanh toán, hoàn tiền và giữ hàng.
- Các sự kiện đã xảy ra trước khi hủy.

Nếu xóa vật lý đơn hàng, hệ thống có thể mất khả năng giải thích vì sao đã thu tiền, vì sao kho giải phóng hàng hoặc vì sao khách được hoàn tiền. Hành vi phù hợp thường là `cancel()` và chuyển trạng thái, kèm các bước phối hợp cần thiết.

### 2.2. Vô hiệu hóa không giống xóa

Vô hiệu hóa một tài khoản đăng nhập có thể chặn xác thực nhưng vẫn giữ hồ sơ người dùng, lịch sử thao tác và quan hệ với dữ liệu khác. Nếu người dùng được phép quay lại, tài khoản có thể được kích hoạt lại theo chính sách. Xóa vật lý sẽ có hệ quả khác và có thể không thể đảo ngược.

### 2.3. Lưu trữ không phải là xóa

Archive thường thay đổi cách dữ liệu được truy cập hoặc lưu trữ, ví dụ đưa hợp đồng đã kết thúc khỏi danh sách mặc định. Dữ liệu vẫn có thể được truy xuất để kiểm toán, hỗ trợ hoặc đối soát. Việc lưu trữ có thể được thực hiện bằng trạng thái, partition hoặc kho lưu trữ riêng, tùy yêu cầu kỹ thuật.

## 3. Xác định quan hệ sở hữu trước khi xóa

Một đối tượng có thể liên quan đến nhiều đối tượng khác, nhưng không phải mọi quan hệ đều là quan hệ sở hữu. Phân biệt đúng hai loại này là điều kiện quan trọng để quyết định có thể xóa dây chuyền hay không.

### 3.1. Quan hệ sở hữu (ownership)

Một đối tượng sở hữu đối tượng khác khi vòng đời của đối tượng bên trong phụ thuộc vào đối tượng sở hữu theo quy tắc miền. Đối tượng bên trong thường không có ý nghĩa độc lập ngoài phạm vi chủ sở hữu.

Ví dụ, `OrderLine` thường thuộc về một `Order`. Khi một đơn nháp bị loại bỏ theo chính sách, các dòng hàng nội bộ có thể bị loại bỏ cùng aggregate. Dòng hàng không phải là một đơn hàng độc lập và bên ngoài không nên tự ý thay đổi nó.

### 3.2. Quan hệ tham chiếu hoặc liên kết (reference/association)

Một đối tượng có thể tham chiếu đối tượng khác nhưng không sở hữu vòng đời của nó. Ví dụ:

- `Order` tham chiếu `CustomerId`, nhưng xóa một đơn không có nghĩa xóa khách hàng.
- `Invoice` tham chiếu `OrderId`, nhưng vòng đời hóa đơn có thể độc lập và phải được giữ theo quy định kế toán.
- `Shipment` tham chiếu `OrderId`, nhưng hủy đơn không thể tự động xóa lịch sử vận chuyển đã xảy ra.
- `Payment` tham chiếu `OrderId`, nhưng giao dịch thanh toán cần được đối soát riêng.

Trong các trường hợp này, xóa đối tượng được tham chiếu có thể làm hỏng lịch sử hoặc phá vỡ ý nghĩa của đối tượng còn lại. Hệ thống cần chính sách xử lý quan hệ, chẳng hạn chặn xóa, giữ tham chiếu, thay bằng trạng thái ẩn danh hoặc thực hiện quy trình chuyển đổi.

### 3.3. Quan hệ database không tự quyết định ownership nghiệp vụ

Foreign key, cascade option và quan hệ một-nhiều trong ORM mô tả cách lưu trữ hoặc ánh xạ dữ liệu. Chúng không tự chứng minh rằng một đối tượng sở hữu vòng đời của đối tượng khác.

Ví dụ, bảng `order_line` có foreign key đến `orders` và được cấu hình `ON DELETE CASCADE`. Cấu hình này có thể phù hợp nếu dòng hàng chỉ tồn tại như một phần của đơn nháp và chính sách cho phép xóa đơn. Nhưng nó có thể sai nếu dòng hàng cần được giữ để truy vết, hoặc nếu đơn đã phát sinh hóa đơn và giao dịch.

Quyết định ownership phải đến từ nghiệp vụ và mô hình aggregate; database constraint được thiết kế để thực thi quyết định đó.

## 4. Xóa đối tượng nội bộ thông qua aggregate root

Trong DDD, aggregate root là cổng truy cập bên ngoài đến các đối tượng thuộc aggregate. Nếu một entity nội bộ cần được thêm, thay đổi hoặc loại bỏ, thao tác nên đi qua root để duy trì invariant.

Ví dụ, một đơn hàng nháp có thể cho phép loại bỏ một dòng hàng. Nhưng đơn đã xác nhận có thể không cho phép xóa dòng trực tiếp; thay vào đó cần một quy trình điều chỉnh đơn, hủy một phần hoặc tạo yêu cầu trả hàng.

```text
Application Service
        |
        v
OrderRepository
        |
        v
Order (Aggregate Root)
        |
        +---- OrderLine A
        +---- OrderLine B
        +---- OrderLine C

Yêu cầu loại bỏ OrderLine B
        |
        v
Order.removeLine(lineId)
        |
        +--> kiểm tra trạng thái đơn
        +--> kiểm tra dòng hàng tồn tại
        +--> kiểm tra invariant (ví dụ: đơn phải còn ít nhất một dòng)
        +--> loại bỏ dòng nếu được phép
        +--> tính lại tổng tiền và ghi nhận thay đổi
```

### 4.1. Ví dụ: loại bỏ dòng hàng khỏi đơn nháp

```java
public final class Order {
    private final OrderId id;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status;

    public void removeLine(OrderLineId lineId) {
        ensureDraft();

        boolean removed = lines.removeIf(line -> line.id().equals(lineId));
        if (!removed) {
            throw new OrderLineNotFoundException(lineId);
        }

        // Tổng tiền được tính từ các dòng còn lại.
        // Có thể ghi nhận OrderLineRemoved nếu nghiệp vụ cần.
    }

    private void ensureDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new OrderCannotBeModifiedException(id, status);
        }
    }
}
```

Đây là ví dụ minh họa. Nếu nghiệp vụ yêu cầu đơn không được rỗng, root cần kiểm tra invariant đó trước khi loại bỏ dòng cuối cùng. Nếu đơn đã xác nhận, hành vi có thể bị từ chối hoặc được thay thế bằng một use case điều chỉnh riêng. Phương thức của root là nơi thực thi quy tắc, không phải một phép xóa collection tùy tiện.

### 4.2. Repository lưu aggregate sau khi thay đổi

Application service tải root, gọi hành vi và lưu aggregate:

```java
public final class RemoveOrderLineService {
    private final OrderRepository orders;

    public RemoveOrderLineService(OrderRepository orders) {
        this.orders = orders;
    }

    public void remove(OrderId orderId, OrderLineId lineId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.removeLine(lineId);
        orders.save(order);
    }
}
```

Repository không cần cung cấp một `OrderLineRepository.deleteById()` để bên ngoài xóa entity nội bộ. API như vậy có thể phá vỡ ranh giới aggregate và bỏ qua invariant của `Order`.

### 4.3. Khi nào xóa cả aggregate?

Một aggregate có thể được xóa vật lý khi nghiệp vụ xác nhận rằng nó không còn cần tồn tại và các quan hệ phụ thuộc đã được xử lý. Ví dụ, một bản nháp được tạo nhầm, chưa phát sinh giao dịch hoặc lịch sử cần giữ, có thể được xóa theo chính sách.

Tuy nhiên, với một đơn đã xác nhận, thanh toán hoặc giao hàng, hành vi thường là hủy hoặc kết thúc vòng đời thay vì xóa aggregate. Nếu có yêu cầu xóa dữ liệu cá nhân, nhóm cần xác định chính xác dữ liệu nào được xóa, dữ liệu nào phải giữ và cách bảo toàn tính toàn vẹn của hồ sơ còn lại.

## 5. Xóa value object và thay đổi giá trị

Value object được xác định bằng giá trị, không có identity riêng trong mô hình. Vì vậy, “xóa value object” thường có nghĩa là loại bỏ một giá trị khỏi đối tượng sở hữu hoặc thay nó bằng một giá trị khác.

Ví dụ:

- Xóa địa chỉ giao hàng phụ khỏi hồ sơ.
- Bỏ mã khuyến mại khỏi đơn nháp.
- Thay khoảng thời gian hiệu lực bằng một khoảng mới.
- Loại bỏ một tag khỏi tập tag của bài viết.

Nếu value object thuộc aggregate, thao tác thay đổi vẫn nên đi qua root khi nó ảnh hưởng invariant. Một `ShippingAddress` có thể được thay thế bằng địa chỉ mới khi đơn còn ở trạng thái cho phép chỉnh sửa. Không cần tạo repository hoặc API xóa riêng cho value object nếu nó không có vòng đời độc lập.

## 6. Xóa entity độc lập và chính sách vòng đời

Một entity có identity và vòng đời riêng có thể cần một hành vi kết thúc rõ ràng. Nhưng cách kết thúc phụ thuộc vào ý nghĩa nghiệp vụ.

Ví dụ với tài khoản khách hàng:

- `deactivate()` ngăn tài khoản được sử dụng.
- `close()` kết thúc quan hệ hoặc tài khoản theo quy trình.
- `archive()` chuyển hồ sơ ra khỏi luồng vận hành thường xuyên.
- `erasePersonalData()` xóa hoặc ẩn danh những dữ liệu được xác định trong phạm vi chính sách.

Không nên gom các hành vi này vào một `delete()` chỉ vì tất cả đều làm đối tượng không còn xuất hiện trong danh sách hoạt động.

### 6.1. Xác định trạng thái kết thúc

Một entity có thể có trạng thái `ACTIVE`, `INACTIVE`, `CLOSED`, `CANCELLED`, `EXPIRED` hoặc `ARCHIVED`. Những trạng thái này giúp mô hình diễn đạt điều đã xảy ra và những hành động còn được phép.

Ví dụ, tài khoản đã đóng có thể không được phát sinh giao dịch mới nhưng vẫn cho phép truy vấn lịch sử. Một hợp đồng đã hết hạn có thể không còn hiệu lực nhưng vẫn cần được đọc để giải quyết tranh chấp. Trạng thái kết thúc không nhất thiết là trạng thái không thể truy cập.

### 6.2. Ghi nhận lý do và chủ thể thực hiện

Với các hành động như hủy, đóng, thu hồi hoặc xóa dữ liệu, có thể cần ghi nhận:

- Thời điểm thực hiện.
- Người hoặc quy trình yêu cầu.
- Lý do hoặc căn cứ.
- Trạng thái trước và sau.
- Phạm vi dữ liệu bị tác động.
- Kết quả của các bước liên quan.

Không phải mọi thao tác xóa kỹ thuật đều cần toàn bộ thông tin này. Hãy dựa vào yêu cầu truy vết và ý nghĩa nghiệp vụ để xác định dữ liệu cần lưu.

## 7. Hard delete và soft delete

Ở tầng lưu trữ, có hai cách thường được nhắc đến.

**Hard delete (xóa vật lý)** loại bỏ bản ghi khỏi kho lưu trữ đang xét. Sau khi xóa, bản ghi có thể không còn truy vấn được và việc khôi phục phụ thuộc backup hoặc cơ chế lưu trữ khác.

**Soft delete (xóa mềm)** đánh dấu bản ghi là đã xóa hoặc không còn hoạt động, thường bằng cờ `deleted`, thời điểm `deletedAt` hoặc trạng thái tương ứng. Bản ghi vẫn tồn tại trong database và có thể được ẩn khỏi các truy vấn mặc định.

| Tiêu chí | Hard delete | Soft delete |
| --- | --- | --- |
| Bản ghi trong bảng chính | Bị loại bỏ | Vẫn tồn tại với dấu hiệu đã xóa |
| Khôi phục | Thường cần backup hoặc bản lưu khác | Có thể khôi phục nếu chính sách cho phép |
| Truy vấn | Không thấy bản ghi đã xóa | Mọi truy vấn cần lọc đúng trạng thái |
| Ràng buộc duy nhất | Giá trị có thể được dùng lại sau khi xóa tùy constraint | Bản ghi cũ vẫn có thể chiếm unique key |
| Lịch sử | Cần cơ chế audit riêng nếu phải giữ | Có thể giữ dữ liệu nhưng chưa chắc đủ audit |
| Tác động lưu trữ | Giảm dữ liệu trong bảng đang xét | Tăng dữ liệu và độ phức tạp truy vấn |

Không có lựa chọn nào luôn đúng. Soft delete hữu ích khi cần khôi phục hoặc giữ dấu vết, nhưng nó không tự động đáp ứng mọi yêu cầu kiểm toán hoặc quyền riêng tư. Hard delete phù hợp khi dữ liệu thực sự được phép loại bỏ và các tham chiếu đã được xử lý.

### 7.1. Soft delete cần quy tắc rõ ràng

Nếu dùng cờ `deletedAt`, cần xác định:

- Truy vấn nào mặc định loại bỏ bản ghi đã xóa?
- Quản trị viên có được xem bản ghi đã xóa không?
- Các quan hệ có được phép tham chiếu bản ghi đã xóa không?
- Có thể khôi phục không và ai có quyền?
- Unique constraint xử lý dữ liệu đã xóa như thế nào?
- Khi nào bản ghi được xóa vật lý hoặc ẩn danh?

Nếu không có quy ước thống nhất, một phần ứng dụng có thể ẩn bản ghi trong khi phần khác vẫn hiển thị hoặc xử lý nó như bình thường.

### 7.2. Soft delete không thay thế audit log

Một cột `deletedAt` chỉ cho biết thời điểm đánh dấu xóa. Nó không nhất thiết cho biết ai thực hiện, lý do, trạng thái trước đó hoặc những thay đổi nào đã xảy ra. Nếu cần lịch sử đầy đủ, hãy dùng audit log hoặc domain event phù hợp.

## 8. Cascade delete: xóa dây chuyền có kiểm soát

**Cascade delete** là cơ chế khiến việc xóa một đối tượng kéo theo việc xóa những đối tượng liên quan. Nó có thể được thực hiện ở ORM, database hoặc trong logic ứng dụng.

Cascade phù hợp khi các đối tượng con thực sự phụ thuộc vòng đời vào đối tượng cha. Ví dụ, một dòng nháp hoặc một thành phần cấu hình riêng tư có thể được loại bỏ cùng aggregate sở hữu nó.

Cascade nguy hiểm khi quan hệ chỉ là tham chiếu. Xóa một khách hàng không nên tự động xóa mọi đơn hàng, hóa đơn, giao dịch thanh toán và vận đơn nếu các hồ sơ này cần được giữ độc lập.

### 8.1. Phân biệt cascade trong ORM và cascade nghiệp vụ

Cascade trong ORM như `CascadeType.REMOVE` hoặc `orphanRemoval = true` điều khiển hành vi persistence. Nó không tự hiểu điều kiện hủy đơn, quyền xóa, nghĩa vụ tài chính hoặc lịch sử cần giữ.

Cascade nghiệp vụ là một quy trình có chủ đích: khi một đối tượng kết thúc, hệ thống xác định những đối tượng nào cần đóng, hủy, thu hồi, ẩn danh hoặc xóa theo quy tắc. Quy trình đó có thể gồm nhiều aggregate và cần xử lý lỗi giữa chừng.

Không nên bật cascade remove chỉ vì hai entity có quan hệ `@OneToMany`. Hãy xác nhận ownership và vòng đời trước.

### 8.2. Orphan removal

Orphan removal thường được dùng khi một entity con không còn thuộc collection của owner và cần được xóa khỏi database. Điều này có thể hợp lý với `OrderLine` trong đơn nháp nếu dòng hàng không có ý nghĩa ngoài đơn.

Nhưng nếu entity con có lịch sử hoặc được tham chiếu độc lập, loại nó khỏi collection không nên tự động xóa bản ghi. Cần phân biệt “không còn thuộc tập hợp này” với “không còn tồn tại trong nghiệp vụ”.

### 8.3. Xóa database không thay thế quy trình miền

Một lệnh SQL cascade có thể xóa nhanh nhiều hàng nhưng không tự phát domain event, hoàn tiền, giải phóng tồn kho, thu hồi quyền hoặc gửi thông báo. Nếu những hành động đó là yêu cầu nghiệp vụ, cần điều phối chúng trước hoặc trong quy trình kết thúc vòng đời.

## 9. Quan hệ tham chiếu và cách xử lý khi đối tượng bị xóa

Khi một entity được tham chiếu bởi các đối tượng khác, nhóm cần xác định chính sách để tránh dữ liệu mồ côi hoặc lịch sử mất ý nghĩa.

Một số lựa chọn phổ biến:

| Chính sách | Ý nghĩa | Khi có thể phù hợp |
| --- | --- | --- |
| Restrict / Prevent delete | Từ chối xóa nếu còn tham chiếu quan trọng | Khách hàng còn hợp đồng hoặc hóa đơn đang mở |
| Set null | Xóa tham chiếu nếu quan hệ là tùy chọn và việc mất liên kết được chấp nhận | Người phụ trách không còn làm việc, hồ sơ vẫn tồn tại |
| Replace with another reference | Chuyển quyền sở hữu hoặc tham chiếu sang đối tượng khác | Chuyển hồ sơ cho nhân viên mới |
| Keep snapshot | Lưu thông tin cần thiết tại thời điểm giao dịch | Hóa đơn giữ tên và địa chỉ người mua lúc phát hành |
| Tombstone / redirect | Giữ dấu vết rằng ID cũ đã bị xóa hoặc thay thế | Đồng bộ nhiều hệ thống hoặc xử lý tham chiếu cũ |
| Anonymize | Loại bỏ hoặc thay thế dữ liệu nhận diện nhưng giữ cấu trúc giao dịch cần thiết | Khi chính sách cho phép xóa định danh nhưng cần giữ số liệu tổng hợp |

Không nên tự động chọn `SET NULL` chỉ để tránh lỗi foreign key. Việc bỏ tham chiếu có thể khiến một hóa đơn không còn xác định được bên mua hoặc một giao dịch mất nguồn gốc. Cần xác nhận với nghiệp vụ và các yêu cầu lưu trữ liên quan.

### 9.1. Snapshot có thể bảo vệ ý nghĩa lịch sử

Một đơn hàng hoặc hóa đơn thường cần giữ lại thông tin tại thời điểm giao dịch. Nếu chỉ tham chiếu `CustomerId` và luôn lấy tên, địa chỉ hiện tại từ hồ sơ khách hàng, lịch sử có thể thay đổi theo hồ sơ hiện tại.

Trong một số mô hình, aggregate giao dịch giữ snapshot như tên người mua, địa chỉ xuất hóa đơn hoặc giá đã áp dụng tại thời điểm xác nhận. Snapshot không có nghĩa sao chép mọi dữ liệu khách hàng; nó lưu những giá trị cần thiết để giải thích giao dịch theo chính sách.

## 10. Xóa trong hệ thống phân tán và nhiều bounded context

Một entity có thể được tham chiếu bởi nhiều bounded context hoặc hệ thống bên ngoài. Xóa bản ghi trong một database không làm các bản sao, cache, search index, message hoặc hệ thống đối tác tự biến mất.

Ví dụ, khi một tài khoản người dùng bị vô hiệu hóa, hệ thống có thể cần:

1. Chặn đăng nhập trong context identity.
2. Thu hồi session và token.
3. Cập nhật quyền truy cập ở các dịch vụ liên quan.
4. Ẩn hồ sơ khỏi các danh sách vận hành.
5. Giữ các giao dịch và audit record theo chính sách.

Đây là một quy trình nhiều bước. Nó có thể được điều phối qua domain event, policy hoặc saga. Không nên giả định một lệnh `DELETE` trong một service có thể bảo đảm mọi hệ thống đã quên đối tượng.

### 10.1. Công bố sự kiện kết thúc vòng đời

Khi một hành vi nghiệp vụ xảy ra, context sở hữu có thể phát sự kiện như:

- `CustomerAccountDeactivated`.
- `SubscriptionCancelled`.
- `ContractClosed`.
- `PersonalDataErasureRequested`.
- `ProductDiscontinued`.

Các context nhận sự kiện và thực hiện hành động thuộc trách nhiệm của mình. Tên event cần diễn đạt chính xác điều đã xảy ra hoặc yêu cầu đã được ghi nhận; không dùng một event chung `EntityDeleted` nếu các bên cần phân biệt lý do và ngữ nghĩa.

### 10.2. Tombstone và đồng bộ xóa

Trong hệ thống đồng bộ dữ liệu, **tombstone** là dấu hiệu cho biết một ID đã bị xóa hoặc không còn hiệu lực. Nó giúp consumer nhận biết rằng bản ghi biến mất là một thay đổi có chủ đích, không phải dữ liệu chưa từng tồn tại.

Ví dụ, một search index cần nhận thông điệp xóa để loại tài liệu khỏi kết quả tìm kiếm. Nếu chỉ dừng gửi bản cập nhật, bản sao cũ có thể tồn tại vô thời hạn.

Tombstone cần có định danh, thời điểm hoặc phiên bản để consumer xử lý đúng thứ tự. Nếu một thông điệp cập nhật cũ đến sau tombstone, consumer cần tránh khôi phục nhầm dữ liệu đã bị xóa.

### 10.3. Xử lý lỗi giữa các bước

Một quy trình xóa nhiều hệ thống có thể thất bại giữa chừng. Ví dụ, tài khoản đã bị vô hiệu hóa nhưng một dịch vụ phụ chưa xóa cache. Cần xác định:

- Bước nào là điều kiện tiên quyết?
- Có thể retry an toàn không?
- Làm thế nào để phát hiện dịch vụ chưa xử lý?
- Có trạng thái “đang xử lý xóa” hoặc “đã hoàn tất” không?
- Khi nào cần hành động bù hoặc can thiệp vận hành?
- Làm thế nào để bảo đảm yêu cầu xóa không bị bỏ quên?

Outbox/inbox, idempotent consumer và saga/process manager có thể hỗ trợ thực hiện quy trình này. Chúng không thay thế việc xác định ngữ nghĩa và quyền sở hữu của từng dữ liệu.

## 11. Lưu trữ, kiểm toán và yêu cầu bảo vệ dữ liệu

Quyết định xóa có thể bị chi phối bởi hợp đồng, chính sách lưu trữ, nghĩa vụ kế toán, kiểm toán, tranh chấp hoặc yêu cầu bảo vệ dữ liệu. Nhóm phát triển không nên tự suy đoán thời hạn lưu trữ hay phạm vi được phép xóa.

Một yêu cầu “xóa dữ liệu khách hàng” cần được phân tích thành các nhóm dữ liệu:

- Dữ liệu định danh trực tiếp như tên, email, số điện thoại.
- Dữ liệu giao dịch có thể cần giữ theo nghĩa vụ riêng.
- Dữ liệu xác thực, session và token.
- Bản sao trong cache, search index, log, analytics hoặc backup.
- Dữ liệu được chia sẻ với nhà cung cấp hoặc hệ thống khác.

Nhóm cần làm rõ dữ liệu nào có thể xóa, dữ liệu nào phải giữ, dữ liệu nào có thể ẩn danh và dữ liệu nào chỉ cần hạn chế truy cập. Các quyết định về pháp lý và tuân thủ cần được xác nhận bởi người có thẩm quyền phù hợp.

### 11.1. Anonymization khác pseudonymization

**Anonymization (ẩn danh hóa)** loại bỏ khả năng liên kết dữ liệu với một cá nhân theo tiêu chí áp dụng. **Pseudonymization (giả danh hóa)** thay thông tin nhận diện bằng mã hoặc bí danh nhưng vẫn có thể liên kết lại nếu có thông tin bổ sung.

Không nên gọi việc thay email bằng một ID ngẫu nhiên là ẩn danh hóa nếu một bảng ánh xạ vẫn cho phép xác định lại người đó. Mức độ và hiệu lực của biện pháp phải được đánh giá theo bối cảnh dữ liệu.

### 11.2. Backup và bản sao dữ liệu

Xóa bản ghi trong database chính không đồng nghĩa dữ liệu biến mất khỏi backup, log hoặc hệ thống phân tích. Nếu yêu cầu xóa bao gồm các bản sao, cần chính sách vòng đời backup, thời hạn lưu và cách ngăn dữ liệu đã xóa quay trở lại khi restore.

Một cách tiếp cận có thể là giữ danh sách tombstone hoặc yêu cầu xóa được áp dụng lại sau khi khôi phục backup. Thiết kế cụ thể phụ thuộc kiến trúc lưu trữ và yêu cầu được xác nhận.

## 12. API và mô hình hóa command xóa

API có thể dùng HTTP `DELETE`, nhưng ý nghĩa nghiệp vụ vẫn cần được thể hiện trong use case và domain model. HTTP method mô tả thao tác trên resource ở tầng giao thức; nó không tự quyết định việc hủy, đóng hay xóa vật lý.

Ví dụ:

| Endpoint hoặc command | Ý nghĩa cần thể hiện |
| --- | --- |
| `DELETE /draft-orders/{id}` | Xóa bản nháp nếu thỏa điều kiện |
| `POST /orders/{id}/cancellation` | Yêu cầu hủy đơn theo chính sách |
| `POST /accounts/{id}/deactivation` | Vô hiệu hóa tài khoản |
| `POST /contracts/{id}/closure` | Đóng hợp đồng |
| `POST /customers/{id}/erasure-requests` | Ghi nhận yêu cầu xóa dữ liệu cần thẩm định |

Đây là ví dụ về cách biểu đạt API, không phải quy ước bắt buộc. REST API có thể sử dụng `DELETE` cho một hành vi xóa mềm hoặc một resource có vòng đời riêng nếu semantics được định nghĩa rõ. Điều quan trọng là client biết kết quả và trạng thái của yêu cầu.

### 12.1. Idempotency và kết quả yêu cầu

Một client có thể gửi lại yêu cầu xóa do timeout. Hệ thống cần xác định gửi lại cùng yêu cầu có an toàn không và phản hồi thế nào nếu đối tượng đã ở trạng thái kết thúc.

Một số hành vi có thể được thiết kế idempotent: yêu cầu vô hiệu hóa tài khoản đã vô hiệu hóa có thể trả về trạng thái hiện tại. Nhưng nếu thao tác phát sinh phí, hoàn tiền hoặc gửi thông báo, cần bảo đảm tác dụng phụ không lặp lại.

### 12.2. Phân quyền và kiểm tra điều kiện

Xóa thường là hành động có tác động lớn. Application layer cần xác thực actor, quyền hạn, tenant và phạm vi đối tượng. Domain model kiểm tra điều kiện nghiệp vụ như trạng thái hiện tại, nghĩa vụ chưa hoàn tất hoặc quan hệ chưa được giải quyết.

Không nên coi việc ẩn nút Delete trên giao diện là cơ chế phân quyền. Quy tắc phải được kiểm tra ở phía server và trong các luồng kích hoạt khác như message consumer hoặc tác vụ nền.

## 13. Quy trình thiết kế hành vi xóa

Khi nhận yêu cầu xóa một đối tượng, nhóm có thể làm theo các bước sau.

### Bước 1: Làm rõ mục tiêu nghiệp vụ

Hỏi người yêu cầu muốn đối tượng ngừng hoạt động, bị ẩn, kết thúc vòng đời, bị hủy hay bị xóa dữ liệu. Xác định ai yêu cầu và kết quả mong muốn.

### Bước 2: Xác định bounded context sở hữu đối tượng

Làm rõ context nào sở hữu identity, vòng đời và các quy tắc của entity. Context khác chỉ tham chiếu hay có quyền quyết định đối với đối tượng đó?

### Bước 3: Xác định aggregate root và ownership

Đối tượng là aggregate root, entity nội bộ hay value object? Nó có đối tượng con nào phụ thuộc vòng đời? Những quan hệ nào chỉ là tham chiếu?

### Bước 4: Kiểm tra trạng thái và invariant

Đối tượng có được phép xóa ở trạng thái hiện tại không? Có đơn hàng, hóa đơn, thanh toán, hợp đồng hoặc quy trình đang mở nào cần xử lý trước không?

### Bước 5: Chọn ngữ nghĩa kết thúc

Chọn delete, deactivate, close, cancel, archive, expire, revoke hoặc erase theo ý nghĩa đã thống nhất. Định nghĩa trạng thái trước/sau và khả năng khôi phục.

### Bước 6: Xác định tác động đến quan hệ

Với từng đối tượng liên quan, quyết định restrict, cascade, set null, chuyển tham chiếu, giữ snapshot, tombstone hoặc anonymize. Không áp dụng một chính sách chung cho mọi quan hệ.

### Bước 7: Xác định sự kiện và quy trình liên context

Nếu các context khác cần phản ứng, định nghĩa domain event hoặc integration event phù hợp, owner của từng bước, retry, idempotency và trạng thái hoàn tất.

### Bước 8: Xác định lưu trữ và truy vết

Quyết định hard delete, soft delete, archive, audit trail, retention và cách xử lý backup theo chính sách đã xác nhận.

### Bước 9: Kiểm tra quyền và kiểm thử

Kiểm tra quyền ở server, các trạng thái hợp lệ/không hợp lệ, tham chiếu còn tồn tại, lỗi giữa các bước, yêu cầu lặp và concurrency. Xác nhận rằng không mất dữ liệu hoặc quan hệ cần giữ.

## 14. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Dùng `delete()` cho mọi hành động kết thúc vòng đời | Hủy, đóng, lưu trữ và xóa dữ liệu bị nhập làm một | Dùng tên hành vi phản ánh chính sách nghiệp vụ |
| Xóa đơn đã giao thay vì ghi nhận hủy/trả hàng | Mất lịch sử giao dịch và khả năng đối soát | Mô hình hóa trạng thái và quy trình sau giao hàng |
| Xóa entity nội bộ trực tiếp từ repository riêng | Bỏ qua invariant của aggregate root | Thay đổi qua hành vi của root |
| Bật cascade remove chỉ vì có quan hệ ORM | Xóa nhầm hóa đơn, thanh toán hoặc dữ liệu độc lập | Xác minh ownership và vòng đời trước khi cấu hình cascade |
| Coi foreign key là bằng chứng ownership | Chính sách xóa bị quyết định bởi schema database | Phân biệt quan hệ nghiệp vụ với quan hệ lưu trữ |
| Dùng soft delete nhưng quên lọc truy vấn | Bản ghi đã xóa vẫn xuất hiện hoặc được xử lý | Thống nhất query policy và kiểm thử các luồng |
| Coi soft delete là audit đầy đủ | Không biết ai xóa và vì sao | Ghi audit hoặc domain event khi cần |
| Xóa một entity được nhiều context tham chiếu mà không thông báo | Cache và hệ thống khác giữ dữ liệu cũ | Phát sự kiện, tombstone và điều phối xóa |
| Cho rằng xóa database sẽ xóa cả backup và log | Dữ liệu vẫn tồn tại trong bản sao | Xây dựng chính sách vòng đời dữ liệu toàn hệ thống |
| Retry yêu cầu xóa mà không kiểm soát tác dụng phụ | Gửi thông báo hoặc thực hiện quy trình nhiều lần | Dùng idempotency và trạng thái xử lý rõ ràng |

## 15. Nguyên tắc thực hành

Khi thiết kế xóa đối tượng trong DDD, nhóm nên nhớ:

- **Bắt đầu từ ý nghĩa nghiệp vụ.** Xác định điều người dùng muốn xảy ra trước khi chọn SQL hoặc HTTP method.
- **Phân biệt kết thúc hoạt động với xóa dữ liệu.** Hủy, đóng, vô hiệu hóa, lưu trữ và xóa có hệ quả khác nhau.
- **Tôn trọng ownership.** Đối tượng nội bộ được quản lý qua aggregate root; đối tượng chỉ được tham chiếu không bị xóa dây chuyền tùy tiện.
- **Bảo vệ invariant.** Kiểm tra trạng thái, nghĩa vụ và quan hệ trước khi cho phép kết thúc vòng đời.
- **Không để ORM quyết định nghiệp vụ.** Cascade và orphan removal phải phản ánh quyết định ownership đã được xác nhận.
- **Chọn hard delete hoặc soft delete có chủ đích.** Mỗi cách có chi phí, khả năng truy vết và tác động truy vấn riêng.
- **Phối hợp giữa các context.** Dùng event, tombstone và quy trình có retry khi cần đồng bộ việc xóa.
- **Giữ lịch sử cần thiết.** Snapshot, audit và dữ liệu giao dịch phải được xử lý theo chính sách.
- **Kiểm soát quyền và yêu cầu lặp.** Kiểm tra actor, phạm vi và idempotency ở phía server.
- **Kiểm thử toàn bộ tác động.** Xác nhận cả dữ liệu chính, quan hệ, event, cache, index và các hệ thống liên quan.

Xóa một đối tượng đúng nghĩa trong DDD là thực hiện một hành vi phù hợp với vòng đời và quyền sở hữu của nó. Khi nhóm phân biệt được entity nội bộ với đối tượng được tham chiếu, để aggregate root kiểm soát thay đổi, lựa chọn rõ trạng thái kết thúc và phối hợp các context liên quan, hệ thống có thể loại bỏ dữ liệu cần thiết mà vẫn bảo vệ tính nhất quán và lịch sử nghiệp vụ.

## 16. Câu hỏi tự kiểm tra

1. Vì sao một yêu cầu “xóa khách hàng” chưa đủ để xác định hệ thống phải thực hiện thao tác gì?
2. Phân biệt delete, deactivate, close, cancel, archive, expire và revoke bằng ví dụ.
3. Vì sao hủy một đơn hàng đã xác nhận thường không đồng nghĩa xóa vật lý đơn hàng?
4. Phân biệt quan hệ ownership với association/reference trong mô hình miền.
5. Vì sao foreign key hoặc `CascadeType.REMOVE` không tự chứng minh quan hệ sở hữu nghiệp vụ?
6. Tại sao việc loại bỏ `OrderLine` nên đi qua `Order` aggregate root?
7. Khi nào một value object được xem là đã bị loại bỏ và vì sao thường không cần repository riêng cho nó?
8. Phân biệt hard delete và soft delete; soft delete cần những quy tắc truy vấn và khôi phục nào?
9. Orphan removal phù hợp với loại đối tượng nào và có thể gây rủi ro gì?
10. Khi một entity được nhiều bounded context tham chiếu, tombstone và domain event hỗ trợ phối hợp xóa như thế nào?
11. Phân biệt anonymization với pseudonymization và vì sao cần xem xét backup/log khi xử lý yêu cầu xóa dữ liệu?
12. Hãy chọn một entity trong hệ thống của bạn, xác định ownership, các tham chiếu, hành vi kết thúc vòng đời và chính sách lưu trữ phù hợp.
