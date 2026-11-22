# Trạng thái kết thúc của miền nghiệp vụ — Terminal domain state

## 1. Trạng thái kết thúc là một cam kết về vòng đời

Một khoản giữ tồn kho đã hết hạn không được dùng lại để xác nhận bán. Một lệnh hoàn đã thành công không được gửi như một lệnh mới chỉ vì client retry. Một quyết định đã bị thu hồi không được sống lại khi một message cũ đến muộn.

Những yêu cầu đó liên quan đến **terminal domain state**: trạng thái kết thúc trong một vòng đời nghiệp vụ đã xác định. Từ trạng thái này, đối tượng không còn được đi tiếp qua các chuyển trạng thái thông thường của chính vòng đời đó.

Trong chương **Domain State** của học phần **Business Logic Security**, trạng thái kết thúc cần được xem như một ranh giới bảo vệ quyền lợi và tác động. Nó xác định quyết định nào đã chốt, quyền nào đã tiêu thụ hoặc chấm dứt, và hành động nào không còn được phép.

Một nhãn `COMPLETED`, `FAILED` hoặc `CLOSED` trong enum chưa tự tạo ra ranh giới đó. Hệ thống phải thực thi điều kiện chuyển, kiểm soát cạnh tranh, chống tác động trùng và giữ được ý nghĩa của lịch sử.

Sau bài này, bạn cần có khả năng:

- Xác định trạng thái nào thật sự kết thúc trong phạm vi mô hình.
- Phân biệt đóng vòng đời với bất biến toàn bộ dữ liệu hoặc không thể đảo ngược mọi tác động.
- Ngăn request và sự kiện muộn tạo chuyển trạng thái hoặc quyền lợi mới trái phép.
- Thiết kế xử lý đồng thời tại thời điểm đóng đối tượng.
- Kiểm thử các tình huống retry, hết hạn, bù trừ và kết quả chưa rõ.

## 2. Xác định phạm vi trước khi gọi một trạng thái là terminal

Một đối tượng có thể kết thúc một vòng đời nhưng vẫn liên quan tới các quy trình khác.

| Đối tượng và phạm vi | Trạng thái có thể là terminal theo chính sách | Điều không được tự suy ra |
| --- | --- | --- |
| Khoản giữ tồn kho | Đã sử dụng, đã giải phóng, đã hết hạn | Đơn hàng liên quan không thể bị trả hoặc điều chỉnh |
| Một lần thực thi hoàn tiền | Thành công hoặc thất bại cuối cùng đã xác minh | Timeout là thất bại cuối cùng |
| Yêu cầu phê duyệt một nội dung | Đã duyệt, bị từ chối hoặc bị thu hồi tùy vòng đời | Mọi quy trình coi “bị từ chối” là không thể sửa và gửi lại |
| Tác vụ xuất dữ liệu | Hoàn tất, hủy xong hoặc thất bại cuối cùng | File đầu ra tồn tại mãi hoặc ai cũng được tải |
| Đơn hàng | Đã đóng theo vòng đời đơn được định nghĩa | Không còn quy trình trả hàng, tranh chấp hoặc đối soát riêng |

Một trạng thái chỉ là terminal khi mô hình nói rõ không còn chuyển trạng thái thông thường nào từ nó trong phạm vi đó.

Nếu hồ sơ bị từ chối vẫn có thể sửa rồi gửi lại trên cùng đối tượng, `REJECTED` không phải terminal theo mô hình ấy. Nếu mỗi lần gửi là một phiên bản hoặc một yêu cầu riêng, lần xét cũ có thể kết thúc trong khi một lần mới bắt đầu.

### 2.1. Tách nhiều chiều trạng thái khi cần

Một đơn có thể có đồng thời:

~~~text
orderLifecycle: CLOSED
paymentStatus: CAPTURED
returnCaseStatus: OPEN
refundExecutionStatus: PENDING_RECONCILIATION
~~~

Đây có thể là trạng thái hợp lệ nếu các vòng đời và quan hệ được định nghĩa rõ. Một cột `status` dùng cho tất cả dễ tạo những kết luận sai như “đơn đóng nên không cần đối soát hoàn tiền nữa”.

Mỗi chiều cần nguồn có thẩm quyền, chuyển trạng thái và invariant liên quan. Việc tách nhiều cột cũng không tự bảo đảm đúng: cần kiểm soát các tổ hợp bị cấm.

### 2.2. Kết thúc vòng đời không có nghĩa mọi dữ liệu trở thành bất biến

Sau khi một khoản giữ đã sử dụng, hệ thống có thể bổ sung mã tương quan hoặc ghi thêm kết quả kiểm toán. Điều đó không nhất thiết làm sống lại khoản giữ.

Cần tách:

- Nội dung quyết định và tác động đã chốt.
- Thông tin bổ sung không làm đổi ý nghĩa quyết định.
- Một hành động nghiệp vụ mới có thẩm quyền, như điều chỉnh hoặc bù trừ.

Không cho một endpoint “sửa ghi chú” đồng thời thay số lượng, chủ sở hữu, payment hoặc trạng thái kết thúc. Danh sách trường được phép và quyền ghi phải phản ánh ranh giới này.

### 2.3. Kết thúc không đồng nghĩa không thể có sự kiện mới trong thực tế

Một khoản tiền đã được ghi nhận thành công có thể liên quan tới một giao dịch đảo hoặc tranh chấp sau đó. Một đơn đã đóng vẫn có thể phát sinh yêu cầu hỗ trợ.

Cần biểu diễn sự kiện mới theo quy trình và sổ phù hợp, thay vì sửa lịch sử để làm như kết quả trước chưa từng xảy ra.

