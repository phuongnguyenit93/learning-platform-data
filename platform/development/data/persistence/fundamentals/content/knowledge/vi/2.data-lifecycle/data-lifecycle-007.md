# Chuyển trạng thái nghiệp vụ và điều kiện được phép lưu

> **Chương:** Vòng đời dữ liệu  
> **Module:** DATA_PERSISTENCE_FUNDAMENTALS  
> **Phạm vi:** Thiết kế và lưu giữ các thay đổi trạng thái đúng quy tắc trong ứng dụng Java, từ ràng buộc nghiệp vụ, giao dịch và cô lập đến xử lý đồng thời, lỗi kết nối, bảo mật và khả năng phục hồi.

## 1. Vấn đề: “ghi được” chưa có nghĩa “được phép ghi”

Một ứng dụng bán hàng có thể lưu giá trị `SHIPPED` vào cột trạng thái đơn hàng bằng một câu lệnh `UPDATE`. Nhưng đơn hàng vừa được tạo, chưa được thanh toán và chưa có vận đơn, liệu nó có được phép chuyển ngay sang trạng thái **đã giao cho đơn vị vận chuyển**?

Database có thể chấp nhận một chuỗi hợp lệ về mặt kiểu dữ liệu nhưng **không hợp lệ về nghiệp vụ**. Tương tự, một yêu cầu “hủy đơn” có thể hợp lệ ở lúc khách chưa thanh toán, nhưng trở nên không hợp lệ nếu một giao dịch khác đã ghi nhận thanh toán trước đó.

Vì thế, một hệ thống persistence cần giải quyết đồng thời hai câu hỏi:

1. **Có được phép chuyển trạng thái không?** Điều này phụ thuộc vào trạng thái hiện tại, thao tác được yêu cầu, quyền của người thực hiện và các điều kiện nghiệp vụ.
2. **Làm sao lưu thay đổi an toàn?** Điều này phụ thuộc vào transaction, ràng buộc dữ liệu, cách kiểm soát đồng thời, xác nhận commit và xử lý lỗi.

Mục tiêu bài học:

- Biểu diễn vòng đời của một thực thể bằng các trạng thái, sự kiện và phép chuyển được phép.
- Phân biệt kiểm tra cấu trúc dữ liệu với điều kiện nghiệp vụ và quyền thao tác.
- Tổ chức logic kiểm tra **trước khi lưu** và duy trì tính đúng đắn khi nhiều request chạy đồng thời.
- Thiết kế ranh giới persistence của Java bằng một ví dụ có mã và câu lệnh SQL.
- Nhận diện cách xử lý retry, idempotency, audit, lỗi kết nối và tiến hóa schema.

## 2. Những khái niệm cần tách bạch

**Trạng thái nghiệp vụ (business state)** mô tả một thực thể đang ở giai đoạn nào của vòng đời. Chẳng hạn, đơn hàng có thể ở trạng thái **nháp**, **đã đặt**, **đã thanh toán**, **đã gửi đi** hoặc **đã hủy**. Trạng thái là thông tin nghiệp vụ cần được duy trì nếu nó ảnh hưởng đến các thao tác tiếp theo.

**Lệnh (command)** thể hiện ý định của người dùng hoặc hệ thống: “đặt đơn”, “ghi nhận thanh toán”, “gửi hàng”, “hủy”. Lệnh có thể bị từ chối; việc nhận được lệnh không có nghĩa nó đã thực hiện thành công.

**Sự kiện (event)** mô tả điều đã xảy ra: “đơn đã được đặt” hoặc “thanh toán đã được xác nhận”. Trong hệ thống có sự kiện bất đồng bộ, cần phân biệt **thông báo sự kiện được gửi đến** với **sự kiện đã được kiểm chứng và áp dụng thành công**.

**Chuyển trạng thái (transition)** là phép thay đổi từ trạng thái nguồn sang trạng thái đích, ví dụ `DRAFT → SUBMITTED`. Một transition chỉ được chấp nhận khi đáp ứng tất cả điều kiện liên quan.

**Điều kiện bảo vệ (guard)** là điều kiện phải đúng để thực hiện transition, ví dụ “đơn có ít nhất một dòng hàng” hoặc “chứng từ thanh toán đã được xác minh”.

**Bất biến (invariant)** là quy tắc luôn phải đúng đối với dữ liệu hợp lệ, chẳng hạn “tổng tiền không âm” hoặc “một vận đơn không được liên kết nhầm với hai đơn khác nhau”.

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Trạng thái | Bản ghi đang ở đâu trong vòng đời? | `SUBMITTED` |
| Lệnh | Tác nhân muốn làm gì? | `ConfirmPayment` |
| Guard | Có đủ điều kiện để làm không? | Thanh toán đúng đơn, đúng số tiền |
| Transition | Chuyển từ đâu sang đâu? | `SUBMITTED → PAID` |
| Bất biến | Điều gì tuyệt đối không được vi phạm? | Số lượng hàng đặt phải dương |
| Persistence | Thay đổi được ghi và xác nhận thế nào? | Cập nhật theo điều kiện trong transaction |

