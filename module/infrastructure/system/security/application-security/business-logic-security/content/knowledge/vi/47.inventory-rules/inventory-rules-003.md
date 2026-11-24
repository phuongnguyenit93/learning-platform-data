# Reserved quantity: bảo vệ số lượng tồn kho đang giữ

## Mục tiêu và phạm vi

Reserved quantity là số lượng hàng đã được hệ thống giữ cho một mục đích nghiệp vụ, khiến lượng đó không còn tự do cấp cho yêu cầu khác. Trong luồng mua hàng, giữ tồn thường giúp khách có thời gian thanh toán mà không bị một đơn khác lấy mất phần hàng vừa được chấp nhận.

Trong bảo mật logic nghiệp vụ, giữ tồn là việc cấp một quyền đối với tài nguyên hữu hạn. Sai quy tắc có thể làm bán vượt tồn, giải phóng hàng vẫn đang được giao, giữ hàng vô thời hạn hoặc chiếm dụng tồn của cửa hàng khác. Một request hợp lệ về cú pháp và có đăng nhập vẫn có thể gây ra những kết quả này.

Bài học tập trung vào các bất biến số lượng, máy trạng thái, quyền theo đối tượng, transaction, idempotency và kiểm thử tấn công logic. Mục tiêu là bảo đảm mỗi lần giữ, chuyển giao hoặc giải phóng hàng có nguồn rõ ràng và không làm tăng khả năng bán ngoài thực tế.

Sau bài này, bạn có thể:

- Phân biệt tồn thực tế, giữ tạm, phân bổ cho đơn và tồn khả dụng.
- Cấp quyền giữ bằng thao tác nguyên tử thay vì kiểm tra rồi ghi rời rạc.
- Kiểm soát thay đổi số lượng, hủy, hết hạn và giao hàng một phần.
- Chống phát lại request, callback và tác vụ kho.
- Xử lý thanh toán muộn, nhiều SKU hoặc nhiều kho mà không che giấu giới hạn nhất quán.
- Xây dựng kiểm thử đồng thời và đối soát các số lượng với nguồn nghiệp vụ.

## 1. Chốt ý nghĩa của từng số lượng

### 1.1. Một mô hình dùng xuyên suốt bài

Trong phạm vi một khóa tồn kho xác định, đặt:

- `O` — on-hand quantity: số lượng thực tế thuộc nhóm hàng đạt điều kiện bán, chưa xuất kho. Lượng này có thể đang được giữ hoặc đã phân bổ cho đơn.
- `R` — reserved quantity: số lượng đang giữ tạm, chưa chuyển sang phân bổ chắc chắn cho đơn.
- `A` — allocated quantity: số lượng đã phân bổ cho đơn, chưa xuất kho.
- `V` — available quantity: số lượng có thể cấp mới.

Với mô hình này:

~~~text
V = O - R - A
~~~

Một số hệ thống gọi toàn bộ R+A là reserved quantity. Khi đọc tài liệu hoặc thiết kế API, phải xác định đang dùng nghĩa nào. Nếu một trường reserved đã bao gồm allocated thì không được trừ allocated thêm lần nữa.

Bài này chọn R và A là hai tập không giao nhau để thấy rõ việc chuyển từ giữ tạm sang cam kết thực hiện đơn.

### 1.2. Khóa tồn kho quan trọng không kém con số

Một lượng hàng chỉ có nghĩa trong phạm vi của nó:

~~~text
InventoryKey =
    tenant
    SKU chuẩn
    kho
    nhóm trạng thái hàng
    chủ sở hữu hoặc lô hàng, nếu nghiệp vụ phân biệt
~~~

Một chiếc áo cùng SKU nhưng ở kho khác không tự đáp ứng cùng cam kết giao hàng. Hàng cách ly hoặc chờ kiểm tra không được cộng vào lượng đạt điều kiện bán. Hàng ký gửi của hai chủ sở hữu cũng có thể cần phạm vi riêng.

Client có thể gửi mong muốn nhận hàng tại một địa điểm. Máy chủ vẫn phải xác định kho được phép phục vụ và khóa tồn thực sự dùng để cấp quyền. Không tin một `warehouseId` bất kỳ trong body.

### 1.3. Giỏ hàng không tự là reservation

Một giỏ có thể chỉ biểu thị ý định mua. Hệ thống có thể chọn giữ hàng khi thêm vào giỏ hoặc chỉ khi bắt đầu checkout, nhưng phải thực hiện một hành động giữ thực sự tại mốc được chọn.

Nếu chưa có quyền giữ, thông báo “còn hàng” chỉ là kết quả đọc tại một thời điểm, không phải lời bảo đảm hàng đã thuộc về khách.

Ngược lại, nếu thêm vào giỏ lập tức giữ hàng, cần thời hạn, giới hạn và quy tắc giải phóng để người dùng không chiếm phần lớn kho chỉ bằng việc tạo nhiều giỏ.

## 2. Bất biến số lượng và các phép chuyển

### 2.1. Bất biến trong trạng thái vận hành bình thường

Với hàng đếm theo đơn vị nguyên:

~~~text
O >= 0
R >= 0
A >= 0
R + A <= O
V = O - R - A
~~~

Muốn giữ thêm q đơn vị:

~~~text
q là số nguyên dương hợp lệ
q <= V
~~~

Máy chủ cần giới hạn q theo phạm vi số của hệ thống và quy tắc mua hàng. Không cho số âm hoặc phép tràn số biến một lần giữ thành tăng tồn khả dụng.

Nếu hàng bán theo cân hoặc chiều dài, dùng một đơn vị cơ sở cùng thang đo rõ ràng. Không mặc định mọi hàng hóa đều dùng số nguyên chiếc, cũng không dùng số thực nhị phân tùy tiện cho các phép bảo toàn số lượng.

### 2.2. Các phép chuyển theo mô hình đã chọn

| Hành động | Thay đổi O | Thay đổi R | Thay đổi A |
| --- | ---: | ---: | ---: |
| Giữ q đơn vị mới | 0 | +q | 0 |
| Giải phóng q đơn vị giữ tạm | 0 | -q | 0 |
| Chuyển q từ giữ tạm sang phân bổ | 0 | -q | +q |
| Xuất q đơn vị đã phân bổ | -q | 0 | -q |
| Hủy phân bổ và xác nhận hàng có thể cấp lại | 0 | 0 | -q |
| Nhập lại q đơn vị đã đạt điều kiện bán | +q | 0 | 0 |