Ngược lại, nếu hệ thống vẫn chưa biết một lệnh đã thành công hay chưa, gọi nó là terminal quá sớm sẽ tạo nền tảng sai cho các quyết định tiếp theo.

## 3. Ví dụ xuyên suốt: vòng đời khoản giữ tồn kho

Xét một reservation của tenant T1, dành một lượng hàng cho khách C42:

~~~text
reservationId: R-42
tenant: T1
customer: C42
SKU: P1
quantity: 4
state: ACTIVE
expiresAt: thời điểm do máy chủ xác định
version: 7
~~~

Các trạng thái minh họa:

| Trạng thái | Ý nghĩa | Terminal trong vòng đời reservation? |
| --- | --- | --- |
| ACTIVE | Đang giữ quyền sử dụng 4 đơn vị | Không |
| CONSUMED | Quyền giữ đã được dùng để cấp hàng cho một đơn cụ thể | Có |
| RELEASED | Quyền giữ đã được giải phóng theo yêu cầu hợp lệ | Có |
| EXPIRED | Quyền giữ đã được giải phóng theo điều kiện hết hạn | Có |

`CONSUMED` ở đây là phân bổ hàng trong nghiệp vụ, không khẳng định đã giao vật lý hoặc đã thu tiền.

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE: Giữ hàng thành công
    ACTIVE --> CONSUMED: Xác nhận hợp lệ và còn hiệu lực
    ACTIVE --> RELEASED: Giải phóng theo quyền và chính sách
    ACTIVE --> EXPIRED: Xử lý hết hạn hợp lệ
    CONSUMED --> [*]
    RELEASED --> [*]
    EXPIRED --> [*]
~~~

Không có mũi tên từ EXPIRED về ACTIVE trong mô hình cơ sở. Nếu khách muốn giữ lại hàng, cần một lần giữ mới có kiểm tra tồn và quyền hiện tại.

### 3.1. Các invariant

~~~text
Chỉ ACTIVE mới được tiêu thụ hoặc giải phóng theo luồng cơ sở.
Một reservation chỉ có một kết quả kết thúc.
Tiêu thụ, giải phóng và hết hạn không được cùng tạo tác động.
Số lượng và phạm vi thực thi phải khớp reservation có thẩm quyền.
Một reservation chỉ cấp lượng hàng được phép cho đúng đơn.
Retry không tạo thêm quyền giữ hoặc phân bổ.
Sự kiện cũ không làm trạng thái terminal trở lại ACTIVE.
~~~

Mỗi invariant cần áp dụng trên mọi đường ghi: API, worker, job hết hạn, batch và công cụ quản trị.

### 3.2. Tác động lên tồn kho

Gọi:

- A: lượng khả dụng.
- H: lượng đang giữ.
- C: lượng đã phân bổ từ các khoản giữ được sử dụng.

Trong mô hình đóng không có nhập, trả hoặc điều chỉnh ngoài phạm vi:

~~~text
A + H + C = K
~~~

Khi giữ 4 đơn vị:

~~~text
A giảm 4
H tăng 4
~~~

Khi tiêu thụ reservation:

~~~text
H giảm 4
C tăng 4
A không đổi
~~~

Khi giải phóng hoặc xử lý hết hạn:

~~~text
H giảm 4
A tăng 4
C không đổi
~~~

Nếu luồng tiêu thụ và luồng hết hạn cùng áp dụng tác động, hệ thống có thể vừa cấp hàng vừa trả 4 đơn vị về khả dụng. Một nhãn trạng thái cuối hợp lệ không đủ nếu các bộ đếm hoặc lệnh phía sau đã bị áp dụng hai lần.

## 4. Thiết kế điều kiện đóng đối tượng

Đối với mỗi chuyển sang terminal, cần xác định đủ các điều kiện:

| Điều kiện | Câu hỏi |
| --- | --- |
| Actor | Ai được thực hiện hoặc khởi phát? |
| Phạm vi | Đúng tenant, khách hàng, SKU và đối tượng liên quan không? |
| Trạng thái nguồn | Có còn ở trạng thái cho phép không? |
| Nội dung | Số lượng, số tiền hoặc người nhận có khớp quyết định không? |
| Thời gian | Quy tắc xét hạn áp dụng ở mốc nào? |
| Tác động | Những bản ghi, sổ hoặc lệnh nào phải đi cùng? |
| Cạnh tranh | Điều gì bảo đảm chỉ một chuyển trạng thái thắng? |
| Gửi lại | Request hoặc message lặp được xử lý thế nào? |

### 4.1. Thời điểm hết hạn cần có nghĩa rõ ràng

Trong ví dụ, chính sách cho tiêu thụ nếu thời gian máy chủ kiểm tra dưới cơ chế kiểm soát tranh chấp còn nhỏ hơn `expiresAt`. Tại hoặc sau mốc đó, không tạo tiêu thụ mới.

Job hết hạn có thể chạy muộn. Việc bản ghi còn ACTIVE không tự chứng minh reservation còn được tiêu thụ. Cần kiểm tra cả thời gian theo chính sách.

Ngược lại, đồng hồ client báo hết hạn không tự làm bộ đếm tồn thay đổi. Giải phóng phải được ghi nhận nhất quán tại nguồn có thẩm quyền.

Không hứa một mốc thời gian có nghĩa “mọi dịch vụ đã cập nhật đồng thời” nếu kiến trúc không thực hiện điều đó. Cần xác định nơi quyết định hiệu lực và cách các bên khác theo dõi.

### 4.2. Không dùng trạng thái terminal như giá trị đích do caller lựa chọn

Một API kiểu:

~~~json
{
  "reservationId": "R-42",
  "state": "CONSUMED",
  "quantity": 400,
  "customerId": "C99"
}
~~~