Lưu ý: trạng thái nghiệp vụ khác với trạng thái kỹ thuật như **request đang xử lý**, **connection đang mở**, **job đang retry**. Đôi khi trạng thái kỹ thuật cũng cần lưu bền, nhưng không nên trộn chúng vào cùng một cột nếu chúng đại diện cho hai vòng đời khác nhau.

## 3. Ví dụ xuyên suốt: vòng đời đơn hàng

Ta xét một hệ thống đặt hàng với sáu trạng thái:

- `DRAFT` — đơn nháp, người mua còn được chỉnh sửa nội dung.
- `SUBMITTED` — người mua đã xác nhận đặt, hệ thống đã chốt thông tin cần thiết.
- `PAID` — một khoản thanh toán hợp lệ đã được hệ thống xác minh và ghi nhận.
- `SHIPPED` — hàng đã được bàn giao để vận chuyển.
- `DELIVERED` — giao hàng hoàn tất theo quy trình đã thiết kế.
- `CANCELLED` — đơn đã được hủy theo quy tắc cho phép.

Sơ đồ dưới đây mô tả **một quy trình giản lược**. Thực tế có thể cần thêm các trạng thái như thanh toán thất bại, hoàn tiền, giao hàng thất bại hoặc trả hàng.

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> SUBMITTED: SubmitOrder
    DRAFT --> CANCELLED: CancelOrder
    SUBMITTED --> PAID: ConfirmPayment
    SUBMITTED --> CANCELLED: CancelOrder (chưa thanh toán)
    PAID --> SHIPPED: ShipOrder
    SHIPPED --> DELIVERED: ConfirmDelivery
    DELIVERED --> [*]
    CANCELLED --> [*]
~~~

Sơ đồ cung cấp **những cạnh được phép**. Mỗi cạnh còn cần điều kiện cụ thể:

| Trạng thái hiện tại | Lệnh | Đích | Điều kiện điển hình |
| --- | --- | --- | --- |
| `DRAFT` | `SubmitOrder` | `SUBMITTED` | Có ít nhất một dòng hàng; dữ liệu giao hàng hợp lệ; người dùng có quyền |
| `DRAFT` | `CancelOrder` | `CANCELLED` | Chủ đơn hoặc tác nhân được ủy quyền |
| `SUBMITTED` | `ConfirmPayment` | `PAID` | Thanh toán đáng tin cậy, đúng đơn, đúng số tiền, chưa áp dụng trùng |
| `SUBMITTED` | `CancelOrder` | `CANCELLED` | Chưa có thanh toán thành công hoặc nghĩa vụ cần xử lý riêng |
| `PAID` | `ShipOrder` | `SHIPPED` | Có thông tin vận chuyển; đủ điều kiện xuất hàng; nhân viên có quyền |
| `SHIPPED` | `ConfirmDelivery` | `DELIVERED` | Có bằng chứng hoàn tất giao hoặc xác nhận hợp lệ |

Trong mô hình này, `DRAFT → SHIPPED` là **không hợp lệ**, dù người gửi request tự đặt `status = "SHIPPED"`. Tương tự, `DELIVERED → DRAFT` không có trong đồ thị. Hoàn trả hàng hoặc hoàn tiền cần một quy trình riêng, không nên tự ý “quay lùi” trạng thái đơn bằng cách sửa cột.

### Trạng thái cuối không có nghĩa dữ liệu được xóa

`CANCELLED` và `DELIVERED` là trạng thái cuối của **quy trình đơn hàng đang xét**. Bản ghi đơn hàng có thể vẫn cần được giữ lại để tra cứu, kế toán, đối soát, kiểm toán hoặc xử lý yêu cầu hỗ trợ. Hủy nghiệp vụ và xóa dữ liệu vật lý là hai thao tác khác nhau.

## 4. Khi nào một thay đổi được phép lưu?

Có thể biểu diễn điều kiện ở mức khái niệm:

~~~text
Cho phép chuyển =
    trạng thái nguồn hợp lệ
    AND lệnh có trong tập chuyển cho phép
    AND tác nhân có quyền
    AND guard nghiệp vụ thỏa
    AND dữ liệu đích giữ đúng bất biến

Lưu thành công =
    thay đổi hợp lệ được áp dụng nguyên tử
    AND không có xung đột đồng thời chưa giải quyết
    AND thao tác được xác nhận theo hợp đồng lưu trữ
~~~

Đây là hai lớp điều kiện **liên quan nhưng không đồng nhất**. Kiểm tra trước rồi mới gọi `save` vẫn có thể sai nếu dữ liệu đã thay đổi trong khoảng giữa hai bước; vì thế, tầng persistence phải bảo vệ lại các điều kiện quan trọng tại thời điểm ghi.

### 4.1. Trạng thái nguồn và lệnh hợp lệ

Đầu tiên, phải xác nhận bản ghi **thực sự** đang ở trạng thái cho phép. Ví dụ, `ConfirmPayment` chỉ áp dụng cho đơn `SUBMITTED` trong mô hình này. Không được tin vào trạng thái do client gửi lên; hãy đọc hoặc kiểm tra trực tiếp trạng thái hiện hành của nguồn dữ liệu chính.

### 4.2. Quyền của tác nhân