Chuyển R sang A không làm V tăng. Đây là điểm dễ sai: thanh toán thành công không có nghĩa hàng đã rời kho, nên không được chỉ giảm R rồi cho đơn khác lấy lượng đó.

Xuất kho làm cả O và A giảm tương ứng. Không giảm O thêm một lần khi nhận lại callback của cùng lần xuất.

Hủy phân bổ chỉ trả lại khả năng bán khi quá trình thực hiện đơn không còn có thể lấy hoặc xuất phần đó, và hàng thực sự trở lại trạng thái phù hợp. Nếu hàng đã được lấy ra và còn chờ hoàn vị trí, có thể tiếp tục giữ phân bổ hoặc dùng nhóm trạng thái riêng theo mô hình kho.

### 2.3. Một diễn tiến số lượng

Ban đầu có 10 đơn vị hàng đạt điều kiện bán:

| Bước | O | R | A | V |
| --- | ---: | ---: | ---: | ---: |
| Ban đầu | 10 | 0 | 0 | 10 |
| Giữ 3 đơn vị cho đơn O1 | 10 | 3 | 0 | 7 |
| Xác nhận phân bổ cả 3 đơn vị | 10 | 0 | 3 | 7 |
| Xuất 2 đơn vị | 8 | 0 | 1 | 7 |
| Hủy 1 đơn vị còn lại và xác nhận có thể cấp lại | 8 | 0 | 0 | 8 |

Nếu bước xác nhận phân bổ chỉ làm R từ 3 về 0 mà quên tăng A, hệ thống sẽ hiển thị V=10 dù ba đơn vị đã cam kết cho O1. Đơn tiếp theo có thể lấy phần hàng đó.

Nếu bước hủy cuối trả lại cả ba đơn vị ban đầu thay vì một đơn vị còn chưa xuất, hệ thống sẽ tạo thêm khả năng bán cho hàng đã đi khỏi kho.

### 2.4. Hỏng, mất hoặc sai lệch tồn thực tế

Bất biến R+A<=O mô tả trạng thái không thiếu hàng đã cam kết. Thực tế có thể phát hiện mất hàng hoặc hàng hỏng khiến lượng đạt điều kiện bán giảm xuống dưới tổng đã giữ và phân bổ.

Không che giấu sự cố bằng cách sửa R về 0 hoặc tiếp tục bán như bình thường. Cần phản ánh tồn thực tế, ghi nhận thiếu hụt, chặn cấp thêm trên phần thiếu và xử lý các đơn bị ảnh hưởng theo chính sách điều chuyển, bổ sung hoặc bù trừ.

Có thể theo dõi:

~~~text
shortage = max(R + A - O, 0)
~~~

Đây là một ngoại lệ cần vận hành xử lý, không phải lý do bỏ kiểm tra dung lượng khi cấp quyền mới. Giá trị V âm trong dữ liệu không được âm thầm kẹp về 0 rồi coi như mọi cam kết đã khớp; nếu giao diện hiển thị 0, vẫn phải giữ và điều tra thông tin thiếu hụt.

## 3. Dữ liệu phải gắn được phần giữ với nguồn nghiệp vụ

### 3.1. Các bản ghi và trách nhiệm

| Bản ghi | Nội dung quan trọng |
| --- | --- |
| Inventory balance | O, R, A, khóa tồn, trạng thái cho phép cấp mới và version |
| Reservation | Chủ thể, đơn, dòng hàng, thời hạn, trạng thái và định danh lần giữ |
| Reservation line | Khóa tồn cụ thể, số lượng và các phần còn giữ, đã phân bổ, đã kết thúc |
| Allocation | Phần hàng đã cam kết thực hiện cho đơn và liên kết tới reservation |
| Inventory ledger | Biến động có nguồn, loại, số lượng và khóa chống trùng |
| Shipment / return record | Chứng từ xuất hoặc nhận lại hàng và trạng thái thực tế |
| Idempotency mapping | Phạm vi request, fingerprint và operation đã tạo |
| Outbox / inbox | Ý định đã commit và sự kiện cần xử lý lại an toàn |

Không nhất thiết phải tạo đúng số bảng như trên. Điều quan trọng là không chỉ lưu một tổng R rồi mất khả năng trả lời số đó thuộc những đơn nào.

Reservation nên lưu ít nhất:

~~~text
reservation_id
tenant_id
owner_id hoặc chủ thể được phép
order_id, order_line_id
order_content_version
inventory_key
accepted_quantity
remaining_held_quantity
remaining_allocated_quantity
expires_at
status
generation / version
policy_snapshot
~~~

Dữ liệu do máy chủ tạo và kiểm tra. Client không được tự chọn chủ sở hữu, generation hoặc trạng thái “đã phân bổ”.

### 3.2. Định danh ổn định và quyền theo đối tượng

Khóa idempotency nhận diện một request gửi lại. Khóa nghiệp vụ nhận diện phần quyền giữ cho đơn hoặc dòng hàng. Hai loại khóa phải được tách biệt.

Nếu mỗi dòng hàng chỉ có một nhóm quyền giữ đang có hiệu lực, cần ràng buộc phù hợp với dòng đó. Khách đổi idempotency key không được tạo thêm quyền ngoài số lượng đã chấp nhận cho cùng ý định.

Phiên bản nội dung dùng để phát hiện đơn đã bị sửa. Không để mỗi lần sửa một thuộc tính không liên quan tự tạo “ý định mới” nhằm vượt giới hạn giữ hàng.

Khi một quyền hết hạn và được phép thử lại, máy chủ tạo lần giữ mới theo quy trình có kiểm soát. Lần mới có định danh hoặc generation mới, kiểm tra tồn và thời gian lại. Không hồi sinh bản ghi cũ bằng cách đổi trạng thái mà bỏ qua điều kiện.

Mọi thao tác đọc, tăng, giảm, giải phóng hoặc chuyển phân bổ cần kiểm tra tenant, chủ thể và đơn liên quan. Biết một reservation ID không phải bằng chứng có quyền thao tác.

## 4. Kiểm tra đầu vào và cấp quyền giữ nguyên tử

### 4.1. Những trường không có thẩm quyền từ client

Một payload có thể chứa mong muốn mua hàng:

~~~json
{
  "orderLineId": "L1",
  "sku": "SKU-01",
  "quantity": 3,
  "preferredWarehouseId": "W1"
}
~~~

Máy chủ phải kiểm tra dòng thuộc đúng đơn, chuẩn hóa SKU, xác định số lượng hợp lệ và chọn kho được phép phục vụ.

