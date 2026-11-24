# Lost update prevention — ngăn cập nhật bị ghi đè khi xử lý đồng thời

Hai request đều có quyền, đều đọc được dữ liệu hợp lệ và đều đi qua bước kiểm tra nghiệp vụ, nhưng kết quả cuối vẫn có thể sai. Khi cả hai tính toán từ cùng một giá trị cũ rồi ghi lại, thay đổi của request trước có thể bị request sau ghi đè. Đây là **lost update**, hay cập nhật bị mất.

Trong chương **Concurrency Rules**, bài học này xem lost update như một vấn đề bảo mật logic nghiệp vụ. Nếu thao tác đồng thời có thể vượt giới hạn tồn kho, làm mất thay đổi số tiền hoặc ghi lại trạng thái cũ để bỏ qua phê duyệt, người dùng có thể cố ý tạo cuộc đua để khai thác. Cách bảo vệ cần nối việc đọc, phân quyền, kiểm tra invariants và ghi dữ liệu thành một quyết định có kiểm soát xung đột.

Sau bài học, bạn có thể:

- Nhận diện lost update trong thao tác đọc–sửa–ghi và phân biệt nó với các lỗi đồng thời khác.
- Dùng phiên bản và conditional update để từ chối dữ liệu nền đã cũ.
- Chọn giữa optimistic locking, pessimistic locking và cập nhật nguyên tử theo ý nghĩa lệnh nghiệp vụ.
- Thiết kế retry, idempotency và phản hồi xung đột mà không làm sai ý định người dùng.
- Kiểm thử cuộc đua với thứ tự thực thi được điều khiển, thay vì dựa vào xác suất.

## 1. Lost update xảy ra như thế nào?

Giả sử kho có 10 sản phẩm khả dụng, chưa có sản phẩm nào được giữ chỗ. Hai người đặt hàng cùng lúc:

- Request A giữ 6 sản phẩm.
- Request B giữ 7 sản phẩm.

Một cách xử lý dễ mắc lỗi là đọc tồn kho, kiểm tra đủ hàng, tính số mới trong ứng dụng rồi ghi đè các cột bằng giá trị đã tính.

```text
Ban đầu: available = 10, reserved = 0

A đọc: available = 10, reserved = 0
B đọc: available = 10, reserved = 0

A kiểm tra 10 >= 6, tính available = 4, reserved = 6
B kiểm tra 10 >= 7, tính available = 3, reserved = 7

A ghi available = 4, reserved = 6 và tạo giữ chỗ cho 6 sản phẩm
B ghi available = 3, reserved = 7 và tạo giữ chỗ cho 7 sản phẩm

Cuối cùng: kho ghi nhận reserved = 7,
nhưng hai yêu cầu đã được chấp nhận với tổng 13 sản phẩm.
```

Thay đổi của A đã bị B ghi đè. Các cột tồn kho vẫn không âm, nên một kiểm tra đơn giản `available >= 0` không phát hiện sự sai lệch giữa tồn kho và các giữ chỗ đã được chấp nhận.

Lịch thực thi trên minh họa điều có thể xảy ra khi đường ghi không bảo vệ dữ liệu nền đã đọc. Một cơ sở dữ liệu hoặc mức cô lập cụ thể có thể chặn, báo xung đột hoặc hủy một giao dịch. Ứng dụng phải hiểu và xử lý bảo đảm thực tế của hệ thống đang dùng; không được mặc định mọi engine đều tự ngăn lịch thực thi này.

### Mẫu mã dễ gây ghi đè

```java
Inventory stock = repository.find(tenantId, skuId);
if (stock.available() < quantity) {
    throw new InsufficientStockException();
}

long newAvailable = stock.available() - quantity;
long newReserved = stock.reserved() + quantity;

repository.overwriteCounters(tenantId, skuId, newAvailable, newReserved);
```

Nếu câu ghi cuối chỉ có điều kiện tenant và ID, nó không chứng minh các giá trị đã đọc vẫn còn hiện hành. Việc kiểm tra đúng quyền trên SKU cũng không chứng minh dữ liệu tính toán chưa bị một request hợp lệ khác thay đổi.

## 2. Vì sao đây là rủi ro logic nghiệp vụ?

Lost update có thể gây lỗi ngẫu nhiên, nhưng cũng có thể bị kích hoạt có chủ ý bằng nhiều request song song, nhiều tab hoặc nhiều đường ghi khác nhau như API, import và worker.

| Nghiệp vụ | Dữ liệu nền bị cũ | Hậu quả có thể xảy ra |
|---|---|---|
| Giữ chỗ tồn kho | Số lượng khả dụng trước lần giữ chỗ khác | Chấp nhận vượt lượng hàng thực tế |
| Sửa đề nghị mua hàng | Số tiền và trạng thái trước khi người khác cập nhật | Làm mất thay đổi hoặc phục hồi trạng thái cũ |
| Duyệt nội dung | Phiên bản đã được người duyệt xem | Phê duyệt một nội dung khác với nội dung đang được lưu |
| Sử dụng hạn mức | Mức đã dùng trước giao dịch khác | Chấp nhận tổng sử dụng vượt giới hạn |
| Quản lý danh sách quyền | Danh sách thành viên trước thay đổi đồng thời | Ghi lại quyền vừa bị thu hồi hoặc làm mất quyền mới cấp |