Một khách hàng chỉ được thao tác trên đơn hàng mình sở hữu, trừ khi có quyền đặc biệt. Nhân viên kho có thể được phép chuyển đơn sang `SHIPPED` nhưng không được tự ý xác nhận một khoản thanh toán. Quyền phải được kiểm tra phía server dựa trên thông tin định danh tin cậy, không dựa trên trường `isAdmin` do client tự gửi.

### 4.3. Guard và dữ liệu cần thiết

Khi đặt đơn, có thể yêu cầu danh sách hàng không rỗng, số lượng từng dòng lớn hơn 0, địa chỉ giao đủ thông tin và sản phẩm còn cho phép bán. Khi gửi hàng, có thể yêu cầu mã vận đơn và đã ghi nhận các bước kiểm tra trước xuất kho.

Không phải mọi guard đều nằm trên cùng một hàng database. Ví dụ, để gửi hàng có thể cần kiểm tra cả tồn kho, dòng hàng và quyền của nhân viên. Những thay đổi liên quan cần có ranh giới transaction nhất quán.

### 4.4. Bất biến sau chuyển trạng thái

Ngay cả khi trạng thái mới nằm trong danh sách hợp lệ, dữ liệu vẫn có thể mâu thuẫn. Ví dụ, đơn `PAID` mà không có thông tin thanh toán được kiểm chứng là không đáng tin; đơn `SHIPPED` thiếu vận đơn có thể vi phạm chính sách giao vận.

Các bất biến có thể được bảo vệ ở nhiều nơi: domain model, service, câu lệnh cập nhật có điều kiện, ràng buộc `CHECK`/`UNIQUE`/`FOREIGN KEY` trong database. Không phải tất cả quy tắc nghiệp vụ đều biểu diễn đầy đủ bằng một ràng buộc SQL.

### 4.5. Kiểm tra đồng thời tại thời điểm ghi

Hai request có thể cùng thấy đơn `SUBMITTED`. Request A muốn hủy, request B vừa xác nhận thanh toán. Nếu cả hai đọc rồi ghi thiếu điều kiện, trạng thái sau cùng phụ thuộc vào request ghi cuối cùng, có thể làm mất kết quả của request trước.

Do đó, **đã kiểm tra guard trong RAM** chưa đủ: cần khóa, kiểm tra version, cập nhật có điều kiện hoặc mức cô lập giao dịch phù hợp để bảo vệ điều kiện tại thời điểm ghi.

## 5. Phân biệt dữ liệu hợp lệ về cấu trúc và chuyển trạng thái hợp lệ

Các tầng kiểm tra có vai trò khác nhau:

| Tầng kiểm tra | Ví dụ điều kiện | Kết quả khi vi phạm |
| --- | --- | --- |
| Định dạng/kiểu | `orderId` là UUID, số lượng là số nguyên | Từ chối dữ liệu đầu vào |
| Ràng buộc cơ sở dữ liệu | `status` thuộc tập cho phép; tổng tiền không âm | Database từ chối giá trị không hợp lệ |
| Quy tắc vòng đời | `PAID` không được chuyển trực tiếp về `DRAFT` | Từ chối lệnh nghiệp vụ |
| Quyền truy cập | Chỉ chủ đơn được sửa nháp của mình | Từ chối thao tác trái quyền |
| Đồng thời | Version hiện tại đúng bằng version đã đọc | Phát hiện xung đột; không ghi đè âm thầm |
| Tính duy nhất của tác động | Một event thanh toán không được cộng hai lần | Trả kết quả đã xử lý hoặc áp dụng quy tắc idempotency |

Ví dụ, ràng buộc `CHECK (status IN (...))` trong database chỉ bảo đảm giá trị thuộc danh sách trạng thái. Nó **không tự biết** rằng `DRAFT → PAID` là một bước nhảy không hợp lệ. Việc xác thực cạnh chuyển và guard cần được thực hiện trong logic nghiệp vụ và/hoặc câu lệnh ghi có điều kiện.

## 6. Quy tắc chỉnh sửa phụ thuộc trạng thái

Không chỉ phép chuyển trạng thái, **những field được sửa** cũng thay đổi theo vòng đời:

| Trạng thái | Có thể chỉnh sửa gì? | Điều nên hạn chế |
| --- | --- | --- |
| `DRAFT` | Dòng hàng, số lượng, địa chỉ giao, ghi chú | Không cho sửa định danh hoặc trường thuộc người khác |
| `SUBMITTED` | Một số thông tin hỗ trợ theo quy định; thao tác thanh toán/hủy hợp lệ | Không tự ý thay giá hoặc số lượng đã chốt |
| `PAID` | Thông tin vận chuyển theo quyền và quy trình | Không tự ý sửa tổng tiền gốc hoặc chứng từ thanh toán |
| `SHIPPED` | Cập nhật tiến độ giao qua sự kiện có xác thực | Không sửa dữ liệu đã dùng để ghi nhận giao vận |
| `DELIVERED`/`CANCELLED` | Ghi chú, yêu cầu hỗ trợ, bản ghi điều chỉnh riêng | Không ghi đè lịch sử đã chốt bằng trạng thái nháp |

Một API kiểu `PATCH /orders/{id}` nhận mọi field mà client gửi rồi cập nhật nguyên bản ghi thường tạo rủi ro **mass assignment**: người gửi có thể tự đổi `status`, `totalMinor` hoặc `ownerId` ngoài các thao tác cho phép.

