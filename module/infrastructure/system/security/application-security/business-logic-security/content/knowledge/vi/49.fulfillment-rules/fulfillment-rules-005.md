# Hủy thực hiện đơn hàng (Fulfillment cancellation)

Hủy fulfillment là quá trình dừng một phần hoặc toàn bộ cam kết chuẩn bị và giao hàng. Đây không chỉ là thao tác đổi một cột `status`: hàng có thể đã được lấy khỏi kệ, đóng gói, đưa vào chuyến vận chuyển hoặc bàn giao cho đơn vị giao nhận; tiền có thể mới được giữ hạn mức hoặc đã thu.

Trong chương **Fulfillment Rules**, việc hủy cần bảo vệ một số quy tắc nghiệp vụ đồng thời: không vừa hủy vừa xuất cùng phần hàng, không nhả giữ hàng hai lần, không hoàn tiền vượt phần được phép và không cho người dùng tác động lên đơn ngoài quyền. Chủ đề này kết nối business invariants, state machine, quyền theo đối tượng, transaction, idempotency và kiểm thử tình huống tấn công logic.

Sau bài học, bạn có thể:

- Xác định khi nào một yêu cầu hủy còn hợp lệ và ai có quyền gửi hoặc phê duyệt.
- Phân biệt việc tiếp nhận yêu cầu, xác nhận dừng giao, thu hồi hàng và xử lý tiền.
- Thiết kế chuyển trạng thái an toàn khi hủy cạnh tranh với lấy hàng hoặc xuất kho.
- Xử lý hủy từng phần, retry và sự kiện lặp mà không tạo tác động nghiệp vụ trùng.
- Xây dựng audit và kiểm thử cho các trường hợp lỗi giữa nhiều dịch vụ.

## 1. Hủy cái gì và hủy đến đâu?

### 1.1. Phân biệt các đối tượng nghiệp vụ

Một đơn hàng có thể sinh nhiều fulfillment, mỗi fulfillment chứa một phần số lượng của một hoặc nhiều dòng đơn. Một fulfillment cũng có thể liên quan nhiều kiện hoặc nhiều lần bàn giao tùy mô hình.

| Đối tượng | Vai trò | Ví dụ |
| --- | --- | --- |
| Order | Cam kết mua bán ở cấp đơn | Đơn O-100 mua 10 sản phẩm |
| Order line | Mặt hàng và số lượng được đặt | Dòng L1 gồm 10 đơn vị SKU-A |
| Allocation/reservation | Phần tồn kho được dành cho cam kết | Kho W1 giữ 6, kho W2 giữ 4 |
| Fulfillment | Kế hoạch thực hiện giao một phần hàng | F1 giao 4, F2 giao 6 |
| Shipment/package | Kiện hoặc lần vận chuyển | Kiện P1 đã được bàn giao |
| Cancellation request | Ý định hủy một phạm vi cụ thể | Hủy 3 đơn vị thuộc F2 |
| Refund obligation | Nghĩa vụ hoàn tiền phát sinh hợp lệ | Hoàn phần tiền của 3 đơn vị đã xác nhận hủy |

Không suy ra rằng hủy F2 đồng nghĩa hủy cả đơn O-100 hoặc được phép hoàn toàn bộ tiền của đơn. Ngược lại, một API “hủy đơn” phải phân rã ý định thành các phần fulfillment còn đủ điều kiện và báo rõ phần không thể hủy.

### 1.2. Hủy, chặn giao và trả hàng là các quy trình khác nhau

- **Hủy fulfillment:** dừng cam kết giao cho phần hàng còn có thể dừng an toàn.
- **Chặn hoặc thu hồi chuyến giao:** cố gắng ngăn phần hàng đã vượt cổng xuất; cần xác nhận từ bên đang kiểm soát hàng.
- **Trả hàng:** xử lý hàng đã giao hoặc đã đi vào quy trình giao không còn hủy được theo chính sách thông thường.

Một request mang tên `cancel` không được tự biến hàng đã giao thành tồn kho có thể bán. Nếu đã vượt ngưỡng hủy, hệ thống phải từ chối theo chính sách hoặc mở quy trình ngoại lệ phù hợp, có trạng thái và bằng chứng riêng.

### 1.3. Tiếp nhận yêu cầu chưa có nghĩa là hủy thành công

Ví dụ, HTTP `202 Accepted` có thể chỉ cho biết yêu cầu đã được lưu để xử lý. Kết quả đó không chứng minh kho đã dừng đóng gói, carrier đã ngừng nhận kiện hoặc tiền đã được hoàn.

Một phản hồi hữu ích cần có:

```json
{
  "cancellationId": "C-203",
  "decision": "PENDING",
  "requestedQuantity": 3,
  "confirmedQuantity": 0,
  "statusUrl": "/cancellations/C-203"
}
```

Client phải đọc kết quả theo hợp đồng API, không coi mọi mã `2xx` là hủy hoàn tất. API tra cứu trạng thái cũng cần kiểm tra quyền trên cancellation và đơn liên quan.

## 2. Mô hình trạng thái và ranh giới không thể bỏ qua

### 2.1. Trạng thái fulfillment và trạng thái hủy nên được phân biệt

Một luồng thực hiện hàng minh họa:

```text
READY -> PICKING -> PACKED -> DISPATCH_COMMITTED -> SHIPPED -> DELIVERED
```

Một luồng quyết định hủy minh họa:

```text
PENDING -> STOPPING -> CONFIRMED
   |          |
   +----------+----> REJECTED
   |
   +---------------> NEEDS_REVIEW
```

Ý nghĩa các trạng thái:

| Trạng thái hủy | Ý nghĩa |
| --- | --- |
| `PENDING` | Đã lưu yêu cầu, chưa có bằng chứng đủ để khẳng định hàng sẽ không được xuất |
| `STOPPING` | Bên có thẩm quyền đã chặn tiến trình xuất mới cho phần hàng, đang hoàn tất việc dừng |
| `CONFIRMED` | Đã xác nhận phần hàng không tiếp tục được giao theo fulfillment đó |
| `REJECTED` | Không chấp nhận hủy phạm vi được yêu cầu; có lý do nghiệp vụ rõ ràng |
| `NEEDS_REVIEW` | Chưa đủ thông tin hoặc có xung đột cần xử lý có kiểm soát |

Đây là mô hình gợi ý, không phải danh sách trạng thái bắt buộc cho mọi hệ thống. Cần quy định chuyển trạng thái cho từng loại fulfillment và không cho client tùy ý gửi trạng thái đích.

Với luồng kho cần xác nhận vật lý, `STOPPING` chỉ chuyển sang `CONFIRMED` sau khi đã có bằng chứng dừng theo quy trình. Nếu phát hiện một tác vụ xuất đã được chốt trước khi cổng dừng có hiệu lực, phải giải quyết theo kết quả có thẩm quyền; không xác nhận hủy chỉ vì lệnh dừng đã được gửi.

### 2.2. Xác định cổng chốt xuất

Trong bài học, `DISPATCH_COMMITTED` là điểm hệ thống có thẩm quyền chốt quyền xuất của một phần hàng. Sau điểm này, chính sách minh họa không cho hủy thông thường; muốn chặn tiếp phải dùng quy trình ngoại lệ.

Cổng này cần được định nghĩa bằng một sự kiện có thể kiểm chứng, gắn với thao tác kho và quyền bàn giao. Việc tạo nhãn vận chuyển hoặc in phiếu lấy hàng không mặc nhiên có nghĩa hàng đã rời kho.

Ngược lại, nếu thực tế kiện đã được bàn giao nhưng hệ thống vẫn cho hủy vì chưa nhận webhook, ranh giới bảo vệ đã được đặt sai hoặc chưa được thực thi đầy đủ.

### 2.3. Hủy đã xác nhận vẫn có thể còn công việc tiếp theo

Cần theo dõi riêng:

```text
cancellation_decision = CONFIRMED
inventory_recovery   = PENDING
refund_status        = PROCESSING
```

Trạng thái trên có thể hợp lệ: kho đã bảo đảm không giao tiếp nhưng hàng đang được đưa về vị trí phù hợp, còn dịch vụ thanh toán đang xử lý hoàn tiền.

Không báo “hoàn tiền thành công” khi mới tạo tác vụ hoàn. Cũng không chuyển đơn trở lại giao hàng chỉ vì một tác vụ hoàn tiền bị lỗi; hủy cam kết giao và hoàn thành nghĩa vụ tiền là hai quyết định khác nhau.

## 3. Các bất biến cần bảo vệ

### 3.1. Bảo toàn số lượng của từng dòng đơn

Với một dòng có số lượng đã xác nhận `N`, mô hình minh họa phân chia lượng đó thành bốn nhóm:

```text
N = Q_open + Q_cancel_pending + Q_cancelled + Q_dispatch_committed

Q_open >= 0
Q_cancel_pending >= 0
Q_cancelled >= 0
Q_dispatch_committed >= 0
```

Trong đó:

- `Q_open`: chưa chốt xuất, chưa thuộc một yêu cầu hủy đang chiếm giữ phần lượng đó.
- `Q_cancel_pending`: phần đang được xử lý hủy, chưa có kết luận cuối cùng.
- `Q_cancelled`: phần đã xác nhận hủy cam kết giao.
- `Q_dispatch_committed`: phần đã vượt cổng chốt xuất, bao gồm hàng có thể đã giao.

Không phải mọi lượng `Q_open` đều đủ điều kiện hủy: còn phải xét loại hàng, thời hạn, quyền và trạng thái quy trình. Trả hàng và đặt lại hàng là các nghiệp vụ riêng, không tự giảm `Q_dispatch_committed` để mở lại quyền hủy cũ.

Mỗi đơn vị hoặc phần allocation phải thuộc đúng một nhóm trong mô hình có thẩm quyền. Trong hệ thống phân tán, bản sao tại dịch vụ đơn hàng có thể chậm hơn kho; phải phân biệt trạng thái đã xác nhận với suy đoán từ projection.

### 3.2. Một phần hàng không được vừa hủy vừa chốt xuất

Quy tắc quan trọng là tính loại trừ trên **cùng phần allocation**, không chỉ trên tổng lượng của đơn:

```text
cancel(part) và commitDispatch(part)
không thể cùng được chấp nhận như hai kết quả cuối hợp lệ
```

Một fulfillment có thể được tách để hủy 3 và xuất 3. Nhưng không thể hủy đúng 3 đơn vị đó rồi vẫn cho tác vụ xuất cũ giao chúng đi.

Cần định danh phần allocation hoặc phần fulfillment sau khi tách. Chỉ lưu một bộ đếm `cancelledQuantity` trên order mà không biết tác động lên phần hàng nào sẽ làm việc phân xử và đối soát khó hơn.

### 3.3. Mỗi hiệu ứng chỉ được thực hiện một lần

Một cancellation đã được xác nhận có thể sinh nhiều hiệu ứng:

```text
STOP_FULFILLMENT
RELEASE_RESERVATION
RECOVER_PICKED_STOCK
VOID_AUTHORIZATION hoặc CREATE_REFUND_OBLIGATION
NOTIFY_CUSTOMER
```

Mỗi hiệu ứng cần định danh bền vững, ví dụ:

```text
(tenant_id, cancellation_id, allocation_part_id, effect_type)
```