Với bảo mật logic nghiệp vụ, câu hỏi không chỉ là “request này có quyền không?”, mà còn là “quyết định này được đưa ra trên phiên bản dữ liệu nào, và phiên bản đó có còn đúng khi ghi không?”.

### Không gộp mọi race condition thành lost update

- **Lost update:** hai đường ghi tác động lên cùng dữ liệu; một đường ghi đè thay đổi dựa trên dữ liệu cũ.
- **Write skew:** hai giao dịch sửa các bản ghi khác nhau nhưng cùng phá một điều kiện tổng thể. Phiên bản của từng hàng có thể đều hợp lệ.
- **Thực hiện lặp:** cùng một lệnh được áp dụng nhiều lần do retry hoặc gửi trùng. Đây là bài toán idempotency.
- **Dùng kết quả kiểm tra đã cũ:** quyền, trạng thái hoặc quan hệ thay đổi giữa kiểm tra và thực hiện. Lost update có thể là một dạng cụ thể của khoảng đua này, nhưng không bao phủ mọi trường hợp.

Phân loại đúng giúp tránh dùng một cột `version` để giải quyết những vấn đề nằm ngoài phạm vi của nó.

## 3. Xác định đơn vị dữ liệu phải được bảo vệ

Trước khi chọn khóa, hãy xác định invariant và đơn vị quyết định nghiệp vụ.

Với tồn kho một SKU:

```text
available >= 0
reserved >= 0

Mỗi lần giữ chỗ được chấp nhận phải:
  giảm available đúng quantity,
  tăng reserved đúng quantity,
  tạo bản ghi giữ chỗ tương ứng,
  và commit các thay đổi đó cùng nhau.
```

Với phê duyệt đề nghị:

```text
Nội dung được phê duyệt phải đúng nội dung mà người duyệt đã xem.
Không được dùng quyết định phê duyệt của revision cũ cho revision mới.
```

“Một đối tượng nghiệp vụ” không nhất thiết chỉ là một hàng. Đề nghị có thể gồm hàng cha, nhiều dòng hàng và các chứng từ. Nếu phiên bản chỉ tăng khi sửa hàng cha, việc sửa dòng chi tiết có thể không làm phiên bản đổi. Khi đó kiểm tra phiên bản hàng cha chưa bảo vệ được toàn bộ nội dung đang được phê duyệt.

Có thể bảo vệ một aggregate bằng giao thức tăng phiên bản chung cho mọi thay đổi liên quan, bằng revision nội dung bất biến hoặc bằng cơ chế khóa và kiểm tra phù hợp. Điều quan trọng là mọi đường ghi đều tham gia, kể cả import, tác vụ nền và công cụ quản trị.

## 4. Optimistic locking: chỉ ghi khi phiên bản nền chưa đổi

Optimistic locking cho phép đọc mà không giữ khóa dài trong lúc người dùng suy nghĩ hoặc ứng dụng chuẩn bị lệnh. Khi ghi, hệ thống kiểm tra dữ liệu có còn ở phiên bản mà lệnh dựa vào hay không.

Ví dụ bảng tồn kho có:

```text
Inventory
  tenant_id
  sku_id
  available
  reserved
  status
  version
```

Hai request cùng đọc `version = 12`. Câu ghi phải bao gồm điều kiện phiên bản và tăng phiên bản trong cùng thao tác:

```sql
UPDATE inventory
SET available = :new_available,
    reserved = :new_reserved,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND sku_id = :sku_id
  AND version = :expected_version;
```

Các giá trị được truyền bằng tham số. Nếu A cập nhật thành công từ phiên bản 12 sang 13, B không còn được ghi với `expected_version = 12`. Thay đổi của A không bị một câu ghi cũ âm thầm ghi đè.

Đây là dạng **compare-and-set**: chỉ áp dụng thay đổi nếu giá trị dùng để so sánh vẫn khớp. Việc đọc phiên bản trước rồi dùng một câu UPDATE không có điều kiện phiên bản không tạo ra bảo đảm tương đương.

### Phải kiểm tra số hàng bị ảnh hưởng

| Kết quả cập nhật | Cách xử lý |
|---|---|
| Đúng 1 hàng | Điều kiện đã khớp; tiếp tục hoàn tất giao dịch |
| 0 hàng | Không có bản ghi phù hợp mọi điều kiện; không được báo ghi thành công |
| Nhiều hơn 1 hàng khi mong đợi một đối tượng | Lỗi ràng buộc hoặc truy vấn; rollback và điều tra |

Số hàng bằng 0 không tự chứng minh lỗi phân quyền hay xác định chính xác dữ liệu đã thay đổi thế nào. Bản ghi có thể không tồn tại trong tenant, phiên bản đã đổi hoặc một điều kiện trạng thái không còn đúng. Phản hồi cần tuân theo chính sách tránh làm lộ đối tượng ngoài quyền.