Không dùng các trường do client tự gửi như `availableQuantity`, `reservedQuantity`, `ownerId`, `isPaid` hoặc `expiresAt` để chứng minh quyền giữ. Trường số lượng mong muốn cũng phải được đối chiếu với nội dung đơn, giới hạn mua và đơn vị tính.

Nếu một sản phẩm được bán theo thùng 12 đơn vị, cần quy đổi ở phía máy chủ theo cấu hình sản phẩm. Không để endpoint đặt hàng hiểu là thùng còn endpoint giữ tồn hiểu là chiếc.

Với bộ sản phẩm, các thành phần cần giữ phải được suy ra từ cấu hình bộ đã chấp nhận. Giữ một đơn vị bộ trên một SKU ảo không đủ nếu kho thực tế xuất nhiều SKU thành phần.

### 4.2. Lỗi kiểm tra rồi ghi

Ban đầu O=1, R=0, A=0. Hai khách cùng thực hiện:

~~~text
A đọc V=1, kết luận đủ
B đọc V=1, kết luận đủ
A giữ 1
B giữ 1
~~~

Nếu các thao tác không được bảo vệ chung, R có thể thành 2 trong khi O chỉ là 1.

Một lỗi khác còn khó thấy hơn: cả hai tiến trình đọc R=0 rồi đều ghi R=1. Tổng R trông có vẻ đúng, nhưng đã tồn tại hai quyền giữ, mỗi quyền một đơn vị. Đây là mất cập nhật, làm số tổng hợp che giấu cam kết thực tế.

Bởi vậy cần kiểm tra cả bất biến số tổng và quan hệ với các reservation nguồn.

### 4.3. Cập nhật có điều kiện

Một mẫu SQL minh họa:

~~~sql
UPDATE inventory_balance
SET reserved_qty = reserved_qty + :q,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND sku_id = :sku_id
  AND warehouse_id = :warehouse_id
  AND stock_bucket = :stock_bucket
  AND stock_status = 'OPEN'
  AND :q > 0
  AND :q <= on_hand_qty - reserved_qty - allocated_qty;
~~~

Mẫu này giả định khóa tồn đã đầy đủ cho mô hình, các số lượng có kiểu và phạm vi phù hợp. Nếu còn chiều chủ sở hữu hoặc lô, điều kiện khóa phải bao gồm chúng.

Chỉ coi giữ thành công khi đúng một hàng được cập nhật. Cập nhật số tổng và tạo reservation phải nằm trong cùng transaction. Nếu tạo reservation thất bại vì trùng khóa nghiệp vụ thì phần tăng R cũng rollback.

Có thể dùng khóa hàng rồi kiểm tra và cập nhật thay câu lệnh trên. Điều bắt buộc là không có khoảng trống cho yêu cầu khác lấy phần tồn đã dùng trong quyết định.

### 4.4. Số tổng không được tách khỏi nguồn

Luồng sau dễ để lại tồn bị khóa:

~~~text
Transaction 1: tăng R, commit
Transaction 2: tạo reservation, thất bại
~~~

Luồng ngược lại cũng sai: reservation tồn tại nhưng tăng R thất bại, khiến hàng vẫn có thể cấp cho người khác.

Trong cùng một transaction cục bộ cần ghi:

~~~text
thay đổi balance
reservation và các dòng
ledger có nguồn
idempotency mapping
outbox, nếu có công việc sau commit
~~~

Không gọi cổng thanh toán hoặc chờ phản hồi kho trong lúc giữ khóa dài. Ghi ý định trước rồi xử lý bên ngoài với định danh ổn định.

## 5. Thay đổi số lượng và giữ nhiều dòng

### 5.1. Phân biệt số lượng đích với lượng tăng thêm

Giả sử reservation đang giữ 5 đơn vị. Khách muốn đổi thành 8:

~~~text
current_held = 5
target_held = 8
delta = target_held - current_held = 3
~~~

Chỉ kiểm tra và tăng R thêm 3 đơn vị, không giữ thêm 8. Ngược lại, không nhận một delta do client khai báo rồi bỏ qua số lượng đích đã được chấp nhận trên đơn.

Việc đọc số hiện tại, kiểm tra phiên bản, tính delta và cập nhật cần được bảo vệ chung. Hai request cùng đọc 5 rồi đổi lần lượt thành 8 và 7 không được cùng dựa trên phiên bản cũ.

Một quy tắc an toàn:

~~~text
khóa quyền giữ và dòng hàng
kiểm tra expected_version
xác minh thay đổi được phép
tính delta phía máy chủ

nếu delta > 0:
    kiểm tra và giữ thêm dung lượng
nếu delta < 0:
    chỉ giải phóng phần còn đang giữ và được phép giảm
nếu delta = 0:
    không tạo biến động mới

ghi số lượng đích, version mới và ledger
~~~

Yêu cầu giữ mới cần số lượng dương. Đặt số lượng đích về 0 có thể là thao tác hủy hợp lệ nếu API định nghĩa như vậy; nó vẫn phải qua quyền, trạng thái và cơ chế chống lặp, không phải lối tắt để trừ tùy ý.

### 5.2. Không giảm phần đã đi sang quy trình khác

Một dòng có ba đơn vị ban đầu nhưng đã xuất hai không còn ba đơn vị để giải phóng. Máy chủ phải tính từ phần còn lại, không từ số lượng đặt mua gốc.

Nếu có phân bổ, lấy hàng và xuất một phần, có thể theo dõi các phần không giao nhau:

~~~text
held_remaining
allocated_remaining
shipped_quantity
released_quantity
~~~

Với một phần nguồn cố định, chưa có điều chỉnh thêm:

~~~text
accepted_quantity =
    held_remaining
  + allocated_remaining
  + shipped_quantity
  + released_quantity
~~~

Tăng số lượng sau đó cần một điều chỉnh hoặc phần nguồn mới có thể truy vết. Không sửa số gốc để làm mất lịch sử đã xuất.

Một cờ `released = true` cho cả dòng không đủ mô tả nhiều lần xử lý một phần. Ledger cũng phải cho phép nhiều hiệu ứng hợp lệ theo phần nguồn, nhưng giới hạn tổng không vượt số được phép.

### 5.3. Nhiều SKU trong cùng kho dữ liệu

Nếu đơn chỉ được chấp nhận khi đủ mọi thành phần, cần giữ tất cả hoặc không giữ phần nào:

~~~text
begin transaction
    khóa các balance theo thứ tự ổn định của InventoryKey
    kiểm tra từng lượng cần giữ
    tăng R cho các dòng
    tạo toàn bộ reservation lines và ledger