Hướng tốt hơn là cung cấp các lệnh có ý nghĩa nghiệp vụ, ví dụ `UpdateDraftOrder`, `SubmitOrder`, `CancelOrder` hoặc `ConfirmPayment`, với tập trường đầu vào riêng. Kể cả khi sử dụng API PATCH, server vẫn phải kiểm tra danh sách field và quyền tương ứng.

### Phân biệt bản nháp và dữ liệu đã chốt

Trong một số hệ thống, người dùng cần lưu nháp chưa hoàn chỉnh. Khi ấy, điều kiện để **lưu nháp** có thể nhẹ hơn điều kiện để **nộp/xác nhận**. Ví dụ:

- Nháp có thể chưa có địa chỉ giao đầy đủ.
- Khi chuyển sang `SUBMITTED`, địa chỉ và danh sách hàng phải hợp lệ.
- Khi chuyển sang `PAID`, phải có bằng chứng thanh toán từ nguồn tin cậy.

Không nên áp dụng mọi guard của trạng thái cuối lên bản nháp, vì sẽ cản trở người dùng lưu công việc chưa hoàn thành. Tuy nhiên, những bất biến cơ bản như quyền sở hữu, định danh và kiểu dữ liệu vẫn phải được bảo vệ.

## 7. Hiện thực quy tắc bằng Java

Ví dụ sau mô tả domain đơn hàng trên Java 17 trở lên. Một lệnh chuyển trạng thái **tạo ra trạng thái đề xuất mới**, nhưng chưa ghi vào database:

~~~java
import java.time.Instant;
import java.util.UUID;

enum OrderStatus {
    DRAFT, SUBMITTED, PAID, SHIPPED, DELIVERED, CANCELLED
}

record Order(
        UUID id,
        long customerId,
        OrderStatus status,
        long version,
        int itemCount,
        long totalMinor,
        Instant submittedAt) {

    Order submit(Instant at) {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Chi don nhap moi duoc dat");
        }
        if (itemCount <= 0 || totalMinor < 0) {
            throw new IllegalArgumentException(
                    "Don khong co hang hoac tong tien khong hop le");
        }
        if (at == null) {
            throw new IllegalArgumentException("Thieu thoi diem dat");
        }
        return new Order(
                id, customerId, OrderStatus.SUBMITTED,
                version + 1, itemCount, totalMinor, at);
    }
}
~~~

Phương thức `submit` trả về một bản sao mới với trạng thái `SUBMITTED` khi guard thỏa. Nếu trạng thái nguồn không phải `DRAFT`, nó phát sinh lỗi ngay ở domain. **Việc trả về object mới không có nghĩa dữ liệu đã được lưu thành công**.

Ứng dụng có thể dùng một hợp đồng repository:

~~~java
import java.time.Instant;
import java.util.ConcurrentModificationException;
import java.util.Optional;
import java.util.UUID;

interface OrderRepository {
    Optional<Order> findById(UUID id);

    // Chỉ trả true nếu chính xác một bản ghi đã chuyển trạng thái.
    boolean saveTransition(
            Order proposed,
            OrderStatus expectedStatus,
            long expectedVersion);
}

final class SubmitOrderService {
    private final OrderRepository repository;

    SubmitOrderService(OrderRepository repository) {
        this.repository = repository;
    }

    void submit(UUID orderId, long actingCustomerId, Instant now) {
        Order current = repository.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Khong tim thay don"));

        if (current.customerId() != actingCustomerId) {
            throw new SecurityException("Khong co quyen dat don");
        }

        Order proposed = current.submit(now);
        boolean saved = repository.saveTransition(
                proposed, current.status(), current.version());

        if (!saved) {
            throw new ConcurrentModificationException(
                    "Don da thay doi, can tai lai trang thai");
        }
    }
}
~~~

Mẫu này minh họa:

1. **Application service** điều phối request, danh tính và truy cập dữ liệu.
2. **Domain** kiểm tra trạng thái nguồn và các guard nội tại.
3. **Repository** chịu trách nhiệm lưu chuyển trạng thái với điều kiện chống ghi đè.

Ví dụ cố ý đơn giản: chưa triển khai xử lý nhiều dòng hàng, khóa tài nguyên kho, kiểm tra chính sách giá hoặc thanh toán. Nếu các guard phụ thuộc vào nhiều bản ghi, chỉ kiểm tra trên object cũ có thể không đủ; cần bảo vệ việc đọc, quyết định và ghi trong cùng transaction hoặc dùng cơ chế kiểm soát đồng thời tương đương.

## 8. Ghi có điều kiện và optimistic locking trong SQL

Giả sử bảng đơn hàng có lược đồ đơn giản theo cú pháp PostgreSQL:

~~~sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'DRAFT', 'SUBMITTED', 'PAID',
            'SHIPPED', 'DELIVERED', 'CANCELLED'
        )
    ),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    item_count INTEGER NOT NULL DEFAULT 0 CHECK (item_count >= 0),
    total_minor BIGINT NOT NULL DEFAULT 0 CHECK (total_minor >= 0),
    submitted_at TIMESTAMPTZ,
    paid_at TIMESTAMPTZ,
    CHECK (
        status NOT IN ('SUBMITTED', 'PAID', 'SHIPPED', 'DELIVERED')
        OR (item_count > 0 AND submitted_at IS NOT NULL)
    ),
    CHECK (
        status NOT IN ('PAID', 'SHIPPED', 'DELIVERED')
        OR paid_at IS NOT NULL
    )
);
~~~