Không xử lý xung đột bằng cách bỏ điều kiện `version` rồi thử lại. Cách đó khôi phục chính lỗ hổng mà optimistic locking được dùng để ngăn.

### Các yêu cầu đối với cột phiên bản

- Phiên bản phải do máy chủ hoặc cơ sở dữ liệu quản lý, không do khách quyết định giá trị kế tiếp.
- Mọi thay đổi thuộc phạm vi được bảo vệ phải làm phiên bản thay đổi.
- Không đặt lại phiên bản về giá trị cũ hoặc tái sử dụng danh tính đối tượng theo cách khiến dữ liệu cũ trông như hiện hành.
- Kiểu dữ liệu và giới hạn phải tránh tràn; không cho phép phiên bản quay vòng âm thầm.
- Mọi đường ghi phải kiểm tra hoặc phối hợp với cùng cơ chế, kể cả SQL trực tiếp và cập nhật hàng loạt.

Timestamp có độ phân giải không đủ hoặc phụ thuộc đồng hồ có thể không phân biệt được hai thay đổi gần nhau. Đừng tự coi `updated_at` là token chống xung đột nếu chưa bảo đảm tính chất cần thiết. Một bộ đếm phiên bản được quản lý nhất quán thường dễ giải thích hơn.

## 5. Lệnh sửa dữ liệu phải mang theo phiên bản mà người dùng đã xem

Giả sử người dùng mở đề nghị PR-101 ở phiên bản 12. Trong lúc họ sửa số tiền, người khác đã đổi nội dung sang phiên bản 13.

Nếu server nhận payload cũ rồi tự đọc phiên bản mới nhất 13 để điền vào câu ghi, request vẫn có thể ghi đè nội dung phiên bản 13. Điều kiện UPDATE lúc đó chỉ bảo vệ khoảng thời gian từ lần đọc mới của server đến lúc ghi; nó không bảo vệ ý định đã được hình thành từ màn hình phiên bản 12.

Hợp đồng lệnh sửa cần biểu đạt dữ liệu nền:

```text
UpdatePurchaseRequest
  request_id
  expected_version = 12
  requested_changes
```

Hoặc API có thể dùng ETag cùng điều kiện HTTP `If-Match`. Nếu sử dụng cách này, token cần phù hợp với ngữ nghĩa kiểm tra mạnh của `If-Match` và thay đổi khi nội dung được bảo vệ thay đổi. ETag không thay thế việc phân quyền theo tenant và đối tượng.

Khi phiên bản không khớp:

- Không áp dụng thay đổi cũ một cách âm thầm.
- Trả phản hồi xung đột phù hợp, chẳng hạn 409 cho xung đột nghiệp vụ hoặc 412 khi điều kiện `If-Match` không đạt.
- Cho người dùng tải bản mới và so sánh với thay đổi đang nhập theo quyền hiện hành.
- Chỉ cho phép hợp nhất khi ứng dụng có quy tắc rõ ràng và kiểm tra lại invariants.

Nếu API yêu cầu phiên bản mà khách không gửi, hãy từ chối theo hợp đồng API. Không mặc định thiếu phiên bản nghĩa là đồng ý ghi đè bản mới nhất.

### Phiên bản không phải thông tin cấp quyền

Biết hoặc đoán được `version = 13` không cho phép sửa PR-101. Một request vẫn phải qua xác thực, phạm vi tenant, quyền đối tượng, quyền trường và state machine. Phiên bản chỉ là bằng chứng về điều kiện đồng thời được yêu cầu, không phải bí mật hay một loại mật khẩu.

## 6. Cập nhật nguyên tử cho lệnh tăng, giảm và giữ chỗ

Không phải thao tác nào cũng cần đọc một giá trị, tính trong Java rồi ghi giá trị tuyệt đối. Với lệnh có ý nghĩa “giữ thêm q sản phẩm từ tồn kho hiện hành”, có thể dùng một UPDATE nguyên tử:

```sql
UPDATE inventory
SET available = available - :quantity,
    reserved = reserved + :quantity,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND sku_id = :sku_id
  AND status = 'ACTIVE'
  AND available >= :quantity;
```

Ứng dụng phải xác thực `quantity` là số nguyên dương trong giới hạn được hỗ trợ trước khi chạy câu lệnh. Giá trị âm có thể đảo ngược ý nghĩa của giữ chỗ. Cần kiểm soát cả nguy cơ tràn số và các ràng buộc phù hợp ở cơ sở dữ liệu.

Điểm khác biệt là phép trừ được thực hiện trên giá trị hiện hành trong thao tác ghi có điều kiện. Hai request không cùng ghi lại hai kết quả tuyệt đối được tính từ số 10 cũ. Với 10 sản phẩm và hai lệnh giữ 6, 7, không thể để cả hai được báo thành công chỉ bằng cách ghi đè các bộ đếm.

### Khi nào vẫn cần phiên bản?

Nếu hợp đồng lệnh yêu cầu đúng phiên bản mà người dùng đã xem, bổ sung:

```sql
  AND version = :expected_version
```