commit
~~~

Nếu một SKU không đủ thì rollback phần đã tăng ở SKU khác. Không đánh dấu toàn bộ đơn “đã giữ hàng” khi mới thành công một nửa.

Thứ tự khóa thống nhất giúp giảm deadlock. Nếu transaction phải thử lại, giữ định danh ý định và kiểm tra lại dữ liệu hiện hành, không tạo thêm quyền từ một lần thử đã commit.

### 5.4. Nhiều kho hoặc dịch vụ

Một transaction của dịch vụ đặt hàng không tự bảo vệ nguyên tử các kho dữ liệu độc lập.

Có thể cần một nhóm reservation đang điều phối:

~~~text
PENDING_GROUP → CONFIRMED_GROUP
PENDING_GROUP → RELEASING → RELEASED_GROUP
~~~

Chỉ xác nhận nhóm khi đủ các phần bắt buộc. Nếu thất bại giữa chừng, giải phóng các phần đã giữ bằng thao tác chống trùng; các phần đang chưa rõ kết quả phải được đối soát.

Nếu doanh nghiệp cho phép giao một phần, trạng thái và trải nghiệm phải thể hiện rõ phần đã chấp nhận. Không dùng nhãn “đủ hàng” cho cả đơn để che một chiến lược chấp nhận từng phần.

Điều chuyển kho cũng cần phân biệt thay nguồn phục vụ với di chuyển vật lý. Không cộng O ở kho đích chỉ vì đã phát lệnh chuyển; hàng phải qua các trạng thái xuất, đang vận chuyển và nhận theo quy trình thực tế.

## 6. Vòng đời, hết hạn và phản hồi muộn

### 6.1. Máy trạng thái cơ bản

~~~mermaid
stateDiagram-v2
    [*] --> HELD: Giữ tồn thành công
    HELD --> ALLOCATED: Đủ điều kiện chốt đơn
    HELD --> RELEASED: Hủy trước cam kết
    HELD --> EXPIRED: Hết hạn theo chính sách
    ALLOCATED --> SHIPPED: Xuất hàng
    ALLOCATED --> CANCEL_PENDING: Yêu cầu hủy phân bổ
    CANCEL_PENDING --> RELEASED: Xác nhận có thể cấp lại hàng
~~~

Sơ đồ mô tả một phần hàng được xử lý trọn vẹn. Với xử lý một phần, cần số lượng còn lại hoặc các phần nguồn riêng; một trạng thái tổng không thay thế được chúng.

Trong HELD, phần hàng đóng góp vào R. Trong ALLOCATED và CANCEL_PENDING, nó vẫn chiếm phần cam kết phù hợp, ở đây là A. Không trả lại khả năng bán chỉ vì yêu cầu hủy đã được gửi.

Sau SHIPPED, hoàn tiền không tự làm O tăng. Chỉ nhập lại hàng khi có sự kiện nhận thực tế và hàng đạt điều kiện bán. Hàng trả cần kiểm tra phải vào nhóm riêng, chưa được cấp mới.

### 6.2. Hạn giữ và nguồn thời gian

Hạn được máy chủ tạo từ chính sách và nguồn thời gian tin cậy. Client không được gửi một hạn tùy ý hoặc gia hạn bằng cách gọi lại API đọc.

Mỗi lần xử lý lại cùng request trả cùng quyền hiện có, không đặt lại `expires_at = now + TTL`. Nếu cho gia hạn, cần một thao tác riêng có quyền, giới hạn tổng thời gian và số lần, cùng điều kiện trạng thái phù hợp.

Scheduler hết hạn chạy chậm có thể làm một phần tồn bị giữ lâu hơn dự kiến. Trong mô hình lưu R tổng hợp, không chỉ bỏ qua reservation hết hạn khi hiển thị rồi cho phép cấp thêm mà chưa kết chuyển đúng phần giữ. Có thể giải phóng theo lịch hoặc khi truy cập, nhưng chuyển trạng thái và cập nhật R vẫn phải nguyên tử.

### 6.3. Hai hợp đồng cho thanh toán chưa rõ kết quả

**Giữ cam kết trong khi thanh toán đang được xác minh:** phần hàng tiếp tục chiếm R hoặc chuyển sang trạng thái giữ riêng. Chỉ giải phóng khi đủ điều kiện chắc chắn theo quy trình. Hợp đồng này cần cơ chế xử lý các giao dịch treo, không kéo dài vô hạn mà không giám sát.

**Hạn cứng cho quyền giữ:** có thể hết hạn và cấp lại hàng nếu mọi đường phân bổ, lấy hàng và xuất hàng đều buộc kiểm tra quyền còn hiệu lực. Thanh toán thành công muộn không hồi sinh quyền cũ; hệ thống phải giữ mới nếu chính sách cho phép và còn tồn, hoặc xử lý hoàn tiền/bù trừ.

Không có một lựa chọn bắt buộc cho mọi hệ thống. Điều nguy hiểm là giải phóng theo hợp đồng hạn cứng nhưng callback lại phân bổ theo hợp đồng bảo đảm hàng, khiến cùng một đơn vị được cam kết hai lần.

### 6.4. Tín hiệu kho chưa rõ khác với cờ hủy đơn

Nếu lệnh lấy hàng hoặc xuất hàng đã gửi mà chưa biết kết quả, không coi việc đặt `order.cancelled = true` là bằng chứng hàng còn có thể bán.

Giữ phần cam kết hoặc chuyển vào trạng thái chờ giải quyết cho tới khi kho xác nhận phù hợp. Nếu hàng thực sự đã xuất, phải ghi nhận thực tế và xử lý ngoại lệ; không bỏ qua chứng từ chỉ để giữ nguyên số tồn đẹp trong cơ sở dữ liệu.

## 7. Luồng xử lý từ API đến kho

### 7.1. Giữ tồn trong một transaction

Giả mã dưới đây giả định các balance liên quan nằm trong một ranh giới transaction cục bộ. Luồng nhiều dịch vụ cần cơ chế điều phối riêng như phần trước.