không được gán trực tiếp các trường đó vào entity rồi coi thao tác hợp lệ.

Nên có command theo ý định, chẳng hạn yêu cầu dùng reservation cho một đơn. Máy chủ tải lượng đã chốt, kiểm tra quan hệ, quyền, thời hạn và trạng thái nguồn.

Khách hàng sở hữu reservation không có quyền tự chọn bất kỳ kết quả nào hoặc tự tăng lượng hàng. Quyền sở hữu là một điều kiện, không thay thế các invariant khác.

## 5. Đóng đối tượng phải nguyên tử với tác động cục bộ

Nếu lưu CONSUMED trước rồi tiến trình dừng trước khi phân bổ hàng, reservation có thể trông như đã hoàn tất nhưng tác động còn thiếu.

Nếu phân bổ trước rồi dừng trước khi đóng reservation, retry có thể phân bổ lần nữa.

Trong mô hình dữ liệu cùng một cơ sở dữ liệu, nên đưa các thay đổi liên quan vào cùng transaction:

~~~text
kiểm tra quyền và điều kiện
  -> giành quyền chuyển ACTIVE sang kết quả cuối
  -> cập nhật lượng giữ và phân bổ hoặc khả dụng
  -> lưu bản ghi tác động có tính duy nhất
  -> ghi outbox nếu cần
  -> commit
~~~

Thứ tự mã cụ thể có thể khác, nhưng không để trạng thái kết thúc và tác động cục bộ commit rời nhau nếu invariant yêu cầu chúng đi cùng.

Một annotation transaction chưa tự bảo đảm cạnh tranh. Cần cơ chế như khóa hàng, cập nhật có điều kiện hoặc phiên bản, cùng quy tắc cho mọi đường ghi.

## 6. Kiểm soát cạnh tranh tại điểm kết thúc

Hai luồng có thể cùng đọc ACTIVE:

~~~text
Luồng A: khách xác nhận dùng reservation.
Luồng B: job xử lý hết hạn.
~~~

Nếu kiểm tra và cập nhật tách rời, A có thể phân bổ hàng trong khi B trả cùng lượng về khả dụng.

Cần giành quyền thực hiện một chuyển trạng thái cuối. Có thể dùng:

- Khóa bản ghi, đọc lại và kiểm tra điều kiện dưới khóa.
- Cập nhật có điều kiện trên trạng thái nguồn cùng phiên bản.
- Optimistic locking và xử lý xung đột bằng cách đánh giá lại.
- Mô hình transaction khác phù hợp với cơ sở dữ liệu và invariant.

### 6.1. Mẫu cập nhật có điều kiện

~~~sql
UPDATE reservation
SET state = 'CONSUMED',
    consumed_by_order_id = :order_id,
    closed_at = :accepted_at,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND id = :reservation_id
  AND state = 'ACTIVE'
  AND version = :expected_version;
~~~

Chỉ tiếp tục nếu số hàng cập nhật bằng 1. Các placeholder biểu diễn tham số bind.

Mẫu này minh họa guard trạng thái và phiên bản. Nó chưa tự giải quyết quyền, thời hạn, quan hệ với order hoặc bộ đếm tồn. Những điều kiện đó phải được kiểm tra trong cùng cơ chế nhất quán phù hợp; phần Java dưới đây minh họa kiểm tra dưới khóa.

Nếu số hàng bằng 0, không được tiếp tục phân bổ hàng rồi coi như cập nhật trạng thái đã thành công. Cần đọc hoặc trả kết quả theo hợp đồng mà không tiết lộ đối tượng ngoài quyền.

### 6.2. Trạng thái cuối không được ghi đè bằng dữ liệu cũ

Một object đã được đọc khi ACTIVE có thể trở nên cũ sau khi transaction khác đóng reservation. Lệnh save không có guard có thể ghi lại ACTIVE cùng các trường cũ.

Không dùng cơ chế cập nhật toàn bộ entity mà bỏ qua phiên bản hoặc trạng thái có thẩm quyền. Một thao tác chỉ sửa ghi chú cũng không được vô tình ghi đè các trường vòng đời đã thay đổi.

Cần kiểm tra cả đường ORM, SQL trực tiếp, batch và job. Guard chỉ tồn tại trên một đường không bảo vệ được cả vòng đời.

### 6.3. Khóa đúng đối tượng dùng chung

Khóa reservation ngăn hai kết quả cuối trên cùng reservation nếu mọi đường tham gia đúng cơ chế. Nó chưa tự ngăn hai reservation khác nhau vượt tổng tồn hoặc cùng phân bổ quá nhu cầu một order.

Các ngân sách và quan hệ dùng chung cũng cần primitive nguyên tử hoặc khóa tương ứng. Khi khóa nhiều bản ghi, dùng thứ tự thống nhất và transaction đủ ngắn để giảm tranh chấp.

Nếu gặp deadlock hoặc xung đột, retry phải tải và đánh giá lại dữ kiện hiện tại. Không dùng lại kết luận ACTIVE đã có trước lỗi.

## 7. Minh họa Java: tiêu thụ reservation và đóng vòng đời

Đoạn mã sau là **mã khung kiến trúc**, chưa phải ứng dụng chạy độc lập. Nó minh họa mô hình dữ liệu liên quan cùng tham gia transaction cục bộ. Các repository, quyền và primitive tồn kho phải được hiện thực đúng hợp đồng.

~~~java
record ConsumeReservationCommand(
        String reservationId,
        String orderId,
        String idempotencyKey) {}

record AllocationReceipt(
        String allocationId,
        String reservationState) {}