Nếu lệnh có ý nghĩa rõ ràng là giữ số lượng trên trạng thái hiện hành, điều kiện số lượng có thể là căn cứ đồng thời chính cho hàng tồn kho. Hai cách này có ngữ nghĩa khác nhau; không tự bỏ phiên bản chỉ để giảm xung đột.

Ví dụ, một đơn hàng còn dựa vào báo giá, loại hàng hoặc chính sách giới hạn đã hiển thị cho người mua. Cập nhật nguyên tử tồn kho không chứng minh các căn cứ khác còn đúng. Phải bảo vệ cả những dữ liệu làm nên quyết định chấp nhận lệnh.

### Những gì câu UPDATE chưa giải quyết

- Nó chưa tự phân quyền actor trên SKU và kho tương ứng.
- Nó chưa bảo đảm một request được gửi lặp chỉ giữ chỗ một lần.
- Nó chưa tạo bản ghi giữ chỗ và thông điệp nghiệp vụ cùng transaction.
- Nó chưa bảo vệ một giới hạn tổng hợp nằm ở nhiều hàng khác.

Đây là công cụ chống ghi đè và thực thi điều kiện cục bộ, không phải toàn bộ quy trình nghiệp vụ.

## 7. Ví dụ Java: giữ chỗ có điều kiện phiên bản

Đoạn dưới là mã minh họa kiến trúc, không phải chương trình độc lập. Các abstraction về transaction, repository và policy thuộc ứng dụng; không mô tả API của một framework cụ thể.

Ví dụ này chọn hợp đồng lệnh có `expectedVersion`. Repository thực hiện câu UPDATE nguyên tử ở phần trước với cả điều kiện phiên bản, trạng thái và số lượng.

```java
ReserveResult reserve(AuthenticatedContext requestContext,
                      ReserveCommand command) {
    commandRules.requirePositiveBoundedQuantity(command.quantity());
    commandRules.requireExpectedVersion(command.expectedVersion());

    return tx.required(() -> {
        AuthContext auth = authority.loadCurrentUnderProtocol(requestContext);
        InventorySnapshot stock = inventories.findInTenant(
            auth.tenantId(), command.skuId())
            .orElseThrow(ResourceUnavailableException::new);

        policy.requireReservePermission(auth, stock);
        if (stock.version() != command.expectedVersion()) {
            throw new InventoryConflictException();
        }
        stockRules.requireActive(stock);
        stockRules.requireEnough(stock, command.quantity());

        int affected = inventories.reserveIfUnchanged(
            auth.tenantId(),
            command.skuId(),
            command.expectedVersion(),
            command.quantity());

        if (affected != 1) {
            throw new InventoryConflictException();
        }

        Reservation reservation = reservations.insert(
            auth.tenantId(), auth.actorId(),
            command.skuId(), command.quantity());
        audit.recordReservation(auth, reservation);
        outbox.appendReservationCreated(auth.tenantId(), reservation.id());
        return ReserveResult.created(reservation.id());
    });
}
```

### Hợp đồng phía sau mã minh họa

- `AuthenticatedContext` đến từ đường xác thực tin cậy; tenant và actor không lấy trực tiếp từ payload tùy ý.
- `findInTenant` giới hạn tenant trong truy vấn và đọc dữ liệu có thẩm quyền thích hợp cho quyết định ghi.
- `reserveIfUnchanged` kiểm tra tenant, SKU, phiên bản, trạng thái và lượng khả dụng trong cùng UPDATE; tăng phiên bản khi thành công.
- Snapshot ban đầu chỉ giúp đánh giá và trả lỗi sớm. Câu ghi có điều kiện mới là nơi chặn thay đổi đồng thời sau lần đọc đó.
- Thay đổi tồn kho, bản ghi giữ chỗ, audit thành công và outbox phải nằm trong cùng giao dịch. Nếu insert giữ chỗ lỗi, UPDATE tồn kho cũng phải rollback.
- Không gửi thông báo hoặc gọi dịch vụ bên ngoài trước commit như thể việc giữ chỗ đã chắc chắn hoàn tất. Outbox lưu công việc trong transaction rồi phát ra sau commit.
- Mọi ngoại lệ hoặc xung đột phải kết thúc giao dịch theo chính sách rollback đúng. Không bắt lỗi cập nhật rồi vẫn commit những thay đổi trước đó.

Đoạn mã tập trung vào chống lost update; nó chưa triển khai sổ lệnh idempotency. Một endpoint hoàn chỉnh cần bổ sung cơ chế nhận diện cùng một lệnh đã thực hiện để ngăn giữ chỗ lần hai khi response đầu bị mất.

### Quyền có thể thay đổi độc lập với phiên bản tồn kho

Nếu quyền dựa trên membership, vai trò hoặc ACL ở bảng khác, cột `inventory.version` không tự phát hiện việc thu hồi quyền. `loadCurrentUnderProtocol` phải tham gia cơ chế đồng bộ quyền phù hợp khi sản phẩm yêu cầu bảo đảm tại commit.