~~~text
reserveInventory(actor, orderId, command, idempotencyKey):
    validateAllowedFieldsAndQuantityShape(command)
    fingerprint = canonicalRequestFingerprint(orderId, command)

    begin transaction
        order = lockOrderAndRelevantLines(orderId)
        authorizeOrderAccess(actor, order)

        previous = findIdempotency(
            tenant = order.tenantId,
            actor = actor.id,
            action = "RESERVE_INVENTORY",
            key = idempotencyKey
        )

        if previous exists:
            requireSameFingerprint(previous, fingerprint)
            authorizeReadOfOperation(actor, previous)
            commit
            return currentResult(previous)

        claim = findClaimForServerControlledIntent(order, command)
        if claim exists:
            requireSameBusinessIntentContent(claim, command)
            saveIdempotencyMapping(idempotencyKey, fingerprint, claim)
            commit
            return currentResult(claim)

        requireOrderCanReserve(order)
        requireExpectedOrderVersion(command, order)

        requirements = deriveInventoryRequirementsOnServer(order, command)
        resources = lockBalancesAndHoldLimitResources(requirements, actor)

        t = authoritativeNow()
        requireAllowedReservationPolicy(order, actor, t)
        requireAllQuantitiesPositiveAndBounded(requirements)
        requireInventoryScopesAuthorized(order, requirements)
        requireActiveHoldLimitsSatisfied(actor, resources, requirements)
        requireAllBalancesHaveCapacity(resources, requirements)

        reservation = insertReservation(
            owner = actor,
            order = order,
            requirements = requirements,
            acceptedAt = t,
            expiresAt = calculateBoundedExpiry(t, order.policy),
            generation = nextServerControlledGeneration(order),
            status = HELD
        )

        incrementReservedBalances(requirements)
        insertReservationLines(reservation, requirements)
        appendInventoryLedger("RESERVE", reservation, requirements)
        saveIdempotencyMapping(idempotencyKey, fingerprint, reservation)
        insertOutbox("INVENTORY_RESERVED", reservation.id)
        appendAudit("RESERVATION_ACCEPTED", actor, reservation)

    commit

    return reservation
~~~

Các ràng buộc dữ liệu vẫn cần tồn tại dù mã ứng dụng đã đọc kiểm tra:

- Khóa tồn là duy nhất theo đầy đủ các chiều nghiệp vụ.
- Claim hoặc vị trí quyền giữ không tạo hai kết quả trái quy tắc.
- Idempotency mapping không trỏ cùng khóa vào hai operation khác nhau.
- Balance và các phần số lượng không âm trong các chuyển đổi hợp lệ.
- Nếu dùng kiểm tra version, thao tác ghi xác nhận version chưa đổi.
- Mọi lỗi sau khi tăng R nhưng trước commit làm rollback phần tăng đó.

Fingerprint dựa trên nội dung yêu cầu đã chuẩn hóa, không dựa trên số tồn biến động mỗi giây. Nếu cùng một request được gửi lại sau khi tồn thay đổi, nó vẫn phải nhận diện được ý định ban đầu.

Nếu khách muốn sửa số lượng hoặc thay cách giao hàng sau khi đã có claim, đi qua thao tác điều chỉnh phù hợp. Không tự biến mọi request mới thành thêm một reservation độc lập.

### 7.2. Chuyển sang phân bổ

~~~text
begin transaction
    khóa đơn, reservation và các balance theo kỷ luật thống nhất
    xác minh chủ thể hoặc sự kiện được phép chốt đơn
    đối chiếu nội dung đơn, trạng thái thanh toán/phê duyệt và generation

    nếu thao tác nghiệp vụ này đã có kết quả:
        trả kết quả cũ, không ghi thêm

    yêu cầu phần quyền đang ở trạng thái cho phép
    kiểm tra hạn và hợp đồng thanh toán muộn
    xác định q từ phần còn đang giữ được chấp nhận

    giảm R đi q và tăng A thêm q trên đúng khóa tồn nguồn
    chuyển phần nguồn sang đã phân bổ
    ghi ledger, kết quả thao tác và outbox cho bước kho
commit
~~~

Phê duyệt hoặc thanh toán phải là bằng chứng phía hệ thống, gắn với đúng đơn và phiên bản cần chốt. Một cờ `paid=true` hoặc `approved=true` trong body không có giá trị chứng minh.

Với xử lý một phần, mỗi lần chuyển có định danh riêng và tổng chuyển không vượt lượng còn giữ. Không dùng một ràng buộc “mỗi reservation chỉ có một loại movement” để vô tình cấm các lần chuyển một phần hợp lệ; cũng không bỏ giới hạn tổng chỉ vì mỗi movement có ID khác.

### 7.3. Tác vụ kho phải mang đúng nguồn quyền

Một lệnh lấy hoặc xuất hàng nên liên kết tới allocation cụ thể, số lượng, đơn và phiên bản hoặc generation phù hợp. Kho không thực hiện chỉ dựa trên một order ID mà bỏ qua phần phân bổ hiện hành.

Nếu đơn được hủy rồi giữ lại với generation mới, lệnh của generation cũ không được lấy hàng từ quyền mới. Điều này đặc biệt quan trọng khi message có thể đến trễ hoặc bị phát lại.

Một token thế hệ chỉ hữu ích khi bên nhận thực sự kiểm tra nó với trạng thái có thẩm quyền hoặc một cơ chế thứ tự được bảo đảm. Thêm trường `generation` vào JSON nhưng không từ chối lệnh lỗi thời không tạo bảo vệ.

Nếu kho không hỗ trợ chặn hoặc hủy lệnh cũ đủ mạnh, phía đặt hàng phải tiếp tục xem phần hàng đó đang cam kết cho đến khi có xác nhận an toàn. Việc phát lệnh hủy chưa đồng nghĩa lệnh lấy hàng trước đó chắc chắn không còn thực thi.

### 7.4. Outbox và xử lý lại

Transaction ghi outbox giúp ý định đã commit không bị bỏ sót chỉ vì tiến trình dừng trước khi gửi message.

Tuy nhiên, outbox có thể được gửi lại. Bên nhận cần dedupe theo thao tác nghiệp vụ và kiểm tra số lượng còn được phép. Nếu worker dừng sau khi kho đã nhận lệnh nhưng trước khi lưu phản hồi, lần gửi lại phải mang cùng định danh, không tạo một lệnh xuất mới độc lập.

Đừng tuyên bố “đúng một lần” chỉ vì message đã có ID. Cần phân biệt một message được nhận nhiều lần với hai message khác nhau cùng yêu cầu thực hiện một hiệu ứng trên cùng phần hàng.

## 8. Idempotency và bảo toàn phần nguồn

### 8.1. Hai tầng chống lặp

| Tầng | Vai trò |
| --- | --- |
| Request idempotency | Nhận diện cùng yêu cầu từ client hoặc kênh gọi |
| Business uniqueness và giới hạn số lượng | Ngăn các yêu cầu khác nhau lấy hoặc trả lại cùng phần hàng ngoài quy tắc |