Các ràng buộc này bảo vệ một phần dữ liệu bất kể lệnh ghi đến từ API nào. Chúng **không kiểm tra đầy đủ lịch sử chuyển trạng thái** và không chứng minh thanh toán thực sự hợp lệ. Việc xác minh thanh toán phải nằm trong một quy trình được thiết kế riêng.

Để thực hiện `DRAFT → SUBMITTED`, repository có thể dùng một lệnh cập nhật có điều kiện:

~~~sql
UPDATE orders
SET status = 'SUBMITTED',
    submitted_at = :submittedAt,
    version = version + 1
WHERE id = :orderId
  AND customer_id = :customerId
  AND status = 'DRAFT'
  AND version = :expectedVersion
  AND item_count > 0;
~~~

Các tên có tiền tố `:` là tham số ở lớp truy cập dữ liệu, ví dụ được bind bằng `PreparedStatement`/framework. Đây không phải câu SQL có thể chạy nguyên xi trong mọi SQL console.

Sau câu lệnh, **số hàng cập nhật** là thông tin quan trọng:

- **1 hàng:** chuyển trạng thái đã được áp dụng ở mức statement; nếu đang trong transaction, còn phải commit thành công.
- **0 hàng:** bản ghi không tồn tại, sai chủ sở hữu, nguồn không phải `DRAFT`, version đã đổi hoặc guard không thỏa. Ứng dụng cần đọc/đánh giá lại để phản hồi chính xác theo quyền truy cập.
- **Lỗi database/timeout:** chưa thể khẳng định thành công hay thất bại chỉ dựa trên việc có ngoại lệ; cần xử lý theo ngữ cảnh transaction và kết quả commit.

Điều kiện `status = 'DRAFT' AND version = :expectedVersion` là một ví dụ của **optimistic concurrency control**. Nếu hai request cùng đọc version 4, request đầu ghi và tăng lên 5 thì request thứ hai không thể âm thầm ghi đè dựa trên version 4.

### Khi thay đổi dòng hàng song song

Trong ví dụ, `item_count` nằm ngay trên hàng đơn và được kiểm tra bằng `UPDATE`. Nếu dữ liệu thực tế được chuẩn hóa thành bảng `order_items` riêng, cần bảo vệ cả các thay đổi dòng hàng cùng với việc nộp đơn. Một cách là mọi thao tác sửa dòng hàng đều khóa hàng `orders` cha và chỉ được thực hiện khi đơn đang `DRAFT`. Khi nộp đơn, transaction dùng cùng quy ước khóa đó rồi kiểm tra lại các điều kiện.

Chỉ thêm trường `version` vào `orders` sẽ **không đủ** nếu một luồng khác sửa `order_items` mà không khóa hoặc tăng version của aggregate tương ứng.

## 9. Transaction: quyết định và ghi phải cùng một đơn vị

Nếu một chuyển trạng thái tạo ra nhiều tác động, các thay đổi liên quan cần được đồng bộ. Ví dụ khi xác nhận đặt đơn, hệ thống có thể phải:

1. Kiểm tra đơn vẫn là `DRAFT` và có dòng hàng hợp lệ.
2. Chốt giá theo quy tắc, giữ hoặc trừ tồn kho theo thiết kế.
3. Cập nhật đơn thành `SUBMITTED`.
4. Ghi sự kiện nghiệp vụ để thành phần khác xử lý.

Nếu chỉ thành công bước 3 nhưng thất bại bước 2, dữ liệu có thể mâu thuẫn. Hướng giải quyết thường là transaction database cùng các ràng buộc bảo vệ tồn kho. Ví dụ logic dưới đây là **mã giả**, không phải script SQL có thể chạy độc lập:

~~~text
BEGIN TRANSACTION
    khóa/kiểm tra các bản ghi liên quan
    xác thực guard và quyền từ dữ liệu tin cậy
    cập nhật tồn kho bằng thao tác có điều kiện
    cập nhật đơn nếu trạng thái/version vẫn hợp lệ
    ghi outbox event trong cùng database nếu cần
COMMIT

Nếu bước bắt buộc thất bại:
    ROLLBACK
~~~

Nếu giao dịch rollback thì không nên công bố rằng trạng thái đã thay đổi. Đồng thời, **transaction database không tự đưa một cuộc gọi mạng bên ngoài vào cùng một giao dịch nguyên tử**. Ví dụ, gửi email hoặc gọi cổng thanh toán ngay giữa transaction có thể dẫn đến thông báo đã gửi nhưng dữ liệu bị rollback.

Một kỹ thuật phổ biến là **transactional outbox**: cập nhật dữ liệu nghiệp vụ và ghi bản ghi outbox trong cùng transaction; một worker gửi thông điệp từ outbox sau đó. Đầu nhận phải hỗ trợ xử lý lặp vì thông điệp có thể được gửi lại. Khi quy trình trải qua nhiều dịch vụ, cần thiết kế state machine và cơ chế bù trừ cho từng bước.