Một phương án là giao dịch nghiệp vụ giữ khóa bảo vệ quyền, còn giao dịch thu hồi quyền lấy khóa xung đột trên cùng phạm vi đến khi commit. Tất cả căn cứ quyền liên quan phải được bảo vệ; chỉ khóa một hàng không có tác dụng nếu quyền thực tế còn thay đổi qua một đường độc lập khác.

Không coi việc thêm chữ `lock` hoặc `current` vào tên hàm là đã có bảo đảm. Cần định nghĩa chính xác dữ liệu nào được bảo vệ và các đường ghi khác có tuân theo cùng giao thức không.

## 8. Pessimistic locking: đọc và quyết định dưới khóa

Pessimistic locking giữ khóa trên dữ liệu trong lúc giao dịch kiểm tra và cập nhật, để các đường ghi xung đột phải chờ hoặc thất bại theo cơ chế của cơ sở dữ liệu.

Một luồng tham khảo:

```sql
BEGIN;

SELECT available, reserved, status, version
FROM inventory
WHERE tenant_id = :tenant_id
  AND sku_id = :sku_id
FOR UPDATE;

-- Kiểm tra quyền, trạng thái và lượng còn lại trên dữ liệu vừa khóa.
-- Cập nhật bộ đếm, tạo giữ chỗ và outbox trong cùng giao dịch.

COMMIT;
```

Cú pháp và hành vi khóa cụ thể phụ thuộc cơ sở dữ liệu. Khi triển khai, phải xác minh những hàng nào bị khóa, các thao tác nào xung đột, timeout, isolation và hành vi khi không tìm được hàng.

### Những điều kiện dễ bị bỏ sót

- Khóa phải được lấy trong đúng giao dịch sẽ ghi, và giữ đến khi giao dịch hoàn tất.
- Sau khi lấy khóa, dùng dữ liệu có thẩm quyền được đọc theo cơ chế khóa; không tiếp tục tính từ một snapshot đã đọc trước đó ở cache.
- Không giữ transaction mở trong lúc chờ người dùng bấm xác nhận hoặc trong một cuộc gọi mạng dài.
- Khi cần khóa nhiều đối tượng, dùng thứ tự ổn định mà các đường xử lý cùng tuân theo.
- Timeout hoặc deadlock không được chuyển thành thành công. Cần rollback và áp dụng chính sách retry thích hợp.

`synchronized` hoặc mutex trong một tiến trình Java chỉ điều phối các luồng của tiến trình đó. Nó không tự bảo vệ khỏi instance khác, worker, công cụ quản trị hoặc SQL trực tiếp. Khóa phân tán cũng cần cơ chế ngăn một chủ thể đã mất quyền giữ khóa tiếp tục ghi; không thay thế mọi điều kiện tại tầng dữ liệu bằng một cờ khóa ngoài hệ thống.

Pessimistic locking có thể giảm số lần phải tính lại trong vùng tranh chấp, nhưng tăng thời gian chờ và nguy cơ deadlock. Nó vẫn cần phân quyền, state machine, invariant và idempotency.

## 9. Chọn cơ chế theo ý nghĩa thao tác

| Cách làm | Phù hợp khi | Điều cần chú ý |
|---|---|---|
| Optimistic locking bằng phiên bản | Người dùng sửa dựa trên bản đã xem; xung đột không quá thường xuyên | Phải truyền đúng phiên bản nền và xử lý xung đột |
| Cập nhật nguyên tử có điều kiện | Lệnh tăng, giảm hoặc giữ chỗ có điều kiện diễn đạt được ngay trong UPDATE | Vẫn cần transaction cho các thay đổi liên quan và idempotency |
| Pessimistic locking | Quyết định cần đọc nhiều thuộc tính có liên hệ và vùng tranh chấp cần điều phối rõ | Giữ khóa ngắn, thống nhất thứ tự, xử lý deadlock |
| Mức cô lập mạnh hoặc giao thức cho aggregate | Invariant liên quan nhiều hàng hoặc truy vấn tổng hợp | Hiểu bảo đảm thực tế, chi phí và lỗi cần retry |

Các cơ chế có thể kết hợp. Ví dụ, khóa một aggregate ngân sách trong giao dịch, đồng thời kiểm tra phiên bản nội dung mà người dùng đã xác nhận. Khóa bảo vệ thay đổi đang diễn ra; phiên bản giữ ngữ nghĩa “tôi chỉ đồng ý với nội dung đã xem”.

### Có transaction chưa chắc đã ngăn lost update

Transaction giúp nhóm các thay đổi thành đơn vị commit hoặc rollback. Mức cô lập và cách đọc–ghi mới quyết định những cuộc đua nào bị ngăn.

Không suy ra rằng thêm một annotation transaction, dùng MVCC hoặc chọn một mức cô lập có tên quen thuộc là mọi thao tác đọc–sửa–ghi đều an toàn. Hành vi cụ thể khác nhau theo engine và câu truy vấn.