Quy ước thường dùng:

| Lần gọi sau | Kết quả |
| --- | --- |
| Cùng khóa, cùng nội dung | Cùng operation và trạng thái hiện tại |
| Cùng khóa, nội dung khác | Từ chối xung đột |
| Khóa mới, cùng ý định đã có quyền | Trả kết quả đã gắn hoặc từ chối; không giữ thêm |
| Cùng operation nhưng khác người không có quyền | Không được đọc hoặc thực hiện |
| Quyền cũ đã hết hạn | Không hồi sinh chỉ vì phát lại request |
| Quyền cũ đã xuất hàng | Không xuất hoặc giải phóng lại |

Sau khi bộ nhớ idempotency hết thời gian lưu, ràng buộc nghiệp vụ và lịch sử phần nguồn vẫn phải bảo vệ vòng đời còn liên quan. Không dùng TTL của cache request làm tuổi thọ duy nhất của cơ chế chống xuất trùng.

### 8.2. Giải phóng từ phần còn lại, không từ số lượng client gửi

Một yêu cầu hủy có thể chỉ cần định danh quyền giữ và lý do. Máy chủ xác định phần được giải phóng từ trạng thái hiện hành.

Nếu API hỗ trợ hủy một phần, lượng yêu cầu phải nằm trong phần được hủy và chưa kết thúc. Phải khóa hoặc cập nhật có điều kiện lượng còn lại.

~~~text
q_release <= releasable_remaining
q_ship <= allocated_remaining
q_allocate <= held_remaining
~~~

Một ID thao tác mới không làm các bất đẳng thức này trở nên tùy chọn. Đây là hàng rào khi người gọi cố ý đổi khóa để phát sinh hiệu ứng mới.

Ledger có thể dùng khóa chống trùng như định danh lệnh nguồn, dòng nguồn và loại movement. Với nhiều lần hợp lệ, mỗi lần có nguồn riêng; tổng vẫn được kiểm tra trên phần chưa sử dụng.

### 8.3. Ràng buộc quyền trước khi trả kết quả cũ

Nếu idempotency key bị đoán hoặc lọt từ log, người khác không được dùng nó để xem nội dung đơn hay giải phóng hàng. Kiểm tra quyền trên operation vẫn cần thực hiện trước khi trả dữ liệu.

Tương tự, nhân viên kho có thể được xác nhận xuất trong phạm vi kho của mình nhưng không được sửa R của kho khác hoặc đổi chủ thể reservation. Các chức năng điều chỉnh cần quyền riêng và nguồn điều chỉnh có thể truy vết.

## 9. Những chuỗi lạm dụng cần chặn

### 9.1. Số lượng âm hoặc đơn vị tính không nhất quán

**Chuỗi thao tác:** gửi lượng âm để phép cộng làm R giảm, hoặc đặt một thùng nhưng chỉ giữ một chiếc.

**Điểm sai:** tin số lượng đã qua validation hình thức hoặc dùng hai cách quy đổi khác nhau.

**Chốt chặn:** kiểm tra miền giá trị, đơn vị, giới hạn số và suy ra nhu cầu tồn từ cấu hình sản phẩm phía máy chủ.

### 9.2. Giữ hàng vô thời hạn bằng retry

**Chuỗi thao tác:** liên tục gọi lại endpoint giữ, đọc hoặc cập nhật nhỏ để đẩy expires_at ra xa.

**Điểm sai:** mỗi request được coi như một lần cấp thời hạn mới mà không kiểm tra tổng thời gian giữ.

**Chốt chặn:** retry đọc lại kết quả; gia hạn là nghiệp vụ riêng, có giới hạn và không được dùng một thay đổi nội dung giả để lách.

### 9.3. Giải phóng lặp để tạo tồn ảo

**Chuỗi thao tác:** gọi hủy hai lần với hai khóa khác nhau, hoặc phát lại callback hủy sau khi một phần đã giao.

**Điểm sai:** trừ R hoặc A theo lượng gốc của đơn thay vì phần còn được phép, thiếu guard trạng thái.

**Chốt chặn:** giải phóng nguyên tử theo phần nguồn, chống trùng thao tác và kiểm tra tổng kết thúc không vượt lượng đã nhận.

### 9.4. Sửa kho, tenant hoặc chủ sở hữu

**Chuỗi thao tác:** thay warehouseId hoặc reservationId để lấy hàng của cửa hàng khác, hoặc giải phóng quyền của người khác.

**Điểm sai:** chỉ kiểm tra có đăng nhập hoặc đối tượng tồn tại.

**Chốt chặn:** kiểm tra quan hệ đối tượng và phạm vi phục vụ, suy ra khóa tồn có thẩm quyền; áp dụng cùng kiểm tra trên API khách, quản trị và tác vụ nội bộ.

### 9.5. Tạo nhiều giỏ để làm cạn tồn

**Chuỗi thao tác:** mở nhiều reservation lớn nhưng không có ý định hoàn tất.

**Điểm sai:** cấp quyền giữ không ràng buộc với đơn và không giới hạn lượng đang giữ.

**Chốt chặn:** giới hạn phù hợp theo chủ thể hoặc phạm vi kinh doanh, thời hạn hữu hạn và theo dõi phần giữ treo. Nếu giới hạn theo tài khoản thì nó chỉ bảo vệ theo tài khoản, không tự bảo đảm mỗi người thật chỉ có một quyền.

### 9.6. Cho callback cũ tiếp tục giao hàng sau hết hạn

**Chuỗi thao tác:** quyền cũ hết hạn, hàng đã cấp cho khách khác, callback thành công muộn lại khiến đơn cũ được xuất.

**Điểm sai:** dùng trạng thái thanh toán làm điều kiện duy nhất cho xuất hàng.

**Chốt chặn:** mọi đường phân bổ và thực hiện đơn kiểm tra quyền tồn hiện hành; thanh toán muộn đi theo chính sách bù trừ hoặc giữ mới, không tự khôi phục phần cũ.

### 9.7. Dùng endpoint phụ để bỏ qua giới hạn

**Chuỗi thao tác:** checkout chính có kiểm tra tồn nhưng API sửa đơn, nhập đơn hàng loạt hoặc công cụ nhân viên ghi thẳng R/A.

**Điểm sai:** bất biến chỉ tồn tại trong một controller.

**Chốt chặn:** đặt quy tắc ở ranh giới nghiệp vụ và lưu trữ chung, yêu cầu mọi đường ghi có nguồn và qua cùng cơ chế phân xử.