public AllocationReceipt consumeReservation(
        ActorContext actor,
        ConsumeReservationCommand command) {

    validateCommand(command);

    return transactions.required(() -> {
        var order = orders.lockByTenantAndId(
                actor.tenantId(), command.orderId());
        permissions.requireCanAccessOrder(actor, order);

        var reservation = reservations.lockByTenantAndId(
                actor.tenantId(), command.reservationId());
        permissions.requireMayConsumeReservation(actor, reservation, order);

        var scope = operationScopes.forReservationConsumption(actor);
        var replay = idempotency.claimOrReplay(
                scope,
                command.idempotencyKey(),
                fingerprints.forConsumption(command));

        if (replay.isPresent()) {
            return replay.get();
        }

        var now = serverClock.instant();
        reservation.requireActiveAndUnexpiredAt(now);
        order.requireCanAcceptReservation(reservation.snapshot());

        var allocation = allocations.createUniqueForReservation(
                reservation.id(),
                order.id(),
                reservation.stockKey(),
                reservation.quantity());

        inventory.consumeHeldOrThrow(
                reservation.stockKey(), reservation.quantity());

        reservation.consume(order.id(), allocation.id(), now);
        order.acceptAllocation(allocation);
        reservations.save(reservation);
        orders.save(order);
        outbox.appendReservationConsumed(allocation.id());

        var result = new AllocationReceipt(
                allocation.id(), "CONSUMED");

        idempotency.complete(scope, command.idempotencyKey(), result);
        return result;
    });
}
~~~

Các hợp đồng bắt buộc:

1. Actor và tenant được xác thực, quan hệ với order cùng reservation được kiểm chứng. Không tin chủ sở hữu hoặc số lượng do client tự khai.
2. Hai repository thực sự bảo vệ bản ghi trong transaction. Các luồng khác dùng thứ tự khóa tương thích; không có một đường ghi bỏ qua guard.
3. Kiểm tra quyền trước replay bảo vệ việc đọc kết quả. Nó không được trộn với điều kiện trạng thái chỉ dành cho thực thi mới, vì lần đầu đã chuyển trạng thái hợp lệ.
4. `claimOrReplay` có phạm vi, fingerprint và ràng buộc duy nhất, xử lý cùng khóa khác nội dung cũng như request cạnh tranh. Transaction bị hủy phải được kết thúc trước khi đọc lại hoặc retry.
5. Thời gian được lấy sau khi đã kiểm soát tranh chấp trên reservation, rồi áp dụng quy tắc hiệu lực của ví dụ.
6. `requireCanAcceptReservation` kiểm tra đúng SKU, nhu cầu, phạm vi và trạng thái order. Việc caller sở hữu cả hai đối tượng không đủ chứng minh chúng ghép được với nhau.
7. `createUniqueForReservation` ngăn một reservation tạo thêm allocation ngoài chính sách. Unique constraint là một lớp bảo vệ tại dữ liệu, không chỉ kiểm tra tồn tại trong Java.
8. `consumeHeldOrThrow` cập nhật các bộ đếm theo cơ chế nhất quán trên dữ liệu dùng chung, không chỉ sửa một object trong bộ nhớ.
9. Allocation, các bộ đếm, trạng thái kết thúc, order, outbox và kết quả idempotency cùng commit hoặc rollback.
10. Nếu reservation đã terminal và đây là một request mới, luồng minh họa từ chối tạo tác động mới. API có thể cung cấp cách đọc kết quả hiện tại hoặc một hợp đồng trả lại kết quả tương đương nếu được thiết kế rõ.

Không gọi nhà cung cấp hoặc kho bên ngoài trong đoạn mã rồi giả định rollback cục bộ sẽ thu hồi được tác động đó. Nếu phân bổ còn cần tác vụ ngoài, dùng định danh ổn định và một quy trình điều phối có trạng thái riêng.

`CONSUMED` xác nhận vòng đời giữ hàng đã được dùng để tạo allocation. Nó không tự xác nhận thanh toán hay giao hàng hoàn tất.

## 8. Idempotency khi đối tượng đã terminal

Một request lặp có thể tới sau khi trạng thái đã đổi. Hệ thống cần phân biệt đọc lại kết quả với tạo chuyển trạng thái mới.

| Tình huống | Cách xử lý có thể chấp nhận theo hợp đồng | Điều không được làm |
| --- | --- | --- |
| Cùng khóa, cùng nội dung sau CONSUMED | Trả kết quả đã lưu sau kiểm tra quyền | Phân bổ hoặc giảm lượng giữ lần nữa |
| Cùng khóa, khác order | Báo xung đột | Dùng kết quả cũ như quyền cấp cho order mới |
| Khóa mới cho reservation đã CONSUMED | Trả kết quả hiện tại hoặc từ chối tác động mới | Tạo allocation thứ hai |
| Tiêu thụ reservation EXPIRED | Từ chối hoặc yêu cầu tạo lần giữ mới | Chuyển lại ACTIVE rồi tiếp tục |
| Giải phóng lại RELEASED | Trả trạng thái ổn định hoặc báo không còn hành động theo hợp đồng | Cộng khả dụng lần nữa |
| Message cũ yêu cầu ACTIVE | Bỏ cập nhật không hợp lệ và ghi nhận phù hợp | Làm sống lại quyền đã kết thúc |
| Cần hoàn tác allocation | Mở nghiệp vụ điều chỉnh có thẩm quyền | Tự đổi CONSUMED về ACTIVE |

Idempotency không nhất thiết yêu cầu mọi request khác nhau đều trả cùng mã HTTP. Nó yêu cầu tác động nghiệp vụ không bị nhân lên ngoài hợp đồng khi gửi lại cùng ý định.

Tính duy nhất theo reservation hoặc quyết định bảo vệ trước việc đổi khóa. State machine bảo vệ tính hợp lệ của hành động. Hai cơ chế bổ sung cho nhau.