Nếu dùng serializable và mọi dữ liệu ảnh hưởng đến quyết định đều được đọc, kiểm tra và ghi theo đúng hợp đồng trong giao dịch đó, cơ sở dữ liệu có thể từ chối các lịch thực thi không hợp lệ bằng lỗi cần xử lý. Ứng dụng phải sẵn sàng chạy lại toàn bộ giao dịch khi phù hợp.

Serializable cũng không biết rằng một giá trị trong payload đến từ màn hình đã mở từ hôm qua. Nếu ứng dụng chấp nhận giá trị tuyệt đối cũ mà không có điều kiện phiên bản hoặc quy tắc lệnh tương ứng, một lần ghi tuần tự vẫn có thể làm mất ý định của người dùng khác.

### Phiên bản từng hàng không bảo vệ mọi giới hạn tổng hợp

Giả sử hai người tạo hai khoản giữ ngân sách khác nhau. Cả hai đọc tổng đã dùng là 90 trên hạn mức 100, rồi mỗi người tạo một hàng mới trị giá 8. Không có hàng hiện hữu nào bị ghi đè và hai khóa phiên bản riêng không xung đột, nhưng tổng thành 106.

Đây là write skew hoặc một cuộc đua trên điều kiện tổng hợp, không phải chỉ là lost update một hàng. Có thể cần một hàng ngân sách làm điểm điều phối chung, thao tác cấp hạn mức nguyên tử, ràng buộc dữ liệu phù hợp hoặc mức cô lập cung cấp bảo đảm cần thiết.

Khóa hàng chưa tồn tại cũng không đơn giản tương đương khóa một hàng hiện hữu. Không mặc định `SELECT ... FOR UPDATE` trả rỗng sẽ ngăn giao dịch khác tạo dữ liệu mới; điều này phụ thuộc cơ chế khóa và isolation thực tế.

## 10. Retry phải bảo vệ ý định, không chỉ làm request thành công

Khi gặp xung đột, hai loại lệnh cần cách xử lý khác nhau.

### Người dùng sửa giá trị tuyệt đối

Ví dụ: người dùng mở số tiền 1.000.000 và đổi thành 1.200.000. Trong lúc đó, người khác đã sửa thành 1.500.000 với lý do nghiệp vụ mới.

Không được tự đọc phiên bản mới rồi gửi lại 1.200.000 với phiên bản vừa đọc. Đây là ghi đè có chủ ý của ứng dụng, làm cho cơ chế phát hiện xung đột mất tác dụng đối với người dùng.

Hãy trả xung đột và hỗ trợ so sánh:

```text
Giá trị gốc người dùng đã xem: 1.000.000
Giá trị người dùng muốn lưu:   1.200.000
Giá trị hiện hành:            1.500.000
```

Nếu cho phép hợp nhất, chỉ áp dụng những trường mà người dùng thật sự thay đổi theo quy tắc rõ ràng, rồi kiểm tra lại quyền trường và invariants. Hai trường khác nhau cũng có thể liên hệ: sửa ngày bắt đầu và ngày kết thúc độc lập vẫn có thể tạo một khoảng thời gian không hợp lệ.

### Lệnh nghiệp vụ có thể đánh giá lại

Ví dụ: “giữ thêm 2 sản phẩm nếu hiện tại vẫn đủ hàng”. Nếu hợp đồng cho phép đánh giá trên trạng thái mới, hệ thống có thể retry có giới hạn:

1. Rollback lần thử lỗi.
2. Đọc lại dữ liệu có thẩm quyền trong giao dịch mới.
3. Kiểm tra lại quyền, trạng thái và toàn bộ điều kiện liên quan.
4. Áp dụng cùng ý định lệnh nếu nó vẫn hợp lệ.
5. Dừng khi hết ngân sách retry hoặc có lỗi không thể retry.

Nếu lệnh đã ràng buộc vào một báo giá hoặc revision mà người dùng chấp nhận, không tự chuyển lệnh sang revision mới. Việc có thể retry về kỹ thuật không chứng minh được phép thay đổi điều kiện nghiệp vụ.

Giới hạn số lần, thời gian và nhịp retry để tránh khuếch đại tranh chấp. Không retry lỗi phân quyền hoặc dữ liệu không hợp lệ như thể đó là xung đột tạm thời. Sau lỗi khiến transaction không còn dùng được, bắt đầu một transaction mới thay vì tiếp tục trong trạng thái lỗi.

## 11. Idempotency và lost update bảo vệ hai điều khác nhau

Optimistic locking trả lời: “lệnh có còn dựa trên phiên bản phù hợp không?”. Idempotency trả lời: “đây có phải cùng một lệnh đã được thực hiện không?”.

Giả sử lần giữ chỗ đầu đã commit nhưng response bị mất. Khách gửi lại. Nếu ứng dụng chỉ đọc phiên bản mới rồi thực hiện lại phép trừ, cùng một ý định mua hàng có thể giữ kho hai lần dù không có lost update.

Một thiết kế có thể lưu receipt, tức bản ghi kết quả lệnh, với khóa duy nhất theo:

```text
(tenant_id, actor_id, operation, idempotency_key)
```