Nếu hệ thống cho bán đặt trước hoặc chấp nhận nợ hàng, cần mô hình và hạn mức riêng. Một trường `allowNegativeStock` do client gửi không được âm thầm vô hiệu hóa các quy tắc của tồn có sẵn.

## 10. Kiểm thử tình huống tấn công logic

### 10.1. Ma trận kiểm thử

| Tình huống | Kết quả cần quan sát |
| --- | --- |
| Hai khách tranh một đơn vị cuối | Chỉ một quyền giữ mới có hiệu lực; nguồn và tổng R khớp nhau |
| Hai request đọc cùng R cũ rồi cập nhật | Không mất cập nhật, không che giấu hai quyền bằng một tổng nhỏ hơn |
| Giữ mới với q bằng 0, âm hoặc ngoài phạm vi số | Không tạo quyền hoặc làm tăng khả năng bán |
| Đơn vị thùng/chiếc hoặc đơn vị đo khác nhau | Máy chủ quy đổi đúng nhu cầu tồn theo cấu hình đã chấp nhận |
| Bộ sản phẩm thiếu một thành phần | Không xác nhận đủ bộ khi các thành phần bắt buộc chưa được giữ |
| Balance chưa tồn tại | Không suy ra O từ client; từ chối hoặc xử lý theo quy tắc dữ liệu có thẩm quyền |
| Client sửa availableQuantity hoặc reservedQuantity | Không thay đổi quyết định có thẩm quyền |
| Dòng hàng thuộc đơn khác | Bị từ chối; không đổi tồn hoặc reservation |
| Kho hoặc tenant ngoài phạm vi | Không được giữ, giải phóng hoặc xuất |
| Cùng khóa, cùng request | Cùng operation, không tăng R lần hai |
| Cùng khóa, đổi số lượng hoặc đơn | Xung đột, không chuyển quyền sang nội dung khác |
| Khóa mới, cùng ý định đã có quyền | Không tạo thêm phần giữ |
| Retry hoặc đọc liên tục | Không đẩy expires_at ra xa ngoài nghiệp vụ gia hạn |
| Đổi từ 5 lên 8 đơn vị | Chỉ giữ thêm 3, tổng khớp số lượng đích |
| Hai lần sửa đồng thời dựa trên cùng version | Không cùng ghi từ trạng thái cũ; bên xung đột phải xử lý lại |
| Giảm số lượng sau khi đã xuất một phần | Chỉ phần còn được phép mới được giải phóng |
| Nhiều SKU, một SKU không đủ | Rollback mọi phần giữ trong transaction nếu chính sách yêu cầu đủ tất cả |
| Giữ nhiều dịch vụ thất bại giữa chừng | Không xác nhận nhóm đầy đủ; các phần được giải quyết có truy vết |
| Chuyển giữ sang phân bổ | R giảm, A tăng tương ứng, V không tăng |
| Callback phân bổ phát lại | Không chuyển cùng phần hai lần |
| Worker hết hạn và chốt đơn chạy đồng thời | Chỉ một kết quả hợp lệ, không vừa cấp lại vừa phân bổ phần cũ |
| Thanh toán muộn sau hết hạn cứng | Không hồi sinh quyền; đi theo quy trình được định nghĩa |
| Thanh toán chưa rõ theo hợp đồng bảo đảm hàng | Phần cam kết không bị giải phóng chỉ vì timeout |
| Hủy phân bổ khi lệnh kho chưa rõ kết quả | Không cấp lại hàng chỉ vì đã gửi lệnh hủy |
| Lệnh kho của generation cũ đến trễ | Không dùng quyền mới để thực hiện lệnh cũ |
| Xuất một phần rồi hủy phần còn lại | Chỉ giải phóng lượng chưa xuất và đã được kho cho phép cấp lại |
| Chứng từ xuất được gửi lại | O và A không bị trừ thêm |
| Yêu cầu trả hoặc hoàn tiền nhưng hàng chưa về | O không tăng chỉ vì yêu cầu được tạo |
| Nhận lại hàng còn chờ kiểm tra | Chưa cộng vào nhóm hàng có thể cấp mới |
| Cache còn báo đủ hàng | Giữ mới vẫn kiểm tra dung lượng tại nguồn có thẩm quyền |
| Idempotency cache hết hạn lưu | Khóa nghiệp vụ và phần nguồn vẫn ngăn giữ hoặc xuất trùng |
| Phát hiện hỏng hàng làm thiếu so với cam kết | Ghi nhận thiếu hụt, chặn cấp thêm theo chính sách; không xóa nghĩa vụ cũ |
| Công cụ quản trị sửa số tổng ngoài quy trình | Bị ngăn hoặc phát hiện; mọi điều chỉnh hợp lệ có nguồn và audit |

### 10.2. Tạo bài kiểm thử đồng thời có ý nghĩa

Đặt O=1, R=0, A=0. Hai tiến trình dùng hai đơn và hai idempotency key khác nhau, cùng yêu cầu giữ một đơn vị.

Điều phối để chúng thực sự cạnh tranh tại thao tác cấp quyền, rồi đọc kết quả đã commit:

~~~text
Số quyền mới có hiệu lực = 1
R = 1
A = 0
O = 1
V = 0
Không có reservation thành công mà chưa được tính vào R
Không có phần tăng R thiếu nguồn reservation
~~~

Tiếp theo kiểm thử cùng một quyền giữ với hai tiến trình: một tiến trình hết hạn, tiến trình còn lại phân bổ. Kết quả phải tương ứng một nhánh hợp lệ, không phải chỉ một mã HTTP mà số lượng đã bị cập nhật bởi cả hai nhánh.

Không chỉ thêm thời gian ngủ ngẫu nhiên rồi kỳ vọng race xuất hiện. Cần kiểm soát điểm đồng bộ hoặc điều phối được cạnh tranh và xác nhận các bất biến sau xử lý.

### 10.3. Kiểm thử theo chuỗi trạng thái

Một chuỗi có giá trị:

~~~text
giữ → tăng số lượng → bắt đầu thanh toán → mất phản hồi
→ retry → nhận kết quả → phân bổ → xuất một phần
→ yêu cầu hủy → nhận callback trùng → xác nhận phần còn lại
~~~

Sau mỗi bước, kiểm tra balance, các phần nguồn, trạng thái và outbox. Chỉ kiểm tra cuối chuỗi có thể bỏ qua một khoảng thời gian hệ thống từng cấp lại hàng quá sớm cho đơn thứ ba.