### Mức cô lập không thay thế quy tắc nghiệp vụ

Các mức `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE` giải quyết những hiện tượng đồng thời khác nhau tùy hệ quản trị. Không nên giả định bật transaction hoặc dùng mức cô lập mặc định là đủ. Ví dụ, các điều kiện như “không được đặt vượt chỗ”, “không thanh toán trùng” hoặc “không phát sinh hai vận đơn” vẫn cần ràng buộc, câu lệnh có điều kiện và đôi khi cần khóa/serializable transaction.

## 10. Idempotency: xử lý yêu cầu bị gửi lại

Trong hệ thống thực tế, một request có thể bị gửi hai lần vì người dùng nhấn nhiều lần, client retry hoặc một message được phân phối lại. Nếu thao tác mang ý nghĩa **tạo thêm** hoặc **ghi nhận tiền**, xử lý hai lần có thể gây tác động nghiêm trọng.

Ví dụ: cổng thanh toán gửi cùng một sự kiện `payment_succeeded` hai lần. Ứng dụng phải kiểm tra:

- Sự kiện có đến từ nguồn đáng tin cậy, đã được xác thực hay chưa?
- `providerEventId` có được xử lý thành công trước đó không?
- Số tiền, đơn vị tiền và mã đơn có khớp với thông tin đơn hàng không?
- Đơn hiện tại còn ở trạng thái `SUBMITTED` không?
- Nếu đơn đã bị hủy trước khi sự kiện đến thì cần xử lý thanh toán trễ như thế nào?

Một thiết kế có thể lưu `provider_event_id` với ràng buộc duy nhất, đồng thời cập nhật trạng thái đơn trong **cùng transaction**. Khi event trùng đến, trả kết quả “đã xử lý” theo bản ghi đã tồn tại, thay vì thực hiện lại tác động.

Không nên coi mã event do client tùy ý đặt là bằng chứng thanh toán. Chỉ sau khi xác minh với nguồn đáng tin cậy, ứng dụng mới được ghi nhận `PAID`. Nếu một event thanh toán tới sau khi đơn đã `CANCELLED`, không được tự ép đơn trở lại `PAID`; hãy áp dụng quy trình đối soát/hoàn tiền được định nghĩa riêng.

**Idempotency** cũng giúp khi kết quả commit không rõ. Nếu kết nối đứt đúng sau khi gửi `COMMIT`, hệ thống có thể đã lưu dữ liệu dù client nhận timeout. Thay vì tạo đơn mới với ID khác, có thể dùng cùng mã yêu cầu để tra cứu trạng thái và quyết định có cần tiếp tục hay không.

## 11. Ghi lịch sử thay đổi và audit

Cột `status` hiện tại chỉ trả lời **đơn đang ở trạng thái nào**. Để biết **ai**, **khi nào**, **vì sao** đã chuyển trạng thái, có thể cần một bảng lịch sử:

~~~sql
CREATE TABLE order_status_history (
    event_id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders(id),
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    reason TEXT,
    occurred_at TIMESTAMPTZ NOT NULL
);
~~~

Khi transition thành công, ứng dụng ghi một bản ghi lịch sử **trong cùng transaction** với cập nhật `orders`. Với thao tác nhạy cảm, có thể lưu thêm định danh request, loại tác nhân, nguồn sự kiện và bằng chứng có thể đối soát. Cần giới hạn dữ liệu cá nhân trong log lịch sử và phân quyền xem lịch sử.

| Thông tin | Tác dụng |
| --- | --- |
| `from_status`, `to_status` | Cho biết đường chuyển đã được thực hiện |
| `actor_id` | Hỗ trợ kiểm toán quyền và xử lý sự cố |
| `occurred_at` | Cung cấp mốc thời gian nghiệp vụ |
| `reason` | Giải thích hành động như hủy đơn |
| `event_id` hoặc `request_id` | Hỗ trợ truy vết, chống xử lý trùng |

Lịch sử thao tác, domain events và event sourcing là các khái niệm có liên quan nhưng không hoàn toàn giống nhau. Chỉ thêm bảng audit **không tự biến** hệ thống thành event-sourced system. Nếu trạng thái hiện tại được tái dựng từ chuỗi sự kiện, yêu cầu về thứ tự, version, schema sự kiện và replay sẽ nghiêm ngặt hơn.

## 12. Trạng thái trong ứng dụng Java và trạng thái đã commit

Trong Java, một object có thể mang `OrderStatus.PAID` sau khi mã nguồn gán hoặc dựng một bản sao mới, trong khi database vẫn ở `SUBMITTED`. Sự khác biệt này có thể xuất hiện khi:

- Ứng dụng mới cập nhật object nhưng chưa gọi repository.
- ORM đã phát hiện field thay đổi nhưng chưa `flush`.
- SQL đã được gửi nhưng transaction chưa `commit`.
- Giao dịch bị rollback.
- Commit thành công nhưng ứng dụng chưa nhận phản hồi do mất kết nối.