Retry hoặc sự kiện lặp không được nhả reservation, đưa hàng về tồn hoặc tạo nghĩa vụ hoàn tiền lần nữa.

Không đặt unique trên toàn bộ `order_id` vì một đơn có thể có nhiều yêu cầu hủy từng phần hợp lệ. Cũng không kết luận rằng hai yêu cầu có cùng số lượng là một: cần biết chúng đang chỉ tới cùng ý định và cùng phần hàng hay tới những phần còn lại khác nhau.

### 3.4. Không vượt quyền và không tự tính tiền từ dữ liệu không tin cậy

Mỗi quyết định hủy phải gắn với tenant, người sở hữu hoặc vai trò được cấp quyền, đối tượng fulfillment và lý do nghiệp vụ hợp lệ.

Số tiền hoàn phải được server tính từ chứng từ giá và thanh toán gốc, phần lượng đã xác nhận hủy cùng chính sách áp dụng. Client không được quyết định số tiền bằng cách gửi `refundAmount` hoặc tự chỉ định tài khoản nhận tiền ngoài quy trình cho phép.

## 4. Chính sách đủ điều kiện hủy và quyền theo đối tượng

### 4.1. Điều kiện phải là một quyết định nghiệp vụ rõ ràng

| Khía cạnh | Ví dụ kiểm tra |
| --- | --- |
| Danh tính | Người dùng đã xác thực hoặc có cơ chế truy cập đơn khách vãng lai hợp lệ |
| Phạm vi | Đúng tenant, đơn, dòng đơn, fulfillment và phần allocation |
| Vai trò | Chủ đơn được hủy trong phạm vi cho phép; nhân viên hỗ trợ có quyền tương ứng |
| Tiến độ | Chưa vượt cổng chốt xuất của chính sách |
| Số lượng | Dương, không vượt phần còn có thể yêu cầu hủy |
| Loại hàng | Hàng đặt riêng hoặc dịch vụ đang thực hiện có thể cần quy tắc riêng |
| Phê duyệt | Ngoại lệ hoặc vượt ngưỡng cần đúng cấp duyệt |
| Nội dung đã duyệt | Kho, phần hàng, số lượng và căn cứ chưa bị thay đổi sau approval |

Các quy tắc về thời hạn hoặc loại hàng phải được quyết định ở server. Không dựa vào nút hủy đang hiện trên giao diện hay một field `isCancellable` được client gửi lại.

Nếu cần giải thích quyết định theo thời gian, lưu phiên bản chính sách được dùng. Không để cùng một cancellation thay đổi căn cứ tùy vào cấu hình mới mà không có quy tắc xử lý rõ ràng.

### 4.2. Mỗi đường vào đều phải giữ cùng bất biến

Không chỉ API của khách hàng mới cần kiểm tra. Portal hỗ trợ, tác vụ quản trị, consumer sự kiện, batch xử lý và tích hợp kho đều có thể trở thành đường vòng.

Một nhân viên hỗ trợ có quyền xem đơn chưa chắc có quyền hủy sau khi chốt xuất. Một service có quyền xử lý message chưa chắc được phép thay tenant hoặc xác nhận hủy mọi kho.

Nếu có quyền ngoại lệ, cần giới hạn phạm vi, lý do và phê duyệt theo chính sách. Không dùng một cờ `force=true` để bỏ qua mọi điều kiện về hàng, tiền và dấu chống trùng.

### 4.3. Replay cũng phải được kiểm tra quyền

Khi nhận lại cùng idempotency key, hệ thống có thể trả lại kết quả cũ nhưng vẫn phải xác thực người gọi và kiểm tra họ được đọc kết quả đó. Một key đoán được không được trở thành cách lấy thông tin đơn hàng của người khác.

Thông tin lỗi cũng phải tuân theo phạm vi truy cập. Không cần tiết lộ đơn có tồn tại hay đang giao đến đâu cho người không có quyền trên đơn.

## 5. Luồng tiếp nhận yêu cầu hủy an toàn

### 5.1. Dữ liệu đầu vào nên thể hiện ý định

Một command minh họa:

```json
{
  "orderId": "O-100",
  "fulfillmentId": "F-2",
  "lines": [
    { "orderLineId": "L-1", "quantity": 3 }
  ],
  "reasonCode": "CUSTOMER_CHANGED_MIND"
}
```

Idempotency key có thể truyền qua header theo hợp đồng API. Các ID vẫn cần được tra cứu và kiểm tra quan hệ: F-2 phải thuộc O-100, L-1 phải nằm trong phạm vi fulfillment phù hợp và mọi đối tượng phải thuộc tenant được phép.

Danh tính người thao tác, tenant thực thi, lượng đã xuất, lượng còn giữ và số tiền hoàn được lấy từ nguồn server có thẩm quyền. Cần chuẩn hóa dòng trùng trong request hoặc từ chối chúng; không để hai dòng cùng `orderLineId` vượt kiểm tra giới hạn nếu mỗi dòng được xét độc lập.

### 5.2. Transaction tiếp nhận không nên tạo tác động cuối quá sớm

Đoạn dưới là **mã giả** cho trường hợp cần kho xác nhận bất đồng bộ:

```text
requestCancellation(context, command, idempotencyKey):
    principal = authenticate(context)
    validatePositiveQuantitiesAndBounds(command)
    authorizeOrderAndFulfillment(principal, command)
    normalized = normalizeAndResolveLineReferences(command)
    fingerprint = businessFingerprint(normalized, principal.scope)

    response = transaction:
        request = claimIdempotency(
            principal.scope,
            idempotencyKey,
            fingerprint
        )

        if request.alreadyExists:
            require request.fingerprint == fingerprint
            require principal may read request.cancellation
            return request.savedAcceptanceResponse

        lock order lines and allocation parts in stable order
        recheck ownership, policy and current local states
        require requested quantities fit eligible unclaimed quantities

        cancellation = createCancellation(PENDING)
        claim quantities for this cancellation
        increment relevant aggregate versions

        appendCancellationAudit(cancellation, principal)
        appendOutbox(
            type = TRY_STOP_FULFILLMENT,
            cancellationId = cancellation.id,
            exactAllocationParts = selectedParts,
            expectedVersions = selectedParts.versions
        )

        response = buildPendingResponse(cancellation)
        saveAcceptanceResponse(request, response)

    return response after successful commit
```

Transaction này chưa nhả hàng và chưa hoàn tiền. Nó lưu ý định, quyền chiếm giữ lượng đang yêu cầu và thông điệp cần gửi một cách bền vững.

Nếu kho là hệ thống độc lập, claim tại dịch vụ đơn hàng chưa bảo đảm đã thắng cuộc đua với chốt xuất tại kho. Trạng thái vẫn là `PENDING` cho tới khi nguồn có thẩm quyền phân xử và phản hồi.

Khi toàn bộ quyết định và dữ liệu kho cùng nằm trong một database, có thể xác nhận hủy ngay trong transaction nếu đã thỏa đủ điều kiện. Không cần bắt buộc mọi mô hình đi qua message broker; điều quan trọng là ranh giới nhất quán bao phủ được quyết định loại trừ.

### 5.3. Idempotency có hai lớp trách nhiệm

**Lớp request:** unique theo phạm vi phù hợp, chẳng hạn `(tenant_id, caller_id, idempotency_key)`; fingerprint gắn key với đúng nội dung chuẩn hóa.

**Lớp nghiệp vụ:** cancellation và từng hiệu ứng có định danh riêng, còn lượng trên allocation được kiểm soát theo trạng thái và transaction.

Cùng key khác payload phải báo xung đột. Cùng cancellation được gửi lại bằng key khác không được sinh lại hiệu ứng đã hoàn thành. Một ý định mới muốn hủy phần khác vẫn phải kiểm tra lượng và quyền còn lại.

Kết quả tiếp nhận có thể giữ nguyên cancellation ID khi replay; endpoint trạng thái cung cấp tiến độ mới nhất. Không tạo một cancellation mới chỉ vì phản hồi đầu tiên bị mất.

## 6. Cuộc đua giữa hủy và xuất: chọn đúng nơi phân xử

### 6.1. Khóa phải bảo vệ cùng phần dữ liệu

Nếu cùng một database quản lý cổng xuất và quyền hủy:

```text
Transaction hủy                    Transaction xuất
-------------------------------   -------------------------------
Khóa allocation part              Khóa cùng allocation part
Kiểm tra chưa chốt xuất           Kiểm tra chưa bị chặn/hủy
Chuyển sang STOPPING              Chuyển sang DISPATCH_COMMITTED
Tăng version                      Tăng version
Commit                            Commit
```

Một bên phải đợi hoặc nhận conflict. Bên đến sau đọc trạng thái mới và quyết định theo state machine; không tiếp tục sử dụng dữ liệu đã đọc trước khi khóa.

Có thể dùng optimistic locking hoặc cập nhật có điều kiện thay khóa tường minh. Khi đó phải kiểm tra số hàng bị ảnh hưởng và xử lý conflict bằng cách đọc lại quyết định; không coi update ảnh hưởng 0 hàng là thành công.

### 6.2. Khóa tại dịch vụ đơn hàng không khóa được kho độc lập

Một tình huống nguy hiểm:

```text
T1: Dịch vụ đơn hàng đọc fulfillment = PACKED.
T2: Kho chốt xuất và bắt đầu bàn giao kiện.
T3: Dịch vụ đơn hàng đổi trạng thái thành CANCELLED.
T4: Dịch vụ tồn kho nhả giữ; dịch vụ tiền tạo refund.
T5: Khách vừa được giao hàng, vừa được hoàn tiền.
```

Giải pháp cần một bên có quyền quyết định cổng xuất của chính phần hàng đó. Nếu WMS quản lý cổng này, lệnh hủy phải được WMS phân xử với lệnh xuất, thay vì chỉ sửa bản sao trạng thái ở dịch vụ đơn hàng.

Khi WMS xác nhận dừng, nó phải bảo đảm tác vụ xuất mới không tiếp tục được nhận và các tác vụ đã phát ra được xử lý theo quy trình. Chỉ gửi một message “stop” rồi lập tức xác nhận hủy ở dịch vụ khác không tạo bảo đảm đó.

### 6.3. Version và fencing token phải được kiểm tra tại nơi thực thi

Một thiết kế có thể dùng revision hoặc fencing token để ngăn tác vụ cũ tiếp tục:

```text
Allocation part A:
    version = 8
    state = PACKED

WMS chấp nhận dừng:
    state = STOPPING
    version = 9

Tác vụ xuất cũ mang token/version 8:
    bị từ chối tại cổng thực thi
```

Tăng version chỉ trong database của coordinator không đủ nếu scanner, worker kho hoặc hệ thống bàn giao vẫn chấp nhận token cũ.

Nếu một lệnh xuất cũ đã được cổng có thẩm quyền chấp nhận trước khi dừng, không thể suy ra nó chưa xảy ra chỉ vì chưa có phản hồi. Nếu thiết bị làm việc offline, hệ thống phải có quy trình dừng và xác nhận đủ mạnh; khi chưa biết kết quả, giữ trạng thái chờ hoặc xử lý ngoại lệ thay vì tự kết luận hủy thành công.