Receipt cần gắn với fingerprint của payload có ý nghĩa nghiệp vụ, gồm đối tượng, số lượng và các điều kiện nền quan trọng. Cùng khóa nhưng khác payload phải báo xung đột, không áp dụng nội dung mới dưới danh tính lệnh cũ.

Việc claim lệnh, thay đổi tồn kho, tạo giữ chỗ và lưu receipt thành công cần được phối hợp nguyên tử trong phạm vi giao dịch đã chọn. Hai request cùng khóa phải được điều phối bằng ràng buộc và giao thức phù hợp; chỉ kiểm tra “chưa có receipt” rồi insert sau là vẫn có race.

Khi nhận lại một lệnh đã commit, có thể trả kết quả cũ nếu người gọi hiện còn được phép xem kết quả đó. Không cấp lại quyền thực hiện hay tiết lộ dữ liệu chỉ vì người dùng biết khóa idempotency.

| Trường hợp | Cơ chế chính |
|---|---|
| Hai người sửa cùng đối tượng từ cùng phiên bản cũ | Kiểm soát phiên bản hoặc cơ chế khóa phù hợp |
| Một người gửi cùng lệnh hai lần do mất response | Idempotency |
| Hai lệnh khác nhau hợp lệ nhưng cùng tranh lượng tồn kho | Cập nhật nguyên tử hoặc giao thức transaction phù hợp |
| Thông điệp outbox được giao lại | Idempotency ở bên nhận tác dụng phụ |

Một hệ thống thường cần nhiều cơ chế trong bảng cùng lúc.

## 12. Những đường ghi dễ làm thủng cơ chế bảo vệ

### ORM có phiên bản nhưng bulk update bỏ qua

Một ORM có thể hỗ trợ optimistic locking cho entity được quản lý. Không suy ra rằng SQL tự viết, bulk update, import hoặc thủ tục nền cũng tự động dùng cùng cơ chế.

Nếu một job thay đổi `available` mà không tăng phiên bản, request đang giữ phiên bản cũ có thể vẫn khớp và ghi đè. Nếu job có tăng phiên bản nhưng một đường ghi khác không kiểm tra phiên bản hoặc điều kiện nguyên tử tương đương, đường ghi đó vẫn có thể gây mất cập nhật.

Hãy quản lý quy tắc ở dịch vụ nghiệp vụ và repository có hợp đồng rõ ràng, đồng thời xác nhận những gì thực sự được gửi đến cơ sở dữ liệu khi triển khai.

### Cache và read replica làm bản đọc cũ kéo dài

Bản đọc phục vụ màn hình có thể cũ theo hợp đồng sản phẩm, nhưng lệnh sửa phải mang điều kiện nền và được quyết định ở nơi có thẩm quyền ghi. Không lấy snapshot từ cache, tự gắn phiên bản mới từ một nguồn khác rồi coi cặp đó là một trạng thái nhất quán.

Sau xung đột, việc đọc lại từ replica còn trễ có thể trả đúng phiên bản vừa bị từ chối. Đường xử lý cần chọn nguồn và mức nhất quán phù hợp cho việc phục hồi xung đột.

### Ghi toàn bộ entity từ DTO cũ

Một màn hình chỉ sửa ghi chú nhưng gửi lại cả `status`, `total_amount` và `owner_id` cũ có thể ghi đè những thay đổi không liên quan. Dùng danh sách trường cho phép và biểu đạt rõ phần người dùng muốn đổi.

PATCH hoặc cập nhật ít trường giúp giảm phạm vi ghi đè, nhưng không tự thay thế kiểm soát đồng thời. Những trường khác nhau vẫn có thể cùng tham gia một invariant hoặc một quyết định phê duyệt.

### Xung đột được phát hiện sau tác dụng phụ

Nếu ứng dụng gửi email xác nhận, phát voucher hoặc gọi dịch vụ giao hàng trước khi câu ghi có điều kiện thành công, rollback DB không thu hồi được những tác dụng đã xảy ra. Gắn tác dụng phụ vào kết quả commit bằng outbox hoặc một quy trình phối hợp có bù trừ được định nghĩa rõ.

Không ghi audit “đã giữ chỗ” như kết quả cuối trước khi giao dịch commit. Audit về lần thử thất bại cần đường lưu phù hợp để không bị mất theo transaction rollback.

## 13. Kiểm thử cuộc đua với lịch thực thi xác định

Một bài kiểm thử lost update có ý nghĩa phải sử dụng các giao dịch hoặc kết nối độc lập và điều khiển được điểm đọc, ghi, commit. Chỉ chạy nhiều thread rồi đếm số response 200 không chứng minh invariant được giữ.

### Kịch bản optimistic locking

```text
Chuẩn bị:
  available = 10, reserved = 0, version = 12.

1. Cho A và B cùng đọc phiên bản 12 bằng hai giao dịch độc lập.
2. Dừng cả hai tại một barrier sau bước đọc.
3. Cho A giữ 6 và commit.
4. Cho B ghi với expected_version = 12.

Kỳ vọng:
  A thành công; B không được ghi từ phiên bản cũ.
  available = 4, reserved = 6, version = 13.
  Chỉ có một giữ chỗ và tác dụng nghiệp vụ tương ứng.
```