Trong JPA/Hibernate, `flush` đồng bộ thay đổi trong persistence context thành thao tác SQL, **không đồng nghĩa** commit thành công và không bảo đảm tác động đã được những transaction khác nhìn thấy. Cần kiểm tra ranh giới transaction của framework và không phát thông báo thành công dựa trên object trong RAM trước khi hoàn tất cam kết của hệ thống.

Đối với một workflow bất đồng bộ, API có thể trả về trạng thái **đã tiếp nhận để xử lý**, nhưng phải diễn đạt đúng cam kết: “đã nhận yêu cầu” khác với “đơn đã được thanh toán” hoặc “đơn đã được gửi đi”. Có thể lưu trạng thái xử lý trung gian riêng để client tra cứu tiến độ.

## 13. Khi nào cần từ chối, thử lại hoặc báo xung đột?

| Tình huống | Cách xử lý hợp lý |
| --- | --- |
| Dữ liệu đầu vào thiếu hoặc sai kiểu | Từ chối và nêu trường không hợp lệ |
| Người dùng không có quyền trên đơn | Từ chối theo chính sách phân quyền |
| Lệnh không có cạnh transition | Từ chối như một xung đột trạng thái/nghiệp vụ |
| Guard không thỏa dù trạng thái nguồn phù hợp | Nêu điều kiện cần bổ sung hoặc xử lý nghiệp vụ tương ứng |
| Version không khớp, hàng đã bị cập nhật | Nạp lại trạng thái; báo xung đột hoặc thử lại có giới hạn nếu thao tác an toàn |
| Deadlock hoặc lỗi giao dịch được DB đánh dấu có thể thử lại | Rollback, bắt đầu transaction mới và retry có giới hạn |
| Mất kết nối gần thời điểm commit | Không suy diễn kết quả; tra cứu theo định danh ổn định trước khi gửi lại |
| Event đã xử lý thành công được gửi lại | Trả kết quả đã xử lý theo cơ chế idempotency |
| Có sự kiện muộn trái với trạng thái hiện tại | Áp dụng quy trình đối soát/bù trừ; không bỏ qua hay ghi đè tùy tiện |

Ở HTTP API, có thể chọn `400` cho dữ liệu sai cấu trúc, `403` cho thiếu quyền, `404` cho tài nguyên không tồn tại, và `409` cho xung đột trạng thái hoặc version. Cách ánh xạ còn phụ thuộc quy ước API và yêu cầu tránh làm lộ sự tồn tại của dữ liệu người khác. Quan trọng hơn mã HTTP là **phản hồi đúng lý do, không tạo ảo giác thao tác đã được ghi thành công**.

### Retry chỉ an toàn khi biết tác động có thể lặp

Đọc dữ liệu thông thường có thể retry dễ hơn thao tác thanh toán hoặc xuất kho. Nếu thử lại vì xung đột, phải **đọc lại trạng thái mới** và đánh giá guard lần nữa. Không được đơn giản lặp câu lệnh với version cũ hoặc ghi đè theo giá trị request đầu tiên.

## 14. Chuyển trạng thái tự động, timeout và dữ liệu cũ

Không phải mọi transition do người dùng nhấn nút. Một đơn `SUBMITTED` có thể tự hủy sau một thời hạn thanh toán nếu quy tắc cho phép. Một tác vụ định kỳ có thể làm:

~~~sql
UPDATE orders
SET status = 'CANCELLED',
    version = version + 1
WHERE status = 'SUBMITTED'
  AND submitted_at < :cutoff;
~~~

Đây là ví dụ **đơn giản hóa**. Trong thực tế còn cần kiểm tra trạng thái thanh toán, chính sách gia hạn, việc đã có khoản thanh toán đang chờ xử lý và sự cạnh tranh với webhook. Nếu chỉ dựa vào thời gian, một job có thể hủy đơn đúng lúc thanh toán được xác nhận ở hệ thống khác.

Giải pháp phải đặt các điều kiện quan trọng trong cùng ranh giới transaction/khóa, hoặc phối hợp qua workflow được thiết kế để xử lý sự kiện muộn. Tác vụ chạy theo lịch cần idempotent, có khả năng tiếp tục sau restart và ghi dấu kết quả để theo dõi.

**Thời gian nghiệp vụ** cũng cần được định nghĩa: mốc thời gian lấy từ đồng hồ đáng tin cậy của hệ thống, sử dụng UTC khi lưu nếu phù hợp, và xác định rõ quy tắc hết hạn. Không nên lấy thời gian client tự gửi để quyết định một quyền lợi có thể bị lợi dụng.

## 15. Thay đổi quy tắc khi hệ thống đã có dữ liệu

Một trạng thái mới như `PAYMENT_PENDING` có thể được thêm vào giữa `SUBMITTED` và `PAID`. Khi đó, đội phát triển cần xem xét:

1. **Dữ liệu cũ:** những đơn hiện đang `SUBMITTED` sẽ được xử lý như thế nào?
2. **Schema:** danh sách trạng thái hợp lệ trong constraint, enum và mapping phải được cập nhật an toàn.
3. **Phiên bản ứng dụng:** trong lúc triển khai nhiều instance, phiên bản cũ có hiểu trạng thái mới hay không?
4. **Điều kiện transition:** command và guard thay đổi thế nào?
5. **Sự kiện và lịch sử:** consumer cũ có xử lý được event mới? Có cần schema version?
6. **Kiểm thử và vận hành:** có thể rollback bản phát hành mà không làm dữ liệu không đọc được không?