Cơ chế lease hoặc lock có thời hạn cũng không tự thu hồi công việc đã được bên ngoài chấp nhận. Cần thiết kế để bên thực thi thực sự kiểm tra quyền xuất còn hiệu lực.

### 6.4. Timeout là chưa biết kết quả

Lệnh dừng timeout có thể xảy ra trước khi kho nhận lệnh, sau khi đã dừng nhưng trước khi trả lời, hoặc khi kết quả chưa được đồng bộ.

Do đó:

- Retry cùng định danh yêu cầu và hiệu ứng.
- Tra cứu kết quả ở nguồn có thẩm quyền.
- Duy trì việc chặn các quyết định mâu thuẫn trong phạm vi đã được xác nhận.
- Chuyển sang `NEEDS_REVIEW` nếu không thể tự xác định kết quả an toàn trong thời gian cho phép.

Không tự xác nhận hủy, nhả hàng hoặc tạo một lệnh xuất mới chỉ dựa trên việc đồng hồ chờ đã hết.

## 7. Tồn kho: dừng giao không đồng nghĩa hàng đã có thể bán lại

### 7.1. Nhả đúng reservation, đúng phần còn hiệu lực

Khi cancellation được xác nhận, cần tìm phần reservation hoặc allocation tương ứng. Không nhả bằng cách giảm một bộ đếm chung mà không biết reservation nào đang được giải phóng.

Nếu một phần đã được xuất hoặc nhả trước đó, lượng được nhả thêm phải dựa trên lượng còn lại. Retry của `RELEASE_RESERVATION` sử dụng cùng định danh hiệu ứng và không tạo movement lần hai.

Với mô hình tồn kho phổ biến:

```text
available = on_hand - reserved

Nhả reservation q chưa xuất:
    delta_on_hand = 0
    delta_reserved = -q
```

Nhả giữ không phải nhập hàng mới. Nếu cộng thêm `on_hand` khi hủy phần hàng vẫn còn trong kho, hệ thống sẽ tự tạo tồn kho ảo.

### 7.2. Hàng đã lấy khỏi kệ cần luồng thu hồi phù hợp

Một kiện bị hủy có thể đang ở khu đóng gói, cần tháo nhãn hoặc kiểm tra chất lượng trước khi được phân bổ lại.

Nếu trạng thái hàng và vị trí là các chiều tồn kho, có thể cần chuyển từ ngăn đã lấy sang ngăn chờ kiểm tra rồi mới về ngăn có thể bán. Trong thời gian đó, việc giảm reservation không được làm lượng chưa đủ điều kiện xuất hiện như hàng có thể bán ngay.

Thiết kế có thể duy trì hold phục hồi, chuyển bucket trạng thái hoặc chỉ giải phóng khi đủ bằng chứng. Phải chọn cách phù hợp với công thức available thực tế; không giả định việc nhả reservation luôn an toàn ở mọi vị trí.

Các movement phục hồi phải liên kết tới cancellation và thao tác vật lý liên quan. Không dùng một adjustment tùy ý để làm số dư khớp mà bỏ mất căn cứ.

### 7.3. Hủy sau khi đã ghi xuất không được đảo tồn tùy tiện

Nếu hàng đã chốt xuất hoặc đã rời kho, muốn đưa lại tồn cần chứng minh hàng thực sự đã quay về hoặc quyền kiểm soát đã được phục hồi theo mô hình nghiệp vụ.

Đảo dấu movement xuất mà không có xác nhận đó có thể làm hệ thống bán tiếp cùng một món hàng đang trên đường giao. Quy trình thu hồi hoặc trả hàng phải quản lý được sự kiện nhận lại, tình trạng hàng và phần lượng đủ điều kiện nhập lại.

## 8. Thanh toán: hủy quyền giao và xử lý tiền phải liên kết đúng

### 8.1. Phân biệt authorization, capture và refund

| Trạng thái tiền | Hành động có thể phù hợp sau khi hủy được xác nhận |
| --- | --- |
| Chưa giữ hoặc thu tiền | Không tạo refund cho khoản chưa thu |
| Chỉ có authorization | Giảm hoặc hủy phần authorization theo khả năng và chính sách tích hợp |
| Đã capture | Tạo nghĩa vụ hoàn cho phần tiền đủ điều kiện |
| Capture hoặc refund chưa rõ kết quả | Đối soát kết quả; không đoán rồi thực hiện thêm một lần |
| Có nhiều khoản thu hoặc nhiều phương thức | Phân bổ nghĩa vụ vào đúng nguồn thanh toán theo quy tắc |

Capture có thể cạnh tranh với hủy authorization. Dịch vụ thanh toán cần phân xử dựa trên trạng thái có thẩm quyền và kết quả từ nhà cung cấp; một bản sao `paymentStatus` cũ ở order không đủ để quyết định.

### 8.2. Tính từ chứng từ gốc và phần được hủy

Giá gốc, giảm giá được phân bổ, thuế, phí vận chuyển, số tiền đã thu và các lần hoàn trước ảnh hưởng đến số tiền cần xử lý.

Ví dụ chính sách minh họa:

```text
Dòng đơn: 10 sản phẩm, giá 100.000 đồng/sản phẩm.
Giảm giá dòng: 100.000 đồng, phân bổ đều.
Giá trị hàng thuần của dòng: 900.000 đồng.
Đã thu đủ; chưa hoàn lần nào.
Xác nhận hủy 3 sản phẩm.
Phần tiền hàng tương ứng: 3 x 90.000 = 270.000 đồng.
```

Ví dụ chỉ tính phần tiền hàng của dòng. Quy tắc về thuế, phí giao hàng, ưu đãi và làm tròn cần được định nghĩa riêng từ chứng từ và chính sách áp dụng. Không lấy giá catalog hiện tại để hoàn một giao dịch đã chốt theo giá khác.