Bộ kiểm thử thời gian nên dùng nguồn thời gian có thể điều khiển trong môi trường test. Không đưa khả năng giả thời gian thành header công khai trong môi trường vận hành.

## 11. Ví dụ tranh đơn vị cuối với thanh toán muộn

Chọn hợp đồng:

~~~text
Hàng đạt điều kiện bán: 1 đơn vị
Quyền giữ có hạn cứng
Mọi đường phân bổ và xuất kiểm tra quyền hiện hành
Thanh toán thành công sau khi quyền hết hạn:
    không hồi sinh quyền cũ
    xử lý giữ mới hoặc bù trừ theo chính sách
Chưa có lệnh lấy hoặc xuất cho quyền chỉ đang HELD
~~~

| Bước | Sự kiện | O | R | A | V |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | A và B cùng thấy thông tin còn một đơn vị | 1 | 0 | 0 | 1 |
| 2 | Transaction của A giữ thành công | 1 | 1 | 0 | 0 |
| 3 | B thử giữ và bị từ chối | 1 | 1 | 0 | 0 |
| 4 | Quyền A hết hạn hợp lệ, chuyển EXPIRED | 1 | 0 | 0 | 1 |
| 5 | B gửi yêu cầu hợp lệ mới và được giữ | 1 | 1 | 0 | 0 |
| 6 | Kết quả thanh toán A đến muộn | 1 | 1 | 0 | 0 |
| 7 | B đủ điều kiện chốt, chuyển giữ sang phân bổ | 1 | 0 | 1 | 0 |
| 8 | Kho xác nhận xuất cho B | 0 | 0 | 0 | 0 |
| 9 | Callback xuất B hoặc hủy A được phát lại | 0 | 0 | 0 | 0 |

Ở bước 6, tiền của A vẫn phải được xử lý đúng. Tuy nhiên, quyền A đã hết hạn và phần hàng đang thuộc quyền B nên callback đó không được tăng A hoặc tạo lệnh xuất cho A. Nếu chính sách cho thử giữ mới, yêu cầu mới sẽ thấy không còn dung lượng ở thời điểm này.

Nếu chọn bảo đảm hàng trong lúc thanh toán chưa được xác minh, bước 4 không được diễn ra theo cùng điều kiện; B sẽ chưa được giữ ở bước 5. Hai hợp đồng dẫn tới kết quả khác nhau nhưng đều cần một mô hình nhất quán.

## 12. Đối soát và vận hành

### 12.1. Đối chiếu balance với phần nguồn

Trên một snapshot nhất quán, có thể kiểm tra theo từng InventoryKey:

~~~text
R = tổng held_remaining của các phần quyền còn chiếm giữ
A = tổng allocated_remaining của các phần còn cam kết chưa xuất
~~~

Các trạng thái chờ thanh toán hoặc chờ hủy cần được tính theo hợp đồng đã chọn, không chỉ lọc duy nhất nhãn HELD hoặc ALLOCATED.

O cần đối soát với các chứng từ nhập, xuất, chuyển nhóm trạng thái và điều chỉnh thực tế đã được chấp nhận. Không suy ra tồn thực tế chỉ từ trạng thái thanh toán của đơn.

Tổng số không âm chưa đủ chứng minh hệ thống đúng. Có thể có hai quyền cùng giữ một đơn vị nhưng R chỉ phản ánh một quyền do mất cập nhật. Cần đối chiếu cả nguồn và tổng.

### 12.2. Dữ liệu audit cần trả lời được điều gì?

Mỗi thao tác quan trọng nên truy vết được:

~~~text
operation_id và khóa nguồn nghiệp vụ
tenant, chủ thể thực hiện, vai trò
order, order_line, reservation, allocation
InventoryKey
generation / version
số lượng trước và sau hoặc movement cụ thể
lý do, thời điểm, kết quả
chứng từ kho hoặc sự kiện bên ngoài liên quan
~~~

Từ đó cần giải thích được ai giữ phần hàng, vì sao được giải phóng, đơn nào tiêu dùng nó và sự kiện nào đã làm hàng rời kho.

### 12.3. Các tín hiệu cần điều tra

- R hoặc A âm, hoặc không khớp tổng các phần nguồn.
- V âm do sai lệch hoặc thiếu hụt thực tế.
- Nhiều quyền đang có hiệu lực cho cùng ý định ngoài chính sách.
- Quyền treo quá hạn mà không có lý do nghiệp vụ rõ ràng.
- Callback muộn thường xuyên làm đơn chờ xử lý.
- Một chủ thể giữ lượng lớn nhưng liên tục không hoàn tất.
- Lệnh kho lỗi thời hoặc lặp vẫn tạo chứng từ mới.
- Phần xuất hoặc nhận lại hàng không có nguồn được phép.
- Việc sửa đơn hoặc chạy công cụ quản trị làm biến động R/A bất thường.

Đối soát và sửa lệch phải phối hợp với các transaction đang hoạt động bằng khóa hoặc kiểm tra phiên bản. Không lấy báo cáo cập nhật chậm ghi đè balance hiện hành, không đặt toàn bộ R về 0 để “mở lại hàng”, và không bỏ lịch sử nguồn để làm các số trông khớp.

## 13. Câu hỏi tự đánh giá

1. Reserved quantity trong hệ thống là giữ tạm hay đã bao gồm lượng phân bổ?
2. Khóa tồn có đủ tenant, SKU, kho và các chiều trạng thái cần thiết không?
3. Tồn khả dụng được bảo vệ bằng cơ chế nguyên tử nào khi hai yêu cầu tranh phần cuối?
4. Mỗi phần R/A có nguồn reservation hoặc allocation và chủ thể được phép rõ ràng không?
5. Chuyển sang đơn đã chốt có vô tình làm tồn khả dụng tăng không?
6. Sửa số lượng, giao một phần và hủy phần còn lại có bảo toàn từng phần nguồn không?
7. Retry và thay idempotency key có tạo thêm quyền hoặc giải phóng trùng không?
8. Hết hạn khi thanh toán chưa rõ đang theo hợp đồng nào, và callback muộn xử lý ra sao?
9. Kho có thật sự từ chối lệnh cũ, hay chỉ đang nhận một trường generation không được thực thi?
10. Hàng đã xuất hoặc hàng trả chưa kiểm tra có bị cộng lại khả năng bán quá sớm không?
11. Những đường nhập đơn, sửa đơn và điều chỉnh quản trị có dùng cùng bất biến không?
12. Có thể đối soát O, R, A với chứng từ và phần nguồn ở một thời điểm nhất quán không?