Thông thường nên triển khai thay đổi theo các giai đoạn tương thích: cho phép đọc dữ liệu mới, cập nhật schema và migration, rồi kích hoạt đường ghi mới. Với trạng thái mang nghĩa pháp lý hoặc tài chính, không nên “sửa cho đúng” bằng cách đổi thẳng giá trị trong database mà thiếu lịch sử và đối soát.

## 16. Tình huống tự luyện

**Tình huống A — Nộp đơn hai lần.** Hai request cùng đọc đơn `DRAFT` version 7 rồi đều gọi `SubmitOrder`. Request đầu cập nhật thành `SUBMITTED` version 8. Request thứ hai phải trả gì? Vì sao kiểm tra `status` trong Java trước khi lưu chưa đủ?

**Gợi ý:** Lệnh cập nhật có điều kiện `WHERE status = 'DRAFT' AND version = 7` của request thứ hai tác động 0 hàng; ứng dụng tra cứu lại và xử lý như xung đột hoặc cùng một yêu cầu đã được thực hiện nếu có cơ chế idempotency phù hợp.

**Tình huống B — Hủy trong lúc thanh toán.** Đơn đang `SUBMITTED`. Một tác vụ định kỳ muốn hủy vì quá hạn; cùng lúc có webhook báo thanh toán thành công. Hãy đề xuất quy tắc quyết định chuyển sang `CANCELLED` hoặc `PAID` và cách bảo vệ quy tắc ấy khi hai xử lý cạnh tranh.

**Gợi ý:** Cần xác định mốc chốt thời gian, trạng thái thanh toán đáng tin cậy, thứ tự hoặc điều phối thao tác, điều kiện cập nhật trong transaction và quy trình đối soát khoản thanh toán đến muộn.

**Tình huống C — Nháp chưa hoàn chỉnh.** Người dùng lưu đơn nháp không có địa chỉ giao. Có nên từ chối không? Khi họ nộp đơn thì sao?

**Gợi ý:** Có thể cho lưu bản nháp thiếu một số thông tin; khi chuyển sang `SUBMITTED` phải thực hiện guard kiểm tra những trường bắt buộc.

**Tình huống D — Mất kết nối khi commit.** API gửi lệnh tạo đơn, sau đó mất kết nối mà không biết database đã commit chưa. Client retry với cùng `idempotencyKey`. Hệ thống cần lưu và tra cứu thông tin nào để không tạo hai đơn?

**Gợi ý:** Lưu khóa yêu cầu duy nhất gắn với kết quả nghiệp vụ trong cùng ranh giới giao dịch; khi retry, tìm kết quả đã xử lý trước khi tạo mới.

## 17. Checklist thiết kế chuyển trạng thái có persistence

- [ ] Đã vẽ hoặc mô tả rõ trạng thái, lệnh, cạnh chuyển và trạng thái kết thúc.
- [ ] Đã phân biệt lưu nháp với xác nhận nghiệp vụ; quy tắc bắt buộc phụ thuộc từng giai đoạn.
- [ ] Đã xác định guard, bất biến và quyền cho mỗi transition.
- [ ] Không cho client sửa trực tiếp các field trạng thái, giá, quyền hoặc chủ sở hữu ngoài lệnh được phép.
- [ ] Các điều kiện trọng yếu được bảo vệ lúc ghi, bằng version, cập nhật có điều kiện, khóa hoặc transaction.
- [ ] Những thay đổi nhiều bản ghi có ranh giới nguyên tử và kế hoạch xử lý lỗi.
- [ ] Đã xác định cách tránh xử lý lặp, tiếp nhận sự kiện muộn và xử lý commit không rõ kết quả.
- [ ] Đã có cách ghi lịch sử chuyển trạng thái khi cần kiểm toán/truy vết.
- [ ] Các quy tắc bảo mật, migration, backup và quyền đọc dữ liệu cũ đã được xem xét.
- [ ] Phản hồi từ API phân biệt rõ từ chối nghiệp vụ, xung đột, lỗi hạ tầng và lưu thành công.

## 18. Tổng kết

Một thay đổi trạng thái **chỉ được phép lưu** khi lệnh phù hợp với vòng đời hiện tại, tác nhân được phép thực hiện, các guard được thỏa và trạng thái mới giữ đúng bất biến nghiệp vụ. Sau bước quyết định, hệ thống vẫn cần bảo vệ việc ghi trước cạnh tranh đồng thời, bảo đảm transaction phù hợp và chỉ báo thành công theo kết quả đã được xác nhận.

Trong ứng dụng Java, sự phân tách **domain quyết định chuyển trạng thái**, **service điều phối quyền và quy trình**, **repository thực hiện cập nhật có điều kiện** tạo nền tảng để hệ thống dễ hiểu và đáng tin hơn. Các chủ đề sâu hơn về schema, chỉ mục, mức cô lập, lỗi kết nối, tiến hóa dữ liệu, bảo mật, sao lưu và tối ưu hiệu năng đều phục vụ mục tiêu chung: **lưu đúng những chuyển biến thực sự hợp lệ của nghiệp vụ, qua thời gian và qua sự cố**.