Tiền cần dùng đơn vị nhỏ nhất hoặc kiểu thập phân chính xác theo hệ tiền tệ. Quy tắc phân bổ phải bảo đảm các phần cộng lại khớp tổng chứng từ, kể cả khi không thể chia đều tuyệt đối.

### 8.3. Một nghĩa vụ hoàn có thể có nhiều lần thử kỹ thuật

Nên có `refund_obligation_id` gắn với cancellation và thành phần tiền. Nhiều lần retry kỹ thuật vẫn thực hiện cùng nghĩa vụ, không tạo khoản hoàn nghiệp vụ mới.

Một giới hạn quan trọng tại phần tiền được phân bổ:

```text
available_to_claim_for_refund
    = captured_amount
    - succeeded_refund_amount
    - amount_reserved_by_other_unresolved_refund_obligations
```

Phải claim ngân sách hoàn trong transaction của dịch vụ thanh toán để hai worker không cùng sử dụng phần tiền còn lại. Nghĩa vụ đang chờ hoặc chưa biết kết quả vẫn phải được tính giữ chỗ; không giải phóng chỉ vì timeout.

Khi gọi nhà cung cấp, dùng cơ chế chống trùng phù hợp của tích hợp và giữ liên kết giữa obligation, lần thử và transaction bên ngoài. Nếu chưa rõ kết quả, tra cứu hoặc đối soát trước khi cấp một khóa mới có thể tạo thêm khoản hoàn.

### 8.4. Lỗi hoàn tiền không tự mở lại fulfillment

Khi cancellation đã được xác nhận và hàng đã dừng, một lỗi payment cần tạo retry hoặc công việc vận hành. Không tự bỏ chặn xuất để “bù” cho lỗi hoàn tiền.

Nếu khách muốn mua lại, đó là ý định mới cần kiểm tra quyền, giá, tồn kho và thanh toán theo quy trình phù hợp. Việc sửa một cột `status` trở lại `READY` có thể làm lệnh cũ chạy lại, mất dấu căn cứ hoặc tạo nghĩa vụ tiền mâu thuẫn.

## 9. Điều phối nhiều dịch vụ và phục hồi sau lỗi

### 9.1. Dùng outbox/inbox để chống mất và chống lặp

Trong mỗi dịch vụ, thay đổi trạng thái cục bộ và ghi outbox phải nằm cùng transaction. Consumer cần ghi dấu đã xử lý và tác động cục bộ trong cùng transaction của mình.

```text
Order service:
    lưu cancellation + claim lượng + outbox TRY_STOP

WMS:
    phân xử dừng/xuất + lưu quyết định + outbox STOP_RESULT

Order/coordinator:
    áp dụng kết quả + outbox các tác vụ tiếp theo

Inventory / Payment:
    áp dụng hiệu ứng theo định danh riêng + lưu kết quả + outbox
```

Outbox giúp thông điệp không bị mất giữa commit và publish, nhưng message vẫn có thể được gửi lặp. Consumer phải chống trùng theo hiệu ứng nghiệp vụ, không chỉ kỳ vọng broker giao đúng một lần.

Inbox theo `event_id` hữu ích, nhưng nếu cùng hiệu ứng bị phát thành hai event khác ID, ràng buộc theo cancellation và loại hiệu ứng vẫn cần ngăn tác động trùng.

### 9.2. Không lùi trạng thái theo sự kiện cũ

Sự kiện có thể đến sai thứ tự. Một sự kiện `PACKED` đến muộn không được đưa phần hàng đã `CANCELLED` trở lại chuẩn bị giao.

Version hoặc sequence theo aggregate giúp nhận diện dữ liệu cũ và khoảng thiếu. Cách xử lý cần phù hợp loại sự kiện: event chứa delta có thể không được bỏ qua tùy tiện chỉ vì đã nhìn thấy version lớn hơn. Có thể cần đệm, nạp lại trạng thái từ nguồn có thẩm quyền hoặc phục hồi các event còn thiếu.

Kết quả hủy phải gắn với đúng allocation part, lần yêu cầu và revision hoặc quyết định có liên quan. Không nhận một xác nhận cũ rồi dùng nó cho phần hàng đã được tái phân bổ trong một nghiệp vụ mới.

### 9.3. Bù trừ không phải lúc nào cũng là thao tác ngược

Nếu mới claim lượng trong order nhưng kho từ chối hủy, có thể cần trả lượng đang chờ về nhóm phù hợp với trạng thái thật. Nếu kho đã chốt xuất, phần đó phải phản ánh trạng thái chốt xuất; không mù quáng đưa về `Q_open`.

Nếu đã xác nhận hủy, việc hoàn tiền thất bại tạo nghĩa vụ cần xử lý tiếp. Nếu hàng đã về khu phục hồi, không tự chuyển nó lại kiện cũ chỉ vì một message kế tiếp lỗi.

Mỗi bước bù trừ phải có tiền điều kiện, định danh hiệu ứng và audit riêng. Không chạy ngược một danh sách API một cách máy móc.

### 9.4. Lưu dữ liệu chống trùng đủ lâu

Thời gian retry, sự kiện trễ, khôi phục backup và xử lý thủ công có thể dài hơn thời gian tồn tại của một cache idempotency.

Key request có thể có chính sách lưu giữ riêng, nhưng định danh cancellation, trạng thái allocation và hiệu ứng đã áp dụng phải tồn tại đủ cho vòng đời nghiệp vụ. Không để xóa cache làm một cancellation cũ có thể nhả hàng hoặc hoàn tiền lại.