### 8.1. Hết hạn cache không mở lại quyền đã dùng

Nếu idempotency key chỉ được lưu một thời gian, ràng buộc miền và dấu vết kết thúc vẫn phải ngăn dùng lại reservation sau đó.

Không để việc cache bị xóa hoặc tiến trình khởi động lại trở thành điều kiện tạo một allocation mới từ cùng quyền cũ.

Không dùng lại định danh reservation cũ cho một lần giữ mới. Một lần giữ mới có điều kiện hiện tại, ngân sách hiện tại và lịch sử riêng.

### 8.2. Một kết quả terminal không phải quyền đọc công khai

Người biết reservationId hoặc khóa request không mặc nhiên có quyền xem order, chủ sở hữu hoặc kết quả allocation. Kiểm tra tenant và quan hệ vẫn cần khi trả replay hoặc truy vấn trạng thái.

Nếu quyền đọc đã bị thu hồi theo chính sách, có thể không trả dữ liệu cho caller hiện tại. Điều đó không làm tác động đã commit bị thực hiện lại hoặc tự đảo ngược.

## 9. Sự kiện muộn và kết quả chưa rõ

### 9.1. Bỏ qua sự kiện cũ cần dựa trên ngữ nghĩa

Một consumer nhận sự kiện ACTIVE phiên bản 7 sau khi đã áp dụng EXPIRED phiên bản 8 không được làm bản sao quay về ACTIVE.

Cần so phạm vi đối tượng, nguồn và phiên bản hoặc quy tắc thứ tự được định nghĩa. Thời điểm message tới không chứng minh đó là dữ kiện mới nhất.

Nếu sự kiện là lệnh tạo tác động chứ không chỉ cập nhật projection, còn cần tính duy nhất và guard tại nơi thực thi. Projection đúng trạng thái không tự ngăn một worker gửi lệnh trùng.

### 9.2. Không bỏ qua một sự kiện thực tế quan trọng chỉ vì có chữ terminal

Giả sử một lệnh hoàn bị đánh dấu thất bại nhưng sau đó nhà cung cấp xác nhận đã chuyển tiền. Không được đơn giản bỏ thông báo thành công rồi giữ một sổ sai.

Cần xác minh sự kiện và giải quyết mâu thuẫn: trạng thái thất bại trước đó có thật sự đủ điều kiện cuối cùng hay đã được chốt sai? Việc sửa sai phải có lịch sử, đối soát và thẩm quyền phù hợp.

Một sự kiện đảo giao dịch sau thành công cũng có thể là nghiệp vụ mới cần ghi nhận, không phải một message cũ để bỏ qua. Tùy mô hình, nó thuộc vòng đời liên quan hoặc chứng minh trạng thái được gọi là terminal đã được định nghĩa quá rộng.

### 9.3. Timeout không phải trạng thái thất bại cuối cùng

Các trạng thái như sau thường cần tiếp tục được xử lý:

~~~text
PENDING_EXTERNAL_RESULT
PENDING_RECONCILIATION
OUTCOME_UNKNOWN
~~~

Tên cụ thể tùy hệ thống. Ý nghĩa là chưa có bằng chứng đủ để chốt thành công hoặc thất bại.

Nếu đánh dấu FAILED ngay khi timeout rồi giải phóng ngân sách, một retry có thể tạo tác động thứ hai trong khi lần đầu đã thành công. Cần giữ mã lệnh ổn định, bảo toàn khoản giữ liên quan và truy vấn hoặc đối soát theo hợp đồng.

Một trạng thái cuối phải dựa trên điều kiện nghiệp vụ đã được xác định, không chỉ dựa trên việc số lần retry nội bộ đã hết.

### 9.4. Job hết hạn không được tin snapshot cũ

Nếu sản phẩm cho phép gia hạn khi ACTIVE, job có thể đã chụp expiresAt cũ trước khi một lần gia hạn hợp lệ hoàn tất.

Job phải kiểm tra lại trạng thái, thời hạn và phiên bản có thẩm quyền dưới cơ chế nhất quán. Không cập nhật EXPIRED chỉ vì một danh sách cũ nói rằng đối tượng đã đến hạn.

Mọi việc gia hạn cũng phải có chính sách, hạn mức và guard riêng. Không cho gia hạn một reservation đã terminal như cách phục hồi quyền cũ.

## 10. Bù trừ và mở quy trình mới không phải làm sống lại lịch sử

Trạng thái terminal không loại bỏ nhu cầu kinh doanh thay đổi kết quả. Nó buộc thay đổi đó phải có mô hình và quyền riêng.

### 10.1. Hủy đơn sau khi reservation đã được dùng

Nếu order bị hủy sau khi tạo allocation, không nên đổi reservation từ CONSUMED về ACTIVE. Cách đó có thể:

- Làm cùng reservation tiêu thụ lần nữa.
- Mất dấu allocation đã từng được tạo.
- Gây lệch bộ đếm và các sự kiện đã phát.
- Cho phép dùng lại thời hạn hoặc điều kiện cũ.

Thay vào đó, có thể tạo một thao tác giải phóng hoặc điều chỉnh allocation, tham chiếu allocation gốc, với điều kiện và tính duy nhất phù hợp.

Chỉ đưa hàng về khả dụng khi có đủ căn cứ theo quy trình. Hàng đã bàn giao vật lý không tự trở lại kho chỉ vì trạng thái đơn đổi.

Nếu mở rộng mô hình để có lượng trả lại khả dụng, phải mở rộng cả sổ và invariant. Ví dụ, khi C là tổng lượng đã phân bổ trong lịch sử và R là tổng lượng được khôi phục hợp lệ:

~~~text
A + H + C - R = K
~~~