Kiểm tra lại với B thắng trước. Kết quả phải hợp lệ theo thứ tự thắng, không cố định một request luôn thắng.

### Kịch bản cập nhật nguyên tử

Cho hai lệnh giữ 6 và 7 sản phẩm tranh 10 sản phẩm bằng câu UPDATE có điều kiện. Xác nhận tổng lượng giữ chỗ đã commit không vượt lượng được phép, bộ đếm tương ứng với các giữ chỗ và request không thành công không phát sinh sự kiện xác nhận.

Nếu hai lệnh giữ 3 và 4 đều có thể được chấp nhận theo hợp đồng trên trạng thái hiện hành, kết quả phải phản ánh đủ cả hai thay đổi: `available = 3`, `reserved = 7`. Việc chỉ cho một lệnh thành công có thể phù hợp hợp đồng phiên bản nghiêm ngặt, nhưng không phải mặc định của mọi lệnh giữ chỗ.

### Ma trận tình huống cần kiểm tra

| Tình huống | Bằng chứng cần xác nhận |
|---|---|
| Hai cập nhật tuyệt đối cùng phiên bản | Không có ghi đè âm thầm; phía thua nhận xung đột |
| Thiếu phiên bản ở endpoint bắt buộc | Không được tự điền bản mới rồi ghi |
| Phiên bản đúng nhưng actor sai quyền hoặc sai tenant | Không cập nhật và không tiết lộ dữ liệu ngoài quyền |
| Trạng thái chuyển sang đã duyệt trước câu ghi | Lệnh sửa cũ không phục hồi trạng thái hoặc thay nội dung trái quy tắc |
| Dòng con thay đổi trước lệnh phê duyệt | Cơ chế revision hoặc aggregate phát hiện nội dung đã đổi |
| Native SQL, import hoặc worker ghi đồng thời | Cùng tham gia giao thức chống ghi đè |
| UPDATE tồn kho thành công nhưng insert giữ chỗ lỗi | Toàn bộ giao dịch rollback; không mất hàng khả dụng |
| Deadlock, timeout hoặc xung đột serialization | Không báo thành công; retry đúng phạm vi khi được phép |
| Response mất sau commit và khách gửi lại cùng khóa | Không giữ chỗ hoặc phát tác dụng nghiệp vụ lần hai |
| Cùng khóa idempotency nhưng khác số lượng | Xung đột payload; không tái sử dụng kết quả sai |
| Retry một lệnh sửa giá trị tuyệt đối cũ | Không âm thầm thay expected version để ghi đè |
| Hai hàng khác nhau cùng tranh giới hạn tổng hợp | Không cho rằng optimistic locking từng hàng đã đủ |
| Số lượng bằng 0, âm hoặc quá lớn | Bị từ chối trước khi làm biến đổi phép cộng trừ |
| Đọc lại sau xung đột từ nguồn có độ trễ | Không lặp vô hạn trên dữ liệu cũ hoặc ghép sai snapshot |

Các thuộc tính hữu ích để mở rộng kiểm thử:

- Mọi thay đổi được báo thành công đều có điều kiện đồng thời đã được thực thi tại điểm ghi hoặc được bảo vệ bởi giao thức khóa tương đương.
- Không có bản ghi giữ chỗ đã commit mà thiếu thay đổi tồn kho tương ứng, và ngược lại.
- Phiên bản không bị giữ nguyên sau một thay đổi thuộc phạm vi bảo vệ.
- Tổng tác dụng nghiệp vụ tương ứng với các lệnh thực sự đã commit, không phải số lần request được gửi.

## 14. Checklist áp dụng vào thiết kế

- Lệnh đang biểu đạt giá trị tuyệt đối từ một bản cũ hay một thao tác trên trạng thái hiện hành?
- Dữ liệu nào là căn cứ quyết định và có thể đổi trước lúc ghi?
- Điều kiện phiên bản, trạng thái và tenant có nằm ngay trong câu ghi hoặc giao thức khóa không?
- Có kiểm tra số hàng bị ảnh hưởng và rollback đúng đơn vị nghiệp vụ không?
- Tất cả đường ghi, kể cả import, worker và SQL trực tiếp, có tham gia cùng cơ chế không?
- Phiên bản bảo vệ đúng toàn bộ nội dung cần duyệt hay chỉ một hàng cha?
- Giới hạn nhiều hàng có điểm điều phối hoặc bảo đảm isolation phù hợp không?
- Retry có giữ đúng ý định và kiểm tra lại quyền, trạng thái, invariants không?
- Idempotency, receipt và tác dụng phụ có được phối hợp với commit không?
- Bộ kiểm thử có điều khiển lịch đọc–ghi–commit và xác nhận dữ liệu cuối không?

Ngăn lost update là bảo vệ mối liên hệ giữa dữ liệu đã đọc và quyết định được phép ghi. Khi conditional update, khóa, transaction và retry được chọn theo đúng ý nghĩa lệnh, các request hợp lệ chạy đồng thời mới không trở thành đường vượt qua quy tắc nghiệp vụ.