Cần có tác vụ đối soát cancellation treo, kết quả WMS chưa về, nghĩa vụ hoàn chưa xong và outbox lỗi. Các tác vụ này tiếp tục cùng định danh nghiệp vụ, không tạo ý định mới cho mỗi lần chạy.

## 10. Ví dụ hủy từng phần và kết quả cần báo

Dòng L1 có 10 đơn vị. Đã chốt xuất 4; còn 6 chưa chốt. Khách yêu cầu hủy 3 trong phần còn lại.

| Bước | Q_open | Q_cancel_pending | Q_cancelled | Q_dispatch_committed |
| --- | ---: | ---: | ---: | ---: |
| Trước yêu cầu | 6 | 0 | 0 | 4 |
| Đã claim 3 để yêu cầu hủy | 3 | 3 | 0 | 4 |
| Kho xác nhận hủy đúng 3 đã claim | 3 | 0 | 3 | 4 |
| 3 còn lại được chốt xuất hợp lệ | 0 | 0 | 3 | 7 |

Tổng mỗi hàng vẫn bằng 10. Ba đơn vị bị hủy phải có định danh phần allocation riêng với ba đơn vị tiếp tục xuất.

Sau cùng, đơn có thể có kết quả tổng hợp là đã hủy một phần và tiếp tục giao phần còn lại. Không gán cả đơn thành `CANCELLED` trong khi 7 đơn vị vẫn thuộc nhánh thực hiện.

Nếu chính sách giá của ví dụ ở phần thanh toán áp dụng, phần tiền hàng tương ứng 3 đơn vị là 270.000 đồng. Việc tạo refund phải dựa trên 3 đã xác nhận hủy, không dựa trên 6 từng còn mở hoặc 10 của toàn dòng.

### Trường hợp kho đã chốt xuất trước

Nếu kho đã chốt xuất đúng phần 3 đang được yêu cầu trước khi nhận lệnh dừng, nguồn có thẩm quyền có thể từ chối hủy phần đó. Dịch vụ điều phối phải cập nhật theo quyết định thật, giải quyết claim chờ và báo rõ lý do.

Khi chưa nhận được quyết định, response vẫn thể hiện pending. Không nhả reservation hoặc tạo refund cho phần yêu cầu chưa được xác nhận chỉ vì người dùng đã bấm hủy.

### Trường hợp chỉ một phần của yêu cầu hủy được chấp nhận

Nếu request yêu cầu nhiều phần allocation, hợp đồng API cần nêu rõ:

- **Tất cả hoặc không:** chỉ xác nhận khi toàn bộ phạm vi được bảo đảm dừng theo cơ chế hỗ trợ.
- **Chấp nhận từng phần:** trả kết quả riêng cho từng phần, lượng đã hủy và lượng bị từ chối.

Không hứa tính nguyên tử toàn bộ trên nhiều kho độc lập nếu hệ thống chưa có giao thức bảo đảm điều đó. Khi dừng tạm nhiều phần để phối hợp, phải xử lý rõ trường hợp một phần thất bại; việc mở lại những phần đã dừng cũng cần tuân thủ trạng thái thật và điều kiện nghiệp vụ.

## 11. Audit và khả năng giải trình

Một audit hữu ích phải nối được ý định ban đầu, quyết định của kho và tác động tồn kho, thanh toán.

| Nhóm dữ liệu | Nội dung gợi ý |
| --- | --- |
| Định danh | Tenant, order, fulfillment, allocation part, cancellation |
| Chủ thể | Người khởi tạo, service thực thi, người phê duyệt ngoại lệ |
| Phạm vi | Dòng đơn, lượng yêu cầu, lượng xác nhận và lượng từ chối |
| Căn cứ | Reason code, chính sách áp dụng, approval gắn đúng nội dung |
| Chuyển trạng thái | Trước/sau, version, bên đưa ra quyết định |
| Quan hệ nhân quả | Command/event ID, correlation ID, causation ID |
| Tác động | Movement ID, reservation effect, refund obligation và kết quả |
| Thời điểm | Lúc yêu cầu, lúc bên có thẩm quyền quyết định, lúc ghi nhận |

Phân biệt audit của **lần thử** với audit của **quyết định đã commit**. Một request bị từ chối không phải một cancellation thành công và không được xuất hiện như một hiệu ứng nhả hàng.

Không ghi token hoặc dữ liệu thanh toán nhạy cảm vào audit. Các trường ghi chú cần giới hạn độ dài và được xử lý như dữ liệu khi hiển thị. Quyền đọc lịch sử, export và liên kết payment cũng phải theo phạm vi tenant và đối tượng.

Các dấu hiệu cần theo dõi gồm:

- Cancellation đã `CONFIRMED` nhưng cùng phần allocation vẫn phát sinh chốt xuất.
- Lượng nhả vượt reservation còn lại hoặc một hiệu ứng xuất hiện nhiều lần.
- Nghĩa vụ hoàn vượt phần tiền được phép hoặc bị tạo lại với ID mới.
- Yêu cầu `PENDING`/`STOPPING` quá lâu, thiếu kết quả kho hoặc thiếu công việc phục hồi.
- Thao tác hỗ trợ thường xuyên dùng quyền ngoại lệ, sửa phạm vi sau phê duyệt hoặc chia nhỏ để né ngưỡng.
- Trạng thái giữa order, WMS, inventory và payment mâu thuẫn tại cùng mốc đối soát.

Không giải quyết cảnh báo bằng cách sửa lịch sử hoặc gán trạng thái cuối cho đẹp báo cáo. Giữ bằng chứng và thực hiện quy trình sửa sai có căn cứ.

## 12. Kiểm thử lạm dụng logic và điểm lỗi