Đây chỉ là một mô hình mở rộng minh họa khi không có nguồn nhập hoặc điều chỉnh khác. R cần chứng từ và giới hạn để không khôi phục cùng allocation nhiều lần. Không sửa công thức trong test mà bỏ cơ chế bảo vệ thực tế.

### 10.2. Thử lại sau một lần thực thi thất bại cuối cùng

Nếu nghiệp vụ cho phép một attempt mới sau thất bại cuối cùng đã xác minh, attempt cũ vẫn giữ kết quả cũ. Attempt mới có định danh, điều kiện và liên kết rõ ràng với ý định chung.

Không được tạo thêm quyền lợi chỉ vì có attempt mới. Các giới hạn tổng, số tiền đã thành công và phần đang chờ vẫn phải được bảo vệ.

Đặc biệt, chưa rõ kết quả không đủ để coi attempt cũ đã thất bại cuối cùng rồi tạo lệnh mới. Đây là khác biệt quan trọng giữa retry kỹ thuật của cùng lệnh và một lần thực hiện nghiệp vụ mới được cho phép.

### 10.3. Nếu sản phẩm thật sự cho mở lại cùng đối tượng

Có những quy trình cho mở lại một hồ sơ đã đóng. Khi đó cần mô hình hóa chuyển trạng thái, actor, điều kiện và phiên bản rõ ràng.

Trong phạm vi vòng đời bao gồm thao tác mở lại, CLOSED không phải terminal theo nghĩa không còn chuyển thông thường. Có thể tách từng lần xử lý thành một vòng đời con có kết quả cuối riêng.

Không nên vừa tuyên bố trạng thái là bất biến kết thúc, vừa để một API `reopen=true` bỏ mọi guard. Tên gọi và hợp đồng cần nhất quán.

### 10.4. Sửa một kết quả đã bị chốt sai

Một lỗi có thể khiến dữ liệu terminal không phản ánh sự thật. Cần điều tra, đối soát và sửa theo quy trình có quyền, có lý do và lịch sử trước–sau.

Giữ lịch sử không đồng nghĩa giữ một số dư hoặc trạng thái thực tế sai mãi. Mục tiêu là không che việc đã xảy ra và không tạo tác động mới ngoài quyền trong quá trình sửa.

## 11. Lưu trữ, xóa và khôi phục không được tái cấp quyền

Một reservation đã terminal có thể được lưu trữ hoặc giảm dữ liệu theo chính sách. Nhưng việc thiếu bản ghi không được tự biến thành quyền thực hiện lại.

### 11.1. Xác định bằng chứng tối thiểu cần giữ

Tùy mô hình, có thể cần:

- Định danh reservation và phạm vi tenant.
- Kết quả cuối, phiên bản và tham chiếu tác động.
- Tính duy nhất của allocation hoặc ý định đã dùng.
- Bằng chứng cần thiết để xử lý retry và đối soát.
- Liên kết với thao tác điều chỉnh nếu có.

Không mặc nhiên giữ mọi dữ liệu cá nhân vô hạn. Cần chính sách lưu và cách bảo toàn thuộc tính chống tái sử dụng bằng dữ kiện tối thiểu phù hợp.

Nếu dùng dấu vết tối thiểu hoặc tombstone để ghi nhận đối tượng đã kết thúc, nó cũng cần được bảo vệ và tham gia hợp đồng tạo hoặc thực thi. Một bảng tombstone không được caller kiểm tra sẽ không tự ngăn gì.

### 11.2. Không để đồng bộ ngược làm sống lại

Các nguồn có thể chứa bản cũ:

- Cache.
- Search index.
- File import.
- Message tồn đọng.
- Backup.
- Công cụ đồng bộ hai chiều.

Nguồn có thẩm quyền cần giữ quy tắc phiên bản và chuyển trạng thái. Một file import chứa ACTIVE không được ghi đè terminal chỉ vì nó được chạy sau.

Sau restore, cần khôi phục những quyết định và tác động đã có hiệu lực sau thời điểm backup theo kế hoạch phục hồi. Không chạy worker tạo tác động mới từ dữ liệu cũ trong khi lệnh bên ngoài có thể đã hoàn tất.

### 11.3. Không coi xóa cờ kết thúc là một thao tác bảo trì vô hại

Các trường như `closedAt`, `consumedBy` hoặc `terminalVersion` có thể là bằng chứng của tác động. Một công cụ “làm sạch dữ liệu” xóa chúng có thể phá idempotency hoặc truy nguyên.

Cần phân biệt sửa metadata không ảnh hưởng nghĩa với xóa điều kiện bảo vệ. Quyền quản trị và direct SQL vẫn phải nằm trong mô hình tin cậy, không phải ngoại lệ mặc định cho vòng đời.

## 12. Kiểm thử trạng thái kết thúc

Bắt đầu từ state machine và kiểm tra cả chuyển được phép lẫn chuyển bị cấm.

| Tình huống | Thao tác trong môi trường kiểm thử | Điều cần chứng minh |
| --- | --- | --- |
| Kết thúc hợp lệ | Tiêu thụ reservation ACTIVE đủ điều kiện | Có đúng allocation, trạng thái và bộ đếm |
| Tiêu thụ sau hết hạn | Dùng ACTIVE nhưng thời gian đã qua mốc | Không tạo phân bổ mới trái chính sách |
| Tiêu thụ EXPIRED | Gọi API sau khi job đã đóng | Không đổi lại ACTIVE hoặc phân bổ |
| Giải phóng CONSUMED | Gọi hủy khoản giữ đã dùng | Không trả khả dụng bằng đường cũ |
| Retry cùng request | Mất phản hồi sau commit rồi gửi lại | Cùng kết quả, không lặp tác động |
| Khóa mới | Dùng khóa khác cho reservation đã kết thúc | Không tạo quyền lợi mới |
| Cùng khóa khác order | Phát lại khóa với đối tượng đích khác | Xử lý xung đột và không dùng nhầm allocation |
| Xác nhận và hết hạn cạnh tranh | Hai transaction cùng chạm reservation | Chỉ một kết quả cuối và một loại tác động thắng |
| Entity cũ | Đọc ACTIVE, transaction khác đóng, rồi save bản cũ | Không ghi đè trạng thái terminal |
| Sửa metadata | Cập nhật ghi chú sau terminal | Không sửa lượng, chủ thể hoặc kết quả đã chốt |
| Message lệch thứ tự | Áp dụng terminal rồi nhận ACTIVE cũ | Không làm sống lại bản sao hoặc tác động |
| Job dùng hạn cũ | Gia hạn hợp lệ rồi cho job cũ chạy | Job đánh giá đúng dữ kiện hiện hành |
| Lỗi giữa transaction | Gây lỗi giữa trạng thái và bộ đếm hoặc outbox | Không commit kết quả cục bộ dở dang |
| Tác động ngoài chưa rõ | Bên ngoài thực hiện nhưng phản hồi mất | Không chốt thất bại và cấp lại quyền sai |
| Bù trừ | Hủy allocation theo quy trình mới | Giữ lịch sử reservation, không khôi phục cùng quyền cũ |
| Import hoặc restore | Nạp dữ liệu cũ có ACTIVE | Không tái thực thi tác động đã hoàn tất |
| Sai actor hoặc tenant | Dùng ID terminal của chủ thể khác | Không đọc kết quả hoặc tạo sửa đổi trái quyền |

### 12.1. Kiểm tra hơn một cột trạng thái

Sau mỗi kịch bản, cần xem:

- Reservation đang ở trạng thái nào và version nào?
- Có bao nhiêu allocation và chúng thuộc order nào?
- A, H và C hoặc mô hình điều chỉnh có khớp không?
- Có bao nhiêu outbox và tác động phía sau?
- Quyền và danh tính thực của actor có được giữ đúng không?
- Có dấu vết chuyển trạng thái bị từ chối hoặc xử lý lại phù hợp không?

Một hệ thống có thể kết thúc ở CONSUMED nhưng đã trả tồn về khả dụng trước đó. Chỉ kiểm tra `state == CONSUMED` sẽ bỏ sót lỗi này.

### 12.2. Kiểm thử cạnh tranh và thời gian

Dùng request hoặc session dữ liệu độc lập và cơ chế đồng bộ để tạo cạnh tranh thực sự. Hai request tuần tự không chứng minh được guard khi chạy song song.

Nếu dùng barrier, không đặt nó ở nơi luồng thứ nhất đã giữ khóa khiến luồng thứ hai không thể tới barrier. Test có thể tự tạo deadlock ngoài kịch bản muốn kiểm tra.

Dùng đồng hồ kiểm soát cho mốc hết hạn, đồng thời xác định thời điểm kiểm tra có thẩm quyền. Tránh chỉ sleep rồi hy vọng job đã hoàn tất.

Đọc snapshot nhất quán hoặc quan sát tại mốc hệ thống đã ổn định có kiểm soát. Ghép A từ trước chuyển trạng thái với H từ sau chuyển trạng thái có thể tạo lỗi giả.

### 12.3. Sinh chuỗi thao tác

Có thể sinh các chuỗi:

~~~text
giữ
  -> gia hạn nếu được phép
  -> tiêu thụ hoặc giải phóng
  -> retry
  -> phát message cũ
  -> chạy job hết hạn
  -> thử cập nhật entity cũ
~~~

Sau mỗi commit, kiểm tra không có chuyển từ terminal về trạng thái có quyền sử dụng trong mô hình cơ sở, không có allocation trùng và các tổng còn đúng.

Lưu seed, chuỗi thao tác và dữ kiện quan sát khi có counterexample. Một lần chạy qua chỉ cung cấp bằng chứng cho các lịch đã quan sát; cần kết hợp kiểm tra cơ chế dữ liệu và những đường ghi liên quan.

## 13. Quan sát vận hành và đối soát

Dấu vết nên nối được:

~~~text
reservationId
  -> stateTransitionId + version
  -> allocationId
  -> orderId
  -> outboxEventId
  -> downstreamExecutionId
~~~

Ghi actor, tenant, trạng thái trước–sau, lý do và thời điểm máy chủ cần thiết. Không đưa credential hoặc dữ liệu cá nhân không cần thiết vào log.

Các dấu hiệu cần điều tra:

- Một reservation có nhiều allocation ngoài chính sách.
- Tác động cấp hàng không có chuyển trạng thái hợp lệ.
- ACTIVE xuất hiện sau khi cùng reservation đã terminal.
- Bộ đếm giữ hoặc khả dụng không khớp chi tiết.
- Nhiều lần ép chuyển trạng thái qua công cụ quản trị.
- Đối tượng được đóng dù lệnh ngoài chưa rõ kết quả.
- Sự kiện đến muộn làm consumer quay lùi version.

Không tự sửa trạng thái hàng loạt để làm hết cảnh báo. Cần tìm nguyên nhân, xác minh tác động thật và dùng quy trình điều chỉnh có thẩm quyền.

Đối soát hỗ trợ phát hiện và phục hồi. Nó không thay thế guard nguyên tử ở điểm kết thúc hoặc unique constraint tại nơi tạo quyền lợi.

## 14. Hồ sơ thiết kế cho một trạng thái terminal

Với mỗi trạng thái được gọi là terminal, nên trả lời ngắn gọn:

| Nội dung | Câu hỏi cần ghi rõ |
| --- | --- |
| Phạm vi vòng đời | Đối tượng hoặc lần xử lý nào đã kết thúc? |
| Ý nghĩa | Quyền nào đã được dùng, giải phóng hoặc chấm dứt? |
| Bằng chứng | Dữ kiện nào đủ để chốt kết quả? |
| Chuyển vào | Actor và điều kiện nào được phép đóng? |
| Tác động đi cùng | Bản ghi, sổ và outbox nào phải nhất quán? |
| Gửi lại | Cùng khóa, khóa mới và message trùng được xử lý ra sao? |
| Sự kiện muộn | Cái gì bị bỏ qua, cái gì cần đối soát hoặc quy trình mới? |
| Sửa dữ liệu | Trường nào được bổ sung mà không đổi nghĩa kết quả? |
| Bù trừ | Nếu cần thay đổi hậu quả, quy trình mới nào được dùng? |
| Lưu trữ | Bằng chứng tối thiểu nào cần giữ để không tái cấp quyền? |
| Kiểm thử | Những race, lỗi và đường ghi nào phải được kiểm tra? |

Một tài liệu như vậy giúp phát hiện sớm các trạng thái chỉ có tên “hoàn tất” nhưng chưa có điều kiện đủ để coi là kết thúc.

## 15. Những cách triển khai dễ phá ranh giới kết thúc

| Cách triển khai | Vấn đề | Hướng hoàn thiện |
| --- | --- | --- |
| Enum có trạng thái cuối nhưng không guard | Caller vẫn đổi tùy ý | Command và chuyển trạng thái có điều kiện |
| Chỉ ẩn nút sau khi đóng | API vẫn gọi trực tiếp được | Thực thi tại máy chủ |
| Đóng trước, cập nhật sổ sau | Có thể commit nửa chừng | Transaction cục bộ và outbox phù hợp |
| Entity cũ save toàn bộ trường | Có thể ghi lại ACTIVE | Phiên bản, cập nhật có điều kiện hoặc khóa |
| Chỉ dùng idempotency cache | Hết cache có thể tạo lại tác động | Ràng buộc miền và tính duy nhất lâu dài phù hợp |
| Timeout được gán FAILED | Chốt kết quả khi chưa biết | Trạng thái chưa rõ và đối soát |
| Bỏ mọi message sau terminal | Có thể bỏ sự kiện thật hoặc bằng chứng chốt sai | Phân loại ngữ nghĩa và xử lý mâu thuẫn |
| Đổi về ACTIVE để bù trừ | Tái cấp quyền cũ và mất lịch sử | Điều chỉnh hoặc vòng đời mới có tham chiếu |
| Terminal đồng nghĩa không được sửa gì | Cản thông tin bổ sung hợp lệ | Tách metadata và nội dung quyết định |
| Restore rồi chạy worker ngay | Dữ liệu cũ có thể phát lại tác động | Khôi phục bằng chứng và đối soát trước khi phục vụ |

## 16. Bài tập tự kiểm tra

### Bài 1: đã hết giờ nhưng vẫn ACTIVE

Job hết hạn chưa chạy. Request tiêu thụ đến sau expiresAt và code chỉ kiểm tra `state == ACTIVE`.

**Gợi ý trả lời:** ACTIVE chưa đủ chứng minh còn hiệu lực. Phải kiểm tra thời gian theo chính sách tại mốc có thẩm quyền, cùng cơ chế tranh chấp. Job chạy muộn không tự gia hạn quyền giữ.

### Bài 2: hủy đơn sau allocation

Order bị hủy sau khi reservation đã CONSUMED. Lập trình viên đổi reservation về ACTIVE để khách dùng lại sau.

**Gợi ý trả lời:** cách này làm sống lại một quyền đã dùng và có thể tạo allocation mới từ điều kiện cũ. Cần quy trình giải phóng hoặc điều chỉnh allocation có căn cứ, giữ lịch sử reservation và tạo lần giữ mới nếu muốn cấp quyền mới.

### Bài 3: retry sau khi idempotency cache hết hạn

Một request tiêu thụ cũ được gửi lại bằng khóa mới sau khi cache đã xóa.

**Gợi ý trả lời:** state machine và unique theo reservation phải ngăn allocation thứ hai. Cache chỉ hỗ trợ nhận diện request trong cửa sổ của nó, không phải bằng chứng duy nhất rằng quyền đã được sử dụng.

### Bài 4: thông báo thành công sau trạng thái FAILED

Lệnh ngoài bị gán FAILED do timeout. Sau đó nhận bằng chứng đã thành công.

**Gợi ý trả lời:** cần xác minh và đối soát, không bỏ qua chỉ vì trạng thái đã được gọi là terminal. Timeout chưa đủ để chốt thất bại cuối cùng. Phải sửa mâu thuẫn có lịch sử, đồng thời kiểm tra đã có lệnh mới hoặc ngân sách bị giải phóng sai hay chưa.

## 17. Các điểm cần ghi nhớ

Trạng thái terminal kết thúc một vòng đời được định nghĩa rõ, với điều kiện và bằng chứng đủ để chốt quyền hoặc kết quả. Nó không đồng nghĩa mọi dữ liệu bất biến hoặc mọi sự kiện tương lai đều không còn ý nghĩa.

Guard trạng thái, quyền theo đối tượng, binding nội dung, transaction, kiểm soát cạnh tranh và tính duy nhất phải cùng giữ ranh giới kết thúc. Retry, job, message cũ, import và công cụ quản trị đều phải tuân thủ.

Câu hỏi cốt lõi là: **Khi hệ thống nói đối tượng đã kết thúc, điều gì đã thật sự được chốt, và cơ chế nào ngăn quyền hoặc tác động cũ bị sử dụng lại mà vẫn cho phép xử lý đúng các sự kiện mới?**