Mỗi ca cần kiểm tra response, state machine, số lượng, reservation/movement, nghĩa vụ tiền và audit. Chỉ kiểm tra mã HTTP sẽ bỏ sót nhiều lỗi.

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Đổi order hoặc fulfillment sang đối tượng của người/tenant khác | Từ chối trong phạm vi quyền; không lộ kết quả qua replay |
| Trộn order hợp lệ với fulfillment hoặc dòng đơn không thuộc order đó | Từ chối quan hệ đối tượng không hợp lệ |
| Số lượng âm, 0, quá lớn hoặc lặp dòng trong request | Không vượt kiểm tra tổng lượng; không có hiệu ứng trái quy tắc |
| Cùng key và payload được gửi nhiều lần, kể cả đồng thời | Cùng cancellation, không claim hoặc tạo hiệu ứng lần hai |
| Cùng key nhưng sửa phần hàng hoặc số lượng | Xung đột nội dung, không áp dụng ý định mới |
| Gửi lại cùng cancellation/effect bằng event ID hoặc key khác | Không nhả hàng hoặc tạo refund obligation lần nữa |
| Hai yêu cầu hủy cùng tranh phần lượng còn lại | Tổng lượng claim và hủy không vượt phần được phép |
| Hủy cạnh tranh với chốt xuất cùng allocation part | Chỉ một quyết định cuối được chấp nhận ở nguồn có thẩm quyền |
| Tác vụ xuất dùng token cũ sau khi WMS đã chặn hủy | Bị chặn tại nơi thực thi, không chỉ tại API order |
| Kho đã chốt xuất nhưng projection order còn `PACKED` | Không xác nhận hủy dựa riêng vào projection cũ |
| Timeout trước khi kho trả kết quả | Giữ trạng thái chưa biết, retry cùng định danh và đối soát |
| Lỗi ghi outbox trong transaction tiếp nhận | Rollback cả request mới và claim tương ứng |
| Commit thành công rồi mất response | Retry tìm lại cancellation cũ |
| Consumer chết sau khi áp dụng hiệu ứng nhưng trước khi ack | Delivery lại không áp dụng thêm lần nữa |
| Webhook/sự kiện đến lặp hoặc sai thứ tự | Không lùi trạng thái, không tăng/giảm lượng sai hoặc hoàn trùng |
| Hàng ở khu đóng gói chưa đủ điều kiện bán lại | Không tăng available một cách thiếu căn cứ |
| Hoàn tiền timeout hoặc callback đến muộn | Không tạo obligation mới để thử lại một khoản chưa rõ kết quả |
| Sửa lượng sau phê duyệt hoặc dùng `force=true` trái quyền | Không vượt chính sách và không tái sử dụng approval sai nội dung |
| Refund lỗi sau khi hủy đã xác nhận | Fulfillment vẫn bị dừng; nghĩa vụ tiền được xử lý tiếp có kiểm soát |

Các ca race cần điều phối để hai tác vụ chạm cùng điểm kiểm tra; chạy tuần tự không chứng minh được tính an toàn đồng thời. Cần chèn lỗi trước commit, sau commit nhưng trước response và giữa các bước dịch vụ.

Cũng cần kiểm tra đường hợp lệ: hủy một phần, nhiều fulfillment, nhiều kho, đơn khách vãng lai và nhân viên hỗ trợ đúng quyền. Chống trùng quá rộng có thể làm người vận hành không thực hiện được những lần hủy từng phần hợp lệ.

## 13. Bài tập áp dụng

### Bài tập 1: Trạng thái hiển thị không phải bằng chứng dừng giao

Order service đang thấy F1 ở `PACKED`. Nó nhận request hủy, đổi F1 thành `CANCELLED` và gửi hai message nhả hàng, hoàn tiền. Cùng lúc đó, WMS đã chốt xuất kiện nhưng sự kiện chưa đến order service.

Hãy chỉ ra bất biến bị đe dọa và đề xuất cách đổi luồng.

**Gợi ý giải:** Cùng phần hàng có thể vừa được xuất vừa được hủy và hoàn tiền. Order service đã dùng bản sao trễ làm bằng chứng quyết định cuối. Cần lưu cancellation ở trạng thái pending, để WMS phân xử tại cổng xuất, rồi mới kích hoạt tác động phù hợp theo kết quả. Nếu chưa biết kết quả, tiếp tục đối soát; không coi timeout hoặc việc gửi message thành bằng chứng hủy thành công.

### Bài tập 2: Đếm lượng và chống hoàn trùng

Một dòng có `N = 8`, `Q_dispatch_committed = 3`, `Q_cancelled = 2`, `Q_cancel_pending = 1`. Một request mới xin hủy thêm 3. Đồng thời, consumer nhận lại sự kiện xác nhận hủy cho phần 2 đã hủy và định tạo một refund obligation mới.

Hãy xác định lượng chưa thuộc các nhóm trên và hai điểm cần chặn.

**Gợi ý giải:** `Q_open = 8 - 3 - 2 - 1 = 2`. Request mới xin 3 không được chấp nhận nguyên vẹn; tùy hợp đồng, từ chối hoặc trả đề nghị/phần được phép, không tự âm bộ đếm. Consumer phải tìm hiệu ứng/nghĩa vụ đã gắn với cancellation cũ và không tạo thêm khoản hoàn cho cùng phần 2. Đổi event ID hoặc retry không làm tăng lượng được hủy hay ngân sách được hoàn.

Thiết kế hủy fulfillment an toàn cần giữ được chuỗi căn cứ từ yêu cầu được cấp quyền, qua quyết định dừng tại nơi kiểm soát xuất hàng, đến các hiệu ứng tồn kho và tiền được áp dụng đúng một lần. Những phần chưa biết kết quả phải tiếp tục được thể hiện và xử lý như công việc chưa hoàn tất.
